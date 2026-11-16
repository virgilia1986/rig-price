import json
import os
import statistics
import time
import requests
from datetime import datetime, timezone, timedelta

JSON_FILE = "parts.json"
TEMP_FILE = "parts_temp.json"
REQUEST_INTERVAL = 2
REQUEST_TIMEOUT = 10
MIN_PRICE = 2000
MAX_PRICE = 350000

# PC本体・ジャンク・水冷ブロック・サーバー用などのノイズを徹底除外
EXCLUDE_WORDS = [
    "ジャンク", "部品取り", "通電不可", "動作未確認", "不動", "訳あり", "難あり",
    "クーラー", "ファン", "ヒートシンク", "グリス", "水冷", "ウォーターブロック", "ブラケット",
    "箱のみ", "空箱", "パッケージ", "外箱", "化粧箱",
    "シール", "ステッカー", "マニュアル", "説明書", "ケーブル", "変換",
    "ゲーミングPC", "デスクトップ", "ノート", "パソコン", "本体", "BTO", "搭載",
    "セット", "自作代行", "組立", "レンタル", "サーバー", "ECC", "Registered", "増設"
]

# 追加したい最新の売れ筋人気パーツ（まだparts.jsonに無ければ自動で追加される）
NEW_POPULAR_PARTS = [
    {
        "id": "gpu-rtx4060",
        "category": "GPU-NVIDIA",
        "badge": "RTX 4060",
        "name": "GeForce RTX 4060 8GB",
        "newPriceRef": 46000,
        "usedPriceAvg": 36800,
        "recommend": "消費電力わずか115WでDLSS 3（フレーム生成）対応。電気代を抑えつつ最新ゲームをフルHDで快適に遊べる現行定番GPU。",
        "mercariQuery": "RTX 4060 8GB",
        "shopQuery": "RTX 4060 8GB"
    },
    {
        "id": "gpu-rtx4060ti",
        "category": "GPU-NVIDIA",
        "badge": "RTX 4060 Ti",
        "name": "GeForce RTX 4060 Ti 8GB",
        "newPriceRef": 62000,
        "usedPriceAvg": 48500,
        "recommend": "RTX 3070を超える省電力性能と最新機能を搭載。フルHD高リフレッシュレート〜WQHD入門に最適なバランス機。",
        "mercariQuery": "RTX 4060 Ti",
        "shopQuery": "RTX 4060 Ti"
    },
    {
        "id": "gpu-rtx4070s",
        "category": "GPU-NVIDIA",
        "badge": "RTX 4070 SUPER",
        "name": "GeForce RTX 4070 SUPER 12GB",
        "newPriceRef": 98000,
        "usedPriceAvg": 82800,
        "recommend": "無印4070からCUDAコアが大幅増強され、RTX 3090に迫る描画性能を発揮。WQHD〜4Kゲーミングの最適解。",
        "mercariQuery": "RTX 4070 SUPER",
        "shopQuery": "RTX 4070 SUPER"
    },
    {
        "id": "cpu-r7-5700x3d",
        "category": "CPU-AMD",
        "badge": "3D V-Cache",
        "name": "AMD Ryzen 7 5700X3D",
        "newPriceRef": 36000,
        "usedPriceAvg": 29800,
        "recommend": "5800X3Dに迫るゲーム性能を持ちながら価格を抑えたAM4延命の救世主。FPSゲームの最低フレームレートが劇的に向上。",
        "mercariQuery": "Ryzen 7 5700X3D",
        "shopQuery": "Ryzen 7 5700X3D"
    },
    {
        "id": "cpu-r7-7800x3d",
        "category": "CPU-AMD",
        "badge": "3D V-Cache",
        "name": "AMD Ryzen 7 7800X3D",
        "newPriceRef": 68000,
        "usedPriceAvg": 54800,
        "recommend": "世界最高峰のゲーミング性能を誇るAM5の王道CPU。VALORANTやApex、タルコフで限界までFPSを稼ぎたいならこれ一択。",
        "mercariQuery": "Ryzen 7 7800X3D",
        "shopQuery": "Ryzen 7 7800X3D"
    }
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
        parts = data["parts"]
    elif isinstance(data, list) and len(data) > 0:
        parts = data
    else:
        raise ValueError(f"{JSON_FILE} の形式が正しくないか、空です。")

    # 人気パーツがまだ登録されていなければ自動追加
    existing_names = {p.get("name") for p in parts}
    for new_part in NEW_POPULAR_PARTS:
        if new_part["name"] not in existing_names:
            parts.append(new_part)

    return parts


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


def is_valid_title(title, part):
    title_upper = title.upper()
    # 除外ワードチェック
    if any(word.upper() in title_upper for word in EXCLUDE_WORDS):
        return False

    # 無印のモデル検索時に上位モデル（Ti / SUPER / XT / X3D）が混ざるのを防止
    query_upper = (part.get("shopQuery") or part.get("name") or "").upper()
    if "TI" not in query_upper and (" TI" in title_upper or "TI " in title_upper or "TI/" in title_upper):
        return False
    if "SUPER" not in query_upper and "SUPER" in title_upper:
        return False
    if "XT" not in query_upper and (" XT" in title_upper or "XT " in title_upper):
        return False
    if "X3D" not in query_upper and "X3D" in title_upper:
        return False

    return True


def fetch_price(part):
    if not YAHOO_CLIENT_ID:
        raise ValueError("YAHOO_CLIENT_IDが環境変数に設定されていません。")

    query = part.get("shopQuery") or part.get("name")
    new_price_ref = part.get("newPriceRef", 0)

    # 新品参考価格がある場合は、異常な高値（PC本体混入）や極端な安値を事前にカット
    dynamic_min = max(MIN_PRICE, int(new_price_ref * 0.15)) if new_price_ref > 0 else MIN_PRICE
    dynamic_max = min(MAX_PRICE, int(new_price_ref * 1.15)) if new_price_ref > 0 else MAX_PRICE

    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    params = {
        "appid": YAHOO_CLIENT_ID,
        "query": query,
        "condition": "used",
        "genre_category_id": 2502,  # PCパーツカテゴリに限定してPC本体や家電を除外
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

        if not is_valid_title(title, part):
            continue

        if price and dynamic_min <= price <= dynamic_max:
            prices.append(price)

    if not prices:
        raise ValueError(f"有効な価格データなし: {query}")

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


def main():
    parts = load_data()

    for index, part in enumerate(parts, start=1):
        query = part.get("shopQuery") or part.get("name")
        if not query:
            continue

        try:
            new_price = fetch_price(part)
            part["usedPriceAvg"] = new_price
            print(f"[OK] {part['name']}: ¥{new_price:,}")
        except Exception as e:
            print(f"[SKIP] {part['name']}: {e}")

        if index < len(parts):
            time.sleep(REQUEST_INTERVAL)

    save_data(parts)


if __name__ == "__main__":
    main()
