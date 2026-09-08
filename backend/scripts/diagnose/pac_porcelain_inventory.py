"""Reproduce the PAC formal-products git porcelain inventory (Req 12.7).

Read-only: scans `git status --porcelain` for every PAC product and prints its
tracked / `??` state grouped by control-plane. Never stages or commits anything.
Regenerates the headline numbers in `basis/T22-porcelain-inventory.md`.
"""
from __future__ import annotations

import subprocess

# PAC formal products, grouped by the four assembly control planes.
PRODUCTS: dict[str, list[str]] = {
    "spec (三件套 + basis)": [
        ".kiro/specs/platform-architecture-convergence/requirements.md",
        ".kiro/specs/platform-architecture-convergence/design.md",
        ".kiro/specs/platform-architecture-convergence/tasks.md",
        ".kiro/specs/platform-architecture-convergence/basis",
    ],
    "render control-plane": [
        "backend/app/data/component_capabilities.json",
        "backend/app/data/component_host_declarations.json",
        "backend/app/services/component_capability_registry.py",
        "backend/scripts/gen/generate_component_capability_manifest.py",
        "backend/scripts/check/check_component_capabilities.py",
        "backend/tests/test_component_capability_contract.py",
        "backend/app/schemas/render_config_contract.py",
        "backend/app/routers/wp_render_pipeline.py",
        "backend/scripts/check/check_render_config_wire_contract.py",
        "backend/scripts/diagnose/capture_render_config_wire_golden.py",
        "backend/tests/fixtures/platform_architecture",
        "backend/tests/test_render_config_wire_contract.py",
        "backend/tests/test_render_config_pipeline_characterization.py",
        "backend/tests/test_render_pipeline_stage_guards.py",
        "backend/tests/test_wp_classification_pipeline.py",
        "backend/tests/test_render_config_sheet_context.py",
        "audit-platform/frontend/src/types/renderConfig.ts",
        "audit-platform/frontend/src/types/componentCapabilities.generated.ts",
        "audit-platform/frontend/src/types/__tests__",
        "audit-platform/frontend/src/components/workpaper/WpDecisionTracePanel.vue",
        "audit-platform/frontend/src/components/workpaper/GtWpRenderer.real-registry.contract.test.ts",
    ],
    "startup control-plane": [
        "backend/app/core/startup_registry.py",
        "backend/tests/test_startup_registry.py",
    ],
    "governance control-plane": [
        "docs/architecture/domain-boundaries.json",
        "docs/architecture/DOMAIN_DEBT_BURNDOWN.md",
        "backend/scripts/check/check_domain_boundaries.py",
        "backend/scripts/check/baselines/domain-boundary-debt.json",
        "backend/tests/scripts/test_check_domain_boundaries.py",
        ".kiro/steering/domain-boundaries.md",
    ],
    "event control-plane": [
        "backend/app/core/events",
        "backend/tests/test_canonical_event_envelope.py",
        "backend/tests/test_task_event_bus_idempotency_auth.py",
        "backend/tests/test_event_call_site_guards.py",
    ],
    "frontend assembly (route + registry)": [
        "audit-platform/frontend/src/router/domains",
        "audit-platform/frontend/src/router/__tests__",
        "audit-platform/frontend/src/components/workpaper/registry/entries",
        "audit-platform/frontend/src/components/workpaper/__tests__/registrySplitEquivalence.pbt.spec.ts",
        "audit-platform/frontend/src/components/workpaper/__tests__/registryDomainSplit.spec.ts",
        "backend/scripts/gen/split_html_renderer_registry_domains.py",
    ],
    "verification / mutation / e2e": [
        "backend/scripts/diagnose/mutate_pac_platform_architecture_guards.py",
        "backend/scripts/diagnose/_freeze_pac_t01_baseline.py",
        "backend/scripts/diagnose/probe_platform_baseline.py",
        "backend/scripts/diagnose/_pac_t19_t20_probe.py",
        "backend/scripts/diagnose/_pac_t22_resolve_wps.py",
        "backend/scripts/diagnose/pac_porcelain_inventory.py",
        "backend/tests/scripts/test_pac_skeleton_typecheck_ci.py",
        "audit-platform/frontend/tsconfig.pac-t21.json",
        "audit-platform/frontend/e2e/platform-architecture-convergence.spec.ts",
        "audit-platform/frontend/src/__tests__/pacNetworkGate.spec.ts",
        "audit-platform/frontend/src/__tests__/_helpers/pacNetworkGate.ts",
        "audit-platform/frontend/src/__tests__/pac-t21-typecheck-probe.ts",
    ],
}


def porcelain(path: str) -> str:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", path],
        capture_output=True, text=True,
    ).stdout.strip()
    if not out:
        exists = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            capture_output=True, text=True,
        ).returncode == 0
        return "tracked-clean" if exists else "MISSING"
    lines = out.splitlines()
    codes = {ln[:2].strip() for ln in lines}
    suffix = f" ({len(lines)} paths)" if len(lines) > 1 else ""
    if all(c == "??" for c in codes):
        return "?? untracked" + suffix
    return " / ".join(sorted(codes)) + suffix


def main() -> int:
    total = tracked = untracked = 0
    for group, paths in PRODUCTS.items():
        print(f"\n== {group} ==")
        for p in paths:
            st = porcelain(p)
            total += 1
            if st.startswith("??"):
                untracked += 1
                mark = "UNTRACKED"
            elif st == "tracked-clean" or st[:1] in {"M", "A"}:
                tracked += 1
                mark = "tracked"
            else:
                mark = "MISSING?"
            print(f"  [{mark:9}] {st:26} {p}")
    print(f"\nTOTAL {total}  tracked/modified {tracked}  untracked {untracked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
