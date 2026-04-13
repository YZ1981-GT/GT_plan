"""附注模版自定义服务

功能：
- CRUD 自定义附注模版（按行业/客户）
- 存储在 ~/.gt_audit_helper/note_templates/custom/
- 版本管理：版本号 + 版本历史 + 回滚

Validates: Requirements 9.4, 9.5
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def _get_custom_dir() -> Path:
    """获取自定义模版存储目录"""
    d = Path.home() / ".gt_audit_helper" / "note_templates" / "custom"
    d.mkdir(parents=True, exist_ok=True)
    return d


class NoteTemplateService:
    """附注模版自定义服务"""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_templates(self, category: str | None = None) -> list[dict]:
        """列出所有自定义模版"""
        custom_dir = _get_custom_dir()
        templates = []
        for f in sorted(custom_dir.glob("*.json")):
            if f.name.startswith("_"):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8-sig"))
                if category and data.get("category") != category:
                    continue
                templates.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return templates

    def get_template(self, template_id: str) -> dict | None:
        """获取模版详情"""
        path = _get_custom_dir() / f"{template_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            return None

    def create_template(
        self,
        name: str,
        category: str,
        sections: list[dict],
        description: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        """创建自定义模版"""
        template_id = str(uuid4())
        now = datetime.now().isoformat()
        template = {
            "id": template_id,
            "name": name,
            "category": category,
            "description": description,
            "sections": sections,
            "version": "1.0.0",
            "version_history": [
                {"version": "1.0.0", "changed_at": now, "changed_by": created_by or "system"}
            ],
            "created_at": now,
            "updated_at": now,
            "created_by": created_by or "system",
        }
        path = _get_custom_dir() / f"{template_id}.json"
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        return template

    def update_template(
        self,
        template_id: str,
        updates: dict,
        changed_by: str | None = None,
    ) -> dict:
        """更新自定义模版（自动递增版本号）"""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"模版不存在: {template_id}")

        allowed = {"name", "category", "description", "sections"}
        for key, val in updates.items():
            if key in allowed and val is not None:
                template[key] = val

        # 版本递增
        old_version = template.get("version", "1.0.0")
        new_version = self._increment_version(old_version)
        template["version"] = new_version
        now = datetime.now().isoformat()
        template["updated_at"] = now

        history = template.get("version_history", [])
        history.append({
            "version": new_version,
            "changed_at": now,
            "changed_by": changed_by or "system",
        })
        template["version_history"] = history

        path = _get_custom_dir() / f"{template_id}.json"
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        return template

    def delete_template(self, template_id: str) -> dict:
        """删除自定义模版"""
        path = _get_custom_dir() / f"{template_id}.json"
        if not path.exists():
            raise ValueError(f"模版不存在: {template_id}")
        path.unlink()
        return {"id": template_id, "deleted": True}

    # ------------------------------------------------------------------
    # 版本管理
    # ------------------------------------------------------------------

    def get_version_history(self, template_id: str) -> list[dict]:
        """获取模版版本历史"""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"模版不存在: {template_id}")
        return template.get("version_history", [])

    def rollback_version(self, template_id: str, target_version: str) -> dict:
        """回滚到指定版本（当前实现：仅更新版本号标记，实际内容回滚需要版本快照）"""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"模版不存在: {template_id}")

        history = template.get("version_history", [])
        version_exists = any(h["version"] == target_version for h in history)
        if not version_exists:
            raise ValueError(f"版本不存在: {target_version}")

        now = datetime.now().isoformat()
        rollback_version = f"{target_version}-rollback"
        template["version"] = rollback_version
        template["updated_at"] = now
        history.append({
            "version": rollback_version,
            "changed_at": now,
            "changed_by": "system",
        })
        template["version_history"] = history

        path = _get_custom_dir() / f"{template_id}.json"
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        return template

    # ------------------------------------------------------------------
    # SOE / Listed 模版加载
    # ------------------------------------------------------------------

    def get_soe_template(self) -> dict:
        """获取国企版附注模版"""
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        path = data_dir / "note_template_soe.json"
        if not path.exists():
            return {"template_type": "soe", "sections": []}
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def get_listed_template(self) -> dict:
        """获取上市版附注模版"""
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        path = data_dir / "note_template_listed.json"
        if not path.exists():
            return {"template_type": "listed", "sections": []}
        return json.loads(path.read_text(encoding="utf-8-sig"))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _increment_version(version: str) -> str:
        """递增补丁版本号 1.0.0 -> 1.0.1"""
        parts = version.split("-")[0].split(".")
        if len(parts) == 3:
            try:
                parts[2] = str(int(parts[2]) + 1)
                return ".".join(parts)
            except ValueError:
                pass
        return version + ".1"
