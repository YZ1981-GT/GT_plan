<template>
  <div class="l7-tab-detail">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L7-2 其他非流动负债明细表</h3>
        <el-tag type="warning" size="small">27列·2区段Tab</el-tag>
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
        <strong>审计目标：</strong>核实其他非流动负债各项目的性质、形成原因与到期情况，明细合计与审定表 L7-1 逐项勾稽一致。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>27列按2区段Tab管理：</strong>
        项目信息区（项目名称/性质/形成原因/到期情况/期初未审·AJE·RJE·审定） →
        金额变动区（本期AJE增减/本期RJE增减/期末未审·AJE·RJE·审定）。
        负债类（贷方）：期末审定=期末未审+期末AJE−期末RJE。各行与L7-1审定表逐项对应。
      </div>
    </div>

    <!-- ═══ 跨sheet交叉验证警告 ═══ -->
    <el-alert
      v-if="!crossSheetMatch"
      type="error"
      :closable="false"
      show-icon
      class="cross-sheet-alert"
    >
      <template #title>
        明细合计与审定表不一致：差额 {{ fmtAmount(crossSheetDiff) }} 元
      </template>
    </el-alert>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="itemName" label="项目名称" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(val: string) => handleUpdate($index, 'itemName', val)" />
          <span v-else>{{ row.itemName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 区段1: 项目信息 ═══ -->
      <template v-if="activeSegment === 'project-info'">
        <el-table-column label="性质" min-width="130">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.nature" size="small" @change="(val: string) => handleUpdate($index, 'nature', val)" />
            <span v-else>{{ row.nature || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="形成原因" min-width="180">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(val: string) => handleUpdate($index, 'reason', val)" />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期情况" min-width="130">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.maturityInfo" size="small" @change="(val: string) => handleUpdate($index, 'maturityInfo', val)" />
            <span v-else>{{ row.maturityInfo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初未审" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginUnadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginUnadjusted', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初AJE" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginAje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginAje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初RJE" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginRje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginRje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初未审+期初AJE−期初RJE" placement="top">
              <span class="formula-col-header">期初审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.beginAudited) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 金额变动 ═══ -->
      <template v-if="activeSegment === 'amount-movement'">
        <el-table-column label="本期AJE增加" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.ajeIncrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'ajeIncrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.ajeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期RJE增加" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.rjeIncrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rjeIncrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.rjeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末AJE增" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.endAjeIncrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'endAjeIncrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.endAjeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末RJE减" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.endRjeDecrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'endRjeDecrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.endRjeDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末AJE减" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.endAjeDecrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'endAjeDecrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.endAjeDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末RJE增" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.endRjeIncrease" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'endRjeIncrease', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.endRjeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末未审" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初未审+本期AJE增+本期RJE增" placement="top">
              <span class="formula-col-header">期末未审</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末AJE" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初AJE+期末AJE增+期末AJE减" placement="top">
              <span class="formula-col-header">期末AJE</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末RJE" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初RJE+期末RJE减+期末RJE增" placement="top">
              <span class="formula-col-header">期末RJE</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期末未审+期末AJE−期末RJE" placement="top">
              <span class="formula-col-header">期末审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value--primary">{{ fmtAmount(row.endAudited) }}</span>
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

    <!-- ═══ 合计行 ═══ -->
    <div class="summary-bar">
      <span>期末审定合计：<strong class="formula-value--primary">{{ fmtAmount(totalEndAudited) }}</strong></span>
      <span>期初审定合计：<strong>{{ fmtAmount(totalBeginAudited) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 个项目</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>27列按2区段Tab拆分，行跨区段同步</li>
        <li>负债类（贷方）：期末审定=期末未审+期末AJE−期末RJE</li>
        <li>公式列：期初审定=B+C−D，期末未审=B+F+G，期末AJE=C+H+J，期末RJE=D+I+K，期末审定=L+M−N</li>
        <li>明细合计应与审定表L7-1核对一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabDetail — L7-2 其他非流动负债明细表（27列·2区段Tab）
 *
 * Requirements: 3.1-3.5
 * - 27列宽表拆分：项目信息区/金额变动区（行同步）
 * - 动态行新增（ElMessageBox.prompt输入项目名称）+ 删除确认
 * - 导入导出三级（el-dropdown）using useL7ImportExport
 * - 公式列：虚线下划线 + cursor:help + tooltip来源
 * - 与L7-1审定表交叉验证（红色警告）using useL7CrossSheet.adjudicationVsDetail
 * - Font 13px, min-width自适应列
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useL7FormData } from '../../composables/useL7FormData'
import { useL7Detail, type L7DetailRow, L7_DETAIL_SEGMENTS } from '../../composables/useL7Detail'
import { useL7ImportExport } from '../../composables/useL7ImportExport'
import { useL7CrossSheet } from '../../composables/useL7CrossSheet'

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

const formData = useL7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<L7DetailRow[]>([])

const {
  activeSegment,
  computedRows,
  totalEndAudited,
  totalBeginAudited,
  addRow,
  removeRow,
  updateRow,
} = useL7Detail(formData, detailRows)

const { exportTemplate, exportData, importData } = useL7ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const { adjudicationVsDetail } = useL7CrossSheet(formData.allResponses)

// ─── Segment options ─────────────────────────────────────────────────────────

const segmentOptions = L7_DETAIL_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Cross-sheet validation ──────────────────────────────────────────────────

const crossSheetMatch = computed(() => adjudicationVsDetail.value.isMatch)
const crossSheetDiff = computed(() => adjudicationVsDetail.value.diff)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof L7DetailRow, value: string | number) {
  updateRow(index, field, value)
}

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('L7-2')
      break
    case 'exportData':
      exportData('L7-2')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'L7-2')
          if (result) {
            await formData.loadData()
            _restoreRowsFromResponses()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

function handleAI(_section: string) {
  // AI辅助功能待集成
}

function handleReview() {
  openReviewDialog?.('L7-2-detail', '明细表')
}

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRowsFromResponses()
})

/**
 * 从 checklist_responses 恢复明细行数据
 * 行数据存储在 item_id="L7-L7-2-rows" 的 remark 中（JSON）
 */
function _restoreRowsFromResponses() {
  const rowsResp = formData.allResponses.value.get('L7-L7-2-rows')
  if (rowsResp?.remark) {
    try {
      const savedRows = JSON.parse(rowsResp.remark)
      if (Array.isArray(savedRows)) {
        const fullDataResp = formData.allResponses.value.get('L7-L7-2-full-data')
        let fullData: L7DetailRow[] = []
        if (fullDataResp?.remark) {
          try { fullData = JSON.parse(fullDataResp.remark) } catch { /* ignore */ }
        }
        if (fullData.length > 0) {
          detailRows.value = fullData
        } else {
          detailRows.value = savedRows.map((r: any) => ({
            key: r.key || `l7-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            itemName: r.itemName || '',
            beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0,
            ajeIncrease: 0, rjeIncrease: 0,
            endAjeIncrease: 0, endRjeDecrease: 0, endAjeDecrease: 0, endRjeIncrease: 0,
            endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0,
            nature: '', reason: '', maturityInfo: '',
          }))
        }
      }
    } catch { /* parse failed, keep empty */ }
  }
}
</script>

<style scoped>
.l7-tab-detail { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
:deep(.el-table) { font-size: 13px; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; flex-wrap: wrap; }
.l7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
