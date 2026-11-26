"""気象警報・注意報の電文を、区域 × 警報の種類 の表に平らにする。

対象: VPWW53/54（旧）、VPWW55〜61（R06 現象別）、VPWS50（R06 集約通報）。
どれも Body/Warning[@type] の下に Item(Kind*, Area) が並ぶ同じ骨格を持つ。

値は書き換えない。Kind の Name・Code・Status は電文のまま出す。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

NS = {
    "jmx": "http://xml.kishou.go.jp/jmaxml1/",
    "ib": "http://xml.kishou.go.jp/jmaxml1/informationBasis1/",
    "b": "http://xml.kishou.go.jp/jmaxml1/body/meteorology1/",
}

# Warning@type の「（…）」の中身 → 区域の階層
LEVELS = {
    "府県予報区等": "prefecture",
    "一次細分区域等": "primary",
    "市町村等をまとめた地域等": "city_group",
    "市町村等": "city",
}

# 区域に「出ていない」ことを表す Status。これ以外は発表中とみなす
INACTIVE_STATUS = {"解除", "発表警報・注意報はなし"}


@dataclass
class WarningRow:
    # 電文
    title: str
    telegram_type: str
    office: str
    report_datetime: str
    info_type: str
    # 区域
    level: str
    area_code: str
    area_name: str
    # 警報の種類（発表なしの区域では空）
    kind_code: str | None
    kind_name: str | None
    status: str
    kind_datetime: str | None
    last_kind_name: str | None
    change_status: str | None
    full_status: str | None

    @property
    def active(self) -> bool:
        return self.status not in INACTIVE_STATUS


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path, NS)
    return found.text.strip() if found is not None and found.text else None


def parse(xml: bytes) -> list[WarningRow]:
    root = ET.fromstring(xml)
    control = root.find("jmx:Control", NS)
    head = root.find("ib:Head", NS)
    body = root.find("b:Body", NS)
    if control is None or head is None or body is None:
        raise ValueError("Control / Head / Body のどれかがない。警報の電文ではない可能性がある")

    meta = {
        # 管理部の Title は電文の種類名、ヘッダ部の Title は見出し
        # （例: 東京都暴風（雪）警報・注意報）
        "telegram_type": _text(control, "jmx:Title") or "",
        "title": _text(head, "ib:Title") or "",
        "office": _text(control, "jmx:PublishingOffice") or "",
        "report_datetime": _text(head, "ib:ReportDateTime") or "",
        "info_type": _text(head, "ib:InfoType") or "",
    }

    rows: list[WarningRow] = []
    for warning in body.findall("b:Warning", NS):
        wtype = warning.get("type", "")
        level = next((v for k, v in LEVELS.items() if wtype.endswith(f"（{k}）")), None)
        if level is None:
            raise ValueError(f"想定していない Warning@type: {wtype}")
        for item in warning.findall("b:Item", NS):
            area = item.find("b:Area", NS)
            item_meta = {
                "level": level,
                "area_code": _text(area, "b:Code") or "",
                "area_name": _text(area, "b:Name") or "",
                "change_status": _text(item, "b:ChangeStatus"),
                "full_status": _text(item, "b:FullStatus"),
            }
            for kind in item.findall("b:Kind", NS):
                rows.append(
                    WarningRow(
                        **meta,
                        **item_meta,
                        kind_code=_text(kind, "b:Code"),
                        kind_name=_text(kind, "b:Name"),
                        status=_text(kind, "b:Status") or "",
                        kind_datetime=_text(kind, "b:DateTime"),
                        last_kind_name=_text(kind, "b:LastKind/b:Name"),
                    )
                )
    return rows


def to_records(rows: list[WarningRow]) -> list[dict]:
    return [{**asdict(r), "active": r.active} for r in rows]
