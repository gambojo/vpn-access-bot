FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY bot.py .

# Создание папки для данных
RUN mkdir -p /app/data

# Создание непривилегированного пользователя
RUN groupadd -r bot && useradd -r -g bot bot
RUN chown -R bot:bot /app
USER bot

# Запуск бота
CMD ["python", "bot.py"]