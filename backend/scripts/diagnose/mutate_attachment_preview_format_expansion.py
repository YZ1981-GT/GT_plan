# -*- coding: utf-8 -*-
"""audit-evidence-attachment-preview-format-expansion Task 18 — 四态变异外层。

复用 `_mutation_kit` 的 Mutation/apply/judge；本脚本外层增加：
1. strict baseline（失败集空 + passed 与 Task17 manifest 相等）
2. O_EXCL spec lock
3. 全部 mutation target 的 bytes+hash pristine snapshot
4. finally 所有权安全还原；外部字节漂移 → RESTORE-CONFLICT

用法（仓库根）::

    python backend/scripts/diagnose/mutate_attachment_preview_format_expansion.py --list
    python backend/scripts/diagnose/mutate_attachment_preview_format_expansion.py --check-anchors
    python backend/scripts/diagnose/mutate_attachment_preview_format_expansion.py --run all \\
        --out .kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/attachment-preview-format-expansion/mutation_verdicts.json
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402
from _mutation_kit.apply import BAK_SUFFIX, restore_all, stale_backups  # noqa: E402
from _mutation_kit.anchor import md5_of  # noqa: E402
from _mutation_kit.cli import run_cli as _kit_run_cli  # noqa: E402
from _mutation_kit.runner import run_pytest, run_vitest  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = (
    REPO
    / ".kiro"
    / "specs"
    / "_archive"
    / "05-business-features"
    / "audit-evidence-attachment-preview-format-expansion"
    / "evidence"
    / "attachment-preview-format-expansion"
)
LOCK_PATH = EVIDENCE / ".mutation.lock"
BASELINE_MANIFEST = EVIDENCE / "task17_guard_baseline_manifest.json"

FMT = "audit-platform/frontend/src/components/attachment/preview/attachmentPreviewFormats.ts"
LIMITS = "audit-platform/frontend/src/components/attachment/preview/archive/archiveLimits.ts"
ARCHIVE = "audit-platform/frontend/src/components/attachment/preview/archive/archiveContainer.ts"
EMAILPARSER = "audit-platform/frontend/src/components/attachment/preview/email/emailParser.ts"
CONTRACT = (
    ".kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/"
    "attachment-preview-format-expansion/backend_preview_api_contract.json"
)
HTTP = "audit-platform/frontend/src/utils/http.ts"
FETCH = "audit-platform/frontend/src/components/attachment/preview/extendedPreviewRequest.ts"
SANITIZE = "audit-platform/frontend/src/components/attachment/preview/email/emailSanitizer.ts"
BUNDLE = "audit-platform/frontend/src/components/attachment/preview/bundleBudget.ts"
PROCESS = "backend/app/services/process_record_service.py"
DEBT = (
    ".kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/"
    "attachment-preview-format-expansion/registered_debt.json"
)
EXT_VUE = "audit-platform/frontend/src/components/attachment/preview/ExtendedFormatPreview.vue"
DXF_MODEL = "audit-platform/frontend/src/components/attachment/preview/drawing/dxfModel.ts"
EMAIL_VIEW = "audit-platform/frontend/src/components/attachment/preview/email/EmailMessageView.vue"
RESOURCE_SCOPE = "audit-platform/frontend/src/components/attachment/preview/previewResourceScope.ts"
# 收敛后单一预览宿主：弹窗/抽屉薄壳的 legacy 渲染全部下沉 AttachmentPreviewCore
CORE = "audit-platform/frontend/src/components/attachment/preview/AttachmentPreviewCore.vue"

GUARD_FILES = {
    "attachmentPreviewFormats.spec.ts": "Format_Registry / Type_Hint / legacy matrices",
    "archiveLimits.spec.ts": "Archive five limits",
    "archiveFixtures.spec.ts": "Archive fixtures / path / bomb",
    "archiveNoNetwork.spec.ts": "Archive parse zero-network",
    "extendedPreviewRequest.spec.ts": "JSON trap / 403/404",
    "ExtendedFormatPreview.spec.ts": "download channel / worker deadline / CID scope / dwg / list tree",
    "EmailMessageView.spec.ts": "CID object URL ownership / mode reset",
    "dxfModel.spec.ts": "DXF all-entity prescan / typed scene graph",
    "emailDxf.spec.ts": "email sanitize / CID / dxf",
    "emailParseIsolation.spec.ts": "email parse exception isolation (P19)",
    "previewResourceScope.spec.ts": "resource release",
    "bundleBudget.spec.ts": "route eligibility before budget",
    "task1LegacyBaseline.spec.ts": "legacy DOM / OCR / TabPanel",
    "AttachmentPreviewOfficeIframe.spec.ts": "Office preview-pdf URLs",
    "httpDedupe.signal.spec.ts": "_dedupe:false signal contract",
    "test_task1_legacy_api_dto_baseline.py": "preview/upload/DTO/debt",
}

MUTATIONS: list[Mutation] = [
    Mutation(
        id="M01",
        side="fe",
        path=FMT,
        kind="replace",
        anchor="    if (byExt) return byExt",
        new="    if (byExt) return byExt\n    if (typeHint) return { family: 'legacy', byteChannel: 'preview', ext: fromName, advice: 'generic', evidence: 'type_hint' }",
        want="未知扩展名不被 Type_Hint 覆盖",
        why="未知扩展名被 Type_Hint 覆盖成 legacy ⇒ P1 必须 RED",
    ),
    Mutation(
        id="M02",
        side="fe",
        path=FMT,
        kind="replace",
        anchor="    image: Object.freeze(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'] as const),",
        new="    image: Object.freeze(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'] as const),",
        want="Preview 图片不含 svg",
        why="legacy union 把 svg 扩进 Preview 图片集 ⇒ P2/P16 必须 RED",
    ),
    Mutation(
        id="M03",
        side="fe",
        path=FMT,
        kind="replace",
        anchor="  drawing: ['dxf'],",
        new="  drawing: ['dxf', 'dwg'],",
        want="<file-level>:attachmentPreviewFormats.spec.ts",
        why="dwg 入 drawing 族在模块装载期 fail-closed ⇒ 文件级收集失败必须 RED",
    ),
    Mutation(
        id="M04",
        side="fe",
        path=FETCH,
        kind="replace",
        anchor="      _dedupe: false,",
        new="      _dedupe: true,",
        want="下载请求固定 _dedupe:false",
        why="新增三类取字节丢掉 _dedupe:false ⇒ ExtendedFormatPreview 调用契约必须 RED",
    ),
    Mutation(
        id="M05",
        side="fe",
        path=FETCH,
        kind="replace",
        anchor="      logger.error('attachment_preview_json_blob_trap', {",
        new="      logger.error('attachment_preview_json_blob_trap', { previewable: true,",
        want="wiring_error，且日志不含正文",
        why="JSON trap 日志夹带 previewable ⇒ 无敏感内容断言必须 RED",
    ),
    Mutation(
        id="M06",
        side="fe",
        path="audit-platform/frontend/src/components/attachment/preview/previewResourceScope.ts",
        kind="replace",
        anchor="    this.objectUrls.clear()",
        new="    /* mutated: keep object URLs tracked */",
        want="releaseAll 幂等且 late-track 资源立即释放",
        why="跳过 revokeObjectURL ⇒ PreviewResourceScope 回收守卫必须 RED",
    ),
    Mutation(
        id="M07",
        side="fe",
        path=HTTP,
        kind="replace",
        anchor="  if ((config as any)._dedupe === false) return",
        new="  if ((config as any)._dedupe === false && false) return",
        want="_dedupe:false",
        why="忽略 _dedupe:false 早退 ⇒ httpDedupe.signal 双请求互不取消必须 RED",
    ),
    Mutation(
        id="M08",
        side="fe",
        path=LIMITS,
        kind="replace",
        anchor="  maxEntries: 2000,",
        new="  maxEntries: 999999,",
        want="五项单一真源数值",
        why="抬高 maxEntries ⇒ 五限真源数值守卫必须 RED",
    ),
    Mutation(
        id="M08b",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="import { Inflate } from 'fflate'",
        new="import { Inflate } from 'fflate'\nimport http from '@/utils/http'",
        want="archive 目录源码不含 fetch/XHR/http/fs 写出",
        why="archive 容器引入 http ⇒ 零网络结构守卫必须 RED",
    ),
    Mutation(
        id="M09",
        side="fe",
        path=LIMITS,
        kind="replace",
        anchor="  maxCompressionRatio: 100,",
        new="  maxCompressionRatio: 1000000,",
        want="各限可独立触发",
        why="压缩比门失效 ⇒ 独立触发断言/夹具 bomb 路径必须 RED",
    ),
    Mutation(
        id="M10",
        side="fe",
        path=LIMITS,
        kind="replace",
        anchor="  maxPathDepth: 8,",
        new="  maxPathDepth: 999,",
        want="path depth 9 在 ZIP/TAR 真实解析中触发 maxPathDepth",
        why="抬高 maxPathDepth ⇒ 深度标记与五限真源守卫必须 RED",
    ),
    Mutation(
        id="M13",
        side="fe",
        path=SANITIZE,
        kind="replace",
        anchor='  "img-src blob: data:",',
        new='  "img-src *",',
        want="移除 script/事件并阻断外链图片",
        why="CSP 放开 img-src * ⇒ 邮件 CSP 字面量守卫必须 RED",
    ),
    Mutation(
        id="M14",
        side="fe",
        path=SANITIZE,
        kind="replace",
        anchor='  "default-src \'none\'",',
        new='  "default-src *",',
        want="移除 script/事件并阻断外链图片",
        why="CSP default-src 放开 ⇒ wrapEmailSrcdoc CSP 字面量守卫必须 RED",
    ),
    Mutation(
        id="M16",
        side="fe",
        path=CORE,
        kind="replace",
        anchor="  if (isOfficeServer.value && props.attachment?.id) return P_att.previewPdf(props.attachment.id)",
        new="  if (isOfficeServer.value && props.attachment?.id) return props.attachment?.preview_url || ''",
        want="docx uses previewPdf",
        why="Office 改回 preview_url ⇒ preview-pdf 宿主 URL 守卫必须 RED",
    ),
    Mutation(
        id="M17",
        side="be",
        path=PROCESS,
        kind="replace",
        anchor='            "a.ocr_status, a.ocr_text "',
        new='            "a.file_name, a.file_type "',
        want="test_sql_select_list_includes_ocr",
        why="DTO OCR 投影被替换 ⇒ process-record OCR 守卫必须 RED",
    ),
    Mutation(
        id="M20",
        side="fe",
        path=FMT,
        kind="replace",
        anchor="      advice: 'cad_download_only',",
        new="      advice: 'generic',",
        want="dwg 仅 cad_download_only",
        why="dwg 失去 cad_download_only ⇒ drawing/dwg 专用文案守卫必须 RED",
    ),
    Mutation(
        id="M21",
        side="fe",
        path=BUNDLE,
        kind="replace",
        # capability gate first — mutate to prefer volume over capability
        anchor="  const eligible = measurements.filter((m) => isCapabilityEligible(m.capability))",
        new="  const eligible = measurements.filter((m) => m.entryGzip < 999999999)",
        want="A 资格失败时即使体积更小也不得入选",
        why="体积门抢在资格门前 ⇒ Route_Eligibility 先后顺序必须 RED",
    ),
    Mutation(
        id="M23",
        side="fe",
        path=BUNDLE,
        kind="replace",
        anchor="  entryParserBytes: 0,",
        new="  entryParserBytes: 1,",
        want="entryParserBytes 预算真源为 0",
        why="预算真源 entryParserBytes 非 0 ⇒ 预算常量守卫必须 RED",
    ),
    Mutation(
        id="M29",
        side="fe",
        path=EXT_VUE,
        kind="replace",
        anchor="  if (verdict.advice === 'cad_download_only' || !isExtendedFamily(verdict.family)) {",
        new="  if (!isExtendedFamily(verdict.family) && false) {",
        want="dwg 不取字节",
        why="单宿主断线：dwg 短路被关掉 ⇒ ExtendedFormatPreview dwg 守卫必须 RED",
    ),
    Mutation(
        id="M11",
        side="fe",
        path=LIMITS,
        kind="replace",
        anchor="  99: 'container_unsupported', // AES",
        new="  99: 'entry_ok', // AES",
        want="加密与 unsupported method",
        why="AES 加密方法被当可解 ⇒ unsupported 容器/方法分层守卫必须 RED",
    ),
    Mutation(
        id="M12",
        side="fe",
        path=EMAILPARSER,
        kind="replace",
        anchor="      to: asList(mail.to),",
        new="      to: [],",
        want="解析头与正文",
        why="收件人归一被清空 ⇒ 邮件头部归一守卫（解析头与正文）必须 RED",
    ),
    Mutation(
        id="M15",
        side="fe",
        path=SANITIZE,
        kind="replace",
        anchor="  return detectRasterMime(bytes) === declaredMime.toLowerCase()",
        new="  return true",
        want="CID magic 不匹配时拒绝转 blob",
        why="PNG magic 恒真 ⇒ CID magic 不匹配拒绝守卫必须 RED",
    ),
    Mutation(
        id="M18",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    "extension_whitelist": false,',
        new='    "extension_whitelist": true,',
        want="test_upload_handler_has_size_gate_no_extension_whitelist",
        why="谎报上传有扩展名白名单 ⇒ preview/upload 契约守卫必须 RED",
    ),
    Mutation(
        id="M19",
        side="fe",
        path=EMAILPARSER,
        kind="replace",
        anchor="    return { status: 'parse_failed', message: error instanceof Error ? error.message : 'parse_failed' }",
        new="    throw error",
        want="归一为 parse_failed",
        why="解析异常改为向外抛 ⇒ P19 解析异常隔离守卫必须 RED",
    ),
    Mutation(
        id="M22",
        side="fe",
        path=BUNDLE,
        kind="replace",
        anchor="  return size <= budget.drawingChunk",
        new="  return size <= budget.drawingChunk * 1000",
        want="drawing 超门 → drawing_drop",
        why="放宽 drawing 门 ⇒ drawing 超门 drawing_drop 守卫必须 RED",
    ),
    Mutation(
        id="M24",
        side="fe",
        path=BUNDLE,
        kind="replace",
        anchor="  if (onDemand > budget.onDemandTotal) {",
        new="  if (onDemand > budget.onDemandTotal * 1000) {",
        want="按需 chunk 合计超门",
        why="放宽按需合计门 ⇒ subset_required 守卫必须 RED",
    ),
    Mutation(
        id="M25",
        side="fe",
        path=BUNDLE,
        kind="replace",
        anchor="  entryGzipDelta: 8 * 1024,",
        new="  entryGzipDelta: 9 * 1024,",
        want="entryGzipDelta 首屏增量门为 8 KiB",
        why="首屏增量门真源被改 ⇒ entryGzipDelta 8KiB 常量守卫必须 RED",
    ),
    Mutation(
        id="M32",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  if ((~gzipCrc >>> 0) !== frame.expectedCrc) {",
        new="  if (false) {",
        want="gzip trailer CRC",
        why="跳过 GZIP trailer CRC ⇒ 损坏 TGZ 被接受，完整性守卫必须 RED",
    ),
    Mutation(
        id="M33",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  const usesDescriptor = !!(record.flags & 0x8)",
        new="  const usesDescriptor = false",
        want="classic data descriptor 有/无签名",
        why="关闭 bit 3 descriptor 分支 ⇒ 合法 classic descriptor 支持守卫必须 RED",
    ),
    Mutation(
        id="M34",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  if (isDirectory && size !== 0) {",
        new="  if (false) {",
        want="TAR 目录条目不得携带正文",
        why="允许目录正文绕过结构门 ⇒ TAR 资源绕过守卫必须 RED",
    ),
    Mutation(
        id="M35",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="    if (unread !== 0) return parseFailure(state.entries, 'deflate_trailing_data')",
        new="    if (false) return parseFailure(state.entries, 'deflate_trailing_data')",
        want="entry 数据跨度必须与下一结构精确闭合",
        why="忽略 DEFLATE 尾随垃圾 ⇒ 声明压缩跨度未完整消费仍被接受，结构守卫必须 RED",
    ),
    Mutation(
        id="M36",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="      state.compressedConsumed = pushedBytes - unread",
        new="      state.compressedConsumed = buf.length",
        want="gzip 可选 header 不计入压缩比分母",
        why="把 GZIP wrapper 计入 ratio 分母 ⇒ 巨型可选头可绕过 zip-bomb 门，守卫必须 RED",
    ),
    Mutation(
        id="M37",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  if ((gzipOutputBytes >>> 0) !== frame.expectedSize) {",
        new="  if (false) {",
        want="gzip trailer CRC、ISIZE",
        why="跳过 GZIP ISIZE 一致性 ⇒ 损坏 trailer 被接受，结构守卫必须 RED",
    ),
    Mutation(
        id="M38",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  if (initialLimit && initialLimit !== 'maxCompressionRatio') {",
        new="  if (initialLimit && initialLimit !== 'maxCompressionRatio' && initialLimit !== 'maxPathDepth') {",
        want="path depth 9 在 ZIP/TAR 真实解析中触发",
        why="TAR 忽略真实路径深度门 ⇒ maxPathDepth 行为守卫必须 RED",
    ),
    Mutation(
        id="M39",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="        entryCompressedConsumed: state.compressedConsumed - state.entryCompressedStart,",
        new="        entryCompressedConsumed: undefined,",
        want="前置 stored 条目不能稀释后续单条 deflate bomb",
        why="移除 ZIP 单 entry ratio ⇒ 前置大条目可稀释 bomb，守卫必须 RED",
    ),
    Mutation(
        id="M40",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  const fullName = state.nextPax.path ?? state.nextLongName ?? state.globalPax.path ?? headerName",
        new="  const fullName = state.nextLongName ?? state.globalPax.path ?? headerName",
        want="受限 PAX/GNU long-name 只作用于真实条目",
        why="忽略 local PAX path ⇒ 受限 PAX 真消费守卫必须 RED",
    ),
    Mutation(
        id="M41",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  if (typeflag === 'S') {",
        new="  if (false) {",
        want="TAR sparse、PAX sparse 与异常扩展",
        why="GNU sparse type 不再专门 fail closed ⇒ sparse 判据守卫必须 RED",
    ),
    Mutation(
        id="M42",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="    return hintExt?.toLowerCase().replace(/^\\./, '') === 'gz'",
        new="    return false",
        want="普通 .gz 按 hint 返回单条实际元数据",
        why="忽略 .gz hint 并强制走 TAR ⇒ 普通 gzip 支持守卫必须 RED",
    ),
    Mutation(
        id="M43",
        side="fe",
        path=DXF_MODEL,
        kind="replace",
        anchor="    if ((section === 'ENTITIES' || section === 'BLOCKS') && !DXF_STRUCTURE_TOKENS.has(value)) {",
        new="    if ((section === 'ENTITIES' || section === 'BLOCKS') && !DXF_STRUCTURE_TOKENS.has(value) && value !== 'HATCH') {",
        want="所有 ENTITIES/BLOCKS 实体类型都参与预扫",
        why="unsupported HATCH 绕过预扫 ⇒ 全实体计数守卫必须 RED",
    ),
    Mutation(
        id="M44",
        side="fe",
        path=EXT_VUE,
        kind="replace",
        anchor="    DRAWING_LIMITS.deadlineMs,",
        new="    WORKER_DEADLINE_MS,",
        want="drawing Worker 消费单一真源的 10 秒 deadline",
        why="drawing 恢复统一 15 秒 ⇒ deadline 接线守卫必须 RED",
    ),
    Mutation(
        id="M45",
        side="fe",
        path=RESOURCE_SCOPE,
        kind="replace",
        anchor="    if (!this.objectUrls.delete(url)) return",
        new="    return",
        want="CID URL 纳入 PreviewResourceScope",
        why="单 URL release 失效 ⇒ CID 换信/卸载资源回收守卫必须 RED",
    ),
    Mutation(
        id="M46",
        side="fe",
        path=EMAIL_VIEW,
        kind="replace",
        anchor="    mode.value = v.html ? 'html' : 'text'",
        new="    if (!v.html) mode.value = 'text'",
        want="跨邮件按当前安全正文复位 HTML/text mode",
        why="HTML 新邮件沿用上一封 text mode ⇒ 切信状态守卫必须 RED",
    ),
    Mutation(
        id="M47",
        side="fe",
        path=EXT_VUE,
        kind="replace",
        anchor='        :create-object-url="createEmailObjectUrl"',
        new='        data-mutated-create-object-url="missing"',
        want="Email CID object URL 由宿主 PreviewResourceScope 统一持有",
        why="宿主不再注入 scope factory ⇒ CID URL 逃逸统一资源台账，集成守卫必须 RED",
    ),
    Mutation(
        id="M48",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="      mtime,",
        new="      mtime: null,",
        want="解析 header/PAX mtime",
        why="TAR mtime 模型消费断线 ⇒ 元数据守卫必须 RED",
    ),
    Mutation(
        id="M49",
        side="fe",
        path=ARCHIVE,
        kind="replace",
        anchor="  const fullName = state.nextPax.path ?? state.nextLongName ?? state.globalPax.path ?? headerName",
        new="  const fullName = state.nextPax.path ?? state.globalPax.path ?? headerName",
        want="受限 PAX/GNU long-name 只作用于真实条目",
        why="GNU long-name 不再覆盖下一 header ⇒ long-name 守卫必须 RED",
    ),
    Mutation(
        id="M50",
        side="fe",
        path=LIMITS,
        kind="replace",
        anchor="  if (state.pathDepth > limits.maxPathDepth) return 'maxPathDepth'",
        new="  if (state.pathDepth > limits.maxPathDepth && state.totalUncompressed / Math.max(1, state.compressedConsumed) <= limits.maxCompressionRatio) return 'maxPathDepth'",
        want="TAR 路径门不被头阶段 ratio 遮蔽",
        why="只在 ratio 未超限时检查路径 ⇒ 大正文可遮蔽 TAR/PAX/GNU 深路径，交叉守卫必须 RED",
    ),
    Mutation(
        id="M31",
        side="be",
        path=DEBT,
        kind="replace",
        anchor='      "in_scope": false,',
        new='      "in_scope": true,',
        scope='      "id": "xlsx-0.18.5-cve",',
        offset=1,
        want="test_three_debts_out_of_scope",
        why="registered debt 标回 in_scope=true ⇒ 债务不夹带修复守卫必须 RED",
    ),
]


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _acquire_lock() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(LOCK_PATH), flags)
    except FileExistsError:
        print(f"RESTORE-CONFLICT: lock exists {LOCK_PATH}", file=sys.stderr)
        return 0
    os.write(fd, f"pid={os.getpid()} ts={time.time()}\n".encode("utf-8"))
    return fd


def _release_lock(fd: int | None) -> None:
    if fd:
        try:
            os.close(fd)
        except OSError:
            pass
    if LOCK_PATH.exists():
        LOCK_PATH.unlink(missing_ok=True)  # type: ignore[arg-type]


def _snapshot_targets() -> dict[str, dict[str, str | int]]:
    out: dict[str, dict[str, str | int]] = {}
    for m in MUTATIONS:
        p = REPO / m.path
        raw = p.read_bytes()
        out[m.path] = {"sha1": hashlib.sha1(raw).hexdigest(), "bytes": len(raw)}
    return out


def _verify_pristine(snap: dict[str, dict[str, str | int]], label: str) -> list[str]:
    problems: list[str] = []
    for rel, meta in snap.items():
        p = REPO / rel
        if not p.exists():
            problems.append(f"{label}: missing {rel}")
            continue
        raw = p.read_bytes()
        if len(raw) != meta["bytes"] or hashlib.sha1(raw).hexdigest() != meta["sha1"]:
            problems.append(f"{label}: RESTORE-CONFLICT on {rel}")
        bak = Path(str(p) + BAK_SUFFIX)
        if bak.exists():
            problems.append(f"{label}: leftover {bak.name}")
    return problems


def _strict_baseline() -> tuple[bool, str]:
    man = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
    expect_fe = int(man["frontend_passed"])
    expect_be = int(man["backend_passed"])

    be = run_pytest(
        REPO,
        [
            "backend/tests/attachment_preview_format_expansion/",
            "-c",
            "backend/pytest.ini",
            "-q",
            "--tb=no",
            "-rfE",
        ],
    )
    fe_dir = REPO / "audit-platform" / "frontend"
    fe = run_vitest(
        fe_dir,
        [
            "src/components/attachment/preview/__tests__",
            "src/__tests__/AttachmentPreviewOfficeIframe.spec.ts",
            "src/utils/__tests__/httpDedupe.signal.spec.ts",
        ],
        fe_dir / ".apfe-mutation-baseline.json",
    )
    if be.failed or fe.failed:
        return False, f"baseline has failures be={sorted(be.failed)} fe={sorted(fe.failed)}"
    if be.passed != expect_be:
        return False, f"backend passed {be.passed} != manifest {expect_be}"
    if fe.passed != expect_fe:
        return False, f"frontend passed {fe.passed} != manifest {expect_fe}"
    return True, f"strict baseline ok be={be.passed} fe={fe.passed}"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # passthrough for --list / --check-anchors without lock
    if any(a in ("--list", "--check-anchors", "-h", "--help") for a in argv):
        return _kit_main(argv)

    fd = None
    snap: dict[str, dict[str, str | int]] = {}
    try:
        fd = _acquire_lock()
        if not fd:
            return 3
        ok, msg = _strict_baseline()
        print(msg)
        if not ok:
            return 2
        snap = _snapshot_targets()
        (EVIDENCE / "mutation_target_pristine.json").write_text(
            json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        code = _kit_main(argv)
        problems = _verify_pristine(snap, "post-run")
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 4
        return code
    finally:
        if snap:
            # best-effort restore if kit left anything
            try:
                restore_all(REPO)
            except Exception as exc:  # noqa: BLE001
                print(f"restore_all: {exc}", file=sys.stderr)
            problems = _verify_pristine(snap, "finally")
            if problems:
                print("\n".join(problems), file=sys.stderr)
        _release_lock(fd)


def _kit_main(argv: list[str]) -> int:
    fe_dir = REPO / "audit-platform" / "frontend"
    # rebuild argv into sys for run_cli argparse
    old = sys.argv
    try:
        sys.argv = [old[0], *argv]
        return run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="attachment-preview-format-expansion Task 18 mutations",
            backend_args=[
                "backend/tests/attachment_preview_format_expansion/",
                "-c",
                "backend/pytest.ini",
                "-q",
                "--tb=no",
                "-rfE",
            ],
            frontend_dir=fe_dir,
            vitest_json=fe_dir / ".apfe-mutation-vitest.json",
            frontend_filters=[
                "src/components/attachment/preview/__tests__",
                "src/__tests__/AttachmentPreviewOfficeIframe.spec.ts",
                "src/utils/__tests__/httpDedupe.signal.spec.ts",
            ],
            baseline_backend_passed=23,
            baseline_frontend_passed=180,
        )
    finally:
        sys.argv = old


if __name__ == "__main__":
    raise SystemExit(main())
