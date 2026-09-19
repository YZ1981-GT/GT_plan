"""模板级 ProcedureRowDefinition 导入与规范化修订哈希（Task 3）

Feature: procedure-delegation-notification / 需求 1.1-1.7 / Design C1、D1、Properties P1-P3

职责：
- 统一 **JSON 模板**（``procedure_table_templates.json``）与 **xlsx fallback**
  （``extract_program_rows``）两个来源，抽取 source_locator、program text、
  ref snapshot 与 legacy aliases。
- 对每条程序行做 **canonical JSON 规范化** 并生成跨项目/跨机器/顺序无关的
  稳定 ``definition_key``；对整套定义集合做 **SHA-256** ``template_revision_hash``。
- 规范化 **排除** mtime、绝对路径、导入时间、项目 id 与数组位置；这些非内容元数据
  不进入 hash（P2）。``row-{program_no}``/数组序号 **仅** 登记为 legacy alias，
  不成为长期身份（P3）。
- ``import_definitions`` 是显式写命令：按 ``definition_key`` **insert-if-absent**，
  **保留旧 revision，不静默覆盖**（需求 1.6，继承关系交由 reconcile / Task 5 显式处理）。

纯逻辑（规范化 / 哈希 / key 生成）无 DB 副作用，便于 PBT；DB 持久化只 flush 不 commit。
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 规范化原语
# ---------------------------------------------------------------------------

def normalize_text(value: Any) -> str:
    """文本规范化：Unicode NFKC + 换行统一（\\r\\n,\\r → \\n）+ 首尾 trim。"""
    if value is None:
        return ""
    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def canonical_json(obj: Any) -> str:
    """canonical JSON：对象 key 排序、无多余空白、保留非 ASCII 原文。

    作为 SHA-256 的稳定输入；相同语义内容在任何机器/顺序下产生同一字符串。
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_program_no(value: Any) -> str | None:
    """程序号规范化为字符串（语义标签，非数组位置）；空 → None。"""
    if value is None:
        return ""
    if isinstance(value, bool):  # 防御：bool 是 int 子类
        return str(value)
    if isinstance(value, float) and value == int(value):
        value = int(value)
    text = normalize_text(value)
    return text or ""


def _split_ref_tokens(ref_index: Any) -> list[str]:
    """ref_index 字符串（如 "G1-1/G1-2"）拆为 token 列表。"""
    text = normalize_text(ref_index)
    if not text:
        return []
    parts = [p.strip() for p in text.replace("\\", "/").split("/")]
    return [p for p in parts if p]


def _build_ref_snapshot(ref_index: Any, auto_data_source: Any) -> list[str]:
    """引用快照：ref_index token + auto source（前缀 ``auto:`` 以区分）。

    语义无序集合，作为身份/哈希输入时排序，故此处仅收集并去重。
    """
    tokens = list(_split_ref_tokens(ref_index))
    auto = normalize_text(auto_data_source)
    if auto and auto.lower() not in ("none", "null"):
        tokens.append(f"auto:{auto}")
    # 去重且稳定
    seen: dict[str, None] = {}
    for t in tokens:
        seen.setdefault(t, None)
    return list(seen.keys())


# ---------------------------------------------------------------------------
# 统一中间行模型
# ---------------------------------------------------------------------------

@dataclass
class _RawRow:
    """JSON/xlsx 两源统一后的中间程序行。"""

    program_no: str
    procedure_text: str
    ref_snapshot: list[str]
    array_index: int
    legacy_row_id: str | None = None


def _raw_from_json_item(item: dict, array_index: int) -> _RawRow:
    program_no = _normalize_program_no(item.get("seq"))
    return _RawRow(
        program_no=program_no,
        procedure_text=normalize_text(item.get("content")),
        ref_snapshot=_build_ref_snapshot(item.get("ref_index"), item.get("auto_data_source")),
        array_index=array_index,
        legacy_row_id=f"row-{program_no}" if program_no else None,
    )


def _raw_from_xlsx_row(row: dict, array_index: int) -> _RawRow:
    program_no = _normalize_program_no(row.get("program_no"))
    return _RawRow(
        program_no=program_no,
        procedure_text=normalize_text(row.get("program_desc")),
        ref_snapshot=_build_ref_snapshot(row.get("linked_workpapers"), None),
        array_index=array_index,
        legacy_row_id=normalize_text(row.get("id")) or (f"row-{program_no}" if program_no else None),
    )


# ---------------------------------------------------------------------------
# definition_key / revision 生成
# ---------------------------------------------------------------------------

