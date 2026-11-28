-- V281: 补齐 ORM 枚举标签在 PG 枚举中缺失的两个值（schema 漂移修复）
--
-- 背景（2026-11-28）：启动漂移检测报 enum_mismatch —
--   projects.project_type 的 public.projecttype 缺 'enterprise_income_tax_settlement'；
--   users.role 的 public.userrole 缺 'site_lead'。
-- ORM 枚举（app/models/base.py）早已声明这两个标签，但历史上没有任何 V*.sql
-- 对这两个枚举 ADD VALUE —— create_all 新建库天然带全标签，存量库则漂移
-- （写入这些值时报 invalid input value）。补两条幂等 ADD VALUE（写法同 V053）。
ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'enterprise_income_tax_settlement';
ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'site_lead';
