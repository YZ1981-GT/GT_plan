# K 循环双向回写地基与首张 canary — 设计

## 上游与边界

| 项 | 内容 |
|---|---|
| slice | `backend/data/workpaper_sync_k_cycle_manifest_slice.json`（221,580 B，Task 53，冻结 2026-08-31） |
| 守卫 | `backend/tests/workpaper_sync/test_task53_k_cycle_migration.py` |
| 变异脚本（**复用不新写**） | `backend/scripts/diagnose/mutate_k_cycle_guards.py` · `mutate_task53_k_cycle_migration_guards.py` |
| 实景核验（**复用不新写**） | `backend/scripts/diagnose/verify_k_cycle_live.py` |
| 删除计划 | `backend/data/workpaper_sync_k_cycle_deletion_plan.json`（79,713 B） |
| 校验规则 | `backend/data/k_cycle_validation_rules.json`（5,391 B） |
| 本 spec entry | `xlsx/gt-k10-other-income`（**1 条**） |
| 承接 | FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20 |

**后端已有产物（一律不重造）**：42 个 `_k*.py` render 策略（13 主 + 3 K0 + 26 辅助）· `backend/data/wp_guidance/K0.json`~`K13.json` **14 个全有**（与 J 缺 `J2.json` 不同）· `four_table/{k1_aux_detail,k1_detail_seed,k_cycle_specs}.py` · `k_cycle_ie_manifest.yaml` · 🔴 **render schema 在 `backend/data/ledger_adapters/wp_render_schema/` 的 `K0.yaml`~`K13.yaml` 14 份**（不在 `backend/app/data/wp_render_schema/`，那里只有 3 个 J 的）

---

## K 与前七轮的形态差异总表（KD-1 ~ KD-7 由 slice 提出，本节给现算复核结论）

| ID | slice 结论 | 现算复核 |
|---|---|---|
| KD-1 | 7 个**一阶** orphan dual-mode（K1~K7），八轮新高；二阶恒 0 | ✅ 确证。`components/workpaper/composables/index.ts` 现算 `exists == False` ⇒ 无 barrel 可躲 |
| KD-2 | K1~K7 宿主**内联 IIFE**，composable 与内联实现同时存在且都完整 | ✅ 确证。IIFE 命中 K1~K7 各 1（合 **7**）/ `import useK{n}DualMode` 命中 K8~K13 各 1（合 **6**），两集合互斥；K4/K5/K6 宿主内联有 `k{n}-dual-mode:` 前缀**撞车 3**、K1/K2/K3/K7 内联**无持久化 4**（3+4=7 ✓） |
| KD-3 | K 对共享基类贡献 **0** 边 ⇒ 29 保持 29 | ✅ 确证。窄口径 **29** / 宽口径 **33**（不含基类自身）/ 差集 **4** = `useK9DualMode.ts` + `GtG2InterestReceivable.vue` + `GtN2TaxesPayable.vue` + `workpaperSyncLegacyBaseline.generated.ts`；窄口径里 K 路径条数 **0** |
| KD-4 | 14 册 vs 13 entry **单射不满射**，多出 `K0 管理循环函证.xlsx` | ✅ 确证。🔴 `K0` 两个解析函数**都返真实文件**（J0 都返 None）⇒ 判据不得照抄 J |
| KD-5 | parent_duplicate **0** ⇒ 不写该条件节 | ✅ 确证（写空节 = additive 死声明） |
| KD-6 | 两种 `el-segmented` 门控并存：11 宿主 `v-if`、K8/K9 用 `disabled` | ✅ 确证。`v-if gate` 宿主层命中 **11**（K1~K7 + K10~K13），K8/K9 为 **0**；🔴 `disabled: !isOoAvailable` 在 **composable**（`useK8DualMode.ts#L48` / `useK9DualMode.ts#L47`），宿主层命中 **0** |
| KD-7 | 11 宿主第二处 `el-segmented` 在**块注释里** | ✅ 确证。剥注释后 13/13 恒 **1** 处 |

🔴 **slice 未声明、本轮自行现算并纳入 KC 的三项**：definedName 断链（KC-9）· K1 双变体披露表 70 格 `#REF!`（KC-11）· 键全集 1065 与 derived_total 83（KC-5 / KC-16）。

---

## KC-1 ~ KC-24 共同裁决

> 🔴 这 24 条**只在本文件裁一次**。`k1-k7-inlined-iife-hosts-and-orphan-cleanup` 与
> `k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub` 两份 lane spec **只引用编号，不复述正文**。

### KC-1 manifest 口径与 BP-9 分歧必须显式登记

manifest 里 K 前缀 13 条 entry 现算：`capability` 全 `single_onlyoffice` · `html_store` 全 `unresolved` · `adapter_id` 全 `null` · **0 条有 `capability_target` 字段**。这三个值**不是裁决**，是 `workpaper_sync_entry_overlay.json` 的 `defaults_by_component.GtOnlyOfficeSheet` 默认值机械展开的结果。

本 slice 现算 `bidirectional` 条数 = **0**、`capability_verdict_pending` = **13**。

**判据**：守卫 SHALL 断言 manifest 与 slice 在这两个字段上**不相等**，且该分歧已登记为 BP-9。断言相等就是把 overlay 默认值当裁决（AP-3 明禁）。

### KC-2 载体族在 K 内部两种并存（IC-2 / JC-2 在 K 的扩展）

| 载体族 | entry | 现算证据 |
|---|---|---|
| `formdata_composable_bare_endpoint` | K1/K2/K3/K4/K6/K7/K8/K9/K10/K11/K12/K13（**12 条**） | `useK{n}FormData.ts` 各 **2 处** `checklist-responses` 端点字面量 |
| 🔴 `shared_platform_persistence_adapter` | **K5（1 条）** | `useK5FormData.ts` 的 `checklist-responses` = **0**、`useChecklistPersistence` = **3**（#L23×2 / #L67）⇒ 端点在适配器内部 |

补充现算：`useK11Detail.ts` 另有 1 处 · K1 三个 Tab 各 1 处（`K1TabAdjudication.vue` / `K1TabPolicyCheck.vue` / `K1TabWriteoffCheck.vue`）⇒ 合计 **16 文件**（已排除 `GtKamWorkpaper.vue`）。
13 宿主的 `checklist-responses` 现算全 **0**（都在 composable 层），`useChecklistPersistence` 各 **3** 处（13×3 = 39）。
K5 的 **10 个 Tab 全部只 `emit('save')`**（Decommission 8 / Adjustment 7 / Adjudication 6 / Litigation 5 / DisclosureSoe 5 / Warranty 4 / Detail 4 / DisclosureListed 4 / ProvisionCheck 2），由宿主 `GtK5Provisions.vue` 收口。

🔴 **判据必须二分支**。按 H 的「载体有 `http.put`」或按「每条 entry 都得有 `checklist-responses` 裸端点」去核，**K5 必假红**；K5 不是缺陷。

### KC-3 写路径与发布门按端点字面量判定，且必须认反引号（JC-3 在 K 的加强）

扫描正则 SHALL 同时认单引号、双引号、**反引号**。slice 的 `endpoint_scan_recipe` 明文记录：首轮只认单/双引号，把 6 个 `` `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config` `` 直调**漏登记成 0**，守卫现算时打红才发现。

K 域端点现算 **30 种**（`${...}` 归一为 `{X}` 后），Top 7 见 requirements Req 3.2。
`onlyoffice/health` 的 **20** 文件 = 13 个 `useK{n}DualMode.ts` + 7 个宿主内联 IIFE ✓ 与 slice 的 13 / 7 双向吻合。
`onlyoffice-config` 现算 **6 文件 / 9 处**（K8:2 K9:2 K10:1 K11:2 K12:1 K13:1）⇒ slice 的 6 是**文件数不是处数**。

