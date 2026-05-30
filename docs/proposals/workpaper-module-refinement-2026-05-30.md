# 底稿模块改进优化建议书

> 起草：2026-05-30
> 基线：本机 `main` 分支实测（行数 / 测试 / 卡点状态均为当次 grep 时刻真实值）
> 范围：底稿（Workpaper）模块前端 views + 子组件 + 后端 service + 防退化卡点 + 业务链 + 功能类型 + 证据管理
> 性质：诊断 + 可落地路线图，非立即实施（实施需逐项起 spec 三件套）
> 演进说明：本文档分多轮逐步扩写。**第〇~六章是第一轮"瘦身治理"快照（保留为历史轨迹，勿据此判断全貌）**；真正的全景结论与 spec 总图见 **第二十四章**。下方导航表是 24 章总览。

---

## 文档导航（24 章总览）

| 章 | 主题 | 一句话结论 |
|---|---|---|
| 〇~一 | 结构债快照 | views 已瘦身，债下沉子组件 |
| 二~三 | 卡点失效 + D类测试断层 | check_file_size 路径已修；D类 3646 行零测 |
| 四~六 | 优先级 + 范围边界 | P0 卡点收口 |
| 七~八 | 运行时质量 | float 卡点丢失 / LLM stub / 错误处理残留 |
| 九 | TSJ LLM 复核 | 提示词驱动复核是孤儿能力待接线 |
| 十 | 联动溯源 | 溯源 service 已接线但孤岛化 |
| 十一 | 前端布局 | 侧栏 13 Tab / 8 横幅拥挤 |
| 十二 | HTML 渲染扩展 | 按内容性质而非前缀选格式 |
| 十三 | EDITOR_MAP | 死代码待清理 |
| 十四 | 元复盘 | 查库推翻"两套体系"假设 |
| 十五~十六 | 业务链连通 | 5 条链全通，骨架健康 |
| 十七 | 异构格式追溯 | HTML 渲染器无 cell 定位（核心难点） |
| 十八 | 分阶段路线图 | 收口为 5 spec |
| 十九~二十 | 功能类型谱系 | 14 大类 30+ 细类，functional_type 维度缺失 |
| 二十一 | 抽凭原始凭证 LLM | 需求已设计实现停在正则 |
| 二十二 | 性能/协作/迁移/轨迹/离线/移动端 | 3 真盲区 |
| 二十三 | 多准则 + PBC | 准则状态 4 套口径散落 / PBC 空壳 |
| 二十四 | 全景收敛 | 11 spec + 3 梯队总图 + 元结论 |

> ⚠️ 注：第十八、二十四章曾出现"封口声明"，因用户持续追加规划维度而多轮扩写，封口声明已失效——本文档定位为**持续累积的全维度诊断库**，不再宣称封口。

---

## 〇、执行摘要（第一轮快照，全貌见第二十四章）

底稿模块经过两轮瘦身 spec（`workpaper-list-shrink` / `workpaper-editor-shrink-phase2`），两个主 view 已从 god-component 降到健康区间（WorkpaperEditor 758 行 / WorkpaperList 476 行）。但本次复盘实测发现技术债**没有消失，只是下沉**到三个层面：

1. **防退化卡点本身失效**（最高优先级）：`check_file_size.py` 在目录迁移后白名单路径错误，整个文件大小护城河静默失效；两个已瘦身 view 的白名单基线仍锁在瘦身前的旧值（假绿）。
2. **债下沉到渲染器子组件**：`GtCNoteTable`(1609) / `GtDFormReview`(1537) / `GtDFormConfirmation`(1311) / `GtEControlTest`(1279) 四个超 1500 行 SFC。
3. **D 类渲染器测试断层**：`GtDFormReview` + `GtDFormConfirmation` + `GtDFormParagraph` 共 3646 行**零单测**，违反"骨架未跑测试≠完成"铁律。

本书给出按 ROI 排序的四段路线图：P0 卡点收口（半天）→ P1 测试补齐（2 天）→ P2 子组件拆分（4-5 天）→ P3 后端 service 拆分（2 天）。

---

## 一、实测现状快照（2026-05-30）

### 1.1 前端 views（已健康）

| 文件 | 实测行数 | 状态 |
|---|---|---|
| WorkpaperEditor.vue | 758 | ✅ 已瘦身 |
| WorkpaperList.vue | 476 | ✅ 已瘦身 |
| WorkpaperSummary.vue | 342 | ✅ 健康 |
| WorkpaperWordEditor.vue | 340 | ✅ 健康 |
| WorkpaperHybridEditor.vue | 234 | ✅ 健康 |
| WorkpaperTableEditor.vue | 237 | ✅ 健康 |
| WorkpaperFormEditor.vue | 207 | ✅ 健康 |

views 层不再有 god-component，这是两轮瘦身 spec 的实际成果。

### 1.2 渲染器子组件（债务集中区）

| 文件 | 实测行数 | 上限 | 白名单基线 | 单测 |
|---|---|---|---|---|
| GtCNoteTable.vue | 1609 | 1500 | 1802（松 193） | ✅ 有 |
| GtDFormReview.vue | 1537 | 1500 | 1670（松 133） | ❌ **无** |
| GtDFormConfirmation.vue | 1311 | 1500 | **未登记** | ❌ **无** |
| GtEControlTest.vue | 1279 | 1500 | **未登记** | ✅ 有 |
| GtDFormQA.vue | 1107 | 1500 | — | ✅ 有 |
| GtDFormTable.vue | 895 | 1500 | — | （部分） |
| GtDFormParagraph.vue | 798 | 1500 | — | ❌ **无** |
| GtAProgramConsole.vue | 691 | 1500 | — | ✅ 有 |

### 1.3 后端 service（最大文件）

| 文件 | 实测行数 | 上限 | 白名单基线 |
|---|---|---|---|
| workpaper_fill_service.py | 1587 | 800 | 1817（松 230） |
| prefill_engine.py | 1304 | 800 | 1511（松 207） |
| wp_template_init_service.py | 985 | 800 | 未登记 |

backend 共 60+ 个 `wp_*` / `workpaper_*` service，数量本身偏多但多数 ≤ 300 行（职责单一，健康）。问题集中在最大的两个取数 service。

---

## 二、问题诊断

### P0-1：文件大小护城河静默失效（已修复）

**根因**：`backend/scripts/check/check_file_size.py` 从 `backend/scripts/` 迁入 `check/` 子目录后，`WHITELIST_FILE = Path(__file__).parent / "file_size_whitelist.txt"` 指向不存在的 `check/file_size_whitelist.txt`。`load_whitelist()` 遇文件不存在静默返回空 dict，导致：

- 所有 52 个历史大文件不再被豁免 → pre-commit 时全部误判"超限"
- 开发者被迫习惯性 `git commit --no-verify` 绕过 → 卡点形同虚设
- 同时白名单"膨胀检测"（基线 +5% 报警）也失效 → 大文件可无限增长

**影响范围**：仅 `.pre-commit-config.yaml` 调用（CI workflow 未调用 file_size 卡点，故 CI 无漏检）。但 pre-commit 是本地第一道防线，失效后所有体积治理无感知退化。

**修复**：`WHITELIST_FILE = ROOT / "backend" / "scripts" / "file_size_whitelist.txt"`（与同目录 `check_hotspot_files.py` 同款显式路径写法），已恢复 52 条基线加载。本次同时修复了同批次的 `parents[2]→[3]` ROOT 路径 bug。

**铁律沉淀**：脚本依赖的数据文件路径必须用 `ROOT / 显式相对路径`，禁止用 `Path(__file__).parent`——后者在目录迁移时失效且静默不报错。

### P0-2：已瘦身 view 的白名单假绿

`WorkpaperEditor.vue` 实测 758 行但白名单锁 **2342**（松弛 1584 行）；`WorkpaperList.vue` 实测 476 行但白名单锁 **3464**（松弛 2988 行）。这意味着卡点允许这两个文件涨回 3 倍才报警——瘦身成果完全没有被卡点保护，随时可悄悄膨胀回去。

### P1：D 类渲染器测试断层

`GtDFormReview`(1537) + `GtDFormConfirmation`(1311) + `GtDFormParagraph`(798) = **3646 行零单测**。这是 D 类销售收入循环的核心渲染器（复核流程 / 函证 / 段落），承载状态机流转、签字链、字段联动等复杂逻辑。无测试的大组件违反项目"骨架未跑测试≠完成"铁律，且让后续拆分变成"盲拆"（无回归保护）。

实测确认有测的：GtDFormQA（业务模式判定 27 用例）、GtCNoteTable（继承规则校验等）、GtEControlTest、GtAProgramConsole。

### P2：渲染器子组件 god-component

四个超 1500 行 SFC（GtCNoteTable / GtDFormReview / GtDFormConfirmation / GtEControlTest）。其中两个还游离在白名单之外（GtDFormConfirmation / GtEControlTest 未登记），意味着它们既超限又不被任何基线追踪——一旦 P0-1 卡点恢复，这两个会直接触发 pre-commit 阻断。

### P3：后端取数 service 偏大

`workpaper_fill_service.py`(1587) 单文件混合了 6 类职责：fill-task 生命周期、5 个 prompt builder、分析性复核、底稿数据生成、附注初稿生成、智能复核。职责边界清晰但堆在一个文件，任何一类改动都要碰 1587 行。

---

## 三、改进路线图（按 ROI 排序）

### P0 — 卡点收口（半天，零代码风险）

**目标**：让防退化护城河真正生效，锁住已有瘦身成果。

| 任务 | 动作 | 验证 |
|---|---|---|
| P0-1 ✅ 已完成 | 修复 `check_file_size.py` whitelist 路径 + 4 脚本 ROOT 层级 | `load_whitelist()` 返回 52 条 |
| P0-2 | 收紧 view 白名单：WorkpaperEditor 2342→820、WorkpaperList 3464→520 | pre-commit 不破基线 |
| P0-3 | 登记两个游离子组件：GtDFormConfirmation 1311→~1380、GtEControlTest 1279→~1350（先登记现状防阻断，标注"待拆"） | pre-commit 通过 |
| P0-4 | 刷新 `INDEX.md` §1/§2/§4 过时计数（WorkpaperEditor 写 2167 实为 758 等） | 文档与实测一致 |

P0-2 与 P0-3 是同一文件（`file_size_whitelist.txt`）的纯配置改动，无代码风险，应一次做完。

### P1 — D 类渲染器测试补齐（2 天）

**目标**：消除 3646 行零单测断层，为后续拆分提供回归保护。

| 任务 | 内容 |
|---|---|
| P1-1 | `GtDFormReview.spec.ts`：状态机流转（onTransitionClick）、签字/撤销（onSignClick/canUnsign）、字段联动（setStepField/onChecklistChange）、debounce save payload |
| P1-2 | `GtDFormConfirmation.spec.ts`：函证字段填充、状态切换、save payload |
| P1-3 | `GtDFormParagraph.spec.ts`：段落渲染、变量插值、readonly 模式 |

测试模式可复用现有 `GtDFormQA.spec.ts` / `GtCNoteTable.spec.ts` 的范式（Element Plus stubs + fake timers + mount props）。**测试必须先于拆分**——否则拆分无回归保护。

### P2 — 渲染器子组件拆分（4-5 天，已有 README stub）

**目标**：四个超 1500 行 SFC 降到单文件 ≤ 400 行。已有 `gt-c-note-table-shrink` spec README，需扩展覆盖 D 类。

GtCNoteTable / GtEControlTest 的拆分方案见 `.kiro/specs/gt-c-note-table-shrink/README.md`（GtCNoteTable 拆 5 子组件按 Header/Body/Merge/Penetrate/Comments；GtEControlTest 拆 7 按 6 步骤 + 结论）。

本书补充 D 类拆分建议（依赖 P1 测试先行）：

- **GtDFormReview**(1537)：script 块逻辑分层清晰，可抽 composable —— `useReviewStateMachine`（状态机流转 + 审计日志）/ `useReviewSignature`（签字链 + 撤销规则）/ `useReviewFields`（步骤字段 + checklist + 联动）；shell ≤ 400 行。
- **GtDFormConfirmation**(1311)：抽 `useConfirmationFields` + `useConfirmationState`；shell ≤ 400 行。

**关键铁律**（来自 WorkpaperEditor 瘦身教训）：setup const 声明顺序——`const X = useY(..., Z)` 引用的 Z 必须在 X 之前定义，链式依赖按拓扑顺序写。

### P3 — 后端取数 service 拆分（2 天，已有 README stub）

**目标**：`workpaper_fill_service.py`(1587) 拆为职责单一的多个 ≤ 500 行 service。

已有 `.kiro/specs/workpaper-fill-service-split/README.md` 方案（拆 wp_prefill_engine / wp_formula_parser / wp_cell_writeback / wp_snapshot_diff，原文件退化为 facade）。

实测补充：当前文件按方法分布天然可分为 6 段——fill-task 生命周期（46-401）/ 分析性复核（403-768）/ 底稿数据生成（769-1195）/ 附注初稿（1196-1516）/ 智能复核（1518-末尾）。拆分时这些 `# ===` 分隔的区块是天然边界。验收要求现有调用方（router_registry/prefill / chain_orchestrator / wp_cross_check_service）零改动通过。

---

## 四、优先级与依赖关系

```
P0 卡点收口 (半天) ──┐
                     ├──> 独立，立即可做，无前置
P1 D类测试 (2天) ────┘
        │
        └──> P2 D类拆分（必须 P1 在先，否则盲拆）

P2 C/E类拆分 ──> 独立（已有测试），可与 P1 并行
P3 后端拆分 ──> 独立（已有测试），纯后端无外部依赖，可随时启动
```

**建议执行顺序**：
1. **P0**（半天）—— 最便宜，直接堵住"瘦身白做"风险，且 P0-1 已完成
2. **P1**（2 天）—— 质量底线，且是 P2-D 的前置
3. **P3** 或 **P2-CE**（并行候选）—— 都有测试保护，无相互依赖，按"触碰即拆"原则在动到对应功能时启动
4. **P2-D**（依赖 P1 完成）

## 五、范围边界（不做）

- 不修改任何 prefill / 渲染 / cycle 业务逻辑（仅做结构拆分 + 测试补齐 + 卡点修复）
- 不改 DB schema / migration / router 路径
- 不引入新依赖、不改技术选型（HTML 渲染器 / Univer 双轨保持）
- 不动 GtDFormQA / GtAProgramConsole（已健康或临界可接受）

## 六、验收总标准

- pre-commit `check_file_size` 全绿（白名单生效 + 无新增超限 + 无膨胀）
- D 类三渲染器单测覆盖关键交互逻辑，vitest 0 fail
- 拆分后所有现有 vitest / pytest 0 回归，vue-tsc 0 errors
- 拆分后单文件：前端 SFC ≤ 400 行 / 后端 service ≤ 500 行
- `INDEX.md` 计数与实测一致

---

> 附：本书所有行数为 2026-05-30 实测，依"实测有效期=单次 grep 时刻"铁律，立项前需按当时分支重测。

---

## 七、第二轮复盘补充（2026-05-30，运行时/功能维度）

第一轮（一~六章）聚焦**结构债**（体积/测试/卡点）。第二轮转向上一轮未覆盖的**运行时质量、数据一致性、功能完整度**维度，新发现四类问题：

### P0-5：金额 Decimal 化卡点已丢失（防退化护城河缺口）

V3 spec Req 2 建立的"金额 Decimal 化铁律"配套卡点 `scripts/_check_no_float_amount.py`（design 声明 CI 调用、baseline 15）**实测已不存在**：

- `fileSearch check_no_float_amount` → 0 命中（`_` 前缀一次性脚本，疑似用完即删或未合入本分支）
- `.github/workflows/*.yml` grep `float` → 0 命中（CI 从未真正调用该卡点）

后果：底稿后端大量 service 仍用 `float()` 处理金额且**无防退化保护**，可自由退化。实测 `float()` 金额用法分布在 `wp_ai_service`（取数 audited_debit-credit）/ `wp_explanation_service` / `wp_chat_service`（借贷汇总）/ `wp_cross_check_service` / `workpaper_summary_service` 等 10+ service。

**风险分级**（实测后细化，非一刀切）：
- **低风险（可接受）**：`wp_cross_check_service` 的核心勾稽比对实际用 Decimal + `DEFAULT_TOLERANCE` 容差，`float()` 仅用于输出 JSON 序列化——逻辑安全。
- **需复核**：`wp_ai_service` / `wp_explanation_service` 的 `float(debit) - float(credit)` 在送 LLM 前做差额计算，若结果回写底稿则有精度损失风险。

**建议**：重建 `backend/scripts/check/check_no_float_amount.py`（去 `_` 前缀转正式工具，与 check_file_size 同目录）+ 跑一次确定真实 baseline + 接入 pre-commit。**这是 P0 卡点收口的一部分，应与 P0-2/P0-3 白名单收紧合并做**。

### P1-4：LLM 链路 stub（功能完整度债）

底稿模块 6+ 个 AI 计算对话框仍是 `is_llm_stub` 实现（前端已有 `⚠️ Stub 模式（待 AI 服务接入）` 提示 tag）：

- `InventoryImpairmentDialog`（存货跌价）/ `IncomeTaxCalcDialog`（所得税）/ `ImpairmentSummaryDialog`（减值汇总）/ `SharePaymentDialog`（股份支付）/ `PayrollCalcDialog`（薪酬）/ `InterestCalcDialog`（利息）

这些对话框 UI + 写回链路完整，仅 LLM 分析返回 stub 数据。属于已知功能待办（memory「6 stub 引擎 + LLM 链路 3 bug」），**前置阻塞 = vLLM/httpx 链路 3 bug 未修**（httpx 系统代理 mounts={}+trust_env=False / vLLM chat_template_kwargs 顶层 / thinking content=None length 分支）。

