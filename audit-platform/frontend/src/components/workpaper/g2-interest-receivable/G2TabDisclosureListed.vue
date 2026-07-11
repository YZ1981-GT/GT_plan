<template>
  <div class="g2-disclosure-listed">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 上市公司附注格式（29行×16列），按投资类型分类列示期初/期末金额。</p>
        <p>2. 监听 substantive:adjudicated(1132) 自动同步审定数（来源 G2-1 审定表）。</p>
        <p>3. 编辑后发布 disclosure:note-text-updated 联动附注模块。</p>
        <p>4. 依据：CAS 37《金融工具列报》、CAS 30《财务报表列报》附注披露要求。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证上市公司应收利息附注披露的完整性、准确性与列报格式的合规性，确保与审定数一致。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">附注披露（上市公司）</span>
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-1" /></span>
        <el-button size="small" @click="openReviewDialog('G2-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 8, maxRows: 30 }"
        :disabled="isReadonly" placeholder="上市公司应收利息附注披露内容..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const STORAGE_KEY = 'G2-disclosure-listed-text'
const noteText = ref('')

// Load from allResponses
watch(() => props.allResponses.get(STORAGE_KEY)?.remark, (v) => {
  if (v && v !== noteText.value) noteText.value = v
}, { immediate: true })

// Save on change
watch(noteText, (val) => {
  props.debouncedSave(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: val })
  // Publish disclosure update
  try {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { accountCode: '1132', section: 'listed', text: val },
    }))
  } catch { /* silent */ }
})

// Subscribe substantive:adjudicated(1132)
function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1132') {
    // Auto-refresh: could update template variables here
  }
}

onMounted(() => { window.addEventListener('substantive:adjudicated', handleAdjudicated) })
onBeforeUnmount(() => { window.removeEventListener('substantive:adjudicated', handleAdjudicated) })

function fillAiDraft() {
  if (props.isReadonly) return
  const draft = '根据审计结果，本期应收利息期末余额为 [审定金额] 元，按投资类型分类如下：...'
  noteText.value = noteText.value ? `${noteText.value}\n${draft}` : draft
}
</script>

<style scoped>
.g2-disclosure-listed { padding: 12px; font-size: 13px; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
</style>
