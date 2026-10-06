<template>
  <div class="cw-layout" :data-load-status="worksheetLoadState">
    <el-alert
      v-if="worksheetLoadState === 'error'"
      type="error"
      :closable="false"
      show-icon
      class="cw-load-error"
      data-testid="cw-load-error"
      :title="worksheetLoadError || '合并工作底稿加载失败，请稍后重试'"
    />
    <el-alert
      v-else-if="worksheetLoadState === 'empty'"
      type="info"
      :closable="false"
      show-icon
      class="cw-empty-state"
      data-testid="cw-empty-state"
      title="当前年度暂无已保存的合并工作底稿，已加载可编辑默认表格"
    />
    <!-- 总分汇总提示：仅在验证结果为纯「总分汇总」时显示（需求 4.6） -->
    <el-alert
      v-if="isBranchMode"
      type="info"
      :closable="false"
      show-icon
      class="cw-branch-notice"
      data-testid="cw-branch-notice"
    >
      <template #title>
        <span>本项目的下级企业都是<b>分公司</b>（总分汇总）：分公司为非独立法人，合并数 = 本部与各分公司审定数之和加母分差额，<b>无需填写以下母子合并抵销底稿</b>；本部与分公司之间的内部抵销请在企业树的「母分差额」节点录入。合并方式按各下级企业的与上级关系自动识别。</span>
      </template>
    </el-alert>
    <!-- G7 合并联动 stale 常驻提示（Task 6.1；失败静默降级 Property 12） -->
    <el-alert
      v-if="linkageStale.stale.value"
      type="warning"
      :closable="false"
      show-icon
      class="cw-linkage-stale-notice"
      title="G7 长期股权投资联动结果已过期，请从 G7 底稿重新联动或重新导入"
      :description="linkageStale.staleSheets.value.length
        ? `受影响底稿：${linkageStale.staleSheets.value.join('、')}`
        : ''"
    />
    <!-- 左侧：表样导航 -->
    <aside class="cw-nav" :style="{ width: navWidth + 'px' }">
      <div class="cw-nav-header">
        <span class="cw-nav-title">合并工作底稿</span>
        <el-tooltip content="合并流程：基础数据→净资产归集→权益法模拟→抵消分录→汇总核查" placement="right">
          <span style="cursor:help;font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">ⓘ</span>
        </el-tooltip>
      </div>
      <div class="cw-nav-list">
        <template v-for="group in navGroups" :key="group.key">
          <div class="cw-nav-group" @click="groupCollapsed[group.key] = !groupCollapsed[group.key]">
            <div class="cw-nav-group-left">
              <span class="cw-nav-group-num">{{ group.step }}</span>
              <span class="cw-nav-group-label">{{ group.label }}</span>
            </div>
            <div class="cw-nav-group-right">
              <span class="cw-nav-group-count">{{ group.sheets.length }}表</span>
              <span class="cw-nav-group-arrow">{{ group.collapsed ? '›' : '‹' }}</span>
            </div>
          </div>
          <template v-if="!group.collapsed">
            <div v-for="sheet in group.sheets" :key="sheet.key"
              class="cw-nav-item" :class="{ 'cw-nav-item--active': activeSheet === sheet.key }"
              @click="activeSheet = sheet.key">
              <el-icon :size="14"><component :is="sheet.icon" /></el-icon>
              <div class="cw-nav-item-text">
                <span class="cw-nav-item-label">{{ sheet.label }}</span>
                <span class="cw-nav-item-desc">{{ sheet.desc }}</span>
              </div>
              <el-tag v-if="sheet.tag" :type="(sheet.tagType) || undefined" size="small" effect="plain" style="flex-shrink:0">{{ sheet.tag }}</el-tag>
            </div>
          </template>
        </template>
      </div>
    </aside>
    <div class="cw-resizer" @mousedown="startResize" />
    <!-- 右侧：表样内容 -->
    <main class="cw-content">
      <!-- 导入导出工具栏（合并工作底稿 Phase 1） -->
      <div class="cw-ie-toolbar">
        <el-button size="small" type="success" plain :loading="g7LinkageLoading" @click="openG7Linkage">
          从 G7 联动
        </el-button>
        <el-dropdown v-if="canImportExport" trigger="click" @command="(cmd: string) => {
          if (cmd === 'export-template') handleExportTemplate()
          else if (cmd === 'export-data') handleExportData()
          else if (cmd === 'import-data') handleImportClick()
        }">
          <el-button size="small" type="primary" plain>
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">↓ 导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">↓ 导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>↑ 导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="importFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleImportFile" />
      </div>
      <SubsidiaryInfoSheet v-if="activeSheet === 'info'" v-model="data.subsidiaryInfo"
        @save="onSave('基本信息表', $event)" @open-share-change="onOpenShareChange" @open-formula="onOpenFormula" />
      <InvestmentCostSheet v-else-if="activeSheet === 'cost'" v-model="data.investmentCost"
        @save="onSave('投资明细-成本法', $event)" @open-formula="onOpenFormula" />
      <InvestmentEquitySheet v-else-if="activeSheet === 'equity_inv'" v-model="data.investmentEquity"
        @save="onSave('投资明细-权益法', $event)" @open-formula="onOpenFormula" />
      <NetAssetSheet v-else-if="activeSheet === 'net_asset'" :companies="companyColumns" v-model="data.netAsset"
        @save="onSave('净资产表', $event)" @open-formula="onOpenFormula"
        @restore-defaults="data.netAsset = buildNetAsset()" />
      <EquitySimSheet v-else-if="activeSheet === 'equity_sim'" :companies="companyColumns"
        :direct-rows="data.equitySimDirect" :indirect-sections="computedIndirectSections"
        :net-asset-data="data.netAsset"
        @save="onSave('模拟权益法', $event)" @open-formula="onOpenFormula" />
      <!-- 合并抵消分录明细表：唯一来源 elimination_entries；工作底稿三类来源的计算结果作为待生成分组传入 -->
      <EliminationSheet v-else-if="activeSheet === 'elimination'" ref="eliminationSheetRef" :project-id="projectId" :year="year"
        :source-groups="sourceGroups" :source-origins="sourceOrigins"
        @open-formula="onOpenFormula" @goto-sheet="onGotoSheet" />
      <CapitalReserveSheet v-else-if="activeSheet === 'capital'" :companies="companyColumns"
        v-model="data.capitalReserve" :elimination-data="elimSummaryForCapital"
        @save="onSave('资本公积变动', $event)" @open-formula="onOpenFormula" />
      <!-- 动态股比变动表 -->
      <ShareChangeSheet v-else-if="activeSheet.startsWith('share_change_')"
        :key="activeSheet"
        :change-times="activeShareChangeTimes"
        :companies="activeShareChangeCompanies"
        :all-companies="companyColumns"
        :indirect-companies="indirectCompanyList"
        :initial-data="shareChangeData[activeSheet] || []"
        @save="onShareChangeSave" @open-formula="onOpenFormula" />
      <!-- 汇总计算表 -->
      <PostElimInvestSheet v-else-if="activeSheet === 'post_invest'"
        :companies="companyColumns" :investment-cost="data.investmentCost"
        :investment-equity="data.investmentEquity" :equity-sim-direct="data.equitySimDirect"
        :elim-equity="data.elimEquity" @save="onSave('抵消后长投', $event)" @open-formula="onOpenFormula"
        @goto-sheet="onGotoSheet" />
      <PostElimIncomeSheet v-else-if="activeSheet === 'post_income'"
        :companies="companyColumns" :investment-cost="data.investmentCost"
        :equity-sim-direct="data.equitySimDirect" :elim-income="data.elimIncome"
        @save="onSave('抵消后投资收益', $event)"
        @goto-sheet="onGotoSheet" @open-formula="onOpenFormula" />
      <MinorityInterestSheet v-else-if="activeSheet === 'minority'"
        :companies="companyColumns" :net-asset-data="data.netAsset"
        :equity-sim-direct="data.equitySimDirect" :elim-equity="data.elimEquity"
        :elim-income="data.elimIncome" @save="onSave('少数股东权益损益', $event)"
        @goto-sheet="onGotoSheet" @open-formula="onOpenFormula" />
      <!-- 内部抵消表 -->
      <InternalArApSheet v-else-if="activeSheet === 'internal_arap'"
        :companies="companyColumns" :initial-rows="internalRows.arap"
        @save="onSave('内部往来抵消', $event)" @open-formula="onOpenFormula"
        @rows-changed="(r: any[]) => internalRows.arap = r" />
      <InternalTradeSheet v-else-if="activeSheet === 'internal_trade'"
        :companies="companyColumns" :initial-rows="internalRows.trade"
        @save="onSave('内部交易抵消', $event)" @open-formula="onOpenFormula"
        @rows-changed="(r: any[]) => internalRows.trade = r" />
      <!-- 内部现金流没有会计科目（属现金流量表工作底稿），不生成抵销分录 -->
      <InternalCashFlowSheet v-else-if="activeSheet === 'internal_cashflow'"
        :companies="companyColumns" @save="onSave('内部现金流抵消', $event)" @open-formula="onOpenFormula" />
      <!-- G7 建议草稿（只读；由 G7 联动勾选建议后写入，不参与合并计算） -->
      <G7SuggestionDraftSheet v-else-if="activeSheet === 'g7_suggestions'"
        :rows="g7SuggestionDraft.rows" :note="g7SuggestionDraft.note"
        :imported-at="g7SuggestionDraft.importedAt"
        @goto-sheet="onGotoSheet" @refresh="loadAllData" />
    </main>

    <el-dialog v-model="g7LinkageVisible" title="G7 → 合并工作底稿联动" width="920px" destroy-on-close>
      <el-alert
        v-if="g7LinkagePreview && !g7LinkagePreview.source_wp_id"
        type="warning"
        :closable="false"
        title="当前项目未找到 G7 工作底稿"
      />
      <template v-else-if="g7LinkagePreview">
        <el-descriptions :column="3" border size="small" class="g7-linkage-summary">
          <el-descriptions-item label="来源底稿">G7</el-descriptions-item>
          <el-descriptions-item label="已识别源表">{{ g7LinkagePreview.sources_used.join('、') || '无' }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatLinkageTime(g7LinkagePreview.source_updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="基本信息">
            {{ g7LinkagePreview.counts.info?.importable || 0 }}/{{ g7LinkagePreview.counts.info?.candidate || 0 }} 可导入
          </el-descriptions-item>
          <el-descriptions-item label="成本法明细">
            {{ g7LinkagePreview.counts.cost?.importable || 0 }}/{{ g7LinkagePreview.counts.cost?.candidate || 0 }} 可导入
          </el-descriptions-item>
          <el-descriptions-item label="权益法明细">
            {{ g7LinkagePreview.counts.equity_inv?.importable || 0 }}/{{ g7LinkagePreview.counts.equity_inv?.candidate || 0 }} 可导入
          </el-descriptions-item>
          <el-descriptions-item label="净资产表">
            {{ g7LinkagePreview.counts.net_asset?.importable || 0 }}/{{ g7LinkagePreview.counts.net_asset?.candidate || 0 }} 可导入
          </el-descriptions-item>
          <el-descriptions-item label="字段差异">
            新增 {{ g7LinkagePreview.diff_summary?.added || 0 }} /
            变更 {{ g7LinkagePreview.diff_summary?.changed || 0 }} /
            冲突 {{ g7LinkagePreview.diff_summary?.conflict || 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="建议草稿">
            {{ g7LinkagePreview.suggestions?.length || 0 }} 条（G7-9/10/3/16）
          </el-descriptions-item>
        </el-descriptions>

        <el-alert type="info" :closable="false" class="g7-linkage-note">
          默认只填充合并底稿空值，并保存 G7 来源信息；不会自动生成正式抵消分录。
          勾选「基本信息」才会同步合并范围，且不覆盖已有纳入状态。
          商誉/少数股东仅作建议草稿，需单独勾选后写入。
        </el-alert>

        <el-alert
          v-if="g7LinkagePreview.linkage_stale"
          type="error"
          :closable="false"
          class="g7-linkage-note"
          :title="`G7 源数据已变更，以下合并底稿联动过期：${(g7LinkagePreview.stale_sheets || []).join('、') || '相关表'}。请重新确认导入。`"
        />

        <el-alert
          v-if="(g7LinkagePreview.skipped_net_asset_fields?.length || 0) > 0"
          type="warning"
          :closable="false"
          class="g7-linkage-note"
          :title="`净资产有 ${g7LinkagePreview.skipped_net_asset_fields?.length} 项无对应行已跳过（如公允价值调整/内部交易），未并入未分配利润`"
        />

        <el-alert
          v-if="(g7LinkagePreview.ambiguous_companies?.length || 0) > 0"
          type="warning"
          :closable="false"
          class="g7-linkage-note"
          title="存在同名企业，请手动选择企业代码后才能导入"
        />

        <div v-if="g7PendingMappings.length" class="g7-linkage-mapping">
          <div class="g7-linkage-title">待确认主体映射</div>
          <el-table :data="g7PendingMappings" border size="small" max-height="220">
            <el-table-column label="原因" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.reason === 'ambiguous' ? 'warning' : 'info'">
                  {{ row.reason === 'ambiguous' ? '同名冲突' : '未匹配' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="G7 被投资单位" min-width="200">
              <template #default="{ row }">{{ row.name }}</template>
            </el-table-column>
            <el-table-column label="合并企业代码" min-width="320">
              <template #default="{ row }">
                <el-select v-model="g7CompanyMappings[row.name]" clearable filterable placeholder="选择匹配企业；留空则本次跳过">
                  <el-option
                    v-for="company in g7LinkagePreview.available_companies"
                    :key="company.company_code"
                    :label="`${company.company_name}（${company.company_code}）`"
                    :value="company.company_code"
                  />
                </el-select>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="g7EditableDiffs.length" class="g7-linkage-mapping">
          <div class="g7-linkage-title">
            字段差异确认
            <el-button link type="primary" size="small" @click="selectAllDiffs(true)">全选可写入</el-button>
            <el-button link size="small" @click="selectAllDiffs(false)">清空</el-button>
          </div>
          <el-table :data="g7EditableDiffs" border size="small" max-height="260">
            <el-table-column width="52" align="center">
              <template #default="{ row }">
                <el-checkbox
                  v-model="row.selected"
                  :disabled="row.status === 'conflict' && !g7Overwrite"
                />
              </template>
            </el-table-column>
            <el-table-column label="表" width="100" prop="sheet_key" />
            <el-table-column label="企业" min-width="120">
              <template #default="{ row }">{{ row.company_name || row.identity }}</template>
            </el-table-column>
            <el-table-column label="字段" width="130" prop="field" />
            <el-table-column label="原值" min-width="100">
              <template #default="{ row }">{{ formatDiffValue(row.old_value) }}</template>
            </el-table-column>
            <el-table-column label="G7 新值" min-width="100">
              <template #default="{ row }">{{ formatDiffValue(row.new_value) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.status === 'conflict' ? 'danger' : row.status === 'added' ? 'success' : 'warning'"
                >
                  {{ diffStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="g7UnrecognizedMetaRows.length" class="g7-linkage-mapping">
          <div class="g7-linkage-title">G7-16 未确认损失备查（结构化，不入正式抵消）</div>
          <el-table :data="g7UnrecognizedMetaRows" border size="small" max-height="200">
            <el-table-column label="企业" min-width="140" prop="company_name" />
            <el-table-column label="超额亏损" width="110" align="right">
              <template #default="{ row }">{{ formatDiffValue(row.excess_loss) }}</template>
            </el-table-column>
            <el-table-column label="未确认损失" width="110" align="right">
              <template #default="{ row }">{{ formatDiffValue(row.unrecognized_loss) }}</template>
            </el-table-column>
            <el-table-column label="上期累计" width="110" align="right">
              <template #default="{ row }">{{ formatDiffValue(row.prior_cumulative) }}</template>
            </el-table-column>
            <el-table-column label="本期变动" width="110" align="right">
              <template #default="{ row }">{{ formatDiffValue(row.current_change) }}</template>
            </el-table-column>
            <el-table-column label="G7-14其他调整" width="120" align="right">
              <template #default="{ row }">{{ formatDiffValue(row.other_adj) }}</template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="(g7LinkagePreview.suggestions?.length || 0) > 0" class="g7-linkage-mapping">
          <div class="g7-linkage-title">
            建议草稿（G7-3/6/9/10/13/15/16，不自动入正式抵消；确认后可在左侧「G7 建议草稿」查看）
          </div>
          <el-table :data="g7LinkagePreview.suggestions" border size="small" max-height="240">
            <el-table-column width="52" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="g7SuggestionSelected[row.id]" />
              </template>
            </el-table-column>
            <el-table-column label="来源" width="70" prop="source_sheet" />
            <el-table-column label="类型" width="120">
              <template #default="{ row }">{{ suggestionTypeLabel(row.type) }}</template>
            </el-table-column>
            <el-table-column label="企业/科目" min-width="140">
              <template #default="{ row }">
                {{ row.company_name || row.account_name || '—' }}
              </template>
            </el-table-column>
            <el-table-column label="摘要" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.change_type || row.description || row.note || '—' }}
              </template>
            </el-table-column>
            <el-table-column label="关键金额" width="120">
              <template #default="{ row }">
                {{ formatDiffValue(
                  row.goodwill_amount
                    ?? row.equity_adjustment
                    ?? row.debit_amount
                    ?? row.credit_amount
                    ?? row.unrecognized_loss
                    ?? row.current_change
                    ?? row.amount,
                ) }}
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="g7-linkage-options">
          <el-checkbox-group v-model="g7SelectedSheets">
            <el-checkbox value="info">基本信息/合并范围</el-checkbox>
            <el-checkbox value="cost">成本法投资明细</el-checkbox>
            <el-checkbox value="equity_inv">权益法投资明细</el-checkbox>
            <el-checkbox value="net_asset">净资产表（G7-14）</el-checkbox>
          </el-checkbox-group>
          <el-switch
            v-model="g7Overwrite"
            active-text="覆盖已有非空值（谨慎）"
            @change="onG7OverwriteChange"
          />
        </div>
      </template>
      <template #footer>
        <el-button @click="g7LinkageVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="g7LinkageImporting"
          :disabled="!g7LinkagePreview?.source_wp_id || g7SelectedSheets.length === 0"
          @click="confirmG7Linkage"
        >
          确认联动
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, markRaw, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { List, Coin, TrendCharts, DataBoard, SetUp, Tickets, PieChart } from '@element-plus/icons-vue'
import { getConsolScope, getWorksheetTree } from '@/services/consolidationApi'
import { directSubsidiaryMembers } from '@/components/consolidation/composables/consolTreeView'
import {
  declaredOrigins,
  sourceGroupsByOrigin,
  WORKSHEET_ORIGINS,
} from '@/components/consolidation/composables/elimSourceGroups'
import {
  importG7Linkage,
  loadAllWorksheetData,
  loadWorksheetData,
  previewG7Linkage,
  saveWorksheetData,
  WorksheetVersionConflictError,
  type G7LinkageFieldDiff,
  type G7LinkagePreview,
  type WorksheetLoadStatus,
} from '@/services/consolWorksheetDataApi'
import { useG7ConsolLinkageEntry } from '@/components/workpaper/composables/g7ConsolLinkageEntry'
import SubsidiaryInfoSheet from './SubsidiaryInfoSheet.vue'
import InvestmentCostSheet from './InvestmentCostSheet.vue'
import InvestmentEquitySheet from './InvestmentEquitySheet.vue'
import NetAssetSheet from './NetAssetSheet.vue'
import EquitySimSheet from './EquitySimSheet.vue'
import EliminationSheet from './EliminationSheet.vue'
import CapitalReserveSheet from './CapitalReserveSheet.vue'
import ShareChangeSheet from './ShareChangeSheet.vue'
import PostElimInvestSheet from './PostElimInvestSheet.vue'
import PostElimIncomeSheet from './PostElimIncomeSheet.vue'
import MinorityInterestSheet from './MinorityInterestSheet.vue'
import InternalArApSheet from './InternalArApSheet.vue'
import InternalTradeSheet from './InternalTradeSheet.vue'
import InternalCashFlowSheet from './InternalCashFlowSheet.vue'
import G7SuggestionDraftSheet from './G7SuggestionDraftSheet.vue'
import { eventBus } from '@/utils/eventBus'
import type { FormulaChangedPayload } from '@/utils/eventBus'
import { handleApiError } from '@/utils/errorHandler'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'

interface ConsolWorksheetTabsProps {
  projectId: string
  year: number
  consolMode?: string | null
  isRootSelection?: boolean
}

const props = withDefaults(defineProps<ConsolWorksheetTabsProps>(), {
  consolMode: null,
  isRootSelection: false,
})

const projectId = computed(() => props.projectId)
const year = computed(() => props.year)

const worksheetLoadState = ref<WorksheetLoadStatus>('empty')
const worksheetLoadError = ref('')
const worksheetLoading = ref(false)
let worksheetRequestSeq = 0
let scopeRequestSeq = 0

function isWorksheetContextCurrent(projectSnapshot: string, yearSnapshot: number): boolean {
  return projectId.value === projectSnapshot && year.value === yearSnapshot
}

// ─── 合并工作底稿导入导出列定义 ─────────────────────────────────────────────
const CONSOL_SHEET_COLS: Record<string, ExcelColumn[]> = {
  info: [
    { key: 'company_name', header: '企业名称', width: 20 },
    { key: 'company_code', header: '企业代码', width: 12 },
    { key: 'parent_code', header: '上级企业代码', width: 12 },
    { key: 'ultimate_controller', header: '最终控制方', width: 16 },
    { key: 'accounting_method', header: '核算方式', width: 10 },
    { key: 'holding_type', header: '持股方式', width: 8 },
    { key: 'non_common_ratio', header: '非同一控制持股比例', width: 14 },
    { key: 'common_ratio', header: '同一控制持股比例', width: 14 },
    { key: 'acquisition_date', header: '取得日', width: 12 },
    { key: 'merge_type', header: '合并类型', width: 10 },
    { key: 'first_consol_date', header: '首次合并日', width: 12 },
  ],
  cost: [
    { key: 'sub_name', header: '被投资单位', width: 20 },
    { key: 'sub_code', header: '企业代码', width: 12 },
    { key: 'initial_cost', header: '初始投资成本', width: 14 },
    { key: 'book_value', header: '账面价值', width: 14 },
    { key: 'fair_value', header: '公允价值', width: 14 },
    { key: 'dividend_received', header: '已收股利', width: 14 },
    { key: 'impairment', header: '减值准备', width: 14 },
  ],
  equity_inv: [
    { key: 'sub_name', header: '被投资单位', width: 20 },
    { key: 'sub_code', header: '企业代码', width: 12 },
    { key: 'initial_cost', header: '初始投资成本', width: 14 },
    { key: 'share_ratio', header: '持股比例', width: 10 },
    { key: 'net_profit_share', header: '损益调整', width: 14 },
    { key: 'other_ci_share', header: '其他综合收益', width: 14 },
    { key: 'book_value', header: '账面价值', width: 14 },
    { key: 'impairment', header: '减值准备', width: 14 },
  ],
  net_asset: [
    { key: 'subject', header: '项目', width: 20 },
    { key: 'begin_amount', header: '期初数', width: 14 },
    { key: 'end_amount', header: '期末数', width: 14 },
    { key: 'remark', header: '备注', width: 16 },
  ],
  equity_sim: [
    { key: 'sub_name', header: '被投资单位', width: 20 },
    { key: 'ratio', header: '持股比例', width: 10 },
    { key: 'begin_equity', header: '期初净资产', width: 14 },
    { key: 'end_equity', header: '期末净资产', width: 14 },
    { key: 'net_profit', header: '本期净利润份额', width: 14 },
    { key: 'other_ci', header: '其他综合收益份额', width: 14 },
    { key: 'simulated_value', header: '模拟权益法金额', width: 14 },
  ],
  capital: [
    { key: 'item', header: '项目', width: 20 },
    { key: 'begin_amount', header: '期初数', width: 14 },
    { key: 'increase', header: '本期增加', width: 14 },
    { key: 'decrease', header: '本期减少', width: 14 },
    { key: 'end_amount', header: '期末数', width: 14 },
    { key: 'remark', header: '备注', width: 16 },
  ],
  // ── Phase 1 扩展：剩余 10 张表 ──────────────────────────────────────────
  post_invest: [
    { key: 'sub_name', header: '被投资单位', width: 20 },
    { key: 'sub_code', header: '企业代码', width: 12 },
    { key: 'method', header: '核算方式', width: 10 },
    { key: 'cost_book_value', header: '账面价值（投资）', width: 16 },
    { key: 'equity_sim_value', header: '模拟权益法金额', width: 16 },
    { key: 'elim_amount', header: '抵消金额', width: 14 },
    { key: 'post_elim_value', header: '抵消后长投', width: 14 },
    { key: 'remark', header: '备注', width: 16 },
  ],
  post_income: [
    { key: 'sub_name', header: '被投资单位', width: 20 },
    { key: 'sub_code', header: '企业代码', width: 12 },
    { key: 'cost_income', header: '成本法投资收益', width: 16 },
    { key: 'equity_income', header: '权益法投资收益', width: 16 },
    { key: 'elim_income', header: '抵消投资收益', width: 14 },
    { key: 'post_elim_income', header: '抵消后投资收益', width: 16 },
    { key: 'remark', header: '备注', width: 16 },
  ],
  minority: [
    { key: 'sub_name', header: '被投资单位', width: 20 },
    { key: 'sub_code', header: '企业代码', width: 12 },
    { key: 'minority_ratio', header: '少数股东比例', width: 14 },
    { key: 'begin_equity', header: '期初少数股东权益', width: 16 },
    { key: 'net_profit_share', header: '少数股东损益', width: 14 },
    { key: 'other_ci_share', header: '其他综合收益份额', width: 16 },
    { key: 'dividend', header: '分红', width: 14 },
    { key: 'end_equity', header: '期末少数股东权益', width: 16 },
  ],
  internal_arap: [
    { key: 'from_company', header: '债务方', width: 16 },
    { key: 'to_company', header: '债权方', width: 16 },
    { key: 'subject', header: '科目', width: 16 },
    { key: 'amount', header: '金额', width: 14 },
    { key: 'direction', header: '借贷', width: 8 },
    { key: 'confirmed', header: '已确认', width: 8 },
    { key: 'diff_amount', header: '差异金额', width: 14 },
    { key: 'remark', header: '说明', width: 16 },
  ],
  internal_trade: [
    { key: 'seller', header: '销售方', width: 16 },
    { key: 'buyer', header: '购买方', width: 16 },
    { key: 'trade_type', header: '交易类型', width: 12 },
    { key: 'revenue_amount', header: '收入金额', width: 14 },
    { key: 'cost_amount', header: '成本金额', width: 14 },
    { key: 'unrealized_profit', header: '未实现利润', width: 14 },
    { key: 'direction', header: '借贷', width: 8 },
    { key: 'remark', header: '说明', width: 16 },
  ],
  internal_cashflow: [
    { key: 'from_company', header: '付款方', width: 16 },
    { key: 'to_company', header: '收款方', width: 16 },
    { key: 'cashflow_type', header: '现金流类型', width: 14 },
    { key: 'amount', header: '金额', width: 14 },
    { key: 'direction', header: '借贷', width: 8 },
    { key: 'remark', header: '说明', width: 16 },
  ],
  // 合并抵消分录不在此列：分录唯一来源是 elimination_entries（明细表自带导出），
  // 这里的导入会把 Excel 行写进 consol_worksheet_data['elimination']，而该 JSON 已不参与任何计算（需求 1.1）
  share_change: [
    { key: 'company_name', header: '企业名称', width: 20 },
    { key: 'change_date', header: '变动日期', width: 12 },
    { key: 'before_ratio', header: '变动前比例', width: 12 },
    { key: 'after_ratio', header: '变动后比例', width: 12 },
    { key: 'change_type', header: '变动类型', width: 12 },
    { key: 'amount', header: '变动金额', width: 14 },
    { key: 'remark', header: '备注', width: 16 },
  ],
}

interface SubsidiaryInfoRow {
  company_name: string; company_code: string; parent_code: string
  ultimate_controller: string; ultimate_controller_code: string
  account_subject: string
  accounting_method: string; holding_type: string; indirect_holder: string; share_changed: string; change_times: number
  acquisition_date: string; merge_type: string; first_consol_date: string
  non_common_cost: number | null; non_common_ratio: number | null
  common_cost: number | null; common_ratio: number | null
  no_consol_cost: number | null; no_consol_ratio: number | null
  disposal_date: string; disposal_amount: number | null; disposal_ratio: number | null
  pre_disposal_reduce: string; pre_disposal_times: number | null
  post_disposal_reduce: string; post_disposal_times: number | null
}
interface NetAssetRow {
  seq: string; item: string; total: number | null; parent: number | null
  values: (number | null)[]; indent?: number; bold?: boolean
  isHeader?: boolean; isComputed?: boolean; section?: string
}
interface EquitySimRow {
  seq: string; step: string; direction: string; subject: string; detail: string
  total: number | null; values?: (number | null)[]; isStep?: boolean; isComputed?: boolean
}
interface IndirectSection {
  companyName: string; ratio: number; rows: EquitySimRow[]
  endLongInvest: number; endNetAssetShare: number; difference: number; diffReason: string
}
interface ElimRow {
  direction: string; subject: string; detail?: string
  total?: number | null; values?: (number | null)[]; isComputed?: boolean
}
interface CapitalReserveRow {
  item: string; total: number | null; elimAdj: number | null; parentVal: number | null
  values?: (number | null)[]; bold?: boolean; isComputed?: boolean; fromElim?: boolean; isDiff?: boolean; note?: string
}

const EQUITY_ITEMS = [
  '实收资本（或股本）', '其他权益工具', '资本公积', '减：库存股',
  '其他综合收益', '专项储备', '盈余公积', '△一般风险准备', '未分配利润',
]

const staticSheets = [
  { key: 'info', label: '基本信息表', desc: '子企业清单·核算方式·持股变动', icon: markRaw(List), tag: '基础', tagType: '' as const },
  { key: 'cost', label: '投资明细-成本法和公允值', desc: '期初→增加→减少→期末', icon: markRaw(Coin), tag: '基础', tagType: '' as const },
  { key: 'equity_inv', label: '投资明细-权益法', desc: '权益法长投台账', icon: markRaw(TrendCharts), tag: '基础', tagType: '' as const },
  { key: 'net_asset', label: '净资产表', desc: '净资产和损益变动·长投校对', icon: markRaw(DataBoard), tag: '核心', tagType: 'warning' as const },
  { key: 'equity_sim', label: '模拟权益法', desc: '直接持股+间接持股·9步模拟', icon: markRaw(SetUp), tag: '引擎', tagType: 'danger' as const },
  { key: 'elimination', label: '合并抵消分录', desc: '全部调整抵销分录·待生成·审批后推送', icon: markRaw(Tickets), tag: '输出', tagType: 'success' as const },
  { key: 'capital', label: '资本公积变动', desc: '从抵消分录提取·差异核查', icon: markRaw(PieChart), tag: '核查', tagType: 'info' as const },
  { key: 'post_invest', label: '抵消后长投明细', desc: '账面+模拟-抵消=合并列示数', icon: markRaw(DataBoard), tag: '汇总', tagType: 'success' as const },
  { key: 'post_income', label: '抵消后投资收益', desc: '红利+模拟-还原-抵消', icon: markRaw(Coin), tag: '汇总', tagType: 'success' as const },
  { key: 'minority', label: '少数股东权益损益', desc: '净资产×少数比例·超额亏损', icon: markRaw(PieChart), tag: '汇总', tagType: 'success' as const },
  { key: 'internal_arap', label: '内部往来抵消', desc: '债务方×债权方·账龄·坏账', icon: markRaw(Tickets), tag: '抵消', tagType: 'warning' as const },
  { key: 'internal_trade', label: '内部交易抵消', desc: '卖方×买方·未实现利润', icon: markRaw(Tickets), tag: '抵消', tagType: 'warning' as const },
  { key: 'internal_cashflow', label: '内部现金流抵消', desc: '按现金流量表项目配对', icon: markRaw(Tickets), tag: '抵消', tagType: 'warning' as const },
  { key: 'g7_suggestions', label: 'G7 建议草稿', desc: '商誉/股比/调整分录建议·需复核', icon: markRaw(Tickets), tag: '草稿', tagType: 'warning' as const },
]

// 从基本信息表提取有股比变动的企业，动态生成导航项
// 设计 §十三.2：不限于 1|2|3，从事件集合（或已保存的 share_change_N 键）动态生成
const shareChangeSheets = computed(() => {
  const sheets: any[] = []
  const changedCompanies = data.subsidiaryInfo.filter(
    (r: SubsidiaryInfoRow) => r.share_changed === '是' && r.change_times > 0 && r.company_name
  )
  // 收集所有出现过的变动次数（含已保存数据中超过 3 次的 share_change_N 键）
  const timesSet = new Set<number>()
  for (const r of changedCompanies) {
    if (r.change_times > 0) timesSet.add(r.change_times)
  }
  // 补充已加载数据中的 share_change_N 键（后端可能有 4 次以上的保存数据）
  for (const key of Object.keys(shareChangeData)) {
    const match = key.match(/^share_change_(\d+)$/)
    if (match) timesSet.add(Number(match[1]))
  }
  // 按次数升序生成导航项
  const sortedTimes = [...timesSet].sort((a, b) => a - b)
  for (const times of sortedTimes) {
    const companies = changedCompanies.filter((r: SubsidiaryInfoRow) => r.change_times === times)
    if (companies.length > 0 || shareChangeData[`share_change_${times}`]) {
      const names = companies.map((r: SubsidiaryInfoRow) => r.company_name).join('、')
      sheets.push({
        key: `share_change_${times}`,
        label: `股比变${times}次`,
        desc: names.length > 16 ? names.slice(0, 16) + '...' : names,
        icon: markRaw(TrendCharts),
        tag: `${companies.length}家`,
        tagType: 'warning' as const,
        _times: times,
        _companies: companies,
      })
    }
  }
  return sheets
})

const sheetList = computed(() => {
  const list = [...staticSheets]
  const simIdx = list.findIndex(s => s.key === 'equity_sim')
  list.splice(simIdx, 0, ...shareChangeSheets.value)
  return list
})

// ─── 树形分组导航 ─────────────────────────────────────────────────────────────
const groupCollapsed = reactive<Record<string, boolean>>({ g1: false, g2: false, g3: false, g4: true, g5: false, g6: true })

const navGroups = computed(() => [
  {
    key: 'g1', label: '基础数据', step: '1',
    collapsed: groupCollapsed.g1,
    sheets: sheetList.value.filter(s => ['info', 'cost', 'equity_inv'].includes(s.key)),
  },
  {
    key: 'g2', label: '净资产归集', step: '2',
    collapsed: groupCollapsed.g2,
    sheets: sheetList.value.filter(s => s.key === 'net_asset' || s.key.startsWith('share_change_')),
  },
  {
    key: 'g3', label: '权益法模拟', step: '3',
    collapsed: groupCollapsed.g3,
    sheets: sheetList.value.filter(s => s.key === 'equity_sim'),
  },
  {
    key: 'g4', label: '内部抵消', step: '4',
    collapsed: groupCollapsed.g4,
    sheets: sheetList.value.filter(s => ['internal_arap', 'internal_trade', 'internal_cashflow'].includes(s.key)),
  },
  {
    key: 'g5', label: '合并抵消', step: '5',
    collapsed: groupCollapsed.g5,
    sheets: sheetList.value.filter(s => ['elimination', 'capital', 'g7_suggestions'].includes(s.key)),
  },
  {
    key: 'g6', label: '汇总核查', step: '✓',
    collapsed: groupCollapsed.g6,
    sheets: sheetList.value.filter(s => ['post_invest', 'post_income', 'minority'].includes(s.key)),
  },
])

const activeSheet = ref('info')
const eliminationSheetRef = ref<InstanceType<typeof EliminationSheet> | null>(null)

// ─── 从合并范围加载子企业列表 ────────────────────────────────────────────────
// 项目和年度由父页提供，确保工作底稿与左树/报表使用同一年度上下文。

// ─── G7 联动 stale 常驻提示（Task 6.1；失败静默降级 Property 12） ────────────
const linkageStale = useG7ConsolLinkageEntry(projectId, year)

const scopeCompanies = ref<{ name: string; code: string; ratio: number }[]>([])
const g7LinkageVisible = ref(false)
const g7LinkageLoading = ref(false)
const g7LinkageImporting = ref(false)
const g7LinkagePreview = ref<G7LinkagePreview | null>(null)
const g7CompanyMappings = reactive<Record<string, string>>({})
const g7SelectedSheets = ref<string[]>(['info', 'cost', 'equity_inv', 'net_asset'])
const g7Overwrite = ref(false)
const g7EditableDiffs = ref<G7LinkageFieldDiff[]>([])
const g7SuggestionSelected = reactive<Record<string, boolean>>({})
/** 已写入的 G7 建议草稿（sheet_key='g7_suggestions'，只读展示，不参与合并计算） */
const g7SuggestionDraft = reactive<{
  rows: Record<string, any>[]
  note: string
  importedAt: string
}>({ rows: [], note: '', importedAt: '' })

/** 从 importable equity_inv 提取 G7-16 结构化备查字段 */
const g7UnrecognizedMetaRows = computed(() => {
  const inv = g7LinkagePreview.value?.importable?.equity_inv
  if (!Array.isArray(inv)) return [] as Array<Record<string, unknown>>
  return inv
    .filter((r: any) =>
      r?._g7_unrecognized_loss != null
      || r?._g7_excess_loss != null
      || r?._g7_current_change != null
      || r?._g7_g7_16,
    )
    .map((r: any) => ({
      company_name: r.company_name || r.company_code || '—',
      excess_loss: r._g7_excess_loss,
      unrecognized_loss: r._g7_unrecognized_loss,
      prior_cumulative: r._g7_prior_cumulative,
      current_change: r._g7_current_change,
      other_adj: r._g7_other_adj,
    }))
})

const g7PendingMappings = computed(() => {
  const preview = g7LinkagePreview.value
  if (!preview) return [] as Array<{ name: string; reason: 'unresolved' | 'ambiguous' }>
  const rows: Array<{ name: string; reason: 'unresolved' | 'ambiguous' }> = []
  for (const name of preview.ambiguous_companies || []) {
    rows.push({ name, reason: 'ambiguous' })
  }
  for (const name of preview.unresolved_companies || []) {
    if (!(preview.ambiguous_companies || []).includes(name)) {
      rows.push({ name, reason: 'unresolved' })
    }
  }
  return rows
})

function formatLinkageTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function formatDiffValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function diffStatusLabel(status: string): string {
  if (status === 'added') return '新增'
  if (status === 'changed') return '变更'
  if (status === 'conflict') return '冲突'
  return '相同'
}

function suggestionTypeLabel(type: string): string {
  if (type === 'goodwill_nci') return '商誉/NCI'
  if (type === 'share_change_capital') return '股比/资本公积'
  if (type === 'consol_adjustment_draft') return '调整草稿'
  if (type === 'unrecognized_loss') return '未确认损失'
  return type || '建议'
}

function syncDiffSelectionsFromPreview() {
  const diffs = (g7LinkagePreview.value?.field_diffs || []).filter(
    (d) => d.status !== 'unchanged',
  )
  g7EditableDiffs.value = diffs.map((d) => ({
    ...d,
    selected:
      d.status === 'added'
      || d.status === 'changed'
      || (g7Overwrite.value && d.status === 'conflict'),
  }))
}

function selectAllDiffs(selected: boolean) {
  for (const row of g7EditableDiffs.value) {
    if (row.status === 'conflict' && !g7Overwrite.value) {
      row.selected = false
      continue
    }
    row.selected = selected
  }
}

function onG7OverwriteChange() {
  for (const row of g7EditableDiffs.value) {
    if (row.status === 'conflict') {
      row.selected = g7Overwrite.value
    }
  }
}

function resetSuggestionSelections() {
  Object.keys(g7SuggestionSelected).forEach((key) => delete g7SuggestionSelected[key])
  for (const item of g7LinkagePreview.value?.suggestions || []) {
    g7SuggestionSelected[item.id] = !!item.selected_default
  }
}

async function openG7Linkage() {
  if (!projectId.value) {
    ElMessage.warning('项目ID缺失')
    return
  }
  g7LinkageLoading.value = true
  try {
    g7LinkagePreview.value = await previewG7Linkage(projectId.value, year.value)
    Object.keys(g7CompanyMappings).forEach(key => delete g7CompanyMappings[key])
    syncDiffSelectionsFromPreview()
    resetSuggestionSelections()
    g7LinkageVisible.value = true
  } catch (error: any) {
    handleApiError(error, 'G7 联动预览失败')
  } finally {
    g7LinkageLoading.value = false
  }
}

async function confirmG7Linkage() {
  if (!projectId.value || !g7LinkagePreview.value) return
  g7LinkageImporting.value = true
  try {
    const mappings = Object.fromEntries(
      Object.entries(g7CompanyMappings).filter(([, code]) => !!code),
    )
    const selectedDiffs = g7EditableDiffs.value
      .filter((d) => d.selected)
      .map((d) => ({
        sheet_key: d.sheet_key,
        identity: d.identity,
        field: d.field,
      }))
    const applySuggestionIds = Object.entries(g7SuggestionSelected)
      .filter(([, on]) => on)
      .map(([id]) => id)
    // 有新映射时差异表尚未覆盖这些主体；无差异时走整表填空合并
    const useSelectiveDiffs = Object.keys(mappings).length === 0
      && g7EditableDiffs.value.length > 0
    const result = await importG7Linkage(projectId.value, year.value, {
      company_mappings: mappings,
      sheet_keys: g7SelectedSheets.value,
      overwrite: g7Overwrite.value,
      expected_versions: g7LinkagePreview.value.item_versions || {},
      selected_diffs: useSelectiveDiffs ? selectedDiffs : undefined,
      apply_suggestion_ids: applySuggestionIds,
    })
    await Promise.all([loadAllData(), loadConsolScope()])
    g7LinkageVisible.value = false
    // Task 6.1: 成功导入后刷新 stale 状态（Property 12：清除两侧提示）
    void linkageStale.refreshStale()
    const imported = Object.values(result.imported || {}).reduce(
      (rowCount, currentCount) => rowCount + Number(currentCount || 0),
      0,
    )
    const skipped = (result.unresolved_companies?.length || 0)
      + (result.ambiguous_companies?.length || 0)
    const scopeNote = result.scope_synced
      ? `，范围同步 ${result.scope_synced} 家`
      : ''
    const draftNote = result.suggestions_applied
      ? `，建议草稿 ${result.suggestions_applied} 条（见左侧「G7 建议草稿」）`
      : ''
    ElMessage.success(
      `G7 联动完成：导入 ${imported} 行${scopeNote}${draftNote}${skipped ? `，仍有 ${skipped} 个主体未匹配` : ''}`,
    )
  } catch (error: any) {
    const status = error?.response?.status || error?.status
    if (status === 409) {
      ElMessage.warning('G7 源数据已变更，请重新预览后再导入')
      try {
        g7LinkagePreview.value = await previewG7Linkage(projectId.value, year.value)
        syncDiffSelectionsFromPreview()
        resetSuggestionSelections()
      } catch {
        /* ignore refresh failure */
      }
    } else {
      handleApiError(error, 'G7 联动导入失败')
    }
  } finally {
    g7LinkageImporting.value = false
  }
}

// 合并方式按下级企业的与上级关系自动识别（企业树接口 mode）；纯「总分汇总」才提示无需抵销底稿
const treeMode = ref<string | null>(null)
const rootCompanyCode = ref('')
const isBranchMode = computed(() => (props.consolMode ?? treeMode.value) === 'branch')

async function loadConsolScope() {
  const projectSnapshot = projectId.value
  const yearSnapshot = year.value
  if (!projectSnapshot || !yearSnapshot) return
  const ticket = ++scopeRequestSeq
  // 企业树：合并方式识别 + 企业列回退（合并范围表为空时取根合并节点下的子公司类成员）
  let treeMembers: { name: string; code: string; ratio: number }[] = []
  try {
    const res = await getWorksheetTree(projectSnapshot)
    if (ticket !== scopeRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return
    treeMode.value = res?.mode ?? null
    treeMembers = directSubsidiaryMembers(res?.tree)
    // 本合并项目的企业代码：工作底稿里的「母公司」= 它（交易方留痕与归属预填用）
    rootCompanyCode.value = res?.tree?.company_code || ''
  } catch {
    if (ticket !== scopeRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return
    treeMode.value = null
  }
  try {
    // 优先从合并范围获取（持股比例等手工维护信息在这里）
    const items = await getConsolScope(projectSnapshot, yearSnapshot)
    if (ticket !== scopeRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return
    if (Array.isArray(items) && items.length) {
      scopeCompanies.value = items
        .filter((s: any) => s.is_included && s.company_code)
        .map((s: any) => ({
          name: s.company_name || s.company_code,
          code: s.company_code,
          ratio: Number(s.ownership_ratio) || 0,
        }))
      return
    }
  } catch { /* ignore */ }
  if (ticket !== scopeRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return
  // 回退：企业树中的子公司类成员（排除合并差额、母公司与分公司）
  scopeCompanies.value = treeMembers
}

async function loadAllData() {
  const projectSnapshot = projectId.value
  const yearSnapshot = year.value
  if (!projectSnapshot || !yearSnapshot) return
  const ticket = ++worksheetRequestSeq
  worksheetLoading.value = true
  try {
    const result = await loadAllWorksheetData(projectSnapshot, yearSnapshot)
    if (ticket !== worksheetRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return

    if (result.status === 'error') {
      // 同一上下文重载失败时保留已展示数据，避免网络抖动把有效表格清空。
      worksheetLoadState.value = 'error'
      worksheetLoadError.value = result.errorMessage || '工作底稿批量加载失败'
      return
    }

    worksheetLoadState.value = result.status
    worksheetLoadError.value = ''
    resetWorksheetData()
    const saved = result.data
    if (Array.isArray(saved.info?.rows)) data.subsidiaryInfo = saved.info.rows
    if (Array.isArray(saved.cost?.rows)) data.investmentCost = saved.cost.rows
    if (Array.isArray(saved.equity_inv?.rows)) data.investmentEquity = saved.equity_inv.rows
    if (Array.isArray(saved.net_asset?.rows)) data.netAsset = saved.net_asset.rows
    if (saved.equity_sim?.rows && typeof saved.equity_sim.rows === 'object') {
      if (Array.isArray(saved.equity_sim.rows.direct)) data.equitySimDirect = saved.equity_sim.rows.direct
      if (Array.isArray(saved.equity_sim.rows.indirect)) data.equitySimIndirect = saved.equity_sim.rows.indirect
    }
    // 旧版「合并抵消分录」JSON（saved.elimination）不再恢复：分录唯一来源是 elimination_entries，
    // 旧版自定义行由明细表提示并转为草稿分录（需求 1.6 / 9.2）。旧实现读的 rows.equity/income/cross
    // 是对象形状，而旧明细表保存的是数组 ⇒ 这三项从未恢复成功（design §一 F3），data.elimEquity 等
    // 一直是骨架行，下游 PostElimInvest / PostElimIncome / MinorityInterest / 资本公积沿用骨架，行为不变。
    // 内部往来 / 内部交易：恢复已保存的行（原先不恢复 ⇒ 刷新页面后表空、待生成也空）
    internalRows.arap = Array.isArray(saved.internal_arap?.rows) ? saved.internal_arap.rows : null
    internalRows.trade = Array.isArray(saved.internal_trade?.rows) ? saved.internal_trade.rows : null
    savedSheetKeys.value = new Set(Object.keys(saved))
    // 记录各表版本号（CAS 保存用）
    Object.keys(sheetVersions).forEach((k) => delete sheetVersions[k])
    if (result.versions) {
      Object.assign(sheetVersions, result.versions)
    }
    if (Array.isArray(saved.capital?.rows)) data.capitalReserve = saved.capital.rows
    // G7 建议草稿（只读；由 G7 联动勾选建议写入）
    const draft = saved.g7_suggestions
    g7SuggestionDraft.rows = Array.isArray(draft?.rows) ? draft.rows : []
    g7SuggestionDraft.note = typeof draft?.note === 'string' ? draft.note : ''
    g7SuggestionDraft.importedAt = typeof draft?.imported_at === 'string' ? draft.imported_at : ''
    // 动态股比变动表：按后端返回的 share_change_N 键恢复，不把 3 次写死为业务上限。
    for (const [key, content] of Object.entries(saved)) {
      if (!/^share_change_\d+$/.test(key)) continue
      const rows = content?.rows
      if (Array.isArray(rows)) shareChangeData[key] = rows
    }
  } catch (error: any) {
    if (ticket === worksheetRequestSeq && isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) {
      worksheetLoadState.value = 'error'
      worksheetLoadError.value = error?.message || '工作底稿批量加载失败'
    }
  } finally {
    if (ticket === worksheetRequestSeq && isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) {
      worksheetLoading.value = false
    }
  }
}

/** 推送完成后的统一重载：范围、各工作底稿数据，以及当前抵消分录明细。 */
async function reload() {
  await Promise.all([loadConsolScope(), loadAllData()])
  if (activeSheet.value === 'elimination') await eliminationSheetRef.value?.reload()
}

onMounted(async () => {
  void loadConsolScope()
  eventBus.on('formula-changed', onFormulaChanged)
  // 从后端加载已保存的工作底稿数据
  await loadAllData()
  // Task 6.1: 挂载时刷新 stale 状态（Property 12：失败静默降级）
  void linkageStale.refreshStale()
})
onUnmounted(() => {
  worksheetRequestSeq += 1
  scopeRequestSeq += 1
  eventBus.off('formula-changed', onFormulaChanged)
})

watch([projectId, year], ([nextProjectId, nextYear], previous) => {
  if (nextProjectId === previous?.[0] && nextYear === previous?.[1]) return
  worksheetRequestSeq += 1
  scopeRequestSeq += 1
  resetWorksheetData()
  worksheetLoadState.value = 'empty'
  worksheetLoadError.value = ''
  if (nextProjectId && nextYear) {
    void Promise.all([loadConsolScope(), loadAllData()])
  }
})

async function onFormulaChanged(_payload: FormulaChangedPayload) {
  // 公式变更后重新加载已保存的合并数据（各表持久化值）。
  // 注：按新公式的完整重算需走「一键刷新」（后端 recalc_full）；前端仅重载展示，
  // 不在此处虚假声称"重算"（原实现只 loadConsolScope 却提示"数据同步中"=误导）。
  ElMessage.info('公式已更新，正在重新加载合并数据；如需按新公式重算请使用「一键刷新」')
  await Promise.all([loadConsolScope(), loadAllData()])
}

// ─── 拖拽 ─────────────────────────────────────────────────────────────────────
const navWidth = ref(260)
let rsx = 0, rsw = 0
function startResize(e: MouseEvent) {
  rsx = e.clientX; rsw = navWidth.value
  document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onResize); document.addEventListener('mouseup', stopResize)
}
function onResize(e: MouseEvent) { navWidth.value = Math.max(200, Math.min(400, rsw + (e.clientX - rsx))) }
function stopResize() {
  document.body.style.cursor = ''; document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onResize); document.removeEventListener('mouseup', stopResize)
}

// ─── 默认数据构建 ─────────────────────────────────────────────────────────────
function mkEmptyRow(): SubsidiaryInfoRow {
  return { company_name: '', company_code: '', parent_code: '',
    ultimate_controller: '', ultimate_controller_code: '',
    account_subject: '', accounting_method: '',
    holding_type: '直接', indirect_holder: '', share_changed: '否', change_times: 0, acquisition_date: '', merge_type: '', first_consol_date: '',
    non_common_cost: null, non_common_ratio: null, common_cost: null, common_ratio: null,
    no_consol_cost: null, no_consol_ratio: null, disposal_date: '', disposal_amount: null, disposal_ratio: null,
    pre_disposal_reduce: '', pre_disposal_times: null, post_disposal_reduce: '', post_disposal_times: null }
}

function buildNetAsset(): NetAssetRow[] {
  const r: NetAssetRow[] = []
  const mk = (seq: string, item: string, o: Partial<NetAssetRow> = {}): NetAssetRow =>
    ({ seq, item, total: null, parent: null, values: [], ...o })
  r.push(mk('1', '所有者权益/股东权益', { isHeader: true, bold: true }))
  r.push(mk('', '期初合计：', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1 })))
  r.push(mk('', '本期增加', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1 })))
  r.push(mk('', '本期减少', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1 })))
  r.push(mk('', '期末金额', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1, isComputed: true })))
  r.push(mk('2', '利润及利润分配表', { isHeader: true, bold: true }))
  r.push(mk('', '一、期初金额', { bold: true }))
  r.push(mk('', '二、本年增减变动金额', { bold: true, isComputed: true }))
  r.push(mk('', '（一）综合收益总额', { indent: 1 }))
  r.push(mk('', '其中：当期归母净利润', { indent: 2 }))
  r.push(mk('', '（二）所有者投入和减少资本', { indent: 1, isComputed: true }))
  for (const s of ['2-1所有者投入的普通股','2-2其他权益工具持有者投入资本','2-3股份支付计入所有者权益的金额','2-4其他']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '（三）专项储备提取和使用', { indent: 1, isComputed: true }))
  for (const s of ['3-1提取专项储备','3-2使用专项储备']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '（四）利润分配', { indent: 1, isComputed: true }))
  for (const s of ['4-1提取盈余公积','4-1-1法定公积金','4-1-2任意公积金','4-1-3#储备基金','4-1-4#企业发展基金','4-1-5#利润归还投资','4-2△提取一般风险准备','4-3对所有者（或股东）的分配','4-4其他']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '（五）所有者权益内部结转', { indent: 1, isComputed: true }))
  for (const s of ['5-1资本公积转增资本（或股本）','5-2盈余公积转增资本（或股本）','5-3弥补亏损','5-4 设定受益计划变动额结转留存收益','5-5其他综合收益结转留存收益','5-6其他']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '三、本年年末余额', { bold: true, isComputed: true }))
  r.push(mk('3', '资本公积变动表', { isHeader: true, bold: true }))
  r.push(mk('', '期初金额')); r.push(mk('', '其中：国有独享资本公积', { indent: 1 }))
  r.push(mk('', '本期变动', { isComputed: true }))
  for (const s of ['其中：资本溢价','其他资本公积','国有独享资本公积']) r.push(mk('', s, { indent: 1 }))
  r.push(mk('', '期末金额', { bold: true, isComputed: true }))
  r.push(mk('', '其中：国有独享资本公积', { indent: 1, isComputed: true }))
  return r
}

