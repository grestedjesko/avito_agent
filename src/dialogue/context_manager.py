from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime


class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime = datetime.now()
    metadata: Optional[Dict] = None


class ConversationContext:
    def __init__(self, session_id: str, max_history: int = 10):
        self.session_id = session_id
        self.max_history = max_history
        self.messages: List[Message] = []
        self.metadata: Dict = {}
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> None:
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        self.messages.append(message)
        
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
    
    def get_history(self, last_n: Optional[int] = None) -> List[Message]:
        if last_n:
            return self.messages[-last_n:]
        return self.messages
    
    def get_history_text(self, last_n: Optional[int] = None) -> str:
        messages = self.get_history(last_n)
        
        history_parts = []
        for msg in messages:
            role_label = "Покупатель" if msg.role == "user" else "Продавец"
            history_parts.append(f"{role_label}: {msg.content}")
        
        return "\n".join(history_parts)
    
    def get_last_user_message(self) -> Optional[str]:
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
        return None
    
    def get_last_assistant_message(self) -> Optional[str]:
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg.content
        return None
    
    def set_metadata(self, key: str, value: any) -> None:
        self.metadata[key] = value
    
    def get_metadata(self, key: str) -> Optional[any]:
        return self.metadata.get(key)
    
    def clear_history(self) -> None:
        self.messages = []
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "messages": [msg.dict() for msg in self.messages],
            "metadata": self.metadata
        }


class ContextManager:
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.contexts: Dict[str, ConversationContext] = {}
    
    def get_or_create_context(self, session_id: str) -> ConversationContext:
        if session_id not in self.contexts:
            self.contexts[session_id] = ConversationContext(
                session_id=session_id,
                max_history=self.max_history
            )
        return self.contexts[session_id]
    
    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        return self.contexts.get(session_id)
    
    def delete_context(self, session_id: str) -> None:
        if session_id in self.contexts:
            del self.contexts[session_id]


_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