def _source_locator_stable(template_code: str, sheet_key: str) -> dict:
    """进入哈希的 source_locator 稳定部分：仅逻辑定位（模板/ sheet），

    **排除** 物理来源种类（json/xlsx）、绝对路径、文件名、mtime、导入时间，
    以保证 JSON 与 xlsx 同一逻辑行可统一，且路径/时间变化不改变 revision（P2）。
    """
    return {"template_code": template_code, "sheet_key": sheet_key}


def _semantic_content(template_code: str, sheet_key: str, raw: _RawRow) -> dict:
    """身份/哈希输入的规范语义形式（数组仅在语义无序字段 refs 上排序）。"""
    return {
        "template_code": template_code,
        "sheet_key": sheet_key,
        "source_locator_stable": _source_locator_stable(template_code, sheet_key),
        "program_no": raw.program_no,
        "procedure_text": raw.procedure_text,
        "refs": sorted(raw.ref_snapshot),
    }


def compute_definition_key(template_code: str, sheet_key: str, raw: _RawRow) -> str:
    """跨项目/机器/顺序稳定的 definition_key（内容寻址）。

    形如 ``{template_code}::{sheet_key}::{digest16}``；不含 project_id、wp_id、
    数组位置、mtime、绝对路径。程序号作为语义标签参与摘要（非数组序号）。
    """
    digest = sha256_hex(canonical_json(_semantic_content(template_code, sheet_key, raw)))
    return f"{template_code}::{sheet_key}::{digest[:16]}"


def _build_definition(template_code: str, sheet_key: str, raw: _RawRow, source_locator: dict) -> dict:
    """构造单条 definition dict（含 legacy aliases、normalized_content）。"""
    definition_key = compute_definition_key(template_code, sheet_key, raw)
    normalized_content = _semantic_content(template_code, sheet_key, raw)

    # legacy aliases：row-{program_no} 与数组序号仅作别名，不作身份（P3）
    aliases: dict[str, None] = {}
    if raw.legacy_row_id:
        aliases.setdefault(raw.legacy_row_id, None)
    if raw.program_no:
        aliases.setdefault(f"row-{raw.program_no}", None)
    aliases.setdefault(f"index-{raw.array_index}", None)
    legacy_aliases = list(aliases.keys())

    return {
        "definition_key": definition_key,
        "template_code": template_code,
        "sheet_key": sheet_key,
        "source_locator": source_locator,
        "program_no": raw.program_no or None,
        "procedure_text": raw.procedure_text,
        "ref_snapshot": list(raw.ref_snapshot),
        "legacy_aliases": legacy_aliases,
        "normalized_content": normalized_content,
    }


def compute_revision_hash(definitions: list[dict]) -> str:
    """整套定义集合的 SHA-256 revision。

    按 ``(sheet_key, source_locator stable part, definition_key)`` 排序后对
    canonical JSON 求 SHA-256，故与导入顺序、机器、项目无关（P1）；仅语义内容变化
    才改变 revision（P2）。
    """
    collection = [
        {
            "sheet_key": d["sheet_key"],
            "source_locator_stable": _source_locator_stable(d["template_code"], d["sheet_key"]),
            "definition_key": d["definition_key"],
            "program_no": d.get("program_no") or "",
            "procedure_text": d.get("procedure_text") or "",
            "refs": sorted(d.get("ref_snapshot") or []),
        }
        for d in definitions
    ]
    collection.sort(
        key=lambda x: (
            x["sheet_key"],
            canonical_json(x["source_locator_stable"]),
            x["definition_key"],
        )
    )
    return sha256_hex(canonical_json(collection))


@dataclass
class ImportResult:
    """一次抽取的结果：定义列表 + 集合级 revision。"""

    template_code: str
    sheet_key: str
    definitions: list[dict] = field(default_factory=list)
    revision_hash: str = ""

    def with_revision(self) -> "ImportResult":
        rev = compute_revision_hash(self.definitions)
        self.revision_hash = rev
        for d in self.definitions:
            d["template_revision_hash"] = rev
        return self


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------

