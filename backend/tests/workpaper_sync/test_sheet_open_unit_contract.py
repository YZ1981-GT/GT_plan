"""task 5.1：sheet 打开链路的后端 unit / contract 判据总纲。

spec: `onlyoffice-sheet-open-via-published-artifact` task 5.1
Requirements: 1, 2, 7

═══ 这个文件解决什么问题 ═══

spec 5.1 点名 7 类判据：mapping 唯一性、scope、target sheet、current representation、
candidate 拒绝、path boundary、typed error。它们**分散在 6 个文件**里（1.x / 2.x 各任务
的产物）。

分散的后果：某类判据被删掉（重构 / 误删）时**没有任何东西会发现** —— 剩下的判据照常
全绿，而那一类保证已经消失。本文件提供两样东西：

1. **判据清单守卫**：每类判据必须至少有一条**真实的**测试函数（不是关键词命中）；
2. **真实缺口补齐**：`path boundary` 此前只有关键词命中而无真测试 —— 补三条
   （跨项目、跨底稿、路径逃逸）。

═══ 为什么清单是「函数名 + 所属文件」而不是自由文本 ═══

自由文本的清单会腐化（改名后没人更新）。这里逐条断言「该函数在**该文件**里真实存在」，
改名/删除都会红，从而强制同步 —— 那是清单唯一有意义的状态。
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[2]
TESTS_DIR = BACKEND / "tests" / "workpaper_sync"


#: spec 5.1 点名的 7 类判据 → (判据标签, [(测试文件, 测试函数)])
#:
#: 🔴 每一条都必须指向**真实存在**的测试函数。清单腐化时下面的
#: `test_every_required_judgement_has_a_real_test` 会红。
JUDGEMENT_COVERAGE: dict[str, tuple[str, ...]] = {
    "mapping 唯一性": (
        "test_sheet_open_bindings.py::test_effective_entry_id_is_never_a_forged_parent_fallback",
        "test_sheet_open_binding_resolver.py::test_duplicate_exact_bindings_are_ambiguous",
    ),
    "scope（single_sheet / whole_workbook 封闭域）": (
        "test_sheet_descriptor_view_identity.py::test_document_scopes_enum_is_exactly_two_values",
        "test_sheet_descriptor_view_identity.py::test_whole_workbook_with_target_sheet_is_refused",
    ),
    "target sheet（必须在 published artifact 里）": (
        "test_sheet_published_artifact.py::test_missing_target_sheet_fails_without_template_fallback",
        "test_sheet_descriptor_view_identity.py::test_valid_single_sheet_and_whole_workbook_both_construct",
    ),
    "current representation（candidate 不得冒充）": (
        "test_sheet_published_artifact.py::test_no_current_representation_is_visible_failure",
        "test_sheet_published_artifact.py::test_candidate_artifact_is_refused_with_its_own_code",
    ),
    "candidate 拒绝": (
        "test_sheet_published_artifact.py::test_candidate_artifact_is_refused_with_its_own_code",
    ),
    "path boundary（跨项目 / 跨底稿 / 路径逃逸）": (
        "test_sheet_open_unit_contract.py::test_artifact_from_another_project_is_refused",
        "test_sheet_open_unit_contract.py::test_artifact_from_another_workpaper_is_refused",
        "test_sheet_open_unit_contract.py::test_path_escape_outside_published_root_is_refused",
    ),
    "typed error（code + 中文原因）": (
        "test_sheet_published_artifact.py::test_every_required_failure_has_a_chinese_reason",
        "test_sheet_published_artifact.py::test_error_carries_both_code_and_reason",
    ),
}


def _test_function_exists(file_name: str, func_name: str) -> bool:
    """该文件里是否有这个测试函数（允许装饰器与 `async def`）。"""
    path = TESTS_DIR / file_name
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return bool(
        re.search(
            rf"^(?:@[^\n]*\n)*(?:async\s+)?def {re.escape(func_name)}\b", text, re.M
        )
    )


@pytest.mark.parametrize("label", sorted(JUDGEMENT_COVERAGE))
def test_every_required_judgement_has_a_real_test(label: str) -> None:
    """spec 5.1 点名的每一类判据都必须有**真实存在**的测试函数。

    🔴 判据不是「关键词出现过」—— 那是最容易假绿的形态（注释里提一句就算）。
    本判据逐条查函数定义。
    """
    entries = JUDGEMENT_COVERAGE[label]
    assert entries, f"{label} 没有任何测试登记 —— 该类保证不存在"
    missing: list[str] = []
    for entry in entries:
        file_name, func_name = entry.split("::", 1)
        if not _test_function_exists(file_name, func_name):
            missing.append(entry)
    assert not missing, (
        f"{label} 的判据不存在（改名或删除后必须同步本清单）：{missing}"
    )


def test_coverage_map_has_exactly_the_seven_named_judgements() -> None:
    """分母守卫：清单必须恰好覆盖 spec 5.1 点名的 7 类。

    少一类就少一类保证；多出来的类别说明清单在膨胀（有人往里塞不相关的东西）。
    """
    assert len(JUDGEMENT_COVERAGE) == 7, (
        f"应恰好 7 类判据，实得 {len(JUDGEMENT_COVERAGE)}：{sorted(JUDGEMENT_COVERAGE)}"
    )


def test_no_judgement_relies_on_a_single_test() -> None:
    """除 candidate 拒绝（本身就是一条精确判据）外，每类至少 2 条测试。

    🔴 单条测试的脆弱性：一条断言写得不够严时整类保证就空了。两条以上才有交叉验证。
    """
    thin = [
        label for label, entries in JUDGEMENT_COVERAGE.items()
        if len(entries) < 2 and label != "candidate 拒绝"
    ]
    assert not thin, f"这些判据只有一条测试（易假绿）：{thin}"


# ═══════════════════════════════════════════════════════════════════════════
# 真实缺口：path boundary 此前只有关键词命中而无真测试
#
# spec 5.1 点名「path boundary」，Requirement 7.3 要求「跨项目、跨底稿、历史 candidate、
# incoming artifact 与模板库路径必须 fail-closed」。2.3 的 reader 把边界校验**委托**给
# `CanonicalArtifactRepository.resolve_published_artifact` —— 那是对的（单一实现），
# 但**委托不等于被验证**：委托方抛错时 reader 是否真的 fail-closed 没人测过。
#
# 下面三条在 reader 的层面验证「委托失败 ⇒ 不回退、不静默」。
# ═══════════════════════════════════════════════════════════════════════════


class _RejectingArtifacts:
    """模拟 canonical resolver 的三种边界拒绝（跨项目 / 跨底稿 / 路径逃逸）。

    🔴 刻意**不**在 reader 里重写边界判定 —— 那会是第二套实现。这里只验证
    「resolver 拒绝时 reader 的行为」。
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self.calls: list[dict] = []

    def resolve_published_artifact(self, **kwargs):
        self.calls.append(kwargs)
        raise PermissionError(self.reason)

    def sha256_of_file(self, path):  # pragma: no cover - 不该被调到
        raise AssertionError("边界拒绝后不得继续读文件")


