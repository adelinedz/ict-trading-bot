# ICT Trading Bot

A trading bot that implements ICT (Inner Circle Trader) concepts to generate trading signals via Telegram.

## Features

- Liquidity pool detection
- Volume confirmation for order blocks
- ATR-based validation for Fair Value Gaps (FVGs)
- Break of Structure (BOS) and Change of Character (CHoCH) detection
- Dynamic risk management
- Real-time signal generation
- Telegram notifications
- Market hours validation
- Signal persistence and duplicate detection

## Deployment Instructions

### GitHub Setup

1. Create a new GitHub repository
2. Clone the repository locally
3. Copy all project files to the repository
4. Push to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin your-repo-url
   git push -u origin main
   ```

### Render Deployment

1. Sign up for a [Render](https://render.com) account
2. Connect your GitHub repository to Render
3. Create a new "Background Worker" service
4. Select your repository and branch
5. The service will automatically use the `render.yaml` configuration

### Environment Variables

Set the following environment variables in Render dashboard:

- `BOT_TOKEN`: Your Telegram bot token (7658645448:AAEsXo8qor9ffWaV9pOo3jeDRXKaCas4JbM)
- `CHAT_ID`: Your Telegram chat ID (1160437891)
- `LOG_LEVEL`: Logging level (default: INFO)
- `MAX_MEMORY_MB`: Maximum memory usage (default: 500)
- `SIGNAL_EXPIRY_HOURS`: Hours before signal expiry (default: 4)

## Local Development

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the required environment variables
4. Run the bot:
   ```bash
   python main.py
   ```

## Monitoring

- Check the Render dashboard for logs and performance metrics
- Monitor Telegram for signal notifications
- Check the logs directory for detailed logging information

## Support

For issues and feature requests, please create an issue in the GitHub repository.

## Project Structure

```
/ict_bot
├─ main.py                 # Runs analysis loop
├─ signal_engine.py        # Detects ICT setups
├─ market_data.py          # Pulls live price data
├─ telegram_notifier.py    # Sends signals to Telegram
├─ utils.py                # Common helpers
└─ .env                    # Secrets (bot token + chat ID)
```

## Test Mode

To send a test message to your Telegram chat, run:

```bash
python telegram_notifier.py
```

## Backtest Mode

To run the backtest mode, you can call the `backtest_signal_logic` function from `signal_engine.py` with historical data. An example is provided within `signal_engine.py`.

## Important Notes

- The ICT concept detection logic is a simplified implementation for demonstration purposes. For real-world trading, these algorithms would require significant refinement and validation.
- The bot runs every 5 minutes during specified kill zones. Ensure your system clock is accurate and synchronized.
- Risk management parameters (Entry, Stop Loss, Take Profit, Risk) are placeholders and should be adjusted based on your trading strategy.


