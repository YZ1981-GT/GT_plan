# Feature: procedure-trimming-and-delegation-intelligence — Task 23（零回归验证）
"""Task 23 零回归判据的后端守卫（Requirements 14.1 / 14.2 / 14.6）。

Task 23 有五条零回归判据。本文件承担**其中三条的后端侧**，另两条在别处已有承重守卫、
本文件只加「证据锚」（防它们被后续会话删掉而缺口无人察觉）：

| 判据 | 承重位置 | 本文件做什么 |
|---|---|---|
| (a) `no_data` 自动裁集合与改造前逐条一致 | 前端 `trimNoDataZeroRegression.spec.ts`（决策内核是 TS） | 只钉死**唯一分歧输入类不可达**（见 :class:`TestMandatoryDivergenceUnreachable`） |
| (b) canonical 未带 `reason_code` 时 payload 逐字节不变 | 同目录 `test_trim_reason_code_contract.py::TestAdditiveZeroRegression` | 证据锚 + 独立复算一次真实归一结果 |
| (c) 委派 preview / apply 对外契约字段逐字段不变 | **本文件** :class:`TestDelegationContractFrozen` | 冻结字段集 + HEAD 侧交叉佐证 |
| (d) `load_b50_accounts` 既有三类键逐字节相同 | 同目录 `test_b50_reader_extension.py`（Task 1 冻结快照） | 证据锚 + 按路径 import 兄弟模块**独立复算**一次 |
| (e) 既有附注同步链路输出逐字节不变 | Task 21 的 `test_note_linkage_single_source.py`（51 例） | **本文件**钉死既有链路源码与 HEAD 逐字节相同 + 联动为纯新增 |

## 🔴 为什么 (c) 只能这样验，不能"跑一遍比一遍"

`preview` / `apply` 都要真实 DB（行锁 `FOR UPDATE` + 一次性凭证 + append-only history
触发器），而真实库 `procedure_row_tasks` 仅 3 个项目 157 行、`procedure_instances`
**0 条已裁剪**。既有 `test_procedure_delegation_characterization.py` 在 sqlite 下因
`project_users` / `staff_members` / `wp_visibility_policy_epoch` 缺表而恒 404（Wave 3
已定性为预存在失败）。故"对外契约字段"这一层只能落在**响应字典的键集**上：

1. **主判据**（恒执行）= 冻结的字段集常量与源码 AST 抽出的键集**精确相等**。
   多一个键（未登记的 additive）或少一个键（破契约）都打红。
2. **佐证**（git 不可用时 skip 并写明理由）= 同一抽取器施加于 `git show HEAD:` 的
   同一文件，两侧键集必须相等 —— 这才是"逐字段不变"的直接证据。
   ⚠️ 这里 `git show` **只用于读取一份文本做比对**，不是把工作树文件换成 HEAD 版再跑
   同一组测试（后者被 tasks.md 明令禁止：本仓库并发度高，HEAD 侧可能含他人未提交
   成果，且被中断时 HEAD 版会留在工作树）。

## 🔴 键集用 AST 抽，不用正则

`preview` 的返回字典**嵌套三层**（`summary` / `membership_load` /
`affected_workpapers` / `target_versions` 里的元素字典），`apply` 的返回字典在**嵌套
函数** `_apply_fn` 里。正则会把注释里的 `"xxx":` 一起数进来，也数不清嵌套归属。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

# 🔴 有意不在模块顶层 import 生产模块：顶层 import 失败会让整个文件 collection error、
# 零断言执行，那时"全红"既可能是功能没做也可能是守卫自己写坏。

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_REPO = _BACKEND.parent

DELEGATION_SVC_REL = "backend/app/services/procedure_delegation_service.py"
DELEGATION_SVC = _REPO / DELEGATION_SVC_REL
PROC_SVC = _BACKEND / "app" / "services" / "procedure_service.py"
PROC_MODELS = _BACKEND / "app" / "models" / "procedure_models.py"
SIB_B50 = _HERE.parent / "test_b50_reader_extension.py"
SIB_REASON = _HERE.parent / "test_trim_reason_code_contract.py"

# ═══════════════════════════════════════════════════════════════════════════
# 冻结基线：委派 preview / apply 的对外契约字段（R14.1）
#
# 取值来源 = 改造前（HEAD）与改造后（工作树）**逐字段相同**的实测结果，2026-08-11。
# 新增字段属 additive，**必须同时登记在此**，否则本守卫打红 —— 这正是它的作用：
# 让"悄悄多下发一个键"和"悄悄少下发一个键"都必须经过一次显式登记。
# ═══════════════════════════════════════════════════════════════════════════
PREVIEW_TOP_KEYS = frozenset({
    "status",
    "preview_id",
    "expires_at",
    "summary",
    "conflict_task_ids",
    "membership_load",
    "affected_workpapers",
    "target_versions",
})
PREVIEW_SUMMARY_KEYS = frozenset({
    "targets",
    "would_assign",
    "would_reassign",
    "would_reviewer_update",
    "unchanged",
    "conflict",
    "terminal",
    "skipped_assigned",
    "already_assigned",
    "in_progress",
    "submitted",
})
PREVIEW_MEMBERSHIP_LOAD_KEYS = frozenset({"assignee_staff_id", "active_task_count"})
PREVIEW_AFFECTED_WP_KEYS = frozenset({"wp_index_ids", "wp_ids"})
PREVIEW_TARGET_VERSION_KEYS = frozenset({"task_id", "lock_version", "assignment_version"})

APPLY_KEYS = frozenset({
    "delegation_batch_id",
    "applied",
    "unchanged",
    "failed",
    "conflict",
    "terminal",
    "skipped_assigned",
    "best_effort",
    "per_task",
})

# 附注同步链路的**既有**模块（本 spec 的 Task 21 联动为纯新增，不得改它们）。
NOTE_CHAIN_FILES = (
    "backend/app/services/note_content_utils.py",
    "backend/app/services/disclosure_engine.py",
    "backend/app/services/note_word_exporter.py",
    "backend/app/services/note_word_dynamic_styles.py",
    "backend/app/services/note_trim_service.py",
    "backend/app/services/note_is_empty_calc.py",
    "backend/app/services/note_empty_table_detector.py",
    "backend/app/services/wp_note_linkage_service.py",
    "backend/app/services/note_readiness_service.py",
    "backend/app/services/disclosure_stale_marker.py",
)
NOTE_LINKAGE_NEW = "backend/app/services/procedure_trim_note_linkage.py"


# ═══════════════════════════════════════════════════════════════════════════
# helper
# ═══════════════════════════════════════════════════════════════════════════
def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _git_show(rel: str) -> str | None:
    """读 HEAD 版文本；git 不可用或路径不在 HEAD 时返回 None（**不**换工作树文件）。"""
    try:
        proc = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=str(_REPO), capture_output=True, timeout=60,
        )
    except Exception:  # noqa: BLE001
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def _find_func(tree: ast.AST, name: str, *, within: ast.AST | None = None) -> ast.AST | None:
    """按名字找 (async) 函数定义；`within` 非空时只在该子树里找（用于嵌套函数）。"""
    scope = within if within is not None else tree
    for node in ast.walk(scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            if within is not None and node is within:
                continue
            return node
    return None


def _return_dicts(func: ast.AST) -> list[ast.Dict]:
    """该函数体内**直属**的 `return {...}` 字典字面量（跳过嵌套函数的 return）。"""
    inner = {
        n for sub in ast.walk(func)
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not func
        for n in ast.walk(sub)
    }
    out: list[ast.Dict] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and node not in inner and isinstance(node.value, ast.Dict):
            out.append(node.value)
    return out


def _keys(d: ast.Dict) -> set[str]:
    return {k.value for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _sub_dict(d: ast.Dict, key: str) -> ast.Dict | None:
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Dict):
            return v
    return None


def _list_elem_dict(d: ast.Dict, key: str) -> ast.Dict | None:
    """取 `key` 对应的列表/推导式里的元素字典（`target_versions` 是列表推导式）。"""
    for k, v in zip(d.keys, d.values):
        if not (isinstance(k, ast.Constant) and k.value == key):
            continue
        if isinstance(v, ast.ListComp) and isinstance(v.elt, ast.Dict):
            return v.elt
        if isinstance(v, ast.List) and v.elts and isinstance(v.elts[0], ast.Dict):
            return v.elts[0]
    return None


def _preview_dict(src: str) -> ast.Dict:
    tree = ast.parse(src)
    fn = _find_func(tree, "preview")
    assert fn is not None, "未找到 `preview` 函数定义 —— 扫描面失效"
    dicts = _return_dicts(fn)
    assert len(dicts) == 1, f"`preview` 直属 return 字典字面量数 = {len(dicts)}，期望 1"
    return dicts[0]


def _apply_dict(src: str) -> ast.Dict:
    tree = ast.parse(src)
    outer = _find_func(tree, "apply")
    assert outer is not None, "未找到 `apply` 函数定义 —— 扫描面失效"
    inner = _find_func(tree, "_apply_fn", within=outer)
    assert inner is not None, (
        "未在 `apply` 内找到嵌套 `_apply_fn` —— apply 的对外契约就在它的 return 字典里"
        "（`consume_and_apply` 原样返回 `apply_fn` 结果，不重塑键集）"
    )
    dicts = _return_dicts(inner)
    assert len(dicts) == 1, f"`_apply_fn` 直属 return 字典字面量数 = {len(dicts)}，期望 1"
    return dicts[0]


def _load_sibling(path: Path, name: str):
    """按文件路径加载兄弟守卫模块（复用其冻结快照，**不抄第二份**）。

    抄一份会让「快照被改」与「实现回归」不可区分 —— 两边各自全绿。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法为 {path.name} 建 import spec"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# helper 自检（判据的扫描面必须真的命中，否则红/绿都不可信）
