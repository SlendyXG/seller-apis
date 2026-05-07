import datetime
import logging.config
from environs import Env
from seller import download_stock

import requests

from seller import divide, price_conversion

logger = logging.getLogger(__file__)


def get_product_list(page, campaign_id, access_token):
    """Получает список товаров из кампании Яндекс Маркета.

    Args:
        page: Токен страницы для пагинации (nextPageToken).
        campaign_id: Идентификатор кампании продавца на Яндекс Маркете.
        access_token: API-токен для авторизации.

    Returns:
        Словарь с результатами запроса, содержащий список товаров,
        информацию о пагинации и общее количество.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> get_product_list("", 12345, "token_xyz")
        {'offerMappingEntries': [...], 'paging': {'nextPageToken': 'abc123'}}
    """
    endpoint_url = "https://api.partner.market.yandex.ru/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Host": "api.partner.market.yandex.ru",
    }
    payload = {
        "page_token": page,
        "limit": 200,
    }
    url = endpoint_url + f"campaigns/{campaign_id}/offer-mapping-entries"
    response = requests.get(url, headers=headers, params=payload)
    response.raise_for_status()
    response_object = response.json()
    return response_object.get("result")


def update_stocks(stocks, campaign_id, access_token):
    """Обновляет остатки товаров на Яндекс Маркете.

    Отправляет список с новыми остатками в API Яндекс Маркета.
    За один запрос можно обновить до 2000 товаров.

    Args:
        stocks: Список словарей с остатками товаров. Каждый словарь должен
                содержать sku, warehouseId и items с количеством.
        campaign_id: Идентификатор кампании продавца на Яндекс Маркете.
        access_token: API-токен для авторизации.

    Returns:
        Словарь с ответом API Яндекс Маркета.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> stocks = [{"sku": "123", "warehouseId": 12345, "items": [{"count": 10, "type": "FIT"}]}]
        >>> update_stocks(stocks, 12345, "token_xyz")
        {'status': 'OK'}
    """
    endpoint_url = "https://api.partner.market.yandex.ru/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Host": "api.partner.market.yandex.ru",
    }
    payload = {"skus": stocks}
    url = endpoint_url + f"campaigns/{campaign_id}/offers/stocks"
    response = requests.put(url, headers=headers, json=payload)
    response.raise_for_status()
    response_object = response.json()
    return response_object


def update_price(prices, campaign_id, access_token):
    """Обновляет цены товаров на Яндекс Маркете.

    Отправляет список с новыми ценами в API Яндекс Маркета.
    За один запрос можно обновить до 500 товаров.

    Args:
        prices: Список словарей с ценами товаров. Каждый словарь должен
                содержать id и price с value и currencyId.
        campaign_id: Идентификатор кампании продавца на Яндекс Маркете.
        access_token: API-токен для авторизации.

    Returns:
        Словарь с ответом API Яндекс Маркета.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> prices = [{"id": "123", "price": {"value": 5990, "currencyId": "RUR"}}]
        >>> update_price(prices, 12345, "token_xyz")
        {'status': 'OK'}
    """
    endpoint_url = "https://api.partner.market.yandex.ru/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Host": "api.partner.market.yandex.ru",
    }
    payload = {"offers": prices}
    url = endpoint_url + f"campaigns/{campaign_id}/offer-prices/updates"
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    response_object = response.json()
    return response_object


def get_offer_ids(campaign_id, market_token):
    """Получает список всех артикулов товаров из кампании Яндекс Маркета.

    Функция автоматически обрабатывает пагинацию, запрашивая товары
    порциями по 200 штук, пока не будут получены все товары кампании.

    Args:
        campaign_id: Идентификатор кампании продавца на Яндекс Маркете.
        market_token: API-токен для авторизации.

    Returns:
        Список строк — артикулов (shopSku) всех товаров в кампании.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> get_offer_ids(12345, "token_xyz")
        ['sku_001', 'sku_002', 'sku_003']
    """
    page = ""
    product_list = []
    while True:
        some_prod = get_product_list(page, campaign_id, market_token)
        product_list.extend(some_prod.get("offerMappingEntries"))
        page = some_prod.get("paging").get("nextPageToken")
        if not page:
            break
    offer_ids = []
    for product in product_list:
        offer_ids.append(product.get("offer").get("shopSku"))
    return offer_ids


