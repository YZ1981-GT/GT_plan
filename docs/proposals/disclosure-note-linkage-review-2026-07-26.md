# 附注模块联动复盘与整改记录（2026-07-26）

> 范围：附注模块与底稿 / 报表 / 合并 / 交付 / 公式 五条联动链。
> 本文既是复盘实测记录，也是本轮整改的落地清单与遗留项台账。

## 一、实测现状（复盘时的库内事实，4 个项目 / 554 条活跃附注）

| 事实 | 数字 | 含义 |
|---|---|---|
| `table_data._source in (workpaper, workpaper_html)` | 0 | 底稿→附注结构化推送在生产**零使用** |
| `sub_table_data` / `_sub_table_columns` | 0 / 0 | 46 个 `buildXSyncPayload` + 列头守卫全绿但无真实数据 |
| `last_sync_source` / `last_sync_wp_id` | 0 | 「此数据由底稿同步」溯源字段没被写过 |
| `table_data._formulas` | 0 | 用户附注公式零使用 → 报表页「关联附注」（只扫 `_formulas`）恒空 |
| `_validation_rules` / `note_validation_results` | 76 / **0** | 规则在，但校验从未跑过并落库（11 executor + soe760/listed187 预设空转） |
| `is_stale` | listed 181/181、soe 40/373 | 报表任一变更即全项目置 stale → 标记退化为噪声 |
| `consolidation_breakdown` / `source_project_id` / `template_lineage` | 0 / 0 / 0 | 合并穿透、跨项目模板血缘零使用 |
| 11 张 `note_*` 辅助表 | 全 0 行 | 章节实例/锁/版本树/模板/裁剪方案/科目映射×2/集团模板(+baseline)/`consol_note_data` |
| 灰度开关 | RAG / FORMULA / VALIDATION_STRICT 全 False | 表内公式、RAG、严格校验未启用 |
| `headers=[]` 的 legacy 表 | 81 | 表头读时派生（模板优先）已覆盖 |

## 二、本轮已整改（含 live 验证）

| 项 | 内容 | 验证 |
|---|---|---|
| P0-1 | 新增就绪度看板：后端 `GET /api/disclosure-notes/{pid}/{year}/readiness` + `note_readiness_service` + 前端 `NoteReadinessPanel`（工具栏「📋 就绪度」带徽标） | live：181 章节 / 26 有底稿映射 / 23 从未同步 / wp_ids 与 sheet 名解析正确 |
| P0-1 真源 | 新增 `backend/data/note_workpaper_sync_registry.json`（由 `scripts/gen_note_wp_sync_registry.py` 从前端 `*NoteSectionMap.ts` + 反向跳转 map 生成，29 科目）。**不再使用陈旧的 `DEFAULT_WP_MAPPING`**（其编号仍是老体系 D1→五、2 / D2→五、3） | 单测锁定权威章节号（D1=五、4 / D2=五、5 / K1·G2 同挂 五、8） |
| P0-2 | 底稿披露 sheet 顶部统一「附注同步状态条」：`GtWpDisclosureSyncBar` 在 `GtWpRenderer` 一处接入（覆盖全循环）+ 后端 `GET .../wp-sync-status?wp_code=` | live：D1 listed 已同步 / E1 未同步 / 未知 wp_code 返空 |
| P0-3 | `mark_notes_stale_for_report_change` 粒度化：有 linkage → 只标关联章节（`stale_source='report'`）；全项目无 linkage → 保守全量但标 `report_fallback`。新增列 `disclosure_notes.stale_source`（V129 additive） | 迁移已应用、drift 无新增；3 条单测覆盖三分支 |
| P0-4 | 生成 / 项目级刷新 / 单章节刷新 / 底稿同步（单条+批量）后自动 fail-open 跑 `validate_all` 并落库；附注树节点透出服务端 findings 计数徽标 | tree 端点 additive `findings` 字段 live 可用 |
| P1-1 | 报表行→附注引用三级回退：`_formulas` → `ReportNoteLinkage`（Cell_Binding+配置） → 预设库 `logic_check` 勾稽（origin 字段标注来源） | live：BS-002 → 五、1（origin=cross_check，修前恒空）；BS-008 → 五、4 |
| P1-2 | 高级查询 `source=disclosure` 真源修正：优先 `disclosure_notes`（554 条真实数据），无命中才回退 `consol_note_data`（合并那套，0 行）；表头缺失走读时派生 | live：rows 8 / 列含 note_section·section_title·table_name + 派生中文表头（修前恒 0 行） |
| P1-3 | 附注交付出具软闸门：`DeliverableExportResponse.warnings`（additive）列出「有底稿映射但从未同步」「校验存在错误」「尚未执行过校验」；前端导出后弹提示，**不阻断出具** | AST/诊断通过；文案与 readiness 同源 |

