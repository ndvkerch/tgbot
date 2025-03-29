bot/
│── src/                    # Основной код бота
│   │── bot.py              # Точка входа (запуск бота)
│   │── config.py           # Конфигурации (API-ключи, пути, настройки)
│   │── database.py         # Работа с SQLite
│   │── keyboards.py        # Inline и Reply клавиатуры
│   │── middlewares.py      # Middleware для логирования, ограничений
│   │── services/           # Взаимодействие с внешними API
│   │   │── weather.py      # API погоды
│   │   │── geo.py          # Определение ближайших спотов
│   │── handlers/           # Обработчики команд
│   │   │── start.py        # /start, /help
│   │   │── profile.py      # /profile, редактирование данных
│   │   │── checkin.py      # /checkin, работа с геолокацией
│   │   │── weather.py      # /weather, прогноз погоды
│── tests/                  # Тесты
│   │── test_db.py          # Тестирование базы данных
│   │── test_handlers.py    # Тестирование команд
│── migrations/             # Миграции базы данных
│── .env                    # Переменные окружения (API-ключи, токены)
│── requirements.txt        # Python-зависимости
│── Dockerfile              # Docker-образ
│── docker-compose.yml      # Композиция сервисов (бот + БД)
│── README.md               # Документация
