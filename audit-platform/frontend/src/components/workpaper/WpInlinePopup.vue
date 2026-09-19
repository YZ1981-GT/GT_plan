<script setup lang="ts">
/**
 * WpInlinePopup — 子底稿弹窗容器
 *
 * 根据 wpCode 动态加载对应子组件：
 * - A1-11 → WpPopupSigning（签字审批链）
 * - A1-12 → WpPopupChecklist（适用性核查）
 * - A1-17 → WpPopupProcedure（程序步骤）
 * - A1-18 → WpPopupMixedForm（混合型）
 * - docx 子底稿 → WpPopupDocxEditor（配置驱动，见 wpPopupDocxConfigs.ts）
 */
import { computed, defineAsyncComponent } from 'vue'
import { ALL_DOCX_POPUP_CONFIGS, DOCX_POPUP_WP_CODES } from './wpPopupDocxConfigs'

const WpPopupDocxEditor = defineAsyncComponent(() => import('./WpPopupDocxEditor.vue'))

const props = defineProps<{
  visible: boolean
  wpCode: string
  wpId?: string
  projectId?: string
  projectInfo?: Record<string, any>
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'save'): void
  (e: 'completed', wpCode: string): void
}>()

// 专用弹窗组件（非 docx 通用编辑器）
const POPUP_COMPONENTS: Record<string, ReturnType<typeof defineAsyncComponent>> = {
  'A1-11': defineAsyncComponent(() => import('./WpPopupSigning.vue')),
  'A1-12': defineAsyncComponent(() => import('./WpPopupChecklist.vue')),
  'A1-17': defineAsyncComponent(() => import('./WpPopupProcedure.vue')),
  'A1-18': defineAsyncComponent(() => import('./WpPopupMixedForm.vue')),
}

// Dialog titles
const POPUP_TITLES: Record<string, string> = {
  'A1-11': '业务报告签发流转控制表',
  'A1-12': '重大事项决定程序的履行情况核查表',
  'A1-17': '对应数据程序表',
  'A1-18': '采用新金融工具准则衔接影响数核对',
  ...Object.fromEntries(
    Object.entries(ALL_DOCX_POPUP_CONFIGS).map(([code, cfg]) => [code, cfg.title]),
  ),
}

// Dialog widths
const POPUP_WIDTHS: Record<string, string> = {
  'A1-11': '500px',
  'A1-12': '700px',
  'A1-17': '600px',
  'A1-18': '80vw',
}

const DOCX_DEFAULT_WIDTH = '75vw'

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const title = computed(() => POPUP_TITLES[props.wpCode] || props.wpCode)
const width = computed(() => {
  if (POPUP_WIDTHS[props.wpCode]) return POPUP_WIDTHS[props.wpCode]
  if (DOCX_POPUP_WP_CODES.has(props.wpCode)) return DOCX_DEFAULT_WIDTH
  return '600px'
})

const component = computed(() => {
  if (POPUP_COMPONENTS[props.wpCode]) return POPUP_COMPONENTS[props.wpCode]
  if (DOCX_POPUP_WP_CODES.has(props.wpCode)) return WpPopupDocxEditor
  return null
})

function handleSave() {
  emit('save')
}

function handleClose() {
  emit('update:visible', false)
  emit('save')
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="title"
    :width="width"
    :close-on-click-modal="false"
    destroy-on-close
    @close="handleClose"
  >
    <component
      v-if="component"
      :is="component"
      :wp-code="wpCode"
      :wp-id="wpId"
      :project-id="projectId"
      :project-info="projectInfo"
      @save="handleSave"
      @completed="emit('completed', wpCode)"
    />
    <div v-else class="popup-empty">
      <p>该子底稿暂不支持弹窗展示</p>
    </div>
  </el-dialog>
</template>

<style scoped>
.popup-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