class _Row:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row

    def scalar_one_or_none(self):
        return None  # bundle 行不存在 ⇒ 不视为 drift（见 2.5）


class _Session:
    def __init__(self, row):
        self.row = row

    async def execute(self, _statement):
        return _Row(self.row)


def _fake_rows(*, project_id: UUID, wp_id: UUID, entry_id: str):
    from types import SimpleNamespace

    representation = SimpleNamespace(
        id=uuid4(),
        wp_id=wp_id,
        entry_id=entry_id,
        artifact_id=uuid4(),
        generation=1,
        definition_bundle_id=uuid4(),
        definition_bundle_sha256="a" * 64,
        adapter_id="x",
    )
    artifact = SimpleNamespace(
        id=representation.artifact_id,
        kind="canonical",
        state="published",
        relative_path=".versions/wp/representations/x.xlsx",
        sha256="b" * 64,
        size_bytes=1,
        document_type="xlsx",
        # 🔴 刻意放一个**不同的** project_id：变异 M2（从 artifact 行反推 project_id）
        # 只有在「行上的值与请求值不同」时才可观测。首版没有这个字段 ⇒
        # `getattr(artifact, 'project_id', project_id)` 回落到请求值 ⇒ 语义等价 ⇒ 变异存活。
        project_id=uuid4(),
    )
    return SimpleNamespace(project_id=project_id), _Session((representation, artifact))


