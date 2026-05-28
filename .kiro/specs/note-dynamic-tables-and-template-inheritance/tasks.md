# 附注模块全维度增强 — 任务列表

> 版本：v0.6.2（2026-05-28，新增 D15 离线分发）
> **重心调整**：用户原话「主要是修复单体附注模块，合并附注模块内容是连带完成」「支持国企版和上市版的丝滑切换」「最好要支持用户的离线处理 / 人机互补」
> 151 验收 / **38.5 人天** + 外部 5 人天 / **3 Phase / 17 Sprint**
> 关联：requirements.md / design.md
> 原则：能不写死就不写死，全部支持动态调整
>
> **v0.6 关键变更**：
> 1. **Phase 化重组** — Phase 1（单体附注修复）/ Phase 2（合并附注完整 + 联动）/ Phase 3（高级特性 + 收尾）
> 2. **D14 国企↔上市丝滑切换独立成 Sprint A.5**
>
> **v0.6.1 修复**：Sprint A.5 工作量 2 → 2.5 人天（16 子任务对齐）；总工作量 36 → 36.5 人天
>
> **v0.6.2 新增**：D15 离线分发独立成 **Sprint C.0**（Phase 3，2 人天，23 子任务）；总 36.5 → 38.5 人天 / 16 → 17 Sprint
> 2. **新增 D14：国企↔上市丝滑切换**（含同项目年内切换、集团内子公司不同模板共存、互转无丢失）
> 3. **依赖关系修正** — Sprint 顺序按依赖图调整（合并汇总服务先于合并附注完整）
> 4. **单体↔合并联动 5 项前置条件** 明示

## 前置（外部依赖，5 人天）

- [ ] **P-1** 审计师标注 60+ 章节动态区域（行+列，1 人天）
- [ ] **P-2** 审计师标注 30+ 章节 wp_data 绑定（1 人天）
- [ ] **P-3** 审计师标注 20+ 段落 Jinja 模板（0.5 人天）
- [ ] **P-4** 致同 PDF 视觉基线（0.5 人天）
- [ ] **P-5** 审计师标注 150+ 章节合并↔单体映射 + 抵销规则（1.5 人天）
  - 输出：`backend/data/note_consol_section_mapping.csv`
- [ ] **P-6** 审计师确认 173 章节层级编号方案（0.5 人天）
  - 输出：`backend/data/note_section_levels.csv`
- [ ] **P-7** 审计师确认国企↔上市差异清单（v0.6 新增，并入 P-1）
  - 章节集差异（约 14 章节 ± 10 格式不同）
  - 输出：`backend/data/note_soe_listed_diff.json`

---

# Phase 1：单体附注核心修复（17 人天，主线）

> 用户原话「**主要是修复单体附注模块**」。Phase 1 完成后，单体附注 173 章节可独立运行（动态/wp_data/Jinja/序号/国企↔上市切换全部就绪）。

## Sprint A.0：D13 章节序号重构（基础，1.5 人天）⚠ 必须最先做

- [ ] **A.0.1** V019 migration（原计划 V022，因 V001-V018 已落地按真实下一编号）：DisclosureNote 加 section_id / level / parent_section_id / sort_index / auto_numbering / lock_number / locked_number 字段
- [x] **A.0.2** 模板 JSON 字段重构（保留 section_number 作为兼容字段）
- [x] **A.0.3** `note_section_numbering_service.py` 核心
- [x] **A.0.4** 5 级编号格式注册器（一/(一)/1./(1)/①）
- [x] **A.0.5** `migrate_section_number_to_section_id.py` 一次性迁移脚本
- [x] **A.0.6** Jinja `ref()` 函数（内部引用自动跟随）
- [x] **A.0.7** 单元测试 25 用例（含 scope 切换 / 锁定 / 拖拽 / 重排 / 多层级）
- [x] **A.0.8** 历史 173 章节迁移落库（首汽租车 + 重庆和平药房 双项目验证）
- [x] **A.0.9** 验收（CI-18/CI-19 + ADR-019/020）

## Sprint A.1：数据模型 + Migration（2 人天）

- [x] **A.1.1** row_type/列 sidecar 模型
- [x] **A.1.2** binding 多源 fallback 模型
- [x] **A.1.3** is_empty / lineage / is_local_override / text_template_vars 字段
- [x] **A.1.4** group_note_template_baseline 表 V020
- [x] **A.1.5** note_section_version_tree 表 V021
- [x] **A.1.6** 验收（CI-1/CI-2/CI-3）

