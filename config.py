# config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

# 3X-UI Panel
PANEL_URL = os.getenv("PANEL_URL", "https://cerberusvless.top:19844/KsSNaHIplNjDaiy1Xs")
API_TOKEN = os.getenv("API_TOKEN")

# Inbound IDs
INBOUND_LATVIA = 2
INBOUND_NETHERLANDS = 1
INBOUND_FINLAND = 5  # 🇫🇮 Новый сервер

# Crypto Pay
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")
CRYPTO_ASSET = os.getenv("CRYPTO_ASSET", "USDT")

# Platega Payment Gateway
# Авторизация у Platega — через заголовки X-MerchantId / X-Secret (не подпись в теле!)
PLATEGA_ENABLED = os.getenv("PLATEGA_ENABLED", "false").lower() == "true"
PLATEGA_BASE_URL = os.getenv("PLATEGA_BASE_URL", "https://app.platega.io")
PLATEGA_API_VERSION = os.getenv("PLATEGA_API_VERSION", "v1")  # v1 -> /transaction/process ("redirect"), v2 -> /v2/transaction/process ("url")
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID", "")
PLATEGA_SECRET = os.getenv("PLATEGA_SECRET", "")
PLATEGA_RETURN_URL = os.getenv("PLATEGA_RETURN_URL", "https://t.me/cerberusVPN_robot")
PLATEGA_FAILED_URL = os.getenv("PLATEGA_FAILED_URL", "https://t.me/cerberusVPN_robot")

# Коды методов оплаты Platega (см. PaymentMethodInt в docs.platega.io):
# 2 = СБП (QR-код) + Sberpay, 11 = Карточный эквайринг
PLATEGA_METHOD_CARD = 11
PLATEGA_METHOD_SBP = 2
# Комиссии показываются в кнопках информативно — реальную итоговую сумму
# (с уже включённой комиссией) всегда считает сама Platega и возвращает в ответе.
PLATEGA_CARD_COMMISSION_PERCENT = 9
PLATEGA_SBP_COMMISSION_PERCENT = 8

# Уведомления пользователям (истечение подписки / трафик)
NOTIFY_EXPIRY_HOURS_BEFORE = int(os.getenv("NOTIFY_EXPIRY_HOURS_BEFORE", "24"))
NOTIFY_TRAFFIC_THRESHOLD_PERCENT = float(os.getenv("NOTIFY_TRAFFIC_THRESHOLD_PERCENT", "90"))
NOTIFY_CHECK_INTERVAL_MINUTES = int(os.getenv("NOTIFY_CHECK_INTERVAL_MINUTES", "30"))

# VPN
VPN_DOMAIN = os.getenv("VPN_DOMAIN", "cerberusvless.top")

# Database
DB_PATH = os.getenv("DB_PATH", "bot.db")

# Subscription server port
SUBSCRIPTION_PORT = 2096

# Webhook
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))
CRYPTOBOT_WEBHOOK_SECRET = os.getenv("CRYPTOBOT_WEBHOOK_SECRET", "")

# Курс USDT к RUB (для конвертации)
USDT_TO_RUB_RATE = float(os.getenv("USDT_TO_RUB_RATE", "95.0"))

# Тарифы: устройства × периоды = цена в рублях
TARIFF_PRICES = {
    3: {
        30: 79,
        90: 239,
        180: 449,
        365: 849,
    },
    5: {
        30: 99,
        90: 259,
        180: 469,
        365: 869,
    },
    10: {
        30: 199,
        90: 459,
        180: 869,
        365: 1669,
    },
}

SUBSCRIPTION_PERIODS = [30, 90, 180, 365]

PERIOD_NAMES = {
    30: "30 дней",
    90: "90 дней",
    180: "180 дней",
    365: "365 дней",
}

PERIOD_EMOJIS = {
    30: "🗓️",
    90: "📅",
    180: "📆",
    365: "🎉",
}

# Все локации
ALL_INBOUNDS = [
    {"id": INBOUND_LATVIA, "name": "🇱🇻 Латвия", "host": "lv.cerberusvless.top"},
    {"id": INBOUND_NETHERLANDS, "name": "🇳🇱 Нидерланды", "host": "nl.cerberusvless.top"},
    {"id": INBOUND_FINLAND, "name": "🇫🇮 Финляндия", "host": "fi.cerberusvless.top"},
]