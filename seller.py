import io
import logging.config
import os
import re
import zipfile
from environs import Env

import pandas as pd
import requests

logger = logging.getLogger(__file__)


def get_product_list(last_id, client_id, seller_token):
    """Получает список товаров из магазина Ozon.

    Args:
        last_id: Идентификатор последнего товара из предыдущего запроса
                 (для пагинации). Для первого запроса передаётся пустая строка.
        client_id: Идентификатор клиента (продавца) в системе Ozon.
        seller_token: API-ключ для авторизации продавца.

    Returns:
        Словарь с результатами запроса, содержащий список товаров,
        общее количество и last_id для следующего запроса.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> get_product_list("", "client_123", "token_xyz")
        {'items': [...], 'total': 150, 'last_id': 'abc123'}
    """
    url = "https://api-seller.ozon.ru/v2/product/list"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {
        "filter": {
            "visibility": "ALL",
        },
        "last_id": last_id,
        "limit": 1000,
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    response_object = response.json()
    return response_object.get("result")


def get_offer_ids(client_id, seller_token):
    """Получает список всех артикулов товаров из магазина Ozon.

    Функция автоматически обрабатывает пагинацию, запрашивая товары
    порциями по 1000 штук, пока не будут получены все товары магазина.

    Args:
        client_id: Идентификатор клиента (продавца) в системе Ozon.
        seller_token: API-ключ для авторизации продавца.

    Returns:
        Список строк — артикулов (offer_id) всех товаров в магазине.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> get_offer_ids("client_123", "token_xyz")
        ['1001', '1002', '1003', '1004']
    """
    last_id = ""
    product_list = []
    while True:
        some_prod = get_product_list(last_id, client_id, seller_token)
        product_list.extend(some_prod.get("items"))
        total = some_prod.get("total")
        last_id = some_prod.get("last_id")
        if total == len(product_list):
            break
    offer_ids = []
    for product in product_list:
        offer_ids.append(product.get("offer_id"))
    return offer_ids


def update_price(prices: list, client_id, seller_token):
    """Обновляет цены товаров на Ozon.

    Отправляет список с новыми ценами в API Ozon.
    За один запрос можно обновить до 1000 товаров.

    Args:
        prices: Список словарей с ценами товаров. Каждый словарь должен
                содержать offer_id и price.
        client_id: Идентификатор клиента (продавца) в системе Ozon.
        seller_token: API-ключ для авторизации продавца.

    Returns:
        Словарь с ответом API Ozon, содержащий результаты обновления цен.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> prices = [{"offer_id": "123", "price": "5990"}]
        >>> update_price(prices, "client_123", "token_xyz")
        {'result': [{'offer_id': '123', 'updated': True}]}
    """
    url = "https://api-seller.ozon.ru/v1/product/import/prices"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"prices": prices}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def update_stocks(stocks: list, client_id, seller_token):
    """Обновляет остатки товаров на Ozon.

    Отправляет список с новыми остатками в API Ozon.
    За один запрос можно обновить до 100 товаров.

    Args:
        stocks: Список словарей с остатками товаров. Каждый словарь должен
                содержать offer_id и stock.
        client_id: Идентификатор клиента (продавца) в системе Ozon.
        seller_token: API-ключ для авторизации продавца.

    Returns:
        Словарь с ответом API Ozon, содержащий результаты обновления остатков.

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса.

    Examples:
        >>> stocks = [{"offer_id": "123", "stock": 10}]
        >>> update_stocks(stocks, "client_123", "token_xyz")
        {'result': [{'offer_id': '123', 'updated': True}]}
    """
    url = "https://api-seller.ozon.ru/v1/product/import/stocks"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"stocks": stocks}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def download_stock():
    """Скачивает и обрабатывает файл с остатками от поставщика.

    Скачивает ZIP-архив с сайта timeworld.ru, извлекает из него
    Excel-файл, читает данные, начиная с 17-й строки, и преобразует
    их в список словарей. После обработки временный Excel-файл удаляется.

    Returns:
        Список словарей, где каждый словарь соответствует одной строке
        из файла остатков. Ключи словарей — названия столбцов Excel.

    Raises:
        requests.exceptions.RequestException: При ошибках скачивания файла.
        FileNotFoundError: Если файл ostatki.xls не найден после распаковки.

    Examples:
        >>> remnants = download_stock()
        >>> remnants[0]
        {'Код': '12345', 'Количество': '5', 'Цена': '5\'990.00 руб.'}
    """
    # Скачать остатки с сайта
    casio_url = "https://timeworld.ru/upload/files/ostatki.zip"
    session = requests.Session()
    response = session.get(casio_url)
    response.raise_for_status()
    with response, zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(".")
    # Создаем список остатков часов:
    excel_file = "ostatki.xls"
    watch_remnants = pd.read_excel(
        io=excel_file,
        na_values=None,
        keep_default_na=False,
        header=17,
    ).to_dict(orient="records")
    os.remove("./ostatki.xls")  # Удалить файл
    return watch_remnants


