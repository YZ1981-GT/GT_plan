"""platform-architecture-convergence Task 1: 平台骨架红基线只读探针。

只读、无外部依赖、无凭据。用于在实施前核实 spec 三件套中登记的"已确认红基线"
是否仍在当前工作树成立，避免按过期事实做重复工作。

运行：python backend/scripts/diagnose/probe_platform_baseline.py
     python backend/scripts/diagnose/probe_platform_baseline.py --json
"""
from __future__ import annotations

import ast
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# ── 目标清单：spec 声明的路径 vs 实际路径 ─────────────────────────────────────
TARGETS = [
    "backend/app/routers/wp_render_config.py",
    "backend/app/routers/wp_render_pipeline.py",
    "backend/app/routers/wp_render_strategies/__init__.py",
    "backend/app/schemas/render_config_contract.py",
    "backend/app/services/wp_classification_service.py",
    "backend/app/data/wp_code_overrides.json",
    "backend/app/data/component_capabilities.json",
    "backend/app/data/component_host_declarations.json",
    "backend/app/services/component_capability_registry.py",
    "backend/scripts/gen/generate_component_capability_manifest.py",
    "backend/scripts/check/check_component_capabilities.py",
    "backend/tests/test_component_capability_contract.py",
    "backend/scripts/check/check_domain_boundaries.py",
    "backend/scripts/check/baselines/domain-boundary-debt.json",
    "docs/architecture/domain-boundaries.json",
    "scripts/gen_service_deps.py",
    "audit-platform/frontend/src/types/componentCapabilities.generated.ts",
    "audit-platform/frontend/src/types/RenderConfigWire.ts",
    "audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts",
    "audit-platform/frontend/src/components/workpaper/registry/index.ts",
    "audit-platform/frontend/src/components/workpaper/registry/entries/core.ts",
    "audit-platform/frontend/src/router/index.ts",
    "audit-platform/frontend/src/router/domains/auth.ts",
    "audit-platform/frontend/src/composables/useWpRenderer.ts",
    "backend/app/services/task_event_bus.py",
    "backend/app/services/event_bus.py",
    "backend/app/core/events/envelope.py",
    "backend/app/main.py",
    "backend/app/api/probes.py",
    "backend/app/models/phase15_models.py",
]

# spec 写成不存在的路径 → 实际路径
PATH_CORRECTIONS = {
    "backend/app/services/wp_render_strategies.py": "backend/app/routers/wp_render_strategies/__init__.py",
    "backend/app/services/dispatch_records.py": "backend/app/routers/dispatch_records.py",
    "backend/app/services/s_transaction_calculation.py": "backend/app/routers/s_transaction_calculation.py",
    "backend/scripts/gen_service_deps.py": "scripts/gen_service_deps.py",
}


def mtime(rel: str) -> str:
    f = ROOT / rel
    return (
        datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")
        if f.exists()
        else "MISSING"
    )


def strip_comments(src: str) -> str:
    """剥离注释与字符串，避免字符串字面量里的假命中。"""
    return re.sub(r"#[^\n]*", "", src)


def count_literal(text: str, needle: str) -> int:
    return text.count(needle)