function buildEquitySim(): EquitySimRow[] {
  const r: EquitySimRow[] = []
  const mk = (seq: string, step: string, dir: string, subj: string, det = '', o: Partial<EquitySimRow> = {}): EquitySimRow =>
    ({ seq, step, direction: dir, subject: subj, detail: det, total: null, values: [], ...o })
  r.push(mk('1','期初长投模拟','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','损益调整')); r.push(mk('','','借','长期股权投资','其他权益变动'))
  r.push(mk('','','贷','年初未分配利润')); r.push(mk('','','贷','资本公积')); r.push(mk('','','贷','其他综合收益'))
  r.push(mk('','','贷','专项储备')); r.push(mk('','','贷','其他权益工具')); r.push(mk('','','贷','△一般风险准备'))
  r.push(mk('2','模拟当期长期股权投资','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','损益调整')); r.push(mk('','','借','长期股权投资','其他权益变动'))
  r.push(mk('','','贷','投资收益')); r.push(mk('','','贷','资本公积')); r.push(mk('','','贷','其他综合收益'))
  r.push(mk('','','贷','专项储备')); r.push(mk('','','贷','其他权益工具')); r.push(mk('','','贷','△一般风险准备'))
  r.push(mk('','','贷','2-3股份支付计入所有者权益的金额','（二）所有者投入和减少资本'))
  r.push(mk('','','贷','2-4其他','（二）所有者投入和减少资本'))
  r.push(mk('','','贷','4-3对所有者的分配','（四）利润分配'))
  r.push(mk('','','贷','4-4其他','（四）利润分配'))
  r.push(mk('3','还原分红影响','','','',{isStep:true}))
  r.push(mk('','','借','投资收益')); r.push(mk('','','贷','长期股权投资','损益调整'))
  r.push(mk('4','股比发生变动对享有净资产的影响','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','损益调整')); r.push(mk('','','借','长期股权投资','其他权益变动'))
  r.push(mk('','','贷','资本公积')); r.push(mk('','','贷','投资收益'))
  r.push(mk('','模拟后期末长期股权投资','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','投资成本')); r.push(mk('','','借','长期股权投资','损益调整'))
  r.push(mk('','','借','长期股权投资','其他权益变动')); r.push(mk('','','借','长期股权投资','资产减值准备'))
  r.push(mk('','','','长期股权投资','小计',{isComputed:true}))
  return r
}

