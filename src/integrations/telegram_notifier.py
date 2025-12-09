import asyncio
import logging
from typing import Optional
from config import get_settings

logger = logging.getLogger(__name__)

try:
    from telegram import Bot
    TELEGRAM_AVAILABLE = True
except ImportError:
    logger.warning("python-telegram-bot not installed. Telegram notifications disabled.")
    TELEGRAM_AVAILABLE = False


class TelegramNotifier:
    def __init__(self):
        settings = get_settings()
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = bool(self.bot_token and self.chat_id and TELEGRAM_AVAILABLE)
        
        if self.enabled:
            self.bot = Bot(token=self.bot_token)
            logger.info("Telegram notifier enabled")
        else:
            self.bot = None
            if not TELEGRAM_AVAILABLE:
                logger.warning("Telegram notifier disabled: library not available")
            else:
                logger.warning("Telegram notifier disabled: missing token or chat_id")
    
    def send_message(self, message: str) -> bool:
        if not self.enabled:
            logger.info(f"[Telegram] Would send: {message}")
            return False
        
        try:
            logger.info(f"[Telegram] Sending to {self.chat_id}")
            
            asyncio.run(self._send_async(message))
            return True
            
        except Exception as e:
            logger.error(f"[Telegram] Error sending message: {e}")
            return False
    
    async def _send_async(self, message: str):
        async with self.bot:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
    
    def notify_new_message(self, user_message: str, session_id: str) -> bool:
        message = f"""
🔔 Новое сообщение от покупателя

Session: {session_id}
Сообщение: {user_message}
"""
        return self.send_message(message.strip())
    
    def notify_meeting_scheduled(
        self,
        product_title: str,
        location: str,
        date: str,
        time: str,
        price: Optional[float] = None,
        calendar_link: Optional[str] = None
    ) -> bool:
        message = f"""
📅 <b>Запланирована встреча</b>

<b>Товар:</b> {product_title}
<b>Место:</b> {location}
<b>Дата:</b> {date}
<b>Время:</b> {time}"""
        
        if price:
            message += f"\n<b>Цена:</b> {price:,.0f} руб."
        
        if calendar_link:
            message += f"\n\n<a href=\"{calendar_link}\">🔗 Открыть в календаре</a>"
        
        return self.send_message(message.strip())
    
    def notify_deal_agreed(
        self,
        product_title: str,
        agreed_price: float
    ) -> bool:
        message = f"""
✅ <b>Договорились о сделке</b>

<b>Товар:</b> {product_title}
<b>Цена:</b> {agreed_price:,.0f} руб.
"""
        return self.send_message(message.strip())


_notifier: Optional[TelegramNotifier] = None


def get_telegram_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