**建议**：先修 `vllm-httpx-bugfix`（1 天，已有 spec 候选），再用 `settings.WP_AI_SERVICE_ENABLED` 一键切换关闭 stub。不属于本"结构优化"范围，列为关联功能待办。

### P2-2：前端错误处理 component 层残留

底稿组件错误处理整体一致（多数用 `handleApiError(e, context)`），但有残留：

- **裸 `ElMessage.error`**：`ProcedureTrimmingPanel`（3 处，业务校验 result.message）/ `SideTimerTab` / `ItemAttachment`（beforeUpload 文件大小）/ `InventoryStocktakeDialog`（签字校验）—— 其中文件大小/签字校验属业务校验（可保留），ProcedureTrimming 的 `result.message` 应走统一封装
- **手工拼接 message**：`WorkpaperAuditNav` / `SideStandardsTab` / `PriorYearCompareDrawer` / `OcrFieldsDrawer` / `LedgerPenetrateDrawer` 用 `error.value = '...' + err.message` 模式 —— 与 M1 spec 治理的 catch 裸用同类

M1 spec 主要扫 `views/`，component 层（尤其 `components/workpaper/`）未纳入。**建议**：M1 的 `audit-elmessage-error.mjs` AST 脚本扩展扫描范围到 `components/workpaper/`，作为 M2 联动闭环的一部分。

### P3-2：后端静默吞错 `except Exception: pass`

`wp_xlsx_export_service`（calculate_dimension / cell 样式）/ `wp_template_init_service`（rollback / 样式写入）/ `wp_header_service` / `wp_generic_processor` 多处 `except Exception: pass` 静默吞错。多数是**合理的非阻断降级**（如只读单元格无法设样式、维度计算失败忽略），但缺少 `logger.debug` 留痕的几处应补日志，便于排查"底稿导出样式丢失"类问题。

**建议**：低优先级，触碰 xlsx 导出功能时顺手给裸 `pass` 补一行 `logger.debug`。属代码卫生，不单独立项。

---

## 八、第二轮复盘后的优先级修订

| 优先级 | 任务 | 工时 | 变化 |
|---|---|---|---|
| **P0** | 卡点收口：①✅ check_file_size 路径 ②view 白名单收紧 ③游离子组件登记 ④**重建 float 金额卡点** ⑤INDEX 刷新 | 1 天 | +float 卡点 |
| **P1** | D 类渲染器测试补齐（Review/Confirmation/Paragraph 3646 行零测） | 2 天 | 不变 |
| **P2** | 子组件拆分（C/E 已有测试可并行 / D 依赖 P1）+ 错误处理 component 层扩扫 | 4-5 天 | +错误处理扩扫 |
| **P3** | 后端 service 拆分 + 静默吞错补日志 | 2 天 | +日志卫生 |
| **关联** | vllm-httpx-bugfix（解锁 6 个 stub AI 对话框） | 1 天 | 新列（功能债，非结构） |

**核心结论不变**：P0 最便宜且堵风险（现扩展到含 float 卡点重建），应先做；P1 是 P2-D 的前置。LLM stub 是独立功能线，不阻塞结构优化。

> 附：第二轮所有结论同样遵循"实测有效期=单次 grep 时刻"铁律，立项前需重测。


---

## 九、第三轮复盘：融合 TSJ 提示词的 LLM 复核功能（2026-05-30）

前两轮聚焦结构债与运行时质量。第三轮专题论证**如何把 `backend/data/tsj_review_prompts/` 的 70 科目复核提示词融入底稿 LLM 审核**——这是"人机互补"的核心场景：提示词是资深合伙人沉淀的复核框架，LLM 是执行引擎，底稿是被审对象。

### 9.1 现状勘察（实测，非臆测）

底稿模块的 AI 复核基础设施**比想象中完整**，问题在于"半成品 + 没接线 + 各自为政"：

| 能力 | 位置 | 状态 | 用途 |
|---|---|---|---|
| TSJ 结构化提取 | `tsj_prompt_service`（tips/checklist/risk_areas） | ✅ 已接线 | wp_mapping `/tsj/{account}` |
| TSJ 原文侧栏 | `knowledge_tsj` router + `SideStandardsTab.vue` | ✅ 已接线 | 底稿"准则"Tab（只读参考） |
| TSJ 驱动结构化复核 | `workpaper_fill_service.review_workpaper_with_prompt` | 🔴 **孤儿（未接 router）** | 提示词逐项检查底稿 |
| 分析性复核 | `wp_ai.py` `/ai/analytical-review` + `wp_ai_service` | ✅ 已接线 | 变动分析（未用 TSJ） |
| AI 辅助填写 | `wp_ai.py` `/ai/suggest` | ✅ 已接线 | 字段建议（未用 TSJ） |
| AI 内容溯源 | `AiContent` 模型（risk_alert 类型）+ V3 Req6 确认机制 | ✅ 已就绪 | 强制人工确认 + 审计轨迹 |
| AI 对话侧栏 | `AiAssistantSidebar.vue` + `/ai/chat` | ✅ 已接线 | 自由问答 |

**核心矛盾**：最有价值的 `review_workpaper_with_prompt`（完整提示词驱动复核：底稿→audit_cycle→匹配 TSJ→注入 system prompt→逐项检查→存 ai_content）**写好了却没人能调用**。而已接线的分析性复核 / suggest 又**没有用上 TSJ 提示词**（各自硬编码自己的 prompt）。

### 9.2 关键缺陷诊断

**缺陷 1 — 复核能力是孤儿**：`review_workpaper_with_prompt` 无 router 暴露，前端无入口。

**缺陷 2 — TSJ 与 AI 执行链路割裂**：
- `SideStandardsTab` 把 TSJ 当**静态文档**给人看（marked 渲染），没喂给 LLM
- `analytical_review` / `suggest` 用**自己的 prompt**，不读 TSJ
- 结果：提示词资产只发挥了"给人看"的一半价值，没发挥"驱动 AI 逐项核对"的另一半

**缺陷 3 — 整文件单次调用，输出非结构化**：
- 8000 字符截断（大底稿被砍）
- 不按 sheet / 认定拆分（一次性塞整个底稿）
- 输出是自由文本，没解析成结构化发现（TSJ 明明定义了精确格式：`问题类型 + 数值/逻辑错误 + sheet!单元格 + 严重程度 + 整改建议`）
- 没回写 `AiContent.risk_alert` 关联到具体 cell

**缺陷 4 — LLM 链路 3 bug 是共同前置**（httpx 代理 / vLLM chat_template / thinking length），不修则所有 AI 复核返回 stub/报错。

### 9.3 融合方案（分层，最小可用先行）

#### MVP（约 1 天）：接线 + 修路，让已有能力跑起来

1. **接线复核端点**：`wp_ai.py` 新增 `POST /api/workpapers/{wp_id}/ai/tsj-review`，调用已有 `review_workpaper_with_prompt`，`WP_AI_SERVICE_ENABLED` 门控（与 suggest 同模式）
2. **修 LLM 链路 3 bug**（vllm-httpx-bugfix，已有 spec 候选）——这是硬前置
3. **前端入口**：`SideStandardsTab`（已展示 TSJ 原文）加一个「🤖 用此提示词复核当前底稿」按钮，调上述端点；复核结果进 `AiAssistantSidebar` 或独立 drawer

MVP 完成后，"看提示词"和"用提示词复核"在同一个面板闭环。

#### 增强版（约 3-4 天）：结构化逐项复核

4. **按认定分段复核**：不再整文件单次调用，而是按 TSJ 的认定章节（存在性/完整性/准确性/权利义务/分类）分段，每段独立 LLM 调用 + 独立 token 预算，规避 8000 截断
5. **结构化输出解析**：要求 LLM 按 TSJ 定义的格式输出 JSON（`{问题类型, 严重程度, sheet, 单元格范围, 数值/逻辑描述, 证据关联, 整改建议}`），后端解析后逐条写入 `AiContent`（content_type=risk_alert）并关联 `target_cell`
6. **复核发现进确认流**：复用 V3 Req6 的 `AiContentMustBeConfirmedRule` —— AI 复核发现默认 pending，审计师逐条确认/驳回/采纳，形成人机互补闭环（用户原话「全面体现人机互补」）
7. **风险分级可视化**：TSJ 的【必检】/【条件检查】/【风险检查】+ 高/中/低映射到前端 tag，复核报告按严重程度排序（一级问题置顶）

#### 智能版（独立 Sprint，依赖真实数据 + 6000 并发验证）

8. **自动取数喂数据**：复核前先用 `wp_auto_fill_service` 把底稿 TB/WP/REPORT 实际数填进 prompt，让 LLM 基于真实数字核对（而非只看模板结构）
9. **跨底稿勾稽融入**：把 `wp_cross_check_service` 的 L1/L2 勾稽结果作为 LLM 复核的输入证据
10. **批量复核**：项目经理一键复核整个循环的所有底稿（D 类全部），结果汇总到 PM 收件箱

### 9.4 落地优先级与依赖

```
vllm-httpx-bugfix (1天) ──→ [硬前置，解锁所有 AI 复核]
        │
        ├──→ MVP 接线 (1天) ──→ 增强版结构化 (3-4天) ──→ 智能版 (独立Sprint)
        │
        └──→ 同时解锁第七章 P1-4 的 6 个 stub AI 对话框
```

**建议**：先做 `vllm-httpx-bugfix`（一举解锁 TSJ 复核 + 6 个 stub 对话框两条线），再做 TSJ MVP 接线（投入小、价值立现）。增强版的结构化输出是真正发挥 TSJ 价值的关键，但需要 LLM 链路稳定后再做。

### 9.5 不在范围

- 不改 TSJ 提示词内容本身（提示词是审计专家资产，由业务侧维护）
- 不替换现有 `analytical_review` / `suggest`（它们服务不同场景，可后续逐步改为读 TSJ）
- 不做提示词的可视化编辑器（提示词维护走 md 文件 + git）

> 附：第三轮所有结论基于 2026-05-30 实测代码勘察，立项前需按当时分支重测。


---

## 十、第四轮复盘：跨模块联动与溯源（2026-05-30）

本轮专题勘察底稿与四表（试算表）/调整分录/附件/报表/附注之间的**联动**（数据变化的级联传播）与**溯源**（追溯一个数字从哪来、影响到哪）。结论先行：**联动骨架相当完整且已接线，溯源能力也已存在但分散割裂**——问题不是"缺能力"，而是"能力孤岛 + 闭环缺失 + 反向链路不全"。

### 10.1 现状盘点（实测核实，已纠正子代理两处误判）

**联动事件机制（成熟）**：
- `EventBus`（debounce 500ms 去重 + Redis Stream 持久化 + SSE fan-out）+ 40+ `EventType` + 30+ handler 已注册
- 正向数据流闭环完整：`调整分录→TB→报表→附注→审计报告`（ADJUSTMENT_* → TrialBalanceService → TRIAL_BALANCE_UPDATED → ReportEngine → REPORTS_UPDATED → DisclosureEngine + AuditReportService）
- 底稿保存 → WORKPAPER_SAVED → 一致性检查 + prefill stale 标记
- 跨底稿引用 `cross_wp_references.json` 400+ 条（H9↔H8 租赁反向回填等）

**溯源能力（已存在且已接线，子代理误判为"缺失/无统一 service"）**：
- ✅ `wp_trace_service` + `wp_trace.py` router：`trace_upstream`（哪些上游单元格喂入此对象）/ `trace_downstream`（此对象影响哪些下游）
- ✅ `report_trace_service` + `report_trace.py` router：`GET /api/report-review/{pid}/trace/{section}` = 附注章节→底稿→试算表→序时账**完整四级链**
- ✅ `version_line_service.query_lineage`：版本血缘
- ✅ `cell_provenance`（prefill_engine 回写到 `parsed_data.cell_provenance`，记录每个单元格的公式来源 TB/WP/REPORT）
- ✅ 前端溯源 UI 多处：TrialBalance 右键「🔍 数据溯源」+ ReportView 溯源浮动条/多定位选择弹窗/「溯源定位」列 + GtTraceabilityDialog + usePenetrate 12 穿透方法 + useNavigationStack（Backspace 返回栈，MAX_DEPTH 20）

**stale 传播（部分）**：
- `is_stale` 字段在 FinancialReport / DisclosureNote / AuditReport 三表
- 触发：账套回滚（`_mark_downstream_stale_on_rollback`）/ 调整分录变更（`_mark_workpapers_stale_by_account`）/ 子公司附注→合并附注（`consol_note_stale_handler`）
- 前端 `useNoteStale` 订阅 3 事件显示"建议重算"

**跨模块冲突调解（成熟）**：
- `cross_module_conflicts` 表 + `conflict_resolution_service`（enqueue/resolve/auto_resolve）+ manual_override 前置守卫（user_edit→入队 pending，system_recompute→自动接受）

### 10.2 真正的缺口诊断（经核实）

不是"没有溯源"，而是以下结构性问题：

**缺口 1 — 溯源能力孤岛化，缺统一入口**：
存在 3 个独立溯源 service（`wp_trace` / `report_trace` / `version_line`）+ 散落的前端溯源 UI（TrialBalance 右键 / ReportView 浮动条 / GtTraceabilityDialog），但**各做各的、数据格式不统一、入口分散**。同一个"这个数字从哪来"的问题，在不同模块要走不同 UI、调不同端点、看不同格式。缺一个**统一的溯源面板**（给定任意对象 = TB行/底稿cell/报表行/附注cell/调整分录，统一返回完整上下游血缘图）。

**缺口 2 — 反向溯源链路不全**：
- 正向（上游→下游）较全：TB→报表→附注
- 反向（下游→上游）有断点：`report_trace` 能做附注→底稿→TB→序时账（已接线），但**附注 cell → 具体底稿 cell** 的精确反查、**附件 → 引用它的底稿/报表行/附注** 的反查缺失
- `usePenetrate` 有 `toReportFromNote`（附注→报表）但**无 `toWorkpaperFromNote`**（附注→底稿直达）

**缺口 3 — 附件（attachment）游离在联动网络外**：
- 底稿附件（wp_attachments）只与底稿关联，没有进入溯源网络
- 无法回答"这张银行回单支撑了报表哪一行/附注哪个数字"——而 TSJ 提示词反复要求"每个问题必须关联至少 1 个审计证据底稿位置"，附件正是证据载体

**缺口 4 — stale 传播是全量标记，无增量 + 无可视化影响范围**：
- 当前 stale 标记是"同项目同年度全标记"，大项目（6000 并发目标 / 65 万行）性能堪忧
- 用户改一个调整分录，看不到"这会让哪 3 张底稿 + 2 个报表行 + 1 个附注变 stale"的**影响范围预览**（`linkage.get_impact_preview` 存在但未串成可视化）

**缺口 5 — 联动可观测性弱**：
- 事件链路只有 DEBUG 日志，出问题（如"改了调整分录但报表没更新"）难排查
- 无"联动健康度"面板显示事件是否正常级联

### 10.3 改进方案（分层，复用已有资产）

#### P1 — 统一溯源面板（3-4 天，价值最高）
把 3 个孤岛 service 收口到一个统一端点 + 一个统一前端组件：
- 后端：`GET /api/projects/{pid}/lineage?object_type=&object_id=&direction=both` 统一返回 `{upstream:[], downstream:[], current:{}}` 血缘图，内部委托现有 3 个 trace service
- 前端：`LineageGraphPanel.vue` 统一血缘图（复用现有 GtTraceabilityDialog 但升级为图谱视图），任意模块右键「数据溯源」都打开同一面板
- 复用：`cell_provenance` 已记录单元格级来源，是统一溯源的数据基础

#### P2 — 补齐反向链路 + 附件入网（3 天）
- `usePenetrate` 补 `toWorkpaperFromNote`（附注 cell → 底稿 cell 直达，后端用 report_trace 的反查能力）
- 附件溯源：建立 `attachment ↔ {wp_cell, report_row, note_section}` 关联表，让附件进入溯源网络（呼应 TSJ"问题关联证据"要求 + 第九章 TSJ 复核可直接跳证据）

#### P3 — stale 影响范围预览 + 增量传播（2-3 天，依赖性能验证）
- 把 `linkage.get_impact_preview` 串成 UI：改调整分录/底稿前，弹出"将影响 N 张底稿 / M 报表行 / K 附注"预览
- stale 标记从全量改增量（按 account_code/wp_code 精确传播，呼应第二章 P0 性能视角）

#### P4 — 联动可观测性（2 天，呼应 observability-baseline spec）
- `event_cascade_health` 面板：显示各 EventType 最近触发时间 + 级联成功率
- 联动失败（SYNC_FAILED）告警进前端 banner

### 10.4 与前几轮的协同

- 第九章 TSJ 复核 **依赖** 本章溯源：LLM 复核发现问题后，"关联证据底稿位置"正是靠统一溯源面板 + 附件入网（缺口 2/3）落地
- 第二章 P0 性能视角与本章缺口 4（stale 增量）同源
- 统一溯源面板（P1）是后续所有"人机互补"功能的基础设施

### 10.5 不在范围
- 不改 EventBus / 现有正向数据流（已成熟，不动）
- 不重写现有 3 个 trace service（收口到统一入口，内部复用）
- 不改 cross_wp_references.json 引用数据

> 附：第四轮基于 2026-05-30 实测 + context-gatherer 子代理梳理 + 人工核实纠正（溯源 service 实际已接线，非子代理所述"缺失"）；立项前需按当时分支重测。


---

## 十一、第五轮复盘：前端布局与用户提示（2026-05-30）

本轮专题勘察底稿模块的**界面布局密度**与**用户引导/提示**。结论：核心交互框架（壳瘦身 + 配置驱动工具栏 + lazy tab + keep-alive）已是良好实践，但**几处界面信息密度过高**，且**新用户缺乏渐进引导**。问题集中在"什么都想露出来"导致的视觉过载。

