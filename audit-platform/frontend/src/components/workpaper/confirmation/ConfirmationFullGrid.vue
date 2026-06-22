<template>
  <div class="confirmation-full-grid">
    <div class="confirmation-full-grid__scroll">
      <table class="confirmation-full-grid__table">
        <colgroup>
          <col v-for="col in columns" :key="col.field" :style="{ width: col.width + 'px' }" />
        </colgroup>
        <thead>
          <tr class="confirmation-full-grid__group-header">
            <th v-for="group in columnGroups" :key="group.label" :colspan="group.cols.length" :class="'group--' + group.color">
              {{ group.label }}
            </th>
          </tr>
          <tr class="confirmation-full-grid__col-header">
            <th v-for="col in columns" :key="col.field" :class="{ 'col--frozen': col.frozen }">
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in rows" :key="row._row_id" :class="{ 'row--zebra': idx % 2 === 1 }">
            <td
              v-for="col in columns"
              :key="col.field"
              :class="[
                { 'col--frozen': col.frozen },
                { 'cell--empty': isEmpty(row, col.field) },
              ]"
            >
              <!-- Readonly span -->
              <span v-if="readonly || col.readonly">
                {{ formatCell(row, col) }}
              </span>
              <!-- Enum select -->
              <el-select
                v-else-if="col.type === 'enum'"
                :model-value="(row as any)[col.field]"
                size="small"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.field, v)"
              >
                <el-option v-for="opt in col.options" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <!-- Number input -->
              <el-input-number
                v-else-if="col.type === 'number'"
                :model-value="(row as any)[col.field]"
                size="small"
                :controls="false"
                :precision="2"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.field, v)"
              />
              <!-- Boolean -->
              <el-checkbox
                v-else-if="col.type === 'boolean'"
                :model-value="(row as any)[col.field]"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.field, v)"
              />
              <!-- Text input -->
              <el-input
                v-else
                :model-value="(row as any)[col.field]"
                size="small"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.field, v)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ConfirmationRow } from './confirmationTypes'

defineProps<{ rows: ConfirmationRow[]; readonly: boolean }>()
defineEmits<{ (e: 'update', rowId: string, field: string, value: any): void }>()

interface ColumnDef {
  field: string
  label: string
  width: number
  type: 'text' | 'number' | 'enum' | 'boolean' | 'date'
  frozen?: boolean
  readonly?: boolean
  options?: string[]
}

interface ColumnGroup {
  label: string
  color: string
  cols: ColumnDef[]
}

const columnGroups: ColumnGroup[] = [
  { label: '基本信息', color: 'blue', cols: [
    { field: 'seq', label: '序号', width: 50, type: 'number', readonly: true },
    { field: 'confirm_index', label: '索引号', width: 90, type: 'text', frozen: true },
    { field: 'entity_name', label: '被询证单位', width: 160, type: 'text' },
    { field: 'entity_address', label: '地址', width: 160, type: 'text' },
    { field: 'contact_person', label: '联系人', width: 80, type: 'text' },
    { field: 'contact_phone', label: '联系电话', width: 110, type: 'text' },
  ]},
  { label: '函证信息', color: 'green', cols: [
    { field: 'account_type', label: '科目', width: 100, type: 'enum', options: ['应收账款', '合同负债', '其他应收款', '预付账款', '应付账款', '其他应付款', '短期借款', '长期借款', '银行存款', '定期存款', '理财产品', '其他货币资金', '其他'] },
    { field: 'amount', label: '函证金额', width: 110, type: 'number' },
    { field: 'currency', label: '币种', width: 60, type: 'text' },
    { field: 'confirmation_method', label: '函证方式', width: 80, type: 'enum', options: ['积极式', '消极式'] },
    { field: 'send_date', label: '发函日期', width: 100, type: 'date' },
  ]},
  { label: '回函信息', color: 'orange', cols: [
    { field: 'is_replied', label: '已回函', width: 60, type: 'boolean' },
    { field: 'reply_date', label: '回函日期', width: 100, type: 'date' },
    { field: 'reply_method', label: '回函方式', width: 90, type: 'enum', options: ['原件寄回', '传真', '电子邮件', '当面确认'] },
    { field: 'reply_amount', label: '回函金额', width: 110, type: 'number' },
    { field: 'match_status', label: '相符情况', width: 80, type: 'enum', options: ['相符', '不符', '未回函'] },
  ]},
  { label: '确认金额', color: 'purple', cols: [
    { field: 'confirmed_amount', label: '可确认金额', width: 110, type: 'number', readonly: true },
    { field: 'difference', label: '差异', width: 100, type: 'number', readonly: true },
    { field: 'alt_confirmed', label: '替代确认', width: 100, type: 'number' },
  ]},
  { label: '关联信息', color: 'teal', cols: [
    { field: 'diff_ref_index', label: '差异索引', width: 90, type: 'text' },
    { field: 'alt_ref_index', label: '替代索引', width: 90, type: 'text' },
    { field: 'electronic_reply', label: '电子回函', width: 70, type: 'boolean' },
    { field: 'reliability_verified', label: '已验证', width: 60, type: 'boolean' },
    { field: 'fraud_risk_flag', label: '舞弊标志', width: 70, type: 'boolean' },
    { field: 'remark', label: '备注', width: 160, type: 'text' },
    { field: '_source', label: '来源', width: 60, type: 'text', readonly: true },
  ]},
]

const columns: ColumnDef[] = columnGroups.flatMap(g => g.cols)

function isEmpty(row: ConfirmationRow, field: string): boolean {
  const val = (row as any)[field]
  return val == null || val === '' || val === false
}

function formatCell(row: ConfirmationRow, col: ColumnDef): string {
  const val = (row as any)[col.field]
  if (val == null || val === '') return ''
  if (col.type === 'number') return typeof val === 'number' ? val.toLocaleString() : String(val)
  if (col.type === 'boolean') return val ? '是' : '否'
  return String(val)
}
</script>

<style scoped>
.confirmation-full-grid {
  overflow: hidden;
}

.confirmation-full-grid__scroll {
  overflow-x: auto;
  max-height: 600px;
  overflow-y: auto;
}

.confirmation-full-grid__table {
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}

.confirmation-full-grid__table th,
.confirmation-full-grid__table td {
  border: 1px solid var(--el-border-color-lighter);
  padding: 4px 6px;
}

.confirmation-full-grid__group-header th {
  text-align: center;
  font-weight: 600;
  font-size: 12px;
}

.group--blue { background: #e8f4fd; color: #1890ff; }
.group--green { background: #e8f8e8; color: #52c41a; }
.group--orange { background: #fff7e6; color: #fa8c16; }
.group--purple { background: #f3e8ff; color: #722ed1; }
.group--teal { background: #e6fffb; color: #13c2c2; }

.confirmation-full-grid__col-header th {
  background: #fafafa;
  font-weight: 500;
  text-align: center;
}

.col--frozen {
  position: sticky;
  left: 0;
  z-index: 2;
  background: #fff;
}

.row--zebra td {
  background: #fafbfc;
}

.cell--empty {
  opacity: 0.4;
}

.confirmation-full-grid__table .el-select,
.confirmation-full-grid__table .el-input,
.confirmation-full-grid__table .el-input-number {
  width: 100%;
}
</style>
