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

    # Регионы (настраиваемый список)
    REGIONS: str = "546,621,545,674,538,719"

    @property
    def regions_list(self) -> List[str]:
        """Получить список регионов"""
        return [r.strip() for r in self.REGIONS.split(",") if r.strip()]

    # Webhook (для Render.com, оставить пустым для polling)
    WEBHOOK_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"

    # Названия листов для аккаунтов
    # Формат таблицы База: дата | логин | пароль | ...
    # Формат таблицы Выдача: дата | логин | пароль | ... | регион | employee | status
    SHEET_NAMES: dict = {
        "vk_male": "ВК Муж",
        "vk_female": "ВК Жен",
        "mamba_male": "Мамб Муж",
        "mamba_female": "Мамб Жен",
        "ok_male": "ОК Муж",
        "ok_female": "ОК Жен",
        "gmail_domain": "Гугл Гмейл",
        "gmail_any": "Гугл Обыч",
        "whitelist": "whitelist",
        # Номера телефонов (общие для Beboo/Loloo/Табор)
        # Формат База: дата | номер
        # Формат Выдача: дата | номер | регион | employee | ресурсы
        "numbers": "Номера",
        "numbers_issued": "Номера Выдано",
    }

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
