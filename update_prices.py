import json
import os
import re
import urllib.request
import urllib.parse
import statistics
import time

JSON_FILE = "parts.json"
TEMP_FILE = "parts_temp.json"

def load_data():
    """JSON破損時は絶対にダミーデータで上書きせず、即座に処理を止めてデータを守る"""
    if not os.path.exists(JSON_FILE):
        raise FileNotFoundError(f"{JSON_FILE} が見つかりません。")
    
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            raise ValueError(f"{JSON_FILE} が破損しています。安全のため処理を強制停止します。")
            
    if not data or not isinstance(data, list):
        raise ValueError("JSONの形式が正しくありません。")
        
    return data

def fetch_price(url):
    """標準機能だけで取得。ノイズを弾き、中央値を取る"""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        raise RuntimeError(f"通信エラー: {e}")
        
    matches = re.findall(r'([0-9,]{3,})円', html)
    prices = []
    for m in matches:
        try:
            prices.append(int(m.replace(',', '')))
        except ValueError:
            continue
            
    if not prices:
        raise ValueError("ページ内に価格データが見つかりませんでした。")
        
    # 外れ値（送料やジャンク品など）を簡易的に除外するための四分位処理
    if len(prices) >= 4:
        sorted_prices = sorted(prices)
        q1_idx = len(sorted_prices) // 4
        q3_idx = (len(sorted_prices) * 3) // 4
        q1 = sorted_prices[q1_idx]
        q3 = sorted_prices[q3_idx]
        iqr = q3 - q1
        
        valid_prices = [p for p in sorted_prices if p > 0 and (q1 - 1.5 * iqr) <= p <= (q3 + 1.5 * iqr)]
        if valid_prices:
            return int(statistics.median(valid_prices))
            
    return int(statistics.median(prices))

def main():
    try:
        parts_data = load_data()
    except Exception as e:
        print(f"::error:: {e}")
        exit(1)
        
    for part in parts_data:
        part_name = part.get("name", "Unknown")
        
        # 【修正点1】実際のJSONに合わせて shopQuery（検索キーワード）を取得する
        query = part.get("shopQuery") or part.get("name")
        
        if not query:
            print(f"::warning:: {part_name} の検索キーワードが見つからないためスキップします。")
            continue
            
        # 【修正点2】検索キーワードをURLエンコードし、Yahooショッピングの検索URLを動的に生成する
        encoded_query = urllib.parse.quote(query)
        url = f"https://shopping.yahoo.co.jp/search?p={encoded_query}"
            
        print(f"Fetching {part_name} (Query: {query})...")
        try:
            new_price = fetch_price(url)
            
            # 【修正点3】余計なキーを作らず、既存の usedPriceAvg を正しく更新する
            part["usedPriceAvg"] = new_price
            
            print(f"Success: {part_name} -> {new_price}円")
            
        except Exception as e:
            # 取得失敗時はエラーを通知しつつ、該当パーツの価格更新だけをスキップする
            print(f"::error:: {part_name} の更新に失敗: {e}")
            
        time.sleep(2)
        
    # アトミック書き込み（途中で強制終了してもファイルが空にならない）
    with open(TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(parts_data, f, ensure_ascii=False, indent=2)
    os.replace(TEMP_FILE, JSON_FILE)
    print("すべての処理が完了しました。")

if __name__ == "__main__":
    main()
    
