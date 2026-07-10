# Feature: aging-config-enhancement, Property 1/2/3/4: AgingConfigService 预设解析/默认推断/往返保持/校验
"""AgingConfigService 的 Property-Based Tests（hypothesis, max_examples=5）。

覆盖 design.md 中定义的 4 条正确性属性（后端纯逻辑 + 持久化逻辑）：

- Property 1: Preset resolution returns correct segments
    (THREE_YEAR→4段 / FIVE_YEAR→6段, 标签有序正确)  — Validates Requirements 1.1
- Property 2: Default preset inference by subject
    (D2/K1/K3/G5→FIVE_YEAR, D3/F1→THREE_YEAR)       — Validates Requirements 1.2, 10.1
- Property 3: Configuration round-trip preservation
    (save_config → get_config 保持 preset/custom_segments/subject_overrides)
                                                       — Validates Requirements 1.3
- Property 4: Validation rejects invalid configurations
    (CUSTOM 段数<2 或 >10 / 空白 label / 重复 label)   — Validates Requirements 1.4, 1.5, 2.3

DB 策略：get_config/save_config/get_effective_segments 仅读写 `project.wizard_state`
并调用 `db.flush()`。为保证 example 间完全隔离且无外部依赖，使用轻量 fake
session/project（execute 返回固定 project，flush 为 no-op）。这忠实覆盖服务真实
逻辑分支（默认推断分支 / wizard_state 序列化-反序列化往返），同时保持确定性。
"""

from __future__ import annotations

import asyncio
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services import aging_config_service
from app.services.aging_config_service import (
    PRESET_SEGMENTS,
    AgingConfigPayload,
    AgingPreset,
    AgingSegment,
    resolve_segments,
    validate_config,
)

_PBT = settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# ─── Fake async DB session / project（example 间隔离，无外部依赖） ──────────────


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeSession:
    """最小化 AsyncSession 替身：execute 返回固定 project，flush 为 no-op。"""

    def __init__(self, project):
        self._project = project

    async def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeResult(self._project)

    async def flush(self):
        return None


class _FakeProject:
    def __init__(self, wizard_state=None):
        self.wizard_state = wizard_state


# ─── 生成策略 ────────────────────────────────────────────────────────────────

# 预定义（非 CUSTOM）预设
st_named_preset = st.sampled_from([AgingPreset.THREE_YEAR, AgingPreset.FIVE_YEAR])

# 受影响科目
st_subject = st.sampled_from(["D2", "K1", "K3", "G5", "D3", "F1"])
_FIVE_YEAR_SUBJECTS = {"D2", "K1", "K3", "G5"}

# 非空白 label（限定字母/数字/常见中文字符，避免纯空白）
st_label = st.text(
    alphabet="abcdefghij0123456789年月以内至上",
    min_size=1,
    max_size=6,
)


@st.composite
def _valid_custom_segments(draw, min_size: int = 2, max_size: int = 10):
    """生成 min_size~max_size 个 label 唯一的合法自定义段。"""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    labels = draw(
        st.lists(st_label, min_size=n, max_size=n, unique=True)
    )
    segs: list[AgingSegment] = []
    for i, lab in enumerate(labels):
        segs.append(
            AgingSegment(
                key=f"seg_{i}",
                label=lab,
                dayFrom=i * 100,
                dayTo=None if i == len(labels) - 1 else i * 100 + 99,
            )
        )
    return segs


@st.composite
def _valid_config_payload(draw):
    """生成合法 AgingConfigPayload（三种 preset 均可）。"""
    preset = draw(st.sampled_from(list(AgingPreset)))
    custom = draw(_valid_custom_segments()) if preset == AgingPreset.CUSTOM else None
    overrides = draw(
        st.dictionaries(keys=st_subject, values=st_named_preset, max_size=6)
    )
    return AgingConfigPayload(
        preset=preset,
        custom_segments=custom,
        subject_overrides=overrides or None,
    )


@st.composite
def _invalid_config_payload(draw):
    """生成保证非法的 AgingConfigPayload（三类违规之一）。"""
    mode = draw(st.sampled_from(["bad_count", "empty_label", "duplicate_label"]))

    if mode == "bad_count":
        # CUSTOM 但段数 <2 或 >10
        count = draw(st.one_of(st.integers(0, 1), st.integers(11, 15)))
        labels = draw(
            st.lists(st_label, min_size=count, max_size=count, unique=True)
        )
        segs = [
            AgingSegment(key=f"seg_{i}", label=lab, dayFrom=i * 100, dayTo=None)
            for i, lab in enumerate(labels)
        ]
        return AgingConfigPayload(preset=AgingPreset.CUSTOM, custom_segments=segs)

    if mode == "empty_label":
        # 合法段数(2~10)但至少一个 label 为空白
        segs = draw(_valid_custom_segments())
        blank = draw(st.sampled_from(["", " ", "   ", "\t", "\n"]))
        idx = draw(st.integers(0, len(segs) - 1))
        segs[idx] = AgingSegment(
            key=segs[idx].key, label=blank, dayFrom=0, dayTo=None
        )
        return AgingConfigPayload(preset=AgingPreset.CUSTOM, custom_segments=segs)

    # duplicate_label: 合法段数但两段 label 相同
    segs = draw(_valid_custom_segments(min_size=2))
    segs[1] = AgingSegment(
        key=segs[1].key, label=segs[0].label, dayFrom=999, dayTo=None
    )
    return AgingConfigPayload(preset=AgingPreset.CUSTOM, custom_segments=segs)


