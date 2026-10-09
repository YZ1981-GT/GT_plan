# -*- coding: utf-8 -*-
"""entry 契约路径单源 + 伴生扩容面必须真的进契约 —— 两条平台级不变量。

spec: d3-sync-coverage-via-row-table-engine（补建判据；缺口由 2026-09-30 复盘现算发现）

═══ 第一条：契约路径只能走 `contracts.contract_path_for` ═══

`phase5_entry_orchestration.build_orchestration()` 的默认 `contract_file_path()` 曾自己拼
`_BACKEND_ROOT / "backend/data/workpaper_sync_contracts/{adapter_id}.json"`，而
`_BACKEND_ROOT` 本身**就是** `<repo>/backend` ⇒ `backend` 拼了两次。5 个没传
`contract_file_path_fn` 的 entry（d2/d3/d5/d6/d7）因此拿到
`<repo>/backend/backend/data/workpaper_sync_contracts/*.json`。

🔴 这个错不会报错，只会**静默写错地方**：`generate_phase5_*_contract.py --apply` 打印
`[apply] wrote` 然后把契约写进影子目录，而运行时 `load_contract()` 走的是正确的
`contract_path_for` ⇒ **真正的磁盘契约永远不被重生成**。工作树里 `backend/backend/data/`
真实存在（同类错路径写出来的 `guard_assertion_grades.json`）即其化石证据。

注意 entry 模块**自己**也定义过一份正确的 `contract_file_path()`（如
`phase5_d3_prepaid_receipts.py` 里 `return contract_path_for(ADAPTER_ID)`），但文件末尾
`contract_file_path = _orch.contract_file_path` 把它覆盖了 ⇒ 那份是死代码，看源码会被骗。
所以本判据**调用**它取真值，而不是读源码文本。

═══ 第二条：伴生扩容模块声明的 sheet 必须真的进契约 ═══

`phase5_*_expansion.py` 声明「本 entry 还有哪几张受管 sheet」，但这些声明必须被 entry 的
`build_contract_payload()` 真的拼进 `sheets[]` 才算接线。D3 实测就是没接：4 个灰度开关全
`True`、`managed_row_table_specs()` 返回 6 个 spec，而契约里只有 1 张 `d32-managed`。

🔴 **为什么现有的两把锁都看不见它**：

* `assert_contract_file_matches_source()` 比「磁盘契约 vs 源 payload」—— 两边**漏的是同样
  4 张** ⇒ 逐字节相等 ⇒ 报绿。它测的是「有没有人只改一边」，测不出「两边一起缺」。
* `assert_specs_align_with_contract_sheets()` 能看见（它比 spec 集合 vs 契约集合），但它
  **没有任何生产调用方**，只被各家自己 lane 的测试调用 ⇒ D3 那家的 lane 测试
  (`test_d3_expansion.py`) 确实红了，可那是「一家的红」，读的人会当成该 lane 的欠账，
  而不是「这条不变量在平台层没人守」。实测该红从 commit `57c78b53c` 起就在 HEAD 上，
  而 CI 的 `backend-tests` 是 `pytest backend/tests/ -x` 全量带 `-x`。

⇒ 本文件把第二条提成**跨 entry 普查**：只要某 entry 有伴生扩容模块，它的 spec 集合就必须
  与磁盘契约对齐；少一家都打红，且新增 expansion 模块无法静默脱管（见
  `test_expansion_coverage_table_has_no_gap`）。
"""
from __future__ import annotations

import functools
import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - 与同目录其它判据一致的引导
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("DB_DISABLE_SSL", "True")

_PKG = "app.services.workpaper_sync"
_PKG_DIR = _BACKEND / "app" / "services" / "workpaper_sync"


#: 扫描下限。低于它说明模块目录改名 / 文本筛选口径失效 ⇒ 判据在空转，必须打红而不是默默通过。
#: 现算值 50（`contract_file_path` 可调用且有 `ADAPTER_ID`/`PILOT_ADAPTER_ID` 的模块数）。
_MIN_ENTRIES_SCANNED = 40


def _is_doubled_backend(path: Path) -> bool:
    """路径里 `backend` 出现两次以上 —— 即本文件要根治的那个形态。"""
    return [p.lower() for p in path.parts].count("backend") > 1


