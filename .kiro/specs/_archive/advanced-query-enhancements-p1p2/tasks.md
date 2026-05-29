# Tasks — 高级查询模块剩余 P1-P2 增强项

> Spec: `advanced-query-enhancements-p1p2`
> Design: `design.md`
> Requirements: `requirements.md`

---

## Phase 1: P2 架构基础（Req 4 / 5 / 6 / 7 / 8）

### Task 1: wp_template_registry 双源合并入 DB（Req 4）

- [x] 1.1 创建 Alembic migration：`wp_template_registry` 表 DDL（含 PK / cycle CHECK / 3 索引）
- [x] 1.2 编写 migration data_upgrades：从 `wp_account_mapping.json` + `step_sheet_mapping.json` 双源读取、去重合并、冲突仲裁（step_sheet_mapping 为准）写入
- [x] 1.3 创建 `WpTemplateRegistryService`：`load_tree()` 从 PG 读取替代 JSON 文件读取
- [x] 1.4 改造 `get_indicators` 端点：优先从 `wp_template_registry` 读取底稿树
- [x] 1.5 实现 version 递增逻辑 + `X-Indicators-Schema-Version` 响应头联动
- [ ] 1.6 测试：migration 幂等性 + 回滚 + 行数断言 + 冲突仲裁验证
  - [x] 1.6.1 Property 9: migration 冲突仲裁 step_sheet_mapping 优先
  - [x] 1.6.2 Property 10: version 单调递增
  - [x] 1.6.3 Property 11: migration 行数 = 双源去重并集

### Task 2: parsed_data GIN 索引（Req 5）

- [x] 2.1 创建 Alembic migration：`CREATE INDEX CONCURRENTLY` + `_ccnew` 残骸清理逻辑
- [x] 2.2 实现启动时 `pg_stat_progress_create_index` 检查 → 全局 `INDEX_BUILDING` flag
- [x] 2.3 改造查询路径：flag=True 时降级顺序扫描 + `X-Index-Status=building` 响应头
- [x] 2.4 添加 `pg_index_size` 监控告警阈值（500MB）
- [x] 2.5 测试：EXPLAIN ANALYZE 验证走索引 + 降级路径单测

### Task 3: structure.json 单源化（Req 6）

- [x] 3.1 改造 `POST /api/working-papers/{id}/univer-save`：移除 structure.json 写入逻辑
- [x] 3.2 改造三式联动读取路径：从 `parsed_data['univer_snapshot']` 解析（不读 structure.json）
- [x] 3.3 编写一次性迁移脚本 `scripts/_migrate_structure_to_jsonb.py`：回填 + 删文件
- [x] 3.4 物理删除 structure.json 相关读写代码 + 单元测试 mock
- [x] 3.5 实现 `snapshot_missing_total` 监控指标（缺失时走 LibreOffice 兜底）
- [x] 3.6 测试：Property 12 单源化 round-trip + 删除验证

### Task 4: 审计日志洪泛节流（Req 7）

- [x] 4.1 创建 `backend/app/services/audit_throttle.py`：Redis SET NX EX 5s 实现
- [x] 4.2 集成到 `execute_query` 路径：调用 `should_record()` 决定是否写 audit_log
- [x] 4.3 实现敏感操作白名单（cell_writeback / cross_sheet_trace 不节流）
- [x] 4.4 实现 Redis 不可用降级（全部记录 + logger.warning）
- [x] 4.5 测试：
  - [x] 4.5.1 Property 13: 审计节流窗口
  - [x] 4.5.2 Property 14: 敏感操作绕过节流
  - [x] 4.5.3 Redis 降级单测

### Task 5: LibreOffice 池化 + 健康检查（Req 8）

- [x] 5.1 重构 `libreoffice_pool.py`：模块级 `asyncio.Semaphore(2)` + `convert_with_libreoffice` async 方法
- [x] 5.2 实现 Windows pid+tid UserInstallation 隔离
- [x] 5.3 实现 startup 事件 4 路径探测 + `soffice --version` 健康检查
- [x] 5.4 实现 60s 超时 kill + semaphore 释放 + HTTP 504
- [x] 5.5 实现 `X-Recompute-Queue-Depth` 响应头 + `libreoffice_queue_depth` metric
- [x] 5.6 测试：
  - [x] 5.6.1 Property 15: 并发限制 ≤ 2
  - [x] 5.6.2 Property 16: Windows UserInstallation 唯一性
  - [x] 5.6.3 Property 17: 超时强制 kill