def probe() -> dict:
    out: dict = {"root": str(ROOT), "probed_at": datetime.datetime.now().isoformat(timespec="seconds")}

    files: dict[str, dict] = {}
    for rel in TARGETS:
        f = ROOT / rel
        entry: dict = {"mtime": mtime(rel)}
        if f.exists():
            raw = f.read_text(encoding="utf-8", errors="replace")
            entry["bytes"] = len(raw.encode("utf-8"))
            entry["lines"] = len(raw.splitlines())
        else:
            entry["bytes"] = None
            entry["lines"] = None
        files[rel] = entry
    out["files"] = files

    # ── 后端真源差集（复用 generator AST 提取，禁止 literal_eval Callable）──
    srcs: dict[str, set[str]] = {}
    rd: set[str] = set()
    fr: set[str] = set()
    try:
        backend_root = ROOT / "backend"
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from scripts.gen.generate_component_capability_manifest import (  # type: ignore
            extract_observed_sources,
        )

        observed = extract_observed_sources()
        for name, values in observed.named_sets():
            srcs[name] = set(values)
        rd = set(observed.backend_renderer_types)
        fr = set(observed.frontend_registry_types)
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        out["sources_extract_error"] = f"{type(exc).__name__}: {exc}"

    manifest = ROOT / "backend/app/data/component_capabilities.json"
    mc: set[str] = set()
    exemptions = 0
    if manifest.exists():
        m = json.loads(manifest.read_text(encoding="utf-8"))
        mc = set(m.get("components", {}))
        exemptions = len(m.get("exemptions", []))

    out["sources"] = {
        "named_source_counts": {k: len(v) for k, v in srcs.items()},
        "backend_renderer_count": len(rd),
        "frontend_renderer_count": len(fr),
        "manifest_count": len(mc),
        "manifest_exemptions": exemptions,
        "backend_only": sorted(rd - fr),
        "frontend_only": sorted(fr - rd),
        "not_in_manifest_backend": sorted((rd - mc)),
        "not_in_manifest_frontend": sorted((fr - mc)),
        "manifest_only": sorted(mc - rd - fr),
    }

    htmlreg = ROOT / "audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts"

    # ── render-config 协调器 ─────────────────────────────────────────
    rcc = ROOT / "backend/app/routers/wp_render_config.py"
    if rcc.exists():
        tree = ast.parse(rcc.read_text(encoding="utf-8"))
        stages = {
            "load_render_subject": 0,
            "resolve_classification_sources": 0,
            "resolve_scope_redirect": 0,
            "load_common_render_facts": 0,
            "plan_sheets": 0,
            "materialize_sheet": 0,
            "finalize_render_response": 0,
        }
        text = rcc.read_text(encoding="utf-8")
        for name in stages:
            stages[name] = count_literal(text, name + "(")
        impl = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_get_render_config_impl"),
            None,
        )
        endpoint = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_render_config"),
            None,
        )
        out["render_config"] = {
            "total_lines": files["backend/app/routers/wp_render_config.py"]["lines"],
            "impl_start": impl.lineno if impl else None,
            "impl_lines": (impl.end_lineno - impl.lineno + 1) if impl else None,
            "endpoint_start": endpoint.lineno if endpoint else None,
            "stage_call_counts": stages,
            "stages_extracted": all(v > 0 for v in stages.values()),
        }

    contract = ROOT / "backend/app/schemas/render_config_contract.py"
    if contract.exists():
        tree = ast.parse(contract.read_text(encoding="utf-8"))
        cls = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "RenderConfigResponse"), None)
        fields: list[str] = []
        if cls:
            for stmt in cls.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.append(stmt.target.id)
        out["render_contract"] = {
            "model_lines": (cls.end_lineno - cls.lineno + 1) if cls else None,
            "field_count": len(fields),
            "fields": fields,
        }

    # ── 前端 registry / router ────────────────────────────────────────
    if htmlreg.exists():
        text = htmlreg.read_text(encoding="utf-8")
        out["frontend_registry"] = {
            "lines": files["audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts"]["lines"],
            "componentType_literal_count": count_literal(text, "componentType: '"),
            "has_assert_unique": "assertUniqueRegistryComponentTypes" in text,
            "unique_before_map": text.find("assertUniqueRegistryComponentTypes(REGISTRY_LIST)")
            < text.find("new Map(REGISTRY_LIST.map"),
            "getRendererEntry_sync": bool(
                re.search(r"export function getRendererEntry\([^)]*\)\s*:", text)
            ),
            "checks_map_values": "HTML_RENDERER_REGISTRY.values()" in text,
        }
    reg_index = ROOT / "audit-platform/frontend/src/components/workpaper/registry/index.ts"
    if reg_index.exists():
        t = reg_index.read_text(encoding="utf-8")
        out["registry_barrel"] = {
            "lines": files["audit-platform/frontend/src/components/workpaper/registry/index.ts"]["lines"],
            "uses_classifyDomain": "classifyDomain" in t,
            "uses_startsWith": "startsWith" in t,
            "reexport_only": "ORIGINAL_REGISTRY" in t,
            "has_entries_dir": (ROOT / "audit-platform/frontend/src/components/workpaper/registry/entries").is_dir(),
        }
    router = ROOT / "audit-platform/frontend/src/router/index.ts"
    if router.exists():
        t = router.read_text(encoding="utf-8")
        out["router"] = {
            "lines": files["audit-platform/frontend/src/router/index.ts"]["lines"],
            "path_literal_count": count_literal(t, "path: '"),
            "beforeEach_count": len(re.findall(r"\.beforeEach\(", t)),
            "has_domains_dir": (ROOT / "audit-platform/frontend/src/router/domains").is_dir(),
        }

    # ── lifespan ──────────────────────────────────────────────────────
    mainp = ROOT / "backend/app/main.py"
    if mainp.exists():
        tree = ast.parse(mainp.read_text(encoding="utf-8"))
        ls = next((n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"), None)
        workers = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_start_workers"), None)
        wtext = ast.get_source_segment(mainp.read_text(encoding="utf-8"), workers) or "" if workers else ""
        create_task_count = count_literal(wtext, "create_task(")
        out["lifespan"] = {
            "start": ls.lineno if ls else None,
            "lines": (ls.end_lineno - ls.lineno + 1) if ls else None,
            "has_registry": "StartupTaskSpec" in mainp.read_text(encoding="utf-8"),
            "worker_create_task_calls": create_task_count,
        }

    # ── 事件总线确定缺陷 ────────────────────────────────────────────
    teb = ROOT / "backend/app/services/task_event_bus.py"
    if teb.exists():
        tree = ast.parse(teb.read_text(encoding="utf-8"))
        pub = next((n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "publish"), None)
        src = ast.get_source_segment(teb.read_text(encoding="utf-8"), pub) or "" if pub else ""
        seg_ids = {
            "writes_idempotency_key": "idempotency_key=" in src,
            "dedup_by_trace_id_like": ".like(" in src,
            "generates_trace_id": "generate_trace_id" in src,
        }
        out["task_event_bus"] = {"publish_line": pub.lineno if pub else None, "checks": seg_ids}

    dr = ROOT / "backend/app/routers/dispatch_records.py"
    stc = ROOT / "backend/app/routers/s_transaction_calculation.py"
    bad_imports: dict[str, int] = {}
    if dr.exists():
        t = dr.read_text(encoding="utf-8")
        bad_imports["dispatch_records.py:from app.core.event_bus import"] = count_literal(t, "from app.core.event_bus import")
    if stc.exists():
        t = stc.read_text(encoding="utf-8")
        bad_imports["s_transaction_calculation.py:from app.core.event_bus import"] = count_literal(t, "from app.core.event_bus import")
    for rel in (
        "backend/app/services/review_workflow_service.py",
        "backend/app/services/independence_signing_service.py",
        "backend/app/routers/adjustments.py",
    ):
        f = ROOT / rel
        if f.exists():
            bad_imports[rel] = count_literal(f.read_text(encoding="utf-8"), "from app.core.event_bus import")
    out["bad_event_bus_imports"] = bad_imports

    # app.core.event_bus 是否真实存在
    out["app_core_event_bus_exists"] = (ROOT / "backend/app/core/event_bus.py").exists()

    out["path_corrections"] = {
        old: {
            "spec_path_exists": (ROOT / old).exists(),
            "actual_path": new,
            "actual_exists": (ROOT / new).exists(),
        }
        for old, new in PATH_CORRECTIONS.items()
    }
    return out


def main() -> int:
    data = probe()
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        s = data["sources"]
        print("== 真源差集 ==")
        if data.get("sources_extract_error"):
            print(f"  EXTRACT_ERROR: {data['sources_extract_error']}")
        for k, v in (s.get("named_source_counts") or {}).items():
            print(f"  source.{k}: {v}")
        for k in ("backend_renderer_count", "frontend_renderer_count", "manifest_count", "manifest_exemptions"):
            print(f"  {k}: {s[k]}")
        for k in ("backend_only", "frontend_only", "not_in_manifest_backend", "not_in_manifest_frontend", "manifest_only"):
            v = s[k]
            print(f"  {k} ({len(v)}): {v[:12]}" + (" ..." if len(v) > 12 else ""))
        rc = data.get("render_config", {})
        print("== render-config ==")
        print(f"  file lines={rc.get('total_lines')} impl=L{rc.get('impl_start')} ({rc.get('impl_lines')}行) endpoint=L{rc.get('endpoint_start')}")
        print(f"  stages_extracted={rc.get('stages_extracted')} calls={rc.get('stage_call_counts')}")
        print("== 前端 ==")
        for k, v in data.get("frontend_registry", {}).items():
            print(f"  registry.{k}: {v}")
        for k, v in data.get("router", {}).items():
            print(f"  router.{k}: {v}")
        print("== lifespan ==")
        for k, v in data.get("lifespan", {}).items():
            print(f"  {k}: {v}")
        print("== 事件总线 ==")
        for k, v in data.get("task_event_bus", {}).get("checks", {}).items():
            print(f"  publish.{k}: {v}")
        print("== 错误 import (from app.core.event_bus import) ==")
        for k, v in data.get("bad_event_bus_imports", {}).items():
            print(f"  {k}: {v}")
        print(f"  app/core/event_bus.py exists: {data.get('app_core_event_bus_exists')}")
        print("== spec 路径纠错 ==")
        for old, v in data.get("path_corrections", {}).items():
            print(f"  {old} -> {v['actual_path']} | spec_exists={v['spec_path_exists']} actual_exists={v['actual_exists']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