async def _read_with_rejecting_resolver(*, reason: str, project_id: UUID, wp_id: UUID):
    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    _, session = _fake_rows(
        project_id=project_id, wp_id=wp_id, entry_id="xlsx/gt-k11-asset-impairment-loss"
    )
    artifacts = _RejectingArtifacts(reason)

    async def current(_session, *, entry_id):
        return session.row[0].id

    with pytest.raises(PublishedSheetArtifactError) as exc:
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="K11-1",
            whole_workbook=False,
            resolve_representation=current,
        )
    return exc.value, artifacts


@pytest.mark.asyncio
async def test_artifact_from_another_project_is_refused() -> None:
    """跨项目读取必须 fail-closed（Requirement 7.3）。

    reader 把边界委托给 canonical resolver；本条验证 resolver 拒绝时 reader
    **不回退模板、不静默返回**，而是抛 typed error。
    """
    err, artifacts = await _read_with_rejecting_resolver(
        reason="artifact 属于另一个项目", project_id=uuid4(), wp_id=uuid4()
    )
    assert err.error_code == "artifact_path_unresolvable", (
        f"跨项目应报 path_unresolvable，实得 {err.error_code}"
    )
    assert artifacts.calls, "resolver 从未被调用 —— 边界校验被绕过了"


@pytest.mark.asyncio
async def test_artifact_from_another_workpaper_is_refused() -> None:
    """跨底稿读取必须 fail-closed（同一 project 内也不行）。"""
    project_id = uuid4()
    err, artifacts = await _read_with_rejecting_resolver(
        reason="artifact 属于另一份底稿", project_id=project_id, wp_id=uuid4()
    )
    assert err.error_code == "artifact_path_unresolvable"
    # 传给 resolver 的必须是**本次请求**的 project_id（不是从 artifact 行反推的）
    assert artifacts.calls[0]["project_id"] == project_id


@pytest.mark.asyncio
async def test_path_escape_outside_published_root_is_refused() -> None:
    """`../` 逃逸 / 绝对路径注入必须 fail-closed（Requirement 7.2：客户端不得提交任意路径）。

    本条的价值：reader 的 `relative_path` 来自**数据库行**（不是客户端），但行本身可能
    被污染或历史遗留 —— resolver 必须拒绝，reader 必须如实透出 typed error。
    """
    err, artifacts = await _read_with_rejecting_resolver(
        reason="relative_path 逃出 published 根", project_id=uuid4(), wp_id=uuid4()
    )
    assert err.error_code == "artifact_path_unresolvable"
    # reader 必须把 `kind` / `state` 一并交给 resolver（那是边界判定的一部分）
    call = artifacts.calls[0]
    assert call["kind"] == "canonical"
    assert call["state"] == "published"


@pytest.mark.asyncio
async def test_boundary_rejection_does_not_fall_back_to_template() -> None:
    """边界拒绝后**不得**回退模板目录（Requirement 2.2 / 2.3）。

    🔴 这是 5.4 变异 04（恢复 template copy）的单元层对应判据：模板回退若发生在
    「路径被拒」分支上，会让跨项目读取变成「读到模板内容」—— 比报错严重得多。
    """
    err, _ = await _read_with_rejecting_resolver(
        reason="denied", project_id=uuid4(), wp_id=uuid4()
    )
    # 错误消息里不得出现任何模板路径痕迹
    message = str(err)
    assert "wp_templates" not in message, f"错误消息泄漏模板路径：{message}"
    assert err.error_code == "artifact_path_unresolvable"


# ═══════════════════════════════════════════════════════════════════════════
# 补：M2 / M3 两个真缺口（5.1 变异暴露）
# ═══════════════════════════════════════════════════════════════════════════


