"""GS4 —— X-3 catalog 登记顺序守卫（先适配器、再 catalog）

spec: `x3-adjustment-entry-import-export` · Wave 0 任务 1.3
_Requirements: 5.1, 5.2, 5.7, 10.1, 10.5_

## 为什么这条守卫必须写成「双向」

design §C4 的 Preflight 是一条**逐条判据**：对 catalog 里每个已启用的 X-3，其
`api_prefix` 必须四步全通 —— `IE_ADAPTER_REGISTRY` 有键 → 模块可解析 →
`_endpoint_for` 三态非 None → `sheet ∈ module.IE_SHEETS`。

但今天这 16 张在 catalog **零启用条目** ⇒「遍历已启用 X-3」这个集合是**空集**
⇒ 只写这一条判据的守卫会因为 `for` 一次都不进而**恒真变绿**。那正是 memory
记的假绿第一类（判据在、作业面空 = 空转），且这种绿会诱导下一轮直接跳过登记。

⇒ 本文件把作业面本身钉住：

- **第①条**（`TestX3RegisteredInCatalog`）断言 16 张必须已启用 —— 当前 16/16
  未启用 ⇒ **全红**，红是预期。
- **第②条**（`TestEnabledX3PassPreflight`）才是 Preflight 实判 —— 当前作用域为空
  ⇒ 空过；任务 9.1 登记后自动转为实判。

①红 ⟺ ②空转，互为对照。变异验证实测（任务 1.3 实录）：把第①条注掉 ⇒ 第②条
全绿 ⇒ 第①条不可省。

## 判据落在行为上，不是「键存在」

父 spec 的教训：初版判据写 `startswith(f"{p}-")` 的宽容分支，让 4 个死前缀
冒充放过，变异检验 RED 0/3 才暴露。所以这里：

- adapter 目标模块**从已注册闭包实取**（`export_fn.__closure__`），不重抄一份
  `_PREFIX_TO_MODULE` 解析规则 —— 任务 6.1 会改那份映射与拼接规则。
- 模块**真 import**、`_endpoint_for` **真调**、`IE_SHEETS` **真查属性**。
- `no_adapter` 用**真跑 `export_tab` / `import_tab`** 的探针判定（见下），
  不是查一下字典里有没有这个键。

## `no_adapter` 为什么值得一条独立的行为探针

后果链（`bulk_export_service` 第 340 行 / `bulk_import_service` 第 761 行）：

    export_tab() → IE_ADAPTER_REGISTRY.get(prefix) 返 None → raise KeyError
    → 上层 `except KeyError` → skip_reason="no_adapter" → 该 sheet 静默出包

全程只有一条 warning 日志，用户拿到的 ZIP 少表且界面无提示。父 spec 已两次踩过
（5 个前缀 / 15 个 sheet）。⇒ 探针把注册表查找那一步**真跑一遍**，在 adapter
边界处用哨兵异常停住（不去跑各循环的 workbook 构建，那属 GS7 的半径），
返回值就是 bulk 服务会写进 manifest 的 `skip_reason`。

探针自带正/负对照（`TestScanSurface` 末两条）：未注册前缀必须被判 `no_adapter`、
已注册前缀必须越过注册表查找。少了这两条，探针自己坏掉时上面的断言会静默空转。

## 实测现状（2026-08-13，本任务落值依据）

- catalog 1215 sheet；16 张目标**各有且仅有一条**条目，`class_code = F-调整分录`。
- 16 张的 `import_export` **键整段缺失**（不是显式 `null`：全库 `null` 计数 0、
  键缺失计数 878）。spec 正文写的「均为 `null`」是 Python 侧 `.get()` 的口径，
  磁盘上是键缺失 —— 两者都落进「未启用」，故本守卫一律按**有效值**判定并在
  失败消息里回报实际形态（`missing` / `null` / `disabled`）。
- 16 个短前缀 16/16 在 `IE_ADAPTER_REGISTRY`（今天指向工厂模块）；三态
  `_endpoint_for` 16/16 非 None；`IE_SHEETS` **无一存在** ⇒ 今天 Preflight 卡在
  第 4 步，前 3 步已通（`TestScanSurface` 把前 3 步钉成非空转的绿）。
- catalog 中使用这 16 个短前缀的**已启用**条目：0 条（L/M/N 已启用前缀为
  l1/l3/l4/l5/n4）。
"""

