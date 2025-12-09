from typing import Dict, Any
from src.agent.state import AgentState
from src.agent.tools import get_agent_tools
from src.llm.deepseek_client import get_deepseek_client
from src.llm.prompts import (
    RESPONSE_GENERATOR_SYSTEM_PROMPT,
    get_product_info_prompt,
    get_delivery_check_prompt,
    get_bargaining_prompt,
    get_clarification_prompt
)
from src.dialogue.slot_manager import get_slot_manager, Slots, Intent
from src.dialogue.context_manager import get_context_manager
from src.rag.hybrid_retriever import get_hybrid_retriever
from src.integrations.telegram_notifier import get_telegram_notifier
from src.integrations.calendar_service import get_calendar_service
from src.config import get_settings
from src.observability.logger import get_logger
from src.observability.metrics import get_metrics_collector
from src.observability.tracers import create_tracer

settings = get_settings()
tools = get_agent_tools()
llm_client = get_deepseek_client()
slot_manager = get_slot_manager()
context_manager = get_context_manager()
hybrid_retriever = get_hybrid_retriever(
    semantic_weight=settings.rag_semantic_weight, 
    keyword_weight=settings.rag_keyword_weight,
    use_query_expansion=True,
    use_llm_reranking=True
)
telegram = get_telegram_notifier()
calendar_service = get_calendar_service()


def classify_intent_node(state: AgentState) -> Dict[str, Any]:
    """Classify user intent with tracing and metrics."""
    session_id = state.get('session_id', 'unknown')
    logger = get_logger(__name__, session_id=session_id)
    metrics = get_metrics_collector()
    
    logger.info(f"Классификация намерения: {state['user_message'][:50]}...", node="classify_intent")
    
    node_metric = metrics.start_node_execution(
        session_id=session_id,
        node_name="classify_intent",
        metadata={'message_length': len(state['user_message'])}
    )
    
    try:
        context = context_manager.get_context(session_id)
        context_text = context.get_history_text(last_n=5) if context else None
        
        result = llm_client.classify_intent(
            state['user_message'],
            context_text,
            session_id=session_id
        )
        
        intent = result.get("intent", "general_question")
        confidence = result.get("confidence", 0.5)
        entities = result.get("entities", {})
        
        logger.info(
            f"Намерение: {intent} (confidence: {confidence:.2f})",
            node="classify_intent",
            intent=intent,
            confidence=confidence
        )
        
        if entities:
            logger.debug(f"Извлеченные entities: {entities}", node="classify_intent")
        
        # Record intent in metrics
        metrics.record_intent(session_id, intent)
        
        # Finish node metrics
        metrics.finish_node_execution(session_id, node_metric, success=True)
        
        return {
            "intent": intent,
            "intent_confidence": confidence,
            "entities": entities
        }
    
    except Exception as e:
        logger.error(f"Ошибка классификации намерения: {e}", exc_info=True, node="classify_intent")
        metrics.finish_node_execution(session_id, node_metric, success=False, error=str(e))
        # Fallback
        return {
            "intent": "general_question",
            "intent_confidence": 0.5,
            "entities": {}
        }


def check_slots_node(state: AgentState) -> Dict[str, Any]:
    print(f"Проверка слотов для намерения: {state['intent']}")
    current_slots = Slots(**state['slots'])
    updated_slots = slot_manager.extract_slots_from_entities(
        state['entities'],
        current_slots
    )
    
    if not updated_slots.product_id and state.get('product_id'):
        updated_slots.product_id = state['product_id']
        print(f"Используется product_id из контекста: {state['product_id']}")
    
    try:
        intent = Intent(state['intent'])
    except ValueError:
        intent = Intent.GENERAL_QUESTION
    
    is_complete, missing = slot_manager.check_slots_completeness(intent, updated_slots)
    clarification = None
    if not is_complete:
        clarification = slot_manager.generate_clarification_question(missing)
        print(f"Недостающие слоты: {missing}")
    
    return {
        "slots": updated_slots.model_dump(),
        "slots_complete": is_complete,
        "missing_slots": missing,
        "needs_clarification": not is_complete,
        "clarification_question": clarification
    }