class _RecordingArtifacts:
    """记录 resolver 收到的参数并**按参数校验**（模拟真实 canonical resolver 的判定）。

    🔴 与 `_RejectingArtifacts` 的区别：后者无条件拒绝，所以「project_id 传错」这件事
    观察不到（都会拒）。本条按 `project_id` 是否等于期望值决定接受/拒绝 ——
    只有这样「从 artifact 行反推 project_id」才会被抓住。
    """

    def __init__(self, *, expected_project_id: UUID, expected_kind: str, expected_state: str):
        self.expected_project_id = expected_project_id
        self.expected_kind = expected_kind
        self.expected_state = expected_state
        self.calls: list[dict] = []
        self.accepted = False

    def resolve_published_artifact(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("project_id") != self.expected_project_id:
            raise PermissionError(
                f"project_id 不匹配：收到 {kwargs.get('project_id')!r}，"
                f"期望 {self.expected_project_id!r}"
            )
        if kwargs.get("kind") != self.expected_kind:
            raise PermissionError(f"kind 不匹配：{kwargs.get('kind')!r}")
        if kwargs.get("state") != self.expected_state:
            raise PermissionError(f"state 不匹配：{kwargs.get('state')!r}")
        self.accepted = True
        # 返回一个不存在的路径 ⇒ 后续走 artifact_missing 分支（本条不关心）
        from pathlib import Path as _P

        return _P("/nonexistent/published.xlsx")

    def sha256_of_file(self, path):  # pragma: no cover
        raise AssertionError("文件不存在时不该走到这里")


@pytest.mark.asyncio
async def test_project_id_passed_to_resolver_is_the_request_one() -> None:
    """传给 resolver 的 `project_id` 必须是**本次请求**的，不得从 artifact 行反推。

    🔴 为什么这条必须单独存在：`_RejectingArtifacts` 无条件拒绝 ⇒ 「传错 project_id」
    观察不到（两种实现都拒绝）⇒ 变异 M2（改成 `getattr(artifact, 'project_id', ...)`）
    存活。本用例让 resolver **按 project_id 校验**，传错就拒 ⇒ 变异必红。

    Requirement 7.1 / 7.3：服务端必须先验证归属，再读 artifact；从 artifact 行反推
    等于「用被读对象证明自己有权限读它」—— 那是循环论证。
    """
    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    project_id, wp_id = uuid4(), uuid4()
    _, session = _fake_rows(
        project_id=project_id, wp_id=wp_id, entry_id="xlsx/gt-k11-asset-impairment-loss"
    )
    # artifact 行上**故意**放一个不同的 project_id（模拟「行被污染」或「跨项目行」）
    artifacts = _RecordingArtifacts(
        expected_project_id=project_id, expected_kind="canonical", expected_state="published"
    )

    async def current(_session, *, entry_id):
        return session.row[0].id

    # 正常路径：project_id 传对 ⇒ resolver 接受（后续 artifact_missing 是预期的）
    with pytest.raises(PublishedSheetArtifactError) as exc:
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="K11-1",
            whole_workbook=False,
            resolve_representation=current,
        )
    assert artifacts.accepted, (
        "resolver 未接受本次请求的 project_id —— reader 传的不是请求值"
    )
    assert artifacts.calls[0]["project_id"] == project_id
    # 走到 artifact_missing（因为路径不存在），不是 path_unresolvable
    assert exc.value.error_code == "artifact_missing", (
        f"应走 artifact_missing，实得 {exc.value.error_code}"
    )


@pytest.mark.asyncio
async def test_kind_and_state_are_asserted_before_resolving() -> None:
    """`kind` / `state` 必须在**调 resolver 之前**校验，且断言的是 canonical + published。

    🔴 M3 变异（`if False:` 跳过 kind/state 校验）在 5.1 首轮存活 —— 因为
    `test_candidate_artifact_is_refused_with_its_own_code` 在另一个文件里，而我的
    `_RejectingArtifacts` 不检查 kind/state（无条件拒绝）⇒ 跳过校验也「看起来正常」。

    本用例让 resolver **按 kind/state 校验**：reader 传错就拒，且 reader 自己该先拒的
    （candidate）不该走到 resolver。
    """
    from types import SimpleNamespace

    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    project_id, wp_id = uuid4(), uuid4()
    _, session = _fake_rows(
        project_id=project_id, wp_id=wp_id, entry_id="xlsx/gt-k11-asset-impairment-loss"
    )
    # 把 artifact 的 state 改成 candidate
    _representation, artifact = session.row
    artifact.state = "candidate"
    artifacts = _RecordingArtifacts(
        expected_project_id=project_id, expected_kind="canonical", expected_state="published"
    )

    async def current(_session, *, entry_id):
        return session.row[0].id

    with pytest.raises(PublishedSheetArtifactError) as exc:
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="K11-1",
            whole_workbook=False,
            resolve_representation=current,
        )
    assert exc.value.error_code == "artifact_candidate_rejected"
    assert not artifacts.calls, (
        "candidate 竟走到了 resolver —— reader 的 kind/state 校验被跳过了"
    )