另两处须登记的端点异常：
- 🔴 `GET /api/projects/{X}/ledger/entries/1221?year={X}` —— **科目码 1221 硬编码在 URL 里**
- `GET /api/workpapers/{X}/render-config?force_component_type=k1-other-receivables` —— K1 用 `force_component_type` 强制组件类型

### KC-4 TB 发布门 13/13 全有，但载体分布在四层

| 载体层 | entry | 处数 |
|---|---|---|
| `useK{n}FormData.ts` | K1 / K3 / K4 / K5 / K10 | 5 |
| `useK{n}Adjudication.ts` | K8 / K9 / K11 | 3 |
| `K{n}TabAdjudication.vue` | K2 / K5 / K7 / K12 / K13 | 5 |
| 🔴 **宿主 `GtK6HeldForSale.vue`** | K6 | **1** |

合计 **14 处 / 13 条 entry 全覆盖**（K5 占 2 处：`useK5FormData.ts#L216` + `K5TabAdjudication.vue`）。
🔴 判据按单一层写必漏；按符号名 `publishToTb` 判也会漏（J 轮已证该符号名可以全域 0 命中而端点命中）。

### KC-5 三个命名空间必须分清（JC-5 在 K 的扩展）

| 命名空间 | 形态 | 现算 | 是否 managed table 键 |
|---|---|---|---|
| 业务持久化键 | `K{n}-{sheet}-{field}` 完整字面量 | **1065 个** | ✅ 是 |
| 🔴 复核会话键 | `K{n}-review-session-{14位时间戳}` | **9 个**（真库各 261~262 B；K10 占 6 · K12 1 · K1 1 · 另 1） | ❌ **不是**，须显式排除 |
| 🔴 per-row 拆键 | `K{n}-1-r-{6位base36}-{begin\|unadj}` | K2 实测 8 个（4 有值 4 空） | ⚠️ 是，但属「一表多键组」，见 KC-20 |

键全集 **1065** 逐 entry 现算：K1 142 · K5 119 · K6 107 · K2 86 · K3 86 · K8 86 · K9 79 · K7 76 · K10 64 · K4 62 · K13 57 · K12 53 · K11 48（和 = 1065 ✓）⇒ **全平台单循环最多**（J 是 160，K 是其 6.7 倍）。

### KC-6 行身份四族与判别式（与 J 的 JD-8 统一表述）

**判别式（可复算布尔表达式，不是人工归类）**：
```
ENTROPY  = /Date\.now\(\)|Math\.random\(\)/
FALLBACK = /\?\?|\|\|/
family_c ⇔  ENTROPY ∧ ¬FALLBACK      （安全，非缺陷）
family_b ⇔  FALLBACK                 （下标兜底，缺陷）
family_a ⇔  其余                      （纯序号，缺陷）
```

| 族 | 现算 | slice | 判定 |
|---|---|---|---|
| family_a 纯序号 | **32** | 32 | ✅ 缺陷 |
| family_b 下标兜底 | **13** | 13 | ✅ 缺陷 |
| family_c 熵生成 | **3** | 3 | 非缺陷 |
| `total_hits` | **48** | 48 | = a+b+c |
| `defect` | **45** | 45 | = a+b |
| 🔴 family_d 展示序号 | `seq` **35** / `seqNo` **6** / `index` **25** | 38 | **不计入 `total_hits`**；slice 的 38 是多键口径，判据须写明键名集合 |

逐 entry defect 现算 **9 条逐条吻合 slice**：K8 8 · K9 7 · K5 7 · K6 7 · K7 6 · K11 4 · K1 3 · K12 2 · K3 1（和 = 45 ✓）；**零缺陷 4 条** = K2 / K4 / K10 / K13。

🔴 **与 J 轮 JD-8 的镜像反例**：`K7TabDisclosureSoe.vue#L401` 的 ``String(raw?.id || `grant-${idx}-${Date.now()}`)`` **同时含 ENTROPY 与 FALLBACK** ⇒ 按判别式归 **family_b（是缺陷）**。J 轮裁的是「含 `Math.random()` 且回落分支不是下标 ⇒ 安全」，K 轮这处**回落分支本身就是含下标的模板** ⇒ 两轮判别式必须统一到上面这三行布尔表达式，不能各写一套散文。

🔴 **扫描范围**：owner 模块**分居两处** —— `components/workpaper/composables/`（`useK1WriteoffCheck` / `k1DisclosureModel` / `useK8Checks` / `useK9Cutoff` 等 **205 个**）与 `components/workpaper/k{n}/**`（各 Tab，**149 个**）。只扫其中一处会漏掉一半命中；前缀正则须带 `(?![0-9])` 负向断言，否则 `K1` 会吃掉 `K10..K13`。

**三族已真落库确证**（BP-8 非空反证）：
- `K1-2-detail-rows`（274,741 B / 4 行）：`{"id":"K1-2-r-ec868163cf71","seq":1,"counterparty":"上海九州通医疗器械供应链有限公司","beginBalance":53336,"endBalance":99999,"agingPrior":{…6档},"agingCurrent":{…}}` ⇒ `K1-2-r-{12位hex}` **安全族**，且 `seq` 确为展示序号（**family_d 不计入的实证**）
- `K8-6-rows`（195,960 B）：`{"rowKey":"row-0-1784807974207","index":1,"voucherNo":"0285","amount":79.97,"accountCode":"6601.15.01"}` ⇒ 🔴 **family_c 的 `row-${idx}-${Date.now()}` 真落库**（idx=0），另有 `index` 展示序号
- `K9-1-rows`（11,549 B）：`{"rowKey":"row-jil2dvsb","projectName":"管理费用_职工薪酬_工资",…}` ⇒ `row-{8位base36}` 纯随机族

### KC-7 removeRow 契约需四元组（JC-7 从三元组扩展）

现算 **36 种签名形态 / 124 站点**（J 是 4 种 / 8 处）。

| arity | 种数 | 参数名族 |
|---|---|---|
| 1 | **28** | `id` · `rowId` · `rowKey` · `idx` · `$index` · `row.id` · `row.rowId` · `row.rowKey` · `row` · `row: K2AdjRow` · `tableIndex` · `actualIdx` |
| 2 | **8** | `(tableKey, id)` `useK1AuditRows.ts#L60` · `(section:'reversal'\|'writeoff', id)` `useK1WriteoffCheck.ts#L424` · `(block: K6BlockKey, id)` `useK6NoteBlocks.ts#L127/#L247` · 调用点字面量 `('rows', row.id)` / `('reversal', row.id)` / `('writeoff', row.id)` / `('impairment', row.id)` / `('nonCurrent', id)` / `('disposalGroup', id)` / `('liabilities', id)` / `('liabilities', row.id)` |

⇒ 契约字段 `row_delete_api_kind` 的单值枚举**装不下**，SHALL 改为 `{kind, arity, param_order, param_name_family}` **四元组**。

🔴 **K 有下标族**（J 无）：`$index` / `idx: number` / `actualIdx` / `tableIndex`，站点集中在 **K3 / K4 / K5 / K6 / K7** —— 正是 BP-8 位置化的重叠 entry，两条缺陷在同一批文件里叠加。

### KC-8 跨循环键冻结在 K 强命中（JC-17 的完全反向）

