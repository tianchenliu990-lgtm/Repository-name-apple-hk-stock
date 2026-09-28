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


def load_state():
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
    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
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


def check_store(store_number):
    params = {
        "pl": "true",
        "mts.0": "regular",
        "parts.0": PART_NUMBER,
        "store": store_number,
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

    for store in stores:
        if store.get("storeNumber") != store_number:
            continue

        availability = store.get("partsAvailability", {})
        product = availability.get(PART_NUMBER, {})

        return product.get("pickupDisplay") == "available"

    return False


def main():
    previous = load_state()
    current = {}

    print("Checking Apple Hong Kong stock...")

    for store_number, store_name in STORES.items():
        try:
            available = check_store(store_number)
            current[store_number] = available

            print(
                f"{store_name}: "
                f"{'AVAILABLE' if available else 'unavailable'}"
            )

        except Exception as e:
            print(f"{store_name}: ERROR - {e}")

    if not current:
        raise RuntimeError("没有成功检查任何香港 Apple Store。")

    newly_available = []

    for store_number, available in current.items():
        if available and not previous.get(store_number, False):
            newly_available.append(STORES[store_number])

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
            "立即打开 Apple 官方页面确认：\n"
            "https://www.apple.com/hk/shop/buy-iphone/"
            "iphone-18-pro/6.9-inch-display-512gb-glacier"
        )

        send_ntfy(message)

        print("NTFY notification sent!")

    save_state(current)

    print("Stock check completed.")


if __name__ == "__main__":
    main()
