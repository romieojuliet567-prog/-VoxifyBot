import os
import logging
import re
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from gtts import gTTS

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Language & Voice Options (gTTS supported) ---
LANGUAGES = {
    "en": "🇬🇧 English",
    "es": "🇪🇸 Spanish",
    "fr": "🇫🇷 French",
    "de": "🇩🇪 German",
    "it": "🇮🇹 Italian",
    "pt": "🇵🇹 Portuguese",
    "ru": "🇷🇺 Russian",
    "ja": "🇯🇵 Japanese",
    "ko": "🇰🇷 Korean",
    "hi": "🇮🇳 Hindi",
}

# Speed options
SPEEDS = {
    "normal": ("Normal Speed", False),
    "slow": ("Slow Speed", True),
}

# --- User Session State (simple in-memory) ---
user_state = {}


def get_user_state(user_id):
    if user_id not in user_state:
        user_state[user_id] = {"lang": "en", "slow": False, "last_text": None}
    return user_state[user_id]


def split_text(text, max_len=500):
    """Split long text into manageable chunks for gTTS."""
    if len(text) <= max_len:
        return [text]
    # Split at sentence boundaries if possible
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_len:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks if chunks else [text[:max_len]]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with main menu."""
    user = update.effective_user
    state = get_user_state(user.id)

    keyboard = [
        [InlineKeyboardButton("🌍 Change Language", callback_data="menu_lang")],
        [InlineKeyboardButton("🎚️ Speed Settings", callback_data="menu_speed")],
        [InlineKeyboardButton("📜 My History", callback_data="menu_history")],
        [InlineKeyboardButton("ℹ️ About", callback_data="menu_about")],
        [InlineKeyboardButton("🆘 Help", callback_data="menu_help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        f"Welcome to **Voxify** — your text-to-voice converter.\n\n"
        f"Simply send me any text, and I'll turn it into natural-sounding speech.\n\n"
        f"**Current Settings:**\n"
        f"🌍 Language: {LANGUAGES.get(state['lang'], 'English')}\n"
        f"🎚️ Speed: {'Slow' if state['slow'] else 'Normal'}\n\n"
        f"Use the menu below to change settings:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle menu button clicks."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    state = get_user_state(user_id)

    if query.data == "menu_lang":
        keyboard = []
        for code, name in LANGUAGES.items():
            keyboard.append([InlineKeyboardButton(name, callback_data=f"set_lang_{code}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="menu_back")])
        await query.edit_message_text(
            "🌍 **Choose a language:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data.startswith("set_lang_"):
        code = query.data.replace("set_lang_", "")
        if code in LANGUAGES:
            state["lang"] = code
            await query.edit_message_text(
                f"✅ Language set to **{LANGUAGES[code]}**.\n\nSend me text to convert!",
                parse_mode="Markdown"
            )
            await start(update, context)

    elif query.data == "menu_speed":
        keyboard = [
            [InlineKeyboardButton("⚡ Normal Speed", callback_data="set_speed_normal")],
            [InlineKeyboardButton("🐢 Slow Speed", callback_data="set_speed_slow")],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu_back")],
        ]
        await query.edit_message_text(
            "🎚️ **Choose speech speed:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data.startswith("set_speed_"):
        speed = query.data.replace("set_speed_", "")
        if speed in SPEEDS:
            state["slow"] = SPEEDS[speed][1]
            await query.edit_message_text(
                f"✅ Speed set to **{SPEEDS[speed][0]}**.\n\nSend me text to convert!",
                parse_mode="Markdown"
            )

    elif query.data == "menu_history":
        if state["last_text"]:
            await query.edit_message_text(
                f"📜 **Your Last Text:**\n\n_{state['last_text'][:300]}_",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "📜 **No history yet.**\n\nSend me some text to get started!",
                parse_mode="Markdown"
            )

    elif query.data == "menu_about":
        await query.edit_message_text(
            "ℹ️ **About Voxify**\n\n"
            "Voxify is a free text-to-speech bot that converts your text into natural-sounding audio.\n\n"
            "**Features:**\n"
            "• Multiple languages\n"
            "• Adjustable speed\n"
            "• Long text support\n"
            "• Audio download\n\n"
            "No account needed. Just send text.",
            parse_mode="Markdown"
        )

    elif query.data == "menu_help":
        await query.edit_message_text(
            "🆘 **How to use Voxify:**\n\n"
            "1️⃣ Send me any text message\n"
            "2️⃣ I'll convert it to voice\n"
            "3️⃣ You'll receive an audio file\n\n"
            "**Commands:**\n"
            "/start - Main menu\n"
            "/lang - Change language\n"
            "/speed - Change speed\n"
            "/history - View last text\n"
            "/about - About this bot",
            parse_mode="Markdown"
        )

    elif query.data == "menu_back":
        await start(update, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert user text to speech."""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    text = update.message.text.strip()

    if not text:
        return

    # Save history
    state["last_text"] = text

    # Send processing message
    processing_msg = await update.message.reply_text("🎙️ Generating voice...")

    try:
        # Split long text
        chunks = split_text(text, max_len=500)

        for i, chunk in enumerate(chunks):
            tts = gTTS(text=chunk, lang=state["lang"], slow=state["slow"])
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)

            filename = f"voice_{i+1}.mp3" if len(chunks) > 1 else "voice.mp3"
            await update.message.reply_voice(
                voice=InputFile(audio_buffer, filename=filename),
                caption=f"🔊 Part {i+1}/{len(chunks)}" if len(chunks) > 1 else "🔊 Here's your voice message!",
            )

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"TTS error: {e}")
        await processing_msg.edit_text(
            "❌ Sorry, I couldn't generate the voice. Please try again with shorter text."
        )


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick language selection."""
    keyboard = []
    for code, name in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"set_lang_{code}")])
    await update.message.reply_text(
        "🌍 **Choose a language:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def speed_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick speed selection."""
    keyboard = [
        [InlineKeyboardButton("⚡ Normal Speed", callback_data="set_speed_normal")],
        [InlineKeyboardButton("🐢 Slow Speed", callback_data="set_speed_slow")],
    ]
    await update.message.reply_text(
        "🎚️ **Choose speech speed:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show last text."""
    state = get_user_state(update.effective_user.id)
    if state["last_text"]:
        await update.message.reply_text(
            f"📜 **Your Last Text:**\n\n_{state['last_text'][:500]}_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("📜 No history yet.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error("Exception while handling an update:", exc_info=context.error)


def main() -> None:
    """Start the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        return

    application = Application.builder().token(token).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("lang", lang_command))
    application.add_handler(CommandHandler("speed", speed_command))
    application.add_handler(CommandHandler("history", history_command))

    # Callback query handler
    application.add_handler(CallbackQueryHandler(menu_callback))

    # Text message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Error handler
    application.add_error_handler(error_handler)

    logger.info("Starting @VoxifyBot with long polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
