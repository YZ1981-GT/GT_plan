/**
 * useLineagePanel — 统一溯源面板 composable
 *
 * 提供打开 LineageGraphPanel 的统一接口，供各模块右键菜单接入。
 *
 * @example
 * const { openLineage, lineagePanelProps } = useLineagePanel()
 * // 右键菜单中调用
 * openLineage('wp_cell', 'D2-3!B5')
 * // 模板中绑定
 * <LineageGraphPanel v-bind="lineagePanelProps" @update:modelValue="lineagePanelProps.modelValue = $event" />
 */
import { reactive } from 'vue'

export interface LineagePanelState {
  modelValue: boolean
  objectType: string
  objectId: string
}

export function useLineagePanel() {
  const state = reactive<LineagePanelState>({
    modelValue: false,
    objectType: 'wp_cell',
    objectId: '',
  })

  function openLineage(objectType: string, objectId: string) {
    state.objectType = objectType
    state.objectId = objectId
    state.modelValue = true
  }

  function closeLineage() {
    state.modelValue = false
  }

  return {
    /** 打开溯源面板 */
    openLineage,
    /** 关闭溯源面板 */
    closeLineage,
    /** 绑定到 LineageGraphPanel 的 props */
    lineagePanelProps: state,
  }
}
