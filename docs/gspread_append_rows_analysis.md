# Анализ работы gspread.append_rows()

## Версии библиотек
- **gspread**: 6.0.2
- **gspread_asyncio**: 2.0.0

## 1. Как работает append_rows?

### Основной принцип

`append_rows()` использует Google Sheets API метод [values.append](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values/append), который:

**ДОБАВЛЯЕТ СТРОКИ ПОСЛЕ ПОСЛЕДНЕЙ ЗАПОЛНЕННОЙ СТРОКИ В УКАЗАННОМ ДИАПАЗОНЕ**

### Ключевые параметры

```python
def append_rows(
    self,
    values: Sequence[Sequence[Union[str, int, float]]],
    value_input_option: ValueInputOption = ValueInputOption.raw,
    insert_data_option: Optional[InsertDataOption] = None,
    table_range: Optional[str] = None,  # ВАЖНЫЙ ПАРАМЕТР!
    include_values_in_response: Optional[bool] = None,
) -> JSONResponse:
```

### Критический параметр: `table_range`

- **Если `table_range` НЕ УКАЗАН**: API ищет последнюю заполненную строку во ВСЕМ листе
- **Если `table_range` УКАЗАН** (например, `"A1:F1000"`): API ищет последнюю заполненную строку ТОЛЬКО В ЭТОМ ДИАПАЗОНЕ

## 2. Проблема в вашем коде

### Текущая реализация (строка 856)

```python
async with sheets_rate_limiter:
    result = await ws_issued.append_rows(rows_to_add, value_input_option="USER_ENTERED")
```

### Проблема

**БЕЗ `table_range` метод может добавить строки НЕ СРАЗУ после существующих данных!**

Почему:
1. Google Sheets API определяет "последнюю заполненную строку" сканируя ВСЕ столбцы
2. Если где-то в столбцах G, H, Z и т.д. есть данные, API может считать их "последней строкой"
3. Результат: строки добавляются с пропусками

### Пример проблемы

```
Строка 1: Заголовок | A | B | C | D | E | F |
Строка 2: Данные    | 1 | 2 | 3 | 4 | 5 | 6 |
Строка 3: Данные    | 7 | 8 | 9 | 10| 11| 12|
Строка 4: ПУСТО
Строка 5: ПУСТО
Строка 100: [в столбце Z случайно есть значение "test"]

append_rows() без table_range -> ДОБАВИТ В СТРОКУ 101!
```

## 3. Решение проблемы

### Вариант 1: Использовать table_range (РЕКОМЕНДУЕТСЯ)

```python
# Указываем диапазон таблицы (например, только колонки A-F)
async with sheets_rate_limiter:
    result = await ws_issued.append_rows(
        rows_to_add,
        value_input_option="USER_ENTERED",
        table_range="A1:F"  # Сканировать только колонки A-F
    )
```

**Преимущества:**
- API будет искать последнюю заполненную строку ТОЛЬКО в колонках A-F
- Игнорирует случайные данные в других колонках
- Предсказуемое поведение

### Вариант 2: Вручную вычислить номер строки

```python
async with sheets_rate_limiter:
    issued_values = await ws_issued.get_all_values()

# Находим последнюю непустую строку в нужных колонках
last_row_index = 1  # Заголовок
for idx, row in enumerate(issued_values[1:], start=2):
    # Проверяем только значимые колонки (например, колонку 2 - номер телефона)
    if row and len(row) >= 2 and row[1].strip():
        last_row_index = idx

# Записываем начиная со следующей строки
start_row = last_row_index + 1
for i, row_data in enumerate(rows_to_add):
    row_range = f"A{start_row + i}:F{start_row + i}"
    async with sheets_rate_limiter:
        await ws_issued.update(row_range, [row_data], value_input_option="USER_ENTERED")
```

**Преимущества:**
- Полный контроль над позицией
- Можно точно вычислить row_index

**Недостатки:**
- Больше API вызовов
- Медленнее чем append_rows
- Нет атомарности (между чтением и записью могут добавиться строки)

### Вариант 3: Batch update с вычисленным диапазоном

