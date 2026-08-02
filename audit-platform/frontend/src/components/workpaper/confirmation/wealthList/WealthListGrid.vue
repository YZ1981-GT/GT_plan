<template>
  <div class="wealth-grid">
    <!-- 源模板口径提示（防「份额 × 净值」误解） -->
    <div class="wealth-grid__header-note">
      <el-icon :size="14"><InfoFilled /></el-icon>
      <span>{{ WEALTH_LIST_HEADER_NOTE }}</span>
    </div>

    <!-- 工具栏 -->
    <div class="wealth-grid__toolbar">
      <el-button-group>
        <el-button size="small" type="primary" :icon="Plus" :disabled="readonly" @click="$emit('add')">
          新增产品
        </el-button>
        <el-button
          size="small"
          type="danger"
          :icon="Delete"
          :disabled="readonly || !selectedIds.length"
          @click="$emit('delete', selectedIds)"
        >
          删除
        </el-button>
      </el-button-group>

      <el-dropdown trigger="click" @command="handleIoCommand">
        <el-button size="small">
          导入导出<el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import" :disabled="readonly" divided>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <div class="wealth-grid__toolbar-right">
        <el-button size="small" :disabled="!rows.length" @click="$emit('jump-summary')">
          查看 E0-1 汇总
        </el-button>
        <el-button size="small" type="success" :disabled="readonly || !isDirty" @click="$emit('save')">
          保存
        </el-button>
      </div>
    </div>

    <!-- 网格 -->
    <el-table
      :data="rows"
      border
      size="small"
      highlight-current-row
      max-height="520"
      show-summary
      :summary-method="summaryMethod"
      :row-class-name="rowClassName"
      class="wealth-grid__table"
      empty-text="暂无理财产品，点「新增产品」开始登记"
      @selection-change="handleSelectionChange"
    >
      <el-table-column v-if="!readonly" type="selection" width="36" fixed="left" />
      <el-table-column label="序号" prop="seq" width="52" align="center" fixed="left" />

      <!-- 索引号（E0-1 汇总键之一） -->
      <el-table-column width="104" fixed="left">
        <template #header>
          <span :class="{ 'wealth-grid__th-key': true }">索引号</span>
          <el-tooltip content="E0-1 汇总键之一（对应 E0-1「询证函索引号」），留空则该笔金额汇不进 E0-1" placement="top">
            <el-icon :size="12" class="wealth-grid__th-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.confirm_index"
            size="small"
            placeholder="E0-6-"
            :class="{ 'wealth-grid__cell--missing': !String(row.confirm_index || '').trim() }"
            @input="(v: string) => emitUpdate(row, 'confirm_index', v)"
          />
          <span v-else>{{ row.confirm_index || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="报表截止日" width="126" align="center">
        <template #default="{ row }">
          <el-date-picker
            v-if="!readonly"
            :model-value="row.cutoff_date"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择"
            style="width: 100%"
            @update:model-value="(v: string) => emitUpdate(row, 'cutoff_date', v)"
          />
          <span v-else>{{ row.cutoff_date || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="开户行名称及收件人" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.bank_and_recipient"
            size="small"
            placeholder="如：招商银行XX分行 / 收件人张三"
            @input="(v: string) => emitUpdate(row, 'bank_and_recipient', v)"
          />
          <span v-else>{{ row.bank_and_recipient || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 产品名称（E0-1 汇总键之一） -->
      <el-table-column min-width="170" show-overflow-tooltip>
        <template #header>
          <span class="wealth-grid__th-key">产品名称</span>
          <el-tooltip
            content="E0-1 汇总键之一（对应 E0-1「账号/理财产品名称」）——理财产品无账号，源模板用产品名称作键"
            placement="top"
          >
            <el-icon :size="12" class="wealth-grid__th-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.product_name"
            size="small"
            placeholder="理财产品全称"
            :class="{ 'wealth-grid__cell--missing': !String(row.product_name || '').trim() }"
            @input="(v: string) => emitUpdate(row, 'product_name', v)"
          />
          <span v-else>{{ row.product_name || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="产品类型" width="112" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.product_type"
            size="small"
            placeholder="选择"
            clearable
            style="width: 100%"
            @update:model-value="(v: string) => emitUpdate(row, 'product_type', v)"
          >
            <el-option v-for="t in WEALTH_PRODUCT_TYPES" :key="t" :value="t" :label="t" />
          </el-select>
          <template v-else>
            <el-tag v-if="row.product_type" size="small" type="info" effect="plain">{{ row.product_type }}</el-tag>
            <span v-else>—</span>
          </template>
        </template>
      </el-table-column>

      <el-table-column label="币种" width="104" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.currency"
            size="small"
            placeholder="选择"
            filterable
            allow-create
            default-first-option
            style="width: 100%"
            @update:model-value="(v: string) => emitUpdate(row, 'currency', v)"
          >
            <el-option v-for="c in WEALTH_CURRENCY_SUGGESTIONS" :key="c" :value="c" :label="c" />
          </el-select>
          <span v-else>{{ row.currency || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 持有份额：数量，禁套 WpAmountInput（金额专用） -->
      <el-table-column label="持有份额" prop="units_held" width="132" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!readonly"
            :model-value="row.units_held"
            :precision="4"
            :controls="false"
            :min="0"
            size="small"
            placeholder="份额"
            style="width: 100%"
            @update:model-value="(v: number) => emitUpdate(row, 'units_held', v)"
          />
          <span v-else>{{ row.units_held ?? '—' }}</span>
        </template>
      </el-table-column>

      <!-- 产品净值：金额（总额口径）→ E0-1 发函金额 -->
      <el-table-column prop="net_value" width="146" align="right">
        <template #header>
          <span class="wealth-grid__th-amount">产品净值</span>
          <el-tooltip
            content="总额口径。源模板 E0-1「发函金额（原币）」= SUMIFS(本表产品净值列)，不是「持有份额 × 单位净值」"
            placement="top"
          >
            <el-icon :size="12" class="wealth-grid__th-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <WpAmountInput
            v-if="!readonly"
            :model-value="row.net_value ?? 0"
            :aria-label="`产品净值 ${row.product_name || ''}`"
            @change="(v: number) => emitUpdate(row, 'net_value', v)"
          />
          <span v-else class="wealth-grid__amount">{{ fmt(row.net_value) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="购买日" width="126" align="center">
        <template #default="{ row }">
          <el-date-picker
            v-if="!readonly"
            :model-value="row.purchase_date"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择"
            style="width: 100%"
            @update:model-value="(v: string) => emitUpdate(row, 'purchase_date', v)"
          />
          <span v-else>{{ row.purchase_date || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="到期日" width="150" align="center">
        <template #default="{ row }">
          <div class="wealth-grid__maturity">
            <el-date-picker
              v-if="!readonly"
              :model-value="row.maturity_date"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择"
              style="width: 100%"
              @update:model-value="(v: string) => emitUpdate(row, 'maturity_date', v)"
            />
            <span v-else>{{ row.maturity_date || '—' }}</span>
            <el-tooltip v-if="isMatured(row)" content="到期日不晚于报表截止日，请核实期末是否仍应列示" placement="top">
              <el-tag size="small" type="warning" effect="plain">已到期</el-tag>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="是否受限" width="118" align="center">
        <template #header>
          <span>是否受限</span>
          <el-tooltip content="源列名：是否被用于担保或存在其他使用限制。勾「是」的产品应在受限资产相关披露中反映" placement="top">
            <el-icon :size="12" class="wealth-grid__th-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.restricted"
            size="small"
            placeholder="选择"
            style="width: 100%"
            @update:model-value="(v: string) => emitUpdate(row, 'restricted', v)"
          >
            <el-option v-for="o in WEALTH_RESTRICTED_OPTIONS" :key="o" :value="o" :label="o" />
          </el-select>
          <template v-else>
            <el-tag v-if="row.restricted === '是'" size="small" type="warning">是</el-tag>
            <span v-else-if="row.restricted === '否'">否</span>
            <span v-else>—</span>
          </template>
        </template>
      </el-table-column>

      <!-- 质量状态（派生列，只读） -->
      <el-table-column label="状态" width="96" align="center" fixed="right">
        <template #default="{ row }">
          <el-tooltip v-if="statusOf(row) === 'danger'" placement="top">
            <template #content>缺「索引号」或「产品名称」——E0-1 按这两个键匹配，缺任一则金额汇不进 E0-1</template>
            <el-tag size="small" type="danger">键缺失</el-tag>
          </el-tooltip>
          <el-tag v-else-if="statusOf(row) === 'warning'" size="small" type="warning" effect="plain">待核实</el-tag>
          <el-tag v-else size="small" type="success" effect="plain">正常</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编制提示（折叠在底部） -->
    <details class="wealth-grid__tips">
      <summary>编制提示（源模板口径）</summary>
      <ul>
        <li>本表逐只登记<strong>已决定函证</strong>的理财产品。源模板本表<strong>没有「是否函证」列</strong>，入表即视为发函对象。</li>
        <li>「索引号」+「产品名称」是 E0-1 汇总的两个匹配键，二者缺一则该笔发函金额在 E0-1 显示为 0。</li>
        <li>「产品净值」为总额口径，直接汇入 E0-1「发函金额（原币）」；「持有份额」不参与金额计算。</li>
        <li>「开户行名称及收件人」是被询证单位（银行）；理财产品名称不是单位名。</li>
        <li>勾「是否受限 = 是」的产品：计入其他货币资金的进 E1「受限制的货币资金明细」；
          计入交易性金融资产等的进「所有权或使用权受到限制的资产」附注段。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Plus, Delete, ArrowDown, InfoFilled, QuestionFilled } from '@element-plus/icons-vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { WEALTH_LIST_HEADER_NOTE, type WealthProductRow } from './wealthListTypes'
import {
  WEALTH_PRODUCT_TYPES,
  WEALTH_RESTRICTED_OPTIONS,
  WEALTH_CURRENCY_SUGGESTIONS,
} from './wealthListEnums'
import { isMatured, toNum } from './composables/useWealthListData'

const props = defineProps<{
  rows: WealthProductRow[]
  readonly: boolean
  isDirty: boolean
  getRowQualityStatus: (row: WealthProductRow) => 'ok' | 'warning' | 'danger'
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete', ids: string[]): void
  (e: 'save'): void
  (e: 'update', rowId: string, field: string, value: any): void
  (e: 'import-excel'): void
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'jump-summary'): void
}>()

const displayPrefs = useDisplayPrefsStore()
function fmt(v: unknown): string {
  return displayPrefs.fmtAmount(toNum(v))
}

const selectedIds = ref<string[]>([])
function handleSelectionChange(sel: WealthProductRow[]) {
  selectedIds.value = sel.map((r) => r._row_id!).filter(Boolean)
}

function emitUpdate(row: WealthProductRow, field: string, value: any) {
  if (!row._row_id) return
  emit('update', row._row_id, field, value)
}

function statusOf(row: WealthProductRow): 'ok' | 'warning' | 'danger' {
  return props.getRowQualityStatus(row)
}

function rowClassName({ row }: { row: WealthProductRow }): string {
  const s = statusOf(row)
  if (s === 'danger') return 'wealth-grid__row--danger'
  if (s === 'warning') return 'wealth-grid__row--warning'
  return ''
}

function handleIoCommand(cmd: string) {
  if (cmd === 'import') emit('import-excel')
  else if (cmd === 'export-template') emit('export-template')
  else if (cmd === 'export-data') emit('export-data')
}

/**
 * 合计行：仅份额与净值两列求和（其余留空）。
 * 按 `column.property` 判别，不按 label/width —— 产品净值列用的是自定义 #header
 * 插槽，`label` 为空，靠 width 判别会在改列宽时静默失效。
 */
function summaryMethod({ columns }: { columns: any[] }): string[] {
  const unitsTotal = props.rows.reduce((s, r) => s + toNum(r.units_held), 0)
  const netTotal = props.rows.reduce((s, r) => s + toNum(r.net_value), 0)
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    if (col.property === 'units_held') return String(Math.round(unitsTotal * 10000) / 10000)
    if (col.property === 'net_value') return displayPrefs.fmtAmount(netTotal)
    return ''
  })
}
</script>

<style scoped>
.wealth-grid {
  font-size: 13px;
}

.wealth-grid__header-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 10px;
  margin-bottom: 10px;
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.wealth-grid__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.wealth-grid__toolbar-right {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.wealth-grid__table {
  font-size: 13px;
}

.wealth-grid__th-key,
.wealth-grid__th-amount {
  border-bottom: 1px dashed var(--el-color-primary);
}

.wealth-grid__th-icon {
  margin-left: 2px;
  color: var(--el-text-color-secondary);
  vertical-align: -1px;
}

.wealth-grid__amount {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.wealth-grid__maturity {
  display: flex;
  align-items: center;
  gap: 4px;
}

.wealth-grid__cell--missing :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-danger-light-5) inset;
}

.wealth-grid__table :deep(.wealth-grid__row--danger) {
  --el-table-tr-bg-color: var(--el-color-danger-light-9);
}

.wealth-grid__table :deep(.wealth-grid__row--warning) {
  --el-table-tr-bg-color: var(--el-color-warning-light-9);
}

.wealth-grid__table :deep(td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.wealth-grid__tips {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.wealth-grid__tips summary {
  cursor: pointer;
  user-select: none;
  color: var(--el-color-primary);
}

.wealth-grid__tips ul {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.9;
}
</style>
