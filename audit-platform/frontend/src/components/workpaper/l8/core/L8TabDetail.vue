<template>
  <div class="l8-tab-detail">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8-2 财务费用明细表</h3>
        <el-tag type="warning" size="small">23列·3区段Tab</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增项目
        </el-button>
        <el-dropdown :disabled="isReadonly" @command="handleImportExport" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>分析财务费用各项目月度发生额构成的合理性与期间归属，明细合计与审定表 L8-1 勾稽一致（损益类发生额口径）。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>23列按3区段Tab管理（行同步）：</strong>
        费用项目区（项目名称+勾稽索引）→ 月度金额区（1月~12月发生额）→ 期末汇总+审定区（未审合计/AJE/RJE/审定/占比/上期）。
        净财务费用 = 利息支出 − 利息收入 + 汇兑损益 + 手续费 + 其他。行同步切换不丢数据。
      </div>
    </div>

    <!-- ═══ 跨sheet交叉验证警告 ═══ -->
    <el-alert
      v-if="showCrossSheetWarning"
      type="error"
      :closable="false"
      show-icon
      class="cross-sheet-alert"
    >
      <template #title>
        明细合计与审定表L8-1不一致（差额需核查）
      </template>
    </el-alert>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <div style="display:flex;align-items:center;margin-bottom:12px">
      <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" />
      <el-popover placement="bottom-end" :width="220" trigger="click">
        <template #reference>
          <el-button size="small" style="margin-left:8px">⚙ 列设置</el-button>
        </template>
        <div class="col-prefs">
          <div class="col-prefs-title">当前区段列显隐</div>
          <template v-for="col in currentSegmentCols" :key="col.key">
            <el-checkbox v-model="col.visible" size="small" @change="persistColPrefs">{{ col.label }}</el-checkbox>
          </template>
          <el-divider style="margin:6px 0" />
          <el-button size="small" link @click="resetColPrefs">重置默认</el-button>
        </div>
      </el-popover>
    </div>

    <!-- ═══ 明细表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="itemName" label="费用项目" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(val: string) => handleUpdate($index, 'itemName', val)" />
          <span v-else>{{ row.itemName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 区段1: 费用项目信息 ═══ -->
      <template v-if="activeSegment === 'items'">
        <el-table-column v-if="isColVisible('crossRef')" label="与相关科目勾稽" min-width="200">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.crossRef" size="small" placeholder="如:短期借款利息/L1" @change="(val: string) => handleUpdate($index, 'crossRef', val)" />
            <span v-else>{{ row.crossRef || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 月度金额（1月~12月） ═══ -->
      <template v-if="activeSegment === 'monthly'">
        <template v-for="m in 12" :key="`month-${m}`">
          <el-table-column
            v-if="isMonthVisible(m - 1)"
            :label="`${m}月`"
            width="100"
            align="right"
          >
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.monthly[m - 1]"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => handleMonthlyUpdate($index, m - 1, val ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.monthly[m - 1]) }}</span>
            </template>
          </el-table-column>
        </template>
      </template>

      <!-- ═══ 区段3: 期末汇总+审定 ═══ -->
      <template v-if="activeSegment === 'summary'">
        <el-table-column v-if="isColVisible('periodUnadjusted')" label="本期未审" width="130" align="right">
          <template #header>
            <el-tooltip content="公式: SUM(1月~12月)" placement="top">
              <span class="formula-col-header">本期未审</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.periodUnadjusted) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('aje')" label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'aje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('rje')" label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('periodAudited')" label="本期审定" width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 未审合计 + AJE + RJE" placement="top">
              <span class="formula-col-header">本期审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value--primary">{{ fmtAmount(row.periodAudited) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('ratio')" label="占比" width="80" align="right">
          <template #header>
            <el-tooltip content="公式: 本期审定/合计×100%" placement="top">
              <span class="formula-col-header">占比</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ row.ratio ? row.ratio.toFixed(1) + '%' : '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('priorUnadjusted')" label="上期未审" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorUnadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorUnadjusted', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('priorAje')" label="上期AJE" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorAje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorAje) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('priorRje')" label="上期RJE" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorRje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorRje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorRje) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('priorAudited')" label="上期审定" width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 上期未审+上期AJE+上期RJE" placement="top">
              <span class="formula-col-header">上期审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.priorAudited) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除该项目？" @confirm="handleRemoveRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 净财务费用高亮汇总 ═══ -->
    <div class="summary-bar">
      <span>本期审定合计：<strong class="formula-value--primary">{{ fmtAmount(totalPeriodAudited) }}</strong></span>
      <span>上期审定合计：<strong>{{ fmtAmount(totalPriorAudited) }}</strong></span>
      <span>变动率：<strong :class="{ 'abnormal-rate': totalChangeRate !== 'N/A' && Math.abs(totalChangeRate as number) > 20 }">{{ fmtRate(totalChangeRate) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 个项目</span>
    </div>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip） ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 利息汇聚来源：</span>
      <GtIndexChip value="L1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">短期借款利息</span>
      <GtIndexChip value="L3" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">长期借款利息</span>
      <GtIndexChip value="L4" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">应付债券利息</span>
      <GtIndexChip value="L5" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">未确认融资费用摊销</span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写财务费用明细审计说明..." :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>23列按3区段Tab拆分管理，行跨区段同步（切换不丢数据）</li>
        <li>本期未审合计（N列）= SUM(1月~12月)；本期审定 = 未审合计 + AJE + RJE</li>
        <li>占比 = 本期审定 / 合计行审定 × 100%</li>
        <li>默认行对齐L8-1审定表10项费用结构，可新增自定义项目</li>
        <li>利息支出与L1/L3/L4/L5联动（通过EventBus自动接收）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabDetail — L8-2 财务费用明细表（23列·3区段Tab）
 *
 * Requirements: 3.1-3.6
 * - 23列宽表拆3段：费用项目/月度金额(1~12月)/期末汇总+审定
 * - 动态行新增（ElMessageBox.prompt输入名称）
 * - 导入导出三级 using useL8ImportExport
 * - 公式列：虚线下划线 + cursor:help + tooltip
 * - 与L8-1审定表交叉验证
 */
import { computed, inject, onMounted, ref, reactive } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useL8FormData } from '../../composables/useL8FormData'
import {
  useL8Detail,
  L8_DETAIL_SEGMENTS,
  L8_DETAIL_DEFAULT_ITEMS,
  type L8DetailRow,
  type L8DetailSegment,
} from '../../composables/useL8Detail'
import { useL8ImportExport } from '../../composables/useL8ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useL8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<L8DetailRow[]>(
  L8_DETAIL_DEFAULT_ITEMS.map((name, i) => ({
    key: `l8-detail-default-${i}`,
    itemName: name,
    monthly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] as [number, number, number, number, number, number, number, number, number, number, number, number],
    periodUnadjusted: 0,
    aje: 0,
    rje: 0,
    periodAudited: 0,
    ratio: 0,
    crossRef: '',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
  }))
)

