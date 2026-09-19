<!--
  K1TabStageCheck.vue — K1-7 三阶段划分检查表

  对齐致同源模板：
    一、审计目标
    二、审计程序 — (一) SICR 13项 / (二) 较低信用风险 3项 / (三) 已减值 6项
    三、审计说明 / 四、审计结论

  行式：每户一行 + 展开三区块检查矩阵；阶段含低风险豁免；联动 K1-2 / K1-8
-->
<template>
  <div class="k1-tab-stage-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>逐户填写三区块检查矩阵</div>
      <div class="guide-step"><span class="gs-no">2</span>核对建议阶段与企业划分</div>
      <div class="guide-step"><span class="gs-no">3</span>同步至 K1-2 / K1-8</div>
      <div class="guide-step"><span class="gs-no">4</span>形成审计说明与结论</div>
    </div>

    <div class="methodology-context">
      <p>K1-7 按 CAS 22 一般法将其他应收款划分为 ECL 三阶段。<strong>Stage 3</strong> 已减值 → 存续期 ECL；
        <strong>Stage 2</strong> 信用风险显著增加且不满足低风险豁免 → 存续期 ECL；
        <strong>Stage 1</strong> 其余（含 SICR 但满足低风险豁免）→ 12 个月 ECL。
        逾期 ≥30 日通常推定 SICR；逾期 ≥90 日通常推定违约（Stage 3）。</p>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <p class="ao-text">其他应收款、坏账准备以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。须追踪信用风险变化，按三阶段计提预期信用损失。</p>
    </el-alert>

    <div class="section-head">
      <h3 class="sheet-title">K1-7 三阶段划分检查表</h3>
      <div class="head-actions">
        <el-tag size="small" type="info">共 {{ rows.length }} 户</el-tag>
        <el-tag v-if="summary.inconsistentCount" size="small" type="danger">不一致 {{ summary.inconsistentCount }}</el-tag>
        <el-tag v-if="stageMigrationWarnings.length" size="small" type="warning">待说明迁移 {{ stageMigrationWarnings.length }}</el-tag>
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-7-stage')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview('K1-7-stage')">💬 复核</el-button>
      </div>
    </div>

    <div class="toolbar">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromK12">从 K1-2 带入</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromK110">从 K1-10 勾选逾期项</el-button>
      <el-button
        v-if="inconsistentRows.length && !isReadonly"
        size="small"
        type="danger"
        plain
        @click="pushInconsistencyToK14"
      >不一致推送 K1-4（{{ inconsistentRows.length }}）</el-button>
      <el-button size="small" @click="expandAll">全部展开</el-button>
      <el-button size="small" @click="collapseAll">全部折叠</el-button>
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
    </div>

    <div class="stage-summary-panel">
      <div class="summary-card stage-1-card">
        <div class="card-label">Stage 1（12个月ECL）</div>
        <div class="card-stat">
          <span class="stat-count">{{ summary.stage1Count }} 笔</span>
          <span class="stat-amount">{{ fmtAmt(summary.stage1Total) }}</span>
          <span class="stat-pct">{{ fmtPct(summary.stage1Total) }}</span>
        </div>
      </div>
      <div class="summary-card stage-2-card">
        <div class="card-label">Stage 2（存续期ECL）</div>
        <div class="card-stat">
          <span class="stat-count">{{ summary.stage2Count }} 笔</span>
          <span class="stat-amount">{{ fmtAmt(summary.stage2Total) }}</span>
          <span class="stat-pct">{{ fmtPct(summary.stage2Total) }}</span>
        </div>
      </div>
      <div class="summary-card stage-3-card">
        <div class="card-label">Stage 3（已减值）</div>
        <div class="card-stat">
          <span class="stat-count">{{ summary.stage3Count }} 笔</span>
          <span class="stat-amount">{{ fmtAmt(summary.stage3Total) }}</span>
          <span class="stat-pct">{{ fmtPct(summary.stage3Total) }}</span>
        </div>
      </div>
    </div>

    <el-empty v-if="rows.length === 0" description="暂无数据，点击「新增」或「从 K1-2 带入」" />

    <el-alert
      v-if="deeplinkHint"
      type="info"
      :closable="false"
      show-icon
      class="deeplink-bar"
    >
      <template #title>
        <span>{{ deeplinkHint }}</span>
        <el-button size="small" link type="primary" style="margin-left: 8px" @click="clearDeeplink">清除筛选</el-button>
      </template>
    </el-alert>

    <div v-if="rows.length" class="filter-bar">
      <el-input v-model="searchFilter" placeholder="搜索往来对象..." size="small" clearable class="search-input" />
      <span v-if="searchFilter.trim()" class="filter-hint">显示 {{ filteredRows.length }} / {{ rows.length }} 户</span>
    </div>

    <el-table
      v-if="rows.length"
      ref="tableRef"
      :data="filteredRows"
      border
      size="small"
      :max-height="520"
      class="stage-check-table"
      row-key="id"
      :expand-row-keys="Array.from(expandedRowIds)"
      :row-style="tableRowStyle"
      :row-class-name="tableRowClassName"
      @expand-change="handleExpandChange"
    >
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="expand-detail">
            <div v-if="triggerLabels(row).length" class="trigger-box">
              <strong>阶段触发因素：</strong>
              <ul>
                <li v-for="(t, i) in triggerLabels(row)" :key="i">{{ t }}</li>
              </ul>
              <el-button
                v-if="row.auditStageOverridden && !isReadonly"
                size="small" text type="primary"
                @click="resetAuditStageToSuggested(row.id); persistRows()"
              >清除覆写（恢复建议 Stage {{ row.suggestedStage }}）</el-button>
            </div>

            <div class="check-section">
              <div class="check-section-title">二、(一) 信用风险是否显著增加（13项，任一项「是」即显著增加）</div>
              <el-table :data="row.sectionOneChecks" border size="small" class="check-detail-table">
                <el-table-column label="#" width="42" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="需要考虑的信息" prop="label" min-width="320" />
                <el-table-column label="判断" width="140" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => onCheckChange(row.id, 'significantIncrease', $index, v)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                      <el-option value="不适用" label="不适用" />
                    </el-select>
                    <span v-else>{{ item.value }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="check-section">
              <div class="check-section-title">二、(二) 是否具有较低信用风险（3项须同时为「是」方可豁免 Stage2）</div>
              <el-table :data="row.sectionTwoChecks" border size="small" class="check-detail-table">
                <el-table-column label="#" width="42" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="条件（同时满足）" prop="label" min-width="320" />
                <el-table-column label="判断" width="140" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => onCheckChange(row.id, 'lowCreditRisk', $index, v)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                    </el-select>
                    <span v-else>{{ item.value }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="check-section">
              <div class="check-section-title">二、(三) 已发生信用减值的评估（6项，任一项「是」即 Stage3）</div>
              <el-table :data="row.sectionThreeChecks" border size="small" class="check-detail-table">
                <el-table-column label="#" width="42" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="可观察信息" prop="label" min-width="320" />
                <el-table-column label="判断" width="140" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => onCheckChange(row.id, 'creditImpairment', $index, v)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                    </el-select>
                    <span v-else>{{ item.value }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="往来对象" min-width="130" fixed>
        <template #default="{ row }">
          <span>{{ row.counterparty }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'endBalance', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="显著增加" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isSignificantIncrease ? 'warning' : 'info'" size="small">
            {{ row.isSignificantIncrease ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="低风险" width="72" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasLowCreditRisk ? 'success' : 'info'" size="small">
            {{ row.hasLowCreditRisk ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="已减值" width="72" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isImpaired ? 'danger' : 'info'" size="small">
            {{ row.isImpaired ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="企业阶段" width="100" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.companyStage" size="small"
            @change="(v: number) => handleUpdate(row.id, 'companyStage', v)">
            <el-option label="Stage 1" :value="1" />
            <el-option label="Stage 2" :value="2" />
            <el-option label="Stage 3" :value="3" />
          </el-select>
          <span v-else>Stage {{ row.companyStage }}</span>
        </template>
      </el-table-column>

      <el-table-column label="建议阶段" width="90" align="center">
        <template #default="{ row }">
          <span class="formula-cell" title="检查矩阵自动判定">Stage {{ row.suggestedStage }}</span>
        </template>
      </el-table-column>

      <el-table-column label="审计阶段" width="100" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.stage" size="small"
            @change="(v: number) => handleUpdate(row.id, 'stage', v)">
            <el-option label="Stage 1" :value="1" />
            <el-option label="Stage 2" :value="2" />
            <el-option label="Stage 3" :value="3" />
          </el-select>
          <el-tag v-else :type="stageTagType(row.stage)" size="small" effect="dark">Stage {{ row.stage }}</el-tag>
          <div v-if="row.auditStageOverridden" class="override-hint">已覆写</div>
        </template>
      </el-table-column>

      <el-table-column label="上期阶段" width="90" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.priorStage" size="small"
            @change="(v: number) => handleUpdate(row.id, 'priorStage', v)">
            <el-option label="Stage 1" :value="1" />
            <el-option label="Stage 2" :value="2" />
            <el-option label="Stage 3" :value="3" />
          </el-select>
          <span v-else>Stage {{ row.priorStage }}</span>
        </template>
      </el-table-column>

      <el-table-column label="变动说明" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.changeNote" size="small"
            :class="{ 'warn-field': row.priorStage !== row.stage && !row.changeNote }"
            placeholder="阶段变动原因"
            @change="(v: string) => handleUpdate(row.id, 'changeNote', v)" />
          <span v-else>{{ row.changeNote || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-alert v-if="stageMigrationWarnings.length" type="warning" :closable="false" show-icon class="migrate-warn">
      <template #title>
        {{ stageMigrationWarnings.length }} 户阶段发生迁移但未填写变动说明：
        {{ stageMigrationWarnings.map(r => r.counterparty).slice(0, 5).join('、') }}{{ stageMigrationWarnings.length > 5 ? '等' : '' }}
      </template>
    </el-alert>

    <div class="sync-actions">
      <el-button size="small" type="primary" :disabled="isReadonly || rows.length === 0" @click="handleSyncToDetail">
        同步审计阶段至 K1-2 →
      </el-button>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'K1-2 明细表')">跳转 K1-2</el-button>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'K1-8')">跳转 K1-8 测算</el-button>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="概述三阶段划分程序、与企业会计政策一致性、阶段迁移原因及与 K1-8 测算的衔接等"
        @change="persistMeta" />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="基于上述检查，其他应收款 ECL 三阶段划分是否恰当……"
        @change="persistMeta" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS 22 / 非打印）</summary>
      <ul>
        <li>组合1~N 在系统中对应逐户往来对象；展开行填写三区块检查矩阵</li>
        <li>判定优先级：已减值(Stage3) &gt; 显著增加且非低风险豁免(Stage2) &gt; 其余(Stage1)</li>
        <li>逾期 ≥30 日通常推定 SICR；逾期 ≥90 日通常推定违约（Stage3），须有合理依据方可推翻</li>
        <li>企业阶段 ≠ 审计阶段时可一键推送 K1-4 调整分录备忘（金额待 K1-8 测算补录）</li>
        <li>K1-10 长期未收回可自动勾选逾期相关检查项并升级阶段</li>
        <li>阶段迁移须填写变动说明；完成后同步至 K1-2 明细与 K1-8 测算分组</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import type { ElTable } from 'element-plus'
import {
  useK1StageCheck,
  getK1StageTriggerLabels,
  type K1StageRow,
} from '../../composables/useK1StageCheck'
import { injectK1Adjustments } from '../../composables/k1AdjustmentInject'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import {
  K1RowNavigationKey,
  applyK1IncomingFocus,
  buildK1DeeplinkHint,
} from '../../composables/useK1RowNavigation'

const K1_7_ADJ_SOURCE = 'k1-7-stage-inconsistency'

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

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const k1Nav = inject(K1RowNavigationKey, null)
const allResponsesRef = computed(() => props.allResponses)
const searchFilter = ref('')
const deeplinkHint = ref('')
const tableRef = ref<InstanceType<typeof ElTable>>()

const filteredRows = computed(() => {
  const keyword = searchFilter.value.trim().toLowerCase()
  if (!keyword) return rows.value
  return rows.value.filter((r) => String(r.counterparty ?? '').toLowerCase().includes(keyword))
})

const {
  rows, auditNote, auditConclusion, expandedRowIds, summary,
  stageMigrationWarnings, inconsistentRows,
  loadRows, addRow, removeRow, updateRow, updateCheckValue,
  resetAuditStageToSuggested, applyFromK12Detail, applyFromK110,
  buildInconsistencyAdjDrafts, syncStagesToDetail,
  expandAll, collapseAll, toggleExpand, serializeRows,
  ITEM_NOTE, ITEM_CONCLUSION,
} = useK1StageCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const { exportTemplate, exportData, importData } = useK1ImportExport({ wpId: toRef(props, 'wpId') })
const { generateAndConfirm } = useK1AiGenerate(toRef(props, 'wpId'))

onMounted(() => {
  loadRows()
  applyIncomingFocus()
})

function applyIncomingFocus(): void {
  applyK1IncomingFocus({
    sheet: 'K1-7',
    k1Nav,
    rows: rows.value,
    nameOf: (r) => (r as K1StageRow).counterparty,
    onResolved: (resolved, focus) => {
      searchFilter.value = resolved.counterparty
      deeplinkHint.value = buildK1DeeplinkHint(focus, resolved.counterparty)
      if (resolved.rowId) {
        k1Nav?.focusRow(resolved.rowId)
        scrollToRow(resolved.rowId)
      }
    },
  })
}

function scrollToRow(rowId: string): void {
  if (!rowId) return
  nextTick(() => {
    const root = tableRef.value?.$el as HTMLElement | undefined
    const rowEl = root?.querySelector(`tr[data-row-key="${rowId}"]`) as HTMLElement | null
    rowEl?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

function clearDeeplink(): void {
  searchFilter.value = ''
  deeplinkHint.value = ''
}

function tableRowClassName({ row }: { row: K1StageRow }): string {
  return k1Nav?.rowHighlightClass(row.id) ?? ''
}

const totalBalance = computed(() =>
  summary.value.stage1Total + summary.value.stage2Total + summary.value.stage3Total,
)

function triggerLabels(row: K1StageRow): string[] {
  return getK1StageTriggerLabels(row)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入往来对象名称', '新增阶段划分行', {
      confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '往来对象名称',
    })
    if (!value?.trim()) { ElMessage.warning('往来对象名称不能为空'); return }
    addRow(value.trim(), 0)
    persistRows()
    ElMessage.success(`已新增：${value.trim()}`)
  } catch { /* cancelled */ }
}

function handleRemoveRow(id: string) {
  removeRow(id)
  persistRows()
}

function handleUpdate(id: string, field: keyof K1StageRow, value: any) {
  updateRow(id, field, value)
  persistRows()
}

function onCheckChange(
  id: string,
  section: 'significantIncrease' | 'lowCreditRisk' | 'creditImpairment',
  index: number,
  value: string,
) {
  updateCheckValue(id, section, index, value as any)
  persistRows()
}

function handleExpandChange(row: K1StageRow, expandedRows: K1StageRow[]) {
  toggleExpand(row.id, expandedRows.some(r => r.id === row.id))
}

function persistRows() {
  const itemId = 'K1-7-stage-rows'
  const json = serializeRows()
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: json })
  emit('save', itemId, { remark: json })
}

function persistMeta() {
  props.allResponses.set(ITEM_NOTE, { item_id: ITEM_NOTE, conclusion: null, remark: auditNote.value })
  props.allResponses.set(ITEM_CONCLUSION, { item_id: ITEM_CONCLUSION, conclusion: null, remark: auditConclusion.value })
  emit('save', ITEM_NOTE, { remark: auditNote.value })
  emit('save', ITEM_CONCLUSION, { remark: auditConclusion.value })
}

function importFromK110() {
  const { added, upgraded, checked } = applyFromK110()
  persistRows()
  if (!checked) {
    ElMessage.warning('K1-10 长期未收回检查表暂无数据')
    return
  }
  ElMessage.success(`已从 K1-10 勾选 ${checked} 户逾期项：新增 ${added} 户，升级 ${upgraded} 户`)
}

function pushInconsistencyToK14(): void {
  if (props.isReadonly) return
  const drafts = buildInconsistencyAdjDrafts()
  if (!drafts.length) {
    ElMessage.info('无企业/审计阶段不一致项可推送')
    return
  }
  const added = injectK1Adjustments(props.allResponses, drafts, K1_7_ADJ_SOURCE)
  const payload = props.allResponses.get('K1-4-adj-entries')?.remark
  emit('save', 'K1-4-adj-entries', payload)
  ElMessage.success(`已向 K1-4 推送 ${added.length} 条阶段不一致备忘（金额待 K1-8 测算补录）`)
}

function importFromK12() {
  const { added, updated } = applyFromK12Detail()
  persistRows()
  if (added || updated) {
    ElMessage.success(`已从 K1-2 带入：新增 ${added} 户，更新 ${updated} 户`)
  } else {
    ElMessage.warning('K1-2 明细表暂无数据')
  }
}

function handleSyncToDetail() {
  const stageMap = syncStagesToDetail()
  const mapObj = Object.fromEntries(stageMap)
  const syncId = 'K1-7-stage-sync'
  props.allResponses.set(syncId, { item_id: syncId, conclusion: null, remark: JSON.stringify(mapObj) })
  emit('save', syncId, { remark: JSON.stringify(mapObj) })
  ElMessage.success(`已同步 ${stageMap.size} 户审计阶段至 K1-2`)
}

function handleExportTemplate() { exportTemplate('K1-7') }
function handleExportData() { exportData('K1-7') }
function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData('K1-7', file)
    if (result) loadRows()
  }
  input.click()
}

function tableRowStyle({ row }: { row: K1StageRow }): Record<string, string> {
  if (row.stage === 3) return { 'background-color': '#fde2e2' }
  if (row.stage === 2) return { 'background-color': '#fdf0e2' }
  return {}
}

function stageTagType(stage: 1 | 2 | 3): 'success' | 'warning' | 'danger' {
  if (stage === 3) return 'danger'
  if (stage === 2) return 'warning'
  return 'success'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(stageTotal: number): string {
  if (totalBalance.value === 0) return '0.00%'
  return ((stageTotal / totalBalance.value) * 100).toFixed(2) + '%'
}

async function handleAiGenerate(_section: string) {
  const content = await generateAndConfirm('overall-opinion', auditNote.value, {
    rowCount: rows.value.length,
    stage1: summary.value.stage1,
    stage2: summary.value.stage2,
    stage3: summary.value.stage3,
  }, 'AI 生成 K1-7 审计说明')
  if (content) {
    auditNote.value = content
    persistMeta()
  }
}
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k1-tab-stage-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }

.guide-banner {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px;
  background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%);
  border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px;
}
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff;
  font-size: 11px; font-weight: 600; flex-shrink: 0;
}

.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb; padding: 10px 14px; margin-bottom: 10px;
  font-size: 12px; line-height: 1.6;
}
.audit-objective { margin-bottom: 10px; }
.ao-title { font-weight: 600; }
.ao-text { margin: 4px 0 0; line-height: 1.6; font-size: 12px; }

.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }

.stage-summary-panel { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.summary-card { border-radius: 6px; padding: 10px 14px; border: 1px solid var(--el-border-color-lighter); }
.card-label { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.card-stat { display: flex; gap: 12px; align-items: baseline; font-size: 12px; }
.stat-count { font-weight: 600; }
.stat-amount { font-variant-numeric: tabular-nums; }
.stat-pct { color: var(--el-text-color-secondary); }
.stage-1-card { background: #f0fdf4; border-color: #bbf7d0; }
.stage-2-card { background: #fffbeb; border-color: #fde68a; }
.stage-3-card { background: #fef2f2; border-color: #fecaca; }

.stage-check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell, .amount-input { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.override-hint { font-size: 10px; color: var(--el-color-warning); }
.warn-field :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--el-color-warning) inset; }

.expand-detail { padding: 10px 12px 6px; background: #fafafa; }
.trigger-box { margin-bottom: 10px; font-size: 12px; }
.trigger-box ul { margin: 4px 0 0; padding-left: 18px; }
.check-section { margin-bottom: 12px; }
.check-section-title { font-weight: 600; font-size: 12px; margin-bottom: 6px; color: var(--el-color-primary); }
.check-detail-table { font-size: 12px; }

.migrate-warn { margin-top: 10px; }
.sync-actions { margin: 12px 0; display: flex; gap: 12px; align-items: center; }
.section-card { margin-bottom: 10px; }
.card-title { font-weight: 600; }

.compile-hint { margin-top: 10px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.deeplink-bar { margin: 8px 0; }
.filter-bar { display: flex; align-items: center; gap: 10px; margin: 8px 0 10px; }
.search-input { width: 220px; }
.filter-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.stage-check-table :deep(.k1-row-deeplink-hl > td) { background-color: #ecf5ff !important; animation: k1-row-flash 1.2s ease-in-out 0s 2; }
@keyframes k1-row-flash { 0%, 100% { background-color: #ecf5ff; } 50% { background-color: #d9ecff; } }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
