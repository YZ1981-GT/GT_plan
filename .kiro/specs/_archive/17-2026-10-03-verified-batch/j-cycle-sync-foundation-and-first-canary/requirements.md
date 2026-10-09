# Requirements Document

## Introduction

本 spec 是 **J 循环（职工薪酬）地基 spec**，覆盖唯一一条独立 entry
`xlsx/j1/gt-j1-employee-compensation` 与它的 parent_duplicate 子入口
`xlsx/j1/inspection/j1-tab-general-check`，承载 **JC-1 ~ JC-20 共同裁决**，
并交付**首张 canary（`J1-6-short-term`，计提情况检查表J1-6）**。

🔴 **J 是 D~I 七轮里与前六轮形态差异最大的一轮**：
**3 个可达宿主 + 3 本权威模板，但 source manifest 里只有 1 条独立 entry** ——
只有 J1 宿主挂了 `GtOnlyOfficeSheet`。J2 / J3 宿主在产品上可达（`htmlRendererRegistry` 有真模块边）
但 OO 侧无入口，因此不是 manifest entry ⇒ 它们连同 4 个 orphan dual-mode 归下游 lane spec。

**上游**：umbrella Task 52（J slice + 守卫 `test_task52_j_cycle_migration.py` +
🔴 **已有变异注入脚本** `backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py`）·
FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`）·
GC-1~GC-10（`g-cycle-sync-foundation-and-first-canary/design.md`）·
HC-1~HC-16（`h-cycle-sync-foundation-and-first-canary/design.md`）·
IC-1~IC-20（`i-cycle-sync-foundation-and-first-canary/design.md`）。

🔴 **JC-1 ~ JC-20 在本 spec 裁一次，下游 lane 只引用不复述**（复述即漂移）。

**不重造已有产物**：
`backend/tests/workpaper_sync/test_task52_j_cycle_migration.py`（含 `TestOrphanDualModeInventory` /
`TestTransportKeyResolution` / `TestParadigmCompliance` / `TestAc14HonestModeVisibility`）·
🔴 `backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py`（变异注入，**直接复用**）·
`backend/data/workpaper_sync_j_cycle_deletion_plan.json` ·
`backend/app/data/wp_render_schema/j1-employee-compensation.yaml`（另有 j2/j3 两份）·
`backend/app/routers/wp_render_strategies/_j1_employee_compensation.py` · `_j1_import_export.py` ·
`_j1_ai_generate.py` · `_j1_disclosure_import_export.py`（**J1 四个后端策略文件**）·
`backend/data/wp_guidance/J1.json`（🔴 **`J2.json` 缺失**，登记不补 —— J2 不是 entry）。

🔴 **不得修改 `backend/wp_templates/` 字节**。
🔴 **不得手改 `backend/data/workpaper_sync_entry_manifest.json`**（只走 `register_from_manifest()`）。
🔴 **不得修改 `backend/data/workpaper_sync_migration_paradigm.json` 的任何字节**（守卫用 digest 双向锁死）。

## 范围：1 条独立 entry + 1 条 parent_duplicate 子入口

| 项 | 值 |
|---|---|
| entry_id | `xlsx/j1/gt-j1-employee-compensation` |
| 宿主 | `components/workpaper/j1/GtJ1EmployeeCompensation.vue`（**258 行**原始 / 244 行剥注释） |
| 幻影码 | `J1E` |
| 模板 | `J/J1 应付职工薪酬.xlsx` · sha256 `a6100d91202f4d06…` · **196,750 B** · **23 sheets**（业务 15 + retired 7 + `GT_Custom` 1） |
| mount | **1**（🔴 slice 的 `mount_count: 1` 是 slice 自算值，manifest 里**无该字段**） |
| 载体 | 🔴 **`shared_platform_persistence_adapter`**（第三种族，见 JC-2） |
| payload mode | `remark_only`（真库 83 行 `conclusion` 全 NULL） |
| primary managed table | 🔴 **一表三键** `J1-2-detail-{shortTerm, postEmployment, severance}` |
| 行身份字段 | 🔴 **`id`** 不是 `rowId` |
| parent_duplicate | `xlsx/j1/inspection/j1-tab-general-check`（`J1TabGeneralCheck.vue`，wp_codes `['J1-8','J1T']`，own keys `J1-8-voucher-check` / `J1-8-post-period`） |
| canary | 🔴 **`J1-6-short-term`**（`计提情况检查表J1-6`）—— **不是** primary managed table，理由见 Requirement 8 |

🔴 **无 pilot、无 J0 函证册**：四个 pilot 是 B60/D2/H1/G7，逐文件读 `review.entry_id` 无一条属 J；
`find_template_file('J0')` 与 `_any` 都返 None。这两条「查过且没有」是判据的一部分。

## Requirement 1：现算复核先行 —— slice 的结构性结论可信、**行号与环境快照不可信**

**User Story**：作为实施者，我要先知道 slice 里哪些数字还能用、哪些已经过期，
否则照着冻结快照写判据会一上手就假红。

### Acceptance Criteria

1. WHEN 实施任一 Task THEN SHALL 先现算复核，且 SHALL 区分两类结论：
   **（A）结构性结论 —— 现算零反驳，可直接采信**：
   3 模板 sha256/size/sheets（J1 `a6100d91202f4d06`/196,750/23 · J2 `b9a4d87c95d275d7`/107,237/9 ·
   J3 `72e026f43612ec6b`/50,195/6）· 4 个 orphan 行数 41/37/35/39 ·
   共享基类 `useWorkpaperEntryDualMode.ts` **65 行 / localStorage 0 / statement 边 29 / J 贡献 3** ·
   `useChecklistPersistence` statement 边 **23** · 第二写路径 **7 文件 / 8 站点** ·
   owner 常量实值全部逐字相符 · **8 个 guessed key 各 0 命中** ·
   位置化 family_a 1 / family_b 6 · `severance` defaultRows **恰 1 行**空 label
2. 🔴 **（B）必须重算的六处快照**：
   ① manifest entries 总数 —— slice 多处写 **186**，现算 **155**
   ② 契约目录个数 —— slice BP-2 记 **5**，现算 **18**；`DELIVERED_PER_ENTRY_CONTRACTS` **21 条**；
      `adapter_registered=True` 现算 **5 条** `{d2, d4, g7, h1, d1}`
   ③ 共享基类**宽口径** —— slice 记 30，现算 **34**，宽−窄差集 **5 个**不是 1 个
   ④ `GtEntrySyncCapabilityNotice` 消费方 —— slice 记 41，现算 **48**（J 域仍 **0** ✓）
   ⑤ 🔴 **行号**（见 AC 1.3）
   ⑥ `useJ2FormData.ts` **已被物理删除**（slice 的 2026-09-14 更新已兑现）
3. 🔴 WHEN 编写任何判据 THEN SHALL **按常量名 / 形态 / 端点字面量定位，禁写死行号**。
   实测行号漂移规律：**组件类 `.vue` 文件全漂 10~28 行，composable 的常量区未漂**。
   漂移样本（slice → 现算）：宿主 import 共享基类 `#L110`→**`#L103`** ·
   `useJ1Detail` load 兜底 `#L181`→**`#L164`** · `J1TabAdjustment` 位置化 `#L59`→**`#L47`** ·
   `J2TabAdjustment` `#L104`/`#L111`→**`#L94`/`#L101`** · `J3TabCheck` `#L103`/`#L105`→**`#L89`/`#L91`** ·
   `J3TabDetail` `#L126`→**`#L109`**。
   未漂样本：`J1_SECTIONS#L53` · defaultRows `#L58`/`#L85`/`#L100` · `STORAGE_KEY_PREFIX#L108` ·
   `storageKey#L110` · `J1_ADJ_*#L88`/`#L90`/`#L91` · `J1_DETAIL_SECTION_KEYS#L94` ·
   `J1TabAdjustment STORAGE_KEY#L49` · `J1TabGeneralCheck ITEM_ID#L324` · `useJ1Detail` 生成式 `#L127`。
