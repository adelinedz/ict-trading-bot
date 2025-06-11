import time
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any
import sys
import signal as sys_signal
from pathlib import Path
import gc
import psutil
import pytz

from market_data import get_historical_data, MarketDataError, get_market_hours
from signal_engine import generate_signal, is_in_kill_zone
from telegram_notifier import TelegramNotifier, TelegramError, send_test_message
from utils import get_env_variable, ConfigError

# Configure logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / 'trading_bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Send initial test message
try:
    logger.info("Sending startup test message...")
    send_test_message()
    logger.info("Test message sent successfully!")
except Exception as e:
    logger.error(f"Failed to send test message: {e}")

# Configure timezone
EST_TZ = pytz.timezone('US/Eastern')

# Trading pairs configuration with their respective timeframes
ASSETS = {
    "EUR/USD": {"ticker": "EUR/USD", "timeframe": "5m", "min_volume": 0},
    "GBP/USD": {"ticker": "GBP/USD", "timeframe": "5m", "min_volume": 0},
    "NASDAQ-100": {"ticker": "^NDX", "timeframe": "5m", "min_volume": 1000},
    "Gold": {"ticker": "GC=F", "timeframe": "5m", "min_volume": 100},
    "Bitcoin": {"ticker": "BTC-USD", "timeframe": "5m", "min_volume": 1}
}

class MemoryMonitor:
    def __init__(self, threshold_mb=500):
        self.threshold_mb = threshold_mb
        self.process = psutil.Process()
    
    def check_memory(self):
        """Check memory usage and cleanup if necessary"""
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        if memory_mb > self.threshold_mb:
            logger.warning(f"Memory usage high ({memory_mb:.1f} MB). Running garbage collection...")
            gc.collect()
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            logger.info(f"Memory usage after cleanup: {memory_mb:.1f} MB")

