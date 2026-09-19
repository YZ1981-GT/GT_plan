"""Wave 6 守卫：自定义底稿批量创建 + 预览。

spec: .kiro/specs/custom-workpaper-dual-mode-formula-and-batch/
  Task 19（批量创建端点）/ Task 28（预览端点）/ Task 22（本守卫）

覆盖 Property：
  11 预览只读（调用前后 wp_index / working_paper 行数不变）
  12 零回归（单条端点响应形状未变 + 批量与单条共用创建逻辑）

🔴 判据设计（平台既有铁律，逐条都踩过）：
  - 读源码前必 `stripPyComments()`，否则注释里解释「为什么要 savepoint」的文字
    会被数成真实调用 ⇒「savepoint 被删」这个核心变异静默逃逸
  - 断言「某校验/门控存在」判据必须是**条件表达式形态**而非其中出现的标识符
    （`if False and ...` 会让「标识符仍在」的弱判据通过）
  - 函数体截取按**圆括号配对跳参数列表 + 行缩进**，不用固定字符窗口
    （`\\s*` 在 re.M 下含换行会从空行起匹配，把函数体截成空串）
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent

TPL_REL = "backend/app/routers/wp_template.py"


def _read(rel: str) -> str:
    p = _REPO / rel
    assert p.exists(), f"判据文件缺失（守卫失效）: {rel}"
    txt = p.read_text(encoding="utf-8")
    assert txt.strip(), f"判据文件为空（守卫失效）: {rel}"
    return txt


def _strip_py_comments(src: str) -> str:
    """剥 docstring 与 `#` 注释。

    🔴 本 spec 的生产代码注释里大量引用被要求/被禁的符号名（解释 savepoint、
    三态、只读理由），不剥会让说明文字被数成真实调用。

    🔴 必须做**引号状态跟踪**：裸 `#.*$` 会把 `accept="image/*"` / `"keep#me"`
    这类字符串里的 `#` 当注释起点，把该行剩余内容一起吃掉 ⇒ 真实调用被截掉
    = 假绿（平台已实证「正则剥块注释被 MIME 通配骗过」同族）。
    """
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    out_lines: list[str] = []
    for line in src.splitlines():
        quote: str | None = None
        cut = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in ("'", '"'):
                quote = ch
            elif ch == "#":
                cut = i
                break
            i += 1
        out_lines.append(line[:cut])
    return "\n".join(out_lines)


def _func_body(src: str, name: str, *, min_len: int = 40) -> str:
    """截 `def name(` / `async def name(` 的函数体（配对跳参数列表 + 缩进收尾）。"""
    m = re.search(rf"(?m)^([ \t]*)(?:async\s+)?def\s+{re.escape(name)}\s*\(", src)
    assert m, f"未找到函数 {name}（守卫判据失效）"
    indent = len(m.group(1))
    i = src.index("(", m.end() - 1)
    depth = 0
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    assert depth == 0, f"{name} 参数列表括号不配对"
    lines = src[i:].splitlines()
    body = []
    for ln in lines[1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        body.append(ln)
    out = "\n".join(body)
    assert len(out) >= min_len, f"{name} 函数体过短（截取失败）"
    return out


def _loop_body(src: str, fn: str) -> str:
    """截函数内 `for item in ...:` 的循环体（per-item 判据只看这一段）。

    🔴 判「循环体内不得 raise」不能拿整个函数体判 —— 函数开头的入参守卫
    （超限 422）本就该 raise，会让判据假红。
    """
    body = _func_body(src, fn)
    m = re.search(r"(?m)^([ \t]*)for\s+\w+\s+in\s+", body)
    assert m, f"{fn} 未找到 for 循环（判据失效）"
    indent = len(m.group(1))
    lines = body[m.start():].splitlines()
    out = []
    for ln in lines[1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        out.append(ln)
    joined = "\n".join(out)
    assert len(joined) > 80, f"{fn} 循环体过短（截取失败）"
    return joined


# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfCheck:
    """判据自检：剥注释与截函数体必须真的有效，否则下面全是空转。"""

    def test_strip_comments_works(self):
        sample = 'def f():\n    """doc begin_nested"""\n    x = 1  # begin_nested\n    s = "keep#me"'
        cleaned = _strip_py_comments(sample)
        assert "begin_nested" not in cleaned
        assert "keep#me" in cleaned

    def test_read_raises_on_missing(self):
        with pytest.raises(AssertionError, match="判据文件缺失"):
            _read("backend/__no_such__.py")

    def test_func_body_skips_multiline_params(self):
        sample = (
            "async def outer(\n    a: int,\n    b: int,\n) -> None:\n"
            "    return a + b\n\n"
            "def other():\n    return 0\n"
        )
        body = _func_body(sample, "outer", min_len=1)
        assert "return a + b" in body
        assert "return 0" not in body, "函数体越界到了下一个函数"

    def test_loop_body_excludes_preamble(self):
        """反向自检：循环体截取不得含函数开头的入参守卫。"""
        sample = (
            "async def f(items):\n"
            "    if len(items) > 3:\n"
            "        raise HTTPException(status_code=422, detail='too many items here')\n"
            "    out = []\n"
            "    for item in items:\n"
            "        try:\n"
            "            out.append(item)\n"
            "        except Exception as e:\n"
            "            out.append(('bad', e))\n"
            "    return out\n"
        )
        loop = _loop_body(sample, "f")
        assert "out.append(item)" in loop
        assert "HTTPException" not in loop, "循环体截取吞进了函数开头的入参守卫"

    def test_weak_criterion_contrast(self):
        """证明「只断言标识符出现」抓不住条件短路 —— 故下面用条件形态判据。"""
        good = "if len(items) > MAX_BATCH_ITEMS:"
        mutated = "if False:  # MAX_BATCH_ITEMS 仍在文本里"
        assert "MAX_BATCH_ITEMS" in good and "MAX_BATCH_ITEMS" in mutated
        shape = re.compile(r"if\s+len\(\s*\w+\s*\)\s*>\s*MAX_BATCH_ITEMS\s*:")
        assert shape.search(good) and not shape.search(_strip_py_comments(mutated))


# ════════════════════════════════════════════════════════════════════════════
class TestSharedCreationLogic:
    """R8.7 / R8.9 交叉锁死：批量与单条**共用** `_create_one_custom_workpaper`。

    🔴 变异「批量另写一份创建逻辑」必须打红 —— 两份实现会漂移（平台已实证
    「未完成的重构」缺陷模式：A 保留作入口却没真的委托 B）。
    """

    def test_shared_helper_exists(self):
        src = _strip_py_comments(_read(TPL_REL))
        assert re.search(r"async def _create_one_custom_workpaper\s*\(", src)

    @pytest.mark.parametrize(
        "fn", ["create_custom_workpaper", "create_custom_workpaper_batch"]
    )
    def test_both_endpoints_delegate(self, fn):
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, fn)
        assert "_create_one_custom_workpaper(" in body, (
            f"{fn} 未委托共享创建函数 ⇒ 两份实现会漂移"
        )

    @pytest.mark.parametrize(
        "fn", ["create_custom_workpaper", "create_custom_workpaper_batch"]
    )
    def test_endpoints_do_not_construct_models_themselves(self, fn):
        """端点自己不得 new WpIndex/WorkingPaper —— 那就是第二份实现。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, fn)
        assert "WpIndex(" not in body, f"{fn} 自行构造 WpIndex ⇒ 绕过共享逻辑"
        assert "WorkingPaper(" not in body, f"{fn} 自行构造 WorkingPaper ⇒ 绕过共享逻辑"

    def test_shared_helper_actually_creates(self):
        """反向自检：共享函数里确实有创建动作（否则上面三条是空转）。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "_create_one_custom_workpaper")
        assert "WpIndex(" in body and "WorkingPaper(" in body
        assert "refresh_custom_projection(" in body, "共享创建必须投影（否则网格空态）"


# ════════════════════════════════════════════════════════════════════════════
class TestPerItemSavepoint:
    """R8.6：per-item savepoint —— 一条失败其余仍创建。"""

    def test_begin_nested_present_in_batch(self):
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "create_custom_workpaper_batch")
        assert "begin_nested()" in body, (
            "批量缺 per-item savepoint ⇒ 一条失败整批回滚"
        )

    def test_single_commit_at_outermost(self):
        """最外层只 commit 一次（per-item commit 会让部分成功不可回滚）。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "create_custom_workpaper_batch")
        assert body.count("await db.commit()") == 1, (
            "批量应最外层一次 commit"
        )

    def test_per_item_try_except_continues(self):
        """失败项记入 failed 后**继续**，不是 raise 中断整批。

        🔴 判据只看 **for 循环体**：函数开头的入参守卫（超限 422）本就该 raise，
        拿整个函数体判会假红。
        """
        src = _strip_py_comments(_read(TPL_REL))
        loop = _loop_body(src, "create_custom_workpaper_batch")
        assert "except Exception" in loop
        assert "failed.append(" in loop, "失败项必须落 failed 三态桶"
        assert "raise" not in loop, (
            "per-item 循环体不得 raise（会中断整批）"
        )

    def test_entry_guard_raises_outside_loop(self):
        """反向自检：入参守卫的 raise 在循环**之外**（证明上一条不是空转）。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "create_custom_workpaper_batch")
        loop = _loop_body(src, "create_custom_workpaper_batch")
        assert "raise HTTPException" in body, "缺入参守卫（超限应 422）"
        assert "raise HTTPException" not in loop

    def test_three_states_distinguishable(self):
        """R8.5：成功 / 编号已存在跳过 / 失败 三态可分。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "create_custom_workpaper_batch")
        for bucket in ("created.append(", "skipped.append(", "failed.append("):
            assert bucket in body, f"缺三态桶 {bucket}"

    def test_duplicate_goes_to_skipped_not_failed(self):
        """编号已存在是 skipped（预期结果）不是 failed（异常）。

        🔴 库内重号由 `_create_one_custom_workpaper` 抛 `ValueError` 传递上来，
        批量端点**不重复查库**（那会多一次往返且两处判据可能漂移）⇒ 判据是
        「`except ValueError` 分支落 skipped」而非「先调 `_custom_code_exists`」。
        """
        src = _strip_py_comments(_read(TPL_REL))
        loop = _loop_body(src, "create_custom_workpaper_batch")
        m = re.search(r"except\s+ValueError(\s+as\s+\w+)?\s*:", loop)
        assert m, "批量必须捕获共享创建函数的 ValueError（编号已存在）"
        after = loop[m.end(): m.end() + 400]
        assert "skipped.append(" in after, "库内重号必须归 skipped 不是 failed"
        # 反向：ValueError 分支不得落 failed
        assert "failed.append(" not in after.split("except Exception")[0]

    def test_shared_helper_raises_valueerror_on_duplicate(self):
        """反向自检：共享创建函数确实对重号抛 ValueError（否则上一条空转）。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "_create_one_custom_workpaper")
        m = re.search(r"if\s+await\s+_custom_code_exists\([^)]*\)\s*:", body)
        assert m, "共享创建函数必须先查库内重号"
        after = body[m.end(): m.end() + 200]
        assert "raise ValueError" in after

    def test_batch_size_limit_condition_shape(self):
        """上限判据用条件形态断言（防 `if False:` 短路）。

        实参形态是 `data.items or []`（含点号与 `or`），故正则放宽到 `[^)]+`
        但仍钉住 `len(...) > MAX_BATCH_ITEMS` 的**比较形态**。
        """
        src = _strip_py_comments(_read(TPL_REL))
        for fn in ("create_custom_workpaper_batch", "preview_custom_workpaper_batch"):
            body = _func_body(src, fn)
            assert re.search(
                r"if\s+len\(\s*[^)]+\)\s*>\s*MAX_BATCH_ITEMS\s*:", body
            ), f"{fn} 缺批量上限校验（或被常量短路）"

    def test_limit_guard_weak_criterion_contrast(self):
        """证明上一条抓得住 `if False:` 短路（弱判据抓不住）。"""
        mutated = "if False:\n    x = MAX_BATCH_ITEMS"
        assert "MAX_BATCH_ITEMS" in mutated  # 弱判据仍过
        assert not re.search(
            r"if\s+len\(\s*[^)]+\)\s*>\s*MAX_BATCH_ITEMS\s*:", mutated
        )


# ════════════════════════════════════════════════════════════════════════════
class TestPreviewReadOnly:
    """Property 11：预览端点只读 —— 不得有任何写库动作。"""

    def test_no_write_calls(self):
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "preview_custom_workpaper_batch")
        for forbidden in ("db.add(", "db.flush(", "db.commit(", "begin_nested("):
            assert forbidden not in body, (
                f"预览端点出现写库动作 {forbidden} ⇒ 违反只读（Property 11）"
            )

    def test_queries_db_for_duplicate(self):
        """反向自检：预览确实查了库（否则「只读」是因为它什么都没做）。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "preview_custom_workpaper_batch")
        assert "db.execute(" in body or "_custom_code_exists(" in body, (
            "预览未查库 ⇒ duplicate_db 判不出来"
        )

    def test_four_statuses_present(self):
        """R8.8：status ∈ ok | duplicate_input | duplicate_db | invalid。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "preview_custom_workpaper_batch")
        for st in ("duplicate_input", "duplicate_db", "invalid", '"ok"'):
            assert st in body, f"预览缺状态 {st}"

    def test_summary_counts_present(self):
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "preview_custom_workpaper_batch")
        assert "summary" in body, "预览缺 summary 计数（前端预览表格依赖它）"


# ════════════════════════════════════════════════════════════════════════════
class TestCodeFormatCheckShape:
    """R8.8 / R8.4：编号格式校验在**两个**批量端点都必须存在，且用条件形态断言。

    🔴 只断言 `"invalid"` 字样在函数体里抓不住「删掉格式校验」这个变异 ——
    空值校验那条分支同样写 `"invalid"`（平台已实证：断言标识符出现挡不住
    `if False:` / 删整块）。故判据必须是 `re.fullmatch(WP_CODE_PATTERN, ...)` 的
    调用形态；`import` 行不算调用（`name\\s*\\(` 才算）。
    """

    _SHAPE = re.compile(r"re\.fullmatch\(\s*WP_CODE_PATTERN\s*,")

    @pytest.mark.parametrize(
        "fn", ["preview_custom_workpaper_batch", "create_custom_workpaper_batch"]
    )
    def test_format_check_present(self, fn):
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, fn)
        assert self._SHAPE.search(body), (
            f"{fn} 缺编号格式校验 ⇒ 非法编号会创建出打不开的底稿"
        )

    @pytest.mark.parametrize(
        "fn", ["preview_custom_workpaper_batch", "create_custom_workpaper_batch"]
    )
    def test_format_check_guards_a_branch(self, fn):
        """校验必须真的拦下（`if not re.fullmatch(...)`），不是算完丢弃。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, fn)
        assert re.search(
            r"if\s+not\s+re\.fullmatch\(\s*WP_CODE_PATTERN\s*,[^)]*\)\s*:", body
        ), f"{fn} 的格式校验结果未用于分支（算了不拦）"

    def test_pattern_is_module_level_and_compiles(self):
        """反向自检：常量确实存在且是可用正则（名字写错会运行时 NameError）。"""
        from app.routers.wp_template import WP_CODE_PATTERN

        assert re.fullmatch(WP_CODE_PATTERN, "D1-x_2.a")
        assert not re.fullmatch(WP_CODE_PATTERN, "-bad")
        assert not re.fullmatch(WP_CODE_PATTERN, "a" * 33)

    def test_pattern_matches_frontend(self):
        """跨前后端交叉锁死：正则字面量必须与前端 `WP_CODE_RE` 逐字一致。"""
        fe = _read(
            "audit-platform/frontend/src/components/workpaper/custom/"
            "customWpBatchParse.ts"
        )
        m = re.search(r"export const WP_CODE_RE\s*=\s*/([^/]+)/", fe)
        assert m, "前端未找到 WP_CODE_RE（守卫判据失效）"
        from app.routers.wp_template import WP_CODE_PATTERN

        assert m.group(1) == WP_CODE_PATTERN, (
            f"前后端编号正则漂移: 前端={m.group(1)!r} 后端={WP_CODE_PATTERN!r}"
        )

    def test_max_items_matches_frontend(self):
        """跨前后端交叉锁死：批量上限两侧必须相等。"""
        fe = _read(
            "audit-platform/frontend/src/components/workpaper/custom/"
            "customWpBatchParse.ts"
        )
        m = re.search(r"export const MAX_BATCH_ITEMS\s*=\s*(\d+)", fe)
        assert m, "前端未找到 MAX_BATCH_ITEMS（守卫判据失效）"
        from app.routers.wp_template import MAX_BATCH_ITEMS

        assert int(m.group(1)) == MAX_BATCH_ITEMS, (
            f"批量上限漂移: 前端={m.group(1)} 后端={MAX_BATCH_ITEMS}"
        )


