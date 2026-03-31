# 💰 Заработай СЕГОДНЯ: Продай AI Telegram-бот шаблон

> Дата анализа: 29 марта 2026
> Время реализации: 2–4 часа
> Потенциал: $29–$49 за продажу, 10–30 продаж в первый месяц = **$290–$1470**

---

## 1. ЧТО ИМЕННО СОЗДАЁМ

**"AI Assistant Bot Starter Kit"** — готовый Python-шаблон Telegram-бота с AI-интеграцией

### Состав пакета (что получает покупатель):
- `bot.py` — основной бот на `aiogram 3.x`
- Интеграция с Claude API (Anthropic) или OpenAI GPT-4o
- Система диалоговой памяти (хранение контекста разговора)
- Команды: `/start`, `/help`, `/reset`, `/mode` (переключение режимов: ассистент / переводчик / редактор кода)
- Система подписок: бесплатный лимит (20 сообщений/день) + платный режим
- Интеграция с Telegram Stars (встроенная оплата Telegram)
- Docker + `docker-compose.yml` для мгновенного деплоя
- `.env.example` с понятными инструкциями
- `README.md` на русском и английском
- Видео-инструкция (экранная запись, 5 минут): запуск за 10 минут

### Почему это продаётся:
- Telegram в 2026 — #1 мессенджер в СНГ и топ-3 в мире
- 260+ скриптов чат-ботов на CodeCanyon, но мало **готовых, простых, с Claude/GPT**
- Разработчики и малый бизнес хотят запустить бота быстро, не разбираясь в AI API

---

## 2. ГДЕ ПРОДАЁМ / РАЗМЕЩАЕМ

### Основная площадка: **Gumroad** (gumroad.com)
- 0 вложений, моментальная регистрация
- Выплаты на карту / PayPal / Wise
- Комиссия: 10% от продажи (у тебя остаётся $26–$44 с каждой)
- Цифровые товары продаются автоматически 24/7

### Дополнительно (после первых продаж):
- **CodeCanyon (Envato)** — продажи выше, но модерация 1–3 дня
- **Telegram-канал** — создаёшь канал @ai_bot_template, закрепляешь демо-видео
- **GitHub Sponsors / Buy me a coffee** — для open-source версии с платным Pro

---

## 3. СКОЛЬКО СТОИТ И ПОЧЕМУ

### Цена: **$39** (основной пакет)

| Пакет | Цена | Что включено |
|-------|------|--------------|
| Basic | $29 | Код бота + README |
| **Pro (рекомендуем)** | **$39** | Код + Docker + видео + 30 дней поддержки в TG |
| Agency | $79 | Pro + лицензия на перепродажу клиентам |

### Почему $39, а не $9:
- Конкуренты на CodeCanyon: Telegram AI Chatbot — $49–$69
- Аналогичные n8n-шаблоны на Gumroad: $19–$49
- Покупатель экономит 4–8 часов своего времени → $39 — это дёшево
- Низкая цена ($9) = сигнал «плохое качество», высокая ($99) = долгое раздумье

---

## 4. ПОШАГОВЫЙ ПЛАН СОЗДАНИЯ ЗА 2–4 ЧАСА

### ⏱ Час 1: Пишем код (60 минут)

```bash
mkdir ai-telegram-bot-kit && cd ai-telegram-bot-kit
python -m venv venv && source venv/bin/activate
pip install aiogram anthropic python-dotenv aiosqlite
```

**Структура проекта:**
```
ai-telegram-bot-kit/
├── bot.py              # главный файл
├── handlers/
│   ├── chat.py         # обработка сообщений + AI ответ
│   ├── billing.py      # Telegram Stars оплата
│   └── admin.py        # /stats для владельца
├── services/
│   ├── ai_client.py    # обёртка над Claude/OpenAI API
│   └── db.py           # SQLite: пользователи, лимиты
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

**Минимальный рабочий `bot.py`:**
```python
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart
from services.ai_client import get_ai_response
from services.db import check_and_decrement_limit
import os
from dotenv import load_dotenv

load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Привет! Я AI-ассистент на базе Claude.\n"
        "У тебя 20 бесплатных сообщений в день.\n"
        "Просто напиши мне что-нибудь!"
    )

@dp.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    has_limit = await check_and_decrement_limit(user_id)

    if not has_limit:
        await message.answer(
            "❌ Лимит на сегодня исчерпан.\n"
            "💎 Оформи подписку: /subscribe"
        )
        return

    await message.answer("⏳ Думаю...")
    response = await get_ai_response(
        user_id=user_id,
        text=message.text
    )
    await message.answer(response)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

### ⏱ Час 2: Docker + README + .env (30 минут)

**`docker-compose.yml`:**
```yaml
version: '3.8'
services:
  bot:
    build: .
    env_file: .env
    restart: unless-stopped
    volumes:
      - ./data:/app/data
```

**`.env.example`:**
```env
BOT_TOKEN=your_telegram_bot_token_here
ANTHROPIC_API_KEY=your_claude_api_key_here
# ИЛИ: OPENAI_API_KEY=your_openai_key_here
DAILY_FREE_LIMIT=20
ADMIN_ID=your_telegram_user_id
```

**README.md** (30 строк):
- Что это
- Быстрый старт (4 команды)
- Как получить ключи API
- Как настроить платёжку
- Скриншоты работающего бота