# ═══════════════════════════════════════════════════════════════════════════
class TestHelperSelfCheck:
    def test_return_dicts_skips_nested_function_returns(self):
        src = (
            "def outer():\n"
            "    def inner():\n"
            "        return {'inner_key': 1}\n"
            "    return {'outer_key': 2}\n"
        )
        fn = _find_func(ast.parse(src), "outer")
        got = [_keys(d) for d in _return_dicts(fn)]
        assert got == [{"outer_key"}], f"嵌套函数的 return 被算进直属集合: {got}"

    def test_find_func_locates_nested_by_scope(self):
        src = (
            "async def apply():\n"
            "    async def _apply_fn(db, p):\n"
            "        return {'a': 1}\n"
            "    return await run(_apply_fn)\n"
        )
        tree = ast.parse(src)
        outer = _find_func(tree, "apply")
        inner = _find_func(tree, "_apply_fn", within=outer)
        assert inner is not None and inner.name == "_apply_fn"
        assert _keys(_return_dicts(inner)[0]) == {"a"}

    def test_keys_ignores_non_string_and_comments(self):
        d = ast.parse("x = {'a': 1, 2: 'b', **rest}").body[0].value
        assert _keys(d) == {"a"}, "非字符串键或 ** 展开被误算成字段名"

    def test_list_elem_dict_handles_comprehension(self):
        d = ast.parse("x = {'tv': [{'task_id': i} for i in xs]}").body[0].value
        elem = _list_elem_dict(d, "tv")
        assert elem is not None and _keys(elem) == {"task_id"}

    def test_scan_surface_is_not_empty(self):
        """扫描面非空自检：目标文件存在且够长（防路径写错导致断言在空文本上求值）。"""
        assert DELEGATION_SVC.exists(), f"缺文件: {DELEGATION_SVC}"
        assert len(_read(DELEGATION_SVC)) > 20000, "委派服务源码过短，扫描面可疑"

    def test_git_show_helper_returns_none_for_absent_path(self):
        """反向自检：`_git_show` 对不存在的路径返回 None 而不是空串或抛异常。

        没有这条，git 不可用时 HEAD 佐证会以「两侧都是空集、相等」的形态**假绿**。
        """
        assert _git_show("backend/app/services/__t23_definitely_absent__.py") is None


