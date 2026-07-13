<template>
  <div class="f2-interview-summary">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总 IPO 供应商访谈情况，逐条记录访谈方式、受访人、内容摘要与结论。</p>
        <p>2. 访谈应核实交易真实性、关联关系及是否存在体外资金循环、利益输送等异常。</p>
        <p>3. 结论选择"存在疑点/需进一步核查/异常"的行须补充关注事项，并追加访谈明细（F2-72）。</p>
        <p>4. 点击供应商行的 →F2-72 索引可跳转至对应访谈明细底稿。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：通过供应商访谈验证采购交易的真实性与商业合理性，识别关联关系及异常交易迹象。</template>
    </el-alert>

    <header class="sheet-header">
      <div>
        <h3>供应商访谈记录汇总</h3>
        <span class="code">F2-71</span>
      </div>
      <div class="summary-chips">
        <el-tag>访谈 {{ iv.conclusionSummary.value.total }}</el-tag>
        <el-tag type="success">无异常 {{ iv.conclusionSummary.value.normal }}</el-tag>
        <el-tag type="warning">疑点 {{ iv.conclusionSummary.value.doubt }}</el-tag>
        <el-tag type="info">需核查 {{ iv.conclusionSummary.value.review }}</el-tag>
        <el-tag type="danger">异常 {{ iv.conclusionSummary.value.abnormal }}</el-tag>
      </div>
    </header>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="iv.addRow()">+ 新增访谈</el-button>
        <el-input v-model="iv.searchQuery.value" size="small" placeholder="搜索供应商/受访人" clearable class="search" />
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-71"
          :disabled="isReadonly"
          ai-section="supplier-analysis"
          :existing-content="iv.auditNote.value"
          review-section="F2-71-interview"
          @ai-filled="(t: string) => { iv.auditNote.value = t }"
        />
        <GtIndexChip value="wp:F2-71" />
        <el-tag size="small" type="info">共 {{ iv.filteredRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="iv.filteredRows.value"
      border size="small" max-height="460"
      :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''"
    >
      <el-table-column type="index" label="序号" width="55" />
      <el-table-column label="供应商名称" width="150">
        <template #default="{ row }">
          <div class="supplier-cell">
            <el-input v-if="!isReadonly" :model-value="row.supplierName" size="small"
              @change="(v: string) => iv.updateRow(row.id, { supplierName: v })" />
            <span v-else>{{ row.supplierName }}</span>
            <GtIndexChip v-if="row.supplierName" :value="`F2-72:${row.supplierName}`" :label="`→F2-72`" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="访谈日期" width="125">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.interviewDate" type="date" size="small"
            value-format="YYYY-MM-DD" style="width: 100%"
            @update:model-value="(v: string) => iv.updateRow(row.id, { interviewDate: v ?? '' })" />
          <span v-else>{{ row.interviewDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="访谈方式" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.method || undefined" size="small" clearable
            @change="(v: string) => iv.updateRow(row.id, { method: v as any })">
            <el-option v-for="m in iv.INTERVIEW_METHODS" :key="m" :label="m" :value="m" />
          </el-select>
          <span v-else>{{ row.method }}</span>
        </template>
      </el-table-column>
      <el-table-column label="受访人" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.interviewee" size="small"
            @change="(v: string) => iv.updateRow(row.id, { interviewee: v })" />
          <span v-else>{{ row.interviewee }}</span>
        </template>
      </el-table-column>
      <el-table-column label="职务" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.intervieweeTitle" size="small"
            @change="(v: string) => iv.updateRow(row.id, { intervieweeTitle: v })" />
          <span v-else>{{ row.intervieweeTitle }}</span>
        </template>
      </el-table-column>
      <el-table-column label="主要内容摘要" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small"
            @update:model-value="(v: string) => iv.updateRow(row.id, { summary: v })" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关注事项" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.concerns" size="small"
            @update:model-value="(v: string) => iv.updateRow(row.id, { concerns: v })" />
          <span v-else>{{ row.concerns }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="130">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.conclusion || undefined" size="small" clearable
            @change="(v: string) => iv.updateRow(row.id, { conclusion: v as any })">
            <el-option v-for="c in iv.INTERVIEW_CONCLUSIONS" :key="c" :label="c" :value="c" />
          </el-select>
          <el-tag v-else :type="conclusionTag(row.conclusion)" size="small">{{ row.conclusion }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="iv.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 访谈汇总说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">访谈汇总说明</span>
        </div>
      </template>
      <el-input v-model="iv.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="汇总供应商访谈发现，说明异常/疑点行的处理及交易真实性判断……" />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="audit-card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNoteText"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述所执行的供应商访谈核查程序、测试范围与结果，以及发现的异常事项及其处理。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="audit-card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusionText"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2InterviewSummary, type InterviewConclusion } from '../../composables/useF2InterviewSummary'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{ wpId?: string; allResponses: Map<string, ChecklistResponse>; isReadonly: boolean }>()

const iv = useF2InterviewSummary({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function conclusionTag(c: InterviewConclusion | ''): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (c === '无异常') return 'success'
  if (c === '存在疑点') return 'warning'
  if (c === '需进一步核查') return 'info'
  if (c === '异常') return 'danger'
  return ''
}

// ─── 审计说明 / 审计结论（逐 sheet 打磨补齐，持久化走 f2-spe:save-items）──────
const NOTE_KEY = 'F2-71-audit-note'
const CONCLUSION_KEY = 'F2-71-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')
function persistSpeAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  persistSpeAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  persistSpeAudit(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})
</script>

<style scoped>
.f2-interview-summary { padding: 12px 16px; font-size: var(--wp-font-size, 13px); background: linear-gradient(180deg, #f8fafc 0%, #fff 100px); border-radius: 8px; }
.f2-interview-summary :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-interview-summary :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-header h3 { margin: 0; font-size: 16px; display: inline; }
.code { font-size: 12px; color: #909399; margin-left: 8px; }
.summary-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.search { width: 200px; }
.supplier-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
:deep(.warn-row) { background: #fdf6ec !important; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; border-radius: 8px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.audit-card-header { font-weight: 600; font-size: 14px; color: #303133; }
</style>
