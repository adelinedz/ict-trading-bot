import requests
import logging
import time
from datetime import datetime
from utils import get_env_variable

logger = logging.getLogger(__name__)
# Set logger to DEBUG level
logger.setLevel(logging.DEBUG)

class TelegramError(Exception):
    """Custom exception for Telegram-related errors"""
    pass

class TelegramNotifier:
    def __init__(self):
        self.bot_token = get_env_variable("BOT_TOKEN")
        self.chat_id = get_env_variable("CHAT_ID")
        logger.debug(f"Initializing TelegramNotifier with chat_id: {self.chat_id}")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        logger.debug(f"Base URL configured: {self.base_url}")
        self.last_message_time = 0
        self.min_message_interval = 1
        self.max_retries = 3
        self.retry_delay = 5
        
        # Verify bot token on initialization
        self.verify_bot()

    def verify_bot(self):
        """Verify bot token and permissions"""
        try:
            logger.debug("Verifying bot token...")
            response = requests.get(f"{self.base_url}/getMe", timeout=10)
            response.raise_for_status()
            bot_info = response.json()
            logger.info(f"Bot verification successful: @{bot_info['result']['username']}")
            
            # Test chat permission
            logger.debug("Testing chat permissions...")
            test_response = requests.get(
                f"{self.base_url}/getChat",
                params={"chat_id": self.chat_id},
                timeout=10
            )
            test_response.raise_for_status()
            logger.info("Chat permissions verified successfully")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Bot verification failed: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response content: {e.response.text}")
            raise TelegramError(f"Bot verification failed: {str(e)}")

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
                logger.debug(f"Attempt {attempt + 1}/{retries} to send message")
                logger.debug(f"Endpoint: {endpoint}")
                logger.debug(f"Payload: {payload}")
                
                # Rate limiting
                now = time.time()
                if now - self.last_message_time < self.min_message_interval:
                    wait_time = self.min_message_interval - (now - self.last_message_time)
                    logger.debug(f"Rate limiting: waiting {wait_time} seconds")
                    time.sleep(wait_time)
                
                response = requests.post(f"{self.base_url}/{endpoint}", data=payload, timeout=10)
                logger.debug(f"Response status code: {response.status_code}")
                logger.debug(f"Response content: {response.text}")
                
                response.raise_for_status()
                
                self.last_message_time = time.time()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt + 1}/{retries} failed")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response status code: {e.response.status_code}")
                    logger.error(f"Response content: {e.response.text}")
                
                if attempt < retries - 1:
                    logger.info(f"Waiting {self.retry_delay} seconds before retry")
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
        
        logger.debug("Preparing to send message")
        logger.debug(f"Message length: {len(message)} characters")
        logger.debug(f"Parse mode: {parse_mode}")
        
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
    logger.info("Initializing test message function")
    try:
        notifier = TelegramNotifier()
        test_message = """
*ICT Trading Bot - Test Message* 🤖

This is a test message to verify the bot's connectivity.

*Bot Status:* Online ✅
*Time:* {}

If you're seeing this message, the bot is properly configured and ready to send trading signals!
""".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        logger.info("Sending test message...")
        result = notifier.send_message(test_message)
        logger.info("Test message sent successfully")
        return result
    except Exception as e:
        logger.error(f"Failed to send test message: {e}")
        raise

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    send_test_message()


