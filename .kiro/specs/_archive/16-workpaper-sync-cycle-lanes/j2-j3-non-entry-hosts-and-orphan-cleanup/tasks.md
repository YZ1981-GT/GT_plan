# Implementation Plan

## Overview

**spec**：`j2-j3-non-entry-hosts-and-orphan-cleanup`　**创建**：2026-09-26　
**状态**：**15/18 已真实实施**（2026-09-27），3 条如实留 `[ ]*`

🔴 **本文件此前是假绿**：18 个 Task 全标 `[x]` 但本行原写「0/18，Design-First 未实施」，
且 `evidence/` 目录不存在、OD-1~OD-4 四个待删 orphan 全部还在。
本轮真实实施并逐 Task 现算，证据在 **`evidence/task0-to-17-real-implementation.md`**。

**本轮实际产出**：删 **7 个文件 ~594 行** 死代码（OD-1~OD-4 + `useJ3FormData` 簇 3 个）·
修 **5 处**位置化行身份（新建 `jRowIdentity.ts`，number 安全生成器 + 两族 grandfather）·
守卫 `jRowIdentity.spec.ts` **15 passed**（含原缺陷复现 + grandfather 反向自检）·
**7 处**现算否证 spec/plan 冻结值（见 evidence §Task 17）。

**上游（只引用不复述）**：`j-cycle-sync-foundation-and-first-canary`（**JC-1 ~ JC-20** +
canary `J1-6-short-term` 范式）· umbrella Task 52 的 J slice · FC-1~FC-13 · GC-1~GC-10 ·
HC-1~HC-16 · IC-1~IC-20。

`[ ]*` = 依赖外部供给（业务确认 / 模板治理另一链路）。
🔴 **BP-1 ~ BP-4 对本 lane 不是阻塞**（本 lane 不发 contract 不注册 adapter）—— 本 lane 可立刻实施完。

🔴 **本 lane 的主题只有一个**：把「从任何真实宿主都到不了、但看起来活着」的代码删掉，
并把 J2/J3 接入 OO 前需要什么登记成清单。
🔴 **不交付** contract / adapter / roundtrip / canary（J2/J3 **不是** manifest entry）。
🔴 **不得修改 `backend/wp_templates/` 字节**。
🔴 **不得把 J2/J3 手写进 `workpaper_sync_entry_manifest.json`**。
🔴 **不重造已有产物**：`test_task52_j_cycle_migration.py`（含 `TestOrphanDualModeInventory`）·
**变异脚本** `mutate_task52_j_cycle_migration_guards.py`（直接复用）·
🔴 **`workpaper_sync_j_cycle_deletion_plan.json`（已有删除计划，按它执行不另起）**·
两份 render schema（`j2-defined-benefit-plan.yaml` / `j3-share-based-payment.yaml`）。

## Tasks

### 阶段 0：前置门 + 红判据（先打红）

- [x] 0. 前置依赖与已有产物清点（`git show HEAD:` 判定）
  - 核已有 deletion plan 的 4 个待删路径与本 spec 的 OD-1~OD-4 **逐条一致**
  - 声明复用：`TestOrphanDualModeInventory` · 变异脚本 · 两份 render schema
  - 证据 `evidence/task0-prerequisites.md`

- [x] 1. 🔴 JN-1 四侧都验「J2/J3 不是 entry」（JN-P1 ~ JN-P4）
  - ① `selection_rule` 现算 entry 集合恰 **1 条** `xlsx/j1/gt-j1-employee-compensation`
  - ② manifest 里无任何 entry 的 `host_path` 等于两宿主路径
  - ③ 两宿主外层 `<template>` 里 `GtOnlyOfficeSheet` 与 `el-segmented` 命中**各 0**
  - ④ `htmlRendererRegistry` 里两条 componentType 的 import 路径**真指向**这两个文件
  - 🔴 变异「把 J2/J3 手写进 manifest」SHALL 打红（违反 slice step 1 forbidden）
  - 登记宿主 import 段实测四项（无 OO 组件、无 dual-mode）+ 行数 238 / 210 原始
  - 🔴 manifest entries 总数**现算**（**155**，slice 写 186）；写死该数 SHALL 打红

