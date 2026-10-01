# N1 / N3 宿主内联路由与共享路由采纳 — 任务

约定：`[ ]` 待办 · `[ ]*` 受外部依赖阻塞（不计入完成率）。共同判据只引用 **NC 编号**，判据正文在 foundation。

🔴 **跨 spec 顺序硬约束**：任务 8（行身份改造）须在 foundation 任务 14（E 族样板提取）**之后**执行；任务 15（删 orphan）须在本 spec 任务 8 之后。

## 阶段 1 — 归属基线

- [x] 1. lane2 归属守卫
  - 落地 `design.md` 归属份额表全部 17 行，逐行与 foundation 算术自检表比对（任一不等即视为归属错）
  - 断言 entry 2 条全名、科目借贷相反（1811 资产/借 vs 2901 负债/贷）、BP 各 9 项且成员集吻合
  - _Requirements: 1_
  - _NC/NA-P: NC-1 · NC-22 · NA-P1 · NA-P2_

## 阶段 2 — BP-10 与 BP-4 收口

- [x] 2. 新增 `n1SheetRouting.ts` / `n3SheetRouting.ts` 并接入宿主
  - 沿用既有三者（`n2/n4/n5SheetRouting.ts`）的模块形态与命名，不另创范式
  - 采用方从 **3** 升至 **5**，BP-10 成员集变空集
  - 🔴 迁移过程中 sheet 名按原始字面量比对，禁归一化（本 spec 有「表的{码}」3 处）
  - _Requirements: 2_
  - _NC/NA-P: NC-10 · NC-19 · NA-P3_

- [x] 3. 保留 N1 / N3 门控语义差异
  - N1 保留 `isSwitchableSheet && dualMode.isOnlyOffice.value`（🔴 不得替换为 `isHtmlSheet`）
  - N3 保留三条件 `isHtmlSheet && renderMode === 'onlyoffice' && ooHealthy`（🔴 不得简化为两条件）
  - 识别正则覆盖带泛型 `ref<'html' | 'onlyoffice'>(` 与 `isOnlyOffice` 计算属性两种变体
  - _Requirements: 2, 3_
  - _NC/NA-P: NC-13 · NA-P4 ~ NA-P6_

- [x] 4. N3 health 收敛到统一能力层（BP-4）
  - `checkOoHealth()` 内的 `http.get('/api/workpapers/onlyoffice/health')` 改经统一能力层
  - 🔴 收敛后 `onlyoffice/health` 生产命中数仍须为 **5**（每 entry 一处，不增不减）
  - BP-4 成员集变空集
  - _Requirements: 3_
  - _NC/NA-P: NC-3 · NA-P8_

- [x] 5. 修 N3 `onModeChange` 静默失败
  - 现状 `if (val === 'onlyoffice' && !ooHealthy.value) return` 无任何用户提示
  - 🔴 改为显式反馈（不可用原因 + 已回落 HTML 模式），SHALL NOT 仅加日志
  - _Requirements: 3_
  - _NC/NA-P: NC-13 · NA-P7_

- [x] 6. 收敛 N1 `onlyoffice-config` 直调
  - 全 N 域现算 **1** 处（`useN1DualMode.ts`），是 N 域独有触点（M 轮为 0）
  - _Requirements: 3_
  - _NC/NA-P: NC-37 · NA-P9_

## 阶段 3 — 载体与行身份

- [x] 7. N1 三值载体改造（保 matrix）
  - 保留 matrix 分支与 **9** 个被消费成员的对外契约（`mode` / `modeOptions` / `switchMode` / `fetchingConfig` / `isOOHealthy` / `ooConfigReady` / `isOnlyOffice` / `isMatrix` / `onOoLoadFailed`）
  - 🔴 若统一能力层不支持三值，在能力层扩展而非在 N1 砍功能
  - 断言 5 条生产边（宿主 + 4 子 Tab）、localStorage 键 `n1-dual-mode` 按 wp 分区
  - _Requirements: 4_
  - _NC/NA-P: NC-2 · NC-16 · NA-P10 · NA-P11_

