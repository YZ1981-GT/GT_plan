# -*- coding: utf-8 -*-
"""V151 schema 行为守卫：在**真实 PostgreSQL** 上验证约束会拒绝违规数据。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 9
Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 3.1, 3.6, 3.7, 4.1, 4.11, 5.4, 5.5, 5.10, 8.1, 12.10, 12.11, 13.5
Properties: P4 / P5 / P10 / P11 / P18 / P62 / P64 / P68 / P69

═══ 为什么判据必须是「真实 PG 拒绝插入」而不是「DDL 文本里有 CHECK」 ═══

只断言迁移文本包含 `CHECK`/`UNIQUE` 属于假绿第②源（grep 式守卫）：把
`CHECK (state IN (...))` 改成 `CHECK (true)`、把 trigger body 改成 `RETURN NEW`、
把 partial unique 的 WHERE 条件放宽，文本里 `CHECK`/`UNIQUE` 依然存在，守卫全绿。

故本文件的每条判据都是**行为判据**：
  1. 把 `backend/migrations/V151__*.sql` 的**真实文本**用 `MigrationRunner._split_sql_statements`
     （生产用的同一个切分器）拆开，逐条应用到真实 PostgreSQL 的 scratch schema；
  2. 建一套完整合法「世界」（正控制：合法数据必须能落库，含同 content version 的两个
     representation generation、一个 application + 两个 delivery + 1 primary/2 duplicate）；
  3. 跑 ~70 条**违规插入/更新/删除**（负控制），每条**必须被数据库拒绝**；
  4. 再跑一遍全部语句证明幂等；跑 R151 证明可回滚、再前滚证明可重建。

⇒ 改坏 V151 的任何一条约束（CHECK 放宽 / trigger 短路 / UNIQUE 去掉 / partial unique
   WHERE 放宽），对应负控制会变成「未被拒绝」⇒ 打红。变异四态统计见
   `backend/scripts/diagnose/mutate_task9_v151_schema_guards.py`。

═══ 隔离与「不写业务表」 ═══

scratch schema 名固定 `tmp_task9_v151_<hex>`，且 `search_path` **只含该 schema**
（不含 public）：`projects/users/working_paper` 三张前置表在 scratch 内建**桩表**，
因此 `ALTER TABLE working_paper ADD COLUMN` 与 revision 0 回填 SQL 打到桩表上，
物理上不可能触到业务库的 `public.working_paper`。测试结束 DROP SCHEMA CASCADE。

═══ 连库写法（memory 已记的坑）═══

全部快照由**一次 `asyncio.run`** 取回（module 级 fixture）；不给每个测试各自开 async，
否则共享连接池被污染，第二个测试起会 `NoneType has no attribute send`。

DATABASE_URL 非 PostgreSQL 时**直接失败而不是 skip**：本任务是纯 schema 层，
skip 等于把唯一判据静默抹掉（假绿第②源的变体）。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_MIGRATION = _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
_ROLLBACK = _BACKEND / "migrations" / "R151__rollback_workpaper_sync_content_application_bundle_scope.sql"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_task9_v151_"

# scratch schema 内的前置桩表：让 V151 的 `ALTER TABLE working_paper` 与回填 SQL
# 打在桩表上，且 search_path 不含 public ⇒ 物理上无法触到业务表。
_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_ZERO_DIGEST = "0" * 64


def _d(label: str) -> str:
    """确定性 digest（真实 sha256，不是手写基线）。"""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _marker_digest(slot: str) -> str:
    payload = (
        '{"schema_version":"definition-bundle-marker:v1","slot":"%s","value":"none"}' % slot
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 合法「世界」：正控制。任何一条失败都说明约束过严（把合法写入也拦了）。
# ═══════════════════════════════════════════════════════════════════════════


def _new_ids() -> dict[str, Any]:
    keys = (
        "project user user_b wp wp_ledger_probe "
        "art_tpl art_instr art_contract art_authority art_authority_custom art_bundle_payload "
        "art_bundle_payload_custom art_canonical_g1 art_canonical_g2 art_canonical_result "
        "art_projection art_projection_v2 art_candidate art_trace art_runmanifest art_pending_payload "
        "art_incoming_ok art_incoming_quarantined art_incoming_recovery "
        "def_tpl def_instr def_contract def_authority def_authority_custom def_tpl_candidate "
        "bundle bundle_custom "
        "cv1 cv2 rep_g1 rep_g2 rep_result cand "
        "room part_a part_b conf_a conf_b "
        "req_a req_b req_close req_recovery "
        "app op_a op_b op_c op_recovery "
        "del_1 del_2 del_pre del_unmatched del_recovery "
        "recovery_case intent_a intent_b conflict pending_mutation "
        "test_run scen_standard scen_download"
    ).split()
    return {k: uuid.uuid4() for k in keys}


def _world_sql(i: dict[str, Any]) -> list[str]:
    """构造一套完整合法世界（单事务内执行，deferred 约束在 COMMIT 时统一校验）。"""
    p = i["project"]
    wp = i["wp"]
    entry = "g7.disclosure.listed"
    base = f"storage/{p}/workpapers"

    sha = {
        "tpl": _d("template-definition"),
        "instr": _d("instrumentation-definition"),
        "contract": _d("contract-definition"),
        "authority": _d("authority-projection-contract"),
        "authority_custom": _d("authority-custom-ooxml"),
        "bundle": _d("bundle-canonical-payload"),
        "bundle_custom": _d("bundle-canonical-payload-custom"),
        "canonical_g1": _d("canonical-gen1"),
        "canonical_g2": _d("canonical-gen2"),
        "canonical_result": _d("canonical-result"),
        "projection": _d("projection-v1"),
        "projection_v2": _d("projection-v2"),
        "candidate": _d("candidate-artifact"),
        "trace": _d("trace-bundle"),
        "runmanifest": _d("run-manifest"),
        "pending_payload": _d("pending-payload"),
        "incoming_ok": _d("incoming-durable"),
        "incoming_quarantined": _d("incoming-quarantined"),
        "incoming_recovery": _d("incoming-recovery"),
        "tpl_candidate": _d("template-definition-candidate"),
    }
    i["sha"] = sha
    i["entry"] = entry
    i["base_path"] = base

    def art(key: str, kind: str, state: str, path: str, digest: str, extra: str = "") -> str:
        cols = ["id", "project_id", "wp_id", "kind", "state", "relative_path", "sha256",
                "size_bytes", "document_type"]
        vals = [f"'{i[key]}'", f"'{p}'", f"'{wp}'", f"'{kind}'", f"'{state}'",
                f"'{path}'", f"'{digest}'", "4096", "'xlsx'"]
        stamp = {
            "durable": "durable_at",
            "published": "published_at",
            "quarantined": "quarantined_at",
            "orphan": "orphaned_at",
        }.get(state)
        if stamp:
            cols.append(stamp)
            vals.append("now()")
        if extra:
            k, v = extra.split("=", 1)
            if k in cols:  # 覆盖既有列（如 document_type），不得追加成重复列
                vals[cols.index(k)] = v
            else:
                cols.append(k)
                vals.append(v)
        return (
            f"INSERT INTO working_paper_artifact ({', '.join(cols)}) VALUES ({', '.join(vals)})"
        )

    stmts: list[str] = [
        f"INSERT INTO projects (id) VALUES ('{p}')",
        f"INSERT INTO users (id) VALUES ('{i['user']}')",
        f"INSERT INTO working_paper (id, project_id, parsed_data) VALUES ('{wp}', '{p}', '{{}}'::jsonb)",
        # 世界的 wp 在迁移回填之后创建，故显式补一行 revision 0 台账
        # （否则 P4-backfill-ledger-immutable / -no-delete 的 UPDATE/DELETE 命中 0 行 ⇒
        #  「未被拒绝」是守卫自身缺陷而不是约束失效）
        f"""INSERT INTO working_paper_content_revision_backfill_ledger
              (wp_id, project_id, backfilled_content_revision, legacy_file_version, had_parsed_data)
            VALUES ('{wp}', '{p}', 0, 1, true)""",
        # 专供台账负控制的 wp：**故意不建台账行**。若负控制用随机 UUID，会先撞
        # `wp_id` 的 FK 而被拒 ⇒ 台账自身的 CHECK 被 FK 遮蔽，变异检验必判 GREEN。
        f"INSERT INTO working_paper (id, project_id) VALUES ('{i['wp_ledger_probe']}', '{p}')",
        # ── artifacts ────────────────────────────────────────────────────
        art("art_tpl", "definition", "published", f"{base}/.versions/{wp}/definitions/tpl.json", sha["tpl"]),
        art("art_instr", "definition", "published", f"{base}/.versions/{wp}/definitions/instr.json", sha["instr"]),
        art("art_contract", "definition", "published", f"{base}/.versions/{wp}/definitions/contract.json", sha["contract"]),
        art("art_authority", "definition", "published", f"{base}/.versions/{wp}/definitions/authority.json", sha["authority"]),
        art("art_authority_custom", "definition", "published", f"{base}/.versions/{wp}/definitions/authority-custom.json", sha["authority_custom"]),
        art("art_bundle_payload", "definition", "published", f"{base}/.versions/{wp}/definitions/bundle.json", sha["bundle"]),
        art("art_bundle_payload_custom", "definition", "published", f"{base}/.versions/{wp}/definitions/bundle-custom.json", sha["bundle_custom"]),
        art("art_canonical_g1", "canonical", "published", f"{base}/.versions/{wp}/representations/{entry}/gen1.xlsx", sha["canonical_g1"]),
        art("art_canonical_g2", "canonical", "published", f"{base}/.versions/{wp}/representations/{entry}/gen2.xlsx", sha["canonical_g2"]),
        art("art_canonical_result", "canonical", "published", f"{base}/.versions/{wp}/representations/{entry}/result.xlsx", sha["canonical_result"]),
        art("art_projection", "projection", "published", f"{base}/.versions/{wp}/projections/v1.json.gz", sha["projection"], "document_type='json.gz'"),
        art("art_projection_v2", "projection", "published", f"{base}/.versions/{wp}/projections/v2.json.gz", sha["projection_v2"], "document_type='json.gz'"),
        art("art_candidate", "upgrade_candidate", "staged", f"{base}/.upgrade-candidates/{wp}/cand.xlsx", sha["candidate"]),
        art("art_trace", "trace_bundle", "published", f"{base}/.evidence/{wp}/trace.zip", sha["trace"], "document_type='zip'"),
        art("art_runmanifest", "evidence", "published", f"{base}/.evidence/{wp}/run.json", sha["runmanifest"], "document_type='json'"),
        art("art_pending_payload", "projection", "published", f"{base}/.versions/{wp}/projections/pending.json.gz", sha["pending_payload"], "document_type='json.gz'"),
        # incoming：路径必须 `.incoming/{wp_id}/{delivery_id}/`（delivery FK 为 DEFERRABLE，同事务后建）
        art("art_incoming_ok", "incoming", "durable", f"{base}/.incoming/{wp}/{i['del_1']}/artifact.xlsx", sha["incoming_ok"], f"source_delivery_id='{i['del_1']}'"),
        art("art_incoming_quarantined", "incoming", "quarantined", f"{base}/.incoming/{wp}/{i['del_pre']}/artifact.xlsx", sha["incoming_quarantined"], f"source_delivery_id='{i['del_pre']}'"),
        art("art_incoming_recovery", "incoming", "durable", f"{base}/.incoming/{wp}/{i['del_recovery']}/artifact.xlsx", sha["incoming_recovery"], f"source_delivery_id='{i['del_recovery']}'"),
        # ── definition artifacts ─────────────────────────────────────────
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, structure_hash, source_commit, state, approved_at)
            VALUES ('{i['def_tpl']}', 'template', 'g7.listed.template', '1.0.0', '{i['art_tpl']}',
                    '{sha['tpl']}', '{_d('tpl-structure')}', 'abc1234', 'approved', now())""",
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, structure_hash, source_commit, state, approved_at)
            VALUES ('{i['def_instr']}', 'instrumentation', 'g7.listed.instrumentation', '1.0.0', '{i['art_instr']}',
                    '{sha['instr']}', '{_d('instr-structure')}', 'abc1234', 'approved', now())""",
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, source_commit, state, approved_at)
            VALUES ('{i['def_contract']}', 'contract', 'g7.listed.contract', '1.0.0', '{i['art_contract']}',
                    '{sha['contract']}', 'abc1234', 'approved', now())""",
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, authority_model_type, source_commit, state, approved_at)
            VALUES ('{i['def_authority']}', 'authority_model', 'authority.projection', '1.0.0', '{i['art_authority']}',
                    '{sha['authority']}', 'projection_contract', 'abc1234', 'approved', now())""",
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, authority_model_type, source_commit, state, approved_at)
            VALUES ('{i['def_authority_custom']}', 'authority_model', 'authority.custom', '1.0.0', '{i['art_authority_custom']}',
                    '{sha['authority_custom']}', 'custom_authoritative_ooxml', 'abc1234', 'approved', now())""",
        # 未批准的 template definition（负控制用）
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, source_commit, state)
            VALUES ('{i['def_tpl_candidate']}', 'template', 'g7.listed.template', '2.0.0', '{i['art_tpl']}',
                    '{sha['tpl_candidate']}', 'abc1234', 'candidate')""",
        # ── bundles ──────────────────────────────────────────────────────
        f"""INSERT INTO working_paper_sync_definition_bundle
              (id, authority_model_definition_id, authority_model_definition_sha256,
               template_slot_type, template_slot_ref, template_slot_digest,
               instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest,
               contract_slot_type, contract_slot_ref, contract_slot_digest,
               canonical_payload_artifact_id, canonical_payload_sha256, state, approved_at)
            VALUES ('{i['bundle']}', '{i['def_authority']}', '{sha['authority']}',
                    'definition', 'definition:{i['def_tpl']}', '{sha['tpl']}',
                    'definition', 'definition:{i['def_instr']}', '{sha['instr']}',
                    'definition', 'definition:{i['def_contract']}', '{sha['contract']}',
                    '{i['art_bundle_payload']}', '{sha['bundle']}', 'approved', now())""",
        # custom_authoritative_ooxml：instrumentation/contract 用 registry typed null marker
        f"""INSERT INTO working_paper_sync_definition_bundle
              (id, authority_model_definition_id, authority_model_definition_sha256,
               template_slot_type, template_slot_ref, template_slot_digest,
               instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest,
               contract_slot_type, contract_slot_ref, contract_slot_digest,
               canonical_payload_artifact_id, canonical_payload_sha256, state, approved_at)
            VALUES ('{i['bundle_custom']}', '{i['def_authority_custom']}', '{sha['authority_custom']}',
                    'definition', 'definition:{i['def_tpl']}', '{sha['tpl']}',
                    'instrumentation:none:v1', 'marker:instrumentation:none:v1', '{_marker_digest('instrumentation')}',
                    'contract:none:v1', 'marker:contract:none:v1', '{_marker_digest('contract')}',
                    '{i['art_bundle_payload_custom']}', '{sha['bundle_custom']}', 'approved', now())""",
        # ── content versions ─────────────────────────────────────────────
        f"""INSERT INTO working_paper_content_version
              (id, wp_id, revision, source, projection_artifact_id, projection_sha256, actor_id)
            VALUES ('{i['cv1']}', '{wp}', 1, 'html', '{i['art_projection']}', '{sha['projection']}', '{i['user']}')""",
        f"""INSERT INTO working_paper_content_version
              (id, wp_id, revision, parent_version_id, source, projection_artifact_id, projection_sha256, actor_id)
            VALUES ('{i['cv2']}', '{wp}', 2, '{i['cv1']}', 'onlyoffice', '{i['art_projection_v2']}', '{sha['projection_v2']}', '{i['user']}')""",
        # ── representations：同一 cv1 两个 generation（Property 4 正控制）────
        f"""INSERT INTO working_paper_content_representation
              (id, wp_id, content_version_id, entry_id, generation, document_type, artifact_id, artifact_sha256,
               definition_bundle_id, definition_bundle_sha256, authority_model_definition_id,
               authority_model_definition_sha256, adapter_id, adapter_build_digest, structure_hash,
               identity_inventory_sha256, reason)
            VALUES ('{i['rep_g1']}', '{wp}', '{i['cv1']}', '{entry}', 1, 'xlsx', '{i['art_canonical_g1']}', '{sha['canonical_g1']}',
                    '{i['bundle']}', '{sha['bundle']}', '{i['def_authority']}', '{sha['authority']}',
                    'g7.listed', '{_d('adapter-build')}', '{_d('structure-g1')}', '{_d('identity-g1')}', 'content_commit')""",
        f"""INSERT INTO working_paper_content_representation
              (id, wp_id, content_version_id, entry_id, generation, parent_representation_id, document_type,
               artifact_id, artifact_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_id, authority_model_definition_sha256, adapter_id,
               adapter_build_digest, structure_hash, identity_inventory_sha256, reason)
            VALUES ('{i['rep_g2']}', '{wp}', '{i['cv1']}', '{entry}', 2, '{i['rep_g1']}', 'xlsx',
                    '{i['art_canonical_g2']}', '{sha['canonical_g2']}', '{i['bundle']}', '{sha['bundle']}',
                    '{i['def_authority']}', '{sha['authority']}', 'g7.listed', '{_d('adapter-build')}',
                    '{_d('structure-g2')}', '{_d('identity-g2')}', 'definition_upgrade')""",
        f"""INSERT INTO working_paper_content_representation
              (id, wp_id, content_version_id, entry_id, generation, document_type, artifact_id, artifact_sha256,
               definition_bundle_id, definition_bundle_sha256, authority_model_definition_id,
               authority_model_definition_sha256, adapter_id, adapter_build_digest, structure_hash,
               identity_inventory_sha256, reason)
            VALUES ('{i['rep_result']}', '{wp}', '{i['cv2']}', '{entry}', 1, 'xlsx', '{i['art_canonical_result']}',
                    '{sha['canonical_result']}', '{i['bundle']}', '{sha['bundle']}', '{i['def_authority']}',
                    '{sha['authority']}', 'g7.listed', '{_d('adapter-build')}', '{_d('structure-result')}',
                    '{_d('identity-result')}', 'content_commit')""",
        # entry pointer 指向 gen2（纯表示升级后切 pointer，content_revision 不变）
        f"""INSERT INTO working_paper_sync_entry_state (wp_id, entry_id, current_representation_id, representation_generation)
            VALUES ('{wp}', '{entry}', '{i['rep_g2']}', 2)""",
        # upgrade candidate（non-current，awaiting_contract）
        f"""INSERT INTO working_paper_representation_upgrade_candidate
              (id, wp_id, content_version_id, entry_id, source_representation_id, staged_artifact_id,
               staged_artifact_sha256, template_definition_id, instrumentation_definition_id, state)
            VALUES ('{i['cand']}', '{wp}', '{i['cv1']}', '{entry}', '{i['rep_g2']}', '{i['art_candidate']}',
                    '{sha['candidate']}', '{i['def_tpl']}', '{i['def_instr']}', 'awaiting_contract')""",
        # ── room：server last-applied=cv2，client-confirmed base=cv1（Property 62 正控制）──
        f"""INSERT INTO working_paper_oo_room
              (id, project_id, wp_id, entry_id, doc_key, generation, opened_base_version_id,
               last_applied_version_id, client_confirmed_base_version_id, client_confirmed_representation_id,
               client_confirmed_definition_bundle_id, client_confirmed_definition_bundle_sha256,
               client_confirmed_projection_sha256, latest_request_sequence, latest_durable_sequence,
               write_fence_epoch, state, expires_at)
            VALUES ('{i['room']}', '{p}', '{wp}', '{entry}', 'gt-room-{i['room']}-1', 1, '{i['cv1']}',
                    '{i['cv2']}', '{i['cv1']}', '{i['rep_g2']}', '{i['bundle']}', '{sha['bundle']}',
                    '{sha['projection']}', 3, 0, 1, 'active', now() + interval '1 hour')""",
        f"""INSERT INTO working_paper_oo_participant
              (id, room_id, user_id, mode, state, permission_epoch, joined_write_fence_epoch, lease_token_hash, expires_at)
            VALUES ('{i['part_a']}', '{i['room']}', '{i['user']}', 'edit', 'active', 5, 1, '{_d('lease-a')}', now() + interval '1 hour')""",
        f"""INSERT INTO users (id) VALUES ('{i['user_b']}')""",
        f"""INSERT INTO working_paper_oo_participant
              (id, room_id, user_id, mode, state, permission_epoch, joined_write_fence_epoch, lease_token_hash, expires_at)
            VALUES ('{i['part_b']}', '{i['room']}', '{i['user_b']}', 'edit', 'closing', 5, 1, '{_d('lease-b')}', now() + interval '1 hour')""",
        f"""INSERT INTO working_paper_oo_client_confirmation
              (id, room_id, participant_id, generation, doc_key, representation_id, artifact_sha256,
               content_version_id, projection_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_sha256, bundle_slots_digest, write_fence_epoch, idempotency_key)
            VALUES ('{i['conf_a']}', '{i['room']}', '{i['part_a']}', 1, 'gt-room-{i['room']}-1', '{i['rep_g2']}',
                    '{sha['canonical_g2']}', '{i['cv1']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{sha['authority']}', '{_d('slots')}', 1, 'ready-a')""",
        f"""INSERT INTO working_paper_oo_client_confirmation
              (id, room_id, participant_id, generation, doc_key, representation_id, artifact_sha256,
               content_version_id, projection_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_sha256, bundle_slots_digest, write_fence_epoch, idempotency_key)
            VALUES ('{i['conf_b']}', '{i['room']}', '{i['part_b']}', 1, 'gt-room-{i['room']}-1', '{i['rep_g2']}',
                    '{sha['canonical_g2']}', '{i['cv1']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{sha['authority']}', '{_d('slots')}', 1, 'ready-b')""",
    ]

    def req(key: str, seq: int, kind: str, part: str, idem: str, state: str = "correlated") -> str:
        return f"""INSERT INTO working_paper_forcesave_request
              (id, room_id, generation, request_sequence, kind, initiated_by_participant_id,
               initiator_permission_epoch, client_edit_epoch, write_fence_epoch, client_base_version_id,
               client_base_representation_id, client_base_projection_sha256, definition_bundle_id,
               definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256,
               adapter_build_digest, contributor_snapshot_digest, idempotency_key,
               frozen_request_fingerprint, state, accepted_at)
            VALUES ('{i[key]}', '{i['room']}', 1, {seq}, '{kind}', '{i[part]}', 5, 7, 1, '{i['cv1']}',
                    '{i['rep_g2']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{i['def_authority']}', '{sha['authority']}', '{_d('adapter-build')}',
                    '{_d('contributors')}', '{idem}', '{_d('fingerprint-' + key)}', '{state}', now())"""

    stmts += [
        req("req_a", 1, "forcesave", "part_a", "idem-a"),
        req("req_b", 2, "forcesave", "part_b", "idem-b"),
        req("req_close", 3, "close_capture", "part_b", "idem-close", state="frozen"),
    ]

    # ── application：origin=req_a(seq1)，fold 了 req_b(seq2) ⇒ effective=2 ──
    stmts.append(
        f"""INSERT INTO working_paper_content_application
              (id, project_id, wp_id, entry_id, room_id, generation, origin_request_id, application_key,
               client_edit_epoch, origin_request_sequence, effective_request_sequence, base_version_id,
               base_representation_id, current_revision, result_revision, incoming_artifact_id,
               incoming_sha256, incoming_projection_sha256, merged_projection_sha256,
               result_representation_id, result_artifact_sha256, definition_bundle_id,
               definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256,
               adapter_id, adapter_build_digest, contributor_snapshot_digest, state,
               logical_result_code, durable_at, finished_at)
            VALUES ('{i['app']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['req_a']}', '{_d('application-key')}',
                    7, 1, 2, '{i['cv1']}', '{i['rep_g2']}', 1, 2, '{i['art_incoming_ok']}',
                    '{sha['incoming_ok']}', '{_d('incoming-projection')}', '{_d('merged-projection')}',
                    '{i['rep_result']}', '{sha['canonical_result']}', '{i['bundle']}', '{sha['bundle']}',
                    '{i['def_authority']}', '{sha['authority']}', 'g7.listed', '{_d('adapter-build')}',
                    '{_d('contributors')}', 'applied', 'applied', now(), now())"""
    )
    stmts.append(
        f"""UPDATE working_paper_oo_room
               SET latest_durable_application_id = '{i['app']}', latest_durable_sequence = 2
             WHERE id = '{i['room']}'"""
    )

    def op(key: str, request: str | None, application: str | None, dup: str | None,
           state: str, direction: str = "oo_to_html") -> str:
        cols = ["id", "project_id", "wp_id", "entry_id", "room_id", "direction", "state",
                "definition_bundle_id", "definition_bundle_sha256",
                "authority_model_definition_id", "authority_model_definition_sha256", "created_by"]
        vals = [f"'{i[key]}'", f"'{p}'", f"'{wp}'", f"'{entry}'", f"'{i['room']}'",
                f"'{direction}'", f"'{state}'", f"'{i['bundle']}'", f"'{sha['bundle']}'",
                f"'{i['def_authority']}'", f"'{sha['authority']}'", f"'{i['user']}'"]
        if request:
            cols.append("forcesave_request_id")
            vals.append(f"'{i[request]}'")
        if application:
            cols += ["application_id", "application_bound_at"]
            vals += [f"'{i[application]}'", "now()"]
        if dup:
            cols.append("duplicate_of_operation_id")
            vals.append(f"'{i[dup]}'")
        return f"INSERT INTO working_paper_sync_operation ({', '.join(cols)}) VALUES ({', '.join(vals)})"

    stmts += [
        # winner primary
        op("op_a", "req_a", "app", None, "applied"),
        # loser shell：application 空 + 直指 primary + terminal duplicate
        op("op_b", "req_b", None, "op_a", "duplicate"),
        # 第三个同 key shell（证明 N 个 shell → 1 primary + N-1 direct duplicates）
        op("op_c", None, None, "op_a", "duplicate"),
        # ── deliveries：同一 application 多 delivery（status 6 与 status 2）──
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, operation_id, application_id,
               forcesave_request_id, route_credential_id, callback_status, delivery_key, state,
               payload_sha256, correlation_result, incoming_artifact_id, durable_at, responded_at)
            VALUES ('{i['del_1']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['op_a']}', '{i['app']}',
                    '{i['req_a']}', '{i['user']}', 6, '{_d('delivery-6')}', 'acknowledged',
                    '{_d('payload-6')}', 'request', '{i['art_incoming_ok']}', now(), now())""",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, operation_id, application_id,
               forcesave_request_id, route_credential_id, callback_status, delivery_key, state,
               payload_sha256, correlation_result, incoming_artifact_id, durable_at, responded_at)
            VALUES ('{i['del_2']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['op_b']}', '{i['app']}',
                    '{i['req_b']}', '{i['user']}', 2, '{_d('delivery-2')}', 'durable',
                    '{_d('payload-2')}', 'existing_application', '{i['art_incoming_ok']}', now(), now())""",
        # pre-durable delivery：零 owner 合法
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, route_credential_id,
               callback_status, delivery_key, state)
            VALUES ('{i['del_pre']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['user']}',
                    6, '{_d('delivery-pre')}', 'downloading')""",
        # unmatched delivery → recovery case（三实体全空）
        f"""INSERT INTO working_paper_callback_recovery_case
              (id, project_id, wp_id, entry_id, room_id, generation, source_delivery_key,
               incoming_artifact_id, reason, candidate_confirmation_digest, state, expires_at)
            VALUES ('{i['recovery_case']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{_d('delivery-recovery')}',
                    '{i['art_incoming_recovery']}', 'crash_close', '{_d('candidate-confirmation')}',
                    'unclaimed', now() + interval '7 days')""",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, callback_recovery_case_id,
               route_credential_id, callback_status, delivery_key, state, correlation_result,
               incoming_artifact_id, durable_at)
            VALUES ('{i['del_recovery']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['recovery_case']}',
                    '{i['user']}', 2, '{_d('delivery-recovery')}', 'unmatched', 'unmatched',
                    '{i['art_incoming_recovery']}', now())""",
        # ── timeline events ──────────────────────────────────────────────
        f"""INSERT INTO working_paper_sync_operation_event
              (operation_id, sequence_no, from_state, to_state, actor_type, correlation_id,
               origin_request_sequence, effective_request_sequence)
            VALUES ('{i['op_a']}', 1, 'waiting_application', 'application_bound', 'callback', '{i['op_a']}', 1, 2)""",
        f"""INSERT INTO working_paper_sync_operation_event
              (operation_id, sequence_no, from_state, to_state, actor_type, correlation_id,
               origin_request_sequence, effective_request_sequence)
            VALUES ('{i['op_b']}', 1, 'waiting_application', 'duplicate', 'callback', '{i['op_b']}', 2, 2)""",
        f"""INSERT INTO working_paper_content_application_event
              (application_id, sequence_no, event_type, origin_request_sequence, effective_request_sequence, actor_type)
            VALUES ('{i['app']}', 1, 'created', 1, 1, 'callback')""",
        f"""INSERT INTO working_paper_content_application_event
              (application_id, sequence_no, event_type, folded_request_id, origin_request_sequence,
               effective_request_sequence, room_latest_durable_sequence, actor_type)
            VALUES ('{i['app']}', 2, 'sequence_folded', '{i['req_b']}', 1, 2, 2, 'callback')""",
        f"""INSERT INTO working_paper_callback_recovery_case_event
              (case_id, sequence_no, to_state, actor_type)
            VALUES ('{i['recovery_case']}', 1, 'unclaimed', 'callback')""",
        # ── close intents ────────────────────────────────────────────────
        f"""INSERT INTO working_paper_oo_close_intent
              (id, room_id, generation, participant_id, client_confirmation_id, intent_sequence,
               barrier_epoch, ordinary_forcesave_request_id, state)
            VALUES ('{i['intent_a']}', '{i['room']}', 1, '{i['part_a']}', '{i['conf_a']}', 1, 1, '{i['req_a']}', 'waiting_barrier')""",
        f"""INSERT INTO working_paper_oo_close_intent
              (id, room_id, generation, participant_id, client_confirmation_id, intent_sequence,
               barrier_epoch, promoted_request_id, state)
            VALUES ('{i['intent_b']}', '{i['room']}', 1, '{i['part_b']}', '{i['conf_b']}', 2, 2, '{i['req_close']}', 'promoted')""",
        f"""INSERT INTO working_paper_oo_close_intent_event
              (intent_id, sequence_no, from_state, to_state, eligibility_epoch, eligibility_digest, actor_type)
            VALUES ('{i['intent_b']}', 1, 'leader_ready', 'promoted', 1, '{_d('eligibility')}', 'reconciler')""",
        f"""UPDATE working_paper_oo_room SET close_leader_intent_id = '{i['intent_b']}',
                 close_barrier_epoch = 2, close_leader_eligibility_epoch = 1,
                 close_leader_eligibility_digest = '{_d('eligibility')}'
             WHERE id = '{i['room']}'""",
        # ── conflict / pending mutation ──────────────────────────────────
        f"""INSERT INTO working_paper_sync_conflict
              (id, operation_id, client_edit_epoch, canonical_application_id, effective_request_sequence,
               stable_field_key, business_label, sheet_key, table_key, row_key, json_pointer, oo_location,
               field_source, protection_policy, suggested_action, conflict_kind,
               base_value, current_value, incoming_value)
            VALUES ('{i['conflict']}', '{i['op_a']}', 7, '{i['app']}', 2, 'g7.listed.row3.amount',
                    '其他债权投资期末余额', 'Sheet1', 'tbl_main', 'row3', '/rows/3/values/1', 'Sheet1!C5',
                    'projection', 'editable', 'prefer_incoming', 'value',
                    '100'::jsonb, '120'::jsonb, '130'::jsonb)""",
        f"""INSERT INTO working_paper_pending_mutation
              (id, project_id, wp_id, entry_id, sheet_key, user_id, expected_revision,
               payload_artifact_id, payload_sha256, idempotency_key, state, expires_at)
            VALUES ('{i['pending_mutation']}', '{p}', '{wp}', '{entry}', 'Sheet1', '{i['user']}', 1,
                    '{i['art_pending_payload']}', '{sha['pending_payload']}', 'flush-1', 'pending',
                    now() + interval '10 minutes')""",
        # ── evidence ─────────────────────────────────────────────────────
        f"""INSERT INTO working_paper_sync_test_run
              (id, entry_id, source_commit, runner_version, manifest_source_digest, editability, room_model,
               scenario_profile_digest, onlyoffice_build, browser_build, environment_digest,
               required_scenario_set_digest, authority_model_definition_sha256, definition_bundle_sha256,
               run_manifest_artifact_id, run_manifest_sha256, started_at, finished_at, aggregate_result)
            VALUES ('{i['test_run']}', '{entry}', 'abc1234', 'runner-1.0', '{_d('manifest')}', 'editable', 'shared',
                    '{_d('profile')}', '9.4.0', 'chrome-131', '{_d('environment')}', '{_d('required-set')}',
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_runmanifest']}', '{sha['runmanifest']}',
                    now(), now(), 'passed')""",
        f"""INSERT INTO working_paper_entry_evidence_scenario
              (id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, application_ids,
               recovery_case_ids, content_version_ids, representation_ids,
               authority_model_definition_sha256, definition_bundle_sha256, trace_bundle_artifact_id,
               trace_bundle_sha256, server_timeline_digest, database_snapshot_digest, browser_build)
            VALUES ('{i['scen_standard']}', '{i['test_run']}', 'oo_to_html', 1, 'standard', 'passed',
                    '["{i['op_a']}"]'::jsonb, '["{i['app']}"]'::jsonb, '[]'::jsonb,
                    '["{i['cv2']}"]'::jsonb, '["{i['rep_result']}"]'::jsonb,
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_trace']}', '{sha['trace']}',
                    '{_d('timeline')}', '{_d('snapshot')}', 'chrome-131')""",
        f"""INSERT INTO working_paper_entry_evidence_scenario
              (id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, application_ids,
               recovery_case_ids, content_version_ids, representation_ids,
               authority_model_definition_sha256, definition_bundle_sha256, trace_bundle_artifact_id,
               trace_bundle_sha256, server_timeline_digest, database_snapshot_digest, browser_build)
            VALUES ('{i['scen_download']}', '{i['test_run']}', 'download_only', 1, 'download_only', 'passed',
                    '[]'::jsonb, '[]'::jsonb, '["{i['recovery_case']}"]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_trace']}', '{sha['trace']}',
                    '{_d('timeline-dl')}', '{_d('snapshot-dl')}', 'chrome-131')""",
        # ── scope index ──────────────────────────────────────────────────
        f"""INSERT INTO working_paper_sync_scope_index
              (resource_kind, resource_id, project_id, wp_id, entry_id, room_id, generation)
            VALUES ('room', '{i['room']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1)""",
        f"""INSERT INTO working_paper_sync_scope_index
              (resource_kind, resource_id, project_id, wp_id, entry_id, room_id, generation)
            VALUES ('content_application', '{i['app']}', '{p}', '{wp}', '{entry}', '{i['room']}', 1)""",
        f"""INSERT INTO working_paper_sync_scope_index
              (resource_kind, resource_id, project_id, wp_id, entry_id)
            VALUES ('content_version', '{i['cv1']}', '{p}', '{wp}', '{entry}')""",
    ]
    return stmts


