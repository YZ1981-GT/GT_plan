# B 类孤儿载体与宿主内联门控通道 — 任务

> 判据一律引用 `b-cycle-sync-foundation-and-first-canary` 的 BC 编号，本文件不重复裁决。
> 🔴 子组 A 的载体删除必须等 3 条全部改线完成，不可提前。

## 阶段 1：子组 A 基线（孤儿载体 3 条）

- [x] 1. 冻结 `useWpDualMode.ts` 孤儿性质
  - 断言 B 域边 **3** == 全域生产边 **3**（差值 0 是成孤儿的充要条件）
  - 断言 `becomes_orphan_after_rewire` 为**真**（全 slice 唯一）
  - 断言 3 条挂点行号 `#L223` / `#L166` / `#L301`
  - _判据：BC-2、BC-58_

- [x] 2. 三条 entry 事实锁定
  - `xlsx/gt-b1-evaluation`：432 行，权威册 docx，sheet 名表达式 `sourceSheet || '业务评价表B1-3'`
  - `xlsx/gt-b1-kaa-check`：311 行，sheet 名表达式含**前导空格**字面量
  - `xlsx/gt-b1-risk-assessment`：538 行，sheet 名表达式为裸变量 `ooSheetName`
  - 断言三条 mode 值全为 `'结构化视图'`，且均未在宿主内声明 `modeOptions`
  - _判据：BC-41、BC-10_

- [x] 3. 真库零分母登记
  - 断言子组 A 三条真库载荷全为 **0** 行
  - 断言 `B1*` bucket 唯一 1 行是 `B1-review-session-20260725075000`（AI 会话，wp_code 为裸 `B1`），**不属**本组任何 entry
  - 造人工数据集验证，并显式声明零分母前提
  - _判据：BC-60、BC-20_

## 阶段 2：解析失败三模式兜底

- [x] 4. 返回 `None` 路径
  - 断言 `业务评价表B1-3` / `风险评估表-保持` / `风险评估表-承接` / `尽职调查报告B1-4` 解析返回 `None`
  - 兜底须给可诊断信息，区分「码不存在」与「sheet 名被当码查」
  - _判据：BC-46、BC-52_

- [x] 5. 抛异常路径（`gt-b1-kaa-check`）
  - 断言 `' B1-5 KAA检查表-业务承接'`（带前导空格）抛 `FileNotFoundError`
  - 兜底须 `try/except FileNotFoundError` 与 `if result is None` 两路都有
  - 🔴 断言禁归一化：不得 `strip()` 前导空格（来自真实 sheet 名）
  - _判据：BC-46、BC-52、BC-10_

- [x] 6. 多册歧义路径（`gt-b14-due-diligence-report`）
  - 断言 `B1-4` 对应两本册：标准版（39 表 × 1292 格 / 405 段 / 6 sections）与简化版（23 表 × 832 格 / 206 段 / 3 sections）
  - 改线须显式选册，守卫断言所选册的 size + sha256
  - _判据：BC-50、BC-52、BC-44_

- [x] 7. override 表字段语义缺陷上报（BC-51 根因）
  - 断言根因：`B1-1` 册 sheet 名为 `风险评估表-承接`、`B1-2` 册为 `风险评估表-保持`
  - 断言 override 表登记的「wp_code」实为 sheet 名
  - 断言 manifest 的 6 个 pattern 中本组 4 个（`B1E` / `B1K` / `B1R` / `B14D`）全部解析为 `None`
  - _判据：BC-51、BC-15_

## 阶段 3：一 componentType 四 wp_code 消歧

- [x] 8. `gt-b1-risk-assessment` 命名空间分离
  - 断言 `wp_codes_via_component_type` 有 **4** 项：`B1-1` / `B1-2` / `风险评估表-保持` / `风险评估表-承接`
  - 承接版与保持版持久化 `item_id` 前缀分离，不共享命名空间
  - 解析只接受真实码（`B1-1` / `B1-2`），sheet 名作册内定位输入
  - _判据：BC-15、BC-51_

- [x] 9. `wp_index` 一码多行制约
  - 断言 `wp_index` 中 `B1-1` ~ `B1-5` 各 **2** 行、`B23` **4** 行
  - 改线须显式确定使用哪一行并断言
  - _判据：BC-55_

- [x] 10. 派生合计判据（`gt-b1-risk-assessment` 单点）
  - 断言 `.reduce(` **4** 处全在该宿主（全 B 域唯一）
  - 断言冒号式 `derived_total` 全 B 域为 **0**（空分母，配变异证明）
  - _判据：BC-14、BC-20_

## 阶段 4：子组 B 宿主内联（2 条）

- [x] 11. `gt-b14-due-diligence-report` 双 segmented 归属
  - 断言该宿主有 **2** 个 segmented 控件（全 B 域唯一）
  - 门控扫描按控件归属不计重，确认两控件各门控哪个视图
  - _判据：BC-13、BC-11_

- [x] 12. `gt-b14` 宿主内 `modeOptions` 收敛
  - 断言 **3** 处字符串数组声明：`['结构化视图','在线编辑']` + 2 × `['结构化视图']`
  - 断言该宿主另有第四值 `'polish'` 1 次
  - 断言全 B 域只有本条在宿主内声明 `modeOptions`
  - 改线时统一到共享定义，避免三处漂移
  - _判据：BC-41_

- [x] 13. 写死对标公司改动态列（Property 22 D2）
  - 断言现状 `#L347` `{ key: 'peer1', label: '对标公司1', width: 120 }` + `#L348` `peer2`
  - 改为动态列以支持第 3 家及更多对标公司
  - 断言 `dynamic_column_sites` 中本宿主 **2** 条的 key 用 `col.key` / `col.field` 属正确形态（不计缺陷）
  - _判据：BC-48、BC-53_

