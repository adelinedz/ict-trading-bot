import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging
import pytz

logger = logging.getLogger(__name__)

# Configure rate limiting
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
MIN_REQUIRED_CANDLES = 50

# Configure timezone
EST_TZ = pytz.timezone('US/Eastern')

class MarketDataError(Exception):
    """Custom exception for market data related errors"""
    pass

def validate_data(df, min_required_candles=MIN_REQUIRED_CANDLES):
    """
    Validates the market data for completeness and quality
    """
    if df is None or df.empty:
        raise MarketDataError("No data received")
        
    if len(df) < min_required_candles:
        raise MarketDataError(f"Insufficient data points. Got {len(df)}, need {min_required_candles}")
        
    # Ensure index is timezone-aware
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize('UTC').tz_convert(EST_TZ)
        
    # Check for missing values
    if df.isnull().any().any():
        # Forward fill small gaps (up to 2 missing values)
        df.fillna(method='ffill', limit=2, inplace=True)
        
        # If still have missing values after forward fill
        if df.isnull().any().any():
            raise MarketDataError("Data contains missing values that couldn't be filled")
            
    # Check for zero or negative prices
    if (df[['Open', 'High', 'Low', 'Close']] <= 0).any().any():
        raise MarketDataError("Data contains invalid (zero or negative) prices")
        
    # Verify OHLC relationships
    if not all(df['High'] >= df['Low']) or \
       not all(df['High'] >= df['Open']) or \
       not all(df['High'] >= df['Close']) or \
       not all(df['Low'] <= df['Open']) or \
       not all(df['Low'] <= df['Close']):
        raise MarketDataError("Data contains invalid OHLC relationships")
        
    # Check for duplicate timestamps
    if df.index.duplicated().any():
        raise MarketDataError("Data contains duplicate timestamps")
        
    # Check for future timestamps
    now = datetime.now(EST_TZ)
    if df.index.max().tz_convert(EST_TZ) > now:
        raise MarketDataError("Data contains future timestamps")
        
    return df

def format_ticker(ticker):
    """
    Formats ticker symbols for yfinance compatibility
    """
    # Remove any whitespace
    ticker = ticker.strip()
    
    # Forex pairs need =X suffix
    if '/' in ticker:
        base, quote = ticker.split('/')
        return f"{base.strip()}{quote.strip()}=X"
        
    # Special cases
    if ticker == "NASDAQ-100":
        return "^NDX"
    elif ticker == "Gold":
        return "GC=F"
        
    return ticker

def get_historical_data(ticker, interval='1h', period='7d', retries=MAX_RETRIES):
    """
    Fetches historical data for a given ticker with retry mechanism and validation.
    
    Args:
        ticker (str): The ticker symbol (e.g., 'EUR/USD', 'GC=F' for Gold, 'BTC-USD' for Bitcoin)
        interval (str): Data interval ('1m', '5m', '15m', '1h', '1d')
        period (str): Data period ('1d', '5d', '1mo', '3mo', '1y', '5y', 'max')
        retries (int): Number of retry attempts
        
    Returns:
        pd.DataFrame: Validated historical data
        
    Raises:
        MarketDataError: If data cannot be fetched or validated after retries
    """
    formatted_ticker = format_ticker(ticker)
    
    for attempt in range(retries):
        try:
            logger.info(f"Fetching {interval} data for {ticker}, attempt {attempt + 1}/{retries}")
            
            # Download data
            data = yf.download(
                formatted_ticker,
                interval=interval,
                period=period,
                progress=False,
                show_errors=False,
                threads=False  # Disable multithreading to avoid potential issues
            )
            
            if data.empty:
                raise MarketDataError(f"No data received for {ticker}")
                
            # Convert index to EST timezone
            if data.index.tzinfo is None:
                data.index = data.index.tz_localize('UTC').tz_convert(EST_TZ)
            
            # Validate and return data
            return validate_data(data)
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed for {ticker}: {str(e)}")
            
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
            else:
                raise MarketDataError(f"Failed to fetch data for {ticker} after {retries} attempts: {str(e)}")

def get_latest_candle(ticker, interval='5m', retries=MAX_RETRIES):
    """
    Fetches the latest candle data for a given ticker with validation.
    
    Args:
        ticker (str): The ticker symbol
        interval (str): Data interval ('1m', '5m', '15m', '1h')
        retries (int): Number of retry attempts
        
    Returns:
        pd.Series: Latest validated candle data
        
    Raises:
        MarketDataError: If data cannot be fetched or validated after retries
    """
    # Get slightly more data than needed to ensure we have enough for validation
    lookback_periods = {
        '1m': '30m',
        '5m': '1h',
        '15m': '2h',
        '1h': '4h',
        '4h': '12h',
        '1d': '5d'
    }
    
    period = lookback_periods.get(interval, '1d')
    
    for attempt in range(retries):
        try:
            logger.info(f"Fetching latest {interval} candle for {ticker}, attempt {attempt + 1}/{retries}")
            
            # Get recent data
            data = get_historical_data(ticker, interval=interval, period=period)
            
            if data is None or data.empty:
                raise MarketDataError("No data received")
                
            # Get the latest complete candle (second to last if available)
            if len(data) >= 2:
                latest_complete = data.iloc[-2]
                current_incomplete = data.iloc[-1]
                
                # Check if the current candle is too new (less than 20% of interval passed)
                interval_minutes = int(''.join(filter(str.isdigit, interval)))
                candle_age = (datetime.now(EST_TZ) - current_incomplete.name).total_seconds() / 60
                
                if candle_age < interval_minutes * 0.2:
                    return latest_complete
                
                # If the current candle shows significant movement, use it instead
                if abs(current_incomplete['Close'] - current_incomplete['Open']) > \
                   abs(latest_complete['Close'] - latest_complete['Open']):
                    return current_incomplete
                    
                return latest_complete
            
            return data.iloc[-1]
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed for latest candle {ticker}: {str(e)}")
            
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
            else:
                raise MarketDataError(f"Failed to fetch latest candle for {ticker} after {retries} attempts: {str(e)}")

def get_market_hours(ticker):
    """
    Returns the trading hours for the given ticker in EST
    """
    current_time = datetime.now(EST_TZ)
    
    # Basic implementation - can be expanded based on needs
    if '/' in ticker:  # Forex
        return {
            'is_24h': True,
            'opens': None,
            'closes': None,
            'is_open': True
        }
    elif ticker in ['BTC-USD', 'ETH-USD']:  # Crypto
        return {
            'is_24h': True,
            'opens': None,
            'closes': None,
            'is_open': True
        }
    else:  # Stocks/Commodities (basic US market hours)
        market_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = current_time.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return {
            'is_24h': False,
            'opens': market_open.time(),
            'closes': market_close.time(),
            'is_open': market_open.time() <= current_time.time() <= market_close.time()
        }

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Example usage with error handling
    try:
        # EUR/USD
        eurusd_data = get_historical_data('EUR/USD', interval='1h', period='1d')
        if eurusd_data is not None:
            logger.info("EUR/USD Historical Data:")
            logger.info(eurusd_data.head())

        # BTC/USD latest 5-minute candle
        btc_latest_candle = get_latest_candle('BTC-USD', interval='5m')
        if btc_latest_candle is not None:
            logger.info("\nBTC/USD Latest 5-minute Candle:")
            logger.info(btc_latest_candle)
            
    except MarketDataError as e:
        logger.error(f"Market data error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")


