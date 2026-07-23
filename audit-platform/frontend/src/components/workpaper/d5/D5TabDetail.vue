<template>
<div class="d5-detail">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示应收款项融资（科目1124）明细，按"应收票据"与"应收账款"两类归集，采用出售（背书/贴现）模式管理的票据/账款以公允价值计量（FVOCI）。</p>
        <p>2. 灰色底纹列为自动计算列（期初审定/期末余额/期末未审/期末审定），不可手工编辑。</p>
        <p>3. 支持从 D1-6（出售模式票据）、D2-13（出售模式账款）及余额表一键导入明细。</p>
        <p>4. 各类别自动生成小计行，全表生成合计行，请与 D5-1 审定表按类别聚合核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实应收款项融资各明细项目期末余额的存在与准确，确认按出售模式分类计量的恰当性，为审定表按类别聚合提供依据。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加明细行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromD1">从D1导入(出售模式票据)</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromD2">从D2导入(出售模式账款)</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="doImportPostRealized" type="warning" plain>取期后兑现</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭引擎</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx"
                  :auto-upload="false"
                  :disabled="isReadonly || importing"
                  @change="(f: any) => onImportFile(f.raw || f)"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-popover trigger="click" :width="260" placement="bottom-end">
          <template #reference>
            <el-button size="small" circle><el-icon><Setting /></el-icon></el-button>
          </template>
          <div class="col-prefs-popover">
            <div class="col-prefs-header">
              <span>列显示设置</span>
              <el-button size="small" text type="primary" @click="resetDefaults">重置默认</el-button>
            </div>
            <div v-for="group in columnGroups" :key="group.label" class="col-prefs-group">
              <div class="col-prefs-group-label">{{ group.label }}</div>
              <div v-for="key in group.keys" :key="key" class="col-prefs-item">
                <el-checkbox
                  :model-value="isColVisible(key)"
                  :disabled="group.alwaysShow"
                  size="small"
                  @change="toggleCol(key)"
                >{{ getColLabel(key) }}</el-checkbox>
              </div>
            </div>
          </div>
        </el-popover>
        <span class="chip-wrap"><GtIndexChip value="wp:D1-6" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:D2-13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 勾稽校验提示 -->
    <!-- 抽凭引擎 Dialog -->
    <GtVoucherSamplingEngine
      v-if="showSamplingDialog"
      account-code="1124"
      phase="final"
      :workpaper-id="props.wpId"
      :project-id="props.projectId"
      :year="samplingYear"
      @filled="onSampleFilled"
      @close="showSamplingDialog = false"
    />

    <el-alert
      v-if="crossCheckInfo"
      :type="crossCheckInfo.type"
      :title="crossCheckInfo.message"
      :closable="false"
      show-icon
      style="margin-bottom: 8px"
    />

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
      </el-alert>
      <el-button size="small" @click="toggleBrowseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>
    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="browseRows"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="36"
      :header-height="40"
      :row-event-handlers="rowEventHandlers"
      fixed
      class="virtual-table"
    />

    <!-- 明细表主体 -->
    <div v-if="!useVirtualScroll || !browseMode">
    <el-table
      :data="displayRows"
      size="small"
      border
      stripe
      :max-height="rows.length > 30 ? 600 : undefined"
      style="width: 100%"
    >
      <!-- A: 类别 (固定) -->
      <el-table-column label="类别" width="120" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.category }}</span>
          </template>
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="选择类别"
            @change="(val: string) => updateCell(row.rowId, 'category', val)"
          >
            <el-option label="应收票据" value="应收票据" />
            <el-option label="应收账款" value="应收账款" />
          </el-select>
          <span v-else>
            {{ row.category }}
            <GtIndexChip v-if="row.category === '应收票据'" value="wp:D1-6" :context-project-id="projectId" />
            <GtIndexChip v-if="row.category === '应收账款'" value="wp:D2-13" :context-project-id="projectId" />
          </span>
        </template>
      </el-table-column>

      <!-- B: 明细项目 (固定) -->
      <el-table-column label="明细项目" width="140" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.itemName || '' }}</span>
          </template>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.itemName"
            size="small"
            @change="(val: string) => updateCell(row.rowId, 'itemName', val)"
          />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>

      <!-- C: 期初未审 -->
      <el-table-column v-if="isColVisible('priorUnadjusted')" label="期初未审" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorUnadjusted"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'priorUnadjusted', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- D: 期初AJE -->
      <el-table-column v-if="isColVisible('priorAje')" label="期初AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'priorAje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <!-- E: 期初RJE -->
      <el-table-column v-if="isColVisible('priorRje')" label="期初RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'priorRje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorRje) }}</span>
        </template>
      </el-table-column>

      <!-- F: 期初审定 (自动) -->
      <el-table-column v-if="isColVisible('priorAudited')" label="期初审定" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
        </template>
      </el-table-column>

      <!-- G: OCI减值准备余额 -->
      <el-table-column v-if="isColVisible('ociImpairment')" label="OCI减值" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.ociImpairment) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.ociImpairment"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'ociImpairment', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.ociImpairment) }}</span>
        </template>
      </el-table-column>

      <!-- H: 本期增加 -->
      <el-table-column v-if="isColVisible('periodIncrease')" label="本期增加" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.periodIncrease) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.periodIncrease"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'periodIncrease', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodIncrease) }}</span>
        </template>
      </el-table-column>

      <!-- I: 本期减少 -->
      <el-table-column v-if="isColVisible('periodDecrease')" label="本期减少" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.periodDecrease) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.periodDecrease"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'periodDecrease', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodDecrease) }}</span>
        </template>
      </el-table-column>

      <!-- J: 期末余额 (自动) -->
      <el-table-column v-if="isColVisible('endBalance')" label="期末余额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <!-- K: 被审计单位重分类 -->
      <el-table-column v-if="isColVisible('entityReclass')" label="重分类" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.entityReclass) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.entityReclass"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'entityReclass', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.entityReclass) }}</span>
        </template>
      </el-table-column>

      <!-- L: 期末未审余额 (自动) -->
      <el-table-column v-if="isColVisible('endUnadjusted')" label="期末未审" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endUnadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- M: 期末账项调整 -->
      <el-table-column v-if="isColVisible('endAje')" label="期末AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'endAje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endAje) }}</span>
        </template>
      </el-table-column>

      <!-- N: 期末重分类调整 -->
      <el-table-column v-if="isColVisible('endRje')" label="期末RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'endRje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endRje) }}</span>
        </template>
      </el-table-column>

      <!-- O: 期末审定余额 (自动) -->
      <el-table-column label="期末审定" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endAudited) }}</span>
        </template>
      </el-table-column>

      <!-- P: 期末OCI减值 -->
      <el-table-column v-if="isColVisible('endOciImpairment')" label="期末OCI减值" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endOciImpairment) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endOciImpairment"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'endOciImpairment', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endOciImpairment) }}</span>
        </template>
      </el-table-column>

      <!-- Q: 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(val: string) => updateCell(row.rowId, 'remark', val)"
          />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            type="danger"
            text
            size="small"
            @click="removeRow(row.rowId)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D5-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:D1-6" :context-project-id="projectId" />
            <GtIndexChip value="wp:D2-13" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genDetailNote">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D5-detail-note')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditExplanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 7 }"
          :disabled="isReadonly"
          placeholder="对明细表本期变动的分析说明..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">审计结论</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genDetailConclusion">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D5-detail-conclusion')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 7 }"
          :disabled="isReadonly"
          placeholder="对应收款项融资明细表的审计结论..."
        />
      </div>
    </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D5TabDetail.vue — D5-2 明细表
 *
 * el-table 横向滚动17列，固定前2列（类别/明细项目）
 * 自动计算列灰底不可编辑（F/J/L/O）
 * 按类别小计行 + 总合计行
 * 超30行虚拟滚动（max-height限制）
 *
 * Task: 14.1
 * Requirements: 4.1-4.9, 5.1-5.7, 10.9
 */
