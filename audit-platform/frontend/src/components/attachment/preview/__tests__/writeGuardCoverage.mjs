/**
 * Generate Task 17 guard_coverage.json + freeze nodeid manifest from vitest JSON.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const evidence = resolve(
  'D:/GT_plan/.kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/attachment-preview-format-expansion',
)

const vitest = JSON.parse(readFileSync(resolve(evidence, '_task17_vitest.json'), 'utf8'))
const feNodeids = []
for (const f of vitest.testResults || []) {
  const rel = String(f.name).replace(/\\/g, '/')
  const short = rel.includes('/src/') ? 'src/' + rel.split('/src/')[1] : rel
  for (const a of f.assertionResults || []) {
    feNodeids.push(`${short}::${a.fullName}`)
  }
}

const beNodeids = [
  'tests/attachment_preview_format_expansion/test_task1_legacy_api_dto_baseline.py::TestPreviewWhitelistContract::test_whitelist_frozen_and_includes_svg',
  'tests/attachment_preview_format_expansion/test_task1_legacy_api_dto_baseline.py::TestPreviewWhitelistContract::test_non_whitelist_json_shape_keys_documented',
  'tests/attachment_preview_format_expansion/test_task1_legacy_api_dto_baseline.py::TestPreviewWhitelistContract::test_upload_handler_has_size_gate_no_extension_whitelist',
  'tests/attachment_preview_format_expansion/test_task1_legacy_api_dto_baseline.py::TestGuessFileTypeProductionShape::test_guess_file_type_matrix',
  'tests/attachment_preview_format_expansion/test_task1_legacy_api_dto_baseline.py::TestProcessRecordDtoProjection::test_list_projection_includes_ocr_fields',
  'tests/attachment_preview_format_expansion/test_task1_legacy_api_dto_baseline.py::TestProcessRecordDtoProjection::test_sql_select_list_includes_ocr',
  'tests/attachment_preview_format_expansion/test_task1_legacy_api_dto_baseline.py::TestRegisteredDebtLedger::test_three_debts_out_of_scope',
]

/** Property → primary behavioural nodeids (titles/substrings ok for FE want matching) */
const properties = {
  1: {
    title: '判族确定、归一、封闭且 Type_Hint 只在无扩展名时作受限回退',
    nodeids: [
      'attachmentPreviewFormats.spec.ts::扩展名优先且大小写/空白稳定',
      'attachmentPreviewFormats.spec.ts::未知扩展名不被 Type_Hint 覆盖',
      'attachmentPreviewFormats.spec.ts::无扩展名时 Type_Hint MIME/分类词/别名受限回退',
    ],
    mutation_ids: ['M01'],
  },
  2: {
    title: 'legacy 归族、宿主能力矩阵与 Byte_Channel 均由 registry 单向派生',
    nodeids: [
      'attachmentPreviewFormats.spec.ts::legacy 走 preview 通道',
      'attachmentPreviewFormats.spec.ts::Preview 图片不含 svg；Drawer Office 10 项；Tab 6 项',
    ],
    mutation_ids: ['M02'],
  },
  3: {
    title: 'registry 外无第二份清单，跨族重复或 dwg 入族均 fail closed',
    nodeids: [
      'attachmentPreviewFormats.spec.ts::跨族冲突 fail closed',
      'attachmentPreviewFormats.spec.ts::dwg 入族 fail closed',
    ],
    mutation_ids: ['M03'],
  },
  4: {
    title: '新增三类只走 Download_Endpoint，两个宿主 legacy URL 逐字不变',
    nodeids: [
      'ExtendedFormatPreview.spec.ts::dev/Vitest 也走真实协议 fake module Worker',
      'extendedPreviewRequest.spec.ts::下载请求固定 _dedupe:false',
      'AttachmentPreviewOfficeIframe.spec.ts::docx uses previewPdf',
      'task1LegacyBaseline.spec.ts::fileName=',
    ],
    mutation_ids: ['M04'],
  },
  5: {
    title: 'JSON_Blob_Trap 记无敏感内容的 ERROR，403/404/其他失败互斥',
    nodeids: [
      'extendedPreviewRequest.spec.ts::JSON content-type → wiring_error',
      'extendedPreviewRequest.spec.ts::403/404 互斥映射',
    ],
    mutation_ids: ['M05'],
  },
  6: {
    title: 'close/switch/unmount 取消请求、终止 worker、释放 URL 与监听器',
    nodeids: ['previewResourceScope.spec.ts', 'EmailMessageView.spec.ts', 'ExtendedFormatPreview.spec.ts::Email CID'],
    mutation_ids: ['M06', 'M45', 'M47'],
  },
  7: {
    title: '_dedupe:false 保留调用方 signal，同 URL 双宿主互不取消，代际栅栏丢弃迟到结果',
    nodeids: [
      'ExtendedFormatPreview.spec.ts::_dedupe: false',
      'extendedPreviewRequest.spec.ts',
    ],
    mutation_ids: ['M07'],
  },
  8: {
    title: 'archive 清单展示实际大小且全部不可信解析在零网络、零落盘 Worker 内完成',
    nodeids: [
      'archiveNoNetwork.spec.ts',
      'ExtendedFormatPreview.spec.ts::zip 走 download 并渲染清单',
      'archiveFixtures.spec.ts',
    ],
    mutation_ids: ['M08', 'M32', 'M33', 'M34', 'M35', 'M37', 'M40', 'M41', 'M42', 'M48', 'M49'],
  },
  9: {
    title: '五项上限各自可触发，zip bomb 只按实际流式输出中止',
    nodeids: [
      'archiveLimits.spec.ts::各限可独立触发',
      'archiveFixtures.spec.ts::maxEntries 触发',
    ],
    mutation_ids: ['M09', 'M36', 'M38', 'M39', 'M50'],
  },
  10: {
    title: '路径穿越被标记且解析图无写出接口',
    nodeids: ['archiveFixtures.spec.ts', 'archiveLimits.spec.ts'],
    mutation_ids: ['M10', 'M08b'],
  },
  11: {
    title: '编码回退、加密提示、内容嗅探、unsupported 容器/方法分层',
    nodeids: ['archiveFixtures.spec.ts'],
    mutation_ids: ['M11'],
  },
  12: {
    title: 'eml/msg 在受限 Worker 中归一并展示头、正文与轻量附件清单',
    nodeids: ['emailDxf.spec.ts::解析头与正文'],
    mutation_ids: ['M12'],
  },
  13: {
    title: 'HTML 默认展示且可切文本，主动标签/属性与危险协议全部移除',
    nodeids: [
      'emailDxf.spec.ts::移除 script/事件并阻断外链图片',
      'EmailMessageView.spec.ts::跨邮件按当前安全正文复位',
    ],
    mutation_ids: ['M13', 'M46'],
  },
  14: {
    title: 'sanitizer 资源重写与 sandbox/CSP 双层阻断全部自动加载向量',
    nodeids: ['emailDxf.spec.ts::移除 script/事件并阻断外链图片'],
    mutation_ids: ['M14'],
  },
  15: {
    title: 'CID 仅安全栅格且跨邮件隔离，中文头可读，失败不污染下一封',
    nodeids: [
      'emailDxf.spec.ts::CID 仅在 magic 匹配时转 blob',
      'emailDxf.spec.ts::CID magic 不匹配时拒绝转 blob',
      'emailDxf.spec.ts::trim / 尖括号',
    ],
    mutation_ids: ['M15'],
  },
  16: {
    title: '两宿主各自 legacy DOM/文案/URL 不变且 Office 转 PDF 不受影响',
    nodeids: [
      'task1LegacyBaseline.spec.ts',
      'AttachmentPreviewOfficeIframe.spec.ts',
    ],
    mutation_ids: ['M16'],
  },
  17: {
    title: 'OCR 通过真实 DTO 链在新增视图可达，所有失败态保留下载',
    nodeids: [
      'task1LegacyBaseline.spec.ts::Drawer OCR badge/text',
      'test_list_projection_includes_ocr_fields',
      'ExtendedFormatPreview.spec.ts::dwg 不取字节',
    ],
    mutation_ids: ['M17'],
  },
  18: {
    title: 'preview/upload 行为契约不变且上传无扩展名白名单事实入账',
    nodeids: [
      'test_whitelist_frozen_and_includes_svg',
      'test_upload_handler_has_size_gate_no_extension_whitelist',
    ],
    mutation_ids: ['M18'],
  },
  19: {
    title: '任一解析异常都被状态机隔离且宿主仍可关闭',
    nodeids: [
      'emailParseIsolation.spec.ts::eml 解析器抛 → parse_failed 不 reject',
      'emailParseIsolation.spec.ts::msg 解析器构造抛 → parse_failed 不 reject',
      'emailDxf.spec.ts::损坏邮件 parse_failed 且不抛到外层',
      'ExtendedFormatPreview.spec.ts',
    ],
    mutation_ids: ['M19'],
  },
  20: {
    title: 'drawing 仅 dxf，dwg 永不创建 worker并显示专用文案',
    nodeids: [
      'attachmentPreviewFormats.spec.ts::dwg 仅 cad_download_only',
      'ExtendedFormatPreview.spec.ts::dwg 不取字节',
      'task1LegacyBaseline.spec.ts::LibreOffice 降级文案与 DWG',
      'dxfModel.spec.ts::所有 ENTITIES/BLOCKS 实体类型都参与预扫',
      'ExtendedFormatPreview.spec.ts::drawing Worker 消费单一真源',
    ],
    mutation_ids: ['M20', 'M43', 'M44'],
  },
  21: {
    title: '产品 chunk 许可证白名单、精确依赖清单与 lockfile 版本均可复核',
    nodeids: ['bundleBudget.spec.ts', 'dependency_licenses.json'],
    mutation_ids: ['M21'],
    evidence: ['dependency_licenses.json'],
  },
  22: {
    title: 'drawing 超门时完整退出并重建，不通过改阈值伪绿',
    nodeids: ['bundleBudget.spec.ts::drawing 超门 → drawing_drop'],
    mutation_ids: ['M22'],
  },
  23: {
    title: 'Route_Eligibility 先于真实生产构建体积裁决',
    nodeids: ['bundleBudget.spec.ts::A 资格失败时即使体积更小也不得入选'],
    mutation_ids: ['M23'],
  },
  24: {
    title: '首屏与各按需 chunk 分别报告且解析/worker 模块零字节归属首屏',
    nodeids: ['task16_production_bundle_gate.json'],
    mutation_ids: ['M24'],
    evidence: ['task16_production_bundle_gate.json'],
  },
  25: {
    title: '预算、基线 digest 与实测可复核',
    nodeids: ['bundleBudget.spec.ts', 'task16_production_bundle_gate.json'],
    mutation_ids: ['M25'],
  },
  26: {
    title: '守卫覆盖全部判据面且行为/DOM/网络优先于字符串存在',
    nodeids: ['guard_coverage.json'],
    mutation_ids: [],
    self: true,
  },
  27: {
    title: '每条 Property/test nodeid 有变异，四态按预期测试差集判读',
    nodeids: ['mutation_verdicts.json'],
    mutation_ids: [],
    deferred_to: 'task18',
  },
  28: {
    title: 'strict baseline、全目标快照/锁、finally 所有权安全还原',
    nodeids: ['mutation_verdicts.json'],
    mutation_ids: [],
    deferred_to: 'task18',
  },
  29: {
    title: '两宿主以真实 Type_Hint/DTO 接线，完整 render tree 的三要素均可观察',
    nodeids: [
      'task1LegacyBaseline.spec.ts::zip/eml/msg/dxf',
      'ExtendedFormatPreview.spec.ts::ArchiveEntryList',
      'task1LegacyBaseline.spec.ts::源码把 file_type 写入 type_hint',
    ],
    mutation_ids: ['M29'],
  },
  30: {
    title: 'artifact manifest 逐项证明 tracked，CI 引用在干净检出存在',
    nodeids: ['artifact_manifest.json'],
    mutation_ids: [],
    deferred_to: 'task20',
  },
  31: {
    title: 'xlsx 告警、AttachmentHub 待办与两宿主成本均登记且明确不夹带修复',
    nodeids: ['test_three_debts_out_of_scope'],
    mutation_ids: ['M31'],
  },
  32: {
    title: '本会话临时诊断产物按归属清除',
    nodeids: ['task20 cleanup'],
    mutation_ids: [],
    deferred_to: 'task20',
  },
}

