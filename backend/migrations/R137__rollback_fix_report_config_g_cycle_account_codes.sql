-- R137: 回滚 V137（报表配置科目码数据修正）。
-- 反向替换可能误改迁移后的人工公式，必须使用迁移前逐行快照。
DO $$ BEGIN
    RAISE EXCEPTION 'R137 拒绝自动回滚：report_config 科目码修正需使用迁移前快照';
END $$;
