"""Mutation verification for the workpaper writer inventory generator, gate and guards.

A guard that never turns red proves nothing. Each mutation below changes exactly one
character-range and names the single test that must fail because of it.

Four-state verdicts (an exit code alone collapses the last three into RED):

===========  ====================================================
RED          turned red, and the expected test is the one failing
GREEN        did not turn red                     -> guard defect
ANCHOR-MISS  anchor absent or matched more than once -> script defect
WRONG-TEST   turned red, but not on the expected test
===========  ====================================================

Mutation classes differ in whether the generated inventory has to be rebuilt:

* ``source`` - mutates production code under ``backend/app``. The inventory is regenerated
  so the guards see the mutated *facts*. Without this step every source mutation would
  merely trip the staleness check, which is WRONG-TEST, not proof.
* ``generator`` - mutates the discovery predicate. Also regenerated, for the same reason.
* ``gate`` - mutates the gate's evaluation only; nothing is regenerated.

Usage from the repository root::

    python backend/scripts/check/mutate_workpaper_writer_inventory_gates.py --check-anchors
    python backend/scripts/check/mutate_workpaper_writer_inventory_gates.py --apply
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_GUARD = "backend/tests/test_workpaper_writer_inventory.py"
_GENERATOR = "backend/scripts/gen/generate_workpaper_writer_inventory.py"
_GATE = "backend/scripts/check/check_workpaper_writer_revision_gate.py"
_INVENTORY = _REPO / "backend" / "data" / "workpaper_writer_inventory.json"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover
        pass


@dataclass(frozen=True)
class Mutation:
    mid: str
    kind: str  # "source" | "generator" | "gate"
    path: str
    old: str
    new: str
    expect_test: str
    why: str

    @property
    def needs_regeneration(self) -> bool:
        return self.kind in {"source", "generator"}


MUTATIONS: tuple[Mutation, ...] = (
    # ─── M1/M2/M3 were rewritten by Task 18 ──────────────────────────────────
    # Their original form injected the *end state* Task 18 was going to deliver (route
    # HTML save through the unified boundary; drop `parsed_data._version`; stop moving
    # `file_version` in the shared handler). Once Task 18 landed, all three anchors were
    # gone and the mutations degraded to ANCHOR-MISS -- so the direction is flipped: they
    # now inject the *regression*, which is the only form that stays falsifiable.
    Mutation(
        mid="M1",
        kind="source",
        path="backend/app/routers/wp_html_save.py",
        old="    mutation_service = build_html_content_mutation_service(db)\n",
        new="    mutation_service = _mut_detached_lane(db)\n",
        expect_test="test_only_the_migrated_writers_reach_the_unified_commit_boundary",
        why="make the migrated HTML save leave the unified commit boundary again "
        "(the called name no longer matches _UNIFIED_COMMIT_MARKERS, so the row's "
        "unified_commit_calls goes back to empty)",
    ),
    Mutation(
        mid="M2",
        kind="source",
        path="backend/app/routers/wp_html_save.py",
        old='    parsed_data["last_modified_at"] = now.isoformat()\n',
        new=(
            '    parsed_data["last_modified_at"] = now.isoformat()\n'
            '    parsed_data["_version"] = server_version + 1\n'
        ),
        expect_test="test_html_save_no_longer_writes_two_version_domains",
        why="re-introduce the private parsed_data._version counter beside "
        "working_paper.content_revision -- exactly the two-domain finding Task 18 closed",
    ),
    # The retirement ledger verifies itself against source: `_build_retired_writers`
    # raises when a retired writer starts writing version state again, so regeneration
    # refuses and the stored inventory no longer matches the AST. That derivability test
    # is therefore the guard that owns the claim here -- same reasoning as M7/M8 below.
    # The *direct* judgement ("after_save moved a version") lives in
    # `mutate_task16_durable_outbox_guards.py::M37` and
    # `mutate_task18_html_save_unified_revision_guards.py::M07`.
    Mutation(
        mid="M3",
        kind="source",
        path="backend/app/services/workpaper_save_orchestrator.py",
        old="        wp.prefill_stale = True\n",
        new="        wp.prefill_stale = True\n        wp.file_version += 1\n",
        expect_test="test_inventory_on_disk_matches_the_ast",
        why="give the shared, replayable post-save handler a version domain again -- the "
        "retirement ledger must refuse to regenerate rather than quietly re-admit it",
    ),
    Mutation(
        mid="M4",
        kind="source",
        path="backend/app/services/version_trail_service.py",
        old='            "DELETE FROM checklist_responses WHERE wp_id = :workpaper_id"\n',
        new='            "DELETE FROM some_other_table WHERE wp_id = :workpaper_id"\n',
        expect_test="test_two_content_stores_hold_workpaper_business_content",
        why="hide the history-restore delete of the second content store",
    ),
    Mutation(
        mid="M5",
        kind="generator",
        path=_GENERATOR,
        old='_CONTENT_ATTRS: frozenset[str] = frozenset({"parsed_data", "file_path"})',
        new='_CONTENT_ATTRS: frozenset[str] = frozenset({"parsed_data", "file_path", "prefill_stale"})',
        expect_test="test_status_and_staleness_fields_are_never_counted_as_business_content",
        why="let a staleness flag count as business content",
    ),
    Mutation(
        mid="M6",
        kind="generator",
        path=_GENERATOR,
        old='_NON_CONTENT_ATTRS: frozenset[str] = frozenset({"prefill_stale", "updated_at", "updated_by"})',
        new='_NON_CONTENT_ATTRS: frozenset[str] = frozenset({"updated_at", "updated_by"})',
        expect_test="test_staleness_writers_are_recorded_as_side_effects_instead",
        why="stop recording staleness writes as side effects at all",
    ),
    # M7 and M8 both make whole lanes of adjudicated writers vanish. The overlay-to-source
    # bidirectional lock in `build_inventory` refuses to regenerate at all, so the guard
    # that owns the claim is the derivability test, not a downstream fact assertion --
    # a downstream assertion would still be reading the pre-mutation file and stay green.
    Mutation(
        mid="M7",
        kind="generator",
        path=_GENERATOR,
        old='    "checklist_responses": frozenset({"remark", "conclusion"}),',
        new="",
        expect_test="test_inventory_on_disk_matches_the_ast",
        why="forget that workpaper content also lives in checklist_responses",
    ),
    Mutation(
        mid="M8",
        kind="generator",
        path=_GENERATOR,
        old="        hits = sorted(targets & direct)\n        if hits:\n",
        new="        hits = sorted(targets & direct)\n        if False and hits:\n",
        expect_test="test_single_hop_delegation_resolves_same_module_and_imported_callees",
        why="disable single-hop delegation so delegating endpoints stop counting as writers",
    ),
    Mutation(
        mid="M9",
        kind="generator",
        path=_GENERATOR,
        old="    identities = list(facts[\"resolver_calls\"])",
        new="    identities = list(facts[\"resolver_calls\"])[:1]",
        expect_test="test_onlyoffice_config_and_download_fan_out_to_several_resolvers",
        why="collapse multi-resolver fan-out to a single resolver",
    ),
    Mutation(
        mid="M10",
        kind="generator",
        path=_GENERATOR,
        old='    body = {key: value for key, value in inventory.items() if key != "inventory_digest"}\n'
        '    return _sha256(_stable_json(body).encode("utf-8"))',
        new='    return str(inventory.get("inventory_digest"))',
        expect_test="test_hand_edited_inventory_is_rejected_by_self_consistency",
        why="make the self-consistency digest trivially agree with itself",
    ),
    Mutation(
        mid="M11",
        kind="gate",
        path=_GATE,
        old="            if is_writer:\n                issues[\"unadjudicated_writer\"].append(writer_id)",
        new="            if False:\n                issues[\"unadjudicated_writer\"].append(writer_id)",
        expect_test="test_a_single_unadjudicated_writer_keeps_the_gate_red",
        why="stop treating an undecided writer as blocking",
    ),
    Mutation(
        mid="M12",
        kind="gate",
        path=_GATE,
        old='    if expected["entries"] != inventory.get("entries"):',
        new='    if False and expected["entries"] != inventory.get("entries"):',
        expect_test="test_dropping_a_row_cannot_make_the_gate_greener",
        why="stop comparing stored rows against the rows re-derived from source",
    ),
    Mutation(
        mid="M13",
        kind="gate",
        path=_GATE,
        old='        if is_writer and verdicts.get("bypasses_unified_commit"):',
        new='        if False and verdicts.get("bypasses_unified_commit"):',
        expect_test="test_unified_revision_gate_is_red_and_names_every_reason",
        why="stop reporting writers that bypass the unified commit boundary",
    ),
)


def _read(path: str) -> str:
    """Read preserving the on-disk line endings.

    ``newline=""`` matters: universal-newline translation would rewrite a CRLF file as LF
    on restore, which silently reformats production source. It is passed to ``open`` rather
    than ``Path.read_text`` because the latter only accepts it from Python 3.13.
    """
    with open(_REPO / path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: str, text: str) -> None:
    with open(_REPO / path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _dominant_newline(source: str) -> str:
    """Return the newline this file actually uses.

    Production modules under ``backend/app`` are CRLF while the scripts are LF. Anchors are
    authored with ``\\n``, so a multi-line anchor matches zero times against a CRLF file --
    the documented ANCHOR-MISS trap. Translating the anchor to the file's own newline keeps
    one authored form working against both.
    """
    return "\r\n" if "\r\n" in source else "\n"


def _localise(text: str, newline: str) -> str:
    return text.replace("\n", newline) if newline != "\n" else text


def _regenerate() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, _GENERATOR.replace("/", "\\"), "--apply"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _run_guard(expect_test: str) -> tuple[bool, bool]:
    """Run the guard file; return (anything failed, the expected test failed).

    ERROR lines count as well: a module-scoped fixture that now raises reports the
    expected test as ERROR rather than FAILED, and that is still the guard firing.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            _GUARD,
            "-q",
            "--tb=no",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
        ],
        cwd=_REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    expected_failed = any(
        line.startswith(("FAILED", "ERROR")) and expect_test in line
        for line in output.splitlines()
    )
    return proc.returncode != 0, expected_failed