## Sprint A.2：动态行/列引擎 + wp_data（2.5 人天）

- [x] **A.2.1** _expand_dynamic_regions 行展开
- [x] **A.2.2** _expand_dynamic_columns 列展开 + 合并表头处理
- [x] **A.2.3** aux_balance 行 explode
- [x] **A.2.4** **wp_data _extract_wp_table / _extract_wp_cell / _extract_wp_column_sum**（核心）
- [x] **A.2.5** 多源 fallback 链（CI-9/CI-10）
- [x] **A.2.6** _cell_provenance 记录
- [x] **A.2.7** 动态行 label 自动填充
- [x] **A.2.8** 合计公式自动适配
- [x] **A.2.9** note_cell_merge 行+列三态合并 PBT
- [x] **A.2.10** is_empty 计算
- [x] **A.2.11** 验收

## Sprint A.3：公式 + auto_trim v2（1 人天）

- [x] **A.3.1** REGION + WP 公式函数完善
- [x] **A.3.2** PRIOR 跨年动态匹配
- [x] **A.3.3** auto_trim_v2 三级裁剪（章节+表格+段落，CI-8）
- [x] **A.3.4** 验收

## Sprint A.4：文字段落 Jinja（1.5 人天）

- [x] **A.4.1** note_text_template_engine.py（Jinja env + filter format_amount/cn_number/date_cn）
- [x] **A.4.2** _render_text_paragraph 接入
- [x] **A.4.3** 段落变量自动收集（wizard_state + client master + consolidation + prior_notes）
- [x] **A.4.4** 段落 Word 渲染
- [ ] **A.4.5** 模板 P-3 入库
- [x] **A.4.6** CI-11 必有变量声明
- [x] **A.4.7** 单测 18 用例

## Sprint A.5：D14 国企↔上市丝滑切换（v0.6 新增⭐⭐⭐，2.5 人天）

> 用户原话「集团下会有上市公司，二者模板不同」。这是 Phase 1 闭环的关键。

### 14.1 同项目年内切换（已有 note_conversion_service 升级）

- [x] **A.5.1** 改造 `note_conversion_service.py` 接入 D13 section_id（不依赖 section_number 字符串）
- [x] **A.5.2** 互转无数据丢失保证：用户编辑过的 cells（`_cell_modes[i]==manual`）必须保留
- [x] **A.5.3** 互转预览：显示「将新增 X 章节、删除 Y 章节、保留 Z 章节」+ 「N 个用户编辑会被保留」+ 「M 个章节因目标版无对应将归档」
- [x] **A.5.4** 章节差异表加载：从 P-7 输出 `note_soe_listed_diff.json` 加载映射

### 14.2 集团内子公司不同模板共存

- [x] **A.5.5** 子公司项目 template_type 独立存储（已有 `Project.template_type`，确认 ORM）
- [x] **A.5.6** 合并项目模板由 partner 锁定（不跟随子公司变更，避免误改）
- [x] **A.5.7** 集团基线（D6）按 template_type 区分（同集团可有 SOE 基线 + Listed 基线两套）
- [x] **A.5.8** child apply baseline 时检查 template_type 一致（不一致弹警告 + 自动转换）

### 14.3 模板差异管理

- [x] **A.5.9** `note_template_diff.py` 服务：加载 SOE/Listed 双模板，diff 输出章节级 + 表格级 + 字段级差异
- [x] **A.5.10** 章节级映射规则：
  - 共有章节（150+）— 直接复制 cells
  - SOE 独有 → Listed：用户决定保留/丢弃
  - Listed 独有 → SOE：用户决定保留/丢弃（带数据归档）
  - 格式略不同（~10）— 列映射 + 字段映射
- [x] **A.5.11** 差异表样自动适配（如固定资产 SOE movement → Listed category_sum 列重映射）

### 14.4 前端切换 UI

- [ ] **A.5.12** DisclosureEditor 顶部「准则」切换器（国企版 ⇆ 上市版）
- [ ] **A.5.13** 切换前确认弹窗：显示影响章节数 + 用户编辑保留情况
- [ ] **A.5.14** 切换中进度条 + 切换后 toast 「已切换为 XX 版，保留 N 处用户编辑」
- [x] **A.5.15** 单测 12 用例（PBT round-trip：SOE → Listed → SOE 数据无丢失）