4. WHEN 产出证据 THEN SHALL 逐项列「slice 声明值 vs 现算值」两列表，不符者标 `STALE`。
5. 🔴 WHEN 现算发现新的不符 THEN SHALL **以现算为准并登记**，不得回头改 slice 字节
   （slice 是 append-only 的冻结审计轨迹）。

## Requirement 2：四类「查过且没有」的红判据

### Acceptance Criteria

1. WHEN 断言**无 pilot** THEN SHALL 逐文件读契约目录每份 JSON 的 `review.entry_id`，
   断言无一条以 `xlsx/j` 或 `xlsx/gt-j` 开头；🔴 **不是数契约个数**。
2. WHEN 断言**无 J0 函证册** THEN SHALL 枚举 `backend/wp_templates/J`（跳 `~$` 锁文件）得恰 3 本，
   且 `find_template_file('J0')` 与 `find_template_file_any('J0')` 都返 None。
3. WHEN 断言 **J 循环完全自闭** THEN SHALL 两侧都验：
   ① J 的键无一个被非 J 路径文件消费 ② J 文件里无任何非 J 循环的键字面量
   ⇒ **HC-8 / IC-17 的跨循环键冻结在 J 不命中**（重大简化：改键名无跨循环风险）
   🔴 但 SHALL 同时登记**端点跨循环复用 1 处**：`composables/workpaper/j1/useJ1VoucherOcr.ts`
   调 **D4 的** `POST /api/workpapers/{wpId}/d4/contract-ocr`。
4. WHEN 断言 `hardcoded_scan_result` 六个模式全 0 与 `family_e`（四表种子）0 THEN
   SHALL 按 JC-20 写成「现算为 0 **且不是漏扫**」，并**复用已有变异注入脚本**逐条证明非空跑。
