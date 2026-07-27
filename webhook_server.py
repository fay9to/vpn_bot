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

        await issue_subscription(
            user_id, devices, tariff_days, amount, asset,
            renewal_subscription_id=payment_info.get("renewal_subscription_id")
        )
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

        # Platega шлёт health-check пинг пустым телом без заголовков авторизации —
        # на него нужно ответить 200 OK, не отклоняя как неавторизованный запрос.
        merchant_header = request.headers.get("X-MerchantId", "")
        secret_header = request.headers.get("X-Secret", "")
        if not merchant_header and not secret_header and not body:
            logger.info("ℹ️ Platega webhook verification ping")
            return JSONResponse({"status": "ok"})

        # Проверяем авторизацию по заголовкам X-MerchantId / X-Secret
        if not platega.verify_webhook_auth(request.headers):
            logger.warning("⚠️ Webhook отклонен: неверные X-MerchantId/X-Secret")
            return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

        # Ключ сопоставления — transactionId ("id" в теле callback), а НЕ payload:
        # согласно офиц. документации Platega (CallbackPayload), в вебхуке
        # присутствуют только {id, amount, currency, status, paymentMethod} —
        # поля payload/orderId там нет.
        transaction_id = str(body.get("id") or "")
        status = str(body.get("status", "")).upper()
        amount = float(body.get("amount") or 0)

        logger.info(f"💰 Обработка Platega: TransactionId={transaction_id}, Status={status}, Amount={amount}")

        # Нас интересует только успешная оплата. По докам статус может быть
        # только PENDING / CANCELED / CONFIRMED / CHARGEBACKED.
        if status != "CONFIRMED":
            logger.info(f"ℹ️ Игнорируем статус: {status}")
            return JSONResponse({"status": "ok"})  # Важно вернуть 200 OK, чтобы Platega не спамила повторами

        # Ищем платеж в БД по transactionId (мы сохраняли его как invoice_id
        # в pending_payments сразу после успешного создания платежа)
        payment_info = await db.get_pending_payment(transaction_id)

        if not payment_info:
            logger.warning(f"⚠️ Транзакция {transaction_id} не найдена в pending_payments. Возможно, уже обработана.")
            return JSONResponse({"status": "ok"})  # Возвращаем OK, чтобы Platega перестал стучаться

        user_id = payment_info["user_id"]
        devices = payment_info["devices"]
        tariff_days = payment_info["tariff_days"]

        # Выдаем подписку
        logger.info(f"✅ Выдача подписки для user_id={user_id}, devices={devices}, days={tariff_days}")
        await issue_subscription(
            user_id, devices, tariff_days, amount, "RUB",
            renewal_subscription_id=payment_info.get("renewal_subscription_id")
        )

        # Удаляем из pending
        await db.delete_pending_payment(transaction_id)
        logger.info(f"✅ Webhook успешно обработан для транзакции {transaction_id}")

        return JSONResponse({"status": "ok", "message": "success"})

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в Platega webhook: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok"}


