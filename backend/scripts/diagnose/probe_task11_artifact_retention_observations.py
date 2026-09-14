# -*- coding: utf-8 -*-
"""Task 11 观测采集：把 CanonicalArtifactRepository / OOXML 安全门 / RetentionPolicy 的
**实际运行观测量**落成可复算 evidence。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 2.4, 3.4, 5.6, 5.9, 5.11, 9.6, 9.7, 10.7, 10.8, 14.11
Properties: P5 / P17 / P42 / P60

═══ 与守卫的分工 ═══

守卫（`backend/tests/workpaper_sync/test_task11_*.py`）负责**判定**；本脚本负责把同一批
事实的**数值**记录下来，便于复盘时不重跑测试也能看到「峰值内存多少、门顺序是什么、
诊断码映射是什么」。每个 `observed_*` 字段都注明由哪条测试重算 —— 这样 evidence
不是手填的，而是「可被 pytest 复现」的。

只读：全部产物写在系统临时目录，跑完删除；不碰真实 `storage/`、不连数据库
（DB 侧观测在 `test_task11_retention_orphan_pg.py` 的快照里）。

用法（仓库根）:
    python backend/scripts/diagnose/probe_task11_artifact_retention_observations.py \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task11-artifact-retention/fs_observations.json
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tracemalloc
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

from app.services.workpaper_sync.artifacts import (  # noqa: E402
    ArtifactPathError,
    CanonicalArtifactRepository,
    CrossVolumeError,
    DownloadAuthorization,
    FileInUseError,
    classify_os_error,
    same_volume,
    sha12,
)
from app.services.workpaper_sync.limits import BudgetExceededError, load_limits  # noqa: E402
from app.services.workpaper_sync.models import ArtifactState  # noqa: E402
from app.services.workpaper_sync.ooxml_security import (  # noqa: E402
    GATE_ORDER,
    OoxmlSecurityError,
    OoxmlStructureError,
    validate_ooxml_artifact,
)
from app.services.workpaper_sync.retention import (  # noqa: E402
    REFERENCE_SOURCES,
    load_retention_policy,
)

_CT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/></Types>'
)
_WB = b'<?xml version="1.0"?><workbook><sheets/></workbook>'


def _xlsx(**extra: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CT)
        zf.writestr("xl/workbook.xml", _WB)
        for name, payload in extra.items():
            zf.writestr(name.replace("__", "/"), payload)
    return buf.getvalue()


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(REPO), capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        return ""


def collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部文件系统观测
    lim = load_limits()
    policy = load_retention_policy()
    base = Path(tempfile.mkdtemp(prefix="tmp_task11_probe_"))
    (base / "storage").mkdir()
    (base / "definition_store").mkdir()
    repo = CanonicalArtifactRepository(base)
    project, wp, delivery = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    out: dict[str, Any] = {
        "probe_status": "ok",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "repo_volume": os.path.splitdrive(str(REPO))[0],
            "temp_volume": os.path.splitdrive(tempfile.gettempdir())[0],
            "source_commit": _git("rev-parse", "--short", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        },
        "recompute": {
            "command": (
                "python -m pytest backend/tests/workpaper_sync/"
                "test_task11_artifact_repository.py "
                "backend/tests/workpaper_sync/test_task11_retention_orphan_pg.py"
            ),
            "note": "每个 observed_* 字段都由下方 recomputed_by 指名的测试重算；手填不能过守卫。",
        },
    }
    try:
        # ── 预算配置（Requirement 14.11 单一真源）──────────────────────
        out["budgets"] = {
            "recomputed_by": "test_limits_config_matches_requirement_14_11_exactly",
            "max_compressed_bytes": lim.max_compressed_bytes,
            "max_expanded_bytes": lim.max_expanded_bytes,
            "max_zip_entries": lim.max_zip_entries,
            "max_compression_ratio": lim.max_compression_ratio,
            "max_table_rows": lim.max_table_rows,
            "max_projection_fields": lim.max_projection_fields,
            "chunk_bytes": lim.chunk_bytes,
            "peak_memory_budget_bytes": lim.peak_memory_budget_bytes,
            "ooxml_policy_version": lim.ooxml.policy_version,
        }

        # ── staging + fsync（Task 7 fs1 对齐）─────────────────────────
        staged = repo.stage_bytes(
            project_id=project, wp_id=wp, payload=_xlsx(), document_type="xlsx"
        )
        dir_fsync: dict[str, Any] = {"supported": True, "stage": None}
        try:
            fd = os.open(str(staged.path.parent), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            dir_fsync = {
                "supported": False,
                "stage": "open" if isinstance(exc, PermissionError) else "fsync",
                "exc_type": type(exc).__name__,
                "errno": exc.errno,
            }
        out["staging"] = {
            "recomputed_by": "test_contract_directory_fsync_unsupported_and_never_claimed",
            "artifact_stage_id_independent_of_operation": True,
            "relative_path": staged.relative_path,
            "file_fsync_performed": staged.file_fsync_performed,
            "directory_fsync_performed": staged.directory_fsync_performed,
            "observed_directory_fsync": dir_fsync,
            "same_volume_as_publish_target": staged.same_volume_as_publish_target,
            "streaming_sha256": staged.sha256,
        }

        # ── 内容寻址不可变发布 ────────────────────────────────────────
        first = repo.publish_representation(entry_id="probe.entry", generation=7, staged=staged)
        again = repo.publish_representation(
            entry_id="probe.entry", generation=7,
            staged=repo.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx(), document_type="xlsx"
            ),
        )
        out["publish"] = {
            "recomputed_by": "test_contract_target_name_pattern_and_idempotency_scope",
            "target_name": first.path.name,
            "target_name_pattern": "{generation:09d}-{sha256[:12]}{ext}",
            "relative_path": first.relative_path,
            "sha256": first.sha256,
            "sha12": sha12(first.sha256),
            "republish_same_path": again.relative_path == first.relative_path,
            "republish_reused_without_replace": again.reused,
            "verified_before_publish": first.verified_before_publish,
            "verified_after_publish": first.verified_after_publish,
            "idempotency_scope": "path_and_sha256",
        }

        # ── Windows 占用 / 跨卷诊断码 ─────────────────────────────────
        diag: dict[str, Any] = {
            "recomputed_by": "test_file_in_use_diagnostics_for_target_and_source",
        }
        proj_root = repo.layout.project_root(project)
        src, dst = proj_root / "probe_src.bin", proj_root / "probe_dst.bin"
        src.write_bytes(b"new")
        dst.write_bytes(b"old")
        try:
            with dst.open("rb"):
                repo.atomic_replace(src, dst)
        except FileInUseError as exc:
            diag["target_occupied"] = {
                "code": exc.error_code, "winerror": exc.winerror, "held": exc.held,
                "old_content_preserved": dst.read_bytes() == b"old",
            }
        try:
            with src.open("rb"):
                repo.atomic_replace(src, dst)
        except FileInUseError as exc:
            diag["source_occupied"] = {
                "code": exc.error_code, "winerror": exc.winerror, "held": exc.held,
            }
        cross_dir = None
        for candidate in (Path(tempfile.gettempdir()), REPO):
            if not same_volume(candidate, proj_root):
                cross_dir = Path(tempfile.mkdtemp(dir=str(candidate), prefix="tmp_task11_xvol_"))
                break
        if cross_dir is None:
            diag["cross_volume"] = {"verified": False, "reason": "single_volume_environment"}
        else:
            try:
                xsrc = cross_dir / "payload.bin"
                xsrc.write_bytes(b"payload")
                try:
                    repo.atomic_replace(xsrc, proj_root / "xvol_dst.bin")
                    diag["cross_volume"] = {"verified": False, "reason": "unexpectedly_succeeded"}
                except CrossVolumeError as exc:
                    diag["cross_volume"] = {
                        "verified": True, "code": exc.error_code, "winerror": exc.winerror,
                        "source_survived": xsrc.exists(),
                        "target_absent": not (proj_root / "xvol_dst.bin").exists(),
                    }
            finally:
                shutil.rmtree(cross_dir, ignore_errors=True)
        synthesized = {}
        for label, (errno_, winerror) in {
            "target_occupied": (13, 5), "source_occupied": (13, 32),
            "cross_volume": (18, 17), "other_io": (13, 1224),
        }.items():
            exc = OSError(errno_, "probe")
            exc.winerror = winerror  # type: ignore[attr-defined]
            synthesized[label] = classify_os_error(exc)
        diag["classifier_matrix"] = synthesized
        out["windows_diagnostics"] = diag

        # ── OOXML 安全门（顺序 + 逐门拒绝码）──────────────────────────
        clean = repo.stage_bytes(
            project_id=project, wp_id=wp, payload=_xlsx(), document_type="xlsx"
        )
        report = validate_ooxml_artifact(clean.path, document_type="xlsx")
        gates: dict[str, Any] = {
            "recomputed_by": "test_contract_validation_gate_order_and_masquerade",
            "gate_order": list(GATE_ORDER),
            "observed_clean_gates": list(report.gates),
            "observed_detected_document_type": report.detected_document_type,
        }
        cases = {
            "non_zip": (b"<html/>", "xlsx"),
            "polyglot_prefix": (b"MZ" * 8 + _xlsx(), "xlsx"),
            "masquerade": (_xlsx(), "docx"),
            "traversal_entry": (_xlsx(**{"..__evil.xml": b"x"}), "xlsx"),
            "macro_part": (_xlsx(**{"xl__vbaProject.bin": b"MZ"}), "xlsx"),
            "embedded_object": (_xlsx(**{"xl__embeddings__ole.bin": b"OLE"}), "xlsx"),
            "external_relationship": (
                _xlsx(
                    **{
                        "xl___rels__workbook.xml.rels": (
                            b'<Relationships><Relationship Target="http://evil/x" '
                            b'TargetMode="External"/></Relationships>'
                        )
                    }
                ),
                "xlsx",
            ),
        }
        observed_rejections: dict[str, Any] = {}
        for label, (payload, doc_type) in cases.items():
            st = repo.stage_bytes(
                project_id=project, wp_id=wp, payload=payload, document_type=doc_type
            )
            try:
                validate_ooxml_artifact(st.path, document_type=doc_type)
                observed_rejections[label] = {"rejected": False}
            except (OoxmlSecurityError, OoxmlStructureError) as exc:
                observed_rejections[label] = {
                    "rejected": True, "gate": exc.gate, "error_code": exc.error_code
                }
        gates["observed_rejections"] = observed_rejections
        out["ooxml_gates"] = gates

        # ── zip bomb：内存峰值 ────────────────────────────────────────
        bomb = _xlsx(**{"xl__bomb.bin": b"\0" * (64 * 1024 * 1024)})
        bomb_staged = repo.stage_incoming(
            project_id=project, wp_id=wp, delivery_id=delivery,
            chunks=[bomb], document_type="xlsx",
        )
        scaled = CanonicalArtifactRepository(
            base, limits=dataclasses.replace(lim, max_expanded_bytes=8 * 1024 * 1024)
        )
        tracemalloc.start()
        try:
            sealed = scaled.seal_incoming(bomb_staged, delivery_id=delivery)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        out["zip_bomb"] = {
            "recomputed_by": "test_property_17_zip_bomb_is_quarantined_with_bounded_memory",
            "archive_bytes": bomb_staged.size_bytes,
            "declared_expanded_bytes": 64 * 1024 * 1024,
            "expanded_cap_used": 8 * 1024 * 1024,
            "sealed_state": sealed.state.value,
            "durable_at_is_null": sealed.durable_at is None,
            "rejection_error_code": sealed.rejection_error_code,
            "rejection_gate": sealed.rejection_gate,
            "observed_peak_traced_bytes": peak,
            "peak_within_budget": peak < lim.peak_memory_budget_bytes,
        }

        # ── incoming sealing 两支 ─────────────────────────────────────
        d2 = uuid.uuid4()
        good = repo.seal_incoming(
            repo.stage_incoming(
                project_id=project, wp_id=wp, delivery_id=d2,
                chunks=[_xlsx()], document_type="xlsx",
            ),
            delivery_id=d2,
        )
        release_blocked = None
        try:
            repo.release_quarantined(sealed)
        except Exception as exc:  # noqa: BLE001 - 记录 error_code
            release_blocked = getattr(exc, "error_code", type(exc).__name__)
        promote_blocked = None
        try:
            repo.promote_incoming_to_published(good)
        except Exception as exc:  # noqa: BLE001
            promote_blocked = getattr(exc, "error_code", type(exc).__name__)
        unauthorized = None
        try:
            repo.open_quarantined_for_download(
                sealed,
                authorization=DownloadAuthorization(
                    granted=False, actor_id=None, action="download_only"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            unauthorized = getattr(exc, "error_code", type(exc).__name__)
        out["incoming"] = {
            "recomputed_by": "test_property_17_incoming_sealing_is_delivery_scoped_and_durable"
                             " / test_property_17_quarantine_is_permanent_and_download_only",
            "durable_relative_path": good.relative_path,
            "durable_state": good.state.value,
            "durable_has_durable_at": good.durable_at is not None,
            "quarantined_relative_path": sealed.relative_path,
            "sealing_path_is_delivery_scoped": f".incoming/{wp}/{d2}/" in good.relative_path,
            "sealing_path_contains_no_operation_id": "operation" not in good.relative_path,
            "release_quarantined_error_code": release_blocked,
            "promote_to_published_error_code": promote_blocked,
            "unauthorized_download_error_code": unauthorized,
        }

        # ── candidate 隔离 ────────────────────────────────────────────
        candidate = repo.stage_upgrade_candidate(
            staged=repo.stage_bytes(
                project_id=project, wp_id=wp, payload=_xlsx(**{"cand.xml": b"<c/>"}),
                document_type="xlsx",
            ),
            entry_id="probe.entry", equivalence_report=b'{"visible_equivalent":true}',
        )
        finalized = repo.finalize_candidate_artifact(candidate=candidate, generation=8)
        out["candidate"] = {
            "recomputed_by": "test_candidate_is_non_current_and_outside_resolver_namespace"
                             " / test_finalize_candidate_copies_and_verifies_digest_before_and_after",
            "candidate_relative_path": candidate.relative_path,
            "equivalence_relative_path": candidate.equivalence_relative_path,
            "verified_before_move": candidate.verified_before_move,
            "verified_after_move": candidate.verified_after_move,
            "finalized_relative_path": finalized.relative_path,
            "candidate_file_survives_finalize": candidate.path.exists(),
            "versions_namespace_after": repo.scan_versions_namespace(project, wp),
            "candidate_in_versions_namespace": any(
                ".upgrade-candidates" in p
                for p in repo.scan_versions_namespace(project, wp)
            ),
        }

        # ── 路径安全（Property 42）───────────────────────────────────
        escapes = {
            "traversal_relative": r"..\..\..\outside.xlsx",
            "traversal_posix_style": "../../../outside.xlsx",
            "absolute_outside": str(Path(tempfile.gettempdir()) / "tmp_task11_evil.xlsx"),
            "unc_path": r"\\127.0.0.1\C$\tmp_task11_evil.xlsx",
        }
        path_obs: dict[str, Any] = {
            "recomputed_by": "test_contract_path_safety_cases_all_rejected",
            "resolution_rule": "os.path.realpath 后必须仍等于项目根或以项目根为祖先",
        }
        for label, rel in escapes.items():
            try:
                repo.resolve_within_project(project, rel)
                path_obs[label] = {"accepted": True}
            except ArtifactPathError as exc:
                path_obs[label] = {"accepted": False, "reason": exc.reason}
        path_obs["inside_ok"] = {
            "accepted": bool(repo.resolve_within_project(project, r"wp\artifact.xlsx"))
        }
        out["path_safety"] = path_obs

        # ── definition store / bundle / marker ───────────────────────
        payload = b'{"schema_version":"definition-bundle:v1"}'
        bundle = repo.publish_bundle_canonical_bytes(
            project_id=project, wp_id=wp, canonical_bytes=payload
        )
        marker = repo.publish_typed_null_marker(
            project_id=project, wp_id=wp, marker_id="contract:none:v1",
            canonical_payload=b'{"slot":"contract","value":"none"}',
        )
        out["definition_store"] = {
            "recomputed_by": "test_definition_bundle_and_marker_use_content_addressed_immutable_publish",
            "bundle_relative_path": bundle.relative_path,
            "bundle_sha256_equals_content": bundle.sha256
            == hashlib.sha256(payload).hexdigest(),
            "bundle_republish_reused": repo.publish_bundle_canonical_bytes(
                project_id=project, wp_id=wp, canonical_bytes=payload
            ).reused,
            "marker_relative_path": marker.relative_path,
        }

        # ── retention 策略快照 ───────────────────────────────────────
        out["retention_policy"] = {
            "recomputed_by": "test_retention_policy_declares_every_class_used_by_production_code"
                             " /（DB 侧）test_task11_retention_orphan_pg.py",
            "policy_version": policy.policy_version,
            "class_count": len(policy.classes),
            "classes": {
                name: {
                    "sensitivity": k.sensitivity,
                    "ttl_hours": k.ttl_hours,
                    "grace_hours": k.grace_hours,
                    "deletable": k.deletable,
                    "honor_legal_hold": k.honor_legal_hold,
                    "requires_orphaned_at": k.requires_orphaned_at,
                    "age_anchor": k.age_anchor,
                    "access_roles": list(k.access_roles),
                }
                for name, k in sorted(policy.classes.items())
            },
            "alert_retain_reasons": sorted(policy.alert_retain_reasons),
            "reference_source_count": len(REFERENCE_SOURCES),
            "reference_sources": [
                f"{s.table}.{s.column}" for s in REFERENCE_SOURCES
            ],
        }

        # ── 预算门边界（N-1 / N / N+1）───────────────────────────────
        boundaries: dict[str, Any] = {
            "recomputed_by": "test_property_60_scalar_budget_boundaries"
                             " / test_property_60_compression_ratio_boundaries"
                             " / test_property_60_table_rows_and_projection_fields_boundaries"
                             " / test_property_60_zip_entry_boundaries_end_to_end",
        }
        for budget, gate in (
            ("max_compressed_bytes", lim.assert_compressed_size),
            ("max_expanded_bytes", lim.assert_expanded_size),
            ("max_zip_entries", lim.assert_zip_entries),
            ("max_table_rows", lim.assert_table_rows),
            ("max_projection_fields", lim.assert_projection_fields),
        ):
            limit = getattr(lim, budget)
            row: dict[str, Any] = {"limit": limit}
            for label, value in (("n_minus_1", limit - 1), ("n", limit), ("n_plus_1", limit + 1)):
                try:
                    gate(value)
                    row[label] = "accepted"
                except BudgetExceededError:
                    row[label] = "rejected"
            boundaries[budget] = row
        ratio_row: dict[str, Any] = {"limit": lim.max_compression_ratio}
        for label, expanded in (
            ("n_minus_1", 1000 * (lim.max_compression_ratio - 1)),
            ("n", 1000 * lim.max_compression_ratio),
            ("n_plus_1", 1000 * lim.max_compression_ratio + 1),
        ):
            try:
                lim.assert_compression_ratio(compressed=1000, expanded=expanded)
                ratio_row[label] = "accepted"
            except BudgetExceededError:
                ratio_row[label] = "rejected"
        boundaries["max_compression_ratio"] = ratio_row
        out["budget_boundaries"] = boundaries

        assert ArtifactState.durable  # 触发一次枚举引用，防未使用导入被误删
        return out
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 11 文件系统/安全/预算观测采集")
    ap.add_argument("--out", metavar="PATH", help="观测 JSON 落盘路径")
    args = ap.parse_args()
    try:
        data = collect()
    except Exception as exc:  # noqa: BLE001 - 采集失败必须显式记录，不静默产出空文件
        data = {"probe_status": "error", "error": f"{type(exc).__name__}: {exc}"}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"落盘: {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        print(text)
    return 0 if data.get("probe_status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