@functools.lru_cache(maxsize=1)
def _entry_modules_with_contract_path() -> tuple[tuple[str, ModuleType], ...]:
    """所有暴露可调用 `contract_file_path()` 的 entry 模块。

    🔴 先按**源码文本**粗筛再 import：整个包有 260+ 个模块，全量 import 会把本文件拖到
       分钟级。粗筛只用来缩小 import 面，真值一律靠**调用**取（见模块 docstring 末段）。
    """
    out: list[tuple[str, ModuleType]] = []
    for path in sorted(_PKG_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "contract_file_path" not in text:
            continue
        mod = importlib.import_module(f"{_PKG}.{path.stem}")
        if callable(getattr(mod, "contract_file_path", None)):
            out.append((path.stem, mod))
    return tuple(out)


def _adapter_id_of(mod: ModuleType) -> str | None:
    for name in ("ADAPTER_ID", "PILOT_ADAPTER_ID"):
        value = getattr(mod, name, None)
        if isinstance(value, str) and value:
            return value
    return None


def test_entry_scan_is_not_silently_empty() -> None:
    """反空转：扫到的 entry 数不得低于下限（否则下面两条在测空集合）。"""
    found = _entry_modules_with_contract_path()
    assert len(found) >= _MIN_ENTRIES_SCANNED, (
        f"只扫到 {len(found)} 个暴露 contract_file_path() 的 entry 模块，低于下限 "
        f"{_MIN_ENTRIES_SCANNED} —— 目录改名或文本粗筛口径失效，本文件的其余判据在空转。"
    )


def test_entry_contract_file_path_is_single_sourced() -> None:
    """🔴 每个 entry 的 `contract_file_path()` 必须逐字等于 `contract_path_for(adapter_id)`。

    同时断言路径里 `backend` 只出现一次、且文件真的存在 —— 「拼对了」与「指向真文件」
    是两件事，只查前者会漏掉拼对但指向空目录的情形。
    """
    from app.services.workpaper_sync.contracts import contract_path_for

    offenders: list[str] = []
    checked = 0
    for stem, mod in _entry_modules_with_contract_path():
        adapter_id = _adapter_id_of(mod)
        if adapter_id is None:
            continue
        checked += 1
        actual = Path(mod.contract_file_path())
        expected = contract_path_for(adapter_id)
        if actual != expected:
            offenders.append(f"{stem}: 现算 {actual} ≠ contract_path_for {expected}")
        elif _is_doubled_backend(actual):
            offenders.append(f"{stem}: 路径里 backend 出现多次 -> {actual}")
        elif not actual.exists():
            offenders.append(f"{stem}: 路径对但文件不存在 -> {actual}")

    assert checked >= _MIN_ENTRIES_SCANNED, (
        f"只有 {checked} 个模块同时具备 contract_file_path() 与 adapter_id，低于下限。"
    )
    assert offenders == [], (
        "以下 entry 的契约路径没走唯一真源 `contracts.contract_path_for`：\n  "
        + "\n  ".join(offenders)
        + "\n🔴 自己拼 `<backend_root>/backend/data/...` 会把 backend 拼两次，"
        "生成脚本 --apply 会静默写进影子目录，真正的磁盘契约永远不被重生成。"
    )


def test_doubled_backend_path_is_actually_rejected() -> None:
    """变异反证：把当年那个错路径喂给判据的谓词，必须被判违规。

    少了这条，上面那条可能因为 `_is_doubled_backend` 写错（例如恒 False）而恒绿 ——
    那它就不是在测「路径有没有拼两次」这个轴。
    """
    from app.services.workpaper_sync.contracts import contract_path_for

    buggy = _BACKEND / "backend/data/workpaper_sync_contracts/d3.prepaid_receipts_detail.json"
    assert _is_doubled_backend(buggy), f"谓词没识别出错路径：{buggy}"
    assert not buggy.exists(), (
        f"影子路径 {buggy} 竟然存在 —— 说明还有工具在往 backend/backend/ 下写契约，"
        "先查出是谁写的再改本判据。"
    )
    good = contract_path_for("d3.prepaid_receipts_detail")
    assert not _is_doubled_backend(good), f"谓词把正确路径也判成违规：{good}"
    assert good.exists(), f"正确路径下的契约文件不存在：{good}"


# ═══════════════════════════════════════════════════════════════════════════
# 第二条：伴生扩容模块声明的 sheet 必须真的进契约
# ═══════════════════════════════════════════════════════════════════════════

#: 伴生扩容模块 → 它所属的 entry 模块。
#:
#: 🔴 这张表不是白名单（白名单会让下一家静默脱管），而是**配对表**：
#:    `test_expansion_coverage_table_has_no_gap` 反向断言磁盘上每个
#:    `phase5_*_expansion.py` 都必须在这里出现。新增一家忘登记 ⇒ 打红。
_EXPANSION_ENTRIES: dict[str, str] = {
    "phase5_d1_expansion": "phase5_d1_notes_receivable",
    "phase5_d3_expansion": "phase5_d3_prepaid_receipts",
    "phase5_d5_expansion": "phase5_d5_receivables_financing",
    "phase5_d6_expansion": "phase5_d6_contract_assets",
    "phase5_d7_expansion": "phase5_d7_contract_liabilities",
}

#: 不是「某家的」扩容面，而是三家共用的 sheets[] 构建实现 ⇒ 不参与配对。
_SHARED_EXPANSION_HELPERS: frozenset[str] = frozenset({"phase5_d567_expansion_contract"})


def _discovered_expansion_modules() -> set[str]:
    return {
        p.stem
        for p in _PKG_DIR.glob("phase5_*expansion*.py")
        if p.stem not in _SHARED_EXPANSION_HELPERS
    }


def test_expansion_coverage_table_has_no_gap() -> None:
    """🔴 反向：磁盘上每个伴生扩容模块都必须在配对表里（两侧差集都要为空）。"""
    discovered = _discovered_expansion_modules()
    declared = set(_EXPANSION_ENTRIES)
    assert discovered, "一个伴生扩容模块都没扫到 —— glob 口径失效，下面的判据在空转。"
    missing = sorted(discovered - declared)
    stale = sorted(declared - discovered)
    assert not missing, (
        f"这些伴生扩容模块没在 _EXPANSION_ENTRIES 里登记，会静默脱离本文件的普查：{missing}"
    )
    assert not stale, f"_EXPANSION_ENTRIES 里这些模块磁盘上已不存在，请删掉：{stale}"


@pytest.mark.parametrize(
    ("expansion_name", "entry_name"),
    sorted(_EXPANSION_ENTRIES.items()),
    ids=sorted(_EXPANSION_ENTRIES),
)
def test_expansion_specs_are_wired_into_contract_payload(
    expansion_name: str, entry_name: str
) -> None:
    """🔴 扩容面已启用的每个 sheet_key 必须出现在 entry 现算 payload 的 `sheets[]` 里。

    这条直接钉「接线」本身：D3 的缺口就是 `build_contract_payload()` 从不读扩容面，
    于是 6 个已启用 spec 一张都没进 payload，而两把既有的锁都看不见（见模块 docstring）。
    """
    exp = importlib.import_module(f"{_PKG}.{expansion_name}")
    entry = importlib.import_module(f"{_PKG}.{entry_name}")

    specs = exp.managed_row_table_specs()
    if not specs:
        pytest.skip(f"{expansion_name} 的灰度开关全关，无可断言的 sheet（合法形态）")

    payload_keys = {s.get("sheet_key") for s in (entry.build_contract_payload().get("sheets") or [])}
    spec_keys = {s.sheet_key for s in specs}
    missing = sorted(spec_keys - payload_keys)
    assert not missing, (
        f"{expansion_name} 声明并已启用的受管 sheet 没进 {entry_name} 的契约 payload：{missing}\n"
        f"  payload 现有 sheet_key: {sorted(k for k in payload_keys if k)}\n"
        "🔴 接线方式见 d5/d6/d7：在 build_contract_payload 的 sheets[] 里 splice "
        "`phase5_d567_expansion_contract.build_expansion_sheets(_exp.managed_row_table_specs())`。"
    )


@pytest.mark.parametrize(
    ("expansion_name", "entry_name"),
    sorted(_EXPANSION_ENTRIES.items()),
    ids=sorted(_EXPANSION_ENTRIES),
)
def test_expansion_alignment_guard_passes_against_disk_contract(
    expansion_name: str, entry_name: str
) -> None:
    """🔴 各家自己的对齐守卫对**磁盘**契约也必须通过（上一条只查源 payload）。

    两条都要：只查源 payload 会漏掉「源接上了但磁盘契约没重生成」，
    只查磁盘会漏掉「两边一起缺」。
    """
    exp = importlib.import_module(f"{_PKG}.{expansion_name}")
    entry = importlib.import_module(f"{_PKG}.{entry_name}")
    guard = getattr(exp, "assert_specs_align_with_contract_sheets", None)
    assert callable(guard), f"{expansion_name} 缺 assert_specs_align_with_contract_sheets"
    guard(entry.load_contract_from_disk())


def test_at_least_one_expansion_is_actually_enabled() -> None:
    """反空转：至少一家扩容面真的开了开关，否则上面两条会被 `skip` / 空集合架空。"""
    enabled: dict[str, int] = {}
    for expansion_name in _EXPANSION_ENTRIES:
        exp = importlib.import_module(f"{_PKG}.{expansion_name}")
        count = len(exp.managed_row_table_specs())
        if count:
            enabled[expansion_name] = count
    assert enabled, (
        "所有伴生扩容模块的灰度开关都是关的 —— 本文件第二条不变量此刻无实际覆盖对象，"
        "请确认是不是有人整批关了开关。"
    )
