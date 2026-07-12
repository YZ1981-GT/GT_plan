<script setup lang="ts">
/** G 循环附注 — 报表校对 + ƒx 公式管理 drawer（对标 D4 附注） */
import { ref } from 'vue'

export interface GCycleFormulaMapRow {
  field: string
  source: string
  formula: string
  account: string
}

const props = defineProps<{
  cycleLabel: string
  accountCode: string
  adjudicatedAmount: number | null
  disclosureTotal: number
  formulaMap: GCycleFormulaMapRow[]
  manualFormulaNotes?: string[]
  isRefreshing?: boolean
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const showFormulaDrawer = ref(false)

function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const reconcileDiff = () => {
  if (props.adjudicatedAmount == null) return null
  return props.adjudicatedAmount - props.disclosureTotal
}
</script>

<template>
  <div class="g-cycle-disclosure-extras">
    <div class="disclosure-toolbar">
      <el-button size="small" :loading="isRefreshing" :disabled="isReadonly" @click="emit('refresh')">
        🔄 报表校对刷新
      </el-button>
      <el-button size="small" @click="showFormulaDrawer = true">ƒx 公式管理</el-button>
      <span class="toolbar-hint">{{ cycleLabel }} · 科目 {{ accountCode }}</span>
    </div>

    <el-drawer v-model="showFormulaDrawer" title="公式管理 - 数据来源映射" size="480px" direction="rtl">
      <div class="formula-drawer-content">
        <p class="formula-desc">以下字段从审定表/明细表自动汇总，点击「报表校对刷新」更新。</p>
        <el-table :data="formulaMap" border size="small" style="width: 100%">
          <el-table-column prop="field" label="字段" width="160" />
          <el-table-column prop="source" label="数据源" width="120" />
          <el-table-column prop="formula" label="公式/取数逻辑" min-width="200">
            <template #default="{ row }">
              <code class="formula-code">{{ row.formula }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="account" label="科目" width="60" align="center" />
        </el-table>
        <ul v-if="manualFormulaNotes?.length" class="formula-manual-list">
          <li v-for="(note, i) in manualFormulaNotes" :key="i">{{ note }}</li>
        </ul>
      </div>
    </el-drawer>

    <el-card class="reconcile-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">📊 报表校对</span>
          <el-button size="small" :loading="isRefreshing" :disabled="isReadonly" @click="emit('refresh')">
            🔄 重新校对
          </el-button>
        </div>
      </template>
      <div class="reconcile-grid">
        <div class="reconcile-item">
          <span class="reconcile-label">审定表合计</span>
          <span class="reconcile-value">{{ fmtAmt(adjudicatedAmount) }}</span>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">附注表合计</span>
          <span class="reconcile-value">{{ fmtAmt(disclosureTotal) }}</span>
        </div>
        <div
          class="reconcile-item"
          :class="{ 'reconcile-diff': reconcileDiff() != null && Math.abs(reconcileDiff()!) > 0.01 }"
        >
          <span class="reconcile-label">差异</span>
          <span class="reconcile-value">
            {{ reconcileDiff() != null ? fmtAmt(reconcileDiff()) : '待刷新' }}
          </span>
        </div>
      </div>
      <div class="reconcile-note">差异≠0 时请检查审定表是否已更新，或点击「从明细同步」。</div>
    </el-card>
  </div>
</template>

<style scoped>
.g-cycle-disclosure-extras { margin-top: 12px; }
.disclosure-toolbar {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
  padding: 8px 12px; background: #f5f7fa; border-radius: 6px;
}
.toolbar-hint { font-size: 12px; color: #909399; margin-left: auto; }
.formula-drawer-content { padding: 0 4px; }
.formula-desc { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 12px; }
.formula-code {
  font-size: 11px; background: #f5f7fa; padding: 2px 4px;
  border-radius: 2px; color: #409eff; word-break: break-all;
}
.formula-manual-list { font-size: var(--wp-font-size, 13px); color: #606266; padding-left: 20px; margin-top: 12px; }
.reconcile-card :deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; }
.section-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; }
.reconcile-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.reconcile-item { padding: 10px 12px; background: #f5f7fa; border-radius: 4px; text-align: center; }
.reconcile-label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.reconcile-value { font-size: 14px; font-weight: 600; color: #303133; }
.reconcile-diff { background: #fef0f0; }
.reconcile-diff .reconcile-value { color: #f56c6c; }
.reconcile-note { margin-top: 10px; font-size: 12px; color: #909399; }
</style>
