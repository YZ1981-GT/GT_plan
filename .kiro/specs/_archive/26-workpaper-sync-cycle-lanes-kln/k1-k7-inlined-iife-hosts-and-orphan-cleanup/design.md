# K1~K7 内联 IIFE 宿主与 orphan 清理 — 设计

## 上游与边界

| 项 | 内容 |
|---|---|
| 共同裁决 | `k-cycle-sync-foundation-and-first-canary` 的 **KC-1 ~ KC-24** —— 🔴 **本 spec 只引用编号，不复述正文** |
| 本 spec entry | `xlsx/gt-k1-other-receivables` · `xlsx/gt-k2-other-current-assets` · `xlsx/gt-k3-other-payables` · `xlsx/gt-k4-other-current-liabilities` · `xlsx/gt-k5-provisions` · `xlsx/gt-k6-held-for-sale` · `xlsx/gt-k7-deferred-income`（**7 条 = BP-5 全集**） |
| Property 前缀 | `KA-P` |
| 变异脚本 | 复用 `backend/scripts/diagnose/mutate_k_cycle_guards.py` · `mutate_task53_k_cycle_migration_guards.py`（**不新写**） |
| 删除计划 | `backend/data/workpaper_sync_k_cycle_deletion_plan.json` |

🔴 **本 lane 与 lane 2 的分界 = BP-5 / BP-6**：本 lane 7 条全是「宿主内联 IIFE + orphan 孪生」，lane 2 的 5 条全是「宿主 import 专用 composable」。两集合互斥，并集 12 条，加 foundation 的 K10 == 13 ✓。

---

## 聚类理由：为什么这 7 条在一起

1. 🔴 **BP-5 的 entry 全集恰好是这 7 条**（`capability_target_blocked_by` 含 BP-5 的现算为 K1~K7）⇒ 「7 个一阶 orphan 的删除判据」写一次即收口，分开会抄七遍。
2. 🔴 **BP-8 的 45 处按 BP-5/BP-6 分界恰好二分成 24 / 21**，本 lane 占 **24**（K1 3 · K3 1 · K5 7 · K6 7 · K7 6），不跨 lane。
3. 🔴 **definedName 断链 65 个全在本 lane**（K2 29 + K4 36）⇒ 模板层治理单点收口。
4. 🔴 **下标族 removeRow 站点集中在 K3~K7**（全在本 lane）⇒ 与 BP-8 的位置化在同一批文件里叠加，组合判据只在本 lane 需要。
5. **内含对照组**：K2 与 K4 的位置化命中为 **0**（K 域零缺陷 4 条里的 2 条）⇒ 能判断某形态是特例还是通例。

**否决把 K1 单独拆一份**：K1 虽然最重（BP-4 writeoff + 70 格 `#REF!` + 17 sheets + 142 键 + 真库 290,402 B），但它与 K2~K7 同属 BP-5，分开会把「7 个 orphan 的两阶可达性判据」抄两遍；BP-4 与 `#REF!` 两件事作本 lane 内的专节（KA-1 / KA-4）即可。

---

## KA-1 ~ KA-7 本 lane 专属裁决

### KA-1 BP-4：K1-9 writeoff 的 adapter 化

**结论**：`is_client_only == False`，裁决 `must_be_adapter_borne`。

**5 hop 写路径**（按端点字面量与形态定位，不写行号）：

| hop | 位置 | 动作 |
|---|---|---|
| 1 | `useK1WriteoffCheck.ts` 的 `buildSavePayload()` | 产出 1 主键 + 2 合计键 |
| 2 | `K1TabWriteoffCheck.vue` 的 `persist()` | 写进 `allResponses` 并 `emit('save', …)` |
| 3 | `GtK1OtherReceivables.vue` 的 `handleChildSave()` | 调 `persistence.save(itemId, toChecklistPatch(value))` |
| 4 | `useChecklistPersistence.ts` | 发 `PUT /api/workpapers/{wpId}/checklist-responses` |
| 5 | `backend/app/routers/checklist_responses.py` | PUT 处理器真实存在（非 404） |

**五个常量**（`useK1WriteoffCheck.ts` 的常量区，形态 `const XXX = 'K1-…'`）：

| 常量 | 值 | role | 精确命中 | 子串命中 |
|---|---|---|---|---|
| `ITEM_ID` | `K1-9-writeoff` | `primary_managed_table` | **9** | 🔴 **12** |
| `REVERSAL_TOTAL_KEY` | `K1-9-reversal-total` | `derived_total` | 2 | 2 |
| `WRITEOFF_TOTAL_KEY` | `K1-9-writeoff-total` | `derived_total` | 2 | 2 |
| `K1_3_ROWS_KEY` | `K1-3-baddebt-rows` | `cross_sheet_read` | 8 | 8 |
| `K1_11_ITEM_ID` | `K1-11-related-party` | `cross_sheet_read` | 3 | 3 |