- [x] 2. 零回归基线现算（JN-P39）
  - 现算契约目录 `*.json` 个数与**文件名集合** · `DELIVERED_PER_ENTRY_CONTRACTS` 条数与 entry_id 集合 ·
    `adapter_registered=True` 集合 · `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS`
  - 🔴 **禁写死个数**（会随地基 spec 的 canary 注册而变）
  - 断言本 lane 开工前后契约目录**不变**（本 lane 不发 contract）

### 阶段 1：JN-2 两阶可达性判定 + orphan 删除（本 lane 主线）

- [x] 3. 🔴 两阶可达性判定配方落地（JN-P5 / JN-P6）
  - 一阶：statement 生产边 == 0 **且**测试边 == 0
  - 二阶：全部生产边都指向同一目录 barrel `index.ts`，**且该 barrel 入边 == 0**
  - 四条逐项现算：OD-1 41 行零边 · OD-2 37 行零边 · OD-3 35 行（边 1 barrel + 1 spec，barrel 入边 0）·
    OD-4 39 行（边 1 barrel，barrel 入边 0）
  - 🔴 **反证**：让朴素判据「入度 > 0 ⇒ 不是孤儿」在 `useJ2DualMode`（边数 2）上**放它过去**而打红
  - 🔴 断言 J2 宿主与 6 个子 Tab 都走**逐模块深链**、不走 barrel（这是 barrel 入边为 0 的原因）

- [x] 4. 🔴 OD-1 / OD-2 的 sheet 映射表「接上就坏」判据（JN-P7）
  - `J2_SHEET_MAP` **8 目标** vs 模板真实 **9 张** ⇒ 断言交集 == **空集**
  - `J3_SHEET_MAP` **4 目标** vs 模板真实 **6 张** ⇒ 断言交集 == **空集**
  - 两侧都验：目标数现算 == 8 / 4，且与 `sheetnames` 交集为空
  - 🔴 登记结论：接上宿主会按**不存在的 sheet 名**去取 ⇒ 「接上就坏」不是「接上能用」

- [x] 5. 🔴 OD-4 违规直调登记（JN-P8）
  - 断言 `useJ3DualMode.ts` 直调 `GET /api/workpapers/onlyoffice/health`
    ⇒ 命中 `legacy_deletion_paradigm` **step 6 明禁项**（只能经 sync bridge 的 materialize 协议）
  - 登记它自带的 `checkOOHealth` 与共享基类**重复且更弱**（无 `_silent`、无信封双形态兼容）
  - 🔴 登记风险性质：现在无危害只因整个模块不可达；顺着 barrel 接起来就是**绕过 bridge 的旁路**

- [x] 6. 两个 orphan barrel + 🔴 不得过度宣称（JN-P9）
  - 断言 `composables/workpaper/j2/index.ts` 与 `j3/index.ts` 入边**各 0**
  - 🔴 断言**不宣称**整个 `composables/workpaper/j3/` 目录死：
    同目录 `useJ3ImportExport.ts` 有**真实生产边**（`j3/core/J3TabDetail.vue` 走深链）
  - 变异「把整个 `j3/` 目录列入删除」SHALL 因误删 `useJ3ImportExport` 而打红

- [x] 7. 共享基类保留 + 🔴 窄口径（JN-P10 / JN-P11）
  - 断言 `useWorkpaperEntryDualMode.ts` **保留**：65 行 / localStorage 0 /
    窄口径边 **29** / J 贡献 **3**（OD-1 + OD-2 + J1 宿主）/ 删后剩 **26**
  - 🔴 断言必须用**窄口径**：宽口径现算 **34** 会得 31，让「删完还剩多少」说不清
  - 🔴 按 JC-16：差集判据写「**包含** `workpaperSyncLegacyBaseline.generated.ts`」+ 现算清单
    （现算 **5 个**），**禁写死 1 个**
  - 🔴 保留窄口径的判别规则：匹配点之前未转义双引号个数为奇数 ⇒ 落在字符串内 ⇒ 不是语句

