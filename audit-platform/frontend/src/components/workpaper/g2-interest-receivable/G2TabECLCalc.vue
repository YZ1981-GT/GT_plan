<template>
  <div class="g2-ecl-calc">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表独立测算预期信用损失（ECL），验证企业坏账准备计提的合理性。两个区段Tab共享同一组行数据，切换时行保持同步。</p>
        <p>2. 阶段判定优先级：已减值→Stage3 &gt; 显著增加→Stage2 &gt; 否则 Stage1。</p>
        <p>3. 适用PD：Stage1 用 12个月PD，Stage2/3 用整个存续期PD。</p>
        <p>4. ECL = EAD × 适用PD × LGD；差异 = 测算ECL - 企业计提；灰色底纹列为自动计算列。</p>
        <p>5. 差异/企业计提 &gt; 10% 时橙色高亮，须重点关注。</p>
        <p>6. 依据：CAS 22《金融工具确认和计量》预期信用损失（ECL）三阶段模型。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：独立测算应收利息预期信用损失，验证企业坏账准备计提金额与阶段划分的合理性与充分性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-7 坏账准备测算</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ecl.addRow()">新增行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-7" /></span>
        <el-tag size="small" type="info">共 {{ ecl.dataRows.value.length }} 行</el-tag>
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
      <el-table-column label="划分阶段" width="100" align="center" class-name="auto-calc-col">
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
      <el-table-column label="适用PD" width="100" align="right" class-name="auto-calc-col">
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
      <el-table-column label="ECL金额" width="120" align="right" class-name="auto-calc-col">
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
      <el-table-column label="差异" width="110" align="right" class-name="auto-calc-col">
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

  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { useG2ECLCalc } from '../../composables/useG2ECLCalc'
import GtIndexChip from '../GtIndexChip.vue'
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
.g2-ecl-calc :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.g2-ecl-calc :deep(.el-table .cell) { font-size: 13px !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.variance-warn { color: #e6a23c; font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
