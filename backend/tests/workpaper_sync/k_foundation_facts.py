# -*- coding: utf-8 -*-
"""K 循环 foundation spec 共享事实层。

spec: k-cycle-sync-foundation-and-first-canary

═══ 为什么需要它 ═══

foundation spec 的阶段 1 有 16 个 Task，每个都要现算同一批前端事实
（K 域文件集 / 端点命中 / 载体族 / 行身份族 / 键全集）。各 Task 各写一遍
= 多份漂移面：改了扫描口径只改一处、其余静默用旧基线。

本模块是**唯一口径真源**。两份 lane spec 也复用它。

🔴 口径铁律
- 行数一律 `len(text.split("\\n"))`（`splitlines()` 恒少 1）
- 剥注释同长空白替换，**保留行号**
- 端点正则**必须认反引号**（只认单/双引号会把 9 处 config 直调漏成 0）
- 枚举 K 宿主**必须排除** `GtKamWorkpaper.vue`（367 vs 368）
"""
from __future__ import annotations

import pathlib
import re
from collections import defaultdict

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
CYCLE_COMPOSABLES = FRONTEND / "composables" / "workpaper"
SYNC_DIR = WP_COMPONENTS / "sync"
DATA = BACKEND / "data"

KAM_HOST = "GtKamWorkpaper.vue"

#: 13 条 entry 的 wp_code 序号
K_INDEXES = tuple(range(1, 14))

#: 13 个宿主文件名（按序号）
K_HOSTS = {
    1: "GtK1OtherReceivables.vue",
    2: "GtK2OtherCurrentAssets.vue",
    3: "GtK3OtherPayables.vue",
    4: "GtK4OtherCurrentLiabilities.vue",
    5: "GtK5Provisions.vue",
    6: "GtK6HeldForSale.vue",
    7: "GtK7DeferredIncome.vue",
    8: "GtK8SellingExpenses.vue",
    9: "GtK9AdminExpenses.vue",
    10: "GtK10OtherIncome.vue",
    11: "GtK11AssetImpairmentLoss.vue",
    12: "GtK12NonOperatingIncome.vue",
    13: "GtK13NonOperatingExpense.vue",
}

#: BP-5 组（宿主内联 IIFE + orphan 孪生）= lane 1
BP5_INDEXES = (1, 2, 3, 4, 5, 6, 7)
#: BP-6 组（宿主 import 专用 composable）= foundation K10 + lane 2
BP6_INDEXES = (8, 9, 10, 11, 12, 13)


# ═══════════════════════════════════════════════════════════════════════════
# 文本与扫描口径
# ═══════════════════════════════════════════════════════════════════════════
_TEXT_CACHE: dict[str, str] = {}


def cached_text(p: pathlib.Path) -> str:
    key = str(p)
    if key not in _TEXT_CACHE:
        _TEXT_CACHE[key] = p.read_text(encoding="utf-8")
    return _TEXT_CACHE[key]


