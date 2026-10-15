
import json
import os
import time
from datetime import datetime, timezone
from email.header import Header

import requests


# ==================== 商品设置 ====================

PARTS = {
    "MJXW4ZA/A": "Glacier 冰川色",
    "MJXT4ZA/A": "Black 黑色",
    "MJXU4ZA/A": "Silver 银色",
    "MJXV4ZA/A": "Burgundy 布根地红",
}

BLUE_PART_NUMBER = "MJXW4ZA/A"

APPLE_URL = "https://www.apple.com/hk/shop/retail/pickup-message"
PRODUCT_URL = (
    "https://www.apple.com/hk/shop/buy-iphone/iphone-18-pro"
)

STATE_FILE = "stock_state.json"

# 有货提醒间隔：每种颜色独立计算
STOCK_INTERVAL = 60 * 60

# 全部无货提醒间隔：2 小时
NO_STOCK_INTERVAL = 2 * 60 * 60

MAX_RETRIES = 3
RETRY_DELAY = 3


# ==================== 门店设置 ====================

STORES = {
    "R409": "Canton Road 尖沙咀广东道",
    "R428": "ifc mall 国际金融中心",
    "R485": "Causeway Bay 铜锣湾",
    "R499": "Festival Walk 又一城",
    "R610": "New Town Plaza 新城市广场",
    "R673": "apm Hong Kong 观塘 apm",
}


# ==================== 请求设置 ====================

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

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()

if not NTFY_TOPIC:
    raise RuntimeError(
        "缺少 NTFY_TOPIC 环境变量，请检查 GitHub Secrets。"
    )


# ==================== 状态文件 ====================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception as e:
        print(f"WARNING: 无法读取状态文件：{e}")
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")


def make_check_key(store_number, part_number):
    return f"{store_number}|{part_number}"


def make_notice_key(part_number):
    # 每种颜色分别保存提醒时间
    safe_part_number = part_number.replace("/", "_")
    return f"last_stock_notice_{safe_part_number}"


# ==================== ntfy 通知 ====================

def send_ntfy(title, message, priority="high"):
    # 将中文标题编码，避免 HTTP 请求头编码错误
    encoded_title = Header(title, "utf-8").encode()

    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": encoded_title,
            "Priority": priority,
            "Tags": "apple,iphone",
        },
        timeout=20,
    )

    response.raise_for_status()

    print(f"NTFY notification sent: {title}")
    print(f"NTFY HTTP status: {response.status_code}")


