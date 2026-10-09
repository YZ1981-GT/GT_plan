# K1~K7 内联 IIFE 宿主与 orphan 清理 — 需求

## 引言

本 spec 覆盖 **K 循环 7 条 entry（K1~K7）**，它们的共同特征是 **BP-5 组**：宿主把 dual-mode **内联成 IIFE**，同时存在一个**一阶 orphan** 的 `useK{n}DualMode.ts`（生产边与测试边各为 0）。这 7 条是 K 循环 BP-5 的**全集**。

**上游**：`k-cycle-sync-foundation-and-first-canary` 的 **KC-1 ~ KC-24**（🔴 **只引用编号，不复述正文**）。
**Property 前缀**：`KA-P`（spec-scoped）。

### 本 spec 的 7 条 entry（全名，无缩写）

| entry_id | wp_code | 宿主 | sheets | 键 | 裸 IF | BP-8 位置化 | 真库非空键 |
|---|---|---|---|---|---|---|---|
| `xlsx/gt-k1-other-receivables` | `K1O` | `GtK1OtherReceivables.vue` | **17** | **142** | 91 | **3** | **26** |
| `xlsx/gt-k2-other-current-assets` | `K2O` | `GtK2OtherCurrentAssets.vue` | 11 | 86 | 76 | **0** | 11 |
| `xlsx/gt-k3-other-payables` | `K3O` | `GtK3OtherPayables.vue` | 12 | 86 | 22 | **1** | 3 |
| `xlsx/gt-k4-other-current-liabilities` | `K4O` | `GtK4OtherCurrentLiabilities.vue` | 8 | 62 | 6 | **0** | 2 |
| `xlsx/gt-k5-provisions` | `K5P` | `GtK5Provisions.vue` | 11 | **119** | 9 | **7** | 6 |
| `xlsx/gt-k6-held-for-sale` | `K6H` | `GtK6HeldForSale.vue` | 11 | **107** | 47 | **7** | 5 |
| `xlsx/gt-k7-deferred-income` | `K7D` | `GtK7DeferredIncome.vue` | 11 | 76 | 40 | **6** | 1 |
| **合计** | — | 7 宿主 | **81** | **678** | **291** | **24** | **54** |

🔴 **对照组**：K2 与 K4 的 BP-8 位置化命中为 **0**（K 循环全域零缺陷 4 条 entry 里有 2 条在本 lane）⇒ 用于判断某形态是特例还是通例。

🔴 **所有计数一律现算，禁写死；判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号。**

---

## Requirement 1：BP-5 —— 7 个一阶 orphan 的两阶可达性判定与删除

**User Story:** 作为迁移实施者，我需要 7 个 orphan dual-mode 的不可达性被两阶验证后再删，这样不会误删仍有消费方的模块。

### 验收准则

1. **WHEN** 判定 orphan **THEN** 消费边 SHALL 只认三种 **statement-position** 形态：`from '<spec>'` / `import('<spec>')` / `vi.mock('<spec>')`，且 `<spec>` 经 `@/` 与相对路径解析后必须**路径相等**于目标模块（不是 stem 相等）。🔴 落在**双引号字符串内**的匹配一律排除（`workpaperSyncLegacyBaseline.generated.ts` 的 JSON `"snippet"` 字段里含完整的 `from '...'` 形态，会骗过路径字面量口径）。
2. **WHEN** 现算 7 个 `useK{n}DualMode.ts`（n=1..7）**THEN** 生产边与测试边 SHALL **各为 0**（一阶 orphan）。
3. 🔴 **WHEN** 判二阶 **THEN** SHALL 断言 `audit-platform/frontend/src/components/workpaper/composables/index.ts` **不存在**（`os.path.exists == False`）⇒ 该目录下模块**没有 barrel 可躲**，K 循环二阶 orphan 恒为 0。两侧都验：7 个一阶边数各为 0 **且** barrel 确实不存在。
4. **WHEN** 现算 7 个文件行数 **THEN** SHALL 用 `len(text.split("\n"))` 口径得 `K1 115 · K2 115 · K3 115 · K4 126 · K5 126 · K6 125 · K7 116`，合计 **838**；🔴 `splitlines()` 口径**恒少 1**（得 831）—— 判据必须声明口径（引用 KC-22②）。
5. **WHEN** 核 legacy 端点 **THEN** 7 个 orphan SHALL **各调 1 处** `/api/workpapers/onlyoffice/health`、**各 0 处** `onlyoffice-config`（与 BP-6 的 6 个 live composable 相反）。
6. **WHEN** 删除 **THEN** SHALL 在删前后各跑一次全量测试并断言零回归；删除路径 SHALL 与其余七份 slice 的删除路径集合不相交。

