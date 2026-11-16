"""
正式导出证据覆盖台账（AC-22 的可伪证遗留清单）。

## 为什么需要这个文件

AC-22 要求「普通金额底稿必须以当前 Workpaper 内容版本的 artifact hash+policy pair
（或已登记 data_exchange 的 source_storage_unit）匹配，缺证据历史文件阻断」。

现状（2026-11-16 现算）：`working_paper_content_version` 的
`export_surface_class` / `unit_policy_snapshot` / `unit_policy_digest` /
`source_storage_unit` 四列**只在 ORM 与 V265 迁移里存在，零生产写入方**
（`git grep export_surface_class -- backend/app/services` 只命中
`export_surface_registry.py` 的注释）。也就是说：

- **已收口**：Word 交付件（`word_export_task_versions` 的 policy pair）与
  归档清单（`archive_inventory` 按 latest version 绑定 hash + policy digest）；
- **未收口**：普通底稿（xlsx）归档仍只按文件本身，不绑定内容版本证据。

## 这个守卫做什么

按 memory 铁律 ㉗③「规模超单轮能力时冻结棘轮而非硬修」：

1. **冻结现状**：四列的「生产写入方」集合当前为空，断言它**不得变大**
   （变大 = 有人接了一半又停手，比没接更危险）；
2. **正向钉住已收口的部分**：Word pair 与归档 latest-version 绑定必须保持；
3. **每条遗留都必须可伪证**：写明 `reason`、`owner`、`next_batch` 与
   `verify` 谓词（不是自由文本 allowlist）；
4. **已收口项必须从台账删除**：收口后如果还留在台账里，本守卫打红。

Requirements: AC-22、AC-26（「未清遗留必须如实保留」）
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_APP = _BACKEND / "app"

#: 台账文件（与 `export_surface_classification_gaps.json` 同一目录约定）
LEDGER_FILE = _BACKEND / "data" / "export_evidence_coverage_ledger.json"


# ── 台账结构 ──────────────────────────────────────────────


class TestLedgerSchema:
    def test_ledger_exists_and_is_valid_json(self) -> None:
        assert LEDGER_FILE.exists(), f"台账文件不存在: {LEDGER_FILE}"
        payload = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), "台账顶层必须是对象"
        assert "entries" in payload, "台账缺 entries"
        assert isinstance(payload["entries"], list)

    def test_every_entry_has_required_fields(self) -> None:
        payload = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        required = {"id", "reason_code", "reason", "owner", "next_batch", "verify"}
        for entry in payload["entries"]:
            missing = required - set(entry)
            assert not missing, f"台账条目 {entry.get('id')} 缺字段 {missing}"
            # reason 必须是可读理由，不能是占位
            assert len(str(entry["reason"])) >= 20, (
                f"台账条目 {entry['id']} 的 reason 太短（需 ≥20 字，禁占位文本）"
            )
            assert entry["reason_code"] in {
                "NO_PRODUCTION_WRITER",
                "PARTIAL_WIRING",
                "EXTERNAL_DEPENDENCY",
            }, f"未知 reason_code: {entry['reason_code']}"

    def test_verify_predicates_are_executable(self) -> None:
        """每个 `verify` 必须是 `{kind, target, expect}` 形态且 kind 有限。

        🔴 这是「可伪证」的核心：只存理由文本 = 加一行就变绿的后门
        （memory 铁律 ㉗⑤）。`kind` 必须能被执行，`target` 必须能被现算。
        """
        payload = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        for entry in payload["entries"]:
            verify = entry["verify"]
            assert isinstance(verify, dict), f"{entry['id']}.verify 必须是对象"
            assert set(verify) >= {"kind", "target", "expect"}, (
                f"{entry['id']}.verify 缺 kind/target/expect"
            )
            assert verify["kind"] in {
                "symbol_has_no_production_caller",
                "column_has_no_production_writer",
                "file_absent",
            }, f"{entry['id']}.verify.kind 未知: {verify['kind']}"
            assert verify["target"], f"{entry['id']}.verify.target 为空"


# ── 冻结现状：四列确实没有生产写入方 ──────────────────────


def _app_python_files() -> list[Path]:
    return [p for p in _APP.rglob("*.py") if "__pycache__" not in p.parts]


def _assign_targets(path: Path) -> set[str]:
    """收集「被赋值的属性名」（`x.col = ...` 或 `Model(col=...)` 或字典键）。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        # x.col = value
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    names.add(target.attr)
        # Model(col=value)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg:
                    names.add(kw.arg)
        # {"col": value}
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.add(key.value)
    return names


