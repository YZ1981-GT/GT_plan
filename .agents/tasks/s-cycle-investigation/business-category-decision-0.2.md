# Task 0.2 证据记录：`Project.business_category` 与 `refinancing`

## 结论摘要

**推荐方案：批准加宽 `Project.business_category`，目标为 `String(11)` / PostgreSQL `VARCHAR(11)`。**

**当前状态：尚未获得迁移批准，未创建或执行迁移；`refinancing` 的 PG/render 验收仍阻塞。** 本记录是静态核查、只读真库核查和方案建议，不是对共享数据库的变更，也不把工作树已有的适用性代码当作验收证据。

选择加宽而不是短 canonical code 的依据：

1. ORM 和 V077 初始迁移都把该字段定义为 `String(10)` / `VARCHAR(10)`；真实 PostgreSQL 也确认是 `character varying(10)`。
2. `refinancing` 是现有适用性声明和当前工作树 `biz_refinancing` 判定使用的语义字面值，长度为 11；当前没有发现已落地的、可持久化且被读取方共同采用的短 canonical code 契约。
3. 若临时把 `refinancing` 截断或换成未定义的短码，会造成 mapping、生成链、render-config 和持久化值之间的协议漂移；在没有完整映射/回读契约前，不应把它当作可实施方案。
4. 加宽到 11 个字符是最小的 schema/ORM 一致变更；但本任务不执行该变更，必须由用户/环境另行明确批准后再按运行时迁移规范新增 V/R 配对并更新 ORM。

## 静态代码核查

| 项目 | 证据 | 结果 |
|---|---|---|
| ORM | `backend/app/models/core.py` 的 `Project.business_category: Mapped[str \| None] = mapped_column(String(10), nullable=True)` | 长度上限 10，允许 NULL |
| 初始迁移 | `backend/migrations/V077__projects_business_category.sql`：`ADD COLUMN IF NOT EXISTS business_category VARCHAR(10) DEFAULT 'C'` | 数据库设计上限 10，默认 `C` |
| 现有分类服务 | `backend/app/services/business_category_service.py` 的 `get_category_prefix` / `is_template_applicable` | 现有服务按 A/B/C 前缀处理，未发现可持久化的 `refinancing` 短码映射 |
| 适用性声明 | `backend/data/wp_account_mapping.json`（由调查记录复核） | S34 的声明包含 `refinancing`，S35 的声明为 `refinancing`；不是已定义的短码 |
| 当前生成链工作树 | `backend/app/services/chain_orchestrator.py` 当前未提交改动中的 `biz_refinancing` | 使用字面量匹配 `"refinancing" in biz_cat`；这只是工作树实现事实，不是 PG/render 验收证据 |

## 真库只读核查

执行的是一次性只读探针：

```text
.venv/Scripts/python.exe backend/scripts/analyze/_s_cycle_business_category_probe.py
```

探针只执行 `information_schema`、`pg_catalog` 和 `SELECT/COUNT/GROUP BY`，连接使用 `.env`，不输出凭据，不执行 INSERT/UPDATE/DELETE/DDL。结果如下：

### 列元数据

- `public.projects.business_category`
- `information_schema.data_type`: `character varying`
- `character_maximum_length`: `10`
- `character_octet_length`: `40`
- `udt_name`: `varchar`
- `is_nullable`: `YES`
- 默认值：`'C'::character varying`
- `pg_catalog.format_type`: `character varying(10)`

### 行数与长度

| 指标 | 值 |
|---|---:|
| `projects` 总行数 | 142 |
| 未删除行数（`is_deleted=false`） | 85 |
| `business_category IS NULL` | 76（未删除 76） |
| 空字符串 | 0 |
| 非空 | 66 |
| 实际最大字符长度（全表） | 3 |
| 实际最大字符长度（未删除） | 3 |
| 字符长度大于 10 | 0 |
| 精确值 `refinancing`（全表） | 0 |
| 精确值 `refinancing`（未删除） | 0 |
| `lower(trim(...))='refinancing'`（全表） | 0 |
| `lower(trim(...))='refinancing'`（未删除） | 0 |

实际分类分布（只输出分类值，不输出项目身份）：

| `business_category` | 长度 | 总行数 | 未删除行数 |
|---|---:|---:|---:|
| `NULL` | — | 76 | 76 |
| `C` | 1 | 65 | 8 |
| `IPO` | 3 | 1 | 1 |

独立长度核验：Python `len("refinancing") == 11`。因此当前真库没有 `refinancing` 样本，并不能证明当前列可承载该值；列类型已经证明其上限为 10。

## 允许的验证与明确未做事项

在决策未批准前，只运行了纯函数测试：

```text
rtk python -m pytest backend/tests/test_wp_account_mapping_single_source.py -k "applicable_when" -p no:playwright
```

结果：`3 passed, 29 deselected`（仅覆盖 `match_workpapers` 的 `business_category` / `industry` 适用性命中与未命中）。

未做且不得宣称通过：

- 未执行任何迁移、DDL、INSERT、UPDATE 或共享库写入。
- 未创建短 canonical code，也未截断/替换任何业务分类值。
- 未运行 `refinancing` 的 PG 集成验收、render-config 验收、生成链端到端验收或浏览器验收；这些继续标记为阻塞。
- 未修改生产代码、ORM、迁移或测试代码。

一次性探针在本记录写入后删除；如需复核，应按本记录中的 SQL 口径重新建立独立只读探针，不应直接把探针当成迁移工具。

## 后续批准后的最小切换点（本任务不执行）

若批准加宽：同一变更中更新 `Project.business_category` 的 ORM 类型与新的 V/R 运行时迁移，并在迁移后重新做 schema drift、持久化 `refinancing`、生成链/render-config 和浏览器读回验证；所有证据必须绑定到迁移已落库的数据库。

若改为批准短 canonical code：必须先由产品/领域方指定稳定短值、正向/反向映射、唯一性/回读规则，并同步 mapping、生成链、render-config、表单/导入和数据库契约；在该契约落地前，本记录的推荐方案不变。
