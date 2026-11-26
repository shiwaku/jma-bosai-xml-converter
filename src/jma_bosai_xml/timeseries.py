"""MeteorologicalInfos / TimeSeriesInfo の入れ子を、縦長の表に平らにする。

時系列を持つ電文（府県天気予報 VPFD51、週間天気予報 VPFW50 など）は、
TimeDefines で時刻を定義し、値の要素が refID でその時刻を参照する。
このモジュールは電文の種類を問わず、refID を持つ値を1行ずつ取り出す。

1行 = 1つの場所（Area か Station）× 1つの項目 × 1つの時刻。値は文字列のまま返す。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

EB = "{http://xml.kishou.go.jp/jmaxml1/elementBasis1/}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el if _local(c.tag) == name), None)


def _child_text(el: ET.Element | None, name: str) -> str | None:
    if el is None:
        return None
    c = _child(el, name)
    return c.text.strip() if c is not None and c.text else None


@dataclass
class Value:
    section: str  # MeteorologicalInfos@type（区域予報、地点予報）
    place_kind: str  # Area / Station
    place_code: str
    place_name: str
    property_type: str  # Property/Type（天気、降水確率、３時間毎気温 など）
    element: str  # 値の要素名（Weather、Temperature など）
    value_type: str | None  # 値の要素の type 属性（天気予報用テロップ番号、朝の最低気温 など）
    unit: str | None
    time_id: str
    datetime: str | None
    duration: str | None
    time_name: str | None  # 今日、明日 など
    value: str | None
    condition: str | None  # 値の要素の condition 属性（値なしの理由など）


def parse(xml: bytes) -> list[Value]:
    root = ET.fromstring(xml)
    body = _child(root, "Body")
    if body is None:
        raise ValueError("Body がない")

    out: list[Value] = []
    for infos in body:
        if _local(infos.tag) != "MeteorologicalInfos":
            continue
        section = infos.get("type", "")
        for ts in infos:
            if _local(ts.tag) != "TimeSeriesInfo":
                continue
            times = {}
            defines = _child(ts, "TimeDefines")
            for d in defines if defines is not None else []:
                times[d.get("timeId")] = (
                    _child_text(d, "DateTime"),
                    _child_text(d, "Duration"),
                    _child_text(d, "Name"),
                )
            for item in ts:
                if _local(item.tag) != "Item":
                    continue
                place = _child(item, "Area")
                if place is None:
                    place = _child(item, "Station")
                if place is None:
                    continue
                for kind in item:
                    if _local(kind.tag) != "Kind":
                        continue
                    for prop in kind:
                        ptype = _child_text(prop, "Type") or ""
                        for el in prop.iter():
                            ref = el.get("refID")
                            if ref is None:
                                continue
                            dt, dur, name = times.get(ref, (None, None, None))
                            if el.tag.startswith(EB):
                                value = el.text.strip() if el.text else None
                            else:
                                # DetailForecast の WeatherForecastPart などは Sentence を値にする
                                value = _child_text(el, "Sentence")
                            out.append(
                                Value(
                                    section=section,
                                    place_kind=_local(place.tag),
                                    place_code=_child_text(place, "Code") or "",
                                    place_name=_child_text(place, "Name") or "",
                                    property_type=ptype,
                                    element=_local(el.tag),
                                    value_type=el.get("type"),
                                    unit=el.get("unit"),
                                    time_id=ref,
                                    datetime=dt,
                                    duration=dur,
                                    time_name=name,
                                    value=value,
                                    condition=el.get("condition"),
                                )
                            )
    return out
