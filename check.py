"""Следит за свободными местами на уровне подписки Sponsr и шлёт уведомления в Telegram."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PAGE = os.environ.get('PAGE_URL', 'https://sponsr.ru/marahovsky/')
SUBSCRIBE = os.environ.get('SUBSCRIBE_URL', 'https://sponsr.ru/marahovsky/subscribe/')
LEVEL = os.environ.get('LEVEL_NAME', 'Собеседник вечности')
SPAM = int(os.environ.get('SPAM_COUNT') or 10)
TEST = (os.environ.get('TEST') or '').lower() == 'true'
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


def find_level(node):
    if isinstance(node, dict):
        if node.get('level_name') == LEVEL and 'level_subscribers' in node:
            return node
        node = list(node.values())
    if isinstance(node, list):
        for x in node:
            found = find_level(x)
            if found:
                return found
    return None


def parse(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError('на странице нет __NEXT_DATA__, Sponsr поменял вёрстку или отдал заглушку')
    level = find_level(json.loads(m.group(1)))
    if not level:
        raise RuntimeError(f'уровень «{LEVEL}» не найден на странице')
    subs, limit = level.get('level_subscribers'), level.get('level_limit')
    free = level.get('level_status') == 'active' and (limit is None or (subs is not None and subs < limit))
    return subs, limit, free


def send(text):
    if not TOKEN or not CHAT:
        print('TG_TOKEN или TG_CHAT_ID не заданы, сообщение не отправлено:', text)
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


def main():
    html, err = None, None
    for attempt in range(3):
        try:
            html = fetch(PAGE)
            break
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5)
    try:
        if html is None:
            raise RuntimeError(f'Sponsr не открылся: {err}')
        subs, limit, free = parse(html)
    except Exception as e:  # noqa: BLE001
        if TEST:
            send(f'Тест не прошёл. {e}')
        sys.exit(str(e))

    print(f'{LEVEL}: занято {subs} из {limit}, свободно={free}')
    if TEST:
        send(f'Тест прошёл. «{LEVEL}» сейчас занято {subs} из {limit}. Бот на посту.')
    if free:
        text = (f'🚨 Освободилось место на уровне «{LEVEL}»! Занято {subs} из {limit}.\n'
                f'Подписаться: {SUBSCRIBE}')
        for i in range(SPAM):
            send(text if i == 0 else f'🚨 {i + 1}/{SPAM} Место на «{LEVEL}» свободно! {SUBSCRIBE}')
            time.sleep(1.2)


if __name__ == '__main__':
    main()
