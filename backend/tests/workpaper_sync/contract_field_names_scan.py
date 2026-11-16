# -*- coding: utf-8 -*-
"""契约受管字段名 ↔ 前端代码现算（spec oo-writeback-template-parity-closure R3.2，design §4）。

供 `test_contract_field_names_in_frontend.py` 使用（不是测试文件本身，pytest 不收集）。

═══ 口径 ═══

字段名 = 契约字段 `json_pointer` 的行内路径各段（行表取 `{row_uuid}/` 之后、静态表取末段；数字段跳过），
外加行表的行身份键（`row_identity.json_pointer` 末段）。前端语料 = `audit-platform/frontend/src` 的生产
代码（`.ts` / `.vue` / `.js`；不含 `__tests__`、`.spec.ts`、`.test.ts`、`.d.ts`），按**标识符记号**比对（不是子串，
`openingAje` 不会被 `openingAjeTotal` 冒充）。

* ① 前端全无：字段名在整个前端生产代码里都不出现；
* ② 本 item 不用：字段名前端有，但不在「处理该 store item 的代码」里。该范围 = 含该 store item 字面量的文件、
  它们直接 import 的文件与直接 import 它们的文件，加上对拍适配器（`templateFormulaParity.adapters.ts`）给该 item
  调用的前端模块，加上 `EXTRA_SCOPE` 手工登记的入口（store item 键动态拼接、字面量找不到的）。
* 非标识符的字段名（逐格存储的动态键，如 `a51-audit-1.adjustment` / `D2-adj-aging-prior-aje`）按其中的标识符
  片段逐个判（片段全在 ⇒ 视为在）；`store_item_id` 为空的表（审定表一类逐格键）只判 ①。

🔴 **「词干 × 后缀」拼键（L4-3 教训，spec oo-writeback-template-parity-closure R3.2 批 D）**：前端把成对列存成
`${stem}Qty` / `${stem}Amount`，**整个键名在源码里从不逐字出现**（词干在 `const PAIR_STEMS = ['priorAje', …]`，
后缀在 `for (const unit of ['Qty','Amount'])`，键在 `` `${stem}${unit}` `` / `row[g.stem + unit.suffix]` 里拼出来）。
逐字比对因此把它们全判成「前端全无」——`l4.bonds_payable|L4-3-rows` 的 27 条全是这种假阴（契约 json 键与前端
运行时键**逐字相同**，端到端往返 38/38 实证）。口径 = **按源码里真有的拼法**合成键（词干集合 × 后缀集合），
不是「凡以 Qty/Amount 结尾就算」。三个来源缺一不可：纯标识符字符串数组、for-of 循环变量绑定、后缀字面量。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CONTRACTS_DIR = BACKEND / "data" / "workpaper_sync_contracts"
FRONTEND_SRC = REPO / "audit-platform" / "frontend" / "src"
ADAPTERS_TS = FRONTEND_SRC / "components" / "workpaper" / "sync" / "__tests__" / "templateFormulaParity.adapters.ts"

_TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_IMPORT = re.compile(r"""(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]""")

#: store item 键在前端是动态拼出来的（字面量找不到）或字段定义在不 import 键所在文件的 schema 里
#: ⇒ 手工登记处理它的入口文件（相对 frontend/src）。
_D4_IPO_SCHEMA = ("components/workpaper/d4/ipo/ipoChecklistSchema.ts",)
EXTRA_SCOPE: dict[str, tuple[str, ...]] = {
    # D4 IPO 检查表四张：列定义在 schema（`sheetCode` + 列 key），store 键由 useD4Ipo 按 sheetCode 拼出
    "D4-25-rows": _D4_IPO_SCHEMA,
    "D4-26-rows": _D4_IPO_SCHEMA,
    "D4-27-rows": _D4_IPO_SCHEMA,
    "D4-28-rows": _D4_IPO_SCHEMA,
}

#: 契约里 store item 写成占位串（M 循环）
PLACEHOLDER_ITEM = "placeholder"


@dataclass
class Corpus:
    texts: dict[str, str]
    tokens: dict[str, frozenset[str]]
    imports: dict[str, set[str]]
    importers: dict[str, set[str]]
    all_tokens: frozenset[str]
    adapter_roots: dict[str, set[str]] = field(default_factory=dict)
    #: 文件里由常量拼出的键（`const ITEM_PREFIX = 'K3-3-adj'` + `` `${ITEM_PREFIX}-entries` `` ⇒ `K3-3-adj-entries`）
    derived_keys: dict[str, frozenset[str]] = field(default_factory=dict)
    #: 文件里「词干 × 后缀」可能拼出的键（`${stem}Qty` / `${stem}${unit}` / `row[g.stem + unit.suffix]`）
    composed_keys: dict[str, frozenset[str]] = field(default_factory=dict)


_CONST_STR = re.compile(r"""\bconst\s+(\w+)\s*(?::\s*[\w<>\[\] |]+)?=\s*['"]([^'"\n]+)['"]""")
_CONST_TEMPLATE = re.compile(r"`\$\{(\w+)\}([^`$\n]*)`")


def _derived_keys(text: str) -> frozenset[str]:
    consts = dict(_CONST_STR.findall(text))
    return frozenset(consts[name] + rest for name, rest in _CONST_TEMPLATE.findall(text) if name in consts)


def _is_prod(rel: str, parts: tuple[str, ...]) -> bool:
    return "__tests__" not in parts and not rel.endswith((".spec.ts", ".test.ts", ".d.ts"))


def _resolve(src_rel: str, spec: str, known: dict[str, str] | set[str]) -> str | None:
    if spec.startswith("@/"):
        base = spec[2:]
    elif spec.startswith("."):
        parts: list[str] = []
        for seg in (Path(src_rel).parent / spec).as_posix().split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg not in (".", ""):
                parts.append(seg)
        base = "/".join(parts)
    else:
        return None
    for cand in (base, f"{base}.ts", f"{base}.vue", f"{base}.js", f"{base}/index.ts"):
        if cand in known:
            return cand
    return None


def _adapter_roots(prod: set[str]) -> dict[str, set[str]]:
    """对拍适配器：`'ITEM': { … alias.fn(…) … }` ⇒ ITEM → alias 指向的前端模块。"""
    if not ADAPTERS_TS.is_file():
        return {}
    text = ADAPTERS_TS.read_text(encoding="utf-8")
    rel_self = ADAPTERS_TS.relative_to(FRONTEND_SRC).as_posix()
    alias: dict[str, str] = {}
    for m in re.finditer(r"""import \* as (\w+) from ['"]([^'"]+)['"]""", text):
        tgt = _resolve(rel_self, m.group(2), prod)
        if tgt:
            alias[m.group(1)] = tgt
    for m in re.finditer(r"""import \{([^}]*)\} from ['"]([^'"]+)['"]""", text):
        tgt = _resolve(rel_self, m.group(2), prod)
        if tgt:
            for name in re.findall(r"\w+", m.group(1)):
                alias[name] = tgt
    roots: dict[str, set[str]] = {}
    start = text.find("PARITY_ADAPTERS")
    entries = list(re.finditer(r"^  '([^']+)': \{", text[start:], flags=re.M)) if start >= 0 else []
    for i, m in enumerate(entries):
        end = entries[i + 1].start() if i + 1 < len(entries) else len(text) - start
        body = text[start + m.end(): start + end]
        roots[m.group(1)] = {alias[a] for a in re.findall(r"\b(\w+)\b", body) if a in alias}
    return roots


_IDENT_ONLY = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def _close_index(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """`text[start-1]` 是 `open_ch`，返回与之配对的 `close_ch` 下标（括号配平，禁 `split`）。"""
    depth, i = 1, start
    while i < len(text) and depth:
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
        i += 1
    return i - 1


def _string_arrays(text: str) -> dict[str, list[str]]:
    """`const NAME = ['a', 'b'] as const` ⇒ NAME → 元素。

    只收**纯标识符字符串数组**（有对象字面量 / 模板串的一律不收）：`SCALAR_COLUMNS` 那种一行一条记录的
    数组若被当成词干池，`{ key: 'instrumentName' }` 的 `key` 会与 `Qty` 拼成 `keyQty` 这种不存在的键。
    """
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"\bconst\s+(\w+)[^=\n]*=\s*\[", text):
        body = text[m.end(): _close_index(text, m.end(), "[", "]")]
        if "{" in body or "`" in body or "(" in body:
            continue
        elems = [e for e in re.findall(r"'([^']*)'", body) if _IDENT_ONLY.fullmatch(e)]
        if elems:
            out[m.group(1)] = elems
    return out


def _loop_bindings(text: str, arrays: dict[str, list[str]]) -> dict[str, list[str]]:
    """`for (const stem of L4_3_PAIR_STEMS)` / `of ['Qty','Amount']` ⇒ 循环变量 → 元素。"""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"for\s*\(\s*const\s+(\w+)\s+of\s+(.+?)\)\s*\{", text):
        src = m.group(2).strip()
        if src.startswith("["):
            start = text.index("[", m.start(2))
            body = text[start + 1: _close_index(text, start + 1, "[", "]")]
            elems = [e for e in re.findall(r"'([^']*)'", body) if _IDENT_ONLY.fullmatch(e)]
        else:
            elems = arrays.get(src) or []
        if elems:
            out[m.group(1)] = elems
    return out


def _suffix_literals(text: str) -> set[str]:
    """后缀字面量：`suffix: 'Qty'` 对象字段 + `for (const u of ['Qty','Amount'])` 的取值。"""
    out = {s for s in re.findall(r"suffix\s*:\s*'(\w+)'", text) if _IDENT_ONLY.fullmatch(s)}
    for m in re.finditer(r"for\s*\(\s*const\s+\w+\s+of\s*\[", text):
        start = text.index("[", m.end() - 1)
        body = text[start + 1: _close_index(text, start + 1, "[", "]")]
        out |= {e for e in re.findall(r"'([^']*)'", body) if _IDENT_ONLY.fullmatch(e)}
    return out


def composed_keys(text: str) -> frozenset[str]:
    """该文件里**真有的拼法**可能产出的键名（词干 × 后缀）。

    三种写法，逐条对应真实源码形态（L4-3 实测）：

    ① `` `${stem}Qty` `` —— 变量 + 字面尾（词干取自 for-of 绑定的数组）
    ② `` `${stem}${unit}` `` —— 两个变量（词干 × 后缀集合）
    ③ `row[g.stem + unit.suffix]` —— 属性拼（词干池来自 `Object.keys(LABELS)` 与纯字符串数组）

    🔴 只认这三种：不做「凡后缀是 Qty/Amount 就合成」的泛化 —— 那会把前端根本没有的键也算进来，把缺陷判成接通。
    """
    arrays = _string_arrays(text)
    bind = _loop_bindings(text, arrays)
    suffixes = _suffix_literals(text)
    keys: set[str] = set()
    # ① `${stem}Qty` —— 尾是字面量
    for m in re.finditer(r"`\$\{(\w+)\}([A-Za-z]\w*)`", text):
        for stem in bind.get(m.group(1), ()):
            keys.add(stem + m.group(2))
    # ② `${stem}${unit}`
    for m in re.finditer(r"`\$\{(\w+)\}\$\{(\w+)\}`", text):
        right = bind.get(m.group(2)) or tuple(suffixes)
        for stem in bind.get(m.group(1), ()):
            for tail in right:
                keys.add(stem + tail)
    # ③ `row[x.stem + y.suffix]`（含 `g.stem + unit.suffix`）
    if re.search(r"\w+\[[^\]]*\.\w+\s*\+\s*\w+\.\w+", text):
        pools: set[str] = set()
        for ob in re.findall(r"Object\.keys\(\s*(\w+)\s*\)", text):
            m = re.search(rf"\bconst\s+{ob}\b[^=\n]*=\s*\{{", text)
            if m:
                body = text[m.end(): _close_index(text, m.end(), "{", "}")]
                pools |= set(re.findall(r"^\s{2}'?(\w+)'?\s*:", body, re.M))
        pools |= {e for elems in arrays.values() for e in elems}
        for stem in pools:
            for tail in suffixes:
                keys.add(stem + tail)
    return frozenset(keys)


def load_corpus() -> Corpus:
    texts: dict[str, str] = {}
    for p in FRONTEND_SRC.rglob("*"):
        if p.suffix not in (".ts", ".vue", ".js") or not p.is_file():
            continue
        rel = p.relative_to(FRONTEND_SRC).as_posix()
        if _is_prod(rel, p.parts):
            texts[rel] = p.read_text(encoding="utf-8", errors="replace")
    tokens = {rel: frozenset(_TOKEN.findall(t)) for rel, t in texts.items()}
    imports: dict[str, set[str]] = defaultdict(set)
    importers: dict[str, set[str]] = defaultdict(set)
    for rel, t in texts.items():
        for m in _IMPORT.finditer(t):
            tgt = _resolve(rel, m.group(1), texts)
            if tgt and tgt != rel:
                imports[rel].add(tgt)
                importers[tgt].add(rel)
    all_tokens = frozenset().union(*tokens.values())
    corpus = Corpus(texts, tokens, imports, importers, all_tokens)
    corpus.adapter_roots = _adapter_roots(set(texts))
    corpus.derived_keys = {rel: _derived_keys(t) for rel, t in texts.items()}
    corpus.composed_keys = {rel: composed_keys(t) for rel, t in texts.items()}
    return corpus


def name_parts(segment: str) -> tuple[str, ...]:
    """字段名 → 需要在前端出现的标识符。

    标识符原样；动态键（含 `-` / `.` 的逐格键，如 `D2-adj-aging-prior-aje`、`minority-fs-company_1_current`）
    取其中两个字母以上的纯字母片段（数字、序号与单字母列标是前端拼键时代入的变量，不要求字面出现）。
    """
    if _TOKEN.fullmatch(segment):
        return (segment,)
    return tuple(t for t in re.findall(r"[A-Za-z]+", segment) if len(t) >= 2)


def scope_composed_keys(corpus: Corpus, item: str) -> frozenset[str]:
    """处理该 item 的代码（同 `scope_files`）里能拼出的键名并集。"""
    return frozenset().union(*(corpus.composed_keys.get(f, frozenset())
                              for f in scope_files(corpus, item)))


def leaf_segments(pointer: str) -> list[str]:
    tail = pointer.split("{row_uuid}/", 1)[1] if "{row_uuid}/" in pointer else pointer.rsplit("/", 1)[-1]
    return [s for s in tail.strip("/").split("/") if s and s != "*" and not s.isdigit()]


def contract_names() -> list[tuple[str, str, str]]:
    """(contract_id, store_item_id, 字段名) —— 去重、排序。"""
    out: set[tuple[str, str, str]] = set()
    for path in sorted(CONTRACTS_DIR.glob("*.json")):
        if ".candidate." in path.name:
            continue
        c = json.loads(path.read_text(encoding="utf-8"))
        cid = c.get("contract_id") or path.stem
        for sheet in c.get("sheets", []):
            for table in sheet.get("tables", []) or []:
                fields = table.get("fields", []) or []
                first_item = next((f.get("store_item_id") for f in fields if f.get("store_item_id")), "") or ""
                rid = (table.get("row_identity") or {}).get("json_pointer")
                if rid:
                    out.add((cid, first_item, rid.rsplit("/", 1)[-1]))
                uses: dict[str, int] = defaultdict(int)
                for f in fields:
                    uses[f.get("store_item_id") or ""] += 1
                for f in fields:
                    item = f.get("store_item_id") or ""
                    if not rid and item and uses[item] == 1:
                        # 逐格存储（一格一个 store item，值在 item 本身）：json 末段是契约内部名，核 item 键本身
                        out.add((cid, item, item))
                        continue
                    for seg in leaf_segments(f.get("json_pointer", "")):
                        out.add((cid, item, seg))
            for f in sheet.get("fields", []) or []:
                for seg in leaf_segments(f.get("json_pointer", "")):
                    out.add((cid, f.get("store_item_id") or "", seg))
    return sorted(out)


def literal_files(corpus: Corpus, item: str) -> set[str]:
    """含该 store item 键的文件（引号字面量，或同文件常量拼出的模板字面量）。"""
    quoted = (f"'{item}'", f'"{item}"', f"`{item}`")
    return {rel for rel, t in corpus.texts.items()
            if any(q in t for q in quoted) or item in corpus.derived_keys.get(rel, frozenset())}


def scope_files(corpus: Corpus, item: str) -> set[str]:
    direct = literal_files(corpus, item)
    scope = set(direct)
    for rel in direct:
        scope |= corpus.importers.get(rel, set()) | corpus.imports.get(rel, set())
    scope |= corpus.adapter_roots.get(item, set())
    scope |= set(EXTRA_SCOPE.get(item, ()))
    return scope


def compute_misses(
    corpus: Corpus, names: list[tuple[str, str, str]] | None = None
) -> dict[str, set[str]]:
    """`"{contract_id}|{store_item_id}"` → 前端对不上的字段名集合（①② 合并；组键里 item 可为空串）。

    `names` 缺省取生产契约（`contract_names()`）；判据自检传构造的名单。
    """
    scope_tokens: dict[str, frozenset[str]] = {}
    scope_composed: dict[str, frozenset[str]] = {}
    misses: dict[str, set[str]] = defaultdict(set)
    for cid, item, seg in (contract_names() if names is None else names):
        parts = name_parts(seg)
        literal = all(p in corpus.all_tokens for p in parts)
        if not literal and not (item and seg != item and item != PLACEHOLDER_ITEM):
            misses[f"{cid}|{item}"].add(seg)
            continue
        # 无 store item 的表（审定表逐格键）与逐格存储（字段名就是 store item 本身）只判 ①
        if not item or seg == item:
            continue
        if item == PLACEHOLDER_ITEM:
            # 契约 store item 写成占位串 ⇒ 前端处理它的代码无从谈起，字段一律算对不上
            misses[f"{cid}|{item}"].add(seg)
            continue
        if item not in scope_tokens:
            files = scope_files(corpus, item)
            scope_tokens[item] = frozenset().union(*(corpus.tokens[f] for f in files if f in corpus.tokens))
            scope_composed[item] = scope_composed_keys(corpus, item)
        # ② 本 item 不用：逐字（标识符）在 scope 里，或该键由 scope 内真有的拼法合成出来
        if all(p in scope_tokens[item] for p in parts):
            continue
        if seg in scope_composed[item]:
            continue
        misses[f"{cid}|{item}"].add(seg)
    return dict(misses)
