"""
ハローワーク求人情報スクレイパー
"""

import requests
from bs4 import BeautifulSoup
import time
import re
import logging
from typing import Dict, List, Optional, Callable, Tuple
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

PREFECTURE_CODES = {
    "指定なし": "",
    "北海道": "01", "青森県": "02", "岩手県": "03", "宮城県": "04",
    "秋田県": "05", "山形県": "06", "福島県": "07", "茨城県": "08",
    "栃木県": "09", "群馬県": "10", "埼玉県": "11", "千葉県": "12",
    "東京都": "13", "神奈川県": "14", "新潟県": "15", "富山県": "16",
    "石川県": "17", "福井県": "18", "山梨県": "19", "長野県": "20",
    "岐阜県": "21", "静岡県": "22", "愛知県": "23", "三重県": "24",
    "滋賀県": "25", "京都府": "26", "大阪府": "27", "兵庫県": "28",
    "奈良県": "29", "和歌山県": "30", "鳥取県": "31", "島根県": "32",
    "岡山県": "33", "広島県": "34", "山口県": "35", "徳島県": "36",
    "香川県": "37", "愛媛県": "38", "高知県": "39", "福岡県": "40",
    "佐賀県": "41", "長崎県": "42", "熊本県": "43", "大分県": "44",
    "宮崎県": "45", "鹿児島県": "46", "沖縄県": "47",
}

# 雇用形態 → ippanCKBox 値リスト（フルタイム=1, パート=2）
EMP_TYPE_CODES = {
    "指定なし": [],
    "正社員": ["1"],
    "契約社員": ["1"],
    "パート・アルバイト": ["2"],
    "派遣社員": ["1"],
}

CORP_FIELD_MAP = {
    "法人番号": "法人番号",
    "事業所番号": "事業所番号",
    "事業所名": "事業所名",
    "ホームページ": "事業所ホームページ",
    "事業所ホームページ": "事業所ホームページ",
    "産業分類": "産業分類",
    "従業員数（企業全体）": "従業員数企業全体",
    "従業員数企業全体": "従業員数企業全体",
    "従業員数（就業場所）": "従業員数就業場所",
    "従業員数就業場所": "従業員数就業場所",
    "従業員数": "従業員数企業全体",
    "資本金": "資本金",
    "設立年": "創業年",
    "創業年": "創業年",
    "事業内容": "事業内容",
    "会社の特長": "会社の特長",
    "会社の特徴": "会社の特長",
    "代表者役職": "代表者役職",
    "代表者名": "代表者名",
    "就業場所": "就業場所住所",
    "転勤の範囲": "転勤範囲",
    "転勤範囲": "転勤範囲",
    "事業所所在地": "事業所所在地",
    "所在地": "事業所所在地",
}

JOB_FIELD_MAP = {
    "職種": "職種",
    "仕事の内容": "仕事内容",
    "仕事内容": "仕事内容",
    "必要な経験等": "必要な経験等",
    "必要なPCスキル": "必要なPCスキル",
    "必要な免許・資格": "必要な免許・資格",
    "採用人数": "採用人数",
    "募集理由区分": "募集理由区分",
    "その他募集理由": "その他募集理由",
    "求人に関する特記事項": "求人に関する特記事項",
    "事業内容・会社の特長": "事業内容・会社の特長",
}

EMPTY_RECORD = {
    "法人番号": "",
    "事業所番号": "",
    "事業所名": "",
    "事業所ホームページ": "",
    "産業分類": "",
    "従業員数企業全体": "",
    "従業員数就業場所": "",
    "資本金": "",
    "創業年": "",
    "事業内容": "",
    "会社の特長": "",
    "代表者役職": "",
    "代表者名": "",
    "就業場所住所": "",
    "転勤範囲": "",
    "事業所所在地": "",
    "職種": "",
    "仕事内容": "",
    "必要な経験等": "",
    "必要なPCスキル": "",
    "必要な免許・資格": "",
    "採用人数": "",
    "募集理由区分": "",
    "その他募集理由": "",
    "求人に関する特記事項": "",
    "事業内容・会社の特長": "",
    "求人番号": "",
    "詳細URL": "",
}

