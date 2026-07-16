# handlers/main_menu.py
from aiogram import types, Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import qrcode
import io
from database import db
import time
import uuid
import logging
import config
from pathlib import Path

logger = logging.getLogger(__name__)
router = Router()

# Путь к приветственному изображению
WELCOME_IMAGE = Path("/root/vpn_bot/welcome.jpg")


class GiftState(StatesGroup):
    entering_code = State()


# ==================== КОМАНДЫ ====================

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    logger.info(f"📩 Получена команда /start от {message.from_user.id}")
    await state.clear()

    args = message.text.split()

    if len(args) > 1:
        arg = args[1]
        if arg.startswith("gift_"):
            gift_code = arg.replace("gift_", "")
            await handle_gift_code(message, gift_code, state)
            return

        referral_code = arg
        await handle_referral(message, referral_code)
    else:
        await show_main_menu(message)


# ==================== ГЛАВНОЕ МЕНЮ ====================

async def show_main_menu(message: types.Message):
    logger.info(f"📋 Показ главного меню для {message.from_user.id}")

    try:
        user = await db.get_user(message.from_user.id)

        if not user:
            logger.info(f"🆕 Создание нового пользователя {message.from_user.id}")
            await db.create_user(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                referral_code=uuid.uuid4().hex[:10]
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription"),
                InlineKeyboardButton(text="🎁 Пробная подписка", callback_data="trial_subscription")
            ],
            [
                InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile"),
                InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")
            ],
            [
                InlineKeyboardButton(text="💬 Поддержка", callback_data="support"),
                InlineKeyboardButton(text="📢 Канал", callback_data="channel")
            ],
            [
                InlineKeyboardButton(text="💰 Тарифы", callback_data="tariffs_info"),
                InlineKeyboardButton(text="📄 Документы", callback_data="documents")
            ],
            [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="about_service")]
        ])

        # Нейтральный текст БЕЗ VPN-триггеров
        welcome_text = (
            "<b>Добро пожаловать в Cerberus VPN</b>\n\n"
            "🔥 <b>CerberusVPN</b> — сервис защищённого соединения! 🌍✨\n\n"
            "🚀 <b>Наши преимущества:</b>\n"
            "🔹 Протокол Hysteria2 (высокая скорость)\n"
            "🔹 Шифрование данных\n"
            "🔹 Стабильное соединение\n"
            "🔹 3 локации: 🇱🇻 🇳🇱 🇫🇮\n"
            "🔹 Отзывчивая поддержка\n"
            "🔹 Реферальная программа: 3-уровневая\n\n"
            "🎯 Попробуй наш сервис совершенно бесплатно 👇"
        )

        # Отправляем с фото если оно существует
        if WELCOME_IMAGE.exists():
            with open(WELCOME_IMAGE, "rb") as image_file:
                await message.answer_photo(
                    photo=types.BufferedInputFile(
                        image_file.read(),
                        filename="cerberus_welcome.jpg"
                    ),
                    caption=welcome_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        else:
            await message.answer(
                welcome_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

        logger.info(f"✅ Главное меню отправлено")
    except Exception as e:
        logger.error(f"Ошибка показа меню: {e}")
        import traceback
        traceback.print_exc()


# ==================== ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ ====================

@router.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription"),
            InlineKeyboardButton(text="🎁 Пробная подписка", callback_data="trial_subscription")
        ],
        [
            InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile"),
            InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")
        ],
        [
            InlineKeyboardButton(text="💬 Поддержка", callback_data="support"),
            InlineKeyboardButton(text="📢 Канал", callback_data="channel")
        ],
        [
            InlineKeyboardButton(text="💰 Тарифы", callback_data="tariffs_info"),
            InlineKeyboardButton(text="📄 Документы", callback_data="documents")
        ],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="about_service")]
    ])

    welcome_text = (
        "<b>Добро пожаловать в Cerberus VPN</b>\n\n"
        "🔥 <b>CerberusVPN</b> — сервис защищённого соединения! 🌍✨\n\n"
        "🚀 <b>Наши преимущества:</b>\n"
        "🔹 Протокол Hysteria2 (высокая скорость)\n"
        "🔹 Шифрование данных\n"
        "🔹 Стабильное соединение\n"
        "🔹 Несколько локаций\n"
        "🔹 Отзывчивая поддержка\n"
        "🔹 Реферальная программа: 3-уровневая\n\n"
        "🎯 Попробуй наш сервис совершенно бесплатно 👇"
    )

    await callback.message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== ТАРИФЫ ====================

