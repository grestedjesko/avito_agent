from typing import Any, Dict, List, Optional
from openai import OpenAI
import json
import logging

from src.config import get_settings
from src.observability.langfuse_config import get_langfuse_callback, langfuse_manager
from src.observability.logger import get_logger
from src.llm.prompts import (
    INTENT_CLASSIFIER_SYSTEM_PROMPT, 
    REFLECTION_VALIDATOR_PROMPT,
    LLM_ROUTER_PROMPT,
    PLANNING_PROMPT
)

logger = get_logger(__name__)


class DeepSeekClient:
    def __init__(self):
        settings = get_settings()
        
        self.client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        
        self.model = "deepseek-chat"
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
        operation_name: str = "chat"
    ) -> tuple[str, Dict[str, int]]:
        """
        Make a chat completion request with tracing.
        
        Returns:
            Tuple of (response_text, usage_dict)
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        try:
            logger.debug(
                f"LLM request: {operation_name}",
                session_id=session_id,
                model=self.model,
                temperature=kwargs["temperature"]
            )
            
            response = self.client.chat.completions.create(**kwargs)
            
            content = response.choices[0].message.content or ""
            usage = {
                'input_tokens': response.usage.prompt_tokens if response.usage else 0,
                'output_tokens': response.usage.completion_tokens if response.usage else 0,
                'total_tokens': response.usage.total_tokens if response.usage else 0
            }
            
            self.total_input_tokens += usage['input_tokens']
            self.total_output_tokens += usage['output_tokens']
            
            cost = (usage['input_tokens'] / 1_000_000 * 0.14) + \
                   (usage['output_tokens'] / 1_000_000 * 0.28)
            self.total_cost += cost
            
            logger.debug(
                f"LLM response: {operation_name}",
                session_id=session_id,
                input_tokens=usage['input_tokens'],
                output_tokens=usage['output_tokens'],
                cost_usd=f"{cost:.6f}"
            )
            
            if langfuse_manager.is_enabled() and session_id:
                try:
                    trace = langfuse_manager.create_trace(
                        name=f"llm_{operation_name}",
                        session_id=session_id,
                        input_data={'messages': messages},
                        metadata={
                            'model': self.model,
                            'temperature': kwargs['temperature'],
                            'max_tokens': kwargs['max_tokens']
                        }
                    )
                    
                    if trace:
                        trace.generation(
                            name=operation_name,
                            model=self.model,
                            input=messages,
                            output=content,
                            usage={
                                'input': usage['input_tokens'],
                                'output': usage['output_tokens'],
                                'total': usage['total_tokens']
                            },
                            metadata={'cost_usd': cost}
                        )
                        
                except Exception as e:
                    logger.warning(f"Failed to report to Langfuse: {e}")
            
            return content, usage
            
        except Exception as e:
            logger.error(
                f"LLM error: {operation_name}",
                session_id=session_id,
                exc_info=True
            )
            raise
    
    def classify_intent(
        self,
        user_message: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Classify user intent with tracing."""
        system_prompt = INTENT_CLASSIFIER_SYSTEM_PROMPT

        user_prompt = f"Сообщение пользователя: {user_message}"
        if context:
            user_prompt += f"\n\nКонтекст предыдущих сообщений:\n{context}"
            user_prompt += "\n\nУчитывай контекст! Если пользователь дает короткий ответ, вероятно это уточнение к предыдущему вопросу."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response, usage = self.chat(
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
            session_id=session_id,
            operation_name="classify_intent"
        )
        
        try:
            result = json.loads(response)
            
            if langfuse_manager.is_enabled() and session_id:
                confidence = result.get('confidence', 0.5)
                langfuse_manager.score(
                    name="intent_confidence",
                    value=confidence,
                    comment=f"Intent: {result.get('intent')}"
                )
            
            return result
        except json.JSONDecodeError:
            logger.error("Failed to parse intent classification response")
            return {
                "intent": "general_question",
                "confidence": 0.5,
                "entities": {}
            }
    
    def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """Generate response with tracing."""
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        if context:
            messages.append({"role": "system", "content": f"Контекст: {context}"})
        
        messages.append({"role": "user", "content": user_message})
        
        response, usage = self.chat(
            messages=messages,
            session_id=session_id,
            operation_name="generate_response"
        )
        return response
    
    def validate_response(
        self,
        response: str,
        user_message: str,
        context: Optional[str] = None,
        action_result: Optional[str] = None,
        intent: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Валидация качества сгенерированного ответа с трейсингом."""
        
        validation_prompt = f"""
ОТВЕТ ДЛЯ ПРОВЕРКИ:
{response}

ИСХОДНЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{user_message}

НАМЕРЕНИЕ: {intent or 'не определено'}
"""
        
        if context:
            validation_prompt += f"\n\nКОНТЕКСТ/ИНФОРМАЦИЯ ИЗ БАЗЫ:\n{context}"
        
        if action_result:
            validation_prompt += f"\n\nРЕЗУЛЬТАТ ДЕЙСТВИЯ:\n{action_result}"
        
        validation_prompt += "\n\nПРОВЕДИ КРИТИЧЕСКУЮ ОЦЕНКУ ОТВЕТА."
        
        messages = [
            {"role": "system", "content": REFLECTION_VALIDATOR_PROMPT},
            {"role": "user", "content": validation_prompt}
        ]
        
        try:
            response_text, usage = self.chat(
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"},
                session_id=session_id,
                operation_name="validate_response"
            )
            
            result = json.loads(response_text)
            
            if "is_valid" not in result:
                result["is_valid"] = result.get("overall_score", 0) >= 7.0
            
            if langfuse_manager.is_enabled() and session_id:
                score = result.get("overall_score", 7.0)
                langfuse_manager.score(
                    name="response_quality",
                    value=score / 10.0,
                    comment=f"Validation: {'valid' if result['is_valid'] else 'invalid'}"
                )
            
            return result
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Ошибка валидации ответа: {e}", exc_info=True)
            return {
                "is_valid": True,
                "overall_score": 7.0,
                "issues": [],
                "suggestions": "",
                "critical_error": None
            }
    
    def route_decision(
        self,
        intent: str,
        intent_confidence: float,
        slots_complete: bool,
        missing_slots: List[str],
        has_rag_results: bool = False,
        has_action_result: bool = False,
        previous_nodes: Optional[List[str]] = None,
        user_message: str = "",
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Интеллектуальная маршрутизация с помощью LLM и трейсингом."""
        
        routing_prompt = f"""
ТЕКУЩЕЕ СОСТОЯНИЕ:
- Сообщение пользователя: {user_message}
- Намерение: {intent}
- Уверенность в намерении: {intent_confidence:.2f}
- Слоты заполнены: {'Да' if slots_complete else 'Нет'}
- Недостающие слоты: {', '.join(missing_slots) if missing_slots else 'нет'}
- Есть результаты RAG: {'Да' if has_rag_results else 'Нет'}
- Есть результат действия: {'Да' if has_action_result else 'Нет'}
- Пройденные узлы: {', '.join(previous_nodes) if previous_nodes else 'нет'}

ЗАДАЧА: Определи, какой узел вызвать следующим для оптимальной обработки запроса.
"""
        
        messages = [
            {"role": "system", "content": LLM_ROUTER_PROMPT},
            {"role": "user", "content": routing_prompt}
        ]
        
        try:
            response_text, usage = self.chat(
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
                session_id=session_id,
                operation_name="route_decision"
            )
            
            result = json.loads(response_text)
            
            valid_nodes = [
                "rag_search", "stock_check", "delivery_check", 
                "bargaining", "meeting_planning", "generate_response"
            ]
            
            if result.get("next_node") not in valid_nodes:
                result["next_node"] = "generate_response"
            
            return result
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Ошибка LLM routing: {e}", exc_info=True)
            return {
                "next_node": "rag_search",
                "confidence": 0.5,
                "reasoning": "Fallback из-за ошибки LLM routing",
                "alternative_nodes": [],
                "estimated_complexity": "medium"
            }
    
    def create_plan(
        self,
        user_message: str,
        intent: str,
        entities: Dict[str, Any],
        context: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Создание плана выполнения запроса с трейсингом."""
        
        planning_prompt = f"""
ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_message}

ОПРЕДЕЛЕННОЕ НАМЕРЕНИЕ: {intent}

ИЗВЛЕЧЕННЫЕ СУЩНОСТИ: {entities}
"""
        
        if context:
            planning_prompt += f"\nКОНТЕКСТ БЕСЕДЫ:\n{context}"
        
        planning_prompt += "\n\nСОСТАВЬ ОПТИМАЛЬНЫЙ ПЛАН ВЫПОЛНЕНИЯ ЭТОГО ЗАПРОСА."
        
        messages = [
            {"role": "system", "content": PLANNING_PROMPT},
            {"role": "user", "content": planning_prompt}
        ]
        
        try:
            response_text, usage = self.chat(
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
                session_id=session_id,
                operation_name="create_plan"
            )
            
            result = json.loads(response_text)
            
            if "complexity" not in result:
                result["complexity"] = "medium"
            if "plan" not in result:
                result["plan"] = []
            
            if langfuse_manager.is_enabled() and session_id:
                complexity_score = {
                    "simple": 0.3,
                    "medium": 0.6,
                    "complex": 1.0
                }.get(result.get("complexity", "medium"), 0.6)
                
                langfuse_manager.score(
                    name="plan_complexity",
                    value=complexity_score,
                    comment=f"Steps: {result.get('estimated_steps', len(result.get('plan', [])))}"
                )
            
            return result
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Ошибка планирования: {e}", exc_info=True)
            return {
                "complexity": "simple",
                "estimated_steps": 2,
                "plan": [
                    {
                        "step": 1,
                        "action": "rag_search",
                        "goal": "Найти информацию",
                        "required_data": [],
                        "expected_output": "info"
                    },
                    {
                        "step": 2,
                        "action": "generate_response",
                        "goal": "Ответить пользователю",
                        "required_data": [],
                        "depends_on": [1]
                    }
                ],
                "success_criteria": "Ответ сгенерирован",
                "fallback_plan": "Уточнить у пользователя",
                "estimated_time": "3-5 секунд"
            }
    
    def get_usage_stats(self) -> Dict[str, Any]:
        return {
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'total_tokens': self.total_input_tokens + self.total_output_tokens,
            'total_cost_usd': round(self.total_cost, 4)
        }


_client: Optional[DeepSeekClient] = None


def get_deepseek_client() -> DeepSeekClient:
    global _client
    if _client is None:
        _client = DeepSeekClient()
    return _client
