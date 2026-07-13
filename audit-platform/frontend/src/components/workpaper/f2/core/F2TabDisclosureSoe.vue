<script setup lang="ts">
/** F2TabDisclosureSoe — 附注披露（国企） */
import { ref, toRef, onMounted, type Ref } from 'vue'
import { useF2DisclosureSoe } from '../../composables/useF2DisclosureSoe'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  applicableStandards: string[]
}>()

function fmtAmount(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const { isApplicable, rows, subtotal, noteText, dataUpdatedVisible } = useF2DisclosureSoe({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────────
const NOTE_KEY = 'F2-disclosure-soe-audit-note'
const CONCLUSION_KEY = 'F2-disclosure-soe-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistAudit(NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistAudit(CONCLUSION_KEY, val)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<template>
  <div class="f2-disclosure-soe">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />

    <template v-else>
      <!-- 编制提示 -->
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 存货分类披露的期末/期初余额自 F2-1 审定表各类别净值自动取数（跨 sheet，只读）。</p>
          <p>2. 依《企业会计准则第 1 号——存货》，应按存货类别披露账面价值及跌价准备计提情况。</p>
          <p>3. 国有企业需按主管部门要求补充披露存货减值、周转及积压情况。</p>
          <p>4. 审定表数据更新后本表自动刷新，请核对分类合计与报表一致。</p>
        </div>
      </details>

      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="objective-alert"
        title="审计目标：核实国有企业存货附注披露的分类、账面价值与跌价准备的完整、准确，确保与 F2-1 审定表及主管部门列报要求一致。"
      />

      <!-- 工具栏 -->
      <div class="tab-toolbar">
        <div class="toolbar-left" />
        <div class="toolbar-right">
          <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        </div>
      </div>

      <el-alert
        v-if="dataUpdatedVisible"
        type="info"
        title="审定表数据已更新，附注分类披露已自动刷新"
        :closable="false"
        show-icon
        class="update-bar"
      />

      <div class="disclosure-card">
        <h4 class="card-title">
          存货分类披露
          <GtIndexChip value="wp:F2-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...rows, subtotal]" size="small" border stripe>
          <el-table-column prop="label" label="存货类别" width="180">
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endAmount) }}</template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">{{ fmtAmount(row.priorAmount) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">附注说明文字</h4>
        <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly" placeholder="附注披露说明..." />
      </div>

      <!-- 审计说明 -->
      <el-card shadow="never" class="audit-note-card">
        <template #header><div class="card-header"><span>审计说明</span></div></template>
        <el-input
          type="textarea"
          :model-value="auditNote"
          :disabled="isReadonly"
          :autosize="{ minRows: 5 }"
          placeholder="填写审计说明：概述存货附注分类披露的取数来源、与审定表核对情况及减值/周转/积压等披露事项。"
          @change="saveAuditNote"
        />
      </el-card>

      <!-- 审计结论 -->
      <el-card shadow="never" class="audit-note-card">
        <template #header><div class="card-header"><span>审计结论</span></div></template>
        <el-input
          type="textarea"
          :model-value="auditConclusion"
          :disabled="isReadonly"
          :autosize="{ minRows: 3 }"
          placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
          @change="saveAuditConclusion"
        />
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.f2-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-disclosure-soe :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-disclosure-soe :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.update-bar { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 20px; }
.card-title { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.subtotal-label { font-weight: 600; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