# ═══════════════════════════════════════════════════════════════════════════
# 负控制矩阵：每条**必须被真实 PostgreSQL 拒绝**。
# case_id 前缀 = 它守的 Property。
# ═══════════════════════════════════════════════════════════════════════════


def _negative_cases(i: dict[str, Any]) -> list[tuple[str, str, str]]:
    p, wp, entry = i["project"], i["wp"], i["entry"]
    sha = i["sha"]
    base = i["base_path"]
    ad = _d("adapter-build")

    def rep_insert(rid: str, cv: str, gen: int, artifact: str, artifact_sha: str,
                   bundle: str, bundle_sha: str, authority: str, authority_sha: str) -> str:
        return f"""INSERT INTO working_paper_content_representation
              (id, wp_id, content_version_id, entry_id, generation, document_type, artifact_id, artifact_sha256,
               definition_bundle_id, definition_bundle_sha256, authority_model_definition_id,
               authority_model_definition_sha256, adapter_id, adapter_build_digest, structure_hash,
               identity_inventory_sha256, reason)
            VALUES ('{rid}', '{wp}', '{cv}', '{entry}', {gen}, 'xlsx', '{artifact}', '{artifact_sha}',
                    '{bundle}', '{bundle_sha}', '{authority}', '{authority_sha}',
                    'g7.listed', '{ad}', '{_d('s')}', '{_d('ii')}', 'content_commit')"""

    def bundle_insert(bid: str, authority: str, authority_sha: str,
                      t: tuple[str, str, str], ins: tuple[str, str, str], c: tuple[str, str, str],
                      payload_artifact: str, payload_sha: str, state: str = "approved") -> str:
        approved = "now()" if state == "approved" else "NULL"
        return f"""INSERT INTO working_paper_sync_definition_bundle
              (id, authority_model_definition_id, authority_model_definition_sha256,
               template_slot_type, template_slot_ref, template_slot_digest,
               instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest,
               contract_slot_type, contract_slot_ref, contract_slot_digest,
               canonical_payload_artifact_id, canonical_payload_sha256, state, approved_at)
            VALUES ('{bid}', '{authority}', '{authority_sha}',
                    '{t[0]}', '{t[1]}', '{t[2]}', '{ins[0]}', '{ins[1]}', '{ins[2]}',
                    '{c[0]}', '{c[1]}', '{c[2]}',
                    '{payload_artifact}', '{payload_sha}', '{state}', {approved})"""

    def op_insert(oid: str, request: str | None, application: str | None, dup: str | None,
                  state: str, bundle: str | None = None, bundle_sha: str | None = None,
                  entry_override: str | None = None, room: str | None = None,
                  bound_at: bool | None = None) -> str:
        bundle = bundle or str(i["bundle"])
        bundle_sha = bundle_sha or sha["bundle"]
        cols = ["id", "project_id", "wp_id", "entry_id", "room_id", "direction", "state",
                "definition_bundle_id", "definition_bundle_sha256",
                "authority_model_definition_id", "authority_model_definition_sha256"]
        vals = [f"'{oid}'", f"'{p}'", f"'{wp}'", f"'{entry_override or entry}'",
                f"'{room or i['room']}'", "'oo_to_html'", f"'{state}'",
                f"'{bundle}'", f"'{bundle_sha}'", f"'{i['def_authority']}'", f"'{sha['authority']}'"]
        if request:
            cols.append("forcesave_request_id")
            vals.append(f"'{request}'")
        if application:
            cols.append("application_id")
            vals.append(f"'{application}'")
            if bound_at is not False:
                cols.append("application_bound_at")
                vals.append("now()")
        if dup:
            cols.append("duplicate_of_operation_id")
            vals.append(f"'{dup}'")
        return f"INSERT INTO working_paper_sync_operation ({', '.join(cols)}) VALUES ({', '.join(vals)})"

    def app_insert(aid: str, key_digest: str, origin_request: str, origin_seq: int,
                   effective_seq: int, incoming: str, incoming_sha: str,
                   bundle: str | None = None, bundle_sha: str | None = None,
                   base_version: str | None = None, base_rep: str | None = None,
                   state: str = "merging", extra_cols: str = "", extra_vals: str = "") -> str:
        bundle = bundle or str(i["bundle"])
        bundle_sha = bundle_sha or sha["bundle"]
        return f"""INSERT INTO working_paper_content_application
              (id, project_id, wp_id, entry_id, room_id, generation, origin_request_id, application_key,
               client_edit_epoch, origin_request_sequence, effective_request_sequence, base_version_id,
               base_representation_id, current_revision, incoming_artifact_id, incoming_sha256,
               definition_bundle_id, definition_bundle_sha256, authority_model_definition_id,
               authority_model_definition_sha256, adapter_id, adapter_build_digest,
               contributor_snapshot_digest, state{extra_cols})
            VALUES ('{aid}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{origin_request}', '{key_digest}',
                    7, {origin_seq}, {effective_seq}, '{base_version or i['cv1']}',
                    '{base_rep or i['rep_g2']}', 1, '{incoming}', '{incoming_sha}',
                    '{bundle}', '{bundle_sha}', '{i['def_authority']}', '{sha['authority']}',
                    'g7.listed', '{ad}', '{_d('contributors')}', '{state}'{extra_vals})"""

    n = uuid.uuid4  # 新 id 生成器
    cases: list[tuple[str, str, str]] = []
    add = lambda cid, why, sql: cases.append((cid, why, sql))  # noqa: E731

    # ── Property 4：业务 revision ⊥ representation generation ──────────────
    add("P4-dup-revision", "同 wp 重复 revision 必须被 UNIQUE(wp_id,revision) 拒绝",
        f"""INSERT INTO working_paper_content_version (id, wp_id, revision, source, projection_artifact_id, projection_sha256)
            VALUES ('{n()}', '{wp}', 1, 'html', '{i['art_projection']}', '{sha['projection']}')""")
    add("P4-dup-generation", "同 (wp,entry,content_version,generation) 重复必须被拒绝",
        rep_insert(str(n()), str(i["cv1"]), 2, str(i["art_canonical_result"]), sha["canonical_result"],
                   str(i["bundle"]), sha["bundle"], str(i["def_authority"]), sha["authority"]))
    add("P4-content-version-immutable", "content version 是 immutable 历史行，UPDATE 必须被拒绝",
        f"UPDATE working_paper_content_version SET revision = 99 WHERE id = '{i['cv1']}'")
    add("P4-representation-immutable", "representation 是 immutable 行，UPDATE 必须被拒绝",
        f"UPDATE working_paper_content_representation SET reason = 'rollback' WHERE id = '{i['rep_g1']}'")
    add("P4-representation-needs-approved-bundle", "candidate 状态 bundle 不得 finalize representation",
        "\n;".join([
            bundle_insert(str(bid := n()), str(i["def_authority"]), sha["authority"],
                          ("definition", f"definition:{i['def_tpl']}", sha["tpl"]),
                          ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                          ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                          str(i["art_bundle_payload"]), _d("candidate-bundle-payload"), state="candidate"),
            rep_insert(str(n()), str(i["cv2"]), 2, str(i["art_canonical_g1"]), sha["canonical_g1"],
                       str(bid), _d("candidate-bundle-payload"), str(i["def_authority"]), sha["authority"]),
        ]))
    add("P4-representation-bundle-digest-mismatch", "representation 的 bundle digest 与 bundle 不一致必须被拒绝",
        rep_insert(str(n()), str(i["cv2"]), 3, str(i["art_canonical_g1"]), sha["canonical_g1"],
                   str(i["bundle"]), _d("wrong-bundle-digest"), str(i["def_authority"]), sha["authority"]))
    add("P4-representation-authority-not-locked", "representation 的 authority 与 bundle child 不一致必须被拒绝",
        rep_insert(str(n()), str(i["cv2"]), 4, str(i["art_canonical_g1"]), sha["canonical_g1"],
                   str(i["bundle"]), sha["bundle"], str(i["def_authority_custom"]), sha["authority_custom"]))
    # 🔴 用 wp_ledger_probe（真实存在但无台账行）而不是随机 UUID：随机 UUID 会先撞
    #    wp_id 的 FK，台账 CHECK 被遮蔽 ⇒ 变异检验会把该 CHECK 判成 GREEN。
    add("P4-backfill-ledger-non-zero", "回填台账只能落 revision 0",
        f"""INSERT INTO working_paper_content_revision_backfill_ledger
              (wp_id, project_id, backfilled_content_revision, had_parsed_data)
            VALUES ('{i['wp_ledger_probe']}', '{p}', 3, true)""")
    add("P4-backfill-ledger-immutable", "回填事实不可改写",
        f"UPDATE working_paper_content_revision_backfill_ledger SET backfilled_content_revision = 1 WHERE wp_id = '{wp}'")
    add("P4-backfill-ledger-no-delete", "回填台账禁止删除",
        f"DELETE FROM working_paper_content_revision_backfill_ledger WHERE wp_id = '{wp}'")
    add("P4-backfill-ledger-claims-entities", "回填声称创建了 content version/representation 必须被拒绝",
        f"""INSERT INTO working_paper_content_revision_backfill_ledger
              (wp_id, project_id, backfilled_content_revision, had_parsed_data, content_version_created)
            VALUES ('{i['wp_ledger_probe']}', '{p}', 0, true, true)""")

    # ── Property 5：staged artifact / candidate 不产生悬空可见态 ────────────
    add("P5-incoming-published", "incoming artifact 永不 published",
        f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, source_delivery_id, published_at)
            VALUES ('{n()}', '{p}', '{wp}', 'incoming', 'published', '{base}/.incoming/{wp}/{i['del_1']}/pub.xlsx', '{_d('neg-incoming-pub')}', 1, 'xlsx', '{i['del_1']}', now())""")
    add("P5-candidate-published", "upgrade_candidate artifact 永不 published",
        f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, published_at)
            VALUES ('{n()}', '{p}', '{wp}', 'upgrade_candidate', 'published', '{base}/.upgrade-candidates/{wp}/pub.xlsx', '{_d('neg-cand-pub')}', 1, 'xlsx', now())""")
    add("P5-incoming-without-delivery", "incoming artifact 必须绑定 delivery",
        f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, durable_at)
            VALUES ('{n()}', '{p}', '{wp}', 'incoming', 'durable', '{base}/.incoming/{wp}/x/a.xlsx', '{_d('neg-incoming-nodel')}', 1, 'xlsx', now())""")
    add("P5-incoming-path-not-sealed", "incoming 路径必须 `.incoming/{wp}/{delivery}/` sealing",
        f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, source_delivery_id, durable_at)
            VALUES ('{n()}', '{p}', '{wp}', 'incoming', 'durable', '{base}/.incoming/{wp}/wrong-dir/a.xlsx', '{_d('neg-incoming-path')}', 1, 'xlsx', '{i['del_1']}', now())""")
    add("P5-incoming-path-uses-operation", "incoming 路径不得依赖 operation id",
        f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, source_delivery_id, created_by_operation_id, durable_at)
            VALUES ('{n()}', '{p}', '{wp}', 'incoming', 'durable', '{base}/.incoming/{wp}/{i['del_1']}/{i['op_a']}.xlsx', '{_d('neg-incoming-oppath')}', 1, 'xlsx', '{i['del_1']}', '{i['op_a']}', now())""")
    add("P5-incoming-durable-to-quarantined", "durable incoming 不得转 quarantined（两支不可互转）",
        f"UPDATE working_paper_artifact SET state = 'quarantined', durable_at = NULL, quarantined_at = now() WHERE id = '{i['art_incoming_ok']}'")
    add("P5-incoming-quarantined-to-durable", "quarantined incoming 永不 release/转 durable",
        f"UPDATE working_paper_artifact SET state = 'durable', quarantined_at = NULL, durable_at = now() WHERE id = '{i['art_incoming_quarantined']}'")
    add("P5-artifact-sha-immutable", "artifact 内容身份不可变",
        f"UPDATE working_paper_artifact SET sha256 = '{_d('tampered')}' WHERE id = '{i['art_canonical_g1']}'")
    add("P5-quarantined-with-durable-at", "quarantined 必须保持 durable_at=NULL",
        f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, source_delivery_id, durable_at, quarantined_at)
            VALUES ('{n()}', '{p}', '{wp}', 'incoming', 'quarantined', '{base}/.incoming/{wp}/{i['del_pre']}/q2.xlsx', '{_d('neg-q-durable')}', 1, 'xlsx', '{i['del_pre']}', now(), now())""")
    add("P5-entry-pointer-to-staged-artifact", "current pointer 不得指向未 published 的 artifact",
        "\n;".join([
            f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type)
                VALUES ('{(aid := n())}', '{p}', '{wp}', 'canonical', 'staged', '{base}/.staging/{wp}/s1/a.xlsx', '{_d('neg-staged')}', 1, 'xlsx')""",
            rep_insert(str(rid := n()), str(i["cv2"]), 7, str(aid), _d("neg-staged"),
                       str(i["bundle"]), sha["bundle"], str(i["def_authority"]), sha["authority"]),
            f"""UPDATE working_paper_sync_entry_state SET current_representation_id = '{rid}', representation_generation = 7
                 WHERE wp_id = '{wp}' AND entry_id = '{entry}'""",
        ]))
    add("P5-entry-pointer-generation-mismatch", "entry pointer 的 generation 必须与 representation 一致",
        f"""UPDATE working_paper_sync_entry_state SET representation_generation = 99
             WHERE wp_id = '{wp}' AND entry_id = '{entry}'""")
    add("P5-representation-on-incoming-artifact", "representation 不得以 incoming artifact 为载体",
        rep_insert(str(n()), str(i["cv2"]), 8, str(i["art_incoming_ok"]), sha["incoming_ok"],
                   str(i["bundle"]), sha["bundle"], str(i["def_authority"]), sha["authority"]))
    add("P5-representation-on-candidate-artifact", "representation 不得以 upgrade_candidate artifact 为载体",
        rep_insert(str(n()), str(i["cv2"]), 9, str(i["art_candidate"]), sha["candidate"],
                   str(i["bundle"]), sha["bundle"], str(i["def_authority"]), sha["authority"]))
    add("P5-candidate-ready-without-bundle", "candidate 未补齐 approved contract+bundle 不得 ready",
        f"UPDATE working_paper_representation_upgrade_candidate SET state = 'ready' WHERE id = '{i['cand']}'")
    add("P5-candidate-finalize-advances-revision", "candidate finalize 必须绑定同一 content version",
        f"""UPDATE working_paper_representation_upgrade_candidate
               SET state = 'finalized', finalized_at = now(),
                   target_contract_definition_id = '{i['def_contract']}',
                   target_definition_bundle_id = '{i['bundle']}',
                   finalized_representation_id = '{i['rep_result']}'
             WHERE id = '{i['cand']}'""")
    add("P5-candidate-on-published-artifact", "candidate 只能引用 upgrade_candidate 类 staged artifact",
        f"""INSERT INTO working_paper_representation_upgrade_candidate
              (id, wp_id, content_version_id, entry_id, source_representation_id, staged_artifact_id,
               staged_artifact_sha256, template_definition_id, instrumentation_definition_id, state)
            VALUES ('{n()}', '{wp}', '{i['cv1']}', '{entry}', '{i['rep_g2']}', '{i['art_canonical_g1']}',
                    '{sha['canonical_g1']}', '{i['def_tpl']}', '{i['def_instr']}', 'staged')""")

    # ── Property 10：单次业务 commit 与 representation 幂等 ─────────────────
    add("P10-pending-mutation-dup-key", "pending mutation 复合幂等键重复必须被拒绝",
        f"""INSERT INTO working_paper_pending_mutation
              (id, project_id, wp_id, entry_id, sheet_key, user_id, expected_revision,
               payload_artifact_id, payload_sha256, idempotency_key, expires_at)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', 'Sheet2', '{i['user']}', 1,
                    '{i['art_pending_payload']}', '{sha['pending_payload']}', 'flush-1', now() + interval '5 minutes')""")
    add("P10-pending-committed-without-result", "committed pending mutation 必须留下可重放结果",
        f"UPDATE working_paper_pending_mutation SET state = 'committed', committed_at = now() WHERE id = '{i['pending_mutation']}'")
    add("P10-pending-uncommitted-with-result", "未 committed 不得预留 result",
        f"""UPDATE working_paper_pending_mutation SET result_content_version_id = '{i['cv1']}'
             WHERE id = '{i['pending_mutation']}'""")
    add("P10-pending-ttl-inverted", "pending mutation TTL 必须晚于 created_at",
        f"""INSERT INTO working_paper_pending_mutation
              (id, project_id, wp_id, entry_id, sheet_key, user_id, expected_revision,
               payload_artifact_id, payload_sha256, idempotency_key, created_at, expires_at)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', 'Sheet3', '{i['user']}', 1,
                    '{i['art_pending_payload']}', '{sha['pending_payload']}', 'flush-ttl',
                    now(), now() - interval '1 minute')""")
    add("P10-duplicate-application-key", "同 application_key 重复必须被 UNIQUE 拒绝",
        app_insert(str(n()), _d("application-key"), str(i["req_b"]), 2, 2,
                   str(i["art_incoming_ok"]), sha["incoming_ok"]))

    # ── Property 11：唯一 descriptor + ready 后确认 ────────────────────────
    add("P11-duplicate-active-confirmation", "同 (room,participant,generation) 只能一个 active confirmation",
        f"""INSERT INTO working_paper_oo_client_confirmation
              (id, room_id, participant_id, generation, doc_key, representation_id, artifact_sha256,
               content_version_id, projection_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_sha256, bundle_slots_digest, write_fence_epoch, idempotency_key)
            VALUES ('{n()}', '{i['room']}', '{i['part_a']}', 1, 'gt-room-{i['room']}-1', '{i['rep_g2']}',
                    '{sha['canonical_g2']}', '{i['cv1']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{sha['authority']}', '{_d('slots')}', 1, 'ready-a2')""")
    add("P11-confirmation-empty-bundle-digest", "confirmation 的 bundle digest 不得为空串",
        f"""INSERT INTO working_paper_oo_client_confirmation
              (id, room_id, participant_id, generation, doc_key, representation_id, artifact_sha256,
               content_version_id, projection_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_sha256, bundle_slots_digest, write_fence_epoch, idempotency_key)
            VALUES ('{n()}', '{i['room']}', '{i['part_b']}', 1, 'gt-room-{i['room']}-1', '{i['rep_g2']}',
                    '{sha['canonical_g2']}', '{i['cv1']}', '{sha['projection']}', '{i['bundle']}', '',
                    '{sha['authority']}', '{_d('slots')}', 1, 'ready-empty')""")
    add("P11-confirmation-zero-hash-authority", "confirmation 的 authority digest 不得为全零 hash",
        f"""INSERT INTO working_paper_oo_client_confirmation
              (id, room_id, participant_id, generation, doc_key, representation_id, artifact_sha256,
               content_version_id, projection_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_sha256, bundle_slots_digest, write_fence_epoch, idempotency_key)
            VALUES ('{n()}', '{i['room']}', '{i['part_b']}', 1, 'gt-room-{i['room']}-1', '{i['rep_g2']}',
                    '{sha['canonical_g2']}', '{i['cv1']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{_ZERO_DIGEST}', '{_d('slots')}', 1, 'ready-zero')""")
    add("P11-confirmation-stale-generation", "confirmation 的 generation 与 room 不一致必须 409/拒绝",
        f"""INSERT INTO working_paper_oo_client_confirmation
              (id, room_id, participant_id, generation, doc_key, representation_id, artifact_sha256,
               content_version_id, projection_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_sha256, bundle_slots_digest, write_fence_epoch, idempotency_key)
            VALUES ('{n()}', '{i['room']}', '{i['part_b']}', 2, 'gt-room-{i['room']}-1', '{i['rep_g2']}',
                    '{sha['canonical_g2']}', '{i['cv1']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{sha['authority']}', '{_d('slots')}', 1, 'ready-stale')""")
    add("P11-confirmation-bundle-not-locked", "confirmation 的 bundle 与 representation 未双向锁死必须被拒绝",
        f"""INSERT INTO working_paper_oo_client_confirmation
              (id, room_id, participant_id, generation, doc_key, representation_id, artifact_sha256,
               content_version_id, projection_sha256, definition_bundle_id, definition_bundle_sha256,
               authority_model_definition_sha256, bundle_slots_digest, write_fence_epoch, idempotency_key)
            VALUES ('{n()}', '{i['room']}', '{i['part_b']}', 1, 'gt-room-{i['room']}-1', '{i['rep_g2']}',
                    '{sha['canonical_g2']}', '{i['cv1']}', '{sha['projection']}', '{i['bundle_custom']}',
                    '{sha['bundle_custom']}', '{sha['authority_custom']}', '{_d('slots')}', 1, 'ready-wrong-bundle')""")

    # ── Property 18：delivery 可多次、frozen application 恰一次 ─────────────
    add("P18-two-primaries-same-application", "一个 application 只能被一个 primary operation 绑定",
        op_insert(str(n()), None, str(i["app"]), None, "application_bound"))
    add("P18-both-application-and-duplicate", "operation 不得同时绑定 application 与 duplicate 指针",
        op_insert(str(n()), None, str(i["app"]), str(i["op_a"]), "duplicate"))
    add("P18-duplicate-chain", "duplicate 不得指向另一个 duplicate（禁链/环）",
        op_insert(str(n()), None, None, str(i["op_b"]), "duplicate"))
    add("P18-duplicate-target-unbound", "duplicate 目标必须已绑定 application（禁 stranded）",
        "\n;".join([
            op_insert(str(shell := n()), None, None, None, "waiting_application"),
            op_insert(str(n()), None, None, str(shell), "duplicate"),
        ]))
    add("P18-duplicate-cross-entry", "duplicate 目标必须同 scope",
        op_insert(str(n()), None, None, str(i["op_a"]), "duplicate", entry_override="other.entry"))
    add("P18-duplicate-cross-bundle", "duplicate 目标必须同 frozen bundle",
        op_insert(str(n()), None, None, str(i["op_a"]), "duplicate",
                  bundle=str(i["bundle_custom"]), bundle_sha=sha["bundle_custom"]))
    add("P18-duplicate-state-not-terminal", "带 duplicate 指针的 operation 必须 state=duplicate",
        op_insert(str(n()), None, None, str(i["op_a"]), "applied"))
    add("P18-duplicate-rebind-application", "duplicate 不得再绑定 application",
        f"UPDATE working_paper_sync_operation SET application_id = '{i['app']}', application_bound_at = now() WHERE id = '{i['op_b']}'")
    add("P18-primary-unbind-application", "primary 已绑定 application 后不得解绑/改绑",
        f"UPDATE working_paper_sync_operation SET application_id = NULL, application_bound_at = NULL WHERE id = '{i['op_a']}'")
    add("P18-duplicate-pointer-deleted", "duplicate 指针不得被删除",
        f"UPDATE working_paper_sync_operation SET duplicate_of_operation_id = NULL, state = 'applied' WHERE id = '{i['op_b']}'")
    add("P18-two-open-close-captures", "同 (room,generation) 只能有一个 open close_capture",
        f"""INSERT INTO working_paper_forcesave_request
              (id, room_id, generation, request_sequence, kind, initiated_by_participant_id,
               initiator_permission_epoch, client_edit_epoch, write_fence_epoch, client_base_version_id,
               client_base_representation_id, client_base_projection_sha256, definition_bundle_id,
               definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256,
               adapter_build_digest, contributor_snapshot_digest, idempotency_key,
               frozen_request_fingerprint, state)
            VALUES ('{n()}', '{i['room']}', 1, 4, 'close_capture', '{i['part_a']}', 5, 7, 1, '{i['cv1']}',
                    '{i['rep_g2']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{i['def_authority']}', '{sha['authority']}', '{ad}', '{_d('contributors')}',
                    'idem-close-2', '{_d('fingerprint-close-2')}', 'frozen')""")
    add("P18-delivery-primary-application-mismatch", "delivery 引用 primary 时 application 必须相等",
        "\n;".join([
            app_insert(str(aid := n()), _d("second-application"), str(i["req_b"]), 2, 2,
                       str(i["art_incoming_ok"]), sha["incoming_ok"]),
            f"""INSERT INTO working_paper_callback_delivery
                  (id, project_id, wp_id, entry_id, room_id, generation, operation_id, application_id,
                   route_credential_id, callback_status, delivery_key, state, incoming_artifact_id, durable_at)
                VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['op_a']}', '{aid}',
                        '{i['user']}', 6, '{_d('delivery-mismatch')}', 'durable', '{i['art_incoming_ok']}', now())""",
        ]))
    add("P18-delivery-duplicate-primary-mismatch", "delivery 引用 duplicate 时其 direct primary 的 application 必须相等",
        "\n;".join([
            app_insert(str(aid2 := n()), _d("third-application"), str(i["req_b"]), 2, 2,
                       str(i["art_incoming_ok"]), sha["incoming_ok"]),
            f"""INSERT INTO working_paper_callback_delivery
                  (id, project_id, wp_id, entry_id, room_id, generation, operation_id, application_id,
                   route_credential_id, callback_status, delivery_key, state, incoming_artifact_id, durable_at)
                VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['op_b']}', '{aid2}',
                        '{i['user']}', 2, '{_d('delivery-dup-mismatch')}', 'durable', '{i['art_incoming_ok']}', now())""",
        ]))
    add("P18-delivery-double-owner", "delivery 任何阶段都不得双 owner",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, application_id, callback_recovery_case_id,
               route_credential_id, callback_status, delivery_key, state, incoming_artifact_id, durable_at)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['app']}', '{i['recovery_case']}',
                    '{i['user']}', 2, '{_d('delivery-double')}', 'durable', '{i['art_incoming_ok']}', now())""")
    add("P18-durable-delivery-zero-owner", "durable delivery 必须恰有一个 owner",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, route_credential_id,
               callback_status, delivery_key, state, incoming_artifact_id, durable_at)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['user']}',
                    6, '{_d('delivery-zero-owner')}', 'durable', '{i['art_incoming_ok']}', now())""")
    add("P18-unmatched-with-application", "unmatched delivery 的 request/application/operation 必须全空",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, application_id, route_credential_id,
               callback_status, delivery_key, state, correlation_result, incoming_artifact_id, durable_at)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['app']}', '{i['user']}',
                    2, '{_d('delivery-unmatched-app')}', 'unmatched', 'unmatched', '{i['art_incoming_ok']}', now())""")
    add("P18-durable-state-without-durable-fact", "state=durable 却无 durable_at（把泛化 terminal 当 durable）必须被拒绝",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, application_id, route_credential_id,
               callback_status, delivery_key, state, incoming_artifact_id)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['app']}', '{i['user']}',
                    6, '{_d('delivery-fake-durable')}', 'durable', '{i['art_incoming_ok']}')""")
    add("P18-delivery-key-duplicate", "delivery_key 必须唯一",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, route_credential_id,
               callback_status, delivery_key, state)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['user']}',
                    6, '{_d('delivery-6')}', 'received')""")
    add("P18-durable-at-cleared", "durable_at 是 immutable durable fact，不得清空",
        f"UPDATE working_paper_callback_delivery SET durable_at = NULL WHERE id = '{i['del_1']}'")
    add("P18-post-durable-owner-dropped", "post-durable 不得丢弃既有 owner",
        f"UPDATE working_paper_callback_delivery SET application_id = NULL, state = 'error' WHERE id = '{i['del_1']}'")
    add("P18-recovery-pre-claim-has-operation", "recovery case claim 前不得有 operation/application/request",
        f"UPDATE working_paper_callback_recovery_case SET operation_id = '{i['op_a']}' WHERE id = '{i['recovery_case']}'")
    add("P18-recovery-claimed-without-all-entities", "claim 成功必须一次性写三实体 + prior confirmation + frozen bundle",
        f"""UPDATE working_paper_callback_recovery_case
               SET state = 'application_created', claimed_at = now(), operation_id = '{i['op_a']}'
             WHERE id = '{i['recovery_case']}'""")
    add("P18-recovery-download-only-with-entities", "download-only 三实体恒空",
        f"""UPDATE working_paper_callback_recovery_case
               SET state = 'download_only', application_id = '{i['app']}'
             WHERE id = '{i['recovery_case']}'""")

    # ── Property 62：server last-applied 与 client-confirmed base 不混同 ────
    add("P62-room-partial-client-confirmed", "client-confirmed 快照必须整组具备（bundle id/digest 不得半缺）",
        f"""UPDATE working_paper_oo_room SET client_confirmed_definition_bundle_sha256 = NULL WHERE id = '{i['room']}'""")
    add("P62-room-refresh-without-reason", "refresh_required 必须留下原因与时间",
        f"UPDATE working_paper_oo_room SET state = 'refresh_required' WHERE id = '{i['room']}'")
    add("P62-room-durable-sequence-regress", "room durable fence 只可单调提升",
        f"UPDATE working_paper_oo_room SET latest_durable_sequence = 1 WHERE id = '{i['room']}'")
    add("P62-room-write-fence-regress", "write fence 只可单调提升",
        f"UPDATE working_paper_oo_room SET write_fence_epoch = 0 WHERE id = '{i['room']}'")
    add("P62-room-eligibility-epoch-regress", "close leader eligibility epoch 只可单调提升",
        f"UPDATE working_paper_oo_room SET close_leader_eligibility_epoch = 0 WHERE id = '{i['room']}'")
    add("P62-room-durable-exceeds-request", "durable fence 不得超过已发出的 request fence",
        f"UPDATE working_paper_oo_room SET latest_durable_sequence = 99 WHERE id = '{i['room']}'")
    add("P62-room-identity-mutated", "room 身份列（doc_key/generation/opened_base）不可变",
        f"UPDATE working_paper_oo_room SET generation = 2 WHERE id = '{i['room']}'")
    add("P62-room-unknown-state", "room state 必须在封闭枚举内",
        f"UPDATE working_paper_oo_room SET state = 'whatever' WHERE id = '{i['room']}'")

    # ── Property 64：application identity 用 frozen bundle 且不含 status ────
    add("P64-application-origin-sequence-rewritten", "origin_request_sequence 永不改写",
        f"UPDATE working_paper_content_application SET origin_request_sequence = 5 WHERE id = '{i['app']}'")
    add("P64-application-effective-sequence-regress", "effective_request_sequence 只可单调提升",
        f"UPDATE working_paper_content_application SET effective_request_sequence = 1 WHERE id = '{i['app']}'")
    add("P64-application-effective-below-origin", "effective 不得低于 origin",
        app_insert(str(n()), _d("app-eff-below"), str(i["req_b"]), 2, 1,
                   str(i["art_incoming_ok"]), sha["incoming_ok"]))
    add("P64-application-key-mutated", "application_key 不可变",
        f"UPDATE working_paper_content_application SET application_key = '{_d('new-key')}' WHERE id = '{i['app']}'")
    add("P64-application-self-supersede", "同 canonical application 不得 self-supersede",
        f"UPDATE working_paper_content_application SET superseded_by_application_id = '{i['app']}' WHERE id = '{i['app']}'")
    add("P64-application-on-quarantined-incoming", "quarantined incoming 不得创建 application",
        app_insert(str(n()), _d("app-quarantined"), str(i["req_b"]), 2, 2,
                   str(i["art_incoming_quarantined"]), sha["incoming_quarantined"]))
    add("P64-application-on-canonical-artifact", "application 的 incoming 必须 kind=incoming",
        app_insert(str(n()), _d("app-canonical"), str(i["req_b"]), 2, 2,
                   str(i["art_canonical_g1"]), sha["canonical_g1"]))
    add("P64-application-zero-bundle-digest", "bundle digest 不得为全零 hash",
        app_insert(str(n()), _d("app-zero-bundle"), str(i["req_b"]), 2, 2,
                   str(i["art_incoming_ok"]), sha["incoming_ok"],
                   bundle=str(i["bundle"]), bundle_sha=_ZERO_DIGEST))
    add("P64-application-origin-sequence-mismatch", "origin_request_sequence 必须等于 origin request 的 sequence",
        app_insert(str(n()), _d("app-seq-mismatch"), str(i["req_b"]), 1, 2,
                   str(i["art_incoming_ok"]), sha["incoming_ok"]))
    add("P64-application-base-not-frozen", "application 的 frozen base 必须来自 origin request",
        app_insert(str(n()), _d("app-base-drift"), str(i["req_b"]), 2, 2,
                   str(i["art_incoming_ok"]), sha["incoming_ok"], base_version=str(i["cv2"])))
    add("P64-request-idempotency-reuse-same-participant", "同 (room,generation,initiator,kind,key) 重复必须被拒绝",
        f"""INSERT INTO working_paper_forcesave_request
              (id, room_id, generation, request_sequence, kind, initiated_by_participant_id,
               initiator_permission_epoch, client_edit_epoch, write_fence_epoch, client_base_version_id,
               client_base_representation_id, client_base_projection_sha256, definition_bundle_id,
               definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256,
               adapter_build_digest, contributor_snapshot_digest, idempotency_key,
               frozen_request_fingerprint, state)
            VALUES ('{n()}', '{i['room']}', 1, 5, 'forcesave', '{i['part_a']}', 5, 7, 1, '{i['cv1']}',
                    '{i['rep_g2']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{i['def_authority']}', '{sha['authority']}', '{ad}', '{_d('contributors')}',
                    'idem-a', '{_d('fingerprint-other')}', 'frozen')""")
    add("P64-request-duplicate-sequence", "同 (room,generation,request_sequence) 必须唯一",
        f"""INSERT INTO working_paper_forcesave_request
              (id, room_id, generation, request_sequence, kind, initiated_by_participant_id,
               initiator_permission_epoch, client_edit_epoch, write_fence_epoch, client_base_version_id,
               client_base_representation_id, client_base_projection_sha256, definition_bundle_id,
               definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256,
               adapter_build_digest, contributor_snapshot_digest, idempotency_key,
               frozen_request_fingerprint, state)
            VALUES ('{n()}', '{i['room']}', 1, 1, 'forcesave', '{i['part_a']}', 5, 7, 1, '{i['cv1']}',
                    '{i['rep_g2']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{i['def_authority']}', '{sha['authority']}', '{ad}', '{_d('contributors')}',
                    'idem-seq-dup', '{_d('fingerprint-seq-dup')}', 'frozen')""")
    add("P64-request-frozen-field-mutated", "request 冻结字段不可变",
        f"UPDATE working_paper_forcesave_request SET client_base_version_id = '{i['cv2']}' WHERE id = '{i['req_a']}'")
    add("P64-request-fingerprint-empty", "frozen_request_fingerprint 不得为空串",
        f"""INSERT INTO working_paper_forcesave_request
              (id, room_id, generation, request_sequence, kind, initiated_by_participant_id,
               initiator_permission_epoch, client_edit_epoch, write_fence_epoch, client_base_version_id,
               client_base_representation_id, client_base_projection_sha256, definition_bundle_id,
               definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256,
               adapter_build_digest, contributor_snapshot_digest, idempotency_key,
               frozen_request_fingerprint, state)
            VALUES ('{n()}', '{i['room']}', 1, 6, 'forcesave', '{i['part_a']}', 5, 7, 1, '{i['cv1']}',
                    '{i['rep_g2']}', '{sha['projection']}', '{i['bundle']}', '{sha['bundle']}',
                    '{i['def_authority']}', '{sha['authority']}', '{ad}', '{_d('contributors')}',
                    'idem-empty-fp', '', 'frozen')""")
    add("P64-request-bundle-drift", "request 冻结的 bundle 必须与 client base representation 一致",
        f"""INSERT INTO working_paper_forcesave_request
              (id, room_id, generation, request_sequence, kind, initiated_by_participant_id,
               initiator_permission_epoch, client_edit_epoch, write_fence_epoch, client_base_version_id,
               client_base_representation_id, client_base_projection_sha256, definition_bundle_id,
               definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256,
               adapter_build_digest, contributor_snapshot_digest, idempotency_key,
               frozen_request_fingerprint, state)
            VALUES ('{n()}', '{i['room']}', 1, 7, 'forcesave', '{i['part_a']}', 5, 7, 1, '{i['cv1']}',
                    '{i['rep_g2']}', '{sha['projection']}', '{i['bundle_custom']}', '{sha['bundle_custom']}',
                    '{i['def_authority_custom']}', '{sha['authority_custom']}', '{ad}', '{_d('contributors')}',
                    'idem-bundle-drift', '{_d('fingerprint-bundle-drift')}', 'frozen')""")
    add("P64-operation-bundle-drift-from-request", "operation 的 frozen bundle 必须与 request 一致",
        op_insert(str(n()), str(i["req_close"]), None, None, "accepted",
                  bundle=str(i["bundle_custom"]), bundle_sha=sha["bundle_custom"]))
    add("P64-operation-application-cross-bundle", "primary 绑定的 application 必须同 frozen bundle",
        "\n;".join([
            app_insert(str(aid3 := n()), _d("app-other-bundle"), str(i["req_b"]), 2, 2,
                       str(i["art_incoming_ok"]), sha["incoming_ok"]),
            op_insert(str(n()), None, str(aid3), None, "application_bound",
                      bundle=str(i["bundle_custom"]), bundle_sha=sha["bundle_custom"]),
        ]))
    add("P64-operation-bound-without-timestamp", "绑定 application 必须同时写 application_bound_at",
        op_insert(str(n()), None, str(i["app"]), None, "application_bound", bound_at=False))
    add("P64-two-shells-one-request", "每个 request 最多一个 operation shell",
        op_insert(str(n()), str(i["req_a"]), None, None, "accepted"))

    # ── bundle typed slots（Requirement 2.3 / 3.3；P4/P10/P11/P64 共同前置）─
    add("BUNDLE-null-slot-ref", "slot ref 为 SQL NULL 必须被 NOT NULL 拒绝",
        f"""INSERT INTO working_paper_sync_definition_bundle
              (id, authority_model_definition_id, authority_model_definition_sha256,
               template_slot_type, template_slot_ref, template_slot_digest,
               instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest,
               contract_slot_type, contract_slot_ref, contract_slot_digest,
               canonical_payload_artifact_id, canonical_payload_sha256, state, approved_at)
            VALUES ('{n()}', '{i['def_authority']}', '{sha['authority']}',
                    'definition', NULL, '{sha['tpl']}',
                    'definition', 'definition:{i['def_instr']}', '{sha['instr']}',
                    'definition', 'definition:{i['def_contract']}', '{sha['contract']}',
                    '{i['art_bundle_payload']}', '{_d('bundle-null-ref')}', 'approved', now())""")
    add("BUNDLE-empty-slot-digest", "slot digest 空串必须被拒绝",
        bundle_insert(str(n()), str(i["def_authority"]), sha["authority"],
                      ("definition", f"definition:{i['def_tpl']}", ""),
                      ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                      ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                      str(i["art_bundle_payload"]), _d("bundle-empty-digest")))
    add("BUNDLE-zero-slot-digest", "slot digest 全零 hash 必须被拒绝",
        bundle_insert(str(n()), str(i["def_authority"]), sha["authority"],
                      ("definition", f"definition:{i['def_tpl']}", _ZERO_DIGEST),
                      ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                      ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                      str(i["art_bundle_payload"]), _d("bundle-zero-digest")))
    add("BUNDLE-slot-child-not-approved", "definition child 必须 approved",
        bundle_insert(str(n()), str(i["def_authority"]), sha["authority"],
                      ("definition", f"definition:{i['def_tpl_candidate']}", sha["tpl_candidate"]),
                      ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                      ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                      str(i["art_bundle_payload"]), _d("bundle-unapproved-child")))
    add("BUNDLE-slot-child-wrong-kind", "template slot 不得引用 contract definition",
        bundle_insert(str(n()), str(i["def_authority"]), sha["authority"],
                      ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                      ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                      ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                      str(i["art_bundle_payload"]), _d("bundle-wrong-kind")))
    add("BUNDLE-slot-digest-mismatch", "slot digest 必须等于 child 实际 sha256",
        bundle_insert(str(n()), str(i["def_authority"]), sha["authority"],
                      ("definition", f"definition:{i['def_tpl']}", _d("not-template-digest")),
                      ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                      ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                      str(i["art_bundle_payload"]), _d("bundle-digest-mismatch")))
    add("BUNDLE-projection-contract-with-marker", "projection_contract 不得用 marker 冒充 contract child",
        bundle_insert(str(n()), str(i["def_authority"]), sha["authority"],
                      ("definition", f"definition:{i['def_tpl']}", sha["tpl"]),
                      ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                      ("contract:none:v1", "marker:contract:none:v1", _marker_digest("contract")),
                      str(i["art_bundle_payload"]), _d("bundle-marker-contract")))
    add("BUNDLE-unregistered-marker", "未登记的 typed null marker 必须被拒绝",
        bundle_insert(str(n()), str(i["def_authority_custom"]), sha["authority_custom"],
                      ("definition", f"definition:{i['def_tpl']}", sha["tpl"]),
                      ("instrumentation:none:v9", "marker:instrumentation:none:v9", _marker_digest("instrumentation")),
                      ("contract:none:v1", "marker:contract:none:v1", _marker_digest("contract")),
                      str(i["art_bundle_payload"]), _d("bundle-unregistered-marker")))
    add("BUNDLE-marker-digest-forged", "marker digest 必须等于 registry 真实 digest",
        bundle_insert(str(n()), str(i["def_authority_custom"]), sha["authority_custom"],
                      ("definition", f"definition:{i['def_tpl']}", sha["tpl"]),
                      ("instrumentation:none:v1", "marker:instrumentation:none:v1", _d("forged-marker")),
                      ("contract:none:v1", "marker:contract:none:v1", _marker_digest("contract")),
                      str(i["art_bundle_payload"]), _d("bundle-forged-marker")))
    add("BUNDLE-marker-wrong-slot", "marker 必须用于其登记槽位",
        bundle_insert(str(n()), str(i["def_authority_custom"]), sha["authority_custom"],
                      ("definition", f"definition:{i['def_tpl']}", sha["tpl"]),
                      ("instrumentation:none:v1", "marker:instrumentation:none:v1", _marker_digest("instrumentation")),
                      ("contract:none:v1", "marker:instrumentation:none:v1", _marker_digest("instrumentation")),
                      str(i["art_bundle_payload"]), _d("bundle-marker-wrong-slot")))
    add("BUNDLE-authority-child-not-approved", "authority model child 必须 approved",
        "\n;".join([
            f"""INSERT INTO working_paper_sync_definition_artifact
                  (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, authority_model_type, source_commit, state)
                VALUES ('{(aid4 := n())}', 'authority_model', 'authority.pending', '1.0.0', '{i['art_authority']}',
                        '{_d('authority-pending')}', 'projection_contract', 'abc1234', 'candidate')""",
            bundle_insert(str(n()), str(aid4), _d("authority-pending"),
                          ("definition", f"definition:{i['def_tpl']}", sha["tpl"]),
                          ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                          ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                          str(i["art_bundle_payload"]), _d("bundle-pending-authority")),
        ]))
    add("BUNDLE-authority-wrong-kind", "authority slot 不得引用 template definition",
        bundle_insert(str(n()), str(i["def_tpl"]), sha["tpl"],
                      ("definition", f"definition:{i['def_tpl']}", sha["tpl"]),
                      ("definition", f"definition:{i['def_instr']}", sha["instr"]),
                      ("definition", f"definition:{i['def_contract']}", sha["contract"]),
                      str(i["art_bundle_payload"]), _d("bundle-authority-wrong-kind")))
    add("BUNDLE-approved-mutated", "approved bundle 的 typed slots 不可修改/重组",
        f"""UPDATE working_paper_sync_definition_bundle
               SET contract_slot_type = 'contract:none:v1',
                   contract_slot_ref = 'marker:contract:none:v1',
                   contract_slot_digest = '{_marker_digest('contract')}'
             WHERE id = '{i['bundle']}'""")
    add("BUNDLE-marker-registry-mutated", "typed null marker registry 不可变",
        f"UPDATE working_paper_sync_definition_null_marker SET sha256 = '{_d('tampered-marker')}' WHERE marker_id = 'contract:none:v1'")
    add("BUNDLE-unversioned-marker-registered", "marker id 必须自带版本后缀",
        f"""INSERT INTO working_paper_sync_definition_null_marker
              (marker_id, applies_to_slot, marker_version, canonical_payload, sha256)
            VALUES ('contract:none', 'contract', 'v1', '{{}}', '{_d('unversioned-marker')}')""")
    add("BUNDLE-authority-model-type-on-template", "非 authority_model definition 不得携带 authority_model_type",
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, authority_model_type, source_commit, state)
            VALUES ('{n()}', 'template', 'bad.template', '1.0.0', '{i['art_tpl']}',
                    '{_d('bad-template')}', 'projection_contract', 'abc1234', 'candidate')""")
    add("BUNDLE-authority-model-unknown-enum", "authority model 枚举必须封闭",
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, authority_model_type, source_commit, state)
            VALUES ('{n()}', 'authority_model', 'bad.authority', '1.0.0', '{i['art_authority']}',
                    '{_d('bad-authority')}', 'freestyle_model', 'abc1234', 'candidate')""")
    # 🔴 `wpsync_is_digest` 的**隔离**判据：bundle slot 的全零/空串 digest 会先被
    #    「slot digest 必须等于 child 实际 sha256」遮蔽 ⇒ 那两条无法单独证明
    #    digest 谓词有效（变异 M32 曾判 GREEN）。故另用**无跨行比对**的 digest 列
    #    （participant.lease_token_hash）单独打这条谓词。
    add("BUNDLE-zero-hash-standalone", "全零 hash 不得充当任何身份 digest（无跨行比对的隔离判据）",
        f"""INSERT INTO working_paper_oo_participant
              (id, room_id, user_id, mode, state, permission_epoch, joined_write_fence_epoch, lease_token_hash, expires_at)
            VALUES ('{n()}', '{i['room']}', '{i['user_b']}', 'view', 'expired', 5, 1, '{_ZERO_DIGEST}', now() + interval '1 hour')""")
    add("BUNDLE-empty-hash-standalone", "空串不得充当任何身份 digest（无跨行比对的隔离判据）",
        f"""INSERT INTO working_paper_oo_participant
              (id, room_id, user_id, mode, state, permission_epoch, joined_write_fence_epoch, lease_token_hash, expires_at)
            VALUES ('{n()}', '{i['room']}', '{i['user_b']}', 'view', 'expired', 5, 1, '', now() + interval '1 hour')""")
    add("BUNDLE-authority-model-missing-on-authority", "kind=authority_model 必须携带封闭枚举",
        f"""INSERT INTO working_paper_sync_definition_artifact
              (id, kind, logical_id, semantic_version, blob_artifact_id, sha256, source_commit, state)
            VALUES ('{n()}', 'authority_model', 'bad.authority2', '1.0.0', '{i['art_authority']}',
                    '{_d('bad-authority2')}', 'abc1234', 'candidate')""")

    # ── scope index（authorization-only + tombstone 不灭）───────────────────
    add("SCOPE-physical-delete", "scope index 禁止物理删除",
        f"DELETE FROM working_paper_sync_scope_index WHERE resource_kind = 'room' AND resource_id = '{i['room']}'")
    add("SCOPE-tombstone-cleared", "tombstone 不可清空",
        "\n;".join([
            f"""UPDATE working_paper_sync_scope_index SET retired_at = now()
                 WHERE resource_kind = 'room' AND resource_id = '{i['room']}'""",
            f"""UPDATE working_paper_sync_scope_index SET retired_at = NULL
                 WHERE resource_kind = 'room' AND resource_id = '{i['room']}'""",
        ]))
    add("SCOPE-cross-scope-rebind", "scope 不可变（禁跨 scope 重绑）",
        f"""UPDATE working_paper_sync_scope_index SET entry_id = 'other.entry'
             WHERE resource_kind = 'room' AND resource_id = '{i['room']}'""")
    add("SCOPE-numeric-revision-as-resource-id", "numeric revision 禁作 scope key",
        f"""INSERT INTO working_paper_sync_scope_index (resource_kind, resource_id, project_id, wp_id, entry_id)
            VALUES ('content_version', '1', '{p}', '{wp}', '{entry}')""")
    # 🔴 上一条同时会被 `ck_wpssi_content_version_uuid` 拦住 ⇒ 无法单独证明 opaque 谓词
    #    有效（变异 M37 曾判 GREEN）。故再用非 content_version 的 kind 做隔离判据。
    add("SCOPE-numeric-resource-id-non-version", "任何 resource_kind 的纯数字 resource_id 都禁用（隔离判据）",
        f"""INSERT INTO working_paper_sync_scope_index (resource_kind, resource_id, project_id, wp_id, entry_id)
            VALUES ('sync_operation', '12', '{p}', '{wp}', '{entry}')""")
    add("SCOPE-content-version-non-uuid", "content_version 的 resource_id 必须是 UUID",
        f"""INSERT INTO working_paper_sync_scope_index (resource_kind, resource_id, project_id, wp_id, entry_id)
            VALUES ('content_version', 'rev-2', '{p}', '{wp}', '{entry}')""")
    add("SCOPE-resource-id-reuse", "(resource_kind,resource_id) 永不复用（PK）",
        f"""INSERT INTO working_paper_sync_scope_index (resource_kind, resource_id, project_id, wp_id, entry_id)
            VALUES ('room', '{i['room']}', '{p}', '{wp}', 'another.entry')""")
    add("SCOPE-unknown-resource-kind", "resource_kind 必须在封闭枚举内",
        f"""INSERT INTO working_paper_sync_scope_index (resource_kind, resource_id, project_id, wp_id, entry_id)
            VALUES ('secret_payload', '{n()}', '{p}', '{wp}', '{entry}')""")

    # ── Property 68：timeline 完整单调 / append-only ────────────────────────
    add("P68-operation-event-dup-sequence", "operation event (operation_id,sequence_no) 必须唯一",
        f"""INSERT INTO working_paper_sync_operation_event
              (operation_id, sequence_no, to_state, actor_type) VALUES ('{i['op_a']}', 1, 'applied', 'system')""")
    add("P68-operation-event-update", "operation timeline 禁止 UPDATE",
        f"UPDATE working_paper_sync_operation_event SET to_state = 'applied' WHERE operation_id = '{i['op_a']}'")
    add("P68-operation-event-delete", "operation timeline 禁止删除中间 event",
        f"DELETE FROM working_paper_sync_operation_event WHERE operation_id = '{i['op_a']}'")
    add("P68-two-application-bound-events", "同 operation 只能有一个 application_bound event",
        f"""INSERT INTO working_paper_sync_operation_event
              (operation_id, sequence_no, to_state, actor_type) VALUES ('{i['op_a']}', 2, 'application_bound', 'system')""")
    add("P68-two-duplicate-events", "同 operation 只能有一个 duplicate terminal event",
        f"""INSERT INTO working_paper_sync_operation_event
              (operation_id, sequence_no, to_state, actor_type) VALUES ('{i['op_b']}', 2, 'duplicate', 'system')""")
    add("P68-application-event-update", "application timeline 禁止 UPDATE",
        f"UPDATE working_paper_content_application_event SET effective_request_sequence = 9 WHERE application_id = '{i['app']}'")
    add("P68-application-event-delete", "application timeline 禁止删除",
        f"DELETE FROM working_paper_content_application_event WHERE application_id = '{i['app']}'")
    add("P68-fold-event-without-request", "sequence_folded 必须记录被折叠的 request",
        f"""INSERT INTO working_paper_content_application_event
              (application_id, sequence_no, event_type, origin_request_sequence, effective_request_sequence,
               room_latest_durable_sequence, actor_type)
            VALUES ('{i['app']}', 3, 'sequence_folded', 1, 3, 3, 'callback')""")
    add("P68-fold-event-without-room-fence", "sequence_folded 必须同事务写 room durable fence",
        f"""INSERT INTO working_paper_content_application_event
              (application_id, sequence_no, event_type, folded_request_id, origin_request_sequence,
               effective_request_sequence, actor_type)
            VALUES ('{i['app']}', 4, 'sequence_folded', '{i['req_close']}', 1, 3, 'callback')""")
    add("P68-fold-same-request-twice", "同 request 对同 application 只能 fold 一次",
        f"""INSERT INTO working_paper_content_application_event
              (application_id, sequence_no, event_type, folded_request_id, origin_request_sequence,
               effective_request_sequence, room_latest_durable_sequence, actor_type)
            VALUES ('{i['app']}', 5, 'sequence_folded', '{i['req_b']}', 1, 2, 2, 'callback')""")
    add("P68-fold-event-effective-below-origin", "event 的 effective 不得低于 origin",
        f"""INSERT INTO working_paper_content_application_event
              (application_id, sequence_no, event_type, folded_request_id, origin_request_sequence,
               effective_request_sequence, room_latest_durable_sequence, actor_type)
            VALUES ('{i['app']}', 6, 'sequence_folded', '{i['req_close']}', 5, 2, 2, 'callback')""")
    add("P68-recovery-event-update", "recovery case timeline 禁止 UPDATE",
        f"UPDATE working_paper_callback_recovery_case_event SET to_state = 'application_created' WHERE case_id = '{i['recovery_case']}'")
    add("P68-recovery-event-delete", "recovery case timeline 禁止删除",
        f"DELETE FROM working_paper_callback_recovery_case_event WHERE case_id = '{i['recovery_case']}'")
    add("P68-recovery-event-dup-sequence", "recovery event (case_id,sequence_no) 必须唯一",
        f"""INSERT INTO working_paper_callback_recovery_case_event
              (case_id, sequence_no, to_state, actor_type) VALUES ('{i['recovery_case']}', 1, 'claiming', 'user')""")
    add("P68-close-intent-event-update", "close-intent timeline 禁止 UPDATE",
        f"UPDATE working_paper_oo_close_intent_event SET to_state = 'superseded' WHERE intent_id = '{i['intent_b']}'")
    add("P68-close-intent-event-delete", "close-intent timeline 禁止删除",
        f"DELETE FROM working_paper_oo_close_intent_event WHERE intent_id = '{i['intent_b']}'")
    add("P68-close-intent-event-dup-sequence", "close-intent event (intent_id,sequence_no) 必须唯一",
        f"""INSERT INTO working_paper_oo_close_intent_event
              (intent_id, sequence_no, to_state, eligibility_epoch, actor_type)
            VALUES ('{i['intent_b']}', 1, 'authorization_stale', 1, 'reconciler')""")
    add("P68-close-intent-promoted-without-request", "state=promoted 必须携带 close_capture request",
        f"UPDATE working_paper_oo_close_intent SET state = 'promoted' WHERE id = '{i['intent_a']}'")
    add("P68-close-intent-promoted-to-forcesave", "close intent 只能提升为 close_capture request",
        f"""UPDATE working_paper_oo_close_intent SET state = 'promoted', promoted_request_id = '{i['req_a']}'
             WHERE id = '{i['intent_a']}'""")
    add("P68-close-intent-dup-sequence", "同 (room,generation,intent_sequence) 必须唯一",
        f"""INSERT INTO working_paper_oo_close_intent
              (id, room_id, generation, participant_id, client_confirmation_id, intent_sequence, barrier_epoch, state)
            VALUES ('{n()}', '{i['room']}', 1, '{i['part_a']}', '{i['conf_a']}', 1, 3, 'created')""")

    # ── Property 69：evidence 由逐 scenario 实体闭合 ────────────────────────
    add("P69-scenario-dup-ordinal", "scenario (run_id,scenario_id,ordinal) 必须唯一",
        f"""INSERT INTO working_paper_entry_evidence_scenario
              (id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, application_ids,
               recovery_case_ids, authority_model_definition_sha256, definition_bundle_sha256,
               trace_bundle_artifact_id, trace_bundle_sha256, server_timeline_digest,
               database_snapshot_digest, browser_build)
            VALUES ('{n()}', '{i['test_run']}', 'oo_to_html', 1, 'standard', 'passed',
                    '["{i['op_a']}"]'::jsonb, '["{i['app']}"]'::jsonb, '[]'::jsonb,
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_trace']}', '{sha['trace']}',
                    '{_d('t2')}', '{_d('s2')}', 'chrome-131')""")
    add("P69-download-only-with-operation", "download-only scenario 的 operation/application 恒空",
        f"""INSERT INTO working_paper_entry_evidence_scenario
              (id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, application_ids,
               recovery_case_ids, authority_model_definition_sha256, definition_bundle_sha256,
               trace_bundle_artifact_id, trace_bundle_sha256, server_timeline_digest,
               database_snapshot_digest, browser_build)
            VALUES ('{n()}', '{i['test_run']}', 'download_only', 2, 'download_only', 'passed',
                    '["{i['op_a']}"]'::jsonb, '[]'::jsonb, '["{i['recovery_case']}"]'::jsonb,
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_trace']}', '{sha['trace']}',
                    '{_d('t3')}', '{_d('s3')}', 'chrome-131')""")
    add("P69-download-only-without-recovery-case", "download-only 必须绑定 recovery case",
        f"""INSERT INTO working_paper_entry_evidence_scenario
              (id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, application_ids,
               recovery_case_ids, authority_model_definition_sha256, definition_bundle_sha256,
               trace_bundle_artifact_id, trace_bundle_sha256, server_timeline_digest,
               database_snapshot_digest, browser_build)
            VALUES ('{n()}', '{i['test_run']}', 'download_only', 3, 'download_only', 'passed',
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_trace']}', '{sha['trace']}',
                    '{_d('t4')}', '{_d('s4')}', 'chrome-131')""")
    add("P69-standard-passed-without-entities", "standard passed 必须有真实 operation + application",
        f"""INSERT INTO working_paper_entry_evidence_scenario
              (id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, application_ids,
               recovery_case_ids, authority_model_definition_sha256, definition_bundle_sha256,
               trace_bundle_artifact_id, trace_bundle_sha256, server_timeline_digest,
               database_snapshot_digest, browser_build)
            VALUES ('{n()}', '{i['test_run']}', 'identity_retention', 1, 'standard', 'passed',
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_trace']}', '{sha['trace']}',
                    '{_d('t5')}', '{_d('s5')}', 'chrome-131')""")
    add("P69-scenario-bundle-cross-run", "scenario 的 bundle identity 必须与所属 run 一致",
        f"""INSERT INTO working_paper_entry_evidence_scenario
              (id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, application_ids,
               recovery_case_ids, authority_model_definition_sha256, definition_bundle_sha256,
               trace_bundle_artifact_id, trace_bundle_sha256, server_timeline_digest,
               database_snapshot_digest, browser_build)
            VALUES ('{n()}', '{i['test_run']}', 'merge_conflict', 1, 'standard', 'passed',
                    '["{i['op_a']}"]'::jsonb, '["{i['app']}"]'::jsonb, '[]'::jsonb,
                    '{sha['authority']}', '{sha['bundle_custom']}', '{i['art_trace']}', '{sha['trace']}',
                    '{_d('t6')}', '{_d('s6')}', 'chrome-131')""")
    add("P69-scenario-immutable", "scenario 是不可变实体，禁止 UPDATE",
        f"UPDATE working_paper_entry_evidence_scenario SET result = 'failed' WHERE id = '{i['scen_standard']}'")
    add("P69-test-run-profile-mutated", "test run 的 profile/identity 不可变",
        f"UPDATE working_paper_sync_test_run SET room_model = 'exclusive' WHERE id = '{i['test_run']}'")
    add("P69-test-run-result-without-finish", "未 finished 不得判定 aggregate result",
        f"""INSERT INTO working_paper_sync_test_run
              (id, entry_id, source_commit, runner_version, manifest_source_digest, editability, room_model,
               scenario_profile_digest, onlyoffice_build, browser_build, environment_digest,
               required_scenario_set_digest, authority_model_definition_sha256, definition_bundle_sha256,
               run_manifest_artifact_id, run_manifest_sha256, started_at, aggregate_result)
            VALUES ('{n()}', '{entry}', 'abc1234', 'runner-1.0', '{_d('manifest')}', 'editable', 'shared',
                    '{_d('profile')}', '9.4.0', 'chrome-131', '{_d('environment')}', '{_d('required-set')}',
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_runmanifest']}', '{sha['runmanifest']}',
                    now(), 'passed')""")
    add("P69-test-run-free-text-room-model", "room_model 必须是机器枚举，不得自由文本",
        f"""INSERT INTO working_paper_sync_test_run
              (id, entry_id, source_commit, runner_version, manifest_source_digest, editability, room_model,
               scenario_profile_digest, onlyoffice_build, browser_build, environment_digest,
               required_scenario_set_digest, authority_model_definition_sha256, definition_bundle_sha256,
               run_manifest_artifact_id, run_manifest_sha256, started_at)
            VALUES ('{n()}', '{entry}', 'abc1234', 'runner-1.0', '{_d('manifest')}', 'editable', '多人共享',
                    '{_d('profile')}', '9.4.0', 'chrome-131', '{_d('environment')}', '{_d('required-set')}',
                    '{sha['authority']}', '{sha['bundle']}', '{i['art_runmanifest']}', '{sha['runmanifest']}', now())""")

    # ── Requirement 8.1：冲突记录字段完备 ──────────────────────────────────
    add("R81-conflict-duplicate-field", "同 (operation,stable_field_key,row_key,oo_location) 必须唯一",
        f"""INSERT INTO working_paper_sync_conflict
              (id, operation_id, client_edit_epoch, stable_field_key, business_label, row_key,
               json_pointer, oo_location, field_source, protection_policy, suggested_action, conflict_kind)
            VALUES ('{n()}', '{i['op_a']}', 7, 'g7.listed.row3.amount', '其他债权投资期末余额', 'row3',
                    '/rows/3/values/1', 'Sheet1!C5', 'projection', 'editable', 'prefer_incoming', 'value')""")
    add("R81-conflict-empty-stable-key", "stable field key 不得为空",
        f"""INSERT INTO working_paper_sync_conflict
              (id, operation_id, client_edit_epoch, stable_field_key, business_label, row_key,
               json_pointer, oo_location, field_source, protection_policy, suggested_action, conflict_kind)
            VALUES ('{n()}', '{i['op_a']}', 7, '   ', '标签', 'row9', '/rows/9', 'Sheet1!C9',
                    'projection', 'editable', 'prefer_incoming', 'value')""")
    add("R81-conflict-bad-json-pointer", "JSON Pointer 必须是 / 开头或空串",
        f"""INSERT INTO working_paper_sync_conflict
              (id, operation_id, client_edit_epoch, stable_field_key, business_label, row_key,
               json_pointer, oo_location, field_source, protection_policy, suggested_action, conflict_kind)
            VALUES ('{n()}', '{i['op_a']}', 7, 'k2', '标签', 'row10', 'rows/10', 'Sheet1!C10',
                    'projection', 'editable', 'prefer_incoming', 'value')""")
    add("R81-conflict-unknown-kind", "conflict_kind 必须在封闭枚举内",
        f"""INSERT INTO working_paper_sync_conflict
              (id, operation_id, client_edit_epoch, stable_field_key, business_label, row_key,
               json_pointer, oo_location, field_source, protection_policy, suggested_action, conflict_kind)
            VALUES ('{n()}', '{i['op_a']}', 7, 'k3', '标签', 'row11', '/rows/11', 'Sheet1!C11',
                    'projection', 'editable', 'prefer_incoming', 'whatever')""")

    # ── Requirement 2.6：participant lease ────────────────────────────────
    add("R26-duplicate-active-lease", "同 room 同 user 只能一个未终结 lease",
        f"""INSERT INTO working_paper_oo_participant
              (id, room_id, user_id, mode, state, permission_epoch, joined_write_fence_epoch, lease_token_hash, expires_at)
            VALUES ('{n()}', '{i['room']}', '{i['user']}', 'edit', 'active', 6, 1, '{_d('lease-dup')}', now() + interval '1 hour')""")
    add("R26-unknown-participant-state", "participant state 必须含 closing 且为封闭枚举",
        f"UPDATE working_paper_oo_participant SET state = 'zombie' WHERE id = '{i['part_a']}'")
    add("R26-revoked-without-timestamp", "revoked 必须留下 revoked_at",
        f"UPDATE working_paper_oo_participant SET state = 'revoked' WHERE id = '{i['part_a']}'")

    return cases


