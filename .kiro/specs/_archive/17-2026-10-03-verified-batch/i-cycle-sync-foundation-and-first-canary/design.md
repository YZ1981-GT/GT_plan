# Design Document

## Overview

本 design 交付三件事：

1. **IC-1 ~ IC-20**：I 循环共同裁决全文（两份 lane spec 只引用不复述）。
2. **FC-1~FC-13 / GC-1~GC-10 / HC-1~HC-16 在 I 的适用性重裁**（逐条给结论，7 条不命中）。
3. **canary I6 的端到端设计**（契约 / representation / provider / 守卫 / roundtrip / TB 发布链）。

🔴 **本 design 的所有事实均来自三轮按值实测**（slice 读取 → openpyxl 逐格 → 前后端+真库 grep）。

🔴 **Property 编号**：本 spec `Property N` = `IF-P{N}`。

---

## 实测与 slice 的关系：零反驳 + 三条超出

🔴 **I slice 是 D/E/F/G/H/I 六份里唯一一份「承重结论零反驳」的**。本轮独立复算范围：

| 复算项 | 范围 | 结果 |
|---|---|---|
| 8 条 CD 的源区间字节 | CD-1/CD-2/CD-3/CD-4/CD-8 共 5 条逐格 openpyxl 真读 | **全部相符** |
| ID-3 消费方计数 | 12 个 composable，用 **import 路径字面量**三形态重算 | **全部相符** |
| ID-1/ID-2/ID-5 宿主命中 | 6 宿主 × 18 个模式 | **全部相符** |
| owner 常量实值 | 6 个 `useI{n}Detail.ts` | **全部相符** |
| BP-6 family_a/b + 位置化标签 | 1 + 4 + 3 处 | **全部相符** |
| manifest 6 条字段 | capability / html_store / adapter_id / independent / parent / mounts | **全部相符** |
| 模板 6 文件 size | 逐文件 | **全部相符** |

🔴 **但实测出 3 条 slice 未登记或不够精确的事实**（见 IC-7），以及 **1 处 slice 快照过期**
（BP-2 记契约目录 5 个文件，现算 **17 个**；但其**实质结论仍成立** —— 逐文件读 `review.entry_id`
无一条以 `xlsx/gt-i` 开头）。

**方法论结论**：slice 质量高不等于可以照抄。①**计数类结论必须现算**（契约目录已从 5 → 17）
②**扫描口径类结论必须复核覆盖面**（slice 的位置化正则漏了 `${added}` 形态）
③**"没说"不等于"没有"**（removeRow 签名两族 / I5 重置换 rowId 都是 slice 未覆盖的维度）。

---

## IC-1 ~ IC-20 共同裁决

### IC-1　manifest capability 的实测口径与迁移路径

**现状（现算 `backend/data/workpaper_sync_entry_manifest.json`）**：6 条 I entry 全部
`capability="single_onlyoffice"` · `html_store="unresolved"` · **`capability_target` 字段不存在（读取返 `None`）** ·
`adapter_id=None` · `independent_entry=True` · `parent_entry_id=None` ·
mounts **I3=4**、其余 5 条 =2。

**裁决**：

1. spec 与守卫**一律用实测值**。slice 的 `capability: null` + `capability_target: "bidirectional"` +
   `migration_state: "legacy_fake_bidirectional"` 是 **slice 自己的裁决值**，不是 manifest 字段值 ——
   引用时须标注来源是 slice 裁决。
2. **BP-9 根因已查清**：manifest 那两个值来自
   `backend/data/workpaper_sync_entry_overlay.json` 的 `defaults_by_component.GtOnlyOfficeSheet`
   （**组件级默认值**，不是逐 entry 裁决）；overlay 的 `by_entry` / `overrides` 里
   🔴 **0 条 I entry**（实测）⇒ 这不是 manifest 抄错，是"默认值被当成裁决值读"。
3. `capability` 从 `single_onlyoffice` → `bidirectional` 的迁移**只能**由
   `WorkpaperSyncAdapterRegistry.register_from_manifest()` 在注册成功后驱动，
   🔴 **禁止手改 manifest 文件**（手改会造出「manifest 说双向、实际无 adapter」的假绿）。
4. 与 **FC-12 / G 的 BP-6 / H 的 HC-1** 同源，本裁决是它们在 I 的具体形态，不重复立项。

**判据**：现算 manifest 后断言 6 条上述七个字段值；变异「把某条手改成 `bidirectional` 而 adapter 仍 None」
SHALL 打红；变异「往 overlay 的 `by_entry` 塞一条 I entry」SHALL 使 BP-9 根因断言打红。

### IC-2　载体族二分（5:1 严重偏斜）+ 两条反向断言

**实测族表（6 条逐条）**：

| entry | 写族 | 写 client | 宿主 `http_import` | 宿主 `checklist_put` | 读族 | 宿主 `force_ct` | 宿主 `checklist_get` |
|---|---|---|---|---|---|---|---|
| I1 | `host_inline` | `http` | 1 | 1 | `host_inline_render_config_refetch` | 1 | **0** |
| I2 | `host_inline` **+第二写路径** | `http` | 1 | 1 | 同 | 1 | **0** |
| I3 | `host_inline` | `http` | 1 | 1 | 同 | 1 | **0** |
| I4 | `host_inline` | `http` | 1 | 1 | 同 | 1 | **0** |
| **I5** | **`formdata_composable`** | `http`（在 composable 里） | 🔴 **0** | 🔴 **0** | **`formdata_composable`** | 🔴 **0** | **0** |
| **I6（canary）** | `host_inline` | `http` | 1 | **2** | 同 | 1 | **0** |

**宿主统一实测**：6 条全部 `bridge=0`（无 `useWorkpaperSyncBridge`/`WorkpaperSyncEditorHost`）·
`ocr=0` · 🔴 `notice=0` + `noticeText=0`（BP-10）· `publishToTb=0`（宿主层）· `adjCentral=0`（宿主层）·
🔴 `localStorage=0`；`legacyOO` 5 条=4、**I3=6**（`mount_count=4` 的对应证据）；
`allResponses` I1 34 / I2 37 / I3 28 / I4 27 / I5 15 / I6 27。
宿主行数：I1 519 / I2 606 / I3 426 / I4 420 / **I5 288（最短）** / I6 418。

**裁决**：

1. 载体定位**禁止按文件名推断**。每条 entry 的载体三元组（写族 / 读族 / TB 门）必须按值实测后写入契约。
2. 🔴 **F 循环守卫「持久化 composable 必须自带 GET+PUT」在 I 对 5 条必然假红**（那 5 条的 PUT 在宿主）。
3. 🔴 **H 循环的三族口径在 I 让 `per_tab` 族分母为空** ⇒ 那部分判据是**空跑重言式**，必须删掉而不是留着。
4. 🔴 **反向断言 ①**：对 I5 断言宿主文件里**没有** http/api 的 import
   （写死「全宿主都有 client import」会让 I5 静默通过）。
5. 🔴 **反向断言 ②**：断言 6 条宿主里 `checklist-responses` 的 **GET 命中数 == 0**
   —— **这个 0 是判据的一部分，不是省略**。照抄 H 的「载体里必须有 checklist GET」会对 6 条全假红。
6. `checklist GET` 实测只出现在 6 个 `useI{n}FormData.ts` 里，其中 **I4/I6 两个生产零消费**（见 IC-3）。
7. `useAdjustmentCentralSync` 实测 **6/6 全覆盖**（`i{1..6}/core/I{n}TabAdjustment.vue` 各 3 处，宿主层 0）
   ⇒ roundtrip 必须把「调整分录中央同步」当作 primary 表之外的**第二写入方**。

**判据**：对 6 条逐条断言族标签 == 实测值；变异「把 I5 的族标签改成 `host_inline`」SHALL 打红。

### IC-3　消费方判定必须用 import 路径字面量（禁符号名 grep）

**实测（全仓 `.ts`/`.vue`，三形态 `from '<mod>'` / `import('<mod>')` / `vi.mock('<mod>')`）**：

