<script setup lang="ts">
/**
 * F2FourTableSourcePanel.vue — F2「四表取数（公式管理）」面板
 *
 * 镜像 E1FourTableSourcePanel：展示各存货类别从四表库自动提取的取数来源
 * - 来源科目（code + name）
 * - 取数公式（TB('code','期末余额') 等）
 * - 期初 / 增加 / 减少 / 期末
 *
 * 提供「🔄 从四表库刷新取数」：以四表库值覆盖当前审定表锚点。
 * 灰度门控：tbValues 含 formulas 字段时才渲染。
 */
import { computed, ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { F2_CATEGORIES, type TbValuesEntry } from '../composables/useF2Adjudication'
import { F2_ROW_KEY_ACCOUNT } from '../composables/useF2CrossSheet'
import {
  resolveF2RowKeyToAccounts,
  type F2InventoryAccountItem,
} from '../composables/f2AccountModel'
import type { ChecklistResponse } from '../composables/useF2FormData'

export interface F2FourTableSourcePanelProps {
  tbValues: Record<string, TbValuesEntry> | null | undefined
  allResponses: Map<string, ChecklistResponse>
  isReadonly?: boolean
  wpId?: string
  projectId?: string
  /** render 输出的本项目实际存货科目清单（供来源科目列展示项目实际子科目，替代单一编码兜底） */
  inventoryAccounts?: F2InventoryAccountItem[] | null
}

type F2BlockKey = 'gross' | 'impairment'

const props = defineProps<F2FourTableSourcePanelProps>()
const emit = defineEmits<{ (e: 'refresh-complete'): void }>()

const isRefreshing = ref(false)

// ─── 灰度判定：tbValues 含 formulas 字段时显示 ───
const hasFourTableData = computed(() => {
  if (!props.tbValues) return false
  return Object.values(props.tbValues).some(
    (v) => v && (v.formulas || v.source_codes),
  )
})

// ─── 源行构建 ───
interface SourceRow {
  rowKey: string
  label: string
  accountCode: string
  formulaOpening: string
  opening: number
  formulaIncrease: string
  increase: number
  formulaDecrease: string
  decrease: number
  closing: number
  sourceCodes: string[]
}

// 本项目实际科目按 rowKey 分组（Wave 3）：一个 rowKey 可能对应多个客户子科目
// （如「周转材料」= 周转材料+包装物+低值易耗品），故用清单而非单一编码兜底。
const rowKeyToAccounts = computed(() => resolveF2RowKeyToAccounts(props.inventoryAccounts))

function accountCodeDisplay(rowKey: string): string {
  const codes = rowKeyToAccounts.value[rowKey]
  if (codes && codes.length > 0) return codes.join('/')
  return F2_ROW_KEY_ACCOUNT[rowKey] || ''
}

const sourceRows = computed<SourceRow[]>(() => {
  if (!props.tbValues) return []
  return F2_CATEGORIES.map((cat) => {
    const entry = props.tbValues![cat.rowKey]
    const accountCode = accountCodeDisplay(cat.rowKey)
    if (!entry) {
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        accountCode,
        formulaOpening: '',
        opening: 0,
        formulaIncrease: '',
        increase: 0,
        formulaDecrease: '',
        decrease: 0,
        closing: 0,
        sourceCodes: [],
      }
    }
    const formulas = entry.formulas || {}
    return {
      rowKey: cat.rowKey,
      label: cat.label,
      accountCode,
      formulaOpening: formulas.opening || `TB('${accountCode || '?'}','期初余额')`,
      opening: entry.opening ?? 0,
      formulaIncrease: formulas.increase || `TB('${accountCode || '?'}','借方发生额')`,
      increase: entry.increase ?? 0,
      formulaDecrease: formulas.decrease || `TB('${accountCode || '?'}','贷方发生额')`,
      decrease: entry.decrease ?? 0,
      closing: entry.closing ?? 0,
      sourceCodes: entry.source_codes || [],
    }
  }).filter((r) => r.opening !== 0 || r.increase !== 0 || r.decrease !== 0 || r.closing !== 0)
})

const totalOpening = computed(() => sourceRows.value.reduce((s, r) => s + r.opening, 0))
const totalClosing = computed(() => sourceRows.value.reduce((s, r) => s + r.closing, 0))

// ─── itemId 镜像 useF2Adjudication ───
function itemId(block: F2BlockKey, rowKey: string, field: string): string {
  return `F2-1-${block}-${rowKey}-${field}`
}

