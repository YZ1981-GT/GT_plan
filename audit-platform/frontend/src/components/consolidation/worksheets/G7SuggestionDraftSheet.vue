<template>
  <div class="g7-sug">
    <div class="sheet-head">
      <div class="head-main">
        <h3>G7 建议草稿</h3>
        <el-tag size="small" type="warning" effect="plain">草稿 · 需人工复核</el-tag>
        <el-tag v-if="rows.length" size="small" effect="plain">共 {{ rows.length }} 条</el-tag>
        <el-tag v-if="importedAtText" size="small" type="info" effect="plain">
          写入时间 {{ importedAtText }}
        </el-tag>
      </div>
      <div class="head-actions">
        <el-button size="small" @click="emit('goto-sheet', 'elimination')">前往合并抵消分录</el-button>
        <el-button size="small" @click="emit('refresh')">刷新</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="notice">
      本表为 G7 联动写入的<strong>建议草稿</strong>：仅供项目组复核参考，
      <strong>不构成正式抵消分录</strong>，也不参与合并报表计算。确认采纳后，请在
      「合并抵消分录」「资本公积变动」「投资明细-权益法」等正式表中手工录入。
      <template v-if="note">
        <br />后端说明：{{ note }}
      </template>
    </el-alert>

    <el-empty
      v-if="!rows.length"
      description="暂无建议草稿。请在本页工具栏点「从 G7 联动」，在预览弹窗中勾选建议后确认导入。"
    />

    <el-table
      v-else
      :data="rows"
      size="small"
      border
      stripe
      max-height="560"
      class="sug-table"
    >
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="expand-body">
            <div v-for="field in detailFields(row)" :key="field.key" class="expand-row">
              <span class="expand-label">{{ field.key }}</span>
              <span class="expand-value">{{ field.value }}</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="来源" prop="source_sheet" width="90" />
      <el-table-column label="类型" width="170">
        <template #default="{ row }">
          <el-tag size="small" effect="plain" :type="typeTagType(row.type)">
            {{ typeLabel(row.type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="被投资单位 / 主体" min-width="180">
        <template #default="{ row }">
          {{ row.company_name || row.company_code || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="关键金额" width="150" align="right">
        <template #default="{ row }">
          <span v-if="keyAmount(row) == null">—</span>
          <span v-else>{{ fmtAmount(keyAmount(row) as number) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="拟进入" min-width="200">
        <template #default="{ row }">
          {{ row.target_hint || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="240">
        <template #default="{ row }">
          {{ row.description || row.note || '—' }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * G7SuggestionDraftSheet — 合并工作底稿「G7 建议草稿」只读视图
 *
 * 数据源：consol_worksheet_data.sheet_key='g7_suggestions'（由
 * g7_consol_linkage_service.import_g7_linkage 在用户勾选建议后写入）。
 *
 * 只读展示，绝不参与合并计算，也不生成抵消分录（与后端 note 口径一致）。
 * 建议行字段随 type 而异（G7-3/6/9/10/13/15/16 各不相同），故主表只渲染
 * 通用列，其余字段经展开行原样列出，避免臆造字段映射。
 */
import { computed } from 'vue'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{
  rows: Record<string, any>[]
  note?: string
  importedAt?: string
}>()

const emit = defineEmits<{
  'goto-sheet': [sheetKey: string]
  refresh: []
}>()

const rows = computed(() => (Array.isArray(props.rows) ? props.rows : []))
const note = computed(() => props.note || '')

const importedAtText = computed(() => {
  const raw = props.importedAt
  if (!raw) return ''
  const d = new Date(raw)
  return Number.isNaN(d.getTime()) ? String(raw) : d.toLocaleString('zh-CN')
})

/** 与后端 build_g7*_suggestions 的 type 取值一一对应（不臆造，未知类型原样显示） */
const TYPE_LABELS: Record<string, string> = {
  goodwill_nci: '商誉 / 少数股东权益（G7-9）',
  share_change_capital: '股比变动 · 权益调整（G7-10）',
  consol_adjustment_draft: '调整分录草稿（G7-3）',
  investment_cost_goodwill: '投资成本差额 · 商誉（G7-13）',
  investment_cost_bargain: '投资成本差额 · 廉价购买（G7-13）',
  unrecognized_loss: '未确认投资损失（G7-16）',
  internal_transaction_elim: '内部交易抵销（G7-15）',
  accounting_policy_adj: '会计政策调整（G7-6）',
}

const TYPE_TAG_TYPES: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  goodwill_nci: 'warning',
  share_change_capital: 'warning',
  consol_adjustment_draft: 'danger',
  investment_cost_goodwill: 'info',
  investment_cost_bargain: 'info',
  unrecognized_loss: 'danger',
  internal_transaction_elim: 'warning',
  accounting_policy_adj: 'info',
}

function typeLabel(type: unknown): string {
  const key = String(type || '')
  return TYPE_LABELS[key] || key || '—'
}

function typeTagType(type: unknown): 'success' | 'warning' | 'danger' | 'info' {
  return TYPE_TAG_TYPES[String(type || '')] || 'info'
}

/** 各 type 的主金额字段（顺序即优先级；均取自后端建议字段名） */
const AMOUNT_KEYS = [
  'goodwill_amount',
  'difference',
  'unrecognized_loss',
  'policy_adj_amount',
  'equity_adjustment',
  'amount',
  'debit_amount',
  'credit_amount',
  'current_change',
]

function keyAmount(row: Record<string, any>): number | null {
  for (const key of AMOUNT_KEYS) {
    const raw = row?.[key]
    if (raw == null || raw === '') continue
    const num = Number(raw)
    if (Number.isFinite(num) && num !== 0) return num
  }
  return null
}

const HIDDEN_FIELDS = new Set(['id', 'selected_default', 'type', 'source_sheet'])

/** 展开行：列出该建议的全部业务字段（跳过内部字段与空值） */
function detailFields(row: Record<string, any>): Array<{ key: string; value: string }> {
  if (!row || typeof row !== 'object') return []
  return Object.entries(row)
    .filter(([key, value]) =>
      !HIDDEN_FIELDS.has(key)
      && !key.startsWith('_')
      && value != null
      && value !== '',
    )
    .map(([key, value]) => ({
      key,
      value: typeof value === 'object' ? JSON.stringify(value) : String(value),
    }))
}
</script>

<style scoped>
.g7-sug { font-size: 13px; padding: 4px 0; }
.sheet-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 10px;
}
.head-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.head-main h3 { margin: 0; font-size: 14px; }
.head-actions { display: flex; gap: 8px; }
.notice { margin-bottom: 12px; }
.sug-table { font-size: 13px; }
.sug-table :deep(.el-table__cell) { font-size: 13px; }
.expand-body { padding: 8px 16px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 24px; }
.expand-row { display: flex; gap: 8px; font-size: 12px; }
.expand-label { flex-shrink: 0; min-width: 170px; color: var(--el-text-color-secondary); }
.expand-value { color: var(--el-text-color-primary); word-break: break-all; }
</style>
