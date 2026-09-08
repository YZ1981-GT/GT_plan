"""Freeze platform-architecture-convergence Task 1 baseline (read-only).

Writes:
  .kiro/specs/platform-architecture-convergence/basis/T01-platform-skeleton-baseline.json

No credentials / customer body. Reuses the generator's AST extractors.
"""
from __future__ import annotations

import ast
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from scripts.gen.generate_component_capability_manifest import (  # noqa: E402
    DEFAULT_SOURCE_PATHS,
    extract_observed_sources,
)

OUT = (
    ROOT
    / ".kiro"
    / "specs"
    / "platform-architecture-convergence"
    / "basis"
    / "T01-platform-skeleton-baseline.json"
)

CONCURRENT_FILES = {
    ".kiro/specs/INDEX.md": {
        "owner": "index-maintainers (all active specs)",
        "pac_allowed": "exact small merge of platform-architecture-convergence row only",
        "forbid": "full rewrite / reformat / other-spec progress edits",
    },
    "backend/app/routers/wp_render_config.py": {
        "owner": "workpaper-guidance-content-closure + platform-architecture-convergence",
        "pac_allowed": "exact small merges: stage orchestration imports, response_model bind, whitelist→manifest projection",
        "forbid": "full rewrite / format-only churn; must preserve concurrent canonical sheet identity edits",
    },
    "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue": {
        "owner": "workpaper-guidance-content-closure + workpaper-page-formula-toolbar-closure",
        "pac_allowed": "exact small merges for mount-contract hooks only",
        "forbid": "full rewrite / visual changes / formula-toolbar scope",
    },
    "audit-platform/frontend/src/composables/useWpRenderer.ts": {
        "owner": "workpaper-guidance-content-closure + platform-architecture-convergence",
        "pac_allowed": "replace WpComponentType union with generated projection; wire DTO imports",
        "forbid": "full rewrite / business render logic changes",
    },
}

LIFESPAN_STARTUP_SEQUENCE = [
    "setup_logging",
    "_run_migrations (if GT_BOOTSTRAP_DONE!=1)",
    "migration_state.mark_complete",
    "ACNR redis inject (get_redis / set_redis_client)",
    "register_event_handlers",
    "register_a13_event_handlers",
    "_register_phase_handlers",
    "_replay_startup_events",
    "validate_grammar_on_startup (critical: sys.exit)",
    "_check_gin_index_status",
    "_check_libreoffice_health",
    "_validate_procedure_rollout_config",
    "_validate_template_manifest",
    "_run_schema_drift_check",
    "_warm_render_caches",
    "_check_attachment_security_gates",
    "start_epoch_subscriber",
    "acnr invalidation outbox dispatcher.start",
    "_recover_ai_chat_runs",
    "_run_ai_chat_health_check (best_effort)",
    "ACNR catalog snapshot GC (best_effort)",
    "_start_workers",
    "install_sigterm_handler",
    "print Ready",
]

LIFESPAN_SHUTDOWN_SEQUENCE = [
    "sleep PRE_DRAIN_DELAY",
    "sse_registry.close_all",
    "drain_http_requests",
    "stop_event.set",
    "stop_epoch_subscriber",
    "acnr dispatcher.stop",
    "cancel+await workers",
    "dispose_engine",
]

WORKERS = [
    "sla_worker",
    "import_recover_worker",
    "outbox_replay_worker",
    "audit_log_writer_worker",
    "budget_alert_worker",
    "dataset_purge_worker",
    "staged_orphan_cleaner",
    "export_cleanup_worker",
    "time_machine_cleanup_worker",
    "procedure_dispatcher_worker",
    "invalidation_dispatcher_worker",
    "ImportJobRunner.run_forever",
]


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_meta(rel: str) -> dict:
    path = ROOT / rel
    if not path.exists():
        return {"exists": False}
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return {
        "exists": True,
        "bytes": len(raw),
        "lines": len(text.splitlines()),
        "content_sha256": _sha256_text(text),
        "mtime_iso": datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(
            timespec="seconds"
        ),
    }


def _extract_dispatch_keys() -> list[str]:
    path = DEFAULT_SOURCE_PATHS.render_dispatch
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "RENDERER_DISPATCH":
                value = node.value
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "RENDERER_DISPATCH" for t in node.targets):
                value = node.value
        if value is None:
            continue
        if not isinstance(value, ast.Dict):
            raise RuntimeError("RENDERER_DISPATCH is not a literal dict")
        keys: list[str] = []
        for key in value.keys:
            if key is None:
                raise RuntimeError("RENDERER_DISPATCH contains ** expansion")
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                raise RuntimeError("RENDERER_DISPATCH non-literal key")
            keys.append(key.value)
        return keys
    raise RuntimeError("RENDERER_DISPATCH assignment not found")


