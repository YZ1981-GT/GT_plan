"""
本 spec 四组迁移的 R 回滚保护（NFR 数据安全 / design §2）。

判据来源：`.kiro/specs/platform-global-display-settings-closure`
requirements NFR「数据安全」：

> R 在项目非默认单位、任一偏好 / 导入 attempt / custom authority 行、
> 不可由旧字段无损表示的 export task、正式 Word policy snapshot/digest
> 或底稿内容版本单位证据存在时必须 `RAISE EXCEPTION` 并整单回滚，
> 不得以 warning 后删列。

本文件只做**静态可伪证判据**（SQL 文本层）：每条 R 必须
①有 `RAISE EXCEPTION`，②每条 `DROP TABLE` / `DROP COLUMN` 之前都已出现保护块，
③保护块检查的对象是本组真实表。真跑 PG 回滚属各迁移自己的 PG 用例（需库）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"

#: R 文件 → 必须被检查的表（保护块里必须出现这些表名）
ROLLBACK_PROTECTION: dict[str, tuple[str, ...]] = {
    "R250__rollback_display_preferences_and_project_amount_unit.sql": (
        "user_display_preferences",
        "projects",
    ),
    "R265__rollback_export_unit_policy_columns.sql": (
        "custom_workbook_unit_authorities",
        "export_tasks",
        "word_export_task_versions",
        "working_paper_content_version",
    ),
    "R273__rollback_ledger_import_attempts.sql": ("ledger_import_attempts",),
    "R275__rollback_custom_template_publication_registry.sql": (
        "custom_template_publications",
        "custom_template_publication_pins",
    ),
}


def _read(name: str) -> str:
    path = _MIGRATIONS / name
    assert path.exists(), f"迁移文件不存在: {name}"
    return path.read_text(encoding="utf-8-sig")


class TestRollbackFilesExistAndPair:
    @pytest.mark.parametrize("rollback", sorted(ROLLBACK_PROTECTION))
    def test_v_pair_exists(self, rollback: str) -> None:
        version = rollback[1:].split("__", 1)[0]
        assert (_MIGRATIONS / f"V{version}__").parent.exists()
        forward = list(_MIGRATIONS.glob(f"V{version}__*.sql"))
        assert forward, f"R{version} 找不到配对的 V{version}"


class TestRollbackRaisesBeforeDrop:
    """判据必须只看**可执行 SQL**，不看注释。

    🔴 M1/M2 首轮存活暴露的正是这一点：`test_has_raise_exception` 原先只做
    `"RAISE EXCEPTION" in text`，而 R275 的文件头注释里引用了 NFR 原文
    （含「必须 `RAISE EXCEPTION`」字样）⇒ 把整个 `DO $$ ... END $$;` 块删掉后
    注释里的字样仍在，判据照样通过。这就是 memory 铁律 ㉖
    「判断代码是否真做了 X 一律用结构化分析，禁文本 `in` 匹配 ——
    注释 / docstring 正反两向都会骗过扫描器」。
    """

    @staticmethod
    def _sql_without_comments(text: str) -> str:
        """剥离 `--` 行注释与 `/* */` 块注释，只留可执行 SQL。"""
        out_lines = []
        in_block = False
        for line in text.split("\n"):
            stripped = line.strip()
            if in_block:
                if "*/" in stripped:
                    in_block = False
                continue
            if stripped.startswith("--"):
                continue
            if "/*" in stripped and "*/" not in stripped:
                in_block = True
                continue
            # 行内 `--` 注释（不在字符串里时先粗剥；SQL 字面量里出现 `--` 极少）
            if "--" in line:
                line = line.split("--", 1)[0]
            out_lines.append(line)
        return "\n".join(out_lines)

    @pytest.mark.parametrize(("rollback", "tables"), sorted(ROLLBACK_PROTECTION.items()))
    def test_has_raise_exception_in_executable_sql(
        self, rollback: str, tables: tuple[str, ...]
    ) -> None:
        sql = self._sql_without_comments(_read(rollback))
        assert "RAISE EXCEPTION" in sql, (
            f"{rollback} 的**可执行 SQL** 里缺少 RAISE EXCEPTION（注释里出现不算）"
        )

    @pytest.mark.parametrize(("rollback", "tables"), sorted(ROLLBACK_PROTECTION.items()))
    def test_protection_mentions_real_tables(self, rollback: str, tables: tuple[str, ...]) -> None:
        sql = self._sql_without_comments(_read(rollback))
        for table in tables:
            assert table in sql, f"{rollback} 的保护块没有检查 {table}"

    @pytest.mark.parametrize(("rollback", "tables"), sorted(ROLLBACK_PROTECTION.items()))
    def test_raise_comes_before_every_drop(self, rollback: str, tables: tuple[str, ...]) -> None:
        """所有 DROP 都必须出现在第一个 `RAISE EXCEPTION` 之后（保护在前）。"""
        sql = self._sql_without_comments(_read(rollback))
        raise_at = sql.find("RAISE EXCEPTION")
        assert raise_at >= 0
        for match in re.finditer(r"\bDROP\s+(TABLE|COLUMN|INDEX)\b", sql, re.IGNORECASE):
            assert match.start() > raise_at, (
                f"{rollback} 的 {match.group(0)} 出现在 RAISE EXCEPTION 之前"
                f"（偏移 {match.start()} < {raise_at}）"
            )

    @pytest.mark.parametrize(("rollback", "tables"), sorted(ROLLBACK_PROTECTION.items()))
    def test_no_warning_swallow(self, rollback: str, tables: tuple[str, ...]) -> None:
        """禁止「warning 后照样删列」的写法。"""
        sql = self._sql_without_comments(_read(rollback)).upper()
        assert "RAISE WARNING" not in sql
        assert "RAISE NOTICE" not in sql

    @pytest.mark.parametrize(("rollback", "tables"), sorted(ROLLBACK_PROTECTION.items()))
    def test_each_protected_table_has_its_own_guard(
        self, rollback: str, tables: tuple[str, ...]
    ) -> None:
        """每张受保护表都必须出现在**某个保护块里**，且该块会 `RAISE EXCEPTION`。

        🔴 M2 首轮存活暴露的判据弱点：原先只断言「表名在文件里出现过」，
        把 pins 的 `IF EXISTS` 改成恒假后表名仍在（只是在别处）⇒ 判据照样通过。

        两种真实写法都要认（穷举变体，memory 铁律 ⑮）：

        1. `IF EXISTS (SELECT 1 FROM <table>)` —— R273/R275 的形态；
        2. `IF to_regclass('public.<table>') IS NOT NULL` +
           `SELECT count(*) INTO ... FROM <table>` —— R250 的形态
           （表可能已被删掉，用 `to_regclass` 判存在更稳）。

        判据 = 「针对该表的保护块里必须出现 `RAISE EXCEPTION`」，
        而不是「文件任意位置有 RAISE EXCEPTION」。
        """
        sql = self._sql_without_comments(_read(rollback))
        for table in tables:
            patterns = [
                # 形态 1：IF EXISTS (SELECT 1 FROM <table>) —— 必须**紧跟** SELECT 1
                # 🔴 M2 二次存活暴露的细节：若允许 `SELECT ... {0,200} FROM <表>`，
                #    把 `IF EXISTS (SELECT 1 FROM pins)` 改成
                #    `IF EXISTS (SELECT 1 FROM publications WHERE false)` 后，
                #    同块里紧随的 `(SELECT count(*) FROM pins)` 仍会命中该正则
                #    ⇒ 变异测不出来。收窄成「SELECT 1 紧接 FROM <表>」。
                r"IF\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+" + re.escape(table) + r"\b",
                # 形态 2：to_regclass('public.<table>')
                r"to_regclass\s*\(\s*'[^']*" + re.escape(table) + r"'",
                # 形态 3：R250 的「列存在性」检查 ——
                #   IF EXISTS (SELECT 1 FROM information_schema.columns
                #              WHERE ... AND table_name = '<表>' AND column_name = '...')
                #   这条也必须算「针对该表的保护块」。
                r"IF\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+information_schema\.columns"
                r"[\s\S]{0,200}?table_name\s*=\s*'"
                + re.escape(table)
                + r"'",
            ]
            found_guard = False
            for pattern in patterns:
                for match in re.finditer(pattern, sql, re.IGNORECASE):
                    # 从保护块起点往后 400 字符内必须出现 RAISE EXCEPTION
                    window = sql[match.start() : match.start() + 400]
                    if "RAISE EXCEPTION" in window:
                        found_guard = True
                        break
                if found_guard:
                    break
            # 形态 2 的 R250 用 `SELECT count(*) INTO ... FROM <表>` 作计数，
            # 但它的**保护条件**是 `to_regclass(...) IS NOT NULL`，已由上面第二条覆盖。
            assert found_guard, (
                f"{rollback} 里没有「针对 {table} 且会 RAISE EXCEPTION」的保护块"
            )


class TestForwardMigrationIsIdempotent:
    """V 侧 DDL 必须幂等（`IF NOT EXISTS` / `IF EXISTS`）。"""

    @pytest.mark.parametrize(
        "forward",
        [
            "V250__display_preferences_and_project_amount_unit.sql",
            "V265__add_export_unit_policy_columns.sql",
            "V273__ledger_import_attempts.sql",
            "V275__custom_template_publication_registry.sql",
        ],
    )
    def test_create_statements_are_idempotent(self, forward: str) -> None:
        text = _read(forward)
        creates = re.findall(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+(?:IF NOT EXISTS\s+)?", text, re.IGNORECASE)
        assert creates, f"{forward} 里找不到 CREATE 语句（夹具失锚）"
        for match in re.finditer(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+(?!IF NOT EXISTS)", text, re.IGNORECASE):
            raise AssertionError(
                f"{forward} 有非幂等的 CREATE（偏移 {match.start()}）：{text[match.start():match.start()+60]!r}"
            )
