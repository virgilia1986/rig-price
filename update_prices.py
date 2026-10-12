import json
import os
import statistics
import time
import requests
import tweepy
from datetime import datetime, timezone, timedelta

JSON_FILE = "parts.json"
TEMP_FILE = "parts_temp.json"
REQUEST_INTERVAL = 3
REQUEST_TIMEOUT = 10
MIN_PRICE = 2500
MAX_PRICE = 350000

EXCLUDE_WORDS = [
    "ジャンク", "部品取り", "通電不可", "動作未確認", "不動",
    "クーラー", "ファン", "ヒートシンク", "グリス",
    "箱のみ", "空箱", "パッケージ", "外箱",
    "シール", "ステッカー", "マニュアル", "説明書"
]

YAHOO_CLIENT_ID = os.environ.get("YAHOO_CLIENT_ID")

def load_data():
    if not os.path.exists(JSON_FILE):
        raise FileNotFoundError(f"{JSON_FILE} が見つかりません。")
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"{JSON_FILE} が破損しています。詳細: {e}")
    
    if isinstance(data, dict) and "parts" in data:
        return data["parts"]
    elif isinstance(data, list) and len(data) > 0:
        return data
    else:
        raise ValueError(f"{JSON_FILE} の形式が正しくないか、空です。")

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
        "condition": "used",
        "results": 50
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
        title = item.get("name", "")
        price = item.get("price")
        
        if any(word in title for word in EXCLUDE_WORDS):
            continue
            
        if price and MIN_PRICE <= price <= MAX_PRICE:
            prices.append(price)

    if not prices:
        raise ValueError("有効な価格データなし")

    filtered_prices = remove_outliers(prices)
    return int(statistics.median(filtered_prices))

def save_data(parts):
    jst = timezone(timedelta(hours=9), 'JST')
    now_str = datetime.now(jst).strftime("%Y/%m/%d %H:%M")
    
    output_data = {
        "lastUpdated": now_str,
        "parts": parts
    }
    
    with open(TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    os.replace(TEMP_FILE, JSON_FILE)

def post_to_x(best_drop_part, best_drop_rate):
    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_secret = os.environ.get("X_ACCESS_SECRET")
    
    if not all([api_key, api_secret, access_token, access_secret]):
        print("X API keys are not set. Skip tweeting.")
        return

    message = "【RigPrice 中古相場を自動更新しました】\n\n"
    if best_drop_part:
        drop_percent = abs(int(best_drop_rate * 100))
        message += f"📉 注目パーツ: {best_drop_part['name']}\n昨日より {drop_percent}% 値下がりして ¥{best_drop_part['usedPriceAvg']:,} になりました！\n\n"
    else:
        message += "現在の最安値・適正価格をサイトでチェック！\n\n"

    message += "👇 フリマ・中古ショップの価格を一発比較\nhttps://virgilia1986.github.io/rig-price/\n#自作PC #PCパーツ #個人開発"

    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        client.create_tweet(text=message)
        print("Tweet posted successfully.")
    except Exception as e:
        print(f"Failed to tweet: {e}")

def main():
    parts = load_data()
    best_drop_part = None
    best_drop_rate = 0.0

    for index, part in enumerate(parts, start=1):
        query = part.get("shopQuery") or part.get("name")
        if not query:
            continue

        old_price = part.get("usedPriceAvg", 0)
        try:
            new_price = fetch_price(query)
            part["usedPriceAvg"] = new_price

            if isinstance(old_price, (int, float)) and old_price > 0 and new_price < old_price:
                drop_rate = (new_price - old_price) / old_price
                if drop_rate < best_drop_rate:
                    best_drop_rate = drop_rate
                    best_drop_part = part

        except Exception as e:
            pass

        if index < len(parts):
            time.sleep(REQUEST_INTERVAL)

    save_data(parts)
    
    # 全パーツ更新完了後、Xに自動投稿
    post_to_x(best_drop_part, best_drop_rate)

if __name__ == "__main__":
    main()
