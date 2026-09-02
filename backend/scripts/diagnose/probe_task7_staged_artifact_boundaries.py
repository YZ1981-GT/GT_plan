"""Task 7 探针：Windows staged artifact publish、DB rollback 与 orphan GC 边界实证

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure Task 7
Requirements 2.4 / 3.4 / 5.9 / 9.6 / 9.7 / 14.6
Property 5（staged artifact 与 DB pointer 不产生悬空可见态）
Property 9（materialize 使用临时校验与原子发布）
Property 42（路径安全）

这是 **Wave 0 探针**，不是实现：Task 9（迁移）与 Task 11（CanonicalArtifactRepository）尚未开工，
本脚本只负责在**本机真实 Windows 文件系统 + 真实 PostgreSQL 16** 上取证 design.md
§Filesystem Layout 与发布协议 所依赖的平台行为，供 Task 9/11/15 直接引用，不建生产 repository、
不加生产迁移、不写任何业务表。

采集内容
--------
FS 阶段（`fs`，无需数据库）
  fs1  流式 staging 写入 + fsync（含 Windows 目录 fsync 能力实测）
  fs2  content-addressed publish 幂等（同内容同目标名、异内容不覆盖）
  fs3  `os.replace` 同卷原子性（share-delete 读者并发观测，统计 partial/missing）
  fs4  `os.replace` 跨卷（期望失败）+ `shutil.move` 跨卷可观测到 partial（证明必须同卷）
  fs5  目标/源文件被**另一进程**占用时 `os.replace` 的真实异常与错误码（两种 share 模式）
  fs6  写 staging 途中 kill 子进程 / staging 完成后 kill，残留能否被误当 published
  fs7  路径安全：目录穿越、项目外绝对路径、UNC、软链接越界、跨项目复用、扩展名伪装（Property 42）
  fs8  校验门注入：zip 结构 / OOXML 结构 / roundtrip 等值 三个注入点失败后 current 不变（Property 9）

DB 阶段（`db`，需真实 PostgreSQL）
  db1  scratch schema 建等价结构（artifact / content_version / representation / entry_state / gc_audit）
  db2  publish 到磁盘后 DB 事务 rollback：pointer/revision/representation 不变，文件仍在（Property 5）
  db3  representation 不得引用 candidate / incoming（trigger 实测拒绝）
  db4  reconciliation 标 orphan（磁盘侧无 DB row、DB 侧无引用两种形态）
  db5  RetentionPolicy/GC：grace 前 retain、grace 后二次确认无引用才删、重现引用则 retain、legal hold 保留
  db6  「pointer 指向缺失 artifact」在物理上可能 ⇒ 必须 publish-then-commit（发布顺序的实证理由）

🔴 硬约束
  - **禁止宣称文件系统与 PostgreSQL 同一事务**：db2 的实证结论恰是「DB rollback 不回滚文件」。
  - **禁止 fail-open**：任何采集异常记 `status="error"` + traceback，并让脚本退出码非 0、
    evidence 的 `probe_status="error"`，守卫据此打红。预期内的 OSError（如跨卷失败）
    记录在 `outcome` 字段里，不算 harness 错误。
  - **判成败查数据不看 exit code**：kill 类用例一律查磁盘实际状态。
  - DB 阶段只在 `tmp_task7_probe_<hex>` scratch schema 内建表并全量 DROP；所有 SQL 进
    `sql_log`，守卫逐条校验 DDL/DML 必须带 scratch schema 名（= 未写业务表的可复算证据）。

用法（仓库根，Windows）
    $env:PYTHONIOENCODING='utf-8'
    python backend/scripts/diagnose/probe_task7_staged_artifact_boundaries.py all
    python backend/scripts/diagnose/probe_task7_staged_artifact_boundaries.py fs
    python backend/scripts/diagnose/probe_task7_staged_artifact_boundaries.py db
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVIDENCE_DIR = (
    REPO_ROOT
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task7-staged-artifact-db-rollback"
)
#: 只读复制源；绝不修改 backend/wp_templates/（运行时权威模板库）。
SEED_XLSX = REPO_ROOT / "backend" / "wp_templates" / "A" / "A31 审计标识一览表.xlsx"

#: 版本化 retention 策略（探针内联的参考实现，Task 11 的 RetentionPolicyService 以此为形状基线）。
RETENTION_POLICY: dict[str, Any] = {
    "policy_version": "workpaper-sync-retention:v1",
    "classes": {
        "canonical_orphan": {"grace_seconds": 86400, "legal_hold": False},
        "upgrade_candidate": {"grace_seconds": 43200, "legal_hold": False},
        "incoming": {"grace_seconds": 604800, "legal_hold": False},
        "legal_hold_canonical": {"grace_seconds": 86400, "legal_hold": True},
    },
}

CHUNK = 64 * 1024


# ---------------------------------------------------------------------------
# 采集骨架：禁止 fail-open
# ---------------------------------------------------------------------------


class ProbeHarnessError(RuntimeError):
    """探针自身（非被测行为）出错。必须记 ERROR 态，不得吞成「不支持/无数据」。"""


class _Recorder:
    def __init__(self) -> None:
        self.cases: dict[str, dict[str, Any]] = {}
        self.errors: list[dict[str, Any]] = []

    def run(self, case_id: str, title: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        try:
            payload = fn()
            record = {
                "case_id": case_id,
                "title": title,
                "status": "ok",
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
        except Exception as exc:  # noqa: BLE001 - 采集异常必须显式记 ERROR 态并向上冒泡到退出码
            record = {
                "case_id": case_id,
                "title": title,
                "status": "error",
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(limit=12),
            }
            self.errors.append({"case_id": case_id, "error_type": type(exc).__name__, "error_message": str(exc)})
        self.cases[case_id] = record
        flag = "OK " if record["status"] == "ok" else "ERR"
        print(f"  [{flag}] {case_id}  {title}")
        if record["status"] == "error":
            print(f"        {record['error_type']}: {record['error_message']}")
        return record


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _oserror_facts(exc: BaseException) -> dict[str, Any]:
    return {
        "exc_type": type(exc).__name__,
        "errno": getattr(exc, "errno", None),
        "winerror": getattr(exc, "winerror", None),
        "strerror": getattr(exc, "strerror", None) or str(exc),
    }


# ---------------------------------------------------------------------------
# staged publish 参考实现（探针内联，供 Task 11 对齐）
# ---------------------------------------------------------------------------


def _stage_stream(src_bytes: bytes, staging_file: Path, chunk: int = CHUNK) -> dict[str, Any]:
    """流式写 staging：分块写 + 每块 flush + 结束 fsync，并同步计算 hash。"""
    staging_file.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    chunks = 0
    with staging_file.open("wb") as fh:
        for offset in range(0, len(src_bytes), chunk):
            block = src_bytes[offset : offset + chunk]
            fh.write(block)
            digest.update(block)
            fh.flush()
            chunks += 1
        fh.flush()
        os.fsync(fh.fileno())
    return {
        "staging_path": str(staging_file),
        "chunks_written": chunks,
        "streaming_sha256": digest.hexdigest(),
        "size_bytes": staging_file.stat().st_size,
    }


def _dir_fsync(directory: Path) -> dict[str, Any]:
    """Windows 上目录 fsync 能力实测（POSIX 惯用手法在 Windows 未必可用）。"""
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError as exc:
        return {"supported": False, "stage": "open", **_oserror_facts(exc)}
    try:
        os.fsync(fd)
        return {"supported": True, "stage": "fsync"}
    except OSError as exc:
        return {"supported": False, "stage": "fsync", **_oserror_facts(exc)}
    finally:
        os.close(fd)


def _content_addressed_name(generation: int, sha256: str, ext: str) -> str:
    """design.md §Filesystem Layout：`000000003-{artifactSha12}.xlsx`。"""
    return f"{generation:09d}-{sha256[:12]}{ext}"


def _publish(staging_file: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(staging_file), str(target))
    return {"target_path": str(target), "target_sha256": _sha256_file(target)}


def _resolver_namespace_scan(versions_root: Path) -> list[str]:
    """resolver 只看 `.versions/**`；`.staging`/`.incoming`/`.upgrade-candidates` 不在其命名空间。"""
    if not versions_root.exists():
        return []
    return sorted(str(p.relative_to(versions_root)).replace("\\", "/") for p in versions_root.rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# share-delete 读者（观测 os.replace 原子性）
# ---------------------------------------------------------------------------


def _read_share_delete(path: Path) -> bytes | None:
    """用 FILE_SHARE_DELETE 打开读取：不阻塞 os.replace，因此能观测替换过程中的中间态。"""
    import pywintypes
    import win32con
    import win32file

    try:
        handle = win32file.CreateFile(
            str(path),
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            0,
            None,
        )
    except pywintypes.error as exc:
        if exc.winerror in (2, 3):  # ERROR_FILE_NOT_FOUND / ERROR_PATH_NOT_FOUND
            return None
        raise
    try:
        parts: list[bytes] = []
        while True:
            _rc, data = win32file.ReadFile(handle, 1 << 16)
            if not data:
                break
            parts.append(data)
        return b"".join(parts)
    finally:
        win32file.CloseHandle(handle)


def _observe_while(target: Path, expect: dict[bytes, str], stop: threading.Event) -> dict[str, int]:
    """并发读目标文件并把每次读到的字节分类成 full_*/partial/missing。"""
    tally = {"missing": 0, "partial": 0, "read_denied": 0}
    for label in expect.values():
        tally[label] = 0
    while not stop.is_set():
        try:
            data = _read_share_delete(target)
        except Exception:  # noqa: BLE001 - 读者侧的瞬时错误单独计数，不吞成 partial
            tally["read_denied"] += 1
            continue
        if data is None:
            tally["missing"] += 1
        elif data in expect:
            tally[expect[data]] += 1
        else:
            tally["partial"] += 1
    return tally


# ---------------------------------------------------------------------------
# 子进程模式（文件占用 / 中断）
# ---------------------------------------------------------------------------


def _child_hold(path: str, mode: str, ready: str, hold_seconds: float) -> int:
    """持有目标文件句柄，供父进程实测 os.replace 在「文件被占用」下的行为。

    `mode` 覆盖 Python 内建 open 与五种 Win32 share 组合：只测一种会得出错误结论
    （实测六种全部让 os.replace 报 WinError 5）。
    """
    import win32con
    import win32file

    share_map = {
        "none": 0,
        "read": win32file.FILE_SHARE_READ,
        "read_write": win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
        "read_delete": win32file.FILE_SHARE_READ | win32file.FILE_SHARE_DELETE,
        "read_write_delete": win32file.FILE_SHARE_READ
        | win32file.FILE_SHARE_WRITE
        | win32file.FILE_SHARE_DELETE,
        "delete_only": win32file.FILE_SHARE_DELETE,
    }
    if mode == "plain":
        handle: Any = open(path, "rb")  # noqa: SIM115 - 必须长期持有
        handle.read(16)
    elif mode in share_map:
        handle = win32file.CreateFile(
            path, win32file.GENERIC_READ, share_map[mode], None, win32con.OPEN_EXISTING, 0, None
        )
        win32file.ReadFile(handle, 16)
    else:  # pragma: no cover - CLI 误用
        raise SystemExit(f"unknown hold mode: {mode}")
    Path(ready).write_text("ready", encoding="utf-8")
    time.sleep(hold_seconds)
    return 0


def _child_slow_write(path: str, total: int, chunk: int, ready: str, ready_after: int, sleep: float) -> int:
    """分块写 staging，每块 flush+fsync；父进程在 ready 后 kill，制造真实半成品。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    index = 0
    with target.open("wb") as fh:
        while written < total:
            block = bytes([index % 251]) * min(chunk, total - written)
            fh.write(block)
            fh.flush()
            os.fsync(fh.fileno())
            written += len(block)
            index += 1
            if index == ready_after:
                Path(ready).write_text("ready", encoding="utf-8")
            time.sleep(sleep)
    Path(ready).write_text("complete", encoding="utf-8")
    time.sleep(300)
    return 0


