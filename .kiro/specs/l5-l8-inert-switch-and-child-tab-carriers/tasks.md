# L5 ~ L8 死开关与子 Tab 专属载体车道 — 任务

> **实施纪律**
> - 🔴 **共同裁决只引用编号**（LC-1 ~ LC-26 在 foundation 的 `design.md`），**禁复述判据内容**。
> - 🔴 **所有计数一律现算**，与 `design.md` 等值比对。**禁写死**。
> - 🔴 **判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号**。
> - 🔴 **L 域文件集必须 strict 口径**（LC-5）。
> - 🔴 **行数口径统一 `len(text.split("\n"))`**。
> - 🔴 **含正则的核验一律写探针文件**，禁用 `python -c`。
> - 🔴 **判 inert / segmented 前必须先剥注释**（LC-15）。
> - 🔴 **BP-5 在本 spec 不适用**——四条的载体是 live 模块不是 orphan，本 spec 没有删 orphan 的动作。
> - `[ ]*` = 依赖外部供给（BP-1 / BP-2 / BP-3）或待造数据，本 spec **不承诺完成**。
> - 并发会话正在实施 F3/F4/F5 与 H9 的 spec，其契约与关联产物**一律不碰**。

---

## 阶段 0：BP 归位与形态差异门（Task 0 ~ 3）

- [x] 0. 四条 entry 的 blocked_by 现算门
  - 现算四条 `capability_target_blocked_by` 各 7 项且**完全一致**（BP-1/2/3/4/6/7/9）
  - 断言均**不含** BP-5 / BP-8 / BP-10；断言「含 BP-4+BP-6」与「含 BP-5」两集合完全互斥
  - 断言 BP-4 **只**出现在这四条的 `evidence.unverifiable_reasons` 里，且四条 reasons 比 L1~L4 多一条
  - _Property: LB-P1, LB-P2, LB-P3_

- [x] 1. 与 foundation 的七项形态差异门
  - 逐项现算断言：载体位置（子 Tab vs 宿主）· `mode_values`（`structured` vs `html`）· `switch_is_redeemable`（`false` vs `true`）· localStorage 键形态（`:` 分隔 vs 尾连字符）· `ui_toolbar_gate.anchor`（`null` vs 非空）· notice 落位点（子 Tab vs 宿主）· `orphan_twin`（`null` vs 非空）
  - 🔴 断言四条的判据**不可照抄 foundation**
  - _Property: LB-P14_

- [x] 2. BP-9 / BP-7 引用门
  - BP-9 引用 **LC-1**；BP-7 引用 **LC-14**，🔴 **不重新裁决**
  - 🔴 断言四条 `ui_toolbar_gate.anchor is None` 但 `child_level_segmented_site` **非空** ⇒ notice 落位点在**子 Tab 层**
  - _Property: 引用 LF-P5, LC-14_

- [ ] 3.* BP-1 / BP-2 / BP-3 外部供给登记
  - 标 `[ ]*`：approved authority model + per-entry contract + non-null bundle / Task 36 published representation / 真实 OnlyOffice 9.4 探针
  - _Property: 不宣称通过_

---

## 阶段 1：BP-4 死开关收口（Task 4 ~ 9）

- [x] 4. inert 三条件现算门（先剥注释）
  - 对四个子 Tab 各验：① 剥注释后有 `el-segmented`；② 以 `mode` 为条件的 `v-if`/`v-else-if`/`v-show` 现算 **0**；③ 文件内 `GtOnlyOfficeSheet` 命中 **0**
  - 🔴 三条必须同时成立才判 inert
  - _Property: LB-P4_

- [x] 5. 对照组门（两侧都验）
  - 现算 L1 / L2 宿主的门控式 OO 挂点存在（引用 **LC-2**）
  - 🔴 证明判据能区分「可兑现」与「inert」两形态，而非一律判红
  - _Property: LB-P5_