🔴 **口径反证**：`K1-9-writeoff` 的子串命中 **12** 比精确命中 **9** 多 **3**，因为 `'K1-9-writeoff-total'` 被算进去。slice 明文记录「首轮实测差 3 处，守卫打红才发现」。

**payload 形态**：`JSON.stringify({ tables: { reversal: [...], writeoff: [...] }, auditProcedures, auditNote, conclusion, conclusionOption })`

**OO 对端**：模板 `K1 其他应收款.xlsx` **有** sheet `坏账准备转回（收回）、核销检查表K1-9`，但无 adapter/contract 映射 ⇒ `oo_counterpart_status = absent`。🔴 **这不是「无 HTML 对端」**，AC 12.8 的唯一判据是后者。

**该 sheet 精确几何**（`r=25 c=8 merged=2`，公式 6 个，**裸 IF 0**）：

| 区 | 模板行 | payload 字段 |
|---|---|---|
| 分区（一）本期重要的坏账准备转回检查 | R10 标题 / R11 单级表头 8 列 / **R12:R14 三行全空** | `tables.reversal[]` |
| footer（一） | R15 `合 计` = `=SUM(E12:E14)`（**只 E 列**） | `reversalTotal` |
| 分区（二）本期重要的核销检查 | R16 标题 / R17 单级表头 8 列 / **R18:R20 三行全空** | `tables.writeoff[]` |
| footer（二） | R21 `合 计` = `=SUM(C18:C20)`（**只 C 列**） | `writeoffTotal` |
| 说明区 | R22 三、审计说明 / R25 四、审计结论 | `auditNote` / `conclusion` |

有效列 8 == `max_column` ⇒ UUID 列 **9**。
🔴 **行数错配必须由 adapter 处理**：模板数据区**固定 3 行**，HTML 侧动态行。
🔴 **Property 24 的精确落点**：两个 `derived_total` 键与模板 footer **一一对应**，且由 `computed` 归约产出 ⇒ 任何 contract 把它们标 `mode: "input"` 即违规。

**7 个猜键零命中**（非空反向分母）：`K1-9-rows` · `K1-9-writeoff-rows` · `K1-9-reversal-rows` · `k1-9-writeoff` · `K1-writeoff` · `K1-9-total` · `K1-9-writeoff-check`。

🔴 **裸 sheet 码 `'K1-9'` 现算 13 处**（slice 内部矛盾：`guessed_keys_note` 写 12、`bare_sheet_code_hits` 写 11，**两个都错**）：

| 文件 | 处数 |
|---|---|
| `K1TabWriteoffCheck.vue` | 4 |
| `K1TabIndex.vue` | 3 |
| `useK1ImportExport.ts` | 2 |
| `useK1WriteoffImportExport.ts` | 2 |
| `k1SheetProgress.ts` | 1 |
| `GtK1OtherReceivables.vue` | 1 |
| **合计** | **13** |

它是 **sheet 码不是 checklist item_id** ⇒ 不得当「传输键存在」的证据，也不得列进零命中清单。

### KA-2 BP-5：7 个一阶 orphan 的两阶可达性与删除

**消费边口径**（与 slice 同口径）：只认三种 **statement-position** 形态 —— `from '<spec>'` / `import('<spec>')` / `vi.mock('<spec>')`，`<spec>` 经 `@/` 与相对路径解析后必须**路径相等**于目标模块（不是 stem 相等，那会把 `./apiPaths/index` 这类误命中）。
🔴 **落在双引号字符串内的匹配一律排除** —— `workpaperSyncLegacyBaseline.generated.ts` 的 JSON `"snippet"` 字段里含完整的 `from '...'` 形态，会骗过路径字面量口径。

| orphan | 行数（`split("\n")`） | 生产边 | 测试边 | legacy `health` | legacy `config` | 宿主孪生前缀 |
|---|---|---|---|---|---|---|
| `useK1DualMode.ts` | 115 | **0** | **0** | 1 | 0 | 🔴 **无** |
| `useK2DualMode.ts` | 115 | **0** | **0** | 1 | 0 | 🔴 **无** |
| `useK3DualMode.ts` | 115 | **0** | **0** | 1 | 0 | 🔴 **无** |
| `useK4DualMode.ts` | 126 | **0** | **0** | 1 | 0 | `k4-dual-mode:`（**撞车**） |
| `useK5DualMode.ts` | 126 | **0** | **0** | 1 | 0 | `k5-dual-mode:`（**撞车**） |
| `useK6DualMode.ts` | 125 | **0** | **0** | 1 | 0 | `k6-dual-mode:`（**撞车**） |
| `useK7DualMode.ts` | 116 | **0** | **0** | 1 | 0 | 🔴 **无** |
| 合计 | **838** | 0 | 0 | **7** | **0** | 撞车 3 / 无持久化 4 |

