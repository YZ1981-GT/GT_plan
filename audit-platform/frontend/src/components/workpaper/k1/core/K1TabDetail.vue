<!--
  K1TabDetail.vue — K1-2 明细表（36列 → 3区段Tab）

  3区段Tab切换：基础(序号/往来对象/性质/关联关系/期初余额/期末余额)
              / 账龄(1年内/1-2年/2-3年/3-4年/4-5年/5年以上/账龄合计)
              / 减值(阶段/坏账准备/净值/凭证号/结论/备注)
  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  公式列：账龄合计(=各区间之和)、净值(=期末-坏账准备)
  动态行：ElMessageBox.prompt输入往来对象名称再创建
  3年以上高亮：aging3to4 + aging4to5 + aging5plus > 0 → 橙色背景
  底部统计：往来笔数 / 期末合计 / 3年以上占比

  Spec: .kiro/specs/k1-other-receivables/ Task 4.3
  Requirements: 3.1-3.6
-->
<template>
  <div class="k1-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K1-2明细表按往来对象逐笔列示其他应收款余额及账龄分布。账龄合计应与期末余额一致；3年以上账龄需重点关注回收性及减值充分性。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-2 其他应收款明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-2-detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleReview('K1-2-detail')">💬 复核</el-button>
      </div>
    </div>

    <!-- 3区段Tab -->
    <el-tabs v-model="activeSegment" type="border-card" class="segment-tabs">
      <el-tab-pane label="基础区段" name="basic" />
      <el-tab-pane label="账龄区段" name="aging" />
      <el-tab-pane label="减值区段" name="impairment" />
    </el-tabs>

    <!-- 表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      :max-height="520"
      :row-class-name="rowClassName"
      class="detail-table"
    >
      <!-- 序号 + 往来对象（固定列，所有区段可见） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="往来对象" min-width="140" fixed>
        <template #default="{ row }">
          <span>{{ row.counterparty }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 基础区段列 ═══ -->
      <template v-if="activeSegment === 'basic'">
        <el-table-column label="性质" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.nature" size="small" placeholder="选择"
              @change="(v: string) => updateField(row.id, 'nature', v)">
              <el-option label="经营性" value="经营性" />
              <el-option label="往来款" value="往来款" />
              <el-option label="保证金" value="保证金" />
              <el-option label="押金" value="押金" />
              <el-option label="备用金" value="备用金" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联关系" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.relatedParty" size="small"
              @change="(v: string) => updateField(row.id, 'relatedParty', v)">
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
            </el-select>
            <span v-else>{{ row.relatedParty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginBalance" size="small"
              :controls="false" class="amount-input"
              @change="(v: number) => updateField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small"
              :controls="false" class="amount-input"
              @change="(v: number) => updateField(row.id, 'endBalance', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 账龄区段列（动态，基于 bands from useAgingConfig） ═══ -->
      <template v-if="activeSegment === 'aging'">
        <el-table-column
          v-for="band in bands"
          :key="band.key"
          :label="band.label"
          min-width="110"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.agingAudited[band.key] ?? 0"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => updateField(row.id, `agingAudited.${band.key}`, v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.agingAudited[band.key]) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄合计" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="账龄合计=各账龄段之和">
              {{ fmtAmt(row.agingTotal) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="勾稽" width="60" align="center">
          <template #default="{ row }">
            <el-icon v-if="Math.abs(row.agingTotal - row.endBalance) > 0.01" color="var(--el-color-danger)">
              <WarningFilled />
            </el-icon>
            <el-icon v-else color="var(--el-color-success)">
              <CircleCheckFilled />
            </el-icon>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 减值区段列 ═══ -->
      <template v-if="activeSegment === 'impairment'">
        <el-table-column label="阶段" min-width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.stage" size="small"
              @change="(v: number) => updateField(row.id, 'stage', v)">
              <el-option :label="'Stage 1'" :value="1" />
              <el-option :label="'Stage 2'" :value="2" />
              <el-option :label="'Stage 3'" :value="3" />
            </el-select>
            <el-tag v-else :type="row.stage === 3 ? 'danger' : row.stage === 2 ? 'warning' : 'success'" size="small">
              {{ row.stage }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="坏账准备" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.badDebtProvision" size="small"
              :controls="false" class="amount-input"
              @change="(v: number) => updateField(row.id, 'badDebtProvision', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.badDebtProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净值" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=期末余额-坏账准备">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="凭证号"
              @change="(v: string) => updateField(row.id, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.conclusion" size="small" placeholder="选择"
              @change="(v: string) => updateField(row.id, 'conclusion', v)">
              <el-option label="合规" value="合规" />
              <el-option label="存疑" value="存疑" />
              <el-option label="异常" value="异常" />
            </el-select>
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注"
              @change="(v: string) => updateField(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 账龄勾稽警告 -->
    <div v-if="agingMismatches.length > 0" class="aging-warnings">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          <span>账龄合计与期末余额不一致 ({{ agingMismatches.length }}笔)</span>
        </template>
        <ul class="mismatch-list">
          <li v-for="(msg, idx) in agingMismatches.slice(0, 5)" :key="idx">{{ msg }}</li>
          <li v-if="agingMismatches.length > 5">...还有{{ agingMismatches.length - 5 }}笔</li>
        </ul>
      </el-alert>
    </div>

    <!-- 底部统计 -->
    <div class="stats-bar">
      <el-tag type="info" effect="plain">往来笔数: {{ stats.totalCount }}</el-tag>
      <el-tag type="primary" effect="plain">期末合计: {{ fmtAmt(stats.totalEndBalance) }}</el-tag>
      <el-tag :type="stats.over3YearRatio && stats.over3YearRatio > 0.3 ? 'danger' : 'warning'" effect="plain">
        3年以上占比: {{ stats.over3YearRatio != null ? (stats.over3YearRatio * 100).toFixed(1) + '%' : '-' }}
      </el-tag>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>36列拆为3区段Tab切换，行数据同步</li>
        <li>账龄区间基于项目级配置动态生成（支持3年段/5年段/自定义）</li>
        <li>账龄合计=各区间之和，须与期末余额一致（勾稽列显示✓或✗）</li>
        <li>3年以上(含3-4年/4-5年/5年以上/3年以上)行显示橙色背景</li>
        <li>减值阶段：Stage1正常/Stage2显著增加/Stage3已减值</li>
        <li>净值=期末余额-坏账准备（公式自动计算）</li>
        <li>"新增"按钮弹出对话框输入往来对象名称后创建行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabDetail.vue — K1-2 明细表
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.3
 * Requirements: 3.1-3.6
 * 36列3区段Tab + 账龄 + 动态行 + 统计 + 导入导出 + 3年以上高亮
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, WarningFilled, CircleCheckFilled } from '@element-plus/icons-vue'
import { useK1Detail, type K1DetailRow } from '../../../composables/useK1Detail'
import { useK1ImportExport } from '../../../composables/useK1ImportExport'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  stats,
  agingMismatches,
  bands,
  loadRows,
  addRow,
  removeRow,
  updateRow,
  isOver3Years,
  serializeRows,
} = useK1Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const {
  exportTemplate,
  exportData,
  importData,
} = useK1ImportExport({ wpId: toRef(props, 'wpId') })

// ─── 区段状态 ────────────────────────────────────────────────────────────────

const activeSegment = ref<'basic' | 'aging' | 'impairment'>('basic')

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadRows()
})

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入往来对象名称',
      '新增明细行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '往来对象名称' }
    )
    if (!value || !value.trim()) {
      ElMessage.warning('往来对象名称不能为空')
      return
    }
    addRow(value.trim())
    persistRows()
    ElMessage.success(`已新增：${value.trim()}`)
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(id: string) {
  removeRow(id)
  persistRows()
}

function updateField(id: string, field: keyof K1DetailRow, value: any) {
  updateRow(id, field, value)
  persistRows()
}

/** 持久化行数据到 allResponses + emit save */
function persistRows() {
  const itemId = 'K1-2-detail-rows'
  const payload = { item_id: itemId, conclusion: null, remark: serializeRows() }
  props.allResponses.set(itemId, payload)
  emit('save', itemId, { remark: serializeRows() })
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate('K1-2') }
function handleExportData() { exportData('K1-2') }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData('K1-2', file)
    if (result) {
      // 重新加载行数据
      loadRows()
    }
  }
  input.click()
}

// ─── 行样式（3年以上高亮） ────────────────────────────────────────────────────

function rowClassName({ row }: { row: K1DetailRow }): string {
  return isOver3Years(row) ? 'over-3-years-row' : ''
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────

function handleAiGenerate(section: string) {
  console.log('[K1-2] AI generate:', section)
}
function handleReview(id: string) { openReviewDialog(id) }

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k1-tab-detail {
  padding: 16px;
  font-size: 13px;
}

/* 方法论上下文（琥珀色） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

/* 标题栏 */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 区段Tab */
.segment-tabs {
  margin-bottom: 0;
}
.segment-tabs :deep(.el-tabs__content) {
  display: none;
}

/* 表格 */
.detail-table {
  font-size: 13px;
  margin-top: -1px;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}
.amount-input {
  width: 100%;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 3年以上高亮（橙色背景） */
.detail-table :deep(.over-3-years-row) {
  background-color: #fff7ed !important;
}
.detail-table :deep(.over-3-years-row td) {
  background-color: #fff7ed !important;
}

/* 账龄勾稽警告 */
.aging-warnings {
  margin-top: 12px;
}
.mismatch-list {
  margin: 4px 0 0;
  padding-left: 16px;
  font-size: 12px;
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 0;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
