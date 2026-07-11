<template>
  <div class="g5-disclosure-soe">
    <div class="section-head">
      <h3 class="sheet-title">附注披露（国企）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" text :disabled="props.readonly">AI 辅助</el-button>
        <GtReviewTrigger section-id="G5-disclosure-soe" />
      </div>
    </div>
    <el-card shadow="never">
      <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 8, maxRows: 30 }"
        :disabled="props.readonly" placeholder="长期应收款附注披露（国企格式）..." />
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
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { G5_ACCOUNT_CODE } from '../../composables/g5Constants'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const noteText = ref('')

watch(noteText, (val) => {
  try {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { accountCode: G5_ACCOUNT_CODE, section: 'soe', text: val },
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
.g5-disclosure-soe { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
</style>