J 循环是「完全自闭」（J 键无一被非 J 消费、J 文件无非 J 键）。**K 完全相反**。

| K 键 | 被消费方 |
|---|---|
| `K11-2-detail-rows` | `useH1Impairment.ts`（🔴 **H1 = adapter 已注册的 pilot**）· `useH8Impairment.ts` · `useI1Impairment.ts` · `h3ImpairmentCrossSheet.ts` |
| `K11-2-fixed-asset-occurrence` | `useH1Impairment.ts` |
| `K11-2-rou-occurrence` | `useH8Impairment.ts` |
| `K11-2-intangible-occurrence` · `K11-2-intangible-source-amount` | `useI1Impairment.ts` |
| `K11-source-H1-amount` / `-H3-` / `-H8-` / `-I1-amount` | 对应 H1 / H3 / H8 / I1 各一 |
| `K1-1` | **G 循环** 4 文件（`G2TabDisclosureListed.vue` · `G3TabDisclosureListed.vue` · `g2NoteSectionMap.ts` · `G3TabDisclosureSOE.vue`） |

非 K 域文件消费的 K 键现算 **70 个**（含大量 `cycleImportExportRegistry.generated.ts` 的 sheet 码）。
反向：K 域文件里的非 K 循环键仅 **4 种**（`b19-alert` 2 处 · `b19-tag` 1 · `H1-14-supplement-total` 1 · `H1-14-calc-rows` 1）。

🔴 **判据**：`K11-*` 与 `K1-1` 一律**冻结键名**，改动必回归 **H1 pilot 的 golden**（H1 的 adapter 已注册，契约 `h1.disposal_check.json` 已 reviewed）。

### KC-9 definedName 断链登记（🔴 slice 完全漏掉，本轮自行现算）

| 册 | definedName | 含 `#REF!` | 断链率 |
|---|---|---|---|
| **K4 其他流动负债** | **43** | **36** | 84% |
| **K2 其他流动资产** | **37** | **29** | 78% |
| K6 持有待售 | 1 | 0 | — |
| K10 其他收益 | 1 | 0 | — |
| 其余 10 册 | 0 | 0 | — |
| **合计** | **82** | **65** | 79% |

slice 的 `k_cycle_form_differences`（KD-1~KD-7）与 `template_resolution_audit` **没有任何 definedName 节** ⇒ 这是 HC-14 / IC-10 / JC-13 的承接缺口。
**判据**：登记基线 + 断言**不增长**，**不删**（删 definedName 有 Excel 公式连带风险）。断链的 65 个全落 lane 1（K2 29 + K4 36）。

### KC-10 sheet 名四类字符缺陷禁归一化

| 类别 | 现算 | 实例 |
|---|---|---|
| 名中半角空格 | **21** | K4 全 5 张（`审定表 K4-1` / `明细表 K4-2` / `调整分录汇总 K4-3` / `其他流动负债检查表 K4-4` / `实质性程序表 K4A`）· K5 全 8 张 · K6 5 张（含 `减值准备测试表（后续计量） K6-5`）· K1 / K2 / K11 各 1（`实质性程序表 K1A` 等） |
| 🔴 括号半/全角混用**不配对** | **5** | K1 `附注披露信息(上市公司）`（半左+全右）· K5 `附注披露信息（上市公司)`（全左+半右）· K6 `附注披露信息(国企）` · K8 `截止性测试(从记账凭证至原始凭证）K8-6` · K9 `截止性测试(从记账凭证至原始凭证）K9-6` |
| 全半角括号 | **2** | K3 `附注披露信息(上市公司)` / `附注披露信息(国企)` |
| 🔴 重复字 | **1** | K2 `其他流动资产检查表表K2-6`（「表表」） |

另：🔴 **K7 用 `附注披露信息（国有企业）`**，其余 12 册全用「国企」。
**首尾空格现算 0**（`s != s.strip()` 命中 0）—— 与 J1 册**相反**，JC-10 的「尾部空格」判据在 K 不命中，但「0 命中」本身是可复算结论须两侧都验。
`实质性程序表 K1A`（有空格）vs `实质性程序表K3A`（无空格）不一致 ⇒ 按 sheet 名定位 sheet 一律**逐字节比对，禁 strip、禁全半角归一**。

### KC-11 K1 双变体披露表 70 格 `=#REF!` 死公式（🔴 slice 完全漏掉，真缺陷）

| sheet | 格数 | 行数 | 行区间 |
|---|---|---|---|
| `附注披露信息(上市公司）` | **35** | 8 | R125-R140 |
| `附注披露信息（国企）` | **35** | 8 | R104-R129 |

**上市公司表逐格语义**（国企表对称同型）：
- R124 表头「按欠款方归集的期末余额前五名的其他应收款」 → **R125-R129 的 A/C/D/F 列全 `=#REF!`**（🔴 **E 列 `=IF(C125=0,0,C125/$B$18)` 活着**，指向账龄小计 B18）→ R130 `合 计` = `=SUM(C125:C129)` / `=SUM(F125:F129)` ⇒ **恒传播 `#REF!`**
- R137 表头「⑧ 应收政府补助情况（逐项披露）」 → **R138-R140 的 A-E 全 `=#REF!`** → R141 `合 计` = `=SUM(C138:C140)` ⇒ 同样传播

**算术**：R125-129 的 4 列 × 5 行 = 20 + R138-140 的 5 列 × 3 行 = 15 ⇒ **35** ✓（两表合 70）
**判定**：E 列活证明不是整表失效，而是**源 sheet 被删或改名导致的部分断链** ⇒ **真缺陷**，走**覆盖层**修（FC-5 覆盖层例外的新增一条）。归 lane 1（K1 在 lane 1）。

### KC-12 footer 三形态（无 SUBTOTAL）

| 形态 | 现算 | 实例 |
|---|---|---|
| 连续区间 SUM | **140** | `=SUM(D11:D16)`（canary 所在 `调整分录汇总K10-3` 属此族） |
| 加法式 | **19** | `=B18-B19`（K1 披露表）· `=B36+B33` |
| 跳跃式 SUM 多段 | **5** | `=SUM(B9,B10)`（`审定表K1-1` 三处）· `=SUM(B16,B26,B37,B45)`（`坏账准备测算K1-8`）· `=SUM(B25:B26,B29:B30)`（`初始确认检查表K6-4`） |
| 合计 | **164** | 140 + 19 + 5 ✓ |

与 JC-12 的三形态**同构但分布不同**（J 是跳跃/加法/连续三类，K 以连续区间为绝对主体）。IC-13 的第四值 `row_formula_applied` 在 K **未命中**（无 SUBTOTAL）。

### KC-13 两处扫描误报必须如实登记（否则会误立缺陷）

**① J 型「幽灵行」在 K 不命中**
宽口径（A/B/C 全空但同行有公式）现算 **149 行**；收紧到「落在最后一个 footer 行之前」现算 **125 行**。三处样本逐格核验：
- `明细表K3-2` R10-R14：只有 H 列 `=E10+F10+G10`（期初审定 = 未审 + 两类调整），A-G 待用户填
- `摊销测算表K2-5` R12-R16：只有 H/I 列（到期判断 / 日期计算），A-G 待填
- `明细表K8-2` R22-R24：**连公式都没有**，R25 `合计 =SUM(B12:B24)` 含这三空行是**预留扩展**

⇒ 全是**预置空白业务行带公式**的正常模板设计。
🔴 **与 J 的 R45 区分判据**：J 的幽灵行落在 **footer 区内**且是**横向校验** `F45 = C45+D45-E45`；K 的落在**数据区**且是**纵向派生** ⇒ 该判据在 K 退化为「预置空白业务行计数」，**不是缺陷**。

