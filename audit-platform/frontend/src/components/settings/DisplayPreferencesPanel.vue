<template>
  <div class="gt-display-prefs-panel" :class="{ 'is-compact': compact }" data-testid="display-preferences-panel">
    <div class="gt-dp-row">
      <span class="gt-dp-label">金额单位</span>
      <el-radio-group :model-value="unitChoice" size="small" data-testid="dp-amount-unit" @change="onUnitChoice">
        <el-radio-button value="follow">跟随项目</el-radio-button>
        <el-radio-button v-for="opt in prefs.unitOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
      </el-radio-group>
    </div>
    <div class="gt-dp-hint" data-testid="dp-amount-unit-hint">{{ unitHint }}</div>
    <div class="gt-dp-row">
      <span class="gt-dp-label">表格字号</span>
      <el-radio-group :model-value="prefs.fontSize" size="small" data-testid="dp-font-size" @change="(v: any) => prefs.setFontSize(v)">
        <el-radio-button v-for="opt in prefs.fontOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
      </el-radio-group>
    </div>
    <div class="gt-dp-row">
      <span class="gt-dp-label">小数位数</span>
      <el-radio-group v-if="compact" :model-value="prefs.decimals" size="small" @change="(v: any) => prefs.setDecimals(v)">
        <el-radio-button :value="0">整数</el-radio-button>
        <el-radio-button :value="2">2位</el-radio-button>
        <el-radio-button :value="4">4位</el-radio-button>
      </el-radio-group>
      <el-input-number
        v-else :model-value="prefs.decimals" :min="0" :max="6" :step="1" step-strictly size="small"
        data-testid="dp-decimals" @change="(v: number | undefined) => v != null && prefs.setDecimals(v)"
      />
    </div>
    <div class="gt-dp-row">
      <span class="gt-dp-label">零值显示</span>
      <el-switch :model-value="prefs.showZero" size="small" active-text="0.00" inactive-text="—" @change="(v: any) => prefs.setShowZero(!!v)" />
    </div>
    <div class="gt-dp-row">
      <span class="gt-dp-label">负数红色</span>
      <el-switch :model-value="prefs.negativeRed" size="small" @change="(v: any) => prefs.setNegativeRed(!!v)" />
    </div>
    <div class="gt-dp-row">
      <span class="gt-dp-label">变动高亮</span>
      <el-radio-group :model-value="prefs.highlightThreshold" size="small" @change="(v: any) => prefs.setHighlightThreshold(v)">
        <el-radio-button :value="0">关</el-radio-button>
        <el-radio-button :value="0.1">10%</el-radio-button>
        <el-radio-button :value="0.2">20%</el-radio-button>
        <el-radio-button :value="0.5">50%</el-radio-button>
      </el-radio-group>
    </div>
    <div class="gt-dp-row">
      <span class="gt-dp-label">表格密度</span>
      <el-radio-group :model-value="prefs.density" size="small" data-testid="dp-density" @change="(v: any) => prefs.setDensity(v)">
        <el-radio-button v-for="opt in prefs.densityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
      </el-radio-group>
    </div>
    <!-- 表格编辑方式（spec excel-style-table-editing R1） -->
    <div class="gt-dp-row">
      <span class="gt-dp-label">表格编辑</span>
      <el-radio-group :model-value="prefs.gridEditMode" size="small" data-testid="grid-edit-mode" @change="(v: any) => prefs.setGridEditMode(v)">
        <el-radio-button v-for="opt in prefs.gridEditModeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
      </el-radio-group>
    </div>
    <div class="gt-dp-hint">{{ gridEditModeHint }}</div>

    <template v-if="!compact">
      <div class="gt-dp-section-title">已保存的固定列</div>
      <div v-if="!fixedEntries.length" class="gt-dp-hint" data-testid="dp-fixed-empty">还没有保存过固定列。</div>
      <div v-for="entry in fixedEntries" :key="entry.pageKey" class="gt-dp-fixed-row" data-testid="dp-fixed-entry">
        <span class="gt-dp-fixed-key" :title="entry.pageKey">{{ entry.pageKey }}</span>
        <span class="gt-dp-fixed-count">{{ entry.count }} 列</span>
        <el-button link type="primary" size="small" @click="prefs.clearFixedColumns(entry.pageKey)">清除</el-button>
      </div>
    </template>

    <div class="gt-dp-sync" :class="`is-${syncTone}`" data-testid="dp-sync-status">
      <span>{{ syncText }}</span>
      <el-button v-if="canRetry" link type="primary" size="small" data-testid="dp-sync-retry" @click="prefs.retryPending()">重试同步</el-button>
    </div>
    <div class="gt-dp-hint">显示设置只影响屏幕显示；正式导出的金额单位按项目和模板确定。</div>
  </div>
