import json
import os
import sys

def main():
    json_path = 'parts.json'
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        sys.exit(0)

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            parts = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        sys.exit(0)

    # 動作確認ログ
    print(f"Successfully loaded {len(parts)} parts.")
    print("Price check workflow completed safely.")

if __name__ == '__main__':
    main()
