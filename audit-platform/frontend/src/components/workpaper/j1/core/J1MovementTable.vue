<template>
  <el-table
    :data="tableData"
    border
    size="small"
    :highlight-current-row="selectable"
    :row-class-name="rowClassName"
    @current-change="onCurrentChange"
  >
    <el-table-column :label="labelHeader" min-width="240">
      <template #default="{ row }">
        <template v-if="row.isSubtotal">
          <span class="subtotal-label">{{ row.label }}</span>
        </template>
        <el-input
          v-else-if="isLabelEditable(row)"
          v-model="row.label"
          size="small"
          :disabled="isReadonly"
          :style="row.indent ? 'padding-left:16px' : undefined"
          :placeholder="row.indent ? '输入子项名称' : '输入项目名称'"
          @change="emit('row-change', row)"
        />
        <span v-else>{{ row.label }}</span>
      </template>
    </el-table-column>

    <el-table-column
      v-for="col in amountColumns"
      :key="col.key"
      :label="col.label"
      align="right"
      :class-name="col.key === 'endBalance' ? 'auto-calc-col' : undefined"
    >
      <template #default="{ row }">
        <!-- 合计行 / 期末列 / 派生父行：一律只读公式单元格 -->
        <span
          v-if="row.isSubtotal"
          class="formula-cell"
          :title="subtotalTitle"
        >{{ fmt(row[col.key]) }}</span>
        <span
          v-else-if="col.key === 'endBalance'"
          class="formula-cell"
          :title="`${labelOf('endBalance')} = ${labelOf('beginBalance')} + ${labelOf('increase')} − ${labelOf('decrease')}`"
        >{{ fmt(row.endBalance) }}</span>
        <span
          v-else-if="isDerived(row)"
          class="formula-cell derived-cell"
          :title="derivedTitle"
        >{{ fmt(row[col.key]) }}</span>
        <WpAmountInput
          v-else
          v-model="row[col.key]"
          size="small"
          :disabled="isReadonly"
          :aria-label="`${col.label}｜${row.label}`"
          @change="emit('row-change', row)"
        />
      </template>
    </el-table-column>

    <el-table-column v-if="removable !== 'none'" label="" width="36" align="center">
      <template #default="{ row }">
        <el-button
          v-if="isRemovable(row)"
          type="danger"
          link
          size="small"
          :disabled="isReadonly"
          @click="emit('remove', row.id)"
        >✕</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
/**
 * J1MovementTable — J1 披露表的五列变动表（上市 / 国企 × 汇总 / 短期薪酬 / 设定提存 共 6 处复用）
 *
 * 背景（2026-07-30 复盘）：三张表的 `el-table` 模板在两个披露组件里各写 3 遍，
 * 6 份几乎逐字相同（约 55 行 × 6）。任何一项改进（公式单元格 / 复核触发器 / 千分符）
 * 都要落 6 遍 —— 抽成子组件后只改一处。
 *
 * 三处差异由 props 表达：
 * - 列头字面：上市「上年年末数 / 期末数」vs 国企「期初余额 / 期末余额」（源模板各自口径，
 *   附注侧统一由 `j1MovementColumns()` 投影，见 spec 裁决 1）
 * - 标签可编辑范围：汇总表全部行可改名（`all`）；明细表只有「其中：」缩进行可改名（`indent`）
 * - 行选中：明细表需要 `highlight-current-row` 以支持"在选中行后插入新行"，汇总表不需要
 *
 * 只读单元格三类（都渲染成虚线下划线 + tooltip 的公式单元格）：
 * 1. 合计行全部金额列（源模板 SUM 公式）
 * 2. 任意行的期末列（期末 = 期初 + 增加 − 减少）
 * 3. **派生父行**的期初/增加/减少列 —— 非缩进行其后紧跟连续缩进子行时，父行 = Σ 子行
 *    （源模板 `B20=SUM(B21:B27)` 社会保险费 / `B41=SUM(B42:B45)` 离职后福利）
 *
 * 可编辑金额格一律用 `shared/WpAmountInput.vue`（Task 16.3）：element-plus 2.13.6 的
 * `el-input-number` **没有** `formatter`/`parser` prop（编译产物全文无此实现），挂上去是
 * 空操作、千分符从未生效；`WpAmountInput` 用 `el-input` 自行接管显示态（失焦千分符 /
 * 聚焦原始值 / 粘贴带逗号可解析 / 非法输入回退不写 NaN）。
 * **绝不套用于**利率 / 汇率 / 比例 / 笔数 / 年度 —— 本表四列全是金额，故整表适用。
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/ Task 11 / Task 16.3
 */
