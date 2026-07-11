<template>
  <div class="l4-tab-equity-liab-check">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-5 权益与负债划分检查表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleExecute">
          执行分拆计算
        </el-button>
        <el-button size="small" @click="handleAI('equityLiab')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>CAS 37 复合金融工具分拆：</strong>
        可转债等含权益成分的金融工具需分拆。先按同期限、无转换权的类似工具市场利率折现确定负债成分（NPV），
        权益成分 = 发行总额 − 负债成分现值。若权益成分<0则标记"分拆异常"（红色警告）。
      </div>
    </div>

    <!-- ═══ 划分检查表 ═══ -->
    <el-table
      :data="computedRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
    >
      <el-table-column type="index" label="#" width="50" align="center" />

      <el-table-column prop="instrumentName" label="工具名称" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.instrumentName" size="small" @change="(val: string) => onUpdate($index, 'instrumentName', val)" />
          <span v-else>{{ row.instrumentName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="发行总额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.totalProceeds" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'totalProceeds', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.totalProceeds) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="面值" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'faceValue', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.faceValue) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="票面利率(%)" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.couponRate * 100" :controls="false" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'couponRate', (val ?? 0) / 100)" />
          <span v-else>{{ (row.couponRate * 100).toFixed(4) }}%</span>
        </template>
      </el-table-column>

      <el-table-column label="市场利率(%)" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.marketRate * 100" :controls="false" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'marketRate', (val ?? 0) / 100)" />
          <span v-else>{{ (row.marketRate * 100).toFixed(4) }}%</span>
        </template>
      </el-table-column>

      <el-table-column label="期限(年)" min-width="80" align="center">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.periods" :controls="false" :min="1" size="small" style="width:100%" @change="(val: number | undefined) => onUpdate($index, 'periods', val ?? 1)" />
          <span v-else>{{ row.periods }}</span>
        </template>
      </el-table-column>

      <el-table-column label="付息方式" min-width="130">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" :model-value="row.paymentType" size="small" style="width:100%" @change="(val: string) => onUpdate($index, 'paymentType', val)">
            <el-option label="分期付息" value="installment" />
            <el-option label="到期一次还本付息" value="bullet" />
          </el-select>
          <span v-else>{{ row.paymentType === 'bullet' ? '到期一次' : '分期付息' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="负债成分" min-width="130" align="right">
        <template #header>
          <el-tooltip content="未来现金流按市场利率折现的现值" placement="top">
            <span class="formula-col-header">负债成分</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.liabilityComponent) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="权益成分" min-width="130" align="right">
        <template #header>
          <el-tooltip content="发行总额 − 负债成分" placement="top">
            <span class="formula-col-header">权益成分</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', row.isAbnormal ? 'text-danger-bold' : '']">
            {{ fmtAmount(row.equityComponent) }}
          </span>
          <el-tag v-if="row.isAbnormal" type="danger" size="small" style="margin-left:4px">异常</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="划分依据" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.classificationBasis" size="small" @change="(val: string) => onUpdate($index, 'classificationBasis', val)" />
          <span v-else>{{ row.classificationBasis || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 汇总 ═══ -->
    <div class="summary-bar">
      <span>发行总额：<strong>{{ fmtAmount(summary.totalProceeds) }}</strong></span>
      <span>负债成分合计：<strong>{{ fmtAmount(summary.totalLiability) }}</strong></span>
      <span>权益成分合计：<strong :class="summary.totalEquity < 0 ? 'text-danger' : ''">{{ fmtAmount(summary.totalEquity) }}</strong></span>
      <span v-if="summary.abnormalCount > 0" class="text-danger">⚠ 异常 {{ summary.abnormalCount }} 项</span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写权益负债划分审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>仅含权益成分的复合工具（如可转债）需要分拆</li>
        <li>普通债券无需分拆（全额归负债成分）</li>
        <li>市场利率取同期限、无转换权的类似信用工具利率</li>
        <li>权益成分<0说明分拆参数有误，需核实市场利率或现金流</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabEquityLiabCheck — L4-5 权益与负债划分检查表
 *
 * Requirements: 7.1-7.5
 * - 复合金融工具分拆
 * - 权益成分=发行总额−负债成分现值
 * - 权益成分<0红色警告
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { useL4EquityLiabCheck, type L4EquityLiabRow } from '../../composables/useL4EquityLiabCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const checkRows = ref<L4EquityLiabRow[]>([])

const {
  computedRows,
  summary,
  abnormalRows,
  updateRow,
  executeClassification,
} = useL4EquityLiabCheck(formData, checkRows)

const auditNote = ref('')

function saveAuditNote() {
  formData.debouncedSave('L4-5-auditNote', { remark: auditNote.value || null })
}

function onUpdate(index: number, field: keyof L4EquityLiabRow, value: string | number) {
  updateRow(index, field, value)
}

function handleExecute() {
  executeClassification()
}

function getRowClassName({ row }: { row: any }) {
  return row.isAbnormal ? 'abnormal-row' : ''
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l4-tab-equity-liab-check { padding: 12px; font-size: 13px; }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px;
}
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.text-danger { color: #f56c6c; }
.text-danger-bold { color: #f56c6c !important; font-weight: 700; }

:deep(.el-table) { font-size: 13px; }
:deep(.abnormal-row) { background-color: #fef0f0 !important; }

.summary-bar {
  display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px;
  background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266;
}

.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
