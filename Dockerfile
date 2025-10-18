FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/bot.py .
RUN mkdir -p /app/data
RUN groupadd -r bot && useradd -r -g bot bot
RUN chown -R bot:bot /app
USER bot
CMD ["python", "bot.py"]
