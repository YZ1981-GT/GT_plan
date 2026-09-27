# K 循环双向回写地基与首张 canary — 任务

> **实施纪律**
> - 🔴 **所有计数一律现算**，与 `design.md` 等值比对；多一处少一处都红。禁写死。
> - 🔴 **判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号**（组件类 `.vue` 行号会漂）。
> - 🔴 **行数口径统一为 `len(text.split("\n"))`**（KF-P61）。
> - 🔴 **枚举 K 宿主必须排除 `GtKamWorkpaper.vue`**（KF-P5）。
> - 变异脚本**复用** `backend/scripts/diagnose/mutate_k_cycle_guards.py` 与 `mutate_task53_k_cycle_migration_guards.py`；实景核验复用 `verify_k_cycle_live.py`。**不新写**。
> - `[ ]*` = 依赖外部供给（BP-1 / BP-2 / BP-3），本 spec **不承诺完成**。
> - 并发会话正在实施 F3/F4/F5 与 H9 的 spec，其契约与关联产物**一律不碰**。

---

## 阶段 0：前置门与红判据（Task 0 ~ 3）

- [ ] 0. 建立 K 域文件集与扫描口径基线
  - 实现 `k_domain_files()`：`components/workpaper/k{1..13}/**` + `composables/workpaper/k{1..13}/**` 的 `.ts`/`.vue`（排除 `__tests__`）+ `components/workpaper/GtK*.vue`（🔴 排除 `GtKamWorkpaper.vue`）+ `components/workpaper/composables/` 下 `^(use)?[kK](1[0-3]|[1-9])(?![0-9])` 的 `.ts`
  - 断言现算 == **367**；并断言含 `GtKamWorkpaper.vue` 时为 **368**（两侧都验）
  - 实现 `strip_comments()`：块/行/HTML 注释同长空白替换保留行号，行注释正则用 `(?<!:)//`
  - _Property: KF-P5_

- [ ] 1. manifest 与 slice 分歧门（BP-9）
  - 按 `selection_rule` 从 manifest 现算 K 前缀 xlsx 独立 entry 集合，与 slice `independent_entries` 等值比对（**13** 条）
  - 断言 13 条的 `capability` 全 `single_onlyoffice` / `html_store` 全 `unresolved` / `adapter_id` 全 null / **0 条有 `capability_target`**
  - 断言 slice 的 `bidirectional` 条数 == 0、`capability_verdict_pending` == 13，且守卫断言 manifest 与 slice **不相等**并指向 BP-9
  - 断言 `parent_entry_id ∈ 13 条` == 0 ∧ overlay `parent_rules` 含 `/k\d` == 0 ∧ slice 无 `parent_duplicate_summary` 键
  - _Property: KF-P1, KF-P2, KF-P3, KF-P4_

- [ ] 2. 模板层基线冻结（14 册）
  - 现算 `backend/wp_templates/K/` 非锁文件 **14** / 锁文件 **0**；`belongs_to_entry` 非 null **13** + null 带 `excluded_reason` **1**
  - 🔴 对 `K0` 跑 `find_template_file` 与 `find_template_file_any`，断言**两者都返 `K0 管理循环函证.xlsx`**（非 None，与 J0 相反）
  - 现算 14 册 sheets 合计 **152**、逐册 sheet_count 与 slice 等值；13 entry 册 = **141**
  - 现算 definedName **82 / 含 `#REF!` 65**（K4 43/36 · K2 37/29 · K6 1/0 · K10 1/0 · 其余 10 册 0），登记基线 + 断言不增长
  - 现算 sheet 名四类字符缺陷 **21 / 5 / 2 / 1**，并断言**首尾空格 0**
  - 现算 footer **164 = 140 + 19 + 5**、裸 IF 14 册 **735** / 13 entry 册 **715** / K10 册 **0**、hidden `GT_Custom` **8 册**
  - _Property: KF-P6, KF-P7, KF-P8, KF-P29, KF-P30, KF-P32_

