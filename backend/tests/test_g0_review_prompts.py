"""G0-1 下区 AI / 复核 prompt 登记守卫。

spec: g0-confirmation-source-alignment / Task 19（Requirement 3.7 / 3.9）

─── 为什么 G0 这 6 条和 F0 撤回的那 6 条不同 ────────────────────────────────────

F0 那 6 条被撤回的首要理由是**不可达**（`review-dialog/ai-generate` 的 section_id
只来自 `useReviewDialog(props.sectionId)`，而 F0 一个组件都没接）。G0 侧逐环实证
（2026-08-04）链路是通的，故登记有意义：

    GtWpRenderer → useWorkpaperScaffold → useWorkpaperReviewProvide
                     → provide('openReviewDialog')
                       ↳ 没有它 `GtReviewTrigger` 的 `v-if="openReviewDialog"` 不渲染
    GtWpRenderer → GtWorkpaperRuntimeHosts → GtWpReviewDialogHost   （对话框宿主）
    GtConfirmationSummary（v-if isG0）→ G0SummaryLowerZone.vue
                     → <GtReviewTrigger :section-id="d.reviewSectionId" />

─── 两条链路的门完全不同（缺登记的后果不同） ───────────────────────────────────

| 链路     | 端点                                        | 门                          |
|----------|---------------------------------------------|-----------------------------|
| 复核     | `review-dialog/ai-generate`                 | `.get()` 回退通用 prompt，**无门** |
| AI 生成  | `{wp_id}/g0/ai-generate`（`_g0_confirmation_ai`） | `_SUPPORTED_SECTIONS` **硬门 400** |
| AI 生成  | `{wp_id}/ai/generate-text`（`wp_guidance_chat`）  | **无门**，且显式 `prompt` 优先于 section 兜底 |

→ 复核侧缺登记只降 prompt 质量；AI 侧走专属端点缺登记则 400 被前端 `catch` 静默吞
（按钮看着能点、实际永远失败）。故本守卫对 AI 侧断言「键集相等」。

期望 id **全部从前端源码派生**（`g0SummaryLowerZone.ts`），不写死字面量 ——
新增下区文本域必然要求补 prompt。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.review_dialog import _SECTION_PROMPTS as REVIEW_PROMPTS
from app.routers.review_dialog import resolve_review_ai_prompt
from app.routers.wp_render_strategies._g0_confirmation_ai import (
    _SECTION_PROMPTS as G0_AI_PROMPTS,
)
from app.routers.wp_render_strategies._g0_confirmation_ai import (
    _SUPPORTED_SECTIONS as G0_AI_SUPPORTED,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
G0_DIR = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "g0-confirmation"
)
LOWER_ZONE_TS = G0_DIR / "g0SummaryLowerZone.ts"
LOWER_ZONE_VUE = G0_DIR / "G0SummaryLowerZone.vue"
HOST_VUE = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "confirmation"
    / "GtConfirmationSummary.vue"
)
G0_TEMPLATE = REPO_ROOT / "backend" / "wp_templates" / "G" / "G0 投资循环函证.xlsx"

_FORBID_FABRICATION = ("不得虚构", "严禁虚构")
_MIN_PROMPT_LEN = 20

# G0 下区 prompt 的键前缀（孤儿检测用；`securities-diff-conclusion` /
# `alternative-audit-conclusion` 是 G0-3/G0-6 的既有 section，不属本组）
_AI_SECTION_PREFIX = "g0-summary-"
_REVIEW_ID_PREFIX = "G0-1-"


# ─── 前端真源抽取（纯函数，便于反向自检） ────────────────────────────────────


def _strip_ts_comments(text: str) -> str:
    """去掉 `//` 与 `/* */` 注释。

    守卫说明注释里会写出被禁的字面量（如「不得写 test_scope」），不去注释会把
    说明文字数成真实声明。
    """
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    return re.sub(r"//[^\n]*", "", text)


def _self_check_strip_ts_comments() -> None:
    """`_strip_ts_comments` 的内联 fixture 反向自检（不依赖真实文件恰好含反例）。"""
    fixture = "const a = 1 // aiSection: 'ghost-in-comment'\n/* aiSection: 'ghost-block' */\nconst b = 2"
    out = _strip_ts_comments(fixture)
    assert "ghost-in-comment" not in out
    assert "ghost-block" not in out
    assert "const a = 1" in out and "const b = 2" in out


def _extract(pattern: str, text: str) -> list[str]:
    return re.findall(pattern, text)


def _frontend_ai_sections(src: str) -> list[str]:
    """`G0_AUDIT_NOTE_DEFS[].aiSection` + `G0_CONCLUSION_AI_SECTION`。

    `G0_AI_SECTIONS` 在 TS 里是运行期 `map` 出来的，无法正则直取 → 按其两个
    组成部分抽取（与前端 `G0_AI_SECTIONS` 的定义逐字对应）。
    """
    body = _strip_ts_comments(src)
    ids = _extract(r"aiSection:\s*'([^']+)'", body)
    ids += _extract(r"G0_CONCLUSION_AI_SECTION\s*=\s*'([^']+)'", body)
    return ids


def _frontend_review_section_ids(src: str) -> list[str]:
    """`G0_AUDIT_NOTE_DEFS[].reviewSectionId` + `G0_CONCLUSION_REVIEW_SECTION_ID`。"""
    body = _strip_ts_comments(src)
    ids = _extract(r"reviewSectionId:\s*'([^']+)'", body)
    ids += _extract(r"G0_CONCLUSION_REVIEW_SECTION_ID\s*=\s*'([^']+)'", body)
    return ids


def _function_body(src: str, decl: str) -> str:
    """按花括号配对截函数体（禁固定字符窗口 —— 会溢出到下一个函数）。"""
    i = src.find(decl)
    assert i != -1, f"未能定位 `{decl}`（改名？）"
    j = src.find("{", i)
    assert j != -1, f"`{decl}` 之后没有 `{{`"
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[j : k + 1]
    raise AssertionError(f"`{decl}` 花括号未配对")


def _self_check_function_body() -> None:
    """`_function_body` 的内联 fixture 反向自检。"""
    fixture = "function a() {\n  if (x) { y() }\n  return 1\n}\nfunction b() { return 2 }\n"
    body_a = _function_body(fixture, "function a(")
    assert "return 1" in body_a
    assert "return 2" not in body_a, "截取溢出到了下一个函数"


@pytest.fixture(scope="module")
def lower_zone_ts() -> str:
    assert LOWER_ZONE_TS.exists(), f"前端真源缺失：{LOWER_ZONE_TS}"
    return LOWER_ZONE_TS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def lower_zone_vue() -> str:
    assert LOWER_ZONE_VUE.exists(), f"前端组件缺失：{LOWER_ZONE_VUE}"
    return LOWER_ZONE_VUE.read_text(encoding="utf-8")


# ─── 反向自检（抽取器失效必打红） ────────────────────────────────────────────


def test_helpers_pass_inline_selfchecks() -> None:
    _self_check_strip_ts_comments()
    _self_check_function_body()


def test_extractors_read_real_declarations(lower_zone_ts: str) -> None:
    """抽取器真读到声明（否则后续断言全是空转）。"""
    ai = _frontend_ai_sections(lower_zone_ts)
    review = _frontend_review_section_ids(lower_zone_ts)
    assert len(ai) == 6, f"应抽到 5 段审计说明 + 1 结论 = 6 个 aiSection，实得 {ai}"
    assert len(review) == 6, f"应抽到 6 个 reviewSectionId，实得 {review}"
    assert len(set(ai)) == 6, f"aiSection 有重复：{ai}"
    assert len(set(review)) == 6, f"reviewSectionId 有重复：{review}"
    # 抽取器对空输入必须返回空（防「正则宽到什么都能命中」）
    assert _frontend_ai_sections("") == []
    assert _frontend_review_section_ids("") == []


def test_extractor_fails_loud_when_source_shape_changes() -> None:
    """反向自检：字段改名（如 aiSection → aiKey）必须抽不到 → 上面那条立刻红。"""
    renamed = "{ seq: 1, aiKey: 'g0-summary-control', reviewKey: 'G0-1-audit-note-1' }"
    assert _frontend_ai_sections(renamed) == []
    assert _frontend_review_section_ids(renamed) == []


def _missing_registrations(expected: list[str], registered) -> list[str]:
    """本文件全部「已登记」类断言共用的判据（供反向自检复用同一段逻辑）。"""
    return [s for s in expected if s not in registered]


def test_removing_one_registration_would_go_red(lower_zone_ts: str) -> None:
    """反向自检：删掉任一条登记，判据必须点名那一条（防断言空转）。

    直接对判据函数做变异，不去改真实文件 —— 与真实断言共用 `_missing_registrations`，
    故这条绿 ⇒ 真实断言具备发现能力。
    """
    ai_expected = _frontend_ai_sections(lower_zone_ts)
    review_expected = _frontend_review_section_ids(lower_zone_ts)
    assert _missing_registrations(ai_expected, G0_AI_SUPPORTED) == []
    assert _missing_registrations(review_expected, REVIEW_PROMPTS) == []

    for victim in ai_expected:
        mutated = {k: v for k, v in G0_AI_PROMPTS.items() if k != victim}
        assert _missing_registrations(ai_expected, mutated) == [victim]
    for victim in review_expected:
        mutated = {k: v for k, v in REVIEW_PROMPTS.items() if k != victim}
        assert _missing_registrations(review_expected, mutated) == [victim]


# ─── 复核链路（review_dialog，无门 → 只影响 prompt 质量） ─────────────────────


def test_review_section_ids_registered(lower_zone_ts: str) -> None:
    expected = _frontend_review_section_ids(lower_zone_ts)
    missing = _missing_registrations(expected, REVIEW_PROMPTS)
    assert missing == [], (
        f"前端会发出但 review_dialog 未登记专属 prompt 的 section_id：{missing}"
        "（`resolve_review_ai_prompt` 是 .get() 回退 → 不报错但会退化成笼统通用 prompt）"
    )


def test_review_prompt_quality(lower_zone_ts: str) -> None:
    for sid in _frontend_review_section_ids(lower_zone_ts):
        text = REVIEW_PROMPTS[sid]
        assert len(text.strip()) >= _MIN_PROMPT_LEN, f"{sid} prompt 过短（{len(text)} 字）"
        assert any(k in text for k in _FORBID_FABRICATION), (
            f"{sid} prompt 缺「不得虚构」类约束 → 上下文缺失时模型会编造金额/结论"
        )


def test_no_orphan_g0_review_prompts(lower_zone_ts: str) -> None:
    """拦孤儿 prompt：后端登记了 `G0-1-*` 但前端没有该 section。"""
    expected = set(_frontend_review_section_ids(lower_zone_ts))
    registered = {k for k in REVIEW_PROMPTS if k.startswith(_REVIEW_ID_PREFIX)}
    orphans = sorted(registered - expected)
    assert orphans == [], (
        f"孤儿 prompt（后端已登记、前端无该 section）：{orphans} —— 前端删了文本域就该删登记"
    )


def test_review_resolve_returns_dedicated_prompt(lower_zone_ts: str) -> None:
    for sid in _frontend_review_section_ids(lower_zone_ts):
        section_type = "审计说明" if "note" in sid else "审计结论"
        resolved = resolve_review_ai_prompt(sid, section_type)
        assert REVIEW_PROMPTS[sid] in resolved
        assert section_type in resolved
    # 反向自检：未登记 id 仍走通用回退（证明本组不是靠改成硬门才「生效」）
    generic = resolve_review_ai_prompt("g0-1-not-registered-note", "审计说明")
    assert "不得虚构" not in generic and "严禁虚构" not in generic


def test_review_trigger_actually_mounted(lower_zone_ts: str, lower_zone_vue: str) -> None:
    """可达性：每个 reviewSectionId 都真挂在 `GtReviewTrigger` 上（F0 撤回的教训）。"""
    body = _strip_ts_comments(lower_zone_vue)
    assert "GtReviewTrigger" in body, "组件未挂 GtReviewTrigger → 复核 prompt 不可达"
    # 组件按 def 循环渲染，故断言绑定表达式而非字面 id
    assert 'section-id="d.reviewSectionId"' in body, "审计说明 5 段未按 def 绑定 reviewSectionId"
    assert "CONCLUSION_REVIEW_SECTION_ID" in body, "审计结论未绑定复核 section-id"
    # 真源侧确实声明了 6 个（与上面的绑定合起来 = 6 个入口）
    assert len(_frontend_review_section_ids(lower_zone_ts)) == 6


# ─── AI 生成链路（G0 专属端点，硬门 400） ────────────────────────────────────


def test_g0_ai_sections_registered_in_both_places(lower_zone_ts: str) -> None:
    """🔴 硬门：`_SUPPORTED_SECTIONS` 缺登记 → 400 被前端 catch 静默吞。"""
    expected = _frontend_ai_sections(lower_zone_ts)
    missing_gate = _missing_registrations(expected, G0_AI_SUPPORTED)
    assert missing_gate == [], (
        f"未登记 `_SUPPORTED_SECTIONS` 的 section：{missing_gate} —— "
        "`_g0_confirmation_ai` 对未登记 section `raise HTTPException(400)`，"
        "前端 catch 会吞成「AI 生成失败」"
    )
    missing_prompt = _missing_registrations(expected, G0_AI_PROMPTS)
    assert missing_prompt == [], f"未登记 `_SECTION_PROMPTS` 的 section：{missing_prompt}"


def test_g0_ai_gate_and_prompt_key_sets_equal() -> None:
    """两侧键集必须相等（只登记一侧 = 400 或 无指令泛化生成）。"""
    gate = {s for s in G0_AI_SUPPORTED if s.startswith(_AI_SECTION_PREFIX)}
    prompts = {s for s in G0_AI_PROMPTS if s.startswith(_AI_SECTION_PREFIX)}
    assert gate == prompts, (
        f"`_SUPPORTED_SECTIONS` 与 `_SECTION_PROMPTS` 键集不等："
        f"只在门里={sorted(gate - prompts)}，只在 prompt 里={sorted(prompts - gate)}"
    )
    # 全量键集也不得出现「有门无 prompt」（G0-3/G0-6 既有两条一并守住）
    assert G0_AI_SUPPORTED == set(G0_AI_PROMPTS), (
        f"全量键集不等：门={sorted(G0_AI_SUPPORTED)} prompt={sorted(G0_AI_PROMPTS)}"
    )


def test_g0_ai_prompt_quality(lower_zone_ts: str) -> None:
    for sid in _frontend_ai_sections(lower_zone_ts):
        text = G0_AI_PROMPTS[sid]
        assert len(text.strip()) >= _MIN_PROMPT_LEN, f"{sid} prompt 过短（{len(text)} 字）"
        assert any(k in text for k in _FORBID_FABRICATION), f"{sid} prompt 缺「不得虚构」类约束"
        assert "G0-1" in text or "源模板" in text, f"{sid} prompt 未写明源模板口径"


def test_no_orphan_g0_ai_prompts(lower_zone_ts: str) -> None:
    expected = set(_frontend_ai_sections(lower_zone_ts))
    registered = {k for k in G0_AI_PROMPTS if k.startswith(_AI_SECTION_PREFIX)}
    orphans = sorted(registered - expected)
    assert orphans == [], f"孤儿 AI prompt（后端登记、前端无该 section）：{orphans}"


def test_frontend_ai_call_is_consistent_with_registration() -> None:
    """AI 调用点与登记处必须自洽（**双向**断言，不写死某一个端点）。

    2026-08-04 现状：`handleG0LowerAi` 走通用 `/api/workpapers/{id}/ai/generate-text`
    并**显式传 prompt** → 通用端点无门、且显式 prompt 优先于 section 兜底，
    所以「往 `wp_guidance_chat._SECTION_PROMPTS` 登记 g0-summary-*」会是死配置。
    tasks.md Task 19 的裁决是改指 `/g0/ai-generate`（拿到 G0 专属 `_SYSTEM_PROMPT`
    与 `_load_project_context`），本轮因该文件正被并发会话改动而未动刀。

    故本断言写成两种接线各自的自洽条件 —— 无论哪种都不会假绿，也不必在改指之后
    再来改这条测试：

    - 走 `/g0/ai-generate` → 载荷必须驼峰（`existingContent`/`relatedContext`），
      且 section 已在硬门里（由上面 `test_g0_ai_sections_registered_in_both_places` 保证）
    - 走通用端点 → 必须显式传 `prompt` 且该 prompt 含「不得虚构」类约束
      （否则退化成 `请根据提供的上下文信息生成专业的审计文本。` = 放任自造）
    """
    assert HOST_VUE.exists(), f"宿主缺失：{HOST_VUE}"
    src = HOST_VUE.read_text(encoding="utf-8")
    body = _function_body(src, "async function handleG0LowerAi(")

    uses_dedicated = "/g0/ai-generate" in body
    uses_generic = "/ai/generate-text" in body
    assert uses_dedicated or uses_generic, "handleG0LowerAi 未发现任何 AI 端点调用"
    assert not (uses_dedicated and uses_generic), "同时调用两个端点（口径分叉）"

    if uses_dedicated:
        assert "existingContent" in body, "G0 专属端点载荷字段是驼峰 existingContent"
        assert "relatedContext" in body, "G0 专属端点载荷字段是驼峰 relatedContext"
        # 端点路径必须带 /api（vite proxy 只代理 /api，缺了会打到 SPA 路由返回 HTML）
        assert "/api/workpapers/" in body, "缺 /api 前缀 → 请求不会到后端"
    else:
        assert re.search(r"\bprompt:\s", body), (
            "走通用端点却没显式传 prompt → 会退化到 `请根据提供的上下文信息生成专业的审计文本。`"
        )
        assert any(k in body for k in _FORBID_FABRICATION), (
            "走通用端点时内联 prompt 必须含「不得虚构」类约束"
        )
        assert "/api/workpapers/" in body, "缺 /api 前缀 → 请求不会到后端"


# ─── 源模板锚点交叉核对（prompt 引用的源格必须真是那个内容） ──────────────────


@pytest.fixture(scope="module")
def g0_summary_sheet():
    openpyxl = pytest.importorskip("openpyxl")
    assert G0_TEMPLATE.exists(), f"源模板缺失：{G0_TEMPLATE}"
    wb = openpyxl.load_workbook(G0_TEMPLATE, data_only=False)
    try:
        yield wb["函证结果汇总表G0-1"], set(wb.sheetnames)
    finally:
        wb.close()


def test_source_anchors_referenced_by_prompts(g0_summary_sheet) -> None:
    ws, _ = g0_summary_sheet
    assert str(ws["S19"].value).strip() == "三、审计说明"
    assert str(ws["C30"].value).strip() == "四、审计结论"
    assert str(ws["S20"].value).strip().startswith("1、对询证函保持的控制的说明")
    assert str(ws["X20"].value).strip().startswith("2、对误差的分析")
    assert str(ws["S24"].value).strip().startswith("3、对以传真或电子邮件形式收到的回函的可靠性的考虑")
    assert str(ws["S25"].value).strip().startswith("4、针对不符事项的程序")
    assert str(ws["S28"].value).strip().startswith("5、针对未回函的替代程序")
    # X21+X22 是被拆成两格的一句话（prompt 里引用了它的完整语义）
    joined = str(ws["X21"].value).strip() + str(ws["X22"].value).strip()
    assert "界定误差构成条件" in joined and "不能合理解释其差异" in joined
    # S26 是独立提示语（prompt 第 4 项引用它）
    assert "未函证的其他信息" in str(ws["S26"].value)


def test_reference_conclusions_are_in_column_b(g0_summary_sheet) -> None:
    """参考结论内容在 **B 列**，A 列只是 `A、`/`B、`/`C、` 标签。"""
    ws, _ = g0_summary_sheet
    assert str(ws["A54"].value).strip() == "参考结论："
    for label_cell, code in (("A55", "A"), ("A56", "B"), ("A57", "C")):
        assert str(ws[label_cell].value).strip() == f"{code}、"
    assert str(ws["B55"].value).strip() == "未见异常。"
    assert "调整事项" in str(ws["B56"].value)
    assert "不可确认" in str(ws["B57"].value)
    # 结论 prompt 必须把三条参考结论原文带进去（否则模型自造结论口径）
    prompt = G0_AI_PROMPTS["g0-summary-conclusion"]
    assert "未见异常" in prompt and "不可确认" in prompt


def test_s24_typo_preserved_and_prompt_points_to_g0_7(g0_summary_sheet) -> None:
    """源模板 S24 写「（G0-6）」是笔误（可靠性验证表实为 G0-7）。

    双向：源模板文字**原样保留**（不得「顺手修正」），prompt 按**意图**指向 G0-7
    并显式标注笔误。
    """
    ws, sheet_names = g0_summary_sheet
    s24 = str(ws["S24"].value)
    assert "（G0-6）" in s24, "源模板 S24 的笔误被改掉了（三向比对会打红）"
    assert "邮件传真回函可靠性验证G0-7" in sheet_names
    assert "替代程序检查表G0-6" in sheet_names

    for prompts, key in (
        (G0_AI_PROMPTS, "g0-summary-reliability"),
        (REVIEW_PROMPTS, "G0-1-audit-note-3"),
    ):
        text = prompts[key]
        assert "G0-7" in text, f"{key} 未按意图指向 G0-7"
        assert "笔误" in text, f"{key} 未标注源模板笔误（审计追溯要求）"
