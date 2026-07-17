"""Append-only Evidence Manifest writer + precheck (Task 1 evidence scaffolding).

Implements the spec Evidence_Manifest tooling:
  * fixed manifest path ``.kiro/specs/.../evidence/manifest.json``
  * fixed schema path  ``.kiro/specs/.../evidence/manifest.schema.json``
  * append-only run writer (failed runs are retained, never overwritten)
  * precheck: artifact relative paths must stay inside the spec dir (reject
    ``..`` and absolute paths); SHA-256 and size are recomputed from raw bytes
    and compared to the recorded values.

Stdlib-only for the core append/precheck logic. ``jsonschema`` is used opportun-
istically for structural validation when installed (Completion_Guard, Task 18,
performs the authoritative full validation).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[3]
SPEC_DIR = _REPO_ROOT / ".kiro" / "specs" / "procedure-delegation-visibility-isolation"
EVIDENCE_DIR = SPEC_DIR / "evidence"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
SCHEMA_PATH = EVIDENCE_DIR / "manifest.schema.json"

SCHEMA_VERSION = "1.0.0"
_VALID_STATUSES = ("passed", "failed", "not_run", "error", "skipped")


# ---------------------------------------------------------------------------
# Path safety + hashing
# ---------------------------------------------------------------------------
def is_unsafe_rel_path(rel: str) -> bool:
    """True if ``rel`` escapes the spec dir (contains ``..`` or is absolute)."""
    if rel is None:
        return True
    p = str(rel).replace("\\", "/")
    if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
        return True  # absolute path
    return any(seg == ".." for seg in p.split("/"))


def sha256_and_size(abs_path: Path) -> tuple[str, int]:
    """Recompute SHA-256 (hex) and byte size from an artifact's raw bytes."""
    h = hashlib.sha256()
    size = 0
    with open(abs_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Manifest load / init
# ---------------------------------------------------------------------------
def empty_manifest() -> dict[str, Any]:
    return {
        "spec": "procedure-delegation-visibility-isolation",
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "runs": [],
    }


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not Path(manifest_path).exists():
        return empty_manifest()
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def _resolve_artifact(rel: str, spec_dir: Path) -> Path:
    if is_unsafe_rel_path(rel):
        raise ValueError(f"unsafe artifact relative path (contains '..' or absolute): {rel!r}")
    return spec_dir / str(rel).replace("\\", "/")


def build_artifact_record(rel_path: str, spec_dir: Path = SPEC_DIR,
                          media_type: str | None = None) -> dict[str, Any]:
    """Build a single artifact record with freshly computed SHA-256 + size."""
    abs_path = _resolve_artifact(rel_path, spec_dir)
    if not abs_path.exists():
        raise FileNotFoundError(f"artifact not found: {abs_path}")
    sha, size = sha256_and_size(abs_path)
    rec: dict[str, Any] = {
        "path": str(rel_path).replace("\\", "/"),
        "sha256": sha,
        "size": size,
    }
    if media_type:
        rec["media_type"] = media_type
    return rec


# ---------------------------------------------------------------------------
# Append-only run writer
# ---------------------------------------------------------------------------
def append_run(
    *,
    task_id: str,
    status: str,
    artifacts: Iterable[str | Mapping[str, Any]] = (),
    test_ids: Iterable[str] = (),
    criterion_ids: Iterable[str] = (),
    command: str | None = None,
    run_id: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    notes: str | None = None,
    manifest_path: Path = MANIFEST_PATH,
    spec_dir: Path = SPEC_DIR,
) -> dict[str, Any]:
    """Append one Criterion_Run to the manifest. Existing runs are never mutated.

    ``artifacts`` may be relative-path strings (SHA-256/size computed here) or
    pre-built artifact records. Returns the appended run record.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; expected one of {_VALID_STATUSES}")

    manifest = load_manifest(manifest_path)
    runs = manifest.setdefault("runs", [])

    art_records: list[dict[str, Any]] = []
    for a in artifacts:
        if isinstance(a, Mapping):
            rel = a.get("path")
            if is_unsafe_rel_path(rel):
                raise ValueError(f"unsafe artifact relative path: {rel!r}")
            # Recompute from disk to guarantee integrity even for prebuilt records.
            art_records.append(build_artifact_record(rel, spec_dir, a.get("media_type")))
        else:
            art_records.append(build_artifact_record(str(a), spec_dir))

    seq = len(runs) + 1
    finished = finished_at or _now()
    run = {
        "run_id": run_id or f"{task_id}-{seq:04d}-{finished}",
        "seq": seq,
        "task_id": str(task_id),
        "test_ids": list(test_ids),
        "criterion_ids": list(criterion_ids),
        "status": status,
        "command": command,
        "started_at": started_at or finished,
        "finished_at": finished,
        "artifacts": art_records,
    }
    if notes:
        run["notes"] = notes

    runs.append(run)  # append-only
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return run


# ---------------------------------------------------------------------------
# Precheck
# ---------------------------------------------------------------------------
def precheck(
    manifest_path: Path = MANIFEST_PATH,
    schema_path: Path = SCHEMA_PATH,
    spec_dir: Path = SPEC_DIR,
) -> list[str]:
    """Validate the manifest. Returns a list of problems (empty == OK).

    Checks: manifest + schema load as JSON; (optional) jsonschema conformance;
    every artifact relative path is safe (no ``..``/absolute); recomputed
    SHA-256 and size match the recorded values.
    """
    problems: list[str] = []

    mp, sp = Path(manifest_path), Path(schema_path)
    if not sp.exists():
        problems.append(f"schema missing: {sp}")
    if not mp.exists():
        problems.append(f"manifest missing: {mp}")
        return problems

    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"manifest is not valid JSON: {exc}"]

    schema = None
    if sp.exists():
        try:
            schema = json.loads(sp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"schema is not valid JSON: {exc}")

    # Optional structural validation via jsonschema (authoritative in Task 18).
    if schema is not None:
        try:
            import jsonschema  # type: ignore

            jsonschema.validate(instance=manifest, schema=schema)
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 — ValidationError etc.
            problems.append(f"manifest does not conform to schema: {exc}")

    runs = manifest.get("runs")
    if not isinstance(runs, list):
        problems.append("manifest.runs must be a list")
        return problems

    for run in runs:
        rid = run.get("run_id", "<no run_id>")
        if run.get("status") not in _VALID_STATUSES:
            problems.append(f"run {rid}: invalid status {run.get('status')!r}")
        for art in run.get("artifacts", []):
            rel = art.get("path")
            if is_unsafe_rel_path(rel):
                problems.append(f"run {rid}: unsafe artifact path {rel!r}")
                continue
            abs_path = spec_dir / str(rel).replace("\\", "/")
            if not abs_path.exists():
                problems.append(f"run {rid}: artifact missing on disk: {rel}")
                continue
            sha, size = sha256_and_size(abs_path)
            if art.get("sha256") != sha:
                problems.append(
                    f"run {rid}: SHA-256 mismatch for {rel} "
                    f"(recorded {art.get('sha256')}, recomputed {sha})"
                )
            if art.get("size") != size:
                problems.append(
                    f"run {rid}: size mismatch for {rel} "
                    f"(recorded {art.get('size')}, recomputed {size})"
                )
    return problems


def _main() -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    problems = precheck()
    if problems:
        print(f"[evidence-precheck] {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"[evidence-precheck] OK ({MANIFEST_PATH})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
