# 附注模块全维度增强 — 任务列表

> 版本：v0.5（草稿，2026-05-28）
> 126 验收 / **34 人天** + 外部 5 人天 / **15 Sprint**（Sprint 6 升级 + Sprint 13 配套加强）
> 关联：requirements.md / design.md
> 原则：能不写死就不写死，全部支持动态调整
> v0.5 关键变更：D8 「合并附注衔接」升级为「合并附注完整开发」，Sprint 6 工作量从 1.5 → 3.5 人天

## 前置（外部依赖，5 人天）

- [ ] **P-1** 审计师标注 60+ 章节动态区域（行+列，1 人天）
- [ ] **P-2** 审计师标注 30+ 章节 wp_data 绑定（1 人天）
- [ ] **P-3** 审计师标注 20+ 段落 Jinja 模板（0.5 人天）
- [ ] **P-4** 致同 PDF 视觉基线（0.5 人天）
- [ ] **P-5** 审计师标注 150+ 章节合并↔单体映射 + 抵销规则（1.5 人天，v0.4 ⭐）
  - 输出：`backend/data/note_consol_section_mapping.csv`
  - 列：consol_section_id, child_section_ids, aggregation_method, elimination_rules
- [ ] **P-6** 审计师确认 173 章节层级编号方案（0.5 人天，v0.4 ⭐）
  - 5 级标准 / 哪些自动 / 哪些 partner 锁定 / 表格标题层级
  - 输出：`backend/data/note_section_levels.csv`

## Sprint 0：D13 章节序号重构（基础，1.5 人天，I1-I15 + ADR-019/020）⚠ 优先级最高

- [ ] **0.1** V022 migration：DisclosureNote 加 section_id / level / parent_section_id / sort_index / auto_numbering / lock_number / locked_number 字段
- [ ] **0.2** 模板 JSON 字段重构（保留 section_number 作为兼容字段）
- [ ] **0.3** `note_section_numbering_service.py` 核心
- [ ] **0.4** 5 级编号格式注册器（cn_number / circled_number / 阿拉伯）
- [ ] **0.5** `migrate_section_number_to_section_id.py` 一次性迁移脚本
- [ ] **0.6** Jinja `ref()` 函数（内部引用自动跟随）
- [ ] **0.7** 单元测试 25 用例（含 scope 切换 / 锁定 / 拖拽 / 重排 / 多层级）
- [ ] **0.8** 历史 173 章节迁移落库（首汽租车 + 重庆和平药房 双项目验证）
- [ ] **0.9** Sprint 0 验收（CI-18/CI-19 + ADR-019/020）

## Sprint 1：数据模型 + Migration（2 人天，A1~A15）

- [ ] **1.1** row_type/列 sidecar 模型（A1-A5）
- [ ] **1.2** binding 多源 fallback 模型（A6-A8）
- [ ] **1.3** is_empty / lineage / is_local_override / text_template_vars 字段（A9-A12）
- [ ] **1.4** group_note_template_baseline 表 V019（A13）
- [ ] **1.5** note_section_version_tree 表 V020（A14）
- [ ] **1.6** Sprint 1 验收（CI-1/CI-2/CI-3/CI-14）

## Sprint 2：动态行/列引擎（2.5 人天，B1-B11）

- [ ] **2.1** _expand_dynamic_regions 行展开
- [ ] **2.2** _expand_dynamic_columns 列展开 + 合并表头处理
- [ ] **2.3** aux_balance 行 explode
- [ ] **2.4** wp_data _extract_wp_table / _extract_wp_cell / _extract_wp_column_sum（核心，单测 15 用例）
- [ ] **2.5** 多源 fallback 链 _resolve_with_fallback（CI-9/CI-10）
- [ ] **2.6** _cell_provenance 记录
- [ ] **2.7** 动态行 label 自动填充
- [ ] **2.8** 合计公式自动适配
- [ ] **2.9** update_note_values + note_cell_merge 行+列三态合并 PBT 6 不变量
- [ ] **2.10** is_empty 计算
- [ ] **2.11** Sprint 2 验收

## Sprint 3：公式 + auto_trim v2（1 人天）