- [ ] 3. 七项结构性零 + 变异证明
  - 逐项现算并断言为 0：① 本表行越界 ② 跨表指向不存在 sheet ③ **同尾码双 sheet**（⇒ HC-5/JC-11 不命中）④ Excel Table ⑤ sheet 名首尾空格 ⑥ hardcoded 五模式 ⑦ `duplicate_account_aggregation_found`
  - 🔴 断言 `positional_row_id_template` == **13 非 0**，且这 13 处是位置化 48 处的**子集**
  - 🔴 断言 `blankRows` 全 K 域 **0 次调用** ⇒ HC-13 不命中；同时登记 24 张 ≥20 列宽表是纵向多行+列固定形态
  - 对每项跑变异注入（复用既有两个脚本），断言注入后打红
  - _Property: KF-P58, KF-P59, KF-P60_

---

## 阶段 1：KC-1 ~ KC-24 落地（Task 4 ~ 19）

- [ ] 4. KC-2 载体族二分支判据
  - 现算 `checklist-responses` 端点 **16 文件**（排除 Kam）：12 个 `useK{n}FormData.ts` 各 2 处 + `useK11Detail.ts` 1 + K1 三个 Tab 各 1
  - 🔴 断言 `useK5FormData.ts` 裸端点 **0** ∧ `useChecklistPersistence` **3** ⇒ 写成 `shared_platform_persistence_adapter` 族，**不判为缺陷**
  - 断言 13 宿主该端点全 **0** ∧ `useChecklistPersistence` 各 **3**（合 39）
  - 断言 K5 的 10 个 Tab 全部只 `emit('save')`，宿主 `GtK5Provisions.vue` 收口
  - _Property: KF-P9, KF-P10_

- [ ] 5. KC-3 端点扫描器（认反引号）+ 变异反证
  - 实现端点扫描正则同时认单引号 / 双引号 / **反引号**，`${...}` 归一为 `{X}`
  - 🔴 变异反证：把正则改成只认单/双引号，断言 `onlyoffice-config` 命中从 **6 文件降为 0**
  - 现算端点全集 **30 种**；断言 `onlyoffice/health` **20 文件 = 13 composable + 7 宿主**
  - 现算 `onlyoffice-config` **6 文件 / 9 处**（K8:2 K9:2 K10:1 K11:2 K12:1 K13:1），口径写明「文件数 ≠ 处数」
  - 登记 `ledger/entries/1221` 硬编码科目码 + `force_component_type=k1-other-receivables` 两处
  - _Property: KF-P11, KF-P12, KF-P13, KF-P14_

- [ ] 6. KC-4 TB 发布门四层载体清册
  - 按端点字面量现算 **14 处 / 13 条 entry 全覆盖**，按四层归类（FormData 5 / Adjudication 3 / TabAdjudication 5 / **宿主 1**），K5 占 2 处
  - 🔴 反证：按符号名 `publishToTb` 判定，断言与端点判定结果不同（J 轮已证该符号名可全域 0 命中）
  - _Property: KF-P15_

- [ ] 7. KC-5 三命名空间分离器
  - 现算业务键全集 **1065**，逐 entry 分布等值比对（K1 142 · K5 119 · K6 107 · K2 86 · K3 86 · K8 86 · K9 79 · K7 76 · K10 64 · K4 62 · K13 57 · K12 53 · K11 48）
  - 🔴 现算 `K{n}-review-session-{14位时间戳}` **9 个**，写入「排除清单」
  - 现算 per-row 拆键形态 `K{n}-1-r-{6位base36}-{begin|unadj}`
  - _Property: KF-P16, KF-P17_

