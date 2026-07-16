# handlers/purchase.py
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import asyncio
import time
import uuid
import logging
import config

logger = logging.getLogger(__name__)
router = Router()

from panel_client import XUIPanelClient
from database import db

panel = XUIPanelClient()


def pluralize_devices(n: int) -> str:
    """Правильное склонение слова 'устройство' для русского языка"""
    n = abs(n) % 100
    n1 = n % 10

    if 10 < n < 20:
        return f"{n} устройств"
    if n1 == 1:
        return f"{n} устройство"
    if 2 <= n1 <= 4:
        return f"{n} устройства"
    return f"{n} устройств"


class PurchaseState(StatesGroup):
    selecting_devices = State()
    selecting_period = State()
    waiting_payment = State()


def create_invoice_sync(amount: float, asset: str, description: str, payload: str):
    """Синхронное создание инвойса через CryptoPay API"""
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {
        "Crypto-Pay-API-Token": config.CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "amount": str(amount),
        "asset": asset,
        "description": description,
        "payload": payload
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()


def get_invoice_sync(invoice_id: int):
    """Синхронная проверка статуса инвойса"""
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {
        "Crypto-Pay-API-Token": config.CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "invoice_ids": [invoice_id]
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()


# ==================== НАЧАЛО ПОКУПКИ ====================

@router.callback_query(F.data == "buy_subscription")
async def start_purchase(callback: types.CallbackQuery, state: FSMContext):
    """Начало покупки - выбор количества устройств"""
    logger.info(f"🛒 Начало покупки от {callback.from_user.id}")

    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📱 {pluralize_devices(devices)}",
            callback_data=f"devices_{devices}"
        )]
        for devices in [3, 5, 10]
    ])

    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])

    await callback.message.answer(
        "📱 <b>Выберите количество устройств:</b>\n\n"
        "🔒 Количество устройств = количество одновременных подключений\n\n"
        "📡 Все локации включены:\n"
        "• 🇱🇻 Латвия\n"
        "• 🇳🇱 Нидерланды\n"
        "• 🇫🇮 Финляндия\n\n"
        "💡 Одно подключение работает на ВСЕХ серверах",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(PurchaseState.selecting_devices)
    await callback.answer()


# ==================== ВЫБОР УСТРОЙСТВ ====================

@router.callback_query(F.data.startswith("devices_"),
                       PurchaseState.selecting_devices)
async def process_devices(callback: types.CallbackQuery, state: FSMContext):
    """Выбор устройств → выбор периода"""
    devices = int(callback.data.split("_")[1])
    await state.update_data(devices=devices)

    prices = config.TARIFF_PRICES.get(devices, {})

    keyboard_buttons = []
    for period in config.SUBSCRIPTION_PERIODS:
        price_rub = prices.get(period, 0)
        emoji = config.PERIOD_EMOJIS.get(period, "📅")
        period_name = config.PERIOD_NAMES.get(period, f"{period} дней")

        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {period_name} - {price_rub}₽",
                callback_data=f"period_{period}"
            )
        ])

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    devices_text = pluralize_devices(devices)

    await callback.message.answer(
        f"✅ Выбрано: <b>{devices_text}</b>\n\n"
        f"📅 <b>Выберите срок подписки:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(PurchaseState.selecting_period)
    await callback.answer()


# ==================== ВЫБОР ПЕРИОДА ====================

@router.callback_query(F.data.startswith("period_"),
                       PurchaseState.selecting_period)
async def process_period(callback: types.CallbackQuery, state: FSMContext):
    """Выбор периода → создание оплаты"""
    period = int(callback.data.split("_")[1])
    await state.update_data(period=period)

    data = await state.get_data()
    devices = data["devices"]

    price_rub = config.TARIFF_PRICES[devices][period]
    price_usdt = round(price_rub / config.USDT_TO_RUB_RATE, 2)

    await state.update_data(price_rub=price_rub, price_usdt=price_usdt)

    period_name = config.PERIOD_NAMES.get(period, f"{period} дней")
    period_emoji = config.PERIOD_EMOJIS.get(period, "📅")
    devices_text = pluralize_devices(devices)

    # В функции process_period, в keyboard_buttons добавь:
    keyboard_buttons = [
        [InlineKeyboardButton(text="💎 Оплатить криптой (USDT)", callback_data="pay_crypto")],
        [InlineKeyboardButton(text=f"💳 Оплатить картой/СБП ({price_rub} ₽)", callback_data="pay_platega")],
    ]

    if callback.from_user.id in config.ADMIN_IDS:
        keyboard_buttons.append([InlineKeyboardButton(
            text="🧪 Тестовая оплата (для админа)",
            callback_data="test_payment"
        )])

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.answer(
        f"📋 <b>Детали покупки:</b>\n\n"
        f"📱 Устройства: {devices_text}\n"
        f"📅 Срок: {period_emoji} {period_name}\n"
        f"🌍 Локации: Все ({len(config.ALL_INBOUNDS)})\n\n"
        f"💵 <b>Стоимость:</b>\n"
        f"💰 {price_rub} ₽\n"
        f"💎 ~{price_usdt} USDT\n\n"
        f"💳 Выберите способ оплаты:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(PurchaseState.waiting_payment)
    await callback.answer()


# ==================== ОПЛАТА ЧЕРЕЗ CRYPTOBOT ====================

@router.callback_query(F.data == "pay_crypto", PurchaseState.waiting_payment)
async def pay_crypto(callback: types.CallbackQuery, state: FSMContext):
    """Оплата через CryptoBot"""
    data = await state.get_data()
    devices = data["devices"]
    period = data["period"]
    price_usdt = data["price_usdt"]
    price_rub = data["price_rub"]

    user_id = uuid.uuid4().hex[:10]
    period_name = config.PERIOD_NAMES.get(period, f"{period} дней")
    devices_text = pluralize_devices(devices)

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: create_invoice_sync(
                amount=price_usdt,
                asset=config.CRYPTO_ASSET,
                description=f"Cerberus VPN - {devices_text} на {period_name}",
                payload=f"{user_id}_{devices}_{period}"
            )
        )

        if not result.get("ok"):
            raise Exception(result.get("error", {}).get("name", "Unknown error"))

        invoice = result["result"]
        invoice_id = invoice["invoice_id"]
        pay_url = invoice["pay_url"]

        user = await db.get_user(callback.from_user.id)
        if not user:
            user = await db.create_user(
                telegram_id=callback.from_user.id,
                username=callback.from_user.username,
                referral_code=uuid.uuid4().hex[:10]
            )

        await db.add_pending_payment(
            invoice_id=invoice_id,
            user_id=user['id'],
            devices=devices,
            tariff_days=period,
            amount=price_usdt
        )

    except Exception as e:
        logger.error(f"Ошибка создания оплаты: {e}")
        await callback.message.answer(f"❌ Ошибка создания оплаты: {e}")
        await state.clear()
        return

    keyboard_buttons = [
        [InlineKeyboardButton(text="💎 Оплатить через CryptoBot", url=pay_url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment_{invoice_id}")]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.answer(
        f"💎 <b>Оплата криптовалютой</b>\n\n"
        f"📱 Устройства: {devices_text}\n"
        f"📅 Срок: {period_name}\n"
        f"💵 Сумма: <b>{price_usdt} USDT</b> (~{price_rub} ₽)\n\n"
        f"1️⃣ Нажмите кнопку «Оплатить»\n"
        f"2️⃣ Оплатите инвойс в @CryptoBot\n"
        f"3️⃣ Нажмите «Проверить оплату»\n\n"
        f"⚡️ Подписка выдаётся автоматически после оплаты!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# handlers/purchase.py (добавь этот блок)

@router.callback_query(F.data == "pay_platega", PurchaseState.waiting_payment)
async def pay_platega(callback: types.CallbackQuery, state: FSMContext):
    """Оплата через Platega"""
    from platega_client import platega

    data = await state.get_data()
    devices = data["devices"]
    period = data["period"]
    price_rub = data["price_rub"]

    user = await db.get_user(callback.from_user.id)
    if not user:
        user = await db.create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            referral_code=uuid.uuid4().hex[:10]
        )

    order_id = f"vpn_{user['id']}_{uuid.uuid4().hex[:8]}"

    result = await platega.create_payment(
        order_id=order_id,
        amount=price_rub,
        description=f"Cerberus VPN - {devices} устр. на {period} дн.",
    )

    if not result or not result.get("success"):
        error_msg = result.get("error", "Неизвестная ошибка") if result else "Платежная система недоступна"
        logger.error(f"❌ Ошибка создания платежа Platega для юзера {callback.from_user.id}: {error_msg}")
        await callback.message.answer(
            f"❌ Ошибка создания счёта: {error_msg}\n\nПопробуйте еще раз или выберите другой способ оплаты.")
        return

    await db.add_pending_payment(
        invoice_id=order_id,
        user_id=user['id'],
        devices=devices,
        tariff_days=period,
        amount=price_rub
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить сейчас", url=result["payment_url"])],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_platega_{order_id}")]
    ])

    await callback.message.answer(
        f"💳 <b>Оплата через Platega</b>\n\n"
        f"💵 Сумма: <b>{price_rub} ₽</b>\n\n"
        f"1️⃣ Нажмите «Оплатить сейчас»\n"
        f"2️⃣ Выберите способ (Карта, СБП, SberPay)\n"
        f"3️⃣ После оплаты нажмите «Проверить оплату»\n\n"
        f"⚡️ Подписка выдаётся автоматически!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("check_platega_"), PurchaseState.waiting_payment)
async def check_platega_payment(callback: types.CallbackQuery, state: FSMContext):
    """Ручная проверка оплаты Platega (на случай если вебхук задерживается)"""
    from platega_client import platega

    order_id = callback.data.replace("check_platega_", "")

    payment_info = await db.get_pending_payment(order_id)
    if not payment_info:
        # Платежа уже нет в pending — значит вебхук его обработал и выдал подписку
        await callback.answer("✅ Оплата уже подтверждена, подписка выдана!", show_alert=True)
        return

    # У нас в БД нет сохранённого transaction_id Platega, поэтому просто сообщаем,
    # что ждём вебхук — сама выдача подписки происходит в webhook_server.py
    await callback.answer(
        "⏳ Ожидаем подтверждение от платёжной системы. Обычно это занимает 5-15 секунд. Если оплата прошла, подписка придёт автоматически!",
        show_alert=True)
# ==================== ТЕСТОВАЯ ОПЛАТА ====================

@router.callback_query(F.data == "test_payment", PurchaseState.waiting_payment)
async def test_payment(callback: types.CallbackQuery, state: FSMContext):
    """Тестовая оплата для админа"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("❌ Только для администраторов", show_alert=True)
        return

    data = await state.get_data()
    devices = data["devices"]
    period = data["period"]

    client_email = f"test_{uuid.uuid4().hex[:10]}"
    expiry_time = int(time.time() * 1000) + (period * 24 * 60 * 60 * 1000)

    await callback.message.answer("⏳ [ТЕСТ] Создаю подключение...")

    success = await panel.add_client_to_all_inbounds(
        email=client_email,
        expiry_time=expiry_time,
        limit_ip=devices
    )

    if not success:
        await callback.message.answer("❌ [ТЕСТ] Ошибка при создании подключения.")
        await state.clear()
        return

    user = await db.get_user(callback.from_user.id)
    if not user:
        await db.create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            referral_code=uuid.uuid4().hex[:10]
        )
        user = await db.get_user(callback.from_user.id)

    await db.add_subscription(
        user_id=user['id'],
        client_email=client_email,
        tariff_days=period,
        device_limit=devices,
        expiry_time=expiry_time
    )

    sub_link = await panel.get_subscription_link(client_email)

    if not sub_link:
        await callback.message.answer("⚠️ [ТЕСТ] Клиент создан, но не удалось получить ссылку подписки.")
        await state.clear()
        return

    period_name = config.PERIOD_NAMES.get(period, f"{period} дней")
    devices_text = pluralize_devices(devices)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    await callback.message.answer(
        f"🧪 <b>ТЕСТОВАЯ ОПЛАТА УСПЕШНА!</b>\n\n"
        f"📱 Устройства: {devices_text}\n"
        f"📅 Срок: {period_name}\n"
        f"🌍 Локаций: {len(config.ALL_INBOUNDS)}\n\n"
        f"Нажмите кнопку ниже, чтобы добавить подписку 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    await state.clear()


# ==================== ПРОВЕРКА ОПЛАТЫ ====================

@router.callback_query(F.data.startswith("check_payment_"),
                       PurchaseState.waiting_payment)
async def check_payment(callback: types.CallbackQuery, state: FSMContext):
    """Проверка оплаты"""
    invoice_id = int(callback.data.split("_")[-1])

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: get_invoice_sync(invoice_id)
        )

        if not result.get("ok"):
            raise Exception(result.get("error", {}).get("name", "Unknown error"))

        invoices = result["result"]["items"]
        invoice = invoices[0] if invoices else None

    except Exception as e:
        logger.error(f"Ошибка проверки оплаты: {e}")
        await callback.message.answer(f"❌ Ошибка проверки оплаты: {e}")
        return

    if not invoice or invoice["status"] != "paid":
        await callback.answer("⏳ Оплата ещё не подтверждена. Попробуйте через 10-20 секунд.", show_alert=True)
        return

    data = await state.get_data()
    devices = data["devices"]
    period = data["period"]

    client_email = f"user_{uuid.uuid4().hex[:10]}"
    expiry_time = int(time.time() * 1000) + (period * 24 * 60 * 60 * 1000)

    await callback.message.answer("⏳ Создаю подключение...")

    success = await panel.add_client_to_all_inbounds(
        email=client_email,
        expiry_time=expiry_time,
        limit_ip=devices
    )

    if not success:
        await callback.message.answer("❌ Ошибка при создании подключения. Напишите администратору.")
        await state.clear()
        return

    user = await db.get_user(callback.from_user.id)
    if not user:
        await db.create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            referral_code=uuid.uuid4().hex[:10]
        )
        user = await db.get_user(callback.from_user.id)

    await db.add_subscription(
        user_id=user['id'],
        client_email=client_email,
        tariff_days=period,
        device_limit=devices,
        expiry_time=expiry_time
    )

    await db.delete_pending_payment(invoice_id)

    sub_link = await panel.get_subscription_link(client_email)

    if not sub_link:
        await callback.message.answer("⚠️ Клиент создан, но не удалось получить ссылку подписки.")
        await state.clear()
        return

    period_name = config.PERIOD_NAMES.get(period, f"{period} дней")
    devices_text = pluralize_devices(devices)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    await callback.message.answer(
        f"✅ <b>Оплата подтверждена!</b>\n\n"
        f"📱 Устройства: {devices_text}\n"
        f"📅 Срок: {period_name}\n"
        f"🌍 Локаций: {len(config.ALL_INBOUNDS)}\n\n"
        f"Нажмите кнопку ниже, чтобы добавить подписку 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    await state.clear()