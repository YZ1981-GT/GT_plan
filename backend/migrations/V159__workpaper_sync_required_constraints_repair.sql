-- ═══════════════════════════════════════════════════════════════════════════
-- V159：修复 create_all-first 引导路径跳过 V151/V152 内联约束的问题
--
-- `backend/scripts/seed/init_tables.py` 会先按 ORM 创建最新表形状。V151 随后使用
-- `CREATE TABLE IF NOT EXISTS`，因此由 V151 建表语句拥有的 CHECK / UNIQUE 不会落地。
-- 本迁移不修改 V151/V152 历史字节、不删除表、不回填业务数据；仅按“目标表 + 约束名”
-- 幂等补齐 program milestone 只读数据库探针要求的 23 项 canonical 约束。
--
-- CHECK / UNIQUE 定义逐字取自 V151；`ck_wpcv_source` 使用 V152 的最终七值词表。
-- 健康业务库中约束均已存在，所有分支 no-op；缺失库若存在冲突数据则 ADD CONSTRAINT
-- 必须失败，禁止 NOT VALID、豁免或静默降级。
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    -- working_paper_content_application (3)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_content_application'::regclass
          AND conname = 'working_paper_content_application_application_key_key'
    ) THEN
        ALTER TABLE public.working_paper_content_application
            ADD CONSTRAINT working_paper_content_application_application_key_key
            UNIQUE (application_key);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_content_application'::regclass
          AND conname = 'ck_wpca_state'
    ) THEN
        ALTER TABLE public.working_paper_content_application
            ADD CONSTRAINT ck_wpca_state CHECK (state IN (
                'queued', 'validating', 'extracting', 'merging', 'conflict', 'rematerializing',
                'applying', 'applied', 'refresh_required', 'error', 'superseded',
                'authorization_stale'
            ));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_content_application'::regclass
          AND conname = 'ck_wpca_applied_requires_result'
    ) THEN
        ALTER TABLE public.working_paper_content_application
            ADD CONSTRAINT ck_wpca_applied_requires_result CHECK (
                state <> 'applied'
                OR (result_revision IS NOT NULL
                    AND result_representation_id IS NOT NULL
                    AND merged_projection_sha256 IS NOT NULL
                    AND logical_result_code IS NOT NULL)
            );
    END IF;

    -- working_paper_sync_operation (4)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_sync_operation'::regclass
          AND conname = 'uq_wpso_application'
    ) THEN
        ALTER TABLE public.working_paper_sync_operation
            ADD CONSTRAINT uq_wpso_application UNIQUE (application_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_sync_operation'::regclass
          AND conname = 'uq_wpso_request'
    ) THEN
        ALTER TABLE public.working_paper_sync_operation
            ADD CONSTRAINT uq_wpso_request UNIQUE (forcesave_request_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_sync_operation'::regclass
          AND conname = 'ck_wpso_bound_requires_application'
    ) THEN
        ALTER TABLE public.working_paper_sync_operation
            ADD CONSTRAINT ck_wpso_bound_requires_application CHECK (
                state <> 'application_bound' OR application_id IS NOT NULL
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_sync_operation'::regclass
          AND conname = 'ck_wpso_not_both_owners'
    ) THEN
        ALTER TABLE public.working_paper_sync_operation
            ADD CONSTRAINT ck_wpso_not_both_owners CHECK (
                application_id IS NULL OR duplicate_of_operation_id IS NULL
            );
    END IF;

    -- working_paper_content_version (3)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_content_version'::regclass
          AND conname = 'uq_wpcv_wp_revision'
    ) THEN
        ALTER TABLE public.working_paper_content_version
            ADD CONSTRAINT uq_wpcv_wp_revision UNIQUE (wp_id, revision);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_content_version'::regclass
          AND conname = 'fk_wpcv_operation'
    ) THEN
        ALTER TABLE public.working_paper_content_version
            ADD CONSTRAINT fk_wpcv_operation
            FOREIGN KEY (operation_id)
            REFERENCES public.working_paper_sync_operation(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_content_version'::regclass
          AND conname = 'ck_wpcv_source'
    ) THEN
        ALTER TABLE public.working_paper_content_version
            ADD CONSTRAINT ck_wpcv_source CHECK (source IN (
                'html', 'onlyoffice', 'conflict_resolution', 'rollback', 'custom', 'upload', 'wopi'
            ));
    END IF;

    -- working_paper_callback_delivery (3)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_callback_delivery'::regclass
          AND conname = 'ck_wpcd_durable_exactly_one_owner'
    ) THEN
        ALTER TABLE public.working_paper_callback_delivery
            ADD CONSTRAINT ck_wpcd_durable_exactly_one_owner CHECK (
                durable_at IS NULL
                OR ((application_id IS NOT NULL) <> (callback_recovery_case_id IS NOT NULL))
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_callback_delivery'::regclass
          AND conname = 'ck_wpcd_durable_requires_incoming'
    ) THEN
        ALTER TABLE public.working_paper_callback_delivery
            ADD CONSTRAINT ck_wpcd_durable_requires_incoming CHECK (
                durable_at IS NULL OR incoming_artifact_id IS NOT NULL
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_callback_delivery'::regclass
          AND conname = 'ck_wpcd_durable_state_requires_fact'
    ) THEN
        ALTER TABLE public.working_paper_callback_delivery
            ADD CONSTRAINT ck_wpcd_durable_state_requires_fact CHECK (
                state NOT IN ('durable', 'acknowledged', 'unmatched') OR durable_at IS NOT NULL
            );
    END IF;

    -- working_paper_oo_room (4)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_oo_room'::regclass
          AND conname = 'uq_wpoor_doc_key'
    ) THEN
        ALTER TABLE public.working_paper_oo_room
            ADD CONSTRAINT uq_wpoor_doc_key UNIQUE (doc_key);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_oo_room'::regclass
          AND conname = 'uq_wpoor_generation'
    ) THEN
        ALTER TABLE public.working_paper_oo_room
            ADD CONSTRAINT uq_wpoor_generation UNIQUE (wp_id, entry_id, generation);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_oo_room'::regclass
          AND conname = 'fk_wpoor_latest_durable_application'
    ) THEN
        ALTER TABLE public.working_paper_oo_room
            ADD CONSTRAINT fk_wpoor_latest_durable_application
            FOREIGN KEY (latest_durable_application_id)
            REFERENCES public.working_paper_content_application(id) ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_oo_room'::regclass
          AND conname = 'ck_wpoor_durable_fence_pair'
    ) THEN
        ALTER TABLE public.working_paper_oo_room
            ADD CONSTRAINT ck_wpoor_durable_fence_pair CHECK (
                (latest_durable_application_id IS NULL AND latest_durable_sequence = 0)
                OR latest_durable_application_id IS NOT NULL
            );
    END IF;

    -- working_paper_forcesave_request (3)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_forcesave_request'::regclass
          AND conname = 'uq_wpfr_idempotency'
    ) THEN
        ALTER TABLE public.working_paper_forcesave_request
            ADD CONSTRAINT uq_wpfr_idempotency UNIQUE (
                room_id, generation, initiated_by_participant_id, kind, idempotency_key
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_forcesave_request'::regclass
          AND conname = 'uq_wpfr_sequence'
    ) THEN
        ALTER TABLE public.working_paper_forcesave_request
            ADD CONSTRAINT uq_wpfr_sequence UNIQUE (room_id, generation, request_sequence);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_forcesave_request'::regclass
          AND conname = 'ck_wpfr_state'
    ) THEN
        ALTER TABLE public.working_paper_forcesave_request
            ADD CONSTRAINT ck_wpfr_state CHECK (state IN (
                'frozen', 'pending', 'accepted', 'correlated', 'terminal',
                'rejected', 'unmatched', 'superseded', 'authorization_stale'
            ));
    END IF;

    -- working_paper_oo_close_intent (3)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_oo_close_intent'::regclass
          AND conname = 'uq_wpoci_sequence'
    ) THEN
        ALTER TABLE public.working_paper_oo_close_intent
            ADD CONSTRAINT uq_wpoci_sequence UNIQUE (room_id, generation, intent_sequence);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_oo_close_intent'::regclass
          AND conname = 'ck_wpoci_promoted_pair'
    ) THEN
        ALTER TABLE public.working_paper_oo_close_intent
            ADD CONSTRAINT ck_wpoci_promoted_pair CHECK (
                (state = 'promoted') = (promoted_request_id IS NOT NULL)
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.working_paper_oo_close_intent'::regclass
          AND conname = 'ck_wpoci_state'
    ) THEN
        ALTER TABLE public.working_paper_oo_close_intent
            ADD CONSTRAINT ck_wpoci_state CHECK (state IN (
                'created', 'ordinary_forcesaving', 'waiting_barrier', 'leader_ready', 'promoted',
                'retryable_blocked', 'authorization_stale', 'successor_selected',
                'recovery_required', 'superseded', 'error'
            ));
    END IF;
END $$;