---

## Phase 2: P1 跨模块 + 模板联动（Req 13 / 14 / 15）

### Task 6: 跨模块单元格级查询（Req 13）

- [x] 6.1 创建 `backend/app/services/custom_query/module_cell_resolver.py`：source 命名空间路由器
- [x] 6.2 实现 `_query_report_cells`：从 `report_snapshot.data` JSONB 提取 cell
- [x] 6.3 实现 `_query_note_cells`：从 `consol_note_data.data` JSONB 提取 cell
- [x] 6.4 实现 `_query_adj_cells`：从 `adjustments` 表拼虚拟 sheet
- [x] 6.5 实现 `_query_tb_cells`：从 `trial_balance` 表拼虚拟 sheet
- [x] 6.6 改造 `execute_query`：识别 `report:` / `note:` / `adj:` / `tb:` 前缀路由到 Module_Cell_Resolver
- [x] 6.7 前端 SheetCellRangePicker 适配 4 模块 source（透明识别）
- [x] 6.8 测试：
  - [x] 6.8.1 Property 24: source URI 解析 round-trip
  - [x] 6.8.2 Property 25: 模块路由 + 输出形态
  - [x] 6.8.3 4 模块 × 选区 e2e（4 条）

### Task 7: 模板页面双向联动（Req 14）

- [x] 7.1 创建 `TemplateLibraryButton.vue`：3 模板页挂「📊 高级查询」按钮 + emit `open-custom-query`
- [x] 7.2 实现 `GET /api/custom-query/address-resolve` 端点：URI 反查模板信息
- [x] 7.3 前端右键菜单「🔗 跳模板溯源」：调 address-resolve → router.push 跳转 + highlight
- [x] 7.4 改造 IndicatorTree：新增「按模板形态分组」视图 + toggle 切换 + sessionStorage 记忆
- [x] 7.5 实现 `open-custom-query` 事件监听：自动选中 source + 树 reveal + scroll-into-view
- [x] 7.6 测试：
  - [x] 7.6.1 Property 27: registry lookup 正确性
  - [x] 7.6.2 Property 28: 事件驱动树 reveal
  - [x] 7.6.3 3 页面按钮存在性 e2e

### Task 8: 模板入口可达性 + 保存完整性（Req 15）

- [x] 8.1 创建 `scripts/_ensure_custom_query_tables.py`：启动检查兜底建表 + 索引
- [x] 8.2 创建 `MyTemplatesDialog.vue` + `SaveAsTemplateButton.vue`：3 入口共用
- [x] 8.3 扩展 `custom_query_templates.config` JSONB schema：完整字段（cell_range / sheet_name / page_size / sort）
- [x] 8.4 实现「保存为模板」：从 SheetCellRangePicker 选区状态序列化完整 config
- [x] 8.5 实现「加载模板」：反序列化 config → 还原所有控件状态（选区器 + range + 树 reveal + 列宽）
- [x] 8.6 实现 stale sheet 检测：config.cell_range 引用 sheet 不存在时弹对话框
- [x] 8.7 测试：
  - [x] 8.7.1 Property 29: 模板 config save/load round-trip
  - [x] 8.7.2 表缺失修复单测
  - [x] 8.7.3 3 入口同步状态 e2e

---

## Phase 3: P1 业务功能（Req 1 / 2 / 3）

### Task 9: 多底稿批量查询（Req 1）

- [x] 9.1 创建 `BatchQueryToolbar.vue`：ctrl+click 多选 + 紫底白字 chip + 空集合阻断
- [x] 9.2 创建 `BatchQueryResultGroup.vue`：分组折叠面板 + 合并导出按钮
- [x] 9.3 实现前端 Batch_Query_Controller：Promise.allSettled + 最大并发 5 限流
- [x] 9.4 创建 `POST /api/custom-query/batch-execute` 端点（参数校验 + 审计聚合）
- [x] 9.5 实现合并导出：xlsx-js-style 多 sheet 写入
- [x] 9.6 测试：
  - [x] 9.6.1 Property 1: 批量故障隔离
  - [x] 9.6.2 Property 2: 并发限制 ≤ 5
  - [x] 9.6.3 空集合阻断 vitest
  - [x] 9.6.4 批量查询 e2e

### Task 10: 双向编辑写回（Req 2）

