<template>
  <el-drawer
    :model-value="visible"
    title="单元格来源"
    direction="rtl"
    size="420px"
    :append-to-body="true"
    destroy-on-close
    @update:model-value="onVisibleChange"
  >
    <template v-if="cellInfo">
      <!-- Section 1: 当前值 + 模式标签 -->
      <section class="cell-source-section">
        <h4 class="cell-source-section__title">当前值</h4>
        <div class="cell-source-value-row">
          <span class="cell-source-value">{{ formatValue(cellInfo.value) }}</span>
          <el-tag
            :type="modeTagType(cellInfo.mode)"
            size="small"
          >{{ modeLabel(cellInfo.mode) }}</el-tag>
        </div>
      </section>

      <!-- Section 2: 绑定来源 -->
      <section class="cell-source-section">
        <h4 class="cell-source-section__title">绑定来源</h4>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="binding_id">
            <code class="cell-source-mono">{{ cellInfo.bindingId || '—' }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="表">
            {{ cellInfo.tableId || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="行">
            {{ cellInfo.rowId || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="列">
            {{ cellInfo.colId || '—' }}
          </el-descriptions-item>
        </el-descriptions>
      </section>

      <!-- Section 3: 公式详情 -->
      <section v-if="cellInfo.formula" class="cell-source-section">
        <h4 class="cell-source-section__title">公式详情</h4>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="公式 ID">
            <code class="cell-source-mono">{{ cellInfo.formula.formulaId }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="表达式">
            <pre class="cell-source-formula-expr">{{ cellInfo.formula.expr }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="来源">
            {{ cellInfo.formula.source || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="最近结果">
            <span class="cell-source-result">{{ cellInfo.formula.lastResult ?? '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="执行时间">
            {{ cellInfo.formula.lastEvaluatedAt || '—' }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 公式错误提示 -->
        <el-alert
          v-if="cellInfo.formula.lastError"
          type="error"
          :title="cellInfo.formula.lastError"
          show-icon
          :closable="false"
          class="cell-source-error"
        />

        <!-- 依赖列表 -->
        <div v-if="cellInfo.formula.dependencies?.length" class="cell-source-deps">
          <span class="cell-source-deps__label">依赖：</span>
          <el-tag
            v-for="(dep, idx) in cellInfo.formula.dependencies"
            :key="idx"
            size="small"
            type="info"
            class="cell-source-dep-tag"
          >{{ depLabel(dep) }}</el-tag>
        </div>
      </section>

      <!-- Section 4: 手工覆盖状态 -->
      <section v-if="cellInfo.manualOverride" class="cell-source-section">
        <h4 class="cell-source-section__title">手工覆盖</h4>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="覆盖值">
            <span class="cell-source-override-value">{{ formatValue(cellInfo.manualOverride.overrideValue) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="原自动值">
            {{ formatValue(cellInfo.manualOverride.originalAutoValue) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="cellInfo.manualOverride.overriddenAt" label="覆盖时间">
            {{ cellInfo.manualOverride.overriddenAt }}
          </el-descriptions-item>
        </el-descriptions>
        <el-button
          v-if="cellInfo.mode !== 'locked'"
          type="warning"
          size="small"
          class="cell-source-restore-btn"
          @click="onRestoreAuto"
        >恢复自动取数</el-button>
      </section>

      <!-- Section 5: 跳转来源 -->
      <section class="cell-source-section">
        <h4 class="cell-source-section__title">跳转来源</h4>
        <div class="cell-source-nav-buttons">
          <el-button
            v-for="nav in navigableLinks"
            :key="nav.type"
            size="small"
            type="primary"
            plain
            @click="onNavigate(nav)"
          >{{ nav.label }}</el-button>
          <span v-if="!navigableLinks.length" class="cell-source-no-nav">无可跳转来源</span>
        </div>
      </section>
    </template>

    <!-- 空状态 -->
    <el-empty v-else description="未选中单元格" :image-size="80" />
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * NoteCellSourceDrawer — 单元格来源面板最小版
 *
 * 点击附注金额单元格时展示公式、来源、执行结果、错误、手工覆盖和恢复自动取数入口。
 *
 * Validates: Requirements 4.1, 4.2, 4.4, 5.5
 */
import { computed } from 'vue'

export interface CellSourceFormula {
  formulaId: string
  expr: string
  source: string
  dependencies: { type: string; wp_code?: string; field?: string }[]
  lastResult?: string
  lastError?: string | null
  lastEvaluatedAt?: string
}

export interface CellSourceManualOverride {
  overrideValue: any
  originalAutoValue: any
  overriddenAt?: string
}

export interface CellSourceInfo {
  value: any
  mode: 'auto' | 'manual' | 'locked' | 'formula' | 'ai_draft'
  tableId?: string
  rowId?: string
  colId?: string
  bindingId?: string
  formula?: CellSourceFormula
  manualOverride?: CellSourceManualOverride
}

export interface NavigateSourcePayload {
  type: string
  id?: string
  wp_code?: string
}

interface Props {
  visible: boolean
  cellInfo: CellSourceInfo | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'navigate-source': [payload: NavigateSourcePayload]
  'restore-auto': []
}>()

interface NavLink {
  type: string
  label: string
  id?: string
  wp_code?: string
}

const navigableLinks = computed<NavLink[]>(() => {
  if (!props.cellInfo) return []
  const links: NavLink[] = []
  const deps = props.cellInfo.formula?.dependencies || []

  for (const dep of deps) {
    if (dep.type === 'workpaper' && dep.wp_code) {
      links.push({
        type: 'workpaper',
        label: `底稿 ${dep.wp_code}`,
        wp_code: dep.wp_code,
      })
    } else if (dep.type === 'report') {
      links.push({ type: 'report', label: '报表' })
    } else if (dep.type === 'trial_balance') {
      links.push({ type: 'trial_balance', label: '试算表' })
    }
  }

  // Deduplicate by type + wp_code
  const seen = new Set<string>()
  return links.filter(l => {
    const key = `${l.type}:${l.wp_code || ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

function modeTagType(mode: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  switch (mode) {
    case 'auto': return 'success'
    case 'formula': return 'success'
    case 'manual': return 'warning'
    case 'locked': return 'danger'
    case 'ai_draft': return 'info'
    default: return ''
  }
}

function modeLabel(mode: string): string {
  const map: Record<string, string> = {
    auto: '自动',
    formula: '公式',
    manual: '手工',
    locked: '锁定',
    ai_draft: 'AI 草稿',
  }
  return map[mode] || mode
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })
  }
  return String(v)
}

function depLabel(dep: { type: string; wp_code?: string; field?: string }): string {
  if (dep.type === 'workpaper' && dep.wp_code) {
    return `WP:${dep.wp_code}${dep.field ? '.' + dep.field : ''}`
  }
  if (dep.type === 'trial_balance') return 'TB'
  if (dep.type === 'report') return 'REPORT'
  if (dep.type === 'prior_note') return 'PRIOR'
  return dep.type.toUpperCase()
}

function onVisibleChange(val: boolean) {
  emit('update:visible', val)
}

function onRestoreAuto() {
  emit('restore-auto')
}

function onNavigate(nav: NavLink) {
  emit('navigate-source', {
    type: nav.type,
    id: nav.id,
    wp_code: nav.wp_code,
  })
}
</script>

<style scoped>
.cell-source-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
}

.cell-source-section:last-child {
  border-bottom: none;
}

.cell-source-section__title {
  margin: 0 0 10px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.cell-source-value-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cell-source-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}

.cell-source-mono {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.cell-source-formula-expr {
  margin: 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--gt-color-primary, #4b2d77);
}

.cell-source-result {
  font-weight: 600;
  color: var(--el-color-success);
}

.cell-source-error {
  margin-top: 10px;
}

.cell-source-deps {
  margin-top: 10px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.cell-source-deps__label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.cell-source-dep-tag {
  margin: 0;
}

.cell-source-override-value {
  font-weight: 600;
  color: var(--el-color-warning);
}

.cell-source-restore-btn {
  margin-top: 12px;
}

.cell-source-nav-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.cell-source-no-nav {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