### 11.1 拥挤点实测盘点

**🔴 拥挤点 1 — WorkpaperSidePanel 13 个 Tab 挤在 400px 抽屉**（最严重）：
实测标签：AI / 附件 / 版本 / 批注 / 程序 / 程序要求 / 依赖 / 一致性 / 公式 / 证据 / 复核标记 / 自检 / 提示 —— **13 个 tab + `stretch` 平铺在 400px 宽抽屉**，每个标签仅约 30px，中文标签必然换行或截断，用户根本扫不过来，也记不住哪个功能在哪个 tab。这是典型的"功能堆砌"反模式。

**🔴 拥挤点 2 — EditorBanners 8 类横幅垂直堆叠**：
归档 / AI pending / 跨模块冲突 / 数字信任度 / 状态机 / 编辑锁 / 前置状态 / stale 影响范围 —— 8 类横幅各自 `v-if` 但**同时满足条件时垂直堆叠**，把真正的编辑区域（Univer/HTML 渲染器）往下挤。极端情况下用户打开底稿先看到 4-5 条横幅才看到表格。

**🟡 拥挤点 3 — 编辑器顶部工具栏一行塞满**：
左侧：返回 + wp_code + wp_name + 状态 tag + dirty 指示；右侧：复核 badge + 审计导航图 + 主操作组(保存/填充/提交) + 更多▾ + 面板 badge + 独立按钮组(刷新取数)。**单行 10+ 元素**，窄屏必然换行错位。

**🟡 拥挤点 4 — WorkpaperList 7 视图切换 + 多按钮工具栏**：
视图 radio：列表/工作台/看板/依赖图/手册/生命周期/委派矩阵 7 个 + 工具栏：导入/刷新/批量下载/批量委派 + 筛选栏 4 个下拉。顶部信息密度偏高（虽已用 GtToolbar 合并，仍偏满）。

### 11.2 已有的良好实践（保持，不要破坏）

实测确认这些做对了，新方案应在其上叠加而非推翻：
- ✅ 工具栏「更多 ▾」dropdown 收纳次要操作（配置驱动 `toolbarDropdownItems`）
- ✅ 所有侧栏 tab `lazy` 加载 + keep-alive max 5
- ✅ 侧栏 tab 上 `el-badge` 显示自检失败数/复核标记数/冲突数（信息前置）
- ✅ `GtEmpty` 空状态 preset + 子编辑器加载失败 overlay 引导
- ✅ WorkpaperList「手册」视图（体系总览/审计流程/底稿关系/循环详解）= 已有的体系级引导
- ✅ 侧栏抽屉 `:modal="false"` 不遮挡主区（可边看边编辑）

### 11.3 布局优化建议（按功能分组 + 渐进披露）

#### P1 — 侧栏 13 Tab 按功能分组收敛（2-3 天，价值最高）
把 13 个平铺 tab 重组为 **4 个功能组**，用二级结构或分组下拉：

| 功能组 | 包含原 tab | 高频度 |
|---|---|---|
| **编制辅助** | AI / 程序 / 程序要求 / 提示 | 高（编制时常用） |
| **质量检查** | 自检 / 一致性 / 公式 / 复核标记 | 高（自检+复核） |
| **追溯关联** | 附件 / 依赖 / 证据 / 批注 | 中 |
| **历史版本** | 版本 | 低 |

方案选型（二选一）：
- **A. 分组 tab**：一级 4 组 + 组内二级切换（`el-tabs` 嵌套 or 顶部分组 + 下方子标签）
- **B. 高频直显 + 低频收纳**：默认显示编制辅助 + 质量检查的高频 tab，其余进「更多面板 ▾」下拉
推荐 A（结构清晰、可发现性好）。**保留所有 badge 数字上浮到组标签**（如"质量检查 ⑶"汇总组内未处理数）。

#### P2 — 横幅折叠为统一通知条（2 天）
8 类横幅改为**单条可展开的"状态提示条"**：
- 默认收起为一行：`⚠ 3 项待处理（冲突 1 / AI 待确认 1 / 前置未完成 1）` + 「展开」
- 展开后才显示各横幅详情
- 归档/编辑锁这类**阻断性**状态保持常驻显眼（不折叠），信息类（信任度/状态机/stale）折叠进通知条
- 复用已有 banner 组件，只加一层折叠容器 + 计数聚合

#### P3 — 工具栏分层 + 响应式（1-2 天）
- 左侧 wp_code/name/状态/dirty 保持（标识信息）
- 右侧按使用频率三层：**主操作组**(保存/填充/提交) 直显 → **常用**(面板/刷新取数) 直显 → **次要**(导航图/复核badge/版本/导出) 全进「更多 ▾」
- 窄屏（<1280px）自动把主操作组也收进 dropdown，只留保存

### 11.4 用户提示增强建议

#### P1 — 首次进入渐进引导（2 天）
- 底稿编辑器首次打开：轻量 spotlight 引导（保存在哪、面板有什么、如何穿透溯源），可「跳过」+ 「不再提示」（localStorage）
- 复用 memory 提到的 `useWpOnboardingGuide` composable（若已存在则接线，未完成则补全）
- 侧栏分组后，每组首次点开显示一句话说明该组用途

#### P2 — 空状态与操作反馈强化（1-2 天）
- 13 个侧栏 tab 的"请先选择底稿"占位统一为 `GtEmpty` + 该 tab 用途说明（如证据 tab 空态："关联审计证据，支撑底稿结论。点击上方 + 添加"）
- 危险/重要操作（提交复核/一键填充覆盖）增加结果预览提示（呼应第十章 stale 影响预览）

#### P3 — 上下文提示（hover/图标说明）（1 天）
- 工具栏图标按钮补 `el-tooltip`（部分已有，盘点补齐）
- 状态 tag、badge 数字 hover 显示含义（如"自检 ⑶" hover → "3 项自检未通过，点击查看"）

### 11.5 落地优先级

```
P1 侧栏 13→4 组收敛 (2-3天，最大体感提升)
P1 首次渐进引导 (2天，降低上手门槛)
        ↓
P2 横幅折叠通知条 (2天) + 空状态强化 (1-2天)
        ↓
P3 工具栏分层响应式 (1-2天) + 上下文提示 (1天)
```

建议先做**侧栏分组**（P1）——它是体感最强的拥挤点，且不涉及业务逻辑改动（纯 template 重组 + 保留所有现有子组件）。

### 11.6 设计原则（沉淀为后续 UI 铁律候选）
- **渐进披露**：高频直显、低频收纳，不要"什么都露出来"
- **功能分组优于平铺**：>6 个同级 tab/按钮必须分组
- **阻断性 vs 信息性区分**：阻断状态常驻显眼，信息提示可折叠
- **每个空状态都是引导机会**：占位文案说明该区域用途 + 下一步操作

### 11.7 不在范围
- 不改各子面板/对话框内部功能逻辑（仅重组布局容器）
- 不删任何现有 tab/功能（收纳 ≠ 删除）
- 不引入新 UI 库（driver.js 类引导可用现有 el-popover/el-tour 实现，Element Plus 2.4+ 自带 `el-tour`）

> 附：第五轮基于 2026-05-30 实测前端 template 结构（WorkpaperEditor 758 行壳 / WorkpaperSidePanel 13 tab / EditorBanners 8 横幅 / WorkpaperList 7 视图）；立项前需按当时分支重测。


---

## 十二、第六轮复盘：底稿内容呈现样式（HTML 原生渲染的扩展）（2026-05-30）

本轮针对"底稿内容呈现样式"——用户洞察是：**有些底稿（如程序表）天然适合 HTML 原生样式，能支持点击跳转、视觉美观、一目了然，呈现不应拘泥于电子表格格式，以实用为主**。勘察确认这个方向已有坚实基础，但**覆盖不全、判定僵化**。

### 12.1 现状：双轨渲染已成型，HTML 类呈现优秀

底稿编辑器是 **HTML 渲染器 / Univer 电子表格** 双轨架构（`useEditorMode` 路由分发）：

**已 HTML 化的 9 类（呈现质量高，正是用户想要的样子）**：
| 类型 | 组件 | 呈现亮点 |
|---|---|---|
| A 程序表 | GtAProgramConsole | 进度条 + 类别筛选 + 行展开(描述/历史决策时间线) + 5 认定 checkmark + GtIndexChip 可点跳转 + 审计逻辑流程图 + 批量裁剪 |
| B 目录 | GtBIndex | el-descriptions 编制信息 + 索引导航可点跳转(同底稿切 sheet/跨底稿 router) + 底稿架构树 |
| C 附注表 | GtCNoteTable | 多级表头 + 动态行 + 继承规则校验 + 穿透 |
| D 销售(5 子模式) | GtDForm* | 表格/段落/问答/函证/复核 5 形态 |
| E 控制测试 | GtEControlTest | 6 步骤决策树 + 4 互斥结论 |
| H 静态说明 | GtHStaticDoc | 文档式呈现 |

这些组件用 Element Plus 原生组件（el-table/el-progress/el-timeline/el-descriptions/el-tag）+ GtIndexChip 可点索引 + 穿透跳转，**视觉美观、信息分层、一目了然**——完全是用户期望的方向。

**仍 Univer 电子表格的 F/G（558 sheet）**：
- `_CLASS_TO_COMPONENT` 把 `F-`(采购存货数据表) / `G-`(投资测算表) **硬编码为 `univer`**
- 理由：数据密集型、多列宽表、用户需要类 Excel 的网格编辑体验

### 12.2 问题诊断

**问题 1 — HTML/Univer 判定是"按 wp_code 前缀僵化映射"，非"按内容性质"**：
当前 `derive_component_type` 纯粹按字母前缀（F→univer / G→univer）一刀切。但 F/G 内部**并非所有 sheet 都是数据密集网格**——F 循环里也有程序表、控制测试说明、分析性复核这类**更适合 HTML 呈现**的 sheet，却被前缀规则统统打成 univer。这正是用户说的"拘泥于格式"。

**问题 2 — render_schema 覆盖不全**：
前几轮记录显示 render_schema 覆盖 349 模板的 ~55%，意味着**近半底稿 sheet 还没有 HTML 渲染配置**，只能走 Univer 或 fallback。覆盖率是 HTML 化扩展的硬约束。

**问题 3 — Univer 的局限正是用户痛点**：
Univer 电子表格虽然像 Excel，但：
- 索引号是纯文本，**不可点击跳转**（HTML 类的 GtIndexChip 可点）
- 样式受限于网格，无法做进度条/时间线/状态标签等**信息可视化**
- 大表加载慢（Univer 冷启动 + 整 workbook 加载）

**问题 4 — 缺"按 sheet 内容自适应呈现"的机制**：
同一底稿内不同 sheet 性质不同（程序说明 sheet vs 数据明细 sheet），但当前一个 wp_code 基本走单一路由（HTML 渲染器内部已支持 per-sheet componentType，但分类种子数据没充分利用这点）。

### 12.3 改进方案（以实用为主，按内容性质决定呈现）

#### P1 — 程序表/说明类 sheet 优先 HTML 化（3-4 天，价值最高）
不改 F/G 数据明细 sheet（保留 Univer 的网格编辑），但把 F/G/其他循环里**程序表性质的 sheet** 重新分类到 `a-program-console` 或新增轻量 HTML 类型：
- 扫描 `workpaper_template_analysis.json`（349 模板/2602 sheet 全分析）识别"程序表/控制说明/分析性复核"性质的 sheet（按 sheet 名关键词 + 列结构特征）
- 这类 sheet 改走 HTML，享受可点跳转 + 进度可视化
- F/G 的纯数据明细表保留 Univer

#### P2 — 补全 render_schema 覆盖率（持续，依赖模板分析）
- 当前 ~55% → 目标 80%+，让更多 sheet 有 HTML 渲染配置
- 已有 `workpaper_template_analysis.json` 是全量输入源（前轮记录 349/349 模板全覆盖 / 2602 sheet 全分析 / 仅 7 pending），可批量生成 yaml render_schema

#### P3 — 新增"通用表格 HTML 渲染器"承接中间地带（3-4 天）
F/G 里有大量"既非纯数据明细、也非程序表"的中等复杂度 sheet（如测算表带小计/分类汇总）。新增一个 `g-generic-table` 类型：
- 用 el-table 渲染（支持列宽拖拽 + 排序 + 可点单元格穿透 + 公式 tooltip）
- 比 Univer 轻、比纯静态表灵活
- 数字列用 GtAmountCell（呼应第七章金额一致性）

#### P4 — per-sheet 自适应呈现（2 天）
- 充分利用 HTML 渲染器已有的 per-sheet componentType 能力
- 同一底稿内：程序说明 sheet 走 HTML、数据明细 sheet 走 Univer/通用表格，按 sheet 性质自动选择
- 分类种子数据 `workpaper_sheet_classification` 已是 sheet 级（非 wp_code 级），只需补充更细的分类规则

### 12.4 判定原则（沉淀为呈现选型铁律候选）
**按内容性质而非 wp_code 前缀决定呈现方式**：
- **程序表/清单/决策树/控制说明** → HTML（A/E 类样式：进度+筛选+展开+可点跳转）
- **目录/导航/索引** → HTML（B 类样式：跳转优先）
- **文档/说明/段落** → HTML（H/D-paragraph 样式）
- **带小计/分类/勾稽的中等表格** → 通用 HTML 表格（el-table + GtAmountCell + 穿透）
- **纯数据明细大宽表（如序时账级）** → Univer（保留网格编辑 + 大数据性能）

判定依据从"wp_code 首字母"升级为"sheet 内容特征"（列数/是否有公式/是否有索引引用/是否决策型）。

### 12.5 与前几轮协同
- HTML 化扩展直接服务用户核心诉求（可点跳转 + 美观 + 实用）
- 可点索引/穿透呼应第十章统一溯源面板（HTML 的 GtIndexChip 是溯源跳转的载体）
- 通用表格用 GtAmountCell 呼应第七章金额一致性
- 新增 HTML 组件需配测试，呼应第一/三章测试债治理

### 12.6 不在范围
- 不强行把所有 Univer 底稿改 HTML（纯数据明细大宽表保留 Univer 是合理的）
- 不改 Univer 编辑器本身
- 不改致同模板 Excel 导出（HTML 渲染只影响在线呈现，导出仍按模板 1:1 还原）

> 附：第六轮基于 2026-05-30 实测（useEditorMode 双轨路由 / 9 类 HTML 组件 / F-G 硬编码 univer / wp_classification_service 前缀映射）；render_schema 覆盖率等数字引前轮记录，立项前需重测。


---

## 十三、第七轮复盘：EDITOR_MAP 子编辑器能否纳入"按内容选格式"体系（2026-05-30）

用户提问：EDITOR_MAP 的 table/form/word/hybrid 子编辑器，能否根据底稿模板内容实际情况选用，既实现前述功能（可点跳转/溯源/美观）又方便编辑？本轮给出明确架构判断。

### 13.1 EDITOR_MAP 子编辑器实测能力

| 编辑器 | 渲染方式 | schema 来源 | 编辑能力 | 可点跳转/溯源 |
|---|---|---|---|---|
| `WorkpaperFormEditor` | el-form（7 字段类型：input/textarea/select/date/checkbox/radio/divider） | `parsed_data._schema` or `procedure_steps`，**无则空** | ✅ 存 parsed_data | ❌ 无 |
| `WorkpaperTableEditor` | el-table（增删行/排序/搜索/导入Excel） | `parsed_data._columns`，**无则 2 列硬编码兜底** | ✅ 存 parsed_data | ❌ 无 |
| `WorkpaperWordEditor` | 富文本/段落 | — | ✅ | ❌ |
| `WorkpaperHybridEditor` | 混合 | — | ✅ | ❌ |

它们都有共享工具栏（EditorSharedToolbar：保存/导出/版本/面板）+ useWpDetailGuard 三态守卫，工程基础是好的。

### 13.2 关键现状：存在两套并行且重叠的 component_type 体系

实测发现**两套 seed 脚本写两套数据，且功能重叠**：

| 体系 | seed 脚本 | 写入表 | 产出 component_type | 状态 |
|---|---|---|---|---|
| **旧（metadata）** | `seed_wp_template_metadata.py` | `wp_template_metadata` | A/S→`hybrid` / C→结构化表单 / D-N→`univer` | 88 条，按 wp_code 粗粒度推断 |
| **新（classification）** | `seed_workpaper_sheet_classification.py` | `workpaper_sheet_classification` | HTML 9 类（含 `d-form-table`/`d-form-paragraph` 等） | 3867 行，sheet 级精确 |

`useEditorMode.fetchComponentType` 读 `detail.component_type || template_metadata.component_type`，而 `useHtmlRenderer` 走新体系且**优先级更高**。结果：
- HTML 渲染器（新）能命中就走 HTML，EDITOR_MAP（旧 metadata 的 hybrid 等）基本被旁路
- `render_summary` 15 种呈现里**没有 table/form/word/hybrid**，证明新体系下没有 sheet 实际走 EDITOR_MAP

**核心矛盾**：HTML 渲染器的 `d-form-table`（D 类表格型检查）/ `d-form-paragraph`（段落）/ `d-form-qa`（问答）**已经覆盖了 EDITOR_MAP 的 table/form/word 想做的事，而且做得更好**（GtIndexChip 可点跳转 + 溯源 + 美观），EDITOR_MAP 子编辑器反而**没有跳转/溯源能力**。

### 13.3 架构判断：不要"复活" EDITOR_MAP，而是统一到 HTML 渲染器体系

直接回答用户：**table/form/word 这些格式的"按内容选用"是对的方向，但不应该通过 EDITOR_MAP 旧子编辑器实现，而应在 HTML 渲染器体系内扩展对应的 componentType**。理由：