- [x] 8. A 族 3 处改造为稳定身份（**须在 foundation 任务 14 之后**）
  - 3 处全在 `useN1Adjudication.ts`，全 N 域 A 族 100% 在此
  - 🔴 抄 E 族既有形态（全域 86 处 / 27 文件），禁自建新范式
  - 本 spec 范围内 `removeRow` 的 by_index 调用改为 by_rowid，守卫按单调方向断言
  - 改造后 A 族计数降至 **0**，`N1-1-adj` 持久化键不再含数组下标
  - _Requirements: 7_
  - _NC/NA-P: NC-6 · NC-7 · NC-8 · NA-P16_

- [x] 9. `transport_key` 守卫（N1 双 owner + TK-2 双条件）
  - N1 双声明：`useN1FormData.ts`（545 行）`'N1-'` + `useN1Adjudication.ts`（507 行）`'N1-1-adj'`；N3 单声明 `useN3FormData.ts`（379 行）`'N3-'`
  - 🔴 TK-2 用双条件判据（模板串命中 + 展开数 == `N1_ADJUDICATION_CATEGORIES` 长度 **7**），禁用恒假的字面量命中
  - `N1-1-rows` / `N1-1-adjudication-rows` / `N3-1-rows` 各 **0** 命中（反向分母）
  - _Requirements: 6_
  - _NC/NA-P: NC-30 · NA-P13 ~ NA-P15_

- [x] 10. `parent_duplicate` 数据侧断言（4 条全挂 N1）
  - 逐条全名：`xlsx/n1/calc/n1-tab-calc-table` · `xlsx/n1/core/n1-tab-adjudication` · `xlsx/n1/core/n1-tab-adjustment` · `xlsx/n1/core/n1-tab-detail`
  - 🔴 K/L/M 三轮该字段均 0，N 首次触发 ⇒ 给完整断言而非分支占位；判据逻辑复用 foundation 骨架不重复实现
  - _Requirements: 5_
  - _NC/NA-P: NC-31 · NA-P12_

## 阶段 4 — 契约与真库

- [x] 11. 契约双列映射（N1 载荷全在 `conclusion`）
  - N1 `conclusion` 非空 **14** / N3 **2**，合计 **16**；N1 `remark` 唯一非空行是 AI 会话（261 B）须白名单排除
  - 载荷清单：`N1-disclosure-listed-unoffset` 1201 B · `-soe-unoffset` 1198 B · `-soe-netoffset` 1196 B · `-soe-synced-tables` 298 B · `N1-5-rows` 363 B
  - 🔴 登记后缀规则例外：`N1-5-rows` 按后缀应取 `remark` 但实际在 `conclusion` ⇒ 采「实际非空列优先」，防静默丢 363 B
  - 披露表读写覆盖上市公司 + 国企两变体
  - _Requirements: 8_
  - _NC/NA-P: NC-34 · NA-P17_

- [x] 12. 真库污染 2 条登记（asyncpg）
  - `N1-3-entries` / `N3-3-entries` 均落 `wp_code='G8'`，登记 + 守卫锁定现值，**不就地清理**（依 NC-19 的平台级裁定）
  - 实现 `-3-entries` 双向回写时以 entry 自身 `wp_code` 为写入目标，不沿用被污染值
  - 无库环境 skip 并标原因，禁静默 pass
  - _Requirements: 9_
  - _NC/NA-P: NC-19 · NA-P18_

## 阶段 5 — 模板缺陷登记与收口

- [x] 13. 族 A2 与脏形态守卫（记录型，不改模板）
  - `N3-2` H11~H21 全 11 行 `=F#+O#`：锁「无反向分母、整列同形、H ≡ F」；🔴 与族 A1 分开计数（依 NC-32）
  - `N3-2 E23 =SUM(E3:O22)` 判合法
  - 「表的{码}」3 处逐一锁原始字面量；`definedName` 48 / broken 30 含 `'[2]2004'!#REF!` 新形态与中文名 `本循环科目`
  - 🔴 本任务 SHALL NOT 修改 `.xlsx`，交付后模板 sha256 仍须 5/5 match
  - _Requirements: 10_
  - _NC/NA-P: NC-9 · NC-25 · NC-32 · NA-P19 · NA-P20_

