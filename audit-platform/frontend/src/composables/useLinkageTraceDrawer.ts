/**
 * useLinkageTraceDrawer — 统一穿透面板状态管理（P1-2.4）
 *
 * 提供试算表、报表、底稿、附注各模块打开穿透面板的统一入口。
 * 各视图 import 后调用 openTrace() 即可触发 drawer。
 *
 * P1-3.4: 冲突解决后可调用 refresh() 刷新当前 trace 数据。
 */
import { ref, readonly } from 'vue'

export interface TraceDrawerState {
  visible: boolean
  sourceType: string
  sourceId: string
  cell: string | null
  year: number | null
  /** P1-3.4: 自增计数器，变化时触发 drawer 重新查询 */
  refreshKey: number
}

const state = ref<TraceDrawerState>({
  visible: false,
  sourceType: '',
  sourceId: '',
  cell: null,
  year: null,
  refreshKey: 0,
})

/**
 * 打开穿透面板
 */
export function openLinkageTrace(params: {
  sourceType: string
  sourceId: string
  cell?: string | null
  year?: number | null
}) {
  state.value = {
    visible: true,
    sourceType: params.sourceType,
    sourceId: params.sourceId,
    cell: params.cell ?? null,
    year: params.year ?? null,
    refreshKey: state.value.refreshKey,
  }
}

/**
 * 关闭穿透面板
 */
export function closeLinkageTrace() {
  state.value.visible = false
}

/**
 * P1-3.4: 冲突解决后刷新 LinkageContract 状态
 */
export function refreshLinkageTrace() {
  state.value.refreshKey++
}

/**
 * composable hook，在 App.vue 或 layout 中使用
 */
export function useLinkageTraceDrawer() {
  return {
    state: readonly(state),
    open: openLinkageTrace,
    close: closeLinkageTrace,
    refresh: refreshLinkageTrace,
    /** 用于 v-model 绑定 */
    setVisible(val: boolean) {
      state.value.visible = val
    },
  }
}
