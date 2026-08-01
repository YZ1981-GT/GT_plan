# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-08-01
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active 17（`.kiro/specs/` 实测目录数）/ Archived 491 = 总计 508
**最高迁移**：**V133**（以 `migration_status` 实测为准）
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

---

## 一、Active Specs

| Spec | 阶段 | 说明 |
|------|------|------|
| `disclosure-note-follow-actual-content` | 5/13 完成 | 附注跟随底稿实际内容。已完成：空表判定（双侧 38 测试镜像）/ 模板差异五类计算（29 测试）/ legacy 迁移 dry-run 四类分类（32 测试）/ F2 自动同步修复（mounted 防护 bug + 全平台清除 + 覆盖率守卫 + 后端兜底 stale marker 43 测试 + 浏览器实测）/ 缺失链路 Tab 定性→独立立项。**待做**：模板回流写入 / 过期可见性 / legacy 破坏性迁移（阻塞于 columns 补齐）/ 空表折叠 / 全链实测 / 收尾 |
| `k1-four-table-extraction-and-disclosure-alignment` | **27/27 全完成 + 实测** | K1 四表库取数口径根治 + 披露/附注结构对齐。**已完成**：共享件 `four_table/{report_line_accounts,leaf_aggregation}.py`（D1 薄壳委托、零回归）/ K1 render 改叶子口径 + 备抵精确到 `1231-03`（实测坏账 28,464,225.16→900,217.36 虚增 31.6 倍已修、原值 211,252,631.06→269,885,933.03 少 21.7% 已修）/ `tb_source_codes` 溯源面板 / 「从四表库带入未审数」按钮 + FS 三行预填 / 账龄枚举贯通 K1-1（3年段 `over3` 不再丢）/ 公式预设 +6 条 / 附注 §五、8 补源模板 ⑧⑨⑩ 三表 + 上市变动表两级表头 + 账龄 5 年段、§八、9 账龄表还原源模板 3 列 + 忠实推小计/减坏账/合计 / 三向守卫（源 xlsx ↔ 模板 ↔ 载荷）。**已实测**：render 链路 + 两个项目预填（性质桶之和分文不差等于原值合计、报表数按 BS-009 公式符号加权正确）+ 披露推送→§八、9 落库与读时投影（3 列 flat、_column_groups=[]、小计−减坏账=合计）；实测数据已复原。代码/测试/模板已随并发会话分层提交 |
| `f1-four-table-extraction-and-disclosure-alignment` | **28/28 全完成 + 实测** | F1 预付款项四表库取数链路根治 + 披露/附注收尾。**已完成**：render 改走共享件 `four_table`（删缺点号边界的 `_is_leaf`，`BS-008` 报表映射 + `account_mapping` 反解，备抵兜底 `1231-04` + 宽前缀时叠「预付」名称过滤）/ **F1-1「按性质分类」四表预填**（`1123` 叶子科目名 → 货款·工程款·设备款·服务费·其他，实证 5 桶之和 = 父科目期末）+「从四表库带入未审数」按钮（对四表无数据且无手工值的桶显式写 0，否则合计翻倍）/ **修 F1-4 存货余额恒 0**（前缀 `1401` 是「材料采购」→ 改 `BS-010` 区间 `SUM_TB('1401~1499')`，实测 0→117,808,961.20）/ `tb_source_codes` 由 dead output 升级为结构化 + `F1FourTableSourcePanel`（并列展示 trial_balance 与叶子两口径并检出差异）/ 披露列头三向对齐源 xlsx（`账  龄`、上市 `金  额` 双空格·`期末数`/`上年年末数`，国企 `金 额` 单空格）/ **上市③前五名「汇总或分别披露」二选一** + `_removed_table_keys` / 8 处 `el-input-number` → `WpAmountInput`（归零）/ 3 个 Tab 的 `fmtAmount` 收敛到 `displayPrefs` / **披露勾稽引擎 + 面板**（F7-1~F7-14 + 国企四表库比对，17 条）/ 公式预设 1 块 5 条 → 3 块 17 条。**已实测**（项目 `2aa00f57`/wp `6de6c91d`）：溯源面板四 tag + 两口径差异 1,301,918.43；带入后性质合计 = 账龄合计 = 1,301,918.43；国企三级表头正确、`el-input-number` 0 / `WpAmountInput` 17、录 1234567.5 → `1,234,567.50`；自动同步 → §八、7 `last_sync_at` 前移 + 3 子表 + 列头字面逐字一致 + 合计 67,350.93；上市 Tab 在国企项目正确显示「不适用」零写入；11 个实测键已复原。CI job `note-f1-four-table` / `-frontend`。**遗留**：上市侧无活体（8 项目全 soe）/ commit |
| `disclosure-sync-path-buildout` | 缺口 64→24 | 补齐披露 Tab 同步链路。**已完成**：批1 G 循环（G4/G5/G6/G8/G9/G12 接线 + 实测）/ 批2 H 循环（H4Soe/H6×2委托/H7×2）/ 批3 L 循环（L5/L6/L7/L8 接线 + L2/L4 豁免/留缺口）/ 批4 M 部分（M4/M5/M7 标准变动表 6 Tab 接线 + 实测）。**待做**：批5 N 循环（N2/N3/N4/N5 7Tab，但 `n-cycle-tax-disclosure-alignment` 已完成这些→需核实是否已收口）/ 批6 D2·F4·J2 / 收尾归零 |
| `k1-extraction-chain-and-note-alignment` | **✅ 8/8 wave 全完成 + 实测（2026-08-01），待 commit** | K1 其他应收款循环第二轮收口（承接归档 spec `k1-four-table-extraction-and-disclosure-alignment` 之后新发现的取数级联与结构问题）。**Wave 1~7**：新建共享件 `four_table/{aux_aggregation,k1_aux_detail,k1_detail_seed}.py`（`aux_aggregation` 把 F1 `pick_aux_type` 提升为共享件；K1-3 坏账 transient seed）/ 新端点 `POST /k1/import-aux-balance`（K1-2 明细四表自动归集，全库 0→有数据）/ 修正 K1-2 `item_id`（`K1-2-rows`→`K1-2-detail-rows`，后端 specs 与前端真实读写键 4 处不一致已修正）/ 前端 `useK1DetailAutoSeed`（打开 K1-2 空表自动归集）/ 三阶段变动表行集按源模板重建（`k1StageMovementRows.ts`，12/10 行 + 历史迁移守恒）/ 附注列头三向对齐 + 汇总表「其他应收款」推送（F8-48 勾稽）+ `_note_texts` 补中文 title / 公式预设 2→6 块。**Wave 8 实测**：真实项目 `2aa00f57` 打开 K1-2 → 自动归集 333 行、合计 88,596,839.09 与 `tb_aux_balance` 分文不差；K1-1 性质分布级联正确、账龄需手动同步按钮（设计如此）；披露国企 Tab「从源底稿取数」刷新账龄组合/前五名表正确、「同步至附注」落库 §八、9（`last_sync_at` 前移 + 汇总表键出现 + F8-48 勾稽验证通过）。**范围收窄**：K1-5/K1-7/K1-8 导入导出字段结构性不匹配（K1-8 甚至非行数组而是单一 JSON 对象），记录为独立缺陷另立 spec，未纳入本次。测试数据已逐字复原（`checklist_responses` K1-2-detail-rows 删除 / K1-1-* 49 条删除 / K1-note-soe-rows 三字段复原；`disclosure_notes` §八、9 汇总表键移除 + 两表清零 + `last_sync_at` 回退）。**遗留**：K2~K13 沿用本范式另立 / commit |