</template>

<script setup lang="ts">
/**
 * 当前账号的显示偏好面板（spec platform-global-display-settings-closure R2 / R3 / AC-07）。
 *
 * 顶栏「Aa」用紧凑形态，`/display-settings` 与管理员系统设置用完整形态，三处是同一个组件。
 * 只读写 displayPrefs store；保存、同步、冲突重放都由 store 负责。
 */
import { computed } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useProjectStore } from '@/stores/project'
import { AMOUNT_UNITS, type AmountUnit } from '@/utils/formatters'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })

const prefs = useDisplayPrefsStore()
const projectStore = useProjectStore()

const unitChoice = computed(() => prefs.amountUnitOverride ?? 'follow')

function onUnitChoice(value: string | number | boolean | undefined): void {
  if (value === 'follow') prefs.followProjectUnit()
  else if (typeof value === 'string' && value in AMOUNT_UNITS) prefs.setUnit(value as AmountUnit)
}

const unitHint = computed(() => {
  const projectUnit = projectStore.projectAmountUnit
  const effective = AMOUNT_UNITS[prefs.amountUnit]?.label ?? '元'
  if (prefs.amountUnitOverride) return `当前按个人设置显示：${effective}`
  if (!projectStore.projectId) return '当前未进入项目，按元显示'
  if (!projectUnit) return '项目默认单位尚未读取，暂按元显示'
  return `当前跟随项目默认单位：${AMOUNT_UNITS[projectUnit]?.label ?? '元'}`
})

const gridEditModeHint = computed(() => {
  const option = prefs.gridEditModeOptions.find((item) => item.value === prefs.gridEditMode)
  return option?.hint ?? ''
})

const fixedEntries = computed(() => Object.entries(prefs.fixedColumns)
  .map(([pageKey, entry]) => ({ pageKey, count: entry.columns.length }))
  .sort((a, b) => a.pageKey.localeCompare(b.pageKey)))

const syncText = computed(() => {
  if (prefs.syncMessage) return prefs.syncMessage
  if (!prefs.ownerUserId) return '未登录，设置不会保存'
  if (prefs.loadState === 'loading') return '正在读取显示偏好…'
  switch (prefs.syncState) {
    case 'syncing': return '正在同步…'
    case 'pending': return '有更改待同步'
    case 'offline': return '服务端暂不可用，当前设置只保存在本机'
    case 'conflict': return '版本冲突，仍有更改待同步'
    default: return prefs.loadState === 'offline' ? '服务端暂不可用，当前使用本机或默认设置' : '已同步到账号'
  }
})

const syncTone = computed(() => {
  if (prefs.syncState === 'offline' || prefs.syncState === 'conflict' || prefs.loadState === 'offline') return 'warning'
  if (prefs.syncState === 'pending' || prefs.syncState === 'syncing' || prefs.loadState === 'loading') return 'info'
  return 'ok'
})

const canRetry = computed(() => !!prefs.ownerUserId && prefs.hasPendingChanges
  && (prefs.syncState === 'offline' || prefs.syncState === 'conflict'))
</script>

<style scoped>
.gt-display-prefs-panel { display: flex; flex-direction: column; gap: 10px; }
.gt-display-prefs-panel.is-compact { gap: 8px; }
.gt-display-prefs-panel.is-compact :deep(.el-radio-button__inner) { padding: 4px 8px; font-size: var(--gt-font-size-xs, 11px); }
.gt-dp-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.gt-dp-label { color: var(--gt-color-text-secondary, #606266); font-size: var(--gt-font-size-sm, 12px); min-width: 56px; }
.gt-dp-hint { color: var(--gt-color-text-tertiary, #909399); font-size: var(--gt-font-size-xs, 11px); line-height: 1.5; }
.gt-dp-section-title { margin-top: 6px; font-weight: 600; font-size: var(--gt-font-size-sm, 12px); }
.gt-dp-fixed-row { display: flex; align-items: center; gap: 8px; font-size: var(--gt-font-size-sm, 12px); }
.gt-dp-fixed-key { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-dp-fixed-count { color: var(--gt-color-text-tertiary, #909399); }
.gt-dp-sync { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: var(--gt-font-size-xs, 11px); }
.gt-dp-sync.is-ok { color: var(--gt-color-success, #28a745); }
.gt-dp-sync.is-info { color: var(--gt-color-info, #909399); }
.gt-dp-sync.is-warning { color: var(--gt-color-warning, #e6a23c); }
</style>
