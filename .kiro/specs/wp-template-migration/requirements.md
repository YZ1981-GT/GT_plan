# 需求文档：模板版本升级数据迁移

## 引言

致同模板年度修订（如 v2025-R5→R6）后，已编制的底稿如何迁移用户数据？当前完全无机制——sheet 增删、列变化时用户数据会丢失或错位。6000 人规模 + 年度修订必然遇到。

## 需求

### 需求 1：模板版本 diff
1. WHEN 新模板版本发布，THE system SHALL 生成 sheet/列级 diff（新增/删除/改名/移动）
2. WHEN diff 生成，THEN SHALL 标注每个变化的影响范围（影响多少已编制底稿）

### 需求 2：已编制底稿数据迁移
1. WHEN 模板升级，THE system SHALL 对已编制底稿按 diff 迁移用户数据
2. WHEN 迁移执行，THEN 共有 sheet/列的用户数据 SHALL 保留不丢
3. WHEN 新增 sheet/列，THEN SHALL 从新模板填充默认值
4. WHEN 删除 sheet/列，THEN 用户数据 SHALL 归档（不丢弃，可回溯）

### 需求 3：迁移报告
1. WHEN 迁移完成，THE system SHALL 生成迁移报告（成功/跳过/需人工处理的底稿列表）
2. WHEN 某底稿无法自动迁移（如结构冲突），THEN SHALL 标记为"需人工处理"

### 需求 4：可回滚
1. WHEN 迁移执行前，THE system SHALL 创建快照（支持回滚）
2. WHEN 用户发现迁移问题，THEN SHALL 能回滚到迁移前状态

## 范围边界
- 不改模板文件本身（模板由审计专家维护）
- 不做实时迁移（批量离线执行）
- 不处理跨年继承（那是已有的 copy_from_prior 能力）
