# -*- coding: utf-8 -*-
"""H 循环共享事实扫描器 —— 四份 H spec 的判据共用这一处**现算**实现。

spec: `h-cycle-sync-foundation-and-first-canary` · Task 1/5/6/7

═══ 为什么单独一个模块 ═══

H 循环有 4 份 spec（foundation + 3 lane），每份都要现算同一批前端/模板事实
（载体族 / 消费方计数 / 主表键命中 / 行身份族 / 裸 IF 计数 / 有效内容列）。
四份各写一遍 = 四份漂移面：改了扫描口径只改一处、另三处静默变旧基线。

🔴 **本模块只提供「怎么数」，不提供「应该是几」**。期望值一律写在各 spec 的判据里
（GC-10：零回归基线现算，不写死）。本模块返回现算结果，判据自己比。

🔴 **HC-3**：消费方计数区分 生产 / 测试 / 定义 三类。只有**生产消费 == 0** 才可删；
slice 的「零消费」名单必须重算（实测 `useH7FormData` / `useH9DualMode` 都不是孤儿）。

🔴 **HC-4**：主表键命中必须带**拼接解析**分支。`H5-2-rows` 字面量全仓零命中 ——
H5 全部键由 `` `${ITEM_PREFIX}-rows` `` 拼接。只做字面量 grep 必假红。
"""
from __future__ import annotations

import functools
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence

_REPO: Final[Path] = Path(__file__).resolve().parents[3]
BACKEND: Final[Path] = _REPO / "backend"
FRONTEND_SRC: Final[Path] = _REPO / "audit-platform" / "frontend" / "src"
WORKPAPER_DIR: Final[Path] = FRONTEND_SRC / "components" / "workpaper"
COMPOSABLES: Final[Path] = WORKPAPER_DIR / "composables"
TPL_H: Final[Path] = BACKEND / "wp_templates" / "H"
SLICE_PATH: Final[Path] = BACKEND / "data" / "workpaper_sync_h_cycle_manifest_slice.json"
CONTRACTS_DIR: Final[Path] = BACKEND / "data" / "workpaper_sync_contracts"

#: 9 条独立 entry（H1 pilot / H0 函证 / 5 条子入口均不在内）。
H_ENTRY_IDS: Final[tuple[str, ...]] = (
    "xlsx/gt-h2-construction-in-progress",
    "xlsx/gt-h3-investment-property",
    "xlsx/gt-h4-engineering-materials",
    "xlsx/gt-h5-oil-gas-assets",
    "xlsx/gt-h6-asset-disposal-clearing",
    "xlsx/gt-h7-biological-assets",
    "xlsx/gt-h8-right-of-use-assets",
    "xlsx/gt-h9-lease-liabilities",
    "xlsx/gt-h10-asset-disposal-income",
)

#: 5 条 parent_duplicate 子入口（manifest 现算 `xlsx/hN/...` 路径）。
H_SUB_ENTRY_IDS: Final[tuple[str, ...]] = (
    "xlsx/h4/impairment/h4-tab-impairment",
    "xlsx/h4/impairment/h4-tab-recoverable",
    "xlsx/h8/impairment/h8-tab-recoverable",
    "xlsx/h8/measurement/h8-tab-measurement-annual",
    "xlsx/h8/measurement/h8-tab-measurement-monthly",
)

#: entry 短码 → 宿主文件名（按值实测，不按命名推演）。
H_HOSTS: Final[Mapping[str, str]] = {
    "H2": "GtH2ConstructionInProgress.vue",
    "H3": "GtH3InvestmentProperty.vue",
    "H4": "GtH4EngineeringMaterials.vue",
    "H5": "GtH5OilGasAssets.vue",
    "H6": "GtH6AssetDisposalClearing.vue",
    "H7": "GtH7BiologicalAssets.vue",
    "H8": "GtH8RightOfUseAssets.vue",
    "H9": "GtH9LeaseLiabilities.vue",
    "H10": "GtH10AssetDisposalIncome.vue",
}

#: entry 短码 → 权威模板文件名（sha256 由 slice 冻结，见 :func:`authoritative_templates`）。
H_TEMPLATES: Final[Mapping[str, str]] = {
    "H2": "H2 在建工程.xlsx",
    "H3": "H3 投资性房地产.xlsx",
    "H4": "H4 工程物资.xlsx",
    "H5": "H5 油气资产.xlsx",
    "H6": "H6 固定资产清理.xlsx",
    "H7": "H7 生产性生物资产.xlsx",
    "H8": "H8 使用权资产.xlsx",
    "H9": "H9 租赁负债.xlsx",
    "H10": "H10 资产处置损益.xlsx",
}