---

## Requirement 2：KD-2 —— 内联 IIFE 与 orphan 孪生的 localStorage 分裂

**User Story:** 作为实施者，我需要「模式偏好是否持久化」在 K1~K7 内的不一致被显式登记，这样改线时不会留下读写不同键的分裂状态。

### 验收准则

1. **WHEN** 现算 7 个宿主 **THEN** `const dualMode = (() => ` 形态 SHALL **各恰 1 处**，`import { useK{n}DualMode }` SHALL **各 0 处**（两侧都验；K8~K13 反向）。
2. 🔴 **WHEN** 现算宿主内联实现的 localStorage 前缀 **THEN** SHALL 得**两类**：

| 类别 | entry | 宿主内联前缀 | orphan composable 前缀 |
|---|---|---|---|
| **前缀撞车（同值两处声明）** | K4 / K5 / K6（**3 条**） | `k4-` / `k5-` / `k6-dual-mode:` | 同值 |
| **孪生无持久化** | K1 / K2 / K3 / K7（**4 条**） | 🔴 **无**（`localStorage` 命中 0） | 有 |

3 + 4 = 7 ✓。
3. **WHEN** 改线 **THEN** 撞车的 3 条 SHALL **两处同时改**（只改一处会留下读写不同键的分裂状态）；无持久化的 4 条 SHALL 明确「改线后模式偏好是否持久化」的目标态，不得沿用「一边有一边无」。
4. **WHEN** 核 7 宿主直调 legacy 端点 **THEN** SHALL 现算各 **1 处** `/api/workpapers/onlyoffice/health`（合 7，与 13 个 composable 的 13 处合计 20 ✓ 引用 KC-3）。

---

## Requirement 3：BP-4 —— K1-9 writeoff 必须由 adapter 承载

**User Story:** 作为实施者，我需要 K1-9 的 writeoff 能力被判定为「非纯客户端」并走 adapter，这样切模式后录入不会丢。

### 验收准则

1. **WHEN** 判 writeoff 是否纯客户端 **THEN** SHALL 逐跳实证得 **5 hop 完整服务端链路**：`useK1WriteoffCheck.buildSavePayload()` → `K1TabWriteoffCheck.vue` 的 `emit('save', …)` → 宿主 `handleChildSave()` 调 `persistence.save(itemId, toChecklistPatch(value))` → `useChecklistPersistence` 发 `PUT /api/workpapers/{wpId}/checklist-responses` → 后端 `backend/app/routers/checklist_responses.py` 的 PUT 处理器真实存在（非 404）。⇒ `is_client_only == False`，裁决 `must_be_adapter_borne`。
2. 🔴 **WHEN** 论证 **THEN** SHALL 显式登记：即使 writeoff **真是**纯客户端，「纯客户端」本身也**不是**裁 `single_onlyoffice` 的理由 —— AC 12.8 的唯一判据是「无 HTML 对端」。
3. **WHEN** 核五个传输键 **THEN** SHALL 用**精确字面量**口径（整个引号内容 == 目标串，每行至多一次）现算：

| 键 | role | 现算命中 |
|---|---|---|
| `K1-9-writeoff` | `primary_managed_table` | **9** |
| `K1-9-reversal-total` | `derived_total` | **2** |
| `K1-9-writeoff-total` | `derived_total` | **2** |
| `K1-3-baddebt-rows` | `cross_sheet_read` | **8** |
| `K1-11-related-party` | `cross_sheet_read` | **3** |