def rag_search_node(state: AgentState) -> Dict[str, Any]:
    print("Поиск информации о товаре")
    query = state['user_message']
    
    if state.get('product_id'):
        print(f"Используется product_id из контекста: {state['product_id']}")
        product_context = hybrid_retriever.get_product_context(state['product_id'])
        if product_context:
            return {
                "rag_results": product_context,
                "relevance_score": 1.0,
                "action_type": "rag_search"
            }
    
    slots = state.get('slots', {})
    query_parts = [query]
    
    if slots.get('product_name'):
        query_parts.insert(0, slots['product_name'])
    if slots.get('product_color'):
        color_str = ', '.join(slots['product_color']) if isinstance(slots['product_color'], list) else slots['product_color']
        query_parts.append(color_str)
    if slots.get('product_memory'):
        memory_str = ', '.join(slots['product_memory']) if isinstance(slots['product_memory'], list) else slots['product_memory']
        query_parts.append(memory_str)
    if slots.get('product_variant'):
        query_parts.append(slots['product_variant'])
    
    query = " ".join(query_parts)
    print(f"Запрос: {query}")
    
    context = context_manager.get_context(state['session_id'])
    if context:
        last_assistant = context.get_last_assistant_message()
        if last_assistant and len(state['user_message'].split()) <= 3:
            query = f"{last_assistant[:100]} {query}"
    
    results = hybrid_retriever.retrieve(query)
    formatted = hybrid_retriever.retrieve_formatted(query)
    
    avg_score = sum(r['score'] for r in results) / len(results) if results else 0.0
    print(f"Найдено результатов: {len(results)}, средняя релевантность: {avg_score:.3f}")
    
    product_id = None
    if results and len(results) > 0:
        product_id = results[0].get('metadata', {}).get('product_id')
        print(f"Топ результат: product_id={product_id}")
    
    return {
        "rag_results": formatted,
        "relevance_score": avg_score,
        "action_type": "rag_search",
        "product_id": product_id
    }


def stock_check_node(state: AgentState) -> Dict[str, Any]:
    slots = state.get('slots', {})
    requested_memory = slots.get('product_memory')
    requested_color = slots.get('product_color')
    product_name = slots.get('product_name')
    
    product_id = state.get('product_id') or slots.get('product_id')
    
    if not product_id:
        query = state['user_message']
        
        if product_name:
            query = f"{product_name} {query}"
        if requested_color:
            color_str = ', '.join(requested_color) if isinstance(requested_color, list) else requested_color
            query = f"{query} {color_str}"
        if requested_memory:
            memory_str = ', '.join(requested_memory) if isinstance(requested_memory, list) else requested_memory
            query = f"{query} {memory_str}"
        
        results = hybrid_retriever.retrieve(query, top_k=5)
        
        if not results:
            return {
                "action_result": "Не смог определить, о каком товаре речь. Уточните название товара.",
                "action_type": "stock_check"
            }
        
        exact_match = None
        alternatives = []
        
        for result in results:
            result_product_id = result.get('metadata', {}).get('product_id')
            result_title = result.get('metadata', {}).get('title', '')
            score = result.get('score', 0)
            
            memory_match = True
            if requested_memory:
                # Handle both string and list of memory values
                memory_values = requested_memory if isinstance(requested_memory, list) else [requested_memory]
                title_normalized = result_title.upper().replace(' ', '')
                
                # Check if any of the requested memory values match
                memory_match = False
                for mem_val in memory_values:
                    memory_normalized = mem_val.upper().replace(' ', '').replace('ГБ', 'GB').replace('GB', '')
                    if memory_normalized in title_normalized or f"{memory_normalized}GB" in title_normalized:
                        memory_match = True
                        break
            
            if memory_match and not exact_match:
                exact_match = (result_product_id, result_title, score)
            elif not memory_match:
                alternatives.append((result_product_id, result_title, score))
        
        if exact_match:
            product_id, title, score = exact_match
        elif alternatives:
            alt_titles = [title for _, title, _ in alternatives[:3]]
            
            if requested_memory:
                memory_str = ' или '.join(requested_memory) if isinstance(requested_memory, list) else requested_memory
                alternatives_text = "\n- ".join(alt_titles)
                return {
                    "action_result": f"К сожалению, {product_name} на {memory_str} нет в наличии.\n\nНо есть другие варианты:\n- {alternatives_text}\n\nХотите узнать подробнее о них?",
                    "action_type": "stock_check"
                }
            else:
                product_id = alternatives[0][0]
        else:
            return {
                "action_result": "Не смог определить, о каком товаре речь. Уточните название товара.",
                "action_type": "stock_check"
            }
    
    result = tools.check_stock(product_id)
    
    if not result['found']:
        action_result = result['message']
    elif result['available']:
        action_result = f"Товар в наличии, доступно {result['quantity']} шт."
    else:
        action_result = "К сожалению, товара нет в наличии."
    
    return {
        "action_result": action_result,
        "product_id": product_id,
        "action_type": "stock_check"
    }


