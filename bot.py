import os
import json
import subprocess
from dotenv import load_dotenv
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Load secrets from .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = (
    "You are a helpful assistant controlling a local Ubuntu machine via defined tools. "
    "When the user asks something that requires checking the system (files, disk space, "
    "processes, uptime, etc.), call the appropriate tool with correctly structured arguments. "
    "Do not write out a function call as plain text — always use the proper tool-calling mechanism. "
    "If no tool is needed, just reply normally in plain text."
)


def list_files(directory="."):
    """List files in a given directory."""
    try:
        return os.listdir(directory)
    except Exception as e:
        return f"Error: {e}"


DANGEROUS_PATTERNS = ["rm ", "mv ", "shutdown", "reboot", "dd ", "> /dev", "mkfs", ":(){:|:&};:"]

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
                        "description": "The directory path to list, e.g. '.', '/home/usr-01/Downloads'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command on the local Ubuntu machine and return its output",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact shell command to run, e.g. 'df -h' or 'uptime'"
                    }
                },
                "required": ["command"]
            }
        }
    }
]

AVAILABLE_FUNCTIONS = {
    "list_files": list_files
}


def call_groq(user_message):
    """Calls Groq with tools enabled. Retries once if the model malforms a tool call."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    for attempt in range(2):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=TOOLS,
                max_tokens=300
            )
            return response.choices[0].message
        except Exception as e:
            if "tool_use_failed" in str(e) and attempt == 0:
                continue  # retry once
            raise
    return None


# /start command — just a greeting
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_text("Hey! I'm alive and connected to your Ubuntu machine.")


# /run command — full shell access, with a confirm step for destructive stuff
async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /run <command>")
        return

    command = " ".join(context.args)

    if any(pattern in command for pattern in DANGEROUS_PATTERNS):
        context.user_data["pending_command"] = command
        await update.message.reply_text(
            f"This looks destructive:\n```\n{command}\n```\nReply /confirm to run it anyway, or ignore to cancel.",
            parse_mode="Markdown"
        )
        return

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        output = result.stdout or result.stderr or "(no output)"
        if len(output) > 3500:
            output = output[:3500] + "\n...(truncated)"
        await update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# /confirm — actually runs a command flagged as destructive
async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    command = context.user_data.pop("pending_command", None)
    if not command:
        await update.message.reply_text("Nothing pending to confirm.")
        return
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        output = result.stdout or result.stderr or "(no output)"
        if len(output) > 3500:
            output = output[:3500] + "\n...(truncated)"
        await update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# Any plain text message — routed through Groq, with tool-calling access
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    user_message = update.message.text

    try:
        message = call_groq(user_message)

        if message is None:
            await update.message.reply_text("Couldn't get a valid response, try rephrasing.")
            return

        if message.tool_calls:
            for call in message.tool_calls:
                func_name = call.function.name
                func_args = json.loads(call.function.arguments)

                if func_name == "run_shell":
                    command = func_args.get("command", "")
                    if any(pattern in command for pattern in DANGEROUS_PATTERNS):
                        context.user_data["pending_command"] = command
                        await update.message.reply_text(
                            f"This looks destructive:\n```\n{command}\n```\nReply /confirm to run it anyway, or ignore to cancel.",
                            parse_mode="Markdown"
                        )
                        continue
                    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
                    output = result.stdout or result.stderr or "(no output)"
                    await update.message.reply_text(f"```\n{output[:3500]}\n```", parse_mode="Markdown")

                elif func_name in AVAILABLE_FUNCTIONS:
                    result = AVAILABLE_FUNCTIONS[func_name](**func_args)
                    await update.message.reply_text(str(result))

                else:
                    await update.message.reply_text(f"Unknown tool: {func_name}")
        else:
            reply_text = message.content or "(no response generated)"
            await update.message.reply_text(reply_text)

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("confirm", confirm_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    print("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
