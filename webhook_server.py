# webhook_server.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import hmac
import hashlib
import json
import asyncio
import time
import uuid
import logging
import config
from database import db
from platega_client import platega

logger = logging.getLogger(__name__)

# СНАЧАЛА создаём приложение
app = FastAPI()


# ПОТОМ все обработчики
@app.post("/webhook/cryptobot")
async def cryptobot_webhook(request: Request):
    """Webhook для CryptoBot"""
    try:
        body = await request.json()
        logger.info(f"📩 CryptoBot webhook received")

        update_type = body.get("update_type")
        if update_type != "invoice_paid":
            return JSONResponse({"status": "ok"})

        invoice = body.get("payload", {})
        invoice_id = invoice.get("invoice_id")
        amount = float(invoice.get("amount", 0))
        asset = invoice.get("asset")

        logger.info(f"💰 Invoice {invoice_id} paid: {amount} {asset}")

        payment_info = await db.get_pending_payment(invoice_id)

        if not payment_info:
            logger.warning(f"⚠️ Invoice {invoice_id} not found in pending")
            return JSONResponse({"status": "ok"})

        user_id = payment_info["user_id"]
        devices = payment_info["devices"]
        tariff_days = payment_info["tariff_days"]

        tariff = next((t for t in config.TARIFFS if t.days == tariff_days), None)
        if not tariff:
            logger.error(f"❌ Tariff {tariff_days} not found")
            return JSONResponse({"status": "error"}, status_code=500)

        await issue_subscription(user_id, devices, tariff, amount, asset)
        await db.delete_pending_payment(invoice_id)

        return JSONResponse({"status": "ok"})

    except Exception as e:
        logger.error(f"❌ CryptoBot webhook error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error"}, status_code=500)


@app.post("/webhook/platega")
async def platega_webhook(request: Request):
    """Webhook для Platega"""
    try:
        # Логируем ВСЁ, что приходит от Platega, для отладки
        logger.info(f"📩 Входящий запрос Platega Webhook")
        logger.info(f"Headers: {dict(request.headers)}")

        try:
            body = await request.json()
            logger.info(f"Body (JSON): {body}")
        except Exception:
            form = await request.form()
            body = dict(form)
            logger.info(f"Body (Form): {body}")

        from platega_client import platega

        received_signature = body.get("signature", "")

        # Проверяем подпись
        if not platega.verify_webhook_signature(body, received_signature):
            logger.warning("⚠️ Webhook отклонен: неверная подпись")
            # Возвращаем 401, чтобы Platega знал, что мы его не приняли
            return JSONResponse({"status": "error", "message": "Invalid signature"}, status_code=401)

        order_id = str(body.get("orderId") or body.get("order_id"))
        status = str(body.get("status", "")).upper()
        amount = float(body.get("amount", 0))

        logger.info(f"💰 Обработка Platega: Order={order_id}, Status={status}, Amount={amount}")

        # Нас интересует только успешная оплата
        if status not in ["CONFIRMED", "SUCCESS", "COMPLETED", "PAID"]:
            logger.info(f"ℹ️ Игнорируем статус: {status}")
            return JSONResponse({"status": "ok"})  # Важно вернуть 200 OK, чтобы Platega не спамил重试

        # Ищем платеж в БД
        payment_info = await db.get_pending_payment(order_id)

        if not payment_info:
            logger.warning(f"⚠️ Заказ {order_id} не найден в pending_payments. Возможно, уже обработан.")
            return JSONResponse({"status": "ok"})  # Возвращаем OK, чтобы Platega перестал стучаться

        user_id = payment_info["user_id"]
        devices = payment_info["devices"]
        tariff_days = payment_info["tariff_days"]

        tariff = next((t for t in config.TARIFFS if t.days == tariff_days), None)
        if not tariff:
            logger.error(f"❌ Тариф {tariff_days} дней не найден в config.py")
            return JSONResponse({"status": "error"}, status_code=500)

        # Выдаем подписку
        logger.info(f"✅ Выдача подписки для user_id={user_id}, devices={devices}, days={tariff_days}")
        await issue_subscription(user_id, devices, tariff, amount, "RUB")

        # Удаляем из pending
        await db.delete_pending_payment(order_id)
        logger.info(f"✅ Webhook успешно обработан для заказа {order_id}")

        return JSONResponse({"status": "ok", "message": "success"})

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в Platega webhook: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok"}


async def issue_subscription(user_id: int, devices: int, tariff, amount: float, currency: str):
    """Выдача подписки после оплаты"""
    from panel_client import XUIPanelClient
    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    panel = XUIPanelClient()

    user = await db.get_user_by_id(user_id)
    if not user:
        logger.error(f"❌ User {user_id} not found")
        return

    client_email = f"user_{uuid.uuid4().hex[:10]}"
    expiry_time = int(time.time() * 1000) + (tariff.days * 24 * 60 * 60 * 1000)

    success = await panel.add_client_to_all_inbounds(
        email=client_email,
        expiry_time=expiry_time,
        limit_ip=devices
    )

    if not success:
        logger.error(f"❌ Failed to create client {client_email}")
        return

    await db.add_subscription(
        user_id=user_id,
        client_email=client_email,
        tariff_days=tariff.days,
        device_limit=devices,
        expiry_time=expiry_time
    )

    bot = Bot(token=config.BOT_TOKEN)
    sub_link = await panel.get_subscription_link(client_email)

    device_text = "♾️ Безлимит" if devices == 0 else f"{devices} устройств"

    keyboard_buttons = []
    if sub_link:
        keyboard_buttons.append([InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)])

    keyboard_buttons.extend([
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    try:
        await bot.send_message(
            user['telegram_id'],
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"💵 Сумма: {amount:.2f} {currency}\n"
            f"📱 Устройства: {device_text}\n"
            f"📅 Срок: {tariff.emoji} {tariff.title}\n"
            f"🌍 Локаций: Все ({len(config.ALL_INBOUNDS)})\n\n"
            f"Нажмите кнопку ниже для подключения 👇",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Failed to notify user: {e}")

    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Новая оплата!</b>\n\n"
                f"👤 Пользователь: @{user['username'] or user['telegram_id']}\n"
                f"💵 Сумма: {amount:.2f} {currency}\n"
                f"📱 Устройства: {device_text}\n"
                f"📅 Срок: {tariff.title}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Failed to notify admin {admin_id}: {e}")

    await bot.session.close()


def start_webhook_server():
    """Запускает webhook сервер"""
    import uvicorn
    uvicorn.run(app, host=config.WEBHOOK_HOST, port=config.WEBHOOK_PORT, log_level="info")