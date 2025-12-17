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