- [x] 6. dualMode 成员消费面门
  - 现算每个 inert 开关消费到的成员恰 3 个（`mode` / `modeOptions` / `switchMode`）
  - 断言 `mode` 只作 `v-model` 双绑，无任何分支以它为条件
  - _Property: LB-P6_

- [x] 7. 🔴 收口路线裁定（本 task 的产物是裁定书）
  - 在 ①**兑现**（补 OO 挂点 + mode 门控分支）与 ②**摘除**（删 segmented + 删载体）之间裁定，**写明理由**
  - 判断依据：BP-1/2/3 是否已到位（路线 ① 依赖它们供给 OO 侧权威定义）
  - 🔴 若选路线 ① ⇒ 后续实施 task 标 `[ ]*`；若选路线 ② ⇒ 走 Task 8
  - _Property: LB-P7 的前置_

- [x] 8. 路线 ② 执行（若被选）
  - 删四个子 Tab 的 `el-segmented` + 删四个 `useL{n}DualMode.ts`
  - 🔴 **同 commit 一并删**（删 segmented 后载体消费边归零，留着就是新 orphan）
  - 删前 grep 消费方 → 删前后测试全绿 → 独立 commit
  - _Property: LB-P8_

- [x] 9. 收口后现算门 + 立场约束
  - 断言 inert 计数 4 → **0**，`switch_is_redeemable` 不再有 `false`
  - 🔴 断言四册模板各有真实业务 sheet（现算 12 / 9 / 8 / 10）⇒ **不得借 inert 把 entry 裁成 `single_html`**（引用 slice 的 `not_single_html_because`）
  - _Property: LB-P7, LB-P9_

---

## 阶段 2：BP-6 探活收敛（Task 10 ~ 12）

- [x] 10. 两个端点都现算门
  - 按端点字面量分别扫 `onlyoffice/health` 与 `onlyoffice-config`
  - 🔴 **两个数都断言**：health 命中数现算；`onlyoffice-config` 命中 == **0**
  - 🔴 在文档与注释里写明「L 域只探活不取配置」，**不得表述为「两个端点都在直调」**
  - _Property: LB-P10_

- [x] 11. 越层判定门
  - 定位 health 直调点所属模块，断言**不经**任何共享适配层（与 LD-3 同型：L 域适配层每循环一份）
  - _Property: LB-P11_

- [x] 12. 探活收敛 + 守卫
  - 把探活收敛到单一入口（共享 composable 或 service）
  - 🔴 **守恒校验**：收敛后直调点 == 0 且 入口调用点 == 收敛前直调点数
  - 守卫按端点字面量卡点（不按符号名），禁止 L 域出现新的裸 health 直调
  - _Property: LB-P12_

---

## 阶段 3：载体族统一（Task 13 ~ 14）

- [x] 13. 载体族五项全同门
  - 现算断言：kind / site 目录形态 / `mode_values` / `orphan_twin is None` / localStorage 键形态 五项四条全同
  - 引用 **LC-18** 断言键属 `` `${PREFIX}:${wpId}` `` 形态，判据落「**key 含 wpId**」
  - _Property: LB-P13, LB-P15_

- [x] 14. 统一方案（不新造第四种形态）
  - 复用 foundation 对共享载体的裁定（引用 **LC-2** 与 foundation 关于「部分收缩」的结论）
  - 🔴 断言未引入第四种载体形态
  - _Property: LB-P13_

---

## 阶段 4：位置化收口（Task 15 ~ 19）

- [x] 15. 本 spec 位置化命中现算门
  - 引用 **LC-8** 口径 ②，按模块列分布并现算总数
  - 断言本 spec 承担的份额是全 L 域最大的一块
  - _Property: LB-P16_

- [x] 16. 分隔符异常定位门
  - 🔴 **两侧都验**：断言 `row${…}`（无连字符）**只**出现在两个 L6 Disclosure 组件；其余全是 `row-${…}`
  - _Property: LB-P17_

