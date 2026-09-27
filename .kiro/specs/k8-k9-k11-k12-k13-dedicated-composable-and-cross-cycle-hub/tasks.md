# K8/K9/K11/K12/K13 专用 composable 与跨循环枢纽 — 任务

> **实施纪律**
> - 上游共同裁决 **KC-1 ~ KC-24** 在 `k-cycle-sync-foundation-and-first-canary/design.md`，🔴 **本 spec 只引用编号不复述**。
> - 🔴 所有计数**现算**并与 `design.md` 等值比对，禁写死。
> - 🔴 判据锚点用**常量名 / 端点字面量 / 形态特征**，**禁写死行号**。
> - 🔴 行数口径统一 `len(text.split("\n"))`（KB-P8）。
> - 🔴 **BP-1 / BP-2 / BP-3 对本 lane 的五件主线事都不是阻塞**（legacy 端点收口 / localStorage 收敛 / 位置化修复 / K11 键冻结清单 / 模板层登记）⇒ 这五件**可立刻实施完**；`[ ]*` 只标「发 contract / 注册 adapter / 产 evidence」。
> - 🔴 **BP-4 与 BP-5 都不落本 lane**（全在 lane 1）。
> - 🔴 本 lane **不产 canary**，但 foundation 的 canary 与本 lane **同属 BP-6 组** ⇒ 其形态判据可直接外推到本 lane 5 条。
> - 变异与实景脚本**复用** `backend/scripts/diagnose/` 既有三个 K 脚本，**不新写**。

---

## 阶段 0：前置门（Task 0 ~ 2）

- [ ] 0. entry 边界与切分自检
  - 列出本 spec 的 **5 条 entry_id 全名**；断言与 foundation 的 `xlsx/gt-k10-other-income` 及 lane 1 的 7 条**三者无交集**、并集 **13**
  - 断言 5 条的 `capability_target_blocked_by` **全部含 BP-6**，且 K 循环含 BP-6 的 entry 恰好是 K8~K13 共 6 条、去 K10 后是这 5 条（两侧都验）
  - 现算本 lane 六项规模并与 design 等值：sheets **49** · 键 **323** · 裸 IF **424** · BP-8 **21** · 真库非空键 **6** · definedName **0**
  - _Property: KB-P1, KB-P2_

- [ ] 1. 反向对照门（证明本 lane 的非零结论不是漏扫）
  - 🔴 现算 lane 1 的 7 个 `useK{n}DualMode.ts` 生产边与测试边**各为 0**、`onlyoffice-config` **全为 0**
  - 现算本 lane 5 个 **各 1 条生产边**、`config` 非 0 ⇒ 两侧都验
  - _Property: KB-P3, KB-P4_

- [ ] 2. 端点扫描器与行数口径
  - 端点正则**认反引号**；🔴 变异反证：改成只认单/双引号时，本 lane 的 `onlyoffice-config` 命中从 **8 处降为 0**
  - 现算 5 个 composable 行数（`split("\n")`）= 189/182/154/158/158 = **841**；断言 `splitlines()` 得 **836**（各少 1）
  - _Property: KB-P7, KB-P8_

---

## 阶段 1：BP-6 legacy 端点与持久化收口（Task 3 ~ 6）

- [ ] 3. 5 个 live composable 的端点清册
  - 现算 `onlyoffice/health` **各 1（合 5）** · `onlyoffice-config` **K8/K9/K11 各 2 + K12/K13 各 1（合 8）**
  - 🔴 与 foundation 的 K10（health 1 / config 1）对账，断言 BP-6 全集 6 个 composable 的 config = **9 处 / 6 文件**，并写明 slice 的 6 是**文件数不是处数**
  - _Property: KB-P5, KB-P6_

- [ ] 4. 两类端点直调改走 sync bridge materialize
  - 5 个 composable 的 `onlyoffice/health` 与 `onlyoffice-config` 直调全部改走 bridge materialize
  - 断言处置后本 lane 两端点命中**都降为 0**，bridge materialize 路径命中非 0
  - _Property: KB-P9_

- [ ] 5. localStorage 收敛（只收模式偏好）
  - 现算 5 个 composable 的前缀 **5 个 / 12 处**（K8 2 · K9 2 · K11 2 · K12 3 · K13 3），收敛到 `workpaper-sync-mode:`
  - 🔴 断言列偏好类 `useK10DetailColumnPrefs.ts` / `useK11DetailColumnPrefs.ts` / `useK10GrantColumnPrefs.ts` **未被改动**（引用 KC-18）
  - 🔴 断言 5 宿主 `localStorage` 命中**全为 0**（与 lane 1 的 K4/K5/K6 各 2 处形成对照）
  - _Property: KB-P10, KB-P11_