function buildElimEquity(): ElimRow[] {
  const mk = (d: string, s: string, det = ''): ElimRow => ({ direction: d, subject: s, detail: det, values: [] })
  return [mk('借','实收资本（或股本）'),mk('借','其他权益工具'),mk('借','资本公积'),mk('借','减：库存股'),
    mk('借','其他综合收益'),mk('借','专项储备'),mk('借','盈余公积'),mk('借','△一般风险准备'),mk('借','未分配利润'),
    mk('借','商誉'),mk('借','长期股权投资','减值准备'),mk('贷','长期股权投资','投资成本'),
    mk('贷','长期股权投资','损益调整'),mk('贷','长期股权投资','其他权益变动'),mk('贷','少数股东权益')]
}
function buildElimIncome(): ElimRow[] {
  const mk = (d: string, s: string, det = ''): ElimRow => ({ direction: d, subject: s, detail: det, values: [] })
  return [mk('借','年初未分配利润'),mk('借','投资收益'),mk('借','少数股权损益'),
    mk('贷','2-3股份支付计入所有者权益的金额','（二）所有者投入和减少资本'),mk('贷','2-4其他','（二）所有者投入和减少资本'),
    mk('贷','4-1提取盈余公积','（四）利润分配'),mk('贷','4-1-1法定公积金','（四）利润分配'),
    mk('贷','4-1-2任意公积金','（四）利润分配'),mk('贷','4-1-3#储备基金','（四）利润分配'),
    mk('贷','4-1-4#企业发展基金','（四）利润分配'),mk('贷','4-1-5#利润归还投资','（四）利润分配'),
    mk('贷','4-2△提取一般风险准备','（四）利润分配'),mk('贷','4-3对所有者（或股东）的分配','（四）利润分配'),
    mk('贷','4-4其他','（四）利润分配')]
}
function buildCapitalReserve(): CapitalReserveRow[] {
  const mk = (item: string, o: Partial<CapitalReserveRow> = {}): CapitalReserveRow =>
    ({ item, total: null, elimAdj: null, parentVal: null, values: [], ...o })
  return [mk('期初金额',{bold:true}),mk('当期变动',{isComputed:true}),mk('+权益法模拟',{fromElim:true}),
    mk('-合并抵消数',{fromElim:true}),mk('+自身报表变动'),mk('其他'),mk('期末金额',{bold:true,isComputed:true})]
}