import { ref, computed, inject, watch, toRef, type Ref } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { useD5Detail, createEmptyRow, recalcRow } from '../composables/useD5Detail'
import { useD5DetailColumnPrefs } from '../composables/useD5DetailColumnPrefs'
import type { ChecklistResponse } from '../composables/useD5FormData'
import { useD5ImportExport } from '../composables/useD5ImportExport'
import { useD5AiGenerate } from '../composables/useD5AiGenerate'
import { parseNum } from '../composables/useD5FormulaEngine'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
// @ts-ignore
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  year?: number
  bsDate?: string
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

// ─── Column Preferences ──────────────────────────────────────────────────────

const { columnGroups, hiddenKeys, isColVisible, toggleCol, resetDefaults } = useD5DetailColumnPrefs()

const COL_LABELS: Record<string, string> = {
  category: '类别', itemName: '明细项目', priorUnadjusted: '期初未审',
  priorAje: '期初AJE', priorRje: '期初RJE', priorAudited: '期初审定',
  ociImpairment: 'OCI减值', periodIncrease: '本期增加', periodDecrease: '本期减少',
  endBalance: '期末余额', entityReclass: '重分类', endUnadjusted: '期末未审',
  endAje: '期末AJE', endRje: '期末RJE', endAudited: '期末审定',
  endOciImpairment: '期末OCI减值', remark: '备注',
}
function getColLabel(key: string): string { return COL_LABELS[key] || key }

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD5ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D5-2',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
}

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  subtotalByCategory,
  totalRow,
  addRow,
  removeRow,
  updateCell,
  importFromD1,
  importFromD2,
  importFromAuxBalance,
  importPostRealizedFromLedger,
} = useD5Detail({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

// ─── 抽凭引擎 ───────────────────────────────────────────────────────────────

const showSamplingDialog = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())

function onSampleFilled(payload: any) {
  const samples = payload?.samples
  if (!Array.isArray(samples) || samples.length === 0) return

  const imported = samples.map((s: any) => {
    const row = createEmptyRow()
    row.category = '应收票据'
    row.itemName = s.counterpartAccount || s.summary || ''
    row.periodIncrease = parseNum(s.debitAmount)
    row.periodDecrease = parseNum(s.creditAmount)
    row.remark = `抽凭: ${s.voucherNo || ''}`
    return recalcRow(row)
  })

  rows.value = [...rows.value, ...imported]
  props.debouncedSave('D5-2-rows', { remark: JSON.stringify(rows.value) })
  showSamplingDialog.value = false
}

// ─── 期后兑现取数 ────────────────────────────────────────────────────────────

function doImportPostRealized() {
  const bsDate = props.bsDate || (props.year ? `${props.year}-12-31` : `${new Date().getFullYear()}-12-31`)
  importPostRealizedFromLedger(bsDate)
}

const crossCheckInfo = computed(() => {
  const d5NotesTotal = subtotalByCategory.value['应收票据']?.endAudited ?? 0
  const d5AccTotal = subtotalByCategory.value['应收账款']?.endAudited ?? 0

  const d1SoldTotal = parseFloat(allResponsesRef.value.get('D1-6-sold-total')?.remark || '') || 0
  const d2SoldTotal = parseFloat(allResponsesRef.value.get('D2-13-sold-total')?.remark || '') || 0

  // If no D1/D2 data available, show info
  if (d1SoldTotal === 0 && d2SoldTotal === 0) {
    return { type: 'info' as const, message: '勾稽校验：D1-6/D2-13 暂无出售模式数据，无法核对' }
  }

  const notesDiff = d5NotesTotal - d1SoldTotal
  const accDiff = d5AccTotal - d2SoldTotal

  if (Math.abs(notesDiff) < 0.01 && Math.abs(accDiff) < 0.01) {
    return { type: 'success' as const, message: `勾稽校验通过：应收票据 ${fmtAmount(d5NotesTotal)} = D1-6 ${fmtAmount(d1SoldTotal)}，应收账款 ${fmtAmount(d5AccTotal)} = D2-13 ${fmtAmount(d2SoldTotal)}` }
  }

  const parts: string[] = []
  if (Math.abs(notesDiff) >= 0.01) parts.push(`应收票据差异 ${fmtAmount(notesDiff)}（D5: ${fmtAmount(d5NotesTotal)} vs D1-6: ${fmtAmount(d1SoldTotal)}）`)
  if (Math.abs(accDiff) >= 0.01) parts.push(`应收账款差异 ${fmtAmount(accDiff)}（D5: ${fmtAmount(d5AccTotal)} vs D2-13: ${fmtAmount(d2SoldTotal)}）`)

  return { type: 'warning' as const, message: `勾稽校验：${parts.join('；')}` }
})

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = rows
const browseRowCount = computed(() => rows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('category', '类别', 100),
  virtualTextCol('itemName', '明细项目', 120),
  virtualNumCol('priorUnadjusted', '期初未审', 100, fmtAmount),
  virtualNumCol('endUnadjusted', '期末未审', 100, fmtAmount),
  virtualNumCol('endAudited', '期末审定', 100, fmtAmount),
  virtualTextCol('remark', '备注', 120),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 1400,
})