# ==================== Apple 库存查询 ====================

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

                raise RuntimeError(
                    f"未知库存状态：{status}"
                )

            raise RuntimeError(
                f"Apple 没有返回门店 {store_number}"
            )

        except Exception as e:
            last_error = e

            print(
                f"{STORES[store_number]} / {part_number} "
                f"第 {attempt}/{MAX_RETRIES} 次失败：{e}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    raise RuntimeError(f"Apple 请求失败：{last_error}")


# ==================== 主程序 ====================

def main():
    previous = load_state()

    previous_checks = previous.get("checks", {})
    if not isinstance(previous_checks, dict):
        previous_checks = {}

    current = {}
    failed_checks = []

    total_checks = len(STORES) * len(PARTS)

    print("=" * 50)
    print("Apple 香港库存监控")
    print("型号：iPhone 18 Pro Max")
    print("容量：512GB")
    print(f"颜色数量：{len(PARTS)}")
    print(f"门店数量：{len(STORES)}")
    print(f"总查询数：{total_checks}")
    print("=" * 50)

    # 优先查询冰川色
    ordered_parts = sorted(
        PARTS.items(),
        key=lambda item: (
            0 if item[0] == BLUE_PART_NUMBER else 1
        ),
    )

    # 查询所有颜色与门店
    for part_number, color_name in ordered_parts:
        print(f"\n--- {color_name} ({part_number}) ---")

        for store_number, store_name in STORES.items():
            key = make_check_key(
                store_number,
                part_number,
            )

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

                print(
                    f"{store_name}: ERROR - {e}"
                )

    now_timestamp = datetime.now(timezone.utc).timestamp()

    # 用于判断状态文件是否需要更新
    new_state = previous.copy()
    saved_checks = previous_checks.copy()
    state_changed = False
    notification_sent = False

    # ================================================
    # 第一部分：每种颜色独立发送有货提醒
    # ================================================

    for part_number, color_name in ordered_parts:
        color_keys = [
            make_check_key(store_number, part_number)
            for store_number in STORES
        ]

        # 该颜色的 6 家门店必须全部查询成功
        color_checks_succeeded = all(
            key in current
            for key in color_keys
        )

        if not color_checks_succeeded:
            print(
                f"跳过 {color_name} 有货提醒："
                "该颜色有门店查询失败。"
            )
            continue

        # 只要该颜色至少一家门店有货，就视为该颜色有货
        available_stores = [
            (store_number, store_name)
            for store_number, store_name in STORES.items()
            if current.get(
                make_check_key(
                    store_number,
                    part_number,
                )
            ) is True
        ]

        if not available_stores:
            print(f"{color_name}：目前无货。")
            continue

        notice_key = make_notice_key(part_number)
        last_notice = previous.get(notice_key, 0)

        should_send = (
            now_timestamp - float(last_notice or 0)
            >= STOCK_INTERVAL
        )

        if not should_send:
            remaining = int(
                STOCK_INTERVAL
                - (now_timestamp - float(last_notice or 0))
            )

            print(
                f"{color_name}：有货，"
                f"距离下次提醒约 {max(0, remaining // 60)} 分钟。"
            )
            continue

        lines = [
            "Apple 香港门店库存提醒",
            "",
            "型号：iPhone 18 Pro Max",
            "容量：512GB",
            f"颜色：{color_name}",
            "",
            "目前有货的门店：",
        ]

        for store_number, store_name in available_stores:
            lines.append(f"• {store_name}")

        lines.extend([
            "",
            "提醒频率：该颜色每小时一次",
            "",
            "请尽快前往官网确认库存及取货时间：",
            PRODUCT_URL,
        ])

        if part_number == BLUE_PART_NUMBER:
            title = "🚨 冰川色现货提醒"
            priority = "urgent"
        else:
            title = f"📦 {color_name}现货提醒"
            priority = "high"

        # 发送成功后才更新该颜色的提醒时间
        send_ntfy(
            title,
            "\n".join(lines),
            priority=priority,
        )

        new_state[notice_key] = now_timestamp
        notification_sent = True

    # ================================================
    # 第二部分：全部无货时，每 2 小时提醒一次
    # ================================================

    all_checks_succeeded = (
        len(current) == total_checks
        and not failed_checks
    )

    all_unavailable = (
        all_checks_succeeded
        and not any(current.values())
    )

    last_no_stock_notice = float(
        previous.get("last_no_stock_notice", 0) or 0
    )

    should_send_no_stock = (
        all_unavailable
        and (
            now_timestamp - last_no_stock_notice
            >= NO_STOCK_INTERVAL
        )
    )

    if should_send_no_stock:
        message = (
            "📦 Apple 香港库存监控\n\n"
            "型号：iPhone 18 Pro Max 512GB\n\n"
            "4 种颜色、6 家门店均已成功查询，"
            "目前全部无货。\n\n"
            "监控仍在运行。\n"
            "下次无货提醒：约 2 小时后\n\n"
            f"官方页面：{PRODUCT_URL}"
        )

        send_ntfy(
            "📦 苹果香港门店暂时无货",
            message,
            priority="high",
        )

        new_state["last_no_stock_notice"] = now_timestamp
        notification_sent = True

    # ================================================
    # 第三部分：保存库存状态和提醒时间
    # ================================================

    for key, available in current.items():
        if saved_checks.get(key) != available:
            state_changed = True

        saved_checks[key] = available

    new_state["checks"] = saved_checks

    # 兼容旧版状态文件中的 stores 字段
    store_summary = {}
    for store_number in STORES:
        store_summary[store_number] = all(
            current.get(
                make_check_key(store_number, part_number)
            ) is True
            for part_number in PARTS
        ) if all(
            make_check_key(store_number, part_number) in current
            for part_number in PARTS
        ) else False

    new_state["stores"] = store_summary

    # 只在库存变化、通知发送或状态文件首次创建时保存。
    # 不要每分钟仅因为时间戳变化而提交文件。
    if (
        state_changed
        or notification_sent
        or not os.path.exists(STATE_FILE)
    ):
        new_state["last_checked_utc"] = (
            datetime.now(timezone.utc).isoformat()
        )
        save_state(new_state)
        print("\n库存状态已保存。")
    else:
        print("\n库存状态没有变化，无需更新状态文件。")

    print("\n" + "=" * 50)
    print(f"成功查询：{len(current)}/{total_checks}")

    if failed_checks:
        print("\n警告：以下查询失败，不能当作无货：")
        for item in failed_checks:
            print(f"- {item}")

    print("\n库存检查完成。")
    print("=" * 50)


if __name__ == "__main__":
    main()
