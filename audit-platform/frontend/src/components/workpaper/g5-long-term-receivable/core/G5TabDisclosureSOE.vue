<template>
  <div class="g5-disclosure-soe">
    <div class="section-head">
      <h3 class="sheet-title">附注披露（国企）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" text :disabled="props.readonly">AI 辅助</el-button>
        <GtReviewTrigger section-id="G5-disclosure-soe" />
      </div>
    </div>
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：核实长期应收款附注披露的完整性与准确性，确保账龄、关联方、减值计提及计量政策按国企格式充分披露。"
      style="margin-bottom: 12px" />

    <el-card shadow="never">
      <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 8, maxRows: 30 }"
        :disabled="props.readonly" placeholder="长期应收款附注披露（国企格式）..." />
    </el-card>
    <el-card shadow="never" style="margin-top: 12px">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="props.readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：披露项目的核对情况、审定数据来源、与明细表/审定表勾稽结果及未决事项。"
        @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" style="margin-top: 12px">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="props.readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、附注披露完整准确。B、除下述事项外披露恰当。C、存在重大披露缺失或错误，需修改。"
        @change="saveAuditConclusion" />
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

// ─── 审计说明 / 审计结论（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-disclosure-soe-audit-note'
const G5_CONCLUSION_KEY = 'G5-disclosure-soe-audit-conclusion'
function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

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
.g5-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
</style>