1. **避免双轨重复**：EDITOR_MAP 的 table/form 与 HTML 的 d-form-table/d-form-paragraph 功能重叠，复活 EDITOR_MAP = 维护两套表格/表单渲染逻辑
2. **EDITOR_MAP 缺核心能力**：无可点跳转、无溯源、无 cell_provenance——恰恰是用户前几轮强调的功能。HTML 渲染器已内建这些
3. **新体系是 sheet 级精确分类**，旧 metadata 是 wp_code 级粗粒度——精度差一个数量级

### 13.4 落地方案：用 HTML 渲染器承接"按内容选格式"（呼应第六章）

把用户诉求（按内容性质选 table/form/word 格式 + 方便编辑 + 可跳转）落到 HTML 渲染器体系：

| 内容性质 | 推荐 componentType | 编辑形态 | 已有/需新增 |
|---|---|---|---|
| 规整明细列表（可增删行） | `g-generic-table`（第六章 P3 提议） | el-table 增删行 + GtAmountCell + 可点穿透 | **需新增**（吸收 WorkpaperTableEditor 的增删行能力 + 加跳转） |
| 字段录入型（结构化表单） | `d-form-table` / 新 `generic-form` | el-form schema 驱动 | d-form-table 已有；通用 form 可吸收 FormEditor |
| 段落/文档型 | `d-form-paragraph` / `h-static-doc` | 富文本/段落 | **已有** |
| 问答/决策型 | `d-form-qa` / `e-control-test` | 步骤/问答 | **已有** |

**关键**：新增 `g-generic-table` 时直接吸收 `WorkpaperTableEditor` 的成熟交互（增删行/排序/搜索/导入Excel），但接入 HTML 渲染器的 GtIndexChip 跳转 + cell_provenance 溯源。这样"方便编辑"和"可跳转/溯源"两个诉求一次满足。

### 13.5 EDITOR_MAP 的处置建议

- **短期**：保留 EDITOR_MAP 路由（不破坏现有能力），但明确它是"过渡/特例通道"，不作为主推路径
- **中期**：把 `WorkpaperTableEditor` 的增删行交互逻辑抽成 composable（`useEditableTableRows`），供新 `g-generic-table` HTML 组件复用——**代码资产不浪费**
- **长期**：当 HTML 渲染器覆盖 table/form/word 三类后，评估 EDITOR_MAP 是否可下线（需先确认无项目级 override 在用，见第六轮待确认项）
- **先决动作**：查 `workpaper_sheet_classification` + `wp_template_metadata` 表实际 component_type 分布，确认 EDITOR_MAP 当前是否真有底稿命中（判定活跃 vs 空壳）

### 13.6 结论一句话
用户的方向正确——**按内容性质选 table/form/word/段落格式**是底稿呈现该走的路；但**实现载体应是 HTML 渲染器的 componentType 扩展（吸收 EDITOR_MAP 的编辑交互 + 加上跳转/溯源），而非复活功能更弱、会造成双轨重复的 EDITOR_MAP 旧子编辑器**。这与第六章"按内容性质而非前缀决定呈现"一脉相承。

### 13.7 不在范围
- 不立即删 EDITOR_MAP（需先确认无活跃使用）
- 不改两套 seed 脚本前先做 component_type 体系收敛设计（避免又造第三套）

> 附：第七轮基于 2026-05-30 实测（EDITOR_MAP 4 子编辑器能力 / 两套 seed 脚本 component_type 体系 / FormEditor+TableEditor schema 来源）；EDITOR_MAP 是否有活跃底稿命中需查库确认。


---

## 十四、元复盘：对本文档自身的批判性审视 + 建设性补充（2026-05-30）

应要求对前十三章做一次诚实的元复盘——**好的坏的都讲**。前面坐实了一个挂账七轮从未真查的先决动作（查 DB component_type 分布），结果推翻了文档若干隐含假设。

### 14.1 先纠错：查库结果推翻了文档的几处论断

**🔴 重大发现 1 — `wp_template_metadata` 表在本机 DB 根本不存在**：
`docker exec psql` 查询返回 `relation "wp_template_metadata" does not exist`。这意味着第七章/第十三章反复讨论的"旧 metadata 体系（A/S→hybrid）"**其表从未建、从未灌数**。连带结论：
- `useEditorMode.fetchComponentType` 读 `template_metadata.component_type` 永远拿不到值
- EDITOR_MAP 的 table/form/word/hybrid 是**彻底死代码、零底稿命中**——第十三章纠结的"是否复活"其实是伪命题，应直接判定为**死路由待清理**（保留 WorkpaperTableEditor/FormEditor 的交互代码作 composable 素材，但 EDITOR_MAP 路由分支可删）

**🔴 重大发现 2 — 本机 `workpaper_sheet_classification` 表 0 行**：
查询返回 0 行。意味着**本机环境当前所有底稿都走不了 HTML 渲染器**（`useHtmlRenderer` 要求 classification 非空），全部 fallback。连带：
- 第六章"HTML 已占 57% / Univer 33%"的论断**是基于模板分析 JSON（理论值），不是本机 DB 实测** —— 文档没区分"理论分类"和"实际渲染"，这是个表述失实
- `seed_workpaper_sheet_classification.py` 没在本机跑过，是 HTML 渲染的前置数据缺失

**🔴 重大发现 3 — `derive_component_type` 永不产出 table/form/word/hybrid**：
seed 脚本只灌 class_code，componentType 全由 `derive_component_type` 派生，而该函数白名单只有 HTML 9 类 + univer + skip。所以**新体系从架构上就不可能命中 EDITOR_MAP**——第十三章"两套体系并存"的表述需修正为"旧体系是空壳死表，实际只有一套半（新 classification + working_paper.parsed_data 里 EDITOR_MAP 残留）"。

**教训**：文档连续七轮把"查库确认"列为待办却从不执行，导致基于代码静态分析的推断（"两套并存""HTML 占 57%"）与运行时事实脱节。**这违反了项目"彻底解决先复现"和"实测有效期"铁律本身**——本文档犯了它自己反复强调要避免的错误。

### 14.2 文档做得好的地方（值得保留的方法论）

诚实地说，文档也有扎实之处：
- ✅ **每轮都先实测再下结论**（grep/readFile），多数结构性判断（行数/测试缺口/孤儿能力）是准的
- ✅ **主动纠正子代理误判**（第十章溯源 service 实际已接线）——体现了交叉核实意识
- ✅ **ROI 排序 + 依赖关系图**清晰，P0 卡点收口确实是最高性价比
- ✅ **复用已有资产**的导向对（不重写、收口孤岛、抽 composable）
- ✅ **风险分级细化**（第七章 float 金额区分 cross-check 安全 vs ai_service 需复核），没有一刀切

### 14.3 文档做得不好的地方（坦诚问题）

**问题 1 — 七轮全是"诊断+建议"，零行落地代码**：
文档 461 行，规划得很丰满，但除了 P0-1（check_file_size 路径，那是上一轮顺手修的）外，**没有任何一条建议被实施**。P0-2/P0-3（白名单收紧，半天零风险）反复强调"最便宜先做"，却从未真做。**有沦为"规划过度、执行不足"的风险**。

**问题 2 — 范围膨胀，从"瘦身"漂移到"重构整个模块"**：
开篇定位"结构债治理"（拆文件/补测试），到第九~十三章已扩张到 TSJ LLM 复核、统一溯源面板、HTML 渲染扩展、EDITOR_MAP 清理——**这些每一个都是独立的大 spec（数周工作量）**，堆在一份"refinement"文档里，优先级被稀释。真正能半天落地的 P0 反而被淹没。

**问题 3 — 工时估算偏乐观且口径不一**：
"统一溯源面板 3-4 天""TSJ 增强版 3-4 天"——这些涉及前后端 + 测试 + UAT 的功能，按项目历史（disclosure-note spec 38.5 人天）看，单项 3-4 天明显低估。且各章工时口径不一（有的含测试有的不含）。

**问题 4 — 理论值与实测值混用未标注**（见 14.1）：HTML 占比、render_schema 55% 等数字来自模板分析 JSON，但行文像是运行时事实。

**问题 5 — 跨章引用形成"循环依赖叙事"**：第九章依赖第十章溯源、第十章呼应第二章性能、第十二章呼应第七章金额……读起来环环相扣，但实际**每条都没落地**，相互"呼应"反而让人误以为体系已成型。

### 14.4 建设性补充建议（基于查库新事实）

#### 新增 P0 — 修复本机 HTML 渲染前置数据缺失（最高优先，0.5 天）
比所有规划都紧急：**本机 sheet_classification 表 0 行 = HTML 渲染器当前根本没生效**。
- 跑 `python -m scripts.seed_workpaper_sheet_classification` 灌入 3867 行分类
- 验证若干底稿（D2/A1/B 目录）真的走 HTML 渲染器（Playwright 实测，不是看 JSON）
- **这一步不做，第六/七/十二章关于 HTML 的所有讨论都是空中楼阁**

#### 新增建议 — EDITOR_MAP 直接判死，不再纠结（0.5 天）
查库已证 table/form/word/hybrid 零命中、无 DB 来源：
- 删 `EDITOR_MAP` 路由分支 + 4 个子编辑器的路由注册（保留 SFC 文件作 composable 素材库）
- 把 WorkpaperTableEditor 增删行逻辑抽 `useEditableTableRows`（第十三章已提，现在有了"反正要删路由"的明确动因）
- 第十三章那套"短期保留/中期/长期"的渐进处置可简化——既然是死代码，直接清理

#### 元建议 — 拆分本文档，避免"规划黑洞"
本文档已成"什么都想管"的巨型规划。建议：
- **抽出可立即执行的 P0**（卡点收口 + 本机 seed + EDITOR_MAP 清理 = 1.5 天）单独成一个**立即执行清单**，本周做掉
- 第九章（TSJ 复核）、第十章（统一溯源）、第十二章（HTML 扩展）**各自独立成 spec**，按真实工时（每个 1-3 周）排期，不要混在"refinement"里
- 本文档退化为**索引/导航**（"底稿模块改进全景图"），指向各独立 spec

#### 诚实的优先级再排（基于"能落地"而非"价值大"）
```
立即（本周，1.5 天，零/低风险）：
  ① 本机 seed classification（修 HTML 渲染前置）← 新发现，最紧急
  ② check_file_size 白名单收紧 P0-2/P0-3（锁瘦身成果）
  ③ EDITOR_MAP 死路由清理
  ④ INDEX.md 计数刷新

近期（1-2 周，有回归保护要求）：
  ⑤ D 类渲染器补测试（P1，3646 行零测，是后续拆分前置）
  ⑥ vllm-httpx-bugfix（解锁 AI 复核 + 6 stub 对话框）

中期（各独立 spec，按真实工时数周）：
  ⑦ TSJ LLM 复核融合（独立 spec）
  ⑧ 统一溯源面板（独立 spec）
  ⑨ HTML 渲染扩展 + 子组件拆分（独立 spec）
```

### 14.5 一句话总结
文档**诊断扎实但执行缺位、范围膨胀、且自己犯了"不查运行时只看代码"的错**。最有价值的修正是：**先把本机 HTML 渲染跑起来（seed 0 行）+ 砍掉 EDITOR_MAP 死代码 + 落地半天就能做的卡点收紧**，而不是继续往文档里堆第八轮、第九轮规划。**规划已经足够多了，缺的是动手。**

> 附：第十四章基于 2026-05-30 docker psql 实测（wp_template_metadata 不存在 / sheet_classification 0 行 / working_paper 无 component_type 列）+ 对前十三章的回读审视。这是本文档首次执行"查库"先决动作，建议据此重排优先级。


---

## 十五、端到端业务流程连通性核查：裁剪→分发→接收→完成→提交复核（2026-05-30）

用户问这条链"都在不、都通不"。逐环节实测核查（子代理初判 + 人工核实纠正），结论：**5 个环节全部存在、接线、前后端通——这条链是通的**。

### 15.1 逐环节核查结果

| 环节 | 后端 | 前端 | 接线 | 结论 |
|---|---|---|---|---|
| **1 裁剪** | `procedures.py` `PUT /{pid}/procedures/{cycle}/trim`（cycle 级批量）+ `wp_procedure_trim.py` `PATCH /procedure-trim`（行级 + summary + history，走 procedure_trim_engine）+ `wp_procedures.py` `PATCH /{proc_id}/trim`（procedure 级） | `ProcedureTrimming.vue`（统计卡片 + 循环 Tab + 一键智能裁剪 + 保存裁剪 + 自定义程序模板）`saveTrim`→`updateProcedureTrim`→`PUT .../trim` | ✅ procedures router 已注册 collaboration.py | ✅ **通** |
| **2 分发** | `batch_assign_enhanced.py` `POST /api/workpapers/batch-assign-enhanced`（4 策略 smart/round_robin/by_level/manual + 权限守卫 + 发 WORKPAPER_ASSIGNED 事件） | `BatchAssignDialog.vue`（2 步：策略+候选人→预览）+ WorkpaperList「批量委派」按钮 + WorkpaperAssignmentMatrix 委派矩阵 | ✅ 已注册 | ✅ **通** |
| **3 接收** | `my_todo.py` `GET /{pid}/my-todo`（紧急度排序 critical>high>medium>normal）+ my_todo_service 聚合 | `WorkpaperLifecycleView` 待办卡片 + Dashboard `MyTodoCard.vue` | ✅ 已注册（16 tests） | ✅ **通** |
| **4 完成** | `working_paper_service` WpFileStatus 状态机（draft→edit_complete→under_review→review_passed）+ `workpaper_batch_status.py` `POST /batch-status` action=mark_complete | WorkpaperList 批量 mark_complete + WorkpaperEditor 工具栏（useEditorSave） | ✅ 已注册 | ✅ **通** |
| **5 提交复核** | `working_paper.py` `POST /{pid}/working-papers/{wpId}/submit-review`（**5 项门禁**：复核人已分配/QC通过/批注已回复/AI已确认/复核意见已回复）+ update_review_status 10 状态流转 | WorkpaperEditor「提交复核」按钮→confirmSubmitReview→submitWorkpaperReview + ReviewWorkbench 复核工作台 | ✅ 已注册 | ✅ **通** |

### 15.2 环节间串联验证（关键——不是单点存在，是链路衔接）

- **裁剪→分发**：裁剪保留执行的程序进"待执行底稿库"，ProcedureTrimming 底部明示"可在委派矩阵中分配"；分发对象是 WorkingPaper（底稿级），裁剪是 procedure（程序级）——**两者粒度不同但同向衔接**（裁剪决定底稿内要做哪些程序，分发决定底稿给谁）
- **分发→接收**：分发写 assignee + 发 `WORKPAPER_ASSIGNED` 事件 → my_todo_service 按 assignee 聚合 → 被分发人在待办卡片看到 ✅
- **完成→提交**：WpFileStatus `edit_complete` 是提交复核的前置状态检查 ✅
- **提交→复核**：review_status `pending_level1` 流转 + 5 项门禁 → ReviewWorkbench 复核人接收 ✅

### 15.3 纠正子代理误判（诚实记录）

context-gatherer 子代理初判**环节 1 裁剪"断裂"**（"前端骨架无逻辑、后端 trim_procedure 孤儿"），人工核实后**该判断错误**：
- 前端 `ProcedureTrimming.vue` **有真实 API 调用**（saveTrim/onSmartTrim/自定义程序模板 http.get+post 俱全），非骨架
- 后端裁剪有 **3 套端点**（cycle 级 procedures.py + 行级 wp_procedure_trim.py + procedure 级 wp_procedures.py），procedures router 已注册 collaboration.py，非孤儿
- 子代理只看了 `wp_procedure_service.trim_procedure`（其中一套）就下"孤儿"结论，漏看了真正接线的 `procedures.py:save_trim`

**教训**：子代理报告必须人工核实关键结论，尤其"断裂/孤儿/缺失"这类否定判断（易因只看部分代码而误判）——呼应第十章同款纠正（溯源 service 实际已接线）。

### 15.4 但有几个值得注意的"通而不顺"点（建设性）

链路通 ≠ 体验顺，实测发现可优化处：

**注意点 1 — 裁剪粒度与分发粒度的概念断层**：
裁剪在 **procedure（程序）** 级、分发在 **workpaper（底稿）** 级。用户心智里"裁剪后分发"是连续动作，但系统里是两个不同对象、两个不同页面（ProcedureTrimming 视图 vs WorkpaperList 批量委派）。**建议**：在 ProcedureTrimming 保存后给一个「→ 去委派这些底稿」的引导跳转，把两个页面串成流程感（呼应第五章渐进引导）。

**注意点 2 — 三套裁剪端点并存，可能重复/语义重叠**：
cycle 级（procedures.py）/ 行级（wp_procedure_trim.py + procedure_trim_engine）/ procedure 级（wp_procedures.py + wp_procedure_service）——**三套裁剪逻辑写在三处**，可能是不同 spec 迭代沉淀。需确认它们是"不同粒度互补"还是"历史重复"，避免改一处漏两处（呼应第十三章 component_type 体系收敛教训）。

**注意点 3 — 5 项提交门禁可能过严，缺"为什么不能提交"的清晰反馈**：
提交复核有 5 项门禁（复核人/QC/批注/AI/复核意见），任一不满足就拦。**建议**：提交前用 checklist 预览 5 项状态（哪项没过 + 一键跳去处理），而非提交时才报错——否则用户反复试错。

**注意点 4 — 接收任务的"通知"可能不够主动**：
my_todo 是**拉取式**（用户主动看待办卡片），WORKPAPER_ASSIGNED 事件是否推送实时通知（站内信/红点）给被分发人需确认。若仅靠用户自己刷待办，分发的"及时性"会打折。

