from aiogram.utils.markdown import hcode, hlink

from bot.models.enums import Resource, EmailResource


def format_account_message(resource: Resource, account, region: str) -> str:
    """Форматирование сообщения с аккаунтом для выдачи"""
    # Заголовок с эмодзи
    lines = [f"<b>{resource.emoji} {resource.display_name}</b> | Регион: {region}"]

    if resource == Resource.VK:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        lines.append("")
        tab_line = f"{account.login}\t{account.password}"
        lines.append(f"📋 <pre>{tab_line}</pre>")

    elif resource == Resource.MAMBA:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        lines.append(f"Пароль почты: {hcode(account.email_password)}")
        if account.confirmation_link:
            lines.append(f"Подтверждение: {hlink('ссылка', account.confirmation_link)}")
        lines.append("")
        tab_line = f"{account.login}\t{account.password}\t{account.email_password}\t{account.confirmation_link or ''}"
        lines.append(f"📋 <pre>{tab_line}</pre>")

    elif resource == Resource.OK:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        lines.append("")
        tab_line = f"{account.login}\t{account.password}"
        lines.append(f"📋 <pre>{tab_line}</pre>")

    elif resource == Resource.GMAIL:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        if account.backup_email:
            lines.append(f"Резервная: {hcode(account.backup_email)}")
        lines.append("")
        tab_line = f"{account.login}\t{account.password}\t{account.backup_email or ''}"
        lines.append(f"📋 <pre>{tab_line}</pre>")

    return "\n".join(lines)


def format_account_compact(resource: Resource, account, region: str, status_display: str) -> str:
    """Компактное форматирование аккаунта после фидбека (без строки копирования)"""
    lines = [f"<b>{resource.emoji} {resource.display_name}</b> | Регион: {region}"]

    if resource == Resource.VK:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")

    elif resource == Resource.MAMBA:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        lines.append(f"Пароль почты: {hcode(account.email_password)}")
        if account.confirmation_link:
            lines.append(f"Подтверждение: {hlink('ссылка', account.confirmation_link)}")

    elif resource == Resource.OK:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")

    elif resource == Resource.GMAIL:
        lines.append(f"Логин: {hcode(account.login)}")
        lines.append(f"Пароль: {hcode(account.password)}")
        if account.backup_email:
            lines.append(f"Резервная: {hcode(account.backup_email)}")

    lines.append(f"\n<b>Статус: {status_display}</b>")
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


def format_email_message(
    email_resource: EmailResource,
    login: str,
    password: str,
    region: str,
    email_type_display: str = None,
    extra_info: str = None,
) -> str:
    """Форматирование сообщения с почтой для выдачи"""
    header = f"<b>{email_resource.emoji} {email_resource.display_name}</b>"
    if email_type_display:
        header += f" ({email_type_display})"
    header += f" | Регион: {region}"

    lines = [header]
    lines.append(f"Логин: {hcode(login)}")
    lines.append(f"Пароль: {hcode(password)}")
    if extra_info:
        lines.append(f"Доп инфа: {hcode(extra_info)}")
    lines.append("")
    tab_line = f"{login}\t{password}"
    lines.append(f"📋 <pre>{tab_line}</pre>")

    return "\n".join(lines)


def format_email_compact(
    email_resource: EmailResource,
    login: str,
    password: str,
    region: str,
    status_display: str,
    email_type_display: str = None,
) -> str:
    """Компактное форматирование почты после фидбека (без строки копирования)"""
    header = f"<b>{email_resource.emoji} {email_resource.display_name}</b>"
    if email_type_display:
        header += f" ({email_type_display})"
    header += f" | Регион: {region}"

    lines = [header]
    lines.append(f"Логин: {hcode(login)}")
    lines.append(f"Пароль: {hcode(password)}")
    lines.append(f"\n<b>Статус: {status_display}</b>")

    return "\n".join(lines)


def format_number_message(number: str, date_added: str, resources_text: str) -> str:
    """Форматирование сообщения с номером для выдачи"""
    lines = [
        f"<b>📱 Номер</b> | {resources_text}",
        f"<code>{number}</code>",
        f"<i>Добавлен: {date_added}</i>",
    ]
    return "\n".join(lines)


def format_number_compact(number: str, resources_text: str, status_display: str) -> str:
    """Компактное форматирование номера после фидбека"""
    lines = [
        f"<b>📱 Номер</b> | {resources_text}",
        f"<code>{number}</code>",
        f"\n<b>Статус: {status_display}</b>",
    ]
    return "\n".join(lines)


def format_proxy_message(
    proxy_type: str,
    address: str,
    country_flag: str,
    country_name: str,
    expires_at: str,
    used_for_text: str,
) -> str:
    """Форматирование сообщения с прокси для выдачи"""
    lines = [
        f"<b>🌐 Прокси получен!</b>",
        f"Тип: {proxy_type}",
        f"Адрес: {hcode(address)}",
        f"Страна: {country_flag} {country_name}",
        f"Истекает: {expires_at}",
        f"Ранее использован для: {used_for_text}",
    ]
    return "\n".join(lines)


import re


def make_compact_after_feedback(html_text: str, status_display: str) -> str:
    """
    Преобразует сообщение в компактный формат после фидбека:
    - Убирает строку копирования (📋 и <pre>...</pre>)
    - Убирает строку с подтверждением (для Мамбы)
    - Убирает лишние пустые строки
    - Добавляет статус
    """
    # Убираем строку с 📋 Копировать
    text = re.sub(r'\n?📋[^\n]*\n?', '', html_text)
    # Убираем <pre>...</pre> блоки
    text = re.sub(r'\n?<pre>[^<]*</pre>\n?', '', text)
    # Убираем строку с подтверждением (Мамба)
    text = re.sub(r'\n?Подтверждение:[^\n]*\n?', '', text)
    # Убираем множественные пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Убираем пустую строку в конце
    text = text.rstrip('\n')
    # Добавляем статус
    text += f"\n\n<b>Статус: {status_display}</b>"
    return text
