"""抽样复核 prompt 登记守卫（sampling-evaluation-and-governance-closure R10）

背景：`resolve_review_ai_prompt` 对未登记的 section_id **回退通用 prompt**（不是 400），
所以「漏登记」不会打红、只会让复核 AI 拿到笼统提示 → 需要守卫从**前端源码**抽
section_id 并要求后端有专属 prompt。

Validates: Requirements 10.4, 10.5, 10.6
Properties: Property 17, Property 18
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.review_dialog import (
    _NO_FABRICATION,
    _SECTION_PROMPTS,
    resolve_review_ai_prompt,
)


def _repo_root() -> Path:
    """双哨兵向上查找（单哨兵将来会被同名文件骗停）。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend" / "app" / "routers" / "review_dialog.py").is_file() and (
            parent / "audit-platform" / "frontend" / "package.json"
        ).is_file():
            return parent
    raise AssertionError("未能定位仓库根（两个哨兵文件都要存在）")


ROOT = _repo_root()
ENGINE = (
    ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "voucher-sampling"
    / "GtVoucherSamplingEngine.vue"
)

EXPECTED_IDS = ("sampling-config", "sampling-conclusion")


# ─── Property 17：两个 section 均已登记专属 prompt ────────────────────────────


def test_engine_source_exists():
    """哨兵：抽样引擎组件必须存在（路径错会让全部断言空转）。"""
    assert ENGINE.is_file(), f"未找到抽样引擎组件：{ENGINE}"


@pytest.mark.parametrize("section_id", EXPECTED_IDS)
def test_sampling_section_has_dedicated_prompt(section_id: str):
    assert section_id in _SECTION_PROMPTS, (
        f"抽样复核 section「{section_id}」未登记专属 prompt —— "
        "未登记不会报错，只会静默回退通用 prompt"
    )


@pytest.mark.parametrize("section_id", EXPECTED_IDS)
def test_prompt_is_substantive(section_id: str):
    prompt = _SECTION_PROMPTS[section_id]
    assert len(prompt) >= 60, f"{section_id} prompt 过短（{len(prompt)} 字），易诱导自由发挥"
    assert _NO_FABRICATION in prompt, f"{section_id} prompt 缺「不得虚构」约束"


def test_config_prompt_covers_population_and_dataset():
    """抽样配置复核 prompt 必须覆盖总体完整性与抽样框版本两个要点。"""
    prompt = _SECTION_PROMPTS["sampling-config"]
    for keyword in ("总体", "抽样框"):
        assert keyword in prompt, f"抽样配置 prompt 缺少要点「{keyword}」"


def test_conclusion_prompt_covers_uml_and_disposition():
    """结论复核 prompt 必须覆盖错报上限与未检查样本处置。"""
    prompt = _SECTION_PROMPTS["sampling-conclusion"]
    for keyword in ("错报上限", "未检查样本", "偏差"):
        assert keyword in prompt, f"抽样结论 prompt 缺少要点「{keyword}」"


# ─── Property 18：前后端交叉锁死（前端出现新 section 必须后端跟上）─────────


def _frontend_section_ids() -> set[str]:
    """从组件源码抽 GtReviewTrigger 的 section-id 取值。

    🔴 组件里 section-id 绑的是 computed，且 id 由**模板字符串**拼出：

        const samplingConfigSectionId = computed(
          () => `${samplingSectionPrefix.value}sampling-config`)

    故只认 `= 'sampling-x'` 的抽取器会一个都抽不到（表现为「正则失效 → 断言空转」）。
    两种形态都要认：模板字符串里紧跟 `${...}` 的部分，以及裸字符串字面量。
    """
    raw = ENGINE.read_text(encoding="utf-8")
    # 🔴 只扫 <script> 段：<style> 里的 CSS 类名（`.sampling-table`）会被裸字面量
    # 正则误抓成 section id，导致守卫要求后端为一个不存在的 section 登记 prompt。
    m = re.search(r"<script[^>]*>([\s\S]*?)</script>", raw)
    src = m.group(1) if m else raw
    ids: set[str] = set()
    # 形态 1（当前实现）：`${prefix}sampling-config`
    ids |= set(re.findall(r"\$\{[^}]*\}(sampling-[a-z-]+)", src))
    # 形态 2（若将来改为不带前缀的裸字面量）：'sampling-config' / "sampling-config"
    ids |= set(re.findall(r"['\"`](sampling-[a-z-]+)['\"`]", src))
    return ids


def test_frontend_ids_are_discoverable():
    """反向自检：抽取器必须真能从组件里抽到 id（抽不到说明正则失效 → 全部空转）。"""
    ids = _frontend_section_ids()
    assert ids, "未能从抽样引擎组件抽出任何 sampling-* section id（正则失效）"


def test_every_frontend_sampling_section_is_registered():
    """前端每个 sampling-* section 都必须在后端有专属 prompt。"""
    ids = _frontend_section_ids()
    missing = sorted(i for i in ids if i not in _SECTION_PROMPTS)
    assert not missing, (
        f"前端使用了未登记 prompt 的抽样复核 section：{missing}\n"
        "→ 请在 backend/app/routers/review_dialog.py 的 _SECTION_PROMPTS 补登记"
    )


def test_no_stale_sampling_prompt():
    """反面：后端登记的 sampling-* prompt 都要有前端消费方（防孤儿 prompt）。"""
    ids = _frontend_section_ids()
    registered = {k for k in _SECTION_PROMPTS if k.startswith("sampling-")}
    stale = sorted(registered - ids)
    assert not stale, (
        f"后端登记了前端不再使用的抽样 prompt：{stale}（孤儿 prompt，请清理或接线）"
    )


# ─── 回退行为仍然成立（零回归）────────────────────────────────────────────


def test_unregistered_section_still_falls_back():
    """未登记 section 仍回退通用 prompt（该机制是既有语义，不得因本次改动变成报错）。"""
    text = resolve_review_ai_prompt("totally-unknown-section-xyz", "抽样结论")
    assert isinstance(text, str) and text
    assert "抽样结论" in text


def test_registered_section_prompt_is_embedded():
    """已登记 section 的专属内容必须真的出现在最终 prompt 里。"""
    text = resolve_review_ai_prompt("sampling-conclusion", "抽样结论")
    assert "错报上限" in text, "专属 prompt 内容未被拼进最终输出（登记了但没生效）"
