import pytest

from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill

TIERS = [{"up_to": 180, "price": 0.52}, {"up_to": 260, "price": 0.62}, {"up_to": None, "price": 0.82}]


def test_tier_first_band_only():
    r = calc_bill(120, TIERS, 1.0)
    assert r["total"] == 62.40
    assert len(r["segments"]) == 1


def test_tier_three_bands():
    r = calc_bill(400, TIERS, 1.0)
    assert r["total"] == 258.00
    assert len(r["segments"]) == 3


def test_peak_factor_multiplies_prices():
    plain = calc_bill(400, TIERS, 1.0)
    peak = calc_bill(400, TIERS, 1.2)
    assert peak["total"] == 309.60
    assert peak["total"] > plain["total"]


def test_compare_delta():
    c = compare_plain_vs_peak(400, TIERS, 1.2)
    assert c["plain_total"] == 258.00
    assert c["peak_total"] == 309.60
    assert c["delta"] == 51.60


def test_negative_kwh_raises():
    with pytest.raises(ValueError):
        calc_bill(-1, TIERS, 1.0)


def test_start_kwh_uses_absolute_year_coordinates():
    # 年累计已到 120，再算 100：60 在第一档(120->180)，40 在第二档(180->220)
    r = calc_bill(100, TIERS, 1.0, start_kwh=120)
    assert r["start_kwh"] == 120
    assert [s["from_kwh"] for s in r["segments"]] == [120.0, 180.0]
    assert [s["to_kwh"] for s in r["segments"]] == [180.0, 220.0]
    assert r["total"] == 60 * 0.52 + 40 * 0.62


def test_start_kwh_in_top_band():
    # 已越过两档，新电量全部落在开放档
    r = calc_bill(100, TIERS, 1.0, start_kwh=300)
    assert len(r["segments"]) == 1
    assert r["segments"][0]["from_kwh"] == 300.0
    assert r["segments"][0]["to_kwh"] == 400.0
    assert r["total"] == 82.0


def test_default_start_kwh_matches_legacy():
    legacy = calc_bill(400, TIERS, 1.2)
    assert legacy["start_kwh"] == 0
    assert legacy["total"] == 309.60
    assert legacy["segments"][0]["from_kwh"] == 0.0


def test_negative_start_kwh_raises():
    with pytest.raises(ValueError):
        calc_bill(10, TIERS, 1.0, start_kwh=-1)