### 14.5 验收

- [x] **A.5.16** Sprint A.5 验收（CI-20 模板互转 round-trip 无丢失 PBT）

## Sprint A.6：协作锁集成 D9（0.5 人天）

- [x] **A.6.1** 4 入口集成 NoteSectionLockService（动态行/列/基线/auto_trim/切换）
- [ ] **A.6.2** 前端章节列表锁可视化
- [ ] **A.6.3** 锁冲突弹窗 + 抢占
- [x] **A.6.4** 验收（CI-13）

## Sprint A.7：集团模板继承（2.5 人天）

- [ ] **A.7.1** group_note_baseline_service.py（save/apply/diff/sync）
- [ ] **A.7.2** 多层级 lineage（parent_baseline_id 链）
- [ ] **A.7.3** apply_group_baseline 复制文字+表样+vars
- [ ] **A.7.4** local_override 标记
- [ ] **A.7.5** 基线版本管理 v{major}.{minor}
- [ ] **A.7.6** 基线升级通知
- [ ] **A.7.7** 多 child 批量同步
- [ ] **A.7.8** child 反哺基线建议
- [ ] **A.7.9** 新 router group_note_baseline.py（5 端点）
- [ ] **A.7.10** **template_type 一致性检查（与 D14 联动）**
- [ ] **A.7.11** 验收（CI-7）

## Sprint A.8：Phase 1 单体附注 UAT（1 人天）

- [ ] **A.8.1** 60+ 章节 _dynamic_regions 入库
- [ ] **A.8.2** 30+ 章节 wp_data binding 入库
- [ ] **A.8.3** 20+ 段落 Jinja 模板入库
- [ ] **A.8.4** 173 章节 section_id 化验证
- [ ] **A.8.5** UAT 全链路（首汽租车_2025 SOE + 重庆和平药房_2025 SOE）
  - 行/列动态加删
  - wp_data 取数（H/G/J/L/D/K/M）
  - fallback 链触发
  - Jinja 段落变量预览
  - 集团基线 apply
  - **国企↔上市切换（章节差异 + 用户编辑保留）**
  - 章节序号实时渲染（拖拽/裁剪/锁定）
  - Word 导出
- [ ] **A.8.6** UAT 报告 `docs/uat/note-phase1-uat-{date}.md`

---

# Phase 2：合并附注完整开发 + 联动（10 人天，连带 Phase 1 后跑通）

> 用户原话「合并附注模块内容是连带完成先，不然无法准确联动的」。Phase 2 严格依赖 Phase 1 完成。
> **5 项前置条件**（任一缺失合并附注无法准确联动）：
> 1. ✅ 子公司项目单体附注已生成（依赖 Phase 1）
> 2. ✅ 合并项目 `parent_project_id` 链已建（已有，consol_tree_service）
> 3. ✅ 章节映射 P-5 已标注
> 4. ✅ 抵销规则已配置
> 5. ✅ 序号方案 P-6 已确认（依赖 Sprint A.0）

## Sprint B.0：D12 合并↔单体映射核心服务（2 人天）

⚠ **必须先于 Sprint B.1**（Sprint B.1 调用此 Service）

- [ ] **B.0.1** binding 新 source 类型 `consol_aggregation` 定义 + 单测
- [ ] **B.0.2** `consol_note_aggregation_service.py` 新建（5 种 aggregation_method）
  - simple_sum / sum_after_elimination / top_n_after_elimination / weighted_avg / first_n_concat
- [ ] **B.0.3** `consol_elimination_rules.py` 抵销规则注册器
  - internal_ar / internal_revenue / internal_inventory_unrealized / internal_dividend
- [ ] **B.0.4** 模糊合并同名算法（label_fuzzy 阈值 0.85）
- [ ] **B.0.5** 多层合并 lineage 链（孙合并 → 子合并 → 总合并）
- [ ] **B.0.6** 子公司单体附注更新事件 → 合并 stale（EventBus 集成）
- [ ] **B.0.7** 模板 P-5 输出（150+ 章节映射）入库
- [ ] **B.0.8** 「重新汇总」端点 + 进度 SSE
- [ ] **B.0.9** 单测 + PBT
- [ ] **B.0.10** 验收（CI-15/CI-16/CI-17 + ADR-017/018）

