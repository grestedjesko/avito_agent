from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from enum import Enum


class Intent(str, Enum):
    PRODUCT_INFO = "product_info"
    STOCK_CHECK = "stock_check"
    DELIVERY_QUESTION = "delivery_question"
    WARRANTY_QUESTION = "warranty_question"
    BARGAINING = "bargaining"
    MEETING_PLANNING = "meeting_planning"
    GENERAL_QUESTION = "general_question"


class Slots(BaseModel):
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    product_color: Optional[str] = None
    product_memory: Optional[str] = None
    product_variant: Optional[str] = None
    
    offered_price: Optional[float] = None
    agreed_price: Optional[float] = None
    
    meeting_location: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_time: Optional[str] = None
    
    delivery_service: Optional[str] = None
    delivery_address: Optional[str] = None
    city: Optional[str] = None
    
    user_preference: Optional[Dict[str, Any]] = None


class SlotRequirements:
    REQUIREMENTS = {
        Intent.PRODUCT_INFO: [],
        Intent.STOCK_CHECK: [],
        Intent.DELIVERY_QUESTION: ["product_id"],
        Intent.WARRANTY_QUESTION: ["product_id"],
        Intent.BARGAINING: ["product_id", "offered_price"],
        Intent.MEETING_PLANNING: ["product_id", "meeting_location", "meeting_date", "meeting_time"],
        Intent.GENERAL_QUESTION: []
    }
    
    CLARIFICATION_QUESTIONS = {
        "product_id": "О каком товаре вы спрашиваете?",
        "offered_price": "Какую цену вы предлагаете?",
        "meeting_location": "Где вам удобно встретиться?",
        "meeting_date": "Какой день вам подходит?",
        "meeting_time": "В какое время вам удобно?",
        "delivery_service": "Какая служба доставки вас интересует?",
        "delivery_address": "Куда нужно доставить товар?"
    }


class SlotManager:
    def __init__(self):
        self.requirements = SlotRequirements()
    
    def check_slots_completeness(
        self,
        intent: Intent,
        slots: Slots
    ) -> tuple[bool, List[str]]:
        required_slots = self.requirements.REQUIREMENTS.get(intent, [])
        missing_slots = []
        
        for slot_name in required_slots:
            slot_value = getattr(slots, slot_name, None)
            
            # Special handling: product_name can substitute for product_id
            # System will resolve product_name to product_id via RAG search
            if slot_value is None:
                if slot_name == "product_id" and slots.product_name:
                    # product_name is available, so we can find product_id later
                    continue
                missing_slots.append(slot_name)
        
        is_complete = len(missing_slots) == 0
        return is_complete, missing_slots
    
    def generate_clarification_question(self, missing_slots: List[str]) -> str:
        if not missing_slots:
            return ""
        
        priority_order = [
            "product_id",
            "offered_price",
            "meeting_date",
            "meeting_time",
            "meeting_location"
        ]
        
        # Find first missing slot in priority order
        for slot in priority_order:
            if slot in missing_slots:
                return self.requirements.CLARIFICATION_QUESTIONS.get(
                    slot,
                    f"Пожалуйста, уточните {slot}"
                )
        
        # Fallback to first missing slot
        first_missing = missing_slots[0]
        return self.requirements.CLARIFICATION_QUESTIONS.get(
            first_missing,
            f"Пожалуйста, уточните {first_missing}"
        )
    
    def extract_slots_from_entities(
        self,
        entities: Dict[str, Any],
        current_slots: Slots
    ) -> Slots:
        updated_slots = current_slots.model_copy(deep=True)
        
        if "product_id" in entities and entities["product_id"]:
            updated_slots.product_id = entities["product_id"]
        
        if "product_name" in entities and entities["product_name"]:
            updated_slots.product_name = entities["product_name"]
        
        # Support both "color" and "product_color" for backwards compatibility
        if "product_color" in entities and entities["product_color"]:
            updated_slots.product_color = entities["product_color"]
        elif "color" in entities and entities["color"]:
            updated_slots.product_color = entities["color"]
        
        # Support both "memory" and "product_memory" for backwards compatibility
        if "product_memory" in entities and entities["product_memory"]:
            updated_slots.product_memory = entities["product_memory"]
        elif "memory" in entities and entities["memory"]:
            updated_slots.product_memory = entities["memory"]
        
        if "variant" in entities and entities["variant"]:
            updated_slots.product_variant = entities["variant"]
        
        if "price" in entities and entities["price"]:
            try:
                updated_slots.offered_price = float(entities["price"])
            except (ValueError, TypeError):
                pass
        
        if "location" in entities and entities["location"]:
            updated_slots.meeting_location = entities["location"]
        
        if "date" in entities and entities["date"]:
            updated_slots.meeting_date = entities["date"]
        
        if "time" in entities and entities["time"]:
            updated_slots.meeting_time = entities["time"]
        
        if "delivery_service" in entities and entities["delivery_service"]:
            updated_slots.delivery_service = entities["delivery_service"]
        
        if "city" in entities and entities["city"]:
            updated_slots.city = entities["city"]
        
        return updated_slots
    
    def should_ask_clarification(self, intent: Intent, slots: Slots) -> bool:
        is_complete, _ = self.check_slots_completeness(intent, slots)
        return not is_complete


_slot_manager: Optional[SlotManager] = None


def get_slot_manager() -> SlotManager:
    global _slot_manager
    if _slot_manager is None:
        _slot_manager = SlotManager()
    return _slot_manager