def _blank_keep_newlines(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_comments(source: str) -> str:
    """剥块 / 行 / HTML 注释，**行号不变**（同长空白替换）。

    🔴 行注释正则用 `(?<![:\\w\"'`\\\\])//` 避免吃掉 URL 的 `//`。
    """
    source = re.sub(r"/\*.*?\*/", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(
        r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source
    )
    return source


def line_count(p: pathlib.Path) -> int:
    """🔴 口径：`len(text.split("\\n"))`。`splitlines()` 恒少 1。"""
    return len(cached_text(p).split("\n"))


def line_count_splitlines(p: pathlib.Path) -> int:
    """对照口径，用于证明两者差 1。"""
    return len(cached_text(p).splitlines())


# ═══════════════════════════════════════════════════════════════════════════
# K 域文件集（KF-P5：367 / 含 KAM 368）
# ═══════════════════════════════════════════════════════════════════════════
def k_domain_files(*, include_kam: bool = False) -> list[pathlib.Path]:
    """K 域生产文件。口径与 slice 的 `scanned_scope` 逐字一致。"""
    out: list[pathlib.Path] = []
    for n in K_INDEXES:
        d = WP_COMPONENTS / f"k{n}"
        if d.is_dir():
            for p in d.rglob("*"):
                if (
                    p.is_file()
                    and p.suffix in (".ts", ".vue")
                    and "__tests__" not in p.as_posix()
                ):
                    out.append(p)
    for p in sorted(WP_COMPONENTS.iterdir()):
        if p.suffix == ".vue" and re.match(r"^GtK\d+", p.name):
            out.append(p)
        elif include_kam and p.name == KAM_HOST:
            out.append(p)
    for p in sorted(WP_COMPOSABLES.iterdir()):
        if p.suffix == ".ts" and re.match(
            r"^(use)?[kK](1[0-3]|[1-9])(?![0-9])", p.name
        ):
            out.append(p)
    for n in K_INDEXES:
        d = CYCLE_COMPOSABLES / f"k{n}"
        if d.is_dir():
            for p in d.rglob("*.ts"):
                if "__tests__" not in p.as_posix():
                    out.append(p)
    return sorted(set(out))


def host_path(n: int) -> pathlib.Path:
    return WP_COMPONENTS / K_HOSTS[n]


def dual_mode_path(n: int) -> pathlib.Path:
    return WP_COMPOSABLES / f"useK{n}DualMode.ts"


def form_data_path(n: int) -> pathlib.Path:
    return WP_COMPOSABLES / f"useK{n}FormData.ts"


# ═══════════════════════════════════════════════════════════════════════════
# 端点扫描（KC-3：必须认反引号）
# ═══════════════════════════════════════════════════════════════════════════
#: 🔴 认单引号 / 双引号 / **反引号**。漏反引号 ⇒ 9 处 config 直调记成 0。
ENDPOINT_RX = re.compile(r"['\"`](/api/[^'\"`]+)['\"`]")
#: 反证用：只认单/双引号。
ENDPOINT_RX_NO_BACKTICK = re.compile(r"['\"](/api/[^'\"]+)['\"]")


def normalize_endpoint(ep: str) -> str:
    """把 `${...}` 插值归一为 `{X}`。"""
    return re.sub(r"\$\{[^}]*\}", "{X}", ep)


def endpoint_index(
    files: list[pathlib.Path], *, recognize_backtick: bool = True
) -> tuple[dict[str, set[str]], dict[str, int]]:
    """返回 (endpoint -> 文件名集合, endpoint -> 处数)。"""
    rx = ENDPOINT_RX if recognize_backtick else ENDPOINT_RX_NO_BACKTICK
    by_file: dict[str, set[str]] = defaultdict(set)
    hits: dict[str, int] = defaultdict(int)
    for p in files:
        src = strip_comments(cached_text(p))
        for m in rx.finditer(src):
            ep = normalize_endpoint(m.group(1))
            by_file[ep].add(p.name)
            hits[ep] += 1
    return dict(by_file), dict(hits)


def literal_hits(files: list[pathlib.Path], needle: str) -> dict[str, int]:
    """逐文件统计裸子串命中次数（剥注释后）。返回 {文件名: 次数}，0 不收录。"""
    out: dict[str, int] = {}
    rx = re.compile(re.escape(needle))
    for p in files:
        src = strip_comments(cached_text(p))
        c = len(rx.findall(src))
        if c:
            out[p.name] = c
    return out


def exact_literal_hits(files: list[pathlib.Path], target: str) -> list[str]:
    """精确字面量命中：整个引号内容 == target，每行至多计一次。

    🔴 与子串口径的差异是 KA-P18 的反证对象（`K1-9-writeoff` 子串 12 vs 精确 9）。
    """
    rx = re.compile(r"['\"`]" + re.escape(target) + r"['\"`]")
    out: list[str] = []
    for p in files:
        src = strip_comments(cached_text(p))
        for i, line in enumerate(src.split("\n"), 1):
            if rx.search(line):
                out.append(f"{p.relative_to(ROOT).as_posix()}#L{i}")
    return out


def substring_literal_hits(files: list[pathlib.Path], target: str) -> list[str]:
    """子串口径（对照用）：引号内容**包含** target。"""
    rx = re.compile(r"['\"`][^'\"`]*" + re.escape(target) + r"[^'\"`]*['\"`]")
    out: list[str] = []
    for p in files:
        src = strip_comments(cached_text(p))
        for i, line in enumerate(src.split("\n"), 1):
            if rx.search(line):
                out.append(f"{p.relative_to(ROOT).as_posix()}#L{i}")
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 行身份四族判别式（KC-6）
# ═══════════════════════════════════════════════════════════════════════════
IDENTITY_KEY_RX = re.compile(r"(?<![\w$])(rowId|rowKey|id)\s*:\s*([^,\n]+)")
POSITIONAL_TOKEN_RX = re.compile(
    r"(?:^|[^\w$])(?:i|idx|index)(?:\s*\+\s*1)?(?:\s*\}|\s*[,)\]`]|$)"
)
POSITIONAL_INTERP_RX = re.compile(r"\$\{\s*(?:i|idx|index)\s*\}")
ENTROPY_RX = re.compile(r"Date\.now\(\)|Math\.random\(\)")
FALLBACK_RX = re.compile(r"\?\?|\|\|")


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 扫描器误报：固定槽位持久化键（2026-10-01 复盘 lane 1 Task 15 时登记）
# ═══════════════════════════════════════════════════════════════════════════
# KC-6 判别式只看「身份值里有没有下标 token」，分不清两种形态：
#   ① 动态行身份（行可增删、id 只在载荷内引用）—— 下标 = 缺陷，应值化
#   ② 固定槽位键（行集合由常量/配置派生、条数固定，rowKey 是**持久化 item_id 的一段**）
#      —— 下标就是槽位号，必须确定性，**值化 = 数据丢失**
# lane 1 Task 15 把 ② 也一律换成 `newRowIdentity()`，造成三处真回归：
#   · k1AdjudicationModel.ts  `a${i}` → `K1-1-aging-gross-a0-unadj`（文件自注「不能改」）
#     ⇒ 每次渲染换一套 key，存量账龄 AJE/RJE 全部读不回
#   · k1AdjK11Writeback.ts    `r${i}` → 写 `K1-1-${block}-${rowKey}-${field}`，
#     同函数仍读 `K1-1-${block}-r${i}-unadj` ⇒ **读写键分叉**，回写进孤儿键
#   · K5TabAdjudication.vue   `r${i}` → 「从专项表带入」按 rowKey 写 `K5-1-${rowKey}-unadj`，
#     同文件 L524 仍按 `r${idx}` 读 ⇒ 带入的值写进孤儿键、界面不显示
# 现已撤回为确定性槽位号。它们从 BP-8 分母里**重分类为误报**（不是「已收敛」）。
#: (文件名, 身份值原文, 该值流入的 item_id 模板片段) —— 第三元是可伪证依据
FIXED_SLOT_PERSISTED_KEY_SITES: tuple[tuple[str, str, str], ...] = (
    ("k1AdjudicationModel.ts", "`a${i}`", "K1-1-aging-gross-a0-unadj"),
    ("k1AdjK11Writeback.ts", "`r${i}`", "`K1-1-${block}-${rowKey}-${field}`"),
    ("K5TabAdjudication.vue", "`r${i}`", "`K5-1-${rowKey}-unadj`"),
)


def is_fixed_slot_exempt(p: pathlib.Path, value: str) -> bool:
    """该命中是否属登记的固定槽位持久化键（扫描器误报）。"""
    v = value.strip().rstrip(",")
    return any(p.name == f and v == val for f, val, _ in FIXED_SLOT_PERSISTED_KEY_SITES)


def family_of(value: str) -> str:
    """三族判别式 —— 可复算布尔表达式，不是人工归类。

    🔴 顺序要紧：同时含 ENTROPY 与 FALLBACK ⇒ family_b（是缺陷），不是放过。
    """
    if ENTROPY_RX.search(value) and not FALLBACK_RX.search(value):
        return "c"
    if FALLBACK_RX.search(value):
        return "b"
    return "a"


def positional_identity_hits(
    files: list[pathlib.Path],
) -> list[tuple[str, str, str]]:
    """返回 [(ref, key, value)]，与 slice 的 scan_recipe 同一口径。"""
    hits: list[tuple[str, str, str]] = []
    for p in files:
        src = strip_comments(cached_text(p))
        for i, line in enumerate(src.split("\n"), 1):
            for m in IDENTITY_KEY_RX.finditer(line):
                val = m.group(2).strip()
                if is_fixed_slot_exempt(p, val):
                    continue
                if POSITIONAL_TOKEN_RX.search(val) or POSITIONAL_INTERP_RX.search(val):
                    hits.append(
                        (f"{p.relative_to(ROOT).as_posix()}#L{i}", m.group(1), val)
                    )
    return hits


def family_census(files: list[pathlib.Path]) -> dict[str, int]:
    """三族计数 + total + defect。"""
    counts = {"a": 0, "b": 0, "c": 0}
    for _ref, _key, val in positional_identity_hits(files):
        counts[family_of(val)] += 1
    counts["total"] = counts["a"] + counts["b"] + counts["c"]
    counts["defect"] = counts["a"] + counts["b"]
    return counts


def entry_of_path(p: pathlib.Path) -> int | None:
    """从路径反推 entry 序号（K1..K13）。无法判定返回 None。

    🔴 前缀正则必须带 `(?![0-9])` 负向断言，否则 `K1` 会吃掉 `K10..K13`。
    """
    posix = p.as_posix()
    m = re.search(r"/k(1[0-3]|[1-9])(?![0-9])/", posix)
    if m:
        return int(m.group(1))
    m = re.match(r"^(?:use|Gt)?[kK](1[0-3]|[1-9])(?![0-9])", p.name)
    if m:
        return int(m.group(1))
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 业务键全集（KC-5）
# ═══════════════════════════════════════════════════════════════════════════
#: 业务持久化键：`K{n}-{...}` 完整字面量
BUSINESS_KEY_RX = re.compile(r"['\"`](K(?:1[0-3]|[1-9])-[A-Za-z0-9][A-Za-z0-9\-]*)['\"`]")
#: 复核会话键：`K{n}-review-session-{14位时间戳}`
REVIEW_SESSION_RX = re.compile(r"^K(?:1[0-3]|[1-9])-review-session-\d{14}$")
#: per-row 拆键：`K{n}-1-r-{6位base36}-{begin|unadj}`
PER_ROW_RX = re.compile(r"^K(?:1[0-3]|[1-9])-\d+-r-[0-9a-z]{6}-(?:begin|unadj)$")


def business_keys(files: list[pathlib.Path]) -> dict[str, set[str]]:
    """返回 {key: 出现该键的文件名集合}。"""
    out: dict[str, set[str]] = defaultdict(set)
    for p in files:
        src = strip_comments(cached_text(p))
        for m in BUSINESS_KEY_RX.finditer(src):
            out[m.group(1)].add(p.name)
    return dict(out)


def keys_by_entry(files: list[pathlib.Path]) -> dict[int, set[str]]:
    """按 entry 序号分组键集合。"""
    out: dict[int, set[str]] = defaultdict(set)
    for key in business_keys(files):
        m = re.match(r"^K(1[0-3]|[1-9])(?![0-9])", key)
        if m:
            out[int(m.group(1))].add(key)
    return dict(out)


# ═══════════════════════════════════════════════════════════════════════════
# derived_total（KC-16：正则必须覆盖中置形态）
# ═══════════════════════════════════════════════════════════════════════════
#: 只认尾部 —— 漏中置形态（K 有 6 个仅中置命中）
DERIVED_TAIL_RX = re.compile(r"-(total|subtotal|summary)$")
#: 尾部 + 中置
DERIVED_FULL_RX = re.compile(r"(?:^|-)(total|subtotal|summary)(?:-|$)")


def derived_total_keys(
    files: list[pathlib.Path], *, include_infix: bool = True
) -> set[str]:
    rx = DERIVED_FULL_RX if include_infix else DERIVED_TAIL_RX
    return {k for k in business_keys(files) if rx.search(k)}


# ═══════════════════════════════════════════════════════════════════════════
# removeRow 签名（KC-7：契约字段需四元组）
# ═══════════════════════════════════════════════════════════════════════════
#: 函数**定义**处（`function removeRow(...)` / `const removeRow = (...)`）
REMOVE_ROW_DEF_RX = re.compile(
    r"(?:function|const)\s+(\w*[Rr]emove\w*Row\w*)\s*(?:=\s*)?\(([^)]*)\)"
)
#: 函数定义 + 调用点（宽口径）
REMOVE_ROW_ANY_RX = re.compile(
    r"\b(?:remove|delete|handleRemove|handleDelete)\w*Row\w*\s*\(([^)]*)\)"
)
#: 下标族参数名（KC-7：K 有下标族，J 无）
POSITIONAL_PARAM_NAMES = ("$index", "idx", "actualIdx", "tableIndex", "index", "i")


def remove_row_definitions(
    files: list[pathlib.Path],
) -> dict[str, list[str]]:
    """函数定义处的签名 -> [文件名:函数名]。"""
    out: dict[str, list[str]] = defaultdict(list)
    for p in files:
        src = strip_comments(cached_text(p))
        for m in REMOVE_ROW_DEF_RX.finditer(src):
            out[m.group(2).strip()].append(f"{p.name}:{m.group(1)}")
    return dict(out)


def remove_row_sites(files: list[pathlib.Path]) -> dict[str, list[str]]:
    """定义 + 调用点的宽口径签名 -> [文件名]。"""
    out: dict[str, list[str]] = defaultdict(list)
    for p in files:
        src = strip_comments(cached_text(p))
        for m in REMOVE_ROW_ANY_RX.finditer(src):
            out[m.group(1).strip()].append(p.name)
    return dict(out)


def arity_of(params: str) -> int:
    """签名参数个数。"""
    return 0 if not params.strip() else params.count(",") + 1


def positional_remove_row_sites(
    files: list[pathlib.Path],
) -> dict[int, list[str]]:
    """下标族 removeRow 站点，按 entry 序号分组。"""
    rx = re.compile(
        r"\b(?:remove|handleRemove)\w*Row\w*\s*\(\s*"
        r"(?:\$index|idx|actualIdx|tableIndex|index)\b"
    )
    out: dict[int, list[str]] = defaultdict(list)
    for p in files:
        src = strip_comments(cached_text(p))
        for m in rx.finditer(src):
            e = entry_of_path(p)
            if e is not None:
                out[e].append(p.name)
    return dict(out)


# ═══════════════════════════════════════════════════════════════════════════
# 逐 entry 位置化缺陷分布（KC-6）
# ═══════════════════════════════════════════════════════════════════════════
def defect_by_entry(files: list[pathlib.Path]) -> dict[int, int]:
    """按 entry 序号统计 family_a + family_b（缺陷）命中数。"""
    out: dict[int, int] = defaultdict(int)
    for p in files:
        src = strip_comments(cached_text(p))
        for line in src.split("\n"):
            for m in IDENTITY_KEY_RX.finditer(line):
                val = m.group(2).strip()
                if is_fixed_slot_exempt(p, val):
                    continue
                if not (
                    POSITIONAL_TOKEN_RX.search(val)
                    or POSITIONAL_INTERP_RX.search(val)
                ):
                    continue
                if family_of(val) not in ("a", "b"):
                    continue
                e = entry_of_path(p)
                if e is not None:
                    out[e] += 1
    return dict(out)


# ═══════════════════════════════════════════════════════════════════════════
# family_d 展示序号（KC-6：不计入 total_hits）
# ═══════════════════════════════════════════════════════════════════════════
def display_seq_hits(files: list[pathlib.Path], key: str) -> int:
    """展示序号站点数（`seq: idx + 1` 形态）。"""
    rx = re.compile(rf"(?<![\w$]){re.escape(key)}\s*:\s*[^,\n]*(?:idx|index|\bi\b)\s*\+\s*1")
    total = 0
    for p in files:
        src = strip_comments(cached_text(p))
        total += len(rx.findall(src))
    return total


# ═══════════════════════════════════════════════════════════════════════════
# BP-8 收敛账本（lane 2 Task 13 起）—— 单一真源
# ═══════════════════════════════════════════════════════════════════════════
# 🔴 为什么要账本而不是直接改数字：
#   位置化行身份是**逐 lane 推进**的。若把判据里的 45 直接改成 24，就丢掉了
#   「改造前基线」这条审计轨迹，也没法再判「收敛是真的做了，还是被人顺手放宽了」。
#   账本让三件事同时可复算：
#     ① 改造前基线不被篡改（`BP8_BASELINE_*` 与 slice 登记逐条等值）
#     ② 收敛进度真实（现算 == 基线 − 已收敛量，两侧都验）
#     ③ 未收敛部分没退化（现算的缺陷 entry 集合 == 基线集合 − 已收敛集合）

#: 改造前基线（== slice `positional_identity_inventory` 的登记值，append-only）
BP8_BASELINE_TOTAL_HITS = 48
BP8_BASELINE_DEFECT = 45
BP8_BASELINE_FAMILY = {"a": 32, "b": 13, "c": 3}
BP8_BASELINE_DEFECT_BY_ENTRY = {1: 3, 3: 1, 5: 7, 6: 7, 7: 6, 8: 8, 9: 7, 11: 4, 12: 2}
BP8_BASELINE_ZERO_DEFECT_ENTRIES = (2, 4, 10, 13)

#: 🔴 已收敛的 entry —— **现已全 13 条**：
#:   · lane 2 Task 13 收敛 5 条（K8/K9/K11/K12/K13）
#:   · lane 1 Task 15 收敛 7 条（K1~K7）
#:   · K10 基线本就零缺陷（foundation canary）
#: 零缺陷的（K2/K4/K10/K13）列入是因为它们属各 lane 交付范围，同样受守卫约束。
BP8_CONVERGED_ENTRIES = tuple(range(1, 14))
#: 已收敛 entry 的族分解（用于 family_census 的收敛等式）。
#: lane 2 修 a 13 + b 8 = 21；lane 1 修 a 19 + b 5 = 24 ⇒ 合计 a 32 + b 13 = 45。
BP8_CONVERGED_FAMILY = {"a": 32, "b": 13}
#: 分 lane 的族分解（留档：两 lane 的交付量）
BP8_CONVERGED_FAMILY_BY_LANE = {
    "lane2": {"a": 13, "b": 8},
    "lane1": {"a": 19, "b": 5},
}
#: 🔴 顺带修掉的「判别式漏计」站点：`id: \`k81-${idx++}\`` 形态 2 处。
#: `${idx++}` 不匹配 `POSITIONAL_INTERP_RX` ⇒ 从来没进过基线 48，
#: 所以它**不参与**收敛等式，单独登记以免被当成基线误差。
BP8_EXTRA_FIXED_OUTSIDE_BASELINE = 2

#: 统一修复出口（值化身份工厂）
ROW_IDENTITY_MODULE = (
    WP_COMPOSABLES / "shared" / "rowIdentity.ts"
)
ROW_IDENTITY_FACTORY = "newRowIdentity"


# ═══════════════════════════════════════════════════════════════════════════
# 契约目录的「文件 ≠ 契约」口径
# ═══════════════════════════════════════════════════════════════════════════
# 🔴 为什么需要这一层：`backend/data/workpaper_sync_contracts/` 里**不全是契约**。
#   并发的 L 循环 spec 把一张键映射表 `_l_cycle_positional_key_mapping.json` 放进了
#   这个目录（它的内容是 `{_note, L5..L8, legacy_compat}`，没有 `review_status`，
#   也不是任何 adapter 的 `{adapter_id}.json`）。
#
#   生产侧不受影响 —— `contracts.load_contract()` 按**精确文件名**取，
#   `phase5_a51` 的分母按 `review_status == "reviewed"` 筛。但 K 的守卫原先按
#   「目录里每个 `*.json` 都是契约」写，于是被这一个文件打红。那是**口径错**
#   （前提不成立），不是 K 侧的缺陷。
#
#   处置：显式白名单 + **反向断言**（白名单成员必须真的不是契约、且白名单里不得有
#   失效条目）。只存一句理由的名单是「加一行就变绿」的后门（方法论铁律 ㉗⑤）。
CONTRACT_DIR = DATA / "workpaper_sync_contracts"

# ═══════════════════════════════════════════════════════════════════════════
# K 循环真双向晋级账本（2026-10-01）—— 「K 有没有生产契约 / adapter」的唯一真源
# ═══════════════════════════════════════════════════════════════════════════
# 🔴 原先 K 守卫写的是「K 循环生产契约数 == 0」「13 条 adapter_id 全 null」—— 那是**晋级前**
#    的事实。晋级后若把这些判据直接删掉，就失去「谁晋级了、谁没有、为什么」的审计轨迹；
#    若各文件各写一份清单，就是 N 个漂移面。⇒ 统一读这里，判据改成「恰好等于账本」。
#: reviewed 生产契约（6 条：调整分录汇总六册）。entry 序号 → contract_id。
K_REVIEWED_CONTRACTS: dict[int, str] = {
    1: "k1.baddebt_reversal_writeoff_check",
    8: "k8.selling_expenses_adjustment",
    9: "k9.admin_expenses_adjustment",
    10: "k10.other_income_adjustment",
    11: "k11.asset_impairment_loss_adjustment",
    12: "k12.non_operating_income_adjustment",
    13: "k13.non_operating_expense_adjustment",
}
#: 已发布首版 representation 且 manifest 翻成 bidirectional 的 entry（6 条：K1 + 5 条调整表）。
K_BIDIRECTIONAL_ENTRIES: tuple[int, ...] = (1, 8, 9, 11, 12, 13)
#: 契约已 reviewed、但**首版发布被 OOXML 安全门拒绝**的 entry 及原因（不是代码缺陷，
#: 是安全策略裁决：`workpaper_sync_limits.json` 的 `allow_embedded_objects=false`）。
K_PUBLISH_BLOCKED: dict[int, str] = {
    10: (
        "K10 权威模板 `K/K10 其他收益.xlsx` 的 `明细表K10-2` 嵌入了 2 个 Word 对象"
        "（xl/embeddings/Microsoft_Word___.docx / Microsoft_Word___1.docx），"
        "OOXML 安全门 embedded_objects 拒绝 ⇒ 首版发布停在 stage 3/10。"
        "解除需安全策略裁决（放行嵌入对象或剥离后重发模板），不在本 spec 内放宽。"
    ),
}


#: 13 条 entry 全名（序号 → entry_id）
K_ENTRY_ID_BY_INDEX: dict[int, str] = {
    1: "xlsx/gt-k1-other-receivables",
    2: "xlsx/gt-k2-other-current-assets",
    3: "xlsx/gt-k3-other-payables",
    4: "xlsx/gt-k4-other-current-liabilities",
    5: "xlsx/gt-k5-provisions",
    6: "xlsx/gt-k6-held-for-sale",
    7: "xlsx/gt-k7-deferred-income",
    8: "xlsx/gt-k8-selling-expenses",
    9: "xlsx/gt-k9-admin-expenses",
    10: "xlsx/gt-k10-other-income",
    11: "xlsx/gt-k11-asset-impairment-loss",
    12: "xlsx/gt-k12-non-operating-income",
    13: "xlsx/gt-k13-non-operating-expense",
}


def k_expected_manifest_adapters() -> dict[str, str]:
    """晋级账本推出的期望：{entry_id: adapter_id}（只含已翻 bidirectional 的 5 条）。"""
    return {K_ENTRY_ID_BY_INDEX[n]: K_REVIEWED_CONTRACTS[n] for n in K_BIDIRECTIONAL_ENTRIES}


def k_manifest_adapters(manifest: dict) -> dict[str, str]:
    """现算：manifest 里 wp_code_patterns 以 K 开头且 adapter_id 非空的 {entry_id: adapter_id}。"""
    return {
        e["entry_id"]: e["adapter_id"]
        for e in manifest["entries"]
        if e.get("adapter_id")
        and any(
            str(p).startswith("K")
            for p in ((e.get("wp_match") or {}).get("wp_code_patterns") or [])
        )
    }


def k_reviewed_contract_owners() -> dict[str, str]:
    """现算：契约目录里 review_status=reviewed 且归属 K 循环的 {文件名: entry_id}。"""
    import json as _json

    out: dict[str, str] = {}
    for p in sorted(CONTRACT_DIR.glob("*.json")):
        doc = _json.loads(p.read_text(encoding="utf-8"))
        if doc.get("review_status") != "reviewed":
            continue
        owner = str((doc.get("review") or {}).get("entry_id") or "")
        if re.match(r"^xlsx/gt-k(1[0-3]|[1-9])(?![0-9])-", owner):
            out[p.name] = owner
    return out


#: 契约目录里的**非契约**文件。新增条目必须同时说明归属 spec 与为何放在这里。
NON_CONTRACT_FILES_IN_CONTRACT_DIR: tuple[str, ...] = (
    # 归属 l5-l8-inert-switch-and-child-tab-carriers；读它的只有
    # `test_l_lane3_inert_and_carriers.py`（5 处硬编码该路径）⇒ 本 spec 不搬动它，
    # 只如实登记。搬家动作是跨 spec 待办。
    "_l_cycle_positional_key_mapping.json",
)


def contract_dir_split() -> tuple[dict[str, dict], dict[str, dict]]:
    """把契约目录按「有没有 `review_status`」分成 (契约, 非契约)。

    返回两个 `{文件名: 文档}`。判定依据是**文档结构**而不是文件名前缀 ——
    `_example.candidate.json` 同样以 `_` 开头，但它是合法 candidate 契约。
    """
    import json as _json

    contracts: dict[str, dict] = {}
    others: dict[str, dict] = {}
    for p in sorted(CONTRACT_DIR.glob("*.json")):
        doc = _json.loads(p.read_text(encoding="utf-8"))
        if doc.get("review_status") is None:
            others[p.name] = doc
        else:
            contracts[p.name] = doc
    return contracts, others


def bp8_expected_defect_total() -> int:
    """收敛等式右侧：基线 defect − 已收敛 entry 的基线 defect。"""
    return BP8_BASELINE_DEFECT - sum(
        BP8_BASELINE_DEFECT_BY_ENTRY.get(n, 0) for n in BP8_CONVERGED_ENTRIES
    )


def bp8_expected_defect_by_entry() -> dict[int, int]:
    """收敛后仍应有缺陷的 entry 及其条数（已收敛的一律不出现）。"""
    return {
        n: c
        for n, c in BP8_BASELINE_DEFECT_BY_ENTRY.items()
        if n not in BP8_CONVERGED_ENTRIES
    }


def bp8_expected_family() -> dict[str, int]:
    """收敛后的三族期望值（family_c 不参与修复，恒等）。"""
    return {
        "a": BP8_BASELINE_FAMILY["a"] - BP8_CONVERGED_FAMILY["a"],
        "b": BP8_BASELINE_FAMILY["b"] - BP8_CONVERGED_FAMILY["b"],
        "c": BP8_BASELINE_FAMILY["c"],
    }


#: `positional_row_id_template`（KC-24 第六个 hardcoded 模式）改造前基线
BP8_BASELINE_TEMPLATE_HITS = 13
#: 模板正则（`` `row-${idx} `` 类前缀）—— family_c 的 `` `row-${idx}-${Date.now()}` ``
#: 也带这个前缀，故收敛后它仍命中，属**故意保留**（非缺陷）。
TEMPLATE_ROW_ID_RX = re.compile(
    r"`(?:seed|row|detail|item)-\$\{\s*(?:i|idx|index)\s*\}"
)


def template_row_id_sites(files: list[pathlib.Path]) -> dict[str, int]:
    """逐文件统计模板命中数（0 不收录）。"""
    out: dict[str, int] = {}
    for p in files:
        c = len(TEMPLATE_ROW_ID_RX.findall(strip_comments(cached_text(p))))
        if c:
            out[p.name] = c
    return out


def identity_site_index(
    files: list[pathlib.Path],
) -> dict[str, tuple[int | None, str]]:
    """站点 -> (entry 序号, 族)。站点格式 `相对路径#Lnn`。"""
    out: dict[str, tuple[int | None, str]] = {}
    by_name = {p.name: p for p in files}
    for ref, _key, val in positional_identity_hits(files):
        head = ref.rsplit("#", 1)[0].rsplit("/", 1)[-1]
        p = by_name.get(head)
        out[ref] = (entry_of_path(p) if p else None, family_of(val))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# BP-5 删除账本（lane 1 Task 5 起）—— 单一真源
# ═══════════════════════════════════════════════════════════════════════════
# 🔴 与 BP-8 收敛账本同型：删除是**不可逆**的地基改动，判据必须同时守住
#   ① 改造前基线不被篡改（与 slice 登记逐条等值）
#   ② 删除量精确（现算 == 基线 − 已删）
#   ③ 删除范围没越界（留下的一个不少）

#: 🔴 lane 1 删掉的 7 个一阶 orphan（`useK{n}DualMode.ts`，n=1..7）。
#: 删除依据：生产边与测试边现算各 0 ∧ `composables/index.ts` 不存在
#: ∧ 无任何文件 `export * from` 指向它们 ⇒ 二阶恒 0。
BP5_DELETED_ORPHAN_ENTRIES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)
BP5_DELETED_ORPHAN_NAMES: tuple[str, ...] = tuple(
    f"useK{n}DualMode.ts" for n in BP5_DELETED_ORPHAN_ENTRIES
)
BP5_DELETED_COUNT = len(BP5_DELETED_ORPHAN_NAMES)

#: K 域文件数：删除前基线 / 含 KAM
BP5_K_DOMAIN_FILES_BASELINE = 367
BP5_K_DOMAIN_FILES_BASELINE_WITH_KAM = 368

#: 🔴 `useK*DualMode.ts` 文件数：13（全集）→ 删除后 6（BP-6 组）
BP5_DUALMODE_FILES_BASELINE = 13
BP5_DUALMODE_ENTRIES_REMAINING: tuple[int, ...] = (8, 9, 10, 11, 12, 13)

#: 🔴 legacy health 直调的三段式账本（**顺序要紧**）：
#:   ① design 写 spec 时 = 7 宿主 + 13 composable = **20**
#:   ② lane 2 把 6 个 live composable 收敛掉 ⇒ **14**（= 7 宿主 + 7 orphan）
#:   ③ lane 1 删 7 orphan ⇒ **7**（只剩宿主内联）
#:   ④ lane 1 Task 7 把 7 宿主改走 bridge ⇒ **0**
#: design 的「20 降为 13」是 ①→② 未发生时的预期；实际推进顺序是 lane 2 先做。
BP5_HEALTH_DESIGN_BASELINE = 20
BP5_HEALTH_AFTER_LANE2_CONVERGENCE = 14
BP5_HEALTH_AFTER_ORPHAN_DELETION = 7

#: localStorage：删除前 26 文件 / 模式偏好类 16（13 composable + 3 宿主）
BP5_LOCALSTORAGE_FILES_BASELINE = 26
BP5_MODE_PREF_FILES_BASELINE = 16


def bp5_expected_k_domain_files(*, include_kam: bool = False) -> int:
    """删除后的 K 域文件数 = 基线 − 7。"""
    base = (
        BP5_K_DOMAIN_FILES_BASELINE_WITH_KAM
        if include_kam
        else BP5_K_DOMAIN_FILES_BASELINE
    )
    return base - BP5_DELETED_COUNT


def bp5_orphan_is_deleted(name: str) -> bool:
    return name in BP5_DELETED_ORPHAN_NAMES


# ═══════════════════════════════════════════════════════════════════════════
# BP-5 宿主收敛账本（lane 1 Task 7~8）—— 删除账本的第二段
# ═══════════════════════════════════════════════════════════════════════════
#: 🔴 health 三段式的第 ④ 段：7 宿主改走 `fetchOnlyOfficeHealthy()` ⇒ K 域 **0**
BP5_HEALTH_AFTER_HOST_CONVERGENCE = 0

#: 🔴 K1/K2/K3/K7 **原先无持久化**，Task 7 统一目标态为「都持久化」⇒ 各新增 1 文件
BP5_HOSTS_GAINED_PERSISTENCE: tuple[int, ...] = (1, 2, 3, 7)
#: K4/K5/K6 原有 legacy 前缀，Task 7 收敛到统一键（文件数不变）
BP5_HOSTS_PREFIX_CONVERGED: tuple[int, ...] = (4, 5, 6)

#: 🔴 BP-7 notice 在 K 循环**全部兑现**：13 条宿主全挂
BP7_NOTICE_MOUNTED_ENTRIES: tuple[int, ...] = tuple(range(1, 14))
#: notice 符号的平台基线（design 口径，改造前）
BP7_NOTICE_COMPONENT_PLATFORM_BASELINE = 48
BP7_NOTICE_MODULE_PLATFORM_BASELINE = 2


def bp5_expected_localstorage_files() -> int:
    """localStorage 文件数 = 基线 26 − 删掉 7 + 新增持久化 4。"""
    return (
        BP5_LOCALSTORAGE_FILES_BASELINE
        - BP5_DELETED_COUNT
        + len(BP5_HOSTS_GAINED_PERSISTENCE)
    )


def bp5_expected_mode_pref_files() -> int:
    """模式偏好类 = 基线 16 − 删掉 7 + 新增持久化 4。"""
    return (
        BP5_MODE_PREF_FILES_BASELINE
        - BP5_DELETED_COUNT
        + len(BP5_HOSTS_GAINED_PERSISTENCE)
    )
