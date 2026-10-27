"""高级查询 ``acnr_targets``：唯一的解析 + 取值编排（acnr-foundation-defect-closure T14，design §2.2 / §2.3）。

两步，全有或全无：

1. ``resolve_acnr_targets``：逐个顺序调用 ``AddressingService.resolve_target``（同一会话不能并发）。遇到第一个
   ``resolve_unavailable`` 立即停止 ⇒ 503 ``RESOLVE_UNAVAILABLE``；整批套 ``ACNR_BATCH_DEADLINE_S`` 时限，超时同样 503
   （R2-F9）。全部解析完后逐项分类（``classify_target``），任一项不接受 ⇒ 422 ``ACNR_TARGETS_REJECTED`` + 逐项
   ``issues``（与前端 ``formulaRefIssues.ts`` 同构）。两种拒绝都不取数。
2. ``read_acnr_target_values``：对已接受的目标逐个经 ``wp_cell_target.read_entry_cell`` 取值（取值唯一读取函数
   ``wp_cell_reader.resolve_wp_cell`` 在其下一层），目录用 ``effective_catalog``（锁定项目为锁定目录）并显式传
   ``index=``；返回 ``acnr_results`` 块，``items`` 与请求逐项对应、顺序相同、重复项各答一次。

本模块不读 ``parsed_data``、不调 ``extract_custom_cells``（``test_acnr_targets_single_reader`` 用 AST 钉住）。
端点接线、项目鉴权与年度补齐在 T15（``QueryOrchestrator`` / 构建器三端点）。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from app.services.acnr.limits import ACNR_BATCH_DEADLINE_S
from app.services.acnr.reasons import TARGET_REJECT_REASONS
from app.services.acnr.wp_cell_target import effective_catalog, read_entry_cell
from app.services.custom_query.addressing_service import (
    ERR_RESOLVE_UNAVAILABLE,
    AddressingService,
    ResolvedTarget,
    addressing_service,
)

if TYPE_CHECKING:
    from app.services.acnr.catalog import CatalogIndex

__all__ = [
    "ACNR_TARGETS_REJECTED", "RESOLVE_UNAVAILABLE", "TargetIssue", "classify_target", "read_acnr_target_values",
    "resolve_acnr_targets",
]

ACNR_TARGETS_REJECTED = "ACNR_TARGETS_REJECTED"
RESOLVE_UNAVAILABLE = "RESOLVE_UNAVAILABLE"
_UNAVAILABLE_MESSAGE = "地址解析服务暂不可用，未执行查询，请稍后重试"
#: 候选最多给几条（design §2.3 ambiguous「带候选 ≤5」）
_MAX_CANDIDATES = 5


@dataclass(frozen=True)
class TargetIssue:
    """一项被拒绝的目标（字段与 ``formulaRefIssues.ts`` 同构：ref / message，另带 error_code 与候选）。"""

    ref: str
    error_code: str
    message: str
    candidates: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref, "error_code": self.error_code, "message": self.message,
            "candidates": list(self.candidates), "required_context": list(self.required_context),
        }


def _candidate_ids(raw: list[dict] | None) -> tuple[str, ...]:
    out: list[str] = []
    for cand in raw or []:
        addr = cand.get("addr_id") if isinstance(cand, dict) else cand
        if addr:
            out.append(str(addr))
    return tuple(out[:_MAX_CANDIDATES])


def _issue(target: ResolvedTarget, code: str, *, detail: str | None = None,
           candidates: tuple[str, ...] = (), context: tuple[str, ...] = ()) -> TargetIssue:
    message = detail or TARGET_REJECT_REASONS[code]
    return TargetIssue(ref=target.raw, error_code=code, message=message, candidates=candidates,
                       required_context=context)


def classify_target(target: ResolvedTarget) -> TargetIssue | None:
    """design §2.3 分类表：返回 None 表示接受（L1 底稿单元格），否则为拒绝原因。判据只读结果字段，按表序首个命中。"""
    if target.error == ERR_RESOLVE_UNAVAILABLE or target.result is None:
        return _issue(target, "resolve_unavailable")
    res = target.result
    if res.error == "external_module_not_resolved":
        return _issue(target, "external_namespace")
    if res.source_layer == "V1":
        return _issue(target, "unsupported_domain")
    if res.source_layer == "L3":
        return _issue(target, "runtime_entry")
    if res.entry_type == "sheet":
        return _issue(target, "sheet_level")
    if res.deprecated is True:
        detail = res.reason or TARGET_REJECT_REASONS["deprecated"].format(replaced_by=res.replaced_by or "")
        return _issue(target, "deprecated", detail=detail,
                      candidates=(res.replaced_by,) if res.replaced_by else ())
    if res.error == "ambiguous":
        return _issue(target, "ambiguous", detail=res.reason or None, candidates=_candidate_ids(res.candidates),
                      context=tuple(res.required_context or ()))
    if not res.found:
        return _issue(target, "unresolvable", candidates=_candidate_ids(res.candidates))
    if res.entry_type == "cell" and res.source_layer == "L1_cell":
        return None
    # found 但不是 L1 底稿单元格（如 runtime_cell 未标 L3）：同样不取值，不默认接受
    return _issue(target, "unresolvable", detail=f"{TARGET_REJECT_REASONS['unresolvable']}（类型 {res.entry_type}）")


def _unavailable(issues: list[TargetIssue]) -> HTTPException:
    return HTTPException(status_code=503, detail={
        "error_code": RESOLVE_UNAVAILABLE, "message": _UNAVAILABLE_MESSAGE,
        "issues": [i.to_dict() for i in issues],
    })


async def resolve_acnr_targets(
    targets: list[str], *, project_id, db, addressing: AddressingService | None = None,
) -> list[ResolvedTarget]:
    """逐项解析并分类；全部接受才返回（与输入同序），否则抛 503 / 422（都不取数）。"""
    if not targets:
        return []
    service = addressing or addressing_service
    resolved: list[ResolvedTarget] = []
    try:
        async with asyncio.timeout(ACNR_BATCH_DEADLINE_S):
            for raw in targets:
                item = await service.resolve_target(raw, project_id=project_id, db=db)
                if item.error == ERR_RESOLVE_UNAVAILABLE:
                    raise _unavailable([_issue(item, "resolve_unavailable")])
                resolved.append(item)
    except TimeoutError:
        pending = targets[len(resolved)] if len(resolved) < len(targets) else targets[-1]
        raise _unavailable([TargetIssue(ref=pending, error_code="resolve_unavailable",
                                        message=TARGET_REJECT_REASONS["resolve_unavailable"])]) from None
    issues = [issue for issue in (classify_target(t) for t in resolved) if issue is not None]
    if issues:
        raise HTTPException(status_code=422, detail={
            "error_code": ACNR_TARGETS_REJECTED,
            "message": f"所选单元格中有 {len(issues)} 项无法取值，未执行查询",
            "issues": [i.to_dict() for i in issues],
        })
    return resolved


def _display_label(cell: dict, sheet: dict) -> str:
    """目录统一显示名（T29 由生成器写入 cell 的 ``display_label``）；写入前用 sheet 显示名 › 坐标 语义名 过渡。"""
    if cell.get("display_label"):
        return str(cell["display_label"])
    head = sheet.get("display_label") or sheet.get("addr_id") or ""
    tail = " ".join(x for x in (cell.get("cell_address"), cell.get("semantic_label")) if x)
    return f"{head} › {tail}" if tail else str(head)


def _jump_route(sheet: dict, wp_id) -> str | None:
    """与 ``resolve_instance`` 同形态；读的是父底稿时也带 ``sheet=`` 定位到该表（R2-N7）。"""
    if wp_id is None:
        return None
    template = sheet.get("jump_route_template") or ""
    route = template.replace("{wp_id}", str(wp_id)) if template else f"/workpapers/{wp_id}"
    if "sheet=" not in route:
        route += ("&" if "?" in route else "?") + f"sheet={sheet.get('sheet_code', '')}"
    return route


def _state_fields(read) -> dict[str, Any]:
    if read.state == "ok":
        return {"state": "ok", "value": str(read.value), "text": read.raw, "reason_code": None, "reason": None}
    if read.state == "blocked" and read.reason_code == "non_numeric":
        return {"state": "text", "value": None, "text": read.raw, "reason_code": "non_numeric", "reason": read.reason}
    return {"state": read.state, "value": None, "text": None, "reason_code": read.reason_code, "reason": read.reason}


async def read_acnr_target_values(
    resolved: list[ResolvedTarget], *, project_id, year: int | None, db,
) -> dict[str, Any] | None:
    """已接受目标逐项取值 ⇒ ``acnr_results`` 块；没有目标返回 None（响应里不输出该键）。"""
    if not resolved:
        return None
    cat: CatalogIndex = await effective_catalog(db, project_id)
    items: list[dict[str, Any]] = []
    for target in resolved:
        cell = cat.cells_by_addr_id.get(target.addr_id or "")
        sheet = cat.sheets_by_addr_id.get((cell or {}).get("parent_addr_id", ""))
        if cell is None or sheet is None:
            raise LookupError(f"目录版本 {cat.registry_version} 中找不到已解析的地址 {target.addr_id}")
        got = await read_entry_cell(db, project_id=project_id, year=year, entry=sheet,
                                    cell=cell["cell_address"], index=cat)
        read = got.read
        items.append({
            "input": target.raw,
            "addr_id": target.addr_id,
            "display_label": _display_label(cell, sheet),
            "formula_ref": cell.get("formula_ref"),
            **_state_fields(read),
            "source": {
                "wp_code": got.bound_wp_code, "sheet_code": sheet.get("sheet_code"), "sheet_key": read.sheet_key,
                "cell": cell["cell_address"], "wp_id": str(read.wp_id) if read.wp_id else None,
                "jump_route": _jump_route(sheet, read.wp_id),
            },
        })
    return {"registry_version": cat.registry_version, "year": year, "items": items}