**② 「合计漏加小计」2 格是两层小计的正确写法**
`附注披露信息(上市公司）` 的 B18/C18 命中 `SUM(B12:B17)` 含小计行 R12。逐格核验该区结构：
```
R9-R11   1年以内的三个分档
R12      1年以内小计：   =SUM(B9:B11)
R13-R17  1至2年 / 2至3年 / 3至4年 / 4至5年 / 5年以上（引 '审定表K1-1'!I32..I36）
R18      小  计         =SUM(B12:B17)   ← 外层故意含内层小计行
R19      减：坏账准备     ='审定表K1-1'!I45
R20      合  计         =B18-B19
```
内层明细 R9-R11 已被 R12 吸收，外层不再单列 ⇒ **不重不漏**，与 J 轮 `附注披露信息（国有企业）!B29:E29` 同型的**扫描误报**。

🔴 **副产物（KD 级新发现）**：同册 `附注披露信息（国企）` 却是 **R7-R12 六档一层** + R13 `小 计 =SUM(B7:B12)` ⇒ **同册双变体披露表的账龄分层深度不同**（上市公司 3+5 两层 / 国企 6 档一层）⇒ 两变体不能共用同一套行映射。

### KC-14 BP-7 notice 从零补，判据必须写明符号

| 符号 | 全平台生产命中 | K 域命中 |
|---|---|---|
| `GtEntrySyncCapabilityNotice`（组件名） | **48** | **0** |
| `workpaperEntrySyncNotice`（模块名） | **2**（仅 `sync/` 目录自身两文件） | **0** |

两个口径都对，只是符号不同 ⇒ 判据 SHALL 写明用哪个。K 域两者都 0 ⇒ **BP-7 确证，13 宿主一个都没挂**，是「从零补」不是「已有待改」。

### KC-15 两种 el-segmented 门控形态 + 判据必须先剥注释（KD-6 + KD-7）

| 门控形态 | 宿主 | 现算 |
|---|---|---|
| `v-if="dualMode.isOoAvailable.value"` 二级门控 | K1~K7 + K10~K13（**11 条**） | 宿主层各 1 处 |
| 🔴 `disabled: !isOoAvailable.value` 选项（D4 范式） | **K8 / K9** | 宿主层 **0**，在 **composable**：`useK8DualMode.ts#L48` / `useK9DualMode.ts#L47` |

🔴 判据统一写「必须有 `v-if` 二级门控」会**假红 K8/K9**；且必须**去 composable 里找** `disabled`，宿主层扫不到。
`el-segmented` 剥注释前多数宿主命中 2 处（第二处在块注释里）、**剥后 13/13 恒 1 处**，且剥后那处须落在该宿主声明的 `toolbar_gate_anchor` 之后 6 行内。

### KC-16 derived_total 现算 83 个，正则必须覆盖中置形态（JC-18 在 K 放大）

| 正则 | 现算 |
|---|---|
| 尾部 `-(total\|subtotal\|summary)$` | **77** |
| 🔴 加中置 `(?:^\|-)(total\|subtotal\|summary)(?:-\|$)` | **83** |
| 🔴 **仅中置命中的 6 个** | `K1-8-calc-total-provision` · `K11-2-total-occurrence` · `K4-1-subtotal-credit` · `K4-1-subtotal-debit` · `K8-2-total-audited` · `K9-2-total-audited` |

J 轮是 7 个（4 尾 + 3 中置），K 是 **83 个（77 尾 + 6 中置）** ⇒ 同一教训在 K 规模放大 **11.9 倍**。
**判据**：`derived_total_keys` 一律**现算**（禁写死）；契约 SHALL 声明这 83 个键为派生态、排除 roundtrip 业务比对、指定重算责任方。
🔴 这 83 个键是 **Property 24 的非空分母**（「回写时不得把派生值当用户录入写回」这条在 K 有真对象可验，虽然回写路径本身还不存在）。

### KC-17 prefill 51 条：sheet 名逐字一致是 K 的干净点

文件真名 `backend/data/prefill_formula_mapping.json`（460,871 B，`mappings` 306 条），K 前缀现算 **51 条** = 14 条审定表（K0~K13 各 1）+ **26 条披露表**（13 entry × 2 变体）+ 11 条其他。

🔴 **sheet 名 51/51 全部与模板真名逐字一致**，含全部四类字符缺陷：`审定表 K4-1`（带空格）· K1 `附注披露信息(上市公司）`（半全混）· K3 `附注披露信息(上市公司)`（全半角）· K5 `附注披露信息（上市公司)` · K6 `附注披露信息(国企）` · K7 `附注披露信息（国有企业）`
⇒ **与 J 的「`审定表J1-1` 缺尾部空格必失配」形成鲜明对比，这是 K 的一个干净点**，判据方向是**断言保持一致**。

两处仍须登记的缺陷：
- 🔴 **2 条 `cells=0` 死配置**：`明细表K1-2`（`wp_name='其他应收款明细'`）· `明细表K3-2`（`'其他应付款明细'`）⇒ 与 J 的 `明细表J1-2 ` 的 `cells: []` 同型
- 🔴 **K4 三条 `account_codes=[]` 空科目**：审定表 + 上市披露 + 国企披露
- `items` 全 `None`（与 J 的「items 全 0」同）

科目码现算：K0 `['1221','1231-03','1131','2241','2231']` · K1 `['1221','1231-03','1131','1132']` · K2 `1901` · K3 `2241` · K5 `2801` · K6 `['1481','1482']` · K7 `2401` · K8 `6601` · K9 `6602` · K10 `6117` · K11 `6701` · K12 `6301` · K13 `6711`。

### KC-18 localStorage 两种用途须分清（legacy step 5 在 K 适用，J 不适用）

现算 **26 文件**：

| 用途 | 文件 | 说明 |
|---|---|---|
| 模式偏好 | 13 个 `useK{n}DualMode.ts`（各 2~3 处，前缀 `k{n}-dual-mode:`）+ 3 宿主（K4/K5/K6 各 2 处，**与 composable 同值撞车**） | ⇒ step 5 `unify_mode_values` **只收敛这一类**，目标 `workpaper-sync-mode:` |
| 🔴 列显示偏好 | `useK1DetailColumnPrefs.ts` · `useK4DetailColumnPrefs.ts` · `useK10DetailColumnPrefs.ts` · `useK11DetailColumnPrefs.ts` · `useK10GrantColumnPrefs.ts`（各 2 处） | **另一用途，不是模式偏好**，不得一并收敛 |
| 其他 | 6 个 Tab 组件（`K6TabDetail` / `K7TabDeferredCheck` / `K8TabSellingCheck` / `K9TabDetail` / `K9TabAdminCheck` 等各 2 处） | 逐处判定用途 |

J 循环 localStorage 现算 **0**（共享基类零 localStorage）⇒ legacy step 5 在 J 不适用；**K 适用**，照抄 J 的「不适用」结论会漏做。

### KC-19 OCR 两种 URL 形态并存（本身就是缺陷）

| 端点形态 | 现算文件数 | 站点样本 |
|---|---|---|
| 🔴 `/api/d4/contract-ocr`（**无 wpId 段**） | **7** | `useK1VoucherOcr.ts` · `K12TabDetail.vue` · `K12TabNonOperatingCheck.vue` · `K13TabNonOperatingCheck.vue` · `K3TabRelatedParty.vue` · `K8TabContractCheck.vue` |
| `/api/workpapers/${…}/d4/contract-ocr` | **3** | `K5TabLitigationCheck.vue` · `K9TabAdminCheck.vue` · `K9TabContractCheck.vue` |
| 宽口径 `contract-ocr` | **12** | 另含 `K10TabOtherIncomeCheck.vue` · `K10TabReceivableGrant.vue` |

