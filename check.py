import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PAGE = os.environ.get('PAGE_URL') or 'https://sponsr.ru/marahovsky/'
SUBSCRIBE = os.environ.get('SUBSCRIBE_URL') or 'https://sponsr.ru/marahovsky/subscribe/'
MIN_PRICE = int(os.environ.get('MIN_PRICE') or 1100)
SPAM = int(os.environ.get('SPAM_COUNT') or 10)
TEST = (os.environ.get('TEST') or '').lower() == 'true'
PREV = (os.environ.get('PREV_CONCLUSION') or '').lower()
TOKEN = os.environ.get('TG_TOKEN', '')
CHAT = os.environ.get('TG_CHAT_ID', '')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def collect_levels(node, out):
    if isinstance(node, dict):
        if 'level_name' in node and 'level_price' in node:
            out.append(node)
            return out
        node = list(node.values())
    if isinstance(node, list):
        for x in node:
            collect_levels(x, out)
    return out


def price_of(level):
    try:
        return float(level.get('level_price') or 0)
    except (TypeError, ValueError):
        return 0


def parse(html):
    """Возвращает список уровней дороже MIN_PRICE в виде (имя, цена, занято, лимит, свободно)."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError('на странице нет __NEXT_DATA__, Sponsr поменял вёрстку или не пустил')
    seen, watched = set(), []
    for lvl in collect_levels(json.loads(m.group(1)), []):
        key = lvl.get('id') or lvl.get('level_name')
        if key in seen or price_of(lvl) < MIN_PRICE:
            continue
        seen.add(key)
        subs, limit = lvl.get('level_subscribers'), lvl.get('level_limit')
        open_ = lvl.get('level_status') == 'active' and lvl.get('level_visible') in (None, 'visible')
        free = open_ and (limit is None or (subs is not None and subs < limit))
        watched.append((lvl.get('level_name'), int(price_of(lvl)), subs, limit, free))
    if not watched:
        raise RuntimeError(f'не нашёл ни одного уровня от {MIN_PRICE} ₽')
    return sorted(watched, key=lambda w: w[1])


def send(text):
    if not TOKEN or not CHAT:
        print('TG_TOKEN или TG_CHAT_ID не заданы, сообщение не отправлено.', text)
        return
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': text,
                                   'disable_web_page_preview': 'true'}).encode()
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    for _ in range(3):
        try:
            urllib.request.urlopen(url, data=data, timeout=30).read()
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get('Retry-After') or 3))
                continue
            raise


def fail(reason):
    print('Ошибка.', reason)
    if TEST or PREV != 'failure':
        send(f'⚠️ Бот sponsr-watch не смог проверить места. {reason}\n'
             'Пока ошибка повторяется, больше писать не буду.')
    sys.exit(1)


def main():
    html, err = None, None
    for _ in range(3):
        try:
            html = fetch(PAGE)
            break
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5)
    if html is None:
        fail(f'Sponsr не открылся ({err}).')
    try:
        watched = parse(html)
    except Exception as e:  # noqa: BLE001
        fail(f'Не разобрал страницу ({e}).')

    for name, price, subs, limit, free in watched:
        print(f'{name} ({price} ₽): занято {subs} из {limit}, свободно={free}')

    if TEST:
        lines = ', '.join(f'{n} {s} из {l}' for n, _, s, l, _ in watched)
        send(f'Тест прошёл. Сейчас {lines}. Бот на посту.')

    free_levels = [w for w in watched if w[4]]
    if not free_levels:
        return
    for name, price, subs, limit, _ in free_levels:
        send(f'🚨 Освободилось место на уровне «{name}» за {price} ₽ в месяц, занято {subs} из {limit}.\n'
             f'Подписаться {SUBSCRIBE}')
        time.sleep(1.2)
    names = ', '.join(f'«{w[0]}»' for w in free_levels)
    for i in range(max(SPAM - len(free_levels), 0)):
        send(f'🚨 {i + len(free_levels) + 1}/{SPAM} Свободно место на {names}! {SUBSCRIBE}')
        time.sleep(1.2)


if __name__ == '__main__':
    main()
