from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    ADMIN_ID: int

    # Google Sheets
    GOOGLE_CREDENTIALS_JSON: str
    SPREADSHEET_ACCOUNTS: str
    SPREADSHEET_ISSUED: str

    # Quix Email API (аренда временных почт)
    QUIX_EMAIL_API_KEY: str = ""

    # Регионы (настраиваемый список)
    REGIONS: str = "546,621,545,674,538,719"

    @property
    def regions_list(self) -> List[str]:
        """Получить список регионов"""
        return [r.strip() for r in self.REGIONS.split(",") if r.strip()]

    # Названия листов для аккаунтов
    # Формат таблицы База: дата | логин | пароль | ...
    # Формат таблицы Выдача: дата | логин | пароль | ... | регион | employee | status
    SHEET_NAMES: dict = {
        "vk_none": "ВКонтакте",
        "mamba_male": "Мамб Муж",
        "mamba_female": "Мамб Жен",
        "ok_none": "Одноклассники",
        "gmail_gmail_domain": "Гугл Гмейл",
        "gmail_any": "Гугл Любые",
        # Номера телефонов (общие для Beboo/Loloo/Табор)
        # Формат База: дата | номер
        # Формат Выдача: дата | номер | регион | employee | ресурсы
        "numbers": "Номера",
        "numbers_issued": "Номера",  # Тот же лист что и база
        # Почты
        # Формат: дата | логин | пароль
        "rambler_none": "Рамблер",
    }

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
