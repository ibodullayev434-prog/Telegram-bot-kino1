import logging
import sqlite3
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

# ================== SOZLAMALAR ==================
BOT_TOKEN = "8701336123:AAH_r004WWwUD7W3bAAtDTHO_dWi_7EbLt8"
ADMIN_IDS = [123456789]  # O'zingizning ID
SECRET_CHANNEL_ID = -6227666140  # Maxfiy kanal ID
# ================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

# Kodlar jadvali
cursor.execute("""
CREATE TABLE IF NOT EXISTS codes (
    code TEXT PRIMARY KEY,
    message_id INTEGER,
    downloads INTEGER DEFAULT 0
)
""")

# Kanallar jadvali
cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER,
    invite_link TEXT
)
""")

conn.commit()

# ================== DB FUNKSIYALAR ==================
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
async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
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

def get_sub_keyboard():
    cursor.execute("SELECT invite_link FROM channels")
    links = cursor.fetchall()

    keyboard = []
    for (link,) in links:
        keyboard.append([InlineKeyboardButton("📢 Obuna bo‘lish", url=link)])

    keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])

    return InlineKeyboardMarkup(keyboard)

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_subscribed(user.id, context):
        await update.message.reply_text(
            "⚠️ Avval kanallarga obuna bo‘ling:",
            reply_markup=get_sub_keyboard()
        )
        return

    await update.message.reply_text("📩 Kod yuboring")

# ================== CHECK BUTTON ==================
async def check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    if await is_subscribed(user.id, context):
        await query.message.edit_text("✅ Obuna tasdiqlandi! Endi kod yuboring")
    else:
        await query.answer("❌ Hali obuna bo‘lmadingiz", show_alert=True)

# ================== INDEX POST ==================
async def index_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post

    if msg.chat_id != SECRET_CHANNEL_ID:
        return

    text = msg.caption or msg.text or ""
    match = re.search(r'#kod_(\w+)', text)

    if match:
        code = match.group(1)
        save_code(code, msg.message_id)
        logger.info(f"Saqlandi: {code}")

# ================== FOYDALANUVCHI ==================
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    code = update.message.text.strip()

    if not await is_subscribed(user.id, context):
        await update.message.reply_text(
            "⚠️ Obuna bo‘ling",
            reply_markup=get_sub_keyboard()
        )
        return

    if not re.match(r'^\w+$', code):
        await update.message.reply_text("❌ Noto‘g‘ri kod")
        return

    data = get_code(code)

    if not data:
        await update.message.reply_text("❌ Topilmadi")
        return

    message_id, downloads = data

    try:
        await context.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=SECRET_CHANNEL_ID,
            message_id=message_id
        )

        increment_download(code)

        await update.message.reply_text(
            f"📊 {downloads + 1} marta yuklangan"
        )

    except Exception as e:
        logger.error(e)
        await update.message.reply_text("⚠️ Xatolik")

# ================== ADMIN ==================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    await update.message.reply_text(
        "🔧 Admin panel:\n\n"
        "/addchannel id link\n"
        "/delchannel id\n"
        "/channels\n"
        "/stats\n"
        "/delcode 123"
    )

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if len(context.args) < 2:
        await update.message.reply_text("Format:\n/addchannel id link")
        return

    cursor.execute(
        "INSERT INTO channels (channel_id, invite_link) VALUES (?, ?)",
        (int(context.args[0]), context.args[1])
    )
    conn.commit()

    await update.message.reply_text("✅ Qo‘shildi")

async def del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cursor.execute("DELETE FROM channels WHERE channel_id=?", (int(context.args[0]),))
    conn.commit()

    await update.message.reply_text("🗑 O‘chirildi")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cursor.execute("SELECT channel_id, invite_link FROM channels")
    rows = cursor.fetchall()

    text = "📢 Kanallar:\n\n"
    for ch in rows:
        text += f"{ch[0]}\n{ch[1]}\n\n"

    await update.message.reply_text(text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cursor.execute("SELECT COUNT(*), SUM(downloads) FROM codes")
    data = cursor.fetchone()

    await update.message.reply_text(
        f"📦 Kodlar: {data[0]}\n📥 Yuklashlar: {data[1] or 0}"
    )

async def del_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    code = context.args[0]

    cursor.execute("DELETE FROM codes WHERE code=?", (code,))
    conn.commit()

    await update.message.reply_text("🗑 O‘chirildi")

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("delchannel", del_channel))
    app.add_handler(CommandHandler("channels", list_channels))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("delcode", del_code))

    app.add_handler(CallbackQueryHandler(check_sub, pattern="check_sub"))

    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, index_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()