// ─── Audit Notes ─────────────────────────────────────────────────────────────

const auditExplanation = ref('')
const auditConclusion = ref('')

watch(
  () => allResponsesRef.value.get('D5-2-note-explanation')?.remark,
  (val) => { auditExplanation.value = val || '' },
  { immediate: true },
)

watch(auditExplanation, (val) => {
  props.debouncedSave('D5-2-note-explanation', { remark: val })
})

watch(
  () => allResponsesRef.value.get('D5-2-note-conclusion')?.remark,
  (val) => { auditConclusion.value = val || '' },
  { immediate: true },
)

watch(auditConclusion, (val) => {
  props.debouncedSave('D5-2-note-conclusion', { remark: val })
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD5AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genDetailNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('detail-change', auditExplanation.value, {
    task: '应收款项融资明细表变动分析',
    rowCount: rows.value.length,
  }, 'AI · 明细变动分析')
  if (text) auditExplanation.value = text
}

async function genDetailConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('detail-conclusion', auditConclusion.value, {
    task: '应收款项融资明细表审计结论',
    rowCount: rows.value.length,
  }, 'AI · 审计结论')
  if (text) auditConclusion.value = text
}

// ─── Display Rows (含小计行+合计行) ──────────────────────────────────────────

interface DisplayRow {
  rowId: string
  category: string
  itemName: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  ociImpairment: number
  periodIncrease: number
  periodDecrease: number
  endBalance: number
  entityReclass: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  endOciImpairment: number
  remark: string
  _isSubtotal?: boolean
  _isTotal?: boolean
}

const displayRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = []
  // 按类别分组：先显示应收票据行及其小计，再显示应收账款行及其小计
  const categories = ['应收票据', '应收账款']

  for (const cat of categories) {
    const catRows = rows.value.filter(r => r.category === cat)
    if (catRows.length > 0) {
      result.push(...catRows.map(r => ({ ...r } as DisplayRow)))
      // 类别小计行
      const sub = subtotalByCategory.value[cat]
      if (sub) {
        result.push({
          ...sub,
          rowId: `__subtotal-${cat}__`,
          category: `${cat}小计`,
          itemName: '',
          _isSubtotal: true,
        } as DisplayRow)
      }
    }
  }

  // 未分类行
  const uncategorized = rows.value.filter(r => !categories.includes(r.category))
  if (uncategorized.length > 0) {
    result.push(...uncategorized.map(r => ({ ...r } as DisplayRow)))
  }

  // 总合计行
  result.push({
    ...totalRow.value,
    rowId: '__total__',
    category: '合计',
    itemName: '',
    _isTotal: true,
  } as DisplayRow)

  return result
})

function openReview(sectionId: string) {
  openReviewDialog(sectionId)
}
</script>

<style scoped>
.d5-detail {
  padding: 12px;
}
.d5-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d5-detail :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.virtual-hint {
  flex: 1;
}

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  color: #909399;
}
.subtotal-label {
  font-weight: 700;
}
.subtotal-amount {
  font-weight: 700;
}

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}

/* 列设置 popover */
.col-prefs-popover { max-height: 320px; overflow-y: auto; }
.col-prefs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
.col-prefs-group { margin-bottom: 8px; }
.col-prefs-group-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.col-prefs-item { margin-left: 8px; }
</style>
