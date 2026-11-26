from pathlib import Path

from jma_bosai_xml import timeseries

FIXTURE = Path(__file__).parent / "fixtures" / "20261126193534_0_VPFD51_130000.xml"


def values():
    return timeseries.parse(FIXTURE.read_bytes())


def test_sections_and_places():
    vs = values()
    assert {v.section for v in vs} == {"区域予報", "地点予報"}
    areas = {v.place_code for v in vs if v.place_kind == "Area"}
    stations = {v.place_code for v in vs if v.place_kind == "Station"}
    assert "130010" in areas  # 東京地方
    assert "44132" in stations  # 東京
    assert all(len(c) == 6 for c in areas)
    assert all(len(c) == 5 for c in stations)


def test_ref_id_is_resolved_to_datetime():
    vs = values()
    assert all(v.datetime for v in vs)
    pop = [v for v in vs if v.property_type == "降水確率"]
    assert pop and all(v.duration == "PT6H" for v in pop)


def test_daily_weather_has_text_and_telop_code():
    vs = [v for v in values() if v.place_code == "130010" and v.property_type == "天気"]
    weather = [v for v in vs if v.element == "Weather"]
    codes = [v for v in vs if v.element == "WeatherCode"]
    assert len(weather) == len(codes) >= 2
    assert all(c.value.isdigit() and len(c.value) == 3 for c in codes)
    assert weather[0].time_name == "今日"


def test_detail_forecast_sentence_is_kept():
    sentences = [v for v in values() if v.element == "WeatherForecastPart"]
    assert sentences and all(v.value for v in sentences)
