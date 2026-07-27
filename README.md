# my-agent

A Telegram bot running on Ubuntu that can execute basic commands remotely.

## Setup
1. Create a virtual environment: `python3 -m venv venv`
2. Activate it: `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Create a `.env` file with:

TELEGRAM_BOT_TOKEN=your_token_here
ALLOWED_USER_ID=your_telegram_user_id

5. Run: `python bot.py`
