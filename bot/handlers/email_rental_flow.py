"""
Handler для аренды временных почт через quix.email.

Flow:
1. Пользователь нажимает "Аренда" в меню почт
2. Вводит домен сайта (mamba.ru, beboo.ru и т.д.)
3. Выбирает домен почты из списка доступных
4. Ждёт письмо (с таймером и возможностью отмены)
5. Получает код/ссылку из письма
6. Может запросить повторное письмо на ту же почту
"""
import asyncio
import logging
import time
from typing import Dict, Any, List
from dataclasses import dataclass

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states.states import EmailRentalStates
from bot.keyboards.callbacks import (
    EmailRentalMenuCallback,
    EmailRentalDomainCallback,
    EmailRentalDomainPageCallback,
    EmailRentalCancelCallback,
    EmailRentalRepeatCallback,
    EmailRentalBackCallback,
)
from bot.keyboards.email_rental_keyboards import (
    get_email_rental_enter_site_keyboard,
    get_email_rental_domains_keyboard,
    get_email_rental_waiting_keyboard,
    get_email_rental_received_keyboard,
    get_email_rental_timeout_keyboard,
    get_email_rental_error_keyboard,
)
from bot.keyboards.email_keyboards import get_email_menu_keyboard
from bot.services.quix_email_service import (
    quix_email_api,
    normalize_site,
    parse_email_content,
    POLL_INTERVAL,
    POLL_TIMEOUT,
)

logger = logging.getLogger(__name__)
router = Router()

# Храним активные задачи поллинга для возможности отмены
_polling_tasks: Dict[str, asyncio.Task] = {}

# Храним время заказа почт для проверки 4-минутного ограничения
_order_times: Dict[str, float] = {}

# Минимальное время до отмены (4 минуты)
MIN_CANCEL_TIME = 240  # секунд

# Интервал обработки очереди отмены
CANCEL_QUEUE_INTERVAL = 10  # секунд


@dataclass
class CancelRequest:
    """Запрос на отмену почты"""
    activation_id: str
    order_time: float
    chat_id: int
    message_id: int


# Очередь отмены
_cancel_queue: List[CancelRequest] = []
_cancel_queue_task: asyncio.Task = None
_bot_instance: Bot = None  # Храним инстанс бота для обновления сообщений из очереди


async def process_cancel_queue():
    """Фоновая задача обработки очереди отмены"""
    global _cancel_queue, _bot_instance

    while True:
        try:
            await asyncio.sleep(CANCEL_QUEUE_INTERVAL)

            if not _cancel_queue:
                continue

            current_time = time.time()
            still_pending = []

            for request in _cancel_queue:
                elapsed = current_time - request.order_time

                if elapsed >= MIN_CANCEL_TIME:
                    # Прошло 3 минуты - можно отменять
                    logger.info(f"Processing delayed cancel for {request.activation_id}")
                    cancelled = await quix_email_api.cancel_email(request.activation_id)
                    logger.info(f"Cancel result for {request.activation_id}: {cancelled}")

                    # Обновляем сообщение пользователю
                    if _bot_instance:
                        try:
                            await _bot_instance.edit_message_text(
                                chat_id=request.chat_id,
                                message_id=request.message_id,
                                text=(
                                    "📧 <b>Аренда почты</b>\n\n"
                                    "❌ Заказ отменён."
                                ),
                                reply_markup=get_email_rental_error_keyboard(),
                            )
                        except Exception as e:
                            logger.warning(f"Failed to update cancel message: {e}")

                    # Очищаем время заказа
                    _order_times.pop(request.activation_id, None)
                else:
                    # Ещё рано - оставляем в очереди
                    still_pending.append(request)

            _cancel_queue = still_pending

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Cancel queue error: {e}")


def start_cancel_queue_task():
    """Запустить фоновую задачу обработки очереди отмены"""
    global _cancel_queue_task
    if _cancel_queue_task is None or _cancel_queue_task.done():
        _cancel_queue_task = asyncio.create_task(process_cancel_queue())
        logger.info("Cancel queue task started")


def stop_cancel_queue_task():
    """Остановить фоновую задачу"""
    global _cancel_queue_task
    if _cancel_queue_task and not _cancel_queue_task.done():
        _cancel_queue_task.cancel()


# === Вспомогательные функции ===

