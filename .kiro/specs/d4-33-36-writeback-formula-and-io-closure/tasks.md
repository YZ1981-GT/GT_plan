# Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-1",
      "name": "后端导入导出修复（含死配置清理）",
      "tasks": [1, 2, 3],
      "depends_on": []
    },
    {
      "id": "wave-2",
      "name": "公式引擎接线 + 覆盖层 + 判据单一真源（含死代码删除）",
      "tasks": [4, 5, 6],
      "depends_on": []
    },
    {
      "id": "wave-3",
      "name": "双模式回写共享件 + A13 联动",
      "tasks": [7, 8],
      "depends_on": ["wave-2"]
    },
    {
      "id": "wave-4",
      "name": "四张表前端接线",
      "tasks": [9, 10, 11, 12],
      "depends_on": ["wave-1", "wave-2", "wave-3"]
    },
    {
      "id": "wave-5",
      "name": "守卫、变异检验与真栈实测收口",
      "tasks": [13, 14, 15, 16],
      "depends_on": ["wave-4"]
    }
  ]
}
```

> **顶层任务与 Checkpoint 不纳入依赖图**（沿用本仓库 spec 约定）；依赖图只声明带小数编号的叶子任务。

## Wave 1 — 后端导入导出修复

- [ ] 1.1 新增 D4-33 专用 import/export：`_parse_d4_33_row` 逆向解析后端既有 16 行 export 形态（12 月+合计+上年数+变动额+变动比例）回 `BizType[]`，落库写 `{bizTypes: [...]}` 嵌套对象；导出模板与导入解析必须对称（当前 export 有专属分支而 import 无）
  - Validates: Requirements 1.1
  - 判据：D4-33 导出→导入往返后 `bizTypes` 的 12 月 + `priorMonths` 逐字段一致；合计/毛利率/变动额/变动比例由重算得出且不参与比对
- [ ] 1.2 新增 D4-34 两区专用 parser/export：`_parse_d4_34_rental_row`（`RentalRow` 9 字段）与 `_parse_d4_34_consult_row`（`ConsultRow` 8 字段）逐字段中文列头名 → 英文 key 映射；**落库必须合并写回同一个 `D4-34-data`**，导入 `-rental` 时保留既有 `consults`、反之亦然（读既有 → 合并 → 写回，禁止整对象覆盖）
  - Validates: Requirements 1.2, 1.5
  - 判据：Property 3 —— 两区互不覆盖（含另一区为空数组的态）
- [ ] 1.3 新增 D4-35 专用 parser/export：`_parse_d4_35_row` 映射 `CheckRow` 16 字段（含 `check1..check6`），`isAnomalous` 保持 **string** 语义（`是`/`否`/空）不得转 boolean；落库写 `{rows, sampling, periodAmount}`，其中 `sampling`（抽样参数 6 字段）与 `periodAmount` **不由行导入覆盖**（保留既有值）
  - Validates: Requirements 1.3
  - 判据：导入后 `sampling`/`periodAmount` 逐字段不变；`rows` 录入字段逐字段一致
- [ ] 1.4 新增 D4-36 两区专用 parser/export：`_parse_d4_36_forward_row` 与 `_parse_d4_36_backward_row`，**一律按列头名映射（非列序）**——backward 的 xlsx 列头顺序（单据在前、凭证在后）与 forward 相反，按位置取会交叉错位；落库合并写回同一个 `D4-36-data`（`forward`/`backward` 互不覆盖）
  - Validates: Requirements 1.4, 1.5
  - 判据：backward 行导入后 `voucherAmount` 与 `docAmount` 不互换
- [ ] 1.5 item_id 映射：在 import/export 两处 `elif` 链新增 `D4-33 → D4-33-data`、`D4-34-rental`/`D4-34-consult → D4-34-data`、`D4-35 → D4-35-data`、`D4-36-forward`/`D4-36-backward → D4-36-data`（**改后端映射，不改前端键**）
  - Validates: Requirements 1.5
  - 判据：Property 2 —— 四表 sheet → item_id 字面量断言，无 `f"{sheet}-rows"` 兜底
- [ ] 1.6 删除死配置：从 `_SUPPORTED_SHEETS` 与 `_SHEET_HEADERS` 删除 `D4-34`（12 列主键）与 `D4-36`（12 列主键）——前端只用 `-rental`/`-consult` 与 `-forward`/`-backward` 子键，主键零消费方
  - Validates: Requirements 1.6
  - 判据：Property 12 —— `_SUPPORTED_SHEETS` 每个键都有前端真实消费方
- [ ] 1.7 列头校验与金额兜底：四表「缺少列」判定使用补齐后真实列头（D4-33 需确认列头与 export 16 行形态一致）；金额类走 `_safe_float`，D4-35 的 `amount`（string 类型）**空串保持空串**不写 0
  - Validates: Requirements 1.7, 1.8
  - 判据：Property 1 —— 空金额往返后仍为空串
- [ ] 1.8 新增后端守卫 `backend/tests/test_d4_33_36_import_export_roundtrip.py`：6 个 parser 产出结构与前端类型**逐字段**一致 + 多子区互不覆盖 + `sampling` 保护 + backward 列名映射
  - Validates: Requirements 5.1
  - 判据：pytest 全绿；变异（parser 改回 `_parse_generic_row`、backward 改按列序、D4-34 改整对象覆盖）三条均 RED
- [ ] 1.9 新增后端守卫 `backend/tests/test_d4_33_36_item_id_and_dead_config.py`：sheet → item_id 六条字面量断言 + `_SUPPORTED_SHEETS`/`_SHEET_HEADERS` 不含 `D4-34`/`D4-36` 主键
  - Validates: Requirements 5.7
  - 判据：item_id 改回 `f"{sheet}-rows"` 必红；死配置重新加入必红

## Wave 2 — 公式引擎接线 + 覆盖层 + 判据单一真源

- [ ] 2.1 新增平台公式预设与 F-SHELL v2 effective definition 的读取入口：`getFormulaParam(sheet, key)` 单一读取入口，读 `checklist_responses[{sheet}-formula-override].remark`（JSON，如 `{"grossMargin.anomalyThreshold": 15}`）；未命中返回引擎默认常量；**JSON 解析失败/类型错误必须记 ERROR 并给可见提示，不得静默返回默认值**（fail-open 是最贵一类缺陷）
  - Validates: Requirements 4.5, 4.7
  - 判据：Property 11 —— 三类异常均有可见错误信号
- [ ] 2.2 新增单一真源常量 `backend/data/d4OtherGroupFormulaDefaults.json`：集中四表默认公式参数（D4-33 毛利率阈值 ±20 个百分点、变动率阈值 30%；D4-34 差异容忍 `0`；D4-35 异常率阈值；D4-36 跨期判定阈值）；**后端导出与前端运行时读同一文件**，由契约测试锁死双向一致（导出在后端执行，默认值不能只在前端有一份）
  - Validates: Requirements 4.5, 4.6
  - 判据：Property 4 —— 三处同口径的前置条件；新增契约测试断言两端读同一真源
- [ ] 2.3 D4-33 公式接线：**按 DEC-2 统一到引擎 `calcGrossMarginRate` 的百分比口径**（现内联实现返回小数比率、引擎返回百分比，差 100 倍）——组件展示补 `%` 后缀，**禁止**局部 `*100` 打补丁；同时接线 `calcSubtotal`（12 月合计）与 `calcChangeRate`（同比变动率）；删除组件内联毛利率/合计/变动率计算
  - Validates: Requirements 4.1
  - 判据：Property 5 —— 全库不存在返回小数比率的第二套毛利率计算路径
- [ ] 2.4 D4-34 公式接线：`diff` 替换为引擎 `calcChangeAmount(actualRevenue, expectedRevenue)`；**删除组件内联的本地 `pn` 函数**改用引擎 `parseNum`（本地 `pn` 与引擎 `parseNum` 并存属第二套解析路径）
  - Validates: Requirements 4.2
  - 判据：组件内 grep 无本地 `pn` 定义；差异由引擎产出
- [ ] 2.5 D4-35 公式接线：异常率接 `calcAnomalyRate`、覆盖率接 `calcCoverageRate`（引擎已有却未被消费），组件内禁止内联 `filter().length` 与 `reduce`
  - Validates: Requirements 4.3
  - 判据：`anomalyCount`/`checkRatio` 走引擎调用链（判行为，非字符串存在型）
- [ ] 2.6 D4-36 公式接线：跨期判定接引擎 `isCrossPeriod` + `calcCrossPeriodDays`，跨期汇总接 `calcSubtotal`；**新增方向化纯函数** `isCrossPeriodForward(voucherDate, docDate, bsDate)` 与 `isCrossPeriodBackward(docDate, voucherDate, bsDate)`（forward = 凭证在期内且单据在期后；backward = 单据在期内且凭证在期后）——**不得**照抄死代码 `useD4OtherGroup.ts` 里不区分方向的 `isCrossPeriod(voucherDate, shipDate, bsDate)`
  - Validates: Requirements 4.4
  - 判据：forward/backward 对同一组日期输入结果方向相反；纯函数无副作用无 Vue 依赖
- [ ] 2.7 新增可推送判据单一真源 `composables/d4OtherGroupPushPredicates.ts`：D4-33（毛利率超阈值或变动率超阈值）/ D4-34（`diff !== 0`，租赁与咨询各自独立成条）/ D4-35（`isAnomalous === '是'`）/ D4-36（`isCrossPeriod === true`，forward 取 `docAmount`、backward 取 `voucherAmount`）；判据必须读覆盖层阈值（`getFormulaParam`），**禁止**四个组件各写一份过滤条件
  - Validates: Requirements 3.12
  - 判据：Property 10 —— 判据集中在一个文件，组件内无内联过滤
- [ ] 2.8 **删除死代码** `audit-platform/frontend/src/components/workpaper/composables/useD4OtherGroup.ts`（grep 全库零消费者；键位 `D4-33-rows` 等与真实键 `D4-33-data` 全不符；类型与真实组件全不符如 `isAnomalous: boolean` vs 实际 string），**不留 DEPRECATED 注释**；删除后 grep 确认无残留 import
  - Validates: Requirements 1.9
  - 判据：Property 10 —— 文件不存在且全库 `useD4OtherGroup` 零命中
- [ ] 2.9 新增前端守卫 `composables/__tests__/d4OtherGroupFormulaOverride.spec.ts`：覆盖层三处同口径（表格渲染值 / A13 推送判据 / 导出行构造值）专测 + 百分比口径断言（防回归小数比率）+ 三类异常不静默 + `pn` 已删 + 死代码零命中
  - Validates: Requirements 5.5, 5.6
  - 判据：vitest 全绿；变异（毛利率改回小数比率、覆盖层改成静默 return 默认值）两条均 RED

## Wave 3 — 双模式回写共享件 + A13 联动

- [ ] 3.1 既有 `ContentMutationService` + `useWorkpaperSyncBridge` 共享接线：**excel → html 同步**（OO 保存成功后显式动作，adapter.toStructured(rows) → persistAll → `d4:save-items`）；失败必须 fail-closed（中文可见错误 + 同步态**不置**「已同步」+ html 保持改动前状态 + 提示「excel 侧改动未同步，请重试」）
  - Validates: Requirements 2.1, 2.2
  - 判据：Property 9 —— 失败路径可见报错且不标记已同步
- [ ] 3.2 新增共享件 **html → excel 同步**：工具条「同步到在线编辑」按钮，**仅人工触发**，禁止在 html 保存时自动静默反写 excel（防双写冲突与回环）；只读态禁用
  - Validates: Requirements 2.3, 2.7
  - 判据：Property 9 —— 不存在 html 保存时自动反写 excel 的调用链
- [ ] 3.3 新增共享件 **只读校对**：`compareBothSides(sheet)` 输出行/字段级差异列表，**仅提示、绝不自动覆盖任一侧**；同步态三态（「已同步」/「excel 侧有未同步改动」/「html 侧有未同步改动」）中文彩色 tag 接入四张表工具条
  - Validates: Requirements 2.4, 2.5
  - 判据：Property 9 —— 差异只提示不反写；同步态中文（禁裸英文）
- [ ] 3.4 新增共享件 **多子区 adapter 声明**：四张表结构差异大（D4-33 `{bizTypes}` / D4-34 `{rentals, consults}` / D4-35 `{rows, sampling, periodAmount}` / D4-36 `{forward, backward}`），adapter 必须**显式声明**每表结构，禁止通用 JSON 猜测；D4-34/D4-36 同步必须**逐区独立**（同步 `-rental` 不冲 `consults`、同步 `forward` 不冲 `backward`）
  - Validates: Requirements 2.6, 2.9
  - 判据：Property 3 —— 多子区同步不互相覆盖
- [ ] 3.5 OO 不可用降级：「在线编辑」未挂载或 OO 服务不可用时 html 侧功能完全不受影响（不因 OO 探针失败阻断 html 编辑/保存），差异提示退化为「在线编辑不可用」
  - Validates: Requirements 2.8
  - 判据：html 编辑/保存在 OO 断连时仍可用
- [ ] 3.6 四张表 A13 推送接线：复用既有 `useD4InspectionWriteback`（`pushToA13` + `appendToD41Note`），**禁止**组件内联重写事件构造或落库逻辑；`wpCode` 分别为 `D4-33`/`D4-34`/`D4-35`/`D4-36`，**`accountCode: '6051'`、`accountName: '其他业务收入'`**（DEC-5，**不得**照抄姊妹 spec 的 `6001`）；A13 仅接收人工认定的错报金额与方向并完成 durable ack 后的项目；定性风险不推送金额 0，差异保留方向，凭证金额不等同错报金额。，D4-35 取 `parseNum(amount)`，D4-36 forward 取 `docAmount`/backward 取 `voucherAmount`；只读态禁用入口；空项不 emit 且中文提示
  - Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
  - 判据：Property 6 / Property 7 / Property 8
- [ ] 3.7 溯源 chip 校验修正：按 `cross_wp_references.json` 已登记关系校验四表 `GtIndexChip`（现存 `D4-33 → wp:D4-3`、`D4-34 → wp:D4-33`、`D4-35 → wp:D4-34`、`D4-36 → wp:D4-35`），禁止自造未登记引用；`D4-36` 若已登记应补 `wp:D4-17`/`wp:D4-18` 姊妹截止测试引用
  - Validates: Requirements 3.11
  - 判据：所有 `wp:` 引用值存在于 `cross_wp_references.json`

## Wave 4 — 四张表前端接线

- [ ] 4.1 D4-33 `D4TabOtherMargin.vue` 接线：公式覆盖层 + 判据单一真源 + 双模式同步 + A13 推送入口；**`.auto-calc` 旧样式替换为蓝本 `.auto-calc-col`**（灰底 + 虚线下划线 + 列头 tooltip 标注计算来源，阈值类 tooltip 随覆盖层实时反映生效值）；「⚙ 公式设置」入口
  - Validates: Requirements 4.1, 4.5, 4.8, 4.9
  - 判据：公式面板可见预设默认值与「恢复默认」；自动列样式统一
- [ ] 4.2 D4-34 `D4TabOtherContract.vue` 接线：同 4.1；两区（租赁/咨询）各自独立推送条目；`diff !== 0` 判据走覆盖层容忍阈值
  - Validates: Requirements 4.2, 4.6, 4.9
  - 判据：两区命中时各自独立成条（不合并）
- [ ] 4.3 D4-35 `D4TabOtherCheck.vue` 接线：同 4.1；`isAnomalous === '是'` 判据；推送描述带凭证号 + 业务内容 + 6 个核对列未通过项
  - Validates: Requirements 4.3, 4.6, 4.9
  - 判据：描述含未通过核对项标识
- [ ] 4.4 D4-36 `D4TabOtherCutoff.vue` 接线：同 4.1；方向化跨期判定（forward/backward 语义相反）；推送描述带方向标识 + 跨期天数 + 调整建议
  - Validates: Requirements 4.4, 4.6, 4.9
  - 判据：描述含方向标识与跨期天数
- [ ] 4.5 四表工具条统一打磨：AI + 复核按钮右对齐（放默认插槽 `margin-left:auto`，勿放 `#actions`）；同步态 tag 与「⚙ 公式设置」并列「导入导出 ▾」；只读态全部禁用
  - Validates: Requirements 2.5, 4.8
  - 判据：Property 7 —— 只读态全禁

