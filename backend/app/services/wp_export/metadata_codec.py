"""MetadataCodec - 底稿元数据编解码器

负责将 MetadataBundle 嵌入 xlsx/docx 文件属性，并从文件中提取元数据。
- xlsx: 使用 openpyxl Custom Document Properties
- docx: 将全部元数据作为 JSON 存入 core_properties.comments

Requirements: 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from docx import Document
from openpyxl import Workbook
from openpyxl.packaging.custom import IntProperty, StringProperty

from app.schemas.wp_export_schemas import MetadataBundle

logger = logging.getLogger(__name__)


class MetadataCodec:
    """元数据编解码器

    在导出文件中嵌入底稿元数据，导入时提取用于匹配目标底稿和版本冲突检测。
    """

    XLSX_PROPS: list[str] = [
        "wp_code",
        "project_id",
        "file_version",
        "export_timestamp",
        "preparer",
        "reviewer",
        "review_status",
    ]

    # docx 策略：全部元数据作为 JSON 存入 core_properties.comments
    # 避免 python-docx 对 custom properties 支持有限的问题
    _DOCX_METADATA_KEY = "_wp_metadata_bundle"

    def embed_xlsx(self, wb: Workbook, metadata: MetadataBundle) -> None:
        """写入 xlsx Custom Properties

        将 MetadataBundle 各字段作为独立的 Custom Document Property 写入。
        已存在同名属性时先移除再写入（幂等）。
        """
        props = wb.custom_doc_props

        # 清除已有的同名属性（幂等写入）
        existing_names = set(props.names)
        if existing_names & set(self.XLSX_PROPS):
            props.props = [
                p for p in props.props if p.name not in self.XLSX_PROPS
            ]

        for field in self.XLSX_PROPS:
            value = getattr(metadata, field, None)
            if value is None:
                # 可选字段为空时写空字符串标记（提取时还原为 None）
                props.append(StringProperty(name=field, value=""))
                continue

            if field == "file_version":
                props.append(IntProperty(name=field, value=int(value)))
            elif field == "project_id":
                props.append(StringProperty(name=field, value=str(value)))
            elif field == "export_timestamp":
                # 序列化为 ISO-8601 字符串
                if isinstance(value, datetime):
                    props.append(
                        StringProperty(name=field, value=value.isoformat())
                    )
                else:
                    props.append(StringProperty(name=field, value=str(value)))
            else:
                props.append(StringProperty(name=field, value=str(value)))

    def embed_docx(self, doc: Document, metadata: MetadataBundle) -> None:
        """写入 docx core properties (comments 字段存 JSON)

        将全部元数据序列化为 JSON 字符串存入 core_properties.comments。
        这是最可靠的方式，避免 python-docx custom properties 支持有限的问题。
        """
        bundle_dict = {
            "wp_code": metadata.wp_code,
            "project_id": str(metadata.project_id),
            "file_version": metadata.file_version,
            "export_timestamp": metadata.export_timestamp.isoformat(),
            "preparer": metadata.preparer,
            "reviewer": metadata.reviewer,
            "review_status": metadata.review_status,
        }
        doc.core_properties.comments = json.dumps(
            bundle_dict, ensure_ascii=False
        )

    def extract_xlsx(self, wb: Workbook) -> MetadataBundle | None:
        """从 xlsx Custom Properties 提取元数据

        Returns:
            MetadataBundle 如果必要字段 (wp_code, project_id) 存在；
            否则返回 None。
        """
        props = wb.custom_doc_props
        existing_names = set(props.names)

        # 必要字段检查
        if "wp_code" not in existing_names or "project_id" not in existing_names:
            return None

        # 构建 name→value 映射
        prop_map: dict[str, str | int] = {}
        for prop in props.props:
            if prop.name in self.XLSX_PROPS:
                prop_map[prop.name] = prop.value

        return self._parse_prop_map(prop_map)

    def extract_docx(self, doc: Document) -> MetadataBundle | None:
        """从 docx core_properties.comments 提取元数据

        Returns:
            MetadataBundle 如果 comments 中包含有效 JSON 且含必要字段；
            否则返回 None。
        """
        comments = doc.core_properties.comments
        if not comments:
            return None

        try:
            bundle_dict = json.loads(comments)
        except (json.JSONDecodeError, TypeError):
            logger.warning("docx comments 不是有效的 JSON 元数据")
            return None

        if not isinstance(bundle_dict, dict):
            return None

        # 必要字段检查
        if not bundle_dict.get("wp_code") or not bundle_dict.get("project_id"):
            return None

        return self._parse_prop_map(bundle_dict)

    def _parse_prop_map(
        self, prop_map: dict[str, str | int | None]
    ) -> MetadataBundle | None:
        """将属性映射解析为 MetadataBundle"""
        try:
            wp_code = str(prop_map.get("wp_code", ""))
            if not wp_code:
                return None

            project_id_raw = prop_map.get("project_id", "")
            if not project_id_raw:
                return None
            project_id = UUID(str(project_id_raw))

            file_version_raw = prop_map.get("file_version", 0)
            file_version = int(file_version_raw) if file_version_raw else 0

            export_timestamp_raw = prop_map.get("export_timestamp", "")
            if export_timestamp_raw and str(export_timestamp_raw).strip():
                export_timestamp = datetime.fromisoformat(
                    str(export_timestamp_raw)
                )
            else:
                export_timestamp = datetime.now(tz=timezone.utc)

            # 可选字段：空字符串视为 None
            preparer = _empty_to_none(prop_map.get("preparer"))
            reviewer = _empty_to_none(prop_map.get("reviewer"))
            review_status = _empty_to_none(prop_map.get("review_status"))

            return MetadataBundle(
                wp_code=wp_code,
                project_id=project_id,
                file_version=file_version,
                export_timestamp=export_timestamp,
                preparer=preparer,
                reviewer=reviewer,
                review_status=review_status,
            )
        except (ValueError, TypeError) as e:
            logger.warning("解析元数据失败: %s", e)
            return None


def _empty_to_none(value: str | int | None) -> str | None:
    """空字符串或 None 转 None，非空字符串保留"""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