# ═══════════════════════════════════════════════════════════════════════════
# 正控制矩阵：每条**必须被接受**。防「守卫过严把合法写入也拦了」。
# ═══════════════════════════════════════════════════════════════════════════


def _positive_cases(i: dict[str, Any]) -> list[tuple[str, str, str]]:
    p, wp, entry = i["project"], i["wp"], i["entry"]
    sha = i["sha"]
    n = uuid.uuid4
    cases: list[tuple[str, str, str]] = []
    add = lambda cid, why, sql: cases.append((cid, why, sql))  # noqa: E731

    add("POS-third-duplicate-shell", "第 N 个同 key shell 可继续成为 direct duplicate",
        f"""INSERT INTO working_paper_sync_operation
              (id, project_id, wp_id, entry_id, room_id, direction, state, duplicate_of_operation_id,
               definition_bundle_id, definition_bundle_sha256, authority_model_definition_id,
               authority_model_definition_sha256)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 'oo_to_html', 'duplicate', '{i['op_a']}',
                    '{i['bundle']}', '{sha['bundle']}', '{i['def_authority']}', '{sha['authority']}')""")
    add("POS-extra-delivery-same-application", "同一 application 可再有 delivery（网络重试）",
        f"""INSERT INTO working_paper_callback_delivery
              (id, project_id, wp_id, entry_id, room_id, generation, operation_id, application_id,
               route_credential_id, callback_status, delivery_key, state, incoming_artifact_id, durable_at)
            VALUES ('{n()}', '{p}', '{wp}', '{entry}', '{i['room']}', 1, '{i['op_b']}', '{i['app']}',
                    '{i['user']}', 6, '{_d('delivery-retry')}', 'durable', '{i['art_incoming_ok']}', now())""")
    add("POS-fold-effective-sequence-up", "effective_request_sequence 可单调提升",
        f"UPDATE working_paper_content_application SET effective_request_sequence = 3 WHERE id = '{i['app']}'")
    add("POS-room-durable-fence-up", "room durable fence 可单调提升",
        f"UPDATE working_paper_oo_room SET latest_request_sequence = 5, latest_durable_sequence = 3 WHERE id = '{i['room']}'")
    add("POS-scope-retire", "scope row 可以 retired_at 退役（不物理删除）",
        f"""UPDATE working_paper_sync_scope_index SET retired_at = now()
             WHERE resource_kind = 'content_application' AND resource_id = '{i['app']}'""")
    add("POS-cross-wp-same-revision", "不同 wp 的相同 numeric revision 由不同 opaque UUID 无碰撞",
        "\n;".join([
            f"INSERT INTO working_paper (id, project_id) VALUES ('{(wp2 := n())}', '{p}')",
            f"""INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, published_at)
                VALUES ('{(a2 := n())}', '{p}', '{wp2}', 'projection', 'published',
                        'storage/{p}/workpapers/.versions/{wp2}/projections/v1.json.gz', '{_d('wp2-projection')}', 1, 'json.gz', now())""",
            f"""INSERT INTO working_paper_content_version (id, wp_id, revision, source, projection_artifact_id, projection_sha256)
                VALUES ('{(cv := n())}', '{wp2}', 1, 'html', '{a2}', '{_d('wp2-projection')}')""",
            f"""INSERT INTO working_paper_sync_scope_index (resource_kind, resource_id, project_id, wp_id, entry_id)
                VALUES ('content_version', '{cv}', '{p}', '{wp2}', '{entry}')""",
        ]))
    add("POS-custom-bundle-with-markers", "custom_authoritative_ooxml 可用 registry typed null marker",
        f"""INSERT INTO working_paper_sync_definition_bundle
              (id, authority_model_definition_id, authority_model_definition_sha256,
               template_slot_type, template_slot_ref, template_slot_digest,
               instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest,
               contract_slot_type, contract_slot_ref, contract_slot_digest,
               canonical_payload_artifact_id, canonical_payload_sha256, state, approved_at)
            VALUES ('{n()}', '{i['def_authority_custom']}', '{sha['authority_custom']}',
                    'definition', 'definition:{i['def_tpl']}', '{sha['tpl']}',
                    'instrumentation:none:v1', 'marker:instrumentation:none:v1', '{_marker_digest('instrumentation')}',
                    'contract:none:v1', 'marker:contract:none:v1', '{_marker_digest('contract')}',
                    '{i['art_bundle_payload_custom']}', '{_d('bundle-custom-2')}', 'approved', now())""")
    add("POS-quarantined-download-only-expire", "quarantined incoming 可 expire 到 orphan（不 release）",
        f"UPDATE working_paper_artifact SET state = 'orphan', orphaned_at = now() WHERE id = '{i['art_incoming_quarantined']}'")
    add("POS-append-next-event", "timeline 可继续 append 递增 event",
        f"""INSERT INTO working_paper_sync_operation_event
              (operation_id, sequence_no, from_state, to_state, actor_type)
            VALUES ('{i['op_a']}', 2, 'application_bound', 'applied', 'system')""")
    return cases