4. 🔴 **WHEN** 核口径 **THEN** SHALL 反证「子串口径会多算」：`K1-9-writeoff` 的**子串**命中为 **12**（多 3，因为 `'K1-9-writeoff-total'` 被算进去），精确字面量命中为 **9**。
5. **WHEN** 核 7 个「按命名规律该有」的键 **THEN** SHALL 现算精确命中各为 **0**（非空反向分母）：`K1-9-rows` · `K1-9-writeoff-rows` · `K1-9-reversal-rows` · `k1-9-writeoff` · `K1-writeoff` · `K1-9-total` · `K1-9-writeoff-check`。
6. 🔴 **WHEN** 核裸 sheet 码 **THEN** `'K1-9'` 精确字面量 SHALL 现算 **13 处**（分布：`k1SheetProgress.ts` 1 · `useK1ImportExport.ts` 2 · `useK1WriteoffImportExport.ts` 2 · `GtK1OtherReceivables.vue` 1 · `K1TabIndex.vue` 3 · `K1TabWriteoffCheck.vue` 4）。它是 **sheet 码不是 checklist item_id**，不得当「传输键存在」的证据，也不得列进零命中清单。
   🔴 **slice 自相矛盾须如实登记**：slice 的 `guessed_keys_note` 写 **12**、`bare_sheet_code_note` 与 `bare_sheet_code_hits` 写 **11**，**两个都与现算的 13 不符**。
7. **WHEN** 核 OO 对端 **THEN** SHALL 断言 `K1 其他应收款.xlsx` **有** sheet `坏账准备转回（收回）、核销检查表K1-9`（`sheetnames` 命中），但**无任何 adapter / contract 把三个传输键映射到该 sheet 的单元格** ⇒ `oo_counterpart_status = absent`。🔴 这**不是**「无 HTML 对端」。
8. **WHEN** 核该 sheet 几何 **THEN** SHALL 现算 `r=25 c=8 merged=2`（只标题 `A1:H1` / `A2:H2`）、公式 **6** 个、**裸 IF 0**，并按下表建立 payload ↔ 模板的映射：

| payload 字段 | 模板落点 |
|---|---|
| `tables.reversal[]` | 分区（一）R10 标题 → R11 **单级表头 8 列** → **R12:R14 三行全空** |
| `tables.writeoff[]` | 分区（二）R16 标题 → R17 **单级表头 8 列** → **R18:R20 三行全空** |
| `reversalTotal` | R15 `合 计` = `=SUM(E12:E14)`（**只 E 列**） |
| `writeoffTotal` | R21 `合 计` = `=SUM(C18:C20)`（**只 C 列**） |

有效列 8 == `max_column` ⇒ UUID 列为 **9**。
9. 🔴 **WHEN** 设计 adapter **THEN** SHALL 显式处理**行数错配**：模板数据区**固定 3 行**，而 HTML 侧是动态行。
10. 🔴 **WHEN** 报 Property 24 **THEN** 这两个 `derived_total` 键与模板 footer **一一对应**的事实 SHALL 作为非空分母的精确落点（两个键由 `computed` 归约产出，任何 contract 把它们标 `mode: "input"` 即违规）。

---

## Requirement 4：BP-8 —— 本 lane 的 24 处位置化行身份

**User Story:** 作为实施者，我需要本 lane 的 24 处位置化身份按族分治，这样已落库旧 id 不会被无谓重写。

### 验收准则

1. **WHEN** 现算本 lane 的 defect 分布 **THEN** SHALL 得 **24 处**：K1 **3** · K3 **1** · K5 **7** · K6 **7** · K7 **6**（K2 / K4 为 **0**）。引用 KC-6 的判别式，不复述。
2. 🔴 **WHEN** 归族 **THEN** `K7TabDisclosureSoe.vue` 里形如 ``String(raw?.id || `grant-${idx}-${Date.now()}`)`` 的那处 SHALL 归 **family_b（缺陷）**（同时含 ENTROPY 与 FALLBACK，回落分支本身含下标）。定位用**形态**不用行号。
3. **WHEN** 处置已落库 id **THEN** SHALL **grandfather 不重写**，只保证新增行走值化身份。
4. 🔴 **WHEN** 核组合风险 **THEN** SHALL 加组合判据：本 lane 的 **K3/K4/K5/K6/K7 同时是下标族 removeRow 的站点集中区**（引用 KC-7）⇒ 「位置化身份 × 下标删行」双重叠，两条单独判据都抓不到「删中间一行后其后所有行身份集体前移」。组合判据 = **删中间一行后，剩余行的身份集合不变**。

---

## Requirement 5：KC-20 —— K2 的孤儿 per-row 键清理

**User Story:** 作为实施者，我需要孤儿 per-row 键被发现并清理，这样审定表的金额不会挂在已删除的行上。

### 验收准则

