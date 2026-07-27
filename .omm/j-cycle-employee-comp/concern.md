# 关注点 / 已知脆弱处（J 循环）

## 1. J1 曾经的一批真实缺陷（勿回退）

- **审定表编辑不落库**：`onCellChange` 只改内存、`saveAuditNote` 只赋值 ref → 编辑/说明/结论刷新全丢
  （现 `useJ1Adjudication` 带持久化 + 派生跨表键 `J1-1-audited-total` / `J1-1-audited-begin-total`）
- **后端 `_extract_json` 读不存在的 `content` 列**（应读 `remark`）→ render 输出的 8 个 `*_rows` 恒空
- **变动列字段漂移**：模板读 `unadjVsPriorDiff/Rate` + `auditedVsPriorDiff/Rate`，composable 只算
  `changeDiff/changeRate` → 四列恒 undefined、30% 标红从不触发
- **两张披露表 onMounted 只有 `// TODO`**（完全不落库）
- **导入导出三处死链**：后端 4 处 `INSERT checklist_responses` 漏 `project_id`（NOT NULL → 恒 500）；
  `SHEET_TYPES` 缺 `adjustment`（J1-3 点导入导出恒 400）；
  **前端把 `sheet_type` 塞 FormData 而后端是 `Query`** → 每次导入都按 `detail` 解析（从 J1-6/J1-7 导入被当明细表）
- **A13 推送 404**：曾调不存在的 `POST /workpapers/{id}/push-to-a13`，现改 `eventBus.emit('a13:push-misstatement')`

## 2. 🔴 JSDoc 里的 `*/` 会提前闭合块注释

在注释里写 `unadjVsPrior*/auditedVsPrior*` 之类字符串 → esbuild `Unexpected "*"`。
**`get_diagnostics` 查不出，唯 Vite transform 500 暴露**（L1 也踩过同一个坑，J1 是第二次）。

## 3. 循环 IE 的 `sheet_type` 是 Query 不是 Form

前端必须走 `params` 传 `sheet_type` / `sheet`，塞进 FormData 后端收不到 → 用默认值解析错表
（这是"导入提示成功但数据进错表"的典型根因）。

## 4. J2/J3 曾有 `import { http }` 命名导入崩溃

`@/utils/http` 只有 `export default`，`import { http }` 是**运行时 ESM 加载错**
（Vite transform 200、get_diagnostics 全清都查不出，只有打开该 tab 才崩）。
J2 5 个 composable + J3 6 个文件曾全中招。

## 5. J1 分配检查的 counterpart 填充率问题

`tb_ledger.counterpart_account` 在部分账套填充率很低 → 按对方科目归集会漏；
`unattributedAmount` 必须如实提示，**不能把无法归属的金额强行分摊**（与 H1 折旧归属同一类问题）。

## 6. J2 的 CAS9 六要素表列语义容易做错

- 国企版是**单张合并表**（义务现值 | 计划资产 | 净负债三组并列，各含本期/上期共 6 数值列），
  上市版是**3 张独立表** → 按 variant 只换 label 硬套会错
- **计划资产列部分单元格不适用显 "—"**（当期服务/过去服务/结算利得/精算利得），不能填 0
- 期末余额 = 期初 + 二(当期损益) + 三(OCI) **−** 四(其他变动)（源模板公式，注意减号）

## 7. J3 现金结算需每期重新计量

权益结算在授予日确定公允价值后不再调整；**现金结算每个资产负债表日重新计量负债公允价值**。
引导弹窗的实时分析面板会给警告，但金额仍需人工。倒签风险（授予日 vs 行权日间隔异常）也只是提示。

## 8. J1/J2/J3 的目录跳转链

J1 主入口 `provide('jumpToSection')` → 子组件 inject；J2 曾**缺 provide** 导致目录点击无反应（已补）；
J3 经 `@navigate-sheet` emit 链。加新 sheet 时三条链都要接。