| 载体 | import 生产 | import 测试 | 仅提及 | 结论 |
|---|---|---|---|---|
| `useI1FormData` | **5**（`useI1AdditionCheck` / `useI1Adjudication` / `useI1Amortization` / `useI1Detail` / `useI1Impairment`） | 0 | 1 | 最活跃 |
| `useI2FormData` | **4**（宿主 + `useI2Adjudication` + `useI2Impairment` + `i2/core/I2TabAdjudication.vue`） | 1 | 0 | **第二写路径实证** |
| `useI3FormData` | 2（`useI3Detail` / `useI3Impairment`） | 2 | 0 | 在用 |
| **`useI4FormData`**（394 行） | **0** | **0** | 1（`GtI4LongTermPrepaid.vue` 注释） | 🔴 **双零消费 = BP-5①** |
| `useI5FormData` | 1（宿主） | 0 | 0 | 在用 |
| **`useI6FormData`**（448 行） | **0** | **0** | 2（`useI6CrossSheet.ts` + `factories/createChecklistFormData.ts`） | 🔴 **双零消费 = BP-5②** |
| `useI{1..6}DualMode` | **各 1**（各自父宿主） | I1/I6 各 1 | 共 4 处 | 🔴 **I 无孤儿 dual-mode** |

**4 处 mention-only 实测是链式**：`useI3DualMode.ts`→提 `useI1DualMode` · `useI4DualMode.ts`→提 `useI3DualMode` ·
`useI5DualMode.ts`→提 `useI4DualMode` · `useI6DualMode.ts`→提 `useI5DualMode`
（注释形态 `* - Follow useI{n}DualMode pattern`；即 `useI2DualMode`/`useI6DualMode` 未被提及）。

**裁决**：

1. **判消费方一律用 import 路径字面量**，**禁用符号名 grep** ——
   符号名口径会把 4 处注释报成 composable→composable 的消费边。
2. **两侧都断言**：声称零消费的真零、声称有消费方的真有。
3. 对 4 处 mention-only **反向断言它们不是 import 边**（否则判据回到符号名口径）。
4. 两个孤儿都含**完整的 checklist GET/PUT + trial-balance/writeback 管道** ⇒
   「additive 注入即死代码」的**教科书形态 = 假绿第①源**：按「文件名对得上就是载体」改线会接到死代码上，
   宿主行为一点不变而守卫因「文件确实被改了」全绿。
5. 🔴 **I 循环 6 个 dual-mode 无一 wraps 共享基类 `useWorkpaperEntryDualMode`**
   （与 D/M/J 那些 wrapper 不同）⇒ deletion plan 不会与那些 wrapper 撞车。

**判据**：对上表 12 项逐条断言三个计数；变异「用符号名口径重算」SHALL 让 4 处 mention 变成假消费边而打红。

### IC-4　主表键与 owner 常量从常量现读 + I6 legacy alias

**实测**：

| entry | owner 常量 | 值 | 身份字段 | 生产命中 | stringify 位置 |
|---|---|---|---|---|---|
| I1 | `ITEM_ID_ROWS` | `I1-2-rows` | `rowId` | **13** | host |
| I2 | `ITEM_ID_ROWS` | `I2-2-rows` | `rowId` | **11** | composable(`useI2Detail#L523`) |
| I3 | `ITEM_ID_ROWS` | `I3-2-rows` | `rowId` | 7 | host |
| I4 | `ITEM_ID_ROWS` | `I4-2-rows` | `rowId` | **12** | composable(`useI4Detail#L588`) |
| I5 | `ITEM_ID_ROWS` | `I5-2-rows` | `rowId` | 8 | composable(`useI5Detail#L704`) |
| **I6** | **`STORAGE_KEY`** | **`I6-2-detail-rows`** | **`id`** | **10** | host |
| I6 legacy | **`LEGACY_STORAGE_KEY`** | **`I6-2-rows`** | — | 2（`useI6CrossSheet.ts` + `useI6Detail.ts`） | — |

composable 行数：`useI1Detail` 787 / `useI2Detail` 703 / `useI3Detail` 868 / `useI4Detail` 733 /
**`useI5Detail` 898** / `useI6Detail` 868。

**裁决**：

1. 按 owner 常量**现读**，不按命名规律推断 —— 按规律推断会在 I6 上**推错两处**（键名 + 身份字段名）。
2. 🔴 I6 契约 SHALL 声明「**读认两键、写只写主键**」，并断言 `LEGACY_STORAGE_KEY` 常量真存在且值为
   `I6-2-rows`（读兼容不能悄悄消失，否则历史数据读不出）。
3. value 形态按 stringify 位置两族声明（**host 族 I1/I3/I6** · **composable 族 I2/I4/I5**）——
   按「谁 stringify」推断 value_type 会在两族之间推错。

**判据**：6 条逐条断言 `const {CONST} = '{item_id}'` 存在于声明的 `owner_module`；
变异「删掉 `LEGACY_STORAGE_KEY`」SHALL 打红。

### IC-5　分类/行模型三边校验（继承 slice 首创节 `classification_row_model_derivation`）

**为什么需要第三边**：前五个循环的 slice 只把 `source_ref` 写成 `工作簿!sheet!cell`，守卫验的是
「那个 cell 存在 / 那张 sheet 在册」—— 这留了一个洞：**声明的 cell 与实现的常量同时错成一致时判据仍自洽**
（例如把分类常量改成 12 类、同时把 source_ref 指到另一段区间，两边都「对得上」）。
三边 = ①声明 ②**openpyxl 真读的字节** ③impl 常量；断言 ②==③ 且 ① 可解析 ⇒ 同错时第三边把它们一起打红。

**8 条 CD 实测裁定**（本轮已独立复算 5 条源区间字节，与 slice **全部相符**）：

| CD | entry | impl 常量 | 声明 source_ref | verdict | status |
|---|---|---|---|---|---|
| CD-1 | I1 | `I1_DEFAULT_CATEGORIES`（11 类） | `底稿目录!A9:A19` | MATCH | clean |
| **CD-2** | I1 | `I1_SOE_CATEGORIES`（12 类） | `附注披露信息（国有企业）!A9:A19`（11 类） | **MISMATCH** | **defect = BP-7** |
| CD-3 | I5 | `I5_BUILTIN_CATEGORIES`（10 类） | `明细表I5-2!A11:A20` | MATCH | clean |
| **CD-4** | I6 | `I6_DETAIL_DEFAULT_CATEGORIES`（8 条） | `明细表I6-2!A9:A12`（4 类） | **PREFIX_MATCH_WITH_UNSOURCED_TAIL** | **defect = BP-8①** |
| CD-5 | I2 | 无 | — | NO_IMPL_CLASSIFICATION_BY_DESIGN | clean |
| CD-6 | I2 | `defaultPerCapitaPeers` | — | HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF | scanned_and_classified_not_a_defect |
| CD-7 | I3 | 无 | — | SOURCE_ITSELF_DERIVES_FROM_DETAIL | clean |
| **CD-8** | I4 | `CATEGORY_OPTIONS`（6 条） | `明细表I4-2!A11`（1 条） | **PREFIX_MATCH_WITH_UNSOURCED_TAIL** | **defect = BP-8②** |

summary：8 / **clean 4**(CD-1,3,5,7) / **defect 3**(CD-2,4,8) / **classified_not_defect 1**(CD-6)。
🔴 计数按 **status 维度**现算并与 slice summary 等值比对；
`no_impl_classification_by_design` 是 **verdict 维度**的子集（CD-5 一条；CD-7 是第二种 verdict），
**不与三个 status 数相加**。

**我的源字节复算结果（逐格）**：

- **CD-1** `底稿目录!A9:A19` = 土地使用权 / 住房使用权 / 专利权 / 非专利技术 / 商标权 / 著作权 /
  特许经营权 / 软件 / 矿产权 / 数据资源 / 其他（11 格）；`A8`=「无形资产类别设置（以下内容请根据实际情况修改）：」
  是标题、`A20`=`……` 是可扩位 ⇒ **声明区间边界正确**。
- **CD-2** `附注披露信息（国有企业）!A9:A19` = 同 11 类（`A9` 带「其中：」前缀）；`A8`=「一、原价合计」不是分类
  ⇒ **BP-7 成立**：源 **11 类** vs impl **12 类**；源用 `住房使用权`/`特许经营权`/`矿产权`
  而 impl 用 `房屋使用权`/`特许权`/`采矿权`；源**无** `探矿权`；`软件` 在源侧是**第 8 条**而 impl 提到首位。
  `采矿权`/`探矿权`/`房屋使用权` 三词在 `note_template_soe.json` 里命中 **0**（slice 已双向证实）。
- **CD-3** `明细表I5-2!A11:A20` = 预付土地出让金 / 预付工程款 / 预付房屋、设备款 / 无形资产预付款 /
  预付投资款 / 委托贷款 / 合同资产 / 合同取得成本 / 合同履约成本 / 应收退货成本（10 格）；
  `A21`=`……` · `A22`=合计。
