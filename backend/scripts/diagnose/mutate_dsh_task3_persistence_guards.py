"""Task 3 持久化守卫变异检验（spec dsh-agent-panel-integration / Task 3）。

## 为什么需要它

「28 条守卫全绿」只证明当前代码没触发断言，**不证明断言有效**。Task 3 交付的是
Phase A 的持久化底座，最贵的假绿形态都在这里：

- history 悄悄退回"取最早 N 条"（会话一长，用户与模型都拿不到近期上下文）；
- 会话/run/收据的 upsert 退回"先查后建"（单线程测试永远绿，只在并发下分裂）；
- 部分唯一索引的 ON CONFLICT 谓词漏掉（推断不到索引 ⇒ 幂等失效）；
- session_key 少绑一个要素（跨年度/跨项目会话互相串用）；
- 迁移回填表达式与 Python 侧算法漂移（存量行的 key 与运行时 key 错位）；
- ``seq`` 的 DB 生成语义被拿掉（ORM 写 NULL，PG BIGSERIAL 默认值永不生效）；
- 附件外键从 RESTRICT 改回 CASCADE（clear session 把 metadata 连带删掉，
  ``storage/ai_chat/`` 下的物理文件变成无人追踪的孤儿）；
- CHECK 取值域与 Python 枚举单向漂移。

唯一可靠的反证是把生产代码/迁移**改坏**，看对应守卫是否打红。

## 一条重要边界：已应用的迁移，改文件不改库

V147 已经应用在 dev PG 上。改迁移文件**不会**改变 live schema，因此：

- 读 **live PG** 的守卫（CHECK/索引/外键/列）对迁移文件的变异**必然 GREEN**；
- 只有读**迁移文件本身**的守卫（回填表达式求值、语句序、去重规则、
  外键声明）才可能被迁移变异打红。

所以本脚本对迁移文件的变异只挂到那几条"读文件"的判据上，而 live schema 类判据
改由**Python 取值域枚举**的变异来反证（枚举与 CHECK 双向比对，改枚举即打红）。

## 四态判定

由 ``_mutation_kit`` 统一给出：RED（新增失败含期望项）/ WRONG-TEST（新增失败不含
期望项）/ GREEN（无新增失败 = 守卫缺陷）/ ANCHOR-MISS（锚点未唯一命中 = 本脚本缺陷）。
退出码不作判据。

用法::

    python backend/scripts/diagnose/mutate_dsh_task3_persistence_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task3_persistence_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task3_persistence_guards.py --run all
    python backend/scripts/diagnose/mutate_dsh_task3_persistence_guards.py --restore
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: 本 Task 创建的守卫文件全集（覆盖面分母）。新增守卫文件必须同时加一条变异。
GUARD_FILES: dict[str, str] = {
    "test_task3_chat_persistence.py": "Task 3 新建（Property 6/10/21 + 持久化结构契约）",
}

#: 冻结基线（本会话实测 2026-08-22）：29 passed（本文件单独跑）。
#: 同目录合并跑为 51 passed（含 Task 1 的 22 条）。改这个数必须同时说明来源。
BASELINE_BE_PASSED = 29

#: 🔴 `-rfE` 而不是 `-rf`：本文件的并发判据挂在**模块级 fixture** 上，变异一旦让
#: fixture 抛异常，pytest 把 18 条判据记为 **ERROR** 而非 FAILED。`-rf` 的 short
#: summary **只列 failed**，于是 `_mutation_kit` 的 `^ERROR\s+(\S+)` 一条都抓不到
#: ⇒ 明明打红了却被判 WRONG-TEST（实测 M07/M08 踩过）。
BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel/test_task3_chat_persistence.py",
    "-q",
    "--tb=no",
    "-rfE",
    "-p",
    "no:randomly",
]

PERSIST = "backend/app/services/ai_chat/persistence.py"
MODELS = "backend/app/models/ai_models.py"
MIGRATION = "backend/migrations/V147__ai_chat_persistence_runs_and_session_key.sql"

MUTATIONS: list[Mut] = [
    # ── history：Property 10 ────────────────────────────────────────────────
    Mut(
        id="M01",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="        .order_by(AIChatMessage.created_at.desc(), AIChatMessage.seq.desc())",
        new="        .order_by(AIChatMessage.created_at.asc(), AIChatMessage.seq.asc())",
        want="test_history_returns_most_recent_n_ascending_with_real_metadata",
        why=(
            "内层子查询由倒序改回正序 = 恢复旧实现的「取最早 N 条」。会话超过 N 条后"
            "用户再也看不到刚说过的话。守卫用 12 条/limit=5（最早 5 与最近 5 互斥）"
            "锁死，只数条数的判据查不出来。"
        ),
        tags=("property10", "req4.10"),
    ),
    Mut(
        id="M02",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="            AIChatRun.engine.label(\"engine\"),",
        new="            sa.null().label(\"engine\"),",
        want="test_history_returns_most_recent_n_ascending_with_real_metadata",
        why=(
            "history 不再带出 run 的 engine（Req 4.10 明列 engine 为必须元数据）。"
            "只断言「返回了 N 条」的守卫查不出元数据缺失。"
        ),
        tags=("property10", "req4.10"),
    ),
    Mut(
        id="M03",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="        content_hash=content_hash(text),",
        new="        content_hash=None,",
        want="test_history_returns_most_recent_n_ascending_with_real_metadata",
        why=(
            "消息不再保存服务端算出的 content hash ⇒ 采纳/转存失去「正文未被客户端"
            "篡改」的校验依据（Req 8.1/8.6 的前置）。"
        ),
        tags=("property10", "req8.1"),
    ),
    Mut(
        id="M04",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="    session.last_message_at = datetime.now()",
        new="    session.last_message_at = None",
        want="test_history_returns_most_recent_n_ascending_with_real_metadata",
        why=(
            "last_message_at 不再写入 ⇒ 会话列表排序与「无 year 时取最近会话」的"
            "只读兜底都会失效（find_session 的 fallback 依赖它）。"
        ),
        tags=("req4.10",),
    ),
    # ── 并发幂等：Property 6 / 21 ──────────────────────────────────────────
    Mut(
        id="M05",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="        inserted_id = (await db.execute(stmt)).scalar_one_or_none()",
        # 该行在 upsert_session / upsert_run / claim_action_receipt 中逐字相同，
        # 用上一行 `.returning(AIChatSession.id)` 作 scope 相对定位到会话分支。
        scope="            .returning(AIChatSession.id)",
        offset=2,
        new=(
            "        _pre = (await db.execute(sa.select(AIChatSession.id).where("
            "AIChatSession.user_id == user_id, AIChatSession.session_key == key"
            "))).scalar_one_or_none()\n"
            "        inserted_id = None\n"
            "        if _pre is None:\n"
            "            inserted_id = (await db.execute(sa.insert(AIChatSession)"
            ".values(**values).returning(AIChatSession.id))).scalar_one_or_none()"
        ),
        want="test_session_upsert_issues_on_conflict_before_any_select",
        wants=(
            "test_concurrent_identical_session_keys_produce_exactly_one_session",
            "test_concurrent_identical_idempotency_keys_produce_one_run_one_message",
            "test_concurrent_note_idempotency_keys_create_one_receipt_and_one_resource",
        ),
        why=(
            "会话创建退回**先查后建**（旧实现的真实形态）。单线程下行为完全正常，"
            "只有「第一条触及 ai_chat_session 的语句必须是 INSERT … ON CONFLICT」"
            "这条语句序判据能抓住；并发场景下败者会撞唯一索引抛错。"
        ),
        tags=("property6", "req4.11"),
    ),
    Mut(
        id="M06",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="                index_where=_SESSION_CONFLICT_WHERE,",
        new="                index_where=None,",
        want="test_session_upsert_issues_on_conflict_before_any_select",
        wants=("test_concurrent_identical_session_keys_produce_exactly_one_session",),
        why=(
            "部分唯一索引的 ON CONFLICT 推断漏掉谓词 ⇒ PG 找不到匹配的唯一索引，"
            "冲突推断直接报错。这是「部分索引 + ON CONFLICT」最常见的接线错误。"
        ),
        tags=("property6", "req4.11"),
    ),
    Mut(
        id="M07",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="                    AIChatRun.idempotency_key,",
        new="                    AIChatRun.host_id,",
        want="test_concurrent_identical_idempotency_keys_produce_one_run_one_message",
        why=(
            "run 幂等键从 idempotency_key 换成 host_id ⇒ 冲突推断落到不存在的唯一"
            "索引上。若守卫只查「run 行数是否为 1」而不真并发，这类错接在单线程下"
            "也会暴露；本条同时验证并发夹具真的在跑。"
        ),
        tags=("property6", "req4.6"),
    ),
    Mut(
        id="M08",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="                    AIChatActionReceipt.idempotency_key,",
        new="                    AIChatActionReceipt.source_message_hash,",
        want="test_concurrent_note_idempotency_keys_create_one_receipt_and_one_resource",
        wants=("test_receipt_carries_server_side_content_hash_not_client_text",),
        why=(
            "笔记收据的幂等键被换掉 ⇒ Req 8.3 要求的「数据库唯一约束保证并发幂等」"
            "失效，会创建重复文件夹/文档。"
        ),
        tags=("property21", "req8.3"),
    ),
    Mut(
        id="M09",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="    if not idempotency_key:",
        # 该行在 upsert_run 与 claim_action_receipt 中各一次；用 upsert_run 独有的
        # `eng = …` 行作 scope 相对定位（offset=-3 回到目标行），不用绝对行号。
        scope="    eng = engine.value if isinstance(engine, ChatEngineName) else str(engine)",
        offset=-3,
        new="    if False:",
        want="test_run_and_receipt_reject_empty_idempotency_key",
        why=(
            "空 idempotency key 不再拒绝 ⇒ 幂等退化为「每次都新建」（空串在唯一索引"
            "里是一个具体值，第二次反而会撞约束报 500）。"
        ),
        tags=("req8.2",),
    ),
    # ── session_key 五要素与 sentinel ──────────────────────────────────────
    Mut(
        id="M10",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="            str(audit_year) if audit_year is not None else NO_YEAR_SENTINEL,",
        new="            NO_YEAR_SENTINEL,",
        want="test_session_key_binds_all_five_locator_elements",
        why=(
            "年度不再进定位键 ⇒ 同一底稿的不同审计年度共用一个会话，跨年度历史串用。"
            "Req 4.11 明列 year 为定位五要素之一。"
        ),
        tags=("req4.11",),
    ),
    Mut(
        id="M11",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="            str(project_id) if project_id else NO_PROJECT_SENTINEL,",
        new="            NO_PROJECT_SENTINEL,",
        want="test_session_key_binds_all_five_locator_elements",
        wants=("test_session_key_sql_backfill_matches_python",),
        why=(
            "项目不再进定位键 ⇒ 跨项目同名宿主共用会话（跨项目泄漏）。同时会让"
            "迁移回填表达式与 Python 算法漂移，两条判据都应打红。"
        ),
        tags=("req4.11",),
    ),
    Mut(
        id="M12",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="    if not host_id:",
        new="    if False:",
        want="test_global_knowledge_uses_explicit_sentinel_not_empty_string",
        why=(
            "空 host_id 不再拒绝 ⇒ 恢复「用空字符串伪装有效 ID」这一被明令禁止的"
            "形态（Req 3.3），所有无 ID 宿主会塌到同一个 key 上。"
        ),
        tags=("req4.11",),
    ),
    Mut(
        id="M13",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="NO_PROJECT_SENTINEL = GLOBAL_KNOWLEDGE_HOST_ID",
        new='NO_PROJECT_SENTINEL = "no-project"',
        want="test_global_knowledge_uses_explicit_sentinel_not_empty_string",
        wants=("test_session_key_sql_backfill_matches_python",),
        why=(
            "无项目 sentinel 不再复用 Task 1 冻结的常量而自造第二个 ⇒ 迁移里写死的"
            "'global-knowledge' 与运行时算法分叉。这正是「同一概念两个真源」的形态。"
        ),
        tags=("req4.11",),
    ),
    # ── seq 的 DB 生成语义 ────────────────────────────────────────────────
    Mut(
        id="M14",
        side="be",
        path=MODELS,
        kind="replace",
        anchor="        sa.BigInteger, sa.FetchedValue(), nullable=True",
        new="        sa.BigInteger, nullable=True",
        want="test_history_returns_most_recent_n_ascending_with_real_metadata",
        why=(
            "去掉 FetchedValue ⇒ ORM insert 把未赋值的 seq 当 NULL 一起写进 INSERT，"
            "PG 的 BIGSERIAL 默认值永不生效 ⇒ NotNullViolation。这是本 Task 实测踩过"
            "的真实缺陷，必须有守卫兜住。"
        ),
        tags=("property10",),
    ),
    # ── CHECK 取值域 ↔ Python 枚举双向 ────────────────────────────────────
    Mut(
        id="M15",
        side="be",
        path=MODELS,
        kind="replace",
        anchor='    interrupted = "interrupted"',
        new='    interrupted = "interrupted_v2"',
        want="test_check_constraint_value_domain_equals_python_enum",
        why=(
            "run 状态枚举值漂移一个字符 ⇒ 应用层写该值会被 CHECK 拒绝（运行时 500）。"
            "单向包含判据（DB ⊆ Python）查不出 Python 多出取值这一侧，故守卫必须双向。"
        ),
        tags=("req4.11",),
    ),
    Mut(
        id="M16",
        side="be",
        path=MODELS,
        kind="replace",
        anchor='    empty = "empty"',
        new='    empty = "no_text"',
        want="test_check_constraint_value_domain_equals_python_enum",
        why=(
            "OCR 的 empty 态（Req 7.6：成功但无文字，不得当失败）取值漂移 ⇒ 写库即被"
            "CHECK 拒绝，五态互斥（Property 19）的基础塌掉。"
        ),
        tags=("req7.3",),
    ),
    Mut(
        id="M20",
        side="be",
        path=PERSIST,
        kind="replace",
        anchor="    if exact is not None or audit_year is not None:",
        new="    if exact is not None:",
        want="test_doc_facade_history_resolves_with_and_without_year",
        why=(
            "给定 year 却找不到精确会话时也去回退取「最近一个会话」⇒ 跨年度隔离失效："
            "查 2024 年的历史会返回 2025 年的对话。Req 4.11 的 year 绑定就白写了。"
        ),
        tags=("req4.10", "req4.11"),
    ),
    Mut(
        id="M21",
        side="be",
        path="backend/app/services/doc_chat_persistence.py",
        kind="replace",
        anchor="    if session is None:",
        # 该行在 get_history_entries 与 clear_history 中各一次；用 get_history_entries
        # 独有的后随行相对定位（offset=-2 回到目标行）。
        scope="    return await persistence.load_recent_history(",
        offset=-2,
        new="    if True:",
        want="test_doc_facade_history_resolves_with_and_without_year",
        why=(
            "宿主门面读历史时恒走空分支 ⇒ 端点永远返回空历史（「重启不丢」的能力"
            "静默失效，而端点仍然 200）。这类「静默取空」是 fail-open 最常见的表现，"
            "只断言 HTTP 状态或字段形状的判据抓不到。"
        ),
        tags=("req4.10",),
    ),
    # ── 迁移文件：只有"读文件"的判据才可能被它打红（见模块 docstring）─────
    Mut(
        id="M17",
        side="be",
        path=MIGRATION,
        kind="replace",
        anchor="            'v1|' || s.user_id::text",
        new="            'v2|' || s.user_id::text",
        want="test_session_key_sql_backfill_matches_python",
        why=(
            "迁移回填表达式的算法版本段与 Python 侧漂移 ⇒ 存量行算出的 session_key "
            "与运行时算出的不一致，同一会话变两行、历史分裂。守卫在真实 PG 上对两侧"
            "求值比对，不是比字符串长得像。"
        ),
        tags=("req4.11",),
    ),
    Mut(
        id="M18",
        side="be",
        path=MIGRATION,
        kind="replace",
        anchor="               ORDER BY s.total_messages DESC NULLS LAST, s.created_at ASC, s.id ASC",
        # 合并步骤有两个逐字相同的 CTE（改挂消息 + 删败者），用后随的
        # `UPDATE ai_chat_message m` 相对定位到第一个（offset=-5）。
        scope="UPDATE ai_chat_message m",
        offset=-5,
        new="               ORDER BY s.created_at ASC",
        want="test_migration_records_dedup_rule_and_orders_backfill_before_unique_index",
        why=(
            "去重规则从三级排序退化为一级 ⇒ 并列时胜者不确定（同一份数据两次执行可能"
            "选出不同胜者、丢不同的会话）。规则必须可复现。"
        ),
        tags=("req4.11",),
    ),
    Mut(
        id="M19",
        side="be",
        path=MIGRATION,
        kind="replace",
        anchor="    session_id         UUID         NOT NULL REFERENCES ai_chat_session(id) ON DELETE RESTRICT,",
        new="    session_id         UUID         NOT NULL REFERENCES ai_chat_session(id) ON DELETE CASCADE,",
        want="test_attachment_session_fk_is_restrict_so_metadata_never_orphans_files",
        why=(
            "附件→会话外键改回 CASCADE ⇒ clear session 把附件 metadata 连带删掉，"
            "storage/ai_chat/ 下的物理文件变成无人追踪的孤儿 —— 正是 Req 7.9 要防的"
            "形态。该判据同时读 live PG 的删除规则**与**迁移声明，故文件变异也能打红。"
        ),
        tags=("req7.3",),
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="dsh-agent-panel-integration Task 3 持久化守卫变异检验",
            backend_args=BE_PYTEST_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
        )
    )
