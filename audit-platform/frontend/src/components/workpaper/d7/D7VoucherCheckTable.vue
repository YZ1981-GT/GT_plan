<template>
  <el-table :data="rows" size="small" border max-height="400" :row-class-name="rowClassName">
    <!-- 阶段 / 来源 / 配对（共享回填函数写的行元数据，spec voucher-identity-writeback-and-audit-phase 任务 10） -->
    <el-table-column label="来源" width="150">
      <template #default="{ row }">
        <VoucherRowMetaCell :row="row" :locked="!!isRowLocked?.(row)" :project-id="projectId ?? ''" :year="year ?? null" />
      </template>
    </el-table-column>
    <el-table-column v-for="col in LEAD_COLUMNS" :key="col.field" :label="col.label" :width="col.width">
      <template #default="{ row }">
        <WpCommitInput v-if="!rowReadonly(row)" :model-value="row[col.field]" size="small" @change="(v: string) => emit('update', row.rowId, col.field, v)" />
        <span v-else>{{ row[col.field] }}</span>
        <GtIndexChip
          v-if="block === 'post' && col.field === 'counterAccount' && String(row.counterAccount || '').includes('主营业务收入')"
          value="wp:D4" :context-project-id="projectId" style="margin-left:4px"
        />
      </template>
    </el-table-column>
    <el-table-column v-for="col in amountColumns" :key="col.field" :label="col.label" width="110" align="right">
      <template #default="{ row }">
        <WpAmountInput v-if="!rowReadonly(row)" :model-value="row[col.field]" size="small" style="width:100%" @change="(v: number) => emit('update', row.rowId, col.field, v ?? 0)" />
        <span v-else>{{ fmtAmt(row[col.field]) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="支持性文件" width="110">
      <template #default="{ row }">
        <WpCommitInput v-if="!rowReadonly(row)" :model-value="row.supportDocs" size="small" @change="(v: string) => emit('update', row.rowId, 'supportDocs', v)" />
        <span v-else>{{ row.supportDocs }}</span>
      </template>
    </el-table-column>
    <el-table-column label="核对内容" align="center">
      <el-table-column v-for="i in 5" :key="i" :label="String(i)" width="42" align="center">
        <template #default="{ row }">
          <el-checkbox :model-value="!!row.checkItems?.[i - 1]" :disabled="rowReadonly(row)" @change="(v: boolean) => emit('toggle', row.rowId, i - 1, v)" />
        </template>
      </el-table-column>
    </el-table-column>
    <el-table-column label="索引号" width="90">
      <template #default="{ row }">
        <WpCommitInput v-if="!rowReadonly(row)" :model-value="row.indexRef" size="small" @change="(v: string) => emit('update', row.rowId, 'indexRef', v)" />
        <span v-else>{{ row.indexRef }}</span>
      </template>
    </el-table-column>
    <el-table-column label="是否异常" width="70" align="center">
      <template #default="{ row }">
        <el-checkbox :model-value="row.isAbnormal" :disabled="rowReadonly(row)" @change="(v: boolean) => emit('update', row.rowId, 'isAbnormal', v)" />
      </template>
    </el-table-column>
    <el-table-column label="备注说明" min-width="120">
      <template #default="{ row }">
        <WpCommitInput v-if="!rowReadonly(row)" :model-value="row.remark" size="small" @change="(v: string) => emit('update', row.rowId, 'remark', v)" />
        <span v-else>{{ row.remark }}</span>
      </template>
    </el-table-column>
    <el-table-column v-if="!isReadonly" label="" width="50" align="center">
      <template #default="{ row }">
        <el-button type="danger" text size="small" :disabled="!!isRowLocked?.(row)" @click="emit('remove', row.rowId)">删</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
/**
 * D7-7 合同负债检查表的一个区（本期增减变动 / 期后结转），列按模板 R16-R17 / R33-R34：
 * 客户名称 · 记账凭证（日期 / 凭证编号 / 业务内容 / 对方科目 / 对方明细科目 / 金额）· 支持性文件 ·
 * 核对内容 1~5 · 索引号 · 是否异常 · 备注说明。本期区金额两列（借 / 贷），期后结转区只有借方金额。
 * spec oo-writeback-template-parity-closure R3 批 B2（原表只显示 1 个核对项，缺对方明细科目 / 支持性文件 / 索引号 / 备注）。
 */
import { computed } from 'vue'
import WpAmountInput from '../shared/WpAmountInput.vue'
import GtIndexChip from '../GtIndexChip.vue'
import WpCommitInput from '../shared/WpCommitInput.vue'
import VoucherRowMetaCell from '../voucher-sampling/VoucherRowMetaCell.vue'
import type { VoucherCheckRow } from '../composables/useD7VoucherCheck'

const props = defineProps<{
  rows: VoucherCheckRow[]
  block: 'period' | 'post'
  isReadonly: boolean
  projectId?: string
  /** 审计年度（来源列「多科目」看整张凭证时兜底；凭证键上带年度时以键为准） */
  year?: number | null
  /** 行样式（宿主共享回填函数给年审阶段的预审行加 gt-row-locked） */
  rowClassName?: (data: { row: VoucherCheckRow; rowIndex: number }) => string
  /** 年审阶段的预审行：不可改、不可删 */
  isRowLocked?: (row: VoucherCheckRow) => boolean
}>()
const emit = defineEmits<{
  (e: 'update', rowId: string, field: string, value: unknown): void
  (e: 'toggle', rowId: string, index: number, value: boolean): void
  (e: 'remove', rowId: string): void
}>()

const LEAD_COLUMNS: ReadonlyArray<{ field: keyof VoucherCheckRow & string; label: string; width: number }> = [
  { field: 'customerName', label: '客户名称', width: 130 },
  { field: 'date', label: '日期', width: 100 },
  { field: 'voucherNo', label: '凭证编号', width: 90 },
  { field: 'businessContent', label: '业务内容', width: 130 },
  { field: 'counterAccount', label: '对方科目', width: 120 },
  { field: 'counterDetail', label: '对方明细科目', width: 120 },
]
/** 本行只读：整张底稿只读，或年审阶段的预审行 */
function rowReadonly(row: VoucherCheckRow): boolean {
  return props.isReadonly || !!props.isRowLocked?.(row)
}
const amountColumns = computed(() =>
  props.block === 'period'
    ? [{ field: 'debitAmount', label: '借方金额' }, { field: 'creditAmount', label: '贷方金额' }]
    : [{ field: 'debitAmount', label: '借方金额' }],
)

/** 与 D7TabVoucherCheck 原表同格式：0 / 空显示「-」，负数加括号。 */
function fmtAmt(val: unknown): string {
  const n = Number(val)
  if (val == null || !Number.isFinite(n) || n === 0) return '-'
  const s = Math.abs(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return n < 0 ? `(${s})` : s
}
</script>
