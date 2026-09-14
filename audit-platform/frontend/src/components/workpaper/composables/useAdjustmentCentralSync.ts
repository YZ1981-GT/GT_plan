/**
 * useAdjustmentCentralSync — 底稿调整分录 → 集中式登记 汇聚（共享 composable）
 *
 * spec: workpaper-adjustment-centralization
 *
 * 各循环调整分录 tab 复用本 composable：
 *  - `syncToCentral()`：把当前分录组映射为标准 line_items，调 sync 端点写入集中登记
 *    （origin='workpaper'，幂等 by source_ref={wpId}:{itemId}）。
 *  - `centralStatus`：集中登记复核状态回流（draft/pending/approved/rejected + 驳回原因），只读。
 *  - `refreshStatus()`：拉取回流状态。
 *
 * 不改动底稿→审定表→TB 既有链路；sync 失败仅 toast，不阻断底稿保存。
 */
import { ref, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  syncAdjustmentFromWorkpaper,
  getAdjustmentBySourceRef,
} from '@/services/auditPlatformApi'
import { eventBus } from '@/utils/eventBus'

export interface CentralSyncLineItem {
  standard_account_code?: string
  account_name?: string
  report_line_code?: string
  debit_amount: number
  credit_amount: number
}

export interface CentralStatus {
  entry_group_id?: string
  adjustment_no?: string
  review_status?: string
  rejection_reason?: string | null
  source_wp_code?: string
  /** 协作接力状态回流（pending/acknowledged/contributed/confirmed/rejected/closed），底稿侧只读展示 + 覆盖保护 */
  collaboration_status?: string | null
}

/** 协作状态中文标签（底稿侧展示） */
export const COLLAB_STATUS_LABELS_MIN: Record<string, string> = {
  pending: '待知晓', acknowledged: '已知晓', contributed: '已补充',
  confirmed: '已确认', rejected: '已退回', closed: '已关闭',
}

export interface UseAdjustmentCentralSyncOptions {
  projectId: Ref<string> | (() => string)
  year: Ref<number> | (() => number)
  wpId: Ref<string> | (() => string)
  wpCode: Ref<string> | (() => string) | string
  /** 该 tab 分录组的 checklist item_id（幂等键构成）；可为 getter 以支持随类型切换的动态 itemId */
  itemId: string | (() => string)
  /** tab 把自身 rows 映射为标准 line_items */
  buildLineItems: () => CentralSyncLineItem[]
  /** tab 提供 description + adjustmentType（报表调整→rje / 其余→aje） */
  buildMeta: () => { description: string; adjustmentType: 'aje' | 'rje' }
  /** P1-7: 保存后自动同步到集中登记（默认 false，开启后 saveAndPublish 成功可调 scheduleAutoSync） */
  autoSync?: boolean
}

function unwrap<T>(v: Ref<T> | (() => T) | T): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as any)) return (v as Ref<T>).value
  return v as T
}

/** 复核状态中文标签 */
export const CENTRAL_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  pending_review: '待复核',
  approved: '已通过',
  rejected: '已驳回',
}