def _router_inventory() -> dict:
    text = (ROOT / "audit-platform/frontend/src/router/index.ts").read_text(encoding="utf-8")
    paths = re.findall(r"path:\s*'([^']+)'", text)
    names = re.findall(r"name:\s*'([^']+)'", text)
    return {
        "file": "audit-platform/frontend/src/router/index.ts",
        "path_literal_count": len(paths),
        "name_literal_count": len(names),
        "beforeEach_count": len(re.findall(r"\.beforeEach\(", text)),
        "has_domains_dir": (ROOT / "audit-platform/frontend/src/router/domains").is_dir(),
        "unique_paths": sorted(set(paths)),
        "duplicate_paths": sorted({p for p in paths if paths.count(p) > 1}),
        "duplicate_names": sorted({n for n in names if names.count(n) > 1}),
    }


def _registry_inventory() -> dict:
    text = (
        ROOT / "audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts"
    ).read_text(encoding="utf-8")
    literals = re.findall(r"componentType:\s*'([^']+)'", text)
    return {
        "file": "audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts",
        "componentType_literal_count": len(literals),
        "componentType_literal_unique": len(set(literals)),
        "has_assert_unique_before_map": (
            "assertUniqueRegistryComponentTypes(REGISTRY_LIST)" in text
            and text.find("assertUniqueRegistryComponentTypes(REGISTRY_LIST)")
            < text.find("new Map(REGISTRY_LIST.map")
        ),
        "checks_map_values": "HTML_RENDERER_REGISTRY.values()" in text,
        "has_entries_dir": (
            ROOT / "audit-platform/frontend/src/components/workpaper/registry/entries"
        ).is_dir(),
        "registry_index_uses_startsWith": "startsWith"
        in (ROOT / "audit-platform/frontend/src/components/workpaper/registry/index.ts").read_text(
            encoding="utf-8"
        )
        if (ROOT / "audit-platform/frontend/src/components/workpaper/registry/index.ts").exists()
        else None,
    }


def _event_defects() -> dict:
    teb = (ROOT / "backend/app/services/task_event_bus.py").read_text(encoding="utf-8")
    pub_match = re.search(r"async def publish\([\s\S]*?\n    async def ", teb)
    pub = pub_match.group(0) if pub_match else ""
    bad: dict[str, int] = {}
    for rel in (
        "backend/app/routers/dispatch_records.py",
        "backend/app/routers/s_transaction_calculation.py",
        "backend/app/services/review_workflow_service.py",
        "backend/app/services/independence_signing_service.py",
        "backend/app/routers/adjustments.py",
    ):
        path = ROOT / rel
        if path.exists():
            bad[rel] = path.read_text(encoding="utf-8").count("from app.core.event_bus import")
    return {
        "publish_writes_idempotency_key_column": "idempotency_key=" in pub,
        "dedup_uses_trace_id_like": ".like(" in pub and "idem_key" in pub,
        "app_core_event_bus_exists": (ROOT / "backend/app/core/event_bus.py").exists(),
        "bad_imports_app_core_event_bus": bad,
        "canonical_envelope_exists": (
            ROOT / "backend/app/core/events/envelope.py"
        ).exists(),
    }


def _render_config_state() -> dict:
    path = ROOT / "backend/app/routers/wp_render_config.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    impl = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_get_render_config_impl"),
        None,
    )
    stages = [
        "load_render_subject",
        "resolve_classification_sources",
        "resolve_scope_redirect",
        "load_common_render_facts",
        "plan_sheets",
        "materialize_sheet",
        "finalize_render_response",
    ]
    return {
        "lines": len(text.splitlines()),
        "impl_lines": (impl.end_lineno - impl.lineno + 1) if impl else None,
        "has_response_model_bind": "response_model=RenderConfigResponse" in text,
        "stage_call_counts": {name: text.count(name + "(") for name in stages},
        "pipeline_module_exists": (ROOT / "backend/app/routers/wp_render_pipeline.py").exists(),
        "whitelist_set_still_defined": "_ONLYOFFICE_HTML_WHITELIST" in text,
        "confirmation_set_still_defined": "_CONFIRMATION_COMPONENTS" in text,
        "contract_schema_exists": (
            ROOT / "backend/app/schemas/render_config_contract.py"
        ).exists(),
        "golden_fixture_exists": (
            ROOT
            / "backend/tests/fixtures/platform_architecture/render_config_wire_golden.json"
        ).exists(),
    }


