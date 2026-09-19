"""source-backed entry profile 域（Task 13 的 registry 输入）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
Requirements 1.2（**owner 是 Task 1/67**）/ 1.3 / 1.4 / 12.1 / 12.12
Property 3

## 这个模块存在的原因

Task 13 的 registry 必须「逐 entry 交叉校验 source-backed manifest 的
`editable` / `room_model` / `scenario_profile` 与宿主能力、descriptor mode、room
配置事实，任一漂移 fail closed」。本模块提供这三个机器字段的**封闭取值域**与
交叉规则，让 registry 只做编排。

## 🔴 已实证的欠账：生产 manifest 现在没有这三个字段

`backend/data/workpaper_sync_entry_manifest.json` 的 186 条 entry 只有 13 个键
（`entry_id / host_path / mounts / independent_entry / parent_entry_id / wp_match /
document_type / html_store / canonical_resolver / adapter_id / capability /
migration_state / evidence`），`editability` / `room_model` / `scenario_profile`
**一个都没有**。Requirement 1.2 要求它们进入 manifest digest，owner 是 Task 1
（其 `_Requirements` 含 1.2），最终 reconcile 由 Task 67 承接。

本模块因此把「profile 缺失」当成**最极端的一种漂移**：
:func:`extract_entry_profile` 抛 :class:`EntryProfileMissingError`，registry 拒绝
为该 entry 注册任何 adapter。这不是绕开 —— 不变式是

    每条 manifest entry 要么有完整合法 profile，要么不可能注册 adapter

这条不变式在 Task 1 补齐字段**之前和之后都成立**，所以守卫不会把「当前缺失态」
锁成基线（那是假绿第③源：守卫把错值当真源）。缺口本身由
`registry.RegistryReport.missing_profile` 计数暴露。

## 取值域与 DB 双向锁死

`Editability` / `RoomModel` 的取值刻意与 V151 `working_paper_sync_test_run` 的
CHECK 约束同域：

* `ck_wpstr_editability CHECK (editability IN ('editable','readonly','unreachable'))`
* `CHECK (room_model IN ('shared','exclusive','none'))`

枚举在 Python 侧声明、由守卫从 `backend/migrations/V151__*.sql` 解析 CHECK 反向
比对（与 `models.py` 的其他 DB 枚举同一范式）。**命名裁决**：requirements 1.2/12.11
用 `editable`、12.10 用 `editability`、12.12 又把 `editable` 当布尔用；本模块以 DB
列名 `editability`（三值）为字段名，布尔 `editable` 是派生属性
（:attr:`EntryProfile.editable`），两者只有一处定义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.models import SyncDomainError

_BACKEND: Final[Path] = Path(__file__).resolve().parents[3]

#: Task 1 生成的入口清册（唯一真源；本模块只读，不生成、不改写）。
ENTRY_MANIFEST_PATH: Final[Path] = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"

#: profile 三字段在 manifest entry 里的键名。
PROFILE_KEYS: Final[tuple[str, ...]] = ("editability", "room_model", "scenario_profile")

#: `scenario_profile` 的 profile_id 形态：稳定 key，不接受含空格的自由文本。
_PROFILE_ID_ALLOWED: Final[str] = "abcdefghijklmnopqrstuvwxyz0123456789_.-"


class Capability(str, Enum):
    """能力态封闭四值（Requirement 1.3；与 manifest 生成器的 `_CAPABILITIES` 同域）。"""

    bidirectional = "bidirectional"
    single_html = "single_html"
    single_onlyoffice = "single_onlyoffice"
    unreachable = "unreachable"


class Editability(str, Enum):
    """与 V151 `ck_wpstr_editability` 同域。"""

    editable = "editable"
    readonly = "readonly"
    unreachable = "unreachable"


class RoomModel(str, Enum):
    """与 V151 `working_paper_sync_test_run.room_model` 的 CHECK 同域。"""

    shared = "shared"
    exclusive = "exclusive"
    none = "none"


class DescriptorMode(str, Enum):
    """`EditorLaunchDescriptor` 对前端宣称的模式（Requirement 1.4 / 1.5）。

    刻意没有 `unreachable`：不可达入口根本不该产出 descriptor。
    """

    bidirectional = "bidirectional"
    single_html = "single_html"
    single_onlyoffice = "single_onlyoffice"


# ═══════════════════════════════════════════════════════════════════════════
# 异常
# ═══════════════════════════════════════════════════════════════════════════


class EntryProfileError(SyncDomainError):
    error_code = "entry_profile_invalid"


class EntryProfileMissingError(EntryProfileError):
    """manifest entry 缺 source-backed profile 字段（Requirement 1.2 欠账）。

    与 :class:`EntryProfileDriftError` 分成两类：前者是「生成器还没产出这个字段」
    （Task 1/67 的欠账），后者是「字段有值但与宿主/descriptor/room 事实矛盾」
    （裁决错）。共用一个类型时，把缺失分支删掉会被漂移分支遮蔽 ⇒ 变异判 GREEN。
    """

    error_code = "entry_profile_missing"


class EntryProfileDriftError(EntryProfileError):
    """profile 与 capability / descriptor mode / room 事实矛盾。"""

    error_code = "entry_profile_drift"


# ═══════════════════════════════════════════════════════════════════════════
# profile 与事实
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ScenarioProfile:
    """机器可读的场景 profile。

    `payload` 是 manifest 给出的原始机器字段；`digest` 是它的 canonical SHA-256，
    会被 Task 39 冻结进 `working_paper_sync_test_run.scenario_profile_digest`。
    **required scenario set 的推导不在本模块**（AC 12.12 归 Task 39）—— 这里只保证
    profile 是可复现的机器值，不是自由文本。
    """

    profile_id: str
    payload: Mapping[str, Any]

    @property
    def digest(self) -> str:
        return canonical_digest(dict(self.payload))


@dataclass(frozen=True)
class EntryProfile:
    """一条 entry 的 source-backed profile 三字段。"""

    entry_id: str
    editability: Editability
    room_model: RoomModel
    scenario_profile: ScenarioProfile

    @property
    def editable(self) -> bool:
        """AC 12.12 把 `editable` 当布尔用；这是**唯一**的派生点。"""
        return self.editability is Editability.editable


@dataclass(frozen=True)
class DescriptorFacts:
    """服务端 launch descriptor 事实（Task 25/31 的产出，registry 只做交叉校验）。"""

    mode: DescriptorMode
    exposes_mode_switch: bool


@dataclass(frozen=True)
class RoomFacts:
    """OO room 配置事实。

    `doc_key_includes_mtime` 是**当前生产实况**：
    `wp_onlyoffice_router._generate_doc_key()` = `hash(wp_code + file.st_mtime_ns)`。
    Property 6 要求 doc_key 与 mtime 解耦，因此只要该事实为真，registry 就拒绝
    注册 —— 这条门必须由 Task 21 的 room service 先摘掉 mtime 才能过。
    """

    shared_doc_key: bool
    doc_key_includes_mtime: bool
    participant_lease: bool


# ═══════════════════════════════════════════════════════════════════════════
# 解析
# ═══════════════════════════════════════════════════════════════════════════


def _parse_scenario_profile(raw: Any, *, entry_id: str) -> ScenarioProfile:
    if isinstance(raw, str):
        profile_id = raw.strip()
        payload: Mapping[str, Any] = {"profile_id": profile_id}
    elif isinstance(raw, Mapping):
        profile_id = str(raw.get("profile_id") or "").strip()
        payload = dict(raw)
    else:
        raise EntryProfileError(
            f"entry {entry_id}: scenario_profile 必须是 profile_id 字符串或机器对象，"
            f"实得 {type(raw).__name__}"
        )
    if not profile_id:
        raise EntryProfileError(f"entry {entry_id}: scenario_profile 缺 profile_id")
    if not profile_id.isascii() or any(ch not in _PROFILE_ID_ALLOWED for ch in profile_id):
        raise EntryProfileError(
            f"entry {entry_id}: scenario_profile.profile_id 必须是稳定 key"
            f"（小写字母/数字/`_`/`.`/`-`），实得 {profile_id!r} —— required scenarios "
            "不得由自由文本决定（Requirement 1.2）"
        )
    return ScenarioProfile(profile_id=profile_id, payload=payload)


def extract_entry_profile(entry: Mapping[str, Any]) -> EntryProfile:
    """从 manifest entry 取出 profile 三字段；任一缺失即 fail closed。"""
    entry_id = str(entry.get("entry_id") or "").strip()
    if not entry_id:
        raise EntryProfileError("manifest entry 缺 entry_id")
    missing = [key for key in PROFILE_KEYS if entry.get(key) is None]
    if missing:
        raise EntryProfileMissingError(
            f"entry {entry_id}: manifest 缺 source-backed profile 字段 {missing} —— "
            "Requirement 1.2 要求生成器按宿主/descriptor/registry 事实产出 "
            f"{list(PROFILE_KEYS)} 并计入 manifest digest；owner 是 Task 1（最终 reconcile "
            "Task 67）。在补齐之前该 entry 不得注册任何 adapter"
        )
    try:
        editability = Editability(entry["editability"])
    except (ValueError, TypeError) as exc:
        raise EntryProfileError(
            f"entry {entry_id}: editability 未登记: {entry.get('editability')!r}"
            f"（封闭域 {sorted(item.value for item in Editability)}）"
        ) from exc
    try:
        room_model = RoomModel(entry["room_model"])
    except (ValueError, TypeError) as exc:
        raise EntryProfileError(
            f"entry {entry_id}: room_model 未登记: {entry.get('room_model')!r}"
            f"（封闭域 {sorted(item.value for item in RoomModel)}）"
        ) from exc
    return EntryProfile(
        entry_id=entry_id,
        editability=editability,
        room_model=room_model,
        scenario_profile=_parse_scenario_profile(entry["scenario_profile"], entry_id=entry_id),
    )


def capability_of(entry: Mapping[str, Any]) -> Capability:
    raw = entry.get("capability")
    try:
        return Capability(raw)
    except (ValueError, TypeError) as exc:
        raise EntryProfileError(
            f"entry {entry.get('entry_id')!r}: capability 未登记: {raw!r}"
            f"（封闭四态 {sorted(item.value for item in Capability)}）"
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 交叉规则
# ═══════════════════════════════════════════════════════════════════════════

#: capability → 允许的 editability。每条都是独立判据，逐条可变异。
_CAPABILITY_EDITABILITY: Final[Mapping[Capability, frozenset[Editability]]] = {
    Capability.bidirectional: frozenset({Editability.editable}),
    Capability.single_html: frozenset({Editability.editable, Editability.readonly}),
    Capability.single_onlyoffice: frozenset({Editability.editable, Editability.readonly}),
    Capability.unreachable: frozenset({Editability.unreachable}),
}

#: capability → 允许的 room_model。`single_html` 与 `unreachable` 不开 OO room。
_CAPABILITY_ROOM_MODEL: Final[Mapping[Capability, frozenset[RoomModel]]] = {
    Capability.bidirectional: frozenset({RoomModel.shared, RoomModel.exclusive}),
    Capability.single_html: frozenset({RoomModel.none}),
    Capability.single_onlyoffice: frozenset({RoomModel.shared, RoomModel.exclusive}),
    Capability.unreachable: frozenset({RoomModel.none}),
}


def assert_profile_consistent_with_capability(
    profile: EntryProfile, capability: Capability
) -> None:
    """profile ↔ 宿主能力态（Requirement 1.3 / 1.4 / 12.12）。"""
    allowed_editability = _CAPABILITY_EDITABILITY[capability]
    if profile.editability not in allowed_editability:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: capability={capability.value} 只允许 editability ∈ "
            f"{sorted(item.value for item in allowed_editability)}，实得 "
            f"{profile.editability.value}"
        )
    allowed_room = _CAPABILITY_ROOM_MODEL[capability]
    if profile.room_model not in allowed_room:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: capability={capability.value} 只允许 room_model ∈ "
            f"{sorted(item.value for item in allowed_room)}，实得 {profile.room_model.value}"
        )


def assert_profile_consistent_with_descriptor(
    profile: EntryProfile, capability: Capability, descriptor: DescriptorFacts
) -> None:
    """profile/capability ↔ descriptor mode（Requirement 1.4 / 1.5 / Property 3）。"""
    if capability is Capability.unreachable:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: capability=unreachable 的入口不应产出 launch "
            f"descriptor（实得 mode={descriptor.mode.value}）—— 不可达旧桩应删除"
            "（Requirement 1.7）"
        )
    if descriptor.mode.value != capability.value:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: descriptor mode={descriptor.mode.value} 与 manifest "
            f"capability={capability.value} 不符 —— 前端只允许显示真实可用模式"
            "（Requirement 1.4 / 1.5）"
        )
    if descriptor.exposes_mode_switch and capability is not Capability.bidirectional:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: capability={capability.value} 却暴露模式切换按钮 —— "
            "不得显示不可兑现的切换（Requirement 1.5 / Property 3）"
        )


def assert_profile_consistent_with_room(profile: EntryProfile, room: RoomFacts) -> None:
    """profile ↔ room 配置事实（Requirement 2.5~2.9 / Property 6）。"""
    if room.doc_key_includes_mtime:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: room 的 doc_key 仍包含文件 mtime —— doc_key 必须与 "
            "mtime 解耦，否则一次 sheet 可见性写盘就会轮转 doc_key 并打断进行中的会话"
            "（Property 6）。当前 `wp_onlyoffice_router._generate_doc_key()` = "
            "`hash(wp_code + st_mtime_ns)`，须先由 Task 21 的 room service 取代"
        )
    if profile.room_model is RoomModel.none:
        if room.shared_doc_key or room.participant_lease:
            raise EntryProfileDriftError(
                f"entry {profile.entry_id}: room_model=none 却存在 shared doc_key / "
                "participant lease —— room 事实与 profile 矛盾"
            )
        return
    if profile.room_model is RoomModel.shared and not room.shared_doc_key:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: room_model=shared 要求 doc_key 与用户无关（同 wp 共享），"
            "实测 room 事实为 per-client doc_key"
        )
    if profile.room_model is RoomModel.exclusive and room.shared_doc_key:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: room_model=exclusive 却使用共享 doc_key"
        )
    if not room.participant_lease:
        raise EntryProfileDriftError(
            f"entry {profile.entry_id}: room_model={profile.room_model.value} 要求逐用户 "
            "participant lease（mode/epoch/TTL/revoke），实测缺失"
        )


# ═══════════════════════════════════════════════════════════════════════════
# manifest 读取
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def load_entry_manifest() -> Mapping[str, Any]:
    """只读加载 Task 1 的 manifest。本模块永不写它。"""
    try:
        payload = json.loads(ENTRY_MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EntryProfileError(
            f"入口清册缺失: {ENTRY_MANIFEST_PATH} —— 没有 source-backed manifest 时"
            "不得注册任何 adapter"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EntryProfileError(f"入口清册不是合法 JSON: {ENTRY_MANIFEST_PATH}: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("entries"):
        raise EntryProfileError(f"入口清册结构非法（缺 entries）: {ENTRY_MANIFEST_PATH}")
    return payload


def manifest_entries_by_id(manifest: Mapping[str, Any] | None = None) -> dict[str, Mapping[str, Any]]:
    payload = manifest if manifest is not None else load_entry_manifest()
    out: dict[str, Mapping[str, Any]] = {}
    for entry in payload.get("entries") or []:
        if not isinstance(entry, Mapping):
            raise EntryProfileError("manifest entries[] 元素必须是对象")
        entry_id = str(entry.get("entry_id") or "").strip()
        if not entry_id:
            raise EntryProfileError("manifest entry 缺 entry_id")
        if entry_id in out:
            raise EntryProfileError(f"manifest entry_id 重复: {entry_id}")
        out[entry_id] = entry
    return out


__all__ = [
    "ENTRY_MANIFEST_PATH", "PROFILE_KEYS",
    "Capability", "Editability", "RoomModel", "DescriptorMode",
    "EntryProfileError", "EntryProfileMissingError", "EntryProfileDriftError",
    "ScenarioProfile", "EntryProfile", "DescriptorFacts", "RoomFacts",
    "extract_entry_profile", "capability_of",
    "assert_profile_consistent_with_capability",
    "assert_profile_consistent_with_descriptor",
    "assert_profile_consistent_with_room",
    "load_entry_manifest", "manifest_entries_by_id",
]
