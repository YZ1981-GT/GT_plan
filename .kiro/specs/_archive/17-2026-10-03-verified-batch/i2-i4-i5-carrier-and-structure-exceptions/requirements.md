# Requirements Document

## Introduction

本 spec 是 **I 循环 lane 2**，覆盖 **I2（开发支出）· I4（长期待摊费用）· I5（其他非流动资产）** 三条 entry。

这三条放一起不是因为科目相邻，而是因为**它们每一条都是 I 循环某个维度上的「唯一 / 例外」**：

| entry | 它独有的那一条 | 全 I 循环对照 |
|---|---|---|
| **I2** | 唯一**缺二级 UI 门控**；唯一发布门**不在 composable 而在 `.vue` 自建**；`isOoAvailable` / 「仅结构化视图」双 0 | 其余 5 条都有门控、门都在 composable |
| **I4** | 唯一 `payload_mode = dual_write`；definedName **476**（全 I 最多） | 其余 4 条 `remark_only`；I1/I2/I3/I6 的 definedName 都是 0 |
| **I5** | 唯一 `carrier = formdata_composable`；唯一 `payload_mode = passthrough`；唯一**三数据区**；唯一**内置行「删除」是原位重置且换 rowId**；`http_import` 唯一 0 | 其余 5 条都 `host_inline`；单区或双区 |

🔴 **必须合成一个 lane 才能判断一条特性是「特例」还是「通例」**。
分成三份写，每份都只看见自己那一套，就会把 I5 的 `formdata_composable` 当成通例去推广，
或者把 I2 的缺门控当成「本来就不需要门控」。放一起才有对照组。

**上游（只引用不复述）**：
`i-cycle-sync-foundation-and-first-canary`（**IC-1 ~ IC-20** + canary I6 端到端范式）·
`i1-i3-disclosure-positional-identity-and-classification-source`（lane 1，**跨 lane 键冻结**对账方）·
umbrella Task 51 的 I slice · FC-1~FC-13 · GC-1~GC-10 · HC-1~HC-16。

🔴 **IC-1 ~ IC-20 的正文在地基 spec 裁定，本 spec 一条都不复述**（复述即漂移）。

**不重造已有产物**：
`backend/tests/workpaper_sync/test_task51_i_cycle_migration.py`（149,054 B 守卫）·
`composables/__tests__/iAdjudicationPublishGate.spec.ts` · `useI2Detail.spec.ts` ·
`useI2CrossSheet.spec.ts` · `iCycleDynamicRows.spec.ts` ·
`backend/app/services/four_table/i_cycle_*.py`（5 文件）。

🔴 **不得修改 `backend/wp_templates/` 字节**。
🔴 **不得改 `I2-2-rows` 键名**：lane 1 的 `useI1AdditionCheck.ts#L250-251` 跨 entry 读它。
🔴 **不得修改 H1 pilot 的契约 / adapter / golden digest**（IC-17）。

## 范围：3 条 entry / 42 sheets

