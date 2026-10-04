# -*- coding: utf-8 -*-
"""G2 canary：前端受管 sheet 清单与后端 provider 受管面逐字一致（GF Task 15 · Req 4.7）。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 15

═══ 这条判据守的是什么 ═══

Task 15 原文要求宿主的 `isG2SyncManagedSheet`「**从 provider 派生**」。平台当前没有把受管
sheet 的**短码**集合下发到前端的运行时通路（manifest 生成物只带 AST 抽出的 sheet 字面量/
表达式；render-config / store-projection 端点都不下发），故可接受形态二选一 ——
「运行时从 provider 派生」**或**「前端集中声明一次 + 契约测试守护与 provider 一致」。
本文件取后者，范式照 `test_d3_frontend_managed_sheet_parity.py`（仓库里唯一把这件事做实的
样本）。

🔴 **为什么不照 F 循环**：F1/F3/F4/F5 四条已落地 lane 都在宿主里内联一张
`F*_SHEET_KEY_BY_CODE`，注释写「从 provider 受管清单派生（需求 1.6）」而实现是宿主硬编码，
没有任何判据能在两侧漂移时报红 —— 注释与实现对不上。本 lane 不复制那个形态。

守护三件事：
  ① 前端 `G2_MANAGED_SHEETS` 的 `excelName` 集合 == provider `all_managed_sheet_names()`（逐字）。
  ② 前端 rows 类的 `sheetKey` 集合 == provider 行表 spec 的 `sheet_key` 集合。
  ③ 审定表 G2-1 当前**不在**受管面（裁决 GF-H5 后置到第五份 spec）⇒ 前端不得声明
     `kind='adjudication'` 条目，provider `adjudication_spec()` 必须恒 `None`。两侧同时锁，
     防「前端先假称审定表可切 OO」。

变异检验（判据要有牙齿，不是恒真装饰）：
  · 注入一张 provider 没有的假 sheet ⇒ 必红；
  · 前端漏一张 provider 已受管的 sheet ⇒ 必红；
  · 前端偷偷加 adjudication 条目 ⇒ 必红。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_g2_interest_receivable as G2  # noqa: E402

_ROOT = _BACKEND.parent
_FRONTEND_MODULE = (
    _ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "g2ManagedSheets.ts"
)
_HOST = (
    _ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "GtG2InterestReceivable.vue"
)

#: 解析 `G2_MANAGED_SHEETS` 数组里每个条目的 code/sheetKey/kind/excelName 字面量。
_ENTRY_RE = re.compile(
    r"\{\s*code:\s*'(?P<code>[^']+)'\s*,"
    r"\s*sheetKey:\s*'(?P<sheetKey>[^']+)'\s*,"
    r"\s*kind:\s*'(?P<kind>rows|adjudication)'\s*,"
    r"\s*excelName:\s*'(?P<excelName>[^']+)'\s*,?\s*\}"
)


def _parse_frontend_managed_sheets(src: str | None = None) -> list[dict[str, str]]:
    """从前端模块解析 `G2_MANAGED_SHEETS` 条目（纯字面量正则，不执行 TS）。"""
    text = src if src is not None else _FRONTEND_MODULE.read_text(encoding="utf-8")
    block = re.search(
        r"G2_MANAGED_SHEETS[^\[]*\[(?P<body>.*?)\]\s*as const\)",
        text,
        re.DOTALL,
    )
    assert block is not None, "未在前端模块里定位到 G2_MANAGED_SHEETS 数组"
    return [m.groupdict() for m in _ENTRY_RE.finditer(block.group("body"))]


def _assert_parity(entries: list[dict[str, str]]) -> None:
    """一致性断言核心：前端 excelName 集合 == provider all_managed_sheet_names()。"""
    frontend_excel = {e["excelName"] for e in entries}
    backend_names = set(G2.all_managed_sheet_names())
    assert frontend_excel == backend_names, (
        f"前端受管 sheet 集合与 provider all_managed_sheet_names() 不一致："
        f"前端有而后端无={sorted(frontend_excel - backend_names)}；"
        f"后端有而前端无={sorted(backend_names - frontend_excel)}"
    )


def test_frontend_module_exists() -> None:
    assert _FRONTEND_MODULE.is_file(), f"前端受管清单模块不存在：{_FRONTEND_MODULE}"


def test_frontend_managed_sheet_names_match_backend() -> None:
    """主判据：前端 excelName 集合逐字 == provider all_managed_sheet_names()。"""
    entries = _parse_frontend_managed_sheets()
    assert len(entries) == 1, f"G2 当前受管面恰 1 张（明细表G2-2），实得 {len(entries)}：{entries}"
    _assert_parity(entries)


def test_frontend_rows_sheet_keys_match_backend_row_table_specs() -> None:
    """前端 rows 类 sheetKey 集合 == provider 行表 spec 的 sheet_key 集合。"""
    entries = _parse_frontend_managed_sheets()
    frontend_rows_keys = {e["sheetKey"] for e in entries if e["kind"] == "rows"}
    backend_rows_keys = {spec.sheet_key for spec in G2.managed_row_table_specs()}
    assert frontend_rows_keys == backend_rows_keys, (
        f"前端 rows sheetKey 与 provider 行表 sheet_key 不一致："
        f"前端={sorted(frontend_rows_keys)} 后端={sorted(backend_rows_keys)}"
    )
    assert frontend_rows_keys == {"g202-managed"}


def test_adjudication_sheet_is_deferred_on_both_sides() -> None:
    """GF-H5：审定表 G2-1 归第五份 spec ⇒ provider 恒 None、前端不得声明 adjudication 条目。"""
    assert G2.adjudication_spec() is None, (
        "provider adjudication_spec() 已非 None ⇒ 审定表已接入，"
        "请同步把前端清单补一条 kind='adjudication' 并改本判据"
    )
    entries = _parse_frontend_managed_sheets()
    assert [e for e in entries if e["kind"] == "adjudication"] == [], (
        "前端声明了 adjudication 条目但 provider 侧未接入 ⇒ 假称审定表可切 OO"
    )


def test_host_derives_managed_judgement_from_the_single_source() -> None:
    """宿主的受管判定必须**引用**受管清单模块，不得内联字面量 map（F 循环反模式）。"""
    host = _HOST.read_text(encoding="utf-8")
    assert "from './sync/g2ManagedSheets'" in host, (
        "宿主未引用受管清单模块 ⇒ 受管判定又回到宿主内联硬编码"
    )
    assert "isG2OoWiredRowsSheet(currentSheet.value)" in host, (
        "宿主的 isG2SyncManagedSheet 未从受管清单派生"
    )
    # 反模式扫描：宿主不得出现 `G2_SHEET_KEY_BY_CODE` 这类内联 map（F 循环四条 lane 的形态）。
    assert "G2_SHEET_KEY_BY_CODE" not in host, (
        "宿主出现内联受管 map `G2_SHEET_KEY_BY_CODE` ⇒ 复制了 F 循环「注释说派生、实现硬编码」的反模式"
    )


def test_host_keeps_shared_dual_mode_base_and_legacy_onlyoffice() -> None:
    """P14：接桥不得内联展开共享基座、也不得删 legacy GtOnlyOfficeSheet（非受管 sheet 仍需它）。"""
    host = _HOST.read_text(encoding="utf-8")
    assert "from './composables/useG2DualMode'" in host, (
        "共享基座包装 useG2DualMode 被删/内联展开 ⇒ P14 违背（基座被多循环共同消费）"
    )
    # 🔴 口径说明：tasks.md 写「保留 legacy `GtOnlyOfficeSheet`（4 处）」，那个 4 是**改造前
    #    源码里 `GtOnlyOfficeSheet` 这个 token 的裸出现次数** —— 拆开是
    #    `defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))` 一行里含 2 次
    #    （常量名 + 路径）+ 模板 2 个挂载点。裸计数会被注释里提到组件名的文字污染
    #    （本次接桥新增的两条说明注释就各含一次），故判据落在**语义落点**上：
    #    挂载点恰 2 个 + 异步声明恰 1 处。
    mount_sites = host.count("<GtOnlyOfficeSheet")
    assert mount_sites == 2, (
        f"legacy GtOnlyOfficeSheet 模板挂载点应恰 2 个（OO 模式非受管分支 + 未迁移 sheet 兜底），"
        f"实得 {mount_sites} ⇒ 非受管 sheet 的兜底被动了"
    )
    assert host.count("import('./GtOnlyOfficeSheet.vue')") == 1, (
        "legacy GtOnlyOfficeSheet 的 defineAsyncComponent 声明被删/重复"
    )
    assert "GtEntrySyncCapabilityNotice" in host, "能力提示条被删（AC 1.4）"


def test_toolbar_entries_stay_reachable_in_both_modes() -> None:
    """Task 18「公式管理入口两模式可达」的宿主侧判据。

    G2 的公式管理 / 版本历史 / 编制手册 / 能力提示都挂在**同一条工具条**上，而这条工具条的
    渲染条件只有 `currentSheet !== '底稿目录'` —— **不带** `renderMode` 条件 ⇒ 结构化视图与
    在线编辑两模式下都在。判据锁住这件事：一旦有人把工具条塞进 `v-if="!isOoMode"` 分支
    （接桥时最容易顺手做的"优化"），切到在线编辑就再也点不到公式管理，而那是只有真人点一次
    才会发现的缺陷。

    🔴 判法是**位置**而不是存在：断言工具条的 `v-if` 里不出现模式判定，且模式分支
    （`isOoMode`）在工具条**之后**才开始。
    """
    host = _HOST.read_text(encoding="utf-8")
    m = re.search(r'<div v-if="([^"]*)" class="g2-interest-receivable-toolbar">', host)
    assert m is not None, "找不到 G2 工具条的渲染条件 ⇒ 判据无对象"
    cond = m.group(1)
    for token in ("renderMode", "isOoMode", "onlyoffice"):
        assert token not in cond, (
            f"工具条渲染条件里出现 {token!r}（实际条件：{cond!r}）"
            " ⇒ 工具条被模式门住，切到在线编辑后公式管理/版本历史点不到"
        )
    assert cond.strip() == "currentSheet !== '底稿目录'", (
        f"工具条条件变成 {cond!r} —— 与「两模式可达」的前提不同，请重判"
    )
    # 模式分支必须在工具条之后（工具条在两分支之上，故两模式都渲染）
    toolbar_pos = m.start()
    oo_branch_pos = host.find('v-if="isOoMode && isG2SyncManagedSheet"')
    legacy_branch_pos = host.find('v-else-if="isOoMode"')
    assert 0 < toolbar_pos < oo_branch_pos < legacy_branch_pos, (
        "工具条与模式分支的相对位置变了 ⇒ 请复核工具条是否仍在两模式共用的位置"
    )


def test_host_mounts_editor_host_with_definite_height() -> None:
    """接桥必须给 WorkpaperSyncEditorHost 视口相关的确定高度（前端 sizing 守卫同口径）。"""
    host = _HOST.read_text(encoding="utf-8")
    assert "<WorkpaperSyncEditorHost" in host
    assert re.search(r"height:\s*calc\(\s*100vh", host), (
        "挂了 WorkpaperSyncEditorHost 但没有 height: calc(100vh …) 容器 ⇒ 编辑区会被压扁"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 变异检验：判据要有牙齿
# ═══════════════════════════════════════════════════════════════════════════
class TestMutationParityHasTeeth:
    def test_mutation_inject_fake_sheet_name_makes_parity_red(self) -> None:
        entries = _parse_frontend_managed_sheets()
        _assert_parity(entries)  # 对照：真实清单通过
        mutated = entries + [
            {
                "code": "G2-99",
                "sheetKey": "g299-managed",
                "kind": "rows",
                "excelName": "伪造明细表G2-99",
            }
        ]
        with pytest.raises(AssertionError):
            _assert_parity(mutated)

    def test_mutation_frontend_drops_the_managed_sheet_makes_parity_red(self) -> None:
        entries = _parse_frontend_managed_sheets()
        with pytest.raises(AssertionError):
            _assert_parity(entries[:-1])

    def test_mutation_stray_literal_is_not_counted_as_a_declaration(self) -> None:
        """反证：解析器读的是数组字面量 —— 游离字面量不会被计入条目。"""
        src = _FRONTEND_MODULE.read_text(encoding="utf-8")
        polluted = src + "\n// 游离字面量污染：const stray = 'G2-2'\n"
        assert len(_parse_frontend_managed_sheets(polluted)) == 1
