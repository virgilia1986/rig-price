import json
import urllib.request
import urllib.parse
import re
import time

def get_used_price(query):
    """
    楽天市場の中古市場データから最新の適正中古相場を算出
    """
    try:
        encoded_query = urllib.parse.quote(f"{query} 中古")
        url = f"https://search.rakuten.co.jp/search/mall/{encoded_query}/?f=1&s=2"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        matches = re.findall(r'class="price--[^"]*">([\d,]+)円', html)
        prices = [int(p.replace(',', '')) for p in matches if int(p.replace(',', '')) >= 2000]

        if len(prices) >= 3:
            prices.sort()
            # 極端なジャンク品を除外し、下位3番目付近の実用的な最安値を相場とする
            target_idx = min(2, len(prices) - 1)
            return prices[target_idx]
    except Exception as e:
        print(f"Error fetching {query}: {e}")
    return None

def main():
    try:
        with open('parts.json', 'r', encoding='utf-8') as f:
            parts = json.load(f)
    except Exception as e:
        print(f"Error reading parts.json: {e}")
        return

    updated_count = 0
    for part in parts:
        query = part.get('shopQuery') or part.get('name')
        new_price = get_used_price(query)
        time.sleep(1) # サーバー負荷軽減のための待機

        if new_price and abs(new_price - part.get('usedPriceAvg', 0)) >= 500:
            old_price = part.get('usedPriceAvg', 0)
            print(f"Updating {part['name']}: ¥{old_price:,} -> ¥{new_price:,}")
            part['usedPriceAvg'] = new_price
            updated_count += 1

    if updated_count > 0:
        with open('parts.json', 'w', encoding='utf-8') as f:
            json.dump(parts, f, ensure_ascii=False, indent=2)
        print(f"完了: {updated_count} 件のパーツ価格を自動更新しました。")
    else:
        print("大きな価格変動はありませんでした。")

if __name__ == '__main__':
    main()
