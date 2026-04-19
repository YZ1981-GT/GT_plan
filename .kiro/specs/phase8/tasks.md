# Phase 8 — 任务清单

## 概述
Phase 8 聚焦于数据模型优化、性能提升和用户体验完善。本任务清单基于需求文档，将需求拆解为具体的开发任务。

## 任务组 1：数据模型字段缺失修复

### Task 1.1 辅助表字段补充（✅已在 Phase 6 完成）
- [x] ~~编写 Alembic 迁移脚本（已通过手动 ALTER TABLE 完成）~~
- [x] ~~tb_aux_balance 添加 account_name 字段（VARCHAR(100)，非空）~~
- [x] ~~tb_aux_ledger 添加 account_name 字段（VARCHAR(100)，非空）~~
- [x] ~~从 account_chart 同步 account_name 数据~~
- [x] ~~创建 idx_tb_aux_balance_account_name 索引~~
- [x] ~~创建 idx_tb_aux_ledger_account_name 索引~~
- [x] ~~编写迁移回滚脚本~~
- [x] ~~测试迁移脚本（开发环境验证）~~

### Task 1.2 试算表字段补充
- [x] 编写 Alembic 迁移脚本 034_add_currency_code_to_trial_balance.py
- [x] trial_balance 添加 currency_code 字段（VARCHAR(3)，默认 'CNY'）
- [x] 创建 idx_trial_balance_currency_code 索引
- [x] 编写迁移回滚脚本
- [x] 测试迁移脚本（开发环境验证）

### Task 1.3 穿透查询优化（✅已在 Phase 6 完成）
- [x] ~~修改 LedgerPenetrationService 查询逻辑，直接使用 aux.account_name~~
- [x] ~~移除不必要的 account_chart JOIN~~
- [x] ~~更新穿透查询测试用例~~
- [x] ~~性能测试：对比优化前后查询时间~~
- [x] ~~更新 API 文档~~

## 任务组 2：查询性能优化

### Task 2.1 穿透查询缓存（✅缓存已在 Phase 6 完成，仅游标分页为增量）
- [x] ~~LedgerPenetrationService 添加 Redis 缓存（TTL=5min）~~
- [x] ~~实现 get_balance 缓存逻辑~~
- [x] ~~实现 get_ledger 缓存逻辑~~
- [x] ~~实现 get_aux_balance 缓存逻辑~~
- [x] ~~实现 get_aux_ledger 缓存逻辑~~
- [x] ~~编写缓存测试用例~~
- [x] ~~缓存失效策略：WORKPAPER_SAVED 事件触发缓存清理~~

### Task 2.2 游标分页
- [x] LedgerPenetrationService 实现游标分页
- [x] API 端点支持 cursor 和 limit 参数
- [x] 前端 LedgerPenetration.vue 改用游标分页
- [x] 虚拟滚动组件集成
- [ ] 性能测试：大数据量场景（10万+行）

### Task 2.3 四表联查优化
- [x] 使用 CTE 优化四表联查 SQL
- [x] 添加复合索引优化查询计划
- [ ] EXPLAIN ANALYZE 分析慢查询
- [x] 批量查询优化：减少 N+1 查询
- [ ] 性能测试：对比优化前后响应时间

### Task 2.4 报表生成缓存
- [x] ReportEngine 添加 Redis 缓存（TTL=10min）
- [x] 缓存键：report:{project_id}:{report_type}
- [x] 增量更新：只重新计算受影响的报表行
- [x] 事件驱动缓存失效：TRIAL_BALANCE_UPDATED 触发
- [x] 报表生成完成后发布 REPORT_GENERATED 事件
- [x] 编写缓存测试用例

### Task 2.5 核心表复合索引补齐
- [x] 034 迁移脚本中新增 idx_trial_balance_project_year_std_code 索引
- [x] 034 迁移脚本中新增 idx_tb_balance_project_year_deleted 索引
- [x] 034 迁移脚本中新增 idx_adjustments_project_year_account_code 索引
- [x] 034 迁移脚本中新增 idx_import_batches_project_year 索引
- [x] EXPLAIN ANALYZE 验证索引生效（试算表重算/报表生成/导入计数）