- [x] 8. 🔴 JN-3 `useJ3FormData` 整簇不可达（JN-P12 ~ JN-P16）
  - 断言 **151 行** / 入边 **3**（barrel + `useJ3Detail` + `useJ3Integration`）
  - 🔴 **两层判定**：`useJ3Detail` 自身入边 1（只 barrel）· `useJ3Integration` 自身入边 **0**
    ⇒ 三者构成只经孤立 barrel 相连的簇；变异「只看一层」SHALL 判成活着而打红
  - 断言它含完整管道（render-config GET + checklist PUT + events/publish）
    且 item_id 形态 `` `J3-${key}` `` 在生产路径命中 **0** ⇒ `FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION`
  - 列入 `forbidden_carriers`
  - 🔴 断言 `composables/workpaper/j2/useJ2FormData.ts` **不存在**（删除已兑现）
    —— 作为「删除动作真做了」的**正例锚点**
  - 🔴 登记 `j3/core/J3TabDetail.vue` **自己也直写** `PUT …/checklist-responses`（slice 未提）

- [ ]* 9. 🔴 删除执行（JN-P15 / JN-P38）
  - ✅ **已删 7 个文件 ~594 行**：OD-1(41) / OD-2(37) / OD-3(35) / OD-4(39) +
    `useJ3FormData`(151) / `useJ3Detail`(119) / `useJ3Integration`(172)；
    同步摘 barrel re-export（j2 摘 1 条 / j3 摘 4 条）+ 改 `j2Components.spec.ts`
  - ✅ 删前显式确认联动：`events/publish` **4** 处 + `cross-wp-references/batch` **1** 处
    随整簇消失（整簇不可达 ⇒ 本来就没跑过）
  - ✅ 零回归：grep 零代码引用 · `tsc` EXIT=0 · vitest J 全域 105 passed
  - ✅ 共享基类窄口径边现算 **27**（删前 29 − OD-1 − OD-2）
  - 🔴 **未完成部分：两个 orphan barrel 保留**（本 Task 原文要求删）——
    逐 export 现算后裁决不删：`j2/index.ts` 后面还挂着 **4 个**「只经它被生产消费」的模块
    （`useJ2AccrualCheck` / `useJ2Adjudication` / `useJ2Detail` / `useJ2Disclosure`），
    删它等于**额外宣称那 4 个也死** ⇒ 违反本 spec Task 6 的「不得过度宣称」，
    也超出 deletion plan 精确只列 4 条的授权范围；`j3/index.ts` 同理还挂着 5 个未授权处置的
    orphan。⇒ 只摘掉指向已删模块的 re-export 并在 barrel 内留判定依据注释，剩余归下一轮。
  - 🔴 **按已有 `workpaper_sync_j_cycle_deletion_plan.json` 执行，不另起计划**
  - 删除范围：OD-1 ~ OD-4 四个 orphan dual-mode + 两个 orphan barrel +
    `useJ3FormData` 簇（含评估 `useJ3Detail` / `useJ3Integration` 是否同批）
  - 🔴 **删除前显式确认联动**：`events/publish` 3 处 + `cross-wp-references/batch` 1 处
    随整簇消失（现状：整簇不可达 ⇒ 这些联动本来就没跑过）
  - 三件事齐备才动手：① 两阶判定成立 ② 删前后全套测试零回归 ③ **独立 commit**（便于回滚）
  - 🔴 断言共享基类窄口径边从 **29** 变 **26**（现算，不写死）

### 阶段 2：JN-4 non_entry 位置化身份修复

- [x] 10. 🔴 5 处位置化落表 + family_a 真库实证（JN-P17 / JN-P18）
  - 五处逐条现算落表（family_a 1：`j2/J2TabAdjustment.vue` 的 `id: i + 1` →
    `J2-3-entries`；family_b 4：同文件 `id: e.id ?? i+1` · `j3/core/J3TabDetail.vue` 的
    `id: p.id ?? i+1` · `j3/core/J3TabCheck.vue` **两处** `id: r.id ?? i+1`）
  - 🔴 **用真库实证而不是推演**：`J2-3-entries` 真库 **171 B** 载荷里 `"id":1` **已落库**
    （`[{"id":1,"description":"重分类一年内到期辞退福利","category":"账项调整",…}]`）
  - 🔴 断言这是全 J 域**唯一** family_a 且**已有真实数据受影响** ⇒ 本 lane 最高优先修项