def _active_specs() -> list[str]:
    specs = ROOT / ".kiro" / "specs"
    names: list[str] = []
    for child in sorted(specs.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if (child / "tasks.md").exists():
            names.append(child.name)
        else:
            names.append(f"{child.name} (empty shell)")
    return names


def _highest_migration() -> str | None:
    migrations = sorted((ROOT / "backend/migrations").glob("V*.sql"))
    return migrations[-1].name if migrations else None


def main() -> int:
    observed = extract_observed_sources(DEFAULT_SOURCE_PATHS)
    named = {name: sorted(values) for name, values in observed.named_sets()}
    rd = set(named["RENDERER_DISPATCH"])
    fr = set(named["REGISTRY_LIST"])
    mc_path = ROOT / "backend/app/data/component_capabilities.json"
    mc: set[str] = set()
    exemptions = 0
    if mc_path.exists():
        payload = json.loads(mc_path.read_text(encoding="utf-8"))
        mc = set(payload.get("components", {}))
        exemptions = len(payload.get("exemptions", []))

    concurrent = {}
    for rel, policy in CONCURRENT_FILES.items():
        concurrent[rel] = {**policy, **_file_meta(rel)}

    baseline = {
        "spec": "platform-architecture-convergence",
        "task": 1,
        "frozen_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "note": "Read-only freeze. Counts are derived; do not hand-edit componentType sets.",
        "eight_sources": {
            name: {"count": len(values), "sha256_of_sorted_join": _sha256_text("\n".join(values))}
            for name, values in named.items()
        },
        "source_diffs": {
            "backend_only": sorted(rd - fr),
            "frontend_only_count": len(fr - rd),
            "frontend_only_sample": sorted(fr - rd)[:20],
            "manifest_count": len(mc),
            "manifest_exemptions": exemptions,
            "not_in_manifest_backend": sorted(rd - mc),
            "not_in_manifest_frontend": sorted(fr - mc),
            "manifest_only": sorted(mc - rd - fr),
            "all_observed_count": len(observed.all_component_types),
        },
        "renderer_dispatch_keys_count": len(_extract_dispatch_keys()),
        "render_config": _render_config_state(),
        "lifespan": {
            "startup_sequence": LIFESPAN_STARTUP_SEQUENCE,
            "shutdown_sequence": LIFESPAN_SHUTDOWN_SEQUENCE,
            "workers": WORKERS,
            "has_startup_registry": "StartupTaskSpec"
            in (ROOT / "backend/app/main.py").read_text(encoding="utf-8"),
        },
        "router": _router_inventory(),
        "frontend_registry": _registry_inventory(),
        "event_defects": _event_defects(),
        "concurrent_dirty_files": concurrent,
        "active_specs_with_tasks": _active_specs(),
        "highest_migration": _highest_migration(),
        "path_corrections": {
            "backend/app/services/wp_render_strategies.py": "backend/app/routers/wp_render_strategies/__init__.py",
            "backend/app/services/dispatch_records.py": "backend/app/routers/dispatch_records.py",
            "backend/app/services/s_transaction_calculation.py": "backend/app/routers/s_transaction_calculation.py",
            "backend/scripts/gen_service_deps.py": "scripts/gen_service_deps.py",
        },
        "wip_already_present": {
            "component_capabilities_json": mc_path.exists(),
            "generate_component_capability_manifest": (
                ROOT / "backend/scripts/gen/generate_component_capability_manifest.py"
            ).exists(),
            "check_component_capabilities": (
                ROOT / "backend/scripts/check/check_component_capabilities.py"
            ).exists(),
            "component_capability_registry": (
                ROOT / "backend/app/services/component_capability_registry.py"
            ).exists(),
            "wp_render_pipeline": (
                ROOT / "backend/app/routers/wp_render_pipeline.py"
            ).exists(),
            "render_config_contract": (
                ROOT / "backend/app/schemas/render_config_contract.py"
            ).exists(),
            "frontend_generated_types": (
                ROOT
                / "audit-platform/frontend/src/types/componentCapabilities.generated.ts"
            ).exists(),
            "frontend_renderConfig_wire": (
                ROOT / "audit-platform/frontend/src/types/renderConfig.ts"
            ).exists(),
            "wire_contract_checker": (
                ROOT / "backend/scripts/check/check_render_config_wire_contract.py"
            ).exists(),
        },
        "red_baselines_still_open": [
            "TaskEventBus.publish computes idempotency hash but dedups via trace_id LIKE; does not write idempotency_key (column exists on TaskEvent / phase15_models)",
            "review_workflow_service / independence_signing_service / adjustments import missing app.core.event_bus",
            "lifespan has no StartupTaskSpec registry (order only in source line order)",
            "router still monolithic; router/domains does not exist",
            "renderer registry entries/ domain arrays do not exist; registry/index still startsWith classifier",
            "_ONLYOFFICE_HTML_WHITELIST / _CONFIRMATION_COMPONENTS moved to component_host_declarations.json; wp_render_config exports manifest projections via types_from_source (planner already uses host_policy)",
        ],
        "schema_notes": {
            "task_event_idempotency_key_column": "present on TaskEvent (phase15_models.idempotency_key); wiring blocked only by publish path, not by missing migration",
            "highest_migration_at_freeze": None,  # filled below
        },
    }
    baseline["schema_notes"]["highest_migration_at_freeze"] = baseline["highest_migration"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(
        "sources:",
        {k: v["count"] for k, v in baseline["eight_sources"].items()},
    )
    print("diffs:", {k: (len(v) if isinstance(v, list) else v) for k, v in baseline["source_diffs"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
