# lxmlライブラリを使用するように変更
from lxml import etree as ET
import re
import requests
from bs4 import BeautifulSoup, NavigableString
import logging
import os
from urllib.parse import urlparse
import html

# --- 設定項目 ---
INPUT_XML_FILE = 'export.xml'   # 入力するWordPressのエクスポートファイル名
OUTPUT_XML_FILE = 'import.xml'  # 出力する新しいインポートファイル名
LOG_FILE = 'migration.log'      # ログファイル名

# --- ロギング設定 ---
def setup_logging():
    """ログファイルとコンソールに処理内容を出力する設定"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

# --- 名前空間の定義 ---
namespaces = {
    'wp': 'http://wordpress.org/export/1.2/',
    'content': 'http://purl.org/rss/1.0/modules/content/'
}


def create_media_library_map(root):
    """
    XMLのルート要素からメディアライブラリの情報を読み込み、
    {ファイル名: メディアライブラリのURL} の辞書を作成する
    """
    media_map = {}
    logging.info("ステップ0: メディアライブラリのURLマップを作成開始...")
    for item in root.findall('.//item'):
        post_type = item.find('wp:post_type', namespaces)
        if post_type is not None and post_type.text == 'attachment':
            attachment_url_element = item.find('wp:attachment_url', namespaces)
            if attachment_url_element is not None and attachment_url_element.text:
                url = attachment_url_element.text
                filename = os.path.basename(urlparse(url).path)
                if filename:
                    media_map[filename.lower()] = url
    logging.info(f"メディアライブラリから {len(media_map)} 件のファイル情報を読み込みました。")
    return media_map

def get_filename_from_url(url):
    """URLからファイル名を取得し、サムネイル部分があれば削除する"""
    base_filename = os.path.basename(urlparse(url).path)
    if '-thumb-' in base_filename:
        image_filename = re.sub(r'-thumb-.*(?=\.\w+$)', '', base_filename)
        logging.info(f"    -> サムネイル名を修正: {base_filename} -> {image_filename}")
        return image_filename
    return base_filename

def process_content(content_text, media_map):
    """
    コンテンツ本文を処理し、URLの置換を行う (BeautifulSoup全面採用版)
    """
    if not content_text:
        return ""

    unescaped_content = html.unescape(content_text)
    soup = BeautifulSoup(unescaped_content, 'html.parser')
    img_path_keywords = ["/assets_c/", "/today/images/"]

    # --- ルール3: テキストリンクなどの<a>タグの処理 (最優先) ---
    logging.info("--- 1. テキストの<a>タグの処理を開始 ---")
    for a_tag in soup.find_all('a', href=re.compile(r'/assets_c/')):
        if a_tag.find('img'): continue
        
        logging.info(f"  [テキスト<a>処理対象発見] タグ: {a_tag}")
        href = a_tag.get('href', '')
        image_filename = None
        
        if href.lower().endswith('.html'):
            try:
                response = requests.get(href, timeout=10)
                response.raise_for_status()
                html_soup = BeautifulSoup(response.content, 'html.parser')
                img_tag_in_html = html_soup.find('img')
                if not img_tag_in_html or not img_tag_in_html.get('src'):
                    logging.warning(f"    -> [スキップ] リンク先HTML内にimgタグが見つかりません: {href}")
                    continue
                # ▼▼▼ 修正箇所 ▼▼▼
                # リンク先のsrcからファイル名を取得するロジックに統一
                image_filename = get_filename_from_url(img_tag_in_html['src'])
                # ▲▲▲ 修正箇所 ▲▲▲
            except requests.RequestException as e:
                logging.error(f"    -> [エラー] HTMLページへのアクセス失敗: {href} ({e})")
                continue
        else:
            # ▼▼▼ 修正箇所 ▼▼▼
            # hrefからファイル名を取得するロジックに統一
            image_filename = get_filename_from_url(href)
            # ▲▲▲ 修正箇所 ▲▲▲
        
        if image_filename and image_filename.lower() in media_map:
            new_url = media_map[image_filename.lower()]
            new_img_tag = soup.new_tag('img', src=new_url)
            logging.info(f"    -> [置換成功] <a>タグを<img>タグに置換: {new_img_tag}")
            a_tag.replace_with(new_img_tag)
        else:
            logging.warning(f"    -> [スキップ] メディアライブラリにファイルが見つかりません: {image_filename}")

    # --- ルール1 & 2: すべての<img>タグを処理 (リンク内外を問わず) ---
    logging.info("--- 2. すべての<img>タグの処理を開始 ---")
    for img_tag in soup.find_all('img'):
        src = img_tag.get('src', '')
        if not src or not any(keyword in src for keyword in img_path_keywords):
            continue

        logging.info(f"  [<img>処理対象発見] タグ: {img_tag}")
        
        # ▼▼▼ 修正箇所 ▼▼▼
        # alt属性を見ずに、常にsrc属性からファイル名を生成する
        image_filename = get_filename_from_url(src)
        # ▲▲▲ 修正箇所 ▲▲▲

        if image_filename and image_filename.lower() in media_map:
            new_url = media_map[image_filename.lower()]
            logging.info(f"    -> ファイルを発見: {image_filename} -> {new_url}")
            
            img_tag['src'] = new_url
            for attr in ['class', 'width', 'height']:
                if img_tag.has_attr(attr): del img_tag[attr]
            
            if img_tag.parent.name == 'a':
                logging.info(f"    -> 親の<a>タグを削除します。")
                img_tag.parent.replace_with(img_tag)
        else:
            logging.warning(f"    -> [スキップ] メディアライブラリにファイルが見つかりません: {image_filename}")

    if soup.body:
        return soup.body.decode_contents()
    else:
        return str(soup)


def main():
    """メイン処理"""
    setup_logging()
    logging.info(f"ブログ移行処理を開始します。入力ファイル: {INPUT_XML_FILE}")

    try:
        parser = ET.XMLParser(remove_blank_text=True)
        tree = ET.parse(INPUT_XML_FILE, parser)
        root = tree.getroot()
    except FileNotFoundError:
        logging.error(f"エラー: 入力ファイルが見つかりません: {INPUT_XML_FILE}")
        return
    except ET.XMLSyntaxError as e:
        logging.error(f"エラー: XMLファイルの解析に失敗しました: {e}")
        return
    
    media_library_map = create_media_library_map(root)
    logging.info("コンテンツの修正処理を開始します...")
    
    content_elements = root.findall('.//content:encoded', namespaces)
    total_contents = len(content_elements)
    
    for i, content_element in enumerate(content_elements):
        logging.info(f"--- コンテンツ {i+1}/{total_contents} を処理中 ---")
        if content_element.text:
            modified_text = process_content(content_element.text, media_library_map)
            content_element.text = ET.CDATA(modified_text)

    try:
        tree.write(OUTPUT_XML_FILE, encoding='utf-8', xml_declaration=True, pretty_print=True)
        logging.info(f"ステップ5: 処理が正常に完了し、'{OUTPUT_XML_FILE}' が出力されました。")
    except Exception as e:
        logging.error(f"エラー: ファイルの書き込みに失敗しました: {e}")

if __name__ == '__main__':
    main()
