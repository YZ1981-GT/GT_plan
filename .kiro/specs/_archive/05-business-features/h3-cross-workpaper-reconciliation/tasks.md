# Implementation Plan: H3 Cross-Workpaper Reconciliation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "W0", "tasks": ["1"] },
    { "id": "W1", "tasks": ["2", "3"] },
    { "id": "W2", "tasks": ["4", "5"] },
    { "id": "W3", "tasks": ["6", "7"] },
    { "id": "W4", "tasks": ["8", "9"] }
  ]
}
```

## Tasks

- [x] 1. 后端 tb_6051_audited 注入：`_h3_investment_property.py::_load_project_context` 新增 `tb_6051_audited`（`SELECT SUM(audited_amount) FROM trial_balance WHERE standard_account_code LIKE '6051%'`），查询失败返 null。验证 AST parse OK + render smoke 零回归。
- [x] 2. h3TransferReconcile.ts 纯函数：新建 `composables/h3TransferReconcile.ts`（pullH1TransferForH3 + pullH2TransferForH3 + buildH3TransferReconcile），try/catch fail-open。
- [x] 3. h3TransferReconcile.spec.ts 单测：P1(fromH1差额) P2(fromH2差额) P3(toH1差额) P6(pull失败) P7(空数据)，5+ 用例全绿。
- [x] 4. H3-6 互转审核表勾稽面板 UI：`H3TabTransferReview.vue` 底部新增 el-card 勾稽面板（三行表格+状态tag+GtIndexChip H1/H2+pull按钮+失败降级手工输入）。get_diagnostics 清+Vite 200。
- [x] 5. H3-14 租金勾稽面板 UI + 单测：H3-14 已有完整 TB 6051 勾稽面板（plReconcile/d43Reconcile/refreshTbReconcile），无需重复；h3RentalReconcile.spec.ts(P4/P8) 6测全绿。
- [x] 6. h3MortgageReconcile.ts 纯函数：新建 `composables/h3MortgageReconcile.ts`（pullL1PledgeForH3 + pullL3PledgeForH3 + buildH3MortgageReconcile），try/catch fail-open。
- [x] 7. h3MortgageReconcile.spec.ts 单测：P5(抵押差额) P6(pull失败) P7(空数据)，4+ 用例全绿。
- [x] 8. H3-12 产权核对表抵押勾稽面板 UI：`H3TabTitleCheck.vue` 底部新增 el-card 抵押勾稽面板（H3已抵押合计 vs L1+L3+差异+状态tag+GtIndexChip L1/L3+pull按钮+失败降级）。get_diagnostics 清+Vite 200。
- [x] 9. 全量回归门+Playwright*：全部改动文件 diagnostics 全清+Vite 200；h3TransferReconcile+h3MortgageReconcile+h3RentalReconcile spec 20测全绿；Playwright 需实例化项目（可选，留待）。

## Notes

- 复用范式：h1CipH2Pull/h2H1TransferPull/h2L1LoanPull
- 无后端新表/迁移（纯前端 pull + 后端 additive project_context 字段）
- 容差统一1元
- EventBus 联动天然覆盖（H3 主入口已订阅）