- [x] 11. family_a 修复 + grandfather（JN-P19）
  - ✅ 新建 `components/workpaper/composables/jRowIdentity.ts`；守卫 `jRowIdentity.spec.ts` **15 passed**
  - 🔴 **不复用 `f5RowIdentity.ts`**：那套铸 **string**，而 J 侧 `id` 是 **number** 且宿主用
    `Math.max(...)+1` 做游标、`r.id === row.id` 做定位 ⇒ 换 string 会让 `Math.max` 返 `NaN`、
    打断 4 个行接口类型、与已落库数字 id 冲突。本文件铸 number
    `Date.now()*1000 + Math.floor(Math.random()*1000)`（含随机 / 无下标 / 严格大于现存 id）
  - 🔴 **与 F5 刻意相反**：F5 对「命中旧下标模式」的 id **重铸**；J 侧**不重铸** ——
    F5 旧 id 带前缀（`oc-migrated-3`）可区分，J 侧旧 id 是裸数字 `1`，**无法**区分
    「历史下标 1」与「合法身份 1」⇒ 重铸必然误伤
  - ✅ 反向自检通过：造 `id:1` 历史行，三轮「载入→保存→再载入」后仍是 `1`
  - ✅ 判据复现原缺陷：旧写法删中间行后重载 ⇒ C 身份从 3 变 2（2 上一轮属 B）备注串行
  - ✅ 删掉 3 个变成只写不读的死游标（`seq` / `vSeq` / `vcSeq`）
  - 换安全生成器（含 `Math.random()` 且回落分支不是下标，口径见 JC-6，**不复述**）
  - 🔴 已落库 `id: 1..N` **一律 grandfather 不重写**（改它等于换身份）；
    契约层声明 `legacy_ordinal_ids_grandfathered: true`
  - 🔴 反向自检：造一条 `id: 1` 的历史行，修复后重读 SHALL 仍是 `1`（被重写成新格式即打红）
  - 判据 SHALL 复现原缺陷：删中间一行再新增 ⇒ 后续行 id 左移、备注串行（修复前打红）

- [x] 12. family_b 四处修复（JN-P20）
  - ✅ 四处只改**回落分支**，保留「上游有 id 时优先用上游 id」语义
  - 🔴 **spec 漏记一条（真库实证）**：family_b 的回落**也已落库** ——
    `J3-2-variation` 288 B 的 `"id":1` 就是 `J3TabCheck` 的 `id: r.id ?? i + 1` 产生的。
    spec 只说「family_a 是唯一已有真实数据受影响」⇒ 若照它只对 family_a 做 grandfather，
    修 family_b 时会**重写那条 id = 换身份**。本轮 grandfather 策略对**两族一致**
  - 只改**回落分支**，保留「上游有 id 时优先用上游 id」语义
  - 判据 SHALL 覆盖真实回落情形：「render-config 种子派生的行尚未保存」「旧数据无 id」

- [ ]* 13. J2 侧披露层同口径复核 + 键 owner 边界（JN-P21 ~ JN-P23）
  - 🔴 **未完成**：本 Task 原文即标「修法标 `[ ]*`」—— J2 披露层 11 键 / J3 9 键的修法
    属**业务确认**（披露口径归会计准则判断），不在本 lane 可自行决定的范围
  - `J2TabDisclosureListed.vue`（**11 键**）与 `J2TabDisclosureSoe.vue`（**9 键**）
    按 JC-6 的 JD-7 四条风险**同口径复核**；🔴 **不复述** JC-6 正文；修法标 `[ ]*`
  - 断言 owner 是各子 Tab 的组件局部 `KEY` 对象（J2 **6 个** / J3 **3 个**）
  - 🔴 断言 `J2TabIndex.vue` 与 `J3TabIndex.vue` **无 `KEY` 对象**（只读 allResponses 算完成度）；
    登记 slice 首版把 `J3TabIndex` 列进 owner 清单**被守卫打红改正** ⇒ 「四个 Tab」是错的、**实为三个**
  - 🔴 断言**不冻结 J2/J3 键全集**（会造无消费方的死声明 = additive 即死代码）；
    只验两件事：真实形态 == 各 Tab 字面量 `KEY` · orphan 载体形态 `J3-${key}` ≠ 真实形态

