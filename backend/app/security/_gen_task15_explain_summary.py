"""Generate a DETERMINISTIC Task 15 EXPLAIN summary artifact.

Feature: procedure-delegation-visibility-isolation — Task 15 evidence determinism.

The original Task 15 evidence pinned ``explain_plans.txt`` whose bytes are volatile
(EXPLAIN ANALYZE emits per-run timing / buffers / actual-rows / loops). That makes
the pinned hash drift on every re-run and fails the Completion Guard.

This generator re-runs the Task 15 EXPLAIN / query-count verification against the
*real* PostgreSQL ``audit_platform`` and writes a summary that keeps ONLY facts
that are invariant by query construction and by the implementation:

  * the 5 UNION ALL grant branches (lead/assignee/reviewer/lead_history/row_history);
  * ``has_correlated_subplan`` — the N+1 fingerprint — verified absent via
    EXPLAIN (FORMAT JSON) with all cost/rows/width/timing/buffers stripped;
  * grants / gate query-count constancy (constant regardless of workpaper count).

All planner-choice / statistics-dependent numbers (cost, estimated rows, actual
time, buffers, loops, timestamps) are stripped, so CI reproduces identical bytes.
The raw ``explain_plans.txt`` is preserved on disk (not hash-pinned).

Run:  python -m app.security._gen_task15_explain_summary
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[3]
_SUMMARY_PATH = (
    _REPO_ROOT
    / ".kiro" / "specs" / "procedure-delegation-visibility-isolation"
    / "evidence" / "artifacts" / "task15" / "task15_explain_summary.json"
)


def _collect() -> dict:
    # Force the full ORM model registry to load (resolves cross-table FKs such
    # as projects.accounting_standard_id -> accounting_standards) exactly as the
    # pytest conftest environment does.
    import app.main  # noqa: F401
    from sqlalchemy import text

    # Reuse the tested Task 15 helpers (real PG engine + savepoint isolation).
    from tests.procedure_delegation_visibility.test_task15_integration_explain import (  # noqa: E501
        _fresh_engine_run,
        _seed_lead_n,
        _BA,
        CapturingResponder,
    )
    from app.services.wp_visibility import visibility_query as vq
    from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
    from app.services.wp_visibility.visibility_query import VisibilityQueryService
    from app.services.wp_visibility.wp_bound_gate import (
        NullRateLimiter,
        WpBoundGate,
    )

    # ---- (1) EXPLAIN (FORMAT JSON): structural node types, no volatile numbers.
    async def _explain_coro(s, counter):  # noqa: ANN001
        proj, user, _wps = await _seed_lead_n(s, 30)
        branches = [
            vq._BRANCH_LEAD.format(wpx_filter_wi=""),
            vq._BRANCH_ASSIGNEE.format(wpx_filter_prt=""),
            vq._BRANCH_REVIEWER.format(wpx_filter_prt=""),
            vq._BRANCH_LEAD_HISTORY.format(wpx_filter_wdh=""),
            vq._BRANCH_ROW_HISTORY.format(wpx_filter_wdh=""),
        ]
        sql = "\nUNION ALL\n".join(f"({b.strip()})" for b in branches)
        params = {
            "pid": str(proj.id),
            "uid": str(user.id),
            "cancelled": "cancelled",
            "scope": ["D"],
        }
        rows = (await s.execute(text("EXPLAIN (FORMAT JSON) " + sql), params)).all()
        plan_json = rows[0][0]
        if isinstance(plan_json, str):
            plan_json = json.loads(plan_json)
        return plan_json

    plan_json = _fresh_engine_run(_explain_coro)
    root = plan_json[0]["Plan"] if isinstance(plan_json, list) else plan_json["Plan"]

    node_types: set[str] = set()
    has_subplan = {"v": False}

    def _walk(node: dict) -> None:
        nt = node.get("Node Type", "")
        node_types.add(nt)
        if node.get("Parent Relationship") == "SubPlan" or node.get("Subplan Name"):
            has_subplan["v"] = True
        for child in node.get("Plans", []) or []:
            _walk(child)

    _walk(root)
    top_node = root.get("Node Type", "")
    top_family = "Append" if "Append" in top_node else top_node

    # ---- (2) grants list query-count constancy (no per-workpaper N+1).
    def _grants_count(n: int) -> int:
        async def _c(s, counter):  # noqa: ANN001
            proj, user, _wps = await _seed_lead_n(s, n)
            ctx = VisibilityContext(
                user_id=user.id,
                project_id=proj.id,
                role=VisibilityRole.restricted,
                is_admin=False,
                scope_cycles=frozenset({"D"}),
            )
            counter["n"] = 0
            gs = await VisibilityQueryService(s).grants_for_project(ctx)
            assert len(gs.by_wp_index) == n
            return counter["n"]
        return _fresh_engine_run(_c)

    # ---- (3) single-resource gate query-count constancy.
    def _gate_count(n: int) -> int:
        async def _c(s, counter):  # noqa: ANN001
            proj, user, wps = await _seed_lead_n(s, n)
            target_wp = wps[0][1]
            gate = WpBoundGate(
                s, rate_limiter=NullRateLimiter(), responder=CapturingResponder()
            )
            req = _BA.wp(
                entrypoint="workpaper.render_config",
                action="read_render",
                method="GET",
                wp_id=target_wp.id,
                project_id=proj.id,
            )
            counter["n"] = 0
            ctx = await gate.resolve(user, req)
            assert "lead" in ctx.access_kinds
            return counter["n"]
        return _fresh_engine_run(_c)

    grants_n3, grants_n30 = _grants_count(3), _grants_count(30)
    gate_n3, gate_n30 = _gate_count(3), _gate_count(30)

    return {
        "spec": "procedure-delegation-visibility-isolation",
        "task": "15",
        "artifact_kind": "deterministic_explain_summary",
        "determinism_note": (
            "Planner cost/estimated-rows/width and EXPLAIN ANALYZE timing/buffers/"
            "actual-rows/loops/timestamps are stripped. Only query-construction and "
            "implementation invariants are retained so CI reproduces identical bytes. "
            "Raw EXPLAIN (ANALYZE, BUFFERS) output is preserved in explain_plans.txt "
            "(not hash-pinned because its bytes are volatile)."
        ),
        "verified_backend": "PostgreSQL",
        "grants_union": {
            "branches": [
                "lead",
                "assignee",
                "reviewer",
                "lead_history",
                "row_history",
            ],
            "branch_count": 5,
            "union_all": True,
            "top_node_family": top_family,
            "has_correlated_subplan": has_subplan["v"],
        },
        "grants_query_count": {
            "n3": grants_n3,
            "n30": grants_n30,
            "constant": grants_n3 == grants_n30,
            "le_2": grants_n3 <= 2,
        },
        "gate_query_count": {
            "n3": gate_n3,
            "n30": gate_n30,
            "constant": gate_n3 == gate_n30,
        },
    }


def generate(path: Path = _SUMMARY_PATH) -> dict:
    summary = _collect()
    # Fail loudly if the core invariants regressed (never fake-pass).
    assert summary["grants_union"]["has_correlated_subplan"] is False, (
        "EXPLAIN shows a correlated SubPlan (possible per-workpaper N+1)"
    )
    assert summary["grants_query_count"]["constant"], "grants query-count N+1"
    assert summary["grants_query_count"]["le_2"], "grants query-count not <=2"
    assert summary["gate_query_count"]["constant"], "gate query-count N+1"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic bytes: sorted keys, fixed indent, trailing newline.
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    summary = generate()
    print(f"[task15-explain-summary] wrote {_SUMMARY_PATH}")
    print(json.dumps(summary["grants_union"], ensure_ascii=False, sort_keys=True))
    print(json.dumps(summary["grants_query_count"], ensure_ascii=False, sort_keys=True))
    print(json.dumps(summary["gate_query_count"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
