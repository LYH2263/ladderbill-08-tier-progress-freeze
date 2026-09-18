"""年度档位进度冻结：年累计、冻结快照、解冻、重算校验、跨年隔离。"""

from pathlib import Path

import pytest

from app import seed
from app.db import DB_PATH
from app.services.billing_service import BillingService


def _reset_db():
    """每个用例使用全新的种子库。"""
    p = Path(DB_PATH)
    if p.exists():
        p.unlink()
    seed.init_db()


def test_year_kwh_is_sum_of_persisted_bill_runs():
    _reset_db()
    with BillingService() as svc:
        year = svc.current_year()
        # 种子数据中户 1 有一笔 120 的 bill 运行（归属当前 UTC 年）
        assert svc.year_kwh(1, year) == 120.0
        svc.run_bill(30, False, 1, persist=True)
        assert svc.year_kwh(1, year) == 150.0


def test_bill_segments_start_at_realtime_cumulative():
    _reset_db()
    with BillingService() as svc:
        r = svc.run_bill(100, False, 1, persist=True)
        # 起点即实时年累计 120；分段绝对坐标 120-180 / 180-220
        assert r["start_kwh"] == 120.0
        assert r["tier_base_kwh"] == 120.0
        assert r["year_kwh"] == 220.0
        assert r["segment_added_kwh"] == 100.0
        assert [s["from_kwh"] for s in r["segments"]] == [120.0, 180.0]
        assert r["frozen"] is False
        assert r["freeze"] is None


def test_freeze_writes_snapshot_and_pins_segment_start():
    _reset_db()
    with BillingService() as svc:
        year = svc.current_year()
        svc.run_bill(100, False, 1, persist=True)  # 年累计 220
        out = svc.freeze_year(1, note="年中冻结")
        assert out["frozen_kwh"] == 220.0
        assert out["year_kwh"] == 220.0
        assert out["frozen_at"]

        # 冻结后第一笔：分段起点=冻结点 220
        r1 = svc.run_bill(100, False, 1, persist=True)
        assert r1["frozen"] is True
        assert r1["freeze"]["frozen_kwh"] == 220.0
        assert r1["start_kwh"] == 220.0
        assert r1["segments"][0]["from_kwh"] == 220.0
        assert r1["year_kwh"] == 320.0
        assert r1["segment_added_kwh"] == 100.0

        # 冻结后第二笔：档位仍钉在冻结点，不从 320 起档
        r2 = svc.run_bill(50, False, 1, persist=True)
        assert r2["start_kwh"] == 220.0
        assert r2["segments"][0]["from_kwh"] == 220.0
        assert r2["year_kwh"] == 370.0

        prog = svc.year_progress(1, year)
        assert prog["frozen"] is True
        assert prog["tier_base_kwh"] == 220.0
        assert prog["year_kwh"] == 370.0
        assert prog["freeze"]["note"] == "年中冻结"


def test_unfreeze_restores_realtime_cumulative_keeps_record():
    _reset_db()
    with BillingService() as svc:
        year = svc.current_year()
        svc.run_bill(100, False, 1, persist=True)  # 220
        svc.freeze_year(1)
        svc.run_bill(100, False, 1, persist=True)  # 冻结期入库 -> 320
        svc.run_bill(50, False, 1, persist=True)   # 370
        out = svc.unfreeze_year(1)
        assert out["year_kwh"] == 370.0
        assert out["unfrozen_at"]

        # 解冻后下一笔恢复实时累计起点
        r = svc.run_bill(10, False, 1, persist=True)
        assert r["frozen"] is False
        assert r["start_kwh"] == 370.0
        assert r["year_kwh"] == 380.0

        # 冻结点记录仍可查（状态 unfrozen）
        prog = svc.year_progress(1, year)
        assert prog["frozen"] is False
        points = prog["freeze_points"]
        assert len(points) == 1
        assert points[0]["status"] == "unfrozen"
        assert points[0]["frozen_kwh"] == 220.0


def test_recompute_verifies_snapshot_against_run_details():
    _reset_db()
    with BillingService() as svc:
        svc.run_bill(100, False, 1, persist=True)  # 220
        svc.freeze_year(1)
        svc.run_bill(80, False, 1, persist=True)   # 冻结期 300
        rep = svc.recompute_year(1)
        assert rep["consistent"] is True
        assert rep["year_kwh"] == 300.0
        assert rep["run_count"] == len(rep["details"]) == 3
        check = rep["freeze_checks"][0]
        assert check["runs_up_to_freeze"] == 220.0
        assert check["snapshot_year_kwh"] == 220.0
        assert check["consistent"] is True


def test_double_freeze_and_unfreeze_without_freeze_raise():
    _reset_db()
    with BillingService() as svc:
        svc.freeze_year(1)
        with pytest.raises(ValueError):
            svc.freeze_year(1)
        svc.unfreeze_year(1)
        with pytest.raises(ValueError):
            svc.unfreeze_year(1)


def test_cross_year_isolation():
    _reset_db()
    with BillingService() as svc:
        cur = svc.current_year()
        before = svc.year_kwh(1, cur)
        # 显式归属上一年，不应计入本年累计
        svc.run_bill(999, False, 1, persist=True, year=cur - 1)
        assert svc.year_kwh(1, cur - 1) == 999.0
        assert svc.year_kwh(1, cur) == before
        # 本年冻结不影响往年
        svc.freeze_year(1, cur)
        assert svc.year_progress(1, cur - 1)["frozen"] is False


def test_freeze_unknown_account_raises():
    _reset_db()
    with BillingService() as svc:
        with pytest.raises(ValueError):
            svc.freeze_year(9999)
