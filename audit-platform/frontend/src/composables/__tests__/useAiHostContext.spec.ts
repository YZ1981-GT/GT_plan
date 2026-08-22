/**
 * Task 2 前端宿主契约守卫（Feature: dsh-agent-panel-integration）
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
 * Properties:
 *   - **Property 5（宿主加载器唯一映射）**：空 project ID 不会被构造成有效项目 HostContext；
 *     六个宿主提交同一形状，各自用自己的稳定标识。
 *     **Validates: Requirements 3.1, 3.2, 3.4, 3.7**
 *   - **Property 2（HostContext 断言一致性）** 的前端一侧：客户端只提交断言，
 *     取不到权威值时提交 `null` 而不是猜测值（猜测值到服务端就是 `host_context_mismatch`）。
 *     **Validates: Requirements 2.3, 3.3**
 *
 * 判据说明：本文件测的是 adapter 的**行为输出**（返回值形状与取值），
 * 不检查"源码里是否出现某个符号"。宿主页面的接线由
 * `src/components/__tests__/DocAiChatPanel.host.spec.ts` 用真实 mount + 模板形态判据守卫。
 */

import { describe, expect, it } from 'vitest'
import {
  AI_HOST_LABELS,
  AI_HOST_TYPES,
  AI_REPORT_HOST_IDS,
  GLOBAL_KNOWLEDGE_HOST_ID,
  buildAmbientHost,
  buildGlobalKnowledgeHost,
  buildKnowledgeDocHost,
  buildKnowledgeFolderHost,
  buildNoteHost,
  buildReportHost,
  buildWorkpaperHost,
  hostScopeHint,
  hostPathSegments,
  hostQueryString,
  isUuid,
  type AiHostRequest,
} from '../useAiHostContext'

const PROJECT_ID = '22222222-2222-4222-8222-222222222222'
const WP_ID = '11111111-1111-4111-8111-111111111111'
const NOTE_ID = '44444444-4444-4444-8444-444444444444'
const FOLDER_ID = '33333333-3333-4333-8333-333333333333'
const DOC_ID = '55555555-5555-4555-8555-555555555555'

/** 所有 adapter 产出必须具备的键（六宿主同形，Req 3.5）。 */
const REQUEST_KEYS = [
  'host',
  'available',
  'unavailableReason',
  'projectToolsEnabled',
  'label',
].sort()

const HOST_KEYS = ['type', 'id', 'projectId', 'year'].sort()

function assertShape(request: AiHostRequest) {
  expect(Object.keys(request).sort()).toEqual(REQUEST_KEYS)
  if (request.host) expect(Object.keys(request.host).sort()).toEqual(HOST_KEYS)
  if (request.available) {
    expect(request.unavailableReason).toBeNull()
    expect(request.host).not.toBeNull()
  } else {
    expect(request.host).toBeNull()
    expect(typeof request.unavailableReason).toBe('string')
    expect(request.unavailableReason).not.toHaveLength(0)
    expect(request.projectToolsEnabled).toBe(false)
  }
}

describe('useAiHostContext — 宿主类型取值域与后端枚举对账', () => {
  it('HostType 取值与后端 contracts.HostType 逐字一致', () => {
    // 后端真源：backend/app/services/ai_chat/contracts.py::HostType
    expect([...AI_HOST_TYPES]).toEqual([
      'workpaper',
      'note',
      'report',
      'knowledge_doc',
      'knowledge_folder',
      'global_knowledge',
    ])
    // 每个类型都有中文标签（NFR-5 全中文），无遗漏
    for (const t of AI_HOST_TYPES) {
      expect(AI_HOST_LABELS[t]).toBeTruthy()
    }
    expect(Object.keys(AI_HOST_LABELS).sort()).toEqual([...AI_HOST_TYPES].sort())
  })

  it('报表稳定 ID 取值与后端 FinancialReportType 一致', () => {
    expect([...AI_REPORT_HOST_IDS].sort()).toEqual([
      'balance_sheet',
      'cash_flow_statement',
      'cash_flow_supplement',
      'equity_statement',
      'impairment_provision',
      'income_statement',
    ])
  })

  it('全局知识 sentinel 与后端 GLOBAL_KNOWLEDGE_HOST_ID 一致', () => {
    expect(GLOBAL_KNOWLEDGE_HOST_ID).toBe('global-knowledge')
  })
})