🔴 **二阶恒 0 的可复算理由**：`components/workpaper/composables/index.ts` 现算 `exists == False` ⇒ 该目录下模块**没有 barrel 可躲**。两侧都验：7 个一阶边数各为 0 **且** barrel 确实不存在。
🔴 **行数口径**：上表用 `len(text.split("\n"))`；`splitlines()` 口径**恒少 1**（逐个 114/114/114/125/125/124/115，合计 831 = 838 − 7）。判据必须声明口径（引用 KC-22②）。
🔴 **与 lane 2 的反向对照**：lane 2 的 6 个 live composable **各有 1 条生产边**，且**各调 1~2 处 `onlyoffice-config`**；本 lane 的 7 个 orphan **config 全为 0**。两侧都验。

### KA-3 KD-2：内联 IIFE 与 localStorage 分裂

| entry | 宿主 IIFE | 宿主 `import useK{n}DualMode` | 宿主 `localStorage` | 宿主内联前缀 |
|---|---|---|---|---|
| K1 | **1** | **0** | **0** | 🔴 无 |
| K2 | **1** | **0** | **0** | 🔴 无 |
| K3 | **1** | **0** | **0** | 🔴 无 |
| K4 | **1** | **0** | 2 | `k4-dual-mode:` |
| K5 | **1** | **0** | 2 | `k5-dual-mode:` |
| K6 | **1** | **0** | 2 | `k6-dual-mode:` |
| K7 | **1** | **0** | **0** | 🔴 无 |
| 合计 | **7** | **0** | 6 | 撞车 3 / 无 4 |

**两类后果**：
- **撞车 3 条（K4/K5/K6）**：同一前缀在 orphan composable 与宿主内联 IIFE **两处各声明一份同值** ⇒ 改线时只改一处会留下**读写不同键的分裂状态**。
- **无持久化 4 条（K1/K2/K3/K7）**：宿主内联实现**完全没有** localStorage，而其 orphan composable 有 ⇒ **「模式偏好是否持久化」在 K 循环内部不一致**，改线须明确目标态。

**其他宿主特征现算**（13 宿主统一口径，本 lane 取 7 条）：`GtOnlyOfficeSheet` 各 4 · `el-segmented` 剥注释后各 1 · `useChecklistPersistence` 各 3 · `useWorkpaperEntryDualMode` 各 **0**（KD-3）· `v-if` 二级门控各 1 · `@/utils/http` 各 1 · `checklist-responses` 各 **0**（在 composable 层）· notice 两符号各 **0**。
🔴 **`apiProxy` 只 K6 宿主命中 1** · 🔴 **`publish-to-tb` 只 K6 宿主命中 1**（全 K 唯一在宿主层的 TB 发布门，引用 KC-4）。

### KA-4 KC-11 落地：K1 双变体披露表 70 格 `#REF!` 的覆盖层修复

| sheet | 格数 | 行数 | 行区间 | 断链列 | 活着的列 |
|---|---|---|---|---|---|
| `附注披露信息(上市公司）` | **35** | 8 | R125-R140 | R125-R129 的 A/C/D/F · R138-R140 的 A-E | 🔴 R125-R129 的 **E 列** `=IF(C{r}=0,0,C{r}/$B$18)` |
| `附注披露信息（国企）` | **35** | 8 | R104-R129 | 对称同型 | 对称同型 |

**两个子区的业务语义**：
- R124 表头「按欠款方归集的期末余额前五名的其他应收款」→ R125-R129 **前五名 5 行** → R130 `合 计` = `=SUM(C125:C129)` / `=SUM(F125:F129)`
- R137 表头「⑧ 应收政府补助情况（逐项披露）」→ R138-R140 **3 行** → R141 `合 计` = `=SUM(C138:C140)`

**算术自检**：`4 列 × 5 行 = 20` + `5 列 × 3 行 = 15` == **35** ✓（两表合 **70**）
**定性**：E 列活着证明**不是整表失效**，而是「源 sheet 被删或改名」导致的**部分断链**；合计行**恒传播 `#REF!`** ⇒ 该两个披露子区的期末余额与坏账准备合计**恒为错**。
**修法**：走**覆盖层**（FC-5 覆盖层例外的新增一条），**不改源模板字节**。
🔴 **判据载荷**：验证时的载荷必须让「只有这两个子区有数」，否则其他区的正确值会掩盖错误 ⇒ 否则假绿。

🔴 **副产物：账龄分层深度不同**（KC-13② 的副产物，本 lane 落地）

| 变体 | 结构 | 内层小计 | 外层小计 |
|---|---|---|---|
| 上市公司 | R9-R11 三分档 + R13-R17 五分档 = **3+5 两层** | R12 `1年以内小计：=SUM(B9:B11)` | R18 `小 计 =SUM(B12:B17)`（**含内层**） |
| 国企 | R7-R12 **六档一层** | 无 | R13 `小 计 =SUM(B7:B12)` |

