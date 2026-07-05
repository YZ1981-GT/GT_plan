<template>
  <div class="g2-bad-debt">
    <div class="section-head">
      <h3 class="sheet-title">G2-3 坏账准备明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="bd.addRow()">新增行</el-button>
        <el-button size="small" @click="openReviewDialog('G2-3-bad-debt')">💬复核</el-button>
      </div>
    </div>

    <el-table :data="bd.dataRows.value" border size="small" max-height="500">
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
      <el-table-column label="投资标的" width="130" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
            @change="(v: string) => bd.updateCell(row.id, 'investTarget', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.closingBalance" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'closingBalance', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="减值阶段" width="100">
        <template #default="{ row }">
          <el-select :model-value="row.eclStage" size="small" :disabled="isReadonly"
            @change="(v: string) => bd.updateCell(row.id, 'eclStage', v)">
            <el-option v-for="opt in stageOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="转移方向" width="90">
        <template #default="{ row }">
          <el-select :model-value="row.transferDirection" size="small" :disabled="isReadonly"
            @change="(v: string) => bd.updateCell(row.id, 'transferDirection', v)">
            <el-option v-for="opt in transferOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="12个月PD" width="100" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.pd12Month" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="6"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'pd12Month', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="存续期PD" width="100" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.pdLifetime" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="6"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'pdLifetime', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="LGD" width="90" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.lgd" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="4"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'lgd', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="EAD" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.ead" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'ead', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="ECL金额" width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="ECL = EAD × 适用PD × LGD">{{ fmtNum(row.eclAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="企业计提" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.companyProvision" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'companyProvision', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="差异 = ECL金额 - 企业计提">{{ fmtNum(row.variance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期ECL" width="110" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.previousECL" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'previousECL', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="本期变动" width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="本期变动 = 本期ECL - 上期ECL">{{ fmtNum(row.periodChange) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转入" width="100" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.transferIn" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'transferIn', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="转出" width="100" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.transferOut" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'transferOut', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="核销" width="100" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.writeOff" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'writeOff', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="收回" width="100" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.recovery" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => bd.updateCell(row.id, 'recovery', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => bd.updateCell(row.id, 'remark', v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="bd.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        期末余额 {{ fmtNum(bd.totals.value.closingBalance) }} ·
        ECL {{ fmtNum(bd.totals.value.eclAmount) }} ·
        企业计提 {{ fmtNum(bd.totals.value.companyProvision) }} ·
        差异 {{ fmtNum(bd.totals.value.variance) }} ·
        本期变动 {{ fmtNum(bd.totals.value.periodChange) }}
      </div>
    </div>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>ECL = EAD × 适用PD × LGD（Stage1用12个月PD，Stage2/3用整个存续期PD）</li>
        <li>差异 = 测算ECL - 企业计提</li>
        <li>本期变动 = 本期ECL - 上期ECL</li>
        <li>转移方向标记阶段间的迁移方向（如1→2表示从正常转为关注）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import {
  useG2BadDebtDetail,
  STAGE_OPTIONS,
  TRANSFER_DIRECTION_OPTIONS,
} from '../../composables/useG2BadDebtDetail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const bd = useG2BadDebtDetail({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const stageOptions = STAGE_OPTIONS
const transferOptions = TRANSFER_DIRECTION_OPTIONS

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g2-bad-debt { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
