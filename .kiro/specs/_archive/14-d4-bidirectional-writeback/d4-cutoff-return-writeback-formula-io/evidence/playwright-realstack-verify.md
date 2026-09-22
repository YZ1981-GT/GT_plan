# D4-16 / D4-17 真栈 Playwright 验证证据（2026-09-19）

> 环境：真实后端 9980（healthy，PG+Redis ok，migration 163，drift 0）+ 前端 3030 + OnlyOffice healthy。
> 真实项目：重庆和平药房连锁有限责任公司_2024（project `f064f5e4…`，D4 workbook wp `51b66517…`）。
> 全程 0 console error。测试数据已清理（真实项目零残留，见末尾）。

## D4-16 出口收入电子口岸核对 —— 派生列重算 + A13 全链路

**渲染**：两级表头（账面出口收入金额 / 电子口岸系统[期间/结关金额/差异/原因/索引] / 免抵退税申报数据[…]），编制信息带出真实被审计单位名，0 error。

**派生列单源重算（精确读 DOM）**：录入 账面=100000 / 口岸结关=98000 / 申报外营收入=95000 后：
- 账面出口收入合计 = **100,000.00**
- 口岸系统差异合计 = **2,000.00** = 100000 − 98000 ✓（portsDiff 前端重算）
- 免抵退税差异合计 = **5,000.00** = 100000 − 95000 ✓（taxDiff 前端重算）
- 行内差异单元格 diff-warn = 2,000.00 / 5,000.00 ✓
- 「推送差异至 A13」按钮：无差异时 disabled → 有差异后 **enabled**（hasDiff 门控正确）

**A13 全链路（emit → bridge → POST → DB）**：点击推送后：
- ElMessage 两条：`已推送 1 项至 A13 错报汇总，并同步至 D4-1 审计说明`（useD4InspectionWriteback）+ `已记入未更正错报汇总 1 笔`（useA13MisstatementBridge，仅 ok>0 显示 = 后端 POST 成功）
- DB `unadjusted_misstatements` 实证写入：`source_wp_code=D4-16` / `description=第1行：口岸差异2000，免抵退税差异5000（索引:D4-16）` / `amount=7000.00`(=|2000|+|5000|) / `type=factual` / `account=6001 营业收入`

## D4-17 截止测试（账到单据）—— isCrossPeriodForward 公式收敛

**渲染**：两级表头（记账凭证/发货单/跨期/备注），0 error。「推送跨期至 A13」按钮 cutoffIssues=0 时 disabled。

**跨期公式引擎单源（真栈）**：录入 凭证日期=2025-12-20（期内）+ 发货单日期=2026-01-05（期后，cutoff 默认 2025-12-31）：
- 跨期列渲染 **`×`** = isCutoff=false = `!isCrossPeriodForward(2025-12-20, 2026-01-05, 2025-12-31)` = `!true` ✓（内联 checkCutoff 已收敛为引擎函数，浏览器实证生效）
- 「推送跨期至 A13」按钮从 disabled → **enabled**（cutoffIssues 0→1）

## 🔴 真栈实测印证的已知缺口（B3 durable ack）

D4-16 推送点击两次（间隔 48 秒）→ DB 产生 **2 条重复错报**。根因：`useA13MisstatementBridge` 的 `recentHashes` 去重窗口仅 5000ms（内存 Map，跨窗口/刷新失效）。这与 spec 登记的 **B3 [blocked] durable ack**（无持久 ack/重试/跨会话幂等）完全一致 —— 真栈实测证明该缺口真实存在，非臆想。属平台级基础设施待建，非本 spec 范围。

## 测试数据清理

真栈验证在真实项目留下的污染已全部清除（临时脚本用完即删）：
- `unadjusted_misstatements` source_wp_code=D4-16 的 2 条测试错报 → deleted 2，复查 count=0
- `checklist_responses` D4-16-rows / D4-17-rows 测试行 → deleted，复查 []
- `D4-1-adj-note` 追加的测试行 → cleaned，复查 remark=''

## 结论

D4-16 派生列重算 + A13 全链路（前端→事件桥→后端 POST→DB 落库）+ D4-17 跨期公式引擎收敛，**均真栈闭环验证通过**。本轮做实的「公式单源 + A13 人工认定链」从「代码绿」升级为「浏览器绿 + DB 绿」。durable ack 缺口经真栈实测印证，如实归 B3 blocked。
