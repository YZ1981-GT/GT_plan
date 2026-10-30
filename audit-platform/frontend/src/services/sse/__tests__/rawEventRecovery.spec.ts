// raw SSE 事件不冒充 typed replay；每个活跃消费族登记恢复方式。
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  PROJECT_TRANSPORT_RECOVERED_EVENT,
  RAW_CONSUMER_RECOVERY,
  RAW_EVENT_REPLAY_DEGRADED,
} from '../rawEventRecovery'

const ROOT = path.resolve(__dirname, '../../../')
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), 'utf-8')

const adjustments = read('views/Adjustments.vue')
const attachments = read('views/AttachmentManagement.vue')
const consolidation = read('views/ConsolidationIndex.vue')
const lineage = read('components/deliverable/LineagePanel.vue')
const central = read('components/workpaper/composables/useAdjustmentCentralSync.ts')
const refreshTracking = read('components/consolidation/composables/useConsolRefreshTracking.ts')
const e1 = read('components/workpaper/GtE1MonetaryFund.vue')
const k1 = read('components/workpaper/GtK1OtherReceivables.vue')

describe('raw event 恢复清单', () => {
  it('清单非空且 transport.recovered 明确区分 typed replay 与 raw 全量刷新', () => {
    expect(RAW_EVENT_REPLAY_DEGRADED.length).toBeGreaterThanOrEqual(30)
    expect(PROJECT_TRANSPORT_RECOVERED_EVENT).toBe('transport.recovered')
    expect(RAW_EVENT_REPLAY_DEGRADED).toContain('attachment.uploaded')
    expect(RAW_EVENT_REPLAY_DEGRADED).toContain('formula.pushed')
  })

  it('可安全全量重拉的 raw 消费方全部接 onReconnect', () => {
    expect(adjustments).toContain('{ onReconnect: _refreshAdjustmentsAfterReconnect }')
    expect(adjustments).toContain('fetchEntries()')
    expect(adjustments).toContain('fetchSummary()')

    expect(attachments).toContain('{ onReconnect: reloadAttachmentsAfterEvent }')
    expect(attachments).toContain('void loadAttachments()')

    expect(consolidation).toContain('{ onReconnect: recoverConsolPushAfterReconnect }')
    expect(consolidation).toContain('loadConsolPushStatus()')
    expect(consolidation).toContain('refreshCurrentAfterConsolPush()')

    expect(lineage).toContain('{ onReconnect: refreshLineageAfterEvent }')
    expect(lineage).toContain('void loadSections()')

    expect(central).toContain('{ onReconnect: () => refreshStatus() }')
  })

  it('长任务进度有状态轮询兜底，不靠不可重放的 progress 帧决定终态', () => {
    expect(RAW_CONSUMER_RECOVERY['consol.refresh.*']).toBe('status_poll')
    expect(refreshTracking).toContain('refreshStatus(')
    expect(refreshTracking).toContain('pollTimer = setTimeout(poll, 3000)')
  })

  it('formula.pushed 不在重连后静默覆盖用户编辑，只保留手动载入提示', () => {
    expect(RAW_CONSUMER_RECOVERY['formula.pushed']).toBe('manual_dirty_safe_reload')
    for (const source of [e1, k1]) {
      const block = source.slice(source.indexOf("subscribeProjectEvent(props.projectId, 'formula.pushed'"))
      expect(block).not.toContain('onReconnect: reloadPushedItems')
      expect(source).toContain('async function reloadPushedItems')
      expect(source).toContain('pushNotice')
    }
  })
})