def delivery_check_node(state: AgentState) -> Dict[str, Any]:
    print("Проверка доставки")
    product_id = state.get('product_id') or state['slots'].get('product_id')
    if not product_id:
        results = hybrid_retriever.retrieve(state['user_message'], top_k=1)
        if results:
            product_id = results[0].get('metadata', {}).get('product_id')
    
    if not product_id:
        return {
            "action_result": "Не смог определить, о каком товаре речь. Уточните название товара.",
            "action_type": "delivery_check"
        }
    
    city = state['entities'].get('city') or state['slots'].get('city')
    delivery_service = state['entities'].get('delivery_service') or state['slots'].get('delivery_service')
    is_professional = state.get('is_professional_seller', False)
    
    result = tools.check_delivery(
        product_id,
        city=city,
        delivery_service=delivery_service,
        is_professional_seller=is_professional
    )
    
    if not result['found']:
        action_result = result['message']
    else:
        action_result = result['recommendation']
    
    return {
        "action_result": action_result,
        "product_id": product_id,
        "action_type": "delivery_check"
    }


def bargaining_node(state: AgentState) -> Dict[str, Any]:
    print("Обработка торга")
    product_id = state.get('product_id') or state['slots'].get('product_id')
    offered_price = state['slots'].get('offered_price')
    
    if not product_id:
        results = hybrid_retriever.retrieve(state['user_message'], top_k=1)
        if results:
            product_id = results[0].get('metadata', {}).get('product_id')
    
    if not product_id or not offered_price:
        missing = []
        if not product_id:
            missing.append("товар")
        if not offered_price:
            missing.append("предложенная цена")
        
        result = {
            "action_result": f"Не хватает информации: {', '.join(missing)}",
            "needs_clarification": True,
            "action_type": "bargaining"
        }
        if product_id:
            result["product_id"] = product_id
        return result
    
    result = tools.evaluate_bargaining(product_id, offered_price)
    
    if not result['found']:
        action_result = result['message']
    else:
        action_result = result['explanation']
        
        if result['decision'] == 'accept':
            state['slots']['agreed_price'] = offered_price
            
            product_info = tools.get_product_by_id(product_id)
            product_title = product_info.get('title', f'Товар {product_id}') if product_info else f'Товар {product_id}'
            
            telegram.notify_deal_agreed(
                product_title=product_title,
                agreed_price=offered_price
            )
    
    return {
        "action_result": action_result,
        "product_id": product_id,
        "action_type": "bargaining"
    }


