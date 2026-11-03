"""底稿两阶段生成的同卷 staging、模板指纹与文件提升。

本模块只做文件系统工作，不读写数据库。所有路径由 UUID 构造并在 ``wp_storage`` 根内复核；
调用方把结果 manifest 持久化后，Phase B 才创建可见底稿行。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services import wp_template_init_service as _init
from app.services.wp_generate_file import (
    GeneratedWorkpaperFile,
    WorkpaperFileJob,
    materialize_workpaper_files,
)


@dataclass(frozen=True)
class StagingItem:
    item_id: UUID
    wp_id: UUID
    wp_code: str
    wp_name: str
    library_file: str | None = None
    expected_source_fingerprint: str | None = None
    expected_file_sha256: str | None = None
    expected_from_template: bool = False
    existing_staging_path: str | None = None


@dataclass(frozen=True)
class SourceSnapshot:
    item_id: UUID
    source: dict[str, Any]
    fingerprint: str


@dataclass(frozen=True)
class PromotedFile:
    path: Path
    moved: bool


@dataclass(frozen=True)
class MaterializedItem:
    item_id: UUID
    staging_path: str
    file_sha256: str
    from_template: bool


def _inside(root: Path, candidate: Path) -> Path:
    root_r = root.resolve()
    candidate_r = candidate.resolve()
    if not candidate_r.is_relative_to(root_r):
        raise ValueError(f"生成文件路径越界：{candidate_r}")
    return candidate_r


def staging_root(project_id: UUID, operation_id: UUID, *, create: bool = True) -> Path:
    storage = _init.STORAGE_DIR.resolve()
    root = _inside(storage, storage / str(project_id) / ".generation" / str(operation_id))
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def staging_base(project_id: UUID, operation_id: UUID, wp_id: UUID) -> Path:
    root = staging_root(project_id, operation_id)
    return _inside(root, root / str(wp_id))


def final_path(project_id: UUID, wp_id: UUID, suffix: str) -> Path:
    storage = _init.STORAGE_DIR.resolve()
    base = _init.get_workpaper_storage_path(project_id, wp_id)
    return _inside(storage, base.with_suffix(suffix))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_paths(wp_code: str, scenario: str, library_file: str | None) -> list[Path]:
    if library_file:
        from app.services.wp_export.wp_file_resolver import resolve_wp_file

        resolved = resolve_wp_file(library_file, wp_code=None, allow_template_fallback=False).path
        if resolved is not None:
            return [resolved.resolve()]

    main = _init.find_template_file_any(wp_code)
    if main is None:
        return []
    main = main.resolve()
    if main.suffix.lower() != ".xlsx":
        return [main]
    all_files = [p.resolve() for p in _init.find_all_template_files(wp_code)]
    others = [p for p in all_files if p != main and p.suffix.lower() == ".xlsx"]
    return [main, *_init._filter_files_by_scenario(others, scenario)]


def source_snapshot(wp_code: str, scenario: str, library_file: str | None = None) -> tuple[dict[str, Any], str]:
    files = []
    for path in _source_paths(wp_code, scenario, library_file):
        stat = path.stat()
        files.append({
            "path": str(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": file_sha256(path),
        })
    source = {"wp_code": wp_code, "scenario": scenario, "library_file": library_file, "files": files}
    raw = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return source, hashlib.sha256(raw).hexdigest()


def snapshot_sources(items: list[StagingItem], scenario: str) -> list[SourceSnapshot]:
    """任何 staging 写入前冻结全部模板来源；中途失败时还没有生成文件。"""
    result = []
    for item in items:
        source, fingerprint = source_snapshot(item.wp_code, scenario, item.library_file)
        result.append(SourceSnapshot(item.item_id, source, fingerprint))
    return result


def _existing_staging(item: StagingItem, root: Path) -> MaterializedItem | None:
    if not item.existing_staging_path or not item.expected_file_sha256:
        return None
    path = _inside(root, Path(item.existing_staging_path))
    if not path.is_file() or file_sha256(path) != item.expected_file_sha256:
        return None
    return MaterializedItem(item.item_id, str(path), item.expected_file_sha256, item.expected_from_template)


def materialize_atomic(
    project_id: UUID,
    operation_id: UUID,
    items: list[StagingItem],
    *,
    scenario: str,
    has_foreign_currency: bool,
) -> list[MaterializedItem]:
    """模板集整批物化；任一失败清理本 operation staging 后抛出。"""
    root = staging_root(project_id, operation_id)
    reused: dict[UUID, MaterializedItem] = {}
    jobs: list[WorkpaperFileJob] = []
    try:
        for item in items:
            hit = _existing_staging(item, root)
            if hit:
                reused[item.item_id] = hit
                continue
            if item.expected_source_fingerprint:
                _, current = source_snapshot(item.wp_code, scenario, item.library_file)
                if current != item.expected_source_fingerprint:
                    raise RuntimeError(f"模板来源已变化：{item.wp_code}")
            jobs.append(WorkpaperFileJob(
                item.wp_id, item.wp_code, item.wp_name, item.library_file,
                staging_base(project_id, operation_id, item.wp_id),
            ))
        generated = materialize_workpaper_files(
            project_id, jobs, scenario=scenario, has_foreign_currency=has_foreign_currency,
        )
        generated_by_wp = {job.wp_id: output for job, output in zip(jobs, generated)}
        out: list[MaterializedItem] = []
        for item in items:
            if item.item_id in reused:
                out.append(reused[item.item_id])
                continue
            output = generated_by_wp[item.wp_id]
            if item.expected_source_fingerprint:
                _, current = source_snapshot(item.wp_code, scenario, item.library_file)
                if current != item.expected_source_fingerprint:
                    raise RuntimeError(f"模板物化期间来源发生变化：{item.wp_code}")
            out.append(MaterializedItem(item.item_id, str(output.path), file_sha256(output.path), output.from_template))
        return out
    except BaseException:
        cleanup_staging(project_id, operation_id)
        raise


def _public_materialize_error(error: BaseException) -> str:
    text = str(error).strip()
    if text.startswith(("模板来源已变化", "模板物化期间来源发生变化")):
        return text[:300]
    return "底稿文件准备失败，请重试；若持续失败请联系管理员"


def materialize_per_item(
    project_id: UUID,
    operation_id: UUID,
    items: list[StagingItem],
    *,
    scenario: str,
    has_foreign_currency: bool,
) -> tuple[list[MaterializedItem], list[tuple[UUID, str]]]:
    """按编码逐项物化；单项失败如实返回，不删除其他成功 staging。"""
    done: list[MaterializedItem] = []
    failed: list[tuple[UUID, str]] = []
    root = staging_root(project_id, operation_id)
    for item in items:
        hit = _existing_staging(item, root)
        if hit:
            done.append(hit)
            continue
        output: GeneratedWorkpaperFile | None = None
        try:
            if item.expected_source_fingerprint:
                _, current = source_snapshot(item.wp_code, scenario, item.library_file)
                if current != item.expected_source_fingerprint:
                    raise RuntimeError("模板来源已变化")
            output = materialize_workpaper_files(
                project_id,
                [WorkpaperFileJob(
                    item.wp_id, item.wp_code, item.wp_name, item.library_file,
                    staging_base(project_id, operation_id, item.wp_id),
                )],
                scenario=scenario,
                has_foreign_currency=has_foreign_currency,
            )[0]
            if item.expected_source_fingerprint:
                _, current = source_snapshot(item.wp_code, scenario, item.library_file)
                if current != item.expected_source_fingerprint:
                    raise RuntimeError("模板物化期间来源发生变化")
            done.append(MaterializedItem(item.item_id, str(output.path), file_sha256(output.path), output.from_template))
        except Exception as exc:  # 单项失败策略
            if output is not None:
                output.path.unlink(missing_ok=True)
            cleanup_staging_item(project_id, operation_id, item.wp_id)
            failed.append((item.item_id, _public_materialize_error(exc)))
    return done, failed


def promote_staging(project_id: UUID, wp_id: UUID, staging_path: str, expected_sha256: str) -> PromotedFile:
    root = _init.STORAGE_DIR.resolve()
    source = _inside(root, Path(staging_path))
    target = final_path(project_id, wp_id, source.suffix)
    if target.is_file():
        if file_sha256(target) != expected_sha256:
            raise RuntimeError(f"正式文件已存在且摘要冲突：{wp_id}")
        source.unlink(missing_ok=True)
        return PromotedFile(target, False)
    if not source.is_file() or file_sha256(source) != expected_sha256:
        raise RuntimeError(f"staging 文件缺失或摘要不符：{wp_id}")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    return PromotedFile(target, True)


def cleanup_staging(project_id: UUID, operation_id: UUID) -> None:
    root = staging_root(project_id, operation_id, create=False)
    if root.exists():
        shutil.rmtree(root)
    generation_dir = root.parent
    try:
        generation_dir.rmdir()
    except OSError:
        pass


def discard_staging_file(project_id: UUID, operation_id: UUID, staging_path: str | None) -> None:
    if not staging_path:
        return
    root = staging_root(project_id, operation_id, create=False)
    path = _inside(root, Path(staging_path))
    path.unlink(missing_ok=True)


def cleanup_staging_item(project_id: UUID, operation_id: UUID, wp_id: UUID) -> None:
    """清理某一明细可能在抛错前留下、尚未来得及返回 manifest 的半成品。"""
    root = staging_root(project_id, operation_id, create=False)
    if not root.exists():
        return
    prefix = str(wp_id)
    for path in root.iterdir():
        if path.is_file() and (path.name == prefix or path.stem == prefix):
            path.unlink(missing_ok=True)


def validated_staging_file(project_id: UUID, operation_id: UUID, raw_path: str, expected_sha256: str) -> Path:
    root = staging_root(project_id, operation_id, create=False)
    path = _inside(root, Path(raw_path))
    if not path.is_file() or file_sha256(path) != expected_sha256:
        raise RuntimeError("staging 文件缺失或摘要不符")
    return path
