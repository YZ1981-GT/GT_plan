"""增强审计日志服务 — 详细上下文 + 导出 + 查询分析 + 告警

Phase 8 Task 10.2: 审计日志增强
"""

from __future__ import annotations

import csv
import io
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# Anomaly detection thresholds
ANOMALY_THRESHOLDS = {
    "bulk_download": {"count": 10, "window_seconds": 300},  # 10 downloads in 5 min
    "off_hours_operation": {"start_hour": 22, "end_hour": 6},
    "rapid_export": {"count": 5, "window_seconds": 60},
}


class AuditLoggerEnhanced:
    """增强审计日志服务。"""

    def __init__(self):
        self._recent_actions: list[dict] = []
        self._anomaly_alerts: list[dict] = []

    async def log_action(
        self,
        user_id: UUID | str,
        action: str,
        object_type: str,
        object_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        """记录操作日志（含详细上下文）。"""
        entry = {
            "user_id": str(user_id),
            "action": action,
            "object_type": object_type,
            "object_id": str(object_id) if object_id else None,
            "project_id": str(project_id) if project_id else None,
            "details": details or {},
            "ip_address": ip_address,
            "request_id": request_id,
            "timestamp": time.time(),
            "created_at": datetime.utcnow().isoformat(),
        }

        self._recent_actions.append(entry)
        if len(self._recent_actions) > 10000:
            self._recent_actions = self._recent_actions[-10000:]

        # Check for anomalies
        self._check_anomalies(entry)

        return entry

    def _check_anomalies(self, entry: dict):
        """检测异常操作。"""
        user_id = entry["user_id"]
        action = entry["action"]
        now = entry["timestamp"]

        # Bulk download detection
        if action in ("download", "export", "batch_download"):
            recent = [
                a for a in self._recent_actions
                if a["user_id"] == user_id
                and a["action"] in ("download", "export", "batch_download")
                and now - a["timestamp"] < ANOMALY_THRESHOLDS["bulk_download"]["window_seconds"]
            ]
            if len(recent) >= ANOMALY_THRESHOLDS["bulk_download"]["count"]:
                self._add_anomaly_alert(
                    "bulk_download",
                    f"用户 {user_id} 在5分钟内下载/导出 {len(recent)} 次",
                    entry,
                )

        # Off-hours detection
        hour = datetime.utcnow().hour
        threshold = ANOMALY_THRESHOLDS["off_hours_operation"]
        if hour >= threshold["start_hour"] or hour < threshold["end_hour"]:
            if action in ("delete", "export", "batch_download", "modify"):
                self._add_anomaly_alert(
                    "off_hours",
                    f"用户 {user_id} 在非工作时间执行 {action} 操作",
                    entry,
                )

    def _add_anomaly_alert(self, alert_type: str, message: str, entry: dict):
        self._anomaly_alerts.append({
            "type": alert_type,
            "message": message,
            "user_id": entry["user_id"],
            "action": entry["action"],
            "timestamp": time.time(),
        })
        if len(self._anomaly_alerts) > 500:
            self._anomaly_alerts = self._anomaly_alerts[-500:]
        logger.warning("ANOMALY ALERT [%s]: %s", alert_type, message)

    # ---- Query & Analysis ----

    def query_logs(
        self,
        user_id: str | None = None,
        action: str | None = None,
        object_type: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """查询日志。"""
        results = self._recent_actions
        if user_id:
            results = [r for r in results if r["user_id"] == user_id]
        if action:
            results = [r for r in results if r["action"] == action]
        if object_type:
            results = [r for r in results if r["object_type"] == object_type]
        if project_id:
            results = [r for r in results if r.get("project_id") == project_id]
        return results[-limit:]

    def get_anomaly_alerts(self, limit: int = 50) -> list[dict]:
        """获取异常告警。"""
        return self._anomaly_alerts[-limit:]

    # ---- Export ----

    def export_csv(self, logs: list[dict] | None = None) -> bytes:
        """导出为 CSV。"""
        data = logs or self._recent_actions
        output = io.StringIO()
        fields = ["created_at", "user_id", "action", "object_type", "object_id", "project_id", "ip_address"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for entry in data:
            writer.writerow(entry)
        return output.getvalue().encode("utf-8-sig")

    def export_excel(self, logs: list[dict] | None = None) -> bytes:
        """导出为 Excel（openpyxl）。"""
        try:
            import openpyxl
            from io import BytesIO

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "审计日志"

            # 表头
            headers = ["ID", "事件类型", "操作者", "角色", "对象类型", "对象ID", "操作", "时间"]
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=h)
                cell.font = openpyxl.styles.Font(bold=True, name="仿宋_GB2312")

            # 数据行
            data = logs if logs is not None else []
            for row_idx, log in enumerate(data, 2):
                ws.cell(row=row_idx, column=1, value=log.get("id", ""))
                ws.cell(row=row_idx, column=2, value=log.get("event_type", ""))
                ws.cell(row=row_idx, column=3, value=log.get("actor_id", ""))
                ws.cell(row=row_idx, column=4, value=log.get("actor_role", ""))
                ws.cell(row=row_idx, column=5, value=log.get("resource_type", log.get("object_type", "")))
                ws.cell(row=row_idx, column=6, value=log.get("resource_id", log.get("object_id", "")))
                ws.cell(row=row_idx, column=7, value=log.get("action", ""))
                ws.cell(row=row_idx, column=8, value=log.get("created_at", ""))

            # 列宽
            for col in range(1, len(headers) + 1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 20

            buf = BytesIO()
            wb.save(buf)
            return buf.getvalue()
        except ImportError:
            # openpyxl 不可用时降级为 CSV
            return self.export_csv(logs)

    # ---- Retention ----

    def cleanup_old_logs(self, max_age_days: int = 365) -> int:
        """清理超过保留期的日志。"""
        cutoff = time.time() - (max_age_days * 86400)
        before = len(self._recent_actions)
        self._recent_actions = [a for a in self._recent_actions if a["timestamp"] > cutoff]
        return before - len(self._recent_actions)


# Global instance
audit_logger = AuditLoggerEnhanced()