def meeting_planning_node(state: AgentState) -> Dict[str, Any]:
    print("Планирование встречи")
    from meetings.meeting_validator import get_meeting_validator
    from datetime import datetime, timedelta
    
    validator = get_meeting_validator()
    
    product_id = state.get('product_id') or state['slots'].get('product_id')
    location = state['slots'].get('meeting_location')
    date = state['slots'].get('meeting_date')
    time = state['slots'].get('meeting_time')
    
    print(f"Параметры встречи: товар={product_id}, место={location}, дата={date}, время={time}")
    
    if not product_id:
        results = hybrid_retriever.retrieve(state['user_message'], top_k=1)
        if results:
            product_id = results[0].get('metadata', {}).get('product_id')
    
    if not product_id:
        return {
            "action_result": "Не указан товар для встречи. О каком товаре вы спрашиваете?",
            "needs_clarification": True,
            "action_type": "meeting_planning"
        }
    
    locations_result = tools.get_meeting_locations(product_id)
    
    if not locations_result['found']:
        return {
            "action_result": "Товар не найден.",
            "action_type": "meeting_planning"
        }
    
    available_locations = locations_result['locations']
    print(f"Доступные места встречи: {available_locations}")
    
    if location and location not in available_locations:
        locations_text = ", ".join(available_locations)
        action_result = (
            f"К сожалению, могу встретиться только в этих местах: {locations_text}. "
            f"Какое место вам удобно?"
        )
        return {
            "action_result": action_result,
            "needs_clarification": True,
            "action_type": "meeting_planning",
            "product_id": product_id
        }
    
    if not date:
        suggested_days = []
        today = datetime.now()
        
        for days_ahead in range(0, 4):
            check_date = today + timedelta(days=days_ahead)
            date_str = check_date.strftime("%Y-%m-%d")
            
            if days_ahead == 0:
                date_label = "сегодня"
            elif days_ahead == 1:
                date_label = "завтра"
            else:
                date_label = check_date.strftime("%d.%m")
            
            available_times = validator.get_available_slots(date_str)
            
            if available_times:
                first_time = available_times[0]
                last_time = available_times[-1]
                suggested_days.append(f"{date_label} с {first_time} до {last_time}")
                
                if len(suggested_days) >= 3:
                    break
        
        if suggested_days:
            days_text = ", ".join(suggested_days)
            locations_text = ", ".join(available_locations)
            action_result = (
                f"Могу встретиться: {days_text}. "
                f"Доступные места: {locations_text}. "
                f"Какие день, время и место вам удобны?"
            )
        else:
            action_result = "К сожалению, ближайшие дни заняты. Предложите удобное вам время."
        return {
            "action_result": action_result,
            "needs_clarification": True,
            "action_type": "meeting_planning",
            "product_id": product_id
        }
    
    if date and not time:
        if date.lower() == "сегодня":
            date_obj = datetime.now()
            date_str = date_obj.strftime("%Y-%m-%d")
            date_label = "сегодня"
        elif date.lower() == "завтра":
            date_obj = datetime.now() + timedelta(days=1)
            date_str = date_obj.strftime("%Y-%m-%d")
            date_label = "завтра"
        else:
            date_str = date
            date_label = date
        
        available_times = validator.get_available_slots(date_str)
        
        if available_times:
            first_time = available_times[0]
            last_time = available_times[-1]
            action_result = (
                f"На {date_label} можно с {first_time} до {last_time}. "
                f"Во сколько вам удобно?"
            )
        else:
            action_result = f"К сожалению, на {date_label} все время занято. Предложите другой день?"
        
        return {
            "action_result": action_result,
            "needs_clarification": True,
            "action_type": "meeting_planning"
        }
    
    if date and time and not location:
        is_valid, issues, suggestion = validator.validate_meeting_time(date, time)
        
        if not is_valid:
            issue_text = ", ".join(issues)
            action_result = f"❌ К сожалению, {date} в {time} не подходит ({issue_text}). {suggestion if suggestion else 'Предложите другое время.'}"
            
            return {
                "action_result": action_result,
                "needs_clarification": True,
                "action_type": "meeting_planning"
            }
        
        locations_text = ", ".join(available_locations)
        action_result = f"Отлично, {date} в {time}. Где встретимся? Доступны: {locations_text}"
        
        return {
            "action_result": action_result,
            "needs_clarification": True,
            "action_type": "meeting_planning"
        }
    
    if date and time and location:
        is_valid, issues, suggestion = validator.validate_meeting_time(date, time, location)
        
        if not is_valid:
            issue_text = ", ".join(issues)
            action_result = f"❌ К сожалению, {date} в {time} не подходит ({issue_text}). {suggestion if suggestion else 'Предложите другое время.'}"
            
            return {
                "action_result": action_result,
                "needs_clarification": True,
                "action_type": "meeting_planning"
            }
        
        product_title = locations_result['product_title']
        product_price = locations_result.get('price')
        
        final_price = state['slots'].get('agreed_price') or product_price
        
        print("Резервирование товара...")
        reserve_result = tools.reserve_product(product_id, quantity=1)
        
        if not reserve_result['success']:
            print(f"Ошибка резервирования: {reserve_result['message']}")
            action_result = (
                f"К сожалению, не удалось зарезервировать товар: {reserve_result['message']}. "
                f"Попробуйте выбрать другое время или товар."
            )
            return {
                "action_result": action_result,
                "action_type": "meeting_planning"
            }
        
        print("Товар зарезервирован")
        
        if date.lower() == "сегодня":
            date_str = datetime.now().strftime("%Y-%m-%d")
        elif date.lower() == "завтра":
            date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            try:
                if '.' in date:
                    parts = date.split('.')
                    if len(parts) == 2:
                        day, month = parts
                        year = datetime.now().year
                        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
                    else:
                        day, month, year = parts
                        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
                else:
                    date_str = date
            except Exception as e:
                date_str = date
        
        calendar_link = None
        if calendar_service.is_enabled():
            print("Создание события в календаре...")
            
            description = f"Продажа товара: {product_title}\nМесто встречи: {location}"
            if final_price:
                description += f"\nЦена: {final_price:,.0f} руб."
            
            event_data = calendar_service.create_event(
                title=f"Встреча: {product_title}",
                location=location,
                date_str=date_str,
                time_str=time,
                duration_minutes=30,
                description=description
            )
            
            if event_data:
                calendar_link = event_data.get('link')
                print(f"Событие создано: {calendar_link}")
        
        action_result = (
            f"Договорились! Встречаемся {date} в {time}, место: {location}. "
            f"Товар: {product_title}"
        )
        
        if final_price:
            action_result += f", цена: {final_price:,.0f} руб."
        
        action_result += ". "
        
        if calendar_link:
            action_result += f"Добавил встречу в календарь. Товар зарезервирован. Жду вас!"
        else:
            action_result += f"Товар зарезервирован. Жду вас!"
        
        telegram.notify_meeting_scheduled(
            product_title=product_title,
            location=location,
            date=date,
            time=time,
            price=final_price,
            calendar_link=calendar_link
        )
        
        return {
            "action_result": action_result,
            "product_id": product_id,
            "action_type": "meeting_planning",
            "calendar_event_created": bool(calendar_link),
            "product_reserved": True
        }
    
    missing_info = []
    if not location:
        missing_info.append(f"место ({', '.join(available_locations)})")
    if not date:
        missing_info.append("дата")
    if not time:
        missing_info.append("время")
    
    return {
        "action_result": f"Уточните: {', '.join(missing_info)}",
        "needs_clarification": True,
        "action_type": "meeting_planning"
    }