5. 🔴 WHEN 断言「模板无金额错误」THEN SHALL 登记**一处扫描误报的复核结论**：
   `附注披露信息（国有企业）!B29:E29` = `=SUM(B17:B28)-SUM(B20:B23)`，
   R19 `社会保险费` = `=SUM(B20:B23)` 是小计、R20:R23 是其明细
   ⇒ 全区加总再减明细正好抵消重复，**是正确的去重写法不是缺陷**。
   只看扫描命中数会造出 4 个假缺陷 ⇒ 判据 SHALL 记录「命中 4 格、逐格核验后判定非缺陷」。

## Requirement 3：🔴 载体族第三种 + 写路径必须按端点字面量判定

**User Story**：作为平台维护者，我要能准确说出「这条 entry 的写入到底经过哪几条路」，
而不是照上一个循环的口径去猜然后假红。

### Acceptance Criteria

1. WHEN 声明载体 THEN SHALL 落 **第三种写载体族 `shared_platform_persistence_adapter`**：
   `composables/workpaper/useChecklistPersistence.ts`，client 是 🔴 **`api` from `@/services/apiProxy`**
   （不是 `http` from `@/utils/http`），statement 消费边现算 **23**。
2. 🔴 WHEN 编写载体判据 THEN SHALL 写两条对照反证：
   ① 按 H 的「载体里必须有 `http.put`」去核 SHALL 在 `useChecklistPersistence` 上**假红**（它用 `api.put`）
   ② 按 I 的「宿主必须 import `@/utils/http`」去核 SHALL 在 J1 宿主上**假红**
      （现算宿主 `@/utils/http` 与 `apiProxy` 命中**均为 0**）
   ⇒ 判据 SHALL 按 entry 声明的 `write_client` 名字去找 `{client}.put(`。
3. 🔴 WHEN 判定写路径 THEN SHALL **按端点字面量扫描，禁按函数名**。现算六类端点：

| # | 端点 | 文件数 | 性质 |
|---|---|---|---|
| ① | `PUT /api/workpapers/{wpId}/checklist-responses` | **11** | 主写路径（J1 十个子 Tab + 🔴 `j3/core/J3TabDetail.vue`）+ orphan `useJ3FormData.ts` |
| ② | `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` | **1** | 🔴 **TB 发布门** |
| ③ | `POST /api/projects/{projectId}/disclosure-notes/sync-from-workpaper` | **4** | 🔴 写**另一张表**（J1 两披露 Tab + J2 两披露 Tab） |
| ④ | `POST /api/projects/{projectId}/events/publish` | **4** | 事件广播（J2/J3 侧） |
| ⑤ | `POST /api/projects/{projectId}/cross-wp-references/batch` | **1** | 跨底稿引用（J3 侧） |
| ⑥ | `POST /api/workpapers/{wpId}/ai/generate-text` | **15** | AI 生成（**非持久化**，须与写路径分清） |

4. 🔴 WHEN 判定 TB 发布门 THEN SHALL 用端点 ② 判定并断言现算命中 **1**；
   SHALL 同时登记**非空反证**：符号名 `publishToTb` 在全 J 域命中 **0**
   ——「按函数名判定得 0、按端点判定得 1」是本条判据存在的理由。
   ⇒ **GC-9 在 J 是 1/1 有门**（不是无门），canary **可以**覆盖发布链。
5. WHEN 声明第二写路径 THEN SHALL 落现算 **7 文件 / 8 站点**（`J1TabAdjustment` 两处）；
   两个数 SHALL **分别现算**，混用会让「7 还是 8」说不清。
6. WHEN 声明调整分录中央同步 THEN SHALL 落现算 **2 处**
   （`j1/core/J1TabAdjustment.vue` + `j2/J2TabAdjustment.vue`），🔴 **J3 无**（无独立科目）
   ⇒ 与 I 的 6/6、H 的 9/9 都不同，是 **2/3**。
7. WHEN 声明 OCR THEN SHALL 登记 🔴 **FC-8 在 J 命中**（不是不适用）：
   宿主层 `ocr` 命中 0 成立，但 `composables/workpaper/j1/useJ1VoucherOcr.ts` 有真 OCR 调用
   ⇒ 判据扫描范围 SHALL 含 composable 层。

## Requirement 4：一表三键 + 键真源多份 + 模板字符串拼接键

### Acceptance Criteria

1. WHEN 声明 primary managed table THEN SHALL 落 🔴 **一张逻辑表三个传输键**
   `J1-2-detail-{shortTerm, postEmployment, severance}`，由
   `useJ1Detail.ts` 的 `STORAGE_KEY_PREFIX = 'J1-2-detail-'` + `storageKey()` 派生，
   section 取自 `J1_SECTIONS[].key`（三值）；🔴 **身份字段是 `id`** 不是 `rowId`。
