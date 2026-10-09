
import json
import os
import time
from datetime import datetime, timezone

import requests

# 只监控 iPhone 18 Pro Max 512GB
# 请确认所有产品编号均对应香港官网的正确颜色和容量
PARTS = {
    "MJXW4ZA/A": "Glacier 冰川色",       # 重点颜色
    "MJXT4ZA/A": "Black 黑色",
    "MJXU4ZA/A": "Silver 银色",
    "MJXV4ZA/A": "Burgundy 布根地红",
}

BLUE_PART_NUMBER = "MJXW4ZA/A"

APPLE_URL = "https://www.apple.com/hk/shop/retail/pickup-message"
PRODUCT_URL = (
    "https://www.apple.com/hk/shop/buy-iphone/iphone-18-pro"
)

NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = "stock_state.json"

# 所有颜色、所有门店均确认无货时，每 2 小时提醒一次
NO_STOCK_INTERVAL = 2 * 60 * 60

MAX_RETRIES = 3
RETRY_DELAY = 3

STORES = {
    "R409": "Canton Road",
    "R428": "ifc mall",
    "R485": "Causeway Bay",
    "R499": "Festival Walk",
    "R610": "New Town Plaza",
    "R673": "apm Hong Kong",
}

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
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"WARNING: 无法读取状态文件: {e}")
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_ntfy(title, message, priority="urgent"):
    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            # 标题使用 ASCII，避免 HTTP Header 编码问题
            "Title": title,
            "Priority": priority,
            "Tags": "apple,iphone",
        },
        timeout=20,
    )
    response.raise_for_status()
    print(f"NTFY notification sent: {title}")