## Wave 5 — 守卫、变异检验与真栈实测

- [ ] 5.1 新增前端守卫 `d4OtherGroupWriteback.spec.ts`：四表按钮存在 + `isReadonly` 禁用 + 点击真 `eventBus.emit('a13:push-misstatement')` 且 payload `wpCode` 字面量正确；金额必须来自人工认定并保留方向，D4-33 定性项不得以 `amount: 0` 自动进入汇总，D4-34 不得使用 `abs(diff)`；空项不 emit。
  - Validates: Requirements 5.3
  - 判据：变异「accountCode 改 6001」必红（Property 8）
- [ ] 5.2 新增前端守卫（双模式回写）：excel→html 失败路径可见错误 + 不标记已同步（**判行为**，非字符串存在型）；html→excel 为人工触发（断言不存在 html 保存时自动反写 excel 的调用链）；多子区逐区同步不互相覆盖；OO 断连时 html 不受影响
  - Validates: Requirements 5.4
  - 判据：Property 3 / Property 9
- [ ] 5.3 编写变异检验 harness `mutate_d4_33_36_guards.py` 并四态判定（RED / GREEN=守卫缺陷 / ANCHOR-MISS / WRONG-TEST）；**锚点至少 12 条**：① 任一表 item_id 改回 `f"{sheet}-rows"` ② D4-35 parser 改回 `_parse_generic_row` ③ D4-36 backward 改按列序映射 ④ D4-34 导入改整对象覆盖 ⑤ D4-33 毛利率改回小数比率 ⑥ 任一表 `accountCode` 改 `6001` ⑦ 覆盖层改成静默 return 默认值（fail-open）⑧ 组件重新引入 `useD4OtherGroup` import ⑨ 死配置 `D4-34`/`D4-36` 重新加入 ⑩ html 保存时自动反写 excel ⑪ 本地 `pn` 复活 ⑫ D4-35 `sampling` 被行导入覆盖
  - Validates: Requirements 5.2
  - **A13 金额必须人工认定并保留方向**：D4-33 定性风险不得以 `amount: 0` 自动进入汇总；D4-34 不得使用 `abs(diff)`；不得把抽凭金额直接等同错报金额。
