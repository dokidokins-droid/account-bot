# Telegram Bot Project

## Overview
A Python Telegram bot using aiogram framework that manages accounts and integrates with Google Sheets.

## Project Structure
- `bot/` - Main bot package
  - `main.py` - Entry point with bot initialization
  - `config.py` - Configuration using pydantic-settings
  - `handlers/` - Telegram message handlers
  - `keyboards/` - Inline keyboards
  - `middlewares/` - Request middleware (auth)
  - `models/` - Data models
  - `services/` - Business logic services
  - `states/` - FSM states
  - `utils/` - Utility functions
- `data/` - JSON data files for caching and configuration
- `docs/` - Documentation
- `scripts/` - Utility scripts
- `tests/` - Test files

## Running the Bot
```bash
python -m bot.main
```

## Required Environment Variables
- `BOT_TOKEN` - Telegram bot token
- `ADMIN_ID` - Telegram admin user ID
- `GOOGLE_CREDENTIALS_JSON` - Google service account credentials (JSON string)
- `SPREADSHEET_ACCOUNTS` - Google Sheets ID for accounts
- `SPREADSHEET_ISSUED` - Google Sheets ID for issued items

## Optional Environment Variables
- `REGIONS` - Comma-separated list of region codes (default: "546,621,545,674,538,719")

## Dependencies
- aiogram 3.13.1 - Telegram Bot framework
- gspread / gspread-asyncio - Google Sheets integration
- pydantic-settings - Configuration management
- aiohttp - Async HTTP client

## Recent Changes
- Initial Replit setup (December 2025)
