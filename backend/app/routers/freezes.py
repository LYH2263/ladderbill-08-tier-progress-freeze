from fastapi import APIRouter, HTTPException

from app.schemas.billing import FreezeRequest, UnfreezeRequest
from app.services.billing_service import BillingService

router = APIRouter(tags=["freeze"])


@router.get("/accounts/{account_id}/year-progress")
def get_year_progress(account_id: int, year: int | None = None):
    with BillingService() as svc:
        try:
            return svc.year_progress(account_id, year)
        except ValueError as exc:
            raise HTTPException(404, str(exc))


@router.post("/accounts/{account_id}/freeze")
def freeze_account(account_id: int, body: FreezeRequest | None = None):
    with BillingService() as svc:
        try:
            year = body.year if body is not None else None
            note = body.note if body is not None else None
            return svc.freeze_year(account_id, year, note)
        except ValueError as exc:
            msg = str(exc)
            raise HTTPException(409 if "already frozen" in msg else 404, msg)


@router.post("/accounts/{account_id}/unfreeze")
def unfreeze_account(account_id: int, body: UnfreezeRequest | None = None):
    with BillingService() as svc:
        try:
            year = body.year if body is not None else None
            return svc.unfreeze_year(account_id, year)
        except ValueError as exc:
            raise HTTPException(409, str(exc))


@router.get("/accounts/{account_id}/recompute")
def recompute_account(account_id: int, year: int | None = None):
    with BillingService() as svc:
        try:
            return svc.recompute_year(account_id, year)
        except ValueError as exc:
            raise HTTPException(404, str(exc))
