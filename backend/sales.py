"""Sales / POS integration — the business side of 'Store Intelligence'.

The challenge's core metric is STORE CONVERSION RATE = transactions / footfall.
Footfall comes from the CCTV pipeline (people entering). Transactions come from
the POS sales CSV (one transaction == one unique invoice_number).

This module loads the Purplle store sales export and computes:
  - transactions (unique invoices), unique customers, units, revenue
  - hourly transaction buckets (to align with hourly footfall)
  - department / brand / salesperson breakdowns (zone-level conversion context)

Kept dependency-free (stdlib csv) so it runs in lite mode.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SALES = Path("data/sales/brigade_bangalore_2026-04-10.csv")


def _to_float(x: str) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class SalesSummary:
    transactions: int = 0
    unique_customers: int = 0
    units_sold: int = 0
    gross_revenue: float = 0.0
    net_revenue: float = 0.0
    by_hour: dict[int, int] = field(default_factory=dict)
    by_department: dict[str, int] = field(default_factory=dict)
    by_brand: dict[str, int] = field(default_factory=dict)
    by_salesperson: dict[str, int] = field(default_factory=dict)
    store_name: str = ""
    date: str = ""


class SalesData:
    """Loads + aggregates the POS CSV. Recomputed from the file, never hardcoded."""

    def __init__(self, path: str | Path = DEFAULT_SALES) -> None:
        self.path = Path(path)
        self._rows: list[dict] = []
        if self.path.exists():
            with open(self.path, encoding="utf-8", errors="replace") as f:
                self._rows = list(csv.DictReader(f))

    @property
    def available(self) -> bool:
        return bool(self._rows)

    def summary(self) -> SalesSummary:
        s = SalesSummary()
        if not self._rows:
            return s

        invoices: dict[str, str] = {}          # invoice -> order_time
        customers: set[str] = set()
        by_dep: dict[str, set[str]] = defaultdict(set)   # dep -> invoices
        by_brand: dict[str, set[str]] = defaultdict(set)
        by_sp: dict[str, set[str]] = defaultdict(set)

        for r in self._rows:
            inv = (r.get("invoice_number") or "").strip()
            if not inv:
                continue
            invoices.setdefault(inv, (r.get("order_time") or "00:00:00"))
            cust = (r.get("customer_number") or "").strip()
            if cust:
                customers.add(cust)
            s.units_sold += int(_to_float(r.get("qty", "0")))
            s.gross_revenue += _to_float(r.get("GMV", "0"))
            s.net_revenue += _to_float(r.get("NMV", "0"))
            if r.get("dep_name"):
                by_dep[r["dep_name"]].add(inv)
            if r.get("brand_name"):
                by_brand[r["brand_name"]].add(inv)
            if r.get("salesperson_name"):
                by_sp[r["salesperson_name"].strip()].add(inv)

        s.transactions = len(invoices)
        s.unique_customers = len(customers)
        s.store_name = (self._rows[0].get("store_name") or "").strip()
        s.date = (self._rows[0].get("order_date") or "").strip()

        by_hour: dict[int, int] = defaultdict(int)
        for inv, t in invoices.items():
            try:
                by_hour[int(t[:2])] += 1
            except (ValueError, IndexError):
                pass
        s.by_hour = dict(sorted(by_hour.items()))
        s.by_department = {k: len(v) for k, v in sorted(by_dep.items(), key=lambda x: -len(x[1]))}
        s.by_brand = {k: len(v) for k, v in sorted(by_brand.items(), key=lambda x: -len(x[1]))}
        s.by_salesperson = {k: len(v) for k, v in sorted(by_sp.items(), key=lambda x: -len(x[1]))}
        return s
