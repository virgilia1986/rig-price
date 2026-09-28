import json
import os
import statistics
import time
import requests

JSON_FILE = "parts.json"
TEMP_FILE = "parts_temp.json"
REQUEST_INTERVAL = 1  # API利用のため1秒間隔に短縮
REQUEST_TIMEOUT = 10
MIN_PRICE = 2500
MAX_PRICE = 250000

# GitHub SecretsからAPIキーを取得
YAHOO_CLIENT_ID = os.environ.get("YAHOO_CLIENT_ID")

def load_data():
    if not os.path.exists(JSON_FILE):
        raise FileNotFoundError(f"{JSON_FILE} が見つかりません。")
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"{JSON_FILE} が破損しています。詳細: {e}")
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError(f"{JSON_FILE} の形式が正しくないか、空です。")
    return data

def remove_outliers(prices):
    if len(prices) < 4:
        return prices
    sorted_prices = sorted(prices)
    q1 = statistics.quantiles(sorted_prices, n=4, method="inclusive")[0]
    q3 = statistics.quantiles(sorted_prices, n=4, method="inclusive")[2]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    filtered = [p for p in sorted_prices if lower <= p <= upper]
    return filtered if filtered else sorted_prices

def fetch_price(query):
    if not YAHOO_CLIENT_ID:
        raise ValueError("YAHOO_CLIENT_IDが環境変数に設定されていません。")

    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    params = {
        "appid": YAHOO_CLIENT_ID,
        "query": query,
        "condition": "used",  # 中古品のみを指定
        "results": 50         # 最大50件取得して精度を高める
    }
    
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise RuntimeError(f"APIリクエストに失敗しました: {e}")

    hits = data.get("hits", [])
    prices = []
    
    for item in hits:
        price = item.get("price")
        if price and MIN_PRICE <= price <= MAX_PRICE:
            prices.append(price)

    if not prices:
        raise ValueError("該当する中古商品の価格データを取得できませんでした。")

    filtered_prices = remove_outliers(prices)
    median_price = int(statistics.median(filtered_prices))
    
    print(f"  取得件数: {len(prices)}件 / 外れ値除去後: {len(filtered_prices)}件 / 中央値: ¥{median_price:,}", flush=True)
    return median_price

def save_data(data):
    with open(TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(TEMP_FILE, JSON_FILE)

def main():
    print("========================================")
    print(" RigPrice Used - Price Update (API Version)")
    print("========================================\n")

    try:
        parts = load_data()
    except Exception as e:
        print(f"::error:: {e}", flush=True)
        raise SystemExit(1)

    print(f"対象パーツ: {len(parts)}件\n", flush=True)
    updated_count = failed_count = skipped_count = 0

    for index, part in enumerate(parts, start=1):
        part_name = part.get("name", f"Unknown #{index}")
        query = part.get("shopQuery") or part.get("name")

        if not query:
            print(f"::warning:: [{index}/{len(parts)}] {part_name}: 検索キーワードなし。スキップ", flush=True)
            skipped_count += 1
            continue

        old_price = part.get("usedPriceAvg", 0)
        print(f"[{index}/{len(parts)}] Fetching: {part_name}", flush=True)
        print(f"  Query: {query}", flush=True)

        try:
            new_price = fetch_price(query)
            part["usedPriceAvg"] = new_price

            if isinstance(old_price, (int, float)) and old_price > 0:
                diff_percent = ((new_price - old_price) / old_price) * 100
                print(f"  ¥{old_price:,} -> ¥{new_price:,} ({diff_percent:+.1f}%)", flush=True)
            else:
                print(f"  ¥{new_price:,} (初回取得)", flush=True)
            updated_count += 1
        except Exception as e:
            failed_count += 1
            print(f"::error:: [{index}/{len(parts)}] {part_name}: {e}", flush=True)
            print(f"  既存価格 ¥{old_price:,} を維持", flush=True)

        if index < len(parts):
            time.sleep(REQUEST_INTERVAL)

    try:
        save_data(parts)
    except Exception as e:
        print(f"::error:: parts.jsonの保存に失敗しました: {e}", flush=True)
        if os.path.exists(TEMP_FILE):
            try: os.remove(TEMP_FILE)
            except OSError: pass
        raise SystemExit(1)

    print("\n========================================")
    print(" Update Completed")
    print("========================================")
    print(f"更新成功 : {updated_count}件", flush=True)
    print(f"取得失敗 : {failed_count}件", flush=True)
    print(f"スキップ : {skipped_count}件", flush=True)
    print("parts.jsonを保存しました。")
    print("========================================")

if __name__ == "__main__":
    main()