// ─── 数据 ─────────────────────────────────────────────────────────────────────
function createDefaultWorksheetData() {
  return {
  subsidiaryInfo: Array.from({ length: 5 }, () => mkEmptyRow()) as SubsidiaryInfoRow[],
  investmentCost: Array.from({ length: 5 }, () => ({
    company_name:'',company_code:'',current_dividend:null,open_ratio:null,open_cost:null,open_impairment:null,open_fv:null,
    add_ratio:null,add_cost:null,add_impairment:null,add_fv:null,reduce_ratio:null,reduce_cost:null,reduce_impairment:null,reduce_fv:null,
  })) as any[],
  investmentEquity: Array.from({ length: 5 }, () => ({
    company_name:'',company_code:'',open_ratio:null,open_amount:null,open_impairment:null,
    add_ratio:null,add_cost:null,add_income_adj:null,add_oci:null,add_other_equity:null,add_other:null,add_impairment:null,
    reduce_ratio:null,reduce_cost:null,reduce_dividend:null,reduce_other:null,reduce_impairment:null,
  })) as any[],
  netAsset: buildNetAsset(),
  equitySimDirect: buildEquitySim(),
  equitySimIndirect: [] as IndirectSection[],
  // 下游抵消后长投 / 投资收益 / 少数股东 / 资本公积表的「抵消」取数骨架（逐企业列）。旧版从合并抵消分录 JSON 恢复，
  // 该恢复从未生效（形状不符）且已删除；分录唯一来源改为 elimination_entries 后这些表的抵消列另行接入（不在本 spec 范围）
  elimEquity: buildElimEquity(),
  elimIncome: buildElimIncome(),
  capitalReserve: buildCapitalReserve(),
  }
}

