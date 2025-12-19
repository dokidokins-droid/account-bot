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
    selecting_resource = State()  # Выбор ресурса
    selecting_gender = State()  # Выбор пола/типа
    selecting_region = State()  # Выбор региона (+ все регионы)
    searching_region = State()  # Ручной ввод региона
    selecting_period = State()  # Выбор периода (день/неделя/месяц)


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
    get_selecting_resource = State()  # Выбор ресурса
    get_selecting_country = State()  # Выбор страны (сетка с флагами)
    get_selecting_proxy = State()  # Выбор конкретного прокси (с пагинацией)


class NumberStates(StatesGroup):
    """Состояния для выдачи номеров телефонов"""
    selecting_resources = State()  # Множественный выбор ресурсов (Beboo/Loloo/Табор)
    selecting_region = State()  # Выбор региона
    searching_region = State()  # Ручной ввод региона
    selecting_quantity = State()  # Выбор количества (1-5)