## Sprint B.1：合并附注完整开发 D8（3.5 人天）

⭐ **核心价值**：从「7 个合并专用章节」→「173+7=180 完整章节，全部从子公司单体附注汇总」

### B.1.A 后端服务改造

- [ ] **B.1.1** 改造 ConsolDisclosureService 为 V2（`generate_full_consol_notes`）
- [ ] **B.1.2** `_aggregate_common_section` 调 ConsolNoteAggregationService（依赖 Sprint B.0）
- [ ] **B.1.3** 子公司清单实时拉取（用 consol_tree_service.build_tree）
- [ ] **B.1.4** 抵销前后双列
- [ ] **B.1.5** 商誉/MI/外币 章节绑 H/G/M wp_data
- [ ] **B.1.6** 多层合并 lineage（孙合并 → 子合并 → 总合并）
- [ ] **B.1.7** 文字段落合并版 vars（subsidiary_count / consolidated_revenue 等，依赖 D7）
- [ ] **B.1.8** 章节序号按 scope='consolidated' 重排（依赖 D13/Sprint A.0）
- [ ] **B.1.9** 7 个合并专用章节用 wp_data 强化（取代写死字符串）
- [ ] **B.1.10** 合并范围变化事件 → 自动 stale（CONSOL_SUBSIDIARY_CHANGED 事件）

### B.1.B 前端 ConsolNoteTab 升级

- [ ] **B.1.11** 章节树 180 章节 + 「来自 N 家子公司」标识
- [ ] **B.1.12** ConsolCellProvenanceDialog（cell 溯源到子公司贡献）
- [ ] **B.1.13** 「重新汇总」按钮 + 进度 SSE
- [ ] **B.1.14** 多层合并 lineage 可视化（孙→子→总）
- [ ] **B.1.15** **合并附注顶部准则切换器**（合并项目下显示当前合并版准则，partner 可锁/解锁）

### B.1.C 验收

- [ ] **B.1.16** Sprint B.1 验收（CI-12 + Playwright UAT 1 个合并项目）

## Sprint B.2：D14 集团内多模板共存联动（v0.6 新增，1 人天）

> 集团内子公司可能 SOE，子公司可能 Listed，合并附注汇总时需要对齐

- [ ] **B.2.1** 子公司不同模板的章节映射兼容（SOE 子公司 → Listed 合并 / 反之）
- [ ] **B.2.2** 跨模板汇总时章节差异处理：
  - 共有章节 — 直接汇总
  - 子公司有 / 合并版无 — 数据归档不丢
  - 合并版有 / 子公司无 — 标 not_applicable + UI 提示
- [ ] **B.2.3** 合并 cell provenance 标识子公司模板（「来自 SOE 子公司 A 100w + Listed 子公司 B 50w」）
- [ ] **B.2.4** 单测 6 用例（含跨模板汇总 PBT）
- [ ] **B.2.5** 验收

## Sprint B.3：Phase 2 合并附注 UAT（1 人天）

- [ ] **B.3.1** 1 个合并项目 demo（首汽租车_2025 + 重庆和平药房_2025 → 模拟集团合并）
- [ ] **B.3.2** UAT 全链路
  - 子公司单体附注先生成
  - 触发合并附注生成（180 章节）
  - 抽样 5 章节验证数字 = 子公司汇总 - 内部抵销
  - cell 溯源点击验证
  - 子公司单体附注修改 → 合并附注 stale 标记
  - 「重新汇总」触发 + 进度
  - **跨模板共存验证**（一家子公司改 Listed 看汇总）
  - Word 导出
- [ ] **B.3.3** UAT 报告 `docs/uat/note-phase2-consol-uat-{date}.md`

---

# Phase 3：高级特性 + 收尾（11 人天）

## Sprint C.0：D15 离线分发与一键导入（v0.6.2 新增⭐⭐ 人机互补，2 人天）

> 用户原话「最好要支持用户的离线处理，比如导出所有的附注模板或部分附注科目模板，用户分发给其他项目组成员，成员在模板上编辑处理好后，在支持一键导入功能」「这个功能全面体现了人机互补的作用」。