def generate_response_node(state: AgentState) -> Dict[str, Any]:
    """Generate response with tracing and metrics."""
    session_id = state.get('session_id', 'unknown')
    logger = get_logger(__name__, session_id=session_id)
    metrics = get_metrics_collector()
    
    logger.info("Генерация ответа", node="generate_response")
    
    node_metric = metrics.start_node_execution(
        session_id=session_id,
        node_name="generate_response",
        metadata={'intent': state.get('intent')}
    )
    
    try:
        context_parts = []
        
        action_result = state.get('action_result')
        rag_results = state.get('rag_results')
        has_data = bool(action_result or rag_results)
        
        if action_result:
            context_parts.append(f"Результат действия:\n{action_result}")
        
        if not has_data and state.get('needs_clarification') and state.get('clarification_question'):
            metrics.finish_node_execution(session_id, node_metric, success=True)
            return {
                "response": state['clarification_question']
            }
        
        conversation_context = context_manager.get_context(session_id)
        if conversation_context:
            history = conversation_context.get_history_text(last_n=3)
            if history:
                context_parts.append(f"История диалога:\n{history}")
        
        if rag_results:
            context_parts.append(f"Информация из базы:\n{rag_results}")
        
        has_data = bool(state.get('rag_results') or action_result)
        
        if not has_data and state.get('intent') in ['stock_check', 'product_info']:
            context_parts.append(
                "ВАЖНО: Данные о товаре не найдены в базе. "
                "НЕ ВЫДУМЫВАЙ информацию. Скажи, что уточнишь у продавца."
            )
        
        context = "\n\n".join(context_parts) if context_parts else "Нет дополнительного контекста."
        
        response = llm_client.generate_response(
            system_prompt=RESPONSE_GENERATOR_SYSTEM_PROMPT,
            user_message=state['user_message'],
            context=context,
            session_id=session_id
        )
        
        logger.info(
            f"Ответ сгенерирован: {response[:100]}...",
            node="generate_response",
            response_length=len(response)
        )
        
        metrics.finish_node_execution(session_id, node_metric, success=True)
        
        return {
            "response": response.strip()
        }
    
    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}", exc_info=True, node="generate_response")
        metrics.finish_node_execution(session_id, node_metric, success=False, error=str(e))
        return {
            "response": "Извините, возникла ошибка при генерации ответа. Попробуйте переформулировать вопрос."
        }


