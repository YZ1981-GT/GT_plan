# -*- coding: utf-8 -*-
"""One-shot capture for the curated-entry-facility Task 1 baseline fixture.

Why this exists (environment blocker, precisely):
    `generate_workpaper_sync_manifest.build_manifest` cannot run end-to-end from live
    source on this branch. Two independent reasons, both observed, not assumed:
      1. `discover_source()` (Node AST) yields sourceDigest a18a531d… which no longer
         matches the reviewed overlay.approved_source_digest d9fddb64… -> the digest gate
         inside build_manifest fails closed (this is by design; the mount inventory drifted).
      2. Even bypassing the gate, `derive_entry_profile` scans live frontend files, and the
         inbound-reference set has drifted since the manifest was committed (e.g. a new
         `registry/entries/programs.ts` referrer bumps inbound_reference_count 1 -> 2), so
         live derivation cannot reproduce the committed manifest bytes.

    The committed manifest embeds every discovery fact we need to run the REAL build_manifest:
    all 277 mounts (276 template_ast physical mounts + 1 registry_ast dispatcher), the reviewed
    sourceDigest, and stats.byComponent. We reconstruct a faithful discovery dict from those
    embedded facts. Feeding it to the real build_manifest reproduces the committed entry
    structure exactly; the only field that differs from the committed bytes is `profile_source`
    (because build_manifest re-derives it against live source). We capture the real run's output
    as the frozen baseline. The Task 1 guard then proves the additive invariant against it and,
    more importantly, proves the drift-immune relative invariant (absent == empty curated).

Run from repo root:  python backend/tests/workpaper_sync/data/_capture_curated_baseline.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_GEN = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_MANIFEST = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
_OVERLAY = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
_HERE = Path(__file__).resolve().parent

_DISCOVERY_FIXTURE = _HERE / "curated_baseline_discovery.json"
_BASELINE_MANIFEST = _HERE / "curated_baseline_manifest.json"
_BASELINE_FRONTEND = _HERE / "curated_baseline_frontend.generated.ts"


def _load_generator():
    spec = importlib.util.spec_from_file_location("curated_capture_generator", _GEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reconstruct_discovery(manifest: dict) -> dict:
    """Reconstruct the discovery dict build_manifest consumes, from the committed manifest.

    Physical mounts are the template_ast facts; the dynamic dispatcher is the registry_ast
    fact. These two lists are exactly what `discover_source()` returns, split by sourceKind.
    """
    mounts: list[dict] = []
    dispatchers: list[dict] = []
    for entry in manifest["entries"]:
        for mount in entry["mounts"]:
            if mount.get("sourceKind") == "template_ast":
                mounts.append(mount)
            else:
                dispatchers.append(mount)
    mounts.sort(key=lambda item: item["mountId"])
    dispatchers.sort(key=lambda item: item["mountId"])
    if len(mounts) != manifest["stats"]["mount_count"]:
        raise SystemExit(
            f"reconstructed mount_count {len(mounts)} != manifest {manifest['stats']['mount_count']}"
        )
    if len(dispatchers) != manifest["stats"]["dispatcher_count"]:
        raise SystemExit(
            f"reconstructed dispatcher_count {len(dispatchers)} "
            f"!= manifest {manifest['stats']['dispatcher_count']}"
        )
    return {
        "schemaVersion": 1,
        "sourceDigest": manifest["source_digest"],
        "mounts": mounts,
        "dispatchers": dispatchers,
        "stats": {"byComponent": manifest["stats"]["by_component"]},
    }


def main() -> int:
    generator = _load_generator()
    manifest_disk = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    overlay = json.loads(_OVERLAY.read_text(encoding="utf-8"))
    if "curated_entries" in overlay:
        raise SystemExit("overlay already has curated_entries; baseline capture expects none")

    discovery = reconstruct_discovery(manifest_disk)

    # Run the REAL build_manifest twice and require determinism before freezing anything.
    built_a = generator.build_manifest(discovery, overlay)
    built_b = generator.build_manifest(discovery, overlay)
    manifest_bytes_a = generator.render_manifest(built_a)
    manifest_bytes_b = generator.render_manifest(built_b)
    frontend_bytes_a = generator.render_frontend(built_a)
    frontend_bytes_b = generator.render_frontend(built_b)
    if manifest_bytes_a != manifest_bytes_b or frontend_bytes_a != frontend_bytes_b:
        raise SystemExit("build_manifest is not deterministic on the reconstructed discovery")

    # Freeze the discovery fixture with newline='\n' so the guard reads identical bytes on Windows.
    discovery_text = json.dumps(discovery, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _DISCOVERY_FIXTURE.write_text(discovery_text, encoding="utf-8", newline="\n")
    _BASELINE_MANIFEST.write_text(manifest_bytes_a, encoding="utf-8", newline="\n")
    _BASELINE_FRONTEND.write_text(frontend_bytes_a, encoding="utf-8", newline="\n")

    print(f"[captured] discovery fixture: {_DISCOVERY_FIXTURE.name} "
          f"mounts={len(discovery['mounts'])} dispatchers={len(discovery['dispatchers'])} "
          f"sourceDigest={discovery['sourceDigest'][:16]}")
    print(f"[captured] baseline manifest: {_BASELINE_MANIFEST.name} "
          f"bytes={len(manifest_bytes_a.encode('utf-8'))} digest={built_a['manifest_digest'][:16]}")
    print(f"[captured] baseline frontend: {_BASELINE_FRONTEND.name} "
          f"bytes={len(frontend_bytes_a.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
