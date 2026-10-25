"""Task 7.1 / 7.4 —— OO 路径隔离的**源码锁与普查**（J1 / J2 / J5）+ 路由清单反向判据。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 2.2 / 2.3 / 2.5 · design § 3.3（J1~J5 判据表）· ADR-AOS-001（OO 路径零改动）

═══ J1~J5 在 design § 3.3 里**五条都在**（逐字引原文，不是我编的）═══

| # | 判据 | 形态 | 归属任务 |
| --- | --- | --- | --- |
| J1 | `oo_to_html.py` 的三个 `_mirror_*` 转发方法**不出现** prune 相关符号 | AST/源码锁断言 | 7.1 §1 |
| J2 | `store_mirror.mirror_projection_into_store` 的签名与函数体**不新增**删除逻辑 | 会话基线 sha256 + 「本 spec 符号在该函数体内命中为零」双条件 | 7.1 §2 |
| J3 | 同一 `(base, projection)` 经 OO 路径与 adopt 路径执行，**删除侧结果不同** | 变异反证（相同即判据失效） | **7.2**（Property 5，落 `test_aos_property_mode_dichotomy.py`） |
| J4 | OO callback 既有引用面回归零红 | 定向跑既有测试面 | **7.3**（无新判据文件，见 tasks.md 清单） |
| J5 | prune 的调用点在全仓**恰 1 处**且位于 adopt 链上 | 全仓 grep + 逐条判注释/代码 | 7.1 §3 |

⇒ 任务书只在 7.1 下列了 J1 / J2 / J5，**不是** J3 / J4 不存在 —— 它们分别是 7.2 与 7.3 的
判据。本文件承载 J1 / J2 / J5 与 Task 7.4；J3 在伴生 property 文件、J4 是定向回归动作。

═══ 🔴 J1 的现算与 design 措辞**不符**（本轮发现，如实登记，未改 design）═══

design 与 `store_mirror.py` 模块 docstring 都写「`OoToHtmlCoordinator` 的三个 `_mirror_*`
方法改为**薄转发**」。现算实证：

* `HEAD` 版 `oo_to_html.py` 有 **4** 个 `_mirror_*` 定义（3 个真实现 + 1 个旧名别名）；
* **工作树**版只剩 **2** 个：`_mirror_store_backed_if_needed`（唯一真转发）与
  `_mirror_d2_store_if_needed`（转调前者的旧名别名）。

`_mirror_dedicated_dict_stores` / `_mirror_d4_dual_stores` 这两个**不是**被改成转发，而是被
**整体删除**，其函数体搬进 `store_mirror` 成了 `_mirror_dedicated_dict_stores` /
`_mirror_dual_stores`（由 `mirror_projection_into_store` 内部调用）。⇒ 「三个转发方法」这句
在现树上不成立。本节据此把判据写成**与个数无关**的形态：扫 `oo_to_html` 里**全部**
`_mirror_*` 方法（现算 2）**并且**扫 `store_mirror` 的**全部**模块级镜像函数（现算 3），
两侧合起来才是 design 想保护的那「三个镜像体」的完整落点。个数另配一条**棘轮**断言 ——
个数一变就打红，逼迫重新确认覆盖面与 design 措辞，而不是让判据静默漏掉新方法。

═══ 🔴 J2 为什么**必须**是函数体 sha256，而 `git diff == 0` 是**恒真**门禁 ═══

design 给的理由是「工作树可能被并发会话改动」。本轮现算发现一个**更强**的理由：

    git status --porcelain -- backend/app/services/workpaper_sync/store_mirror.py
    ?? backend/app/services/workpaper_sync/store_mirror.py

`store_mirror.py` **尚未进版本库（untracked）** ⇒ `git diff` 对它**恒为空**。于是
「`git diff == 0`」这条判据不是「弱」，而是**恒真** —— 无论有人往那个函数里塞多少删除逻辑，
它都绿。这与平台铁律 ㉗「有门禁 ≠ 门禁生效；永真门禁比没门禁更糟」是同一形态。
（顺带实证：同目录 `oo_to_html.py` 是 `M`、`-465` 行，正是本次抽取；若拿**整文件** diff 当
判据，J1 会因为别人的合法抽取而长期打红 —— 永红与永真两头都踩。）

⇒ 本节的基线是 `ast.get_source_segment` 取出的**函数体源码段** sha256：
① 与文件内其它位置的改动无关（并发会话动别处不打红）；
② 对该函数**一个字符**的改动敏感（§2 的 B2 变异实测）；
③ 不依赖 git 状态 ⇒ untracked / staged / committed 三态下行为一致。

═══ 🔴 J5 为什么必须 AST（平台铁律 ㉖，本 spec 已踩过一次）═══

`prune_undeclared_rows` 在全仓的文本命中里**大半不是调用点**：现算全仓 tokenize 命中
**121** 条（`NAME` 74 / `STRING` 38 / `FSTRING_MIDDLE` 3 / `COMMENT` 6），而 AST 真调用点
只有 32 条、其中落在 `backend/app/`（生产口径）的**恰 1 条**。本 spec 6.4 的原棘轮
`"_diff_snapshots" not in src` 就是被注释骗成假阴的同型事故（tasks.md 6.4 已登记）。
⇒ 本节一律用 AST 节点判定，文本口径只作为「命中总数」的对照登记，不参与断言。

═══ Task 7.4 是**反向**判据（容易做反）═══

本 spec **不新增路由** ⇒ `test_task28_sync_router.py` 的三处分母**不应**变化。§4 把三处现值
钉成棘轮，并配「假装新增一个路由 ⇒ 判据打红」的变异反证。🔴 判据方向是「保持原值」，
**不是**「跟着 router 走」—— 后者等于把守卫改成复述实现，新增路由时静默全绿。
"""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import io
import tokenize
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import adopt_overwrite_apply as AOA
from app.services.workpaper_sync import adopt_overwrite_plan as AOP
from app.services.workpaper_sync import oo_to_html as OO
from app.services.workpaper_sync import store_mirror as SM

