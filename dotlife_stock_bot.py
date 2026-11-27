#!/usr/bin/env python3
"""
Dotlife stock bot: เช็คสต็อคสินค้า Sony Gaming Console บน dotlife.store
แล้วแจ้งเตือนเมื่อสินค้ากลับมามีของ (OUT_OF_STOCK -> IN_STOCK หรือมีสินค้าใหม่ที่พร้อมขาย)

ติดตั้ง:   pip install requests
รันครั้งเดียว:       python dotlife_stock_bot.py
รันวนทุก 10 นาที:    python dotlife_stock_bot.py --loop 600
กรองชื่อสินค้า:      python dotlife_stock_bot.py --watch "ps5,playstation 5"
ทดสอบแจ้งเตือน:      python dotlife_stock_bot.py --test-notify

แจ้งเตือน (ตั้งตัวแปรสภาพแวดล้อมอย่างใดอย่างหนึ่งหรือทั้งสอง):
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
  DISCORD_WEBHOOK
ถ้าไม่ตั้งอะไรเลย จะพิมพ์ผลลัพธ์ในหน้าจอเท่านั้น
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

# URL ที่ copy มาจาก DevTools (query + variables ถูกแกะออกมาใช้ซ้ำอัตโนมัติ)
RAW_URL = (
    "https://apim.istudio.store/graphql?query=query+GetCategories%28%24id%3AString%21%24pageSize%3AInt%21%24currentPage%3AInt%21%24filters%3AProductAttributeFilterInput%21%24sort%3AProductAttributeSortInput%29%7BcategoryList%28filters%3A%7Bcategory_uid%3A%7Bin%3A%5B%24id%5D%7D%7D%29%7Buid+id+name+description+display_mode+image+canonical_url+cms_block%7Bidentifier+content+__typename%7Dseo_content+hreflang%7Bcode+href+__typename%7DsocialMarkup%7BopenGraph%7Bproperty+content+__typename%7DtwitterCard%7Bname+content+__typename%7D__typename%7DschemaOrg%7BschemaType+script+__typename%7D...CategoryFragment+__typename%7Dproducts%28pageSize%3A%24pageSize+currentPage%3A%24currentPage+filter%3A%24filters+sort%3A%24sort%29%7B...ProductsFragment+__typename%7D%7Dfragment+CategoryFragment+on+CategoryTree%7Buid+meta_title+meta_keywords+meta_description+__typename%7Dfragment+ProductsFragment+on+Products%7Bitems%7B...ProductGalleryItemFragment+__typename%7Dpage_info%7Btotal_pages+__typename%7Dtotal_count+__typename%7Dfragment+ProductGalleryItemFragment+on+ProductInterface%7Bid+uid+name+price_range%7Bminimum_price%7Bregular_price%7Bcurrency+value+__typename%7Dfinal_price%7Bcurrency+value+__typename%7D__typename%7D__typename%7Dsku+small_image%7Burl+__typename%7Dbrand+brand_name+only_x_left_in_stock+stock_status+rating_summary+__typename+url_key+price_tiers%7Bfinal_price%7Bcurrency+value+__typename%7D__typename%7Dprogram_info%7Blabel+logo+price%7BminimalPrice%7Bamount%7Bcurrency+value+__typename%7D__typename%7DmaximalPrice%7Bamount%7Bcurrency+value+__typename%7D__typename%7DregularPrice%7Bamount%7Bcurrency+value+__typename%7D__typename%7D__typename%7D__typename%7D...on+ConfigurableProduct%7Bconfigurable_options%7Battribute_code+attribute_id+uid+label+values%7Buid+swatch_data%7Bvalue+__typename%7D__typename%7D__typename%7Dvariants%7Battributes%7Bcode+value_index+__typename%7Dproduct%7Buid+sku+name+stock_status+small_image%7Burl+__typename%7Durl_key+brand+brand_name+only_x_left_in_stock+categories%7Buid+name+__typename%7Dprice_tiers%7Bfinal_price%7Bcurrency+value+__typename%7D__typename%7Dprogram_info%7Blabel+logo+price%7BminimalPrice%7Bamount%7Bcurrency+value+__typename%7D__typename%7DmaximalPrice%7Bamount%7Bcurrency+value+__typename%7D__typename%7DregularPrice%7Bamount%7Bcurrency+value+__typename%7D__typename%7D__typename%7D__typename%7D__typename%7D__typename%7D__typename%7D%7D"
    "&operationName=GetCategories&variables=%7B%22currentPage%22%3A1%2C%22id%22%3A%22MTY5NQ%3D%3D%22%2C%22filters%22%3A%7B%22brand%22%3A%7B%22eq%22%3A%22481%22%7D%2C%22category_uid%22%3A%7B%22eq%22%3A%22MTY5NQ%3D%3D%22%7D%7D%2C%22pageSize%22%3A40%7D"
)

SITE = "https://www.dotlife.store"
STATE_FILE = Path(__file__).with_name("stock_state.json")
MIN_INTERVAL = 300  # วินาที: ไม่ให้เช็คถี่เกินไป

HEADERS = {
    "accept": "*/*",
    "accept-language": "th,en-US;q=0.9,en;q=0.8",
    "content-type": "application/json",
    "origin": SITE,
    "referer": SITE + "/",
    "store": "dth",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36"
    ),
}

_u = urlparse(RAW_URL)
API = f"{_u.scheme}://{_u.netloc}{_u.path}"
_qs = parse_qs(_u.query)
QUERY = _qs["query"][0]
OPERATION = _qs["operationName"][0]
BASE_VARS = json.loads(_qs["variables"][0])


def fetch_page(page: int) -> dict:
    variables = {**BASE_VARS, "currentPage": page}
    r = requests.get(
        API,
        params={
            "query": QUERY,
            "operationName": OPERATION,
            "variables": json.dumps(variables, separators=(",", ":")),
        },
        headers=HEADERS,
        timeout=30,
    )
    if r.status_code in (403, 429):
        raise RuntimeError(
            f"HTTP {r.status_code}: ถูกบล็อก/จำกัดความถี่ ลองเว้นระยะให้ห่างขึ้น หรือเปลี่ยนไปใช้ Playwright"
        )
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]["products"]


def price_of(item: dict):
    try:
        return item["price_range"]["minimum_price"]["final_price"]["value"]
    except (KeyError, TypeError):
        return None


def fetch_all() -> dict:
    """คืน dict: sku -> {name, status, price, left, url}"""
    result = {}
    page = 1
    while True:
        products = fetch_page(page)
        for it in products["items"]:
            price = price_of(it)
            variants = it.get("variants") or []
            if variants:  # สินค้าแบบมีตัวเลือก (สี/รุ่นย่อย) เช็คแยกตามตัวเลือก
                for v in variants:
                    p = v["product"]
                    key = p.get("url_key") or it.get("url_key")
                    result[p["sku"]] = {
                        "name": p["name"],
                        "status": p["stock_status"],
                        "price": price,
                        "left": p.get("only_x_left_in_stock"),
                        "url": f"{SITE}/{key}.html",
                    }
            else:
                result[it["sku"]] = {
                    "name": it["name"],
                    "status": it["stock_status"],
                    "price": price,
                    "left": it.get("only_x_left_in_stock"),
                    "url": f"{SITE}/{it.get('url_key')}.html",
                }
        if page >= products["page_info"]["total_pages"]:
            break
        page += 1
        time.sleep(1)
    return result


def notify(text: str) -> bool:
    """ส่งแจ้งเตือน คืน True ถ้าไม่มีช่องทางใดล้มเหลว"""
    print(text)
    ok = True
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text[:4000]},
                timeout=15,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"[telegram error] {e}", file=sys.stderr)
            ok = False
    hook = os.getenv("DISCORD_WEBHOOK")
    if hook:
        try:
            r = requests.post(hook, json={"content": text[:1900]}, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"[discord error] {e}", file=sys.stderr)
            ok = False
    return ok


def fmt(v: dict) -> str:
    line = f"🟢 {v['name']}"
    if v["price"] is not None:
        line += f"\nราคา ฿{v['price']:,.0f}"
    if v.get("left"):
        line += f" (เหลือ {v['left']})"
    return line + f"\n{v['url']}"


def run_once(watch: list) -> None:
    current = fetch_all()
    if watch:
        current = {
            k: v for k, v in current.items() if any(w in v["name"].lower() for w in watch)
        }

    first_run = not STATE_FILE.exists()
    prev = {} if first_run else json.loads(STATE_FILE.read_text())

    in_stock = [v for v in current.values() if v["status"] == "IN_STOCK"]
    print(f"[{time.strftime('%H:%M:%S')}] ตรวจ {len(current)} รายการ, มีของ {len(in_stock)}")

    if first_run:
        print("รันครั้งแรก: บันทึกสถานะตั้งต้นไว้ (ยังไม่แจ้งเตือน)")
        for v in in_stock:
            print("  มีของอยู่แล้ว:", v["name"])
    else:
        restocked = [
            v
            for sku, v in current.items()
            if v["status"] == "IN_STOCK" and prev.get(sku, {}).get("status") != "IN_STOCK"
        ]
        if restocked:
            msg = "🎮 Dotlife มีของแล้ว!\n\n" + "\n\n".join(fmt(v) for v in restocked)
            if not notify(msg):
                print("แจ้งเตือนไม่สำเร็จ จะลองใหม่รอบหน้า", file=sys.stderr)
                return  # ไม่บันทึกสถานะ เพื่อให้รอบหน้าแจ้งซ้ำ

    STATE_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="วนทุก N วินาที (ขั้นต่ำ 300)")
    ap.add_argument("--watch", default="", help="คำในชื่อสินค้า คั่นด้วยคอมมา เช่น ps5,playstation 5")
    ap.add_argument("--test-notify", action="store_true", help="ส่งข้อความทดสอบแล้วจบ")
    args = ap.parse_args()

    if args.test_notify:
        notify("✅ ทดสอบแจ้งเตือนจาก Dotlife stock bot")
        return

    watch = [w.strip().lower() for w in args.watch.split(",") if w.strip()]

    if not args.loop:
        run_once(watch)
        return

    interval = max(args.loop, MIN_INTERVAL)
    while True:
        try:
            run_once(watch)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
        time.sleep(interval + random.uniform(0, 30))


if __name__ == "__main__":
    main()