```python
async with sheets_rate_limiter:
    issued_values = await ws_issued.get_all_values()

# Находим последнюю непустую строку
last_row_index = len([r for r in issued_values if any(c.strip() for c in r[:6])])
start_row = last_row_index + 1

# Формируем диапазон для batch update
end_row = start_row + len(rows_to_add) - 1
batch_range = f"A{start_row}:F{end_row}"

async with sheets_rate_limiter:
    await ws_issued.update(
        batch_range,
        rows_to_add,
        value_input_option="USER_ENTERED"
    )
```

**Преимущества:**
- Один API вызов для всех строк
- Контроль над позицией
- Можно точно вычислить row_index

**Недостатки:**
- Race condition между чтением и записью
- Нужно вручную вычислять индексы

## 4. Атомарность и Race Conditions

### Проблема в текущем коде

В методе `_sync_issued_cache_to_sheets()` есть потенциальная проблема:

```python
# ШАГ 1: Читаем состояние
async with sheets_rate_limiter:
    issued_values = await ws_issued.get_all_values()

# ... обработка ...

# ШАГ 5: Добавляем строки (ВРЕМЯ ПРОШЛО!)
async with sheets_rate_limiter:
    result = await ws_issued.append_rows(rows_to_add, ...)

# Между чтением и записью могла произойти другая запись!
```

### Решение: Глобальная блокировка (УЖЕ ЕСТЬ!)

В вашем коде уже есть `self._sync_lock`, который защищает от параллельных синхронизаций:

```python
async with self._sync_lock:
    # Только одна синхронизация одновременно
    ...
```

**Это правильно!** Но нужно убедиться, что lock используется везде.

## 5. Рекомендации для вашего кода

### Оптимальное решение для number_service.py

```python
async def _sync_issued_cache_to_sheets(self) -> None:
    # ... существующий код до строки 846 ...

    # === ШАГ 5: Добавляем новые строки ===
    if rows_to_add:
        rows_before_append = len(issued_values)

        logger.info(f"Appending {len(rows_to_add)} rows (current rows: {rows_before_append})")

        async with sheets_rate_limiter:
            # ИСПОЛЬЗУЕМ table_range для предсказуемости
            result = await ws_issued.append_rows(
                rows_to_add,
                value_input_option="USER_ENTERED",
                table_range="A1:F"  # Только колонки данных
            )

        logger.info(f"Synced {len(rows_to_add)} new records (result: {result})")

        # Вычисляем row_index
        async with self._issued_cache_lock:
            for idx, record in enumerate(records_for_new_rows):
                record.row_index = rows_before_append + 1 + idx
                logger.debug(f"Assigned row_index {record.row_index} to {record.number}")
```

### Проверка корректности индексов

Добавьте валидацию после записи:

```python
# После append_rows
if len(rows_to_add) > 0:
    # Перечитываем ТОЛЬКО новые строки для проверки
    async with sheets_rate_limiter:
        new_values = await ws_issued.get_values(
            f"A{rows_before_append + 1}:F{rows_before_append + len(rows_to_add)}"
        )

    # Проверяем что номера совпадают
    for idx, (written_row, expected_record) in enumerate(zip(new_values, records_for_new_rows)):
        written_number = written_row[1] if len(written_row) > 1 else ""
        if written_number != expected_record.number:
            logger.error(
                f"Row index mismatch! Expected {expected_record.number} "
                f"at {rows_before_append + 1 + idx}, got {written_number}"
            )
            # Пометить как требующий повторной синхронизации
            expected_record.row_index = None
```

## 6. Альтернативы append_rows

### 6.1. update() с вычисленным диапазоном

```python
# Читаем текущее состояние
all_values = await ws.get_all_values()
next_row = len(all_values) + 1

# Записываем batch'ем
await ws.update(
    f"A{next_row}:F{next_row + len(rows_to_add) - 1}",
    rows_to_add,
    value_input_option="USER_ENTERED"
)
```

**Когда использовать:**
- Нужен точный контроль над row_index
- Структура таблицы сложная

### 6.2. batch_update() (используется в вашем коде)

```python
await batch_update_cells(ws_issued, [
    {"row": 10, "col": 1, "value": "data"},
    {"row": 10, "col": 2, "value": "more data"},
])
```