# 🔴 共用件只 import 不另造第二份（域内纪律，见 test_aos_adopt_plan_wiring 模块 docstring）。
from test_aos_adopt_plan_wiring import (  # noqa: E402
    _ROUTER_PY,
    _callee_name,
    _source_mutant,
)

_REPO = Path(__file__).resolve().parents[3]
_APP = _REPO / "backend" / "app"
_SM_PY = _APP / "services" / "workpaper_sync" / "store_mirror.py"
_ROUTER_TEST_PY = Path(__file__).with_name("test_task28_sync_router.py")

#: 本 spec 引入的符号 —— 一个都不许出现在 OO 侧执行层的**代码**里。
#: 🔴 `overwrite` / `declared` / `prune` 是**子串**口径（比符号名更宽），刻意的：
#: 有人手写一个 `_prune_rows` 私有函数塞进 `store_mirror` 也会被抓住。
AOS_CODE_TOKENS: tuple[str, ...] = (
    "prune",
    "overwrite",
    "declared",
    "substrate",
    "adopt",
    "OverwritePlan",
    "RowReader",
)

#: prune 门面名（J5 的被查符号）。
PRUNE = "prune_undeclared_rows"
#: adopt 链上唯一允许调它的函数。
DELETION_APPLY = "apply_overwrite_deletions"


# ═══════════════════════════════════════════════════════════════════════════════
# 工具：AST 取件（按模块对象，不写死行号 —— `.py` 行号会漂）
# ═══════════════════════════════════════════════════════════════════════════════


def _tree_of(module: Any) -> ast.Module:
    return ast.parse(inspect.getsource(module))


def _defs_named(module: Any, *, prefix: str, top_level_only: bool = False) -> list[Any]:
    """按名字前缀取函数定义（`top_level_only` 时只取模块级）。"""
    tree = _tree_of(module)
    pool = tree.body if top_level_only else list(ast.walk(tree))
    return sorted(
        (
            n
            for n in pool
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith(prefix)
        ),
        key=lambda n: n.name,
    )


def _code_tokens(node: ast.AST) -> set[str]:
    """节点子树里**真代码**引用到的标识符集合。

    🔴 只收 `Name` / `Attribute` / `ImportFrom` / 关键字参数名 —— docstring 与 `#` 注释
    天然不在其中（前者是 `Expr(Constant)` 不产生 `Name`、后者根本不进 AST），这正是
    铁律 ㉖ 要的「注释骗不过扫描器」。字符串常量**刻意排除**（见 `_string_tokens`）。
    """
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
        elif isinstance(sub, ast.ImportFrom):
            found.add(str(sub.module or ""))
            found.update(a.name for a in sub.names)
            found.update(a.asname for a in sub.names if a.asname)
        elif isinstance(sub, ast.Import):
            found.update(a.name for a in sub.names)
        elif isinstance(sub, ast.keyword) and sub.arg:
            found.add(sub.arg)
    return {t for t in found if t}


