import os
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import ContextTypes

# Предполагаем, что в cards_data.py у вас есть словарь "cards":
# cards = {
#   "Туз Пентаклей": {
#       "description": "...",
#       "advice": "...",
#       "image_file": "tuz_pentakley.jpg"
#   },
#   ...
# }
from cards_data import cards

logger = logging.getLogger(__name__)

# Список мастей и входящих в них карт
SUITS = {
    "Major": [
        "Шут", "Маг", "Жрица", "Императрица", "Император", "Верховный жрец",
        "Влюблённые", "Колесница", "Справедливость", "Отшельник",
        "Колесо Фортуны", "Сила", "Повешенный", "Смерть", "Умеренность",
        "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир"
    ],
    "Pentacles": [
        "Туз Пентаклей", "Двойка Пентаклей", "Тройка Пентаклей", "Четвёрка Пентаклей",
        "Пятёрка Пентаклей", "Шестёрка Пентаклей", "Семёрка Пентаклей",
        "Восьмёрка Пентаклей", "Девятка Пентаклей", "Десятка Пентаклей",
        "Паж Пентаклей", "Рыцарь Пентаклей", "Королева Пентаклей", "Король Пентаклей"
    ],
    "Wands": [
        "Туз Жезлов", "Двойка Жезлов", "Тройка Жезлов", "Четвёрка Жезлов",
        "Пятёрка Жезлов", "Шестёрка Жезлов", "Семёрка Жезлов",
        "Восьмёрка Жезлов", "Девятка Жезлов", "Десятка Жезлов",
        "Паж Жезлов", "Рыцарь Жезлов", "Королева Жезлов", "Король Жезлов"
    ],
    "Cups": [
        "Туз Кубков", "Двойка Кубков", "Тройка Кубков", "Четвёрка Кубков",
        "Пятёрка Кубков", "Шестёрка Кубков", "Семёрка Кубков",
        "Восьмёрка Кубков", "Девятка Кубков", "Десятка Кубков",
        "Паж Кубков", "Рыцарь Кубков", "Королева Кубков", "Король Кубков"
    ],
    "Swords": [
        "Туз Мечей", "Двойка Мечей", "Тройка Мечей", "Четвёрка Мечей",
        "Пятёрка Мечей", "Шестёрка Мечей", "Семёрка Мечей",
        "Восьмёрка Мечей", "Девятка Мечей", "Десятка Мечей",
        "Паж Мечей", "Рыцарь Мечей", "Королева Мечей", "Король Мечей"
    ]
}


def suits_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора масти (нижнее сообщение).
    """
    keyboard = [
        [
            InlineKeyboardButton("🧿 Пентакли 🧿", callback_data='suit_Pentacles'),
            InlineKeyboardButton("🌿 Жезлы 🌿", callback_data='suit_Wands'),
        ],
        [
            InlineKeyboardButton("🍷 Кубки 🍷", callback_data='suit_Cups'),
            InlineKeyboardButton("⚔️ Мечи ⚔️", callback_data='suit_Swords'),
        ],
        [
            InlineKeyboardButton("👑 Старшие Арканы 👑", callback_data='suit_Major'),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_card_buttons(suit_name: str) -> InlineKeyboardMarkup:
    """
    Создаёт инлайн-клавиатуру со списком карт выбранной масти.
    """
    if suit_name not in SUITS:
        # Если масть не найдена, вернём клавиатуру мастей.
        return suits_keyboard()

    cards_in_suit = SUITS[suit_name]
    keyboard = []
    row = []
    for idx, card_name in enumerate(cards_in_suit):
        row.append(InlineKeyboardButton(card_name, callback_data=f'card_{card_name}'))
        if (idx + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # «Назад к мастям»
    keyboard.append([InlineKeyboardButton("⬅ Назад к мастям", callback_data='suit_back')])
    return InlineKeyboardMarkup(keyboard)


async def start_card_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    При команде /start_card_search отправляем:
    1) Верхнее сообщение (будем менять при выборе карты),
    2) Нижнее сообщение (с кнопками мастей).
    """
    user = update.message.from_user
    logger.info(f"Пользователь {user.username} ({user.id}) начал поиск карты (два сообщения).")

    # 1) Верхнее сообщение (заглушка)
    msg_top = await update.message.reply_text("Пока не выбрана карта.")
    # Сохраняем message_id, чтобы менять его в будущем
    context.user_data["card_message_id"] = msg_top.message_id

    # 2) Нижнее сообщение с кнопками мастей
    await update.message.reply_text(
        "Выберите масть:",
        reply_markup=suits_keyboard()
    )


async def handle_suit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Пользователь выбрал масть или «Назад к мастям» (на нижнем сообщении).
    Меняем (edit_message_text) нижнее сообщение:
     - либо показываем кнопки карт,
     - либо возвращаем к кнопкам мастей.
    Верхнее сообщение не трогаем.
    """
    query = update.callback_query
    await query.answer()

    data = query.data
    # Если 'suit_back': вернуться к мастям
    if data == 'suit_back':
        await query.edit_message_text(
            text="Выберите масть:",
            reply_markup=suits_keyboard()
        )
        return

    # Иначе data = suit_XYZ
    _, suit_name = data.split('_', 1)
    new_kb = create_card_buttons(suit_name)

    # Меняем нижнее сообщение
    await query.edit_message_text(
        text=f"Вы выбрали масть: {suit_name}. Теперь выберите карту:",
        reply_markup=new_kb
    )


async def handle_card_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Пользователь выбрал конкретную карту на нижнем сообщении.
    МЕНЯЕМ верхнее сообщение (текст или фото) на описание карты.
    Клавиатуру в нижнем сообщении не трогаем, чтобы пользователь мог выбрать другую карту.
    """
    query = update.callback_query
    await query.answer()

    # card_Туз Пентаклей
    _, card_name = query.data.split('_', 1)
    card_info = cards.get(card_name)

    if not card_info:
        await query.message.reply_text(f"Информация о карте «{card_name}» не найдена.")
        return

    # Формируем текст
    description = card_info.get("description", "Описание отсутствует.")
    advice = card_info.get("advice", "")
    image_file = card_info.get("image_file", "")

    caption = (
        f"🃏 {card_name}\n\n"
        f"{description}\n\n"
        f"💡 Совет: {advice}"
    )

    # Ищем message_id верхнего сообщения
    top_msg_id = context.user_data.get("card_message_id")
    if not top_msg_id:
        # На случай, если старт бота был другим
        await query.message.reply_text(caption)
        return

    chat_id = query.message.chat_id

    # Путь к изображению
    base_dir = os.path.dirname(os.path.abspath(__file__))
    image_path = os.path.join(base_dir, 'images', image_file)

    # 1) Удаляем старое верхнее сообщение
    #    (т.к. оно было текстом, а мы хотим новое фото-сообщение)
    from telegram.error import BadRequest
    try:
        await context.bot.delete_message(chat_id, top_msg_id)
    except BadRequest as e:
        logger.warning(f"Не удалось удалить старое верхнее сообщение ID={top_msg_id}: {e}")

    # 2) Отправляем новое верхнее сообщение (фото или текст)
    if os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            new_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption
            )
    else:
        new_msg = await context.bot.send_message(chat_id=chat_id, text=caption)

    # 3) Запоминаем новое message_id в user_data, 
    #    чтобы при следующем выборе карты снова удалить/заменить
    context.user_data["card_message_id"] = new_msg.message_id

    # Нижнее сообщение (с кнопками) при этом не меняем —
    # пользователь может выбрать другую карту (или вернуться к мастям).
