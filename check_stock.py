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

        raise RuntimeError(
            f"未知库存状态: {status}"
        )

    raise RuntimeError(
        f"Apple 没有返回门店 {store_number}"
    )


def main():
    previous = load_state()
    current = {}

    print("Checking Apple Hong Kong stock...")

    successful_checks = 0
    failed_stores = []

    for store_number, store_name in STORES.items():
        try:
            available = check_store(store_number)

            current[store_number] = available
            successful_checks += 1

            print(
                f"{store_name}: "
                f"{'AVAILABLE' if available else 'unavailable'}"
            )

        except Exception as e:
            failed_stores.append(store_name)

            print(
                f"{store_name}: ERROR - {e}"
            )

    # 如果所有门店都查询失败，直接让任务失败
    # 防止 Apple API 整体异常时误认为全部无货
    if successful_checks == 0:
        raise RuntimeError(
            "所有香港 Apple Store 查询都失败，"
            "为了防止漏报库存，本次不更新库存状态。"
        )

    # 只有成功查询到的门店才进行库存状态判断
    newly_available = []

    for store_number, available in current.items():
        was_available = previous.get(
            store_number,
            False
        )

        if available and not was_available:
            newly_available.append(
                STORES[store_number]
            )

    # 发现「无货 → 有货」
    if newly_available:
        message = (
            "🚨 Apple 香港门店发现库存！\n\n"
            "iPhone 18 Pro Max\n"
            "❄️ Glacier 冰川色\n"
            "💾 512GB\n\n"
            "有货门店：\n"
            + "\n".join(
                f"• {store}"
                for store in newly_available
            )
            + "\n\n"
            "立即打开 Apple 官方页面确认：\n"
            "https://www.apple.com/hk/shop/buy-iphone/"
            "iphone-18-pro/6.9-inch-display-512gb-glacier"
        )

        send_ntfy(message)

        print("NTFY notification sent!")

    # 只保存成功查询的门店
    #
    # 查询失败的门店保留旧状态，
    # 防止 API 临时异常造成误判。
    new_state = previous.copy()
    new_state.update(current)

    save_state(new_state)

    print("")
    print("Stock check completed.")

    if failed_stores:
        print("")
        print(
            "WARNING: 以下门店本次查询失败："
        )

        for store in failed_stores:
            print(f"- {store}")


if __name__ == "__main__":
    main()
