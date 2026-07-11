<template>
  <div class="l6-tab-detail">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L6-2 专项应付款明细表</h3>
        <el-tag type="warning" size="small">33列·区段Tab</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增专项
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
        <strong>审计目标：</strong>核实各专项应付款的来源批文、用途与资金变动的真实完整，明细合计与审定表 L6-1 勾稽一致，核查专款专用。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>33列按3区段Tab管理：</strong>
        项目信息（序号/项目/来源/批文/用途/期初/拨入/结转/返还/期末） →
        资金变动（AJE+RJE各4列） → 用途核查（审定5列+索引+状态+备注）。
        负债类：期末=期初+本期拨入(贷方)−本期结转(借方)−本期返还(借方)。
      </div>
    </div>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ L6-1交叉验证指示器 ═══ -->
    <div v-if="!crossSheet.isMatch.value" class="cross-validation-warning">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          明细合计({{ fmtAmount(crossSheet.detailTotal.value) }}) ≠ 审定表合计({{ fmtAmount(crossSheet.adjTotal.value) }})，
          差额：<strong>{{ fmtAmount(crossSheet.diff.value) }}</strong>
        </template>
      </el-alert>
    </div>

    <!-- ═══ 明细表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="project" label="专项项目" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.project" size="small" @change="(val: string) => handleUpdate($index, 'project', val)" />
          <span v-else>{{ row.project || '—' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 区段1: 项目信息 ═══ -->
      <template v-if="activeSegment === 'project-info'">
        <el-table-column label="拨款来源" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.fundSource" size="small" @change="(val: string) => handleUpdate($index, 'fundSource', val)" />
            <span v-else>{{ row.fundSource || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="批文号" min-width="130">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.approvalNo" size="small" @change="(val: string) => handleUpdate($index, 'approvalNo', val)" />
            <span v-else>{{ row.approvalNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="用途" min-width="160">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.purpose" size="small" @change="(val: string) => handleUpdate($index, 'purpose', val)" />
            <span v-else>{{ row.purpose || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginBalance', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期拨入(贷方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditIn" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'creditIn', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.creditIn) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期结转(借方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.carryForward" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'carryForward', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.carryForward) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期返还(借方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.refund" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'refund', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.refund) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初+本期拨入(贷方)−本期结转(借方)−本期返还(借方)，负债类" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'negative-warning': row.endBalance < 0 }">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 资金变动（AJE+RJE） ═══ -->
      <template v-if="activeSegment === 'fund-movement'">
        <el-table-column label="AJE调整" align="center">
          <el-table-column label="期初AJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.ajeBegin" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'ajeBegin', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.ajeBegin) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="拨入AJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.ajeCredit" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'ajeCredit', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.ajeCredit) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结转AJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.ajeCarryFwd" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'ajeCarryFwd', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.ajeCarryFwd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="返还AJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.ajeRefund" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'ajeRefund', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.ajeRefund) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="RJE调整" align="center">
          <el-table-column label="期初RJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.rjeBegin" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rjeBegin', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.rjeBegin) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="拨入RJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.rjeCredit" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rjeCredit', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.rjeCredit) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结转RJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.rjeCarryFwd" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rjeCarryFwd', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.rjeCarryFwd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="返还RJE" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" :model-value="row.rjeRefund" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rjeRefund', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.rjeRefund) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </template>

      <!-- ═══ 区段3: 用途核查 ═══ -->
      <template v-if="activeSegment === 'usage-check'">
        <el-table-column label="审定期初" min-width="120" align="right">
          <template #header>
            <el-tooltip content="审定期初=期初+期初AJE+期初RJE" placement="top">
              <span class="formula-col-header">审定期初</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedBegin" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'auditedBegin', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.auditedBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定拨入" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedCredit" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'auditedCredit', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.auditedCredit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定结转" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedCarryFwd" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'auditedCarryFwd', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.auditedCarryFwd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定返还" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedRefund" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'auditedRefund', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.auditedRefund) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定期末" min-width="130" align="right">
          <template #header>
            <el-tooltip content="审定期初+审定拨入−审定结转−审定返还，负债类" placement="top">
              <span class="formula-col-header">审定期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'negative-warning': row.auditedEnd < 0 }">{{ fmtAmount(row.auditedEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="文件依据" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.docRef" size="small" @change="(val: string) => handleUpdate($index, 'docRef', val)" />
            <span v-else>{{ row.docRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(val: string) => handleUpdate($index, 'indexRef', val)" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完成状态" min-width="120">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.completionStatus" size="small" style="width:100%" @change="(val: string) => handleUpdate($index, 'completionStatus', val)">
              <el-option label="未开始" value="未开始" />
              <el-option label="进行中" value="进行中" />
              <el-option label="已完成" value="已完成" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="statusTagType(row.completionStatus)" size="small">{{ row.completionStatus || '未开始' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="180">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(val: string) => handleUpdate($index, 'remark', val)" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-bar">
      <span>期末余额合计：<strong>{{ fmtAmount(totalEndBalance) }}</strong></span>
      <span>期初余额合计：<strong>{{ fmtAmount(totalBeginBalance) }}</strong></span>
      <span>本期拨入合计：<strong>{{ fmtAmount(totalCreditIn) }}</strong></span>
      <span>本期结转合计：<strong>{{ fmtAmount(totalCarryForward) }}</strong></span>
      <span>本期返还合计：<strong>{{ fmtAmount(totalRefund) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 个专项项目</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>33列按3区段Tab拆分，行跨区段同步</li>
        <li>负债类：期末=期初+本期拨入(贷方)−本期结转(借方)−本期返还(借方)</li>
        <li>各行按专项项目列示（科研经费/基建项目/扶贫资金等），需与拨款批文一一对应</li>
        <li>明细表合计应与审定表L6-1核对一致</li>
        <li>用途核查区段需关注专款专用情况，异常用途在L6-4检查表中详查</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L6TabDetail — L6-2 专项应付款明细表（33列·区段Tab）
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 4.3
 * Requirements: 3.1-3.5
 *
 * 33列宽表拆分为3区段Tab切换（项目信息/资金变动/用途核查，行同步）
 * 动态行新增（ElMessageBox.prompt输入专项项目名称）+ 导入导出三级
 * 负债类公式：期末=期初+本期拨入-本期结转-本期返还（auto-computed, readonly）
 * 公式列虚线下划线 + cursor:help + tooltip
 * L6-1交叉验证: show diff indicator
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL6FormData } from '../../composables/useL6FormData'
import { useL6Detail, type L6DetailRow, L6_DETAIL_SEGMENTS } from '../../composables/useL6Detail'
import { useL6ImportExport } from '../../composables/useL6ImportExport'
import { useL6CrossSheet } from '../../composables/useL6CrossSheet'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useL6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetPrefix: 'L6-L6-2',
})

const detailRows = ref<L6DetailRow[]>([])

const {
  activeSegment,
  computedRows,
  totalEndBalance,
  totalBeginBalance,
  totalCreditIn,
  totalCarryForward,
  totalRefund,
  addRow,
  removeRow,
  updateRow,
} = useL6Detail(formData, detailRows)

const importExport = useL6ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const crossSheet = useL6CrossSheet(formData.responses)

const segmentOptions = L6_DETAIL_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof L6DetailRow, value: string | number) {
  updateRow(index, field, value)
}

/** 导入导出三级命令处理 */
function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate('L6-2')
      break
    case 'exportData':
      importExport.exportData('L6-2')
      break
    case 'importData':
      triggerFileUpload()
      break
  }
}

/** 触发文件上传对话框 */
function triggerFileUpload() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importExport.importData(file, 'L6-2')
    if (result) {
      // 重新加载数据
      await formData.loadData()
    }
  }
  input.click()
}

function handleAI(_section: string) {
  // AI辅助 — 由上层集成
}

function handleReview() {
  openReviewDialog?.()
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case '已完成': return 'success'
    case '进行中': return 'warning'
    case '不适用': return 'info'
    default: return ''
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 从已保存的 responses 还原明细行
  restoreRowsFromResponses()
})

/** 从 checklist_responses 还原行数据 */
function restoreRowsFromResponses() {
  const rowsResp = formData.responses.value.get('L6-L6-2-rows')
  if (rowsResp?.remark) {
    try {
      const savedRows = JSON.parse(rowsResp.remark)
      if (Array.isArray(savedRows) && savedRows.length > 0) {
        detailRows.value = savedRows.map((r: any, i: number) => ({
          key: r.key || `l6-detail-restored-${i}`,
          seq: i + 1,
          project: r.project || '',
          fundSource: r.fundSource || '',
          approvalNo: r.approvalNo || '',
          purpose: r.purpose || '',
          beginBalance: Number(r.beginBalance) || 0,
          creditIn: Number(r.creditIn) || 0,
          carryForward: Number(r.carryForward) || 0,
          refund: Number(r.refund) || 0,
          endBalance: Number(r.endBalance) || 0,
          ajeBegin: Number(r.ajeBegin) || 0,
          ajeCredit: Number(r.ajeCredit) || 0,
          ajeCarryFwd: Number(r.ajeCarryFwd) || 0,
          ajeRefund: Number(r.ajeRefund) || 0,
          rjeBegin: Number(r.rjeBegin) || 0,
          rjeCredit: Number(r.rjeCredit) || 0,
          rjeCarryFwd: Number(r.rjeCarryFwd) || 0,
          rjeRefund: Number(r.rjeRefund) || 0,
          auditedBegin: Number(r.auditedBegin) || 0,
          auditedCredit: Number(r.auditedCredit) || 0,
          auditedCarryFwd: Number(r.auditedCarryFwd) || 0,
          auditedRefund: Number(r.auditedRefund) || 0,
          auditedEnd: Number(r.auditedEnd) || 0,
          docRef: r.docRef || '',
          indexRef: r.indexRef || '',
          completionStatus: r.completionStatus || '',
          remark: r.remark || '',
        }))
      }
    } catch {
      // JSON解析失败，保持空行
    }
  }
}
</script>

<style scoped>
.l6-tab-detail { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.segment-switcher { margin-bottom: 12px; }
.cross-validation-warning { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value.negative-warning { color: #f56c6c; }
:deep(.el-table) { font-size: 13px; }
.summary-bar { display: flex; gap: 20px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; flex-wrap: wrap; }
.l6-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