- [x] 14. `rowIndex` 形参改稳定 id（`gt-b14`）
  - 断言 `rowIndex` 形参 **2** 处索引章节表 JSON 数组
  - 断言 slice 的 `row_identity.kind` 为 `function_parameter_row_index_into_json_array`、`violates_forbidden_identity_kind` 为 `array_index`
  - 改为稳定 id，参照同宿主 `sections` 已有的 `sec.id`
  - 断言该宿主同时有稳定身份正样本（`rowId` / `rowKey` / `.id` 族）
  - _判据：BC-53、BC-6_

- [x] 15. `gt-b23-process-control` xlsm 宏层处置
  - 断言权威册为 B23 家族 **14** 本 xlsm（`B23-1` ~ `B23-14`），运行时实测解析到 `B23-15 了解信息处理控制.xlsx`
  - 断言 14 本全含 `xl/vbaProject.bin`
  - 回写必须 `keep_vba=True`
  - 🔴 数据验证丢失无技术解，登记为已知限制（不可标已解决）
  - _判据：BC-49_

- [x] 16. `currentCard.name` sheet 名表达式（形态 D 唯一）
  - 断言该表达式为全 B 域唯一形态 D（裸对象属性，非 `||` fallback）
  - 运行时取值取决于当前选中卡片，守卫须枚举可能取值
  - _判据：BC-10、BC-52_

- [x] 17. `gt-b23` 其余缺陷
  - 断言 `idx` 形参、`count` 键、`removeRow` 家族在该宿主均存在
  - 断言 `count` 值须等于实际行键数量
  - 断言真库 `B23` **2** 行 / remark 非空 2 / conclusion 非空 0（BC-34 反转在本条成立）
  - _判据：BC-53、BC-54、BC-7、BC-34_

- [x] 18. 门控假阴修正（子组内 2 条）
  - 用祖先链 × 递归 v-else 回溯口径断言 `gt-b1-risk-assessment` 与 `gt-b23-process-control` 的 OO 挂点被 mode 门控
  - 断言全 B 域 3 处假阴中本 spec 占 **2**
  - _判据：BC-13、BC-11_

## 阶段 5：docx 与模板层判据

- [x] 19. docx 几何与占位符（`gt-b1-evaluation` / `gt-b14`）
  - 断言 `B1-3 业务评价表.docx` = 5 表 × 60 格 / merged **65%** / 54 段 / 1 section
  - 断言首段为 `索引号：B1-3`（第三种首段形态）
  - 断言 merged 比例 65% ~ 85% 区间内 `id(cell._tc)` 去重判据适用
  - 断言占位符 `XX`（60 / 46 处）+ `【`（44 / 28），`××` 全角为 **0**
  - _判据：BC-39、BC-26、BC-20_

- [x] 20. 幽灵行上界（`gt-b1-risk-assessment`）
  - 断言 `B1-1` 的 `风险评估表-承接` 是 438 行 × 5 列而 last_value 仅 **103 × 3** ⇒ 幽灵 **335 行 / 2 列**
  - 遍历上界必须取 `last_value_row`
  - _判据：BC-35_

- [x] 21. footer 三态（本组册）
  - 断言 footer 读 raw XML，禁用 openpyxl
  - 断言内容全为 `&C&P/&N`
  - 断言 xlsm 也有 footer
  - _判据：BC-36_

## 阶段 6：孤儿载体删除收尾

- [x] 22. 逐条改线后 grep 引用数
  - 每条 entry 改完后 grep `useWpDualMode` 剩余生产引用数
  - 断言 3 条全完成后引用数归零
  - 🔴 未归零不可进入下一步
  - _判据：BC-58_
  - ✅ 守卫已落地（TestOrphanDeletionCloseout.test_current_production_edges_count / test_all_3_edges_are_b1_hosts）：现算生产调用 **3**，全在 3 条 B1 宿主，全域边 == B 域边（成孤儿充要条件成立）

- [ ]* 23. 删除 `useWpDualMode.ts` —— **外部依赖阻塞**
  - 删前 grep 0 调用方、删前后测试全绿
  - 独立成 commit 便于回滚
  - deprecated 过渡期不超过 1 个 sprint
  - _判据：BC-58、BC-2_
  - 🔴 **代码已改但未实测删除**：3 条 B1 宿主已接入 sync composable，但因 capability 升级为 bidirectional 依赖 BP-1~5（外部），legacy 降级路径（descriptorReady 门控）仍在用，引用数为 3 未归零 ⇒ 按铁律不可删。守卫 test_deletion_blocked_by_external_dependency 已冻结此前置条件

- [x] 24. 回滚路径
  - 5 条 entry 的 `capability` 可独立退回 `null`
  - 断言删除步骤可单独回滚（与 entry 改线解耦）
  - 断言既存 B60 pilot 的 **7** 处断言保持通过
  - _判据：BC-2、BC-58_
  - ✅ 守卫已落地（test_b60_pilot_7_assertions_not_regressed）：B60 组件不引孤儿 sync/useWpDualMode，改线可独立回滚

## 外部依赖（本轮不可标 completed）

- [ ]* 25. BP-1 ~ BP-5 五项全 slice 共有阻塞 —— 见 foundation tasks 26 ~ 30
- [ ]* 26. BC-49 数据验证扩展保留 —— openpyxl 无解，须换库或放弃该能力
- [ ]* 27. 子组 A 三条与 `gt-b14` 的真实数据 UAT —— 四条真库载荷均为 0，待真实项目数据
