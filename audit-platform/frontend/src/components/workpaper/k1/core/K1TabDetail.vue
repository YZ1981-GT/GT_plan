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
        <el-popover placement="bottom-end" :width="280" trigger="click">
          <template #reference>
            <el-button size="small">⚙ 列设置</el-button>
          </template>
          <div class="col-prefs">
            <div class="col-prefs-presets">
              <el-button
                v-for="p in presetOptions"
                :key="p.name"
                size="small"
                :type="activePreset === p.name ? 'primary' : 'default'"
                @click="applyPreset(p.name)"
              >{{ p.label }}</el-button>
            </div>
            <el-divider style="margin: 8px 0" />
            <div class="col-prefs-list">
              <el-checkbox
                v-for="col in colsBySegment[activeSegment as 'basic' | 'aging' | 'impairment']"
                :key="col"
                :model-value="isColVisible(col)"
                @change="(v: boolean | string | number) => toggleCol(col, !!v)"
              >{{ colLabels[col] }}</el-checkbox>
            </div>
          </div>
        </el-popover>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-button v-if="!isReadonly && registryParties.length" size="small" type="primary" plain @click="handleBatchMatchB19">
          批量匹配 B19 清单
        </el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small" :loading="auxImporting">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :disabled="isReadonly || auxImporting" @click="handleImportFromAuxBalance">
                从余额表导入
              </el-dropdown-item>
              <el-dropdown-item divided @click="handleExportTemplate">导出模板</el-dropdown-item>
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

    <div class="filter-bar">
      <el-input
        v-model="searchFilter"
        placeholder="搜索往来对象..."
        size="small"
        clearable
        class="search-input"
      />
      <span v-if="searchFilter.trim()" class="filter-hint">
        显示 {{ filteredRows.length }} / {{ rows.length }} 笔
      </span>
    </div>

    <!-- 表格 -->
    <el-table
      ref="tableRef"
      :data="filteredRows"
      row-key="id"
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
      <el-table-column label="往来对象" min-width="168" fixed>
        <template #default="{ row }">
          <div class="counterparty-cell">
            <span>{{ row.counterparty }}</span>
            <el-dropdown
              v-if="row.counterparty.trim()"
              trigger="click"
              @command="(cmd: K1NavSheet) => navigateFromDetail(row, cmd)"
            >
              <el-button link type="primary" size="small" class="jump-btn">→</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="K1-5">K1-5 大额分析</el-dropdown-item>
                  <el-dropdown-item command="K1-7">K1-7 三阶段</el-dropdown-item>
                  <el-dropdown-item command="K1-10">K1-10 长期未收</el-dropdown-item>
                  <el-dropdown-item v-if="isRelatedPartyRow(row)" command="K1-11">K1-11 关联方</el-dropdown-item>
                  <el-dropdown-item command="K1-12">K1-12 凭证检查</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>

      <!-- ═══ 基础区段列 ═══ -->
      <template v-if="activeSegment === 'basic'">
        <el-table-column v-if="isColVisible('nature')" label="性质" min-width="100">
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
        <el-table-column v-if="isColVisible('relatedParty')" label="关联关系" min-width="160">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.relatedParty" size="small" filterable
              @change="(v: string) => updateField(row.id, 'relatedParty', v)">
              <el-option v-for="opt in relatedPartyOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.relatedParty || '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('beginBalance')" label="期初余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginBalance" size="small"
              :controls="false" class="amount-input"
              @change="(v: number) => updateField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('endBalance')" label="期末余额" min-width="120" align="right">
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
        <template v-if="isColVisible('agingBands')">
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
        </template>
        <el-table-column v-if="isColVisible('agingTotal')" label="账龄合计" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="账龄合计=各账龄段之和">
              {{ fmtAmt(row.agingTotal) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('agingTotal')" label="勾稽" width="60" align="center">
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
        <el-table-column v-if="isColVisible('stage')" label="阶段" min-width="80" align="center">
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
        <el-table-column v-if="isColVisible('provision')" label="坏账准备" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.badDebtProvision" size="small"
              :controls="false" class="amount-input"
              @change="(v: number) => updateField(row.id, 'badDebtProvision', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.badDebtProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('netValue')" label="净值" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=期末余额-坏账准备">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('voucherNo')" label="凭证号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="凭证号"
              @change="(v: string) => updateField(row.id, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('conclusion')" label="结论" min-width="100">
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
        <el-table-column v-if="isColVisible('remark')" label="备注" min-width="140">
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

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <el-button v-if="!isReadonly" size="small" type="primary" link @click="handleAiGenerate('K1-2-detail')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="明细表审计说明..." :disabled="isReadonly" @blur="saveAuditNote" />
    </el-card>

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
import { ref, computed, inject, toRef, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, WarningFilled, CircleCheckFilled } from '@element-plus/icons-vue'
import type { ElTable } from 'element-plus'
import { useK1Detail, type K1DetailRow } from '../../composables/useK1Detail'
import { useK1DetailColumnPrefs } from '../../composables/useK1DetailColumnPrefs'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import {
  K1_DETAIL_RELATED_PARTY_OPTIONS,
  batchMatchK1DetailRelatedParty,
  isK1RelatedPartyMarked,
  matchK1RelatedPartyFromRegistry,
} from '../../composables/useK1RelatedParty'
import {
  K1RowNavigationKey,
  resolveK1DetailFocusRow,
  buildK1DeeplinkHint,
  type K1NavSheet,
} from '../../composables/useK1RowNavigation'
import { manualImportK1DetailFromAux } from '../../composables/useK1DetailAutoSeed'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** B19 关联方清单，用于新增行时自动建议关联关系 */
  relatedParties?: string[]
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const k1Nav = inject(K1RowNavigationKey, null)
// 宿主（GtK1OtherReceivables）provide 的 reload：手动「从余额表导入」成功后重载 allResponses，
// 让 K1-1/披露级联读到最新持久化行（Requirement 4.6）。
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

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

const { generateAndConfirm } = useK1AiGenerate(toRef(props, 'wpId'))
const auditNote = ref('')

watch(() => props.allResponses.get('K1-2-audit-note')?.remark, (v) => {
  auditNote.value = v || ''
}, { immediate: true })

const relatedPartyOptions = K1_DETAIL_RELATED_PARTY_OPTIONS
const registryParties = computed(() => props.relatedParties ?? [])

const activeSegment = ref<'basic' | 'aging' | 'impairment'>('basic')

const {
  activePreset,
  presetOptions,
  colLabels,
  colsBySegment,
  isColVisible,
  toggleCol,
  applyPreset,
} = useK1DetailColumnPrefs()
const searchFilter = ref('')
const deeplinkHint = ref('')
const tableRef = ref<InstanceType<typeof ElTable>>()

const filteredRows = computed(() => {
  const keyword = searchFilter.value.trim().toLowerCase()
  if (!keyword) return rows.value
  return rows.value.filter((r) =>
    String(r.counterparty ?? '').toLowerCase().includes(keyword),
  )
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadRows()
  applyIncomingFocus()
})

function applyIncomingFocus(): void {
  const focus = k1Nav?.consumeFocus('K1-2')
  if (!focus) return
  const resolved = resolveK1DetailFocusRow(rows.value, focus)
  if (!resolved) return
  searchFilter.value = resolved.counterparty
  deeplinkHint.value = buildK1DeeplinkHint(focus, resolved.counterparty)
  activeSegment.value = 'basic'
  if (resolved.rowId) {
    k1Nav?.focusRow(resolved.rowId)
    scrollToRow(resolved.rowId)
  }
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

function isRelatedPartyRow(row: K1DetailRow): boolean {
  return isK1RelatedPartyMarked(row.relatedParty)
}

function navigateFromDetail(row: K1DetailRow, sheet: K1NavSheet) {
  const name = row.counterparty.trim()
  if (!name) {
    ElMessage.warning('往来对象名称为空')
    return
  }
  if (k1Nav) {
    k1Nav.navigateToRow({
      sheet,
      rowId: row.id,
      counterparty: name,
      sourceSheet: 'K1-2',
      section: sheet === 'K1-12' ? 'occurrence' : undefined,
    })
    return
  }
  emit('navigate-sheet', sheet === 'K1-2' ? 'K1-2 明细表' : sheet)
}

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
    const name = value.trim()
    const row = addRow(name)
    const suggested = matchK1RelatedPartyFromRegistry(name, registryParties.value)
    if (suggested !== '否') {
      updateRow(row.id, 'relatedParty', suggested)
    }
    persistRows()
    ElMessage.success(`已新增：${name}${suggested !== '否' ? `（已匹配 B19 清单 → ${suggested}）` : ''}`)
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

function handleBatchMatchB19() {
  if (!registryParties.value.length) {
    ElMessage.warning('B19 关联方清单为空，请先在 B19-1 维护')
    return
  }
  const count = batchMatchK1DetailRelatedParty(rows.value, registryParties.value)
  if (!count) {
    ElMessage.info('未发现可匹配的未标记关联方行')
    return
  }
  persistRows()
  ElMessage.success(`已批量匹配 ${count} 笔关联方（关联关系 → 其他关联方）`)
}

function handleExportTemplate() { exportTemplate('K1-2') }
function handleExportData() { exportData('K1-2') }

// ─── 从余额表导入（手动入口，区别于宿主 onMounted 的 AutoSeed） ─────────────────
// AutoSeed 仅空表触发一次；本手动入口可在非空表上按 merge 语义追加（Requirement 4.5）。
// loading 期间禁止重复提交（Requirement 4.3）；0 行按 reason 码给可辨别提示（Requirement 4.4）。
const auxImporting = ref(false)

async function handleImportFromAuxBalance() {
  if (props.isReadonly || auxImporting.value || !props.wpId) return
  auxImporting.value = true
  try {
    const result = await manualImportK1DetailFromAux({
      wpId: props.wpId,
      // 宿主 reload 重填 allResponses（级联 K1-1/披露）；本 Tab 的 rows 是手动 loadRows() 派生、
      // 无 allResponses watcher，故 reload 后必须再 loadRows() 一次本 Tab 才刷新。
      reload: async () => {
        await (reloadWorkpaperData?.() ?? Promise.resolve())
        loadRows()
      },
    })
    const { level, text } = result.prompt
    ElMessage[level]({ message: text })
  } finally {
    auxImporting.value = false
  }
}

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
  const parts: string[] = []
  if (isOver3Years(row)) parts.push('over-3-years-row')
  const hl = k1Nav?.rowHighlightClass(row.id)
  if (hl) parts.push(hl)
  return parts.join(' ')
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────

async function handleAiGenerate(_section: string) {
  const content = await generateAndConfirm('overall-opinion', auditNote.value, {
    rowCount: stats.value.totalCount,
    endBalanceTotal: stats.value.totalEndBalance,
    over3YearRatio: stats.value.over3YearRatio,
  }, 'AI 生成 K1-2 审计说明')
  if (content) {
    auditNote.value = content
    saveAuditNote()
  }
}
function saveAuditNote() {
  const itemId = 'K1-2-audit-note'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: auditNote.value })
  emit('save', itemId, { remark: auditNote.value })
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
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
  margin-top: -1px;
}
.detail-table :deep(.k1-row-deeplink-hl > td) {
  background-color: #ecf5ff !important;
  animation: k1-row-flash 1.2s ease-in-out 0s 2;
}
@keyframes k1-row-flash {
  0%, 100% { background-color: #ecf5ff; }
  50% { background-color: #d9ecff; }
}
.deeplink-bar { margin: 8px 0; }
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0 10px;
}
.search-input { width: 220px; }
.filter-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.counterparty-cell { display: flex; align-items: center; gap: 4px; }
.jump-btn { flex-shrink: 0; padding: 0 2px; font-weight: 600; }
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
.col-prefs-presets { display: flex; flex-wrap: wrap; gap: 6px; }
.col-prefs-list { display: flex; flex-direction: column; gap: 4px; max-height: 240px; overflow: auto; }
</style>
