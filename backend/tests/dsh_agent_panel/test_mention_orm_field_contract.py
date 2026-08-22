"""Mention 取数的 ORM 字段契约守卫

## 为什么需要这组守卫

`mention_service.py` 曾同时引用 **9 个不存在的 ORM 属性**：

| 代码里写的                        | 模型上的真实列                    |
|-----------------------------------|-----------------------------------|
| `DisclosureNote.section_number`   | `note_section`                    |
| `DisclosureNote.content`          | `text_content` / `table_data`     |
| `FinancialReport.report_name`     | 无（行级表，只有 `row_name`）      |
| `FinancialReport.content`         | 无                                |
| `KnowledgeDocument.title` (×2)    | `name`                            |
| `KnowledgeDocument.project_id`    | `project_ids`（JSONB）            |
| `KnowledgeDocument.content`       | `content_text`                    |
| `KnowledgeFolder.project_id`      | `project_ids`（JSONB）            |
| `WorkingPaper.content`            | `parsed_data` / `file_path`       |

后果是 7 类 mention 里 4 类**恒 error**、底稿正文**恒进不了上下文**，而：

- `asyncio.gather(return_exceptions=True)` 把 AttributeError 收成 `type_status='error'`
- 前端只在"所有类型都 unavailable"时才提示，单类 error 被吞成 `success`
- 界面统一显示"无匹配结果"，看起来像"库里没数据"

四层（Volar / vitest / pytest / 类型检查）全绿，只有真跑一次 SQL 才暴露。

## 守卫策略

用 AST 提取源码里**全部** `Model.attr` 引用再逐个 `hasattr` 核验 —— 不维护手写清单，
因此将来新增的取数代码自动被覆盖。这是"行为/结构判据"而不是"字符串存在判据"：
把字段名改错一个字母就会红。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
from app.models.report_models import DisclosureNote, FinancialReport
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.ai_chat.contracts import REPORT_HOST_IDS, ResourceType
from app.services.ai_chat.host_context import REPORT_LABELS
from app.services.ai_chat.mention_service import (
    PROJECT_REQUIRED_MENTION_TYPES,
    MentionTypeStatus,
)

#: 参与 mention / 上下文取数的业务模型（名称 → 类）。
_MODELS = {
    "WorkingPaper": WorkingPaper,
    "WpIndex": WpIndex,
    "DisclosureNote": DisclosureNote,
    "FinancialReport": FinancialReport,
    "KnowledgeDocument": KnowledgeDocument,
    "KnowledgeFolder": KnowledgeFolder,
}

#: 被扫描的取数源码（mention 搜索 + 正文加载两条路径）。
_BACKEND = Path(__file__).resolve().parents[2]
_SCANNED_SOURCES = [
    _BACKEND / "app" / "services" / "ai_chat" / "mention_service.py",
    _BACKEND / "app" / "services" / "doc_ai_context_builder.py",
    _BACKEND / "app" / "services" / "ai_chat" / "host_context.py",
]

#: SQLAlchemy 模型类上合法的非列属性（不参与列存在性判定）。
_ALLOWED_NON_COLUMN = {"__tablename__", "__mapper__", "__table__", "metadata"}


def _collect_model_attribute_refs(source: Path) -> list[tuple[str, str, int]]:
    """提取 ``Model.attr`` 形式的引用 → [(模型名, 属性名, 行号)]。"""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    refs: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.value, ast.Name):
            continue
        model_name = node.value.id
        if model_name not in _MODELS:
            continue
        if node.attr in _ALLOWED_NON_COLUMN:
            continue
        refs.append((model_name, node.attr, node.lineno))
    return refs


@pytest.mark.parametrize("source", _SCANNED_SOURCES, ids=lambda p: p.name)
def test_all_referenced_orm_attributes_exist(source: Path) -> None:
    """取数源码引用的每一个 ORM 属性都必须真实存在于模型上。

    这是本次修复的核心守卫：把任一字段名改错（如 ``note_section`` → ``section_number``）
    即打红，而不必连库、不必真发请求。
    """
    assert source.exists(), f"待扫描源码不存在: {source}"

    refs = _collect_model_attribute_refs(source)
    assert refs, (
        f"{source.name} 未扫到任何 Model.attr 引用 —— 说明扫描器失效（锚点漂移），"
        "不是代码真的不取数；这种情况必须当失败处理，否则守卫恒真。"
    )

    missing: list[str] = []
    for model_name, attr, lineno in refs:
        model = _MODELS[model_name]
        if not hasattr(model, attr):
            columns = sorted(c.key for c in model.__mapper__.column_attrs)
            missing.append(
                f"{source.name}:{lineno} 引用了不存在的 {model_name}.{attr}；"
                f"该模型实际列: {', '.join(columns)}"
            )

    assert not missing, "存在不存在的 ORM 属性引用（会被 fail-open 吞成空结果）:\n" + "\n".join(
        missing
    )


def test_scanner_actually_detects_a_bad_attribute() -> None:
    """扫描器反向自检：故意写错的属性必须被判定为缺失。

    没有这条，上面的守卫可能因为扫描器坏掉而恒绿（假绿第③源）。
    """
    bogus = "section_number_that_does_not_exist"
    assert not hasattr(DisclosureNote, bogus), "自检用的假字段竟然存在，请换一个"

    src = ast.parse(f"x = DisclosureNote.{bogus}\n")
    found = [
        n.attr
        for n in ast.walk(src)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name)
        and n.value.id == "DisclosureNote"
    ]
    assert found == [bogus], "扫描器无法提取 Model.attr 引用"


def test_historical_wrong_fields_stay_gone() -> None:
    """历史上写错的 9 个属性不得再出现在任何取数源码的**可执行代码**里。

    docstring 里提及旧字段名是允许的（本次修复特意留了说明），所以这里只看
    AST 提取出的真实引用，不做字符串包含判断。
    """
    historical_mistakes = {
        ("DisclosureNote", "section_number"),
        ("DisclosureNote", "content"),
        ("FinancialReport", "report_name"),
        ("FinancialReport", "content"),
        ("KnowledgeDocument", "title"),
        ("KnowledgeDocument", "project_id"),
        ("KnowledgeDocument", "content"),
        ("KnowledgeFolder", "project_id"),
        ("WorkingPaper", "content"),
    }

    regressions: list[str] = []
    for source in _SCANNED_SOURCES:
        for model_name, attr, lineno in _collect_model_attribute_refs(source):
            if (model_name, attr) in historical_mistakes:
                regressions.append(f"{source.name}:{lineno} {model_name}.{attr}")

    assert not regressions, (
        "历史错误字段回归（这些属性在模型上不存在，会让整类 mention 恒 error）:\n"
        + "\n".join(regressions)
    )


def test_project_required_types_cover_exactly_project_bound_resources() -> None:
    """需要项目绑定的类型 = 四类项目资源；知识资产可跨项目共享不得列入。

    取值域是前后端共享契约，前端 `useAiMention.PROJECT_REQUIRED_MENTION_TYPES`
    镜像本集合并由 vitest 对账。
    """
    assert PROJECT_REQUIRED_MENTION_TYPES == frozenset(
        {
            ResourceType.workpaper,
            ResourceType.note,
            ResourceType.report,
            ResourceType.address,
        }
    )
    # 知识资产不受项目绑定限制（access_level=public 的公共知识全所可引用）
    assert ResourceType.knowledge_doc not in PROJECT_REQUIRED_MENTION_TYPES
    assert ResourceType.knowledge_folder not in PROJECT_REQUIRED_MENTION_TYPES


def test_project_required_status_distinct_from_empty() -> None:
    """`project_required` 必须是独立状态，不能复用 `empty`。

    混用会让受限全局知识模式下的"未绑定项目"显示成"无匹配结果"。
    """
    assert MentionTypeStatus.project_required.value == "project_required"
    assert MentionTypeStatus.project_required is not MentionTypeStatus.empty
    values = {s.value for s in MentionTypeStatus}
    assert {"success", "empty", "error", "unavailable", "timeout", "project_required"} == values


def test_report_labels_cover_every_report_host_id() -> None:
    """报表 mention 候选按方案 A 由常量真源生成 ⇒ 每个 report_type 都必须有中文名。

    缺一个就会在候选列表里露出 `cash_flow_supplement` 这类英文字面量（违反全中文 UI）。
    """
    missing = sorted(REPORT_HOST_IDS - set(REPORT_LABELS))
    assert not missing, f"以下 report_type 缺中文名: {missing}"
    for report_type in REPORT_HOST_IDS:
        label = REPORT_LABELS[report_type]
        assert label and not label.isascii(), f"{report_type} 的展示名应为中文，实际 {label!r}"


# ---------------------------------------------------------------------------
# 行为守卫：无项目绑定时的 project_required 前置判断
#
# 上面的 test_project_required_status_distinct_from_empty 只证明"枚举里有这个取值"，
# 不证明 search() 真的用上了它 —— 那属于 additive 死代码风险（假绿第①源）。
# 这里真调一次 search()，断言四类项目资源被前置标记，且**不发出任何查询**。
# ---------------------------------------------------------------------------


def _global_knowledge_host() -> object:
    """构造受限全局知识模式的宿主上下文（project_id 恒 None，由契约强制）。"""
    import uuid

    from app.services.ai_chat.contracts import GLOBAL_KNOWLEDGE_HOST_ID, HostType
    from app.services.ai_chat.host_context import AuthorizedHostContext

    return AuthorizedHostContext(
        principal_id=uuid.uuid4(),
        project_id=None,
        year=None,
        resource_type=HostType.global_knowledge,
        resource_id=GLOBAL_KNOWLEDGE_HOST_ID,
        display_label="全局知识库（无项目上下文）",
        permission_binding="global:knowledge_readonly",
        allowed_actions=frozenset({"read", "search"}),
    )


@pytest.mark.asyncio
async def test_unbound_project_reports_project_required_without_querying() -> None:
    """受限全局知识模式：四类项目资源报 project_required，且不触碰数据库。

    ``db`` 传 None：若前置判断失效而代码继续去查库，会抛 AttributeError 并被
    ``gather`` 收成 ``error`` ⇒ 断言立即失败。因此本测试同时证明
    "标记正确" 与 "确实短路了、没白跑查询"。
    """
    from app.services.ai_chat.mention_service import MentionSearchService

    class _FakeUser:
        id = __import__("uuid").uuid4()
        role = "audit_assistant"

    service = MentionSearchService(None)  # type: ignore[arg-type]
    result = await service.search(
        user=_FakeUser(),
        host=_global_knowledge_host(),  # type: ignore[arg-type]
        query="存货",
    )

    for resource_type in PROJECT_REQUIRED_MENTION_TYPES:
        actual = result.type_status.get(resource_type.value)
        assert actual == MentionTypeStatus.project_required.value, (
            f"{resource_type.value} 在无项目绑定时应报 project_required，实际 {actual!r}；"
            "报 empty 会让用户以为库里没有这类资源"
        )

    # 反向对照：知识资产不受项目绑定限制，不该被前置短路
    for resource_type in (ResourceType.knowledge_doc, ResourceType.knowledge_folder):
        actual = result.type_status.get(resource_type.value)
        assert actual != MentionTypeStatus.project_required.value, (
            f"{resource_type.value} 可跨项目共享，不应报 project_required（实际 {actual!r}）"
        )

    assert not result.items, "无项目绑定时不应返回任何项目资源候选"


@pytest.mark.asyncio
async def test_project_bound_host_does_not_short_circuit() -> None:
    """反向对照：有项目绑定时四类**不得**被标记 project_required（防恒真）。

    传 None db ⇒ 各类型会因无法查库而落到 ``error``；关键是它们必须**尝试过**，
    而不是被前置短路成 project_required。
    """
    import uuid

    from app.services.ai_chat.contracts import HostType
    from app.services.ai_chat.host_context import AuthorizedHostContext
    from app.services.ai_chat.mention_service import MentionSearchService

    class _FakeUser:
        id = uuid.uuid4()
        role = "audit_assistant"

    host = AuthorizedHostContext(
        principal_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        year=2025,
        resource_type=HostType.workpaper,
        resource_id=str(uuid.uuid4()),
        display_label="D2-1 应收账款审定表",
        permission_binding="workpaper:gate_wp",
        allowed_actions=frozenset({"read", "search"}),
    )

    result = await MentionSearchService(None).search(  # type: ignore[arg-type]
        user=_FakeUser(), host=host, query="存货"
    )

    for resource_type in PROJECT_REQUIRED_MENTION_TYPES:
        actual = result.type_status.get(resource_type.value)
        assert actual != MentionTypeStatus.project_required.value, (
            f"有项目绑定时 {resource_type.value} 竟被短路成 project_required（实际 {actual!r}）"
        )


# ---------------------------------------------------------------------------
# 行为守卫：报表候选（方案 A）
#
# 上面的 test_report_labels_cover_every_report_host_id 只证明"常量表齐全"，
# 不证明 _search_reports 真的用了它 —— 变异检验里把 label 来源换成英文字面量、
# 或删掉"未生成不进候选"的校验，那条测试都不会红。
#
# 这里用 fake db 直接驱动 _search_reports，断言三件事：
#   ① 候选 id 取自 REPORT_HOST_IDS 枚举真源
#   ② label 是中文（全中文 UI）
#   ③ 该项目**未生成**的报表不进候选（不让用户引用一张空表）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _FakeDb:
    """只回放预置行的最小 db 替身（_search_reports 只做一次 execute().all()）。"""

    def __init__(self, rows: list) -> None:
        self._rows = rows
        self.execute_count = 0

    async def execute(self, *_args, **_kwargs) -> _FakeResult:
        self.execute_count += 1
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_report_candidates_come_from_enum_with_chinese_labels() -> None:
    """报表候选 = 已生成的 report_type ∩ 枚举真源，label 为中文名。"""
    import uuid
    from collections import namedtuple

    from app.services.ai_chat.mention_service import MentionSearchService

    Row = namedtuple("Row", ["report_type", "latest_year"])
    # 只生成了两张报表
    generated = [Row("balance_sheet", 2025), Row("income_statement", 2025)]
    db = _FakeDb(generated)

    service = MentionSearchService(db)  # type: ignore[arg-type]
    out = await service._search_reports("%", uuid.uuid4(), 10)

    ids = {c.id for c in out}
    labels = {c.label for c in out}

    # ① 只出已生成的两张，未生成的四张不得出现
    assert ids == {"balance_sheet", "income_statement"}, (
        f"未生成的报表不应进候选（用户会引用到空表），实际 {sorted(ids)}"
    )
    # ② id 必须是枚举真源里的稳定标识（不是 UUID、不是行号）
    assert ids <= REPORT_HOST_IDS

    # ③ label 必须是中文名，不能漏出 report_type 英文字面量
    assert labels == {"资产负债表", "利润表"}, f"label 应为中文名，实际 {labels}"
    for candidate in out:
        assert not candidate.label.isascii(), (
            f"{candidate.id} 的 label 是 {candidate.label!r} —— 英文字面量违反全中文 UI"
        )
        assert candidate.jump_route == f"/reports/{candidate.id}"


@pytest.mark.asyncio
async def test_report_candidates_match_by_chinese_keyword() -> None:
    """关键词按**中文名**匹配（用户不会输 `balance_sheet`）。"""
    import uuid
    from collections import namedtuple

    from app.services.ai_chat.mention_service import MentionSearchService

    Row = namedtuple("Row", ["report_type", "latest_year"])
    generated = [
        Row("balance_sheet", 2025),
        Row("income_statement", 2025),
        Row("cash_flow_statement", 2025),
    ]

    service = MentionSearchService(_FakeDb(generated))  # type: ignore[arg-type]
    out = await service._search_reports("%现金流量%", uuid.uuid4(), 10)

    assert [c.label for c in out] == ["现金流量表"], (
        f"中文关键词应精确命中，实际 {[c.label for c in out]}"
    )


@pytest.mark.asyncio
async def test_report_candidates_empty_when_nothing_generated() -> None:
    """该项目一张报表都没生成 ⇒ 零候选（而不是把六张全列出来）。"""
    import uuid

    from app.services.ai_chat.mention_service import MentionSearchService

    service = MentionSearchService(_FakeDb([]))  # type: ignore[arg-type]
    out = await service._search_reports("%", uuid.uuid4(), 10)
    assert out == [], "未生成任何报表时不得凭空列出候选"