### 15.5 结论
**这条链整体是通的，5 环节都不是空壳**——可以放心地说"裁剪→分发→接收→完成→提交复核"端到端可走。真正的优化空间不在"补缺失环节"，而在 15.4 的 4 个"通而不顺"点（流程串联引导 / 裁剪端点收敛 / 提交门禁预览 / 主动通知）。

> 附：第十五章基于 2026-05-30 实测（procedures.py/batch_assign_enhanced.py/my_todo.py/working_paper.py 端点 + ProcedureTrimming.vue/BatchAssignDialog.vue 调用）+ 人工核实纠正子代理对环节 1 的误判；4 个注意点中"三套裁剪端点是否重复""WORKPAPER_ASSIGNED 是否推实时通知"需进一步查实。


---

## 十六、扩展业务链连通性核查（2026-05-30）

承第十五章，把"前后端联动、有输入有输出、能否跑通"的核查扩展到底稿模块相关的其余核心业务链。每条链给出：**入口（输入）→ 端点（处理）→ 出口（输出）+ 前端调用 + 连通结论**。所有端点经 grep 实测确认存在并注册（不依赖子代理结论）。

### 链 A：数据导入 → 生成底稿 → 预填充（编制起点）

| 步骤 | 输入 | 后端端点 | 输出 | 前端 |
|---|---|---|---|---|
| 1 智能导入 | 序时账/余额 Excel | `POST /ledger/smart-preview`（解析表头+前N行，不写库）→ `POST /ledger/smart-import`（异步写入） | tb_balance/tb_ledger 数据 | UnifiedImportDialog / UploadStep |
| 2 推荐底稿 | 有余额科目 | `GET /wp-mapping/recommend?year=` | 建议编制的底稿清单 | WpMapping 推荐 |
| 3 生成底稿 | wp_code 清单 | `POST /working-papers/generate-from-codes`（**前置 PrerequisiteChecker.check generate_workpapers**） | wp_index + working_paper 记录 + 模板文件 | 生成入口 |
| 4 批量预填充 | 已生成底稿 | `POST /batch-prefill` | parsed_data 填入 TB/WP 取数 + cell_provenance | batchPrefill |

**结论 ✅ 通**：有输入（Excel/科目）有输出（底稿+预填数据），前后端接线，且步骤 3 有前置门禁（旧账套未导入则拦截）。**输入校验完整**（旧 `/ledger/upload` 已 410 废弃，强制走 smart 双段式）。

### 链 B：底稿审定 → 生成报表 → 生成附注 →（审计报告）（出表链）

| 步骤 | 输入 | 后端端点 | 输出 | 前端 |
|---|---|---|---|---|
| 1 生成报表 | TB 审定数 | `POST /api/reports/generate`（**前置 generate_reports 门禁**）+ 发 REPORTS_UPDATED 事件 | 四表 financial_report | ReportView |
| 2 生成附注 | 报表行 | `POST /api/disclosure-notes/generate`（**前置 generate_notes 门禁**） | disclosure_notes 章节树 | DisclosureEditor |
| 3 导出附注 Word | 附注章节 | `POST /api/disclosure-notes/{pid}/{year}/export-word` + `POST /notes/export-word` | docx StreamingResponse | ExportDialog |
| 4 导出审计报告 | 报表+附注 | `POST /word-export/audit-report/generate` | docx 任务 | word_export |
| 5 全套打包 | 全部 | `POST /word-export/full-package`（**Phase14 export_package 门禁**） | 审计报告+4表+附注 ZIP | full-package |

**结论 ✅ 通**：链路完整且自带 EventBus 联动（报表生成→附注增量更新，第十章已验证），每步有 PrerequisiteChecker 门禁（输入不满足则拦），输出从结构化数据到 docx/ZIP 文件齐全。

### 链 C：复核通过 → 归档（收尾链）

| 步骤 | 输入 | 后端端点 | 输出 | 前端 |
|---|---|---|---|---|
| 1 归档就绪检查 | 项目 | `GET /api/qc/archive-readiness?project_id=` | 就绪清单/拦截项 | ArchiveWizard |
| 2 启动归档编排 | review_passed 底稿 | `POST /api/projects/{pid}/archive/orchestrate`（ArchiveOrchestrator） | 归档 job | archiveApi |
| 3 查作业状态 | job_id | `GET /archive/jobs/{jobId}` + retry | 归档进度/结果 | 轮询 |
| 4 监管备案（可选） | 归档包 | `POST /api/regulatory/archival-standard` + `/cicpa-report` | 备案状态 | regulatory |

**结论 ✅ 通（异步编排式）**：旧 3 个归档端点（wp_storage/private_storage/data_lifecycle）已统一 `Deprecated` 指向 orchestrate，入口收敛干净。归档前有就绪检查（输入门禁），输出是归档 job + 可选监管备案。

### 链 D：底稿复核意见 → 工单 →（整改回流）（质量回环）

| 步骤 | 输入 | 后端端点 | 输出 | 前端 |
|---|---|---|---|---|
| 1 复核记录 | 复核人意见 | wp_review REVIEW_RECORD_CREATED 事件 | review_records | ReviewWorkbench |
| 2 工单补偿 | 复核意见 | 事件 handler 自动建 IssueTicket（source='reminder'） | issue_ticket | IssueTicketList |
| 3 退回整改 | 不通过 | `update_review_status` → level1_rejected（强制填退回原因） | revision_required 状态 | - |
| 4 通过自动闭环 | review_passed | 自动关闭 source='reminder' 的 IssueTicket（Batch1 Fix7.1） | 工单 closed | - |

**结论 ✅ 通（事件驱动闭环）**：复核↔工单双向联动，退回有强制原因校验，通过有自动闭环。

### 16.5 汇总：各链连通性一览

| 业务链 | 连通 | 输入校验/门禁 | 输出 | 备注 |
|---|---|---|---|---|
| 裁剪→分发→接收→完成→复核（十五章） | ✅ | 5 项提交门禁 | 状态流转 | 4 个"通而不顺"点 |
| A 导入→生成底稿→预填充 | ✅ | generate_workpapers 门禁 + smart 双段 | 底稿+预填数据 | 强校验 |
| B 审定→报表→附注→报告→打包 | ✅ | 3 道 PrerequisiteChecker + Phase14 门禁 | docx/ZIP | EventBus 联动 |
| C 复核通过→归档→备案 | ✅ | archive-readiness 检查 | 归档 job | 入口已收敛 |
| D 复核意见→工单→整改回流 | ✅ | 退回强制原因 | 工单闭环 | 事件驱动 |

### 16.6 跨链的两个系统性观察（建设性）

**观察 1 — 链路普遍"能跑通但门禁反馈滞后"**：
链 A/B/C 都有 PrerequisiteChecker / gate_engine 门禁（这是好事，保证数据完整性），但**和第十五章注意点 3 同病**——门禁多是"点了生成才告诉你不满足"，而非"进页面就预览还差什么"。**系统性建议**：做一个统一的"前置就绪看板"composable（`usePrerequisiteStatus`），各链入口页面进入时主动展示"距离可生成还差 X 项"+ 一键跳去补，把所有链的门禁从"拦截式"升级为"引导式"。

**观察 2 — 异步任务（generate/export/archive/import）的进度反馈分散**：
链 A 的 smart-import、链 B 的 word-export full-package、链 C 的 archive orchestrate 都是**异步 job + 前端轮询/SSE**，但各自实现进度反馈（有的轮询 jobs/{id}、有的 SSE）。**系统性建议**：统一异步任务进度组件（`AsyncJobProgress.vue` + 统一 job 状态端点契约），所有"生成/导出/归档/导入"复用，避免每条链各做一套进度条（呼应第五章布局一致性 + 第十章联动可观测性）。

### 16.7 结论
**底稿模块相关的 5 条核心业务链全部跑得通**，都满足"前后端联动 + 有输入（含门禁校验）+ 有输出（数据/文件/状态流转）"。这说明项目的**业务骨架是完整且健康的**——这是个重要的正面结论，前面十五章聚焦问题容易让人误以为"到处是坑"，实际核心流程是通的。真正的提升空间是跨链的两个系统性体验问题（门禁引导式化 + 异步进度统一），而非补缺失链路。

> 附：第十六章端点均经 grep 实测确认存在并注册（ledger_penetration/reports/disclosure_notes/word_export/archive/wp_template/wp_batch_ops + 前端 apiPaths）；"门禁反馈滞后""异步进度分散"是基于端点模式的系统性推断，具体每条链的前端门禁 UI 现状需逐一实测确认。


---

## 十七、复盘：异构格式下的互动追溯难点（前后端联动深挖）（2026-05-30）

用户点到了真正的架构难点：**底稿格式多（HTML 9 类 + Univer + 子编辑器），跨格式的互动追溯会很难，前后端联动要考虑好**。第十章讲了"统一溯源面板"的方向，但没深挖这个具体难点。本轮实测定位到 3 个真实技术断点。

### 17.1 难点本质：追溯有"数据层"和"落地层"两层，落地层被格式绑架

互动追溯 = "从 A 跳到 B 并高亮定位到 B 的具体位置"。它分两层：
- **数据层**（这个数字从哪来/到哪去）：算出来的是 `wp_code + sheet + cell`
- **落地层**（跳过去后真的滚动/高亮到那个 cell）：依赖目标底稿的渲染器能"接住"定位指令

**问题**：数据层基本统一了，**落地层完全被渲染格式绑架**——这才是"格式多→追溯难"的真正根因。

### 17.2 三个实测断点

**🔴 断点 1 — cell 定位是 Univer 独占能力，HTML 渲染器 0 响应**：
- `WorkpaperEditor.onLocateCell` 注释明写"定位由 UniverEditorCore 内部处理"
- `GtWpRenderer`（HTML 9 类渲染器）grep `locate/cellRef/scrollTo/highlight` = **0 命中**
- 后果：追溯/版本跳转/穿透即使带了 `sheet+cell`，**跳到 HTML 类底稿（A/B/C/D/E/H）后无法定位高亮**——而第六章刚说 HTML 已占 57%，意味着**过半底稿的精确定位追溯是断的**

**🔴 断点 2 — 两个 trace service 输出粒度不一致**：
- `wp_trace_service.TraceItem` 用 `wp_code + sheet + cell + value` **cell 级三段式**（精确）
- `report_trace_service.trace_section` 只返回整个 `parsed_data`（**底稿级，不到 cell**）
- 后果：第十章说的"统一溯源面板"要收口这两个 service，但它们**连定位粒度都不统一**，收口时得先统一数据契约

**🔴 断点 3 — 穿透到底稿丢失定位上下文**：
- `usePenetrate.toWorkpaperEditor(wpId)` **只带 wpId，不带 sheet/cell**
- 后果：从报表/附注穿透到底稿，只能到"打开这张底稿"，回答不了"定位到支撑这个数的那一格"

### 17.3 为什么这是"前后端联动"问题而非纯前端

定位链路跨越前后端：
```
后端 trace service 算出 {wp_code, sheet, cell}（数据层，已统一为 TraceItem）
    ↓ 通过 router 返回
前端拿到定位坐标 → router.push 带 query → 目标编辑器
    ↓ 编辑器按 componentType 分发
Univer：UniverEditorCore 接住 locate-cell ✅
HTML：GtWpRenderer 无 locate 能力 ❌  ← 断在这
```
所以修这个难点必须**前后端各出一半**：后端统一 trace 输出契约（含 sheet+cell+componentType），前端给 HTML 渲染器补统一的 locate 能力。

### 17.4 改进方案：统一"定位坐标 + 定位接口"双契约

#### P1 — 统一定位坐标契约（后端，2 天）
所有 trace service 输出统一为 `LocateTarget`：
```
{ wp_code, wp_id, sheet_name, cell_ref, component_type, value, label }
```
- `report_trace_service` 从"返回整个 parsed_data"升级为"返回精确 cell 列表"（利用 cell_provenance 已记录的单元格来源）
- `component_type` 一并返回，让前端知道目标是 HTML 还是 Univer，走对应定位策略

#### P2 — HTML 渲染器补统一 locate 能力（前端，3 天，难点核心）
给 `GtWpRenderer` + 9 个子组件加统一的定位接口：
- `GtWpRenderer` 监听 `workpaper:locate-cell` 事件（对齐 Univer 路径）
- 内部先切到目标 sheet（已有 sheet tab 能力），再委托当前 componentType 子组件定位
- 子组件实现 `locateCell(cellRef)`：el-table 类（C/D-table/通用表格）滚动到行 + 高亮；GtIndexChip 类直接 scrollIntoView + 闪烁
- **抽 `useCellLocate` composable** 统一"切 sheet → 滚动 → 高亮 → 3s 淡出"逻辑，9 类子组件复用（避免每个组件各写一套）

#### P3 — 穿透带定位上下文（前后端，1 天）
- `toWorkpaperEditor` 扩展签名：`toWorkpaperEditor(wpId, { sheet?, cell? })`
- 路由 query 带 `sheet`/`cell`，WorkpaperEditor onMounted 读 query → 触发 locate（HTML/Univer 统一走 P2 的接口）

#### P4 — 定位失败的优雅降级（0.5 天，体验兜底）
异构格式下定位必然有"找不到 cell"的情况（如目标 sheet 被裁剪、cell 在折叠区）：
- 定位失败时不静默，给"已打开底稿但未能定位到 X 单元格（可能已变更）"提示
- 降级到 sheet 级定位（至少切到对的 sheet）

### 17.5 与前几轮的关系（修正第十章的乐观）
第十章把"统一溯源面板"标为 P1 价值最高，但**当时低估了落地层的难度**——以为收口 3 个 service 就行，实测发现**HTML 渲染器根本没有定位能力**，这是比"收口 service"大得多的工作量。**修正**：统一溯源面板的真正前置是本章 P2（HTML 渲染器 locate 能力），没有它，溯源面板算得出血缘但"点了跳不到位置"，等于半残。**依赖顺序**：P1 坐标契约 → P2 HTML locate（核心）→ P3 穿透上下文 → 第十章统一溯源面板（最后做，此时落地层已就绪）。

### 17.6 务实的范围建议
- **不追求 Univer 级的像素精确定位**：HTML 类底稿定位到"行 + 高亮"足够实用（用户能一眼看到），不必复刻 Excel 的单元格选区
- **优先 C/D 类**（附注表/销售表，cell 引用多、追溯需求高），A/B/H 类（程序表/目录/说明）定位需求低可后做
- **复用 GtIndexChip**：它已是 HTML 类的可点跳转载体，locate 能力可与它共用高亮机制

### 17.7 结论
"格式多导致追溯难"是**真问题且已实测定位到根因**：不是数据层缺溯源（TraceItem 已统一），而是**落地层的 cell 定位能力只有 Univer 有、HTML 渲染器缺失**，加上穿透丢上下文、trace 粒度不一。这是个**前后端各出一半**的活：后端统一坐标契约 + 前端给 HTML 渲染器补 `useCellLocate`。**它还是第十章统一溯源面板的真正前置**——之前低估了。建议把 P2（HTML locate 能力）作为整个"互动追溯"主题的第一块基石。

> 附：第十七章基于 2026-05-30 实测（onLocateCell 注释 / GtWpRenderer grep locate=0 / TraceItem vs report_trace 粒度 / toWorkpaperEditor 签名）；HTML 渲染器无 locate 是关键发现，建议立项前在真实底稿上 Playwright 复现一次"从报表穿透到 HTML 类底稿能否定位"以坐实。


---

## 十八、分阶段实施路线图（收口全文 → 可起 spec 三件套）

前十七章是诊断 + 建议（按用户多轮提问逐章累积）。本章执行第十四章自己提的"收口"动作：把散落 17 章的建议**合并成 5 个边界清晰、可直接起三件套的 spec**，并标注真实完成状态（已 grep/查库核实，不是规划口径）。

### 18.0 实测完成状态校准（2026-05-30 复核）

避免把已做的列成待办：

| 项 | 文档原述 | 实测状态 |
|---|---|---|
| check_file_size whitelist 路径 | P0-1 已修 | ✅ 确认（52 条加载正常） |
| 本机 sheet_classification seed | 新 P0 最紧急 | ✅ **已执行**（3867 行，本轮真跑过，HTML 渲染前置已通） |
| WorkpaperEditor 白名单收紧 | P0-2 | ❌ 仍锁 2342（未收紧） |
| WorkpaperList 白名单收紧 | P0-2 | ❌ 仍锁 3464（未收紧） |
| GtDFormConfirmation/GtEControlTest 登记 | P0-3 | ⚠️ 部分（Confirmation 未登记 / Review 已登记 1670） |
| EDITOR_MAP 死路由清理 | 元复盘建议 | ❌ 未做 |
| seed 脚本 ANALYSIS_JSON 路径 bug | 第 4 个同款 | ✅ 本轮已修（parents[3]） |

**净结论**：最紧急的"本机 HTML 渲染前置"已在核查中顺手做掉，剩余 P0 是纯配置（白名单）+ 死代码清理，半天可清。

### 18.1 五个 spec 的拆分（按依赖与可落地性排序）

#### Spec 1 — `workpaper-guardrail-cleanup`（P0，1.5 天，零/低风险，立即可起）
**收敛**：第二章 P0-2/P0-3/P0-4 + 第七章 float 卡点 + 元复盘 EDITOR_MAP 清理 + 第十六章路径 bug 成批排查。
- 白名单收紧（WorkpaperEditor 2342→820、WorkpaperList 3464→520）+ 登记游离子组件
- 重建 `check_no_float_amount.py`（去 `_` 转正式工具）+ 跑一次定 baseline + 接 pre-commit
- EDITOR_MAP 死路由清理（查库已证零命中，删路由 + 保留 SFC 作素材）
- grep 全 `backend/scripts/` 子目录排查同款路径 bug（已知第 4 个，可能还有）
- INDEX.md 计数刷新
**验收**：pre-commit 全绿 + 卡点真生效 + 无死路由。**无业务逻辑改动，纯治理。**