1. **WHEN** 核 `审定表K2-1` 的键组 **THEN** SHALL 现算**一表 9 键组**：主键 `K2-1-rows`（存行定义）+ **8 个 per-row 键** `K2-1-r-{6位base36}-{begin|unadj}`（存金额）。
2. 🔴 **WHEN** 比对 rowId 集合 **THEN** SHALL 发现 **4 个孤儿**：`K2-1-r-ryx6og-begin` / `-unadj` 与 `K2-1-r-yqfa02-begin` / `-unadj`（值全为空串），其 rowId **不在 `K2-1-rows` 载荷里**（载荷只含 `r-ls0ldh` 与 `r-5ac9vk`）⇒ **行已删、金额键残留**。
3. **WHEN** 立判据 **THEN** per-row 键出现的 rowId 集合 SHALL 是主键载荷 rowId 集合的**子集**；超出者登记为孤儿并给清理动作。
4. **WHEN** 核有值的 4 个键 **THEN** SHALL 现算真金额：`K2-1-r-ls0ldh-begin='-732505.4'` · `-unadj='-1312178.93'` · `K2-1-r-5ac9vk-begin='-377709.19'` · `-unadj='-406014.85'` ⇒ 清理动作**不得误删这 4 个**。

---

## Requirement 6：KC-21 —— `审定表K2-1` 是纯派生表

**User Story:** 作为契约作者，我需要纯派生表被标注，这样不会给它发「可写回」的契约。

### 验收准则

1. **WHEN** 核 `审定表K2-1` **THEN** SHALL 现算 `r=23 c=16 merged=9`，且**数据区 R7:R13 七行连 A 列项目名都是跨表公式** `='明细表K2-2'!A11` ~ `A17`；B/C/D/F 同样跨表引；E/I/J/L 是本表派生。
2. **WHEN** 发契约 **THEN** SHALL 标 `derived` + `editable_labels: false`；🔴 SHALL 显式登记「OO 侧无任何用户输入位，双向回写的写回方向空转」⇒ **不得选此类表作 canary**。
3. 🔴 **WHEN** 核表头 **THEN** SHALL 发现 R5 的 J5/L5 含**单元格内换行符**：`本期未审数与上期\n未审数的比较` / `本期审定数与上期\n审定数的比较` ⇒ 与 J 轮 RD-5 第三类同型，三边比对须**逐格字节**，禁按行 strip。
4. **WHEN** 核 R14/R15 **THEN** SHALL 登记 R14 是**空行（预留）**、R15 `合计 =SUM(B7:B14)` **含该空行** ⇒ 属 KC-12 连续区间 SUM 族的正常形态，不是缺陷。

---

## Requirement 7：模板层治理（definedName 断链 + K1 的 70 格 `#REF!`）

**User Story:** 作为实施者，我需要本 lane 的模板缺陷有基线和修法，这样改动会被发现。

### 验收准则

1. 🔴 **WHEN** 现算本 lane 的 definedName **THEN** SHALL 得 **81 个 / 含 `#REF!` 65 个**：K4 **43/36**（84%）· K2 **37/29**（78%）· K6 **1/0** · K1/K3/K5/K7 **各 0**。⇒ **K 循环全部 65 个断链都在本 lane**。
2. **WHEN** 处置 **THEN** SHALL **登记基线 + 断言不增长，不删**（删 definedName 有 Excel 公式连带风险）。
3. 🔴 **WHEN** 现算 K1 两张披露表的 `#REF!` **THEN** SHALL 得**各 35 格 / 8 行 = 70 格**（`附注披露信息(上市公司）` R125-R140 · `附注披露信息（国企）` R104-R129）；算术自检 `R125-129 的 4 列 × 5 行 = 20` + `R138-140 的 5 列 × 3 行 = 15` == **35**。
4. **WHEN** 核断链范围 **THEN** SHALL 断言 **E 列 `=IF(C125=0,0,C125/$B$18)` 活着**（指向账龄小计）⇒ 定性为「源 sheet 被删或改名的**部分**断链」而非整表失效。
5. **WHEN** 核传播 **THEN** SHALL 断言合计行 `R130 =SUM(C125:C129)` / `=SUM(F125:F129)` 与 `R141 =SUM(C138:C140)` **恒传播 `#REF!`**。
6. **WHEN** 修 **THEN** SHALL 走**覆盖层**（FC-5 覆盖层例外的新增一条），不改源模板字节。
7. 🔴 **WHEN** 核 K1 双变体披露表结构 **THEN** SHALL 登记**账龄分层深度不同**（上市公司 R9-R11 三分档 + R12 内层小计 + R13-R17 五分档 + R18 外层小计 = **3+5 两层**；国企 R7-R12 **六档一层** + R13 小计）⇒ **两变体不得共用同一套行映射**。
8. **WHEN** 核本 lane sheet 名字符缺陷 **THEN** SHALL 现算：名中半角空格 **19 处**（K1 1 · K2 1 · K4 5 · K5 8 · K6 4）· 括号半/全混不配对 **3 处**（K1 / K5 / K6）· 全半角括号 **2 处**（K3 两张）· 「表表」重复字 **1 处**（K2）；另 K7 用「国有企业」。
   🔴 **注**：KC-10 的全 K 口径是 21 / 5 / 2 / 1；本 lane 占 19 / 3 / 2 / 1，其余（K11 的 1 处名中空格 + K8/K9 的 2 处括号不配对）归 lane 2 —— 19 + 1 + 1 = 21 ✓、3 + 2 = 5 ✓。

