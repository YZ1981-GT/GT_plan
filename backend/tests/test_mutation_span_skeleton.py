"""Self-tests for the shared span-anchor mutation skeleton (`_mutation_kit/span.py`).

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Wave 0 Task 8 - Requirements 14.7 - Property 57

A mutation harness is the tool every other guard's credibility rests on, so its own
verdicts have to be proven rather than assumed. Each of the four states is produced here
from a real temporary file plus a stand-in test runner that decides pass/fail by *reading
the file it was handed*, which is what makes these behavioural rather than mock-shaped:

* RED - the anchor lands, the runner reports the expected test failing
* GREEN - the anchor lands, nothing fails (a guard defect, not a code defect)
* WRONG-TEST - something fails but not the expected test (contamination or wrong anchor)
* ANCHOR-MISS - the anchor matched zero or several times, so nothing was ever proven

The last two are the ones a naive `exit code != 0` harness silently reports as RED, so they
get the most attention. CRLF handling and byte-exact restore are proven on files written
with each line ending explicitly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import RunResult  # noqa: E402
from _mutation_kit.anchor import AnchorMiss  # noqa: E402
from _mutation_kit.apply import RestoreFailed  # noqa: E402
from _mutation_kit.span import (  # noqa: E402
    ANCHOR_MISS,
    GREEN,
    RED,
    WRONG_TEST,
    SpanMutation,
    dominant_eol,
    localise,
    locate_span,
    run_cli,
    sha256_of,
    span_mutated,
    validate_span,
    validate_spans,
)

GUARD_FILES = {"test_fake_guard.py": "Task 8 self-test denominator"}
LF_BODY = "def keep():\n    hits = compute()\n    if hits:\n        return hits\n    return None\n"


def _write(path: Path, body: str, eol: str) -> Path:
    path.write_bytes(body.replace("\n", eol).encode("utf-8"))
    return path


@pytest.fixture()
def lf_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    _write(tmp_path / "src" / "mod.py", LF_BODY, "\n")
    return tmp_path


@pytest.fixture()
def crlf_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    _write(tmp_path / "src" / "mod.py", LF_BODY, "\r\n")
    return tmp_path


def _mutation(**over) -> SpanMutation:
    base = dict(
        id="M01",
        path="src/mod.py",
        anchor="    hits = compute()\n    if hits:",
        new="    hits = compute()\n    if False and hits:",
        want="test_hits_branch_is_live",
        why="disabling the branch must be caught by the guard that owns it",
    )
    base.update(over)
    return SpanMutation(**base)  # type: ignore[arg-type]


def _runner_from(repo: Path, *, fails_when_mutated: set[str], baseline: set[str] = frozenset()):
    """Stand-in runner: fails only while the file actually carries the mutation."""
    original = (repo / "src" / "mod.py").read_bytes()

    def run() -> RunResult:
        current = (repo / "src" / "mod.py").read_bytes()
        failed = set(baseline) | (set(fails_when_mutated) if current != original else set())
        return RunResult(
            failed={f"test_fake_guard.py::{name}" for name in failed},
            summary=f"{3 - len(failed)} passed, {len(failed)} failed",
            passed=3 - len(failed),
            name2file={f"test_fake_guard.py::{name}": "test_fake_guard.py" for name in failed},
        )

    return run


def _run(repo: Path, mutation: SpanMutation, runner, report: Path | None = None) -> int:
    argv = ["--run", "all"]
    if report is not None:
        argv += ["--report-path", str(report)]
    return run_cli(
        mutations=[mutation],
        guard_files=GUARD_FILES,
        repo=repo,
        pytest_args=["backend/tests/test_fake_guard.py"],
        runner=runner,
        argv=argv,
    )


def _verdict(report: Path) -> str:
    return json.loads(report.read_text(encoding="utf-8"))["mutations"][0]["verdict"]


# ------------------------------------------------------------------ CRLF normalisation


def test_dominant_eol_and_localise_round_trip() -> None:
    assert dominant_eol("a\r\nb") == "\r\n"
    assert dominant_eol("a\nb") == "\n"
    assert dominant_eol("single line") == "\n"
    assert localise("a\nb", "\r\n") == "a\r\nb"
    assert localise("a\nb", "\n") == "a\nb"


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_multiline_anchor_hits_on_both_line_endings(tmp_path: Path, eol: str) -> None:
    """The authored anchor uses `\\n`; a CRLF target must still match exactly once."""
    target = _write(tmp_path / "mod.py", LF_BODY, eol)
    text = target.read_bytes().decode("utf-8")
    hits = locate_span(text, "    hits = compute()\n    if hits:")
    assert len(hits) == 1
    assert dominant_eol(text) == eol


def test_crlf_target_is_not_rewritten_to_lf(crlf_repo: Path) -> None:
    """Byte-level IO: a CRLF file must still be CRLF after a mutate/restore cycle."""
    target = crlf_repo / "src" / "mod.py"
    before = target.read_bytes()
    with span_mutated(_mutation(), crlf_repo) as mutated:
        assert b"\r\n" in mutated and b"if False and hits:" in mutated
        assert mutated.count(b"\n") == before.count(b"\n")
    assert target.read_bytes() == before
    assert b"\r\n" in target.read_bytes()


# ----------------------------------------------------------------- anchor uniqueness


def test_zero_hit_anchor_is_anchor_miss(lf_repo: Path) -> None:
    with pytest.raises(AnchorMiss, match="0 命中"):
        locate_span((lf_repo / "src" / "mod.py").read_text(encoding="utf-8"), "no such text")


def test_multiple_hit_anchor_is_anchor_miss(tmp_path: Path) -> None:
    target = _write(tmp_path / "mod.py", "x = 1\ny = 2\nx = 1\ny = 2\n", "\n")
    text = target.read_text(encoding="utf-8")
    with pytest.raises(AnchorMiss, match="命中 2 次"):
        locate_span(text, "x = 1\ny = 2")
    assert len(locate_span(text, "x = 1\ny = 2", allow_multi=True)) == 2


def test_allow_multi_replaces_every_hit(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    _write(tmp_path / "src" / "mod.py", "flag = True\nflag = True\n", "\n")
    mutation = _mutation(
        anchor="flag = True",
        new="flag = False",
        allow_multi=True,
        multi_reason="the fixture intentionally repeats the line",
    )
    with span_mutated(mutation, tmp_path) as mutated:
        assert mutated.decode("utf-8").count("flag = False") == 2


# ---------------------------------------------------------------- byte-exact restore


def test_restore_is_byte_exact_even_when_the_body_raises(lf_repo: Path) -> None:
    target = lf_repo / "src" / "mod.py"
    before, digest = target.read_bytes(), sha256_of(target)
    with pytest.raises(ZeroDivisionError):
        with span_mutated(_mutation(), lf_repo):
            raise ZeroDivisionError("simulated test-run crash")
    assert target.read_bytes() == before and sha256_of(target) == digest


def test_restore_mismatch_raises_restore_failed(lf_repo: Path, monkeypatch) -> None:
    """The sha256 re-check is a real branch, not decoration."""
    import _mutation_kit.span as span_mod

    monkeypatch.setattr(span_mod, "sha256_of", lambda _p: "0" * 64)
    with pytest.raises(RestoreFailed, match="还原后 sha256 不符"):
        with span_mutated(_mutation(), lf_repo):
            pass


def test_no_op_mutation_is_refused_before_the_body_runs(lf_repo: Path) -> None:
    """A replacement that leaves the bytes identical proves nothing, so it is refused.

    ``validate_span`` already rejects ``new == anchor`` at declaration time; this asserts
    the second, independent line of defence inside ``span_mutated`` - the two layers exist
    because a future mutation kind could produce an accidental no-op that the declaration
    check cannot see.
    """
    mutation = SpanMutation(
        id="M01",
        path="src/mod.py",
        anchor="    if hits:",
        new="    if hits:",
        want="test_x",
        why="identical replacement writes no change at all",
    )
    assert any("无效变异" in p for p in validate_span(mutation))
    target = lf_repo / "src" / "mod.py"
    digest = sha256_of(target)
    with pytest.raises(AnchorMiss, match="sha256 未变"):
        with span_mutated(mutation, lf_repo):
            pytest.fail("the body must not run when nothing was written")
    assert sha256_of(target) == digest


# --------------------------------------------------------------- four-state verdicts


def test_red_when_the_expected_guard_fails(lf_repo: Path, tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = _run(
        lf_repo,
        _mutation(),
        _runner_from(lf_repo, fails_when_mutated={"test_hits_branch_is_live"}),
        report,
    )
    assert _verdict(report) == RED
    assert code == 0, "all-RED plus a covered denominator must exit 0"


def test_green_when_nothing_fails(lf_repo: Path, tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = _run(lf_repo, _mutation(), _runner_from(lf_repo, fails_when_mutated=set()), report)
    assert _verdict(report) == GREEN, "a guard that stays green must not be reported as RED"
    assert code == 1


def test_wrong_test_when_a_different_guard_fails(lf_repo: Path, tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = _run(
        lf_repo,
        _mutation(),
        _runner_from(lf_repo, fails_when_mutated={"test_some_unrelated_thing"}),
        report,
    )
    assert _verdict(report) == WRONG_TEST, (
        "a failure on another test proves nothing about the expected claim"
    )
    assert code == 1


def test_anchor_miss_when_the_anchor_is_absent(lf_repo: Path, tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = _run(
        lf_repo,
        _mutation(anchor="def gone():\n    pass", new="def gone():\n    return 1"),
        _runner_from(lf_repo, fails_when_mutated={"test_hits_branch_is_live"}),
        report,
    )
    assert _verdict(report) == ANCHOR_MISS, (
        "an anchor that never matched must never be reported as RED - nothing ran"
    )
    assert code == 1


def test_anchor_miss_is_not_reported_as_red_even_though_the_runner_would_fail(
    lf_repo: Path, tmp_path: Path
) -> None:
    """The exact confusion this harness exists to prevent, stated as its own assertion.

    The stand-in runner is clean on the baseline call and then reports exactly the wanted
    test failing on every later call. If the harness ever ran the tests despite the absent
    anchor - or reused someone else's failure - the verdict would read RED. It must not.
    """
    calls = {"n": 0}

    def run() -> RunResult:
        calls["n"] += 1
        if calls["n"] == 1:
            return RunResult(failed=set(), summary="3 passed", passed=3)
        return RunResult(
            failed={"test_fake_guard.py::test_hits_branch_is_live"},
            summary="2 passed, 1 failed",
            passed=2,
            name2file={"test_fake_guard.py::test_hits_branch_is_live": "test_fake_guard.py"},
        )

    report = tmp_path / "report.json"
    code = _run(lf_repo, _mutation(anchor="absent anchor", new="still absent"), run, report)
    assert _verdict(report) == ANCHOR_MISS
    assert code == 1
    assert calls["n"] == 1, "the tests must not run at all once the anchor missed"


def test_expect_green_control_inverts_the_verdict(lf_repo: Path, tmp_path: Path) -> None:
    """A control mutation ("this harmless edit must NOT turn anything red") is supported."""
    report = tmp_path / "report.json"
    control = _mutation(
        want="*",
        expect_green=True,
        why="adding a harmless entry must not trip the guard; direction check only",
    )
    code = _run(lf_repo, control, _runner_from(lf_repo, fails_when_mutated=set()), report)
    assert _verdict(report) == RED
    #: A control mutation reddens nothing by design, so it contributes no guard file to the
    #: coverage denominator. The kit's rule that a full run must cover every registered
    #: guard file therefore still fails - which is correct: a suite made only of controls
    #: has proven no guard at all.
    assert code == 1


def test_runner_crash_is_recorded_as_error_not_as_success(lf_repo: Path, tmp_path: Path) -> None:
    """AC 5.12 in miniature: an exception must be recorded, never degraded into a pass.

    A harness that swallowed the crash would report GREEN - "the guard did not fire" -
    which reads as a code defect when the truth is that nothing ran.
    """
    calls = {"n": 0}

    def run() -> RunResult:
        calls["n"] += 1
        if calls["n"] == 1:
            return RunResult(failed=set(), summary="3 passed", passed=3)
        raise RuntimeError("simulated pytest launch failure")

    report = tmp_path / "report.json"
    target = lf_repo / "src" / "mod.py"
    digest = sha256_of(target)
    code = _run(lf_repo, _mutation(), run, report)
    record = json.loads(report.read_text(encoding="utf-8"))["mutations"][0]
    assert record["verdict"] == "ERROR" and "RuntimeError" in record["detail"]
    assert code == 1
    assert sha256_of(target) == digest, "the file must still be restored after a crash"


def test_dirty_baseline_aborts(lf_repo: Path) -> None:
    code = _run(
        lf_repo,
        _mutation(),
        _runner_from(
            lf_repo, fails_when_mutated={"test_hits_branch_is_live"}, baseline={"test_pre_existing"}
        ),
    )
    assert code == 4, "a red baseline makes the difference verdict untrustworthy"


# ------------------------------------------------------------------ CLI surface


def test_check_anchors_is_read_only(lf_repo: Path, tmp_path: Path) -> None:
    target = lf_repo / "src" / "mod.py"
    digest = sha256_of(target)
    report = tmp_path / "anchors.json"
    code = run_cli(
        mutations=[_mutation()],
        guard_files=GUARD_FILES,
        repo=lf_repo,
        pytest_args=["backend/tests/test_fake_guard.py"],
        argv=["--check-anchors", "--report-path", str(report)],
    )
    assert code == 0 and sha256_of(target) == digest
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["mode"] == "check-anchors"
    assert payload["mutations"][0]["verdict"] == "OK"


def test_check_anchors_reports_miss_without_touching_the_file(lf_repo: Path) -> None:
    target = lf_repo / "src" / "mod.py"
    digest = sha256_of(target)
    code = run_cli(
        mutations=[_mutation(anchor="absent", new="also absent")],
        guard_files=GUARD_FILES,
        repo=lf_repo,
        pytest_args=["x"],
        argv=["--check-anchors"],
    )
    assert code == 1 and sha256_of(target) == digest


def test_empty_denominator_is_refused(lf_repo: Path) -> None:
    with pytest.raises(ValueError, match="guard_files"):
        run_cli(
            mutations=[_mutation()],
            guard_files={},
            repo=lf_repo,
            pytest_args=["x"],
            argv=["--list"],
        )


def test_bad_declaration_is_refused_before_anything_runs(lf_repo: Path) -> None:
    target = lf_repo / "src" / "mod.py"
    digest = sha256_of(target)
    code = run_cli(
        mutations=[_mutation(why="short")],
        guard_files=GUARD_FILES,
        repo=lf_repo,
        pytest_args=["x"],
        argv=["--run", "all"],
    )
    assert code == 6 and sha256_of(target) == digest


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"anchor": ""}, "anchor 为空"),
        ({"anchor": "a\r\nb"}, "含 \\r"),
        ({"new": "x\r\n"}, "含 \\r"),
        ({"anchor": "same", "new": "same"}, "无效变异"),
        ({"why": "tiny"}, "why 缺失或过短"),
        ({"want": "", "wants": ()}, "want / wants 都为空"),
        ({"allow_multi": True}, "必须写 multi_reason"),
        ({"multi_reason": "no flag"}, "自相矛盾"),
    ],
)
def test_declaration_validation_rejects(over: dict, expected: str) -> None:
    problems = validate_span(_mutation(**over))
    assert any(expected in p for p in problems), problems


def test_duplicate_ids_are_refused() -> None:
    problems = validate_spans([_mutation(), _mutation()])
    assert any("id 重复" in p for p in problems)


def test_empty_mutation_list_is_refused() -> None:
    assert any("清单为空" in p for p in validate_spans([]))
