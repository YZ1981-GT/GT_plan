# 底稿编辑器瘦身与跨模块联动 — 任务清单

> 对应 requirements.md（7 US）+ design.md
> 数据源：workpaper_template_analysis.json（349 模板 / 2602 sheet / 15 渲染类型）
> 预估工作量：10 人天 / 3 Sprint
> 核心原则：底稿必须先能正确渲染（schema 全覆盖），再做瘦身和联动

---

## Sprint 1：render_schema 全覆盖 + 底稿渲染完整性（4 人天）

- [x] 1. 修复 generate_wp_render_schema.py 去重 bug（US-7，最高优先）
  - [x] 1.1 修复 `extract_wp_code_from_filename`：去掉 `.split("-")[0]`，保留完整 wp_code（如 A1-11/D2-1）
  - [x] 1.2 修复 `iter_template_files`：去掉 `seen_codes.setdefault` 去重逻辑，每个 xlsx 独立生成
  - [x] 1.3 新增 `--analysis-json` 参数：加载 workpaper_template_analysis.json 作为 ground truth 交叉验证
  - [x] 1.4 重跑全量生成：`python backend/scripts/generate_wp_render_schema.py --overwrite`
  - [x] 1.5 验证 yaml 总数 ≥349（每个模板 xlsx 至少 1 个 yaml）
  - [x] 1.6 验证 14 个手写 yaml 未被覆盖（手写优先级高于 generated）

- [x] 2. render_schema 质量验证（确保每个 sheet 按实际内容正确路由）
  - [x] 2.1 A 类验证（65 模板 / 607 sheet）：278 个 HTML 中控台 sheet 的 componentType = a-program-console
  - [x] 2.2 B 类验证（49 模板 / 262 sheet）：149 个索引导航 sheet 的 componentType = b-index
  - [x] 2.3 C 类验证（36 模板 / 164 sheet）：166 个嵌套表 sheet 的 sub_tables 定义与模板 xlsx 实际结构匹配
  - [x] 2.4 D 类验证（17 模板 / 155 sheet）：5 子模式正确路由（table=305 / confirmation=109 / review=27 / paragraph=19 / qa=9）
  - [x] 2.5 E 类验证（5 模板 / 56 sheet）：292 个 HTML 表单 + 29 个 stepper 正确映射到 e-control-test
  - [x] 2.6 H 类验证（11 模板 / 187 sheet）：104 个静态展示 sheet 的 componentType = h-static-doc
  - [x] 2.7 F/G 类确认（30 模板 / 348 sheet）：864 个 Univer sheet 保持 componentType = univer
  - [x] 2.8 I 类确认：244 个跳过渲染 sheet 的 componentType = skip
  - [x] 2.9 7 个 PENDING sheet 人工归类决策并补入 yaml

- [x] 3. CI + 前端验证
  - [x] 3.1 新增 `backend/tests/test_render_schema_coverage.py`：3 个断言（覆盖率 100% / sheets 匹配 / componentType 一致）
  - [x] 3.2 前端验证：useWpClassification 对所有 wp_code 返回有效 componentType（不再 fallback Univer）
  - [x] 3.3 Playwright 抽样验证：每类（A/B/C/D/E/H）各选 2 个底稿打开确认 HTML 渲染正确
  - [x] 3.4 xlsx 导出 round-trip 验证：A/C/D/E 各选 1 个底稿，填入测试数据 → 导出 xlsx → 与模板 diff 确认 1:1 还原

---

## Sprint 2：编辑器瘦身 + 跨模块联动（4 人天）

- [x] 3. CycleDialogSlot 配置驱动化（US-1）
  - [x] 3.1 新建 `src/config/cycleDialogRegistry.ts`，定义 15 条 dialog 配置
  - [x] 3.2 新建 `src/components/workpaper/CycleDialogSlot.vue`（配置读取 + 匹配 + 渲染 trigger + 异步加载 dialog）
  - [x] 3.3 WorkpaperEditor.vue 移除 12 个 trigger div + 15 个 dialog 实例 + 15 个 import + 15 个 ref
  - [x] 3.4 WorkpaperEditor.vue 插入 `<CycleDialogSlot>` 单组件替代
  - [x] 3.5 验证行数 ≤2100（减 ≥600 行）
  - [x] 3.6 PBT P-1：cycleDialogRegistry 配置完备性测试（正则合法 + 组件存在 + 无歧义）
  - [x] 3.7 Playwright 回归：F/G/H/I/K/L/M/N 各循环 dialog 打开/关闭/保存