- [ ] 5.4 浏览器真栈实测（Playwright）：四张表各一次导出→导入往返（值逐字对齐）+ 各一次差异→A13 推送（A13 页面出现错报且 `source_wp_code` 正确、科目为 6051）+ **D4-35 一次 html↔excel 双向回写完整往返**（html 改→同步到 excel→excel 改→回读 html）+ 一次公式覆盖编辑后三处口径一致验证 + 四表工具条同步态三态可见
  - Validates: Requirements 5.8
  - 判据：Playwright 全绿；截图/日志留证
- [ ] 5.5 收口校验：spec 三件套机器校验（`### Property N` 纯整数、`**Validates: Requirements X.Y**` 全 `X.Y` 形态、tasks 含 waves JSON 且 DAG 无环）+ 人工核对未被引用的 AC（悬挂 0 也要查整条 Requirement 是否零实现）+ design 承诺的新函数（`_parse_d4_3X_row` 六件套 / `isCrossPeriodForward` / `getFormulaParam` / `既有 `ContentMutationService` + `useWorkpaperSyncBridge``）必须能在生产代码 grep 到
  - Validates: Requirements 5.9
  - 判据：AC 覆盖率 100%；Property 全部挂任务；无死承诺
- [ ] 5.6 **产物入库**：`git status --porcelain` 逐个 diff 归因，确认本 spec 全部正式产物（后端 6 parser + 2 守卫 + `d4OtherGroupFormulaDefaults.json`、前端 3 新增 composable + 4 组件接线 + 3 守卫 spec + 变异 harness、spec 目录本身）**无 `??` 未跟踪**——「spec 全绿 ≠ 产物已入库」，丢工作树即蒸发（本 spec 目录也必须入库）
  - Validates: Requirements 5.9
  - 判据：`git ls-files` 对本 spec 目录与全部产物路径非空

