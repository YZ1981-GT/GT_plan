-- V075: 下线 v1 底稿专用锁表 workpaper_editing_locks
-- 前置条件：阶段 2 四门控全满足后执行（前端全量切 v2 / 存量迁移核对 / Playwright 全链路 / 测试覆盖迁移）
-- V073 已将存量活跃锁迁入 editing_locks (resource_type='workpaper')
-- 本脚本仅 DROP 源表，配对 R075 可重建空表（但无法恢复数据或 v1 功能）

DROP TABLE IF EXISTS workpaper_editing_locks;