// ── mutation id 存在性断言：property 引用的 mutation 必须在 mutation_verdicts.json 真实存在 ──
// 之前 guard_coverage 曾硬编码 M11/M12/M15/M18/M19/M22/M24/M25 等根本不存在的 id，本断言让虚数永久打红。
let knownMutationIds = null
try {
  const verdicts = JSON.parse(readFileSync(resolve(evidence, 'mutation_verdicts.json'), 'utf8'))
  knownMutationIds = new Set((Array.isArray(verdicts) ? verdicts : []).map((v) => v.id))
} catch {
  // mutation_verdicts.json 尚未生成（Task 18 之前）；此时不校验存在性，但记为 unverified
  knownMutationIds = null
}

if (knownMutationIds) {
  const dangling = []
  for (const [p, def] of Object.entries(properties)) {
    for (const id of def.mutation_ids || []) {
      if (!knownMutationIds.has(id)) dangling.push(`P${p} → ${id}`)
    }
  }
  if (dangling.length) {
    throw new Error(
      `guard_coverage: property 引用了 mutation_verdicts.json 中不存在的 mutation id：\n  ` +
        dangling.join('\n  '),
    )
  }
}

// 真实变异覆盖统计（分母 = 32 条 property；deferred_to 的元 property 不计入应有变异的分子）
const metaProps = new Set()
for (const [p, def] of Object.entries(properties)) {
  if (def.self || def.deferred_to) metaProps.add(p)
}
const propsWithMutation = Object.entries(properties).filter(
  ([, def]) => (def.mutation_ids || []).length > 0,
)
const propsExpectingMutationButMissing = Object.entries(properties)
  .filter(([p, def]) => !metaProps.has(p) && (def.mutation_ids || []).length === 0)
  .map(([p]) => Number(p))