- [x] 17. 🔴 L6 读写键取证（取证前不得下结论）
  - 把写侧与读侧的 item_id 模板**各自展开成完整键模式集合**（field 名一并取出）
  - 求交集与差集：交集为空或部分缺失 ⇒ 判 **A 真缺陷**并单列修复项；field 名本就不同 ⇒ 如实登记为 **B 两套键并存**（不是 bug）
  - 🔴 **只看分隔符不同就判 bug 是误判**；结论必须由数据决定
  - _Property: LB-P18_

- [x] 18. 去位置化实施（复用正面样板）
  - 复用 lane 2 抽取的 rowId 正面样板形态（`useL2Detail` / `useL2VoucherCheck` / `useL3VoucherCheck`）
  - 🔴 断言未自造第四种生成形态
  - 登记新旧键映射表，旧键保留只读兼容期；🔴 真库 L6/L7/L8 为 **0 行**（引用 **LC-24** 第 10 项）⇒ 迁移无存量数据风险
  - _Property: LB-P19_

- [x] 19. removeRow 变体收口
  - 引用 **LC-7** 四元组，枚举并处理本 spec 名下全部变体（含 L7 两个 Disclosure 的 `removeRow($index)`、L8 的 `removeRow(section, index)` 双参）
  - _Property: LB-P20_

---

## 阶段 5：模板层修复（Task 20 ~ 22）

- [x] 20. 倒挤减法链现算门（两个变体都扫）
  - 引用 **LC-20**，断言两形态各自非空：L5「减本表已列项」· L6「减对方表明细行」
  - 🔴 **两侧都验**：断言只在「国企」版，上市公司版无（只扫一个变体会误判已修复）
  - _Property: LB-P21_

- [x] 21. 倒挤减法链修复
  - 把硬编码行号窗口换成可随行数扩展的形式（整列 SUM 减固定标签行，或 `SUBTOTAL`）
  - 现算断言修复后增行场景合计正确
  - 🔴 范围只含 L5 / L6 两册；L4 审定表结构（**LC-21**）归 lane 2
  - _Property: LB-P21_

- [x] 22. 模板基线同步
  - 🔴 改模板后**同步更新 slice `template_ref` 的 sha256 基线**，守卫现算比对（引用 **LF-P23**）
  - 🔴 不更新基线会让既存守卫 `test_task54_l_cycle_migration.py` 红
  - _Property: LB-P22_

---

## 阶段 6：L8 损益分支与收尾（Task 23 ~ 26）

- [x] 23. L8 科目性质与 TB 口径门
  - 引用 **LC-26** 断言 L8 是 8 条里唯一损益类
  - 现算断言发布参数走「本期发生额」而非「期末余额」，判据落发布调用的实参形态（引用 **LC-3** 端点字面量口径）
  - 四表判据按资产负债 / 损益**两分支**写，且两分支分母都非空（7 + 1）
  - _Property: LB-P23_

- [x] 24. L8 键与模板专属项
  - 引用 **LC-16** 断言 L8 的 derived_total 属 MID 型且**少重复 sheet 段**
  - 登记 `非金融机构利息支出测算表L8-4` 的四固定槽 + 硬编码加法链
  - 🔴 断言该表**单元格值带尾随空格**（含下划线占位）⇒ 回写须按**坐标**不按标签
  - _Property: LB-P24_

- [ ] 25.* 四条 entry 的端到端闭环
  - 标 `[ ]*`：真库 L6/L7/L8 为 0 行、L5 仅两行 `'[]'` ⇒ 四条均无有效载荷，待造数据
  - _Property: 不宣称通过_

- [x] 26. 本 spec 自检
  - 断言 LC-x 引用**只出现编号不出现复述**（扫本 spec 三文件）
  - 断言 entry 用 entry_id 全名、4 条无重无漏
  - 断言「N 处」类表述与列举项数一致；无 U+FFFD
  - 算术自检：sheets 12+9+8+10 = 39、HTML 覆盖 11+8+8+10 = 37、OO 兜底 1+1+0+0 = 2、37+2 = 39
  - 🔴 全 L 域闭合自检：foundation 13 + lane2 38 + 本 spec 39 = **90** == owned sheets
  - _Property: 全清单自检_
