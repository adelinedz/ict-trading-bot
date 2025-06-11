import pandas as pd
import logging
from datetime import datetime, time
import numpy as np

logger = logging.getLogger(__name__)

def is_in_kill_zone(check_time):
    london_start = time(2, 0)  # 2 AM EST
    london_end = time(5, 0)    # 5 AM EST
    new_york_start = time(8, 30) # 8:30 AM EST
    new_york_end = time(11, 30) # 11:30 AM EST

    current_time = check_time.time()

    if (london_start <= current_time <= london_end) or \
       (new_york_start <= current_time <= new_york_end):
        return True
    return False

def detect_liquidity_pools(df, lookback=10):
    pools = []
    
    # Calculate swing highs and lows
    for i in range(lookback, len(df) - lookback):
        high = df['High'].iloc[i]
        low = df['Low'].iloc[i]
        
        # Check for swing high (potential sell-side liquidity)
        if high > df['High'].iloc[i-lookback:i].max() and \
           high > df['High'].iloc[i+1:i+lookback+1].max():
            pools.append({
                'type': 'sell-side',
                'price': high,
                'time': df.index[i]
            })
            
        # Check for swing low (potential buy-side liquidity)
        if low < df['Low'].iloc[i-lookback:i].min() and \
           low < df['Low'].iloc[i+1:i+lookback+1].min():
            pools.append({
                'type': 'buy-side',
                'price': low,
                'time': df.index[i]
            })
    
    return pools

def detect_fvg(df):
    fvgs = []
    for i in range(len(df) - 2):
        candle1 = df.iloc[i]
        candle2 = df.iloc[i+1]
        candle3 = df.iloc[i+2]
        
        # Calculate average true range for volatility context
        atr = calculate_atr(df, period=14).iloc[i] if i >= 13 else None
        
        if atr is None:
            continue

        # Bullish FVG with minimum gap size requirement
        gap_size = candle3["Low"] - candle1["High"]
        if (candle1["High"] < candle3["Low"] and 
            candle2["Low"] > candle1["High"] and 
            candle2["High"] < candle3["Low"] and
            gap_size > 0.5 * atr):  # Minimum gap size requirement
            
            fvgs.append({
                "type": "bullish",
                "start_time": candle1.name,
                "end_time": candle3.name,
                "low": candle3["Low"],
                "high": candle1["High"],
                "gap_size": gap_size
            })
            
        # Bearish FVG with minimum gap size requirement
        gap_size = candle1["Low"] - candle3["High"]
        if (candle1["Low"] > candle3["High"] and 
            candle2["High"] < candle1["Low"] and 
            candle2["Low"] > candle3["High"] and
            gap_size > 0.5 * atr):  # Minimum gap size requirement
            
            fvgs.append({
                "type": "bearish",
                "start_time": candle1.name,
                "end_time": candle3.name,
                "low": candle3["High"],
                "high": candle1["Low"],
                "gap_size": gap_size
            })
    return fvgs

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    
    return true_range.rolling(period).mean()

def detect_order_blocks(df):
    order_blocks = []
    atr = calculate_atr(df)
    
    for i in range(1, len(df) - 1):
        prev_candle = df.iloc[i-1]
        current_candle = df.iloc[i]
        next_candle = df.iloc[i+1] if i < len(df) - 1 else None
        
        if next_candle is None:
            continue
            
        current_volume = current_candle.get('Volume', 0)
        avg_volume = df['Volume'].rolling(20).mean().iloc[i] if 'Volume' in df.columns else 0
        
        # Bullish Order Block with volume confirmation
        if (prev_candle["Close"] < prev_candle["Open"] and  # Bearish candle
            current_candle["Close"] > current_candle["Open"] and  # Bullish candle
            current_candle["Close"] > prev_candle["High"] and  # Strong momentum
            current_volume > avg_volume * 1.5 and  # Volume confirmation
            next_candle["Low"] > current_candle["Low"]):  # Price acceptance
            
            order_blocks.append({
                "type": "bullish",
                "time": prev_candle.name,
                "open": prev_candle["Open"],
                "close": prev_candle["Close"],
                "high": prev_candle["High"],
                "low": prev_candle["Low"],
                "strength": current_volume / avg_volume if avg_volume > 0 else 1
            })
            
        # Bearish Order Block with volume confirmation
        elif (prev_candle["Close"] > prev_candle["Open"] and  # Bullish candle
              current_candle["Close"] < current_candle["Open"] and  # Bearish candle
              current_candle["Close"] < prev_candle["Low"] and  # Strong momentum
              current_volume > avg_volume * 1.5 and  # Volume confirmation
              next_candle["High"] < current_candle["High"]):  # Price acceptance
            
            order_blocks.append({
                "type": "bearish",
                "time": prev_candle.name,
                "open": prev_candle["Open"],
                "close": prev_candle["Close"],
                "high": prev_candle["High"],
                "low": prev_candle["Low"],
                "strength": current_volume / avg_volume if avg_volume > 0 else 1
            })
    return order_blocks

