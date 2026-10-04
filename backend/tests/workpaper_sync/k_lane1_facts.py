# -*- coding: utf-8 -*-
"""K 循环 lane 1 的共享口径真源。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup

🔴 **只放本 lane 特有的口径**；通用口径（K 域文件集 / 行数 / 剥注释 / 三族判别式 /
derived_total / 收敛账本）一律 import `k_foundation_facts`，不重造。

═══ 🔴 口径差异（如实登记，不改判据方向）═══

**键数 678 是真库口径**，前端源码纯字面量现算 **512**。
逐条差 +21~28 且**分布均匀**（K1 +24 · K2 +22 · K3 +23 · K4 +21 · K5 +21 ·
K6 +28 · K7 +27）—— 均匀差是真库口径的特征：每条 entry 在真库里都有一批
**运行时生成**的键（review-session / published / 各类 meta），源码里没有字面量。
与 lane 2 的「323 真库 vs 201 前端」同型。两个口径都对，混用会算错。
"""
from __future__ import annotations

import pathlib
import re

from tests.workpaper_sync.k_foundation_facts import (  # noqa: F401
    DATA,
    ROOT,
    WP_COMPOSABLES,
    WP_COMPONENTS,
    cached_text,
    strip_comments,
)

# ═══════════════════════════════════════════════════════════════════════════
# 本 lane 的 7 条 entry
# ═══════════════════════════════════════════════════════════════════════════
LANE1_INDEXES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)
LANE2_INDEXES: tuple[int, ...] = (8, 9, 11, 12, 13)
FOUNDATION_INDEXES: tuple[int, ...] = (10,)

LANE1_ENTRY_IDS: dict[int, str] = {
    1: "xlsx/gt-k1-other-receivables",
    2: "xlsx/gt-k2-other-current-assets",
    3: "xlsx/gt-k3-other-payables",
    4: "xlsx/gt-k4-other-current-liabilities",
    5: "xlsx/gt-k5-provisions",
    6: "xlsx/gt-k6-held-for-sale",
    7: "xlsx/gt-k7-deferred-income",
}

LANE1_HOSTS: dict[int, str] = {
    1: "GtK1OtherReceivables.vue",
    2: "GtK2OtherCurrentAssets.vue",
    3: "GtK3OtherPayables.vue",
    4: "GtK4OtherCurrentLiabilities.vue",
    5: "GtK5Provisions.vue",
    6: "GtK6HeldForSale.vue",
    7: "GtK7DeferredIncome.vue",
}

#: 7 个一阶 orphan（生产边与测试边各 0）
LANE1_ORPHANS: dict[int, str] = {
    n: f"useK{n}DualMode.ts" for n in LANE1_INDEXES
}

#: 🔴 barrel 门：这个文件**不存在**是「一阶 0 ⇒ 二阶恒 0」的前提
BARREL_PATH = WP_COMPOSABLES / "index.ts"

# ═══════════════════════════════════════════════════════════════════════════
# 规模基线（design 等值，全部现算比对）
# ═══════════════════════════════════════════════════════════════════════════
LANE1_SHEETS_BY_ENTRY = {1: 17, 2: 11, 3: 12, 4: 8, 5: 11, 6: 11, 7: 11}
LANE1_BARE_IF_BY_ENTRY = {1: 91, 2: 76, 3: 22, 4: 6, 5: 9, 6: 47, 7: 40}
#: definedName (总数, 含 `#REF!`)
LANE1_DEFINED_NAMES_BY_ENTRY = {
    1: (0, 0), 2: (37, 29), 3: (0, 0), 4: (43, 36), 5: (0, 0), 6: (1, 0), 7: (0, 0),
}
#: 🔴 真库口径（design），**不是**前端字面量口径
LANE1_KEYS_LIVE_DB_BY_ENTRY = {1: 142, 2: 86, 3: 86, 4: 62, 5: 119, 6: 107, 7: 76}
#: 🔴 前端纯字面量口径（现算）
LANE1_KEYS_FRONTEND_BY_ENTRY = {1: 118, 2: 64, 3: 63, 4: 41, 5: 98, 6: 79, 7: 49}
LANE1_LIVE_NONEMPTY_KEYS_BY_ENTRY = {1: 26, 2: 11, 3: 3, 4: 2, 5: 6, 6: 5, 7: 1}
LANE1_LIVE_PAYLOAD_BYTES = 295_573

