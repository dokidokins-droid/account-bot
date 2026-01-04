from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния регистрации нового пользователя"""
    waiting_for_stage = State()  # Ожидание ввода stage (никнейма)
    waiting_for_approval = State()  # Ожидание одобрения админом


class AccountFlowStates(StatesGroup):
    """Состояния процесса выдачи аккаунтов"""
    selecting_resource = State()  # Выбор ресурса (VK/Mamba/OK/Gmail)
    selecting_region = State()  # Выбор региона
    searching_region = State()  # Поиск региона (ввод текста)
    selecting_quantity = State()  # Выбор количества (1-5)
    selecting_gender = State()  # Выбор пола / типа


class StatisticStates(StatesGroup):
    """Состояния просмотра статистики"""
    # Основные аккаунты (VK, Mamba, OK)
    selecting_resource = State()  # Выбор ресурса
    selecting_gender = State()  # Выбор пола/типа
    selecting_region = State()  # Выбор региона (+ все регионы)
    searching_region = State()  # Ручной ввод региона
    selecting_period = State()  # Выбор периода (день/неделя/месяц)

    # Почты (Gmail, Rambler)
    email_selecting_resource = State()  # Выбор почтового ресурса
    email_selecting_type = State()  # Выбор типа Gmail (Любые/gmail.com)
    email_selecting_region = State()  # Выбор региона для почт
    email_searching_region = State()  # Ручной ввод региона для почт
    email_selecting_period = State()  # Выбор периода для почт

    # Номера
    number_selecting_region = State()  # Выбор региона для номеров
    number_searching_region = State()  # Ручной ввод региона для номеров
    number_selecting_period = State()  # Выбор периода для номеров


class BufferClearStates(StatesGroup):
    """Состояния для очистки буфера (админ)"""
    selecting_category = State()  # Аккаунты / Почты / Всё
    selecting_resource = State()  # Конкретный ресурс
    selecting_type = State()  # available / pending / buffer / all
    confirming = State()  # Подтверждение


class BufferReleaseStates(StatesGroup):
    """Состояния для освобождения буфера (возврат в базу, админ)"""
    selecting_category = State()  # Аккаунты / Почты
    selecting_resource = State()  # Конкретный ресурс
    confirming = State()  # Подтверждение


class ProxyStates(StatesGroup):
    """Состояния для работы с прокси"""
    # Главное меню прокси
    main_menu = State()  # Выбор: добавить или получить

    # Добавление прокси
    add_selecting_type = State()  # Выбор типа прокси (HTTP/SOCKS5)
    add_waiting_proxy = State()  # Ожидание ввода прокси
    add_selecting_resources = State()  # Выбор ресурсов (множественный выбор)
    add_selecting_duration = State()  # Выбор срока действия

    # Получение прокси
    get_selecting_resources = State()  # Множественный выбор ресурсов
    get_selecting_country = State()  # Выбор страны (сетка с флагами)
    get_selecting_proxy = State()  # Выбор конкретного прокси (с пагинацией)
    get_multiselecting = State()  # Множественный выбор прокси (с чекбоксами)


class NumberStates(StatesGroup):
    """Состояния для выдачи номеров телефонов"""
    selecting_resources = State()  # Множественный выбор ресурсов (Beboo/Loloo/Табор)
    selecting_region = State()  # Выбор региона
    searching_region = State()  # Ручной ввод региона
    selecting_quantity = State()  # Выбор количества (1-5)


class EmailFlowStates(StatesGroup):
    """Состояния процесса выдачи почт (новый flow с умным распределением)"""
    selecting_email_resource = State()  # Выбор почтового домена (Gmail/Рамблер)
    selecting_email_type = State()  # Выбор типа Gmail (Любые / только gmail.com)
    selecting_region = State()  # Выбор региона
    searching_region = State()  # Поиск региона (ввод текста)
    selecting_mode = State()  # Выбор режима (Новая/Эконом)
    selecting_target_resources = State()  # Мультиселект целевых ресурсов
    selecting_quantity = State()  # Выбор количества (1-5)


class EmailRentalStates(StatesGroup):
    """Состояния для аренды временных почт через quix.email"""
    entering_site = State()      # Ввод домена сайта (mamba.ru, beboo.ru и т.д.)
    selecting_domain = State()   # Выбор домена почты (gmail.com, mail.ru и т.д.)
    waiting_email = State()      # Ожидание получения письма