def planning_node(state: AgentState) -> Dict[str, Any]:
    """
    Стратегическое планирование выполнения запроса с трейсингом.
    Создает пошаговый план для сложных запросов.
    """
    session_id = state.get('session_id', 'unknown')
    logger = get_logger(__name__, session_id=session_id)
    metrics = get_metrics_collector()
    
    logger.info("📋 Planning: создание плана выполнения...", node="planning")
    
    node_metric = metrics.start_node_execution(
        session_id=session_id,
        node_name="planning",
        metadata={'intent': state.get('intent')}
    )
    
    try:
        user_message = state['user_message']
        intent = state.get('intent', 'general_question')
        entities = state.get('entities', {})
        
        context = None
        conversation_context = context_manager.get_context(session_id)
        if conversation_context:
            context = conversation_context.get_history_text(last_n=3)
        
        plan = llm_client.create_plan(
            user_message=user_message,
            intent=intent,
            entities=entities,
            context=context,
            session_id=session_id
        )
        
        complexity = plan.get('complexity', 'medium')
        estimated_steps = plan.get('estimated_steps', 2)
        plan_steps = plan.get('plan', [])
        
        logger.info(
            f"📊 Сложность запроса: {complexity}, Запланировано шагов: {estimated_steps}",
            node="planning",
            complexity=complexity,
            steps=estimated_steps
        )
        
        if plan_steps:
            logger.debug("🎯 План действий:", node="planning")
            for step in plan_steps[:3]:
                logger.debug(f"   {step['step']}. {step['action']} - {step['goal']}", node="planning")
        
        first_action = None
        if plan_steps and len(plan_steps) > 0:
            first_action = plan_steps[0].get('action')
            logger.info(f"▶️  Первое действие: {first_action}", node="planning")
        
        metrics.finish_node_execution(session_id, node_metric, success=True)
        
        return {
            "execution_plan": plan,
            "current_step": 0,
            "plan_complexity": complexity,
            "completed_steps": [],
            "next_planned_action": first_action
        }
    
    except Exception as e:
        logger.error(f"Ошибка планирования: {e}", exc_info=True, node="planning")
        metrics.finish_node_execution(session_id, node_metric, success=False, error=str(e))
        return {
            "execution_plan": {"complexity": "simple", "plan": []},
            "current_step": 0,
            "plan_complexity": "simple",
            "completed_steps": [],
            "next_planned_action": None
        }


def intelligent_route_node(state: AgentState) -> Dict[str, Any]:
    """
    Интеллектуальная маршрутизация на основе LLM.
    Анализирует состояние и принимает решение о следующем узле.
    """
    print("🧠 Intelligent Routing: анализ маршрута...")
    
    intent = state.get('intent', 'general_question')
    intent_confidence = state.get('intent_confidence', 0.5)
    slots_complete = state.get('slots_complete', False)
    missing_slots = state.get('missing_slots', [])
    user_message = state['user_message']
    
    has_rag_results = bool(state.get('rag_results'))
    has_action_result = bool(state.get('action_result'))
    
    execution_plan = state.get('execution_plan')
    if execution_plan and execution_plan.get('plan'):
        current_step = state.get('current_step', 0)
        plan_steps = execution_plan['plan']
        
        if current_step < len(plan_steps):
            next_action = plan_steps[current_step].get('action')
            print(f"📋 Следую плану: шаг {current_step + 1}/{len(plan_steps)} -> {next_action}")
            
            return {
                "routing_decision": next_action,
                "routing_reasoning": f"Выполнение шага {current_step + 1} плана",
                "routing_confidence": 0.9,
                "current_step": current_step + 1,
                "completed_steps": state.get('completed_steps', []) + [next_action]
            }
    
    routing_result = llm_client.route_decision(
        intent=intent,
        intent_confidence=intent_confidence,
        slots_complete=slots_complete,
        missing_slots=missing_slots,
        has_rag_results=has_rag_results,
        has_action_result=has_action_result,
        user_message=user_message
    )
    
    next_node = routing_result.get('next_node', 'rag_search')
    confidence = routing_result.get('confidence', 0.5)
    reasoning = routing_result.get('reasoning', 'LLM routing decision')
    alternatives = routing_result.get('alternative_nodes', [])
    
    print(f"🎯 Решение: {next_node} (уверенность: {confidence:.2f})")
    print(f"💭 Обоснование: {reasoning[:100]}...")
    
    if alternatives:
        print(f"🔀 Альтернативы: {', '.join(alternatives[:2])}")
    
    return {
        "routing_decision": next_node,
        "routing_reasoning": reasoning,
        "routing_confidence": confidence,
        "alternative_routes": alternatives
    }