_MABA_VRBS = (
    "infTkRiyoDantaiBtn,searchShosaiBtn,searchBtn,searchNoBtn,"
    "searchClearBtn,searchNoClearBtn,searchNoClearBtn_mobile,"
    "dispDetailBtn,kyujinhyoBtn,checkedKyujinViewBtn,"
    "checkedKyujinhyoIppanBtn,checkedKyujinhyoDsBtn,changeSearchCond"
)


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


class HelloWorkScraper:
    BASE_URL = "https://www.hellowork.mhlw.go.jp"
    KENSAKU_URL = "/kensaku/GECA110010.do"

    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.stop_flag = False
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.hellowork.mhlw.go.jp/",
        })

    def search(
        self,
        keyword: str = "",
        prefecture: str = "指定なし",
        emp_type: str = "指定なし",
        max_count: int = 100,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
    ) -> List[Dict]:
        results: List[Dict] = []

        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        try:
            log("ハローワーク検索フォームへ接続中...")
            init_url = (
                self.BASE_URL + self.KENSAKU_URL
                + "?action=initDisp&screenId=GECA110010"
            )
            self._get(init_url)

            pref_code = PREFECTURE_CODES.get(prefecture, "")
            emp_boxes = EMP_TYPE_CODES.get(emp_type, [])

            form_data: List[Tuple[str, str]] = [
                ("action", "searchBtn"),
                ("screenId", "GECA110010"),
                ("kjKbnRadioBtn", "1"),
                ("freeWordInput", keyword),
                ("freeWordRadioBtn", "0"),
                ("todohukenHidden", pref_code),
                ("ensenHidden", ""),
                ("roudousijyoHidden", ""),
                ("kyujinkensu", "0"),
                ("iNFTeikyoRiyoDantaiID", ""),
                ("searchClear", "0"),
                ("kiboSuruSKSU1Hidden", ""),
                ("kiboSuruSKSU2Hidden", ""),
                ("kiboSuruSKSU3Hidden", ""),
                ("summaryDisp", "false"),
                ("searchInitDisp", "0"),
                ("hiddenViewedKyujinList", ""),
                ("CHECKEDKJNOLIST", ""),
                ("maba_vrbs", _MABA_VRBS),
                ("preCheckFlg", "false"),
                ("searchBtn", "検索する"),
            ]
            for box in emp_boxes:
                form_data.append(("ippanCKBox", box))

            log(f"検索条件: 都道府県={prefecture}, キーワード={keyword}, 雇用形態={emp_type}")
            list_url = self.BASE_URL + self.KENSAKU_URL
            resp = self._post(list_url, form_data)

        except Exception as exc:
            log(f"[ERROR] 検索フォーム取得失敗: {exc}")
            return results

        page = 1
        while not self.stop_flag and len(results) < max_count:
            soup = BeautifulSoup(resp.text, "lxml")
            links = self._extract_detail_links(soup)

            if not links:
                log(f"ページ {page}: 求人リンクが見つかりませんでした。終了します。")
                break

            log(f"ページ {page}: {len(links)} 件の求人リンクを検出")

            for detail_info in links:
                if self.stop_flag or len(results) >= max_count:
                    break
                record = self._scrape_detail(detail_info, log)
                if record:
                    results.append(record)
                    if progress_callback:
                        progress_callback(len(results))
                time.sleep(self.delay)

            next_data = self._find_next_page_data(soup)
            if not next_data or self.stop_flag or len(results) >= max_count:
                break
            log(f"次のページへ移動 (ページ {page + 1})")
            resp = self._post(self.BASE_URL + self.KENSAKU_URL, next_data)
            page += 1

        log(f"収集完了: {len(results)} 件")
        return results

    def _get(self, url: str, **kwargs) -> requests.Response:
        time.sleep(0.5)
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, data, **kwargs) -> requests.Response:
        time.sleep(0.5)
        resp = self.session.post(url, data=data, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def _extract_detail_links(self, soup: BeautifulSoup) -> List[dict]:
        links = []
        base = self.BASE_URL + self.KENSAKU_URL
        seen_kjno: set = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "dispDetailBtn" in href:
                m = re.search(r"kJNo=([^&]+)", href)
                kjno = m.group(1) if m else href
                if kjno not in seen_kjno:
                    seen_kjno.add(kjno)
                    links.append({"url": urljoin(base, href)})
        return links

    def _find_next_page_data(self, soup: BeautifulSoup) -> Optional[List[Tuple[str, str]]]:
        form = soup.find("form", id="ID_form_1")
        if not form:
            return None

        next_btn = form.find("input", {"name": "fwListNaviBtnNext"})
        if not next_btn:
            return None

        data: List[Tuple[str, str]] = []
        for inp in form.find_all("input"):
            name = inp.get("name")
            type_ = (inp.get("type") or "text").lower()
            val = inp.get("value", "")

            if not name:
                continue
            if type_ in ("submit", "button", "image", "reset"):
                continue
            if type_ == "radio" and not inp.get("checked"):
                continue
            if type_ == "checkbox" and not inp.get("checked"):
                continue

            data.append((name, val))

        for sel in form.find_all("select"):
            name = sel.get("name")
            if name:
                opt = sel.find("option", selected=True)
                data.append((name, opt["value"] if opt else ""))

        data.append(("fwListNaviBtnNext", next_btn.get("value", "次へ＞")))
        return data

    def _scrape_detail(self, detail_info: dict, log: Callable) -> Optional[Dict]:
        try:
            if "url" in detail_info:
                resp = self._get(detail_info["url"])
                page_url = detail_info["url"]
            else:
                resp = self._post(
                    detail_info["post_url"], detail_info["post_data"]
                )
                page_url = detail_info["post_url"]

            soup = BeautifulSoup(resp.text, "lxml")
            record = dict(EMPTY_RECORD)
            record["詳細URL"] = page_url
            self._parse_detail_page(soup, record)
            log(f"  取得: {record.get('事業所名', '(事業所名なし)')} / {record.get('職種', '(職種なし)')}")
            return record

        except Exception as exc:
            log(f"  [ERROR] 詳細ページ取得失敗: {exc}")
            return None

    def _parse_detail_page(self, soup: BeautifulSoup, record: dict):
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                ths = row.find_all("th")
                tds = row.find_all("td")
                if ths and tds:
                    for th, td in zip(ths, tds):
                        label = _clean(th.get_text())
                        value = _clean(td.get_text())
                        self._map_field(label, value, record)
                elif len(tds) >= 2:
                    label = _clean(tds[0].get_text())
                    value = _clean(tds[1].get_text())
                    self._map_field(label, value, record)

        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                label = _clean(dt.get_text())
                value = _clean(dd.get_text())
                self._map_field(label, value, record)

        num_text = soup.get_text()
        m = re.search(r"求人番号[\s：:]*([0-9A-Z\-]+)", num_text)
        if m:
            record["求人番号"] = m.group(1)
            parts = m.group(1).split("-")
            if len(parts) >= 2:
                record["事業所番号"] = record["事業所番号"] or "-".join(parts[:2])

        if not record.get("法人番号"):
            record["法人番号"] = "要別途確認"

    def _map_field(self, label: str, value: str, record: dict):
        if not label or not value:
            return
        for key, mapped in CORP_FIELD_MAP.items():
            if key in label:
                if not record.get(mapped):
                    record[mapped] = value
                return
        for key, mapped in JOB_FIELD_MAP.items():
            if key in label:
                if not record.get(mapped):
                    record[mapped] = value
                return