# ════════════════════════════════════════════════════════════════════════════
class TestSingleEndpointUnchanged:
    """Property 12：单条端点响应形状未变（既有前端调用方零改动）。"""

    def test_response_keys_preserved(self):
        """单条端点响应键集不变。

        🔴 重构后端点写 `return {**result, "message": ...}` ⇒ 四个业务键在
        **共享函数的 return** 里，不在端点函数体里。判据必须跨两处，否则
        「共享函数少返一个键」这个真实回归静默逃逸。
        """
        src = _strip_py_comments(_read(TPL_REL))
        ep = _func_body(src, "create_custom_workpaper")
        shared = _func_body(src, "_create_one_custom_workpaper")
        assert '"message"' in ep, "单条端点响应缺 message（破坏既有调用方）"
        assert "**result" in ep, (
            "单条端点未展开共享函数结果 ⇒ 响应形状可能已变"
        )
        for key in ('"wp_id"', '"wp_code"', '"wp_name"', '"file_path"'):
            assert key in shared, f"共享创建函数返回缺 {key}（破坏既有调用方）"

    def test_shared_return_is_the_only_source_of_keys(self):
        """反向自检：端点自己不再拼这四个键（否则上一条的跨两处判据是巧合）。"""
        src = _strip_py_comments(_read(TPL_REL))
        ep = _func_body(src, "create_custom_workpaper")
        assert '"wp_id"' not in ep, (
            "单条端点又自行拼 wp_id ⇒ 与共享函数形成双真源"
        )

    def test_duplicate_still_409(self):
        """单条端点重号仍 409（批量才用 skipped 语义）。"""
        src = _strip_py_comments(_read(TPL_REL))
        body = _func_body(src, "create_custom_workpaper")
        assert "409" in body, "单条端点重号必须仍返 409"

    def test_routes_registered(self):
        from app.routers import wp_template

        paths = {
            getattr(r, "path", "")
            for r in wp_template.router.routes  # type: ignore[attr-defined]
        }
        assert (
            "/api/projects/{project_id}/working-papers/create-custom" in paths
        )
        assert (
            "/api/projects/{project_id}/working-papers/create-custom-batch" in paths
        )
        assert (
            "/api/projects/{project_id}/working-papers/create-custom-batch/preview"
            in paths
        )


# ════════════════════════════════════════════════════════════════════════════
class TestModuleImportsResolve:
    """🔴 `re` 用了但没在模块顶层 import 会在运行时 NameError，
    而 `get_diagnostics` 查不出（平台一天内踩两次）。"""

    def test_re_available_at_module_level(self):
        from app.routers import wp_template

        assert hasattr(wp_template, "re"), (
            "wp_template 用了 re.fullmatch 但模块命名空间无 re ⇒ 预览端点运行时 NameError"
        )

    def test_helper_signature_binds(self):
        """共享创建函数签名与两个调用点绑定一致（sig.bind 实证，非读源码）。"""
        import inspect

        from app.routers.wp_template import _create_one_custom_workpaper

        sig = inspect.signature(_create_one_custom_workpaper)
        # 全部业务参数都是 kw-only，漏传会在 bind 阶段就报错
        sig.bind(
            object(),
            project_id=object(),
            wp_code="X1",
            wp_name="n",
            audit_cycle=None,
            year=2025,
            created_by=None,
        )
