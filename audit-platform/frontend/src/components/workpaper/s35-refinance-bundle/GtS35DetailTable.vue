<script setup lang="ts">
/**
 * GtS35DetailTable — S35 明细核查子表（可配置）
 *
 * 单组件覆盖 S35-1-1 / S35-2-1 / S35-3-1 三个子表。
 * 通过 sheetCode prop 驱动列定义 + 公式计算。
 *
 * 特性：
 * - 公式列只读（虚线下划线 + cursor:help + tooltip "公式计算"）
 * - 核查判断列（select）
 * - 动态行（新增/删除）
 * - 导入导出三级（el-dropdown）
 * - 13px 全中文
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/  Task 4.2
 * Requirements: 4.1, 4.2, 4.3
 */
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Download, ArrowDown } from '@element-plus/icons-vue'
import {
  calcS35_1_1_Total,
  calcS35_1_1_Ratio,
  calcS35_2_1_InvestRatio,
  formatPercent,
  formatAmount,
} from '../composables/useS35FormulaEngine'
import { useS35ImportExport, type S35ImportableSheet } from '../composables/useS35ImportExport'
import { api } from '@/services/apiProxy'

// ─── Types ───

export type S35SheetCode = 'S35-1-1' | 'S35-2-1' | 'S35-3-1'

interface ColumnDef {
  key: string
  label: string
  type: 'text' | 'number' | 'textarea' | 'select' | 'formula'
  width?: string
  options?: string[]
  formulaTooltip?: string
}

/** 一行数据 */
type RowData = Record<string, any>

// ─── Props ───

