import requests
import json
import time

while True:
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': 'GME',
        'interval': '5min',
        'apikey': 'F6IB6RPAUW71252F'
    }
    url = 'https://www.alphavantage.co/query'
    r = requests.get(url, params)

    print(r.url)

    raw_data = json.loads(r.text)

    d = raw_data.get('Time Series (5min)', {})

    prev_close = None
    open_price = None
    current_price = None
    max_price = None
    min_price = None

    date = None


    for ts, data in d.items():
        curr_open = float(data.get('1. open'))
        curr_high = float(data.get('2. high'))
        curr_low = float(data.get('3. low'))
        curr_close = float(data.get('4. close'))
        ts = ts.split(' ')
        date = ts[0] if date is None else date


        if date == ts[0]:
            open_price = curr_open if curr_open is not None else open_price
            prev_close = curr_close if current_price is not None and prev_close is None else prev_close
            current_price = curr_close if current_price is None else current_price

            max_price = curr_high if max_price is None or curr_high > max_price else max_price
            min_price = curr_low if min_price is None or curr_low < min_price else min_price



    price_range = max_price-min_price

    open_point = round(9 * (open_price-min_price)/price_range)

    curent_point = round(9 * (current_price-min_price)/price_range)

    prev_close_point = round(9 * (prev_close-min_price)/price_range)



    leds = []

    for index in range(0,10):
        led = (0, 0, 0)
        if index == open_point:
            led = (128, 128, 128)
        elif index == curent_point and current_price >= prev_close:
            led = (0, 168, 42)
        elif index == curent_point and current_price < prev_close:
            led = (194, 10, 0)
        elif curent_point > index >= prev_close_point:
            led = (0, 168, 0)
        elif prev_close_point >= index > curent_point:
            led = (100, 0, 0)
        elif curent_point > index >= open_point:
            led = (0, 5, 0)
        elif open_point >= index > curent_point:
            led = (5, 0, 0)
        leds.append(led)


    led_params = {
        'cmd': 'set_pixel',
        'pixel': f'{",".join([str(index) for index, _ in enumerate(leds)])}]',
        'r':  f'{",".join([str(x[0]) for x in leds])}',
        'g': f'{",".join([str(x[1]) for x in leds])}',
        'b': f'{",".join([str(x[2]) for x in leds])}'
    }

    r = requests.get('http://192.168.1.10', params=led_params)
    print(r.url)
    time.sleep(60*5)
