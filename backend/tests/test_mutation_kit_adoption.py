"""采纳守卫 —— 新写的变异脚本必须用共享件（存量冻结名单形态）。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 8.1, 8.2 · Property 29

## 它防的是什么

R8 的 User Story：「这次收敛完，下一个 spec 新写变异脚本时不能又抄一份不带分母的
样板出来。」平台实测的样板抄袭率：可共享函数占各脚本顶层函数的比例中位数约 67%，
而**覆盖面分母只有 3/17 个脚本有** —— 抄漏哪一项就是一个假绿入口。

判据链是：采纳共享件 ⇒ `run_cli` 的 `guard_files` 是**必填关键字参数** ⇒ 强制有分母。
所以「是否采纳共享件」是「是否有覆盖面分母」的充分条件，这就是本守卫的落点。

## 🔴 为什么是「冻结名单」而不是「全局阻断」

本守卫的原设计（R8.1 初版）是**全局阻断**：扫全部 `mutate*.py`，未采纳且不在豁免表
即失败。该形态于 2026-08-16 在**实现之前**被撤回，因为它没有自然终止条件：

    全局阻断 + 「已归档 spec 的豁免会被失效检测打红」
      ⇒ 每归档一个 spec 就强制迁移它的变异脚本
      ⇒ 迁移工作量随归档数线性增长，产出仅是「让 CI 变绿」

实测证据：立项后一周内 `k-cycle` / `i-cycle` / `l-cycle` 三个 spec 全部归档，待迁面
从钦定的 5 个膨胀到 10+ 个，含 1558 行的 `mutate_k_cycle_guards.py` 与 736 行的
`mutate_trim_decision_guards.py`，且每个都要逐条验证判定等价（Property 26）。

改为**存量冻结名单**后：

- 名单外（= 本 spec 之后新建的脚本）未采纳 ⇒ **失败**（User Story 完整覆盖）
- 名单内未采纳 ⇒ 只 INFO（存量不受打扰，跑步机不会重现）
- 名单**只许缩小**（某脚本被迁移后移出），不许新增条目

## 名单「只许缩小」怎么判

用**冻结条目数上限**（:data:`_FROZEN_SIZE`），不用「git 首次提交日期 <= 冻结日」。
后者看起来更严谨，但在 CI 上不可靠：GitHub Actions 默认 `fetch-depth: 1`，
`git log --diff-filter=A -- <path>` 在 shallow clone 下查不到添加 commit ⇒ 判据
静默失效（属 memory 记的 fail-open 形态）。

条目数上限配合另两条判据形成闭环：

1. :func:`test_frozen_list_only_shrinks` —— 条目数不得超过冻结值
2. :func:`test_adopted_scripts_are_removed_from_frozen_list` —— 名单内脚本一旦采纳
   就必须移出（名单随迁移自动收缩，且防「采纳了还挂在名单里」的死条目）
3. :func:`test_every_frozen_entry_has_a_real_reason` —— 每条必须写明为什么不迁，
   空话（「暂不处理」）打红

「同时新增一条又删一条」在理论上可绕过条目数判据，但那需要故意操作且会出现在
diff 里；本守卫的目标是防**无意的**样板抄袭，不是防对抗性绕过。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("backend/scripts/check", "backend/scripts/diagnose")
KIT_PACKAGE = "_mutation_kit"

#: 冻结名单 —— 本 spec 之前已存在、**不要求**采纳共享件的存量脚本。
#:
#: 🔴 **只许缩小，不许新增**：某脚本被迁移到共享件后从此表移出（条目数随之下降）。
#: 新写的变异脚本一律不得加入 —— 它必须直接用共享件。
#:
#: 每条的值是「为什么不迁」，供后来者判断是否值得迁，不是免责声明。
_LEGACY_NOT_REQUIRED: dict[str, str] = {
    # ── 已归档 spec 的产物，迁移需逐条等价性验证（Property 26），成本不由本 spec 支付 ──
    "backend/scripts/diagnose/mutate_h_cycle_guards.py":
        "Task 12 原定待迁，2026-08-16 实测阻塞放弃：M1/M2 用 `groups` 模型同时跑 be"
        "(BE_DUAL) + fe(FE_SCOPE) 两个侧并合并判定（`new_fails = fails_be ∪ fails_fe`），"
        "而共享件的 `Mutation.side` 是单值（每条变异只跑一个侧）。等价迁移需改共享件加 "
        "`sides` 多侧并行+合并判定能力，或非等价拆条（1条→2条，判定矩阵结构改变 ⇒ "
        "违反 Property 26）。须单独立项扩展共享件后再迁",
    "backend/scripts/diagnose/mutate_g7_column_alignment_guards.py":
        "Task 12 原定待迁，2026-08-16 实测阻塞放弃：M14/M15 两条变异含跨行锚点"
        "（`\\n`），在 CRLF 工作树下 text.count() 恒 0 命中 = 已失效的 ANCHOR-MISS。"
        "迁移到共享件声明期会直接拒绝（`anchor 含换行`），而改写锚点 = 改判据 ≠ "
        "行为等价重构（违反 Property 26/28）。须单独立项先修锚点再迁",
    "backend/scripts/check/mutate_trim_decision_guards.py":
        "Task 12 原定待迁，2026-08-16 实测阻塞放弃：全部 12 条变异声明 `sides=(py,ts)`"
        "——每条同时跑 Python 和 TypeScript 测试并合并判定。共享件的 `Mutation.side` 是"
        "单值，不支持跨侧合并。与 h_cycle 同为「共享件架构限制：一条 Mutation 只有一个"
        " side」的同族阻塞。须扩展共享件后再迁",
    # ── Task 13 决策为「不迁」的 7 个（procedure-trimming 已归档，Task 3 已入库）──
    "backend/scripts/check/mutate_task13_wiring_guards.py":
        "Task 13 决策不迁：R5 的目标是入库（防工作树一丢即蒸发），Task 3 已达成；"
        "其 spec 已归档无人维护，迁移的回归风险由本 spec 承担而收益归零",
    "backend/scripts/check/mutate_task14_cscope_guards.py":
        "Task 13 决策不迁，同上。另注：其 MUTATIONS 元素是 dict 而非 dataclass，"
        "字段名叫 file 而非 path，迁移需逐条改写声明",
    "backend/scripts/check/mutate_task18_suggestion_guards.py":
        "Task 13 决策不迁，同上（属已归档 procedure-trimming，84 条变异的等价性验证"
        "成本远超收益）",
    "backend/scripts/check/mutate_task19_apply_guards.py":
        "Task 13 决策不迁，同上。其 M5 锚点依赖 6 空格缩进精确匹配，迁移易引入 ANCHOR-MISS",
    "backend/scripts/check/mutate_task20_review_guards.py":
        "Task 13 决策不迁：14 条变异锚在已归档 spec 的复核链路上，其 spec 无人维护，"
        "等价性验证要跑完整复核测试面，成本远超收益",
    "backend/scripts/check/mutate_task21_note_linkage_guards.py":
        "Task 13 决策不迁：20 条变异（该批最多），锚点覆盖附注联动全链，等价性验证需跑"
        "附注测试面且其锚点邻近并发高频改写的附注模板 ⇒ 判定矩阵不可比",
    "backend/scripts/check/mutate_task23_baseline_guards.py":
        "Task 13 决策不迁，同上。另按 Property 28 登记既有缺陷：T23-4 / T23-8 锚点在 "
        "ProcedureTrimming.vue 零命中（取金额逻辑已重构为 resolveAccountAmount，"
        "该 spec 归档时这两条变异就已失效）—— 只登记不修",
    # ── 立项时在办、其后归档的 spec（R7.5：归属状态不是迁移判据）──
    "backend/scripts/diagnose/mutate_k_cycle_guards.py":
        "1558 行，平台最大的变异脚本。其 spec 已归档，但按 R7.5 不因归档而自动转必迁 —— "
        "迁移需逐条等价性验证，且它的部分锚点落在并发高频改写的 note_template_*.json 上",
    "backend/scripts/diagnose/mutate_i_cycle_guards.py":
        "其 spec 已归档。缺锚点唯一性断言（17 个脚本里唯一缺这项的），迁移会改变其判定"
        "行为 ⇒ 违反 Property 26 的等价要求，须单独立项处理",
    "backend/scripts/diagnose/mutate_l_cycle_guards.py":
        "其 spec 已归档（2026-08-16）。归档当日入库，本 spec 未参与其判据设计，"
        "不代其迁移",
    "backend/scripts/diagnose/mutate_ie_lifecycle_guards.py":
        "1265 行，其 spec `workpaper-import-export-lifecycle-closure` **仍在办**"
        "（24/25）⇒ Property 18 明令本 spec 不得触碰",
    "backend/scripts/diagnose/mutate_wp_export_resolver_guards.py":
        "归属经三条判据查清为在办 spec `workpaper-import-export-lifecycle-closure` 的"
        "前身产物，且当前仍 `??` 未入库（已在入库豁免表登记）⇒ 入库与迁移均交其推进方裁决",
    "backend/scripts/check/mutate_report_line_resolution_guards.py":
        "其 spec `procedure-trim-report-line-account-resolution` 已归档（登记入库豁免后"
        "约 100 分钟内完成，已由其推进方入库）。本 spec 未参与其判据设计，不代其迁移",
    "backend/scripts/check/mutate_guard_attribution.py":
        "其 spec `guard-assertion-attribution-refactor` 已归档（2026-08-16）。"
        "该 spec 的主题正是「守卫判据归因化」，其变异判据与本共享件的四态模型不同构",
    "backend/scripts/check/mutate_amount_column_typing.py":
        "孤儿脚本：其 spec `amount-input-migration-and-column-typing` 目录在 active 区"
        "与 _archive 下均不存在（实扫确认），归属待查清 ⇒ 不在归属未明时改动它",
    "backend/scripts/diagnose/mutate_parent_company_note_guards.py":
        "并发会话正在删除该文件（工作树已删、index 仍有）。留在本表是为了两种结局都安全："
        "删除完成则本条成为可清理的僵尸项（只 INFO），若被恢复则按存量处理不打红",
}

#: 冻结时的条目数（2026-08-16 实测 19 条）。**只许下调**：某脚本迁移后从名单移出，
#: 同时把这个数字改小。上调即意味着有人给新脚本开了后门。
_FROZEN_SIZE = 19

#: 扫描机制自检用的锚点脚本 —— 本 spec 自己的产物，必然存在且必然已采纳。
#: 用它们代替「扫到的数量 >= N」那种会随归档漂移的阈值判据。
_SENTINELS = (
    "backend/scripts/diagnose/mutate_e_cycle_guards.py",
    "backend/scripts/diagnose/mutate_mutation_kit_guards.py",
)


def discover_mutation_scripts() -> list[str]:
    """磁盘上的 `mutate*.py` 全集（仓库相对路径，POSIX 分隔符，已排序）。"""
    found: list[str] = []
    for rel in SCAN_DIRS:
        d = REPO / rel
        if not d.is_dir():
            continue
        for p in sorted(d.glob("mutate*.py")):
            found.append(p.relative_to(REPO).as_posix())
    return found


def imports_kit_src(src: str) -> bool:
    """源码字符串里是否**真的** import 了共享件。

    🔴 用 AST 解析真实 import 语句，**不用字符串匹配** —— 注释或 docstring 里提一句
    `_mutation_kit` 就能骗过 `"_mutation_kit" in src`（memory 假绿第②源：grep 式守卫
    只查字符串存在）。

    🔴 **为什么收成「接收源码」的纯函数**：初版直接接收路径、内部自己读文件，于是
    反向自检只能用内联源码串自行 `ast.walk` 一遍 —— 那证明的是「AST 语义如此」，
    而不是「本文件的实现如此」，把这里的判据改成字符串匹配它照样绿。抽成纯函数后
    自检直接调用被测实现，改坏必红（Property 29 要的正是这个）。
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == KIT_PACKAGE:
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == KIT_PACKAGE for a in node.names):
                return True
    return False


