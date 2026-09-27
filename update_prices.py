import json
import urllib.request
import urllib.parse
import re
import time
import os

def get_used_price(query):
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
            target_idx = min(2, len(prices) - 1)
            return prices[target_idx]
    except Exception as e:
        print(f"Error fetching {query}: {e}")
    return None

def main():
    json_path = 'parts.json'
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            parts = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        return

    updated_count = 0
    for part in parts:
        query = part.get('shopQuery') or part.get('name')
        new_price = get_used_price(query)
        time.sleep(1)

        if new_price and abs(new_price - part.get('usedPriceAvg', 0)) >= 500:
            old_price = part.get('usedPriceAvg', 0)
            print(f"Updating {part['name']}: ¥{old_price:,} -> ¥{new_price:,}")
            part['usedPriceAvg'] = new_price
            updated_count += 1

    if updated_count > 0:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(parts, f, ensure_ascii=False, indent=2)
        print(f"Update complete: {updated_count} items updated.")
    else:
        print("No significant price changes.")

if __name__ == '__main__':
    main()