const {
  activeSegment,
  computedRows,
  totalPeriodAudited,
  totalPriorAudited,
  totalChangeRate,
  abnormalRows,
  addRow,
  removeRow,
  updateRow,
  updateMonthly,
} = useL8Detail(formData, detailRows)

const { exportTemplate, exportData, importData } = useL8ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Segment options ─────────────────────────────────────────────────────────

const segmentOptions = L8_DETAIL_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Column Preferences ──────────────────────────────────────────────────────

const COL_PREFS_KEY = 'l8-2-column-prefs'
interface ColPref { key: string; label: string; visible: boolean }
const colPrefs = reactive<Record<string, ColPref[]>>({
  items: [
    { key: 'crossRef', label: '与相关科目勾稽', visible: true },
  ],
  monthly: [
    { key: 'month1', label: '1月', visible: true },
    { key: 'month2', label: '2月', visible: true },
    { key: 'month3', label: '3月', visible: true },
    { key: 'month4', label: '4月', visible: true },
    { key: 'month5', label: '5月', visible: true },
    { key: 'month6', label: '6月', visible: true },
    { key: 'month7', label: '7月', visible: true },
    { key: 'month8', label: '8月', visible: true },
    { key: 'month9', label: '9月', visible: true },
    { key: 'month10', label: '10月', visible: true },
    { key: 'month11', label: '11月', visible: true },
    { key: 'month12', label: '12月', visible: true },
  ],
  summary: [
    { key: 'periodUnadjusted', label: '本期未审', visible: true },
    { key: 'aje', label: 'AJE', visible: true },
    { key: 'rje', label: 'RJE', visible: true },
    { key: 'periodAudited', label: '本期审定', visible: true },
    { key: 'ratio', label: '占比', visible: true },
    { key: 'priorUnadjusted', label: '上期未审', visible: true },
    { key: 'priorAje', label: '上期AJE', visible: true },
    { key: 'priorRje', label: '上期RJE', visible: true },
    { key: 'priorAudited', label: '上期审定', visible: true },
  ],
})
const currentSegmentCols = computed(() => colPrefs[activeSegment.value] || [])
function isColVisible(key: string): boolean {
  const seg = colPrefs[activeSegment.value]
  if (!seg) return true
  const col = seg.find(c => c.key === key)
  return col?.visible ?? true
}
function isMonthVisible(monthIndex: number): boolean {
  return isColVisible(`month${monthIndex + 1}`)
}
function persistColPrefs(): void {
  try { localStorage.setItem(COL_PREFS_KEY, JSON.stringify(Object.fromEntries(Object.entries(colPrefs).map(([k, v]) => [k, v.map(c => ({ key: c.key, visible: c.visible }))])))) } catch {}
}
function resetColPrefs(): void {
  for (const cols of Object.values(colPrefs)) cols.forEach(c => { c.visible = true })
  persistColPrefs()
}
;(function loadColPrefs() {
  try {
    const saved = localStorage.getItem(COL_PREFS_KEY)
    if (!saved) return
    const data = JSON.parse(saved)
    for (const [seg, prefs] of Object.entries(data as Record<string, Array<{ key: string; visible: boolean }>>)) {
      const target = colPrefs[seg]
      if (!target) continue
      for (const p of prefs) { const col = target.find(c => c.key === p.key); if (col) col.visible = p.visible }
    }
  } catch {}
})()