def check_anchors() -> int:
    """Read-only: every anchor must match its target file exactly once."""
    status = 0
    print("-- anchors --")
    for mutation in MUTATIONS:
        source = _read(mutation.path)
        anchor = _localise(mutation.old, _dominant_newline(source))
        hits = source.count(anchor)
        verdict = "OK" if hits == 1 else f"ANCHOR-MISS({hits})"
        if hits != 1:
            status = 1
        print(f"{mutation.mid:<4} {verdict:<18} {mutation.kind:<9} {mutation.why}")
    return status


def apply_mutations() -> int:
    baseline_failed, _ = _run_guard("__none__")
    if baseline_failed:
        print("[FAIL] baseline guard run is already red; fix that before mutating")
        return 2
    inventory_backup = _INVENTORY.read_bytes()
    verdicts: dict[str, str] = {}

    for mutation in MUTATIONS:
        original = _read(mutation.path)
        newline = _dominant_newline(original)
        anchor = _localise(mutation.old, newline)
        replacement = _localise(mutation.new, newline)
        if original.count(anchor) != 1:
            verdicts[mutation.mid] = "ANCHOR-MISS"
            print(f"{mutation.mid:<4} ANCHOR-MISS  {mutation.why}")
            continue
        regen_note = ""
        try:
            _write(mutation.path, original.replace(anchor, replacement, 1))
            if mutation.needs_regeneration:
                ok, output = _regenerate()
                if not ok:
                    regen_note = "  (regeneration refused the mutation)"
            overall, expected = _run_guard(mutation.expect_test)
            if not overall:
                verdict = "GREEN"
            elif expected:
                verdict = "RED"
            else:
                verdict = "WRONG-TEST"
        finally:
            _write(mutation.path, original)
            _INVENTORY.write_bytes(inventory_backup)
        verdicts[mutation.mid] = verdict
        print(
            f"{mutation.mid:<4} {verdict:<12} {mutation.kind:<9} "
            f"{mutation.expect_test}{regen_note}"
        )

    # Prove the restore was byte-exact, otherwise a later run inherits our damage.
    restored_clean, _ = _run_guard("__none__")
    if restored_clean:
        print("[FAIL] guard is red after restore; the working tree was not fully restored")
        return 2

    counts: dict[str, int] = {}
    for verdict in verdicts.values():
        counts[verdict] = counts.get(verdict, 0) + 1
    print("\nverdicts: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if counts.get("RED", 0) == len(MUTATIONS) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-anchors", action="store_true", help="read-only anchor check")
    mode.add_argument("--apply", action="store_true", help="run every mutation")
    args = parser.parse_args(argv)
    return check_anchors() if args.check_anchors else apply_mutations()


if __name__ == "__main__":
    raise SystemExit(main())