⇒ **两变体不得共用同一套行映射**；且上市公司表的 R18 外层含内层小计是**正确写法**（内层明细已被吸收，不重不漏）—— 这是 KC-13② 的「扫描误报」白名单在本 lane 的具体落点。

### KA-5 KC-20 落地：K2 的孤儿 per-row 键

`审定表K2-1` 是**一表 9 键组**：

| 键 | 内容（真库现读） |
|---|---|
| `K2-1-rows`（主键，160 B） | `[{"rowId":"r-ls0ldh","label":"坏账准备_其他应收款","source":"tb","accountCode":"1231.03"},{"rowId":"r-5ac9vk","label":"坏账准备_应收账款","source":"tb","accountCode":"1231.02"}]` ⇒ **存行定义不是业务数据** |
| `K2-1-r-ls0ldh-begin` / `-unadj` | `'-732505.4'` / `'-1312178.93'` ⇒ **真金额** |
| `K2-1-r-5ac9vk-begin` / `-unadj` | `'-377709.19'` / `'-406014.85'` ⇒ **真金额** |
| 🔴 `K2-1-r-ryx6og-begin` / `-unadj` | `''` / `''` —— **rowId 不在主键载荷里** |
| 🔴 `K2-1-r-yqfa02-begin` / `-unadj` | `''` / `''` —— **rowId 不在主键载荷里** |

⇒ **8 个 per-row 键里 4 个是孤儿**（行已删、金额键残留）。
**判据**：per-row 键出现的 rowId 集合 SHALL ⊆ 主键载荷 rowId 集合；超出者登记为孤儿并给清理动作。
🔴 **清理动作不得误删有值的 4 个**（`r-ls0ldh` / `r-5ac9vk` 各 2 键）。

### KA-6 KC-21 落地：`审定表K2-1` 纯派生

`r=23 c=16 merged=9`：

| 区 | 内容 |
|---|---|
| R5 / R6 | **两级表头**；🔴 R5 的 J5/L5 含**单元格内换行符** `本期未审数与上期\n未审数的比较` / `本期审定数与上期\n审定数的比较` |
| **R7:R13 数据区（7 行）** | 🔴 **连 A 列项目名都是** `='明细表K2-2'!A11` ~ `A17`；B/C/D/F 同样跨表引（`!B11` / `!F11` / `!G11` / `!E11`）；E/I/J/L 本表派生（`=B7+C7+D7` / `=F7+G7+H7` / `=F7-B7` / `=I7-E7`）；K/M 是裸 IF 变动率 |
| R14 | **空行（预留）** |
| R15 | `合计 =SUM(B7:B14)` **含空行** ⇒ KC-12 连续区间 SUM 族的正常形态，不是缺陷 |
| R16-R22 | 审计说明 / 审计结论 |

⇒ **OO 侧无任何用户输入位**，双向回写的写回方向空转。
**契约标注**：`derived` + `editable_labels: false`。
🔴 **不得选此类表作 canary**（这是 foundation 否决 `K2-1-rows` 的第三条理由）。
🔴 **三边比对须逐格字节**（R5 的换行符与 J 轮 RD-5 第三类同型），禁按行 strip、禁全半角归一。

### KA-7 BP-8 落地：本 lane 24 处位置化 + 下标族叠加

| entry | defect | 说明 |
|---|---|---|
| K5 | **7** | 含 `K5TabDisclosureSoe.vue` 的多处（`row-` / `contingent-` / `lit-` / `dec-` 各一，slice 明文点名） |
| K6 | **7** | `useK6NoteBlocks.ts` 的三处 family_b（`raw.rowKey ?? ...` 形态） |
| K7 | **6** | 含 🔴 `K7TabDisclosureSoe.vue` 的 ``String(raw?.id \|\| `grant-${idx}-${Date.now()}`)`` ⇒ **同时含 ENTROPY 与 FALLBACK，按 KC-6 判别式归 family_b（是缺陷）** |
| K1 | **3** | 含 `k1AdjK11Writeback.ts` / `k1AdjudicationModel.ts` / `k1DisclosureModel.ts` |
| K3 | **1** | `useK3Checks.ts` 一处 family_b |
| **K2 / K4** | **0** | 🔴 **对照组** |
| 合计 | **24** | 与 lane 2 的 21 合计 45 ✓ |

🔴 **双重叠风险**：本 lane 的 **K3/K4/K5/K6/K7 同时是下标族 removeRow 的站点集中区**（KC-7），形态含 `$index` / `idx: number` / `actualIdx` / `tableIndex`。
站点样本（按形态定位不写行号）：`K3TabDetail.vue` / `K4TabDetail.vue` / `K5TabDetail.vue` / `K6TabDetail.vue` / `K7TabDetail.vue` 的 `handleRemoveRow($index)` 与 `removeRow(idx)`；`useK3Detail.ts` / `useK4Detail.ts` / `useK5Detail.ts` / `useK5Warranty.ts` / `useK5Litigation.ts` / `useK5Decommission.ts` / `useK6Detail.ts` / `useK6Impairment.ts` / `useK6GroupImpairment.ts` / `useK7Detail.ts` 的 `removeRow(idx: number)`；`K7TabDetail.vue` 另有 `removeRow(actualIdx)` 与 `handleRemoveRow(tableIndex: number)`。