---

## 二、已归档 Spec（491个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          2
├── 04-infra-architecture/            36
├── 05-business-features/            234
├── 06-engineering-governance/        13
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              39
├── 09-consolidation-phases/           5
├── 10-A~S-workpaper-all-cycles-complete/ 31
├── 11-confirmation-d0-module/        11
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     4
```

### 最近归档（2026-08-01，第三批）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| f2-inventory-account-mapping-and-linkage | F2 存货四表库科目映射结构性修复（13/13 全完成+实测）：库内并存两版互不兼容的标准存货科目表（`1405`/`1406`/`1407`/`1408`/`1411`/`1416`/`1461` 名称↔编码在两版间完全相反）→ 新建按**名称**归类的单一真源 `category_rules.py`（Property 1~5 + 两变体参数化守卫 50 例，同 N4/F1 铁律）；render 改叶子口径委托 `four_table.select_leaves`（同 K1 同款「取最深层级丢叶子」bug）；前端 `f2AccountModel.ts` 新增 `resolveF2InventoryAccounts` 系列（动态项目科目表优先，回退静态兜底）接入 AJE 下拉与溯源面板；公式管理页 `workpaper:F2` 删 31 条「编码=分类」写死映射改为区间口径+底稿间 `WP()` 联动（18→20 块/71→85 条，`fix_f2_prefill_presets.py` 幂等脚本）；披露表结构核查确认与姊妹 spec `f2-inventory-disclosure-template-alignment` 已对齐。后端 168 + 前端 105 files/925 tests 全绿；真实 DB 双变体项目直跑验证桶合计==叶子合计分文不差。 |

### 最近归档（2026-08-01，第二批）

**→ 08-disclosure-notes（+3）**

| Spec | 说明 |
|------|------|
| d1-extraction-chain-completion | D1 应收票据「四表入库→底稿取数→披露→附注」全链路（6 wave 全完成+实测）：修掉 5 处真实缺陷（表名漏字/准则23号括注挂错表/披露小节标题漂移/guidance markdown 冲突/净额归一 dead output）。后端 743 绿/前端 34 文件 489 绿 |
| d-cycle-extraction-chain-completion | D2/D3/D5/D6/D7 取数链路推广 D1 范式（6 wave 全完成+实测）：D6 取错科目族（1402→1141）/ D2 缺减备抵 / D5 引不存在科目诚实化 / D2 附注模板两版 30 表补齐 / D6 账龄枚举贯通 / D5~D7 公式预设 sheet 名环形错位修正。后端 949+2skip / 前端 108 文件 1366 绿 |
| d1-four-table-extraction-formula-wiring | D1 四表库取数公式接线（4 wave 全完成+浏览器实测）：叶子取数 seed D1-cat-rows/D1-bd-portfolio-rows + 跨底稿溯源登记 + 披露/附注复核；实测挖出坏账 seed 被全零骨架永久堵死的真缺陷并修复（`_is_blank_skeleton` 判定） |

### 最近归档（2026-08-01，第一批）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| h-cycle-legacy-cleanup-and-platform-hygiene | H 循环复盘 8 项遗留收口（19/19 全完成+实测）：平台级 `**` 残迹剥离（58 处成对标记，隔离验证仅删 `*` 字符）/ H8-H9 死按钮+H1/H2/H4/H5/H6 缺 AI 全部接入统一 `useHCycleDisclosureAi`（24 处文本域）/ `report_row_code` 134 行陈旧编号按标签反查重映射 92 处（位移量 1~14 不一致，证伪统一偏移假设）/ registry 命名覆盖 62→67 条（G1/G3/G6/G10/H4/H6 修复，含嵌套双章节支持）/ 勾稽引擎 H1/D1/F1 委托共享容差常量 + 新建 H2/H5/H8/H9/H10 五套规则接入统一面板 / Wave 6 活体验证：上市变体门控（`0ec33ac9` 临时改 `entity_type=listed` 验证 H1 §五、22 同步 39 行落库，验证后逐字复原）+ 反向验证国企项目零写入 + 真实数据端到端（`tb_balance` 叶子聚合精确等于父科目期末 51,188,971.32）。全量前端 19969 例仅 90 失败（全部核实为预存在基线或本次顺手修复）。 |

### 2026-07-31 归档

**→ 08-disclosure-notes（+19，含并发会话完成的 spec）**

| Spec | 说明 |
|------|------|
| h2-construction-in-progress-disclosure-alignment | H2 在建工程披露结构对齐（7/7 全完成+实测）：两级表头重建 + 「项  目」→「工程物资」改名 + 10 表 columns/guidance + 契约守卫 + CI job + 浏览器实测通过 |
| d2-ar-disclosure-template-alignment | D2 应收账款上市披露三层对齐（31/31 全完成+实测+已提交） |
| d2-ar-disclosure-soe-alignment | D2 应收账款国企披露结构对齐（25/25 全完成） |
| f2-inventory-disclosure-template-alignment | F2 存货披露对齐（Sprint 1~8 全完成+已提交） |
| f1-prepayment-disclosure-template-alignment | F1 预付款项披露对齐（全完成+实测+待 commit） |
| disclosure-columns-coverage-rollout | 披露表 columns 覆盖推广（Task 1~16 全完成+已提交） |
| j1-disclosure-template-alignment | J1 应付职工薪酬披露对齐（61/61 全完成+待 commit） |
| k2-other-current-assets-disclosure-alignment | K2 其他流动资产披露对齐（22/22 全完成+实测） |
| n1-deferred-tax-disclosure-template-alignment | N1 递延所得税资产披露对齐（57/61 实现+实测完成） |
| n-cycle-tax-disclosure-alignment | N 循环税务类披露对齐（N2/N4/N5 全完成+实测） |
| d-cycle-remaining-disclosure-alignment | D3/D5/D6/D7 披露结构对齐（Task 1~9 全完成+实测） |
| k-cycle-disclosure-alignment | K1~K13 三批披露对齐（全完成+实测） |
| d1-notes-receivable-disclosure-alignment | D1 应收票据披露对齐（四阶段全完成+实测） |
| f-cycle-disclosure-parity | F 类披露复盘对齐（R1~R9 全完成） |
| applicable-standards-frontend-wiring | 准则前端全链接通（全完成+实测） |
| applicable-standards-runtime-and-sync-guard | 准则运行时守卫（全完成+实测） |

**→ 05-business-features（+2）**

| Spec | 说明 |
|------|------|
| f1-prepayment | F1 预付款项（含四表库自动取数补齐） |
| k2-other-current-assets | K2 其他流动资产 |

**→ 06-engineering-governance（+1，清理空壳）**

| Spec | 说明 |
|------|------|
| procedure-delegation-visibility-isolation | 服务端底稿可见性隔离（18/18，2026-07-18 已归档，空壳清理） |

### 2026-07-29 归档（12 个，详见 git log）

**→ 05-business-features（+9）**

| Spec | 说明 |
|------|------|
| advanced-query-consolidation | 高级查询模块合并收敛（12/12） |
| attachment-workpaper-linkage-convergence | 附件↔底稿联动收敛（23/23） |
| f2-adjudication-import-export | F2 审定表导入导出（9/9） |
| f2-detail-ledger-pull | F2 明细表序时账取数（11/11） |
| f2-four-table-extraction-refresh | F2 四表取数刷新（22/22） |
| hi-cycle-four-table-extraction | H/I 循环四表取数（14/14） |
| lmn-four-table-extraction | L/M/N 循环四表取数（12/12） |
| template-library-formula-preset-custom | 模板库公式预设（16/16） |
| work-hours-auto-collect-and-edit | 工时自动采集与编辑（18/18） |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| d-cycle-disclosure-note-enhancement | D3-D7 审定↔披露差异告警（13/13） |

**→ 09-consolidation-phases（+1）**

| Spec | 说明 |
|------|------|
| consol-disclosure-note-persistence | 合并附注 V2 按项目灰度（9/9） |

**→ 11-confirmation-d0-module（+1）**

| Spec | 说明 |
|------|------|
| confirmation-linkage-completion | 函证两价值孤儿正式做完（19/19） |

---

## 三、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| 最高迁移 | `ls backend/migrations/V*.sql \| sort \| tail -1` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 四、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 归档移到 `_archive/{分类}/`，同步更新本文件
3. 分类：01地基 / 02循环 / 03打磨 / 04架构 / 05业务 / 06工程 / 07底稿瘦身 / 08附注 / 09合并 / 10全循环 / 11函证 / 12 2023-06-23批 / 13 2026-06-29批 / 99取代
4. **凭印象禁令**：完成度必须实证
5. 迁移系统 = `backend/migrations/V*.sql`（MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
