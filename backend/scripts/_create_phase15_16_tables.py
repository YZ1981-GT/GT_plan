"""一次性脚本：在本地PG中创建 Phase 14/15/16 缺失的表

包括：
- trace_events (Phase 14)
- gate_decisions (Phase 14)
- gate_rule_configs (Phase 14)
- task_tree_nodes (Phase 15)
- task_events (Phase 15)
- issue_tickets (Phase 15)
- review_conversation_participants (Phase 15)
- review_conversation_exports (Phase 15)
- version_line_stamps (Phase 16)
- evidence_hash_checks (Phase 16)
- offline_conflicts (Phase 16)

以及 review_conversations / review_messages 的增强字段。

用法: python backend/scripts/_create_phase15_16_tables.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/audit_platform")
# 转换 asyncpg URL 为 psycopg2 格式
db_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

DDL_STATEMENTS = [
    # ═══ Phase 14: trace_events ═══
    """
    CREATE TABLE IF NOT EXISTS trace_events (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        object_type VARCHAR(32) NOT NULL,
        object_id UUID NOT NULL,
        actor_id UUID NOT NULL,
        actor_role VARCHAR(32) NULL,
        action VARCHAR(128) NOT NULL,
        decision VARCHAR(16) NULL,
        reason_code VARCHAR(64) NULL,
        from_status VARCHAR(32) NULL,
        to_status VARCHAR(32) NULL,
        before_snapshot JSONB NULL,
        after_snapshot JSONB NULL,
        content_hash VARCHAR(64) NULL,
        version_no INTEGER NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trace_events_project_type ON trace_events(project_id, event_type, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_trace_events_trace_id ON trace_events(trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_trace_events_object ON trace_events(object_type, object_id)",
    "CREATE INDEX IF NOT EXISTS idx_trace_events_actor ON trace_events(actor_id, created_at DESC)",

    # ═══ Phase 14: gate_decisions ═══
    """
    CREATE TABLE IF NOT EXISTS gate_decisions (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        gate_type VARCHAR(32) NOT NULL,
        wp_id UUID NULL,
        actor_id UUID NOT NULL,
        decision VARCHAR(16) NOT NULL,
        hit_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
        context JSONB NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gate_decisions_project ON gate_decisions(project_id, gate_type, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_gate_decisions_trace ON gate_decisions(trace_id)",

    # ═══ Phase 14: gate_rule_configs ═══
    """
    CREATE TABLE IF NOT EXISTS gate_rule_configs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        rule_code VARCHAR(32) NOT NULL,
        config_level VARCHAR(16) NOT NULL DEFAULT 'platform',
        threshold_key VARCHAR(64) NULL,
        threshold_value VARCHAR(128) NULL,
        tenant_id UUID NULL,
        updated_by UUID NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_gate_rule_configs_unique ON gate_rule_configs(rule_code, config_level, COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid))",

    # ═══ Phase 15: task_tree_nodes ═══
    """
    CREATE TABLE IF NOT EXISTS task_tree_nodes (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        node_level VARCHAR(16) NOT NULL,
        parent_id UUID NULL,
        ref_id UUID NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'pending',
        assignee_id UUID NULL,
        due_at TIMESTAMP NULL,
        meta JSONB NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_task_tree_project_level ON task_tree_nodes(project_id, node_level, status)",
    "CREATE INDEX IF NOT EXISTS idx_task_tree_parent ON task_tree_nodes(parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_tree_assignee ON task_tree_nodes(assignee_id, status)",

    # ═══ Phase 15: task_events ═══
    """
    CREATE TABLE IF NOT EXISTS task_events (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        task_node_id UUID NULL,
        payload JSONB NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        retry_count INT NOT NULL DEFAULT 0,
        max_retries INT NOT NULL DEFAULT 3,
        next_retry_at TIMESTAMP NULL,
        error_message TEXT NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_task_events_project_status ON task_events(project_id, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_task_events_trace ON task_events(trace_id)",

    # ═══ Phase 15: issue_tickets ═══
    """
    CREATE TABLE IF NOT EXISTS issue_tickets (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        wp_id UUID NULL,
        task_node_id UUID NULL,
        conversation_id UUID NULL,
        source VARCHAR(16) NOT NULL,
        severity VARCHAR(16) NOT NULL,
        category VARCHAR(64) NOT NULL,
        title VARCHAR(200) NOT NULL,
        description TEXT NULL,
        owner_id UUID NOT NULL,
        due_at TIMESTAMP NULL,
        entity_id UUID NULL,
        account_code VARCHAR(20) NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'open',
        thread_id UUID NULL,
        evidence_refs JSONB DEFAULT '[]'::jsonb,
        reason_code VARCHAR(64) NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        closed_at TIMESTAMP NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_issue_tickets_project_status ON issue_tickets(project_id, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_issue_tickets_owner ON issue_tickets(owner_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_issue_tickets_source ON issue_tickets(source, severity)",
    "CREATE INDEX IF NOT EXISTS idx_issue_tickets_conversation ON issue_tickets(conversation_id)",

    # ═══ Phase 15: review_conversation_participants ═══
    """
    CREATE TABLE IF NOT EXISTS review_conversation_participants (
        id UUID PRIMARY KEY,
        conversation_id UUID NOT NULL,
        user_id UUID NOT NULL,
        participant_role VARCHAR(32) NOT NULL DEFAULT 'viewer',
        is_required_ack BOOLEAN NOT NULL DEFAULT false,
        joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
        left_at TIMESTAMP NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rc_participants_conv ON review_conversation_participants(conversation_id, is_deleted)",
    "CREATE INDEX IF NOT EXISTS idx_rc_participants_user ON review_conversation_participants(user_id, is_deleted)",

    # ═══ Phase 15: review_conversation_exports ═══
    """
    CREATE TABLE IF NOT EXISTS review_conversation_exports (
        id UUID PRIMARY KEY,
        export_id VARCHAR(64) NOT NULL UNIQUE,
        conversation_id UUID NOT NULL,
        project_id UUID NOT NULL,
        requested_by UUID NOT NULL,
        export_scope VARCHAR(32) NOT NULL DEFAULT 'full_timeline',
        purpose TEXT NOT NULL,
        receiver VARCHAR(200) NOT NULL,
        mask_policy VARCHAR(32) NOT NULL DEFAULT 'none',
        include_hash_manifest BOOLEAN NOT NULL DEFAULT false,
        file_hash VARCHAR(64) NULL,
        trace_id VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'ready',
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rc_exports_conv ON review_conversation_exports(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_rc_exports_project ON review_conversation_exports(project_id, created_at DESC)",

    # ═══ Phase 16: version_line_stamps ═══
    """
    CREATE TABLE IF NOT EXISTS version_line_stamps (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        object_type VARCHAR(32) NOT NULL,
        object_id UUID NOT NULL,
        version_no INTEGER NOT NULL,
        source_snapshot_id VARCHAR(64) NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_version_line_project ON version_line_stamps(project_id, object_type, object_id, version_no)",
    "CREATE INDEX IF NOT EXISTS idx_version_line_trace ON version_line_stamps(trace_id)",

    # ═══ Phase 16: evidence_hash_checks ═══
    """
    CREATE TABLE IF NOT EXISTS evidence_hash_checks (
        id UUID PRIMARY KEY,
        export_id VARCHAR(64) NOT NULL,
        file_path TEXT NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        signature_digest VARCHAR(128) NULL,
        check_status VARCHAR(16) NOT NULL DEFAULT 'passed',
        checked_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidence_hash_export ON evidence_hash_checks(export_id)",

    # ═══ Phase 16: offline_conflicts ═══
    """
    CREATE TABLE IF NOT EXISTS offline_conflicts (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        wp_id UUID NOT NULL,
        procedure_id UUID NULL,
        field_name VARCHAR(64) NOT NULL,
        local_value JSONB NULL,
        remote_value JSONB NULL,
        merged_value JSONB NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'open',
        resolver_id UUID NULL,
        reason_code VARCHAR(64) NULL,
        qc_replay_job_id UUID NULL,
        trace_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMP NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_offline_conflicts_project ON offline_conflicts(project_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_offline_conflicts_wp ON offline_conflicts(wp_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_offline_conflicts_trace ON offline_conflicts(trace_id)",

    # ═══ Phase 15: RC 增强字段（ALTER TABLE） ═══
    "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS priority VARCHAR(16) DEFAULT 'medium'",
    "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS sla_due_at TIMESTAMP NULL",
    "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP NULL",
    "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolved_by UUID NULL",
    "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS resolution_code VARCHAR(64) NULL",
    "ALTER TABLE review_conversations ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL",
    "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reply_to UUID NULL",
    "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS mentions JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP NULL",
    "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS redaction_flag BOOLEAN DEFAULT false",
    "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS message_version INTEGER DEFAULT 1",
    "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64) NULL",
    "ALTER TABLE review_messages ADD COLUMN IF NOT EXISTS reason_code VARCHAR(64) NULL",
]


def main():
    print(f"连接数据库: {db_url.split('@')[1] if '@' in db_url else db_url}")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    success = 0
    skipped = 0
    errors = 0

    for i, stmt in enumerate(DDL_STATEMENTS):
        stmt_clean = " ".join(stmt.split())[:80]
        try:
            cur.execute(stmt)
            # 判断是否是 CREATE TABLE
            if "CREATE TABLE" in stmt.upper():
                print(f"  ✅ [{i+1}/{len(DDL_STATEMENTS)}] {stmt_clean}...")
            else:
                pass  # 索引和 ALTER 静默
            success += 1
        except Exception as e:
            err_msg = str(e).strip()
            if "already exists" in err_msg.lower():
                skipped += 1
            else:
                print(f"  ❌ [{i+1}] {stmt_clean}... → {err_msg}")
                errors += 1

    cur.close()
    conn.close()

    print(f"\n完成: {success} 成功, {skipped} 跳过, {errors} 错误")
    print("Phase 14/15/16 全部表已就绪。")


if __name__ == "__main__":
    main()