def format_time(seconds: int) -> str:
    """Форматировать секунды в мм:сс"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


async def poll_email_status(
    bot: Bot,
    chat_id: int,
    message_id: int,
    activation_id: str,
    email: str,
    site: str,
    state: FSMContext,
) -> None:
    """
    Поллинг статуса письма с обновлением сообщения.

    Обновляет сообщение каждые POLL_INTERVAL секунд.
    При получении письма показывает результат.
    При таймауте показывает сообщение об ошибке.
    """
    start_time = time.time()
    last_update_time = 0

    try:
        while True:
            elapsed = int(time.time() - start_time)

            # Проверяем таймаут
            if elapsed >= POLL_TIMEOUT:
                logger.info(f"Email rental timeout: {activation_id}")
                
                # Очищаем время заказа
                _order_times.pop(activation_id, None)

                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        f"📧 <b>Аренда почты</b>\n\n"
                        f"📬 Почта: <code>{email}</code>\n"
                        f"🌐 Сайт: {site}\n\n"
                        f"⏱ <b>Время ожидания истекло</b>\n"
                        f"Письмо не пришло за {format_time(POLL_TIMEOUT)}.\n\n"
                        f"Попробуйте запросить снова или отмените."
                    ),
                    reply_markup=get_email_rental_timeout_keyboard(activation_id, email, site),
                )

                # Очищаем состояние
                await state.clear()
                return

            # Проверяем статус каждые POLL_INTERVAL секунд
            if elapsed - last_update_time >= POLL_INTERVAL or last_update_time == 0:
                last_update_time = elapsed

                # Запрос статуса
                status = await quix_email_api.check_status(activation_id)

                if status and status.status == "completed":
                    # Письмо получено!
                    logger.info(f"Email received: {activation_id}")
                    
                    # Очищаем время заказа
                    _order_times.pop(activation_id, None)

                    # Парсим содержимое
                    parsed = parse_email_content(status.data or "")

                    # Формируем сообщение
                    result_text = f"📧 <b>Аренда почты</b>\n\n"
                    result_text += f"📬 Почта: <code>{email}</code>\n"
                    result_text += f"🌐 Сайт: {site}\n\n"
                    result_text += f"✅ <b>Письмо получено!</b>\n\n"

                    if parsed.code:
                        result_text += f"🔑 <b>Код:</b> <code>{parsed.code}</code>\n"

                    if parsed.link:
                        result_text += f"🔗 <b>Ссылка:</b>\n{parsed.link}\n"

                    if not parsed.code and not parsed.link:
                        # Показываем начало текста
                        preview = (parsed.raw[:500] + "...") if len(parsed.raw) > 500 else parsed.raw
                        result_text += f"📝 <b>Содержимое:</b>\n<pre>{preview}</pre>\n"

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=result_text,
                        reply_markup=get_email_rental_received_keyboard(activation_id, email, site),
                        disable_web_page_preview=True,
                    )

                    # Очищаем состояние
                    await state.clear()
                    return

                elif status and status.status == "cancelled":
                    # Отменено
                    logger.info(f"Email cancelled externally: {activation_id}")
                    
                    # Очищаем время заказа
                    _order_times.pop(activation_id, None)

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"📧 <b>Аренда почты</b>\n\n"
                            f"❌ Заказ отменён."
                        ),
                        reply_markup=get_email_rental_error_keyboard(),
                    )

                    await state.clear()
                    return

                # Обновляем сообщение с таймером
                remaining = POLL_TIMEOUT - elapsed

                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        f"📧 <b>Аренда почты</b>\n\n"
                        f"📬 Почта: <code>{email}</code>\n"
                        f"🌐 Сайт: {site}\n\n"
                        f"⏳ <b>Ожидание письма...</b>\n"
                        f"⏱ Прошло: {format_time(elapsed)} / {format_time(POLL_TIMEOUT)}\n"
                        f"Осталось: {format_time(remaining)}"
                    ),
                    reply_markup=get_email_rental_waiting_keyboard(activation_id),
                )

            # Короткий сон перед следующей итерацией
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        # Задача отменена (пользователь нажал отмену)
        logger.info(f"Polling cancelled for: {activation_id}")
        raise

    except Exception as e:
        logger.error(f"Polling error for {activation_id}: {e}")

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                f"📧 <b>Аренда почты</b>\n\n"
                f"❌ Ошибка при проверке статуса:\n{e}"
            ),
            reply_markup=get_email_rental_error_keyboard(),
        )

        await state.clear()


# === Handlers ===

@router.callback_query(EmailRentalMenuCallback.filter())
async def open_email_rental_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Открытие меню аренды почт - запрос домена сайта"""
    await state.set_state(EmailRentalStates.entering_site)

    await callback.message.edit_text(
        "📧 <b>Аренда временной почты</b>\n\n"
        "Введите домен сайта, от которого ожидаете письмо:\n\n"
        "Примеры: <code>mamba.ru</code>, <code>beboo.ru</code>, <code>ok.ru</code>",
        reply_markup=get_email_rental_enter_site_keyboard(),
    )
    await callback.answer()