#### Spec 2 — `gtdform-test-and-shrink`（P1，1 周，依赖无）
**收敛**：第一/三章 D 类测试断层 + 第二章 P2 子组件拆分 + 已有 `gt-c-note-table-shrink` README。
- 先补测试（GtDFormReview 1537/Confirmation 1311/Paragraph 798 共 3646 行零测）——**拆分前置**
- 再拆分（抽 useReviewStateMachine/useReviewSignature/useReviewFields 等 composable，shell ≤400）
- 合并已有 `gt-c-note-table-shrink`（GtCNoteTable 1609 + GtEControlTest 1279）
**验收**：4 个 god-component ≤400 行 + 关键交互有单测 + 0 回归。**测试必先于拆分（否则盲拆）。**

#### Spec 3 — `wp-interactive-traceability`（P1-P2，2-3 周，核心难点）
**收敛**：第十章统一溯源面板 + 第十七章异构格式定位（**本 spec 是重头戏**）。
- 后端：统一 `LocateTarget` 坐标契约 + 收口 3 个 trace service 到 `GET /lineage` + report_trace 升级到 cell 级
- 前端核心：**HTML 渲染器补 `useCellLocate` composable**（9 类复用，切 sheet→滚动→高亮）
- 穿透带 sheet/cell 上下文 + 定位失败降级
- 附件入网（attachment ↔ wp_cell/report_row/note_section）
- 最后做 `LineageGraphPanel.vue` 统一血缘图
**验收**：从报表/附注穿透到任意格式底稿能定位高亮（Playwright 实测 HTML + Univer 双格式）。**依赖顺序：坐标契约→HTML locate→穿透→面板。**

#### Spec 4 — `wp-tsj-llm-review`（P1，依赖 vllm-httpx-bugfix）
**收敛**：第九章 TSJ 提示词融合 LLM 复核 + 第七章 6 个 stub 对话框。
- 前置：先做 `vllm-httpx-bugfix`（独立 1 天，解锁所有 AI）
- MVP：接线 `POST /ai/tsj-review` + SideStandardsTab 加按钮
- 增强：按认定分段复核 + 结构化 JSON 输出 + 进 V3 Req6 确认流
- 复核发现"关联证据位置"**依赖 Spec 3 的定位能力**
**验收**：选 TSJ 提示词复核真实底稿，发现逐条进确认流可跳证据。

#### Spec 5 — `wp-frontend-ux-polish`（P2，1-2 周，体验提升）
**收敛**：第五章布局 + 第六章 HTML 化扩展 + 第十六章门禁引导/异步进度统一。
- 侧栏 13 Tab → 4 功能组 + 首次渐进引导（el-tour）
- 8 横幅 → 折叠状态条
- HTML 化扩展（F/G 程序表性质 sheet 改 HTML + g-generic-table）
- 统一 `usePrerequisiteStatus`（门禁引导式）+ `AsyncJobProgress`（异步进度）
**验收**：侧栏不拥挤 + 门禁进页面即预览 + 异步任务统一进度条。

### 18.2 依赖关系与建议排期

```
立即（本周）：
  Spec 1 guardrail-cleanup (1.5天) ──── 无依赖，纯治理，先做锁成果
        │
近期（2-4周，可部分并行）：
  Spec 2 gtdform-test-and-shrink (1周) ──── 无依赖（测试先于拆分）
  vllm-httpx-bugfix (1天) ──→ Spec 4 wp-tsj-llm-review
        │
重头（2-3周，按依赖串行）：
  Spec 3 wp-interactive-traceability ──── 坐标契约→HTML locate→穿透→面板
        │  （HTML locate 是 Spec 4"关联证据"的前置）
        └──→ Spec 4 增强版的"跳证据" + Spec 5 的穿透体验都依赖它

体验（1-2周，最后做或穿插）：
  Spec 5 wp-frontend-ux-polish
```

**关键依赖链**：Spec 3 的「HTML 渲染器 locate 能力」是 Spec 4（复核跳证据）和 Spec 5（穿透体验）的共同地基——**这是整个路线图的技术枢纽，建议 Spec 1 之后优先启动 Spec 3 的 P1/P2（坐标契约 + HTML locate）**。

### 18.3 每个 spec 起三件套时的注意事项

| Spec | requirements 重点 | design 重点 | tasks 风险点 |
|---|---|---|---|
| 1 guardrail | 卡点真生效的验收标准 | float 卡点 baseline 怎么定 | EDITOR_MAP 删除前确认无引用 |
| 2 gtdform | 测试覆盖关键交互清单 | composable 拆分边界 | **setup const 顺序铁律**（拓扑序） |
| 3 traceability | LocateTarget 契约字段 | useCellLocate 9 类适配策略 | HTML 各子组件定位实现差异大 |
| 4 tsj-review | 结构化输出 JSON schema | 按认定分段策略 | LLM 链路 3 bug 必先修 |
| 5 ux-polish | 不破坏现有好实践 | 4 Tab 分组归属 | HTML 化扩展不动 Excel 导出 |

### 18.4 全文收口声明
本文档至此**停止新增诊断章节**（共 18 章，从结构债到异构追溯已覆盖底稿模块全维度）。后续动作是**起 spec 落地，不再扩写规划**——这是对第十四章"规划已够多，缺的是动手"自我批评的正面回应。本章 5 个 spec 边界清晰、依赖明确，可作为各自三件套的起点输入。

**文档定位转变**：从"持续累积的诊断书"转为"分阶段实施的导航索引"。每个 spec 落地后，对应章节的诊断价值即被实现取代，可在 spec 完成后回标 ✅。

> 附：第十八章基于 2026-05-30 实测完成状态校准（whitelist 52 条 / classification 3867 行已 seed / WorkpaperEditor 仍锁 2342）；5 个 spec 中 Spec 2/4 已有 README stub（gt-c-note-table-shrink / workpaper-fill-service-split），可直接扩展为完整三件套。


---

## 十九、5 个 spec 三件套一致性复盘 + 底稿按功能类型的专属联动（2026-05-30）

本章两件事：① 复盘第十八章 5 个 spec 拆分的内部一致性；② 回应用户关键洞察——**底稿按功能类型差异极大、各需专属联动**，这暴露了 5-spec 拆分漏了一整类。

### 19.1 5 个 spec 三件套一致性复盘

**一致性问题 1 — 5 个 spec 都还只是"章节收敛"，没有真正的 requirements/design/tasks**：
第十八章列了 5 个 spec 的"收敛范围 + 验收 + 注意事项"，但**这不等于三件套**。三件套要求 requirements（用户故事 + 验收标准 EARS 格式）、design（架构 + 数据模型 + 时序）、tasks（带依赖的可勾选任务）。当前 5 个 spec **只有 README 级方案描述**，其中 2 个（gt-c-note-table-shrink / workpaper-fill-service-split）有 README stub，其余 3 个连 stub 都没有。

**一致性问题 2 — 粒度严重不均**：
- Spec 1（guardrail）：1.5 天纯治理，**该不该是 spec？** 它更像一个"清理任务清单"，起三件套是过度仪式化。建议降级为 checklist 直接做。
- Spec 3（traceability）：2-3 周跨前后端 + 异构格式适配，**体量是 Spec 1 的 10 倍**，单个 spec 装不下，应拆成"坐标契约+HTML locate"和"溯源面板+附件入网"两个 spec。
- 粒度不均导致"5 个 spec"这个数字是凑出来的，不是自然边界。

**一致性问题 3 — 依赖声明前后矛盾**：
- 第十八章说 Spec 4 "跳证据依赖 Spec 3"，但又把 Spec 4 排在"2-4 周可并行"、Spec 3 排在"重头串行"之后——**依赖方比被依赖方先排期**，逻辑冲突。正确：Spec 3 的 HTML locate 必须先于 Spec 4 增强版。

**一致性问题 4 — 验收标准口径不一**：
有的 spec 验收是"行数 ≤400"（可量化），有的是"侧栏不拥挤"（主观）、"能定位高亮"（需 Playwright）。三件套的验收必须统一为可自动化验证的断言。

**一致性结论**：第十八章是**好的"spec 选题清单"，但不是 5 份三件套**。真要落地，应：① Spec 1 降级为 checklist 直接做；② Spec 3 拆 2 个；③ 修正依赖顺序；④ 每个先写 requirements 再评估工时（现在工时是拍的）。

### 19.2 关键遗漏：底稿按功能类型的专属联动（用户洞察）

用户列举了 ~12 种功能各异的底稿类型，**这是比"HTML vs Univer 渲染格式"更深一层的维度**——不是"长什么样"，而是"这张底稿要联动什么数据源、要什么交互"。我前 18 章聚焦渲染格式（HTML/Univer）和通用链路，**漏了"按功能类型的专属取数/联动"这一整类**。实测后端能力盘点：

| 底稿功能类型 | 用户要求的联动 | 后端现状（实测） | 缺口 |
|---|---|---|---|
| **目录页** | 流程图/全仓图体现科目所有程序 + 跳转 | GtBIndex（编制信息+索引导航+架构树） | ⚠️ 有导航无"科目→所有程序"流程图视角 |
| **程序控制台** | 特别考虑 | GtAProgramConsole（进度+筛选+展开+审计逻辑流程图）✅ 已是最佳实践 | ✅ 基本满足 |
| **抽凭表** | 联动凭证表 + 弹窗确认 + 分层/随机/大额多方式 + 填充底稿 | `wp_sampling_engine`（样本量计算 statistical/mus/non-statistical）+ `wp_ocr_fill_service`（OCR→抽凭表填充） | 🔴 **缺"从凭证表按分层/随机/大额抽样→弹窗确认→填进底稿"链路**（现有是样本量公式 + OCR 填充，非从 tb_ledger 直接抽样填充） |
| **截止性测试表** | 报表日后前后 N 天自定义 + 凭证表复核条件填充 | `CutoffTestService.run_cutoff_test`（取期末前后 N 天交易，已注册 `sampling_enhanced` router）✅ | 🔴 **取数端点有，但"填进截止测试底稿 + 前端弹窗设 N 天"未串** |
| **合同检查表** | 上传合同附件 + LLM 识别 + 生成台账 + 逐份确认 | `wp_ocr_fill_service.fill_ledger_from_contract_ocr` + `_extract_contract_fields`（正则）+ unified_ocr 识别合同 | 🔴 **是正则提取非 LLM + 缺"逐份确认"UI**（用户明确要 LLM + 每份确认） |
| **月度明细分析**（管理/销售费用） | 从四表库提二级/末级明细填充 | `MonthlyDetailService.generate_monthly_detail`（按月汇总，已注册）+ aux_balance 二级明细 ✅ | 🔴 **取数端点有，但"填进分析底稿 + 取末级而非仅按月"未完整** |
| **文字提示型** | 指导用户做程序，不一定是单独底稿 | h-static-doc / d-form-paragraph | ✅ 渲染支持 |
| **会计政策/访谈/声明书/计划/小结/盘点/函证类** | 各自表单/文档形态 | D 类 5 子模式 + 函证 extract_confirmations | ⚠️ 渲染有，专属联动深度不一 |

**核心发现**：**抽凭/截止/月度明细的后端取数能力都已实现且接线了 router，但"取数结果→填进对应底稿 cell + 前端参数弹窗确认"这关键一跳普遍缺失**。它们现在是"独立查询端点"，不是"在底稿里发起→填回底稿"的闭环。合同检查表更缺 LLM 识别（现在是正则）+ 逐份确认 UI。

### 19.3 这暴露了一个架构级的缺失：底稿的"功能类型"维度

当前 componentType 体系（9 类 HTML + univer）是**按"渲染形态"分**，但用户列举的是**按"功能行为"分**（抽凭/截止/合同/月度分析…）。一张底稿可能渲染形态是 `d-form-table`（HTML 表格），但功能行为是"抽凭表"——**这两个维度正交，当前系统只有渲染维度，没有功能行为维度**。

后果：抽凭表和普通明细表渲染一样（都是 el-table），但抽凭表需要"抽样按钮+参数弹窗+从凭证表填充"，普通明细表不需要。**当前没有机制让 d-form-table 知道"我是一张抽凭表，要挂抽样工具"**。

### 19.4 新增 Spec 6 — `wp-functional-actions`（底稿功能行为联动）

这是第十八章 5-spec 漏掉的一整块，应独立成 spec（且体量不小，3-4 周）：

**核心设计**：在 componentType（渲染维度）之外，引入 **`functional_type`（功能行为维度）** + **"底稿动作面板"机制**：
- 分类种子表（workpaper_sheet_classification）增加 `functional_type` 字段（sampling/cutoff/contract/monthly_analysis/aging/...）
- 底稿渲染时按 functional_type 在工具栏挂对应"动作"（抽凭表挂"抽样"按钮，截止表挂"取期末交易"按钮）
- 每个动作 = 参数弹窗（输入）→ 调已有后端端点（处理）→ 填回底稿 cell（输出）

**逐功能落地**（复用已有后端能力，补"弹窗+填充"这一跳）：
| 动作 | 复用后端 | 要补 |
|---|---|---|
| 抽凭 | 新建"从 tb_ledger 分层/随机/大额抽样"端点（wp_sampling_engine 扩展） | 弹窗（方式+参数）+ 抽样结果填底稿 + OCR 照片关联（已有 wp_ocr_fill） |
| 截止测试 | `CutoffTestService` ✅ | 弹窗（自定义 N 天）+ 结果填截止测试底稿 |
| 合同台账 | unified_ocr 识别 | **LLM 提取替换正则** + 逐份确认 UI + 台账填充 |
| 月度分析 | `MonthlyDetailService` ✅ + aux 末级 | 弹窗（选末级明细）+ 填分析底稿 |
| 账龄 | `AgingAnalysisService` ✅ FIFO | 弹窗（账龄区间）+ 填账龄表 |
| 目录页流程图 | 需新建"科目→所有程序"聚合 | 流程图/全仓图组件 + 跳转 |

**关键**：80% 的后端取数能力已存在（CutoffTest/Monthly/Aging/Sampling 都已实测有 service + router），缺的是**前端"动作面板 + 参数弹窗 + 填回底稿"的统一框架** + functional_type 分类。这比从零做省一半。

### 19.5 修正后的 spec 全景（6 个 + 1 checklist）

```
[直接做] guardrail-cleanup（原 Spec 1 降级为 checklist，1.5 天）

[独立 spec]
  Spec 2 gtdform-test-and-shrink（1 周，无依赖）
  Spec 3a wp-locate-foundation（坐标契约+HTML locate，1.5 周）← 技术枢纽
  Spec 3b wp-traceability-panel（溯源面板+附件入网，1 周，依赖 3a）
  Spec 4 wp-tsj-llm-review（依赖 vllm-bugfix + 3a 的 locate）
  Spec 5 wp-frontend-ux-polish（1-2 周）
  Spec 6 wp-functional-actions（底稿功能行为联动，3-4 周，依赖 3a 的 locate + 部分复用 4 的 LLM）← 用户洞察，重头
```

### 19.6 结论
- **5 个 spec 三件套一致性**：是好的选题清单但**不是真三件套**（粒度不均/依赖矛盾/验收口径不一/Spec 1 过度仪式化）。建议 Spec 1 降级 checklist、Spec 3 拆 2、修正依赖顺序、每个先写 requirements 再估工时。
- **底稿功能类型联动**：用户洞察击中要害——前 18 章只看了"渲染格式"维度，漏了"功能行为"维度。**好消息是抽凭/截止/月度/账龄的后端取数能力 80% 已实测存在并接线**，缺的是"参数弹窗→填回底稿"这一跳 + functional_type 分类机制。这是**新增 Spec 6**，是 6 个 spec 里最贴近"实用"的一块（直接服务审计师日常做底稿）。

> 附：第十九章基于 2026-05-30 实测（sampling_enhanced_service 三类 + router 已注册 / wp_ocr_fill_service 合同正则提取 / wp_sampling_engine 样本量公式）；"取数已有但填回底稿缺失"是关键发现，建议立项前 Playwright 实测一张抽凭表/截止表确认前端是否真有"抽样→填充"动作。


---

## 二十、底稿功能类型完整谱系（从真实模板数据归纳）（2026-05-30）

第十九章只列了抽凭/截止/合同/月度 4 类作举例，用户指出"底稿还有很多类型"。本章从 `workpaper_template_analysis.json`（2602 sheet）**实测挖出 sheet 名关键词频次 + 各 class 样本**，系统归纳出 **functional_type 完整谱系**——不再凭印象，而是数据驱动。

### 20.1 sheet 名关键词频次（功能类型的实测信号）

```
程序 241 / 检查 209 / 披露 176 / 目录 148 / 汇总 135 / 控制 126 / 明细 120
测试 119 / 审定 108 / 分析 99 / 调整 99 / 评价 72 / 测算 65 / 减值 54
函证 52 / 核对 45 / 清单 37 / 合同 32 / 复核 31 / 风险 30 / 政策 21
截止 19 / 了解 18 / 盘点 16 / 说明 15 / 监盘 13 / 访谈 12 / 折旧 12
确认 10 / 计划 9 / 摊销 9 / 计提 9 / 小结 5 / 问卷 5 / 账龄 2 / 台账 1
```
这印证了用户判断：**功能类型远不止十九章的 4 类，实测至少 20+ 种**。

### 20.2 完整 functional_type 谱系（14 大类，按联动复杂度分层）

基于关键词 + class 样本归纳，按"需要什么联动/交互"分为 4 个层级：

