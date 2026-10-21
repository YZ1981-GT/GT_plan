"""同步内核（纯函数，design §4）：上游从 U0 变为 U1 时，按项目状态分类并给出效果。

「上游」= 本项目订阅的模板（有定义时）否则全局。四个动作共用本内核：全局发布、
模板发布新版本、订阅（U0=全局，U1=模板）、退订回到全局（U0=模板，U1=全局）。

分类（自上而下取第一条）：

| 条件 | 分类 |
|---|---|
| 项目已归档 | frozen |
| 无本项目适配 | inherit |
| 本项目适配已固定（暂缓） | pinned |
| 本项目适配 == U1 | same |
| 本项目适配 == 基线 | follow |
| 其他 | conflict |

本模块不碰数据库；效果由 ``publish`` / ``project_ops`` 落到各域存储。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from app.services.formula_settings.definitions import DISABLED_KEY, merge_keep_local_desc, same_exec


class Category(str, Enum):
    FROZEN = "frozen"
    INHERIT = "inherit"
    PINNED = "pinned"
    SAME = "same"
    FOLLOW = "follow"
    CONFLICT = "conflict"


CATEGORY_LABELS: dict[str, str] = {
    "frozen": "冻结（已归档，不改动）",
    "inherit": "直接生效",
    "pinned": "已暂缓（仍用旧定义）",
    "same": "已一致",
    "follow": "自动跟随",
    "conflict": "冲突",
}


class ProjectChoice(str, Enum):
    APPLY = "apply"
    DEFER = "defer"


class ConflictChoice(str, Enum):
    ADOPT = "adopt"   # 采用新上游
    KEEP = "keep"     # 保留本项目
    ASK = "ask"       # 交项目确认（默认）


class Action(str, Enum):
    NONE = "none"                    # 不写项目层
    SET_LOCAL = "set_local"          # 本项目适配改为给定定义
    DELETE_LOCAL = "delete_local"    # 删除本项目适配（回到上游）
    REBASE = "rebase"                # 更新基线；执行字段不变（说明字段可随上游）
    PIN = "pin"                      # 固定在旧定义（写 / 保留固定行）
    PENDING = "pending"              # 生成或更新待确认事项，项目层不动


@dataclass(frozen=True)
class LocalState:
    """本项目在某公式位上的适配状态。``definition is None`` 表示无适配。"""

    definition: Mapping[str, Any] | None
    base_definition: Mapping[str, Any] | None = None
    base_version: int | None = None
    pinned: bool = False


@dataclass(frozen=True)
class Effect:
    action: Action
    local_definition: Mapping[str, Any] | None = None
    base_definition: Mapping[str, Any] | None = None
    base_version: int | None = None
    pinned: bool = False
    pending_reason: str | None = None
    #: 本项目的有效定义是否因此变化（决定是否需要传播）
    effective_changed: bool = False


def classify(domain: str, *, new_upstream: Mapping[str, Any] | None,
             local: LocalState | None, frozen: bool) -> Category:
    """上游变为 ``new_upstream`` 时，本项目在该公式位上的分类。"""
    if frozen:
        return Category.FROZEN
    if local is None or local.definition is None:
        return Category.INHERIT
    if local.pinned:
        return Category.PINNED
    if same_exec(domain, local.definition, new_upstream):
        return Category.SAME
    if same_exec(domain, local.definition, local.base_definition):
        return Category.FOLLOW
    return Category.CONFLICT


def _adopt(domain: str, new_upstream: Mapping[str, Any] | None, new_version: int | None,
           local: LocalState | None) -> Effect:
    if new_upstream is None:
        return Effect(Action.DELETE_LOCAL, effective_changed=True)
    merged = merge_keep_local_desc(
        domain, new_upstream,
        local.definition if local else None,
        local.base_definition if local else None,
    )
    return Effect(Action.SET_LOCAL, local_definition=merged, base_definition=new_upstream,
                  base_version=new_version, effective_changed=True)


def decide(domain: str, category: Category, *,
           old_upstream: Mapping[str, Any] | None, old_version: int | None,
           new_upstream: Mapping[str, Any] | None, new_version: int | None,
           local: LocalState | None,
           project_choice: ProjectChoice = ProjectChoice.APPLY,
           conflict_choice: ConflictChoice = ConflictChoice.ASK,
           materialize: bool = False) -> Effect:
    """分类 + 管理员决策 → 效果（design §4 决策表）。

    ``materialize``：上游是订阅的模板时为真 —— 模板定义要写成本项目层行（物化），
    所以「无本项目适配 + 应用」也要写入，而不是什么都不做。
    """
    defer = project_choice is ProjectChoice.DEFER
    if category is Category.FROZEN:
        if local is None or local.definition is None:
            # 已归档项目一律保持旧有效定义：写固定行（旧上游不存在时固定为「停用」），不生成待确认。
            pin_def = old_upstream if old_upstream is not None else {DISABLED_KEY: True}
            return Effect(Action.PIN, local_definition=pin_def, base_definition=old_upstream,
                          base_version=old_version, pinned=True)
        return Effect(Action.NONE)
    if category is Category.INHERIT:
        if defer:
            pin_def = old_upstream if old_upstream is not None else {DISABLED_KEY: True}
            return Effect(Action.PIN, local_definition=pin_def, base_definition=old_upstream,
                          base_version=old_version, pinned=True, pending_reason="deferred")
        changed = not same_exec(domain, old_upstream, new_upstream)
        if materialize and new_upstream is not None:
            return Effect(Action.SET_LOCAL, local_definition=new_upstream, base_definition=new_upstream,
                          base_version=new_version, effective_changed=changed)
        return Effect(Action.NONE, effective_changed=changed)
    if category is Category.PINNED:
        return Effect(Action.PENDING, pending_reason="deferred")
    if category is Category.SAME:
        assert local is not None
        # 执行字段已一致：只更新基线；本项目没改过的说明字段随上游更新（R2.4）
        merged = merge_keep_local_desc(domain, new_upstream, local.definition, local.base_definition)
        return Effect(Action.REBASE, local_definition=merged if merged is not None else local.definition,
                      base_definition=new_upstream, base_version=new_version)
    assert local is not None
    if category is Category.FOLLOW:
        if defer:
            return Effect(Action.PIN, local_definition=local.definition,
                          base_definition=local.base_definition, base_version=local.base_version,
                          pinned=True, pending_reason="deferred")
        return _adopt(domain, new_upstream, new_version, local)
    # CONFLICT
    if defer or conflict_choice is ConflictChoice.ASK:
        return Effect(Action.PENDING, pending_reason="conflict")
    if conflict_choice is ConflictChoice.KEEP:
        return Effect(Action.REBASE, local_definition=local.definition, base_definition=new_upstream,
                      base_version=new_version)
    return _adopt(domain, new_upstream, new_version, local)


class Resolution(str, Enum):
    ADOPT = "adopt"
    KEEP = "keep"
    CUSTOM = "custom"


def resolve_pending(domain: str, choice: Resolution, *,
                    upstream: Mapping[str, Any] | None, upstream_version: int | None,
                    local: LocalState | None,
                    custom_definition: Mapping[str, Any] | None = None) -> Effect:
    """项目处理待确认事项（采用最新上游 / 保留本项目 / 手工修改）。都会取消固定。"""
    if choice is Resolution.ADOPT:
        return _adopt(domain, upstream, upstream_version, local)
    if choice is Resolution.KEEP:
        if local is None or local.definition is None:
            return Effect(Action.NONE)
        return Effect(Action.SET_LOCAL, local_definition=local.definition, base_definition=upstream,
                      base_version=upstream_version)
    if custom_definition is None:
        raise ValueError("手工修改必须提供定义")
    changed = not same_exec(domain, custom_definition, local.definition if local else upstream)
    return Effect(Action.SET_LOCAL, local_definition=custom_definition, base_definition=upstream,
                  base_version=upstream_version, effective_changed=changed)


# ── 应用到指定项目（同级推送）：以目标项目当前有效定义为参照，写目标项目的本项目适配 ──


def classify_push(domain: str, *, source: Mapping[str, Any] | None,
                  target_effective: Mapping[str, Any] | None,
                  local: LocalState | None, frozen: bool) -> Category:
    """把 ``source`` 推到目标项目时的分类（R7.3）。"""
    if frozen:
        return Category.FROZEN
    if same_exec(domain, target_effective, source):
        return Category.SAME
    if local is None or local.definition is None:
        return Category.INHERIT
    if not local.pinned and same_exec(domain, local.definition, local.base_definition):
        return Category.FOLLOW
    return Category.CONFLICT


def decide_push(domain: str, category: Category, *, source: Mapping[str, Any] | None,
                local: LocalState | None, upstream: Mapping[str, Any] | None,
                upstream_version: int | None,
                conflict_choice: ConflictChoice = ConflictChoice.ASK) -> Effect:
    """同级推送的效果：只写目标项目的适配，基线保持目标项目自己的上游。"""
    if category in (Category.FROZEN, Category.SAME):
        return Effect(Action.NONE)
    if source is None:
        target = Effect(Action.DELETE_LOCAL, effective_changed=True)
    elif category is Category.INHERIT:
        target = Effect(Action.SET_LOCAL, local_definition=source, base_definition=upstream,
                        base_version=upstream_version, effective_changed=True)
    else:
        assert local is not None
        target = Effect(Action.SET_LOCAL, local_definition=source,
                        base_definition=local.base_definition if local.base_definition is not None else upstream,
                        base_version=local.base_version if local.base_definition is not None else upstream_version,
                        effective_changed=True)
    if category is Category.CONFLICT:
        if conflict_choice is ConflictChoice.ASK:
            return Effect(Action.PENDING, pending_reason="conflict")
        if conflict_choice is ConflictChoice.KEEP:
            return Effect(Action.NONE)
    return target