- [x] 4. 报表 stale 联动（US-2）
  - [x] 4.1 新建 `backend/app/services/report_stale_service.py`
  - [x] 4.2 `POST /api/workpapers/{id}/save` 成功后调用 `mark_if_mapped`
  - [x] 4.3 SSE 广播 `report.stale` 事件
  - [x] 4.4 ReportView.vue 订阅 + 黄色横幅 + 刷新按钮
  - [x] 4.5 PBT P-2：stale 传播正确性（映射命中/未命中/幂等）
  - [x] 4.6 性能断言：mark_if_mapped <50ms

- [x] 5. C 类底稿 → 附注同步（US-3）
  - [x] 5.1 扩展 `wp_disclosure_sync_service.py` 新增 `sync_from_html` 方法
  - [x] 5.2 新增端点 `POST /api/wp-disclosure-sync/{wp_id}/sync-html`
  - [x] 5.3 WorkpaperEditor.vue onSaveSuccess 中检测 c-note-table 类型触发同步
  - [x] 5.4 冲突检测 + 409 响应 + 前端 ElMessageBox 处理
  - [x] 5.5 PBT P-3：同步一致性（值相等 + is_stale=false + 原子性）
  - [x] 5.6 审计日志写入验证

---

## Sprint 3：附件 + LLM + router 治理（2 人天）

- [x] 6. 附件联动（US-4）
  - [x] 6.1 workpaper_attachment 表新增 `row_ref` 列（V 迁移）
  - [x] 6.2 GtAProgramConsole 每行增加 📎 按钮 + badge
  - [x] 6.3 GtEControlTest 每步骤增加 📎 按钮
  - [x] 6.4 点击弹出 AttachmentDropZone 绑定 wp_id + sheet + row
  - [x] 6.5 PBT P-4：附件关联完整性（表记录 + evidence_index + 物理文件）

- [x] 7. LLM 辅助填写（US-5）
  - [x] 7.1 GtDFormParagraph / GtDFormQA / GtEControlTest 增加 🤖 AI 建议按钮
  - [x] 7.2 后端 `wp_ai.py` 新增 `POST /{wp_id}/suggest` 端点
  - [x] 7.3 前端采纳/修改/忽略交互 + ai_assisted 标记
  - [x] 7.4 feature flag WP_AI_SERVICE_ENABLED 控制按钮显隐
  - [x] 7.5 PBT P-5：LLM 安全性（flag 关闭 403 / 长度限制 / 审计轨迹）

- [x] 8. router_registry 聚合治理（US-6）
  - [x] 8.1 workpaper.py 按 6 组重构注册逻辑（模板/生命周期/复核/渲染/数据/搜索）
  - [x] 8.2 验证所有端点 URL 不变（pytest 全量通过）
  - [x] 8.3 注册行数 ≤20

---

## Sprint 4：用户体验增强（P2 迭代，3 人天）

> 在 Sprint 1~3 核心功能完成后实施，按成本/收益排序。

- [x] 9. 底稿填写完成度可视化（US-8，高收益低成本）
  - [x] 9.1 新建 `useWpCompletionRate` composable：按组件类型分化计算逻辑
  - [x] 9.2 底稿编辑器顶部增加 el-progress circle（36px）
  - [x] 9.3 底稿列表页每行增加完成度小圆环（24px）
  - [x] 9.4 A 类：已决策/总程序；D 类：已答/总问题；E 类：已完成步骤/总步骤

- [x] 10. schema 缺失智能提示（US-10，低成本高感知）
  - [x] 10.1 `useWpRenderer` 增加 `schemaFallbackBanner` computed
  - [x] 10.2 GtWpRenderer 顶部渲染 info banner（class_code 为 A~E 但 fallback 到 Univer 时）
  - [x] 10.3 schema 全覆盖后 banner 自动消失

- [x] 11. 底稿间导航增强（US-9）
  - [x] 11.1 新建 `useWpNavigationHistory` composable（sessionStorage 栈，max=5）
  - [x] 11.2 GtIndexChip 跳转时 push 历史记录
  - [x] 11.3 目标底稿顶部显示「← 返回 X 第 N 行」面包屑
  - [x] 11.4 复用 initGlobalBackspace 支持 Backspace 键返回

- [x] 12. 渲染模式手动切换（US-11）
  - [x] 12.1 工具栏增加「切换渲染模式」按钮（仅 A/B/D/E 类显示）
  - [x] 12.2 切换后写入 project_workpaper_sheet_override 表
  - [x] 12.3 下次打开自动使用上次选择的模式