@router.callback_query(F.data == "tariffs_info")
async def tariffs_info(callback: types.CallbackQuery):
    """Информация о тарифах"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    tariffs_text = (
        "💰 <b>Тарифы CerberusVPN</b>\n\n"
        "📱 <b>3 устройства (3 IP):</b>\n"
        "🗓️ 30 дней — 79 ₽\n"
        "📅 90 дней — 239 ₽\n"
        "📆 180 дней — 449 ₽\n"
        "🎉 365 дней — 849 ₽\n\n"
        "📱 <b>5 устройств (5 IP):</b>\n"
        "🗓️ 30 дней — 99 ₽\n"
        "📅 90 дней — 259 ₽\n"
        "📆 180 дней — 469 ₽\n"
        "🎉 365 дней — 869 ₽\n\n"
        "📱 <b>10 устройств (10 IP):</b>\n"
        "🗓️ 30 дней — 199 ₽\n"
        "📅 90 дней — 459 ₽\n"
        "📆 180 дней — 869 ₽\n"
        "🎉 365 дней — 1669 ₽\n\n"
        "🎁 <b>Пробная подписка:</b> бесплатно\n"
        "⏰ 3 дня / 3 устройства / 10 ГБ\n\n"
        "💡 Все тарифы включают:\n"
        "• Все локации (🇱🇻 + 🇳🇱 + 🇫🇮)\n"
        "• Протокол Hysteria2\n"
        "• Техническую поддержку 24/7"
    )

    await callback.message.answer(
        tariffs_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== ДОКУМЕНТЫ ====================

@router.callback_query(F.data == "documents")
async def documents(callback: types.CallbackQuery):
    """Документы сервиса"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📜 Политика конфиденциальности",
            url="https://telegra.ph/Politika-konfidencialnosti-06-21-31"
        )],
        [InlineKeyboardButton(
            text="📋 Пользовательское соглашение",
            url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    await callback.message.answer(
        "📄 <b>Документы сервиса</b>\n\n"
        "Ознакомьтесь с документами, регулирующими использование сервиса:\n\n"
        "🔹 Политика конфиденциальности\n"
        "🔹 Пользовательское соглашение\n\n"
        "Нажмите на кнопку для просмотра документа 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== ПРОБНАЯ ПОДПИСКА ====================

@router.callback_query(F.data == "trial_subscription")
async def trial_subscription(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    subscription = await db.get_active_subscription(user['id'])
    if subscription:
        await callback.answer(
            "⚠️ У вас уже есть активная подписка!\n"
            "Пробную подписку можно получить только один раз.",
            show_alert=True
        )
        return

    await callback.answer("⏳ Создаю пробную подписку...")

    from panel_client import XUIPanelClient
    panel = XUIPanelClient()

    client_email = f"trial_{uuid.uuid4().hex[:10]}"
    expiry_time = int(time.time() * 1000) + (3 * 24 * 60 * 60 * 1000)
    total_gb = 10 * 1024 * 1024 * 1024

    try:
        success = await panel.add_client_to_all_inbounds(
            email=client_email,
            expiry_time=expiry_time,
            limit_ip=3,
            total_gb=total_gb
        )

        if not success:
            await callback.message.answer("❌ Ошибка при создании пробной подписки.")
            return

        await db.add_subscription(
            user_id=user['id'],
            client_email=client_email,
            tariff_days=3,
            device_limit=3,
            expiry_time=expiry_time
        )

        sub_link = await panel.get_subscription_link(client_email)

        if not sub_link:
            await callback.message.answer("⚠️ Клиент создан, но не удалось получить ссылку подписки.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)],
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])

        await callback.message.answer(
            f"🎁 <b>Пробная подписка активирована!</b>\n\n"
            f"⏰ Срок: 3 дня\n"
            f"📱 Устройств: 3\n"
            f"💾 Трафик: 10 ГБ\n"
            f"🌍 Локаций: Все\n\n"
            f"Нажмите кнопку ниже, чтобы добавить подписку 👇",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка пробной подписки: {e}")
        import traceback
        traceback.print_exc()
        await callback.message.answer(f"❌ Ошибка: {e}")


# ==================== ПОДДЕРЖКА ====================

@router.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать в поддержку", url="https://t.me/basir1337")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    await callback.message.answer(
        "💬 <b>Поддержка Cerberus VPN</b>\n\n"
        "Если у вас возникли вопросы или проблемы:\n\n"
        "📧 Напишите в нашу поддержку\n"
        "⏰ Время ответа: обычно до 1 часа\n"
        "🌐 Работаем 24/7",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== КАНАЛ ====================

@router.callback_query(F.data == "channel")
async def channel(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url="https://t.me/cerberusvpn")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    await callback.message.answer(
        "📢 <b>Наш канал</b>\n\n"
        "Подпишитесь, чтобы быть в курсе:\n\n"
        "📰 Новостей и обновлений\n"
        "🎁 Акции и промокоды\n"
        "📚 Инструкции по настройке\n"
        "💡 Полезные советы",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== О СЕРВИСЕ (БЕЗ VPN-ТРИГГЕРОВ) ====================

@router.callback_query(F.data == "about_service")
async def about_service(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    await callback.message.answer(
        "ℹ️ <b>О сервисе Cerberus VPN</b>\n\n"
        "🔐 <b>Безопасность:</b>\n"
        "• Современное шифрование данных\n"
        "• Защита передаваемой информации\n"
        "• Без логов и сохранения истории\n\n"
        "⚡ <b>Скорость:</b>\n"
        "• Серверы в 🇱🇻 Латвии, 🇳🇱 Нидерландах и 🇫🇮 Финляндии\n"
        "• Протокол Hysteria2\n"
        "• До 1 Гбит/с\n\n"
        "📱 <b>Совместимость:</b>\n"
        "• iOS / Android / Windows / macOS / Linux\n"
        "• Роутеры и Smart TV\n\n"
        "💳 <b>Оплата:</b>\n"
        "• Банковские карты РФ\n"
        "• СБП (Система быстрых платежей)\n"
        "• USDT (CryptoBot)\n"
        "• Моментальная выдача\n\n"
        "🎁 <b>Бонусы:</b>\n"
        "• 3-уровневая реферальная программа\n"
        "• Пробная подписка: 3 дня / 3 устройства / 10 ГБ\n"
        "• Промокоды и акции",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== ЛИЧНЫЙ КАБИНЕТ ====================

@router.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    subscription = await db.get_active_subscription(user['id'])

    if subscription:
        now_ms = int(time.time() * 1000)
        days_left = max(0, (subscription['expiry_time'] - now_ms) // (24 * 60 * 60 * 1000))
        hours_left = max(0, ((subscription['expiry_time'] - now_ms) // (60 * 60 * 1000)) % 24)
        tariff_text = f"{days_left} дн. {hours_left} ч. осталось"

        from panel_client import XUIPanelClient
        panel = XUIPanelClient()
        sub_link = await panel.get_subscription_link(subscription['client_email'])

        if not sub_link:
            sub_link = None

        device_text = f"{subscription['device_limit']} IP"
    else:
        tariff_text = "Нет активной подписки"
        sub_link = None
        device_text = "-"

    keyboard_buttons = []

    if sub_link:
        keyboard_buttons.append([InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)])

    keyboard_buttons.extend([
        [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="renew_subscription")],
        [InlineKeyboardButton(text="⚙️ Управление подпиской", callback_data="manage_subscription")],
        [
            InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
            InlineKeyboardButton(text="🎁 Подарить", callback_data="gift")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.answer(
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user['telegram_id']}</code>\n"
        f"👤 <b>Username:</b> @{user['username'] or 'не указан'}\n"
        f"💰 <b>Баланс:</b> {user['balance']:.2f} ₽\n\n"
        f"📅 <b>Подписка:</b> {tariff_text}\n"
        f"📱 <b>Устройств:</b> {device_text}\n"
        f"🌍 <b>Локаций:</b> Все (🇱🇻 + 🇳🇱 + 🇫🇮)",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== БАЛАНС ====================

@router.callback_query(F.data == "balance")
async def balance(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    transactions = await db.get_transactions(user['id'], limit=5)

    transactions_text = ""
    if transactions:
        transactions_text = "\n\n📜 <b>Последние операции:</b>\n"
        for tx in transactions:
            sign = "+" if tx['amount'] > 0 else ""
            emoji = "💰" if tx['amount'] > 0 else "💸"
            date = tx['created_at'][:16] if tx['created_at'] else ""
            desc = tx['description'] or tx['type']
            transactions_text += f"{emoji} {sign}{tx['amount']:.2f} ₽ — {desc}\n   <i>{date}</i>\n"
    else:
        transactions_text = "\n\n📜 <i>История операций пуста</i>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="top_up_balance")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
    ])

    await callback.message.answer(
        f"💰 <b>Ваш баланс</b>\n\n"
        f"💵 <b>Доступно:</b> {user['balance']:.2f} ₽\n\n"
        f"💡 Баланс можно пополнить через:\n"
        f"• Реферальную программу\n"
        f"• Подарочные коды\n"
        f"• Прямое пополнение{transactions_text}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "top_up_balance")
async def top_up_balance(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Пополнить через поддержку", url="https://t.me/basir1337")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="balance")]
    ])

    await callback.message.answer(
        "💳 <b>Пополнение баланса</b>\n\n"
        "Для пополнения баланса напишите в поддержку:\n\n"
        "📧 @basir1337\n\n"
        "💵 Доступные способы:\n"
        "• Банковская карта\n"
        "• СБП\n"
        "• USDT (CryptoBot)\n"
        "• Другие способы (уточняйте)",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== ПРОДЛЕНИЕ ПОДПИСКИ ====================

@router.callback_query(F.data == "renew_subscription")
async def renew_subscription(callback: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    subscription = await db.get_active_subscription(user['id'])

    if not subscription:
        await callback.answer("⚠️ У вас нет активной подписки!", show_alert=True)
        from handlers.purchase import start_purchase
        await start_purchase(callback, state)
        return

    current_devices = subscription['device_limit']

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📱 Продлить ({current_devices} устройств)",
            callback_data=f"devices_{current_devices}"
        )],
        [InlineKeyboardButton(text="💳 Купить новый тариф", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
    ])

    await callback.message.answer(
        f"🔄 <b>Продление подписки</b>\n\n"
        f"📱 Ваш текущий тариф: <b>{current_devices} устройств</b>\n\n"
        f"💡 Выберите действие:\n"
        f"• Продлить текущий тариф\n"
        f"• Купить новый тариф с другим количеством устройств",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== УПРАВЛЕНИЕ ПОДПИСКОЙ ====================

@router.callback_query(F.data == "manage_subscription")
async def manage_subscription(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    subscription = await db.get_active_subscription(user['id'])

    if not subscription:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
        ])

        await callback.message.answer(
            "⚠️ <b>У вас нет активной подписки</b>\n\n"
            "Вы можете купить новую подписку.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    now_ms = int(time.time() * 1000)
    days_left = max(0, (subscription['expiry_time'] - now_ms) // (24 * 60 * 60 * 1000))
    hours_left = max(0, ((subscription['expiry_time'] - now_ms) // (60 * 60 * 1000)) % 24)

    device_text = f"{subscription['device_limit']} IP"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="renew_subscription")],
        [InlineKeyboardButton(text="📱 Мои устройства", callback_data="my_devices")],
        [InlineKeyboardButton(text="📊 Статистика трафика", callback_data="traffic_stats")],
        [InlineKeyboardButton(text="📜 История подписок", callback_data="subscription_history")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
    ])

    await callback.message.answer(
        f"⚙️ <b>Управление подпиской</b>\n\n"
        f"📅 <b>Осталось:</b> {days_left} дн. {hours_left} ч.\n"
        f"📱 <b>Устройств:</b> {device_text}\n"
        f"🌍 <b>Локаций:</b> Все (🇱🇻 + 🇳🇱 + 🇫🇮)\n\n"
        f"🆔 <b>Email клиента:</b>\n<code>{subscription['client_email']}</code>\n\n"
        f"📅 <b>Дата окончания:</b>\n"
        f"<code>{time.strftime('%d.%m.%Y %H:%M', time.localtime(subscription['expiry_time'] / 1000))}</code>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "my_devices")
async def my_devices(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    subscription = await db.get_active_subscription(user['id'])

    if not subscription:
        await callback.answer("⚠️ Нет активной подписки", show_alert=True)
        return

    from panel_client import XUIPanelClient
    panel = XUIPanelClient()

    sub_link = await panel.get_subscription_link(subscription['client_email'])

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)] if sub_link else [],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="manage_subscription")]
    ])

    device_text = f"{subscription['device_limit']} IP"

    await callback.message.answer(
        f"📱 <b>Мои устройства</b>\n\n"
        f"🔒 Лимит устройств: {device_text}\n\n"
        f"💡 Чтобы подключить новое устройство:\n"
        f"1. Нажмите кнопку ниже\n"
        f"2. Добавьте подписку в приложение\n"
        f"3. Подключитесь к серверу\n\n"
        f"📱 Поддерживаемые приложения:\n"
        f"• Hysteria 2\n"
        f"• V2RayNG (Android)\n"
        f"• Shadowrocket (iOS)\n"
        f"• Streisand (iOS)\n"
        f"• Clash (Windows/Mac)",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "traffic_stats")
async def traffic_stats(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    subscription = await db.get_active_subscription(user['id'])

    if not subscription:
        await callback.answer("⚠️ Нет активной подписки", show_alert=True)
        return

    from panel_client import XUIPanelClient
    panel = XUIPanelClient()

    client_info = await panel.get_client_info(subscription['client_email'])

    if not client_info:
        await callback.answer("❌ Не удалось получить статистику", show_alert=True)
        return

    client_data = client_info.get('client', {})
    up_bytes = client_data.get('up', 0) or 0
    down_bytes = client_data.get('down', 0) or 0
    total_bytes = client_data.get('totalGB', 0) or 0

    def format_bytes(b):
        if b == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if b < 1024:
                return f"{b:.2f} {unit}"
            b /= 1024
        return f"{b:.2f} PB"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="manage_subscription")]
    ])

    await callback.message.answer(
        f"📊 <b>Статистика трафика</b>\n\n"
        f"⬆️ <b>Отправлено:</b> {format_bytes(up_bytes)}\n"
        f"⬇️ <b>Получено:</b> {format_bytes(down_bytes)}\n"
        f"📊 <b>Всего использовано:</b> {format_bytes(up_bytes + down_bytes)}\n"
        f"💾 <b>Лимит трафика:</b> {format_bytes(total_bytes) if total_bytes > 0 else '♾️ Безлимит'}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "subscription_history")
async def subscription_history(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    subscriptions = await db.get_all_subscriptions(user['id'])

    if not subscriptions:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="manage_subscription")]
        ])

        await callback.message.answer(
            "📜 <b>История подписок</b>\n\n"
            "<i>История пуста</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    now_ms = int(time.time() * 1000)
    history_text = "📜 <b>История подписок</b>\n\n"

    for sub in subscriptions[:5]:
        status = "✅ Активна" if sub['expiry_time'] > now_ms else "⏹️ Истекла"
        date_end = time.strftime('%d.%m.%Y', time.localtime(sub['expiry_time'] / 1000))
        device_text = f"{sub['device_limit']} IP"

        history_text += (
            f"📅 <b>{sub['tariff_days']} дней</b> — {status}\n"
            f"   📱 {device_text} | ⏰ до {date_end}\n\n"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="manage_subscription")]
    ])

    await callback.message.answer(
        history_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ==================== ПОДАРОЧНЫЕ КОДЫ ====================

@router.callback_query(F.data == "gift")
async def gift(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Активировать код", callback_data="activate_gift")],
        [InlineKeyboardButton(text="🎟️ Создать подарок", callback_data="create_gift")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
    ])

    await callback.message.answer(
        "🎁 <b>Подарочные коды</b>\n\n"
        "🎟️ <b>Активировать код:</b>\n"
        "Введите подарочный код, полученный от друга или купленный в магазине\n\n"
        "🎁 <b>Создать подарок:</b>\n"
        "Создайте подарочный код для друга (доступно с активной подпиской)",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "activate_gift")
async def activate_gift(callback: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="gift")]
    ])

    await callback.message.answer(
        "🎟️ <b>Активация подарочного кода</b>\n\n"
        "Введите подарочный код:\n\n"
        "<i>Пример: ABC123XYZ</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(GiftState.entering_code)


@router.message(GiftState.entering_code)
async def process_gift_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.clear()

    gift_code = await db.get_gift_code(code)

    if not gift_code:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="gift")]
        ])

        await message.answer(
            "❌ <b>Код не найден</b>\n\n"
            "Проверьте правильность введённого кода.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    if gift_code['used_by']:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="gift")]
        ])

        await message.answer(
            "⚠️ <b>Код уже использован</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    user = await db.get_user(message.from_user.id)

    if not user:
        await message.answer("❌ Пользователь не найден")
        return

    success = await db.use_gift_code(code, user['id'])

    if not success:
        await message.answer("❌ Ошибка активации кода")
        return

    from panel_client import XUIPanelClient
    panel = XUIPanelClient()

    client_email = f"gift_{uuid.uuid4().hex[:10]}"
    expiry_time = int(time.time() * 1000) + (gift_code['days'] * 24 * 60 * 60 * 1000)

    success = await panel.add_client_to_all_inbounds(
        email=client_email,
        expiry_time=expiry_time,
        limit_ip=gift_code['devices']
    )

    if not success:
        await message.answer("❌ Ошибка создания подписки")
        return

    await db.add_subscription(
        user_id=user['id'],
        client_email=client_email,
        tariff_days=gift_code['days'],
        device_limit=gift_code['devices'],
        expiry_time=expiry_time
    )

    sub_link = await panel.get_subscription_link(client_email)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)] if sub_link else [],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")]
    ])

    await message.answer(
        f"🎉 <b>Подарочный код активирован!</b>\n\n"
        f"📅 Срок: {gift_code['days']} дней\n"
        f"📱 Устройств: {gift_code['devices']}\n\n"
        f"Нажмите кнопку ниже для подключения 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "create_gift")
async def create_gift(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    subscription = await db.get_active_subscription(user['id'])

    if not subscription:
        await callback.answer(
            "⚠️ Для создания подарка нужна активная подписка!",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 день / 1 IP", callback_data="gift_plan_1_1"),
            InlineKeyboardButton(text="3 дня / 1 IP", callback_data="gift_plan_3_1")
        ],
        [
            InlineKeyboardButton(text="7 дней / 1 IP", callback_data="gift_plan_7_1"),
            InlineKeyboardButton(text="7 дней / 3 IP", callback_data="gift_plan_7_3")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="gift")]
    ])

    await callback.message.answer(
        "🎁 <b>Создание подарочного кода</b>\n\n"
        "Выберите параметры подарка:\n\n"
        "💡 Подарочный код можно отправить другу\n"
        "Он сможет активировать его и получить подписку",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("gift_plan_"))