- [ ] 8. KC-6 行身份四族判别器（与 J 统一判别式）
  - 实现三行布尔判别式：`ENTROPY`/`FALLBACK` 两个正则 + 三族互斥定义
  - 现算 a**32** / b**13** / c**3** / total**48** / defect**45**，断言三族互斥且并集 == total
  - 逐 entry defect 9 条等值 + 零缺陷 4 条（K2/K4/K10/K13）
  - 🔴 family_d 按键名集合分别现算（`seq` 35 / `seqNo` 6 / `index` 25），断言**不计入 total_hits**，并登记 slice 的 38 是多键口径
  - 🔴 断言 `K7TabDisclosureSoe.vue` 那处（按 `String(raw?.id || \`grant-${idx}-${Date.now()}\`)` **形态定位不按行号**）归 **family_b**
  - 断言扫描范围覆盖两处 owner 目录（composables **205** + `k{n}/**` **149**），前缀正则带 `(?![0-9])`
  - _Property: KF-P18, KF-P19, KF-P20, KF-P21, KF-P22_

- [ ] 9. KC-6 三族真落库实证（真库现读）
  - 现读 `K1-2-detail-rows` 断言 `id` 形态 `K1-2-r-{12位hex}` ∧ 含 `seq` 展示序号字段
  - 现读 `K8-6-rows` 断言 `rowKey` 形态 `row-{idx}-{13位ts}` ∧ 含 `index` 字段 ⇒ family_c 真落库
  - 现读 `K9-1-rows` 断言 `rowKey` 形态 `row-{base36}` ⇒ 纯随机族
  - 🔴 已落库旧 id 一律 **grandfather 不重写**，只保证新增走值化身份
  - _Property: KF-P23_

- [ ] 10. KC-7 removeRow 四元组契约字段
  - 现算 **36 种签名 / 124 站点**（arity=1 **28** 种 / arity=2 **8** 种），按参数名族归类
  - 把契约字段从单值 `row_delete_api_kind` 改为 `{kind, arity, param_order, param_name_family}` 四元组
  - 🔴 断言 K **有下标族**（`$index`/`idx: number`/`actualIdx`/`tableIndex`）且站点集中 K3~K7
  - _Property: KF-P24, KF-P25_

- [ ] 11. KC-8 跨循环键冻结 + H1 golden 回归钩子
  - 现算非 K 域消费 K 键 **70 个**；逐条列出 `K11-2-detail-rows` / `K11-2-fixed-asset-occurrence` / `K11-2-rou-occurrence` / `K11-2-intangible-occurrence` / `K11-2-intangible-source-amount` / `K11-source-{H1,H3,H8,I1}-amount` / `K1-1` 的消费方
  - 🔴 建立冻结清单：`K11-*` 与 `K1-1` 不得改名；改动触发 **H1 pilot golden 回归**
  - 反向现算 K 域引用的非 K 键仅 **4 种**
  - _Property: KF-P26, KF-P27, KF-P28_

- [ ] 12. KC-11 K1 披露表 `#REF!` 登记（缺陷归 lane 1，本 spec 只立判据）
  - 现算两张披露表各 **35 格 / 8 行**（合 70 格）；断言 E 列 `=IF(C{r}=0,0,C{r}/$B$18)` **活着**
  - 断言合计行 `=SUM(C125:C129)` / `=SUM(F125:F129)` / `=SUM(C138:C140)` **传播 `#REF!`**
  - 算术自检 20 + 15 == 35
  - 定性为「源 sheet 被删或改名的部分断链」⇒ 走**覆盖层**（FC-5 例外新增一条），实际修复归 lane 1
  - _Property: KF-P31_

- [ ] 13. KC-13 两处扫描误报的区分判据
  - 🔴 实现幽灵行两口径（宽 **149** / 收紧到 footer 之前 **125**），并对三处样本（`明细表K3-2` / `摊销测算表K2-5` / `明细表K8-2`）逐格核验为预置空白业务行
  - 写明与 J 的 R45 的区分判据：J = footer 区内 + 横向校验 `F=C+D-E`；K = 数据区 + 纵向派生
  - 🔴 实现「两层小计」白名单判据：外层 SUM 区间含内层小计行且内层明细已被吸收 ⇒ 判**正确**不判缺陷
  - 登记副产物「同册双变体披露表账龄分层深度不同」（上市 3+5 两层 / 国企 6 档一层）⇒ 两变体不共用行映射
  - _Property: KF-P33, KF-P34_

