from typing import List, Tuple, Optional, Dict, Any
import re


class ResponseValidator:
    def __init__(self, min_relevance_score: float = 0.5):
        self.min_relevance_score = min_relevance_score
    
    def validate_rag_response(
        self,
        response: str,
        rag_results: Optional[str],
        relevance_score: float
    ) -> Tuple[bool, List[str]]:
        issues = []
        
        if relevance_score < self.min_relevance_score:
            issues.append(
                f"Low relevance score: {relevance_score:.2f} "
                f"(minimum: {self.min_relevance_score})"
            )
        
        if not rag_results or len(rag_results.strip()) < 10:
            issues.append("No RAG results available to ground the response")
        
        hallucination_patterns = [
            r'я не уверен',
            r'возможно',
            r'вероятно',
            r'могу ошибаться',
            r'не могу гарантировать'
        ]
        
        response_lower = response.lower()
        for pattern in hallucination_patterns:
            if re.search(pattern, response_lower):
                issues.append(f"Response contains uncertainty marker: {pattern}")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def validate_price_mention(
        self,
        response: str,
        valid_prices: List[float]
    ) -> Tuple[bool, List[str]]:
        issues = []
        
        price_pattern = r'(\d{1,3}(?:[,\s]?\d{3})*(?:\.\d{2})?)\s*(?:руб|₽|рублей)'
        mentioned_prices = re.findall(price_pattern, response)
        
        for price_str in mentioned_prices:
            price_clean = price_str.replace(',', '').replace(' ', '')
            try:
                price = float(price_clean)
                
                is_valid_price = any(
                    abs(price - valid_price) < 100  # 100 rub tolerance
                    for valid_price in valid_prices
                )
                
                if not is_valid_price:
                    issues.append(
                        f"Mentioned price {price} руб. not in valid prices: {valid_prices}"
                    )
            except ValueError:
                issues.append(f"Could not parse price: {price_str}")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def validate_no_fabrication(
        self,
        response: str,
        allowed_info: str
    ) -> Tuple[bool, List[str]]:
        issues = []
        
        fabrication_indicators = [
            'точно знаю что',
            'гарантирую что',
            'обещаю',
            'клянусь',
            'на 100% уверен'
        ]
        
        response_lower = response.lower()
        for indicator in fabrication_indicators:
            if indicator in response_lower:
                issues.append(f"Response contains over-confident indicator: '{indicator}'")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def validate_response(
        self,
        response: str,
        context: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        all_issues = []
        
        rag_results = context.get('rag_results')
        relevance_score = context.get('relevance_score', 0.0)
        if rag_results is not None:
            _, issues = self.validate_rag_response(response, rag_results, relevance_score)
            all_issues.extend(issues)
        
        valid_prices = context.get('valid_prices', [])
        if valid_prices:
            _, issues = self.validate_price_mention(response, valid_prices)
            all_issues.extend(issues)
        
        allowed_info = context.get('allowed_info', '')
        if allowed_info:
            _, issues = self.validate_no_fabrication(response, allowed_info)
            all_issues.extend(issues)
        
        is_valid = len(all_issues) == 0
        return is_valid, all_issues


class ActionValidator:
    def validate_reservation(
        self,
        product_id: str,
        quantity: int,
        stock_available: int
    ) -> Tuple[bool, str]:
        if quantity <= 0:
            return False, "Количество должно быть больше 0"
        
        if quantity > stock_available:
            return False, f"Недостаточно товара (доступно: {stock_available})"
        
        return True, "OK"
    
    def validate_meeting_time(
        self,
        date_str: str,
        time_str: str
    ) -> Tuple[bool, str]:
        if not date_str or not time_str:
            return False, "Не указана дата или время"
        
        return True, "OK"
    
    def validate_price_offer(
        self,
        offered_price: float,
        min_price: float,
        max_price: float
    ) -> Tuple[bool, str]:
        if offered_price < 0:
            return False, "Цена не может быть отрицательной"
        
        if offered_price < min_price * 0.5:
            return False, f"Цена слишком низкая (меньше половины от {min_price})"
        
        if offered_price > max_price * 2:
            return False, f"Цена подозрительно высокая (больше в 2 раза от {max_price})"
        
        return True, "OK"


_response_validator: Optional[ResponseValidator] = None
_action_validator: Optional[ActionValidator] = None


def get_response_validator() -> ResponseValidator:
    global _response_validator
    if _response_validator is None:
        _response_validator = ResponseValidator()
    return _response_validator


def get_action_validator() -> ActionValidator:
    global _action_validator
    if _action_validator is None:
        _action_validator = ActionValidator()
    return _action_validator
