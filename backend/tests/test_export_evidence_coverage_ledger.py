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


#: 承载 V265 四列的 ORM 类（`class WorkpaperContentVersion(Base)`）
_ORM_MODEL = "WorkpaperContentVersion"


def _callable_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _orm_target_writes(path: Path, columns: set[str]) -> list[str]:
    """只认**真正写 `WorkpaperContentVersion` 列**的形态，不认 dataclass / dict 载体。

    🔴 为什么不能按「属性名出现在赋值里」判（本守卫第一版就是这么写的）：
    consumer 侧把 evidence 装进 dataclass
    （`ContentExportEvidence(export_surface_class=...)`）或 evidence dict
    （`{"source_storage_unit": ...}`）也会命中 —— 那是**读出来往下传**，
    不是写库。第一版的处理是把这两个文件按文件名 skip 掉，那是新的静默
    脱管口（memory 铁律 ㉔③：每条收窄都要配反向断言；文件名 allowlist
    在文件改名 / 搬家后静默失效，且没有任何断言会发现）。

    正解 = 按「写入目标是不是 ORM 类」判，四类形态覆盖全部实际写法：

    ① ``WorkpaperContentVersion(col=...)`` —— ORM 构造；
    ② ``sa.update(WorkpaperContentVersion).values(col=...)`` —— Core update；
    ③ 同文件确实引用该 ORM 类时，``<obj>.col = ...`` 实例属性赋值；
    ④ 裸 SQL ``UPDATE working_paper_content_version`` 且同一语句出现列名。

    ``workpaper_sync_models.py`` 由调用方跳过（那里只有 ``mapped_column``
    声明，列名必然出现且不写值）。
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[str] = []
    # ③ 的判据依赖「本文件确实在跟这个 ORM 类打交道」，否则会把任意对象
    # 的同名属性赋值（例如 dataclass 字段改写）算成写库。
    mentions_model = any(
        (isinstance(node, ast.Name) and node.id == _ORM_MODEL)
        or (isinstance(node, ast.Attribute) and node.attr == _ORM_MODEL)
        for node in ast.walk(tree)
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _callable_name(node.func)
            if name == _ORM_MODEL:  # ①
                for kw in node.keywords:
                    if kw.arg in columns:
                        hits.append(f"{node.lineno}: {_ORM_MODEL}({kw.arg}=...)")
            elif name == "values":  # ②
                chain = ast.unparse(node.func).replace(" ", "")
                if f"update({_ORM_MODEL})" in chain:
                    for kw in node.keywords:
                        if kw.arg in columns:
                            hits.append(f"{node.lineno}: {chain}({kw.arg}=...)")
        if mentions_model and isinstance(node, (ast.Assign, ast.AnnAssign)):  # ③
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in columns:
                    hits.append(f"{node.lineno}: <obj>.{target.attr} = ...")
    for match in re.finditer(  # ④
        r"UPDATE\s+working_paper_content_version\b[^;]*", text, re.S | re.I
    ):
        for column in columns:
            if re.search(rf"\b{column}\b", match.group(0)):
                hits.append(
                    f"raw-sql: UPDATE working_paper_content_version ... {column}"
                )
    return hits


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
            for hit in _orm_target_writes(path, {column}):
                writers.append(f"{path.relative_to(_BACKEND)}:{hit}")
        assert not writers, (
            f"{column} 出现了生产写入方 {writers} —— 请同时\n"
            f"  ① 从 backend/data/export_evidence_coverage_ledger.json 删除对应条目\n"
            f"  ② 补上「普通底稿归档绑定 content version」的端到端用例\n"
            f"只接线不删台账会让本守卫恒红（这是有意的）"
        )

    def test_orm_write_detector_has_bidirectional_mutation_proof(self, tmp_path: Path) -> None:
        """正向/反向双向钉住扫描器本身（memory 铁律 ㉒：只做单向变异会把
        干净域判成缺陷域；本守卫第一版正是「任何同名属性都算写入」，
        靠按文件名 skip 才变绿 —— 那是静默脱管口）。

        反向（必须**不**命中）：consumer 侧 dataclass kwarg、evidence dict 键。
        正向（必须命中）：ORM 构造 / Core update / 实例属性 / 裸 SQL。
        """
        consumer = tmp_path / "consumer_like.py"
        consumer.write_text(
            "from dataclasses import dataclass\n"
            "class Evidence:\n"
            "    export_surface_class: str\n"
            "def build():\n"
            "    ev = Evidence(export_surface_class='formal')\n"
            "    return {'source_storage_unit': None, 'export_surface_class': 'formal'}\n",
            encoding="utf-8",
        )
        assert _orm_target_writes(consumer, {"export_surface_class"}) == []
        assert _orm_target_writes(consumer, {"source_storage_unit"}) == []

        writer = tmp_path / "writer_like.py"
        writer.write_text(
            "import sqlalchemy as sa\n"
            "from app.models.workpaper_sync_models import WorkpaperContentVersion\n"
            "def construct(cv_cls):\n"
            "    return WorkpaperContentVersion(export_surface_class='formal')\n"
            "def core_update(db):\n"
            "    return db.execute(sa.update(WorkpaperContentVersion).values(source_storage_unit='yuan'))\n"
            "def assign(obj):\n"
            "    obj.export_surface_class = 'formal'\n"
            "RAW = 'UPDATE working_paper_content_version SET source_storage_unit = 1'\n",
            encoding="utf-8",
        )
        assert _orm_target_writes(writer, {"export_surface_class"}), "ORM 构造/实例赋值未命中"
        assert _orm_target_writes(writer, {"source_storage_unit"}), "Core update/裸 SQL 未命中"

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