async def issue_subscription(user_id: int, devices: int, tariff_days: int, amount: float, currency: str,
                              renewal_subscription_id: int = None):
    """Выдача подписки после оплаты (новая) либо продление существующей"""
    from panel_client import XUIPanelClient, generate_client_email
    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    panel = XUIPanelClient()

    user = await db.get_user_by_id(user_id)
    if not user:
        logger.error(f"❌ User {user_id} not found")
        return

    period_title = config.PERIOD_NAMES.get(tariff_days, f"{tariff_days} дн.")
    period_emoji = config.PERIOD_EMOJIS.get(tariff_days, "📅")
    device_text = "♾️ Безлимит" if devices == 0 else f"{devices} устройств"
    bot = Bot(token=config.BOT_TOKEN)

    # ==================== ПРОДЛЕНИЕ существующей подписки ====================
    if renewal_subscription_id:
        subscription = await db.get_subscription_by_id(renewal_subscription_id)

        if not subscription or subscription["user_id"] != user_id:
            logger.error(f"❌ Продление: подписка {renewal_subscription_id} не найдена/не принадлежит юзеру {user_id}")
            # Не молчим — сообщаем админам, чтобы разобрались вручную, деньги-то уже пришли
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"⚠️ <b>Ошибка продления!</b>\n\n"
                        f"user_id={user_id}, renewal_subscription_id={renewal_subscription_id}\n"
                        f"Подписка не найдена. Оплата {amount:.2f} {currency} прошла, "
                        f"нужно продлить вручную!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            await bot.session.close()
            return

        now_ms = int(time.time() * 1000)
        base_time = max(subscription["expiry_time"], now_ms)
        new_expiry_time = base_time + tariff_days * 24 * 60 * 60 * 1000

        extended = await panel.extend_client_expiry(subscription["client_email"], new_expiry_time)

        if not extended:
            logger.error(f"❌ Не удалось продлить клиента {subscription['client_email']} на панели")
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"⚠️ <b>Ошибка продления на панели!</b>\n\n"
                        f"user_id={user_id}, client_email={subscription['client_email']}\n"
                        f"Оплата {amount:.2f} {currency} прошла, но панель не продлила клиента. "
                        f"Нужно продлить вручную!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            await bot.session.close()
            return

        await db.extend_subscription(renewal_subscription_id, new_expiry_time)

        await db.log_event(
            telegram_id=user['telegram_id'],
            event_type="renewal",
            username=user.get('username'),
            details=f"{tariff_days}d +{amount:.2f} {currency}, sub_id={renewal_subscription_id}"
        )

        sub_link = await panel.get_subscription_link(subscription["client_email"])
        keyboard_buttons = []
        if sub_link:
            keyboard_buttons.append([InlineKeyboardButton(text="📱 Моя ссылка подписки", url=sub_link)])
        keyboard_buttons.append([InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        try:
            await bot.send_message(
                user['telegram_id'],
                f"✅ <b>Подписка продлена!</b>\n\n"
                f"💵 Сумма: {amount:.2f} {currency}\n"
                f"➕ Добавлено: {period_emoji} {period_title}\n"
                f"📅 Новая дата окончания: "
                f"<code>{time.strftime('%d.%m.%Y %H:%M', time.localtime(new_expiry_time / 1000))}</code>\n\n"
                f"Ссылка и настройки VPN не изменились — переподключаться не нужно.",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Failed to notify user: {e}")

        for admin_id in config.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🔄 <b>Продление подписки!</b>\n\n"
                    f"👤 Пользователь: @{user['username'] or user['telegram_id']}\n"
                    f"💵 Сумма: {amount:.2f} {currency}\n"
                    f"➕ Срок: {period_title}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"❌ Failed to notify admin {admin_id}: {e}")

        await bot.session.close()
        return

    # ==================== НОВАЯ подписка ====================
    client_email = generate_client_email()
    expiry_time = int(time.time() * 1000) + (tariff_days * 24 * 60 * 60 * 1000)

    success = await panel.add_client_to_all_inbounds(
        email=client_email,
        expiry_time=expiry_time,
        limit_ip=devices
    )

    if not success:
        logger.error(f"❌ Failed to create client {client_email}")
        await bot.session.close()
        return

    await db.add_subscription(
        user_id=user_id,
        client_email=client_email,
        tariff_days=tariff_days,
        device_limit=devices,
        expiry_time=expiry_time
    )

    await db.log_event(
        telegram_id=user['telegram_id'],
        event_type="purchase",
        username=user.get('username'),
        details=f"{devices} устр., {tariff_days}d, {amount:.2f} {currency}, email={client_email}"
    )

    sub_link = await panel.get_subscription_link(client_email)

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
            f"📅 Срок: {period_emoji} {period_title}\n\n"
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
                f"📅 Срок: {period_title}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Failed to notify admin {admin_id}: {e}")

    await bot.session.close()


def start_webhook_server():
    """Запускает webhook сервер"""
    import uvicorn
    uvicorn.run(app, host=config.WEBHOOK_HOST, port=config.WEBHOOK_PORT, log_level="info")