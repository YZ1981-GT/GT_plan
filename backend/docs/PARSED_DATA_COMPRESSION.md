# parsed_data 压缩存储策略

**编制日期**：2026-05-22  
**状态**：已决策 — 依赖 PG TOAST 自动压缩，零代码变更

---

## 1. 现状分析

`working_paper.parsed_data` 列类型为 `JSONB`，存储底稿解析后的结构化数据。

- **典型大小**：单 sheet 底稿 10~50 KB，多 sheet（100+）底稿可达 1~5 MB
- **增长趋势**：随 prefill cells 增加（当前 1035 cells），parsed_data 内嵌的 namespace 数据（depreciation_calcs / amortization_calcs / equity_movement 等）持续增长
- **性能影响**：大 JSONB 值在 SELECT 时全量读取，影响 WorkpaperList 等列表查询响应时间

---

## 2. PostgreSQL TOAST 机制（当前方案）

PostgreSQL 对超过 ~2 KB 的列值自动启用 [TOAST](https://www.postgresql.org/docs/16/storage-toast.html) 压缩存储：

- **压缩算法**：PG 16 默认使用 LZ4（`SET default_toast_compression = 'lz4'`），旧版本使用 pglz
- **触发条件**：行总大小超过 TOAST_TUPLE_THRESHOLD（默认 2 KB）时自动压缩 + 外部存储
- **压缩比**：JSON 类数据典型压缩比 3:1 ~ 5:1（重复 key 名 + 结构化文本）
- **透明性**：应用层无感知，SELECT/INSERT/UPDATE 自动解压/压缩

### 优势

- **零代码变更**：无需修改 SQLAlchemy 模型或 API 层
- **零迁移风险**：不需要 Alembic migration
- **自动生效**：已有数据在 VACUUM FULL 后重新压缩

### 局限

- 无法控制压缩粒度（整列压缩，不能按 sheet 分片）
- 查询时仍需全量解压（即使只读 parsed_data 的一个 key）

---

## 3. 备选方案：应用层 zstd 压缩

如果未来 TOAST 压缩不足以满足性能需求，可考虑：

```python
# 写入时压缩
import zstandard as zstd
compressor = zstd.ZstdCompressor(level=3)
compressed = compressor.compress(json.dumps(parsed_data).encode())
# 存储为 BYTEA 列 parsed_data_compressed

# 读取时解压
decompressor = zstd.ZstdDecompressor()
raw = decompressor.decompress(compressed)
parsed_data = json.loads(raw)
```

**代价**：
- 需要新增 `parsed_data_compressed BYTEA` 列 + 数据迁移
- 失去 JSONB 的 `->` / `->>` / `@>` 等 JSON 路径查询能力
- 需要应用层序列化/反序列化逻辑

**结论**：当前阶段不实施，TOAST 已足够。

---

## 4. 备选方案：按 sheet 拆分存储

将 parsed_data 拆分为独立表 `workpaper_sheet_data(wp_id, sheet_name, data JSONB)`：

**优势**：
- 查询单 sheet 时只读取对应行
- 每行更小，TOAST 压缩更高效

**代价**：
- 大规模 schema 变更 + 数据迁移
- 所有读写 parsed_data 的代码需重构
- 事务一致性更复杂

**结论**：作为 Phase 5+ 长期优化方案保留，当前不实施。

---

## 5. 监控方案

使用 `pg_column_size()` 定期监控 parsed_data 列的存储大小分布：

```sql
-- Top 20 最大的 parsed_data
SELECT 
    wp.id,
    wi.wp_code,
    pg_column_size(wp.parsed_data) AS raw_bytes,
    pg_size_pretty(pg_column_size(wp.parsed_data)::bigint) AS human_size
FROM working_paper wp
JOIN wp_index wi ON wp.wp_index_id = wi.id
WHERE wp.parsed_data IS NOT NULL
ORDER BY pg_column_size(wp.parsed_data) DESC
LIMIT 20;

-- 大小分布统计
SELECT 
    CASE 
        WHEN pg_column_size(parsed_data) < 1024 THEN '< 1 KB'
        WHEN pg_column_size(parsed_data) < 10240 THEN '1-10 KB'
        WHEN pg_column_size(parsed_data) < 102400 THEN '10-100 KB'
        WHEN pg_column_size(parsed_data) < 1048576 THEN '100 KB - 1 MB'
        ELSE '> 1 MB'
    END AS size_bucket,
    COUNT(*) AS count
FROM working_paper
WHERE parsed_data IS NOT NULL
GROUP BY 1
ORDER BY MIN(pg_column_size(parsed_data));
```

监控脚本：`backend/scripts/check_parsed_data_size.py`

---

## 6. 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-22 | 依赖 PG TOAST，不做应用层压缩 | 零代码变更 + 保留 JSONB 查询能力 + 压缩比已足够 |
| - | 监控 pg_column_size 分布 | 数据驱动决策，超过阈值再升级方案 |
| - | 列表 API 已实现 field_selection 排除 parsed_data | Phase 5 FE-2 已落地，列表查询不返回大字段 |

---

## 7. 触发升级条件

当以下任一条件满足时，重新评估压缩方案：

1. Top 20 底稿 parsed_data > 5 MB（当前预估 < 2 MB）
2. WorkpaperList API P95 > 500ms 且瓶颈在 parsed_data 读取
3. 数据库总大小增长 > 50% 且 parsed_data 占比 > 30%
