# 迁移完整性与枚举漂移收口 — 需求

> 2026-09-29 新建。来源：`knowledge-base-retrieval-and-authz-closure` 实施中现查真库发现的平台级欠账，
> 用户裁定「方案 A，其他的逐一修复」。本 spec 只处理**迁移 / 枚举**两类；启动延迟、环境卫生另行处理。

## 背景（全部为 2026-09-29 现查真库 + git 历史的结论）

| # | 事实 | 后果 |
|---|------|------|
| F1 | `detect_checksum_drift()` 已实现但**全仓零调用方**；现场报 7 条漂移（V042/046/105/128/143/151/163） | 「已应用迁移被事后编辑」完全不可见 |
| F2 | 7 条里只有 **V128** 有效果缺失：真库记录的是 2026-07-26 00:04 首版（833a37fa5，checksum `0727d53b…`）；当日 17:06 原地改写（04580b855）加了 2 条 `COMMENT ON TABLE`、把触发器换绑到 `evgov_forbid_update/delete()` —— 改写版从未在真库执行 | `confirmation_action_log` 的 UPDATE/DELETE 拒绝走自建函数，SQLSTATE 为 P0001 而非其余 8 张 evgov 表的 23514 / 23001；两表无表注释 |
| F3 | 另 6 条漂移逐对象核验（CREATE TABLE/INDEX/FUNCTION/TRIGGER/TYPE、ADD COLUMN/CONSTRAINT、ADD VALUE、COMMENT）：当前文件声明的对象在 public 全部存在 | 属「编辑后效果已由他处补齐」，不需补迁移，但必须显式登记 |
| F4 | V042 以**空文件**登记为已应用（checksum = `sha256("")`），应用时间早于提交时间 | 零语句迁移会被静默记为成功，内容写入后永不执行（V168 才补回） |
| F5 | checksum 计算用 `read_text`（通用换行）⇒ CRLF 与 LF 同哈希；磁盘 162 个 CRLF 文件全部与 LF 版一致 | 行尾**不是**漂移成因（排除该假设） |
| F6 | `_diff_enums` 三处缺陷：①按类名 snake_case 猜 PG 类型名（漏配、错配；同模块两个同名 `ApprovalStatus` 后者遮蔽前者）②比较 `.value`，而 SQLAlchemy 原生枚举持久化的是**成员名**（`Enum.enums`）③查 `pg_type` 不限 schema，`tmp_*` 残留 schema 的同名类型把标签并进来 | 既漏报真缺口，又误报假缺口：memory 记录的「confirmation_risk_level_enum 缺 pass、workpaper_task_status_enum 缺 4 值」实为 ② 造成的**误报**（库里存的正是成员名 `pass_` / `PENDING…`） |
| F7 | 真缺口 1：`GTWpCoding.wp_type` 声明原生枚举 `gt_wp_type`，真库列是 varchar、public 无该类型 ⇒ asyncpg 渲染 `$1::gt_wp_type`，**任何**按 wp_type 的查询与插入都抛 `UndefinedObjectError` | 致同编码种子加载 / 筛选恒 500（表 0 行即此） |
| F8 | 真缺口 2：`WorkpaperReviewRecord.review_status` 用 `ApprovalStatus(pending/approved/rejected)` 映射到共享类型 `review_status_enum(draft/pending_review/approved/rejected)` ⇒ `pending` 插入抛 `InvalidTextRepresentation` | 模型当前零调用方、表 0 行，接入即炸 |

## Requirement 1：补齐 V128 缺失效果

