<script setup lang="ts">
/**
 * F4TabDisclosureSOE — 附注披露（国企）
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.6
 * 订阅EventBus `substantive:adjudicated`(accountCode='2202') 自动刷新
 * 发布 `disclosure:note-text-updated` 联动附注模块
 * Requirements: 4.1~4.5
 */
import { inject, ref, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import type { ChecklistResponse } from '../composables/useF4FormData'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 数据 ────────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'F4-disclosure-soe'
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const noteText = ref('')

watch(() => (props.allResponses as Map<string, any>).get(STORAGE_KEY)?.remark, (v) => {
  if (!noteText.value && v) noteText.value = v
}, { immediate: true })

watch(noteText, (val) => {
  const map = props.allResponses as Map<string, ChecklistResponse>
  map.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: val })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    const item = map.get(STORAGE_KEY)
    if (item) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { accountCode: '2202', type: 'soe', text: val },
      }))
    }
  }, 2000)
})

// 订阅审定完成事件
function onAdjudicated(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.accountCode === '2202') {
    ElMessage.info('审定数据已更新，请检查附注披露内容')
  }
}

window.addEventListener('substantive:adjudicated', onAdjudicated)
onBeforeUnmount(() => {
  window.removeEventListener('substantive:adjudicated', onAdjudicated)
  if (debounceTimer) { clearTimeout(debounceTimer) }
})
</script>

<template>
  <div class="f4-tab-disclosure-soe">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 国企附注披露需按国资委要求额外披露相关内容。</p>
        <p>2. 包括：国有企业间往来、关联方交易、大额长期未结清款项等。</p>
        <p>3. 当审定表确认后，本页面会收到通知提醒检查披露内容是否需要更新。</p>
      </div>
    </details>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <span class="section-label">附注披露（国企）</span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F4-1" :context-project-id="projectId" /></span>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-soe')">复核</el-button>
      </div>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">附注披露内容</span>
          <div class="opinion-actions">
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-soe')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 10, maxRows: 30 }"
        :disabled="isReadonly"
        placeholder="请编写国企附注披露内容（国有企业间往来、关联交易、大额长期挂账等）..."
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-disclosure-soe { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; font-size: var(--wp-font-size, 13px); }
.guidance-details .guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-details .guidance-content p { margin: 2px 0; }
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-label { font-weight: 600; font-size: 14px; color: #303133; }
.opinion-card { border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