### 15.1 后端导出服务

- [ ] **C.0.1** `note_offline_export_service.py` 服务（按 section_id list 选择章节子集）
- [ ] **C.0.2** xlsx 包结构生成：注意事项 sheet + 章节清单 sheet + N 章节 sheet + 隐藏 _meta_ sheet
- [ ] **C.0.3** 单元格 4 色语义渲染（黄=可填 / 灰=公式 / 红=锁定 / 绿=必填）+ DataValidation 锁定
- [ ] **C.0.4** 单元格批注 = 公式说明 + wp_code/试算账号 数据源
- [ ] **C.0.5** _meta_ sheet 存 binding/formula/row_meta JSON（base64+gzip 压缩）
- [ ] **C.0.6** 注意事项 sheet 模板（6 节使用说明 + partner 联系人占位符）
- [ ] **C.0.7** 章节清单 TOC（含完成度 / 必填 / section_id 隐藏列）
- [ ] **C.0.8** 可选 AES 加密 + 文件 hash 记录

### 15.2 后端导入服务

- [ ] **C.0.9** `note_offline_import_service.py` 解压 + 校验 _meta_ sheet 存在
- [ ] **C.0.10** 按 section_id 匹配现有章节（命中 / 缺失 / 系统多余 三态）
- [ ] **C.0.11** 字段级 diff 算法（值 / 公式 / manual 三类字段）
- [ ] **C.0.12** 章节级冲突选择（覆盖 / 保留 / 合并 / 丢弃）
- [ ] **C.0.13** 与 D9 协作锁集成（导入前自动获章节锁）
- [ ] **C.0.14** 与 D11 版本树集成（导入触发新版本节点）
- [ ] **C.0.15** 与 D14 template_type 校验（不一致弹警告）
- [ ] **C.0.16** 审计日志 + 文件 30 天归档 + 可回滚

### 15.3 前端 UI

- [ ] **C.0.17** 「导出附注」按钮 + 章节多选树 + 导出选项弹窗
- [ ] **C.0.18** 「一键导入」按钮 + 文件上传
- [ ] **C.0.19** 字段级 diff 预览（章节维度 + cell 级 add/remove/modify 高亮）
- [ ] **C.0.20** 章节冲突选择 UI（4 选项 + cell 级勾选）
- [ ] **C.0.21** 导入进度 SSE + 完成 toast「N 章节导入 / M 处保留 / K 处冲突」

### 15.4 验收

- [ ] **C.0.22** 单测 + PBT（CI-21/CI-22 导出→导入 round-trip 无丢失）
- [ ] **C.0.23** Sprint C.0 验收 UAT（partner 导出 60 章节 → 模拟成员填写 → 一键导回 + diff 预览）

## Sprint C.1：AI 辅助 D10（1 人天）

- [ ] **C.1.1** suggest_dynamic_rows
- [ ] **C.1.2** generate_paragraph_from_workpaper
- [ ] **C.1.3** check_wp_tb_consistency
- [ ] **C.1.4** 前端 AI 建议侧栏
- [ ] **C.1.5** 单测 + UAT

## Sprint C.2：章节版本图 D11（1.5 人天）

- [ ] **C.2.1** note_section_version_tree_service.py（fork/merge/diff）
- [ ] **C.2.2** 跨年合并范围变化高亮
- [ ] **C.2.3** 章节 fork
- [ ] **C.2.4** 多版本 merge
- [ ] **C.2.5** 前端版本树可视化
- [ ] **C.2.6** 验收（CI-14）

## Sprint C.3：前端编辑器全维度 UI（3 人天）

- [ ] **C.3.1** 9 个 composable（含 useNoteAggregation / useNoteSectionNumbering / useNoteTemplateConversion）
- [ ] **C.3.2** NoteTableEditor.vue 动态行视觉
- [ ] **C.3.3** 动态列视觉 + 拖动调宽 + 合并表头 + 冻结列
- [ ] **C.3.4** 「+ 添加明细行/列」按钮
- [ ] **C.3.5** 删除右键 + 公式栏多源选项 + 数据源 chip
- [ ] **C.3.6** 集团基线对话框 + 版本对比 + diff
- [ ] **C.3.7** 段落变量编辑器 + 实时预览
- [ ] **C.3.8** 协作锁可视化
- [ ] **C.3.9** AI 建议侧栏
- [ ] **C.3.10** 上年对比侧栏 + 章节版本树
- [ ] **C.3.11** 章节序号实时渲染（D13）
- [ ] **C.3.12** 单体↔合并切换 + 章节序号自动重算
- [ ] **C.3.13** 章节树拖拽排序
- [ ] **C.3.14** **国企↔上市切换器**（顶部工具栏，含切换前预览）
- [ ] **C.3.15** vue-tsc + vitest 通过
- [ ] **C.3.16** Playwright 实测全链路

