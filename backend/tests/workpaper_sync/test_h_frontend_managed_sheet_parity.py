"""前端 H 受管清单 ↔ 后端 provider / registry 的 **parity 守卫**。

spec: `h-cycle-sync-foundation-and-first-canary`

═══ 为什么需要这条守卫 ═══════════════════════════════════════════════════════

前端 `sync/hManagedSheets.ts` 是**手写**清单（平台当前没有把「受管 sheet 短码」下发前端
的通路：`workpaperSyncManifest.generated.ts` 只带 AST 抽出的 sheet 字面量/表达式，
render-config 与 store-projection 都不下发这个集合）。手写就会漂移 —— F 循环 5 条 lane
的宿主内联 map 注释写「从 provider 派生」而实际是硬编码，**没有任何判据能报红**。

本守卫把那份手写清单逐字钉死在后端三个真源上：
  · `excelName`   == provider `all_managed_sheet_names()`
  · `sheetKey`    == provider 行表 spec 的 `sheet_key`
  · `storeItemId` == `store_item_registry` 对应 plan 的 item_id
  · `entryId`     == provider `ENTRY_ID`
后端增删受管面而前端没跟上（或反之），这里立刻红。

🔴 **不比「H 循环 9 条 entry 都在清单里」** —— 当前只有 canary H9 的 provider 落地，
   H2/H3/H4/H5/H6/H7/H8/H10 八条 lane 尚未实现。断言「9 条齐全」会把未完成工作伪装成
   缺陷；本守卫只断言「清单里的每一条都真实存在且逐字一致」+「provider 已落地的受管
   sheet 都在清单里」，两个方向都不留缺口，且不预设未来进度。

H1 是同循环既有 pilot（`pilot_h1_grouped_dynamic`，`pilot_*` 范式、adapter 已注册），
**不属本轮受管面**，故不参与本 parity（前端清单也刻意不含它，避免两套范式并进同一判定）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import phase5_h4_engineering_materials as h4
from app.services.workpaper_sync import phase5_h6_asset_disposal_clearing as h6
from app.services.workpaper_sync import phase5_h8_right_of_use_assets as h8
from app.services.workpaper_sync import phase5_h9_lease_liabilities as h9
from app.services.workpaper_sync import store_item_registry as sir

# ═══════════════════════════════════════════════════════════════════════════
# 前端清单解析（不引 node —— 直接从 TS 源里取结构化字面量）
# ═══════════════════════════════════════════════════════════════════════════

_FE_ROOT = Path(__file__).resolve().parents[3] / "audit-platform" / "frontend"
_MANAGED_TS = (
    _FE_ROOT / "src" / "components" / "workpaper" / "sync" / "hManagedSheets.ts"
)

#: 逐条 `{ entryId: '…', code: '…', … }` 对象字面量
_ENTRY_RE = re.compile(
    r"\{\s*"
    r"entryId:\s*'(?P<entryId>[^']+)',\s*"
    r"code:\s*'(?P<code>[^']+)',\s*"
    r"sheetKey:\s*'(?P<sheetKey>[^']+)',\s*"
    r"kind:\s*'(?P<kind>[^']+)',\s*"
    r"excelName:\s*'(?P<excelName>[^']+)',\s*"
    r"storeItemId:\s*'(?P<storeItemId>[^']+)',\s*"
    r"\}",
    re.S,
)

_WIRED_RE = re.compile(
    r"H_OO_WIRED_ROWS_CODES:\s*readonly\s+string\[\]\s*=\s*Object\.freeze\(\[(?P<body>.*?)\]\)",
    re.S,
)


def _strip_line_comments(src: str) -> str:
    """去掉 `//` 行注释。

    🔴 必须先去注释再匹配：`_ENTRY_RE` 要求字段之间只有空白，而条目里写注释是**正常**的
    （H6 那条就解释了「excelName 不带科目前缀，不按 H9 构词法推演」）。不去注释会让
    「加了一行注释」表现成「该条目从清单里消失」—— 报错信息指向 parity 失配，排查方向
    完全错。本函数只处理行注释：清单里不出现 `/* */`，也不出现含 `//` 的字符串字面量
    （entryId 是 `xlsx/gt-…` 单斜杠）。
    """
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in src.splitlines())


def _parse_frontend_managed_sheets() -> list[dict[str, str]]:
    assert _MANAGED_TS.exists(), f"前端受管清单不存在：{_MANAGED_TS}"
    src = _MANAGED_TS.read_text(encoding="utf-8")
    # 只解析 H_MANAGED_SHEETS 的数组体，避免把 docstring 里的示例误抓
    start = src.index("export const H_MANAGED_SHEETS")
    body = _strip_line_comments(src[start:])
    rows = [m.groupdict() for m in _ENTRY_RE.finditer(body)]
    assert rows, "未从 hManagedSheets.ts 解析出任何受管条目（正则与源形态失配？）"
    return rows


def _parse_frontend_wired_codes() -> list[str]:
    src = _MANAGED_TS.read_text(encoding="utf-8")
    m = _WIRED_RE.search(src)
    assert m, "未解析出 H_OO_WIRED_ROWS_CODES"
    return re.findall(r"'([^']+)'", m.group("body"))


# ═══════════════════════════════════════════════════════════════════════════
# 后端真源
# ═══════════════════════════════════════════════════════════════════════════

#: 本轮受管面的 provider（lane provider 落地后在此追加，parity 自动覆盖）。
#: h9 = canary（foundation spec）· h6 = 发布链首例（lane3）· h4 = 首个四级表头宽表（lane2）
#: 🔴 h4 **受管但未接桥** —— `test_wired_codes_have_delivered_contract` 只覆盖已接桥的，
#:    受管面的一致性由 excelName / sheetKey / storeItemId 三条双向判据覆盖。
#: h8 = 58 列全 1:1 零 template-only（lane2），同样**受管但未接桥**
_PROVIDERS: tuple[Any, ...] = (h9, h6, h4, h8)


def _backend_managed_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for mod in _PROVIDERS:
        for spec in mod.managed_row_table_specs():
            rows.append(
                {
                    "entryId": mod.ENTRY_ID,
                    "sheetKey": spec.sheet_key,
                    "excelName": spec.managed_sheet,
                    "storeItemId": spec.store_item_id,
                }
            )
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 判据
# ═══════════════════════════════════════════════════════════════════════════


def test_frontend_excel_names_match_provider_managed_sheet_names() -> None:
    """`excelName` 集合 == 各 provider `all_managed_sheet_names()` 之并。"""
    fe = {r["excelName"] for r in _parse_frontend_managed_sheets()}
    be: set[str] = set()
    for mod in _PROVIDERS:
        be |= set(mod.all_managed_sheet_names())
    assert fe == be, (
        "前端受管清单的 excelName 与后端 all_managed_sheet_names() 不一致\n"
        f"  仅前端有：{sorted(fe - be)}\n"
        f"  仅后端有：{sorted(be - fe)}"
    )


def test_frontend_sheet_keys_match_provider_row_table_specs() -> None:
    """`sheetKey` 集合 == 各 provider 行表 spec 的 `sheet_key` 集合。"""
    fe = {r["sheetKey"] for r in _parse_frontend_managed_sheets()}
    be = {r["sheetKey"] for r in _backend_managed_rows()}
    assert fe == be, f"sheetKey 失配：仅前端 {sorted(fe - be)} / 仅后端 {sorted(be - fe)}"


def test_frontend_store_item_ids_match_registry() -> None:
    """`storeItemId` 必须是 `store_item_registry` 里对应 plan 真实登记的 item_id。"""
    for row in _parse_frontend_managed_sheets():
        # 直接按 provider 的 ADAPTER_ID 取 plan —— 唯一确定的映射。
        # （早期版本按 provider_module 前缀 + adapter_id 首段模糊匹配，`or` 分支
        #  可能误命中同前缀的另一条 plan，判据会失去区分力。）
        mod = next(m for m in _PROVIDERS if m.ENTRY_ID == row["entryId"])
        plan = sir.STORE_MERGE_REGISTRY.get(mod.ADAPTER_ID)
        assert plan is not None, (
            f"registry 里没有 adapter_id={mod.ADAPTER_ID!r} 的 plan"
            f"（已登记 {sorted(sir.STORE_MERGE_REGISTRY)}）"
        )
        registered = {item.item_id for item in plan.items}
        assert row["storeItemId"] in registered, (
            f"{row['code']}: 前端声明 storeItemId={row['storeItemId']!r}，"
            f"但 registry plan {plan.adapter_id!r} 只登记了 {sorted(registered)}"
        )


def test_frontend_entry_ids_are_real_provider_entry_ids() -> None:
    """`entryId` 必须逐字等于某个 provider 的 `ENTRY_ID`（不得自造）。"""
    known = {mod.ENTRY_ID for mod in _PROVIDERS}
    for row in _parse_frontend_managed_sheets():
        assert row["entryId"] in known, (
            f"{row['code']}: entryId={row['entryId']!r} 不是任何已落地 provider 的 ENTRY_ID"
            f"（已知 {sorted(known)}）"
        )


def test_every_backend_managed_row_is_declared_in_frontend() -> None:
    """反向：provider 已落地的受管行表**都**必须在前端清单里（否则前端切不进 OO）。"""
    fe = {(r["entryId"], r["sheetKey"]) for r in _parse_frontend_managed_sheets()}
    be = {(r["entryId"], r["sheetKey"]) for r in _backend_managed_rows()}
    missing = be - fe
    assert not missing, (
        "后端已受管但前端清单缺失（这些 sheet 在 UI 上无法进入在线编辑）："
        f"{sorted(missing)}"
    )


def test_wired_codes_are_subset_of_managed_codes() -> None:
    """已接桥短码必须是受管短码的子集 —— 不得声明一个不受管的 sheet「已接桥」。"""
    managed = {r["code"] for r in _parse_frontend_managed_sheets()}
    wired = set(_parse_frontend_wired_codes())
    assert wired <= managed, f"声明已接桥但不在受管清单：{sorted(wired - managed)}"


def test_wired_codes_have_delivered_contract() -> None:
    """已接桥的 entry 必须有**落盘的契约 JSON** —— 否则前端进 OO 时后端无契约可用。"""
    codes = {r["code"]: r for r in _parse_frontend_managed_sheets()}
    contracts_dir = (
        Path(__file__).resolve().parents[2] / "data" / "workpaper_sync_contracts"
    )
    for code in _parse_frontend_wired_codes():
        row = codes[code]
        mod = next(m for m in _PROVIDERS if m.ENTRY_ID == row["entryId"])
        path = contracts_dir / f"{mod.ADAPTER_ID}.json"
        assert path.exists(), f"{code}: 已声明接桥但契约未落盘 {path}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        sheets = payload.get("sheets") or []
        keys = {s.get("sheet_key") for s in sheets}
        assert row["sheetKey"] in keys, (
            f"{code}: 契约 {path.name} 的 sheet_key 集合 {sorted(keys)} "
            f"不含前端声明的 {row['sheetKey']!r}"
        )


@pytest.mark.parametrize("row", _parse_frontend_managed_sheets(), ids=lambda r: r["code"])
def test_each_declared_row_is_row_kind_or_adjudication(row: dict[str, str]) -> None:
    """`kind` 只允许两个取值 —— 新增第三种桥时必须显式扩这条判据，不得静默混入。"""
    assert row["kind"] in {"rows", "adjudication"}, f"未知 kind={row['kind']!r}"
