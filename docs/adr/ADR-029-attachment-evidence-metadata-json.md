# ADR-029: 附件证据属性存储方案 — metadata JSON

## 状态

已采纳 (2026-06)

## 上下文

P0-3 需要为附件扩展证据属性（来源、取得日期、提供方、是否关键证据等）。有两种方案：

1. **新增列**：每个属性一列（`source`, `obtained_date`, `provider`, `is_key_evidence`）
2. **metadata JSON**：复用已有 `ocr_fields_cache` JSON 字段思路，新增 `evidence_metadata` JSON 字段

## 决策

**选择方案 2：metadata JSON 字段**。

P0 阶段使用 `Attachment.ocr_fields_cache` 或独立 `evidence_metadata` dict 存储证据属性。
因为 Attachment 模型已有 `ocr_fields_cache: Mapped[dict | None]` JSON 列，且 P0 目标是快速闭环，
不引入新列可避免迁移脚本依赖。

### 具体字段设计

```json
{
  "source": "客户提供 | 第三方获取 | 自行编制",
  "obtained_date": "2025-12-01",
  "provider": "XX公司财务部",
  "is_key_evidence": true,
  "linked_workpapers": ["wp-id-1", "wp-id-2"],
  "reference_count": 3
}
```

### 存储位置

使用 Attachment 模型的 `evidence_metadata` 属性（Pydantic schema 层面扁平化），
实际落入 `ocr_fields_cache` JSON 的 `evidence` 子键，或后续 P1 新增独立列。

## 后果

- 优势：零迁移、快速交付、schema 灵活
- 劣势：无法做 DB 级索引过滤（如 `WHERE is_key_evidence = true`）
- 缓解：P1 阶段可根据使用频率决定是否提取为独立列
- 回滚：直接删除 service 层对 metadata 的读写即可

## 相关

- P0-3.2: 因选择 metadata JSON，跳过 migration 文件（无需新增列）
- P0-3.3: ORM 层不新增 Mapped 字段，通过 service 层读写 JSON
