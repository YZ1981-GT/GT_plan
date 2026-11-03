# -*- coding: utf-8 -*-
"""GT_plan 本地知识库检索（Claude Code UserPromptSubmit hook）。

用法: stdin 传 JSON {"prompt": "...", ...}，stdout 输出 top-N 相关知识片段。
设计: 纯标准库 BM25；中文 bigram + 英文/数字分词；标题加权；## 分块；mtime 缓存。
约束: 任何异常静默 exit 0 空输出，绝不阻塞提问。
"""
from __future__ import annotations

import json
import math
import pickle
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_FILE = Path(__file__).resolve().parent / ".cache.pkl"

# 外部知识源根目录（office 文档经 kb_convert.py 转 md 后在 knowledge/external/ 下）
EXTERNAL_DIRS = [
    r"C:\Users\baiji\Desktop\文件\税务平台",
]
EXCLUDE_PARTS = {"node_modules", "dist", ".git", ".workbuddy", "build", ".venv"}
EXTERNAL_SUFFIXES = {".md", ".txt"}

MAX_PROMPT_LEN = 2000      # 超长 prompt 截断后再分词
MIN_PROMPT_LEN = 6         # 过短（问候/短指令）跳过检索
TOP_K = 4                  # 返回片段数
SNIPPET_MAX = 400          # 每片段字符上限
TOTAL_MAX = 1600           # 总输出字符上限
TITLE_BOOST = 2.0          # 标题行词频乘子
BM25_K1, BM25_B = 1.5, 0.75

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """英文/数字按词，中文按字符 bigram（顺带保留单字以命中短查询）。"""
    tokens: list[str] = []
    tokens.extend(m.group(0).lower() for m in _WORD_RE.finditer(text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        tokens.extend(run)  # 单字兜底（权重靠 BM25 自然稀释）
    return tokens


def knowledge_files() -> list[Path]:
    files: list[Path] = []
    files.extend((ROOT / "knowledge").rglob("*.md"))
    files.extend((ROOT / ".kiro" / "steering").glob("*.md"))
    files.extend((ROOT / "docs").rglob("*.md"))
    readme = ROOT / "README.md"
    if readme.exists():
        files.append(readme)
    # 外部知识源：仅文本类，排除代码/依赖/压缩包
    for base in EXTERNAL_DIRS:
        base_path = Path(base)
        if not base_path.is_dir():
            continue
        for f in base_path.rglob("*"):
            if f.suffix.lower() not in EXTERNAL_SUFFIXES:
                continue
            if any(part in EXCLUDE_PARTS for part in f.parts):
                continue
            if f.is_file():
                files.append(f)
    return [f for f in files if f.is_file()]


def split_chunks(text: str) -> list[dict]:
    """按 ## 二级标题分块；无标题整文件为一块。返回 [{title, body}]。"""
    lines = text.splitlines()
    chunks: list[dict] = []
    title, buf = "", []
    for line in lines:
        if line.startswith("## "):
            if buf:
                chunks.append({"title": title, "body": "\n".join(buf)})
            title, buf = line[3:].strip(), [line]
        else:
            buf.append(line)
    if buf:
        chunks.append({"title": title, "body": "\n".join(buf)})
    return chunks or [{"title": "", "body": ""}]


def display_path(f: Path) -> str:
    """仓库内文件取相对路径；外部文件取 外部目录名/相对路径。"""
    try:
        return f.relative_to(ROOT).as_posix()
    except ValueError:
        for base in EXTERNAL_DIRS:
            base_path = Path(base)
            try:
                return f"[外部] {base_path.name}/{f.relative_to(base_path).as_posix()}"
            except ValueError:
                continue
        return f.as_posix()


def load_index() -> dict:
    cached: dict = {}
    try:
        if CACHE_FILE.exists():
            cached = pickle.loads(CACHE_FILE.read_bytes())
    except Exception:
        cached = {}
    fresh: dict = {}
    changed = False
    for f in knowledge_files():
        try:
            rel = display_path(f)
            mtime = f.stat().st_mtime
            entry = cached.get(rel)
            if entry and entry["mtime"] == mtime:
                fresh[rel] = entry
                continue
            changed = True
            text = f.read_text(encoding="utf-8", errors="ignore")
            chunks = []
            for c in split_chunks(text):
                toks = tokenize(c["body"])
                head = tokenize(c["title"])
                if toks or head:
                    chunks.append((c["title"], c["body"], toks, head))
            if chunks:
                fresh[rel] = {"mtime": mtime, "chunks": chunks}
        except OSError:
            continue
    if changed or set(cached) != set(fresh):
        try:
            CACHE_FILE.write_bytes(pickle.dumps(fresh))
        except OSError:
            pass
    return fresh


class BM25:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.n = len(docs)
        self.avgdl = sum(d["dl"] for d in docs) / self.n if self.n else 0.0
        self.df: dict[str, int] = {}
        for d in docs:
            for term in set(d["tf"]):
                self.df[term] = self.df.get(term, 0) + 1

    def score(self, query: list[str], i: int) -> float:
        d, s = self.docs[i], 0.0
        for term in query:
            tf = d["tf"].get(term)
            if not tf:
                continue
            df = self.df.get(term, 0)
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * d["dl"] / self.avgdl)
            s += idf * tf * (BM25_K1 + 1) / denom
        return s


def search(query: str) -> list[tuple[float, str, str]]:
    index = load_index()
    docs: list[dict] = []
    for rel, entry in index.items():
        for title, body, toks, head in entry["chunks"]:
            tf: dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            for t in head:  # 标题加权
                tf[t] = tf.get(t, 0) + TITLE_BOOST
            docs.append({"rel": rel, "title": title, "dl": len(toks) + len(head), "tf": tf, "body": body})
    if not docs:
        return []
    bm25 = BM25(docs)
    q = tokenize(query[:MAX_PROMPT_LEN])
    scored = [(bm25.score(q, i), docs[i]) for i in range(len(docs))]
    scored = [(s, d) for s, d in scored if s > 0.0]
    scored.sort(key=lambda x: -x[0])
    results: list[tuple[float, str, str]] = []
    seen: set[str] = set()
    for s, d in scored:
        key = d["rel"]  # 同文件只取最高分块，保证来源多样性
        if key in seen:
            continue
        seen.add(key)
        header = d["title"] or "（文件级）"
        snippet = d["body"].strip().replace("\n\n+", "\n")
        if len(snippet) > SNIPPET_MAX:
            snippet = snippet[:SNIPPET_MAX] + "…"
        results.append((s, f'{d["rel"]}' + (f' § {header}' if d["title"] else ""), snippet))
        if len(results) >= TOP_K:
            break
    return results


def main() -> int:
    try:
        raw = sys.stdin.buffer.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", errors="ignore")  # Windows 管道回退
        data = json.loads(text) if text.strip() else {}
        prompt = str(data.get("prompt") or "")
        if len(prompt.strip()) < MIN_PROMPT_LEN:
            return 0
        results = search(prompt)
        if not results:
            return 0
        out, total = [], 0
        for score, source, snippet in results:
            block = f"[KB] 来源: {source}\n{snippet}"
            if total + len(block) > TOTAL_MAX:
                break
            out.append(block)
            total += len(block)
        if out:
            sys.stdout.buffer.write("\n\n".join(out).encode("utf-8"))
            sys.stdout.buffer.flush()
    except Exception:
        pass  # 静默：知识库故障不阻塞提问
    return 0


if __name__ == "__main__":
    sys.exit(main())
