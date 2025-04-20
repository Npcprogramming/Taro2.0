import os
import logging
from datetime import datetime
import random
import datetime as dt

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from cards_data import cards
from personal_account import (
    get_zodiac_sign,
    main_menu_keyboard
)
from ai_utils import get_ai_description

logger = logging.getLogger(__name__)

conn = None
cursor = None
BASE_DIR = None

def initialize_menu_functions(connection, db_cursor, base_directory):
    global conn, cursor, BASE_DIR
    conn = connection
    cursor = db_cursor
    BASE_DIR = base_directory

async def daily_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global conn, cursor, BASE_DIR
    user = update.message.from_user
    logger.info(f"Пользователь {user.username} ({user.id}) запросил карту дня.")

    now = dt.datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    last_draw_date_str = context.user_data.get('daily_card_date')

    if last_draw_date_str == today_str:
        await update.message.reply_text("Вы уже получали карту на сегодня. Возвращайтесь завтра!")
        return

    cursor.execute(
        "SELECT nickname, zodiac_sign, total_cards, straight_cards, reversed_cards, consecutive_days, last_card_date "
        "FROM users WHERE user_id = ?",
        (user.id,)
    )
    user_data = cursor.fetchone()
    if user_data:
        nickname, zodiac_sign, total_cards, straight_cards, reversed_cards, consecutive_days, last_card_date = user_data
    else:
        nickname = user.first_name
        zodiac_sign = None
        total_cards = 0
        straight_cards = 0
        reversed_cards = 0
        consecutive_days = 0
        last_card_date = None

    card = random.choice(list(cards.keys()))
    card_info = cards[card]
    is_reversed = random.choice([True, False])
    image_path = os.path.join(BASE_DIR, 'images', card_info['image_file'])

    if last_card_date:
        last_date = datetime.strptime(last_card_date, '%Y-%m-%d')
        delta = now.date() - last_date.date()
        if delta.days == 1:
            consecutive_days += 1
        else:
            consecutive_days = 1
    else:
        consecutive_days = 1

    total_cards += 1
    if is_reversed:
        reversed_cards += 1
    else:
        straight_cards += 1

    last_card_date_str = now.strftime('%Y-%m-%d')
    cursor.execute(
        "UPDATE users SET total_cards = ?, straight_cards = ?, reversed_cards = ?, consecutive_days = ?, last_card_date = ? "
        "WHERE user_id = ?",
        (total_cards, straight_cards, reversed_cards, consecutive_days, last_card_date_str, user.id)
    )
    conn.commit()

    position = "Перевёрнутая" if is_reversed else "Прямая"
    description = card_info.get('reversed_description') if is_reversed else card_info.get('description')
    advice = card_info.get('advice', '')

    # Проверка подписки
    cursor.execute("SELECT 1 FROM subscriptions WHERE user_id = ?", (user.id,))
    is_premium = cursor.fetchone() is not None

    # Генерация AI-совета или fallback
    if is_premium:
        try:
            ai_text = await get_ai_description(card, card_info, zodiac_sign, is_reversed)
        except Exception as e:
            logger.error(f"Ошибка при генерации AI-совета: {e}")
            ai_text = f"⚠️ Не удалось получить совет от AI.\n\n💡 Совет по карте: {advice}"
        caption = (
            f"🃏 {nickname}, ваша карта дня: {card} ({position})\n\n"
            f"🤖 *AI-совет:*\n{ai_text}\n\n"
            f"✨ Получено по премиум-доступу"
        )
    else:
        caption = (
            f"🃏 {nickname}, ваша карта дня: {card} ({position})\n\n"
            f"💬 *Значение:*\n{description}\n\n"
            f"💡 *Совет:*\n{advice}\n\n"
            f"🔒 Получите персональный AI-совет, оформив премиум-подписку."
        )

    context.user_data['daily_card_date'] = today_str
    context.user_data['daily_card'] = {
        'card': card,
        'date': now.strftime('%Y-%m-%d %H:%M:%S'),
        'is_reversed': is_reversed
    }

    try:
        cursor.execute(
            "INSERT INTO history (user_id, date, card, is_reversed, type) VALUES (?, ?, ?, ?, ?)",
            (user.id, now.strftime('%Y-%m-%d %H:%M:%S'), card, int(is_reversed), 'daily_card')
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка при сохранении истории: {e}")

    # Отправка изображения и текста
    if os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await update.message.reply_photo(photo=photo)
        await update.message.reply_text(caption, parse_mode='Markdown')
    else:
        await update.message.reply_text(caption, parse_mode='Markdown')


async def send_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    news_message = (
        "📰 Последние новости Таро:\n\n"
        "- Новая статья о значении карт.\n"
        "- Советы по раскладам.\n"
        "- И многое другое!"
    )
    await update.message.reply_text(news_message)

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    try:
        cursor.execute(
            "SELECT date, card, is_reversed FROM history WHERE user_id = ? ORDER BY date DESC LIMIT 30",
            (user.id,)
        )
        rows = cursor.fetchall()
        if rows:
            text = "📜 Ваша история карт:\n\n"
            for date_str, card_name, is_rev in rows:
                pos = "Перевёрнутая" if is_rev else "Прямая"
                advice = cards.get(card_name, {}).get('advice', '')
                text += f"{date_str} | {card_name} ({pos}) | {advice}\n"
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("У вас пока нет истории карт.")
    except Exception as e:
        logger.error(f"Ошибка при получении истории: {e}")
        await update.message.reply_text("Произошла ошибка при получении истории.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    try:
        cursor.execute("INSERT OR IGNORE INTO subscriptions (user_id) VALUES (?)", (user.id,))
        conn.commit()
        await update.message.reply_text("✅ Вы подписались на ежедневные уведомления.")
    except Exception as e:
        logger.error(f"Ошибка при подписке: {e}")
        await update.message.reply_text("Ошибка при подписке.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Доступные команды:\n"
        "/start – Начать\n"
        "/help – Помощь\n"
        "/history – История карт\n"
        "/subscribe – Подписка\n"
        "/feedback – Отзыв\n"
        "/premium – Оформить премиум\n"
               "🧭 Используйте кнопки меню для удобства."
    )

def settings_menu_keyboard():
    return ReplyKeyboardMarkup([
        ['🔔 Подписаться', '❓ Помощь'],
        ['✉️ Отзыв'], ['⬅️ Назад']
    ], resize_keyboard=True)

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ Настройки:", reply_markup=settings_menu_keyboard())

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Главное меню:", reply_markup=main_menu_keyboard())

async def request_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✉️ Пожалуйста, отправьте отзыв командой:\n/feedback [текст]")

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '🃏 Карта дня':
        await daily_card(update, context)
    elif text == '📜 История':
        await show_history(update, context)
    elif text == '📰 Новости':
        await send_news(update, context)
    elif text == '⚙️ Настройки':
        await settings_menu(update, context)
    elif text == '⬅️ Назад':
        await main_menu(update, context)
    elif text == '🔔 Подписаться':
        await subscribe(update, context)
    elif text == '❓ Помощь':
        await help_command(update, context)
    elif text == '✉️ Отзыв':
        await request_feedback(update, context)
    elif text == '👤 Личный кабинет':
        from personal_account import personal_account
        await personal_account(update, context)
    elif text == '🔍 Поиск карты':
        from card_search import start_card_search
        await start_card_search(update, context)
    elif text == '💎 Премиум-доступ':
        await premium_command(update, context)
    else:
        await update.message.reply_text("🤖 Я не понял команду. Используйте меню.", reply_markup=main_menu_keyboard())
