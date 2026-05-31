-- R041: 回滚 V041 — 删除 consol_worksheet_data + consol_note_data 表
-- 幂等：DROP TABLE IF EXISTS

DROP TABLE IF EXISTS consol_worksheet_data;
DROP TABLE IF EXISTS consol_note_data;
