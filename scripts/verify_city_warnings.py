"""検証: 警報の電文を、市町村等（気象警報等）の面に結合できるか。

    uv run python -X utf8 scripts/verify_city_warnings.py <電文XML> <GISのzip> <出力フォルダ>

出力
- municipalities.parquet : 市町村等（気象警報等）を GeoParquet にしたもの（EPSG:6668）
- warnings_city.parquet  : 市町村ごとに、発表中の警報・注意報をまとめて面に付けたもの
- warnings_city.geojson  : 同じ内容を、表示用に簡略化したもの
- warnings_city.png      : 確認用の地図
- 結合できなかったコードを、電文側・GIS側の両方から標準出力に出す
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

from jma_bosai_xml import warning

# 予報区等GISデータは JGD2011 の緯度経度（配布ページに記載。.prj は付いていない）
JGD2011 = "EPSG:6668"

# 表示用の区分。電文の値は変えず、名前の語尾から読み取るだけ
CATEGORY_ORDER = ["特別警報", "危険警報", "警報", "注意報"]


def category(name: str | None) -> str | None:
    if not isinstance(name, str):
        return None
    return next((c for c in CATEGORY_ORDER if name.endswith(c)), None)


def level(name: str | None) -> int | None:
    if not isinstance(name, str):
        return None
    m = re.match(r"レベル([０-９\d])", name)
    return (
        int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
        if m
        else None
    )


def load_municipalities(zip_path: Path) -> gpd.GeoDataFrame:
    shp = next(n for n in zipfile.ZipFile(zip_path).namelist() if n.endswith(".shp"))
    g = gpd.read_file(f"zip://{zip_path}!{shp}", encoding="utf-8")
    return g.set_crs(JGD2011)


def main(xml_path: Path, gis_zip: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    rows = warning.parse(xml_path.read_bytes())
    df = pd.DataFrame(warning.to_records(rows))
    city = df[df.level == "city"].copy()
    city["category"] = city.kind_name.map(category)
    city["warning_level"] = city.kind_name.map(level)
    head = rows[0]
    print(f"電文: {head.title} / {head.office} / {head.report_datetime}")
    print(f"市町村の行: {len(city)}  区域: {city.area_code.nunique()}")

    muni = load_municipalities(gis_zip)
    muni.to_parquet(out / "municipalities.parquet")
    # コードのない区域がある（北方領土、境界未定の埋立地、鳥島などの離島）。警報の発表区域ではない
    no_code = muni[muni.regioncode.isna()]
    print(f"GIS: {len(muni)} 区域（うちコードなし {len(no_code)}: {'、'.join(no_code.name)}）")

    # --- 結合できないコードを両方向から調べる
    tel_codes = set(city.area_code)
    gis_codes = set(muni.regioncode.dropna())
    only_tel = sorted(tel_codes - gis_codes)
    only_gis = sorted(gis_codes - tel_codes)
    print(f"電文にあってGISにない: {len(only_tel)}")
    for c in only_tel:
        print("   ", c, city.loc[city.area_code == c, "area_name"].iloc[0])
    print(f"GISにあって電文にない: {len(only_gis)}")
    for c in only_gis:
        print("   ", c, muni.loc[muni.regioncode == c, "regionname"].iloc[0])

    # 名前も合っているか（コードが同じでも区域の版が違うと名前がずれる）
    names = city.drop_duplicates("area_code").merge(
        muni[["regioncode", "name", "regionname"]], left_on="area_code", right_on="regioncode"
    )
    mismatch = names[(names.area_name != names.name) & (names.area_name != names.regionname)]
    print(f"コードは一致するが名前が違う: {len(mismatch)}")
    for _, r in mismatch.head(20).iterrows():
        print("   ", r.area_code, r.area_name, "<->", r.regionname)

    # --- 市町村ごとに1行にまとめる
    active = city[city.active]
    agg = (
        active.sort_values("warning_level", ascending=False, na_position="last")
        .groupby("area_code")
        .agg(
            kinds=("kind_name", "、".join),
            n_kinds=("kind_name", "size"),
            max_level=("warning_level", "max"),
            top_category=(
                "category",
                lambda s: min(s.dropna(), key=CATEGORY_ORDER.index, default=None),
            ),
        )
        .reset_index()
    )
    gdf = muni.merge(agg, left_on="regioncode", right_on="area_code", how="left").drop(
        columns="area_code"
    )
    gdf["n_kinds"] = gdf.n_kinds.fillna(0).astype(int)
    gdf["in_telegram"] = gdf.regioncode.isin(tel_codes)
    gdf["report_datetime"] = head.report_datetime
    gdf["source"] = f"気象庁防災情報XML {xml_path.name}"

    gdf.to_parquet(out / "warnings_city.parquet")
    simple = gdf.copy()
    simple["geometry"] = simple.geometry.simplify(0.002, preserve_topology=True)
    simple.to_file(out / "warnings_city.geojson", driver="GeoJSON")
    print("区分ごとの市町村数:", gdf.top_category.value_counts(dropna=False).to_dict())

    render(simple, out / "warnings_city.png", f"{head.title} {head.report_datetime}")
    for p in sorted(out.iterdir()):
        print(f"{p.name:28s} {p.stat().st_size / 1e6:8.1f} MB")


def render(gdf: gpd.GeoDataFrame, path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matplotlib.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "sans-serif"]
    colors = {"特別警報": "#0c0c0c", "危険警報": "#a0006e", "警報": "#e60000", "注意報": "#f2e700"}
    fig, ax = plt.subplots(figsize=(10, 11))
    gdf.plot(ax=ax, color="#e8e8e8", edgecolor="#bbbbbb", linewidth=0.1)
    for cat, color in reversed(colors.items()):
        sub = gdf[gdf.top_category == cat]
        if len(sub):
            sub.plot(ax=ax, color=color, edgecolor="#555555", linewidth=0.1, label=cat)
    missing = gdf[~gdf.in_telegram]
    if len(missing):
        missing.plot(ax=ax, color="none", edgecolor="#0060ff", linewidth=0.6, hatch="///")
    ax.set_xlim(122.5, 146.5)
    ax.set_ylim(24, 46)
    ax.set_axis_off()
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors.values()]
    ax.legend(handles, colors.keys(), loc="lower right", title="発表中の最も強いもの")
    ax.set_title(f"{title}\n出典: 気象庁防災情報XML・予報区等GISデータ", fontsize=10)
    fig.savefig(path, dpi=130, bbox_inches="tight")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
