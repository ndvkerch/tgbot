FROM python:3.11-slim

EXPOSE 30000  # <-- Указываем новый порт
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "src/bot.py"]