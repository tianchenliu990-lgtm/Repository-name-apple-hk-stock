import json
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============ 配置区 ============
PART_NUMBER = "MJXW4ZA/A"

APPLE_URL = "https://www.apple.com/hk/shop/retail/pickup-message"

PRODUCT_URL = (
    "https://www.apple.com/hk/shop/buy-iphone/"
    "iphone-18-pro/6.9-inch-display-512gb-glacier"
)

STORES = {
    "R409": "Canton Road",
    "R428": "ifc mall",
    "R485": "Causeway Bay",
    "R499": "Festival Walk",
    "R610": "New Town Plaza",
    "R673": "apm Hong Kong",
}

# ============ 环境变量 ============
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
APPLE_COOKIE = os.environ.get("APPLE_COOKIE", "")

if not NTFY_TOPIC:
    raise SystemExit("❌ 未设置 NTFY_TOPIC")

# ============ Headers ============
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.apple.com/hk/",
    "Cookie": APPLE_COOKIE,
}


# ============ 带重试的 session ============
def build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ============ ntfy 推送 ============
def send_ntfy(message):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"

    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": "🍎 Apple 香港库存提醒",
            "Priority": "urgent",
            "Tags": "apple,iphone",
            "Click": PRODUCT_URL,
        },
        timeout=20,
    )
    response.raise_for_status()
    print(f"✅ ntfy 推送成功：{response.status_code}")


# ============ 主逻辑 ============
def main():
    session = build_session()

    params = {
        "pl": "true",
        "mts.0": "regular",
        "parts.0": PART_NUMBER,
    }

    print(f"🔍 查询 SKU：{PART_NUMBER}")
    print(f"🍪 Cookie 长度：{len(APPLE_COOKIE)}")

    response = session.get(
        APPLE_URL,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    print(f"📡 HTTP 状态码：{response.status_code}")

    if response.status_code != 200:
        print(f"❌ 响应内容前 500 字：{response.text[:500]}")
        raise SystemExit(1)

    try:
        data = response.json()
    except Exception as e:
        print(f"❌ JSON 解析失败：{e}")
        print(f"响应前 500 字：{response.text[:500]}")
        raise SystemExit(1)

    body = data.get("body", {})
    stores = body.get("stores", [])

    print(f"🏬 返回门店数：{len(stores)}")

    if not stores:
        print("⚠️ Apple API 未返回门店数据。可能原因：")
        print("   1. Cookie 已过期")
        print("   2. SKU 已下架或错误")
        print("   3. 请求被风控拦截")
        print(f"   完整响应前 800 字：{json.dumps(data, ensure_ascii=False)[:800]}")
        raise SystemExit(1)

    available_stores = []

    for store in stores:
        store_number = store.get("storeNumber")
        if store_number not in STORES:
            continue

        parts = store.get("partsAvailability", {})
        product = parts.get(PART_NUMBER, {})
        status = product.get("pickupDisplay", "unknown")

        print(f"   • {STORES[store_number]} ({store_number}) → {status}")

        if status == "available":
            available_stores.append(STORES[store_number])

    if available_stores:
        message = (
            "🚨 Apple 香港门店发现库存！\n\n"
            "iPhone 18 Pro Max\n"
            "❄️ Glacier 冰川色\n"
            "💾 512GB\n\n"
            "有货门店：\n"
            + "\n".join(f"• {s}" for s in available_stores)
            + "\n\n"
            "请立即打开 Apple 官方页面确认并下单：\n"
            + PRODUCT_URL
        )
        try:
            send_ntfy(message)
        except Exception as e:
            print(f"❌ ntfy 推送失败：{e}")
    else:
        print("🟢 暂无库存，不推送")

    print("\n📊 当前库存汇总：")
    for store in stores:
        store_number = store.get("storeNumber")
        if store_number not in STORES:
            continue
        parts = store.get("partsAvailability", {})
        product = parts.get(PART_NUMBER, {})
        status = product.get("pickupDisplay", "unknown")
        print(
            f"   {STORES[store_number]}: "
            + ("✅ AVAILABLE" if status == "available" else f"❌ {status}")
        )


if __name__ == "__main__":
    time.sleep(int(os.environ.get("START_DELAY", "0")))
    main()
