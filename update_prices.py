import json
import os
import re
import statistics
import time
import requests
from bs4 import BeautifulSoup

JSON_FILE = "parts.json"
TEMP_FILE = "parts_temp.json"

# 【指摘5】パーツ構成の初期値 (万が一のJSON破損時にここから復旧する)
DEFAULT_PARTS = [
    {
        "name": "Intel Core i7-14700K",
        "search_url": "https://shopping.yahoo.co.jp/search?p=Core+i7-14700K",
        "current_price": 0,
        "diffPercent": "0.0"
    },
    {
        "name": "NVIDIA GeForce RTX 4070 SUPER",
        "search_url": "https://shopping.yahoo.co.jp/search?p=RTX+4070+SUPER",
        "current_price": 0,
        "diffPercent": "0.0"
    }
]

def load_data():
    """JSONの読み込み。破損時はデフォルト設定で安全に復旧する。"""
    if not os.path.exists(JSON_FILE):
        return DEFAULT_PARTS.copy()
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("JSON format is invalid or empty.")
            return data
    except Exception as e:
        print(f"::warning:: {JSON_FILE} is broken ({e}). Fallback to DEFAULT_PARTS.")
        return DEFAULT_PARTS.copy()

def remove_outliers(prices):
    """【指摘1】四分位範囲(IQR)を用いて異常値(ジャンク品やケースのみ等)を除外する"""
    if len(prices) < 4:
        return prices  # データが少なすぎる場合はそのまま処理

    sorted_prices = sorted(prices)
    q1 = statistics.quantiles(sorted_prices, n=4)[0]
    q3 = statistics.quantiles(sorted_prices, n=4)[2]
    iqr = q3 - q1
    
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    # 外れ値を弾き、0円以下の異常値も除外
    valid_prices = [p for p in sorted_prices if p > 0 and lower_bound <= p <= upper_bound]
    
    return valid_prices if valid_prices else prices

def fetch_price(url):
    """【指摘3】正規表現を用いてノイズを拾わず正確に価格をパースする"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    
    # タイムアウトを設定し、無限ハングを防ぐ
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # サイトの構造に依存しすぎないよう、「数字＋円」のパターンを厳格に抽出
    price_elements = soup.find_all(string=re.compile(r'[0-9,]+\s*円'))
    
    prices = []
    for elem in price_elements:
        # 無関係な「1」などを拾わないよう、金額部分だけを正確に抜き出す
        match = re.search(r'([0-9,]{3,})', elem)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                prices.append(int(price_str))
            except ValueError:
                continue
                
    if not prices:
        raise ValueError("Could not find any valid price data on the page.")
        
    # 外れ値を除外した上で、平均ではなく「中央値」を返す
    valid_prices = remove_outliers(prices)
    return int(statistics.median(valid_prices))

def save_data(data):
    """【指摘5】アトミック書き込み処理 (保存中に強制終了されてもファイルが壊れない)"""
    with open(TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 完全に書き込めたら本ファイルにリネーム上書き
    os.replace(TEMP_FILE, JSON_FILE)

def main():
    parts_data = load_data()
    
    for part in parts_data:
        part_name = part.get("name", "Unknown")
        url = part.get("search_url")
        old_price = part.get("current_price", 0)
        
        if not url:
            print(f"::error:: No search_url for {part_name}")
            continue
            
        print(f"Fetching {part_name}...")
        try:
            new_price = fetch_price(url)
            
            # 【指摘2】変動率 (diffPercent) の計算と文字列フォーマット (+/- を付ける)
            if old_price > 0:
                diff = ((new_price - old_price) / old_price) * 100
                diff_str = f"{diff:+.1f}" 
            elif old_price == 0 and new_price > 0:
                diff_str = "+100.0"
            else:
                diff_str = "0.0"
                
            # 正常に取得できた場合のみ更新
            part["current_price"] = new_price
            part["diffPercent"] = diff_str
            print(f"Success: {part_name} | {old_price}円 -> {new_price}円 ({diff_str}%)")
            
        except Exception as e:
            # 【指摘4】エラーを pass で握りつぶさず、GitHub Actionsのログに明記。
            # かつ、価格は取得できなかったため old_price を維持する(安全なフェイルセーフ)
            print(f"::error:: Failed to update {part_name}. Error: {e}")
            print(f"Using previous price ({old_price}円) for {part_name}.")
            
        # アクセスブロック回避のためのインターバル
        time.sleep(2)
        
    # 全てのループが完了してから一括で安全に保存
    save_data(parts_data)
    print("All tasks completed.")

if __name__ == "__main__":
    main()
