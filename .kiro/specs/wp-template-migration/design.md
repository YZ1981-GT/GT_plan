# 设计文档：模板版本升级数据迁移

## 概述
模板版本升级时，对已编制底稿执行 sheet/列级 diff → 数据迁移 → 迁移报告。核心是"保留用户数据 + 适配新结构"。

## 核心设计

### 模板 diff 引擎
- 输入：旧模板 xlsx + 新模板 xlsx
- 输出：`TemplateDiff { added_sheets, removed_sheets, renamed_sheets, added_columns, removed_columns, renamed_columns }`
- 实现：openpyxl 读两版本 → 按 sheet 名 + 列标题对比

### 数据迁移引擎
- 输入：TemplateDiff + 已编制底稿 parsed_data
- 输出：迁移后的 parsed_data
- 策略：共有保留 / 新增填默认 / 删除归档到 `_archived_data`

### 迁移报告
- 成功/跳过/需人工处理分类
- 输出 markdown 到 docs/uat/

### 快照与回滚
- 迁移前 parsed_data 快照存 `wp_migration_snapshots` 表
- 回滚 = 恢复快照

## 正确性属性
**Property 1**: 迁移后共有 sheet/列的用户数据与迁移前一致。
**Property 2**: 迁移可逆——回滚后 parsed_data 与迁移前一致。

## 不在范围
- 不改模板文件
- 不做实时迁移