const data = reactive(createDefaultWorksheetData())

/** 股比变动表本地缓存（按 share_change_N），避免刷新丢失 */
const shareChangeData = reactive<Record<string, any[]>>({})

function resetWorksheetData(options: { clearScope?: boolean; resetView?: boolean } = {}) {
  Object.assign(data, createDefaultWorksheetData())
  for (const key of Object.keys(shareChangeData)) delete shareChangeData[key]
  internalRows.arap = null
  internalRows.trade = null
  savedSheetKeys.value = new Set()
  Object.keys(sheetVersions).forEach((k) => delete sheetVersions[k])
  g7SuggestionDraft.rows = []
  g7SuggestionDraft.note = ''
  g7SuggestionDraft.importedAt = ''
  if (options.clearScope) {
    scopeCompanies.value = []
    rootCompanyCode.value = ''
    treeMode.value = null
  }
  if (options.resetView) {
    g7LinkagePreview.value = null
    g7LinkageVisible.value = false
    activeSheet.value = 'info'
  }
}

// 子企业列：优先从合并范围树获取，降级从基本信息表获取
const companyColumns = computed(() => {
  if (scopeCompanies.value.length) return scopeCompanies.value
  return data.subsidiaryInfo.filter((r: SubsidiaryInfoRow) => r.company_name)
    .map((r: SubsidiaryInfoRow) => ({
      name: r.company_name,
      code: r.company_code,
      ratio: r.non_common_ratio || r.common_ratio || r.no_consol_ratio || 0,
    }))
})

