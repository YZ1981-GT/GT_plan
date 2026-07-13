<template>
  <div class="g2-bad-debt">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示应收利息减值准备（预期信用损失 ECL）明细，验证计提充分性与阶段划分恰当性。</p>
        <p>2. ECL = EAD × 适用PD × LGD（Stage1 用 12个月PD，Stage2/3 用整个存续期PD）。</p>
        <p>3. 差异 = 测算ECL - 企业计提；本期变动 = 本期ECL - 上期ECL。</p>
        <p>4. 灰色底纹列为自动计算列；转移方向标记阶段间迁移（如 1→2 表示由正常转为关注）。</p>
        <p>5. 依据：CAS 22《金融工具确认和计量》预期信用损失（ECL）三阶段模型。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证应收利息减值准备（ECL）计提的充分性、阶段划分的恰当性，以及减值变动的准确性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-3 坏账准备明细表</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="bd.addRow()">新增行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-3" /></span>
        <el-tag size="small" type="info">共 {{ bd.dataRows.value.length }} 行</el-tag>
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
      <el-table-column label="ECL金额" width="120" align="right" class-name="auto-calc-col">
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
      <el-table-column label="差异" width="110" align="right" class-name="auto-calc-col">
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
      <el-table-column label="本期变动" width="110" align="right" class-name="auto-calc-col">
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

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject, onMounted } from 'vue'
import {
  useG2BadDebtDetail,
  STAGE_OPTIONS,
  TRANSFER_DIRECTION_OPTIONS,
} from '../composables/useG2BadDebtDetail'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

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

// ─── 审计说明 / 审计结论（持久化）───────────────────────────────────────────
const NOTE_KEY = 'G2-3-audit-note'
const CONCLUSION_KEY = 'G2-3-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<style scoped>
.g2-bad-debt { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-bad-debt :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g2-bad-debt :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
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
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
