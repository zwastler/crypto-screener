# Crypto price screener

Это простое приложение которое слушает поток сделок бирж (по вебсокету подписывается на все рынки), и
следит за изменениями цены. Если цена удовлетворяет условиям сигналов, то приложение отправляет уведомление в телеграм.
Вместе с сообщением о изменении цены отправляется ссылка на Coinglass, для быстрого анализа рынка на возможные
торговые возможности.

При обновлении сигнала в течении 2 минут (таймаут задается через ENV
`SIGNAL_TIMEOUT`), при условии что проценты стали выше, сообщение в телеграм обновится
новыми данными.

## Список поддерживаемых бирж:

- Bybit
- Binance
- Okx
- Gate

## Configure

Для работы приложения необходимо создать файл `.env` в корне проекта и заполнить его следующими данными:

```dotenv
BOT_API_KEY="123456:BOT_TOKEN"  # Токен вашего телеграм бота для отправки сигналов созданный через @botfather
TARGET_IDS="[123456,234567]"  # Список ID пользователей телеграм, которым будут отправляться сигналы
SIGNAL_THRESHOLDS='["5,4","20,10"]'  # Пороги для отправки сигналов в формате ["период в минутах, порог изменения цены в %", ...]
# в примере выше, настроено два сигнала, если цена изменится на 4% за 5 минуты, и на 10% за 20 минут
# для быстрой проверки можете установить низкие пороги %, например ["5,1.5","10,2"]
```

## Install

Для запуска используется Docker compose. Перед запуском убедитесь что у вас установлен `docker` и `docker-compose`.

Вы можете запустить приложение с помощью команды:

```shell
docker compose -f deployment/docker-compose.yaml up -d --build
```

Вместе с приложением запустится docker контейнер с БД Redis с включенной модификацией RedisTimeSeries, который
необходим для работы приложения.

## Про зависимости

В проекте используются последние на момент публикации версии библиотек, хэши зависимостей которых запинены во 
избежание проблем с запуском в будущем:

- `python 3.12`
- `uvloop` для ускорения event loop
- `aiohttp` для работы с websockets
- `msgspec` для быстрой сериализации json
- `redis` для хранения стейта и работы с timeseries
- `emoji` для отправки красивых сообщений в telegram
- `pydantic-settings` для удобной работы и валидации настроек
- `structlog` для логирования

## License

MIT License

Copyright (c) 2024 Victor Wastler

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.