- [ ] **3.1** REGION + WP 公式函数完善
- [ ] **3.2** PRIOR 跨年动态匹配
- [ ] **3.3** auto_trim_v2 三级裁剪（CI-8）
- [ ] **3.4** Sprint 3 验收

## Sprint 4：文字段落 Jinja（1.5 人天）

- [ ] **4.1** note_text_template_engine.py（Jinja env + filter format_amount/cn_number/date_cn）
- [ ] **4.2** _render_text_paragraph 接入
- [ ] **4.3** 段落变量自动收集
- [ ] **4.4** 段落 Word 渲染
- [ ] **4.5** 模板 P-3 入库
- [ ] **4.6** CI-11 必有变量声明
- [ ] **4.7** 单测 18 用例

## Sprint 5：集团模板继承（2.5 人天）

- [ ] **5.1** group_note_baseline_service.py（save/apply/diff/sync）
- [ ] **5.2** 多层级 lineage（parent_baseline_id 链）
- [ ] **5.3** apply_group_baseline 复制文字+表样+vars
- [ ] **5.4** local_override 标记
- [ ] **5.5** 基线版本管理 v{major}.{minor}
- [ ] **5.6** 基线升级通知
- [ ] **5.7** 多 child 批量同步
- [ ] **5.8** child 反哺基线建议
- [ ] **5.9** 新 router group_note_baseline.py（5 端点）
- [ ] **5.10** Sprint 5 验收（CI-7）

## Sprint 6：合并附注完整开发 D8（**3.5 人天 ⬆ v0.5 升级**）

⭐ **核心价值**：从「7 个合并专用章节」→「173+7=180 完整章节，全部从子公司单体附注汇总」

- [ ] **6.1** 改造 ConsolDisclosureService 为 V2（generate_full_consol_notes）
- [ ] **6.2** `_aggregate_common_section` 调 ConsolNoteAggregationService（依赖 Sprint 13）
- [ ] **6.3** 子公司清单实时拉取（用 consol_tree_service.build_tree）
- [ ] **6.4** 抵销前后双列
- [ ] **6.5** 商誉/MI/外币 章节绑 H/G/M wp_data
- [ ] **6.6** 多层合并 lineage（孙合并 → 子合并 → 总合并）
- [ ] **6.7** 文字段落合并版 vars（subsidiary_count / consolidated_revenue 等）
- [ ] **6.8** 章节序号按 scope='consolidated' 重排（依赖 D13/Sprint 0）
- [ ] **6.9** 7 个合并专用章节用 wp_data 强化（取代写死字符串）
- [ ] **6.10** 合并范围变化事件 → 自动 stale（CONSOL_SUBSIDIARY_CHANGED 事件）
- [ ] **6.11** 前端 ConsolNoteTab 升级（章节树 180 章节 + 「来自 N 家子公司」标识）
- [ ] **6.12** ConsolCellProvenanceDialog（cell 溯源到子公司贡献）
- [ ] **6.13** 「重新汇总」按钮 + 进度 SSE
- [ ] **6.14** 多层合并 lineage 可视化（孙→子→总）
- [ ] **6.15** Sprint 6 验收（CI-12 + Playwright UAT 1 个合并项目）

## Sprint 7：协作锁集成 D9（0.5 人天）

- [ ] **7.1** 4 入口集成 NoteSectionLockService
- [ ] **7.2** 前端章节列表锁可视化
- [ ] **7.3** 锁冲突弹窗 + 抢占
- [ ] **7.4** Sprint 7 验收（CI-13）

## Sprint 8：AI 辅助 D10（1 人天）

- [ ] **8.1** suggest_dynamic_rows
- [ ] **8.2** generate_paragraph_from_workpaper
- [ ] **8.3** check_wp_tb_consistency
- [ ] **8.4** 前端 AI 建议侧栏
- [ ] **8.5** 单测 + UAT

## Sprint 9：章节版本图 D11（1.5 人天）

- [ ] **9.1** note_section_version_tree_service.py（fork/merge/diff）
- [ ] **9.2** 跨年合并范围变化高亮
- [ ] **9.3** 章节 fork
- [ ] **9.4** 多版本 merge
- [ ] **9.5** 前端版本树可视化
- [ ] **9.6** Sprint 9 验收（CI-14）

