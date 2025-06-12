import xml.etree.ElementTree as ET
import sys
import os
from urllib.parse import urlparse
import re

# --- 設定項目 ---
INPUT_XML_FILE = 'export.xml'

# --- 名前空間の定義 ---
namespaces = {
    'wp': 'http://wordpress.org/export/1.2/',
    'content': 'http://purl.org/rss/1.0/modules/content/'
}

def create_media_library_map_debug(root):
    """メディアライブラリの情報を読み込む（デバッグ用）"""
    media_map = {}
    print("--- 1. メディアライブラリの読み込み開始 ---")
    
    items = root.findall('.//item')
    print(f"合計 {len(items)} 個の <item> タグが見つかりました。")

    attachment_count = 0
    for item in items:
        post_type = item.find('wp:post_type', namespaces)
        if post_type is not None and post_type.text == 'attachment':
            attachment_count += 1
            attachment_url_element = item.find('wp:attachment_url', namespaces)
            if attachment_url_element is not None and attachment_url_element.text:
                url = attachment_url_element.text
                filename = os.path.basename(urlparse(url).path)
                if filename:
                    media_map[filename.lower()] = url
    
    print(f"投稿タイプが 'attachment' のアイテムは {attachment_count} 個でした。")
    print(f"メディアライブラリマップには {len(media_map)} 件のファイル情報が作成されました。")
    print("-" * 20)
    return media_map

def main():
    """調査用のメイン処理"""
    if len(sys.argv) < 2:
        print("エラー: 調査したいファイル名を引数として指定してください。")
        print("例: python debug_tool.py \"my-image.jpg\"")
        return

    target_filename = sys.argv[1]
    print(f"調査対象ファイル名: {target_filename}")
    print("=" * 40)

    try:
        tree = ET.parse(INPUT_XML_FILE)
        root = tree.getroot()
    except Exception as e:
        print(f"エラー: {INPUT_XML_FILE} の読み込みに失敗しました: {e}")
        return

    # 1. メディアライブラリの情報を読み込んで表示
    media_map = create_media_library_map_debug(root)

    # 2. 調査対象ファイルがメディアライブラリに存在するかチェック
    print(f"--- 2. 調査対象ファイル「{target_filename}」の存在チェック ---")
    target_filename_lower = target_filename.lower()
    if target_filename_lower in media_map:
        print(f"結果: [成功] メディアライブラリ内に存在します。")
        print(f"URL: {media_map[target_filename_lower]}")
    else:
        print(f"結果: [失敗] メディアライブラリ内に存在しません。")
    print("-" * 20)

    # 3. コンテンツ内を検索し、関連する生のデータを表示
    print(f"--- 3. コンテンツ内から「{target_filename}」を含む投稿を検索 ---")
    content_elements = root.findall('.//content:encoded', namespaces)
    found_count = 0
    for i, content_element in enumerate(content_elements):
        content_text = content_element.text
        # 大文字小文字を区別せずにファイル名を検索
        if content_text and re.search(re.escape(target_filename), content_text, re.IGNORECASE):
            found_count += 1
            print(f"\n▼▼▼ {found_count}件目: コンテンツ番号 {i+1} で発見 ▼▼▼")
            # repr() を使って、特殊文字やエスケープも見えるように生のデータを表示
            print(repr(content_text))
            print("▲" * 30)

    if found_count == 0:
        print("結果: コンテンツ内に指定されたファイル名を含む投稿は見つかりませんでした。")
    else:
        print(f"\n合計 {found_count} 件のコンテンツでファイル名が見つかりました。")
    
    print("=" * 40)
    print("調査を終了します。")


if __name__ == '__main__':
    main()
