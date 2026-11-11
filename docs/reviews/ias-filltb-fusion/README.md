# IAS / FillTb 离线审阅交付

目录版本：`707d2e9c5f557e3f165b969be150f466b837bd01ae0206c5e5e95b2cc3b1c8e2`。平台源码静态快照，不是项目有效规则或运行包。

## 重生成
```powershell
python docs/reviews/ias-filltb-fusion/generate_review.py
python docs/reviews/ias-filltb-fusion/generate_review.py --replay
python docs/reviews/ias-filltb-fusion/verify_delivery.py
```
普通模式重读本地来源；--replay 只用平台快照、人工摘要与定位摘要。人工摘要未经改写。原件消失后不再证明原文，保留原文件hash与当时的核验定位。
同内容比较实际二进制后跳过写入；丢失或被改的输出必重建。ZIP时间与工作簿属性固定以保证可重现，不是来源修改时间。每次逐格读回并连跑两次核对hash和mtime。

## 边界与数量
所列平台JSON完整保存于 sources/platform；catalog.json 保留原payload、source hash、payload hash、稳定ID和逐边关系。IAS 18条行为、20字段；FillTb 20个码+5列位。字段/码与公式按文本，不执行表达式。
四口径各自计边，不等于报表行数；一对多页可能同时包含多对一，边数不等于唯一科目数。未知外部准则不广播为平台四套已适用。平台已有不等于映射正确或已部署。
缺口编码为空；1523/1524都保留；其他综合3102↔M9的4003、专项储备M7的4301↔chart研发支出、盈余3101↔M5的4101均明示冲突。
审批字段为空，所有外部候选未确认；未查库、未运行外部SQL、未读取凭据、未改spec/INDEX。许可尚未核实；本轮仅保留最小必要事实供人工审阅，不推定取得转换或分发授权；导入及运行接入均未实施。
IAS行为属于报告取数/配对语义，使用report_line命名空间并以record_kind区分；科目码缺失绝不由报表字段Code推造。校对来源登记仅静态读取12项登记与内置7条种子，不调用加载器、不伪称数据库规则全量。

## 本次现算
```json
{
  "standard_accounts": 174,
  "report_dimensions": {
    "soe_standalone": 154,
    "soe_consolidated": 154,
    "listed_standalone": 154,
    "listed_consolidated": 154
  },
  "report_rows": 1191,
  "workpaper_mappings": 1025,
  "push_rules": 268,
  "push_kinds": {
    "four_table_leaves": 2,
    "formula": 87,
    "derivation": 179
  },
  "import_fields": 30,
  "import_aliases": 102,
  "tb_formula_columns": 14,
  "ias_behaviors": 18,
  "ias_fields": 20,
  "filltb_codes": 20,
  "filltb_positions": 5,
  "report_codes_absent_from_chart": [
    "1409",
    "1416",
    "1452",
    "1525",
    "1526",
    "1527",
    "1532",
    "1651",
    "1652",
    "1653",
    "1704",
    "1922",
    "2102",
    "2651",
    "5002",
    "5101",
    "5802"
  ],
  "report_code_gap_count": 17
}
```

## 工作表与计数

### 规则目录_审阅稿.xlsx（24页）
| 工作表 | 数据行数 |
| --- | ---: |
| 阅读说明 | 11 |
| 三方差异与融合 | 14 |
| 平台取数行为 | 13 |
| 多级表头映射 | 30 |
| 审阅总览 | 15 |
| 平台导入别名 | 30 |
| 平台表识别 | 7 |
| 平台标准科目 | 174 |
| 平台报表行 | 1191 |
| 平台科目报表映射 | 616 |
| 平台底稿附注 | 1025 |
| 平台推送规则 | 268 |
| 平台公式TB词表 | 14 |
| IAS可见规则 | 18 |
| IAS字段语义 | 20 |
| IAS材料缺口 | 4 |
| FillTb精选编码 | 20 |
| FillTb导入列位 | 5 |
| 差异融合与待确认 | 17 |
| 平台内部冲突 | 6 |
| 校对来源登记 | 12 |
| 报表校对种子 | 7 |
| 来源清单 | 20 |
| 字段字典 | 69 |

### 编码对照表_审阅稿.xlsx（20页）
| 工作表 | 数据行数 |
| --- | ---: |
| 阅读说明 | 11 |
| 三方差异与融合 | 14 |
| 差异融合总览 | 15 |
| 平台科目基线 | 174 |
| 国企单体 | 154 |
| 国企合并 | 154 |
| 上市单体 | 154 |
| 上市合并 | 154 |
| IAS候选与缺口 | 24 |
| FillTb关键候选 | 75 |
| FillTb导入列位 | 5 |
| 一对多关系 | 1944 |
| 冲突孤儿与待确认 | 552 |
| 平台内部冲突 | 6 |
| 标准码差集 | 17 |
| 底稿科目与附注关系 | 1147 |
| 推送目标关系 | 268 |
| 全部关系 | 2134 |
| 来源清单 | 20 |
| 字段字典 | 69 |

字段字典说明三维状态；来源清单逐项说明hash、路径、commit与许可。原JSON Pointer可随排序改变，稳定ID不含数组位置；来源删除保留退役记录，不自动沿用审批。
人工审批尚未发生；本工具不提供批准或发布入口。

## 最终版本核验
- 本版为规则目录24页、编码对照20页；建议先阅读两本工作簿的“阅读说明”“三方差异与融合”“平台内部冲突”。
- 直接复核：`python -B docs/reviews/ias-filltb-fusion/verify_readback.py`，结果见 `final_validation.json`；已完成来源hash、快照重算、工作簿逐格/类型/状态核验，无公式执行、外部链接或宏。
- `validation_report.json`记录生成器本版逐格读回及重复生成hash/mtime不变。`verify_delivery.py`完整多轮重建曾在300秒超时，不能用旧版本报告声称本版全套通过；旧报告已移除。
- A 与0规格位于 `.kiro/specs/ias-filltb-import-compatibility/` 和 `.kiro/specs/ias-filltb-rule-catalog-crosswalk/`，索引仅新增两行；没有修改产品代码、运行导入、提交或推送。