const props = withDefaults(defineProps<{
  wpId: string
  sheetCode: S35SheetCode
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  (e: 'data-changed'): void
}>()

// ─── Column definitions per sheet ───

const SHEET_CONFIG: Record<S35SheetCode, { label: string; columns: ColumnDef[] }> = {
  'S35-1-1': {
    label: '关联交易核查',
    columns: [
      { key: 'project', label: '项目', type: 'text', width: '120px' },
      { key: 'parentCompany', label: '母公司', type: 'number', width: '110px' },
      { key: 'sub1', label: '子公司1', type: 'number', width: '110px' },
      { key: 'sub2', label: '子公司2', type: 'number', width: '110px' },
      { key: 'total', label: '合计', type: 'formula', width: '110px', formulaTooltip: '公式计算：SUM(母公司+子公司…)' },
      { key: 'indicator', label: '发行人相应指标金额', type: 'number', width: '140px' },
      { key: 'ratio', label: '占比', type: 'formula', width: '100px', formulaTooltip: '公式计算：合计÷发行人指标' },
      { key: 'transNature', label: '募投项目新增关联交易性质', type: 'textarea', width: '180px' },
      { key: 'pricingBasis', label: '定价依据', type: 'textarea', width: '160px' },
      { key: 'judgment', label: '是否构成重大不利影响', type: 'select', width: '150px', options: ['是', '否', '不适用'] },
    ],
  },
  'S35-2-1': {
    label: '财务性投资核查',
    columns: [
      { key: 'companyName', label: '公司名称', type: 'text', width: '140px' },
      { key: 'industry', label: '公司行业', type: 'text', width: '120px' },
      { key: 'investType', label: '财务性投资类型', type: 'select', width: '140px', options: ['股权投资', '债权投资', '基金投资', '理财产品', '其他'] },
      { key: 'purpose', label: '投资目的', type: 'textarea', width: '160px' },
      { key: 'term', label: '投资期限', type: 'text', width: '100px' },
      { key: 'investAmount', label: '投资金额', type: 'number', width: '120px' },
      { key: 'netProfit', label: '归母净利润', type: 'number', width: '120px' },
      { key: 'investRatio', label: '投资占比', type: 'formula', width: '100px', formulaTooltip: '公式计算：投资金额÷归母净利润' },
      { key: 'judgment', label: '是否符合要求', type: 'select', width: '130px', options: ['符合', '不符合', '待核实'] },
    ],
  },
  'S35-3-1': {
    label: '现金分红核查',
    columns: [
      { key: 'seq', label: '序号', type: 'number', width: '70px' },
      { key: 'parentUndist', label: '母公司未分配利润', type: 'number', width: '140px' },
      { key: 'consolidatedUndist', label: '合并报表未分配利润', type: 'number', width: '150px' },
      { key: 'dividendAmount', label: '分红金额', type: 'number', width: '120px' },
      { key: 'charterRule', label: '章程规定', type: 'textarea', width: '180px' },
      { key: 'fundUsage', label: '融资款项用途', type: 'textarea', width: '160px' },
      { key: 'judgment', label: '是否违规', type: 'select', width: '100px', options: ['是', '否', '不适用'] },
      { key: 'rectification', label: '整改措施', type: 'textarea', width: '160px' },
    ],
  },
}

// ─── State ───

const rows = ref<RowData[]>([])
const saving = ref(false)
const sheetLabel = computed(() => SHEET_CONFIG[props.sheetCode]?.label ?? props.sheetCode)
const columns = computed(() => SHEET_CONFIG[props.sheetCode]?.columns ?? [])

// ─── Import/Export ───

const wpIdRef = computed(() => props.wpId)
const { importing, exportTemplate, exportData, importData } = useS35ImportExport({
  wpId: wpIdRef,
  sheetCode: props.sheetCode as S35ImportableSheet,
  sheetLabel: sheetLabel.value,
  onImported: async () => {
    await loadData()
    emit('data-changed')
  },
})

// ─── Formula recalc (Req 4.2) ───

/**
 * 实时重算所有公式列。当任何数值变化时触发。
 * 公式列只读，用户不可覆盖。
 */
function recalcFormulas(): void {
  if (props.sheetCode === 'S35-1-1') {
    for (const row of rows.value) {
      const amounts = [row.parentCompany, row.sub1, row.sub2].filter(
        (v) => v != null && v !== '',
      ).map(Number)
      row.total = calcS35_1_1_Total(amounts)
      row.ratio = calcS35_1_1_Ratio(row.total, Number(row.indicator) || null)
    }
  } else if (props.sheetCode === 'S35-2-1') {
    for (const row of rows.value) {
      row.investRatio = calcS35_2_1_InvestRatio(
        Number(row.investAmount) || null,
        Number(row.netProfit) || null,
      )
    }
  }
  // S35-3-1 无公式
}

// Watch row data for formula recalc
watch(rows, () => {
  recalcFormulas()
}, { deep: true })

// ─── Dynamic rows ───

function addRow(): void {
  const newRow: RowData = {}
  for (const col of columns.value) {
    if (col.type === 'number' || col.type === 'formula') {
      newRow[col.key] = null
    } else if (col.type === 'select') {
      newRow[col.key] = ''
    } else {
      newRow[col.key] = ''
    }
  }
  // S35-3-1 序号自增
  if (props.sheetCode === 'S35-3-1') {
    newRow.seq = rows.value.length + 1
  }
  rows.value.push(newRow)
}

function removeRow(index: number): void {
  rows.value.splice(index, 1)
  // S35-3-1 重新编号
  if (props.sheetCode === 'S35-3-1') {
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }
}

// ─── Cell value helpers ───

function onCellInput(row: RowData, col: ColumnDef, value: any): void {
  if (col.type === 'number') {
    row[col.key] = value === '' ? null : Number(value)
  } else {
    row[col.key] = value
  }
}

function getFormulaDisplay(row: RowData, col: ColumnDef): string {
  const val = row[col.key]
  if (col.key === 'ratio' || col.key === 'investRatio') {
    return formatPercent(val)
  }
  return formatAmount(val)
}

// ─── Persistence (checklist_responses JSON 打包) ───

async function loadData(): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, {
      params: { item_prefix: props.sheetCode },
      _silent: true,
    } as any)
    const items = (res as any[]) || []
    const dataItem = items.find((r: any) => r.item_id === `${props.sheetCode}-rows`)
    if (dataItem?.conclusion) {
      try {
        const parsed = JSON.parse(dataItem.conclusion)
        rows.value = Array.isArray(parsed) ? parsed : []
      } catch {
        rows.value = []
      }
    } else {
      rows.value = []
    }
    recalcFormulas()
  } catch {
    rows.value = []
  }
}

