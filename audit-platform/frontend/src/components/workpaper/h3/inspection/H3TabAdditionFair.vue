<template>
  <div class="h3-tab-addition-fair">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增检查行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="triggerVoucherSampling">抽凭</el-button>
      <el-dropdown size="small" class="export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item>导出模板</el-dropdown-item>
            <el-dropdown-item>导出数据</el-dropdown-item>
            <el-dropdown-item>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 20列检查表（公允模式） -->
    <el-table :data="fairRows" border size="small" class="audit-table" show-summary :summary-method="getFairSummary">
      <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
      <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
        <template #default="{ row, $index }">
          <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onCellChange($index, 'assetName', row.assetName)" />
        </template>
      </el-table-column>
      <el-table-column prop="date" label="日期" width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.date" size="small" :disabled="isReadonly" @change="onCellChange($index, 'date', row.date)" />
        </template>
      </el-table-column>
      <el-table-column prop="changeType" label="增减类型" width="110">
        <template #default="{ row, $index }">
          <el-select v-model="row.changeType" size="small" :disabled="isReadonly" @change="onCellChange($index, 'changeType', row.changeType)">
            <el-option label="购入" value="购入" />
            <el-option label="自建转入" value="自建转入" />
            <el-option label="自用转入" value="自用转入" />
            <el-option label="处置" value="处置" />
            <el-option label="转出" value="转出" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="fairValue" label="公允价值" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.fairValue" size="small" :disabled="isReadonly" @change="onCellChange($index, 'fairValue', row.fairValue)" />
        </template>
      </el-table-column>
      <el-table-column prop="appraisalBasis" label="评估依据" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.appraisalBasis" size="small" :disabled="isReadonly" @change="onCellChange($index, 'appraisalBasis', row.appraisalBasis)" />
        </template>
      </el-table-column>
      <el-table-column prop="contract" label="合同" width="60" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.contract" :disabled="isReadonly" @change="onCellChange($index, 'contract', row.contract)" />
        </template>
      </el-table-column>
      <el-table-column prop="invoice" label="发票" width="60" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.invoice" :disabled="isReadonly" @change="onCellChange($index, 'invoice', row.invoice)" />
        </template>
      </el-table-column>
      <el-table-column prop="appraisal" label="评估报告" width="70" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.appraisal" :disabled="isReadonly" @change="onCellChange($index, 'appraisal', row.appraisal)" />
        </template>
      </el-table-column>
      <el-table-column prop="titleCert" label="产权证" width="70" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.titleCert" :disabled="isReadonly" @change="onCellChange($index, 'titleCert', row.titleCert)" />
        </template>
      </el-table-column>
      <el-table-column prop="fairValueChange" label="公允价值变动" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.fairValueChange" size="small" :disabled="isReadonly" @change="onCellChange($index, 'fairValueChange', row.fairValueChange)" />
        </template>
      </el-table-column>
      <el-table-column prop="plImpact" label="损益影响" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.plImpact" size="small" :disabled="isReadonly" @change="onCellChange($index, 'plImpact', row.plImpact)" />
        </template>
      </el-table-column>
      <el-table-column label="📎" width="50" align="center">
        <template #default="{ $index }">
          <el-button size="small" text @click="handleOcr($index)">📎</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="审计结论" min-width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="onCellChange($index, 'conclusion', row.conclusion)">
            <el-option label="无异常" value="无异常" />
            <el-option label="需关注" value="需关注" />
            <el-option label="有问题" value="有问题" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- 汇总 -->
    <div class="summary-row">
      <span>公允价值合计：<b>{{ fmtNum(totalFairValue) }}</b></span>
      <span>公允变动合计：<b>{{ fmtNum(totalFairChange) }}</b></span>
      <span>损益影响合计：<b>{{ fmtNum(totalPlImpact) }}</b></span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-5-fair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-5-fair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdditionFair.vue — H3-5 增减检查表（公允价值模式）
 * el-table 20列公允模式+抽凭+OCR+汇总
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH3AdditionCheck } from '../../composables/useH3AdditionCheck'
import { useH3FormData } from '../../composables/useH3FormData'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('fair_value') as any,
})

const {
  fairRows, addFairRow, updateFairCell, totalFairValue, totalFairChange, totalPlImpact,
} = useH3AdditionCheck({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
  measurementModel: ref('fair_value') as any,
})

const conclusion = ref(getValue('H3-5-fair-conclusion') ?? '')

function addRow() { addFairRow() }
function onCellChange(index: number, field: string, value: any) { updateFairCell(index, field, value) }

function triggerVoucherSampling() {
  window.dispatchEvent(new CustomEvent('voucher:open-sampling', {
    detail: { wpId: props.wpId, section: 'H3-5', population: fairRows.value },
  }))
}

/** 📎列 OCR 识别 — POST contract-ocr 端点 → ElMessageBox 确认 → merge */
async function handleOcr(index: number) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.jpg,.jpeg,.png,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const ocrData = res.data?.data ?? res.data
      if (!ocrData) return
      await ElMessageBox.confirm(
        `OCR 识别结果：\n金额: ${ocrData.amount ?? '-'}\n日期: ${ocrData.date ?? '-'}\n对方: ${ocrData.counterparty ?? '-'}\n\n确认填入第 ${index + 1} 行？`,
        'OCR 识别结果确认',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      const row = fairRows.value[index]
      if (row) {
        if (ocrData.amount) updateFairCell(index, 'fairValue', ocrData.amount)
        if (ocrData.date) updateFairCell(index, 'date', ocrData.date)
        if (ocrData.counterparty) updateFairCell(index, 'assetName', ocrData.counterparty)
      }
    } catch (err: any) {
      if (err === 'cancel' || err?.toString?.().includes('cancel')) return
      console.warn('[H3-5 Fair OCR]', err)
    }
  }
  input.click()
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function getFairSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => idx === 0 ? '合计' : '')
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-addition-fair { padding: 16px; font-size: 13px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: 13px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.summary-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