- **CD-4** `明细表I6-2!A9:A12` = 人工费 / 材料费 / 制造费用分摊 / 无形资产摊销（4 格）；
  🔴 **`A13:A18` 六格全空** ⇒ **实证「无名可扩位」不是有名分类**，impl 后 4 条
  （`设计费`/`装备调试费`/`委外研发费`/`其他`）**无真源**。
- **CD-8** `明细表I4-2!A11` = `使用权资产改良及维护支出`（唯一有名分类）；
  🔴 **`A9`/`A10` 空 + `A12:A22` 全空** ⇒ impl 第 2~4 条
  （`租入固定资产改良支出`/`固定资产大修理支出`/`开办费`）无真源。

**裁决**：

1. 判据必须三边；**有序等值**比对，**禁用集合比对**（顺序也是行模型的一部分 ——
   BP-7 的缺陷之一正是 `软件` 的位次）。
2. 遵守 slice 冻结的四条 **forbidden_shortcuts**：只断言 sheet 名在 `sheetnames` 里 · 只断言 cell 非空 ·
   集合比对代替有序比对 · 把 impl 常量硬抄进守卫常量（第二真源）。
3. 🔴 **新登记（源模板内部的真源断链 3 处）**：源模板自己把 `底稿目录!A9:A19` 当分类真源
   （`附注披露信息（上市公司）!B10..L10` 逐格是 `=底稿目录!A9`..`A19`），但
   **`K10` 例外是字面 `数据资源`** · 实测 **`明细表I1-2!A29` 也是字面 `数据资源`** ·
   **`明细表I2-2!A17` 是字面 `数据资源`** ⇒ 改 `底稿目录!A18` **不会传播到这三处**。
   本轮**登记不修模板字节**。
4. 稳定 key 与 label 分离：`i1CategoryColumnKey` 生成 `{slot.key}_{slot.seq}`（`i1CategoryScope.ts#L34-36`）
   符合 H7 范式 SK-1；🔴 反向断言全 I 的 `key: X.label` 与 `row[X.label]` 命中 **0**
   （**H8 那族缺陷在 I 不存在**）。

**判据**：8 条逐条三边比对 + status 计数现算等值 + 反向自检（把任一 declaration 的
`expected_source_labels` 改一字，判据必须点名那一条）。

### IC-6　行身份四族分治（HC-7 在 I 的扩展）

**扫描口径（slice 已冻结，本 spec 须扩充）**：`audit-platform/frontend/src/components/workpaper` 下
满足 ①文件名匹配 `^GtI[1-6][A-Z]` ②文件名匹配 `^(use)?[iI][1-6][A-Z]` ③路径含 `/workpaper/i[1-6]/`
任一条的 `.ts`/`.vue`（排除 `__tests__`）共 **235** 个文件；逐行取
`rowId:` / `rowKey:` / `itemId:` / `item_id:` / `id:` **自己的值表达式**再判位置化。

**四族**：

| 族 | 判据 | 实测命中 | 处置 |
|---|---|---|---|
| **A 安全** | `Date.now()` + `Math.random()` 生成串 | `useI1Detail#L307/#L369` · `useI2Detail#L162 generateRowId()=i22-…` · `useI3Detail#L274` · `useI4Detail#L210 i42-…` · `useI5Detail#L211 i52-…` · `useI6Detail#L250/#L303/#L761` · `useI3Disclosure#L521/#L570/#L629/#L690` | 保持 |
| **A′ 纯下标且真落库** | 身份**完全**由数组下标构成、无稳定兜底、经 `_persistSection` 真写库 | **1 处**：`useI3Disclosure.ts#L488 rowId: \`cgu-${i}\`` → 写 `I3-disc-{listed\|soe}-cgu_allocation-rows`，链路 `#L497 _persistSection('cgu_allocation')` → `#L870 _persistSection` → `GtI3Goodwill.vue#L319 http.put` | **必修**（BP-6，归 lane 1） |
| **B 下标兜底** | 主身份是上游稳定 rowId，仅在缺失时回落下标 | **5 处**：`useI3Disclosure#L441 bv-${r.rowId\|\|i}` · `#L463 imp-${r.rowId\|\|i}` · `#L503 perf-${r.rowId\|\|i}` · `i1DisclosureEnhance.ts#L241 tc-i18-${r.rowId\|\|i}` · 🔴 `i3/impairment/I3TabRecoverableTest.vue#L686 String(r.rowId \|\| \`cgu-${idx}\`)` | **必修**（回落分支在「四表 prefill 派生行未保存」「旧数据无 rowId」两情形**会**执行） |
| **D 递增计数（🔴 新增，slice 正则未覆盖）** | `${added}` 批量新增局部计数 | **2 处**：`useI3Disclosure.ts#L665 perf-${Date.now()}-${added}` · `#L725 ap-${Date.now()}-${added}` | 弱于 B 但非零（同毫秒两次批量且 added 从 0 起会撞）⇒ 扫描正则须扩 |
| **C 展示序号（不得点名）** | `seq: idx+1` 等展示用序号，与身份字段同在一个对象字面量里 | **20 处**（含 `i1AdditionCheckModel.ts#L314` · `i1DisclosureSyncPayload.ts#L43` · `useI{1,2,3}Adjustment.ts` 等） | **反向自检：判据必须不点名这 20 处** |

**另有位置化标签 3 处**（与位置化身份是两件事，一并登记）：
`useI3Disclosure.ts#L442` / `#L464` / `#L504` 各 `String(r.investee \|\| \`项目${i + 1}\`)`。

🔴 **entry 维度是 2（I3 + I1）而 site 维度是 8**（族 A′ 1 + 族 B 5 + 族 D 2）
—— 不分开会把「2」误当成「2 处」或把「8」误当成「8 条 entry 都有」。
按 entry 拆：**I3 = 7 处**（`useI3Disclosure` 6 + `I3TabRecoverableTest.vue` 1）· **I1 = 1 处**
（`i1DisclosureEnhance.ts#L241`）。

🔴 **族 B 的第 5 处是本轮复算新并入的**：它在 `.vue` 而非 composable，slice 与本 design 初稿都把它
当「site 维度第 6 处」单列、没并进族 B 计数 ⇒ **守卫若只扫 composable 会整处漏网**。
判据 SHALL 按**形态口径**（`r.rowId || <下标>`）而非文件类型口径扫描。

🔴 **I 循环没有 H2/H4/H8 那种 `seed-{i}` 四表种子形态** —— 这个「没有」也是判据的一部分，
否则后来者会照 H 的口径去找、找不到就当判据通过。

**判据**：族 A′ 命中 1 · 族 B 命中 **5** · 族 D 命中 2（扩充正则后）· 族 C 命中 20 且**不被点名**；
site 合计 8 且**与列举项数逐条相等**；变异「把 `useI6Detail#L250` 算进族 B」SHALL 打红
（它有 `Math.random()`，属族 A）；变异「把扫描限定为 `composables/` 目录」SHALL 因漏掉
`I3TabRecoverableTest.vue#L686` 而打红。

### IC-7　删行语义三件事（三条全部是本轮实测超出 slice 的新事实）

#### ① removeRow 签名两族 3:3（slice 未登记）

| 族 | 成员 | 签名 | 实现 |
|---|---|---|---|
| **按数组下标删** | I1 / I2 / I3 | `useI1Detail.ts#L623 removeRow(rowIndex: number)` · `useI2Detail.ts#L505 removeRow(index: number)` · `useI3Detail.ts#L580 removeRow(rowIndex: number)` | `rows.value.splice(<下标>, 1)` |
| **按 rowId/id 删** | I4 / I5 / I6 | `useI4Detail.ts#L672 removeRow(rowId: string)` · `useI5Detail.ts#L821 removeRow(rowId: string)` · `useI6Detail.ts#L779 removeRow(id: string)` | 先 `findIndex` 再 splice |

**设计含义**：roundtrip 侧「OO 删了第 N 行」在两族要走**不同映射** ——
下标族可以直接传位置，id 族必须先把位置解析成身份；反之若统一按身份实现，下标族的 API 接不上。
🔴 按单一口径实现会在另一族**删错行**。契约 SHALL 声明 `row_delete_api_kind: "index" | "identity"`。

#### ② I5 内置分类行「删除」是原位重置且**会换掉 rowId**（比 slice 更精确）

`useI5Detail.ts#L821-839` 实读：