#: 9 条 entry 的主受管表键（实测定位见各 lane spec）。
#: 🔴 `H5-2-rows` 是**拼接键**（`useH5Detail.ts` 的 `${ITEM_PREFIX}-rows`），
#: 字面量全仓零命中 —— 见 :func:`resolve_item_key_hits`（HC-4）。
H_PRIMARY_KEYS: Final[Mapping[str, str]] = {
    "H2": "H2-2-rows",
    "H3-cost": "H3-2-cost-rows",
    "H3-fair": "H3-2-fair-rows",
    "H4": "H4-2-rows",
    "H5": "H5-2-rows",
    "H6": "H6-2-rows",
    "H7-cost": "H7-2-cost-rows",
    "H7-fair": "H7-2-fair-rows",
    "H8": "H8-2-rows",
    "H9": "H9-2-rows",
    "H10": "H10-detail-rows",
}

#: HC-8 冻结键：被**已注册 adapter 的 H1 pilot** 或 **G 循环** 消费，本轮不改键名。
H_FROZEN_KEYS: Final[tuple[str, ...]] = (
    "H2-2-rows",
    "H6-1-rows",
    "H6-2-rows",
    "H6-1-end-balance-audited",
    "H10-detail-rows",
    "H3-2-fair-rows",
)

#: HC-9（BP-12）：`h10RelatedH6Pull.ts` 回退链里的两个**猜测键**（H6 侧生产命中 0）。
H_GUESSED_KEYS: Final[tuple[str, ...]] = ("H6-detail-rows", "H6-clearing-rows")


@dataclass(frozen=True)
class SourceFile:
    """一个前端源文件的扫描视图。"""

    rel: str
    text: str
    is_test: bool
    stem: str

    def count(self, needle: str) -> int:
        return self.text.count(needle)

    def line_of(self, offset: int) -> int:
        return self.text.count("\n", 0, offset) + 1


@functools.lru_cache(maxsize=1)
def frontend_files() -> tuple[SourceFile, ...]:
    """全仓 `.ts` / `.vue`（一次读盘，四份 spec 的判据共享缓存）。"""
    out: list[SourceFile] = []
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".vue"}:
            continue
        rel = str(path.relative_to(FRONTEND_SRC)).replace("\\", "/")
        out.append(
            SourceFile(
                rel=rel,
                text=path.read_text(encoding="utf-8", errors="replace"),
                is_test="__tests__" in rel or rel.endswith(".spec.ts"),
                stem=path.stem,
            )
        )
    return tuple(out)


def workpaper_files(*, include_tests: bool = False) -> tuple[SourceFile, ...]:
    """只取 `components/workpaper/` 下的（H 循环的作业面）。"""
    return tuple(
        f
        for f in frontend_files()
        if f.rel.startswith("components/workpaper/") and (include_tests or not f.is_test)
    )


@dataclass(frozen=True)
class ConsumerCount:
    """HC-3 消费方计数：生产 / 测试 / 定义 三分。"""

    name: str
    production: tuple[str, ...]
    tests: tuple[str, ...]
    definitions: tuple[str, ...]

    @property
    def deletable(self) -> bool:
        """🔴 只有**生产消费 == 0** 才可删（HC-3 第 1 条）。"""
        return len(self.production) == 0 and len(self.definitions) > 0

    @property
    def defined(self) -> bool:
        return bool(self.definitions)


def count_consumers(name: str) -> ConsumerCount:
    """按 `\\b<name>\\b` 现算某载体的消费方（HC-3）。

    `definitions` = 文件名恰为该符号的文件（`useH5DualMode.ts` 定义 `useH5DualMode`）。
    定义文件里的自引用不计入生产消费 —— 否则每个载体都"至少被自己消费一次"，判据恒真。
    """
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    production: list[str] = []
    tests: list[str] = []
    definitions: list[str] = []
    for f in frontend_files():
        hits = len(pattern.findall(f.text))
        if not hits:
            continue
        if f.stem == name:
            definitions.append(f.rel)
        elif f.is_test:
            tests.append(f"{f.rel}:{hits}")
        else:
            production.append(f"{f.rel}:{hits}")
    return ConsumerCount(
        name=name,
        production=tuple(production),
        tests=tuple(tests),
        definitions=tuple(definitions),
    )