#: 7 个 orphan 的行数（`split("\n")` 口径）
LANE1_ORPHAN_LINE_COUNTS = {1: 115, 2: 115, 3: 115, 4: 126, 5: 126, 6: 125, 7: 116}

# ═══════════════════════════════════════════════════════════════════════════
# 消费边解析（statement-position import）
# ═══════════════════════════════════════════════════════════════════════════
#: 三形态：`from '…'` / `import('…')` / `require('…')`
IMPORT_FORMS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""from\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""require\s*\(\s*['"]([^'"\n]+)['"]"""),
)

FRONTEND_SRC = ROOT / "audit-platform" / "frontend" / "src"


def inside_double_quoted_string(line: str, pos: int) -> bool:
    """`pos` 是否落在**双引号字符串**内。

    🔴 为什么需要这个：`workpaperSyncLegacyBaseline.generated.ts` 的 JSON
    `"snippet"` 字段里含完整的 `from '...'` 形态（现算 9 处）。不排除就会把
    基线快照里的**文本**当成真实的 import 边，orphan 判定直接假红。
    """
    in_dq = False
    escaped = False
    for i, ch in enumerate(line):
        if i >= pos:
            break
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_dq = not in_dq
    return in_dq


def resolve_import(spec: str, importer: pathlib.Path) -> pathlib.Path | None:
    """把 import 说明符归一成仓库内绝对路径（无扩展名）。

    🔴 **路径相等**判定，不是 stem 相等 —— 同名文件在不同目录是不同模块。
    """
    if spec.startswith("@/"):
        base = FRONTEND_SRC / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    return base


def is_test_path(p: pathlib.Path) -> bool:
    s = p.as_posix()
    return (
        "__tests__" in s
        or "/tests/" in s
        or p.name.endswith((".spec.ts", ".test.ts", ".spec.vue"))
    )


def statement_edges_to(target: pathlib.Path) -> tuple[list[str], list[str]]:
    """返回 (生产边, 测试边)，格式 `相对路径#Lnn`。

    只认 statement-position 的 import 路径字面量，且排除双引号字符串内的匹配。
    """
    want = target.with_suffix("")
    prod: list[str] = []
    test: list[str] = []
    for p in FRONTEND_SRC.rglob("*"):
        if not p.is_file() or p.suffix not in (".ts", ".tsx", ".vue", ".js"):
            continue
        if p == target:
            continue
        text = cached_text(p)
        if target.stem not in text:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            for rx in IMPORT_FORMS:
                for m in rx.finditer(line):
                    if inside_double_quoted_string(line, m.start()):
                        continue
                    resolved = resolve_import(m.group(1), p)
                    if resolved is None:
                        continue
                    if resolved.with_suffix("") != want:
                        continue
                    ref = f"{p.relative_to(ROOT).as_posix()}#L{i}"
                    (test if is_test_path(p) else prod).append(ref)
    return sorted(prod), sorted(test)


# ═══════════════════════════════════════════════════════════════════════════
# 内联 IIFE 宿主形态
# ═══════════════════════════════════════════════════════════════════════════
INLINE_IIFE_RX = re.compile(r"const\s+dualMode\s*=\s*\(\(\)\s*=>")
LEGACY_HEALTH_EP = "/api/workpapers/onlyoffice/health"
LEGACY_CONFIG_EP = "onlyoffice-config"

#: 🔴 localStorage 前缀分裂：撞车 3 条 vs 孪生无持久化 4 条
PREFIX_COLLISION_ENTRIES: tuple[int, ...] = (4, 5, 6)
TWIN_NO_PERSIST_ENTRIES: tuple[int, ...] = (1, 2, 3, 7)

#: 🔴 列偏好类**不动**（KC-18）
COLUMN_PREFS_UNTOUCHED = (
    "useK1DetailColumnPrefs.ts",
    "useK4DetailColumnPrefs.ts",
)


def host_path(n: int) -> pathlib.Path:
    return WP_COMPONENTS / LANE1_HOSTS[n]


def orphan_path(n: int) -> pathlib.Path:
    return WP_COMPOSABLES / LANE1_ORPHANS[n]


def literal_count(p: pathlib.Path, needle: str) -> int:
    """剥注释后统计裸子串出现次数。"""
    return strip_comments(cached_text(p)).count(needle)
