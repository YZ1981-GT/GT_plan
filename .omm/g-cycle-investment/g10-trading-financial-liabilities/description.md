# G10 交易性金融负债（2101）

componentType `g10-trading-financial-liabilities`，主入口 `GtG10TradingFinancialLiabilities.vue`。
与 G1（交易性金融资产）镜像：**一个底稿覆盖两个附注节**（交易性金融负债 + 衍生金融负债）。

## 子目录

| 目录 | 内容 |
|---|---|
| `core/` | 审定 / 明细 / 调整 / 披露上市 / 披露国企 |
| `classification/` | 分类与指定 FVTPL 的理由 |
| `voucher/` | 凭证检查 |
| `handbooks/` + 四件套 | 手册 / 审计文本卡片 / 导入导出 ▾ |

`g10Constants`：`G10_ACCOUNT_CODE='2101'`、`G10_ACCOUNT_NAME='交易性金融负债'`（TB 按名称回退匹配）。

## 附注结构（4 张表）

`g10NoteSectionMap`：listed `{trading:'五、34', derivative:'五、35'}` / soe `{trading:'八、34', derivative:'八、35'}`

上市版四张子表：
1. 交易性金融负债变动（项目/期初/本期增加/本期减少/期末）
2. 指定为 FVTPL 的负债（项目/期初/期末/指定理由）
3. **公允价值变动中信用风险部分**（表名含动态年份 `listedFvCreditTableName(year)`）
4. 衍生金融负债

国企版为期末/期初公允价值两列。列头统一取 `G10_DISCLOSURE_COL_LABELS`（与源模板同步），
`buildG10SyncPayload` 的 columns 键必须用**同一批动态表名函数**（表名函数在纯函数体内引用常量，无 TDZ 问题）。

## 关键机制

- 公允变动 → `6101 公允价值变动损益`（`useG10Adjustment` 自动生成对方行）
- 审定回写 TB 2101；`substantive:adjudicated` 联动披露与附注
- 正向跳转靠精确章节号（五、34 / 五、35）区分两节；反向跳转 map 用节级 key

## 与其他元素的关系

- 与 G1 是资产/负债镜像，衍生工具核查方法学一致
- 公允变动 → G13 公允价值变动收益（6101）
- 套期用途的衍生 → G12 净敞口套期收益（6103）
