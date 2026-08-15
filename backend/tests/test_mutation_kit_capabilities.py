"""共享件 `_mutation_kit` 的七项能力守卫 —— 判据是「故意破坏后必失败」。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.5 · Property 20

## 判据形态

不写「函数存在」「能调用不抛」这类断言 —— 那是 memory 假绿第②源（grep 式守卫）。
每条测试都构造一个**会触发该能力的坏输入**，断言它被拒绝；同时配一条**合规输入
不得被误报**的反向自检，否则「恒报错」也能让前一半断言通过。

被测对象全部用 `tmp_path` 下的替身文件，**不拿真实生产文件做素材** —— 共享件的
测试自己去改生产代码，是把测试变成第二个污染源。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import (  # noqa: E402
    ANCHOR_MISS,
    GREEN,
    RED,
    WRONG_TEST,
    AnchorMiss,
    CoverageTally,
    Mutation,
    RestoreFailed,
    RunResult,
    apply_mutation,
    find_anchor,
    judge,
    md5_of,
    mutated,
    read_lines,
    run_cli,
    stale_backups,
    validate_all,
    validate_mutation,
)
from _mutation_kit.cli import _run_one  # noqa: E402


# ─── 夹具：临时仓库 + 替身目标文件 ───────────────────────────────────────────


def _write(path: Path, text: str, crlf: bool = True) -> None:
    """按字节写，默认 CRLF —— 平台工作树就是 CRLF，测试必须复现这个条件。"""
    body = text.replace("\n", "\r\n") if crlf else text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "src" / "target.py",
        "def f():\n    return 1\n\n\ndef g():\n    return 2\n",
    )
    _write(
        tmp_path / "guards" / "test_alpha.py",
        "def test_alpha_one():\n    assert True\n",
    )
    _write(
        tmp_path / "guards" / "test_beta.py",
        "def test_beta_one():\n    assert True\n",
    )
    return tmp_path


def _mut(**over) -> Mutation:
    base = dict(
        id="M01", side="be", path="src/target.py", kind="replace",
        anchor="    return 1", new="    return 999",
        want="test_alpha_one", why="改掉返回值以反证守卫是否锁死该值",
    )
    base.update(over)
    return Mutation(**base)  # type: ignore[arg-type]


# ═══ 能力 1：锚点唯一性 ═══════════════════════════════════════════════════════


def test_anchor_multiple_hits_is_rejected(fake_repo: Path) -> None:
    _write(fake_repo / "src" / "dup.py", "    return 1\nx = 0\n    return 1\n")
    lines = read_lines(fake_repo / "src" / "dup.py")
    with pytest.raises(AnchorMiss, match="命中 2 次"):
        find_anchor(lines, "    return 1")


def test_anchor_zero_hits_is_rejected(fake_repo: Path) -> None:
    lines = read_lines(fake_repo / "src" / "target.py")
    with pytest.raises(AnchorMiss, match="命中 0 次"):
        find_anchor(lines, "    return 42")


def test_anchor_substring_does_not_count_as_hit(fake_repo: Path) -> None:
    """整行相等而非子串包含 —— 缩进不同的行不得被算进来（Wave 1 实测的假阳性形态）。"""
    _write(fake_repo / "src" / "indent.py", "      return 1\n    return 1\n")
    lines = read_lines(fake_repo / "src" / "indent.py")
    assert find_anchor(lines, "    return 1") == 1
    assert find_anchor(lines, "      return 1") == 0


def test_anchor_unique_hit_passes(fake_repo: Path) -> None:
    """反向自检：合规锚点不得被误报。"""
    lines = read_lines(fake_repo / "src" / "target.py")
    assert find_anchor(lines, "    return 1") == 1


def test_line_disambiguation_requires_exact_match(fake_repo: Path) -> None:
    lines = read_lines(fake_repo / "src" / "target.py")
    with pytest.raises(AnchorMiss, match="内容不符"):
        find_anchor(lines, "    return 1", want_line=1)


def test_find_anchor_rejects_multiline_anchor(fake_repo: Path) -> None:
    """🔴 定位期也必须拒绝含换行的锚点 —— 与声明期那道是**两层独立防护**。

    本条由变异检验补出（M02）：原先只有
    `test_multiline_anchor_rejected_at_declaration` 覆盖声明期（`validate_mutation`），
    于是把 `anchor.py` 里定位期的换行检查删掉时**没有任何测试会红**（判定 GREEN）。
    绕过 `run_cli` 直接调 `find_anchor` 的调用方（例如共享件内部的 `block_range`、
    或临时诊断脚本）走的正是这一层。
    """
    lines = read_lines(fake_repo / "src" / "target.py")
    with pytest.raises(AnchorMiss, match="含换行"):
        find_anchor(lines, "def f():\n    return 1")
    with pytest.raises(AnchorMiss, match="含换行"):
        find_anchor(lines, "def f():\r\n    return 1")


# ═══ 能力 2：声明期校验（锚点换行是重点）═════════════════════════════════════


def test_multiline_anchor_rejected_at_declaration() -> None:
    """🔴 本 spec 作者自己在 Wave 2 写出过多行锚点并吃到 ANCHOR-MISS ⇒ 必须在声明期拦住。"""
    errs = validate_mutation(_mut(anchor="    return 1\n    return 2"))
    assert any("含换行" in e for e in errs), errs


def test_anchor_with_trailing_eol_rejected() -> None:
    errs = validate_mutation(_mut(anchor="    return 1\n"))
    assert any("含换行" in e or "行尾" in e for e in errs), errs


def test_replace_with_identical_new_rejected() -> None:
    """`new == anchor` 是无效变异（改动不落盘），必须在声明期就拒绝。"""
    errs = validate_mutation(_mut(new="    return 1"))
    assert any("无效变异" in e for e in errs), errs


def test_missing_why_rejected() -> None:
    errs = validate_mutation(_mut(why=""))
    assert any("why" in e for e in errs), errs


def test_duplicate_id_rejected() -> None:
    problems = validate_all([_mut(), _mut(new="    return 7")])
    assert any("id 重复" in p for p in problems), problems


def test_empty_mutation_list_rejected() -> None:
    """空清单会让所有子命令恒成功 —— 是假绿而非「没有变异」。"""
    assert any("为空" in p for p in validate_all([]))


def test_valid_declaration_passes() -> None:
    """反向自检：合规声明不得被误报。"""
    assert validate_mutation(_mut()) == []
    assert validate_all([_mut()]) == []


def test_swap_requires_anchor2_and_block_open() -> None:
    errs = validate_mutation(_mut(kind="swap"))
    assert any("anchor2" in e for e in errs), errs
    assert any("block_open" in e for e in errs), errs


# ═══ 能力 3：应用与还原（md5 逐字核验 + CRLF 保留）═══════════════════════════


def test_apply_preserves_crlf(fake_repo: Path) -> None:
    target = fake_repo / "src" / "target.py"
    assert target.read_bytes().count(b"\r\n") > 0, "夹具应为 CRLF"
    apply_mutation(_mut(), fake_repo)
    body = target.read_bytes()
    assert b"    return 999\r\n" in body, "替换后必须保留原行尾"
    assert body.count(b"\n") == body.count(b"\r\n"), "不得混入裸 LF"


def test_mutated_context_restores_byte_for_byte(fake_repo: Path) -> None:
    target = fake_repo / "src" / "target.py"
    before = md5_of(target)
    with mutated(_mut(), fake_repo) as changed:
        assert b"return 999" in changed
        assert md5_of(target) != before
    assert md5_of(target) == before, "退出上下文后必须逐字还原"
    assert not stale_backups(fake_repo), "不得留下 .mutbak"


def test_mutated_restores_even_on_exception(fake_repo: Path) -> None:
    target = fake_repo / "src" / "target.py"
    before = md5_of(target)
    with pytest.raises(ValueError):
        with mutated(_mut(), fake_repo):
            raise ValueError("模拟测试执行阶段抛错")
    assert md5_of(target) == before, "异常路径也必须还原（还原写在 finally）"
    assert not stale_backups(fake_repo)


def test_restore_failure_is_raised_not_swallowed(fake_repo: Path, monkeypatch) -> None:
    """🔴 篡改还原内容后必须抛 RestoreFailed —— 不信「写回成功」。"""
    target = fake_repo / "src" / "target.py"
    real_write = Path.write_bytes

    def poisoned(self: Path, data: bytes) -> int:  # type: ignore[override]
        if self == target and b"return 1" in data:
            data = data.replace(b"return 1", b"return 111")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", poisoned)
    with pytest.raises(RestoreFailed):
        with mutated(_mut(), fake_repo):
            pass


def test_noop_mutation_reported_as_anchor_miss(fake_repo: Path) -> None:
    """变异后 md5 未变（改动没落盘）⇒ ANCHOR-MISS，不能当成守卫问题。

    这是 `mutated()` 的**运行时兜底**：声明期已有「replace 的 new 与 anchor 相同」
    这条校验，但调用方可以绕过 `run_cli` 直接用 `mutated()`，故两层都要有。
    """
    m = _mut(kind="replace", anchor="    return 1", new="    return 1")
    with pytest.raises(AnchorMiss, match="未变"):
        with mutated(m, fake_repo):
            pass


def test_noop_mutation_also_rejected_at_declaration(fake_repo: Path) -> None:
    """同一形态在声明期就该被拒（双层防护的另一层）。"""
    errs = validate_mutation(_mut(kind="replace", anchor="    return 1", new="    return 1"))
    assert any("无效变异" in e for e in errs), errs


# ═══ 能力 4：四态判定 ════════════════════════════════════════════════════════


def test_verdict_red_when_want_in_added() -> None:
    v, added, gone, hit = judge("test_a", set(), {"test_a", "test_b"})
    assert v == RED and hit == ["test_a"] and set(added) == {"test_a", "test_b"}


def test_verdict_green_when_nothing_added() -> None:
    v, *_ = judge("test_a", {"test_x"}, {"test_x"})
    assert v == GREEN


def test_verdict_wrong_test_when_want_missing() -> None:
    v, added, _, hit = judge("test_a", set(), {"test_zzz"})
    assert v == WRONG_TEST and hit == [] and added == ["test_zzz"]


def test_verdict_ignores_exit_code_by_construction() -> None:
    """判定只吃失败名集合 —— judge 的签名里根本没有退出码，形态上不可能误用。"""
    import inspect

    params = set(inspect.signature(judge).parameters)
    assert params == {"want", "baseline_failed", "current_failed"}, params


def test_gone_items_are_reported(fake_repo: Path) -> None:
    _, _, gone, _ = judge("test_a", {"test_flaky"}, {"test_a"})
    assert gone == ["test_flaky"], "基线中消失的失败项必须报出（基线不稳的信号）"


# ═══ 能力 5：作用域自证（Wave 1 实测的 GREEN 误判形态）═══════════════════════


def test_scope_check_failure_is_anchor_miss_not_green(fake_repo: Path) -> None:
    """🔴 锚点落在被测判据作用域之外时，必须判 ANCHOR-MISS 而不是 GREEN。

    Wave 1 实测：变异把豁免表顶部 `_schema.reason`（文档说明）改短了，而被测校验只
    覆盖 `exemptions[]` 内的项 ⇒ 四态判定式「新增失败集合是否为空」报 GREEN，
    把脚本缺陷误报成守卫缺陷。
    """
    m = _mut(scope_check=lambda _b: False)

    def runner() -> RunResult:
        raise AssertionError("scope_check 失败时不应再跑测试")

    rec = _run_one(m, fake_repo, set(), runner)
    assert rec["verdict"] == ANCHOR_MISS
    assert "作用域" in rec["detail"]
    assert rec["restored"] is True


def test_scope_check_pass_proceeds_to_runner(fake_repo: Path) -> None:
    """反向自检：作用域自证通过时必须继续跑测试（否则该机制会吞掉全部变异）。"""
    called: list[bool] = []

    def runner() -> RunResult:
        called.append(True)
        return RunResult(failed={"test_alpha_one"}, summary="stub")

    rec = _run_one(_mut(scope_check=lambda b: b"return 999" in b), fake_repo, set(), runner)
    assert called == [True]
    assert rec["verdict"] == RED


# ═══ 能力 6：覆盖面分母 ══════════════════════════════════════════════════════


def test_empty_denominator_is_rejected() -> None:
    """🔴 空分母会让「守卫都被反证过」恒成立。"""
    with pytest.raises(ValueError, match="不能为空"):
        CoverageTally({})


def test_tally_reports_uncovered_guard_file() -> None:
    t = CoverageTally({"test_a.py": "Task 1", "test_b.py": "Task 2", "test_c.py": "Task 3"})
    t.record({"test_a.py", "test_b.py"})
    lines = "\n".join(t.report(full_run=True))
    assert "test_c.py" in lines and "[GAP]" in lines
    assert "2/3" in lines
    assert not t.is_complete(full_run=True)


def test_tally_complete_when_all_covered() -> None:
    t = CoverageTally({"test_a.py": "Task 1"})
    t.record({"test_a.py"})
    assert t.is_complete(full_run=True)
    assert "[GAP]" not in "\n".join(t.report(full_run=True))


def test_tally_subset_run_makes_no_coverage_claim() -> None:
    """子集运行不给覆盖面结论 —— 否则 `--run M01` 会报一堆噪声缺口。"""
    t = CoverageTally({"test_a.py": "Task 1", "test_b.py": "Task 2"})
    t.record({"test_a.py"})
    lines = "\n".join(t.report(full_run=False))
    assert "不做覆盖面结论" in lines and "[GAP]" not in lines
    assert not t.is_complete(full_run=False)


def test_tally_extra_files_are_info_only() -> None:
    t = CoverageTally({"test_a.py": "Task 1"})
    t.record({"test_a.py", "test_other_spec.py"})
    lines = "\n".join(t.report(full_run=True))
    assert "[INFO]" in lines and "test_other_spec.py" in lines
    assert t.is_complete(full_run=True), "未登记文件被打红不应算作缺口"


# ═══ 能力 7：CLI —— --list 校验与 --check-anchors 只读 ═══════════════════════


def _cli(fake_repo: Path, argv: list[str], muts: list[Mutation] | None = None,
         guard_files: dict[str, str] | None = None) -> int:
    return run_cli(
        mutations=muts if muts is not None else [_mut()],
        guard_files=guard_files if guard_files is not None else {"test_alpha.py": "夹具"},
        repo=fake_repo,
        guard_roots=("guards",),
        argv=argv,
    )


def test_list_fails_when_want_cannot_be_located(fake_repo: Path) -> None:
    """🔴 want 定位不到时 `--list` 必须非零退出 —— 否则判定永远只能是 WRONG-TEST。"""
    rc = _cli(fake_repo, ["--list"], muts=[_mut(want="test_does_not_exist_anywhere")])
    assert rc != 0


def test_list_fails_when_guard_file_missing(fake_repo: Path) -> None:
    rc = _cli(fake_repo, ["--list"], guard_files={"test_never_existed.py": "分母项失效"})
    assert rc != 0


def test_list_fails_on_bad_anchor(fake_repo: Path) -> None:
    rc = _cli(fake_repo, ["--list"], muts=[_mut(anchor="    return 42")])
    assert rc != 0


def test_list_passes_on_healthy_declaration(fake_repo: Path) -> None:
    """反向自检：健康声明的 `--list` 必须返回 0（否则上面三条恒真）。"""
    assert _cli(fake_repo, ["--list"]) == 0


def test_check_anchors_is_read_only(fake_repo: Path) -> None:
    """🔴 `--check-anchors` 跑完后目标文件 md5 必须不变、无 .mutbak 残留。"""
    target = fake_repo / "src" / "target.py"
    before = md5_of(target)
    rc = _cli(fake_repo, ["--check-anchors"])
    assert rc == 0
    assert md5_of(target) == before
    assert not stale_backups(fake_repo)


def test_check_anchors_reports_drift(fake_repo: Path) -> None:
    rc = _cli(fake_repo, ["--check-anchors"], muts=[_mut(anchor="    return 42")])
    assert rc == 1, "锚点漂移必须非零退出"


def test_subset_run_exit_code_not_penalized_by_coverage(fake_repo: Path, monkeypatch) -> None:
    """🔴 子集运行不得因「覆盖面不完整」而非零退出。

    子集（`--run M01`）天然只覆盖少数守卫文件。若把 `is_complete(full_run=False)`
    算进退出码，「只跑一条变异确认它还红」这个最常用动作会永远失败。
    该缺陷由 Task 11 迁移 e-cycle 时暴露：判定矩阵 6/6 逐一相同却 RC=1。

    此处用替身 runner 让变异判 RED（不真跑 pytest），只验退出码逻辑。
    """
    from _mutation_kit import cli as cli_mod

    def stub_runner(_repo, _args, timeout=1800):  # noqa: ANN001, ARG001
        return RunResult(failed=set(), summary="stub 0 failed", passed=1)

    calls = {"n": 0}

    def stub_after_mutation(_repo, _args, timeout=1800):  # noqa: ANN001, ARG001
        calls["n"] += 1
        # 基线（第 1 次）空集；变异后（第 2 次起）返回 want 命中
        if calls["n"] == 1:
            return RunResult(failed=set(), summary="stub baseline", passed=1)
        return RunResult(
            failed={"test_alpha.py::test_alpha_one"},
            summary="stub mutated",
            passed=0,
            name2file={"test_alpha.py::test_alpha_one": "test_alpha.py"},
        )

    monkeypatch.setattr(cli_mod, "run_pytest", stub_after_mutation)
    two = [_mut(), _mut(id="M02", anchor="    return 2", new="    return 888")]
    rc = run_cli(
        mutations=two,
        guard_files={"test_alpha.py": "夹具", "test_beta.py": "夹具（本子集覆盖不到）"},
        repo=fake_repo,
        backend_args=["-q"],
        guard_roots=("guards",),
        argv=["--run", "M01"],
    )
    assert rc == 0, "子集运行全 RED 时必须返回 0，不得因覆盖面不全被判失败"
    assert stub_runner is not None  # 保留引用，避免 linter 误删


def test_full_run_exit_code_still_requires_coverage(fake_repo: Path, monkeypatch) -> None:
    """反向自检：全量运行仍必须满足覆盖面，否则上一条会把覆盖面机制整个废掉。"""
    from _mutation_kit import cli as cli_mod

    calls = {"n": 0}

    def stub(_repo, _args, timeout=1800):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return RunResult(failed=set(), summary="stub baseline", passed=1)
        return RunResult(
            failed={"test_alpha.py::test_alpha_one"},
            summary="stub mutated",
            passed=0,
            name2file={"test_alpha.py::test_alpha_one": "test_alpha.py"},
        )

    monkeypatch.setattr(cli_mod, "run_pytest", stub)
    rc = run_cli(
        mutations=[_mut()],
        guard_files={"test_alpha.py": "夹具", "test_beta.py": "夹具（无变异覆盖）"},
        repo=fake_repo,
        backend_args=["-q"],
        guard_roots=("guards",),
        argv=["--run", "all"],
    )
    assert rc == 1, "全量运行有覆盖面缺口时必须非零退出"


def test_run_aborts_on_stale_backup(fake_repo: Path) -> None:
    """残留备份意味着上一轮被中断、基线已被污染 ⇒ 必须 ABORT 而不是继续。"""
    (fake_repo / "src" / "target.py.mutbak").write_bytes(b"stale")
    rc = _cli(fake_repo, ["--run", "all"])
    assert rc == 3


def test_bad_declaration_blocks_run_subcommand(fake_repo: Path) -> None:
    """声明期校验对 --run 无条件生效：坏声明不该有机会跑起来。"""
    rc = _cli(fake_repo, ["--run", "all"], muts=[_mut(anchor="a\nb")])
    assert rc == 6


def test_guard_files_is_keyword_only_and_required() -> None:
    """🔴 让「没有分母」在签名层面不可能，而不是靠约定。"""
    import inspect

    sig = inspect.signature(run_cli)
    param = sig.parameters["guard_files"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty, "guard_files 不得有默认值"
