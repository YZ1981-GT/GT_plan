"""四场景语义真源守卫 —— Wave 4 Task 10
spec: workpaper-import-export-lifecycle-closure（R3.1~R3.4、R3.7、R3.8）

## 核心判据：endpoint ⊆ 真实 `app.routes`

R3.1 要求「复用既有三态端点，不新造第二套」。唯一可靠判据是**运行期路由表**
—— 源码里写个路径字符串谁都能写，但它是否真被注册只有 `app.routes` 知道。

本文件同时钉死 R3.4（场景②③同一 import 通路）与 R3.8（归档态三态语义）。
"""

from __future__ import annotations

import pytest

from app.services.bulk_tab.scenario_registry import (
    SCENARIOS,
    ScenarioSpec,
    all_endpoints,
    get_scenario,
    scenarios_for_ui,
)


@pytest.fixture(scope="module")
def real_paths() -> set[str]:
    from app.main import app

    return {getattr(r, "path", "") for r in app.routes}


# ═══════════════════════════════════════════════════════════════════════════
# 类 A —— 结构自检
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistryShape:
    def test_exactly_four_scenarios(self) -> None:
        assert len(SCENARIOS) == 4, f"四场景应恰为 4 个，实际 {len(SCENARIOS)}"

    def test_keys_are_the_four_expected(self) -> None:
        assert {s.key for s in SCENARIOS} == {
            "blank_template",
            "fill_back",
            "refresh_edit",
            "archive_export",
        }

    def test_keys_unique(self) -> None:
        keys = [s.key for s in SCENARIOS]
        assert len(set(keys)) == len(keys), f"场景键重复: {keys}"

    def test_get_scenario_fails_loud_on_unknown(self) -> None:
        """未知键必须抛 —— 静默返 None 会让 UI 渲染空白入口（假绿形态）。"""
        with pytest.raises(KeyError):
            get_scenario("does_not_exist")

    def test_every_scenario_has_at_least_one_endpoint(self) -> None:
        for s in SCENARIOS:
            assert s.export_endpoint or s.import_endpoint, (
                f"{s.key} 既无导出也无导入端点 ⇒ 是个死入口"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B —— R3.1：端点必须真实存在
# ═══════════════════════════════════════════════════════════════════════════


class TestEndpointsAreReal:
    def test_all_endpoints_registered(self, real_paths: set[str]) -> None:
        """🔴 每个 endpoint 必须在 `app.routes` 里 —— 判据是运行期不是源码。"""
        missing = sorted(all_endpoints() - real_paths)
        assert not missing, (
            f"场景引用了未注册的端点（点了会 404）: {missing}\n"
            f"（bulk 相关真实路径示例: "
            f"{sorted(p for p in real_paths if 'bulk-tab' in p)[:4]}）"
        )

    def test_endpoints_nonempty(self) -> None:
        """扫描面自检 —— 空集会让上一条恒绿。"""
        assert len(all_endpoints()) >= 3, f"端点集异常小: {all_endpoints()}"

    def test_no_per_cycle_endpoint_reused_as_bulk(self, real_paths: set[str]) -> None:
        """四场景走**项目级 bulk** 端点，不得混用 per-cycle 单表端点。

        混用会让"四场景"退化成"逐表点 87 次"，失去批量语义。
        """
        for ep in all_endpoints():
            assert "bulk-tab" in ep, (
                f"{ep} 不是 bulk 端点 —— 四场景应走项目级批量通路"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B —— R3.2 / R3.3：mode 语义
# ═══════════════════════════════════════════════════════════════════════════


class TestModeSemantics:
    def test_blank_template_is_template_mode(self) -> None:
        """R3.2：场景①产物不含项目数据 ⇒ mode 必须是 template。"""
        s = get_scenario("blank_template")
        assert s.mode == "template"
        assert s.export_endpoint is not None
        assert "export-templates" in s.export_endpoint

    def test_refresh_edit_is_data_mode(self) -> None:
        """R3.3：场景③含已取数内容 ⇒ mode 必须是 data。"""
        s = get_scenario("refresh_edit")
        assert s.mode == "data"
        assert s.export_endpoint is not None
        assert "export-data" in s.export_endpoint

    def test_archive_export_is_data_mode(self) -> None:
        s = get_scenario("archive_export")
        assert s.mode == "data"

    def test_template_and_data_modes_both_present(self) -> None:
        """两种 mode 都要有 —— 只有一种说明场景没区分开。"""
        modes = {s.mode for s in SCENARIOS}
        assert modes == {"template", "data"}, f"mode 覆盖不全: {modes}"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B —— R3.4：场景②③同一 import 通路
# ═══════════════════════════════════════════════════════════════════════════


class TestSharedImportPath:
    def test_fill_back_and_refresh_edit_share_import_endpoint(self) -> None:
        """🔴 R3.4：两场景回传必须解析到**同一**端点。

        分成两个端点会让回传逻辑分叉、冲突策略（overwrite/fill-empty/reject）
        与拓扑序无法统一。
        """
        a = get_scenario("fill_back")
        b = get_scenario("refresh_edit")
        assert a.import_endpoint is not None
        assert a.import_endpoint == b.import_endpoint, (
            f"回传端点不一致: fill_back={a.import_endpoint} "
            f"refresh_edit={b.import_endpoint}"
        )

    def test_export_only_scenarios_have_no_import(self) -> None:
        """纯导出场景不得带 import 端点（否则 UI 会渲染出无意义的导入按钮）。"""
        for key in ("blank_template", "archive_export"):
            assert get_scenario(key).import_endpoint is None, (
                f"{key} 是纯导出场景，不应有 import_endpoint"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B —— R3.8：归档态三态
# ═══════════════════════════════════════════════════════════════════════════


class TestArchivedGating:
    def test_export_scenarios_allowed_when_archived(self) -> None:
        """R3.8：归档态**导出仍可用**（调阅归档底稿是正常需求）。"""
        for key in ("blank_template", "archive_export"):
            assert get_scenario(key).archived_allowed is True, (
                f"{key} 在归档态应仍可用"
            )

    def test_import_scenarios_blocked_when_archived(self) -> None:
        """R3.8：归档态**导入必须拒绝**（归档后改数据破坏留痕完整性）。"""
        for key in ("fill_back", "refresh_edit"):
            assert get_scenario(key).archived_allowed is False, (
                f"{key} 含回传，归档态必须拒绝"
            )

    def test_archived_flag_matches_direction(self) -> None:
        """一致性：凡带 import_endpoint 的场景，archived_allowed 必须为 False。"""
        for s in SCENARIOS:
            if s.import_endpoint:
                assert s.archived_allowed is False, (
                    f"{s.key} 可回传却允许归档态操作 ⇒ 与 R3.8 冲突"
                )

    def test_workflow_gate_treats_archived_as_blocked(self) -> None:
        """🔴 声明与实现交叉锁死：`WorkflowGate` 必须真把 archived 判 blocked。

        只在 registry 里声明 `archived_allowed=False` 是**声明侧**；
        真正拦下来的是 `WorkflowGate.classify`。两侧必须一致，
        否则 registry 说"不许"而后端照样写入（additive 注入即死代码的同族）。
        """
        import uuid

        from app.models.workpaper_models import WpFileStatus
        from app.services.bulk_tab.workflow_gate import WorkflowGate

        wp_id = uuid.uuid4()
        got = WorkflowGate().classify(
            [{"wp_id": wp_id, "status": WpFileStatus.archived.value}]
        )
        assert got[wp_id].classification == "blocked", (
            "WorkflowGate 未把 archived 判为 blocked ⇒ 归档态导入拦不住"
        )
        assert got[wp_id].reason == WpFileStatus.archived.value

    def test_workflow_gate_allows_draft(self) -> None:
        """反向自检：正常态必须 writable，否则上一条是恒真的。"""
        import uuid

        from app.models.workpaper_models import WpFileStatus
        from app.services.bulk_tab.workflow_gate import WorkflowGate

        wp_id = uuid.uuid4()
        got = WorkflowGate().classify(
            [{"wp_id": wp_id, "status": WpFileStatus.draft.value}]
        )
        assert got[wp_id].classification == "writable"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B —— R3.7：UI 文案单一真源
# ═══════════════════════════════════════════════════════════════════════════


class TestUiPayload:
    def test_every_scenario_has_both_notes(self) -> None:
        """每个场景都要说明「产物含什么」与「什么时点用」。"""
        for s in SCENARIOS:
            assert s.artifact_note.strip(), f"{s.key} 缺产物说明"
            assert s.timing_note.strip(), f"{s.key} 缺适用时点"

    def test_notes_are_chinese(self) -> None:
        import re

        for s in SCENARIOS:
            for field, val in (
                ("label", s.label),
                ("artifact_note", s.artifact_note),
                ("timing_note", s.timing_note),
            ):
                assert re.search(r"[\u4e00-\u9fff]", val), (
                    f"{s.key}.{field} 非中文: {val!r}（UI 全中文化铁律）"
                )

    def test_notes_are_distinct_across_scenarios(self) -> None:
        """四场景的产物说明必须互不相同 —— 相同等于没区分（R3.7 的实质）。"""
        notes = [s.artifact_note for s in SCENARIOS]
        assert len(set(notes)) == 4, f"产物说明有重复: {notes}"

    def test_ui_payload_shape(self) -> None:
        payload = scenarios_for_ui()
        assert len(payload) == 4
        required = {
            "key", "label", "artifactNote", "timingNote",
            "exportEndpoint", "importEndpoint", "mode",
            "direction", "archivedAllowed",
        }
        for item in payload:
            assert required <= set(item), f"UI 载荷缺字段: {required - set(item)}"

    def test_blank_template_note_says_no_project_data(self) -> None:
        """R3.2 的用户可见面：场景①必须明说"不含项目数据"。"""
        note = get_scenario("blank_template").artifact_note
        assert "不含" in note, f"未说明产物不含项目数据: {note!r}"

    def test_refresh_edit_note_flags_uneditable_columns(self) -> None:
        """R3.3 的用户可见面：场景③必须提示取数列不可直接改。"""
        note = get_scenario("refresh_edit").artifact_note
        assert "不可直接改" in note or "不可直接修改" in note, (
            f"未提示取数列不可改: {note!r}"
        )

    def test_archive_export_note_mentions_integrity(self) -> None:
        """场景④是归档用途，必须提到完整性校验（manifest / sha256）。"""
        note = get_scenario("archive_export").artifact_note
        assert "sha256" in note.lower() or "校验" in note, (
            f"未提及完整性校验: {note!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 反向自检
# ═══════════════════════════════════════════════════════════════════════════


class TestReverseChecks:
    def test_frozen_dataclass_prevents_mutation(self) -> None:
        """真源不可变 —— 防运行时被改出第二份语义。"""
        import dataclasses

        s = SCENARIOS[0]
        assert isinstance(s, ScenarioSpec)
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.label = "篡改"  # type: ignore[misc]

    def test_fake_endpoint_would_be_caught(self, real_paths: set[str]) -> None:
        """证明端点判据不是恒真：一个编造的路径必须不在 `app.routes` 里。"""
        fake = "/api/projects/{project_id}/bulk-tab/does-not-exist"
        assert fake not in real_paths