def create_stocks(watch_remnants, offer_ids):
    """Создаёт список остатков для загрузки на Ozon.

    Сопоставляет данные из файла поставщика с артикулами товаров на Ozon.
    Товары с остатком ">10" получают значение 100, товары с остатком "1"
    получают 0 (означает "нет в наличии"). Товары, отсутствующие в файле
    поставщика, получают остаток 0.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
                        Каждый словарь должен содержать ключи "Код" и "Количество".
        offer_ids: Список артикулов товаров, загруженных в магазин Ozon.

    Returns:
        Список словарей с ключами "offer_id" и "stock" для загрузки в API Ozon.

    Raises:
        ValueError: Если значение "Количество" не является числом (кроме ">10" и "1").

    Examples:
        >>> watch_remnants = [{"Код": "123", "Количество": "5"}, {"Код": "456", "Количество": ">10"}]
        >>> offer_ids = ["123", "456", "789"]
        >>> create_stocks(watch_remnants, offer_ids)
        [{'offer_id': '123', 'stock': 5}, {'offer_id': '456', 'stock': 100}, {'offer_id': '789', 'stock': 0}]
    """
    stocks = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            count = str(watch.get("Количество"))
            if count == ">10":
                stock = 100
            elif count == "1":
                stock = 0
            else:
                stock = int(watch.get("Количество"))
            stocks.append({"offer_id": str(watch.get("Код")), "stock": stock})
            offer_ids.remove(str(watch.get("Код")))
    # Добавим недостающее из загруженного:
    for offer_id in offer_ids:
        stocks.append({"offer_id": offer_id, "stock": 0})
    return stocks


def create_prices(watch_remnants, offer_ids):
    """Создаёт список цен для загрузки на Ozon.

    Сопоставляет данные из файла поставщика с артикулами товаров на Ozon
    и формирует структуру данных, необходимую для API Ozon.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
                        Каждый словарь должен содержать ключи "Код" и "Цена".
        offer_ids: Список артикулов товаров, загруженных в магазин Ozon.

    Returns:
        Список словарей с ключами "auto_action_enabled", "currency_code",
        "offer_id", "old_price", "price" для загрузки в API Ozon.

    Raises:
        KeyError: Если в словаре watch_remnants отсутствует ключ "Код" или "Цена".
        AttributeError: Если price_conversion получает некорректный аргумент.

    Examples:
        >>> watch_remnants = [{"Код": "123", "Цена": "5'990.00 руб."}]
        >>> offer_ids = ["123", "456"]
        >>> create_prices(watch_remnants, offer_ids)
        [{'auto_action_enabled': 'UNKNOWN', 'currency_code': 'RUB', 'offer_id': '123', 'old_price': '0', 'price': '5990'}]
    """
    prices = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            price = {
                "auto_action_enabled": "UNKNOWN",
                "currency_code": "RUB",
                "offer_id": str(watch.get("Код")),
                "old_price": "0",
                "price": price_conversion(watch.get("Цена")),
            }
            prices.append(price)
    return prices


def price_conversion(price: str) -> str:
      """Преобразует цену из формата поставщика в числовой формат Ozon.

    Функция удаляет из строки цены все символы, кроме цифр,
    отбрасывая дробную часть и валюту. Например, цену вида "5'990.00 руб."
    превращает в "5990".

    Args:
        price: Строка с ценой в формате поставщика, обычно содержащая
               цифры, разделители тысяч ('), дробную часть и название валюты.

    Returns:
        Строка, содержащая только цифры из целой части цены.

    Raises:
        AttributeError: Если аргумент price не является строкой.
        AttributeError: Если в строке нет ни одной цифры (функция вернёт пустую строку).

    Examples:
        >>> price_conversion("5'990.00 руб.")
        '5990'
        >>> price_conversion("12'500.50 руб.")
        '12500'
        >>> price_conversion("1000")
        '1000'
    """
    return re.sub("[^0-9]", "", price.split(".")[0])