def _string_tokens(node: ast.AST) -> set[str]:
    """节点子树里**字符串常量**的内容（对照用，不参与 J1/J2 断言）。"""
    return {
        sub.value
        for sub in ast.walk(node)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    }


def judge_no_aos_tokens(node: ast.AST, *, label: str) -> list[str]:
    """判据：节点子树的**代码**里不出现任何本 spec 符号（J1 / J2 共用）。"""
    hits = sorted(
        f"{token}→{ident}"
        for ident in _code_tokens(node)
        for token in AOS_CODE_TOKENS
        if token.lower() in ident.lower()
    )
    return [f"{label} 的代码里出现本 spec 符号 {hits}"] if hits else []


# ═══════════════════════════════════════════════════════════════════════════════
# §1 J1 —— OO 侧镜像体的源码锁（个数无关 + 个数棘轮）
# ═══════════════════════════════════════════════════════════════════════════════

#: 现算：`oo_to_html` 工作树版的 `_mirror_*` 方法（棘轮；design 写「三个」已不符，见模块 docstring）。
OO_MIRROR_METHODS: tuple[str, ...] = ("_mirror_d2_store_if_needed", "_mirror_store_backed_if_needed")
#: 现算：`store_mirror` 的模块级镜像函数 —— 被搬走的那两个镜像体现在住这里。
SM_MIRROR_FUNCS: tuple[str, ...] = (
    "_mirror_dedicated_dict_stores",
    "_mirror_dual_stores",
    "mirror_projection_into_store",
)


class TestJ1MirrorBodiesAreFreeOfPruneSymbols:
    """J1：OO 侧镜像体的**代码**里一个本 spec 符号都没有。"""

    def test_every_oo_mirror_method_is_clean(self) -> None:
        """判据与个数无关：扫 `oo_to_html` 里**全部** `_mirror_*` 方法。"""
        found = _defs_named(OO, prefix="_mirror")
        assert found, "oo_to_html 里一个 `_mirror_*` 方法都没有 —— 判据分母塌陷成空集必恒真"
        violations: list[str] = []
        for fn in found:
            violations += judge_no_aos_tokens(fn, label=f"oo_to_html.{fn.name}")
        assert violations == [], violations

    def test_every_store_mirror_function_is_clean(self) -> None:
        """J1 的另一半：被搬进 `store_mirror` 的两个镜像体（+ 门面）同样干净。

        🔴 少了这一半，「把 prune 塞进 `_mirror_dual_stores`」这条最危险的形态就没人看 ——
        它是 OO 与 adopt 共用的执行层，删除侧在那里生效会静默删掉用户刚在表单侧加的行
        （Requirement 2.1 的原文风险）。
        """
        found = _defs_named(SM, prefix="", top_level_only=True)
        assert found, "store_mirror 里没有模块级函数 —— 分母塌陷"
        violations: list[str] = []
        for fn in found:
            violations += judge_no_aos_tokens(fn, label=f"store_mirror.{fn.name}")
        assert violations == [], violations

    def test_the_mirror_census_matches_the_recorded_baseline(self) -> None:
        """棘轮：两侧镜像体清单与现算基线逐值相等。

        个数/命名一变即打红 —— 不是为了阻止改动，是逼迫改动者重新确认 J1 覆盖面，
        以及 design § 3.3「三个 `_mirror_*` 转发方法」这句措辞（现树已不符）。
        """
        assert tuple(n.name for n in _defs_named(OO, prefix="_mirror")) == OO_MIRROR_METHODS
        assert tuple(n.name for n in _defs_named(SM, prefix="", top_level_only=True)) == (
            SM_MIRROR_FUNCS
        )

    def test_the_real_forwarder_forwards_and_nothing_else(self) -> None:
        """`_mirror_store_backed_if_needed` 必须是**薄转发**：只调门面，不自己算。"""
        fn = next(n for n in _defs_named(OO, prefix="_mirror") if n.name == OO_MIRROR_METHODS[1])
        callees = {_callee_name(c) for c in ast.walk(fn) if isinstance(c, ast.Call)}
        assert "mirror_projection_into_store" in callees, (
            f"转发方法没调门面（实调 {sorted(callees)}）—— 它不再是薄转发，J1 的保护面就漂了"
        )
        assert not callees - {"mirror_projection_into_store", "str"}, (
            f"转发方法多出了调用 {sorted(callees - {'mirror_projection_into_store', 'str'})} —— "
            "薄转发只应做「取入参 + 调门面」"
        )

    def test_mutant_prune_call_inside_a_mirror_body_is_caught(self) -> None:
        """变异 A1：往 `_mirror_store_backed_if_needed` 体内插一次 prune 调用 ⇒ J1 打红。

        🔴 变异在 **deepcopy 的 AST 树**上做，生产文件一字不改（本域有并发会话）。
        """
        fn = copy.deepcopy(
            next(n for n in _defs_named(OO, prefix="_mirror") if n.name == OO_MIRROR_METHODS[1])
        )
        fn.body.append(ast.parse(f"{PRUNE}(payload, row_keys={{}}, reader=None)").body[0])
        got = judge_no_aos_tokens(fn, label="MUTANT")
        assert len(got) == 1 and "prune" in got[0], f"A1 未打红，实得 {got}"

    def test_mutant_a_renamed_private_pruner_is_also_caught(self) -> None:
        """变异 A2：换个名字手写私有剪枝（`_prune_rows`）⇒ 子串口径仍打红。

        A1 只证「照抄门面名会被抓」，A2 才证「换名字绕不过去」—— 没有 A2，判据退化成
        「禁止出现某一个字面量」，而真实的「顺手统一两侧」多半是重写一份。
        """
        fn = copy.deepcopy(_defs_named(SM, prefix="", top_level_only=True)[-1])
        fn.body.append(ast.parse("_prune_rows(payload)").body[0])
        got = judge_no_aos_tokens(fn, label="MUTANT")
        assert len(got) == 1 and "_prune_rows" in got[0], f"A2 未打红，实得 {got}"

    def test_the_judge_ignores_docstrings_and_comments(self) -> None:
        """反向：判据**不**被 docstring / 注释里的指针说明骗红（铁律 ㉖ 的另一向）。

        `store_mirror` 模块 docstring 现算就提到 `adopt-substrate`（现读实证），若判据是
        文本 `in`，它当场假红并诱导后人删掉那条有用的指针注释。
        """
        module_doc = ast.get_docstring(_tree_of(SM)) or ""
        assert "adopt-substrate" in module_doc, (
            "store_mirror 模块 docstring 不再提 adopt-substrate —— 本反向判据失去被测对象，"
            "须换一处仍存在的注释锚点，不得删断言"
        )
        fn = copy.deepcopy(_defs_named(SM, prefix="", top_level_only=True)[-1])
        fn.body.insert(0, ast.parse(f'"""指针：删除侧在 {PRUNE}，见 ADR-AOS-001。"""').body[0])
        assert judge_no_aos_tokens(fn, label="DOC") == [], (
            "判据被 docstring 骗红 —— 它在数文本而不是数代码"
        )
        assert any(PRUNE in s for s in _string_tokens(fn)), "变异体里那段 docstring 没插进去"


