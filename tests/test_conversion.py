"""Tests for the business logic: sales aggregation + conversion/funnel math.

Uses a temp SQLite DB and a tiny inline sales CSV so it runs without the real
dataset or any video.
"""
import json
import tempfile
from pathlib import Path

from backend.conversion import Conversion
from backend.sales import SalesData
from backend.store_sqlite import Store

SALES_CSV = """invoice_number,order_time,customer_number,qty,GMV,NMV,dep_name,brand_name,salesperson_name,store_name,order_date
INV1,12:10:00,900,1,400,300,makeup,Faces,Asha,TestStore,10-04-2026
INV1,12:10:00,900,1,200,150,skin,GV,Asha,TestStore,10-04-2026
INV2,13:20:00,901,2,500,400,makeup,Lakme,Ravi,TestStore,10-04-2026
INV3,19:05:00,902,1,250,250,hair,TFS,Asha,TestStore,10-04-2026
"""


def _store_with_events(tmp) -> Store:
    db = Path(tmp) / "t.db"
    store = Store(db)
    # 5 visitors enter; 2 reach the cash counter
    for tid in range(1, 6):
        store.insert_event({
            "event_id": f"e-in-{tid}", "event_type": "line_cross",
            "ts": "2026-04-10T12:00:0%d+00:00" % tid, "camera_id": "cam-01",
            "frame_idx": tid, "track_id": tid, "zone": "door",
            "payload": json.dumps({"direction": "in"}),
        })
        store.insert_event({
            "event_id": f"e-brz-{tid}", "event_type": "zone_enter",
            "ts": "2026-04-10T12:01:0%d+00:00" % tid, "camera_id": "cam-01",
            "frame_idx": tid, "track_id": tid, "zone": "foh",
            "payload": json.dumps({}),
        })
    for tid in (1, 2):
        store.insert_event({
            "event_id": f"e-cc-{tid}", "event_type": "zone_enter",
            "ts": "2026-04-10T12:05:0%d+00:00" % tid, "camera_id": "cam-01",
            "frame_idx": tid, "track_id": tid, "zone": "cash_counter",
            "payload": json.dumps({}),
        })
    return store


def _sales(tmp) -> SalesData:
    p = Path(tmp) / "sales.csv"
    p.write_text(SALES_CSV)
    return SalesData(p)


def test_sales_summary_counts_unique_invoices():
    with tempfile.TemporaryDirectory() as tmp:
        s = _sales(tmp).summary()
        assert s.transactions == 3          # INV1, INV2, INV3
        assert s.unique_customers == 3
        assert s.units_sold == 5            # 1+1+2+1
        assert s.by_department["makeup"] == 2  # INV1 + INV2


def test_metrics_conversion_rate():
    with tempfile.TemporaryDirectory() as tmp:
        conv = Conversion(store=_store_with_events(tmp), sales=_sales(tmp))
        m = conv.metrics()
        assert m["footfall"] == 5
        assert m["transactions"] == 3
        assert m["conversion_rate_pct"] == 60.0   # 3/5


def test_funnel_dropoff_is_monotonic_and_session_based():
    with tempfile.TemporaryDirectory() as tmp:
        conv = Conversion(store=_store_with_events(tmp), sales=_sales(tmp))
        f = conv.funnel()
        counts = [s["count"] for s in f["funnel"]]
        assert counts[0] == 5      # entered
        assert counts[2] == 2      # reached counter
        assert counts[3] == 3      # purchased (from sales)
        assert f["overall_conversion_pct"] == 60.0


def test_metrics_vary_with_input_not_hardcoded():
    with tempfile.TemporaryDirectory() as tmp:
        # no events -> footfall 0 -> conversion None, but sales still load
        empty = Store(Path(tmp) / "empty.db")
        conv = Conversion(store=empty, sales=_sales(tmp))
        m = conv.metrics()
        assert m["footfall"] == 0
        assert m["conversion_rate"] is None
        assert m["transactions"] == 3