def create_stocks(watch_remnants, offer_ids, warehouse_id):
    """Создаёт список остатков для загрузки на Яндекс Маркет.

    Сопоставляет данные из файла поставщика с артикулами товаров на Яндекс Маркете.
    Товары с остатком ">10" получают значение 100, товары с остатком "1"
    получают 0 (означает "нет в наличии"). Товары, отсутствующие в файле
    поставщика, получают остаток 0. Добавляет временную метку UTC.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
                        Каждый словарь должен содержать ключи "Код" и "Количество".
        offer_ids: Список артикулов товаров, загруженных в кампанию.
        warehouse_id: Идентификатор склада на Яндекс Маркете.

    Returns:
        Список словарей с ключами "sku", "warehouseId", "items" (count, type, updatedAt).

    Raises:
        ValueError: Если значение "Количество" не является числом (кроме ">10" и "1").

    Examples:
        >>> watch_remnants = [{"Код": "123", "Количество": "5"}]
        >>> offer_ids = ["123", "456"]
        >>> create_stocks(watch_remnants, offer_ids, 12345)
        [{'sku': '123', 'warehouseId': 12345, 'items': [{'count': 5, 'type': 'FIT', 'updatedAt': '2024-01-01T12:00:00Z'}]}, {'sku': '456', 'warehouseId': 12345, 'items': [{'count': 0, 'type': 'FIT', 'updatedAt': '2024-01-01T12:00:00Z'}]}]
    """
    stocks = list()
    date = str(datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z")
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            count = str(watch.get("Количество"))
            if count == ">10":
                stock = 100
            elif count == "1":
                stock = 0
            else:
                stock = int(watch.get("Количество"))
            stocks.append(
                {
                    "sku": str(watch.get("Код")),
                    "warehouseId": warehouse_id,
                    "items": [
                        {
                            "count": stock,
                            "type": "FIT",
                            "updatedAt": date,
                        }
                    ],
                }
            )
            offer_ids.remove(str(watch.get("Код")))
    # Добавим недостающее из загруженного:
    for offer_id in offer_ids:
        stocks.append(
            {
                "sku": offer_id,
                "warehouseId": warehouse_id,
                "items": [
                    {
                        "count": 0,
                        "type": "FIT",
                        "updatedAt": date,
                    }
                ],
            }
        )
    return stocks


def create_prices(watch_remnants, offer_ids):
        """Создаёт список цен для загрузки на Яндекс Маркет.

    Сопоставляет данные из файла поставщика с артикулами товаров
    и формирует структуру данных, необходимую для API Яндекс Маркета.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
                        Каждый словарь должен содержать ключи "Код" и "Цена".
        offer_ids: Список артикулов товаров, загруженных в кампанию.

    Returns:
        Список словарей с ключами "id" и "price" (value, currencyId).

    Raises:
        KeyError: Если в словаре watch_remnants отсутствует ключ "Код" или "Цена".

    Examples:
        >>> watch_remnants = [{"Код": "123", "Цена": "5'990.00 руб."}]
        >>> offer_ids = ["123", "456"]
        >>> create_prices(watch_remnants, offer_ids)
        [{'id': '123', 'price': {'value': 5990, 'currencyId': 'RUR'}}]
    """
    prices = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            price = {
                "id": str(watch.get("Код")),
                # "feed": {"id": 0},
                "price": {
                    "value": int(price_conversion(watch.get("Цена"))),
                    # "discountBase": 0,
                    "currencyId": "RUR",
                    # "vat": 0,
                },
                # "marketSku": 0,
                # "shopSku": "string",
            }
            prices.append(price)
    return prices


async def upload_prices(watch_remnants, campaign_id, market_token):
    """Асинхронно загружает цены товаров на Яндекс Маркет пачками.

    Получает артикулы товаров из кампании, создаёт список цен
    и отправляет их на Яндекс Маркет порциями по 500 товаров.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
        campaign_id: Идентификатор кампании продавца на Яндекс Маркете.
        market_token: API-токен для авторизации.

    Returns:
        Список словарей с созданными ценами (такой же, как возвращает create_prices).

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса к API.

    Examples:
        >>> watch_remnants = [{"Код": "123", "Цена": "5990"}]
        >>> # Асинхронный вызов требует await:
        >>> # result = await upload_prices(watch_remnants, 12345, "token_xyz")
    """
    offer_ids = get_offer_ids(campaign_id, market_token)
    prices = create_prices(watch_remnants, offer_ids)
    for some_prices in list(divide(prices, 500)):
        update_price(some_prices, campaign_id, market_token)
    return prices


async def upload_stocks(watch_remnants, campaign_id, market_token, warehouse_id):
    """Асинхронно загружает остатки товаров на Яндекс Маркет пачками.

    Получает артикулы товаров из кампании, создаёт список остатков
    и отправляет их на Яндекс Маркет порциями по 2000 товаров.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
        campaign_id: Идентификатор кампании продавца на Яндекс Маркете.
        market_token: API-токен для авторизации.
        warehouse_id: Идентификатор склада на Яндекс Маркете.

    Returns:
        Кортеж из двух списков:
            - not_empty: Товары с ненулевыми остатками
            - stocks: Полный список всех созданных остатков

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса к API.

    Examples:
        >>> watch_remnants = [{"Код": "123", "Количество": "5"}]
        >>> # Асинхронный вызов требует await:
        >>> # not_empty, stocks = await upload_stocks(watch_remnants, 12345, "token_xyz", 12345)
    """
    offer_ids = get_offer_ids(campaign_id, market_token)
    stocks = create_stocks(watch_remnants, offer_ids, warehouse_id)
    for some_stock in list(divide(stocks, 2000)):
        update_stocks(some_stock, campaign_id, market_token)
    not_empty = list(
        filter(lambda stock: (stock.get("items")[0].get("count") != 0), stocks)
    )
    return not_empty, stocks


def main():
    """Основная функция запуска процесса обновления цен и остатков на Яндекс Маркете.

    Загружает переменные окружения (MARKET_TOKEN, FBS_ID, DBS_ID,
    WAREHOUSE_FBS_ID, WAREHOUSE_DBS_ID), скачивает актуальные остатки
    от поставщика, последовательно обновляет остатки и цены для
    FBS и DBS кампаний.

    Raises:
        requests.exceptions.ReadTimeout: При превышении времени ожидания ответа.
        requests.exceptions.ConnectionError: При проблемах с сетевым соединением.
        Exception: При любых других ошибках (выводит сообщение "ERROR_2").

    Examples:
        # Для запуска необходимо установить переменные окружения:
        # export MARKET_TOKEN="ваш_токен"
        # export FBS_ID="идентификатор_fbs"
        # export DBS_ID="идентификатор_dbs"
        # export WAREHOUSE_FBS_ID="склад_fbs"
        # export WAREHOUSE_DBS_ID="склад_dbs"
        #
        # Запуск скрипта:
        # python market.py
    """
    env = Env()
    market_token = env.str("MARKET_TOKEN")
    campaign_fbs_id = env.str("FBS_ID")
    campaign_dbs_id = env.str("DBS_ID")
    warehouse_fbs_id = env.str("WAREHOUSE_FBS_ID")
    warehouse_dbs_id = env.str("WAREHOUSE_DBS_ID")

    watch_remnants = download_stock()
    try:
        # FBS
        offer_ids = get_offer_ids(campaign_fbs_id, market_token)
        # Обновить остатки FBS
        stocks = create_stocks(watch_remnants, offer_ids, warehouse_fbs_id)
        for some_stock in list(divide(stocks, 2000)):
            update_stocks(some_stock, campaign_fbs_id, market_token)
        # Поменять цены FBS
        upload_prices(watch_remnants, campaign_fbs_id, market_token)

        # DBS
        offer_ids = get_offer_ids(campaign_dbs_id, market_token)
        # Обновить остатки DBS
        stocks = create_stocks(watch_remnants, offer_ids, warehouse_dbs_id)
        for some_stock in list(divide(stocks, 2000)):
            update_stocks(some_stock, campaign_dbs_id, market_token)
        # Поменять цены DBS
        upload_prices(watch_remnants, campaign_dbs_id, market_token)
    except requests.exceptions.ReadTimeout:
        print("Превышено время ожидания...")
    except requests.exceptions.ConnectionError as error:
        print(error, "Ошибка соединения")
    except Exception as error:
        print(error, "ERROR_2")


if __name__ == "__main__":
    main()
