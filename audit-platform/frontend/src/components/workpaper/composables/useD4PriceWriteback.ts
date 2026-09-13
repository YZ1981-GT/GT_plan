/**
 * useD4PriceWriteback — D4 价格分析异常回标接收端
 *
 * 监听 `d4:price-abnormal` 事件，将异常客户/产品标记写回 D4-2-rows 行。
 * 幂等：按 name 覆盖标记集合，空数组清除全部标记（Req 4.5）。
 * 目标行缺失静默跳过（Req 4.4）。
 *
 * Spec: d4-price-analysis-writeback-linkage Task 5
 */
import { onBeforeUnmount, type Ref } from 'vue'
import { eventBus, type Events } from '@/utils/eventBus'

interface UseD4PriceWritebackOptions {
  allResponses: Ref<Map<string, any>>
  debounceSave: () => void
}

/**
 * 安全 parse JSON 字符串为数组，失败返回空数组。
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function useD4PriceWriteback(options: UseD4PriceWritebackOptions) {
  const { allResponses, debounceSave } = options

  function handlePriceAbnormal(payload: Events['d4:price-abnormal']) {
    if (!payload) return

    const { targetKey, items } = payload

    if (targetKey === 'customer' || targetKey === 'product') {
      // 回标到 D4-2-rows（产品维度的异常也标在 D4-2 主营明细行上）
      const resp = allResponses.value.get('D4-2-rows')
      const rows = safeParseRows<any>(resp?.remark)
      if (rows.length === 0) return

      // 构建异常名 → diffPct 映射（幂等：直接覆盖）
      const abnormalMap = new Map<string, number>()
      for (const item of items) {
        abnormalMap.set(item.name, item.diffPct)
      }

      let changed = false
      for (const row of rows) {
        const name = targetKey === 'customer' ? (row.product || '') : (row.product || '')
        const abnormalPct = abnormalMap.get(name)

        if (abnormalPct !== undefined) {
          // 标记异常
          if (!row.priceAbnormal || row.priceAbnormalPct !== abnormalPct) {
            row.priceAbnormal = true
            row.priceAbnormalPct = abnormalPct
            changed = true
          }
        } else {
          // 清除标记（items 为空数组时全清）
          if (row.priceAbnormal) {
            row.priceAbnormal = false
            delete row.priceAbnormalPct
            changed = true
          }
        }
      }

      if (changed) {
        allResponses.value.set('D4-2-rows', {
          item_id: 'D4-2-rows',
          conclusion: null,
          remark: JSON.stringify(rows),
        })
        debounceSave()
      }
    }
  }

  // 注册事件监听（eventBus，非裸 window CustomEvent）
  eventBus.on('d4:price-abnormal', handlePriceAbnormal)

  onBeforeUnmount(() => {
    eventBus.off('d4:price-abnormal', handlePriceAbnormal)
  })

  return { handlePriceAbnormal }
}