# ═══════════════════════════════════════════════════════════════════════════════
# §2 J2 —— 会话基线 sha256 + 「本 spec 符号在函数体内命中为零」**双条件**
# ═══════════════════════════════════════════════════════════════════════════════

MIRROR_FACADE = "mirror_projection_into_store"

#: 🔴 **会话基线** —— `mirror_projection_into_store` 的**函数体源码段** sha256（现算，非整文件）。
#: 取法：`ast.get_source_segment(store_mirror 源码, 该函数的 AST 节点)` → utf-8 → sha256。
#: 为什么不是整文件 / 不是 `git diff`：见模块 docstring「J2 为什么必须是函数体 sha256」——
#: `store_mirror.py` 是 **untracked**，`git diff` 对它恒空 ⇒ 那条判据恒真。
#: 🔴 一旦本函数确有合法改动（非本 spec 所致），**先查改了什么**，确认与删除侧无关后再更新此值，
#: 并在 tasks.md 登记新旧两值 —— 不得在不看 diff 的情况下顺手改成实测值。
MIRROR_FACADE_BODY_SHA256 = "41acda282f40a382b5eff29366b9b18be766ac1400f1a497a883599cc5e65364"
#: 同上口径的行数（`splitlines()`），与 sha 一起给，便于人工快速判断改动量级。
MIRROR_FACADE_BODY_LINES = 112


def _facade_segment() -> str:
    """取门面函数的源码段（AST 定位 ⇒ 与文件内其它位置的改动无关）。"""
    src = _SM_PY.read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.parse(src).body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == MIRROR_FACADE
    )
    segment = ast.get_source_segment(src, node)
    assert segment, f"{MIRROR_FACADE} 的源码段取不到 —— 基线判据无从计算，不得跳过"
    return segment