#: HC-4：`` `${CONST}-suffix` `` 拼接形态。捕获常量名与后缀。
_TEMPLATE_CONCAT_RE: Final[re.Pattern[str]] = re.compile(
    r"`\$\{(?P<const>[A-Za-z_][A-Za-z0-9_]*)\}(?P<suffix>-[A-Za-z0-9\-]+)`"
)
#: 常量字面量声明（`const ITEM_PREFIX = 'H5-2'`）。
_CONST_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r"const\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[^=]+)?=\s*['\"](?P<value>[^'\"]+)['\"]"
)


def template_concat_keys(f: SourceFile) -> dict[str, str]:
    """解析一个文件里全部 `` `${CONST}-suffix` `` 的**拼接结果** → 常量名。

    HC-4：H5 的 16 个 PREFIX 常量决定它全部 item_id，字面量在源码里根本不出现。
    """
    consts = {m.group("name"): m.group("value") for m in _CONST_LITERAL_RE.finditer(f.text)}
    out: dict[str, str] = {}
    for m in _TEMPLATE_CONCAT_RE.finditer(f.text):
        value = consts.get(m.group("const"))
        if value:
            out[f"{value}{m.group('suffix')}"] = m.group("const")
    return out


@dataclass(frozen=True)
class KeyHits:
    """一个 store item 键的命中分布（字面量 + 拼接两路）。"""

    key: str
    literal: tuple[str, ...]
    concatenated: tuple[str, ...]

    @property
    def production_files(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.literal) | set(self.concatenated)))

    @property
    def resolved(self) -> bool:
        return bool(self.production_files)


def resolve_item_key_hits(key: str, *, include_tests: bool = False) -> KeyHits:
    """现算一个 item_id 的生产命中（**含 HC-4 拼接解析分支**）。

    🔴 变异「去掉 `concatenated` 分支」⇒ `H5-2-rows` 判为零命中 ⇒ 打红。
    这正是 slice 把 H5 主表键记成缺陷的原因：它只做了字面量 grep。
    """
    literal: list[str] = []
    concatenated: list[str] = []
    for f in frontend_files():
        if f.is_test and not include_tests:
            continue
        hits = f.count(key)
        if hits:
            literal.append(f.rel)
        if key in template_concat_keys(f):
            concatenated.append(f.rel)
    return KeyHits(key=key, literal=tuple(literal), concatenated=tuple(concatenated))


#: 读取形态：`getString(K)` / `_getJson(K)` / `map.get(K)` / `pick(K)` / `resolve…(K)` …
#: 参数既可以是键字面量，也可以是绑定该字面量的模块常量（`const ROWS_KEY = 'H8-2-rows'`）。
_READ_CALL_TEMPLATE: Final[str] = (
    r"(?:\.get|\bget[A-Za-z]*|\b_get[A-Za-z]*|\bpick[A-Za-z]*|\bread[A-Za-z]*|"
    r"\bload[A-Za-z]*|\bfetch[A-Za-z]*|\bresolve[A-Za-z]*)\(\s*{arg}\s*[,)]"
)


def key_read_sites(key: str) -> tuple[str, ...]:
    """现算某 store item 键的**读取点**（含模块常量间接引用）。

    🔴 这是区分 **BP-5（写进零消费方）** 与 **H7-2-fair-rows（自读自写、正常）** 的判据。
    只看「生产命中文件数 == 1」两者都命中 1 ⇒ 会把 H7 误判成缺陷（HC-6 第 4 条）。
    只看「有无对应 total 键」也不行 —— 实测 `H7-2-fair-total` **并不存在**
    （只有 `H7-2-cost-total`），H7 公允价值侧靠 Tab 自身回读。

    ⇒ 权威判据是「**有无读取点**」：
    * `H8-2-detail-prefill` —— 全仓只有 `map.set(...)`，**零读取点** ⇒ 缺陷；
    * `H7-2-fair-rows` —— `H7TabDetailFair.vue` 里 `getString('H7-2-fair-rows')` ⇒ 正常。
    """
    out: list[str] = []
    literal_pat = re.compile(_READ_CALL_TEMPLATE.format(arg=rf"['\"]{re.escape(key)}['\"]"))
    for f in frontend_files():
        if f.is_test:
            continue
        if literal_pat.search(f.text):
            out.append(f.rel)
            continue
        # 常量间接：`const ROWS_KEY = 'H8-2-rows'` → `_getJson(ROWS_KEY)`
        for m in _CONST_LITERAL_RE.finditer(f.text):
            if m.group("value") != key:
                continue
            const_pat = re.compile(_READ_CALL_TEMPLATE.format(arg=re.escape(m.group("name"))))
            if const_pat.search(f.text):
                out.append(f.rel)
                break
    return tuple(sorted(set(out)))