🔴 **组合判据（两条单独判据都抓不到）**：**删中间一行后，剩余行的身份集合不变**。
- 单看「位置化身份」判据：只发现 id 是下标，但不知道删行会不会触发
- 单看「下标族 removeRow」判据：只发现删行按下标，但不知道身份也是下标
- 两者叠加时，删中间一行会让**其后所有行的身份集体前移一位**，OO↔HTML 合并会把值搬到错误的行上

**处置**：已落库 id **grandfather 不重写**，只保证新增行走值化身份；removeRow 改为按身份删而不是按下标删。

---

## 本 lane 的模板层与真库基线

### definedName（🔴 K 循环全部 65 个断链都在本 lane）

| 册 | definedName | 含 `#REF!` | 断链率 |
|---|---|---|---|
| **K4 其他流动负债** | **43** | **36** | 84% |
| **K2 其他流动资产** | **37** | **29** | 78% |
| K6 持有待售资产和负债 | 1 | 0 | — |
| K1 / K3 / K5 / K7 | 0 | 0 | — |
| **本 lane 合计** | **81** | **65** | 80% |

处置：**登记基线 + 断言不增长，不删**（KC-9）。

### sheet 名字符缺陷（本 lane 占比）

| 类别 | 本 lane | 全 K（KC-10） | 其余归属 |
|---|---|---|---|
| 名中半角空格 | **19**（K1 1 · K2 1 · K4 5 · K5 8 · K6 4） | 21 | K11 的 1 处 + K6 的第 5 处已计入本 lane ⇒ 差 2 归 lane 2（K11 1）与本 lane 内部核对 |
| 括号半/全混不配对 | **3**（K1 · K5 · K6） | 5 | K8 / K9 各 1 ⇒ lane 2 |
| 全半角括号 | **2**（K3 两张） | 2 | — |
| 「表表」重复字 | **1**（K2 `其他流动资产检查表表K2-6`） | 1 | — |

🔴 **算术自检**：括号不配对 **3 + 2 == 5** ✓；全半角 **2 + 0 == 2** ✓；重复字 **1 + 0 == 1** ✓。
🔴 **名中半角空格的分摊须现算**：全 K 21 处 = K1 1 + K2 1 + K11 1 + K4 5 + K5 8 + K6 5 ⇒ 本 lane（K1/K2/K4/K5/K6）= 1+1+5+8+5 = **20**，lane 2（K11）= **1**，20 + 1 == 21 ✓。
**上表「本 lane 19」是按 K6 计 4 的口径**，实施时须现算裁定 K6 是 4 还是 5（`减值准备测试表（后续计量） K6-5` 与 `处置组减值测试表（后续计量） K6-6` 的括号后空格是否计入「名中半角空格」）——🔴 **口径分歧必须先裁定再写死判据**，两种口径下的分摊分别是 19+1+1=21 或 20+1=21，都自洽但明细不同。

另：K7 用 `附注披露信息（国有企业）`（其余 12 册全「国企」）⇒ 本 lane 独有。

### 裸 IF 与 footer（本 lane）

裸 IF 现算 **291** = K1 91 + K2 76 + K6 47 + K7 40 + K3 22 + K5 9 + K4 6。
🔴 最高密度：`审定表K1-1` `r=89 c=13 f=547 bareIF=60`（**全 K 最复杂审定表**）· `实质性程序表 K2A` r=205 · `实质性程序表K3A` r=210 · `实质性程序表 K4A` r=207 · `实质性程序表 K6A` r=207（🔴 **四张 200+ 行的程序表全在本 lane**，其余册程序表都在 20~35 行）。

footer 属 KC-12 三形态；本 lane 含**全部 5 处跳跃式**中的 4 处：`审定表K1-1` 三处 `=SUM(B9,B10)` / `=SUM(B16,B17)` / `=SUM(B23,B24)` · `坏账准备测算K1-8` 的 `=SUM(B16,B26,B37,B45)` · `初始确认检查表K6-4` 的 `=SUM(B25:B26,B29:B30)` ⇒ 🔴 **5 处里 5 处都在本 lane**（K1 4 + K6 1），lane 2 与 foundation 各 0。

### hidden sheet

`GT_Custom` 在本 lane 的 **K1 / K2 / K3 / K7 四册**存在；K4 / K5 / K6 **无**（全 K 是 8 册有：另含 K0 / K10 / K12 / K13）。

### 真库基线（本 lane 54 个非空键）

