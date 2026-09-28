import json
import os
from datetime import datetime, timezone

import requests


# =========================
# Apple HK
# iPhone 18 Pro Max
# Glacier / 512GB
# =========================

PART_NUMBER = "MJXW4ZA/A"

APPLE_URL = (
    "https://www.apple.com/hk/shop/retail/pickup-message"
)

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

STATE_FILE = "stock_state.json"


# =========================
# Hong Kong Apple Stores
# =========================

STORES = {
    "R409": "Canton Road",
    "R428": "ifc mall",
    "R485": "Causeway Bay",
    "R499": "Festival Walk",
    "R610": "New Town Plaza",
    "R673": "apm Hong Kong",
}


# =========================
# Request headers
# =========================

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


# =========================
# Load saved state
# =========================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception:
        return {}


# =========================
# Save state
# =========================

def save_state(state):
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


# =========================
# Send ntfy notification
# =========================

def send_ntfy(title, message):

    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",

        data=message.encode("utf-8"),

        headers={
            # HTTP Header 不能直接放中文
            "Title": "Apple HK Stock Alert",

            "Priority": "urgent",

            "Tags": "apple,iphone",
        },

        timeout=20,
    )

    response.raise_for_status()

    print(
        "NTFY notification sent."
    )


# =========================
# Check one Apple Store
# =========================

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

    stores = (
        data
        .get("body", {})
        .get("stores", [])
    )

    if not stores:

        raise RuntimeError(
            "Apple 没有返回门店数据"
        )

    for store in stores:

        if (
            store.get("storeNumber")
            != store_number
        ):
            continue

        availability = store.get(
            "partsAvailability",
            {},
        )

        product = availability.get(
            PART_NUMBER,
            {},
        )

        status = product.get(
            "pickupDisplay"
        )

        if status == "available":

            return True

        if status in (
            "unavailable",
            "ineligible",
        ):

            return False

        raise RuntimeError(
            f"未知库存状态: {status}"
        )

    raise RuntimeError(
        f"Apple 没有返回门店 "
        f"{store_number}"
    )


# =========================
# Get today's UTC date
# =========================

def today_utc():

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d"
    )


# =========================
# Main
# =========================

def main():

    previous = load_state()

    current = {}

    successful_checks = 0

    failed_stores = []

    print(
        "Checking Apple Hong Kong stock..."
    )


    # =========================
    # Check all 6 stores
    # =========================

    for (
        store_number,
        store_name
    ) in STORES.items():

        try:

            available = check_store(
                store_number
            )

            current[
                store_number
            ] = available

            successful_checks += 1

            print(
                f"{store_name}: "
                f"{'AVAILABLE' if available else 'unavailable'}"
            )

        except Exception as e:

            failed_stores.append(
                store_name
            )

            print(
                f"{store_name}: ERROR - {e}"
            )


    # =========================
    # All stores failed
    # Do NOT update state
    # =========================

    if successful_checks == 0:

        raise RuntimeError(
            "所有香港 Apple Store "
            "查询都失败。"
            "本次不更新库存状态。"
        )


    # =========================
    # Detect new stock
    # =========================

    previous_stores = previous.get(
        "stores",
        {}
    )

    newly_available = []

    for (
        store_number,
        available
    ) in current.items():

        was_available = previous_stores.get(
            store_number,
            False
        )

        # 无货 → 有货
        if (
            available
            and not was_available
        ):

            newly_available.append(
                STORES[store_number]
            )


    # =========================
    # STOCK FOUND
    # =========================

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

        send_ntfy(
            "Apple HK Stock Alert",
            message,
        )


    # =========================
    # All stores unavailable
    # Send once per day
    # =========================

    all_unavailable = (
        successful_checks
        == len(STORES)
        and not any(
            current.values()
        )
    )

    today = today_utc()

    last_no_stock_notice = (
        previous.get(
            "last_no_stock_notice"
        )
    )


    if (
        all_unavailable
        and last_no_stock_notice
        != today
    ):

        message = (
            "📦 Apple 香港库存监控\n\n"

            "目前 6 家 Apple Store "
            "均没有库存。\n\n"

            "型号：iPhone 18 Pro Max\n"

            "颜色：Glacier 冰川色\n"

            "容量：512GB\n\n"

            "监控仍在正常运行。"
        )

        send_ntfy(
            "Apple HK No Stock",
            message,
        )

        previous[
            "last_no_stock_notice"
        ] = today


    # =========================
    # Save state
    # =========================

    new_state = previous.copy()

    old_stores = previous.get(
        "stores",
        {}
    )

    old_stores.update(
        current
    )

    new_state[
        "stores"
    ] = old_stores

    new_state[
        "last_check"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    save_state(
        new_state
    )


    # =========================
    # Result
    # =========================

    print("")

    print(
        "Stock check completed."
    )


    if failed_stores:

        print("")

        print(
            "WARNING: 以下门店查询失败："
        )

        for store in failed_stores:

            print(
                f"- {store}"
            )


# =========================
# Start
# =========================

if __name__ == "__main__":

    main()
