# Implementation Plan: TB 回写显式发布门（tb-writeback-explicit-publish-gate）

## Overview

方案 B（逐组件改走显式发布端点）实施计划，任务量按 census 只读盘点（`census_writeback_call_sites.md`）修正为三类：**活改造 8 个循环任务**（真实被消费的活路径约 48 处，需完整改造）、**死代码清理 1 个集中任务**（约 40+ 处零消费，只删+收口）、**产品决策 1 个前置任务**（K5/K7 假回写）。

M0（端点扩展，Task 1）是所有**活路径**逐组件任务的前置；死代码清理任务**不依赖 M0**（只删代码），可提前/并行；K5/K7 产品决策是 K 循环真实改造的前置。各审计循环活改造批次内部可并行（不同循环组件互不依赖）。收口任务依赖全部活改造 + 死清理完成；UAT 任务依赖各自循环改造完成 + 外部环境。

> **每个活路径逐组件任务的通用改造动作**：①**第一步固定实证 sheet 名**——grep 组件 `sheetName` / render schema（`backend/data/ledger_adapters/wp_render_schema/`）/ `SheetLabels.ts` / `wp_code`，确认审定表真实 sheet 名能否解出 `[D-N]\d+-1`；不可解则任务内规整命名或按 R1 降级登记；②前端加中文二次确认 → 改走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`（多科目/发生额用 `writeback_rows`，`amount_kind` 标注 occurrence）；③移除 `PUT .../trial-balance/writeback` 直调 + 形态 B 的 `{cycle}:writeback-trial-balance` dispatch/listener（保留 `{cycle}:save-items` 等其他事件）；④**保留** `substantive:adjudicated` emit 及活路径跨模块联动（如 I6→I2）；⑤同循环 `useXFormData` 里被 adjudication/inline 取代的**零消费 writeback 重复定义**顺手删除（触类旁通，配 M1 注释范式）；⑥加前端单测（确认→post 命中/取消→无副作用/不再调旧端点/仍 emit）+ 后端集成测试 + 每组至少一个端到端验证点。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "16", "17"],
      "rationale": "并行前置。task1=M0 端点扩展（活路径改造的入参契约前置）；task16=K5/K7 假回写产品决策（K5/K7 处置前置，不依赖 M0）；task17=死代码集中清理（约40+处零消费，只删代码，不依赖 M0 端点扩展，可最先/并行做）。"
    },
    {
      "wave": 2,
      "tasks": ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"],
      "rationale": "各循环活路径逐组件改造（task2=M1 D 循环已完成）。不同循环组件互不依赖可并行；全部依赖 wave1 的 M0(task1) 扩展端点契约。K 循环活改造(7/8/9)另受 task16 决策约束（若 K5/K7 决策为补真回写则纳入 K 改造）。"
    },
    {
      "wave": 3,
      "tasks": ["18", "19"],
      "rationale": "收口：task18=grep 零直调断言（含 trial_balance 变体）+ CI 守卫；task19=旧端点删除/降级决策。依赖全部活改造(wave2)+死清理(task17)完成。"
    },
    {
      "wave": 4,
      "tasks": ["20", "21"],
      "rationale": "真实项目 UAT + Playwright 全链路实测，依赖各自循环改造完成且受外部环境（live PG 真实数据 / start-dev.bat）约束，标 data-blocked。"
    }
  ],
  "blocking": {
    "1": ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"],
    "16": ["7", "8", "9"],
    "2": ["18"],
    "3": ["18"],
    "4": ["18"],
    "5": ["18"],
    "6": ["18"],
    "7": ["18"],
    "8": ["18"],
    "9": ["18"],
    "10": ["18"],
    "11": ["18"],
    "12": ["18"],
    "13": ["18"],
    "14": ["18"],
    "15": ["18"],
    "17": ["18"],
    "18": ["19"]
  }
}
```

## Tasks

## M0：端点扩展（所有逐组件任务的前置）