`runOcr` 命中 **4 文件**；`OcrConfirm` 命中 **0**。
⇒ **FC-8 在 K 命中且跨循环复用 D4 端点**（J 轮只 1 处 `useJ1VoucherOcr.ts`），规模放大到 12 文件；🔴 **两种 URL 形态不一致本身是缺陷**（同一能力两个契约面），SHALL 登记并在 lane 内统一。

### KC-20 孤儿 per-row 键（新缺陷）

K2 的 `审定表K2-1` 是「一表多键组」：主键 `K2-1-rows` 存**行定义**、per-row 键存**金额**。

真库实测：
```
K2-1-rows = [{"rowId":"r-ls0ldh","label":"坏账准备_其他应收款","source":"tb","accountCode":"1231.03"},
             {"rowId":"r-5ac9vk","label":"坏账准备_应收账款","source":"tb","accountCode":"1231.02"}]
K2-1-r-ls0ldh-begin = '-732505.4'      K2-1-r-ls0ldh-unadj = '-1312178.93'
K2-1-r-5ac9vk-begin = '-377709.19'     K2-1-r-5ac9vk-unadj = '-406014.85'
🔴 K2-1-r-ryx6og-begin = ''   K2-1-r-ryx6og-unadj = ''     ← rowId 不在 K2-1-rows 里
🔴 K2-1-r-yqfa02-begin = ''   K2-1-r-yqfa02-unadj = ''     ← rowId 不在 K2-1-rows 里
```
⇒ **行已删、金额键残留**（8 个 per-row 键里 4 个有值 4 个是孤儿）。
**判据**：per-row 键集合里出现的 rowId SHALL 是主键载荷 rowId 集合的**子集**；超出的登记为孤儿并给清理动作。归 lane 1（K2 在 lane 1）。

### KC-21 审定表可以是纯派生表（无 OO 侧输入位）

`审定表K2-1` 现算 `r=23 c=16 merged=9`：
- R5/R6 **两级表头**；🔴 R5 的 J5/L5 含**单元格内换行符** `本期未审数与上期\n未审数的比较` / `本期审定数与上期\n审定数的比较`（J 轮 RD-5 第三类在 K 复现）
- **数据区 R7:R13 七行**：🔴 **连 A 列项目名都是公式** `='明细表K2-2'!A11` ~ `A17`；B/C/D/F 同样跨表引；E/I/J/L 是本表派生（`=B7+C7+D7` / `=F7-B7` 等）
- R14 空行（预留）· R15 `合计 =SUM(B7:B14)` 含空行

⇒ **OO 侧无任何用户输入位**，双向回写的「写回」方向空转。
**判据**：契约 SHALL 标 `derived` + `editable_labels: false`；且**不得选此类表作 canary**（这是 canary 未选 `K2-1-rows` 的第三条理由）。

### KC-22 三条口径陷阱必须写进判据

1. 🔴 **`GtKamWorkpaper.vue` 必须排除**：含则 K 域文件数 **368**、排除则 **367** ✓ 吻合 slice。slice 的 `excluded_from_slice` 第 5 条专门登记它「让『按文件名前缀 GtK 枚举宿主』这条捷径被显式否决」。它带 **2 处 `checklist-responses`** + `/api/a17/kam/push-to-report` + `/api/a17/kam/{X}/ai-generate` 两端点，不排除会污染写路径计数。
2. 🔴 **行数口径**：slice 的 13 个 dual-mode 行数全部用 `len(text.split("\n"))`；`splitlines()` **恒少 1**（13/13 验证：slice 115/115/115/126/126/125/116/189/182/155/154/158/158 ↔ `splitlines()` 114/114/114/125/125/124/115/188/181/154/153/157/157）。orphan 7 个合计 slice 838 = `splitlines` 831 + 7。
3. 🔴 **「契约已发」≠「adapter 已注册」**：契约目录现算 **18 文件 / reviewed 17 / candidate 1**，而 manifest 里 `adapter_id` 非空现算 **9 条**（d1,d2,d3,d4,d5,d6,d7,g7,h1）。`b60` / `e1` / `f1` / `f3` / `f4` / `f5` / `g2` / `h9` 八份契约已 reviewed 但 manifest 仍 `single_onlyoffice` + `adapter_id=null` + `legacy_fake_bidirectional`。manifest **根本没有 `adapter_registered` 字段** ⇒ 按该字段判会恒得 0。

### KC-23 科目四表判据必须按资产负债 / 损益分支

| 侧 | entry | 共享件 | 现算 |
|---|---|---|---|
| 资产负债 | K1~K7（7 条） | `select_leaves` / `aggregate_leaves` | 命中非 0 |
| 🔴 损益 | K8~K13（6 条） | `pl_render.render_pl_cycle` → `pl_occurrence` | `select_leaves` 命中 **0 是正确的** |

⇒ 判据统一要求 `select_leaves` 会**假红 6 条损益 entry**。
🔴 `RENDER_STRATEGY_DIR.glob('_k*.py')` 捞 **42** 个 = **13 主** + **3 K0**（`_k0_confirmation.py` / `_k0_confirmation_ai.py` / `_k0_confirmation_import_export.py`，归 Task 57）+ **26 辅助**（各 entry 的 `_ai_generate` / `_import_export`）⇒ 判据 SHALL 按「是否 `import app.services.four_table.k_cycle_specs`」筛，**不能按文件名前缀**（slice 首轮即因此把 `_k0_confirmation.py` 当损益侧 entry 打红）。
前端 13 个 `k{n}AccountScope.ts` 现算全存，范式文件 `k2AccountScope.ts` 的口径 = 运行态取 render 下发的 `tb_source_codes.gross_standard`，常量只作兜底 + 展示。
`duplicate_account_aggregation_found` 现算 **0**（扫 `backend/app/` 全域 .py）。

### KC-24 空分母纪律与七项结构性零

Task 53 点名 Property **20 / 24 / 69 / 70**；另沿用 Property 3 / 21 / 22 / 23 / 28 的可沿用部分。
**不宣称通过的部分**：contract 数 0 / bidirectional 数 0 / K adapter 数 0 / published representation 数 0 所涉的正向判据。

**七项结构性零**（每项都须「现算为 0」+「变异注入后打红」两侧证据）：

| # | 项 | 现算 |
|---|---|---|
| ① | 本表行越界（引用行号 > `max_row`，排除含 `!` 的跨表式） | **0 格** |
| ② | 跨表引用指向不存在 sheet（单引号包裹形态） | **0 格** |
| ③ | 🔴 同尾码双 sheet（变体轴） | **0** ⇒ **HC-5 / JC-11 在 K 不命中**；K8-6/K8-7、K9-6/K9-7、K6-5/K6-6 都是**不同尾码**的方向或对象变体 |
| ④ | Excel Table | **0** |
| ⑤ | sheet 名首尾空格 | **0** |
| ⑥ | hardcoded 六模式里的五个（`blankRows_literal_count` / `horizontal_company_column_literals` / `column_key_uses_label` / `row_cell_key_uses_label` / `seed_placeholder_literal`） | 各 **0** |
| ⑦ | `duplicate_account_aggregation_found` | **0** |