| entry | 非空键 | 载荷合计 | 主表键 |
|---|---|---|---|
| **K1** | **26** | **290,402 B** | 🔴 `K1-2-detail-rows` **274,741 B / 4 行**（占 95%，全平台最大）· `K1-note-listed-rows` 9,921 · `K1-note-soe-rows` 5,143 · `K1-3-baddebt-rows` 176 |
| **K2** | **11** | 2,375 B | `K2-1-rows` 160 + 6 披露层 + 4 个 per-row 键 |
| K3 | 3 | 1,857 B | **全披露层**（`K3-disc-soe-nature` 886 · `-interest` 691 · `-interest-overdue` 280），无主表键 |
| K5 | 6 | 34 B | 全 1~2 B（`K5-4-policy` 26 · `K5-4-history-rows` 2 · `K5-4-timing-rows` 2 · `K5-4-rows` 2 · `K5-4-warranty-total` 1 · `K5-1-audited-total` 1） |
| K6 | 5 | 139 B | `K6-disclosure-soe-liabilities-rows` 119 + `K6-4-result` 14 + 3 个 2 B |
| K4 | 2 | 764 B | **全披露层**（`K4-disc-soe-nature` 681 · `K4-disc-listed-bonds` 83） |
| K7 | 1 | 2 B | `K7-disclosure-soe-grant-rows` 2 B |
| **合计** | **54** | **295,573 B** | — |

🔴 **K2 披露层是 K 域唯一有真金额的结构化披露载荷**：`K2-disc-listed-main` 823 B（`"endAmount":2500000,"priorAmount":1800000`）· `K2-disc-soe-main` 509 B（`1234567.5`）· `K2-disc-listed-carbon` 611 B（碳排放配额 `"currentAmount":5000,"priorAmount":4000`）· `K2-disc-listed-contract-cost` 89 B · `K2-disc-listed-texts` 88 B · `K2-disc-soe-text` 55 B
⇒ 可作**金额维度 roundtrip 的真实载荷来源**（foundation 的 canary 载荷金额全 0，须另造合成载荷；本 lane 有真金额可直接用）。

🔴 **K1 的行身份三族全在这里真落库**（KC-6 的实证来源）：`K1-2-detail-rows` 的 `K1-2-r-{12位hex}` 安全族 + `seq` 展示序号。

### 本 lane 的 TB 发布门分布（引用 KC-4）

| entry | 载体层 |
|---|---|
| K1 | `useK1FormData.ts` |
| K2 | `K2TabAdjudication.vue` |
| K3 | `useK3FormData.ts` |
| K4 | `useK4FormData.ts` |
| K5 | `useK5FormData.ts` **+** `K5TabAdjudication.vue`（🔴 **2 处**） |
| 🔴 K6 | **宿主 `GtK6HeldForSale.vue`**（全 K 唯一在宿主层） |
| K7 | `K7TabAdjudication.vue` |
| 合计 | **8 处 / 7 条 entry**（K5 占 2） |

与 lane 2 的 6 处（K8/K9/K11 在 `useK{n}Adjudication.ts`、K12/K13 在 `K{n}TabAdjudication.vue`）+ foundation 的 K10 1 处 ⇒ 8 + 6 = 14 ✓ 与 KC-4 的 14 处吻合（K10 的 1 处在 `useK10FormData.ts`，已含在 lane 2 的 6 处之外）。
🔴 **算术须现算裁定**：KC-4 的 14 处 = 本 lane 8 + foundation 1（K10）+ lane 2 5（K8/K9/K11/K12/K13）⇒ 8 + 1 + 5 = **14** ✓。

---

## Property 清单（KA-P1 ~ KA-P38）

