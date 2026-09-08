"""Attribution guard: pac-skeleton-typecheck job must stay in governance-checks."""
from __future__ import annotations

from pathlib import Path


class TestPacSkeletonTypecheckCiGuard:
    WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/governance-checks.yml"
    JOB = "pac-skeleton-typecheck"

    def test_job_runs_typecheck_and_network_gate(self) -> None:
        text = self.WORKFLOW.read_text(encoding="utf-8")
        assert f"  {self.JOB}:" in text, f"missing independent CI job {self.JOB}"
        job_idx = text.index(f"  {self.JOB}:")
        rest = text[job_idx + 1 :]
        next_job = None
        for line in rest.splitlines()[1:]:
            if line.startswith("  ") and line.endswith(":") and not line.startswith("   "):
                next_job = line
                break
        job_block = text[job_idx : (text.index(next_job, job_idx) if next_job else len(text))]
        assert "tsconfig.pac-t21.json" in job_block
        assert "pacNetworkGate.spec.ts" in job_block
        assert "vue-tsc" in job_block
