"""Self-tests for check_domain_boundaries.py — synthetic fail-closed scenarios.

Scenarios: allowed, forbidden, unowned, new-debt, reduced-debt, cycle.
Must fail closed on synthetic violations (not only green on compliant data).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CHECK_DIR = Path(__file__).resolve().parents[2] / "scripts" / "check"
sys.path.insert(0, str(CHECK_DIR))

import check_domain_boundaries as guard  # noqa: E402


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_manifest(root: Path, domains: dict) -> Path:
    path = root / "docs/architecture/domain-boundaries.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "domains": domains}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_baseline(path: Path, identities: list[str]) -> None:
    entries = [{"identity": i, "kind": i.split(":", 1)[0], "detail": i} for i in identities]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"metadata": {"count": len(entries)}, "entries": entries}, indent=2) + "\n",
        encoding="utf-8",
    )


MINIMAL_DOMAINS = {
    "core": {
        "owners": ["platform"],
        "paths": ["backend/app/core/**"],
        "may_depend_on": [],
    },
    "alpha": {
        "owners": ["platform"],
        "paths": ["backend/app/services/alpha/**"],
        "may_depend_on": ["core"],
    },
    "beta": {
        "owners": ["platform"],
        "paths": ["backend/app/services/beta/**"],
        "may_depend_on": ["core"],
    },
}


def _seed_core(root: Path) -> None:
    write(root, "backend/app/core/__init__.py", "# core\n")
    write(root, "backend/app/core/util.py", "X = 1\n")


class TestDomainBoundariesSynthetic:
    def test_allowed_edge_is_green(self, tmp_path: Path):
        _seed_core(tmp_path)
        write(
            tmp_path,
            "backend/app/services/alpha/mod.py",
            "from app.core.util import X\n",
        )
        write(tmp_path, "backend/app/services/alpha/__init__.py", "")
        write(tmp_path, "frontend_placeholder.txt", "")
        # frontend scan root optional
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        manifest = write_manifest(tmp_path, MINIMAL_DOMAINS)
        baseline = tmp_path / "baseline.json"
        write_baseline(baseline, [])
        rc = guard.run_check(
            root=tmp_path,
            manifest_path=manifest,
            baseline_path=baseline,
        )
        assert rc == 0

    def test_forbidden_edge_fails_closed(self, tmp_path: Path):
        _seed_core(tmp_path)
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "backend/app/services/alpha/__init__.py", "")
        write(tmp_path, "backend/app/services/beta/__init__.py", "")
        write(tmp_path, "backend/app/services/beta/mod.py", "Y = 2\n")
        write(
            tmp_path,
            "backend/app/services/alpha/mod.py",
            "from app.services.beta.mod import Y\n",
        )
        manifest = write_manifest(tmp_path, MINIMAL_DOMAINS)
        baseline = tmp_path / "baseline.json"
        write_baseline(baseline, [])
        all_v, _, _ = guard.collect_edges(tmp_path, guard.load_manifest(manifest))
        assert any(v.kind == guard.KIND_FORBIDDEN for v in all_v)
        rc = guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline)
        assert rc == 1

    def test_unowned_production_module_fails_closed(self, tmp_path: Path):
        _seed_core(tmp_path)
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "backend/app/services/orphan/mod.py", "Z = 3\n")
        write(tmp_path, "backend/app/services/orphan/__init__.py", "")
        manifest = write_manifest(tmp_path, MINIMAL_DOMAINS)
        baseline = tmp_path / "baseline.json"
        write_baseline(baseline, [])
        all_v, _, _ = guard.collect_edges(tmp_path, guard.load_manifest(manifest))
        assert any(v.kind == guard.KIND_UNOWNED for v in all_v)
        assert any("orphan" in v.identity for v in all_v)
        rc = guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline)
        assert rc == 1

    def test_new_debt_fails_when_baseline_missing_identity(self, tmp_path: Path):
        _seed_core(tmp_path)
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "backend/app/services/alpha/__init__.py", "")
        write(tmp_path, "backend/app/services/beta/__init__.py", "")
        write(tmp_path, "backend/app/services/beta/mod.py", "Y = 2\n")
        write(tmp_path, "backend/app/services/beta/other.py", "Z = 3\n")
        write(
            tmp_path,
            "backend/app/services/alpha/mod.py",
            "from app.services.beta.mod import Y\nfrom app.services.beta.other import Z\n",
        )
        manifest = write_manifest(tmp_path, MINIMAL_DOMAINS)
        domains = guard.load_manifest(manifest)
        all_v, _, _ = guard.collect_edges(tmp_path, domains)
        forbidden = [v for v in all_v if v.kind == guard.KIND_FORBIDDEN]
        assert len(forbidden) >= 2
        # Baseline only covers a subset → remaining identities are NEW debt.
        known = [forbidden[0].identity]
        baseline = tmp_path / "baseline.json"
        write_baseline(baseline, known)
        rc = guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline)
        assert rc == 1

    def test_reduced_debt_prints_hint_but_stays_green(self, tmp_path: Path, capsys):
        _seed_core(tmp_path)
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "backend/app/services/alpha/__init__.py", "")
        write(
            tmp_path,
            "backend/app/services/alpha/mod.py",
            "from app.core.util import X\n",
        )
        manifest = write_manifest(tmp_path, MINIMAL_DOMAINS)
        baseline = tmp_path / "baseline.json"
        # Stale baseline identity that no longer exists.
        write_baseline(
            baseline,
            ["forbidden_edge:alpha->beta:backend/app/services/alpha/mod.py->backend/app/services/beta/mod.py"],
        )
        rc = guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline)
        assert rc == 0
        out = capsys.readouterr().out
        assert "HINT" in out
        assert "shrank" in out

    def test_cycle_detected_fail_closed(self, tmp_path: Path):
        _seed_core(tmp_path)
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "backend/app/services/alpha/__init__.py", "")
        write(tmp_path, "backend/app/services/beta/__init__.py", "")
        write(
            tmp_path,
            "backend/app/services/alpha/mod.py",
            "from app.services.beta.mod import Y\n",
        )
        write(
            tmp_path,
            "backend/app/services/beta/mod.py",
            "from app.services.alpha.mod import X\nX = 1\nY = 2\n",
        )
        manifest = write_manifest(tmp_path, MINIMAL_DOMAINS)
        domains = guard.load_manifest(manifest)
        all_v, edges, _ = guard.collect_edges(tmp_path, domains)
        assert ("alpha", "beta") in edges and ("beta", "alpha") in edges
        assert any(v.kind == guard.KIND_CYCLE for v in all_v)
        baseline = tmp_path / "baseline.json"
        write_baseline(baseline, [])
        rc = guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline)
        assert rc == 1

    def test_cycle_identity_is_scc_node_set(self):
        """Review §4: cycle identity = sorted SCC members, not a rotated path."""
        cycles = guard.detect_domain_cycles([("a", "b"), ("b", "c"), ("c", "a")])
        assert len(cycles) == 1
        assert cycles[0].identity == f"{guard.KIND_CYCLE}:a,b,c"

    def test_cycle_identity_stable_under_intra_scc_edge_churn(self):
        """The core review §4 fix: adding/removing an edge *within* an existing
        SCC must NOT rewrite the cycle identity (no new/resolved churn).

        Old path-string identities exploded: one extra edge rewrote every giant
        cycle's identity. SCC node-set identity is invariant as long as the set
        of mutually reachable domains is unchanged."""
        base = [("a", "b"), ("b", "c"), ("c", "a")]
        churned = base + [("a", "c"), ("b", "a")]  # extra intra-SCC chords
        id_base = {c.identity for c in guard.detect_domain_cycles(base)}
        id_churned = {c.identity for c in guard.detect_domain_cycles(churned)}
        assert id_base == id_churned == {f"{guard.KIND_CYCLE}:a,b,c"}

    def test_disjoint_cycles_get_distinct_scc_identities(self):
        cycles = guard.detect_domain_cycles(
            [("a", "b"), ("b", "a"), ("x", "y"), ("y", "x")]
        )
        ids = sorted(c.identity for c in cycles)
        assert ids == [f"{guard.KIND_CYCLE}:a,b", f"{guard.KIND_CYCLE}:x,y"]

    def test_frontend_forbidden_edge_via_alias_import(self, tmp_path: Path):
        domains = {
            "shell": {
                "owners": ["platform"],
                "paths": ["audit-platform/frontend/src/shell/**"],
                "may_depend_on": [],
            },
            "feature": {
                "owners": ["platform"],
                "paths": ["audit-platform/frontend/src/feature/**"],
                "may_depend_on": [],
            },
        }
        (tmp_path / "backend/app").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "audit-platform/frontend/src/feature/util.ts", "export const n = 1\n")
        write(
            tmp_path,
            "audit-platform/frontend/src/shell/app.ts",
            "import { n } from '@/feature/util'\nexport const x = n\n",
        )
        manifest = write_manifest(tmp_path, domains)
        all_v, _, _ = guard.collect_edges(tmp_path, guard.load_manifest(manifest))
        assert any(v.kind == guard.KIND_FORBIDDEN for v in all_v)
        baseline = tmp_path / "baseline.json"
        write_baseline(baseline, [])
        assert guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline) == 1

    def test_delete_domain_turns_red(self, tmp_path: Path):
        """Mutation: removing a domain leaves former owners unowned → red."""
        _seed_core(tmp_path)
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "backend/app/services/alpha/__init__.py", "")
        write(tmp_path, "backend/app/services/alpha/mod.py", "from app.core.util import X\n")
        full = write_manifest(tmp_path, MINIMAL_DOMAINS)
        # Capture green baseline under full domains.
        domains = guard.load_manifest(full)
        all_v, _, _ = guard.collect_edges(tmp_path, domains)
        baseline = tmp_path / "baseline.json"
        guard.save_baseline(baseline, all_v)
        assert guard.run_check(root=tmp_path, manifest_path=full, baseline_path=baseline) == 0

        broken = dict(MINIMAL_DOMAINS)
        del broken["alpha"]
        broken_manifest = write_manifest(tmp_path, broken)
        # Rewrite manifest path content already overwritten by write_manifest.
        rc = guard.run_check(root=tmp_path, manifest_path=broken_manifest, baseline_path=baseline)
        assert rc == 1

    def test_add_forbidden_edge_turns_red(self, tmp_path: Path):
        """Mutation: new forbidden import beyond baseline → red."""
        _seed_core(tmp_path)
        (tmp_path / "audit-platform/frontend/src").mkdir(parents=True, exist_ok=True)
        write(tmp_path, "backend/app/services/alpha/__init__.py", "")
        write(tmp_path, "backend/app/services/beta/__init__.py", "")
        write(tmp_path, "backend/app/services/beta/mod.py", "Y = 2\n")
        alpha = write(tmp_path, "backend/app/services/alpha/mod.py", "from app.core.util import X\n")
        manifest = write_manifest(tmp_path, MINIMAL_DOMAINS)
        domains = guard.load_manifest(manifest)
        all_v, _, _ = guard.collect_edges(tmp_path, domains)
        baseline = tmp_path / "baseline.json"
        guard.save_baseline(baseline, all_v)
        assert guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline) == 0

        alpha.write_text(
            "from app.core.util import X\nfrom app.services.beta.mod import Y\n",
            encoding="utf-8",
        )
        rc = guard.run_check(root=tmp_path, manifest_path=manifest, baseline_path=baseline)
        assert rc == 1


class TestCiAttributionGuard:
    """Attribution-style guard: assert this job and its file refs exist (not other jobs)."""

    WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/governance-checks.yml"
    JOB = "domain-boundary-governance"

    def test_job_and_file_refs_exist(self):
        text = self.WORKFLOW.read_text(encoding="utf-8")
        assert f"  {self.JOB}:" in text, f"missing independent CI job {self.JOB}"
        required = [
            "backend/scripts/check/check_domain_boundaries.py",
            "backend/tests/scripts/test_check_domain_boundaries.py",
            "docs/architecture/domain-boundaries.json",
            "backend/scripts/check/baselines/domain-boundary-debt.json",
        ]
        for ref in required:
            assert ref in text, f"CI job must reference {ref}"
        # Job body must run checker + unit tests (not merely mention paths in comments elsewhere).
        job_idx = text.index(f"  {self.JOB}:")
        # Next job at same indent after this one (or EOF).
        rest = text[job_idx + 1 :]
        next_job = None
        for line in rest.splitlines()[1:]:
            if line.startswith("  ") and line.endswith(":") and not line.startswith("   "):
                next_job = line
                break
        job_block = text[job_idx : (text.index(next_job, job_idx) if next_job else len(text))]
        assert "check_domain_boundaries.py" in job_block
        assert "test_check_domain_boundaries.py" in job_block
