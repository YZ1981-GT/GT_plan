# 账表导入适配器 JSON Schema

本目录（`backend/data/ledger_adapters/`）存放外置的财务软件适配器定义。
每个文件代表一家软件（或同一家的某个版本变体），由
`AdapterRegistry.reload_from_json(directory)` 在需要时热加载为
`JsonDrivenAdapter`（见 `backend/app/services/ledger_import/adapters/__init__.py`）。

## 扫描规则

- 文件扩展名必须为 `.json`。
- 文件名以 `_` 开头的会被**跳过**（约定用于文档、共享片段、备注等，例如
  本文件 `_schema.md`）。
- 解析失败、缺 `id`、非对象结构会打 `WARNING` 日志并跳过，不影响其他文件。
- 同 `id` 重复注册，后加载者覆盖前者（idempotent）。

## JSON 结构

```json
{
  "id": "yonyou",
  "display_name": "用友 U8/NC/T+",
  "priority": 80,
  "match_patterns": {
    "filename_regex": [
      "(?i)(用友|UFIDA|U8|NC\\d|T\\+)"
    ],
    "signature_columns": {
      "balance": ["科目编码", "科目名称", "方向", "年初余额"],
      "ledger": ["凭证日期", "凭证号", "摘要", "科目"]
    }
  },
  "column_aliases": {
    "balance": {
      "account_code": ["科目编码", "科目代码"],
      "opening_balance": ["年初余额", "期初余额"]
    },
    "ledger": {
      "voucher_date": ["凭证日期", "制单日期"]
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 唯一标识，建议小写短名（`yonyou`/`kingdee`/`sap` 等） |
| `display_name` | string |    | 面向用户的中文名，如"用友 U8/NC/T+" |
| `priority` | int |    | 优先级，数字越大越先参与匹配；建议 vendor 60-90，generic=0 |
| `match_patterns.filename_regex` | string[] |    | 文件名正则，命中任一即得 +0.5 分 |
| `match_patterns.signature_columns` | object |    | `{table_type: [headers...]}`，每个表类型的"特征列"，与实际表头交集比例 × 0.5 计入分数（多 sheet 取最高） |
| `column_aliases` | object |    | `{table_type: {standard_field: [alias, ...]}}`，**仅需**定义关键列 + 次关键列，非关键列走通用 `GenericAdapter.get_column_aliases()` 兜底 |

### 打分规则（复述 `JsonDrivenAdapter.match`）

- filename 命中任一 `filename_regex` → +0.5（多个命中不累加）
- 表头与 `signature_columns[table_type]` 的交集比例 × 0.5（多 sheet 取最高）
- 总分 cap 为 1.0

### 命名约定

- 单家软件单文件：`yonyou.json` / `kingdee.json` / `sap.json` / ...
- 租户自定义：`custom_{tenant_slug}.json`
- 半成品 / 参考模板：以 `_` 开头，如 `_sample.json`、`_draft_xxx.json`（会被 scanner 跳过）

### 列分层说明（与识别层单一真源对齐）

`column_aliases` 中定义的 `standard_field` 归属于哪一层（关键 / 次关键 / 非关键），
由 `detection_types.KEY_COLUMNS` 和 `RECOMMENDED_COLUMNS` 决定，**不**在
本 JSON 中重复声明。适配器只负责"vendor 别名映射"，不重复定义列分层。

## 加载时机

- 模块 import 时 `AdapterRegistry` 只自动注册 `GenericAdapter`。
- 需要加载外置定义时，由业务代码或启动钩子显式调用：

  ```python
  from backend.app.services.ledger_import.adapters import registry
  from pathlib import Path

  registry.reload_from_json(Path("backend/data/ledger_adapters"))
  ```

- 支持热 reload：再次调用相同目录会覆盖同 `id` 的已注册适配器。
