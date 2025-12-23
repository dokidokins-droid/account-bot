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
            "mamba": "🔴",
            "ok": "🟠",
            "gmail": "📧",
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
    NONE = "none"  # Для ресурсов без выбора пола (VK, OK)

    @property
    def display_name(self) -> str:
        names = {
            "male": "Мужской",
            "female": "Женский",
            "any": "Обычные",
            "gmail_domain": "gmail.com",
            "none": "—",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "male": "👨",
            "female": "👩",
            "any": "📧",
            "gmail_domain": "📧",
            "none": "",
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
        """Название для кнопок (с эмодзи)"""
        names = {
            "block": "🚫 Блок",
            "good": "✅ Хороший",
            "defect": "⚠️ Дефектный",
        }
        return names[self.value]

    @property
    def table_name(self) -> str:
        """Название для записи в таблицу (без эмодзи, с большой буквы)"""
        names = {
            "block": "Блок",
            "good": "Хороший",
            "defect": "Дефектный",
        }
        return names[self.value]

    @property
    def background_color(self) -> dict:
        """Цвет фона для ячейки (RGB в формате 0-1)"""
        colors = {
            # Блок - светло-красный
            "block": {"red": 0.96, "green": 0.80, "blue": 0.80},
            # Хороший - светло-зелёный
            "good": {"red": 0.85, "green": 0.94, "blue": 0.85},
            # Дефектный - светло-жёлтый
            "defect": {"red": 1.0, "green": 0.95, "blue": 0.80},
        }
        return colors[self.value]


class ProxyResource(str, Enum):
    """Ресурсы для которых используются прокси"""
    VK = "vk"
    MAMBA = "mamba"
    OK = "ok"
    LOVEPLANET = "loveplanet"
    TEAMO = "teamo"
    BADOO = "badoo"
    BEBOO = "beboo"
    LOLOO = "loloo"
    TOPFACE = "topface"
    LOVERU = "loveru"
    FOTOSTRANA = "fotostrana"
    GALAXY = "galaxy"
    OTHER = "other"

    @property
    def display_name(self) -> str:
        names = {
            "vk": "ВКонтакте",
            "mamba": "Мамба",
            "ok": "Одноклассники",
            "loveplanet": "LovePlanet",
            "teamo": "Teamo",
            "badoo": "Badoo",
            "beboo": "Beboo",
            "loloo": "Loloo",
            "topface": "Topface",
            "loveru": "Love.ru",
            "fotostrana": "Фотострана",
            "galaxy": "Galaxy",
            "other": "Другие",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "vk": "🔵",
            "mamba": "🔴",
            "ok": "🟠",
            "loveplanet": "💙",
            "teamo": "💚",
            "badoo": "🟣",
            "beboo": "🟧",
            "loloo": "🟦",
            "topface": "🎭",
            "loveru": "🔺",
            "fotostrana": "📷",
            "galaxy": "🚀",
            "other": "🔘",
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


class ProxyType(str, Enum):
    """Тип прокси"""
    HTTP = "http"
    SOCKS5 = "socks5"

    @property
    def display_name(self) -> str:
        names = {
            "http": "HTTP",
            "socks5": "SOCKS5",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "http": "🌐",
            "socks5": "🔒",
        }
        return emojis[self.value]

    @property
    def button_text(self) -> str:
        return f"{self.emoji} {self.display_name}"


class NumberResource(str, Enum):
    """Ресурсы для номеров телефонов"""
    BEBOO = "beboo"
    LOLOO = "loloo"
    TABOR = "tabor"

    @property
    def display_name(self) -> str:
        names = {
            "beboo": "Beboo",
            "loloo": "Loloo",
            "tabor": "Табор",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "beboo": "🟧",
            "loloo": "🟦",
            "tabor": "🟥",
        }
        return emojis[self.value]

    @property
    def button_text(self) -> str:
        return f"{self.emoji} {self.display_name}"


class NumberStatus(str, Enum):
    """Статусы номеров телефонов"""
    WORKING = "working"
    RESET = "reset"
    REGISTERED = "registered"
    TG_KICKED = "tg_kicked"

    @property
    def display_name(self) -> str:
        """Название для кнопок (с эмодзи)"""
        names = {
            "working": "✅ Рабочий",
            "reset": "🔄 Сброс",
            "registered": "📝 Зареган",
            "tg_kicked": "❌ Выбило ТГ",
        }
        return names[self.value]

    @property
    def table_name(self) -> str:
        """Название для записи в таблицу (без эмодзи, с большой буквы)"""
        names = {
            "working": "Рабочий",
            "reset": "Сброс",
            "registered": "Зареган",
            "tg_kicked": "Выбило ТГ",
        }
        return names[self.value]

    @property
    def background_color(self) -> dict:
        """Цвет фона для ячейки (RGB в формате 0-1)"""
        colors = {
            # Рабочий - светло-зелёный
            "working": {"red": 0.85, "green": 0.94, "blue": 0.85},
            # Сброс - светло-оранжевый
            "reset": {"red": 1.0, "green": 0.90, "blue": 0.80},
            # Зареган - светло-красный
            "registered": {"red": 0.96, "green": 0.80, "blue": 0.80},
            # Выбило ТГ - светло-вишнёвый
            "tg_kicked": {"red": 0.92, "green": 0.75, "blue": 0.80},
        }
        return colors[self.value]


class EmailResource(str, Enum):
    """Почтовые ресурсы"""
    GMAIL = "gmail"
    RAMBLER = "rambler"

    @property
    def display_name(self) -> str:
        names = {
            "gmail": "Gmail",
            "rambler": "Рамблер",
        }
        return names[self.value]

    @property
    def emoji(self) -> str:
        emojis = {
            "gmail": "🟢",
            "rambler": "🔵",
        }
        return emojis[self.value]

    @property
    def button_text(self) -> str:
        return f"{self.emoji} {self.display_name}"


# Названия стран (полный список ISO 3166-1 alpha-2)
COUNTRY_NAMES = {
    # СНГ и Восточная Европа
    "RU": "Россия",
    "UA": "Украина",
    "BY": "Беларусь",
    "KZ": "Казахстан",
    "UZ": "Узбекистан",
    "TJ": "Таджикистан",
    "KG": "Киргизия",
    "TM": "Туркменистан",
    "MD": "Молдова",
    "GE": "Грузия",
    "AM": "Армения",
    "AZ": "Азербайджан",
    # Западная Европа
    "DE": "Германия",
    "FR": "Франция",
    "GB": "Великобритания",
    "IT": "Италия",
    "ES": "Испания",
    "PT": "Португалия",
    "NL": "Нидерланды",
    "BE": "Бельгия",
    "LU": "Люксембург",
    "CH": "Швейцария",
    "AT": "Австрия",
    "IE": "Ирландия",
    "MC": "Монако",
    "AD": "Андорра",
    "LI": "Лихтенштейн",
    "MT": "Мальта",
    # Северная Европа
    "SE": "Швеция",
    "NO": "Норвегия",
    "FI": "Финляндия",
    "DK": "Дания",
    "IS": "Исландия",
    # Центральная Европа
    "PL": "Польша",
    "CZ": "Чехия",
    "SK": "Словакия",
    "HU": "Венгрия",
    # Южная Европа
    "GR": "Греция",
    "CY": "Кипр",
    # Балканы
    "RO": "Румыния",
    "BG": "Болгария",
    "HR": "Хорватия",
    "RS": "Сербия",
    "SI": "Словения",
    "BA": "Босния",
    "ME": "Черногория",
    "MK": "Сев. Македония",
    "AL": "Албания",
    "XK": "Косово",
    # Прибалтика
    "LT": "Литва",
    "LV": "Латвия",
    "EE": "Эстония",
    # Северная Америка
    "US": "США",
    "CA": "Канада",
    "MX": "Мексика",
    # Центральная Америка
    "GT": "Гватемала",
    "BZ": "Белиз",
    "HN": "Гондурас",
    "SV": "Сальвадор",
    "NI": "Никарагуа",
    "CR": "Коста-Рика",
    "PA": "Панама",
    # Карибы
    "CU": "Куба",
    "DO": "Доминикана",
    "JM": "Ямайка",
    "HT": "Гаити",
    "PR": "Пуэрто-Рико",
    "TT": "Тринидад",
    "BB": "Барбадос",
    "BS": "Багамы",
    # Южная Америка
    "BR": "Бразилия",
    "AR": "Аргентина",
    "CL": "Чили",
    "CO": "Колумбия",
    "PE": "Перу",
    "VE": "Венесуэла",
    "EC": "Эквадор",
    "BO": "Боливия",
    "PY": "Парагвай",
    "UY": "Уругвай",
    "GY": "Гайана",
    "SR": "Суринам",
    # Ближний Восток
    "IL": "Израиль",
    "AE": "ОАЭ",
    "SA": "Сауд. Аравия",
    "TR": "Турция",
    "IR": "Иран",
    "IQ": "Ирак",
    "SY": "Сирия",
    "JO": "Иордания",
    "LB": "Ливан",
    "KW": "Кувейт",
    "QA": "Катар",
    "BH": "Бахрейн",
    "OM": "Оман",
    "YE": "Йемен",
    "PS": "Палестина",
    # Азия
    "CN": "Китай",
    "JP": "Япония",
    "KR": "Юж. Корея",
    "KP": "Сев. Корея",
    "IN": "Индия",
    "PK": "Пакистан",
    "BD": "Бангладеш",
    "TH": "Таиланд",
    "VN": "Вьетнам",
    "ID": "Индонезия",
    "MY": "Малайзия",
    "SG": "Сингапур",
    "PH": "Филиппины",
    "MM": "Мьянма",
    "KH": "Камбоджа",
    "LA": "Лаос",
    "NP": "Непал",
    "LK": "Шри-Ланка",
    "MN": "Монголия",
    "AF": "Афганистан",
    "HK": "Гонконг",
    "TW": "Тайвань",
    "MO": "Макао",
    "BN": "Бруней",
    "TL": "Восточ. Тимор",
    "MV": "Мальдивы",
    # Океания
    "AU": "Австралия",
    "NZ": "Н. Зеландия",
    "FJ": "Фиджи",
    "PG": "Папуа Н. Гвинея",
    "NC": "Н. Каледония",
    "WS": "Самоа",
    "GU": "Гуам",
    # Африка - Северная
    "EG": "Египет",
    "MA": "Марокко",
    "DZ": "Алжир",
    "TN": "Тунис",
    "LY": "Ливия",
    "SD": "Судан",
    # Африка - Западная
    "NG": "Нигерия",
    "GH": "Гана",
    "CI": "Кот-д'Ивуар",
    "SN": "Сенегал",
    "ML": "Мали",
    "BF": "Буркина-Фасо",
    "NE": "Нигер",
    "GN": "Гвинея",
    "BJ": "Бенин",
    "TG": "Того",
    "SL": "Сьерра-Леоне",
    "LR": "Либерия",
    "MR": "Мавритания",
    "GM": "Гамбия",
    "GW": "Гвинея-Бисау",
    "CV": "Кабо-Верде",
    # Африка - Восточная
    "KE": "Кения",
    "TZ": "Танзания",
    "UG": "Уганда",
    "ET": "Эфиопия",
    "RW": "Руанда",
    "BI": "Бурунди",
    "SS": "Южный Судан",
    "SO": "Сомали",
    "ER": "Эритрея",
    "DJ": "Джибути",
    "MG": "Мадагаскар",
    "MU": "Маврикий",
    "SC": "Сейшелы",
    "KM": "Коморы",
    "MW": "Малави",
    "ZM": "Замбия",
    "ZW": "Зимбабве",
    "MZ": "Мозамбик",
    # Африка - Центральная
    "CD": "ДР Конго",
    "CG": "Конго",
    "CM": "Камерун",
    "AO": "Ангола",
    "GA": "Габон",
    "TD": "Чад",
    "CF": "ЦАР",
    "GQ": "Экв. Гвинея",
    "ST": "Сан-Томе",
    # Африка - Южная
    "ZA": "ЮАР",
    "NA": "Намибия",
    "BW": "Ботсвана",
    "SZ": "Эсватини",
    "LS": "Лесото",
    # Неизвестно
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
