<template>
  <el-card shadow="never" class="eqcr-tab__section">
    <template #header>
      <div class="eqcr-tab__section-header">
        <div>
          <span class="eqcr-tab__section-title">关联方交易</span>
          <el-tag size="small" type="info" effect="plain">
            共 {{ transactions.length }} 笔
          </el-tag>
        </div>
        <el-button
          v-if="canWrite && hasRegistries"
          type="primary"
          size="small"
          @click="$emit('add')"
        >
          + 新增交易
        </el-button>
      </div>
    </template>

    <el-empty
      v-if="transactions.length === 0"
      description="该项目尚未登记关联方交易"
      :image-size="60"
    />

    <el-table
      v-else
      :data="transactions"
      size="small"
      border
      stripe
      style="width: 100%"
    >
      <el-table-column label="关联方" min-width="220">
        <template #default="{ row }">
          {{ registryName(row.related_party_id) }}
        </template>
      </el-table-column>
      <el-table-column label="交易类型" width="140">
        <template #default="{ row }">
          {{ TXN_TYPE_LABELS[row.transaction_type] || row.transaction_type }}
        </template>
      </el-table-column>
      <el-table-column label="金额" width="180" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.amount) }}
        </template>
      </el-table-column>
      <el-table-column label="是否公允" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.is_arms_length === true" type="success" size="small" effect="light">公允</el-tag>
          <el-tag v-else-if="row.is_arms_length === false" type="danger" size="small" effect="light">非公允</el-tag>
          <span v-else class="eqcr-muted">未评</span>
        </template>
      </el-table-column>
      <el-table-column label="证据引用" min-width="200">
        <template #default="{ row }">
          <span v-if="!row.evidence_refs" class="eqcr-muted">—</span>
          <span v-else>{{ renderEvidence(row.evidence_refs) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="canWrite" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="$emit('edit', row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="$emit('delete', row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import type { EqcrRelatedPartyTransaction } from '@/services/eqcrService'

const props = defineProps<{
  transactions: EqcrRelatedPartyTransaction[]
  canWrite: boolean
  hasRegistries: boolean
  registryNameMap: Record<string, string>
}>()

defineEmits<{
  add: []
  edit: [row: EqcrRelatedPartyTransaction]
  delete: [row: EqcrRelatedPartyTransaction]
}>()

function registryName(id: string): string {
  return props.registryNameMap[id] ?? '（已删除）'
}

const TXN_TYPE_LABELS: Record<string, string> = {
  sales: '销售', purchase: '采购', loan: '借款',
  guarantee: '担保', service: '服务', asset_transfer: '资产转让', other: '其他',
}

function formatAmount(value: string | null): string {
  if (value === null || value === undefined || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return value
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function renderEvidence(refs: any): string {
  if (Array.isArray(refs)) return refs.length === 0 ? '—' : refs.join('、')
  if (typeof refs === 'string') return refs
  try { return JSON.stringify(refs) } catch { return '—' }
}
</script>

<style scoped>
.eqcr-tab__section { border-radius: var(--gt-radius-md, 6px); }
.eqcr-tab__section-header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.eqcr-tab__section-title { font-weight: 600; color: var(--gt-color-text, #303133); margin-right: 10px; }
.eqcr-muted { color: var(--gt-color-text-tertiary, #909399); }
</style>
