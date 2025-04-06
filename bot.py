import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import requests
from io import BytesIO
import pandas as pd
from fpdf import FPDF
from math import radians, cos, sin, asin, sqrt

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

all_units = [
    {"kadnum": f"77:01:000401:{100 + i}", "area": 80 + i * 5, "type": "нежилое" if i % 2 == 0 else "жилое",
     "usage": "офис" if i % 2 == 0 else "жилое", "lat": 55.75 + (i * 0.001), "lon": 37.62 + (i * 0.001)} for i in range(25)
]

def paginate_units(units, page=0, per_page=10):
    start = page * per_page
    end = start + per_page
    return units[start:end]

def generate_unit_keyboard(page, total, filters=None):
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"show_units:{page-1}"))
    if (page + 1) * 10 < total:
        keyboard.append(InlineKeyboardButton("➡️ Далее", callback_data=f"show_units:{page+1}"))
    filter_buttons = [
        InlineKeyboardButton("Фильтр: жилое", callback_data="filter:жилое"),
        InlineKeyboardButton("Фильтр: нежилое", callback_data="filter:нежилое")
    ]
    return InlineKeyboardMarkup([keyboard] + [[b] for b in filter_buttons])

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return 6371 * c

def geocode_address(address):
    try:
        url = f"https://geocode-maps.yandex.ru/1.x/?format=json&geocode={address}"
        resp = requests.get(url).json()
        pos = resp['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['Point']['pos']
        lon, lat = map(float, pos.split())
        return lat, lon
    except:
        return 55.76, 37.62

def reverse_geocode(lat, lon):
    try:
        url = f"https://geocode-maps.yandex.ru/1.x/?format=json&geocode={lon},{lat}&kind=house"
        resp = requests.get(url).json()
        geo_object = resp['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']
        address = geo_object['metaDataProperty']['GeocoderMetaData']['text']
        components = geo_object['metaDataProperty']['GeocoderMetaData']['Address']['Components']
        district = next((c['name'] for c in components if c['kind'] == 'district'), 'неизвестно')
        metro = next((c['name'] for c in components if c['kind'] == 'metro'), 'неизвестно')
        return address, district, metro
    except:
        return "Неизвестный адрес", "неизвестно", "неизвестно"

async def show_units_page(update, context, page=0, filter_by=None):
    query = update.callback_query
    await query.answer()
    filtered_units = all_units
    if filter_by:
        filtered_units = [u for u in all_units if filter_by == u['type']]
    page_units = paginate_units(filtered_units, page)
    if not page_units:
        await query.edit_message_text("Ничего не найдено по фильтру.")
        return
    msg = "📦 Помещения:\n" + "\n".join([
        f"{i+1}. {u['kadnum']} — {u['area']} м² — {u['type']}"
        for i, u in enumerate(page_units)
    ])
    total = len(filtered_units)
    context.user_data["unit_filter"] = filter_by
    await query.edit_message_text(msg, reply_markup=generate_unit_keyboard(page, total))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("show_units:"):
        page = int(data.split(":")[1])
        filter_by = context.user_data.get("unit_filter")
        await show_units_page(update, context, page, filter_by)
    elif data.startswith("filter:"):
        filter_by = data.split(":")[1]
        await show_units_page(update, context, page=0, filter_by=filter_by)
    elif data == "search_by_kadnum":
        context.user_data["mode"] = "kadnum"
        await query.message.reply_text("✉️ Введите кадастровый номер:")
    elif data == "search_by_address":
        context.user_data["mode"] = "address"
        await query.message.reply_text("✉️ Введите адрес или координаты через запятую:")
    elif data == "export_units":
        df = pd.DataFrame(all_units)
        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        await query.message.reply_document(document=output, filename="units.xlsx")
    elif data == "export_units_pdf":
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        for u in all_units:
            line = f"{u['kadnum']} | {u['area']} м² | {u['type']}"
            pdf.cell(200, 10, txt=line.encode('latin-1', 'replace').decode('latin-1'), ln=True)
        output = BytesIO()
        pdf_output_path = "temp_units.pdf"
        pdf.output(pdf_output_path)
        with open(pdf_output_path, "rb") as f:
            await query.message.reply_document(document=f, filename="units.pdf")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 По кадастровому номеру", callback_data="search_by_kadnum")],
        [InlineKeyboardButton("📍 Поиск по адресу", callback_data="search_by_address")]
    ]
    await update.message.reply_text("Привет! Я помогу с недвижимостью.", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.get("mode")

    if mode == "kadnum":
        kadnum = text
        lat, lon = geocode_address(kadnum)
        address, district, metro = reverse_geocode(lat, lon)
    else:
        address = text
        lat, lon = geocode_address(address)
        kadnum = "77:01:000401:999"
        address, district, metro = reverse_geocode(lat, lon)

    map_url = f"https://static-maps.yandex.ru/1.x/?ll={lon},{lat}&size=600,400&z=17&l=map&pt={lon},{lat},pm2rdm"

    try:
        response = requests.get(map_url)
        if response.status_code == 200:
            photo = BytesIO(response.content)
            caption = f"📍 Адрес: {address}\n🏢 Кадастр: {kadnum}\nТип: Здание\nПлощадь: 1200 м²\nМетро: {metro}\nОкруг: {district}"
            await update.message.reply_photo(photo=photo, caption=caption)
        else:
            raise Exception("Не удалось получить карту")
    except Exception as e:
        logger.warning(f"Ошибка карты: {e}")
        await update.message.reply_text(f"📍 Адрес: {address}\n🏢 Кадастр: {kadnum}\nТип: Здание\nПлощадь: 1200 м²\nМетро: {metro}\nОкруг: {district}")

    keyboard = [
        [InlineKeyboardButton("🌍 Земельный участок", callback_data='show_land')],
        [InlineKeyboardButton("📦 Помещения внутри", callback_data='show_units:0')],
        [InlineKeyboardButton("📤 Excel", callback_data='export_units'), InlineKeyboardButton("📝 PDF", callback_data='export_units_pdf')]
    ]
    await update.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))

def main():
    token = os.getenv("YOUR_TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Токен не установлен в переменных окружения")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address))
    app.run_polling()

if __name__ == '__main__':
    main()
