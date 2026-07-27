# subscription_gate.py
"""
Обязательная подписка на канал. Пока пользователь не подписан на
config.REQUIRED_CHANNEL_USERNAME, бот не выполняет никаких его действий —
ни команды, ни нажатия на инлайн-кнопки — и вместо этого показывает
предложение подписаться с кнопкой повторной проверки.
"""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Router, F, types
from aiogram.types import TelegramObject, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import config

logger = logging.getLogger(__name__)

router = Router()

# callback_data, которым разрешено проходить сквозь гейт без проверки подписки —
# иначе сама кнопка "Я подписался" никогда бы не смогла сработать.
_ALLOWED_CALLBACKS = {"check_subscription"}

_NOT_SUBSCRIBED_STATUSES = {"left", "kicked"}


def _gate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=config.REQUIRED_CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")],
    ])


_GATE_TEXT = (
    "🔒 <b>Доступ ограничен</b>\n\n"
    f"Чтобы пользоваться ботом, подпишитесь на наш канал {config.REQUIRED_CHANNEL_USERNAME}, "
    "а затем нажмите «Я подписался»."
)


async def is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=config.REQUIRED_CHANNEL_USERNAME, user_id=user_id)
        return member.status not in _NOT_SUBSCRIBED_STATUSES
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        # Канал недоступен / бот не может проверить (например, неверно указан
        # username, или бот не состоит в канале) — не блокируем пользователей
        # из-за проблемы конфигурации на нашей стороне, но громко логируем.
        logger.error(f"❌ Не удалось проверить подписку на {config.REQUIRED_CHANNEL_USERNAME}: {e}")
        return True
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка проверки подписки: {e}")
        return True


class ChannelSubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        # Админам подписка не требуется — им нужен беспрепятственный доступ к боту.
        if user.id in config.ADMIN_IDS:
            return await handler(event, data)

        callback_data = getattr(event, "data", None)  # для CallbackQuery
        if callback_data in _ALLOWED_CALLBACKS:
            return await handler(event, data)

        bot = data.get("bot")
        if await is_subscribed(bot, user.id):
            return await handler(event, data)

        logger.info(f"🔒 Пользователь {user.id} не подписан на {config.REQUIRED_CHANNEL_USERNAME}, действие заблокировано")

        if isinstance(event, types.CallbackQuery):
            await event.answer("Подпишитесь на канал, чтобы пользоваться ботом", show_alert=True)
            target = event.message
        else:
            target = event

        try:
            await target.answer(_GATE_TEXT, reply_markup=_gate_keyboard(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Не удалось показать сообщение о подписке: {e}")

        return None  # не пропускаем событие дальше к обработчикам


@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery):
    if await is_subscribed(callback.bot, callback.from_user.id):
        await callback.answer("✅ Спасибо за подписку!")
        # Показать главное меню после успешной проверки
        from handlers.main_menu import show_main_menu
        await show_main_menu(callback.message)
    else:
        await callback.answer("❌ Похоже, вы всё ещё не подписаны. Подпишитесь и попробуйте снова.", show_alert=True)