2. 🔴 WHEN 处置 **BP-11** THEN SHALL 登记它实际是 **4 个文件 5 处声明**（slice 只记「两份」）：
   ① `useJ1Detail.ts` 前缀派生（**写方**）② `useJ1Adjudication.ts` 的 `J1_DETAIL_SECTION_KEYS` 三字面量
   ③ `J1TabAccrualCheck.vue` 的 `DETAIL_KEYS` 三字面量 ④ `J1TabAllocationCheck.vue` 的 `DETAIL_KEYS`
   ⑤ `useJ1DisclosureSections.ts` 三处 `readJson('J1-2-detail-…')` 内联
   ⇒ 判据 SHALL **五处同时比对**；变异「只改前缀」SHALL 打红。
3. WHEN 登记同型多真源 THEN SHALL 一并落：`J1-1-rows` 2 处 · `J1-3-adjustment-rows` 同文件 2 处
   （常量 + `itemId:` 内联）· `J2-3-entries` 同文件 2 处。
4. 🔴 WHEN 处置**模板字符串拼接键** THEN SHALL 登记 slice 的 TK 清单**漏掉披露层 8 键**：
   `useJ1DisclosureSections.ts` 的 `const prefix = \`J1-disc-${variant}\`` +
   `KEY_SUMMARY` / `KEY_SHORT_TERM` / `KEY_POST` / `KEY_NOTES`
   ⇒ `J1-disc-{listed|soe}-{summary, short-term, post-employment, notes}` = **8 键**；
   真库确认有载荷（`J1-disc-soe-short-term` 1325 B · `-post-employment` 917 B ·
   `-summary` 532 B · `-notes` 118 B）。
   ⇒ 判据 SHALL 含**拼接键解析**（按前缀常量 × 后缀常量的笛卡尔积展开），完整字面量 grep 抓不到。
5. 🔴 WHEN 区分命名空间 THEN SHALL 把**三个** J1 披露相关命名空间分清，判据不得混用：
   ① `J1-disc-*`（**持久化键**，8 个）
   ② `J1-disclosure-*`（`GtReviewTrigger` 的 `section-id` + `J1TabIndex` 的 `progressKeys`，**非持久化**）
   ③ `j1-disclosure-{variant}-${aiSection}`（小写，**AI section 标识**）
6. 🔴 WHEN 登记披露层缺口 THEN SHALL 落：`J1TabDisclosureListed.vue` 有
   `J1-disclosure-listed-severance` 这个 section-id，但 `useJ1DisclosureSections` 只拼 4 个键
   （**无 severance**）⇒ 披露层有该区块但**无对应持久化键**。
7. WHEN 声明 `derived_total_keys` THEN SHALL 现算（当前 **7 个**，禁写死）：
   `J1-1-audited-total` · `J1-1-audited-begin-total` · `J1-7-total-admin-expense` ·
   `J1-7-total-production-cost` · `J1-7-total-selling-expense` · `J2-listed-summary` · `J2-soe-summary`
   🔴 正则 SHALL 覆盖 **`-total-` 出现在中间**的形态（只写 `total$` 会漏 3 个）。
8. WHEN 声明键全集 THEN SHALL 现算（当前 **160 条**，禁写死）并说明这是**全平台单循环最多**。

## Requirement 5：行身份族划分与 removeRow 四种签名形态

### Acceptance Criteria

1. WHEN 落行身份族 THEN SHALL 按 **J 口径重裁**（IC-6 在 J 的扩展），逐族现算并分别登记：
   family_a 纯序号真落库 **1**（`J2TabAdjustment` 的 `id: i + 1` → `J2-3-entries`，
   🔴 真库 171 B 载荷里 `"id":1` **已确证落库**）· family_b 下标兜底 **6** ·
   family_c 安全生成 **3** · family_d 展示序号 `seq: i+1` **3**（三个目录页）· family_e 四表种子 **0**
2. 🔴 WHEN 处置 family_c 判别式 THEN SHALL 登记 slice 的判别式**过严**：
   `useJ1DisclosureSections.ts` 有 `id: String(r.id || \`row-${Math.random()…}\`)`
   —— **只有 `Math.random()` 没有 `Date.now()`**，slice 的「同时含两者」会把它排除出 C 族，
   而它其实安全（纯随机不会撞）⇒ 判别式 SHALL 扩为
   「含 `Math.random()` 且回落分支**不是**下标 ⇒ 安全」。
3. 🔴 WHEN 处置**披露层 49 个硬编码序号 id** THEN SHALL 诚实落成「**登记但不判为位置化缺陷**」：
   SOE 侧 `s-1..s-5` + `st-1..st-12` + `pe-1..pe-8` = **25 个** ·
   Listed 侧 `s-1..s-4` + `st-1..st-12` + `pe-1..pe-8` = **24 个**
   理由：id 与 label 写在**同一个对象字面量**里，绑定是静态的、不随数组顺序变
   ⇒ 报成位置化会造出 49 个假缺陷。