# ═══════════════════════════════════════════════════════════════════════════
# HC-7 行身份三族
# ═══════════════════════════════════════════════════════════════════════════

#: 族 B：身份值整体由数组下标构成（`seed-${i}` / `seed-${idx}`）。
FAMILY_B_RE: Final[re.Pattern[str]] = re.compile(r"rowId\s*:\s*`[^`]*seed-\$\{")

#: 族 C：身份内嵌**业务名称**且无随机后缀 ⇒ 改名即身份漂移。
#: 🔴 slice `positional_identity_inventory` 只扫族 B，完全漏掉这族（HC-7 第 3 条）。
#: 🔴 `prefix` 刻意**不在**业务名 token 里 —— `useH5Adjudication.ts` 的
#: `` `row-${prefix}-subtotal` `` 中 `prefix` 是常量（`H5-1`）不是业务名，属族 A/安全形态。
FAMILY_C_TOKENS: Final[tuple[str, ...]] = (
    "category",
    "name",
    "label",
    "item",
    "cat",
    "kind",
)
FAMILY_C_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:rowId|id)\s*:\s*`[^`]*\$\{[^}]*(?:"
    + "|".join(FAMILY_C_TOKENS)
    + r")[^}]*\}[^`]*`"
)
#: 族 A 标记：带随机 / 时间戳后缀 ⇒ 业务名改动不影响身份。
FAMILY_A_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(r"Math\.random|Date\.now|randomUUID")

#: 本轮作业面（H2~H10）。🔴 H1 是**已注册 adapter 的 pilot**，其族 C 4 处不在本轮范围。
_H_SCOPE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|/)(?:h(?:2|3|4|5|6|7|8|9|10)/|useH(?:2|3|4|5|6|7|8|9|10)[A-Z]|GtH(?:2|3|4|5|6|7|8|9|10)[A-Z]|h(?:2|3|4|5|6|7|8|9|10)[A-Z])"
)


def in_h_scope(rel: str) -> bool:
    """该文件是否属 H2~H10 作业面（排除 H1 pilot 与 H0 函证）。"""
    return bool(_H_SCOPE_RE.search(rel))


@dataclass(frozen=True)
class IdentityHit:
    rel: str
    line: int
    fragment: str

    def __str__(self) -> str:  # pragma: no cover - 仅供断言消息
        return f"{self.rel}#L{self.line} {self.fragment}"


def scan_identity_family(pattern: re.Pattern[str], *, exclude_family_a: bool) -> tuple[IdentityHit, ...]:
    """扫 H2~H10 作业面的行身份形态。

    :param exclude_family_a: 剔除带随机/时间戳后缀的形态（族 C 扫描必须剔，否则把安全形态算进来）。
    """
    out: list[IdentityHit] = []
    for f in workpaper_files():
        if not in_h_scope(f.rel):
            continue
        for m in pattern.finditer(f.text):
            frag = m.group(0)
            if exclude_family_a and FAMILY_A_SUFFIX_RE.search(frag):
                continue
            out.append(IdentityHit(rel=f.rel, line=f.line_of(m.start()), fragment=frag))
    return tuple(out)


# ═══════════════════════════════════════════════════════════════════════════
# HC-6 派生合计副本
# ═══════════════════════════════════════════════════════════════════════════

_TOTAL_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"['\"](H(?:1|2|3|4|5|6|7|8|9|10)[A-Za-z0-9\-]*-(?:total|subtotal|summary)[A-Za-z0-9\-]*)['\"]"
)


def derived_total_keys() -> dict[str, tuple[str, ...]]:
    """现算全 H 的派生合计键 → 生产消费文件。

    🔴 HC-6：这些键**排除在 roundtrip 业务比对之外**（否则「OO 改明细 → 平台重算合计」
    会被判成用户编辑了合计）。🔴 **禁止写死个数** —— 数量随功能演进变化（GC-10）。
    """
    out: dict[str, set[str]] = {}
    for f in frontend_files():
        if f.is_test:
            continue
        for m in _TOTAL_KEY_RE.finditer(f.text):
            out.setdefault(m.group(1), set()).add(f.rel)
    return {k: tuple(sorted(v)) for k, v in sorted(out.items())}