export function useAdjustmentCentralSync(opts: UseAdjustmentCentralSyncOptions) {
  const centralStatus = ref<CentralStatus | null>(null)
  const syncing = ref(false)

  function resolveItemId(): string {
    return typeof opts.itemId === 'function' ? opts.itemId() : opts.itemId
  }

  function sourceRef(): string {
    return `${unwrap(opts.wpId)}:${resolveItemId()}`
  }

  async function syncToCentral(): Promise<void> {
    const projectId = unwrap(opts.projectId)
    const year = unwrap(opts.year)
    const wpId = unwrap(opts.wpId)
    if (!projectId || !wpId) {
      ElMessage.warning('缺少项目/底稿上下文，无法同步到集中登记')
      return
    }
    const lineItems = opts.buildLineItems().filter(
      (li) => (Number(li.debit_amount) || 0) !== 0 || (Number(li.credit_amount) || 0) !== 0,
    )
    if (!lineItems.length) {
      ElMessage.info('无有效分录行可同步')
      return
    }
    // 借贷平衡预校验（后端仍会校验，此处给即时反馈）
    const totalDebit = lineItems.reduce((s, li) => s + (Number(li.debit_amount) || 0), 0)
    const totalCredit = lineItems.reduce((s, li) => s + (Number(li.credit_amount) || 0), 0)
    if (Math.abs(totalDebit - totalCredit) > 0.005) {
      ElMessage.error(`借贷不平衡（借 ${totalDebit} / 贷 ${totalCredit}），请先平衡后再同步`)
      return
    }

    // P1-5 覆盖保护：该分录组曾经过协作补充（已补充/已确认）时，重新同步会以底稿当前数据
    // 覆盖协作结果（活跃协作由后端 COLLABORATION_LOCKED 拦截；此处防"确认后再同步"静默覆盖）。
    await refreshStatus()
    const collabSt = centralStatus.value?.collaboration_status
    if (collabSt === 'contributed' || collabSt === 'confirmed') {
      try {
        await ElMessageBox.confirm(
          `该分录组曾经过协作补充（${COLLAB_STATUS_LABELS_MIN[collabSt] || collabSt}），`
          + '重新同步将以底稿当前数据覆盖协作补充结果，是否继续？',
          '协作补充覆盖确认',
          { type: 'warning', confirmButtonText: '仍然同步', cancelButtonText: '取消' },
        )
      } catch {
        return  // 用户取消，保护协作结果
      }
    }

    const meta = opts.buildMeta()
    syncing.value = true
    try {
      await syncAdjustmentFromWorkpaper(projectId, {
        year,
        wp_id: wpId,
        item_id: resolveItemId(),
        source_wp_code: String(unwrap(opts.wpCode) || ''),
        description: meta.description,
        adjustment_type: meta.adjustmentType,
        line_items: lineItems,
      })
      ElMessage.success('已同步到集中调整登记')
      await refreshStatus()
      // P0-3: 显示同步后的编号供确认
      if (centralStatus.value?.adjustment_no) {
        ElMessage({
          type: 'info',
          message: `集中登记编号：${centralStatus.value.adjustment_no}`,
          duration: 4000,
          showClose: true,
        })
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const code = detail?.error_code
      if (code === 'APPROVED_LOCKED') {
        ElMessage.warning('该调整已在集中登记复核通过，需先撤回复核再同步')
      } else if (code === 'UNBALANCED') {
        ElMessage.error(detail?.message || '借贷不平衡，无法同步')
      } else if (code === 'UNRESOLVED_ACCOUNTS') {
        ElMessage.error(detail?.message || '存在无法解析的科目，请补全科目编码')
      } else {
        ElMessage.error('同步到集中登记失败')
      }
    } finally {
      syncing.value = false
    }
  }

  async function refreshStatus(): Promise<void> {
    const projectId = unwrap(opts.projectId)
    if (!projectId) return
    try {
      const res = await getAdjustmentBySourceRef(projectId, sourceRef())
      centralStatus.value = res && res.review_status ? res : null
    } catch {
      centralStatus.value = null
    }
  }

  // P0-4: 订阅集中登记复核状态变更事件，底稿侧自动回流刷新
  function _onReviewChanged() { refreshStatus() }
  onMounted(() => {
    eventBus.on('adjustment:review-changed', _onReviewChanged)
    refreshStatus()
  })
  onBeforeUnmount(() => {
    eventBus.off('adjustment:review-changed', _onReviewChanged)
  })

  // P1-7: 保存后自动同步（debounce 5s，silent 模式失败不弹）
  let _autoSyncTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleAutoSync(): void {
    if (!opts.autoSync) return
    if (_autoSyncTimer) clearTimeout(_autoSyncTimer)
    _autoSyncTimer = setTimeout(async () => {
      _autoSyncTimer = null
      const lineItems = opts.buildLineItems().filter(
        (li) => (Number(li.debit_amount) || 0) !== 0 || (Number(li.credit_amount) || 0) !== 0,
      )
      if (!lineItems.length) return
      // 平衡检查（不平衡则跳过不弹）
      const d = lineItems.reduce((s, li) => s + (Number(li.debit_amount) || 0), 0)
      const c = lineItems.reduce((s, li) => s + (Number(li.credit_amount) || 0), 0)
      if (Math.abs(d - c) > 0.005) return
      try { await syncToCentral() } catch { /* silent */ }
    }, 5000)
  }

  return {
    centralStatus,
    syncing,
    syncToCentral,
    refreshStatus,
    sourceRef,
    scheduleAutoSync,
  }
}

export default useAdjustmentCentralSync