# ═══════════════════════════════════════════════════════════════════════════
# 采集：一次 asyncio.run 取回全部快照（memory 铁律：不给每个测试各自开 async）
# ═══════════════════════════════════════════════════════════════════════════


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


async def _collect() -> dict[str, Any]:
    import sqlalchemy as sa  # noqa: F401  (保持与项目其他 PG 守卫一致的导入形态)
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _HarnessError(
            "V151 是纯 schema 层任务，判据必须落在真实 PostgreSQL 的约束行为上；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。"
            "此处**不 skip**：skip 等于把唯一判据静默抹掉。"
        )
    if not _MIGRATION.exists():
        raise _HarnessError(f"缺少迁移文件: {_MIGRATION}")
    if not _ROLLBACK.exists():
        raise _HarnessError(f"缺少配对回滚脚本: {_ROLLBACK}")

    forward = MigrationRunner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8"))
    backward = MigrationRunner._split_sql_statements(_ROLLBACK.read_text(encoding="utf-8"))

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args={"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {},
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "database": None,
        "server_version": None,
        "statement_count": len(forward),
        "rollback_statement_count": len(backward),
        "apply_errors": [],
        "idempotent_errors": [],
        "world_error": None,
        "negative": {},
        "positive": {},
        "introspection": {},
        "rollback": {},
        "backfill": {},
    }

    async def _tx(statements: list[str]) -> str | None:
        """在独立事务里执行一组语句；返回 None=成功，否则返回错误文本（含 COMMIT 期 deferred 触发）。"""
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                for stmt in statements:
                    await conn.exec_driver_sql(stmt)
        except Exception as exc:  # noqa: BLE001 - 负控制期望异常，需要原文入快照
            return f"{type(exc).__name__}: {exc}"
        return None

    try:
        async with engine.connect() as conn:
            row = (
                await conn.exec_driver_sql("SELECT current_database() AS db, version() AS v")
            ).mappings().one()
            snap["database"] = row["db"]
            snap["server_version"] = row["v"]

        # ── 1. scratch schema + 桩表；search_path 只含 scratch（不含 public）──
        setup_err = await _tx(
            [f'CREATE SCHEMA "{schema}"']
        )
        if setup_err:
            raise _HarnessError(f"scratch schema 创建失败: {setup_err}")
        stub_err = await _tx([s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()])
        if stub_err:
            raise _HarnessError(f"桩表创建失败: {stub_err}")

        # ── 2. 应用真实 V151 ────────────────────────────────────────────
        for idx, stmt in enumerate(forward, 1):
            err = await _tx([stmt])
            if err:
                snap["apply_errors"].append({"index": idx, "statement": stmt[:400], "error": err})
                break

        if not snap["apply_errors"]:
            # ── 3. 幂等重跑 ─────────────────────────────────────────────
            for idx, stmt in enumerate(forward, 1):
                err = await _tx([stmt])
                if err:
                    snap["idempotent_errors"].append({"index": idx, "statement": stmt[:400], "error": err})
                    break

            # ── 4. 回填台账实证（桩表 3 行 wp → 3 行 revision 0 台账）────
            async with engine.begin() as conn:
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                await conn.exec_driver_sql(
                    f"INSERT INTO projects (id) VALUES ('{(seed_p := uuid.uuid4())}')"
                )
                for _ in range(3):
                    await conn.exec_driver_sql(
                        f"INSERT INTO working_paper (id, project_id, file_version) "
                        f"VALUES ('{uuid.uuid4()}', '{seed_p}', 4)"
                    )
            # 重跑迁移的回填段（幂等 append）：既有 3 行 wp 应各得 1 行台账
            for stmt in forward:
                if "INSERT INTO working_paper_content_revision_backfill_ledger" in stmt:
                    await _tx([stmt])
            async with engine.connect() as conn:
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                snap["backfill"] = dict(
                    (
                        await conn.exec_driver_sql(
                            "SELECT count(*) AS ledger_rows,"
                            " count(*) FILTER (WHERE backfilled_content_revision = 0) AS zero_rows,"
                            " count(*) FILTER (WHERE entry_verification_state = 'unverified') AS unverified_rows,"
                            " count(*) FILTER (WHERE content_version_created OR representation_created) AS created_entities"
                            " FROM working_paper_content_revision_backfill_ledger"
                        )
                    ).mappings().one()
                )
                snap["backfill"]["content_versions"] = int(
                    (await conn.exec_driver_sql("SELECT count(*) FROM working_paper_content_version")).scalar_one()
                )
                snap["backfill"]["artifacts"] = int(
                    (await conn.exec_driver_sql("SELECT count(*) FROM working_paper_artifact")).scalar_one()
                )
                snap["backfill"]["wp_revisions"] = [
                    int(r) for r in (
                        await conn.exec_driver_sql("SELECT content_revision FROM working_paper")
                    ).scalars().all()
                ]

            # ── 5. 合法世界（正控制总门）────────────────────────────────
            ids = _new_ids()
            snap["world_error"] = await _tx(_world_sql(ids))

            if snap["world_error"] is None:
                # ── 6. 负控制矩阵 ───────────────────────────────────────
                for cid, why, sql in _negative_cases(ids):
                    err = await _tx([s.strip() for s in sql.split("\n;") if s.strip()])
                    snap["negative"][cid] = {"why": why, "rejected": err is not None, "error": err}

                # ── 7. 正控制矩阵 ───────────────────────────────────────
                for cid, why, sql in _positive_cases(ids):
                    err = await _tx([s.strip() for s in sql.split("\n;") if s.strip()])
                    snap["positive"][cid] = {"why": why, "accepted": err is None, "error": err}

            # ── 8. schema introspection ────────────────────────────────
            async with engine.connect() as conn:
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')

                async def cols(table: str) -> list[str]:
                    return [
                        str(r) for r in (
                            await conn.exec_driver_sql(
                                "SELECT column_name FROM information_schema.columns "
                                f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
                                "ORDER BY column_name"
                            )
                        ).scalars().all()
                    ]

                snap["introspection"]["tables"] = [
                    str(r) for r in (
                        await conn.exec_driver_sql(
                            f"SELECT table_name FROM information_schema.tables "
                            f"WHERE table_schema = '{schema}' ORDER BY table_name"
                        )
                    ).scalars().all()
                ]
                snap["introspection"]["scope_index_columns"] = await cols("working_paper_sync_scope_index")
                snap["introspection"]["operation_columns"] = await cols("working_paper_sync_operation")
                snap["introspection"]["application_columns"] = await cols("working_paper_content_application")
                snap["introspection"]["room_columns"] = await cols("working_paper_oo_room")
                snap["introspection"]["working_paper_columns"] = await cols("working_paper")
                snap["introspection"]["indexes"] = {
                    str(r["indexname"]): str(r["indexdef"])
                    for r in (
                        await conn.exec_driver_sql(
                            f"SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = '{schema}'"
                        )
                    ).mappings().all()
                }
                snap["introspection"]["nullable"] = {
                    f"{r['table_name']}.{r['column_name']}": str(r["is_nullable"])
                    for r in (
                        await conn.exec_driver_sql(
                            "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
                            f"WHERE table_schema = '{schema}' AND table_name IN "
                            "('working_paper_sync_definition_bundle','working_paper_sync_operation',"
                            " 'working_paper_content_application')"
                        )
                    ).mappings().all()
                }
                snap["introspection"]["constraint_triggers"] = [
                    str(r) for r in (
                        await conn.exec_driver_sql(
                            "SELECT t.tgname FROM pg_trigger t "
                            "JOIN pg_class c ON c.oid = t.tgrelid "
                            "JOIN pg_namespace ns ON ns.oid = c.relnamespace "
                            f"WHERE ns.nspname = '{schema}' AND t.tgconstraint <> 0 AND NOT t.tgisinternal"
                        )
                    ).scalars().all()
                ]

            # ── 9. 回滚 → 再前滚 ───────────────────────────────────────
            rb_errors: list[dict[str, Any]] = []
            for idx, stmt in enumerate(backward, 1):
                err = await _tx([stmt])
                if err:
                    rb_errors.append({"index": idx, "statement": stmt[:300], "error": err})
            async with engine.connect() as conn:
                remaining = [
                    str(r) for r in (
                        await conn.exec_driver_sql(
                            f"SELECT table_name FROM information_schema.tables "
                            f"WHERE table_schema = '{schema}' ORDER BY table_name"
                        )
                    ).scalars().all()
                ]
                wp_cols_after = [
                    str(r) for r in (
                        await conn.exec_driver_sql(
                            "SELECT column_name FROM information_schema.columns "
                            f"WHERE table_schema = '{schema}' AND table_name = 'working_paper'"
                        )
                    ).scalars().all()
                ]
            reapply_errors: list[dict[str, Any]] = []
            for idx, stmt in enumerate(forward, 1):
                err = await _tx([stmt])
                if err:
                    reapply_errors.append({"index": idx, "statement": stmt[:300], "error": err})
                    break
            snap["rollback"] = {
                "errors": rb_errors,
                "tables_after_rollback": remaining,
                "working_paper_columns_after_rollback": sorted(wp_cols_after),
                "reapply_errors": reapply_errors,
            }
    finally:
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await engine.dispose()

    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# A. harness 自证（禁 fail-open / 禁写业务表）