- [ ] 6. KC-15 落地：K8/K9 的 `disabled` 门控二分支判据
  - 现算宿主 `v-if` 门控 K11/K12/K13 各 1、🔴 **K8/K9 为 0**
  - 🔴 去 composable 找 `disabled: !isOoAvailable`（在 `useK8DualMode.ts` / `useK9DualMode.ts` 的 `modeOptions` computed 里，按形态定位不写行号），断言宿主层命中 **0**
  - 判据写成二分支：「有 `v-if`」**或**「composable 里有 `disabled: !isOoAvailable`」；反证统一写「必须有 `v-if`」会假红 K8/K9
  - 🔴 现算宿主 `isOoAvailable` = K8 **0** / K9 1 / K11 3 / K12 2 / K13 3 ⇒ 判据范围含 composable
  - 断言 `el-segmented` 剥注释后 5 宿主**各恒 1 处**
  - _Property: KB-P12, KB-P13, KB-P14, KB-P15_

---

## 阶段 2：KC-8 跨循环枢纽 K11 的键冻结（Task 7 ~ 9）

- [ ] 7. K11 的 9 键消费方清册
  - 逐条现算 9 个键的消费方：`K11-2-detail-rows`（**4 方含 H1 pilot**）· `K11-2-fixed-asset-occurrence`←H1 · `K11-2-rou-occurrence`←H8 · `K11-2-intangible-occurrence`+`-source-amount`←I1 · `K11-source-{H1,H3,H8,I1}-amount` 各 1
  - 全局现算：非 K 域消费 K 键 **70 个**；反向 K 域引非 K 键仅 **4 种**
  - 🔴 显式登记「JC-17 在 J 是**完全自闭**、K 是**强命中**」⇒ 照抄 J 会漏掉整条跨循环风险
  - _Property: KB-P16, KB-P18, KB-P19_

- [ ] 8. 建立冻结清单与 H1 golden 回归钩子
  - 9 个键写入冻结清单，**不得改名**
  - 建立回归钩子：任何触及这 9 键的改动 SHALL 触发 **H1 pilot golden 回归**
  - 断言 H1 的 `adapter_id` 现算非空、契约 `h1.disposal_check.json` 现算 `review_status == reviewed`
  - _Property: KB-P17_

- [ ] 9. 🔴 K11「有消费方但无载荷」的风险登记
  - 现算 `K11-%` 真库行数 == **0**
  - 登记为「有 4 方跨循环消费者但真库无载荷」⇒ 消费方读它**恒取空而不报错**
  - 🔴 与 H 循环 BP-12「猜键回退链静默取空」并列为**同型风险**，给检测判据（消费方读空时应告警而非静默）
  - K11 自己的 roundtrip 用合成载荷标 `synthetic_payload_no_live_db_baseline`；H1 golden 回归用 **H1 侧自己的载荷**
  - _Property: KB-P20, KB-P21_

---

## 阶段 3：BP-8 位置化与「一表两路两套身份」（Task 10 ~ 13）

- [ ] 10. 本 lane 21 处位置化清册与归族
  - 现算 **21 处**：K8 **8** · K9 **7** · K11 **4** · K12 **2**；🔴 断言 **K13 为 0**（对照组）
  - 引用 KC-6 的三行布尔判别式（不复述），逐处归族
  - 断言本 lane 21 + lane 1 的 24 == **45** ✓
  - _Property: KB-P22_

- [ ] 11. 🔴 「一表两路两套身份」的双路扫描判据
  - 现算 `useK8Cutoff.ts` / `useK9Cutoff.ts` 的**两条路**（按形态定位不写行号）：
    - 新增行路径 `` rowKey: `row-${idx}-${Date.now()}` `` ⇒ **family_c 非缺陷**
    - 反序列化路径 `` raw.rowKey ?? `row-${idx}` `` ⇒ 🔴 **family_b 缺陷**（历史载荷缺 `rowKey` 时静默退化）
  - 🔴 断言「主身份机制干净 ≠ 该表干净」；判据必须**两条路都扫**
  - 🔴 断言 slice 的 `dynamic_row_identity.tables[]` 与 `positional_identity_inventory` 两容器**并集覆盖全部命中、交集为空**（两侧都验）
  - 现算 family_c 全 K **3 处**，本 lane 占 **2**，第 3 处在 lane 1
  - _Property: KB-P23, KB-P24, KB-P25_

