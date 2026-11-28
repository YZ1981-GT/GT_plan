-- V274: 旧式 doc key / callback 的 drain ledger（spec onlyoffice-sheet-open-via-published-artifact 任务 4.2）
--
-- 为什么需要这张表：
--
-- 任务 4.4 要求「删除旧 direct-write 分支前，守卫要求旧签发数、callback in-flight、
-- drain timeout 连续为 0」。那三个计数必须来自可追溯的记录，否则「连续为 0」
-- 只是「没人查过」的同义词 —— 空分母恒真，是本仓明令禁止的形态。
--
-- 本表是唯一的旧式签发事实来源。gate（_wp_onlyoffice_legacy_url_gate.py）只判
-- 「能不能签」，不记「签了什么」；两者分工，避免 gate 承担写入副作用（它被单测
-- 直接调用，写库会让纯判定变成有状态操作）。
--
-- 为什么是 append-only 而不在原行上改终态：
--
-- 「已签发 -> 已结算」是状态跃迁，但审计要能回答「这一条何时被谁以什么理由结算」。
-- 原地覆盖会让「先 draining 后过期」与「直接过期」变得不可区分。故一行签发 = 一行，
-- 结算写另一行（event_kind = settled），由 issuance_id 关联。
--
-- doc_key 存哈希不存明文：doc_key 是 OO 房间身份，明文落库等于把可伪造的会话
-- 标识写进审计表；查「某个 doc_key 有没有签发记录」用等值哈希查询即可。
CREATE TABLE IF NOT EXISTS working_paper_legacy_drain_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- issued = 旧式 doc key / callback URL 已签发；settled = 该签发已终结
    event_kind VARCHAR(20) NOT NULL,
    -- issued 行恒 NULL；settled 行指向被结算的 issued 行
    issuance_id UUID REFERENCES working_paper_legacy_drain_ledger(id) ON DELETE RESTRICT,
    -- 签发时的 binding 快照（迁移后可回溯当时按哪条 binding 签的）
    binding_id VARCHAR(200),
    binding_status VARCHAR(40),
    entry_id VARCHAR(300) NOT NULL,
    source_wp_code VARCHAR(80),
    sheet_name VARCHAR(300),
    whole_workbook BOOLEAN NOT NULL DEFAULT FALSE,
    wp_id UUID NOT NULL,
    project_id UUID NOT NULL,
    -- doc_key 的 sha256（不存明文，见上方说明）
    doc_key_sha256 CHAR(64),
    -- room 代际。旧式链路可能没有 room，故可空
    generation BIGINT,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- TTL 到期时刻。drain 的「已签发者还能存」边界就是它
    expires_at TIMESTAMPTZ,
    -- settled 行的终结状态；issued 行为 NULL
    terminal_state VARCHAR(30),
    terminal_reason TEXT,
    settled_at TIMESTAMPTZ,
    -- 结算时 callback 是否仍在途（任务 4.4 的 in-flight 计数来源）
    callback_in_flight BOOLEAN,
    CONSTRAINT ck_wpldl_event_kind CHECK (event_kind IN ('issued', 'settled')),
    CONSTRAINT ck_wpldl_terminal_state CHECK (
        terminal_state IS NULL
        OR terminal_state IN ('saved', 'rejected', 'expired', 'superseded', 'abandoned')
    ),
    -- 签发行不得带终结字段；结算行必须带 issuance_id 与终态
    CONSTRAINT ck_wpldl_issued_shape CHECK (
        (event_kind = 'issued')
        = (issuance_id IS NULL AND terminal_state IS NULL AND settled_at IS NULL)
    ),
    CONSTRAINT ck_wpldl_settled_shape CHECK (
        event_kind <> 'settled'
        OR (issuance_id IS NOT NULL AND terminal_state IS NOT NULL AND settled_at IS NOT NULL)
    ),
    -- TTL 必须晚于签发时刻（相等无意义：签发即过期）
    CONSTRAINT ck_wpldl_ttl_order CHECK (expires_at IS NULL OR expires_at > issued_at),
    -- 结算原因必填非空白（空白串与 NULL 在 IS NOT NULL 下同义，会让
    -- 「结算了但没写理由」蒙混过关）
    CONSTRAINT ck_wpldl_terminal_reason CHECK (
        terminal_state IS NULL OR (terminal_reason IS NOT NULL AND length(btrim(terminal_reason)) > 0)
    )
);

-- 查「某 entry 还有多少未结算的旧签发」= drain 的核心查询（4.4 的旧签发数）
CREATE INDEX IF NOT EXISTS ix_wpldl_open_by_entry
    ON working_paper_legacy_drain_ledger (entry_id, event_kind)
    WHERE event_kind = 'issued';

-- 查「已过期但还没结算」= drain timeout 计数来源
CREATE INDEX IF NOT EXISTS ix_wpldl_expired_unsettled
    ON working_paper_legacy_drain_ledger (expires_at)
    WHERE event_kind = 'issued';

-- 按项目 + 时间检索审计轨（运维与 4.4 守卫）
CREATE INDEX IF NOT EXISTS ix_wpldl_project_issued_at
    ON working_paper_legacy_drain_ledger (project_id, issued_at DESC);

-- 结算行反查其签发行（结算幂等与「一行只能结算一次」的判据基础）
CREATE UNIQUE INDEX IF NOT EXISTS ux_wpldl_one_settlement_per_issuance
    ON working_paper_legacy_drain_ledger (issuance_id)
    WHERE event_kind = 'settled';

COMMENT ON TABLE working_paper_legacy_drain_ledger IS
    '旧式 doc key / callback 签发与结算的 append-only ledger（spec onlyoffice-sheet-open 任务 4.2）；4.4 的旧签发数 / in-flight / drain timeout 三个计数的唯一来源';
COMMENT ON COLUMN working_paper_legacy_drain_ledger.doc_key_sha256 IS
    'doc_key 的 sha256，禁存明文（doc_key 是 OO 房间身份，明文落库等于写入可伪造的会话标识）';
COMMENT ON COLUMN working_paper_legacy_drain_ledger.callback_in_flight IS
    '结算时该 callback 是否仍在途；任务 4.4 的 callback in-flight 计数来源';
