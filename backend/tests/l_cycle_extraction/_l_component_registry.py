"""L 循环 componentType 判据层：override ↔ 前端渲染注册表 ↔ 宿主组件 三向。

## 为什么需要这一层

`test_l_cycle_export_import_verification.py` 里有 63 条断言写成
`_WP_CODE_OVERRIDE[code] == "audit-sheet" / "d-form-table" / "a-program-console"`，
即把**通用** componentType 当期望值锁死。L 循环后来整体迁到**专属组件**
（L1~L8 各自一个，如 `l1-short-term-loans`），于是这 63 条恒红。

迁移是合法的，已实证：18 个专属 componentType **同时**存在于后端
`VALID_COMPONENT_TYPES` 与前端 `htmlRendererRegistry.ts`，且每个 L{n} 的全部
wp_code 都归到同一个专属组件（L0 例外，见 `L0_SHARED_CONFIRMATION_NOTE`）。
所以是守卫锁着迁移前的旧值 —— 「守卫把错值当基线锁死」。

## 改法不是把 == 换成新字面量

那只是把 63 个旧字面量换成 8 个新字面量，下次再迁移再红一轮，而且**判据形态
仍是全局等值型（形态 D，禁用）**。这里改成结构不变式（形态 A：违规清单为空）：

1. 归属唯一 —— 每个 L{n}（n≥1）的全部 wp_code 归到**恰好一个**专属组件
2. 命名编码循环号 —— 该组件名匹配 `^l{n}-`，可抓出 L4-3 误指 `l3-*`
3. 可渲染 —— componentType 在前端 registry 里且宿主 `.vue` 在磁盘上存在
4. **第三边** —— wp_code 字面量真的出现在宿主源码里，可抓出「override 指向
   一个并不处理该子码的组件」，这是 `== "audit-sheet"` 永远抓不到的
5. 反向 —— 迁移前的通用类型不得对 L1~L8 复活（保住原判据的防回退本意）

判据 1~4 比原来强：原断言只要字面量对得上就过，即便那个 componentType 前端
没注册、宿主文件不存在、或宿主根本不处理该子码。

## 角色区分（审定表 / 检查表）去哪了

原来 `d-form-table` vs `audit-sheet` 承载「这张表是检查表还是审定表」。迁移后
这个区分在 override 层**不再可表达**（一个 wp 的所有 sheet 同一个专属组件），
在 schema 层也只剩残迹（实测：声明为 d-form-table 的 22 个码仅 5 个有 schema
文件，其中 2 个已改写成专属类型；声明为 audit-sheet 的 25 个**一个都没有**）。

它真正的落点是宿主组件内部按 wp_code / sheet 分发，机制见
`wp_classification_service.derive_component_type(ignore_wp_code_override=True)`
的注释：「多 sheet 底稿跳过此检查，按 class_code 各自派生 —— 避免 wp_code
override 把所有 sheet 压平成同一 componentType」。

故本模块保留角色清单（`DECLARED_FORM_TABLE_CODES` / `DECLARED_AUDIT_SHEET_CODES`）
作为**领域意图的记录**，判据 3/4 用它们校验注册与宿主引用，但不再断言
componentType 等于某个通用值。角色级断言应写在宿主组件的前端测试里。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = [
    "REPO_ROOT",
    "REGISTRY_TS",
    "DEDICATED_TYPE_RE",
    "PRE_MIGRATION_GENERIC_TYPES",
    "L0_SHARED_CONFIRMATION_NOTE",
    "DECLARED_FORM_TABLE_CODES",
    "DECLARED_AUDIT_SHEET_CODES",
    "RegistryEntry",
    "load_renderer_registry",
    "host_source_of",
    "l_overrides",
    "cycle_of",
    "dedicated_owners_by_cycle",
    "evaluate_dedicated_ownership",
    "evaluate_host_references_code",
    "evaluate_no_pre_migration_type",
]

# backend/tests/l_cycle_extraction/ -> 上三层是仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]
assert (REPO_ROOT / "audit-platform").is_dir(), (
    f"REPO_ROOT 推算错误：{REPO_ROOT} 下没有 audit-platform —— 本模块被移动过？"
    "请同步调整 parents[] 层数（路径推算依赖文件位置，是移动文件的高频坑）"
)
REGISTRY_TS = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "htmlRendererRegistry.ts"
)

#: 专属组件命名式：l{循环号}-{业务名}
DEDICATED_TYPE_RE = re.compile(r"^l(\d)-[a-z0-9-]+$")

#: 迁移前 L 循环用过的通用 componentType。它们对 L1~L8 复活即意味着回退。
PRE_MIGRATION_GENERIC_TYPES = frozenset(
    {"audit-sheet", "d-form-table", "c-note-table"}
)

L0_SHARED_CONFIRMATION_NOTE = (
    "L0 不走专属组件：函证模块的 9 个 confirmation-* 组件按平台铁律**跨循环共享**"
    "（D0/E0/F0/G0/H0/K0/L0 复用同一套），不为每个循环各开一份。故 L0 的 wp_code "
    "映射到 confirmation-hub / confirmation-summary / confirmation-entity-verify 等"
    "共享类型，以及 L0A 的通用 a-program-console（L0 无专属宿主可承载程序表）。"
)

#: 领域意图记录：源模板口径下哪些子码是检查表、哪些是审定表/测算表。
#: 迁移后 componentType 已不表达这个区分（见模块 docstring），保留用于
#: 「注册完整 + 宿主确实引用」的校验，以及给后续前端角色级断言当清单。
DECLARED_FORM_TABLE_CODES = (
    "L0-1", "L0-2", "L0-3", "L0-4", "L0-5",
    "L1-1", "L1-6",
    "L2-1", "L2-4",
    "L3-1", "L3-4", "L3-6",
    "L4-1", "L4-8",
    "L5-1", "L5-4",
    "L6-1", "L6-4",
    "L7-1", "L7-4",
    "L8-1", "L8-6",
)
DECLARED_AUDIT_SHEET_CODES = (
    "L1-2", "L1-3", "L1-4", "L1-5",
    "L2-2", "L2-3",
    "L3-2", "L3-3", "L3-5",
    "L4-2", "L4-3", "L4-4", "L4-5", "L4-6", "L4-7",
    "L5-2", "L5-3",
    "L6-2", "L6-3",
    "L7-2", "L7-3",
    "L8-2", "L8-3", "L8-4", "L8-5",
)


@dataclass(frozen=True)
class RegistryEntry:
    component_type: str
    host_rel: str
    host_path: Path

    @property
    def host_exists(self) -> bool:
        return self.host_path.is_file()


@lru_cache(maxsize=1)
def load_renderer_registry() -> dict:
    """解析前端 `htmlRendererRegistry.ts`，得到 componentType -> 宿主 .vue。

    registry 形态是对象数组::

        { componentType: 'l1-short-term-loans',
          component: defineAsyncComponent(() => import('./GtL1ShortTermLoans.vue')),
          ... }

    故取每个 `componentType:` 之后**最近**的一个 `import('...vue')`。窗口限长而非
    全文搜索，避免把下一条目的 import 当成本条的（相邻条目间距实测 < 600 字符）。
    """
    text = REGISTRY_TS.read_text(encoding="utf-8")
    base = REGISTRY_TS.parent
    out: dict[str, RegistryEntry] = {}
    for m in re.finditer(r"componentType:\s*'([a-z0-9-]+)'", text):
        ct = m.group(1)
        window = text[m.end() : m.end() + 600]
        imp = re.search(r"import\(\s*'([^']+\.vue)'\s*\)", window)
        if imp is None:
            continue
        rel = imp.group(1)
        out[ct] = RegistryEntry(ct, rel, (base / rel.lstrip("./")).resolve())
    return out


def host_source_of(component_type: str) -> str | None:
    entry = load_renderer_registry().get(component_type)
    if entry is None or not entry.host_exists:
        return None
    return entry.host_path.read_text(encoding="utf-8", errors="replace")


def l_overrides(override: dict) -> dict:
    """override 里所有 L 循环条目（`L` + 数字开头，含父码 / 子码 / 程序表）。"""
    return {c: t for c, t in override.items() if re.match(r"^L\d", str(c))}


def cycle_of(wp_code: str) -> str:
    m = re.match(r"^(L\d)", str(wp_code))
    assert m, f"{wp_code!r} 不是 L 循环 wp_code"
    return m.group(1)


def dedicated_owners_by_cycle(override: dict) -> dict:
    """每个 L{n} 用到的 componentType 集合（判「归属唯一」用）。"""
    out: dict[str, set] = {}
    for code, ct in l_overrides(override).items():
        out.setdefault(cycle_of(code), set()).add(ct)
    return out


def evaluate_dedicated_ownership(override: dict) -> tuple:
    """判据 1+2：L1~L8 每个循环归属唯一，且组件名编码本循环号。

    返回违规清单（空 = 通过）。L0 按共享函证组件豁免。
    """
    problems: list[str] = []
    for cycle, types in sorted(dedicated_owners_by_cycle(override).items()):
        if cycle == "L0":
            continue
        if len(types) != 1:
            problems.append(
                f"{cycle} 的 wp_code 映射到 {len(types)} 个 componentType "
                f"{sorted(types)} —— 专属组件应承载本循环全部 sheet，归属须唯一"
            )
            continue
        ct = next(iter(types))
        m = DEDICATED_TYPE_RE.match(ct)
        if m is None:
            problems.append(
                f"{cycle} 的 componentType {ct!r} 不符专属组件命名式 l<循环号>-<业务名>"
            )
        elif m.group(1) != cycle[1:]:
            problems.append(
                f"{cycle} 的 componentType {ct!r} 编码的循环号是 l{m.group(1)}，"
                f"与所属循环 {cycle} 不符 —— override 接错了循环"
            )
    return tuple(problems)


def evaluate_host_references_code(override: dict, codes) -> tuple:
    """判据 3+4：componentType 可渲染，且宿主源码真的引用该 wp_code。

    这条是三向的第三边。`== "audit-sheet"` 那种写法即便 componentType 前端没
    注册、宿主文件不存在、宿主根本不处理该子码，也照样通过。
    """
    problems: list[str] = []
    registry = load_renderer_registry()
    for code in codes:
        ct = override.get(code)
        if ct is None:
            problems.append(f"{code}: 未在 _WP_CODE_OVERRIDE 注册")
            continue
        if not DEDICATED_TYPE_RE.match(ct):
            continue  # L0 共享函证组件：宿主由多循环共用，不做 wp_code 引用判定
        entry = registry.get(ct)
        if entry is None:
            problems.append(f"{code}: componentType {ct!r} 不在前端 htmlRendererRegistry 中")
            continue
        if not entry.host_exists:
            problems.append(f"{code}: 宿主 {entry.host_rel} 在磁盘上不存在")
            continue
        src = entry.host_path.read_text(encoding="utf-8", errors="replace")
        if code not in src:
            problems.append(
                f"{code}: 宿主 {entry.host_path.name} 源码里没有该 wp_code —— "
                "override 指向了一个并不处理这张表的组件"
            )
    return tuple(problems)


def evaluate_no_pre_migration_type(override: dict) -> tuple:
    """判据 5（反向）：迁移前的通用类型不得对 L1~L8 复活。"""
    problems: list[str] = []
    for code, ct in sorted(l_overrides(override).items()):
        if cycle_of(code) == "L0":
            continue
        if ct in PRE_MIGRATION_GENERIC_TYPES:
            problems.append(
                f"{code} 退回迁移前的通用 componentType {ct!r} —— "
                f"L1~L8 应由专属组件承载"
            )
    return tuple(problems)