测试：后端 `tests/test_note_readiness_and_stale.py` 15 passed（映射真源 / findings 聚合 / readiness 口径 / stale 三分支 / 勾稽回退）；
前端 `disclosureSyncBar.spec.ts` 25 + `reportNoteReferences.spec.ts` 5 passed；改动文件 get_diagnostics 全清、Vite transform 全 200。

## 三、遗留项台账（本轮**未**做，附原因）

### 需 spec / 跨模块决策

1. **合并附注双真源**：合并附注走 `consol_note_data`（0 行），`generate_full_consol_notes`(V2) 源码注释自认"尚未接 `disclosure_notes` 落库路径"，`CONSOL_NOTES_V2_ENABLED=False` → 依赖 `disclosure_notes.consolidation_breakdown` 的附注级穿透端点恒 `has_breakdown=false`。
   建议：V2 输出落 `disclosure_notes`（带 `source_project_id` + `consolidation_breakdown`），让穿透 / 导出 / 校验 / 公式复用同一套。改动大、涉及合并流水线，须单独 spec。
2. **底稿→附注仍是 push 模型**：payload builder 在前端（依赖各 tab composable 内存态），后端无法批量代跑，故只能"状态条 + 就绪度清单"指路；逐 tab 自动同步（照 E1 `_autoSyncAfterSave`）需 45 个披露 tab 逐个接线，建议按循环分批。

### 数据 / 运维决策

3. **11 张空 `note_*` 表**：`note_section_templates/instances/locks/version_tree`、`note_trim_schemes`、`account_note_mapping` 与 `note_account_mappings`（同义双表）、`group_note_templates(+baseline)`、`consol_note_data`。
   建议：确认无代码引用后标 deprecated 或删；本轮不动（删表属破坏性操作）。
4. **两张备份表**：`_note_wrong_year_orphan_backup`（本次 drift 唯一来源）、`_note_guidance_split_backup`。其使命（错误年度孤儿修正、提示分流迁移）已完成并复核，可 drop；本轮不动。
5. **灰度开关**：`DISCLOSURE_NOTE_FORMULA_ENABLED`（已有 119 条 movement binding 可算）建议按项目灰度先开一个真实项目验证；`DISCLOSURE_NOTE_RAG_ENABLED` 须先补知识库索引（当前知识库为空，开了只会 fail-open 空转）；`DISCLOSURE_NOTE_VALIDATION_STRICT` 待 warning 量可控后再置 True。三者本轮均保持默认关闭（改默认属运维决策）。
6. **历史 stale 数据**：粒度化只影响将来的标记；库内既有 181 条 `stale_source=NULL` 的历史标记未回填（前端按历史文案弱化呈现即可）。

### 明确不建议做

- 批量填 `report_note_linkage.json` 让报表回写附注（方向倒置，会覆盖附注明细汇总真值——决策 1 已定「只校验不写值」）；
- 给缺 binding 的损益类章节批量臆造科目映射（错了就是写错披露）；
- 现在开 RAG 开关。

## 四、可复用范式沉淀

1. **跨端映射真源生成而非手写**：附注章节↔底稿的权威映射在前端 `*NoteSectionMap.ts`，后端需要同一份时用脚本生成 committed JSON（`gen_note_wp_sync_registry.py`），不手工维护第二份；生成器需做形态校验（章节号 `^[一二三四五六七八九十]+、`）防把 sheet 名常量误当章节号。
2. **"能力就绪但零使用"的修法是可见性而非再建能力**：先给"哪里还没做"的只读清单（就绪度看板 + 页内状态条），再谈自动化。
3. **写操作后自动补跑校验**：`run_validation_best_effort` 统一 fail-open（异常 rollback 校验事务，绝不影响已提交主操作），挂在生成/刷新/同步各写路径。
4. **stale 必须有粒度与来源**：一刀切全量标记等于没标；无关联信息时保守全量但用 `stale_source` 区分 `report` / `report_fallback`，前端据此分级呈现。
5. **反向溯源用多级回退**：用户公式 → 写值 linkage → 勾稽预设，并用 `origin` 字段告诉用户关系来自哪一级。
