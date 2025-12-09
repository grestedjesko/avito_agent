import json
from typing import Dict, List, Optional
from pathlib import Path
from product.models import Product, StockStatus


class ProductRepository:
    def __init__(self, data_file: str = "data/products.json"):
        self.data_file = Path(data_file)
        self.products: Dict[str, Product] = {}
        self._load_products()
    
    def _load_products(self) -> None:
        if not self.data_file.exists():
            return
        
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for item in data:
                product = Product(**item)
                self.products[product.id] = product
        except Exception as e:
            pass
    
    def get_product(self, product_id: str) -> Optional[Product]:
        return self.products.get(product_id)
    
    def get_product_by_title(self, title: str) -> Optional[Product]:
        title_lower = title.lower()
        for product in self.products.values():
            if title_lower in product.title.lower():
                return product
        return None
    
    def list_products(
        self,
        category: Optional[str] = None,
        available_only: bool = False
    ) -> List[Product]:
        products = list(self.products.values())
        
        if category:
            products = [p for p in products if p.category.lower() == category.lower()]
        
        if available_only:
            products = [p for p in products if p.is_available()]
        
        return products
    
    def check_stock(self, product_id: str) -> Optional[StockStatus]:
        product = self.get_product(product_id)
        if not product:
            return None
        
        return StockStatus(
            product_id=product.id,
            available=product.is_available(),
            quantity=product.stock,
            can_reserve=product.is_available()
        )
    
    def reserve_product(self, product_id: str, quantity: int = 1) -> bool:
        product = self.get_product(product_id)
        if not product:
            return False
        
        return product.reserve(quantity)
    
    def search_products(self, query: str) -> List[Product]:
        query_lower = query.lower()
        results = []
        
        for product in self.products.values():
            if (query_lower in product.title.lower() or
                query_lower in product.description.lower() or
                query_lower in product.category.lower()):
                results.append(product)
        
        return results
    
    def get_all_products_text(self) -> str:
        text_parts = []
        
        for product in self.products.values():
            text = f"""
Товар ID: {product.id}
Название: {product.title}
Категория: {product.category}
Цена: {product.price} руб.
Наличие: {"В наличии" if product.is_available() else "Нет в наличии"} ({product.stock} шт.)
Вес: {product.weight} кг
Размеры: {product.dimensions.length}x{product.dimensions.width}x{product.dimensions.height} см

Описание: {product.description}

Характеристики:
{chr(10).join(f"- {k}: {v}" for k, v in product.characteristics.items())}

Гарантия: {product.warranty}
Состояние: {product.quality_notes}

Торг: {"Возможен" if product.bargaining_allowed else "Не предусмотрен"}
{f"Максимальная скидка: {product.max_discount_percent}%" if product.max_discount_percent > 0 else ""}

Места встречи: {", ".join(product.meeting_locations)}

---
"""
            text_parts.append(text)
        
        return "\n".join(text_parts)


_repository: Optional[ProductRepository] = None


def get_product_repository() -> ProductRepository:
    global _repository
    if _repository is None:
        _repository = ProductRepository()
    return _repository
