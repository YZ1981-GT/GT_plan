# 公式位命名规范（Formula Slot Key Specification）

> spec: `unified-formula-registry` · R3 公式位命名规范化

## 概述

平台 6 个公式域各有一套公式位标识（slot_key），本文档定义统一的命名格式、与 ACNR 地址坐标的映射关系、以及命名约束。

## 各域格式

| 域 | slot_key 格式 | 示例 | 分隔符 | addr_id 映射 |
|---|---|---|---|---|
| report | `{report_type}:{row_code}` | `balance_sheet:BS-002` | `:` | `report:balance_sheet:BS-002` |
| wp | `{wp_code}\|{sheet}\|{cell}` | `D2\|审定表D2-1\|E100` | `\|` | `wp:D2/审定表D2-1/E100` |
| note | `{section}\|{target}` | `五、1\|应收账款:value` | `\|` | `note:五、1`（章节级） |
| cross_check | `{node_key}#{rule_id}` | `report_balance_sheet#00001` | `#` | `cross_check:report_balance_sheet#00001` |
| tb_detail | `{account}\|{label}` | `1001\|月度明细` | `\|` | `tb_detail:1001\|月度明细` |
| consol_note | `{section}\|{row}\|{col}` | `五、1\|2\|3` | `\|` | `consol_note:五、1\|2\|3` |

## addr_id 转换规则

- **report 域**：`report:` 前缀 + slot_key 原样（slot_key 本身已含 report_type）
- **wp 域**：`wp:` 前缀 + `|` 替换为 `/`（与 ACNR 的 `wp:{code}/{sheet}/{cell}` 一致）
- **note 域**：`note:` 前缀 + slot_key 的第一段（章节码），因为同一章节的多个公式位共享一个 addr_id
- **其余域**：`{domain}:` 前缀 + slot_key 原样

## 命名约束

- slot_key 最大长度：300 字符
- 域名（domain）限 `report` / `wp` / `note` / `cross_check` / `tb_detail` / `consol_note`
- 分隔符不得出现在各段的值中（report 的 `:` / wp/note/tb_detail/consol_note 的 `|` / cross_check 的 `#`）
- 行次编码（row_code）格式：`{报表前缀}-{三位数字}`（如 `BS-002`、`IS-055`）
- 科目编码：纯数字（如 `1001`、`222102`），长度 4~6 位

## 用于依赖分析的特殊地址

- `tb:{account_code}` — 试算表科目（不归属任何公式域，是 TB() 函数的取数目标）
- `adj:{account_code}` — 调整分录科目
- `prev:{account_code}` — 上期科目
- `report:{start}~{end}` — SUM_ROW 区间引用
