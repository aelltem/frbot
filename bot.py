import os
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import requests
from io import BytesIO
import pandas as pd
from fpdf import FPDF
from math import radians, cos, sin, asin, sqrt
from rapidfuzz import process

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x/"
ROSREESTR_API_URL = "https://rosreestr-integration.example.com/api/v1/lookup"  # Условная ссылка

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

        district_params = {
            "apikey": YANDEX_API_KEY,
            "geocode": f"{lon},{lat}",
            "format": "json",
            "kind": "district",
            "results": 1
        }
        metro_params = {
            "apikey": YANDEX_API_KEY,
            "geocode": f"{lon},{lat}",
            "format": "json",
            "kind": "metro",
            "results": 1
        }

        response_district = requests.get(GEOCODER_URL, params=district_params)
        response_district.raise_for_status()
        district_data = response_district.json()
        feature_district = district_data['response']['GeoObjectCollection']['featureMember']
        if feature_district:
            district = feature_district[0]['GeoObject']['name']

        response_metro = requests.get(GEOCODER_URL, params=metro_params)
        response_metro.raise_for_status()
        metro_data = response_metro.json()
        feature_metro = metro_data['response']['GeoObjectCollection']['featureMember']
        if feature_metro:
            metro = feature_metro[0]['GeoObject']['name']

        return district, metro
    except Exception as e:
        logger.error(f"Ошибка при получении округа/метро: {e}")
        return None, None

async def fetch_rosreestr_data(lat, lon):
    try:
        response = requests.get(ROSREESTR_API_URL, params={"lat": lat, "lon": lon})
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при обращении к Росреестру: {e}")
        return None

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
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
        buttons = [
            [InlineKeyboardButton(text=s['address'], callback_data=json.dumps({"action": "select_address", "lat": s['lat'], "lon": s['lon'], "address": s['address']}))] for s in suggestions
        ]
        await update.message.reply_text("Возможно, вы имели в виду:", reply_markup=InlineKeyboardMarkup(buttons))

async def process_selected_address(update: Update, context: ContextTypes.DEFAULT_TYPE, selected):
    lat, lon = selected['lat'], selected['lon']
    district, metro = await fetch_district_and_metro(lat, lon)
    rosreestr_data = await fetch_rosreestr_data(lat, lon)

    info_parts = [f"Найден адрес: {selected['address']}"]
    if district:
        info_parts.append(f"Округ: {district}")
    if metro:
        info_parts.append(f"Ближайшее метро: {metro}")

    if rosreestr_data:
        if rosreestr_data.get('cadastral_number'):
            info_parts.append(f"Кадастровый номер: {rosreestr_data['cadastral_number']}")
        if rosreestr_data.get('area'):
            info_parts.append(f"Площадь: {rosreestr_data['area']} кв.м")
        if rosreestr_data.get('purpose'):
            info_parts.append(f"Назначение: {rosreestr_data['purpose']}")
        if rosreestr_data.get('type') == 'land':
            info_parts.append("Тип объекта: Земельный участок")

    map_button = InlineKeyboardButton(
        text="Показать на карте",
        url=f"https://pkk.rosreestr.ru/#/?lat={lat}&lon={lon}&z=18"
    )

    analogs_button = InlineKeyboardButton(
        text="Аналоги по цене и площади",
        callback_data=json.dumps({"action": "analogs", "lat": lat, "lon": lon})
    )

    await update.message.reply_text(
        "\n".join(info_parts),
        reply_markup=InlineKeyboardMarkup([[map_button], [analogs_button]])
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = json.loads(query.data)

    if data.get("action") == "select_address":
        await process_selected_address(update, context, data)
    elif data.get("action") == "analogs":
        lat, lon = data['lat'], data['lon']
        keyboard = [
            [InlineKeyboardButton("Авито", url=f"https://www.avito.ru/moskva/kvartiry?lat={lat}&lng={lon}"),
             InlineKeyboardButton("Циан", url=f"https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&region=1&center={lon},{lat}"),
             InlineKeyboardButton("Яндекс", url=f"https://realty.yandex.ru/moskva/?ll={lon}%2C{lat}&search_type=geo")]
        ]
        await query.message.reply_text("Выберите источник для сравнения:", reply_markup=InlineKeyboardMarkup(keyboard))

app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address))
app.add_handler(CallbackQueryHandler(handle_callback))

if __name__ == '__main__':
    app.run_polling()
