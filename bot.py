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

# Моковые данные помещений
all_units = [
    {"kadnum": f"77:01:000401:{100 + i}", "area": 80 + i * 5, "type": "нежилое" if i % 2 == 0 else "жилое", "usage": "офис" if i % 3 else "магазин"} for i in range(25)
]

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

    def safe_reply(text):
        if query.message.text:
            return query.edit_message_text(text)
        else:
            return query.message.reply_text(text)

    if query.data == 'search_by_kadnum':
        await safe_reply("Введите кадастровый номер:")
        context.user_data['state'] = 'awaiting_kadnum'
    elif query.data == 'search_by_address':
        await safe_reply("Введите адрес или координаты:")
        context.user_data['state'] = 'awaiting_address'
    elif query.data == 'show_land':
        text = (
            "🌍 Земельный участок:\n"
            "Тип: Земельный участок\n"
            "Год постройки: 2005\n"
            "Площадь: 2 400 м²\n"
            "Назначение: Коммерческое\n"
            "ВРИ: Для офисной застройки\n"
            "Собственник: физ. лицо"
        )
        await safe_reply(text)
    elif query.data.startswith('show_units'):
        page = int(query.data.split(':')[1]) if ':' in query.data else 0
        await show_units_page(query, context, page)
    elif query.data == 'check_risks':
        await safe_reply("🛑 Риски:\n- Вид использования: допустим\n- Площадь подходит под коммерческое использование\n- Не находится в охранной зоне (по открытым данным)")

async def show_units_page(query, context, page):
    page_size = 10
    units_sorted = sorted(all_units, key=lambda x: (x['type'] != 'нежилое', x['usage']))
    start = page * page_size
    end = start + page_size
    units = units_sorted[start:end]

    if not units:
        await query.message.reply_text("Нет данных на этой странице")
        return

    text = "📦 Помещения внутри здания (стр. {}/{}):\n".format(
        page + 1, (len(units_sorted) - 1) // page_size + 1
    )
    for u in units:
        text += f"\n📄 {u['kadnum']}\n🏠 {u['area']} м² — {u['usage']} — {u['type']}\n"

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅ Назад", callback_data=f"show_units:{page - 1}"))
    if end < len(units_sorted):
        buttons.append(InlineKeyboardButton("➡ Далее", callback_data=f"show_units:{page + 1}"))
    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None

    if query.message.text:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query.message.reply_text(text, reply_markup=reply_markup)

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
        [InlineKeyboardButton("🌍 Земельный участок", callback_data='show_land')],
        [InlineKeyboardButton("📦 Помещения внутри", callback_data='show_units:0')],
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
