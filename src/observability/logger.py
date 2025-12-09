import logging
import sys
import json
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path

from src.config import get_settings


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        if hasattr(record, 'session_id'):
            log_data['session_id'] = record.session_id
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'intent'):
            log_data['intent'] = record.intent
        if hasattr(record, 'node'):
            log_data['node'] = record.node
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        
        extra_fields = {
            k: v for k, v in record.__dict__.items()
            if k not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                        'levelname', 'levelno', 'lineno', 'module', 'msecs',
                        'message', 'pathname', 'process', 'processName',
                        'relativeCreated', 'thread', 'threadName', 'exc_info',
                        'exc_text', 'stack_info', 'session_id', 'user_id',
                        'intent', 'node', 'duration_ms']
        }
        
        if extra_fields:
            log_data['extra'] = extra_fields
        
        return json.dumps(log_data)


class ColoredConsoleFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',     # Blue
        'INFO': '\033[92m',      # Green
        'WARNING': '\033[93m',   # Yellow
        'ERROR': '\033[91m',     # Red
        'CRITICAL': '\033[91m\033[1m',  # Red + Bold
        'RESET': '\033[0m'
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        log_parts = [
            f"{color}[{record.levelname}]{reset}",
            f"{timestamp}",
            f"{record.name}:",
            record.getMessage()
        ]
        
        context_parts = []
        if hasattr(record, 'session_id'):
            context_parts.append(f"session={record.session_id}")
        if hasattr(record, 'node'):
            context_parts.append(f"node={record.node}")
        if hasattr(record, 'duration_ms'):
            context_parts.append(f"duration={record.duration_ms}ms")
        
        if context_parts:
            log_parts.append(f"[{', '.join(context_parts)}]")
        
        message = " ".join(log_parts)
        
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        
        return message


class AgentLogger:
    def __init__(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.logger = logging.getLogger(name)
        self.session_id = session_id
        self.user_id = user_id
        self.context = context or {}
    
    def _log(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        extra = extra or {}
        
        if self.session_id:
            extra['session_id'] = self.session_id
        if self.user_id:
            extra['user_id'] = self.user_id
        
        extra.update(self.context)
        
        extra.update(kwargs)
        
        self.logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        if exc_info:
            kwargs['exc_info'] = True
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, exc_info: bool = False, **kwargs) -> None:
        if exc_info:
            kwargs['exc_info'] = True
        self._log(logging.CRITICAL, message, **kwargs)
    
    def set_context(self, **kwargs) -> None:
        self.context.update(kwargs)
    
    def clear_context(self) -> None:
        self.context.clear()


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    json_format: bool = False
) -> None:
    settings = get_settings()
    log_level = log_level or settings.log_level
    
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    root_logger.handlers.clear()
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    
    if json_format or settings.environment == 'production':
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(ColoredConsoleFormatter())
    
    root_logger.addHandler(console_handler)
    
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)
    
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging initialized: level={log_level}, environment={settings.environment}"
    )


def get_logger(
    name: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    **context
) -> AgentLogger:
    return AgentLogger(
        name=name,
        session_id=session_id,
        user_id=user_id,
        context=context
    )


try:
    setup_logging()
except Exception as e:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logging.error(f"Failed to setup logging: {e}", exc_info=True)