def entry_prefix_of(key: str) -> str:
    """`H8-1-cost-audited-total` → `H8`（按数字边界切，`H10` 不会被切成 `H1`）。"""
    m = re.match(r"^(H\d+)", key)
    return m.group(1) if m else ""


def cycle_prefix_of(key: str) -> str:
    """任意循环码前缀：`H6-2-rows`→`H6` · `L1-pledge-rows`→`L1` · `K11-2-rou`→`K11`。"""
    m = re.match(r"^([A-Z]\d{1,2})", key)
    return m.group(1) if m else ""


def producers_in_owning_entry_scope(key: str) -> tuple[str, ...]:
    """现算某键在**它自己所属 entry 的作业面**里的生产命中。

    🔴 这是判定「猜测键」的正确口径（HC-9）。用「消费方文件之外还有没有命中」不行 ——
    实测 `H6-detail-rows` 在 `h10RelatedH6Pull.ts` **和** `useH10CrossSheet.ts` 两处出现，
    但两处都是 **H10 侧**消费方 ⇒ 按「消费方之外」算会判它有生产者，实际 H6 侧一个都没有。
    """
    prefix = cycle_prefix_of(key)
    if not prefix:
        return ()
    letter, digits = prefix[0], prefix[1:]
    scope = re.compile(
        rf"(?:^|/)(?:{letter.lower()}{digits}/"
        rf"|use{letter}{digits}[A-Z]"
        rf"|Gt{letter}{digits}[A-Z]"
        rf"|{letter.lower()}{digits}[A-Z])"
    )
    return tuple(
        rel for rel in resolve_item_key_hits(key).production_files if scope.search(rel)
    )


# ═══════════════════════════════════════════════════════════════════════════
# HC-9 猜键回退链（BP-12）
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 **不是只认 `const keys = [...]`**。spec 的 HC-9 只记了一处
#: （`h10RelatedH6Pull.ts#L59` 的 `const keys`），本轮按值实测另有两处**同族**形态：
#: * `useH6Check.ts#L508` —— 同样是 `const keys = [...]`，4 键里 3 键零生产；
#: * `h6H10Pull.ts#L43` —— 变量名是 `keyPriority`，`for (const key of keyPriority)` 逐个试，
#:   4 键里 **4 键全部零生产**。
#: ⇒ 扫描口径必须按**结构**（数组字面量里 ≥2 个 store-item 形状的字符串 + 被逐个试）而不是变量名。
_KEY_ARRAY_RE: Final[re.Pattern[str]] = re.compile(
    r"const\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[^=]+)?=\s*\[(?P<body>[^\]]*)\]", re.S
)
_QUOTED_RE: Final[re.Pattern[str]] = re.compile(r"['\"]([^'\"]+)['\"]")
#: store item id 形状 = **审计循环码前缀**（`H8-2-rows` / `D5-2-detail-rows` / `K11-source-H8-amount`）。
#: 刻意**不**匹配无循环码前缀的通用键（`applicable_standards` / `subsequent-cost`）——
#: 那些是页内小节键或跨模块通用键，不是「按循环码寻址的 store item」，混进来会造 12 处误命中。
_ITEM_ID_SHAPE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z]\d{1,2}[A-Za-z]?-[A-Za-z0-9\-_]+$")


