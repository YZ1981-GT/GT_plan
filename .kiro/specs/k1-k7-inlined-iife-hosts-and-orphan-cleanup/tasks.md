# K1~K7 内联 IIFE 宿主与 orphan 清理 — 任务

> **实施纪律**
> - 上游共同裁决 **KC-1 ~ KC-24** 在 `k-cycle-sync-foundation-and-first-canary/design.md`，🔴 **本 spec 只引用编号不复述**。
> - 🔴 所有计数**现算**并与 `design.md` 等值比对，禁写死。
> - 🔴 判据锚点用**常量名 / 端点字面量 / 形态特征**，**禁写死行号**。
> - 🔴 行数口径统一 `len(text.split("\n"))`（KA-P6）。
> - 🔴 **BP-1 / BP-2 / BP-3 对本 lane 的四件主线事都不是阻塞**（orphan 删除 / 位置化修复 / 模板层登记 / 孤儿键清理）⇒ 本 lane 这四件**可立刻实施完**；`[ ]*` 只标「发 contract / 注册 adapter / 产 evidence」。
> - 🔴 本 lane **不产 canary**；它承接 foundation canary 未覆盖的 **BP-5 主线形态**。
> - 变异脚本与实景核验**复用** `backend/scripts/diagnose/` 下既有三个 K 脚本，**不新写**。

---

## 阶段 0：前置门（Task 0 ~ 2）

- [ ] 0. entry 边界与切分自检
  - 列出本 spec 的 **7 条 entry_id 全名**；断言与 foundation 的 `xlsx/gt-k10-other-income` 及 lane 2 的 5 条**三者无交集**、并集 **13**
  - 断言 7 条的 `capability_target_blocked_by` **全部含 BP-5**，且 K 循环含 BP-5 的 entry **恰好是这 7 条**（两侧都验）
  - 现算本 lane 六项规模并与 design 等值：sheets **81** · 键 **678** · 裸 IF **291** · BP-8 **24** · 真库非空键 **54** · definedName **81**
  - _Property: KA-P1, KA-P2_

- [ ] 1. 消费边解析器（口径先立，含双引号反例）
  - 实现三形态 statement-position 解析 + `@/` 与相对路径归一 + **路径相等**判定
  - 🔴 实现「排除双引号字符串内匹配」；用 `workpaperSyncLegacyBaseline.generated.ts` 的 `"snippet"` 字段作反例断言（不排除时会多出伪边）
  - _Property: KA-P3_

- [ ] 2. 行数口径与 barrel 门
  - 断言 `components/workpaper/composables/index.ts` 现算 `exists == False`
  - 现算 7 个 `useK{n}DualMode.ts` 行数（`split("\n")` 口径）= 115/115/115/126/126/125/116，合计 **838**；并断言 `splitlines()` 得 **831**（7 个各少 1）
  - _Property: KA-P5, KA-P6_

---

## 阶段 1：BP-5 orphan 清理与内联 IIFE 收口（Task 3 ~ 8）

- [ ] 3. 7 个 orphan 的两阶可达性判定
  - 现算 7 个文件的生产边与测试边**各为 0**
  - 结合 Task 2 的 barrel 门，两侧都验「一阶边数 0 **且** barrel 不存在」⇒ 二阶恒 0
  - _Property: KA-P4, KA-P5_

- [ ] 4. 7 个 orphan 的 legacy 端点清册（与 lane 2 反向对照）
  - 现算 7 个 orphan **各 1 处 `onlyoffice/health`、0 处 `onlyoffice-config`**
  - 🔴 反向对照：断言 lane 2 的 6 个 live composable **各有 1 条生产边且各调 1~2 处 config**（两侧都验，证明本 lane 的 config=0 不是漏扫）
  - _Property: KA-P7_

- [ ] 5. 删除 7 个 orphan
  - 删前跑全量测试留基线；删除；删后再跑并断言**零回归**
  - 断言删除路径与其余七份 slice 的删除路径集合**不相交**
  - 断言删除后 `onlyoffice/health` 的 K 域命中从 20 降为 **13**（7 个 orphan 的 7 处消失，宿主内联的 7 处仍在）
  - _Property: KA-P8, KA-P7_