| entry_id | 宿主 | 幻影码 | sha256 前 16 / 字节 / sheets | mount | 载体 | payload mode | 主表键 | 身份 | 专属阻塞 |
|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-i2-development-expenditure` | `GtI2DevelopmentExpenditure.vue` | I2D | `a93c298b1f4adfe2` / 138,084 / **21** | 2 | host_inline + **第二写路径** | remark_only | `I2-2-rows` | rowId | 无 BP，但**双例外** |
| `xlsx/gt-i4-long-term-prepaid` | `GtI4LongTermPrepaid.vue` | I4L | `8bfb85884705e471` / **312,532** / 12 | 2 | host_inline | **dual_write** | `I4-2-rows` | rowId | **BP-5** · **BP-8②** |
| `xlsx/gt-i5-other-noncurrent-assets` | `GtI5OtherNoncurrentAssets.vue` | I5O | `7e8ec9c22580e05d` / **306,241** / 9 | 2 | **formdata_composable** | **passthrough** | `I5-2-rows` | rowId | 无 BP，**结构最深** |

🔴 **I5 是本 lane 唯一真库有载荷的 entry**（`I5-2-rows` 745 B），但那条 `rowId` 是
**E2E 种子 `e2e-i52-contract`** ⇒ SHALL 标 `live_payload_is_e2e_seed_not_business_data`，
**不得**据此宣称 `passthrough` 已被业务数据证实。

## Requirement 1：载体三形态并存，判据必须三分而不是二分

**User Story**：作为平台维护者，我要能一眼看出某条 entry 的写路径在哪个文件，
而不是照着另一条 entry 的形态去猜。

### Acceptance Criteria

1. WHEN 声明载体 THEN SHALL 按 IC-2 落三行，且三行**互不相同**：

| entry | write | write_client | read | 第二写路径 |
|---|---|---|---|---|
| I2 | `host_inline` | `http` | `host_inline_render_config_refetch` | 🔴 **有**：`composables/useI2FormData.ts#L185`（500 行文件，`_doSave` 内 `api.put /api/workpapers/{wpId}/checklist-responses`） |
| I4 | `host_inline` | `http` | 同 | 无（`useI4FormData.ts` 是**双零消费死代码**，见 Requirement 4） |
| I5 | 🔴 **`formdata_composable`** | — | 同 | — |

2. 🔴 WHEN 校验 I2 第二写路径 THEN SHALL 断言 `useI2FormData.ts` 的 import 生产消费计数 == **4**
   （现算，禁写死）⇒ 它是**真被消费的活代码**，与 I4/I6 的孤儿 FormData 是**两回事**；
   变异「把 `useI2FormData` 也列入可删名单」SHALL 打红。
3. 🔴 WHEN 校验 I2 双写一致性 THEN SHALL 断言两条写路径**写的是同一个端点与同一套 item 形状**
   （`{item_id, conclusion, remark}`）⇒ 注册 adapter 后二者 SHALL 不产生分叉；
   判据 SHALL 含「经第二写路径保存后，adapter 侧读到同一载荷」。
4. WHEN 校验 I5 载体 THEN SHALL 反向断言 **I5 宿主里无任何 http / api client import**
   （写在 composable 里）；变异「按 F 版守卫要求宿主自带 GET+PUT」SHALL 在 I5 上打红。
5. WHEN 校验三条 entry 的 checklist GET THEN SHALL 断言**均为 0**（IC-2 已裁，本 lane 只实例化）。
6. WHEN 声明 OO 与视图开关 THEN SHALL 落实测值并逐条标出 0 值的含义：

| 项 | I2 | I4 | I5 | 含义 |
|---|---|---|---|---|
| `legacyOO` | 5 | 5 | 5 | 通例 |
| `http_import` | 1 | 1 | 🔴 **0** | I5 无导入入口（结构最深，靠 composable 建行） |
| `isOoAvailable` | 🔴 **0** | 2 | 2 | I2 不做 OO 可用性探测 |
| 「仅结构化视图」 | 🔴 **0** | 1 | 1 | I2 无该开关 |
| mount | 2 | 2 | 2 | 三条都 2（I3 的 4 是 lane 1 的例外） |

7. 🔴 WHEN 三个 0 值出现在判据里 THEN SHALL 按 IC-20 空分母纪律处理：
   断言「现算等于 0 且不是漏扫」，**不宣称该维度通过**。
8. WHEN 声明调整分录中央同步 THEN SHALL 落实测三处并断言 roundtrip 期间冻结：
   `i2/core/I2TabAdjustment.vue#L329`(import)/`#L374`(解构) ·
   `i4/core/I4TabAdjustment.vue#L417`/`#L450` · `i5/core/I5TabAdjustment.vue#L430`/`#L467`。

## Requirement 2：🔴 I2 的两条例外（缺二级门控 + 发布门在 `.vue` 自建）

### Acceptance Criteria

