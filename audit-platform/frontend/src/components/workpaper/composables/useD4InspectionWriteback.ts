/**
 * useD4InspectionWriteback — D4 检查类底稿（D4-13/14/15/16）双向回写共享件
 *
 * 打通上下游：核对差异/异常 →
 *   ① A13 未更正错报汇总（eventBus 'a13:push-misstatement'，crossWpEventBridge 白名单，
 *      唯一消费者 useA13MisstatementBridge 落 unadjusted_misstatements）
 *   ② D4-1 审定表审计说明（item_id 'D4-1-adj-note'，经 d4:save-items 落库，D4-1 页面可见来源）
 *
 * 复用平台既有 a13 payload「形态 C」：{ wpCode, accountCode, source, items:[{voucherNo?, amount, description, indexRef}] }
 * 由 useA13MisstatementBridge.normalizeMisstatementPushPayload 归一化，本 composable 不改 bridge。
 */
import { computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 单笔待推送错报项（对齐 a13 形态 C 的 items 元素） */
export interface D4MisstatementItem {
  /** 凭证号/事项标识（可选，入描述） */
  voucherNo?: string
  /** 错报金额（差异额/异常额，取绝对值语义由调用方决定） */
  amount: number
  /** 描述（差异原因/异常说明） */
  description: string
  /** 索引号（溯源到本检查表的行/期间） */
  indexRef?: string
}

export interface UseD4InspectionWritebackOptions {
  /** 来源底稿编码，如 'D4-16'（决定 A13 溯源 source_wp_code） */
  wpCode: string
  /** allResponses 内存态（用于 append D4-1 审计说明） */
  allResponses: Ref<Map<string, any>>
  /** 只读态：只读时禁止推送 */
  isReadonly?: Ref<boolean>
}

const D4_1_NOTE_ITEM_ID = 'D4-1-adj-note'

// ─── Composable ────────────────────────────────────────────────────────────────

export function useD4InspectionWriteback(options: UseD4InspectionWritebackOptions) {
  const { wpCode, allResponses } = options
  const readonly = options.isReadonly ?? computed(() => false)

  /**
   * 把同一批差异摘要 append 到 D4-1 审计说明（item_id: D4-1-adj-note），
   * 经 d4:save-items 落库，使 D4-1 页面能看到来源为本检查表的差异说明。
   */
  function appendToD41Note(items: D4MisstatementItem[]): void {
    if (!items.length) return
    const prev = String(allResponses.value.get(D4_1_NOTE_ITEM_ID)?.remark ?? '')
    const summary = items
      .map((i) => (i.voucherNo ? `${i.voucherNo}：` : '') + i.description)
      .join('；')
    const line = `【${wpCode} 核对差异】${summary}`
    const remark = prev ? `${prev}\n${line}` : line
    allResponses.value.set(D4_1_NOTE_ITEM_ID, {
      item_id: D4_1_NOTE_ITEM_ID,
      conclusion: null,
      remark,
    })
    try {
      window.dispatchEvent(
        new CustomEvent('d4:save-items', {
          detail: { items: [allResponses.value.get(D4_1_NOTE_ITEM_ID)] },
        }),
      )
    } catch {
      /* SSR / 无 window 时静默 */
    }
  }

  /**
   * 推送差异/异常至 A13 未更正错报汇总 + 同步 append D4-1 审计说明。
   * 无可推送项时给中文提示且不 emit（Requirement 4.5）。
   * @returns 是否真的发出了推送
   */
  function pushToA13(
    items: D4MisstatementItem[],
    accountCode = '6001',
    accountName = '营业收入',
  ): boolean {
    if (readonly.value) return false
    if (!items.length) {
      ElMessage.info('无差异/异常项，无需推送')
      return false
    }
    eventBus.emit('a13:push-misstatement' as any, {
      wpCode,
      accountCode,
      accountName,
      source: wpCode,
      items: items.map((i) => ({
        voucherNo: i.voucherNo,
        amount: i.amount,
        description: i.description,
        indexRef: i.indexRef,
      })),
      timestamp: Date.now(),
    })
    appendToD41Note(items)
    ElMessage.success(`已推送 ${items.length} 项至 A13 错报汇总，并同步至 D4-1 审计说明`)
    return true
  }

  return { pushToA13, appendToD41Note }
}

export default useD4InspectionWriteback
