<template>
  <div class="g2-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露（上市公司）</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G2-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 8, maxRows: 30 }"
        :disabled="isReadonly" placeholder="上市公司应收利息附注披露内容..." />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注格式（29行×16列），按投资类型分类列示期初/期末金额</li>
        <li>监听 substantive:adjudicated(1132) 自动同步审定数</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import type { ChecklistResponse } from '../../composables/useF1FormData'

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
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
