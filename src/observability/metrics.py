import time
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import logging

from src.observability.langfuse_config import get_langfuse_client

logger = logging.getLogger(__name__)


@dataclass
class NodeMetrics:
    node_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def finish(self, success: bool = True, error: Optional[str] = None) -> None:
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.success = success
        self.error = error


@dataclass
class LLMMetrics:
    model: str
    operation: str  # classify_intent, generate_response, etc.
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    success: bool = True
    error: Optional[str] = None
    
    def finish(
        self,
        success: bool = True,
        error: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> None:
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.success = success
        self.error = error
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.cost_usd = self._estimate_cost()
    
    def _estimate_cost(self) -> float: 
        input_cost = (self.input_tokens / 1_000_000) * 0.14
        output_cost = (self.output_tokens / 1_000_000) * 0.28
        return input_cost + output_cost


@dataclass
class ConversationMetrics:
    session_id: str
    start_time: float
    end_time: Optional[float] = None
    total_duration_ms: Optional[float] = None
    total_messages: int = 0
    total_nodes_executed: int = 0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    intents: List[str] = field(default_factory=list)
    node_metrics: List[NodeMetrics] = field(default_factory=list)
    llm_metrics: List[LLMMetrics] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    
    def add_node_metric(self, metric: NodeMetrics) -> None:
        self.node_metrics.append(metric)
        self.total_nodes_executed += 1
    
    def add_llm_metric(self, metric: LLMMetrics) -> None:
        self.llm_metrics.append(metric)
        self.total_llm_calls += 1
        self.total_tokens += metric.total_tokens
        self.total_cost_usd += metric.cost_usd
    
    def add_intent(self, intent: str) -> None:
        self.intents.append(intent)
    
    def add_score(self, name: str, value: float) -> None:
        self.scores[name] = value
    
    def finish(self) -> None:
        self.end_time = time.time()
        self.total_duration_ms = (self.end_time - self.start_time) * 1000
    
    def get_summary(self) -> Dict[str, Any]:
        avg_node_duration = 0.0
        if self.node_metrics:
            total_duration = sum(
                m.duration_ms for m in self.node_metrics if m.duration_ms
            )
            avg_node_duration = total_duration / len(self.node_metrics)
        
        avg_llm_duration = 0.0
        if self.llm_metrics:
            total_duration = sum(
                m.duration_ms for m in self.llm_metrics if m.duration_ms
            )
            avg_llm_duration = total_duration / len(self.llm_metrics)
        
        return {
            'session_id': self.session_id,
            'total_duration_ms': self.total_duration_ms,
            'total_messages': self.total_messages,
            'total_nodes': self.total_nodes_executed,
            'total_llm_calls': self.total_llm_calls,
            'total_tokens': self.total_tokens,
            'total_cost_usd': round(self.total_cost_usd, 4),
            'avg_node_duration_ms': round(avg_node_duration, 2),
            'avg_llm_duration_ms': round(avg_llm_duration, 2),
            'intents': self.intents,
            'scores': self.scores
        }


class MetricsCollector:
    def __init__(self):
        self.conversations: Dict[str, ConversationMetrics] = {}
        self.global_metrics = {
            'total_conversations': 0,
            'total_messages': 0,
            'total_tokens': 0,
            'total_cost_usd': 0.0,
            'intent_distribution': defaultdict(int),
            'node_execution_count': defaultdict(int),
            'error_count': defaultdict(int)
        }
        self.langfuse = get_langfuse_client()
    
    def start_conversation(self, session_id: str) -> ConversationMetrics:
        conv_metrics = ConversationMetrics(
            session_id=session_id,
            start_time=time.time()
        )
        self.conversations[session_id] = conv_metrics
        self.global_metrics['total_conversations'] += 1
        
        logger.info(f"Started metrics tracking for session: {session_id}")
        return conv_metrics
    
    def get_conversation(self, session_id: str) -> Optional[ConversationMetrics]:
        return self.conversations.get(session_id)
    
    def start_node_execution(
        self,
        session_id: str,
        node_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> NodeMetrics:
        metric = NodeMetrics(
            node_name=node_name,
            start_time=time.time(),
            metadata=metadata or {}
        )
        
        self.global_metrics['node_execution_count'][node_name] += 1
        
        logger.debug(f"Started node execution: {node_name}", extra={'session_id': session_id})
        return metric
    
    def finish_node_execution(
        self,
        session_id: str,
        metric: NodeMetrics,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        metric.finish(success=success, error=error)
        
        conv = self.conversations.get(session_id)
        if conv:
            conv.add_node_metric(metric)
        
        if not success and error:
            self.global_metrics['error_count'][metric.node_name] += 1
        
        logger.debug(
            f"Finished node execution: {metric.node_name}",
            extra={
                'session_id': session_id,
                'duration_ms': metric.duration_ms,
                'success': success
            }
        )
        
        # Report to Langfuse
        self._report_node_to_langfuse(session_id, metric)
    
    def start_llm_call(
        self,
        session_id: str,
        model: str,
        operation: str
    ) -> LLMMetrics:
        metric = LLMMetrics(
            model=model,
            operation=operation,
            start_time=time.time()
        )
        
        logger.debug(
            f"Started LLM call: {operation}",
            extra={'session_id': session_id, 'model': model}
        )
        return metric
    
    def finish_llm_call(
        self,
        session_id: str,
        metric: LLMMetrics,
        success: bool = True,
        error: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> None:
        metric.finish(
            success=success,
            error=error,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )
        
        conv = self.conversations.get(session_id)
        if conv:
            conv.add_llm_metric(metric)
        
        self.global_metrics['total_tokens'] += metric.total_tokens
        self.global_metrics['total_cost_usd'] += metric.cost_usd
        
        logger.debug(
            f"Finished LLM call: {metric.operation}",
            extra={
                'session_id': session_id,
                'duration_ms': metric.duration_ms,
                'tokens': metric.total_tokens,
                'cost_usd': metric.cost_usd
            }
        )
        
        self._report_llm_to_langfuse(session_id, metric)
    
    def record_intent(self, session_id: str, intent: str) -> None:
        conv = self.conversations.get(session_id)
        if conv:
            conv.add_intent(intent)
        
        self.global_metrics['intent_distribution'][intent] += 1
        
        logger.debug(f"Recorded intent: {intent}", extra={'session_id': session_id})
    
    def record_score(
        self,
        session_id: str,
        name: str,
        value: float,
        comment: Optional[str] = None
    ) -> None:
        conv = self.conversations.get(session_id)
        if conv:
            conv.add_score(name, value)
        
        logger.info(
            f"Recorded score: {name}={value}",
            extra={'session_id': session_id}
        )
        
        if self.langfuse:
            try:
                self.langfuse.score(
                    name=name,
                    value=value,
                    comment=comment
                )
            except Exception as e:
                logger.error(f"Failed to report score to Langfuse: {e}")
    
    def finish_conversation(self, session_id: str) -> Optional[Dict[str, Any]]:
        conv = self.conversations.get(session_id)
        if not conv:
            return None
        
        conv.finish()
        summary = conv.get_summary()
        
        self.global_metrics['total_messages'] += conv.total_messages
        
        logger.info(
            f"Finished conversation: {session_id}",
            extra={
                'duration_ms': conv.total_duration_ms,
                'messages': conv.total_messages,
                'cost_usd': conv.total_cost_usd
            }
        )
        
        return summary
    
    def _report_node_to_langfuse(
        self,
        session_id: str,
        metric: NodeMetrics
    ) -> None:
        if not self.langfuse:
            return
        
        try:
            trace = self.langfuse.trace(
                name=f"node_{metric.node_name}",
                session_id=session_id,
                metadata={
                    'node': metric.node_name,
                    'duration_ms': metric.duration_ms,
                    'success': metric.success,
                    **metric.metadata
                }
            )
            
            if not metric.success and metric.error:
                trace.event(
                    name="node_error",
                    level="ERROR",
                    metadata={'error': metric.error}
                )
        
        except Exception as e:
            logger.error(f"Failed to report node to Langfuse: {e}")
    
    def _report_llm_to_langfuse(
        self,
        session_id: str,
        metric: LLMMetrics
    ) -> None:
        if not self.langfuse:
            return
        
        try:
            trace = self.langfuse.trace(
                name=f"llm_{metric.operation}",
                session_id=session_id,
                metadata={
                    'model': metric.model,
                    'operation': metric.operation,
                    'duration_ms': metric.duration_ms,
                    'input_tokens': metric.input_tokens,
                    'output_tokens': metric.output_tokens,
                    'total_tokens': metric.total_tokens,
                    'cost_usd': metric.cost_usd,
                    'success': metric.success
                }
            )
            
            if not metric.success and metric.error:
                trace.event(
                    name="llm_error",
                    level="ERROR",
                    metadata={'error': metric.error}
                )
        
        except Exception as e:
            logger.error(f"Failed to report LLM to Langfuse: {e}")
    
    def get_global_metrics(self) -> Dict[str, Any]:
        return {
            **self.global_metrics,
            'intent_distribution': dict(self.global_metrics['intent_distribution']),
            'node_execution_count': dict(self.global_metrics['node_execution_count']),
            'error_count': dict(self.global_metrics['error_count'])
        }
    
    def reset_conversation(self, session_id: str) -> None:
        if session_id in self.conversations:
            del self.conversations[session_id]
            logger.info(f"Reset metrics for session: {session_id}")


_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