@router.message(EmailRentalStates.entering_site)
async def process_site_input(message: Message, state: FSMContext) -> None:
    """Обработка ввода домена сайта"""
    raw_site = message.text.strip() if message.text else ""

    if not raw_site:
        await message.answer(
            "❌ Введите домен сайта.\n"
            "Примеры: <code>mamba.ru</code>, <code>beboo.ru</code>",
            reply_markup=get_email_rental_enter_site_keyboard(),
        )
        return

    # Нормализуем сайт
    site = normalize_site(raw_site)

    if not site or "." not in site:
        await message.answer(
            f"❌ Некорректный домен: <code>{raw_site}</code>\n\n"
            "Введите корректный домен сайта.\n"
            "Примеры: <code>mamba.ru</code>, <code>beboo.ru</code>",
            reply_markup=get_email_rental_enter_site_keyboard(),
        )
        return

    # Получаем список доступных доменов почт
    status_msg = await message.answer(
        f"🔍 Загружаю доступные домены для <code>{site}</code>..."
    )

    domains = await quix_email_api.get_domains(site=site)

    if not domains:
        await status_msg.edit_text(
            f"❌ Нет доступных почт для сайта <code>{site}</code>\n\n"
            "Попробуйте другой сайт.",
            reply_markup=get_email_rental_enter_site_keyboard(),
        )
        return

    # Сохраняем данные в состояние
    await state.update_data(site=site, domains=domains)
    await state.set_state(EmailRentalStates.selecting_domain)

    # Показываем список доменов
    await status_msg.edit_text(
        f"📧 <b>Аренда почты для {site}</b>\n\n"
        f"Выберите домен почты:\n"
        f"<i>В скобках указано количество доступных почт</i>",
        reply_markup=get_email_rental_domains_keyboard(domains, page=0),
    )


@router.callback_query(EmailRentalDomainPageCallback.filter(), EmailRentalStates.selecting_domain)
async def handle_domain_pagination(
    callback: CallbackQuery,
    callback_data: EmailRentalDomainPageCallback,
    state: FSMContext,
) -> None:
    """Обработка пагинации доменов"""
    data = await state.get_data()
    domains = data.get("domains", [])
    site = data.get("site", "")

    await callback.message.edit_text(
        f"📧 <b>Аренда почты для {site}</b>\n\n"
        f"Выберите домен почты:\n"
        f"<i>В скобках указано количество доступных почт</i>",
        reply_markup=get_email_rental_domains_keyboard(domains, page=callback_data.page),
    )
    await callback.answer()


@router.callback_query(EmailRentalDomainCallback.filter(), EmailRentalStates.selecting_domain)
async def select_domain(
    callback: CallbackQuery,
    callback_data: EmailRentalDomainCallback,
    state: FSMContext,
    bot: Bot,
) -> None:
    """Выбор домена почты и заказ"""
    data = await state.get_data()
    site = data.get("site", "")
    domain = callback_data.domain

    await callback.answer("Заказываю почту...")

    # Заказываем почту
    result = await quix_email_api.order_email(site=site, domain=domain)

    if not result:
        await callback.message.edit_text(
            f"❌ Не удалось заказать почту @{domain} для {site}\n\n"
            "Попробуйте выбрать другой домен.",
            reply_markup=get_email_rental_domains_keyboard(data.get("domains", []), page=0),
        )
        return

    # Сохраняем данные активации и время заказа
    order_time = time.time()
    _order_times[result.id] = order_time
    
    await state.update_data(
        activation_id=result.id,
        email=result.email,
        order_time=order_time,
    )
    await state.set_state(EmailRentalStates.waiting_email)
    
    # Запускаем задачу очереди отмены если не запущена
    start_cancel_queue_task()

    # Показываем сообщение ожидания
    msg = await callback.message.edit_text(
        f"📧 <b>Аренда почты</b>\n\n"
        f"📬 Почта: <code>{result.email}</code>\n"
        f"🌐 Сайт: {site}\n\n"
        f"⏳ <b>Ожидание письма...</b>\n"
        f"⏱ Прошло: 0:00 / {format_time(POLL_TIMEOUT)}",
        reply_markup=get_email_rental_waiting_keyboard(result.id),
    )

    # Запускаем поллинг в фоне
    task = asyncio.create_task(
        poll_email_status(
            bot=bot,
            chat_id=callback.message.chat.id,
            message_id=msg.message_id,
            activation_id=result.id,
            email=result.email,
            site=site,
            state=state,
        )
    )
    _polling_tasks[result.id] = task


