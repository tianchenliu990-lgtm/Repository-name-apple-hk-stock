import json
import os
import time
from datetime import datetime, timezone

import requests


# ============================================================
# Configuration
# ============================================================

PART_NUMBER = "MJXW4ZA/A"

APPLE_URL = (
    "https://www.apple.com/hk/shop/retail/pickup-message"
)

PRODUCT_URL = (
    "https://www.apple.com/hk/shop/buy-iphone/"
    "iphone-18-pro/6.9-inch-display-512gb-glacier"
)

NTFY_TOPIC = os.environ["NTFY_TOPIC"]

STATE_FILE = "stock_state.json"

# 没货时，每 2 小时提醒一次
NO_STOCK_INTERVAL = 2 * 60 * 60

# Apple 请求失败时最多重试 3 次
MAX_RETRIES = 3

# 每次重试间隔
RETRY_DELAY = 3


# ============================================================
# Hong Kong Apple Stores
# ============================================================

STORES = {
    "R409": "Canton Road",
    "R428": "ifc mall",
    "R485": "Causeway Bay",
    "R499": "Festival Walk",
    "R610": "New Town Plaza",
    "R673": "apm Hong Kong",
}


# ============================================================
# HTTP headers
# ============================================================

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


# ============================================================
# Load state
# ============================================================

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

    except Exception as e:
        print(f"WARNING: 无法读取状态文件: {e}")
        return {}


# ============================================================
# Save state
# ============================================================

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


# ============================================================
# Send ntfy notification
# ============================================================

def send_ntfy(title, message):

    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            # Header 只能使用 ASCII
            "Title": title,
            "Priority": "urgent",
            "Tags": "apple,iphone",
        },
        timeout=20,
    )

    response.raise_for_status()

    print("NTFY notification sent.")


# ============================================================
# Check one Apple Store
# ============================================================

def check_store(store_number):

    params = {
        "pl": "true",
        "mts.0": "regular",
        "parts.0": PART_NUMBER,
        "store": store_number,
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

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
                f"Apple 没有返回门店 {store_number}"
            )

        except Exception as e:

            last_error = e

            print(
                f"{STORES[store_number]} "
                f"第 {attempt}/{MAX_RETRIES} 次失败: {e}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    raise RuntimeError(
        f"Apple 请求失败: {last_error}"
    )


# ============================================================
# Main
# ============================================================

def main():

    previous = load_state()

    previous_stores = previous.get(
        "stores",
        {},
    )

    current = {}

    successful_checks = 0

    failed_stores = []


    print(
        "Checking Apple Hong Kong stock..."
    )

    print(
        "Product: iPhone 18 Pro Max "
        "Glacier 512GB"
    )

    print("")


    # ========================================================
    # Check all stores
    # ========================================================

    for (
        store_number,
        store_name,
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


    # ========================================================
    # All Apple requests failed
    # Do not change stock state
    # ========================================================

    if successful_checks == 0:

        raise RuntimeError(
            "所有香港 Apple Store 查询都失败，"
            "本次不更新库存状态。"
        )


    # ========================================================
    # Detect newly available stores
    # ========================================================

    newly_available = []

    for (
        store_number,
        available,
    ) in current.items():

        was_available = previous_stores.get(
            store_number,
            False,
        )

        # 无货 → 有货
        if (
            available
            and not was_available
        ):

            newly_available.append(
                STORES[store_number]
            )


    # ========================================================
    # Stock found
    # ========================================================

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
            + PRODUCT_URL
        )

        send_ntfy(
            "Apple HK Stock Alert",
            message,
        )


    # ========================================================
    # Check whether all stores are unavailable
    # ========================================================

    all_unavailable = (
        successful_checks == len(STORES)
        and not any(current.values())
    )


    # ========================================================
    # No-stock notification every 20 minutes
    # ========================================================

    now = datetime.now(
        timezone.utc
    )

    now_timestamp = now.timestamp()

    last_no_stock_notice = previous.get(
        "last_no_stock_notice",
        0,
    )

    should_send_no_stock = (
        all_unavailable
        and (
            now_timestamp
            - last_no_stock_notice
            >= NO_STOCK_INTERVAL
        )
    )


    if should_send_no_stock:

        message = (
            "📦 Apple 香港库存监控\n\n"
            "目前 6 家 Apple Store "
            "均没有库存。\n\n"
            "型号：iPhone 18 Pro Max\n"
            "颜色：Glacier 冰川色\n"
            "容量：512GB\n\n"
            "监控仍在正常运行。\n\n"
            "下次无货提醒：约 20 分钟后"
        )

        send_ntfy(
            "Apple HK No Stock",
            message,
        )

        previous[
            "last_no_stock_notice"
        ] = now_timestamp


    # ========================================================
    # Update stock state
    # ========================================================

    new_state = previous.copy()

    old_stores = previous.get(
        "stores",
        {},
    ).copy()

    state_changed = False

    for (
        store_number,
        available,
    ) in current.items():

        if (
            old_stores.get(store_number)
            != available
        ):

            state_changed = True

        old_stores[
            store_number
        ] = available


    new_state[
        "stores"
    ] = old_stores


    # ========================================================
    # Only save when something meaningful changed
    # ========================================================

    if (
        state_changed
        or should_send_no_stock
        or not os.path.exists(STATE_FILE)
    ):

        save_state(
            new_state
        )

        print(
            "Stock state updated."
        )

    else:

        print(
            "No stock state change."
        )


    # ========================================================
    # Result
    # ========================================================

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


# ============================================================
# Start
# ============================================================

if __name__ == "__main__":
    main()