# ═══════════════════════════════════════════════════════════════════════════
# (c) 委派 preview / apply 对外契约字段逐字段不变（R14.1）
# ═══════════════════════════════════════════════════════════════════════════
class TestDelegationContractFrozen:
    """主判据：工作树键集 == 冻结基线（精确相等，多一个少一个都红）。"""

    def test_preview_top_level_keys_frozen(self):
        got = _keys(_preview_dict(_read(DELEGATION_SVC)))
        assert got == set(PREVIEW_TOP_KEYS), (
            f"委派 preview 顶层字段集已变：多出 {sorted(got - PREVIEW_TOP_KEYS)}，"
            f"少了 {sorted(PREVIEW_TOP_KEYS - got)}。"
            "新增字段属 additive 但**必须登记**在 PREVIEW_TOP_KEYS；"
            "少字段即破 R14.1 对外契约（前端读不到会显示成「—」或恒 0）"
        )

    @pytest.mark.parametrize(
        ("sub", "expected"),
        [
            ("summary", PREVIEW_SUMMARY_KEYS),
            ("membership_load", PREVIEW_MEMBERSHIP_LOAD_KEYS),
            ("affected_workpapers", PREVIEW_AFFECTED_WP_KEYS),
        ],
    )
    def test_preview_nested_keys_frozen(self, sub, expected):
        d = _sub_dict(_preview_dict(_read(DELEGATION_SVC)), sub)
        assert d is not None, f"preview 返回里未找到嵌套字典 `{sub}`"
        got = _keys(d)
        assert got == set(expected), (
            f"preview.{sub} 字段集已变：多出 {sorted(got - set(expected))}，"
            f"少了 {sorted(set(expected) - got)}"
        )

    def test_preview_target_version_element_keys_frozen(self):
        elem = _list_elem_dict(_preview_dict(_read(DELEGATION_SVC)), "target_versions")
        assert elem is not None, "preview.target_versions 不是元素为字典的列表/推导式"
        assert _keys(elem) == set(PREVIEW_TARGET_VERSION_KEYS)

    def test_apply_keys_frozen(self):
        got = _keys(_apply_dict(_read(DELEGATION_SVC)))
        assert got == set(APPLY_KEYS), (
            f"委派 apply 字段集已变：多出 {sorted(got - APPLY_KEYS)}，"
            f"少了 {sorted(APPLY_KEYS - got)}"
        )

    def test_consume_and_apply_returns_apply_fn_result_verbatim(self):
        """apply 的契约落在 `_apply_fn` 的 return 上，前提是外层不重塑键集。

        若 `consume_and_apply` 改成 `return {**result, ...}`，本文件冻结的 APPLY_KEYS
        就不再等于真实响应 —— 那时守卫会以「全绿」的形态失去意义。
        """
        p = _BACKEND / "app" / "services" / "procedure_operation_preview.py"
        assert p.exists(), f"缺文件: {p}"
        fn = _find_func(ast.parse(_read(p)), "consume_and_apply")
        assert fn is not None, "未找到 consume_and_apply —— 扫描面失效"
        assert not _return_dicts(fn), (
            "`consume_and_apply` 直属 return 里出现了字典字面量 —— 它可能在重塑 apply "
            "的响应键集，本文件冻结的 APPLY_KEYS 将不再等于真实对外契约"
        )
        returns = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Return) and n.value is not None
        ]
        exprs = [ast.unparse(n.value) for n in returns]
        assert "result" in exprs, (
            f"`consume_and_apply` 未原样返回 `result`（实得 {exprs}）"
        )

    def test_head_side_keys_equal_worktree(self):
        """🔴 直接证据：同一抽取器施加于 HEAD 版文本，两侧键集必须相等。

        这才是「逐字段不变」而不只是「与我写下的常量一致」。
        git 不可用时 skip 并写明理由（主判据仍恒执行）。
        """
        head = _git_show(DELEGATION_SVC_REL)
        if head is None:
            pytest.skip(
                "git show 不可用或该路径不在 HEAD —— HEAD 侧交叉佐证暂不可验证。"
                "⚠️ 不等于契约没变：主判据（冻结常量比对）仍在本类其余用例中执行。"
            )
        wt = _read(DELEGATION_SVC)
        assert _keys(_preview_dict(head)) == _keys(_preview_dict(wt)), (
            "preview 顶层字段集在 HEAD 与工作树之间不同 —— 本 spec 改动了委派对外契约"
        )
        assert _keys(_apply_dict(head)) == _keys(_apply_dict(wt)), (
            "apply 字段集在 HEAD 与工作树之间不同 —— 本 spec 改动了委派对外契约"
        )
        for sub in ("summary", "membership_load", "affected_workpapers"):
            h, w = _sub_dict(_preview_dict(head), sub), _sub_dict(_preview_dict(wt), sub)
            assert h is not None and w is not None, f"HEAD 或工作树缺 preview.{sub}"
            assert _keys(h) == _keys(w), f"preview.{sub} 字段集与 HEAD 不同"

    def test_head_comparison_is_not_vacuous(self):
        """反向自检：上一条不是在空文本上比空集。"""
        head = _git_show(DELEGATION_SVC_REL)
        if head is None:
            pytest.skip("git show 不可用（同上）")
        assert len(head) > 20000, "HEAD 版文本过短，交叉佐证的扫描面可疑"
        assert len(_keys(_preview_dict(head))) >= 8, "HEAD 侧抽出的字段过少，抽取器可疑"

    def test_new_delegation_output_is_additive_only(self):
        """Wave 3 只**新增**了 `member_workloads`，preview/apply 一字未动。

        源码级断言：`member_workloads` 存在（新增能力在册），且它不是 preview/apply
        的嵌套函数（不改两者的返回形态）。
        """
        tree = ast.parse(_read(DELEGATION_SVC))
        mw = _find_func(tree, "member_workloads")
        assert mw is not None, (
            "缺 `member_workloads` —— Wave 3 的负载单一真源不在了，"
            "前端会退回自算负载（口径与后端「非终态任务数」不同）"
        )
        for host in ("preview", "apply"):
            outer = _find_func(tree, host)
            assert _find_func(tree, "member_workloads", within=outer) is None, (
                f"`member_workloads` 被塞进 `{host}` 内部 —— 新增能力不再是 additive"
            )


