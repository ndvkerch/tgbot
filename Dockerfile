FROM python:3.11-slim

WORKDIR /app

# Указываем порт, который будет использоваться приложением
EXPOSE 8000  # <- Добавьте эту строку

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONPATH=/app/src
ENV BOT_TOKEN=${BOT_TOKEN}

CMD ["python", "src/bot.py"]