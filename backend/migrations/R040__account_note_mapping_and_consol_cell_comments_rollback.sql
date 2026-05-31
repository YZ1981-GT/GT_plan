-- R040: 回滚 V040 — 删除 account_note_mapping + consol_cell_comments 表
-- 幂等：DROP TABLE IF EXISTS

DROP TABLE IF EXISTS account_note_mapping;
DROP TABLE IF EXISTS consol_cell_comments;