## Checkpoints

- **Checkpoint 1（Wave 1 完成后）**：四张表导出→导入往返在**后端测试**层面逐字段一致；后端 pytest 覆盖四表 parser + item_id + 死配置；死配置 `D4-34`/`D4-36` 主键已删且前端下拉不含入口。
- **Checkpoint 2（Wave 2 完成后）**：`useD4OtherGroup.ts` 已删除且零残留 import；四表派生值全部走引擎；毛利率百分比口径全库唯一；覆盖层三类异常可见报错（非 fail-open）；判据集中单一文件。
- **Checkpoint 3（Wave 3 完成后）**：双模式共享件落地，excel→html 失败 fail-closed、html→excel 仅人工触发、差异只提示不反写、多子区逐区不覆盖；四表 A13 推送科目全为 6051；空项不 emit。
- **Checkpoint 4（Wave 4 完成后）**：四张表接线完成，自动列样式统一 `.auto-calc-col`，公式面板可见预设默认值，工具条同步态中文三态，只读态全禁。
- **Checkpoint 5（Wave 5 完成后）**：变异 12 条全 RED 且各打红预期测试；Playwright 四表往返 + A13 + D4-35 双向回写 + 覆盖层三处同口径实测通过；三件套机器校验全绿；全部产物已入库。

