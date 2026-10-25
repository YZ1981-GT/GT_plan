# Task 10 证据说明：ORM、repository、允许状态边与数据库并发/不可变约束

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 10
Properties: P4 / P5 / P18 / P36 / P43 / P59 / P63 / P64 / P68

## 产物

| 类别 | 路径 |
|---|---|
| ORM（V151 的 28 张表） | `backend/app/models/workpaper_sync_models.py`（+ `backend/app/models/__init__.py` 注册） |
| domain enum / 允许状态边 / identity | `backend/app/services/workpaper_sync/models.py` |
| 仓储（只 flush 不 commit） | `backend/app/services/workpaper_sync/repository.py` |
| 纯逻辑守卫 | `backend/tests/workpaper_sync/test_task10_orm_repository_contract.py` |
| 真实 PG 并发守卫 | `backend/tests/workpaper_sync/test_task10_repository_pg.py` |
| 变异 runner | `backend/scripts/diagnose/mutate_task10_orm_repository_guards.py` |
| 变异结果 | `mutation_report.json`（本目录） |

## 测试结果

- `backend/tests/workpaper_sync`：**78 passed**（Task 9 的 19 + Task 10 的 31 纯逻辑 + 28 真实 PG）
- PG 守卫在 scratch schema `tmp_task10_repo_<hex>` 内跑，`search_path` 不含 public，
  `projects/users/working_paper` 为桩表 ⇒ 物理上不可能触到业务表；结束 DROP SCHEMA CASCADE。

## 变异四态

**RED 47 / GREEN 0 / ANCHOR-MISS 0 / WRONG-TEST 0**（`--check-anchors` 47/47 命中、
只读性核验通过、目标文件 md5 未变）。

### 首轮 18 条 GREEN 的逐条归因（全部为真实缺陷，无一条靠降标处理）

| 类别 | 条目 | 根因 | 修法 |
|---|---|---|---|
| 判定工具缺陷 | M30 / M34 / M41 / M44 / M49 | pytest 只给 `-rf`，harness（module fixture）异常在 pytest 里是 **ERROR** 不是 FAILED，短摘要不含 `ERROR ...` 行 ⇒ runner 收不到失败名 ⇒ 整轮误判 GREEN | 改 `-rfE` |
| 无效变异 | M03 | `mapped_column(..., nullable=True)` 的显式参数覆盖 `Mapped[X\|None]` 标注推导，改标注对 nullable 毫无影响 | 改为翻转显式 `nullable` 参数 |
| 负控制被遮蔽（生产代码分支不可达） | M10 / M11 | `assert_direct_primary` 里 chain/stranded 两条断言互相遮蔽；`application_id is None` 又被下面的不等值比较完全覆盖 | 删掉不可达的 `is None` 项，chain 的两个 or 项各补一条**只触发其一**的负控制输入 |
| 负控制被遮蔽（异常类型混用） | M37 | quarantine 终态与「尚未 durable」暂态共用 `QuarantinedIncomingError`，短路隔离分支后暂态分支抛同类异常 | 拆出 `IncomingNotDurableError`，守卫断言**异常类型** |
| 负控制被遮蔽（探针 kind 选错） | M36 | 数字 resource_id 探针用了 `content_version` kind，被该 kind 专属的「必须 UUID」校验遮蔽 | 探针换 `sync_conflict` kind + 断言异常类型 + 补 DB 侧裸 INSERT 判据 |
| 负控制被遮蔽（校验顺序） | M52 / M55 | 「零三实体」「缺 approved contract/bundle」两条语义校验写在状态边校验**之后**，永远被 `StateTransitionError` 遮蔽成不可达分支 | 语义专属校验提到状态边之前 + 断言异常类型；`or` 三段收敛成单一布尔 `has_any_entity` |
| 缺负控制 | M40 / M47 | 没有测试重复 correlate 已收敛的 shell，也没有测试改写已 durable 的 delivery 归属 | 各补一条负控制并断言异常类型 |
| 缺判据 | M43 | leader 选择的 comparator（max vs min）在既有场景下两种取值都走同一条 stale→successor 路径 | 守卫独立复算「最高 `(intent_sequence, id)`」并断言相等 |
| 死代码 | M42 | reconcile 里「digest 相同就沿用旧 leader」分支行为上不可达（eligible 集合不变 ⇒ digest 不变 ⇒ `max()` 必选同一条） | 删除该分支（属「additive 注入即死代码」），同 snapshot 不换 leader 由 comparator 确定性 + digest 保证 |

### 自证型变异（不计入 RED/GREEN 统计，单独跑）

`M39`：只把一条错误文案替换成无意义字符串，**不改行为**。跑
`tmp_task10_selfcheck_m39`（已随会话清理）得 `59 passed` ⇒ 判定 **GREEN（期望）**，
证明没有任何守卫是在断言错误文案字符串（否则属 grep 式假绿）。

## 存量失败归因（非本任务引入）

辐射面扫描发现 3 条失败，**摘掉本任务的 ORM 注册后仍然失败**（`__init__.py` md5 复原一致），
故为存量：

- `test_raw_sql_schema_contract.py::test_raw_sql_tables_are_known` —— 幻影表
  `disclosure_note_cells` / `project` / `working_papers`，引用方是 l8/m1/m6/m9/n2/h7 等
  既有 router/service（本任务未触碰）。且该判据的 offender 集合 = 裸 SQL 表 − ORM 表 −
  迁移表 − allowlist，**新增 ORM 表只会缩小它**，结构上不可能由本任务引入。
- `test_production_readiness_properties.py::test_property_14_all_business_routes_under_api`
  —— account-packages / g5·g12·g13·g14 ai 路由未挂 `/api`，与 models 层无关。
- `test_property_archived_invariant.py::...returns_423` —— 归档项目返回 403
  `OPERATION_NOT_ALLOWED wp:edit` 而非 423，另一支 SQLite fixture 缺 `account_chart` 表。

## 未决边界（留给后续任务）

- V151 **尚未在业务库应用**（MigrationRunner 只在后端启动时跑）。本任务的 ORM 已进
  `Base.metadata`，因此在 V151 应用前 `SchemaDriftDetector` 会把这 28 张表报为
  `orm_extra`。启动顺序是「先跑迁移、后做 drift 扫描」（`app/main.py`），故下次后端重启
  即自愈，无需额外动作。
- `working_paper.content_revision / current_content_version_id` 由 repository 用**无表别名**
  的裸 SQL 读写（列级契约测试只校验 `别名.列` 形态，故不受影响），未改动 44KB 的
  `workpaper_models.py`（避免与并发会话争用同一文件）。
