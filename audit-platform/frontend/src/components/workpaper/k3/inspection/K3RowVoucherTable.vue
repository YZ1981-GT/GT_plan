<script setup lang="ts">
/**
 * K3-5 / K3-6 行级抽凭明细表（spec voucher-identity-writeback-and-audit-phase 任务 13）
 *
 * 行上「📋」抽到、或从序时账挂入导入的凭证：一个对方科目一行，挂到往来对象行；来源列显示阶段 / 来源 / 配对，
 * 年审阶段的预审行只读（行样式由宿主传入的共享回填函数 rowClass 给）。数据与保存在 `useK3RowVoucherFill`。
 */
import { computed } from 'vue'
import VoucherRowMetaCell from '../../voucher-sampling/VoucherRowMetaCell.vue'
import type { K3RowVoucher } from '../../composables/k3RowVoucherFill'

const props = defineProps<{
  rows: K3RowVoucher[]
  isReadonly: boolean
  isRowLocked: (row: K3RowVoucher) => boolean
  rowClassName: (arg: { row: K3RowVoucher }) => string
  projectId: string
  year: number
  /** 现有往来对象行的 id（明细挂的行已删或挂凭导入没对上时标「未对应」） */
  targetIds: string[]
}>()

const emit = defineEmits<{
  (e: 'change'): void
  (e: 'remove', rowId: string): void
}>()

const known = computed(() => new Set(props.targetIds))

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="k3-row-voucher-table">
    <div class="k3rv-title">行级抽凭明细（{{ rows.length }} 行）</div>
    <el-table :data="rows" border size="small" :max-height="300" :row-class-name="rowClassName" empty-text="尚未抽凭：点往来对象行的「📋」抽凭，或从序时账挂入导入">
      <el-table-column label="#" type="index" width="42" align="center" />
      <!-- 阶段 / 来源 / 配对（共享回填函数写的行元数据） -->
      <el-table-column label="来源" width="150">
        <template #default="{ row }">
          <VoucherRowMetaCell :row="row" :locked="isRowLocked(row)" :project-id="projectId" :year="year" />
        </template>
      </el-table-column>
      <el-table-column label="往来对象" min-width="130">
        <template #default="{ row }">
          <span>{{ row.counterparty || '-' }}</span>
          <el-tag v-if="!known.has(row.targetRowId)" size="small" type="info" effect="plain" style="margin-left: 4px">未对应</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="日期" prop="voucherDate" width="105" />
      <el-table-column label="凭证号" prop="voucherNo" width="100" />
      <el-table-column label="摘要" prop="summary" min-width="140" show-overflow-tooltip />
      <el-table-column label="对方科目" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ [row.counterpartAccount, row.counterpartAccountName].filter(Boolean).join(' ') || '-' }}</template>
      </el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">{{ fmtAmt(row.debitAmount) }}</template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">{{ fmtAmt(row.creditAmount) }}</template>
      </el-table-column>
      <el-table-column label="核对结果" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.checkResult" size="small" placeholder="原始凭证 / 合同 / 回单核对情况" @change="emit('change')" />
          <span v-else>{{ row.checkResult || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="emit('change')" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isRowLocked(row)" size="small" type="danger" link @click="emit('remove', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.k3-row-voucher-table { margin-top: 12px; }
.k3rv-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary); margin-bottom: 6px; }
</style>
