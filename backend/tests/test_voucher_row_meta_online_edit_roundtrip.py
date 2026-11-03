"""凭证检查行元数据 `_gt` 的在线编辑往返（spec voucher-identity-writeback-and-audit-phase 任务 13，发现 N1）。

抽凭回填 / 挂凭导入写进凭证检查行的 `_gt`（凭证键 vk、分录指纹 lfp、阶段 ph、批次 b、来源 src、配对状态 pr、
对方科目 cp、存续核对 sv）不是受管列，OnlyOffice 里看不见。在线编辑保存后 OO→HTML 的合并必须把它原样留在行上，
否则去重、年审只读、按批次撤销全部失效。

往返 = 带 `_gt` 的 store 行 → store 投影（出方向同一函数）→ 改一格（模拟 OO 里编辑）→ 回方向合并 → 断言：
改动生效、`_gt` 与其他非受管键原样、另一行不动。分两层：

* 合并层：每个受管凭证检查 item 用 provider 的合并函数（回方向接通后用的就是它）。
* 镜像层：经 `store_mirror.mirror_projection_into_store`（OO 回调与 adopt-substrate 共用的回方向执行层），
  走注册表分派 + 读基线 + 合并 + 写回，只把数据库换成假会话；投影是整册的（每张受管表各有行）。
  D1-13 / D4-14 / F5-8 接通。D3-7 / D6-6 / D7-7 / F3-7 / F4-8 的 item 不在 store 投影与镜像的处理范围
  （provider 只登记单个 STORE_ITEM_ID、注册表无 dual_store_fn）⇒ OO 里改的这几张表回不到结构化视图。这是在线编辑
  框架的既有缺陷（范围外，design §4 任务 13 勘误），用 strict xfail 钉住：接通后转红，提示删掉标记。
  任务 13 时 D3 / F3 还会把兄弟表的行按主表字段合进主表（同样 strict xfail）；上游 oo-writeback-template-parity-closure
  9.4a~9.4e 把行表引擎改成只合本表的键后不再串表（任务 14 合入时 XPASS(strict) 转红），标记已删，现为普通断言。
* 未接在线编辑的凭证检查表（D2-7 检查工作簿回方向未注册、F1-7 / F2-56 灰度开关关闭）钉住现状，接通时须补用例。
"""
from __future__ import annotations

import copy
import dataclasses
import importlib
import json
import uuid
from typing import Any

import pytest

from app.services.workpaper_sync import phase5_row_table_sheet as engine
from app.services.workpaper_sync.adapters.base import Projection
from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind, managed_field_specs, resolve_json_path
from app.services.workpaper_sync.store_mirror import mirror_projection_into_store

_PKG = "app.services.workpaper_sync"
EDITED = "OO 里改过"


def _mod(name: str) -> Any:
    return importlib.import_module(f"{_PKG}.{name}")