describe('useAiHostContext — 六个宿主同形（Req 3.5）', () => {
  const all: Array<[string, AiHostRequest]> = [
    ['workpaper', buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: 2025 })],
    ['note', buildNoteHost({ noteId: NOTE_ID, projectId: PROJECT_ID, year: 2025 })],
    ['report', buildReportHost({ reportType: 'balance_sheet', projectId: PROJECT_ID, year: 2025 })],
    ['knowledge_doc', buildKnowledgeDocHost({ docId: DOC_ID })],
    ['knowledge_folder', buildKnowledgeFolderHost({ folderId: FOLDER_ID })],
    ['global_knowledge', buildGlobalKnowledgeHost()],
  ]

  it.each(all)('%s adapter 产出形状一致且类型正确', (type, request) => {
    assertShape(request)
    expect(request.available).toBe(true)
    expect(request.host!.type).toBe(type)
  })

  it('六个 adapter 覆盖全部 HostType，无遗漏无多余', () => {
    expect(all.map(([t]) => t).sort()).toEqual([...AI_HOST_TYPES].sort())
  })
})

describe('useAiHostContext — 绝不把项目 ID 当文档 ID（Req 3.5）', () => {
  it('报表 adapter 拒绝 project UUID / 空串 / 分析类 tab', () => {
    for (const bad of [
      PROJECT_ID, // 旧 ReportView 就是把它当 doc-id
      '',
      'cross_check',
      'multi_year_compare',
      'report_analysis',
      undefined,
      null,
    ]) {
      const req = buildReportHost({ reportType: bad, projectId: PROJECT_ID, year: 2025 })
      assertShape(req)
      expect(req.available).toBe(false)
      expect(req.host).toBeNull()
    }
    // 合法 report type 通过，且 id 就是 report type（不是项目 ID）
    const ok = buildReportHost({
      reportType: 'income_statement',
      projectId: PROJECT_ID,
      year: 2025,
    })
    expect(ok.host!.id).toBe('income_statement')
    expect(ok.host!.id).not.toBe(PROJECT_ID)
  })

  it('任何 adapter 的 host.id 都不会等于传入的 projectId', () => {
    const requests = [
      buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID }),
      buildNoteHost({ noteId: NOTE_ID, projectId: PROJECT_ID }),
      buildReportHost({ reportType: 'balance_sheet', projectId: PROJECT_ID }),
      buildKnowledgeFolderHost({ folderId: FOLDER_ID, projectId: PROJECT_ID }),
      buildKnowledgeDocHost({ docId: DOC_ID, projectId: PROJECT_ID }),
      buildGlobalKnowledgeHost(),
    ]
    for (const req of requests) {
      if (req.host) expect(req.host.id).not.toBe(PROJECT_ID)
    }
  })

  it('缺少资源标识时不可用，而不是发出空 doc_id', () => {
    for (const req of [
      buildWorkpaperHost({ wpId: '', projectId: PROJECT_ID }),
      buildWorkpaperHost({ wpId: undefined, projectId: PROJECT_ID }),
      buildNoteHost({ projectId: PROJECT_ID }),
      buildNoteHost({ noteId: '', sectionId: '', noteSection: '', projectId: PROJECT_ID }),
      buildKnowledgeFolderHost({ folderId: null }),
      buildKnowledgeDocHost({ docId: 'not-a-uuid' }),
    ]) {
      assertShape(req)
      expect(req.available).toBe(false)
    }
  })
})

describe('useAiHostContext — 空 project ID 不构造有效项目宿主（Req 3.3/3.4）', () => {
  it('项目类宿主在 projectId 为空串 / null / 非 UUID 时不可用', () => {
    for (const badProject of ['', '   ', null, undefined, 'null', 'proj-123']) {
      expect(buildWorkpaperHost({ wpId: WP_ID, projectId: badProject }).available).toBe(false)
      expect(buildNoteHost({ noteId: NOTE_ID, projectId: badProject }).available).toBe(false)
      expect(
        buildReportHost({ reportType: 'balance_sheet', projectId: badProject }).available,
      ).toBe(false)
    }
  })

  it('知识库宿主可无项目绑定，但 projectId 必须是 null 而不是空串', () => {
    // 旧 KnowledgeBase 传的是 `''` —— 空串伪装有效项目 ID
    const folder = buildKnowledgeFolderHost({ folderId: FOLDER_ID, projectId: '' })
    expect(folder.available).toBe(true)
    expect(folder.host!.projectId).toBeNull()
    expect(folder.projectToolsEnabled).toBe(false)

    const withProject = buildKnowledgeFolderHost({
      folderId: FOLDER_ID,
      projectId: PROJECT_ID,
    })
    expect(withProject.host!.projectId).toBe(PROJECT_ID)
    expect(withProject.projectToolsEnabled).toBe(true)
  })

  it('受限全局知识模式：无项目绑定且项目工具关闭', () => {
    const req = buildGlobalKnowledgeHost()
    assertShape(req)
    expect(req.host!.projectId).toBeNull()
    expect(req.host!.year).toBeNull()
    expect(req.host!.id).toBe(GLOBAL_KNOWLEDGE_HOST_ID)
    expect(req.projectToolsEnabled).toBe(false)
    expect(hostScopeHint(req)).toContain('项目工具不可用')
  })
})