### Task 2.6 事件总线去重
- [x] EventBus 新增 _pending 缓冲区和 debounce 机制（默认 500ms）
- [x] 相同 (event_type, project_id) 在窗口内合并 account_codes
- [x] config.py 新增 EVENT_DEBOUNCE_MS 配置项
- [x] 编写去重测试用例（10 次 publish 只触发 1 次 handler）
- [x] 保留 publish_immediate() 方法供需要立即触发的场景使用

### Task 2.7 公式引擎超时控制
- [x] FormulaEngine.execute() 添加 asyncio.wait_for(timeout=10s)
- [x] 超时返回 FormulaError(code="TIMEOUT")
- [x] 超时日志记录公式内容+project_id+account_code
- [x] config.py 新增 FORMULA_EXECUTE_TIMEOUT 配置项
- [x] 编写超时测试用例

### Task 2.8 数据导入流式处理
- [x] GenericParser 新增 parse_streaming() 方法（openpyxl read_only=True）
- [x] import_service.start_import() 改用流式解析+分批校验+分批写入
- [x] 解析过程中发布 IMPORT_PROGRESS 事件（SSE 进度推送）
- [ ] 内存占用测试：26 万行 Excel 导入时峰值内存 < 200MB
- [x] 向后兼容：CSV 文件仍用原有解析逻辑（CSV 本身是流式的）

## 任务组 3：底稿编辑体验优化

### Task 3.1 ONLYOFFICE 编辑器性能优化
- [x] WOPIHostService.put_file 改为异步事件发布
- [x] WORKPAPER_SAVED 事件异步处理
- [x] 编辑器加载优化：预加载常用模板
- [ ] 文件保存性能测试：对比优化前后保存时间

### Task 3.2 底稿列表加载优化
- [x] WorkpaperList.vue 实现虚拟滚动
- [x] 集成 vue-virtual-scroller 组件
- [x] 懒加载：底稿详情按需加载
- [x] 搜索优化：底稿搜索使用防抖
- [ ] 性能测试：1000+底稿场景

### Task 3.3 底稿预填性能优化
- [x] PrefillService.batch_prefill 并发预填
- [x] 预填结果缓存（TTL=10min）
- [x] 批量预填 API 端点
- [ ] 性能测试：批量预填10个底稿

## 任务组 4：报表导出优化

### Task 4.1 Word 导出性能优化
- [x] ReportExportEngine 模板缓存
- [x] python-docx 并行处理
- [x] 流式导出：大文档避免内存溢出
- [ ] 性能测试：对比优化前后导出时间

### Task 4.2 PDF 导出性能优化
- [x] PDFExportEngine 异步导出
- [x] 集成 task_center 跟踪导出任务
- [x] 前端 ExportPanel.vue 显示导出进度
- [ ] 性能测试：对比优化前后导出时间

### Task 4.3 导出格式一致性
- [x] 统一 Word 导出样式（字体/页边距/表格）
- [x] 导出预览：导出前实时预览
- [x] 格式校验：导出后自动校验
- [x] 格式一致性测试

## 任务组 5：移动端适配

### Task 5.1 响应式布局
- [x] ThreeColumnLayout.vue 移动端适配
- [x] 断点配置：mobile/tablet/desktop
- [x] 移动端单栏布局
- [x] 触摸优化：手势支持
- [x] 字体大小优化

### Task 5.2 移动端底稿编辑
- [x] MobileWorkpaperEditor.vue 组件
- [x] 简化单元格编辑器
- [x] 移动端下载/上传按钮
- [ ] 离线支持：已缓存底稿查看

### Task 5.3 核心功能移动端访问
- [x] 移动端项目列表
- [x] 移动端报表查看
- [x] 移动端穿透查询（简化版）
- [x] 移动端复核查看

## 任务组 6：审计程序精细化

### Task 6.1 细分程序打磨
- [x] ProcedureTrimEngine 程序裁剪逻辑优化
- [x] 风险等级计算优化
- [x] 优先打磨5个高风险科目程序
- [x] 程序裁剪测试

### Task 6.2 程序执行自动化
- [x] 自动识别程序执行条件
- [x] 自动标记程序执行状态
- [x] 自动生成程序执行记录
- [x] 程序执行进度可视化

