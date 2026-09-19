-- R128: 回滚 V128 — 函证证据链表结构
-- spec: confirmation-attachment-ocr-linkage
-- 幂等：DROP IF EXISTS / 列存在才删除。
-- 注意：回滚会丢失 confirmation_attachment_link 和 confirmation_action_log 数据。

-- 1. 删除触发器（先于表，避免函数依赖）
DROP TRIGGER IF EXISTS trg_conf_action_log_forbid_update ON confirmation_action_log;
DROP TRIGGER IF EXISTS trg_conf_action_log_forbid_delete ON confirmation_action_log;

-- 2. 删除新表
DROP TABLE IF EXISTS confirmation_action_log;
DROP TABLE IF EXISTS confirmation_attachment_link;

-- 3. 删除 confirmations 新增列
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'confirmations' AND column_name = 'sent_date') THEN
    ALTER TABLE confirmations DROP COLUMN sent_date;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'confirmations' AND column_name = 'reply_date') THEN
    ALTER TABLE confirmations DROP COLUMN reply_date;
  END IF;
END $$;

-- 注：evgov_forbid_update / evgov_forbid_delete 函数不删除（V108/V111 共享，其它表仍依赖）。
