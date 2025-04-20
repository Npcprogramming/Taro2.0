import logging
import os
import sqlite3
import pytz
import types
from datetime import datetime, time, timedelta

from telegram import Update, ReplyKeyboardRemove, InputFile, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

from config import TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_IDS  # Список ID админов
from ai_utils import get_ai_description
from personal_account import (
    personal_account,
    get_zodiac_sign,
    initialize_db as initialize_personal_account_db,
)
from menu_functions import (
    daily_card,
    send_news,
    show_history,
    subscribe,
    help_command,
    settings_menu,
    settings_menu_keyboard,
    main_menu,
    handle_message,
    request_feedback,
    initialize_menu_functions
)
from card_search import (
    start_card_search,
    handle_suit_selection,
    handle_card_selection
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logs_dir = os.path.join(BASE_DIR, 'logs')
os.makedirs(logs_dir, exist_ok=True)

current_date = datetime.now().strftime('%d.%m.%Y')
log_file = os.path.join(logs_dir, f'bot_log_{current_date}.log')

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

conn = sqlite3.connect('user_data.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        user_id INTEGER,
        date TEXT,
        card TEXT,
        is_reversed INTEGER,
        type TEXT DEFAULT 'daily_card'
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id INTEGER PRIMARY KEY,
        expires_at TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        nickname TEXT,
        birth_date TEXT,
        zodiac_sign TEXT,
        avatar TEXT,
        total_cards INTEGER DEFAULT 0,
        straight_cards INTEGER DEFAULT 0,
        reversed_cards INTEGER DEFAULT 0,
        consecutive_days INTEGER DEFAULT 0,
        last_card_date TEXT
    )
''')

# Добавление колонки expires_at, если её нет
try:
    cursor.execute("ALTER TABLE subscriptions ADD COLUMN expires_at TEXT")
except sqlite3.OperationalError:
    pass

conn.commit()
initialize_personal_account_db(conn, cursor)
initialize_menu_functions(conn, cursor, BASE_DIR)

ASK_NICKNAME, ASK_BIRTHDATE = range(2)

def main_menu_keyboard(user_id=None):
    buttons = [
        ['🃏 Карта дня', '📜 История'],
        ['📰 Новости', '⚙️ Настройки'],
        ['🔍 Поиск карты']  
    ]
    if user_id:
        cursor.execute("SELECT 1 FROM subscriptions WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            buttons.append(['💎 Премиум-доступ'])
    else:
        buttons.append(['💎 Премиум-доступ'])
    buttons.append(['👤 Личный кабинет'])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"Пользователь {user.username} ({user.id}) вызвал команду /start.")
    context.user_data.setdefault('daily_card_date', None)
    context.user_data['BASE_DIR'] = BASE_DIR

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    user_data = cursor.fetchone()

    if user_data is None:
        await update.message.reply_text("Здравствуйте! Давайте настроим ваш профиль.",
                                        reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Введите ваш желаемый никнейм:")
        return ASK_NICKNAME
    else:
        await update.message.reply_text(
            f"С возвращением, {user_data[1]}!",
            reply_markup=main_menu_keyboard(user.id)
        )
        return ConversationHandler.END

async def ask_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nickname'] = update.message.text.strip()
    await update.message.reply_text("Введите вашу дату рождения в формате ДД.ММ.ГГГГ:")
    return ASK_BIRTHDATE

async def save_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    birthdate_str = update.message.text.strip()
    try:
        birthdate = datetime.strptime(birthdate_str, "%d.%m.%Y")
        zodiac_sign = get_zodiac_sign(birthdate.day, birthdate.month)
        nickname = context.user_data['nickname']
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, nickname, birth_date, zodiac_sign) VALUES (?, ?, ?, ?)",
            (user.id, nickname, birthdate_str, zodiac_sign)
        )
        conn.commit()
        await update.message.reply_text(
            f"Профиль сохранён!\nНик: {nickname}\nДата: {birthdate_str}\nЗнак: {zodiac_sign}",
            reply_markup=main_menu_keyboard(user.id)
        )
    except ValueError:
        await update.message.reply_text("Неверный формат. Попробуйте ДД.ММ.ГГГГ.")
        return ASK_BIRTHDATE
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    await update.message.reply_text("Отменено.", reply_markup=main_menu_keyboard(user.id))
    return ConversationHandler.END

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    feedback_text = ' '.join(context.args)
    if feedback_text:
        await context.bot.send_message(ADMIN_TELEGRAM_IDS[0], text=f"Отзыв от {user.username} ({user.id}):\n{feedback_text}")
        await update.message.reply_text("Спасибо за отзыв!")
    else:
        await update.message.reply_text("Введите текст после команды /feedback")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    await update.message.reply_text("Неизвестная команда. Используйте меню.", reply_markup=main_menu_keyboard(user.id))

async def send_daily_cards(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()
    cursor.execute("SELECT user_id, expires_at FROM subscriptions")
    for user_id, expires_at in cursor.fetchall():
        if expires_at and datetime.strptime(expires_at, "%Y-%m-%d").date() >= today:
            class DummyMessage:
                def __init__(self, user_id):
                    self.chat_id = user_id
                    self.from_user = types.SimpleNamespace(id=user_id, username='', first_name='')
                    self.message_id = None
                    self.text = ''
            dummy_update = Update(update_id=0, message=DummyMessage(user_id))
            await daily_card(dummy_update, context)

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "💎 *Премиум-доступ к AI-советам*\n\n"
        "Получите эксклюзивные советы от искусственного интеллекта 🧠\n\n"
        "💳 *Цена*: 499 руб\n"
        "Перевод на карту: `4276 5600 1773 5988`\n\n"
        "После оплаты отправьте чек 📸. Админ активирует доступ вручную.\n"
        "_Для связи: @looperproper_"
    )
    await update.message.reply_text(message, parse_mode='Markdown')

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_path = f"payment_proof_{user.id}.jpg"
        await file.download_to_drive(file_path)
        caption = f"🧾 Чек от @{user.username or 'user'} (ID: {user.id})\n👉 /activate {user.id}"
        await context.bot.send_photo(chat_id=ADMIN_TELEGRAM_IDS[0], photo=InputFile(file_path), caption=caption)
        await update.message.reply_text("✅ Чек отправлен. Ждите подтверждения.")
    else:
        await update.message.reply_text("⚠️ Пожалуйста, отправьте скриншот чека как фото.")

async def activate_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_TELEGRAM_IDS:
        await update.message.reply_text("⛔ Недостаточно прав.")
        return
    if context.args:
        try:
            user_id = int(context.args[0])
            expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO subscriptions (user_id, expires_at)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET expires_at = excluded.expires_at
            """, (user_id, expires_at))
            conn.commit()
            await update.message.reply_text(f"✅ Премиум активирован до {expires_at}")
            await context.bot.send_message(user_id, text=f"🎉 Ваша премиум-подписка активирована до {expires_at}")
        except Exception as e:
            logger.error(f"Ошибка активации премиума: {e}")
            await update.message.reply_text("❌ Ошибка при активации.")
    else:
        await update.message.reply_text("Используйте: /activate <user_id>")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_TELEGRAM_IDS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    cursor.execute("SELECT users.user_id, nickname, zodiac_sign, expires_at FROM users JOIN subscriptions ON users.user_id = subscriptions.user_id ORDER BY expires_at DESC")
    users = cursor.fetchall()
    if not users:
        await update.message.reply_text("Нет активных подписчиков.")
        return
    message = "📋 Подписчики:\n\n"
    for uid, nick, sign, expires in users:
        message += f"👤 {nick} | ID: {uid}\n♈ Знак: {sign} | до: {expires}\n\n"
    await update.message.reply_text(message)

def main():
    try:
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        logger.info("Бот запущен.")

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                ASK_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_birthdate)],
                ASK_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_profile)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        app.add_handler(conv_handler)
        app.add_handler(CommandHandler('help', help_command))
        app.add_handler(CommandHandler('history', show_history))
        app.add_handler(CommandHandler('subscribe', subscribe))
        app.add_handler(CommandHandler('feedback', feedback))
        app.add_handler(CommandHandler('premium', premium_command))
        app.add_handler(CommandHandler('activate', activate_premium))
        app.add_handler(CommandHandler('adminpanel', admin_panel))
        app.add_handler(MessageHandler(filters.PHOTO, handle_payment_proof))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex('^🔍 Поиск карты$'), start_card_search))
        app.add_handler(CallbackQueryHandler(handle_suit_selection, pattern='^suit_'))
        app.add_handler(CallbackQueryHandler(handle_card_selection, pattern='^card_'))

        target_time = time(hour=12, minute=0, tzinfo=pytz.timezone('Europe/Moscow'))
        app.job_queue.run_daily(send_daily_cards, time=target_time)

        app.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")

if __name__ == '__main__':
    main()