- [ ] 14. KC-14 + KC-15 门控与 notice 判据
  - 断言 notice 两符号 K 域命中都 **0**，判据写明用组件名（全平台 48）还是模块名（全平台 2）
  - 现算 `v-if` 门控 **11** 宿主；🔴 断言 K8/K9 的 `disabled: !isOoAvailable` 在 **composable**（按常量/形态定位，不写行号），宿主层 **0**
  - 断言 `el-segmented` 剥注释后 **13/13 恒 1 处**，且落在该宿主 `toolbar_gate_anchor` 之后 6 行内
  - _Property: KF-P35, KF-P36_

- [ ] 15. KC-16 derived_total 双正则
  - 现算尾部正则 **77** / 加中置 **83**，列出仅中置命中的 6 个键
  - 契约声明 83 个键为派生态 + 排除 roundtrip 业务比对 + 指定重算责任方
  - 🔴 把这 83 个键登记为 **Property 24 的非空分母**
  - _Property: KF-P37, KF-P54_

- [ ] 16. KC-17 prefill 一致性断言（干净点，方向是「保持」）
  - 现算 K 前缀 **51 条**（14 审定 + 26 披露 + 11 其他）
  - 🔴 断言 **sheet 名 51/51 与模板真名逐字一致**（含四类字符缺陷全部原样）—— 与 J 的失配形成对照
  - 登记 2 条 `cells=0` 死配置（`明细表K1-2` / `明细表K3-2`）+ K4 三条 `accounts=[]`
  - _Property: KF-P38_

- [ ] 17. KC-18 localStorage 分类 + step 5 范围界定
  - 现算 **26 文件**，分三类登记（模式偏好 13 composable + 3 宿主撞车 / 列偏好 5 文件 / 其他 6 Tab）
  - 断言 step 5 `unify_mode_values` **只收敛模式偏好类**，列偏好不动
  - 🔴 登记「J 循环该项为 0 故不适用，K 适用」⇒ 照抄 J 会漏做
  - _Property: KF-P39_

- [ ] 18. KC-19 OCR 两形态登记
  - 现算 `/api/d4/contract-ocr` **7 文件（无 wpId 段）** vs `/api/workpapers/${…}/d4/contract-ocr` **3 文件**；宽口径 **12**
  - 断言 `runOcr` **4** / `OcrConfirm` **0**
  - 🔴 登记「同一能力两个契约面」为缺陷，统一动作归 lane（K1 的归 lane 1、其余归 lane 2）
  - _Property: KF-P40_

- [ ] 19. KC-20 + KC-21 + KC-22 + KC-23 四条收口
  - 🔴 实现 per-row 孤儿键判据：per-row 键的 rowId 集合 ⊆ 主键载荷 rowId 集合；K2 实测 4 个孤儿（`r-ryx6og` / `r-yqfa02` 各 2 键）⇒ 清理动作归 lane 1
  - 🔴 断言 `审定表K2-1` 数据区 R7:R13 连 A 列都是 `='明细表K2-2'!A{n}` ⇒ 契约标 `derived` + `editable_labels:false`；并断言 R5 含单元格内换行符
  - 三条口径陷阱写入守卫：`GtKamWorkpaper.vue` 排除（367 vs 368）· 行数口径 13/13 验证 · 契约 18/17 vs `adapter_id` 非空 9（且 manifest 无 `adapter_registered` 字段）
  - 🔴 KC-23 分支判据：K1~K7 看 `select_leaves` / K8~K13 看 `render_pl_cycle`；42 个 `_k*.py` 按 import `k_cycle_specs` 筛（13 主 + 3 K0 + 26 辅助）；13 个 `k{n}AccountScope.ts` 全存且走 `tb_source_codes.gross_standard`
  - _Property: KF-P41, KF-P42, KF-P5, KF-P57, KF-P61, KF-P63_

---

## 阶段 2：canary `K10-3-entries` 端到端（Task 20 ~ 27）

