"""A/B 实验、策略版本与漏斗统计。"""

from __future__ import annotations

import hashlib
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class GrowthService:
    def __init__(self, db_path: str = "data/growth.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS strategy_versions (
                    strategy_type TEXT NOT NULL,
                    version TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    baseline INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(strategy_type, version)
                );

                CREATE TABLE IF NOT EXISTS experiment_assignments (
                    experiment_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    strategy_version TEXT,
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY(experiment_id, subject_id)
                );

                CREATE TABLE IF NOT EXISTS funnel_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    experiment_id TEXT,
                    variant TEXT,
                    strategy_version TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_funnel_stage_time
                ON funnel_events(stage, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_funnel_exp_variant
                ON funnel_events(experiment_id, variant, stage);
                """
            )

    def set_strategy_version(
        self,
        strategy_type: str,
        version: str,
        *,
        active: bool = False,
        baseline: bool = False,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_versions(strategy_type, version, is_active, baseline, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(strategy_type, version) DO UPDATE SET
                    is_active=excluded.is_active,
                    baseline=excluded.baseline
                """,
                (strategy_type, version, 1 if active else 0, 1 if baseline else 0, now),
            )
            if active:
                conn.execute(
                    "UPDATE strategy_versions SET is_active=0 WHERE strategy_type=? AND version<>?",
                    (strategy_type, version),
                )
        return self.get_active_strategy(strategy_type)

    def rollback_to_baseline(self, strategy_type: str) -> dict[str, Any] | None:
        sql = (
            "SELECT version FROM strategy_versions "
            "WHERE strategy_type=? AND baseline=1 "
            "ORDER BY created_at DESC LIMIT 1"
        )
        with self._connect() as conn:
            row = conn.execute(sql, (strategy_type,)).fetchone()
        if not row:
            return None
        return self.set_strategy_version(strategy_type, str(row["version"]), active=True, baseline=True)

    def get_active_strategy(self, strategy_type: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM strategy_versions WHERE strategy_type=? AND is_active=1 LIMIT 1",
                (strategy_type,),
            ).fetchone()
            return dict(row) if row else None

    def assign_variant(
        self,
        experiment_id: str,
        subject_id: str,
        variants: tuple[str, ...] = ("A", "B"),
        strategy_version: str | None = None,
    ) -> dict[str, Any]:
        assign_sql = (
            "SELECT variant, strategy_version FROM experiment_assignments WHERE experiment_id=? AND subject_id=?"
        )
        with self._connect() as conn:
            existing = conn.execute(assign_sql, (experiment_id, subject_id)).fetchone()
            if existing:
                return {
                    "experiment_id": experiment_id,
                    "subject_id": subject_id,
                    "variant": str(existing["variant"]),
                    "strategy_version": existing["strategy_version"],
                    "new_assignment": False,
                }

            digest = hashlib.sha1(f"{experiment_id}:{subject_id}".encode()).hexdigest()
            idx = int(digest[:8], 16) % max(1, len(variants))
            variant = variants[idx]

            conn.execute(
                """
                INSERT INTO experiment_assignments(experiment_id, subject_id, variant, strategy_version, assigned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (experiment_id, subject_id, variant, strategy_version, self._now()),
            )
            return {
                "experiment_id": experiment_id,
                "subject_id": subject_id,
                "variant": variant,
                "strategy_version": strategy_version,
                "new_assignment": True,
            }

    def record_event(
        self,
        subject_id: str,
        stage: str,
        *,
        experiment_id: str | None = None,
        variant: str | None = None,
        strategy_version: str | None = None,
    ) -> dict[str, Any]:
        if experiment_id and not variant:
            assign_sql = (
                "SELECT variant, strategy_version FROM experiment_assignments WHERE experiment_id=? AND subject_id=?"
            )
            with self._connect() as conn:
                row = conn.execute(assign_sql, (experiment_id, subject_id)).fetchone()
            if row:
                variant = str(row["variant"])
                if not strategy_version:
                    strategy_version = row["strategy_version"]

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO funnel_events(subject_id, stage, experiment_id, variant, strategy_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (subject_id, stage, experiment_id, variant, strategy_version, self._now()),
            )
        return {
            "subject_id": subject_id,
            "stage": stage,
            "experiment_id": experiment_id,
            "variant": variant,
            "strategy_version": strategy_version,
        }

    def funnel_stats(self, days: int = 7, bucket: str = "day") -> dict[str, Any]:
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).strftime("%Y-%m-%dT%H:%M:%SZ")
        group_expr = "substr(created_at, 1, 10)" if bucket == "day" else "strftime('%Y-%W', created_at)"

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {group_expr} AS bucket, stage, COUNT(DISTINCT subject_id) AS c
                FROM funnel_events
                WHERE created_at >= ?
                GROUP BY bucket, stage
                ORDER BY bucket ASC
                """,
                (cutoff,),
            ).fetchall()

        data: dict[str, dict[str, int]] = {}
        for row in rows:
            b = str(row["bucket"])
            if b not in data:
                data[b] = {}
            data[b][str(row["stage"])] = int(row["c"])

        return {"days": days, "bucket": bucket, "series": data}

    @staticmethod
    def _z_test(p1: float, n1: int, p2: float, n2: int) -> float:
        if n1 <= 0 or n2 <= 0:
            return 1.0
        pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
        denom = math.sqrt(max(1e-9, pooled * (1 - pooled) * (1 / n1 + 1 / n2)))
        z = abs((p1 - p2) / denom)
        # Two-tailed p-value using normal approximation
        return max(0.0, min(1.0, 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))))

    def compare_variants(
        self,
        experiment_id: str,
        from_stage: str = "inquiry",
        to_stage: str = "ordered",
    ) -> dict[str, Any]:
        with self._connect() as conn:
            denom = conn.execute(
                """
                SELECT variant, COUNT(DISTINCT subject_id) AS c
                FROM funnel_events
                WHERE experiment_id=? AND stage=?
                GROUP BY variant
                """,
                (experiment_id, from_stage),
            ).fetchall()
            numer = conn.execute(
                """
                SELECT variant, COUNT(DISTINCT subject_id) AS c
                FROM funnel_events
                WHERE experiment_id=? AND stage=?
                GROUP BY variant
                """,
                (experiment_id, to_stage),
            ).fetchall()

        d = {str(r["variant"]): int(r["c"]) for r in denom}
        n = {str(r["variant"]): int(r["c"]) for r in numer}

        variants = sorted(set(d.keys()) | set(n.keys()))
        result: dict[str, Any] = {}
        for v in variants:
            total = d.get(v, 0)
            conv = n.get(v, 0)
            rate = (conv / total) if total else 0.0
            result[v] = {
                "from_stage_users": total,
                "to_stage_users": conv,
                "conversion_rate": round(rate, 4),
            }

        p_value = None
        if len(variants) >= 2:
            a, b = variants[0], variants[1]
            p_value = self._z_test(
                result[a]["conversion_rate"],
                result[a]["from_stage_users"],
                result[b]["conversion_rate"],
                result[b]["from_stage_users"],
            )

        return {
            "experiment_id": experiment_id,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "variants": result,
            "p_value": round(p_value, 6) if p_value is not None else None,
            "significant_at_0_05": bool(p_value is not None and p_value < 0.05),
        }
