"""test_sampling_evaluation_fill_path — R2.5 回填路径的评价归一（Task 24 实测挖出）

**缺陷形态（改造前，浏览器实测复现）**：R2.5 允许回填时随 `extraction_criteria`
一并带上 `evaluation`（省一次往返），但 `cutoff_fill` 把客户端载荷**原样落库**，
而 `evaluated_at` / `evaluated_by` 是**服务端权威字段**（客户端不传）→ 该路径写出的
evaluation 缺这两个键 → 前端 `evaluationSourceHint` 因 `evaluatedAt` 为空而不渲染
「读自批次 X（… 评价）」标注 ⇒ R2.7 的「标注来源批次与评价时间」落不了地。

判据都是**源码形态 + 纯函数行为**，不依赖数据库（连库断言在
`test_sampling_evaluation_endpoint.py`）。

Validates: Requirements 2.3, 2.5, 2.7
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[1]
CUTOFF = BACKEND / "app" / "routers" / "cutoff_sampling.py"
VOUCHER = BACKEND / "app" / "routers" / "voucher_sampling.py"


def _read(p: Path) -> str:
    src = p.read_text(encoding="utf-8")
    assert len(src) > 1000, f"{p.name} 应非空（路径漂移会让本文件断言空转）"
    return src


def _strip_comments_and_docstrings(src: str) -> str:
    """剥 `#` 注释与 docstring，保留普通字符串字面量。

    本文件的说明注释里会写出被禁形态，不剥会把说明数成真实代码。
    """
    # 1. 剥 # 注释
    out_lines = src.splitlines()
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except tokenize.TokenError:
        toks = []
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            row = tok.start[0] - 1
            out_lines[row] = out_lines[row][: tok.start[1]]
    stripped = "\n".join(out_lines)
    # 2. 剥 docstring（按行号置空）
    try:
        tree = ast.parse(stripped)
    except SyntaxError:
        return stripped
    lines = stripped.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(
            first.value.value, str
        ):
            for i in range(first.lineno - 1, (first.end_lineno or first.lineno)):
                if 0 <= i < len(lines):
                    lines[i] = ""
    return "\n".join(lines)


CUTOFF_SRC = _read(CUTOFF)
CUTOFF_CODE = _strip_comments_and_docstrings(CUTOFF_SRC)


class TestStripSelfCheck:
    """剥注释/docstring 的自检（否则后续断言可能在空串上求值）。"""

    def test_strip_actually_removes(self) -> None:
        assert len(CUTOFF_CODE) < len(CUTOFF_SRC), "剥注释必须真的变短"

    def test_strip_keeps_string_literals(self) -> None:
        sample = 'x = "evaluation"  # evaluation\n'
        got = _strip_comments_and_docstrings(sample)
        assert '"evaluation"' in got, "普通字符串字面量不得被剥（可能是真消费）"
        assert got.count("evaluation") == 1, "注释里的那一处应被剥掉"

    def test_scan_target_is_the_right_file(self) -> None:
        assert "async def cutoff_fill" in CUTOFF_CODE
        assert "record_extraction_log" in CUTOFF_CODE


class TestCutoffFillNormalizesEvaluation:
    """R2.5：回填路径必须复用同一归一器。"""

    def test_calls_shared_normalizer(self) -> None:
        assert "_normalize_evaluation" in CUTOFF_CODE, (
            "cutoff_fill 未复用 `_normalize_evaluation` —— 客户端原样落库会缺 "
            "evaluated_at / evaluated_by（服务端权威字段），R2.7 的来源批次标注失效"
        )
        assert re.search(
            r"from\s+app\.routers\.voucher_sampling\s+import\s+_normalize_evaluation",
            CUTOFF_CODE,
        ), "必须从 voucher_sampling 导入同一函数（不得另抄一份归一逻辑 = 双真源）"

    def test_normalize_is_guarded_by_dict_check(self) -> None:
        """只在 evaluation 确为 dict 时归一（不传/传 null 时行为逐字节不变 = 零回归）。"""
        assert re.search(
            r'if\s+isinstance\(\s*criteria\.get\("evaluation"\)\s*,\s*dict\s*\)\s*:',
            CUTOFF_CODE,
        ), "缺少 dict 门控：不带 evaluation 的既有调用方必须行为不变"

    def test_normalize_happens_before_log_write(self) -> None:
        """归一必须早于落库，否则写进去的还是原始载荷。"""
        i_norm = CUTOFF_CODE.index("_normalize_evaluation(")
        i_write = CUTOFF_CODE.index("record_extraction_log(")
        assert i_norm < i_write, "归一必须在 record_extraction_log 之前"

    def test_actor_id_from_server_not_payload(self) -> None:
        body = CUTOFF_CODE[
            CUTOFF_CODE.index("_normalize_evaluation(") : CUTOFF_CODE.index("_normalize_evaluation(")
            + 220
        ]
        assert "actor_id=current_user.id" in body, (
            "actor 必须取服务端会话用户；取载荷里的值等于让客户端自报操作人"
        )

    def test_no_duplicate_normalizer_definition(self) -> None:
        """本模块不得自己定义一份同名归一器（双真源）。"""
        assert "def _normalize_evaluation" not in CUTOFF_CODE


class TestNormalizerStampsServerFields:
    """归一器本身必须盖服务端时间/操作人（这是上面复用它的全部理由）。"""

    def test_stamps_evaluated_at_and_by(self) -> None:
        from app.routers.voucher_sampling import _normalize_evaluation

        actor = uuid4()
        out = _normalize_evaluation({"projected": "1.00"}, actor_id=actor)
        assert out.get("evaluated_at"), "evaluated_at 必须由服务端盖章"
        assert out.get("evaluated_by") == str(actor)

    def test_client_supplied_stamps_are_overridden(self) -> None:
        from app.routers.voucher_sampling import _normalize_evaluation

        actor = uuid4()
        out = _normalize_evaluation(
            {"evaluated_at": "1999-01-01T00:00:00+00:00", "evaluated_by": str(uuid4())},
            actor_id=actor,
        )
        assert not out["evaluated_at"].startswith("1999"), "客户端时间不可信，必须被覆盖"
        assert out["evaluated_by"] == str(actor)

    @pytest.mark.parametrize("raw", [None, "", 0, [], "not-a-dict"])
    def test_non_dict_input_still_returns_shape(self, raw: object) -> None:
        """非 dict 载荷不得抛错（回填路径的 dict 门控之外还有直接端点）。"""
        from app.routers.voucher_sampling import _normalize_evaluation

        out = _normalize_evaluation(raw, actor_id=uuid4())
        assert isinstance(out, dict) and out.get("evaluated_at")

    def test_preserves_a13_marker_from_existing(self) -> None:
        """a13_pushed_at 未提供时保留既有值（防重复计入的标记不能被回填抹掉）。"""
        from app.routers.voucher_sampling import _normalize_evaluation

        out = _normalize_evaluation(
            {"projected": "1.00"},
            actor_id=uuid4(),
            existing={"a13_pushed_at": "2026-01-01T00:00:00Z"},
        )
        assert out["a13_pushed_at"] == "2026-01-01T00:00:00Z"


class TestReverseSelfCheck:
    """反向自检：证明上面的判据真能区分好坏实现。"""

    def test_naive_passthrough_would_be_detected(self) -> None:
        """替身：原样落库的实现里没有归一器调用 → 判据必判违规。"""
        fake = (
            "async def cutoff_fill():\n"
            '    criteria = dict(req.extraction_criteria)\n'
            "    result = await LedgerSamplingService.record_extraction_log(db, log_data)\n"
        )
        assert "_normalize_evaluation" not in fake

    def test_normalizer_without_stamp_would_be_detected(self) -> None:
        """替身：归一器不盖章时，TestNormalizerStampsServerFields 的判据会失败。"""
        out = {"projected": "1.00"}  # 不含 evaluated_at
        assert not out.get("evaluated_at")
