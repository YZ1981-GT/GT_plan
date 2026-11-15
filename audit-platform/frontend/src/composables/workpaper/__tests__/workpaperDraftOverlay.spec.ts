/**
 * 宿主未保存草稿访问器守卫（spec chat-host-draft-overlay / Task 4）。
 *
 * Requirements: 2.2（纳入时携带 host_id / baseline_version / content_length）、
 *               6.1（无未保存修改时不提供草稿）、6.3（草稿基于旧版本不得静默使用）。
 *
 * ## 判据取向
 *
 * * 「无未保存修改 → `null`」用**保存前后同一访问器**的两态证明（阳性对照 + 阴性对照），
 *   而不是只断言 `null`（那样实现恒返回 `null` 也能过）。
 * * 「基线冻结在打开时」用**让版本前进再取值**证明：值必须仍是打开时那一版。
 * * 「与后端版本口径逐字一致」用**跨语言对账**：直接读 `draft_overlay.py` 的常量与
 *   `normalize_business_version` 源码，再拿同一批输入两侧比对（含微秒、时区、小写 z）。
 */

import { effectScope, nextTick, ref } from 'vue'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import {
  DRAFT_OVERLAY_HOST_TYPES,
  MAX_DRAFT_OVERLAY_CHARS,
  WORKPAPER_BUSINESS_VERSION_SOURCE,
  clearHtmlDraftSources,
  clearWorkpaperDraftAccessors,
  hasWorkpaperDraftOverlay,
  normalizeBusinessVersion,
  publishHtmlDraftSource,
  readHtmlDraft,
  readWorkpaperDraftOverlay,
  registerWorkpaperDraftAccessor,
  useWorkpaperDraftAccessor,
  workpaperDraftAccessorOf,
  type WorkpaperDraftAccessor,
} from '../workpaperDraftOverlay'

const WP_ID = '11111111-1111-4111-8111-111111111111'
const OTHER_WP_ID = '22222222-2222-4222-8222-222222222222'

/** 仓库根：`audit-platform/frontend/src/composables/workpaper/__tests__` 上溯 5 层。 */
function repoRoot(): string {
  return resolve(__dirname, '../../../../../../')
}

function backendOverlaySource(): string {
  return readFileSync(
    resolve(repoRoot(), 'backend/app/services/ai_chat/draft_overlay.py'),
    'utf-8',
  ).replace(/\r\n/g, '\n')
}

afterEach(() => {
  clearWorkpaperDraftAccessors()
  clearHtmlDraftSources()
})

// ---------------------------------------------------------------------------
// 版本归一：与后端 normalize_business_version 逐条对账
// ---------------------------------------------------------------------------

