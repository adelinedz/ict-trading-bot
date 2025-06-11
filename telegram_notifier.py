import requests
import logging
import time
from datetime import datetime
from utils import get_env_variable

logger = logging.getLogger(__name__)

class TelegramError(Exception):
    """Custom exception for Telegram-related errors"""
    pass

class TelegramNotifier:
    def __init__(self):
        self.bot_token = get_env_variable("BOT_TOKEN")
        self.chat_id = get_env_variable("CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_message_time = 0
        self.min_message_interval = 1  # Minimum seconds between messages
        self.max_retries = 3
        self.retry_delay = 5

    def format_signal_message(self, signal):
        """
        Formats a trading signal into a well-structured Telegram message
        """
        # Determine emoji based on direction
        direction_emoji = "🟢" if signal["direction"] == "BUY" else "🔴"
        
        # Format prices with appropriate precision
        precision = 5 if "/" in signal["asset"] else 2  # More precision for forex pairs
        
        # Calculate potential profit/loss percentages
        entry = float(signal["entry"])
        sl = float(signal["stop_loss"])
        tp = float(signal["take_profit"])
        
        risk_pips = abs(entry - sl)
        reward_pips = abs(tp - entry)
        
        # Build message
        message = f"""
*{direction_emoji} NEW ICT SIGNAL*

*Asset:* {signal["asset"]}
*Direction:* {signal["direction"]}
*Entry:* {entry:.{precision}f}
*Stop Loss:* {sl:.{precision}f} ({risk_pips:.{precision}f} pips)
*Take Profit:* {tp:.{precision}f} ({reward_pips:.{precision}f} pips)
*R:R Ratio:* 1:{reward_pips/risk_pips:.1f}

*Kill Zone:* {signal["kill_zone"]}
*Setup:* {signal["setup"]}
*Risk:* {signal["risk"]}
*Confidence:* {signal.get("confidence", "N/A")}

*Time:* {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} EST
"""
        return message

    def _send_with_retry(self, endpoint, payload, retries=None):
        """
        Sends a request to Telegram API with retry mechanism
        """
        if retries is None:
            retries = self.max_retries
            
        for attempt in range(retries):
            try:
                # Rate limiting
                now = time.time()
                if now - self.last_message_time < self.min_message_interval:
                    time.sleep(self.min_message_interval - (now - self.last_message_time))
                
                response = requests.post(f"{self.base_url}/{endpoint}", data=payload, timeout=10)
                response.raise_for_status()
                
                self.last_message_time = time.time()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{retries} failed: {str(e)}")
                
                if attempt < retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise TelegramError(f"Failed to send message after {retries} attempts: {str(e)}")

    def send_message(self, message, parse_mode="Markdown"):
        """
        Sends a text message to Telegram
        """
        if not isinstance(message, str):
            raise ValueError("Message must be a string")
            
        if len(message) > 4096:
            logger.warning("Message too long, truncating to 4096 characters")
            message = message[:4093] + "..."
            
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode
        }
        
        try:
            result = self._send_with_retry("sendMessage", payload)
            logger.info("Telegram message sent successfully")
            return result
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise

    def send_signal(self, signal):
        """
        Formats and sends a trading signal
        """
        try:
            message = self.format_signal_message(signal)
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Error formatting/sending signal: {e}")
            raise TelegramError(f"Failed to send signal: {str(e)}")

def send_test_message():
    """
    Sends a test message to verify Telegram bot configuration
    """
    notifier = TelegramNotifier()
    test_signal = {
        "asset": "BTC/USD",
        "direction": "BUY",
        "entry": 31250.75,
        "stop_loss": 30980.25,
        "take_profit": 31800.50,
        "kill_zone": "London",
        "setup": "FVG_bullish + OB_bullish + BOS_bullish",
        "risk": "0.8%",
        "confidence": "3/4 confluences"
    }
    
    try:
        logger.info("Sending test signal...")
        notifier.send_signal(test_signal)
        logger.info("Test signal sent successfully")
    except TelegramError as e:
        logger.error(f"Failed to send test signal: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    send_test_message()