- [x] 1. 扩展 `publish-to-tb` 端点支持预算行（`writeback_rows`）与发生额形态
  - `backend/app/routers/wp_html_save.py`：`PublishToTbRequest` 加 `writeback_rows: list[WritebackRow] | None`、`html_data` 改可选；新增 `WritebackRow{account_code, audited_amount, amount_kind}`
  - `writeback_rows` 存在 → 直接构造 `parsed_data.rows`（跳过 `fetch_audit_sheet_tb_values` 三分量重算）；否则回退原 `audit_rows` 路径
  - 二者都发结构一致的 `WORKPAPER_SAVED`（`publish_confirmed=True`+`confirmed_by`+`publish_token`）
  - 后端集成测试：三分量路径零回归 + `writeback_rows` 路径生效 + 发生额 `amount_kind` 透传 + `sheet_name` 不可解→400 + 幂等重放只写一次 + 普通保存(无 publish_confirmed)→TB 不变
  - _需求: 6, 7, 4, 3_
  - **✅ 完成证据（2026）**：
    - 改动文件：`backend/app/routers/wp_html_save.py`（`Literal` import + `WritebackRow` schema + `PublishToTbRequest.html_data → dict|None` + `writeback_rows` 入参 + 端点二选一路径逻辑 + `amount_kinds` 透传进 `extra`）
    - 新增测试：`backend/tests/test_publish_to_tb_writeback_rows.py`（12 用例）
    - 测试命令：`..\.venv\Scripts\python.exe -m pytest "D:/GT_plan/backend/tests/test_publish_to_tb_writeback_rows.py" "D:/GT_plan/backend/tests/test_publish_determination_to_tb.py" -q` → **18 passed / 0 failed**（12 新 + 6 D4-1 三分量零回归）
    - 覆盖点：writeback_rows 预算行直传不被三分量重算覆盖 / occurrence 语义透传 amount_kinds / 多科目 rows 全含 / 三分量零回归(1000+50+0=1050) / 两路径同给以 writeback_rows 优先 / sheet 不可解→400 / 两路径都空→400 / 空列表回退→400 / 同内容合成同 token(幂等由 handler tb_publish_ack 承载) / 显式 token 透传 / readonly&qc→403
    - 边界裁定（最小惊讶原则，已写注释）：两路径都为空→400；同时给以 `writeback_rows` 优先；`writeback_rows=[]` 空列表回退路径①
    - 幂等说明：端点侧保证同内容合成同 `publish_token`（本任务断言）；实际"只写一次"由 handler `_on_d_audit_determination_saved` 的 `tb_publish_ack` `ON CONFLICT DO NOTHING` 承载（既有 handler 集成测试已覆盖，handler 未改）
    - 设计与现状偏差：无。设计 §Components/接口1 对端点现状描述与真实代码一致（`html_data.audit_rows` 三分量重算 + `extract_determination_wp_code` + `publish_confirmed/confirmed_by/publish_token` 的 `WORKPAPER_SAVED`），handler 侧确认无需改动，扩展仅在端点侧。

## M1：D 循环

