import logging
import os
from datetime import datetime, time
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Configure logging with rotation
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ict_bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class ConfigError(Exception):
    """Custom exception for configuration errors"""
    pass

def get_env_variable(var_name: str, default: Optional[str] = None) -> str:
    """
    Get an environment variable with optional default value
    
    Args:
        var_name: Name of the environment variable
        default: Optional default value if variable is not set
        
    Returns:
        str: The value of the environment variable
        
    Raises:
        ConfigError: If variable is not set and no default is provided
    """
    try:
        value = os.environ.get(var_name)
        if value is None:
            if default is not None:
                logger.warning(f"Environment variable {var_name} not set, using default value")
                return default
            raise ConfigError(f"Environment variable {var_name} is not set")
        return value
    except Exception as e:
        error_msg = f"Error accessing environment variable {var_name}: {str(e)}"
        logger.error(error_msg)
        raise ConfigError(error_msg)

def load_json_file(file_path: str, default: Optional[Dict] = None) -> Dict:
    """
    Load a JSON file with error handling
    
    Args:
        file_path: Path to the JSON file
        default: Optional default value if file doesn't exist
        
    Returns:
        dict: Loaded JSON data
        
    Raises:
        ConfigError: If file cannot be loaded and no default is provided
    """
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        if default is not None:
            logger.warning(f"File {file_path} not found, using default value")
            return default
        raise ConfigError(f"Configuration file {file_path} not found")
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {file_path}: {str(e)}")
    except Exception as e:
        raise ConfigError(f"Error loading {file_path}: {str(e)}")

def save_json_file(file_path: str, data: Dict) -> None:
    """
    Save data to a JSON file with error handling
    
    Args:
        file_path: Path to save the JSON file
        data: Data to save
        
    Raises:
        ConfigError: If file cannot be saved
    """
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise ConfigError(f"Error saving to {file_path}: {str(e)}")

def format_price(price: float, asset: str) -> str:
    """
    Format price with appropriate precision based on asset type
    
    Args:
        price: Price to format
        asset: Asset symbol
        
    Returns:
        str: Formatted price
    """
    # More decimal places for forex pairs
    precision = 5 if '/' in asset else 2
    return f"{price:.{precision}f}"

def calculate_pip_value(price: float, asset: str) -> float:
    """
    Calculate pip value based on asset type
    
    Args:
        price: Current price
        asset: Asset symbol
        
    Returns:
        float: Pip value
    """
    if '/' in asset:  # Forex pairs
        return 0.0001
    elif asset in ['BTC-USD', 'ETH-USD']:  # Crypto
        return 1.0
    else:  # Stocks/indices
        return 0.01

def is_market_open(asset: str) -> bool:
    """
    Check if market is currently open for the given asset
    
    Args:
        asset: Asset symbol
        
    Returns:
        bool: True if market is open
    """
    current_time = datetime.now().time()
    
    # 24/7 markets
    if '/' in asset or asset in ['BTC-USD', 'ETH-USD']:
        return True
        
    # US market hours (simplified)
    market_open = time(9, 30)  # 9:30 AM EST
    market_close = time(16, 0)  # 4:00 PM EST
    
    return market_open <= current_time <= market_close

def get_risk_params(account_size: float, risk_percentage: float, entry: float, stop_loss: float) -> Dict[str, float]:
    """
    Calculate position size and risk parameters
    
    Args:
        account_size: Total account size
        risk_percentage: Risk percentage (0-100)
        entry: Entry price
        stop_loss: Stop loss price
        
    Returns:
        dict: Dictionary containing position size and risk parameters
    """
    risk_amount = account_size * (risk_percentage / 100)
    price_risk = abs(entry - stop_loss)
    position_size = risk_amount / price_risk
    
    return {
        "position_size": position_size,
        "risk_amount": risk_amount,
        "price_risk": price_risk
    }


