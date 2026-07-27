import os
import ollama
import subprocess
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Load secrets from .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))


def list_files(directory="."):
    """List files in a given directory."""
    try:
        return os.listdir(directory)
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in a given directory on the local machine",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "The directory path to list files from, e.g. '.' or '/home/usr-01/Downloads'"
                    }
                },
                "required": []
            }
        }
    }
]

AVAILABLE_FUNCTIONS = {
    "list_files": list_files
}


# /start command — just a greeting
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_text("Hey! I'm alive and connected to your Ubuntu machine.")


# /run command — runs a shell command and returns output
async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /run <command>")
        return
    command = " ".join(context.args)
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        output = result.stdout or result.stderr or "(no output)"
        if len(output) > 3500:
            output = output[:3500] + "\n...(truncated)"
        await update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# Any plain text message — plain chat with minicpm5-1b, no tools
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    user_message = update.message.text

    response = ollama.chat(
        model="minicpm5-1b:latest",
        messages=[{"role": "user", "content": user_message}]
    )

    await update.message.reply_text(response["message"]["content"])
    # Case 1: model wants to call a tool
    if message.get("tool_calls"):
        for call in message["tool_calls"]:
            func_name = call["function"]["name"]
            func_args = call["function"]["arguments"]

            func = AVAILABLE_FUNCTIONS.get(func_name)
            if func:
                result = func(**func_args)
            else:
                result = f"Unknown tool: {func_name}"

            await update.message.reply_text(f"Ran `{func_name}` → {result}", parse_mode="Markdown")
    else:
        # Case 2: model just replied in plain text, no tool needed
        await update.message.reply_text(message["content"])


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    print("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
