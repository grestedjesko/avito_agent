from typing import Annotated, Dict, List, Optional, Any
from typing_extensions import TypedDict
from langgraph.graph import add_messages
from dialogue.slot_manager import Slots, Intent


class AgentState(TypedDict):
    messages: Annotated[List[Dict[str, str]], add_messages]
    
    user_message: str
    
    session_id: str
    
    intent: Optional[str]
    intent_confidence: float
    entities: Dict[str, Any]
    
    slots: Dict[str, Any] 
    slots_complete: bool
    missing_slots: List[str]
    
    product_id: Optional[str]
    product_context: Optional[str]
    
    rag_results: Optional[str]
    relevance_score: float
    
    action_result: Optional[str]
    action_type: Optional[str]
    
    response: str
    needs_clarification: bool
    clarification_question: Optional[str]
    
    validation_passed: bool
    validation_issues: List[str]
    
    # Reflection & Confidence fields
    reflection_result: Optional[Dict[str, Any]]
    response_quality_score: float
    needs_regeneration: bool
    regeneration_count: int
    confidence_level: str  # 'low', 'medium', 'high'
    routing_decision: Optional[str]
    
    # Planning fields
    execution_plan: Optional[Dict[str, Any]]
    current_step: int
    plan_complexity: str  # 'simple', 'medium', 'complex'
    completed_steps: List[str]
    next_planned_action: Optional[str]
    
    # LLM Routing fields
    routing_reasoning: Optional[str]
    alternative_routes: List[str]
    routing_confidence: float
    
    step_count: int
    error: Optional[str]
