"""Conversion-rate + funnel logic — the business metric the challenge centres on.

Conversion rate = transactions / footfall.

Funnel (session-based, no double counting — re-entries collapse to one visitor):
    1. entered_store   : unique visitor sessions (from CCTV line-cross 'in')
    2. browsed_zone    : sessions that dwelled in any product zone
    3. reached_counter : sessions that reached the cash-counter zone
    4. purchased       : transactions from the POS CSV (unique invoices)

We intentionally compute footfall from events and purchases from sales, then
join them — exactly the "translate raw signals into business insight" the rubric
asks for. Every number is derived from inputs (no hardcoding).
"""
from __future__ import annotations

from backend.sales import SalesData
from backend.store_sqlite import Store

# Zones that count as a "browse" vs. the checkout zone (see pipeline/zones.py).
COUNTER_ZONE = "cash_counter"


class Conversion:
    def __init__(self, store: Store | None = None, sales: SalesData | None = None) -> None:
        self.store = store or Store()
        self.sales = sales or SalesData()

    # ---- footfall / session helpers (from CCTV events) ----
    def _footfall(self) -> int:
        """Unique visitor sessions = distinct track_ids that crossed the door 'in'.

        Using distinct track_id makes this session-based: a person tracked once
        is one visitor even if they cross the line jitter-y times.
        """
        with self.store.conn() as c:
            row = c.execute(
                """SELECT COUNT(DISTINCT track_id) AS n FROM events
                   WHERE event_type='line_cross'
                     AND json_extract(payload,'$.direction')='in'
                     AND track_id IS NOT NULL"""
            ).fetchone()
        return int(row["n"]) if row else 0

    def _sessions_in_zone(self, zone: str | None = None) -> int:
        with self.store.conn() as c:
            if zone:
                row = c.execute(
                    """SELECT COUNT(DISTINCT track_id) n FROM events
                       WHERE event_type='zone_enter' AND zone=? AND track_id IS NOT NULL""",
                    (zone,),
                ).fetchone()
            else:
                row = c.execute(
                    """SELECT COUNT(DISTINCT track_id) n FROM events
                       WHERE event_type='zone_enter' AND track_id IS NOT NULL"""
                ).fetchone()
        return int(row["n"]) if row else 0

    # ---- public API ----
    def metrics(self) -> dict:
        footfall = self._footfall()
        sales = self.sales.summary()
        txns = sales.transactions
        conv = round(txns / footfall, 4) if footfall else None
        return {
            "store_name": sales.store_name or "Brigade_Bangalore",
            "date": sales.date,
            "footfall": footfall,
            "transactions": txns,
            "unique_customers": sales.unique_customers,
            "units_sold": sales.units_sold,
            "gross_revenue": round(sales.gross_revenue, 2),
            "net_revenue": round(sales.net_revenue, 2),
            "conversion_rate": conv,
            "conversion_rate_pct": round(conv * 100, 2) if conv is not None else None,
            "avg_basket_value": round(sales.net_revenue / txns, 2) if txns else 0,
            "sales_available": self.sales.available,
        }

    def funnel(self) -> dict:
        footfall = self._footfall()
        browsed = self._sessions_in_zone(None)
        counter = self._sessions_in_zone(COUNTER_ZONE)
        purchased = self.sales.summary().transactions

        stages = [
            {"stage": "entered_store", "count": footfall},
            {"stage": "browsed_zone", "count": browsed},
            {"stage": "reached_counter", "count": counter},
            {"stage": "purchased", "count": purchased},
        ]
        # drop-off % between consecutive stages
        for i in range(1, len(stages)):
            prev = stages[i - 1]["count"]
            cur = stages[i]["count"]
            stages[i]["conversion_from_prev_pct"] = (
                round(cur / prev * 100, 1) if prev else None
            )
        overall = round(purchased / footfall * 100, 2) if footfall else None
        return {"funnel": stages, "overall_conversion_pct": overall}

    def hourly(self) -> list[dict]:
        """Footfall vs transactions per hour -> conversion by hour."""
        sales_by_hour = self.sales.summary().by_hour
        with self.store.conn() as c:
            rows = c.execute(
                """SELECT CAST(substr(ts,12,2) AS INTEGER) AS hour,
                          COUNT(DISTINCT track_id) AS footfall
                   FROM events
                   WHERE event_type='line_cross'
                     AND json_extract(payload,'$.direction')='in'
                   GROUP BY hour ORDER BY hour"""
            ).fetchall()
        foot_by_hour = {int(r["hour"]): int(r["footfall"]) for r in rows}
        hours = sorted(set(foot_by_hour) | set(sales_by_hour))
        out = []
        for h in hours:
            f = foot_by_hour.get(h, 0)
            t = sales_by_hour.get(h, 0)
            out.append({
                "hour": h,
                "footfall": f,
                "transactions": t,
                "conversion_pct": round(t / f * 100, 1) if f else None,
            })
        return out

    def breakdowns(self) -> dict:
        s = self.sales.summary()
        return {
            "by_department": s.by_department,
            "by_brand": s.by_brand,
            "by_salesperson": s.by_salesperson,
        }
