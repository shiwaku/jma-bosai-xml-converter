"""Atom フィードから電文を探し、取得する。

気象庁は1日10GBを超えるとアクセス元を遮断する。電文の URL は一意で中身が変わらないので、
URL をキーに手元へ保存し、二度と取りにいかない。
"""

from __future__ import annotations

import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

FEED_BASE = "https://www.data.jma.go.jp/developer/xml/feed/"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
USER_AGENT = "jma-bosai-xml-converter (+https://github.com/shiwaku/jma-bosai-xml-converter)"


@dataclass(frozen=True)
class Entry:
    title: str
    author: str
    updated: str
    url: str

    @property
    def data_type(self) -> str:
        """電文の種類のコード（URL の3つ目の要素。例: VPFD51）"""
        return self.url.rsplit("/", 1)[-1].split("_")[2]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read()


def read_feed(name: str) -> list[Entry]:
    """フィード（regular / extra / eqvol / other と、その長期版 *_l）を読む。"""
    root = ET.fromstring(_get(f"{FEED_BASE}{name}.xml"))
    return [
        Entry(
            title=e.findtext("a:title", "", ATOM),
            author=e.findtext("a:author/a:name", "", ATOM),
            updated=e.findtext("a:updated", "", ATOM),
            url=e.findtext("a:id", "", ATOM),
        )
        for e in root.findall("a:entry", ATOM)
    ]


def latest_by_author(entries: list[Entry], data_type: str) -> list[Entry]:
    """種類ごとに、発表官署ごとの最新の1通を返す。"""
    latest: dict[str, Entry] = {}
    for e in entries:
        if e.data_type != data_type:
            continue
        if e.author not in latest or e.updated > latest[e.author].updated:
            latest[e.author] = e
    return sorted(latest.values(), key=lambda e: e.url)


def fetch(url: str, cache_dir: Path, wait: float = 0.2) -> bytes:
    """電文を取得する。手元にあれば取りにいかない。"""
    path = cache_dir / url.rsplit("/", 1)[-1]
    if path.exists():
        return path.read_bytes()
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = _get(url)
    path.write_bytes(data)
    time.sleep(wait)
    return data
