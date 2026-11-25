"""生成 Sheet → published sync entry 的显式绑定清单。

Usage from repository root::

    python backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py --apply
    python backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py --check

本生成器只把当前 manifest 的 source-backed 事实投影为待审核 binding；它不会在运行时
读取模板目录、按 sheet 名猜父级编码，也不会把 `xlsx-sheet/*` 伪造进 manifest。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "backend" / "data"
MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY = DATA / "workpaper_sync_entry_overlay.json"
ADJUDICATION = DATA / "workpaper_sync_entry_wp_code_adjudication.json"
#: 人工审核记录。**只有**这里列出的 entry 才允许晋级到 migrated / ready / draining /
#: retired（spec design §3.2 第 1 步的 "reviewed overlay"）。
#:
#: 🔴 为什么不复用 `workpaper_sync_entry_overlay.json`：那是**组件级默认值**文件，
#: 180 条 entry 共用（改一项会同时翻转全部 GtOnlyOfficeSheet entry 的 capability）。
#: 「审核某一条 binding 可以迁移」与「改组件默认值」是两件事，不能混在一个文件里。
#: 人工审核记录路径。**可被 `GT_SHEET_REVIEWED_IN` 覆盖** —— 判据要能构造
#: 「有记录 / 无记录 / 错记录」三种输入，而真实审核记录是仓库状态、不该被测试改。
REVIEWED = Path(
    os.environ.get("GT_SHEET_REVIEWED_IN")
    or str(DATA / "workpaper_sync_sheet_open_reviewed_bindings.json")
)
#: 输出路径。**可被 `GT_SHEET_BINDINGS_OUT` 覆盖** —— 变异套件用它把生成结果写到
#: 沙箱目录，从而完全不碰已跟踪的真实产物（否则 `_tracked_write_guard` 会报警，
#: 且进程被打断时可能留下变异态产物 —— 本仓踩过这个坑）。
OUTPUT = Path(
    os.environ.get("GT_SHEET_BINDINGS_OUT")
    or str(DATA / "workpaper_sync_sheet_open_bindings.json")
)
SCHEMA_VERSION = "sheet-open-binding:v1"
STATUSES = {"pending", "ready", "migrated", "draining", "retired", "out_of_scope"}
MAPPING_KINDS = {"exact", "provider", "whole_workbook", "ambiguous", "out_of_scope"}

#: reviewed 文件允许的 schema 与 decision 封闭集。
#:
#: 🔴 为什么 `pending` / `out_of_scope` 不在 decision 里：它们是生成器的**默认**结论，
#: 不是人工裁决。允许人工「裁决成 pending」等于允许把审核撤回 —— 撤回应该删记录，
#: 而不是留一条 decision=pending 的记录（那样无法区分「没审过」与「审过但决定不迁」）。
REVIEWED_SCHEMA = "sheet-open-reviewed-binding:v1"
REVIEWED_DECISIONS = {"ready", "migrated", "draining", "retired"}

#: `pending` 的**封闭**原因集（spec 1.4）。
#:
#: 🔴 为什么必须封闭：`reason` 是前端与运维唯一的归因线索。开放字符串会让「新加一条
#: 未登记原因」静默通过 —— 用户看到一句没人写过的中文、监控按前缀分组时落进「其他」，
#: 而没人知道该找谁。封闭域 + 生成器断言 = 加原因必须同时改这里（一次显式决策）。
PENDING_REASONS = {
    # 文档类型不适用本迁移（custom / Word / single_onlyoffice）
    "document_type_out_of_scope",
    # 整册入口：需人工审核 target scope 后才可晋级
    "whole_workbook_target_requires_reviewed_binding",
    # exact 候选：sheet 名与 wp_code 都是字面量，但仍需确认 published artifact 里真有它
    "exact_candidate_requires_published_artifact_review",
    # provider 候选：sheet 名是运行时表达式，必须由 provider 声明 target sheet
    "runtime_sheet_name_requires_provider_binding",
    # 多义：同一 wp_code 命中多张 sheet，不得猜
    "ambiguous_sheet_target",
    # 没有声明任何 sheet 目标
    "sheet_target_not_declared",
    # manifest / overlay / adjudication 源 digest 在生成后变过
    "source_digest_stale",
    # entry 不在 manifest（binding 引用了已删除 entry）
    "manifest_entry_missing",
}

#: provider binding 的 resolver identity 前缀。
#:
#: 🔴 为什么需要**稳定** identity：provider 的 `sheet_name` 是运行时表达式，解析时要由
#: provider 自己给出 target sheet。若 identity 按 entry 名或行号临时算，manifest 一重排
#: 全部 provider binding 的 `binding_id` 就变 ⇒ 已审核的 binding 集体失效、需要重审。
#: 用 `wp_code_patterns` + `sheet_expressions` 的规范化摘要，与 manifest 顺序无关。
PROVIDER_RESOLVER_PREFIX = "provider:"


def _display_path(path: Path) -> str:
    """仓库内的路径记相对值（可读、可在 review 里复查），仓库外记绝对值。

    🔴 不许 `relative_to(REPO)` 直接崩：判据会用 `GT_SHEET_REVIEWED_IN` 指向 tmp_path，
    而不是每个调用点都保证「一定在仓库里」。
    """
    try:
        return str(path.relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def digest_bytes(raw: bytes) -> str:
    """对**内容**算 sha256（行尾归一化为 LF）。

    🔴 为什么必须归一化：本仓 `core.autocrlf=true`，同一份文件在主工作区是 LF、
    在干净检出（CI / 新 clone / 临时 worktree）是 CRLF —— 逐字节 sha256 会因此不同，
    后果是**干净检出上 `--check` 恒红**（实测：`manifest_digest` 1401511B/LF vs
    1438333B/CRLF，JSON 解析后逐条相等、`entries differ: 0`，但 digest 不同 ⇒
    生成物被判 stale ⇒ task 5.6 的 clean checkout 总验必挂）。

    行尾是**检出属性**而不是内容，不该进内容摘要。归一化只碰 `\r\n` → `\n`，
    不动其它字节（BOM / 缩进 / 顺序都仍参与摘要）。
    """
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def read_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), digest_bytes(raw)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def source_digest(path: Path) -> str | None:
    return digest_bytes(path.read_bytes()) if path.is_file() else None


def mount_text(entry: dict[str, Any]) -> str:
    return canonical_json(entry.get("mounts") or [])


def has_whole_workbook_marker(entry: dict[str, Any]) -> bool:
    text = mount_text(entry).lower()
    return any(marker in text for marker in ("whole-workbook", "whole_workbook", "wholeworkbook"))


def load_reviewed() -> tuple[dict[str, dict[str, Any]], str | None]:
    """读人工审核记录。

    返回 `({entry_id: review}, digest)`。文件不存在 ⇒ `({}, None)`（这是**合法**状态：
    首版交付本就没有任何审核记录，生成物应保持全 pending —— spec 1.4）。

    🔴 每条 review 都在这里现场校验，不留给下游：
      · `entry_id` / `effective_entry_id` 必填且非空
      · `decision` 必须在 `REVIEWED_DECISIONS` 内（`pending` 不是可裁决值）
      · 同一 `entry_id` 不许重复（重复时后者覆盖前者会让审核静默失效）
    """
    if not REVIEWED.exists():
        return {}, None
    payload, _ = read_json(REVIEWED)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{REVIEWED.name} 顶层必须是对象")
    schema = str(payload.get("schema_version") or "").strip()
    if schema != REVIEWED_SCHEMA:
        raise RuntimeError(
            f"{REVIEWED.name} 的 schema_version={schema!r} 不是 {REVIEWED_SCHEMA!r}"
        )
    reviews = payload.get("reviews")
    if not isinstance(reviews, list):
        raise RuntimeError(f"{REVIEWED.name} 缺 reviews 数组")
    by_entry: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(reviews):
        if not isinstance(item, dict):
            raise RuntimeError(f"{REVIEWED.name} reviews[{i}] 不是对象")
        entry_id = str(item.get("entry_id") or "").strip()
        effective_id = str(item.get("effective_entry_id") or "").strip()
        decision = str(item.get("decision") or "").strip()
        if not entry_id or not effective_id:
            raise RuntimeError(f"{REVIEWED.name} reviews[{i}] 缺 entry_id / effective_entry_id")
        if decision not in REVIEWED_DECISIONS:
            raise RuntimeError(
                f"{REVIEWED.name} reviews[{i}] 的 decision={decision!r} 不在 "
                f"{sorted(REVIEWED_DECISIONS)} 内"
            )
        if entry_id in by_entry:
            raise RuntimeError(f"{REVIEWED.name} 里 entry_id={entry_id!r} 重复出现")

        # project_ids(可选)：把审核限定到指定项目。缺省 = 全局生效（与旧记录兼容）。
        # 写空数组等于「哪儿都不生效」—— 无意义声明，直接拒，避免静默失效。
        pids = item.get("project_ids")
        if pids is not None:
            if not isinstance(pids, list) or not pids:
                raise RuntimeError(
                    f"{REVIEWED.name} reviews[{i}] 的 project_ids 必须是非空数组"
                )
            for raw in pids:
                s = str(raw or "").strip()
                if not s:
                    raise RuntimeError(f"{REVIEWED.name} reviews[{i}] 的 project_ids 含空值")
                try:
                    uuid.UUID(s)
                except ValueError as exc:
                    raise RuntimeError(
                        f"{REVIEWED.name} reviews[{i}] 的 project_ids 值 {s!r} 不是 UUID"
                    ) from exc

        by_entry[entry_id] = item
    return by_entry, source_digest(REVIEWED)


def binding_for(
    entry: dict[str, Any],
    *,
    input_digest: str,
    reviewed: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entry_id = str(entry.get("entry_id") or "").strip()
    effective_id = str(entry.get("effective_entry_id") or entry_id).strip()
    document_type = str(entry.get("document_type") or "").strip()
    wp_match = entry.get("wp_match") or {}
    wp_patterns = [str(x).strip() for x in (wp_match.get("wp_code_patterns") or []) if str(x).strip()]
    sheet_literals = [str(x).strip() for x in (wp_match.get("sheet_literals") or []) if str(x).strip()]
    sheet_expressions = [str(x).strip() for x in (wp_match.get("sheet_expressions") or []) if str(x).strip()]
    source_host = str(wp_match.get("source_host") or entry.get("host_path") or "").strip() or None

    if document_type != "xlsx":
        kind = "out_of_scope"
        status = "out_of_scope"
        reason = "document_type_out_of_scope"
        scope = "out_of_scope"
    elif has_whole_workbook_marker(entry):
        kind = "whole_workbook"
        status = "pending"
        reason = "whole_workbook_target_requires_reviewed_binding"
        scope = "whole_workbook"
    elif len(wp_patterns) > 1:
        # 🔴 多 wp_code 必须**先于** exact / provider 判（spec 1.4）：一个 entry 声明多个
        # wp_code 时，一个 sheet 请求可能命中多张表，任何「挑第一个」都是猜。放在 provider
        # 之后就永远进不来（`wp_patterns` 非空 ⇒ provider 分支先命中）—— 实测踩过。
        kind = "ambiguous"
        status = "pending"
        reason = "ambiguous_sheet_target"
        scope = "single_sheet"
    elif len(sheet_literals) == 1 and len(wp_patterns) == 1:
        kind = "exact"
        status = "pending"
        reason = "exact_candidate_requires_published_artifact_review"
        scope = "single_sheet"
    elif sheet_expressions or wp_patterns:
        kind = "provider"
        status = "pending"
        reason = "runtime_sheet_name_requires_provider_binding"
        scope = "single_sheet"
    else:
        kind = "ambiguous"
        status = "pending"
        reason = "sheet_target_not_declared"
        scope = "single_sheet"

    row: dict[str, Any] = {
        "entry_id": entry_id,
        "effective_entry_id": effective_id,
        "source_wp_code": wp_patterns[0] if len(wp_patterns) == 1 else None,
        "document_scope": scope,
        "target_sheet": sheet_literals[0] if len(sheet_literals) == 1 else None,
        "sheet_key": sheet_literals[0] if len(sheet_literals) == 1 else None,
        "mapping_kind": kind,
        "status": status,
        "reason": reason,
        "manifest_entry_digest": digest_bytes(canonical_json(entry).encode("utf-8")),
        "source_refs": [source_host] if source_host else [],
        "owner": None,
        "input_digest": input_digest,
        "independent_entry": bool(entry.get("independent_entry", False)),
        "document_type": document_type,
        "capability": entry.get("capability"),
        "wp_code_patterns": wp_patterns,
        "sheet_expressions": sheet_expressions,
        "sheet_literals": sheet_literals,
        # provider 候选的稳定 resolver identity（spec 1.3）。与 manifest 顺序无关：
        # 只由「声明了哪些 wp_code / sheet 表达式」决定，重排 manifest 不改它。
        "resolver_identity": (
            PROVIDER_RESOLVER_PREFIX
            + digest_bytes(
                canonical_json({
                    "wp_code_patterns": sorted(wp_patterns),
                    "sheet_expressions": sorted(sheet_expressions),
                }).encode("utf-8")
            )[:16]
            if kind == "provider"
            else None
        ),
    }
    # ── 人工审核覆盖（spec design §3.2 的 reviewed overlay）─────────────────
    #
    # 🔴 只有 reviewed 文件能给出 migrated / ready / draining / retired。
    # 没有记录的 entry **保持上面的默认结论**（pending / out_of_scope），一个字段都不动 ——
    # 这是 spec 1.4 / 首版守卫 `test_projection_does_not_claim_migration_without_reviewed_binding`
    # 的语义。所以「有 reviewed」与「无 reviewed」两条路径必须分别可证。
    review = (reviewed or {}).get(entry_id)
    if review is not None:
        decision = str(review.get("decision") or "").strip()
        if decision not in REVIEWED_DECISIONS:
            # loader 已校验过；这里再挡一次是因为 binding_for 也能被单独调用（fixture 用）。
            raise RuntimeError(
                f"entry {entry_id!r} 的 reviewed decision={decision!r} 不在 "
                f"{sorted(REVIEWED_DECISIONS)} 内"
            )
        # `out_of_scope` 的文档类型不许被人工晋级：那不是「还没审」，是「不适用本迁移」。
        # 允许晋级等于让 Word / custom 文档强行进 room 协议（Requirement 2.7 禁止）。
        if kind == "out_of_scope":
            raise RuntimeError(
                f"entry {entry_id!r} 的 document_type={document_type!r} 不适用本迁移，"
                f"不得审核为 {decision!r}"
            )
        row["status"] = decision
        row["reason"] = None
        row["owner"] = str(review.get("reviewed_by") or "").strip() or None
        row["reviewed"] = {
            "decision": decision,
            "reviewed_by": review.get("reviewed_by"),
            "reviewed_at": review.get("reviewed_at"),
            "decision_basis": review.get("decision_basis"),
            "published_artifact_evidence": review.get("published_artifact_evidence"),
            "project_ids": review.get("project_ids"),
        }
    else:
        row["reviewed"] = None

    binding_material = {k: v for k, v in row.items() if k != "binding_id"}
    row["binding_id"] = "sha256:" + digest_bytes(canonical_json(binding_material).encode("utf-8"))
    return row


def build() -> dict[str, Any]:
    manifest, manifest_digest = read_json(MANIFEST)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise RuntimeError("manifest 缺少 entries 数组")
    overlay_digest = source_digest(OVERLAY)
    adjudication_digest = source_digest(ADJUDICATION)
    # 只对**被读的那张表**算摘要：整份文件里还有别的段落，改它们不该让 binding 变 stale。
    wp_code_adjudication_digest = digest_bytes(
        canonical_json(
            (read_json(ADJUDICATION)[0] or {}).get("wp_code_adjudication") or {}
        ).encode("utf-8")
    )
    # 人工审核记录：**改它必须让 input_digest 变**，否则「改了审阅却没重跑」不会被
    # `--check` 发现（那正是 spec 要求 input digest 的理由）。
    reviewed_by_entry, reviewed_digest = load_reviewed()
    # 审核记录里的 entry 必须真的在 manifest 里 —— 拼错时静默无效比报错危险得多。
    manifest_ids = {str(e.get("entry_id") or "").strip() for e in manifest["entries"]}
    unknown = sorted(set(reviewed_by_entry) - manifest_ids)
    if unknown:
        raise RuntimeError(
            f"{REVIEWED.name} 里这些 entry_id 不在 manifest 中（拼写错会让审核静默失效）：{unknown}"
        )
    input_material = {
        "manifest_digest": manifest_digest,
        "overlay_digest": overlay_digest,
        "adjudication_digest": adjudication_digest,
        "wp_code_adjudication_digest": wp_code_adjudication_digest,
        "reviewed_digest": reviewed_digest,
        "schema_version": SCHEMA_VERSION,
    }
    input_digest = digest_bytes(canonical_json(input_material).encode("utf-8"))
    rows = [
        binding_for(dict(entry), input_digest=input_digest, reviewed=reviewed_by_entry)
        for entry in manifest["entries"]
    ]
    rows.sort(key=lambda row: (row["entry_id"], row["effective_entry_id"]))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "manifest": str(MANIFEST.relative_to(REPO)).replace("\\", "/"),
            "manifest_digest": manifest_digest,
            "overlay": str(OVERLAY.relative_to(REPO)).replace("\\", "/"),
            "overlay_digest": overlay_digest,
            "adjudication": str(ADJUDICATION.relative_to(REPO)).replace("\\", "/"),
            "adjudication_digest": adjudication_digest,
            # Requirement 8.1 点名：`wp_code` 裁决表本身的摘要（adjudication 文件里
            # 真正被读的那张表）。它与 `adjudication_digest`（整份文件）不同 ——
            # 整份文件里还有别的段落，改那些段落不该让 binding 变 stale。
            "wp_code_adjudication_digest": wp_code_adjudication_digest,
            # 人工审核记录文件（可能不存在 —— 那表示尚未审核任何 binding）。
            "reviewed": _display_path(REVIEWED),
            "reviewed_digest": reviewed_digest,
        },
        "input_digest": input_digest,
        "summary": {"entry_count": len(rows), "status_counts": counts},
        "bindings": rows,
    }


def render(payload: dict[str, Any], *, newline: str = "\n") -> bytes:
    """渲染生成物。

    🔴 `newline` 必须与**目标文件当前行尾**一致：`core.autocrlf=true` 下工作树是 CRLF
    而本函数默认 LF ⇒ `--check` 读工作树字节与输出恒不等 ⇒ 恒红。
    目标文件不存在时用 LF（git 会归一，不产生 churn）。

    与 `generate_legacy_onlyoffice_caller_ledger.render` 同族 —— 两个生成器都踩过。
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if newline != "\n":
        text = text.replace("\n", newline)
    return text.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    # 行尾与目标文件一致（见 render 的说明）。
    newline = "\n"
    if OUTPUT.is_file() and b"\r\n" in OUTPUT.read_bytes():
        newline = "\r\n"
    expected = render(build(), newline=newline)
    current = OUTPUT.read_bytes() if OUTPUT.is_file() else None
    if args.check:
        if current != expected:
            print(f"[FAIL] {OUTPUT}: generated binding projection is stale or missing")
            return 1
        print(f"[OK] {OUTPUT}: {len(json.loads(expected)['bindings'])} bindings")
        return 0
    OUTPUT.write_bytes(expected)
    print(f"[APPLIED] {OUTPUT}: {len(json.loads(expected)['bindings'])} bindings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
