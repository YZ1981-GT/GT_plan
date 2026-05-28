# 附注模块动态表格 + 模板继承支持 — 任务列表

> 版本：v0.2（草稿，2026-05-28 大幅扩展）
> 53 验收 / 12.2 人天 + 外部 P-1/P-2/P-3 共 2.5 人天 / 7 Sprint
> 关联：requirements.md / design.md

## 前置（外部依赖，2.5 人天）

- [ ] **P-1** 审计师标注 60+ 章节动态区域（行 + 列，1 人天）
  - 输入：`附注模版/{soe,listed}*.md`
  - 输出：`backend/data/note_dynamic_regions_annotation.csv`
  - 列：section, region_name, axis(row|column), start_label, end_label, source, source_config_json
  - 优先级：应收账款前 5 名 / 子公司明细 / 借款明细 / 关联方清单 / 存货分类 / 应交税费 / 固定资产分类 / 应付职工薪酬 共 8 大类先做

- [ ] **P-2** 审计师标注 30+ 章节 wp_data 绑定（1 人天）
  - 输出：`backend/data/note_wp_data_bindings.csv`
  - 列：section, row_idx, col_id, wp_code, sheet, extract, label_col, value_cols_json
  - 覆盖 H/G/J/L/D/K/M 7 大循环主要底稿

- [ ] **P-3** 致同 PDF 视觉基线（0.5 人天）
  - 5 张实际致同附注 PDF（含动态行/列 + 空表替换样式）
  - 标注：动态行字号 / 列宽 / 「本期无此项业务」段落字号
  - 存放：`tests/fixtures/note_dynamic_baseline/*.png`

## Sprint 1：数据模型（1.5 人天，A1~A10）

- [ ] **1.1** row_type 枚举扩展 + is_dynamic 字段
  - 修改 `note_cell_merge.py` / `disclosure_engine.py` / 模板 JSON schema
  - 单测 8 用例

- [ ] **1.2** `_columns_meta` sidecar 模型
  - 新建 `backend/app/services/note_columns_meta.py`
  - 校验 column_id 唯一 + value_type 枚举
  - 单测 6 用例

- [ ] **1.3** `_dynamic_regions` sidecar 模型（行+列双 axis）
  - 新建 `backend/app/services/note_dynamic_regions.py`
  - 单测 10 用例

- [ ] **1.4** `note.is_empty` 计算 + `template_lineage` 字段
  - DisclosureNote ORM 加字段
  - V019 migration（`is_empty: bool` + `template_lineage: jsonb`）
  - 单测 4 用例

- [ ] **1.5** `group_note_template_baseline` 表创建
  - V020 migration
  - ORM model
  - 单测 6 用例

- [ ] **1.6** Sprint 1 验收（CI-1/CI-2/CI-3）
  - pytest 全绿
  - 单 commit

## Sprint 2：引擎核心（2.5 人天，B1~B10）

- [ ] **2.1** `_expand_dynamic_regions` 行展开
  - 单测 12 用例（含三模式 A/B/C）

- [ ] **2.2** `_expand_dynamic_columns` 列展开
  - 单测 8 用例

- [ ] **2.3** `aux_balance` 行 explode（已存在功能整合）
  - 单测 6 用例

- [ ] **2.4** **`wp_data` 数据源接入**（核心，含 _extract_wp_table / _extract_wp_cell / _extract_wp_column_sum）
  - 单测 15 用例（每种 extract 5 用例）

- [ ] **2.5** 动态行/列 label 自动填充
  - 单测 6 用例

- [ ] **2.6** 合计公式自动适配（SUM 范围动态）
  - 单测 8 用例

- [ ] **2.7** `is_empty` 计算（rows 全空 + text_content 空）
  - 单测 8 用例

- [ ] **2.8** Sprint 2 验收
  - 单 commit

## Sprint 3：合并与公式（1 人天，B7/B8/B13）

- [ ] **3.1** `note_cell_merge.merge_dynamic_table` 行+列三态合并
  - 按 (region_name, label) + column_id 双键匹配
  - hypothesis PBT 6 不变量

- [ ] **3.2** REGION + WP 公式函数完善
  - 单测 12 用例

- [ ] **3.3** PRIOR 跨年动态行/列匹配
  - 单测 6 用例

## Sprint 4：auto_trim v2 + 空内容剔除（0.7 人天，B9/B10/D4/D5）

- [ ] **4.1** `auto_trim_v2` 三级裁剪
  - section_pruned / table_pruned / paragraph_pruned 分类
  - 单测 10 用例

- [ ] **4.2** Word 导出空表替换段落「本期无此项业务」
  - GTNoteEmptyTablePlaceholder 样式
  - 单测 4 用例

- [ ] **4.3** Word 导出空章节跳过
  - 含 TOC 不显示空章节
  - 单测 4 用例

## Sprint 5：集团模板继承（2.5 人天，B11~B15 + E1~E5）

- [ ] **5.1** `group_note_baseline_service.py` 新建
  - `save_baseline(parent_project_id, name, version, template_type)`
  - `apply_group_baseline(child_project_id, baseline_id, year)`
  - 单测 12 用例

- [ ] **5.2** 基线版本管理（v1.0 / v1.1 / v2.0）
  - is_active 标记
  - 单测 6 用例

- [ ] **5.3** lineage 写入 + diff 计算
  - 单测 8 用例

- [ ] **5.4** child local override 标记
  - 用户改 → is_local_override=true
  - 单测 4 用例