### 阶段 3：JN-5 模板层登记

- [x] 14. 🔴 definedName 断链登记 + 不删（JN-P24 / JN-P25 / JN-P26）
  - ✅ 现算全部与 spec 一致：基线 `{J2: 37, J3: 502}` · 断链 `{30, 479}`（81% / 95%）
  - ✅ spec 列的 6 个跨循环残留样本**全部命中**，另发现 4 个
    （`_3余额表_一级_.dbf` / `fix2000.dbf` / `fixlj2000.dbf` / `zjgch2000.dbf`）
  - 🔴 **裸 IF 口径差异（本轮新发现）**：`审定表J2-1` 有 **12 格**含裸 IF，
    每格恰 **2 个嵌套 IF**（`=IF(AND(..),0,IF(AND(..),1,..))`）⇒ 按格数 **12**（spec 口径）、
    按出现次数 **24**（findall 口径）**两者都对**，但判据必须写明口径否则复核必对不上；
    J3 整册 **0** ✓。per-file 挂中性化
  - 清理仍标 `[ ]*`（属模板治理另一链路，不删 —— 删会让 `max_column` 内公式整片失效）
  - 基线 `{J2: 37, J3: 502}` + 🔴 **断链数 `{30, 479}`**（含 `#REF!`）+ 断言**不增长**
  - 🔴 逐条列 J3 的跨循环来源样本证明是复制残留：`_1固定资产数据库_筛选打印`(H) ·
    `_2其他资产_开办费除外_明细表`(K) · `_2、主要业务活动`(B) ·
    `_1、受本循环影响的相关交易和账户余额`(B) · `_.dbf` · `AS2DocOpenMode`
  - 🔴 **不删**（删会让 `max_column` 内公式整片失效），只声明「同步时不新增、不改写」；
    清理标 `[ ]*`（属模板治理另一链路）
  - 🔴 登记**比 I 循环严重一级**：I 只是「非 0」（I4 476 / I5 334，未查断链）；J 是「非 0 **且绝大多数断链**」
  - 裸 IF 落表 J2 **12**（全在 `审定表J2-1`）/ 🔴 J3 **0**（整册）；per-file 挂；整册统一挂 SHALL 打红

- [x] 15. J2/J3 模板几何登记（JN-P27 ~ JN-P32）
  - `明细表J2-2` r=90 c=14 f=221 merged=30 **六子区 ↔ 六键一一对应**（主表 R11-18 footer `=C13+C16-C17` /
    到期分析 R20-27 footer `=SUM(C22:C26)` 含预留空行 R26 / 设定受益计划情况 R30-47 🔴 **三级嵌套**
    R38 `=C39` → R39 `=SUM(C40:C42)` footer R47 `=C32+C33+C38-C43` / 计划资产 R49-61 footer
    `=C51+C52+C56+C60` / 精算假设 R63 起 / 敏感性分析末区）
  - 🔴 断言 **J2 与 J1 的 14 列语义逐字相同** ⇒ 接入时契约**可共用列映射**；有效列 14 ⇒ UUID 列 **15**
  - 🔴 `股份支付情况表J3-1` r=43 c=18 f=**7** —— 那 7 个公式**全是** R3/R4 的 `=底稿目录!A2`/`A3`
    ⇒ **整表零业务公式**；数据区 R20-27（R21=`以权益工具结算`，R22-27 空）· **无 footer** ·
    有效列 **14** vs max_column **18** ⇒ UUID 列 **15**
  - 🔴 断言 **J3 无审定表 + 无独立科目**（6 张 sheet 无 `审定表J3-*`；宿主 docstring 明写
    「费用端走 K8/K9，权益端走 M4，现金端走 J1」）⇒ 判据**不要求** J3 有 TB 发布门（要求即假红）
  - sheet 名：J2/J3 **无尾部空格**，**名中空格 3 张**禁 strip；
    🔴 `长期应付职工薪酬实质性程序表 L2A` 现算 **hidden**（slice 未记）且属 **L 循环**串册，登记不修
  - 干净点四项各 0（越界 / 宽表 / Excel Table / retired）按 JC-20 空分母纪律 + 变异证明