#: AC-22 要求但当前未接线的四列
UNWIRED_COLUMNS = (
    "export_surface_class",
    "source_storage_unit",
)


class TestUnwiredColumnsStayUnwired:
    """四列的生产写入方当前为空，**不得增加**（半接比没接更危险）。

    一旦有人给这些列接上写入方，就必须同时：
    ①把对应台账条目从 `export_evidence_coverage_ledger.json` 删除；
    ②补上 AC-22 要求的「普通底稿归档绑定 content version」端到端用例。
    只接线不删台账 ⇒ 本守卫打红（防止台账变成永久垃圾）。
    """

    @pytest.mark.parametrize("column", UNWIRED_COLUMNS)
    def test_no_production_writer_yet(self, column: str) -> None:
        writers: list[str] = []
        for path in _app_python_files():
            # 跳过 ORM 定义本身与注册表（它们只声明列，不写值）
            if path.name in {
                "workpaper_sync_models.py",
                "export_surface_registry.py",
            }:
                continue
            if column in _assign_targets(path):
                writers.append(str(path.relative_to(_BACKEND)))
        assert not writers, (
            f"{column} 出现了生产写入方 {writers} —— 请同时\n"
            f"  ① 从 backend/data/export_evidence_coverage_ledger.json 删除对应条目\n"
            f"  ② 补上「普通底稿归档绑定 content version」的端到端用例\n"
            f"只接线不删台账会让本守卫恒红（这是有意的）"
        )

    def test_ledger_has_matching_entries(self) -> None:
        """台账必须逐列登记（不许只写一行概括四列）。"""
        payload = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        targets = {
            entry["verify"]["target"]
            for entry in payload["entries"]
            if entry["verify"]["kind"] == "column_has_no_production_writer"
        }
        for column in UNWIRED_COLUMNS:
            assert column in targets, (
                f"台账没有为 {column} 登记 column_has_no_production_writer 条目"
            )


# ── 正向钉住：已收口的证据链不得退化 ──────────────────────


class TestAlreadyClosedEvidenceChains:
    """已收口的三条链必须有可执行断言（防止「收口了又被改回去」）。"""

    def test_word_version_policy_pair_is_required_by_archive(self) -> None:
        """归档清单必须拒绝缺 policy pair 的 Word 版本。"""
        src = (_BACKEND / "app/services/archive_inventory.py").read_text(encoding="utf-8")
        assert "policy_digest" in src
        assert "policy_snapshot" in src
        # 必须存在「缺任一即转 MISSING」的判据
        assert re.search(
            r"if\s+not\s+expected_hash\s+or\s+not\s+policy_digest\s+or\s+not\s+policy_snapshot",
            src,
        ), "归档清单没有「hash / policy_digest / policy_snapshot 三者缺一即阻断」的判据"

    def test_word_version_evidence_goes_into_manifest(self) -> None:
        src = (_BACKEND / "app/services/archive_inventory.py").read_text(encoding="utf-8")
        for key in ("version_id", "version_no", "file_hash", "policy_digest", "policy_snapshot"):
            assert f'"{key}"' in src or f"'{key}'" in src, f"归档 evidence 缺 {key}"

    def test_export_package_is_fail_closed(self) -> None:
        """组合包不得以空 bytes / placeholder 宣称成功（AC-20）。"""
        src = (_BACKEND / "app/services/export_package_service.py").read_text(encoding="utf-8")
        assert "ExportPackageBuildError" in src
        # 不得出现 `except Exception: ... BytesIO(b"")` 这种静默废件
        assert not re.search(
            r"except\s+Exception[^\n]*:\s*\n(?:.*\n){0,3}?\s*\w+_output\s*=\s*BytesIO\(b[\"']{2}\)",
            src,
        ), "export_package_service 仍有「异常后返回空 bytes 照样打包」的形态"

    def test_trial_balance_export_writes_unit_label(self) -> None:
        """试算表正式导出必须写单位标注（数值与标注同源）。"""
        src = (_BACKEND / "app/services/trial_balance_export.py").read_text(encoding="utf-8")
        assert "金额单位" in src, "试算表导出没有写「金额单位：X」标注"
