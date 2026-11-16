-- R136: 回滚 V136（report_config formula 数据修正）。
-- V136 没有保存被替换的旧 formula；反向 UPDATE 无法区分后续人工修改，拒绝自动回滚。
DO $$ BEGIN
    RAISE EXCEPTION 'R136 拒绝自动回滚：report_config 公式修正需使用迁移前快照';
END $$;
