"""变异检验 — wp_export 路径解析守卫（wp-export-file-path-resolution）

判据：对每个变异，测试的**失败集合**必须新增条目（RED）。
- RED         → 守卫有效
- GREEN       → 守卫缺陷（该变异逃逸）
- ANCHOR-MISS → 本脚本缺陷（锚点没命中恰好 1 行）

铁律遵循：
- 行级锚点定位（避开 CRLF 与跨行匹配坑），命中数必须恰为 1
- 备份落 `.bak` + `finally` 无条件还原 + md5 核验残留
- baseline 本身可能有红 → 按**失败测试名集合差集**判定，不看退出码
"""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "_wip_mutate_report.txt"

RESOLVER = BACKEND / "app" / "services" / "wp_export" / "wp_file_resolver.py"
DOWNLOAD = BACKEND / "app" / "services" / "wp_download_service.py"
ENGINE = BACKEND / "app" / "services" / "wp_export" / "export_engine.py"

TEST_TARGET = "tests/wp_export/test_wp_file_resolver.py"


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()[:12]


def run_tests() -> tuple[int, int, set[str]]:
    """跑守卫，返回 (passed, failed, 失败测试名集合)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_TARGET, "-q", "--tb=no", "-rf", "-p", "no:randomly"],
        cwd=str(BACKEND),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    fails = set(re.findall(r"FAILED\s+\S+::(?:\w+::)?(\w+)", out))
    m_pass = re.search(r"(\d+) passed", out)
    m_fail = re.search(r"(\d+) failed", out)
    return (
        int(m_pass.group(1)) if m_pass else 0,
        int(m_fail.group(1)) if m_fail else 0,
        fails,
    )


class Mutation:
    """行级锚点变异：把命中行整体替换成 new_line（保持原缩进）。"""

    def __init__(self, mid: str, target: Path, anchor: str, new_line: str, intent: str):
        self.mid = mid
        self.target = target
        self.anchor = anchor          # 行内子串（strip 后比较，必须恰好命中 1 行）
        self.new_line = new_line      # 替换后的行内容（不含缩进，脚本自动补齐）
        self.intent = intent

    def locate(self, lines: list[str]) -> list[int]:
        hits = []
        for i, ln in enumerate(lines):
            if self.anchor in ln and not ln.strip().startswith("#"):
                hits.append(i)
        return hits

    def apply(self) -> tuple[bool, str]:
        src = self.target.read_text(encoding="utf-8")
        lines = src.splitlines(keepends=True)
        hits = self.locate(lines)
        if len(hits) != 1:
            return False, f"ANCHOR-MISS 命中 {len(hits)} 行（要求恰好 1）"
        idx = hits[0]
        original = lines[idx]
        indent = original[: len(original) - len(original.lstrip())]
        newline_char = "\r\n" if original.endswith("\r\n") else "\n"
        lines[idx] = f"{indent}{self.new_line}{newline_char}"
        self.target.write_text("".join(lines), encoding="utf-8")
        return True, f"line {idx + 1}"


MUTATIONS = [
    Mutation(
        "M1", RESOLVER,
        anchor="if _is_blank(file_path):",
        new_line="if False:  # MUTATED: 不再拦空路径",
        intent="共享件不再把空 file_path 判为不可达 → 空串会往下走 Path('') 语义坑",
    ),
    Mutation(
        "M2", RESOLVER,
        anchor="if candidate.is_file():",
        new_line="if candidate.exists():  # MUTATED: is_file → exists",
        intent="把 is_file() 放宽成 exists() → 目录会被当成可用文件返回",
    ),
    Mutation(
        "M3", DOWNLOAD,
        anchor="if res.path is None or not res.path.is_file():",
        new_line="if res.path is None:  # MUTATED: 去掉 is_file 兜底",
        intent="download_pack 去掉 is_file 兜底 → 目录条目会重新进 ZIP",
    ),
    Mutation(
        "M4", DOWNLOAD,
        anchor="_SKIPPED_MANIFEST_NAME,",
        new_line='"_skipped_MUTATED.txt",  # MUTATED: 不走常量',
        intent="跳过清单文件名不再走常量 → 常量与写入点漂移",
    ),
    Mutation(
        "M5", ENGINE,
        anchor="except Exception as e:  # noqa: BLE001",
        new_line="except (TemplateNotFoundError, Exception) as e:  # MUTATED",
        intent="恢复吞一切的 except 元组",
    ),
    Mutation(
        "M6", ENGINE,
        anchor='value=f"导出失败：{reason}',
        new_line='value=f"{reason}",  # MUTATED: 去掉「导出失败」标记',
        intent="回退 workbook 不再自证失败 → 空文件与「本来就空」不可区分",
    ),
    Mutation(
        "M7", ENGINE,
        anchor="return resolve_wp_file(file_path, wp_code=wp_code).path",
        new_line="return Path(file_path) if file_path else None  # MUTATED: 不再委托共享件",
        intent="_resolve_docx_template 不再委托共享件（回到自写路径解析）",
    ),
    Mutation(
        "M8", RESOLVER,
        # 🔴 锚点必须行级唯一：`"file",` 在 resolver 里命中 3 行
        #    （WP_FILE_VERDICTS 声明 / VERDICT_LABELS 键 / __all__），
        #    用声明行做锚点才唯一。
        anchor='WP_FILE_VERDICTS: tuple[WpFileVerdict, ...] = (',
        new_line='WP_FILE_VERDICTS: tuple[WpFileVerdict, ...] = ("ok", "template_fallback", "empty", "missing")  # MUTATED',
        intent="verdict 取值域漂移 → 守卫与实现的单一真源断言必须打红",
    ),
]


def main() -> None:
    buf = io.StringIO()

    def w(s: str = "") -> None:
        buf.write(s + "\n")

    w("=" * 78)
    w("变异检验 — wp_export 路径解析守卫")
    w("=" * 78)

    base_pass, base_fail, base_fails = run_tests()
    w(f"[baseline] passed={base_pass} failed={base_fail} fails={sorted(base_fails)}")
    w()

    red = green = miss = 0

    for mut in MUTATIONS:
        backup = mut.target.with_suffix(mut.target.suffix + f".bak_{mut.mid}")
        before_md5 = md5(mut.target)
        backup.write_bytes(mut.target.read_bytes())
        try:
            ok, note = mut.apply()
            if not ok:
                miss += 1
                w(f"--- {mut.mid} [ANCHOR-MISS] {mut.target.name}")
                w(f"    意图: {mut.intent}")
                w(f"    结果: {note}")
                w()
                continue

            p, f, fails = run_tests()
            new_fails = fails - base_fails
            resolved = base_fails - fails
            if new_fails:
                red += 1
                verdict = "RED"
                detail = f"新增失败 {sorted(new_fails)}（{note}）"
            elif resolved:
                red += 1
                verdict = "RED(转绿信号)"
                detail = f"原有失败转绿 {sorted(resolved)}（{note}）"
            else:
                green += 1
                verdict = "GREEN"
                detail = f"失败集合无变化 passed={p} failed={f}（守卫缺陷）"

            w(f"--- {mut.mid} [{verdict}] {mut.target.name}")
            w(f"    意图: {mut.intent}")
            w(f"    结果: {detail}")
            w()
        finally:
            mut.target.write_bytes(backup.read_bytes())
            after_md5 = md5(mut.target)
            if after_md5 != before_md5:
                w(f"    🔴 {mut.mid} 还原失败! md5 {before_md5} → {after_md5}")
            backup.unlink(missing_ok=True)

    w("=" * 78)
    w(f"汇总: RED={red}/{len(MUTATIONS)}  GREEN={green}  ANCHOR-MISS={miss}")
    if green or miss:
        w("🔴 GREEN=守卫缺陷 / ANCHOR-MISS=本脚本缺陷，两者都要修。")
    else:
        w("✅ 全部变异被守卫捕获。")

    leftovers = sorted(
        p.name for p in (RESOLVER.parent, DOWNLOAD.parent, ENGINE.parent)
        for p in p.glob("*.bak_M*")
    )
    w(f"残留备份文件: {leftovers or '无'}")

    OUT.write_text(buf.getvalue(), encoding="utf-8")
    print(f"written: {OUT}")
    print(f"RED={red}/{len(MUTATIONS)} GREEN={green} MISS={miss}")


if __name__ == "__main__":
    main()