### 阶段 4：接入清单 + 复盘

- [x] 16. JN-6 接入前置清单 8 条（登记不执行，JN-P33 ~ JN-P36）
  - 八项逐条给现状与缺口（OO 挂载 0 / segmented + 二级门控 0 / 🔴 4 个 orphan **一个都不能接** /
    notice 0 / contract 0 且 **J2 列映射可共用 J1** / 🔴 **J3 不需要 TB 门** /
    🔴 `wp_guidance/J2.json` 缺失**登记不补** / 🔴 两份 render schema **已存在不重造**）
  - 🔴 显式登记给下一轮：**J2/J3 真库都有非空载荷**（J2 顶 `J2-2-dbp-status` 2731 B /
    `J2-soe-change` 2556 B；J3 顶 `J3-2-variation` 288 B）⇒ 将来成为 entry 时**满足 canary 硬标准**
    （与 J1 的 primary managed table 三键真库全空**相反**）
  - 登记子码解析反直觉：`J2-5..J2-10` / `J3-3..J3-10` 源模板无对应 sheet 但解析**仍返回册**
    ⇒ 接入判据**不得写**「解析非 None ⇒ sheet 存在」
  - 写路径与事件路径全清单落表（J2 五类 / J3 五类）

- [x] 17. 交接与复盘核验（不改代码，只核）
  - JC 引用闭合性：本 spec 的 `JC-\d+` 引用集合 ⊆ 地基 spec 的 `### JC-\d+` 定义集合，**无悬空**
  - 🔴 断言本 spec **无一条复述** JC 正文（只写编号 + 一句话用途）
  - 🔴 **交付边界表**核验：七项不交付各有理由；
    **「BP-1~BP-4 对本 lane 不是阻塞」已显式登记**（否则后来者会以为本 lane 也卡在平台供给上）
  - 「N 处」类表述与列举项数**逐条相等**（4 orphan / 8 与 4 个映射目标 / 5 处位置化 /
    六子区六键 / 8 条接入清单 / 三张名中空格 / 四项干净点）
  - 计数类要么现算要么标「现算值 + 禁写死阈值」；全文无 U+FFFD
  - 🔴 与地基 spec 对账：entry 归属不重不漏（本 lane **不含任何 entry_id**，只含两个非 entry 宿主路径）

## 阻塞项对齐

| BP / 事项 | 归属 | 本 spec 交付 |
|---|---|---|
| 🔴 **BP-1 ~ BP-4** | 平台级 | 🔴 **对本 lane 不是阻塞**（不发 contract 不注册 adapter）⇒ 本 lane 可立刻实施完 |
| **BP-6** 4 个 orphan dual-mode | **本 lane** | Task 3~7、9（两阶判定 + 映射表判据 + 违规直调 + 删除） |
| **BP-7** `useJ3FormData.ts` | **本 lane** | Task 8~9（整簇两层判定 + `forbidden_carriers` + 删除） |
| **BP-8**（non_entry 5 处） | **本 lane** | Task 10~12（真库实证 + grandfather + 回落分支修） |
| J2/J3 definedName 断链 | 本 lane 登记 | Task 14；🔴 **不删**，清理标 `[ ]*` |
| J2 侧披露层 49 硬编码 id 同型 | 本 lane 复核 | Task 13；修法 `[ ]*`（涉用户可见披露口径） |
| `wp_guidance/J2.json` 缺失 | 本 lane 登记 | **不补**（J2 不是 entry） |
| 跨循环串册 `L2A` | 本 lane 登记 | Task 15；不修 |
| 接入前置清单 8 条 | 本 lane 交付清单 | Task 16（**登记不执行**） |
| BP-5 / BP-9 / BP-10 / BP-11 | **地基 spec** | 不在本 lane |
| JC-4 / JC-5 / JC-8 / JC-9 / JC-12 / JC-18 / JC-19 | **地基 spec**（全是 J1 的形态） | 🔴 与本 lane 无关 |