def multi_key_fallback_chains() -> dict[str, tuple[str, ...]]:
    """现算 H 作业面里**多键回退链**（不限变量名）。

    HC-9：回退链里每个键都必须「H 侧生产命中 > 0」，否则是猜测键 ⇒ 上游改键后静默取空。

    判定一个数组是回退链的条件（结构性，不看变量名）：
    1. 数组字面量里有 **≥ 2** 个 store-item 形状的字符串；
    2. 该数组变量在同文件里被**逐个试**（`for (const … of NAME)` / `NAME.map` / `NAME.find`）。
    """
    out: dict[str, tuple[str, ...]] = {}
    for f in workpaper_files():
        if not in_h_scope(f.rel):
            continue
        for m in _KEY_ARRAY_RE.finditer(f.text):
            keys = tuple(
                k for k in _QUOTED_RE.findall(m.group("body")) if _ITEM_ID_SHAPE_RE.match(k)
            )
            if len(keys) < 2:
                continue
            name = m.group("name")
            # 🔴 只在**声明之后**找迭代点。同名局部变量（`keys`）在一个文件里可能出现多次，
            #    从文件头搜会配到上一个同名变量的循环（实测 `useH6Check.ts` 声明在 L508
            #    却配到 L281 的另一处 `for (const key of keys)`，于是整条链被漏扫）。
            iterated = re.search(
                rf"(?:for\s*\(\s*const\s+\w+\s+of\s+{re.escape(name)}\b"
                rf"|{re.escape(name)}\s*\.(?:map|find|forEach|some|every)\()",
                f.text[m.end() :],
            )
            if iterated is None:
                continue
            iter_end = m.end() + iterated.end()
            # 🔴 回退链的判定还要**两个**结构特征，否则会把「目录 sheet 码清单」
            #    「分析指标名清单」「默认行对象数组」全算进来（实测这三类共 12 处误命中）：
            #    ① 循环体里做 **store item 查表**；② 有 **早退**（`break` / `return`）。
            body = f.text[iter_end : iter_end + 900]
            looks_up_store = re.search(
                r"item_id\s*===|loadResponseItem\(|_getItemRaw\(|getString\(|_getJson\(|\.get\(",
                body,
            )
            early_exit = re.search(r"\b(?:break|return)\b", body)
            if looks_up_store is None or early_exit is None:
                continue
            out[f"{f.rel}#L{f.line_of(m.start())}"] = keys
    return out


# ═══════════════════════════════════════════════════════════════════════════
# HC-12 per-file 裸 IF 中性化 · HC-13 宽表有效内容列 · HC-14 四个干净点
# ═══════════════════════════════════════════════════════════════════════════


@functools.lru_cache(maxsize=16)
def bare_if_cell_count(entry_code: str) -> int:
    """按**生产函数的正则**现算一册的裸 `IF(` **格数**（不是出现次数）。

    🔴 HC-12：口径必须与 `g7_oo_crash_if_neutralize._BARE_IF_CALL` 一致 ——
    spec 表里若记的是 `findall` 出现次数（一格嵌两层 IF 算两次）会与本函数差一截。
    """
    import openpyxl

    from app.services.workpaper_sync.g7_oo_crash_if_neutralize import _BARE_IF_CALL

    wb = openpyxl.load_workbook(TPL_H / H_TEMPLATES[entry_code], data_only=False)
    count = 0
    for name in wb.sheetnames:
        for row in wb[name].iter_rows():
            for cell in row:
                value = cell.value
                if isinstance(value, str) and value.startswith("=") and _BARE_IF_CALL.search(value):
                    count += 1
    wb.close()
    return count


@functools.lru_cache(maxsize=16)
def workbook_clean_points(entry_code: str) -> dict[str, object]:
    """HC-14 四个干净点 + HC-7 附带事实，一册一次读盘。"""
    import openpyxl

    wb = openpyxl.load_workbook(TPL_H / H_TEMPLATES[entry_code], data_only=False)
    tables: dict[str, list[str]] = {}
    hidden: list[str] = []
    for name in wb.sheetnames:
        ws = wb[name]
        if ws.tables:
            tables[name] = sorted(ws.tables.keys())
        if ws.sheet_state != "visible":
            hidden.append(name)
    out = {
        "sheet_count": len(wb.sheetnames),
        "sheet_names": tuple(wb.sheetnames),
        "defined_name_count": len(list(wb.defined_names)),
        "excel_tables": tables,
        "hidden_sheets": tuple(hidden),
    }
    wb.close()
    return out


@functools.lru_cache(maxsize=1)
def authoritative_templates() -> dict[str, dict[str, object]]:
    """slice 冻结的 11 个 H 模板字节事实 + **现算 sha256 复核**。"""
    doc = json.loads(SLICE_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict[str, object]] = {}
    for item in doc["authoritative_templates"]["files"]:
        path = TPL_H / str(item["name"])
        data = path.read_bytes()
        out[str(item["name"])] = {
            "frozen_sha256": str(item["sha256"]),
            "actual_sha256": hashlib.sha256(data).hexdigest(),
            "frozen_size": int(item["size"]),
            "actual_size": len(data),
            "belongs_to_entry": item.get("belongs_to_entry"),
            "in_runtime_index": bool(item.get("in_runtime_index")),
        }
    return out


