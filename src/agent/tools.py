from typing import Optional, Dict, Any
from product.repository import get_product_repository
from product.delivery_validator import get_delivery_validator
from bargaining.negotiation_engine import get_negotiation_engine
from rag.hybrid_retriever import get_hybrid_retriever


class AgentTools:
    def __init__(self):
        self.product_repo = get_product_repository()
        self.delivery_validator = get_delivery_validator()
        self.negotiation_engine = get_negotiation_engine()
        self.retriever = get_hybrid_retriever()
    
    def search_product_info(self, query: str) -> Dict[str, Any]:
        results = self.retriever.retrieve(query)
        formatted = self.retriever.retrieve_formatted(query)
        
        return {
            "results": results,
            "formatted_text": formatted,
            "count": len(results)
        }
    
    def get_product_by_id(self, product_id: str) -> Optional[Dict]:
        product = self.product_repo.get_product(product_id)
        if not product:
            return None
        
        return product.model_dump()
    
    def check_stock(self, product_id: str) -> Dict[str, Any]:
        status = self.product_repo.check_stock(product_id)
        if not status:
            return {
                "found": False,
                "message": "Товар не найден"
            }
        
        return {
            "found": True,
            "available": status.available,
            "quantity": status.quantity,
            "can_reserve": status.can_reserve
        }
    
    def check_delivery(
        self,
        product_id: str,
        city: Optional[str] = None,
        delivery_service: Optional[str] = None,
        is_professional_seller: bool = False
    ) -> Dict[str, Any]:
        product = self.product_repo.get_product(product_id)
        if not product:
            return {
                "found": False,
                "message": "Товар не найден"
            }
        
        # Если пользователь спросил про конкретную службу - проверяем именно её
        if delivery_service:
            recommendation = self.delivery_validator.check_specific_service(
                product,
                delivery_service,
                is_professional_seller=is_professional_seller,
                city=city
            )
        else:
            # Иначе даём общую рекомендацию со всеми подходящими службами
            recommendation = self.delivery_validator.get_delivery_recommendation(
                product,
                is_professional_seller=is_professional_seller,
                city=city
            )
        
        suitable_services = self.delivery_validator.find_suitable_services(
            product,
            is_professional_seller=is_professional_seller,
            city=city
        )
        
        return {
            "found": True,
            "recommendation": recommendation,
            "suitable_services": suitable_services,
            "product_weight": product.weight,
            "product_dimensions": product.dimensions.model_dump(),
            "product_price": product.price
        }
    
    def evaluate_bargaining(
        self,
        product_id: str,
        offered_price: float,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        product = self.product_repo.get_product(product_id)
        if not product:
            return {
                "found": False,
                "message": "Товар не найден"
            }
        
        decision, counter_price, explanation = self.negotiation_engine.evaluate_offer(
            product, offered_price
        )
        
        return {
            "found": True,
            "decision": decision,
            "counter_price": counter_price,
            "explanation": explanation,
            "current_price": product.price,
            "min_price": product.min_price
        }
    
    def get_meeting_locations(self, product_id: str) -> Dict[str, Any]:
        product = self.product_repo.get_product(product_id)
        if not product:
            return {
                "found": False,
                "message": "Товар не найден"
            }
        
        return {
            "found": True,
            "locations": product.meeting_locations,
            "product_title": product.title,
            "price": product.price
        }
    
    def reserve_product(self, product_id: str, quantity: int = 1) -> Dict[str, Any]:
        success = self.product_repo.reserve_product(product_id, quantity)
        
        if success:
            return {
                "success": True,
                "message": f"Товар зарезервирован (количество: {quantity})"
            }
        else:
            return {
                "success": False,
                "message": "Не удалось зарезервировать товар (недостаточно на складе)"
            }


_tools: Optional[AgentTools] = None


def get_agent_tools() -> AgentTools:
    global _tools
    if _tools is None:
        _tools = AgentTools()
    return _tools
