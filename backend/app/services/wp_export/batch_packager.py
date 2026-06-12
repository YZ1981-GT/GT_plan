"""BatchPackager — 批量打包器（纯函数层）

核心职责：
1. 按审计循环+状态过滤筛选底稿列表
2. 构建 ZIP 目录结构 {audit_cycle}/{wp_code}_{wp_name}.{ext}
3. 生成 manifest.json（文件清单+SHA-256+导出时间+项目元数据+失败项）
4. 单文件失败跳过+manifest 标注
5. 空循环报错而非空 ZIP

设计原则：
- 纯函数：不依赖 DB/IO，接收 workpaper dicts 列表和内容字节
- 现有 download_pack 已实现 ZIP + 目录结构——不重写
- 本模块只做增强：manifest.json + 状态过滤 + 失败容错 + 空循环报错

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any


class BatchPackager:
    """批量打包器（纯函数设计，无 DB/IO 依赖）

    接收底稿数据列表，返回打包结果结构体。
    """

    def package(
        self,
        workpapers: list[dict],
        audit_cycles: list[str],
        status_filter: list[str] | None = None,
        project_meta: dict | None = None,
    ) -> dict:
        """纯函数：给定底稿列表，按循环+状态筛选，构建 ZIP 结构。

        Args:
            workpapers: 底稿列表，每项包含:
                - wp_code: str
                - wp_name: str
                - audit_cycle: str
                - status: str (draft/in_review/approved)
                - is_deleted: bool
                - file_content: bytes | None (文件内容，None 表示导出失败)
                - file_format: str (xlsx/docx)
                - error: str | None (导出失败原因)
            audit_cycles: 要导出的审计循环代号列表
            status_filter: 可选状态过滤列表 (draft/in_review/approved)
            project_meta: 可选项目元数据 (entity_name, period_end, project_id 等)

        Returns:
            dict with:
              - files: list of {path, sha256, wp_code, wp_name, audit_cycle}
              - manifest: dict (manifest.json 内容)
              - failed: list of {wp_code, error}
              - zip_entries: list of (zip_path, content_bytes)

        Raises:
            ValueError: 筛选后无可导出底稿（空循环）
        """
        # Step 1: 筛选
        filtered = self._filter_workpapers(workpapers, audit_cycles, status_filter)

        # Step 2: 空循环报错
        if not filtered:
            raise ValueError(
                f"指定循环 {audit_cycles} 下无可导出底稿"
                + (f"（状态过滤: {status_filter}）" if status_filter else "")
            )

        # Step 3: 构建 ZIP 条目
        files: list[dict] = []
        failed: list[dict] = []
        zip_entries: list[tuple[str, bytes]] = []

        seen_paths: set[str] = set()

        for wp in filtered:
            wp_code = wp["wp_code"]
            wp_name = wp["wp_name"]
            audit_cycle = wp["audit_cycle"]
            file_format = wp.get("file_format", "xlsx")
            file_content = wp.get("file_content")
            error = wp.get("error")

            # 单文件失败：跳过+记录
            if file_content is None or error:
                failed.append({
                    "wp_code": wp_code,
                    "error": error or "file_content is None",
                })
                continue

            # 构建 ZIP 路径
            zip_path = self._build_zip_path(audit_cycle, wp_code, wp_name, file_format)

            # 去重路径（极端情况下同 wp_code 同循环）
            if zip_path in seen_paths:
                # 加序号避免覆盖
                base, ext = zip_path.rsplit(".", 1)
                counter = 2
                while f"{base}_{counter}.{ext}" in seen_paths:
                    counter += 1
                zip_path = f"{base}_{counter}.{ext}"
            seen_paths.add(zip_path)

            # 计算 SHA-256
            sha256 = hashlib.sha256(file_content).hexdigest()

            files.append({
                "path": zip_path,
                "sha256": sha256,
                "wp_code": wp_code,
                "wp_name": wp_name,
                "audit_cycle": audit_cycle,
            })
            zip_entries.append((zip_path, file_content))

        # Step 4: 构建 manifest
        manifest = self._build_manifest(files, failed, project_meta)

        return {
            "files": files,
            "manifest": manifest,
            "failed": failed,
            "zip_entries": zip_entries,
        }

    def _filter_workpapers(
        self,
        workpapers: list[dict],
        audit_cycles: list[str],
        status_filter: list[str] | None = None,
    ) -> list[dict]:
        """按审计循环和状态过滤底稿列表。

        排除 is_deleted=True 的底稿。
        """
        result = []
        cycle_set = set(audit_cycles)

        for wp in workpapers:
            # 排除已删除
            if wp.get("is_deleted", False):
                continue

            # 匹配审计循环
            if wp.get("audit_cycle") not in cycle_set:
                continue

            # 状态过滤
            if status_filter:
                if wp.get("status") not in status_filter:
                    continue

            result.append(wp)

        return result

    def _build_zip_path(
        self,
        audit_cycle: str,
        wp_code: str,
        wp_name: str,
        file_format: str,
    ) -> str:
        """构建 {audit_cycle}/{wp_code}_{wp_name}.{ext} 路径。

        清理文件名中的非法字符。
        """
        # 清理文件名中的非法字符
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", wp_name)
        safe_code = re.sub(r'[\\/:*?"<>|]', "_", wp_code)
        safe_cycle = re.sub(r'[\\/:*?"<>|]', "_", audit_cycle)

        return f"{safe_cycle}/{safe_code}_{safe_name}.{file_format}"

    def _build_manifest(
        self,
        files: list[dict],
        failed: list[dict],
        project_meta: dict[str, Any] | None = None,
    ) -> dict:
        """构建 manifest.json 内容。

        包含:
        - files: [{path, sha256}]
        - export_timestamp: ISO-8601
        - project: 项目元数据
        - failed: [{wp_code, error}]
        """
        return {
            "files": [
                {"path": f["path"], "sha256": f["sha256"]}
                for f in files
            ],
            "export_timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "project": project_meta or {},
            "failed": failed,
            "total_files": len(files),
            "total_failed": len(failed),
        }