class SignalManager:
    def __init__(self, storage_file: str = "signals.json"):
        self.storage_file = Path(storage_file)
        self.sent_signals: Dict[str, Dict[str, Any]] = {}
        self.signal_expiry = timedelta(hours=4)  # Signals expire after 4 hours
        self.load_signals()

    def load_signals(self):
        """Load previously sent signals from storage"""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r') as f:
                    stored_signals = json.load(f)
                    # Convert stored timestamps back to datetime objects
                    for asset, signal in stored_signals.items():
                        if signal and 'timestamp' in signal:
                            signal['timestamp'] = datetime.fromisoformat(signal['timestamp'])
                    self.sent_signals = stored_signals
            except Exception as e:
                logger.error(f"Error loading signals from storage: {e}")
                self.sent_signals = {}

    def save_signals(self):
        """Save current signals to storage"""
        try:
            # Convert datetime objects to ISO format strings for JSON serialization
            signals_to_save = {}
            for asset, signal in self.sent_signals.items():
                if signal:
                    signal_copy = signal.copy()
                    if 'timestamp' in signal_copy:
                        signal_copy['timestamp'] = signal_copy['timestamp'].isoformat()
                    signals_to_save[asset] = signal_copy
                else:
                    signals_to_save[asset] = None

            # Write to temporary file first
            temp_file = self.storage_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(signals_to_save, f, indent=2)
            
            # Rename temporary file to actual file
            temp_file.replace(self.storage_file)
            
        except Exception as e:
            logger.error(f"Error saving signals to storage: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def is_duplicate_signal(self, asset: str, new_signal: Dict[str, Any]) -> bool:
        """
        Check if a signal is a duplicate, considering both similarity and expiry time
        """
        if asset not in self.sent_signals or not self.sent_signals[asset]:
            return False

        old_signal = self.sent_signals[asset]
        signal_time = old_signal.get('timestamp')

        # Check if the old signal has expired
        if signal_time and datetime.now(EST_TZ) - signal_time > self.signal_expiry:
            return False

        # Compare relevant signal properties
        try:
            return (
                old_signal['direction'] == new_signal['direction'] and
                old_signal['setup'] == new_signal['setup'] and
                abs(float(old_signal['entry']) - float(new_signal['entry'])) / float(old_signal['entry']) < 0.001
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error comparing signals: {e}")
            return False

    def add_signal(self, asset: str, signal: Dict[str, Any]):
        """Add a new signal with timestamp"""
        signal['timestamp'] = datetime.now(EST_TZ)
        self.sent_signals[asset] = signal
        self.save_signals()

    def cleanup_expired_signals(self):
        """Remove expired signals"""
        current_time = datetime.now(EST_TZ)
        for asset in list(self.sent_signals.keys()):
            signal = self.sent_signals[asset]
            if signal and 'timestamp' in signal:
                if current_time - signal['timestamp'] > self.signal_expiry:
                    self.sent_signals[asset] = None
        self.save_signals()

class TradingBot:
    def __init__(self):
        self.notifier = TelegramNotifier()
        self.signal_manager = SignalManager()
        self.memory_monitor = MemoryMonitor()
        self.running = True
        self.last_run_time = {}  # Track last run time for each asset
        self.setup_signal_handlers()

    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        sys_signal.signal(sys_signal.SIGINT, self.handle_shutdown)
        sys_signal.signal(sys_signal.SIGTERM, self.handle_shutdown)

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info("Shutdown signal received. Cleaning up...")
        self.running = False

    def get_market_data(self, asset_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch and prepare market data for analysis
        """
        try:
            # Check if market is open
            market_hours = get_market_hours(asset_config['ticker'])
            if not market_hours['is_24h'] and not market_hours['is_open']:
                logger.info(f"Market closed for {asset_config['ticker']}")
                return None

            # Get enough historical data for analysis
            df = get_historical_data(
                asset_config['ticker'],
                interval=asset_config['timeframe'],
                period='1d'  # Get 1 day of data for better context
            )
            
            if df is None or df.empty:
                raise MarketDataError(f"No data received for {asset_config['ticker']}")
                
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {asset_config['ticker']}: {e}")
            return None

    def should_process_asset(self, asset_name: str) -> bool:
        """
        Determine if an asset should be processed based on time constraints
        """
        current_time = datetime.now(EST_TZ)
        
        # Check last run time
        if asset_name in self.last_run_time:
            last_run = self.last_run_time[asset_name]
            min_interval = timedelta(minutes=4)  # Minimum 4 minutes between checks
            
            if current_time - last_run < min_interval:
                return False
        
        self.last_run_time[asset_name] = current_time
        return True

    def process_signals(self):
        """
        Main signal processing loop
        """
        current_time = datetime.now(EST_TZ)
        
        if not is_in_kill_zone(current_time):
            logger.info(f"Not in a kill zone ({current_time.strftime('%H:%M')}). Waiting...")
            return

        logger.info(f"Currently in a kill zone ({current_time.strftime('%H:%M')}). Checking for signals...")
        
        # Cleanup expired signals before processing new ones
        self.signal_manager.cleanup_expired_signals()

        # Check memory usage
        self.memory_monitor.check_memory()

        for asset_name, asset_config in ASSETS.items():
            try:
                # Check if we should process this asset
                if not self.should_process_asset(asset_name):
                    continue
                    
                logger.info(f"Processing {asset_name}...")
                
                # Get market data
                df = self.get_market_data(asset_config)
                if df is None:
                    continue

                # Generate signal
                signal = generate_signal(asset_name, df)
                if not signal:
                    logger.info(f"No signal detected for {asset_name}")
                    continue

                # Check for duplicates
                if self.signal_manager.is_duplicate_signal(asset_name, signal):
                    logger.info(f"Duplicate signal for {asset_name} - skipping")
                    continue

                # Send signal
                try:
                    self.notifier.send_signal(signal)
                    self.signal_manager.add_signal(asset_name, signal)
                    logger.info(f"Signal dispatched for {asset_name}: {signal}")
                except TelegramError as e:
                    logger.error(f"Failed to send signal for {asset_name}: {e}")

            except Exception as e:
                logger.error(f"Error processing {asset_name}: {e}")
                continue

            finally:
                # Cleanup memory after processing each asset
                gc.collect()

    def run(self):
        """
        Main bot loop
        """
        logger.info("Starting ICT Trading Bot...")
        
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while self.running:
            try:
                self.process_signals()
                consecutive_errors = 0  # Reset error counter on success
                
                # Sleep until next check
                time.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                consecutive_errors += 1
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors ({consecutive_errors}). Shutting down...")
                    self.running = False
                else:
                    sleep_time = 60 * consecutive_errors  # Progressive backoff
                    logger.info(f"Sleeping for {sleep_time} seconds before retry...")
                    time.sleep(sleep_time)

        logger.info("Bot shutdown complete")

if __name__ == '__main__':
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)


