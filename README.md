
# Real Estate Telegram Bot

Бот для поиска объектов недвижимости по адресу и кадастровому номеру, с возможностями просмотра на карте, интеграцией с Росреестром, Яндекс Геокодером и сервисами Avito, Cian, Yandex Недвижимость.

## Запуск

1. Скопируйте `.env.example` в `.env` и вставьте ваши токены
2. Соберите Docker контейнер:

```
docker build -t real-estate-bot .
docker run --env-file .env real-estate-bot
```