- [ ] **5.5** 基线升级通知（child 列表显示 N 章节待同步）
  - 单测 4 用例

- [ ] **5.6** 新 router `group_note_baseline.py`（5 端点）
  - 注册 router_registry
  - 单测 10 用例

## Sprint 6：前端（2.5 人天，C1~C12 + 集团基线 UI）

- [ ] **6.1** `useNoteDynamic.ts` composable
  - 调动态行/列 5 端点

- [ ] **6.2** `useGroupBaseline.ts` composable
  - 调集团基线 5 端点

- [ ] **6.3** `NoteTableEditor.vue` 动态行/列视觉
  - 浅黄/浅紫底色 + ★/+ 标记
  - vue 单测 8 用例

- [ ] **6.4** 「+ 添加明细行」/「+ 添加列」按钮
  - 仅动态区显示
  - vue 单测 6 用例

- [ ] **6.5** 删除右键 + 公式栏绑定选项
  - vue 单测 6 用例

- [ ] **6.6** 「📦 应用集团基线」按钮 + 对话框
  - baseline 选择 + 版本对比 + 预览 diff
  - vue 单测 8 用例

- [ ] **6.7** 「💾 保存为集团基线」按钮（partner 权限）
  - 名称 + 版本号输入
  - vue 单测 4 用例

- [ ] **6.8** 「🔄 同步基线」按钮 + lineage 显示
  - 章节级 lineage 标识 + override 标记
  - vue 单测 6 用例

- [ ] **6.9** Sprint 6 验收
  - vue-tsc 通过
  - vitest 全绿
  - Playwright 实测一个动态表 + 一次基线 apply

## Sprint 7：Word 导出（1 人天，D1~D8）

- [ ] **7.1** GTNoteDynamicRow / GTNoteDynamicCol 样式
  - `scripts/build_note_export_template.py` 加样式
  - 视觉与 GTNoteTableRow 一致

- [ ] **7.2** Word 导出动态区渲染
  - `_add_dynamic_row` / `_add_dynamic_column`
  - 「（不适用的项目请删除）」自动提示
  - 单测 6 用例

- [ ] **7.3** 19 项视觉断言（11 + 8 新增）
  - `test_note_export_visual.py` 扩展
  - 含动态行/列 / 空表替换 / 集团 lineage 备注

- [ ] **7.4** Sprint 7 验收
  - 全量 173 章节导出无样式畸形
  - 单 commit

## Sprint 8：模板数据 + 收尾（1 人天）

- [ ] **8.1** `generate_note_template_bindings.py` 扩展
  - 读 P-1 输出 → 写 _dynamic_regions
  - 读 P-2 输出 → 写 wp_data binding
  - 幂等可重跑

- [ ] **8.2** 60+ 章节 _dynamic_regions 入库
- [ ] **8.3** 30+ 章节 wp_data binding 入库

- [ ] **8.4** UAT
  - 首汽租车_2025 应收账款前 5 名 / 长期股权投资 / 应交税费 / 固定资产 4 个动态表
  - 集团基线：从首汽租车_2025 保存基线 → 重庆和平药房_2025 应用基线 → diff 对比
  - 验证：行加删 / 列加删 / 排序 / Word 导出 / 空表替换 / 章节跳过
  - 出报告 `docs/uat/note-dynamic-tables-uat-{date}.md`

## 收尾

- [ ] **F-1** 全量回归（不破坏现有 173 章节）
- [ ] **F-2** memory.md 沉淀（动态表/集团基线铁律）
- [ ] **F-3** ADR-011 + ADR-012 撰写 + INDEX.md
- [ ] **F-4** v1 → v2 演进路线（跨章节联动 / fork-merge / AI 自动识别）写入 backlog

## CI 卡点汇总

| ID | 描述 | Sprint |
|----|------|--------|
| CI-1 | `_dynamic_regions` idx/col_id 有效性 | 1.6 |
| CI-2 | row_type=dynamic_* 在 region 范围内 | 1.6 |
| CI-3 | column_id 全局唯一 per table | 1.6 |
| CI-4 | REGION/WP 公式能解析 | 3 |
| CI-5 | 行/列删除后合计 PBT | 4 |
| CI-6 | round-trip 无丢失 PBT | 8.4 |
| CI-7 | apply_baseline 后 lineage 必有 baseline_id | 5.6 |
| CI-8 | auto_trim v2 三级互斥 | 4 |

## 任务依赖图

```
P-1 ──┐
P-2 ──┤        ┌→ Sprint 1 → 2 → 3 ─┐
P-3 ──┴→ ──────┘                    ├→ Sprint 6 → 7 ─┐
                                    ├→ Sprint 4 ────┤
                                    └→ Sprint 5 ────┴→ Sprint 8 → F
```

## 风险登记册

| 风险 | 影响 | 缓解 |
|------|------|------|
| wp_data 底稿数据格式跨循环不统一 | 取数失败 | 每循环单独 adapter（H/G/J/L/D/K/M），不试图通用化 |
| 集团基线 apply 误覆盖用户修改 | 数据丢失 | 强制 is_local_override 标记 + 预览 diff + 事务回滚 |
| 动态列对其他章节影响 | 表样不一致 | column_id 仅 per-table 唯一，不跨章节 |
| auto_trim v2 误剔有用章节 | 输出不完整 | feature flag + 三级互斥 CI-8 + 用户可手工恢复 |
| 60+ 章节标注工作量超 P-1 1 人天 | Sprint 8 阻塞 | 先做 8 大类（可降级到 30+ 章节启动）|
