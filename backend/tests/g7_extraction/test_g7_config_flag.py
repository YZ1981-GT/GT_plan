"""灰度开关 ``G7_FOUR_TABLE_EXTRACTION_ENABLED`` 契约。

🔴 2026-08-08 默认值断言由 ``is False`` 改为 ``is True``
======================================================
原断言（Wave 0 / Task 1.1）锁定的是**灰度未上线时**的零回归契约。该 spec
（`g7-four-table-extraction-and-disclosure-alignment`）已 26/26 收口，且真实库
直跑 8 个有 1511 数据的项目实证两个纯函数全部产出真值
（`parent_check.diff` 全 0.0、6 个分类桶按科目名归类正确）；前端亦已完整消费。

**关键**：开关关闭时用户**不可达** —— `G7TabAdjudication` 的「G7-1 账套分类合计
核对卡片」是 `v-if="leafCategories"`（关闭 ⇒ 整卡不渲染）、「从四表库带入未审数」
按钮在 `adjudication_prefill` 为空时报「四表库无该科目数据」、G7-2「从四表取数」
按钮由 `g7_extraction_enabled` 显隐 ⇒ 关闭时的表象正是「四表已入库但底稿没数据」。

照 H1 已落地的范式（``test_h1_extraction_characterization.test_flag_default_is_live``）：
**默认值断言改为锁定上线值**，而「关闭时零注入」这条实质语义**不丢** —— 由
:mod:`backend.tests.g7_extraction.test_g7_leaf_categories` 与
:mod:`backend.tests.g7_extraction.test_g7_pbt` 里 monkeypatch 到 False 的用例保住
（见 :func:`test_flag_off_semantics_is_still_guarded`）。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings, settings

_TESTS_DIR = Path(__file__).resolve().parent


def test_g7_extraction_flag_default_is_live():
    """G7 四表取数已上线：默认 ``True``（不受进程内 monkeypatch 影响，读 Settings()）。"""
    assert Settings().G7_FOUR_TABLE_EXTRACTION_ENABLED is True


def test_g7_extraction_flag_is_bool():
    assert isinstance(settings.G7_FOUR_TABLE_EXTRACTION_ENABLED, bool)


def test_g7_flag_aligns_with_d_cycle_naming():
    """与既有灰度开关同名族存在（命名一致性）。"""
    assert hasattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED")
    assert hasattr(settings, "G7_FOUR_TABLE_EXTRACTION_ENABLED")


def test_g7_flag_aligns_with_shipped_siblings():
    """与已上线的同族开关默认值一致（H1 / H2 / H4 / HI_CYCLE 均为 True）。

    这条是**方向性**锁死：G7 与它们同为「四表叶子聚合 + 审定表预填」形态，
    默认值分叉会让「哪些循环刷新取数有数据」变成不可预期的按循环猜。
    """
    s = Settings()
    siblings = {
        "H1_FOUR_TABLE_EXTRACTION_ENABLED": s.H1_FOUR_TABLE_EXTRACTION_ENABLED,
        "H2_FOUR_TABLE_EXTRACTION_ENABLED": s.H2_FOUR_TABLE_EXTRACTION_ENABLED,
        "H4_FOUR_TABLE_EXTRACTION_ENABLED": s.H4_FOUR_TABLE_EXTRACTION_ENABLED,
        "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED": (
            s.HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED
        ),
    }
    off = [k for k, v in siblings.items() if v is not True]
    assert not off, (
        f"同族开关出现分叉（这些已不是 True）：{off}。"
        "若确有裁决要关掉某个，请同步更新本断言并写明依据。"
    )
    assert s.G7_FOUR_TABLE_EXTRACTION_ENABLED is True


_REPO = Path(__file__).resolve().parents[3]
_RENDER = (
    _REPO
    / "backend/app/routers/wp_render_strategies/_g7_long_term_equity_main.py"
)
_G7_FE = (
    _REPO
    / "audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main"
)


def test_flag_is_exposed_under_project_context_not_top_level():
    """🔴 层级交叉锁死：``g7_extraction_enabled`` 在 ``project_context`` 而**非顶层**。

    memory 铁律「同一份 html_data 的 render 输出分两层放，逐个 key 都要核实位置」——
    本轮探针一度按顶层读得 ``None``，若前端也读错层会得到「按钮永久禁用」这一
    静默失效（TS 里 html_data 是 any，编译与 vitest 都不报错）。

    实测层级：``project_context.g7_extraction_enabled`` / ``project_context
    .tb_source_codes``；而 ``tb_leaf_categories`` / ``adjudication_prefill`` /
    ``bucket_defs`` / ``tb_values`` 在**顶层**。
    """
    src = _RENDER.read_text(encoding="utf-8")
    m = re.search(r"project_context:\s*dict\s*=\s*\{(.*?)\n    \}", src, re.S)
    assert m, "未找到 project_context 字面量（render 结构变了，本断言需重写）"
    block = m.group(1)
    assert '"g7_extraction_enabled"' in block, (
        "g7_extraction_enabled 必须放在 project_context 里（前端 4 个组件读的是这一层）"
    )
    # 顶层返回体里不得再放一份（双真源会让两侧读到不同值）
    ret = src[src.rindex("    return {"):]
    top_keys = set(re.findall(r'^\s{8}"([a-z0-9_]+)":', ret, re.M))
    assert "g7_extraction_enabled" not in top_keys, (
        "顶层返回体不得重复下发 g7_extraction_enabled（双真源）"
    )
    for k in ("tb_leaf_categories", "adjudication_prefill"):
        assert k in top_keys, f"{k} 应在顶层返回体（前端读 htmlData.{k}）"
        assert f'"{k}"' not in block, f"{k} 不应同时出现在 project_context（双真源）"


def test_frontend_reads_flag_from_project_context():
    """前端 4 个消费点必须读 ``project_context.g7_extraction_enabled``。

    读错层 ⇒ 恒 falsy ⇒ 「从四表取数 / 从四表库带入未审数」按钮**永久禁用**，
    表象正是「四表已入库但底稿没数据」（本轮修复的核心症状）。
    """
    if not _G7_FE.is_dir():
        import pytest as _pytest

        _pytest.skip(f"前端目录不存在：{_G7_FE}")
    # 判据：每处 `g7_extraction_enabled` 的**紧前上下文**必须含 project_context
    #（容忍 `?.` / `.` / `['...']` 等多种取值写法，只锁「读的是哪一层」）
    key = "g7_extraction_enabled"
    hits: dict[str, int] = {}
    for p in sorted(_G7_FE.rglob("*.vue")):
        txt = p.read_text(encoding="utf-8")
        if key not in txt:
            continue
        bad: list[int] = []
        n_all = 0
        for m in re.finditer(re.escape(key), txt):
            n_all += 1
            ctx = txt[max(0, m.start() - 60) : m.start()]
            if "project_context" not in ctx:
                bad.append(m.start())
        hits[p.name] = n_all - len(bad)
        assert not bad, (
            f"{p.name} 有 {len(bad)} 处未经 project_context 读该 flag"
            f"（读错层 = 按钮永久禁用），偏移 {bad}"
        )
    assert len(hits) >= 4, (
        f"消费点少于 4 个（实际 {sorted(hits)}）—— 扫描面可能失效，"
        "或有组件漏接灰度门控"
    )


def test_flag_off_semantics_is_still_guarded():
    """反向自检：「关闭时零注入」的语义断言仍然存在（改默认值没把它一起弄丢）。

    翻转默认值最大的风险不是「开了会出错」，而是**顺手把零回归契约删掉** ——
    那样将来想回退灰度时没有任何断言保护。故此处强制存在 monkeypatch 到 False
    的用例（同 spec 目录内扫描）。
    """
    pattern = re.compile(
        r'monkeypatch\.setattr\(\s*(?:app_)?settings,\s*'
        r'"G7_FOUR_TABLE_EXTRACTION_ENABLED",\s*False'
    )
    hits: list[str] = []
    for p in sorted(_TESTS_DIR.glob("test_*.py")):
        if p.name == Path(__file__).name:
            continue
        if pattern.search(p.read_text(encoding="utf-8")):
            hits.append(p.name)
    assert hits, (
        "找不到任何把 G7_FOUR_TABLE_EXTRACTION_ENABLED monkeypatch 到 False 的用例 —— "
        "「灰度关闭时 render 不注入 tb_leaf_categories / adjudication_prefill」这条"
        "零回归契约已失去守卫。翻转默认值时**不得**顺手删掉它。"
    )
