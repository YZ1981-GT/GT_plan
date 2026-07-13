<script setup lang="ts">
/**
 * F4TabDisclosureListed — 附注披露（上市公司）
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.6
 * 订阅EventBus `substantive:adjudicated`(accountCode='2202') 自动刷新
 * 发布 `disclosure:note-text-updated` 联动附注模块
 * Requirements: 4.1~4.5
 */
import { inject, toRef, ref, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
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

const STORAGE_KEY = 'F4-disclosure-listed'
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
      // 发布附注更新事件
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { accountCode: '2202', type: 'listed', text: val },
      }))
    }
  }, 2000)
})

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────
const NOTE_KEY = 'F4-disclosure-listed-audit-note'
const CONCLUSION_KEY = 'F4-disclosure-listed-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistF4(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  ;(props.allResponses as Map<string, any>).set(key, item)
  window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistF4(NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistF4(CONCLUSION_KEY, val)
}

onMounted(() => {
  const map = props.allResponses as Map<string, any>
  const n = map.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = map.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
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
  <div class="f4-tab-disclosure-listed">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 上市公司附注披露需按准则要求披露应付账款的主要内容。</p>
        <p>2. 包括：按性质分类、前五名供应商、账龄分析、关联方应付等。</p>
        <p>3. 当审定表确认后，本页面会收到通知提醒检查披露内容是否需要更新。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实应付账款(2202)在上市公司财务报表附注中的列报完整、分类准确，按性质/前五名/账龄/关联方等要求充分披露。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <span class="section-label">附注披露（上市公司）</span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F4-1" :context-project-id="projectId" /></span>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-listed')">复核</el-button>
      </div>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">附注披露内容</span>
          <div class="opinion-actions">
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-listed')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 10, maxRows: 30 }"
        :disabled="isReadonly"
        placeholder="请编写上市公司附注披露内容（应付账款按性质分类、前五名、账龄分析等）..."
      />
    </el-card>

    <!-- ─── 审计说明 ──────────────────────────────────────────────────── -->
    <el-card class="opinion-card" shadow="never" style="margin-top:16px">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-listed-note')">💬</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：说明披露内容与审定表/明细表的核对情况及依据。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ─── 审计结论 ──────────────────────────────────────────────────── -->
    <el-card class="opinion-card" shadow="never" style="margin-top:16px">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：附注披露是否符合企业会计准则列报要求。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-disclosure-listed { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; font-size: var(--wp-font-size, 13px); }
.guidance-details .guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-details .guidance-content p { margin: 2px 0; }
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-label { font-weight: 600; font-size: 14px; color: #303133; }
.audit-objective { margin-bottom: 12px; }
.opinion-card { border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