def divide(lst: list, n: int):
    """Разделяет список на части заданного размера.

    Args:
        lst: Исходный список для разделения.
        n: Размер каждой части (количество элементов).

    Yields:
        Список из n элементов (последняя часть может быть короче).

    Raises:
        TypeError: Если lst не является списком или n не является целым числом.
        ValueError: Если n меньше или равно нулю.

    Examples:
        >>> list(divide([1, 2, 3, 4, 5], 2))
        [[1, 2], [3, 4], [5]]
        >>> list(divide([1, 2, 3], 5))
        [[1, 2, 3]]
    """
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


async def upload_prices(watch_remnants, client_id, seller_token):
    """Асинхронно загружает цены товаров на Ozon пачками.

    Получает артикулы товаров из магазина, создаёт список цен
    и отправляет их на Ozon порциями по 1000 товаров.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
        client_id: Идентификатор клиента (продавца) в системе Ozon.
        seller_token: API-ключ для авторизации продавца.

    Returns:
        Список словарей с созданными ценами (такой же, как возвращает create_prices).

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса к API Ozon.

    Examples:
        >>> watch_remnants = [{"Код": "123", "Цена": "5990"}]
        >>> # Асинхронный вызов требует await:
        >>> # result = await upload_prices(watch_remnants, "client_123", "token_xyz")
    """
    offer_ids = get_offer_ids(client_id, seller_token)
    prices = create_prices(watch_remnants, offer_ids)
    for some_price in list(divide(prices, 1000)):
        update_price(some_price, client_id, seller_token)
    return prices


async def upload_stocks(watch_remnants, client_id, seller_token):
    """Асинхронно загружает остатки товаров на Ozon пачками.

    Получает артикулы товаров из магазина, создаёт список остатков
    и отправляет их на Ozon порциями по 100 товаров.

    Args:
        watch_remnants: Список словарей с данными из файла поставщика.
        client_id: Идентификатор клиента (продавца) в системе Ozon.
        seller_token: API-ключ для авторизации продавца.

    Returns:
        Кортеж из двух списков:
            - not_empty: Товары с ненулевыми остатками
            - stocks: Полный список всех созданных остатков

    Raises:
        requests.exceptions.RequestException: При ошибках HTTP-запроса к API Ozon.

    Examples:
        >>> watch_remnants = [{"Код": "123", "Количество": "5"}]
        >>> # Асинхронный вызов требует await:
        >>> # not_empty, stocks = await upload_stocks(watch_remnants, "client_123", "token_xyz")
        >>> # print(not_empty)  # [{'offer_id': '123', 'stock': 5}]
    """
    offer_ids = get_offer_ids(client_id, seller_token)
    stocks = create_stocks(watch_remnants, offer_ids)
    for some_stock in list(divide(stocks, 100)):
        update_stocks(some_stock, client_id, seller_token)
    not_empty = list(filter(lambda stock: (stock.get("stock") != 0), stocks))
    return not_empty, stocks


def main():
    """Основная функция запуска процесса обновления цен и остатков.

    Загружает переменные окружения (SELLER_TOKEN, CLIENT_ID),
    получает список артикулов товаров из магазина Ozon,
    скачивает актуальные остатки от поставщика,
    обновляет остатки (пачками по 100 товаров) и цены (пачками по 900 товаров).

    Raises:
        requests.exceptions.ReadTimeout: При превышении времени ожидания ответа.
        requests.exceptions.ConnectionError: При проблемах с сетевым соединением.
        Exception: При любых других ошибках (выводит сообщение "ERROR_2").

    Examples:
        # Для запуска необходимо установить переменные окружения:
        # export SELLER_TOKEN="ваш_токен"
        # export CLIENT_ID="ваш_client_id"
        #
        # Запуск скрипта:
        # python script.py
    """
    env = Env()
    seller_token = env.str("SELLER_TOKEN")
    client_id = env.str("CLIENT_ID")
    try:
        offer_ids = get_offer_ids(client_id, seller_token)
        watch_remnants = download_stock()
        # Обновить остатки
        stocks = create_stocks(watch_remnants, offer_ids)
        for some_stock in list(divide(stocks, 100)):
            update_stocks(some_stock, client_id, seller_token)
        # Поменять цены
        prices = create_prices(watch_remnants, offer_ids)
        for some_price in list(divide(prices, 900)):
            update_price(some_price, client_id, seller_token)
    except requests.exceptions.ReadTimeout:
        print("Превышено время ожидания...")
    except requests.exceptions.ConnectionError as error:
        print(error, "Ошибка соединения")
    except Exception as error:
        print(error, "ERROR_2")


if __name__ == "__main__":
    main()