## Sprint 10：前端编辑器（3 人天）

- [ ] **10.1** 8 个 composable 新建（含 useNoteAggregation / useNoteSectionNumbering）
- [ ] **10.2** NoteTableEditor.vue 动态行视觉
- [ ] **10.3** 动态列视觉 + 拖动调宽 + 合并表头 + 冻结列
- [ ] **10.4** 「+ 添加明细行/列」按钮
- [ ] **10.5** 删除右键 + 公式栏多源选项 + 数据源 chip
- [ ] **10.6** 集团基线对话框 + 版本对比 + diff
- [ ] **10.7** 段落变量编辑器 + 实时预览
- [ ] **10.8** 协作锁可视化
- [ ] **10.9** AI 建议侧栏
- [ ] **10.10** 上年对比侧栏 + 章节版本树
- [ ] **10.11** vue-tsc + vitest 通过
- [ ] **10.12** Playwright 实测全链路
- [ ] **10.13** 章节序号实时渲染（D13 集成）⭐
- [ ] **10.14** 单体↔合并切换按钮 + 章节序号自动重算 ⭐
- [ ] **10.15** 章节树拖拽排序 → 序号实时刷新 ⭐

## Sprint 11：Word 导出（1.5 人天）

- [ ] **11.1** GTNoteDynamicRow / GTNoteDynamicCol 样式
- [ ] **11.2** 合并表头 docx 渲染
- [ ] **11.3** 空表替换 + 空章节跳过 + 不适用提示
- [ ] **11.4** Jinja 段落 Word 输出
- [ ] **11.5** 合并附注独立章节集 + 抵销双列 Word 表
- [ ] **11.6** 27 项视觉断言
- [ ] **11.7** 多公司基线对比 PDF 工具
- [ ] **11.8** Sprint 11 验收
- [ ] **11.9** Word TOC 使用 D13 最新序号 ⭐
- [ ] **11.10** Word 内部引用 ref() 渲染最终序号 ⭐

## Sprint 12：模板数据 + UAT（2 人天）

- [ ] **12.1** generate_note_template_bindings.py 多扩展
- [ ] **12.2** 60+ 章节 _dynamic_regions 入库
- [ ] **12.3** 30+ 章节 wp_data binding 入库
- [ ] **12.4** 20+ 段落 Jinja 模板入库
- [ ] **12.5** 集团基线 demo
- [ ] **12.6** UAT 全链路（含 D12/D13）
- [ ] **12.7** UAT 报告

## Sprint 13：合并↔单体附注映射 D12（2 人天，H1-H12 + ADR-017/018）⭐ v0.4 新增

- [ ] **13.1** binding 新 source 类型 `consol_aggregation` 定义 + 单测
- [ ] **13.2** consol_note_aggregation_service.py 新建（5 种 aggregation_method）
- [ ] **13.3** consol_elimination_rules.py 抵销规则注册器
- [ ] **13.4** 模糊合并同名算法（label_fuzzy 阈值 0.85）
- [ ] **13.5** 多层合并 lineage 链（孙合并 → 子合并 → 总合并）
- [ ] **13.6** 子公司单体附注更新事件 → 合并 stale（EventBus 集成）
- [ ] **13.7** 「重新汇总」端点 + 进度 SSE
- [ ] **13.8** 合并 cell 溯源对话框（来自 N 家子公司）
- [ ] **13.9** 模板 P-5 输出（150+ 章节映射）入库
- [ ] **13.10** 1 个合并项目 demo（合并附注从 N 个子公司汇总）
- [ ] **13.11** 单测 + PBT
- [ ] **13.12** Sprint 13 验收（CI-15/CI-16/CI-17 + ADR-017/018）

## 收尾

- [ ] **F-1** 全量回归（不破坏现有 173 章节）
- [ ] **F-2** memory.md 沉淀（13 维度铁律）
- [ ] **F-3** ADR-011~ADR-020 全部撰写 + INDEX.md
- [ ] **F-4** v2 backlog：跨章节联动 / fork-merge / AI 全自动撰写 / 多语言序号

