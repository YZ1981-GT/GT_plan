/**
 * 「纳入当前未保存草稿」纯函数守卫（spec chat-host-draft-overlay / Task 5）
 *
 * Requirements:
 *   - 4.4：默认关闭（面板侧默认值由 `PlatformAiChatDraftOverlay.spec.ts` 在真实 DOM 上断言）。
 *   - 5.2：**不改既有「提示未纳入」文案** —— 开关关闭时范围说明逐字不变。
 *   - 2.5：manifest 能区分「已保存内容」与「未保存草稿」，前端在消息上标注。
 *
 * ## 判据取向
 *
 * * 「关闭时文案逐字不变」用**与 `hostScopeHint()` 输出直接 `toBe`** 证明（不是 `toContain`）：
 *   需求 5.2 说的是"不改既有文案"，改一个字都算违约，只有全等能钉住。
 * * 「开启时只换尾句」同时断言**前缀仍在**（宿主标签不能丢）与**旧尾句已消失**
 *   （否则会变成"不会纳入本轮"和"将纳入"同时出现的自相矛盾文案）。
 * * `denied` 原因是后端产出的中文整句 ⇒ 断言**含汉字**且不含英文码；
 *   `trimmed` / `unavailable` 的 reason 是英文码 ⇒ 断言**不把英文码露给用户**。
 */

import { describe, expect, it } from 'vitest'

import {
  DRAFT_OVERLAY_SOURCE_PREFIX,
  SCOPE_TAIL_SAVED_ONLY,
  buildDraftOverlayPayload,
  draftOverlayNoticeText,
  formatDraftBaselineVersion,
  hostScopeHintWithDraft,
  readDraftOverlayNotice,
  type ChatDraftOverlayNotice,
} from '@/composables/aiDraftOverlay'
import {
  buildGlobalKnowledgeHost,
  buildReportHost,
  buildWorkpaperHost,
  hostScopeHint,
  type AiHostRequest,
} from '@/composables/useAiHostContext'
import type { WorkpaperDraftOverlay } from '@/composables/workpaper/workpaperDraftOverlay'

const PROJECT_ID = '22222222-2222-4222-8222-222222222222'
const WP_ID = '11111111-1111-4111-8111-111111111111'
const BASELINE = '2026-11-15T10:00:00+00:00'
const CJK_RE = /[\u4e00-\u9fff]/

function workpaperHost(): AiHostRequest {
  return buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: 2025 })
}