- [ ] 6. 7 宿主内联 IIFE 的特征清册与 localStorage 分裂登记
  - 现算 7 宿主 `const dualMode = (() => ` **各 1 处** ∧ `import { useK{n}DualMode }` **各 0 处**
  - 🔴 现算前缀撞车 **3 条**（K4/K5/K6）∧ 孪生无持久化 **4 条**（K1/K2/K3/K7），断言 3+4 == 7
  - 现算 7 宿主其余特征：`GtOnlyOfficeSheet` 各 4 · `el-segmented` 剥注释后各 1 · `useChecklistPersistence` 各 3 · `useWorkpaperEntryDualMode` 各 **0** · `v-if` 门控各 1 · `checklist-responses` 各 **0** · notice 两符号各 **0**
  - 🔴 断言 `apiProxy` 与 `publish-to-tb` **只 K6 宿主各命中 1**
  - _Property: KA-P9, KA-P10, KA-P13, KA-P14_

- [ ] 7. 宿主内联实现改走 sync bridge + localStorage 收敛
  - 7 宿主的 `onlyoffice/health` 直调改走 bridge materialize；断言处置后该端点 K 域命中降为 **0**（13 composable 的在 lane 2 处置、7 orphan 的已随 Task 5 消失）
  - 🔴 撞车 3 条（K4/K5/K6）的前缀**两处同时改**，收敛到 `workpaper-sync-mode:`
  - 🔴 无持久化 4 条（K1/K2/K3/K7）明确目标态并落实（不得沿用「一边有一边无」）
  - 🔴 列偏好类 `useK1DetailColumnPrefs.ts` / `useK4DetailColumnPrefs.ts` **不动**（引用 KC-18）
  - _Property: KA-P11, KA-P12, KA-P50_

- [ ] 8. BP-7 在 7 宿主挂 notice
  - 按 KC-14 口径选符号（组件名 `GtEntrySyncCapabilityNotice` 全平台 48 / 模块名 `workpaperEntrySyncNotice` 全平台 2）
  - 断言挂载前 7 宿主两符号命中**都是 0**，挂载后按选定符号命中 7
  - _Property: KA-P13_

---

## 阶段 2：BP-4 writeoff adapter 化（Task 9 ~ 12）

- [ ] 9. 5 hop 写路径逐跳实证 + 裁决
  - 逐跳定位（按常量名与端点字面量，不写行号）：`buildSavePayload()` → `emit('save', …)` → `handleChildSave()` → `useChecklistPersistence` 的 PUT → 后端 PUT 处理器
  - 断言末端 `backend/app/routers/checklist_responses.py` 的 PUT 处理器**真实存在**（非 404）⇒ `is_client_only == False`，裁 `must_be_adapter_borne`
  - 🔴 显式登记「纯客户端本身不是裁 `single_onlyoffice` 的理由」（AC 12.8 唯一判据是「无 HTML 对端」）
  - _Property: KA-P15, KA-P16_

- [ ] 10. 五个传输键的精确字面量口径 + 子串反证
  - 现算五键精确命中 **9 / 2 / 2 / 8 / 3**
  - 🔴 反证：`K1-9-writeoff` 子串命中 **12** vs 精确 **9**，差 **3**（`'K1-9-writeoff-total'` 被算进去）⇒ 守卫口径必须是精确字面量
  - 现算 7 个猜键精确命中**各为 0**（非空反向分母）
  - 🔴 现算裸 `'K1-9'` **13 处 / 6 文件**（`K1TabWriteoffCheck.vue` 4 · `K1TabIndex.vue` 3 · `useK1ImportExport.ts` 2 · `useK1WriteoffImportExport.ts` 2 · `k1SheetProgress.ts` 1 · `GtK1OtherReceivables.vue` 1），判为 **sheet 码不是 item_id**；如实登记 slice 的 **12 与 11 两个都错**
  - _Property: KA-P17, KA-P18, KA-P19, KA-P20_

