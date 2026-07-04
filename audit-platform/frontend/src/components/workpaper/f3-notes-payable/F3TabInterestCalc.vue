<script setup lang="ts">

/** F3TabInterestCalc — F3-4 带息票据利息测算 | Task 6.3, 9.3 */

import { ref, toRef, inject, type Ref } from 'vue'

import { ElMessage, ElMessageBox } from 'element-plus'

import http from '@/utils/http'

import { useF3InterestCalc, type F3NoteOcrFields } from '../composables/useF3InterestCalc'

import { useF3AiGenerate } from '../composables/useF3AiGenerate'

import F3ImportExportToolbar from './F3ImportExportToolbar.vue'



const props = defineProps<{

  wpId: string

  projectId: string

  allResponses: Map<string, any>

  isReadonly: boolean

}>()



const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)

function onImported() { reloadWorkpaperData?.() }



function fmt(v: number): string {

  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

}



const { rows, totals, auditConclusion, addRow, removeRow, updateCell, rowClassName, mergeOcrFields } = useF3InterestCalc({

  wpId: toRef(props, 'wpId') as Ref<string>,

  projectId: toRef(props, 'projectId') as Ref<string>,

  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,

  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,

})



const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)



async function generateAiConclusion() {

  if (props.isReadonly) return

  const text = await generateAndConfirm(

    'interest-conclusion',

    auditConclusion.value,

    {

      rowCount: rows.value.length,

      totalFaceValue: totals.value.faceValue,

      totalPayableInterest: totals.value.payableInterest,

      totalVariance: totals.value.variance,

    },

    'AI 生成 · 利息测算结论',

  )

  if (text) auditConclusion.value = text

}



const ocrLoadingId = ref<string | null>(null)



async function handleNoteOcr(rowId: string, file: File) {

  if (props.isReadonly) return

  ocrLoadingId.value = rowId

  const formData = new FormData()

  formData.append('file', file)



  try {

    const res = await http.post(

      `/api/workpapers/${props.wpId}/f3/contract-ocr`,

      formData,

      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,

    )

    const data = res.data?.data ?? res.data

    const { extracted_fields: fields, confidence } = data



    const fieldSummary = Object.entries(fields || {})

      .filter(([, v]) => v != null && v !== '' && v !== 0)

      .map(([k, v]) => `${k}: ${v}`)

      .join('\n')



    await ElMessageBox.confirm(

      `OCR识别完成（置信度: ${((confidence || 0) * 100).toFixed(0)}%）\n\n提取字段：\n${fieldSummary || '（未提取到有效信息）'}\n\n是否将提取结果填入当前行？`,

      '票据OCR提取结果',

      { confirmButtonText: '填入（覆盖空字段）', cancelButtonText: '取消', type: 'info' },

    )

    mergeOcrFields(rowId, fields as F3NoteOcrFields, false)

    ElMessage.success('OCR结果已填入')

  } catch (err: any) {

    if (err !== 'cancel' && err?.message !== 'cancel') {

      ElMessage.warning('OCR识别失败，请手动填写')

    }

  } finally {

    ocrLoadingId.value = null

  }

}

</script>



<template>

  <div class="f3-tab-interest">

    <details class="guidance-details"><summary>📋 编制提示</summary><p>应付利息 = 面值×利率/100×应计天数/360。差异&gt;100元橙色高亮。📎列可上传票据进行OCR识别。</p></details>

    <div class="toolbar">

      <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>

      <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-4" :disabled="isReadonly" @imported="onImported" />

    </div>

    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="font-size:13px">

      <el-table-column prop="seq" label="序号" width="55" />

      <el-table-column label="📎" width="45" align="center">

        <template #default="{ row }">

          <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly || ocrLoadingId === row.rowId"

            @change="(f: any) => handleNoteOcr(row.rowId, f.raw || f)">

            <el-button link size="small" :loading="ocrLoadingId === row.rowId">📎</el-button>

          </el-upload>

        </template>

      </el-table-column>

      <el-table-column label="出票人" min-width="100">

        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.drawer" size="small" @change="(v: string) => updateCell(row.rowId, 'drawer', v)" /><span v-else>{{ row.drawer }}</span></template>

      </el-table-column>

      <el-table-column label="面值" width="110" align="right">

        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>

      </el-table-column>

      <el-table-column label="利率%" width="80" align="right">

        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.interestRate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'interestRate', v ?? 0)" /><span v-else>{{ row.interestRate }}</span></template>

      </el-table-column>

      <el-table-column label="计息起始" width="110">

        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.interestStart" size="small" @change="(v: string) => updateCell(row.rowId, 'interestStart', v)" /><span v-else>{{ row.interestStart }}</span></template>

      </el-table-column>

      <el-table-column label="计息截止" width="110">

        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.interestEnd" size="small" @change="(v: string) => updateCell(row.rowId, 'interestEnd', v)" /><span v-else>{{ row.interestEnd }}</span></template>

      </el-table-column>

      <el-table-column label="应计天数" width="90" align="right"><template #default="{ row }"><span class="formula-cell">{{ row.accruedDays }}</span></template></el-table-column>

      <el-table-column label="应付利息" width="110" align="right"><template #default="{ row }"><span class="formula-cell">{{ fmt(row.payableInterest) }}</span></template></el-table-column>

      <el-table-column label="企业计提" width="110" align="right">

        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.bookInterest" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'bookInterest', v ?? 0)" /><span v-else>{{ fmt(row.bookInterest) }}</span></template>

      </el-table-column>

      <el-table-column label="差异" width="100" align="right"><template #default="{ row }"><span class="formula-cell">{{ fmt(row.variance) }}</span></template></el-table-column>

      <el-table-column label="操作" width="55"><template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template></el-table-column>

    </el-table>

    <div class="subtotal">合计 — 面值 {{ fmt(totals.faceValue) }} | 应付利息 {{ fmt(totals.payableInterest) }} | 计提 {{ fmt(totals.bookInterest) }} | 差异 {{ fmt(totals.variance) }}</div>

    <el-card shadow="never" class="audit-card">
      <template #header>
        <div class="audit-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion">AI 辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :rows="3" :disabled="isReadonly" />
    </el-card>

  </div>

</template>



<style scoped>

.f3-tab-interest { font-size: 13px; }

.toolbar { margin-bottom: 8px; }

.formula-cell { background: #f5f7fa; border-bottom: 1px dashed #c0c4cc; }

:deep(.variance-warn td) { background: #fdf6ec !important; }

.subtotal { margin-top: 8px; text-align: right; font-weight: 600; }

.audit-card { margin-top: 12px; }
.audit-header { display: flex; justify-content: space-between; align-items: center; }

</style>