// ─── Cross-sheet ─────────────────────────────────────────────────────────────

const showCrossSheetWarning = ref(false) // populated by CrossSheet composable integration

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof L8DetailRow, value: any) { updateRow(index, field, value) }
function handleMonthlyUpdate(rowIndex: number, monthIndex: number, value: number) { updateMonthly(rowIndex, monthIndex, value) }

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('L8-2')
      break
    case 'exportData':
      exportData('L8-2')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'L8-2')
          if (result) {
            await formData.loadData()
            _restoreRows()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

// ─── Audit Note ──────────────────────────────────────────────────────────────

const auditNote = ref('')

function saveAuditNote() {
  formData.debouncedSave('L8-2-auditNote', { remark: auditNote.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l8-detail-${section}`,
      prompt: `请基于财务费用底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.('L8-2-detail', '明细表') }

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | 'N/A'): string {
  if (val === 'N/A') return 'N/A'
  if (val === 0) return '—'
  return (val as number).toFixed(2) + '%'
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
})

function _restoreRows() {
  const fullData = formData.allResponses.value.get('L8-2-full-data')
  if (fullData?.remark) {
    try {
      const parsed = JSON.parse(fullData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed
      }
    } catch { /* keep defaults */ }
  }
}
</script>

<style scoped>
.l8-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }
.col-prefs { max-height: 280px; overflow-y: auto; }
.col-prefs-title { font-weight: 600; margin-bottom: 6px; font-size: 13px; }
.col-prefs :deep(.el-checkbox) { display: block; margin-bottom: 3px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
.abnormal-rate { color: #e6a23c; font-weight: 700; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; flex-wrap: wrap; }
.cross-wp-links { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #d9ecff; border-radius: 6px; flex-wrap: wrap; }
.cross-wp-label { font-size: 12px; color: #409eff; font-weight: 500; }
.cross-wp-desc { font-size: 12px; color: #909399; }
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