1. WHEN 处置 IC-16 THEN SHALL 断言 I2 是**唯一无二级 UI 门控**的 entry，
   且判据 SHALL **按 toolbar class 定位区块**（防 `I1#L171` / `I4#L142` 那类误判）。
2. 🔴 WHEN 编写门控判据 THEN SHALL 写反向自检：把判据改成「全 slice 都有二级门控」
   SHALL 在 I2 上**从静默恒真变打红** —— 若改了还是恒真，说明判据的分母是空的。
3. 🔴 WHEN 处置 TB 发布门 THEN SHALL 登记本轮现算的第二条例外：

| entry | composable 层 `publishToTb` | `.vue` 层 |
|---|---|---|
| I4 | `useI4Adjudication.ts#L371` 定义 / `#L489` 导出 | `I4TabAdjudication.vue#L510` import / `#L634` 调用 |
| I5 | `useI5Adjudication.ts#L362` 定义 / `#L472` 导出 | `I5TabAdjudication.vue#L548` import / `#L718` 调用 |
| **I2** | 🔴 **0 命中**（`useI2Adjudication.ts` 里完全没有） | 🔴 **自建 4 处**：`I2TabAdjudication.vue#L74` 按钮 / `#L359` 区块注释 / `#L381` 注释 / `#L384` 定义 |

4. 🔴 THEREFORE 「I 循环 6/6 全有发布门」SHALL 说明是 **entry 维度**成立；
   若判据写成「composable 里必须有 `publishToTb`」，**I2 会假红**。
   判据 SHALL 按 **entry 维度**找门：composable 或宿主 Tab 任一处有即算有，并记录 `gate_layer` 字段。
