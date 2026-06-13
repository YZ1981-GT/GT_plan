-- R073: 回滚 V073 迁入的 workpaper 锁数据
-- 仅删除 resource_type='workpaper' 的记录，不影响其它 resource_type
-- 无匹配行时静默成功（DELETE no-op）

DELETE FROM editing_locks WHERE resource_type = 'workpaper';