from __future__ import annotations

import asyncio
import importlib
from types import ModuleType
from typing import Any

import pytest

# ─── 作业面（spec §Introduction 的 16 张 X-3）──────────────────────────────────
#
# 🔴 这 16 个 sheet_code 是本 spec 的作业面声明，Wave 0 阶段无更上游真源可引
# （契约清单里 15 条在 `exempt`、`L6-3` 尚未登记，任务 2.1 才迁入 `sheets`）。
# 为防「打错一个码就把作业面静默缩小」，`TestScanSurface` 逐条把它钉到 catalog
# 的结构事实上（存在 + 唯一 + `class_code = F-调整分录`）。
_TARGET_SHEETS: tuple[str, ...] = (
    "L2-3",
    "L6-3",
    "M1-3",
    "M2-3",
    "M3-3",
    "M4-3",
    "M5-3",
    "M6-3",
    "M7-3",
    "M8-3",
    "M9-3",
    "M10-3",
    "N1-3",
    "N2-3",
    "N3-3",
    "N5-3",
)

_ADJ_CLASS_CODE = "F-调整分录"

#: catalog `import_export` 段的必填字段（design §C4 Step 2 / R5.3）
_REQUIRED_IE_FIELDS: tuple[str, ...] = (
    "enabled",
    "api_prefix",
    "item_id",
    "storage_field",
)

_THREE_STATE_SUFFIXES: tuple[str, ...] = (
    "export-template",
    "export-data",
    "import-data",
)

#: 红色断言统一带这个标记 —— 红是本任务的预期结果，不是回归
_PENDING = "尚未实现（Wave 6 任务 9.1）"

#: 探针用的必然未注册前缀（正对照）
_UNREGISTERED_PROBE_PREFIX = "zz-x3-probe-unregistered"
_PROBE_WP_ID = "00000000-0000-0000-0000-000000000000"


def _short_prefix(sheet_code: str) -> str:
    """`M10-3` → `m10`。短前缀由 sheet_code 派生，不在本文件留第二份映射表。"""
    return sheet_code.split("-", 1)[0].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# catalog 读取（走生产入口 `list_sheets`，不自己解 JSON）
# ═══════════════════════════════════════════════════════════════════════════════


def _ie(entry: dict[str, Any]) -> dict[str, Any]:
    """取 `import_export` 段的 null-safe 形态。

    🔴 不用 `entry.get("import_export", {})`：磁盘上该键**缺失**时它返回 `{}`
    没问题，但一旦任务 9.1 写成显式 `null`，`.get(默认)` 会返回 `None` 再
    `.get` 就 AttributeError（`catalog.list_sheets(import_export_only=True)`
    正是这个写法，本文件因此不依赖它做筛选）。
    """
    return entry.get("import_export") or {}


def _ie_state(entry: dict[str, Any]) -> str:
    """回报 `import_export` 的实际形态，供失败消息区分四种未启用成因。"""
    if "import_export" not in entry:
        return "missing(键缺失)"
    raw = entry.get("import_export")
    if raw is None:
        return "null"
    if not isinstance(raw, dict):
        return f"非对象({type(raw).__name__})"
    if not raw.get("enabled"):
        return f"disabled(enabled={raw.get('enabled')!r})"
    return "enabled"


@pytest.fixture(scope="module")
def catalog_sheets() -> list[dict[str, Any]]:
    from app.services.acnr.catalog import list_sheets

    return list_sheets()


