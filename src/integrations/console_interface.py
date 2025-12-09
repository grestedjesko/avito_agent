import uuid
from typing import Optional
from agent.graph import get_agent_graph
from agent.state import AgentState
from dialogue.context_manager import get_context_manager
from observability.tracers import create_tracer
from integrations.telegram_notifier import get_telegram_notifier


class ConsoleInterface:
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.agent = get_agent_graph()
        self.context_manager = get_context_manager()
        self.context = self.context_manager.get_or_create_context(self.session_id)
        self.tracer = create_tracer(self.session_id)
        self.telegram = get_telegram_notifier()
        
        self.current_slots = {}
        self.current_product_id = None
        
        print(f"Сессия: {self.session_id}")
        print("Введите 'выход' для завершения")
    
    def run(self) -> None:
        """Run interactive console session."""
        while True:
            print("\n" + "-" * 70)
            user_input = input("Вы: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['выход', 'quit', 'exit', 'q']:
                print("\nДо свидания!")
                break
            
            # Отправляем уведомление о новом сообщении
            self.telegram.notify_new_message(user_input, self.session_id)
            
            self.context.add_message("user", user_input)
            
            response = self.process_message(user_input)
            
            self.context.add_message("assistant", response)
            
            print(f"\nАгент: {response}")
    
    def process_message(self, user_message: str) -> str:
        try:
            self.tracer.start_trace(
                name="agent_conversation",
                metadata={"user_message": user_message}
            )
            
            initial_state: AgentState = {
                "messages": [],
                "user_message": user_message,
                "session_id": self.session_id,
                "intent": None,
                "intent_confidence": 0.0,
                "entities": {},
                "slots": self.current_slots.copy(),
                "slots_complete": False,
                "missing_slots": [],
                "product_id": self.current_product_id,
                "product_context": None,
                "rag_results": None,
                "relevance_score": 0.0,
                "action_result": None,
                "action_type": None,
                "response": "",
                "needs_clarification": False,
                "clarification_question": None,
                "validation_passed": True,
                "validation_issues": [],
                "step_count": 0,
                "error": None
            }
            
            print("Обработка сообщения...")
            result = self.agent.invoke(initial_state)
            
            self.current_slots = result.get('slots', {})
            if result.get('product_id'):
                self.current_product_id = result.get('product_id')
            
            self.tracer.log_event(
                name="agent_response",
                metadata={
                    "intent": result.get('intent'),
                    "action_type": result.get('action_type'),
                    "response": result.get('response', '')[:100],
                    "slots": self.current_slots,
                    "product_id": self.current_product_id
                }
            )
            
            self.tracer.end_trace()
            
            return result.get('response', "Извините, произошла ошибка.")
            
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            
            self.tracer.log_event(
                name="error",
                level="ERROR",
                metadata={"error": error_msg}
            )
            self.tracer.end_trace()
            
            return "Извините, произошла ошибка при обработке запроса."


def run_console_interface(session_id: Optional[str] = None) -> None:
    interface = ConsoleInterface(session_id)
    interface.run()
