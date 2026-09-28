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
            "Title": "🍎 Apple 香港库存监控测试",
            "Priority": "urgent",
            "Tags": "apple,iphone,test",
        },
        timeout=20,
    )

    response.raise_for_status()

    print("NTFY notification sent successfully!")


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

    if not stores:
        raise RuntimeError("Apple 没有返回门店数据")

    for store in stores:
        if store.get("storeNumber") != store_number:
            continue

        availability = store.get("partsAvailability", {})
        product = availability.get(PART_NUMBER, {})

        status = product.get("pickupDisplay")

        if status == "available":
            return True

        if status in ("unavailable", "ineligible"):
            return False

        raise RuntimeError(f"未知库存状态: {status}")

    raise RuntimeError(f"Apple 没有返回门店 {store_number}")


def main():

    # ==============================
    # 测试 ntfy 推送
    # ==============================

    print("Sending test notification...")

    send_ntfy(
        "🔔 Apple 香港库存监控测试成功！\n\n"
        "如果你在 iPhone 的 ntfy App 收到这条消息，"
        "说明 GitHub → ntfy → iPhone 推送正常。\n\n"
        "这是一条测试消息。"
    )

    print("")

    # ==============================
    # 同时测试 Apple 库存接口
    # ==============================

    print("Checking Apple Hong Kong stock...")

    successful_checks = 0

    for store_number, store_name in STORES.items():

        try:
            available = check_store(store_number)

            successful_checks += 1

            print(
                f"{store_name}: "
                f"{'AVAILABLE' if available else 'unavailable'}"
            )

        except Exception as e:

            print(
                f"{store_name}: ERROR - {e}"
            )

    if successful_checks == 0:
        raise RuntimeError(
            "所有香港 Apple Store 查询都失败。"
        )

    print("")
    print("Test completed successfully.")


if __name__ == "__main__":
    main()
