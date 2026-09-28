import json
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright

# ============ 配置区 ============
PART_NUMBER = "MJXW4ZA/A"
APPLE_URL = "https://www.apple.com/hk/shop/retail/pickup-message"
PRODUCT_URL = "https://www.apple.com/hk/shop/buy-iphone/iphone-18-pro/6.9-inch-display-512gb-glacier"
STORES = {
    "R409": "Canton Road", "R428": "ifc mall", "R485": "Causeway Bay",
    "R499": "Festival Walk", "R610": "New Town Plaza", "R673": "apm Hong Kong",
}

# ============ 环境变量 ============
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
if not NTFY_TOPIC:
    raise SystemExit("❌ 未设置 NTFY_TOPIC")

# ============ 核心：使用 Playwright 自动获取 Cookie ============
def get_cookie_with_playwright():
    print("🔄 正在启动浏览器获取 Cookie...")
    with sync_playwright() as p:
        # headless=True 表示无头模式，在后台静默运行
        browser = p.chromium.launch(headless=True)
        # 模拟一个真实的浏览器上下文，降低被风控的概率
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-HK",
            timezone_id="Asia/Hong_Kong",
        )
        page = context.new_page()
        try:
            # 访问 Apple 香港官网，触发 Cookie 生成
            print("  正在访问 Apple 香港官网...")
            page.goto("https://www.apple.com/hk/shop/buy-iphone", wait_until="networkidle", timeout=60000)
            # 等待一小段时间，确保所有 Cookie 都设置完毕
            time.sleep(3)
            # 获取浏览器上下文中的所有 Cookie
            cookies = context.cookies()
            if not cookies:
                print("   ⚠️ 未能获取到任何 Cookie。")
                return None
            # 将 Cookie 格式化为字符串
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            print(f"   ✅ 成功获取 Cookie (长度: {len(cookie_str)})")
            return cookie_str
        except Exception as e:
            print(f"   ❌ 获取 Cookie 时发生错误: {e}")
            return None
        finally:
            browser.close()

# ============ 带重试的 session ============
def build_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# ============ ntfy 推送 ============
def send_ntfy(message):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {"Title": "🍎 Apple 香港库存提醒", "Priority": "urgent", "Tags": "apple,iphone", "Click": PRODUCT_URL}
    try:
        response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=20)
        response.raise_for_status()
        print(f"   ✅ ntfy 推送成功: {response.status_code}")
    except Exception as e:
        print(f"   ❌ ntfy 推送失败: {e}")

# ============ 主逻辑 ============
def main():
    # 1. 获取 Cookie
    cookie_str = get_cookie_with_playwright()
    if not cookie_str:
        print("❌ 获取 Cookie 失败，本次检查终止。")
        return

    # 2. 构建请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.apple.com/hk/",
        "Cookie": cookie_str,
    }
    
    session = build_session()
    params = {"pl": "true", "mts.0": "regular", "parts.0": PART_NUMBER}
    
    print(f"🔍 查询 SKU: {PART_NUMBER}")
    response = session.get(APPLE_URL, params=params, headers=headers, timeout=30)
    print(f"📡 HTTP 状态码: {response.status_code}")

    if response.status_code != 200:
        print(f"❌ 响应内容前 500 字: {response.text[:500]}")
        return

    try:
        data = response.json()
    except Exception as e:
        print(f"❌ JSON 解析失败: {e}")
        print(f"响应前 500 字: {response.text[:500]}")
        return

    stores = data.get("body", {}).get("stores", [])
    print(f"🏬 返回门店数: {len(stores)}")

    if not stores:
        print("⚠️ Apple API 未返回门店数据。即使使用 Playwright，IP 也可能被暂时限制。")
        return

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
            "iPhone 18 Pro Max\n❄️ Glacier 冰川色\n💾 512GB\n\n"
            "有货门店：\n" + "\n".join(f"• {s}" for s in available_stores) +
            "\n\n请立即打开 Apple 官方页面确认并下单：\n" + PRODUCT_URL
        )
        send_ntfy(message)
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
        print(f"   {STORES[store_number]}: " + ("✅ AVAILABLE" if status == "available" else f"❌ {status}"))

if __name__ == "__main__":
    time.sleep(int(os.environ.get("START_DELAY", "0")))
    main()
