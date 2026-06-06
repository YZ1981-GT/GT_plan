-- V058: 函证管理表（能力域 D — global-refinement-v5-closure）
CREATE TABLE IF NOT EXISTS confirmations (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID         NOT NULL REFERENCES projects(id),
    confirm_type      VARCHAR(20)  NOT NULL,            -- receivable / payable / bank / loan
    counterparty      VARCHAR(255) NOT NULL,            -- 函证对象名称
    status            VARCHAR(20)  NOT NULL DEFAULT 'pending',  -- pending/sent/returned/matched/discrepancy
    wp_id             UUID         REFERENCES working_paper(id),
    account_code      VARCHAR(50),
    book_amount       NUMERIC(20,2),
    confirmed_amount  NUMERIC(20,2),
    diff_amount       NUMERIC(20,2),
    diff_note         TEXT,
    created_by        UUID         REFERENCES users(id),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_confirmations_project ON confirmations (project_id);
CREATE INDEX IF NOT EXISTS idx_confirmations_status  ON confirmations (status);