- [ ] 20. canary 选型四项硬标准复算 + 否决理由留档
  - 逐条复算：真库 **199 B** 非空 ∧ 在 `xlsx/gt-k10-other-income` 内 ∧ `parent_duplicate` 计数 0 ∧ **单 sheet 单键**（同表 `K10-3-published` 是发布标记非行数据）
  - 🔴 现算 **13 册「调整分录汇总」完全同构**（`r∈[21,25]` / `c=10` / `f=7` / `bareIF=0` / `merged=3`，13/13 无例外）⇒ 记为「canary 判据可外推到其余 12 条 entry」的依据
  - 把八条否决候选与理由写进 evidence（含 `K2-1-rows` 的三条硬伤、`K10-2-detail-rows` 的「有行但 remark 空」）
  - _Property: KF-P43, KF-P44_

- [ ] 21. canary 身份族确认（不做前置修复）
  - 现读真库载荷断言 `id` 形态 `entry-{13位ts}-{6位base36}` ⇒ 安全族
  - 断言 K10 在零位置化缺陷 4 条 entry 内 ⇒ **canary 无身份前置修复项**（与 I6 的 backfill、J1-6 的 RD-5 都不同）
  - _Property: KF-P45_

- [ ] 22. 发 K10 per-entry contract（`[ ]*` 依赖 BP-1）
  - 声明 managed table = `K10-3-entries` ↔ `调整分录汇总K10-3`
  - 🔴 显式排除 **6 个 `K10-review-session-{14位时间戳}` 键**（另一命名空间）
  - 声明 `row_delete_api_kind` 四元组（K10 侧现算形态）
  - 声明 derived_total 键（K10 侧属 83 个全集的子集）
  - _Property: KF-P48, KF-P24, KF-P37_
  - **注**：`[ ]*` —— 发布生产契约需 approved authority model（BP-1），本 spec 只交付契约草案 + 判据

- [ ] 23. 注册 provider 与 adapter（`[ ]*` 依赖 BP-1 / BP-2）
  - 只走 `register_from_manifest()`，不手写注册
  - 断言注册后 `adapter_id` 非空、`capability` 由 slice 反哺（BP-9 闭环）
  - _Property: KF-P50_

- [ ] 24. 写入方集合与 roundtrip 骨架
  - 🔴 断言写入方集合含 `useAdjustmentCentralSync`（`K10TabAdjustment.vue` 3 处）
  - 断言 K10 的读写载体属 `formdata_composable_bare_endpoint` 族（`useK10FormData.ts` 2 处 `checklist-responses`）
  - roundtrip 跑通「HTML → 服务端 → OO → 服务端 → HTML」结构比对
  - _Property: KF-P47, KF-P9_

- [ ] 25. 🔴 合成载荷补金额维度
  - 如实登记真库载荷是**测试骨架**（`description` 测试串 + 金额 0 + 5 字段空串）
  - 另造带金额合成载荷跑第二轮 roundtrip，标 `synthetic_payload_for_amount_dimension`
  - 断言金额维度的 footer 重算（连续区间 SUM 族）一致
  - _Property: KF-P46, KF-P32_

- [ ] 26. BP-6 与 BP-7 在 K10 的处置
  - 删 `useK10DualMode.ts` 的两处 legacy 端点直调（`onlyoffice/health` 1 + `onlyoffice-config` 1），改走 sync bridge materialize
  - 断言处置后该文件两端点命中降为 **0**，bridge materialize 路径命中非 0
  - 在 `GtK10OtherIncome.vue` 挂 notice（按 KC-14 口径选符号）
  - 🔴 `useK10DualMode.ts` 的 localStorage 前缀 `k10-dual-mode:` 收敛到 `workpaper-sync-mode:`；**`useK10DetailColumnPrefs.ts` 与 `useK10GrantColumnPrefs.ts` 不动**
  - _Property: KF-P51, KF-P35, KF-P39_

