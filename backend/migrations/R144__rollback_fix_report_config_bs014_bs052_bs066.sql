-- R144: 回滚 V144（report_config formula/科目码数据修正）。
-- BS-014/BS-052 原公式被置 NULL，当前库无法无损恢复；拒绝自动回滚。
DO $$ BEGIN
    RAISE EXCEPTION 'R144 拒绝自动回滚：report_config 公式清空/科目码修正需使用迁移前快照';
END $$;
