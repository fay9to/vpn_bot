from aiogram import types, Router
from aiogram.filters import Command
import config
from database import db

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # Add user to database
    await db.add_user(message.from_user.id, message.from_user.username)

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text="💳 Купить VPN",
            callback_data="buy"
        )],
        [types.InlineKeyboardButton(
            text="👤 Мой профиль",
            callback_data="profile"
        )],
        [types.InlineKeyboardButton(
            text="📞 Поддержка",
            callback_data="support"
        )],
    ])

    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"🚀 <b>CerberusVPN</b> - быстрый и надёжный VPN\n\n"
        f"🌍 <b>Доступные локации:</b>\n"
        f"• 🇱🇻 Латвия\n"
        f"• 🇳🇱 Нидерланды\n\n"
        f"⚡ Мгновенная выдача после оплаты\n"
        f"📱 Работает на всех устройствах\n\n"
        f"Нажмите 'Купить VPN' чтобы начать!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == "profile")
async def profile(callback: types.CallbackQuery):
    subscription = await db.get_subscription(callback.from_user.id)

    if subscription:
        await callback.answer("🔜 Функция в разработке", show_alert=True)
    else:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)


@router.callback_query(lambda c: c.data == "support")
async def support(callback: types.CallbackQuery):
    await callback.message.answer(
        "📞 <b>Поддержка</b>\n\n"
        "Если у вас возникли вопросы, напишите нам:\n"
        f"@{config.ADMIN_IDS}" if config.ADMIN_IDS else "Администратору"
    )