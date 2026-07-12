<template>
  <div class="g2-interest-calc">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表独立测算应收利息，验证企业利息计提金额的准确性与完整性。</p>
        <p>2. 应收利息 = 面值 × 票面利率/100 × 计息天数/365（365天基准，非360天）。</p>
        <p>3. 差异 = 测算应收利息 - 企业计提金额；灰色底纹列为自动计算列。</p>
        <p>4. |差异| &gt; 100 元时橙色高亮，须查明原因并做说明。</p>
        <p>5. 测算应与 G2-2 明细表中对应标的利息交叉核对。</p>
        <p>6. 依据：CAS 22《金融工具确认和计量》（实际利率法、应收利息确认）。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过独立测算应收利息，验证企业利息计提金额的准确性与完整性，识别少计或多计风险。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-5 利息测算表</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="calc.addRow()">新增测算行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-5" /></span>
        <el-tag size="small" type="info">共 {{ calc.dataRows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G2-5-interest-calc')">💬复核</el-button>
      </div>
    </div>

    <el-table :data="calc.dataRows.value" border size="small" max-height="500">
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
      <el-table-column label="投资标的" width="140" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
            @change="(v: string) => calc.updateCell(row.id, 'investTarget', v)" />
        </template>
      </el-table-column>
      <el-table-column label="面值/本金" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.faceValue" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => calc.updateCell(row.id, 'faceValue', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="票面利率(%)" width="110" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.couponRate" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="4"
            @update:model-value="(v: number) => calc.updateCell(row.id, 'couponRate', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="计息起始日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.accrualStart" type="date" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => calc.updateCell(row.id, 'accrualStart', v ?? '')" />
        </template>
      </el-table-column>
      <el-table-column label="计息截止日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.accrualEnd" type="date" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => calc.updateCell(row.id, 'accrualEnd', v ?? '')" />
        </template>
      </el-table-column>
      <el-table-column label="计息天数" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="计息天数 = 截止日 - 起始日">{{ row.accruedDays }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应收利息" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="应收利息 = 面值 × 利率/100 × 天数/365">{{ fmtNum(row.calculatedInterest) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="企业计提" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.companyAccrual" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => calc.updateCell(row.id, 'companyAccrual', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="['formula-cell', { 'variance-warn': calc.isVarianceWarning(row) }]"
            title="差异 = 应收利息 - 企业计提">
            {{ fmtNum(row.variance) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => calc.updateCell(row.id, 'remark', v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="calc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">利息测算合计</span>
        面值 {{ fmtNum(calc.totals.value.faceValue) }} ·
        应收利息 {{ fmtNum(calc.totals.value.calculatedInterest) }} ·
        企业计提 {{ fmtNum(calc.totals.value.companyAccrual) }} ·
        差异 {{ fmtNum(calc.totals.value.variance) }}
      </div>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对利息测算的复核结论..." />
    </el-card>

  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { useG2InterestCalc } from '../composables/useG2InterestCalc'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calc = useG2InterestCalc({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const auditConclusion = ref('')

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}

function fillAiDraft() {
  if (props.isReadonly) return
  const t = calc.totals.value
  const draft =
    `经测算，本期应收利息合计 ${t.calculatedInterest.toLocaleString()} 元，` +
    `企业计提 ${t.companyAccrual.toLocaleString()} 元，差异 ${t.variance.toLocaleString()} 元。` +
    (Math.abs(t.variance) < 100
      ? '测算结果与企业账面核对一致，利息计提金额恰当。'
      : '测算结果与企业账面存在差异，需进一步查明原因。')
  auditConclusion.value = auditConclusion.value ? `${auditConclusion.value}\n${draft}` : draft
}
</script>

<style scoped>
.g2-interest-calc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-interest-calc :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g2-interest-calc :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.variance-warn { color: #e6a23c; font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 12px; }
</style>
