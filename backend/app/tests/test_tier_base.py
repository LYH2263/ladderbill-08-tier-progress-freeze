import pytest

from app.engines.tier_progressive import calc_bill

TIERS = [{"up_to": 180, "price": 0.52}, {"up_to": 260, "price": 0.62}, {"up_to": None, "price": 0.82}]


def test_base_zero_keeps_legacy_coordinates():
    r = calc_bill(120, TIERS, 1.0, base_kwh=0)
    assert r["base_kwh"] == 0
    assert r["segments"][0]["from_kwh"] == 0
    assert r["segments"][0]["to_kwh"] == 120


def test_segments_continue_from_freeze_point():
    # 150 already accumulated this year: 30 lands in band 1, 70 in band 2
    r = calc_bill(100, TIERS, 1.0, base_kwh=150)
    assert r["total"] == round(30 * 0.52 + 70 * 0.62, 2)
    assert r["segments"][0]["from_kwh"] == 150
    assert r["segments"][0]["to_kwh"] == 180
    assert r["segments"][-1]["to_kwh"] == 250


def test_base_past_all_bands_uses_open_price():
    r = calc_bill(50, TIERS, 1.0, base_kwh=300)
    assert r["total"] == round(50 * 0.82, 2)
    assert r["segments"][0]["from_kwh"] == 300


def test_negative_base_raises():
    with pytest.raises(ValueError):
        calc_bill(10, TIERS, 1.0, base_kwh=-1)
