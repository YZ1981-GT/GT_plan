# G11 / G12 / G13 / G14 投资相关损益四科目

四个都是**损益类（取发生额）**，是 G 循环资产侧的"出口"。

| 元素 | 科目 | componentType | 附注（上市 / 国企） | 阈值 |
|---|---|---|---|---|
| G11 投资收益 | 6111 | `g11-investment-income` | 五、69 / 八、70 | 变动率 0.2；收益率变动 0.05 |
| G12 净敞口套期收益 | 6103 | `g12-net-hedge-gains` | 五、70 / 八、71 | 变动率 0.2 |
| G13 公允价值变动收益 | 6101 | `g13-fair-value-changes` | 三、公允价值变动收益 / 八、72 | 变动率 0.3 |
| G14 信用减值损失 | 6702 | `g14-credit-impairment-loss` | 三、信用减值损失 / 八、73 | 变动率 0.3 |

## 结构差异

- **G11**：`core/` + `analysis/`（收益率分析）+ `voucher/` + `handbooks/`，后端有独立 service / validate / ai / import-export
  （`_g11_investment_income{,_service,_validate,_ai,_import_export}.py` + `_g11_disclosure_io.py`）——G 循环后端最重的一包
- **G12**：`core/` + `hedging/`（套期关系、有效性评价）+ `shared/` + `voucher/`；
  后端 `_g12_net_hedge_gains{,_ai,_import_export}.py`
- **G13 / G14**：**扁平单目录**（`G{n}TabAdjudication` / `Adjustment` / `Detail` / `Directory` / `DisclosureListed` / `DisclosureSOE` / `Procedure` + `handbooks/`）——
  它们是"汇总性损益科目"，数据主要来自上游各资产底稿

## 上游来源（这四科目的数据从哪来）

- **G11 投资收益**：G1 处置/股利/利息、G4/G6 利息与处置、G7 权益法收益、G6 处置 OCI 转入
- **G13 公允价值变动收益**：G1 / G9 / G10 的公允变动
- **G14 信用减值损失**：G4-ECL / G6-ECL / G5 三阶段减值（**信用类**；长投/固资等非信用减值走 K11 资产减值损失 6701）
- **G12 净敞口套期收益**：套期工具与被套期项目的公允变动净额（CAS24），处置结转对方科目 `4104 利润分配—未分配利润`

## 附注要点

- G13/G14 上市版章节是**关键词标题**（`三、公允价值变动收益` / `三、信用减值损失`），
  DB 中标题可能被截断 → `?section=` 定位需 `resolveSectionInList` 模糊→精确解析
- G13/G14 已有正向 + 反向跳转 + `buildG13/G14SyncPayload` columns（项目/本期/上期/备注），已登记覆盖率守卫
- G11 附注含上市版处置明细项目表
- **G14 曾有的坑**：listed 附注 `note_section` 实际带括号（`三、信用减值损失（损…`），
  而 `sync_from_workpaper` 精确匹配 clean 章节名会漏掉既有 note → **静默创建重复 note**（平台 latent bug，需模糊解析）

## 与 K11 的边界

**信用减值损失（G14 / 6702）≠ 资产减值损失（K11 / 6701）**：
金融资产 ECL 走 G14，存货/固资/长投/无形/商誉等非金融资产减值走 K11。混淆会导致报表行错位。
