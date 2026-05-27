/**
 * useEditorMode — HTML/Univer 双模式切换逻辑 [V3 Req 12.1.3]
 *
 * 骨架已建 + 示范提取，完整瘦身需独立 Sprint。
 * 将 WorkpaperEditor.vue 中的 component_type 路由分发逻辑（~300 行）
 * 抽离为独立 composable，主组件仅消费 computed 结果。
 *
 * 路由优先级：
 * 1. HTML 类（A/B/C/D/E/H/skip 共 1346 sheet）→ GtWpRenderer
 * 2. 子编辑器（form/word/table/hybrid）→ 动态 component
 * 3. Univer 类（F/G 558 sheet）→ 默认 Univer 编辑器
 *
 * @example
 * const { useHtmlRenderer, componentType, editorComponent, fetchComponentType } = useEditorMode({
 *   wpId, projectId, wpDetail,
 * })
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

/** HTML 类 componentType 白名单（与 GtWpRenderer 子组件分发一致） */
export const HTML_COMPONENT_TYPES = new Set([
  'a-program-console',
  'b-control-understanding',
  'c-control-test',
  'd-revenue',
  'e-cash',
  'h-fixed-asset',
  'h-rou-asset',
  'h-lease-liability',
  'skip',
])

/** 子编辑器组件映射（非 Univer、非 HTML 的 component_type） */
export const EDITOR_MAP: Record<string, any> = {
  // 完整迁移时从 WorkpaperEditor.vue 移入
  // form: WorkpaperFormEditor,
  // word: WorkpaperWordEditor,
  // table: WorkpaperTableEditor,
  // hybrid: WorkpaperHybridEditor,
}

export interface EditorModeContext {
  wpId: Ref<string>
  projectId: Ref<string>
  wpDetail: Ref<any>
}

export interface EditorModeReturn {
  /** 是否使用 HTML 渲染器 */
  useHtmlRenderer: ComputedRef<boolean>
  /** 当前 component_type */
  componentType: Ref<string>
  /** 动态子编辑器组件 */
  editorComponent: ComputedRef<any>
  /** 从后端获取 component_type */
  fetchComponentType: () => Promise<void>
  /** HTML componentType 白名单 */
  HTML_COMPONENT_TYPES: Set<string>
}

/**
 * 示范：双模式切换逻辑骨架
 *
 * 完整迁移时，将 WorkpaperEditor.vue 中以下代码块移入：
 * - componentType ref + editorComponent computed
 * - HTML_COMPONENT_TYPES Set
 * - useWpClassification 调用 + htmlComponentType computed
 * - useHtmlRenderer computed
 * - fetchComponentType 函数
 * - onMounted 中的路由分发逻辑
 */
export function useEditorMode(ctx: EditorModeContext): EditorModeReturn {
  const componentType = ref<string>('univer')

  const editorComponent = computed(() => EDITOR_MAP[componentType.value] || null)

  const useHtmlRenderer = computed(() => {
    // 骨架：完整迁移时接入 useWpClassification
    return false
  })

  async function fetchComponentType() {
    // 骨架：完整迁移时从 WorkpaperEditor.vue 移入 httpApi.get 逻辑
    // try {
    //   const detail = await httpApi.get(P_wp.detail(ctx.projectId.value, ctx.wpId.value))
    //   componentType.value = detail?.component_type || 'univer'
    //   if (detail) ctx.wpDetail.value = detail
    // } catch {
    //   componentType.value = 'univer'
    // }
  }

  // 骨架：完整迁移时加入 watch(wpCodeRef) 触发 classification load
  watch(() => ctx.wpDetail.value?.wp_code, () => {
    // placeholder for classification trigger
  })

  return {
    useHtmlRenderer,
    componentType,
    editorComponent,
    fetchComponentType,
    HTML_COMPONENT_TYPES,
  }
}
