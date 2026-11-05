/**
 * 报表类页面（审定报表 / 报表分析 / 单体财务报表）的悬浮来源卡片（spec citar-cell-source-hover R5）。
 * - 格子写 `data-src="键"`、`data-hint="操作提示"`（CitarAmountCell 自己写）；卡片的操作提示读 data-hint，不在页面再算一遍草稿 / 手工状态
 * - load：整页来源（键 → 来源）；label：卡片标题；locate：链接指向本页格子时由页面定位（不跳页）
 * - 跳到别的页前，有未保存修改先确认
 */
import { computed, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { cellSourceLink, type CellSource, type CellSourceLink } from './cellSource'
import { useCellSourceHover } from './useCellSourceHover'
import { useCitarProject } from './useCitarProject'

export interface CitarSourceCardOptions {
  container: Ref<HTMLElement | null>
  load: () => Promise<Record<string, CellSource>>
  label: (key: string) => string
  /** 本页定位（链接 page 由页面判断）；返回 true = 已处理，不跳页 */
  locate?: (link: CellSourceLink) => boolean
  dirty?: () => boolean
}

export function useCitarSourceCard(opts: CitarSourceCardOptions) {
  const { goSegment } = useCitarProject()

  function hintOf(key: string): string | null {
    const el = opts.container.value?.querySelector<HTMLElement>(`[data-src="${key.replace(/["\\]/g, '\\$&')}"]`)
    return el?.dataset.hint || null
  }

  const hover = useCellSourceHover(opts.container, {
    load: opts.load,
    resolve(key, sources) {
      if (!sources) return null
      const s = sources[key]
      return s ? { ...s, hint: hintOf(key) } : null
    },
    // 正在编辑的格子不弹
    disabled: key => Boolean(opts.container.value?.querySelector(`[data-src="${key.replace(/["\\]/g, '\\$&')}"] input`)),
  })

  const cardLabel = computed(() => (hover.card.value.key ? opts.label(hover.card.value.key) : ''))

  async function open(l: CellSourceLink) {
    hover.close()
    if (opts.locate?.(l)) return
    const link = cellSourceLink(l)
    if (!link) return
    if (opts.dirty?.()) {
      try {
        await ElMessageBox.confirm('有未保存的修改，离开本页会丢失。仍要去看数据来源吗？', '未保存的修改', {
          type: 'warning', confirmButtonText: '离开', cancelButtonText: '留在本页',
        })
      } catch {
        return
      }
    }
    goSegment(link.segment, link.query)
  }

  return { card: hover.card, cardLabel, open, invalidate: hover.invalidate, onCardEnter: hover.onCardEnter, onCardLeave: hover.onCardLeave }
}