### ⏱ Час 3: Записываем видео + создаём страницу на Gumroad (45 минут)

1. Запускаем бота локально, показываем как работает (2 мин)
2. Деплой через Docker на VPS (3 мин)
3. Регистрируемся на Gumroad → New Product → Digital Product
4. Загружаем ZIP-архив с кодом
5. Пишем описание страницы (используй шаблон ниже)

**Шаблон описания для Gumroad:**
```
🤖 AI Telegram Bot — Ready-to-Deploy Starter Kit

Launch your own AI assistant bot in 10 minutes.
Built with Python + aiogram 3 + Claude API.

✅ What's included:
• Full source code (aiogram 3 + Claude/GPT)
• Docker deployment (1 command launch)
• Built-in daily limits + Telegram Stars payments
• Russian & English README
• 5-min setup video
• 30 days Telegram support

Perfect for: developers, agencies, solopreneurs
No subscription fees — one-time purchase, yours forever.
```

### ⏱ Час 4: Первые клиенты (45 минут)

(см. раздел 5)

---

## 5. КАК ПРИВЛЕЧЬ ПЕРВЫХ КЛИЕНТОВ

### День 1 (сегодня, первые 3 часа после публикации):

**🔴 Быстрые каналы (делай параллельно):**

1. **Reddit** — пост в r/TelegramBots, r/PythonProjects, r/SideProject:
   > "I built an AI Telegram bot starter kit with Claude API + Docker.
   > Saves 4+ hours of setup. Launching at $29 today only. Link in comments."

2. **Telegram-чаты** (русскоязычные, 50k+ участников):
   - `@botoid` — чат разработчиков ботов
   - `@python_jobs` — Python вакансии и проекты
   - `@indie_makers_ru` — инди-разработчики
   > Сообщение: "Выложил шаблон AI Telegram-бота (Claude/GPT + Docker).
   > Запуск за 10 минут. $39 на Gumroad — ссылка: [ссылка]"

3. **Twitter/X** — твит с GIF-демо работающего бота:
   > "Built an AI Telegram bot template in 3 hours.
   > Claude API + aiogram + Docker + payments.
   > Selling on Gumroad for $39.
   > #buildinpublic #indiehacker #telegram"

4. **IndieHackers.com** — пост "I launched X in 3 hours":
   - Пиши честно: "Built this today, selling on Gumroad"
   - IndieHackers любит истории "build in public"

5. **ProductHunt** — запуск через 1–2 дня (нужна подготовка):
   - Требует hunter + supporters, но даёт 500–2000 просмотров

### Неделя 1 (удержание и масштаб):

6. **YouTube Shorts / TikTok** — видео "Запускаю AI-бота за 10 минут":
   - Запись экрана + голос = 60 секунд
   - CTA в конце: "Шаблон в описании"

7. **Fiverr / Kwork** — предложи "настройка AI Telegram-бота за $50":
   - Продаёшь услугу, но отдаёшь шаблон → быстро и просто
   - Kwork.ru — русскоязычный Fiverr, конкуренция ниже

8. **GitHub** — выложи урезанную версию (без платёжки):
   - README с ссылкой на Gumroad Pro-версию
   - Звёзды = социальное доказательство

---

## 📊 Прогноз доходов

| Период | Продажи | Доход |
|--------|---------|-------|
| День 1 | 1–3 | $29–$117 |
| Неделя 1 | 5–10 | $145–$390 |
| Месяц 1 | 15–30 | $435–$1,170 |
| Месяц 3 (с отзывами) | 30–60/мес | $870–$2,340/мес |

---

## ⚡ ЧЕКЛИСТ НА СЕГОДНЯ

- [ ] Создать папку проекта и написать `bot.py`
- [ ] Написать `services/ai_client.py` и `services/db.py`
- [ ] Создать `docker-compose.yml` и `.env.example`
- [ ] Протестировать локально (бот отвечает)
- [ ] Записать 5-минутное видео (Loom / OBS)
- [ ] Зарегистрироваться на Gumroad (5 минут)
- [ ] Создать продукт, загрузить ZIP + видео
- [ ] Написать в 3–5 Telegram-чатов
- [ ] Запостить в Reddit (r/TelegramBots)
- [ ] Запостить в Twitter/X

---

## 🛠 Нужные инструменты (все бесплатные)

| Инструмент | Для чего | Стоимость |
|-----------|---------|-----------|
| Gumroad | Продажа | Бесплатно (10% комиссия) |
| BotFather | Создать бота | Бесплатно |
| Anthropic API | Claude API | $5 кредит при регистрации |
| Railway / Render | Хостинг бота для демо | Бесплатный tier |
| Loom | Запись видео | Бесплатно (5 мин) |

---

## 💡 Почему именно ЭТОТ продукт?

1. **Спрос подтверждён**: CodeCanyon продаёт 260+ скриптов чат-ботов, Telegram AI боты — в топе поиска
2. **Конкуренция управляема**: большинство конкурентов — PHP-скрипты или устаревшие, без Claude API
3. **Повторные продажи**: покупатель, который запустил бота, вернётся за следующими шаблонами
4. **Пассивный доход**: выложил один раз — продаётся автоматически
5. **Масштаб**: один шаблон → линейка (WhatsApp-бот, Discord-бот, Web-виджет) → $200+/мес стабильно

---

*Создано: 29 марта 2026 | Актуально для: Python 3.11+, aiogram 3.x, Claude 3.5+*