- [ ] 12. family_c 真落库确证 + family_d 实证
  - 现读真库 `K8-6-rows`（195,960 B），断言 `"rowKey":"row-0-1784807974207"` 形态（`idx=0` + 13 位时间戳）
  - 🔴 断言同载荷另有 `"index":1` 字段（展示序号）⇒ 这是 **KC-6 的 family_d 不计入 `total_hits`** 的实证来源
  - 现算 `positional_row_id_template`（全 K 13 处非 0）本 lane 占比，断言这 13 处是位置化 48 处的**子集**
  - _Property: KB-P26, KB-P27_

- [ ] 13. 位置化修复（grandfather 旧 id）
  - 新增行走值化身份；🔴 已落库 id **grandfather 不重写**（真库 `K8-6-rows` 与 `K9-1-rows` 已落库）
  - 🔴 反序列化兜底 `` ?? `row-${idx}` `` 改为「缺身份时生成新的值化身份」而非退化成下标
  - _Property: KB-P28_

---

## 阶段 4：变体轴口径 + 模板层登记（Task 14 ~ 16）

- [ ] 14. 🔴 K8/K9 截止性测试双 sheet 的变体轴口径裁定
  - 现算四张 sheet 的尾码与几何：`K8-6` r=44 c=11 / `K8-7` r=44 c=12 / `K9-6` r=44 c=11 / `K9-7` r=44 c=12
  - 🔴 断言 **HC-5 / JC-11 的「同尾码双 sheet」在 K 全域为 0** ⇒ 这四张是**不同尾码的方向变体**，照抄那两条判据会误判
  - 🔴 把 K 的变体轴判据改写为「sheet 名前缀相同 + 尾码相邻 + 语义成对」；并登记 lane 1 的 K6-5/K6-6 是同型的**对象变体**
  - 现算 `sampling/cutoff-test` **2 文件**，契约声明它**不是 checklist 写路径**
  - _Property: KB-P29, KB-P30, KB-P32_

- [ ] 15. 本 lane 模板层基线（含括号缺陷分摊对账）
  - 现算 sheets **49**（🔴 K11 只 **7** 张是全 K 最少）· 裸 IF **424**（K9 **175** + K8 **136** + K11 39 + K12 37 + K13 37，🔴 占 13 entry 册 715 的 **59%**，三份 spec 最高）
  - 断言 definedName **5 册全 0** · `#REF!` **0 格** · 跳跃式 footer **0 处**
  - 现算 hidden `GT_Custom`：K12/K13 **有**、K8/K9/K11 **无**
  - 🔴 现算括号半/全混不配对本 lane **2 处**（`K8-6` / `K9-6`），断言 **2 + 3（lane 1）== 5** ✓（引用 KC-10）
  - 现算名中半角空格本 lane **1 处**（`实质性程序表 K11A`），与 lane 1 的口径裁定结论对账
  - 🔴 断言 **5 张「调整分录汇总」与 canary 所在的 `调整分录汇总K10-3` 完全同构**（`c=10 f=7 bareIF=0 merged=3`）⇒ canary 判据外推的直接依据
  - 现算审定表复杂度：K9-1 f=**223** / K11-1 f=**190**（全 K 第二、第三，第一是 lane 1 的 K1-1 f=547）
  - _Property: KB-P37, KB-P31_

- [ ] 16. 写路径与其余收口
  - 现算 TB 发布门 **5 处 / 5 条 entry**（`useK8Adjudication.ts` · `useK9Adjudication.ts` · `useK11Adjudication.ts` · `K12TabAdjudication.vue` · `K13TabAdjudication.vue`）；断言 **5 + 8（lane 1）+ 1（foundation）== 14** ✓
  - 现算 `checklist-responses` 载体：5 个 `useK{n}FormData.ts` 各 2 处 + `useK11Detail.ts` 1 处 ⇒ 全属 `formdata_composable_bare_endpoint` 族
  - 现算披露双变体 **10 处**；断言 **10 + 14（lane 1）+ 2（foundation）== 26** ✓
  - 现算 `useAdjustmentCentralSync` 5 条各 **3 处** ⇒ roundtrip 的**第二写入方**
  - 🔴 现算 OCR 两形态在本 lane 的分布并**统一为一种**（引用 KC-19）
  - 🔴 现算 derived_total 的 6 个「仅中置命中」键里本 lane **3 个**（`K11-2-total-occurrence` · `K8-2-total-audited` · `K9-2-total-audited`），断言 **3 + 3 == 6** ✓
  - BP-7：在 5 宿主各挂 notice（按 KC-14 口径选符号）；断言挂载前两符号命中**都是 0**
  - _Property: KB-P39, KB-P38, KB-P40_

