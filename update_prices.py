import json
import urllib.request
import urllib.parse
import re
import time
import os

def clean_json_string(s):
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s)

def get_used_price(query):
    try:
        encoded = urllib.parse.quote(f"{query} 中古")
        url = f"https://search.rakuten.co.jp/search/mall/{encoded}/?f=1&s=2"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        matches = re.findall(r'class="price--[^"]*">([\d,]+)円', html)
        prices = [int(p.replace(',', '')) for p in matches if int(p.replace(',', '')) >= 2000]

        if len(prices) >= 2:
            prices.sort()
            return prices[min(2, len(prices) - 1)]
    except Exception as e:
        print(f"Fetch skip ({query}): {e}")
    return None

def main():
    json_path = 'parts.json'
    if not os.path.exists(json_path):
        print("parts.json not found.")
        return

    with open(json_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content = clean_json_string(content)

    try:
        parts = json.loads(content)
    except Exception as e:
        print(f"JSON Parse Error: {e}")
        return

    print(f"Loaded {len(parts)} items. Scanning market prices...")
    updated = 0

    for item in parts:
        q = item.get('shopQuery') or item.get('name')
        new_p = get_used_price(q)
        time.sleep(1)

        if new_p and abs(new_p - item.get('usedPriceAvg', 0)) >= 500:
            old_p = item.get('usedPriceAvg', 0)
            print(f"Update: {item.get('name')} (¥{old_p:,} -> ¥{new_p:,})")
            item['usedPriceAvg'] = new_p
            updated += 1

    if updated > 0:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(parts, f, ensure_ascii=False, indent=2)
        print(f"Completed! {updated} prices updated.")
    else:
        print("Completed! All prices are up-to-date.")

if __name__ == '__main__':
    main()
