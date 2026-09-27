# Implementation Plan

## Overview

**spec**：`j-cycle-sync-foundation-and-first-canary`　**创建**：2026-09-26　
**状态**：0/28（Task 0~27），Design-First 未实施

**上游**：umbrella Task 52（J slice 181,051 B + 守卫 `test_task52_j_cycle_migration.py` +
🔴 **已有变异注入脚本** `backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py`）·
FC-1~FC-13 · GC-1~GC-10 · HC-1~HC-16 · IC-1~IC-20。

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

🔴 **本 spec 是下游 lane 的共同前置**：JC-1~JC-20 在此裁一次，
`j2-j3-non-entry-hosts-and-orphan-cleanup` 只引用不复述。canary 只做 **`J1-6-short-term`**。

🔴 **不得修改 `backend/wp_templates/` 字节**。
🔴 **不得手改 `backend/data/workpaper_sync_entry_manifest.json`**（只走 `register_from_manifest()`）。
🔴 **不得修改 `backend/data/workpaper_sync_migration_paradigm.json` 的任何字节**。
🔴 **不重造已有产物**：149 KB 级守卫 · **变异注入脚本** · `workpaper_sync_j_cycle_deletion_plan.json` ·
三份 render schema（j1/j2/j3）· J1 四个后端策略文件 · `wp_guidance/J1.json`。

## Tasks

### 阶段 0：前置门 + 红判据（先打红）

- [x] 0. 前置依赖与已有产物清点（`git show HEAD:` 判定，不读工作树）
  - 核 `RowTableSheetSpec` · `StoreMergePlan.oo_crash_neutralization_fn` ·
    `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` **函数体**（历史坑：调用点在 HEAD
    但函数体曾从未落地）
  - 🔴 清点并**声明复用**：`test_task52_j_cycle_migration.py` 的四个 Test 类 ·
    `mutate_task52_j_cycle_migration_guards.py`（本 spec 全部「为 0」断言的变异证明都用它，**不新写**）·
    三份 render schema · J1 四个 `wp_render_strategies/_j1_*.py`
  - 登记 `wp_guidance/J2.json` **缺失**（J2 不是 entry ⇒ 登记不补）
  - 证据 `evidence/task0-prerequisites.md`

- [x] 1. 🔴 现算复核三类结论（JF-P1 / JF-P2 / JF-P3，先打红）
  - **（A）结构性零反驳**逐项重算：3 模板 sha256/size/sheets · 4 orphan 行数 41/37/35/39 ·
    共享基类 65 行 / localStorage 0 / statement 边 29 / J 贡献 3 · `useChecklistPersistence` 边 23 ·
    第二写路径 7 文件 8 站点 · owner 常量实值 · 8 guessed key 各 0 ·
    family_a 1 / family_b 6 · `severance.defaultRows` 恰 1 行空 label
  - 🔴 **（B）六处快照必须重算**：manifest **155**（slice 写 186）· 契约目录 **18**（slice 记 5）+
    `DELIVERED_PER_ENTRY_CONTRACTS` **21** + `adapter_registered=True` **5** `{d2,d4,g7,h1,d1}` ·
    共享基类宽口径 **34** 且差集 **5 个**（slice 记 30/1）· Notice 消费方 **48**（slice 记 41，J 域仍 0）·
    行号 · `useJ2FormData.ts` **已删**
  - 🔴 **（C）五处实质反驳**逐条落：①J1 **有** TB 发布门（端点判定）②写路径**六类端点**
    ③OCR **命中** ④披露层 **8 拼接键**不在 TK 清单 ⑤BP-11 是 **4 文件 5 处**
  - 🔴 判据一律**按常量名/形态/端点字面量定位，禁写死行号**；变异「用 slice 行号锚定」SHALL 打红
  - 证据 `evidence/task1-recompute.md`（逐项「slice 声明值 vs 现算值」两列，不符标 `STALE`）

