import time
import functools
from typing import Any, Dict, Optional, Callable, List
from contextlib import contextmanager
import logging

from src.observability.langfuse_config import get_langfuse_client, langfuse_manager
from src.observability.metrics import get_metrics_collector

logger = logging.getLogger(__name__)


class AgentTracer:
    def __init__(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.langfuse = get_langfuse_client()
        self.metrics = get_metrics_collector()
        self.current_trace = None
        self.span_stack: List[Any] = []
        self.default_metadata = metadata or {}
        
        self.metrics.start_conversation(session_id)
    
    def start_trace(
        self,
        name: str,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> None:
        if self.langfuse:
            try:
                trace_metadata = {**self.default_metadata}
                if metadata:
                    trace_metadata.update(metadata)
                
                self.current_trace = self.langfuse.trace(
                    name=name,
                    session_id=self.session_id,
                    user_id=self.user_id,
                    input=input_data,
                    metadata=trace_metadata,
                    tags=tags
                )
                
                logger.debug(f"Started trace: {name}", extra={'session_id': self.session_id})
                
            except Exception as e:
                logger.error(f"Failed to start trace: {e}", exc_info=True)
    
    def update_trace(
        self,
        output_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        if self.langfuse and self.current_trace:
            try:
                if output_data:
                    self.current_trace.update(output=output_data)
                if metadata:
                    self.current_trace.update(metadata=metadata)
            except Exception as e:
                logger.error(f"Failed to update trace: {e}")
    
    def log_event(
        self,
        name: str,
        level: str = "DEFAULT",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        if self.langfuse and self.current_trace:
            try:
                self.current_trace.event(
                    name=name,
                    level=level,
                    metadata=metadata or {}
                )
                logger.debug(f"Logged event: {name}", extra={'session_id': self.session_id})
            except Exception as e:
                logger.error(f"Failed to log event: {e}")
    
    @contextmanager
    def span(
        self,
        name: str,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        track_metrics: bool = True
    ):
        start_time = time.time()
        error = None
        output_data = None
        span_obj = None
        node_metric = None
        
        if track_metrics:
            node_metric = self.metrics.start_node_execution(
                session_id=self.session_id,
                node_name=name,
                metadata=metadata
            )
        
        if self.langfuse and self.current_trace:
            try:
                span_obj = self.current_trace.span(
                    name=name,
                    input=input_data,
                    metadata=metadata or {}
                )
                self.span_stack.append(span_obj)
            except Exception as e:
                logger.error(f"Failed to create span: {e}")
        
        try:
            class SpanContext:
                def __init__(self):
                    self.output = None
                
                def set_output(self, data: Any):
                    self.output = data
            
            context = SpanContext()
            yield context
            output_data = context.output
            
        except Exception as e:
            error = str(e)
            logger.error(f"Error in span {name}: {e}", exc_info=True)
            raise
        
        finally:
            duration_ms = (time.time() - start_time) * 1000
            
            if span_obj:
                try:
                    span_metadata = metadata or {}
                    span_metadata['duration_ms'] = duration_ms
                    if error:
                        span_metadata['error'] = error
                    
                    span_obj.update(
                        output=output_data,
                        metadata=span_metadata
                    )
                    span_obj.end()
                    
                    if span_obj in self.span_stack:
                        self.span_stack.remove(span_obj)
                        
                except Exception as e:
                    logger.error(f"Failed to update span: {e}")
            
            if track_metrics and node_metric:
                self.metrics.finish_node_execution(
                    session_id=self.session_id,
                    metric=node_metric,
                    success=(error is None),
                    error=error
                )
            
            logger.debug(
                f"Span completed: {name}",
                extra={
                    'session_id': self.session_id,
                    'duration_ms': duration_ms,
                    'error': error
                }
            )
    
    @contextmanager
    def llm_generation(
        self,
        name: str,
        model: str,
        input_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        start_time = time.time()
        error = None
        output_data = None
        generation_obj = None
        llm_metric = None
        
        # Start LLM metrics tracking
        llm_metric = self.metrics.start_llm_call(
            session_id=self.session_id,
            model=model,
            operation=name
        )
        
        # Create Langfuse generation
        if self.langfuse and self.current_trace:
            try:
                generation_obj = self.current_trace.generation(
                    name=name,
                    model=model,
                    input=input_data,
                    metadata=metadata or {}
                )
            except Exception as e:
                logger.error(f"Failed to create generation: {e}")
        
        try:
            class GenerationContext:
                def __init__(self):
                    self.output = None
                    self.input_tokens = 0
                    self.output_tokens = 0
                
                def set_output(self, data: Any):
                    """Set the output data for the generation."""
                    self.output = data
                
                def set_usage(self, input_tokens: int = 0, output_tokens: int = 0):
                    """Set token usage information."""
                    self.input_tokens = input_tokens
                    self.output_tokens = output_tokens
            
            context = GenerationContext()
            yield context
            output_data = context.output
            
        except Exception as e:
            error = str(e)
            logger.error(f"Error in generation {name}: {e}", exc_info=True)
            raise
        
        finally:
            duration_ms = (time.time() - start_time) * 1000
            
            if generation_obj:
                try:
                    gen_metadata = metadata or {}
                    gen_metadata['duration_ms'] = duration_ms
                    if error:
                        gen_metadata['error'] = error
                    
                    generation_obj.update(
                        output=output_data,
                        usage={
                            'input': context.input_tokens,
                            'output': context.output_tokens,
                            'total': context.input_tokens + context.output_tokens
                        },
                        metadata=gen_metadata
                    )
                    generation_obj.end()
                    
                except Exception as e:
                    logger.error(f"Failed to update generation: {e}")
            
            if llm_metric:
                self.metrics.finish_llm_call(
                    session_id=self.session_id,
                    metric=llm_metric,
                    success=(error is None),
                    error=error,
                    input_tokens=context.input_tokens,
                    output_tokens=context.output_tokens
                )
    
    def score(
        self,
        name: str,
        value: float,
        comment: Optional[str] = None
    ) -> None:
        self.metrics.record_score(
            session_id=self.session_id,
            name=name,
            value=value,
            comment=comment
        )
        
        if self.langfuse and self.current_trace:
            try:
                self.current_trace.score(
                    name=name,
                    value=value,
                    comment=comment
                )
            except Exception as e:
                logger.error(f"Failed to add score: {e}")
    
    def end_trace(self) -> None:
        if self.current_trace:
            try:
                self.current_trace.update(metadata={'status': 'completed'})
            except Exception as e:
                logger.error(f"Failed to update trace on end: {e}")
        
        summary = self.metrics.finish_conversation(self.session_id)
        if summary:
            logger.info(
                f"Conversation completed",
                extra={
                    'session_id': self.session_id,
                    **summary
                }
            )
        
        if self.langfuse:
            self.langfuse.flush()
        
        self.current_trace = None
        self.span_stack.clear()


def create_tracer(
    session_id: str,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> AgentTracer:
    return AgentTracer(
        session_id=session_id,
        user_id=user_id,
        metadata=metadata
    )


def trace_node(node_name: Optional[str] = None):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state, *args, **kwargs):
            session_id = state.get('session_id', 'unknown')
            name = node_name or func.__name__
            
            tracer = state.get('_tracer')
            if not tracer:
                tracer = create_tracer(session_id)
                state['_tracer'] = tracer
            
            with tracer.span(name, input_data={'state_keys': list(state.keys())}):
                result = func(state, *args, **kwargs)
                return result
        
        return wrapper
    return decorator
