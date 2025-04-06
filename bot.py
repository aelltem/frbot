import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import requests
from io import BytesIO
import pandas as pd
from fpdf import FPDF
from math import radians, cos, sin, sqrt, atan2

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Моковые данные помещений
all_units = [
    {"kadnum": f"77:01:000401:{100 + i}", "area": 80 + i * 5,
     "type": "нежилое" if i % 2 == 0 else "жилое",
     "usage": "офис" if i % 3 else "магазин",
     "lat": 55.75 + i * 0.001, "lon": 37.62 + i * 0.001}
    for i in range(25)
]

user_history = {}
user_compare = {}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Информация по кадастровому номеру", callback_data='search_by_kadnum')],
        [InlineKeyboardButton("📍 Поиск по адресу/координатам", callback_data='search_by_address')],
        [InlineKeyboardButton("📤 Экспорт XLSX", callback_data='export_units'),
         InlineKeyboardButton("📝 Экспорт PDF", callback_data='export_units_pdf')],
        [InlineKeyboardButton("📊 Сравнить объекты", callback_data='show_comparison')],
    ]
    await update.message.reply_text("Привет! Я бот-помощник по недвижимости.", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        params = {"q": text, "format": "json"}
        res = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers={"User-Agent": "real-estate-bot"})
        data = res.json()
        if not data:
            await update.message.reply_text("Ничего не найдено по адресу.")
            return

        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
        kadnum = "77:01:000401:999"
        user_id = update.effective_user.id
        user_history.setdefault(user_id, []).insert(0, f"{text} → {kadnum}")
        user_history[user_id] = user_history[user_id][:5]

        info = f"🏢 Найден объект по адресу:\nКадастровый номер: {kadnum}\nТип: Здание\nПлощадь: 1200 м²\nНазначение: Офис"
        keyboard = [
            [InlineKeyboardButton("🌍 Земельный участок", callback_data='show_land')],
            [InlineKeyboardButton("📦 Помещения внутри", callback_data='show_units:0')],
            [InlineKeyboardButton("🛑 Проверка рисков", callback_data='check_risks')],
            [InlineKeyboardButton("📍 Соседние объекты (300 м)", callback_data=f'nearby:{lat},{lon}')],
            [InlineKeyboardButton("➕ В сравнение", callback_data=f'add_compare:{kadnum}')],
        ]
        await update.message.reply_text(info, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка при обработке адреса: {e}")
        await update.message.reply_text("Ошибка. Попробуйте снова.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("add_compare:"):
        kadnum = query.data.split(":")[1]
        user_compare.setdefault(user_id, set()).add(kadnum)
        await query.message.reply_text(f"✅ Объект {kadnum} добавлен в сравнение.")
    elif query.data == "show_comparison":
        compare = user_compare.get(user_id, set())
        if not compare:
            await query.message.reply_text("📊 Список сравнения пуст.")
            return
        text = "📊 Сравнение объектов:\n"
        for i, k in enumerate(compare, 1):
            unit = next((u for u in all_units if u['kadnum'] == k), None)
            if unit:
                text += f"{i}. {unit['kadnum']} | {unit['area']} м² | {unit['usage']} | {unit['type']}\n"
            else:
                text += f"{i}. {k} — нет данных\n"
        await query.message.reply_text(text)
    elif query.data.startswith("nearby:"):
        lat, lon = map(float, query.data.split(":")[1].split(","))
        nearby = [u for u in all_units if haversine(lat, lon, u["lat"], u["lon"]) <= 0.3]
        if not nearby:
            await query.message.reply_text("🔍 Рядом ничего не найдено.")
            return
        reply = "🏘 Объекты рядом (до 300 м):\n"
        for i, u in enumerate(nearby, 1):
            reply += f"{i}. {u['kadnum']} | {u['area']} м² | {u['usage']} | {u['type']}\n"
        await query.message.reply_text(reply)

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = user_history.get(user_id, [])
    if not history:
        await update.message.reply_text("История пуста.")
        return
    msg = "🕘 Последние запросы:\n" + "\n".join([f"{i+1}. {h}" for i, h in enumerate(history)])
    await update.message.reply_text(msg)

async def export_units(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = pd.DataFrame(all_units)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    await update.callback_query.message.reply_document(
        document=InputFile(output, filename="units.xlsx"),
        caption="📤 Список экспортирован."
    )

async def export_units_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Список помещений", ln=True, align="C")
    for u in all_units:
        pdf.cell(200, 8, txt=f"{u['kadnum']} | {u['area']} м² | {u['usage']} | {u['type']}", ln=True)
    output = BytesIO()
    pdf.output(output)
    output.seek(0)
    await update.callback_query.message.reply_document(
        document=InputFile(output, filename="units.pdf"),
        caption="📝 PDF экспорт."
    )

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