# 受管凭证检查 item（前端凭证检查宿主经 useVoucherCheckFill 写 `_gt` ∩ 后端契约 html_store.item_ids）
#   item → (adapter_id, 契约所在 provider, 行表 spec 所在模块, 回方向是否接通)
INVENTORY: dict[str, tuple[str, str, str, bool]] = {
    "D1-sampling-vouching-rows": ("d1.notes_receivable_detail", "phase5_d1_notes_receivable", "phase5_d1_expansion", True),
    "D4-14-transactions": ("d4.revenue_detail", "phase5_d4_revenue_detail", "", True),
    "F5-8-rows": ("f5.cost_of_sales_detail", "phase5_f5_cost_of_sales", "phase5_f5_cost_of_sales", True),
    "D3-vc-current-rows": ("d3.prepaid_receipts_detail", "phase5_d3_prepaid_receipts", "phase5_d3_expansion", False),
    "D3-vc-post-rows": ("d3.prepaid_receipts_detail", "phase5_d3_prepaid_receipts", "phase5_d3_expansion", False),
    "D6-6-block1-rows": ("d6.contract_assets_detail", "phase5_d6_contract_assets", "phase5_d6_expansion", False),
    "D6-6-block2-rows": ("d6.contract_assets_detail", "phase5_d6_contract_assets", "phase5_d6_expansion", False),
    "D7-7-period-rows": ("d7.contract_liabilities_detail", "phase5_d7_contract_liabilities", "phase5_d7_expansion", False),
    "D7-7-post-rows": ("d7.contract_liabilities_detail", "phase5_d7_contract_liabilities", "phase5_d7_expansion", False),
    "F3-7-debit-rows": ("f3.notes_payable_detail", "phase5_f3_notes_payable", "phase5_f3_notes_payable", False),
    "F3-7-credit-rows": ("f3.notes_payable_detail", "phase5_f3_notes_payable", "phase5_f3_notes_payable", False),
    "F3-7-subsequent-rows": ("f3.notes_payable_detail", "phase5_f3_notes_payable", "phase5_f3_notes_payable", False),
    "F4-8-debit-rows": ("f4.accounts_payable_detail", "phase5_f4_accounts_payable", "phase5_f4_accounts_payable", False),
    "F4-8-credit-rows": ("f4.accounts_payable_detail", "phase5_f4_accounts_payable", "phase5_f4_accounts_payable", False),
}
#: 镜像层会把兄弟表的行合进主表的 entry（整册投影实测）。任务 13 时是 d3.prepaid_receipts_detail / f3.notes_payable_detail，
#: 上游 oo-writeback-template-parity-closure 9.4a~9.4e 修好后为空；再出现串表就直接红，不要加回 xfail
LEAKING_ADAPTERS: frozenset[str] = frozenset()

_NOT_MIRRORED = "回方向不镜像该 item：provider 只登记单个 STORE_ITEM_ID、注册表无 dual_store_fn（范围外，任务 13 勘误）"
_LEAKS = "单 item 镜像把整册投影按主表字段合进主表，兄弟表的行串进主表（范围外，任务 13 勘误）"


def _meta(n: int) -> dict[str, Any]:
    return {
        "vk": f"2025-12-{20 + n:02d}|记|{n:04d}", "lfp": f"lfp-{n:02d}", "ph": "preliminary", "b": f"batch-{n}",
        "src": ["engine", "attach"], "pr": "paired", "cp": "1002", "sv": {"status": "unchanged", "datasetId": "ds-1"},
    }


def _sample(vt: str, n: int, tag: str) -> Any:
    if vt == "amount":
        return 1000.0 + n
    if vt == "date":
        return f"2025-12-{10 + n:02d}"
    if vt == "integer":
        return n
    return f"{tag}-{n}"


def _put(row: dict, path: str, value: Any) -> None:
    """按 `a/b`、`months/0/x` 写值（数字段把上一级建成够长的 list）。"""
    segs = path.split("/")
    cur: Any = row
    for i, seg in enumerate(segs[:-1]):
        child: Any = [] if segs[i + 1].isdigit() else {}
        if seg.isdigit():
            while len(cur) <= int(seg):
                cur.append(copy.deepcopy(child))
            cur = cur[int(seg)]
        else:
            if cur.get(seg) is None:
                cur[seg] = child
            cur = cur[seg]
    if segs[-1].isdigit():
        while len(cur) <= int(segs[-1]):
            cur.append(None)
        cur[int(segs[-1])] = value
    else:
        cur[segs[-1]] = value


def _rows(fields: list[tuple[str, str, str, str]], identity: str, tag: str, n_rows: int, *, meta: bool,
          section: tuple[str, str] = ("", "")) -> list[dict]:
    """fields: (column_key, mode, value_type, json_path)；meta=True 的行带 `_gt` 与一个宿主自有键。"""
    out = []
    for n in range(1, n_rows + 1):
        row: dict = {identity: f"{tag}-{n}"}
        if section[0]:
            row[section[0]] = section[1]
        for _ck, _mode, vt, path in fields:
            _put(row, path, _sample(vt, n, tag))
        if meta:
            row["_gt"] = _meta(n)
            row["hostOnly"] = f"宿主自有-{n}"
        out.append(row)
    return out


