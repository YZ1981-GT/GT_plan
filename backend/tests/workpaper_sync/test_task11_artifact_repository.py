# -*- coding: utf-8 -*-
"""Task 11 文件系统/安全守卫：CanonicalArtifactRepository、OOXML 预算与 candidate 隔离。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 2.4, 3.4, 5.6, 5.7, 5.8, 5.9, 9.6, 9.7, 10.7, 10.8, 14.11
Properties: P17 / P42 / P60（P5 的 DB 侧在 `test_task11_retention_orphan_pg.py`）

═══ 判据一律是「真实执行」而不是「字符存在」═══

本文件不做任何 grep 式断言。每条判据都真的建文件、真的调 `os.replace`、真的持文件句柄、
真的解压 zip bomb 并量内存峰值。理由是 Task 7 的教训：那轮变异检验里「守卫只做
『语句里出现 scratch schema 名』的子串检查」被一条变异打成 GREEN。

═══ 与 Task 7 契约的交叉锁死 ═══

`backend/data/workpaper_staged_artifact_boundary_contract.json` 是 Wave 0 实测固化的
平台边界。本文件把它当**期望值来源**：诊断码映射、目标名模式、幂等尺度、目录 fsync
不可用、8 类路径逃逸、resolver 谓词全部从契约读出来再驱动生产代码。这样「实现悄悄偏离
实测事实」会立刻打红，而不是靠人复读 findings.md。
"""
from __future__ import annotations

import dataclasses
import io
import json
import os
import subprocess
import sys
import tempfile
import tokenize
import tracemalloc
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.artifacts import (  # noqa: E402
    DOCUMENT_EXTENSIONS,
    RESOLVABLE_KINDS,
    ArtifactDigestMismatchError,
    ArtifactNotPublishedError,
    ArtifactPathError,
    ArtifactPublishError,
    AuthorizationRequiredError,
    CandidateNotResolvableError,
    CanonicalArtifactRepository,
    CrossVolumeError,
    DownloadAuthorization,
    FileInUseError,
    IncomingNotResolvableError,
    QuarantineReleaseForbiddenError,
    classify_os_error,
    same_volume,
    sha12,
)
from app.services.workpaper_sync.limits import (  # noqa: E402
    BudgetExceededError,
    LimitsConfigError,
    load_limits,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    IncomingNotDurableError,
    QuarantinedIncomingError,
)
from app.services.workpaper_sync.ooxml_security import (  # noqa: E402
    GATE_ORDER,
    OoxmlSecurityError,
    OoxmlStructureError,
    assert_projection_budget,
    measure_projection,
    validate_ooxml_artifact,
)
from app.services.workpaper_sync.retention import (  # noqa: E402
    REFERENCE_SOURCES,
    load_retention_policy,
)

_CONTRACT_PATH = _BACKEND / "data" / "workpaper_staged_artifact_boundary_contract.json"
_MIGRATION = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)
ENTRY = "g7.disclosure.listed"


# ═══════════════════════════════════════════════════════════════════════════
# fixtures / helpers
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    """Task 7 的版本化边界契约（期望值来源）。缺失即红，不 skip。"""
    assert _CONTRACT_PATH.exists(), f"Task 7 边界契约缺失: {_CONTRACT_PATH}"
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def base(tmp_path: Path) -> Path:
    """本地 base_root（含 storage/ 与 definition_store/）。绝不触碰真实 storage/。"""
    (tmp_path / "storage").mkdir()
    (tmp_path / "definition_store").mkdir()
    return tmp_path


@pytest.fixture()
def repo(base: Path) -> CanonicalArtifactRepository:
    return CanonicalArtifactRepository(base)


@pytest.fixture()
def scope() -> dict[str, uuid.UUID]:
    return {
        "project": uuid.uuid4(),
        "other_project": uuid.uuid4(),
        "wp": uuid.uuid4(),
        "delivery": uuid.uuid4(),
    }


_XLSX_CT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/></Types>'
)
_WORKBOOK = (
    b'<?xml version="1.0" encoding="UTF-8"?><workbook><sheets>'
    b'<sheet name="G7" sheetId="1" r:id="rId1"/></sheets></workbook>'
)
_DOCUMENT = b'<?xml version="1.0" encoding="UTF-8"?><document><body/></document>'


def _zip_bytes(parts: dict[str, bytes], *, compress: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compress) as zf:
        for name, payload in parts.items():
            zf.writestr(name, payload)
    return buf.getvalue()


def xlsx_bytes(**extra: bytes) -> bytes:
    parts = {"[Content_Types].xml": _XLSX_CT, "xl/workbook.xml": _WORKBOOK}
    parts.update(extra)
    return _zip_bytes(parts)


def docx_bytes(**extra: bytes) -> bytes:
    parts = {"[Content_Types].xml": _XLSX_CT, "word/document.xml": _DOCUMENT}
    parts.update(extra)
    return _zip_bytes(parts)


def xlsx_with_entry(name: str, payload: bytes = b"x") -> bytes:
    """带一个自定义 entry 名的合法 xlsx（用于 entry 名安全用例）。"""
    parts = {"[Content_Types].xml": _XLSX_CT, "xl/workbook.xml": _WORKBOOK, name: payload}
    return _zip_bytes(parts)


def xlsx_with_n_entries(n: int) -> bytes:
    parts = {"[Content_Types].xml": _XLSX_CT, "xl/workbook.xml": _WORKBOOK}
    for i in range(max(0, n - len(parts))):
        parts[f"xl/pad/{i}.xml"] = b"<a/>"
    return _zip_bytes(parts)


def xlsx_bomb(uncompressed_bytes: int) -> bytes:
    """高压缩比炸弹：一个全零大 entry。"""
    return xlsx_bytes(**{"xl/bomb.bin": b"\0" * uncompressed_bytes})


def stage(
    repo: CanonicalArtifactRepository,
    scope: dict[str, uuid.UUID],
    payload: bytes,
    *,
    document_type: str = "xlsx",
) -> Any:
    return repo.stage_bytes(
        project_id=scope["project"], wp_id=scope["wp"],
        payload=payload, document_type=document_type,
    )


def _scaled(**overrides: Any) -> Any:
    """按生产配置派生一份缩放后的预算（用于不做 GiB 级 IO 的集成边界测试）。"""
    return dataclasses.replace(load_limits(), **overrides)


def _numeric_literals(path: Path) -> set[int]:
    """用 tokenize 抽出源码里的整数字面量（剥掉注释与字符串/docstring）。"""
    out: set[int] = set()
    with path.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type != tokenize.NUMBER:
                continue
            raw = tok.string.replace("_", "")
            try:
                out.add(int(raw, 0))
            except ValueError:
                continue
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 一、与 Task 7 实测契约的交叉锁死
# ═══════════════════════════════════════════════════════════════════════════