🔴 **hardcoded 第六个模式 `positional_row_id_template` 现算 13 处非 0**（J slice 的同名判据是「六个 0」，照抄即假红）。这 13 处 SHALL 被断言为位置化 48 处命中的**子集**，证明两个扫描口径互相印证而不是各说各话。
🔴 **`blankRows` 在全 K 域 0 次调用**（该函数在 H 域使用）⇒ HC-13 的「按公司横向展开宽表」在 K 不命中，虽然 K 有 **24 张 ≥20 列的宽表**（最宽 `核实被函证单位信息K0-2` c=40 · `明细表K1-2` c=36 · `明细表K7-2` c=32），它们是**纵向多行 + 列固定**的形态。

---

## canary 裁决：`K10-3-entries`（`调整分录汇总K10-3`）

### 候选对比（硬标准 = 真库有非空载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组）

| 候选 | 真库 | 几何 | entry 位置化 | 载体族 | 裁决 |
|---|---|---|---|---|---|
| **`K10-3-entries`** | **199 B** | `r=25 c=10 f=7 bareIF=0 merged=3` | **0** | dedicated | ✅ **入选** |
| `K1-2-detail-rows` | 274,741 B（全平台最大） | `明细表K1-2` r=50 **c=36** f=136 bareIF=19 | 3 | inlined IIFE | ❌ 太大 + 宽表 + 同册 70 格 `#REF!` |
| `K8-6-rows` | 195,960 B | `截止性测试(从记账凭证至原始凭证）K8-6` r=44 c=11 | **8（最多）** | dedicated | ❌ 位置化最重 + sheet 名半全混 |
| `K9-1-rows` | 11,549 B | `审定表K9-1` r=44 c=14 **f=223 bareIF=19** | 7 | dedicated | ❌ 同表另有 `K9-1-audited-by-item` + `K9-1-audited-total` ⇒ 多键组 |
| `K2-1-rows` | 160 B | `审定表K2-1` r=23 c=16 f=110 bareIF=16 | **0** | inlined IIFE | ❌ **三条硬伤**（见下） |
| `K2-disc-listed-main` | 823 B **有真金额** | `附注披露信息（上市公司）` r=13 c=13 | 0 | inlined IIFE | ❌ 披露层同表 6 键 |
| `K10-2-detail-rows` | **有行但 remark 空** | `明细表K10-2` r=43 c=12 f=27 bareIF=0 | 0 | dedicated | ❌ 不满足硬标准 |
| K11 / K13 | **真库 0 行** | — | 4 / 0 | dedicated | ❌ |
| K3 / K4 | 仅披露层 | — | 1 / 0 | inlined IIFE | ❌ 无主表键 |

**否决 `K2-1-rows` 的三条硬伤**：
1. 载荷是 **TB 来源行定义**不是业务数据（见 KC-20 的真库实测）；真金额在 per-row 拆键里 ⇒ **一表 9 键组**，违反「单 sheet 单键组」
2. 🔴 **有孤儿 per-row 键**（KC-20）⇒ canary 得先修缺陷才能跑
3. 🔴 **`审定表K2-1` 是 100% 派生表**（KC-21）⇒ OO 侧无输入位，「写回」方向空转

### 入选三条硬依据

1. **唯一同时满足四项硬标准**：真库 199 B 非空 + 在 `xlsx/gt-k10-other-income` 内 + K 循环 `parent_duplicate` 计数为 0（自动满足）+ **单 sheet 单键**（同表另一键 `K10-3-published` 是发布标记不是行数据）
2. 🔴 **几何最简且 13 册完全同构** —— 13 册「调整分录汇总」现算 `r ∈ [21,25]` / `c=10` / `f=7` / `bareIF=0` / `merged=3`，**13/13 无例外**（全 K 唯一有此性质的表）⇒ **canary 判据可直接外推到其余 12 条 entry**，这是任何其他候选都没有的杠杆
3. **身份族已是安全族** + K10 是 4 条零位置化缺陷 entry 之一（K2/K4/K10/K13）⇒ **canary 不必先修身份缺陷**（对比：I6 需先做身份 backfill、J1-6 需先修 RD-5 三边差异）；加上 K10 册**裸 IF 0**（14 册唯一）+ definedName 1 个但 **0 个 `#REF!`**

### 四条逆风（如实登记，不粉饰）

| # | 逆风 | 应对 |
|---|---|---|
| ① | 🔴 载荷是**测试骨架**：`description:"测试确认政府补助"` · `debitAmount`/`creditAmount` 均 0 · `category`/`reportItem`/`noteItem`/`refIndex`/`remark` 五字段空串 | roundtrip **只能验结构**；另造带金额合成载荷补一轮，标 `synthetic_payload_for_amount_dimension` |
| ② | 🔴 K10 属 **BP-6 组（`dedicated_composable`）** ⇒ canary **不覆盖 BP-5 的「7 个一阶 orphan + 宿主内联 IIFE」主线形态** | 该首例**外移到 lane 1**，本 spec 在交接节指名 |
| ③ | 🔴 `useAdjustmentCentralSync` 是**第二写入方**（`K10TabAdjustment.vue` 3 处） | roundtrip 的写入方集合 SHALL 含它 |
| ④ | 🔴 同 entry 内有 **6 个 `K10-review-session-{14位时间戳}` 键**（各 262 B） | 契约 SHALL 显式声明属另一命名空间，**不纳入 managed table** |

### canary 模板落点（`调整分录汇总K10-3`，现算）

`r=25 c=10 f=7 merged=3 bareIF=0`；footer 属 **KC-12 的连续区间 SUM 族**。
K10 全部真库键现算 **18 个有行 / 7 个 remark 非空**：6 个 review-session（各 262 B）+ `K10-3-entries`（199 B）；其余 11 个有行但 remark 为空（含 `K10-2-detail-rows` / `K10-2-subtotal` / `K10-3-published` / `K10-4-rows` / `K10-5-check-rows` / `K10-6-check-rows` / `K10-6-coverage-rate` / `K10-1-audit-note` / `K10-disc-soe-row-0` / `K10-4-k7-amort` / `K10-4-k7-consistency`）；`K10-1-rows` 与 `K10-1-audited-total` **无行**。

### K10 的 BP 归属（现算 `capability_target_blocked_by`）

`[BP-1, BP-2, BP-3, BP-6, BP-7, BP-9]` —— **不含 BP-4 / BP-5 / BP-8**。

| BP | 本 spec 处置 |
|---|---|
| BP-1 / BP-2 / BP-3 | 🔴 **平台级供给，只标 `[ ]*`，不承诺在本 spec 内完成** |
| BP-6 | 删 `useK10DualMode.ts` 的两处 legacy 端点直调（`onlyoffice/health` 1 + `onlyoffice-config` 1），改走 sync bridge materialize |
| BP-7 | 在 `GtK10OtherIncome.vue` 挂 notice（KC-14 口径） |
| BP-9 | step 9 后重新生成 manifest |
| BP-4 | 🔴 **不属本 spec**（只 K1）⇒ lane 1 |
| BP-5 | 🔴 **不属本 spec**（K1~K7）⇒ lane 1 |
| BP-8 | 🔴 **不属本 spec**（K10 位置化为 0）⇒ 24 处归 lane 1、21 处归 lane 2 |

---

## 三份 spec 的切分与算术自检

