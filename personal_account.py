import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

# Настройка логирования
logger = logging.getLogger(__name__)

# Глобальные переменные для подключения к базе данных
conn = None
cursor = None

def initialize_db(connection, db_cursor):
    global conn, cursor
    conn = connection
    cursor = db_cursor

# Функция для определения знака зодиака
def get_zodiac_sign(day, month):
    zodiac_signs = [
        (120, 'Козерог'), (219, 'Водолей'), (321, 'Рыбы'), (420, 'Овен'),
        (521, 'Телец'), (621, 'Близнецы'), (723, 'Рак'), (823, 'Лев'),
        (923, 'Дева'), (1023, 'Весы'), (1122, 'Скорпион'), (1222, 'Стрелец'), (1231, 'Козерог')
    ]
    date = month * 100 + day
    for zodiac_date, zodiac_name in zodiac_signs:
        if date <= zodiac_date:
            return zodiac_name
    return 'Козерог'

# Главная клавиатура с проверкой подписки
def main_menu_keyboard(user_id):
    buttons = [
        ['🃏 Карта дня', '📜 История'],
        ['📰 Новости', '⚙️ Настройки']
    ]

    cursor.execute("SELECT 1 FROM subscriptions WHERE user_id = ?", (user_id,))
    is_premium = cursor.fetchone()

    if not is_premium:
        buttons.append(['💎 Премиум-доступ'])

    buttons.append(['👤 Личный кабинет'])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# Функция личного кабинета
async def personal_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global conn, cursor
    user = update.message.from_user
    logger.info(f"Пользователь {user.username} ({user.id}) запросил личный кабинет.")

    cursor.execute("""
        SELECT nickname, birth_date, zodiac_sign,
               total_cards, straight_cards, reversed_cards,
               consecutive_days
        FROM users WHERE user_id = ?
    """, (user.id,))
    user_data = cursor.fetchone()

    if user_data:
        nickname, birth_date, zodiac_sign, total_cards, straight_cards, reversed_cards, consecutive_days = user_data

        # Проверка подписки
        cursor.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user.id,))
        subscription = cursor.fetchone()
        if subscription:
            expires_at = subscription[0]
            sub_status = f"✅ Премиум до {expires_at}"
        else:
            sub_status = "🔒 Без подписки"

        await update.message.reply_text(
            f"👤 *Ваш профиль:*\n"
            f"Никнейм: {nickname}\n"
            f"Дата рождения: {birth_date}\n"
            f"Знак зодиака: {zodiac_sign}\n"
            f"ID: {user.id}\n\n"
            f"📊 *Статистика:*\n"
            f"Получено карт: {total_cards}\n"
            f"Прямых карт: {straight_cards}\n"
            f"Перевёрнутых карт: {reversed_cards}\n"
            f"Дней подряд: {consecutive_days}\n\n"
            f"💼 *Подписка:* {sub_status}",
            reply_markup=main_menu_keyboard(user.id),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "Вы ещё не настроили свой профиль. Используйте команду /start.",
            reply_markup=main_menu_keyboard(user.id)
        )
