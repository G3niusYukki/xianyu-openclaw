"""订单履约服务：下单状态识别、交付、售后、追溯。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient


class OrderFulfillmentService:
    """订单履约闭环最小实现。"""

    STATUS_MAP = {
        "待付款": "pending",
        "已付款": "paid",
        "待发货": "processing",
        "待处理": "processing",
        "待收货": "shipping",
        "已完成": "completed",
        "售后中": "after_sales",
        "退款中": "after_sales",
        "已关闭": "closed",
        "已取消": "closed",
    }
    OPEN_PLATFORM_STATUS_MAP = {
        11: "pending",
        12: "processing",
        21: "shipping",
        22: "completed",
        23: "after_sales",
        24: "closed",
    }

    AFTER_SALES_TEMPLATES = {
        "delay": "抱歉让您久等了，我这边已加急核查并优先处理，预计很快给您明确进度。",
        "refund": "已收到您的退款诉求，我会按平台流程尽快处理，请放心。",
        "quality": "非常抱歉给您带来不便，我这边会先登记问题并提供处理方案（补发/退款/协商）。",
    }
    _ORDER_ID_KEYS = ("order_id", "orderId", "order_no", "orderNo", "id")
    _RAW_STATUS_KEYS = ("raw_status", "status", "order_status", "orderStatus", "trade_status", "tradeStatus")
    _SESSION_ID_KEYS = ("session_id", "sessionId", "chat_id", "chatId", "biz_id", "bizId")
    _ITEM_TYPE_KEYS = ("item_type", "itemType", "goods_type", "goodsType")
    _EXTERNAL_EVENT_ID_KEYS = ("external_event_id", "externalEventId", "event_id", "eventId")

    def __init__(
        self,
        db_path: str = "data/orders.db",
        config: dict[str, Any] | None = None,
        shipping_api_client: OpenPlatformClient | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config or {}
        self.shipping_api_client = shipping_api_client or self._build_shipping_api_client()
        self._init_db()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    quote_snapshot_json TEXT,
                    item_type TEXT NOT NULL DEFAULT 'virtual',
                    status TEXT NOT NULL,
                    manual_takeover INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS order_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_order_events_order_time
                ON order_events(order_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS order_callback_dedup (
                    external_event_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _build_shipping_api_client(self) -> OpenPlatformClient | None:
        cfg = self.config.get("xianguanjia")
        if not isinstance(cfg, dict) or not cfg.get("enabled", False):
            return None
        app_key = str(cfg.get("app_key", "")).strip()
        app_secret = str(cfg.get("app_secret", "")).strip()
        if not app_key or not app_secret:
            return None
        return OpenPlatformClient(
            base_url=str(cfg.get("base_url", "https://open.goofish.pro")).strip(),
            app_key=app_key,
            app_secret=app_secret,
            timeout=float(cfg.get("timeout", 30.0)),
        )

    @staticmethod
    def _pick_first(payload: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
        for key in keys:
            if key in payload:
                value = str(payload.get(key) or "").strip()
                if value:
                    return value
        return default

    @classmethod
    def _extract_shipping_info(cls, payload: dict[str, Any], quote_snapshot: dict[str, Any]) -> dict[str, Any]:
        direct = payload.get("shipping_info")
        if isinstance(direct, dict):
            return dict(direct)

        nested = payload.get("shipping")
        if isinstance(nested, dict):
            return dict(nested)

        from_snapshot = quote_snapshot.get("shipping_info")
        if isinstance(from_snapshot, dict):
            return dict(from_snapshot)
        return {}

    @classmethod
    def _normalize_item_type(cls, value: str, shipping_info: dict[str, Any]) -> str:
        text = str(value or "").strip().lower()
        if text in {"physical", "实体", "实物"}:
            return "physical"
        if text in {"virtual", "虚拟", "卡密"}:
            return "virtual"
        if shipping_info:
            return "physical"
        return "virtual"

    def map_status(self, raw_status: str) -> str:
        if raw_status in self.STATUS_MAP:
            return self.STATUS_MAP[raw_status]

        text = (raw_status or "").lower()
        if any(k in text for k in ("pay", "付款")):
            return "paid"
        if any(k in text for k in ("ship", "发货", "物流")):
            return "shipping"
        if any(k in text for k in ("after", "售后", "退款")):
            return "after_sales"
        if any(k in text for k in ("complete", "完成", "签收")):
            return "completed"
        if any(k in text for k in ("cancel", "关闭")):
            return "closed"
        return "processing"

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except (TypeError, ValueError):
            return None

    @classmethod
    def map_open_platform_status(cls, raw_status: Any) -> str:
        code = cls._coerce_int(raw_status)
        if code is None or code not in cls.OPEN_PLATFORM_STATUS_MAP:
            raise ValueError(f"Unsupported open platform order_status: {raw_status}")
        return cls.OPEN_PLATFORM_STATUS_MAP[code]

    @staticmethod
    def _merge_quote_snapshot(
        base_snapshot: dict[str, Any] | None,
        incoming_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(base_snapshot or {})
        for key, value in (incoming_snapshot or {}).items():
            if key == "shipping_info" and isinstance(value, dict):
                current = merged.get("shipping_info")
                merged["shipping_info"] = {
                    **(current if isinstance(current, dict) else {}),
                    **value,
                }
                continue
            if key == "open_platform" and isinstance(value, dict):
                current = merged.get("open_platform")
                merged["open_platform"] = {
                    **(current if isinstance(current, dict) else {}),
                    **value,
                }
                continue
            merged[key] = value
        return merged

    @classmethod
    def _build_open_platform_snapshot(cls, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        goods = payload.get("goods")
        goods_snapshot = dict(goods) if isinstance(goods, dict) else {}

        shipping_info = {
            "order_no": str(payload.get("order_no") or "").strip(),
            "receiver_name": str(payload.get("receiver_name") or "").strip(),
            "receiver_mobile": str(payload.get("receiver_mobile") or "").strip(),
            "prov_name": str(payload.get("prov_name") or "").strip(),
            "city_name": str(payload.get("city_name") or "").strip(),
            "area_name": str(payload.get("area_name") or "").strip(),
            "town_name": str(payload.get("town_name") or "").strip(),
            "address": str(payload.get("address") or "").strip(),
            "waybill_no": str(payload.get("waybill_no") or "").strip(),
            "express_code": str(payload.get("express_code") or "").strip(),
            "express_name": str(payload.get("express_name") or "").strip(),
            "express_fee": payload.get("express_fee"),
        }
        shipping_info = {key: value for key, value in shipping_info.items() if value not in ("", None)}

        open_platform = {
            "source": source,
            "order_status": cls._coerce_int(payload.get("order_status")),
            "refund_status": cls._coerce_int(payload.get("refund_status")),
            "order_type": cls._coerce_int(payload.get("order_type")),
            "consign_type": cls._coerce_int(payload.get("consign_type")),
            "update_time": cls._coerce_int(payload.get("update_time")),
            "pay_amount": cls._coerce_int(payload.get("pay_amount")),
            "total_amount": cls._coerce_int(payload.get("total_amount")),
            "buyer_eid": str(payload.get("buyer_eid") or "").strip(),
            "buyer_nick": str(payload.get("buyer_nick") or "").strip(),
            "seller_eid": str(payload.get("seller_eid") or "").strip(),
            "seller_name": str(payload.get("seller_name") or "").strip(),
        }
        open_platform = {key: value for key, value in open_platform.items() if value not in ("", None)}

        snapshot: dict[str, Any] = {}
        if shipping_info:
            snapshot["shipping_info"] = shipping_info
        if goods_snapshot:
            snapshot["goods"] = goods_snapshot
        if open_platform:
            snapshot["open_platform"] = open_platform
        return snapshot

    @classmethod
    def _item_type_from_open_platform(cls, payload: dict[str, Any], shipping_info: dict[str, Any]) -> str:
        consign_type = cls._coerce_int(payload.get("consign_type"))
        if consign_type == 2:
            return "virtual"
        if consign_type == 1:
            return "physical"
        return cls._normalize_item_type("", shipping_info)

    @staticmethod
    def _extract_open_platform_payload(response: Any, *, path: str) -> Any:
        if hasattr(response, "ok"):
            if not bool(getattr(response, "ok", False)):
                message = str(getattr(response, "error_message", "") or f"{path} failed")
                raise ValueError(message)
            return getattr(response, "data", None)

        if isinstance(response, dict) and "code" in response:
            code = response.get("code")
            if code not in (None, 0, "0"):
                raise ValueError(str(response.get("msg") or response.get("message") or f"{path} failed"))
            return response.get("data", response)

        return response

    def _upsert_order_record(
        self,
        *,
        order_id: str,
        raw_status: str,
        session_id: str = "",
        quote_snapshot: dict[str, Any] | None = None,
        item_type: str = "virtual",
        normalized_status: str | None = None,
        event_type: str = "status_sync",
        event_detail: dict[str, Any] | None = None,
        idempotent: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        status = normalized_status or self.map_status(raw_status)
        quote_snapshot = dict(quote_snapshot or {})
        now = self._now()
        quote_json = json.dumps(quote_snapshot, ensure_ascii=False)

        with self._connect() as conn:
            existing_row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if existing_row:
                existing = self._parse_order_row(existing_row)
                same_state = (
                    str(existing.get("session_id") or "") == str(session_id or "")
                    and str(existing.get("item_type") or "") == str(item_type or "")
                    and str(existing.get("status") or "") == status
                    and existing.get("quote_snapshot", {}) == quote_snapshot
                )
                if idempotent and same_state:
                    return existing, False

            conn.execute(
                """
                INSERT INTO orders(
                    order_id, session_id, quote_snapshot_json, item_type, status,
                    manual_takeover, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    quote_snapshot_json=excluded.quote_snapshot_json,
                    item_type=excluded.item_type,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (order_id, session_id, quote_json, item_type, status, now, now),
            )
            detail = dict(event_detail or {})
            detail.setdefault("raw_status", raw_status)
            self._append_event(conn, order_id, event_type, status, detail)

        return self.get_order(order_id) or {}, True

    def upsert_order(
        self,
        order_id: str,
        raw_status: str,
        session_id: str = "",
        quote_snapshot: dict[str, Any] | None = None,
        item_type: str = "virtual",
        normalized_status: str | None = None,
        event_type: str = "status_sync",
        event_detail: dict[str, Any] | None = None,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        order, _changed = self._upsert_order_record(
            order_id=order_id,
            raw_status=raw_status,
            session_id=session_id,
            quote_snapshot=quote_snapshot,
            item_type=item_type,
            normalized_status=normalized_status,
            event_type=event_type,
            event_detail=event_detail,
            idempotent=idempotent,
        )
        return order

    def sync_open_platform_order(self, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        data = dict(payload or {})
        order_id = str(data.get("order_no") or data.get("order_id") or "").strip()
        if not order_id:
            raise ValueError("Missing order_no in open platform payload")

        existing = self.get_order(order_id)
        current_snapshot = existing.get("quote_snapshot", {}) if existing else {}
        sync_snapshot = self._build_open_platform_snapshot(data, source=source)
        merged_snapshot = self._merge_quote_snapshot(current_snapshot, sync_snapshot)
        shipping_info = merged_snapshot.get("shipping_info")
        shipping_context = dict(shipping_info) if isinstance(shipping_info, dict) else {}
        normalized_status = self.map_open_platform_status(data.get("order_status"))
        item_type = self._item_type_from_open_platform(data, shipping_context)

        order, changed = self._upsert_order_record(
            order_id=order_id,
            raw_status=str(data.get("order_status") or ""),
            session_id=str(existing.get("session_id") or "") if existing else "",
            quote_snapshot=merged_snapshot,
            item_type=item_type,
            normalized_status=normalized_status,
            event_type="status_sync",
            event_detail={
                "sync_source": source,
                "raw_status": data.get("order_status"),
                "refund_status": data.get("refund_status"),
                "update_time": data.get("update_time"),
            },
            idempotent=True,
        )

        return {
            "source": source,
            "changed": changed,
            "order": order,
        }

    def sync_open_platform_list_orders(self, client: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = client.list_orders(dict(payload or {}))
        data = self._extract_open_platform_payload(response, path="list_orders")
        rows = data.get("list") if isinstance(data, dict) else data
        orders: list[dict[str, Any]] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    orders.append(self.sync_open_platform_order(row, source="list_orders"))

        return {
            "success": True,
            "total": len(orders),
            "changed": sum(1 for item in orders if bool(item.get("changed"))),
            "orders": orders,
        }

    def sync_list_orders(self, client: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.sync_open_platform_list_orders(client, payload)

    def sync_open_platform_order_detail(
        self,
        client: Any,
        payload: dict[str, Any] | None = None,
        *,
        order_no: str | None = None,
    ) -> dict[str, Any]:
        request = dict(payload or {})
        if order_no:
            request["order_no"] = order_no
        response = client.get_order_detail(request)
        data = self._extract_open_platform_payload(response, path="get_order_detail")
        if not isinstance(data, dict):
            raise ValueError("Invalid get_order_detail payload")
        result = self.sync_open_platform_order(data, source="get_order_detail")
        return {"success": True, **result}

    def sync_get_order_detail(
        self,
        client: Any,
        payload: dict[str, Any] | None = None,
        *,
        order_no: str | None = None,
    ) -> dict[str, Any]:
        return self.sync_open_platform_order_detail(client, payload, order_no=order_no)

    def _append_event(
        self,
        conn: sqlite3.Connection,
        order_id: str,
        event_type: str,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO order_events(order_id, event_type, status, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, event_type, status, json.dumps(detail or {}, ensure_ascii=False), self._now()),
        )

    @staticmethod
    def _parse_order_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["manual_takeover"] = bool(data.get("manual_takeover", 0))
        quote = data.get("quote_snapshot_json") or "{}"
        data["quote_snapshot"] = json.loads(quote)
        return data

    def set_manual_takeover(self, order_id: str, enabled: bool) -> bool:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE orders SET manual_takeover=?, updated_at=? WHERE order_id=?",
                (1 if enabled else 0, now, order_id),
            )
            if cur.rowcount > 0:
                self._append_event(
                    conn,
                    order_id,
                    "manual_takeover",
                    "manual" if enabled else "auto",
                    {"enabled": enabled},
                )
            return cur.rowcount > 0

    @staticmethod
    def _shipping_context_from(order: dict[str, Any], override: dict[str, Any] | None = None) -> dict[str, Any]:
        if override:
            return dict(override)

        quote_snapshot = order.get("quote_snapshot")
        if isinstance(quote_snapshot, dict):
            ctx = quote_snapshot.get("shipping_info")
            if isinstance(ctx, dict):
                return dict(ctx)
        return {}

    def _find_express_company(self, keyword: str) -> dict[str, Any] | None:
        """通过闲管家 API 查找快递公司。"""
        if not self.shipping_api_client or not keyword:
            return None
        resp = self.shipping_api_client.list_express_companies()
        if not resp.ok:
            return None
        rows = resp.data if isinstance(resp.data, list) else []
        text = str(keyword).strip().lower()
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("express_code", "")).lower()
            name = str(row.get("express_name", "")).lower()
            if text in {code, name} or text in code or text in name:
                return row
        return None

    def _ship_via_xianguanjia(
        self, order_id: str, shipping_info: dict[str, Any], dry_run: bool
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not self.shipping_api_client:
            return None, None

        waybill_no = str(shipping_info.get("waybill_no", "")).strip()
        express_code = str(shipping_info.get("express_code", "")).strip()
        express_name = str(shipping_info.get("express_name", "")).strip()
        if not express_code and express_name:
            company = self._find_express_company(express_name)
            if company:
                express_code = str(company.get("express_code", "")).strip()
                if not express_name:
                    express_name = str(company.get("express_name", "")).strip()

        if not waybill_no:
            return None, "missing_waybill_no"
        if not express_code:
            return None, "missing_express_code"

        if dry_run:
            return {
                "action": "ship_order_via_xianguanjia",
                "channel": "xianguanjia_api",
                "message": "已模拟调用闲管家物流发货。",
                "dry_run": True,
                "waybill_no": waybill_no,
                "express_code": express_code,
                "express_name": express_name,
            }, None

        payload: dict[str, Any] = {
            "order_no": str(shipping_info.get("order_no") or order_id),
            "waybill_no": waybill_no,
            "express_code": express_code,
        }
        for key in ("express_name", "ship_name", "ship_mobile", "ship_province", "ship_city", "ship_area", "ship_address"):
            val = str(shipping_info.get(key, "")).strip()
            if val:
                payload[key] = val
        if express_name and "express_name" not in payload:
            payload["express_name"] = express_name

        response = self.shipping_api_client.delivery_order(payload)
        if not response.ok:
            return None, response.error_message or "ship_order_api_failed"

        return {
            "action": "ship_order_via_xianguanjia",
            "channel": "xianguanjia_api",
            "message": "已通过闲管家提交物流发货。",
            "dry_run": False,
            "waybill_no": waybill_no,
            "express_code": express_code,
            "express_name": express_name,
        }, None

    def deliver(
        self, order_id: str, dry_run: bool = False, shipping_info: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        if order["manual_takeover"]:
            return {
                "order_id": order_id,
                "status": order["status"],
                "handled": False,
                "reason": "manual_takeover",
            }

        if order["item_type"] == "virtual":
            detail = {
                "action": "send_virtual_code",
                "channel": "message_session",
                "message": "已通过闲鱼会话发送兑换信息。",
            }
            next_status = "completed" if dry_run else "shipping"
        else:
            shipping_ctx = self._shipping_context_from(order, shipping_info)
            detail = None
            api_error = ""
            if self.shipping_api_client:
                try:
                    detail, api_error = self._ship_via_xianguanjia(order_id, shipping_ctx, dry_run)
                except Exception as e:
                    api_error = str(e)

            if detail is None:
                detail = {
                    "action": "create_shipping_task",
                    "channel": "manual_fallback",
                    "message": "已创建实物发货任务，待揽收。",
                }
                if shipping_ctx:
                    detail["shipping_info"] = shipping_ctx
                if api_error:
                    detail["api_error"] = api_error
            next_status = "shipping" if detail.get("channel") == "xianguanjia_api" else "processing"

        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status=?, updated_at=? WHERE order_id=?",
                (next_status, self._now(), order_id),
            )
            self._append_event(conn, order_id, "delivery", next_status, {**detail, "dry_run": dry_run})

        updated = self.get_order(order_id)
        return {
            "order_id": order_id,
            "handled": True,
            "status": updated["status"],
            "delivery": detail,
        }

    def _register_callback_event(
        self,
        conn: sqlite3.Connection,
        *,
        order_id: str,
        external_event_id: str,
        payload: dict[str, Any],
    ) -> bool:
        event_id = str(external_event_id or "").strip()
        if not event_id:
            return True

        cur = conn.execute(
            """
            INSERT INTO order_callback_dedup(external_event_id, order_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(external_event_id) DO NOTHING
            """,
            (event_id, order_id, json.dumps(payload or {}, ensure_ascii=False), self._now()),
        )
        return cur.rowcount > 0

    def process_callback(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = False,
        auto_deliver: bool = False,
    ) -> dict[str, Any]:
        data = dict(payload or {})
        order_id = self._pick_first(data, self._ORDER_ID_KEYS)
        if not order_id:
            raise ValueError("Missing order_id in callback payload")

        raw_status = self._pick_first(data, self._RAW_STATUS_KEYS, default="待处理")
        external_event_id = self._pick_first(data, self._EXTERNAL_EVENT_ID_KEYS)
        session_id = self._pick_first(data, self._SESSION_ID_KEYS)
        quote_snapshot = data.get("quote_snapshot")
        if not isinstance(quote_snapshot, dict):
            quote_snapshot = {}
        else:
            quote_snapshot = dict(quote_snapshot)

        shipping_info = self._extract_shipping_info(data, quote_snapshot)
        if shipping_info and not isinstance(quote_snapshot.get("shipping_info"), dict):
            quote_snapshot["shipping_info"] = dict(shipping_info)

        item_type = self._normalize_item_type(self._pick_first(data, self._ITEM_TYPE_KEYS), shipping_info)
        with self._connect() as conn:
            registered = self._register_callback_event(
                conn,
                order_id=order_id,
                external_event_id=external_event_id,
                payload=data,
            )

        if external_event_id and not registered:
            existing = self.get_order(order_id)
            return {
                "success": True,
                "duplicate": True,
                "external_event_id": external_event_id,
                "order": existing,
                "auto_delivery_triggered": False,
                "delivery": None,
            }

        order = self.upsert_order(
            order_id=order_id,
            raw_status=raw_status,
            session_id=session_id,
            quote_snapshot=quote_snapshot,
            item_type=item_type,
        )

        delivery = None
        should_deliver = auto_deliver and item_type == "physical" and order.get("status") in {"paid", "processing"}
        if should_deliver:
            delivery = self.deliver(order_id, dry_run=dry_run, shipping_info=shipping_info or None)
            order = self.get_order(order_id) or order

        return {
            "success": True,
            "duplicate": False,
            "external_event_id": external_event_id,
            "order": order,
            "auto_delivery_triggered": bool(delivery),
            "delivery": delivery,
        }

    def generate_after_sales_reply(self, issue_type: str = "delay") -> str:
        return self.AFTER_SALES_TEMPLATES.get(issue_type, self.AFTER_SALES_TEMPLATES["delay"])

    def create_after_sales_case(self, order_id: str, issue_type: str = "delay") -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        reply = self.generate_after_sales_reply(issue_type)
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status='after_sales', updated_at=? WHERE order_id=?",
                (self._now(), order_id),
            )
            self._append_event(
                conn,
                order_id,
                "after_sales",
                "after_sales",
                {"issue_type": issue_type, "reply": reply},
            )

        return {
            "order_id": order_id,
            "status": "after_sales",
            "reply_template": reply,
        }

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if not row:
                return None
            return self._parse_order_row(row)

    def list_orders(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        include_manual: bool = True,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM orders"
        clauses: list[str] = []
        params: list[Any] = []

        if status:
            clauses.append("status = ?")
            params.append(status)
        if not include_manual:
            clauses.append("manual_takeover = 0")

        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(int(limit), 1))

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._parse_order_row(row) for row in rows]

    def get_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(1) AS c FROM orders").fetchone()["c"]
            manual = conn.execute("SELECT COUNT(1) AS c FROM orders WHERE manual_takeover=1").fetchone()["c"]
            by_status_rows = conn.execute(
                "SELECT status, COUNT(1) AS c FROM orders GROUP BY status ORDER BY c DESC"
            ).fetchall()

        by_status = {str(row["status"]): int(row["c"]) for row in by_status_rows}
        return {
            "total_orders": int(total),
            "manual_takeover_orders": int(manual),
            "after_sales_orders": int(by_status.get("after_sales", 0)),
            "by_status": by_status,
        }

    def record_after_sales_followup(
        self,
        *,
        order_id: str,
        issue_type: str,
        reply_text: str,
        sent: bool,
        dry_run: bool,
        reason: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        detail = {
            "issue_type": issue_type,
            "reply": reply_text,
            "sent": bool(sent),
            "dry_run": bool(dry_run),
            "reason": reason,
            "session_id": session_id,
        }
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET updated_at=? WHERE order_id=?",
                (self._now(), order_id),
            )
            self._append_event(conn, order_id, "after_sales_followup", "after_sales", detail)

        return {
            "order_id": order_id,
            "status": "after_sales",
            "sent": bool(sent),
            "dry_run": bool(dry_run),
            "reason": reason,
        }

    def trace_order(self, order_id: str) -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        with self._connect() as conn:
            events = conn.execute(
                "SELECT event_type, status, detail_json, created_at FROM order_events WHERE order_id=? ORDER BY id ASC",
                (order_id,),
            ).fetchall()

        parsed_events = []
        for ev in events:
            parsed_events.append(
                {
                    "event_type": ev["event_type"],
                    "status": ev["status"],
                    "detail": json.loads(ev["detail_json"] or "{}"),
                    "created_at": ev["created_at"],
                }
            )

        return {
            "order": order,
            "events": parsed_events,
        }
