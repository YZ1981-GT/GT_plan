# G1 交易性金融资产（`G1_ACCOUNT_CODE='1501'` ⚠ 见 concern）

componentType `g1-trading-financial-assets`，主入口 `GtG1TradingFinancialAssets.vue`，
后端 `_g1_trading_financial_assets.py`。**一个底稿覆盖两个附注节**（交易性 + 衍生）。

## 子目录（`g1-trading-financial-assets/`）

| 目录/组件 | 内容 |
|---|---|
| `core/` | 审定表 / 明细 / 调整分录 / 附注上市 / 附注国企 |
| `classification/` | G1-8 业务模式、G1-9 分类、G1-10 SPPI（分类三步曲，可互相带入） |
| `valuation/` | G1-6 公允价值测试、G1-7 Level 3 估值调节 |
| `inspection/` | G1-4 结存检查、G1-5 收益测算、G1-11 监盘、G1-12 盘点倒轧、G1-13 凭证检查、G1-14 衍生工具核查 |
| `handbooks/` + `G1PreparationHandbookDialog` | 编制/使用手册 |
| `G1AuditTextCards` / `G1SheetStatusBar` / `G1ImportExportDropdown` | 审计文本卡片 / 状态条 / 导入导出 ▾ |

## 关键机制

- **TB 全局勾稽告警**：审定合计 ↔ TB 差异 >1 元 warning（非审定表 tab 时也显示）
- **分类三步曲联动**：G1-8 业务模式 → 建议分类；G1-10 SPPI → 带入 G1-9；G1-9 联合写入结论
- **公允层次（CAS39）**：`fvHierarchyRows`（Level 1/2/3 + 估值技术 + 关键输入值 + 可观察性），
  可从 G1-8 带入并与公允价值表期末勾稽
- **衍生工具合同 OCR**：`POST /api/workpapers/{wp_id}/g1/contract-ocr` 识别 8 类影响变量（利率/汇率/商品价格/指数/信用等级…），
  **只置"是"不覆盖人工"否"**，需人工复核
- **附注**：`g1NoteSectionMap` 五、2 交易性 / 五、3 衍生（八、2 / 八、3），
  `buildG1SyncPayload` 按 variant 附 columns；listed 行键是中文键、soe 是英文键 → columns 必须显式映射中文列头
- **收益勾稽**：G1 利息 + 股利 + 处置 ↔ G11 投资收益审定（`g1G11IncomePull`），差异提示权益法/债务重组等原因

## 与其他元素的关系

- 公允变动 → G13（6101）；投资收益 → G11（6111）
- 分类结论与 G4/G6 的 SPPI 判定同一准则依据（CAS22）