# ═══════════════════════════════════════════════════════════════════════════
# (a) 支撑：改造前/后唯一分歧输入类不可达
# ═══════════════════════════════════════════════════════════════════════════
class TestMandatoryDivergenceUnreachable:
    """`no_data` 集合等价的唯一例外是 `is_mandatory=true`，而它在真实载荷里不存在。

    改造前 `decide()` 读 `p.is_mandatory`（`ProcedureInstance` 无该列 ⇒ 恒 undefined ⇒
    该判据一直是死的）；落地后 `buildAndDecide` 如实硬传 `false`。两者只在
    「载荷里真有 `is_mandatory: true`」这一输入类上不同 —— 本类证明该输入类**不可达**，
    故 (a) 的集合等价在真实输入空间内成立。

    🔴 这条必须钉死：若哪天有人给 `_to_dict` 补上 `is_mandatory`（不管取值从哪来），
    前端 characterization 的「等价」结论就不再覆盖真实输入，而它不会自己变红。
    """

    def test_orm_has_no_is_mandatory_column(self):
        src = _read(PROC_MODELS)
        i = src.index("class ProcedureInstance")
        nxt = src.find("\nclass ", i + 1)
        body = src[i:] if nxt < 0 else src[i:nxt]
        assert len(body) > 500, "ProcedureInstance 类体过短，扫描面可疑"
        assert "__tablename__" in body, "未截到含表名声明的类体"
        assert not re.search(r"^\s+is_mandatory\s*:", body, re.M), (
            "`ProcedureInstance` 出现了 `is_mandatory` 列 —— 前端 no_data 零回归"
            "characterization 的「唯一分歧输入类不可达」前提失效，须重做集合等价验证"
        )

    def test_to_dict_does_not_emit_is_mandatory(self):
        try:
            from app.services.procedure_service import ProcedureService
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"无法导入 ProcedureService: {exc!r}")
        import inspect

        code = inspect.getsource(ProcedureService._to_dict)
        # 剥注释后再判 —— 生产代码刻意在注释里写明「有意不下发 is_mandatory」的成因
        clean = "\n".join(
            re.sub(r"#.*$", "", ln) for ln in code.splitlines()
        )
        assert "is_mandatory" in code, (
            "生产代码里连注释都不再提 `is_mandatory` —— 那段成因说明是本判据的"
            "上下文，删掉后续会话会重新提议补该键"
        )
        assert '"is_mandatory"' not in clean, (
            "`_to_dict` 下发了 `is_mandatory` —— `procedure_instances` 无该列，"
            "凭空补键等于伪造一个数据库里不存在的判据"
        )

    def test_reverse_check_strip_comments_is_load_bearing(self):
        """反向自检：不剥注释时 `is_mandatory` 必然命中（证明剥这一步承重）。"""
        import inspect

        from app.services.procedure_service import ProcedureService

        raw = inspect.getsource(ProcedureService._to_dict)
        assert "is_mandatory" in raw, "原文未提及 —— 上一条的剥注释断言在空转"