# ═══════════════════════════════════════════════════════════════════════════


def test_ran_on_real_postgresql_in_scratch_schema(snap: dict[str, Any]) -> None:
    assert "PostgreSQL" in (snap["server_version"] or ""), f"必须在真实 PostgreSQL 上采集: {snap['server_version']}"
    assert snap["schema"].startswith(_SCHEMA_PREFIX), (
        f"必须在 scratch schema 内建表（禁写业务表），实得 {snap['schema']}"
    )
    # 桩表在 scratch 内，且 search_path 不含 public ⇒ 物理上无法解析到 public.working_paper
    assert "working_paper" in snap["introspection"]["tables"]
    assert "projects" in snap["introspection"]["tables"]


def test_migration_applies_and_is_idempotent(snap: dict[str, Any]) -> None:
    assert snap["apply_errors"] == [], f"V151 应用失败: {snap['apply_errors']}"
    assert snap["idempotent_errors"] == [], f"V151 重复执行不幂等: {snap['idempotent_errors']}"
    assert snap["statement_count"] > 100, f"V151 语句数异常偏少（{snap['statement_count']}），疑似文件被截断"


def test_legal_world_is_accepted(snap: dict[str, Any]) -> None:
    """正控制总门：一整套合法数据（含 deferred 约束触发器）必须能落库。"""
    assert snap["world_error"] is None, f"合法世界被拒绝（约束过严）: {snap['world_error']}"