- [x] 13. 离线暂存 + 弱网恢复（US-12）
  - [x] 13.1 新建 `useWpOfflineCache` composable（localStorage 暂存）
  - [x] 13.2 auto-save 失败时自动暂存 + 底稿列表橙色圆点标记
  - [x] 13.3 恢复网络后自动重试 + 冲突检测弹窗
  - [x] 13.4 localStorage 上限 50MB 超出提示

- [x] 14. 首次使用引导（US-13）
  - [x] 14.1 A 类程序表增加 el-tour 3 步引导
  - [x] 14.2 localStorage 记录已看过不重复显示
  - [x] 14.3 工具栏「?」按钮可重新触发引导

- [x] 15. 底稿模板导出 → 线下填写 → 导入（US-14，核心离线协作）
  - [x] 15.1 新建 `backend/app/services/wp_offline_export_service.py`：导出填写模板 xlsx
  - [x] 15.2 实现注意事项 sheet 生成（7 节内容 + 项目元数据填充）
  - [x] 15.3 实现 cell 颜色标记（黄=可填 / 灰=公式 / 红=禁改 / 绿=必填）+ sheet 保护
  - [x] 15.4 实现 _meta_ sheet 生成（hidden + base64+gzip + sha256 checksum）
  - [x] 15.5 实现可选 AES 加密（Fernet，复用附注模块 `note_offline_export_service` 模式）
  - [x] 15.6 新建 `backend/app/services/wp_offline_import_service.py`：验证 + diff + apply
  - [x] 15.7 实现 validate_and_diff：_meta_ 校验 + 逐 cell 对比 + 分类（changed/added/deleted）
  - [x] 15.8 实现 apply_import：3 种冲突策略（overwrite/keep_system/merge）+ 审计日志
  - [x] 15.9 新建 `backend/app/routers/wp_offline.py`：3 端点（export-template / import-preview / import-apply）
  - [x] 15.10 注册到 router_registry/workpaper.py
  - [x] 15.11 前端 `WpOfflineExportDialog.vue`：sheet 选择 + 加密选项 + 截止日期 + 联系人
  - [x] 15.12 前端 `WpOfflineImportDialog.vue`：4 步流程（上传→验证→diff 预览→确认导入）
  - [x] 15.13 WorkpaperEditor 工具栏增加「📤 导出填写模板」+「📥 导入填写结果」按钮
  - [x] 15.14 导出文件 30 天归档 + 审计日志
  - [x] 15.15 pytest 测试：导出→导入 round-trip PBT（hypothesis 生成随机填写数据验证 diff 正确性）

- [x] 16. HTML 底稿自动刷数 + 全链路跳转（US-15，核心体验）
  - [x] 16.1 后端 render-config 端点增强：批量解析 cross_refs 中 source 标记的 cell 取值
  - [x] 16.2 新增 `_resolve_auto_fill_values` 函数：从 TB/WP/REPORT 批量取数（≤200ms）
  - [x] 16.3 返回 fill_results 含 value + source + label + status（ok/unavailable）
  - [x] 16.4 前端 auto-fill cell 渲染：tooltip 显示来源 + 不可用时红色虚线框
  - [x] 16.5 保存后自动刷新取数值（cross_ref_service.detect_changes 触发）
  - [x] 16.6 确保所有 GtIndexChip 100% 覆盖（A/B/C/D/E 类所有索引号字段）
  - [x] 16.7 跳转目标不存在时灰显 + tooltip 提示原因

- [x] 17. 程序表流程导航图（US-16，可视化增强）
  - [x] 17.1 新建 `GtAuditFlowGraph.vue`：4 层横向流程图（目标→风险→程序→底稿）
  - [x] 17.2 后端新增 `GET /api/workpapers/{wp_id}/audit-flow-graph` 端点
  - [x] 17.3 从 schema.assertions + risk_assessment + programs + linked_workpapers 组装图数据
  - [x] 17.4 节点颜色反映状态（绿=完成 / 黄=进行中 / 灰=待执行 / 红=已裁剪）
  - [x] 17.5 节点可点击：风险→跳转风险底稿 / 程序→滚动到表格行 / 底稿→跳转编辑器
  - [x] 17.6 SVG 连线层渲染 edges（轻量实现，不引入重型图表库）
  - [x] 17.7 GtAProgramConsole 顶部增加「🗺️ 审计逻辑图」折叠按钮
  - [x] 17.8 新建 `GtBArchitectureTree.vue`：B 类目录的底稿架构树（el-tree + GtIndexChip）
  - [x] 17.9 GtBIndex 顶部增加「🏗️ 底稿架构」折叠按钮