// 间接持股企业列表
const indirectCompanyList = computed(() => {
  return data.subsidiaryInfo
    .filter((r: SubsidiaryInfoRow) => r.holding_type === '间接' && r.company_name)
    .map((r: SubsidiaryInfoRow) => ({
      name: r.company_name, code: r.company_code,
      ratio: r.non_common_ratio || r.common_ratio || r.no_consol_ratio || 0,
      indirectHolder: r.indirect_holder || '',
    }))
})

// 间接持股模拟 sections（computed，从基本信息表动态生成）
const computedIndirectSections = computed(() => {
  if (data.equitySimIndirect.length > 0) return data.equitySimIndirect
  return indirectCompanyList.value.map(c => ({
    companyName: c.name,
    ratio: c.ratio,
    indirectHolder: c.indirectHolder || '',
    rows: buildEquitySim(),
    endLongInvest: 0, endNetAssetShare: 0, difference: 0, diffReason: '',
  }))
})

const elimSummaryForCapital = computed(() => {
  const nn = (v: any) => Number(v) || 0
  const elimRow = data.elimEquity.find((r: ElimRow) => r.subject === '资本公积')
  const elimCapital = elimRow ? (elimRow.values||[]).reduce((s: number, v: number|null) => s + nn(v), 0) : 0
  // 从模拟权益法提取资本公积贷方合计
  let equitySimCapital = 0
  for (const row of data.equitySimDirect) {
    if (row.isStep) continue
    if (row.subject === '资本公积' && row.direction === '贷') {
      equitySimCapital += (row.values || []).reduce((s: number, v: any) => s + nn(v), 0)
    }
  }
  return { elimCapital, equitySimCapital }
})