- [x] 2. D 循环审定表改走显式发布端点
  - `useD1FormData`~`useD7FormData`、`GtD2AccountsReceivable`（移除 `d2:writeback-trial-balance` dispatch）；D4 已完成作参照
  - 前端单测（每组件）+ D 审定表发布落库端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **逐组件消费实证（grep 全仓，非估算）**：D 循环 8 组件（D1~D7 + GtD2），D4 已完成作参照。核心发现——**仅 D2 有 live TB 写回路径**；D1/D3/D5/D6/D7 的 `writebackTrialBalance` 是**零消费死代码**（`export` 但无任何调用方：host `GtD{1,3,5,6,7}*.vue` 均不 destructure 它，各自 adjudication 只 `emit substantive:adjudicated` 不写 TB）。故对死代码组件按 I 循环 BP-5 铁律**移除死代码**（不接死代码），仅对 D2 live 路径复刻 D4-1 范式改造。
    - **sheet 名可解性表（extract_determination_wp_code 正则 `([D-N]\d+-1)\b`）**：

      | 组件 | writebackTB 定义 | live 消费方 | 旧端点直调(live) | sheet 名可解 | 本任务处理 |
      |---|---|---|---|---|---|
      | GtD2 + useD2Adjudication | 有(1122) | **有**（totalRow watcher 自动写→CustomEvent `d2:writeback-trial-balance`→GtD2→`PUT trial-balance/writeback`） | **是** | `审定表D2-1`→`D2-1` ✅ | **改造**：watcher 不再自动写；加 `publishToTb`（二次确认→`POST publish-to-tb` writeback_rows 科目1122 amount_kind=balance）；移除 CustomEvent 链；保留 `substantive:adjudicated` emit + `d2:save-items` |
      | useD1FormData | 有(参数) | **无**（GtD1 不 destructure；D1Adjudication 只 emit） | 无(死代码) | D1-1 可解(moot) | 移除死 writebackTB |
      | useD3FormData | 有(2203) | **无**（D3Adjudication 只 emit） | 无(死代码) | D3-1 可解(moot) | 移除死 writebackTB |
      | useD4* | (D4-1 已完成，参照系) | — | — | 审定表D4-1 ✅ | 不动 |
      | useD5FormData | 有(1124) | **无**（GtD5 不 destructure） | 无(死代码) | D5-1 可解(moot) | 移除死 writebackTB |
      | useD6FormData | 有(1141) | **无**（GtD6 不 destructure） | 无(死代码) | D6-1 可解(moot) | 移除死 writebackTB |
      | useD7FormData | 有(2205) | **无**（GtD7 不 destructure） | 无(死代码) | D7-1 可解(moot) | 移除死 writebackTB |

    - **改的文件（11 个源文件 + 1 新测试）**：
      - `composables/useD2Adjudication.ts`：移除 `inject(D2_WRITEBACK_KEY)` + 自动 watcher 写回 + 旧 `writebackTrialBalance`（CustomEvent/inject 旁路）；新增 `publishToTb`（`readonly/publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → `api.post publish-to-tb` writeback_rows[1122, amount_kind=balance] → 成功后 `publishAdjudicated()` emit）+ `publishing` ref；保留 watcher 的 `publishAdjudicated()` emit（Req 1：数据变化只 emit 不写 TB）
      - `GtD2AccountsReceivable.vue`：移除 `d2:writeback-trial-balance` 监听 + `d2Writeback` + `provide(D2_WRITEBACK_KEY)`（保留 `d2:save-items` + `D2_SAVE_ITEMS_KEY`）
      - `composables/d2InjectionKeys.ts`：删 `D2_WRITEBACK_KEY` / `D2WritebackFn`
      - `composables/useD2SaveInject.ts`：删 `writeback` 函数
      - `composables/useD2FormData.ts`：删死 `writebackTrialBalance` + export
      - `composables/useD1/D3/D5/D6/D7FormData.ts`（5 个）：删死 `writebackTrialBalance` + export
      - `d2/D2TabAdjudication.vue`：加「发布到试算表」按钮（`type=warning` `:loading=publishing` `:disabled=isReadonly` `@click=publishToTb`），destructure `publishToTb`/`publishing`
      - 新增测试 `composables/__tests__/d2AdjudicationPublishGate.spec.ts`（6 用例，复刻 D4 gate 测试范式）
    - **测试命令与 pass 数**：
      - 新测试：`rtk npx vitest run src/components/workpaper/composables/__tests__/d2AdjudicationPublishGate.spec.ts --reporter=dot` → **6 passed / 0 failed**（确认→post 命中 publish-to-tb body(sheet_name D2-1 / writeback_rows[1122] audited=500000 amount_kind=balance) / 不再调 trial-balance/writeback(PUT) / 取消→无 post 无 emit / readonly→无 post / 不再 dispatch d2:writeback-trial-balance / 成功后仍 emit substantive:adjudicated(D2/1122)）
      - 回归：`useD2FormData.spec + d2AccountsReceivable.property + useD3Adjudication + d1NotesReceivable.property + d2AdjudicationPublishGate` → **41 passed / 0 failed**
      - 后端 M0 契约（D2 依赖）：`test_publish_to_tb_writeback_rows.py` → **12 passed**
      - ESLint（12 改动文件）：**0 errors**（18 warnings 全为 useD2Adjudication 既存 no-amount-arithmetic/toFixed，均在未改的 crossValidation/totalRow 代码，新增代码 0 warning）
    - **发现的偏差/降级**：
      - 🟡 **D2 UX 变更（合理）**：原 D2 靠 `totalRow.currentAudited` watcher **自动**写 TB（无用户确认，正是本 spec 要消除的反模式）；改造后 D2 无「显式发布」入口 → 本任务在 D2TabAdjudication 新增「发布到试算表」按钮承载显式确认动作。符合 Req 2（回写必经显式确认）。
      - 🟢 **死代码登记（非降级，属清理）**：D1/D3/D5/D6/D7 的 `writebackTrialBalance` 零消费（同 I 循环 BP-5），按铁律移除而非接线，直接满足 Req 9.1（前端 `trial-balance/writeback` 命中数为 0 的收口目标，本批次已消除 6 处 D 循环直调）。
      - 🟢 **sheet 名全可解**：D 循环审定表子码均为标准 `D{n}-1`（`审定表D2-1` 实证可解），无不可解降级项。
      - ⚠️ **预存无关失败（非本任务引入）**：`d2SyncHostWiring.spec.ts` 6 用例 fail —— 该测试断言 GtD2 旧 `useD2SyncBridge`/`ooSheetRef`/`GtOnlyOfficeSheet` 接线，但 GtD2 已于 2026-09-10 DEC-10 迁移到 `useWorkpaperSyncBridge` 统一路径（与 TB 回写无关）。已用 `git stash` 我的改动后单跑该 spec 复现同样 6 fail/9 pass，证明**改动前即失败**，非本任务引入。
    - **端到端验证点**：前端单测覆盖「确认→publish-to-tb 落库路径」；后端 M0 集成测试覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写。真实项目 Playwright 全链路实测归 task 21*（待 start-dev.bat 环境）；真实 PG 无 D 循环审定数据的 UAT 归 task 20*（data-blocked）。
    - **⚠️ M1 遗漏（census 发现，归 task 17 清理）**：D4-1 已移除 `useD4Adjudication.publishAdjudicated` 的 `dispatch('d4:writeback-trial-balance')`，但 `GtD4OperatingRevenue.vue` 仍注册 `handleD4Writeback` 监听器 + `useD4FormData.writebackTrialBalance` 仍在——监听器无 dispatcher = 孤儿死代码（与 M1 对 D1/D3/D5/D6/D7 同源判法漏了 D4FormData 这处）。已登记进 task 17 死代码集中清理。

## 前置：产品决策 + 死代码集中清理（wave 1，不依赖 M0）

- [ ] 16. K5/K7 假回写产品决策（K 循环真实改造前置）
  - **背景（census 实证）**：K5 `handleTbWriteback` 弹「已回写TB(2701)」成功提示但只 `emit('save')` + `publishAdjudicated()`，**从不写 `trial_balance`**；K7 同理只 emit save（2401）。两循环当前无真实 TB 回写。
  - **交付**：向产品/审计负责人确认并记录决策——(a) 补真回写（走 `publish-to-tb`，与其他循环一致，纳入 task 7 K 单科目改造）；或 (b) 维持"仅审定不落 TB"（保留现状、仅清死代码 `useK5/K7FormData.writebackTB`、去掉误导性「已回写TB」成功提示避免假绿）
  - 决策写入本 spec Notes + 据决策更新 task 7 范围；无代码改动（纯决策 + 文档）
  - _需求: 2（消除假回写状态）_

- [ ] 17. 死代码集中清理（grep 0 调用后删除 + 收口注释，不依赖 M0）
  - **清理清单（census 实证零消费，删前逐项 grep 确认 0 调用方）**：
    - 各 `useXFormData.writebackTB/writebackTrialBalance` 被 adjudication/inline 取代的**重复定义**：H1/H3/H4/H6/H8/H9（FormData duplicate）、I1/I2/I3/I4/I5（FormData duplicate，BP-5）、I6/K2/K5/K6/K7/K8/K9/K11/K12/K13（FormData duplicate）
    - **J2 全模块孤儿链**：`composables/workpaper/j2/`（`useJ2FormData.writebackTB` 2221 + `useJ2Integration.onAdjudicationComplete` + 其 `events/publish` + `actuarial` 联动）——无渲染宿主 import，`ieOrphanBaseline.spec.ts` 已固化；连带整个 j2 孤儿模块登记删除
    - **共享工厂零调用**：`components/workpaper/composables/factories/createChecklistFormData.ts`（`createChecklistFormData(` 全仓 0 调用点）——删除工厂或其死 `writebackTB`；同步删/更新 `createChecklistFormData.spec.ts`
    - **D4 残留（M1 遗漏）**：`GtD4OperatingRevenue.vue` 的 `handleD4Writeback` 监听器（无 dispatcher）+ `useD4FormData.writebackTrialBalance`
    - **H8 断链**：`H8TabAdjudication.vue` 的 `onWritebackTB → emit('writeback-tb')`（GtH8 不绑 `@writeback-tb`，emit 无 listener）+ `useH8FormData.writebackTrialBalance`
    - **G6 变体端点**：`useG6MainFormData.writebackTB`（用变体端点 `POST /api/projects/{pid}/trial_balance`，零消费）
  - **验证**：删除前后全量前端测试绿（含 `ieOrphanBaseline.spec.ts` 不回归）；每处删除配 M1 已建的收口注释范式；本任务只删死代码，**无二次确认/端点改造/端到端测试**（Property 9）
  - _需求: 9.1, 9.3（清理死代码支撑最终 grep=0）_

## M2：F 循环（活，5 个，form B）

- [ ] 3. F 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep F1–F5 组件 `sheetName`/render schema(`backend/data/ledger_adapters/wp_render_schema/`)/`SheetLabels`，确认 `F{n}-1` 可解（R1 低风险，F5 成本 occurrence 存疑须确认）
  - 活路径（form B）：`useF1FormData`~`useF4FormData`、`useF5CosSalFormData` + `GtF1Prepayment`（移除 `f1:writeback-trial-balance`）、`GtF5CostOfSales`（移除 `f5:writeback-trial-balance`，保留 `f5:save-items` + `substantive:adjudicated` 供 F5-7 校验区）
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_

## M3：L 循环（活，8 个，A 形态）

- [ ] 4. L 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep L1–L8 确认 `L{n}-1` 可解（R1 低风险）
  - 活路径（A 形态，各 `useL{n}Adjudication` destructure+invoke）：`useL2FormData`~`useL8FormData`（`components/workpaper/composables/`）+ `useL1FormData`/`useL1Adjudication`/`useL3Adjudication`（`src/composables/`）；L1/L3 经 `writebackTB` 由 adjudication 层调用，统一改造。**L 循环无 FormData 死代码重复**（writeback 就在 FormData 被 Adjudication 消费）
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_

## M4：M 循环（活，10 个同构，可批量套模板）

- [ ] 5. M 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep M1–M10 确认 `M{n}-1` 可解（R1 低风险）
  - 活路径（10 个同构 A 形态：`useM{n}Adjudication` `const {writebackTB}=formData` + invoke）：`useM1FormData`~`useM10FormData`（权益类单科目为主）。**高度同构，套一个模板批量改**。**无 FormData 死代码重复**
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_

## M5：N 循环（活，5 个；N1 watcher 须改显式）

- [ ] 6. N 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep N1–N5 确认 `N{n}-1` 可解（N5 6801 occurrence 存疑须确认）
  - 活路径：`useN1FormData`~`useN5FormData`（5 个，税费）；**N1 特例**——`useN1Adjudication` 有 debounce watcher 自动写 TB（违反 Req 1），改造须把自动 watcher 写改为显式确认（watcher 只保留 emit，不写 TB）；N5(6801) 发生额；N4 有 V1+V2 两 adjudication；确认 `n1_deferred_tax_assets_service.py` DEPRECATED 裸 SQL 旁路不复活。**无 FormData 死代码重复**
  - 前端单测（断言 N1 数据变化只 emit 不写 TB）+ 端到端验证点
  - _需求: 1, 2, 8_

## M6：K 循环（活 11 个，多科目 + 发生额主战场；受 task 16 决策约束）

- [ ] 7. K 循环单科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep K2/K3/K4/K8/K9/K10/K11 确认子码可解（K8/K9/K11 发生额高风险须实证）
  - 活路径：`K2TabAdjudication`(inline btn，`tbAccountCode`)、K3(2241)/K4(2245)(btn→FormData.writebackTB)、K8(6601)/K9(6602)/K11(6701)(adjudication inline，发生额 `amount_kind=occurrence`)、K10(btn+A)
  - **依赖 task 16 决策**：K5(2701)/K7(2401) 若决策为(a)补真回写则纳入本任务；若(b)则不纳入（K5/K7 死代码归 task 17，成功提示由 task 16 处置）
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_

- [ ] 8. K1/K6 多科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep K1/K6 确认 `K1-1`/`K6-1` 可解
  - 活路径：`useK1FormData`（btn，1221+坏账准备双科目）、`GtK6HeldForSale`（inline btn，资产+负债，科目取自 `tb_source_codes` **动态解析后透传** `writeback_rows`，端点不硬编码科目）
  - 前端单测（断言双科目均在单次 post 的 writeback_rows）+ 端到端验证点（双科目均落库、幂等不双写）
  - _需求: 5, 2, 8_

- [ ] 9. K12/K13 发生额审定表改走显式发布端点
  - **第一步实证 sheet 名（R1 高风险）**：grep K12/K13 render schema/SheetLabels 实证「6301/6711 类损益审定表」sheet 名能否解出 `[D-N]{n}-1`；不可解则任务内规整命名或按 R1 降级登记
  - 活路径：`K12TabAdjudication`(inline btn，6301 发生额 `amount_kind=occurrence`)、`K13TabAdjudication`(inline btn，6711)。（`useK12/K13FormData.writebackTB` 是死代码 duplicate，归 task 17）
  - 前端单测 + 端到端验证点
  - _需求: 6, 2, 8_

## M7：H 循环（活 9 个，单/双科目 + 形态多样）

- [ ] 10. H 循环单科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep H1/H2/H3/H4/H5/H6/H7/H10 确认子码可解（H7 1621 公允 / H10 处置损益 occurrence 高风险须实证）
  - 活路径：H1(inline callback，1601/1602/1603 多科目)、H2(inline，1604)、H3(inline watcher 1.5s debounce，grossCode/accumDepCode，**防跨循环污染**：本项目无该科目则不写)、H4(inline，1605 LIKE 前缀)、H5(A，1631/1632 多科目)、H6(inline callback)、H7(inline api.put，cost/fair 两组件 1621)、H10(A+B，H10_ACCOUNT_CODE 发生额)
  - 前端单测（H3 断言不污染他循环）+ 端到端验证点
  - _需求: 1, 2, 8_

- [ ] 11. H9 双科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep H9 确认 `H9-1` 可解
  - 活路径：`H9TabAdjudication`(inline callback，租赁负债 + 未确认融资费用双科目)；**注意端点路径当前无 `/api` 前缀需归一**
  - 前端单测（双科目 writeback_rows）+ 端到端验证点
  - _需求: 5, 2, 8_

## M8：G 循环（活 11 个，sheet 名可解性存疑最高）

- [ ] 12. G 循环审定表改走显式发布端点（逐组件确认子码）
  - **第一步逐一实证 sheet 名（R1 中/高风险）**：grep 每个 G 底稿 `sheetName`/render schema/`SheetLabels` 实证能否解出 `[D-N]{n}-1`；G1/G2/G3/G5/G7 中风险（命名多样），G8–G14 高风险（损益/公允/减值发生额）
  - 活路径（form B）：G1–G3,G5,G7–G14（`useG{n}FormData` + `GtG{n}`，移除 `g{n}:writeback-trial-balance`，保留 `g{n}:save-items` 与「substantive:adjudicated 供跨模块刷新不重复写 TB」语义）；G7 多科目动态(权益+减值)；G8–G14 发生额可批量套模板。（G4 无 TB 回写正交排除；G6 变体端点死代码归 task 17）
  - **不可解者**：任务内规整命名，或按 R1 降级登记（保留旁路单独登记）。切换点 = 端点 `extract_determination_wp_code` 返回 None → 400
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8, 7_

## M9：I + E + J1（活 8 个；I2 先评估合规）

- [ ] 13. I 循环审定表改走显式发布端点（改 adjudication 层，避开 FormData 死代码）
  - **第一步实证 sheet 名 + I2 特例评估**：grep I1–I6 确认子码可解；**I2 已用新 per-wp 端点** `POST /api/workpapers/{wpId}/writeback-trial-balance`（非旧 project 端点）→ 先评估 I2 是否已合规 / 可直接并入 `publish-to-tb`，不当普通旧端点直调改
  - 活路径（adjudication 层 inline writeback）：I1(多科目 1701/1702/1703)、I3(1711)、I4(1801)、I5(1911)、I6(6602 发生额，**保留 I6→I2 联动** `research:expense-updated`+`i6:adjustment-writeback`)、I2(视评估结果)。（`useI1~I6FormData.writeback*` 是 BP-5 死代码 duplicate，归 task 17，**只改真实被消费的 adjudication，勿接死代码**）
  - 前端单测（I6 断言 I6→I2 联动仍发）+ 端到端验证点
  - _需求: 1, 2, 8_

- [ ] 14. E1 审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep E1 确认 `E1-1` 可解
  - 活路径：`useE1Adjudication`（多科目 byCode 遍历 → `writeback_rows`，self-invoke）
  - 前端单测 + 端到端验证点
  - _需求: 5, 2, 8_

- [ ] 15. J1 审定表改走显式发布端点（J2 是死代码，归 task 17）
  - **第一步实证 sheet 名**：grep J1 确认 `J1-1` 可解
  - 活路径：`J1TabAdjudication`（@click 按钮 inline，2211）。**J2 不在本任务**——census 实证 J2 整模块（`useJ2FormData`/`useJ2Integration` + `events/publish` + `actuarial` 联动）是无渲染宿主的孤儿链，J2 真实宿主 `J2TabAdjudication.vue` 无 TB 回写；J2 死代码清理归 task 17
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_

## M10：收口

- [ ] 18. 确认前端零直调 + 加 CI 守卫
  - 全仓 grep 断言 `audit-platform/frontend/src/**` 中 `trial-balance/writeback` 命中数 = 0 **且** `trial_balance` 变体端点（`projects/.../trial_balance` POST，G6）命中数 = 0
  - 加 CI 守卫脚本（断言无新增前端直调，覆盖两种字面量，命中即失败），接入 `governance-checks.yml`
  - 依赖全部活改造(3~15)+死清理(17)完成
  - _需求: 9.1, 9.2_

- [ ] 19. 决定旧端点删除 / 降级
  - grep 确认前端零调用且无服务内部合法调用方（S 类走独立 service，不算）后：删除 `writeback_audited_amount` 或降级为仅内部 `publish_confirmed` 调用
  - 后端测试确认删除/降级后无回归
  - _需求: 9.3_

## 可选任务（外部依赖 / 真实数据）

- [ ] 20.* 各循环真实项目端到端 UAT（data-blocked 降级）
  - 真实 PG 仅 5 个 standalone 项目、多数循环无对应审定表真实数据 → 对无数据循环标 `data-blocked`，降级为隔离项目/合成数据（复用 `seed_consol_uat.py` 式最小合成集）跑端点+handler 集成；真实项目补测点标"代码已改但真实项目未实测"
  - 切换点：待 live PG 有对应循环审定数据后逐组件回填
  - _需求: 全部（真实环境验证）_

- [ ] 21.* Playwright 全链路实测（待 start-dev.bat 环境）
  - 对已改造循环跑 Playwright：确认对话框 → 落库 → 报表读到新 audited → 重复确认不双写 → 普通保存不写 TB
  - 降级：环境不可用时以前端单测 + 后端集成测试覆盖，标"运行时未实测"
  - _需求: 1, 2, 4_

## Notes

- **活/死统计（census 权威）**：真正需完整改造的**活路径约 48 处**（E1 / F1–5 / G 11 / H 9 / I 6 / J1 / K 11 / L 8 / M 10 / N 5）；**死代码约 40+ 处**（H/I/K 的 FormData duplicate + J2 孤儿模块 + createChecklistFormData 工厂 + D4 残留 + G6 变体 + H8 断链）只需删除+收口（task 17，Property 9，无二次确认/端点改造/端到端测试）；**2 处产品决策**（K5/K7 假回写，task 16）。
- **任务量映射**：活改造 = task 2(D，已完成)/3(F)/4(L)/5(M)/6(N)/7~9(K)/10~11(H)/12(G)/13(I)/14(E1)/15(J1)；死清理 = task 17（集中）；决策 = task 16。
- **每个活改造任务第一步固定**：grep 组件 `sheetName`/render schema(`backend/data/ledger_adapters/wp_render_schema/`)/`SheetLabels`/`wp_code` 实证审定表真实 sheet 名能否解出 `[D-N]{n}-1`；不可解则任务内规整命名或按 R1 降级登记。
- **R1 sheet 名分层（design §设计风险 R1）**：高风险（损益类发生额）G8–G14/K8/K9/K11/K12/K13/N5/I6/H7/H10——必运行时实证；中风险 G1/G2/G3/G5/G7；低风险其余余额类。
- **K5/K7 假回写（task 16 决策前置）**：当前只 emit 不写 TB；决策(a)补真回写纳入 task 7，或(b)维持仅审定+清死代码+去误导提示。
- **N1 watcher（task 6）**：`useN1Adjudication` debounce watcher 自动写 TB 违反 Req 1，改造须改为显式确认。
- **I2 特例（task 13）**：已用新 per-wp 端点 `/api/workpapers/{wpId}/writeback-trial-balance`，先评估是否已合规/可并入，不当普通旧端点直调改。
- **G6 变体端点（task 17 清理）**：`useG6MainFormData` 用变体端点 `POST /api/projects/{pid}/trial_balance`（死代码），CI 守卫(task 18)须覆盖该字面量。
- **S 类正交不碰**：`SEstimateTBWritebackService`/`STransactionTBWritebackService` 全程不触碰（非目标）。
- **data-blocked 降级**：真实 PG 仅 5 个 standalone 项目，多数循环无对应审定表真实数据。无数据循环的端到端 UAT（task 20*）标 `data-blocked`，降级为隔离项目/合成数据（复用 `seed_consol_uat.py` 式最小合成集）跑端点+handler 集成；真实项目补测点标 `[ ]*`「代码已改但真实项目未实测」，待 live PG 有对应循环审定数据后逐组件回填。
- **Playwright 待环境**：task 21* 待 `start-dev.bat` 环境；不可用时以前端单测 + 后端集成测试覆盖，标「运行时未实测」。
- **`*` 可选任务**：20*/21* 为外部依赖/真实数据任务，非跳过项——环境就绪后须回填。