#### L1 — 取数填充型（联动四表库，需参数弹窗 + 填回底稿）★ 最高价值
| functional_type | 对应底稿样本 | 联动数据源 | 后端现状 |
|---|---|---|---|
| `sampling`（抽凭） | 函证程序表/细节测试 C24A | tb_ledger 凭证 | ⚠️ 样本量公式有，抽样填充缺 |
| `cutoff`（截止测试） | 截止性测试 | tb_ledger 期末前后 N 天 | ✅ CutoffTestService |
| `monthly_analysis`（月度明细分析） | 管理/销售费用分析 | tb_ledger 按月 + aux 末级 | ✅ MonthlyDetailService |
| `aging`（账龄分析） | 应收账款账龄 | tb_aux_ledger FIFO | ✅ AgingAnalysisService |
| `detail_table`（明细表，120 处） | 原值明细表 D1-2/坏账明细 | tb_aux_balance 明细 | ⚠️ 部分（prefill） |
| `reconciliation`（核对，45 处） | 银行流水双向核对 D4-13/ERP 核对 | tb_ledger ↔ 外部数据 | 🔴 缺 |

#### L2 — 文档识别型（上传附件 + LLM 提取 + 逐份确认）★ 用户重点
| functional_type | 对应底稿 | 联动 | 后端现状 |
|---|---|---|---|
| `contract_ledger`（合同台账，32 处） | 合同检查表 | 上传合同→LLM→台账 | 🔴 现是正则非 LLM + 缺逐份确认 |
| `voucher_ocr`（凭证 OCR） | 抽凭照片 | 凭证图→OCR→填抽凭表 | ✅ wp_ocr_fill_service |
| `confirmation`（函证，52 处） | 函证结果汇总 D0-1/差异调节 D0-4 | 回函→识别→差异比对 | ⚠️ extract_confirmations 有，回函 OCR 弱 |

#### L3 — 测算/检查型（公式计算 + 阈值判断）
| functional_type | 对应底稿 | 联动 | 后端现状 |
|---|---|---|---|
| `impairment`（减值测算，54 处） | 商誉减值测试 A3-8/可收回金额 | 现金流折现公式 | ⚠️ 6 stub 对话框之一 |
| `depreciation`（折旧摊销，21 处） | 折旧/摊销计算 | 原值×年限公式 | ⚠️ InterestCalc 类 |
| `provision`（计提，9 处） | 坏账/减值计提 | 比例×基数 | ⚠️ ECL 类 |
| `completeness_test`（完整性测试） | 跳号测试 C24-3/借贷发生额 C24-1 | tb_ledger 序号连续性 | 🔴 缺 |

#### L4 — 文档/记录型（表单录入 + 模板，联动浅）
| functional_type | 对应底稿 | 形态 |
|---|---|---|
| `program_console`（程序表，241 处！最多） | 各类审计程序表 A/D2A | ✅ GtAProgramConsole 已最佳实践 |
| `index_directory`（目录，148 处） | 底稿目录/审计标识 | ⚠️ GtBIndex 有导航，缺"科目→程序流程图" |
| `disclosure`（附注披露，176 处） | 附注披露信息 | ✅ GtCNoteTable |
| `control_test`（控制测试，126+119 处） | IT控制测试 RP/控制测试汇总 | ✅ GtEControlTest |
| `control_evaluation`（评价控制偏差，72 处） | 评价控制偏差 C10-2 | ⚠️ |
| `audited_table`（审定表，108 处） | 期后事项审定 A11-1 | Univer/d-form-table |
| `adjustment`（调整分录，99 处） | 调整分录汇总 | ⚠️ 联动 adjustments 模块 |
| `analysis`（分析，99 处） | 横向/纵向/比率分析 A1-13 | ⚠️ 部分 |
| `policy_check`（会计政策，21 处） | 会计政策检查 D2-8 | 表单 |
| `interview`（访谈，12 处） | 沟通记录/调查问卷 A15-1 | 表单 |
| `representation`（声明书） | 管理层声明 | 文档 |
| `plan_summary`（计划/小结，14 处） | 盘点计划 F2-22/监盘小结 | 文档 |
| `inventory_count`（盘点，16+13 处） | 库存现金盘点 E1-7/存货监盘 | ⚠️ InventoryStocktake |
| `risk_assessment`（风险评估，30 处） | 风险评估表/特别风险舞弊 | 表单 |
| `understanding`（业务了解，18 处） | 了解业务模式 B10-2/行业环境 | 文档 |
| `review_record`（复核记录，31 处） | 项目负责人复核 A22 | 表单+签字 |

### 20.3 关键洞察：三个维度正交，缺一个映射表

底稿实际有 **3 个正交维度**，当前系统只用了 1 个：
1. **渲染形态**（componentType：HTML 9 类 / Univer）✅ 已有
2. **审计循环**（audit_cycle：A-S）✅ 已有
3. **功能行为**（functional_type：上述 14 大类 / 30+ 细类）🔴 **完全缺失**

一张"应收账款账龄表"= 渲染形态 `d-form-table` + 循环 `D` + 功能 `aging`。当前系统知道前两个，不知道第三个，所以无法自动给它挂"FIFO 账龄计算"动作。**补 functional_type 映射是 Spec 6 的地基**。

### 20.4 用户特别点名的几类，专属设计建议

**目录页（148 处）→ 不只是导航，要"科目程序全景图"**：
用户要"流程图/全仓图体现相关科目的所有程序 + 跳转"。当前 GtBIndex 是线性索引导航，应升级为：以科目为中心的**辐射图**（科目 → 该科目涉及的所有底稿程序 A1A/D2-1/D2-8… → 点击跳转），复用第十七章的 locate 能力 + GtAuditFlowGraph 的 SVG 渲染。

**程序控制台（241 处，最多）→ 已是标杆，推广其模式**：
GtAProgramConsole 已是最佳实践（进度+筛选+展开+审计逻辑流程图+可点索引）。建议把它的"中控台"模式抽象为**其他 L4 类型的范本**，而非每类重造。

**抽凭表 → 完整抽样工作流**：
不只是样本量公式，要"选总体（从 tb_ledger）→ 选方式（分层/随机/大额/MUS）→ 弹窗设参数 → 抽样 → 填回底稿 → 关联凭证照片（OCR 已有）→ 记录抽样结论"。

**合同检查表 → LLM 替换正则 + 逐份确认**：
现状 `_extract_contract_fields` 是正则（合同号/金额简单匹配），用户明确要 **LLM 识别 + 每份合同信息生成要用户确认**。这依赖 Spec 4 的 LLM 链路修复。

### 20.5 对 Spec 6 的修正：从"几个动作"扩展为"功能类型框架"
第十九章 Spec 6 只列了抽凭/截止/合同/月度 4 个动作，本章数据证明**功能类型有 14 大类 30+ 细类**。Spec 6 应重新定位为：
- **不是"加 4 个动作"，而是建"functional_type 分类 + 动作面板框架"**（一次性机制，后续加类型只配置不改框架）
- **优先级排序**（按 价值×就绪度）：L1 取数填充型先做（cutoff/monthly/aging 后端已就绪，补弹窗+填充即可）→ L2 文档识别型（合同 LLM，依赖 Spec4）→ L3 测算型（并入 6 stub 对话框治理）→ L4 多数已有渲染（按需补联动）
- **分类灌入**：复用已有 `workpaper_template_analysis.json` 的 class + sheet 名关键词，可半自动推断 functional_type（如名含"账龄"→aging、"截止"→cutoff、"合同"→contract_ledger），人工校正少量

### 20.6 结论
底稿功能类型**实测有 14 大类 30+ 细类**（远超十九章举例的 4 类），sheet 名关键词频次是铁证（程序 241/检查 209/披露 176/明细 120/测试 119…）。核心是补**第三个正交维度 functional_type**（渲染形态、审计循环之外）。**好消息延续**：L1 取数填充型的后端能力（cutoff/monthly/aging）已就绪，L4 文档型多数已有渲染，真正要新建的是 L1 的"填回底稿"+ L2 合同 LLM + 目录页全景图 + functional_type 分类框架。Spec 6 应从"加几个动作"升格为"功能类型框架 + 分阶段填充各类型"。

> 附：第二十章基于 `workpaper_template_analysis.json` 2602 sheet 实测关键词频次 + 33 class 样本归纳；functional_type 谱系是建议分类，落地时需审计业务专家校正归类边界（如"检查 209"含多种性质需细分）。


---

## 二十一、抽凭表原始凭证上传 + LLM 识别 + 关联填充（深化 sampling 功能类型）（2026-05-30）

用户深化抽凭表需求：**支持上传原始凭证（记账凭证/发票/出入库单等）→ 标记关联 → LLM 识别填充抽凭表内容**。本章实测现有能力边界，给出精确 gap 和落地方案。

### 21.1 现状实测：能力分三层，识别引擎是关键短板

| 能力 | 现状 | 文件 |
|---|---|---|
| OCR 结果→抽凭表填充 | ✅ 已有 | `wp_ocr_fill_service.fill_voucher_table_from_ocr`（填 parsed_data.voucher_rows，带 confidence + source='ocr'） |
| 照片↔抽凭行双向关联 | ✅ 已有 | `link_photo_to_voucher_row`（row.attachment_id 单向字段） |
| 凭证识别引擎 | 🔴 **正则，且仅记账凭证** | `wp_ocr_voucher_service.parse_voucher_from_text`（正则提取凭证号/日期/借贷分录） |
| 发票/出入库单识别 | 🔴 **无专门模板** | — |
| LLM 识别 | 🔴 **完全没用** | 现全是正则 + PaddleOCR/Tesseract 纯文字层 |
| 多单据类型关联 | 🔴 缺 | attachment_id 单值，一抽凭行只能关 1 个附件 |

**关键发现**：`docs/requirements.md`（§2226）**早已详尽设计了 12 种单据的 OCR 识别需求**（增值税发票/出库单/入库单/物流单/记账凭证/差旅报销… + 每种的提取字段 + 关联审计领域 + §2317 证据链验证），但**实现停在 Sprint 7 的正则版**——典型的"需求已设计、实现是半成品"gap。用户这次提的正是要把它从正则版推进到 LLM 版。

### 21.2 用户要求拆解 vs 缺口

| 用户要求 | 现状 | 缺口 |
|---|---|---|
| 上传记账凭证 | parse_voucher 正则 | 升级 LLM |
| 上传**发票** | 无 | 新增发票识别（增值税专票/普票字段：购销方/金额/税额/票号/货物） |
| 上传**出入库单** | 无 | 新增出入库单识别（日期/品名/数量/单价/金额/对方） |
| **标记关联** | attachment_id 单值 | 扩展为一抽凭行 ↔ 多原始凭证（记账凭证+发票+出库单组成一组证据） |
| **LLM 识别填充** | 正则 | 多模态 LLM（图片直接喂）或 OCR 文字层 + LLM 结构化 |

### 21.3 落地方案：多单据 LLM 识别 + 证据组关联

#### 设计核心：抽凭行 = 一组原始凭证的证据链
一笔抽样交易，原始凭证不止一张：记账凭证 + 对应发票 + 出/入库单 + 银行回单。当前 `attachment_id` 单值不够，应改为：
```
voucher_row {
  id, voucher_no, ..., 
  evidence_group: [
    { attachment_id, doc_type: 'accounting_voucher', extracted: {...}, confidence },
    { attachment_id, doc_type: 'invoice', extracted: {购方,金额,税额,票号}, confidence },
    { attachment_id, doc_type: 'outbound', extracted: {品名,数量,金额}, confidence },
  ],
  cross_check: { 金额一致性, 日期合理性, ... }  // 证据链交叉核对
}
```

#### 实施分层
**P1 — LLM 多单据识别引擎（依赖 vllm-httpx-bugfix）**：
- 新建 `wp_document_recognizer`（替代/扩展 wp_ocr_voucher_service）
- 按 doc_type 调 LLM：图片→OCR 文字层（已有 unified_ocr）→ LLM 按单据类型 prompt 结构化提取（复用 requirements.md §2226 的字段定义作 prompt 模板）
- 支持记账凭证/发票/出入库单/银行回单/物流单 5+ 类
- 每类返回结构化 JSON + confidence

**P2 — 证据组关联 + 填充**：
- voucher_row.attachment_id → evidence_group[]（schema 迁移，向后兼容旧单值）
- 上传时选"关联到哪一抽凭行 + 单据类型"→ LLM 识别 → 填入 evidence_group
- 前端：抽凭行展开显示该行所有原始凭证缩略图 + 提取字段，点击看大图

**P3 — 逐份确认（呼应合同表同款诉求）**：
- LLM 识别结果默认 pending，逐份确认/修正（复用 V3 Req6 AiContent 确认流）
- 识别字段与抽凭表既有数据（从 tb_ledger 抽来的金额）比对，不一致高亮

**P4 — 证据链交叉核对（高阶，呼应 requirements.md §2317）**：
- 一组证据内：发票金额 vs 记账凭证金额 vs 出库单金额一致性
- 日期合理性（出库≤发票≤记账）
- 异常自动标注（呼应 TSJ 复核 + 第九章）

### 21.4 复用与新建边界
- **复用**：unified_ocr（文字层）/ fill_voucher_table_from_ocr（填充框架）/ link_photo_to_voucher_row（关联机制）/ V3 Req6 确认流 / requirements.md §2226 字段定义
- **新建**：LLM 多单据识别引擎 / evidence_group schema / 证据链交叉核对 / 前端证据组 UI
- **依赖**：vllm-httpx-bugfix（LLM 链路）+ Spec 6 的 sampling functional_type 框架

### 21.5 归入 Spec 6 的 sampling 类型（深化）
本章是第二十章 `sampling` functional_type 的深化。Spec 6 的抽凭动作应从"样本量计算 + 简单 OCR"扩展为完整工作流：
```
抽样（从 tb_ledger 分层/随机/大额）→ 生成抽凭表行
  → 上传原始凭证（多类型）→ LLM 识别 → 填入 evidence_group
  → 逐份确认 → 证据链交叉核对 → 抽凭结论
```
这条链跨 Spec 6（抽样框架）+ Spec 4（LLM）+ 现有 OCR 资产，是"人机互补"在抽凭场景的完整落地。

### 21.6 结论
用户要的"原始凭证上传 + LLM 识别 + 关联填充"是**真实且需求文档早有详尽设计（§2226 12 种单据）的功能**，但实现停在 Sprint 7 正则版（仅记账凭证、无 LLM、单附件关联）。核心升级 3 点：① 正则→LLM 多模态识别 + 扩展发票/出入库单；② attachment_id 单值→evidence_group 多单据证据组；③ 逐份确认 + 证据链交叉核对。复用现有填充/关联框架 + requirements.md 字段定义，依赖 vllm-httpx-bugfix。归入 Spec 6 sampling 类型的完整工作流。

> 附：第二十一章基于 2026-05-30 实测（wp_ocr_fill_service 全文 / wp_ocr_voucher_service 正则 / requirements.md §2226 单据表已设计）；"需求已设计实现是正则半成品"是关键定性，LLM 多模态识别真实效果需 vllm 链路修复后实测。


---

## 二十二、前 21 章未覆盖维度的补充规划（2026-05-30）

前 21 章覆盖了结构/测试/卡点、运行时质量、TSJ 复核、联动溯源、布局、HTML 渲染、EDITOR_MAP、业务链、异构追溯、功能类型、抽凭凭证。本章系统补齐**还没系统看的 6 个维度**（实测现状 + 改进点），不重复前文。

### 22.1 性能与大数据（🔴 真盲区）
**现状实测**：底稿组件**几乎无虚拟滚动**——GtWpRenderer 只有"lazy load 组件"，没有大表行虚拟化。HTML 类用 el-table 直接渲染全部行。
**问题**：
- 大底稿（如序时账级明细表、F 数据表上千行）全量 DOM 渲染会卡
- 第十二章提议的 `g-generic-table` 若不带虚拟滚动，承接 F/G 大表会有性能问题
- TrialBalance 已有 el-table-v2 虚拟滚动（>1000 行），但**底稿渲染器没复用这个能力**
**改进**：
- HTML 渲染器的表格类组件（C/D-table/g-generic-table）接入 el-table-v2 条件虚拟化（>500 行启用）
- 抽凭表/明细表大数据场景分页或虚拟滚动
- 6000 并发目标下，底稿列表/渲染的性能基准需纳入压测（呼应 phase3 UAT-5）

### 22.2 底稿级并发协作（⚠️ 部分，有断层）
**现状实测**：`presence_service`（Redis ZSET 在线感知）✅ + `wopi_service`（_locks 最大 5 编辑人）✅ + `note_section_lock_service`（附注章节锁）✅，但**底稿编辑器的 cell 级/sheet 级锁缺失**——只有 WOPI（Office 在线编辑）有锁，HTML 渲染器编辑无并发控制。
**问题**：
- 两人同时编辑同一张 HTML 底稿的不同 sheet，无锁无冲突检测（只有离线回传 `check_version_conflict`）
- presence 能看到"谁在这张底稿"，但不能阻止同时改同一格
**改进**：
- HTML 渲染器接入 sheet 级软锁（复用 note_section_lock 模式）+ presence 显示"X 正在编辑此 sheet"
- 保存时乐观锁版本校验（parsed_data 带 version，冲突弹合并）
- 呼应第十一章 EditorBanners 已有"编辑锁提示"横幅，但后端锁机制要补全

### 22.3 模板版本升级迁移（🔴 缺失，审计实务痛点）
**现状实测**：跨年继承能力分散且已有不少（程序 `copy_from_prior` / `prior_year_summary` 上年结论 / `=PREV` 跨年公式 / RAG 上年底稿参照），但**"模板版本升级后，已编制的底稿如何迁移"完全没有机制**。
**问题**：
- 致同模板 v2025-R5 升级到 R6 时，已经填了数据的底稿怎么办？sheet 增删、列变化如何迁移用户数据？
- `workpaper_template_version` 表有版本字段，但无"版本间 diff + 数据迁移"逻辑
**改进**：
- 模板版本升级时生成 sheet/列级 diff（新增/删除/改名）
- 已编制底稿数据按 diff 迁移（保留用户填的值，新列空，删列归档）+ 迁移报告
- 这是中长期能力，但 6000 人规模 + 模板年度修订必然遇到

