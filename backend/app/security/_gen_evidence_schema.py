"""One-shot generator for the evidence manifest JSON Schema.

Writes ``.kiro/specs/procedure-delegation-visibility-isolation/evidence/
manifest.schema.json``. Kept as a checked-in generator so the schema can be
regenerated deterministically. Run: ``python -m app.security._gen_evidence_schema``.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.security.evidence_manifest import SCHEMA_PATH

SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "procedure-delegation-visibility-isolation/evidence/manifest.schema.json",
    "title": "Procedure Delegation Visibility Isolation Evidence Manifest",
    "description": (
        "Append-only acceptance evidence index. Runs are ordered and never "
        "overwritten; failed runs are retained. Artifact paths are spec-relative "
        "and must not contain '..' or be absolute. SHA-256 and size are "
        "recomputed from raw bytes by the Completion_Guard."
    ),
    "type": "object",
    "additionalProperties": False,
    "required": ["spec", "schema_version", "runs"],
    "properties": {
        "spec": {"type": "string", "const": "procedure-delegation-visibility-isolation"},
        "schema_version": {"type": "string", "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+$"},
        "created_at": {"type": "string"},
        "runs": {"type": "array", "items": {"$ref": "#/definitions/run"}},
    },
    "definitions": {
        "run": {
            "type": "object",
            "additionalProperties": False,
            "required": ["run_id", "task_id", "status", "artifacts"],
            "properties": {
                "run_id": {"type": "string", "minLength": 1},
                "seq": {"type": "integer", "minimum": 1},
                "task_id": {"type": "string", "minLength": 1},
                "test_ids": {"type": "array", "items": {"type": "string"}},
                "criterion_ids": {"type": "array", "items": {"type": "string"}},
                "status": {
                    "type": "string",
                    "enum": ["passed", "failed", "not_run", "error", "skipped"],
                },
                "command": {"type": ["string", "null"]},
                "started_at": {"type": "string"},
                "finished_at": {"type": "string"},
                "notes": {"type": "string"},
                "artifacts": {"type": "array", "items": {"$ref": "#/definitions/artifact"}},
            },
        },
        "artifact": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "sha256", "size"],
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Spec-relative path; must not contain '..' or be absolute.",
                    "allOf": [
                        {"not": {"pattern": r"\.\."}},
                        {"pattern": r"^(?![/\\])(?![A-Za-z]:).+"},
                    ],
                },
                "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "size": {"type": "integer", "minimum": 0},
                "media_type": {"type": "string"},
            },
        },
    },
}


def main() -> int:
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(
        json.dumps(SCHEMA, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