class ProcedureDefinitionImporter:
    """模板级程序行定义导入器（JSON 模板 + xlsx fallback）。"""

    def __init__(self, db: Any | None = None):
        # DB 仅在 import_definitions 显式写命令中使用；抽取/规范化为纯逻辑无需 DB。
        self.db = db

    # -- 抽取（纯逻辑）--------------------------------------------------------

    @staticmethod
    def build_from_raw_rows(
        template_code: str,
        sheet_key: str,
        raw_rows: list[_RawRow],
        source_locator: dict,
    ) -> ImportResult:
        definitions = [
            _build_definition(template_code, sheet_key, raw, dict(source_locator))
            for raw in raw_rows
        ]
        return ImportResult(template_code, sheet_key, definitions).with_revision()

    @classmethod
    def build_from_json_template(
        cls,
        template_code: str,
        sheet_key: str,
        template: dict,
    ) -> ImportResult:
        """从 procedure_table_templates.json 的单个模板条目抽取定义。"""
        items = template.get("items") or []
        raw_rows = [_raw_from_json_item(it, i) for i, it in enumerate(items) if isinstance(it, dict)]
        source_locator = {
            "kind": "json_template",
            "template_code": template_code,
            "sheet_key": sheet_key,
            "template_name": normalize_text(template.get("name")),
        }
        return cls.build_from_raw_rows(template_code, sheet_key, raw_rows, source_locator)

    @classmethod
    def build_from_xlsx(
        cls,
        template_code: str,
        sheet_key: str,
        file_path: str | Path,
        sheet_name: str,
    ) -> ImportResult:
        """从 xlsx 源 sheet 抽取定义（复用 extract_program_rows 兜底提取）。"""
        from app.services.wp_program_extract import extract_program_rows

        rows = extract_program_rows(file_path, sheet_name)
        raw_rows = [_raw_from_xlsx_row(r, i) for i, r in enumerate(rows) if isinstance(r, dict)]
        # source_locator 只保留稳定/展示信息（文件名 basename），不含绝对路径/mtime
        source_locator = {
            "kind": "xlsx",
            "template_code": template_code,
            "sheet_key": sheet_key,
            "sheet_name": sheet_name,
            "file_name": Path(file_path).name,
        }
        return cls.build_from_raw_rows(template_code, sheet_key, raw_rows, source_locator)

    @classmethod
    def build_from_source(
        cls,
        template_code: str,
        sheet_key: str,
        *,
        json_template: dict | None = None,
        xlsx_path: str | Path | None = None,
        xlsx_sheet: str | None = None,
    ) -> ImportResult:
        """统一入口：优先 JSON 模板，其次 xlsx fallback。"""
        if json_template is not None and (json_template.get("items")):
            return cls.build_from_json_template(template_code, sheet_key, json_template)
        if xlsx_path is not None and xlsx_sheet:
            return cls.build_from_xlsx(template_code, sheet_key, xlsx_path, xlsx_sheet)
        return ImportResult(template_code, sheet_key, []).with_revision()

    # -- 持久化（显式写命令；insert-if-absent，保留旧 revision）----------------

    async def import_definitions(self, result: ImportResult) -> dict:
        """按 definition_key insert-if-absent 持久化。

        - 新 definition_key → 插入新行（携带集合 revision）。
        - 已存在 definition_key → **保留旧行/旧 revision，不静默覆盖**；
          继承/迁移关系由 reconcile（Task 5）显式决定。
        - 只 flush 不 commit（service 约定）。
        """
        if self.db is None:
            raise RuntimeError("import_definitions 需要 AsyncSession（self.db 为空）")

        import sqlalchemy as sa

        from app.models.procedure_models import ProcedureRowDefinition

        inserted = 0
        preserved = 0
        keys = [d["definition_key"] for d in result.definitions]
        existing_keys: set[str] = set()
        if keys:
            rows = (
                await self.db.execute(
                    sa.select(ProcedureRowDefinition.definition_key).where(
                        ProcedureRowDefinition.definition_key.in_(keys)
                    )
                )
            ).scalars().all()
            existing_keys = set(rows)

        for d in result.definitions:
            if d["definition_key"] in existing_keys:
                preserved += 1
                continue
            self.db.add(
                ProcedureRowDefinition(
                    definition_key=d["definition_key"],
                    template_code=d["template_code"],
                    template_revision_hash=d["template_revision_hash"],
                    sheet_key=d["sheet_key"],
                    source_locator=d["source_locator"],
                    program_no=d.get("program_no"),
                    procedure_text=d["procedure_text"],
                    ref_snapshot=d["ref_snapshot"],
                    legacy_aliases=d["legacy_aliases"],
                    normalized_content=d["normalized_content"],
                )
            )
            inserted += 1
            existing_keys.add(d["definition_key"])

        await self.db.flush()
        return {
            "template_code": result.template_code,
            "sheet_key": result.sheet_key,
            "revision_hash": result.revision_hash,
            "inserted": inserted,
            "preserved": preserved,
            "total": len(result.definitions),
        }