# ═══════════════════════════════════════════════════════════════════════════
# (b) / (d) 证据锚 + 独立复算
# ═══════════════════════════════════════════════════════════════════════════
class TestZeroRegressionEvidenceAnchors:
    """判据 (b) / (d) 的承重守卫在兄弟文件里；本类保证它们不会静默消失。

    只写「见另一文件」是不够的：那份文件被删或那个类被改名后，Task 23 的判据就
    只剩一句交付实录里的话。故此处按**名字 + 真跑一次**双向锚定。
    """

    def test_criterion_b_guard_class_exists(self):
        src = _read(SIB_REASON)
        assert "class TestAdditiveZeroRegression" in src, (
            "判据 (b) 的承重守卫 `TestAdditiveZeroRegression` 不在了 —— "
            "canonical payload additive 零回归失去唯一证据"
        )
        assert "test_real_normalize_entry_payload_unchanged_without_reason_code" in src, (
            "判据 (b) 的**真跑**用例不在了（只剩源码级断言时，"
            "「条件写入写对了但运行结果不对」会漏掉）"
        )

    def test_criterion_b_independent_recompute(self):
        """独立复算：不传 `reason_code` 时归一键集恰为扩展前的五键 + canonical key。

        与兄弟文件同结论但**独立构造入参**（不 import 它的常量）—— 两处同时红才说明
        是实现回归，只有一处红说明是那处的判据或样本问题。
        """
        try:
            from app.services.procedure_trim_service import ProcedureTrimService
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"无法导入 ProcedureTrimService: {exc!r}")

        legacy_entry = {
            "kind": "scope",
            "cycle": "L",
            "wp_index_code": "L2-1",
            "target_status": "not_applicable",
            "skip_reason": "本期无该类交易",
        }
        out = ProcedureTrimService._normalize_entry(dict(legacy_entry))
        assert "reason_code" not in out, (
            f"未携带 `reason_code` 的存量 entry 归一后多出该键（实得 {sorted(out)}）"
            " ⇒ canonical payload 字节形态变了 ⇒ 在途 preview 凭证全部 409（R8.9）"
        )
        assert set(out) == {
            "kind", "key", "cycle", "wp_index_code", "target_status", "skip_reason",
        }, f"存量 entry 归一键集漂移: {sorted(out)}"

        # 反向：携带时必须进 payload（否则 preview 与 apply 两侧 payload 不一致 → 409）
        with_code = {**legacy_entry, "reason_code": "below_trivial"}
        out2 = ProcedureTrimService._normalize_entry(dict(with_code))
        assert out2.get("reason_code") == "below_trivial", (
            "携带 `reason_code` 时未进归一结果 —— 上一条断言会在「该字段压根没接」的"
            "实现上恒绿（假绿）"
        )

    def test_criterion_d_guard_and_snapshot_exist(self):
        src = _read(SIB_B50)
        for name in ("_LEGACY_ROWS", "_LEGACY_EXPECTED",
                     "test_legacy_three_key_families_output_frozen"):
            assert name in src, (
                f"判据 (d) 的冻结快照要素 `{name}` 不在了 —— "
                "`load_b50_accounts` 既有三类键的零回归失去基线"
            )

    def test_criterion_d_independent_recompute_with_frozen_snapshot(self):
        """按路径 import 兄弟模块，用**它冻结的**快照独立复算一次（Task 14 范式）。"""
        sib = _load_sibling(SIB_B50, "_t23_sib_b50_reader_extension")
        for name in ("_LEGACY_ROWS", "_LEGACY_EXPECTED", "_load", "_by_account"):
            assert hasattr(sib, name), f"兄弟守卫模块缺 `{name}`，快照复用失败"
        got = sib._by_account(sib._load(list(sib._LEGACY_ROWS)))
        assert set(got) == set(sib._LEGACY_EXPECTED), (
            f"既有三类键的科目集合漂移: {sorted(got)}"
        )
        for name, exp in sib._LEGACY_EXPECTED.items():
            for key, val in exp.items():
                assert got[name][key] == val, (
                    f"{name}.{key}: 期望 {val!r} 实得 {got[name][key]!r} —— "
                    "Task 2 的 additive 扩展改动了既有三类键的解析结果"
                )

    def test_criterion_d_recompute_is_not_vacuous(self):
        """反向自检：往快照里注入一条矩阵行必须让上一条的比对察觉差异。

        没有它，若 `_load` 哪天恒返空列表，上一条会以「两侧都空、相等」假绿。
        """
        sib = _load_sibling(SIB_B50, "_t23_sib_b50_reader_extension")
        baseline = sib._by_account(sib._load(list(sib._LEGACY_ROWS)))
        polluted = sib._by_account(sib._load(list(sib._LEGACY_ROWS) + [
            sib._row("B50-T3-matrix-应收账款-existence-RMM", conclusion="H"),
        ]))
        assert baseline, "基线为空 —— 复算判据在空输入上求值"
        assert baseline["应收账款"]["cells"]["existence"]["rmm"] != \
            polluted["应收账款"]["cells"]["existence"]["rmm"], (
            "注入不同取值的矩阵行后输出未变 —— 深比对失效（会在任何回归上恒绿）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# (e) 既有附注同步链路输出逐字节不变
# ═══════════════════════════════════════════════════════════════════════════
class TestNoteChainUnchanged:
    """本 spec 的附注联动是**纯新增模块**，既有链路一字未改。

    判据取源码字节（行尾归一后）与 HEAD 相等 —— 比"跑一遍看输出"更强：输出相同
    可能是测试面没覆盖到改动，源码字节相同则连未覆盖路径也不可能变。
    """

    @pytest.mark.parametrize("rel", NOTE_CHAIN_FILES)
    def test_existing_chain_file_bytes_equal_head(self, rel):
        p = _REPO / rel
        assert p.exists(), f"既有附注链路文件缺失: {rel}"
        head = _git_show(rel)
        if head is None:
            pytest.skip(
                f"git show 不可用或 {rel} 不在 HEAD —— 该文件的字节级对照暂不可验证。"
                "⚠️ 不等于它没变。"
            )
        wt = p.read_text(encoding="utf-8")
        assert wt.replace("\r\n", "\n") == head.replace("\r\n", "\n"), (
            f"{rel} 与 HEAD 不同 —— 既有附注同步链路被改动（R13.5 要求联动为加法式，"
            "既有链路输出逐字节不变）。若确为并发 spec 的改动，需在此如实登记并"
            "重新评估本 spec 的附注零回归结论"
        )

    def test_linkage_module_is_new_not_a_rewrite(self):
        """联动模块在 HEAD 里不存在 ⇒ 结构上不可能改变既有链路的任何输出。"""
        p = _REPO / NOTE_LINKAGE_NEW
        assert p.exists(), f"联动模块缺失: {NOTE_LINKAGE_NEW}"
        assert _git_show(NOTE_LINKAGE_NEW) is None, (
            "`procedure_trim_note_linkage.py` 已在 HEAD 中 —— 本判据的「纯新增」"
            "前提失效，需改为与 HEAD 版逐字节对照"
        )

    def test_chain_file_list_is_not_empty_and_paths_are_real(self):
        """扫描面自检：清单非空且每条都真实存在（防路径写错导致参数化空转）。"""
        assert len(NOTE_CHAIN_FILES) >= 8, "既有链路清单过短，覆盖面可疑"
        missing = [r for r in NOTE_CHAIN_FILES if not (_REPO / r).exists()]
        assert not missing, f"清单里有不存在的路径（判据会空转）: {missing}"