def test_migration_number_has_no_collision() -> None:
    """迁移号无撞号，且 V151 配了回滚脚本。

    🔴 原来还有一条 `max(versions) == 151`（「V151 必须是当前最高迁移号」）。它是**会
    自动过期**的判据：本 spec 自己往后加一个迁移就必红，而那恰恰是正常推进。
    Task 19 加了 V152（`ck_wpcv_source` 补 `upload` / `wopi`），于是把它换成真正的
    不变量 —— 号不能重复、V151 仍在、且它有配对回滚。

    「V151 的对象后来被谁改过」这条追溯由 `ck_wpcv_source` 那侧的守卫承担：
    `test_task15_content_mutation.py::test_source_vocabulary_matches_the_owning_migration`
    按迁移号取**最后一个**声明该 CHECK 的文件，改哪一版都锁得住。
    """
    import re as _re

    numbers = [
        int(m.group(1))
        for path in (_BACKEND / "migrations").glob("V*.sql")
        if (m := _re.match(r"V(\d+)__", path.name))
    ]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert duplicates == [], f"迁移号撞号: {duplicates}"
    same = [p.name for p in (_BACKEND / "migrations").glob("V151__*.sql")]
    assert same == [_MIGRATION.name], f"V151 撞号: {same}"
    assert 151 in numbers, "V151 不见了"
    assert _ROLLBACK.exists(), "V151 必须配回滚脚本"


