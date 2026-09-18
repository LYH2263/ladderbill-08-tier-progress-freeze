import pytest

from app import seed
from app.db import connect
from app.repositories import accounts as accounts_repo
from app.services.billing_service import BillingService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.DB_PATH", tmp_path / "test.db")
    seed.init_db()
    with BillingService() as service:
        conn = connect()
        cur = conn.execute("INSERT INTO accounts(name, meter_no, note) VALUES ('测试户','T-1','冻结测试')")
        conn.commit()
        service.account_id = int(cur.lastrowid)
        conn.close()
        yield service


def _persist(service, kwh, peak=False):
    return service.run_bill(kwh, peak, service.account_id, persist=True)


def test_annual_accumulates_persisted_bills(svc):
    _persist(svc, 100)
    _persist(svc, 50)
    status = svc.annual_status(svc.account_id)
    assert status["accumulated_kwh"] == 150
    assert status["start_kwh"] == 150
    assert status["frozen"] is False


def test_verify_matches_run_details(svc):
    _persist(svc, 100)
    _persist(svc, 70)
    report = svc.verify_annual(svc.account_id)
    assert report["consistent"] is True
    assert report["run_count"] == 2
    assert report["detail_total_kwh"] == 170
    assert report["accumulated_kwh"] == 170


def test_freeze_then_bill_starts_at_freeze_point(svc):
    _persist(svc, 100)
    frozen = svc.freeze(svc.account_id)
    assert frozen["frozen"] is True
    assert frozen["freeze_point"]["frozen_kwh"] == 100

    r = _persist(svc, 100)
    # live accumulation moves on, but tier progression restarts at the freeze point
    assert r["annual"]["accumulated_kwh"] == 200
    assert r["annual"]["start_kwh"] == 100
    assert r["annual"]["added_kwh"] == 100
    assert r["base_kwh"] == 100
    # 80 kWh in band 1 (100->180), 20 in band 2 (180->200)
    assert r["segments"][0]["from_kwh"] == 100
    assert r["segments"][0]["to_kwh"] == 180
    assert r["segments"][-1]["to_kwh"] == 200
    assert r["total"] == round(80 * 0.52 + 20 * 0.62, 2)

    status = svc.annual_status(svc.account_id)
    assert status["start_kwh"] == 100
    assert status["freeze_point"]["frozen_kwh"] == 100


def test_unfreeze_restores_live_accumulation_keeps_history(svc):
    _persist(svc, 100)
    svc.freeze(svc.account_id)
    _persist(svc, 100)
    svc.unfreeze(svc.account_id)

    status = svc.annual_status(svc.account_id)
    assert status["frozen"] is False
    assert status["freeze_point"] is None
    assert status["accumulated_kwh"] == 200
    assert status["start_kwh"] == 200

    # next bill follows live accumulation
    r = _persist(svc, 100)
    assert r["base_kwh"] == 200
    assert r["segments"][0]["from_kwh"] == 200

    # freeze record remains queryable
    assert len(status["history"]) == 1
    assert status["history"][0]["frozen_kwh"] == 100
    assert status["history"][0]["unfrozen_at"] is not None


def test_unfreeze_without_active_freeze_returns_none(svc):
    assert svc.unfreeze(svc.account_id) is None


def test_year_filtering_isolates_accumulation(svc):
    _persist(svc, 100)
    conn = connect()
    # back-date a bill run to a previous natural year
    conn.execute(
        "INSERT INTO calc_runs(kind, account_id, input_json, result_json, created_at) "
        "VALUES ('bill',?,?,?,?)",
        (
            svc.account_id,
            '{"kwh": 999}',
            '{"kwh": 999}',
            "2000-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()
    status = svc.annual_status(svc.account_id)
    assert status["accumulated_kwh"] == 100
    report = svc.verify_annual(svc.account_id, year=2000)
    assert report["accumulated_kwh"] == 999
    assert report["consistent"] is True