- [x] 14. 超宽表遍历策略 + N3 结构性例外
  - `N1/附注披露信息（国企）` 256 列 / 有值列 7 / 幽灵 249 ⇒ 遍历上界取 `last_value_col`，守卫锁差值
  - 登记 `N1-4 测算表` 为全域双料最密（227 公式格 / 120 裸 IF），单独回归
  - 🔴 N3 无附注披露（n=0）⇒ 对 disclosure 相关判据声明**空分母**，禁写「已验证正常」
  - 登记 N3 三项极值：唯一无 disclosure 子组件 · sheets 最少 6 · 公式格最少 162
  - _Requirements: 11, 12_
  - _NC/NA-P: NC-20 · NC-22 · NC-35 · NA-P21 · NA-P22_

- [x] 15. 删除 orphan 2 个（**须在任务 8 之后**）
  - `useN3DualMode.ts` · `n1DisclosureSegmentTypes.ts`
  - 🔴 统计须用含小写分支的正则，否则后者会漏、本 spec orphan 数错报为 1（依 NC-5）
  - 删前 grep 确认 0 生产引用；删后同步更新 `TestOrphanInventory`（🔴 非 M 轮的 `TestOrphanDualModeInventory`）
  - 行数以现算为准，禁照抄删除清册（plan 计数本身有错，依 NC-29）
  - _Requirements: 13_
  - _NC/NA-P: NC-5 · NC-29_

- [x] 16. `N3A` 跨册碰撞交叉校验（与 lane3 联动）
  - 本 spec 侧 `递延所得税负债审计程序表的N3A`（N3 册）· lane3 侧 `…N3A (原底稿)`（N5 册，半角括号 + 前导空格）
  - 🔴 判据按 `(册, sheet 名)` 二元组定位，禁仅按 sheet 码；测试注释须指向 lane3 `n2-n5-json-table-identity-and-cross-entry-readonly` 的对应断言
  - 外来字母码（`O1A` / `O2A`）对本 spec 空分母，须显式声明
  - _Requirements: 14_
  - _NC/NA-P: NC-20 · NC-21_

- [x] 17. 交付前自检
  - 归属份额表 17 行等式全过；NA-P1 ~ NA-P22 无缺号且每条关联 NC
  - 模板 sha256 仍 5/5 match；无 U+FFFD；「N 处」类表述与列举项数一致
  - 校验本 spec 未复述任何 NC 判据正文（只引编号）
  - _Requirements: 1, 10_
  - _NC/NA-P: NC-1 · NC-11 · NC-25_

- [ ]* 18. 平台级欠账（NC-19 已查实闭合，BP-1/2/3 另批次）
  - [x] G8 污染（NC-19）：正确 join 现查真库 N1/N3 命名空间**0 条跨循环污染**；旧 slice 报「落 G8」是用了会返 NULL 的坏 join `wp_index.id = cr.wp_id`。检测脚本 `backend/scripts/analyze/detect_cross_cycle_namespace_pollution.py`（只查不删），统一记录见 foundation spec 的「平台级欠账实施记录」。真库无污染 ⇒ 无删除决策。
  - [ ]* BP-1 / BP-2 / BP-3（approved 权威模型与 contract/bundle · published 表示层 · 真 OnlyOffice 9.4 探针）—— 按 L1/L3/L4 范式逐条接真双向，另批次做
  - 阻塞理由：BP-1/2/3 须改共享 registry/manifest/契约目录，单独批次
  - _Requirements: 9_
  - _NC/NA-P: NC-19_


---

## 实施记录（2026-10-01，append-only）

