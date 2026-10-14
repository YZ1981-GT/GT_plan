"""一次性校验 disclosure-note-doc-upload-and-batch-fill 三件套闭合性。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / ".kiro/specs/disclosure-note-doc-upload-and-batch-fill"
REQ = SPEC / "requirements.md"
DESIGN = SPEC / "design.md"
TASKS = SPEC / "tasks.md"
INDEX = ROOT / ".kiro/specs/INDEX.md"


def read(path: Path) -> str:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    assert "\ufffd" not in text, f"{path}: UTF-8 replacement character"
    assert text.strip(), f"{path}: empty"
    return text


def numbers(pattern: str, text: str) -> list[int]:
    return [int(x) for x in re.findall(pattern, text, flags=re.MULTILINE)]


def referenced_numbers(prefix: str, text: str) -> set[int]:
    out: set[int] = set()
    for start, end in re.findall(rf"{re.escape(prefix)}-(\d+)(?:~(\d+))?", text):
        lo, hi = int(start), int(end or start)
        out.update(range(lo, hi + 1))
    return out


def require(text: str, needles: tuple[str, ...], where: str) -> None:
    missing = [x for x in needles if x not in text]
    assert not missing, f"{where} missing: {missing}"


def main() -> None:
    req, design, tasks, index = map(read, (REQ, DESIGN, TASKS, INDEX))
    assert numbers(r"^### US-(\d+)\b", req) == list(range(1, 12))
    assert numbers(r"^- NFR-(\d+)\b", req) == list(range(1, 10))
    assert numbers(r"^## §(\d+)\b", design) == list(range(1, 13))
    assert numbers(r"^### ADR-DNT-(\d+)[:：]", design) == list(range(1, 7))
    assert numbers(r"^- \[ \]\*? (\d+)\.", tasks) == list(range(1, 57))
    assert numbers(r"^## Phase (\d+)[:：]", tasks) == list(range(0, 10))
    assert set(numbers(r"AC-(\d+)", tasks)) == set(range(1, 12))
    assert referenced_numbers("US", tasks) == set(range(1, 12))
    assert referenced_numbers("NFR", tasks) == set(range(1, 10))
    assert req.count("```") % 2 == design.count("```") % 2 == 0
    assert tasks.count("```") % 2 == 0

    joined = "\n".join((req, design, tasks))
    require(joined, (
        "V187", "R187", "preview_digest", "FOR UPDATE",
        "is_local_override=true", "KnowledgeIndexService.load_documents",
        "PyMuPDF", "note_section_matcher", "note_template_variant_matrix",
        "status=draft", "narrative", "account_explanation",
    ), "spec")
    for stale in (
        "PyPDF2", "逐章节调用 `PUT", "部分失败",
        "关键词匹配（≥50%", "7 Phase / 28", "9 Phase / 56",
    ):
        assert stale not in joined, f"stale design remains: {stale}"

    idx_line = next(line for line in index.splitlines() if "disclosure-note-doc-upload" in line)
    require(idx_line, ("10 Phase / 56", "V187/R187", "禁模糊自动匹配"), "INDEX")
    assert (SPEC / "requirements.md").exists()
    assert (SPEC / "design.md").exists()
    assert (SPEC / "tasks.md").exists()
    print("OK: 11 US, 9 NFR, 12 design sections, 6 ADR, 10 phases, 56 tasks")


if __name__ == "__main__":
    main()