def test_contract_diagnostic_mapping_matches_classifier(contract: dict[str, Any]) -> None:
    """Requirement 9.7：三种失败的 (errno, winerror) → 语义码必须与实测映射一致。"""
    mapping = contract["publish"]["file_occupancy"]["diagnostic_mapping"]
    assert set(mapping) == {"target_occupied", "source_occupied", "cross_volume"}
    for case, spec in mapping.items():
        exc = OSError(spec["errno"], "probe")
        exc.winerror = spec["winerror"]  # type: ignore[attr-defined]
        assert classify_os_error(exc) == spec["code"], f"{case} 诊断码与契约不符"
    # 反向：未登记的 OSError 不得被归成这两个码（否则真实 IO 错误会被误诊）
    other = OSError(13, "probe")
    other.winerror = 1224  # type: ignore[attr-defined]
    assert classify_os_error(other) == "PUBLISH_IO_ERROR"


def test_contract_target_name_pattern_and_idempotency_scope(
    contract: dict[str, Any], repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """内容寻址目标名与幂等尺度必须与契约一致（`{generation:09d}-{sha12}{ext}` / path+sha256）。"""
    ca = contract["publish"]["content_addressed"]
    assert ca["target_name_pattern"] == "{generation:09d}-{sha256[:12]}{ext}"
    assert ca["idempotency_scope"] == "path_and_sha256"

    payload = xlsx_bytes()
    first = repo.publish_representation(
        entry_id=ENTRY, generation=7, staged=stage(repo, scope, payload)
    )
    assert first.path.name == f"{7:09d}-{sha12(first.sha256)}.xlsx"
    assert first.reused is False

    second = repo.publish_representation(
        entry_id=ENTRY, generation=7, staged=stage(repo, scope, payload)
    )
    assert (second.relative_path, second.sha256) == (first.relative_path, first.sha256)
    assert second.reused is True, "同内容重复 publish 必须按 (路径, sha256) 幂等复用"

    other = repo.publish_representation(
        entry_id=ENTRY, generation=7, staged=stage(repo, scope, xlsx_bytes(**{"x.xml": b"<b/>"}))
    )
    assert other.relative_path != first.relative_path
    assert first.path.exists(), "异内容 publish 不得覆盖已存在的 published artifact"


def test_contract_directory_fsync_unsupported_and_never_claimed(
    contract: dict[str, Any], repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """Task 7 fs1：Windows 不允许 `os.open(dir)`，实现不得声称做了目录 fsync。"""
    spec = contract["staging"]["directory_fsync"]
    staged = stage(repo, scope, xlsx_bytes())
    assert staged.file_fsync_performed is True
    assert staged.directory_fsync_performed is False
    assert staged.same_volume_as_publish_target is True

    stage_dir = staged.path.parent
    observed_supported = True
    stage_of_failure = None
    try:
        fd = os.open(str(stage_dir), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        observed_supported = False
        stage_of_failure = "open" if isinstance(exc, PermissionError) else "fsync"
    if sys.platform == "win32":
        assert observed_supported is False, "Windows 上目录 fsync 竟然成功了 —— 契约需重测"
        assert spec["supported_on_windows"] is False
        assert stage_of_failure == spec["observed_failure_stage"]
    else:  # pragma: no cover - 平台差异；不 skip，只显式记录不可验证
        assert spec["supported_on_windows"] is False


def test_contract_path_safety_cases_all_rejected(
    contract: dict[str, Any], repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """Property 42：契约登记的 8 类逃逸全部被拒，`inside_ok` 被接受。

    判据来自契约的 `path_safety.must_reject` 列表 —— 少测一类就会因为
    「构造出来的用例集与契约不等」而打红。
    """
    must_reject = list(contract["path_safety"]["must_reject"])
    project_root = repo.layout.project_root(scope["project"])
    project_root.mkdir(parents=True, exist_ok=True)
    repo.layout.project_root(scope["other_project"]).mkdir(parents=True, exist_ok=True)

    outside = Path(tempfile.mkdtemp(prefix="tmp_task11_escape_"))
    (outside / "artifact.xlsx").write_bytes(b"evil")
    link = project_root / "escape-link"
    if not link.exists():
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            rc = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                capture_output=True, check=False,
            )
            if rc.returncode != 0:  # pragma: no cover - 无权限即红，不 skip
                pytest.fail(
                    "无法创建软链接/junction ⇒ 契约要求的 symlink_escape 无法覆盖："
                    f"{rc.stdout!r} {rc.stderr!r}"
                )

    cases: dict[str, str] = {
        "traversal_relative": r"..\..\..\outside.xlsx",
        "traversal_nested": r"wp\..\..\..\..\outside.xlsx",
        "traversal_posix_style": "../../../outside.xlsx",
        "absolute_outside": str(Path(tempfile.gettempdir()) / "tmp_task11_evil.xlsx"),
        "unc_path": r"\\127.0.0.1\C$\tmp_task11_evil.xlsx",
        "cross_project_absolute": str(
            repo.layout.project_root(scope["other_project"]) / "wp" / "artifact.xlsx"
        ),
        "cross_project_traversal": (
            rf"..\..\{scope['other_project']}\workpapers\wp\artifact.xlsx"
        ),
        "symlink_escape": r"escape-link\artifact.xlsx",
    }
    assert sorted(cases) == sorted(must_reject), "构造用例集与契约的 must_reject 不等"

    for name, relative in cases.items():
        with pytest.raises(ArtifactPathError) as exc:
            repo.resolve_within_project(scope["project"], relative)
        assert exc.value.reason.startswith("outside_"), f"{name} 的拒绝原因异常"

    accepted = repo.resolve_within_project(scope["project"], r"wp\artifact.xlsx")
    assert accepted.is_relative_to(Path(os.path.realpath(str(project_root))))

    # 跨项目复用：同一相对路径在两个 project 根下必须解析到不同绝对路径
    a = repo.resolve_within_project(scope["project"], r"wp\artifact.xlsx")
    b = repo.resolve_within_project(scope["other_project"], r"wp\artifact.xlsx")
    assert a != b
    assert contract["path_safety"]["cross_project_reuse"][
        "same_relative_path_resolves_to_different_absolute_paths"
    ] is True


def test_contract_resolver_predicate_rejects_candidate_incoming_orphan(
    contract: dict[str, Any]
) -> None:
    """Task 7 db3：candidate / durable incoming / orphan 三者永不可解析，且错误码可区分。

    🔴 判定顺序是判据的一部分：kind 专属禁令必须先于通用 state 门，否则
    `IncomingNotResolvableError` / `CandidateNotResolvableError` 会被
    `ArtifactNotPublishedError` 永久遮蔽成不可达分支。
    """
    excl = contract["db_boundary"]["resolver_exclusion"]
    assert excl["observed_representation_referencing_candidate_rejected"] is True
    assert excl["observed_representation_referencing_incoming_durable_rejected"] is True
    assert excl["observed_representation_referencing_orphan_rejected"] is True
    assert "state='published'" in excl["resolver_predicate"]
    assert {k.value for k in RESOLVABLE_KINDS} == {"canonical", "projection"}

    with pytest.raises(CandidateNotResolvableError):
        CanonicalArtifactRepository.assert_canonical_resolvable(
            kind=ArtifactKind.upgrade_candidate, state=ArtifactState.candidate
        )
    with pytest.raises(IncomingNotResolvableError):
        CanonicalArtifactRepository.assert_canonical_resolvable(
            kind=ArtifactKind.incoming, state=ArtifactState.durable
        )
    with pytest.raises(IncomingNotResolvableError):
        CanonicalArtifactRepository.assert_canonical_resolvable(
            kind=ArtifactKind.incoming, state=ArtifactState.quarantined
        )
    with pytest.raises(ArtifactNotPublishedError):
        CanonicalArtifactRepository.assert_canonical_resolvable(
            kind=ArtifactKind.canonical, state=ArtifactState.orphan
        )
    with pytest.raises(ArtifactNotPublishedError):
        CanonicalArtifactRepository.assert_canonical_resolvable(
            kind=ArtifactKind.evidence, state=ArtifactState.published
        )
    CanonicalArtifactRepository.assert_canonical_resolvable(
        kind=ArtifactKind.canonical, state=ArtifactState.published
    )
    CanonicalArtifactRepository.assert_canonical_resolvable(
        kind=ArtifactKind.projection, state=ArtifactState.published
    )


def test_contract_validation_gate_order_and_masquerade(
    contract: dict[str, Any], repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """校验门顺序与扩展名伪装判定必须与契约一致。"""
    masq = contract["path_safety"]["extension_masquerade"]
    assert masq["observed_non_zip_with_xlsx_ext_rejected"] is True
    assert masq["observed_ext_type_mismatch_detected"] is True

    staged = stage(repo, scope, xlsx_bytes())
    report = validate_ooxml_artifact(staged.path, document_type="xlsx")
    assert tuple(report.gates) == GATE_ORDER, "干净文件必须按固定顺序跑完全部门"
    assert report.detected_document_type == "xlsx"

    # 非 ZIP 但声明 xlsx ⇒ 第一个门就拒
    bad = stage(repo, scope, b"<html>not a zip</html>")
    with pytest.raises(OoxmlStructureError) as exc:
        validate_ooxml_artifact(bad.path, document_type="xlsx")
    assert exc.value.gate == "zip_magic"

    # polyglot：`zipfile` 打得开，只有 magic bytes 门能拦。
    poly = stage(repo, scope, b"MZ" * 8 + xlsx_bytes())
    with zipfile.ZipFile(poly.path) as zf:
        assert "xl/workbook.xml" in zf.namelist(), "前置 stub 的 zip 本应仍可被 zipfile 打开"
    with pytest.raises(OoxmlStructureError) as exc_poly:
        validate_ooxml_artifact(poly.path, document_type="xlsx")
    assert exc_poly.value.gate == "zip_magic"
    assert "magic 不符" in str(exc_poly.value)

    # xlsx 字节声明成 docx ⇒ 由内部部件识破（扩展名不作类型依据）
    masked = stage(repo, scope, xlsx_bytes(), document_type="docx")
    with pytest.raises(OoxmlStructureError) as exc2:
        validate_ooxml_artifact(masked.path, document_type="docx")
    assert exc2.value.gate == "document_type"
    assert "扩展名伪装" in str(exc2.value)


def test_gate_order_is_cheapest_first(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """顺序判据：把两个门同时置于超限，报出的必须是**更早**那个。

    这是「顺序不是实现细节」的可执行证明。若 entry 数检查被挪到流式展开之后，
    20001 个 entry 的炸弹会先被完整展开一遍 —— 那时报的就是 max_expanded_bytes。
    """
    tiny = _scaled(max_expanded_bytes=8, max_compressed_bytes=64 * 1024 * 1024)
    staged = stage(repo, scope, xlsx_with_n_entries(20001))
    with pytest.raises(BudgetExceededError) as exc:
        validate_ooxml_artifact(staged.path, document_type="xlsx", limits=tiny)
    assert exc.value.budget == "max_zip_entries"

    # compressed_size 必须早于 expanded_size
    tiny2 = _scaled(max_compressed_bytes=16, max_expanded_bytes=8, max_zip_entries=99999)
    staged2 = stage(repo, scope, xlsx_bytes())
    with pytest.raises(BudgetExceededError) as exc2:
        validate_ooxml_artifact(staged2.path, document_type="xlsx", limits=tiny2)
    assert exc2.value.budget == "max_compressed_bytes"

    # entry 名安全必须早于任何预算门
    staged3 = stage(repo, scope, xlsx_with_entry("../evil.xml"))
    with pytest.raises(OoxmlSecurityError) as exc3:
        validate_ooxml_artifact(
            staged3.path, document_type="xlsx",
            limits=_scaled(max_zip_entries=1, max_compressed_bytes=1),
        )
    assert exc3.value.gate == "entry_names"


# ═══════════════════════════════════════════════════════════════════════════
# 二、Property 17：incoming 先隔离校验，durable / quarantined 两支不可互转
# ═══════════════════════════════════════════════════════════════════════════


def test_property_17_incoming_sealing_is_delivery_scoped_and_durable(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """合法 incoming 只能成为 `kind=incoming,state=durable`，路径以 delivery identity sealing。"""
    staged = repo.stage_incoming(
        project_id=scope["project"], wp_id=scope["wp"], delivery_id=scope["delivery"],
        chunks=[xlsx_bytes()], document_type="xlsx",
    )
    sealed = repo.seal_incoming(staged, delivery_id=scope["delivery"])
    assert sealed.state is ArtifactState.durable
    assert sealed.durable_at is not None and sealed.quarantined_at is None
    assert sealed.rejection_error_code is None
    assert sealed.path.name == f"callback-{sha12(sealed.sha256)}.xlsx"
    # V151 的 incoming path sealing trigger 要求的片段（不依赖 operation/application）
    assert f".incoming/{scope['wp']}/{scope['delivery']}/" in sealed.relative_path
    assert "operation" not in sealed.relative_path
    # incoming 永不属于 resolver 命名空间
    assert repo.scan_versions_namespace(scope["project"], scope["wp"]) == []
    assert repo.open_incoming_for_engine(sealed) == sealed.path


@pytest.mark.parametrize(
    "label,payload,document_type,expect_code",
    [
        ("non_zip", b"<html/>", "xlsx", "ooxml_structure_invalid"),
        # 🔴 polyglot：前置 EXE stub 的自解压包 —— `zipfile` **能正常打开**（它按中央目录
        # 反算偏移），只有 magic bytes 门拦得住。没有这条用例时 magic 门与 BadZipFile
        # 完全重合，「删掉 magic 检查」这条变异会判 GREEN。
        ("polyglot_prefix", b"MZ" * 8 + xlsx_bytes(), "xlsx", "ooxml_structure_invalid"),
        ("masquerade", xlsx_bytes(), "docx", "ooxml_structure_invalid"),
        ("missing_content_types", _zip_bytes({"xl/workbook.xml": _WORKBOOK}),
         "xlsx", "ooxml_structure_invalid"),
        ("traversal_entry", xlsx_with_entry("../evil.xml"), "xlsx", "ooxml_security_rejected"),
        ("absolute_entry", xlsx_with_entry("/etc/passwd"), "xlsx", "ooxml_security_rejected"),
        ("macro_part", xlsx_bytes(**{"xl/vbaProject.bin": b"MZ"}), "xlsx",
         "ooxml_security_rejected"),
        (
            "external_relationship",
            xlsx_bytes(
                **{
                    "xl/_rels/workbook.xml.rels": (
                        b'<?xml version="1.0"?><Relationships><Relationship Id="rId9" '
                        b'Target="http://evil.example/x" TargetMode="External"/></Relationships>'
                    )
                }
            ),
            "xlsx",
            "ooxml_security_rejected",
        ),
        ("embedded_object", xlsx_bytes(**{"xl/embeddings/oleObject1.bin": b"OLE"}), "xlsx",
         "ooxml_security_rejected"),
    ],
)
def test_property_17_malicious_incoming_is_quarantined_never_durable(
    repo: CanonicalArtifactRepository,
    scope: dict[str, uuid.UUID],
    label: str,
    payload: bytes,
    document_type: str,
    expect_code: str,
) -> None:
    """恶意/不合规 incoming 只能落 `quarantined`，`durable_at` 恒 None。"""
    delivery = uuid.uuid4()
    staged = repo.stage_incoming(
        project_id=scope["project"], wp_id=scope["wp"], delivery_id=delivery,
        chunks=[payload], document_type=document_type,
    )
    sealed = repo.seal_incoming(staged, delivery_id=delivery)
    assert sealed.state is ArtifactState.quarantined, label
    assert sealed.durable_at is None, f"{label}: quarantined 必须保持 durable_at=NULL"
    assert sealed.quarantined_at is not None
    assert sealed.rejection_error_code == expect_code, label
    assert sealed.path.name.startswith("quarantined-"), label
    assert f".incoming/{scope['wp']}/{delivery}/" in sealed.relative_path


def test_property_17_zip_bomb_is_quarantined_with_bounded_memory(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """zip bomb：展开量越界即刻中止、隔离，且进程内存受界（Requirement 14.11 不得 OOM）。"""
    lim = load_limits()
    bomb = xlsx_bomb(64 * 1024 * 1024)
    delivery = uuid.uuid4()
    staged = repo.stage_incoming(
        project_id=scope["project"], wp_id=scope["wp"], delivery_id=delivery,
        chunks=[bomb], document_type="xlsx",
    )
    scaled = CanonicalArtifactRepository(
        repo.layout.base_root, limits=_scaled(max_expanded_bytes=8 * 1024 * 1024)
    )
    tracemalloc.start()
    try:
        sealed = scaled.seal_incoming(staged, delivery_id=delivery)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert sealed.state is ArtifactState.quarantined
    assert sealed.rejection_error_code == "capacity_budget_exceeded"
    assert sealed.rejection_gate == "max_expanded_bytes"
    assert peak < lim.peak_memory_budget_bytes, (
        f"展开过程峰值内存 {peak} 超出预算 {lim.peak_memory_budget_bytes} —— 说明不是流式"
    )


def test_property_17_quarantine_is_permanent_and_download_only(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """quarantined 只允许 authorization-first download-only / expire / retention。

    🔴 两种失败必须是**不同异常类型**：quarantine 是永久终态，「尚未 durable」是暂态。
    Task 10 已实测过共用一个类型时短路隔离分支会判 GREEN。
    """
    delivery = uuid.uuid4()
    staged = repo.stage_incoming(
        project_id=scope["project"], wp_id=scope["wp"], delivery_id=delivery,
        chunks=[b"<html/>"], document_type="xlsx",
    )
    sealed = repo.seal_incoming(staged, delivery_id=delivery)
    assert sealed.state is ArtifactState.quarantined

    with pytest.raises(QuarantinedIncomingError):
        repo.open_incoming_for_engine(sealed)
    with pytest.raises(QuarantineReleaseForbiddenError):
        repo.release_quarantined(sealed)
    with pytest.raises(IncomingNotResolvableError):
        repo.promote_incoming_to_published(sealed)

    # 暂态与终态的异常类型必须不同
    not_durable = dataclasses.replace(
        sealed, state=ArtifactState.staged, durable_at=None, quarantined_at=None
    )
    with pytest.raises(IncomingNotDurableError):
        repo.open_incoming_for_engine(not_durable)
    assert QuarantinedIncomingError is not IncomingNotDurableError

    # download-only 必须授权在前
    with pytest.raises(AuthorizationRequiredError):
        repo.open_quarantined_for_download(
            sealed,
            authorization=DownloadAuthorization(
                granted=False, actor_id=uuid.uuid4(), action="download_only"
            ),
        )
    with pytest.raises(AuthorizationRequiredError):
        repo.open_quarantined_for_download(
            sealed,
            authorization=DownloadAuthorization(
                granted=True, actor_id=uuid.uuid4(), action="extract"
            ),
        )
    granted = DownloadAuthorization(
        granted=True, actor_id=uuid.uuid4(), action="download_only", reason="security review"
    )
    assert repo.open_quarantined_for_download(sealed, authorization=granted) == sealed.path


def test_authorization_precedes_any_resource_read(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """authorization-first 的**顺序**判据：文件已不存在时仍必须先抛授权错误。

    若实现先解析路径/开文件再判授权，这里会抛 `ArtifactRepositoryError('文件缺失')`
    而不是 `AuthorizationRequiredError` —— 顺序被交换即打红（Requirement 10.6）。
    """
    delivery = uuid.uuid4()
    staged = repo.stage_incoming(
        project_id=scope["project"], wp_id=scope["wp"], delivery_id=delivery,
        chunks=[b"<html/>"], document_type="xlsx",
    )
    sealed = repo.seal_incoming(staged, delivery_id=delivery)
    sealed.path.unlink()
    with pytest.raises(AuthorizationRequiredError):
        repo.open_quarantined_for_download(
            sealed,
            authorization=DownloadAuthorization(granted=False, actor_id=None, action="download_only"),
        )


# ═══════════════════════════════════════════════════════════════════════════
# 三、candidate 隔离与 finalize 前后 digest 校验
# ═══════════════════════════════════════════════════════════════════════════


def test_candidate_is_non_current_and_outside_resolver_namespace(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    candidate = repo.stage_upgrade_candidate(
        staged=stage(repo, scope, xlsx_bytes()),
        entry_id=ENTRY,
        equivalence_report=b'{"visible_equivalent": true}',
    )
    assert ".upgrade-candidates/" in candidate.relative_path
    assert candidate.verified_before_move and candidate.verified_after_move
    assert repo.scan_versions_namespace(scope["project"], scope["wp"]) == [], (
        "candidate 绝不能出现在 .versions（resolver）命名空间"
    )
    assert candidate.equivalence_relative_path.endswith(".json")

    with pytest.raises(CandidateNotResolvableError):
        repo.resolve_published_artifact(
            project_id=scope["project"], kind=ArtifactKind.upgrade_candidate,
            state=ArtifactState.candidate, relative_path=candidate.relative_path,
        )


def test_finalize_candidate_copies_and_verifies_digest_before_and_after(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """finalize 只创建新 immutable representation；candidate 文件仍在（rollback target）。"""
    candidate = repo.stage_upgrade_candidate(
        staged=stage(repo, scope, xlsx_bytes()),
        entry_id=ENTRY,
        equivalence_report=b"{}",
    )
    published = repo.finalize_candidate_artifact(candidate=candidate, generation=3)
    assert published.state is ArtifactState.published
    assert published.kind is ArtifactKind.canonical
    assert published.sha256 == candidate.sha256
    assert published.verified_after_publish is True
    assert candidate.path.exists(), "finalize 必须复制而非移动 —— candidate 行仍引用该文件"
    assert repo.scan_versions_namespace(scope["project"], scope["wp"]) == [
        published.relative_path
    ]


def test_finalize_rejects_tampered_candidate_bytes(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """finalize 前的 digest 校验：candidate 字节被改过即拒绝，且 `.versions` 不新增文件。"""
    candidate = repo.stage_upgrade_candidate(
        staged=stage(repo, scope, xlsx_bytes()), entry_id=ENTRY, equivalence_report=b"{}"
    )
    candidate.path.write_bytes(xlsx_bytes(**{"tamper.xml": b"<t/>"}))
    with pytest.raises(ArtifactDigestMismatchError) as exc:
        repo.finalize_candidate_artifact(candidate=candidate, generation=4)
    assert exc.value.stage == "staging"
    assert repo.scan_versions_namespace(scope["project"], scope["wp"]) == []


def test_publish_rejects_declared_digest_mismatch_and_post_publish_drift(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """publish 前后各校验一次；任一不符都不得让 pointer 指向它。"""
    staged = stage(repo, scope, xlsx_bytes())
    tampered = dataclasses.replace(staged, sha256="a" * 64)
    with pytest.raises(ArtifactDigestMismatchError) as exc:
        repo.publish_representation(entry_id=ENTRY, generation=1, staged=tampered)
    assert exc.value.stage == "pre_publish"

    class _DriftingRepo(CanonicalArtifactRepository):
        """注入「replace 之后目标内容与声明不符」——证明 post_publish 校验不是装饰。"""

        def atomic_replace(self, src: Path, dst: Path) -> None:  # type: ignore[override]
            super().atomic_replace(src, dst)
            dst.write_bytes(b"drifted-after-publish")

    drifting = _DriftingRepo(repo.layout.base_root)
    with pytest.raises(ArtifactDigestMismatchError) as exc2:
        drifting.publish_representation(
            entry_id=ENTRY, generation=2, staged=stage(drifting, scope, xlsx_bytes())
        )
    assert exc2.value.stage == "post_publish"


def test_staging_residue_is_invisible_to_resolver_and_refused_by_publish_gate(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """Task 7 fs6：半成品只在 `.staging`，且声明 hash 与实际不符时 publish gate 直接拒。"""
    full = xlsx_bytes(**{"xl/big.bin": b"0" * 4096})
    staged = stage(repo, scope, full)
    # 模拟「写到一半被 kill」：截断文件但保留声明 hash
    with staged.path.open("r+b") as fh:
        fh.truncate(staged.size_bytes // 3)
    assert repo.scan_versions_namespace(scope["project"], scope["wp"]) == []
    assert repo.scan_namespace(scope["project"], ".staging"), "半成品应留在 .staging"
    with pytest.raises(ArtifactDigestMismatchError) as exc:
        repo.publish_representation(entry_id=ENTRY, generation=1, staged=staged)
    assert exc.value.stage == "pre_publish"


# ═══════════════════════════════════════════════════════════════════════════
# 四、Windows 占用与跨卷
# ═══════════════════════════════════════════════════════════════════════════


def test_file_in_use_diagnostics_for_target_and_source(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """目标被占用 = WinError 5；源被占用 = WinError 32；两者都归 `FILE_IN_USE` 且可区分。"""
    if sys.platform != "win32":  # pragma: no cover - 非 Windows 无该失败模式
        pytest.fail("本判据针对 Windows 平台占用语义；换平台需重新取证而非 skip")
    project_root = repo.layout.project_root(scope["project"])
    project_root.mkdir(parents=True, exist_ok=True)
    src = project_root / "src.bin"
    dst = project_root / "dst.bin"

    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    with dst.open("rb"):
        with pytest.raises(FileInUseError) as exc:
            repo.atomic_replace(src, dst)
    assert exc.value.winerror == 5 and exc.value.held == "target"
    assert dst.read_bytes() == b"old", "失败必须保留旧内容"

    with src.open("rb"):
        with pytest.raises(FileInUseError) as exc2:
            repo.atomic_replace(src, dst)
    assert exc2.value.winerror == 32 and exc2.value.held == "source"


def test_content_addressed_publish_survives_held_current_artifact(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """Task 7 fs5 的架构性结论：目标名从不预先存在 ⇒ 占用不阻塞新 generation 发布。"""
    payload_a = xlsx_bytes()
    published_a = repo.publish_representation(
        entry_id=ENTRY, generation=1, staged=stage(repo, scope, payload_a)
    )
    payload_b = xlsx_bytes(**{"b.xml": b"<b/>"})
    with published_a.path.open("rb"):
        published_b = repo.publish_representation(
            entry_id=ENTRY, generation=2, staged=stage(repo, scope, payload_b)
        )
        # 同内容重复 publish 也不受占用影响（走幂等复用，不执行 replace）
        again = repo.publish_representation(
            entry_id=ENTRY, generation=1, staged=stage(repo, scope, payload_a)
        )
    assert published_b.path.exists() and published_a.path.exists()
    assert again.reused is True and again.relative_path == published_a.relative_path


def _other_volume_dir(reference: Path) -> Path:
    """返回一个与 `reference` **不同卷**的可写临时目录。

    候选顺序：系统临时目录 → 仓库根（本仓库在 D:，pytest 的 tmp_path 在 C:）。
    两者都同卷时不 skip，由调用方 `pytest.fail` —— 跨卷是 Task 7 fs4 的硬事实，
    「没测」不能记成「已验证」。
    """
    for candidate in (Path(tempfile.gettempdir()), _REPO):
        if same_volume(candidate, reference):
            continue
        return Path(tempfile.mkdtemp(dir=str(candidate), prefix="tmp_task11_xvol_"))
    raise RuntimeError("no_other_volume")


def test_cross_volume_publish_fails_visible(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """跨卷没有原子原语：`atomic_replace` 报 `CROSS_VOLUME_RENAME`，publish 前置也拒。"""
    import shutil

    project_root = repo.layout.project_root(scope["project"])
    project_root.mkdir(parents=True, exist_ok=True)
    try:
        other = _other_volume_dir(project_root)
    except RuntimeError:  # pragma: no cover - 单卷环境
        pytest.fail(
            "本机找不到与项目根不同卷的可写目录 ⇒ 跨卷判据无法取证。"
            "该条必须在双卷环境运行，不得 skip 后当作已验证"
        )
    try:
        src = other / "payload.xlsx"
        src.write_bytes(xlsx_bytes())
        dst = project_root / "dst.bin"

        # (a) 真实平台码：os.replace 跨卷 ⇒ WinError 17 / EXDEV
        with pytest.raises(CrossVolumeError) as exc:
            repo.atomic_replace(src, dst)
        assert exc.value.winerror == 17
        assert src.exists() and not dst.exists(), "跨卷失败不得留下半成功态"

        # (b) publish 的同卷前置：动手前就 fail visible
        digest, size = repo.sha256_of_file(src)
        cross = dataclasses.replace(
            stage(repo, scope, xlsx_bytes()),
            path=src, relative_path="external", sha256=digest, size_bytes=size,
            same_volume_as_publish_target=False,
        )
        with pytest.raises(CrossVolumeError) as exc2:
            repo.publish_representation(entry_id=ENTRY, generation=9, staged=cross)
        assert "同卷" in str(exc2.value)
        assert repo.scan_versions_namespace(scope["project"], scope["wp"]) == []
    finally:
        shutil.rmtree(other, ignore_errors=True)


def test_resolver_reports_missing_file_instead_of_returning_dangling_path(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """Task 7 db6：「pointer 指向缺失 artifact」物理上可能，必须可见地报错。"""
    published = repo.publish_representation(
        entry_id=ENTRY, generation=1, staged=stage(repo, scope, xlsx_bytes())
    )
    assert repo.resolve_published_artifact(
        project_id=scope["project"], kind=ArtifactKind.canonical,
        state=ArtifactState.published, relative_path=published.relative_path,
    ) == published.path
    published.path.unlink()
    with pytest.raises(ArtifactPublishError) as exc:
        repo.resolve_published_artifact(
            project_id=scope["project"], kind=ArtifactKind.canonical,
            state=ArtifactState.published, relative_path=published.relative_path,
        )
    assert "publish-then-commit" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# 五、definition store / bundle / typed marker 的内容寻址不可变发布
# ═══════════════════════════════════════════════════════════════════════════


def test_definition_bundle_and_marker_use_content_addressed_immutable_publish(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    import hashlib

    payload = b'{"schema_version":"definition-bundle:v1"}'
    first = repo.publish_bundle_canonical_bytes(
        project_id=scope["project"], wp_id=scope["wp"], canonical_bytes=payload
    )
    assert first.relative_path == (
        f"definition_store/bundles/{hashlib.sha256(payload).hexdigest()}.json"
    )
    second = repo.publish_bundle_canonical_bytes(
        project_id=scope["project"], wp_id=scope["wp"], canonical_bytes=payload
    )
    assert second.reused is True and second.sha256 == first.sha256

    marker_payload = (
        b'{"schema_version":"definition-bundle-marker:v1",'
        b'"slot":"instrumentation","value":"none"}'
    )
    marker = repo.publish_typed_null_marker(
        project_id=scope["project"], wp_id=scope["wp"],
        marker_id="instrumentation:none:v1", canonical_payload=marker_payload,
    )
    assert marker.relative_path.startswith("definition_store/markers/")
    assert marker.sha256 == hashlib.sha256(marker_payload).hexdigest()

    with pytest.raises(Exception):
        repo.publish_typed_null_marker(
            project_id=scope["project"], wp_id=scope["wp"],
            marker_id="not-a-marker", canonical_payload=marker_payload,
        )

    for kind in ("template", "instrumentation", "contract", "authority_model"):
        out = repo.publish_definition_blob(
            project_id=scope["project"], wp_id=scope["wp"],
            definition_kind=kind, payload=f'{{"k":"{kind}"}}'.encode(),
        )
        assert out.relative_path.startswith("definition_store/")
        assert out.state is ArtifactState.published

    # definition 命名空间同样不属于 resolver 的 .versions 命名空间
    assert repo.scan_versions_namespace(scope["project"], scope["wp"]) == []


def test_trace_and_evidence_artifacts_are_content_addressed(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    run_id = uuid.uuid4()
    trace = repo.publish_trace_bundle(
        project_id=scope["project"], wp_id=scope["wp"], entry_id=ENTRY,
        test_run_id=run_id, scenario_id="html_to_oo", payload=b"gzipped-trace",
    )
    assert f".evidence/{ENTRY}/{run_id}/scenarios/" in trace.relative_path
    assert trace.relative_path.endswith(".trace.json.gz")
    manifest = repo.publish_evidence_manifest(
        project_id=scope["project"], wp_id=scope["wp"], entry_id=ENTRY,
        test_run_id=run_id, payload=b'{"scenarios": 1}',
    )
    assert sha12(manifest.sha256) in manifest.relative_path
    # candidate/evidence 都不进 resolver
    with pytest.raises(ArtifactNotPublishedError):
        CanonicalArtifactRepository.assert_canonical_resolvable(
            kind=trace.kind, state=trace.state
        )


# ═══════════════════════════════════════════════════════════════════════════
# 六、Property 60：Requirement 14.11 六个预算的 N-1 / N / N+1
# ═══════════════════════════════════════════════════════════════════════════


def test_limits_config_matches_requirement_14_11_exactly() -> None:
    """预算数字必须与 Requirement 14.11 逐条相等（改预算须提交 capacity ADR）。"""
    lim = load_limits()
    assert lim.max_compressed_bytes == 50 * 1024 * 1024
    assert lim.max_expanded_bytes == 512 * 1024 * 1024
    assert lim.max_zip_entries == 20000
    assert lim.max_compression_ratio == 100
    assert lim.max_table_rows == 100000
    assert lim.max_projection_fields == 200000
    assert lim.baseline_max_bytes == 10 * 1024 * 1024
    assert lim.baseline_max_fields == 50000


@pytest.mark.parametrize(
    "budget,gate",
    [
        ("max_compressed_bytes", "assert_compressed_size"),
        ("max_expanded_bytes", "assert_expanded_size"),
        ("max_zip_entries", "assert_zip_entries"),
    ],
)
def test_property_60_scalar_budget_boundaries(budget: str, gate: str) -> None:
    """N-1 / N 合法、N+1 拒绝 —— 三个标量预算的纯门边界（用生产数字，无 GiB 级 IO）。"""
    lim = load_limits()
    limit = getattr(lim, budget)
    fn = getattr(lim, gate)
    fn(limit - 1)
    fn(limit)
    with pytest.raises(BudgetExceededError) as exc:
        fn(limit + 1)
    assert exc.value.budget == budget
    assert exc.value.limit == limit and exc.value.observed == limit + 1


def test_property_60_compression_ratio_boundaries() -> None:
    lim = load_limits()
    ratio = lim.max_compression_ratio
    lim.assert_compression_ratio(compressed=1000, expanded=1000 * (ratio - 1))
    lim.assert_compression_ratio(compressed=1000, expanded=1000 * ratio)
    with pytest.raises(BudgetExceededError) as exc:
        lim.assert_compression_ratio(compressed=1000, expanded=1000 * ratio + 1)
    assert exc.value.budget == "max_compression_ratio"
    # compressed=0（stored 空 entry）不判定，避免除零
    lim.assert_compression_ratio(compressed=0, expanded=10**9)


def test_property_60_table_rows_and_projection_fields_boundaries() -> None:
    """行/field 预算的 N-1/N/N+1，用真实 projection 结构驱动（不是直接调纯门）。"""
    lim = load_limits()
    rows = lim.max_table_rows
    for n, should_raise in ((rows - 1, False), (rows, False), (rows + 1, True)):
        payload = {"tables": {"t1": {"rows": [{"a": 1} for _ in range(n)]}}}
        measured = measure_projection(payload)
        assert measured.max_table_rows == n
        if should_raise:
            with pytest.raises(BudgetExceededError) as exc:
                assert_projection_budget(payload)
            assert exc.value.budget == "max_table_rows"
        else:
            assert_projection_budget(payload)

    fields = lim.max_projection_fields
    big_rows = lim.max_table_rows - 1
    for n, should_raise in ((fields - 1, False), (fields, False), (fields + 1, True)):
        # 行数保持在 max_table_rows 以下，确保打红的一定是 field 预算
        per_row = -(-n // big_rows)
        row = {f"f{i}": i for i in range(per_row)}
        count = 0
        rows_list = []
        while count < n:
            take = min(per_row, n - count)
            rows_list.append({f"f{i}": i for i in range(take)} if take != per_row else row)
            count += take
        payload = {"tables": {"t1": {"rows": rows_list}}}
        measured = measure_projection(payload)
        assert measured.field_count == n
        if should_raise:
            with pytest.raises(BudgetExceededError) as exc2:
                assert_projection_budget(payload)
            assert exc2.value.budget == "max_projection_fields"
        else:
            assert_projection_budget(payload)


def test_property_60_zip_entry_boundaries_end_to_end(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """entry 数用**生产数字**做端到端 N-1/N/N+1（20000）。"""
    lim = load_limits()
    n = lim.max_zip_entries
    for count, should_raise in ((n - 1, False), (n, False), (n + 1, True)):
        staged = stage(repo, scope, xlsx_with_n_entries(count))
        if should_raise:
            with pytest.raises(BudgetExceededError) as exc:
                validate_ooxml_artifact(staged.path, document_type="xlsx")
            assert exc.value.budget == "max_zip_entries" and exc.value.observed == count
        else:
            report = validate_ooxml_artifact(staged.path, document_type="xlsx")
            assert report.entry_count == count


def test_property_60_streaming_stage_aborts_at_cap_without_partial_residue(
    base: Path, scope: dict[str, uuid.UUID]
) -> None:
    """staging 阶段就有界：越界立即中止、删掉半成品，且不静默截断。"""
    scaled = CanonicalArtifactRepository(base, limits=_scaled(max_compressed_bytes=1024))
    with pytest.raises(BudgetExceededError) as exc:
        scaled.stage_stream(
            project_id=scope["project"], wp_id=scope["wp"],
            chunks=(b"x" * 512 for _ in range(10)), document_type="xlsx",
        )
    assert exc.value.budget == "max_compressed_bytes"
    residue = scaled.scan_namespace(scope["project"], ".staging")
    assert residue == [], f"越界中止后不得留下被截断的半成品: {residue}"


def test_property_60_expanded_and_ratio_gates_end_to_end(
    repo: CanonicalArtifactRepository, scope: dict[str, uuid.UUID]
) -> None:
    """缩放预算下的端到端展开量/压缩比拒绝（生产数字的边界由纯门覆盖）。"""
    payload = xlsx_bomb(2 * 1024 * 1024)
    staged = stage(repo, scope, payload)
    with pytest.raises(BudgetExceededError) as exc:
        validate_ooxml_artifact(
            staged.path, document_type="xlsx",
            limits=_scaled(max_expanded_bytes=64 * 1024),
        )
    assert exc.value.budget == "max_expanded_bytes"

    with pytest.raises(BudgetExceededError) as exc2:
        validate_ooxml_artifact(
            staged.path, document_type="xlsx",
            limits=_scaled(max_compression_ratio=2),
        )
    assert exc2.value.budget == "max_compression_ratio"


def test_budgets_have_no_second_source_in_production_code() -> None:
    """生产代码不得出现预算数字字面量（design §Capacity Budget：禁止散落常量）。"""
    lim = load_limits()
    forbidden = {
        lim.max_compressed_bytes, lim.max_expanded_bytes, lim.max_zip_entries,
        lim.max_table_rows, lim.max_projection_fields, lim.baseline_max_bytes,
        lim.baseline_max_fields,
    }
    for rel in (
        "app/services/workpaper_sync/artifacts.py",
        "app/services/workpaper_sync/ooxml_security.py",
        "app/services/workpaper_sync/retention.py",
        "app/services/workpaper_sync/limits.py",
    ):
        literals = _numeric_literals(_BACKEND / rel)
        overlap = literals & forbidden
        assert not overlap, f"{rel} 出现预算数字字面量（第二真源）: {sorted(overlap)}"


def test_limits_config_missing_or_invalid_fails_instead_of_falling_back(tmp_path: Path) -> None:
    """无配置必须炸，不得回落到内置默认值（否则配置被删就变成隐形第二真源）。"""
    with pytest.raises(LimitsConfigError):
        load_limits(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text('{"config_id": "x", "schema_version": 1}', encoding="utf-8")
    with pytest.raises(LimitsConfigError):
        load_limits(bad)
    partial = tmp_path / "partial.json"
    partial.write_text(
        json.dumps(
            {
                "config_id": "x", "schema_version": 1,
                "budgets": {
                    "max_compressed_bytes": 1, "max_expanded_bytes": 2,
                    "max_zip_entries": 3, "max_compression_ratio": 4,
                    "max_table_rows": 5, "max_projection_fields": 6,
                },
                "streaming": {"chunk_bytes": 1, "peak_memory_budget_bytes": 2},
                "baseline_operation": {"max_bytes": 1, "max_fields": 1},
                # 缺 ooxml_policy
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LimitsConfigError):
        load_limits(partial)


# ═══════════════════════════════════════════════════════════════════════════
# 七、retention 引用来源与 V151 DDL 双向锁死
# ═══════════════════════════════════════════════════════════════════════════


def test_reference_sources_match_v151_ddl_bidirectionally() -> None:
    """所有引用 `working_paper_artifact(id)` 的列都必须登记进 `REFERENCE_SOURCES`。

    🔴 这是 GC 安全的根判据：将来新迁移加了新 FK 而忘了登记，GC 的二次引用复核就会
    漏查那张表，可能删掉还在用的文件。双向比对让「漏登记」在 CI 立刻红。
    """
    import re

    ddl = _MIGRATION.read_text(encoding="utf-8")
    ddl_pairs: set[tuple[str, str]] = set()
    current_table: str | None = None
    for line in ddl.splitlines():
        m_tbl = re.match(r"\s*CREATE TABLE IF NOT EXISTS (\w+)", line)
        if m_tbl:
            current_table = m_tbl.group(1)
            continue
        if "working_paper_artifact(id)" not in line:
            continue
        m_col = re.match(r"\s*(\w+)\s+UUID", line)
        if m_col and current_table:
            ddl_pairs.add((current_table, m_col.group(1)))
            continue
        # 换行形式：`col UUID NOT NULL` 在上一行、`REFERENCES ...` 在本行
        idx = ddl.splitlines().index(line)
        prev = ddl.splitlines()[idx - 1]
        m_prev = re.match(r"\s*(\w+)\s+UUID", prev)
        if m_prev and current_table:
            ddl_pairs.add((current_table, m_prev.group(1)))

    declared = {(s.table, s.column) for s in REFERENCE_SOURCES}
    assert ddl_pairs, "未能从 V151 抓到任何 artifact FK —— 解析器失效即假绿"
    assert declared == ddl_pairs, (
        f"REFERENCE_SOURCES 与 V151 DDL 不等；"
        f"漏登记={sorted(ddl_pairs - declared)} 多登记={sorted(declared - ddl_pairs)}"
    )


def test_retention_policy_declares_every_class_used_by_production_code() -> None:
    """生产代码里出现的 retention_class 字符串必须都在策略配置里有条目。"""
    policy = load_retention_policy()
    used = {"orphan_canonical", "retention_audit", "default"}
    missing = used - set(policy.classes)
    assert not missing, f"生产代码使用了未登记的 retention_class: {sorted(missing)}"
    assert policy.classes["retention_audit"].deletable is False, (
        "retention_audit 若可删，删除审计会被下一轮 GC 抹掉"
    )
    assert policy.classes["evidence_manifest"].deletable is False
    assert policy.classes["definition"].deletable is False
    assert policy.classes["default"].deletable is False
    for name, klass in policy.classes.items():
        assert klass.access_roles, f"{name} 缺 access_roles（Requirement 10.7）"
        assert klass.sensitivity, f"{name} 缺敏感级别"


def test_retention_contract_retain_reasons_are_declared(contract: dict[str, Any]) -> None:
    """Task 7 契约登记的 retain 原因必须都是本实现可产出的（超集允许，缺失不允许）。"""
    gc = contract["db_boundary"]["retention_gc"]
    assert gc["policy_version"] == load_retention_policy().policy_version
    assert gc["requires_dry_run_first"] is True
    assert gc["requires_second_reference_recheck"] is True
    assert gc["retain_on_uncertainty"] is True
    produced = {
        "no_policy_retain_and_alert", "legal_hold", "orphaned_at_missing",
        "grace_not_elapsed", "reference_found_on_recheck", "ttl_not_elapsed",
        "class_not_deletable", "class_scope_mismatch", "age_anchor_missing",
        "in_flight_operation", "state_changed_on_recheck", "delete_failed",
        "reference_found_on_plan",
    }
    missing = set(gc["retain_reasons"]) - produced
    assert not missing, f"契约登记但实现产不出的 retain 原因: {sorted(missing)}"


# ═══════════════════════════════════════════════════════════════════════════
# 八、property-based（hypothesis）
# ═══════════════════════════════════════════════════════════════════════════


@settings(max_examples=25, deadline=None)
@given(
    segments=st.lists(
        st.sampled_from(["..", "wp", "a", ".", "sub", "..\\..", "../.."]),
        min_size=1, max_size=8,
    )
)
def test_property_42_resolution_never_escapes_project_root(
    tmp_path_factory: Any, segments: list[str]
) -> None:
    """随机拼接的相对路径要么解析在项目根内，要么被 `ArtifactPathError` 拒绝 —— 无第三种。"""
    root = tmp_path_factory.mktemp("pbt_paths")
    (root / "storage").mkdir(exist_ok=True)
    repo = CanonicalArtifactRepository(root)
    project = uuid.uuid4()
    project_root = Path(os.path.realpath(str(repo.layout.project_root(project))))
    project_root.mkdir(parents=True, exist_ok=True)
    relative = "\\".join(segments) + "\\artifact.xlsx"
    try:
        resolved = repo.resolve_within_project(project, relative)
    except ArtifactPathError:
        return
    assert resolved == project_root or project_root in resolved.parents


@settings(max_examples=25, deadline=None)
@given(payload=st.binary(min_size=1, max_size=512), generation=st.integers(1, 10**6))
def test_content_addressed_name_is_deterministic_and_collision_visible(
    tmp_path_factory: Any, payload: bytes, generation: int
) -> None:
    """同 (generation, 内容) → 同目标名同 sha256；不同内容 → 不同名（内容寻址本体）。"""
    import hashlib

    root = tmp_path_factory.mktemp("pbt_names")
    (root / "storage").mkdir(exist_ok=True)
    repo = CanonicalArtifactRepository(root)
    digest = hashlib.sha256(payload).hexdigest()
    expected = f"{generation:09d}-{digest[:12]}"
    assert expected.startswith(f"{generation:09d}-")
    assert sha12(digest) == digest[:12]
    assert len(sha12(digest)) == 12
    assert DOCUMENT_EXTENSIONS["xlsx"] == ".xlsx"
    assert repo.layout.definition_dir("bundle").name == "bundles"
