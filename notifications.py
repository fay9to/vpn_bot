# notifications.py
"""
Периодические уведомления пользователям:
- подписка скоро истекает (за NOTIFY_EXPIRY_HOURS_BEFORE часов)
- подписка истекла
- заканчивается трафик (>= NOTIFY_TRAFFIC_THRESHOLD_PERCENT % от лимита)

Работает как фоновая asyncio-задача внутри того же процесса бота
(см. bot.py) — отдельный сервис/крон не нужен.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

import config
from database import db

logger = logging.getLogger(__name__)

_BUY_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="buy_subscription")],
])


async def _safe_send(bot: Bot, telegram_id: int, text: str, keyboard: InlineKeyboardMarkup = None):
    try:
        await bot.send_message(telegram_id, text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramForbiddenError:
        logger.info(f"ℹ️ Пользователь {telegram_id} заблокировал бота — пропускаем уведомление")
    except TelegramBadRequest as e:
        logger.warning(f"⚠️ Не удалось отправить уведомление {telegram_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления {telegram_id}: {e}")


async def check_expiring_subscriptions(bot: Bot):
    """Подписки, которые истекут в ближайшие NOTIFY_EXPIRY_HOURS_BEFORE часов."""
    subs = await db.get_subscriptions_expiring_soon(config.NOTIFY_EXPIRY_HOURS_BEFORE)

    for sub in subs:
        hours_left = max(0, round((sub["expiry_time"] - _now_ms()) / (60 * 60 * 1000)))
        text = (
            f"⏰ <b>Ваша подписка скоро закончится!</b>\n\n"
            f"Осталось примерно <b>{hours_left} ч.</b>\n\n"
            f"Продлите подписку заранее, чтобы не потерять доступ 👇"
        )
        await _safe_send(bot, sub["telegram_id"], text, _BUY_KEYBOARD)
        await db.mark_subscription_notified(sub["id"], "notified_expiry_soon")
        logger.info(f"📨 Уведомление об истечении отправлено user={sub['telegram_id']} sub_id={sub['id']}")


async def check_expired_subscriptions(bot: Bot):
    """Подписки, которые уже истекли."""
    subs = await db.get_expired_unnotified_subscriptions()

    for sub in subs:
        text = (
            f"❌ <b>Ваша подписка закончилась</b>\n\n"
            f"Доступ к VPN приостановлен. Продлите подписку, чтобы продолжить пользоваться сервисом 👇"
        )
        await _safe_send(bot, sub["telegram_id"], text, _BUY_KEYBOARD)
        await db.mark_subscription_notified(sub["id"], "notified_expired")
        logger.info(f"📨 Уведомление об истечении подписки отправлено user={sub['telegram_id']} sub_id={sub['id']}")


async def check_low_traffic(bot: Bot):
    """Подписки с лимитом трафика, у которых израсходовано >= NOTIFY_TRAFFIC_THRESHOLD_PERCENT %."""
    from panel_client import XUIPanelClient
    panel = XUIPanelClient()

    subs = await db.get_active_subscriptions_for_traffic_check()

    for sub in subs:
        try:
            traffic = await panel.get_client_traffic(sub["client_email"])
        except Exception as e:
            logger.error(f"❌ Не удалось получить трафик для {sub['client_email']}: {e}")
            continue

        if not traffic:
            continue

        total = traffic.get("total") or 0
        if total <= 0:
            continue  # безлимитный тариф — трафик не проверяем

        used = (traffic.get("up") or 0) + (traffic.get("down") or 0)
        used_percent = (used / total) * 100

        if used_percent >= config.NOTIFY_TRAFFIC_THRESHOLD_PERCENT:
            used_gb = used / (1024 ** 3)
            total_gb = total / (1024 ** 3)
            text = (
                f"📶 <b>Заканчивается трафик</b>\n\n"
                f"Использовано: <b>{used_gb:.1f} / {total_gb:.1f} ГБ</b> "
                f"({used_percent:.0f}%)\n\n"
                f"Продлите или обновите подписку, чтобы не остаться без доступа 👇"
            )
            await _safe_send(bot, sub["telegram_id"], text, _BUY_KEYBOARD)
            await db.mark_subscription_notified(sub["id"], "notified_traffic_low")
            logger.info(f"📨 Уведомление о трафике отправлено user={sub['telegram_id']} sub_id={sub['id']}")


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


async def notifications_loop(bot: Bot):
    """Бесконечный цикл — проверяет всё раз в NOTIFY_CHECK_INTERVAL_MINUTES минут."""
    logger.info(
        f"🔔 Фоновая проверка уведомлений запущена "
        f"(интервал {config.NOTIFY_CHECK_INTERVAL_MINUTES} мин.)"
    )
    while True:
        try:
            await check_expiring_subscriptions(bot)
            await check_expired_subscriptions(bot)
            await check_low_traffic(bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле уведомлений: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(config.NOTIFY_CHECK_INTERVAL_MINUTES * 60)