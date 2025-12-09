import yaml
import random
from typing import Dict, Optional, Tuple
from pathlib import Path
from product.models import Product


class NegotiationEngine:
    def __init__(self, rules_file: str = "data/bargaining_rules.yaml"):
        self.rules_file = Path(rules_file)
        self.rules: Dict = {}
        self._load_rules()
    
    def _load_rules(self) -> None:
        if not self.rules_file.exists():
            return
        
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                self.rules = yaml.safe_load(f)
        except Exception as e:
            pass
    
    def evaluate_offer(
        self,
        product: Product,
        offered_price: float
    ) -> Tuple[str, Optional[float], str]:
        if not product.can_bargain():
            return (
                'decline',
                None,
                f"Извините, торг не предусмотрен. Цена фиксированная: {product.price} руб."
            )
        
        if offered_price >= product.price:
            return (
                'accept',
                offered_price,
                f"Отлично! Договорились на {offered_price} руб."
            )
        
        discount_amount = product.price - offered_price
        discount_percent = (discount_amount / product.price) * 100
        
        max_discount = product.max_discount_percent
        
        if discount_percent <= max_discount:
            phrases = self.rules.get('phrases', {}).get('accept', [
                f"Хорошо, согласен на {offered_price} руб."
            ])
            explanation = random.choice(phrases).format(price=offered_price)
            return ('accept', offered_price, explanation)
        
        elif discount_percent <= max_discount * 1.5:
            counter_price = product.calculate_counter_offer(offered_price)
            phrases = self.rules.get('phrases', {}).get('counter_offer', [
                f"Давайте встретимся посередине? Могу предложить {counter_price} руб."
            ])
            explanation = random.choice(phrases).format(price=counter_price)
            return ('counter_offer', counter_price, explanation)
        
        else:
            min_price = product.calculate_min_acceptable_price()
            phrases = self.rules.get('phrases', {}).get('decline_polite', [
                f"Спасибо за предложение, но это слишком низкая цена. Минимум {min_price} руб."
            ])
            explanation = random.choice(phrases)
            
            value_reasons = self._get_value_reasons(product)
            if value_reasons:
                explain_phrases = self.rules.get('phrases', {}).get('explain_value', [])
                if explain_phrases:
                    value_explanation = random.choice(explain_phrases).format(
                        reason=value_reasons
                    )
                    explanation += f" {value_explanation}"
            
            return ('decline', min_price, explanation)
    
    def _get_value_reasons(self, product: Product) -> str:
        reasons = []
        
        if 'месяц' in product.warranty.lower() or 'год' in product.warranty.lower():
            if 'официальн' in product.warranty.lower():
                reasons.append("официальная гарантия")
        
        if any(word in product.quality_notes.lower() for word in ['новый', 'запечатан', 'идеальн']):
            reasons.append("идеальное состояние")
        
        if 'новый' in product.quality_notes.lower():
            reasons.append("товар новый")
        
        if product.price > 100000:
            reasons.append("дорогой товар с небольшой маржой")
        
        if reasons:
            return ", ".join(reasons)
        
        return "товар в хорошем состоянии"
    
    def generate_negotiation_response(
        self,
        product: Product,
        offered_price: float,
        context: Optional[Dict] = None
    ) -> str:
        decision, counter_price, explanation = self.evaluate_offer(product, offered_price)
        
        if context:
            if context.get('pickup_today'):
                special_discount = self.rules.get('special_conditions', {}).get(
                    'quick_deal', {}
                ).get('additional_discount', 0)
                
                if special_discount > 0 and decision == 'counter_offer' and counter_price:
                    bonus_discount = product.price * (special_discount / 100)
                    counter_price = max(counter_price - bonus_discount, product.min_price)
                    explanation += f" Если заберете сегодня, могу дать дополнительную скидку."
        
        return explanation


_engine: Optional[NegotiationEngine] = None


def get_negotiation_engine() -> NegotiationEngine:
    global _engine
    if _engine is None:
        _engine = NegotiationEngine()
    return _engine