# ═══════════════════════════════════════════════════════════════════════════
# B. 逐 Property 的行为判据（负控制必须被真实 PG 拒绝）
# ═══════════════════════════════════════════════════════════════════════════


def _assert_rejected(snap: dict[str, Any], prefix: str, expected_ids: set[str]) -> None:
    cases = {cid: v for cid, v in snap["negative"].items() if cid.startswith(prefix)}
    assert set(cases) == expected_ids, (
        f"{prefix} 负控制用例集漂移：缺 {sorted(expected_ids - set(cases))}，多 {sorted(set(cases) - expected_ids)}"
    )
    passed_through = {cid: v["why"] for cid, v in cases.items() if not v["rejected"]}
    assert not passed_through, f"{prefix} 以下违规数据**未被数据库拒绝**（约束失效）: {passed_through}"


def test_property_4_business_revision_orthogonal_to_representation(snap: dict[str, Any]) -> None:
    """Property 4：业务内容版本与 representation generation 正交。"""
    _assert_rejected(snap, "P4-", {
        "P4-dup-revision",
        "P4-dup-generation",
        "P4-content-version-immutable",
        "P4-representation-immutable",
        "P4-representation-needs-approved-bundle",
        "P4-representation-bundle-digest-mismatch",
        "P4-representation-authority-not-locked",
        "P4-backfill-ledger-non-zero",
        "P4-backfill-ledger-immutable",
        "P4-backfill-ledger-no-delete",
        "P4-backfill-ledger-claims-entities",
    })
    # 正向：同一 content version 的两个 representation generation 已在合法世界里落库
    # （rep_g1 gen1 + rep_g2 gen2 同挂 cv1），且 working_paper.content_revision 保持 0。
    assert snap["backfill"]["wp_revisions"], "回填后应能读到 content_revision"
    assert set(snap["backfill"]["wp_revisions"]) == {0}, (
        f"回填只能落 revision 0，实得 {snap['backfill']['wp_revisions']}"
    )