4. 🔴 THEREFORE WHEN 登记披露层的**真实四条风险** THEN SHALL 逐条落：
   ① **同 id 跨变体语义不同** —— SOE `st-4`=`其中：医疗保险费` / Listed `st-4`=`其中：1. 医疗保险费`；
      SOE `st-5`=`工伤保险费` / Listed `st-5`=`2. 工伤保险费`；
      🔴 SOE `st-7`=`其他` / Listed `st-7`=**`住房公积金`**（完全不同项目）
   ② 两侧行数不同（SOE summary **5** / Listed summary **4**）
   ③ **新增行 id 形态与骨架不同**（`${category}-${Date.now()}` vs `st-N`）⇒ 同数组混两形态
   ④ 🔴 **`s-${Date.now()}` 无随机串** ⇒ 同毫秒两次点「新增」会撞 id
5. WHEN 声明 entry / non-entry 拆分 THEN SHALL 分别现算并**分开登记**：
   缺陷维度 entry_scope **2** + non_entry **5** = **7**；两者 `must_fix_before` 不同
   （entry 内的在发 per-entry contract 前修；non_entry 的归下游 lane）。
6. 🔴 WHEN 声明 removeRow THEN SHALL 落 **8 处 / 4 种签名形态**，且契约字段 SHALL 是
   `{kind, arity, param_order}` 三元组（单值枚举装不下）：

| 形态 | arity | 站点数 | 样本 |
|---|---|---|---|
| 单参 `id` | 1 | **3** | `J1TabAdjudication` · `J1TabNonMonetaryCheck` · `J1TabSeveranceCheck` |
| 单参 `rowId` | 1 | **1** | `J1TabAdjustment` |
| 🔴 双参 `(id, category)` | 2 | **2** | `J1TabDisclosureListed` · `J1TabDisclosureSoe` |
| 🔴 双参 `(区块键\|section, id\|rowId)`（参数顺序相反） | 2 | **2** | `J1TabGeneralCheck(key, id)` · `useJ1Detail(section, rowId)` |

7. 🔴 WHEN 对照 H/I THEN SHALL 登记 **J 无「下标族」removeRow**（H/I 都有按 `rowIndex`/`index` 删的）
   ⇒ 这是 J 比 H/I 好的一点；但**双参形态是 J 独有** ⇒ 判据不得与 H/I 复用同一签名断言。

## Requirement 6：三边锁覆盖面必须扩到 J1-2 之外

### Acceptance Criteria

1. WHEN 实施三边校验 THEN SHALL 先登记 slice 的覆盖面缺口：
   **RD-1 ~ RD-4 全部只对 `明细表J1-2 `**，没有一条覆盖 `计提情况检查表J1-6` /
   `分配情况检查表J1-7` / `非货币性福利检查表J1-9` / `辞退福利检查表J1-10` 自己的源 sheet。
2. WHEN 复核 **RD-1**（唯一正例锚点）THEN SHALL 三边比对 `J1_SECTIONS[shortTerm].defaultRows`
   **20 项** 对 `明细表J1-2 !B13:B32`，**有序等值 20/20**；
   SHALL 一并验边界格 `A11='序号'` / `B11='项目名称'` / `B12=None` / `A33='合计'` / `B33=None`。
3. WHEN 复核 **RD-2** THEN SHALL 落两类差异**分开计数**（强度不同）：
   ① **真标签差异 1 处** —— impl `其中：1.基本养老保险` 比源 `其中：1．基本养老保险费` **少一个「费」**
   ② **序号分隔符差异 5 处** —— 源全角 `．`(U+FF0E) / impl 半角 `.`（第 2/3/4/6/7 项）
   ⇒ 有序等值仅 **2/8**；🔴 **禁标点归一化**（归一会把真缺陷洗掉）
4. WHEN 复核 **RD-3** THEN SHALL 验否定式声明：源 `B50:B52` 三格**真读全 None**，
   impl `severance.defaultRows` 恰 **1 行**空 label ⇒ 双向断言
   （源必须真为空 **且** impl 必须恰 1 行），防「照源补全分类」这个危险动作。
5. WHEN 复核 **RD-4** THEN SHALL 验第四种形态「同一行模型两份 impl 互不一致」：
   `J1TabAccrualCheck.vue` 的 `POST_EMPLOYMENT_DEFAULTS` **带「费」**且与两份 note_template
   （`note_template_soe.json` 与 `note_template_listed.json` 逐字相同 9 行）一致
   ⇒ 缺陷精确定位在 `useJ1Detail.ts` 的 `postEmployment` 那一项**单一处**；
   🔴 判据 SHALL **双向锁死**：把带「费」那份改成不带费也 SHALL 打红。
6. 🔴 WHEN 新增 **RD-5**（本轮实测发现）THEN SHALL 三边校验 `J1TabAccrualCheck.vue` 的
   `SHORT_TERM_DEFAULTS`（**19 项**）对 `计提情况检查表J1-6` 的 A 列行标签：
   实测模板用**全角 `．` + 全角空格缩进 `　　　`**（`其中：1．工资` / `　　　2．奖金`），
   impl 用**半角 `.` 且无缩进前缀** ⇒ 与 RD-2 同型但发生在 J1-6。
   SHALL 逐格落差异清单，修法标 `[ ]*`（业务确认改哪一侧）。