import { computed } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import type { J1DisclosureRow } from '@/composables/workpaper/j1/j1DisclosureRowModel'

type AmountKey = 'beginBalance' | 'increase' | 'decrease' | 'endBalance'

const props = withDefaults(
  defineProps<{
    /** 数据行（不含合计行） */
    rows: J1DisclosureRow[]
    /** 合计行（composable computed 产出，只读） */
    subtotal: J1DisclosureRow
    /** 期初列列头（上市「上年年末数」/ 国企「期初余额」） */
    beginLabel: string
    /** 期末列列头（上市「期末数」/ 国企「期末余额」） */
    endLabel: string
    /** 标签列列头 */
    labelHeader?: string
    /** 标签可编辑范围 */
    labelEditable?: 'all' | 'indent' | 'none'
    /** 删除按钮可见范围 */
    removable?: 'all' | 'indent' | 'none'
    /** 是否支持行选中（明细表用于"在选中行后插入"） */
    selectable?: boolean
    /** 派生父行 id（其期初/增加/减少 = Σ 紧邻缩进子行，渲染为只读公式单元格） */
    derivedIds?: readonly string[]
    isReadonly?: boolean
  }>(),
  {
    labelHeader: '项 目',
    labelEditable: 'indent',
    removable: 'indent',
    selectable: false,
    derivedIds: () => [],
    isReadonly: false,
  },
)

const emit = defineEmits<{
  'row-change': [row: J1DisclosureRow]
  remove: [id: string]
  'current-change': [row: J1DisclosureRow | null]
}>()

const tableData = computed(() => [...props.rows, props.subtotal])

const amountColumns = computed<Array<{ key: AmountKey; label: string }>>(() => [
  { key: 'beginBalance', label: props.beginLabel },
  { key: 'increase', label: '本期增加' },
  { key: 'decrease', label: '本期减少' },
  { key: 'endBalance', label: props.endLabel },
])

function labelOf(key: AmountKey): string {
  return amountColumns.value.find((c) => c.key === key)?.label ?? key
}

const subtotalTitle = computed(
  () => `合计 = 各非「其中：」行之和（源模板合计公式排除「其中：」明细行，避免双算）`,
)

const derivedTitle = '本行为派生值 = 其下「其中：」各子项之和（源模板父行为 SUM 公式）'

const derivedSet = computed(() => new Set(props.derivedIds))

function isDerived(row: J1DisclosureRow): boolean {
  return derivedSet.value.has(row.id)
}

function isLabelEditable(row: J1DisclosureRow): boolean {
  if (props.labelEditable === 'none') return false
  if (props.labelEditable === 'all') return true
  return Boolean(row.indent)
}

function isRemovable(row: J1DisclosureRow): boolean {
  if (row.isSubtotal) return false
  if (props.removable === 'none') return false
  if (props.removable === 'all') return true
  return Boolean(row.indent)
}

function rowClassName({ row }: { row: J1DisclosureRow }): string {
  if (row.isSubtotal) return 'subtotal-row'
  return row.indent ? 'indent-row' : ''
}

function onCurrentChange(row: J1DisclosureRow | null): void {
  if (!props.selectable) return
  emit('current-change', row)
}

// 只读金额统一走平台单一真源（千分符 + 小数位 + 单位偏好 + localStorage 持久化）。
// 历史实现是组件本地的 `fmtN()`，且 `if (!v) return '-'` 会把 **0 显示成「-」**。
const displayPrefs = useDisplayPrefsStore()

function fmt(v: unknown): string {
  return displayPrefs.fmtAmount(v as number)
}
</script>

<style scoped>
:deep(.el-table) { font-size: 13px !important; }
:deep(.el-table th), :deep(.el-table td) { font-size: 13px !important; padding: 4px 6px !important; }
/* 金额格由 WpAmountInput（el-input）渲染，右对齐与等宽数字在其内部 scoped 样式里 */
:deep(.el-input__inner) { font-size: 13px; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.subtotal-row) { background-color: #f5f7fa !important; font-weight: 600; }
:deep(.indent-row) { color: #606266; }
.subtotal-label { font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.derived-cell { color: #606266; }
</style>