## Notes

- **参照实现（唯一可照抄范式）**：`_d4_import_export.py` 的 D4-15/16/22/23 专用分支（`_parse_d4_XX_row` + 专用 export 行构造 + item_id 映射 elif 链）；`useD4InspectionWriteback.ts`（`pushToA13` + `appendToD41Note`，已存在）；`useD4FormulaEngine`（纯函数库）；`useD4ImportExport`（三端点，四表已接）。
- **反向参照（只借鉴门控纪律，不复制链路）**：D2-2 双向回写（`workpaper-html-onlyoffice-bidirectional-writeback-closure`）—— 写侧/读侧分离 · 反向校对绝不反写 · 写成功才确认 · fail-open 不得掩盖接线错误。D2 的「底稿→附注 `sync-from-workpaper`」推送链路**不复制**：四表 `note_workpaper_sync_registry.json` 零命中、无独立附注章节。
- **与姊妹 spec 的唯一科目差异**：本 spec 全用 `6051`/`其他业务收入`（D4-33~36 属其他业务收入科目），姊妹 spec（D4-13~20）全用 `6001`/`营业收入`。**照抄姊妹 spec 时把 `6001` 抄过来即错**，Property 8 + 变异锚点⑥ 双保险。
- **本 spec 与 D4-2 无直接关系**：D4-2 是主营收入明细表，仅作为公式样式蓝本（`.auto-calc-col`）与治理模式参照；本 spec 独立成四表一个 spec（按用户要求「四表逐一做一个 spec」）。
- **Windows 命令约定**：Python 用 `python`（非 `python3`）；禁止 `&&`（用 `;`）；禁止 `cd`（用 `cwd` 参数）；pytest 从仓库根跑（从 `backend/` 跑相对路径会假红）；shell 命令加 `rtk` 前缀压缩输出。
- **测试执行**：不要跑全量 `backend/tests`（1500+ 文件），按引用关系反查辐射面；`-k "a or b"` 经 shell 会被拆位置参数，用 `subprocess.run([...])` 不经 shell。
- **并发纪律**：同一文件禁与并发会话并行编辑；工作树长期不干净，`git status` 必须逐个 diff 归因；push 前必先 `git fetch` 看远端真实 base；协作走 PR 不直推 main。
- **收尾纪律**：会话结束前清掉自己的 `tmp_*` 诊断产物（`.gitignore` 已收 `tmp_*` 与 `_wip_*`）；spec 目录必须入库。