describe('useAiHostContext — 年度断言不猜（Req 2.3 / Property 2 前端侧）', () => {
  it('取不到 audit_year 时传 null，不用「当前年份-1」兜底', () => {
    for (const bad of [undefined, null, '', 0, NaN, '不是年份']) {
      const req = buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: bad })
      expect(req.available).toBe(true)
      expect(req.host!.year).toBeNull()
    }
    const guessed = new Date().getFullYear() - 1
    const req = buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: null })
    expect(req.host!.year).not.toBe(guessed)
  })

  it('有权威年度时原样透传（含字符串形态）', () => {
    expect(buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: 2025 }).host!.year)
      .toBe(2025)
    expect(buildNoteHost({ noteId: NOTE_ID, projectId: PROJECT_ID, year: '2024' }).host!.year)
      .toBe(2024)
  })
})

describe('useAiHostContext — 附注稳定标识优先级（Req 3.2）', () => {
  it('instance ID 优先于 section key', () => {
    const req = buildNoteHost({
      noteId: NOTE_ID,
      sectionId: 'sec_abc',
      noteSection: '五、7',
      projectId: PROJECT_ID,
    })
    expect(req.host!.id).toBe(NOTE_ID)
  })

  it('无 instance ID 时用 section_id，其次 note_section', () => {
    expect(
      buildNoteHost({ sectionId: 'sec_abc', noteSection: '五、7', projectId: PROJECT_ID }).host!.id,
    ).toBe('sec_abc')
    expect(buildNoteHost({ noteSection: '五、7', projectId: PROJECT_ID }).host!.id).toBe('五、7')
  })

  it('非 UUID 的 noteId 不被当成 instance ID', () => {
    const req = buildNoteHost({
      noteId: 'note-001',
      noteSection: '五、7',
      projectId: PROJECT_ID,
    })
    expect(req.host!.id).toBe('五、7')
  })
})

describe('useAiHostContext — 全局面板 / 独立窗口的 ambient 宿主（Req 3.4/3.5）', () => {
  it('无项目上下文 → 显式全局模式（不发空 project_id）', () => {
    for (const badProject of [undefined, null, '', 'not-a-uuid']) {
      const req = buildAmbientHost({ projectId: badProject })
      assertShape(req)
      expect(req.host!.type).toBe('global_knowledge')
      expect(req.host!.projectId).toBeNull()
      expect(req.projectToolsEnabled).toBe(false)
    }
  })

  it('有项目 + 有底稿 → 绑定底稿宿主，项目工具开启', () => {
    const req = buildAmbientHost({ projectId: PROJECT_ID, wpId: WP_ID, auditYear: 2025 })
    expect(req.host!.type).toBe('workpaper')
    expect(req.host!.id).toBe(WP_ID)
    expect(req.host!.projectId).toBe(PROJECT_ID)
    expect(req.projectToolsEnabled).toBe(true)
  })

  it('有项目但无具体文档 → 仍用显式全局模式（不伪造项目级文档宿主）', () => {
    const req = buildAmbientHost({ projectId: PROJECT_ID })
    expect(req.host!.type).toBe('global_knowledge')
    expect(req.host!.projectId).toBeNull()
  })
})

describe('useAiHostContext — 请求载荷', () => {
  it('hostPathSegments 用宿主类型与稳定 ID 拼路径', () => {
    const req = buildReportHost({
      reportType: 'balance_sheet',
      projectId: PROJECT_ID,
      year: 2025,
    })
    expect(hostPathSegments(req.host!)).toEqual({
      docType: 'report',
      docId: 'balance_sheet',
    })
  })

  it('无项目绑定时不发 project_id 查询参数', () => {
    expect(hostQueryString(buildGlobalKnowledgeHost().host!)).toBe('')
    expect(hostQueryString(buildKnowledgeFolderHost({ folderId: FOLDER_ID }).host!)).toBe('')
    expect(
      hostQueryString(buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID }).host!),
    ).toBe(`?project_id=${PROJECT_ID}`)
  })

  it('不可用宿主的中文原因可直接展示', () => {
    const req = buildReportHost({ reportType: 'cross_check', projectId: PROJECT_ID })
    expect(hostScopeHint(req)).toContain('不是单张报表')
  })
})

describe('useAiHostContext — isUuid', () => {
  it('拒绝空串、null、伪 ID', () => {
    for (const bad of ['', ' ', 'null', 'undefined', 'proj-123', 'wp-001', null, undefined, 123]) {
      expect(isUuid(bad)).toBe(false)
    }
    expect(isUuid(PROJECT_ID)).toBe(true)
    expect(isUuid(` ${PROJECT_ID} `)).toBe(true)
  })
})