1.1 新增 V171（实施前重扫迁移号），只补「改写版相对首版多出的效果」：两条表注释；`confirmation_action_log` 的 UPDATE/DELETE 触发器绑定 `evgov_forbid_update()` / `evgov_forbid_delete()`；删除首版触发器 `trg_conf_action_log_no_update/no_delete` 与其专用函数。
1.2 V171 SHALL 把 `evgov_forbid_update()` / `evgov_forbid_delete()` 钉回 V108 / V111 原文（UPDATE → `check_violation`，DELETE → `restrict_violation`），使「新库按当前 V128 执行」与「真库」收敛到同一函数体；SHALL NOT 重放当前 V128 的函数定义（其 UPDATE 写成 `restrict_violation`，重放会翻转其余 8 张表的拒绝码）。
1.3 SHALL NOT 改写 `schema_version` 里 V128 的 checksum（漂移是历史事实，由 Requirement 3 显式登记）。
1.4 全部语句幂等（`IF EXISTS` / `CREATE OR REPLACE`）；提供 R171。
1.5 真库验证：`confirmation_action_log` UPDATE → SQLSTATE 23514、DELETE → 23001，报文含表名；其余 evgov 表拒绝码不变；替换原有两个 `xfail + assert False` 占位用例（假绿）为真库用例。

## Requirement 2：零语句迁移不得记为已应用

2.1 `_apply_migration` 遇到分句后零条语句的文件 SHALL 抛错（记入 `schema_migration_failures`、不写 `schema_version`、下次启动重试）。
2.2 例外：注释中含 `no-op` 标记的文件（V001 基线已有该标记，不改文件）。
2.3 测试：空文件 → 失败且未登记；写入内容后再跑 → 成功登记；带 `no-op` 标记的空语句文件 → 正常登记。

## Requirement 3：checksum 漂移可见且可伪证

3.1 新增显式登记表：每条已知漂移记录 `stored` 与 `current` 两个 checksum + 中文结论（效果已由谁补齐 / 为何不补）。
3.2 `unexplained_checksum_drift()` = 实测漂移 − 两个 checksum **都逐字相等**的登记项；登记项与实测不符（文件又被改、或漂移已消失）SHALL 视为「未解释」（登记表不能变成永久豁免）。
3.3 启动 schema 漂移扫描 SHALL 把未解释漂移写入 `schema_drift_log`（新类型 `checksum_drift`），`/api/health` 计为 critical ⇒ `degraded`；critical 类型集合单一真源，启动两处与 health 共用。
3.4 离线守卫：登记项的 `current` 与磁盘文件实算值一致（文件再被改即红）；真库守卫：现场未解释漂移为 0。

## Requirement 4：枚举漂移检测按「列」而非「类名」

4.1 遍历 ORM metadata 中 `native_enum=True` 的 `sa.Enum` 列；期望标签 = `column.type.enums`（SQLAlchemy 实际发送的值，默认是成员名）。
4.2 实际类型 = 该列在 **public** 的 `udt_name`；标签只取 public 下该类型的 `pg_enum`。
4.3 两类报告（均 `enum_mismatch`，critical）：DB 类型缺 ORM 标签；ORM 声明原生枚举但 DB 列不是该枚举类型（含 varchar）。
4.4 判定逻辑为纯函数（可离线单测覆盖三处旧缺陷）；真库守卫：修复后现场 0 条，且 F6 所列两个旧误报不再出现；变异（回退任一模型修复）必须打红。

## Requirement 5：修复两个真缺口（ORM 向真库对齐，不改表结构）

5.1 `GTWpCoding.wp_type` 改为非原生枚举（`native_enum=False`、不建约束），与 varchar 列一致；取值校验仍由 `GTWpType` 与 service 层保证。
5.2 `WorkpaperReviewRecord.review_status` 改用 `ReviewStatus`（与共享类型 `review_status_enum` 及 `risk_assessments` 同一枚举）。
5.3 真库验证（回滚事务内）：按 wp_type 查询 / 插入成功；`review_status` 以 `pending_review` 插入成功。

## Requirement 6：验证

6.1 相关测试全绿；预存红逐条归因（改动文件换回 HEAD 复跑对照）。
6.2 变异证明：去掉零语句拒绝 / 登记表比较只看版本号不看 checksum / 枚举比较改回 `.value` / 查询去掉 schema 限定 / 回退任一模型修复 —— 各自必须打红，还原后 sha256 一致。
