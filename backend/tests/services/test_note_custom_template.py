"""单测 — NoteCustomTemplateService（Sprint 3 Task 3.2）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.2
Reqs:   R4.3 验收 36（自定义模板存储 + 历史版本）
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.note_custom_template_service import NoteCustomTemplateService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage_root(tmp_path: Path) -> Path:
    """tmp_path 隔离的 ``storage/projects`` 根。"""
    root = tmp_path / "storage" / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def svc(storage_root: Path) -> NoteCustomTemplateService:
    return NoteCustomTemplateService(db=None, storage_root=storage_root)


@pytest.fixture()
def pid():
    return uuid4()


# ---------------------------------------------------------------------------
# 1. 首次保存（v1 写入）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_save_creates_v1_and_main(svc, storage_root, pid):
    user_id = uuid4()
    sections = [
        {"section_number": "五、X1", "section_title": "递延收益", "sort_order": 8990},
    ]
    result = await svc.save_custom_template(pid, sections, user_id)

    assert result["version"] == 1
    assert isinstance(result["updated_at"], str)
    assert len(result["history"]) == 1
    assert result["history"][0]["version"] == 1
    assert result["history"][0]["snapshot_path"] == "v1.json"

    tmpl_dir = storage_root / str(pid) / "templates"
    main = tmpl_dir / "custom_note_template.json"
    v1 = tmpl_dir / "v1.json"
    assert main.exists()
    assert v1.exists()

    main_payload = json.loads(main.read_text(encoding="utf-8"))
    assert main_payload["version"] == 1
    assert main_payload["sections"] == sections
    assert main_payload["updated_by"] == str(user_id)


# ---------------------------------------------------------------------------
# 2. 第二次保存（v2 + history 追加）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_save_appends_history_and_writes_v2(svc, storage_root, pid):
    sections_v1 = [{"section_number": "五、X1", "section_title": "v1", "sort_order": 1}]
    sections_v2 = [{"section_number": "五、X1", "section_title": "v2", "sort_order": 2}]

    await svc.save_custom_template(pid, sections_v1, uuid4())
    result = await svc.save_custom_template(pid, sections_v2, uuid4())

    assert result["version"] == 2
    assert len(result["history"]) == 2
    assert result["history"][0]["version"] == 1
    assert result["history"][1]["version"] == 2

    tmpl_dir = storage_root / str(pid) / "templates"
    assert (tmpl_dir / "v1.json").exists()
    assert (tmpl_dir / "v2.json").exists()

    main_payload = json.loads((tmpl_dir / "custom_note_template.json").read_text(encoding="utf-8"))
    assert main_payload["sections"] == sections_v2

    # v1 快照不可变：内容仍是 v1
    v1_payload = json.loads((tmpl_dir / "v1.json").read_text(encoding="utf-8"))
    assert v1_payload["sections"] == sections_v1


# ---------------------------------------------------------------------------
# 3. 回滚到 v1（产生 v3，不覆盖 v1/v2）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_creates_new_version_and_preserves_history(svc, storage_root, pid):
    sections_v1 = [{"section_number": "五、X1", "section_title": "v1", "sort_order": 1}]
    sections_v2 = [{"section_number": "五、X2", "section_title": "v2", "sort_order": 2}]

    await svc.save_custom_template(pid, sections_v1, uuid4())
    await svc.save_custom_template(pid, sections_v2, uuid4())

    result = await svc.restore_to_version(pid, target_version=1, updated_by=uuid4())
    assert result["version"] == 3

    tmpl_dir = storage_root / str(pid) / "templates"
    # 4 个文件存在：v1/v2/v3 + 主文件
    assert (tmpl_dir / "v1.json").exists()
    assert (tmpl_dir / "v2.json").exists()
    assert (tmpl_dir / "v3.json").exists()

    # v1/v2 不可变（内容未被覆盖）
    v1_payload = json.loads((tmpl_dir / "v1.json").read_text(encoding="utf-8"))
    v2_payload = json.loads((tmpl_dir / "v2.json").read_text(encoding="utf-8"))
    assert v1_payload["sections"] == sections_v1
    assert v2_payload["sections"] == sections_v2

    # 主文件 sections 已回到 v1 内容
    main_payload = json.loads((tmpl_dir / "custom_note_template.json").read_text(encoding="utf-8"))
    assert main_payload["version"] == 3
    assert main_payload["sections"] == sections_v1
    # history 含 3 条
    assert len(main_payload["history"]) == 3


@pytest.mark.asyncio
async def test_restore_nonexistent_version_raises(svc, pid):
    sections = [{"section_number": "五、X1", "section_title": "x"}]
    await svc.save_custom_template(pid, sections, uuid4())
    with pytest.raises(FileNotFoundError):
        await svc.restore_to_version(pid, target_version=99)


# ---------------------------------------------------------------------------
# 4. list_versions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_versions_returns_history(svc, pid):
    sections = [{"section_number": "五、X1", "section_title": "x"}]
    await svc.save_custom_template(pid, sections, uuid4())
    await svc.save_custom_template(pid, sections, uuid4())

    versions = await svc.list_versions(pid)
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2
    assert versions[0]["snapshot_path"] == "v1.json"


@pytest.mark.asyncio
async def test_list_versions_for_missing_project_returns_empty(svc, pid):
    assert await svc.list_versions(pid) == []


# ---------------------------------------------------------------------------
# 5. 缺主文件的 load 返 None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_missing_returns_none(svc, pid):
    assert await svc.load_custom_template(pid) is None


@pytest.mark.asyncio
async def test_load_after_save_returns_payload(svc, pid):
    sections = [{"section_number": "五、X1", "section_title": "x"}]
    await svc.save_custom_template(pid, sections, uuid4())
    payload = await svc.load_custom_template(pid)
    assert payload is not None
    assert payload["version"] == 1
    assert payload["sections"] == sections


# ---------------------------------------------------------------------------
# 6. 路径越界保护
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_uuid_raises(svc):
    with pytest.raises(ValueError):
        await svc.save_custom_template("../../../etc/passwd", [], None)


@pytest.mark.asyncio
async def test_negative_version_in_restore_raises(svc, pid):
    sections = [{"section_number": "五、X1", "section_title": "x"}]
    await svc.save_custom_template(pid, sections, uuid4())
    with pytest.raises(ValueError):
        await svc.restore_to_version(pid, target_version=-1)


@pytest.mark.asyncio
async def test_zero_version_in_restore_raises(svc, pid):
    sections = [{"section_number": "五、X1", "section_title": "x"}]
    await svc.save_custom_template(pid, sections, uuid4())
    with pytest.raises(ValueError):
        await svc.restore_to_version(pid, target_version=0)


# ---------------------------------------------------------------------------
# 7. sections 空数组合法保存
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_sections_save_legal(svc, storage_root, pid):
    result = await svc.save_custom_template(pid, [], uuid4())
    assert result["version"] == 1
    main = storage_root / str(pid) / "templates" / "custom_note_template.json"
    payload = json.loads(main.read_text(encoding="utf-8"))
    assert payload["sections"] == []


@pytest.mark.asyncio
async def test_non_list_sections_raises(svc, pid):
    with pytest.raises(ValueError):
        await svc.save_custom_template(pid, "not a list", uuid4())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await svc.save_custom_template(pid, None, uuid4())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 8. 串行多次写入幂等（版本号严格 +1）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serial_writes_have_strictly_increasing_versions(svc, storage_root, pid):
    """串行连续写入：每次产生 v{N+1}.json，主文件追踪到 history 完整."""
    user_id = uuid4()
    sections = [{"section_number": "五、X1", "section_title": "x"}]
    last_versions: list[int] = []
    for _ in range(5):
        r = await svc.save_custom_template(pid, sections, user_id)
        last_versions.append(r["version"])
    assert last_versions == [1, 2, 3, 4, 5]

    tmpl_dir = storage_root / str(pid) / "templates"
    for i in range(1, 6):
        assert (tmpl_dir / f"v{i}.json").exists(), f"v{i}.json missing"

    versions = await svc.list_versions(pid)
    assert len(versions) == 5


@pytest.mark.asyncio
async def test_save_does_not_overwrite_existing_snapshots(svc, storage_root, pid):
    """同一版本号的快照绝不会被同次 save 重复写覆盖（即便重新跑相同 sections）."""
    sections_v1 = [{"section_number": "五、X1", "section_title": "原始"}]
    sections_v2 = [{"section_number": "五、X1", "section_title": "修改"}]

    await svc.save_custom_template(pid, sections_v1, uuid4())
    v1_path = storage_root / str(pid) / "templates" / "v1.json"
    v1_mtime_before = v1_path.stat().st_mtime_ns
    v1_content_before = v1_path.read_text(encoding="utf-8")

    await svc.save_custom_template(pid, sections_v2, uuid4())

    # v1.json 内容未变（虽然 mtime 是文件系统级）
    assert v1_path.read_text(encoding="utf-8") == v1_content_before
    _ = v1_mtime_before  # mtime 跨平台不可靠，此处仅做内容对比