## Sprint C.4：Word 导出（1.5 人天）

- [ ] **C.4.1** GTNoteDynamicRow / GTNoteDynamicCol 样式
- [ ] **C.4.2** 合并表头 docx 渲染
- [ ] **C.4.3** 空表替换 + 空章节跳过 + 不适用提示
- [ ] **C.4.4** Jinja 段落 Word 输出
- [ ] **C.4.5** 合并附注 180 章节 + 抵销双列 Word 表
- [ ] **C.4.6** 27 项视觉断言
- [ ] **C.4.7** 多公司基线对比 PDF 工具
- [ ] **C.4.8** Word TOC 使用 D13 最新序号
- [ ] **C.4.9** Word 内部引用 ref() 渲染最终序号
- [ ] **C.4.10** 验收

## Sprint C.5：收尾（1 人天）

- [ ] **C.5.1** 全量回归（不破坏现有 173 章节）
- [ ] **C.5.2** memory.md 沉淀（14 维度铁律 + Phase 1/2/3 完成度）
- [ ] **C.5.3** ADR-011~ADR-022 全部撰写（v0.6 新增 ADR-021 国企↔上市切换 / v0.6.2 新增 ADR-022 离线分发） + INDEX.md
- [ ] **C.5.4** v2 backlog：跨章节联动 / fork-merge / AI 全自动撰写 / 多语言序号

## Sprint C.6：Phase 3 综合 UAT（1 人天）

- [ ] **C.6.1** 全量综合 UAT（合并 + 单体 + 上市 + 国企）
- [ ] **C.6.2** 性能基准（173 章节 < 12s / 集团基线 apply < 3s / 切换 < 1s）
- [ ] **C.6.3** UAT 报告 `docs/uat/note-final-uat-{date}.md`

---

## CI 卡点汇总（22 项，v0.6 新增 CI-20 / v0.6.2 新增 CI-21+CI-22）

| ID | 描述 | Sprint |
|----|------|--------|
| CI-1 | _dynamic_regions idx/col_id 有效 | A.1 |
| CI-2 | row_type=dynamic_* 在 region 内 | A.1 |
| CI-3 | column_id 全表唯一 | A.1 |
| CI-4 | REGION/WP 解析 | A.3 |
| CI-5 | 动态删除合计 PBT | A.2 |
| CI-6 | round-trip PBT | A.8 |
| CI-7 | apply_baseline lineage | A.7 |
| CI-8 | auto_trim v2 三级互斥 | A.3 |
| CI-9 | fallback 链 ≤ 3 级 | A.2 |
| CI-10 | _cell_provenance 必有 source | A.2 |
| CI-11 | Jinja 模板必有变量声明 | A.4 |
| CI-12 | 合并章节序号不冲突 | B.1 |
| CI-13 | 锁释放必触发 | A.6 |
| CI-14 | 版本树无环（DAG） | C.2 |
| CI-15 | consol_aggregation 必有 child_section_id | B.0 |
| CI-16 | 多层合并 lineage 链无环 | B.0 |
| CI-17 | elimination_rules 引用 wp_code 必存在 | B.0 |
| CI-18 | section_id 唯一 + level 1-5 + parent 引用有效 | A.0 |
| CI-19 | rendered_number 在 scope 内唯一 | A.0 |
| **CI-20** | **国企↔上市互转 round-trip 无丢失 PBT** | **A.5** |
| **CI-21** | **离线包 _meta_ sheet 必有 section_id + binding hash** | **C.0** |
| **CI-22** | **导出→导入 round-trip 字段级 diff 无丢失 PBT** | **C.0** |

## 任务依赖图（v0.6 Phase 化）

