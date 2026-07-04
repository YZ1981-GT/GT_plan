<template>
  <div class="f2-interview-summary">
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

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="iv.addRow()">+ 新增访谈</el-button>
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
      <el-input v-model="iv.searchQuery.value" size="small" placeholder="搜索供应商/受访人" clearable class="search" />
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

    <footer class="footer">
      <h4>访谈汇总说明</h4>
      <el-input v-model="iv.auditNote.value" type="textarea" :rows="2" :disabled="isReadonly" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
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
</script>

<style scoped>
.f2-interview-summary { padding: 12px 16px; font-size: 13px; background: linear-gradient(180deg, #f8fafc 0%, #fff 100px); border-radius: 8px; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-header h3 { margin: 0; font-size: 16px; display: inline; }
.code { font-size: 12px; color: #909399; margin-left: 8px; }
.summary-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.toolbar { display: flex; gap: 8px; margin-bottom: 10px; }
.search { width: 200px; }
.supplier-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
:deep(.warn-row) { background: #fdf6ec !important; }
.footer { margin-top: 14px; }
.footer h4 { margin: 0 0 8px; font-size: 13px; color: #606266; }
</style>
