import os
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import requests
from io import BytesIO
import pandas as pd
from fpdf import FPDF

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x/"

async def fetch_coordinates(address):
    params = {
        "apikey": YANDEX_API_KEY,
        "geocode": address,
        "format": "json",
        "results": 5
    }
    try:
        response = requests.get(GEOCODER_URL, params=params)
        response.raise_for_status()
        geo_data = response.json()
        feature_member = geo_data['response']['GeoObjectCollection']['featureMember']
        if not feature_member:
            return None
        suggestions = []
        for item in feature_member:
            obj = item['GeoObject']
            coords = obj['Point']['pos'].split()
            address_text = obj['metaDataProperty']['GeocoderMetaData']['text']
            suggestions.append({
                "address": address_text,
                "lat": float(coords[1]),
                "lon": float(coords[0])
            })
        return suggestions
    except Exception as e:
        logger.error(f"Ошибка при получении координат: {e}")
        return None

async def fetch_district_and_metro(lat, lon):
    try:
        district, metro = None, None
        for kind in ["district", "metro"]:
            response = requests.get(GEOCODER_URL, params={
                "apikey": YANDEX_API_KEY,
                "geocode": f"{lon},{lat}",
                "format": "json",
                "kind": kind,
                "results": 1
            })
            response.raise_for_status()
            data = response.json()
            feature = data['response']['GeoObjectCollection']['featureMember']
            if feature:
                name = feature[0]['GeoObject']['name']
                if kind == "district":
                    district = name
                else:
                    metro = name
        return district, metro
    except Exception as e:
        logger.error(f"Ошибка при получении округа/метро: {e}")
        return None, None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🔍 Поиск по адресу", callback_data=json.dumps({"action": "search_by_address"}))],
        [InlineKeyboardButton("🧾 Поиск по кадастровому номеру", callback_data=json.dumps({"action": "search_by_cadastral"}))]
    ]
    await update.message.reply_text(
        "👋 Привет! Я бот для анализа недвижимости в Москве.\n\nЯ помогу найти адрес, округ, метро, аналоги, объекты внутри, выгрузки и многое другое 📍",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data:
        await query.message.reply_text("Ошибка: кнопка не содержит данных. Попробуйте ещё раз.")
        return

    try:
        data = json.loads(query.data)
    except json.JSONDecodeError:
        await query.message.reply_text("Ошибка обработки кнопки. Попробуйте ещё раз.")
        return

    action = data.get("action")
    if action == "search_by_address":
        await query.message.reply_text("Введите адрес:")
    elif action == "search_by_cadastral":
        await query.message.reply_text("Введите кадастровый номер:")
    elif action == "select_address":
        await process_selected_address(update, context, data)
    elif action == "analogs":
        lat, lon = data['lat'], data['lon']
        keyboard = [
            [InlineKeyboardButton("🏘 Авито", url=f"https://www.avito.ru/moskva/nedvizhimost?location={lat}%2C{lon}"),
             InlineKeyboardButton("📍 Циан", url=f"https://www.cian.ru/cat.php?deal_type=sale&region=1&center={lon},{lat}"),
             InlineKeyboardButton("🏡 Яндекс", url=f"https://realty.yandex.ru/moskva/?ll={lon}%2C{lat}&search_type=geo")]
        ]
        await query.message.reply_text("💰 Выберите источник для сравнения:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif action == "owner_info":
        cad_number = data.get("cad", "")
        if cad_number:
            buttons = [
                [InlineKeyboardButton("🔗 Ручной поиск", url=f"https://proverki.gov.ru/"),
                 InlineKeyboardButton("🤖 Автоматически (будущая интеграция)", callback_data=json.dumps({"action": "owner_future"}))]
            ]
            await query.message.reply_text("📄 Как найти правообладателя?", reply_markup=InlineKeyboardMarkup(buttons))
    elif action == "owner_future":
        await query.message.reply_text("⚙️ Функция автоматического поиска владельца в разработке.")
    elif action == "objects_inside":
        await query.message.reply_text("📂 Функция отображения объектов внутри будет добавлена в следующем обновлении.")

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text

    if user_input.count(":") == 3:
        cad_number = user_input.strip()
        url = f"https://pkk.rosreestr.ru/#/search/{cad_number}"
        await update.message.reply_text(f"🔍 Найден кадастровый номер: {cad_number}\n\n📘 Кадастровая карта: {url}")
        return

    if not user_input.lower().startswith("москва"):
        user_input = f"Москва, {user_input}"

    suggestions = await fetch_coordinates(user_input)

    if not suggestions:
        await update.message.reply_text("Не удалось найти адрес. Попробуйте снова.")
        return

    if len(suggestions) == 1:
        selected = suggestions[0]
        await process_selected_address(update, context, selected)
    else:
        buttons = []
        for s in suggestions:
            try:
                data = json.dumps({"action": "select_address", "lat": s['lat'], "lon": s['lon'], "address": s['address']})
                buttons.append([InlineKeyboardButton(text=s['address'], callback_data=data)])
            except Exception as e:
                logger.error(f"Ошибка сериализации кнопки: {e}")
        await update.message.reply_text("Возможно, вы имели в виду:", reply_markup=InlineKeyboardMarkup(buttons))

async def process_selected_address(update: Update, context: ContextTypes.DEFAULT_TYPE, selected):
    lat, lon = selected['lat'], selected['lon']
    district, metro = await fetch_district_and_metro(lat, lon)

    info_parts = [f"📍 Найден адрес: {selected['address']}"]
    if district:
        info_parts.append(f"🏙️ Округ: {district}")
    if metro:
        info_parts.append(f"🚇 Ближайшее метро: {metro}")

    photo_url = f"https://static-maps.yandex.ru/1.x/?lang=ru_RU&ll={lon},{lat}&z=16&size=450,250&l=map&pt={lon},{lat},pm2rdm"

    buttons = [
        [
            InlineKeyboardButton("🗺️ Яндекс Карты", url=f"https://yandex.ru/maps/?ll={lon},{lat}&z=18"),
            InlineKeyboardButton("📘 Кадастровая карта", url=f"https://pkk.rosreestr.ru/#/?lat={lat}&lon={lon}&z=18")
        ],
        [
            InlineKeyboardButton("📂 Объекты внутри", callback_data=json.dumps({"action": "objects_inside", "lat": lat, "lon": lon}))
        ],
        [
            InlineKeyboardButton("💰 Аналоги по цене и площади", callback_data=json.dumps({"action": "analogs", "lat": lat, "lon": lon}))
        ],
        [
            InlineKeyboardButton("📄 Правообладатель", callback_data=json.dumps({"action": "owner_info", "cad": "77:01:000401:999"}))
        ]
    ]

    await update.message.reply_photo(
        photo=photo_url,
        caption="\n".join(info_parts),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
app.add_handler(CommandHandler("start", start_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address))
app.add_handler(CallbackQueryHandler(handle_callback))

if __name__ == "__main__":
    app.run_polling()