describe('normalizeBusinessVersion — 与后端逐条一致（假冲突会把新鲜草稿判成过期）', () => {
  /**
   * 黄金表：右侧期望值由**后端真实实现**算出（`python -c` 跑
   * `app.services.ai_chat.draft_overlay.normalize_business_version` 得到，见各条注释）。
   * 只钉生产会出现的形态 + 几处刻意对齐的边界（小写 z / 秒 60 / 假日期）。
   */
  const GOLDEN: Array<[unknown, string]> = [
    // 空值：后端 `if raw is None: return ""` / 空白 strip 后空 → ""
    [null, ''],
    [undefined, ''],
    ['', ''],
    ['   ', ''],
    // 同一时刻的不同写法必须归一到同一串（否则每次提问都「假冲突」）
    ['2026-11-15T10:00:00+00:00', '2026-11-15T10:00:00+00:00'],
    ['2026-11-15T10:00:00Z', '2026-11-15T10:00:00+00:00'],
    ['2026-11-15T10:00:00', '2026-11-15T10:00:00+00:00'],
    ['2026-11-15 10:00:00', '2026-11-15T10:00:00+00:00'],
    ['2026-11-15T18:00:00+08:00', '2026-11-15T10:00:00+00:00'],
    ['2026-11-15T02:00:00-08:00', '2026-11-15T10:00:00+00:00'],
    ['2026-11-15T10:00:00+0800', '2026-11-15T02:00:00+00:00'],
    ['2027-01-01T00:00:00+08:00', '2026-12-31T16:00:00+00:00'],
    // 微秒：非 0 时 Python isoformat 恒 6 位（补零 / 截断），为 0 时不写小数点段
    ['2026-11-15T10:00:00.123456+00:00', '2026-11-15T10:00:00.123456+00:00'],
    ['2026-11-15T10:00:00.123+00:00', '2026-11-15T10:00:00.123000+00:00'],
    ['2026-11-15T10:00:00.1+00:00', '2026-11-15T10:00:00.100000+00:00'],
    ['2026-11-15T10:00:00.000000+00:00', '2026-11-15T10:00:00+00:00'],
    ['2026-12-31T23:59:59.999999+00:00', '2026-12-31T23:59:59.999999+00:00'],
    // 认不出的形状原样返回（后端 `except ValueError: return text`）
    ['not-a-timestamp', 'not-a-timestamp'],
    // 🔴 小写 z：Python `fromisoformat` 只认大写 ⇒ 后端原样返回，前端也必须原样返回
    ['2026-11-15T10:00:00z', '2026-11-15T10:00:00z'],
    // 🔴 秒 60 / 假日期：Python ValueError ⇒ 原样返回
    ['2026-11-15T10:00:60+00:00', '2026-11-15T10:00:60+00:00'],
    ['2026-02-30T00:00:00+00:00', '2026-02-30T00:00:00+00:00'],
    ['2026-13-01T00:00:00+00:00', '2026-13-01T00:00:00+00:00'],
    // 首尾空白去掉（后端 `str(raw).strip()`）
    ['  2026-11-15T10:00:00Z  ', '2026-11-15T10:00:00+00:00'],
  ]

  it.each(GOLDEN)('%s → %s', (input, expected) => {
    expect(normalizeBusinessVersion(input)).toBe(expected)
  })

  it('微秒逐位保留（不能被 Date 截成毫秒）', () => {
    // 🔴 用 new Date(...).toISOString() 会把 .123456 变成 .123000
    expect(normalizeBusinessVersion('2026-11-15T10:00:00.123456+00:00'))
      .toBe('2026-11-15T10:00:00.123456+00:00')
    expect(normalizeBusinessVersion('2026-11-15T10:00:00.123456Z'))
      .not.toContain('.123000')
  })

  it('幂等：归一结果再归一不变', () => {
    for (const [input] of GOLDEN) {
      const once = normalizeBusinessVersion(input)
      expect(normalizeBusinessVersion(once)).toBe(once)
    }
  })
})

describe('后端常量镜像 — 直接读 Python 源码对账（改一边不改另一边必红）', () => {
  const source = backendOverlaySource()

  it('WORKPAPER_BUSINESS_VERSION_SOURCE 与后端常量逐字一致', () => {
    const matched = /^WORKPAPER_BUSINESS_VERSION_SOURCE\s*=\s*"([^"]+)"/m.exec(source)
    expect(matched, '后端 draft_overlay.py 里找不到 WORKPAPER_BUSINESS_VERSION_SOURCE').not.toBeNull()
    expect(WORKPAPER_BUSINESS_VERSION_SOURCE).toBe(matched![1])
    // 权威列就是 working_paper.updated_at（design §3 步骤 6 的取数口径）
    expect(WORKPAPER_BUSINESS_VERSION_SOURCE).toBe('working_paper.updated_at')
  })

  it('MAX_DRAFT_OVERLAY_CHARS 与后端上限一致', () => {
    const matched = /^MAX_DRAFT_OVERLAY_CHARS\s*=\s*([\d_]+)/m.exec(source)
    expect(matched).not.toBeNull()
    expect(MAX_DRAFT_OVERLAY_CHARS).toBe(Number(matched![1].replace(/_/g, '')))
  })

  it('DRAFT_OVERLAY_HOST_TYPES 与后端取值域一致（第一批只 workpaper）', () => {
    const matched = /^DRAFT_OVERLAY_HOST_TYPES[^=]*=\s*frozenset\(\{([^}]*)\}\)/m.exec(source)
    expect(matched, '后端 DRAFT_OVERLAY_HOST_TYPES 形状变了，须同步本用例').not.toBeNull()
    const backend = [...matched![1].matchAll(/HostType\.(\w+)/g)].map((m) => m[1]).sort()
    expect([...DRAFT_OVERLAY_HOST_TYPES].sort()).toEqual(backend)
    expect([...DRAFT_OVERLAY_HOST_TYPES]).toEqual(['workpaper'])
  })

  it('后端确实按 UTC + isoformat 归一（前端口径不是自创）', () => {
    // 归一函数体必须同时出现 astimezone(timezone.utc) 与 isoformat()，
    // 否则前端按「UTC + 秒级 isoformat」镜像就失去依据。
    const body = source.slice(source.indexOf('def normalize_business_version'))
    const fnBody = body.slice(0, body.indexOf('def versions_match'))
    expect(fnBody).toContain('astimezone(timezone.utc)')
    expect(fnBody).toContain('.isoformat()')
  })

  it('后端 versions_match 对空基线是 fail-closed（前端因此先挡住空版本）', () => {
    const body = source.slice(source.indexOf('def versions_match'))
    const fnBody = body.slice(0, body.indexOf('class DraftOverlayDecision'))
    expect(fnBody).toMatch(/if not baseline:\s*\n\s*return False/)
  })
})

