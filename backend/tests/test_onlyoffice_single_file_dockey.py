"""单文件共享模型 + doc_key 一致性测试

直接测试 helper 函数 `_resolve_wp_file` 与 room 身份派生（`onlyoffice_room_identity`
+ `workpaper_sync.rooms.derive_doc_key`），验证：
1. 同 wp_code 同 sheet → 相同 doc_key；不同 sheet / 整册视图 → 不同 doc_key
2. 文件首次复制后存在
3. 后续复用（同 wp_code 再次调用返回同一路径，不重复复制）
4. **mtime 变化 → key 不变**
5. 单文件命名：{wp_code}.xlsx 而非 {wp_code}_{sheet_name}.xlsx
6. 不同 wp_code 不同 key
7. 无模板无文件 → FileNotFoundError

Validates: Requirements R4, R5；以及 spec
`workpaper-html-onlyoffice-bidirectional-writeback-closure` 的 AC 2.7 / Property 6。

═══ 第 1 与第 4 条为什么反过来了 ═══

原版 characterize 的是 `_generate_doc_key(file_path, wp_code) = md5(wp_code + mtime_ns)`：
* 所有 sheet 共享一个 key（key 里没有 sheet 成分），靠 mtime 变化迫使 OO 重新下载；
* 于是**任何一次写盘都会轮转 doc_key**，进行中的协同会话被切断；两个用户在不同时刻
  打开同一底稿还会各自进一间房，最后保存的人静默覆盖另一个人的改动。

Task 21 把 doc_key 换成 `(wp_id, entry_id, generation)` 派生，sheet 名与「完整 Excel」
视图算进 entry_id。所以：切换 sheet 仍然换 key（依旧会重新下载），而同一视图反复打开
不再无谓轮转。这两条断言的方向变化**就是**本次修复的可观测形态。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import settings as app_settings
from app.routers.wp_onlyoffice_router import _resolve_wp_file
from app.services.onlyoffice_room_identity import BASELINE_GENERATION, sheet_entry_id
from app.services.workpaper_sync.rooms import derive_doc_key

#: 固定 wp_id：doc_key 现在由 `(wp_id, entry_id, generation)` 派生，wp_code 只是
#: entry_id 的一部分，故测试需要一个稳定的 wp 身份。
_WP_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_WP_ID_OTHER = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _doc_key(wp_code: str, sheet_name: str, *, whole: bool = False, wp_id=_WP_ID) -> str:
    """按生产同一条链路派生 doc_key（`sheet_entry_id` → `derive_doc_key`）。

    刻意复用生产函数而不是在测试里抄一份公式：抄一份就变成「测试验证测试」，
    生产改了派生规则这里也不会红。
    """
    return derive_doc_key(
        wp_id=wp_id,
        entry_id=sheet_entry_id(
            wp_code=wp_code, sheet_name=sheet_name, whole_workbook=whole
        ),
        generation=BASELINE_GENERATION,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """使用 tmp_path 作为 STORAGE_ROOT"""
    monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def project_id():
    """固定的测试项目 ID"""
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def template_file(tmp_path):
    """创建一个模板 xlsx 文件"""
    template = tmp_path / "templates" / "D0.xlsx"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_bytes(b"PK\x03\x04template-xlsx-content-here")
    return template


# ---------------------------------------------------------------------------
# Tests: doc_key 一致性
# ---------------------------------------------------------------------------


class TestDocKeyConsistency:
    """doc_key 一致性：同视图同 key、不同视图不同 key、**与 mtime 无关**

    Validates: Requirements R5；spec AC 2.7 / Property 6
    """

    def test_same_sheet_same_key_but_different_sheet_gets_its_own_key(self, tmp_path):
        """同 wp_code 同 sheet → 同 key；不同 sheet / 整册视图 → 各自一个 key。

        原版断言的是「所有 sheet 共享一个 key」，因为旧公式里没有 sheet 成分，靠 mtime
        变化迫使 OO 重新下载。那个安排有个具体后果：整册视图与单 sheet 视图共享 key 时，
        OO 会把缓存的单 sheet 副本（其余 sheet 已被 openpyxl 隐藏）当成「完整 Excel」
        返回给用户。

        现在 sheet 与整册视图各自成 room 身份，切换视图仍然换 key、仍会重新下载。
        """
        key_a1 = _doc_key("D0", "函证检查表")
        key_a2 = _doc_key("D0", "函证检查表")
        key_b = _doc_key("D0", "替代程序表")
        key_whole = _doc_key("D0", "函证检查表", whole=True)

        assert key_a1 == key_a2, "同一视图反复打开必须得到同一 key（否则协同会话被切断）"
        assert len({key_a1, key_b, key_whole}) == 3, (
            f"不同 sheet / 整册视图必须各自一个 key，实得 {[key_a1, key_b, key_whole]}"
        )
        assert key_a1.startswith("wpsync-")

    def test_mtime_change_does_not_change_the_key(self, tmp_path):
        """**mtime 变化 → doc_key 不变**（Property 6）。

        这是原版 `test_mtime_change_produces_different_key` 的反转。旧行为的真实后果不是
        「不好看」：sheet 可见性改写、callback 落盘、任何一次 `touch` 都会轮转 doc_key，
        OO 于是把它当成另一个文档，进行中的协同会话被切断、已连接用户的编辑落到旧 key
        的房间里再也回不来。

        这里**真的**改一次 mtime 并断言它确实变了 —— 否则「与 mtime 无关」根本没被验证过。
        """
        file_path = tmp_path / "D0.xlsx"
        file_path.write_bytes(b"version 1")
        key_before = _doc_key("D0", "函证检查表")

        stat = file_path.stat()
        new_mtime_ns = stat.st_mtime_ns + 1_000_000_000
        os.utime(file_path, ns=(stat.st_atime_ns, new_mtime_ns))
        assert file_path.stat().st_mtime_ns != stat.st_mtime_ns, (
            "探针没能真的改掉 mtime ⇒ 本条根本没验证任何东西（假绿）"
        )

        assert _doc_key("D0", "函证检查表") == key_before

    def test_different_wp_code_or_wp_id_gives_a_different_key(self, tmp_path):
        """wp_code 或 wp_id 任一不同 ⇒ 不同 doc_key。

        wp_id 也必须参与：同名 wp_code 在两个项目下是两份底稿，共享 doc_key 会让两个
        项目的编辑落进同一个 OO 房间。
        """
        key_a = _doc_key("D0", "函证检查表")
        key_other_code = _doc_key("D1", "函证检查表")
        key_other_wp = _doc_key("D0", "函证检查表", wp_id=_WP_ID_OTHER)
        assert len({key_a, key_other_code, key_other_wp}) == 3

    def test_doc_key_is_deterministic(self, tmp_path):
        """同 wp/entry/generation 多次派生结果稳定（callback 侧要能重算）。"""
        keys = [_doc_key("D2", "存货监盘表") for _ in range(10)]
        assert len(set(keys)) == 1

    def test_generation_rotation_rotates_the_key(self, tmp_path):
        """发布新 generation ⇒ 新 key（AC 2.8 的显式 supersede 语义）。

        这条替代了旧的「写盘就换 key」：轮转的触发点从「文件被动过」变成「平台显式发布
        了新代际」，后者是可控事件，前者不是。
        """
        entry = sheet_entry_id(wp_code="D0", sheet_name="函证检查表", whole_workbook=False)
        g1 = derive_doc_key(wp_id=_WP_ID, entry_id=entry, generation=1)
        g2 = derive_doc_key(wp_id=_WP_ID, entry_id=entry, generation=2)
        assert g1 != g2


# ---------------------------------------------------------------------------
# Tests: 单文件共享模型
# ---------------------------------------------------------------------------


class TestResolveSingleFile:
    """单文件共享模型：按 wp_code 命名，首次复制，后续复用

    Validates: Requirements R4
    """

    def test_file_copied_from_template_on_first_call(self, storage_root, project_id, template_file):
        """文件首次复制后存在

        当项目存储中不存在 {wp_code}.xlsx 但模板文件存在时，
        从模板整本复制一次生成 WP_File。
        """
        result = _resolve_wp_file(project_id, "D0", template_file)

        assert result.exists()
        assert result.read_bytes() == template_file.read_bytes()

    def test_subsequent_call_reuses_file(self, storage_root, project_id, template_file):
        """后续复用：同 wp_code 再次调用返回同一路径，不重复复制

        第二次调用时文件已存在，直接返回既有路径而不再复制。
        """
        result1 = _resolve_wp_file(project_id, "D0", template_file)

        # 修改已有文件内容以验证不被覆盖
        result1.write_bytes(b"modified-by-user-edit")

        result2 = _resolve_wp_file(project_id, "D0", template_file)

        assert result1 == result2
        # 内容仍然是用户修改后的，说明没有重复复制
        assert result2.read_bytes() == b"modified-by-user-edit"

    def test_file_named_wp_code_xlsx(self, storage_root, project_id, template_file):
        """单文件命名：文件名为 {wp_code}.xlsx 而非 {wp_code}_{sheet_name}.xlsx

        验证单文件模型的命名规则（去掉了 per-sheet 后缀）。
        """
        result = _resolve_wp_file(project_id, "D0", template_file)

        assert result.name == "D0.xlsx"
        # 确认不是 per-sheet 命名
        assert "_" not in result.name.replace(".xlsx", "")

    def test_file_named_with_complex_wp_code(self, storage_root, project_id, template_file):
        """复杂 wp_code（含连字符/数字）也正确命名"""
        result = _resolve_wp_file(project_id, "D2-6", template_file)

        assert result.name == "D2-6.xlsx"
        assert result.exists()

    def test_no_template_no_file_raises_file_not_found(self, storage_root, project_id):
        """无模板无文件 → FileNotFoundError

        既不存在已有文件，也没有可复制的模板时抛出异常。
        """
        with pytest.raises(FileNotFoundError, match="OnlyOffice 文件不存在且无模板可复制"):
            _resolve_wp_file(project_id, "NONEXISTENT", None)

    def test_no_template_no_file_with_none_path(self, storage_root, project_id):
        """template_path 为 None 时同样抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            _resolve_wp_file(project_id, "D0", None)

    def test_no_template_nonexistent_path(self, storage_root, project_id, tmp_path):
        """template_path 指向不存在的文件时抛出 FileNotFoundError"""
        fake_template = tmp_path / "nonexistent_template.xlsx"
        assert not fake_template.exists()

        with pytest.raises(FileNotFoundError):
            _resolve_wp_file(project_id, "D0", fake_template)

    def test_existing_file_returns_directly(self, storage_root, project_id):
        """项目存储中已有文件 → 直接返回，不需要模板"""
        # 预先创建文件
        storage_dir = (
            storage_root / "projects" / str(project_id) / "workpapers" / "onlyoffice"
        )
        storage_dir.mkdir(parents=True)
        existing = storage_dir / "D0.xlsx"
        existing.write_bytes(b"pre-existing content")

        # 不提供模板也能成功
        result = _resolve_wp_file(project_id, "D0", None)
        assert result == existing
        assert result.read_bytes() == b"pre-existing content"

    def test_single_file_per_wp_code(self, storage_root, project_id, template_file):
        """每个 wp_code 至多一个 xlsx 文件

        验证项目存储目录下同一 wp_code 只有一个文件。
        """
        _resolve_wp_file(project_id, "D0", template_file)

        storage_dir = (
            storage_root / "projects" / str(project_id) / "workpapers" / "onlyoffice"
        )
        xlsx_files = list(storage_dir.glob("D0*.xlsx"))
        assert len(xlsx_files) == 1
        assert xlsx_files[0].name == "D0.xlsx"