def effective_content_columns(
    entry_code: str, sheet_name: str, rows: Sequence[int]
) -> int:
    """HC-13：按**有效内容列**而非 `max_column` 现算列边界。

    宽表 `max_column` 250~257 但有效列 6~14 —— 按 `max_column` 放 UUID 会落在 251+ 列。
    """
    import openpyxl

    wb = openpyxl.load_workbook(TPL_H / H_TEMPLATES[entry_code], data_only=False)
    ws = wb[sheet_name]
    eff = 0
    for r in rows:
        for c in range(1, ws.max_column + 1):
            value = ws.cell(row=r, column=c).value
            if value is not None and str(value).strip() != "":
                eff = max(eff, c)
    wb.close()
    return eff


# ═══════════════════════════════════════════════════════════════════════════
# HC-2 载体族七分（写 4 族 × 读 4 族 × TB 门 2 族）
# ═══════════════════════════════════════════════════════════════════════════

WRITE_HOST_INLINE: Final[str] = "host_inline"
WRITE_FORMDATA: Final[str] = "formdata_composable"
WRITE_PER_TAB_INSTANCE: Final[str] = "per_tab_formdata_instance"
WRITE_PER_TAB_SELF: Final[str] = "per_tab_self_persisting"

READ_CHECKLIST_GET: Final[str] = "checklist_get"
READ_SNAPSHOT: Final[str] = "html_data_snapshot"
READ_RENDER_CONFIG: Final[str] = "render_config_force_component_type"
READ_BOTH: Final[str] = "checklist_get+html_data_snapshot"


@dataclass(frozen=True)
class HostFacts:
    """一个宿主 `.vue` 的按值实测（HC-2 族分派的输入，**不按文件名推断**）。"""

    code: str
    http_import: int
    checklist_put: int
    checklist_get: int
    force_component_type: int
    responses_snapshot: int
    bridge: int
    legacy_oo: int
    notice: int
    ocr: int
    adjustment_central_sync: int
    local_storage: int
    publish_to_tb: int


_PUT_RE: Final[re.Pattern[str]] = re.compile(r"\.put\(\s*[`'\"][^`'\"]*checklist-responses")
_GET_RE: Final[re.Pattern[str]] = re.compile(r"\.get\(\s*[`'\"][^`'\"]*checklist-responses")


def host_facts(code: str) -> HostFacts:
    """现算一个宿主的载体信号（HC-2）。"""
    text = (WORKPAPER_DIR / H_HOSTS[code]).read_text(encoding="utf-8", errors="replace")
    return HostFacts(
        code=code,
        http_import=len(re.findall(r"import\s+http\s+from\s+'@/utils/http'", text)),
        checklist_put=len(_PUT_RE.findall(text)),
        checklist_get=len(_GET_RE.findall(text)),
        force_component_type=text.count("force_component_type"),
        responses_snapshot=text.count("responses_snapshot"),
        bridge=len(re.findall(r"useWorkpaperSyncBridge|WorkpaperSyncEditorHost", text)),
        legacy_oo=text.count("GtOnlyOfficeSheet"),
        notice=text.count("GtEntrySyncCapabilityNotice"),
        ocr=len(re.findall(r"OcrConfirm|runOcr", text)),
        adjustment_central_sync=text.count("useAdjustmentCentralSync"),
        local_storage=text.count("localStorage"),
        publish_to_tb=text.count("publishToTb"),
    )


#: 前端受管清单（接桥声明的唯一真源）。
_H_MANAGED_TS: Final[Path] = (
    WORKPAPER_DIR / "sync" / "hManagedSheets.ts"
)


def wired_entry_codes() -> frozenset[str]:
    """现算**已接统一双向桥**的 entry 短码集合（如 `{"H9"}`）。

    真源 = 前端 `sync/hManagedSheets.ts` 的 `H_OO_WIRED_ROWS_CODES`（sheet 短码，
    如 `H9-2`），在此归一到 entry 短码（`H9`）。

    🔴 **不写死**：接桥面会随 8 条 lane 逐条增长。守卫据本函数分派「该 entry 应有桥 /
    应无桥」，清单一改判据自动跟随，不会出现「代码接了桥而守卫还断言 0」的假红，也不会
    出现「守卫放宽成 >=0」的假绿。清单与后端 provider 的一致性另由
    `test_h_frontend_managed_sheet_parity.py` 逐字守护。
    """
    if not _H_MANAGED_TS.exists():
        return frozenset()
    src = _H_MANAGED_TS.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"H_OO_WIRED_ROWS_CODES:\s*readonly\s+string\[\]\s*=\s*Object\.freeze\(\[(.*?)\]\)",
        src,
        re.S,
    )
    if not m:
        return frozenset()
    codes = re.findall(r"'([^']+)'", m.group(1))
    # `H9-2` → `H9`；`H10-detail` → `H10`
    return frozenset(re.match(r"(H\d+)", c).group(1) for c in codes if re.match(r"(H\d+)", c))


