import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings
from integrations.console_interface import run_console_interface


def main():
    parser = argparse.ArgumentParser(description="AI Agent - Помощник продавца на Avito")
    parser.add_argument(
        "--mode",
        choices=["console", "api"],
        default="console",
        help="Run mode: console for interactive testing, api for server"
    )
    parser.add_argument(
        "--session-id",
        type=str,
        help="Session ID for conversation tracking"
    )
    
    args = parser.parse_args()
    
    settings = get_settings()
    
    print(f"Окружение: {settings.environment}")
    print(f"Уровень логирования: {settings.log_level}")
    if settings.langfuse_enabled:
        print("LangFuse включен")
    
    if args.mode == "console":
        run_console_interface(session_id=args.session_id)
    
    elif args.mode == "api":
        print("API mode not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