def _spec_fields(spec: Any) -> list[tuple[str, str, str, str]]:
    return [(r[0], r[2], r[3], r[4]) for r in managed_field_specs(spec)]


def _row_specs(spec_module: str) -> list[Any]:
    return [s for s in _mod(spec_module).managed_row_table_specs()
            if s.store_kind is not StoreKind.dict and s.row_identity_key]


@dataclasses.dataclass
class _Shape:
    table_key: str
    identity: str
    fields: list[tuple[str, str, str, str]]
    section: tuple[str, str]


def _shape(item: str) -> _Shape:
    if item == "D4-14-transactions":
        d414 = _mod("phase5_d4_14_occurrence")
        return _Shape(d414.ROWS_TABLE_KEY_D414, d414.ROW_IDENTITY_STORE_KEY_D414,
                      [(r[0], r[2], r[3], r[4]) for r in d414.MANAGED_FIELD_SPECS_D414], ("", ""))
    spec = next(s for s in _row_specs(INVENTORY[item][2]) if s.store_item_id == item)
    return _Shape(spec.table_key, spec.row_identity_key, _spec_fields(spec),
                  (spec.row_section_field, spec.row_section_value))


def _edit_target(shape: _Shape) -> tuple[str, str]:
    """改最后一个可编辑文本列（核对结论 / 是否异常 / 备注一类，审计员在 OO 里填的就是它）。"""
    ck, path = next((c, p) for c, mode, vt, p in reversed(shape.fields) if mode == "editable" and vt == "text")
    return ck, path


def _with_edit(projection: Any, shape: _Shape, rid: str) -> tuple[Any, str]:
    ck, path = _edit_target(shape)
    key = next(k for k in projection.values if k == f"{shape.table_key}/{rid}/{ck}")
    values = dict(projection.values)
    values[key] = dataclasses.replace(values[key], value=EDITED)
    return dataclasses.replace(projection, values=values), path


def _contract(item: str) -> Any:
    return _mod(INVENTORY[item][1]).load_contract_from_disk()


def _item_projection(item: str, rows: list[dict], contract: Any) -> Any:
    """该 item 自己的 store 投影（出方向同一函数）。"""
    payload = json.dumps(rows, ensure_ascii=False)
    if item == "D4-14-transactions":
        return _mod("phase5_d4_14_occurrence").build_d414_store_projection(payload, contract=contract)
    spec = next(s for s in _row_specs(INVENTORY[item][2]) if s.store_item_id == item)
    return engine.build_store_projection(spec, payload, contract=contract)


def _merge_item(item: str, projection: Any, base_rows: list[dict]) -> list[dict]:
    """provider 对该 item 的合并函数（D1 / D4 走整册合并函数取该 item 的结果）。"""
    adapter_id, provider, spec_module, _ = INVENTORY[item]
    p = _mod(provider)
    if item == "D1-sampling-vouching-rows":
        return p.merge_projection_into_all_d1_stores(projection=projection, base_by_item={item: base_rows})[item][0]
    if item == "D4-14-transactions":
        return p.merge_projection_into_all_d4_stores(projection=projection, base_by_item={item: base_rows})[item][0]
    if provider in ("phase5_f3_notes_payable", "phase5_f4_accounts_payable", "phase5_f5_cost_of_sales"):
        return p.merge_projection_into_store_rows(projection=projection, base_rows=base_rows, store_item_id=item)[0]
    spec = next(s for s in _row_specs(spec_module) if s.store_item_id == item)
    return engine.merge_projection_into_store_rows(spec, projection=projection, base_rows=base_rows)[0]