| spec | entry | BP-8 | 键 | sheets | 裸 IF | 真库非空键 | definedName |
|---|---|---|---|---|---|---|---|
| **本 spec**（foundation + canary） | K10（1 条） | **0** | 64 | 11 | **0** | 7 | 1（0 `#REF!`） |
| `k1-k7-inlined-iife-hosts-and-orphan-cleanup` | K1~K7（7 条 = BP-5 全部） | **24** | 678 | 81 | 291 | 54 | 81（**65 `#REF!` 全在此**） |
| `k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub` | K8/K9/K11/K12/K13（5 条） | **21** | 323 | 49 | 424 | 6 | 0 |
| **合计** | **13** ✓ | **45** ✓ | **1065** ✓ | **141** ✓ | **715** ✓ | **67** ✓ | **82** ✓ |

**切分理由**：
1. 🔴 **BP-8 的 45 处恰好按 BP-5 / BP-6 分界二分成 24 / 21**（lane1 = K1 3 + K3 1 + K5 7 + K6 7 + K7 6 = 24；lane2 = K8 8 + K9 7 + K11 4 + K12 2 = 21）⇒ 两 lane 各自内聚，缺陷不跨 lane
2. **每份都有零位置化缺陷 entry 作对照组**：foundation K10 / lane 1 K2+K4 / lane 2 K13 ⇒ 能判断是特例还是通例
3. **BP-6 虽被拆（K10 进 foundation）但 K10 是 BP-6 里最干净的一条**，作 canary 恰好先打通 BP-6 形态，lane 2 的 5 条可直接复用
4. **`#REF!` 65 格 + definedName 81 个全落 lane 1** ⇒ 模板层治理单点收口
5. **下标族 removeRow 集中在 K3~K7** 全在 lane 1；**跨循环枢纽 K11 + K8/K9 的 disabled 门控 + 截止性测试**全在 lane 2

**否决方案 A**（foundation 只做 KC + canary，两 lane 按 K1~K7 / K8~K13 二分）：foundation 不含完整 entry 会让「K10 其余 17 键谁管」说不清，且违反 H/I/J 三轮的既定形态（canary 所在 entry 完整放 foundation）。
**否决方案 B**（4 份，K1 单独一份）：K1 单独太薄（BP-4 writeoff + 70 格 `#REF!` 两件事可作 lane 1 内专节），且 K1 与 K2~K7 同属 BP-5，分开会把「7 个一阶 orphan 的删除判据」抄两遍。

**Property 前缀**：本 spec `KF-P` / lane 1 `KA-P` / lane 2 `KB-P`（spec-scoped，各自无重号无缺号）。

---

## Property 清单（KF-P1 ~ KF-P42）

> 每条都是**可复算布尔断言**。「现算」= 实施时重跑同口径脚本并与本文件等值比对。

| ID | 断言 | 裁决来源 |
|---|---|---|
| KF-P1 | 按 `selection_rule` 从 manifest 现算 K 前缀 xlsx 独立 entry 集合 == slice 的 `independent_entries`，大小 **13** | KC-1 |
| KF-P2 | manifest 里 13 条 K entry 的 `capability` 全 `single_onlyoffice` / `html_store` 全 `unresolved` / `adapter_id` 全 null / **0 条有 `capability_target`** | KC-1 |
| KF-P3 | slice 现算 `bidirectional` 条数 == 0 且 `capability_verdict_pending` == 13；守卫断言 manifest 与 slice **不相等**并指向 BP-9 | KC-1 |
| KF-P4 | `parent_entry_id ∈ 13 条 K entry_id` 的条数 == 0 ∧ overlay `parent_rules[].file_glob` 含 `/k\d` 的条数 == 0 ∧ slice 顶层无 `parent_duplicate_summary` 键 | KD-5 |
| KF-P5 | 🔴 K 域生产文件现算 **367**（排除 `GtKamWorkpaper.vue`）；含它则 368 | KC-22① |
| KF-P6 | `backend/wp_templates/K/` 非锁文件 **14** / 锁文件 **0**；`belongs_to_entry` 非 null **13** + null 带 `excluded_reason` **1** | Req 1.5 |
| KF-P7 | 🔴 `K0` 的 `find_template_file` 与 `find_template_file_any` **都返 `K0 管理循环函证.xlsx`**（非 None，与 J0 相反） | KD-4 |
| KF-P8 | 14 册 sheets 合计 **152**（K0 11 + 13 entry 册 141）；逐册 sheet_count 与 slice 等值 | Req 7 |
| KF-P9 | 载体族二分支：12 个 `useK{n}FormData.ts` 各 2 处裸端点 ∧ **`useK5FormData.ts` 裸端点 0 且 `useChecklistPersistence` 3** | KC-2 |
| KF-P10 | `checklist-responses` 端点现算 **16 文件**（排除 Kam）；13 宿主该端点全 0 且 `useChecklistPersistence` 各 3 | KC-2 |
| KF-P11 | 🔴 端点扫描正则认反引号；只认单/双引号时 `onlyoffice-config` 命中降为 0（变异证明） | KC-3 |
| KF-P12 | K 域端点全集现算 **30 种**；`onlyoffice/health` **20 文件 = 13 composable + 7 宿主** | KC-3 |
| KF-P13 | `onlyoffice-config` 现算 **6 文件 / 9 处**（K8:2 K9:2 K10:1 K11:2 K12:1 K13:1） | KC-3 |
| KF-P14 | 🔴 `ledger/entries/1221` 硬编码科目码与 `force_component_type=k1-other-receivables` 两处已登记 | KC-3 |
| KF-P15 | TB 发布门 **13/13 全有 / 14 处 / 四层载体**（5+3+5+1，K5 占 2）；判据不按单层也不按符号名 | KC-4 |
| KF-P16 | 业务键全集现算 **1065**，逐 entry 分布与本文件等值（K1 142 … K11 48） | KC-5 |
| KF-P17 | 🔴 `K{n}-review-session-{14位时间戳}` 现算 **9 个**，被显式排除在 managed table 之外 | KC-5 |
| KF-P18 | 位置化四族现算 a**32** / b**13** / c**3** / total**48** / defect**45**，三族互斥且并集 == total | KC-6 |
| KF-P19 | 逐 entry defect 现算 9 条等值（K8 8 · K9 7 · K5 7 · K6 7 · K7 6 · K11 4 · K1 3 · K12 2 · K3 1）+ 零缺陷 4 条（K2/K4/K10/K13） | KC-6 |
| KF-P20 | 🔴 family_d 按键名集合现算（`seq` 35 / `seqNo` 6 / `index` 25），**不计入 total_hits**；slice 的 38 是多键口径 | KC-6 |
| KF-P21 | 🔴 `K7TabDisclosureSoe.vue#L401` 同时含 ENTROPY ∧ FALLBACK ⇒ 归 **family_b（缺陷）**；判别式与 J 轮 JD-8 统一为三行布尔表达式 | KC-6 |
| KF-P22 | 扫描范围覆盖两处 owner 目录（composables 205 + `k{n}/**` 149）；前缀正则带 `(?![0-9])` | KC-6 |
| KF-P23 | 三族已真落库：`K1-2-r-{hex}` 安全族 · `row-${idx}-${Date.now()}` family_c · `row-{base36}` 纯随机（真库载荷现读） | KC-6 |
| KF-P24 | removeRow 现算 **36 种签名 / 124 站点**（arity=1 28 种 / arity=2 8 种）；契约用 `{kind, arity, param_order, param_name_family}` 四元组 | KC-7 |
| KF-P25 | 🔴 K **有下标族**（`$index`/`idx: number`/`actualIdx`/`tableIndex`），站点集中 K3~K7 | KC-7 |
| KF-P26 | 🔴 跨循环消费现算：非 K 域消费 K 键 **70 个**；`K11-2-*` 四键 + `K11-source-*` 四键 + `K1-1` 的消费方逐条等值 | KC-8 |
| KF-P27 | 🔴 `K11-*` 与 `K1-1` 冻结键名；改动触发 **H1 pilot golden 回归**（H1 的 `adapter_id` 现算非空） | KC-8 |
| KF-P28 | K 域文件引用的非 K 键仅 **4 种**（`b19-alert` 2 / `b19-tag` 1 / `H1-14-supplement-total` 1 / `H1-14-calc-rows` 1） | KC-8 |
| KF-P29 | 🔴 definedName 现算 **82 / 含 `#REF!` 65**（K4 43/36 · K2 37/29 · K6 1/0 · K10 1/0 · 其余 0）；登记基线 + 断言不增长，**不删** | KC-9 |
| KF-P30 | sheet 名四类缺陷现算 **21 + 5 + 2 + 1**；K7 用「国有企业」；**首尾空格 0**；定位 sheet 一律逐字节比对 | KC-10 |
| KF-P31 | 🔴 K1 双变体披露表 `#REF!` 现算 **各 35 格 / 8 行 = 70 格**；E 列 `=IF(C125=0,0,C125/$B$18)` 活着；合计行传播；算术 20+15=35 | KC-11 |
| KF-P32 | footer 现算 **164 = 140 + 19 + 5**，无 SUBTOTAL；IC-13 第四值在 K 未命中 | KC-12 |
| KF-P33 | 🔴 J 型幽灵行在 K 不命中：宽 **149** / 收紧 **125**，三处样本逐格核验为预置空白业务行；区分判据（J footer 区横向校验 vs K 数据区纵向派生）已写明 | KC-13① |
| KF-P34 | 🔴 「漏加小计」2 格是两层小计正确写法（R12 内层 → R18 外层含之，不重不漏）；副产物「同册双变体账龄分层深度不同」已登记 | KC-13② |
| KF-P35 | notice 两符号 K 域命中都 **0**；判据写明用组件名（全平台 48）还是模块名（全平台 2） | KC-14 |
| KF-P36 | 门控两形态：`v-if` **11** 宿主 ∧ K8/K9 的 `disabled` 在 composable（宿主层 0）；`el-segmented` 剥注释后 13/13 恒 1 处 | KC-15 |
| KF-P37 | 🔴 derived_total 现算 **83 = 尾部 77 + 中置 6**，六个仅中置命中的键逐个等值 | KC-16 |
| KF-P38 | prefill K 条目现算 **51**（14 审定 + 26 披露 + 11 其他）；🔴 **sheet 名 51/51 逐字一致**；2 条 `cells=0` + K4 三条 `accounts=[]` 已登记 | KC-17 |
| KF-P39 | localStorage 现算 **26 文件**，模式偏好与列偏好**分类登记**；step 5 只收敛前者 | KC-18 |
| KF-P40 | 🔴 OCR 两种 URL 形态现算 **7 / 3**（宽口径 12）；`runOcr` 4；`OcrConfirm` 0 | KC-19 |
| KF-P41 | 🔴 per-row 键的 rowId 集合 ⊆ 主键载荷 rowId 集合；K2 实测 4 个孤儿（`r-ryx6og` / `r-yqfa02` 各 2 键） | KC-20 |
| KF-P42 | 🔴 `审定表K2-1` 数据区 R7:R13 连 A 列都是跨表公式 ⇒ 标 `derived` + `editable_labels:false`；R5 含单元格内换行符 | KC-21 |

