"""Сервис для работы с регионами (внутренние объединения команд)"""
import json
import logging
from pathlib import Path
from typing import List, Set

logger = logging.getLogger(__name__)

# Путь к файлу с регионами
REGIONS_FILE = Path(__file__).parent.parent.parent / "data" / "regions.json"


class RegionService:
    """Сервис для управления регионами"""

    def __init__(self):
        self._regions: Set[str] = set()
        self._load_regions()

    def _load_regions(self) -> None:
        """Загрузить регионы из файла"""
        try:
            if REGIONS_FILE.exists():
                with open(REGIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._regions = set(data.get("regions", []))
                    logger.info(f"Loaded {len(self._regions)} regions from file")
            else:
                # Создаём файл с начальными регионами
                self._regions = set()
                self._save_regions()
                logger.info("Created new regions file")
        except Exception as e:
            logger.error(f"Error loading regions: {e}")
            self._regions = set()

    def _save_regions(self) -> None:
        """Сохранить регионы в файл"""
        try:
            # Создаём директорию если не существует
            REGIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Сортируем регионы по числовому значению
            sorted_regions = sorted(
                self._regions,
                key=lambda x: int(x) if x.isdigit() else float('inf')
            )

            with open(REGIONS_FILE, "w", encoding="utf-8") as f:
                json.dump({"regions": sorted_regions}, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(self._regions)} regions to file")
        except Exception as e:
            logger.error(f"Error saving regions: {e}")

    def get_regions(self) -> List[str]:
        """Получить отсортированный список регионов"""
        return sorted(
            self._regions,
            key=lambda x: int(x) if x.isdigit() else float('inf')
        )

    def region_exists(self, region: str) -> bool:
        """Проверить существование региона"""
        return region.strip() in self._regions

    def add_region(self, region: str) -> bool:
        """Добавить новый регион. Возвращает True если добавлен, False если уже существует"""
        region = region.strip()
        if region in self._regions:
            return False

        self._regions.add(region)
        self._save_regions()
        logger.info(f"Added new region: {region}")
        return True

    def remove_region(self, region: str) -> bool:
        """Удалить регион. Возвращает True если удалён, False если не существовал"""
        region = region.strip()
        if region not in self._regions:
            return False

        self._regions.remove(region)
        self._save_regions()
        logger.info(f"Removed region: {region}")
        return True

    def reload(self) -> None:
        """Перезагрузить регионы из файла"""
        self._load_regions()


# Глобальный экземпляр сервиса
region_service = RegionService()
