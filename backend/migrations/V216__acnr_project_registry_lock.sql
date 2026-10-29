-- V216: 项目锁定的地址目录版本落库（spec acnr-foundation-defect-closure 需求 7.1~7.2 / D5 / T17）。
--
-- 背景：历史版本锁定原先只记在进程内字典（`acnr/immutability.py` 的 `_project_registry_versions`），
-- 进程一重启就全丢，归档项目在目录升级后会按新目录解析 —— 归档时的底稿地址对不回去。
-- 段四审计 F4-02 / F4-04 据此判「resolver 支持版本锁定」≠「归档项目已可复现」。
--
--   acnr_registry_version   项目锁定到的目录版本号（14 位 UTC 时间戳，形态 ^\d{14}$；
--                           NULL = 未锁定，按当前目录解析）。长度按 14 定死，与
--                           `catalog_contract.REGISTRY_VERSION_PATTERN` 同一形态。
--   acnr_registry_locked_at 锁定时间（带时区；与 version 同写同清）。
--
-- 存量不回填：既有项目一律为 NULL（未锁定）。不伪造历史版本 —— 它们归档时并没有记过版本，
-- 编不出真实值；按未锁定处理会按当前目录解析，与落库前的行为一致。
-- 两列都可空、无默认值、不建索引：只在归档 / 取消归档时写，读取按主键取项目行。
-- 编号：原用 V214，但共享库里 V214（custom_query_template_soft_delete）与 V215
-- （account_chart_dataset_versioning）已被别的会话应用，其迁移文件在各自工作树里、
-- 本工作树看不到。取号口径因此更正为 max(磁盘最大号, 库里已应用最大号) + 1 = V216。
ALTER TABLE projects ADD COLUMN IF NOT EXISTS acnr_registry_version VARCHAR(14);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS acnr_registry_locked_at TIMESTAMPTZ;

COMMENT ON COLUMN projects.acnr_registry_version IS
    '锁定的 ACNR 地址目录版本号（14 位 UTC 时间戳）；NULL = 未锁定，按当前目录解析';
COMMENT ON COLUMN projects.acnr_registry_locked_at IS
    'ACNR 目录版本锁定时间；与 acnr_registry_version 同写同清';