@pytest.mark.asyncio
async def test_published_artifact_passes_canonical_kind_and_published_state() -> None:
    """正向对照：合法 artifact 时 reader 传给 resolver 的是 canonical + published。

    没有这条，把 reader 改成「恒传 published」或「恒传 candidate」也能让上面两条通过。
    """
    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    project_id, wp_id = uuid4(), uuid4()
    _, session = _fake_rows(
        project_id=project_id, wp_id=wp_id, entry_id="xlsx/gt-k11-asset-impairment-loss"
    )
    artifacts = _RecordingArtifacts(
        expected_project_id=project_id, expected_kind="canonical", expected_state="published"
    )

    async def current(_session, *, entry_id):
        return session.row[0].id

    with pytest.raises(PublishedSheetArtifactError):
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="K11-1",
            whole_workbook=False,
            resolve_representation=current,
        )
    assert artifacts.calls, "resolver 从未被调用"
    assert artifacts.calls[0]["kind"] == "canonical"
    assert artifacts.calls[0]["state"] == "published"


@pytest.mark.asyncio
async def test_non_published_non_candidate_state_is_refused() -> None:
    """`kind`/`state` 校验针对**非 candidate 的非法态**（如 `superseded` / `incoming`）。

    🔴 为什么这条必须单独存在：`artifact_candidate_rejected` 分支在 `kind`/`state`
    校验**之前**独立拦截 candidate ⇒ 把 `kind`/`state` 校验改成 `if False:` 后
    candidate 用例仍绿（实测 M3 存活，16 条全过）。真正只有 `kind`/`state` 能拦的是
    「state 既不是 candidate 也不是 published」这一类（如 `superseded` / `incoming`）。

    Requirement 2.3 / 7.3：历史 candidate、incoming artifact 必须 fail-closed。
    """
    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    for bad_state in ("superseded", "incoming", "draft"):
        project_id, wp_id = uuid4(), uuid4()
        _, session = _fake_rows(
            project_id=project_id, wp_id=wp_id, entry_id="xlsx/gt-k11-asset-impairment-loss"
        )
        _representation, artifact = session.row
        artifact.state = bad_state
        artifacts = _RecordingArtifacts(
            expected_project_id=project_id, expected_kind="canonical", expected_state="published"
        )

        async def current(_session, *, entry_id, _rid=session.row[0].id):
            return _rid

        with pytest.raises(PublishedSheetArtifactError) as exc:
            await read_current_published_sheet_artifact(
                session=session,
                artifact_repository=artifacts,
                project_id=project_id,
                wp_id=wp_id,
                entry_id="xlsx/gt-k11-asset-impairment-loss",
                target_sheet="K11-1",
                whole_workbook=False,
                resolve_representation=current,
            )
        assert exc.value.error_code == "artifact_not_published", (
            f"state={bad_state} 应报 artifact_not_published，实得 {exc.value.error_code}"
        )
        assert not artifacts.calls, f"state={bad_state} 竟走到了 resolver"


@pytest.mark.asyncio
async def test_non_canonical_kind_is_refused() -> None:
    """`kind != canonical` 必须拒（incoming / candidate artifact 都不得当 published 读）。

    Requirement 7.3 点名「incoming artifact 必须 fail-closed」。
    """
    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    for bad_kind in ("incoming", "candidate", "scratch"):
        project_id, wp_id = uuid4(), uuid4()
        _, session = _fake_rows(
            project_id=project_id, wp_id=wp_id, entry_id="xlsx/gt-k11-asset-impairment-loss"
        )
        _representation, artifact = session.row
        artifact.kind = bad_kind
        artifacts = _RecordingArtifacts(
            expected_project_id=project_id, expected_kind="canonical", expected_state="published"
        )

        async def current(_session, *, entry_id, _rid=session.row[0].id):
            return _rid

        with pytest.raises(PublishedSheetArtifactError) as exc:
            await read_current_published_sheet_artifact(
                session=session,
                artifact_repository=artifacts,
                project_id=project_id,
                wp_id=wp_id,
                entry_id="xlsx/gt-k11-asset-impairment-loss",
                target_sheet="K11-1",
                whole_workbook=False,
                resolve_representation=current,
            )
        assert exc.value.error_code == "artifact_not_published", (
            f"kind={bad_kind} 应报 artifact_not_published，实得 {exc.value.error_code}"
        )
        assert not artifacts.calls, f"kind={bad_kind} 竟走到了 resolver"
