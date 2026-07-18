<template>
  <div class="g5-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露（上市公司）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" text :disabled="props.readonly">AI 辅助</el-button>
        <GtReviewTrigger section-id="G5-disclosure-listed" />
      </div>
    </div>
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：核实长期应收款附注披露的完整性与准确性，确保账龄、关联方、减值计提及计量政策按上市公司格式充分披露。"
      style="margin-bottom: 12px" />

    <el-card shadow="never">
      <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 8, maxRows: 30 }"
        :disabled="props.readonly" placeholder="长期应收款附注披露（上市公司格式）..." />
    </el-card>
    
    
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>监听 substantive:adjudicated(1531) 自动同步审定数</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, onBeforeUnmount } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G5_ACCOUNT_CODE } from '../../composables/g5Constants'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const noteText = ref('')

watch(noteText, (val) => {
  try {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { accountCode: G5_ACCOUNT_CODE, section: 'listed', text: val },
    }))
  } catch { /* silent */ }
})

function handleAdjudicated(e: Event) {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === G5_ACCOUNT_CODE && d.adjudicatedAmount != null) {
    noteText.value = noteText.value.replace(/\[审定金额\]/g, String(d.adjudicatedAmount))
  }
}

onMounted(() => window.addEventListener('substantive:adjudicated', handleAdjudicated))
onBeforeUnmount(() => window.removeEventListener('substantive:adjudicated', handleAdjudicated))
</script>

<style scoped>
.g5-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
</style>