### 22.4 审计轨迹与防篡改（✅ 较完整，可深化）
**现状实测**：`wp_audit_trail_service.get_cell_history`（cell 级历史）✅ + `audit_log_helper` hash_chain（哈希链防篡改，V007）✅ + `wp_sign_date_chain_service`（签字日期链）✅。**这块是健康的**。
**可深化**：
- cell history 前端可视化（点单元格看"谁何时改了什么"时间线）——后端有，前端展示弱
- hash_chain 完整性校验有 `/api/audit-logs/verify-chain` 端点（但 memory 记录该 router 曾未注册，需确认）
- 归档时生成"底稿编辑全轨迹"审计报告（CAS 1131 合规）

### 22.5 离线编辑与导入导出（✅ 已较完整）
**现状实测**：`wp_offline_export_service`/`wp_offline_import_service`（4 色 cell + _meta_ base64+gzip + AES + 字段级 diff）✅ + `wp_download_service.check_version_conflict`✅ + WOPI Office 在线编辑✅。**这块设计完整**（workpaper-editor-slimdown spec 沉淀）。
**可深化**：
- 离线包导入的 cell 级合并冲突 UI（已有 diff，merge 勾选已补）——基本够用
- 主要是确保与 22.2 并发锁/版本冲突机制统一（避免离线回传和在线编辑两套版本逻辑）

### 22.6 移动端 / 多端适配（🔴 未覆盖，需求待确认）
**现状**：前 21 章全是桌面端假设（固定宽度布局、Backspace 返回、右键菜单）。
**问题**：审计师现场盘点（库存监盘 E1-7/存货监盘）天然是移动场景——拿平板/手机拍盘点照片、填盘点表。当前底稿编辑器对移动端无适配。
**改进（需先确认需求）**：
- 盘点类底稿（inventory_count）的移动端轻量录入页（拍照 + 数量录入，呼应第二十一章原始凭证上传）
- 函证回函、现场访谈记录的移动端录入
- 这是产品方向决策，非纯技术，建议先确认是否在范围

### 22.7 汇总：6 维度优先级
| 维度 | 现状 | 优先级 | 归属 |
|---|---|---|---|
| 性能/虚拟滚动 | 🔴 盲区 | P1（6000 并发硬需求） | 并入 Spec 6 g-generic-table + 独立性能 spec |
| 并发协作锁 | ⚠️ 断层 | P2 | 新 spec 或并入 Spec 3 |
| 模板版本迁移 | 🔴 缺失 | P2（中长期） | 独立 spec（年度修订必遇） |
| 审计轨迹 | ✅ 健康 | P3（前端可视化） | 并入 Spec 5 ux |
| 离线导入导出 | ✅ 完整 | — | 维护即可 |
| 移动端 | 🔴 未覆盖 | 待确认 | 产品决策 |

### 22.8 结论
前 21 章聚焦"功能完整性与体验"，本章补 6 个系统性维度。**真盲区是 3 个**：① 性能/虚拟滚动（6000 并发硬需求，且 g-generic-table 依赖它）② 模板版本升级迁移（年度修订必遇，完全无机制）③ 移动端盘点/函证（产品方向待确认）。**健康的是 2 个**：审计轨迹（hash_chain + cell history）、离线导入导出（4 色 + AES + diff）。并发协作锁是半成品（presence/WOPI 有，HTML 渲染器编辑无锁）。建议性能纳入 Spec 6 + 独立压测，模板迁移单独立 spec，移动端先确认需求边界。

> 附：第二十二章基于 2026-05-30 实测（GtWpRenderer 无虚拟滚动 / presence_service+wopi_service 有锁但 HTML 编辑无锁 / 跨年继承分散无模板迁移 / wp_audit_trail+hash_chain 健康 / wp_offline 完整）；移动端是产品方向需用户确认是否在范围。


---

## 二十三、多准则切换 + PBC 清单联动（最后两个未挖维度）（2026-05-30）

本章详细分析剩余两个未覆盖维度。两者成熟度截然相反：多准则切换是"附注层成熟、底稿层薄弱"，PBC 是"模型完整、路由空壳"。

### 23.1 多准则切换（国企 SOE ↔ 上市 Listed）

#### 23.1.1 现状实测：三层成熟度天差地别
| 层 | 现状 | 文件 |
|---|---|---|
| **附注层** | ✅ **成熟**：`note_conversion_service` V2（SOE↔Listed 互转 + section_id 保留 + 共有章节不丢用户编辑 + soe_only 归档/listed_only 创建 + format_diff 适配）+ ADR-021 + 大量 PBT（roundtrip SOE→Listed→SOE 不变） | note_conversion_service / consol_cross_template_service |
| **报表层** | ⚠️ **半成型**：generate 时按 applicable_standard 分流，word_template_filler 按 template_type 选 `附注模板_{soe/listed}.docx` | trial_balance_service / word_template_filler |
| **底稿层** | 🔴 **薄弱**：只有"生成时按 scenario 文件级裁剪"（normal 排除 IPO/上市/新三板文件），**没有"已编制底稿 SOE↔Listed 切换"** | wp_template_init_service `_filter_files_by_scenario` |

#### 23.1.2 核心问题：准则状态无统一源 + 底稿层不能切换
**问题 1 — 准则状态散落，无单一真理源**：
- `project.wizard_state.basic_info.data.template_type`（项目向导）
- 附注用 `current_standard`（soe_standalone/listed_standalone/soe_consolidated/listed_consolidated）
- 底稿用 `scenario`（normal/ipo/listed/transfer/restructure/fraud_response）
- 报表用 `applicable_standard`
- **4 套口径、4 个地方**，切换时各模块各读各的，极易不一致

**问题 2 — 底稿层无切换能力**：
附注能 SOE↔Listed 互转保留编辑，但底稿不能。实务场景：一个项目从"按国企准则做"中途变成"要上市（按上市准则）"，附注能转，**已编制的底稿（含用户填的数据）转不了**——只能重新生成丢数据，或手工调。这与附注层的成熟形成断层。

**问题 3 — 准则差异维度比 SOE/Listed 更多**：
实测 scenario 有 6 档（normal/ipo/listed/transfer/restructure/fraud_response），current_standard 有 4 值（standalone/consolidated × soe/listed）。真实准则差异是**多维的**（企业性质 × 单体/合并 × 上市阶段），当前用扁平字符串表达，组合爆炸。

#### 23.1.3 改进方案
- **P1 统一准则状态源**：建 `project.applicable_standard` 结构化字段（{entity_type: soe/listed/private, scope: standalone/consolidated, stage: normal/ipo/...}），各模块统一读，废弃 4 套散落口径（迁移期保留映射）
- **P2 底稿层准则切换**：参照 note_conversion_service V2 模式，给底稿做"切准则保留用户数据"——sheet/列差异 diff + 共有保留 + 独有归档/新建（复用第二十二章 P3 模板版本迁移的 diff 机制，两者本质同源）
- **P3 准则差异可视化**：切换前预览"将影响哪些底稿/附注/报表 + 哪些数据会归档"（呼应第十章 stale 影响预览）

### 23.2 PBC 清单联动（客户资料收集）

#### 23.2.1 现状实测：模型完整，路由是空壳
| 层 | 现状 |
|---|---|
| **模型** | ✅ `PBCChecklist`（pbc_checklist 表）+ PbcStatus（pending/received/...）+ schemas（PBCItemCreate/Update/Response）齐全 |
| **路由** | 🔴 **空壳**：`pbc.py` 的 `list_pbc` 直接返回 `{"status": "developing"}`，无真实 CRUD |
| **联动** | 🔴 **零联动**：PBC 与底稿、附件、任务完全没连 |
| **关联痕迹** | pm_service 有 `related_pbc_id` 字段（占位 None）/ phase15 IssueTicket source 含 'pbc' |

#### 23.2.2 核心问题：PBC 是"挖了坑没填"的功能
- 模型/schema/前端 PBCPanel.vue 都建了（基础设施投入了），但 **router 是 developing 占位**——典型"挖坑没填"
- 更关键：**PBC 的价值在联动**，孤立的资料清单意义不大。真实价值链：
  ```
  PBC 清单（要客户提供什么）→ 客户上传资料 → 资料关联到对应底稿
    → 底稿编制时知道"支撑证据已收到/缺失" → 缺失资料自动催收
  ```
  这条链一个都没接

#### 23.2.3 改进方案
- **P1 填实 PBC CRUD**：pbc.py 从 developing 占位补成真 CRUD（模型已就绪，纯补 router + service）
- **P2 PBC ↔ 资料/附件联动**：客户上传资料标记关联到 PBC 项 → PBC 项状态 pending→received（复用第二十一章 evidence 上传机制）
- **P3 PBC ↔ 底稿联动**：底稿编制侧栏显示"本底稿依赖的 PBC 项及收集状态"（缺失证据高亮，呼应第十章附件入网 + TSJ"问题关联证据"）
- **P4 缺失资料催收**：PBC 项逾期未收 → 自动建 IssueTicket（source='pbc' 已预留）+ 通知客户（呼应链 D 工单机制）
- **需求依据**：`requirements.md` §568 已设计"AI 自动比对 PBC 清单标注已收到/未收到 + 标注缺失资料（如有采购合同但未见对应入库单）"——又是"需求已设计、实现空壳"

#### 23.2.4 与证据链的天然融合
PBC（资料应收）+ 第二十一章原始凭证（证据已收）+ 第十章附件入网（证据关联）= **完整的审计证据收集闭环**：
```
PBC 清单定义"需要什么" → 客户/审计师上传"收到什么"（LLM 识别）
  → 关联到底稿/报表行（附件入网）→ 缺口自动标注（AI 比对）→ 催收
```
三块本是一个证据管理体系的不同切面，建议作为一个大主题统筹（而非散在 3 个 spec）。

### 23.3 归入 spec 路线图
| 维度 | 优先级 | 归属 |
|---|---|---|
| 统一准则状态源 | P1 | 新 spec `multi-standard-unification`（跨底稿/附注/报表，基础设施级） |
| 底稿层准则切换 | P2 | 同上 spec，复用 note_conversion 模式 + 模板迁移 diff |
| PBC 填实 CRUD | P1（投入小，模型已就绪） | 新 spec `pbc-evidence-collection` |
| PBC↔底稿/附件联动 | P2 | 同上 spec，与第二十一章证据组 + 第十章附件入网统筹 |

### 23.4 结论
- **多准则切换**：附注层已成熟（note_conversion V2 + ADR-021），但**底稿层薄弱（只有文件裁剪不能切换已编制底稿）+ 准则状态 4 套口径散落无统一源**。核心是建结构化 `applicable_standard` 统一源 + 底稿层复用附注的转换模式。
- **PBC 清单**：**模型/schema/前端全建好，但 router 是 `developing` 空壳，零联动**——典型"挖坑没填"，且 requirements.md §568 早有详尽设计。填实成本低（模型就绪），价值在联动（PBC→资料→底稿→催收）。
- **统筹建议**：PBC（应收）+ 原始凭证（已收，第二十一章）+ 附件入网（关联，第十章）是**同一个审计证据收集体系的三个切面**，建议合并为一个证据管理大主题统筹，避免散在多个 spec 各做一半。

> 附：第二十三章基于 2026-05-30 实测（note_conversion_service V2 成熟 + wp_template_init scenario 文件裁剪 / pbc.py router 返回 developing 占位 / PBCChecklist 模型完整 / requirements.md §568 PBC 比对已设计）；准则状态 4 套口径散落、PBC 空壳是两个关键定性。


---

## 二十四、全景收敛 + 增量点甄别（诚实结论：维度已基本覆盖）（2026-05-30）

用户问"是否还有进一步改进建议"。本章诚实回答：**底稿模块的功能维度，前 23 章已系统覆盖**。再硬造"新维度"会沦为重复或牵强。本章做两件有价值的事：① 甄别实测后**真正还值得提的少数增量点**（不凑数）；② 把 23 章散落的 spec 收敛成一张全景图。

### 24.1 先说实测确认"已覆盖、无需新规划"的（避免重复造）
这几个我特意查了，确认**已有成熟实现，不需要新建议**：
- **质量评分**：`wp_quality_score_service` 5 维加权（完整性30%+一致性25%+复核20%+程序完成15%+自检10%）✅ + health dashboard 展示 ✅
- **编制智能引导**：`wp_guidance_service`（按底稿类型给引导步骤）✅
- **EQCR 联动**：SOD 独立性规则 + 签字状态机（order=4 EQCR→eqcr_approved）✅
- **全局检索**：global_search + version_search ✅
- **stale 聚合**：stale_summary_aggregate（为 Partner/EQCR/List 单端点聚合）✅

### 24.2 实测后真正值得提的 3 个增量点（不凑数）

**增量 1 — quality_score 是"算了不用"的展示指标，未驱动决策**：
实测：`recalc_quality_score` 在程序完成/裁剪时触发 ✅，health dashboard 展示平均分 ✅，但**它没进任何门禁/决策**——纯展示。
**建议**：让 quality_score 真正驱动——① 提交复核门禁纳入"质量分 < 阈值警告"；② PM 看板按质量分排序找薄弱底稿；③ 质量分低的维度（如自检通过率低）给具体改进提示。**这是把已有指标"用起来"，投入小价值实。**

**增量 2 — 智能引导是静态映射，没用上已有的丰富上下文**：
实测：`wp_guidance_service._GUIDANCE_MAP` 是**按底稿类型的静态步骤映射**，没结合该底稿的实际状态（已填了什么、缺什么、TSJ 复核要点、上年同底稿做法）。
**建议**：引导从"静态步骤"升级为"上下文感知"——结合 prior_year_summary（上年怎么做）+ TSJ 提示词（该查什么）+ 当前 stale/缺失项（还差什么）+ functional_type（该用什么动作）。这把第九章 TSJ、第二十章 functional_type、跨年继承串成"编制时的智能助手"。

**增量 3 — 各种"完成率/质量分/进度"指标口径分散**：
实测 `completion_rate` 在 7+ 处各自计算（pm_service/partner_service/role_ai_features/qc_dashboard/wp_progress…），口径可能不一（有的按 review_passed，有的按 edit_complete）。
**建议**：统一进度/质量指标的计算口径到一个 service（呼应第七章 float 一致性、第十六章门禁口径统一的同类问题——**指标口径分散是这个项目的系统性小病**）。

### 24.3 全景收敛：23 章 → 完整 spec 地图

前 23 章产出的改进点收敛为 **3 个梯队 / 11 个 spec + 1 checklist**：

#### 梯队一：治理与地基（先做，低风险或被依赖）
| spec | 来源章节 | 性质 |
|---|---|---|
| `workpaper-guardrail-cleanup`（checklist） | 二/七/十八 | 白名单+float卡点+EDITOR_MAP+路径bug |
| `gtdform-test-and-shrink` | 一/三/十八 | D类补测+拆分 |
| `multi-standard-unification` | 二十三 | 统一准则源（被多模块依赖） |
| `vllm-httpx-bugfix` | 七/九 | LLM 地基（解锁 AI 全线） |

#### 梯队二：核心能力（中等体量，有依赖）
| spec | 来源章节 | 依赖 |
|---|---|---|
| `wp-locate-foundation`（3a） | 十/十七 | 无（技术枢纽） |
| `wp-traceability-panel`（3b） | 十/十七 | 3a |
| `wp-tsj-llm-review` | 九 | vllm + 3a |
| `wp-functional-actions` | 十九/二十/二十一 | 3a + 部分 LLM |

#### 梯队三：体验与扩展（最后/穿插）
| spec | 来源章节 |
|---|---|
| `wp-frontend-ux-polish`（含 quality_score 驱动 + 智能引导升级） | 五/六/二十四 |
| `wp-evidence-collection`（PBC + 原始凭证 + 附件入网统筹） | 十/二十一/二十三 |
| `wp-performance-virtualization` | 二十二 |
| `wp-template-migration`（模板版本升级 + 跨年） | 二十二/二十三 |

### 24.4 一个贯穿全文的元结论：这个项目的系统性小病
回看 24 章，反复出现**同一类问题**（不是底稿模块独有，是项目级模式）：
1. **"需求已设计、实现半成品/空壳"**：TSJ 复核孤儿、PBC developing 占位、合同正则非 LLM、requirements.md §2226 单据识别只做了正则版——**设计跑在实现前面，留下大量"挖了坑没填"**
2. **"能力已有、口径分散"**：completion_rate 7 处算、准则状态 4 套口径、float 金额散落、门禁反馈各做各的、trace service 3 个粒度不一——**缺收口统一**
3. **"算了不用/做了不接"**：quality_score 纯展示、EDITOR_MAP 死路由、trace service 孤儿、本机 classification 没 seed——**末端一跳缺失**

**真正的高 ROI 不是加新功能，而是"填坑 + 收口 + 接通末端一跳"**——把已投入 80% 的半成品推到 100%。这是比任何新维度都更值得做的事。

### 24.5 结论
诚实说：**功能维度已覆盖，不必再硬造新维度**。值得做的增量是 3 个"把已有用起来"的点（quality_score 驱动决策 / 引导上下文感知 / 指标口径统一）。更重要的是 24.4 的元结论——这个项目的系统性特征是"设计超前、实现留坑、口径分散、末端缺一跳"，**最高 ROI 是填坑收口而非加新功能**。23 章的所有 spec 收敛为 3 梯队 11 spec + 1 checklist（24.3），可作为实施总图。

> 附：第二十四章基于 2026-05-30 实测（quality_score 接线但不进门禁 / wp_guidance 静态映射 / completion_rate 7 处分散 / EQCR+global_search+stale_aggregate 已成熟）；"设计超前实现留坑"是贯穿 24 章的元结论，非单点问题。
