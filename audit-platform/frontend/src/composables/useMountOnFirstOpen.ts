/**
 * 首次打开才挂载、打开后保持挂载（spec platform-performance-residual-findings-closure R5.3）。
 *
 * 重弹窗（如公式管理，约 264 KB）在宿主里无条件渲染时，即便是 `defineAsyncComponent`，宿主一挂载就会下载、
 * 解析并实例化它。用法：
 *
 * ```vue
 * const showFormulaManager = ref(false)
 * const formulaManagerMounted = useMountOnFirstOpen(showFormulaManager)
 * <FormulaManagerDialog v-if="formulaManagerMounted" v-model="showFormulaManager" … />
 * ```
 *
 * 第一次为真后一直为真：关闭只隐藏、不卸载，弹窗内状态（选中节点、已加载的数据）照旧保留。
 * 回调在渲染前执行（默认 `flush: 'pre'`），弹窗挂载那一刻 `modelValue` 已是 true —— 弹窗须支持「挂载时即打开」
 * （公式管理见 `FormulaManagerDialogOpenBeforeMount.spec.ts`）。
 */
import { ref, watch, type Ref, type WatchSource } from 'vue'

export function useMountOnFirstOpen(open: WatchSource<boolean>): Readonly<Ref<boolean>> {
  const mounted = ref(false)
  watch(open, (visible) => { if (visible) mounted.value = true }, { immediate: true })
  return mounted
}