- [ ] 11. OO 对端映射与行数错配
  - 断言 `K1 其他应收款.xlsx` 有 sheet `坏账准备转回（收回）、核销检查表K1-9` ∧ 无 adapter/contract 映射 ⇒ `oo_counterpart_status == absent`；🔴 **不是「无 HTML 对端」**
  - 现算该 sheet `r=25 c=8 merged=2` / 公式 **6** / **裸 IF 0**；UUID 列 **9**
  - 建立 payload ↔ 模板四行映射：`tables.reversal[]`↔R12:R14 · `tables.writeoff[]`↔R18:R20 · `reversalTotal`↔R15 只 E 列 · `writeoffTotal`↔R21 只 C 列
  - 🔴 adapter 显式处理**行数错配**（模板固定 3 行 vs HTML 动态行），给「超出 3 行时的扩行策略」与「少于 3 行时的留空策略」
  - _Property: KA-P21, KA-P22, KA-P23_

- [ ] 12. 发 K1 per-entry contract（`[ ]*` 依赖 BP-1）
  - 声明 managed table = `K1-9-writeoff` ↔ `坏账准备转回（收回）、核销检查表K1-9`
  - 🔴 两个 `derived_total` 键（`K1-9-reversal-total` / `K1-9-writeoff-total`）标派生态，**禁标 `mode:"input"`**；它们与模板 footer 一一对应且由 `computed` 产出 ⇒ Property 24 的精确落点
  - 两个 `cross_sheet_read` 键（`K1-3-baddebt-rows` / `K1-11-related-party`）标只读上游
  - `row_delete_api_kind` 用四元组（K1 侧现算形态：`useK1WriteoffCheck.ts` 的 `(section:'reversal'|'writeoff', id)` arity=2 + 调用点字面量 `('reversal', row.id)` / `('writeoff', row.id)`）
  - _Property: KA-P24, KA-P17_
  - **注**：`[ ]*` —— 发布生产契约需 approved authority model（BP-1），本任务只交付契约草案 + 判据

---

## 阶段 3：BP-8 位置化 + 下标族双重叠（Task 13 ~ 15）

- [ ] 13. 本 lane 24 处位置化清册与归族
  - 现算 **24 处**：K5 **7** · K6 **7** · K7 **6** · K1 **3** · K3 **1**；断言 **K2 / K4 为 0**（对照组）
  - 引用 KC-6 的三行布尔判别式（不复述），逐处归 family_a / family_b
  - 🔴 断言 `K7TabDisclosureSoe.vue` 里形如 ``String(raw?.id || `grant-${idx}-${Date.now()}`)`` 的那处归 **family_b**（按形态定位不写行号）
  - 断言本 lane 24 + lane 2 的 21 == **45** ✓
  - _Property: KA-P35, KA-P36_

- [ ] 14. 🔴 组合判据：位置化身份 × 下标族删行
  - 现算本 lane 下标族 removeRow 站点（形态 `$index` / `idx: number` / `actualIdx` / `tableIndex`），断言集中在 **K3/K4/K5/K6/K7**
  - 🔴 加**组合判据**：**删中间一行后，剩余行的身份集合不变**
  - 反证两条单独判据都抓不到：只看位置化身份 → 不知删行会否触发；只看下标族 removeRow → 不知身份也是下标
  - _Property: KA-P37_

- [ ] 15. 位置化身份修复（grandfather 旧 id）
  - 新增行改走值化身份（时间戳 + 随机，不含下标）
  - 🔴 已落库 id **grandfather 不重写**（真库 K1 的 `K1-2-r-{hex}` 与 K2 的 `r-{base36}` 已落库）
  - removeRow 改**按身份删**不按下标删
  - 跑 Task 14 的组合判据断言通过
  - _Property: KA-P38, KA-P37_

---

## 阶段 4：模板层治理与孤儿键清理（Task 16 ~ 20）

- [ ] 16. definedName 基线冻结（🔴 K 循环全部 65 个断链都在本 lane）
  - 现算 **81 / 含 `#REF!` 65**：K4 **43/36** · K2 **37/29** · K6 **1/0** · K1/K3/K5/K7 **各 0**
  - 登记基线 + 断言**不增长**，**不删**（引用 KC-9）
  - _Property: KA-P39_

