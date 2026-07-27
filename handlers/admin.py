# handlers/admin.py
"""
Мини-админка прямо в Telegram: /admin показывает статистику и последние
действия пользователей (кто зашёл, кто активировал триал/купил/продлил).
Полноценная веб-панель — отдельная, более крупная задача; здесь — самое
необходимое для повседневного контроля без поднятия отдельного сервиса.
"""
import io
import logging
from datetime import datetime

from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

import config
from database import db

logger = logging.getLogger(__name__)
router = Router()

_EVENT_EMOJI = {
    "start": "🚀",
    "trial_activated": "🎁",
    "purchase": "💳",
    "renewal": "🔄",
    "referral": "👥",
}

_EVENT_LABEL = {
    "start": "Зашёл в бота",
    "trial_activated": "Активировал триал",
    "purchase": "Купил подписку",
    "renewal": "Продлил подписку",
    "referral": "Реферал",
}


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def _format_event(ev: dict) -> str:
    emoji = _EVENT_EMOJI.get(ev["event_type"], "▫️")
    label = _EVENT_LABEL.get(ev["event_type"], ev["event_type"])
    who = f"@{ev['username']}" if ev.get("username") else str(ev["telegram_id"])
    when = (ev.get("created_at") or "")[:16]
    details = f" — {ev['details']}" if ev.get("details") else ""
    return f"{emoji} <b>{label}</b> — {who}{details}\n<i>{when}</i>"


def _admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh"),
            InlineKeyboardButton(text="📜 Больше событий", callback_data="admin_more_events"),
        ],
        [InlineKeyboardButton(text="📥 Выгрузить лог (.txt)", callback_data="admin_export_logs")],
    ])


async def _render_admin_text(limit: int = 15) -> str:
    stats = await db.get_admin_stats()
    events = await db.get_recent_events(limit=limit)

    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👤 Всего пользователей: <b>{stats['total_users']}</b> (сегодня +{stats['new_users_today']})\n"
        f"✅ Активных подписок: <b>{stats['active_subscriptions']}</b>\n"
        f"🎁 Всего пробных подписок выдано: <b>{stats['total_trials']}</b>\n\n"
        f"📅 <b>Сегодня:</b>\n"
        f"   🚀 Заходов: {stats['starts_today']}\n"
        f"   🎁 Активаций триала: {stats['trials_today']}\n"
        f"   💳 Покупок/продлений: {stats['purchases_today']}\n\n"
        f"🕒 <b>Последние события:</b>\n\n"
    )

    if events:
        text += "\n\n".join(_format_event(ev) for ev in events)
    else:
        text += "<i>Пока пусто</i>"

    return text


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not _is_admin(message.from_user.id):
        return  # для не-админов команда как будто не существует

    text = await _render_admin_text()
    await message.answer(text, reply_markup=_admin_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_refresh")
async def admin_refresh(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    text = await _render_admin_text()
    try:
        await callback.message.edit_text(text, reply_markup=_admin_keyboard(), parse_mode="HTML")
    except Exception:
        pass  # текст не изменился — Telegram вернёт ошибку, это не критично
    await callback.answer("Обновлено")


@router.callback_query(F.data == "admin_more_events")
async def admin_more_events(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    text = await _render_admin_text(limit=40)
    await callback.message.answer(text, reply_markup=_admin_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_export_logs")
async def admin_export_logs(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer("⏳ Готовлю файл...")

    events = await db.get_recent_events(limit=2000)

    lines = []
    for ev in reversed(events):  # от старых к новым, как обычный лог-файл
        who = f"@{ev['username']}" if ev.get("username") else str(ev["telegram_id"])
        lines.append(
            f"[{ev.get('created_at', '')}] {ev['event_type']:<16} {who:<20} {ev.get('details') or ''}"
        )

    content = "\n".join(lines) if lines else "Логов пока нет"
    file_bytes = content.encode("utf-8")
    filename = f"events_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"

    document = BufferedInputFile(file_bytes, filename=filename)
    await callback.message.answer_document(document, caption=f"📥 Последние {len(events)} событий")