```
P-1~P-7 (外部，5 人天)
        ↓
┌────────────────── Phase 1：单体附注核心修复（17 人天）──────────────────┐
│                                                                          │
│  Sprint A.0 (D13 序号重构) ⚠ 必须最先做                                  │
│         ↓                                                                │
│  Sprint A.1 (数据模型) → A.2 (引擎+wp_data) → A.3 (公式+trim)             │
│                                  ↓                                       │
│                         A.4 (Jinja，集成 ref())                          │
│                                  ↓                                       │
│                         A.5 (国企↔上市切换 D14) ⭐⭐⭐                  │
│                                  ↓                                       │
│                         A.6 (锁) → A.7 (集团基线) → A.8 (Phase 1 UAT)    │
└──────────────────────────────────────────────────────────────────────────┘
        ↓
┌────────────────── Phase 2：合并附注完整 + 联动（10 人天）─────────────┐
│                                                                       │
│  Sprint B.0 (D12 合并汇总服务) ⚠ 必须先于 B.1                          │
│         ↓                                                             │
│  Sprint B.1 (合并附注完整 D8 + 前端 ConsolNoteTab 升级)                │
│         ↓                                                             │
│  Sprint B.2 (集团内多模板共存联动)                                     │
│         ↓                                                             │
│  Sprint B.3 (Phase 2 合并附注 UAT)                                    │
└───────────────────────────────────────────────────────────────────────┘
        ↓
┌────────────────── Phase 3：高级特性 + 收尾（11 人天）─────────────────┐
│                                                                      │
│  C.0 (D15 离线分发) → C.1 (AI) → C.2 (版本图) → C.3 (前端全维度)      │
│                    → C.4 (Word) → C.5 (收尾) → C.6 (综合 UAT)        │
└──────────────────────────────────────────────────────────────────────┘
```

## 风险登记册（v0.6 增量）

| 风险 | 影响 | 缓解 |
|------|------|------|
| section_id 迁移 173 章节出错 | 数据丢失 | 一次性迁移 + 回滚脚本 + note_section_legacy 兼容字段 |
| 多层合并汇总数据量大 | 性能 | 子公司清单 + 章节数据 Redis 缓存 60s |
| 抵销规则配置错误 | 合并金额错 | 「重新汇总」前预览 diff + partner 确认 |
| 章节序号锁定与重排冲突 | 序号断号 | lock_number 标记互斥校验 |
| **国企↔上市切换数据丢失** | **用户编辑被覆盖** | **CI-20 PBT round-trip + 切换前预览影响章节数** |
| **集团内子公司模板不一致** | **合并汇总错位** | **跨模板章节映射 + 数据归档不丢 + UI 警告** |
| **Phase 2 启动早于 Phase 1 完成** | **合并附注无数据可汇总** | **Sprint A.8 UAT 通过为 Phase 2 启动门槛** |
| AI 建议错误 | 误导 | 仅"建议"不"自动应用"，用户必须确认 |
| 多源 fallback 慢 | 性能下降 | 并发解析 + 缓存 |
| Jinja 模板缺变量 | 段落 undefined | strict mode + CI-11 + fallback |
| 38.5 人天工作量 | 延期 | 17 Sprint 拆分 + Phase 化分批上线 |

## v0.6 关键设计决策汇总

### 决策 1：单体优先 + 合并连带

Phase 1 完成后，单体附注 173 章节可独立工作。Phase 2 合并附注严格依赖 Phase 1（5 项前置条件），不可并行启动。

### 决策 2：国企↔上市丝滑切换独立成 Sprint A.5

新增 D14 维度 + ADR-021。切换语义包含：
- **同项目年内切换**（业主在中途调整准则）
- **集团内子公司不同模板共存**（子 A SOE，子 B Listed，合并按需）
- **互转无数据丢失**（用户编辑保留 PBT）

### 决策 3：Sprint 编号 Phase 化

`Phase 1 / Sprint A.0~A.8` `Phase 2 / Sprint B.0~B.3` `Phase 3 / Sprint C.1~C.6`，按依赖顺序排，调整不影响其他 Sprint 编号。

### 决策 4：Sprint B.0 必须先于 B.1

合并附注完整服务（B.1）依赖合并汇总服务（B.0），严格顺序。

### 决策 5：Sprint A.8 通过 = Phase 2 启动门槛

不让 Phase 2 在 Phase 1 单体未通过时启动，避免汇总无数据可用。
