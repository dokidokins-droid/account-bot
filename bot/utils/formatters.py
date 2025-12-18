from aiogram.utils.markdown import hcode, hlink

from bot.models.enums import Resource
from bot.models.account import VKAccount, MambaAccount, OKAccount, GmailAccount


def format_account_message(resource: Resource, account, region: str) -> str:
    """Форматирование сообщения с аккаунтом для выдачи"""
    lines = [f"<b>{resource.display_name}</b> | Регион: {region}", ""]

    if resource == Resource.VK:
        # ВК: логин, пароль
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        lines.append("")
        # Строка для вставки в таблицу (с табуляцией)
        tab_line = f"{account.login}\t{account.password}"
        lines.append(f"📋 Копировать (полная строка):")
        lines.append(f"<pre>{tab_line}</pre>")

    elif resource == Resource.MAMBA:
        # Мамба: логин, пароль, пароль почты, ссылка
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        lines.append(f"Пароль почты: {hcode(account.email_password)}")
        if account.confirmation_link:
            lines.append(f"Подтверждение: {hlink('ссылка', account.confirmation_link)}")
        lines.append("")
        # Строка для вставки в таблицу
        tab_line = f"{account.login}\t{account.password}\t{account.email_password}\t{account.confirmation_link or ''}"
        lines.append(f"📋 Копировать (полная строка):")
        lines.append(f"<pre>{tab_line}</pre>")

    elif resource == Resource.OK:
        # ОК: логин, пароль
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        lines.append("")
        # Строка для вставки в таблицу
        tab_line = f"{account.login}\t{account.password}"
        lines.append(f"📋 Копировать (полная строка):")
        lines.append(f"<pre>{tab_line}</pre>")

    elif resource == Resource.GMAIL:
        # Gmail: логин, пароль, резервная почта
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        if account.backup_email:
            lines.append(f"Резервная: {hcode(account.backup_email)}")
        lines.append("")
        # Строка для вставки в таблицу
        tab_line = f"{account.login}\t{account.password}\t{account.backup_email or ''}"
        lines.append(f"📋 Копировать (полная строка):")
        lines.append(f"<pre>{tab_line}</pre>")

    return "\n".join(lines)


def format_selection_summary(
    resource: Resource,
    region: str,
    quantity: int,
    gender_display: str,
) -> str:
    """Форматирование сводки выбора"""
    return (
        f"<b>Выбрано:</b>\n"
        f"Ресурс: {resource.display_name}\n"
        f"Регион: {region}\n"
        f"Количество: {quantity}\n"
        f"Тип: {gender_display}"
    )


def format_user_request(
    telegram_id: int,
    username: str | None,
    stage: str,
) -> str:
    """Форматирование запроса на одобрение для админа"""
    return (
        f"<b>🆕 Новый запрос на доступ</b>\n\n"
        f"Telegram ID: {hcode(str(telegram_id))}\n"
        f"Username: @{username or 'нет'}\n"
        f"Stage: {hcode(stage)}"
    )
