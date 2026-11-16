-- R138: 回滚 V138（权益/资产报表配置修正）。
-- 部分 formula 被置 NULL，原值未保存在表内，不能安全恢复。
DO $$ BEGIN
    RAISE EXCEPTION 'R138 拒绝自动回滚：report_config 代码修正/公式清空不可从当前库无损恢复';
END $$;
