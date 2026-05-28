# 附注浮动行表格支持 — 任务列表

> 版本：v0.1（草稿）
> 26 验收 / 7.5 人天 / 5 Sprint
> 关联：requirements.md / design.md

## 前置（外部依赖，1.5 人天）

- [ ] **P-1** 审计师标注 60+ 章节浮动区域（1 人天）
  - 输入：`附注模版/{soe,listed}*.md` 模板原文
  - 输出：`backend/data/note_floating_regions_annotation.csv`（章节 / 区域名 / start_label / end_label / source / aux_type / order_by）
  - 优先级：应收账款前五名 / 长期股权投资子公司 / 借款明细 / 关联方清单 / 存货分类 / 应交税费 / 固定资产分类 / 应付职工薪酬 共 8 大类先做

- [ ] **P-2** 浮动行视觉基线（0.5 人天）
  - 老审计师提供 5 张实际致同附注 PDF（含浮动表）
  - 标注：浮动行字号 / 行高 / 是否有底色 / 「（不适用的项目请删除）」位置
  - 存放：`tests/fixtures/note_floating_baseline/*.png`

## Sprint 1：数据模型与引擎（2 人天，A1~A5 + B1~B4）

- [ ] **1.1** row_type 枚举扩展 + is_floating 字段
  - 修改 `note_cell_merge.py` / `disclosure_engine.py` / 模板 JSON schema 校验
  - row_type 新增 `floating_anchor` / `floating_data` / `floating_marker_end`
  - 单测 6 用例

- [ ] **1.2** _floating_regions sidecar 模型
  - 在 `backend/app/services/note_floating_regions.py` 新建 dataclass
  - 校验函数 `validate_floating_regions(table_data)` 检查 idx 有效性
  - 单测 8 用例

- [ ] **1.3** `_expand_floating_regions` 引擎方法
  - `disclosure_engine.py` 新增方法，接 region.floating_source 分支
  - 支持 `aux_balance` / `manual` / `wp_data` 三种 source
  - 单测 12 用例（含 fixed-only / floating-only / mixed 三场景）

- [ ] **1.4** `aux_balance` 浮动展开
  - 按 aux_type + account_codes + limit + order_by 查询 → 每行一条
  - label 自动取 aux_code 的 description 或 aux_code 自身
  - 单测 6 用例（含 limit 截断 / 0 行 / 重复 aux_code）

- [ ] **1.5** Sprint 1 验收
  - CI 卡点 CI-1 / CI-2 实施
  - pytest 全绿
  - 单 commit

## Sprint 2：合并与公式（1.5 人天，B5~B8 + D5）

- [ ] **2.1** `note_cell_merge.merge_floating` 扩展
  - (region_name, label) 元组匹配
  - `_legacy_row` 标记保留
  - hypothesis PBT 4 不变量

- [ ] **2.2** REGION 公式函数
  - `note_formula_generator.py` 新增 REGION(region_name) 解析
  - 自动展开为 `R{start}:R{end}` 当前形态
  - 单测 8 用例（含嵌套 SUM(REGION(...)) / 多 region）

- [ ] **2.3** PRIOR 跨年浮动行匹配
  - 按 label 模糊匹配（先精确，后 fuzzy 0.85）
  - 上年浮动行不存在时返回 0 + 标记 stale
  - 单测 6 用例

- [ ] **2.4** Sprint 2 验收
  - CI-3 / CI-4 实施
  - PBT 通过

## Sprint 3：API + 前端（2.5 人天，C1~C6 + 新端点）

- [ ] **3.1** 新 router `note_floating_rows.py`（POST/DELETE/PUT/GET 4 端点）
  - 注册到 router_registry/report.py（铁律必查）
  - 单测 12 用例

- [ ] **3.2** `useNoteFloatingRows.ts` composable 新建
  - 调用 4 个端点
  - 维护本地浮动行状态 + 乐观更新

- [ ] **3.3** `NoteTableEditor.vue` 浮动区视觉
  - 浅黄底色 (#FFF8E1)
  - 行号 ★ 标记
  - vue 单测 6 用例

- [ ] **3.4** 「+ 添加明细行」按钮 + 删除确认
  - 仅浮动区显示
  - 删除前 ElMessageBox.confirm
  - vue 单测 4 用例

- [ ] **3.5** 公式栏浮动行选项
  - 选中浮动行 → 显示「绑定 aux_balance / 手工」
  - vue 单测 4 用例

- [ ] **3.6** 排序 / 自动重新填充按钮
  - PUT /sort + GET /auto-fill 集成
  - vue 单测 3 用例

- [ ] **3.7** Sprint 3 验收
  - vue-tsc 通过（仅本 spec 涉及文件）
  - vitest 全绿
  - Playwright 实测一个浮动表的加行/删行/导出

## Sprint 4：Word 导出（1 人天，D1~D4）

- [ ] **4.1** GTNoteFloatingRow 样式定义
  - `scripts/build_note_export_template.py` 加该样式
  - 字号 / 行高 / 缩进与 GTNoteTableRow 一致

- [ ] **4.2** `note_word_exporter._add_floating_row` 
  - 浮动区合计自动加粗
  - 浮动区结尾自动加「（不适用的项目请删除）」灰色提示
  - 单测 4 用例

- [ ] **4.3** 11 项视觉断言扩展为 15 项（+4）
  - 浮动行字号 / 行高 / 提示文字 / 合计粗下边框
  - `tests/services/test_note_export_visual.py` 新增 4 断言

- [ ] **4.4** Sprint 4 验收
  - 全量 173 章节导出，浮动行无样式畸形
  - 单 commit

## Sprint 5：模板数据 + 收尾（0.5 人天）

- [ ] **5.1** `generate_note_template_bindings.py` 扩展
  - 读 P-1 输出的 csv → 写入模板 JSON `_floating_regions`
  - 幂等可重跑

- [ ] **5.2** 60+ 章节模板入库
  - 跑脚本，diff 检查
  - 单 commit

- [ ] **5.3** UAT
  - 首汽租车_2025 应收账款前五名 + 长期股权投资 + 应交税费 3 个浮动表
  - 验证：加行 / 改值 / 排序 / 删行 / Word 导出
  - 出报告 `docs/uat/note-floating-rows-uat-{date}.md`

## 收尾（F-1 / F-2 / F-3）

- [ ] **F-1** 全量回归（不破坏现有 173 章节）
- [ ] **F-2** memory.md 沉淀（浮动行铁律 + 关键设计）
- [ ] **F-3** ADR-011 撰写 + INDEX.md 加条目

## 任务依赖图

```
P-1 (外部) ─┐
            ├→ Sprint 5.1/5.2
P-2 (外部) ─┤    ↓
            └→ Sprint 1 → 2 → 3 → 4 → 5.3 → F
```

## CI 卡点汇总

| ID | 描述 | Sprint |
|----|------|--------|
| CI-1 | _floating_regions idx 有效性 | 1.5 |
| CI-2 | row_type=floating_* 必须在 region 内 | 1.5 |
| CI-3 | REGION() 能解析 region name | 2.4 |
| CI-4 | 删除浮动行后合计公式自动重算 PBT | 2.4 |
| CI-5 | 用户加的浮动行 round-trip 无丢失 PBT | 5.3 |
