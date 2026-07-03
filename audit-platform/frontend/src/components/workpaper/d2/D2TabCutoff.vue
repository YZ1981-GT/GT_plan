<script setup lang="ts">
/**
 * D2TabCutoff — 截止测试
 * 8列: 序号|发票号|收入日期|入账日期|金额|跨期判定|结论|备注
 * 自动跨期判定, 红色警告header, 底部汇总
 * 集成 GtCutoffAutoSampling 自动提取（Task 11.1）
 */
import { inject, toRef, computed, type Ref } from 'vue'
import { useD2Cutoff, type CutoffSample } from '../composables/useD2Cutoff'
import GtCutoffAutoSampling from '../cutoff/GtCutoffAutoSampling.vue'
import type { ExtractedVoucher, FillMode } from '../composables/useCutoffAutoSampling'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  bsDate: string
}>()

const emit = defineEmits<{
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.seq || row?.index || 'unknown'
  openReviewDialog(`D2-cutoff-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  samples,
  cutoffCount,
  cutoffTotalAmount,
  hasCutoffIssue,
  addSample,
  removeSample,
  updateCell,
  debounceSave,
} = useD2Cutoff({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as Ref<string>,
})

// ─── 年度计算（从bsDate提取，如 "2025-12-31" → 2025）─────────────────────────

const year = computed(() => {
  if (props.bsDate && props.bsDate.length >= 4) {
    return parseInt(props.bsDate.slice(0, 4), 10)
  }
  return new Date().getFullYear() - 1
})

// ─── 自动提取填充处理 (Task 11.1) ──────────────────────────────────────────

function generateRowId(): string {
  return `ct-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * 将 ExtractedVoucher 映射为 CutoffSample
 * 标记 source: "自动提取"
 */
function mapVoucherToSample(voucher: ExtractedVoucher, seq: number): CutoffSample {
  const debit = voucher.debitAmount ? parseFloat(voucher.debitAmount) : 0
  const credit = voucher.creditAmount ? parseFloat(voucher.creditAmount) : 0
  const amount = debit > 0 ? debit : -credit
  return {
    rowId: generateRowId(),
    seq,
    invoiceNo: voucher.voucherNo || '',
    revenueDate: voucher.voucherDate || '',
    receivableDate: voucher.voucherDate || '',
    amount,
    isCutoff: voucher.cutoffStatus === '可能跨期',
    conclusion: voucher.cutoffStatus || '',
    remark: voucher.remark || '',
    source: '自动提取',
  }
}

/**
 * 处理 GtCutoffAutoSampling @filled 事件
 * 按 fillMode 合并到 samples，触发 debounce 保存
 */
function handleAutoExtractFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }): void {
  const { samples: extracted, fillMode } = payload
  const mapped = extracted.map((v, idx) => mapVoucherToSample(v, idx + 1))

  if (fillMode === 'replace') {
    // 替换模式：清空后填充
    samples.value = mapped.map((s, i) => ({ ...s, seq: i + 1 }))
  } else if (fillMode === 'merge') {
    // 合并模式：按凭证号(invoiceNo)去重
    const existingNos = new Set(samples.value.map(s => s.invoiceNo))
    const newSamples = mapped.filter(s => !existingNos.has(s.invoiceNo))
    const startSeq = samples.value.length + 1
    newSamples.forEach((s, i) => { s.seq = startSeq + i })
    samples.value.push(...newSamples)
  } else {
    // append 模式（默认）：追加到末尾
    const startSeq = samples.value.length + 1
    mapped.forEach((s, i) => { s.seq = startSeq + i })
    samples.value.push(...mapped)
  }

  // 触发 debounce 2s 自动保存
  debounceSave()
}
</script>

<template>
  <div class="d2-tab-cutoff">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample">添加样本</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <!-- 自动提取面板 (Task 11.1) -->
    <div v-if="!isReadonly" class="auto-extract-section">
      <el-collapse>
        <el-collapse-item title="自动提取凭证" name="auto-extract">
          <GtCutoffAutoSampling
            account-code="1122"
            cutoff-direction="post_cutoff"
            :workpaper-id="wpId"
            :project-id="projectId"
            :year="year"
            @filled="handleAutoExtractFilled"
          />
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 跨期警告 -->
    <el-alert v-if="hasCutoffIssue" type="error" :closable="false" class="cutoff-alert">
      发现{{ cutoffCount }}笔跨期，合计金额{{ displayPrefs.fmtAmount(cutoffTotalAmount) }}
    </el-alert>

    <!-- 主表 -->
    <el-table :data="samples" border size="small" style="width: 100%">
      <el-table-column type="index" label="序号" width="60" />
      <el-table-column label="发票号" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.invoiceNo" size="small" @change="(v: string) => updateCell(row.rowId, 'invoiceNo', v)" />
          <span v-else>{{ row.invoiceNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="收入日期" width="140">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.revenueDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @change="(v: string) => updateCell(row.rowId, 'revenueDate', v)"
          />
          <span v-else>{{ row.revenueDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="入账日期" width="140">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.receivableDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @change="(v: string) => updateCell(row.rowId, 'receivableDate', v)"
          />
          <span v-else>{{ row.receivableDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.amount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateCell(row.rowId, 'amount', v)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="跨期判定" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isCutoff" type="danger" size="small">跨期</el-tag>
          <span v-else style="color:#909399">正常</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small" @change="(v: string) => updateCell(row.rowId, 'conclusion', v)" />
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>
      <el-table-column label="来源" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.source === '自动提取'" type="success" size="small">自动提取</el-tag>
          <el-tag v-else-if="row.source === '手动添加'" size="small">手动添加</el-tag>
          <span v-else style="color:#909399">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeSample(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部汇总 -->
    <div class="summary-bar">
      <span>已检查: {{ samples.length }}笔</span>
      <span>跨期笔数: <b :style="{ color: cutoffCount > 0 ? '#f56c6c' : '' }">{{ cutoffCount }}</b></span>
      <span>跨期金额: {{ displayPrefs.fmtAmount(cutoffTotalAmount) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-cutoff { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.auto-extract-section { margin-bottom: 12px; }
.auto-extract-section :deep(.el-collapse-item__header) { font-size: 13px; font-weight: 500; }
.cutoff-alert { margin-bottom: 12px; }
.summary-bar {
  display: flex; gap: 24px; padding: 8px 12px; margin-top: 10px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px;
}
</style>