def _assert_roundtrip(merged: list[dict], base: list[dict], shape: _Shape, edit_path: str) -> None:
    by_id = {r.get(shape.identity): r for r in merged}
    assert set(by_id) == {b[shape.identity] for b in base}, f"行身份变了：{sorted(map(str, by_id))}"
    first, second = by_id[base[0][shape.identity]], by_id[base[1][shape.identity]]
    assert resolve_json_path(first, edit_path) == EDITED, "OO 里改的那一格没合进来"
    assert first["_gt"] == base[0]["_gt"], "合并丢了 `_gt`"
    assert first["hostOnly"] == base[0]["hostOnly"], "合并丢了宿主自有键"
    assert second == base[1], "没改的那一行被动了"


@pytest.mark.parametrize("item", sorted(INVENTORY))
def test_merge_keeps_row_meta(item: str) -> None:
    shape, contract = _shape(item), _contract(item)
    base = _rows(shape.fields, shape.identity, item, 2, meta=True, section=shape.section)
    projection, edit_path = _with_edit(_item_projection(item, base, contract), shape, base[0][shape.identity])
    _assert_roundtrip(_merge_item(item, projection, copy.deepcopy(base)), base, shape, edit_path)


class _Res:
    def __init__(self, scalar: Any = None, rowcount: int = 0) -> None:
        self._scalar, self.rowcount = scalar, rowcount

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class _FakeSession:
    """只认 store_mirror 发的三种语句：按 (wp, item) 读 remark / 更新 / 插入。"""

    def __init__(self, store: dict[str, str]) -> None:
        self.store = dict(store)
        self.written: set[str] = set()

    async def execute(self, stmt: Any, params: dict | None = None) -> _Res:
        sql, p = " ".join(str(stmt).split()), params or {}
        if sql.startswith("SELECT remark FROM checklist_responses"):
            return _Res(self.store.get(p["item"]))
        if sql.startswith("UPDATE checklist_responses") and p["item"] not in self.store:
            return _Res(rowcount=0)
        if sql.startswith(("UPDATE checklist_responses", "INSERT INTO checklist_responses")):
            self.store[p["item"]] = p["val"]
            self.written.add(p["item"])
            return _Res(rowcount=1)
        raise AssertionError(f"store_mirror 发了没预期的语句：{sql[:120]}")

    async def commit(self) -> None:
        return None


def _entry_world(item: str) -> tuple[dict[str, str], Any, list[dict], _Shape, str, dict[str, set[str]]]:
    """整册：每张受管行表各一行（凭证检查表两行带 `_gt`），返回 store、改过一格的整册投影、基线行等。"""
    adapter_id, provider, spec_module, _ = INVENTORY[item]
    contract, shape = _contract(item), _shape(item)
    base = _rows(shape.fields, shape.identity, item, 2, meta=True, section=shape.section)
    store = {item: json.dumps(base, ensure_ascii=False)}
    ids: dict[str, set[str]] = {item: {r[shape.identity] for r in base}}
    if item == "D4-14-transactions":
        d4 = _mod(provider)  # 兄弟表取 D4-2 主表（手写合并函数，months 是 list）
        sibling = _rows([(r[0], r[2], r[3], r[4]) for r in d4.MANAGED_FIELD_SPECS], d4.ROW_IDENTITY_STORE_KEY,
                        d4.STORE_ITEM_ID, 1, meta=False)
        store[d4.STORE_ITEM_ID] = json.dumps(sibling, ensure_ascii=False)
        ids[d4.STORE_ITEM_ID] = {r[d4.ROW_IDENTITY_STORE_KEY] for r in sibling}
        projection = d4.build_combined_store_projection(store, contract=contract)
    else:
        values: dict[str, Any] = {}
        row_keys: dict[str, tuple[str, ...]] = {}
        for spec in _row_specs(spec_module):
            if spec.store_item_id == item:
                rows = base
            else:
                rows = _rows(_spec_fields(spec), spec.row_identity_key, spec.store_item_id, 1, meta=False,
                             section=(spec.row_section_field, spec.row_section_value))
                prev = json.loads(store.get(spec.store_item_id, "[]"))
                store[spec.store_item_id] = json.dumps(prev + rows, ensure_ascii=False)
                ids.setdefault(spec.store_item_id, set()).update(r[spec.row_identity_key] for r in rows)
            proj = engine.build_store_projection(spec, json.dumps(rows, ensure_ascii=False), contract=contract)
            values.update(proj.values)
            row_keys.update(dict(proj.row_keys))
        projection = Projection(contract_id=contract.contract_id, semantic_version=contract.semantic_version,
                                document_type=contract.document_type, values=values, row_keys=row_keys)
    projection, edit_path = _with_edit(projection, shape, base[0][shape.identity])
    return store, projection, base, shape, edit_path, ids


