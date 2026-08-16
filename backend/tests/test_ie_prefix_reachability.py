"""导入导出前缀可达性守卫 —— Wave 4 Task 17

spec: workpaper-import-export-lifecycle-closure（R4.2 / R5.2 / R5.4）

## 这条守卫为什么必须在后端

前端 `CycleImportExportDropdown` 只会拼**路径形态**::

    /api/workpapers/{wp_id}/{api_prefix}/{export-template|export-data|import-data}

而某个 `api_prefix` 的端点究竟长什么样、有没有被 ``include_router``，
**只有真实的 FastAPI 路由表知道**。前端 vitest / Volar / get_diagnostics
三层都不校验 URL 可达性 —— 挂一个不可达的前缀，四层全绿，只有用户点下去才 404。

2026-08-12 本 spec 就真踩了这个坑：给 H5TabDetail / H5TabAdjustment 挂了
``api-prefix="h5"``，全绿通过，实测 ``/api/workpapers/{wp_id}/h5/*``
**在 2113 条运行期路由里完全不存在** —— h5 的真实端点是第三形态
``POST /api/h5/export-data``（wp_id 在 body 里），由
``app/routers/h5_oil_gas_assets.py`` 提供；``_h5_import_export.py`` 工厂声明了
路径形态但从未注册。

## 判据：真实路由表，不是 grep

`_h5_import_export.py` 里**确实有** ``@router.post(".../h5/export-data")`` 字样，
所以任何「grep 后端源码里有没有这个路径」的判据都会绿 —— 那正是 memory 记的
假绿第二源。此处一律以 ``app.routes`` 枚举为准。
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_REGISTRY_DIR = (
    _REPO / "audit-platform/frontend/src/components/workpaper/shared"
)

_ACTIONS = ("export-template", "export-data", "import-data")

#: 已知的「非路径形态」前缀 —— registry 有登记，但三态路径一条都不可达。
#:
#: 它们的能力由 ``/api/{prefix}/*`` 形态的专属 router 提供（wp_id 走 body / Form），
#: 故**禁止给它们挂 CycleImportExportDropdown**。前端守卫
#: ``ieWiringIntegrity.spec.ts`` 的 ``NON_PATH_FORM_PREFIXES`` 与此清单双向锁死。
#:
#: 🔴 这个清单只许缩小，不许扩大：新增即意味着又有一个前缀的路径形态没注册。
NON_PATH_FORM_PREFIXES: frozenset[str] = frozenset({"h5", "n4"})

#: 「sheet 无关」前缀 —— registry 声明了多个 sheet，但后端三端点**不接受 sheet 参数**，
#: 语义是整表导出。
#:
#: 🔴 为什么必须单独钉死：FastAPI 对未声明的 query 参数是**静默丢弃**。给这类前缀的
#: 第二个 sheet 挂 dropdown 不会 404、不会报错，只会导出和第一个 sheet 一样的内容 ——
#: 用户以为拿到的是当前页数据。四层守卫全绿，只有比对导出文件才发现。
#:
#: 实测（2026-08-12）：69 个多 sheet 前缀里 66 个接受 sheet 参数，只有 l4 不接受
#: （`app/routers/l4_bonds_payable.py` 的三个 handler 签名里没有 sheet）。
#: ⇒ 这类前缀在前端**最多允许一个挂载点**，挂在主表上。
SHEET_AGNOSTIC_PREFIXES: frozenset[str] = frozenset({"l4"})


def _registry_prefixes() -> list[str]:
    """从前端 registry（门面 + 生成文件）抽出全部 apiPrefix。"""
    src = ""
    for name in (
        "cycleImportExportRegistry.ts",
        "cycleImportExportRegistry.generated.ts",
    ):
        path = _REGISTRY_DIR / name
        assert path.is_file(), f"registry 文件缺失：{path}（守卫必须打红而非跳过）"
        src += path.read_text(encoding="utf-8") + "\n"
    prefixes = sorted(set(re.findall(r"apiPrefix:\s*'([^']+)'", src)))
    assert prefixes, "registry 里抽不出任何 apiPrefix —— 抽取正则失效，守卫已空转"
    return prefixes


@pytest.fixture(scope="module")
def real_paths() -> set[str]:
    """运行期真实路由路径集合。"""
    from app.main import app  # 延迟 import：构建 app 较重

    paths = {getattr(r, "path", "") for r in app.routes}
    paths.discard("")
    # 反向自检：路由表规模异常小 ⇒ app 没装配好，后面的断言会全体假绿
    assert len(paths) > 500, (
        f"运行期只枚举到 {len(paths)} 条路由，app 未正常装配 —— "
        "此时任何『不可达』结论都不可信"
    )
    return paths


def test_registry_prefixes_are_reachable_or_declared(real_paths: set[str]) -> None:
    """registry 每个前缀：要么三态路径全可达，要么在非路径形态清单里。"""
    unreachable: dict[str, list[str]] = {}
    for prefix in _registry_prefixes():
        missing = [
            act
            for act in _ACTIONS
            if f"/api/workpapers/{{wp_id}}/{prefix}/{act}" not in real_paths
        ]
        if missing:
            unreachable[prefix] = missing

    undeclared = {
        p: acts for p, acts in unreachable.items() if p not in NON_PATH_FORM_PREFIXES
    }
    assert not undeclared, (
        "以下 registry 前缀的三态路径不可达，且未登记在 NON_PATH_FORM_PREFIXES：\n"
        + "\n".join(f"  {p}: 缺 {', '.join(acts)}" for p, acts in undeclared.items())
        + "\n→ 给它们挂 CycleImportExportDropdown 会 404。"
        " 要么注册路径形态 router，要么登记进清单并禁止挂 dropdown。"
    )


def test_declared_non_path_prefixes_really_unreachable(real_paths: set[str]) -> None:
    """反向自检：清单里的前缀确实不可达（否则清单 stale，白挡了能用的前缀）。"""
    wrongly_listed = [
        p
        for p in sorted(NON_PATH_FORM_PREFIXES)
        if all(f"/api/workpapers/{{wp_id}}/{p}/{a}" in real_paths for a in _ACTIONS)
    ]
    assert not wrongly_listed, (
        f"以下前缀已在 NON_PATH_FORM_PREFIXES，但路径形态其实已可达：{wrongly_listed}\n"
        "→ 说明后来注册了路径形态 router，应把它移出清单并允许挂 dropdown"
    )


def test_non_path_prefixes_have_alternative_endpoints(real_paths: set[str]) -> None:
    """清单里的前缀必须真有替代形态端点 —— 否则它是彻底的死能力，不是形态差异。"""
    for prefix in sorted(NON_PATH_FORM_PREFIXES):
        alt = sorted(
            p
            for p in real_paths
            if p.startswith(f"/api/{prefix}/") and any(a in p for a in _ACTIONS)
        )
        assert len(alt) == len(_ACTIONS), (
            f"{prefix} 登记为非路径形态，但 /api/{prefix}/* 下只找到 {len(alt)} 条"
            f" I/E 端点（期望 {len(_ACTIONS)}）：{alt}\n"
            "→ 若一条都没有，它不是『形态不同』而是『能力缺失』，应另行处置"
        )


def test_frontend_guard_list_matches(real_paths: set[str]) -> None:
    """与前端守卫的 NON_PATH_FORM_PREFIXES 双向锁死（防两处各改一半）。"""
    guard = (
        _REPO
        / "audit-platform/frontend/src/components/workpaper/__tests__"
        / "ieWiringIntegrity.spec.ts"
    )
    assert guard.is_file(), f"前端接线守卫缺失：{guard}"
    text = guard.read_text(encoding="utf-8")
    match = re.search(r"NON_PATH_FORM_PREFIXES\s*=\s*\[([^\]]*)\]", text)
    assert match, "前端守卫里找不到 NON_PATH_FORM_PREFIXES 声明"
    fe = set(re.findall(r"'([^']+)'", match.group(1)))
    assert fe == set(NON_PATH_FORM_PREFIXES), (
        f"前后端非路径形态清单不一致：后端={sorted(NON_PATH_FORM_PREFIXES)} "
        f"前端={sorted(fe)}"
    )


def test_no_dropdown_mounted_on_non_path_prefixes() -> None:
    """扫全部 .vue：确认没有任何挂载点用了非路径形态前缀。

    与前端守卫同判据，但在后端再查一遍 —— 前端守卫若被删/被 skip，这里仍会打红。
    """
    wp_root = _REPO / "audit-platform/frontend/src/components/workpaper"
    assert wp_root.is_dir(), f"底稿组件目录缺失：{wp_root}"

    offenders: list[str] = []
    scanned = 0
    for path in wp_root.rglob("*.vue"):
        if "__tests__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "CycleImportExportDropdown" not in text:
            continue
        scanned += 1
        for tag in re.findall(r"<CycleImportExportDropdown[\s\S]*?>", text):
            m = re.search(r'(?:^|\s)api-prefix\s*=\s*"([^"]*)"', tag)
            if m and m.group(1) in NON_PATH_FORM_PREFIXES:
                offenders.append(f"{path.relative_to(wp_root).as_posix()} → {m.group(1)}")

    # 反向自检：扫描面为 0 说明选择器失效，断言会假绿
    assert scanned > 0, "没扫到任何挂 dropdown 的 .vue —— 扫描逻辑失效，断言已空转"
    assert not offenders, (
        "以下挂载点用了非路径形态前缀（点击必 404）：\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_reachability_snapshot_is_recorded() -> None:
    """把可达性快照落成断言，防「不可达数量悄悄增长」。

    2026-08-12 实证：registry 72 前缀，70 个三态全可达，2 个（h5/n4）不可达。
    """
    prefixes = _registry_prefixes()
    assert len(prefixes) >= 72, (
        f"registry 前缀数 {len(prefixes)} 少于基线 72 —— 覆盖面回退了"
    )
    assert len(NON_PATH_FORM_PREFIXES) <= 2, (
        f"非路径形态前缀增至 {len(NON_PATH_FORM_PREFIXES)} 个（基线 2）"
        " ⇒ 又有前缀的路径形态没注册，或有人拿清单当垃圾桶"
    )


def test_registry_json_snapshot_readable() -> None:
    """生成文件可解析（防生成器产出坏文件导致上面全体 ANCHOR-MISS）。"""
    gen = _REGISTRY_DIR / "cycleImportExportRegistry.generated.ts"
    text = gen.read_text(encoding="utf-8")
    entries = re.findall(r"apiPrefix:\s*'([^']+)',\s*sheets:\s*\[([^\]]*)\]", text)
    assert len(entries) >= 60, f"生成文件只解析出 {len(entries)} 条，疑似被截断"
    for prefix, sheets_src in entries:
        sheets = re.findall(r"'([^']+)'", sheets_src)
        assert sheets, f"生成文件里 {prefix} 的 sheets 为空 —— 生成器产出异常"
        # 顺带确认 JSON 化不报错（供其他工具消费）
        json.dumps({prefix: sheets})


# ═══════════════════════════════════════════════════════════════════════════
# sheet 参数一致性（R4.2 / R5.4）
#
# dropdown 会把 `sheet` 传给后端。若后端 handler 签名里没有该参数，FastAPI
# **静默丢弃** —— 这是「不报错但结果错」的一类，比 404 更难发现。
# ═══════════════════════════════════════════════════════════════════════════


def _accepts_sheet(endpoint) -> bool:  # noqa: ANN001
    """handler 是否在签名或 body 模型里接受 sheet/sheet_type。"""
    import inspect

    try:
        params = inspect.signature(endpoint).parameters
    except (TypeError, ValueError):
        return False
    for name, par in params.items():
        if name in {"sheet", "sheet_type", "sheet_name"}:
            return True
        fields = getattr(par.annotation, "model_fields", None)
        if fields and ({"sheet", "sheet_type"} & set(fields)):
            return True
    return False


def _registry_multi_sheet_prefixes() -> dict[str, list[str]]:
    """registry 中 sheets 数 > 1 的前缀 → sheets。"""
    src = ""
    for name in (
        "cycleImportExportRegistry.ts",
        "cycleImportExportRegistry.generated.ts",
    ):
        src += (_REGISTRY_DIR / name).read_text(encoding="utf-8") + "\n"
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"apiPrefix:\s*'([^']+)',\s*sheets:\s*\[([^\]]*)\]", src):
        sheets = re.findall(r"'([^']+)'", m.group(2))
        if len(sheets) > 1:
            out[m.group(1)] = sheets
    assert out, "抽不出任何多 sheet 前缀 —— 抽取失效，断言已空转"
    return out


@pytest.fixture(scope="module")
def prefix_accepts_sheet() -> dict[str, bool]:
    """前缀 → 其三态端点中是否有任一接受 sheet 参数。"""
    from app.main import app

    acc: dict[str, bool] = {}
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        m = re.match(
            r"^/api/workpapers/\{wp_id\}/([\w-]+)/(" + "|".join(_ACTIONS) + r")$", path
        )
        if not m:
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        acc[m.group(1)] = acc.get(m.group(1), False) or _accepts_sheet(endpoint)
    assert acc, "没枚举到任何三态端点 —— app 未装配好"
    return acc


def test_multi_sheet_prefixes_accept_sheet_param(
    prefix_accepts_sheet: dict[str, bool],
) -> None:
    """多 sheet 前缀的后端必须接受 sheet 参数，否则须登记为 sheet 无关。"""
    offenders: list[str] = []
    for prefix, sheets in sorted(_registry_multi_sheet_prefixes().items()):
        if prefix not in prefix_accepts_sheet:
            continue  # 路径形态不可达，由另一条断言负责
        if prefix_accepts_sheet[prefix]:
            continue
        if prefix in SHEET_AGNOSTIC_PREFIXES:
            continue
        offenders.append(f"{prefix}（registry 声明 {len(sheets)} 个 sheet）")
    assert not offenders, (
        "以下前缀 registry 声明了多个 sheet，但后端不接受 sheet 参数"
        "（dropdown 传的 sheet 会被静默丢弃，导出内容与页面不符）：\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n→ 要么给后端加 sheet 参数，要么登记进 SHEET_AGNOSTIC_PREFIXES"
        " 并把前端挂载点收敛到一个"
    )


def test_sheet_agnostic_list_not_stale(prefix_accepts_sheet: dict[str, bool]) -> None:
    """反向自检：清单里的前缀确实不接受 sheet（防清单 stale 白挡能用的前缀）。"""
    wrongly_listed = [
        p
        for p in sorted(SHEET_AGNOSTIC_PREFIXES)
        if prefix_accepts_sheet.get(p, False)
    ]
    assert not wrongly_listed, (
        f"以下前缀已在 SHEET_AGNOSTIC_PREFIXES，但后端其实接受 sheet 参数："
        f"{wrongly_listed}\n→ 应移出清单，并允许按 sheet 分别挂 dropdown"
    )


def test_sheet_agnostic_prefixes_have_single_mount() -> None:
    """sheet 无关前缀在前端最多一个挂载点（多挂会导出同样内容、误导用户）。"""
    wp_root = _REPO / "audit-platform/frontend/src/components/workpaper"
    counts: dict[str, list[str]] = {p: [] for p in SHEET_AGNOSTIC_PREFIXES}
    scanned = 0
    for path in wp_root.rglob("*.vue"):
        if "__tests__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "CycleImportExportDropdown" not in text:
            continue
        scanned += 1
        for tag in re.findall(r"<CycleImportExportDropdown[\s\S]*?>", text):
            m = re.search(r'(?:^|\s)api-prefix\s*=\s*"([^"]*)"', tag)
            if m and m.group(1) in counts:
                sheet = re.search(r'(?:^|\s)sheet\s*=\s*"([^"]*)"', tag)
                counts[m.group(1)].append(
                    f"{path.relative_to(wp_root).as_posix()}"
                    f"(sheet={sheet.group(1) if sheet else '?'})"
                )
    assert scanned > 0, "没扫到任何挂 dropdown 的 .vue —— 扫描失效"

    offenders = {p: v for p, v in counts.items() if len(v) > 1}
    assert not offenders, (
        "以下 sheet 无关前缀挂了多个 dropdown（各页导出内容相同，误导用户）：\n"
        + "\n".join(f"  {p}: {', '.join(v)}" for p, v in offenders.items())
    )


def test_sheet_agnostic_snapshot() -> None:
    """清单规模基线 —— 只许下调。"""
    assert len(SHEET_AGNOSTIC_PREFIXES) <= 1, (
        f"sheet 无关前缀增至 {len(SHEET_AGNOSTIC_PREFIXES)} 个（基线 1）"
        " ⇒ 又有多 sheet 前缀的后端漏了 sheet 参数"
    )

# ═══════════════════════════════════════════════════════════════════════════
# X-3 专属前缀的 sheet 可达性现状登记（GS3 扩展）
# spec: x3-adjustment-entry-import-export —— 任务 1.5（R4.3 / R4.4 / R4.5 / R4.6）
#
# 为什么扩这个文件而不是另建一个：本节的判据实现（运行期路由表 + `_accepts_sheet`
# 的 ``inspect.signature``）与上面 GS3 的不变量是同一条判据的两端。抄第二份实现，
# 两处必然分叉 —— 那时「多 sheet 前缀必须收 sheet」和「X-3 前缀收没收 sheet」会给出
# 互相矛盾的结论，而没人知道该信哪个。
#
# 判据一律取运行期对象（路由表 / 模块属性 / 函数签名），**不 grep 源码**：
# `sheet` 这个词出现在注释、docstring、局部变量名、甚至 `# sheet: 待加` 里
# 都会骗过 grep，而 FastAPI 只认 handler 签名。
#
# 🔴 本节曾有三条【现状登记】断言 —— **Wave 3（任务 5.1 / 5.2）施加完毕，已按各自断言消息
#    的指引反转**（2026-08-14）：
#    ① `test_l2_m1_shape_b_handlers_lack_sheet_param`
#       → `test_l2_m1_shape_b_handlers_accept_sheet_param`（六个 handler 必须声明 `sheet`），
#         `_X3_SHEET_PARAM_PENDING` 改空集；
#    ② `test_x3_dedicated_prefix_whitelists_lack_x3_code`
#       → `test_x3_dedicated_prefix_whitelists_contain_x3_code`（16 / 16 必须声明 `IE_SHEETS`
#         且各含其 X-3），`_X3_WHITELIST_DISCOVERABLE_BASELINE` 由 6 上调到 16；
#    ③ `test_other_14_x3_dedicated_prefixes_accept_sheet_param`
#       → `test_all_16_x3_dedicated_prefixes_accept_sheet_param`（作业面由 42 → 48 个 handler，
#         这一条是①的机械后果：它的期望数由 `16 - len(_X3_SHEET_PARAM_PENDING)` 派生）。
#    反转是**收紧**不是放宽：施加前钉「没有」、施加后钉「必须有」，两侧都不留「随便」。
#    改名而不是留旧名：名字写着 `lack` 却断言「必须有」，下一轮读的人会照名字理解成放宽了。
# ═══════════════════════════════════════════════════════════════════════════

#: 16 张 X-3 的专属长前缀（形态 B：``/api/{长前缀}/{wp_id}/{三态}``）。
#:
#: 来源：design §逐张两列实测值（R1.2 的逐 sheet 运行期实测表）。
#: 短前缀与 X-3 码一律**从长前缀派生**（`m10-other-equity-instruments` → `m10` → `M10-3`），
#: 不另抄一份映射表 —— 抄第二份就有第二个真源，改一处漏一处。
_X3_DEDICATED_LONG_PREFIXES: tuple[str, ...] = (
    "l2-interest-payable",
    "l6-special-payables",
    "m1-dividends-payable",
    "m2-paid-in-capital",
    "m3-treasury-stock",
    "m4-capital-reserve",
    "m5-surplus-reserve",
    "m6-retained-earnings",
    "m7-special-reserve",
    "m8-general-risk-reserve",
    "m9-other-comprehensive-income",
    "m10-other-equity-instruments",
    "n1-deferred-tax-assets",
    "n2-taxes-payable",
    "n3-deferred-tax-liabilities",
    "n5-income-tax-expense",
)

#: R4.3 的作业面（任务 5.2）：这两个长前缀的**六个**形态 B handler。
#:
#: FastAPI 对未声明的 query 参数是**静默丢弃**：施加前给它们的 X-3 挂 dropdown，
#: 请求会 200、文件会下载，内容却是 L2-2 / M1-2 —— 父 spec 在 L4-3 上踩过同一个坑
#: （四层守卫全绿，只有对着导出文件逐列核对才发现），并因此撤销了 L4-3 的挂载点。
_TASK_52_LONG_PREFIXES: frozenset[str] = frozenset(
    {"l2-interest-payable", "m1-dividends-payable"}
)

#: 「尚未声明 `sheet`」的待办集 —— **任务 5.2 已施加完毕，故为空集**（2026-08-14）。
#:
#: 🔴 只许缩小、不许再填回去：非空即意味着又有专属前缀的形态 B handler 丢了 `sheet`
#: 声明，那时下面 `test_all_16_x3_dedicated_prefixes_accept_sheet_param` 的期望数会
#: 被这个集合**自动减小**（它按 `16 - len(_X3_SHEET_PARAM_PENDING)` 派生）⇒ 把前缀写进
#: 这里就等于把它从实判里摘出去，正解是给 handler 加参数。
_X3_SHEET_PARAM_PENDING: frozenset[str] = frozenset()

#: 白名单可发现性基线 —— host 模块级常量里能读出 sheet 码的专属前缀数。
#:
#: 施加前实测（2026-08-13）：6 / 16 可发现（`l2` `l6` `n1` `n2` `n3` `n5`），
#: 其余 10 个把白名单放在 service 层（`m1` ~ `m10` 各自的 `_SHEET_CONFIGS`
#: / `EXPORT_SHEETS` 等，形态逐个不同 —— 这正是 design C2 要用 `IE_SHEETS`
#: 收敛成唯一真源的原因）。
#: 施加后（任务 5.1 / 5.2 收口，2026-08-14）：**16 / 16**，每个 host 模块都声明了 `IE_SHEETS`。
#:
#: 这个基线是**反空转锚点**：扫描实现一旦失效（正则改坏 / 只扫到空命名空间），
#: 可发现数会掉到 0，而「白名单不含 X-3」会因此恒真变绿。只许上调。
_X3_WHITELIST_DISCOVERABLE_BASELINE = 16


def _x3_short_prefix(long_prefix: str) -> str:
    """`m10-other-equity-instruments` → `m10`。"""
    return long_prefix.split("-", 1)[0]


def _x3_code(long_prefix: str) -> str:
    """`m10-other-equity-instruments` → `M10-3`。"""
    return f"{_x3_short_prefix(long_prefix).upper()}-3"


def _sheet_codes_in(value: object, pattern: re.Pattern[str], depth: int = 0) -> set[str]:
    """从运行期常量值里递归抽出 ``{CYCLE}-N`` 形态的 sheet 码（归一化到码本身）。

    归一化的必要性：白名单里的取值形态并不统一 —— `'L2-2 明细表'`（码 + 中文标题）、
    `'M2-2-listed'`（码 + 变体后缀）、`{'N3-2': {...}}`（码作 dict 键）三种都有。
    只有归一化到 `L2-2` / `M2-2` / `N3-2` 才能和 X-3 码直接比对。
    """
    out: set[str] = set()
    if depth > 4:
        return out
    if isinstance(value, str):
        m = pattern.match(value)
        if m:
            out.add(m.group(1))
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            out |= _sheet_codes_in(k, pattern, depth + 1)
            out |= _sheet_codes_in(v, pattern, depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        for v in value:
            out |= _sheet_codes_in(v, pattern, depth + 1)
    return out


@pytest.fixture(scope="module")
def x3_shape_b_matrix() -> dict[str, dict[str, tuple[bool, str]]]:
    """长前缀 → {三态动作: (handler 是否声明 sheet, 宿主模块点路径)}。

    形态 B = ``/api/{长前缀}/{wp_id}/{三态}``（X-3 施加前唯一存在的形态）。
    与上面 `prefix_accepts_sheet` 的区别有两处，都是有意的：
    - 这里**逐端点**记录，不做 or 聚合 —— 「三态里只有一个收 sheet」必须能被看见；
    - 这里带宿主模块，白名单断言要顺它取运行期模块属性。
    """
    from app.main import app  # 与上面两个 fixture 共用同一个 app 实例（模块 import 缓存）

    pattern = re.compile(
        r"^/api/([\w-]+)/\{wp_id\}/(" + "|".join(_ACTIONS) + r")$"
    )
    matrix: dict[str, dict[str, tuple[bool, str]]] = {}
    for route in app.routes:
        m = pattern.match(getattr(route, "path", "") or "")
        if not m or m.group(1) not in _X3_DEDICATED_LONG_PREFIXES:
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        matrix.setdefault(m.group(1), {})[m.group(2)] = (
            _accepts_sheet(endpoint),
            getattr(endpoint, "__module__", "?"),
        )
    # 反向自检：一条都没枚举到 ⇒ app 未装配好或路径形态变了，本节全部结论不可信
    assert matrix, (
        "没枚举到任何 X-3 专属前缀的形态 B 三态端点 —— app 未装配好或形态 B 路径"
        " 已改版；此时『白名单不含 X-3』『六个 handler 没有 sheet』都会恒真变绿"
    )
    return matrix


def test_x3_dedicated_shape_b_endpoints_resolved(
    x3_shape_b_matrix: dict[str, dict[str, tuple[bool, str]]],
) -> None:
    """反空转锚点：16 个专属前缀在运行期各有 3 条形态 B 端点、各有宿主模块。

    本节其余断言全部建立在这张矩阵上。少一条端点就意味着对应结论是「没查到」
    而不是「查过了没问题」—— 这条先打红，避免下面的绿是空转出来的。
    """
    missing = {
        p: sorted(set(_ACTIONS) - set(x3_shape_b_matrix.get(p, {})))
        for p in _X3_DEDICATED_LONG_PREFIXES
        if len(x3_shape_b_matrix.get(p, {})) != len(_ACTIONS)
    }
    assert not missing, (
        "以下 X-3 专属前缀的形态 B 三态端点不齐（design §逐张两列实测值记为 16/16 齐全）：\n"
        + "\n".join(f"  {p}: 缺 {', '.join(a)}" for p, a in missing.items())
        + "\n→ 要么端点被删/改名（本节结论作废，须重取实测值），要么长前缀清单 stale"
    )
    total = sum(len(v) for v in x3_shape_b_matrix.values())
    assert total == len(_X3_DEDICATED_LONG_PREFIXES) * len(_ACTIONS) == 48, (
        f"形态 B 端点数 {total}，期望 48（16 前缀 × 3 态）"
    )
    hostless = sorted(
        f"{p}/{act}"
        for p, acts in x3_shape_b_matrix.items()
        for act, (_, mod) in acts.items()
        if mod in {"?", ""}
    )
    assert not hostless, f"以下端点解析不出宿主模块，白名单判据无处落脚：{hostless}"


def test_l2_m1_shape_b_handlers_accept_sheet_param(
    x3_shape_b_matrix: dict[str, dict[str, tuple[bool, str]]],
) -> None:
    """R4.3（任务 5.2 已施加）：`l2-interest-payable` / `m1-dividends-payable` 六个 handler 均声明 `sheet`。

    施加前本条是【现状登记】（六个 handler **无** `sheet`）；任务 5.2 追加
    ``sheet: str | None = Query(None)`` 后按断言消息的指引反转成本形态，
    `_X3_SHEET_PARAM_PENDING` 同时改为空集。

    🔴 为什么不并进下面那条 48 个 handler 的全量判据：这两个前缀是 5.2 的作业面，
    单独钉住才能在「全量那条因枚举面缩小而少核 6 个」时仍然打红。
    """
    assert _TASK_52_LONG_PREFIXES <= set(_X3_DEDICATED_LONG_PREFIXES), (
        f"_TASK_52_LONG_PREFIXES 有不在专属前缀清单里的项："
        f"{sorted(_TASK_52_LONG_PREFIXES - set(_X3_DEDICATED_LONG_PREFIXES))}"
    )
    handlers = {
        f"{p}/{act}": accepts
        for p in sorted(_TASK_52_LONG_PREFIXES)
        for act, (accepts, _) in sorted(x3_shape_b_matrix.get(p, {}).items())
    }
    assert len(handlers) == len(_TASK_52_LONG_PREFIXES) * len(_ACTIONS) == 6, (
        f"只枚举到 {len(handlers)} 个 handler（期望 6 = 2 前缀 × 3 态）：{sorted(handlers)}\n"
        "→ 端点少了或前缀改名，下面的『都声明了』是空转出来的"
    )
    missing = sorted(k for k, v in handlers.items() if not v)
    assert not missing, (
        f"以下 handler 未声明 sheet 参数：{missing}\n"
        "→ 任务 5.2 已给这六个 handler 追加 `sheet: str | None = Query(None)`；"
        "丢掉该参数后 FastAPI 会**静默丢弃**前端传的 sheet，X-3 页导出到的是业务表内容"
        "（200 + 错文件，四层守卫全绿）。正解是补回参数，不是把前缀写进 _X3_SHEET_PARAM_PENDING。"
    )
    assert not _X3_SHEET_PARAM_PENDING, (
        f"_X3_SHEET_PARAM_PENDING 非空：{sorted(_X3_SHEET_PARAM_PENDING)}\n"
        "→ 任务 5.2 已收口，该集合应保持空集；非空会让下面 48 个 handler 的期望数被自动减小"
        "（= 把这些前缀从实判里摘出去）"
    )


def test_all_16_x3_dedicated_prefixes_accept_sheet_param(
    x3_shape_b_matrix: dict[str, dict[str, tuple[bool, str]]],
) -> None:
    """E5 全量：16 个专属前缀的 **48** 个 handler 均已声明 `sheet`。

    施加前作业面是「其余 14 个前缀 / 42 个 handler」（`l2` / `m1` 那 6 个登记在
    `_X3_SHEET_PARAM_PENDING` 里待做）；任务 5.2 把待办集清空后，期望数由
    `(16 - 0) × 3` 派生 ⇒ **48**，这两个前缀因此自动并入本条实判。

    🔴 `_accepts_sheet` 判据坏掉的两个方向由不同的断言接管，本条只覆盖一半：
    - 坏成恒 False ⇒ 本条 48 条全红（消息里已写明先怀疑判据实现）；
    - 坏成恒 True ⇒ 本条与上一条都会假绿，抓它的是
      `test_sheet_agnostic_list_not_stale`（`l4` 必须仍判定为「不接受 sheet」）。
      施加前那个方向由「六个 handler 无 sheet」的现状登记兜着，反转后由 `l4` 那条接手。
    """
    offenders = sorted(
        f"{p}/{act}"
        for p, acts in x3_shape_b_matrix.items()
        if p not in _X3_SHEET_PARAM_PENDING
        for act, (accepts, _) in acts.items()
        if not accepts
    )
    expected = (
        len(_X3_DEDICATED_LONG_PREFIXES) - len(_X3_SHEET_PARAM_PENDING)
    ) * len(_ACTIONS)
    checked = sum(
        len(acts)
        for p, acts in x3_shape_b_matrix.items()
        if p not in _X3_SHEET_PARAM_PENDING
    )
    assert checked == expected == 48, (
        f"只核了 {checked} 个 handler（期望 48 = 16 前缀 × 3 态）—— 枚举面不完整"
    )
    assert not offenders, (
        "以下 X-3 专属 handler 未声明 sheet 参数（施加后应 16/16 全声明）：\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n→ 若这里全部 48 条同时红，先怀疑 _accepts_sheet 判据失效"
        "（它是本节全部断言的实现），而不是 16 个模块同时退化。"
    )


def test_x3_dedicated_prefix_whitelists_contain_x3_code(
    x3_shape_b_matrix: dict[str, dict[str, tuple[bool, str]]],
) -> None:
    """R4.4（任务 5.1 / 5.2 已施加）：16 个专属前缀 **16 / 16** 声明 `IE_SHEETS` 且各含其 X-3。

    施加前本条是【现状登记】（白名单**无一含** X-3、0 / 16 声明 `IE_SHEETS`），
    按断言消息的指引在 Wave 3 收口时反转成本形态，并把
    `_X3_WHITELIST_DISCOVERABLE_BASELINE` 由 6 上调到 16。

    🔴 主判据只认 `IE_SHEETS`（design C2 裁定的白名单唯一真源），**不认**「模块命名空间里
    扫得到 X-3 码」：16 个 host 模块都 `from ..._x3_adjustment_import_export import
    X3_SHEET_SPECS`，而它是 **plain dict**（键就是 16 个 X-3 码）⇒ 命名空间扫描对 16/16
    恒真，拿它当主判据等于空转。扫描结果只留作反空转锚点（扫描坏掉时可发现数会掉到 0）。
    """
    offenders: list[str] = []
    declared_ie: dict[str, object] = {}
    discoverable: dict[str, list[str]] = {}
    for long_prefix in _X3_DEDICATED_LONG_PREFIXES:
        acts = x3_shape_b_matrix.get(long_prefix, {})
        assert acts, f"{long_prefix} 没有形态 B 端点 —— 见上一条锚点断言"
        cycle = _x3_short_prefix(long_prefix).upper()
        pattern = re.compile(rf"^({re.escape(cycle)}-\d+)")
        codes: set[str] = set()
        for module_path in sorted({mod for _, mod in acts.values()}):
            module = importlib.import_module(module_path)
            ie_sheets = getattr(module, "IE_SHEETS", None)
            if ie_sheets is not None:
                declared_ie[long_prefix] = ie_sheets
                codes |= _sheet_codes_in(ie_sheets, pattern)
            for name, value in vars(module).items():
                if name.startswith("__") or callable(value):
                    continue
                codes |= _sheet_codes_in(value, pattern)
        if codes:
            discoverable[long_prefix] = sorted(codes)
        declared = declared_ie.get(long_prefix)
        if declared is None:
            offenders.append(f"{long_prefix}: 未声明 IE_SHEETS")
        elif not isinstance(declared, (set, frozenset)):
            offenders.append(
                f"{long_prefix}: IE_SHEETS 类型为 {type(declared).__name__}，"
                "期望 set/frozenset（白名单要能做集合运算，list 会引入顺序语义）"
            )
        elif _x3_code(long_prefix) not in declared:
            offenders.append(
                f"{long_prefix}: IE_SHEETS 缺 {_x3_code(long_prefix)}，现值 {sorted(declared)}"
            )

    # 反空转锚点：扫描实现失效会让白名单全空，届时「含 X-3」的判定也无从落脚
    assert len(discoverable) >= _X3_WHITELIST_DISCOVERABLE_BASELINE == 16, (
        f"只在 {len(discoverable)} 个专属前缀的 host 模块里读出白名单"
        f"（基线 {_X3_WHITELIST_DISCOVERABLE_BASELINE}，只许上调）：{sorted(discoverable)}\n"
        "→ 掉到基线以下说明 _sheet_codes_in 的扫描失效（正则改坏 / 常量搬走）"
    )
    assert not offenders, (
        "以下专属前缀的 sheet 白名单不合格（R4.4：X-3 必须在 `IE_SHEETS` 里）：\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n→ 缺了 X-3 时形态 A 端点收到 sheet=X-3 会走 400 分支（或更糟：回退成导出全部 sheet）；"
        "`IE_SHEETS` 是唯一真源，不得再留一份 service 层旧白名单当第二真源。"
    )
    assert len(declared_ie) == len(_X3_DEDICATED_LONG_PREFIXES) == 16, (
        f"只有 {len(declared_ie)} / 16 个 host 模块声明了 IE_SHEETS："
        f"缺 {sorted(set(_X3_DEDICATED_LONG_PREFIXES) - set(declared_ie))}\n"
        "→ 任务 5.1（14 个）+ 5.2（l2 / m1）施加后应为 16 / 16；只许上调"
    )


def test_declared_ie_sheets_must_contain_x3(
    x3_shape_b_matrix: dict[str, dict[str, tuple[bool, str]]],
) -> None:
    """自动收紧（R4.4）：任何已声明 `IE_SHEETS` 的专属前缀，其 X-3 必须在里面。

    当前 0 / 16 声明 ⇒ 本条为空过。它不是摆设：上一条钉死了「现状 0 声明」，
    施加当刻上一条打红、本条接手判内容，两条合起来使
    「声明了 IE_SHEETS 却漏掉 X-3」这条最省事的错路无法通过。
    """
    checked: list[str] = []
    offenders: list[str] = []
    for long_prefix in _X3_DEDICATED_LONG_PREFIXES:
        acts = x3_shape_b_matrix.get(long_prefix, {})
        for module_path in sorted({mod for _, mod in acts.values()}):
            module = importlib.import_module(module_path)
            ie_sheets = getattr(module, "IE_SHEETS", None)
            if ie_sheets is None:
                continue
            checked.append(long_prefix)
            if not isinstance(ie_sheets, (set, frozenset)):
                offenders.append(
                    f"{long_prefix}: IE_SHEETS 类型为 {type(ie_sheets).__name__}，"
                    "期望 set/frozenset（白名单要能做集合运算，list 会引入顺序语义）"
                )
                continue
            if _x3_code(long_prefix) not in ie_sheets:
                offenders.append(
                    f"{long_prefix}: IE_SHEETS 缺 {_x3_code(long_prefix)}，"
                    f"现值 {sorted(ie_sheets)}"
                )
    assert not offenders, (
        "以下前缀声明了 IE_SHEETS 但白名单不合格：\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n→ X-3 必须在白名单内，否则形态 A 端点收到 sheet=X-3 会走 400 分支"
        "（或更糟：回退成导出全部 sheet）"
    )
    # 报告态：留一行可读的进度，便于施加过程中确认覆盖面在长
    assert len(checked) <= len(_X3_DEDICATED_LONG_PREFIXES), "IE_SHEETS 声明数超过 16，前缀清单 stale"


def test_sheet_agnostic_prefixes_subset_of_baseline() -> None:
    """`SHEET_AGNOSTIC_PREFIXES` ⊆ 基线 `{"l4"}` —— 只许下调（R4.6）。

    比上面的规模断言（≤ 1）更严一格：规模不变但把 `l4` 换成别的前缀，
    也必须打红 —— 那同样是「又出现一个静默丢参数的前缀」，只是顺手把旧的除籍了。

    🔴 新增即意味着又出现一个前缀的后端漏了 `sheet` 参数：dropdown 传的 sheet 被
    FastAPI 静默丢弃，用户在第二张 sheet 上导出会拿到第一张的内容，不报错、四层守卫全绿。
    这个清单是最后一道人工闸门，不是垃圾桶。
    """
    baseline = frozenset({"l4"})
    added = sorted(SHEET_AGNOSTIC_PREFIXES - baseline)
    assert not added, (
        f"SHEET_AGNOSTIC_PREFIXES 新增了 {added}（基线 {sorted(baseline)}，只许下调）\n"
        "→ 新增即意味着又出现一个静默丢参数的前缀。正解是给后端 handler 加 sheet 参数，"
        "而不是把它登记进本清单换取守卫变绿。"
    )
    x3_short = {_x3_short_prefix(p) for p in _X3_DEDICATED_LONG_PREFIXES}
    assert not (SHEET_AGNOSTIC_PREFIXES & x3_short), (
        f"X-3 的短前缀被登记为 sheet 无关：{sorted(SHEET_AGNOSTIC_PREFIXES & x3_short)}\n"
        "→ 这 16 个前缀施加后每个都要服务 2+ 张 sheet（X-3 与既有业务表），"
        "登记为 sheet 无关等于承认 X-3 与主表导出同样的内容"
    )


def test_multi_sheet_prefixes_accept_sheet_param_per_endpoint() -> None:
    """R4.5 的逐端点判据：多 sheet 前缀的**每一个**三态端点都要声明 `sheet`。

    上面 `test_multi_sheet_prefixes_accept_sheet_param` 用的是 or 聚合
    （前缀下任一端点收 sheet 即算过）—— 那会漏掉「导出收 sheet、导入不收」这种
    半套接线：用户导出的是 X-3、导入却写进了主表，比整体不收更难查。
    实测（2026-08-13）：78 个形态 A 前缀中无一处于半套状态，故本条当前应全绿。
    """
    from app.main import app

    pattern = re.compile(
        r"^/api/workpapers/\{wp_id\}/([\w-]+)/(" + "|".join(_ACTIONS) + r")$"
    )
    per_endpoint: dict[str, dict[str, bool]] = {}
    for route in app.routes:
        m = pattern.match(getattr(route, "path", "") or "")
        if not m:
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        per_endpoint.setdefault(m.group(1), {})[m.group(2)] = _accepts_sheet(endpoint)
    assert per_endpoint, "没枚举到任何形态 A 三态端点 —— app 未装配好，断言已空转"

    multi = _registry_multi_sheet_prefixes()
    offenders: list[str] = []
    checked = 0
    for prefix, sheets in sorted(multi.items()):
        acts = per_endpoint.get(prefix)
        if not acts:
            continue  # 形态 A 不可达，由 test_registry_prefixes_are_reachable_or_declared 负责
        if prefix in SHEET_AGNOSTIC_PREFIXES:
            continue  # 整表导出语义，已单独登记
        checked += len(acts)
        missing = sorted(a for a, ok in acts.items() if not ok)
        if missing:
            offenders.append(
                f"{prefix}（registry 声明 {len(sheets)} 个 sheet）缺 sheet 的端点：{missing}"
            )
    assert checked > 100, (
        f"只核了 {checked} 个端点，覆盖面异常小 —— registry 抽取或路由枚举失效"
    )
    assert not offenders, (
        "以下多 sheet 前缀存在「部分端点收 sheet」的半套接线：\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n→ 三态必须一致收 sheet。半套接线的典型后果：导出的是当前 sheet，"
        "导入却写进该前缀的默认 sheet（静默错位，接口 200）"
    )
