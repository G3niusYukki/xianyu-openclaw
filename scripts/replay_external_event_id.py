from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from src.modules.orders.service import OrderFulfillmentService


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="xy-p0-04-") as td:
        db_path = Path(td) / "orders.db"
        service = OrderFulfillmentService(db_path=str(db_path))

        payload = {
            "order_id": "ord_xy_p0_04",
            "status": "已付款",
            "external_event_id": "evt_xy_p0_04_001",
            "item_type": "virtual",
            "session_id": "sess_xy_p0_04",
        }

        first = service.process_callback(payload, auto_deliver=False)
        second = service.process_callback(payload, auto_deliver=False)

        trace = service.trace_order("ord_xy_p0_04")
        status_sync_count = sum(1 for ev in trace["events"] if ev["event_type"] == "status_sync")

        with sqlite3.connect(db_path) as conn:
            dedup_count = conn.execute("SELECT COUNT(1) FROM order_callback_dedup").fetchone()[0]

        print("[XY-P0-04] first callback result:")
        print(json.dumps(first, ensure_ascii=False, indent=2))
        print("[XY-P0-04] second callback result (replay):")
        print(json.dumps(second, ensure_ascii=False, indent=2))
        print(f"[XY-P0-04] status_sync_count={status_sync_count}")
        print(f"[XY-P0-04] order_callback_dedup rows={dedup_count}")


if __name__ == "__main__":
    main()