async def _mirror(item: str, store: dict[str, str], projection: Any) -> _FakeSession:
    session = _FakeSession(store)
    await mirror_projection_into_store(session, adapter_id=INVENTORY[item][0], project_id=uuid.uuid4(),
                                       wp_id=uuid.uuid4(), merged_projection=projection, commit=False)
    return session


def _mirror_params(xfail_when: Any, reason: str) -> list[Any]:
    return [pytest.param(i, marks=pytest.mark.xfail(strict=True, reason=reason)) if xfail_when(i) else i
            for i in sorted(INVENTORY)]


@pytest.mark.parametrize("item", _mirror_params(lambda i: not INVENTORY[i][3], _NOT_MIRRORED))
async def test_mirror_roundtrip_keeps_row_meta(item: str) -> None:
    store, projection, base, shape, edit_path, _ = _entry_world(item)
    session = await _mirror(item, store, projection)
    _assert_roundtrip(json.loads(session.store[item]), base, shape, edit_path)


@pytest.mark.parametrize("item", _mirror_params(lambda i: INVENTORY[i][0] in LEAKING_ADAPTERS, _LEAKS))
async def test_mirror_does_not_leak_rows_across_tables(item: str) -> None:
    store, projection, _, _, _, ids = _entry_world(item)
    session = await _mirror(item, store, projection)
    leaked: dict[str, list[str]] = {}
    for written in session.written:
        rows = json.loads(session.store[written] or "null")
        if not isinstance(rows, list):
            continue
        now = {str(r[k]) for r in rows if isinstance(r, dict) for k in ("id", "rowId", "rowUuid") if r.get(k)}
        extra = sorted(now - ids.get(written, set()))
        if extra:
            leaked[written] = extra
    assert not leaked, f"兄弟表的行串进了别的 item：{leaked}"


def test_inventory_items_are_managed_by_their_entry() -> None:
    """清单里的 item 都是该 entry 的受管 item（D3 / D6 / D7 的清单在伴生扩容模块，entry provider 本身不导出）。"""
    for item, (_adapter, provider, spec_module, _wired) in INVENTORY.items():
        owner = provider if hasattr(_mod(provider), "all_store_item_ids") else spec_module
        assert item in _mod(owner).all_store_item_ids(), f"{item} 不在 {owner}.all_store_item_ids()"
        if spec_module:
            assert any(s.store_item_id == item for s in _row_specs(spec_module)), f"{item} 无行表 spec"


def test_unwired_voucher_check_sheets_stay_unwired() -> None:
    """接通在线编辑的那一天这里转红：给新接的凭证检查表补往返用例（加进 INVENTORY）后再改这里。"""
    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    assert "d2.inspection" not in STORE_MERGE_REGISTRY, "D2-7 检查工作簿的回方向接通了，补 D2-vc-* 往返用例"
    assert not hasattr(_mod("pilot_d2_inspection"), "merge_projection_into_store_rows")
    assert _mod("phase5_f1_prepayment")._INCLUDE_F107 is False, "F1-7 接进在线编辑了，补 F1-vc-* 往返用例"
    assert _mod("phase5_f2_inventory_special")._INCLUDE_F256 is False, "F2-56 接进在线编辑了，补 F2-56-rows 往返用例"