def judge_facade_baseline(segment: str) -> list[str]:
    """条件①：函数体 sha256 与会话基线逐字相等。"""
    got = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    if got == MIRROR_FACADE_BODY_SHA256:
        return []
    return [
        f"{MIRROR_FACADE} 的函数体已变（sha256 {got} ≠ 基线 {MIRROR_FACADE_BODY_SHA256}；"
        f"行数 {len(segment.splitlines())} vs 基线 {MIRROR_FACADE_BODY_LINES}）—— "
        "ADR-AOS-001 承诺 OO 路径零改动，先查改了什么再决定是否更新基线"
    ]


class TestJ2FacadeIsLockedByBothConditions:
    """J2 双条件：**基线 sha256**（管「有没有动过」）+ **AST 符号零命中**（管「动的是不是删除逻辑」）。

    两条缺一不可：只有 sha 时，谁都不知道红是因为改了注释还是塞了删除逻辑；只有符号扫描时，
    换个没在 `AOS_CODE_TOKENS` 里的名字（比如 `_reap`）就绕过去了。
    """

    def test_condition_1_body_matches_the_session_baseline(self) -> None:
        assert judge_facade_baseline(_facade_segment()) == []

    def test_condition_2_no_aos_symbol_in_the_facade_body(self) -> None:
        node = next(
            n for n in _defs_named(SM, prefix="", top_level_only=True) if n.name == MIRROR_FACADE
        )
        assert judge_no_aos_tokens(node, label=f"store_mirror.{MIRROR_FACADE}") == []

    def test_the_signature_takes_no_overwrite_mode_parameter(self) -> None:
        """Requirement 2.2 的字面兑现：OO 调用点**无需传任何新参数**。

        判据形态是「参数名集合 == 现算基线」而不是「不含 mode 字样」—— 后者挡不住
        `authoritative_side="substrate"` 这类换词写法。
        """
        signature = inspect.signature(SM.mirror_projection_into_store)
        assert tuple(signature.parameters) == (
            "session",
            "adapter_id",
            "project_id",
            "wp_id",
            "merged_projection",
            "commit",
        ), f"门面签名已变：{tuple(signature.parameters)}"
        assert signature.parameters["commit"].default is True, (
            "`commit` 默认值不再是 True —— OO 调用点不传它就会拿到与改动前不同的行为"
        )

    def test_mutant_b1_a_deletion_call_in_the_body_is_caught_by_condition_2(self) -> None:
        """变异 B1：往门面体内插一次 prune 调用 ⇒ **条件②** 打红（sha 也会红，但那是条件①的活）。"""
        node = copy.deepcopy(
            next(n for n in _defs_named(SM, prefix="", top_level_only=True) if n.name == MIRROR_FACADE)
        )
        node.body.append(ast.parse(f"payload, _d = {PRUNE}(payload, row_keys={{}}, reader=None)").body[0])
        got = judge_no_aos_tokens(node, label="MUTANT")
        assert got and "prune" in got[0], f"B1 未被条件② 抓住，实得 {got}"

    def test_mutant_b2_a_single_character_edit_is_caught_by_condition_1(self) -> None:
        """变异 B2（**可伪证性**）：函数体改**一个字符** ⇒ 条件① 打红。

        🔴 这一条是基线「可伪证」的全部依据。没有它，`MIRROR_FACADE_BODY_SHA256` 只是一个
        写在测试里的常量，谁也不知道它对改动到底敏不敏感 —— 而一个不敏感的基线就是永真门禁。
        """
        segment = _facade_segment()
        anchor = "if commit:"
        assert segment.count(anchor) == 1, (
            f"锚点 {anchor!r} 在门面体内命中 {segment.count(anchor)} 次（须恰 1）—— "
            "命中 0 次时下面的 `replace` 静默空操作，B2 会假绿"
        )
        mutated = segment.replace(anchor, "if  commit:")  # 只多一个空格
        assert mutated != segment
        got = judge_facade_baseline(mutated)
        assert len(got) == 1 and "函数体已变" in got[0], f"B2 未打红，实得 {got}"

    def test_the_baseline_is_not_tied_to_git_state(self) -> None:
        """反向登记：`store_mirror.py` 现为 **untracked** ⇒ `git diff` 恒空。

        本测试不调 git（跑测试不该依赖仓库状态），而是钉住**推论**：基线口径必须是函数体段
        而非整文件。整文件 sha 与函数体 sha 必须是两个不同的值 —— 相等意味着文件里只有这一个
        函数，那时「改别处不打红」这条优势就不存在了，判据形态要重新裁。
        """
        whole = hashlib.sha256(_SM_PY.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        assert whole != MIRROR_FACADE_BODY_SHA256, (
            "整文件 sha 与函数体 sha 相等 —— store_mirror 已塌成单函数文件，J2 口径须重裁"
        )
        segment_lines = len(_facade_segment().splitlines())
        file_lines = len(_SM_PY.read_text(encoding="utf-8").splitlines())
        assert segment_lines < file_lines, (
            f"函数体 {segment_lines} 行 == 整文件 {file_lines} 行 —— 同上"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §3 J5 —— prune 调用点普查：AST 真调用点 vs 文本命中（逐条判注释/代码）
# ═══════════════════════════════════════════════════════════════════════════════

#: 生产口径 = `backend/app/**`。测试与探针**合法**引用它（它们就是在测它）⇒ 不进分子。
#: 🔴 design 原文写「全仓恰 1 处」；现算全仓 AST 调用点 **32** 条（测试 20 + 别的会话探针 11
#: + 生产 1），文本命中 **121** 条 ⇒ 「全仓」只能按**生产口径**成立。两个数都在 tasks.md 登记，
#: 断言用生产口径，文本口径只作对照（§3 末尾的对照测试）。
PRUNE_DEF_MODULE = "adopt_overwrite_plan.py"
PRUNE_CALL_MODULE = "adopt_overwrite_apply.py"


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _ast_call_sites(root: Path, symbol: str) -> list[tuple[str, int, str]]:
    """AST 真调用点：`(相对路径, 行号, 所在函数名)`。docstring / 注释天然不在其中。"""
    sites: list[tuple[str, int, str]] = []
    for path in _py_files(root):
        src = path.read_text(encoding="utf-8")
        if symbol not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:  # pragma: no cover - 生产树里不应出现
            continue
        owner: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and _callee_name(sub) == symbol:
                        owner[id(sub)] = node.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _callee_name(node) == symbol:
                sites.append(
                    (path.relative_to(_REPO).as_posix(), node.lineno, owner.get(id(node), "<module>"))
                )
    return sorted(sites)


def _text_hits(root: Path, symbol: str) -> dict[str, int]:
    """tokenize 口径的文本命中分布（对照用；`COMMENT` / `STRING` 即「注释 vs 代码」的判法）。"""
    tally: dict[str, int] = {}
    for path in _py_files(root):
        src = path.read_text(encoding="utf-8")
        if symbol not in src:
            continue
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover
            continue
        for tok in toks:
            if symbol in tok.string:
                kind = tokenize.tok_name[tok.type]
                tally[kind] = tally.get(kind, 0) + 1
    return tally


class TestJ5PruneHasExactlyOneProductionCallSite:
    def test_exactly_one_call_site_in_production(self) -> None:
        sites = _ast_call_sites(_APP, PRUNE)
        assert len(sites) == 1, (
            f"生产代码里 {PRUNE} 的调用点有 {len(sites)} 处：{sites} —— "
            "ADR-AOS-001 的全部内容就是「删除侧只在 adopt 链上」，多一处即破"
        )
        rel, _line, owner = sites[0]
        assert rel.endswith(PRUNE_CALL_MODULE), f"唯一调用点落在 {rel}（应在 {PRUNE_CALL_MODULE}）"
        assert owner == DELETION_APPLY, (
            f"唯一调用点在 {owner}（应在 {DELETION_APPLY}）—— 它是 adopt 链上的删除侧函数"
        )

    def test_that_one_call_site_really_is_on_the_adopt_chain(self) -> None:
        """「在 adopt 链上」逐段落实：service → 删除侧 → prune，三段都用 AST 定位。

        🔴 不靠「它在 adopt_* 命名的文件里」—— 文件名不是调用链。
        """
        service_tree = ast.parse(
            (_APP / "services" / "workpaper_sync" / "adopt_substrate_response.py").read_text(
                encoding="utf-8"
            )
        )
        entry = next(
            n
            for n in ast.walk(service_tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "compute_adopt_substrate"
        )
        assert any(
            _callee_name(c) == DELETION_APPLY for c in ast.walk(entry) if isinstance(c, ast.Call)
        ), f"compute_adopt_substrate 没调 {DELETION_APPLY} —— adopt 链断了，J5 的「在链上」无从成立"
        apply_fn = next(
            n
            for n in ast.walk(ast.parse(inspect.getsource(AOA)))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == DELETION_APPLY
        )
        assert (
            len([c for c in ast.walk(apply_fn) if isinstance(c, ast.Call) and _callee_name(c) == PRUNE])
            == 1
        ), f"{DELETION_APPLY} 对 {PRUNE} 不是恰 1 次调用"

    def test_neither_protected_module_calls_or_imports_prune(self) -> None:
        """J5 与 J1/J2 的交点：两个受保护模块对 prune **零** 调用、零 import、零裸引用。"""
        for module, label in ((SM, "store_mirror"), (OO, "oo_to_html")):
            tree = ast.parse(inspect.getsource(module))
            assert not [
                c for c in ast.walk(tree) if isinstance(c, ast.Call) and _callee_name(c) == PRUNE
            ], f"{label} 里有 {PRUNE} 调用"
            assert PRUNE not in _code_tokens(tree), f"{label} 的代码里引用了 {PRUNE}"

    def test_the_definition_lives_in_the_pure_function_module(self) -> None:
        """落点核对：定义在纯函数模块，**不在** `store_mirror`（design § 4.1 的红字要求）。"""
        assert AOP.prune_undeclared_rows.__module__.endswith("adopt_overwrite_plan")
        assert AOA.prune_undeclared_rows is AOP.prune_undeclared_rows, (
            "删除侧模块里的 prune 不是纯函数模块那一个 —— 同名不同源就是第二真源"
        )
        assert not hasattr(SM, PRUNE), "store_mirror 上挂了 prune —— design § 4.1 明令不得放进去"

    def test_text_scan_and_ast_scan_really_disagree(self) -> None:
        """🔴 反向对照（铁律 ㉖ 的实证）：文本口径与 AST 口径**必须**给出不同的数。

        两者相等时说明本仓恰好没有注释/字符串提及 —— 那时「用 AST 而不用文本」这条纪律在本域
        就是空话，判据要换个有区分力的形态。现算：生产口径下文本命中 10（NAME 3 / STRING 7）
        而 AST 真调用点 1。
        """
        text = _text_hits(_APP, PRUNE)
        total_text = sum(text.values())
        ast_calls = len(_ast_call_sites(_APP, PRUNE))
        assert total_text > ast_calls, (
            f"生产口径文本命中 {total_text} 条（分布 {text}）未多于 AST 调用点 {ast_calls} 条 —— "
            "本域失去「文本会骗人」的被测样本，J5 判据形态须重裁"
        )
        assert text.get("STRING", 0) >= 1, (
            f"生产代码里 {PRUNE} 的字符串/docstring 提及为 0（分布 {text}）—— "
            "同上：没有假命中样本时本反向判据空转"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §4 Task 7.4 —— 反向判据：路由清单守卫**不应**变化（Requirement 2.3）
#
# 🔴 方向是「保持原值」。不得写成「跟着 `SR.router.routes` 走」—— 那样新增一条路由时守卫
#    自动跟随、静默全绿，本判据的全部意义就没了。
# ═══════════════════════════════════════════════════════════════════════════════

#: 现算三处原值（本 spec 交付前后都应是这三个数）。
ROUTER_REQUIRED_ENDPOINTS = 14  # `_REQUIRED_ENDPOINTS` 元组长度
ROUTER_HANDLER_DENOMINATOR = "len(_REQUIRED_ENDPOINTS) + 5"  # handler 分母表达式（逐字）
ROUTER_SLASHED_SUFFIXES = 19  # `test_a_real_slashed_entry_id_routes` 的 `suffixes` 条数


def _router_test_tree() -> ast.Module:
    return ast.parse(_ROUTER_TEST_PY.read_text(encoding="utf-8"))


def _required_endpoints(tree: ast.Module) -> list[tuple[str, str]]:
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_REQUIRED_ENDPOINTS"
            and isinstance(node.value, ast.Tuple)
        ):
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]  # type: ignore[misc]
    raise AssertionError("_REQUIRED_ENDPOINTS 不在 test_task28_sync_router.py 顶层")


def _handler_denominator(tree: ast.Module) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assert)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "checked"
        ):
            found.append(ast.unparse(node.test.comparators[0]))
    return found