@pytest.fixture(scope="module")
def sheets_by_code(catalog_sheets: list[dict[str, Any]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in catalog_sheets:
        out.setdefault(s.get("sheet_code") or "", []).append(s)
    return out


@pytest.fixture(scope="module")
def enabled_sheets(catalog_sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """catalog 中 `import_export.enabled` 为真的条目（null-safe 自算，不用官方筛选）。"""
    return [s for s in catalog_sheets if _ie(s).get("enabled")]


@pytest.fixture(scope="module")
def enabled_targets(sheets_by_code: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """第②条的作用域 A：16 张目标中**已启用**的那些（当前为空 ⇒ ②空过）。"""
    out: list[dict[str, Any]] = []
    for code in _TARGET_SHEETS:
        for entry in sheets_by_code.get(code, []):
            if _ie(entry).get("enabled"):
                out.append(entry)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 适配器注册表 + Preflight（design §C4 Step 1 的四步，逐步真跑）
# ═══════════════════════════════════════════════════════════════════════════════


def _trigger_adapter_registration() -> dict[str, Any]:
    """填充并返回 `IE_ADAPTER_REGISTRY`。

    注册由各 `register_*_adapters()` 完成，import 模块不保证已触发（`_kfgh` 在
    模块底部自调，`_d` 不一定）⇒ 显式再调一遍（重复注册是幂等覆盖，无害）。
    """
    from app.services.bulk_tab import _d_cycle_adapters, _kfgh_cycle_adapters
    from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY

    for mod in (_d_cycle_adapters, _kfgh_cycle_adapters):
        for fn_name in dir(mod):
            if fn_name.startswith("register_") and fn_name.endswith("_adapters"):
                getattr(mod, fn_name)()
    return IE_ADAPTER_REGISTRY


@pytest.fixture(scope="module")
def adapter_registry() -> dict[str, Any]:
    registry = _trigger_adapter_registration()
    # 反向自检：注册表空 ⇒ 后面每条 Preflight 都会以「无键」为由整体打红，
    # 那是探针坏了而不是被测实现坏了，必须在这一步就区分开。
    assert registry, (
        "IE_ADAPTER_REGISTRY 为空 —— 适配器注册未触发，本文件全部 Preflight 判据失真"
    )
    return registry


def _adapter_target_module_name(prefix: str, registry: dict[str, Any]) -> str | None:
    """取该前缀的 adapter **真实**会 import 的模块名。

    优先从已注册闭包实取（`_make_export_fn` 把 `module_name` 存在 freevar 里）——
    这样任务 6.1 改 `_PREFIX_TO_MODULE` 的值形态或拼接规则时，本守卫跟着变，
    不会因为自己抄了一份旧解析规则而假绿/假红。
    闭包取不到（如 `j3` bespoke 直调命名函数）时回退查映射表。
    """
    spec = registry.get(prefix)
    if spec is not None:
        fn = getattr(spec, "export_fn", None)
        code = getattr(fn, "__code__", None)
        freevars = getattr(code, "co_freevars", ()) or ()
        if "module_name" in freevars and fn.__closure__:
            cell = fn.__closure__[freevars.index("module_name")]
            value = cell.cell_contents
            if isinstance(value, str) and value:
                return value

    from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

    return _PREFIX_TO_MODULE.get(prefix)


def _import_adapter_module(module_name: str) -> ModuleType:
    """真 import。值含 `.` 视为完整点路径（任务 6.1 改指后的形态），否则拼包前缀。"""
    from app.services.bulk_tab._kfgh_cycle_adapters import _MODULE_PKG

    dotted = module_name if "." in module_name else _MODULE_PKG + module_name
    return importlib.import_module(dotted)


def preflight(prefix: str, sheet_code: str, registry: dict[str, Any]) -> list[str]:
    """design §C4 Step 1 的四步 Preflight，返回失败步骤描述（空 = 通过）。

    四步都落在行为上：注册表查键 → 真 import 模块 → 真调 `_endpoint_for` →
    真读 `module.IE_SHEETS`。任一不成立即拒绝登记（R5.1 / R5.8）。
    """
    from app.services.bulk_tab._kfgh_cycle_adapters import _endpoint_for

    failures: list[str] = []

    # Step 1 —— IE_ADAPTER_REGISTRY 有键（否则 bulk 必走 no_adapter 静默跳过）
    if prefix not in registry:
        return [f"step1: `{prefix}` 不在 IE_ADAPTER_REGISTRY ⇒ bulk 必 no_adapter"]

    # Step 2 —— adapter 目标模块可解析
    module_name = _adapter_target_module_name(prefix, registry)
    if not module_name:
        return [f"step2: 判定不出 `{prefix}` 的 adapter 目标模块（闭包与映射表均无）"]
    try:
        module = _import_adapter_module(module_name)
    except Exception as exc:  # noqa: BLE001 —— import 失败是硬失败，记明成因
        return [f"step2: import `{module_name}` 失败: {exc!r}"]

    # Step 3 —— 三态端点在该模块 router 上真解析得到
    missing = [
        suffix
        for suffix in _THREE_STATE_SUFFIXES
        if _endpoint_for(module, prefix, suffix) is None
    ]
    if missing:
        failures.append(
            f"step3: `{module_name}` 上 `/{prefix}/` 三态缺 {missing}"
        )

    # Step 4 —— sheet 在该模块的 IE_SHEETS 白名单内（R4.4 的唯一真源）
    whitelist = getattr(module, "IE_SHEETS", None)
    if whitelist is None:
        failures.append(
            f"step4: `{module_name}` 未声明 IE_SHEETS 白名单（任务 5.1/5.2 补）"
        )
    elif sheet_code not in whitelist:
        failures.append(
            f"step4: `{sheet_code}` 不在 `{module_name}.IE_SHEETS`"
            f"（现有 {sorted(whitelist)}）"
        )
    return failures


# ═══════════════════════════════════════════════════════════════════════════════
# `no_adapter` 行为探针 —— 真跑 export_tab / import_tab 的注册表查找那一步
# ═══════════════════════════════════════════════════════════════════════════════


class _ProbeReachedAdapter(RuntimeError):
    """哨兵：控制流已越过注册表查找、进入适配器调用 ⇒ 不会被标 no_adapter。"""


async def _sentinel_export_fn(*_a: Any, **_kw: Any) -> bytes:
    raise _ProbeReachedAdapter


async def _sentinel_import_fn(*_a: Any, **_kw: Any) -> Any:
    raise _ProbeReachedAdapter


async def _probe_skip_reason(prefix: str, sheet_code: str) -> str | None:
    """返回 bulk 服务会写进 manifest 的 `skip_reason`（`None` = 不跳过）。

    真调生产函数 `export_tab` / `import_tab`，在 adapter 边界处用哨兵停住：
    · `KeyError`             ⇒ 与 `bulk_export_service` 的 `except KeyError`
                               同一分支 ⇒ `skip_reason="no_adapter"`
    · `_ProbeReachedAdapter` ⇒ 已进入适配器 ⇒ 不会被跳过
    其他异常一律上抛（fail-loud，不吞成 None 假绿）。
    """
    from app.services.bulk_tab.single_tab_adapter import (
        IE_ADAPTER_REGISTRY,
        export_tab,
        import_tab,
    )

    real = IE_ADAPTER_REGISTRY.get(prefix)
    if real is not None:
        IE_ADAPTER_REGISTRY[prefix] = real._replace(
            export_fn=_sentinel_export_fn, import_fn=_sentinel_import_fn
        )
    try:
        try:
            await export_tab(
                db=None,  # type: ignore[arg-type] —— 哨兵在用到 db 之前就抛
                wp_id=_PROBE_WP_ID,
                api_prefix=prefix,
                sheet_code=sheet_code,
                mode="template",
            )
        except KeyError:
            return "no_adapter"
        except _ProbeReachedAdapter:
            pass

        try:
            await import_tab(
                db=None,  # type: ignore[arg-type]
                wp_id=_PROBE_WP_ID,
                api_prefix=prefix,
                sheet_code=sheet_code,
                xlsx_bytes=b"",
                strategy="overwrite",
            )
        except KeyError:
            return "no_adapter"
        except _ProbeReachedAdapter:
            pass
        return None
    finally:
        if real is not None:
            IE_ADAPTER_REGISTRY[prefix] = real
        else:
            IE_ADAPTER_REGISTRY.pop(prefix, None)


@pytest.fixture(scope="module")
def skip_reason_probe(adapter_registry: dict[str, Any]) -> dict[str, str | None]:
    """一次 `asyncio.run` 取全部探针结果。

    🔴 不给每条断言各起一个事件循环 —— 共享连接池/单例在多循环下会被污染
    （memory：第二个起报 `NoneType has no attribute send`）。
    """

    async def _collect() -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for code in _TARGET_SHEETS:
            out[code] = await _probe_skip_reason(_short_prefix(code), code)
        out[_UNREGISTERED_PROBE_PREFIX] = await _probe_skip_reason(
            _UNREGISTERED_PROBE_PREFIX, "ZZ-1"
        )
        return out

    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 扫描面自检与前 3 步 Preflight（应全绿；非空转）
# ═══════════════════════════════════════════════════════════════════════════════


class TestScanSurface:
    def test_catalog_parses_and_is_nonempty(
        self, catalog_sheets: list[dict[str, Any]]
    ) -> None:
        """catalog 可解析且规模正常（实测 1215 sheet）。"""
        assert len(catalog_sheets) > 1000, (
            f"catalog 只解析出 {len(catalog_sheets)} 条 sheet —— 扫描面异常，"
            "本文件所有断言都不可信"
        )

    def test_all_targets_exist_uniquely_in_catalog(
        self, sheets_by_code: dict[str, list[dict]]
    ) -> None:
        """16 张目标各有且仅有一条 catalog 条目（R5.2：只填既有条目，无需新建）。"""
        problems: list[str] = []
        for code in _TARGET_SHEETS:
            hits = sheets_by_code.get(code, [])
            if len(hits) != 1:
                problems.append(f"{code}: catalog 命中 {len(hits)} 条（期望 1）")
        assert not problems, (
            "目标 sheet 在 catalog 的条目不唯一/缺失 ⇒ 外科补丁无处落或会撞车：\n"
            + "\n".join(f"  · {p}" for p in problems)
        )

    def test_all_targets_are_adjustment_class(
        self, sheets_by_code: dict[str, list[dict]]
    ) -> None:
        """作业面钉到结构事实上：16 张都是 `F-调整分录`。

        这条挡住「作业面清单打错一个码 ⇒ 第①条静默少判一张」。
        """
        wrong = {
            code: sheets_by_code[code][0].get("class_code")
            for code in _TARGET_SHEETS
            if sheets_by_code.get(code)
            and sheets_by_code[code][0].get("class_code") != _ADJ_CLASS_CODE
        }
        assert not wrong, f"以下目标的 class_code 不是 {_ADJ_CLASS_CODE}: {wrong}"

    def test_target_prefixes_are_registered_as_adapters(
        self, adapter_registry: dict[str, Any]
    ) -> None:
        """16 个短前缀必须在 `IE_ADAPTER_REGISTRY`（R5.1 的「先适配器」那一半）。"""
        missing = sorted(
            {
                _short_prefix(c)
                for c in _TARGET_SHEETS
                if _short_prefix(c) not in adapter_registry
            }
        )
        assert not missing, (
            f"短前缀无 bulk 适配器: {missing} ⇒ 一旦 catalog 登记，批量导出会以 "
            "skip_reason=no_adapter 静默跳过对应 sheet"
        )

    def test_target_prefixes_pass_preflight_steps_1_to_3(
        self, adapter_registry: dict[str, Any]
    ) -> None:
        """Preflight 前 3 步对 16 张**全部**成立（与是否已启用无关）。

        这条让本文件在「零启用」现状下仍有非空转的 Preflight 实判：模块真 import、
        `_endpoint_for` 真调。第 4 步（`IE_SHEETS`）由任务 5.1/5.2 补，故此处排除 ——
        排除方式是只看 step1~step3 的失败项，不是放宽判据。
        """
        offenders: dict[str, list[str]] = {}
        for code in _TARGET_SHEETS:
            failures = [
                f
                for f in preflight(_short_prefix(code), code, adapter_registry)
                if not f.startswith("step4")
            ]
            if failures:
                offenders[code] = failures
        assert not offenders, (
            "以下目标的 adapter 目标模块解析或三态端点解析失败（Preflight step1~3）：\n"
            + "\n".join(f"  · {k}: {'; '.join(v)}" for k, v in offenders.items())
        )

    def test_probe_flags_unregistered_prefix(
        self, skip_reason_probe: dict[str, str | None]
    ) -> None:
        """探针正对照：未注册前缀必须被判 `no_adapter`。

        少了这条，探针一旦坏掉（如 `export_tab` 不再抛 KeyError），下面
        `test_targets_are_not_skipped_as_no_adapter` 会静默全绿。
        """
        assert skip_reason_probe[_UNREGISTERED_PROBE_PREFIX] == "no_adapter", (
            "未注册前缀没被判 no_adapter ⇒ 探针已失效，本文件的 no_adapter 断言在空转"
        )

    def test_probe_reaches_adapter_for_registered_prefix(
        self, adapter_registry: dict[str, Any], skip_reason_probe: dict[str, str | None]
    ) -> None:
        """探针负对照：已注册前缀必须越过注册表查找（否则探针恒判 no_adapter）。"""
        registered = [c for c in _TARGET_SHEETS if _short_prefix(c) in adapter_registry]
        assert registered, "16 个短前缀无一注册 —— 负对照无法成立（见上一条断言）"
        stuck = [c for c in registered if skip_reason_probe[c] == "no_adapter"]
        assert not stuck, (
            f"已注册前缀仍被判 no_adapter: {stuck} ⇒ 探针在注册表查找处误停"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 第①条 —— 作业面钉死（应全红，直到 Wave 6 任务 9.1）
#
# 🔴 不可省：第②条的作用域 = 「已启用的 X-3」，当前为空集 ⇒ 只写第②条会恒真变绿。
# ═══════════════════════════════════════════════════════════════════════════════


class TestX3RegisteredInCatalog:
    def test_all_targets_enabled_in_catalog(
        self, sheets_by_code: dict[str, list[dict]]
    ) -> None:
        """16 张 X-3 的 `import_export.enabled` 必须为真（R5.2）。"""
        not_enabled: list[str] = []
        for code in _TARGET_SHEETS:
            hits = sheets_by_code.get(code, [])
            state = _ie_state(hits[0]) if hits else "条目缺失"
            if state != "enabled":
                not_enabled.append(f"{code}: {state}")
        assert not not_enabled, (
            f"{len(not_enabled)}/{len(_TARGET_SHEETS)} 张 X-3 未在 catalog 启用 I/E"
            f"（{_PENDING}）⇒ 批量与单份两条通路都取不到这些 sheet；"
            "同时使本文件第②条 Preflight 判据的作用域为空 = 恒真空转：\n"
            + "\n".join(f"  · {x}" for x in not_enabled)
            + "\n→ 跑 `python backend/scripts/fix/fix_x3_adjustment_ie_registration.py --check`"
        )

    def test_enabled_entries_carry_required_ie_fields(
        self, sheets_by_code: dict[str, list[dict]]
    ) -> None:
        """`import_export` 四个必填字段齐全且非空（R5.3）。"""
        problems: list[str] = []
        for code in _TARGET_SHEETS:
            hits = sheets_by_code.get(code, [])
            if not hits:
                problems.append(f"{code}: catalog 条目缺失")
                continue
            ie = _ie(hits[0])
            missing = [f for f in _REQUIRED_IE_FIELDS if not ie.get(f)]
            if missing:
                problems.append(f"{code}: 缺 {missing}（当前 {_ie_state(hits[0])}）")
        assert not problems, (
            f"X-3 的 `import_export` 必填字段不全（{_PENDING}）——"
            " 四字段来自 Key_Ledger，缺 `storage_field` 会写错列、"
            "缺 `item_id` 会写进无人读的键：\n"
            + "\n".join(f"  · {p}" for p in problems)
        )

    def test_api_prefix_is_short_cycle_prefix(
        self, sheets_by_code: dict[str, list[dict]]
    ) -> None:
        """`api_prefix` 必须是短前缀（路线 R-D：同一前缀同时驱动两条通路，R1.1）。

        登记成专属长前缀（`l2-interest-payable`）虽能通单份 UI，但那个前缀不在
        `IE_ADAPTER_REGISTRY` ⇒ 批量侧照样 no_adapter。
        """
        problems: list[str] = []
        for code in _TARGET_SHEETS:
            hits = sheets_by_code.get(code, [])
            if not hits:
                problems.append(f"{code}: catalog 条目缺失")
                continue
            actual = _ie(hits[0]).get("api_prefix")
            expected = _short_prefix(code)
            if actual != expected:
                problems.append(f"{code}: api_prefix={actual!r} 期望 {expected!r}")
        assert not problems, (
            f"X-3 的 `api_prefix` 不是短前缀（{_PENDING}）：\n"
            + "\n".join(f"  · {p}" for p in problems)
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 第②条 —— Preflight 实判（当前作用域为空 ⇒ 空过；任务 9.1 登记后转实判）
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnabledX3PassPreflight:
    def test_enabled_targets_pass_preflight(
        self, enabled_targets: list[dict[str, Any]], adapter_registry: dict[str, Any]
    ) -> None:
        """已启用的 X-3，其 `api_prefix` 必须四步 Preflight 全通（R5.1）。

        ⚠️ 作用域 = 已启用的目标。当前 0 条 ⇒ 本条空过，**这正是第①条必须存在的
        理由**：①红时本条无效，①绿时本条才是真判据。
        """
        offenders: dict[str, list[str]] = {}
        for entry in enabled_targets:
            code = entry.get("sheet_code") or "?"
            prefix = _ie(entry).get("api_prefix") or ""
            failures = preflight(prefix, code, adapter_registry)
            if failures:
                offenders[f"{code}(api_prefix={prefix!r})"] = failures
        assert not offenders, (
            "以下已启用 X-3 的 api_prefix 未通过 Preflight ⇒ 登记顺序错误"
            "（R5.1 要求先适配器、再 catalog）：\n"
            + "\n".join(f"  · {k}: {'; '.join(v)}" for k, v in offenders.items())
            + "\n→ 先补 IE_SHEETS/形态 A 端点与 adapter 改指，再跑 Registrar --apply"
        )

    def test_enabled_entries_on_target_prefixes_pass_preflight(
        self, enabled_sheets: list[dict[str, Any]], adapter_registry: dict[str, Any]
    ) -> None:
        """作用域 B：catalog 中**任何**用这 16 个短前缀的启用条目都要 Preflight 通过。

        补上作用域 A 的盲区：把非 X-3 的 sheet（如 `L2-2`）挂到这 16 个短前缀上
        而不进 `IE_SHEETS`，同样会被形态 A 端点以未登记 sheet 拒掉 / 静默回退。
        当前 0 条（L/M/N 已启用前缀为 l1/l3/l4/l5/n4）。
        """
        target_prefixes = {_short_prefix(c) for c in _TARGET_SHEETS}
        offenders: dict[str, list[str]] = {}
        for entry in enabled_sheets:
            prefix = _ie(entry).get("api_prefix") or ""
            if prefix not in target_prefixes:
                continue
            code = entry.get("sheet_code") or "?"
            failures = preflight(prefix, code, adapter_registry)
            if failures:
                offenders[f"{code}(api_prefix={prefix!r})"] = failures
        assert not offenders, (
            "以下启用条目挂在本 spec 的短前缀上但未通过 Preflight：\n"
            + "\n".join(f"  · {k}: {'; '.join(v)}" for k, v in offenders.items())
        )

    def test_targets_are_not_skipped_as_no_adapter(
        self, skip_reason_probe: dict[str, str | None]
    ) -> None:
        """16 张的 bulk 通路不得落到 `skip_reason == "no_adapter"`（R5.7）。

        ⚠️ 与上面两条不同，本条作用域是**全部 16 张**（不以启用为前提）：
        `no_adapter` 只取决于短前缀有没有适配器，今天就可判、今天就应绿。
        它出现即证明登记顺序被颠倒（catalog 先行、适配器未就绪）。
        """
        skipped = {
            code: reason
            for code, reason in skip_reason_probe.items()
            if code in _TARGET_SHEETS and reason is not None
        }
        assert not skipped, (
            "以下 X-3 在 bulk 通路会被静默跳过（用户拿到的 ZIP 少表且无提示）：\n"
            + "\n".join(f"  · {k}: skip_reason={v}" for k, v in skipped.items())
            + "\n→ 登记顺序错误：必须先注册 Bulk_Adapter，再写 catalog（R5.1）"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