def test_property_5_no_dangling_visible_state(snap: dict[str, Any]) -> None:
    """Property 5：staged artifact / candidate 与 DB pointer 不产生悬空可见态。"""
    _assert_rejected(snap, "P5-", {
        "P5-incoming-published",
        "P5-candidate-published",
        "P5-incoming-without-delivery",
        "P5-incoming-path-not-sealed",
        "P5-incoming-path-uses-operation",
        "P5-incoming-durable-to-quarantined",
        "P5-incoming-quarantined-to-durable",
        "P5-artifact-sha-immutable",
        "P5-quarantined-with-durable-at",
        "P5-entry-pointer-to-staged-artifact",
        "P5-entry-pointer-generation-mismatch",
        "P5-representation-on-incoming-artifact",
        "P5-representation-on-candidate-artifact",
        "P5-candidate-ready-without-bundle",
        "P5-candidate-finalize-advances-revision",
        "P5-candidate-on-published-artifact",
    })


def test_property_10_single_commit_and_representation_idempotency(snap: dict[str, Any]) -> None:
    """Property 10：pending mutation token / Idempotency-Key / application key 幂等。"""
    _assert_rejected(snap, "P10-", {
        "P10-pending-mutation-dup-key",
        "P10-pending-committed-without-result",
        "P10-pending-uncommitted-with-result",
        "P10-pending-ttl-inverted",
        "P10-duplicate-application-key",
    })


def test_property_11_unique_descriptor_and_ready_confirmation(snap: dict[str, Any]) -> None:
    """Property 11：唯一 descriptor + ready 后服务端确认；陈旧 identity 必须拒绝。"""
    _assert_rejected(snap, "P11-", {
        "P11-duplicate-active-confirmation",
        "P11-confirmation-empty-bundle-digest",
        "P11-confirmation-zero-hash-authority",
        "P11-confirmation-stale-generation",
        "P11-confirmation-bundle-not-locked",
    })


def test_property_18_many_deliveries_one_frozen_application(snap: dict[str, Any]) -> None:
    """Property 18：delivery 可多次、frozen application 恰一次；1 primary + N-1 direct duplicates。"""
    _assert_rejected(snap, "P18-", {
        "P18-two-primaries-same-application",
        "P18-both-application-and-duplicate",
        "P18-duplicate-chain",
        "P18-duplicate-target-unbound",
        "P18-duplicate-cross-entry",
        "P18-duplicate-cross-bundle",
        "P18-duplicate-state-not-terminal",
        "P18-duplicate-rebind-application",
        "P18-primary-unbind-application",
        "P18-duplicate-pointer-deleted",
        "P18-two-open-close-captures",
        "P18-delivery-primary-application-mismatch",
        "P18-delivery-duplicate-primary-mismatch",
        "P18-delivery-double-owner",
        "P18-durable-delivery-zero-owner",
        "P18-unmatched-with-application",
        "P18-durable-state-without-durable-fact",
        "P18-delivery-key-duplicate",
        "P18-durable-at-cleared",
        "P18-post-durable-owner-dropped",
        "P18-recovery-pre-claim-has-operation",
        "P18-recovery-claimed-without-all-entities",
        "P18-recovery-download-only-with-entities",
    })
    # 正向：同一 application 的多 delivery 与第三个 duplicate shell 必须被接受
    assert snap["positive"]["POS-extra-delivery-same-application"]["accepted"], (
        snap["positive"]["POS-extra-delivery-same-application"]["error"]
    )
    assert snap["positive"]["POS-third-duplicate-shell"]["accepted"], (
        snap["positive"]["POS-third-duplicate-shell"]["error"]
    )


def test_property_62_server_last_applied_not_conflated_with_client_base(snap: dict[str, Any]) -> None:
    """Property 62：server last-applied 与 client-confirmed base 是两套独立指针。"""
    _assert_rejected(snap, "P62-", {
        "P62-room-partial-client-confirmed",
        "P62-room-refresh-without-reason",
        "P62-room-durable-sequence-regress",
        "P62-room-write-fence-regress",
        "P62-room-eligibility-epoch-regress",
        "P62-room-durable-exceeds-request",
        "P62-room-identity-mutated",
        "P62-room-unknown-state",
    })
    room_cols = set(snap["introspection"]["room_columns"])
    # 结构判据：两套指针必须是不同列，且不得退化成单一 last_ack
    for col in (
        "last_applied_version_id",
        "client_confirmed_base_version_id",
        "client_confirmed_representation_id",
        "client_confirmed_definition_bundle_id",
        "client_confirmed_definition_bundle_sha256",
        "client_confirmed_projection_sha256",
        "latest_durable_application_id",
        "latest_durable_sequence",
        "latest_request_sequence",
        "write_fence_epoch",
        "close_barrier_epoch",
        "close_leader_intent_id",
        "close_leader_eligibility_epoch",
        "close_leader_eligibility_digest",
        "refresh_required_at",
        "refresh_reason",
    ):
        assert col in room_cols, f"room 缺少 Requirement 2.5 要求的列: {col}"
    assert "last_ack" not in room_cols, "room 不得用单一 last_ack 混同两套指针"
    for forbidden in ("user_id", "mode", "permission_epoch"):
        assert forbidden not in room_cols, f"room 不得保存单一 {forbidden} 代表全房间（Requirement 2.5）"
    # 正向：durable fence 可单调提升
    assert snap["positive"]["POS-room-durable-fence-up"]["accepted"], (
        snap["positive"]["POS-room-durable-fence-up"]["error"]
    )


def test_property_64_application_identity_uses_frozen_bundle_without_status(snap: dict[str, Any]) -> None:
    """Property 64：application identity 只用 frozen bundle；operation 不得复制 application_key。"""
    _assert_rejected(snap, "P64-", {
        "P64-application-origin-sequence-rewritten",
        "P64-application-effective-sequence-regress",
        "P64-application-effective-below-origin",
        "P64-application-key-mutated",
        "P64-application-self-supersede",
        "P64-application-on-quarantined-incoming",
        "P64-application-on-canonical-artifact",
        "P64-application-zero-bundle-digest",
        "P64-application-origin-sequence-mismatch",
        "P64-application-base-not-frozen",
        "P64-request-idempotency-reuse-same-participant",
        "P64-request-duplicate-sequence",
        "P64-request-frozen-field-mutated",
        "P64-request-fingerprint-empty",
        "P64-request-bundle-drift",
        "P64-operation-bundle-drift-from-request",
        "P64-operation-application-cross-bundle",
        "P64-operation-bound-without-timestamp",
        "P64-two-shells-one-request",
    })
    op_cols = set(snap["introspection"]["operation_columns"])
    app_cols = set(snap["introspection"]["application_columns"])
    # 🔴 application_key 只能存在 application；operation 出现同名列即失败
    assert "application_key" in app_cols, "application_key 必须由 working_paper_content_application 持有"
    assert "application_key" not in op_cols, (
        "working_paper_sync_operation 不得保存 application_key（Property 64 / Requirement 5.5）"
    )
    for forbidden in ("incoming_sha256", "incoming_artifact_id", "callback_status"):
        assert forbidden not in op_cols, f"operation 不得复制 incoming identity/status 作为幂等真源: {forbidden}"
    # application 的 key 不含 callback status
    assert "callback_status" not in app_cols, "application identity 明确不含 callback status"
    for col in ("origin_request_sequence", "effective_request_sequence", "origin_request_id"):
        assert col in app_cols, f"application 缺少 Requirement 5.5 要求的列: {col}"
    # operation 的 application_id 必须 nullable UNIQUE
    nullable = snap["introspection"]["nullable"]
    assert nullable.get("working_paper_sync_operation.application_id") == "YES", (
        "operation.application_id 必须 nullable（normal accepted shell 的 pre-correlation 合法态）"
    )
    assert nullable.get("working_paper_sync_operation.duplicate_of_operation_id") == "YES", (
        "operation.duplicate_of_operation_id 必须 nullable"
    )
    indexes = snap["introspection"]["indexes"]
    assert any(
        "working_paper_sync_operation" in d and "application_id" in d and "UNIQUE" in d
        for d in indexes.values()
    ), f"operation.application_id 必须 UNIQUE（一个 application 只能一个 primary）: {sorted(indexes)}"
    # 正向：effective sequence 可 fold 提升
    assert snap["positive"]["POS-fold-effective-sequence-up"]["accepted"], (
        snap["positive"]["POS-fold-effective-sequence-up"]["error"]
    )


def test_property_68_timeline_complete_and_append_only(snap: dict[str, Any]) -> None:
    """Property 68：operation/application/close-intent/recovery 四条 timeline 完整、单调、append-only。"""
    _assert_rejected(snap, "P68-", {
        "P68-operation-event-dup-sequence",
        "P68-operation-event-update",
        "P68-operation-event-delete",
        "P68-two-application-bound-events",
        "P68-two-duplicate-events",
        "P68-application-event-update",
        "P68-application-event-delete",
        "P68-fold-event-without-request",
        "P68-fold-event-without-room-fence",
        "P68-fold-same-request-twice",
        "P68-fold-event-effective-below-origin",
        "P68-recovery-event-update",
        "P68-recovery-event-delete",
        "P68-recovery-event-dup-sequence",
        "P68-close-intent-event-update",
        "P68-close-intent-event-delete",
        "P68-close-intent-event-dup-sequence",
        "P68-close-intent-promoted-without-request",
        "P68-close-intent-promoted-to-forcesave",
        "P68-close-intent-dup-sequence",
    })
    tables = set(snap["introspection"]["tables"])
    # 四条 timeline 必须各自独立存在（recovery 与 operation timeline 分离是 13.5 的硬要求）
    for t in (
        "working_paper_sync_operation_event",
        "working_paper_content_application_event",
        "working_paper_oo_close_intent_event",
        "working_paper_callback_recovery_case_event",
    ):
        assert t in tables, f"缺少 append-only timeline 表: {t}"
    # 正向：可继续 append 递增 event
    assert snap["positive"]["POS-append-next-event"]["accepted"], (
        snap["positive"]["POS-append-next-event"]["error"]
    )


def test_property_69_evidence_closed_by_per_scenario_entities(snap: dict[str, Any]) -> None:
    """Property 69：evidence 由逐 scenario 实体闭合；download-only 零 operation/application。"""
    _assert_rejected(snap, "P69-", {
        "P69-scenario-dup-ordinal",
        "P69-download-only-with-operation",
        "P69-download-only-without-recovery-case",
        "P69-standard-passed-without-entities",
        "P69-scenario-bundle-cross-run",
        "P69-scenario-immutable",
        "P69-test-run-profile-mutated",
        "P69-test-run-result-without-finish",
        "P69-test-run-free-text-room-model",
    })
    tables = set(snap["introspection"]["tables"])
    assert "working_paper_sync_test_run" in tables
    assert "working_paper_entry_evidence_scenario" in tables


# ═══════════════════════════════════════════════════════════════════════════
# C. bundle typed slots / scope index / 冲突 / lease 的横向判据
# ═══════════════════════════════════════════════════════════════════════════


def test_definition_bundle_typed_slots_are_locked(snap: dict[str, Any]) -> None:
    """Requirement 2.3 / 3.3：四 slot 全 NOT NULL；child kind/state/digest 与 marker registry 锁死。"""
    _assert_rejected(snap, "BUNDLE-", {
        "BUNDLE-null-slot-ref",
        "BUNDLE-empty-slot-digest",
        "BUNDLE-zero-slot-digest",
        "BUNDLE-slot-child-not-approved",
        "BUNDLE-slot-child-wrong-kind",
        "BUNDLE-slot-digest-mismatch",
        "BUNDLE-projection-contract-with-marker",
        "BUNDLE-unregistered-marker",
        "BUNDLE-marker-digest-forged",
        "BUNDLE-marker-wrong-slot",
        "BUNDLE-authority-child-not-approved",
        "BUNDLE-authority-wrong-kind",
        "BUNDLE-approved-mutated",
        "BUNDLE-marker-registry-mutated",
        "BUNDLE-unversioned-marker-registered",
        "BUNDLE-authority-model-type-on-template",
        "BUNDLE-authority-model-unknown-enum",
        "BUNDLE-authority-model-missing-on-authority",
        "BUNDLE-zero-hash-standalone",
        "BUNDLE-empty-hash-standalone",
    })
    nullable = snap["introspection"]["nullable"]
    for col in (
        "authority_model_definition_id", "authority_model_definition_sha256",
        "template_slot_type", "template_slot_ref", "template_slot_digest",
        "instrumentation_slot_type", "instrumentation_slot_ref", "instrumentation_slot_digest",
        "contract_slot_type", "contract_slot_ref", "contract_slot_digest",
        "canonical_payload_artifact_id", "canonical_payload_sha256",
    ):
        key = f"working_paper_sync_definition_bundle.{col}"
        assert nullable.get(key) == "NO", f"bundle 的 {col} 必须 NOT NULL（slot omission 必须在 DB 层被拒）"
    # 正向：custom_authoritative_ooxml 可用 registry typed null marker
    assert snap["positive"]["POS-custom-bundle-with-markers"]["accepted"], (
        snap["positive"]["POS-custom-bundle-with-markers"]["error"]
    )


def test_scope_index_is_authorization_only_and_tombstoned(snap: dict[str, Any]) -> None:
    """design §scope index：只存非敏感归属；禁 payload/状态/hash；tombstone 永不删除/清空/复用。"""
    _assert_rejected(snap, "SCOPE-", {
        "SCOPE-physical-delete",
        "SCOPE-tombstone-cleared",
        "SCOPE-cross-scope-rebind",
        "SCOPE-numeric-revision-as-resource-id",
        "SCOPE-numeric-resource-id-non-version",
        "SCOPE-content-version-non-uuid",
        "SCOPE-resource-id-reuse",
        "SCOPE-unknown-resource-kind",
    })
    cols = set(snap["introspection"]["scope_index_columns"])
    assert cols == {
        "resource_kind", "resource_id", "project_id", "wp_id", "entry_id",
        "room_id", "generation", "created_at", "retired_at",
    }, f"scope index 列集漂移（禁止携带 payload/业务状态/hash/错误/候选摘要/authorization result）: {sorted(cols)}"
    forbidden_fragments = ("payload", "sha", "digest", "hash", "error", "candidate",
                           "authorization", "token", "secret", "value", "status")
    leaked = [c for c in cols for f in forbidden_fragments if f in c]
    assert not leaked, f"scope index 出现敏感/业务语义列: {leaked}"
    # 正向：可 retire
    assert snap["positive"]["POS-scope-retire"]["accepted"], snap["positive"]["POS-scope-retire"]["error"]
    # 正向：跨 wp 相同 numeric revision 由不同 opaque UUID 无碰撞
    assert snap["positive"]["POS-cross-wp-same-revision"]["accepted"], (
        snap["positive"]["POS-cross-wp-same-revision"]["error"]
    )


def test_conflict_and_participant_lease_constraints(snap: dict[str, Any]) -> None:
    """Requirement 8.1（冲突字段完备）与 2.6（per-user lease + closing 中间态）。"""
    _assert_rejected(snap, "R81-", {
        "R81-conflict-duplicate-field",
        "R81-conflict-empty-stable-key",
        "R81-conflict-bad-json-pointer",
        "R81-conflict-unknown-kind",
    })
    _assert_rejected(snap, "R26-", {
        "R26-duplicate-active-lease",
        "R26-unknown-participant-state",
        "R26-revoked-without-timestamp",
    })


def test_backfill_touches_no_business_values(snap: dict[str, Any]) -> None:
    """回填只写台账 + revision 0；不创建 content version/artifact、不改业务值。"""
    b = snap["backfill"]
    assert b["ledger_rows"] == b["zero_rows"] == 3, f"回填台账应逐 wp 一行且全为 revision 0: {b}"
    assert b["unverified_rows"] == 3, f"无合法 approved bundle 的 entry 必须保持 unverified: {b}"
    assert b["created_entities"] == 0, "回填不得声称创建 content version/representation"
    assert b["content_versions"] == 0, f"回填不得创建 content version，实得 {b['content_versions']} 行"
    assert b["artifacts"] == 0, f"回填不得创建/复制 artifact，实得 {b['artifacts']} 行"


def test_rollback_and_reapply(snap: dict[str, Any]) -> None:
    """R151 可回滚（含 working_paper 增量列），V151 可再前滚。"""
    rb = snap["rollback"]
    assert rb["errors"] == [], f"R151 回滚失败: {rb['errors']}"
    leftovers = [t for t in rb["tables_after_rollback"] if t.startswith("working_paper_")]
    assert leftovers == [], f"R151 未清尽 V151 建的表: {leftovers}"
    assert "content_revision" not in rb["working_paper_columns_after_rollback"]
    assert "current_content_version_id" not in rb["working_paper_columns_after_rollback"]
    assert rb["reapply_errors"] == [], f"回滚后再前滚失败: {rb['reapply_errors']}"


def test_deferred_constraint_triggers_exist(snap: dict[str, Any]) -> None:
    """跨行不变式必须由 DEFERRABLE 约束触发器在 COMMIT 时校验（不是应用层 best-effort）。"""
    triggers = set(snap["introspection"]["constraint_triggers"])
    for t in (
        "trg_wpso_duplicate_link",
        "trg_wpso_application_link",
        "trg_wpcd_operation_link",
    ):
        assert t in triggers, f"缺少 deferred 约束触发器: {t}（实得 {sorted(triggers)}）"
