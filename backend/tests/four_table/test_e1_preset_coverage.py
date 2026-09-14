"""E 类公式预设覆盖面守卫（Wave 1 Task 2，先打红）。

判据 Property 11 / 12 / 13 / 14，全部为**纯文件判据**（openpyxl 直读源 xlsx +
读 prefill_formula_mapping.json + AST 扫幂等脚本源码），不连库。

## 断言分两类（与 test_e1_bank_accounts_live.py 同范式）

- **类 A = 独立口径判据**：由本文件自己算出事实（sheet 全集 / 基线计数 / 判据自检）。
  这些**现在就应该全绿** —— 绿了才证明判据基础设施有效而非空转。
- **类 B = 被测状态**：预设 sheet 名是否真实存在、覆盖面是否完备、幂等脚本输出是否
  GBK 安全。这些**现在应该全红**，红消息里写明「Wave 4 Task 10 / 11」。

## 与 design.md Property 14 字面判据的偏离（有意，附实证）

design 写「不得含 emoji 与数学符号（U+2000 以上的非 CJK 字符）」。实测（探针
`_wip_ascii_probe.py`）表明按该字面实现会产生**假红**：

    GBK-OK   : 'U+2192' 'U+FF08' 'U+FF1A' 'U+3001' 'U+2460' 'U+2264' 'U+2026' 'U+2014'
    GBK-FAIL : 'U+2705' 'U+274C' 'U+26A0' 'U+1F534' 'U+21D2' 'U+2286' 'U+2212'

左列码位全部 >= U+2000 且非 CJK 汉字，却在 GBK 控制台完全可打印，并且被
`fix_e1_prefill_presets.py` / `fix_note_e1_monetary_fund_structure.py` 大量使用。

真实崩溃条件就是「该字符能否用 GBK 编码」（`UnicodeEncodeError`），故本守卫以
`str.encode('gbk')` 为主判据。这是对 design 字面的**收紧到真实失效模式**，方向与
Requirement 4 的 User Story（退出码要反映真实欠账）一致。
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

# ---------------------------------------------------------------- 路径与基线

_HERE = Path(__file__).resolve()
# backend/tests/four_table/x.py -> parents[2] == backend/
BACKEND_ROOT = _HERE.parents[2]
E_TEMPLATE_DIR = BACKEND_ROOT / "wp_templates" / "E"
PRESET_JSON = BACKEND_ROOT / "data" / "prefill_formula_mapping.json"
FIX_DIR = BACKEND_ROOT / "scripts" / "fix"

# 非底稿内容的 sheet（目录页与自定义占位），不纳入预设覆盖面
NON_CONTENT_SHEETS = frozenset({"底稿目录", "GT_Custom"})

# 基线：数值来自 2026-08-08 实测复算（openpyxl 直读 5 个源 xlsx），
# 只许因源模板真实变更而变，变更时须重新实测并在此留证。
#
# 🔴 `VISIBLE_SHEET_BASELINE = 40` 是**排除 5 张「底稿目录」后**的口径
#（`NON_CONTENT_SHEETS` 先剔除）；源模板 visible sheet 原始总数是 **45**。
# 两个数字都对，别把 45 直接填进来。
VISIBLE_SHEET_BASELINE = 40
# Task 10（2026-08-08）落地后：17 → 23（+6 新增块 —— (仅人民币)E1-3 / E1-6 /
# E1-10 / E1-21 / E1-22 / E1-23；E0 块只改 sheet 名与 wp_name，不增块）。
E_PRESET_BLOCK_BASELINE = 23

# Wave 4 Task 10 已全部落地 ⇒ 本集合清空。
#
# 🔴 保留空集合而不是删掉常量：`test_pending_preset_sheets_are_real_and_shrinking`
# 用它做「清单只许缩短」的双向锁死（stale 检测 + 已落地必须移出），空集合下这条
# 断言仍在跑 —— 一旦有人往回加条目就会被 stale/landed 判据抓住。
PENDING_PRESET_SHEETS: frozenset[str] = frozenset()

# 登记表真源在幂等脚本里（Task 10 建），本守卫只读取并交叉锁死。
REGISTRY_SCRIPT = FIX_DIR / "fix_e1_prefill_presets.py"
REGISTRY_ATTR = "E1_SHEETS_WITHOUT_PRESET"
# 非数据表白名单真源（同一脚本）—— 底稿目录 / 实质性程序表 / 函证程序表，
# 结构上没有取数格，不该进登记表也不该有预设块。
NON_DATA_ATTR = "NON_DATA_SHEETS"
# Task 10 落地后条目数 = 14（R3.3：E1 7 张 + E0 7 张）。
# 落地前是 18 = 14 + 3 程序表 + 1 (仅人民币)E1-3 variant —— 前 3 张已移入白名单、
# 后 1 张已补预设，故 CAP 由 18 下调到 14。
REGISTRY_CAP = 14
# 🔴 单独一条上限哨兵：只许下调。裸写 len(registry) <= REGISTRY_CAP 拦不住
# 「对不齐就把 CAP 改大」这个动作（memory 已记同族教训）。
_REGISTRY_CAP_CEILING = 14
REGISTRY_MIN_REASON_LEN = 15

# 只扫 E 类幂等脚本（Requirement 4.3 的扫描面）
FIX_SCRIPT_GLOBS = ("fix_e1_*.py", "fix_note_e1_*.py")


# ---------------------------------------------------------------- 判据实现


def gbk_unsafe_chars(text: str) -> list[str]:
    """返回 text 中无法用 GBK 编码的字符（去重后按码位排序）。

    这是「GBK 控制台 print 会不会抛 UnicodeEncodeError」的精确判据。
    """
    bad: set[str] = set()
    for ch in text:
        try:
            ch.encode("gbk")
        except UnicodeEncodeError:
            bad.add(ch)
    return sorted(bad, key=ord)


def describe_chars(chars: list[str]) -> str:
    """把字符列表渲染成只含 ASCII 的描述，避免断言消息本身触发编码问题。

    🔴 断言消息里若夹一个 GBK 不可编码字符，pytest 会把**整段**消息转义成
    \\uXXXX（memory 已记），判读失败原因会变得极其困难。故这里只输出码位。
    """
    return ", ".join(f"U+{ord(c):04X}" for c in chars)


def print_string_literals(src: str) -> list[tuple[int, str]]:
    """AST 提取 print(...) 调用里的全部字符串字面量（含 f-string 的字面片段）。

    有意不扫注释与 docstring —— 那里的字符不会进 stdout。实测两个脚本的注释里
    确有 GBK 不可编码字符而 --check rc == 0，按整文件扫会误红。
    """
    out: list[tuple[int, str]] = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        is_print = (isinstance(fn, ast.Name) and fn.id == "print") or (
            isinstance(fn, ast.Attribute) and fn.attr in {"write", "print"}
        )
        if not is_print:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append((getattr(sub, "lineno", node.lineno), sub.value))
    return out


@dataclass(frozen=True)
class SheetRef:
    name: str
    workbook: str


def _load_visible_sheets() -> list[SheetRef]:
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover
        pytest.skip("openpyxl 不可用，无法直读源模板")
    if not E_TEMPLATE_DIR.is_dir():
        pytest.fail(f"E 类源模板目录不存在: {E_TEMPLATE_DIR}")
    refs: list[SheetRef] = []
    for xlsx in sorted(E_TEMPLATE_DIR.glob("*.xlsx")):
        if xlsx.name.startswith("~$"):  # WPS/Excel 锁文件
            continue
        wb = load_workbook(xlsx, read_only=True, data_only=True)
        try:
            for ws in wb.worksheets:
                if ws.sheet_state != "visible":
                    continue
                if ws.title in NON_CONTENT_SHEETS:
                    continue
                refs.append(SheetRef(ws.title, xlsx.name))
        finally:
            wb.close()
    return refs


def _load_e_preset_blocks() -> list[dict]:
    data = json.loads(PRESET_JSON.read_text(encoding="utf-8"))
    mappings = data["mappings"] if isinstance(data, dict) else data
    return [
        b
        for b in mappings
        if isinstance(b, dict) and str(b.get("wp_code", "")).startswith("E")
    ]


def _assign_targets(node: ast.stmt) -> list[str]:
    """取一条赋值语句的目标名。

    🔴 必须同时认 `ast.Assign` 与 **`ast.AnnAssign`**（带类型注解的赋值，
    如 `X: dict[str, str] = {...}`）—— 只认前者时，带注解的常量会被静默跳过，
    加载器返回 None ⇒ 依赖它的判据全部 `skip` 而不是红（本守卫落地时实测踩中：
    17 张 sheet 被报成「待登记」而真因是登记表根本没被读到）。
    """
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _load_registry() -> dict[str, str] | None:
    """读取登记表；Task 10 未建时返回 None（此时 Property 12 全量打红）。"""
    if not REGISTRY_SCRIPT.exists():
        return None
    src = REGISTRY_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if node.value is None:
            continue
        if REGISTRY_ATTR not in _assign_targets(node):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            pytest.fail(
                f"{REGISTRY_ATTR} 必须是字面量 dict[str, str]（sheet 名 -> 理由），"
                "以便守卫静态读取而无需 import 生产模块"
            )
        if not isinstance(value, dict):
            pytest.fail(f"{REGISTRY_ATTR} 必须是 dict[str, str]，实为 {type(value)}")
        return {str(k): str(v) for k, v in value.items()}
    return None


def _load_non_data_sheets() -> frozenset[str] | None:
    """读取非数据表白名单；未建时返回 None（此时程序表会被算进「待登记」）。

    与 `_load_registry` 同款：静态 AST 读字面量，不 import 生产模块。
    """
    if not REGISTRY_SCRIPT.exists():
        return None
    tree = ast.parse(REGISTRY_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if node.value is None:
            continue
        if NON_DATA_ATTR not in _assign_targets(node):
            continue
        # `frozenset({...})` / `{...}` 两种写法都认
        val = node.value
        if isinstance(val, ast.Call) and getattr(val.func, "id", "") == "frozenset":
            if not val.args:
                return frozenset()
            val = val.args[0]
        try:
            items = ast.literal_eval(val)
        except (ValueError, SyntaxError):
            pytest.fail(
                f"{NON_DATA_ATTR} 必须是字面量 set/frozenset[str]，"
                "以便守卫静态读取而无需 import 生产模块"
            )
        return frozenset(str(x) for x in items)
    return None


# 模块级缓存：openpyxl 读 5 个 workbook（E0 约 1 MB）只做一次
_VISIBLE = _load_visible_sheets()
_BLOCKS = _load_e_preset_blocks()
_REGISTRY = _load_registry()
_NON_DATA = _load_non_data_sheets()
_VISIBLE_NAMES = {r.name for r in _VISIBLE}
_PRESET_SHEETS = {str(b.get("sheet", "")) for b in _BLOCKS}
#: 白名单在**本守卫口径**（已剔除底稿目录）下实际命中的 sheet
_NON_DATA_HIT = frozenset(_NON_DATA or ()) & _VISIBLE_NAMES


# =============================================================== 类 A：应绿


class TestJudgementInfrastructure:
    """类 A：独立口径与判据自检 —— 现在就应该全绿。"""

    def test_source_templates_readable_and_sheet_count_frozen(self):
        assert _VISIBLE, "E 类源模板未读到任何 visible sheet，扫描面为空则后续判据全部空转"
        assert len(_VISIBLE) == VISIBLE_SHEET_BASELINE, (
            f"E 类 visible sheet 数由 {VISIBLE_SHEET_BASELINE} 变为 {len(_VISIBLE)}。"
            "若源模板确有增删，请重新实测后更新 VISIBLE_SHEET_BASELINE 并留证。"
            f"\n当前清单: {sorted(_VISIBLE_NAMES)}"
        )

    def test_e_preset_block_count_frozen(self):
        assert len(_BLOCKS) == E_PRESET_BLOCK_BASELINE, (
            f"E 类预设块数由 {E_PRESET_BLOCK_BASELINE} 变为 {len(_BLOCKS)}。"
            "Wave 4 Task 10 会把它增加到 23（+5 新增，E0 块只改 sheet 名不增块），"
            "届时请同步更新本基线。"
        )

    def test_preset_sheet_values_are_unique(self):
        """两个块写同一 sheet 会让 page_key+cell_ref 互相遮蔽（平台已知坑）。"""
        seen: dict[str, list[str]] = {}
        for b in _BLOCKS:
            seen.setdefault(str(b.get("sheet", "")), []).append(str(b.get("wp_code")))
        dup = {k: v for k, v in seen.items() if len(v) > 1}
        assert not dup, f"同一 sheet 出现多个预设块，后写者会遮蔽先写者: {dup}"

    def test_gbk_criterion_allows_chinese_and_fullwidth_punctuation(self):
        """正向自检：中文汉字与全角标点、常见箭头/序号必须**不**被打红。

        否则判据会把两个本来正常的脚本全部误红。
        """
        safe = "已完成欠账项目（含）：、，。「」【】※①②③±×÷≤≥…—→←↑↓"
        bad = gbk_unsafe_chars(safe)
        assert not bad, (
            "判据把 GBK 可编码字符误判为不安全，会产生假红: " + describe_chars(bad)
        )

    def test_gbk_criterion_flags_real_offenders(self):
        """反向自检：真正会崩的字符必须被判据抓到。"""
        for ch in ["\u2705", "\u274c", "\u26a0", "\U0001f534", "\u21d2", "\u2212"]:
            assert gbk_unsafe_chars(ch) == [ch], (
                f"判据漏掉了会崩的字符 U+{ord(ch):04X}"
            )

    def test_print_scanner_ignores_comments_and_docstrings(self):
        """反向自检：只扫 print 字面参数，不扫注释与 docstring。

        实测 fix_e1_prefill_presets.py 与 fix_note_e1_monetary_fund_structure.py
        的注释里确有 U+2212 / U+1F534，而它们 --check rc == 0（不会崩）。
        """
        fixture = (
            '"""docstring \u2705 里的对勾不会进 stdout。"""\n'
            "# 注释里的 \u274c 同理\n"
            'MSG = "字符串常量 \u26a0 不在 print 里也不会崩"\n'
            'print("干净的输出（含中文）")\n'
        )
        lits = print_string_literals(fixture)
        assert [t for _, t in lits] == ["干净的输出（含中文）"], (
            f"扫描器把注释/docstring/无关常量数进来了: {lits}"
        )
        assert not [c for _, t in lits for c in gbk_unsafe_chars(t)]

        offender = fixture + 'print(f"结果 \u2705 {1}")\n'
        lits2 = print_string_literals(offender)
        bad2 = sorted({c for _, t in lits2 for c in gbk_unsafe_chars(t)})
        assert bad2 == ["\u2705"], (
            "扫描器未能从 f-string 的字面片段里抓到不安全字符（f-string 是本仓库"
            f"最常见的 print 形态）: {bad2}"
        )

    def test_fix_script_scan_surface_is_not_empty(self):
        """扫描面自检：找不到脚本时 Property 14 会静默通过。"""
        files = _fix_scripts()
        assert len(files) >= 3, (
            f"E 类幂等脚本扫描面过小（{[p.name for p in files]}），"
            "判据可能因路径变更而空转"
        )

    def test_intra_wp_preset_reference_graph_is_acyclic(self):
        """Property 13：同 wp_code 内的 `WP()` 引用图必须无环。

        🔴 **判据是「无环」而不是「非审定表不得引用审定表」**（2026-08-08 实测修正）。

        原判据把 sheet 二分成「审定表 / 其它」，其它一律不许引用审定表 —— 它把
        **披露表**误判成 offender。E 类实测引用边：

            审定表E1-1          -> WP(现金明细表E1-2) / WP(银行明细表E1-3) / WP(数字货币E1-4)
            附注披露信息(上市)  -> WP(货币资金审定表E1-1)      <== 被原判据打红
            附注披露信息(国企)  -> WP(现金明细表E1-2) / WP(银行明细表E1-3)

        链条是 `披露表 -> 审定表 -> 明细表`，**没有环**。披露表是取数链的叶子消费方
        （全库无任何块引用披露 sheet），它从审定表取数正是源 xlsx 的口径
        （上市 ``B8='货币资金审定表E1-1'!G7``）。禁掉它等于禁掉披露表的正确实现。

        真正要防的是「A 引 B 且 B 引 A」这类**真环**（求值时互相等待）。故改为
        建有向图跑 DFS 找环，既覆盖原判据要防的形态（审定表<->明细表互引），
        也不误伤合法的三层链。

        跨 wp_code 引用不入图 —— 那是平台既有合法范式（如 D0 引 D2 算函证覆盖率）。
        """
        # 建图：节点 id = `{wp_code}/{sheet}`（只收同 wp_code 的边，故用它作
        # 节点即可，且断言消息里可直接读）。
        # 🔴 节点与边目标必须是**同一种类型**，否则 `edges.get(目标)` 永不命中 ⇒
        # 图恒"无环"，连反向自检也抓不到真环（本轮踩过一次）。
        graph: dict[str, set[str]] = {}
        edge_src: dict[tuple[str, str], str] = {}
        for b in _BLOCKS:
            wp = str(b.get("wp_code", ""))
            sheet = str(b.get("sheet", ""))
            node = _node_id(wp, sheet)
            graph.setdefault(node, set())
            for cell in b.get("cells", []) or []:
                formula = str(cell.get("formula", ""))
                for target in _wp_targets(formula, wp):
                    if target == sheet:
                        continue  # 自引用（PREV 取本表上年数）不是环
                    dst = _node_id(wp, target)
                    graph[node].add(dst)
                    edge_src[(node, dst)] = f"{cell.get('cell_ref')}: {formula}"

        cycles = _find_cycles(graph)
        assert not cycles, (
            "同 wp_code 内的预设 `WP()` 引用图存在环，求值会互相等待:\n"
            + "\n".join(
                "  环: "
                + " -> ".join(path)
                + "".join(
                    f"\n      边 {a} -> {b}: {edge_src.get((a, b), '(未记录)')}"
                    for a, b in zip(path, path[1:])
                )
                for path in cycles
            )
        )

    def test_acyclic_criterion_catches_a_real_cycle(self):
        """反向自检：真环必须被抓到，且合法三层链必须放过。

        没有这条，上面那条在「图恒无环」时与「判据写坏了」不可区分 —— 本轮正是
        它先红，才暴露出节点类型不一致导致图恒无环的实现缺陷。
        """
        adj = _node_id("E1", "货币资金审定表E1-1")
        cash = _node_id("E1", "现金明细表E1-2")
        disc = _node_id("E1", "附注披露信息(上市公司)")

        legal = {disc: {adj}, adj: {cash}, cash: set()}
        assert not _find_cycles(legal), (
            "判据把合法的三层链（披露表 -> 审定表 -> 明细表）误判成环"
        )

        cyclic = {adj: {cash}, cash: {adj}}
        found = _find_cycles(cyclic)
        assert found, "判据漏掉了审定表<->明细表互引这个真环"

        self_loop = {adj: {adj}}
        assert _find_cycles(self_loop), "判据漏掉了自环"

    def test_wp_target_extractor_scopes_to_same_wp(self):
        """反向自检：抽取器只收同 wp_code 的目标，跨循环引用不入图。

        跨循环引用（`D0` 引 `WP('D2', ...)` 算函证覆盖率分母）是平台既有合法范式，
        误收会让不同循环的块在图里连起来、产生假环。
        """
        formula = "WP('E1','现金明细表E1-2','期末合计')+WP('D2','审定表D2-1','x')"
        assert _wp_targets(formula, "E1") == {"现金明细表E1-2"}
        assert _wp_targets(formula, "D2") == {"审定表D2-1"}
        assert _wp_targets("TB('1002','期末余额')", "E1") == set()

    def test_static_loaders_actually_read_both_constants(self):
        """🔴 加载器有效性自检 —— 两个常量必须真的被静态读到（不是返回 None）。

        `_load_registry` / `_load_non_data_sheets` 返回 None 时，依赖它们的判据全部
        `skip`（不是红）⇒ 覆盖面判据会把已登记的 sheet 报成「待登记」，看起来像
        「登记表少了十几条」而真因是**加载器失效**。本条把这种假阴性钉死。

        实测踩过一次：脚本里常量写成 `X: dict[str, str] = {...}`（`ast.AnnAssign`），
        而加载器只认 `ast.Assign` ⇒ 静默跳过。
        """
        assert REGISTRY_SCRIPT.exists(), f"{REGISTRY_SCRIPT.name} 不存在"
        assert _REGISTRY is not None, (
            f"{REGISTRY_ATTR} 静态读取失败（返回 None）。常见成因："
            "①常量带类型注解（AnnAssign）而加载器只认 Assign；"
            "②常量不在模块顶层；③值不是字面量 dict。"
            "此时下游判据会 skip 而非红 = 假阴性。"
        )
        assert _NON_DATA is not None, (
            f"{NON_DATA_ATTR} 静态读取失败（返回 None），同上"
        )
        # 反向自检：AnnAssign 形态确实能被解析（否则本条断言只是碰巧通过）
        probe = ast.parse("A: dict[str, str] = {'k': 'v'}\nB = {'x'}\n")
        assert _assign_targets(probe.body[0]) == ["A"], "AnnAssign 目标名解析失效"
        assert _assign_targets(probe.body[1]) == ["B"], "Assign 目标名解析失效"

    def test_registry_cap_only_shrinks(self):
        assert REGISTRY_CAP <= _REGISTRY_CAP_CEILING, (
            f"登记表上限被上调（{REGISTRY_CAP} > {_REGISTRY_CAP_CEILING}）。"
            "上限只许下调 —— 上调等于把登记表当逃逸阀，对不齐就往里加一条。"
        )

    def test_registry_is_consistent_when_present(self):
        """登记表建成后：无 stale 条目、理由够长、与预设集合无交集、不超上限。"""
        if _REGISTRY is None:
            pytest.skip(
                f"{REGISTRY_ATTR} 尚未建立（Wave 4 Task 10）。"
                "此时 Property 12 会对全部未覆盖 sheet 打红，是预期行为。"
            )
        stale = sorted(set(_REGISTRY) - _VISIBLE_NAMES)
        assert not stale, (
            f"{REGISTRY_ATTR} 含源模板里不存在的 sheet（stale 条目）: {stale}"
        )
        overlap = sorted(set(_REGISTRY) & _PRESET_SHEETS)
        assert not overlap, (
            f"{REGISTRY_ATTR} 与已有预设的 sheet 重叠，两个集合必须互斥: {overlap}"
        )
        short = {
            k: v for k, v in _REGISTRY.items() if len(v.strip()) < REGISTRY_MIN_REASON_LEN
        }
        assert not short, (
            f"登记理由不足 {REGISTRY_MIN_REASON_LEN} 字（占位式理由等于没登记）: "
            f"{sorted(short)}"
        )
        assert len(_REGISTRY) <= REGISTRY_CAP, (
            f"{REGISTRY_ATTR} 条目数 {len(_REGISTRY)} 超过上限 {REGISTRY_CAP}"
        )


def _node_id(wp_code: str, sheet: str) -> str:
    """引用图的节点 id。只收同 wp_code 的边，故 `wp/sheet` 足以唯一标识。"""
    return f"{wp_code}/{sheet}"


def _wp_targets(formula: str, wp_code: str) -> set[str]:
    """从公式里抽出**同 wp_code** 的 ``WP()`` 目标 sheet 名。

    形态 ``WP('E1','货币资金审定表E1-1','期末合计')``。

    只收同 wp_code —— 跨循环引用（`D0` 引 `WP('D2', ...)` 作函证覆盖率分母）是
    平台既有合法范式，误收会把不同循环的块在图里连起来、产生假环。
    """
    out: set[str] = set()
    for m in re.finditer(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'", formula):
        if m.group(1) == wp_code:
            out.add(m.group(2))
    return out


def _find_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """DFS 找出全部有向环（含自环），返回环上的节点序列（首尾同一节点）。

    纯函数，节点类型 = 边目标类型 = ``str``（两者不一致会让图恒"无环"）。
    """
    cycles: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    def walk(stack: list[str], on_stack: set[str]) -> None:
        for nxt in sorted(edges.get(stack[-1], ())):
            if nxt in on_stack:
                loop = stack[stack.index(nxt) :] + [nxt]
                sig = tuple(sorted(set(loop)))
                if sig not in seen:
                    seen.add(sig)
                    cycles.append(loop)
                continue
            walk(stack + [nxt], on_stack | {nxt})

    for start in sorted(edges):
        walk([start], {start})
    return cycles


def _fix_scripts() -> list[Path]:
    files: list[Path] = []
    for pattern in FIX_SCRIPT_GLOBS:
        files.extend(sorted(FIX_DIR.glob(pattern)))
    return sorted(set(files))


# =============================================================== 类 B：应红


class TestPresetSheetNamesAreReal:
    """Property 11：预设块的 sheet 值必须是源 xlsx 真实 tab 名。"""

    def test_every_preset_sheet_exists_in_source_templates(self):
        ghosts = sorted(_PRESET_SHEETS - _VISIBLE_NAMES)
        assert not ghosts, (
            "以下预设块的 sheet 在 E 类源模板里不存在（贴错标签，公式管理页那条链恒空）:\n"
            + "\n".join(
                f"  {g!r} <- wp_code="
                + ",".join(
                    str(b.get("wp_code")) for b in _BLOCKS if b.get("sheet") == g
                )
                for g in ghosts
            )
            + "\n真实 tab 名请以 openpyxl 直读为准。"
            "\n【Wave 4 Task 10 待修】'审定表E0-1' 的真实 tab 名是 '函证结果汇总表E0-1'，"
            "且 wp_name 应由 '银行询证函' 改为 '函证结果汇总表'（R3.1）。"
        )

    def test_ghost_sheet_is_not_recoverable_by_normalization(self):
        """辅助定性：贴错的 tab 名不是括号宽度之类的归一化问题，是整名不同。

        类 A 性质（独立口径），据此排除「只要归一化就能命中」的误判。
        """

        def norm(s: str) -> str:
            table = str.maketrans("（）()：:", "(())::")
            return s.translate(table).replace(" ", "").replace("\u3000", "")

        ghosts = sorted(_PRESET_SHEETS - _VISIBLE_NAMES)
        if not ghosts:
            pytest.skip("已无贴错标签的 sheet（Task 10 已收口）")
        norm_visible = {norm(n) for n in _VISIBLE_NAMES}
        recoverable = [g for g in ghosts if norm(g) in norm_visible]
        assert not recoverable, (
            "以下 sheet 名归一化后能命中源模板，属括号宽度/空白差异而非整名错误，"
            f"修法与整名纠正不同: {recoverable}"
        )


class TestPresetCoverageIsComplete:
    """Property 12：每个 visible sheet 要么有预设、要么显式登记。"""

    def test_no_visible_sheet_is_silently_uncovered(self):
        registered = set(_REGISTRY or {})
        # 🔴 非数据表（实质性程序表 / 函证程序表）走白名单而不是登记表 ——
        # 它们结构上没有取数格，塞进登记表会让登记表被噪声撑大（正是 R3.8 要防的）。
        uncovered = sorted(
            _VISIBLE_NAMES - _PRESET_SHEETS - registered - _NON_DATA_HIT
        )
        if not uncovered:
            return
        pending = [s for s in uncovered if s in PENDING_PRESET_SHEETS]
        others = [s for s in uncovered if s not in PENDING_PRESET_SHEETS]
        by_wb = {r.name: r.workbook for r in _VISIBLE}
        lines = []
        if pending:
            lines.append("[待补预设 Wave 4 Task 10] " + str(len(pending)) + " 张:")
            lines += [f"    {s!r}  <- {by_wb.get(s)}" for s in pending]
        if others:
            lines.append(
                "[待登记 E1_SHEETS_WITHOUT_PRESET，Wave 4 Task 10] "
                + str(len(others))
                + " 张:"
            )
            lines += [f"    {s!r}  <- {by_wb.get(s)}" for s in others]
        pytest.fail(
            "以下 visible sheet 既无预设块也未登记为无预设（静默漏项）:\n"
            + "\n".join(lines)
            + "\n\n登记表真源 = "
            + f"{REGISTRY_SCRIPT.name} 的 {REGISTRY_ATTR}（dict[sheet, 理由]，"
            + f"每条理由 >= {REGISTRY_MIN_REASON_LEN} 字）。"
        )

    def test_pending_preset_sheets_are_real_and_shrinking(self):
        """类 A 性质：PENDING 清单本身不得 stale，且 Task 10 后应清空。"""
        stale = sorted(PENDING_PRESET_SHEETS - _VISIBLE_NAMES)
        assert not stale, (
            f"PENDING_PRESET_SHEETS 含源模板里不存在的 sheet: {stale}"
        )
        landed = sorted(PENDING_PRESET_SHEETS & _PRESET_SHEETS)
        assert not landed, (
            "以下 sheet 已获得预设，请从 PENDING_PRESET_SHEETS 移出（清单只许缩短）: "
            f"{landed}"
        )

    def test_non_data_whitelist_is_effective(self):
        """白名单存在性 + 命中数自检（Task 10 落地后应生效）。

        🔴 **命中数自检是必须的** —— 白名单里的 sheet 名一旦漂移（源模板改名 /
        自己打错字），白名单会静默失效，那些程序表就重新落进「待登记」，
        看起来像「登记表少了几条」而真因是白名单没命中（判据本身失效）。
        """
        if _NON_DATA is None:
            pytest.skip(
                f"{NON_DATA_ATTR} 尚未建立（Wave 4 Task 10）。"
                "此时实质性程序表会被算进「待登记」，是预期行为。"
            )
        assert _NON_DATA, f"{NON_DATA_ATTR} 为空集合（白名单等于没建）"
        # 本守卫口径已剔除「底稿目录」⇒ 白名单在此只应命中 3 张程序表
        expected = {
            "货币资金实质性程序表E1A",
            "货币资金实质性程序表E26A",
            "函证程序表E0A",
        }
        assert _NON_DATA_HIT == expected, (
            f"白名单在本守卫口径下命中 {sorted(_NON_DATA_HIT)}，期望 {sorted(expected)}。"
            "少了说明 sheet 名漂移（白名单失效，程序表会被误算进待登记）；"
            "多了说明误伤了真实数据表。"
        )
        # 白名单里未命中的条目必须是「底稿目录」（本守卫先剔除了它）
        unmatched = sorted(frozenset(_NON_DATA) - _NON_DATA_HIT)
        assert unmatched == ["底稿目录"], (
            f"白名单有源模板里不存在的条目（stale）: {unmatched}"
        )

    def test_non_data_whitelist_is_disjoint_from_presets_and_registry(self):
        """白名单与「有预设」「已登记」三个集合两两互斥。"""
        if _NON_DATA is None:
            pytest.skip(f"{NON_DATA_ATTR} 尚未建立（Wave 4 Task 10）")
        with_preset = sorted(_NON_DATA_HIT & _PRESET_SHEETS)
        assert not with_preset, (
            f"非数据表竟然有预设块: {with_preset} —— 底稿目录/程序表无取数格"
        )
        in_registry = sorted(_NON_DATA_HIT & set(_REGISTRY or {}))
        assert not in_registry, (
            f"非数据表同时出现在无预设登记表里: {in_registry} —— "
            "两者语义不同（白名单=结构上不是数据表；登记表=是数据表但有意不给预设），"
            "混用会让登记表条目数失去意义"
        )


class TestFixScriptsPrintGbkSafe:
    """Property 14：E 类幂等脚本的 print 字面参数必须 GBK 可编码。"""

    def test_print_literals_are_gbk_encodable(self):
        offenders: list[str] = []
        for path in _fix_scripts():
            src = path.read_text(encoding="utf-8")
            try:
                literals = print_string_literals(src)
            except SyntaxError as exc:  # pragma: no cover
                pytest.fail(f"{path.name} 无法解析: {exc}")
            for lineno, text in literals:
                bad = gbk_unsafe_chars(text)
                if bad:
                    offenders.append(
                        f"  {path.name}:{lineno} 含 {describe_chars(bad)}"
                    )
        assert not offenders, (
            "以下 print 字面参数含 GBK 控制台无法编码的字符。GBK 终端下会抛"
            " UnicodeEncodeError，而崩点可能排在写盘之后 -> 退出码非零但改动已落盘，"
            "把 0 欠账误判成红（Requirement 4 的 User Story）:\n"
            + "\n".join(offenders)
            + "\n\n【Wave 4 Task 11 待修】改 ASCII 标记（[OK] / [ERR] / [WARN]）。"
            " 中文汉字与全角标点均可保留。"
        )
