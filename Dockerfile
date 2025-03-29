# Используем Python 3.11 slim
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Обновляем pip и установочные инструменты
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Копируем файл зависимостей и устанавливаем пакеты
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект в контейнер
COPY . .

# Устанавливаем PYTHONPATH для корректного импорта модулей
ENV PYTHONPATH=/app/src

# Загружаем переменные окружения (при запуске)
ENV BOT_TOKEN=${BOT_TOKEN}

# Команда для запуска бота
CMD ["python", "src/bot.py"]