// ─── 股比变动（内联表，非弹窗） ─────────────────────────────────────────────
const activeShareChangeTimes = computed(() => {
  const m = activeSheet.value.match(/share_change_(\d+)/)
  return m ? Number(m[1]) : 1
})
const activeShareChangeCompanies = computed(() => {
  const times = activeShareChangeTimes.value
  return data.subsidiaryInfo
    .filter((r: SubsidiaryInfoRow) => r.share_changed === '是' && r.change_times === times && r.company_name)
    .map((r: SubsidiaryInfoRow) => ({
      name: r.company_name, code: r.company_code,
      ratio: r.non_common_ratio || r.common_ratio || r.no_consol_ratio || 0,
      accountSubject: r.account_subject, accountingMethod: r.accounting_method,
      holdingType: r.holding_type || '直接',
    }))
})

function onOpenShareChange(_row: SubsidiaryInfoRow, times: number) {
  // 直接切换到对应的股比变动表
  activeSheet.value = `share_change_${times}`
}
function onShareChangeSave(d: any) {
  const key = `share_change_${activeShareChangeTimes.value}`
  shareChangeData[key] = d
  doSave(key, d)
}
async function onSave(sheet: string, payload: any) {
  const keyMap: Record<string, string> = {
    '基本信息表': 'info', '投资明细-成本法': 'cost', '投资明细-权益法': 'equity_inv',
    '净资产表': 'net_asset', '模拟权益法': 'equity_sim',
    '资本公积变动': 'capital', '抵消后长投': 'post_invest', '抵消后投资收益': 'post_income',
    '少数股东权益损益': 'minority', '内部往来抵消': 'internal_arap',
    '内部交易抵消': 'internal_trade', '内部现金流抵消': 'internal_cashflow',
  }
  const key = keyMap[sheet] || sheet
  await doSave(key, payload)
  // 基本信息表保存后刷新合并范围（影响子企业列）
  if (key === 'info') loadConsolScope()
}
async function doSave(sheetKey: string, payload: any) {
  if (!projectId.value) { ElMessage.warning('项目ID缺失'); return }
  try {
    // 传入已知版本号启用 CAS；首次保存用 0（首次创建语义，后端验证当前不存在）。
    const currentVersion = sheetVersions[sheetKey] ?? 0
    const result = await saveWorksheetData(
      projectId.value, year.value, sheetKey, { rows: payload }, currentVersion,
    )
    if (!result.ok) {
      ElMessage.error(`${sheetKey} 保存失败，请检查后端服务`)
      return
    }
    // 更新本地版本号，下次保存用新版本做 CAS
    sheetVersions[sheetKey] = result.version
    // 已保存 ⇒ 该表数据已知，生成草稿分录时由它负责（其中不再产出的来源键可删草稿）
    savedSheetKeys.value = new Set([...savedSheetKeys.value, sheetKey])
    ElMessage.success(`${sheetKey} 已保存`)
  } catch (err: any) {
    if (err instanceof WorksheetVersionConflictError) {
      ElMessage.warning('工作底稿已被其他操作修改，正在重新加载……')
      await loadAllData()
      return
    }
    handleApiError(err, `${sheetKey} 保存`)
  }
}

// ─── 合并工作底稿导入导出（Phase 1：前端 useExcelIO 统一） ──────────────────
const { exportTemplate: _ioExportTemplate, exportData: _ioExportData, onFileSelected: _ioOnFileSelected } = useExcelIO()
const importFileRef = ref<HTMLInputElement | null>(null)

/** 当前 activeSheet 是否支持导入导出 */
const canImportExport = computed(() => {
  if (activeSheet.value in CONSOL_SHEET_COLS) return true
  // 动态股比变动表 share_change_1, share_change_2... 统一用 share_change 列定义
  if (activeSheet.value.startsWith('share_change_')) return true
  return false
})

