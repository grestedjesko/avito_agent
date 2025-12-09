from typing import Optional, Dict, Any, List
import atexit
import logging
from src.config import get_settings
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.decorators import observe, langfuse_context

logger = logging.getLogger(__name__)

try:
    LANGFUSE_AVAILABLE = True
except (ImportError, Exception) as e:
    logger.warning(f"Langfuse not available: {e}")
    Langfuse = None
    CallbackHandler = None
    observe = None
    langfuse_context = None
    LANGFUSE_AVAILABLE = False


class LangFuseManager:
    _instance: Optional['LangFuseManager'] = None
    _langfuse_client: Optional[Langfuse] = None
    _callback_handlers: Dict[str, Any] = {}
    _traces: Dict[str, Any] = {}
    
    def __new__(cls) -> 'LangFuseManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if self._langfuse_client is None:
            self._initialize()
    
    def _initialize(self) -> None:
        if not LANGFUSE_AVAILABLE:
            logger.info("Langfuse not available, monitoring disabled")
            return
            
        settings = get_settings()
        
        if not settings.langfuse_enabled:
            logger.info("Langfuse disabled in configuration")
            return
            
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.warning("Langfuse keys not configured, monitoring disabled")
            return
        
        try:
            self._langfuse_client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                enabled=True,
                flush_at=10,  # Flush after 10 events
                flush_interval=1.0,  # Flush every second
            )
            
            logger.info(f"Langfuse initialized successfully at {settings.langfuse_host}")
            
            atexit.register(self._cleanup)
            
        except Exception as e:
            logger.error(f"Failed to initialize Langfuse: {e}", exc_info=True)
            self._langfuse_client = None
    
    def _cleanup(self) -> None:
        if self._langfuse_client:
            logger.info("Flushing Langfuse data before shutdown...")
            self._langfuse_client.flush()
    
    @property
    def client(self) -> Optional[Langfuse]:
        return self._langfuse_client
    
    def get_callback_handler(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[CallbackHandler]:
        if not LANGFUSE_AVAILABLE or not self._langfuse_client:
            return None
        
        try:
            settings = get_settings()
            
            handler = CallbackHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                session_id=session_id,
                user_id=user_id,
                trace_name=trace_name,
                metadata=metadata,
                tags=tags
            )
            
            return handler
            
        except Exception as e:
            logger.error(f"Failed to create callback handler: {e}", exc_info=True)
            return None
    
    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        input_data: Optional[Any] = None
    ):
        if not self._langfuse_client:
            return None
        
        try:
            trace = self._langfuse_client.trace(
                name=name,
                session_id=session_id,
                user_id=user_id,
                metadata=metadata,
                tags=tags,
                input=input_data
            )
            
            if session_id:
                self._traces[session_id] = trace
            
            return trace
            
        except Exception as e:
            logger.error(f"Failed to create trace: {e}", exc_info=True)
            return None
    
    def get_trace(self, session_id: str):
        return self._traces.get(session_id)
    
    def is_enabled(self) -> bool:
        return self._langfuse_client is not None
    
    def flush(self) -> None:
        if self._langfuse_client:
            try:
                self._langfuse_client.flush()
                logger.debug("Flushed Langfuse data")
            except Exception as e:
                logger.error(f"Failed to flush Langfuse data: {e}")
    
    def score(
        self,
        trace_id: Optional[str] = None,
        name: str = "quality",
        value: float = 0.0,
        comment: Optional[str] = None
    ) -> None:
        if not self._langfuse_client:
            return
        
        try:
            self._langfuse_client.score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment
            )
        except Exception as e:
            logger.error(f"Failed to add score: {e}")


langfuse_manager = LangFuseManager()


def get_langfuse_callback(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None
) -> Optional[CallbackHandler]:
    return langfuse_manager.get_callback_handler(
        session_id=session_id,
        user_id=user_id,
        trace_name=trace_name,
        metadata=metadata,
        tags=tags
    )


def get_langfuse_client() -> Optional[Langfuse]:
    return langfuse_manager.client


def is_langfuse_enabled() -> bool:
    return langfuse_manager.is_enabled()


__all__ = [
    'LangFuseManager',
    'langfuse_manager',
    'get_langfuse_callback',
    'get_langfuse_client',
    'is_langfuse_enabled',
    'LANGFUSE_AVAILABLE'
]

if LANGFUSE_AVAILABLE:
    __all__.extend(['observe', 'langfuse_context'])
