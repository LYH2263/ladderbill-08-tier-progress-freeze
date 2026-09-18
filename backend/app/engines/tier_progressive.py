"""Progressive tier electricity: each kWh charged at its band price."""

from app.engines.helpers import kwh_qty, money


def calc_bill(kwh: float, tiers: list[dict], peak_factor: float = 1.0, base_kwh: float = 0.0) -> dict:
    """tiers: [{up_to, price}] last up_to may be None for open end.

    base_kwh: already-accumulated energy within the natural year before this
    run. Segment coordinates (from_kwh/to_kwh) are then expressed in the
    yearly cumulative frame so the ladder continues from a freeze point.
    """
    remain = float(kwh)
    if remain < 0:
        raise ValueError("kwh must be non-negative")
    pos = float(base_kwh)
    if pos < 0:
        raise ValueError("base_kwh must be non-negative")
    segments = []
    total = 0.0
    pf = float(peak_factor)
    for t in tiers:
        up = t.get("up_to")
        price = float(t["price"]) * pf
        if up is None:
            qty = remain
        else:
            available = float(up) - pos
            qty = min(remain, max(0.0, available))
        if qty > 1e-9:
            amount = money(qty * price)
            segments.append(
                {
                    "from_kwh": kwh_qty(pos),
                    "to_kwh": kwh_qty(pos + qty),
                    "qty": kwh_qty(qty),
                    "price": round(price, 4),
                    "amount": amount,
                }
            )
            total += amount
            remain -= qty
            pos += qty
        if remain <= 1e-9:
            break
    return {
        "kwh": kwh_qty(kwh),
        "peak_factor": pf,
        "base_kwh": kwh_qty(base_kwh),
        "total": money(total),
        "segments": segments,
    }
