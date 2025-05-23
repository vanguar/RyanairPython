# Ryanair Flight Search Telegram Bot

Этот Telegram-бот помогает искать дешёвые авиабилеты авиакомпании Ryanair.
Он использует неофициальное API через библиотеку `ryanair-py`.

## Возможности

* Поиск рейсов в одну сторону и туда-обратно.
* Выбор страны и города вылета/прилёта из списка.
* Выбор конкретной даты вылета и возвращения.
* Указание максимальной цены.
* **Гибкий поиск**:
    * Указание только аэропорта вылета (направление любое).
    * Указание только аэропорта прилёта (вылет из любого *указанного* города).
    * Поиск без указания конкретных дат (бот ищет на ближайший год).
* Если на указанную дату рейсов нет, бот автоматически предлагает поискать на +/- 7 дней.

## Установка и запуск локально

1.  **Клонируйте репозиторий:**
    ```bash
    git clone [https://github.com/vanguar/RyanairPython.git](https://github.com/vanguar/RyanairPython.git)
    cd RyanairPython
    ```

2.  **Создайте и активируйте виртуальное окружение:**
    ```bash
    python -m venv venv
    # Windows
    # venv\Scripts\activate
    # macOS/Linux
    # source venv/bin/activate
    ```

3.  **Установите зависимости:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Настройте переменные окружения:**
    Создайте файл `.env` в корневой директории проекта (скопируйте из `.env.example`) и укажите ваш токен Telegram-бота:
    ```
    TELEGRAM_BOT_TOKEN="ВАШ_ТЕЛЕГРАМ_БОТ_ТОКЕН"
    ```

5.  **Запустите бота:**
    ```bash
    python main.py
    ```

## Развёртывание на Railway

1.  Зарегистрируйтесь или войдите на [Railway](https://railway.app/).
2.  Создайте новый проект и выберите "Deploy from GitHub repo".
3.  Выберите этот репозиторий (`vanguar/RyanairPython`).
4.  В настройках сервиса на Railway (во вкладке "Variables") добавьте переменную окружения:
    * `TELEGRAM_BOT_TOKEN`: Укажите ваш токен Telegram-бота.
5.  Railway автоматически соберёт и запустит приложение, используя `Procfile`.

## Структура проекта


RyanairPython/
├── .env.example
├── .gitignore
├── Procfile
├── README.md
├── requirements.txt
├── data/
│   └── countries_data.json
├── bot/
│   ├── init.py
│   ├── config.py
│   ├── flight_api.py
│   ├── handlers.py
│   ├── keyboards.py
│   └── helpers.py
└── main.py


## Используемые технологии

* Python 3.9+
* [python-telegram-bot](https://python-telegram-bot.org/)
* [ryanair-py](https://github.com/pirxthepilot/ryanair-py)
* [python-dotenv](https://github.com/theskumar/python-dotenv)

## Важно

Этот бот использует неофициальное API Ryanair. Возможны изменения в работе API, которые могут повлиять на