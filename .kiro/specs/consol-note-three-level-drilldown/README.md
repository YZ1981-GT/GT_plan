# 合并附注三级穿透（合并附注 → 单体附注 → 单体底稿）

**状态**：占位待办（未启动实施）
**档位**：档 3 三件套（建议）/ 工时 3-4 天
**前置条件**：必须有真实合并母子项目数据

## 业务诉求（用户 2026-05-17）

合并附注是各家汇总的，用户希望：
1. 在合并附注上**右键 → 查看合并明细**（金额按子公司分解）
2. 点击某子公司金额 → 跳转该子公司**单体附注**对应章节
3. 单体附注章节 → 已有路径继续穿透到**单体底稿**

## 现状盘点（已 grep 核验，2026-05-17）

### 已就绪基础设施（80%）

| 组件 | 现状 |
|------|------|
| `Project.parent_project_id` | ✓ 字段已存在（PG 列已有）|
| `Project.consol_level` | ✓ 字段已存在（合并层级 1=单体 / 2=直接合并 / N+ 多级）|
| `consol_tree_service.build_tree` | ✓ 完整企业树构建（递归子项目）|
| `consol_drilldown_service` | ✓ TB 层级穿透已实现 |
| `consol_aggregation_service` | ✓ 三种汇总模式（self / children / descendants）|
| `consol_disclosure_service.generate_consol_notes` | ✓ 合并附注 7 章节生成（合并范围/子公司/商誉/少数股东等）|
| `note_account_mapping_seed` 单体版映射 | ✓ 280 条种子（已 seed） |

### 关键缺口（20%）

| 项目 | 缺口 |
|------|------|
| `disclosure_notes` schema | ⚠ 无 `source_project_id` / `consolidation_breakdown` JSONB 字段 |
| 合并附注 → 子公司明细 API | ⚠ 缺 `GET /api/notes/{section}/consol-breakdown` |
| 子公司附注章节匹配 | ⚠ 缺 `section_title` 跨项目章节 alias |
| 前端 5 视图右键菜单 | ⚠ 缺"穿透到子公司明细"项 |
| ConsolBreakdown 弹窗 | ⚠ 缺组件 |
| `linkage_graph_builder` 父子边 | ⚠ 当前 NOTE 节点不区分合并/单体 |
| 真实合并母子项目数据 | ⚠ PG 实测：0 个项目走 consolidated 模式 |

## 范围

**做**：
1. Alembic 迁移 — `disclosure_notes` 加 `source_project_id` / `consolidation_breakdown` JSONB
2. 改造 `consol_disclosure_service.generate_consol_notes` — 生成合并行时记录子公司明细到 `consolidation_breakdown` 字段
3. 新建 `note_consol_drilldown_service` — 按合并行 + section_title 反查所有子公司同章节明细
4. 新建端点 `GET /api/notes/{section_id}/consol-breakdown` — 返回 `[{child_project_id, child_company_name, amount, child_section_id}]`
5. 新建端点 `GET /api/notes/{section_id}/breakdown/{child_project_id}/source-wp` — 返回该子公司该章节对应的底稿列表
6. 改造 `linkage_graph_builder._from_note_account_mapping` — 添加合并 NOTE → 单体 NOTE 父子边
7. 前端 `DisclosureEditor.vue` 右键菜单加"查看合并明细"
8. 前端 `ConsolBreakdownDialog.vue` 新组件 — 显示子公司明细 + 点击跳转
9. 准备测试用合并母子项目数据（重庆医药集团多家子公司已存在，建立 parent_project_id 关系即可）

**不做**：
- 多级合并（A 合并 B+C，B 又合并 D+E）穿透 — 留独立 spec
- 抵消分录穿透 — 已有 ConsolWorksheet 提供，不重复建
- 合并附注编辑功能 — 当前合并附注是只读生成，不允许直接编辑

## UAT 验收

- ✓ UAT-1：合并项目附注列表能看到"应收账款"章节
- ✓ UAT-2：右键"查看合并明细" → 弹窗列出 N 家子公司各自金额
- ✓ UAT-3：点击某子公司行 → 跳转该单体项目同名章节
- ✓ UAT-4：单体附注 → 单体底稿穿透链路（已有，不破坏）
- ✓ UAT-5：依赖图含合并 NOTE → 单体 NOTE 父子边

## 启动条件

1. 真实合并母子项目数据准备好（重庆医药集团 9 个子公司挂到一个合并母项目下）
2. `consol_disclosure_service.generate_consol_notes` 已被真实跑过一次（生成 7 个合并章节）
3. 前置 spec：global-linkage-bus + note-account-mapping-seed 已稳定（已完成 ✓）

## 已知技术债（实施时考虑）

- TD-A：`section_title` 跨项目可能有别名（"应收账款" vs "应收账款（合并）"），需要 alias 表
- TD-B：consolidation_breakdown JSONB 字段在大表上查询性能可能问题，需 GIN 索引
- TD-C：合并附注 stale 传播链路（任一子公司 stale → 合并母项目 stale）需 stale_engine 增强
