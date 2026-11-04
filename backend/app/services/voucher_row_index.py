"""凭证检查行索引：按凭证身份找各底稿检查表里的行与结论（spec voucher-workflow-linkage-lineage-closure design §8）。

读 ``checklist_responses``（底稿 HTML 侧的录入落点；在线编辑镜像与导入也写这里），不建投影表（ADR-VWL-04）：
写入方有 HTML CAS、在线编辑镜像、导入三类，投影表要每个写入方维护，漂移风险大。

- 两列（``remark`` / ``conclusion``）都可能放载荷（与 ``entry_payload_reader`` 同一结论），只解析以 ``[`` / ``{`` 开头的 JSON；
- 字典带合法的 ``_gt.vk`` ⇒ 身份行；否则有凭证号与日期 ⇒ 旧行（没有 ``_gt`` 的旧导入、手工增补的行），按「号|日期」认
  （与前端 ``legacyIdentity`` 的号、日期取法相同）；认出的行不再往里找（``_gt`` 本身就在行里）；
- 结论只读白名单字段、按固定取值表判（``backend/data/voucher_check_verdict_vocab.json``，ADR-VWL-05）；
- 上限：单条载荷 2,000,000 字符（实测最长约 87 万）、遍历深度 6、单次最多 200,000 个字典；超限停止并标 ``truncated``；
- 只算本项目未删除的底稿。

调用方：已挂查询的「已导入」、底稿待导入提示、他稿结论查询、异常处置。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper
from app.services.voucher_identity import VoucherKey, norm_text

logger = logging.getLogger(__name__)

Verdict = Literal["abnormal", "normal", "unknown"]

VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "voucher_check_verdict_vocab.json"
MAX_PAYLOAD_CHARS = 2_000_000
MAX_DEPTH = 6
MAX_DICTS = 200_000

#: checklist_responses 没有 ORM 模型；这里只声明读到的列（UUID 列在 SQLite 上存 32 位十六进制，与 ORM 表一致）
_META = sa.MetaData()
CHECKLIST = sa.Table(
    "checklist_responses", _META,
    sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
    sa.Column("project_id", PG_UUID(as_uuid=True)),
    sa.Column("wp_id", PG_UUID(as_uuid=True)),
    sa.Column("item_id", sa.String(256)),
    sa.Column("conclusion", sa.Text),
    sa.Column("remark", sa.Text),
)

_NO_FIELDS = ("voucherNo", "voucher_no", "voucherNumber")
_DATE_FIELDS = ("voucherDate", "voucher_date", "date")


@lru_cache(maxsize=1)
def verdict_vocab() -> dict[str, dict[str, tuple]]:
    """字段 → {abnormal: 取值, normal: 取值}。"""
    raw = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))["fields"]
    return {name: {"abnormal": tuple(v["abnormal"]), "normal": tuple(v["normal"])} for name, v in raw.items()}


def _matches(value: Any, options: tuple) -> bool:
    if isinstance(value, bool):
        return any(isinstance(o, bool) and o is value for o in options)
    if isinstance(value, str):
        text = value.strip()
        return any(isinstance(o, str) and o == text for o in options)
    return False


def row_verdict(row: dict) -> Verdict:
    """一行的结论：任一白名单字段为异常即异常；否则任一为正常即正常；否则未判定。"""
    vocab = verdict_vocab()
    seen_normal = False
    for name, options in vocab.items():
        if name not in row:
            continue
        value = row[name]
        if _matches(value, options["abnormal"]):
            return "abnormal"
        if _matches(value, options["normal"]):
            seen_normal = True
    return "normal" if seen_normal else "unknown"


def merge_verdicts(verdicts: Iterable[Verdict]) -> Verdict:
    """同一底稿同一凭证的多行：任一行异常即异常；否则任一行正常即正常；否则未判定（design §8.2）。"""
    seen = set(verdicts)
    if "abnormal" in seen:
        return "abnormal"
    return "normal" if "normal" in seen else "unknown"


def legacy_key(voucher_no: Any, voucher_date: Any) -> str | None:
    """旧行的身份「号|日期」；号或日期为空返回 None（只有号说不清是全年哪一张）。"""
    no = norm_text(voucher_no)
    date_text = norm_text(voucher_date)[:10]
    return f"{no}|{date_text}" if no and date_text else None


def legacy_key_of_voucher(vk: VoucherKey) -> str | None:
    return legacy_key(vk.voucher_no, vk.voucher_date)


def _pick(row: dict, names: tuple[str, ...]) -> Any:
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return v
    return None


@dataclass(frozen=True)
class RowHit:
    wp_id: UUID
    item_id: str
    #: 规范凭证键串；旧行为 None
    vk: str | None
    #: 「号|日期」；身份行也带上（供旧行与身份行互认）
    legacy: str | None
    verdict: Verdict


@dataclass
class ScanResult:
    hits: list[RowHit] = field(default_factory=list)
    truncated: bool = False

    def by_key(self) -> dict[str, list[RowHit]]:
        out: dict[str, list[RowHit]] = {}
        for h in self.hits:
            if h.vk:
                out.setdefault(h.vk, []).append(h)
        return out

    def by_legacy(self) -> dict[str, list[RowHit]]:
        out: dict[str, list[RowHit]] = {}
        for h in self.hits:
            if h.vk is None and h.legacy:
                out.setdefault(h.legacy, []).append(h)
        return out

    def rows_for(self, vk: VoucherKey) -> list[RowHit]:
        """某张凭证的行：身份行按凭证键，旧行按「号|日期」。"""
        key, lk = vk.to_str(), legacy_key_of_voucher(vk)
        return [h for h in self.hits if h.vk == key or (h.vk is None and lk is not None and h.legacy == lk)]


def _row_hit(wp_id: UUID, item_id: str, node: dict) -> RowHit | None:
    meta = node.get("_gt")
    if isinstance(meta, dict) and isinstance(meta.get("vk"), str):
        try:
            vk = VoucherKey.from_str(meta["vk"])
        except ValueError:
            vk = None
        if vk is not None and vk.voucher_no:
            return RowHit(wp_id, item_id, vk.to_str(), legacy_key_of_voucher(vk), row_verdict(node))
    # 没有 `_gt`、或 `_gt` 里没有合法凭证键（手工增补的行）：按凭证号 + 日期认
    lk = legacy_key(_pick(node, _NO_FIELDS), _pick(node, _DATE_FIELDS))
    if lk is not None:
        return RowHit(wp_id, item_id, None, lk, row_verdict(node))
    return None


class _Budget:
    def __init__(self, dicts: int):
        self.dicts = dicts
        self.exhausted = False


def _walk(payload: Any, wp_id: UUID, item_id: str, out: list[RowHit], budget: _Budget) -> None:
    stack: list[tuple[Any, int]] = [(payload, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            if budget.dicts <= 0:
                budget.exhausted = True
                return
            budget.dicts -= 1
            hit = _row_hit(wp_id, item_id, node)
            if hit is not None:
                out.append(hit)
                continue
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth >= MAX_DEPTH:
            continue
        # 逆序压栈 ⇒ 按载荷里的先后顺序出栈（结果顺序稳定、与表格行序一致）
        stack.extend(reversed([(c, depth + 1) for c in children if isinstance(c, (dict, list))]))


def _payloads(remark: str | None, conclusion: str | None) -> Iterable[str]:
    for text in (remark, conclusion):
        s = (text or "").lstrip()
        if s[:1] in ("[", "{"):
            yield s


_PREFILTER = ('%"_gt"%', "%voucherNo%", "%voucher_no%", "%voucherNumber%")


async def scan_voucher_rows(
    db: AsyncSession, project_id: UUID, *, wp_ids: Iterable[UUID] | None = None, max_dicts: int = MAX_DICTS,
) -> ScanResult:
    """扫描本项目（可限定底稿）检查表里的凭证行。查询失败抛出，由调用方决定如何呈现（不当成「没有行」）。"""
    t, wp = CHECKLIST, WorkingPaper.__table__
    conds = [
        t.c.project_id == project_id,
        sa.or_(*[col.like(p) for p in _PREFILTER for col in (t.c.remark, t.c.conclusion)]),
    ]
    ids = list(dict.fromkeys(wp_ids)) if wp_ids is not None else None
    if ids is not None:
        if not ids:
            return ScanResult()
        conds.append(t.c.wp_id.in_(ids))
    stmt = (
        sa.select(t.c.wp_id, t.c.item_id, t.c.remark, t.c.conclusion)
        .select_from(t.join(wp, sa.and_(wp.c.id == t.c.wp_id, wp.c.project_id == project_id, wp.c.is_deleted == sa.false())))
        .where(*conds)
        .order_by(t.c.wp_id, t.c.item_id)
    )
    result = ScanResult()
    budget = _Budget(max_dicts)
    for row in (await db.execute(stmt)).all():
        for text in _payloads(row.remark, row.conclusion):
            if len(text) > MAX_PAYLOAD_CHARS:
                result.truncated = True
                continue
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                continue  # 纯文本结论 / 损坏的 JSON：没有可认的行
            _walk(data, row.wp_id, str(row.item_id), result.hits, budget)
            if budget.exhausted:
                result.truncated = True
                logger.warning("凭证行索引超过 %d 个字典，已截断 project=%s", max_dicts, project_id)
                return result
    return result