7. WHEN 遵守 forbidden_shortcuts THEN SHALL 逐条落成反向断言（slice 冻结 5 条）：
   只断言 sheet 名在 `sheetnames` 里 · 只断言 cell 非空 · 集合比对代替有序比对 ·
   把 impl 常量硬抄进守卫（第二真源）· 🔴 **全角/半角标点归一后再比**。

## Requirement 7：模板层 —— 空格、变体轴、footer 三形态、幽灵行、definedName 断链

### Acceptance Criteria

1. 🔴 WHEN 定位 sheet THEN SHALL **禁 strip 任何空格**，三类各自落表：
   ① **尾部空格 2 张**：`审定表J1-1 ` · `明细表J1-2 `
   ② **名中空格 6 张**：`应付职工薪酬实质性程序表 J1A` · `…J1A-原版` · `…L1A-原` ·
      `长期应付职工薪酬实质性程序表 J2A` · `…L2A` · `股份支付实质性程序表 J3A`
   ③ 🔴 **跨 sheet 引用里带空格且单引号包裹**：`审定表J1-1 !B8 = ='明细表J1-2 '!C13`
   ⇒ 重写公式时 SHALL 保留空格与单引号；变异「strip 后匹配」SHALL 打红。
2. WHEN 声明 retired sheet THEN SHALL 四向等值比对：`sheet_count == len(sheetnames)` ·
   `retired_sheet_count == len(retired_sheets) == 现算命中数` ·
   `business_sheet_count == sheet_count − retired − mechanism`（J1：23 − 7 − 1 = **15**）；
   SHALL 一并登记 **retired 7 张全是 hidden**。
3. 🔴 WHEN 处置 **HC-5 变体轴** THEN SHALL 登记它在 J **命中 2 组**（I 循环是 0 组）：
   ① `J1A` → `应付职工薪酬实质性程序表 J1A`(visible) + `…J1A-原版`(hidden) —— 版本变体
   ② 🔴 `J1-10` → `辞退福利检查表J1-10`(visible, 48 行) + `股份支付检查表J1-10-删除`(hidden, 66 行)
      —— **一码两义**（两张完全不同业务的表，不是版本变体）
   ⇒ 按 sheet 尾码定位 SHALL 带 **visible 过滤**；变异「只按尾码匹配」SHALL 在 `J1-10` 上取到两张而打红。
4. 🔴 WHEN 登记跨循环程序表串册 THEN SHALL 落 **2 处**：
   J1 册的 `应付职工薪酬实质性程序表 L1A-原`（🔴 **slice 漏记**）+ J2 册的 `长期应付职工薪酬实质性程序表 L2A`
   ⇒ 两者都是 **L 循环**的程序表串在 J 册里（源模板原样，非缺陷但须登记，防「悄悄夹带跨循环模板」）。
5. 🔴 WHEN 声明 footer THEN SHALL 落 `明细表J1-2 ` 的 **三种形态各不相同**：
   ① R33 **跳跃式** `=SUM(C13,C19:C20,C25:C31)`（跳过已是小计的明细子行）
   ② R46 **加法式** `=C42+C37`（不是 SUM）
   ③ R53 **连续区间** `=SUM(C50:C52)`
   ⇒ 照单一口径验 SHALL 假红；`审定表J1-1 ` 同样三形态（R22 跳跃 / R34 加法 / R41 连续）。
6. 🔴 WHEN 声明数据区边界 THEN SHALL 登记 **R45 幽灵行**：A/B/C 列全空但**有公式**
   `F45 = =C45+D45-E45`，位于数据区 R37:R44 之后、footer R46 之前
   ⇒ 按「有公式即业务行」会把 8 行算成 **9 行**而与 impl 的 8 项不符；
   判据 SHALL 按 **B 列非空**判业务行，并对 R45 写显式排除断言。
7. WHEN 声明 definedName THEN SHALL 登记基线 `{J1: 0, J2: 37, J3: 502}` + 断言**不增长**，
   并 🔴 **同时登记断链数**：含 `#REF!` 的 **J2 30 / J3 479**；
   J3 的 502 个实测是**跨循环复制残留**（`_1固定资产数据库_筛选打印` / `_2其他资产_开办费除外_明细表` /
   `_2、主要业务活动` / `_.dbf` / `AS2DocOpenMode` 等）⇒ **不删**（删会让公式整片失效），
   只声明「同步时不新增、不改写」；J2/J3 的处置归下游 lane。
8. WHEN 声明裸 IF 中性化 THEN SHALL **per-file** 挂，计数现算 `{J1: 132, J2: 12, J3: 0}` 总 **144**；
   J1 内部分布 `审定表J1-1 ` 56 / `与同行业对比分析表J1-5` 60 / `月度分析表J1-4` 16；
   🔴 **J3 整册裸 IF 为 0**；变异「整册统一挂」SHALL 打红。
9. WHEN 声明 UUID 落位 THEN SHALL 用「有效列 + 1」：
   `明细表J1-2 ` **15**（有效 14 = max_column 14）· `审定表J1-1 ` **13**（有效 12 / max 13）·
   `明细表J2-2` **15**（有效 14）· `股份支付情况表J3-1` **15**（有效 14 / max **18**，差 4）。