---

## 阶段 5：roundtrip 二分策略 + 复盘（Task 17 ~ 19）

- [ ] 17. 🔴 真库载荷三分与 roundtrip 策略
  - 现算非空键 **6** / 载荷 **211,679 B**，并按下表二分：

| entry | 策略 |
|---|---|
| **K8** | ✅ **真库实证**：用 `K8-6-rows` **195,960 B** 真业务载荷（真凭证号/日期/金额/科目码），**金额维度无须合成** |
| **K9** | ✅ 真库实证；🔴 但 `K9-1-rows` 金额字段**全 0**（与 foundation canary 同型「骨架已落库业务未填」）⇒ 金额维度须合成或改用 K8 载荷 |
| K12 | ⚠️ 结构可验；`K12-4-check-rows` 只 2 B 是**空数组不是有效载荷**；`K12-review-session-*` 按 KC-5 排除 |
| 🔴 **K11 / K13** | 🔴 **真库 0 行** ⇒ 合成载荷 + 标 `synthetic_payload_no_live_db_baseline`，**不得宣称有真库实证** |

  - _Property: KB-P33, KB-P34, KB-P35, KB-P36_

- [ ] 18. 发 5 条 per-entry contract（`[ ]*` 依赖 BP-1 / BP-2）
  - 🔴 **复用 foundation canary 的 BP-6 形态判据**（同组，5 张调整分录汇总与 `调整分录汇总K10-3` 完全同构）
  - 逐条声明 managed table / derived_total（含 3 个仅中置命中键）/ `row_delete_api_kind` 四元组 / 跨循环冻结键（K11 的 9 个）/ 排除的 review-session 键（K12）
  - 🔴 K11/K13 的 roundtrip 证据标 `synthetic_payload_no_live_db_baseline`
  - _Property: KB-P43, KB-P40, KB-P20_
  - **注**：`[ ]*` —— 发布生产契约需 approved authority model（BP-1）与 instrumentation candidate（BP-2）

- [ ] 19. 复盘与交付边界
  - 🔴 显式登记 **BP-1 / BP-2 / BP-3 对本 lane 的五件主线事都不是阻塞** ⇒ 这五件**已实施完**；只有发 contract、注册 adapter、产 evidence 卡它们
  - 🔴 显式登记 **BP-4 与 BP-5 都不落本 lane**（全在 lane 1）
  - 🔴 显式登记 **本 lane 不产 canary**，但 foundation canary 与本 lane **同属 BP-6 组** ⇒ 形态判据可直接外推（**这是本 lane 相对 lane 1 的优势**，lane 1 的 BP-5 形态完全无 canary 覆盖）
  - 脚本核验：本 spec 只**引用** KC-1~KC-24 编号、**零复述正文**；`KB-P1`~`KB-P44` 无重号无缺号；无 U+FFFD
  - _Property: KB-P41, KB-P42, KB-P43, KB-P44_

---

## 阻塞项归属表

| BP | 对本 lane | 处置 |
|---|---|---|
| **BP-1 / BP-2 / BP-3** | 🔴 **五件主线事都不是阻塞**，只卡「发 contract / 注册 adapter / 产 evidence」 | 后者标 `[ ]*` |
| BP-4 | 🔴 **不落本 lane**（只 K1） | lane 1 |
| BP-5 | 🔴 **不落本 lane**（K1~K7） | lane 1 |
| **BP-6** | ✅ **本 lane 交付 5 条**（BP-6 全集 6 条，K10 在 foundation） | Task 3~6 |
| BP-7 | ✅ 本 lane 的 5 宿主 | Task 16 |
| **BP-8** | ✅ **本 lane 交付 21 处**（K8 8 · K9 7 · K11 4 · K12 2；K13 为 0） | Task 10~13 |
| BP-9 | 地基已立判据 | 引用 foundation |