- [ ] 17. K1 双变体披露表 70 格 `#REF!` 的覆盖层修复
  - 现算两表**各 35 格 / 8 行**；算术自检 `4×5 = 20` + `5×3 = 15` == **35** ✓
  - 🔴 断言 **E 列 `=IF(C{r}=0,0,C{r}/$B$18)` 活着** ⇒ 定性为**部分断链**非整表失效
  - 断言合计行 `R130` 的两个 SUM 与 `R141` 的 SUM **恒传播 `#REF!`**
  - 走**覆盖层**修（FC-5 例外新增一条），**不改源模板字节**
  - 🔴 判据载荷须「只有这两个子区有数」，否则其他区的正确值会掩盖错误 ⇒ 假绿
  - _Property: KA-P25, KA-P26, KA-P27, KA-P28_

- [ ] 18. 🔴 双变体账龄分层深度差异登记
  - 现算上市公司表 = R9-R11 三分档 + R12 内层小计 + R13-R17 五分档 + R18 外层小计（**3+5 两层**）
  - 现算国企表 = R7-R12 **六档一层** + R13 小计
  - 断言**两变体不共用同一套行映射**
  - 🔴 断言上市表 R18 `=SUM(B12:B17)` 外层含内层小计是**正确写法**（内层明细已被 R12 吸收，不重不漏）⇒ 纳入 KC-13② 的扫描误报白名单
  - _Property: KA-P29_

- [ ] 19. K2 孤儿 per-row 键清理
  - 现算 `审定表K2-1` 的**一表 9 键组**（1 主键 + 8 per-row）
  - 🔴 比对 rowId 集合，断言 **4 个孤儿**（`K2-1-r-ryx6og-{begin,unadj}` / `K2-1-r-yqfa02-{begin,unadj}`，值全空串）
  - 立判据：per-row 键 rowId 集合 ⊆ 主键载荷 rowId 集合
  - 🔴 清理**不得误删**有值的 4 个（`r-ls0ldh-begin='-732505.4'` / `-unadj='-1312178.93'` / `r-5ac9vk-begin='-377709.19'` / `-unadj='-406014.85'`）
  - _Property: KA-P30, KA-P31_

- [ ] 20. `审定表K2-1` 纯派生标注
  - 现算 `r=23 c=16 merged=9`；断言数据区 **R7:R13 连 A 列都是** `='明细表K2-2'!A{n}`
  - 契约标 `derived` + `editable_labels: false`；🔴 登记「OO 侧无输入位，写回方向空转」⇒ **不得作 canary**
  - 🔴 断言 R5 的 J5/L5 含**单元格内换行符** ⇒ 三边比对**逐格字节**，禁 strip、禁全半角归一
  - 断言 R14 空行 + R15 `=SUM(B7:B14)` 含空行属 KC-12 正常形态**不是缺陷**
  - _Property: KA-P32, KA-P33, KA-P34_

---

## 阶段 5：sheet 名口径裁定 + 真库基线 + 复盘（Task 21 ~ 24）

- [ ] 21. 🔴 sheet 名字符缺陷分摊口径裁定（写死判据前必须先裁）
  - 现算全 K 名中半角空格 **21 处**，逐册拆分（K1 1 · K2 1 · K11 1 · K4 5 · K5 8 · K6 ?）
  - 🔴 **先裁定 K6 的 `减值准备测试表（后续计量） K6-5` 与 `处置组减值测试表（后续计量） K6-6` 的括号后空格是否计入「名中半角空格」**：计入则 K6 = 5、本 lane = 20、lane 2 = 1（20+1=21 ✓）；不计入则 K6 = 4、本 lane = 19、另需找出第 21 处（19+1+1=21 ✓）
  - 裁定后把明细写死进判据；断言括号不配对 **3 + 2 == 5** ✓ · 全半角 **2 + 0 == 2** ✓ · 重复字 **1 + 0 == 1** ✓
  - 登记 K7 独有 `附注披露信息（国有企业）`
  - _Property: KA-P40, KA-P41, KA-P42_