// ─── 刷新取数 ───
async function handleRefresh(): Promise<void> {
  if (props.isReadonly || !props.tbValues) return
  const tbVals = props.tbValues
  const map = props.allResponses

  // 检查是否有手工值需覆盖
  const hasExisting = F2_CATEGORIES.some((cat) => {
    const block: F2BlockKey = cat.rowKey === 'impairment-provision' ? 'impairment' : 'gross'
    const id = itemId(block, cat.rowKey, 'opening')
    const existing = map.get(id)
    return existing && existing.conclusion != null && existing.conclusion !== ''
  })

  if (hasExisting) {
    try {
      await ElMessageBox.confirm(
        '当前值将以四表库值覆盖，是否继续？',
        '刷新取数确认',
        { confirmButtonText: '覆盖', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }

  isRefreshing.value = true
  try {
    let count = 0
    for (const cat of F2_CATEGORIES) {
      const entry = tbVals[cat.rowKey]
      if (!entry) continue
      const block: F2BlockKey = cat.rowKey === 'impairment-provision' ? 'impairment' : 'gross'
      const opening = entry.opening ?? 0
      const increase = entry.increase ?? 0
      const decrease = entry.decrease ?? 0

      if (opening !== 0 || increase !== 0 || decrease !== 0) {
        const fields: Array<[string, number]> = [
          ['opening', opening],
          ['increase', increase],
          ['decrease', decrease],
        ]
        for (const [field, val] of fields) {
          if (val !== 0) {
            const id = itemId(block, cat.rowKey, field)
            map.set(id, { item_id: id, conclusion: String(val), remark: null })
            count++
          }
        }
      }
    }
    ElMessage.success(`已刷新 ${count} 个锚点`)
    emit('refresh-complete')
  } finally {
    isRefreshing.value = false
  }
}

function fmtAmount(val: number | undefined | null): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <details v-if="hasFourTableData" class="f2-ft-source-panel" open>
    <summary>
      🔗 四表取数（公式管理）
      <el-tag size="small" type="success" effect="plain">{{ sourceRows.length }} 条来源</el-tag>
    </summary>

    <div class="ft-body">
      <div class="ft-hint">
        以下数据自动提取自四表库（试算余额表 tb_balance 的叶子子科目，借正贷负）。
        各行金额可在审定表中直接编辑；如四表库数据更新，可点「刷新取数」以最新值覆盖。
      </div>

      <el-table :data="sourceRows" border size="small" style="width: 100%" max-height="360">
        <el-table-column label="类别名" min-width="140">
          <template #default="{ row }">
            <span class="ft-name">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源科目" width="100">
          <template #default="{ row }">
            <span class="ft-code">{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初公式" min-width="180">
          <template #default="{ row }">
            <code class="ft-formula">{{ row.formulaOpening }}</code>
          </template>
        </el-table-column>
        <el-table-column label="期初值" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.opening) }}</template>
        </el-table-column>
        <el-table-column label="增加公式" min-width="180">
          <template #default="{ row }">
            <code class="ft-formula">{{ row.formulaIncrease }}</code>
          </template>
        </el-table-column>
        <el-table-column label="增加值" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.increase) }}</template>
        </el-table-column>
        <el-table-column label="减少公式" min-width="180">
          <template #default="{ row }">
            <code class="ft-formula">{{ row.formulaDecrease }}</code>
          </template>
        </el-table-column>
        <el-table-column label="减少值" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.decrease) }}</template>
        </el-table-column>
        <el-table-column label="期末值" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.closing) }}</template>
        </el-table-column>
      </el-table>

      <div class="ft-footer">
        <span class="ft-total">
          四表提取合计：期初 {{ fmtAmount(totalOpening) }} ｜ 期末 {{ fmtAmount(totalClosing) }}
        </span>
        <el-button
          v-if="!isReadonly"
          type="primary"
          plain
          size="small"
          :loading="isRefreshing"
          @click="handleRefresh"
        >🔄 从四表库刷新取数</el-button>
      </div>
    </div>
  </details>
</template>

<style scoped>
.f2-ft-source-panel {
  margin-bottom: 12px;
  border: 1px solid #d9ecff;
  border-left: 3px solid #409eff;
  background: #f4f9ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.f2-ft-source-panel summary {
  cursor: pointer;
  font-weight: 600;
  color: #337ecc;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ft-body {
  margin-top: 10px;
}
.ft-hint {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 8px;
}
.f2-ft-source-panel :deep(.el-table) {
  font-size: 13px;
}
.f2-ft-source-panel :deep(.el-table th),
.f2-ft-source-panel :deep(.el-table td),
.f2-ft-source-panel :deep(.el-table .cell) {
  font-size: 13px;
}
.ft-code {
  font-weight: 600;
  color: #303133;
}
.ft-name {
  color: #606266;
}
.ft-formula {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #409eff;
  background: #ecf5ff;
  padding: 1px 6px;
  border-radius: 3px;
}
.ft-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.ft-total {
  font-weight: 600;
  color: #303133;
  font-size: 13px;
}
</style>