def detect_bos(df, lookback=5):
    bos_signals = []
    atr = calculate_atr(df)
    
    for i in range(lookback, len(df)):
        current_high = df["High"].iloc[i]
        current_low = df["Low"].iloc[i]
        current_volume = df.get('Volume', pd.Series([0] * len(df))).iloc[i]
        avg_volume = df.get('Volume', pd.Series([0] * len(df))).rolling(20).mean().iloc[i]
        
        prev_high = df["High"].iloc[i-lookback:i].max()
        prev_low = df["Low"].iloc[i-lookback:i].min()
        
        # Bullish BOS with volume confirmation
        if (current_high > prev_high and 
            current_volume > avg_volume * 1.2 and  # Volume confirmation
            current_high - prev_high > 0.5 * atr.iloc[i]):  # Significant break
            
            bos_signals.append({
                "type": "bullish",
                "time": df.index[i],
                "break_level": prev_high,
                "strength": (current_high - prev_high) / atr.iloc[i]
            })
        
        # Bearish BOS with volume confirmation
        if (current_low < prev_low and 
            current_volume > avg_volume * 1.2 and  # Volume confirmation
            prev_low - current_low > 0.5 * atr.iloc[i]):  # Significant break
            
            bos_signals.append({
                "type": "bearish",
                "time": df.index[i],
                "break_level": prev_low,
                "strength": (prev_low - current_low) / atr.iloc[i]
            })
    return bos_signals

def detect_choch(df, lookback=5):
    choch_signals = []
    atr = calculate_atr(df)
    
    for i in range(lookback * 2, len(df)):
        window1 = df.iloc[i-lookback*2:i-lookback]
        window2 = df.iloc[i-lookback:i]
        current = df.iloc[i]
        
        # Calculate swing points
        swing_high1 = window1["High"].max()
        swing_low1 = window1["Low"].min()
        swing_high2 = window2["High"].max()
        swing_low2 = window2["Low"].min()
        
        # Bullish CHoCH
        if (swing_low2 < swing_low1 and  # Lower low formed
            current["Close"] > swing_high2 and  # Breaks recent swing high
            current["Close"] - swing_high2 > 0.3 * atr.iloc[i]):  # Significant break
            
            choch_signals.append({
                "type": "bullish",
                "time": df.index[i],
                "break_level": swing_high2,
                "strength": (current["Close"] - swing_high2) / atr.iloc[i]
            })
        
        # Bearish CHoCH
        elif (swing_high2 > swing_high1 and  # Higher high formed
              current["Close"] < swing_low2 and  # Breaks recent swing low
              swing_low2 - current["Close"] > 0.3 * atr.iloc[i]):  # Significant break
            
            choch_signals.append({
                "type": "bearish",
                "time": df.index[i],
                "break_level": swing_low2,
                "strength": (swing_low2 - current["Close"]) / atr.iloc[i]
            })
    
    return choch_signals

def validate_dataframe(df):
    """
    Validates that the DataFrame has the required columns and structure
    """
    required_columns = ['Open', 'High', 'Low', 'Close']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"DataFrame must contain columns: {required_columns}")
    
    # Check for NaN values
    if df[required_columns].isna().any().any():
        raise ValueError("DataFrame contains NaN values in OHLC data")
    
    # Ensure index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be DatetimeIndex")
    
    return df

def analyze_candles(df):
    """
    Analyzes price action for ICT concepts and returns all detected setups
    """
    try:
        # Validate DataFrame
        df = validate_dataframe(df)
        
        # Ensure we have enough data
        min_required_candles = 50
        if len(df) < min_required_candles:
            raise ValueError(f"Insufficient data points. Got {len(df)}, need {min_required_candles}")
        
        return {
            "liquidity_pools": detect_liquidity_pools(df),
            "fvg": detect_fvg(df),
            "order_blocks": detect_order_blocks(df),
            "bos": detect_bos(df),
            "choch": detect_choch(df)
        }
    except Exception as e:
        logger.error(f"Error in analyze_candles: {str(e)}")
        return {
            "liquidity_pools": [],
            "fvg": [],
            "order_blocks": [],
            "bos": [],
            "choch": []
        }

def calculate_risk_params(df, direction, entry_price, atr_multiple=2):
    """
    Calculates dynamic stop loss and take profit levels based on ATR
    """
    atr = calculate_atr(df).iloc[-1]
    
    if direction == "BUY":
        stop_loss = entry_price - (atr * atr_multiple)
        take_profit = entry_price + (atr * atr_multiple * 1.5)  # 1.5 risk:reward ratio
    else:  # SELL
        stop_loss = entry_price + (atr * atr_multiple)
        take_profit = entry_price - (atr * atr_multiple * 1.5)  # 1.5 risk:reward ratio
        
    return stop_loss, take_profit

