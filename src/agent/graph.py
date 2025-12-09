from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import (
    classify_intent_node,
    check_slots_node,
    rag_search_node,
    stock_check_node,
    delivery_check_node,
    bargaining_node,
    meeting_planning_node,
    generate_response_node,
    reflection_node,
    planning_node,
    intelligent_route_node,
    route_intent,
    confidence_aware_routing,
    route_after_reflection,
    route_from_intelligent_router,
    route_by_complexity,
    route_after_action
)


def create_agent_graph() -> StateGraph:
    """
    Создает граф агента с Planning и LLM Routing
    
    Архитектура:
    1. classify_intent -> определение намерения
    2. check_slots -> проверка полноты информации  
    3. [conditional] -> route_by_complexity
       - Простые запросы -> intelligent_router -> direct action
       - Сложные запросы -> planning -> planned execution
    4. action nodes -> execute specific actions
    5. generate_response -> создание ответа
    6. reflection -> проверка качества
    7. [conditional] -> regenerate or END
    """
    workflow = StateGraph(AgentState)
    
    # Добавляем все узлы
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("check_slots", check_slots_node)
    workflow.add_node("planning", planning_node)
    workflow.add_node("intelligent_router", intelligent_route_node)
    workflow.add_node("rag_search", rag_search_node)
    workflow.add_node("stock_check", stock_check_node)
    workflow.add_node("delivery_check", delivery_check_node)
    workflow.add_node("bargaining", bargaining_node)
    workflow.add_node("meeting_planning", meeting_planning_node)
    workflow.add_node("generate_response", generate_response_node)
    workflow.add_node("reflection", reflection_node)
    
    # Точка входа
    workflow.set_entry_point("classify_intent")
    
    # Шаг 1: Классификация намерения
    workflow.add_edge("classify_intent", "check_slots")
    
    # Шаг 2: После проверки слотов -> оценка сложности
    workflow.add_conditional_edges(
        "check_slots",
        route_by_complexity,
        {
            "planning": "planning",  # Сложные запросы -> планирование
            "intelligent_router": "intelligent_router"  # Простые -> прямая маршрутизация
        }
    )
    
    # Шаг 3a: После планирования -> intelligent router (который использует план)
    workflow.add_edge("planning", "intelligent_router")
    
    # Шаг 3b: Intelligent router определяет следующий узел
    workflow.add_conditional_edges(
        "intelligent_router",
        route_from_intelligent_router,
        {
            "rag_search": "rag_search",
            "stock_check": "stock_check",
            "delivery_check": "delivery_check",
            "bargaining": "bargaining",
            "meeting_planning": "meeting_planning",
            "generate_response": "generate_response"
        }
    )
    
    # Шаг 4: Все action узлы проверяют, нужно ли продолжить план
    # Если план многошаговый -> возвращаемся в intelligent_router
    # Если план завершен -> идем в generate_response
    for action_node in ["rag_search", "stock_check", "delivery_check", "bargaining", "meeting_planning"]:
        workflow.add_conditional_edges(
            action_node,
            route_after_action,
            {
                "continue_plan": "intelligent_router",  # Продолжаем выполнение плана
                "generate_response": "generate_response"  # План завершен
            }
        )
    
    # Шаг 5: После генерации ответа -> reflection для проверки качества
    workflow.add_edge("generate_response", "reflection")
    
    # Шаг 6: Conditional routing после reflection
    workflow.add_conditional_edges(
        "reflection",
        route_after_reflection,
        {
            "regenerate": "generate_response",  # Если нужна регенерация -> обратно
            "end": END  # Если всё ок -> завершение
        }
    )
    
    app = workflow.compile()
    
    return app


agent_graph = create_agent_graph()


def get_agent_graph():
    return agent_graph