async def process_gift_plan(callback: types.CallbackQuery):
    parts = callback.data.split("_")[2:]
    days = int(parts[0])
    devices = int(parts[1])

    code = uuid.uuid4().hex[:8].upper()

    user = await db.get_user(callback.from_user.id)
    await db.create_gift_code(code, days, devices, user['id'])

    bot = await callback.bot.get_me()
    activation_link = f"https://t.me/{bot.username}?start=gift_{code}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data=f"copy_gift_{code}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="gift")]
    ])

    await callback.message.answer(
        f"🎁 <b>Подарочный код создан!</b>\n\n"
        f"🎟️ <b>Код:</b> <code>{code}</code>\n"
        f"📅 <b>Срок:</b> {days} дней\n"
        f"📱 <b>Устройств:</b> {devices}\n\n"
        f"🔗 <b>Ссылка для активации:</b>\n"
        f"<code>{activation_link}</code>\n\n"
        f"Отправьте эту ссылку другу!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("copy_gift_"))
async def copy_gift(callback: types.CallbackQuery):
    code = callback.data.replace("copy_gift_", "")
    bot = await callback.bot.get_me()
    link = f"https://t.me/{bot.username}?start=gift_{code}"
    await callback.answer(f"📋 Ссылка: {link}", show_alert=True)


# ==================== РЕФЕРАЛЬНАЯ СИСТЕМА ====================

@router.callback_query(F.data == "referrals")
async def referrals(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    bot = await callback.bot.get_me()
    referral_link = f"https://t.me/{bot.username}?start={user['referral_code']}"

    stats = await db.get_referral_stats(user['id'])

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data="copy_referral_link")],
        [InlineKeyboardButton(text="📱 Показать QR-код", callback_data="show_qr")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

    await callback.message.answer(
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        "🤝 Приглашайте друзей и получайте бонусы! 💰\n\n"
        "🏆 <b>Бонусы за приглашения:</b>\n"
        "1 уровень: 🌟 30% бонуса\n"
        "2 уровень: 🌟 10% бонуса\n"
        "3 уровень: 🌟 5% бонуса\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Всего приглашено: {stats['total']} чел.\n\n"
        f"📈 <b>По уровням:</b>\n"
        f"🔹 Уровень 1: {stats['level_1']} (30%)\n"
        f"🔹 Уровень 2: {stats['level_2']} (10%)\n"
        f"🔹 Уровень 3: {stats['level_3']} (5%)\n\n"
        f"💰 <b>Заработано:</b> {stats['total_earned']:.2f} ₽\n"
        f"💵 <b>Баланс:</b> {user['balance']:.2f} ₽",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "show_qr")
async def show_qr(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    bot = await callback.bot.get_me()
    referral_link = f"https://t.me/{bot.username}?start={user['referral_code']}"

    qr_bytes = generate_qr_code(referral_link)

    await callback.message.answer_photo(
        photo=BufferedInputFile(qr_bytes, filename="referral_qr.png"),
        caption=f"🔗 Ваша реферальная ссылка:\n<code>{referral_link}</code>\n\n📱 Отсканируйте QR-код для быстрого перехода!",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "copy_referral_link")
async def copy_referral_link(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    bot = await callback.bot.get_me()
    referral_link = f"https://t.me/{bot.username}?start={user['referral_code']}"

    await callback.answer(f"📋 Ссылка скопирована!\n{referral_link}", show_alert=True)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def generate_qr_code(data: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    return img_byte_arr.getvalue()


# ==================== РЕФЕРАЛЬНАЯ И ПОДАРОЧНАЯ ОБРАБОТКА ====================

async def handle_referral(message: types.Message, referral_code: str):
    logger.info(f"🔗 Обработка реферального кода: {referral_code}")

    try:
        cursor = await db.conn.cursor()
        await cursor.execute("SELECT * FROM users WHERE referral_code = ?", (referral_code,))
        referrer_row = await cursor.fetchone()

        if referrer_row:
            referrer = dict(referrer_row)
            user = await db.get_user(message.from_user.id)

            if not user:
                new_user = await db.create_user(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    referral_code=uuid.uuid4().hex[:10],
                    referred_by=referrer['id']
                )

                if new_user:
                    bonus = 100
                    await db.add_referral(referrer['id'], new_user['id'], 1, bonus)
                    await db.update_balance(referrer['id'], bonus, f"Реферал: {message.from_user.id}")

                    await message.answer(
                        f"✅ Вы успешно присоединились по реферальной ссылке!\n"
                        f"🎁 Ваш реферер получил {bonus} ₽ бонуса!"
                    )
        await show_main_menu(message)
    except Exception as e:
        logger.error(f"Ошибка обработки реферала: {e}")
        import traceback
        traceback.print_exc()
        await show_main_menu(message)


async def handle_gift_code(message: types.Message, code: str, state: FSMContext):
    gift_code = await db.get_gift_code(code.upper())

    if not gift_code or gift_code['used_by']:
        await message.answer("❌ Неверный или уже использованный подарочный код")
        await show_main_menu(message)
        return

    user = await db.get_user(message.from_user.id)
    if not user:
        user = await db.create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            referral_code=uuid.uuid4().hex[:10]
        )

    success = await db.use_gift_code(code.upper(), user['id'])
    if not success:
        await message.answer("❌ Ошибка активации кода")
        return

    from panel_client import XUIPanelClient
    panel = XUIPanelClient()

    client_email = f"gift_{uuid.uuid4().hex[:10]}"
    expiry_time = int(time.time() * 1000) + (gift_code['days'] * 24 * 60 * 60 * 1000)

    success = await panel.add_client_to_all_inbounds(
        email=client_email,
        expiry_time=expiry_time,
        limit_ip=gift_code['devices']
    )

    if not success:
        await message.answer("❌ Ошибка создания подписки")
        return

    await db.add_subscription(
        user_id=user['id'],
        client_email=client_email,
        tariff_days=gift_code['days'],
        device_limit=gift_code['devices'],
        expiry_time=expiry_time
    )

    sub_link = await panel.get_subscription_link(client_email)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Подключить устройство", url=sub_link)] if sub_link else [],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")]
    ])

    await message.answer(
        f"🎉 <b>Подарочный код активирован!</b>\n\n"
        f"📅 Срок: {gift_code['days']} дней\n"
        f"📱 Устройств: {gift_code['devices']}\n\n"
        f"Нажмите кнопку ниже для подключения 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )