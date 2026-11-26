from pathlib import Path

from jma_bosai_xml import warning

FIXTURE = Path(__file__).parent / "fixtures" / "20261126110334_0_VPWW58_130000.xml"


def rows():
    return warning.parse(FIXTURE.read_bytes())


def test_head_is_copied():
    r = rows()[0]
    assert r.telegram_type == "気象警報・注意報（Ｒ０６）（暴風）"
    assert r.title == "東京都暴風（雪）警報・注意報"
    assert r.office == "気象庁"
    assert r.report_datetime.startswith("2026-11-26T20:03")


def test_all_levels_are_parsed():
    levels = {r.level for r in rows()}
    assert levels == {"prefecture", "primary", "city_group", "city"}


def test_city_codes_are_7_digits_and_cover_tokyo():
    city = [r for r in rows() if r.level == "city"]
    codes = {r.area_code for r in city}
    assert len(codes) == 62
    assert all(len(c) == 7 for c in codes)
    assert "1310100" in codes  # 千代田区


def test_area_without_warning_has_empty_kind_and_is_inactive():
    none = [r for r in rows() if r.status == "発表警報・注意報はなし"]
    assert none
    assert all(r.kind_name is None and not r.active for r in none)


def test_lifted_warning_is_inactive_and_keeps_name():
    lifted = [r for r in rows() if r.status == "解除"]
    assert lifted
    assert all(not r.active and r.kind_name for r in lifted)