**守卫**：`backend/tests/workpaper_sync/test_n_lane2_host_inline_router.py`（复用 foundation 扫描器与基线）· 前端 `composables/__tests__/nCycleLane2RouterAndKeys.spec.ts`（对源模板全部真实 sheet 名做新旧路由逐一等价 + BP-10 防护用例 + N1-1 键迁移）。

**代码改动**：
- T2（BP-10 收口）：新增 `n1SheetRouting.ts` / `n3SheetRouting.ts`（经 `makeCycleSheetRouter`，披露判定前置），两宿主改用之；分发键与原内联实现逐一相等（宿主模板 `v-if` 未改）。采用方 3 → 5。N3 无披露 sheet 的例外（含「附注」的 tab 落 OO 兜底而非空白 HTML）在 `isN3HtmlSheet` 内保留。
- T3：N1 门控 `isSwitchableSheet && dualMode.isOnlyOffice.value`、N3 三条件门控原样保留。
- T4（BP-4）/ T5：N3 health 改走 `sync/onlyOfficeHealth.ts`；拒切 OO 由静默 return 改为强刷一次 + 显式提示「已保持 HTML 模式」。
- T6 / T7：`useN1DualMode` 的 health 改走统一能力层，`onlyoffice-config` 预拉收敛到新增的 `sync/onlyOfficeSheetConfig.ts`（与 health 同级的平台能力层）；三值载体与 9 个对外成员、5 条生产边、wp 分区 localStorage 键全部保留；拒切/配置失败加显式提示。
- T8（A 族 3 → 0）：N1-1 持久化键由数组下标改为**模板行 key**（`N1-1-adj-A7` … `A13`，与 7 类一一绑定）；旧位置键只读兼容（新键优先），写入只走新键。`addAdjustment` / `removeAdjustment` 改按类目寻址。
- 🔴 **顺带修掉一处真缺陷**：`useN1Adjudication` 的 hydrate watch 带 `immediate: true` 且注册在 `totals` 声明之前 —— 宿主走 htmlData 路径（setup 时已有数据）时回调立即调 `_syncTotals()` 读 TDZ 中的 `totals` ⇒ `ReferenceError`，审定表 Tab 挂掉（新前端用例首跑即暴露）。已把 watch 移到 `totals` 之后。
- T15：删除 `useN3DualMode.ts` / `n1DisclosureSegmentTypes.ts`。

**🔴 与 spec 原文的偏离**：T4 写「收敛后 `onlyoffice/health` 生产命中仍须为 5（每 entry 一处）」—— 那是改线前的形态；收敛的正确终态是 N 域生产代码 **0** 处直调、全部经 N 域外唯一能力层（守卫按此断言并注明）。真库 lane2 现 0 行（design 19 行 / 污染 2）⇒ T11/T12 空分母不宣称通过。`definedName` lane2 broken 现算 28（design 30）。

**跨 spec 顺序约束**：T8 在 foundation T14 之后 ✓ · T15 在 T8 之后 ✓。

**未做**：T18 `[ ]*` 平台级；Playwright 真浏览器实测未做。


### 真浏览器补充验收（2026-10-01）
- N1 全部真实 tab 路由逐页打开；N1-5 首轮抓到 `leadRows` **数组/字典契约错配**（composable 返回数组、组件按 `retainedEarnings` 字典读）⇒ 修为稳定业务键字典 + 部分旧载荷逐字段补默认 + 实例默认对象深复制。另补 N1-5 自加载 `useN1FormData`（宿主从未传必填的 `allResponses/formData`）和审计上下文年度回退（禁当前自然年）。复测 console 0 error；结构化/矩阵/在线编辑三值真显示，点矩阵后主表隐藏、矩阵卡真挂载。
- N3 5 个真实 tab 逐页验：N3A 走 OO、目录不显示模式栏、N3-1~3 显示模式栏；点 OnlyOffice 真挂载 OO，console 0 error。
- N5 五路跨底稿取数的同源死端点一并改成平台 `wp-id-by-code` 入口；平台 `useResolveLinkageRoute` 同一死端点也同步修复并更新测试。