10. WHEN 断言干净点 THEN SHALL 逐项现算为 0 并按空分母纪律处理：
    越界引用 **0** · 宽表（max_column ≥ 200）**0** · Excel Table **0** · localStorage **0**
    （共享基类零 localStorage ⇒ legacy_deletion_paradigm step 5「统一键前缀」对 J1 **不适用**）。
11. 🔴 WHEN 登记「一册一 entry」FC-3 在 J 的形态 THEN SHALL 落 **3 文件 ↔ 1 entry = 单射但不满射**：
    判据 SHALL 验「单射 + 每个 `belongs_to_entry: null` 都带 `excluded_reason` +
    有主那条真命中 slice 的 entry_id」；
    🔴 写死「双射」SHALL 对本 slice 假红，写死「多对一」SHALL 放过夹带跨循环模板。

## Requirement 8：canary = `J1-6-short-term`（硬标准口径须改）

**User Story**：作为实施者，我要一个真库有载荷、在 entry 内、且不需要先修身份缺陷的最小闭环。

### Acceptance Criteria

1. 🔴 WHEN 选 canary THEN SHALL 先登记 **D~I 的硬标准在 J 不成立**：
   primary managed table 三键 `J1-2-detail-*` 真库**完全无行**，
   `J1-1-rows`（审定表）与 `J1-3-adjustment-rows`（调整分录）**也无行**
   ⇒ 硬标准 SHALL 改为「**真库有非空载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组**」。
2. WHEN 落选型对照表 THEN SHALL 四个候选逐条给裁决与理由：
   ✅ **`J1-6-short-term`** 真库 **3473 B**（全 J 最大）· `计提情况检查表J1-6` r=60 c=11 f=63
      **裸 IF 0** merged=17 · entry 内 · 键组 clean（id 形态 `acr-{ts}-{i}-{rnd}` 属安全族）
   ❌ `J1-disc-soe-short-term` 1325 B **且有真金额**，但披露层叠 5 个最难形态（见 AC 8.4）
   ❌ `J1-8-voucher-check` 911 B 且 id 形态 `j1vc-imp-credit-1` 真实，但属 **parent_duplicate**
      ⇒ 按 AC 1.6 不独立发布 contract / bundle / candidate / evidence
   ❌ `J1-2-detail-*` primary managed table —— 真库空，不满足硬标准
3. 🔴 WHEN 登记 canary 三条逆风 THEN SHALL 逐条如实写，不得省略：
   ① 3473 B 载荷的**金额字段全 0**（`baseAmount`/`rate`/`estimated`/`actual`/`diff` 全 0；
      `baseName`/`baseIndex`/`diffReason`/`conclusion` 全空串）⇒ 它是「骨架已落库、业务未填」
      ⇒ roundtrip 只能验结构 ⇒ SHALL **另造带金额的合成载荷**补一轮
   ② RD-5（AC 6.6）的三边校验缺口 SHALL 在 canary 内**先补**
   ③ 同 Tab 的 `J1-6-questions` 901 B 是 **AI 生成 markdown 长文本**（5 元素字符串数组，
      首元素是含 `###` 标题与列表的整段中文）⇒ representation SHALL 区分
      「结构化行数组」与「自由文本数组」两种 shape
4. WHEN 说明否决披露层的理由 THEN SHALL 列齐 **5 个叠加形态**：
   双变体（listed/soe）· 49 个硬编码 id · **同 id 跨变体语义不同** ·
   第三条写路径写**另一张表**（`disclosure-notes/sync-from-workpaper`）·
   与明细表**非行对行映射**（12 行 ← 20 行，含 **3 处两行合一** + **1 处手填**）。