### Task 6.3 程序模板优化
- [x] 优化程序模板内容
- [x] 增加参考案例
- [x] 版本管理
- [x] 模板共享机制

## 任务组 7：数据校验增强

### Task 7.1 数据一致性校验
- [x] DataValidationEngine 余额表与辅助表一致性校验
- [x] 报表与附注一致性校验
- [x] 底稿与试算表一致性校验
- [x] 调整分录与报表一致性校验

### Task 7.2 数据完整性校验
- [x] 必填字段完整性校验
- [x] 数据格式正确性校验
- [x] 数据范围合理性校验
- [x] 数据逻辑一致性校验

### Task 7.3 数据校验面板
- [x] DataValidationPanel.vue 组件
- [x] ValidationList.vue 组件
- [x] 按类型/严重度筛选
- [x] 一键修复常见错误
- [x] 校验结果导出

### Task 7.4 数据校验 API
- [x] POST /api/projects/{id}/data-validation 端点
- [x] GET /api/projects/{id}/data-validation/findings 端点
- [x] POST /api/projects/{id}/data-validation/fix 端点
- [x] POST /api/projects/{id}/data-validation/export 端点

## 任务组 8：性能监控

### Task 8.1 Prometheus 指标收集
- [x] 集成 prometheus-client
- [x] API 响应时间指标
- [x] 数据库查询时间指标
- [x] 缓存命中率指标
- [x] 前端性能指标（FCP/LCP/TTI）

### Task 8.2 性能告警
- [x] 设置性能阈值
- [x] 慢查询告警
- [x] API 响应时间告警
- [x] 前端性能告警

### Task 8.3 性能分析面板
- [x] PerformanceMonitor.vue 组件
- [x] ResponseTimeChart.vue 组件
- [x] CacheHitRateChart.vue 组件
- [x] 性能趋势分析
- [x] 性能瓶颈定位

### Task 8.4 性能监控 API
- [x] GET /api/admin/performance-stats 端点
- [x] GET /api/admin/performance-metrics 端点
- [x] GET /api/admin/slow-queries 端点

## 任务组 9：用户体验优化

### Task 9.1 加载状态优化
- [x] 统一加载状态提示组件
- [x] 骨架屏组件
- [x] 错误提示组件
- [x] 空状态组件

### Task 9.2 操作反馈优化
- [x] 操作成功提示优化
- [x] 操作失败提示优化
- [x] 操作进度提示
- [x] 操作撤销功能

### Task 9.3 快捷键支持
- [x] 常用操作快捷键
- [x] 快捷键提示
- [x] 快捷键自定义
- [x] 移动端手势支持

## 任务组 10：安全增强

### Task 10.1 数据加密
- [x] 集成 cryptography 库
- [x] EncryptionService 服务
- [x] 敏感数据加密存储
- [x] API 密钥加密
- [x] 密码加密升级（bcrypt cost=14）

### Task 10.2 审计日志增强
- [x] AuditLogger 服务增强
- [x] 记录更详细的操作上下文
- [x] 审计日志导出（CSV/Excel）
- [x] 审计日志查询和分析
- [x] 审计日志长期存储（1年+）
- [x] ~~敏感导出操作审计日志（底稿下载/附件下载/报表导出/批量下载）~~（✅已在 Phase 7 完成）
- [x] 审计日志告警（异常操作自动告警：大量下载/异常时间操作/短时间内重复导出）

### Task 10.3 安全监控
- [x] SecurityMonitor 服务
- [x] ~~登录失败次数监控~~（✅已在 Phase 0 完成）
- [x] 异常IP检测
- [x] 会话管理
- [x] 安全事件日志

### Task 10.4 安全监控 API
- [x] GET /api/security/login-attempts 端点
- [x] POST /api/security/lock-account 端点
- [x] GET /api/security/sessions 端点
- [x] GET /api/audit-logs/export 端点

### Task 10.5 权限查询缓存
- [x] deps.py require_project_access() 查询结果缓存到 Redis（TTL=5min）
- [x] 缓存 key：perm:{user_id}:{project_id}
- [x] Redis 不可用时降级为直接查库（不阻断请求）
- [x] project_users CRUD 操作后主动失效对应缓存（invalidate_permission_cache）
- [x] 编写权限缓存测试用例（缓存命中/失效/降级）