def split_real_importers(symbol: str) -> tuple[list[str], list[str]]:
    """把某符号的引用方分成「真 import / 调用」与「只在注释里提到」两类。

    返回 `(real, comment_only)`，两者都已排序，且都**排除**该符号的定义文件与测试文件。

    🔴 **必须逐行匹配**。第一版写成跨整个文件的
    ``import\\s+\\{[^}]*\\bSYM\\b[^}]*\\}\\s+from``，而 ``[^}]`` 是否定字符类、**跨换行** ⇒
    任何「文件开头有 ``import {``、中间某条注释提到 SYM、后面有 ``} from``」的文件都会被
    误判成 importer。实测该写法把 `useH6DualMode.ts` / `useH8DualMode.ts` /
    `GtH4EngineeringMaterials.vue` 三个**只在注释里提到**的文件全判成 import，
    同时把两个真 importer（H4 的减值 Tab）判掉了。

    ⇒ 逐行：非注释行里同时出现 `import` 与 `from`，或出现 `SYM(` 调用，才算真引用。
    """
    call_re = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    real: list[str] = []
    comment_only: list[str] = []
    for f in frontend_files():
        if f.is_test or f.rel.endswith(f"composables/{symbol}.ts"):
            continue
        if symbol not in f.text:
            continue
        hit = False
        for line in f.text.splitlines():
            if symbol not in line:
                continue
            stripped = line.lstrip()
            if stripped.startswith(("//", "*", "/*")):
                continue  # 注释行不算
            if ("import" in line and "from" in line) or call_re.search(line):
                hit = True
                break
        (real if hit else comment_only).append(f.rel)
    return sorted(real), sorted(comment_only)


def publish_to_tb_sites() -> dict[str, tuple[str, ...]]:
    """现算 `publishToTb` 在 H2~H10 生产代码里的分布（HD-7 两族缺口的判据）。

    返回 `{entry_code: (rel:count, ...)}`。🔴 H8 / H9 必须是**空元组**（完全无发布门）。
    """
    out: dict[str, list[str]] = {code: [] for code in H_HOSTS}
    for f in frontend_files():
        if f.is_test:
            continue
        hits = f.count("publishToTb")
        if not hits:
            continue
        m = re.search(r"(?:^|/)(?:h(\d+)/|useH(\d+)[A-Z]|GtH(\d+)[A-Z]|h(\d+)[A-Z])", f.rel)
        if m is None:
            continue
        number = next((g for g in m.groups() if g), None)
        code = f"H{number}"
        if code in out:
            out[code].append(f"{f.rel}:{hits}")
    return {k: tuple(sorted(v)) for k, v in out.items()}


def adjustment_central_sync_sites() -> tuple[str, ...]:
    """现算 `useAdjustmentCentralSync` 在 H2~H10 的消费点（HC-2 第 3 条：第二写入方）。"""
    out: list[str] = []
    for f in workpaper_files():
        if not in_h_scope(f.rel):
            continue
        hits = f.count("useAdjustmentCentralSync")
        if hits:
            out.append(f"{f.rel}:{hits}")
    return tuple(sorted(out))


@functools.lru_cache(maxsize=1)
def available_contract_ids() -> tuple[str, ...]:
    """现算契约目录里的 contract_id 集合（GC-10：零回归基线**不写死个数**）。"""
    return tuple(sorted(p.stem for p in CONTRACTS_DIR.glob("*.json")))


# 迁移进度口径（已迁移 entry 集 / BP-8 删除账本 / 交付台账映射 / 冻结行号再定位）
# 见伴生模块 `h_migration_progress.py` —— 本模块已到行数上限，且那是「进展」不是「事实」。


__all__ = [n for n in dir() if not n.startswith("_")]