def reflection_node(state: AgentState) -> Dict[str, Any]:
    """
    Критическая проверка качества сгенерированного ответа с трейсингом.
    Валидирует ответ на соответствие критериям качества.
    """
    session_id = state.get('session_id', 'unknown')
    logger = get_logger(__name__, session_id=session_id)
    metrics = get_metrics_collector()
    
    logger.info("🔍 Reflection: проверка качества ответа...", node="reflection")
    
    node_metric = metrics.start_node_execution(
        session_id=session_id,
        node_name="reflection",
        metadata={'regeneration_count': state.get('regeneration_count', 0)}
    )
    
    try:
        response = state.get('response', '')
        regeneration_count = state.get('regeneration_count', 0)
        
        if regeneration_count >= 2:
            logger.warning("⚠️  Достигнут лимит регенераций, пропускаем валидацию", node="reflection")
            metrics.finish_node_execution(session_id, node_metric, success=True)
            return {
                "reflection_result": {"is_valid": True, "reason": "max_retries_reached"},
                "response_quality_score": 6.0,
                "needs_regeneration": False
            }
        
        if state.get('needs_clarification') and state.get('clarification_question'):
            logger.info("✓ Вопрос уточнения, валидация не требуется", node="reflection")
            metrics.finish_node_execution(session_id, node_metric, success=True)
            return {
                "reflection_result": {"is_valid": True, "reason": "clarification_question"},
                "response_quality_score": 8.0,
                "needs_regeneration": False
            }
        
        validation_result = llm_client.validate_response(
            response=response,
            user_message=state['user_message'],
            context=state.get('rag_results'),
            action_result=state.get('action_result'),
            intent=state.get('intent'),
            session_id=session_id
        )
        
        is_valid = validation_result.get('is_valid', True)
        overall_score = validation_result.get('overall_score', 7.0)
        issues = validation_result.get('issues', [])
        critical_error = validation_result.get('critical_error')
        
        if critical_error:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {critical_error}", node="reflection")
        elif issues:
            logger.warning(f"⚠️  Найдено проблем: {len(issues)}", node="reflection")
            for issue in issues[:3]:
                logger.debug(f"   - {issue}", node="reflection")
        
        logger.info(
            f"📊 Оценка качества: {overall_score:.1f}/10 | Валиден: {is_valid}",
            node="reflection",
            quality_score=overall_score,
            is_valid=is_valid
        )
        
        # Record quality score
        metrics.record_score(
            session_id=session_id,
            name="response_quality",
            value=overall_score / 10.0,  # Normalize to 0-1
            comment=f"Valid: {is_valid}, Issues: {len(issues)}"
        )
        
        needs_regen = not is_valid and regeneration_count < 2
        
        if needs_regen:
            logger.info("🔄 Требуется регенерация ответа", node="reflection")
        else:
            logger.info("✓ Ответ прошел валидацию", node="reflection")
        
        # Finish node metrics
        metrics.finish_node_execution(session_id, node_metric, success=True)
        
        return {
            "reflection_result": validation_result,
            "response_quality_score": overall_score,
            "needs_regeneration": needs_regen,
            "regeneration_count": regeneration_count + (1 if needs_regen else 0),
            "validation_passed": is_valid
        }
    
    except Exception as e:
        logger.error(f"Ошибка в reflection: {e}", exc_info=True, node="reflection")
        metrics.finish_node_execution(session_id, node_metric, success=False, error=str(e))
        return {
            "reflection_result": {"is_valid": True, "reason": "error_fallback"},
            "response_quality_score": 7.0,
            "needs_regeneration": False
        }


def confidence_aware_routing(state: AgentState) -> str:
    """
    Интеллектуальная маршрутизация на основе уверенности в намерении.
    Низкая уверенность -> уточнение, высокая -> выполнение действия.
    """
    confidence = state.get('intent_confidence', 0.5)
    intent = state.get('intent', 'general_question')
    slots_complete = state.get('slots_complete', False)
    
    print(f"🎯 Confidence routing: уверенность={confidence:.2f}, намерение={intent}")
    
    # Низкая уверенность (< 0.6) -> требуется уточнение
    if confidence < 0.6:
        print("⚠️  Низкая уверенность -> уточнение")
        return "clarification"
    
    # Средняя уверенность (0.6-0.8) -> проверяем полноту слотов
    if confidence < 0.8:
        if not slots_complete:
            print("⚠️  Средняя уверенность + неполные слоты -> уточнение")
            return "clarification"
        else:
            print("✓ Средняя уверенность + полные слоты -> выполнение")
            return "execute"
    
    # Высокая уверенность (>= 0.8) -> выполнение
    print("✓ Высокая уверенность -> выполнение")
    return "execute"


