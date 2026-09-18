"""Progressive tier electricity: each kWh charged at its band price."""

from app.engines.helpers import kwh_qty, money


def calc_bill(
    kwh: float,
    tiers: list[dict],
    peak_factor: float = 1.0,
    start_kwh: float = 0.0,
) -> dict:
    """tiers: [{up_to, price}] last up_to may be None for open end.

    start_kwh: 年累计起点（如冻结点电量）。分段区间按年累计绝对坐标输出：
    例如 start_kwh=200、kwh=100 时，分段从 200 计到 300，
    阶梯档位仍按累计坐标累进。
    """
    remain = float(kwh)
    if remain < 0:
        raise ValueError("kwh must be non-negative")
    pos = float(start_kwh)
    if pos < 0:
        raise ValueError("start_kwh must be non-negative")
    segments = []
    total = 0.0
    lower = 0.0  # 当前档的年累计下界
    pf = float(peak_factor)
    for t in tiers:
        up = t.get("up_to")
        upper = None if up is None else float(up)
        price = float(t["price"]) * pf
        if upper is None or pos < upper:
            seg_start = max(pos, lower)
            if upper is None:
                qty = remain
            else:
                qty = min(remain, max(0.0, upper - seg_start))
            if qty > 1e-9:
                amount = money(qty * price)
                segments.append(
                    {
                        "from_kwh": kwh_qty(seg_start),
                        "to_kwh": kwh_qty(seg_start + qty),
                        "qty": kwh_qty(qty),
                        "price": round(price, 4),
                        "amount": amount,
                    }
                )
                total += amount
                remain -= qty
                pos = seg_start + qty
        if remain <= 1e-9:
            break
        if upper is not None:
            lower = upper
    return {
        "kwh": kwh_qty(kwh),
        "start_kwh": kwh_qty(float(start_kwh)),
        "peak_factor": pf,
        "total": money(total),
        "segments": segments,
    }
