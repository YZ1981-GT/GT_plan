# L2 / L3 / L4 孤儿孪生与 sheet 粒度折叠车道 — 任务

> **实施纪律**
> - 🔴 **共同裁决只引用编号**（LC-1 ~ LC-26 在 foundation 的 `design.md`），**禁复述判据内容**。
> - 🔴 **所有计数一律现算**，与 `design.md` 等值比对。**禁写死**。
> - 🔴 **判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号**。
> - 🔴 **L 域文件集必须 strict 口径**（LC-5）。
> - 🔴 **行数口径统一 `len(text.split("\n"))`**。
> - 🔴 **含正则的核验一律写探针文件**，禁用 `python -c`。
> - 🔴 **PG 查询每条独立事务**；`checklist_responses` 列名 `wp_id`，底稿主表 `working_paper`（单数）。
> - `[ ]*` = 依赖外部供给（BP-1 / BP-2 / BP-3）或待造数据，本 spec **不承诺完成**。
> - 并发会话正在实施 F3/F4/F5 与 H9 的 spec，其契约与关联产物**一律不碰**。

---

## 阶段 0：BP 归位与前置门（Task 0 ~ 2）

- [x] 0. 三条 entry 的 blocked_by 现算门
  - 现算 `capability_target_blocked_by`：L2 6 项 / L3 6 项 / L4 7 项
  - 断言三条均**不含** BP-4 与 BP-6；断言 L4 是本 spec 唯一含 BP-8 的（且全 L 域唯一）
  - 断言「含 BP-5」与「含 BP-4+BP-6」两集合完全互斥
  - _Property: LA-P1, LA-P2, LA-P3_

- [x] 1. BP-9 / BP-7 引用门
  - BP-9 引用 **LC-1**，BP-7 引用 **LC-14**，🔴 **不重新裁决**
  - 断言 L3 / L4 的 `ui_toolbar_gate.anchor is None` ⇒ notice 无既成锚点，须与 sync bridge 编辑宿主一并落位
  - _Property: 引用 LF-P5, LC-14_

- [ ] 2.* BP-1 / BP-2 / BP-3 外部供给登记
  - 标 `[ ]*`：approved authority model + per-entry contract + non-null bundle / Task 36 published representation / 真实 OnlyOffice 9.4 探针
  - _Property: 不宣称通过_

---

## 阶段 1：BP-5 孤儿收口（Task 3 ~ 6）

- [x] 3. 四个 orphan 模块定位与可删性门
  - 定位：L2 → `components/workpaper/composables/useL2DualMode.ts` · L3 → **两份**（`src/composables/useL3DualMode.ts` + `components/workpaper/composables/useL3DualMode.ts`）· L4 → `components/workpaper/composables/useL4DualMode.ts`
  - 现算每个的生产消费边 == 0；断言均为一阶 orphan（引用 **LC-24** 第 5/6 项）
  - 🔴 断言 L3 的**两份都在**，说明成因是 **LC-25** 的同构复制
  - _Property: LA-P4, LA-P5, LA-P6_

- [x] 4. 不分区 orphan 的额外风险登记
  - 引用 **LC-18**，断言 `components/workpaper/composables/useL3DualMode.ts` 的 storage 键不含 wpId
  - 登记「接上后所有底稿共享同一模式偏好」为删除理由之一（「orphan 不是无害」实证）
  - _Property: LA-P7_

- [x] 5. 执行删除（删旧代码铁律）
  - 删前 grep 0 调用方 → 删除四个文件 → 删前后测试全绿 → **独立 commit**
  - 🔴 L3 两份必须**同一 commit 一起删**；只删一份即残留
  - _Property: LA-P5_

- [x] 6. 删除后核算门
  - 现算剩余 dual-mode 模块数与行数合计
  - 🔴 断言差额 == 被删四个模块的行数之和（两侧都验）
  - _Property: LA-P8_

---

## 阶段 2：真库跨 entry 污染治理（Task 7 ~ 9）

- [x] 7. 污染现象现算与逐行登记
  - 按 **LC-22** 的判据形态查库：断言「任一 `item_id ~ '^L{n}-'` 的行，其 `wp_id` 对应 `wp_code` 以 `L{n}` 开头」
  - 逐行登记违例（`item_id` / 实际 `wp_code` / 项目 / 载荷长度），现算违例数与 `design.md` 等值
  - 🔴 **不断言成因**（测试残留 vs `wp_id` 解析错），只登记现象
  - _Property: LA-P10, LA-P11_

- [x] 8. 跨 entry 隔离守卫（覆盖 8 条全集）
  - 守卫覆盖 8 条 entry 而非只 L2，防同类复发
  - 🔴 守卫须**查库**，不只查代码（slice 的 `cross_entry_isolation` 只扫代码故漏掉）
  - _Property: LA-P12_

- [ ] 9.* 违例数据清理
  - 标 `[ ]*`：需业务确认该行是否为有效底稿数据。本 spec **只加守卫不动生产数据**
  - _Property: 不宣称通过_

---

## 阶段 3：BP-8 粒度折叠（Task 10 ~ 14）

