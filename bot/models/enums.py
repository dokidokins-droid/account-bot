from enum import Enum


class Resource(str, Enum):
    VK = "vk"
    MAMBA = "mamba"
    OK = "ok"
    GMAIL = "gmail"

    @property
    def display_name(self) -> str:
        names = {
            "vk": "ВКонтакте",
            "mamba": "Мамба",
            "ok": "Одноклассники",
            "gmail": "Gmail",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "vk": "🔵",
            "mamba": "🟠",
            "ok": "🟡",
            "gmail": "🟢",
        }
        return emojis[self.value]

    @property
    def button_text(self) -> str:
        return f"{self.emoji} {self.display_name}"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    ANY = "any"  # Для Gmail - "Гугл Обыч"
    GMAIL_DOMAIN = "gmail_domain"  # Для Gmail - "Гугл Гмейл" (только gmail.com)

    @property
    def display_name(self) -> str:
        names = {
            "male": "Мужской",
            "female": "Женский",
            "any": "Обычные",
            "gmail_domain": "gmail.com",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "male": "👨",
            "female": "👩",
            "any": "📧",
            "gmail_domain": "📧",
        }
        return emojis[self.value]

    @property
    def button_text(self) -> str:
        return f"{self.emoji} {self.display_name}"


class AccountStatus(str, Enum):
    BLOCK = "block"
    GOOD = "good"
    DEFECT = "defect"

    @property
    def display_name(self) -> str:
        names = {
            "block": "Блок",
            "good": "Хороший",
            "defect": "Дефектный",
        }
        return names[self.value]


class ProxyResource(str, Enum):
    """Ресурсы для которых используются прокси"""
    VK = "vk"
    MAMBA = "mamba"
    OK = "ok"
    LOVEPLANET = "loveplanet"
    TEAMO = "teamo"
    BADOO = "badoo"
    TINDER = "tinder"

    @property
    def display_name(self) -> str:
        names = {
            "vk": "ВКонтакте",
            "mamba": "Мамба",
            "ok": "Одноклассники",
            "loveplanet": "LovePlanet",
            "teamo": "Teamo",
            "badoo": "Badoo",
            "tinder": "Tinder",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "vk": "🔵",
            "mamba": "🟠",
            "ok": "🟡",
            "loveplanet": "💜",
            "teamo": "❤️",
            "badoo": "🟣",
            "tinder": "🔥",
        }
        return emojis[self.value]

    @property
    def button_text(self) -> str:
        return f"{self.emoji} {self.display_name}"


class ProxyDuration(str, Enum):
    """Сроки действия прокси"""
    DAYS_5 = "5"
    DAYS_10 = "10"
    DAYS_15 = "15"
    DAYS_30 = "30"

    @property
    def days(self) -> int:
        return int(self.value)

    @property
    def button_text(self) -> str:
        return f"{self.value}д"


# Названия стран
COUNTRY_NAMES = {
    "RU": "Россия",
    "UA": "Украина",
    "KZ": "Казахстан",
    "BY": "Беларусь",
    "US": "США",
    "DE": "Германия",
    "NL": "Нидерланды",
    "GB": "Великобритания",
    "FR": "Франция",
    "PL": "Польша",
    "CZ": "Чехия",
    "IT": "Италия",
    "ES": "Испания",
    "CA": "Канада",
    "AU": "Австралия",
    "JP": "Япония",
    "CN": "Китай",
    "IN": "Индия",
    "BR": "Бразилия",
    "TR": "Турция",
    "LU": "Люксембург",
    "CH": "Швейцария",
    "AT": "Австрия",
    "BE": "Бельгия",
    "SE": "Швеция",
    "NO": "Норвегия",
    "FI": "Финляндия",
    "DK": "Дания",
    "PT": "Португалия",
    "GR": "Греция",
    "RO": "Румыния",
    "HU": "Венгрия",
    "SK": "Словакия",
    "BG": "Болгария",
    "HR": "Хорватия",
    "RS": "Сербия",
    "SI": "Словения",
    "LT": "Литва",
    "LV": "Латвия",
    "EE": "Эстония",
    "MD": "Молдова",
    "GE": "Грузия",
    "AM": "Армения",
    "AZ": "Азербайджан",
    "UZ": "Узбекистан",
    "TJ": "Таджикистан",
    "KG": "Киргизия",
    "TM": "Туркменистан",
    "IL": "Израиль",
    "AE": "ОАЭ",
    "SA": "Сауд. Аравия",
    "TH": "Таиланд",
    "VN": "Вьетнам",
    "ID": "Индонезия",
    "MY": "Малайзия",
    "SG": "Сингапур",
    "KR": "Юж. Корея",
    "MX": "Мексика",
    "AR": "Аргентина",
    "CL": "Чили",
    "CO": "Колумбия",
    "PE": "Перу",
    "ZA": "ЮАР",
    "EG": "Египет",
    "NG": "Нигерия",
    "NZ": "Н. Зеландия",
    "IE": "Ирландия",
    "HK": "Гонконг",
    "TW": "Тайвань",
    "UNKNOWN": "Неизвестно",
}


def get_country_flag(country_code: str) -> str:
    """Получить флаг страны по коду (генерация из Unicode Regional Indicator Symbols)"""
    code = country_code.upper()
    if code == "UNKNOWN" or len(code) != 2:
        return "🌐"
    try:
        # Флаги генерируются из Regional Indicator Symbol Letters
        # A = U+1F1E6, B = U+1F1E7, ..., Z = U+1F1FF
        flag = "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code)
        return flag
    except Exception:
        return "🌐"


def get_country_name(country_code: str) -> str:
    """Получить название страны по коду"""
    return COUNTRY_NAMES.get(country_code.upper(), country_code.upper())
