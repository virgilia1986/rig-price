import json
import os
import re
import statistics
import time
import urllib.parse
import urllib.request
from html import unescape

# ============================================================
# RigPrice Used - 中古価格自動更新
# ============================================================

JSON_FILE = "parts.json"
TEMP_FILE = "parts_temp.json"

# Yahoo!ショッピングへの連続アクセス間隔
REQUEST_INTERVAL = 3

# 通信タイムアウト
REQUEST_TIMEOUT = 15

# 中古パーツとして現実的に扱う価格範囲
MIN_PRICE = 2500
MAX_PRICE = 250000


# ============================================================
# parts.json 読み込み
# ============================================================

def load_data():
    """
    parts.jsonを読み込む。

    重要:
    JSONが壊れていた場合に別のダミーデータで上書きしない。
    データ破損時は処理を停止して、元データを守る。
    """

    if not os.path.exists(JSON_FILE):
        raise FileNotFoundError(
            f"{JSON_FILE} が見つかりません。"
        )

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{JSON_FILE} が破損しています。"
            f"安全のため処理を停止します。詳細: {e}"
        )

    if not isinstance(data, list):
        raise ValueError(
            f"{JSON_FILE} の形式が正しくありません。"
            "配列形式である必要があります。"
        )

    if len(data) == 0:
        raise ValueError(
            f"{JSON_FILE} が空です。安全のため処理を停止します。"
        )

    return data


# ============================================================
# Yahoo!ショッピング検索URL作成
# ============================================================

def build_search_url(query):
    """
    shopQueryからYahoo!ショッピングの中古検索URLを作る。

    「中古」を検索語にも追加することで、
    新品商品だけを拾う可能性を下げる。
    """

    search_query = f"{query} 中古"
    encoded_query = urllib.parse.quote(search_query)

    return (
        "https://shopping.yahoo.co.jp/search"
        f"?p={encoded_query}"
    )


# ============================================================
# HTMLから中古価格を抽出
# ============================================================

def extract_prices(html):
    """
    Yahoo!ショッピング検索結果HTMLから中古価格候補を抽出する。

    単純に「○○円」を全部拾うのではなく、

        「中古」

    が価格の近くに存在する価格だけを候補にする。

    これにより、ページ内の別用途の金額を多少除外する。
    """

    # HTMLエンティティを通常の文字に戻す
    html = unescape(html)

    # タグを除去してテキスト化
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)

    # 余分な空白を整理
    text = re.sub(r"\s+", " ", text)

    prices = []

    # 「数字 円」を探す
    price_pattern = re.compile(
        r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})\s*円"
    )

    for match in price_pattern.finditer(text):
        price_string = match.group(1).replace(",", "")

        try:
            price = int(price_string)
        except ValueError:
            continue

        # 現実的な中古PCパーツ価格だけを対象
        if price < MIN_PRICE or price > MAX_PRICE:
            continue

        # 価格の直前・直後に「中古」があるか確認
        start = max(0, match.start() - 180)
        end = min(len(text), match.end() + 80)

        nearby_text = text[start:end]

        if "中古" not in nearby_text:
            continue

        prices.append(price)

    # 同じ価格が大量に重複している場合を少し抑える
    prices = list(dict.fromkeys(prices))

    return prices


# ============================================================
# 外れ値除去
# ============================================================

def remove_outliers(prices):
    """
    IQR（四分位範囲）を使って極端な価格を除外する。

    例:
        20,000
        21,000
        22,000
        23,000
        150,000

    のような極端な値を相場計算から外す。
    """

    if len(prices) < 4:
        return prices

    sorted_prices = sorted(prices)

    q1 = statistics.quantiles(
        sorted_prices,
        n=4,
        method="inclusive"
    )[0]

    q3 = statistics.quantiles(
        sorted_prices,
        n=4,
        method="inclusive"
    )[2]

    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    filtered = [
        price
        for price in sorted_prices
        if lower <= price <= upper
    ]

    # 全部消えてしまった場合は元データを使用
    if not filtered:
        return sorted_prices

    return filtered


# ============================================================
# Yahoo!から価格取得
# ============================================================

