from fastapi import APIRouter, HTTPException

from app.schemas.billing import FreezeRequest, UnfreezeRequest
from app.services.billing_service import BillingService

router = APIRouter(tags=["freeze"])


def _require_account(svc: BillingService, account_id: int):
    if not svc.get_account(account_id):
        raise HTTPException(404, "account not found")


@router.get("/accounts/{account_id}/annual")
def get_annual(account_id: int, year: int | None = None):
    with BillingService() as svc:
        _require_account(svc, account_id)
        return svc.annual_status(account_id, year)


@router.post("/accounts/{account_id}/freeze")
def post_freeze(account_id: int, body: FreezeRequest | None = None):
    body = body or FreezeRequest()
    with BillingService() as svc:
        _require_account(svc, account_id)
        return svc.freeze(account_id, body.year, body.note)


@router.post("/accounts/{account_id}/unfreeze")
def post_unfreeze(account_id: int, body: UnfreezeRequest | None = None):
    body = body or UnfreezeRequest()
    with BillingService() as svc:
        _require_account(svc, account_id)
        status = svc.unfreeze(account_id, body.year)
        if status is None:
            raise HTTPException(409, "no active freeze point for this year")
        return status


@router.get("/accounts/{account_id}/annual/verify")
def get_annual_verify(account_id: int, year: int | None = None):
    with BillingService() as svc:
        _require_account(svc, account_id)
        return svc.verify_annual(account_id, year)