## Governance Gating Addendum

以下任务在共同契约 `d4-dual-mode-formula-governance` 的 requirements/design 可用、实际 finder/index、contract bundle 与 F-SHELL v2 mutation 接口核定前均为 `blocked`，不得标记完成：

- [ ] B1 [blocked] 核定 `backend/wp_templates/` finder/index 的运行时模板身份，先解决两组声称不同模板的冲突；不得以组件字段替代源模板。
  - Validates: Requirements 1.1, 5.1
- [ ] B2 [blocked] 改为消费 `ContentMutationService`、`useWorkpaperSyncBridge`、durable callback、三方合并及批准 contract bundle；禁止 `既有 `ContentMutationService` + `useWorkpaperSyncBridge`` 自行同步、仅 emit 或无 durable ack/幂等。
  - Validates: Requirements 2.1, 2.6, 5.4
- [ ] B3 [blocked] F-SHELL v2 mutation 统一 effective formula definition 并投影 HTML/OO；mask 仅保护普通值，公式编辑统一经过 expression/refs/params 解析、权限、CAS、审计。
  - Validates: Requirements 4.1, 4.5, 4.6, 5.5
- [ ] B4 [blocked] 移除 checklist remark formula override、前后端重复默认值和纯函数可编辑声明；预设升级不覆盖 custom，删除/恢复默认分开，scope=wp/sheet/row/field，单位显式，未知函数及空/除零/error 显式 blocked。
  - Validates: Requirements 4.5, 4.7, 5.5