### canary 专属 Property（KF-P43 ~ KF-P52）

| ID | 断言 |
|---|---|
| KF-P43 | canary 选型四项硬标准逐条可复算：真库 199 B 非空 ∧ 在 `xlsx/gt-k10-other-income` 内 ∧ `parent_duplicate` 计数 0 ∧ 单 sheet 单键 |
| KF-P44 | 🔴 13 册「调整分录汇总」现算完全同构（`r∈[21,25]` / `c=10` / `f=7` / `bareIF=0` / `merged=3`，13/13 无例外） |
| KF-P45 | canary 载荷 `id` 形态 `entry-{13位ts}-{6位base36}` ⇒ 安全族；canary 不含身份前置修复 |
| KF-P46 | 🔴 载荷是测试骨架（`description` 为测试串 + 金额 0 + 5 字段空串）⇒ roundtrip 只验结构，另一轮合成载荷标 `synthetic_payload_for_amount_dimension` |
| KF-P47 | 🔴 写入方集合含 `useAdjustmentCentralSync`（`K10TabAdjustment.vue` 3 处） |
| KF-P48 | 🔴 契约显式排除 6 个 `K10-review-session-*` 键 |
| KF-P49 | K10 真库现算 **18 键有行 / 7 键 remark 非空**；`K10-2-detail-rows` 有行但空、`K10-1-rows` 与 `K10-1-audited-total` 无行 |
| KF-P50 | K10 的 `blocked_by` 现算 `[BP-1,BP-2,BP-3,BP-6,BP-7,BP-9]`，**不含 BP-4/5/8** |
| KF-P51 | BP-6 处置后 `useK10DualMode.ts` 的两个 legacy 端点直调命中降为 **0**，且 bridge materialize 路径命中非 0 |
| KF-P52 | 🔴 canary **不覆盖 BP-5 主线**（K10 属 dedicated 组）已显式登记，首例外移到 lane 1 |

### 空分母与结构性零 Property（KF-P53 ~ KF-P60）

| ID | 断言 |
|---|---|
| KF-P53 | Property 20 的 contract 维度**不宣称通过**；前提方向四件真验（契约归属逐文件读 `review.entry_id` / 四条 pilot entry_id 等值 / registry K adapter 数 0 / 13 宿主模板无「可双向回写」字样） |
| KF-P54 | Property 24 两分母分开报：回写保护部分不宣称通过；**83 个派生态键**是非空分母 |
| KF-P55 | Property 69 只作负向真验（13 条 UNVERIFIABLE 各带非空 reasons ∧ 无一条空口声称 VERIFIED） |
| KF-P56 | Property 70 真验：**八 slice 28 个配对**两两不相交 + 契约归属 + 14 册单射 + 13 条 `template_ref.workbook` 集合大小 13 + deletion path 不相交 |
| KF-P57 | 🔴 契约与 adapter 分母分开算：契约目录 **18 / reviewed 17 / candidate 1** vs `adapter_id` 非空 **9**；manifest 无 `adapter_registered` 字段 |
| KF-P58 | 七项结构性零各有「现算 0」+「变异打红」两侧证据，变异脚本复用既有两个 |
| KF-P59 | 🔴 `positional_row_id_template` 现算 **13 非 0**，且是位置化 48 处的**子集** |
| KF-P60 | 🔴 `blankRows` 全 K 域 **0 次调用** ⇒ HC-13 不命中；24 张 ≥20 列宽表是纵向多行+列固定形态 |

### 行数与口径 Property（KF-P61 ~ KF-P63）

| ID | 断言 |
|---|---|
| KF-P61 | 🔴 行数口径声明为 `len(text.split("\n"))`；对 13 个 `useK{n}DualMode.ts` 验证 `splitlines()` **恒少 1**（13/13） |
| KF-P62 | 共享基类窄 **29** / 宽 **33**（不含基类自身）/ 差集 **4**；窄口径里 K 路径条数 **0** ⇒ 本任务前后都是 29 |
| KF-P63 | 🔴 KC-23 分支判据：K1~K7 看 `select_leaves` / K8~K13 看 `render_pl_cycle`；42 个 `_k*.py` 按 import 筛不按文件名；13 个 `k{n}AccountScope.ts` 全存 |