- [x] 10. L4 折叠现算门
  - 断言 16 张权威 sheet → 13 个 dispatch code，重复码集合恰**两个**
  - 逐字断言四张同码 sheet 名不同，其中一张带**内部空格**（引用 **LC-10**）
  - _Property: LA-P13, LA-P14_

- [x] 11. router 层危害门（两个数都断言）
  - 断言两张账面核对表**同时** `endswith` 同尾码 ⇒ 解析器取第一个
  - 🔴 **两个数都断言**：router 歧义码总数 与 真正可达数；断言其余是裸循环码
  - _Property: LA-P15, LA-P16_

- [x] 12. `bondBranch` 定性门
  - 现算断言它是当前**唯一**区分手段
  - 引用 **LC-15** 断言它**不是**模式开关（须先剥注释）
  - _Property: LA-P17_

- [x] 13. 契约层区分方案（路线 A）
  - `sheet_key = "{尾码}#{bondBranch 值}"`，契约登记两个分支的映射
  - 🔴 断言该键**不含** LC-10 的空格缺陷（路线 B 会把缺陷固化进契约，已排除）
  - 🔴 **模板改名明确排除**（会打断 render schema 与 prefill，须另立 spec）
  - 契约 `review.entry_id == 'xlsx/gt-l4-bonds-payable'`；🔴 不碰并发会话的 F3/F4/F5/H9 契约文件
  - _Property: LA-P18_

- [x] 14. 解析层 fail-closed 改造
  - 后端 sheet 解析在「多张同时 `endswith`」时**不再静默取第一个**，要求调用方带分支参数，否则返回明确错误
  - 🔴 **两侧都验**：歧义 entry 走新路径；无歧义 entry（L1/L2 等）**不受影响**
  - _Property: LA-P19_

---

## 阶段 4：L3 侧同构对收口（Task 15 ~ 18）

- [x] 15. L3 的 `#REF!` 同源门
  - 断言 `逾期贷款检查表L3-7` 的 4 处与 `逾期贷款检查表L1-7` 的 4 处同源同形（引用 **LC-11 / LC-25**）
  - 🔴 与 foundation 的对应 task **交叉引用**；改一不改二 = 半修
  - _Property: LA-P20_

- [x] 16. L3 的 definedName 溯源门
  - 断言 L3 册有污染且 broken 数与 L6/L7 相同（引用 **LC-9**）
  - 🔴 断言 **L1 册为 0** ⇒ 污染不是从 L1 复制来的，L3 另有来源（此结论须显式写出，避免误把 LC-25 的同构关系过度外推）
  - _Property: LA-P21_

- [x] 17. L3 的 OCR 与 removeRow 同形登记
  - 引用 **LC-19** 断言 `L3TabContractCheck.vue` 与 L1 侧同借 D4 端点、同按 `$index` 传行
  - 引用 **LC-7** 把 `L3TabDetail.vue` 的 `removeRow(originalIndex)` 与 L1 侧同名签名一并登记
  - _Property: LA-P22_

- [x] 18. L4 的位置化收口（本 spec 唯一需改的一处）
  - 收口 `L4TabFinLiabOther.vue` 的 `L4-3-row-${n}-data`（位置化）+ `removeRow($index)`
  - 收口 `L4TabAdjustment.vue` 的两个 `handleRemove` 变体
  - 🔴 显式声明 L6 / L7 的命中**归 lane 3**，不在本 spec 范围
  - _Property: LA-P25_

---

## 阶段 5：正面样板与收尾（Task 19 ~ 22）

- [x] 19. rowId 正面样板抽取
  - 断言 `useL2Detail` / `useL2VoucherCheck` / `useL3VoucherCheck` 是全 L 域唯一按行身份删的模块（引用 **LC-6** 交叉验证）
  - 断言三个模块的 rowId 前缀**两两不同**（防串档）
  - 把其 rowId 生成形态抽为其余 entry 去位置化的**参考实现**，写入本 spec 产物
  - _Property: LA-P23, LA-P24_

- [x] 20. 模板层基线引用（不修）
  - L2 两张附注披露的裸 IF 密度 / L2·L3·L4 程序表 footer 重复两次（引用 **LC-12**）/ L3 审定表幽灵行最大 / L4 宽表最宽 / L4 审定表结构（引用 **LC-21**）
  - 🔴 本 spec **只引用基线不修模板**
  - _Property: 引用 LF-P32, LF-P33, LF-P41_

- [ ] 21.* 三条 entry 的端到端闭环
  - 标 `[ ]*`：三条真库载荷均不足（L2 唯一非空载荷还是违例数据、L3/L4 全为 `'[]'` 或 `NULL`）⇒ 待造合规数据
  - _Property: LA-P26（不宣称通过）_

- [x] 22. 本 spec 自检
  - 断言 LC-x 引用**只出现编号不出现复述**（扫本 spec 三文件）
  - 断言 entry 用 entry_id 全名、3 条无重无漏
  - 断言「N 处」类表述与列举项数一致；无 U+FFFD
  - 算术自检：HTML 覆盖 8+13+15 = 36、OO 兜底 0+1+1 = 2、sheets 8+14+16 = 38 = 36+2
  - _Property: 全清单自检_