def generate_signal(asset, df):
    """
    Generates trading signals based on ICT concepts
    
    Args:
        asset (str): The trading asset name
        df (pd.DataFrame): DataFrame with OHLC data
        
    Returns:
        dict: Signal information if valid signal is found, None otherwise
    """
    try:
        if not isinstance(df, pd.DataFrame):
            raise ValueError("Input must be a pandas DataFrame")
            
        if df.empty:
            raise ValueError("DataFrame is empty")
            
        if not is_in_kill_zone(datetime.now()):
            return None

        # Validate and analyze candles
        df = validate_dataframe(df)
        ict_signals = analyze_candles(df)
        
        current_price = df["Close"].iloc[-1]
        if pd.isna(current_price):
            raise ValueError("Current price is NaN")
            
        atr = calculate_atr(df).iloc[-1]
        if pd.isna(atr):
            raise ValueError("ATR calculation resulted in NaN")

        # Count and classify confluences
        bullish_count = 0
        bearish_count = 0
        confluences = []

        # Process recent signals with proper error handling
        try:
            # Analyze FVGs
            recent_fvgs = [fvg for fvg in ict_signals["fvg"] 
                        if (df.index[-1] - fvg["end_time"]).total_seconds() / 3600 <= 4]
            for fvg in recent_fvgs:
                if fvg["type"] == "bullish":
                    bullish_count += 1
                else:
                    bearish_count += 1
                confluences.append(f"FVG_{fvg['type']}")

            # Analyze Order Blocks
            recent_obs = [ob for ob in ict_signals["order_blocks"] 
                        if (df.index[-1] - ob["time"]).total_seconds() / 3600 <= 4]
            for ob in recent_obs:
                if ob["type"] == "bullish":
                    bullish_count += 1
                else:
                    bearish_count += 1
                confluences.append(f"OB_{ob['type']}")

            # Analyze BOS
            recent_bos = [bos for bos in ict_signals["bos"] 
                        if (df.index[-1] - bos["time"]).total_seconds() / 3600 <= 2]
            for bos in recent_bos:
                if bos["type"] == "bullish":
                    bullish_count += 1
                else:
                    bearish_count += 1
                confluences.append(f"BOS_{bos['type']}")

            # Analyze CHoCH
            recent_choch = [choch for choch in ict_signals["choch"] 
                          if (df.index[-1] - choch["time"]).total_seconds() / 3600 <= 2]
            for choch in recent_choch:
                if choch["type"] == "bullish":
                    bullish_count += 1
                else:
                    bearish_count += 1
                confluences.append(f"CHoCH_{choch['type']}")

        except Exception as e:
            logger.error(f"Error processing signals: {str(e)}")
            return None

        # Generate signal only if we have strong confluence
        min_confluences = 3  # Require at least 3 confluences
        if len(confluences) >= min_confluences:
            direction = "BUY" if bullish_count > bearish_count else "SELL"
            entry = current_price
            
            try:
                stop_loss, take_profit = calculate_risk_params(df, direction, entry)
                if pd.isna(stop_loss) or pd.isna(take_profit):
                    raise ValueError("Risk parameter calculation resulted in NaN")
            except Exception as e:
                logger.error(f"Error calculating risk parameters: {str(e)}")
                return None
            
            kill_zone_type = "London" if time(2,0) <= datetime.now().time() <= time(5,0) else "New York"
            setup = " + ".join(set(confluences))  # Remove duplicates
            
            # Calculate position risk based on ATR
            risk_pct = min(1.0, (abs(entry - stop_loss) / entry) * 100)  # Cap risk at 1%
            
            return {
                "asset": asset,
                "direction": direction,
                "entry": round(entry, 5),
                "stop_loss": round(stop_loss, 5),
                "take_profit": round(take_profit, 5),
                "kill_zone": kill_zone_type,
                "setup": setup,
                "risk": f"{risk_pct:.1f}%",
                "confidence": f"{max(bullish_count, bearish_count)}/{len(confluences)} confluences"
            }
    except Exception as e:
        logger.error(f"Error generating signal: {str(e)}")
        return None
    
    return None

def backtest_signal_logic(historical_data):
    signals = []
    for i in range(len(historical_data) - 2):
        df_slice = historical_data.iloc[i:i+3] # Analyze 3 candles at a time for simplicity
        signal = generate_signal("TEST_ASSET", df_slice) # Use a dummy asset name
        if signal:
            signals.append(signal)
    return signals


