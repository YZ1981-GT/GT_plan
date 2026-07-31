# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-07-31
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active 3（`.kiro/specs/` 实测目录数）/ Archived 505 = 总计 508
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
| `d1-four-table-extraction-formula-wiring` | Wave 1~3 ✅ / Wave 4 阻塞 | D1 四表库取数公式接线。Wave 1~3（后端 seed + render 接入 + 公式管理预设）全绿；Wave 4（披露复核+附注同步+浏览器实测）阻塞于灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False 待用户决策。真实数据 render 路径已验证通过 |
| `disclosure-note-follow-actual-content` | 5/13 完成 | 附注跟随底稿实际内容。已完成：空表判定（双侧 38 测试镜像）/ 模板差异五类计算（29 测试）/ legacy 迁移 dry-run 四类分类（32 测试）/ F2 自动同步修复（mounted 防护 bug + 全平台清除 + 覆盖率守卫 + 后端兜底 stale marker 43 测试 + 浏览器实测）/ 缺失链路 Tab 定性→独立立项。**待做**：模板回流写入 / 过期可见性 / legacy 破坏性迁移（阻塞于 columns 补齐）/ 空表折叠 / 全链实测 / 收尾 |
| `k1-four-table-extraction-and-disclosure-alignment` | 25/27 完成 | K1 四表库取数口径根治 + 披露/附注结构对齐。**已完成**：共享件 `four_table/{report_line_accounts,leaf_aggregation}.py`（D1 薄壳委托、零回归）/ K1 render 改叶子口径 + 备抵精确到 `1231-03`（实测坏账 28,464,225.16→900,217.36 虚增 31.6 倍已修、原值 211,252,631.06→269,885,933.03 少 21.7% 已修）/ `tb_source_codes` 溯源面板 / 「从四表库带入未审数」按钮 + FS 三行预填 / 账龄枚举贯通 K1-1（3年段 `over3` 不再丢）/ 公式预设 +6 条 / 附注 §五、8 补源模板 ⑧⑨⑩ 三表 + 上市变动表两级表头 + 账龄 5 年段、§八、9 账龄表还原源模板 3 列 + 忠实推小计/减坏账/合计 / 三向守卫（源 xlsx ↔ 模板 ↔ 载荷）。**待做**：预填浏览器点选（两个在册项目一个已有持久化数据、一个 401）/ 披露推送→附注落库复核 |
| `disclosure-sync-path-buildout` | 缺口 64→24 | 补齐披露 Tab 同步链路。**已完成**：批1 G 循环（G4/G5/G6/G8/G9/G12 接线 + 实测）/ 批2 H 循环（H4Soe/H6×2委托/H7×2）/ 批3 L 循环（L5/L6/L7/L8 接线 + L2/L4 豁免/留缺口）/ 批4 M 部分（M4/M5/M7 标准变动表 6 Tab 接线 + 实测）。**待做**：批5 N 循环（N2/N3/N4/N5 7Tab，但 `n-cycle-tax-disclosure-alignment` 已完成这些→需核实是否已收口）/ 批6 D2·F4·J2 / 收尾归零 |

---

## 二、已归档 Spec（505个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          2
├── 04-infra-architecture/            36
├── 05-business-features/            236
├── 06-engineering-governance/        14
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              38
├── 09-consolidation-phases/           5
├── 10-A~S-workpaper-all-cycles-complete/ 31
├── 11-confirmation-d0-module/        11
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     4
```

### 最近归档（2026-07-31）

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
