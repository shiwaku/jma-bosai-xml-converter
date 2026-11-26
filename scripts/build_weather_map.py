"""検証: 府県天気予報（R1）を全国分取得し、Web 地図用のデータにする。

    uv run python -X utf8 scripts/build_weather_map.py <区域GISのzip> <地点表json> <出力先>

- 定時の長期フィードから、発表官署ごとに最新の VPFD51 を取る（取得済みの電文は取りにいかない）
- 区域予報は一次細分区域の面に、地点予報はアメダス地点の点に付ける
- 出力: forecast_long.parquet（縦長の全データ）、areas.parquet / stations.parquet（GeoParquet）、
  weather_map.json（Web 地図用。形を簡略化し、値は電文のまま）
"""

from __future__ import annotations

import json
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Point, mapping

from jma_bosai_xml import fetch, timeseries

JGD2011 = "EPSG:6668"
SOURCE = (
    "気象庁防災情報XML 府県天気予報（Ｒ１）、予報区等GISデータ（一次細分区域等）、アメダス地点表"
)


def collect(cache: Path) -> pd.DataFrame:
    entries = fetch.latest_by_author(fetch.read_feed("regular_l"), "VPFD51")
    rows = []
    for e in entries:
        xml = fetch.fetch(e.url, cache)
        for order, v in enumerate(timeseries.parse(xml)):
            rows.append({**asdict(v), "office": e.author, "url": e.url, "order": order})
    return pd.DataFrame(rows)


def load_areas(zip_path: Path) -> gpd.GeoDataFrame:
    # 2019年版はファイル名が Shift_JIS、属性は UTF-8、.prj なし（JGD2011）
    shp = next(n for n in zipfile.ZipFile(zip_path).namelist() if n.endswith(".shp"))
    g = gpd.read_file(f"zip://{zip_path}!{shp}", encoding="utf-8").set_crs(JGD2011)
    return g[g.code.notna()]


def load_stations(path: Path) -> gpd.GeoDataFrame:
    table = json.loads(path.read_text(encoding="utf-8"))
    recs = []
    for code, s in table.items():
        lat = s["lat"][0] + s["lat"][1] / 60
        lon = s["lon"][0] + s["lon"][1] / 60
        recs.append({"code": code, "kjName": s["kjName"], "geometry": Point(lon, lat)})
    return gpd.GeoDataFrame(recs, crs=JGD2011)


def display_geometry(geom, min_area: float = 2e-4, tolerance: float = 0.01):
    """表示用の形。小さな島（約2km²未満）を除き、簡略化する。区域で最大の島は必ず残す。"""
    parts = list(getattr(geom, "geoms", [geom]))
    biggest = max(parts, key=lambda p: p.area)
    kept = [p for p in parts if p.area >= min_area or p is biggest]
    return MultiPolygon(kept).simplify(tolerance, preserve_topology=True)