def calls_run_cli_src(src: str) -> bool:
    """源码字符串里是否真的调用了 `run_cli(...)`。

    只 import 不调用等于没采纳 —— 分母是 `run_cli` 的必填参数，不走它就绕过了分母。
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name == "run_cli":
                return True
    return False


def imports_kit(rel_path: str) -> bool:
    """路径版。解析失败一律抛（fail-closed）：坏掉的脚本也该被发现。"""
    return imports_kit_src((REPO / rel_path).read_text(encoding="utf-8"))


def calls_run_cli(rel_path: str) -> bool:
    """路径版，见 :func:`calls_run_cli_src`。"""
    return calls_run_cli_src((REPO / rel_path).read_text(encoding="utf-8"))


def find_violations(scripts: list[str], frozen: dict[str, str]) -> list[str]:
    """核心判据（抽成纯函数以便反向自检）：名单外、未采纳共享件的脚本。"""
    bad: list[str] = []
    for s in scripts:
        if s in frozen:
            continue
        if not imports_kit(s) or not calls_run_cli(s):
            bad.append(s)
    return bad


# ─── 扫描机制自检（放在最前：它失效会让后面所有判据恒绿）────────────────────


def test_scan_finds_sentinel_scripts() -> None:
    """扫描机制有效性 —— 用结构判据而非数量阈值。

    本 spec 自己的两个脚本必然存在；扫不到它们说明 glob 或目录写错了，
    那会让主判据恒绿（扫到空集时「无违规」恒成立）。
    """
    scripts = set(discover_mutation_scripts())
    missing = [s for s in _SENTINELS if s not in scripts]
    assert not missing, (
        f"扫描不到锚点脚本 {missing} ⇒ 扫描路径失效，主判据会恒绿。实扫 {len(scripts)} 个"
    )


def test_all_scripts_parse_as_python() -> None:
    """全部脚本必须可 AST 解析 —— 解析不了的会让采纳判据抛错而非静默放过。"""
    broken: list[str] = []
    for s in discover_mutation_scripts():
        try:
            ast.parse((REPO / s).read_text(encoding="utf-8"))
        except SyntaxError as exc:
            broken.append(f"{s} → {exc}")
    assert not broken, "以下变异脚本无法解析：\n" + "\n".join("  " + b for b in broken)


# ─── 主判据 ──────────────────────────────────────────────────────────────────


def test_new_scripts_must_use_the_shared_kit() -> None:
    """🔴 主判据：冻结名单**外**的变异脚本必须真用共享件（import + 调 run_cli）。"""
    violations = find_violations(discover_mutation_scripts(), _LEGACY_NOT_REQUIRED)
    assert not violations, (
        "以下变异脚本不在存量冻结名单内，却没有使用 `_mutation_kit` 共享件：\n"
        + "\n".join("  !! " + v for v in violations)
        + "\n\n新写的变异脚本必须走共享件 —— 它的 run_cli 把覆盖面分母（guard_files）"
          "设成必填关键字参数，自己抄一份样板就会漏掉分母、静态锚点自检、四态判定中的某项，"
          "而每漏一项都是一个假绿入口。\n"
          "存量脚本才可登记进 _LEGACY_NOT_REQUIRED（该表只许缩小，不接受新条目）。"
    )


def test_frozen_list_only_shrinks() -> None:
    """冻结名单不得增长 —— 否则新脚本只要把自己加进名单就能逃避约束。"""
    size = len(_LEGACY_NOT_REQUIRED)
    assert size <= _FROZEN_SIZE, (
        f"冻结名单从 {_FROZEN_SIZE} 条涨到 {size} 条 —— 该表只许因『某脚本被迁移』而缩小。"
        "新写的变异脚本不得登记豁免，必须直接用共享件（R8.1/R8.2）。"
        f"\n若确有存量脚本被遗漏，需在 spec 里说明并同步上调 _FROZEN_SIZE（当前 {_FROZEN_SIZE}）"
    )


def test_adopted_scripts_are_removed_from_frozen_list() -> None:
    """名单内脚本一旦采纳共享件，就必须移出名单（防死条目 + 让名单自动收缩）。"""
    stale: list[str] = []
    for rel in sorted(_LEGACY_NOT_REQUIRED):
        p = REPO / rel
        if not p.exists():
            continue
        if imports_kit(rel) and calls_run_cli(rel):
            stale.append(rel)
    assert not stale, (
        "以下脚本已采纳共享件，应从 _LEGACY_NOT_REQUIRED 移出并把 _FROZEN_SIZE 减去相应条数：\n"
        + "\n".join("  " + s for s in stale)
        + "\n（留着会让名单虚高，掩盖真实的未采纳数）"
    )


def test_every_frozen_entry_has_a_real_reason() -> None:
    """每条豁免必须写明为什么不迁 —— 空话让名单退化成免责声明。"""
    problems: list[str] = []
    for rel, reason in sorted(_LEGACY_NOT_REQUIRED.items()):
        if len(reason) < 20:
            problems.append(f"{rel}: 理由过短（{len(reason)} 字）")
        elif not any(
            kw in reason
            for kw in ("等价", "不同构", "归属", "在办", "待迁", "决策", "归档", "并发", "重写")
        ):
            problems.append(f"{rel}: 理由无可归因关键词，疑似空话 → {reason[:40]!r}")
    assert not problems, "冻结名单的理由不合规：\n" + "\n".join("  " + p for p in problems)


def test_frozen_entries_point_at_real_paths() -> None:
    """名单项的路径形态必须正确（POSIX 分隔符 + 落在扫描目录下）。

    不存在于磁盘只作 INFO 不失败 —— 并发会话删除某脚本不该让本守卫打红
    （实测 `mutate_parent_company_note_guards.py` 正处于「工作树已删、index 仍有」态）。
    """
    problems: list[str] = []
    for rel in sorted(_LEGACY_NOT_REQUIRED):
        if "\\" in rel:
            problems.append(f"{rel}: 应用 POSIX 分隔符")
        if not any(rel.startswith(d + "/") for d in SCAN_DIRS):
            problems.append(f"{rel}: 不在扫描目录 {SCAN_DIRS} 下，登记无效")
        if not Path(rel).name.startswith("mutate"):
            problems.append(f"{rel}: 文件名不以 mutate 开头，不会被扫描命中")
    assert not problems, "冻结名单路径形态有误：\n" + "\n".join("  " + p for p in problems)

    zombies = [r for r in sorted(_LEGACY_NOT_REQUIRED) if not (REPO / r).exists()]
    if zombies:
        print(
            "[INFO] 冻结名单有 %d 个僵尸项（文件已不在磁盘，可随下次改动清理）：%s"
            % (len(zombies), zombies)
        )


# ─── 反向自检：Property 29 的三条不变量 ──────────────────────────────────────
#
# memory 铁律：每写完守卫必做变异检验，「没打红 = 守卫有缺陷，不是代码没问题」。
# 这里把核心判据 find_violations 抽成纯函数后直接反证。


def test_reverse_selfcheck_unadopted_new_script_is_caught() -> None:
    """① 名单外未采纳的脚本必须被报出（主判据的正向能力）。"""
    victim = "backend/scripts/check/mutate_task13_wiring_guards.py"  # 确定未采纳
    assert not imports_kit(victim), f"自检前提被破坏：{victim} 应当未采纳共享件"
    caught = find_violations([victim], frozen={})
    assert caught == [victim], f"名单外未采纳脚本没被报出 ⇒ 判据失效，实际={caught}"


def test_reverse_selfcheck_frozen_entry_is_not_flagged() -> None:
    """② 名单内未采纳的存量脚本**不得**被报出。

    🔴 这条是收敛的核心不变量：它若失败，就意味着「归档即必迁」的跑步机重新出现 ——
    存量脚本会持续让 CI 红，逼后来者去迁移一批 1000+ 行的历史脚本。
    """
    victim = "backend/scripts/check/mutate_task13_wiring_guards.py"
    assert find_violations([victim], frozen={victim: "存量"}) == [], (
        "名单内的存量脚本被报成违规 ⇒ 冻结名单失效，跑步机重现"
    )


def test_reverse_selfcheck_adopted_script_passes() -> None:
    """③ 已采纳的脚本不得被误报（防判据反向失效 —— 全报一遍也能让①通过）。"""
    real = "backend/scripts/diagnose/mutate_e_cycle_guards.py"
    assert imports_kit(real) and calls_run_cli(real), f"前提被破坏：{real} 应已采纳共享件"
    assert find_violations([real], frozen={}) == [], "已采纳脚本被误报 ⇒ 判据有假阳性"


def test_reverse_selfcheck_import_without_run_cli_is_caught() -> None:
    """④ 只 import 不调 run_cli 等于没采纳 —— 那样会绕过必填的覆盖面分母。

    判据直接调被测实现（不是内联再 walk 一遍），故把 :func:`calls_run_cli_src`
    改成恒真就会打红这条。
    """
    src = "from _mutation_kit import Mutation\nMUTATIONS = []\n"
    assert imports_kit_src(src), "import 判据认不出真实的 from-import"
    assert not calls_run_cli_src(src), (
        "run_cli 判据把「只 import 未调用」当成了采纳 ⇒ 分母可被绕过"
    )


def test_reverse_selfcheck_comment_mention_is_not_adoption() -> None:
    """⑤ 注释里提一句 `_mutation_kit` 不算采纳（假绿第②源：grep 式判据）。

    这条是 AST 判据存在的**全部理由**：把 :func:`imports_kit_src` 换成
    `KIT_PACKAGE in src` 这类字符串匹配，它必须打红。
    """
    src = '"""本脚本参考 _mutation_kit 的四态判定写法。"""\nimport json\n'
    assert KIT_PACKAGE in src, "构造用例应当在文本层面含该串（否则证明不了 AST 的价值）"
    assert not imports_kit_src(src), (
        "AST 判据把注释里的提及当成了 import ⇒ 已退化为字符串匹配"
    )


def test_reverse_selfcheck_aliased_import_is_adoption() -> None:
    """⑥ 各种真实 import 形态都要认出来（防判据只认一种写法而放过其余）。

    存量迁移里三种形态都出现过：`from _mutation_kit import Mutation as Mut`（e_cycle）·
    `from _mutation_kit import ANY_RED, Mutation as Mut, run_cli`（note_text_hygiene）·
    子模块形态。漏认任一种都会把已采纳的脚本误报成违规。
    """
    for src in (
        "from _mutation_kit import Mutation as Mut\n",
        "from _mutation_kit.spec import Mutation\n",
        "import _mutation_kit\n",
        "from _mutation_kit import ANY_RED, Mutation as Mut, run_cli\n",
    ):
        assert imports_kit_src(src), f"未认出真实 import 形态：{src!r}"