```
function removeRow(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx < 0) return
  const row = rows.value[idx]
  if (row.isBuiltin) {
    rows.value[idx] = emptyI5DetailRow({          // 🔴 原位重置
      projectName: row.projectName,
      name: row.projectName,
      isBuiltin: true,
      indexRef: row.indexRef || I5_BUILTIN_CATEGORIES.find(c => c.name === row.projectName)?.indexRef || '',
    })
  } else {
    rows.value.splice(idx, 1)                     // 自定义行才真删
  }
  ...
  _persist()
}
```

而 `emptyI5DetailRow` 内部 `#L305 rowId: generateRowId()` ⇒ **重置会生成新 rowId**。
🔴 **slice 只说「原位重置为空行并保留 projectName/indexRef」、未提 rowId 会变。**

**双重影响**：①行数不变（按行数或 `projectName` 比对会认为没变）②**rowId 变了**
（按 rowId 比对会认为「删一行 + 增一行」）。

**裁决**：契约 SHALL 声明**内置行的稳定身份是 `projectName` / `indexRef`**（模板 A11:A20 十行是固定分类、
A21 才是可扩位），**或**要求 `removeRow` 重置时保留原 rowId；两种删除语义必须在契约里区分，
否则 roundtrip 会把「重置的内置行」当成「已删的业务行」。
相关实测：`I5_BUILTIN_CATEGORIES`(#L184) · `#L515` 初始化时全部 `isBuiltin=true` ·
`#L676-686` 按内置顺序排序（用 `i` 作**排序权重非身份** ⇒ 属族 C）· `#L844` `importRows` 排除
`projectName === '合计'`。

#### ③ 真库已有缺身份字段的历史数据（slice 未覆盖）

真库 `I6-2-detail-rows` 那 2 行实测形态：
`[{"category":"智能平台研发","months":[500000,0,…],"aje":0,"rje":0},{...}]`
—— 🔴 **没有 `id` 字段**（也没有 `rowId`）。
而 `useI6Detail.ts#L303 id: raw.id ?? raw.rowId ?? \`row-${Date.now()}-${Math.random()…}\`` 会**每次读都兜底生成新 id**
⇒ roundtrip 每次都会判成「全删全增」。

**裁决**：契约 SHALL 声明二者之一 ——
①「**读时兜底生成的 id 必须持久化回写一次**」（一次性 backfill，之后身份稳定）
②改用**业务键**（`category`）作稳定身份。
判据 SHALL 现算真库确认「有多少行缺身份字段」并在 canary 前置处理，**不得**假设真库数据都有身份。

### IC-8　representation 三件事

1. **嵌套路径**：I5 `gross` / `impairment` 两个子对象各含 15 个字段
   （`unadjOpening`/`unadjIncrease`/`unadjDecrease`/`unadjEnding`/`openingAje`/`openingRje`/
   `ajeIncrease`/`ajeDecrease`/`rjeIncrease`/`rjeDecrease`/`auditedOpening`/`auditedIncrease`/
   `auditedDecrease`/`auditedEnding`/…）· I6 `months` 是 **12 元素数组**（对应模板 B-M 列）
   ⇒ representation 须支持嵌套路径，**同源引用** F5-2 的 `months/0` 族规则（不重新裁决）。
2. **中英双字段名**：`useI6Detail.ts#L516 .filter(r => !r.isTotal && String(r.类别 || r.category || '') !== '合计')` ·
   `#L517 .reduce((s, r) => s + parseNum(r.本期审定 ?? r.auditedAmount), 0)`
   ⇒ 🔴 representation **不得只声明一侧**；须标注**中文键是历史/导入路径形态、英文是当前真库形态**
   （真库那 2 行用的是英文 `category`）。同类候选：`单行` / `按上期审定占比`。
3. 🔴 **payload 列三形态在真库无法验证**：slice 记 `remark_only_conclusion_null` 4 条 +
   I4 `dual_write_remark_and_conclusion_for_status_marker` + I5 `passthrough_remark_and_conclusion`；
   但真库 7 行**全部 remark_only**（`both=0` / `conclusion_only=0`，I5 那行 `concl_max=None`）
   ⇒ **dual_write 与 passthrough 声明未被真库证实**。契约 SHALL 标 `unverified_in_live_db`，
   在 canary 前置实证或降级声明，**不得把 slice 声明当已验证事实**。

### IC-9　per-file 裸 IF 中性化

实测 6/6 全命中：**I1 321** · I4 186 · I2 113 · I3 63 · I5 49 · **I6 45**（总 **777**）。

**裁决**：`StoreMergePlan.oo_crash_neutralization_fn` SHALL **per-file** 挂载，**不得**整册统一
（321 与 45 差 7 倍）。这是 I 循环**唯一复用 pilot 产物**的地方
（复用 `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas`）；其余一律走 `phase5_*` 范式。
🔴 前置核查 SHALL 用 `git show HEAD:` 确认该函数**函数体**在 HEAD
（历史上有「调用点在 HEAD、函数体从未落地、两处 import 跑在 `ImportError` 上」的先例）。

**判据**：对 6 册逐册断言中性化前后裸 IF 计数差 == 该册命中数；变异「整册统一挂」SHALL 打红。

### IC-10　干净点与非干净点**分别**断言（HC-14 在 I 的修正）

| 项 | I 实测 | 守卫方向 | 对照 |
|---|---|---|---|
| 合计漏加小计 | **0 格** | 断言保持为 0 | G5-2 45 格 · G7-2 36 格 |
| `max_column≥200` 宽表 | **0 张** | 断言保持为 0 | G 三张 16384 列 · H 十一张 250~257 列 |
| 同尾码双 sheet | **0 组** | 断言保持为 0 | H 三族 11 组 |
| 整册码回落 | **clean**（31 个 I 码逐个实跑 `find_template_file`/`_any`） | 断言保持 clean | F2 按 sheet 段拆册共享一码 |
| `key: X.label` / `row[X.label]` | **0 命中** | 断言保持为 0 | H8 的 BP-7 |
| 🔴 **definedName** | **不是 0**：I4 **476** · I5 **334** · 其余 4 册 **0** | 🔴 **登记基线值 + 断言不增长** | H 9 册全 0 |

🔴 **裁决**：照抄 H 的「definedName 全 0」在 I 会**直接假红**。必须把这一项从「断言为无」
改成「**登记 per-file 基线值 + 断言不增长**」；同时登记 I4/I5 的 definedName 残留解释了
为什么它们字节（312,532 / 306,241）远大于 sheet 更多的 I3（212,588 / 15 sheets vs 12 / 9 sheets）。

**判据**：前 5 项现算断言为 0/clean；definedName 断言 `{I1:0, I2:0, I3:0, I4:476, I5:334, I6:0}` 且不增长；
变异「给 I1 加一个 definedName」SHALL 打红；变异「把 definedName 判据写成全 0」SHALL 在 I4/I5 上打红。

### IC-11　sheet 命名四陷阱

| # | 陷阱 | 实测 | 后果 |
|---|---|---|---|
| ① | **`审定表I1` 不带 `-1`** | 其余 5 册是 `审定表I{n}-1` | 按 `审定表I{n}-1` 模式定位在 I1 上失配 |
| ② | 尾码后还跟**括号后缀** | `摊销测算表（不含减值）I1-10（剩余年限法）` · `摊销测算表I4-7（工作量法）` | 按 `尾码$` 锚定失配 |
| ③ | **I3 两张参考/数据页** | `参考－商誉减值测试示例`（104r/114f，🔴 **非 hidden**，🔴 **全角连字符 `－`**）· `市场平均收益率2017`（hidden, 167r） | 须进排除清单（同 G 的「-修订前」族）；用 `-` 半角写排除清单会漏 |
| ④ | 附注披露命名两族 | **I1 = `附注披露信息（上市公司）`/`（国有企业）`**（多「信息」二字）· 其余 5 册 = `附注披露（上市公司）`/`（国有企业）` | 统一模式匹配会在 I1 上失配 |

🔴 **命名口径先例**：`prefill_formula_mapping.json` 的 **16 条 I mapping 全部用 sheet 全名**
（含 `审定表I1` 与两张括号后缀 sheet）⇒ 契约照此口径，不另造。

**裁决**：契约 `source_ref.sheet_name` 用**模板 sheet 全名**；排除清单字面量不得 strip / 不得换半角。

### IC-12　wp_index 强不可信（禁依赖）—— HC-15 在 I 的加重

**实测三级问题**：

1. 🔴 **`I2-1` 一码两名两底稿**：`商誉减值测试`(×1) 与 `开发支出审定表`(×3)
   ⇒ 同一 wp_code 在不同 project 指**完全不同的底稿**（H 的 `H1-2` 只是同底稿不同名，本条更严重）。
2. 🔴 **wp_index 子码与模板 sheet 尾码是两套不同编号体系**（大面积不一致，实测举例）：

| wp_code | wp_index 的 wp_name | 模板同尾码 sheet |
|---|---|---|
| `I1-3` | 无形资产摊销测算 | `调整分录汇总I1-3` |
| `I1-4` | 无形资产减值测试 | `无形资产摊销减值政策检查表I1-4` |
| `I1-5` | 无形资产增减变动 | `无形资产增加检查表I1-5` |
| `I2-3` | 开发支出资本化条件检查 | `调整分录汇总I2-3` |
| `I3-3` | 商誉减值测试概要 | `调整分录汇总I3-3` |

3. 🔴 wp_index 有 `I6-7`（研发加计扣除测算）/ `I6-8`（研发费用调整分录）但**模板只到 `I6-6`**。
4. 仅少数一致：`I{n}-2` 明细表 ✓ · `I1-10`/`I1-11` 摊销测算表 ✓。

**裁决**：契约 `sheet_code` **绝对禁止依赖 wp_index**，以**模板 sheet 全名**为唯一真源。
本 spec **不修** wp_index（跨 spec 范围），只立规避判据 + 登记待平台侧修正。
wp_index 多行的根因是 **project_id 维度**（每项目一行），**不是重复缺陷**。

**判据**：契约 schema 校验断言 `source_ref` 不含任何 wp_index 来源字段；
变异「用 wp_index 的 `I2-1` 定位审定表」SHALL 打红（会有两个不同底稿候选）。

### IC-13　footer 四形态 + 多 footer

| entry | footer | 形态 |
|---|---|---|
| I1 | R18 | 纯 SUM（`=SUM(C12:C17)` 等） |
| I2 | R23 | 纯 SUM（`=SUM(B13:B22)` 等） |
| **I3** | R23 | 🔴 **第四形态「合计行套用行公式」**：`I23=SUM(D23:E23)-G23` · `M23=D23+J23` · `N23=E23+K23`；**且左右两区约定不一致** —— 右区 `W23=SUM(W14:W22)` 用纯 SUM |
| I4 | R23 | 纯 SUM |
| **I5** | **R22 / R35 / R48** | 🔴 **三 footer**（原值区 / 减值准备区 / 净值区各一个） |
| **I6（canary）** | **R19 + R20** | 🔴 **双 footer**：R19 合计 + **R20「各月比例」**（同 H10-2，**同源引用** H 的裁决） |

**裁决**：

1. `footer_kind` 枚举 SHALL 扩到四值：`pure_sum` / `enumerated_add` / `derived_unit_price`（H4-2） /
   **`row_formula_applied`**（I3-2 新增）。
2. I3-2 SHALL 额外声明 `footer_convention_split`（左区 `row_formula_applied` / 右区 `pure_sum`）——
   同一 footer 行两种约定，按单一约定校验会有一半假红。
3. I5-2 的 `footer_rows: [22, 35, 48]` 是列表不是单值；I6-2 的 `footer_rows: [19, 20]` 同理。
4. **登记不修**：I6-2 的 R19 把 **B19..Y19 全部写成 `=SUM(x9:x18)`**，其中
   🔴 `S19=SUM(S9:S18)` 对**文本列**（`S=与相关科目勾稽`，模板值「开发支出等」）求和**恒 0**、
   `R19=SUM(R9:R18)` 对占比列求和（语义勉强）。

### IC-14　I3-2 模板真实金额错误 4 格（FC-5 新增例外，走覆盖层不改字节）

**实测**：`明细表I3-2!AA23:AD23` 四格 =
`=SUM(AA27:AA30)` / `=SUM(AB27:AB30)` / `=SUM(AC27:AC30)` / `=SUM(AD27:AD30)`。

- 该行是**合计行**（R23），数据区是 **R14-22** ⇒ 正确区间应是 `AA14:AA22`。
- **R27-29 实为「编制说明」文本区**（`B27`=编制说明：· `B28`/`B29` 是说明文字）、**R30 超出 `max_row`=29**。
- 同行左侧 `S23..Z23` **全部正确** `=SUM(x14:x22)`。
- AA/AB/AC/AD 四列语义 = **减值准备区的审定数四列**（`AA12=期初数` / `AB12=本期增加` /
  `AC12=本期减少` / `AD12=期末数`，`AA11:AD11` 合并为「审定数」）；
  行内公式 `AD14=AA14+AB14-AC14` 正常。
- ⇒ 🔴 **减值准备区审定数四列合计恒 0**；四格错法一致 = **复制粘贴错误**
  （同 G5-2 三段各漏一个小计的模式）。

**裁决**：走**模板覆盖层修，不改 `backend/wp_templates/` 字节**（运行时只读 + sha 冻结）。
同族先例：F2-26!J9 · F5-7!G31 · G5-2 45 格 · G5-1!B35 ⇒ 确立规则
「**模板缺陷走覆盖层，FC-5『以模板为权威』只适用于两边都对、口径不同**」。修复归 lane 1。

**判据**：覆盖层修复前后断言 `AA23` 的求值区间从 `AA27:AA30` 变为 `AA14:AA22`；
🔴 判据载荷必须是「**只有减值准备区有数**」——用「两区都有数」时修复前后差异可能为 0 ⇒ 判据空转假绿
（同 G5-H3 的教训）。

### IC-15　BP-10 在 I 是「从零补」不是「已有待改」（🔴 与 H 相反）

**实测**：6 宿主 `GtEntrySyncCapabilityNotice` 命中 **0** · `workpaperEntrySyncNotice` 命中 **0**。
现状的 `el-tag 仅结构化视图` 只在「OO 健康探测失败」时出现（5 条有、**I2 连这个都没有**），
完全不覆盖 AC 1.4 的「未注册 adapter ⇒ 不得显示可双向回写并显示可操作原因」。

**对照**：H 循环 9 宿主 `notice=3`（已挂）⇒ H 的 BP-10 是「已兑现」。

**裁决**：I 的 AC 1.4 UI 义务要**从零建**。本 spec 在 canary（I6）内建**第一处 notice 挂载**作为范式，
两份 lane 照此复制到其余 5 条。文案真源必须是 `workpaperEntrySyncNotice.ts`，**不得**在宿主里硬编码中文。

### IC-16　I2 UI 门控唯一例外（ID-5）

**实测门控表**：

| entry | toolbar class | 一级门控 | 二级门控 `isOoAvailable` | 兜底 `仅结构化视图` | `el-segmented` 总数 |
|---|---|---|---|---|---|
| I1 | `i1-header-toolbar` | `isHtmlSheet && currentSheet !== 'I1'` | **2** | **1** | 3（🔴 `#L171` 有 Tab 内部分段） |
| **I2** | `i2-header-toolbar` | **`showHtmlToolbar`（computed）** | 🔴 **0** | 🔴 **0** | **4**（最多） |
| I3 | `i3-header-toolbar` | `isHtmlSheet && currentSheet !== 'I3'` | 2 | 1 | 2 |
| I4 | `i4-header-toolbar` | 同型 | 2 | 1 | 3（🔴 `#L142` 有 Tab 内部分段） |
| I5 | `i5-header-toolbar` | 同型 | 2 | 1 | 2 |
| I6 | `i6-header-toolbar` | 同型 | 2 | 1 | 2 |

**裁决**：

1. 🔴 判据 SHALL **按 toolbar class 定位区块**再判二级门控的有无，**不得**全文件 grep `el-segmented`
   （`I1#L171` 与 `I4#L142` 各有一个 Tab 内部分段用的 el-segmented，会被误判成第二个模式切换器）。
2. 🔴 写死「全 slice 都有二级门控」的判据会在 I2 上**静默恒真**（判据找不到二级门控就跳过），
   **恰好漏掉最严重的那一条** —— AC 1.5 要求「不显示不可兑现的切换按钮」，
   而 I2 在 OO 探测失败时切换按钮照样显示。
3. 判据 SHALL 与本表**等值比对**（I2 声明「无」，其余 5 条声明「有」；任一条翻转即红）。
4. 修复归 `i2-i4-i5-carrier-and-structure-exceptions`。

### IC-17　跨引用与键冻结 + 零回归现算

**实测跨引用图**：

| 消费方 | 所属 | 消费的 I 键 |
|---|---|---|
| `expenseWpI1AmortPull.ts` | 费用类底稿 | `I6-2-detail-rows` |
| 🔴 `h1DepAllocCounterpartPull.ts` | **H1 pilot（adapter 已注册、golden 已锁）** | `I6-2-detail-rows` |
| `h8DepAllocCounterpartPull.ts` | H8 | `I6-2-detail-rows` |
| `i1AmortAllocCounterpartPull.ts` | I1 | `I6-2-detail-rows` |
| `useI2Analysis.ts` | I2 | `I6-2-detail-rows` |
| `useI1AdditionCheck.ts` | I1 | `I1-2-rows` **+ `I2-2-rows`** |
| `i{2,3,4,5}ConsistencyModel.ts` | 各自 | 各自主表键（正常） |

**裁决**：

1. 🔴 **冻结 `I6-2-detail-rows` 键名**（5 个消费方中 **4 个不属 I6**，其中一个是**已注册 adapter 的 H1 pilot**）；
   本轮只补契约与 adapter、**不动键名**；每次改动完成后 SHALL 回归 **H1 契约 golden digest**，
   且 **不得修改 H1 的契约 / adapter / golden**。
2. `I2-2-rows` 被 `useI1AdditionCheck.ts` 跨 entry 消费 ⇒ lane 2 改它需与 lane 1 协调。
3. 🔴 **零回归基线一律现算**（GC-10）：契约目录 `*.json` 个数与文件名集合 ·
   `register_from_manifest()` 已注册集合。当前现算：**契约 17 个**
   （`_example.candidate` / b60 / d1 / d2 / d3 / d4 / d5 / d6 / d7 / e1 / f1 / f3 / f4 / f5 / g2 / g7 / h1）·
   已注册 `{d2, d4, g7, h1}`。**不得写死这些个数**（slice 冻结时记 5 个，已过期）。
4. BP-2 的实质断言 SHALL 是「**逐文件读 `review.entry_id`，无一条以 `xlsx/gt-i` 开头**」，
   🔴 **不是数文件个数**。

### IC-18　derived_total_keys 轻量命中 + 禁写死

现算 **13 个**：I1 **8**（`I1-10-period-amort-total` · `I1-11-period-amort-total` ·
`I1-12-supplement-total` · `I1-5-period-total` · `I1-9-alloc-totals`（🔴 **复数**）·
`I1-adj-amort-increase-total` · `I1-adj-cost-increase-total` · `I1-adjudication-cost-addition-total`）·
I2 **2**（`I2-1-audited-total` · `I2-15-supplement-total`）·
I6 **3**（`I6-1-audited-total` · `I6-adj-audited-total` · `I6-adj-expected-total`）·
🔴 **I3 / I4 / I5 各 0**。

**裁决**：与 H 的 **89 个**差一个数量级 ⇒ HC-6 在 I 是**轻量命中**，不构成主要工作量；
但仍须在契约声明 `derived_total_keys`、排除 roundtrip 业务比对、指定重算责任方
（OO 侧改明细后由 adapter 在回写阶段重算）。🔴 判据与**现算基线**比对，**禁写死阈值**。

### IC-19　双区 / 三区派生区声明

| entry | 结构 | 第一区（业务行） | 派生区 |
|---|---|---|---|
| **I1** | 双区 | R12-17（6 行，A 列种子是**占位符** `A`/`B`/`C`/`D`/`…`） | **R19「其中：」+ R20-30**（11 行分类汇总，A 列逐格 `=底稿目录!A9`..`A19`，🔴 **R29 例外是字面 `数据资源`**）；`F20` 用 `SUMPRODUCT(($B$12:$B$17=…)` 按 B 列回汇总第一区 |
| **I4** | 双区 | R11-22（12 行，仅 `A11` 有名 `使用权资产改良及维护支出`） | **R24「其中：」+ R25-28**（4 行，A 列 `=底稿目录!A9`..`A12`） |
| **I5** | **三区** | 原值 R11-21（10 内置分类 + `……`）+ R22 合计 | 减值准备 R24-34（A 列 `=A11`..`=A21` **镜像**）+ R35 合计 · 净值 R37-47（A 列 `=A24`..`=A34` 且数值逐格 `=B11-B24`，🔴 **完全派生**）+ R48 合计 |
| I2 / I3 / I6 | 单区 | — | — |

**裁决**：第二 / 第三区 SHALL 声明为 **derived、不纳入业务行比对**
（否则 roundtrip 会把「第一区改动引起的派生区重算」判成用户编辑了派生区）。
I5 的净值区是**完全派生**（A 列镜像 + 数值逐格相减）⇒ 声明 `fully_derived_region`。

### IC-20　Property 20 的空分母纪律（继承 slice `property_denominators`）

Task 51 正文点名 Property **20 / 28 / 69 / 70**。

**Property 20 的 contract 维度分母为空**（I 循环 **0 契约**）⇒ 🔴 **不宣称通过**那部分。
改在**非空同型分母**上验：8 条 CD 的 stable key / label 来源分离。

守卫真验四件事：
①前提断言 —— 逐文件读 `workpaper_sync_contracts/*.json` 的 `review.entry_id`，
断言无一条属本 slice 6 条 entry（🔴 **不是数文件个数**）
②承载字段级判据的 pilot 守卫文件真存在（`test_task13_contract_registry.py`）
③**非空分母上的同型验证** —— 8 条 declaration 逐条断言「稳定 key 与可变 label 分离」
（I1 的列 key 由 `i1CategoryColumnKey` 生成 `{slot.key}_{slot.seq}`；实测全 I `key: X.label` 与
`row[X.label]` 命中 **0**）
④反向 —— `col_[a-z]+` 形态的无语义占位在 I 的分类常量里命中 **0**。

`not_claimed_passing_part` = 「contract 含 `col_` 占位时 registry 真的拒绝」这条。

---

## FC / GC / HC 在 I 的适用性重裁

### FC 系列（`f1-sync-coverage-and-first-canary/design.md`）

| 裁决 | 在 I 的结论 | 依据 |
|---|---|---|
| FC-1 / FC-2 / FC-4 | 适用 | — |
| **FC-3** | **成立且比 H 更强** | 模板 6 文件 ↔ 6 entry **双射**（H 是 11 文件对 9 entry） |
| **FC-5** | 适用，**新增第 5 个例外** | = IC-14 的 I3-2 四格（前四个：F2-26!J9 / F5-7!G31 / G5-2 45 格 / G5-1!B35） |
| FC-6 / FC-7 / FC-9 / FC-10 | 适用 | — |
| **FC-8** | 🔴 **不适用（零命中）** | 6 宿主 `OcrConfirm\|runOcr` 实测 **0** |
| **FC-11** | 🔴 **不命中** | prefill I 实测 **16 条全 `cells` 型、`items=0`**（同 G） |
| **FC-12** | 适用，具体形态 = **IC-1** | manifest capability，与 G BP-6 / H HC-1 同源 |
| FC-13 | 适用（逐元素取 `capability_target_blocked_by`，不跨 entry 套用） | 6 条阻塞项各异 |

### GC 系列（`g-cycle-sync-foundation-and-first-canary/design.md`）

| 裁决 | 在 I 的结论 | 备注 |
|---|---|---|
| GC-1（representation pointer 按 `entry_id` 不按 wp_code） | **适用** | I 无子入口，但 `I2-1` 一码两底稿（IC-12）使 wp_code 更不可靠 |
| GC-2（`oo_crash_neutralization_fn`） | 适用，具体化为 **IC-9**（per-file） | 唯一复用 pilot 的项 |
| GC-3 | 适用 | — |
| **GC-4**（`TransposedSheetSpec`） | 🔴 **不命中** | I 6 主表全 row-table，无转置 |
| GC-5（payload 多形态） | 适用，但 🔴 **三形态中两条真库未证实** = IC-8③ | — |
| GC-6（键与身份按值取） | 适用，具体化为 **IC-4 + IC-6** | — |
| GC-7 / GC-8 | 不命中（无对应缺陷） | — |
| **GC-9**（TB 发布门缺口） | 🔴 **在 I 反向**：**6/6 全有发布门** | 与 H 的 H8/H9 完全无门相反 ⇒ **canary 可直接覆盖发布链** |
| GC-10（零回归基线现算） | **适用，强制** | 见 IC-17 第 3 条 |
| 16384 列 / UUID 放「有效内容列 +1」 | 适用，**同源引用**（不重复裁决） | I 无 16384 列但**有效列 vs max_column 差值大** |

### HC 系列（`h-cycle-sync-foundation-and-first-canary/design.md`）

| 裁决 | 在 I 的结论 | 映射 |
|---|---|---|
| HC-1 | 适用 | = IC-1 |
| HC-2 | 适用但**族数不同**（I 是 2 族不是 4 族） | = IC-2 |
| HC-3 | 适用且**口径升级**（I 用 import 路径字面量，H 用符号名计数） | = IC-3 |
| HC-4（拼接键解析） | **不命中**（I 无 `${CONST}-suffix` 拼接键，全是字面量常量） | 但 IC-4 仍要求从常量现读 |
| **HC-5**（变体轴三维） | 🔴 **不命中** | 同尾码双 sheet **0 组**；I 的变体用**不同尾码**表达（`…I1-10（剩余年限法）`/`…I1-11` · `摊销测算I4-6`/`摊销测算表I4-7（工作量法）`） |
| HC-6 | 适用但**轻量** | = IC-18（13 个 vs H 的 89 个） |
| HC-7 | 适用且**扩展出族 D** | = IC-6 |
| HC-8 | 适用 | = IC-17 |
| HC-9（猜键回退链） | **不命中**（I 无 `const keys = [...]` 多键回退） | — |
| **HC-10**（localStorage 第三存储） | 🔴 **不命中** | 6 宿主 `localStorage` 实测 **0** |
| HC-11（中文枚举 + 派生字段） | 适用，具体化为 **IC-8②** | I 是中英**双字段名**而非中文枚举值 |
| HC-12 | 适用 | = IC-9 |
| **HC-13**（宽表有效列） | 🔴 **不命中** | `max_column≥200` 的 **0 张**；但 UUID 仍放「有效内容列 +1」 |
| **HC-14** | 适用但**必须修正** | = IC-10（definedName 在 I4/I5 非 0） |
| HC-15 | 适用且**加重** | = IC-12 |
| HC-16 | 适用且**扩到四形态** | = IC-13 |
| H 的 BP-7（label-as-key） | 🔴 **不存在** | `key: X.label` / `row[X.label]` 实测 **0** |

### 跨循环同构规则同源引用

🔴 **I6-2 ↔ H10-2 高度同构**：单级表头 · **12 月度列 B-M** · 年度合计列（I6 `N=SUM(B9:M9)` /
H10 `N=SUM(B8:M8)`）· 合计行 · **第二 footer 标签逐字都叫「各月比例」** ·
占比列引合计行（I6 `R9=IF(Q9=0,0,Q9/$Q$19)` 与 `B20=IF($N$19=0,0,B19/$N$19)`；H10 `=IF($Q$17=0,0,Q8/$Q$17)`）
⇒ **月度矩阵与双 footer 规则同源引用 H 的裁决**，本 spec 不重新裁。
更上游的月度矩阵先例：F5-2 / D4-2。

---

## canary 选型：为什么是 I6

### 三条硬依据

1. 🔴 **真库有非空主表载荷**。现算 `checklist_responses`（载荷列 `remark`）：
   I 前缀只有 **7 个 item_id** 有行（H 是 78），其中 6 条主表键**只有 2 条非空** ——
   `I5-2-rows` **745 B** 与 **`I6-2-detail-rows` 194 B / 2 行**；
   I1/I2/I3/I4 主表键 + `I6-2-rows`(legacy) + I3 披露 cgu 两键**全部零载荷**。
   沿用 G2 / H9 的硬标准「真库有非空载荷」—— 否则 roundtrip 断言只能造数据，等于伪实证。
2. **几何最简**：**单级表头 R8**（全 I 最浅）· 数据区 R9-18（10 行）· **84 公式** ·
   **裸 IF 45（全 I 最少）** · **definedName 0**（I4/I5 有 476/334）· **merged 仅 2**（I1 是 72）。
3. 🔴 **与 H10-2 高度同构** ⇒ 月度矩阵 + 双 footer + 占比列引合计行的规则**可同源引用 H 的裁决**，
   省一整套新裁决；这是 I 循环里唯一能这样省的一条。

### 三条逆风与代价（如实登记）

1. 🔴 **真库那 2 行没有 `id` 字段**（也没有 `rowId`）⇒ `useI6Detail.ts#L303` 兜底每次生成新 id，
   roundtrip 会判成「全删全增」⇒ **canary 必须先解决**（IC-7③：一次性 backfill 或改用业务键）。
2. 🔴 **主表键有 legacy alias**（`I6-2-rows`）且**被 H1 pilot 消费**
   （`h1DepAllocCounterpartPull.ts`，adapter 已注册、golden 已锁）⇒ 键名冻结 + 每次改动回归 H1 golden。
3. **两条专属阻塞**：BP-5②（孤儿 `useI6FormData` 双零消费 ⇒ canary 内立**禁接判据**，
   把「additive 即死代码」在 canary 就立住，是正面价值）+ BP-8①（分类后 4 条无真源 ⇒
   分类只作 `category` 字段值不是行身份，**不阻塞 canary**，后置到 lane 2 的同类处置）。

### 否决 I5 的理由

I5 真库载荷最大（**745 B**）、`blocked_by` 只有 BP-1~4（无专属）、CD-3 分类 MATCH/clean，
但被否决 —— canary 不宜同时吃 5 个最难形态：

1. 🔴 **全 I 最深结构**：三区各带合计（R22/R35/R48）+ A 列区间镜像 + **第三区完全派生**。
2. 🔴 **334 公式最多** + definedName **334**。
3. 🔴 **内置行重置换 rowId**（IC-7②）是全 I 最棘手的身份语义。
4. 🔴 真库那行 `rowId="e2e-i52-contract"` —— **不符 `i52-` 生成器格式，是 E2E 测试种子不是真实业务数据**
   ⇒ 「真库有载荷」这条的成色不如 I6。
5. 载荷含**嵌套** `gross` / `impairment` 各 15 字段。

### 与 H9 canary 的形态对照（说明为什么 I 能覆盖发布链而 H 不能）

| | H9（H canary） | I6（I canary） |
|---|---|---|
| 真库主表载荷 | 819 B / 2 行 | 194 B / 2 行 |
| 表头 | 两级 R7/R8 | **单级 R8** |
| TB 发布门 | 🔴 **无** | ✅ **有**（`useI6Adjudication.ts`×3 + `I6TabAdjudication.vue`×2） |
| 读路径 | render-config（HD-2 第三族，最复杂） | render-config（IC-2 仅两族，其中之一） |
| 发布链覆盖 | ❌ 外移到 lane 3 的 H6 | ✅ **canary 直接覆盖** |

---

## canary I6 端到端设计

### 契约 `i6.research_development_expense_detail.json`

```
entry_id        : xlsx/gt-i6-research-development-expense      # GC-1：按 entry_id 不按 wp_code
provider_id     : phase5_research_development_expense_detail    # phase5_* 范式，不照 pilot_*
source_ref      : { workbook_sha256: 924a1e8348a897c2…,
                    sheet_name: "明细表I6-2" }                  # IC-11/IC-12：模板 sheet 全名，禁 wp_index
primary_table   : { item_id: "I6-2-detail-rows",
                    owner_module: "composables/useI6Detail.ts",
                    owner_constant: "STORAGE_KEY",
                    legacy_alias_constant: "LEGACY_STORAGE_KEY",
                    legacy_alias_value: "I6-2-rows",            # IC-4：读认两键、写只写主键
                    identity_field: "id",
                    identity_backfill_required: true,           # 🔴 IC-7③：真库 2 行缺 id
                    header_rows: [8], data_rows: [9, 18],
                    footer_rows: [19, 20],                      # IC-13：双 footer
                    footer_kinds: { 19: "pure_sum", 20: "ratio_footer" },
                    footer_labels: { 19: "合计", 20: "各月比例" },
                    effective_columns: 26 }                      # max_column 是 65
frozen_key      : true
frozen_reason   : "5 消费方中 4 个不属 I6，含 H1 pilot（adapter 已注册、golden 已锁）"
row_delete_api  : { kind: "identity", signature: "removeRow(id: string)",
                    site: "composables/useI6Detail.ts#L779" }    # IC-7①
monthly_matrix  : { columns: ["B".."M"], annual_total_column: "N",
                    rule_ref: "H10-2 / F5-2 / D4-2 同源引用" }    # IC-13 / 跨循环同构
derived_columns : ["N", "Q", "R", "W"]                           # =SUM(B:M) / =N+O+P / 占比 / =T+U+V
text_columns    : ["S", "Z"]                                     # S=与相关科目勾稽（文本）· Z=备注
known_template_quirks : ["S19=SUM(S9:S18) 对文本列求和恒 0（登记不修）",
                         "R19=SUM(R9:R18) 对占比列求和（语义勉强）"]
representation  : { nested_paths: ["months[0..11]"],              # IC-8①，同源引用 F5-2 months/0
                    field_name_aliases: { "类别": "category",
                                          "本期审定": "auditedAmount" },  # IC-8②
                    payload_column_mode: "remark_only_conclusion_null",
                    payload_column_mode_status: "verified_in_live_db" }  # IC-8③：I6 这条已证实
classification  : { impl_constant: "I6_DETAIL_DEFAULT_CATEGORIES",
                    source_ref: "明细表I6-2!A9:A12",
                    verdict: "PREFIX_MATCH_WITH_UNSOURCED_TAIL",  # CD-4 = BP-8①
                    status: "defect_registered_not_fixed",
                    note: "分类只作 category 字段值、不是行身份 ⇒ 不阻塞 canary" }
forbidden_carriers : ["composables/useI6FormData.ts"]             # 🔴 BP-5②：双零消费死代码，禁接
carrier         : { write: "host_inline", write_client: "http",
                    read: "host_inline_render_config_refetch",
                    force_component_type: "i6-research-development-expense",
                    tb_publish_gate: "composables/useI6Adjudication.ts + i6/core/I6TabAdjudication.vue" }
derived_total_keys : ["I6-1-audited-total", "I6-adj-audited-total", "I6-adj-expected-total"]  # 现算
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # per-file，本册裸 IF 45
uuid_column     : 27          # 有效内容列 26 + 1（IC-10/HC-13 同源规则），不得放 66
variant_axis    : null        # HC-5 在 I 不命中
```

### representation（真库实证驱动）

真库那 2 行实测 = `[{"category":"智能平台研发","months":[500000,0,0,0,0,0,0,0,0,0,0,0],"aje":0,"rje":0}, {…}]`。

按 IC-8 声明三件事：
① `months` 12 元素数组 ⇒ 嵌套路径 `months[0..11]` 映射模板 B-M 列（同源引用 F5-2 `months/0`）
② 中英双字段名（真库用英文 `category`；`useI6Detail.ts#L516/#L517` 有 `r.类别 || r.category` 与
`r.本期审定 ?? r.auditedAmount` 兜底 ⇒ 中文键是**历史/导入路径形态**）
③ `payload_column_mode` = `remark_only_conclusion_null`，🔴 **I6 这条已被真库证实**
（I4 的 `dual_write` 与 I5 的 `passthrough` 才是未证实项，归 lane 2）。

🔴 **身份 backfill 是 canary 的第一道前置**：那 2 行既无 `id` 也无 `rowId`
⇒ 必须先一次性把兜底生成的 id 持久化回写（或改用 `category` 作稳定身份），
否则每次读都换 id、roundtrip 恒判「全删全增」。

### roundtrip 前置断言

1. **IC-7③**：现算真库确认 `I6-2-detail-rows` 里缺身份字段的行数；若 > 0 则先 backfill 再 roundtrip。
2. **IC-2**：`useAdjustmentCentralSync` 被 `i6/core/I6TabAdjustment.vue` 消费（3 处）⇒
   roundtrip 期间**冻结**调整分录中央同步，否则第二写入方会污染比对。
3. **IC-18**：`derived_total_keys`（3 个）排除在业务比对之外。
4. **IC-17**：不改 `I6-2-detail-rows` 键名；roundtrip 完成后回归 **H1 golden digest**。
5. **IC-3**：断言**未**接 `useI6FormData`，且宿主/Tab 侧确实引用了新载体。
6. **IC-13**：R20「各月比例」是 footer 不是业务行 ⇒ 不纳入行比对。

### TB 发布链（canary 直接覆盖）

🔴 **I 循环 6/6 全有发布门**（与 H 的 H8/H9 完全无门相反）⇒ 发布链不需外移首例。

实测 I6 的门：`useI6Adjudication.ts`（`publishToTb` ×3）+ `i6/core/I6TabAdjudication.vue`（×2）。
另有 `components/workpaper/__tests__/i6Integration.spec.ts`（×4）已存在集成测试。

**铁律**（平台级，本 design 只引用）：审定数入 `trial_balance` **只能**走
`POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，必经二次确认；
🔴 **禁止**在 `watch` / `onMounted` / debounce 回调内发布（数据变化只 emit）。

### BP-10 的第一处 notice 挂载（canary 内建范式）

实测 6 宿主 `GtEntrySyncCapabilityNotice` 与 `workpaperEntrySyncNotice` 命中**均为 0**
⇒ canary 内建第一处挂载，作为两份 lane 复制的范式。
文案真源必须是 `workpaperEntrySyncNotice.ts`，**不得**在宿主里硬编码中文。
挂载点 SHALL 在 `i6-header-toolbar` 区块内（与 IC-16 的门控判据同一定位口径）。

---

## Property（IF-P）

| # | Property | 引用 |
|---|---|---|
| IF-P1 | manifest 6 条七字段 == 实测；overlay `by_entry` 里 I entry == 0 | IC-1 |
| IF-P2 | 载体族二分表 6 行 == 实测；I5 宿主无 client import；6 宿主 checklist GET == 0 | IC-2 |
| IF-P3 | 12 个 composable 的 import 计数 == 实测；4 处 mention 不是 import 边 | IC-3 |
| IF-P4 | 6 条 owner 常量实值 == 实测；`LEGACY_STORAGE_KEY` 存在且值为 `I6-2-rows` | IC-4 |
| IF-P5 | 8 条 CD 三边比对通过；status 计数现算等值；5 条源区间字节逐格相符 | IC-5 |
| IF-P6 | 族 A′=1 / **B=5** / D=2 / C=20 且 C 不被点名；site 合计 8；`seed-{i}` 命中 0 | IC-6 |
| IF-P7 | removeRow 两族 3:3 == 实测；I5 内置行重置后 rowId 变（现象被断言）；真库缺身份行数现算 | IC-7 |
| IF-P8 | representation 三件事声明齐；I4/I5 的 payload mode 标 `unverified_in_live_db` | IC-8 |
| IF-P9 | 6 册 per-file 中性化计数 == 321/186/113/63/49/45；整册统一打红 | IC-9 |
| IF-P10 | 5 项断言为 0/clean；definedName 断言基线 `{0,0,0,476,334,0}` 且不增长 | IC-10 |
| IF-P11 | sheet 命名四陷阱逐条；全角连字符与括号后缀不被 strip | IC-11 |
| IF-P12 | 契约 `source_ref` 不依赖 wp_index；`I2-1` 两底稿情形打红 | IC-12 |
| IF-P13 | 6 条 footer 形态标签 == 实测；I3 声明 `footer_convention_split` | IC-13 |
| IF-P14 | I3-2 覆盖层修复前后区间变化；判据载荷是「只有减值准备区有数」 | IC-14 |
| IF-P15 | canary 内 notice 挂载存在且文案来自 `workpaperEntrySyncNotice.ts` | IC-15 |
| IF-P16 | 门控表 6 行 == 实测；按 toolbar class 定位；I2 声明「无二级门控」 | IC-16 |
| IF-P17 | 跨引用图 7 行全在；`I6-2-detail-rows` 键名未改；H1 golden 不变 | IC-17 |
| IF-P18 | `derived_total_keys` 与现算基线一致（当前 13），禁写死 | IC-18 |
| IF-P19 | I1/I4 双区、I5 三区的派生区声明 derived；I5 净值区标 `fully_derived_region` | IC-19 |
| IF-P20 | Property 20 的 contract 维度不宣称通过；在 8 条 CD 上验；`col_[a-z]+` 命中 0 | IC-20 |
| IF-P21 | canary 真库 `I6-2-detail-rows` 非空（现算 ≥ 194 B / 2 行） | canary 依据 1 |
| IF-P22 | canary 直接覆盖 TB 发布链；走显式发布门 + 二次确认；禁 watch/onMounted/debounce 内发布 | GC-9 反向 |
| IF-P23 | 零回归基线现算（契约 17 个 / 注册集 `{d2,d4,g7,h1}`），禁写死 | IC-17 / GC-10 |
