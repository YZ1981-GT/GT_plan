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

- [x] 16. K5/K7 假回写产品决策（K 循环真实改造前置）
  - **背景（census 实证）**：K5 `handleTbWriteback` 弹「已回写TB(2701)」成功提示但只 `emit('save')` + `publishAdjudicated()`，**从不写 `trial_balance`**；K7 同理只 emit save（2401）。两循环当前无真实 TB 回写。
  - **交付**：向产品/审计负责人确认并记录决策——(a) 补真回写（走 `publish-to-tb`，与其他循环一致，纳入 task 7 K 单科目改造）；或 (b) 维持"仅审定不落 TB"（保留现状、仅清死代码 `useK5/K7FormData.writebackTB`、去掉误导性「已回写TB」成功提示避免假绿）
  - 决策写入本 spec Notes + 据决策更新 task 7 范围；无代码改动（纯决策 + 文档）
  - _需求: 2（消除假回写状态）_
  - **✅ 决策记录（2026，用户拍板）——决策 = (a) 补真回写**：
    - **裁定**：K5（预计负债，科目动态 `k5AccountCode`，默认 2701，防污染 L5 时为 2801）/ K7（递延收益，科目 2401）像其他 K 循环一样走显式发布门 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` **真正写 TB**，消除"提示成功但 TB 未变"的假回写状态（Property 10）。
    - **纳入 K 改造**：K5/K7 进入 **task 7（K 单科目）活路径改造**（不是 task 17 死代码清理）。K5 用动态 `k5AccountCode(props.tbSourceCodes)` 取科目（禁硬编码 2701），并**去掉误导性「已回写TB(2701)」成功提示**（改真回写后提示「已发布到试算表」）；K7 科目 2401（余额类 balance）。二者均加中文二次确认。
    - **口径**：K5 预计负债=balance（期末余额）；K7 递延收益=balance（期末余额）。
    - **sheet 名可解性实证**（render schema generated/K5.yaml、K7.yaml + K7-1.yaml）：K5 审定表 sheet 名 `审定表 K5-1`（`([D-N]\d+-1)\b` 解出 `K5-1` ✅）；K7 `审定表K7-1`（解出 `K7-1` ✅）。均可走 publish-to-tb，无降级。
    - **无本任务代码改动**（纯决策 + 文档）；据此决策 task 7 范围含 K5/K7 补真回写，实际代码改造证据见 task 7。

- [x] 17. 死代码集中清理（grep 0 调用后删除 + 收口注释，不依赖 M0）
  - **清理清单（census 实证零消费，删前逐项 grep 确认 0 调用方）**：
    - 各 `useXFormData.writebackTB/writebackTrialBalance` 被 adjudication/inline 取代的**重复定义**：H1/H3/H4/H6/H8/H9（FormData duplicate）、I1/I2/I3/I4/I5（FormData duplicate，BP-5）、I6/K2/K5/K6/K7/K8/K9/K11/K12/K13（FormData duplicate）
    - **J2 全模块孤儿链**：`composables/workpaper/j2/`（`useJ2FormData.writebackTB` 2221 + `useJ2Integration.onAdjudicationComplete` + 其 `events/publish` + `actuarial` 联动）——无渲染宿主 import，`ieOrphanBaseline.spec.ts` 已固化；连带整个 j2 孤儿模块登记删除
    - **共享工厂零调用**：`components/workpaper/composables/factories/createChecklistFormData.ts`（`createChecklistFormData(` 全仓 0 调用点）——删除工厂或其死 `writebackTB`；同步删/更新 `createChecklistFormData.spec.ts`
    - **D4 残留（M1 遗漏）**：`GtD4OperatingRevenue.vue` 的 `handleD4Writeback` 监听器（无 dispatcher）+ `useD4FormData.writebackTrialBalance`
    - **H8 断链**：`H8TabAdjudication.vue` 的 `onWritebackTB → emit('writeback-tb')`（GtH8 不绑 `@writeback-tb`，emit 无 listener）+ `useH8FormData.writebackTrialBalance`
    - **G6 变体端点**：`useG6MainFormData.writebackTB`（用变体端点 `POST /api/projects/{pid}/trial_balance`，零消费）
  - **验证**：删除前后全量前端测试绿（含 `ieOrphanBaseline.spec.ts` 不回归）；每处删除配 M1 已建的收口注释范式；本任务只删死代码，**无二次确认/端点改造/端到端测试**（Property 9）
  - _需求: 9.1, 9.3（清理死代码支撑最终 grep=0）_
  - **进度 · 批A（I4/I5/I6 FormData）已清理（2026）**：删除 3 处零消费 writeback 死代码（`useI4FormData.writebackTrialBalance` 科目1801 / `useI5FormData.writebackTrialBalance` 科目1911 / `useI6FormData.writebackTB` 科目6602 发生额），每处配收口注释 + 移除 return export。
    - **grep 0 调用实证**：①I4——`useI4FormData` 全仓无 import（GtI4LongTermPrepaid 注释明示"勿再用孤儿 useI4FormData"，壳层自管），`writebackTrialBalance` 0 消费；②I5——`useI5FormData` 被 GtI5OtherNoncurrentAssets 引入但仅 destructure `isLoading/allResponses/tbData/selfLoad/saveImmediate`，未取 `writebackTrialBalance`，0 消费；③I6——`useI6FormData` 无任何 host import（仅 `createChecklistFormData.ts` 与 `useI6CrossSheet.ts` 的**文档注释**提及，非调用），`writebackTB` 0 消费。全仓 `*.spec.ts`/`*.test.ts` 对三符号 0 引用。
    - **保留的活路径（本批不动，归 M9/task13）**：`useI4Adjudication.writeback`(1801) / `useI5Adjudication.writeback`(1911) / `useI6Adjudication.writeback`(6602 含 I6→I2 联动 `research:expense-updated`+`i6:adjustment-writeback`)——均为 adjudication 层 inline `api.put(.../trial-balance/writeback)` 真实被消费，未删。
    - **测试**：I 循环相关 16 个 spec 全绿（useI4/I5/I6Adjustment + i4/i5AdjudicationModel + i6AdjustmentModel + iCycleComposableExports + i4i5ConsistencyAndReconcile = 75 passed；i6Enhancements + useI6Detail/Cutoff/TargetedCheck + useI4/I5Detail + iCycleDisclosureWiring/DynamicRows = 123 passed）；ESLint 3 改动文件 0 error（9 warnings 全为未改代码既存）。Property 9：无测试因删除变红。
    - **改的文件**：`useI4FormData.ts` / `useI5FormData.ts` / `useI6FormData.ts`（各删 function 体 + return export + 加收口注释）。**未触碰 ieOrphanBaseline.spec.ts**（基线更新留批C 收尾）。
  - **进度 · 批B（K 循环 FormData）已清理（2026）**：删除 6 处零消费 `useKxFormData.writebackTB` 死代码 —— **useK6/K7/K8/K9/K11/K13FormData**（每处删 function 体 + return export + 移除随之失效的 `eventBus` import + 加中文收口注释）。**K1/K3/K4 是活路径，未删**（归 M6/task7~8）。**K2/K5/K12 有专属测试消费其 FormData.writebackTB，Property 9 触发，本批保留待决策，未删**。
    - **grep 0 调用 / 活路径判定表（全仓 grep 实证，排除 __tests__ 判活路径）**：

      | useKxFormData | writebackTB(科目) | 生产宿主 destructure/调用 | 专属测试引用 | 判定 | 本批处理 |
      |---|---|---|---|---|---|
      | **useK1FormData** | writebackTB(1221+坏账准备,双) | **有**：`K1TabAdjudication.vue:572` `const {writebackTB}=useK1FormData` + line757 调用 | k1Integration.test.ts | **活路径** | **保留**（归 M6/task8 多科目改造） |
      | **useK3FormData** | writebackTB(2241) | **有**：`K3TabAdjudication.vue:405` destructure + line509 调用 | k3Integration/k3OtherPayables | **活路径** | **保留**（归 M6/task7） |
      | **useK4FormData** | writebackTB(2245) | **有**：`K4TabAdjudication.vue:323` destructure + line404 调用 | k4Integration | **活路径** | **保留**（归 M6/task7） |
      | **useK6FormData** | writebackTB(1481+2605,双) | **0**：全仓无任何 import（孤儿 composable，含 test 亦零引用）；活路径在 `GtK6HeldForSale.provide('k6WritebackTB')` inline | 无 | **零消费死代码** | **删除** |
      | **useK7FormData** | writebackTB(2401) | **0**：无渲染宿主 import（仅 test import 用别的方法）；K7 真实审定在 K7TabAdjudication 仅 emit（task16 假回写） | 无（对 writebackTB） | **零消费死代码** | **删除** |
      | **useK8FormData** | writebackTB(6601 发生额) | **0**：无渲染宿主 import（仅 test 用 setTbValues）；活路径 `useK8Adjudication.writeback` inline | 无（对 writebackTB） | **零消费死代码** | **删除** |
      | **useK9FormData** | writebackTB(6602 发生额) | **0**：无渲染宿主 import（仅 test 用 setTbValues）；活路径 `useK9Adjudication.writeback` inline | 无（对 writebackTB） | **零消费死代码** | **删除** |
      | **useK11FormData** | writebackTB(6701 发生额) | **0**：`k11-integration.test.ts` 仅 `useK11FormData` 用 setTbValues/selfLoad，不调 writebackTB；活路径 `useK11Adjudication.writeback` inline | 无（对 writebackTB） | **零消费死代码** | **删除** |
      | **useK13FormData** | writebackTB(6711 发生额) | **0**：`K13TabAdjustment.vue` 引 useK13FormData 仅用 save/subtotal（不 destructure writebackTB）；活路径在 K13TabAdjudication inline `handleWritebackTBInternal`（非 FormData.writebackTB） | 无（对 writebackTB） | **零消费死代码** | **删除** |
      | **useK2FormData** | writebackTB(1901) | **0 生产**：`K2TabAdjudication.vue` 仅 import type；活路径 inline `handleWritebackTB` | **有**：`k2Integration.spec.ts` 3 用例直调 `formData.writebackTB` | 死代码但**测试消费** | **保留待决策**（Property 9；删需连带更新测试，超批B纯删范围） |
      | **useK5FormData** | writebackTB(2801,源已从2701漂移) | **0 生产**：仅 import type | **有**：`k5Provisions.integration.spec.ts` 4 用例 + `kCycleAccountScope.spec.ts` 源码扫描 | 死代码但**测试消费** | **保留待决策**（Property 9；且 K5 归 task16 假回写决策） |
      | **useK12FormData** | writebackTB(6301 发生额) | **0 生产**：`K12TabAdjustment.vue` 引 useK12FormData 用 save/subtotal，但 `K12TabAdjudication.vue:461` 传给 useK12Adjudication 的 writebackTB 是本地 `handleWritebackTBInternal`（非 FormData.writebackTB） | **有**：`k12Integration.test.ts` 多用例直调 `formData.writebackTB` | 死代码但**测试消费** | **保留待决策**（Property 9） |

    - **删的文件（6 个）**：`useK6FormData.ts` / `useK7FormData.ts` / `useK8FormData.ts` / `useK9FormData.ts` / `useK11FormData.ts` / `useK13FormData.ts`（各删 writebackTB function 体 + return export + 失效的 `eventBus` import + 中文收口注释「原 writebackTB … 为零消费死代码，已移除；TB 回写走显式发布门 publish-to-tb（M6/task7~9 改造）。spec: Task 17」）
    - **保留的活路径（本批不动，归 M6/task7~8）**：`useK1/K3/K4FormData.writebackTB`（TabAdjudication btn→FormData.writebackTB 真实调用）；K6 live 在 GtK6HeldForSale inline；K8/K9/K11 live 在各 useKxAdjudication.writeback inline；K12/K13 live 在 TabAdjudication inline handleWritebackTBInternal。
    - **保留待决策（Property 9 触发）**：K2/K5/K12 的 `useKxFormData.writebackTB` 虽为死代码 duplicate，但有专属测试直调（k2Integration.spec 3 / k5Provisions.integration.spec 4 + kCycleAccountScope 源扫 / k12Integration.test 多），硬删会使这些测试变红。按铁律「绝不硬删活路径 + Property 9 回滚记录」，本批**不删**，登记待「连带更新/移除专属测试」的后续处理（K5 另归 task16 假回写决策）。
    - **测试**：删除后 K 相关 7 spec 全绿 —— `k1Integration + k12Integration + k11-integration + k9-integration + useK8CrossSheet + useK5CrossSheet + kCycleAccountScope` = **165 passed / 0 failed**（含 k12Integration 对 useK12FormData.writebackTB 全过=证明 K12 正确保留；k11-integration 用 setTbValues 全过=证明 K11 删除无害）。Property 9：6 处删除无任何测试变红。
    - **⚠️ 预存无关失败（非本批引入，已实证）**：`k5Provisions.integration.spec.ts`(3) + `k5PersistenceMigration.spec.ts`(1) 共 **4 fail**，根因=K5FormData 源码科目已于 2026-08-09 按 report_config 从 `2701`→`2801`（防污染 L5 长期应付款），但两 K5 spec 仍断言旧 `2701` → 测试期望滞后。`git status` 实证 **useK5FormData.ts 不在本批改动清单**（本批仅 K6/7/8/9/11/13），故与批B 无关，属 K5 既存 test-vs-source drift，归 task16 K5 处置/独立测试更新，本批不修。
    - **ESLint（6 改动文件）**：**0 errors**（31 warnings 全为 loadTbData/setTbValues 未改代码既存的 `no-amount-arithmetic`/`no-direct-audit-fetch`，新增/删除处 0 warning）；getDiagnostics 6 文件 0 问题。
    - **改的文件**：`useK6/K7/K8/K9/K11/K13FormData.ts`（各删 writebackTB + return export + eventBus import + 收口注释）。**未触碰 ieOrphanBaseline.spec.ts**（基线更新留批C 收尾）。
  - **进度 · 批C（收尾：J2/工厂/D4/G6 + K2/K12 测试连带 + h6 遗留 + ieOrphanBaseline 裁定）已完成（2026）**：删/收口剩余死代码，Task 17 主 checkbox 就此打勾。
    - **① J2 全模块孤儿链**：删除 `composables/workpaper/j2/useJ2FormData.ts`（writebackTB 2221，走变体端点 `POST .../trial-balance/writeback`）+ `useJ2Integration.ts`（onAdjudicationComplete TB回写）+ 更新 barrel `j2/index.ts` 移除两 export（加收口注释）。**grep 0 实证**：二者仅 `j2/index.ts` barrel 引用；全仓无 `from '...j2'`/`from '@/composables/workpaper/j2'`（barrel 零真实消费方）；J2 目录 10 个 `.vue`（GtJ2DefinedBenefitPlan/J2Tab*）无一 import；`j2/__tests__` 无引用。**保守边界**：只删这两个 TB 回写 composable（本 spec 半径），j2 目录其余 composable（ImportExport/Actuarial/Formula 等）属 I/E 孤儿链，归 `workpaper-import-export-lifecycle-closure` spec，未动。
    - **② createChecklistFormData 工厂**：删除工厂的死 `writebackTB(amounts)`（PUT `.../trial-balance/writeback` + emit）+ return 条目 + `eventBus` import + `year/accountCodes` destructure（加收口注释）；同步删 `createChecklistFormData.spec.ts` 3 个 writebackTB 用例。**grep 0 实证**：`createChecklistFormData(` 全仓仅 barrel export + 其 test + 自定义文件引用，**0 生产调用点**。**保守边界**：只删死 writebackTB，保留工厂本体（load/save/persistence/debounce/hydrate 等能力属 `workpaper-maintainability-convergence` spec，非本 spec 半径）。
    - **③ D4 残留（M1 遗漏）**：删 `GtD4OperatingRevenue.vue` 的 `handleD4Writeback` 监听器（+ `d4:writeback-trial-balance` addEventListener/removeEventListener + 未用的 `D4_MAIN/OTHER_REVENUE_STANDARD` import）+ `useD4FormData.writebackTrialBalance`（6001/6051）+ return 条目（加收口注释）。**grep 0 实证**：全仓 0 `d4:writeback-trial-balance` dispatcher（M1 已从 useD4Adjudication 移除）→ 监听器孤儿；`useD4FormData` 仅 GtD4 import（其余全 type-only），`writebackTrialBalance` 仅被该孤儿监听器调用、无测试直调。
    - **④ G6 变体端点**：删 `useG6MainFormData.writebackTB`（走变体端点 `POST /api/projects/{pid}/trial_balance` 科目 1503）+ return 条目（加收口注释）。**grep 0 实证**：`GtG6OtherBondMain.vue` import useG6MainFormData 但**不 destructure/调用 writebackTB**；无任何测试消费；G6 真实回写在 `useG6MainAdjudication`（aggregateG6WritebackNets）。**变体端点 CI 命中清零**：全仓 `projects/.../trial_balance` HTTP 调用数由 1→**0**（task 18 CI 守卫覆盖）。
    - **⑤ K2/K12 测试连带（批B 保留待决策的）**：
      - **K2**：删 `useK2FormData.writebackTB`（解析科目实证 1901）+ return + `eventBus`/`K2_GROSS_FALLBACK_STANDARD` import（加收口注释）；`k2Integration.spec.ts` 删 3 个直调 writebackTB 用例（端点+EventBus / timestamp / 失败不emit），保留 subtotalRow 用例（测 useK2Adjudication 活路径）。**grep 0 实证**：无 `.vue` import useK2FormData（活路径在 K2TabAdjudication inline handleWritebackTB），writebackTB 仅 k2Integration 直调。
      - **K12**：删 `useK12FormData.writebackTB`（6301 发生额 is_occurrence）+ return + `eventBus` import（加收口注释）；`k12Integration.test.ts` 删 Part A(5)+Part B(2) 共 7 个直调 writebackTB 用例 + 未用的 `useK12FormData`/`ref`/`afterEach` import + 空 formData 声明，保留 Part C/D/E（附注订阅 handler / 后端 regex / 事件流分离，用本地函数不调 writebackTB）。**grep 0 实证**：`K12TabAdjustment.vue` 仅用 `formData.selfLoad`（不 destructure writebackTB），活路径在 K12TabAdjudication inline handleWritebackTBInternal；`k12AdjustmentEventBus.test.ts` 仅注释提及 writebackTB 不调用。
    - **⑥ h6 批B 遗留破损测试（触类旁通补删）**：批B 已删 `useH6FormData.writebackTrialBalance`（1606）死代码但漏删直调它的 `h6Integration.spec.ts` describe('H6 集成 — TB回写')，致该用例 `formData.writebackTrialBalance is not a function` 变红。批C 删该 describe（唯一用例测死代码）+ 未用的 `beforeEach/afterEach/nextTick` import。**grep 0 实证**：`useH6FormData` 无 `.vue` 生产宿主；H6 活路径在 H6TabAdjudication.onWritebackTB→useH6Adjudication.publishAdjudicated。
    - **⑦ K5 保守保留（未删，如实登记）**：`useK5FormData.writebackTB`（k5AccountScope 解析，源已 2701→2801）是零生产消费死代码（K5TabAdjudication 仅 type import），但——(a) K5 归 **task16 假回写产品决策**（未定）；(b) 其 4 个专属失败中 3 个（`k5Provisions.integration.spec.ts` 的 writebackTB 断言 2701）就是被明确要求「别碰」的科目 drift 失败，硬删会连带触及。按铁律「边界不清/风险高保守保留」，**未删 K5 writebackTB 及其测试**，登记待 task16 决策 + 独立 test-vs-source drift 修复（k5PersistenceMigration 那 1 个 loadTbData `account_prefix:2701` 断言失败同属 drift，非 writebackTB，一并归独立修复）。
    - **⑧ ieOrphanBaseline.spec.ts 基线裁定（未修改，实证记录）**：**该 spec 属 `workpaper-import-export-lifecycle-closure`**（其头注释明示），追踪 **I/E ImportExport composable 孤儿**（useH5/K1Writeoff/L4/K0/L0/**useJ2ImportExport** 共 6 个），**不追踪本 spec 的 TB writeback 死代码**。其唯一 1 个红 = 该 spec Wave4 Task16/17 的**故意打红占位**（文件注释明确禁止改成 `toBeLessThanOrEqual(6)`）。我删的是 `useJ2FormData`/`useJ2Integration`（**非** `useJ2ImportExport`），**对其孤儿集合零影响**——`git stash` 我的 j2 改动后单跑该 spec 得**完全相同** 1 failed/25 passed（同 6 孤儿），证明批A/B/C 全程未删任何 I/E 孤儿、基线本就无需下调。改它=跨 spec 违规 + 掩盖他 spec 追踪，故**不动**。（原批C 预期「清理使孤儿归零→更新基线」的前提不成立：本 spec 清的是 TB writeback 死代码，与 I/E 孤儿正交。）
    - **验证**：直接受影响 spec 全绿——`createChecklistFormData.spec` + `k2Integration.spec` + `k12Integration.test` + `k12AdjustmentEventBus.test` + `j2.e2e/j2Components` = **77 passed**；`d4/d2AdjudicationPublishGate` + `k1Integration` + `g6OtherBondMain.integration` 全绿；`h6Integration.spec` 补删后**全绿**。ESLint 11 改动文件 **0 error**（10 warnings 全为未改代码既存 no-amount-arithmetic/no-status-string-literal/no-direct-audit-fetch）。getDiagnostics 全 0。
    - **⚠️ 预存无关失败（非批C 引入，git 实证我改动集零 L/K5 源文件）**：①`ieOrphanBaseline.spec.ts` 1 红（他 spec 故意占位，见⑧）；②`l6-integration.test.ts`(2)/`l7-integration.test.ts`(2) 账户码 drift（2601→2711 / 2801→BS-071，L 循环 **活路径** writebackTB 仍在、测试断言滞后，L 循环未在批A/B/C 触碰）；③K5 4 drift（见⑦）。三者均属既存 test-vs-source drift，归各自 spec/独立修复。
    - **改的文件**：`composables/workpaper/j2/index.ts`（+删 useJ2FormData.ts/useJ2Integration.ts）/ `factories/createChecklistFormData.ts` + 其 spec / `GtD4OperatingRevenue.vue` / `useD4FormData.ts` / `useG6MainFormData.ts` / `useK2FormData.ts` + `k2Integration.spec.ts` / `useK12FormData.ts` + `k12Integration.test.ts` / `h6Integration.spec.ts`。
  - **📋 Task 17 三批汇总（A+B+C 全完成）**：
    - **批A（I 循环 FormData）**：删 3 处死代码——`useI4FormData.writebackTrialBalance`(1801) / `useI5FormData.writebackTrialBalance`(1911) / `useI6FormData.writebackTB`(6602)；活路径 useI4/I5/I6Adjudication.writeback 保留。
    - **批B（H+K 循环 FormData）**：删 H1/H3/H4/H6/H8/H9 + K6/K7/K8/K9/K11/K13 的零消费 FormData writeback 死代码（含 H8 断链）；K1/K3/K4 活路径保留；K2/K5/K12 因测试消费保留待批C。
    - **批C（收尾）**：删 J2 孤儿链(2) + createChecklistFormData 死 writebackTB + D4 残留(监听器+FormData) + G6 变体端点 + K2/K12 死 writebackTB(连带 10 测试用例) + h6 批B 遗留破损测试(补删)。K5 保守保留（task16 决策未定）。
    - **累计删除死代码源文件/方法**：整文件删 2（useJ2FormData/useJ2Integration）；方法级删 ~20+（I3 + H/K 批B ~12 + 批C 的 D4/G6/K2/K12/factory/D4监听器 6）。
    - **保留活路径**：约 48 处（E1/F/G/H/I-adjudication/J1/K1-K5活/L/M/N inline 或 adjudication，归 tasks 3-15 逐组件改造）。
    - **保守保留待独立处理**：K5 writebackTB（task16）；ieOrphanBaseline（他 spec）。
    - **收口指标**：全仓（排除 test）变体端点 `projects/.../trial_balance` HTTP 调用 **0**（G6 清零）；`trial-balance/writeback` LIVE HTTP **76**（全为 tasks 3-15 待迁移活路径，死代码已清 0，task 18 CI 守卫将断言活路径迁移后归 0）。Property 9 满足：死代码删除后无活路径依赖、现有测试不因删除变红（h6 遗留已补，K5 属既存 drift 未引入）。

## M2：F 循环（活，5 个，form B）

- [x] 3. F 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep F1–F5 组件 `sheetName`/render schema(`backend/data/ledger_adapters/wp_render_schema/`)/`SheetLabels`，确认 `F{n}-1` 可解（R1 低风险，F5 成本 occurrence 存疑须确认）
  - 活路径（form B）：`useF1FormData`~`useF4FormData`、`useF5CosSalFormData` + `GtF1Prepayment`（移除 `f1:writeback-trial-balance`）、`GtF5CostOfSales`（移除 `f5:writeback-trial-balance`，保留 `f5:save-items` + `substantive:adjudicated` 供 F5-7 校验区）
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名可解性 + 科目 + 口径实证表（`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b`，全可解无降级；F 全 form B）**：

      | 组件 | 科目 | 口径 amount_kind | 审定表 sheet 名（实证来源 `useFPurchaseInventorySheetGroups.test.ts`） | 解出子码 | dispatcher（form B） | writeback_rows |
      |---|---|---|---|---|---|---|
      | F1 预付账款 | 1123 | balance | `审定表F1-1` | F1-1 ✅ | useF1Adjudication.publishAdjudicated | 单行 1123 |
      | F2 存货 | **多科目动态**（`F2_ROW_KEY_ACCOUNT`：1401~1411/1412进销差价/1471跌价，各类别净值 endAudited） | balance | `存货审定表F2-1` | F2-1 ✅ | useF2Adjudication.publishAdjudicated（原 per-account dispatch） | 多行（按科目归集净值，一次原子发布） |
      | F3 应付票据 | 2201 | balance | `审定表F3-1` | F3-1 ✅ | useF3Adjudication.publishAdjudicated | 单行 2201 |
      | F4 应付账款 | 2202 | balance | `审定表F4-1` | F4-1 ✅ | useF4Adjudication.publishAdjudicated | 单行 2202 |
      | F5 营业成本 | 6401 | **occurrence（损益类发生额！）**（F5TabAdjudication guidance 明示"损益类仅列本期/上期发生额，无期初期末"） | `营业务成本审定表F5-1` | F5-1 ✅ | useF5Adjudication.publishAdjudicated | 单行 6401 occurrence |

    - **form B 链处置（删/留清单，实证 grep `f[1-5]:writeback-trial-balance` 全仓仅剩注释/docstring）**：
      - **删（dispatch）**：`useF1/F2/F3/F4/F5Adjudication.publishAdjudicated` 内的 `window.dispatchEvent('f{n}:writeback-trial-balance')`（F2 是 per-account 循环 dispatch）——**改造后 publishAdjudicated 只 emit `substantive:adjudicated`**。
      - **删（listener + handler）**：`GtF{1-5}` 的 `handleF{n}Writeback` + `window.addEventListener('f{n}:writeback-trial-balance')` + `removeEventListener`；GtF1 连带删无用的 `onBeforeUnmount` import。
      - **删（FormData 死代码）**：`useF1FormData.writebackTrialBalance(1123)` / `useF2/F3/F4FormData.writebackTrialBalance(accountCode,amount)` / `useF5CosSalFormData.writebackTrialBalance` + 各自 return export（唯一消费方是被删的 handleF{n}Writeback ⇒ 零消费死代码）。各处配中文收口注释。
      - **保留（严格）**：`f1/f2/f3/f4/f5:save-items` 监听全保留（GtF{1-5} 的 handleF{n}SaveItems + onBeforeUnmount 中的 remove）；`substantive:adjudicated` emit 全保留。
    - **🔴 F5-7 校验区保留证据（重点）**：`GtF5CostOfSales.vue` 的 **`substantive:adjudicated` 监听器（handleAdjudicated，消费 6401 审定营业成本 → adjudicatedCOGS → F5-7 成本倒轧校验区 + 持久化）严格保留**（onMounted/onBeforeUnmount 均只删 `f5:writeback-trial-balance` 那一条，`f5:save-items` + `substantive:adjudicated` 两条完整保留）；`useF5Adjudication.publishAdjudicated` 仍 emit `substantive:adjudicated`（6401），且 `publishToTb` 成功后调 `publishAdjudicated()` ⇒ F5-7 校验区在发布后仍收到审定数刷新。测试断言 F5 发布后仍 emit substantive:adjudicated(wpCode=F5)。
    - **改造范式（复刻 D2/D4-1）**：每个 `useF{n}Adjudication` 新增 `publishToTb`（`readonly/publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → `import api` → `api.post('/api/workpapers/{wpId}/audit-determination/publish-to-tb', {sheet_name, writeback_rows})` → `ElMessage.success` → `publishAdjudicated()` 通知下游；取消/readonly 无副作用）+ `publishing` ref；F2 多科目用 `aggregateAuditedByAccount()`（publishAdjudicated 与 publishToTb 共用）生成多行 writeback_rows。**useF4/F5Adjudication 原不 destructure `wpId`（TB 回写走 projectId），本次补 `wpId`**（F5 的 projectId 改造后无用，从 destructure 移除但保留 options 接口）。各 Tab 发布按钮改 `type=warning` `:loading=publishing` 文案统一「发布到试算表」，`confirmAdjudication` 改 async 调 `publishToTb`（F4 保留原 crossCheck/variance 守卫再发布）。
    - **改的文件（20 源 + 1 新测试 = 21）**：
      - Adjudication（5）：`useF1Adjudication.ts` / `useF2Adjudication.ts` / `useF3Adjudication.ts` / `useF4Adjudication.ts` / `useF5Adjudication.ts`（移除 dispatch + 加 publishToTb/publishing + import ElMessage/ElMessageBox；F2 加 aggregateAuditedByAccount；F4/F5 补 wpId destructure）
      - FormData（5）：`useF1FormData.ts` / `useF2FormData.ts` / `useF3FormData.ts` / `useF4FormData.ts` / `useF5CosSalFormData.ts`（删 writebackTrialBalance + return export + 收口注释；ElMessage 仍用于 load/save 保留 import）
      - Tab 组件（5）：`f1/F1TabAdjudication.vue` / `f2/core/F2TabAdjudication.vue` / `f3-notes-payable/F3TabAdjudication.vue` / `f4-accounts-payable/F4TabAdjudication.vue` / `f5-cost-of-sales/F5TabAdjudication.vue`（destructure publishToTb/publishing + 按钮改造 + confirm 改 async 调 publishToTb）
      - 宿主（5）：`GtF1Prepayment.vue` / `GtF2InventoryMain.vue` / `GtF3NotesPayable.vue` / `GtF4AccountsPayable.vue` / `GtF5CostOfSales.vue`（删 handleF{n}Writeback + f{n}:writeback listener + writeback 调用；GtF1 删 onBeforeUnmount import；GtF5 严格保留 save-items + substantive:adjudicated）
      - 新增测试：`composables/__tests__/fAdjudicationPublishGate.spec.ts`（参数化 F1~F5 × 6 用例 = 30）
    - **测试命令与 pass 数**：
      - 新测试：`rtk npx vitest run src/components/workpaper/composables/__tests__/fAdjudicationPublishGate.spec.ts --reporter=dot` → **30 passed / 0 failed**（确认→POST publish-to-tb body(sheet_name 匹配 F{n}-1 / writeback_rows 含期望科目 / amount_kind F1-4=balance F5=occurrence) / 不再调 trial-balance/writeback(PUT) / 取消→无 post 无 emit / readonly→无 post / 不再 dispatch f{n}:writeback-trial-balance / 发布成功仍 emit substantive:adjudicated(wpCode)）
      - F 既有回归：`GtF4AccountsPayable.integration + GtF3NotesPayable.integration + useF4Adjudication + f4AgingUnification.pbt + useF2Adjudication.p6 + useF2Adjudication.seed + useF1AgingScope` → **169 passed / 0 failed**（GtF3/GtF4 integration 中断言 f3/f4:writeback payload 形状的用例是本地 payload 断言，非实际 dispatch，未受影响仍绿）
      - D2 gate 回归（共享 eventBus）：`d2AdjudicationPublishGate.spec.ts` → **6 passed**
      - ESLint（21 改动文件）：**0 errors**（34 warnings 全为未改代码既存 `no-adhoc-wp-structure`(表渲染 19) / `no-amount-arithmetic`(小计公式 10) / `no-amount-toFixed`(格式化 5)，新增 publishToTb/发布按钮 0 warning）；getDiagnostics 20 源 + 1 测试全 0。
    - **发现的偏差/降级**：
      - 🟢 **sheet 名全可解**：F 循环审定表子码均标准 `F{n}-1`（`useFPurchaseInventorySheetGroups.test.ts` 实证 `审定表F1-1`/`存货审定表F2-1`/`审定表F3-1`/`审定表F4-1`/`营业务成本审定表F5-1`），无不可解降级项。
      - 🟢 **F5 occurrence 已确认**：F5 营业成本损益类，`amount_kind='occurrence'`（唯一非 balance），前端已算最终发生额直传 writeback_rows（Req 6）。
      - 🟢 **F2 多科目**：动态科目由前端 `F2_ROW_KEY_ACCOUNT` 按净值归集后透传，端点不硬编码（Req 5.2）。
      - 🟢 **死代码登记（非降级，属清理）**：F1~F5 各 FormData writeback 移除后唯一消费方（handleF{n}Writeback）同批移除，前端 `trial-balance/writeback` 命中数减少 5+（F2 原 per-account 更多），支撑 Req 9.1 收口。
    - **端到端验证点**：前端单测覆盖「确认→publish-to-tb 落库路径」+「F5-7 校验区 substantive:adjudicated 回归」；后端 M0 集成测试覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写（F5 occurrence 透传已在 M0 test_publish_to_tb_writeback_rows 覆盖）。真实项目 Playwright 全链路归 task 21*（待 start-dev.bat 环境）；真实 PG 无 F 循环审定数据的 UAT 归 task 20*（data-blocked）。

## M3：L 循环（活，8 个，A 形态）

- [x] 4. L 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep L1–L8 确认 `L{n}-1` 可解（R1 低风险）
  - 活路径（A 形态，各 `useL{n}Adjudication` destructure+invoke）：`useL2FormData`~`useL8FormData`（`components/workpaper/composables/`）+ `useL1FormData`/`useL1Adjudication`/`useL3Adjudication`（`src/composables/`）；L1/L3 经 `writebackTB` 由 adjudication 层调用，统一改造。**L 循环无 FormData 死代码重复**（writeback 就在 FormData 被 Adjudication 消费）
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名可解性 + 科目 + 口径实证表（extract_determination_wp_code 正则 `^[D-N]\d+-1$`，`审定表L{n}-1` → `L{n}-1` ✅ 全可解，无降级项；L 负债类 R1 低风险，L8 发生额中风险已实证）**：

      | 组件 | 科目 | 口径 amount_kind | 审定表 sheet 名 | 解出子码 | FormData 位置 | 反模式家族 |
      |---|---|---|---|---|---|---|
      | L1 短期借款 | 2001 | balance | 审定表L1-1 | L1-1 ✅ | `src/composables/`（**positional args (wpId,projectId,isReadonly) + isReadonly guard**） | A（Adjudication watcher `_editableSignature` 自动写） |
      | L2 应付利息 | 2231（`L2_GROSS_FALLBACK_STANDARD`） | balance | 审定表L2-1 | L2-1 ✅ | `components/workpaper/composables/` | B（tab handleSubmit→submitAdjudication） |
      | L3 长期借款 | 2501（`L3_GROSS_FALLBACK_STANDARD`） | balance | 审定表L3-1 | L3-1 ✅ | FormData 在 `components/workpaper/composables/`，**Adjudication 在 `src/composables/`** | B（tab handleSubmit→submitAdjudication） |
      | L4 应付债券 | 2502（`L4_GROSS_FALLBACK_STANDARD`） | balance | 审定表L4-1 | L4-1 ✅ | `components/workpaper/composables/` | B（**tab watch(totalAuditedAmount) 自动写**，已删 watcher） |
      | L5 长期应付款 | **2701 + 2702 双科目**（`L5_GROSS_FALLBACK_STANDARD`+未确认融资费用） | balance | 审定表L5-1 | L5-1 ✅ | `components/workpaper/composables/` | B（保存按钮 handleSave→saveAndWriteback 写 TB） |
      | L6 专项应付款 | 2711（`L6_GROSS_FALLBACK_STANDARD`，纠正旧 2601 租赁负债漂移） | balance | 审定表L6-1 | L6-1 ✅ | `components/workpaper/composables/` | A（Adjudication watcher 自动写） |
      | L7 其他非流动负债 | **BS-071 报表行**（`L7_REPORT_ROW_CODE`，L7 无独立科目码宁缺勿造） | balance | 审定表L7-1 | L7-1 ✅ | `components/workpaper/composables/` | A（Adjudication watcher 自动写） |
      | L8 财务费用 | 6603（`L8_GROSS_FALLBACK_STANDARD`） | **occurrence（发生额口径！）** | 审定表L8-1 | L8-1 ✅ | `components/workpaper/composables/` | A（Adjudication watcher 自动写；tab 另有 handleWritebackTB 无确认按钮） |

      sheet 名实证来源：后端 `event_handlers_cycle_linkage.py::_on_d_audit_determination_saved` 正则 `^[D-N]\d+-1$` + `misstatement_service.py` `^[D-N]\d*-1$`。**L 全 8 子码标准 `L{n}-1`，无不可解降级。**
    - **改造范式（复刻 M1/D2/D4-1，适配 L 三种结构）**：反模式 = `useLxFormData.writebackTB` 直调旧端点 `PUT /projects/{pid}/trial-balance/writeback` + 由 Adjudication watcher（A）/ tab watch（L4）/ 保存按钮（L5）**自动或无二次确认**触发（违反 Req 1/2）。三处改造：
      1. **`useLxFormData.writebackTB`**（8 个）：改走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，body=`{ sheet_name:'审定表Lx-1', writeback_rows:[{account_code, audited_amount, amount_kind}] }`（L8=occurrence，其余 balance；L5 单次 POST 含 2701+2702 两行原子发布）；**守卫由 `projectId` 改 `wpId`**；成功后 `eventBus.emit('substantive:adjudicated', ...)`（L1 原 emit 在 Adjudication，本次移进 FormData 以统一 gate 断言）。加 `DETERMINATION_SHEET_NAME` 常量。
      2. **`useLxAdjudication`**：Family A（L1/L6/L7/L8）`saveAndWriteback`→`saveAdjudication`（**移除 TB 写**），watcher 改「数据变化 → saveAdjudication + 仅 emit（不写 TB）」；Family B（L2/L3/L4）`submitAdjudication` 改「先 saveField 再 writebackTB」（不含确认）。全部 +`publishToTb`（`publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → 保存+writebackTB → 成功 emit + `ElMessage.success`；取消→无副作用）+`publishing` ref；import 加 `ref`/`ElMessage`/`ElMessageBox`（L7 另 import `L7_REPORT_ROW_CODE` 供 watcher emit accountCode）。
      3. **`LxTabAdjudication.vue`**：destructure 改名（saveAdjudication/publishToTb/publishing）；handleSave 改调 saveAdjudication（普通保存不写 TB）；加发布按钮（`type=warning` `:loading=publishing` `:disabled=isReadonly` `@click=handlePublishToTb`）+ `handlePublishToTb`（props.isReadonly 早退→publishToTb）。**L4 tab 删除 `watch(totalAuditedAmount)→submitAdjudication` 自动写 watcher + 去掉未用的 `watch` import**；**L8 tab 复用原 TB回写按钮位改 publishToTb + 删 `isWritingBack` ref**；L2/L3 tab 复用原 TB回写按钮改 publishToTb + 删 `isSubmitting` ref。
    - **改的文件（24 源 + 1 新测试 + 4 既有测试更新 = 29）**：
      - FormData（8）：`useL1FormData.ts`(src/composables) / `useL2~L8FormData.ts`(components/workpaper/composables) —— writebackTB 改走 publish-to-tb + DETERMINATION_SHEET_NAME 常量 + 守卫改 wpId + 收口注释
      - Adjudication（8）：`useL1Adjudication.ts`/`useL3Adjudication.ts`(src/composables) / `useL2/L4/L5/L6/L7/L8Adjudication.ts`(components/workpaper/composables) —— saveAndWriteback→saveAdjudication 去 TB 写（A）/ submitAdjudication 收敛（B）/ watcher 仅 emit / +publishToTb+publishing
      - 组件（8）：`L1~L8TabAdjudication.vue` —— destructure + handleSave/handleSubmit 改 saveAdjudication + handlePublishToTb + 发布按钮（L4 删自动写 watcher，L8 删 isWritingBack，L2/L3 删 isSubmitting）
      - 新增测试：`composables/__tests__/lAdjudicationPublishGate.spec.ts`（参数化 8 循环 × 5 用例 = 40，静态导入 useLx*，吸收 L1 positional args / L5 payload 双科目 / L3 Adjudication 跨路径差异）
      - 既有测试更新（4）：`l8-financial-expenses.integration.test.ts`（api mock +post；writebackTB 断言旧 PUT → publish-to-tb writeback_rows 科目6603 amount_kind=occurrence + 不再调旧端点；空 projectId→改空 wpId 守卫）、`l6-integration.test.ts`（同上科目 **2711**（纠正 2601 漂移）+ 空 wpId 守卫 + emit accountCode 2711）、`l7-integration.test.ts`（同上 account_code **BS-071**（纠正 2801 撞码）+ emit BS-071 + 空 wpId 守卫）、`l5-phase6-integration.test.ts`（api mock +post，双科目 2701+2702 两次 emit 断言保留）
    - **测试命令与 pass 数**：
      - 新 gate 测试：`rtk npx vitest run lAdjudicationPublishGate.spec.ts --reporter=dot` → **40 passed / 0 failed**（每 Lx：writebackTB 走 publish-to-tb 断言 sheet_name(Lx-1)/科目/audited/amount_kind(L8 occurrence 其余 balance) / 不再调 PUT trial-balance/writeback / 成功仍 emit substantive:adjudicated(wpCode Lx/科目) / publishToTb 取消→无 post 无 emit / publishToTb 确认→经 writebackTB 命中 publish-to-tb）
      - gate + 4 更新既有测试联跑：`rtk npx vitest run lAdjudicationPublishGate + l8-financial-expenses.integration + l6-integration + l7-integration + l5-phase6-integration --reporter=dot` → **111 passed / 0 failed**
      - ESLint（24 改动源 + 1 测试 + 4 更新测试 + 8 tab）：**0 errors**（warnings 全为未改代码既存 no-adhoc-wp-structure/no-amount-toFixed/no-amount-arithmetic，在 el-table-column/fmtAmount/crossValidation；新增 publishToTb/handlePublishToTb/发布按钮/gate 测试 0 warning）
      - getDiagnostics（24 源 + 8 tab）：**全 0**
    - **发现的偏差/降级**：
      - 🟢 **sheet 名全可解**：L 负债类 8 子码标准 `L{n}-1`，无不可解降级。
      - 🟢 **account drift 顺手纠正（触类旁通）**：l6-integration 旧断言 2601（租赁负债）→ 源实为 2711（专项应付款，`L6_GROSS_FALLBACK_STANDARD`）；l7-integration 旧断言 2801（预计负债撞码）→ 源实为 BS-071（报表行，`L7_REPORT_ROW_CODE`）。本次更新既有测试时**按真实源码 grep 实证纠正**为 2711/BS-071（memory 记载的 test-vs-source drift 一并修复）。
      - 🟡 **L7 account_code 是报表行非科目码**：L7 无独立科目（2801=K5 预计负债/2901=N1 递延所得税负债，report_config 撞码），沿用既有 `writebackTB` 用 `L7_REPORT_ROW_CODE='BS-071'` 作 account_code（改造前后一致，非本任务引入）。
      - 🟡 **L5 双科目单次原子发布**：原两次 `PUT`（2701+2702）→ 改为单次 `POST publish-to-tb` 含两 writeback_rows（原子性更好，符合 M0 端点 writeback_rows 多行契约）。
      - 🟢 **无 FormData 死代码重复**（与设计一致）：L 的 writebackTB 就在 FormData 被 Adjudication/tab 消费，8 个全活路径，无零消费 duplicate（区别于 H/I/K 循环）。
    - **⚠️ 预存无关失败（非本任务引入，git stash 实证）**：`l4-bonds-payable.integration.test.ts` 2 个 `adjudicationVsDetail`（cross-sheet 勾稽 diff）用例 fail —— 根因在 `useL4CrossSheet.ts` 解析 `L4-L4-2-rows` 的 `auditedAmount` 聚合漂移（detail 合计算成 0 → diff=总额），**与 TB 回写正交**。`git stash` 本任务全部改动后单跑该 spec 复现**完全相同** 2 fail，证明改动前即失败（且 `useL4CrossSheet.ts` 不在本任务改动清单，git status 实证）；属既存 cross-sheet test-vs-source drift，归 L4 独立修复，本任务不碰。
    - **端到端验证点**：前端单测覆盖「确认→publish-to-tb 落库路径 + 取消→无副作用 + 数据变化仅 emit 不写 TB」；后端 M0 集成测试（task 1）覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写（含 occurrence amount_kind 透传 / 多科目 rows）。真实项目 Playwright 全链路实测归 task 21*（待 start-dev.bat 环境）；真实 PG 无 L 循环审定数据的 UAT 归 task 20*（data-blocked）。

## M4：M 循环（活，10 个同构，可批量套模板）

- [x] 5. M 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep M1–M10 确认 `M{n}-1` 可解（R1 低风险）
  - 活路径（10 个同构 A 形态：`useM{n}Adjudication` `const {writebackTB}=formData` + invoke）：`useM1FormData`~`useM10FormData`（权益类单科目为主）。**高度同构，套一个模板批量改**。**无 FormData 死代码重复**
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名可解性表（extract_determination_wp_code 正则 `([D-N]\d+-1)\b`，`审定表M{n}-1` → `M{n}-1`；含 M10：`审定表M10-1` → `M10-1` ✅ 全可解，无降级项）**：

      | 组件 | 科目(单科目余额) | 审定表 sheet 名 | 解出子码 | 合计审定字段 | 备注 |
      |---|---|---|---|---|---|
      | M1 应付股利 | 2232（负债贷方） | 审定表M1-1 | M1-1 ✅ | endAudited | 模板 |
      | M2 实收资本/股本 | 4001 | 审定表M2-1 | M2-1 ✅ | endAudited | |
      | M3 库存股 | 4002（借方/权益备抵） | 审定表M3-1 | M3-1 ✅ | audited | |
      | M4 资本公积 | 4002 | 审定表M4-1 | M4-1 ✅ | audited | |
      | M5 盈余公积 | 4101 | 审定表M5-1 | M5-1 ✅ | audited | self-emit + **M5→M6 `m5:surplus-accrual` 联动保留** |
      | M6 未分配利润 | 4104 | 审定表M6-1 | M6-1 ✅ | audited | self-emit |
      | M7 专项储备 | 4201 | 审定表M7-1 | M7-1 ✅ | audited | 有小计 |
      | M8 一般风险准备 | 4104 | 审定表M8-1 | M8-1 ✅ | endAudited | 组件用 `adjudication.xxx` 对象访问 |
      | M9 其他综合收益 | 4103 | 审定表M9-1 | M9-1 ✅ | audited | 有双区块小计 |
      | M10 其他权益工具 | 4003 | 审定表M10-1 | M10-1 ✅（regex `\d+` 匹配 10） | audited | self-emit(三分组小计) |

      sheet 名实证来源：`src/composables/useMEquityCycleSheetGroups.ts` §3「审定表M*-1 pattern」+ 其 spec 固化 `审定表M2-1…审定表M10-1`；后端正则 `wp_account_package_resolver.py::_DETERMINATION_CODE_RE`。**M 权益类全 R1 低风险，10 个子码全可解，无不可解降级。**
    - **改造范式（复刻 D2/D4-1，适配 M 结构）**：M 循环反模式 = `useMxFormData.writebackTB` 直调旧端点 `PUT /projects/{pid}/trial-balance/writeback` + `useMxAdjudication` 的 `totalRow` watcher **数据变化即自动** `saveAndWriteback()`→writebackTB（违反 Req 1）。三处改造：
      1. **`useMxFormData.writebackTB`**（10 个）：改走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，body=`{ sheet_name:'审定表Mx-1', writeback_rows:[{account_code, audited_amount, amount_kind:'balance'}] }`；守卫由 `projectId` 改 `wpId`；**保留** 成功后 `eventBus.emit('substantive:adjudicated', {accountCode, auditedAmount, wpCode:'Mx', timestamp})`。加 `DETERMINATION_SHEET_NAME` 常量。
      2. **`useMxAdjudication`**（10 个）：`saveAndWriteback`→重命名 `saveAdjudication`（**只保存，移除 `await writebackTB`**）；watcher 改为「数据变化 → saveAdjudication + 仅 emit（不写 TB）」（Req 1）；新增 `publishToTb`（`publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → saveAdjudication → writebackTB → 成功 emit + `ElMessage.success`；取消→无副作用）+ `publishing` ref。**M5/M6/M10 self-emit 抽取为 `emitAdjudicated()`**（watcher + publish 后各调一次），**M5 保留 `m5:surplus-accrual` M5→M6 跨模块联动**（design §3/Property 4）。
      3. **`MxTabAdjudication.vue`**（10 个）：destructure `saveAdjudication/publishToTb/publishing`；`handleSave` 改调 `saveAdjudication`（普通保存不写 TB）；section-header 加「发布到试算表」按钮（`type=warning` `:loading=publishing`(M8 `adjudication.publishing.value`) `:disabled=isReadonly` `@click=handlePublishToTb`）+ `handlePublishToTb`（readonly 早退→publishToTb）。
    - **改的文件（30 源 + 1 新测试 + 2 既有测试更新 = 33）**：
      - FormData（10）：`useM1~M10FormData.ts`（writebackTB 改走 publish-to-tb + DETERMINATION_SHEET_NAME 常量 + 守卫改 wpId + 收口注释）
      - Adjudication（10）：`useM1~M10Adjudication.ts`（saveAndWriteback→saveAdjudication 去 TB 写 / watcher 仅 emit / +publishToTb+publishing / +ref+ElMessage+ElMessageBox import；M5/M6/M10 +emitAdjudicated）
      - 组件（10）：`M1~M10TabAdjudication.vue`（destructure + handleSave 改 saveAdjudication + handlePublishToTb + 发布按钮）
      - 新增测试：`composables/__tests__/mAdjudicationPublishGate.spec.ts`（参数化 10 循环 × 5 用例 = 50，静态导入 useMx*）
      - 既有测试更新：`m4-capital-reserve.integration.test.ts`（writebackTB 断言旧 PUT → 改断言 publish-to-tb writeback_rows 科目4002 + 不再调旧端点；头注释更新）、`m6-retained-earnings.integration.test.ts`（同上科目4104 + guard 测试 projectId空→改 wpId空早退）
    - **测试命令与 pass 数**：
      - 新 gate 测试：`rtk npx vitest run mAdjudicationPublishGate.spec.ts --reporter=dot` → **50 passed / 0 failed**（每 Mx：writebackTB 走 publish-to-tb 断言 sheet_name(Mx-1)/科目/audited/amount_kind=balance / 不再调 PUT trial-balance/writeback / 成功仍 emit substantive:adjudicated(wpCode Mx/科目) / publishToTb 取消→无 post 无 emit / publishToTb 确认→经 writebackTB 命中 publish-to-tb）
      - 全 M 循环回归（43 spec）：`rtk npx vitest run src/components/workpaper/__tests__/m{1..10} + mAdjudicationPublishGate` → **967 passed / 2 todo / 0 failed**
      - ESLint（30 改动源 + 3 测试）：**0 errors**（89 warnings 全为未改代码既存：el-table-column no-bare-amount-cell / autosize textarea no-adhoc-wp-structure / fmtAmount·fmtPercent 的 no-amount-toFixed / cross-validation 的 no-amount-arithmetic；新增代码 publishToTb/emitAdjudicated/watcher/按钮 0 warning）
      - getDiagnostics（30 源）：**全 0**
    - **发现的偏差/降级**：
      - 🟢 **sheet 名全可解**：M 权益类 10 子码标准 `M{n}-1`（含 M10 经 regex `\d+` 正确匹配），无不可解降级。
      - 🟢 **无 FormData 死代码重复**（与设计一致）：M 的 writebackTB 就在 FormData 被 Adjudication 消费，10 个全活路径，无零消费 duplicate（区别于 H/I/K 循环）。
      - 🟡 **M4/M6 既有测试断言旧反模式**：`m4/m6 integration` 各 1 个 `writebackTB → PUT trial-balance/writeback` 断言正是本 spec 消除的反模式（Property 9 / D2 先例：测试断言旧行为须随迁移更新）→ 已改为断言 publish-to-tb writeback_rows；M6 guard 测试语义从 projectId 守卫改为 wpId 守卫。非降级，属测试跟随源迁移。
      - 🟡 **UX 变更（合理，符合 Req 2）**：M 循环原靠 watcher **自动**写 TB（无用户确认，正是本 spec 消除的反模式）→ 改造后各 MxTabAdjudication 新增「发布到试算表」按钮承载显式二次确认动作；数据变化只 emit 附注刷新不写 TB（Req 1）。
      - 🟢 **双 emit 可接受**：M5/M6/M10 发布路径 writebackTB(基本 payload) + emitAdjudicated(富 payload) 各 emit 一次 substantive:adjudicated，下游附注刷新幂等，无害。
    - **端到端验证点**：前端单测覆盖「确认→publish-to-tb 落库路径」+「数据变化只 emit 不写 TB」+「取消无副作用」+「不再调旧端点」；后端 M0 集成测试（task1）覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写。真实项目 Playwright 全链路 + 真实 PG UAT 归 task 20*/21*（data-blocked / 待 start-dev.bat 环境）。
    - **未触碰**：`ieOrphanBaseline.spec.ts`（他 spec）；`n1_deferred_tax_assets_service.py` DEPRECATED 旁路（正交）；S 类独立回写服务（正交，非目标）；其他循环 tasks 3-15 的活路径。

## M5：N 循环（活，5 个；N1 watcher 须改显式）

- [x] 6. N 循环审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep N1–N5 确认 `N{n}-1` 可解（N5 6801 occurrence 存疑须确认）
  - 活路径：`useN1FormData`~`useN5FormData`（5 个，税费）；**N1 特例**——`useN1Adjudication` 有 debounce watcher 自动写 TB（违反 Req 1），改造须把自动 watcher 写改为显式确认（watcher 只保留 emit，不写 TB）；N5(6801) 发生额；N4 有 V1+V2 两 adjudication；确认 `n1_deferred_tax_assets_service.py` DEPRECATED 裸 SQL 旁路不复活。**无 FormData 死代码重复**
  - 前端单测（断言 N1 数据变化只 emit 不写 TB）+ 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名可解性 + 科目 + 口径实证表（extract_determination_wp_code 正则 `([D-N]\d+-1)\b`，handler `^[D-N]\d+-1$`；`审定表N{n}-1` → `N{n}-1` ✅ 全可解，无降级项。N4/N5 发生额中风险已实证）**：

      | 组件 | 科目 | 口径 amount_kind | 审定表 sheet 名 | 解出子码 | FormData 位置 | 反模式家族 |
      |---|---|---|---|---|---|---|
      | N1 递延所得税资产 | 1811 | **balance（期末余额）** | 审定表N1-1 | N1-1 ✅ | `components/workpaper/composables/` | A（Adjudication debounce 2s watcher 自动写，**已删**） |
      | N2 应交税费 | 2221 | balance | 审定表N2-1 | N2-1 ✅ | 同上 | B（tab handleWritebackTB→saveAndSync 无确认） |
      | N3 递延所得税负债 | 2901 | balance | 审定表N3-1 | N3-1 ✅ | 同上 | B（tab handleWritebackTB→saveAndSync 无确认，+ N3→N5 联动） |
      | N4 税金及附加 | 6403 | **occurrence（发生额！）** | 审定表N4-1 | N4-1 ✅ | 同上 | B（tab handleWritebackTB→adjudication.writeback 无确认；旧参 is_occurrence+amount_type:period） |
      | N5 所得税费用 | 6801 | **occurrence（发生额！）** | 审定表N5-1 | N5-1 ✅ | 同上 | B（tab handleWritebackTB 直调 formData.writebackTB 无确认；旧参 amount_type:period） |

      sheet 名实证来源：后端 `wp_account_package_resolver.py::_DETERMINATION_CODE_RE = re.compile(r"([D-N]\d+-1)\b")` + handler `event_handlers_cycle_linkage.py::_on_d_audit_determination_saved` 正则 `^[D-N]\d+-1$`。sheet_name 常量统一用 `审定表N{n}-1`（复刻 L/M 范式），全 5 子码标准 `N{n}-1` 可解，无不可解降级。
    - **N4 V1/V2 双 adjudication 处置（grep 实证）**：
      - **V1 `useN4Adjudication` = LIVE**（`N4TabAdjudication.vue:310` import + 构造，是真实渲染宿主）→ **完整改造**（`writeback()` 去自动写 TB 收敛为经 publishToTb；+ `publishToTb`(二次确认)+`publishing`）。
      - **V2 `useN4AdjudicationV2` = 零消费死代码**（全仓 0 个 `.vue` 消费方，0 个测试引用，仅自身文件 + 一处 test-helper 文档注释提及）→ 按 Task 17 死代码判法**不新增 publishToTb**；但其 `writeback()` 委托注入的 `writebackTB`，而 `useN4FormData.writebackTB` 已改走 publish-to-tb，故 V2 即便被调用也已合规（不再直调旧 PUT）。已加收口注释登记；整体死代码清理归 task 17。**未误删活的 V1，未误接死的 V2。**
    - **N1 debounce watcher 处理（Req 1 特例，R7）**：`useN1Adjudication` 原有 `watch(() => totals.value.endAudited)` debounce 2s → `formData.writebackTB(newVal)`（数据一变就静默写 TB，违反 Req 1）→ **已删除该自动回写 watcher** + 连带删除随之失效的 `_suppressWriteback` / `_writebackTimer` / `nextTick` import（死状态）。合计同步供 crossSheet/下游 N5 读取的职责由 `_syncTotals()`（`watch(rows,...)`，与 TB 回写无关）承载，保留不动。TB 回写收敛为 `publishToTb`（二次确认门）。**gate 测试断言：构造 adjudication + updateRow 数据变化后，20ms 内无任何 POST publish-to-tb / PUT trial-balance/writeback（自动写已消除）。**
    - **N1→N5 联动保留（Req 8，design §3）**：`useN1FormData.writebackTB` 改走 publish-to-tb 后**保留**成功后的两条 emit：`substantive:adjudicated`（附注刷新）+ `deferred-tax:asset-updated`（供 N5 递延所得税费用核对表接收 N1→N5 联动）。**gate 测试 + n1-integration 断言：发布后 deferred-tax:asset-updated 仍 emit（wpCode=N1/accountCode=1811）。** N3→N5 联动（`publishDeferredTaxLiabilityUpdated`）：N3 tab 改为 publishToTb 成功后（返回 boolean）才触发该联动 + 自动快照，取消则不触发。
    - **改造范式（复刻 M/L/D2）**：反模式 = `useNxFormData.writebackTB` 直调旧端点 `PUT /projects/{pid}/trial-balance/writeback`（N4/N5 带旧参 is_occurrence/amount_type:period）+ 由 Adjudication watcher（N1）/ tab 保存按钮（N2~N5，无二次确认）触发。三处改造：
      1. **`useNxFormData.writebackTB`**（5 个）：改走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，body=`{ sheet_name:'审定表Nx-1', writeback_rows:[{account_code, audited_amount, amount_kind}] }`（N4/N5=occurrence，N1/N2/N3=balance）；**守卫由 `projectId` 改 `wpId`**；N4/N5 移除旧 `is_occurrence`/`amount_type:'period'` 参数（改用 `amount_kind='occurrence'`）；N2 移除 `year` 参数；成功后保留原 emit（N1 双 emit / N4 双 emit expense:taxes-surcharges-updated / N2/N3/N5 单 emit）。加 `DETERMINATION_SHEET_NAME` 常量。
      2. **`useNxAdjudication`**（N1/N2/N3/N4 有 composable）：N1 删自动写 watcher；N2 `saveAndSync`→`saveAdjudication`(去 TB 写)；N3 `saveAndSync`→`saveAdjudication`(去 TB 写)+删 `triggerWriteback`；N4 V1 `writeback()` 收敛为仅经 publishToTb 调用。全部 +`publishToTb`（`publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → 保存/写回 → 成功 emit + `ElMessage.success`；取消→无副作用）+`publishing` ref（N3/N4 publishToTb 返 boolean 供 tab 决定是否触发跨模块联动）。N5 无 adjudication composable → 显式确认门直接落在 `N5TabAdjudication.vue` handleWritebackTB。
      3. **`NxTabAdjudication.vue`**（5 个）：handleWritebackTB 改调 publishToTb（N5 内联 confirm）；发布按钮 `type=warning` `:loading=publishing`(N5 用 writebackLoading) `:disabled=isReadonly`，文案改「发布到试算表」；删除各 tab 的 `writebackLoading`（N1~N4，N5 保留复用）。
    - **改的文件（15 源 + 1 新测试 + 2 既有测试更新 = 18）**：
      - FormData（5）：`useN1~N5FormData.ts`（writebackTB 改走 publish-to-tb + DETERMINATION_SHEET_NAME 常量 + 守卫改 wpId + N4/N5 去旧参 + N2 去 year 参 + 收口注释）
      - Adjudication（4 + 1 死代码注释）：`useN1Adjudication.ts`（删自动写 watcher + 死状态 + 加 publishToTb+publishing）、`useN2Adjudication.ts`（saveAndSync→saveAdjudication + publishToTb）、`useN3Adjudication.ts`（saveAndSync→saveAdjudication 删 triggerWriteback + publishToTb 返 boolean）、`useN4Adjudication.ts`（V1 writeback 收敛 + publishToTb 返 boolean）、`useN4AdjudicationV2.ts`（死代码收口注释，未接线）
      - 组件（5）：`N1~N5TabAdjudication.vue`（handleWritebackTB→publishToTb + 发布按钮 warning + N3/N4 联动仅发布成功后触发 + N5 内联 confirm）
      - 新增测试：`composables/__tests__/nAdjudicationPublishGate.spec.ts`（参数化 N1~N4 × 5 用例 + N1 特例(数据变化不写 TB / N1→N5 联动) + N4 参数迁移(无 is_occurrence/amount_type) + N5 routing 3 用例 = **26 用例**）
      - 既有测试更新（2）：`n1-integration.spec.ts`（原 mock-only writebackTB 断言旧 PUT → 改为调真实 useN1FormData.writebackTB + 断言 publish-to-tb writeback_rows 科目1811 amount_kind=balance + 不再调旧端点 + N1→N5 联动 deferred-tax:asset-updated 保留；加 mockPost）、`n3-integration.spec.ts`（同上科目2901 amount_kind=balance；加 mockPost）
    - **测试命令与 pass 数**：
      - 新 gate 测试：`rtk npx vitest run nAdjudicationPublishGate.spec.ts --reporter=dot` → **26 passed / 0 failed**（每 N1~N4：writebackTB 走 publish-to-tb 断言 sheet_name(Nx-1)/科目/audited/amount_kind(N4 occurrence 其余 balance) / 无 PUT/POST 命中旧 trial-balance/writeback / 成功仍 emit substantive:adjudicated(wpCode Nx/科目) / publishToTb 取消→无 post 无 emit / publishToTb 确认→经 writebackTB 命中 publish-to-tb；N1 数据变化 20ms 内不写 TB；N1 发布仍 emit deferred-tax:asset-updated；N4 body 无 is_occurrence/amount_type 用 amount_kind=occurrence；N5 routing 3 用例）
      - N 循环全量回归（13 spec）：`rtk npx vitest run n1-integration + n1-contract + n1-pbt + n1LossCheckModel + n1UnrecognizedLossPayload + n2-contract + n3-integration + n3-contract + n3-pbt + n5-contract + n5-pbt + nCycleSheetRouting + nCycleTaxConsistency + nAdjudicationPublishGate` → **236 passed / 0 failed**
      - ESLint（15 源 + 3 测试 = 18 文件）：**0 errors**（68 warnings 全为未改代码既存 gt-audit/no-amount-arithmetic·no-amount-toFixed·no-adhoc-wp-structure·no-bare-amount-cell，在 formula 计算/fmtAmount/el-table-column；新增 publishToTb/writebackTB/gate 测试 0 warning）
      - getDiagnostics（12 核心文件）：**全 0**
    - **发现的偏差/降级**：
      - 🟢 **sheet 名全可解**：N 税费类 5 子码标准 `N{n}-1`（含 N4/N5 发生额审定表），无不可解降级。
      - 🟢 **无 FormData 死代码重复**（与设计一致）：N 的 writebackTB 就在 FormData 被 Adjudication/tab 消费，5 个全活路径，无零消费 duplicate（区别于 H/I/K 循环）。唯一死代码 = N4 V2 adjudication（整 composable 零消费，归 task 17 判法登记，未接线未误删）。
      - 🟡 **N4 dim2 断言口径调整（合理）**：N4 `writebackTB` 除 publish-to-tb 外仍 `PUT /checklist-responses` 保存审定合计（`N4-1-adjudicated-amount`，正常持久化，非 TB 回写）→ gate 测试 dim2 断言口径改为「无任何 PUT/POST 命中旧 `trial-balance/writeback` 字面量」而非「PUT 从未调用」。非降级，属 N4 特有的合法保存副作用。
      - 🟡 **N4/N5 旧参迁移（合理）**：旧 `is_occurrence:true`/`amount_type:'period'` 参数是旧端点 `PUT trial-balance/writeback` 的口径标注；publish-to-tb 端点用 `writeback_rows[].amount_kind='occurrence'` 承载同一语义（M0/task1 契约），故删除旧参、改用 amount_kind。gate 测试专门断言 N4 body 不再含旧参。
      - 🟡 **UX 变更（合理，符合 Req 2）**：N 循环原靠 watcher 自动写（N1）或无二次确认按钮（N2~N5）写 TB（正是本 spec 消除的反模式）→ 改造后各 NxTabAdjudication 的按钮承载显式二次确认动作（文案「发布到试算表」）；N1 数据变化只 emit 附注刷新不写 TB（Req 1）。
      - 🟢 **既有测试跟随源迁移（非降级，D2/M 先例）**：n1-integration/n3-integration 原「writebackTB payload 正确性」是 mock-only 测试（直调 mockPut 断言旧端点，不跑真实 composable，改动前即不会破）；本次改为调真实 composable + 断言 publish-to-tb 新路径，使其真正验证迁移（test-follows-source）。
      - 🟢 **`n1_deferred_tax_assets_service.py` DEPRECATED 裸 SQL 旁路未复活**：本任务仅改前端，未触碰该后端 service（正交，确认不复活）。
    - **端到端验证点**：前端单测覆盖「确认→publish-to-tb 落库路径 + 取消→无副作用 + N1 数据变化仅 emit 不写 TB + N1→N5/N3→N5 联动保留 + N4/N5 发生额 amount_kind 透传」；后端 M0 集成测试（task 1）覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写（含 occurrence amount_kind）。真实项目 Playwright 全链路实测归 task 21*（待 start-dev.bat 环境）；真实 PG 无 N 循环审定数据的 UAT 归 task 20*（data-blocked）。
    - **未触碰**：`ieOrphanBaseline.spec.ts`（他 spec）；`n1_deferred_tax_assets_service.py` DEPRECATED 旁路（正交）；S 类独立回写服务（正交，非目标）；其他循环 tasks 3/7-15 的活路径。

## M6：K 循环（活 11 个，多科目 + 发生额主战场；受 task 16 决策约束）

- [x] 7. K 循环单科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep K2/K3/K4/K8/K9/K10/K11 确认子码可解（K8/K9/K11 发生额高风险须实证）
  - 活路径：`K2TabAdjudication`(inline btn，`tbAccountCode`)、K3(2241)/K4(2245)(btn→FormData.writebackTB)、K8(6601)/K9(6602)/K11(6701)(adjudication inline，发生额 `amount_kind=occurrence`)、K10(btn+A)
  - **依赖 task 16 决策**：K5(2701)/K7(2401) 若决策为(a)补真回写则纳入本任务；若(b)则不纳入（K5/K7 死代码归 task 17，成功提示由 task 16 处置）
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名可解性 + 科目 + 口径实证表（`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b`，实证来源 `backend/data/ledger_adapters/wp_render_schema/generated/K*.yaml` + `K7-1.yaml`/`K8-1.yaml`/`K9-1.yaml`；全可解，无降级）**：

      | 组件 | 科目 | 口径 amount_kind | 审定表 sheet 名（render schema label） | 解出子码 | 活路径入口 | 二次确认位置 |
      |---|---|---|---|---|---|---|
      | K2 其他流动资产 | 动态 `tbAccountCode`（默认 1901，取 `tbSourceCodes.gross_standard[0]`） | balance | `审定表K2-1` | K2-1 ✅ | K2TabAdjudication inline `publishToTb`（原 handleWritebackTB http.put） | 组件内 |
      | K3 其他应付款 | 2241 | balance | `审定表K3-1` | K3-1 ✅ | K3TabAdjudication.handleWritebackTB → `useK3FormData.writebackTB` | Tab handleWritebackTB |
      | K4 其他流动负债 | 动态 `k4Code`（`k4QueryCodes(tbSourceCodes)[0]`，宁缺勿造） | balance | `审定表K4-1` | K4-1 ✅ | K4TabAdjudication.handleWritebackTB(k4Code守卫) → `useK4FormData.writebackTB(amt, k4Code)` | Tab handleWritebackTB |
      | K8 销售费用 | 6601 | **occurrence（损益发生额！）** | `审定表K8-1` | K8-1 ✅ | K8TabAdjudication.handleTbWriteback → `useK8Adjudication.writeback()` | writeback() 内置 |
      | K9 管理费用 | 6602 | **occurrence** | `审定表K9-1` | K9-1 ✅ | K9TabAdjudication.handleTbWriteback → `useK9Adjudication.writeback()` | writeback() 内置 |
      | K10 其他收益 | 6117 | **occurrence** | `审定表K10-1` | K10-1 ✅ | K10TabAdjudication.handleWritebackTB(已有confirm) → adjudication.writeback() → `useK10FormData.writebackTB` | Tab handleWritebackTB |
      | K11 资产减值损失 | 6701 | **occurrence** | `审定表K11-1` | K11-1 ✅ | K11TabAdjudication.handleTbWriteback → `useK11Adjudication.writeback()` | writeback() 内置 |
      | **K5 预计负债（补真回写）** | 动态 `k5AccountCode(tbSourceCodes)`（兜底 **2801**，禁硬编码 2701 防污染 L5 长期应付款） | balance | `审定表K5-1` | K5-1 ✅ | K5TabAdjudication inline `publishToTb`（原假回写 handleTbWriteback） | 组件内 |
      | **K7 递延收益（补真回写）** | 2401 | balance | `审定表K7-1` | K7-1 ✅ | K7TabAdjudication inline `publishToTb`（原假回写只 emit save） | 组件内 |

    - **🔴 K5/K7 补真回写证据（Task 16 决策a）**：
      - **K5**：原 `handleTbWriteback` 弹「已回写TB(2701)」成功提示但只 `emit('save')`+`publishAdjudicated()`（假回写从不写 TB）。改造后 = `publishToTb`（二次确认 → `POST publish-to-tb` writeback_rows 科目 `k5AccountCode(props.tbSourceCodes)` 动态取值 amount_kind=balance → 成功后 `publishAdjudicated()`）。**去掉误导性「已回写TB(2701)」提示**，改真回写后提示「已发布到试算表」（取端点 resp.message）。button 文案 `回写试算表(2701)`→`发布到试算表`。同时 `useK5FormData.writebackTB` 也改走 publish-to-tb（消除死代码里的 `trial-balance/writeback` 字面量，动态科目）。**kCycleAccountScope.spec 守卫**：K5 tab/host 禁 `'2701'` 引号字面量——用 k5AccountCode 动态，template 里 `(2701)` 纯文本非引号不触发，已保守未新增 2701 字面量。
      - **K7**：原 `handleTbWriteback` 只 `emit('save', 'K7-1-audited-total')`（假回写）。改造后 = `publishToTb`（二次确认 → `POST publish-to-tb` writeback_rows 科目 2401 amount_kind=balance）。button 文案 `回写试算表(2401)`→`发布到试算表(2401)`。
    - **改造范式（复刻 D2/F5）**：`ElMessageBox.confirm` 中文二次确认（取消→无副作用/无 post/无 emit）→ `const { api } = await import('@/services/apiProxy')` → `api.post('/api/workpapers/{wpId}/audit-determination/publish-to-tb', { sheet_name, writeback_rows:[{account_code, audited_amount, amount_kind}] })` → 保留 `substantive:adjudicated` emit（K2/K5/K7 组件内 emit 或 publishAdjudicated；K3/K4/K8/K9/K10/K11 在 FormData/Adjudication 内 emit）。readonly/publishing 早退。
    - **改的文件（12 个源文件）**：`k2/core/K2TabAdjudication.vue`（inline handleWritebackTB→publishToTb）、`k5/core/K5TabAdjudication.vue`（假回写→publishToTb 动态科目去误导提示）、`k7/core/K7TabAdjudication.vue`（假回写→publishToTb 2401）、`k3/core/K3TabAdjudication.vue`（+confirm+ElMessageBox import+按钮warning）、`k4/core/K4TabAdjudication.vue`（+confirm+传 k4Code+按钮warning）、`k8/core/K8TabAdjudication.vue`+`k9/`+`k11/`（按钮 warning）、`k10/core/K10TabAdjudication.vue`（confirm 措辞改 publish+按钮warning）、`composables/useK3FormData.ts`/`useK4FormData.ts`（writebackTB→publish-to-tb；K4 加 accountCode 入参默认 2245）、`useK5FormData.ts`（writebackTB→publish-to-tb 动态科目）、`useK10FormData.ts`（writebackTB→publish-to-tb 6117 occurrence）、`useK8Adjudication.ts`/`useK9Adjudication.ts`/`useK11Adjudication.ts`（writeback()→publish-to-tb occurrence + 内置 ElMessageBox.confirm + readonly 早退）。
    - **测试**：新增 `composables/__tests__/kAdjudicationPublishGate.spec.ts`（参数化 Group A: K1/K3/K4/K5/K10 writebackTB + Group B: K8/K9/K11 writeback 内置确认，**31 passed / 0 failed**：确认→POST publish-to-tb(sheet_name 匹配 K{n}-1 / writeback_rows 科目 / amount_kind occurrence|balance) / 不再调 trial-balance/writeback / Group B 取消确认→无 POST无 emit + readonly→无 POST / 发布后仍 emit substantive:adjudicated）。修复 drift：`k5Provisions.integration.spec.ts` 4 用例(2701→2801 + PUT→POST publish-to-tb) **27 passed**、`k3Integration.spec.ts`(4)+`k3OtherPayables.integration.spec.ts`(1)+`k4Integration.spec.ts`(5)+`k5PersistenceMigration.spec.ts`(1 loadTbData drift 2701→2801) 加 mockPost 断言 publish-to-tb **71 passed**。ESLint 0 error（既存 warn 无新增）；getDiagnostics 0。
    - **偏差/降级**：无 sheet 名不可解降级（render schema 实证全 K{n}-1）。K4 `writebackTB` 加可选 `accountCode` 入参（默认 `ACCOUNT_CODE_2245`）以透传 Tab 动态 `k4Code`，避免 FormData 硬编码与 Tab 动态解析不一致。K5 顺带把死代码 `useK5FormData.writebackTB` 也迁到 publish-to-tb（消除该文件内 `trial-balance/writeback` 字面量，利于 task 18 CI 归零）。

- [x] 8. K1/K6 多科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep K1/K6 确认 `K1-1`/`K6-1` 可解
  - 活路径：`useK1FormData`（btn，1221+坏账准备双科目）、`GtK6HeldForSale`（inline btn，资产+负债，科目取自 `tb_source_codes` **动态解析后透传** `writeback_rows`，端点不硬编码科目）
  - 前端单测（断言双科目均在单次 post 的 writeback_rows）+ 端到端验证点（双科目均落库、幂等不双写）
  - _需求: 5, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名实证**：K1 render schema `审定表K1-1`（generated/K1.yaml 实证）→ K1-1 ✅；K6 `审定表 K6-1`（generated/K6.yaml，含空格仍解出 K6-1）✅。均可走 publish-to-tb，无降级。
    - **K1（1221 + 坏账准备 1231 双科目）**：`useK1FormData.writebackTB(auditedReceivable, auditedBadDebt)` 原两次 `PUT trial-balance/writeback`（1221、1231）→ 改**单次** `POST publish-to-tb`，`writeback_rows: [{1221, balance}, {1231, balance}]` 原子发布，保留 `substantive:adjudicated`(1221/K1) emit。`K1TabAdjudication.handleWritebackTB` 加中文二次确认 + 按钮 `确认审定 → 回写TB`→`发布到试算表`（warning）。守卫改 `wpId`。
    - **K6（资产+负债动态科目）**：`GtK6HeldForSale.writebackTB(assetAudited, liabilityAudited)` 原 `Promise.all` 两次 PUT（`k6AssetCode`/`k6LiabCode` 动态） → 改**单次** `POST publish-to-tb`，`writeback_rows` 按 `k6AccountScope` 解析的动态科目**前端算好透传**（端点不硬编码；科目为空则跳过该行，宁缺勿造），保留资产/负债两条 `substantive:adjudicated` emit。`K6TabAdjudication.handleWritebackTB` 加中文二次确认 + 按钮 warning + `审定数回写TB`→`发布到试算表`。GtK6 用 `wpIdRef` + 动态 import api.post。
    - **改的文件**：`composables/useK1FormData.ts`（writebackTB 双科目单次 publish-to-tb）、`k1/core/K1TabAdjudication.vue`（+confirm+ElMessageBox import+按钮warning+wpId守卫）、`GtK6HeldForSale.vue`（writebackTB 动态双科目单次 publish-to-tb）、`k6/core/K6TabAdjudication.vue`（+confirm+ElMessageBox import+按钮warning）。
    - **测试**：`kAdjudicationPublishGate.spec.ts` 含 **K1 双科目在单次 writeback_rows 原子发布** 专项断言（1221+1231 同在一次 POST，byCode 校验金额）；修复 `k1Integration.test.ts` Part A 5 用例 + 端点路径测试（改断言单次 POST publish-to-tb writeback_rows[1221,1231]，加 mockPost）**57 passed（含 k11）**。K6 走组件 inline，其活路径断言由 gate 测试的 Group A/publish-to-tb 契约 + K6 端到端归 task 20/21（真实数据/Playwright）。ESLint 0 error（GtK6 既存 no-direct-audit-fetch 2 warn 在未改的 _loadTbData）；getDiagnostics 0。
    - **偏差/降级**：无。双科目均在单次 `writeback_rows` 原子发布（Req 5），幂等由端点/handler `tb_publish_ack`（M0 已建）承载。K6 动态科目由前端 `k6AccountScope` 解析后透传，端点不硬编码（符合 R2 缓解）。

- [x] 9. K12/K13 发生额审定表改走显式发布端点
  - **第一步实证 sheet 名（R1 高风险）**：grep K12/K13 render schema/SheetLabels 实证「6301/6711 类损益审定表」sheet 名能否解出 `[D-N]{n}-1`；不可解则任务内规整命名或按 R1 降级登记
  - 活路径：`K12TabAdjudication`(inline btn，6301 发生额 `amount_kind=occurrence`)、`K13TabAdjudication`(inline btn，6711)。（`useK12/K13FormData.writebackTB` 是死代码 duplicate，归 task 17）
  - 前端单测 + 端到端验证点
  - _需求: 6, 2, 8_
  - **✅ 完成证据（2026）**：
    - **🔴 sheet 名实证（R1 高风险损益类发生额审定表，实证解除风险）**：K12 render schema `generated/K12.yaml` sheet label `审定表K12-1`（A2 营业外收入审定表）→ `([D-N]\d+-1)\b` 解出 **K12-1 ✅**；K13 `generated/K13.yaml` `审定表K13-1`（A2 营业外支出审定表）→ **K13-1 ✅**。**均可解，无需规整命名/无 R1 降级**。
    - **K12（6301 发生额）**：`K12TabAdjudication.handleWritebackTBInternal` 原 `http.put trial-balance/writeback`（6301）→ 改 `POST publish-to-tb` writeback_rows `[{6301, occurrence}]` + 保留 `substantive:adjudicated`(6301/K12, type occurrence_amount) emit。`handleWritebackTB`（原无 confirm）**加中文二次确认**。删除未用的 `http` import。按钮 `回写审定数 → TB(6301发生额)`→`发布到试算表(6301发生额)`（warning）。
    - **K13（6711 发生额）**：`K13TabAdjudication.handleWritebackTBInternal` 原 `http.put`（6711）→ 改 `POST publish-to-tb` writeback_rows `[{6711, occurrence}]` + 保留 emit。`handleWritebackTB` 加中文二次确认。删除未用的 `http` import。按钮 `回写审定数 → TB(6711发生额)`→`发布到试算表(6711发生额)`（warning）。
    - **kCycleAccountScope 守卫**：K12 tab 禁 `'6701'`（用 6301 ✅）、K13 tab 禁 `'6702'`（用 6711 ✅），均合规。
    - **改的文件**：`k12/core/K12TabAdjudication.vue`（handleWritebackTBInternal→publish-to-tb occurrence + handleWritebackTB 加 confirm + 删 http import + 按钮warning）、`k13/core/K13TabAdjudication.vue`（同 K12，6711）。
    - **测试**：`kAdjudicationPublishGate.spec.ts` 的 Group A/B occurrence 契约覆盖发生额 amount_kind=occurrence 断言；`k12Integration.test.ts`（Part C/D/E 附注订阅/regex/事件流，Part A/B 死代码已在 task17 批C 移除）全绿；`k12AdjustmentEventBus.test.ts` 全绿。K12/K13 组件 inline handler 的端到端落库归 task 20/21。ESLint 0 error（K12/K13 既存 no-adhoc-wp-structure/no-amount-toFixed warn 在未改表渲染代码）；getDiagnostics 0。
    - **偏差/降级**：无。R1 高风险 sheet 名经 render schema 实证全部可解，未触发降级路径。amount_kind 一律 occurrence（损益发生额，M0 端点已支持透传）。

## M7：H 循环（活 9 个，单/双科目 + 形态多样）

- [x] 10. H 循环单科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep H1/H2/H3/H4/H5/H6/H7/H10 确认子码可解（H7 1621 公允 / H10 处置损益 occurrence 高风险须实证）
  - 活路径：H1(inline callback，1601/1602/1603 多科目)、H2(inline，1604)、H3(inline watcher 1.5s debounce，grossCode/accumDepCode，**防跨循环污染**：本项目无该科目则不写)、H4(inline，1605 LIKE 前缀)、H5(A，1631/1632 多科目)、H6(inline callback)、H7(inline api.put，cost/fair 两组件 1621)、H10(A+B，H10_ACCOUNT_CODE 发生额)
  - 前端单测（H3 断言不污染他循环）+ 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名可解性 + 科目 + 口径实证表**（sheet 名来源：`backend/data/ledger_adapters/wp_render_schema/generated/H{n}.yaml` 均含 `label: H{n}-1` 子码；`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b` / handler `^[D-N]\d+-1$`；我传 `sheet_name='审定表H{n}-1'` 全可解，无 R1 降级）：

      | wp | 组件 / 载体 | 我传的 sheet_name | 解出子码 | 科目 | 口径 amount_kind | 形态实证来源 |
      |---|---|---|---|---|---|---|
      | H1 | `useH1Adjudication.publishToTb`（原 `.vue` onWritebackTB 回调 for 循环 http.put） | `审定表H1-1` | H1-1 ✅ | 1601/1602/1603（**多科目**） | balance | H1TabAdjudication.vue:onWritebackTB |
      | H2 | `useH2Adjudication.publishToTb`（原 onWritebackTB 回调 http.put 1604） | `审定表H2-1` | H2-1 ✅ | 1604 | balance | H2TabAdjudication.vue:onWritebackTB |
      | H3 | `H3TabAdjudicationCost.vue publishToTb`（原 1.5s debounce watcher 自动 http.put） | `审定表H3-1` | H3-1 ✅ | grossCode(兜底1521) + accumDepCode(1525，**动态**) | balance | H3TabAdjudicationCost.vue:writebackTrialBalance |
      | H4 | `useH4Adjudication.publishToTb`（原 onWritebackTB 回调 http.put 1605） | `审定表H4-1` | H4-1 ✅ | 1605（端点 LIKE 前缀匹配子科目） | balance | H4TabAdjudication.vue:onWritebackTB |
      | H5 | `useH5Adjudication.publishToTb`（原 onWritebackTB → formData.writebackTB 两次 api.put） | `审定表H5-1` | H5-1 ✅ | 1631/1632（**多科目**） | balance | H5TabAdjudication.vue:onWritebackTB |
      | H6 | `useH6Adjudication.publishToTb`（原 onWritebackTB **只 emit 不写=假回写**） | `审定表H6-1` | H6-1 ✅ | 1606 固定资产清理（isTransitAccount） | balance | H6TabAdjudication.vue:onWritebackTB |
      | H7 Cost | `H7TabAdjudicationCost.vue handlePublish`（原自包含 api.put 1621） | `审定表H7-1` | H7-1 ✅ | 1621（成本模式净值） | **balance**（🔴运行时实证：1621 生产性生物资产是**余额类资产**非损益，成本模式审定的是期末净值余额） | H7TabAdjudicationCost.vue:handlePublish |
      | H7 Fair | `H7TabAdjudicationFair.vue handlePublish`（原自包含 api.put 1621） | `审定表H7-1` | H7-1 ✅ | 1621（公允价值） | **balance**（🔴运行时实证：公允价值模式审定的是**期末公允价值余额**，非发生额；task「occurrence 存疑」实证结论=balance） | H7TabAdjudicationFair.vue:handlePublish |
      | H10 | `useH10Adjudication.publishToTb`（原 publishAdjudicated→writebackFn 在 mount/debounce/跨wp **三处自动写**） | `审定表H10-1` | H10-1 ✅ | H10_ACCOUNT_CODE=**6115** 资产处置损益 | **occurrence**（🔴运行时实证：6115 损益类，`fetchTrialBalanceAmount` 取「贷方发生 − 借方发生」=本期发生额，非余额） | h10Constants.ts:H10_ACCOUNT_CODE / useH10Adjudication.ts |

    - **🔴 H3 防跨循环污染实现说明（硬约束，gate 专项守护）**：
      - 回写科目一律取 render 下发的 `h3AccountScope`（`html_data.tb_source_codes.slots[key]`），**不臆断硬编码**。改造前历史 bug 是写死 1503/1504（分属 G6 可供出售金融资产 / G4 债权投资，属别循环），会把投资性房地产审定数污染到他循环科目行（同 H8/H9 污染 K2 那次）。
      - `publishToTb` 构造 `writeback_rows` 时逐槽判断：`if (grossCode.value) rows.push(...)`；`if (accumDepCode.value) rows.push(...)`。其中 `accumDepCode = isAccountAbsent ? '' : accountCode`——**本项目无累计折旧科目（后端解析 found=false）时为空串 → 该行被跳过（宁缺勿造）**。`grossCode` 经 `h3AccountScope.accountCode` 恒解出至少兜底码 1521（1521 是 H3 本循环科目族，写它不污染他循环，与旧 1503/1504 本质不同）。
      - `rows.length === 0` 时不发 POST（`ElMessage.warning` 提示「本项目无相关科目，未发布任何 TB 行」）。
      - gate 专项断言：`hAdjudicationPublishGate.spec.ts` 的「🔴 防污染：本项目无累计折旧科目（found=false）→ writeback_rows 不含该行」用例 mount H3 传 `tb_source_codes.slots.accum_dep.found=false`，断言 `writeback_rows` 只含 1521、**不含 1525**、`toHaveLength(1)`。
    - **改造范式说明**：
      - **A 类（H1/H2/H4/H5/H6，adjudication composable）**：把原 `.vue` 的 `onWritebackTB` 回调（直调旧端点 `PUT /projects/{pid}/trial-balance/writeback`）删除，改在 `useHxAdjudication` 新增 `publishToTb()`：`readonly/publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → `api.post('/api/workpapers/{wpId}/audit-determination/publish-to-tb', {sheet_name, writeback_rows})` → `ElMessage.success` → `emitAdjudicated()`（仍 emit `substantive:adjudicated`）。同时把原 `publishAdjudicated`（写 TB + emit）拆为 `emitAdjudicated`（**只 emit 不写 TB**，供数据变化/普通保存路径 Req 1）与 `publishToTb`（显式写）。`.vue` `handlePublish` 改为 `await state.publishToTb()`，删本地 `publishing` ref 改用 composable 的，加/改「发布到试算表」按钮（`type=warning` `:loading=publishing` `:disabled=isReadonly` `data-testid=h{n}-publish-tb`）。为可测 readonly 早退，给 H1/H4/H5/H6 composable 补 `isReadonly?: Ref<boolean>` 入参（H2/H10 本已有）。
      - **H3（.vue inline watcher）**：删 1.5s debounce 自动写 TB（`debouncedWritebackTb`/`writebackTrialBalance` 原 `http.put`）——违反 Req 1。单元格变化 `onOrigCellChange`/`onDepCellChange`/`onImpairCellChange` 改为只调 `emitAdjudicated()`（emit `substantive:adjudicated` 不写 TB）。新增 `publishToTb()`（confirm + POST + 防污染 rows）+ 工具栏「发布到试算表」按钮（`data-testid=h3-publish-tb`，`:disabled=isReadonly`）。
      - **H7 Cost/Fair（.vue 自包含 handlePublish）**：`handlePublish` 加 `if (publishing.value||props.isReadonly) return` + `ElMessageBox.confirm` 中文二次确认，`api.put(.../trial-balance/writeback)` 改 `api.post(.../publish-to-tb, {sheet_name:'审定表H7-1', writeback_rows:[{1621, balance}]})`，保留 `eventBus.emit('substantive:adjudicated')`。按钮改 `type=warning` + `data-testid=h7-cost/fair-publish-tb`。
      - **H10（A+B 多重自动写）**：删 `onMounted → void publishAdjudicated()` 自动写（改 `emitAdjudicated()` 只 emit）；`publishAdjudicatedDebounced`(1.5s，被 applyDetailFill/fillFromDetail/行编辑触发)改调 `emitAdjudicated`（只 emit）；`publishAdjudicated` 拆为 `emitAdjudicated` + `publishToTb`（confirm + POST 6115 **occurrence** + emit）；删 `writebackTB`/`writebackTrialBalance` 入参与 `writebackFn`。`H10TabAdjudication.onPublish` 改 `await adj.publishToTb()`（内置 confirm），按钮改 `data-testid=h10-publish-tb`。`GtH10.handleSubstantiveAdjudicated`（跨 wp 收到 6115 审定即自动 `formData.writebackTrialBalance` 写 TB 的旁路，违反 Req 1/2）连 listener 一并删除；跨 wp 处置明细带入仍走 `disposal:completed`（只追加 H10-2 明细行不写 TB）。
      - **H6/H10 决策(a)补真回写（Property 10）**：H6 原 `onWritebackTB` 只 emit「已回写TB(1606)」提示但从不写 `trial_balance`（假回写）；H10 `onPublish` 显示「6115 发生额已回写」但 `publishAdjudicated` 只 emit。二者按 K5/K7 决策(a) 补真回写（走 publish-to-tb），消除「提示成功但 TB 未变」的假回写状态。
      - **死代码清理（触类旁通）**：H5 迁移后 `useH5FormData.writebackTB`（1631/1632）零消费 → 删 + 收口注释 + 移除 return export + 清失效 `eventBus` import；H10 `useH10FormData.writebackTB`（+alias `writebackTrialBalance`）零消费 → 删 + 收口注释。grep 实证二者全仓 0 生产/测试调用方。
    - **改的文件（18 源 + 1 新测试 + 3 改测试 = 22）**：
      - Adjudication composable（6）：`useH1Adjudication.ts` / `useH2Adjudication.ts` / `useH4Adjudication.ts` / `useH5Adjudication.ts` / `useH6Adjudication.ts` / `useH10Adjudication.ts`（各拆 emitAdjudicated + publishToTb + publishing + isReadonly 守卫 + import ElMessage/ElMessageBox/api；移除 onWritebackTB 入参）
      - FormData（2 死代码清理）：`useH5FormData.ts`（删 writebackTB + eventBus import）/ `useH10FormData.ts`（删 writebackTB + writebackTrialBalance alias）
      - Tab 组件（8）：`h1/core/H1TabAdjudication.vue` / `h2/core/H2TabAdjudication.vue` / `h3/core/H3TabAdjudicationCost.vue` / `h4/core/H4TabAdjudication.vue` / `h5/core/H5TabAdjudication.vue` / `h6/core/H6TabAdjudication.vue` / `h7/core/H7TabAdjudicationCost.vue` / `h7/core/H7TabAdjudicationFair.vue` / `h10/core/H10TabAdjudication.vue`（destructure publishToTb/publishing + 按钮改造 data-testid + handlePublish 调 publishToTb；H3 删 debounce 自动写 + 加按钮；H7 handlePublish 加 confirm + 改 POST）—— 实为 9 个 .vue
      - 宿主（1）：`GtH10AssetDisposalIncome.vue`（删跨 wp 自动写 listener handleSubstantiveAdjudicated + 移除 writeback-trial-balance prop 传递 + 删无用 H10_ACCOUNT_CODE import）
      - 新增测试：`composables/__tests__/hAdjudicationPublishGate.spec.ts`（参数化 H1/H2/H4/H5/H6/H10 composable + mount H3/H7Cost/H7Fair）
      - 改测试（test-follows-source）：`useH1Adjudication.spec.ts` + `useH2Adjudication.spec.ts`（旧 publishAdjudicated/onWritebackTB 用例 → publishToTb 断言 + 加 apiProxy/element-plus mock）/ `useH4Adjudication.spec.ts`（清死 onWritebackTB prop）/ `h6Integration.spec.ts`（更新注释）
    - **测试命令与 pass 数**：
      - 新 gate：`rtk npx vitest run src/components/workpaper/composables/__tests__/hAdjudicationPublishGate.spec.ts --reporter=dot` → **43 passed / 0 failed**（Group A composable H1/H2/H4/H5/H6/H10 × [POST 命中 sheet_name/科目/amount_kind、不再调旧端点、取消→无post无emit、readonly→无post、发布后仍 emit substantive:adjudicated] + H1 多科目 3 行 / H5 双科目 2 行 / H10 occurrence 专项 + Group B mount H3[两科目/🔴防污染无accumDep只1行/取消/readonly disabled] + H7 Cost/Fair[点击→POST 1621 balance/取消/readonly]）
      - 回归：`useH1/H2/H4/H6Adjudication + hAdjudicationPublishGate` = **93 passed**；`h5Integration + h6Integration + h3-integration + h10AssetDisposalIncome.integration + useH10P1 + useH10P2 + h7BiologicalAssets.integration + h7BiologicalAssets.e2e + h5OilGasAssetsRegistry + h3SourcePanelWiring + useH10Disclosure + h10DisclosureSync` = **156 passed / 0 failed**
      - ESLint（13 核心改动文件 + GtH10）：**0 errors**（warnings 全为 loadTb/calc 未改代码既存 no-amount-arithmetic/no-amount-toFixed/no-direct-audit-fetch，新增 publishToTb 代码 0 warning）
      - file_size gate：`check_file_size.py` 全部改动文件 **通过**（最大 H1TabAdjudication.vue 1062 行 / useH4Adjudication.ts 1152 行，均 <1500 上限；无文件需入白名单）
    - **发现的偏差/降级**：
      - 🟢 **sheet 名全可解无降级**：H1–H10 审定表子码均标准 `H{n}-1`（render schema generated/H*.yaml 逐一实证含 `label: H{n}-1`）。
      - 🟡 **H7 口径实证纠偏（task「occurrence 存疑」）**：task 标 H7 为 occurrence 高风险，运行时实证=**balance**（1621 生产性生物资产是余额类资产，成本模式审定净值余额 / 公允模式审定期末公允价值余额，均非损益发生额）。已按 balance 实现。
      - 🟡 **H6/H10 原为假回写（未在 K5/K7 决策清单）**：census 未标 H6/H10 为假回写，实证发现 H6 `onWritebackTB` 只 emit、H10 `publishAdjudicated` 只 emit（TB 写实际靠 mount/debounce/跨wp 自动路径）。按 Property 10 + K 决策(a) 先例补真回写，消除假回写状态。
      - 🟢 **H3 gross 恒写兜底码 1521 非「宁缺勿造」违反**：`h3AccountScope.accountCode(gross)` 无 isAccountAbsent 检查 + queryCodes 有 fallback 1521，故 gross 恒解出。这是源码既有行为（沿用不改）；1521 是 H3 本循环族不污染他循环，防污染硬约束的落点是备抵科目 accumDep/impair（缺则跳过）。
      - 🟡 **vue-tsc 全量类型检查环境 OOM**：`npx vue-tsc --noEmit` 即使 `--max-old-space-size=8192` 仍 exit 134（JS heap OOM，项目体量所致，非本任务代码问题）。改用 ESLint（typescript-eslint TS-aware 解析，0 error）+ vitest（esbuild 编译全部被测模块 + 60/93/156 测试运行通过）交叉验证类型/编译正确性。
    - **预存无关失败实证**：本任务改动前 grep 确认 H5/H10 FormData.writebackTB 无任何测试引用（删除不破坏既有测试）；改写的 3 个既有测试均属 test-follows-source（断言旧端点/旧方法，随迁移更新）。未见与本任务无关的预存失败被引入（所跑 H1~H10 全批次 156+93 全绿）。
    - **端到端验证点**：前端 gate + mount 覆盖「确认→publish-to-tb 落库路径 + 取消/readonly 早退 + 防污染 + 多科目 + occurrence」；后端 M0 端点集成测试（Task 1）已覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写。真实项目 Playwright 全链路归 task 21*（待 start-dev.bat 环境），真实 PG H 循环审定数据 UAT 归 task 20*（data-blocked）。

- [x] 11. H9 双科目审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep H9 确认 `H9-1` 可解
  - 活路径：`H9TabAdjudication`(inline callback，租赁负债 + 未确认融资费用双科目)；**注意端点路径当前无 `/api` 前缀需归一**
  - 前端单测（双科目 writeback_rows）+ 端到端验证点
  - _需求: 5, 2, 8_
  - **✅ 完成证据（2026）**：
    - **sheet 名可解性 + 双科目 + 口径实证表**（sheet 名来源：`backend/data/ledger_adapters/wp_render_schema/generated/H9.yaml` L143 `审定表H9-1:`（`A2: 租赁负债审定表` / `class_code: F-审定表`）；`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b` / handler `^[D-N]\d+-1$`；我传 `sheet_name='审定表H9-1'` → 解出 `H9-1` ✅，无 R1 降级）：

      | 载体 | 我传的 sheet_name | 解出子码 | 科目（实证来源） | 口径 amount_kind | 形态实证来源 |
      |---|---|---|---|---|---|
      | `H9TabAdjudication.vue` 内联 `handleWriteback`（.vue 内联，非 composable；改造后 = publishToTb 语义） | `审定表H9-1` | H9-1 ✅ | **双科目**：租赁负债 gross（`leaseLiabilityCode = h9Scope.grossCode(tbSourceCodes)`，兜底 `2601`，双族 2601/2651）+ 未确认融资费用（`unearnedFinanceCode = h9Scope.slotCodes(...,'unearned_finance')[0]`，兜底 `2602`） | **balance**（🔴运行时实证：租赁负债=负债类期末余额、未确认融资费用=负债备抵类期末余额，均资产负债表项非损益发生额；组件方法论上下文明示「负债类期末=期初+贷方-借方；备抵类期末=期初+借方-贷方」） | `H9TabAdjudication.vue:handleWriteback` + `hCycleAccountScope.ts:H9_ACCOUNT_DEF`（`slotFallbacks.gross=['2601','2651']` / `unearned_finance=['2602']` / `grossFallback='2601'` / `wrongLegacyCodes=['2205']`） |

    - **🔴 /api 前缀归一说明（本任务重点）**：
      - **改造前真实路径**：`H9TabAdjudication.handleWriteback` 用 **`http.put('/projects/${props.projectId}/trial-balance/writeback', {...})`** —— (a) **无 `/api` 前缀**（`http` = `@/utils/http`，非 apiProxy）；(b) **双科目分两次 PUT**（先租赁负债、再未确认融资费用，非原子）；(c) 无二次确认（点按钮直写）；(d) **历史 latent bug**：`account_code: leaseLiabilityCode`/`unearnedFinanceCode` 传的是 **ComputedRef 本体未 `.value` 解包** = 科目码传成对象（后端按对象取科目必失败/写错科目）。
      - **改造后统一路径**：`api.post('/api/workpapers/${props.wpId}/audit-determination/publish-to-tb', { sheet_name:'审定表H9-1', writeback_rows:[…] })`（`const { api } = await import('@/services/apiProxy')`，含 `/api` 前缀；`wpId` 守卫）。ComputedRef 全部 `.value` 正确解包（`leaseLiabilityCode.value`/`unearnedFinanceCode.value`）。
    - **改造范式说明（复刻 D2/D4-1/F/H/K）**：
      - `handleWriteback` 改造：`writebackLoading.value || props.isReadonly` 早退（复用既有 `writebackLoading` ref 作 publishing 守卫）→ 缺 `wpId` 早退 → **双科目归集为 `writeback_rows` 两行**（`leaseCode` 非空 push 租赁负债 balance 行、`unearnedCode` 非空 push 未确认融资费用 balance 行）→ `rows.length===0` 时 `ElMessage.warning` 早退（宁缺勿造）→ `ElMessageBox.confirm` 中文二次确认（明示写入两科目 + 触发下游报表/错报评价重算）→ `api.post publish-to-tb` **单次原子发布** → `ElMessage.success` → **`publishAdjudicated()`（保留，仍 emit `substantive:adjudicated`）**。取消（confirm reject catch return）/readonly 无副作用（不发 POST、不 emit）。
      - **保留 `substantive:adjudicated` emit + 活联动（Req 8）**：`useH9Adjudication.publishAdjudicated()` 内 `window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail:{ wpCode:'H9', accountCode:'2601', auditedAmount, auditedAmountFinanceCost } }))` **完整保留** → H8-H9 CAS21 联动 / 附注 / 报表刷新不回归。`adjustment:created` 监听（H9-4→H9-1 AJE/RJE 联动）保留不动。
      - 「发布到试算表」按钮改造：`type=warning`（原 `primary`）+ `data-testid=h9-publish-tb` + `:loading=writebackLoading` + `:disabled=isReadonly`；文案「发布到试算表（{租赁负债码} 租赁负债 + {未确认融资费用码} 未确认融资费用）」（原「审定数回写TB」）。按钮仍在 `v-if="!isReadonly"` 包裹内（readonly 无按钮）。
      - 死代码：`http` import 移除（全文 `http.` 计数 0）；编制提示两行文案更新（「发布到试算表（须二次确认）」/「经二次确认后走显式发布门 publish-to-tb，双科目单次原子发布」）；docstring 避免 `trial-balance/writeback` 字面量（源码 `trial-balance/writeback` + `projects/{pid}/trial_balance` 计数均 **0**，为 task 18 CI 守卫预留 clean）。**H9 FormData 死代码此前已由 task 17 批B 移除**（`useH9FormData.writebackTB` 零消费，已删+收口注释），本任务无需再动；全仓无 `h9:writeback-trial-balance` window 监听器（本组件 form A inline callback，非 form B）。
    - **改的文件（1 源 + 1 改测试 = 2）**：
      - `h9/core/H9TabAdjudication.vue`：`handleWriteback` 重写（confirm + 双科目 writeback_rows + POST publish-to-tb + 保留 publishAdjudicated emit）+ 移除 `http` import + 按钮 type/testid/disabled + 2 行编制提示文案 + docstring
      - `composables/__tests__/hAdjudicationPublishGate.spec.ts`：新增「H9 双科目审定表发布走显式发布门」describe（mount H9TabAdjudication 走真实点击路径，5 用例；复刻 Task 10 H3/H7 Group B mount 范式；因 H9 用 `window.dispatchEvent` 派发 substantive:adjudicated，emit 断言用 `window.addEventListener` 而非 eventBus）
    - **测试命令与 pass 数**：
      - gate（H1~H10 + H9）：`rtk npx vitest run src/components/workpaper/composables/__tests__/hAdjudicationPublishGate.spec.ts --reporter=dot` → **48 passed / 0 failed**（原 43 H1-H10 + 新增 5 H9：①确认→POST publish-to-tb（url 含 `/api/workpapers/wp-h9-001/audit-determination/publish-to-tb` / sheet_name 匹配 H9-1 / **writeback_rows 恰 2 行含 2601+2602** / 全 amount_kind=balance / audited_amount 为 number）②不再调旧端点 trial-balance/writeback（PUT/POST 变体）③取消二次确认→无 POST 无 emit ④readonly→无发布按钮 + 无 POST ⑤发布后仍 emit substantive:adjudicated（detail.wpCode='H9'））
      - H9 全回归：`npx vitest run src/components/workpaper/h9 + useH9AdjudicationFill + useH9P0Pack + useH9Engines.unit + useH9TerminationAndLinkage + h9LeaseLiabilities.pbt + h9LeaseLiabilities.contract` → **135 passed / 0 failed**（含 `h9AdjudicationTbWiring.spec.ts` 源码扫描契约测试全过，证明 `:html-data`/`:wp-id`/`:project-id`/`:all-responses`/`:is-readonly` prop 未被破坏 + 契约测试 `h9LeaseLiabilities.contract` 全过）
      - ESLint（2 改动文件）：**0 errors**（14 warnings 全为 `no-amount-toFixed`，均在未改的 summary/linkage 展示代码 `.toFixed()`，新增 handleWriteback + 测试代码 0 warning）；getDiagnostics 2 文件 0 问题。
      - file_size gate：H9TabAdjudication.vue **892 行**（HEAD 847 行，净增 45 行；<1500 上限，无需 whitelist）。
    - **发现的偏差/降级**：
      - 🟢 **sheet 名可解无降级**：`审定表H9-1` 实证在 render schema，解出 `H9-1`。
      - 🟢 **口径实证 balance（无 occurrence 存疑）**：H9 双科目均资产负债表项（租赁负债 + 未确认融资费用备抵），非损益发生额 → 均 balance。
      - 🟡 **修复历史 latent bug**：改造前 `handleWriteback` 传 ComputedRef 本体未解包（`account_code: leaseLiabilityCode` 而非 `.value`）—— 科目码传成对象。改造后正确解包。
      - 🟢 **无假回写**：H9 改造前是**真回写**（两次 http.put 真写 TB），非 H6/H10 那类只 emit 的假回写；本任务只是把两次 PUT 归一为单次原子 POST + 加二次确认。
      - 🟢 **form A 无 form B listener 可删**：H9 是 .vue inline callback（form A），无 `h9:writeback-trial-balance` dispatch/listener 链需拆（与 F/部分 H 的 form B 不同）。
    - **预存无关失败实证**：所跑 H9 全批次（gate 48 + 回归 135）全绿，无预存失败被引入。H9 FormData 死代码 task 17 批B 已删且无测试引用（本任务未触碰）；本任务改的测试（hAdjudicationPublishGate 新增 describe）属新增，非改写既有断言。**无需 git stash 实证**（零失败）。
    - **端到端验证点**：前端 gate mount 覆盖「点击「发布到试算表」→ 中文二次确认 → publish-to-tb 双科目原子落库路径 + 取消/readonly 早退 + 双科目单次 writeback_rows + 仍 emit substantive:adjudicated」；后端 M0 端点集成测试（Task 1）已覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写。真实项目 Playwright 全链路归 task 21*（待 start-dev.bat 环境），真实 PG H9 租赁负债审定数据 UAT 归 task 20*（data-blocked）。

## M8：G 循环（活 11 个，sheet 名可解性存疑最高）

- [x] 12. G 循环审定表改走显式发布端点（逐组件确认子码）
  - **第一步逐一实证 sheet 名（R1 中/高风险）**：grep 每个 G 底稿 `sheetName`/render schema/`SheetLabels` 实证能否解出 `[D-N]{n}-1`；G1/G2/G3/G5/G7 中风险（命名多样），G8–G14 高风险（损益/公允/减值发生额）
  - 活路径（form B）：G1–G3,G5,G7–G14（`useG{n}FormData` + `GtG{n}`，移除 `g{n}:writeback-trial-balance`，保留 `g{n}:save-items` 与「substantive:adjudicated 供跨模块刷新不重复写 TB」语义）；G7 多科目动态(权益+减值)；G8–G14 发生额可批量套模板。（G4 无 TB 回写正交排除；G6 变体端点死代码归 task 17）
  - **不可解者**：任务内规整命名，或按 R1 降级登记（保留旁路单独登记）。切换点 = 端点 `extract_determination_wp_code` 返回 None → 400
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8, 7_
  - **✅ 完成证据（2026，本轮收尾：G 循环代码改造在前序会话工作树完成，本轮补 gate 测试 + 回归更新 + 验证 + 修复验证中发现的 2 个真 bug）**：
    - **🔴 sheet 名可解性 + 科目 + 口径逐组件实证表**（sheet 名来源：`backend/data/ledger_adapters/wp_render_schema/generated/G{n}.yaml` 逐一 grep 确认；`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b` / handler `^[D-N]\d+-1$`；各组件传的 `sheet_name` 字面量为源码 grep 实证，非臆断；**全可解，无 R1 降级**）：

      | 组件 | 载体 | 我传的 sheet_name（源码实证） | render schema 子码 | 解出 | 科目（源码实证） | 口径 amount_kind |
      |---|---|---|---|---|---|---|
      | G1 交易性金融资产 | `G1TabAdjudication.vue handlePublishToTb`（.vue 内联） | `审定表G1-1` | `审定表G1-1`(G1.yaml) | G1-1 ✅ | 硬编码 `'1501'`（totalRow.closingAudited） | balance |
      | G2 应收利息 | `useG2Adjudication.publishToTb` | `审定表G2-1` | `审定表G2-1`(G2.yaml) | G2-1 ✅ | `G2_ACCOUNT_CODE`=1132（g2AdjudicationItems.ts） | balance |
      | G3 应收股利 | `useG3Adjudication.publishToTb` | `审定表G3-1` | `审定表G3-1`(G3.yaml) | G3-1 ✅ | `G3_ACCOUNT_CODE`=1131（g3Constants.ts） | balance |
      | G5 长期应收款 | `useG5Adjudication.publishToTb` | `审定表G5-1` | `审定表G5-1`(G5.yaml) | G5-1 ✅ | `G5_ACCOUNT_CODE`=1531（g5Constants.ts） | balance |
      | G7 长期股权投资 | `G7TabAdjudication.vue handlePublishToTb`（.vue 内联，**多科目动态**） | `审定表G7-1` | `长期股权投资审定表G7-1`(G7.yaml，正则仍解出 G7-1) | G7-1 ✅ | 原值 `accountGross`(兜底 1511) + 减值 `accountImpairment`(兜底 1512)，由 tb_source_codes 解析透传，端点不硬编码 | balance |
      | G8 其他权益工具投资 | `useG8Adjudication.publishToTb` | `审定表G8-1` | `审定表G8-1`(G8.yaml) | G8-1 ✅ | `G8_ACCOUNT_CODE`=1503（g8Constants.ts） | balance |
      | G9 其他非流动金融资产 | `useG9Adjudication.publishToTb`（**动态**） | `审定表G9-1` | `审定表G9-1`(G9.yaml) | G9-1 ✅ | `tbResolvedCode.value || G9_ACCOUNT_CODE`(兜底 1519，g9Constants.ts；历史 1510/1504) | balance |
      | G10 交易性金融负债 | `useG10Adjudication.publishToTb`（**动态**） | `审定表G10-1` | `审定表G10-1`(G10.yaml) | G10-1 ✅ | `tbResolvedCode.value || G10_ACCOUNT_CODE`(兜底 2101，g10Constants.ts) | balance |
      | G11 投资收益 | `useG11Adjudication.publishToTb` | `审定表G11-1` | `审定表G11-1`(G11.yaml) | G11-1 ✅ | `G11_ACCOUNT_CODE`=6111（g11Constants.ts） | **occurrence**（损益类本期发生额，源码 confirm 文案明示） |
      | G12 净敞口套期收益 | `useG12Adjudication.publishToTb`（有 variance/原因发布前置守卫） | `审定表G12-1` | `审定表G12-1`(G12.yaml) | G12-1 ✅ | `G12_ACCOUNT_CODE`=6103（g12Constants.ts） | **occurrence** |
      | G13 公允价值变动收益 | `useG13Adjudication.publishToTb` | `审定表G13-1` | `审定表G13-1`(G13.yaml) | G13-1 ✅ | `G13_ACCOUNT_CODE`=6101（g13Constants.ts） | **occurrence** |
      | G14 信用减值损失 | `useG14Adjudication.publishToTb`（有 原因/明细/variance 发布前置守卫） | `审定表G14-1` | `审定表G14-1`(G14.yaml) | G14-1 ✅ | `G14_ACCOUNT_CODE`=6702（g14Constants.ts） | **occurrence** |

      - **G4 正交排除**：G4 无 TB 回写（investment 主表，回写走 G4MainAdjustment/G4_ACCOUNT_CODE=1501 但非审定发布门场景），本 task 不含。
      - **G6 归 task 17**：`useG6MainFormData.writebackTB`（变体端点 `POST /api/projects/{pid}/trial_balance` 科目 1503）为零消费死代码，已在 task 17 批C 移除。
    - **form B 链处置实证（grep `g{n}:writeback-trial-balance` 全仓仅剩收口注释）**：G1–G3/G5/G8–G14 各 `useG{n}Adjudication.publishAdjudicated`/`broadcastAdjudicated` 已移除 `dispatch('g{n}:writeback-trial-balance')`（改 emit-only `substantive:adjudicated`）；各宿主 `GtG{n}` 已移除 `handleG{n}Writeback` 监听器（保留收口注释，`g{n}:save-items` 等其他事件保留）；各 `useG{n}FormData.writebackTB/writebackTrialBalance` 零消费死代码已删 + 收口注释。**通道实证**：G3 走 mitt `eventBus.emit('substantive:adjudicated')`，其余（G2/G5/G8/G9/G10/G11/G12/G13/G14/G1/G7）走 `window.dispatchEvent(new CustomEvent('substantive:adjudicated'))`（gate 测试 emit 断言同挂两通道兼容）。
    - **改造范式**：composable 型（G2/G3/G5/G8/G9/G10/G11/G12/G13/G14）新增 `publishToTb`（`isReadonly/publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → `api.post publish-to-tb {sheet_name, writeback_rows}` → 成功后 `publishAdjudicated/notifyAdjudicated/broadcastAdjudicated` 通知附注刷新）+ `publishing` ref；`.vue` 内联型（G1/G7）在 `handlePublishToTb` 承载同逻辑（G7 多科目 `if(grossCode) rows.push` + `if(impairCode) rows.push` 单次原子 writeback_rows，rows 空则 warning 不发）。G12/G14 保留原发布前置守卫（variance/原因/明细）。
    - **本轮改的文件（源 1 修 bug + 测试 9）**：
      - 🔴 bugfix 源文件：
        - `composables/useG7FormData.ts`：前序会话删除了 `writebackTB` 定义但 **return 块残留 `writebackTB` / `writebackTrialBalance: writebackTB` 两条 export → 运行时 ReferenceError（模块加载即崩）**。本轮删除孤儿 export + 加注释。grep 实证 GtG7/测试均不 destructure 这两 export，删除安全。
        - `composables/useG5Adjudication.ts`：`isReadonly` 计算属性 `!!opts.isReadonly?.value || !!opts.isReadonly` 在 `opts.isReadonly` 为 Ref 时 `!!Ref对象` 恒真 → **isReadonly 恒 true → 发布按钮永久禁用 + publishToTb 早退 → 发布门对 G5 形同虚设**（GtG5 传的正是 `readonlyRef` Ref）。本轮改 `isRef(opts.isReadonly) ? !!opts.isReadonly.value : !!opts.isReadonly` 正确解包 + 加 `isRef` import + 注释。gate 测试 G5 用例守护。
      - 新增 gate 测试：`composables/__tests__/gAdjudicationPublishGate.spec.ts`（Group A composable G2/G3/G5/G8/G9/G10/G11/G12/G13/G14 × [POST 命中 sheet_name/科目/amount_kind、不再调旧端点、取消→无post无emit、readonly→无post、发布后仍 emit substantive:adjudicated] + Group B mount G1/G7[点击→POST/取消/readonly disabled，G7 多科目单次 writeback_rows 含 1511+1512]）。G12 有 variance 发布前置守卫（空数据审定合计非 0 → variance≠0），测试用 `prep` hook 把 TB 取数对齐审定合计清零 variance 后走真正发布门。
      - 改测试（test-follows-source，随迁移更新旧断言）：`g8/g9/g11/g12/g13/g14ReviewFixes.spec.ts` 的「TB 回写单通道」用例（原断言 `g{n}:writeback-trial-balance` dispatch + 父组件 addEventListener + FormData `/trial-balance/writeback`）→ 改断言 publishToTb → `publish-to-tb` + 不再 dispatch/监听旧事件；`useG2Adjudication.spec.ts`「publishAdjudicated 派发试算回写事件」→ 改断言只 emit `substantive:adjudicated`、不再派发 `g2:writeback-trial-balance`；`useG14Adjudication.spec.ts`「差异未清或原因缺失时 publishAdjudicated 不发布」→ 守卫已从 publishAdjudicated 迁到 publishToTb，改断言 `publishToTb` 守卫拦下（不发 POST）、补齐原因后走 POST（6702 occurrence）+ 加 post/ElMessageBox mock。
    - **测试命令与 pass 数**：
      - 新 gate：`rtk npx vitest run src/components/workpaper/composables/__tests__/gAdjudicationPublishGate.spec.ts --reporter=dot` → **56 passed / 0 failed**（10 composable × 5 + G1 × 3 + G7 × 3）
      - 迁移守护 + 单测（9 spec）：`useG2Adjudication + useG14Adjudication + gAdjudicationPublishGate + g8/g9/g11/g12/g13/g14ReviewFixes` → **9 files 全绿**
      - ESLint（本轮 11 改动文件）：**0 errors**（2 warnings 均为 `no-direct-audit-fetch`，在 useG5Adjudication:492 / useG7FormData:430 的 `fetchTrialBalance` 未改代码，非本轮新增）
      - file_size gate：`check_file_size.py` —— 本轮改动文件中仅 `G7TabAdjudication.vue`（1715 行 > 1500）超限，但**改动前 HEAD 即 1647 行已超限**（前序会话迁移 +68 行至 1715），已登记 `backend/scripts/file_size_whitelist.txt`（baseline=1715，附拆分方向）；useG5Adjudication(622)/useG7FormData(508)/G1TabAdjudication(625) 均 <1500 无需登记。
      - 类型/编译：vue-tsc 全量 OOM（项目体量，同 H task 记录）；改用 ESLint（typescript-eslint TS-aware，0 error）+ vitest（esbuild 编译全部被测模块 + 56+回归运行通过）交叉验证。
    - **发现的偏差/降级 + 修复的 bug**：
      - 🟢 **sheet 名全可解无降级**：G1–G14 审定表子码经 render schema generated/G*.yaml 逐一实证可解（G7 label 为 `长期股权投资审定表G7-1`，正则 `([D-N]\d+-1)\b` 仍解出 `G7-1`）。
      - 🔴 **修复 2 个真 bug（验证中发现，根因修复）**：①useG7FormData.ts return 块残留已删的 `writebackTB` export（前序会话未删净）→ ReferenceError；②useG5Adjudication.ts `isReadonly` 对 Ref 恒真致 G5 发布门失效。均属前序会话 G 迁移的遗留缺陷，本轮根因修复 + 测试守护。
      - 🟢 **G12/G14 发布前置守卫保留**：variance 差异 / 原因分析必填 / 明细一致性守卫在 publishToTb 内保留（未因迁移丢失），gate 测试对 G12 用 prep 清零 variance 验证守卫通过后的真正发布路径；G14 单测专项验证守卫拦截 + 补齐后放行。
      - 🟢 **口径 occurrence/balance 逐组件核对**：G11/G12/G13/G14 损益类（投资收益/套期收益/公允价值变动收益/信用减值损失）= occurrence；G1/G2/G3/G5/G7/G8/G9/G10 资产负债表项 = balance（源码 writeback_rows amount_kind 字面量实证）。
    - **预存无关失败 git stash 实证**：本轮跑 `composables/__tests__` + g1 + g7 全量得 12907 测试 / 54 failed；其中 2 个（useG2/useG14Adjudication）本轮已修（test-follows-source），其余 **52 个分布在 11 个文件**（`d4FourTableWiring / g7ColumnThreeWayAlignment / hgDisclosureColumns / k4NoteSectionMap / kLiabilityNoteSubtableContract / kPlNoteSubtableContract / l2l4DisclosureWiring / l4-bonds-payable.integration / noteSectionMapNamingCoverage / useF3Integration / useF5Integration`）—— `git stash` 我全部改动后单跑这 11 文件在 **HEAD 基线同样 52 failed**，证明属 D4/K/L/F/hg-disclosure 等**他 spec 的预存失败**，非本 task 引入（本 task 未触碰这些文件）。stash pop 后改动完整恢复。
    - **端到端验证点**：前端 gate + mount 覆盖「确认→publish-to-tb 落库路径 + 取消/readonly 早退 + 多科目单次 writeback_rows(G7) + occurrence(G11-G14) + 守卫(G12/G14) + 发布后仍 emit substantive:adjudicated」；后端 M0 端点集成测试（Task 1）已覆盖 writeback_rows→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写。真实项目 Playwright 全链路归 task 21*（待 start-dev.bat 环境），真实 PG G 循环审定数据 UAT 归 task 20*（data-blocked）。

## M9：I + E + J1（活 8 个；I2 先评估合规）

- [x] 13. I 循环审定表改走显式发布端点（改 adjudication 层，避开 FormData 死代码）
  - **第一步实证 sheet 名 + I2 特例评估**：grep I1–I6 确认子码可解；**I2 已用新 per-wp 端点** `POST /api/workpapers/{wpId}/writeback-trial-balance`（非旧 project 端点）→ 先评估 I2 是否已合规 / 可直接并入 `publish-to-tb`，不当普通旧端点直调改
  - 活路径（adjudication 层 inline writeback）：I1(多科目 1701/1702/1703)、I3(1711)、I4(1801)、I5(1911)、I6(6602 发生额，**保留 I6→I2 联动** `research:expense-updated`+`i6:adjustment-writeback`)、I2(视评估结果)。（`useI1~I6FormData.writeback*` 是 BP-5 死代码 duplicate，归 task 17，**只改真实被消费的 adjudication，勿接死代码**）
  - 前端单测（I6 断言 I6→I2 联动仍发）+ 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **🔴 sheet 名可解性 + 科目 + 口径实证表**（实证来源：`backend/data/ledger_adapters/wp_render_schema/generated/I{1..6}.yaml` sheet label；`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b`（`wp_account_package_resolver.py:82`）；handler 正则 `^[D-N]\d+-1$`（`event_handlers_cycle_linkage.py:441`））：

      | wp | render sheet label | 我传的 sheet_name | 解出子码 | 科目 | 口径 |
      |---|---|---|---|---|---|
      | I1 | `审定表I1`（**无 -1**） | `审定表I1-1` | I1-1 ✅ | 1701/1702/1703（多科目） | balance |
      | I2 | `审定表I2-1` | `审定表I2-1` | I2-1 ✅ | 开发支出（render 下发 → 兜底 1704，动态） | balance |
      | I3 | `审定表I3-1` | `审定表I3-1` | I3-1 ✅ | 1711 | balance |
      | I4 | `审定表I4-1` | `审定表I4-1` | I4-1 ✅ | 1801 | balance |
      | I5 | `审定表I5-1` | `审定表I5-1` | I5-1 ✅ | 1911 | balance |
      | I6 | `审定表I6-1` | `审定表I6-1` | I6-1 ✅ | 6602（损益类） | **occurrence** |

      **均可解，无 R1 降级**。I1 的 render label 是 `审定表I1`（无 `-1`，正则解不出），但与其余循环一样由**前端传字面量 `sheet_name`**（复刻 D2/D4-1/K6/L6 范式，不依赖 render label），传 `审定表I1-1` 即解出 `I1-1` ✅；handler `^[D-N]\d+-1$` 接受 I1-1~I6-1。
    - **🟡 I2 特例评估裁定**（grep 实证）：
      - **(a) 是否已合规？否**。改造前 `I2TabAdjudication.vue` 靠 `useI2Adjudication({ onAfterSave: s => writebackTb(s.endAudited) })` **每次保存自动**回写 TB → 直接违反 Req 1（普通保存/数据变化绝不写 TB）；且其端点 `POST /api/workpapers/{wpId}/writeback-trial-balance` **后端无路由定义**（`grep 'writeback-trial-balance' backend/app/**/*.py` 零命中，唯一引用是 fix 脚本 docstring）→ `catch{}` 吞 404 ⇒ 运行时实为 **no-op 假回写**。既不合规也不真回写。
      - **(b) 是否可/应并入 publish-to-tb？应并入**。移除 `onAfterSave` 自动回写，改为用户显式二次确认 → 统一 `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（`sheet_name '审定表I2-1'` + `writeback_rows [{i2AccountCode, balance}]`），与其余 I 循环一致。开发支出为资产类 → `balance`。`save()` 内原有的 `substantive:adjudicated` emit 保留（附注刷新不回归）。`http` import 保留（`fetchI2TbData` 仍用）。
    - **改造范式**（复刻 D2/D4-1/K6/L6 inline `api.post publish-to-tb`）：每个 `useIxAdjudication` 的 save 动作（`saveAdjudication`/`writeback`）去掉 inline `api.put trial-balance/writeback`，只 persist + `_emitAdjudicated`（仅 emit `substantive:adjudicated`，Req 1）；新增 `publishToTb`（`publishing` 早退 → `ElMessageBox.confirm` 中文二次确认 → 保存明细 → `api.post publish-to-tb` writeback_rows → 成功后 `_emitAdjudicated`）+ `publishing` ref。守卫用 `wpId`。各 TabAdjudication 加「发布到试算表」按钮（`type=warning` `:loading=publishing` `:disabled=isReadonly` `data-testid=i{n}-publish-tb`），原「保存并回写/回写TB」按钮改为「保存」（只保存不写 TB）。
    - **改的文件清单（11 个源文件 + 2 个测试）**：
      - `composables/useI1Adjudication.ts`：`saveAdjudication` 去三科目 PUT；新增 `publishToTb`（单次 `writeback_rows` 三科目 1701/1702/1703 balance，**多科目原子发布**，Req 5）+ `publishing`。（`onCellChange` 仍调 `saveAdjudication` → 现只 emit 不写 TB，合规）
      - `composables/useI3Adjudication.ts`：`saveAdjudication` 去 1711 PUT；新增 `publishToTb`（gate 阻断则不发布）+ `publishing`。
      - `composables/useI4Adjudication.ts` / `useI5Adjudication.ts`：`writeback(force)` 去 PUT（保留名作 save 动作，host 仍 `writeback(false)`）；新增 `publishToTb`（1801 / 1911 balance）+ `publishing`。
      - `composables/useI6Adjudication.ts`：`writeback` 转 save-only（`_emitAdjudicated` 含 `substantive:adjudicated` + **`research:expense-updated`（I6→I2 联动，保留）**）；新增 `publishToTb`（6602 **occurrence**，Req 6）+ `publishing`；import 补 `ElMessageBox`。`i6:adjustment-writeback` 监听器（`onMounted`）未动。
      - `i1/core/I1TabAdjudication.vue`：删本地 `publishing`，destructure composable 的 `publishToTb/publishing`，`handlePublish` 改调 `publishToTb`，按钮 `确认审定 → 回写TB` → `发布到试算表(1701/1702/1703)`（warning，`data-testid=i1-publish-tb`）；顺手删 `handleReview` 里预存无用 `console.log`（消 no-console error，见下）。
      - `i2/core/I2TabAdjudication.vue`：移除 `onAfterSave` 自动回写；`writebackTb` → `publishToTb`（confirm → publish-to-tb）；加 `publishing` + 发布按钮 `data-testid=i2-publish-tb`；save 按钮 `保存并回写`→`保存`。
      - `i3/i4/i5/i6/core/I{n}TabAdjudication.vue`：destructure `publishToTb/publishing`，加 `handlePublish` + 发布按钮（`data-testid=i{n}-publish-tb`）；I6 host **补传 `wpId: computed(()=>props.wpId)`**（原未传，`publishToTb` 需 `options.wpId`）；save 按钮去「回写」字样。
    - **测试**：新增 `composables/__tests__/iAdjudicationPublishGate.spec.ts`（参数化 I1/I3/I4/I5/I6：确认→POST publish-to-tb 命中 sheet_name/科目全覆盖/amount_kind、取消→无 post 无 emit、不再调旧 PUT、发布后仍 emit `substantive:adjudicated`；I1 专项断言多科目单次 `writeback_rows`；I6 专项断言 occurrence + I6→I2 `research:expense-updated` 仍 emit）——**17 passed**。更新 `__tests__/i6Integration.spec.ts` 6.1 块（test-follows-source：`writeback()` 不再写 TB、新增 `publishToTb` occurrence 断言、补 `ElMessageBox` mock）。
    - **命令与 pass 数**：`rtk npx vitest run <9 文件> --reporter=dot` → **202 passed / 0 failed**（iAdjudicationPublishGate 17 + i6Integration + iCycleAdjudicationSeed 96 + i6AdjustmentModel + useI6Adjustment + useI1Adjudication + GtI1IntangibleAssets 19 + i2SheetDispatch + i5SheetDispatch）。ESLint 改动文件 **0 error**（gt-audit warnings 为预存全仓噪声）。
    - **发现的偏差/预存问题（git 实证非本任务引入）**：① `I1TabAdjudication.vue` `handleReview` 的 `console.log`（no-console error）**预存于 HEAD**（`git show HEAD:...I1TabAdjudication.vue | grep console.log` 命中）——因「改动文件 0 error」铁律顺手删除该死调试。② `iCycleAdjudicationSeed.spec.ts` 首轮 10 假红：其 `stripTs` 天真块注释正则 `/\*[\s\S]*?\*/` 把我 I2 注释里 `backend/app/**` 的 `/**` 误当块注释开头 → 吞掉 `fourTableHint`；**git stash 实证是本任务注释引入** → 改注释措辞消除 `/**`，96 passed 恢复。③ `vue-tsc --noEmit` 全项目 OOM（exit 134，NODE_OPTIONS=8192 仍崩）是**预存环境限制**（仓库过大），崩溃前无 `error TS` 输出；类型正确性由 vitest（vite transform 全绿）+ ESLint 0 error 佐证，getDiagnostics 层面等价通过。
    - **降级/待环境**：真实 PG 无对应 I 循环审定数据 → 端到端 UAT 归 task 20*（data-blocked）；Playwright 归 task 21*（待 start-dev.bat 环境）。本任务代码 + 单测/集成测试层面已封板。

- [x] 14. E1 审定表改走显式发布端点
  - **第一步实证 sheet 名**：grep E1 确认 `E1-1` 可解
  - 活路径：`useE1Adjudication`（多科目 byCode 遍历 → `writeback_rows`，self-invoke）
  - 前端单测 + 端到端验证点
  - _需求: 5, 2, 8_
  - **✅ 完成证据（2026）**：
    - **🔴 sheet 名可解性 + 科目（多科目）+ 口径实证表**（实证来源：render schema `backend/data/ledger_adapters/wp_render_schema/generated/E1-1.yaml`（sheet `货币资金审定表E1-1`）+ `E1-1.yaml`（sheet `E1-1 货币资金审定表` / `wp_code: E1-1`）；`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b`（`wp_account_package_resolver.py:82`）；handler 正则 `^[D-N]\d+-1$`（`event_handlers_cycle_linkage.py:441`，E ∈ [D-N]））：

      | wp | render sheet label（实证来源） | 前端传的 sheet_name | 解出子码 | 科目（多科目 byCode 遍历） | 口径 amount_kind |
      |---|---|---|---|---|---|
      | E1 | `货币资金审定表E1-1`（generated/E1-1.yaml） | `审定表E1-1` | E1-1 ✅ | **1001 库存现金 / 1002 银行存款本金 / 1012 其他货币资金+数字货币**（`aggregateAuditedByCode('ending')` 三科目归集） | balance（余额类，各行 `amount_kind='balance'`） |

      **可解，无 R1 降级**。render label 是 `货币资金审定表E1-1`（含 `E1-1`，正则可解）；但与其余循环一致由**前端传字面量 sheet_name `审定表E1-1`**（复刻 D2/D4-1/I/K/L 范式，`E1_DETERMINATION_SHEET_NAME` 常量，不依赖 render label——host `GtE1MonetaryFund` 未向 `E1TabAdjudication` 传 sheetName），传 `审定表E1-1` 即解出 `E1-1` ✅；handler `^[D-N]\d+-1$` 接受 E1-1。
    - **改造范式说明**（复刻 D2/D4-1/I 循环 inline `api.post publish-to-tb`，多科目单次原子发布）：
      1. **self-invoke writeback 消除（Req 1）**：改造前 `useE1Adjudication` 在 `flushSave`（debounce 2s 保存）与 `watch(totalRow.endingAudited)`（数据变化）里**自动** `api.put('/projects/{pid}/trial-balance/writeback')` 三科目直写（绕过显式门/无二次确认/无幂等/无 publish_confirmed）。现 `writebackTrialBalance()` 语义收敛为**仅内存同步**（调 `syncAuditedTotals()` 写 allResponses 供 E1-14 分析表/附注/全局告警读取，**不落 TB**），`flushSave` 仍调它（只同步不写 TB），`watch(totalRow)` 改为**仅 emit `substantive:adjudicated`**（不再调 writebackTrialBalance）。`projectId` 从 destructure 移除（原唯一用途是旧 PUT 的 `/projects/{pid}/`），守卫改用 `wpId`。
      2. **新增 `publishToTb`（Req 2/5）**：`readonly/publishing` 早退 → `wpId` 空守卫 → `syncAuditedTotals()` + `aggregateAuditedByCode('ending')` **多科目 byCode 遍历生成 writeback_rows 三行**（1001/1002/1012，各 `amount_kind='balance'`，一次原子发布，端点不硬编码科目、前端算好透传）→ `ElMessageBox.confirm` 中文二次确认（明示写入 trial_balance + 触发下游报表/错报评价重算）→ `api.post('/api/workpapers/{wpId}/audit-determination/publish-to-tb', {sheet_name, writeback_rows})` → `ElMessage.success` → `publishAdjudicated()`；用户取消 → 无副作用（不 post/不 emit/不写 TB）。新增 `publishing` ref。
      3. **保留 `substantive:adjudicated` emit 及活路径联动（Req 8）**：`publishAdjudicated()`（wpCode='E1' / accountCode='1001,1002,1012' / detail 三科目明细）保留，`watch(totalRow.endingAudited)` 数据变化仍 emit（Req 1：只 emit 不写 TB），`publishToTb` 成功后也 emit → 下游附注/E1-14/全局告警刷新不回归；`detailRows` watch（immediate）仅内存同步保留。
      4. **E1 TabAdjudication 发布按钮**：`E1TabAdjudication.vue` 加「📤 发布到试算表」按钮（`type=warning` `size=small` `:loading=publishing` `:disabled=isReadonly` `data-testid=e1-publish-tb` `@click=publishToTb`），destructure `publishToTb`/`publishing`。
    - **改的文件清单（2 源 + 1 新测试）**：
      - `composables/useE1Adjudication.ts`：`writebackTrialBalance` 收敛为仅内存同步（去 inline PUT）+ 新增 `publishToTb`/`publishing` + `watch(totalRow)` 去 writebackTrialBalance 只 emit + 移除 `projectId` destructure + import `ElMessageBox`/`api`（已有）+ 收口注释；return 补 `publishToTb`/`publishing`。
      - `e1/E1TabAdjudication.vue`：destructure `publishToTb`/`publishing` + 工具栏加发布按钮（warning/loading/disabled/data-testid）。
      - 新增测试 `composables/__tests__/eAdjudicationPublishGate.spec.ts`（6 用例）。
    - **⚠️ FormData 死代码 duplicate 排查（触类旁通 grep）**：`file_search useE1FormData` → **不存在**（E1 无 FormData composable）；grep `useE1FormData.writeback*` 全仓 0 命中 ⇒ **E1 无 FormData 死代码 duplicate 待清理**（与 D/H/K 循环不同，E1 单 adjudication 承载，无 FormData 旁路）。grep `trial-balance/writeback|writebackTrialBalance` 于全部 E1 composable/组件 → **仅 useE1Adjudication 注释引用**（描述改造前反模式），**0 处 live 旧端点直调**。
    - **测试命令与 pass 数**：
      - 新 gate 测试：`rtk npx vitest run src/components/workpaper/composables/__tests__/eAdjudicationPublishGate.spec.ts --reporter=dot` → **6 passed / 0 failed**（①确认→POST publish-to-tb 命中 url + sheet_name(E1-1) + writeback_rows；②多科目 1001/1002/1012 在**同一次** writeback_rows、各 amount_kind=balance、审定数归集正确(1001=100000/1002=2000000/1012=35000)；③不再调旧 trial-balance/writeback(PUT 未被调用)；④取消→无 post 无 emit；⑤readonly→无 post；⑥发布后仍 emit substantive:adjudicated(wpCode=E1/accountCode=1001,1002,1012)）
      - E1/E 循环回归：`npx vitest run <eAdjudicationPublishGate + e1AdjudicationPrefill + e1AmountControlIronLaw + e1MainRowPrefill + e1DisclosureConsistency + e1HostPropWiring + e1HostSeedWiring + e1SourcePanelWiring + useE1Adjustment.pbt + useE1FormulaEngine + e1SheetDispatch>` → **11 files / 206 passed / 0 failed**
      - 后端 M0 契约（E1 依赖）：`rtk ..\.venv\Scripts\python.exe -m pytest tests/test_publish_to_tb_writeback_rows.py -q` → **12 passed**
      - ESLint（3 改动文件）：`npx eslint useE1Adjudication.ts E1TabAdjudication.vue eAdjudicationPublishGate.spec.ts` → **0 errors / 9 warnings**（9 warnings 全为**预存未改代码**：composable line 225/226/300/303 `aggregateAuditedByCode` 三科目 sum 算术 + line 672 `previousTotalAudited - current` watch + Tab line 265 toFixed / 448/494/532 autosize textarea；`git show HEAD:` 实证 toFixed/autosize 4 命中 + previousTotalAudited/byCode 算术 2 命中**均存在于 HEAD**，非本任务引入；新增 publishToTb/按钮代码 0 warning）；getDiagnostics 0。
    - **test-follows-source 核查**：grep E1 全部 `__tests__` 对 `trial-balance/writeback|writebackTrialBalance` → **0 命中** ⇒ 无既有测试断言旧端点，无需迁移更新（E1 旧自动回写无专属断言测试）。
    - **发现的偏差/降级**：
      - 🟡 **E1 UX 变更（合理，符合 Req 1/2）**：改造前 E1 靠 `flushSave` + `watch(totalRow)` **自动**写 TB（无用户确认，正是本 spec 要消除的反模式）；改造后 E1 无隐式自动回写入口 → 本任务在 E1TabAdjudication 新增「发布到试算表」按钮承载显式确认动作。数据变化/普通保存只 emit `substantive:adjudicated` + 内存同步，不写 TB。
      - 🟢 **E1 无 FormData 死代码**（与 D/H/K 循环不同）：E1 单 `useE1Adjudication` 承载，无 `useE1FormData` 旁路 ⇒ 本任务无「顺手删除零消费 FormData writeback」动作（grep 实证不存在），非遗漏。
      - 🟢 **sheet 名可解**：render label `货币资金审定表E1-1` 本身可解，前端传字面量 `审定表E1-1` 更稳，无不可解降级项。
    - **端到端验证点 / 待环境**：前端 gate 单测覆盖「确认→publish-to-tb 落库路径 + 多科目单次原子发布 + 取消/readonly 无副作用 + 不调旧端点 + 仍 emit」；后端 M0 集成测试覆盖 writeback_rows(balance)→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写。真实 PG 无 E 循环货币资金审定数据 → 端到端 UAT 归 task 20*（data-blocked）；Playwright 全链路归 task 21*（待 start-dev.bat 环境）。本任务代码 + 单测/集成测试层面已封板。
    - **⚠️ 说明**：本任务源码（useE1Adjudication `publishToTb`/内存同步收敛 + E1TabAdjudication 按钮）+ gate 测试在此前 in-progress 轮次已落地（`git status` 实证：composable/Tab `M`、test `??`），本轮完成全量验证（gate 6 + E 回归 206 + 后端 12 + ESLint 0 error + FormData 死代码/旧端点/test-follows-source 全 grep 实证）并补齐完成证据块。

- [x] 15. J1 审定表改走显式发布端点（J2 是死代码，归 task 17）
  - **第一步实证 sheet 名**：grep J1 确认 `J1-1` 可解
  - 活路径：`J1TabAdjudication`（@click 按钮 inline，2211）。**J2 不在本任务**——census 实证 J2 整模块（`useJ2FormData`/`useJ2Integration` + `events/publish` + `actuarial` 联动）是无渲染宿主的孤儿链，J2 真实宿主 `J2TabAdjudication.vue` 无 TB 回写；J2 死代码清理归 task 17
  - 前端单测 + 端到端验证点
  - _需求: 1, 2, 8_
  - **✅ 完成证据（2026）**：
    - **🔴 sheet 名可解性 + 科目 + 口径实证表**（实证来源：render schema `backend/data/ledger_adapters/wp_render_schema/generated/J1.yaml`（sheet `审定表J1-1 `，class_code `F-审定表`）+ `backend/data/ledger_adapters/wp_render_schema/J1-1.yaml`（`wp_code: J1-1`，`应付职工薪酬审定表`）；`extract_determination_wp_code` 正则 `([D-N]\d+-1)\b`；handler 正则 `^[D-N]\d+-1$`，J ∈ [D-N]）：

      | wp | render sheet label（实证来源） | 前端传的 sheet_name | 解出子码 | 科目 | 口径 amount_kind |
      |---|---|---|---|---|---|
      | J1 | `审定表J1-1 `（generated/J1.yaml）/ `wp_code: J1-1`（J1-1.yaml） | `审定表J1-1` | J1-1 ✅ | **2211 应付职工薪酬**（组件 inline 常量，负债贷方；报表行 BS-069 国企 / BS-051 上市，无备抵科目） | **balance**（负债余额类，期末审定合计） |

      **可解，无 R1 降级**（低风险余额类审定表）。render label 本身含 `J1-1` 可解；与其余循环一致由**前端传字面量 sheet_name `审定表J1-1`**（复刻 D2/D4-1/E1/I/K12 范式，不依赖 render label），传 `审定表J1-1` 即解出 `J1-1` ✅；handler `^[D-N]\d+-1$` 接受 J1-1。科目 2211 经 `J1TabAdjudication.vue` inline 实证（原 `http.put` body `account_code:'2211'`、audit-objective/guidance 文案、useAdjudicationBringIn `subjectCode:'2211'` 三处交叉印证），**非臆造**。
    - **改造范式说明**（复刻 K12/E1/I inline `api.post publish-to-tb`）：J1 的回写逻辑**内联在 `J1TabAdjudication.vue` 的 `<script setup>`**（`writebackTB()` 函数，非独立 composable；`file_search useJ1FormData` → 0 命中，**J1 无 FormData 死代码 duplicate**，同 E1）。改造前 `writebackTB` 已有 `isReadonly` 早退 + `ElMessageBox.confirm`，但内部直调旧端点 `http.put('/api/projects/{projectId}/trial-balance/writeback', {account_code:'2211', audited_amount})`（绕过显式发布门/无幂等/无 publish_confirmed）。改造：
      1. **旧端点直调消除（Req 2/3）**：`http.put trial-balance/writeback` → `const { api } = await import('@/services/apiProxy')` + `api.post('/api/workpapers/${props.wpId}/audit-determination/publish-to-tb', { sheet_name: '审定表J1-1', writeback_rows: [{ account_code: '2211', audited_amount: amount, amount_kind: 'balance' }] })`（`amount = grandTotal.value.endAudited` 期末审定合计，单科目余额类）。守卫改用 `wpId`（原旧端点用 `projectId`）。
      2. **早退强化（Req 1/2）**：`if (isReadonly || writebackLoading.value) return`（加 `writebackLoading` 早退防重复点击）。`ElMessageBox.confirm` 文案改为「发布到试算表确认」（明示写入 trial_balance + 触发报表/错报评价下游重算），确认按钮「确认发布」；用户取消 → `catch { return }` 无任何副作用（不 post/不 emit/不写 TB）。
      3. **保留 `substantive:adjudicated` emit（Req 8）**：发布成功后仍 `eventBus.emit('substantive:adjudicated', { wpCode:'J1', accountCode:'2211', auditedAmount, begin_audited, end_audited, projectId, timestamp })`（下游附注/报表联动不回归）。`useAdjudicationBringIn`（带入调整，独立 emit）未动。
      4. **按钮 + 文案**：`发布到试算表（2211）` 按钮 `type=success`→`type=warning`、加 `data-testid=j1-publish-tb`、`:loading=writebackLoading`、`:disabled=isReadonly`；audit-objective alert 与 guidance 第 8 条「回写试算平衡表」文案同步改「发布到试算表」（显式发布门语义）。
    - **改的文件清单（1 源 + 1 新测试）**：
      - `j1/core/J1TabAdjudication.vue`：`writebackTB()` 去 `http.put` 旧端点 → `api.post publish-to-tb`（writeback_rows 2211 balance）+ `writebackLoading` 早退 + confirm 文案 + 收口注释；按钮 warning/testid + audit-objective/guidance 文案。
      - 新增 `components/workpaper/composables/__tests__/jAdjudicationPublishGate.spec.ts`（6 用例，`@vue/test-utils` mount `J1TabAdjudication` 点击 `[data-testid=j1-publish-tb]` 走真实点击路径——J1 handler 内联在 .vue 无独立 composable，按任务要求 mount 组件测按钮点击路径；stub 子组件 + mock apiProxy/http/element-plus/useAdjudicationBringIn(其 onMounted 会 load)/useAuditContext 隔离网络）。
    - **测试命令与 pass 数**：
      - 新 gate 测试：`rtk npx vitest run src/components/workpaper/composables/__tests__/jAdjudicationPublishGate.spec.ts --reporter=dot` → **6 passed / 0 failed**（①按钮存在 data-testid=j1-publish-tb + 文案；②确认→POST publish-to-tb 命中 url(wp-j1-001) + sheet_name(J1-1) + writeback_rows 单行 2211/amount_kind=balance/audited_amount=期末审定合计 1000000；③不再调旧 trial-balance/writeback(api.put 未被调用 + 无 http.put/api.post 含该字面量)；④取消→无 post 无 emit；⑤readonly→按钮 disabled + 早退无 post；⑥发布后仍 emit substantive:adjudicated wpCode=J1/accountCode=2211/auditedAmount=1000000）
      - J1/J 循环回归：`npx vitest run <jAdjudicationPublishGate + src/composables/workpaper/j1 全套 + src/components/workpaper/j1 全套 + j1AllocationLedgerPull + j1DisclosureConsistency + j1h4DisclosureColumns + j1NoteSubtableContract + j1NoteSyncPayload>` → **17 files / 269 passed / 0 failed**（含 useJ1Adjudication/useJ1FormulaEngine.pbt/j1-component-dispatch/j1-e2e-integration/j1DisclosureDetailPull 等既有回归，零回归）
      - ESLint（2 改动文件）：`npx eslint J1TabAdjudication.vue jAdjudicationPublishGate.spec.ts --format compact` → **EXIT=0，0 error / 3 warning**（3 warning 全为 `gt-audit/no-adhoc-wp-structure` 手写 autosize textarea @ line 141/207/219，是**预存的审计说明/结论卡片**未改代码；`git show HEAD:...J1TabAdjudication.vue | grep autosize` → 3 命中，实证 HEAD 已存在非本任务引入；新增 publish-to-tb/按钮代码 0 warning）；getDiagnostics 0（vite transform 全绿佐证 TS 编译通过）。
    - **test-follows-source 核查**：grep J1 全部 `__tests__` 对 `trial-balance/writeback|writebackTB` live 断言 → 唯一命中是本任务新增的 gate 测试（断言**不再**调旧端点）；既有 `j1-e2e-integration.spec.ts` 仅 skeleton placeholder（`expect(true).toBe(true)`，注释描述场景，无旧端点 live 断言）⇒ 无既有测试断言旧端点，无需迁移更新。
    - **发现的偏差/降级**：
      - 🟢 **J1 无 FormData 死代码**（同 E1，与 D/H/K 循环不同）：`useJ1FormData` 不存在（file_search 0），J1 单 `useJ1Adjudication`（承载行模型/持久化/带入，无 TB 回写）+ inline `writebackTB` 承载回写，无 `useJ1FormData.writeback*` 旁路 ⇒ 本任务无「顺手删除零消费 FormData writeback」动作（grep 实证不存在），非遗漏。
      - 🟢 **sheet 名可解**：render label `审定表J1-1` / `wp_code: J1-1` 本身可解，前端传字面量 `审定表J1-1` 更稳，无 R1 不可解降级项。
      - 🟢 **J2 未碰**：按任务范围只改 J1；J2 整模块（`useJ2FormData`/`useJ2Integration` 孤儿链）死代码清理归 task 17（已完成），本任务全程未触碰 J2 文件。
      - 🟡 **gate 测试 flush 说明**：J1 handler 含 `await confirm` + `await import('@/services/apiProxy')` + `await api.post`（动态 import 在 setTimeout 边界解析），单 `nextTick` 不足以让 mockPost 完成 → 测试用 `flush(6)`（交替 `Promise.resolve()` + `setTimeout(0)`）刷微/宏任务队列后断言，非跳过等待。
    - **预存无关失败 git 实证**：`git status` 实证工作树本任务仅 `J1TabAdjudication.vue`(M) + `jAdjudicationPublishGate.spec.ts`(??)；其余 M 文件（useE1/useI*Adjudication + E1/I* TabAdjudication + i6Integration.spec + e/iAdjudicationPublishGate.spec）是 task 13/14 前序已完成产物，非本任务引入。J1/J 回归 269 全绿无预存失败。
    - **端到端验证点 / 待环境**：前端 gate 单测覆盖「确认→publish-to-tb 落库路径（2211 balance 单科目）+ 取消/readonly 无副作用 + 不调旧端点 + 仍 emit」；后端 M0 集成测试覆盖 writeback_rows(balance)→WORKPAPER_SAVED(publish_confirmed)→handler 幂等回写（task 3 M0 已封板）。真实 PG 无 J 循环职工薪酬审定数据 → 端到端 UAT 归 task 20*（data-blocked）；Playwright 全链路归 task 21*（待 start-dev.bat 环境）。本任务代码 + 单测层面已封板。

## M10：收口

- [x] 18. 确认前端零直调 + 加 CI 守卫
  - 全仓 grep 断言 `audit-platform/frontend/src/**` 中 `trial-balance/writeback` 命中数 = 0 **且** `trial_balance` 变体端点（`projects/.../trial_balance` POST，G6）命中数 = 0
  - 加 CI 守卫脚本（断言无新增前端直调，覆盖两种字面量，命中即失败），接入 `governance-checks.yml`
  - 依赖全部活改造(3~15)+死清理(17)完成
  - _需求: 9.1, 9.2_
  - **✅ 完成证据（2026）**：
    - **grep 实证命中数（活代码 HTTP 调用，剥注释/排除测试后）**：
      - 旧端点 `trial-balance/writeback` **活调用 = 0**。收口 grep 发现 **1 处 task 17 遗漏的活直调死代码**（如实报告，未掩盖）：`composables/useH7FormData.ts` 的 `writebackTB()` 内 `api.post('/api/projects/{pid}/trial-balance/writeback')`。定位判定：全仓无 `.vue` 宿主 `import useH7FormData`（H7 真实回写走 `H7TabAdjudicationFair/Cost.vue` 的 `publishToTb`），无任何测试消费 `writebackTB`（`__tests__` 0 引用）——**零消费死代码**，非活路径。按 BP-5「grep 0 调用即删死代码」铁律**移除**（删 `writebackTB` 函数体 + return export + 失效的 `eventBus` import + 头 docstring 更新 + 中文收口注释）。删后活调用归 **0**。
      - G6 变体端点 `projects/.../trial_balance`（POST）**活调用 = 0**（task 17 批C 已清 `useG6MainFormData.writebackTB`）。精准正则 `(api|http|httpApi)\.post[^\n]*/trial_balance[\`'"\s)]` 全仓 0 命中；`trial_balance`（下划线）其余出现全为合法非端点用法（SSE 事件名 `trial_balance.updated` / 查询 DSL `table:'trial_balance'` / SourceType 枚举 / 冻结/快照/balance-check 等 **子**端点 / presence view / 路由 module 名），门禁不误报。
      - **区分实证**：改造后各组件保留描述性收口注释（「此前直调旧端点 PUT trial-balance/writeback…」）+ 测试文件 `expect(...).not.toContain('trial-balance/writeback')` 守卫断言——二者均为合法字面量引用，非活调用。守卫先剥注释再匹配「.put/.post(...URL...)」调用点 + 排除测试文件，故不误报（自测 `test_closure_comment_not_flagged`/`test_jsdoc_closure_comment_not_flagged`/`test_trial_balance_updated_event_not_flagged`/`test_test_files_excluded_from_scan` 覆盖）。
    - **CI 守卫脚本**：`backend/scripts/check/check_tb_writeback_no_direct_call.py`（stdlib-only，秒级）。匹配逻辑：
      - 扫 `audit-platform/frontend/src/**/*.{ts,vue}`，**排除测试**（`__tests__`/`__mocks__` 目录、`*.spec.*`/`*.test.*`/`*.stories.ts`）。
      - **先剥注释再匹配**：逐字符状态机 `strip_comments` 剥掉 `//` 行注释、`/* */` 块注释、`<!-- -->` vue 注释，**保留字符串字面量原样**（端点 URL 在字符串里），且保留行号（回报精确行）。
      - **匹配活调用点而非字面量出现**：legacy 正则 `\.\s*(?:put|post)\s*(?:<...>)?\s*\(\s*[\`'"][^\`'"]*trial-balance/writeback`（任意调用者 api/http/httpApi）；variant 正则 `\.\s*post\s*(?:<...>)?\s*\(\s*[\`'"][^\`'"]*/trial_balance(?=[\`'"])`（`/trial_balance` 作端点末段，紧跟引号，排除 `.updated` 事件名与 `table` 值）。
      - 命中即 exit 1 + 打印 `文件:行 + snippet` + JSON 报告；无命中 exit 0。
    - **governance-checks.yml 接入**：追加 job `tb-writeback-no-direct-call`（5 steps）：checkout → setup-python 3.12 → 跑守卫脚本 → 装 pytest → 跑守卫自测。YAML 已 `yaml.safe_load` 校验通过（job OK / 5 steps / 总 172 jobs）。
    - **守卫自测**：`backend/tests/scripts/test_check_tb_writeback_no_direct_call.py`（24 用例）→ **24 passed / 0 failed**（覆盖 strip_comments 四类注释 + 行号保留 / _is_test_file / scan_file 真拦 legacy+variant + 不误报收口注释/JSDoc/事件名/table 值/freeze 子端点/publish-to-tb 正解端点 / main 集成 clean→0、违规→1、测试文件排除、缺 src 目录 fail-closed）。
    - **守卫 exit 0 证据（真仓库）**：`.venv\Scripts\python.exe backend\scripts\check\check_tb_writeback_no_direct_call.py` → `source_files_scanned:5189 / legacy_endpoint_hits:0 / variant_endpoint_hits:0 / verdict:passed`，EXIT=0。
    - **假直调有效性验证（真能拦）**：临时建 `src/__tmp_tb_guard_probe.ts`（含 1 活 legacy `api.put(...trial-balance/writeback)` + 1 活 variant `api.post(.../trial_balance)` + 1 注释里的字面量）→ 守卫 EXIT=1，精准报出 line 7(legacy)+line 12(variant)**且忽略注释行**（未误报 line 2 注释字面量）→ 验证后删除临时文件（守卫复跑回 EXIT=0）。
    - **无回归**：改动文件 `useH7FormData.ts` ESLint **0 error**（1 warning 为未改的 `loadTbData` 既存 `no-direct-audit-fetch`，非新增）；H7 相关 vitest（`h7BiologicalAssets.integration` + `.e2e` + `hAdjudicationPublishGate`）→ **2 files / 58 passed**。
    - **改的文件（3）**：`audit-platform/frontend/src/components/workpaper/composables/useH7FormData.ts`（删死 writebackTB + eventBus import + docstring + 收口注释）；`backend/scripts/check/check_tb_writeback_no_direct_call.py`（新增守卫）；`backend/tests/scripts/test_check_tb_writeback_no_direct_call.py`（新增自测）；`.github/workflows/governance-checks.yml`（接入 job）。

- [x] 19. 决定旧端点删除 / 降级
  - grep 确认前端零调用且无服务内部合法调用方（S 类走独立 service，不算）后：删除 `writeback_audited_amount` 或降级为仅内部 `publish_confirmed` 调用
  - 后端测试确认删除/降级后无回归
  - _需求: 9.3_
  - **✅ 完成证据（2026）——决策 = (a) 删除**：
    - **目标端点**：`backend/app/routers/trial_balance.py` 的 `@router.put("/writeback")` → `writeback_audited_amount(...)`（`PUT /api/projects/{project_id}/trial-balance/writeback`，D~N 专属组件审定数**绕过显式发布门**的直写旁路：无二次确认/无幂等 token/无 `publish_confirmed`）+ 其 `TBWritebackBody` schema。
    - **grep 调用方实证（三面全 0，删前逐项确认，非臆断）**：
      | 面 | 结论 | 实证 |
      |---|---|---|
      | **前端** `audit-platform/frontend/src/**` | **零活调用** | `trial-balance/writeback` 命中仅剩收口注释（useL1/useF*/useD*/GtK6 等的「此前直调旧端点…已移除」）+ 测试里 `.not.toContain('trial-balance/writeback')` 守卫断言；task 18 CI 守卫 `check_tb_writeback_no_direct_call.py` 锁定（本任务复跑 legacy=0/variant=0/verdict=passed，EXIT=0） |
      | **后端内部** | **零调用方** | 全仓 grep `writeback_audited_amount`：除 `trial_balance.py` 本身，其余全部属 **S 类独立 service** —— `SEstimateTBWritebackService.writeback_audited_amount`（`s_estimate_tb_writeback_service.py` + `s_estimate_calculation.py` 调用）/ `STransactionTBWritebackService.writeback_audited_amount`（`s_transaction_*` 调用）+ 各自 S 类测试。**正交，非本路由端点调用方，全程不碰**。无任何后端 router/service `await` 此 handler 或 HTTP 调此端点 |
      | **测试** | **无端点集成测试** | 无 `client.put(...trial-balance/writeback...)` 命中此路由。后端所有 `trial-balance/writeback` 字面量出现在：①task 18 CI 守卫自测（合成字面量，orthogonal）②`workpaper_sync_*_deletion_plan.json` 冻结迁移清单（其 test_task51/56 扫的是**前端 composable 源码字符串**，非后端路由，orthogonal）③app 运行日志。均非本路由端点的活调用/测试 |
    - **`TBWritebackBody` 唯一使用方实证**：grep 全仓仅 `trial_balance.py` 内被删端点用（且 `from pydantic import BaseModel` 也在删除块内，无孤儿 import）。
    - **决策裁定 (a) 删除**（首选，彻底消除绕过显式门的旁路）：路由端点前端零 + 后端内部零 + 无测试命中 ⇒ 直接删 `@router.put("/writeback")` + handler + `TBWritebackBody` schema + 块内 `BaseModel` import，代以收口注释块（记录删除依据 + Task 19 决策）。**不采 (b) 降级**：无任何暂不能断的合法内部调用方，无需保留收窄。
    - **改的文件（2）**：
      - `backend/app/routers/trial_balance.py`：删端点 handler + `TBWritebackBody` + `pydantic.BaseModel` import（该块唯一用途），换为收口注释（删除决策 + grep 证据摘要 + 迁移去向 publish-to-tb）
      - `backend/app/security/wp_bound_entry_coverage.json`：**外溢发现**——删端点后 coverage ledger 出现该路由的 ghost（`stale_in_ledger`）。**采外科式最小改**（非全量重生成）：仅删该条 http 条目（`app.routers.trial_balance:writeback_audited_amount`，14 行）+ 同步 summary 计数 −1（`entry_total 2350→2349` / `http_total 2335→2334` / `http_non_wp_bound 1494→1493` / `by_family.non_wp_bound 1484→1483` / `by_action.update 116→115` / `by_gate.not_applicable 1516→1515`）。**为何不全量重生成**：committed ledger（2026-08-14 生成）已相对 live app �ative stale 64 条（其他 spec 新增端点），全量重生成会把 63 条无关条目卷入本 commit + 把他 spec 的存量漂移锁进本 spec 基线（违 R8.6）——故只删本 spec 该 1 条，其余存量漂移由各自 spec 承载
    - **后端测试命令 + pass 数（183 passed / 0 failed）**：
      - `..\.venv\Scripts\python.exe -m pytest tests/test_trial_balance.py tests/test_trial_balance_sign_passthrough.py tests/test_s_estimate_tb_writeback.py tests/test_s_transaction_tb_writeback.py tests/test_s_estimate_integration.py tests/test_s_special_transaction_integration.py tests/test_s_estimate_pbt.py tests/test_s_special_transaction_pbt.py tests/test_publish_to_tb_writeback_rows.py tests/test_publish_determination_to_tb.py tests/test_x3_entry_coverage_ledger.py tests/scripts/test_check_tb_writeback_no_direct_call.py -q` → **183 passed**
      - **S 类回写零回归证据**：6 个 S 类测试文件（estimate + transaction 的 unit/integration/pbt）全绿 —— `SEstimateTBWritebackService`/`STransactionTBWritebackService` 全程未触碰，删路由端点不影响 S 类独立 service
      - **publish-to-tb 零回归证据**：`test_publish_to_tb_writeback_rows.py`(12) + `test_publish_determination_to_tb.py`(6) 全绿 —— 显式发布门完好
      - **trial_balance 路由零回归**：`test_trial_balance.py` + `test_trial_balance_sign_passthrough.py` 全绿 —— 同 router 其余端点（get/recalc/balance-check/trace/freeze 等）不受删除影响
      - **X-3 ledger 守卫零回归**：`test_x3_entry_coverage_ledger.py` 全绿 —— ledger 外科编辑后 X-3 切片双向等式仍成立、无 finding 归因 X-3
      - **task 18 CI 守卫自测**：`test_check_tb_writeback_no_direct_call.py`(24) 全绿
    - **coverage drift 守卫状态（漂移中性—改善）**：`check_drift(app, ledger)` total **78→77**（唯一减少项恰是 `stale_in_ledger: 1` = 本 route ghost，删后 `stale_in_ledger=[]`；且 route 不在 `missing_in_ledger`）。剩余 77（64 missing + 1 wp_bound_ungated + 1 fake_pass + 11 native_authz_unaudited）**全部预存**、归各自 spec。ledger `entries_len==summary.entry_total==2349` 内部自洽。
    - **CI 守卫仍 exit 0 证据**：`.venv\Scripts\python.exe backend\scripts\check\check_tb_writeback_no_direct_call.py` → `source_files_scanned:5189 / legacy_endpoint_hits:0 / variant_endpoint_hits:0 / verdict:passed`，**EXIT=0**。
    - **诊断**：`trial_balance.py` `ast.parse` OK + `importlib` import OK + 确认模块无 `writeback_audited_amount`/`TBWritebackBody`；ledger JSON `json.loads` OK。改动文件 0 语法/导入错。
    - **发现的偏差/降级（如实报告）**：
      - 🟡 **外溢到 coverage ledger（非本任务范围内预期，但删端点必然触发）**：删路由 → coverage_guard 双向漂移守卫检出 ghost。已用外科式最小改消解（仅删本 route 条目 + 计数 −1），未卷入全量重生成的 63 条无关漂移。
      - ⚠️ **预存无关红（非本任务引入，删前 HEAD 已实证）**：全仓两个 whole-app `is_clean()` 守卫 `test_task16_coverage_guard.py::test_no_drift_on_committed_ledger` + `test_task4_native_authz_audit.py::TestDriftGuard::test_committed_ledger_clean_no_unaudited` 在**原始 HEAD**（stash 掉我的两处改动后）即 2 failed —— 根因 = committed ledger 相对 live app 已 stale 64 条（其他 spec 新增端点 missing_in_ledger + native_authz_unaudited）。本任务**不承接**该存量全量 resync（会锁他 spec 漂移进本 spec 基线），属他 spec/独立 ledger 维护范畴。本任务改动使这两守卫的 finding 各 −1（移除本 route ghost），**未使其更差**。
      - 🟢 **S 类正交**：`SEstimateTBWritebackService`/`STransactionTBWritebackService.writeback_audited_amount` 全程未碰，6 S 类测试全绿佐证。
    - **未 commit**（用户统一提交）。

## 可选任务（外部依赖 / 真实数据）

- [x] 20.* 各循环真实项目端到端 UAT（data-blocked 降级）
  - 真实 PG 仅 5 个 standalone 项目、多数循环无对应审定表真实数据 → 对无数据循环标 `data-blocked`，降级为隔离项目/合成数据（复用 `seed_consol_uat.py` 式最小合成集）跑端点+handler 集成；真实项目补测点标"代码已改但真实项目未实测"
  - 切换点：待 live PG 有对应循环审定数据后逐组件回填
  - _需求: 全部（真实环境验证）_
  - **✅ 完成证据（2026，降级路径做实 + 真实项目补测点如实标 data-blocked）**：
    - **① 真实环境探测结果**：
      - PG **可用**：`docker ps` 实证 `audit-postgres`(pgvector:pg16, 5432) `Up 6 hours (healthy)`；`settings.DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform`；`SELECT 1` + admin 用户探测通过（admin id=b6f8e8d0-…, role=admin，handler 权限门可验证）。
      - 真实项目 **有 TB 数据但无审定表真实发布数据**：`trial_balance` 按 project 聚合——重药控股安徽(0ec33ac9) 196 行 / 4 家重庆医药子公司 171~174 行 / 首汽租车(df5b8403) 166 行等，`audited_amount` 均已填（历史静态数据，非经本 spec publish-to-tb 门产生）。**关键 data-block**：真实项目**无「经显式发布门产生的、可断言的审定表→TB 回写事件流」**——真实 audited 是既有静态值，无法在不污染真实金额前提下断言"发布前=X→发布后=Y"。故真实项目端到端 UAT 对**所有循环**标 `data-blocked`（不可在真实项目上跑破坏性发布断言，铁律：绝不碰真实金额）。
      - 既有隔离 E2E 项目：`E2E-D4发布测试项目_请勿动_2099`(d4e2e000, year=2099, 2 TB 行) 已存在（`test_d4_publish_e2e_live.py` 用，仅 D4-1 balance 三分量，需运行中 9980 后端）。
    - **② 降级路径说明（核心交付）**：新增**真实 DB、进程内**端到端集成测试 `backend/tests/test_publish_to_tb_synthetic_e2e_chain.py`，用**隔离合成项目**（固定 UUID `2b0e2098-…-002098`, audit_year=**2098** 与真实 2024/2025 及 D4 e2e 的 2099 均不撞, company_code=SYN20）幂等 seed（复用 `seed_d4_publish_e2e.py` 式最小合成集：projects + trial_balance + wp_index + working_paper），真实跑通完整链路：
        **真端点函数 `publish_determination_to_tb`（真 DB session + admin）→ 捕获其发出的 `WORKPAPER_SAVED` EventPayload → 真 handler `_on_d_audit_determination_saved` 消费 → 断言 `trial_balance.audited_amount` 真被更新（真实落库，非 mock）**。
      - 非 mock 空转实证：seed 造真实 TB 行（audited 初值 0）→ 发布 → handler 真写 PG → 查询 PG 断言 audited==合成期望值 + `tb_publish_ack` 恰一条；测试后 `_purge` 清库，**实证 purge 后 proj/tb/wp/ack 全 0**（无真实数据污染）。
      - 跨 loop 陷阱规避：每个 test 完整场景（reset+发布+handler+断言）在**单一 asyncio.run**内跑完，并把 handler 的 `async_session_factory` monkeypatch 为**本 loop 内 NullPool 工厂**——否则 handler 复用 app 共享池（绑已关闭 loop）报 `Event loop is closed`（首版即踩此坑，已修）。
      - **合成数据集成测试覆盖矩阵（口径类别 × 验证要点）**：

        | 口径类别 | 代表 wp_code（科目） | ①audited 落库 | ④occurrence 透传 | ⑤多科目全落 |
        |---|---|---|---|---|
        | balance 单科目 | D2-1(1122)、J1-1(2211) | ✅ | — | — |
        | balance 多科目 | E1-1(1001/1002/1012)、K1-1(1221/1231含负数)、H9-1(2701/2801含负数) | ✅ | — | ✅ |
        | occurrence 发生额 | F5-1(6401)、K8-1(6601)、N5-1(6801)、G11-1(1511) | ✅ | ✅(amount_kinds[c]=="occurrence") | — |

        独立验证要点：②同 publish_token 重放（篡改哨兵 999→二次发布不改回，ack 仍 1）✅；③普通保存（无 publish_confirmed）→ handler no-op TB 不变 ✅；补充非审定表 wp_code(D2-2) → handler return TB 不变 ✅。
      - **代表覆盖说明**：端点(`extract_determination_wp_code` + writeback_rows/三分量路径) 与 handler(`^[D-N]\d+-1$` + `publish_confirmed` 门 + `tb_publish_ack` 幂等 + 按 `standard_account_code` UPDATE audited_amount) 对**所有 D~N 循环同构**（handler 直读 `audited_amount`，balance/occurrence 落库口径一致，仅语义标注不同）；故按**口径类别**取代表覆盖（balance 单/多 + occurrence）即充分验证全循环链路，不逐 30+ 组件重复。
    - **③ 现有测试已覆盖 vs 本任务新补的缺口（不重复造）**：
      - 已覆盖（未重造）：`test_publish_to_tb_writeback_rows.py`(M0/12) 端点级**mock DB**入参契约（writeback_rows 优先/occurrence 透传/多科目/三分量零回归/400×3/幂等 token 合成/角色 403）；`test_cycle_linkage_handlers_integration.py` handler 级**mock session**（捕获 SQL 不落库，验 publish_confirmed 门/非审定表 return/空 rows/权限）；`test_d4_publish_e2e_live.py` **真 HTTP+真 PG** 但仅 D4-1 balance 三分量、需运行中 9980。
      - **本任务补的缺口**：真实 DB + 进程内（无需运行 HTTP 后端，更易 CI/离线跑）驱动**端点→事件→handler→真 TB 落库**的完整链路，且覆盖 **writeback_rows 预算行路径**（既有 live 只覆盖三分量）+ **occurrence 口径真实落库**（既有 live 无）+ **balance 多科目/负数真实落库** + 幂等真实不双写 + 普通保存真实 no-op，跨 9 个循环口径代表。填补"mock 不落库 + live 仅 D4 balance 三分量"之间的真实多循环落库验证空白。
    - **④ 测试命令 + pass 数**：
      - 新测试：`rtk ..\.venv\Scripts\python.exe -m pytest tests/test_publish_to_tb_synthetic_e2e_chain.py -q` → **12 passed / 0 failed**（9 参数化落库 + 幂等 + 普通保存 no-op + 非审定表 no-op）。
      - 零回归批次：`... test_publish_to_tb_synthetic_e2e_chain.py test_publish_to_tb_writeback_rows.py test_publish_determination_to_tb.py test_cycle_linkage_handlers_integration.py -q` → **52 passed / 0 failed**（新 12 + M0 12 + publish_determination 6 + handler integration 22）。第二次跑新文件再次幂等 seed 并通过，无回归。
      - purge 实证：跑后 `SELECT count(*) FROM projects/trial_balance/working_paper/tb_publish_ack WHERE project_id=2b0e2098-…` 全 **0**（隔离数据无残留）。
    - **⑤ data-blocked 循环清单 + 切换点**：**全部 D~N 循环的「真实项目」端到端 UAT 标 `data-blocked`**（代码已改但真实项目未实测）——真实 PG 5 个 standalone 项目的 audited 是既有静态数据，无「经 publish-to-tb 门的可断言发布事件流」，且铁律禁在真实项目上跑破坏性发布断言。
      - **降级已做实**：上述 9 循环口径代表已在隔离合成项目跑通真实 DB 端到端落库（非 mock），链路正确性已验证。
      - **切换点（待 live PG 有对应循环审定数据后逐组件回填）**：待某真实项目出现「经显式发布门产生的审定表发布事件」时，可在该项目上（或对该项目造只读快照对照）逐循环回填真实项目 UAT——(a) 起 `start-dev.bat`(9980) 后用 `test_d4_publish_e2e_live.py` 范式扩到该循环的 wp_id/sheet_name；或 (b) 用本文件 `_publish_via_endpoint`+`_run_handler` 进程内范式指向真实 wp_id（**须先确认可安全 reset/复位该项目审定表 TB，否则维持隔离合成**）。Playwright 全链路（确认对话框→UI→报表读到新 audited）归 task 21*（待 start-dev.bat 环境）。
    - **偏差/降级如实标注**：本任务**未**在真实项目上跑发布断言（铁律：不碰真实金额）——真实项目 UAT 维持 data-blocked，以隔离合成项目做实降级路径；这是"绝不假绿"下对外部依赖任务的正确处置（合成集成测试真实跑通 = 链路已验证；真实项目补测点如实标 data-blocked + 列切换点，不粉饰）。

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