@router.callback_query(EmailRentalCancelCallback.filter())
async def cancel_email(
    callback: CallbackQuery,
    callback_data: EmailRentalCancelCallback,
    state: FSMContext,
    bot: Bot,
) -> None:
    """Отмена заказа почты с учётом 3-минутного ограничения"""
    global _bot_instance
    _bot_instance = bot  # Сохраняем для очереди

    activation_id = callback_data.activation_id

    # Отменяем задачу поллинга
    if activation_id in _polling_tasks:
        _polling_tasks[activation_id].cancel()
        del _polling_tasks[activation_id]

    # Проверяем время с момента заказа
    order_time = _order_times.get(activation_id)
    current_time = time.time()

    if order_time:
        elapsed = current_time - order_time

        if elapsed < MIN_CANCEL_TIME:
            # Ещё не прошло 3 минуты - ставим в очередь
            remaining = int(MIN_CANCEL_TIME - elapsed)

            _cancel_queue.append(CancelRequest(
                activation_id=activation_id,
                order_time=order_time,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            ))

            # Запускаем задачу очереди если не запущена
            start_cancel_queue_task()

            await callback.message.edit_text(
                "📧 <b>Аренда почты</b>\n\n"
                f"⏳ Заказ будет отменён автоматически через ~{remaining} сек.\n"
                f"<i>(Ограничение API: отмена возможна только через 4 минуты после заказа)</i>",
            )

            await state.clear()
            await callback.answer()
            return

    # Прошло 3 минуты или время неизвестно - отменяем сразу
    cancelled = await quix_email_api.cancel_email(activation_id)

    # Очищаем время заказа
    _order_times.pop(activation_id, None)

    if cancelled:
        await callback.message.edit_text(
            "📧 <b>Аренда почты</b>\n\n"
            "❌ Заказ отменён.",
            reply_markup=get_email_rental_error_keyboard(),
        )
    else:
        await callback.message.edit_text(
            "📧 <b>Аренда почты</b>\n\n"
            "⚠️ Не удалось отменить заказ (возможно, уже отменён).",
            reply_markup=get_email_rental_error_keyboard(),
        )

    await state.clear()
    await callback.answer()


@router.callback_query(EmailRentalRepeatCallback.filter())
async def repeat_email(
    callback: CallbackQuery,
    callback_data: EmailRentalRepeatCallback,
    state: FSMContext,
    bot: Bot,
) -> None:
    """Повторный запрос письма на ту же почту"""
    activation_id = callback_data.activation_id
    email = callback_data.email
    site = callback_data.site

    await callback.answer("Запрашиваю повторно...")

    # Повторный запрос
    result = await quix_email_api.repeat_email(activation_id=activation_id)

    if not result:
        # Пробуем по email + site
        result = await quix_email_api.repeat_email(email=email, site=site)

    if not result:
        await callback.message.edit_text(
            f"❌ Не удалось запросить повторное письмо.\n\n"
            f"Попробуйте заново через меню аренды.",
            reply_markup=get_email_rental_error_keyboard(),
        )
        return

    # Обновляем данные активации
    await state.update_data(
        activation_id=result.id,
        email=result.email,
        site=site,
    )
    await state.set_state(EmailRentalStates.waiting_email)

    # Показываем сообщение ожидания
    await callback.message.edit_text(
        f"📧 <b>Аренда почты</b>\n\n"
        f"📬 Почта: <code>{result.email}</code>\n"
        f"🌐 Сайт: {site}\n\n"
        f"⏳ <b>Ожидание письма...</b>\n"
        f"⏱ Прошло: 0:00 / {format_time(POLL_TIMEOUT)}",
        reply_markup=get_email_rental_waiting_keyboard(result.id),
    )

    # Запускаем поллинг
    task = asyncio.create_task(
        poll_email_status(
            bot=bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            activation_id=result.id,
            email=result.email,
            site=site,
            state=state,
        )
    )
    _polling_tasks[result.id] = task


@router.callback_query(EmailRentalBackCallback.filter())
async def handle_back(
    callback: CallbackQuery,
    callback_data: EmailRentalBackCallback,
    state: FSMContext,
) -> None:
    """Обработка кнопки назад"""
    destination = callback_data.to

    if destination == "email_menu":
        # Возврат в меню почт
        await state.clear()

        from bot.states.states import EmailFlowStates
        await state.set_state(EmailFlowStates.selecting_email_resource)

        await callback.message.edit_text(
            "📧 <b>Почты</b>\n\n"
            "Выберите почтовый сервис или аренду временной почты:",
            reply_markup=get_email_menu_keyboard(),
        )

    elif destination == "enter_site":
        # Возврат к вводу сайта
        await state.set_state(EmailRentalStates.entering_site)

        await callback.message.edit_text(
            "📧 <b>Аренда временной почты</b>\n\n"
            "Введите домен сайта, от которого ожидаете письмо:\n\n"
            "Примеры: <code>mamba.ru</code>, <code>beboo.ru</code>, <code>ok.ru</code>",
            reply_markup=get_email_rental_enter_site_keyboard(),
        )

    await callback.answer()