def _slashed_suffixes(tree: ast.Module) -> list[int]:
    found: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "suffixes"
            and isinstance(node.value, ast.List)
        ):
            found.append(len(node.value.elts))
    return found


def judge_router_census_unchanged(tree: ast.Module) -> list[str]:
    """三处分母逐个与原值比。返回违规清单（空 = 本 spec 没碰路由）。"""
    violations: list[str] = []
    required = _required_endpoints(tree)
    if len(required) != ROUTER_REQUIRED_ENDPOINTS:
        violations.append(
            f"_REQUIRED_ENDPOINTS 由 {ROUTER_REQUIRED_ENDPOINTS} 条变成 {len(required)} 条 —— "
            "本 spec 不新增路由（Requirement 2.3），改了就说明误加了端点"
        )
    denominators = _handler_denominator(tree)
    if denominators != [ROUTER_HANDLER_DENOMINATOR]:
        violations.append(
            f"handler 分母表达式由 [{ROUTER_HANDLER_DENOMINATOR!r}] 变成 {denominators} —— 同上"
        )
    suffixes = _slashed_suffixes(tree)
    if suffixes != [ROUTER_SLASHED_SUFFIXES]:
        violations.append(
            f"slashed suffixes 清单条数由 [{ROUTER_SLASHED_SUFFIXES}] 变成 {suffixes} —— 同上"
        )
    return violations