**Когда использовать:**
- Обновление существующих ячеек
- Точечные изменения

### 6.3. append_rows() с table_range

```python
await ws.append_rows(
    rows_to_add,
    value_input_option="USER_ENTERED",
    table_range="A1:F"  # Указываем диапазон!
)
```

**Когда использовать:**
- Простое добавление строк в конец
- Структура таблицы простая (без лишних колонок)
- **РЕКОМЕНДУЕТСЯ для вашего случая**

## 7. Итоговые рекомендации

### Для метода _sync_issued_cache_to_sheets():

1. **Добавьте `table_range="A1:F"` в append_rows()** (строка 856)
2. **Сохраните использование `_sync_lock`** (уже есть, правильно)
3. **Добавьте валидацию** после записи (опционально)
4. **Логируйте result от append_rows()** для отладки

### Измененный код (строки 845-868):

```python
# === ШАГ 5: Добавляем новые строки ===
if rows_to_add:
    rows_before_append = len(issued_values)

    logger.info(
        f"Appending {len(rows_to_add)} rows to sheet '{issued_sheet_name}' "
        f"(current rows: {rows_before_append})"
    )
    for row_data in rows_to_add:
        logger.debug(f"  Row data: {row_data}")

    async with sheets_rate_limiter:
        result = await ws_issued.append_rows(
            rows_to_add,
            value_input_option="USER_ENTERED",
            table_range="A1:F"  # КРИТИЧЕСКИ ВАЖНО!
        )

    logger.info(
        f"Synced {len(rows_to_add)} new records to sheets "
        f"(rows before: {rows_before_append}, result: {result})"
    )

    # Вычисляем row_index
    async with self._issued_cache_lock:
        for idx, record in enumerate(records_for_new_rows):
            record.row_index = rows_before_append + 1 + idx
            logger.debug(f"Assigned row_index {record.row_index} to {record.number}")
```

## 8. Дополнительная информация

### Google Sheets API Reference

- [values.append](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values/append)
- [InsertDataOption](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values/append#InsertDataOption)
- [ValueInputOption](https://developers.google.com/sheets/api/reference/rest/v4/ValueInputOption)

### Поведение по умолчанию

Из документации Google Sheets API:

> "The input range is used to search for existing data and find a "table"
> within that range. Values will be appended to the next row of the table,
> starting with the first column of the table."

**Важно:** "table" определяется как непрерывный блок заполненных ячеек!

### Возвращаемое значение append_rows()

```json
{
  "spreadsheetId": "...",
  "tableRange": "Sheet1!A1:F10",
  "updates": {
    "spreadsheetId": "...",
    "updatedRange": "Sheet1!A11:F13",  // Где РЕАЛЬНО записались данные
    "updatedRows": 3,
    "updatedColumns": 6,
    "updatedCells": 18
  }
}
```

**Используйте `result['updates']['updatedRange']`** для точного определения
где были записаны данные!

## 9. Пример парсинга результата

```python
async with sheets_rate_limiter:
    result = await ws_issued.append_rows(
        rows_to_add,
        value_input_option="USER_ENTERED",
        table_range="A1:F",
        include_values_in_response=False  # Для производительности
    )

# Парсим диапазон из результата
if "updates" in result and "updatedRange" in result["updates"]:
    updated_range = result["updates"]["updatedRange"]
    # Пример: "Sheet1!A11:F13"
    match = re.search(r'!A(\d+):F(\d+)', updated_range)
    if match:
        start_row = int(match.group(1))
        end_row = int(match.group(2))
        logger.info(f"Data written to rows {start_row}-{end_row}")

        # Присваиваем row_index
        for idx, record in enumerate(records_for_new_rows):
            record.row_index = start_row + idx
```

## 10. Заключение

**Главный вывод:**

`append_rows()` БЕЗ `table_range` может вести себя непредсказуемо!

**Решение:**

ВСЕГДА указывайте `table_range` при использовании `append_rows()`:

```python
await ws.append_rows(data, table_range="A1:F")
```

Это гарантирует что:
1. Строки добавятся СРАЗУ после последней заполненной в указанном диапазоне
2. Игнорируются случайные данные в других колонках
3. Поведение предсказуемо и детерминировано