def check_store(store_number, part_number):
    params = {
        "pl": "true",
        "mts.0": "regular",
        "parts.0": part_number,
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

            stores = data.get("body", {}).get("stores", [])
            if not stores:
                raise RuntimeError("Apple 没有返回门店数据")

            for store in stores:
                if store.get("storeNumber") != store_number:
                    continue

                availability = store.get(
                    "partsAvailability", {}
                ).get(part_number, {})

                status = availability.get("pickupDisplay")

                if status == "available":
                    return True

                if status in ("unavailable", "ineligible"):
                    return False

                raise RuntimeError(f"未知库存状态: {status}")

            raise RuntimeError(
                f"Apple 没有返回门店 {store_number}"
            )

        except Exception as e:
            last_error = e
            print(
                f"{STORES[store_number]} / {part_number} "
                f"第 {attempt}/{MAX_RETRIES} 次失败: {e}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    raise RuntimeError(f"Apple 请求失败: {last_error}")


def make_check_key(store_number, part_number):
    return f"{store_number}|{part_number}"


def main():
    previous = load_state()

    # 兼容旧版状态文件：新版使用 checks 保存每个颜色、门店的状态
    previous_checks = previous.get("checks", {})
    if not isinstance(previous_checks, dict):
        previous_checks = {}

    current = {}
    failed_checks = []

    total_checks = len(STORES) * len(PARTS)

    print("Checking Apple Hong Kong stock...")
    print("Product: iPhone 18 Pro Max 512GB")
    print("Priority color: Glacier 冰川色")
    print(f"Colors: {len(PARTS)}")
    print(f"Stores: {len(STORES)}")
    print(f"Total checks: {total_checks}")
    print("")

    # 重点蓝色先检查，其余颜色也全部检查
    ordered_parts = sorted(
        PARTS.items(),
        key=lambda item: 0 if item[0] == BLUE_PART_NUMBER else 1,
    )

    for part_number, color_name in ordered_parts:
        print(f"--- {color_name} ({part_number}) ---")

        for store_number, store_name in STORES.items():
            key = make_check_key(store_number, part_number)

            try:
                available = check_store(
                    store_number,
                    part_number,
                )
                current[key] = available

                print(
                    f"{store_name}: "
                    f"{'AVAILABLE' if available else 'unavailable'}"
                )

            except Exception as e:
                failed_checks.append(
                    f"{color_name} / {store_name}: {e}"
                )
                print(f"{store_name}: ERROR - {e}")

    # 仅在库存从无货/未知变为有货时提醒，避免每分钟重复通知
    newly_available = []

    for key, available in current.items():
        was_available = previous_checks.get(key, False)

        if available and not was_available:
            store_number, part_number = key.split("|", 1)
            newly_available.append({
                "color": PARTS[part_number],
                "store": STORES[store_number],
                "part_number": part_number,
            })

    # 蓝色优先显示，其他颜色也照常通知
    if newly_available:
        newly_available.sort(
            key=lambda item: (
                0 if item["part_number"] == BLUE_PART_NUMBER else 1,
                item["store"],
            )
        )

        blue_items = [
            item for item in newly_available
            if item["part_number"] == BLUE_PART_NUMBER
        ]

        other_items = [
            item for item in newly_available
            if item["part_number"] != BLUE_PART_NUMBER
        ]

        lines = [
            "🚨 Apple 香港门店发现库存！",
            "",
            "型号：iPhone 18 Pro Max",
            "容量：512GB",
            "",
        ]

        if blue_items:
            lines.append("⭐ 蓝色重点库存提醒（冰川色）：")
            for item in blue_items:
                lines.append(f"• {item['store']}")

        if other_items:
            lines.extend([
                "",
                "📦 其他颜色有货：",
            ])
            for item in other_items:
                lines.append(
                    f"• {item['color']} — {item['store']}"
                )

        lines.extend([
            "",
            "请立即打开 Apple 香港官网确认库存：",
            PRODUCT_URL,
        ])

        # 同时发现蓝色和其他颜色时，标题仍突出蓝色
        if blue_items:
            title = "Apple HK BLUE STOCK ALERT"
        else:
            title = "Apple HK OTHER COLOR STOCK"

        send_ntfy(title, "\n".join(lines))

    # 只有全部 24 个组合查询成功且全部无货，才发无货提醒
    all_checks_succeeded = (
        len(current) == total_checks
        and not failed_checks
    )

    all_unavailable = (
        all_checks_succeeded
        and not any(current.values())
    )

    now_timestamp = datetime.now(timezone.utc).timestamp()
    last_notice = previous.get("last_no_stock_notice", 0)

    should_send_no_stock = (
        all_unavailable
        and now_timestamp - last_notice >= NO_STOCK_INTERVAL
    )

    if should_send_no_stock:
        message = (
            "📦 Apple 香港库存监控\n\n"
            "iPhone 18 Pro Max 512GB\n\n"
            "4 种颜色、6 家门店均已成功查询，"
            "目前全部无货。\n\n"
            "重点颜色：Glacier 冰川色\n"
            "其他颜色：黑色、银色、布根地红\n\n"
            "监控仍在运行。\n"
            "下次无货提醒：约 2 小时后\n\n"
            f"官方页面：{PRODUCT_URL}"
        )

        send_ntfy("Apple HK NO STOCK", message)
        previous["last_no_stock_notice"] = now_timestamp

    # 保存本次成功查询的结果；失败组合保留之前状态
    new_state = previous.copy()
    saved_checks = previous_checks.copy()
    state_changed = False

    for key, available in current.items():
        if saved_checks.get(key) != available:
            state_changed = True
        saved_checks[key] = available

    new_state["checks"] = saved_checks
    new_state["last_checked_utc"] = datetime.now(
        timezone.utc
    ).isoformat()

    if (
        state_changed
        or should_send_no_stock
        or not os.path.exists(STATE_FILE)
    ):
        save_state(new_state)
        print("Stock state updated.")
    else:
        print("No stock state change.")

    print("")
    print(
        f"Successful checks: {len(current)}/{total_checks}"
    )

    if failed_checks:
        print("")
        print("WARNING: 以下库存查询失败，不能视为无货：")
        for item in failed_checks:
            print(f"- {item}")

    print("")
    print("Stock check completed.")


if __name__ == "__main__":
    main()
