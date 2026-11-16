-- R114: 回滚 V114（revision registry 修复/重放）。
-- 修复迁移没有独立可逆数据边界；自动删除会误伤 V112 真实版本链，故拒绝。
DO $$ BEGIN
    RAISE EXCEPTION 'R114 拒绝自动回滚：V114 是 revision registry 修复/重放迁移，请使用备份恢复';
END $$;
