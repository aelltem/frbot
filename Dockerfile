# Dockerfile
FROM python:3.11

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
