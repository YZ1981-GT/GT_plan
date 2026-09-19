// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 35
//
// commit 后 `workpaper.content.updated` → 前端刷新的**行为侧**判据。
//
// Validates: Requirements 11.9, 13.1, 13.2, 13.3, 13.4
//
// ═══ 判据取向 ═══
//
// 每一条都落在「真实调用后可观测的事实」上：reload 钩子被调了几次、参数是什么、
// 服务端 revision 计数器动没动、返回的 outcome 是哪一种、失败码是哪一个。
// 没有一条是「某个符号存在」或「抛了就算过」。
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const mockSubscribe = vi.fn()
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: (...args: unknown[]) => mockSubscribe(...args),
}))

import {
  WP_CONTENT_EVENT_CONSUMER_KEYS,
  WP_CONTENT_EVENT_DESIGN_KEYS,
  WP_CONTENT_EVENT_REQUIRED_KEYS,
  WP_CONTENT_REFRESH_ACTION_HINT,
  WP_CONTENT_REFRESH_STATUS_TEXT,
  WP_CONTENT_UPDATED_EVENT_NAME,
  assertContentRefreshTextDisjoint,
  contentUpdateDedupeKey,
  parseContentUpdatedEvent,
  unwrapContentEventWire,
  useWorkpaperContentRefresh,
  type WorkpaperContentRefreshOutcome,
} from '../workpaperSyncContentRefresh'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'

const UUID = (n: number): string => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number): string =>
  String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

const PROJECT = UUID(101)
const WP = UUID(102)
const OTHER_WP = UUID(103)

/**
 * 一份**逐字对齐后端 `ContentMutationService._event_payload()`** 的 payload。
 *
 * 刻意带上 `representation_id` / `requires_client_refresh` 等扩展键：Requirement 13.2
 * 的「不得丢失 extra」只有在 payload 里真有解析器不认识的键时才可被 falsify。
 */
function payloadFixture(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    wp_id: WP,
    project_id: PROJECT,
    revision: 12,
    operation_id: UUID(30),
    source: 'onlyoffice',
    adapter_id: 'g7.disclosure.listed',
    file_sha256: DIGEST(1),
    entry_id: 'xlsx/g7/disclosure/g7-tab-disclosure-listed',
    content_version_id: UUID(23),
    projection_sha256: DIGEST(2),
    representation_id: UUID(24),
    representation_generation: 2,
    definition_bundle_id: UUID(25),
    definition_bundle_sha256: DIGEST(3),
    authority_model: 'projection_contract',
    adapter_build_digest: DIGEST(4),
    requires_client_refresh: false,
    content_revision_advanced: true,
    reason: 'content_commit',
    __event_id: UUID(90),
    ...over,
  }
}

/** `GET /events/stream` 真实下发的 typed 信封（业务键在 `extra` 里）。 */
function sseEnvelope(payload: Record<string, unknown> = payloadFixture()): Record<string, unknown> {
  return {
    event_type: WP_CONTENT_UPDATED_EVENT_NAME,
    project_id: PROJECT,
    year: null,
    account_codes: null,
    entry_group_id: null,
    batch_id: null,
    extra: payload,
  }
}

interface Harness {
  refresh: ReturnType<typeof useWorkpaperContentRefresh>
  reload: ReturnType<typeof vi.fn>
  /** 被测代码**不该**能动的服务端事实。只有 `commit()` 会推进它。 */
  serverRevision: () => number
  commit: () => void
  setDirty: (next: boolean) => void
  setLoaded: (next: number | null) => void
}

