<template>
  <div class="h8-tab-simplified-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：核实短期租赁(≤12月)及低价值资产租赁(≤4万)简化处理的适用性，确认不符合简化条件的租赁已确认使用权资产与租赁负债（CAS21第32条）。" />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第32条简化处理：短期租赁(≤12月)或低价值资产租赁(≤4万)可选择不确认使用权资产和租赁负债，直接计入当期费用。不符合条件的应确认使用权资产。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-13" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 检查表 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="section-title">
          <span>简化处理检查（H8-13，99行18列12公式）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'simplified')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'simplified')">复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border size="small" class="formula-table"
        :row-class-name="getRowClassName" show-summary :summary-method="getSummary">
        <el-table-column prop="contractNo" label="合同号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
              @change="updateCell(row.rowId, 'contractNo', row.contractNo)" />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="承租资产" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
              @change="updateCell(row.rowId, 'assetName', row.assetName)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessor" label="出租方" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessor" size="small"
              @change="updateCell(row.rowId, 'lessor', row.lessor)" />
            <span v-else>{{ row.lessor }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseTermMonths" label="租赁期(月)" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.leaseTermMonths" :controls="false"
              size="small" :min="0"
              @change="(v: number | undefined) => updateCell(row.rowId, 'leaseTermMonths', v)" />
            <span v-else>{{ row.leaseTermMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualRental" label="年租金" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.annualRental" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'annualRental', v)" />
            <span v-else>{{ fmtAmt(row.annualRental) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="newAssetValue" label="全新价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.newAssetValue" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'newAssetValue', v)" />
            <span v-else>{{ fmtAmt(row.newAssetValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="短期(≤12月)" width="100" align="center" class-name="formula-col">
          <template #default="{ row }">
            <el-tag :type="row.isShortTerm ? 'success' : 'info'" size="small">
              {{ row.isShortTerm ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="低价值(≤4万)" width="110" align="center" class-name="formula-col">
          <template #default="{ row }">
            <el-tag :type="row.isLowValue ? 'success' : 'info'" size="small">
              {{ row.isLowValue ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="简化类型" width="110" align="center" class-name="formula-col">
          <template #default="{ row }">
            <el-tag v-if="row.simplifiedType === '不符合'" type="danger" size="small">不符合</el-tag>
            <el-tag v-else-if="row.simplifiedType" type="success" size="small">{{ row.simplifiedType }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="expenseAmount" label="费用确认" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.expenseAmount" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'expenseAmount', v)" />
            <span v-else>{{ fmtAmt(row.expenseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="核查结论" min-width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small"
              @change="updateCell(row.rowId, 'conclusion', row.conclusion)">
              <el-option label="符合简化条件" value="符合简化条件" />
              <el-option label="不符合，应确认ROU" value="不符合，应确认ROU" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="deleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 底部统计卡片 -->
    <div class="stats-row">
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">简化处理笔数</div>
        <div class="stat-value ok">{{ simplifiedCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">简化处理年租金合计</div>
        <div class="stat-value">{{ fmtAmt(totalAnnualRental) }} 元</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">应转为使用权资产笔数</div>
        <div class="stat-value" :class="mustRecognizeCount > 0 ? 'warn' : 'ok'">{{ mustRecognizeCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">全部年租金合计</div>
        <div class="stat-value">{{ fmtAmt(totalAllRental) }} 元</div>
      </el-card>
    </div>

    <!-- 不合规提示 -->
    <el-alert v-if="mustRecognizeCount > 0" type="error" :closable="false" show-icon class="noncompliant-alert">
      <template #title>
        {{ mustRecognizeCount }}笔租赁不符合简化条件，应确认使用权资产和租赁负债
      </template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }" placeholder="请输入审计说明..." @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }" placeholder="请输入审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>短期租赁：剩余租赁期≤12个月（含续租选择权不计入）</li>
        <li>低价值：标的资产全新状态下价值≤40,000元</li>
        <li>简化处理：不确认ROU和租赁负债，租金直接计入当期费用</li>
        <li>不符合简化条件的，红色高亮提示应确认使用权资产</li>
        <li>分租赁（转租方）不能选择短期简化</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabSimplifiedCheck.vue — H8-13 简化处理的租赁检查表
 * 99行18列12公式，自动判断短期/低价值，不合规红色高亮，底部统计
 * Spec: Task 4.9 | Requirements: 8.1-8.4
 */
import { ref, toRef, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8SimplifiedCheck } from '../../composables/useH8SimplifiedCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const {
  rows, simplifiedCount, mustRecognizeCount, totalAnnualRental, totalAllRental,
  addRow, deleteRow, updateCell,
} = useH8SimplifiedCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ── 审计说明 / 审计结论（持久化 checklist_responses，conclusion:null）──
const AUDIT_NOTE_KEY = 'H8-simplified-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-simplified-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入合同号', '新增检查行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：LEASE-2024-001',
  })
  if (value) addRow(value)
}

function getRowClassName({ row }: { row: any }) {
  if (row.simplifiedType === '不符合') return 'noncompliant-row'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return `合计 ${rows.value.length} 笔`
    if (idx === 4) return fmtAmt(totalAllRental.value)
    return ''
  })
}
</script>

<style scoped>
.h8-tab-simplified-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.table-card { margin-bottom: 16px; }
.formula-table { font-size: var(--wp-font-size, 13px); }
.formula-table :deep(.formula-col) { background: #f0fdf4; }
.formula-table :deep(.noncompliant-row) { background: #fef2f2 !important; }

.stats-row { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.stat-card { flex: 1; min-width: 160px; text-align: center; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.stat-value { font-size: 20px; font-weight: 700; color: var(--el-color-primary); }
.stat-value.ok { color: #16a34a; }
.stat-value.warn { color: #dc2626; }

.noncompliant-alert { margin: 12px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
