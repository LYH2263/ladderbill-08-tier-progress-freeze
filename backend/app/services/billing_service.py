import json
from datetime import datetime, timezone

from app.db import connect
from app.engines.helpers import kwh_qty
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.repositories import accounts as accounts_repo
from app.repositories import freezes as freezes_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo


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

    # ---- 年累计 / 冻结 ----

    @staticmethod
    def current_year() -> int:
        return datetime.now(timezone.utc).year

    @staticmethod
    def _parse_ts(value: str) -> datetime:
        """兼容 ISO-8601(...T...+00:00) 与 SQLite datetime('now')('YYYY-MM-DD HH:MM:SS')。

        两者均为 UTC；naive 结果补上 UTC 时区。
        """
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def _bill_runs(self, account_id: int, year: int) -> list[dict]:
        """该户归属某自然年的计费运行，按 id 正序。

        年归属优先取落库时记录的 input_json.year，缺省回退 created_at 年份。
        """
        rows = runs_repo.bill_rows_for_account(self._conn, account_id)
        return [r for r in rows if self._run_year(r) == year]

    @classmethod
    def _run_year(cls, row: dict) -> int:
        try:
            payload = json.loads(row["input_json"])
            y = payload.get("year")
            if y is not None:
                return int(y)
        except (ValueError, TypeError):
            pass
        return int(str(row["created_at"])[:4])

    @staticmethod
    def _run_kwh(row: dict) -> float:
        try:
            payload = json.loads(row["input_json"])
            return float(payload.get("kwh", 0.0))
        except (ValueError, TypeError):
            return 0.0

    def year_kwh(self, account_id: int, year: int) -> float:
        """该年已落库运行净电量之和（年累计的唯一来源）。"""
        total = sum(self._run_kwh(r) for r in self._bill_runs(account_id, year))
        return kwh_qty(total)

    def _progress_snapshot(self, account_id: int, year: int):
        """返回 (年累计, 生效冻结点, 阶梯累进起点, 年内运行明细)。

        冻结态：档位进度被钉在冻结点——本年内每笔后续测算的分段起点
        始终为冻结点电量，新落库电量计入年累计但不推进档位；
        非冻结：起点 = 实时年累计（档位按年累计绝对坐标累进）。
        """
        rows = self._bill_runs(account_id, year)
        year_kwh = kwh_qty(sum(self._run_kwh(r) for r in rows))
        freeze = freezes_repo.active_freeze(self._conn, account_id, year)
        base = kwh_qty(float(freeze["frozen_kwh"])) if freeze else year_kwh
        return year_kwh, freeze, base, rows

    def _freeze_brief(self, freeze: dict | None) -> dict | None:
        if not freeze:
            return None
        return {
            "id": freeze["id"],
            "year": freeze["year"],
            "frozen_kwh": freeze["frozen_kwh"],
            "year_kwh": freeze["year_kwh"],
            "created_at": freeze["created_at"],
            "status": freeze["status"],
            "note": freeze.get("note"),
        }

    def year_progress(self, account_id: int, year: int | None = None) -> dict:
        year = year or self.current_year()
        account = accounts_repo.get(self._conn, account_id)
        if not account:
            raise ValueError("account not found")
        year_kwh, freeze, base, rows = self._progress_snapshot(account_id, year)
        return {
            "account_id": account_id,
            "year": year,
            "year_kwh": year_kwh,
            "run_count": len(rows),
            "tier_base_kwh": base,
            "frozen": freeze is not None,
            "freeze": self._freeze_brief(freeze),
            "freeze_points": [
                self._freeze_brief(f)
                for f in freezes_repo.list_for_account_year(self._conn, account_id, year)
            ],
            "runs": [
                {
                    "run_id": r["id"],
                    "kwh": kwh_qty(self._run_kwh(r)),
                    "created_at": r["created_at"],
                }
                for r in rows
            ],
        }

    def freeze_year(self, account_id: int, year: int | None = None, note: str | None = None) -> dict:
        year = year or self.current_year()
        account = accounts_repo.get(self._conn, account_id)
        if not account:
            raise ValueError("account not found")
        if freezes_repo.active_freeze(self._conn, account_id, year):
            raise ValueError(f"account {account_id} already frozen for {year}")
        year_kwh = self.year_kwh(account_id, year)
        freeze_id = freezes_repo.insert(
            self._conn,
            account_id,
            year,
            frozen_kwh=year_kwh,
            year_kwh=year_kwh,
            note=note,
        )
        freeze = freezes_repo.get(self._conn, freeze_id)
        return {
            "account_id": account_id,
            "year": year,
            "year_kwh": year_kwh,
            "frozen_kwh": year_kwh,
            "frozen_at": freeze["created_at"],
            "freeze": self._freeze_brief(freeze),
        }

    def unfreeze_year(self, account_id: int, year: int | None = None) -> dict:
        year = year or self.current_year()
        freeze = freezes_repo.active_freeze(self._conn, account_id, year)
        if not freeze:
            raise ValueError(f"no active freeze for account {account_id} in {year}")
        updated = freezes_repo.unfreeze(self._conn, freeze["id"])
        return {
            "account_id": account_id,
            "year": year,
            "year_kwh": self.year_kwh(account_id, year),
            "unfrozen_at": updated["unfrozen_at"],
            "freeze": self._freeze_brief(updated),
        }

    def recompute_year(self, account_id: int, year: int | None = None) -> dict:
        """重算校验：逐条运行明细求和，核对年累计及各冻结点快照。"""
        year = year or self.current_year()
        rows = self._bill_runs(account_id, year)
        details = [
            {"run_id": r["id"], "kwh": kwh_qty(self._run_kwh(r)), "created_at": r["created_at"]}
            for r in rows
        ]
        detail_sum = kwh_qty(sum(d["kwh"] for d in details))
        checks = []
        for f in freezes_repo.list_for_account_year(self._conn, account_id, year):
            frozen_at = self._parse_ts(f["created_at"])
            up_to = sum(
                self._run_kwh(r)
                for r in rows
                if self._parse_ts(r["created_at"]) <= frozen_at
            )
            up_to = kwh_qty(up_to)
            checks.append(
                {
                    "freeze_id": f["id"],
                    "status": f["status"],
                    "snapshot_year_kwh": kwh_qty(f["year_kwh"]),
                    "frozen_kwh": kwh_qty(f["frozen_kwh"]),
                    "runs_up_to_freeze": up_to,
                    "consistent": up_to == kwh_qty(f["year_kwh"])
                    and kwh_qty(f["frozen_kwh"]) == kwh_qty(f["year_kwh"]),
                }
            )
        return {
            "account_id": account_id,
            "year": year,
            "year_kwh": detail_sum,
            "run_count": len(rows),
            "details": details,
            "freeze_checks": checks,
            "consistent": all(c["consistent"] for c in checks),
        }

    # ---- 测算 ----

    def run_bill(self, kwh: float, peak: bool, account_id: int | None, persist: bool,
                 year: int | None = None):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0
        year = year or self.current_year()
        freeze = None
        stored_kwh = 0.0
        start_kwh = 0.0
        if account_id is not None:
            stored_kwh, freeze, start_kwh, _ = self._progress_snapshot(account_id, year)
        # 冻结态：分段以上一冻结点为起点（冻结后新增已叠加在 start_kwh）；
        # 非冻结：以实时年累计为起点。
        result = calc_bill(kwh, tiers, factor, start_kwh=start_kwh)
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {"kwh": kwh, "peak": peak, "account_id": account_id,
                 "year": year if account_id is not None else None},
                result,
                account_id,
            )
        year_kwh = kwh_qty(stored_kwh + (float(kwh) if persist else 0.0))
        projected_kwh = kwh_qty(stored_kwh + float(kwh))
        return {
            "run_id": run_id,
            **result,
            "account_id": account_id,
            "year": year if account_id is not None else None,
            "year_kwh": year_kwh,
            "projected_year_kwh": projected_kwh,
            "tier_base_kwh": kwh_qty(start_kwh),
            "segment_added_kwh": kwh_qty(kwh),
            "frozen": freeze is not None,
            "freeze": self._freeze_brief(freeze),
        }

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
