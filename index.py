import logging
import sqlite3
import re
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

# ================== ENV ==================
BOT_TOKEN = os.getenv("8701336123:AAH_r004WWwUD7W3bAAtDTHO_dWi_7EbLt8")
ADMIN_IDS = [int(x) for x in os.getenv("6227666140", "").split(",") if x]

SECRET_CHANNEL_ID = int(os.getenv("3724385902"))

# ================== LOG ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS codes (
    code TEXT PRIMARY KEY,
    message_id INTEGER,
    downloads INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER,
    invite_link TEXT
)
""")

conn.commit()

# ================== DB ==================
def save_code(code, message_id):
    cursor.execute(
        "INSERT OR REPLACE INTO codes (code, message_id, downloads) VALUES (?, ?, COALESCE((SELECT downloads FROM codes WHERE code=?),0))",
        (code, message_id, code)
    )
    conn.commit()

def get_code(code):
    cursor.execute("SELECT message_id, downloads FROM codes WHERE code=?", (code,))
    return cursor.fetchone()

def increment_download(code):
    cursor.execute("UPDATE codes SET downloads = downloads + 1 WHERE code=?", (code,))
    conn.commit()

# ================== OBUNA ==================
async def is_subscribed(user_id, context):
    cursor.execute("SELECT channel_id FROM channels")
    channels = cursor.fetchall()

    if not channels:
        return True

    for (channel_id,) in channels:
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False

    return True

def get_keyboard():
    cursor.execute("SELECT invite_link FROM channels")
    links = cursor.fetchall()

    keyboard = []
    for (link,) in links:
        keyboard.append([InlineKeyboardButton("📢 Obuna bo‘lish", url=link)])

    keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check")])

    return InlineKeyboardMarkup(keyboard)

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update.effective_user.id, context):
        await update.message.reply_text("⚠️ Obuna bo‘ling:", reply_markup=get_keyboard())
        return

    await update.message.reply_text("📩 Kod yuboring")

# ================== CHECK ==================
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await is_subscribed(query.from_user.id, context):
        await query.message.edit_text("✅ Obuna tasdiqlandi!")
    else:
        await query.answer("❌ Hali obuna emassiz", show_alert=True)

# ================== INDEX ==================
async def index_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if msg.chat_id != SECRET_CHANNEL_ID:
        return

    text = msg.caption or msg.text or ""
    match = re.search(r'#kod_(\w+)', text)

    if match:
        save_code(match.group(1), msg.message_id)

# ================== USER ==================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    code = update.message.text.strip()

    if not await is_subscribed(user.id, context):
        await update.message.reply_text("⚠️ Obuna bo‘ling", reply_markup=get_keyboard())
        return

    data = get_code(code)
    if not data:
        await update.message.reply_text("❌ Topilmadi")
        return

    message_id, downloads = data

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=SECRET_CHANNEL_ID,
        message_id=message_id
    )

    increment_download(code)

    await update.message.reply_text(f"📊 {downloads+1} marta yuklangan")

# ================== ADMIN ==================
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    ch_id = int(context.args[0])
    link = context.args[1]

    cursor.execute("INSERT INTO channels (channel_id, invite_link) VALUES (?,?)", (ch_id, link))
    conn.commit()

    await update.message.reply_text("✅ Qo‘shildi")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    cursor.execute("SELECT COUNT(*), SUM(downloads) FROM codes")
    data = cursor.fetchone()

    await update.message.reply_text(f"📦 {data[0]} kod\n📥 {data[1] or 0} yuklash")

# ================== WEB SERVER ==================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ishlayapti")

def run_web():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# ================== MAIN ==================
def main():
    threading.Thread(target=run_web).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("addchannel", add_channel))

    app.add_handler(CallbackQueryHandler(check, pattern="check"))

    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, index_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()