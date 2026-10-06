# 任务：完善合并附注刷新对多级表头的列定位

> 硬依赖 P2（consol-note-template-header-unification）完成后合并附注模板有 `_column_groups`。

## 阶段 1：列解析

- [x] 1. 新建 `_resolve_value_columns()` 纯函数
  - 优先按 `_column_groups` 定位
  - 降级到 `headers` 匹配（跳过斜杠路径）
  - 测试：简单表头 / 分组表头 / 三行多级表头 / 无分组

## 阶段 2：刷新端点改进

- [x] 2. `refresh_note_by_formula` 端点改用 `_resolve_value_columns`
  - 替换原有的逐列字符串匹配
  - 向后兼容：无 `_column_groups` 的表走降级
  - 测试：简单表刷新值不变 / 多级表头写到正确列

## 阶段 3：验收

- [x] 3. 三张 multi_header 表的刷新端到端测试
  - 应收账款账龄表：期末→账面余额列、期初→账面余额列
  - 应收账款分类表：期末→账面余额→金额列
  - 其他应收账款账龄表：同账龄表结构

- [x] 4. 回归
  - 合并附注全套端点回归
  - 简单表头刷新行为不变
  - INDEX.md 更新