## CI 卡点汇总（19 项）

| ID | 描述 | Sprint |
|----|------|--------|
| CI-1 | _dynamic_regions idx/col_id 有效 | 1 |
| CI-2 | row_type=dynamic_* 在 region 内 | 1 |
| CI-3 | column_id 全表唯一 | 1 |
| CI-4 | REGION/WP 解析 | 3 |
| CI-5 | 动态删除合计 PBT | 2 |
| CI-6 | round-trip PBT | 12 |
| CI-7 | apply_baseline lineage | 5 |
| CI-8 | auto_trim v2 三级互斥 | 3 |
| CI-9 | fallback 链 ≤ 3 级 | 2 |
| CI-10 | _cell_provenance 必有 source | 2 |
| CI-11 | Jinja 模板必有变量声明 | 4 |
| CI-12 | 合并章节序号不冲突 | 6 |
| CI-13 | 锁释放必触发 | 7 |
| CI-14 | 版本树无环（DAG） | 9 |
| **CI-15** | **consol_aggregation 必有 child_section_id** | **13** |
| **CI-16** | **多层合并 lineage 链无环** | **13** |
| **CI-17** | **elimination_rules 引用 wp_code 必存在** | **13** |
| **CI-18** | **section_id 唯一 + level 1-5 + parent 引用有效** | **0** |
| **CI-19** | **rendered_number 在 scope 内唯一** | **0** |

## 任务依赖图（v0.4）

```
P-1/P-2/P-3/P-4/P-5/P-6 (外部)
        ↓
Sprint 0 (D13 序号重构) ← 优先级最高，影响后续所有 Sprint
        ↓
Sprint 1 (数据模型) → 2 (引擎) → 3 (公式+trim)
                              ├→ 4 (Jinja，集成 ref())
                              ├→ 5 (集团基线)
                              ├→ 6 (合并衔接)
                              ├→ 7 (锁)
                              ├→ 8 (AI)
                              ├→ 9 (版本图)
                              ├→ 10 (前端)
                              ├→ 11 (Word，含 TOC + ref 渲染)
                              └→ 13 (D12 合并↔单体) → 12 (UAT) → F
```

## 风险登记册（v0.4 增量）

| 风险 | 影响 | 缓解 |
|------|------|------|
| wp_data 跨循环格式不统一 | 取数失败 | 每循环 adapter，不通用化 |
| 集团基线误覆盖 | 数据丢失 | is_local_override + 预览 diff + 事务回滚 |
| 动态列影响其他章节 | 表样不一致 | column_id 仅 per-table |
| auto_trim v2 误剔 | 输出不全 | feature flag + 三级互斥 + 手工恢复 |
| Jinja 模板缺变量 | 段落 undefined | strict mode + CI-11 + fallback |
| 合并章节序号冲突 | 排序混乱 | uniq check + CI-12 |
| 锁未释放 | 章节锁死 | with 退出 + 5min 超时 |
| 版本树成环 | 死循环 | DAG CI-14 |
| AI 建议错误 | 误导 | 仅"建议"不"自动应用" |
| 多源 fallback 慢 | 性能下降 | 并发解析 + 缓存 |
| 子公司清单频繁查询 | 合并卡顿 | Redis 缓存 60s |
| **section_id 迁移 173 章节出错** | **数据丢失** | **一次性迁移 + 回滚脚本 + note_section_legacy 兼容字段** |
| **section_id 迁移影响下游引用** | **内部引用断** | **ref() fallback 到 section_title 模糊匹配** |
| **多层合并汇总数据量大** | **性能** | **子公司清单 + 章节数据 Redis 缓存 60s** |
| **抵销规则配置错误** | **合并金额错** | **「重新汇总」前预览 diff + partner 确认** |
| **章节序号锁定与重排冲突** | **序号断号** | **lock_number 标记互斥校验** |
| **拖拽排序更新慢** | **用户卡顿** | **序号计算只在 UI 端 + 保存时一次入库** |
| 30 人天工作量风险 | 延期 | 14 Sprint 拆分 + feature flag 渐进上线 |
