/**
 * 源头页按 ?locate=编码 定位到行（spec citar-fs-issue-source-locate）：滚到 [data-locate="编码"] 并高亮（.citar-located）。
 * 页面负责：数据读完后调用 apply（先清掉会挡住这一行的筛选），行上写 :data-locate / :class="{ 'citar-located': isLocated(编码) }"。
 * 同一编码只滚动、只提示一次（保存后重读数据不再跳）。
 */
import { computed, nextTick, ref, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

/** 科目编码比较口径：去空白、剥 Excel 数字格式的 .0 */
export function normCode(code: unknown): string {
  const s = String(code ?? '').trim()
  return s.endsWith('.0') ? s.slice(0, -2) : s
}

export function useCitarRowLocate(source?: Ref<string | undefined>) {
  const route = source ? null : useRoute()
  const code = computed(() => normCode(source ? source.value : route?.query.locate))
  const located = ref('')
  let handled = ''

  function isLocated(rowCode: unknown): boolean {
    return Boolean(located.value) && normCode(rowCode) === located.value
  }

  /**
   * found：本页数据里有没有这一行；prepare：清筛选 / 切页签，让该行显示出来；missing：找不到时的提示。
   * 返回是否定位到了。
   */
  async function apply(found: (code: string) => boolean, prepare?: () => void, missing?: string): Promise<boolean> {
    const target = code.value
    if (!target || handled === target) return located.value === target
    handled = target
    if (!found(target)) {
      located.value = ''
      ElMessage.info(missing ?? `本页没有科目 ${target}`)
      return false
    }
    prepare?.()
    located.value = target
    await nextTick()
    const el = document.querySelector<HTMLElement>(`[data-locate="${target.replace(/["\\]/g, '\\$&')}"]`)
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    return true
  }

  return { code, located, isLocated, apply }
}
