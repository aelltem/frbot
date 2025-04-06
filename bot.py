import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import requests
from io import BytesIO

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Информация по кадастровому номеру", callback_data='search_by_kadnum')],
        [InlineKeyboardButton("📍 Поиск по адресу/координатам", callback_data='search_by_address')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Я бот-помощник по недвижимости. Что будем искать?", reply_markup=reply_markup)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'search_by_kadnum':
        await query.edit_message_text("Введите кадастровый номер:")
        context.user_data['state'] = 'awaiting_kadnum'
    elif query.data == 'search_by_address':
        await query.edit_message_text("Введите адрес или координаты:")
        context.user_data['state'] = 'awaiting_address'
    elif query.data == 'show_land':
        await query.edit_message_text("🔍 Участок здания:\nКадастр: 77:01:000401:777\nПлощадь: 2 400 м²\nНазначение: коммерческое")
    elif query.data == 'show_units':
        await query.edit_message_text("📦 Помещения внутри здания:\n1. 77:01:000401:111 — 120 м² — офис\n2. 77:01:000401:112 — 95 м² — магазин\n3. 77:01:000401:113 — 180 м² — кафе")
    elif query.data == 'check_risks':
        await query.edit_message_text("🛑 Риски:\n- Вид использования: допустим\n- Площадь подходит под коммерческое использование\n- Не находится в охранной зоне (по открытым данным)")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    text = update.message.text.strip()

    if state == 'awaiting_kadnum':
        await handle_kadnum(update, context, text)
    elif state == 'awaiting_address':
        await handle_address(update, context, text)
    else:
        await update.message.reply_text("Пожалуйста, выбери действие из меню: /start")

async def handle_kadnum(update: Update, context: ContextTypes.DEFAULT_TYPE, kadnum: str):
    info = f"Объект с кадастровым номером {kadnum}\nТип: Здание\nПлощадь: 1200 м²\nНазначение: Офис\n📞 Телефон УК: +7 (495) 123-45-67"
    keyboard = [
        [InlineKeyboardButton("🌍 Участок здания", callback_data='show_land')],
        [InlineKeyboardButton("📦 Помещения внутри", callback_data='show_units')],
        [InlineKeyboardButton("🛑 Проверка рисков", callback_data='check_risks')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    lat, lon = 55.751244, 37.618423
    map_url = f"https://static-maps.yandex.ru/1.x/?ll={lon},{lat}&z=17&size=600,400&l=map&pt={lon},{lat},pm2rdm"
    try:
        response = requests.get(map_url)
        if response.status_code == 200:
            image = BytesIO(response.content)
            await update.message.reply_photo(photo=image, caption=info, reply_markup=reply_markup)
            return
    except Exception as e:
        logger.error(f"Ошибка загрузки карты: {e}")

    await update.message.reply_text(info + f"\n\nКарта недоступна, координаты: {lat}, {lon}", reply_markup=reply_markup)

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE, address: str):
    try:
        params = {"q": address, "format": "json"}
        res = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers={"User-Agent": "real-estate-bot"})
        data = res.json()
        if not data:
            await update.message.reply_text("Ничего не найдено по данному адресу.")
            return
        lat, lon = data[0]["lat"], data[0]["lon"]
        map_url = f"https://static-maps.yandex.ru/1.x/?ll={lon},{lat}&z=17&size=600,400&l=map&pt={lon},{lat},pm2rdm"
        response = requests.get(map_url)
        if response.status_code == 200:
            image = BytesIO(response.content)
            await update.message.reply_photo(photo=image, caption=f"Координаты: {lat}, {lon}")
        else:
            await update.message.reply_text(f"Координаты: {lat}, {lon}\n(Карта недоступна)")
    except Exception as e:
        logger.error(f"Ошибка при поиске по адресу: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.")

def main():
    token = os.getenv("YOUR_TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Переменная окружения YOUR_TELEGRAM_BOT_TOKEN не установлена")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == '__main__':
    main()
