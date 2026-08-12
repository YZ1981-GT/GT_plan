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
