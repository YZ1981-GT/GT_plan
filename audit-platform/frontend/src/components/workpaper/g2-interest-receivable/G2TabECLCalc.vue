<template>
  <div class="g2-ecl-calc">
    <div class="section-head">
      <h3 class="sheet-title">G2-7 坏账准备测算</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ecl.addRow()">新增行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G2-7-ecl-calc')">💬复核</el-button>
      </div>
    </div>

    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 阶段划分区段 -->
    <el-table v-if="segment === 'stage'" :data="ecl.dataRows.value" border size="small" max-height="500">
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
      <el-table-column label="投资标的" width="140" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
            @change="(v: string) => ecl.updateCell(row.id, 'investTarget', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.closingBalance" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => ecl.updateCell(row.id, 'closingBalance', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="信用等级" width="100">
        <template #default="{ row }">
          <el-input :model-value="row.creditRating" size="small" :disabled="isReadonly"
            @change="(v: string) => ecl.updateCell(row.id, 'creditRating', v)" />
        </template>
      </el-table-column>
      <el-table-column label="显著增加" width="90" align="center">
        <template #default="{ row }">
          <el-checkbox :model-value="row.significantIncrease" :disabled="isReadonly"
            @update:model-value="(v: boolean) => ecl.updateCell(row.id, 'significantIncrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="已减值" width="80" align="center">
        <template #default="{ row }">
          <el-checkbox :model-value="row.isImpaired" :disabled="isReadonly"
            @update:model-value="(v: boolean) => ecl.updateCell(row.id, 'isImpaired', v)" />
        </template>
      </el-table-column>
      <el-table-column label="划分阶段" width="100" align="center">
        <template #default="{ row }">
          <span class="formula-cell" title="已减值→3, 显著增加→2, 否则→1">
            Stage{{ row.determinedStage }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="上期阶段" width="100" align="center">
        <template #default="{ row }">
          <el-select :model-value="row.previousStage" size="small" :disabled="isReadonly"
            @change="(v: number) => ecl.updateCell(row.id, 'previousStage', v)">
            <el-option :value="1" label="Stage1" />
            <el-option :value="2" label="Stage2" />
            <el-option :value="3" label="Stage3" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="变动说明" width="140">
        <template #default="{ row }">
          <el-input :model-value="row.stageChangeNote" size="small" :disabled="isReadonly"
            @change="(v: string) => ecl.updateCell(row.id, 'stageChangeNote', v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="ecl.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ECL测算区段 -->
    <el-table v-else :data="ecl.dataRows.value" border size="small" max-height="500">
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
      <el-table-column label="投资标的" prop="investTarget" width="140" fixed />
      <el-table-column label="12个月PD" width="110" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.pd12Month" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="6"
            @update:model-value="(v: number) => ecl.updateCell(row.id, 'pd12Month', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="存续期PD" width="110" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.pdLifetime" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="6"
            @update:model-value="(v: number) => ecl.updateCell(row.id, 'pdLifetime', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="适用PD" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="Stage1→12个月PD / Stage2,3→存续期PD">
            {{ row.applicablePD.toFixed(6) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="LGD" width="90" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.lgd" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="4"
            @update:model-value="(v: number) => ecl.updateCell(row.id, 'lgd', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="EAD" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.ead" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => ecl.updateCell(row.id, 'ead', v ?? 0)" />
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
            @update:model-value="(v: number) => ecl.updateCell(row.id, 'companyProvision', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="110" align="right">
        <template #default="{ row }">
          <span :class="['formula-cell', { 'variance-warn': ecl.isVarianceWarning(row) }]"
            title="差异 = ECL金额 - 企业计提">
            {{ fmtNum(row.eclVariance) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="测算结论" width="140">
        <template #default="{ row }">
          <el-input :model-value="row.conclusion" size="small" :disabled="isReadonly"
            @change="(v: string) => ecl.updateCell(row.id, 'conclusion', v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="ecl.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        期末余额 {{ fmtNum(ecl.totals.value.closingBalance) }} ·
        EAD {{ fmtNum(ecl.totals.value.ead) }} ·
        ECL {{ fmtNum(ecl.totals.value.eclAmount) }} ·
        企业计提 {{ fmtNum(ecl.totals.value.companyProvision) }} ·
        差异 {{ fmtNum(ecl.totals.value.eclVariance) }}
      </div>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对ECL测算的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>阶段判定优先级：已减值→Stage3 > 显著增加→Stage2 > 否则Stage1</li>
        <li>适用PD：Stage1用12个月PD，Stage2/3用整个存续期PD</li>
        <li>ECL = EAD × 适用PD × LGD</li>
        <li>差异/企业计提 > 10% 时橙色高亮，需重点关注</li>
        <li>两个区段Tab共享同一组行数据，切换时行保持同步</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { useG2ECLCalc } from '../../composables/useG2ECLCalc'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const ecl = useG2ECLCalc({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const segment = ref<'stage' | 'ecl'>('stage')
const segmentOptions = [
  { label: '阶段划分', value: 'stage' },
  { label: 'ECL测算', value: 'ecl' },
]

const auditConclusion = ref('')

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}

function fillAiDraft() {
  if (props.isReadonly) return
  const t = ecl.totals.value
  const draft =
    `经独立测算，本期应收利息ECL合计 ${t.eclAmount.toLocaleString()} 元，` +
    `企业计提 ${t.companyProvision.toLocaleString()} 元，差异 ${t.eclVariance.toLocaleString()} 元。` +
    (Math.abs(t.eclVariance) / Math.max(Math.abs(t.companyProvision), 1) < 0.10
      ? '测算结果与企业计提基本一致，坏账准备计提金额恰当。'
      : '测算结果与企业计提存在较大差异，需进一步分析原因。')
  auditConclusion.value = auditConclusion.value ? `${auditConclusion.value}\n${draft}` : draft
}
</script>

<style scoped>
.g2-ecl-calc { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.variance-warn { color: #e6a23c; font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
