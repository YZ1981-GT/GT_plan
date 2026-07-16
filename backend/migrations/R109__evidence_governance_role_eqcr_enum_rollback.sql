-- R109: 回滚 V109（补入 EQCR 角色 enum 值）
-- PostgreSQL 不支持从 enum 类型移除已加入的值（无 DROP VALUE）。
-- 该迁移为 additive 且 IF NOT EXISTS 幂等，enum 中多出的 'eqcr' 值不影响既有数据/查询，
-- 故回滚为**有意的 no-op**：不删除 enum 值，避免破坏依赖该值的行/约束。
-- 如确需彻底移除，须离线重建 enum 类型（重命名旧类型→建新类型→改列→删旧类型），
-- 属高风险人工操作，不在自动回滚范围内。
SELECT 1;