---

## Requirement 8：BP-6 / BP-7 在本 lane 的处置

**User Story:** 作为实施者，我需要本 lane 的 legacy 端点与 notice 缺口被收口。

### 验收准则

1. 🔴 **WHEN** 核 BP-6 **THEN** SHALL 登记 **BP-6 不落本 lane**（它指向 K8~K13 的 6 个 live composable）；本 lane 的 7 个 orphan **各只调 1 处 `onlyoffice/health`**、0 处 `onlyoffice-config`，且它们**将被删除**（BP-5）⇒ 端点直调随删除一并消失。
2. **WHEN** 核 7 宿主的内联 IIFE **THEN** SHALL 现算**各 1 处** `onlyoffice/health` 直调；这 7 处**不随 composable 删除消失**，SHALL 单独改走 sync bridge materialize。
3. **WHEN** 处置 BP-7 **THEN** SHALL 在 7 个宿主各挂 notice（按 KC-14 口径选符号）；现算 7 宿主两符号命中**都是 0**。
4. **WHEN** 核 localStorage **THEN** SHALL 按 KC-18 分类：本 lane 的模式偏好类 = 7 个 orphan 前缀（随删除消失）+ 3 宿主内联前缀（K4/K5/K6，须收敛）；🔴 列偏好类 `useK1DetailColumnPrefs.ts` / `useK4DetailColumnPrefs.ts` **不动**。

---

## Requirement 9：本 lane 的空分母与不交付边界

**User Story:** 作为后来者，我需要知道本 lane 哪些能立刻做完、哪些卡外部供给。

### 验收准则

1. 🔴 **WHEN** 核 BP-1 / BP-2 / BP-3 **THEN** SHALL 显式登记「它们对本 lane 的 **orphan 删除、位置化修复、模板层登记、孤儿键清理** 四件事**都不是阻塞**」；只有「发 contract / 注册 adapter / 产 evidence」卡它们。
2. **WHEN** 核真库基线 **THEN** SHALL 现算本 lane 真库非空键 **54 个**（K1 26 · K2 11 · K5 6 · K6 5 · K3 3 · K4 2 · K7 1）；🔴 其中 K1 的 `K1-2-detail-rows` 独占 **274,741 B**（全平台最大，占 K1 载荷 290,402 B 的 95%）。
3. 🔴 **WHEN** 评估 canary 资格 **THEN** SHALL 登记本 lane **不产 canary**（首例在 foundation 的 `K10-3-entries`）；本 lane 承接的是 foundation 的 canary **未覆盖的 BP-5 主线形态**，roundtrip 用本 lane 自己的真库载荷（K1/K2 有真金额）。
4. **WHEN** 核 K2 披露层 **THEN** SHALL 登记它是 **K 域唯一有真金额的结构化披露载荷**：`K2-disc-listed-main` 823 B（含 `"endAmount":2500000,"priorAmount":1800000`）· `K2-disc-soe-main` 509 B（含 `1234567.5`）· `K2-disc-listed-carbon` 611 B（碳排放配额）⇒ 可作金额维度 roundtrip 的真实载荷来源。
5. **WHEN** 核 K5 载体 **THEN** SHALL 引用 KC-2 断言 K5 走 `shared_platform_persistence_adapter` 族（`useK5FormData.ts` 裸端点 0 / `useChecklistPersistence` 3），**不判为缺陷**。