async function saveData(): Promise<void> {
  if (!props.wpId || props.readonly) return
  saving.value = true
  try {
    // 保存前重算公式
    recalcFormulas()
    await api.post(`/api/workpapers/${props.wpId}/checklist-responses`, {
      items: [{
        item_id: `${props.sheetCode}-rows`,
        conclusion: JSON.stringify(rows.value),
        remark: null,
      }],
    })
    emit('data-changed')
  } catch (err: any) {
    ElMessage.error('保存失败：' + (err?.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

// ─── Import handler ───

async function handleImport(file: File): Promise<void> {
  await importData(file)
}

function triggerImport(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e: Event) => {
    const files = (e.target as HTMLInputElement).files
    if (files && files[0]) {
      await handleImport(files[0])
    }
  }
  input.click()
}

// ─── Lifecycle ───

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="gt-s35-detail" data-testid="s35-detail-table">
    <!-- 工具栏 -->
    <div class="gt-s35-detail__toolbar">
      <span class="gt-s35-detail__title">{{ sheetLabel }}</span>

      <div class="gt-s35-detail__actions">
        <!-- 导入导出 (Req 4.3) -->
        <el-dropdown
          v-if="!props.readonly"
          trigger="click"
          @command="(cmd: string) => {
            if (cmd === 'export-template') exportTemplate()
            else if (cmd === 'export-data') exportData()
            else if (cmd === 'import-data') triggerImport()
          }"
        >
          <el-button size="small" :icon="Download" :loading="importing">
            导入导出
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <!-- 新增行 -->
        <el-button
          v-if="!props.readonly"
          size="small"
          type="primary"
          :icon="Plus"
          @click="addRow"
        >
          新增行
        </el-button>

        <!-- 保存 -->
        <el-button
          v-if="!props.readonly"
          size="small"
          type="success"
          :loading="saving"
          @click="saveData"
        >
          保存
        </el-button>
      </div>
    </div>

    <!-- 数据表格 -->
    <el-table
      :data="rows"
      border
      stripe
      size="small"
      class="gt-s35-detail__table"
      empty-text="暂无数据，请点击「新增行」或「导入数据」"
    >
      <!-- 序号列（非 S35-3-1 自动编号） -->
      <el-table-column
        v-if="sheetCode !== 'S35-3-1'"
        type="index"
        label="#"
        width="50"
        align="center"
      />

      <el-table-column
        v-for="col in columns"
        :key="col.key"
        :label="col.label"
        :min-width="col.width || '120px'"
        :class-name="col.type === 'formula' ? 'gt-s35-detail__formula-col' : ''"
      >
        <template #default="{ row, $index }">
          <!-- 公式列：只读 (Req 4.2) -->
          <template v-if="col.type === 'formula'">
            <el-tooltip :content="col.formulaTooltip || '公式计算'" placement="top">
              <span class="gt-s35-detail__formula-cell">
                {{ getFormulaDisplay(row, col) }}
              </span>
            </el-tooltip>
          </template>

          <!-- Select 列（核查判断列） -->
          <template v-else-if="col.type === 'select'">
            <el-select
              :model-value="row[col.key]"
              placeholder="请选择"
              size="small"
              :disabled="props.readonly"
              @update:model-value="(v: string) => onCellInput(row, col, v)"
            >
              <el-option
                v-for="opt in col.options"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </template>

          <!-- Textarea 列 -->
          <template v-else-if="col.type === 'textarea'">
            <el-input
              :model-value="row[col.key]"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              :disabled="props.readonly"
              @update:model-value="(v: string) => onCellInput(row, col, v)"
            />
          </template>

          <!-- Number 列 -->
          <template v-else-if="col.type === 'number'">
            <el-input-number
              :model-value="row[col.key]"
              :controls="false"
              size="small"
              :disabled="props.readonly"
              @update:model-value="(v: number | undefined) => onCellInput(row, col, v ?? null)"
            />
          </template>

          <!-- Text 列 -->
          <template v-else>
            <el-input
              :model-value="row[col.key]"
              size="small"
              :disabled="props.readonly"
              @update:model-value="(v: string) => onCellInput(row, col, v)"
            />
          </template>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column
        v-if="!props.readonly"
        label="操作"
        width="70"
        align="center"
        fixed="right"
      >
        <template #default="{ $index }">
          <el-button
            type="danger"
            :icon="Delete"
            size="small"
            link
            @click="removeRow($index)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 行数统计 -->
    <div class="gt-s35-detail__footer">
      <span>共 {{ rows.length }} 行</span>
    </div>
  </div>
</template>

<style scoped>
.gt-s35-detail {
  font-size: 13px;
}

/* 工具栏 */
.gt-s35-detail__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding: 8px 0;
}

.gt-s35-detail__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.gt-s35-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表格 */
.gt-s35-detail__table {
  font-size: 13px;
}

.gt-s35-detail__table :deep(.el-table__header th) {
  font-size: 13px;
  background: var(--gt-color-bg-elevated, #fafafa);
}

.gt-s35-detail__table :deep(.el-input-number) {
  width: 100%;
}

.gt-s35-detail__table :deep(.el-select) {
  width: 100%;
}

/* 公式列只读：虚线下划线 + cursor:help (memory 铁律) */
.gt-s35-detail__formula-cell {
  display: inline-block;
  width: 100%;
  text-align: right;
  border-bottom: 1px dashed var(--gt-color-border, #dcdfe6);
  cursor: help;
  color: var(--gt-color-text-secondary, #606266);
  font-variant-numeric: tabular-nums;
  padding: 2px 4px;
}

/* Footer */
.gt-s35-detail__footer {
  margin-top: 8px;
  text-align: right;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