- [ ] 27. 🔴 实景核验（`[ ]*` 依赖 BP-3）
  - 复用 `backend/scripts/diagnose/verify_k_cycle_live.py`，**不新写**
  - 真 OO 9.4 探针未就绪时，evidence 一律标 UNVERIFIABLE 且带非空 `unverifiable_reasons`
  - 断言无一条 entry 空口声称 VERIFIED
  - _Property: KF-P55_

---

## 阶段 3：空分母纪律与交接（Task 28 ~ 29）

- [ ] 28. 空分母报告
  - Property 20：contract 维度**不宣称通过**；前提方向四件真验
  - Property 24：两分母分开报，83 个派生态键是非空分母
  - Property 69：只作负向真验
  - Property 70：八 slice **28 个配对** + 契约归属 + 14 册单射 + 13 条 `template_ref.workbook` 集合大小 13 + deletion path 不相交
  - 🔴 契约与 adapter 分母分开算（18/17 vs 9），并断言 manifest **无 `adapter_registered` 字段**
  - 共享基类现算窄 **29** / 宽 **33** / 差集 **4**，断言本任务前后都是 29（K 贡献 0 边）
  - _Property: KF-P53, KF-P54, KF-P55, KF-P56, KF-P57, KF-P62_

- [ ] 29. 交接给两份 lane spec
  - 交接清单（逐条指名，不含模糊表述）：

| 交接项 | 去向 |
|---|---|
| BP-4（K1-9 writeoff 必须 adapter 承载，五常量五跳写路径） | lane 1 |
| BP-5（7 个一阶 orphan + 宿主内联 IIFE，**canary 未覆盖的主线形态**） | lane 1 |
| BP-8 的 **24 处**（K1 3 · K3 1 · K5 7 · K6 7 · K7 6） | lane 1 |
| KC-11 的 70 格 `#REF!` 实际修复（覆盖层） | lane 1 |
| KC-20 的 4 个孤儿 per-row 键清理 | lane 1 |
| KC-21 的 `审定表K2-1` 纯派生标注 | lane 1 |
| definedName 断链 **65 个**（K2 29 + K4 36）+ 81 个基线 | lane 1 |
| 下标族 removeRow（K3~K7） | lane 1 |
| BP-6 的其余 **5 条**（K8/K9/K11/K12/K13 的 legacy 端点直调 + localStorage 收敛） | lane 2 |
| BP-8 的 **21 处**（K8 8 · K9 7 · K11 4 · K12 2） | lane 2 |
| KC-8 的跨循环枢纽 **K11**（H1 pilot golden 回归） | lane 2 |
| KC-15 的 K8/K9 `disabled` 门控形态 | lane 2 |
| K8/K9 截止性测试双 sheet（`K8-6`/`K8-7`、`K9-6`/`K9-7` 方向变体） | lane 2 |
| K11 / K13 真库 0 行 ⇒ roundtrip 用合成载荷标 `synthetic_payload_no_live_db_baseline` | lane 2 |

  - 断言两份 lane spec 的 entry 集合与本 spec **无交集**，三者并集 == 13 条
  - 断言两份 lane spec 只**引用** KC-x 编号不复述正文
  - _Property: KF-P52, KF-P56_

---

## 阻塞项归属表

| BP | 归属 | 本 spec 处置 |
|---|---|---|
| **BP-1 ~ BP-3** | 平台级（全循环共有） | 🔴 只标 `[ ]*`，**不承诺** |
| BP-4 | 只 K1 | 🔴 **不属本 spec** ⇒ lane 1 |
| BP-5 | K1~K7 | 🔴 **不属本 spec** ⇒ lane 1 |
| BP-6 | K8~K13（含 K10） | K10 部分在本 spec（Task 26）；其余 5 条 ⇒ lane 2 |
| BP-7 | 13 宿主全部 | K10 部分在本 spec（Task 26）；其余 12 条分属两 lane |
| BP-8 | 9 条 entry / 45 处 | 🔴 **K10 为 0，不属本 spec** ⇒ 24 处 lane 1 + 21 处 lane 2 |
| BP-9 | 13 条全部 | 本 spec 立判据（Task 1）+ step 9 后闭环（Task 23） |