- [ ] B5 [blocked] A13 与双向同步分开，人工认定金额方向后才推送；定性风险不 amount=0 入汇总，diff 保留方向，不 abs 化，抽凭金额不直接等同错报。
  - Validates: Requirements 3.1, 3.2, 3.3, 3.4
- [ ] B6 [blocked] D4-33/34/35/36 各自完成 HTML→OO→HTML、公式编辑重新打开、导出和不同项目隔离真栈验收，不得以 D4-35 代表全组。
  - Validates: Requirements 2.10, 4.6, 5.8

### Governance Properties

### Property 13: 平台协议与 durable ack
**Validates: Requirements 2.1, 2.6, 5.4**

双向回写必须消费批准的平台 mutation/sync bridge、durable callback、三方合并和 contract bundle，并具备 durable ack/幂等；自建同步协议或仅 emit 则保持 blocked。

### Property 14: F-SHELL effective formula 单一真源
**Validates: Requirements 4.1, 4.5, 4.6, 4.7, 5.5**

同一 effective definition 投影 HTML/OO，授权编辑 expression/refs/params 走统一解析、权限、CAS、审计；custom 隔离、预设升级、删除/恢复默认和作用域可验证。

### Property 15: A13 人工认定金额方向
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

A13 payload 只能来自人工认定金额与方向；定性风险不得 amount=0 直接汇总，差异不得 abs 化，抽凭金额不得直接替代错报金额。

### Property 16: 四表完整真栈验收
**Validates: Requirements 1.1, 2.10, 5.1, 5.8**

模板身份必须来自实际 finder/index；四表各自完成双向回写、重新打开公式编辑、导出及跨项目隔离，否则任务保持 blocked。