// ---------------------------------------------------------------------------
// 访问器注册表
// ---------------------------------------------------------------------------

function makeAccessor(overrides: Partial<WorkpaperDraftAccessor> = {}): WorkpaperDraftAccessor {
  return {
    wpId: () => WP_ID,
    hasUnsaved: () => true,
    currentDraftContent: () => 'B1-1 审定表：应收账款 1,200,000（未保存）',
    openedBaselineVersion: () => '2026-11-15T10:00:00+00:00',
    ...overrides,
  }
}

describe('访问器注册表 — 按 wpId 查找，注销只删自己那条', () => {
  it('没有登记时返回 null（面板先于编辑器挂载）', () => {
    expect(workpaperDraftAccessorOf(WP_ID)).toBeNull()
    expect(workpaperDraftAccessorOf(null)).toBeNull()
    expect(workpaperDraftAccessorOf(undefined)).toBeNull()
    expect(workpaperDraftAccessorOf('')).toBeNull()
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })

  it('按 wpId 精确匹配，不串到别的底稿', () => {
    const a = makeAccessor()
    const b = makeAccessor({ wpId: () => OTHER_WP_ID, content: '别处的内容' })
    registerWorkpaperDraftAccessor(a)
    registerWorkpaperDraftAccessor(b)
    expect(workpaperDraftAccessorOf(WP_ID)).toBe(a)
    expect(workpaperDraftAccessorOf(OTHER_WP_ID)).toBe(b)
    expect(readWorkpaperDraftOverlay(WP_ID)?.content).toBe(a.currentDraftContent())
  })

  it('注销只删自己那条：先注销的不会把后来者一起删掉', () => {
    const first = makeAccessor({ currentDraftContent: () => '第一份' })
    const second = makeAccessor({ currentDraftContent: () => '第二份' })
    const unregisterFirst = registerWorkpaperDraftAccessor(first)
    registerWorkpaperDraftAccessor(second)
    // 同一 wpId 后来者覆盖读取结果（最新挂载的编辑器实例）
    expect(readWorkpaperDraftOverlay(WP_ID)?.content).toBe('第二份')

    unregisterFirst()
    expect(workpaperDraftAccessorOf(WP_ID)).toBe(second)
    expect(readWorkpaperDraftOverlay(WP_ID)?.content).toBe('第二份')
  })

  it('全部注销后回到 null', () => {
    const unregister = registerWorkpaperDraftAccessor(makeAccessor())
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(true)
    unregister()
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 无未保存修改 → null（任务正文的验收判据：改一处不保存 → 有值；保存后 → null）
// ---------------------------------------------------------------------------

describe('readWorkpaperDraftOverlay — 保存前后两态（改一处不保存 → 有值；保存后 → null）', () => {
  it('有未保存修改时给出正文 + 归一基线 + 长度', () => {
    const dirty = ref(true)
    const content = ref('B1-1 审定表：应收账款 1,200,000（未保存）')
    registerWorkpaperDraftAccessor({
      wpId: () => WP_ID,
      hasUnsaved: () => dirty.value,
      currentDraftContent: () => (dirty.value ? content.value : null),
      openedBaselineVersion: () => '2026-11-15T10:00:00Z',
    })

    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(true)
    const overlay = readWorkpaperDraftOverlay(WP_ID)
    expect(overlay).not.toBeNull()
    expect(overlay!.content).toBe('B1-1 审定表：应收账款 1,200,000（未保存）')
    // 归一成后端可比形态（Z → +00:00）
    expect(overlay!.baselineVersion).toBe('2026-11-15T10:00:00+00:00')
    expect(overlay!.contentLength).toBe(overlay!.content.length)

    // 保存完成（dirty → false）⇒ 不再提供草稿
    dirty.value = false
    content.value = ''
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })

  it('编辑器报「没有未保存修改」时不读正文（省掉整簿序列化）', () => {
    let collected = 0
    registerWorkpaperDraftAccessor({
      wpId: () => WP_ID,
      hasUnsaved: () => false,
      currentDraftContent: () => {
        collected += 1
        return '不该被取到的正文'
      },
      openedBaselineVersion: () => '2026-11-15T10:00:00+00:00',
    })
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(collected).toBe(0)
  })

  it.each([
    ['空串', ''],
    ['全空白', '   \n\t  '],
  ])('正文为%s时不给 overlay（后端会 422，前端先挡住）', (_label, body) => {
    registerWorkpaperDraftAccessor(makeAccessor({ currentDraftContent: () => body }))
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })

  it('基线版本为空时不给 overlay（后端 versions_match 对空串 fail-closed）', () => {
    registerWorkpaperDraftAccessor(makeAccessor({ openedBaselineVersion: () => null }))
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()

    clearWorkpaperDraftAccessors()
    registerWorkpaperDraftAccessor(makeAccessor({ openedBaselineVersion: () => '' }))
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })

  it('正文超过后端上限时不给 overlay（后端超限 422、不裁剪）', () => {
    const atLimit = 'a'.repeat(MAX_DRAFT_OVERLAY_CHARS)
    registerWorkpaperDraftAccessor(makeAccessor({ currentDraftContent: () => atLimit }))
    expect(readWorkpaperDraftOverlay(WP_ID)?.contentLength).toBe(MAX_DRAFT_OVERLAY_CHARS)

    clearWorkpaperDraftAccessors()
    const overLimit = 'a'.repeat(MAX_DRAFT_OVERLAY_CHARS + 1)
    registerWorkpaperDraftAccessor(makeAccessor({ currentDraftContent: () => overLimit }))
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 基线冻结（这条是本功能的核心：跟着服务端版本走 = 过期检测失效）
// ---------------------------------------------------------------------------

describe('useWorkpaperDraftAccessor — openedBaselineVersion 冻结在打开时', () => {
  it('服务端版本前进后基线不变（否则过期检测永远通过）', async () => {
    const version = ref<unknown>('2026-11-15T10:00:00+00:00')
    const scope = effectScope()
    scope.run(() => {
      useWorkpaperDraftAccessor({
        wpId: () => WP_ID,
        currentBusinessVersion: () => version.value,
        isDirty: () => true,
        collectContent: () => '未保存正文',
      })
    })

    expect(workpaperDraftAccessorOf(WP_ID)?.openedBaselineVersion())
      .toBe('2026-11-15T10:00:00+00:00')

    // 保存后 wpDetail 被重取 ⇒ updated_at 前进
    version.value = '2026-11-15T11:30:00+00:00'
    await nextTick()
    expect(workpaperDraftAccessorOf(WP_ID)?.openedBaselineVersion())
      .toBe('2026-11-15T10:00:00+00:00')

    // 面板侧读到的基线也必须是打开时那一版（服务端据此判 denied）
    expect(readWorkpaperDraftOverlay(WP_ID)?.baselineVersion)
      .toBe('2026-11-15T10:00:00+00:00')
    scope.stop()
  })

  it('详情还没到时先空着，第一次拿到真值即冻结', async () => {
    const version = ref<unknown>(null)
    const scope = effectScope()
    scope.run(() => {
      useWorkpaperDraftAccessor({
        wpId: () => WP_ID,
        currentBusinessVersion: () => version.value,
        isDirty: () => true,
        collectContent: () => '未保存正文',
      })
    })

    // 详情未到 ⇒ 基线为空 ⇒ 面板拿不到 overlay（fail-closed）
    expect(workpaperDraftAccessorOf(WP_ID)?.openedBaselineVersion()).toBeNull()
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()

    version.value = '2026-11-15T10:00:00Z'
    await nextTick()
    expect(workpaperDraftAccessorOf(WP_ID)?.openedBaselineVersion())
      .toBe('2026-11-15T10:00:00+00:00')

    // 冻结后不再跟随
    version.value = '2026-11-16T00:00:00Z'
    await nextTick()
    expect(workpaperDraftAccessorOf(WP_ID)?.openedBaselineVersion())
      .toBe('2026-11-15T10:00:00+00:00')
    scope.stop()
  })

  it('scope 停止后自动注销（切底稿/离页不留悬挂访问器）', () => {
    const scope = effectScope()
    scope.run(() => {
      useWorkpaperDraftAccessor({
        wpId: () => WP_ID,
        currentBusinessVersion: () => '2026-11-15T10:00:00+00:00',
        isDirty: () => true,
        collectContent: () => '未保存正文',
      })
    })
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(true)
    scope.stop()
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// HTML 侧草稿源汇总
// ---------------------------------------------------------------------------

describe('readHtmlDraft — 汇总 sheet 宿主的未保存内容', () => {
  it('没有源 / 源不脏时都报「无」', () => {
    expect(readHtmlDraft(WP_ID)).toEqual({ content: null, hasUnsaved: false })
    publishHtmlDraftSource(WP_ID, {
      label: 'stub',
      hasUnsaved: () => false,
      currentDraftContent: () => '不该被取到',
    })
    expect(readHtmlDraft(WP_ID)).toEqual({ content: null, hasUnsaved: false })
  })

  it('多个源按登记顺序拼接，完全相同的片段只算一次', () => {
    publishHtmlDraftSource(WP_ID, {
      label: 'sheet-a',
      hasUnsaved: () => true,
      currentDraftContent: () => '{"item_id":"K1-1","remark":"100"}',
    })
    publishHtmlDraftSource(WP_ID, {
      label: 'sheet-b',
      hasUnsaved: () => true,
      currentDraftContent: () => '{"item_id":"K1-2","remark":"200"}',
    })
    // 重复登记同一份正文（切 sheet 时新旧组件短暂共存）
    publishHtmlDraftSource(WP_ID, {
      label: 'sheet-a-dup',
      hasUnsaved: () => true,
      currentDraftContent: () => '{"item_id":"K1-1","remark":"100"}',
    })
    const merged = readHtmlDraft(WP_ID)
    expect(merged.hasUnsaved).toBe(true)
    expect(merged.content).toBe('{"item_id":"K1-1","remark":"100"}\n{"item_id":"K1-2","remark":"200"}')
  })

  it('别的底稿的源不参与', () => {
    publishHtmlDraftSource(OTHER_WP_ID, {
      label: 'other',
      hasUnsaved: () => true,
      currentDraftContent: () => '别处',
    })
    expect(readHtmlDraft(WP_ID)).toEqual({ content: null, hasUnsaved: false })
    expect(readHtmlDraft(OTHER_WP_ID).content).toBe('别处')
  })

  it('注销只删自己那条', () => {
    const unregister = publishHtmlDraftSource(WP_ID, {
      label: 'first',
      hasUnsaved: () => true,
      currentDraftContent: () => '第一份',
    })
    publishHtmlDraftSource(WP_ID, {
      label: 'second',
      hasUnsaved: () => true,
      currentDraftContent: () => '第二份',
    })
    expect(readHtmlDraft(WP_ID).content).toBe('第一份\n第二份')
    unregister()
    expect(readHtmlDraft(WP_ID).content).toBe('第二份')
  })
})

// ---------------------------------------------------------------------------
// 面板侧统一读取（useAiHostContext）
// ---------------------------------------------------------------------------

describe('useAiHostContext.readHostDraftOverlay — 只对可用底稿宿主读取', () => {
  it('底稿宿主且可用时透出 overlay', async () => {
    const { buildWorkpaperHost, readHostDraftOverlay, hostHasUnsavedDraft } =
      await import('../../useAiHostContext')
    registerWorkpaperDraftAccessor(makeAccessor())
    const host = buildWorkpaperHost({
      wpId: WP_ID,
      projectId: '33333333-3333-4333-8333-333333333333',
      auditYear: 2025,
    })
    expect(hostHasUnsavedDraft(host)).toBe(true)
    expect(readHostDraftOverlay(host)?.content).toBe(makeAccessor().currentDraftContent())
  })

  it.each([
    ['报表宿主', 'report'],
    ['全局知识模式', 'global'],
    ['不可用宿主', 'unavailable'],
  ])('%s不读草稿（没有 workpaper 宿主就没有可绑定的草稿）', async (_label, kind) => {
    const { buildGlobalKnowledgeHost, buildReportHost, buildWorkpaperHost, readHostDraftOverlay, hostHasUnsavedDraft } =
      await import('../../useAiHostContext')
    registerWorkpaperDraftAccessor(makeAccessor())
    const projectId = '33333333-3333-4333-8333-333333333333'
    const request =
      kind === 'report'
        ? buildReportHost({ reportType: 'balance_sheet', projectId, year: 2025 })
        : kind === 'global'
          ? buildGlobalKnowledgeHost()
          : buildWorkpaperHost({ wpId: '', projectId })
    expect(readHostDraftOverlay(request)).toBeNull()
    expect(hostHasUnsavedDraft(request)).toBe(false)
  })

  it('宿主不可用时即使编辑器登记了也不读', async () => {
    const { buildWorkpaperHost, readHostDraftOverlay } = await import('../../useAiHostContext')
    registerWorkpaperDraftAccessor(makeAccessor())
    // 项目为空 ⇒ adapter 判不可用
    expect(readHostDraftOverlay(buildWorkpaperHost({ wpId: WP_ID, projectId: '' }))).toBeNull()
  })
})
