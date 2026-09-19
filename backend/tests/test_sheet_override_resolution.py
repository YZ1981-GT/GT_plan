"""test_sheet_override_resolution — E0-5 一码两表 skip 不变式守卫

Wave 2 Task 14 of spec `e0-send-list-dedicated-components`.
覆盖 Property 24。

核心不变式：`银行函证其他信息核对表E0-5` 的全名 `skip` 条目 SHALL NOT 被删除或改值。
一旦删除，该 hidden sheet 会在 wp_render_config.py L749 按尾码解析成
`confirmation-send-list-e05`，渲染出一个列集完全不符的多余页签。

🔴 这与 `e0-confirmation-completion` 的 Property 28 / Task 19 是同一条不变式。
两侧择一实现、另一侧引用本文件路径。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_OVERRIDES_PATH = _BACKEND / "app" / "data" / "wp_code_overrides.json"

# ─── 已知的「同时命中全名键与尾码键且取值不同」的 sheet 集合 ──────────────────
# 全库只允许这两张。集合变大即红，迫使重新评估是否又出现了新的一码两表。
_KNOWN_FULLNAME_SKIP_UNIECODE_OVERRIDES = {
    "银行函证其他信息核对表E0-5",
    "长期应付职工薪酬实质性程序表 L2A",
}

# 尾码提取正则（对齐 wp_render_config.py 的 _SHEET_CODE_RE）
_SHEET_CODE_RE = re.compile(r"([A-Z]\d+(?:-\d+)?[A-Z]?)$")


@pytest.fixture(scope="module")
def overrides() -> dict[str, str]:
    return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))


# ──────────────────────── 1. 全名 skip 条目必须存在且值为 skip ──────────────

def test_checklist_e05_fullname_skip_exists(overrides):
    """核对表 E0-5 的全名键必须存在且值为 skip。"""
    key = "银行函证其他信息核对表E0-5"
    assert key in overrides, (
        f"wp_code_overrides.json 缺少全名键 {key!r} —— "
        "删了该条目会让 hidden 核对表被尾码解析成 confirmation-send-list-e05"
    )
    assert overrides[key] == "skip", (
        f"全名键 {key!r} 的值必须为 'skip'，实为 {overrides[key]!r}"
    )


def test_l2a_fullname_skip_exists(overrides):
    """L2A 的全名键 skip 也必须存在（另一个已知一码两表）。"""
    key = "长期应付职工薪酬实质性程序表 L2A"
    assert key in overrides
    assert overrides[key] == "skip"


# ──────────────────────── 2. 影响面钉死：只允许已知 2 条 ────────────────────

def test_fullname_skip_set_is_exactly_known(overrides):
    """全库「同时命中全名键与尾码键且取值不同」的集合 == 已知 2 条。
    
    判定方法：遍历 overrides，如果一个 key 能提取出尾码（_SHEET_CODE_RE 匹配），
    且该尾码也在 overrides 中、且尾码对应的值与全名对应的值不同 → 属于此集合。
    """
    found: set[str] = set()
    for key, value in overrides.items():
        m = _SHEET_CODE_RE.search(key)
        if not m:
            continue
        tail_code = m.group(1)
        # 如果 key 本身就是尾码（纯字母+数字，无中文），跳过
        if key == tail_code:
            continue
        # 尾码也在 overrides 中
        if tail_code in overrides:
            tail_value = overrides[tail_code]
            if tail_value != value:
                found.add(key)

    assert found == _KNOWN_FULLNAME_SKIP_UNIECODE_OVERRIDES, (
        f"「全名与尾码取值不同」的 sheet 集合已变化：\n"
        f"  期望：{_KNOWN_FULLNAME_SKIP_UNIECODE_OVERRIDES}\n"
        f"  实际：{found}\n"
        f"  新增（可能又出现了一码两表）：{found - _KNOWN_FULLNAME_SKIP_UNIECODE_OVERRIDES}"
    )


# ──────────────────────── 3. 反向自检：替身 sheet ─────────────────────────────

def test_reverse_check_stub_sheet_skip_logic():
    """反向自检：用与任何真实循环无关的替身，断言判定逻辑正确。
    
    替身核对表 `替身核对表Z9-1`：全名值 = skip → 该 sheet 不应被 componentType 解析
    替身清单 `替身清单Z9-1`：无全名条目 → 走尾码 `Z9-1`
    
    模拟 wp_render_config.py 的两段判定：
    - L709：全名精确匹配 → skip 则 continue
    - L749：尾码优先
    """
    fake_overrides = {
        "替身核对表Z9-1": "skip",  # 全名 skip
        "Z9-1": "some-component-type",  # 尾码键
    }

    # 替身核对表：全名精确匹配命中 skip → 不进 componentType 解析
    key_checklist = "替身核对表Z9-1"
    if key_checklist in fake_overrides and fake_overrides[key_checklist] == "skip":
        checklist_rendered = False
    else:
        checklist_rendered = True
    assert checklist_rendered is False, "全名 skip 应阻止渲染"

    # 替身清单：全名不在 → 走尾码
    key_sendlist = "替身清单Z9-1"
    if key_sendlist in fake_overrides and fake_overrides[key_sendlist] == "skip":
        sendlist_rendered = False
    else:
        # 走尾码
        m = _SHEET_CODE_RE.search(key_sendlist)
        tail = m.group(1) if m else None
        ct = fake_overrides.get(tail) if tail else None
        sendlist_rendered = ct is not None and ct != "skip"
    assert sendlist_rendered is True, "无全名 skip 时应按尾码解析出 componentType"


def test_reverse_check_removing_fullname_skip_makes_checklist_renderable():
    """反向自检：如果删掉全名 skip 条目，核对表就会按尾码被解析（危险！）。"""
    fake_overrides = {
        # 模拟：全名条目被删除
        "Z9-1": "confirmation-send-list-z91",
    }

    key_checklist = "替身核对表Z9-1"
    # 全名不在 → 走尾码
    if key_checklist not in fake_overrides:
        m = _SHEET_CODE_RE.search(key_checklist)
        tail = m.group(1) if m else None
        ct = fake_overrides.get(tail) if tail else None
        rendered = ct is not None and ct != "skip"
    else:
        rendered = fake_overrides[key_checklist] != "skip"

    assert rendered is True, (
        "删掉全名 skip 后核对表按尾码解析 → 这正是我们要防止的"
    )


# ──────────────────────── 4. 不改实现的正向断言 ──────────────────────────────

def test_overrides_json_is_valid_json():
    """wp_code_overrides.json 是合法 JSON。"""
    text = _OVERRIDES_PATH.read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict)
    assert len(data) > 100, "overrides 条目数应 > 100（防空文件）"


def test_e05_short_key_exists(overrides):
    """E0-5 短键存在（供 componentType 解析用）。"""
    assert "E0-5" in overrides, "E0-5 短键缺失"
    # 当前值是 d-form-table，Wave 2 Task 5 会改成 confirmation-send-list-e05
    # 这里不钉值，只钉「存在且非 skip」（否则发函清单也被跳过）
    assert overrides["E0-5"] != "skip", "E0-5 短键不应为 skip（否则发函清单被跳过）"
