"""Published sheet artifact reader 守卫。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from openpyxl import Workbook

from app.services.workpaper_sync.sheet_published_artifact import (
    PublishedSheetArtifactError,
    read_current_published_sheet_artifact,
)


class _Result:
    """够用的结果替身：`first()` 给 representation join 行，`scalar_one_or_none()`
    给 bundle 行（task 2.5 的 drift 检测会查一次 bundle）。"""

    def __init__(self, row, scalar=None):
        self.row = row
        self.scalar = scalar

    def first(self):
        return self.row

    def scalar_one_or_none(self):
        return self.scalar


class _Session:
    """按「语句里有没有 bundle 表」分派返回。

    🔴 不能用 `statement` 的字符串形态判（`select(Model)` 的 `str()` 是模型名，
    版本间会变）；这里用 `statement` 的 column_descriptions 里出现的实体名判，
    与真实 SQLAlchemy 行为同源。
    """

    def __init__(self, row, *, bundle_digest: str | None = None):
        self.row = row
        self.statement = None
        self.bundle_digest = bundle_digest

    async def execute(self, statement):
        self.statement = statement
        names = " ".join(
            str(desc.get("entity")) for desc in getattr(statement, "column_descriptions", [])
        )
        if "DefinitionBundle" in names:
            if self.bundle_digest is None:
                return _Result(None, scalar=None)
            return _Result(None, scalar=SimpleNamespace(
                canonical_payload_sha256=self.bundle_digest,
            ))
        return _Result(self.row)


class _Artifacts:
    def __init__(self, path: Path):
        self.path = path
        self.calls = []

    def resolve_published_artifact(self, **kwargs):
        self.calls.append(("resolve", kwargs))
        return self.path

    def sha256_of_file(self, path: Path):
        return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size


def _xlsx(tmp_path: Path) -> tuple[Path, str, int]:
    path = tmp_path / "published.xlsx"
    workbook = Workbook()
    workbook.active.title = "K11-1"
    workbook.create_sheet("Other")
    workbook.save(path)
    raw = path.read_bytes()
    return path, hashlib.sha256(raw).hexdigest(), len(raw)


def _rows(path: Path, digest: str, size: int):
    project_id, wp_id, representation_id, artifact_id = (uuid4() for _ in range(4))
    bundle_id = uuid4()
    representation = SimpleNamespace(
        id=representation_id,
        wp_id=wp_id,
        entry_id="xlsx/gt-k11-asset-impairment-loss",
        artifact_id=artifact_id,
        generation=3,
        definition_bundle_id=bundle_id,
        definition_bundle_sha256="a" * 64,
        adapter_id="k11.asset_impairment_loss_adjustment",
    )
    artifact = SimpleNamespace(
        id=artifact_id,
        kind="canonical",
        state="published",
        relative_path=".versions/wp/representations/k11.xlsx",
        sha256=digest,
        size_bytes=size,
        document_type="xlsx",
    )
    return (
        project_id, wp_id, representation_id,
        # 默认让 bundle 现算 digest 等于冻结值（正常路径）；漂移用例单独覆盖。
        _Session((representation, artifact), bundle_digest="a" * 64),
    )


@pytest.mark.asyncio
async def test_reads_current_published_artifact_and_target_sheet(tmp_path: Path):
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        assert entry_id == "xlsx/gt-k11-asset-impairment-loss"
        return representation_id

    result = await read_current_published_sheet_artifact(
        session=session,
        artifact_repository=artifacts,
        project_id=project_id,
        wp_id=wp_id,
        entry_id="xlsx/gt-k11-asset-impairment-loss",
        target_sheet="K11-1",
        whole_workbook=False,
        resolve_representation=current,
    )

    assert result.path == path
    assert result.sheet_names == ("K11-1", "Other")
    assert result.target_sheet == "K11-1"
    assert result.generation == 3
    assert artifacts.calls[0][1]["kind"] == "canonical"
    assert artifacts.calls[0][1]["state"] == "published"


@pytest.mark.asyncio
async def test_missing_target_sheet_fails_without_template_fallback(tmp_path: Path):
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return representation_id

    with pytest.raises(PublishedSheetArtifactError, match="目标 sheet") as exc:
        await read_current_published_sheet_artifact(
            session=session,
            artifact_repository=artifacts,
            project_id=project_id,
            wp_id=wp_id,
            entry_id="xlsx/gt-k11-asset-impairment-loss",
            target_sheet="Missing",
            whole_workbook=False,
            resolve_representation=current,
        )
    assert exc.value.error_code == "target_sheet_not_in_published_artifact"


@pytest.mark.asyncio
async def test_digest_drift_fails_before_ooxml_read(tmp_path: Path):
    path, _digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, "b" * 64, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return representation_id

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
    assert exc.value.error_code == "artifact_digest_drift"


@pytest.mark.asyncio
async def test_no_current_representation_is_visible_failure(tmp_path: Path):
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, _representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return None

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
    assert exc.value.error_code == "current_representation_missing"


# ═══════════════════════════════════════════════════════════════════════════
# task 2.5：typed error + 中文原因
#
# 🔴 为什么「有 error_code」不算完：前端 `catch` 后必须有话可说，而且每条原因要能区分
# **用户下一步做什么**。`current_representation_missing`（去结构化视图保存一次）与
# `artifact_not_published`（等审批）看起来都是「没有文件」，合成一句话用户就会照着做错事。
# ═══════════════════════════════════════════════════════════════════════════


#: 本 spec Requirement 2.3 / 3.3 点名的失败形态。缺一条即红。
_REQUIRED_ERROR_CODES = (
    "current_representation_missing",
    "representation_row_missing",
    "artifact_not_published",
    "artifact_candidate_rejected",
    "artifact_path_unresolvable",
    "artifact_missing",
    "artifact_digest_drift",
    "artifact_ooxml_unreadable",
    "target_sheet_not_in_published_artifact",
    "target_sheet_document_type_mismatch",
    "definition_bundle_drift",
)


def test_every_required_failure_has_a_chinese_reason() -> None:
    """每条 error_code 都必须有中文原因，且不能是兜底那句。"""
    from app.services.workpaper_sync.sheet_published_artifact import (
        DEFAULT_UNKNOWN_REASON,
        PUBLISHED_SHEET_ARTIFACT_REASONS,
    )

    missing = [code for code in _REQUIRED_ERROR_CODES if code not in PUBLISHED_SHEET_ARTIFACT_REASONS]
    assert not missing, f"这些 error_code 没有中文原因：{missing}"
    for code in _REQUIRED_ERROR_CODES:
        reason = PUBLISHED_SHEET_ARTIFACT_REASONS[code]
        assert reason.strip(), f"{code} 的原因为空"
        assert reason != DEFAULT_UNKNOWN_REASON, f"{code} 落到了兜底文案"
        # 必须是中文（至少含一个 CJK 字符），且给出可操作的下一步。
        assert any("\u4e00" <= ch <= "\u9fff" for ch in reason), f"{code} 的原因不是中文：{reason}"
        assert any(
            hint in reason for hint in ("请", "联系", "等待", "刷新")
        ), f"{code} 的原因没给出下一步动作：{reason}"


def test_reasons_are_pairwise_distinct_for_different_remedies() -> None:
    """不同处置方式的失败不许共用同一句文案。

    「保存一次以发布首版」与「等审批完成」是两种完全不同的动作 —— 合成一句会让用户
    在「自己的编辑还没发布」时去等审批，白等。
    """
    from app.services.workpaper_sync.sheet_published_artifact import (
        PUBLISHED_SHEET_ARTIFACT_REASONS,
    )

    pair = (
        PUBLISHED_SHEET_ARTIFACT_REASONS["current_representation_missing"],
        PUBLISHED_SHEET_ARTIFACT_REASONS["artifact_not_published"],
    )
    assert pair[0] != pair[1]
    drift = PUBLISHED_SHEET_ARTIFACT_REASONS["artifact_digest_drift"]
    # 漂移不是「重试就好」—— 那只会一直漂。
    assert "重试" not in drift, f"漂移的原因不该让人重试：{drift}"
    assert "不要继续编辑" in drift, f"漂移必须明确劝阻继续编辑：{drift}"


def test_error_carries_both_code_and_reason() -> None:
    """`as_dict()` 必须同时给三样：机器可读 code、可展示中文 reason、排障 detail。"""
    err = PublishedSheetArtifactError("artifact_digest_drift", "登记 vs 现读 不一致")
    body = err.as_dict()
    assert body["error_code"] == "artifact_digest_drift"
    assert "不要继续编辑" in body["reason"]
    assert "登记 vs 现读" in body["detail"]


def test_unknown_code_falls_back_to_a_safe_chinese_reason() -> None:
    """未登记 code 不得静默给空串 —— 空 reason 会让前端显示一个只有图标的错误。"""
    from app.services.workpaper_sync.sheet_published_artifact import DEFAULT_UNKNOWN_REASON

    err = PublishedSheetArtifactError("something_new", "detail")
    assert err.reason == DEFAULT_UNKNOWN_REASON
    assert err.reason.strip()
    # 兜底不许说「重试」：未登记意味着不知道该怎么修，让用户反复试只消耗他的时间。
    assert "重试" not in err.reason


@pytest.mark.asyncio
async def test_candidate_artifact_is_refused_with_its_own_code(tmp_path: Path):
    """candidate 与「state 不是 published」分两类（candidate 是正常流程中间态）。"""
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)
    # 把 artifact 的 state 改成 candidate
    _representation, artifact = session.row
    artifact.state = "candidate"

    async def current(_session, *, entry_id):
        return representation_id

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
    assert "候选版本" in exc.value.reason


@pytest.mark.asyncio
async def test_missing_file_on_disk_has_its_own_code(tmp_path: Path):
    """路径可解析但文件不在 ⇒ `artifact_missing`（不是 `path_unresolvable`）。

    合成一条会让运维去改根本没坏的存储配置，而真正要做的是恢复/重新发布文件。
    """
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    artifacts = _Artifacts(path)
    artifacts.path = tmp_path / "gone.xlsx"  # 解析得到但文件不存在

    async def current(_session, *, entry_id):
        return representation_id

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
    assert exc.value.error_code == "artifact_missing"
    assert "磁盘" in exc.value.reason


@pytest.mark.asyncio
async def test_definition_bundle_drift_is_refused_before_ooxml_read(tmp_path: Path):
    """bundle 现算 digest ≠ representation 冻结值 ⇒ 先拒，别等到开 room 才失败。

    🔴 这条缺了的后果：`/sync/entry-identity` 会对一份「bundle 已被 alias 换掉内容」的
    representation 报 `room_ready`，用户点进去才在 room 打开处报错 —— 看到的是
    「说是能用、点进去报错」。
    """
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    session.bundle_digest = "b" * 64  # 与 representation 的 "a"*64 不等
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return representation_id

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
    assert exc.value.error_code == "definition_bundle_drift"
    assert "被替换过内容" in str(exc.value)


@pytest.mark.asyncio
async def test_bundle_row_absent_is_not_treated_as_drift(tmp_path: Path):
    """bundle 行不存在是上游的 missing 类问题，不是漂移 —— 别在这里误报。"""
    path, digest, size = _xlsx(tmp_path)
    project_id, wp_id, representation_id, session = _rows(path, digest, size)
    session.bundle_digest = None  # 查不到 bundle 行
    artifacts = _Artifacts(path)

    async def current(_session, *, entry_id):
        return representation_id

    result = await read_current_published_sheet_artifact(
        session=session,
        artifact_repository=artifacts,
        project_id=project_id,
        wp_id=wp_id,
        entry_id="xlsx/gt-k11-asset-impairment-loss",
        target_sheet="K11-1",
        whole_workbook=False,
        resolve_representation=current,
    )
    assert result.generation == 3