class TestTask74RouterCensusMustNotMove:
    def test_all_three_denominators_are_unchanged(self) -> None:
        assert judge_router_census_unchanged(_router_test_tree()) == []

    def test_adopt_substrate_is_already_in_the_route_list(self) -> None:
        """前提：`adopt-substrate` 是**上游** spec 加的既有路由，不是本 spec 新增。

        🔴 少了这一条，「三处不变」可能是因为本 spec 的端点压根没进清单（那才是真问题）。
        """
        tree = _router_test_tree()
        suffix_nodes = [
            ast.unparse(node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value == "/adopt-substrate"
        ]
        assert suffix_nodes, "路由清单里没有 /adopt-substrate —— 本 spec 的端点不在守卫视野内"

    def test_route_total_still_equals_the_slashed_suffix_table(self) -> None:
        """跨侧对账：真实路由数 == slashed suffixes 条数 == 原值。

        三个数相等才说明「路由没动」这句话在**实现侧**也成立，而不只是守卫文本没动。
        """
        from app.routers import wp_sync_router as SR

        assert len(SR.router.routes) == ROUTER_SLASHED_SUFFIXES == _slashed_suffixes(
            _router_test_tree()
        )[0]

    @pytest.mark.parametrize(
        ("label", "old", "new", "expect"),
        [
            (
                # 🔴 锚点取 `_REQUIRED_ENDPOINTS` 的**末项**而非首项：首项
                # `    ("POST", "/pending-mutations"),`（4 空格）是 slashed 清单里那行
                # （12 空格）的**子串** ⇒ `str.count` 得 2，唯一性守卫当场把它拦下来了。
                # 这正是「锚点必须断言 count==1」那条纪律抓到的实例，不是顺手改数迁就。
                "M1_extra_required_endpoint",
                '    ("POST", "/versions/{version_id}/rollback"),',
                '    ("POST", "/versions/{version_id}/rollback"),\n    ("POST", "/aos-fake-route"),',
                "_REQUIRED_ENDPOINTS",
            ),
            (
                "M2_bumped_handler_denominator",
                "len(_REQUIRED_ENDPOINTS) + 5",
                "len(_REQUIRED_ENDPOINTS) + 6",
                "handler 分母",
            ),
            (
                "M3_extra_slashed_suffix",
                '            ("GET", "/store-projection"),',
                '            ("GET", "/store-projection"),\n            ("POST", "/aos-fake"),',
                "slashed suffixes",
            ),
        ],
    )
    def test_mutant_pretending_to_add_a_route_is_caught(
        self, label: str, old: str, new: str, expect: str
    ) -> None:
        """变异反证 M1~M3：假装新增一个路由（三处各改一处）⇒ 判据必须打红且点名那一处。

        🔴 变异在**读进来的源码字符串**上做，`test_task28_sync_router.py` 一字不改
        （它的期望值正是本判据要防止被改的东西）。
        """
        src = _ROUTER_TEST_PY.read_text(encoding="utf-8")
        assert src.count(old) == 1, (
            f"{label} 的锚点 {old!r} 命中 {src.count(old)} 次（须恰 1）—— 命中 0 次时 replace "
            "静默空操作，变异体等于原文、红一次都打不出还全绿"
        )
        got = judge_router_census_unchanged(ast.parse(src.replace(old, new)))
        assert len(got) == 1 and expect in got[0], f"{label} 实得 {got}"
