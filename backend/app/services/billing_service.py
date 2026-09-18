from datetime import datetime, timezone

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.repositories import accounts as accounts_repo
from app.repositories import freezes as freezes_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo

EPS = 1e-6


def current_year() -> int:
    return datetime.now(timezone.utc).year


class BillingService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def list_accounts(self):
        return accounts_repo.list_all(self._conn)

    def get_account(self, account_id: int):
        return accounts_repo.get(self._conn, account_id)

    def list_tiers(self):
        return tiers_repo.list_ordered(self._conn)

    def list_readings(self):
        return readings_repo.list_all(self._conn)

    def readings_for_account(self, account_id: int):
        return readings_repo.for_account(self._conn, account_id)

    def settings_map(self):
        return settings_repo.get_map(self._conn)

    # ----- yearly accumulation / freeze ---------------------------------

    def annual_status(self, account_id: int, year: int | None = None) -> dict:
        """Yearly accumulated billed energy plus freeze state.

        accumulated_kwh is always the live sum of persisted bill runs in the
        natural year. While frozen, tier progression restarts from the freeze
        point (start_kwh); after unfreezing it follows the live accumulation.
        """
        year = year or current_year()
        accumulated = runs_repo.yearly_billed_kwh(self._conn, account_id, year)
        point = freezes_repo.active(self._conn, account_id, year)
        start_kwh = float(point["frozen_kwh"]) if point else accumulated
        return {
            "year": year,
            "accumulated_kwh": accumulated,
            "frozen": point is not None,
            "freeze_point": _freeze_point(point),
            "start_kwh": round(start_kwh, 3),
            "history": freezes_repo.list_for_year(self._conn, account_id, year),
        }

    def freeze(self, account_id: int, year: int | None = None, note: str | None = None) -> dict:
        year = year or current_year()
        accumulated = runs_repo.yearly_billed_kwh(self._conn, account_id, year)
        freezes_repo.create(self._conn, account_id, year, accumulated, note)
        return self.annual_status(account_id, year)

    def unfreeze(self, account_id: int, year: int | None = None) -> dict | None:
        year = year or current_year()
        if not freezes_repo.active(self._conn, account_id, year):
            return None
        freezes_repo.unfreeze(self._conn, account_id, year)
        return self.annual_status(account_id, year)

    def verify_annual(self, account_id: int, year: int | None = None) -> dict:
        """Recompute yearly accumulation from run details and cross-check."""
        year = year or current_year()
        accumulated = runs_repo.yearly_billed_kwh(self._conn, account_id, year)
        details = runs_repo.yearly_bill_details(self._conn, account_id, year)
        detail_total = round(sum(float(d["kwh"] or 0.0) for d in details), 3)
        point = freezes_repo.active(self._conn, account_id, year)
        return {
            "year": year,
            "accumulated_kwh": accumulated,
            "detail_total_kwh": detail_total,
            "run_count": len(details),
            "consistent": abs(accumulated - detail_total) < EPS,
            "frozen": point is not None,
            "freeze_point": _freeze_point(point),
            "details": [
                {
                    "run_id": d["run_id"],
                    "kwh": round(float(d["kwh"] or 0.0), 3),
                    "created_at": d["created_at"],
                }
                for d in details
            ],
        }

    # ----- calculations --------------------------------------------------

    def run_bill(self, kwh: float, peak: bool, account_id: int | None, persist: bool,
                 year: int | None = None):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0
        annual = None
        base_kwh = 0.0
        freeze_id = None
        run_year = year
        if account_id is not None:
            run_year = run_year or current_year()
            status = self.annual_status(account_id, run_year)
            base_kwh = status["start_kwh"]
            freeze_id = status["freeze_point"]["id"] if status["freeze_point"] else None
        result = calc_bill(kwh, tiers, factor, base_kwh=base_kwh)
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {
                    "kwh": kwh,
                    "peak": peak,
                    "account_id": account_id,
                    "year": run_year,
                    "base_kwh": base_kwh,
                    "freeze_id": freeze_id,
                },
                result,
                account_id,
            )
            if account_id is not None:
                annual = self.annual_status(account_id, run_year)
                annual["added_kwh"] = round(float(kwh), 3)
                annual["start_kwh"] = round(base_kwh, 3)
        elif account_id is not None:
            annual = status
            annual["added_kwh"] = round(float(kwh), 3)
        return {"run_id": run_id, **result, "annual": annual}

    def run_compare(self, kwh: float, persist: bool):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        result = compare_plain_vs_peak(kwh, tiers, pf)
        run_id = None
        if persist:
            run_id = runs_repo.insert(self._conn, "compare", {"kwh": kwh}, result, None)
        return {"run_id": run_id, **result}

    def list_history(self, limit: int = 50):
        return runs_repo.list_recent(self._conn, limit)

    def get_run(self, run_id: int):
        return runs_repo.get(self._conn, run_id)

    def dashboard_stats(self):
        accounts = accounts_repo.list_all(self._conn)
        readings = readings_repo.list_all(self._conn)
        clean = [a for a in accounts if "种子" not in a.get("name", "")]
        dirty = [a for a in accounts if "种子" in a.get("name", "")]
        return {
            "account_count": len(accounts),
            "reading_count": len(readings),
            "clean_accounts": len(clean),
            "dirty_accounts": len(dirty),
            "recent_runs": len(runs_repo.list_recent(self._conn, 5)),
        }


def _freeze_point(point: dict | None) -> dict | None:
    if not point:
        return None
    return {
        "id": point["id"],
        "year": point["year"],
        "frozen_kwh": round(float(point["frozen_kwh"]), 3),
        "frozen_at": point["frozen_at"],
        "note": point.get("note"),
    }