- [x] 2. 四类「查过且没有」+ 🔴 一处扫描误报复核（JF-P4 / JF-P5 / JF-P6）
  - 无 pilot（逐文件读 `review.entry_id`，**不是数个数**）· 无 J0（两函数返 None + 模板恰 3 本）
  - J 完全自闭**两侧都验**（J 键无非 J 消费 ∧ J 文件无非 J 键）⇒ HC-8 / IC-17 不命中
  - 🔴 但登记**端点跨循环复用 1 处**：`useJ1VoucherOcr.ts` 调 D4 的 `/{wpId}/d4/contract-ocr`
  - 🔴 **扫描误报复核**：`附注披露信息（国有企业）!B29:E29` 命中 4 格，逐格核验
    （R19 是 `=SUM(B20:B23)` 小计、R20:R23 是明细 ⇒ 全区加总再减明细正好抵消重复）
    ⇒ 判定**非缺陷**并如实登记「命中 4 格、核验后非缺陷」；只看命中数会造 4 个假缺陷

- [x] 3. 零回归基线现算（JF-P43，GC-10）
  - 现算契约目录 `*.json` 个数与**文件名集合** · `DELIVERED_PER_ENTRY_CONTRACTS` 条数与 entry_id 集合 ·
    `adapter_registered=True` 集合 · `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员
  - 🔴 **禁写死个数**；实质断言 SHALL 是「逐文件读 `review.entry_id` 无一条以 `xlsx/j` 开头」

### 阶段 1：JC-1 ~ JC-20 裁决落地（本 spec 的核心交付）

- [x] 4. JC-1 manifest 口径 + BP-9 根因 + 迁移路径
  - 现算七字段落表；登记 slice 的 `capability=null` / `capability_target=bidirectional` /
    `mount_count=1` 都是 **slice 裁决值或自算值，manifest 里无对应字段或值不同**
  - 断言根因 = overlay `defaults_by_component.GtOnlyOfficeSheet`（对所有挂 OO 的 entry 一律给默认值）
  - 迁移只走 `register_from_manifest()`，🔴 **禁手改 manifest**

- [x] 5. JC-2 载体族第三种 + 🔴 两条对照反证（JF-P7）
  - `shared_platform_persistence_adapter` 落表：`useChecklistPersistence.ts` ·
    client **`api` from `@/services/apiProxy`** · 边现算 23 · 端点 `PUT …/checklist-responses`
  - 🔴 **反证 ①** 让 H 版守卫「载体里必须有 `http.put`」在本适配器上**打红**（它用 `api.put`）
  - 🔴 **反证 ②** 让 I 版守卫「宿主必须 import `@/utils/http`」在 J1 宿主上**打红**
    （现算宿主 `@/utils/http` 与 `apiProxy` 命中**均为 0**）
  - 判据 SHALL 按 entry 声明的 `write_client` 名字找 `{client}.put(`，不写死 `http`

- [x] 6. 🔴 JC-3 写路径按端点字面量 + 发布门非空反证（JF-P8 / JF-P9 / JF-P10）
  - 六类端点逐条现算落表（checklist-responses **11** / publish-to-tb **1** /
    disclosure-notes/sync-from-workpaper **4** / events/publish **4** /
    cross-wp-references/batch **1** / ai/generate-text **15**）
  - 🔴 **非空反证**：断言符号名 `publishToTb` 全 J 域命中 **0** 而端点命中 **1**
    ⇒ 「按函数名判定得 0、按端点判定得 1」是本条判据存在的全部理由
  - 断言 **GC-9 在 J 是 1/1 有门**（推翻「J 无发布门」的误判）
  - 第二写路径 **7 文件 / 8 站点**两个数**分别现算**（混用会让「7 还是 8」说不清）
  - `useAdjustmentCentralSync` **2 处**（J3 无）⇒ **2/3**；OCR 在 composable 层命中 ⇒ FC-8 **命中**

- [x] 7. JC-4 一表三键 + 🔴 BP-11 五处真源（JF-P11 / JF-P12）
  - 三键派生落表（`STORAGE_KEY_PREFIX` + `storageKey()` + `J1_SECTIONS[].key` 三值）；身份字段 `id`
  - 🔴 **五处真源同时比对**：`useJ1Detail`(派生) · `useJ1Adjudication.J1_DETAIL_SECTION_KEYS` ·
    `J1TabAccrualCheck.DETAIL_KEYS` · `J1TabAllocationCheck.DETAIL_KEYS` ·
    `useJ1DisclosureSections` 三处 `readJson` 内联
  - 🔴 变异「只改前缀不改四处字面量」SHALL 打红（当前五处逐字一致但是**五份真源**）
  - 同型多真源一并登记：`J1-1-rows` 2 处 · `J1-3-adjustment-rows` 同文件 2 处 · `J2-3-entries` 同文件 2 处

- [x] 8. 🔴 JC-5 拼接键解析 + 三命名空间分清（JF-P13 / JF-P14 / JF-P15）
  - 披露层 **8 键**由 `prefix × 4 后缀` 笛卡尔积展开后验；断言完整字面量 grep **抓不到**
    （这正是 slice 自己 `forbidden_shortcuts` 第 1 条警告的坑，slice 在披露层踩了它）
  - 真库载荷佐证：`J1-disc-soe-short-term` 1325 B / `-post-employment` 917 B /
    `-summary` 532 B / `-notes` 118 B
  - 🔴 三命名空间落表并断言**互不混用**：`J1-disc-*`（持久化 8）/ `J1-disclosure-*`
    （`section-id` + `progressKeys`，**非持久化** 10）/ `j1-disclosure-*-${aiSection}`（小写 AI 2）
  - 登记披露层缺口：有 `J1-disclosure-listed-severance` section-id 但**无对应持久化键**

- [x] 9. 🔴 JC-6 行身份五族 + JD-7 + JD-8（JF-P16 ~ JF-P20）
  - 五族现算落表（A 1 / B 6 / C 3+1 / D 3 / E 0）；C·D 两族**反向断言不被点名**
  - 🔴 family_c 判别式**放宽**：含 `Math.random()` 且回落分支不是下标 ⇒ 安全
    （收纳 `useJ1DisclosureSections` 的纯 random 一处）
  - 🔴 但**严格性不能丢**：断言 `genId(idx)` 那种 `??` 左支给下标的形态**仍判 B 族**；
    变异「只看含 random 即判安全」SHALL 让最严重那条被洗成 C 族而打红
  - 🔴 **JD-7 披露层 49 个硬编码 id 登记但不判缺陷**（SOE 25 + Listed 24）；
    理由：id 与 label 同在一个对象字面量、绑定静态 ⇒ 报成位置化会造 49 个假缺陷；
    变异「把它们报成位置化」SHALL 打红
  - 🔴 落**四条真实风险**：①同 id 跨变体语义不同（`st-7` 一边「其他」一边「住房公积金」）
    ②两侧行数不同（SOE summary 5 / Listed 4）③新增行 `${category}-${Date.now()}` 与骨架 `st-N` 混形态
    ④`s-${Date.now()}` **无随机串**（同毫秒撞 id）
  - entry/non-entry 缺陷维度 **2 + 5 = 7** 两组数**分别现算分别登记**

- [x] 10. JC-7 removeRow 四种签名形态（JF-P21）
  - **8 处 / 4 形态**落表（单参 `id` 3 / 单参 `rowId` 1 / 双参 `(id, category)` 2 /
    双参参数顺序相反 2）
  - 契约字段 SHALL 是 `{kind, arity, param_order}` **三元组**；
    变异「沿用 H/I 的单值枚举 `row_delete_api_kind`」SHALL 因装不下双参而打红
  - 🔴 登记 **J 无下标族**（H/I 都有）⇒ 判据不得与 H/I 复用同一签名断言

- [x] 11. 🔴 JC-8 五条 RD 三边比对 + RD-5 新增（JF-P22 / JF-P23）
  - 先登记 slice 覆盖面缺口：**RD-1~RD-4 全部只对 `明细表J1-2 `**，四张检查表零声明
  - RD-1 **20/20** 正例锚点（含 5 个边界格 `A11`/`B11`/`B12`/`A33`/`B33`）
  - RD-2 **2/8**：两类差异**分开计数**（真标签 1 处「少一个费」+ 分隔符 5 处全角 `．`）
  - RD-3 否定式双向断言（源 `B50:B52` 真读全 None **且** impl 恰 1 行空 label）
  - RD-4 双向锁死（第二份 impl 与三个真源一致 ⇒ 缺陷定位在第一份单一处；
    把带「费」那份改成不带费也 SHALL 打红）
  - 🔴 **RD-5（新）**：`SHORT_TERM_DEFAULTS` **19 项** vs `计提情况检查表J1-6!A17:A35`
    ⇒ **行数 19/19 一致但 10 处内容不等**，三类分开记：
    ①②分隔符 + 缩进 **9 处**（模板全角 `．` + 3 个全角空格 U+3000；impl 半角 `.` 无前缀）
    ③🔴 **单元格内换行符 1 处**（模板 `八、辞退福利\n（因解除劳动关系给予的补偿）`）
  - 🔴 登记**同一张 sheet 内两分区缩进字符不同**（第 1 区全角空格 / 第 2 区 4 个半角空格）
    ⇒ 判据不能用统一 strip 规则，须逐格字节比对
  - 修法标 `[ ]*`（业务确认改哪一侧）

- [x] 12. JC-9 禁归一化 + JC-10 sheet 名禁 strip（JF-P24 / JF-P25）
  - 🔴 变异「比对前 `NFKC` 归一」SHALL 打红（会同时洗掉 RD-2 的 5 处与 RD-5 的 9 处）
  - 三类空格落表（尾部 2 / 名中 6 / 跨 sheet 引用 `='明细表J1-2 '!C13` 带空格 + 单引号）
  - 变异「strip 后匹配」SHALL 打红
  - retired 四向等值比对（`sheet_count == len(sheetnames)` · `retired == len(list) == 现算` ·
    `business == 23 − 7 − 1 = 15`）+ 登记 **retired 7 张全 hidden**

- [x] 13. JC-11 变体轴 2 组 + 跨循环串册（JF-P26 / JF-P27）
  - 🔴 `J1-10` **一码两义**落表（`辞退福利检查表J1-10` visible 48 行 /
    `股份支付检查表J1-10-删除` hidden 66 行，标题行逐字不同业务）
  - 判据按尾码定位 SHALL 带 **visible 过滤**；变异「只按尾码匹配」SHALL 取到两张而打红
  - 登记跨循环程序表串册 **2 处**：`应付职工薪酬实质性程序表 L1A-原`（🔴 **slice 漏记**）+
    `长期应付职工薪酬实质性程序表 L2A`（现算 hidden，slice 未记）

- [x] 14. JC-12 footer 三形态 + 🔴 幽灵行（JF-P28 / JF-P29）
  - `明细表J1-2 ` 三 footer 分别标（R33 跳跃 `=SUM(C13,C19:C20,C25:C31)` / R46 加法 `=C42+C37` /
    R53 连续 `=SUM(C50:C52)`）；`审定表J1-1 ` 同样三形态
  - 变异「照单一 SUM 口径验」SHALL 假红
  - 🔴 **幽灵行 R45** 显式排除断言（A/B/C 全空但有 `F45==C45+D45-E45`）；
    变异「按有公式即业务行」SHALL 把 8 行算成 9 行而打红
  - 判据按 **B 列非空**判 `明细表J1-2 ` 的业务行

- [x] 15. JC-13 definedName 断链 + JC-14 裸 IF（JF-P30 / JF-P31）
  - 基线 `{J1:0, J2:37, J3:502}` + 🔴 **断链数 `{—, 30, 479}`**（含 `#REF!`）+ 断言**不增长**
  - 登记 J3 的 502 个是**跨循环复制残留**（`_1固定资产数据库_筛选打印` /
    `_2其他资产_开办费除外_明细表` / `_.dbf` / `AS2DocOpenMode` 等）⇒ **不删**，只声明同步不新增不改写
  - 裸 IF per-file `{132, 12, 0}` 总 **144**；J1 内部 56/60/16；变异「整册统一挂」SHALL 打红

- [x] 16. 🔴 JC-15 BP-10 无声失败三要素（JF-P32）
  - 断言 notice 挂载 0 + 文案真源引用 0 + `isOoAvailable` 宿主命中 **0** + `仅结构化视图` tag 1
  - 🔴 登记它**比 I2 更差**：共享基类 `switchMode` 只在运行时 `return` ⇒ 用户点了**没反应**（无声失败），
    比 AC 1.5 要求的「不显示不可兑现的按钮」更差
  - 🔴 判据 SHALL **先按 toolbar class `j1-dual-mode-bar` 截出区块再看** ——
    全文件 grep `el-segmented` 会命中 `J1TabGeneralCheck` 与 `J2TabAdjudication` 两处 Tab 内部分段控件而误判

- [x] 17. 🔴 JC-16 伪消费边判据改 + JC-17 自闭与端点复用（JF-P33 / JF-P5）
  - 现算宽 **34** / 窄 **29** / 差集 **5 个**；判据改「差集**包含** `workpaperSyncLegacyBaseline.generated.ts`」
    + 现算差集清单；🔴 **禁写死「差集恰是 1 个」**
  - 🔴 **窄口径判别规则必须保留**：匹配点所在行、之前的未转义双引号个数为奇数 ⇒ 落在字符串内 ⇒ 不是语句；
    变异「去掉该规则」SHALL 因那 5 处 JSON snippet 而打红
  - J 完全自闭两侧断言 + 端点跨循环复用 1 处登记（冻结对象从「键」换成「**端点**」）

- [x] 18. JC-18 derived_total 现算 + JC-19 prefill 四缺陷（JF-P34 ~ JF-P36）
  - `derived_total_keys` 现算 **7 个**；🔴 正则须覆盖 **`-total-` 中置**形态
    （只写 `total$` 得 4 个，漏 `J1-7-total-*` 三个）；禁写死阈值
  - 键全集现算 **160 条**（全平台单循环最多），禁写死
  - prefill 四处缺陷逐条登记：①`审定表J1-1` **缺尾部空格** ②`明细表J1-2 ` 那条 `cells: []`
    ③`=PREV('J1','分析程序J1-3','审定数')` 引用**不存在的 sheet** ④J3 一条 `wp_name=股份支付审定表`
    但 **J3 册无审定表**；修法标 `[ ]*`

- [x] 19. 🔴 JC-20 空分母纪律 + 复用变异脚本（JF-P37 / JF-P38 / JF-P44 / JF-P45）
  - Property 3 / 20 / 69 三条明确标 `not_claimed_passing`；Property 70 真验并宣称通过
  - 七项「查过且为 0」一律写「**现算 0 且不是漏扫**」：`family_e` / 跨循环键引用 /
    `hardcoded_scan_result` 六模式 / 越界引用 / 宽表 / Excel Table / localStorage
  - 🔴 **复用** `mutate_task52_j_cycle_migration_guards.py` 逐条证明非空跑，**不新写变异脚本**
  - 🔴 **FC-3 在 J 是单射不满射**：判据验「单射 + 每个 `belongs_to_entry: null` 带 `excluded_reason` +
    有主那条真命中 entry_id」；变异「写死双射」SHALL 假红、「写死多对一」SHALL 放过夹带跨循环模板
  - 登记 template_resolution_audit 的三条反直觉（`J1A`/`J2A`/`J3A` 无独立索引条目 · `J0` 返 None ·
    🔴 `J2-5..J2-10`/`J3-3..J3-10` 解析返册但 sheet 不存在 ⇒ 判据不得写「非 None ⇒ sheet 存在」）

### 阶段 2：canary `J1-6-short-term` 端到端

- [x] 20. canary 真库前置实证 + 硬标准口径改写（JF-P39）
  - 🔴 先断言 **D~I 硬标准在 J 不成立**：`J1-2-detail-*` 三键 + `J1-1-rows` + `J1-3-adjustment-rows`
    真库**全无行**（现算）
  - 硬标准改四项：真库有非空载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组
  - 现算断言 `J1-6-short-term` **3473 B**（全 J 最大）；J 前缀 item_id 有行 **83 个**、
    每键 rows=1、`conclusion` **83/83 全 NULL**、**31 个键 remark 为空串**
  - 四候选裁决表落地（含否决理由）
  - 🔴 若非空断言失败 THEN canary 选型失效，回 Task 20 重选，**不得造数据顶上**
  - 证据 `evidence/task20-canary-db-evidence.md`

- [x] 21. 🔴 RD-5 先补三边校验（canary 前置，JF-P23）
  - 在写契约**之前**完成 `SHORT_TERM_DEFAULTS` 19 项 vs `计提情况检查表J1-6!A17:A35` 的逐格比对
  - 三类差异分开落表（分隔符 + 缩进 9 / **换行符 1**）；否则 canary 的 representation
    会把错标签固化进契约
  - 修法标 `[ ]*`（业务确认）；本 Task 只交付判据 + 差异清单

- [x] 22. canary 契约 + representation + provider（JF-P40 / JF-P41）
  - ✅ **2026-09-27 已交付**（provider + 契约 + 台账三件同时落地，走正确生成路径）：
    - provider 主模块 `backend/app/services/workpaper_sync/phase5_j1_employee_compensation.py`
      + sheet 层薄声明 `phase5_j1_06_accrual_check.py`（复用 `phase5_h_cycle_common` 骨架，
      实测零 H 硬编码 ⇒ 不为 J 另造一份公共层）
    - 生成器 `backend/scripts/gen/generate_phase5_j_contracts.py`（登记表驱动，新增 entry 只加一行）
    - 🔴 契约**由 `build_contract_payload()` 生成并经 `parse_contract` schema 门后写盘**，
      不是手写（手写会被 `test_task13` 的契约目录↔台账双向锁打红）
    - 台账条目追加进 `adapters/delivered_contracts_ledger.py`（第 32 条）
    - 实测产出：fields **8** / header_rows **2** / `formula_mask` = `G17:G35` + `I17:I35` /
      `footer_anchor` 解析为 **None**（对应 `footer_rows: []`）/ 行身份 `/rows/*/id` /
      `canonical_digest = 299c3383…0339` / json 26 003 B
  - 🔴 **附带修 3 条被 slice 冻结守卫锁死的假红**（口径升级，非放宽）：
    `test_task52::test_no_pilot_contract_belongs_to_the_j_cycle` ·
    `test_task52::test_no_slice_entry_has_a_contract` ·
    `test_task51::TestProperty20And21NotClaimed`（后者按其 docstring 原定指示
    「发了契约就在此补齐字段级判据」补了 5 条字段级判据：台账登记 + schema 门 + 非空壳
    + `row_identity` 存在 + 每字段有 `source_ref`）。
    三条原先写死「本循环起点零契约」= 盘点期快照，交付契约正是 spec 目的 ⇒ 改为
    「**未经平台交付台账登记的契约才打红**」（同 GC-10「基线现算不写死」）。
    🔴 变异仍有效：绕过 provider 手写契约 → 打红；台账 entry_id 与契约不符 → 打红；
    把 `adapter_registered` 改 True 冒充完工 → 由 `test_no_slice_entry_has_a_registered_adapter` 打红
  - 🔴 **Property 20/21 仍不宣称通过** —— 它们要 roundtrip + 人工审核（卡 BP-1~BP-4 无真 OO 9.4）；
    契约属发布链第①环，台账如实记 `adapter_registered=False`
  - 产出 `backend/data/workpaper_sync_contracts/j1.accrual_check_short_term.json`
    （字段见 design §契约）
  - `provider_id = phase5_accrual_check_short_term`（`phase5_*` 范式，**不照** `pilot_*`）
  - `source_ref` 只 `{workbook_sha256, sheet_name: "计提情况检查表J1-6"}`，🔴 **禁 wp_index 字段**
  - 几何现算：表头 **R15/R16 两级** · 分区标题 R14 · 数据区 **R17:R35（19 行）** ·
    🔴 **`footer_rows: []` 本 sheet 无 footer 合计行** · 第二分区 R37/R38/R40-47 ·
    有效列 **11**（== max_column）· UUID 列 **12** · 🔴 **本 sheet 裸 IF 0**
  - 列语义：A 项目 / C-E 计提基数[名称,金额,索引] / F 计提比例 / G 应提金额 `=ROUND(D*F,2)` /
    H 实际计提数 / I 差异 `=G-H` / J 差异原因 / K 结论
  - `row_delete_api = {kind:"identity", arity:1, param_order:["id"]}`（JC-7 三元组）
  - 🔴 `sibling_shapes` 三值区分：`J1-6-post-employment` = `structured_row_array` ·
    **`J1-6-questions` = `free_text_array`**（5 元素，首元素是含 `###` 的 AI markdown 长文）·
    `J1-6-conclusion` = `free_text_scalar`
  - `live_payload_flag = skeleton_persisted_no_business_values`（3473 B 但金额字段全 0）
  - `payload_column_mode = remark_only` 标 `verified_in_live_db`（真库 83 行 conclusion 全 NULL）
  - `tb_publish_gate` 记端点 + `symbol_name_hit_count: 0`（JC-3 非空反证）
  - `cross_cycle_endpoint_dependency: ["POST …/d4/contract-ocr"]`（JC-17）
  - 走 `register_from_manifest()` 注册；注册后 `capability` 才由 `single_onlyoffice` 变 `bidirectional`
  - 注册后重跑 Task 3 基线：契约目录 +1、`DELIVERED_PER_ENTRY_CONTRACTS` +1

- [ ]* 23. 🔴 BP-10 首处 notice 挂载 + 补二级门控（JF-P32）
  - 🔴 **回滚原因（2026-09-27 复盘）**：notice + 二级门控被 test_task52 AC14 守卫锁死（声明 notice_mounted=False / second_level=None）
  - 挂载点在 `class="j1-dual-mode-bar"` 区块内；文案真源 SHALL 是 `workpaperEntrySyncNotice.ts`，
    🔴 **禁在宿主硬编码中文**
  - 给 `el-segmented` 补 `v-if="dualMode.isOoAvailable.value"` 二级门控
  - 🔴 判据先按 toolbar class 截区块再看；变异「全文件 grep `el-segmented`」SHALL 因命中
    `J1TabGeneralCheck` / `J2TabAdjudication` 两处 Tab 内部分段控件而误判、打红
  - 反向自检：模拟 OO 探测失败，断言切换器**不显示**（而不是「显示但点了没反应」）

- [ ]* 24.* 两轮 roundtrip 实证（JF-P42，依赖 BP-4 真 OO 9.4 场景集）
  - 🔴 **未完成（2026-09-27 核实）**：本 Task 自身写明「`evidence.sync_test_run_id` 须来自真 OO 栈，
    **不得** mock 充数」，而平台无真 OO 9.4 场景集（BP-4）⇒ 两轮 roundtrip 一轮都跑不了。
    provider + 契约已交付（Task 22），台账如实记 `adapter_registered=False`；
    `RegistryReport.contract_files_without_adapter` 持续报这笔欠账。
  - 六条前置断言（design §roundtrip 前置断言）：①只经声明的 `write_carrier` 且
    `J1TabAccrualCheck.vue` **不在**第二写路径 7 文件清单里 ②冻结 `useAdjustmentCentralSync`（J1 侧 1 处）
    ③排除 `derived_total_keys`（现算 7 个）④不改任何键名（尤其 `J1-2-detail-*` 与 `J1-disc-*`）
    ⑤🔴 数据区按 **A 列非空**判、**不得套 `明细表J1-2 ` 的「B 列 + 三 footer」口径**
    ⑥🔴 **两轮**：第一轮真库 3473 B 只验结构 · 第二轮**合成带金额载荷**验 `G=ROUND(D*F,2)` 与 `I=G-H`
  - 🔴 `evidence.sync_test_run_id` 须来自真 OO 栈，**不得** mock 充数

- [x] 25. TB 发布链（canary 直接覆盖，JF-P9）
  - 前置登记：J 是 **1/1 有门**（按端点判定）⇒ 发布链**不外移首例**
  - 断言只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 必经二次确认
  - 🔴 断言**禁**在 `watch` / `onMounted` / debounce 回调内发布；
    **复用**平台既有 2 道 CI 守卫（`check_tb_writeback_no_direct_call` /
    `check_tb_publish_confirm_gate`），**不重造**
  - 反向自检：把发布调进 `watch` SHALL 被守卫打红
  - 🔴 登记模板侧对应：`审定表J1-1 ` 有 R42「试算平衡表数」/ R43「差异数」`=D22+D34+D41-D42`

- [ ]* 26.* 人工审核契约与 approved bundle（依赖 BP-2 / BP-3）
  - 🔴 **部分完成（2026-09-27 核实）**：per-entry contract 已交付（Task 22，`review.entry_id`
    = `xlsx/j1/gt-j1-employee-compensation`，`test_task52::test_no_pilot_contract_belongs_to_the_j_cycle`
    逐文件读该字段并与台账比对）；但**人工审核与 approved bundle 未完成** ——
    卡 BP-2（人工审核契约链路）+ BP-3（approved bundle）两个平台级缺口。
    ⇒ 契约的 `review_status` 只到 `reviewed`，没有 approved bundle。
  - 产出第一条 `review.entry_id` 为 `xlsx/j1/gt-j1-employee-compensation` 的 per-entry contract
  - 🔴 判据是「逐文件读 `review.entry_id`」**不是数契约个数**
  - 🔴 契约必须**同时覆盖多条写路径**（JC-3 六类里属持久化的 ①②③），抄别人的模板一定漏

### 阶段 3：交接给下游 lane

- [x] 27. 交接清单核验（不改代码，只核）
  - ✅ **2026-09-27 重新现算核验通过**：design 标题定义 **JC-1~JC-20 共 20 条**；
    两份 J spec（本 spec + `j2-j3-non-entry-hosts-and-orphan-cleanup`）各引用全 20 条；
    **悬空引用 0** · **定义未被引用 0** ⇒ 引用闭合。
    tasks.md 现状 **25 `[x]` + 3 `[ ]*`**（22 已交付转 `[x]`；23/24/26 三条外部依赖如实留 `[ ]*`），
    合计 28 与 spec 声明一致。
  - JC-1~JC-20 全部有 design 正文 + 判据；下游 lane **无一条复述** JC 正文（复述即漂移）
  - 脚本核 JC 引用闭合性：`### JC-\d+` 定义集合 == 两份 spec 全部 `JC-\d+` 引用集合，**无悬空**
  - entry 归属：本 spec 恰为 `xlsx/j1/gt-j1-employee-compensation` +
    `xlsx/j1/inspection/j1-tab-general-check`（parent_duplicate）；一律写 entry_id 全名
  - 逐条确认后置项归属：
    **下游 lane `j2-j3-non-entry-hosts-and-orphan-cleanup`** ← BP-6（4 个 orphan dual-mode）·
    BP-7（`useJ3FormData.ts`）· non_entry 的 5 处位置化 · J2 37 / J3 502 definedName 的处置 ·
    J2 六 Tab / J3 三 Tab 的 KEY 对象 · 披露层 49 硬编码 id 的 J2 侧同型
    **本 spec** ← BP-5 · BP-8（entry 内 2 处 + RD-2/RD-4/RD-5）· BP-9 · BP-10 · BP-11
  - 断言「N 处」类表述与列举项数**逐条相等**（六类端点 / 五处真源 / 八拼接键 / 五族 / 8 处 4 形态 /
    五条 RD / 三类空格 / 2 组变体轴 / 三 footer / 七项为 0 / 四处 prefill 缺陷）
  - 计数类要么现算要么标「现算值 + 禁写死阈值」；全文无 U+FFFD

## 阻塞项对齐

| BP | 归属 | 本 spec 交付 |
|---|---|---|
| BP-1 ~ BP-4 | 平台级（全循环共有） | 只标 `[ ]*`，不承诺 |
| **BP-5** 写路径多轨 | 本 spec | JC-3 六类端点表（🔴 实测**六类**不是 slice 的「双轨」） |
| **BP-6** 4 个 orphan dual-mode | **下游 lane** | 不在本 spec（全在 J2/J3 侧） |
| **BP-7** `useJ3FormData.ts` 死代码 | **下游 lane** | 不在本 spec（`useJ2FormData.ts` 已被物理删除） |
| **BP-8** 行模型 / 行身份 | 本 spec（entry 内 2 处 + RD-2/RD-4/**RD-5**）+ 下游 lane（non_entry 5 处） | Task 9 / 11 |
| **BP-9** manifest capability | 本 spec | JC-1 全文 + Task 4 |
| **BP-10** AC 1.4 未兑现（无声失败） | 本 spec | JC-15 + Task 16 / 23 |
| **BP-11** 传输键多份真源 | 本 spec | 🔴 JC-4（**4 文件 5 处**，非 slice 的两份）+ Task 7 |

**本轮新增登记（slice 未覆盖）**

| 事项 | 归属 | 状态 |
|---|---|---|
| **RD-5** J1-6 骨架 19 项 10 处差异（含**换行符**一类） | 本 spec | 判据交付；修法 `[ ]*` |
| 披露层 **8 个拼接键** | 本 spec | JC-5 判据交付 |
| 披露层 **四条真实风险** | 本 spec | 登记；修法 `[ ]*`（涉用户可见披露口径） |
| **prefill 四处缺陷** | 本 spec | 登记；修法 `[ ]*`（另一条产品链路） |
| `J1-10` **一码两义** | 本 spec | JC-11 visible 过滤判据；不改模板字节 |
| 跨循环串册 2 处（`L1A-原` / `L2A`） | 本 spec | 登记不修 |
| 端点跨循环复用（D4 OCR） | 本 spec | JC-17 登记 |
| `wp_guidance/J2.json` 缺失 | 下游 lane | 登记不补（J2 不是 entry） |
| 扫描误报复核（`附注披露信息（国有企业）!B29:E29`） | 本 spec | Task 2 如实登记「命中 4 格、核验后非缺陷」 |
