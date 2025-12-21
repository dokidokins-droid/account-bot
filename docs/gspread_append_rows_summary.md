# Исправления для gspread.append_rows() - Краткая сводка

## Проблема

`append_rows()` БЕЗ параметра `table_range` может добавлять строки НЕ СРАЗУ после существующих данных, если где-то в других колонках (за пределами основных данных) есть случайные значения.

## Решение

Добавлен параметр `table_range` во все вызовы `append_rows()` и `append_row()`.

## Внесенные изменения

### 1. bot/services/number_service.py (строка 856-863)

**Было:**
```python
result = await ws_issued.append_rows(rows_to_add, value_input_option="USER_ENTERED")
```

**Стало:**
```python
result = await ws_issued.append_rows(
    rows_to_add,
    value_input_option="USER_ENTERED",
    table_range="A1:F"  # Колонки: Дата | Номер | Регионы | Employee | Ресурсы | Статус
)
```

### 2. bot/services/email_service.py (строка 453-458)

**Было:**
```python
await worksheet.append_rows(rows, value_input_option="USER_ENTERED")
```

**Стало:**
```python
await worksheet.append_rows(
    rows,
    value_input_option="USER_ENTERED",
    table_range="A1:G"  # Колонки: Дата | Логин | Пароль | Доп инфа | Регион | Employee | Статус
)
```

### 3. bot/services/proxy_service.py (строка 173-178)

**Было:**
```python
await ws.append_rows(rows_to_add, value_input_option="USER_ENTERED")
```

**Стало:**
```python
await ws.append_rows(
    rows_to_add,
    value_input_option="USER_ENTERED",
    table_range="A1:F"  # Колонки: proxy | country | added_date | expires_date | used_for | proxy_type
)
```

### 4. bot/services/sheets_service.py

#### Строка 394-400 (batch добавление):
```python
await ws.append_rows(
    rows,
    value_input_option="USER_ENTERED",
    table_range="A1:Z"  # Широкий диапазон для всех типов аккаунтов
)
```

#### Строка 453-457 (одиночное добавление):
```python
await ws.append_row(
    row_data,
    value_input_option="USER_ENTERED",
    table_range="A1:Z"  # Широкий диапазон для всех типов аккаунтов
)
```

## Как работает table_range

**Без table_range:**
- API сканирует ВСЕ колонки листа для поиска последней заполненной строки
- Если в колонке Z на строке 100 есть случайное значение, строки добавятся в строку 101

**С table_range="A1:F":**
- API сканирует ТОЛЬКО колонки A-F для поиска последней заполненной строки
- Игнорирует данные в других колонках (G, H, Z, и т.д.)
- Строки добавляются ПРЕДСКАЗУЕМО сразу после последних данных в указанном диапазоне

## Результат

Все вызовы `append_rows()` и `append_row()` теперь:
1. Предсказуемо добавляют строки сразу после существующих данных
2. Игнорируют случайные значения в неиспользуемых колонках
3. Имеют явное документирование структуры таблицы через комментарии

## Дополнительная документация

Полный анализ работы `append_rows()` см. в файле:
`D:\Workspace-projects\ResourceAllocation\account_bot\docs\gspread_append_rows_analysis.md`

## Проверка

После деплоя рекомендуется:
1. Протестировать добавление номеров/почт/прокси
2. Проверить что row_index вычисляется корректно
3. Убедиться что нет пустых строк между записями в Google Sheets

## Примечание о number_service.py

В `number_service.py` метод `_sync_issued_cache_to_sheets()` был ИЗМЕНЕН пользователем после нашего исправления.

**Текущая реализация использует `ws_issued.update()` вместо `append_rows()`:**
```python
# Находит последнюю заполненную строку вручную
last_filled_row = 1
for i, row in enumerate(issued_values, start=1):
    if row and any(cell.strip() for cell in row if cell):
        last_filled_row = i

# Использует update с явным диапазоном
range_str = f"A{start_row}:F{end_row}"
await ws_issued.update(range_str, rows_to_add, value_input_option="USER_ENTERED")
```

Это альтернативный подход который дает:
- **Преимущества**: 100% контроль над позицией, точный row_index
- **Недостатки**: Не использует атомарность append_rows

Оба подхода валидны. Выбор зависит от приоритетов:
- **append_rows с table_range**: проще, атомарнее, быстрее
- **update с вычисленным диапазоном**: больше контроля, точнее row_index