5. WHEN canary 覆盖发布链 THEN SHALL 断言只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`
   + 必经二次确认，且 🔴 **禁**在 `watch` / `onMounted` / debounce 回调内发布；
   SHALL **复用**平台既有 2 道 CI 守卫（`check_tb_writeback_no_direct_call` /
   `check_tb_publish_confirm_gate`），**不重造**。
6. WHEN 处置 BP-10 THEN SHALL 在 canary 内建**第一处** notice 挂载（J 域现算 0）：
   文案真源 SHALL 是 `workpaperEntrySyncNotice.ts`，🔴 禁在宿主硬编码中文；
   SHALL 同时修 **el-segmented 缺二级门控**（现算宿主 `isOoAvailable` 命中 **0**）——
   🔴 当前表现比 AC 1.5 要求的「不显示不可兑现的按钮」**更差**：
   共享基类 `switchMode` 只在运行时 `return` ⇒ 用户点了**没反应**（无声失败）。

## Requirement 9：prefill 四处缺陷 + 零回归 + 空分母纪律

### Acceptance Criteria

1. WHEN 核 prefill THEN SHALL 现算 J 的 mapping 数（当前 **10 条**），字段名是 **`sheet`** 不是
   `sheet_name`，且全部 `cells` 型 / `items` 全 0；`wp_code` 只 `J1`/`J2`/`J3` 三值（非子码）。
2. 🔴 WHEN 登记 prefill 缺陷 THEN SHALL 落 **4 处**：
   ① `sheet: '审定表J1-1'` **缺尾部空格**（模板真名 `审定表J1-1 `）⇒ 按名定位必失配
   ② `sheet: '明细表J1-2 '` 那条 `cells: []` **空数组** = 死配置
   ③ `sheet: '调整分录汇总表J1-3'` 的 cells 里写 `=PREV('J1','分析程序J1-3','审定数')` ——
      🔴 **`分析程序J1-3` 在模板 23 张 sheet 里不存在**
   ④ J3 一条 `wp_name: '股份支付审定表'` 但 🔴 **J3 册没有审定表**（6 张 sheet 里无 `审定表J3-*`）
   修法标 `[ ]*`（prefill 配置属另一条产品链路，本 spec 只交付判据 + 登记）。
3. WHEN 现算零回归基线 THEN SHALL 逐项现算且 🔴 **禁写死个数**：
   契约目录 `*.json` 个数与**文件名集合** · `DELIVERED_PER_ENTRY_CONTRACTS` 条数与 entry_id 集合 ·
   `adapter_registered=True` 的集合 · `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员。
4. WHEN 处置 Property 分母 THEN SHALL 按 Task 52 点名的 Property **3 / 20 / 69 / 70** 分别处理：
   空分母部分（`bidirectional` entry 数 = 0 / 本 slice contract 数 = 0）**不宣称通过**，
   只断言前提成立 + 承载者存在；Property 69 的分母非空但**全为负向**
   （`verification_state = UNVERIFIABLE` + 非空 `unverifiable_reasons` 6 条）。
5. WHEN 迁移 THEN SHALL 只走 `register_from_manifest()`；🔴 **禁手改 manifest**；
   注册后 `capability` 才由 `single_onlyoffice` 变 `bidirectional`。
6. WHEN 收尾 THEN SHALL 复跑 `test_task52_j_cycle_migration.py` 零回归，
   并 🔴 **复用**已有变异注入脚本 `mutate_task52_j_cycle_migration_guards.py` 证明判据非空跑。

## 阻塞项（BP-1 ~ BP-11）

**平台级（全循环共有，只标 `[ ]*` 不承诺）**：
BP-1 non-current instrumentation candidate + finalize 出的 published representation ·
BP-2 人工审核的 per-entry contract（🔴 现算 18 份契约无一条 `review.entry_id` 属 J）·
BP-3 approved authority model + non-null approved definition bundle ·
BP-4 真 OnlyOffice 9.4 的 required scenario set（`evidence.sync_test_run_id` 与
`required_scenario_set_digest` 现为 null）。

**J 专属**：

| BP | 归属 | 本 spec 交付 |
|---|---|---|
| **BP-5** 写路径多轨并存 | 本 spec | JC-3 六类端点表 + Requirement 3；🔴 实测是**六类端点**不是 slice 说的「双轨」 |
| **BP-6** 4 个 orphan dual-mode | **下游 lane** | 不在本 spec（全在 J2/J3 侧） |
| **BP-7** `useJ3FormData.ts` 死代码 | **下游 lane** | 不在本 spec（`useJ2FormData.ts` 已被物理删除） |
| **BP-8** 行模型 / 行身份两类缺陷 | 本 spec（entry 内 2 处 + RD-2/RD-4/RD-5）+ 下游 lane（non_entry 5 处） | Requirement 5 + 6 |
| **BP-9** manifest capability 来自 overlay | 本 spec | JC-1 全文 + `register_from_manifest()` 迁移路径 |
| **BP-10** AC 1.4 未兑现且比 I 更差 | 本 spec | Requirement 8.6（canary 内建首处挂载 + 修二级门控） |
| **BP-11** primary table 传输键多份真源 | 本 spec | 🔴 Requirement 4.2（实测 **4 文件 5 处**，非 slice 说的两份） |

**本轮新增登记（slice 未覆盖）**：

| 事项 | 状态 |
|---|---|
| **RD-5** `J1-6` 的 `SHORT_TERM_DEFAULTS` 19 项未做三边校验 | 本 spec 交付判据；修法 `[ ]*` 业务确认 |
| 披露层 **8 个拼接键**未进 TK 清单 | 本 spec 交付拼接键解析判据 |
| 披露层 **4 条真实风险**（同 id 跨变体语义不同等） | 本 spec 登记；修法 `[ ]*`（涉用户可见披露口径） |
| prefill **4 处缺陷** | 本 spec 登记；修法 `[ ]*`（另一条产品链路） |
| `wp_guidance/J2.json` 缺失 | 登记不补（J2 不是 entry） |
| `J1-10` **一码两义** | 本 spec 交付 visible 过滤判据；不改模板字节 |
| 跨循环程序表串册 2 处（`L1A-原` / `L2A`） | 登记不修 |