function harness(
  options: {
    dirty?: boolean
    loadedRevision?: number | null
    reload?: (minimumRevision: number) => Promise<void>
  } = {},
): Harness {
  let dirty = options.dirty === true
  let loaded = options.loadedRevision === undefined ? 11 : options.loadedRevision
  let serverRevision = 12
  const reload = vi.fn(options.reload ?? (async () => {}))
  const refresh = useWorkpaperContentRefresh({
    wpId: ref(WP),
    projectId: ref(PROJECT),
    loadedRevision: () => loaded,
    isDirty: () => dirty,
    reload: reload as unknown as (minimumRevision: number) => Promise<void>,
    subscribe: () => ({ close: vi.fn() }),
  })
  return {
    refresh,
    reload,
    serverRevision: () => serverRevision,
    commit: () => {
      serverRevision += 1
    },
    setDirty: (next) => {
      dirty = next
    },
    setLoaded: (next) => {
      loaded = next
    },
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// A. 信封归一（Property 53 的消费侧 + 本任务修掉的真实缺陷）
// ═══════════════════════════════════════════════════════════════════════════

describe('typed SSE 信封归一', () => {
  it('剥掉信封后取到内层业务 payload，扁平 payload 原样返回', () => {
    const flat = payloadFixture()
    expect(unwrapContentEventWire(sseEnvelope(flat))).toEqual({
      payload: flat,
      envelope: 'typed_sse',
      eventName: WP_CONTENT_UPDATED_EVENT_NAME,
    })
    expect(unwrapContentEventWire(flat)).toEqual({
      payload: flat,
      envelope: 'flat_payload',
      eventName: null,
    })
  })

  it('只有 extra 而没有 event_type 时不剥层（避免误剥一个恰好带 extra 的 payload）', () => {
    const weird = { wp_id: WP, revision: 12, extra: { wp_id: OTHER_WP, revision: 99 } }
    const result = unwrapContentEventWire(weird)
    expect(result.envelope).toBe('flat_payload')
    expect(result.payload).toEqual(weird)
    // 归一后仍按顶层取键 ⇒ 不会拿到内层那个别的 wp
    expect(contentUpdateDedupeKey(weird)).toBe(`${WP}|12`)
  })

  it('🔴 真实 SSE 信封必须能算出 wp_id + revision 去重键（AC 11.9 的修点）', () => {
    // 修点前：`contentUpdateDedupeKey` 只读顶层 ⇒ 这里恒为 null，去重从未生效。
    expect(contentUpdateDedupeKey(sseEnvelope())).toBe(`${WP}|12`)
    expect(contentUpdateDedupeKey(sseEnvelope())).not.toContain(UUID(30))
  })

  it('扁平形态与信封形态算出同一个键（两条到达路径不得各算一份）', () => {
    expect(contentUpdateDedupeKey(payloadFixture())).toBe(contentUpdateDedupeKey(sseEnvelope()))
  })

  it('拿不到 wp_id / revision 时返回 null 而不是编一个键', () => {
    expect(contentUpdateDedupeKey({ revision: 12 })).toBeNull()
    expect(contentUpdateDedupeKey({ wp_id: WP })).toBeNull()
    expect(contentUpdateDedupeKey(null)).toBeNull()
    expect(contentUpdateDedupeKey(sseEnvelope({ wp_id: WP }))).toBeNull()
  })

  it('Task 31 的 tracker 与本模块共用同一个键实现（不是第二份口径）', async () => {
    const tracker = await import('../workpaperSyncOperationTracker')
    expect(tracker.WORKPAPER_CONTENT_UPDATED_EVENT).toBe(WP_CONTENT_UPDATED_EVENT_NAME)
    expect(tracker.contentUpdateDedupeKey(sseEnvelope())).toBe(`${WP}|12`)
    expect(tracker.contentUpdateDedupeKey(payloadFixture())).toBe(
      contentUpdateDedupeKey(payloadFixture()),
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. Property 53：payload 逐项不丢（含 extra）
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 53：解析后 payload 逐项等于收到的那份', () => {
  it('两种信封都保留**整份** payload，含解析器不认识的扩展键', () => {
    const source = payloadFixture()
    for (const wire of [source, sseEnvelope(source)]) {
      const parsed = parseContentUpdatedEvent(wire)
      // 逐键相等（不是「键都在」这种包含式判据）
      expect(Object.keys(parsed.payload).sort()).toEqual(Object.keys(source).sort())
      for (const [key, value] of Object.entries(source)) {
        expect(parsed.payload[key]).toEqual(value)
      }
      // 解析器不认识的扩展键也必须在
      for (const extension of [
        'representation_id',
        'representation_generation',
        'definition_bundle_sha256',
        'adapter_build_digest',
        'requires_client_refresh',
        'projection_sha256',
      ]) {
        expect(parsed.payload).toHaveProperty(extension)
      }
    }
  })

  it('design §outbox 的 6 个业务字段逐项投影正确', () => {
    const parsed = parseContentUpdatedEvent(sseEnvelope())
    expect({
      wpId: parsed.wpId,
      revision: parsed.revision,
      operationId: parsed.operationId,
      source: parsed.source,
      adapterId: parsed.adapterId,
      fileSha256: parsed.fileSha256,
    }).toEqual({
      wpId: WP,
      revision: 12,
      operationId: UUID(30),
      source: 'onlyoffice',
      adapterId: 'g7.disclosure.listed',
      fileSha256: DIGEST(1),
    })
    expect(parsed.eventId).toBe(UUID(90))
    expect(parsed.envelope).toBe('typed_sse')
  })

  it('必填键集 = design 7 键 + 消费侧 4 键，两段不重叠', () => {
    expect(WP_CONTENT_EVENT_DESIGN_KEYS).toHaveLength(7)
    expect(WP_CONTENT_EVENT_CONSUMER_KEYS).toHaveLength(4)
    expect(WP_CONTENT_EVENT_REQUIRED_KEYS).toHaveLength(11)
    const overlap = WP_CONTENT_EVENT_DESIGN_KEYS.filter((key) =>
      (WP_CONTENT_EVENT_CONSUMER_KEYS as readonly string[]).includes(key),
    )
    expect(overlap).toEqual([])
  })

  it('纯表示升级 payload（operation_id=null / adapter 有值）也能解析', () => {
    const parsed = parseContentUpdatedEvent(
      sseEnvelope(
        payloadFixture({
          operation_id: null,
          source: 'definition_upgrade',
          reason: 'definition_upgrade',
          content_revision_advanced: false,
        }),
      ),
    )
    expect(parsed.operationId).toBeNull()
    expect(parsed.contentRevisionAdvanced).toBe(false)
    expect(parsed.reason).toBe('definition_upgrade')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. 拒绝分型：每个码互不相同且各自可达
// ═══════════════════════════════════════════════════════════════════════════

describe('拒绝分型', () => {
  function codeOf(wire: unknown): string {
    try {
      parseContentUpdatedEvent(wire)
    } catch (error) {
      expect(error).toBeInstanceOf(WorkpaperSyncContractError)
      return (error as WorkpaperSyncContractError).code
    }
    throw new Error('本该拒绝却通过了')
  }

  it('五类形态各打各的码，五个码互不相同', () => {
    const codes = {
      notObject: codeOf('not-an-object'),
      nameMismatch: codeOf({ event_type: 'workpaper.saved', extra: payloadFixture() }),
      wpId: codeOf(payloadFixture({ wp_id: '12' })),
      revision: codeOf(payloadFixture({ revision: -1 })),
      precommit: codeOf(payloadFixture({ content_version_id: null })),
    }
    expect(codes).toEqual({
      notObject: 'content_event_not_an_object',
      nameMismatch: 'content_event_name_mismatch',
      wpId: 'content_event_wp_id_invalid',
      revision: 'content_event_revision_invalid',
      precommit: 'content_event_precommit_shape',
    })
    expect(new Set(Object.values(codes)).size).toBe(5)
  })

  it('全零 content_version_id 也算 commit 前形态（事务前占位值）', () => {
    expect(codeOf(payloadFixture({ content_version_id: UUID(0) }))).toBe(
      'content_event_precommit_shape',
    )
  })

  it('缺任一必填键都打 required_key_missing，且指出缺的是哪个键', () => {
    for (const key of WP_CONTENT_EVENT_REQUIRED_KEYS) {
      const payload = payloadFixture()
      delete payload[key]
      let caught: WorkpaperSyncContractError | null = null
      try {
        parseContentUpdatedEvent(payload)
      } catch (error) {
        caught = error as WorkpaperSyncContractError
      }
      expect(caught, `缺 ${key} 却没有拒绝`).not.toBeNull()
      // wp_id / revision / content_version_id 有各自更早的专属码；其余走通用码。
      const expected =
        key === 'wp_id'
          ? 'content_event_wp_id_invalid'
          : key === 'revision'
            ? 'content_event_revision_invalid'
            : key === 'content_version_id'
              ? 'content_event_precommit_shape'
              : 'content_event_required_key_missing'
      expect(caught?.code, `缺 ${key} 时的码不对`).toBe(expected)
      if (expected === 'content_event_required_key_missing') {
        expect(caught?.message).toContain(key)
      }
    }
  })

  it('content_revision_advanced 非布尔时拒绝（分型全靠它）', () => {
    expect(codeOf(payloadFixture({ content_revision_advanced: 'true' }))).toBe(
      'content_event_required_key_missing',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. AC 11.9 去重 + 七个分支各自可达
// ═══════════════════════════════════════════════════════════════════════════

describe('去重与分支', () => {
  async function fire(h: Harness, wire: unknown): Promise<WorkpaperContentRefreshOutcome> {
    return h.refresh.handleEvent(wire)
  }

  it('同一 wp+revision 重复投递只刷新一次（Requirement 13.3）', async () => {
    const h = harness()
    const first = await fire(h, sseEnvelope())
    const second = await fire(h, sseEnvelope())
    expect(first.kind).toBe('refreshed')
    expect(second.kind).toBe('duplicate')
    expect(second.dedupeKey).toBe(`${WP}|12`)
    expect(h.reload).toHaveBeenCalledTimes(1)
    expect(h.reload).toHaveBeenCalledWith(12)
  })

  it('revision 推进必须刷新（去重不得把状态机压成一次）', async () => {
    const h = harness()
    await fire(h, sseEnvelope())
    h.setLoaded(12)
    const next = await fire(h, sseEnvelope(payloadFixture({ revision: 13 })))
    expect(next.kind).toBe('refreshed')
    expect(h.reload.mock.calls.map((call) => call[0])).toEqual([12, 13])
  })

  it('别的底稿的事件不刷新本底稿（共享连接是项目级的）', async () => {
    const h = harness()
    const outcome = await fire(h, sseEnvelope(payloadFixture({ wp_id: OTHER_WP })))
    expect(outcome.kind).toBe('other_wp')
    expect(h.reload).not.toHaveBeenCalled()
    // 别人的键不得占用本底稿的去重表
    expect(h.refresh.seenKeys()).toEqual([])
  })

  it('纯表示升级不刷新 HTML（revision 没变，投影一个字节都没动）', async () => {
    const h = harness()
    const outcome = await fire(
      h,
      sseEnvelope(payloadFixture({ content_revision_advanced: false, revision: 13 })),
    )
    expect(outcome.kind).toBe('representation_only')
    expect(h.reload).not.toHaveBeenCalled()
    expect(h.refresh.status.value).toBe('idle')
  })

  it('自己刚提交的那条事件走 stale，不自触发重载', async () => {
    const h = harness({ loadedRevision: 12 })
    const outcome = await fire(h, sseEnvelope())
    expect(outcome.kind).toBe('stale')
    expect(h.reload).not.toHaveBeenCalled()
  })

  it('形态非法的事件不进去重表（一条读不懂的事件不该把某 revision 标成已处理）', async () => {
    const h = harness()
    const bad = await fire(h, sseEnvelope(payloadFixture({ content_version_id: null })))
    expect(bad.kind).toBe('rejected')
    expect(h.refresh.seenKeys()).toEqual([])
    // 同一 revision 的**合法**事件随后到达时仍能刷新
    const good = await fire(h, sseEnvelope())
    expect(good.kind).toBe('refreshed')
    expect(h.reload).toHaveBeenCalledTimes(1)
  })

  it('七个 outcome 分支在同一个协调器上全部可达', async () => {
    const h = harness()
    const kinds: string[] = []
    kinds.push((await fire(h, 'garbage')).kind)
    kinds.push((await fire(h, sseEnvelope(payloadFixture({ wp_id: OTHER_WP })))).kind)
    kinds.push(
      (await fire(h, sseEnvelope(payloadFixture({ revision: 5, content_revision_advanced: false }))))
        .kind,
    )
    kinds.push((await fire(h, sseEnvelope(payloadFixture({ revision: 10 })))).kind)
    kinds.push((await fire(h, sseEnvelope())).kind)
    kinds.push((await fire(h, sseEnvelope())).kind)
    h.setDirty(true)
    h.setLoaded(12)
    kinds.push((await fire(h, sseEnvelope(payloadFixture({ revision: 13 })))).kind)
    expect(kinds).toEqual([
      'rejected',
      'other_wp',
      'representation_only',
      'stale',
      'refreshed',
      'duplicate',
      'deferred_dirty',
    ])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// E. dirty 时不静默覆盖
// ═══════════════════════════════════════════════════════════════════════════

describe('dirty 时不静默覆盖', () => {
  it('本地有未保存修改 ⇒ 一次 reload 都不发，只落待办', async () => {
    const h = harness({ dirty: true })
    const outcome = await h.refresh.handleEvent(sseEnvelope())
    expect(outcome.kind).toBe('deferred_dirty')
    expect(h.reload).not.toHaveBeenCalled()
    expect(h.refresh.status.value).toBe('deferred_dirty')
    expect(h.refresh.pendingRevision.value).toBe(12)
    expect(h.refresh.appliedRevision.value).toBeNull()
  })

  it('暂缓期间又来更高 revision ⇒ 待办取最大值，仍不刷新', async () => {
    const h = harness({ dirty: true })
    await h.refresh.handleEvent(sseEnvelope())
    await h.refresh.handleEvent(sseEnvelope(payloadFixture({ revision: 14 })))
    expect(h.refresh.pendingRevision.value).toBe(14)
    expect(h.reload).not.toHaveBeenCalled()
  })

  it('用户显式确认后才加载，且加载到的是待办里那个 revision', async () => {
    const h = harness({ dirty: true })
    await h.refresh.handleEvent(sseEnvelope(payloadFixture({ revision: 14 })))
    h.setDirty(false)
    const outcome = await h.refresh.acceptPending()
    expect(outcome.kind).toBe('refreshed')
    expect(h.reload).toHaveBeenCalledTimes(1)
    expect(h.reload).toHaveBeenCalledWith(14)
    expect(h.refresh.status.value).toBe('synced')
    expect(h.refresh.appliedRevision.value).toBe(14)
    expect(h.refresh.pendingRevision.value).toBeNull()
  })

  it('没有待办时 acceptPending 显式拒绝，不把空操作显示成加载成功', async () => {
    const h = harness()
    await expect(h.refresh.acceptPending()).rejects.toMatchObject({
      code: 'content_refresh_no_pending_revision',
    })
    expect(h.reload).not.toHaveBeenCalled()
  })

  it('保留本地修改 ⇒ 清待办但**不**显示已最新（我们并没有加载到那个 revision）', async () => {
    const h = harness({ dirty: true })
    await h.refresh.handleEvent(sseEnvelope())
    h.refresh.dismissPending()
    expect(h.refresh.status.value).toBe('idle')
    expect(h.refresh.pendingRevision.value).toBeNull()
    expect(h.refresh.appliedRevision.value).toBeNull()
    expect(h.reload).not.toHaveBeenCalled()
    // 同一条事件重放不得再弹一次
    expect((await h.refresh.handleEvent(sseEnvelope())).kind).toBe('duplicate')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// F. Property 54：失败落可恢复态、不影响已提交内容、不产生新 revision
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 54：失败可恢复', () => {
  it('reload 抛错 ⇒ refresh_failed + 可重试 + 待办保留，服务端 revision 不动', async () => {
    const h = harness({ reload: async () => { throw new Error('网络中断') } })
    const before = h.serverRevision()
    const outcome = await h.refresh.handleEvent(sseEnvelope())
    expect(outcome.kind).toBe('refresh_failed')
    expect(outcome.errorCode).toBe('content_refresh_reload_failed')
    expect(h.refresh.status.value).toBe('refresh_failed')
    expect(h.refresh.lastFailure.value).toMatchObject({
      kind: 'refresh',
      errorCode: 'content_refresh_reload_failed',
      retryable: true,
    })
    expect(h.refresh.pendingRevision.value).toBe(12)
    expect(h.refresh.appliedRevision.value).toBeNull()
    // 「不影响已提交内容 / 不产生新 revision」：协调器没有写入口，服务端事实不动
    expect(h.serverRevision()).toBe(before)
    expect(h.refresh.lastFailure.value?.message).toContain('已提交的内容未受影响')
  })

  it('重试成功 ⇒ 落 synced 并清掉失败（不静默丢失，也不永久红）', async () => {
    let attempts = 0
    const h = harness({
      reload: async () => {
        attempts += 1
        if (attempts === 1) throw new Error('网络中断')
      },
    })
    await h.refresh.handleEvent(sseEnvelope())
    const retried = await h.refresh.retry()
    expect(retried.kind).toBe('refreshed')
    expect(attempts).toBe(2)
    expect(h.refresh.status.value).toBe('synced')
    expect(h.refresh.lastFailure.value).toBeNull()
    expect(h.refresh.appliedRevision.value).toBe(12)
  })

  it('事件形态失败与刷新失败是两类：码不相交、可重试性相反', async () => {
    const bad = harness()
    await bad.refresh.handleEvent(sseEnvelope(payloadFixture({ content_version_id: null })))
    const eventFailure = bad.refresh.lastFailure.value
    expect(eventFailure).toMatchObject({ kind: 'event', retryable: false })
    expect(bad.refresh.status.value).toBe('event_rejected')
    expect(bad.reload).not.toHaveBeenCalled()

    const failing = harness({ reload: async () => { throw new Error('boom') } })
    const refreshOutcome = await failing.refresh.handleEvent(sseEnvelope())
    const refreshFailure = failing.refresh.lastFailure.value

    expect(eventFailure?.errorCode).not.toBe(refreshFailure?.errorCode)
    expect(eventFailure?.kind).not.toBe(refreshFailure?.kind)
    // 🔴 只断言"两个码不相等"不够：把刷新失败的码换成**另一个事件类**的码，
    // 两者仍然不相等，而 UI 就再也分不清"事件读不懂"与"刷新失败"了。
    // 判据必须落在**命名空间**上，并且 outcome 与 lastFailure 两处都得对上。
    expect(eventFailure?.errorCode.startsWith('content_event_')).toBe(true)
    expect(refreshFailure?.errorCode.startsWith('content_refresh_')).toBe(true)
    expect(refreshOutcome.errorCode).toBe(refreshFailure?.errorCode)
    expect(refreshOutcome.errorCode?.startsWith('content_refresh_')).toBe(true)
    // 事件形态失败**不可重试** —— 重放同一条坏事件只会再坏一次
    await expect(bad.refresh.retry()).rejects.toMatchObject({
      code: 'content_refresh_nothing_to_retry',
    })
  })

  it('协调器的公开面里没有任何写入口（结构上不可能产生新 revision）', () => {
    const h = harness()
    const surface = Object.keys(h.refresh).sort()
    expect(surface).toEqual(
      [
        'acceptPending',
        'appliedRevision',
        'degraded',
        'dismissPending',
        'feedback',
        'handleEvent',
        'lastFailure',
        'lastUpdate',
        'outcomes',
        'pendingRevision',
        'reloadCallCount',
        'retry',
        'seenKeys',
        'start',
        'status',
        'stop',
      ].sort(),
    )
    for (const forbidden of ['commit', 'save', 'materialize', 'forcesave', 'resolve', 'rollback']) {
      expect(surface.some((name) => name.toLowerCase().includes(forbidden))).toBe(false)
    }
  })

  it('reload 调用次数与 outcome 序列一致（失败也只调一次）', async () => {
    const h = harness({ reload: async () => { throw new Error('boom') } })
    await h.refresh.handleEvent(sseEnvelope())
    expect(h.refresh.reloadCallCount.value).toBe(1)
    expect(h.reload).toHaveBeenCalledTimes(1)
    expect(h.refresh.outcomes.value.map((item) => item.kind)).toEqual(['refresh_failed'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// G. 订阅接线（AC 11.9：消费的是 commit 后耐久事件，不是进程内 debounce 事件）
// ═══════════════════════════════════════════════════════════════════════════

describe('订阅接线', () => {
  it('默认 subscribe 用 projectId + workpaper.content.updated 接共享连接', () => {
    mockSubscribe.mockReset()
    mockSubscribe.mockReturnValue({ close: vi.fn() })
    const refresh = useWorkpaperContentRefresh({
      wpId: ref(WP),
      projectId: ref(PROJECT),
      loadedRevision: () => 11,
      isDirty: () => false,
      reload: async () => {},
    })
    refresh.start()
    expect(mockSubscribe).toHaveBeenCalledTimes(1)
    const [projectId, eventName, handler, options] = mockSubscribe.mock.calls[0]
    expect(projectId).toBe(PROJECT)
    expect(eventName).toBe('workpaper.content.updated')
    expect(typeof handler).toBe('function')
    expect(typeof options.onReconnect).toBe('function')
    expect(typeof options.onDegraded).toBe('function')
    refresh.stop()
  })

  it('start() 幂等：重复调用只建一条订阅', () => {
    mockSubscribe.mockReset()
    mockSubscribe.mockReturnValue({ close: vi.fn() })
    const refresh = useWorkpaperContentRefresh({
      wpId: ref(WP),
      projectId: ref(PROJECT),
      loadedRevision: () => 11,
      isDirty: () => false,
      reload: async () => {},
    })
    refresh.start()
    refresh.start()
    expect(mockSubscribe).toHaveBeenCalledTimes(1)
    refresh.stop()
  })

  it('注入的订阅口真的把事件送进 handleEvent（不是只登记了回调）', async () => {
    const reload = vi.fn(async () => {})
    // 显式函数类型 + no-op 默认值：写成 `| null` 会让 TS 把 `deliver?.()` 窄化成
    // 「不可调用」（TS2349），而运行时其实是好的 —— 那种噪声会掩盖真正的类型错误。
    let deliver: (payload: unknown) => void = () => {}
    let delivered = false
    const close = vi.fn()
    const refresh = useWorkpaperContentRefresh({
      wpId: ref(WP),
      projectId: ref(PROJECT),
      loadedRevision: () => 11,
      isDirty: () => false,
      reload,
      subscribe: (context) => {
        deliver = context.onEvent
        delivered = true
        return { close }
      },
    })
    refresh.start()
    expect(delivered).toBe(true)
    deliver(sseEnvelope())
    await Promise.resolve()
    await Promise.resolve()
    expect(reload).toHaveBeenCalledWith(12)
    refresh.stop()
    expect(close).toHaveBeenCalledTimes(1)
  })

  it('SSE 降级可见，重连后不自己打端点（协调器没有 api 面）', async () => {
    const reload = vi.fn(async () => {})
    let onDegraded: () => void = () => {}
    let onReconnect: () => void = () => {}
    const refresh = useWorkpaperContentRefresh({
      wpId: ref(WP),
      projectId: ref(PROJECT),
      loadedRevision: () => 11,
      isDirty: () => false,
      reload,
      subscribe: (context) => {
        onDegraded = context.onDegraded
        onReconnect = context.onReconnect
        return { close: vi.fn() }
      },
    })
    refresh.start()
    onDegraded()
    expect(refresh.degraded.value).toBe(true)
    onReconnect()
    expect(refresh.degraded.value).toBe(false)
    expect(reload).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// H. 文案表自证
// ═══════════════════════════════════════════════════════════════════════════

describe('文案表', () => {
  it('六个状态各有文案，已落地状态各有具体动作提示，两张表零重复', () => {
    assertContentRefreshTextDisjoint()
    expect(Object.keys(WP_CONTENT_REFRESH_STATUS_TEXT).sort()).toEqual([
      'deferred_dirty',
      'event_rejected',
      'idle',
      'refresh_failed',
      'refreshing',
      'synced',
    ])
    for (const text of Object.values(WP_CONTENT_REFRESH_STATUS_TEXT)) {
      expect(text.trim()).not.toBe('')
      // 全中文：不得出现裸英文状态标识符
      expect(text).not.toMatch(/[a-z]+_[a-z]+/)
    }
  })

  it('只有 synced 允许说「已加载到最新」，失败态不得出现成功字样', () => {
    for (const [status, text] of Object.entries(WP_CONTENT_REFRESH_STATUS_TEXT)) {
      if (status === 'synced') continue
      for (const forbidden of ['已加载到最新', '刷新成功', '同步成功']) {
        expect(text, `${status} 的文案含成功字样`).not.toContain(forbidden)
      }
    }
  })

  it('feedback 的 kind 按状态分型，失败时取协调器记住的失败消息', async () => {
    const ok = harness()
    expect(ok.refresh.feedback.value.kind).toBe('idle')
    await ok.refresh.handleEvent(sseEnvelope())
    expect(ok.refresh.feedback.value.kind).toBe('success')

    const dirty = harness({ dirty: true })
    await dirty.refresh.handleEvent(sseEnvelope())
    expect(dirty.refresh.feedback.value.kind).toBe('warning')
    expect(dirty.refresh.feedback.value.hint).toBe(
      WP_CONTENT_REFRESH_ACTION_HINT.deferred_dirty,
    )

    const failing = harness({ reload: async () => { throw new Error('boom') } })
    await failing.refresh.handleEvent(sseEnvelope())
    expect(failing.refresh.feedback.value.kind).toBe('error')
    expect(failing.refresh.feedback.value.message).toBe(
      failing.refresh.lastFailure.value?.message,
    )
  })
})