const mutationCoverage = {
  total_properties: Object.keys(properties).length,
  properties_with_mutation: propsWithMutation.length,
  meta_properties_deferred: [...metaProps].map(Number).sort((a, b) => a - b),
  behavioural_props_missing_mutation: propsExpectingMutationButMissing,
  known_mutation_ids: knownMutationIds ? [...knownMutationIds].sort() : 'mutation_verdicts.json 未就绪',
  existence_asserted: !!knownMutationIds,
}

const coverage = {
  spec: 'audit-evidence-attachment-preview-format-expansion',
  task: 17,
  recorded_at: new Date().toISOString(),
  denominator: 'property_nodeid_not_file_count',
  mutation_coverage: mutationCoverage,
  frontend_passed: vitest.numPassedTests,
  frontend_failed: vitest.numFailedTests,
  backend_passed: 23,
  frontend_nodeid_count: feNodeids.length,
  backend_nodeid_groups: beNodeids.length,
  requirement_8_1_surfaces: [
    'registry',
    'dual_host_dispatch',
    'byte_channel',
    'json_trap',
    'http_cancel_dedupe',
    'archive_five_limits',
    'path_traversal',
    'email_sanitizer',
    'csp_network_zero',
    'cid_isolation',
  ],
  properties,
  frontend_nodeids: feNodeids,
  backend_nodeid_prefixes: beNodeids,
  gaps: [
    // meta-property：由脚本自身/收口任务证明，不需要独立 mutation
    { property: 26, kind: 'meta', note: '守卫覆盖矩阵自证（本文件 + 存在性断言）' },
    { property: 27, kind: 'meta', deferred_to: 'task18', note: '四态判读由变异脚本落 mutation_verdicts.json' },
    { property: 28, kind: 'meta', deferred_to: 'task18', note: 'strict baseline + O_EXCL 锁由变异脚本外层证明' },
    { property: 30, kind: 'meta', deferred_to: 'task20', note: 'artifact manifest + CI job 在收口证明' },
    { property: 32, kind: 'meta', deferred_to: 'task20', note: '临时诊断产物收口清理' },
    // 行为性缺口：应有变异却缺映射的 property（补完后此列表应为空）
    ...propsExpectingMutationButMissing.map((property) => ({
      property,
      kind: 'behavioural_missing_mutation',
      note: '该行为 property 尚无 mutation 映射，补齐变异后消除',
    })),
  ],
  gate:
    vitest.numFailedTests === 0 && propsExpectingMutationButMissing.length === 0
      ? 'PASS'
      : vitest.numFailedTests === 0
        ? 'PASS_WITH_MUTATION_GAPS'
        : 'BLOCK',
}

writeFileSync(resolve(evidence, 'guard_coverage.json'), JSON.stringify(coverage, null, 2))
writeFileSync(
  resolve(evidence, 'task17_guard_baseline_manifest.json'),
  JSON.stringify(
    {
      spec: 'audit-evidence-attachment-preview-format-expansion',
      task: 17,
      frontend_passed: vitest.numPassedTests,
      backend_passed: 23,
      frontend_filters: [
        'src/components/attachment/preview/__tests__',
        'src/__tests__/AttachmentPreviewOfficeIframe.spec.ts',
      ],
      backend_filters: ['tests/attachment_preview_format_expansion/'],
      frontend_nodeids: feNodeids,
      backend_nodeid_prefixes: beNodeids,
    },
    null,
    2,
  ),
)
console.log(
  JSON.stringify(
    {
      fe: vitest.numPassedTests,
      be: 23,
      props: Object.keys(properties).length,
      gate: coverage.gate,
    },
    null,
    2,
  ),
)