## 任务组 11：测试与验收

### Task 11.1 单元测试
- [x] 数据模型字段补充测试（2个测试）
- [x] 查询性能优化测试（5个测试）
- [x] 事件去重测试（3个测试：debounce/合并/immediate）
- [x] 公式超时测试（2个测试：正常/超时）
- [x] 流式导入测试（3个测试：Excel流式/进度事件/内存限制）
- [x] 底稿编辑优化测试（3个测试）
- [x] 报表导出优化测试（3个测试）
- [x] 数据校验测试（5个测试）
- [x] 安全增强测试（4个测试）
- [x] 权限缓存测试（3个测试：命中/失效/降级）

### Task 11.2 集成测试
- [x] 穿透查询集成测试（2个测试）
- [x] 报表生成集成测试（2个测试）
- [x] 数据校验集成测试（2个测试）
- [x] 性能监控集成测试（1个测试）

### Task 11.3 性能测试
- [ ] 穿透查询性能测试（优化前后对比）
- [ ] 四表联查性能测试（优化前后对比）
- [ ] 报表生成性能测试（优化前后对比）
- [ ] 底稿预填性能测试（优化前后对比）

### Task 11.4 冒烟测试
- [x] 后端测试套件运行
- [ ] 6条主链路手动检查
- [ ] 4个API验证
- [ ] 验收签字表

### Task 11.5 文档更新
- [ ] API 文档更新
- [ ] 部署文档更新
- [ ] 用户手册更新
- [x] README.md 更新

## 执行顺序

0. **迁移脚本**（创建 034 Alembic 迁移脚本：currency_code 字段 + 4个复合索引）
1. **Task 1.1-1.3**（数据模型字段缺失修复）→ 2. **Task 2.1-2.8**（查询性能优化，含索引/事件去重/超时控制/流式导入）
3. **Task 3.1-3.3**（底稿编辑体验优化）→ 4. **Task 4.1-4.3**（报表导出优化）
5. **Task 5.1-5.3**（移动端适配）→ 6. **Task 6.1-6.3**（审计程序精细化）
7. **Task 7.1-7.4**（数据校验增强）→ 8. **Task 8.1-8.4**（性能监控）
9. **Task 9.1-9.3**（用户体验优化）→ 10. **Task 10.1-10.5**（安全增强，含权限缓存）
11. **Task 11.1-11.5**（测试与验收）

## 数据库迁移规划

Phase 8 新增 1 个迁移脚本（1a 已在 Phase 6 手动完成）：

| 迁移脚本 | 包含表/字段 | 功能域 | 状态 |
|---------|------------|--------|------|
| ~~026_add_account_name_to_aux_tables.py~~ | ~~tb_aux_balance.account_name + tb_aux_ledger.account_name + 2个索引~~ | ~~数据模型修复~~ | ✅Phase 6 已完成 |
| 034_phase8_currency_and_indexes.py | trial_balance.currency_code + 5个复合索引 | 数据模型修复+性能优化 | 待开发 |

## 优先级建议

### P0（必须实现）
- 数据模型字段缺失修复（Task 1.1-1.3）
- 查询性能优化（Task 2.1-2.4）

### P1（重要）
- 底稿编辑体验优化（Task 3.1-3.3）
- 报表导出优化（Task 4.1-4.3）
- 数据校验增强（Task 7.1-7.4）
- 安全增强（Task 10.1-10.4）

### P2（可选）
- 移动端适配（Task 5.1-5.3）
- 审计程序精细化（Task 6.1-6.3）
- 性能监控（Task 8.1-8.4）
- 用户体验优化（Task 9.1-9.3）

## 预估工期

- P0任务：2-3周（数据模型修复 + 查询性能优化）
- P1任务：3-4周（体验优化 + 导出优化 + 数据校验 + 安全增强）
- P2任务：2-3周（移动端适配 + 程序精细化 + 性能监控 + 用户体验优化）

总计：7-10周（约2-2.5个月）
