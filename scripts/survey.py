"""長期フィード4本と、種類ごとの電文1通ずつから、防災情報XMLの概要を集計する。

    python -X utf8 scripts/survey.py data/survey  > data/survey_summary.json
"""
import collections
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ATOM = {"a": "http://www.w3.org/2005/Atom"}
FEEDS = ["regular_l", "extra_l", "eqvol_l", "other_l"]


def feed_stats():
    out = {}
    for f in FEEDS:
        root = ET.fromstring(urllib.request.urlopen(
            f"https://www.data.jma.go.jp/developer/xml/feed/{f}.xml").read())
        es = root.findall("a:entry", ATOM)
        times = [datetime.fromisoformat(e.find("a:updated", ATOM).text.replace("Z", "+00:00")) for e in es]
        span_h = (max(times) - min(times)).total_seconds() / 3600
        per = collections.defaultdict(lambda: {"count": 0, "authors": set(), "title": None})
        for e in es:
            code = e.find("a:id", ATOM).text.split("_")[2]
            p = per[code]
            p["count"] += 1
            p["title"] = e.find("a:title", ATOM).text
            p["authors"].add(e.find("a:author/a:name", ATOM).text)
        out[f] = {
            "entries": len(es), "oldest": min(times).isoformat(), "newest": max(times).isoformat(),
            "span_hours": round(span_h, 1),
            "types": {k: {"title": v["title"], "count": v["count"], "authors": len(v["authors"]),
                          "per_day": round(v["count"] / span_h * 24, 1)} for k, v in per.items()},
        }
    return out


def local(tag):
    return tag.rsplit("}", 1)[-1]


def inspect(path: Path):
    root = ET.parse(path).getroot()
    code_types = collections.Counter()
    geom = collections.Counter()
    coords = 0
    areas = 0
    stations = 0
    text_chars = 0
    for el in root.iter():
        n = local(el.tag)
        if n == "Area":
            areas += 1
        if n == "Station":
            stations += 1
        ct = el.get("codeType")
        if ct:
            code_types[ct] += sum(1 for c in el.iter() if local(c.tag) in ("Code", "Area", "Station"))
        elif n == "Code" and el.get("type"):
            code_types[el.get("type")] += 1
        if el.tag.startswith("{http://xml.kishou.go.jp/jmaxml1/elementBasis1/}") and (el.text or "").strip():
            geom[n + ("/" + el.get("type") if el.get("type") else "")] += 1
        if n == "Coordinate" and (el.text or "").strip():
            coords += 1
        if n in ("Text", "Comment", "Headline") or n.endswith("Text"):
            text_chars += len("".join(el.itertext()).strip())
    head = next(e for e in root if local(e.tag) == "Head")
    info_types = sorted({el.get("type") for el in head.iter() if local(el.tag) == "Information" and el.get("type")})
    return {
        "bytes": path.stat().st_size,
        "areas": areas, "stations": stations, "coordinates": coords, "text_chars": text_chars,
        "code_types": dict(code_types), "geom": {k: v for k, v in geom.items() if k.split("/")[0] in ("Coordinate", "Line", "Polygon", "Circle", "Point")}, "head_information_types": info_types,
    }


def main(sample_dir):
    feeds = feed_stats()
    samples = {}
    for p in sorted(Path(sample_dir).glob("*.xml")):
        code = p.name.split("_")[2]
        try:
            samples[code] = {"file": p.name, **inspect(p)}
        except ET.ParseError as e:
            samples[code] = {"file": p.name, "error": str(e)}
    json.dump({"feeds": feeds, "samples": samples}, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