function overlay(overrides: Partial<WorkpaperDraftOverlay> = {}): WorkpaperDraftOverlay {
  return {
    content: '未保存的正文',
    baselineVersion: BASELINE,
    contentLength: 6,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// 范围文案（需求 5.2 / design §5.3）
// ---------------------------------------------------------------------------

describe('范围文案 — 关闭时逐字不变，开启时只换尾句', () => {
  it('既有尾句常量与 hostScopeHint 的实际输出一致（防止两侧漂移）', () => {
    // 这条是下面「关闭时逐字不变」判据的地基：常量一旦与真实文案脱钩，
    // 替换逻辑会静默失效（前缀不以尾句结尾 ⇒ 原样返回 ⇒ 开关看起来没作用）。
    expect(hostScopeHint(workpaperHost())).toContain(SCOPE_TAIL_SAVED_ONLY)
    expect(hostScopeHint(workpaperHost()).endsWith(SCOPE_TAIL_SAVED_ONLY)).toBe(true)
  })

  it('开关打开 → 尾句换成「将纳入当前未保存草稿（基于版本 v…）」，前缀保留', () => {
    const text = hostScopeHintWithDraft(workpaperHost(), BASELINE)
    expect(text).toContain('将纳入当前未保存草稿（基于版本 v')
    expect(text).not.toContain('当前未保存修改不会纳入本轮')
    // 前缀（宿主标签）仍在 —— 只换尾句，不重写整句
    expect(text.startsWith('当前范围：底稿；')).toBe(true)
  })

  it('版本被渲染成可读的 UTC 短形态，且不做本地时区换算', () => {
    const text = hostScopeHintWithDraft(workpaperHost(), BASELINE)
    expect(text).toContain('2026-11-15 10:00:00 UTC')
    // 换算到本地时区会让同一份草稿在不同机器上显示不同时间
    expect(text).not.toContain('+00:00')
  })

  it('基线缺失 → 显示「（未知）」而不是拼出半截句子', () => {
    const text = hostScopeHintWithDraft(workpaperHost(), null)
    expect(text).toContain('将纳入当前未保存草稿（基于版本 v（未知））')
    expect(text).not.toContain('不会纳入本轮')
  })

  it('全局知识模式 / 宿主不可用时原样返回（那些情形没有草稿可言）', () => {
    const global = buildGlobalKnowledgeHost()
    expect(hostScopeHintWithDraft(global, BASELINE)).toBe(hostScopeHint(global))

    const unavailable = buildReportHost({ reportType: 'cross_check', projectId: PROJECT_ID })
    expect(hostScopeHintWithDraft(unavailable, BASELINE)).toBe(hostScopeHint(unavailable))
  })
})

describe('formatDraftBaselineVersion — 短且确定', () => {
  it.each([
    ['2026-11-15T10:00:00+00:00', '2026-11-15 10:00:00 UTC'],
    ['2026-11-15T10:00:00.123456+00:00', '2026-11-15 10:00:00 UTC'],
    ['', ''],
    [null, ''],
    [undefined, ''],
    // 认不出的形状原样返回（与后端 normalize_business_version 的"不猜"取向一致）
    ['not-a-timestamp', 'not-a-timestamp'],
  ])('%s → %s', (input, expected) => {
    expect(formatDraftBaselineVersion(input)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// 请求载荷（design §2 / 需求 6.1）
// ---------------------------------------------------------------------------

describe('buildDraftOverlayPayload — 只在有可用草稿时构造', () => {
  it('可用底稿 + 有草稿 → 五个字段齐全，host_id 取宿主稳定 ID', () => {
    const payload = buildDraftOverlayPayload(workpaperHost(), overlay())
    expect(payload).toEqual({
      host_type: 'workpaper',
      host_id: WP_ID,
      baseline_version: BASELINE,
      content: '未保存的正文',
      content_length: 6,
    })
  })

  it('没有草稿 → null（调用方据此省略整个 draft_overlay 键）', () => {
    expect(buildDraftOverlayPayload(workpaperHost(), null)).toBeNull()
    expect(buildDraftOverlayPayload(workpaperHost(), undefined)).toBeNull()
  })

  it('宿主不可用 / 非底稿 → null（不拿别的宿主内容冒充本宿主草稿）', () => {
    const unavailable: AiHostRequest = {
      host: null,
      available: false,
      unavailableReason: '当前页面未解析到项目，项目工具不可用',
      projectToolsEnabled: false,
      label: '底稿',
    }
    expect(buildDraftOverlayPayload(unavailable, overlay())).toBeNull()

    const global = buildGlobalKnowledgeHost()
    expect(buildDraftOverlayPayload(global, overlay())).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// manifest 条目解析（需求 2.5）
// ---------------------------------------------------------------------------

/** 服务端真实形状：条目按裁决结果**分组**下发（`ContextManifest.as_dict`）。 */
function serverManifest(groups: Record<string, unknown[]>, extra: Record<string, unknown> = {}) {
  return {
    manifest_version: 'context-plan-v1',
    total_budget: 8000,
    total_used: 900,
    ...extra,
    ...groups,
  }
}

function overlayEntry(overrides: Record<string, unknown> = {}) {
  return {
    source_type: `${DRAFT_OVERLAY_SOURCE_PREFIX}:workpaper`,
    source_id: WP_ID,
    label: '当前未保存草稿（底稿 B1-1 货币资金）',
    content_hash: 'sha256:abc123',
    baseline_version: BASELINE,
    ...overrides,
  }
}

describe('readDraftOverlayNotice — 从分组 manifest 里认出 overlay 条目', () => {
  it('included 条目 → 状态 included，带 hash 与基线版本', () => {
    const notice = readDraftOverlayNotice(
      serverManifest({ included: [overlayEntry({ status: 'included', used_tokens: 123 })] }),
    )
    expect(notice).not.toBeNull()
    expect(notice!.status).toBe('included')
    expect(notice!.baselineVersion).toBe(BASELINE)
    expect(notice!.contentHash).toBe('sha256:abc123')
    expect(notice!.label).toContain('当前未保存草稿')
  })

  it('denied 条目在 denied 分组里也能认出（只按顶层键找会漏掉这一类）', () => {
    const notice = readDraftOverlayNotice(
      serverManifest({
        denied: [overlayEntry({ status: 'denied', reason: '草稿基于旧版本 v…，请先保存或刷新' })],
      }),
    )
    expect(notice!.status).toBe('denied')
    expect(notice!.reason).toContain('请先保存或刷新')
  })

  it('没有 overlay 条目 → null（本轮没提交草稿，消息上不该多一行标注）', () => {
    expect(
      readDraftOverlayNotice(
        serverManifest({
          included: [{ source_type: 'workpaper', source_id: WP_ID, status: 'included', label: '审定表' }],
        }),
      ),
    ).toBeNull()
  })

  it('非对象 / 空输入 → null（不抛）', () => {
    for (const raw of [null, undefined, [], 'x', 0]) {
      expect(readDraftOverlayNotice(raw)).toBeNull()
    }
  })

  it('条目自带 status 时以它为准（分组键只是兜底）', () => {
    // 服务端把 trimmed 放在 included 组里不常见，但分组与 status 冲突时
    // 必须以条目自报的状态为准（它才是裁决结果）。
    const notice = readDraftOverlayNotice(
      serverManifest({ included: [overlayEntry({ status: 'trimmed' })] }),
    )
    expect(notice!.status).toBe('trimmed')
  })
})

// ---------------------------------------------------------------------------
// 消息标注文案（需求 2.5 / design §5.5）
// ---------------------------------------------------------------------------

function notice(overrides: Partial<ChatDraftOverlayNotice> = {}): ChatDraftOverlayNotice {
  return {
    status: 'included',
    label: '当前未保存草稿（底稿 B1-1 货币资金）',
    reason: '',
    baselineVersion: BASELINE,
    contentHash: 'sha256:abc123',
    ...overrides,
  }
}

describe('draftOverlayNoticeText — 全中文、可读', () => {
  it('included → 明确说明本轮纳入了未保存草稿，并带上版本', () => {
    const text = draftOverlayNoticeText(notice())
    expect(text).toContain('已纳入当前未保存草稿')
    expect(text).toContain('2026-11-15 10:00:00 UTC')
    expect(text).toMatch(CJK_RE)
  })

  it('denied → 原样展示后端的中文整句原因（含汉字、不弹窗）', () => {
    const reason = '草稿基于旧版本 v2026-11-15T10:00:00+00:00，当前 v2026-11-15T12:00:00+00:00，请先保存或刷新'
    const text = draftOverlayNoticeText(notice({ status: 'denied', reason }))
    expect(text).toContain('当前未保存草稿未纳入')
    expect(text).toContain('请先保存或刷新')
    expect(text).toMatch(CJK_RE)
    // 不能把 status / 英文码这类内部标识直接露给用户
    expect(text).not.toContain('denied')
  })

  it('denied 但后端没给中文原因 → 用中文兜底，绝不显示英文码', () => {
    const text = draftOverlayNoticeText(notice({ status: 'denied', reason: 'version_mismatch' }))
    expect(text).toContain('当前未保存草稿未纳入')
    expect(text).not.toContain('version_mismatch')
    expect(text).toMatch(CJK_RE)
  })

  it('trimmed 的英文码 budget_exceeded 换成中文，且说明是按预算裁剪', () => {
    const text = draftOverlayNoticeText(notice({ status: 'trimmed', reason: 'budget_exceeded' }))
    expect(text).toContain('裁剪')
    expect(text).not.toContain('budget_exceeded')
    expect(text).toMatch(CJK_RE)
  })

  it('unavailable 的英文码 budget_exceeded 也换成中文', () => {
    const text = draftOverlayNoticeText(notice({ status: 'unavailable', reason: 'budget_exceeded' }))
    expect(text).toContain('当前未保存草稿未纳入')
    expect(text).toContain('预算不足')
    expect(text).not.toContain('budget_exceeded')
  })

  it('四种状态的文案互不相同（不会被折叠成同一句）', () => {
    const texts = (['included', 'trimmed', 'denied', 'unavailable'] as const).map((status) =>
      draftOverlayNoticeText(notice({ status, reason: status === 'included' ? '' : 'budget_exceeded' })),
    )
    expect(new Set(texts).size).toBe(4)
  })
})