- [x] 10.1 创建 `backend/app/services/custom_query/snapshot_writer.py`：SnapshotWriter 类
- [x] 10.2 实现乐观锁：`X-File-Opened-At` vs `updated_at` 比对 → WritebackConflict
- [x] 10.3 实现单事务写：JSONB + xlsx + prefill_stale + cross-ref:updated 事件
- [x] 10.4 创建 `POST /api/custom-query/cell-writeback` 端点
- [x] 10.5 扩展 Snapshot_Writer 支持 4 模块路由写入（Req 13 联动）
- [x] 10.6 创建 `CellWritebackDialog.vue`：编辑态 + 冲突 409 处理 + 权限检查
- [ ] 10.7 测试：
  - [x] 10.7.1 Property 3: 写事务一致性
  - [x] 10.7.2 Property 4: 乐观锁冲突检测
  - [x] 10.7.3 Property 5: 写权限强制
  - [x] 10.7.4 Property 26: 跨模块写路由
  - [x] 10.7.5 写回 e2e

### Task 11: 跨 sheet 公式追溯（Req 3）

- [x] 11.1 创建 `backend/app/services/custom_query/cross_sheet_resolver.py`：BFS + 环检测
- [x] 11.2 实现公式解析器：regex 提取 `=Sheet!Cell` 引用对
- [x] 11.3 创建 `GET /api/custom-query/cross-sheet-trace` 端点
- [x] 11.4 创建 `CrossSheetTracePopover.vue`：300ms 延迟 + 4 层展示 + 循环/缺失标记
- [x] 11.5 测试：
  - [x] 11.5.1 Property 6: 跨 sheet 引用解析
  - [x] 11.5.2 Property 7: 深度终止
  - [x] 11.5.3 Property 8: 循环检测
  - [x] 11.5.4 追溯 e2e

---

## Phase 4: 体验细节（Req 9 / 10 / 11 / 12）

### Task 12: 选区记忆（Req 9）

- [x] 12.1 创建 `frontend/src/composables/useRangeMemory.ts`：save / load / clear / LRU 淘汰
- [x] 12.2 集成到 SheetCellRangePicker：打开时自动回填 + 应用时保存
- [x] 12.3 实现越界 clamp + 提示
- [x] 12.4 工具栏「清除记忆」按钮
- [x] 12.5 测试：
  - [x] 12.5.1 Property 18: save/load round-trip
  - [x] 12.5.2 Property 19: LRU 容量
  - [x] 12.5.3 Property 20: 越界 clamp

### Task 13: snapshot 过期警告（Req 10）

- [x] 13.1 创建 `SnapshotStalenessChip.vue`：根据 source + saved_at 选择 chip 变体
- [x] 13.2 实现点击弹窗：精确时间 + 最后编辑人 + 「立即重算」按钮
- [x] 13.3 集成到选区结果区顶部
- [x] 13.4 测试：Property 21 chip 变体选择

### Task 14: 大 range 自动分页（Req 11）

- [x] 14.1 创建 `RangePaginator` 逻辑：阈值判断 + 前端切片 + el-pagination
- [x] 14.2 实现 > 5000 行强制分页 + 禁用全部展开
- [x] 14.3 实现「全部展开」确认对话框
- [x] 14.4 测试：Property 22 分页阈值

### Task 15: 公式溯源 popover（Req 12）

- [x] 15.1 创建 `FormulaTracePopover.vue`：300ms hover + 200ms 关闭延迟
- [x] 15.2 实现公式分类：跨 sheet vs 本 sheet → 不同渲染模式
- [x] 15.3 跨 sheet 引用渲染为可点击链接（调 Cross_Sheet_Resolver）
- [x] 15.4 解析失败兜底：红色提示 + 原始字符串
- [x] 15.5 测试：Property 23 公式分类

---

## Phase 5: 收尾与文档

### Task 16: 死代码清理 + 文档同步

- [x] 16.1 物理删除所有 structure.json 残留文件 + fallback 代码 + DEPRECATED 注释
- [x] 16.2 更新 `#dev-history` 追加本轮成果摘要
- [x] 16.3 更新 `#conventions` 同步新增红线（跨模块 source 命名空间 + 模板联动事件总线契约）
- [x] 16.4 更新 `#architecture` 追加 wp_template_registry 表结构 + GIN 索引 + LibreOffice 池化 + 4 模块 cell 提取器架构图
- [x] 16.5 全量回归测试：现有 18 commit 能力全 pass + 模板库 3 页面无回归

