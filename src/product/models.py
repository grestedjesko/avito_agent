"""Product data models."""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ProductDimensions(BaseModel):
    """Product dimensions in cm."""
    length: float = Field(description="Length in cm")
    width: float = Field(description="Width in cm")
    height: float = Field(description="Height in cm")
    
    @property
    def sum_dimensions(self) -> float:
        """Calculate sum of all dimensions."""
        return self.length + self.width + self.height


class Product(BaseModel):
    """Product model."""
    id: str = Field(description="Product ID")
    title: str = Field(description="Product title")
    category: str = Field(description="Product category")
    price: float = Field(description="Current price in RUB")
    min_price: float = Field(description="Minimum acceptable price in RUB")
    stock: int = Field(description="Available quantity", ge=0)
    weight: float = Field(description="Weight in kg")
    dimensions: ProductDimensions = Field(description="Product dimensions")
    description: str = Field(description="Product description")
    characteristics: Dict[str, str] = Field(
        default_factory=dict,
        description="Product characteristics"
    )
    warranty: str = Field(description="Warranty information")
    quality_notes: str = Field(description="Quality and condition notes")
    bargaining_allowed: bool = Field(
        default=True,
        description="Whether bargaining is allowed"
    )
    max_discount_percent: float = Field(
        default=0.0,
        description="Maximum discount percentage",
        ge=0,
        le=100
    )
    meeting_locations: List[str] = Field(
        default_factory=list,
        description="Available meeting locations"
    )
    
    def is_available(self) -> bool:
        """Check if product is in stock."""
        return self.stock > 0
    
    def can_bargain(self) -> bool:
        """Check if bargaining is allowed."""
        return self.bargaining_allowed and self.max_discount_percent > 0
    
    def calculate_min_acceptable_price(self) -> float:
        """Calculate minimum acceptable price based on discount."""
        discount_amount = self.price * (self.max_discount_percent / 100)
        calculated_min = self.price - discount_amount
        return max(calculated_min, self.min_price)
    
    def is_price_acceptable(self, offered_price: float) -> bool:
        """Check if offered price is acceptable."""
        min_acceptable = self.calculate_min_acceptable_price()
        return offered_price >= min_acceptable
    
    def calculate_counter_offer(
        self,
        offered_price: float,
        strategy: str = "meet_halfway"
    ) -> Optional[float]:
        """Calculate counter offer price."""
        if self.is_price_acceptable(offered_price):
            return None  # Accept the offer
        
        if strategy == "meet_halfway":
            min_acceptable = self.calculate_min_acceptable_price()
            counter = (offered_price + self.price) / 2
            return max(counter, min_acceptable)
        
        return self.calculate_min_acceptable_price()
    
    def reserve(self, quantity: int = 1) -> bool:
        """Reserve product quantity."""
        if self.stock >= quantity:
            self.stock -= quantity
            return True
        return False


class StockStatus(BaseModel):
    """Stock status response."""
    product_id: str
    available: bool
    quantity: int
    can_reserve: bool
