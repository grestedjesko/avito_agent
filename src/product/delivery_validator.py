import yaml
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from product.models import Product


class DeliveryService(Dict):
    pass


class DeliveryValidator:
    def __init__(self, rules_file: str = "data/delivery_rules.yaml"):
        self.rules_file = Path(rules_file)
        self.services: Dict[str, DeliveryService] = {}
        self._load_rules()
    
    def _load_rules(self) -> None:
        if not self.rules_file.exists():
            return
        
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if 'avito_general' in data:
                del data['avito_general']
            
            self.services = data
        except Exception as e:
            pass
    
    def validate_product(
        self,
        product: Product,
        service_name: str,
        is_professional_seller: bool = False,
        city: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        service = self.services.get(service_name)
        if not service:
            return False, [f"Служба доставки '{service_name}' не найдена"]
        
        issues = []
        dims = product.dimensions
        
        min_price = service.get('min_price', 0)
        max_price = service.get('max_price', float('inf'))
        
        if is_professional_seller:
            max_price_professional = service.get('max_price_professional')
            if max_price_professional:
                max_price = max_price_professional
        
        if service_name == 'post5':
            limited_categories = service.get('limited_categories', [])
            if product.category in limited_categories:
                max_price_limited = service.get('max_price_limited', max_price)
                max_price = min(max_price, max_price_limited)
        
        if product.price < min_price:
            issues.append(
                f"Цена товара ({product.price} руб.) ниже минимальной "
                f"для {service.get('name', service_name)} ({min_price} руб.)"
            )
        
        if product.price > max_price:
            issues.append(
                f"Цена товара ({product.price} руб.) превышает максимальную "
                f"для {service.get('name', service_name)} ({max_price} руб.)"
            )
        
        max_weight = service.get('max_weight', float('inf'))
        
        if service_name == 'yandex_delivery' and city:
            extended_cities = service.get('extended_cities', [])
            if city in extended_cities:
                max_weight_extended = service.get('max_weight_extended')
                if max_weight_extended:
                    max_weight = max_weight_extended
        
        if product.weight > max_weight:
            issues.append(
                f"Вес товара ({product.weight} кг) превышает максимальный "
                f"для {service.get('name', service_name)} ({max_weight} кг)"
            )
        
        if service_name == 'yandex_delivery':
            box_sizes = service.get('box_sizes', [])
            fits_in_box = False
            
            if city and city in service.get('extended_cities', []):
                if (dims.length <= 80 and dims.width <= 60 and dims.height <= 60):
                    fits_in_box = True
            else:
                for box in box_sizes:
                    if (dims.length <= box[0] and dims.width <= box[1] and dims.height <= box[2]):
                        fits_in_box = True
                        break
            
            if not fits_in_box:
                issues.append(
                    f"Габариты товара ({dims.length}×{dims.width}×{dims.height} см) "
                    f"не помещаются в стандартные коробки Яндекс.Доставки"
                )
        
        elif service_name == 'cdek':
            max_length = service.get('max_length', float('inf'))
            longest_side = max(dims.length, dims.width, dims.height)
            
            if longest_side > max_length:
                issues.append(
                    f"Самая длинная сторона ({longest_side} см) превышает "
                    f"максимальную для СДЭК ({max_length} см)"
                )
            
            volume = dims.length * dims.width * dims.height
            max_volume = service.get('max_volume_product', float('inf'))
            
            if volume > max_volume:
                large_item_support = service.get('large_item_support', False)
                if large_item_support:
                    large_max_weight = service.get('large_item_weight_max', float('inf'))
                    large_max_length = service.get('large_item_length_max', float('inf'))
                    large_max_volume = service.get('large_item_volume_max', float('inf'))
                    
                    if (product.weight <= large_max_weight and 
                        longest_side <= large_max_length and 
                        volume <= large_max_volume):
                        pass
                    else:
                        issues.append(
                            f"Произведение габаритов ({volume:.0f} см³) превышает "
                            f"максимальное для СДЭК ({max_volume:.0f} см³)"
                        )
                else:
                    issues.append(
                        f"Произведение габаритов ({volume:.0f} см³) превышает "
                        f"максимальное для СДЭК ({max_volume:.0f} см³)"
                    )
        
        else:
            max_length = service.get('max_length', float('inf'))
            max_width = service.get('max_width', float('inf'))
            max_height = service.get('max_height', float('inf'))
            
            longest_side = max(dims.length, dims.width, dims.height)
            if longest_side > max_length:
                issues.append(
                    f"Самая длинная сторона ({longest_side} см) превышает "
                    f"максимальную ({max_length} см)"
                )
            
            if dims.width > max_width:
                issues.append(
                    f"Ширина ({dims.width} см) превышает максимальную ({max_width} см)"
                )
            
            if dims.height > max_height:
                issues.append(
                    f"Высота ({dims.height} см) превышает максимальную ({max_height} см)"
                )
            
            # Check sum of dimensions
            max_sum = service.get('max_sum_dimensions', float('inf'))
            if max_sum != float('inf') and dims.sum_dimensions > max_sum:
                issues.append(
                    f"Сумма габаритов ({dims.sum_dimensions:.1f} см) превышает "
                    f"максимальную ({max_sum} см)"
                )
        
        prohibited = service.get('prohibited_categories', [])
        if product.category in prohibited:
            issues.append(
                f"Категория '{product.category}' запрещена для отправки "
                f"через {service.get('name', service_name)}"
            )
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def find_suitable_services(
        self,
        product: Product,
        is_professional_seller: bool = False,
        city: Optional[str] = None
    ) -> List[Dict[str, any]]:
        suitable = []
        
        for service_name, service_config in self.services.items():
            is_valid, issues = self.validate_product(
                product,
                service_name,
                is_professional_seller=is_professional_seller,
                city=city
            )
            
            if is_valid:
                service_info = {
                    'service_id': service_name,
                    'name': service_config.get('name', service_name),
                    'insurance_available': service_config.get('insurance_available', False),
                    'city_only': service_config.get('city_only', False),
                    'notes': service_config.get('notes', '')
                }
                
                if service_config.get('large_item_support'):
                    service_info['large_item_support'] = True
                
                suitable.append(service_info)
        
        return suitable
    
    def check_specific_service(
        self,
        product: Product,
        service_name: str,
        is_professional_seller: bool = False,
        city: Optional[str] = None
    ) -> str:
        """Проверка конкретной службы доставки по запросу пользователя."""
        service = self.services.get(service_name)
        if not service:
            # Попробуем найти службу по имени (нечувствительно к регистру)
            service_name_lower = service_name.lower()
            for key, srv in self.services.items():
                if service_name_lower in srv.get('name', '').lower() or service_name_lower in key.lower():
                    service_name = key
                    service = srv
                    break
        
        if not service:
            return f"Не нашел службу доставки '{service_name}'. Могу проверить доступные варианты?"
        
        is_valid, issues = self.validate_product(
            product,
            service_name,
            is_professional_seller=is_professional_seller,
            city=city
        )
        
        service_display_name = service.get('name', service_name)

        if is_valid:
            return (
                f"Да, {service_display_name} подходит для этого товара! "
                f"Оформить доставку можно через Авито — в объявлении есть кнопка «Купить с доставкой»."
            )
        else:
            # Формируем понятное объяснение
            main_issue = issues[0] if issues else "не подходит по параметрам"

            # Предлагаем альтернативы
            suitable = self.find_suitable_services(product, is_professional_seller, city)
            if suitable:
                alternatives = ", ".join([s['name'] for s in suitable[:3]])
                return (
                    f"К сожалению, {service_display_name} не подходит: {main_issue}. "
                    f"Но могу предложить: {alternatives}. "
                    f"Оформить можно через Авито — в объявлении есть кнопка «Купить с доставкой»."
                )
            else:
                return (
                    f"К сожалению, {service_display_name} не подходит: {main_issue}. "
                    f"Рекомендую самовывоз или курьерскую доставку по договоренности."
                )
    
    def get_delivery_recommendation(
        self,
        product: Product,
        is_professional_seller: bool = False,
        city: Optional[str] = None
    ) -> str:
        suitable_services = self.find_suitable_services(
            product,
            is_professional_seller=is_professional_seller,
            city=city
        )
        
        if not suitable_services:
            reasons = []
            for service_name in self.services.keys():
                is_valid, issues = self.validate_product(
                    product,
                    service_name,
                    is_professional_seller=is_professional_seller,
                    city=city
                )
                if issues:
                    service_display = self.services[service_name].get('name', service_name)
                    reasons.append(f"{service_display}: {', '.join(issues[:2])}")
            
            return (
                "К сожалению, товар не подходит для стандартной доставки через Avito:\n" +
                "\n".join(f"- {r}" for r in reasons[:3]) +
                "\n\nРекомендую самовывоз или курьерскую доставку по договоренности."
            )
        
        if not city:
            suitable_services = [s for s in suitable_services if not s.get('city_only', False)]
        
        if not suitable_services:
            return (
                "Для этого товара доступна только курьерская доставка внутри города. "
                "Укажите город для проверки доступности."
            )
        
        service_names = [s['name'] for s in suitable_services]
        recommendation = (
            f"Для этого товара подходят: {', '.join(service_names)}. "
            f"Оформить доставку можно через Авито — в объявлении есть кнопка «Купить с доставкой»."
        )
        
        return recommendation


_validator: Optional[DeliveryValidator] = None


def get_delivery_validator() -> DeliveryValidator:
    global _validator
    if _validator is None:
        _validator = DeliveryValidator()
    return _validator