5. WHEN 验证发布铁律 THEN 三条 entry SHALL 一律只走
   `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 必经二次确认，
   且 🔴 **禁**在 `watch` / `onMounted` / debounce 回调内发布；
   SHALL **复用**平台既有 2 道 CI 守卫（`check_tb_writeback_no_direct_call` /
   `check_tb_publish_confirm_gate`）与 `iAdjudicationPublishGate.spec.ts`，**不重造**。
6. 🔴 WHEN I2 的门在 `.vue` 自建 THEN SHALL 评估是否收敛到 composable：
   收敛的收益是判据统一、风险是动 `I2TabAdjudication.vue` 的按钮与二次确认链路 ⇒
   本 lane **先只登记 `gate_layer: "host_tab"` 不收敛**，收敛动作标 `[ ]*`（需 UI 回归实测）。

## Requirement 3：🔴 I4/I5 是 definedName 基线口径的唯一实证场

### Acceptance Criteria

1. WHEN 处置 IC-10 THEN SHALL 落 definedName 现算基线 **I4 = 476 · I5 = 334**
   （另四册 I1/I2/I3/I6 全 0），并断言**不增长**。
2. 🔴 WHEN 编写判据 THEN SHALL 写双变异：
   ① 「给 I1 加一个 definedName」SHALL 打红（基线破坏）
   ② 🔴 「把判据写成 definedName 全 0」SHALL 在 **I4/I5 上打红** ——
   这正是照抄 H 循环 HC-14 口径会踩的坑，本 lane 是全 I 唯一能捕获它的地方。
3. WHEN 声明 definedName 处置 THEN SHALL 明确**不删**这 810 个 definedName（现算 476+334）：
   它们是模板公式的命名引用，删除会让 `max_column` 内的公式整片失效；
   只声明「同步时不新增、不改写」。
4. WHEN 声明裸 IF 中性化 THEN SHALL **per-file** 挂 `oo_crash_neutralization_fn`，
   计数现算（当前 I4 = **186** · I2 = **113** · I5 = **49**；全 I 总 777）；
   变异「整册统一挂」SHALL 打红。
5. WHEN 声明 UUID 落位 THEN SHALL 用「有效列 + 1」规则并逐条落值（见 Requirement 5 几何表），
   🔴 不得放 `max_column` 之后（I2 的 `max_column` 是 61 而有效只 20）。

## Requirement 4：BP-5（I4 孤儿 FormData）· BP-8②（I4 分类无真源）· CD-6（I2 硬编码种子行数）

### Acceptance Criteria

1. 🔴 WHEN 处置 **BP-5 的 I4 侧** THEN SHALL 用 IC-3 的 **import 路径字面量三形态**
   （`from` / `import(` / `vi.mock(`）现算判定 `composables/useI4FormData.ts`（**394 行**）
   的消费方计数 == **0**，两侧都断言；
   🔴 **禁用符号名 grep**（会把注释里的提及算成消费边）。
2. WHEN 确认零消费 THEN SHALL 把 `useI4FormData.ts` 列入契约 `forbidden_carriers`
   （与地基 spec 对 `useI6FormData.ts`（448 行）的处置同型）；
   SHALL **不在本 lane 删文件**，只禁接（删除动作需另起清理 spec，避免与并发会话冲突）。
3. 🔴 WHEN 对照 I2 THEN SHALL 断言 `useI2FormData.ts` 的消费计数 **> 0**（现算 4）⇒
   三个 FormData 里只有 I2 那个是活的；变异「把三个 FormData 一起列入可删」SHALL 打红。
4. WHEN 处置 **BP-8②** THEN SHALL 按 IC-5 三边校验 `CATEGORY_OPTIONS`（I4，**6 条**）
   对 `明细表I4-2!A11`（openpyxl 真读 **1 条**：`使用权资产改良及维护支出`），
   verdict = `PREFIX_MATCH_WITH_UNSOURCED_TAIL`；
   SHALL 登记 `A9`/`A10` 空 + `A12:A22` 全空 ⇒ impl 第 2~4 条
   （`租入固定资产改良支出` / `固定资产大修理支出` / `开办费`）**无真源**。
5. 🔴 WHEN 处置 BP-8② 的**修法** THEN SHALL 标 `[ ]*`（业务确认）：
   这三条是否属于长期待摊费用的合法分类是会计判断，本 lane 只交付判据 + 登记。
6. WHEN 校验 **CD-3（I5，clean）** THEN SHALL 三边比对 `I5_BUILTIN_CATEGORIES`（**10 条**）
   对 `明细表I5-2!A11:A20`（10 格），**有序等值**；
   SHALL 一并登记 `A21` = `……`（可扩位）· `A22` = 合计 ⇒ 声明区间边界正确。
7. WHEN 校验 **CD-6（I2）** THEN SHALL 落 `defaultPerCapitaPeers` 的 verdict
   `HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF` / status `scanned_and_classified_not_a_defect`，
   并 SHALL 说明为什么**不是缺陷**：它是「同业人均数」对照表的默认行数种子，
   模板里本来就没有对应分类区间 ⇒ 无真源是设计而非漏登记。
8. WHEN 校验 **CD-5（I2，clean）** THEN SHALL 落 `NO_IMPL_CLASSIFICATION_BY_DESIGN`；
   🔴 SHALL 说明它与 CD-6 是**同一条 entry 的两个不同 verdict**，
   在 status 维度上 CD-5 计 clean、CD-6 计 classified_not_defect，**两者不相加**（IC-5 已裁）。
9. 🔴 WHEN 登记源模板真源断链 THEN 本 lane SHALL 承接落在 I2 的 1 处：
   `明细表I2-2!A17` 是字面 `数据资源`（不是 `=底稿目录!A18`）⇒ 改 `底稿目录!A18` 不传播；
   另 2 处在 I1 ⇒ 归 lane 1。SHALL 登记不修模板字节。

## Requirement 5：几何三形态 —— 单区 / 双区 / 三区，footer 一到三个

### Acceptance Criteria

1. WHEN 声明几何 THEN SHALL 落三册主表实测值，🔴 三者**结构层级各不相同**：

| 项 | `明细表I2-2` | `明细表I4-2` | `明细表I5-2` |
|---|---|---|---|
| 表头 | **三级 R10-12** | **三级 R8-10** | 🔴 **两级 R8-9** |
| 数据区 | R13-22（1 区） | R11-22（1 区） | 🔴 **3 区**：R11-21 · R24-34 · R37-47 |
| footer | R23 | R23 | 🔴 **3 个**：R22 · R35 · R48 |
| 第二/三区（派生） | 无 | 🔴 **R24-28** | （第三区本身即派生） |
| 有效列 / `max_column` | **20 / 61** | **22 / 25** | **17 / 26** |
| 公式数 | 92 | 98 | 🔴 **334** |
| definedName | 0 | 🔴 **476** | 🔴 **334** |
| 裸 IF | 113 | 186 | 49 |
| UUID 落位 | **21**（= 20+1） | **23**（= 22+1） | **18**（= 17+1） |

2. 🔴 WHEN 声明 I5 三区 THEN SHALL 按 IC-19 逐区声明用途与派生性：
   第 1 区（R11-21）原值 · 第 2 区（R24-34）减值准备 · 第 3 区（R37-47）净值；
   **第 3 区 SHALL 标 `fully_derived_region`**（净值 = 原值 − 减值，逐格由前两区算出）⇒
   回写时 SHALL **整区跳过**，不接受用户输入。
3. 🔴 WHEN 声明 I5 三区行对应 THEN SHALL 断言三区**行数相同（各 11 行）且按行序镜像对应**；
   变异「把某一区的行数改成 10」SHALL 打红（镜像被破坏 ⇒ 净值区算错行）。
4. WHEN 声明 I4 双区 THEN SHALL 按 IC-19 标 R24-28 为派生区。
5. WHEN 声明 footer THEN SHALL 按 IC-13 逐个标 `footer_kind`；
   I5 的 `footer_rows: [22, 35, 48]` 三个 SHALL **分别**标（🔴 不得只声明第一个）。
6. WHEN 声明 sheet 命名 THEN SHALL 按 IC-11 落本 lane 命中的陷阱：
   `摊销测算表I4-7（工作量法）`（括号后缀）⇒ 🔴 禁 strip 括号；
   SHALL 一并登记三册都有 hidden `GT_Custom` ⇒ `excluded_from_sync`。
7. WHEN 声明 `derived_total_keys` THEN SHALL 现算（当前 I2 = **2** · I4 = **0** · I5 = **0**），
   🔴 禁写死；I4/I5 的 0 SHALL 按空分母纪律**不宣称通过**（IC-18 已裁非漏扫）。

## Requirement 6：🔴 I5 内置行「删除」是原位重置且会换掉 rowId

**User Story**：作为审计助理，我清空一个内置分类行的数据后，这一行还应该是同一行，
不能因为清空就跟别处的引用断开。

### Acceptance Criteria

1. WHEN 处置 IC-7② THEN SHALL 逐行现读确认实现形状（`composables/useI5Detail.ts#L821-839`）：

```
removeRow(rowId: string)
  idx = rows.findIndex(r => r.rowId === rowId)
  row = rows[idx]
  if (row.isBuiltin)  rows[idx] = emptyI5DetailRow({ projectName, name, isBuiltin, indexRef })
  else                rows.splice(idx, 1)
  _persist()
```

2. 🔴 WHEN 判定后果 THEN SHALL 断言传入 `emptyI5DetailRow` 的 4 个字段**不含 rowId**，
   而 `emptyI5DetailRow` 内 `#L305 rowId: generateRowId()` ⇒ **重置后 rowId 变了**。
3. 🔴 WHEN 裁定稳定身份 THEN SHALL 声明 I5 内置行的事实主键是 **`projectName`**，
   证据：重置时 `projectName` 与 `name` 都被保留，且 `indexRef` 的兜底正是
   `I5_BUILTIN_CATEGORIES.find(c => c.name === row.projectName)?.indexRef`（`#L830`）
   —— 实现自己就在用 `projectName` 反查 `indexRef`。
4. WHEN 声明契约 THEN SHALL 写 `primary_table.identity_field = "rowId"` +
   `builtin_row_identity_field = "projectName"` + `builtin_row_delete_semantics = "reset_in_place"`；
   🔴 判据 SHALL 断言两个身份字段**都存在**，只声明 `rowId` 一侧 SHALL 打红。
5. 🔴 WHEN 编写判据 THEN SHALL 复现现象：删内置行 → 重读 → `rowId` 变了但 `projectName` 没变；
   并断言**下游引用按 `projectName` 仍能对上**。
6. WHEN 处置修法 THEN SHALL 给两条备选并选一条落地：
   ① 重置时保留原 `rowId`（改 `#L826` 传入 `rowId: row.rowId`）
   ② 契约层承认 `projectName` 为内置行主键
   🔴 本 lane 采 **①+②**（①成本极低且消除隐患，②作为契约层兜底），
   并 SHALL 断言修复后 `rowId` 在重置前后**不变**。
7. WHEN 声明删行两族 THEN SHALL 落本 lane 跨两族的实测：
   I2 **下标族** `composables/useI2Detail.ts#L505 removeRow(index: number)` ·
   I4 **id 族** `composables/useI4Detail.ts#L672 removeRow(rowId: string)` ·
   I5 **id 族** `composables/useI5Detail.ts#L821 removeRow(rowId: string)`
   ⇒ 契约 `row_delete_api_kind` 分别 `index` / `identity` / `identity`。
8. 🔴 WHEN 对照 lane 1 THEN SHALL 登记：lane 1 两条 entry **100% 下标族**、本 lane 是 **1:2 跨两族**
   ⇒ 判据**不得**在两个 lane 之间复用同一个签名断言。

## Requirement 7：payload mode 两条未证实 + I5 真库载荷是 E2E 种子

### Acceptance Criteria

1. 🔴 WHEN 声明 payload mode THEN SHALL 把 I4 的 `dual_write` 与 I5 的 `passthrough`
   都标 `unverified_in_live_db`：真库 I 循环的 payload 列 **7 行全是 `remark_only`**
   （只 `remark` 非空、`conclusion` 为 null）⇒ 这两个 mode 从未被真实数据走过。
2. 🔴 WHEN 处理 I5 真库那条载荷 THEN SHALL 登记三项并标 `live_payload_is_e2e_seed_not_business_data`：
   ① `I5-2-rows` 745 B ② `rowId` == `e2e-i52-contract`（**E2E 种子**）
   ③ 嵌套 `gross` / `impairment` **各 15 字段**
   ⇒ **不得**据此宣称 `passthrough` 已被业务数据证实。
3. WHEN 声明 representation THEN SHALL 按 IC-8 落 I5 的嵌套路径（`gross.*` / `impairment.*` 各 15 字段）
   并说明它对应三区结构的前两区（净值区派生不入载荷）。
4. 🔴 WHEN 编写 roundtrip 判据 THEN SHALL 用**合成载荷**并标 `synthetic_payload`；
   SHALL **不得**把 E2E 种子行当基线（它随 E2E 套件可被重置）。
5. WHEN 声明中英双字段名 THEN SHALL 按 IC-8② 两侧都声明，不得只声明一侧。
6. WHEN `dual_write` 落地 THEN SHALL 断言 `conclusion` 列写入后**不破坏** `remark_only` 读侧
   （I2 的第二写路径与 lane 1 的 `useI1AdditionCheck` 都会读 `conclusion` 兜底）。

## Requirement 8：wp_index 最严重一例落在 I2 + 跨 lane 键冻结

### Acceptance Criteria

1. 🔴 WHEN 处置 IC-12 THEN SHALL 登记全 I 最严重的 wp_index 问题落在本 lane：
   **`I2-1` 一码两名两底稿** —— 真库里 `I2-1` 同时对应 `商誉减值测试`（1 条）
   与 `开发支出审定表`（3 条）；`商誉减值测试` 在业务上属 **I3** 而不是 I2。
2. 🔴 THEREFORE 契约 `source_ref` SHALL **不含任何 wp_index 来源字段**，
   只用 `{workbook_sha256, sheet_name}`；schema 校验层面卡死。
3. WHEN 编写判据 THEN 变异「用 wp_index 的 `I2-1` 反查底稿」SHALL 打红（会取到 I3 的底稿）。
4. WHEN 登记两套编号体系 THEN SHALL 落本 lane 命中的例（`I2-3` 子码与模板尾码不对应）。
5. 🔴 WHEN 冻结键 THEN SHALL 登记 **`I2-2-rows` 被 lane 1 跨 entry 消费**：
   `composables/useI1AdditionCheck.ts#L250-251` 读它（`remark` 优先 / `conclusion` 兜底）⇒
   本 lane **不得改该键名**，也不得在未通知 lane 1 的情况下改 I2 的 payload 列语义。
6. WHEN 登记 I2 内部消费面 THEN SHALL 现算 `I2-2-rows` 的引用点集合（当前 16 处，禁写死），
   含 `i2ConsistencyModel.ts#L213` 的 `'I2-2-': ['I2-2-rows']` 前缀映射 ⇒
   改键名会同时打断一致性检查的前缀表。
7. WHEN 声明跨引用 THEN SHALL 一并登记 `composables/useI2Analysis.ts` 消费 **`I6-2-detail-rows`**
   ⇒ canary 注册后 SHALL 仍取到同一载荷；🔴 断言 **H1 pilot golden digest 不变**。

## Requirement 9：零回归 + 不复述 IC + 证据

### Acceptance Criteria

1. WHEN 实施任一 Task THEN SHALL 先**现算**零回归基线（契约目录 `*.json` 个数与文件名集合 ·
   `register_from_manifest()` 已注册集合 · `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS`），
   🔴 **禁写死个数**（会随 canary 与 lane 1 注册而变）。
2. 🔴 WHEN 引用 IC-1~IC-20 THEN SHALL **只写编号 + 一句话用途**，正文一律不抄；
   交付后 SHALL 脚本核「本 spec 的 `IC-\d+` 引用集合 ⊆ 地基 spec 的 `### IC-\d+` 定义集合」。
3. WHEN 写「N 处」类表述 THEN N SHALL 与同段列举项数**逐条相等**。
4. WHEN 产出证据 THEN SHALL 落 `evidence/` 下逐 Task 一份，含 openpyxl 真读片段与 grep 原文行号；
   SHALL 断言全文无 U+FFFD。
5. WHEN 迁移 THEN SHALL 只走 `register_from_manifest()`，🔴 **禁手改 manifest 文件**（IC-1）。

## 阻塞项

**平台级（全循环共有，只标 `[ ]*` 不承诺）**：
BP-1 instrumentation candidate · BP-2 人工审核 per-entry contract · BP-3 approved authority model +
non-null bundle · BP-4 真 OnlyOffice 9.4 required scenario set。

**本 lane 专属**：

| BP / 事项 | 状态 | 说明 |
|---|---|---|
| **BP-5**（I4 侧） | 本 lane 交付「禁接」 | `useI4FormData.ts`（394 行）零消费 ⇒ `forbidden_carriers`；**不删文件** |
| **BP-8②** 判据 | 本 lane 交付 | `CATEGORY_OPTIONS` 6 条 vs 源 1 条 |
| **BP-8②** 修法 | `[ ]*` 业务确认 | 第 2~4 条是否合法分类属会计判断 |
| I2 发布门收敛到 composable | `[ ]*` UI 回归 | 本 lane 只登记 `gate_layer: "host_tab"` |
| I5 内置行 rowId 保留 | 本 lane 交付 | 采「改 `#L826` 传 `rowId` + 契约声明 `projectName`」双保险 |
| `I2-1` 一码两底稿 | 登记 + 契约规避 | 不改 wp_index 数据（属数据治理另一议题） |
| 源模板真源断链 1 处（I2） | 登记不修 | 不改模板字节 |
| roundtrip 载荷 | `[ ]*` 依赖 BP-4 | 只能合成载荷；E2E 种子不可作基线 |