/** 当前 sheet 的中文名 */
const activeSheetLabel = computed(() => {
  const map: Record<string, string> = {
    info: '基本信息表', cost: '投资明细-成本法', equity_inv: '投资明细-权益法',
    net_asset: '净资产表', equity_sim: '模拟权益法', capital: '资本公积变动',
    post_invest: '抵消后长投', post_income: '抵消后投资收益', minority: '少数股东权益损益',
    internal_arap: '内部往来抵消', internal_trade: '内部交易抵消',
    internal_cashflow: '内部现金流抵消', elimination: '合并抵消分录', share_change: '股比变动表',
  }
  return map[activeSheet.value] || activeSheet.value
})

async function handleExportTemplate() {
  const colKey = activeSheet.value.startsWith('share_change_') ? 'share_change' : activeSheet.value
  const cols = CONSOL_SHEET_COLS[colKey]
  if (!cols) return
  await _ioExportTemplate({
    columns: cols,
    fileName: `合并底稿_${activeSheetLabel.value}_模板.xlsx`,
    includeNoteRow: false,
  })
}

async function handleExportData() {
  const colKey = activeSheet.value.startsWith('share_change_') ? 'share_change' : activeSheet.value
  const cols = CONSOL_SHEET_COLS[colKey]
  if (!cols) return
  if (!projectId.value || !year.value) {
    ElMessage.warning('工作底稿上下文未就绪，无法导出')
    return
  }
  // 从后端加载当前 sheet 数据
  const result = await loadWorksheetData(projectId.value, year.value, activeSheet.value)
  if (result.status === 'error') {
    ElMessage.error(result.errorMessage || '工作底稿加载失败，无法导出')
    return
  }
  const rows = Array.isArray(result.data.rows) ? result.data.rows : []
  if (!rows.length) {
    ElMessage.info('当前表暂无数据可导出')
    return
  }
  await _ioExportData({
    data: rows,
    columns: cols,
    sheetName: activeSheetLabel.value,
    fileName: `合并底稿_${activeSheetLabel.value}_数据.xlsx`,
  })
}

function handleImportClick() {
  importFileRef.value?.click()
}

async function handleImportFile(e: Event) {
  const colKey = activeSheet.value.startsWith('share_change_') ? 'share_change' : activeSheet.value
  const cols = CONSOL_SHEET_COLS[colKey]
  if (!cols) return
  await _ioOnFileSelected(e, async (result) => {
    if (!result.rows.length) {
      ElMessage.warning('未识别到有效数据行')
      return
    }
    // 将 Excel 行映射为目标 JSON 格式（按 header→key 映射）
    const headerToKey: Record<string, string> = {}
    for (const col of cols) headerToKey[col.header] = col.key

    const mapped = result.rows.map((raw: Record<string, any>) => {
      const row: Record<string, any> = {}
      for (const [header, key] of Object.entries(headerToKey)) {
        if (raw[header] != null) row[key] = raw[header]
      }
      return row
    }).filter((r: Record<string, any>) => Object.keys(r).length > 0)

    if (!mapped.length) {
      ElMessage.warning('导入数据为空，请检查列头是否匹配')
      return
    }

    // 保存到后端
    try {
      const currentVersion = sheetVersions[activeSheet.value] ?? 0
      const saveResult = await saveWorksheetData(projectId.value, year.value, activeSheet.value, { rows: mapped }, currentVersion)
      sheetVersions[activeSheet.value] = saveResult.version
      ElMessage.success(`已导入 ${mapped.length} 行到「${activeSheetLabel.value}」`)
      // 触发前端数据刷新
      await loadAllData()
    } catch (error: any) {
      handleApiError(error, '导入保存')
    }
  }, { skipRows: 0 })
  // 重置 file input
  if (importFileRef.value) importFileRef.value.value = ''
}

// ─── 合并抵消分录明细表的待生成分组（spec consol-elimination-single-source-push 任务 10.2）──────
// 内部往来 / 内部交易的行：已保存的从后端恢复，表打开后随编辑更新（rows-changed）；
// 模拟权益法直接取 data.equitySimDirect。三张表的计算与各表底部预览同一函数（elimSourceGroups）。
// 内部现金流没有会计科目，不生成分录。
const internalRows = reactive<{ arap: any[] | null; trade: any[] | null }>({ arap: null, trade: null })
/** 已保存过数据的表（sheet_key）：这些来源的数据已知，生成时由明细表声明负责 */
const savedSheetKeys = ref<Set<string>>(new Set())
/** 每个 sheet_key 当前已知的后端版本号（加载/保存后更新），用于 CAS 保存。 */
const sheetVersions = reactive<Record<string, number>>({})

const sourceGroupsByOriginMap = computed(() => sourceGroupsByOrigin({
  equitySimRows: data.equitySimDirect,
  arapRows: internalRows.arap || [],
  tradeRows: internalRows.trade || [],
  companies: companyColumns.value,
  rootCode: rootCompanyCode.value,
}))
const sourceGroups = computed(() => WORKSHEET_ORIGINS.flatMap((o) => sourceGroupsByOriginMap.value[o]))
const sourceOrigins = computed(() => declaredOrigins(sourceGroupsByOriginMap.value, savedSheetKeys.value))

// ─── 公式 / 跨表导航统一接线（acnr-consumer-wiring Req 20.5/20.6/20.7, task 31.3）──
// 单一父级接线点：所有 ~15 个子 worksheet 的 `open-formula` 事件都绑定到此处，
// 经 EventBus `open-formula-manager` → ThreeColumnLayout 顶层挂载的全局
// FormulaManagerDialog → FormulaEditDialog（已于 task 18.3 迁移到 ACNR：
// useAcnr().listSheets/listCells + mapAcnrCellsToPickerRows）。
// 因此「一处接线惠及全部 worksheet」：子组件无需各自接 ACNR picker。
// miss/picker 不可用时由 FormulaEditDialog 内部回退 legacy 地址注册表（Req 20.7 无回归）。
function onOpenFormula(sheetKey: string) {
  eventBus.emit('open-formula-manager', {
    nodeKey: `consol_${sheetKey}`,
    scope: 'consol_worksheet',
    projectId: projectId.value,
    year: year.value,
    sheetName: sheetKey,
  })
}

// `goto-sheet`：合并工作底稿模块内部的表样切换（如 elimination→net_asset），
// 目标为本模块内的本地 sheet key（非跨底稿 wp_code），按 Req 20.5 合并模块内
// 跳转合法保持本地切换；真正的跨底稿跳转由 GtIndexChip / ACNR resolve 承载
// （本模块 worksheet 未产生跨底稿目标）。
function onGotoSheet(k: string) {
  activeSheet.value = k
}

defineExpose({ reload, activeSheet })
</script>

<style scoped>
.cw-layout { display: flex; height: calc(100vh - 120px); overflow: hidden; margin: -16px; }
.cw-nav {
  flex-shrink: 0; background: var(--gt-color-bg); border-right: 1px solid var(--gt-color-border-light, #e8e4f0);
  display: flex; flex-direction: column; overflow: hidden;
}
.cw-nav-header {
  padding: 16px 16px 12px; border-bottom: 1px solid var(--gt-color-border-light, #e8e4f0); flex-shrink: 0;
}
.cw-nav-title { font-size: var(--gt-font-size-base); font-weight: 700; color: var(--gt-color-text-primary); }
.cw-nav-list { flex: 1; overflow-y: auto; padding: 8px; }
.cw-nav-item {
  display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px 8px 18px; margin: 1px 6px;
  border-radius: 6px; cursor: pointer; transition: all 0.15s;
}
.cw-nav-item:hover { background: rgba(75,45,119,0.04); }
.cw-nav-item--active {
  background: var(--gt-color-primary-bg, #f0edf5) !important;
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
.cw-nav-item--active .cw-nav-item-label { color: var(--gt-color-primary, #4b2d77); font-weight: 600; }
.cw-nav-item-text { flex: 1; min-width: 0; }
.cw-nav-item-label { display: block; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-primary); line-height: 1.4; }
.cw-nav-item-desc { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 2px; }
.cw-nav-group {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; margin: 6px 6px 2px; cursor: pointer;
  background: linear-gradient(135deg, #f0edf5, #e8e4f0); border-radius: 6px;
  user-select: none; transition: background 0.15s;
}
.cw-nav-group:hover { background: linear-gradient(135deg, #e8e4f0, #ddd8e8); }
.cw-nav-group:first-child { margin-top: 2px; }
.cw-nav-group-left { display: flex; align-items: center; gap: 8px; }
.cw-nav-group-num {
  width: 20px; height: 20px; border-radius: 50%; background: var(--gt-color-primary); color: var(--gt-color-text-inverse);
  font-size: var(--gt-font-size-xs); font-weight: 700; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.cw-nav-group-label { font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-text-primary); }
.cw-nav-group-right { display: flex; align-items: center; gap: 6px; }
.cw-nav-group-count { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.cw-nav-group-arrow { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); font-weight: 700; transition: transform 0.15s; }
.cw-resizer {
  width: 4px; cursor: col-resize; background: transparent; flex-shrink: 0;
  transition: background 0.15s;
}
.cw-resizer:hover, .cw-resizer:active { background: var(--gt-color-primary-lighter, #d8d0e8); }
.cw-content { flex: 1; min-width: 0; overflow: auto; padding: 16px; background: var(--gt-color-bg-white); }
.cw-ie-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed var(--gt-color-border-light, #e8e4f0); }
.g7-linkage-summary { margin-bottom: 12px; }
.g7-linkage-note { margin-bottom: 14px; }
.g7-linkage-mapping { margin-top: 14px; }
.g7-linkage-title { margin-bottom: 8px; font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary); display: flex; align-items: center; gap: 8px; }
.g7-linkage-options { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--gt-color-border-light, #e8e4f0); }
</style>
