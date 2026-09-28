import json
import os
import requests

PART_NUMBER = "MJXW4ZA/A"

APPLE_URL = "https://www.apple.com/hk/shop/retail/pickup-message"

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

STORES = {
    "R409": "Canton Road",
    "R428": "ifc mall",
    "R485": "Causeway Bay",
    "R499": "Festival Walk",
    "R610": "New Town Plaza",
    "R673": "apm Hong Kong",
}

STATE_FILE = "stock_state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.apple.com/hk/",
}


def load_previous_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_ntfy(message):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"

    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": "🍎 Apple 香港库存提醒",
            "Priority": "urgent",
            "Tags": "apple,iphone",
            "Click": (
                "https://www.apple.com/hk/shop/buy-iphone/"
                "iphone-18-pro/6.9-inch-display-512gb-glacier"
            ),
        },
        timeout=20,
    )

    response.raise_for_status()


def main():
    params = {
        "pl": "true",
        "mts.0": "regular",
        "parts.0": PART_NUMBER,
    }

    response = requests.get(
        APPLE_URL,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    stores = data.get("body", {}).get("stores", [])

    if not stores:
        raise RuntimeError(
            "Apple API 没有返回门店数据，不能判断库存。"
        )

    previous = load_previous_state()
    current = {}

    for store in stores:
        store_number = store.get("storeNumber")

        if store_number not in STORES:
            continue

        parts = store.get("partsAvailability", {})
        product = parts.get(PART_NUMBER, {})

        status = product.get("pickupDisplay", "unknown")

        current[store_number] = status == "available"

    if not current:
        raise RuntimeError(
            "没有找到目标香港 Apple Store。"
        )

    newly_available = []

    for store_number, is_available in current.items():
        was_available = previous.get(store_number, False)

        if is_available and not was_available:
            newly_available.append(
                STORES[store_number]
            )

    if newly_available:
        message = (
            "🚨 Apple 香港门店发现库存！\n\n"
            "iPhone 18 Pro Max\n"
            "❄️ Glacier 冰川色\n"
            "💾 512GB\n\n"
            "有货门店：\n"
            + "\n".join(
                f"• {store}" for store in newly_available
            )
            + "\n\n"
            "请立即打开 Apple 官方页面确认并下单：\n"
            "https://www.apple.com/hk/shop/buy-iphone/"
            "iphone-18-pro/6.9-inch-display-512gb-glacier"
        )

        send_ntfy(message)

    save_state(current)

    print("Apple HK inventory:")

    for store_number, is_available in current.items():
        print(
            STORES[store_number],
            "AVAILABLE" if is_available else "unavailable"
        )


if __name__ == "__main__":
    main()
