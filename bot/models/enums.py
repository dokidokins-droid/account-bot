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