def fetch_price(query):
    """
    Yahoo!ショッピングから中古価格を取得する。

    戻り値:
        中古相場の中央値

    取得できなかった場合:
        例外を発生させる
    """

    url = build_search_url(query)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            status = response.status

            if status != 200:
                raise RuntimeError(
                    f"HTTPステータス {status}"
                )

            html = response.read().decode(
                "utf-8",
                errors="ignore"
            )

    except Exception as e:
        raise RuntimeError(
            f"Yahoo!へのアクセスに失敗しました: {e}"
        )

    prices = extract_prices(html)

    if not prices:
        raise ValueError(
            "中古商品の価格を1件も取得できませんでした。"
        )

    filtered_prices = remove_outliers(prices)

    if not filtered_prices:
        raise ValueError(
            "有効な価格データがありません。"
        )

    median_price = int(
        statistics.median(filtered_prices)
    )

    print(
        f"  価格候補: {len(prices)}件"
        f" / 外れ値除去後: {len(filtered_prices)}件"
        f" / 中央値: ¥{median_price:,}",
        flush=True
    )

    return median_price


# ============================================================
# 安全なJSON保存
# ============================================================

def save_data(data):
    """
    一時ファイルへ保存してから本ファイルを置き換える。

    途中で処理が止まってもparts.jsonが空になるのを防ぐ。
    """

    with open(
        TEMP_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        TEMP_FILE,
        JSON_FILE
    )


# ============================================================
# メイン処理
# ============================================================

def main():

    print("========================================")
    print(" RigPrice Used - Price Update")
    print("========================================")
    print()

    # --------------------------------------------------------
    # parts.json読み込み
    # --------------------------------------------------------

    try:
        parts = load_data()

    except Exception as e:
        print(
            f"::error:: {e}",
            flush=True
        )
        raise SystemExit(1)

    print(
        f"対象パーツ: {len(parts)}件",
        flush=True
    )
    print()

    updated_count = 0
    failed_count = 0
    skipped_count = 0

    # --------------------------------------------------------
    # 各パーツ処理
    # --------------------------------------------------------

    for index, part in enumerate(parts, start=1):

        part_name = part.get(
            "name",
            f"Unknown #{index}"
        )

        # 現在のparts.jsonで使っている検索キー
        query = (
            part.get("shopQuery")
            or part.get("name")
        )

        if not query:
            print(
                f"::warning:: "
                f"[{index}/{len(parts)}] "
                f"{part_name}: 検索キーワードなし。スキップ",
                flush=True
            )

            skipped_count += 1
            continue

        old_price = part.get(
            "usedPriceAvg",
            0
        )

        print(
            f"[{index}/{len(parts)}] "
            f"Fetching: {part_name}",
            flush=True
        )

        print(
            f"  Query: {query}",
            flush=True
        )

        try:

            new_price = fetch_price(query)

            # ------------------------------------------------
            # usedPriceAvgだけを更新
            # ------------------------------------------------
            part["usedPriceAvg"] = new_price

            if isinstance(old_price, (int, float)) and old_price > 0:

                difference = new_price - old_price
                difference_percent = (
                    difference / old_price
                ) * 100

                print(
                    f"  ¥{old_price:,}"
                    f" -> ¥{new_price:,}"
                    f" ({difference_percent:+.1f}%)",
                    flush=True
                )

            else:

                print(
                    f"  ¥{new_price:,}"
                    " (初回取得)",
                    flush=True
                )

            updated_count += 1

        except Exception as e:

            # 取得失敗時は既存価格を変更しない
            failed_count += 1

            print(
                f"::error:: "
                f"[{index}/{len(parts)}] "
                f"{part_name}: {e}",
                flush=True
            )

            print(
                f"  既存価格 ¥{old_price:,} を維持",
                flush=True
            )

        # Yahooへの連続アクセスを避ける
        if index < len(parts):
            time.sleep(REQUEST_INTERVAL)

    # --------------------------------------------------------
    # 全処理終了後に一度だけ保存
    # --------------------------------------------------------

    try:

        save_data(parts)

    except Exception as e:

        print(
            f"::error:: parts.jsonの保存に失敗しました: {e}",
            flush=True
        )

        # 一時ファイルが残っていた場合の後始末
        if os.path.exists(TEMP_FILE):
            try:
                os.remove(TEMP_FILE)
            except OSError:
                pass

        raise SystemExit(1)

    # --------------------------------------------------------
    # 結果
    # --------------------------------------------------------

    print()
    print("========================================")
    print(" Update Completed")
    print("========================================")
    print(
        f"更新成功 : {updated_count}件",
        flush=True
    )
    print(
        f"取得失敗 : {failed_count}件",
        flush=True
    )
    print(
        f"スキップ : {skipped_count}件",
        flush=True
    )
    print("parts.jsonを保存しました。")
    print("========================================")


if __name__ == "__main__":
    main()