| ID | 断言 | 来源 |
|---|---|---|
| KA-P1 | 本 spec 的 7 条 entry_id 用全名列出，与 foundation 的 K10、lane 2 的 5 条**三者无交集且并集 == 13** | 切分 |
| KA-P2 | 7 条的 `capability_target_blocked_by` **全部含 BP-5**，且 K 循环含 BP-5 的 entry 恰好是这 7 条（两侧都验） | KA-2 |
| KA-P3 | 消费边口径三形态 + 路径相等 + 🔴 **排除双引号字符串内的匹配**（`workpaperSyncLegacyBaseline.generated.ts` 的 `"snippet"` 反例） | KA-2 |
| KA-P4 | 7 个 `useK{n}DualMode.ts` 生产边与测试边**各为 0** | KA-2 |
| KA-P5 | 🔴 `components/workpaper/composables/index.ts` 现算 `exists == False` ⇒ 二阶 orphan 恒 0；两侧都验 | KA-2 |
| KA-P6 | 7 个文件行数按 `split("\n")` 口径现算 115/115/115/126/126/125/116 = **838**；`splitlines()` 得 831（**恒少 1**，7 个各少 1） | KA-2 / KC-22② |
| KA-P7 | 7 个 orphan **各调 1 处 `onlyoffice/health`、0 处 `onlyoffice-config`**；🔴 与 lane 2 的 6 个 live（各 1~2 处 config）反向对照 | KA-2 |
| KA-P8 | 删除前后各跑全量测试断言零回归；删除路径与其余七份 slice 不相交 | KA-2 |
| KA-P9 | 7 宿主 `const dualMode = (() => ` **各 1 处** ∧ `import { useK{n}DualMode }` **各 0 处**（两侧都验） | KA-3 |
| KA-P10 | 🔴 前缀撞车 **3 条**（K4/K5/K6 两处同值）∧ 孪生无持久化 **4 条**（K1/K2/K3/K7 宿主 `localStorage` 命中 0），3+4 == 7 | KA-3 |
| KA-P11 | 撞车 3 条改线时**两处同时改**；无持久化 4 条须明确目标态 | KA-3 |
| KA-P12 | 7 宿主各 1 处 `onlyoffice/health` 直调（合 **7**，与 13 composable 的 13 处合计 20 ✓） | KA-3 / KC-3 |
| KA-P13 | 7 宿主其余特征现算：`GtOnlyOfficeSheet` 各 4 · `el-segmented` 剥注释后各 1 · `useChecklistPersistence` 各 3 · `useWorkpaperEntryDualMode` 各 **0** · `v-if` 门控各 1 · `checklist-responses` 各 **0** · notice 两符号各 **0** | KA-3 |
| KA-P14 | 🔴 `apiProxy` 与 `publish-to-tb` **只 K6 宿主各命中 1**（全 K 唯一在宿主层的 TB 发布门） | KA-3 / KC-4 |
| KA-P15 | BP-4 的 5 hop 写路径逐跳可复算，末端 `backend/app/routers/checklist_responses.py` 的 PUT 处理器真实存在 ⇒ `is_client_only == False` | KA-1 |
| KA-P16 | 🔴 显式登记「纯客户端本身不是裁 single_onlyoffice 的理由」，AC 12.8 的唯一判据是「无 HTML 对端」 | KA-1 |
| KA-P17 | 五个传输键**精确字面量**命中现算 9/2/2/8/3 | KA-1 |
| KA-P18 | 🔴 子串口径反证：`K1-9-writeoff` 子串 **12** vs 精确 **9**，差 **3** | KA-1 |
| KA-P19 | 7 个猜键精确命中**各为 0**（非空反向分母） | KA-1 |
| KA-P20 | 🔴 裸 `'K1-9'` 现算 **13 处**，6 文件分布逐条等值；它是 **sheet 码不是 item_id**；slice 的 12 与 11 **两个都错**须如实登记 | KA-1 |
| KA-P21 | `K1 其他应收款.xlsx` 有 sheet `坏账准备转回（收回）、核销检查表K1-9` ∧ 无 adapter/contract 映射 ⇒ `oo_counterpart_status == absent`，🔴 **不是「无 HTML 对端」** | KA-1 |
| KA-P22 | 该 sheet 现算 `r=25 c=8 merged=2` / 公式 6 / **裸 IF 0**；payload ↔ 模板四行映射逐条等值；UUID 列 **9** | KA-1 |
| KA-P23 | 🔴 adapter 显式处理**行数错配**（模板固定 3 行 vs HTML 动态行） | KA-1 |
| KA-P24 | 🔴 两个 `derived_total` 键与模板 footer 一一对应且由 `computed` 产出 ⇒ contract 标 `mode:"input"` 即违规（Property 24 精确落点） | KA-1 |
| KA-P25 | 🔴 K1 两张披露表 `#REF!` 现算**各 35 格 / 8 行 = 70**；算术 20+15==35 | KA-4 / KC-11 |
| KA-P26 | 🔴 E 列 `=IF(C{r}=0,0,C{r}/$B$18)` **活着** ⇒ 定性为**部分断链**非整表失效 | KA-4 |
| KA-P27 | 合计行 `R130`/`R141` 的三个 SUM **恒传播 `#REF!`** | KA-4 |
| KA-P28 | 修法走**覆盖层**不改源模板字节；🔴 判据载荷须「只有这两个子区有数」否则假绿 | KA-4 |
| KA-P29 | 🔴 双变体**账龄分层深度不同**（上市 3+5 两层 / 国企 6 档一层）⇒ 不共用行映射；上市表 R18 外层含内层小计是**正确写法** | KA-4 / KC-13② |
| KA-P30 | 🔴 K2 per-row 键 **8 个中 4 个是孤儿**（`r-ryx6og` / `r-yqfa02`，值全空串，rowId 不在主键载荷里） | KA-5 / KC-20 |
| KA-P31 | 判据：per-row 键 rowId 集合 ⊆ 主键载荷 rowId 集合；🔴 清理**不得误删** `r-ls0ldh` / `r-5ac9vk` 的 4 个有值键 | KA-5 |
| KA-P32 | 🔴 `审定表K2-1` 数据区 R7:R13 **连 A 列都是** `='明细表K2-2'!A{n}` ⇒ 契约标 `derived` + `editable_labels:false`；不得作 canary | KA-6 / KC-21 |
| KA-P33 | 🔴 R5 的 J5/L5 含**单元格内换行符** ⇒ 三边比对逐格字节，禁 strip、禁全半角归一 | KA-6 |
| KA-P34 | R14 空行 + R15 `=SUM(B7:B14)` 含空行 ⇒ 属 KC-12 正常形态**不是缺陷** | KA-6 |
| KA-P35 | 本 lane BP-8 现算 **24 处**（K5 7 · K6 7 · K7 6 · K1 3 · K3 1；**K2/K4 为 0 是对照组**），与 lane 2 的 21 合计 45 ✓ | KA-7 |
| KA-P36 | 🔴 `K7TabDisclosureSoe.vue` 的 ``String(raw?.id \|\| `grant-${idx}-${Date.now()}`)`` 归 **family_b**（按形态定位不写行号） | KA-7 / KC-6 |
| KA-P37 | 🔴 **组合判据**：删中间一行后剩余行身份集合不变（单看位置化或单看下标族都抓不到）；下标族站点集中 K3~K7 | KA-7 / KC-7 |
| KA-P38 | 已落库 id **grandfather 不重写**；removeRow 改按身份删不按下标删 | KA-7 |

