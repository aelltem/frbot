
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import requests
from io import BytesIO
import pandas as pd
from fpdf import FPDF
from math import radians, cos, sin, sqrt, atan2

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Моковые данные помещений
all_units = [
    {"kadnum": f"77:01:000401:{100 + i}", "area": 80 + i * 5, "type": "нежилое" if i % 2 == 0 else "жилое", "usage": "офис" if i % 3 else "магазин", "lat": 55.75 + (i * 0.001), "lon": 37.62 + (i * 0.001)} for i in range(25)
]

# История запросов и сравнение
user_history = {}
user_compare = {}

# Функция расчета расстояния
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

async def find_nearby_objects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        lat, lon = map(float, text.split(","))
        nearby = [
            u for u in all_units
            if haversine(lat, lon, u["lat"], u["lon"]) <= 0.3  # радиус 300 м
        ]
        if not nearby:
            await update.message.reply_text("🔍 Поблизости объектов не найдено.")
            return

        reply = "🏘 Объекты рядом (до 300 м):\n"
        for i, u in enumerate(nearby, 1):
            reply += f"{i}. {u['kadnum']} | {u['area']} м² | {u['usage']} | {u['type']}\n"
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Ошибка при поиске соседей: {e}")
        await update.message.reply_text("Ошибка: введите координаты в формате: широта,долгота")

def main():
    token = os.getenv("YOUR_TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Переменная окружения YOUR_TELEGRAM_BOT_TOKEN не установлена")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("nearby", find_nearby_objects))
    app.add_handler(CallbackQueryHandler(export_units, pattern="^export_units$"))
    app.add_handler(CallbackQueryHandler(export_units_pdf, pattern="^export_units_pdf$"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address))
    app.run_polling()

if __name__ == '__main__':
    main()