- [ ] 22. 本 lane 模板层其余基线
  - 现算裸 IF **291**（K1 91 · K2 76 · K6 47 · K7 40 · K3 22 · K5 9 · K4 6）
  - 🔴 登记**四张 200+ 行程序表全在本 lane**（`实质性程序表 K2A` 205 · `实质性程序表K3A` 210 · `实质性程序表 K4A` 207 · `实质性程序表 K6A` 207），其余册程序表都在 20~35 行
  - 🔴 断言 **KC-12 的 5 处跳跃式 footer 全在本 lane**（`审定表K1-1` 3 处 + `坏账准备测算K1-8` 1 处 + `初始确认检查表K6-4` 1 处），lane 2 与 foundation 各 **0**
  - 现算 `GT_Custom` 在 K1/K2/K3/K7 存在、K4/K5/K6 无
  - 现算 `审定表K1-1` `r=89 c=13 f=547 bareIF=60`（全 K 最复杂审定表）
  - _Property: KA-P43, KA-P44, KA-P45_

- [ ] 23. 真库基线 + 金额维度 roundtrip（用本 lane 自己的真金额）
  - 现算本 lane 真库非空键 **54**（K1 26 · K2 11 · K5 6 · K6 5 · K3 3 · K4 2 · K7 1），载荷合计 **295,573 B**
  - 🔴 断言 `K1-2-detail-rows` 独占 **274,741 B**（占 K1 载荷 95%，全平台最大）
  - 🔴 **用 K2 披露层的真金额跑金额维度 roundtrip**（`K2-disc-listed-main` 823 B 含 2500000/1800000 · `K2-disc-soe-main` 509 B 含 1234567.5 · `K2-disc-listed-carbon` 611 B 碳排放配额）⇒ **无须合成载荷**（对比 foundation 的 canary 金额全 0 须另造）
  - 现算本 lane TB 发布门 **8 处 / 7 条 entry**（K5 占 2 · 🔴 K6 在宿主层）；断言与 foundation 1 + lane 2 5 合计 **14** ✓
  - 引用 KC-2 断言 K5 走 `shared_platform_persistence_adapter` 族（裸端点 0 / `useChecklistPersistence` 3），**不判为缺陷**
  - _Property: KA-P46, KA-P47, KA-P48_

- [ ] 24. 复盘与交付边界
  - 🔴 显式登记 **BP-1 / BP-2 / BP-3 对本 lane 的四件主线事都不是阻塞**（orphan 删除 / 位置化修复 / 模板层登记 / 孤儿键清理）⇒ **这四件已实施完**；只有发 contract、注册 adapter、产 evidence 卡它们
  - 🔴 显式登记 **BP-6 不落本 lane**（它指向 K8~K13）；本 lane 的 14 处 `health` 直调分两类已分别处置
  - 🔴 显式登记 **本 lane 不产 canary**，它承接 foundation canary 未覆盖的 **BP-5 主线形态**
  - 脚本核验：本 spec 只**引用** KC-1~KC-24 编号、**零复述正文**；`KA-P1`~`KA-P52` 无重号无缺号；无 U+FFFD
  - _Property: KA-P49, KA-P50, KA-P51, KA-P52_

---

## 阻塞项归属表

| BP | 对本 lane | 处置 |
|---|---|---|
| **BP-1 / BP-2 / BP-3** | 🔴 **四件主线事都不是阻塞**，只卡「发 contract / 注册 adapter / 产 evidence」 | 后者标 `[ ]*` |
| **BP-4** | ✅ **本 lane 交付**（只 K1） | Task 9~12 |
| **BP-5** | ✅ **本 lane 交付**（7 条全集） | Task 3~7 |
| BP-6 | 🔴 **不落本 lane**（指向 K8~K13） | lane 2 |
| BP-7 | ✅ 本 lane 的 7 宿主 | Task 8 |
| **BP-8** | ✅ **本 lane 交付 24 处**（K5 7 · K6 7 · K7 6 · K1 3 · K3 1） | Task 13~15 |
| BP-9 | 地基已立判据 | 引用 foundation |