### 模板层与真库 Property（KA-P39 ~ KA-P48）

| ID | 断言 |
|---|---|
| KA-P39 | 🔴 本 lane definedName 现算 **81 / 含 `#REF!` 65**（K4 43/36 · K2 37/29 · K6 1/0 · 其余 4 册 0）⇒ **K 循环全部 65 个断链都在本 lane**；登记基线 + 断言不增长，**不删** |
| KA-P40 | sheet 名缺陷分摊算术自洽：括号不配对 **3 + 2（lane 2）== 5** ✓ · 全半角 **2 + 0 == 2** ✓ · 重复字 **1 + 0 == 1** ✓ |
| KA-P41 | 🔴 名中半角空格分摊**须先裁定 K6 计 4 还是 5 的口径**，两种口径下都能凑成全 K 的 21，但明细不同 ⇒ 判据写死前必须裁定 |
| KA-P42 | K7 独有 `附注披露信息（国有企业）`（其余 12 册全「国企」） |
| KA-P43 | 本 lane 裸 IF 现算 **291**（K1 91 · K2 76 · K6 47 · K7 40 · K3 22 · K5 9 · K4 6）；🔴 **四张 200+ 行程序表全在本 lane**（K2A 205 · K3A 210 · K4A 207 · K6A 207） |
| KA-P44 | 🔴 KC-12 的 **5 处跳跃式 footer 全在本 lane**（K1 4 处 + K6 1 处），lane 2 与 foundation 各 0 |
| KA-P45 | `GT_Custom` hidden sheet 在本 lane 的 K1/K2/K3/K7 存在、K4/K5/K6 无 |
| KA-P46 | 本 lane 真库非空键现算 **54**（K1 26 · K2 11 · K5 6 · K6 5 · K3 3 · K4 2 · K7 1），载荷合计 **295,573 B**；🔴 `K1-2-detail-rows` 独占 274,741 B（95%） |
| KA-P47 | 🔴 **K2 披露层是 K 域唯一有真金额的结构化载荷**（6 键，含 2500000 / 1234567.5 / 碳排放配额）⇒ 可作金额维度 roundtrip 的真实载荷来源，**无须合成** |
| KA-P48 | 本 lane TB 发布门 **8 处 / 7 条 entry**（K5 占 2 · 🔴 K6 在宿主层）；与 foundation 1 + lane 2 5 合计 **14** ✓ |

### 边界与空分母 Property（KA-P49 ~ KA-P52）

| ID | 断言 |
|---|---|
| KA-P49 | 🔴 **BP-1 / BP-2 / BP-3 对本 lane 的四件事都不是阻塞**（orphan 删除 / 位置化修复 / 模板层登记 / 孤儿键清理）⇒ 这四件**可立刻实施完**；只有发 contract、注册 adapter、产 evidence 卡它们 |
| KA-P50 | 🔴 **BP-6 不落本 lane**（它指向 K8~K13）；本 lane 的 7 处 `health` 直调分两类：orphan 内的 7 处随删除消失、宿主内联的 7 处须单独改走 bridge materialize |
| KA-P51 | 🔴 本 lane **不产 canary**（首例在 foundation 的 `K10-3-entries`）；本 lane 承接 foundation canary **未覆盖的 BP-5 主线形态** |
| KA-P52 | 本 lane 只**引用** KC-1 ~ KC-24 的编号，**不复述正文**（脚本核验零复述） |