# ─── Property 1: Preset resolution returns correct segments ──────────────────


@_PBT
@given(preset=st_named_preset)
def test_property_1_preset_resolution(preset: AgingPreset):
    """Feature: aging-config-enhancement, Property 1: Preset resolution returns correct segments.

    resolve_segments(THREE_YEAR/FIVE_YEAR, None) 返回正确段数(4/6)与有序标签。

    Validates: Requirements 1.1
    """
    segs = resolve_segments(preset, None)
    expected = PRESET_SEGMENTS[preset]

    expected_count = 4 if preset == AgingPreset.THREE_YEAR else 6
    assert len(segs) == expected_count
    # 标签顺序正确
    assert [s.label for s in segs] == [s.label for s in expected]
    # key 顺序正确
    assert [s.key for s in segs] == [s.key for s in expected]

    if preset == AgingPreset.THREE_YEAR:
        assert [s.label for s in segs] == ["1年以内", "1-2年", "2-3年", "3年以上"]
    else:
        assert [s.label for s in segs] == [
            "1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上",
        ]


# ─── Property 2: Default preset inference by subject ─────────────────────────


@_PBT
@given(subject=st_subject)
def test_property_2_default_preset_inference(subject: str):
    """Feature: aging-config-enhancement, Property 2: Default preset inference by subject.

    无 aging_config 时，get_effective_segments 对 D2/K1/K3/G5 返回 FIVE_YEAR 段，
    对 D3/F1 返回 THREE_YEAR 段。

    Validates: Requirements 1.2, 10.1
    """
    project = _FakeProject(wizard_state=None)  # 无 aging_config
    session = _FakeSession(project)

    segs = asyncio.run(
        aging_config_service.get_effective_segments(uuid.uuid4(), subject, session)
    )

    expected_preset = (
        AgingPreset.FIVE_YEAR if subject in _FIVE_YEAR_SUBJECTS else AgingPreset.THREE_YEAR
    )
    expected = PRESET_SEGMENTS[expected_preset]

    assert [s.key for s in segs] == [s.key for s in expected]
    assert [s.label for s in segs] == [s.label for s in expected]
    assert len(segs) == (6 if expected_preset == AgingPreset.FIVE_YEAR else 4)


# ─── Property 3: Configuration round-trip preservation ───────────────────────


@_PBT
@given(payload=_valid_config_payload())
def test_property_3_round_trip_preservation(payload: AgingConfigPayload):
    """Feature: aging-config-enhancement, Property 3: Configuration round-trip preservation.

    save_config 后再 get_config，preset/custom_segments/subject_overrides 均保持等价。

    Validates: Requirements 1.3
    """
    # 携带额外 wizard_state 字段，验证不被覆盖
    project = _FakeProject(wizard_state={"__other__": "keep-me"})
    session = _FakeSession(project)
    pid = uuid.uuid4()

    asyncio.run(aging_config_service.save_config(pid, payload, session))
    loaded = asyncio.run(aging_config_service.get_config(pid, session))

    # preset 保持
    assert loaded.preset == payload.preset

    # subject_overrides 保持（None → {}）
    expected_overrides = payload.subject_overrides or {}
    assert loaded.subject_overrides == expected_overrides

    # custom_segments / effective_segments 保持
    if payload.preset == AgingPreset.CUSTOM:
        assert [s.model_dump() for s in loaded.effective_segments] == [
            s.model_dump() for s in (payload.custom_segments or [])
        ]
    else:
        assert [s.key for s in loaded.effective_segments] == [
            s.key for s in PRESET_SEGMENTS[payload.preset]
        ]

    # wizard_state 其他字段未被覆盖
    assert project.wizard_state.get("__other__") == "keep-me"


# ─── Property 4: Validation rejects invalid configurations ───────────────────


@_PBT
@given(payload=_invalid_config_payload())
def test_property_4_validation_rejects_invalid(payload: AgingConfigPayload):
    """Feature: aging-config-enhancement, Property 4: Validation rejects invalid configurations.

    validate_config 对以下任一违规返回非空错误列表：
    (a) CUSTOM 段数 <2 或 >10, (b) 空/纯空白 label, (c) 重复 label。

    Validates: Requirements 1.4, 1.5, 2.3
    """
    errors = validate_config(payload)
    assert errors, f"expected validation errors for invalid payload, got none: {payload!r}"


@_PBT
@given(payload=_valid_config_payload())
def test_property_4_validation_accepts_valid(payload: AgingConfigPayload):
    """Feature: aging-config-enhancement, Property 4 (对偶): 合法配置校验通过（无错误）。

    Validates: Requirements 1.4, 1.5, 2.3
    """
    errors = validate_config(payload)
    assert errors == [], f"expected no errors for valid payload, got: {errors}"