def route_intent(state: AgentState) -> str:
    intent = state.get('intent', 'general_question')
    
    context_aware_intents = {
        'product_info': 'rag_search',
        'warranty_question': 'rag_search',
        'general_question': 'rag_search',
        'stock_check': 'stock_check',
        'meeting_planning': 'meeting_planning',
    }
    
    if intent in context_aware_intents:
        return context_aware_intents[intent]
    
    if state.get('needs_clarification'):
        return "generate_response"
    
    routing = {
        'delivery_question': 'delivery_check',
        'bargaining': 'bargaining',
    }
    
    return routing.get(intent, 'rag_search')


def route_after_reflection(state: AgentState) -> str:
    """Маршрутизация после reflection node"""
    if state.get('needs_regeneration', False):
        print("🔄 Переход на регенерацию ответа")
        return "regenerate"
    else:
        print("✓ Завершение обработки")
        return "end"


def route_from_intelligent_router(state: AgentState) -> str:
    """
    Использует решение intelligent_route_node для выбора следующего узла
    """
    routing_decision = state.get('routing_decision', 'rag_search')
    
    # Маппинг возможных решений
    valid_routes = {
        'rag_search': 'rag_search',
        'stock_check': 'stock_check',
        'delivery_check': 'delivery_check',
        'bargaining': 'bargaining',
        'meeting_planning': 'meeting_planning',
        'generate_response': 'generate_response'
    }
    
    return valid_routes.get(routing_decision, 'rag_search')


def route_after_action(state: AgentState) -> str:
    """
    Маршрутизация после выполнения action узла.
    Проверяет, есть ли еще шаги в плане.
    """
    execution_plan = state.get('execution_plan')
    current_step = state.get('current_step', 0)
    
    # Если есть план и еще остались шаги
    if execution_plan and execution_plan.get('plan'):
        plan_steps = execution_plan['plan']
        
        if current_step < len(plan_steps):
            print(f"📋 План не завершен: шаг {current_step}/{len(plan_steps)} -> возврат в router")
            return "continue_plan"
    
    # План завершен или его не было -> переходим к генерации ответа
    print("✓ План завершен или отсутствует -> генерация ответа")
    return "generate_response"


def route_by_complexity(state: AgentState) -> str:
    """
    Маршрутизация на основе сложности запроса.
    Простые -> прямая обработка, сложные -> через planning.
    """
    intent_confidence = state.get('intent_confidence', 0.5)
    slots_complete = state.get('slots_complete', False)
    intent = state.get('intent', 'general_question')
    slots = state.get('slots', {})
    
    # Определяем сложность запроса
    is_complex = False
    complexity_reason = None
    
    # Сложные намерения, всегда требующие планирования
    complex_intents = ['bargaining', 'meeting_planning']
    
    # Намерения, требующие product_id для выполнения
    product_dependent_intents = ['delivery_question', 'bargaining', 'warranty_question', 'meeting_planning']
    
    # 1. Всегда сложные намерения
    if intent in complex_intents:
        is_complex = True
        complexity_reason = f"Намерение {intent} требует многошагового планирования"
    
    # 2. Многошаговый запрос: есть product_name, но нужен product_id
    # Требуется: RAG search (найти товар) -> затем выполнение действия
    elif intent in product_dependent_intents:
        has_product_name = slots.get('product_name') is not None
        has_product_id = slots.get('product_id') or state.get('product_id')
        
        if has_product_name and not has_product_id:
            is_complex = True
            complexity_reason = f"Требуется найти товар '{slots.get('product_name')}' перед выполнением {intent}"
    
    # 3. Низкая уверенность + неполные слоты
    elif intent_confidence < 0.7 and not slots_complete:
        is_complex = True
        complexity_reason = f"Низкая уверенность ({intent_confidence:.2f}) и неполные слоты"
    
    if is_complex:
        print(f"🎯 Сложный запрос -> Planning")
        if complexity_reason:
            print(f"   Причина: {complexity_reason}")
        return "planning"
    else:
        print("✓ Простой запрос -> Intelligent Router")
        return "intelligent_router"