def build(df: pd.DataFrame, areas: gpd.GeoDataFrame, amedas: gpd.GeoDataFrame) -> dict:
    area_df = df[df.place_kind == "Area"]
    st_df = df[df.place_kind == "Station"]

    # --- 区域: 日ごとの天気（テロップ番号つき）
    daily = area_df[area_df.property_type == "天気"].copy()
    daily["date"] = daily.datetime.str[:10]
    daily_w = daily[daily.element == "Weather"].set_index(["place_code", "date"]).value
    daily_c = daily[daily.element == "WeatherCode"].set_index(["place_code", "date"]).value
    daily_name = daily[daily.element == "Weather"].set_index(["place_code", "date"]).time_name

    # --- 区域: 3時間ごとの天気、6時間ごとの降水確率
    w3 = area_df[area_df.property_type == "３時間内卓越天気"]
    pop = area_df[area_df.property_type == "降水確率"]

    # --- 地点: 日ごとの最高・最低、3時間ごとの気温
    st_daily = st_df[
        st_df.property_type.isin(["日中の最高気温", "最高気温", "朝の最低気温"])
    ].copy()
    st_daily["date"] = st_daily.datetime.str[:10]
    t3 = st_df[st_df.property_type == "３時間毎気温"]

    dates = sorted(daily.date.unique())
    times3 = sorted(set(w3.datetime) | set(t3.datetime))

    feats = []
    simple = areas.copy()
    simple["geometry"] = simple.geometry.map(display_geometry)
    office = area_df.drop_duplicates("place_code").set_index("place_code").office
    # 官署ごとの代表区域（電文の最初の区域）。縮小表示ではこれだけアイコンを出す
    rep_areas = set(area_df.sort_values("order").groupby("office").place_code.first())
    for _, a in simple.iterrows():
        code = a.code
        if code not in office.index:
            continue
        aw3 = w3[w3.place_code == code].set_index("datetime").value.to_dict()
        apop = pop[pop.place_code == code].set_index("datetime").value.to_dict()
        rep = a.geometry.representative_point()
        feats.append(
            {
                "type": "Feature",
                "geometry": json.loads(json.dumps(mapping(a.geometry))),
                "properties": {
                    "code": code,
                    "name": a["name"],
                    "office": office[code],
                    "rep": code in rep_areas,
                    "label": [round(rep.x, 3), round(rep.y, 3)],
                    "daily": {
                        d: {
                            "name": daily_name.get((code, d)),
                            "weather": daily_w.get((code, d)),
                            "telop": daily_c.get((code, d)),
                        }
                        for d in dates
                        if (code, d) in daily_w.index
                    },
                    "w3": aw3,
                    "pop": apop,
                },
            }
        )

    reps = set(st_df.sort_values("order").groupby("office").place_code.first())
    pts = amedas.set_index("code")
    stations = []
    for code, g in st_df.groupby("place_code"):
        p = pts.loc[code].geometry
        dmax, dmin = {}, {}
        for _, r in st_daily[st_daily.place_code == code].iterrows():
            if r.property_type == "朝の最低気温":
                dmin[r.date] = r.value
            elif r.property_type == "日中の最高気温" or r.date not in dmax:
                dmax[r.date] = r.value
        stations.append(
            {
                "code": code,
                "name": g.place_name.iloc[0],
                "office": g.office.iloc[0],
                "rep": code in reps,
                "lon": round(p.x, 4),
                "lat": round(p.y, 4),
                "max": dmax,
                "min": dmin,
                "t3": t3[t3.place_code == code].set_index("datetime").value.to_dict(),
            }
        )

    return {
        "source": SOURCE,
        "report_from": None,
        "dates": dates,
        "times3": times3,
        "areas": {"type": "FeatureCollection", "features": feats},
        "stations": stations,
    }


def round_coords(obj):
    if isinstance(obj, float):
        return round(obj, 3)
    if isinstance(obj, list | tuple):
        return [round_coords(x) for x in obj]
    if isinstance(obj, dict):
        return {k: round_coords(v) if k == "coordinates" else v for k, v in obj.items()}
    return obj


def main(area_zip: Path, amedas_json: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    df = collect(Path("data/cache/xml"))
    df.to_parquet(out / "forecast_long.parquet")

    areas = load_areas(area_zip)
    amedas = load_stations(amedas_json)

    # GeoParquet（形は簡略化しない。値は縦長の表と結合して使う）
    area_codes = set(df[df.place_kind == "Area"].place_code)
    st_codes = set(df[df.place_kind == "Station"].place_code)
    areas[areas.code.isin(area_codes)].to_parquet(out / "areas.parquet")
    amedas[amedas.code.isin(st_codes)].to_parquet(out / "stations.parquet")

    data = build(df, areas, amedas)
    heads = df.drop_duplicates("url")
    data["telegrams"] = len(heads)
    data["urls"] = sorted(heads.url)
    # 電文の URL の先頭14桁は発表時刻（UTC）
    issued = pd.to_datetime(heads.url.str.extract(r"/(\d{14})_")[0], format="%Y%m%d%H%M%S")
    issued = issued.dt.tz_localize("UTC").dt.tz_convert("Asia/Tokyo")
    data["issued"] = [issued.min().isoformat(), issued.max().isoformat()]
    for f in data["areas"]["features"]:
        f["geometry"] = round_coords(f["geometry"])
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (out / "weather_map.json").write_text(text, encoding="utf-8")

    print(f"電文 {len(heads)} 通、行 {len(df)}")
    print(f"区域 {len(data['areas']['features'])}、地点 {len(data['stations'])}")
    print(f"日 {data['dates']}")
    print(f"3時間ごと {data['times3'][0]} 〜 {data['times3'][-1]}（{len(data['times3'])}）")
    for p in sorted(out.iterdir()):
        print(f"{p.name:24s} {p.stat().st_size / 1e6:7.2f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