def _spawn(argv: list[str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), *argv],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _wait_ready(sentinel: Path, expect: str, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sentinel.exists():
            text = sentinel.read_text(encoding="utf-8").strip()
            if text == expect:
                return text
        time.sleep(0.02)
    raise ProbeHarnessError(f"子进程未在 {timeout}s 内到达 sentinel={expect}: {sentinel}")


def _kill_and_reap(proc: subprocess.Popen[bytes]) -> dict[str, Any]:
    proc.kill()
    try:
        _out, err = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:  # pragma: no cover
        raise ProbeHarnessError("kill 后子进程未退出")
    return {
        "child_returncode": proc.returncode,
        "child_stderr_tail": (err or b"").decode("utf-8", "replace")[-400:],
        "verdict_source": "disk_state_not_exit_code",
    }


# ---------------------------------------------------------------------------
# 校验门参考实现（Property 9）
# ---------------------------------------------------------------------------


def _validate_zip_structure(path: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
        if bad is not None:
            return False, f"corrupt_entry:{bad}"
        return True, "ok"
    except zipfile.BadZipFile as exc:
        return False, f"BadZipFile:{exc}"


def _validate_ooxml_parts(path: Path, document_type: str) -> tuple[bool, str]:
    required = {
        "xlsx": ("[Content_Types].xml", "xl/workbook.xml"),
        "docx": ("[Content_Types].xml", "word/document.xml"),
    }[document_type]
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
    missing = [part for part in required if part not in names]
    if missing:
        return False, f"missing_parts:{','.join(missing)}"
    return True, "ok"


def _validate_roundtrip(path: Path, declared_sheet_names: list[str]) -> tuple[bool, str]:
    """反读等值：解析 workbook 的 sheet 名并与声明值比对（不依赖 openpyxl 写入）。"""
    import re

    with zipfile.ZipFile(path) as zf:
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8", "replace")
    found = re.findall(r'<sheet[^>]*\sname="([^"]*)"', workbook_xml)
    if found != declared_sheet_names:
        return False, f"sheet_names_mismatch:{found!r}!={declared_sheet_names!r}"
    return True, "ok"


def _sheet_names(path: Path) -> list[str]:
    import re

    with zipfile.ZipFile(path) as zf:
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8", "replace")
    return re.findall(r'<sheet[^>]*\sname="([^"]*)"', workbook_xml)


# ---------------------------------------------------------------------------
# 路径安全参考实现（Property 42）
# ---------------------------------------------------------------------------


def _resolve_within_root(root: Path, relative: str) -> dict[str, Any]:
    root_resolved = root.resolve(strict=False)
    try:
        candidate = root / relative
        resolved = Path(os.path.realpath(str(candidate)))
    except OSError as exc:
        return {"accepted": False, "reject_reason": "resolve_failed", **_oserror_facts(exc)}
    inside = resolved == root_resolved or root_resolved in resolved.parents
    return {
        "accepted": bool(inside),
        "reject_reason": None if inside else "outside_project_root",
        "root_resolved": str(root_resolved),
        "path_resolved": str(resolved),
    }


def _detect_document_type(path: Path) -> dict[str, Any]:
    head = path.open("rb").read(4)
    if head[:4] != b"PK\x03\x04":
        return {"magic_ok": False, "magic_head_hex": head.hex(), "detected": None}
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
    detected = "xlsx" if "xl/workbook.xml" in names else ("docx" if "word/document.xml" in names else None)
    return {"magic_ok": True, "magic_head_hex": head.hex(), "detected": detected}


# ---------------------------------------------------------------------------
# FS 阶段
# ---------------------------------------------------------------------------


def _fs_phase(work_root: Path, rec: _Recorder) -> dict[str, Any]:
    if not SEED_XLSX.exists():
        raise ProbeHarnessError(f"只读种子模板缺失: {SEED_XLSX}")
    seed_bytes = SEED_XLSX.read_bytes()
    seed_sha = hashlib.sha256(seed_bytes).hexdigest()
    seed_sheets = _sheet_names(SEED_XLSX)

    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    wp_id = uuid.uuid4()
    entry_id = "A31.sheet1"

    def layout(project: uuid.UUID) -> dict[str, Path]:
        base = work_root / "storage" / str(project) / "workpapers"
        return {
            "base": base,
            "staging": base / ".staging",
            "versions": base / ".versions",
            "incoming": base / ".incoming",
            "candidates": base / ".upgrade-candidates",
        }

    la = layout(project_a)
    lb = layout(project_b)
    reps_dir = la["versions"] / str(wp_id) / "representations" / entry_id

    # ---------------- fs1 流式 staging + fsync ----------------
    def fs1() -> dict[str, Any]:
        stage_id = uuid.uuid4()
        staging_dir = la["staging"] / str(wp_id) / str(stage_id)
        staged = _stage_stream(seed_bytes, staging_dir / "artifact.tmp")
        reread = _sha256_file(staging_dir / "artifact.tmp")
        return {
            "same_volume_as_project": Path(staging_dir).drive.upper() == REPO_ROOT.drive.upper(),
            "staging_drive": Path(staging_dir).drive.upper(),
            "seed_sha256": seed_sha,
            "streaming_sha256": staged["streaming_sha256"],
            "reread_sha256": reread,
            "streaming_hash_matches_reread": staged["streaming_sha256"] == reread,
            "streaming_hash_matches_seed": staged["streaming_sha256"] == seed_sha,
            "chunks_written": staged["chunks_written"],
            "size_bytes": staged["size_bytes"],
            "file_fsync_ok": True,
            "directory_fsync": _dir_fsync(staging_dir),
            "staging_dir": str(staging_dir),
        }

    rec.run("fs1", "流式 staging 写入 + fsync（含目录 fsync 能力）", fs1)

    # ---------------- fs2 content-addressed publish 幂等 ----------------
    def fs2() -> dict[str, Any]:
        publishes = []
        for attempt in (1, 2):
            stage_dir = la["staging"] / str(wp_id) / str(uuid.uuid4())
            staged = _stage_stream(seed_bytes, stage_dir / "artifact.tmp")
            name = _content_addressed_name(1, staged["streaming_sha256"], ".xlsx")
            result = _publish(stage_dir / "artifact.tmp", reps_dir / name)
            publishes.append(
                {
                    "attempt": attempt,
                    "target_name": name,
                    "target_sha256": result["target_sha256"],
                    "staging_removed": not (stage_dir / "artifact.tmp").exists(),
                    "file_index": os.stat(reps_dir / name).st_ino,
                }
            )
        # 异内容必须落到不同目标名，不覆盖既有 published artifact
        other_bytes = seed_bytes + b"\x00probe-divergent-tail"
        other_dir = la["staging"] / str(wp_id) / str(uuid.uuid4())
        other_staged = _stage_stream(other_bytes, other_dir / "artifact.tmp")
        other_name = _content_addressed_name(1, other_staged["streaming_sha256"], ".xlsx")
        _publish(other_dir / "artifact.tmp", reps_dir / other_name)
        return {
            "publishes": publishes,
            "target_path_identical": publishes[0]["target_name"] == publishes[1]["target_name"],
            "target_sha_identical": publishes[0]["target_sha256"] == publishes[1]["target_sha256"],
            "target_sha_equals_content_hash": publishes[0]["target_sha256"] == seed_sha,
            "file_index_changed_on_republish": publishes[0]["file_index"] != publishes[1]["file_index"],
            "divergent_content_target_name": other_name,
            "divergent_target_differs": other_name != publishes[0]["target_name"],
            "first_target_survives_divergent_publish": _sha256_file(reps_dir / publishes[0]["target_name"]) == seed_sha,
            "versions_namespace": _resolver_namespace_scan(la["versions"]),
        }

    rec.run("fs2", "content-addressed publish 幂等（同内容同名同 hash；异内容不覆盖）", fs2)

    # ---------------- fs3 os.replace 同卷原子性 ----------------
    def fs3() -> dict[str, Any]:
        """同卷 os.replace 原子性。

        🔴 观测手法说明：Windows 上**任何**打开的目标句柄（含 FILE_SHARE_DELETE）都会让
        `os.replace` 报 WinError 5（见 fs5 的 share-mode 矩阵），所以不能用「长期持有句柄的读者」
        观测原子性。这里分两段：
          size 采样  —— `os.stat` 只读属性、句柄极短，对 replace 干扰最小；观测到中间大小即非原子。
          content 采样 —— 短开短读，判是否读到「撕裂」内容；replace 被拒的次数单独计数（本身就是占用证据）。
        两段都设最小观测数下限，观测不足直接抛 ProbeHarnessError（否则 partial=0 是「没看」而非「没有」）。
        """
        arena = la["base"] / ".probe-atomicity"
        arena.mkdir(parents=True, exist_ok=True)
        target = arena / "current.bin"
        content_a = b"A" * (512 * 1024)
        content_b = b"B" * (768 * 1024)
        size_a, size_b = len(content_a), len(content_b)
        target.write_bytes(content_a)

        def _replace_with_retry(src: Path, retries: int = 200) -> tuple[bool, int]:
            denied = 0
            for _ in range(retries):
                try:
                    os.replace(str(src), str(target))
                    return True, denied
                except OSError:
                    denied += 1
                    time.sleep(0.001)
            return False, denied

        # --- 段 1：size 采样 ---
        rounds = 60
        sources = []
        for index in range(rounds):
            payload = content_b if index % 2 == 0 else content_a
            src = arena / f"stage-size-{index}.tmp"
            src.write_bytes(payload)
            sources.append(src)
        sizes: list[int] = []
        counters = {"stat_missing": 0, "stat_other_error": 0}
        stop = threading.Event()

        def size_sampler() -> None:
            while not stop.is_set():
                try:
                    sizes.append(os.stat(target).st_size)
                except FileNotFoundError:
                    counters["stat_missing"] += 1
                except OSError:
                    counters["stat_other_error"] += 1

        sampler = threading.Thread(target=size_sampler, daemon=True)
        sampler.start()
        size_denied = 0
        size_failed = 0
        for src in sources:
            ok, denied = _replace_with_retry(src)
            size_denied += denied
            if not ok:
                size_failed += 1
                src.unlink(missing_ok=True)
            time.sleep(0.001)
        stop.set()
        sampler.join(timeout=30)
        intermediate = sorted({s for s in sizes if s not in (size_a, size_b)})
        if len(sizes) < 200:
            raise ProbeHarnessError(f"size 采样观测数不足（{len(sizes)}<200），原子性判据无效")

        # --- 段 2：content 采样 ---
        expect = {content_a: "full_old", content_b: "full_new"}
        stop2 = threading.Event()
        tally: dict[str, int] = {}

        def content_reader() -> None:
            tally.update(_observe_while(target, expect, stop2))

        reader = threading.Thread(target=content_reader, daemon=True)
        reader.start()
        content_denied = 0
        content_failed = 0
        for index in range(rounds):
            payload = content_b if index % 2 == 0 else content_a
            src = arena / f"stage-content-{index}.tmp"
            src.write_bytes(payload)
            ok, denied = _replace_with_retry(src)
            content_denied += denied
            if not ok:
                content_failed += 1
                src.unlink(missing_ok=True)
            time.sleep(0.002)
        stop2.set()
        reader.join(timeout=30)
        content_observations = sum(tally.values())
        full_reads = tally.get("full_old", 0) + tally.get("full_new", 0)
        if content_observations < 20:
            raise ProbeHarnessError(f"content 采样观测数不足（{content_observations}<20），撕裂判据无效")

        return {
            "rounds_per_segment": rounds,
            "size_sampling": {
                "observations": len(sizes),
                "distinct_sizes_observed": sorted(set(sizes)),
                "expected_sizes": [size_a, size_b],
                "intermediate_sizes_observed": intermediate,
                "stat_missing": counters["stat_missing"],
                "stat_other_error": counters["stat_other_error"],
                "replace_retry_count": size_denied,
                "replace_permanently_failed": size_failed,
                "no_intermediate_size": not intermediate,
                "never_missing": counters["stat_missing"] == 0,
            },
            "content_sampling": {
                "reader_share_mode": "FILE_SHARE_READ|WRITE|DELETE",
                "observations": content_observations,
                "tally": tally,
                "full_reads": full_reads,
                "torn_reads": tally.get("partial", 0),
                "missing_reads": tally.get("missing", 0),
                "read_denied": tally.get("read_denied", 0),
                "replace_retry_count": content_denied,
                "replace_permanently_failed": content_failed,
                "no_torn_read": tally.get("partial", 0) == 0,
            },
            "atomic_no_partial_or_missing": (not intermediate)
            and counters["stat_missing"] == 0
            and tally.get("partial", 0) == 0,
            "concurrent_open_handle_forces_replace_retry": content_denied > 0 or size_denied > 0,
        }

    rec.run("fs3", "os.replace 同卷原子性（size 采样 + content 采样双判据）", fs3)

    # ---------------- fs4 跨卷 ----------------
    def fs4() -> dict[str, Any]:
        other_volume_root = _pick_other_volume()
        cross_dir = Path(tempfile.mkdtemp(prefix="tmp_task7_probe_crossvol_", dir=str(other_volume_root)))
        try:
            staged = _stage_stream(seed_bytes, cross_dir / "artifact.tmp")
            target = reps_dir / _content_addressed_name(2, staged["streaming_sha256"], ".xlsx")
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_outcome: dict[str, Any]
            try:
                os.replace(str(cross_dir / "artifact.tmp"), str(target))
                replace_outcome = {"raised": False, "target_exists": target.exists()}
            except OSError as exc:
                replace_outcome = {"raised": True, **_oserror_facts(exc)}
            source_survived = (cross_dir / "artifact.tmp").exists()

            # shutil.move 跨卷可用但是 copy 语义 ⇒ size 采样观测目标是否出现「部分可见」中间态
            move_target = cross_dir / "moved-observed.bin"
            big = bytes(range(256)) * (128 * 1024)  # 32 MiB，拉长拷贝窗口以便观测未完成态
            attempts: list[dict[str, Any]] = []
            partial_seen = 0
            for attempt in range(3):
                src = work_root / f"tmp-crossvol-src-{attempt}.bin"
                src.write_bytes(big)
                move_target.unlink(missing_ok=True)
                stop = threading.Event()
                observed: list[int] = []

                def sampler() -> None:
                    while not stop.is_set():
                        try:
                            observed.append(os.stat(move_target).st_size)
                        except OSError:
                            observed.append(-1)  # 尚不存在

                thread = threading.Thread(target=sampler, daemon=True)
                thread.start()
                shutil.move(str(src), str(move_target))
                stop.set()
                thread.join(timeout=30)
                incomplete = sorted({s for s in observed if 0 <= s < len(big)})
                attempts.append(
                    {
                        "attempt": attempt,
                        "observations": len(observed),
                        "absent_observations": sum(1 for s in observed if s == -1),
                        "full_size_observations": sum(1 for s in observed if s == len(big)),
                        "incomplete_size_count": len(incomplete),
                        "incomplete_sizes_sample": incomplete[:6],
                        "incomplete_size_max": max(incomplete) if incomplete else None,
                    }
                )
                partial_seen = max(partial_seen, len(incomplete))
                move_target.unlink(missing_ok=True)
            return {
                "source_volume": str(cross_dir.drive).upper(),
                "target_volume": str(reps_dir.drive).upper(),
                "cross_volume_confirmed": str(cross_dir.drive).upper() != str(reps_dir.drive).upper(),
                "os_replace": replace_outcome,
                "source_survived_after_failure": source_survived,
                "target_absent_after_failure": not target.exists(),
                "shutil_move_size_bytes": len(big),
                "shutil_move_attempts": attempts,
                "shutil_move_distinct_incomplete_sizes_max": partial_seen,
                "shutil_move_destination_visible_while_incomplete": partial_seen > 0,
            }
        finally:
            shutil.rmtree(cross_dir, ignore_errors=True)

    rec.run("fs4", "os.replace 跨卷失败 + shutil.move 跨卷可观测 partial", fs4)

    # ---------------- fs5 文件占用 ----------------
    def fs5() -> dict[str, Any]:
        """文件占用矩阵：逐 share 模式实测 `os.replace`，并单独验证「目标不预先存在」分支。

        `os.replace` 在 Windows 落到 `MoveFileExW(..., MOVEFILE_REPLACE_EXISTING)`；替换既有目标要求
        删除该目标，而 MoveFileEx 的这条路径**不接受目标上存在任何句柄**——连 FILE_SHARE_DELETE
        也不行。故本用例把六种 share 模式全跑一遍，避免只测一种就下结论。
        """
        arena = la["base"] / ".probe-occupancy"
        arena.mkdir(parents=True, exist_ok=True)
        share_modes = ("none", "read", "read_write", "read_delete", "read_write_delete", "delete_only")
        results: dict[str, Any] = {}

        def _hold_and_replace(label: str, hold_mode: str, hold_which: str) -> dict[str, Any]:
            target = arena / f"{label}-current.bin"
            source = arena / f"{label}-stage.tmp"
            old = f"OLD::{label}".encode() * 64
            new = f"NEW::{label}".encode() * 64
            target.write_bytes(old)
            source.write_bytes(new)
            held = target if hold_which == "target" else source
            sentinel = arena / f"{label}.ready"
            sentinel.unlink(missing_ok=True)
            proc = _spawn(
                [
                    "_child-hold",
                    "--path",
                    str(held),
                    "--hold-mode",
                    hold_mode,
                    "--ready",
                    str(sentinel),
                    "--hold-seconds",
                    "25",
                ]
            )
            try:
                _wait_ready(sentinel, "ready")
                try:
                    os.replace(str(source), str(target))
                    outcome: dict[str, Any] = {"raised": False}
                except OSError as exc:
                    outcome = {"raised": True, **_oserror_facts(exc)}
            finally:
                # 🔴 share=none 时父进程连读都读不了目标，内容核对必须在句柄释放之后做
                proc.kill()
                proc.communicate(timeout=30)
            after = target.read_bytes() if target.exists() else None
            return {
                "hold_mode": hold_mode,
                "held_file": hold_which,
                "os_replace": outcome,
                "target_is_old_content": after == old,
                "target_is_new_content": after == new,
                "source_survived": source.exists(),
            }

        for share_mode in share_modes:
            results[f"target_held_{share_mode}"] = _hold_and_replace(
                f"target_held_{share_mode}", share_mode, "target"
            )
        results["source_held_read_write"] = _hold_and_replace("source_held_read_write", "read_write", "source")

        # 关键分支：content-addressed 不可变发布下，目标名从不预先存在
        fresh_label = "fresh_target_while_old_current_held"
        old_current = arena / f"{fresh_label}-000000001-old.bin"
        fresh_target = arena / f"{fresh_label}-000000002-new.bin"
        fresh_source = arena / f"{fresh_label}-stage.tmp"
        old_current.write_bytes(b"OLD-CURRENT-ARTIFACT" * 64)
        fresh_source.write_bytes(b"NEW-CONTENT-ADDRESSED-ARTIFACT" * 64)
        fresh_target.unlink(missing_ok=True)
        sentinel = arena / f"{fresh_label}.ready"
        sentinel.unlink(missing_ok=True)
        proc = _spawn(
            [
                "_child-hold",
                "--path",
                str(old_current),
                "--hold-mode",
                "read",
                "--ready",
                str(sentinel),
                "--hold-seconds",
                "25",
            ]
        )
        try:
            _wait_ready(sentinel, "ready")
            try:
                os.replace(str(fresh_source), str(fresh_target))
                fresh_outcome: dict[str, Any] = {"raised": False}
            except OSError as exc:
                fresh_outcome = {"raised": True, **_oserror_facts(exc)}
        finally:
            proc.kill()
            proc.communicate(timeout=30)
        results[fresh_label] = {
            "hold_mode": "read",
            "held_file": "previous_current_artifact",
            "target_preexisting": False,
            "os_replace": fresh_outcome,
            "target_exists_after": fresh_target.exists(),
            "old_current_intact": old_current.exists(),
        }

        target_cases = {k: v for k, v in results.items() if k.startswith("target_held_")}
        return {
            "cases": results,
            "share_modes_tested": list(share_modes),
            "occupied_target_blocks_replace_in_all_share_modes": all(
                v["os_replace"]["raised"] for v in target_cases.values()
            ),
            "occupied_target_winerrors": sorted(
                {v["os_replace"].get("winerror") for v in target_cases.values()}
            ),
            "share_delete_does_not_help": target_cases["target_held_read_write_delete"]["os_replace"]["raised"],
            "occupied_source_blocks_replace": results["source_held_read_write"]["os_replace"]["raised"],
            "occupied_source_winerror": results["source_held_read_write"]["os_replace"].get("winerror"),
            "old_content_preserved_on_failure": all(
                v["target_is_old_content"] for v in target_cases.values()
            ),
            "fresh_target_publish_succeeds_while_old_current_held": not fresh_outcome["raised"],
            "architectural_consequence": "os.replace 无法在目标被占用时替换（任何 share 模式都不行）"
            "⇒ 固定路径覆盖式发布在 Windows 天然脆弱；content-addressed 不可变目标名从不预先存在，"
            "publish 因此不受占用影响，current 切换改由 DB pointer 承担",
        }

    rec.run("fs5", "文件占用矩阵：六种 share 模式 + 目标不预先存在分支", fs5)

    # ---------------- fs6 进程中断 ----------------
    def fs6() -> dict[str, Any]:
        arena = la["staging"] / str(wp_id)
        total = 4 * 1024 * 1024
        chunk = 256 * 1024
        out: dict[str, Any] = {}

        # 6a 写 staging 途中被 kill
        stage_dir = arena / str(uuid.uuid4())
        staging_file = stage_dir / "artifact.tmp"
        sentinel = stage_dir / "ready"
        stage_dir.mkdir(parents=True, exist_ok=True)
        proc = _spawn(
            [
                "_child-slow-write",
                "--path",
                str(staging_file),
                "--total",
                str(total),
                "--chunk",
                str(chunk),
                "--ready",
                str(sentinel),
                "--ready-after",
                "2",
                "--sleep",
                "0.05",
            ]
        )
        _wait_ready(sentinel, "ready")
        time.sleep(0.15)
        reaped = _kill_and_reap(proc)
        exists = staging_file.exists()
        size = staging_file.stat().st_size if exists else 0
        residue_sha = _sha256_file(staging_file) if exists else None
        expected_full_sha = hashlib.sha256(_expected_slow_payload(total, chunk)).hexdigest()
        out["mid_write_kill"] = {
            **reaped,
            "staging_exists": exists,
            "staging_size_bytes": size,
            "expected_total_bytes": total,
            "is_partial": 0 < size < total,
            "residue_sha256": residue_sha,
            "expected_full_sha256": expected_full_sha,
            "residue_hash_differs_from_full": residue_sha != expected_full_sha,
            "residue_in_staging_namespace": ".staging" in str(staging_file),
            "resolver_namespace_files": _resolver_namespace_scan(la["versions"]),
            "publish_gate_refuses_residue": residue_sha != expected_full_sha,
        }

        # 6b staging 完成后、publish 前被 kill
        stage_dir2 = arena / str(uuid.uuid4())
        staging_file2 = stage_dir2 / "artifact.tmp"
        sentinel2 = stage_dir2 / "ready"
        stage_dir2.mkdir(parents=True, exist_ok=True)
        proc2 = _spawn(
            [
                "_child-slow-write",
                "--path",
                str(staging_file2),
                "--total",
                str(chunk * 4),
                "--chunk",
                str(chunk),
                "--ready",
                str(sentinel2),
                "--ready-after",
                "1",
                "--sleep",
                "0.01",
            ]
        )
        _wait_ready(sentinel2, "complete")
        reaped2 = _kill_and_reap(proc2)
        complete_sha = _sha256_file(staging_file2)
        out["post_stage_pre_publish_kill"] = {
            **reaped2,
            "staging_exists": staging_file2.exists(),
            "staging_size_bytes": staging_file2.stat().st_size,
            "staging_sha256": complete_sha,
            "staging_hash_valid": complete_sha == hashlib.sha256(_expected_slow_payload(chunk * 4, chunk)).hexdigest(),
            "published_anything": False,
            "resolver_namespace_excludes_staging": all(
                ".staging" not in name for name in _resolver_namespace_scan(la["versions"])
            ),
            "classification": "orphan_candidate_invisible_to_resolver",
        }
        out["os_replace_interruption_note"] = {
            "independently_injected": False,
            "derived_from": "fs3",
            "reason": "os.replace 是单次 MoveFileExW 元数据操作，无法在用户态注入「半个 rename」；"
            "原子性判据取 fs3 的并发观测（partial=0 且 missing=0）",
        }
        return out

    rec.run("fs6", "写 staging 途中 kill / staging 完成后 kill 的残留归类", fs6)

    # ---------------- fs7 路径安全（Property 42）----------------
    def fs7() -> dict[str, Any]:
        root_a = la["base"]
        root_b = lb["base"]
        root_a.mkdir(parents=True, exist_ok=True)
        root_b.mkdir(parents=True, exist_ok=True)
        (root_b / "wp").mkdir(parents=True, exist_ok=True)
        (root_b / "wp" / "artifact.xlsx").write_bytes(b"PROJECT-B-ONLY")

        cases: dict[str, Any] = {}
        for label, relative in (
            ("traversal_relative", r"..\..\..\outside.xlsx"),
            ("traversal_nested", r"wp\..\..\..\..\outside.xlsx"),
            ("traversal_posix_style", "../../../outside.xlsx"),
            ("absolute_outside", r"C:\Windows\Temp\tmp_task7_evil.xlsx"),
            ("unc_path", r"\\127.0.0.1\C$\tmp_task7_evil.xlsx"),
            ("inside_ok", r"wp\artifact.xlsx"),
        ):
            cases[label] = {"relative": relative, **_resolve_within_root(root_a, relative)}

        # 跨项目复用
        cases["cross_project_absolute"] = {
            "relative": str(root_b / "wp" / "artifact.xlsx"),
            **_resolve_within_root(root_a, str(root_b / "wp" / "artifact.xlsx")),
        }
        cases["cross_project_traversal"] = {
            "relative": f"..\\..\\{root_b.relative_to(work_root / 'storage').parts[0]}\\workpapers\\wp\\artifact.xlsx",
        }
        cases["cross_project_traversal"].update(
            _resolve_within_root(root_a, cases["cross_project_traversal"]["relative"])
        )
        same_rel = r"wp\artifact.xlsx"
        resolved_a = _resolve_within_root(root_a, same_rel)["path_resolved"]
        resolved_b = _resolve_within_root(root_b, same_rel)["path_resolved"]

        # 软链接越界
        link_dir = root_a / "escape-link"
        escape_target = Path(tempfile.mkdtemp(prefix="tmp_task7_probe_escape_"))
        (escape_target / "artifact.xlsx").write_bytes(b"OUTSIDE-ROOT")
        symlink_mechanism = "none"
        symlink_error: dict[str, Any] | None = None
        try:
            os.symlink(str(escape_target), str(link_dir), target_is_directory=True)
            symlink_mechanism = "os.symlink"
        except OSError as exc:
            symlink_error = _oserror_facts(exc)
            proc = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link_dir), str(escape_target)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode == 0:
                symlink_mechanism = "mklink /J (junction)"
            else:
                symlink_error = {**(symlink_error or {}), "mklink_stderr": (proc.stderr or proc.stdout)[-200:]}
        if symlink_mechanism == "none":
            cases["symlink_escape"] = {
                "relative": r"escape-link\artifact.xlsx",
                "covered": False,
                "mechanism": "none",
                "blocker": symlink_error,
            }
        else:
            cases["symlink_escape"] = {
                "relative": r"escape-link\artifact.xlsx",
                "covered": True,
                "mechanism": symlink_mechanism,
                **_resolve_within_root(root_a, r"escape-link\artifact.xlsx"),
            }

        # 扩展名伪装
        masq_dir = root_a / ".probe-masquerade"
        masq_dir.mkdir(parents=True, exist_ok=True)
        fake_xlsx = masq_dir / "not-a-zip.xlsx"
        fake_xlsx.write_bytes(b"<html>definitely not ooxml</html>")
        renamed_docx = masq_dir / "really-xlsx.docx"
        renamed_docx.write_bytes(seed_bytes)
        masquerade = {
            "non_zip_with_xlsx_ext": _detect_document_type(fake_xlsx),
            "xlsx_bytes_with_docx_ext": _detect_document_type(renamed_docx),
        }
        masquerade["non_zip_rejected"] = masquerade["non_zip_with_xlsx_ext"]["magic_ok"] is False
        masquerade["ext_type_mismatch_detected"] = masquerade["xlsx_bytes_with_docx_ext"]["detected"] == "xlsx"

        try:
            shutil.rmtree(escape_target, ignore_errors=True)
        finally:
            pass
        return {
            "cases": cases,
            "escape_cases_rejected": sorted(
                label
                for label, data in cases.items()
                if data.get("accepted") is False and label not in ("inside_ok",)
            ),
            "inside_path_accepted": cases["inside_ok"]["accepted"],
            "cross_project_same_relative_resolves_differently": resolved_a != resolved_b,
            "cross_project_resolved_a": resolved_a,
            "cross_project_resolved_b": resolved_b,
            "symlink_escape_covered": bool(cases["symlink_escape"].get("covered")),
            "masquerade": masquerade,
        }

    rec.run("fs7", "路径安全：穿越/绝对路径/UNC/软链接越界/跨项目复用/扩展名伪装", fs7)

    # ---------------- fs8 校验门注入（Property 9）----------------
    def fs8() -> dict[str, Any]:
        published_name = _content_addressed_name(1, seed_sha, ".xlsx")
        current = reps_dir / published_name
        if not current.exists():
            raise ProbeHarnessError("fs8 依赖 fs2 已发布的 current artifact")
        before_sha = _sha256_file(current)
        before_namespace = _resolver_namespace_scan(la["versions"])
        pointer = {"generation": 1, "revision": 1, "artifact_sha256": before_sha}

        injections: dict[str, Any] = {}
        for label, mutate in (
            ("zip_structure", lambda b: b[: len(b) // 2]),
            ("ooxml_parts", _strip_content_types),
            ("roundtrip_equivalence", _rename_first_sheet),
        ):
            stage_dir = la["staging"] / str(wp_id) / str(uuid.uuid4())
            payload = mutate(seed_bytes)
            staged = _stage_stream(payload, stage_dir / "artifact.tmp")
            staging_file = stage_dir / "artifact.tmp"
            gates: list[dict[str, Any]] = []
            passed_all = True
            for gate_name, gate in (
                ("zip_structure", lambda p: _validate_zip_structure(p)),
                ("ooxml_parts", lambda p: _validate_ooxml_parts(p, "xlsx")),
                ("roundtrip_equivalence", lambda p: _validate_roundtrip(p, seed_sheets)),
            ):
                try:
                    ok, detail = gate(staging_file)
                except Exception as exc:  # noqa: BLE001 - 校验器抛错也算 gate 失败，但要留下原始类型
                    ok, detail = False, f"{type(exc).__name__}:{exc}"
                gates.append({"gate": gate_name, "passed": ok, "detail": detail})
                if not ok:
                    passed_all = False
                    break
            published = False
            if passed_all:
                # 只有全部 gate 通过才 publish 并推进 pointer/revision（Task 15 的语义）
                _publish(staging_file, reps_dir / _content_addressed_name(9, staged["streaming_sha256"], ".xlsx"))
                pointer = {"generation": 9, "revision": 2, "artifact_sha256": staged["streaming_sha256"]}
                published = True
            injections[label] = {
                "injection_point": label,
                "staged_sha256": staged["streaming_sha256"],
                "gates": gates,
                "first_failed_gate": next((g["gate"] for g in gates if not g["passed"]), None),
                "published": published,
                "current_sha_after": _sha256_file(current),
                "current_sha_unchanged": _sha256_file(current) == before_sha,
                "pointer_after": dict(pointer),
                "pointer_unchanged": pointer == {"generation": 1, "revision": 1, "artifact_sha256": before_sha},
                "versions_namespace_unchanged": _resolver_namespace_scan(la["versions"]) == before_namespace,
                "staging_residue_exists": staging_file.exists(),
            }
        return {
            "current_artifact": published_name,
            "current_sha256_before": before_sha,
            "declared_sheet_names": seed_sheets,
            "injections": injections,
            "all_injections_blocked_publish": all(not v["published"] for v in injections.values()),
            "all_injections_left_current_unchanged": all(v["current_sha_unchanged"] for v in injections.values()),
            "all_injections_left_pointer_unchanged": all(v["pointer_unchanged"] for v in injections.values()),
        }

    rec.run("fs8", "校验门注入（zip/OOXML/roundtrip）失败后 current hash/pointer/revision 不变", fs8)

    return {
        "seed_template": str(SEED_XLSX.relative_to(REPO_ROOT)).replace("\\", "/"),
        "seed_sha256": seed_sha,
        "seed_sheet_names": seed_sheets,
        "project_a": str(project_a),
        "project_b": str(project_b),
        "wp_id": str(wp_id),
        "entry_id": entry_id,
        "work_root": str(work_root),
        "layout": {k: str(v) for k, v in la.items()},
    }


def _expected_slow_payload(total: int, chunk: int) -> bytes:
    parts: list[bytes] = []
    written = 0
    index = 0
    while written < total:
        block = bytes([index % 251]) * min(chunk, total - written)
        parts.append(block)
        written += len(block)
        index += 1
    return b"".join(parts)


def _strip_content_types(data: bytes) -> bytes:
    import io

    src = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "[Content_Types].xml":
                continue
            zout.writestr(item, zin.read(item.filename))
    return out.getvalue()


def _rename_first_sheet(data: bytes) -> bytes:
    import io
    import re

    src = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            payload = zin.read(item.filename)
            if item.filename == "xl/workbook.xml":
                text = payload.decode("utf-8")
                text = re.sub(r'(<sheet[^>]*\sname=")([^"]*)(")', r"\1PROBE_DRIFT\3", text, count=1)
                payload = text.encode("utf-8")
            zout.writestr(item, payload)
    return out.getvalue()


def _pick_other_volume() -> Path:
    """挑一个与项目不同卷的可写目录（跨卷用例的前置条件）。"""
    project_drive = REPO_ROOT.drive.upper()
    candidates = [Path(tempfile.gettempdir())]
    for letter in "CDEFG":
        candidates.append(Path(f"{letter}:/"))
    for candidate in candidates:
        try:
            if candidate.drive.upper() and candidate.drive.upper() != project_drive and candidate.exists():
                probe = candidate / f"tmp_task7_probe_wtest_{uuid.uuid4().hex[:8]}"
                probe.mkdir(parents=True, exist_ok=True)
                probe.rmdir()
                return candidate
        except OSError:
            continue
    raise ProbeHarnessError(f"本机找不到与项目卷 {project_drive} 不同的可写卷，跨卷用例无法实证")


# ---------------------------------------------------------------------------
# DB 阶段
# ---------------------------------------------------------------------------

_DDL = """
CREATE SCHEMA {s};

CREATE TABLE {s}.working_paper_artifact (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    wp_id uuid NOT NULL,
    kind varchar(32) NOT NULL,
    state varchar(32) NOT NULL,
    relative_path text NOT NULL,
    sha256 char(64) NOT NULL,
    size_bytes bigint NOT NULL,
    document_type varchar(16) NOT NULL,
    retention_class varchar(48) NOT NULL,
    durable_at timestamptz,
    quarantined_at timestamptz,
    published_at timestamptz,
    orphaned_at timestamptz,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_wpa_kind CHECK (kind IN ('canonical','upgrade_candidate','incoming','projection','definition','template','evidence','trace_bundle')),
    CONSTRAINT ck_wpa_state CHECK (state IN ('staged','durable','candidate','published','orphan','quarantined','deleted')),
    CONSTRAINT ck_wpa_incoming_never_published CHECK (NOT (kind = 'incoming' AND state = 'published')),
    CONSTRAINT ck_wpa_quarantined_not_durable CHECK (NOT (state = 'quarantined' AND durable_at IS NOT NULL))
);
CREATE UNIQUE INDEX uq_wpa_content_addressed ON {s}.working_paper_artifact (project_id, kind, sha256);

CREATE TABLE {s}.working_paper_content_version (
    id uuid PRIMARY KEY,
    wp_id uuid NOT NULL,
    revision integer NOT NULL,
    parent_version_id uuid REFERENCES {s}.working_paper_content_version (id),
    projection_artifact_sha256 char(64) NOT NULL,
    source varchar(32) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpcv_revision UNIQUE (wp_id, revision)
);

CREATE TABLE {s}.working_paper_content_representation (
    id uuid PRIMARY KEY,
    wp_id uuid NOT NULL,
    content_version_id uuid NOT NULL REFERENCES {s}.working_paper_content_version (id),
    entry_id varchar(128) NOT NULL,
    generation bigint NOT NULL,
    document_type varchar(16) NOT NULL,
    artifact_id uuid NOT NULL REFERENCES {s}.working_paper_artifact (id),
    artifact_sha256 char(64) NOT NULL,
    definition_bundle_id uuid NOT NULL,
    definition_bundle_sha256 char(64) NOT NULL,
    reason varchar(32) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_wpcr_generation UNIQUE (wp_id, entry_id, content_version_id, generation)
);

CREATE TABLE {s}.working_paper_sync_entry_state (
    wp_id uuid NOT NULL,
    entry_id varchar(128) NOT NULL,
    current_representation_id uuid NOT NULL REFERENCES {s}.working_paper_content_representation (id),
    representation_generation bigint NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (wp_id, entry_id)
);

CREATE TABLE {s}.working_paper_artifact_gc_audit (
    id uuid PRIMARY KEY,
    artifact_id uuid NOT NULL,
    policy_version varchar(64) NOT NULL,
    dry_run boolean NOT NULL,
    decision varchar(24) NOT NULL,
    reason varchar(64) NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION {s}.trg_representation_artifact_must_be_published() RETURNS trigger AS $body$
DECLARE
    a_kind text;
    a_state text;
BEGIN
    SELECT kind, state INTO a_kind, a_state
    FROM {s}.working_paper_artifact WHERE id = NEW.artifact_id;
    IF a_state <> 'published' OR a_kind NOT IN ('canonical','projection') THEN
        RAISE EXCEPTION 'representation must reference a published canonical artifact (kind=%, state=%)', a_kind, a_state
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$body$ LANGUAGE plpgsql;

CREATE TRIGGER trg_wpcr_artifact_published
    BEFORE INSERT OR UPDATE ON {s}.working_paper_content_representation
    FOR EACH ROW EXECUTE FUNCTION {s}.trg_representation_artifact_must_be_published();
"""


class _SqlLog:
    def __init__(self, schema: str) -> None:
        self.schema = schema
        self.entries: list[dict[str, Any]] = []

    def note(self, kind: str, sql: str) -> None:
        normalized = " ".join(sql.split())
        self.entries.append({"seq": len(self.entries) + 1, "kind": kind, "sql": normalized[:600]})


async def _db_phase(work_root: Path, rec: _Recorder, fs_meta: dict[str, Any]) -> dict[str, Any]:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    os.environ.setdefault("DB_DISABLE_SSL", "True")
    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise ProbeHarnessError(f"DB 阶段需要真实 PostgreSQL，实得 {settings.DATABASE_URL.split('://')[0]}")
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=connect_args)

    schema = f"tmp_task7_probe_{uuid.uuid4().hex[:12]}"
    log = _SqlLog(schema)
    project_id = uuid.UUID(fs_meta["project_a"])
    # DB 阶段用独立 wp_id：让 `.versions/{wp}` 子树只含本阶段发布的文件，reconciliation 扫描结果干净
    wp_id = uuid.uuid4()
    entry_id = fs_meta["entry_id"]
    bundle_id = uuid.uuid4()
    bundle_sha = hashlib.sha256(b"approved-definition-bundle").hexdigest()

    versions_root = Path(fs_meta["layout"]["versions"])
    db_arena = work_root / "db-artifacts" / str(wp_id)
    db_arena.mkdir(parents=True, exist_ok=True)

    async def _exec(conn: Any, sql: str, params: dict[str, Any] | None = None, kind: str = "DML") -> Any:
        log.note(kind, sql)
        return await conn.execute(sa.text(sql), params or {})

    def _publish_bytes(payload: bytes, generation: int) -> dict[str, Any]:
        stage_dir = Path(fs_meta["layout"]["staging"]) / str(wp_id) / str(uuid.uuid4())
        staged = _stage_stream(payload, stage_dir / "artifact.tmp")
        target = versions_root / str(wp_id) / "representations" / entry_id / _content_addressed_name(
            generation, staged["streaming_sha256"], ".xlsx"
        )
        _publish(stage_dir / "artifact.tmp", target)
        return {
            "path": target,
            "relative_path": str(target.relative_to(work_root)).replace("\\", "/"),
            "sha256": staged["streaming_sha256"],
            "size_bytes": staged["size_bytes"],
        }

    resolver_sql = """
        SELECT a.sha256 AS artifact_sha256, a.relative_path, a.state AS artifact_state,
               r.generation, v.revision
        FROM {s}.working_paper_sync_entry_state es
        JOIN {s}.working_paper_content_representation r ON r.id = es.current_representation_id
        JOIN {s}.working_paper_content_version v ON v.id = r.content_version_id
        JOIN {s}.working_paper_artifact a ON a.id = r.artifact_id
        WHERE es.wp_id = :wp AND es.entry_id = :entry
          AND a.state = 'published' AND a.kind IN ('canonical','projection')
    """.replace("{s}", schema)

    async def resolve(conn: Any) -> list[dict[str, Any]]:
        rows = (await _exec(conn, resolver_sql, {"wp": wp_id, "entry": entry_id}, kind="SELECT")).mappings().all()
        return [dict(row) for row in rows]

    async def counts(conn: Any) -> dict[str, int]:
        out: dict[str, int] = {}
        for name in (
            "working_paper_artifact",
            "working_paper_content_version",
            "working_paper_content_representation",
            "working_paper_sync_entry_state",
            "working_paper_artifact_gc_audit",
        ):
            sql = f"SELECT count(*) AS n FROM {schema}.{name}"
            out[name] = int((await _exec(conn, sql, kind="SELECT")).scalar_one())
        return out

    db_meta: dict[str, Any] = {"schema": schema, "database": None, "server_version": None}
    baseline: dict[str, Any] = {}

    try:
        async with engine.connect() as conn:
            row = (
                await _exec(conn, "SELECT current_database() AS db, version() AS v", kind="SELECT")
            ).mappings().one()
            db_meta["database"] = row["db"]
            db_meta["server_version"] = row["v"]

        # ---------------- db1 scratch schema ----------------
        async with engine.begin() as conn:
            log.note("TX", f"BEGIN -- create scratch schema {schema}")
            # plpgsql 函数体含分号，不能按 ';' 盲切：先取出 CREATE FUNCTION..$body$ 整段单独执行
            ddl_text = _DDL.format(s=schema)
            head, _, rest = ddl_text.partition("CREATE FUNCTION")
            for statement in [s.strip() for s in head.split(";") if s.strip()]:
                await _exec(conn, statement, kind="DDL")
            func_sql, _, trigger_sql = rest.partition("$body$ LANGUAGE plpgsql;")
            await _exec(conn, "CREATE FUNCTION" + func_sql + "$body$ LANGUAGE plpgsql", kind="DDL")
            for statement in [s.strip() for s in trigger_sql.split(";") if s.strip()]:
                await _exec(conn, statement, kind="DDL")
            log.note("TX", "COMMIT -- scratch schema created")

        rec.run(
            "db1",
            "scratch schema 建 artifact/version/representation/entry_state/gc_audit 等价结构",
            lambda: {
                "schema": schema,
                "schema_is_scratch": schema.startswith("tmp_task7_probe_"),
                "tables": [
                    "working_paper_artifact",
                    "working_paper_content_version",
                    "working_paper_content_representation",
                    "working_paper_sync_entry_state",
                    "working_paper_artifact_gc_audit",
                ],
                "trigger": "trg_wpcr_artifact_published",
                "business_tables_touched": [],
                "db_phase_wp_id": str(wp_id),
                "db_phase_project_id": str(project_id),
            },
        )

        # ---------------- baseline：rev1 / gen1 published ----------------
        old_artifact = _publish_bytes(b"OLD-PUBLISHED-ARTIFACT-" + os.urandom(8), 1)
        old_ids = {"artifact": uuid.uuid4(), "version": uuid.uuid4(), "representation": uuid.uuid4()}
        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- baseline rev1/gen1")
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_artifact
                    (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes,
                     document_type, retention_class, published_at)
                    VALUES (:id,:pid,:wp,'canonical','published',:rel,:sha,:size,'xlsx','canonical_orphan', now())""",
                {
                    "id": old_ids["artifact"],
                    "pid": project_id,
                    "wp": wp_id,
                    "rel": old_artifact["relative_path"],
                    "sha": old_artifact["sha256"],
                    "size": old_artifact["size_bytes"],
                },
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_content_version
                    (id, wp_id, revision, projection_artifact_sha256, source)
                    VALUES (:id,:wp,1,:sha,'probe_baseline')""",
                {"id": old_ids["version"], "wp": wp_id, "sha": old_artifact["sha256"]},
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_content_representation
                    (id, wp_id, content_version_id, entry_id, generation, document_type,
                     artifact_id, artifact_sha256, definition_bundle_id, definition_bundle_sha256, reason)
                    VALUES (:id,:wp,:ver,:entry,1,'xlsx',:art,:sha,:bid,:bsha,'content_commit')""",
                {
                    "id": old_ids["representation"],
                    "wp": wp_id,
                    "ver": old_ids["version"],
                    "entry": entry_id,
                    "art": old_ids["artifact"],
                    "sha": old_artifact["sha256"],
                    "bid": bundle_id,
                    "bsha": bundle_sha,
                },
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_sync_entry_state
                    (wp_id, entry_id, current_representation_id, representation_generation)
                    VALUES (:wp,:entry,:rep,1)""",
                {"wp": wp_id, "entry": entry_id, "rep": old_ids["representation"]},
            )
            log.note("TX", "COMMIT -- baseline committed")

        async with engine.connect() as conn:
            baseline = {
                "resolver": await resolve(conn),
                "counts": await counts(conn),
                "old_artifact_sha256": old_artifact["sha256"],
                "old_artifact_exists_on_disk": old_artifact["path"].exists(),
            }

        # ---------------- db2 publish 后 DB rollback ----------------
        rollback_records: dict[str, Any] = {}
        for label, injector in (("injected_exception", "python_raise"), ("constraint_violation", "duplicate_revision")):
            new_artifact = _publish_bytes(f"ROLLBACK-CASE-{label}-".encode() + os.urandom(8), 2)
            new_ids = {"artifact": uuid.uuid4(), "version": uuid.uuid4(), "representation": uuid.uuid4()}
            failure: dict[str, Any]
            try:
                async with engine.begin() as conn:
                    log.note("TX", f"BEGIN -- db2 {label}")
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_artifact
                            (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes,
                             document_type, retention_class, published_at)
                            VALUES (:id,:pid,:wp,'canonical','published',:rel,:sha,:size,'xlsx','canonical_orphan', now())""",
                        {
                            "id": new_ids["artifact"],
                            "pid": project_id,
                            "wp": wp_id,
                            "rel": new_artifact["relative_path"],
                            "sha": new_artifact["sha256"],
                            "size": new_artifact["size_bytes"],
                        },
                    )
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_content_version
                            (id, wp_id, revision, parent_version_id, projection_artifact_sha256, source)
                            VALUES (:id,:wp,2,:parent,:sha,'probe_rollback')""",
                        {
                            "id": new_ids["version"],
                            "wp": wp_id,
                            "parent": old_ids["version"],
                            "sha": new_artifact["sha256"],
                        },
                    )
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_content_representation
                            (id, wp_id, content_version_id, entry_id, generation, document_type,
                             artifact_id, artifact_sha256, definition_bundle_id, definition_bundle_sha256, reason)
                            VALUES (:id,:wp,:ver,:entry,2,'xlsx',:art,:sha,:bid,:bsha,'content_commit')""",
                        {
                            "id": new_ids["representation"],
                            "wp": wp_id,
                            "ver": new_ids["version"],
                            "entry": entry_id,
                            "art": new_ids["artifact"],
                            "sha": new_artifact["sha256"],
                            "bid": bundle_id,
                            "bsha": bundle_sha,
                        },
                    )
                    await _exec(
                        conn,
                        f"""UPDATE {schema}.working_paper_sync_entry_state
                            SET current_representation_id = :rep, representation_generation = 2, updated_at = now()
                            WHERE wp_id = :wp AND entry_id = :entry""",
                        {"rep": new_ids["representation"], "wp": wp_id, "entry": entry_id},
                    )
                    if injector == "python_raise":
                        raise _InjectedFailure("outbox enqueue failed after pointer update")
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_content_version
                            (id, wp_id, revision, projection_artifact_sha256, source)
                            VALUES (:id,:wp,2,:sha,'probe_duplicate')""",
                        {"id": uuid.uuid4(), "wp": wp_id, "sha": new_artifact["sha256"]},
                    )
            except _InjectedFailure as exc:
                failure = {"failure_kind": "python_exception", "exc_type": "_InjectedFailure", "message": str(exc)}
                log.note("TX", f"ROLLBACK -- db2 {label}")
            except Exception as exc:  # noqa: BLE001 - 期望的约束冲突；类型/pgcode 全部记录
                failure = {
                    "failure_kind": "db_constraint",
                    "exc_type": type(exc).__name__,
                    "pgcode": getattr(getattr(exc, "orig", None), "sqlstate", None)
                    or getattr(exc, "sqlstate", None),
                    "message": str(exc)[:300],
                }
                log.note("TX", f"ROLLBACK -- db2 {label}")
            else:
                failure = {"failure_kind": "none", "note": "注入未生效"}

            async with engine.connect() as conn:
                after_resolver = await resolve(conn)
                after_counts = await counts(conn)
                artifact_row = (
                    await _exec(
                        conn,
                        f"SELECT count(*) AS n FROM {schema}.working_paper_artifact WHERE sha256 = :sha",
                        {"sha": new_artifact["sha256"]},
                        kind="SELECT",
                    )
                ).scalar_one()
                pointer = (
                    await _exec(
                        conn,
                        f"""SELECT representation_generation AS gen, current_representation_id AS rep
                            FROM {schema}.working_paper_sync_entry_state WHERE wp_id=:wp AND entry_id=:entry""",
                        {"wp": wp_id, "entry": entry_id},
                        kind="SELECT",
                    )
                ).mappings().one()
            rollback_records[label] = {
                "failure": failure,
                "published_file_sha256": new_artifact["sha256"],
                "published_file_relative_path": new_artifact["relative_path"],
                "file_survived_db_rollback": new_artifact["path"].exists(),
                "file_sha_on_disk_after_rollback": _sha256_file(new_artifact["path"])
                if new_artifact["path"].exists()
                else None,
                "artifact_rows_for_new_sha": int(artifact_row),
                "pointer_generation": int(pointer["gen"]),
                "pointer_representation_is_old": str(pointer["rep"]) == str(old_ids["representation"]),
                "resolver_rows": after_resolver,
                "resolver_returns_old_artifact_only": [r["artifact_sha256"] for r in after_resolver]
                == [old_artifact["sha256"]],
                "counts_after": after_counts,
                "counts_equal_baseline": after_counts == baseline["counts"],
            }

        rec.run(
            "db2",
            "publish 到磁盘后 DB rollback：pointer/revision/representation 不变、文件仍在",
            lambda: {
                "cases": rollback_records,
                "all_cases_pointer_unchanged": all(
                    v["pointer_generation"] == 1 and v["pointer_representation_is_old"]
                    for v in rollback_records.values()
                ),
                "all_cases_file_survived": all(v["file_survived_db_rollback"] for v in rollback_records.values()),
                "all_cases_invisible_to_resolver": all(
                    v["resolver_returns_old_artifact_only"] for v in rollback_records.values()
                ),
                "filesystem_participates_in_db_transaction": False,
                "conclusion": "DB ROLLBACK 不回滚已 publish 的文件 ⇒ 文件系统与 PostgreSQL 不是同一事务；"
                "失败只留下不可见 orphan",
            },
        )

        # ---------------- db3 representation 不得引用 candidate/incoming ----------------
        forbidden: dict[str, Any] = {}
        for label, kind, state, retention in (
            ("upgrade_candidate", "upgrade_candidate", "candidate", "upgrade_candidate"),
            ("incoming_durable", "incoming", "durable", "incoming"),
            ("canonical_orphan", "canonical", "orphan", "canonical_orphan"),
        ):
            art_id = uuid.uuid4()
            ver_id = uuid.uuid4()
            payload = f"FORBIDDEN-{label}-".encode() + os.urandom(8)
            sha = hashlib.sha256(payload).hexdigest()
            outcome: dict[str, Any]
            try:
                async with engine.begin() as conn:
                    log.note("TX", f"BEGIN -- db3 {label}")
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_artifact
                            (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes,
                             document_type, retention_class, durable_at)
                            VALUES (:id,:pid,:wp,:kind,:state,:rel,:sha,:size,'xlsx',:rc,
                                    CASE WHEN :state2 = 'durable' THEN now() ELSE NULL END)""",
                        {
                            "id": art_id,
                            "pid": project_id,
                            "wp": wp_id,
                            "kind": kind,
                            "state": state,
                            "state2": state,
                            "rel": f".probe/{label}.bin",
                            "sha": sha,
                            "size": len(payload),
                            "rc": retention,
                        },
                    )
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_content_version
                            (id, wp_id, revision, projection_artifact_sha256, source)
                            VALUES (:id,:wp,:rev,:sha,'probe_forbidden')""",
                        {"id": ver_id, "wp": wp_id, "rev": 900 + len(forbidden), "sha": sha},
                    )
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_content_representation
                            (id, wp_id, content_version_id, entry_id, generation, document_type,
                             artifact_id, artifact_sha256, definition_bundle_id, definition_bundle_sha256, reason)
                            VALUES (:id,:wp,:ver,:entry,:gen,'xlsx',:art,:sha,:bid,:bsha,'content_commit')""",
                        {
                            "id": uuid.uuid4(),
                            "wp": wp_id,
                            "ver": ver_id,
                            "entry": entry_id,
                            "gen": 900 + len(forbidden),
                            "art": art_id,
                            "sha": sha,
                            "bid": bundle_id,
                            "bsha": bundle_sha,
                        },
                    )
                outcome = {"rejected": False, "note": "representation 被接受（不符合 design 约束）"}
            except Exception as exc:  # noqa: BLE001 - 期望被 trigger 拒绝
                orig = getattr(exc, "orig", None)
                outcome = {
                    "rejected": True,
                    "exc_type": type(exc).__name__,
                    "pgcode": getattr(orig, "sqlstate", None) or getattr(exc, "sqlstate", None),
                    "message": str(exc)[:240],
                }
                log.note("TX", f"ROLLBACK -- db3 {label}")
            forbidden[label] = {"artifact_kind": kind, "artifact_state": state, **outcome}

        rec.run(
            "db3",
            "representation 不得引用 candidate / incoming / orphan artifact（trigger 实测）",
            lambda: {
                "cases": forbidden,
                "all_rejected": all(v["rejected"] for v in forbidden.values()),
                "candidate_never_resolvable": forbidden["upgrade_candidate"]["rejected"],
                "incoming_never_published_or_current": forbidden["incoming_durable"]["rejected"],
            },
        )

        # ---------------- db4 orphan reconciliation ----------------
        async def _reconcile(conn: Any) -> dict[str, Any]:
            """磁盘 `.versions` 命名空间 ↔ DB 引用双向扫描；无引用即 orphan。"""
            referenced = {
                str(row["artifact_sha256"])
                for row in (
                    await _exec(
                        conn,
                        f"SELECT artifact_sha256 FROM {schema}.working_paper_content_representation",
                        kind="SELECT",
                    )
                ).mappings()
            }
            registered = {
                str(row["sha256"]): dict(row)
                for row in (
                    await _exec(
                        conn,
                        f"""SELECT id, sha256, state, relative_path FROM {schema}.working_paper_artifact
                            WHERE kind = 'canonical'""",
                        kind="SELECT",
                    )
                ).mappings()
            }
            disk: dict[str, str] = {}
            reps_root = versions_root / str(wp_id) / "representations" / entry_id
            for path in sorted(reps_root.rglob("*")) if reps_root.exists() else []:
                if path.is_file():
                    disk[_sha256_file(path)] = str(path.relative_to(work_root)).replace("\\", "/")

            marked_existing: list[str] = []
            registered_new: list[str] = []
            for sha, rel in disk.items():
                if sha in referenced:
                    continue
                row = registered.get(sha)
                if row is None:
                    new_id = uuid.uuid4()
                    await _exec(
                        conn,
                        f"""INSERT INTO {schema}.working_paper_artifact
                            (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes,
                             document_type, retention_class, orphaned_at)
                            VALUES (:id,:pid,:wp,'canonical','orphan',:rel,:sha,:size,'xlsx','canonical_orphan', now())""",
                        {
                            "id": new_id,
                            "pid": project_id,
                            "wp": wp_id,
                            "rel": rel,
                            "sha": sha,
                            "size": (work_root / rel).stat().st_size,
                        },
                    )
                    registered_new.append(sha)
                elif row["state"] != "orphan":
                    await _exec(
                        conn,
                        f"""UPDATE {schema}.working_paper_artifact
                            SET state='orphan', orphaned_at=now() WHERE id=:id""",
                        {"id": row["id"]},
                    )
                    marked_existing.append(sha)
            return {
                "disk_files": len(disk),
                "referenced_sha_count": len(referenced),
                "registered_new_orphans": registered_new,
                "marked_existing_as_orphan": marked_existing,
            }

        # 4b：先提交 artifact row（published），随后 pointer 事务 rollback ⇒ DB 侧有 row 无引用
        precommitted = _publish_bytes(b"PRECOMMITTED-ROW-ORPHAN-" + os.urandom(8), 3)
        precommitted_id = uuid.uuid4()
        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- db4b register artifact row first")
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_artifact
                    (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes,
                     document_type, retention_class, published_at)
                    VALUES (:id,:pid,:wp,'canonical','published',:rel,:sha,:size,'xlsx','canonical_orphan', now())""",
                {
                    "id": precommitted_id,
                    "pid": project_id,
                    "wp": wp_id,
                    "rel": precommitted["relative_path"],
                    "sha": precommitted["sha256"],
                    "size": precommitted["size_bytes"],
                },
            )
            log.note("TX", "COMMIT -- artifact row committed, pointer tx will fail")
        try:
            async with engine.begin() as conn:
                log.note("TX", "BEGIN -- db4b pointer tx (will fail)")
                ver = uuid.uuid4()
                await _exec(
                    conn,
                    f"""INSERT INTO {schema}.working_paper_content_version
                        (id, wp_id, revision, projection_artifact_sha256, source)
                        VALUES (:id,:wp,3,:sha,'probe_orphan')""",
                    {"id": ver, "wp": wp_id, "sha": precommitted["sha256"]},
                )
                raise _InjectedFailure("representation write failed")
        except _InjectedFailure:
            log.note("TX", "ROLLBACK -- db4b pointer tx")

        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- db4 reconciliation")
            reconcile_result = await _reconcile(conn)
            log.note("TX", "COMMIT -- reconciliation")

        async with engine.connect() as conn:
            orphan_rows = [
                dict(row)
                for row in (
                    await _exec(
                        conn,
                        f"""SELECT sha256, state, relative_path, orphaned_at
                            FROM {schema}.working_paper_artifact WHERE state='orphan' ORDER BY sha256""",
                        kind="SELECT",
                    )
                ).mappings()
            ]
            resolver_after_reconcile = await resolve(conn)

        rec.run(
            "db4",
            "reconciliation 标 orphan（磁盘无 DB row / DB row 无引用两种形态）",
            lambda: {
                "reconciliation": reconcile_result,
                "orphan_rows": [
                    {
                        "sha256": r["sha256"].strip(),
                        "state": r["state"],
                        "relative_path": r["relative_path"],
                        "orphaned_at_present": r["orphaned_at"] is not None,
                    }
                    for r in orphan_rows
                ],
                "orphan_count": len(orphan_rows),
                "precommitted_row_marked_orphan": precommitted["sha256"]
                in {r["sha256"].strip() for r in orphan_rows},
                "unregistered_disk_file_registered_as_orphan": bool(reconcile_result["registered_new_orphans"]),
                "resolver_after_reconcile": resolver_after_reconcile,
                "resolver_still_only_old_artifact": [r["artifact_sha256"] for r in resolver_after_reconcile]
                == [old_artifact["sha256"]],
            },
        )

        # ---------------- db5 RetentionPolicy / GC grace ----------------
        async def _gc(conn: Any, now: datetime, dry_run: bool) -> list[dict[str, Any]]:
            rows = [
                dict(row)
                for row in (
                    await _exec(
                        conn,
                        f"""SELECT id, sha256, relative_path, retention_class, orphaned_at
                            FROM {schema}.working_paper_artifact
                            WHERE state='orphan' ORDER BY sha256""",
                        kind="SELECT",
                    )
                ).mappings()
            ]
            decisions: list[dict[str, Any]] = []
            for row in rows:
                policy = RETENTION_POLICY["classes"].get(row["retention_class"])
                if policy is None:
                    decision, reason = "retain", "no_policy_retain_and_alert"
                elif policy["legal_hold"]:
                    decision, reason = "retain", "legal_hold"
                elif row["orphaned_at"] is None:
                    decision, reason = "retain", "orphaned_at_missing"
                elif (now - row["orphaned_at"]).total_seconds() < policy["grace_seconds"]:
                    decision, reason = "retain", "grace_not_elapsed"
                else:
                    refs = int(
                        (
                            await _exec(
                                conn,
                                f"""SELECT count(*) AS n FROM {schema}.working_paper_content_representation
                                    WHERE artifact_id = :id OR artifact_sha256 = :sha""",
                                {"id": row["id"], "sha": row["sha256"]},
                                kind="SELECT",
                            )
                        ).scalar_one()
                    )
                    if refs:
                        decision, reason = "retain", "reference_found_on_recheck"
                    else:
                        decision, reason = "delete", "grace_elapsed_and_unreferenced"
                deleted_file = None
                if decision == "delete" and not dry_run:
                    path = work_root / row["relative_path"]
                    deleted_file = path.exists()
                    path.unlink(missing_ok=True)
                    await _exec(
                        conn,
                        f"""UPDATE {schema}.working_paper_artifact
                            SET state='deleted', deleted_at=now() WHERE id=:id""",
                        {"id": row["id"]},
                    )
                await _exec(
                    conn,
                    f"""INSERT INTO {schema}.working_paper_artifact_gc_audit
                        (id, artifact_id, policy_version, dry_run, decision, reason)
                        VALUES (:id,:art,:pv,:dry,:dec,:rsn)""",
                    {
                        "id": uuid.uuid4(),
                        "art": row["id"],
                        "pv": RETENTION_POLICY["policy_version"],
                        "dry": dry_run,
                        "dec": decision,
                        "rsn": reason,
                    },
                )
                decisions.append(
                    {
                        "sha256": row["sha256"].strip(),
                        "retention_class": row["retention_class"],
                        "decision": decision,
                        "reason": reason,
                        "dry_run": dry_run,
                        "file_removed": deleted_file,
                        "relative_path": row["relative_path"],
                    }
                )
            return decisions

        now_ref = datetime.now(timezone.utc)
        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- db5 dry-run before grace")
            dry_before = await _gc(conn, now_ref, dry_run=True)
            log.note("TX", "COMMIT")
        files_exist_after_dry = {
            d["sha256"]: (work_root / d["relative_path"]).exists() for d in dry_before
        }

        # 构造 legal-hold orphan 与「二次确认重现引用」orphan
        legal_hold = _publish_bytes(b"LEGAL-HOLD-ORPHAN-" + os.urandom(8), 4)
        reappearing = _publish_bytes(b"REFERENCE-REAPPEARS-ORPHAN-" + os.urandom(8), 5)
        legal_id, reappear_id, reappear_ver = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- db5 seed legal-hold + reappearing-reference orphans")
            for art_id, meta, retention in (
                (legal_id, legal_hold, "legal_hold_canonical"),
                (reappear_id, reappearing, "canonical_orphan"),
            ):
                await _exec(
                    conn,
                    f"""INSERT INTO {schema}.working_paper_artifact
                        (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes,
                         document_type, retention_class, orphaned_at)
                        VALUES (:id,:pid,:wp,'canonical','orphan',:rel,:sha,:size,'xlsx',:rc,
                                now() - interval '10 days')""",
                    {
                        "id": art_id,
                        "pid": project_id,
                        "wp": wp_id,
                        "rel": meta["relative_path"],
                        "sha": meta["sha256"],
                        "size": meta["size_bytes"],
                        "rc": retention,
                    },
                )
            # 二次确认时引用重现：把 reappearing artifact 改回 published 并挂上 representation
            await _exec(
                conn,
                f"UPDATE {schema}.working_paper_artifact SET state='published', published_at=now() WHERE id=:id",
                {"id": reappear_id},
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_content_version
                    (id, wp_id, revision, projection_artifact_sha256, source)
                    VALUES (:id,:wp,50,:sha,'probe_reappear')""",
                {"id": reappear_ver, "wp": wp_id, "sha": reappearing["sha256"]},
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_content_representation
                    (id, wp_id, content_version_id, entry_id, generation, document_type,
                     artifact_id, artifact_sha256, definition_bundle_id, definition_bundle_sha256, reason)
                    VALUES (:id,:wp,:ver,:entry,50,'xlsx',:art,:sha,:bid,:bsha,'rematerialize')""",
                {
                    "id": uuid.uuid4(),
                    "wp": wp_id,
                    "ver": reappear_ver,
                    "entry": entry_id,
                    "art": reappear_id,
                    "sha": reappearing["sha256"],
                    "bid": bundle_id,
                    "bsha": bundle_sha,
                },
            )
            # 再标回 orphan（模拟 reconciliation 与引用重现的竞态）
            await _exec(
                conn,
                f"UPDATE {schema}.working_paper_artifact SET state='orphan', orphaned_at=now() - interval '10 days' WHERE id=:id",
                {"id": reappear_id},
            )
            # 让 db2/db4 的 orphan 越过 grace
            await _exec(
                conn,
                f"""UPDATE {schema}.working_paper_artifact
                    SET orphaned_at = now() - interval '10 days'
                    WHERE state='orphan' AND retention_class='canonical_orphan'""",
            )
            log.note("TX", "COMMIT")

        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- db5 dry-run after grace")
            dry_after = await _gc(conn, datetime.now(timezone.utc), dry_run=True)
            log.note("TX", "COMMIT")
        files_exist_after_dry_after = {
            d["sha256"]: (work_root / d["relative_path"]).exists() for d in dry_after
        }

        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- db5 apply")
            applied = await _gc(conn, datetime.now(timezone.utc), dry_run=False)
            log.note("TX", "COMMIT")

        files_exist_after_apply = {d["sha256"]: (work_root / d["relative_path"]).exists() for d in applied}
        async with engine.connect() as conn:
            audit_rows = [
                dict(row)
                for row in (
                    await _exec(
                        conn,
                        f"""SELECT dry_run, decision, reason, count(*) AS n
                            FROM {schema}.working_paper_artifact_gc_audit
                            GROUP BY 1,2,3 ORDER BY 1,2,3""",
                        kind="SELECT",
                    )
                ).mappings()
            ]
            resolver_after_gc = await resolve(conn)

        rec.run(
            "db5",
            "RetentionPolicy/GC：grace 前 retain、grace 后二次确认无引用才删、引用重现/legal hold 保留",
            lambda: {
                "policy": RETENTION_POLICY,
                "dry_run_before_grace": dry_before,
                "dry_run_before_grace_all_retained": all(d["decision"] == "retain" for d in dry_before),
                "dry_run_before_grace_reason_set": sorted({d["reason"] for d in dry_before}),
                "files_present_after_dry_run_before_grace": files_exist_after_dry,
                "dry_run_after_grace": dry_after,
                "files_present_after_dry_run_after_grace": files_exist_after_dry_after,
                "dry_run_never_deletes": all(files_exist_after_dry_after.values()),
                "applied": applied,
                "files_present_after_apply": files_exist_after_apply,
                "legal_hold_sha256": legal_hold["sha256"],
                "legal_hold_retained": next(
                    (d["decision"] for d in applied if d["sha256"] == legal_hold["sha256"]), None
                )
                == "retain",
                "legal_hold_file_present": files_exist_after_apply.get(legal_hold["sha256"]),
                "reappearing_sha256": reappearing["sha256"],
                "reappearing_retained_on_recheck": next(
                    (d["reason"] for d in applied if d["sha256"] == reappearing["sha256"]), None
                )
                == "reference_found_on_recheck",
                "reappearing_file_present": files_exist_after_apply.get(reappearing["sha256"]),
                "deleted_sha256": sorted(d["sha256"] for d in applied if d["decision"] == "delete"),
                "deleted_files_gone": all(
                    files_exist_after_apply[d["sha256"]] is False for d in applied if d["decision"] == "delete"
                ),
                "audit_rows": [
                    {"dry_run": r["dry_run"], "decision": r["decision"], "reason": r["reason"], "n": int(r["n"])}
                    for r in audit_rows
                ],
                "resolver_after_gc": resolver_after_gc,
                "resolver_unaffected_by_gc": [r["artifact_sha256"] for r in resolver_after_gc]
                == [old_artifact["sha256"]],
            },
        )

        # ---------------- db6 pointer 指向缺失 artifact 物理可能 ----------------
        ghost_wp = uuid.uuid4()
        ghost_ids = {"artifact": uuid.uuid4(), "version": uuid.uuid4(), "representation": uuid.uuid4()}
        ghost_rel = f"storage/{project_id}/workpapers/.versions/{ghost_wp}/representations/{entry_id}/000000001-deadbeefdead.xlsx"
        async with engine.begin() as conn:
            log.note("TX", "BEGIN -- db6 commit pointer without publishing file")
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_artifact
                    (id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes,
                     document_type, retention_class, published_at)
                    VALUES (:id,:pid,:wp,'canonical','published',:rel,:sha,:size,'xlsx','canonical_orphan', now())""",
                {
                    "id": ghost_ids["artifact"],
                    "pid": project_id,
                    "wp": ghost_wp,
                    "rel": ghost_rel,
                    "sha": hashlib.sha256(b"never-written-to-disk").hexdigest(),
                    "size": 12345,
                },
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_content_version
                    (id, wp_id, revision, projection_artifact_sha256, source)
                    VALUES (:id,:wp,1,:sha,'probe_ghost')""",
                {
                    "id": ghost_ids["version"],
                    "wp": ghost_wp,
                    "sha": hashlib.sha256(b"never-written-to-disk").hexdigest(),
                },
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_content_representation
                    (id, wp_id, content_version_id, entry_id, generation, document_type,
                     artifact_id, artifact_sha256, definition_bundle_id, definition_bundle_sha256, reason)
                    VALUES (:id,:wp,:ver,:entry,1,'xlsx',:art,:sha,:bid,:bsha,'content_commit')""",
                {
                    "id": ghost_ids["representation"],
                    "wp": ghost_wp,
                    "ver": ghost_ids["version"],
                    "entry": entry_id,
                    "art": ghost_ids["artifact"],
                    "sha": hashlib.sha256(b"never-written-to-disk").hexdigest(),
                    "bid": bundle_id,
                    "bsha": bundle_sha,
                },
            )
            await _exec(
                conn,
                f"""INSERT INTO {schema}.working_paper_sync_entry_state
                    (wp_id, entry_id, current_representation_id, representation_generation)
                    VALUES (:wp,:entry,:rep,1)""",
                {"wp": ghost_wp, "entry": entry_id, "rep": ghost_ids["representation"]},
            )
            log.note("TX", "COMMIT -- ghost pointer committed")

        async with engine.connect() as conn:
            ghost_resolver = [
                dict(row)
                for row in (
                    await _exec(
                        conn, resolver_sql, {"wp": ghost_wp, "entry": entry_id}, kind="SELECT"
                    )
                ).mappings()
            ]

        rec.run(
            "db6",
            "DB commit 不会创造文件：pointer 指向缺失 artifact 在物理上可能 ⇒ 必须 publish-then-commit",
            lambda: {
                "committed_relative_path": ghost_rel,
                "file_exists_on_disk": (work_root / ghost_rel).exists(),
                "resolver_returns_row": len(ghost_resolver),
                "resolver_row_path_missing_on_disk": bool(ghost_resolver)
                and not (work_root / ghost_resolver[0]["relative_path"]).exists(),
                "half_success_state_is_physically_possible": True,
                "protocol_consequence": "artifact 必须先 durable/publish 且校验通过，DB 短事务才可发布 pointer；"
                "顺序反了就会产生 pointer 指向缺失 artifact 的半成功态",
            },
        )

        return {
            **db_meta,
            "baseline": baseline,
            "sql_log": log.entries,
            "sql_log_total": len(log.entries),
        }
    finally:
        try:
            async with engine.begin() as conn:
                log.note("DDL", f"DROP SCHEMA {schema} CASCADE")
                await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            async with engine.connect() as conn:
                left = (
                    await conn.execute(
                        sa.text("SELECT count(*) FROM information_schema.schemata WHERE schema_name = :s"),
                        {"s": schema},
                    )
                ).scalar_one()
            print(f"  [--] scratch schema 已清理: {schema} (remaining={left})")
        finally:
            await engine.dispose()


class _InjectedFailure(RuntimeError):
    """显式注入的 DB 事务失败（模拟 outbox/representation 写入失败）。"""


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Task 7 staged artifact / DB rollback / orphan GC 边界探针")
    parser.add_argument(
        "mode",
        choices=["fs", "db", "all", "_child-hold", "_child-slow-write"],
    )
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--keep-workdir", action="store_true")
    # 子进程参数
    parser.add_argument("--path")
    parser.add_argument("--hold-mode", dest="hold_mode", default="plain")
    parser.add_argument("--ready")
    parser.add_argument("--hold-seconds", type=float, default=20.0)
    parser.add_argument("--total", type=int)
    parser.add_argument("--chunk", type=int)
    parser.add_argument("--ready-after", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.05)
    args = parser.parse_args()

    if args.mode == "_child-hold":
        return _child_hold(args.path, args.hold_mode, args.ready, args.hold_seconds)
    if args.mode == "_child-slow-write":
        return _child_slow_write(args.path, args.total, args.chunk, args.ready, args.ready_after, args.sleep)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    work_root = REPO_ROOT / f"tmp_task7_probe_{run_id}"
    work_root.mkdir(parents=True, exist_ok=True)
    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    rec = _Recorder()
    print(f"work_root = {work_root}")
    fs_meta: dict[str, Any] = {}
    db_meta: dict[str, Any] = {}
    try:
        if args.mode in ("fs", "all"):
            print("== FS 阶段 ==")
            fs_meta = _fs_phase(work_root, rec)
        if args.mode in ("db", "all"):
            print("== DB 阶段 ==")
            import asyncio

            if not fs_meta:
                raise ProbeHarnessError("db 阶段依赖 fs 阶段的布局与 published artifact；请用 `all`")
            try:
                # 🔴 一次 asyncio.run 完成全部 DB 快照：多次 run 会拿到已绑定旧 event loop 的连接
                db_meta = asyncio.run(_db_phase(work_root, rec, fs_meta))
            except Exception as exc:  # noqa: BLE001 - DB 阶段 harness 异常必须落 ERROR 态而不是静默崩掉
                rec.cases["db_phase"] = {
                    "case_id": "db_phase",
                    "title": "DB 阶段 harness",
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(limit=20),
                }
                rec.errors.append(
                    {"case_id": "db_phase", "error_type": type(exc).__name__, "error_message": str(exc)}
                )
                print(f"  [ERR] db_phase  {type(exc).__name__}: {exc}")
    finally:
        run_meta = {
            "probe": "backend/scripts/diagnose/probe_task7_staged_artifact_boundaries.py",
            "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
            "task": 7,
            "run_id": run_id,
            "mode": args.mode,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "host": {
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "repo_drive": REPO_ROOT.drive.upper(),
                "temp_drive": Path(tempfile.gettempdir()).drive.upper(),
            },
            "probe_status": "error" if rec.errors else "ok",
            "harness_errors": rec.errors,
            "case_ids": sorted(rec.cases),
            "case_status": {cid: rec.cases[cid]["status"] for cid in sorted(rec.cases)},
            "fs_meta": fs_meta,
            "db_meta": {k: v for k, v in db_meta.items() if k != "sql_log"},
        }
        (evidence_dir / "run_meta.json").write_text(
            json.dumps(run_meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        (evidence_dir / "fs_observations.json").write_text(
            json.dumps(
                {cid: rec.cases[cid] for cid in sorted(rec.cases) if cid.startswith("fs")},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        (evidence_dir / "db_observations.json").write_text(
            json.dumps(
                {
                    "meta": {k: v for k, v in db_meta.items() if k != "sql_log"},
                    "cases": {cid: rec.cases[cid] for cid in sorted(rec.cases) if cid.startswith("db")},
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        (evidence_dir / "db_sql_log.json").write_text(
            json.dumps(
                {"schema": db_meta.get("schema"), "statements": db_meta.get("sql_log", [])},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        if not args.keep_workdir:
            shutil.rmtree(work_root, ignore_errors=True)
            print(f"work_root 已清理: {work_root} (exists={work_root.exists()})")

    print()
    print(f"probe_status = {run_meta['probe_status']}  cases = {len(rec.cases)}  errors = {len(rec.errors)}")
    print(f"evidence → {evidence_dir}")
    return 1 if rec.errors else 0


if __name__ == "__main__":
    sys.exit(main())
