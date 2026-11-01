<template>
  <div class="cw-layout" :class="{ 'cw-layout--readonly': contentBlocked }" :data-load-status="worksheetLoadState">
    <el-alert
      v-if="worksheetLoadState === 'error'"
      type="error"
      :closable="false"
      show-icon
      class="cw-load-error"
      data-testid="cw-load-error"
      :title="worksheetLoadError || '合并工作底稿加载失败，请稍后重试'"
      :description="hasHydratedData ? '已保留上次成功加载的数据；重新读取成功前暂不可编辑。' : '未加载到可编辑数据。'"
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
    <el-alert
      v-if="readonlyReason"
      type="warning"
      :closable="false"
      show-icon
      class="cw-readonly-state"
      data-testid="cw-readonly-state"
      :title="readonlyReason"
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
              @click="requestSheetChange(sheet.key)">
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
    <main
      class="cw-content"
      v-loading="worksheetLoading && hasHydratedData"
      :inert="contentBlocked || undefined"
      :aria-busy="worksheetLoading"
    >
      <el-skeleton v-if="worksheetLoading && !hasHydratedData" :rows="10" animated data-testid="cw-loading-skeleton" />
      <el-empty v-else-if="!hasHydratedData" description="工作底稿尚未成功加载" data-testid="cw-unavailable-state" />
      <template v-else>
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
        <span v-if="worksheetSaving" class="cw-save-state">正在保存…</span>
        <span v-else-if="worksheetDrafts.hasDirty.value" class="cw-save-state cw-save-state--dirty">有未保存修改</span>
      </div>
      <SubsidiaryInfoSheet v-if="activeSheet === 'info'" :model-value="data.subsidiaryInfo" :tree-codes="treeInfoCodes"
        @update:model-value="onModelDraft('info', 'subsidiaryInfo', $event)"
        @save="onSheetSave('info', $event)" @open-share-change="onOpenShareChange" @open-formula="onOpenFormula" />
      <InvestmentCostSheet v-else-if="activeSheet === 'cost'" :model-value="data.investmentCost"
        @update:model-value="onModelDraft('cost', 'investmentCost', $event)"
        @save="onSheetSave('cost', $event)" @open-formula="onOpenFormula" />
      <InvestmentEquitySheet v-else-if="activeSheet === 'equity_inv'" :model-value="data.investmentEquity"
        @update:model-value="onModelDraft('equity_inv', 'investmentEquity', $event)"
        @save="onSheetSave('equity_inv', $event)" @open-formula="onOpenFormula" />
      <NetAssetSheet v-else-if="activeSheet === 'net_asset'" :companies="companyColumns" :model-value="data.netAsset"
        @update:model-value="onModelDraft('net_asset', 'netAsset', $event)"
        @save="onSheetSave('net_asset', $event)" @open-formula="onOpenFormula"
        @restore-defaults="restoreNetAssetDefaults" />
      <EquitySimSheet v-else-if="activeSheet === 'equity_sim'" :companies="companyColumns"
        :direct-rows="data.equitySimDirect" :indirect-sections="computedIndirectSections"
        :net-asset-data="data.netAsset"
        @draft-change="onSheetDraft('equity_sim', $event)"
        @save="onSheetSave('equity_sim', $event)" @open-formula="onOpenFormula" />
      <!-- 草稿分组由服务端按已保存工作表和版本向量重算，浏览器不再提交权威 groups。 -->
      <EliminationSheet v-else-if="activeSheet === 'elimination'" ref="eliminationSheetRef" :project-id="projectId" :year="year"
        :source-sheet-keys="serverSourceSheetKeys" :source-versions="serverSourceVersions"
        @open-formula="onOpenFormula" @goto-sheet="onGotoSheet" />
      <CapitalReserveSheet v-else-if="activeSheet === 'capital'" :companies="companyColumns"
        :model-value="data.capitalReserve" :elimination-data="elimSummaryForCapital"
        :initial-adjustment-items="capitalAdjustmentItems"
        :initial-consol-report-amount="capitalConsolReportAmount"
        @update:model-value="onCapitalRowsUpdate"
        @draft-change="onSheetDraft('capital', $event)"
        @save="onSheetSave('capital', $event)" @open-formula="onOpenFormula" />
      <!-- 动态股比变动表 -->
      <ShareChangeSheet v-else-if="activeSheet.startsWith('share_change_')"
        :key="activeSheet"
        :change-times="activeShareChangeTimes"
        :companies="activeShareChangeCompanies"
        :all-companies="companyColumns"
        :indirect-companies="indirectCompanyList"
        :initial-data="shareChangeData[activeSheet] || []"
        @draft-change="onSheetDraft(activeSheet, $event)"
        @save="onSheetSave(activeSheet, $event)" @open-formula="onOpenFormula" />
      <!-- 汇总计算表 -->
      <PostElimInvestSheet v-else-if="activeSheet === 'post_invest'"
        :companies="companyColumns" :investment-cost="data.investmentCost"
        :investment-equity="data.investmentEquity" :equity-sim-direct="data.equitySimDirect"
        :projection="postElimProjection" :initial-rows="postInvestRows"
        @draft-change="onSheetDraft('post_invest', $event)" @save="onSheetSave('post_invest', $event)"
        @open-formula="onOpenFormula" @goto-sheet="onGotoSheet" />
      <PostElimIncomeSheet v-else-if="activeSheet === 'post_income'"
        :companies="companyColumns" :investment-cost="data.investmentCost"
        :equity-sim-direct="data.equitySimDirect" :projection="postElimProjection"
        :initial-rows="postIncomeRows" @draft-change="onSheetDraft('post_income', $event)"
        @save="onSheetSave('post_income', $event)"
        @goto-sheet="onGotoSheet" @open-formula="onOpenFormula" />
      <MinorityInterestSheet v-else-if="activeSheet === 'minority'"
        :companies="companyColumns" :net-asset-data="data.netAsset"
        :equity-sim-direct="data.equitySimDirect" :projection="postElimProjection"
        :initial-rows="minorityRows"
        @draft-change="onSheetDraft('minority', $event)" @save="onSheetSave('minority', $event)"
        @goto-sheet="onGotoSheet" @open-formula="onOpenFormula" />
      <!-- 内部抵消表 -->
      <InternalArApSheet v-else-if="activeSheet === 'internal_arap'"
        :companies="companyColumns" :initial-rows="internalRows.arap"
        @save="onSheetSave('internal_arap', $event)" @open-formula="onOpenFormula"
        @rows-changed="onInternalRowsChanged('internal_arap', $event)" />
      <InternalTradeSheet v-else-if="activeSheet === 'internal_trade'"
        :companies="companyColumns" :initial-rows="internalRows.trade"
        @save="onSheetSave('internal_trade', $event)" @open-formula="onOpenFormula"
        @rows-changed="onInternalRowsChanged('internal_trade', $event)" />
      <!-- 内部现金流没有会计科目（属现金流量表工作底稿），不生成抵销分录 -->
      <InternalCashFlowSheet v-else-if="activeSheet === 'internal_cashflow'"
        :companies="companyColumns" :initial-rows="internalCashflowRows"
        @draft-change="onSheetDraft('internal_cashflow', $event)"
        @save="onSheetSave('internal_cashflow', $event)" @open-formula="onOpenFormula" />
      <!-- G7 建议草稿（只读；由 G7 联动勾选建议后写入，不参与合并计算） -->
      <G7SuggestionDraftSheet v-else-if="activeSheet === 'g7_suggestions'"
        :rows="g7SuggestionDraft.rows" :note="g7SuggestionDraft.note"
        :imported-at="g7SuggestionDraft.importedAt"
        @goto-sheet="onGotoSheet" @refresh="loadAllData" />
      <!-- 分录汇总表（只读；与合并试算同一计算口径，每次进入都重读） -->
      <EntrySummarySheet v-else-if="activeSheet === 'entry_summary'" ref="entrySummarySheetRef"
        :project-id="projectId" :year="year" @goto-sheet="onGotoSheet" />
      </template>
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
import { ref, computed, reactive, markRaw, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { List, Coin, TrendCharts, DataBoard, SetUp, Tickets, PieChart } from '@element-plus/icons-vue'
import {
  getWorksheetTree,
  getPostEliminationProjection,
  POST_ELIM_ACCOUNT,
  type PostEliminationProjection,
} from '@/services/consolidationApi'
import {
  alignInfoRows,
  mergeImportedInfoRows,
  treeMemberInfos,
  worksheetCompanyColumns,
  type TreeMemberInfo,
} from '@/components/consolidation/composables/consolSubsidiaryInfo'
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
import EntrySummarySheet from './EntrySummarySheet.vue'
import { eventBus } from '@/utils/eventBus'
import type { FormulaChangedPayload } from '@/utils/eventBus'
import { handleApiError } from '@/utils/errorHandler'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'
import { useConsolWorkspaceGuard } from '@/components/consolidation/composables/useConsolWorkspaceGuard'
import { useConsolWorksheetDrafts } from '@/components/consolidation/composables/useConsolWorksheetDrafts'
import { clonePlain } from '@/utils/cloneable'

interface ConsolWorksheetTabsProps {
  projectId: string
  year: number
  consolMode?: string | null
  isRootSelection?: boolean
  readonlyReason?: string
}

const props = withDefaults(defineProps<ConsolWorksheetTabsProps>(), {
  consolMode: null,
  isRootSelection: false,
  readonlyReason: '',
})

const projectId = computed(() => props.projectId)
const year = computed(() => props.year)

type WorksheetViewLoadStatus = WorksheetLoadStatus | 'loading'
const worksheetLoadState = ref<WorksheetViewLoadStatus>('loading')
const worksheetLoadError = ref('')
const worksheetLoading = ref(false)
const hasHydratedData = ref(false)
const draftsReady = ref(false)
const contentBlocked = computed(() => (
  !hasHydratedData.value
  || worksheetLoading.value
  || worksheetLoadState.value === 'error'
  || Boolean(props.readonlyReason)
))
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
  { key: 'entry_summary', label: '分录汇总表', desc: '按类型汇总借贷净额·与差额表对账', icon: markRaw(DataBoard), tag: '汇总', tagType: 'info' as const },
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
    sheets: sheetList.value.filter(s => ['elimination', 'entry_summary', 'capital', 'g7_suggestions'].includes(s.key)),
  },
  {
    key: 'g6', label: '汇总核查', step: '✓',
    collapsed: groupCollapsed.g6,
    sheets: sheetList.value.filter(s => ['post_invest', 'post_income', 'minority'].includes(s.key)),
  },
])

const activeSheet = ref('info')
const eliminationSheetRef = ref<InstanceType<typeof EliminationSheet> | null>(null)
const entrySummarySheetRef = ref<InstanceType<typeof EntrySummarySheet> | null>(null)
const workspaceGuard = useConsolWorkspaceGuard()
const worksheetDrafts = useConsolWorksheetDrafts()
const worksheetSaving = ref(false)
const postInvestRows = ref<any[]>([])
const postIncomeRows = ref<any[]>([])
const minorityRows = ref<any[]>([])
// 四张抵销后表的服务端 canonical projection（抵消分录数唯一真源，batch 3 / ADR-CRW-004）。
// 加载失败保留上一次结果（不清空成空态）；按 worksheetRequestSeq 防切项目/年度串数。
const postElimProjection = ref<PostEliminationProjection | null>(null)
const internalCashflowRows = ref<any[] | null>(null)
const capitalAdjustmentItems = ref<Array<{ description: string; amount: number | null }>>([])
const capitalConsolReportAmount = ref<number | null>(null)
let unregisterWorkspaceDraft: (() => void) | null = null
let worksheetSaveInFlight: Promise<boolean> | null = null

// ─── 从合并范围加载子企业列表 ────────────────────────────────────────────────
// 项目和年度由父页提供，确保工作底稿与左树/报表使用同一年度上下文。

// ─── G7 联动 stale 常驻提示（Task 6.1；失败静默降级 Property 12） ────────────
const linkageStale = useG7ConsolLinkageEntry(projectId, year)

/** 企业树带出的基本信息表成员（spec consol-autotree-linkage-closure R4）；null = 企业树不可用（手工维护） */
const treeInfoMembers = ref<TreeMemberInfo[] | null>(null)
const treeInfoCodes = computed(() => treeInfoMembers.value?.map((m) => m.company_code) ?? null)
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
  // 企业树：合并方式识别 + 基本信息表企业清单 / 各表企业列（只以企业树为准，不再被合并范围表覆盖，R4.4）
  try {
    const res = await getWorksheetTree(projectSnapshot)
    if (ticket !== scopeRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return
    treeMode.value = res?.mode ?? null
    treeInfoMembers.value = res?.tree ? treeMemberInfos(res.tree) : null
    // 本合并项目的企业代码：工作底稿里的「母公司」= 它（交易方留痕与归属预填用）
    rootCompanyCode.value = res?.tree?.company_code || ''
  } catch {
    if (ticket !== scopeRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return
    treeMode.value = null
    // 企业树读取失败：首次加载保持手工维护（null）；已带出过则沿用上次的企业清单，不因一次失败解锁三码
  }
  alignSubsidiaryInfo()
}

/** 基本信息表按企业树对齐（树或已保存数据先到都行：对齐是幂等的）；企业树不可用时保持手工维护 */
function alignSubsidiaryInfo() {
  if (!treeInfoMembers.value) return
  data.subsidiaryInfo = alignInfoRows(data.subsidiaryInfo, treeInfoMembers.value, mkEmptyRow)
}

async function loadAllData() {
  const projectSnapshot = projectId.value
  const yearSnapshot = year.value
  if (!projectSnapshot || !yearSnapshot) return
  const ticket = ++worksheetRequestSeq
  worksheetLoading.value = true
  draftsReady.value = false
  if (!hasHydratedData.value) worksheetLoadState.value = 'loading'
  try {
    const result = await loadAllWorksheetData(projectSnapshot, yearSnapshot)
    if (ticket !== worksheetRequestSeq || !isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) return

    if (result.status === 'error') {
      // 同一上下文重载失败时保留已展示数据，避免网络抖动把有效表格清空。
      worksheetLoadState.value = 'error'
      worksheetLoadError.value = result.errorMessage || '工作底稿批量加载失败'
      draftsReady.value = hasHydratedData.value
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
    // 旧版 elimination JSON 不恢复：正式分录唯一来源仍是 elimination_entries。
    internalRows.arap = Array.isArray(saved.internal_arap?.rows) ? saved.internal_arap.rows : null
    internalRows.trade = Array.isArray(saved.internal_trade?.rows) ? saved.internal_trade.rows : null
    internalCashflowRows.value = Array.isArray(saved.internal_cashflow?.rows) ? saved.internal_cashflow.rows : null
    postInvestRows.value = Array.isArray(saved.post_invest?.rows) ? saved.post_invest.rows : []
    postIncomeRows.value = Array.isArray(saved.post_income?.rows) ? saved.post_income.rows : []
    minorityRows.value = Array.isArray(saved.minority?.rows) ? saved.minority.rows : []
    savedSheetKeys.value = new Set(Object.keys(saved))
    Object.keys(sheetVersions).forEach((key) => delete sheetVersions[key])
    Object.assign(sheetVersions, result.versions || {})

    const capital = savedPayload('capital', saved.capital) as CapitalDraftPayload
    if (capital.rows.length) data.capitalReserve = capital.rows
    capitalAdjustmentItems.value = capital.adjustment_items
    capitalConsolReportAmount.value = capital.consol_report_amount

    const draft = saved.g7_suggestions
    g7SuggestionDraft.rows = Array.isArray(draft?.rows) ? draft.rows : []
    g7SuggestionDraft.note = typeof draft?.note === 'string' ? draft.note : ''
    g7SuggestionDraft.importedAt = typeof draft?.imported_at === 'string' ? draft.imported_at : ''
    for (const [key, content] of Object.entries(saved)) {
      if (/^share_change_\d+$/.test(key) && Array.isArray(content?.rows)) {
        shareChangeData[key] = content.rows
      }
    }
    alignSubsidiaryInfo()
    hasHydratedData.value = true
    await nextTick()
    primeWorksheetDrafts(saved)
    draftsReady.value = true
    // 四表抵销 canonical projection 另行取数（失败保留上次，不阻断底稿加载）
    void loadPostElimProjection(projectSnapshot, yearSnapshot, ticket)
  } catch (error: any) {
    if (ticket === worksheetRequestSeq && isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) {
      worksheetLoadState.value = 'error'
      worksheetLoadError.value = error?.message || '工作底稿批量加载失败'
      draftsReady.value = hasHydratedData.value
    }
  } finally {
    if (ticket === worksheetRequestSeq && isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) {
      worksheetLoading.value = false
    }
  }
}

/** 取四表抵销 canonical projection。按 ticket 防切项目/年度串数；失败保留上次结果（不清空）。 */
async function loadPostElimProjection(
  projectSnapshot: string, yearSnapshot: number, ticket: number,
) {
  try {
    const projection = await getPostEliminationProjection(projectSnapshot, yearSnapshot, { silent: true })
    if (ticket === worksheetRequestSeq && isWorksheetContextCurrent(projectSnapshot, yearSnapshot)) {
      postElimProjection.value = projection
    }
  } catch {
    // 非合并项目 / 暂无数据：保留上次结果，四表抵销列显示为缺来源（由组件兜底展示 0）
  }
}

/** 推送完成后的统一重载：先处理未保存草稿，再重读范围、底稿数据和当前只读明细。 */
async function reloadNow() {
  await Promise.all([loadConsolScope(), loadAllData()])
  if (activeSheet.value === 'elimination') await eliminationSheetRef.value?.reload()
  else if (activeSheet.value === 'entry_summary') await entrySummarySheetRef.value?.load()
}

async function reload(): Promise<boolean> {
  if (!workspaceGuard) {
    await reloadNow()
    return true
  }
  return workspaceGuard.runTransition(
    '重新读取合并工作底稿前，请处理未保存修改。',
    reloadNow,
    ['consol-worksheets'],
  )
}

onMounted(async () => {
  unregisterWorkspaceDraft = workspaceGuard?.register({
    id: 'consol-worksheets',
    label: () => `合并工作底稿·${sheetLabel(activeSheet.value)}`,
    contextKey: () => `${projectId.value}:${year.value}:${activeSheet.value}`,
    isDirty: () => worksheetDrafts.hasDirty.value,
    isSaving: () => worksheetSaving.value,
    save: savePendingWorksheetDrafts,
    discard: discardPendingWorksheetDrafts,
  }) || null
  void loadConsolScope()
  eventBus.on('formula-changed', onFormulaChanged)
  await loadAllData()
  void linkageStale.refreshStale()
})
onUnmounted(() => {
  worksheetRequestSeq += 1
  scopeRequestSeq += 1
  unregisterWorkspaceDraft?.()
  unregisterWorkspaceDraft = null
  eventBus.off('formula-changed', onFormulaChanged)
})

watch([projectId, year], ([nextProjectId, nextYear], previous) => {
  if (nextProjectId === previous?.[0] && nextYear === previous?.[1]) return
  worksheetRequestSeq += 1
  scopeRequestSeq += 1
  draftsReady.value = false
  hasHydratedData.value = false
  worksheetDrafts.clear()
  resetWorksheetData()
  postElimProjection.value = null  // 切项目/年度清空抵销投影，避免显示上一个项目的数
  worksheetLoadState.value = 'loading'
  worksheetLoadError.value = ''
  workspaceGuard?.notifyStateChange()
  if (nextProjectId && nextYear) {
    void Promise.all([loadConsolScope(), loadAllData()])
  }
})

async function onFormulaChanged(_payload: FormulaChangedPayload) {
  const reloadAfterFormula = async () => {
    ElMessage.info('公式已更新，正在重新读取已保存的合并数据；按新公式计算仍请使用“更新合并结果”')
    await reloadNow()
  }
  if (workspaceGuard) {
    await workspaceGuard.runTransition(
      '公式已变化，重新读取工作底稿前请处理未保存修改。',
      reloadAfterFormula,
      ['consol-worksheets'],
    )
  } else {
    await reloadAfterFormula()
  }
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
  // 四张抵销后表的「抵消」列不再用前端空骨架：改读服务端 canonical projection（approved 分录真源，
  // batch 3 / ADR-CRW-004），见 postElimProjection + consolPostElimView。
  capitalReserve: buildCapitalReserve(),
  }
}

const data = reactive(createDefaultWorksheetData())

/** 股比变动表本地缓存（按 share_change_N），避免刷新丢失 */
const shareChangeData = reactive<Record<string, any[]>>({})

type WorksheetModelKey = 'subsidiaryInfo' | 'investmentCost' | 'investmentEquity' | 'netAsset'
type CapitalDraftPayload = {
  rows: CapitalReserveRow[]
  adjustment_items: Array<{ description: string; amount: number | null }>
  consol_report_amount: number | null
}

function savedPayload(sheetKey: string, content: Record<string, any> | undefined): unknown {
  if (sheetKey === 'capital') {
    return {
      rows: Array.isArray(content?.rows) ? content.rows : [],
      adjustment_items: Array.isArray(content?.adjustment_items) ? content.adjustment_items : [],
      consol_report_amount: content?.consol_report_amount ?? null,
    } satisfies CapitalDraftPayload
  }
  return content?.rows
}

function currentPayload(sheetKey: string): unknown {
  if (sheetKey === 'info') return data.subsidiaryInfo
  if (sheetKey === 'cost') return data.investmentCost
  if (sheetKey === 'equity_inv') return data.investmentEquity
  if (sheetKey === 'net_asset') return data.netAsset
  if (sheetKey === 'equity_sim') return { direct: data.equitySimDirect, indirect: data.equitySimIndirect }
  if (sheetKey === 'capital') return {
    rows: data.capitalReserve,
    adjustment_items: capitalAdjustmentItems.value,
    consol_report_amount: capitalConsolReportAmount.value,
  } satisfies CapitalDraftPayload
  if (sheetKey === 'post_invest') return postInvestRows.value
  if (sheetKey === 'post_income') return postIncomeRows.value
  if (sheetKey === 'minority') return minorityRows.value
  if (sheetKey === 'internal_arap') return internalRows.arap || []
  if (sheetKey === 'internal_trade') return internalRows.trade || []
  if (sheetKey === 'internal_cashflow') return internalCashflowRows.value || []
  if (sheetKey.startsWith('share_change_')) return shareChangeData[sheetKey] || []
  return undefined
}

function applyPayloadToState(sheetKey: string, payload: any): void {
  const value = clonePlain(payload)
  if (sheetKey === 'info') data.subsidiaryInfo = Array.isArray(value) ? value : []
  else if (sheetKey === 'cost') data.investmentCost = Array.isArray(value) ? value : []
  else if (sheetKey === 'equity_inv') data.investmentEquity = Array.isArray(value) ? value : []
  else if (sheetKey === 'net_asset') data.netAsset = Array.isArray(value) ? value : []
  else if (sheetKey === 'equity_sim') {
    data.equitySimDirect = Array.isArray(value?.direct) ? value.direct : []
    data.equitySimIndirect = Array.isArray(value?.indirect) ? value.indirect : []
  } else if (sheetKey === 'capital') {
    data.capitalReserve = Array.isArray(value?.rows) ? value.rows : []
    capitalAdjustmentItems.value = Array.isArray(value?.adjustment_items) ? value.adjustment_items : []
    capitalConsolReportAmount.value = value?.consol_report_amount ?? null
  } else if (sheetKey === 'post_invest') postInvestRows.value = Array.isArray(value) ? value : []
  else if (sheetKey === 'post_income') postIncomeRows.value = Array.isArray(value) ? value : []
  else if (sheetKey === 'minority') minorityRows.value = Array.isArray(value) ? value : []
  else if (sheetKey === 'internal_arap') internalRows.arap = Array.isArray(value) ? value : []
  else if (sheetKey === 'internal_trade') internalRows.trade = Array.isArray(value) ? value : []
  else if (sheetKey === 'internal_cashflow') internalCashflowRows.value = Array.isArray(value) ? value : []
  else if (sheetKey.startsWith('share_change_')) shareChangeData[sheetKey] = Array.isArray(value) ? value : []
}

function contentForSave(sheetKey: string, payload: any): Record<string, any> {
  if (sheetKey === 'capital' && payload && !Array.isArray(payload)) return payload
  return { rows: payload }
}

function onSheetDraft(sheetKey: string, payload: unknown): void {
  if (!draftsReady.value || contentBlocked.value) return
  worksheetDrafts.update(sheetKey, payload)
  workspaceGuard?.notifyStateChange()
}

function onModelDraft(sheetKey: string, modelKey: WorksheetModelKey, payload: any[]): void {
  data[modelKey] = payload as never
  onSheetDraft(sheetKey, payload)
}

function onCapitalRowsUpdate(rows: CapitalReserveRow[]): void {
  data.capitalReserve = rows
}

function onInternalRowsChanged(sheetKey: 'internal_arap' | 'internal_trade', rows: any[]): void {
  if (sheetKey === 'internal_arap') internalRows.arap = rows
  else internalRows.trade = rows
  onSheetDraft(sheetKey, rows)
}

function restoreNetAssetDefaults(): void {
  const rows = buildNetAsset()
  data.netAsset = rows
  onSheetDraft('net_asset', rows)
}

function primeWorksheetDrafts(saved: Record<string, Record<string, any>>): void {
  worksheetDrafts.clear()
  const keys = new Set([
    'info', 'cost', 'equity_inv', 'net_asset', 'equity_sim', 'capital',
    'post_invest', 'post_income', 'minority', 'internal_arap', 'internal_trade',
    'internal_cashflow',
    ...Object.keys(saved).filter((key) => key.startsWith('share_change_')),
  ])
  for (const key of keys) worksheetDrafts.prime(key, currentPayload(key))
  workspaceGuard?.notifyStateChange()
}

async function requestSheetChange(sheetKey: string): Promise<boolean> {
  if (!sheetKey || sheetKey === activeSheet.value) return true
  const change = () => { activeSheet.value = sheetKey }
  if (!workspaceGuard) {
    change()
    return true
  }
  return workspaceGuard.runTransition(`切换到“${sheetLabel(sheetKey)}”前，请处理当前未保存修改。`, change, ['consol-worksheets'])
}

function resetWorksheetData(options: { clearScope?: boolean; resetView?: boolean } = {}) {
  Object.assign(data, createDefaultWorksheetData())
  for (const key of Object.keys(shareChangeData)) delete shareChangeData[key]
  internalRows.arap = null
  internalRows.trade = null
  internalCashflowRows.value = null
  postInvestRows.value = []
  postIncomeRows.value = []
  minorityRows.value = []
  capitalAdjustmentItems.value = []
  capitalConsolReportAmount.value = null
  savedSheetKeys.value = new Set()
  Object.keys(sheetVersions).forEach((k) => delete sheetVersions[k])
  g7SuggestionDraft.rows = []
  g7SuggestionDraft.note = ''
  g7SuggestionDraft.importedAt = ''
  if (options.clearScope) {
    treeInfoMembers.value = null
    rootCompanyCode.value = ''
    treeMode.value = null
  }
  if (options.resetView) {
    g7LinkagePreview.value = null
    g7LinkageVisible.value = false
    activeSheet.value = 'info'
  }
}

// 子企业列：只以企业树为准（持股比例取基本信息表填写值）；企业树不可用时回退基本信息表的已填企业（R4.4）
const companyColumns = computed(() => worksheetCompanyColumns(treeInfoMembers.value, data.subsidiaryInfo))

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
  // 资本公积（4002）合并抵消合计：服务端 canonical projection 权威总额（approved 分录派生，替代空骨架）
  const capitalAccount = postElimProjection.value?.accounts?.[POST_ELIM_ACCOUNT.capitalReserve] ?? null
  const elimCapital = nn(capitalAccount?.total)
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
  void requestSheetChange(`share_change_${times}`)
}

async function onSheetSave(sheetKey: string, payload: unknown): Promise<boolean> {
  if (draftsReady.value) worksheetDrafts.update(sheetKey, payload)
  workspaceGuard?.notifyStateChange()
  return saveSingleSheet(sheetKey, payload)
}

async function performSheetSave(sheetKey: string, payload: unknown): Promise<boolean> {
  if (props.readonlyReason) {
    ElMessage.warning(props.readonlyReason)
    return false
  }
  if (!projectId.value) {
    ElMessage.warning('项目ID缺失')
    return false
  }
  const snapshot = clonePlain(payload)
  try {
    const currentVersion = sheetVersions[sheetKey] ?? 0
    const result = await saveWorksheetData(
      projectId.value,
      year.value,
      sheetKey,
      contentForSave(sheetKey, snapshot),
      currentVersion,
    )
    if (!result.ok) {
      ElMessage.error(`${sheetLabel(sheetKey)}保存失败，请检查后端服务`)
      return false
    }
    sheetVersions[sheetKey] = result.version
    savedSheetKeys.value = new Set([...savedSheetKeys.value, sheetKey])
    worksheetDrafts.markSaved(sheetKey, snapshot)
    if (!worksheetDrafts.dirtyKeys.value.has(sheetKey)) applyPayloadToState(sheetKey, snapshot)
    workspaceGuard?.notifyStateChange()
    ElMessage.success(`${sheetLabel(sheetKey)}已保存`)
    return true
  } catch (err: any) {
    if (err instanceof WorksheetVersionConflictError) {
      ElMessage.warning('工作底稿已被其他操作修改；当前编辑已保留，请保存到别处或放弃后重新读取')
      return false
    }
    handleApiError(err, `${sheetLabel(sheetKey)}保存`)
    return false
  }
}

async function saveSingleSheet(sheetKey: string, payload: unknown): Promise<boolean> {
  if (worksheetSaveInFlight) await worksheetSaveInFlight
  worksheetSaving.value = true
  workspaceGuard?.notifyStateChange()
  const task = performSheetSave(sheetKey, payload)
  worksheetSaveInFlight = task
  try {
    return await task
  } finally {
    if (worksheetSaveInFlight === task) worksheetSaveInFlight = null
    worksheetSaving.value = false
    workspaceGuard?.notifyStateChange()
  }
}

async function savePendingWorksheetDrafts(): Promise<boolean> {
  if (worksheetSaveInFlight && !(await worksheetSaveInFlight)) return false
  for (let pass = 0; pass < 8; pass += 1) {
    const keys = [...worksheetDrafts.dirtyKeys.value]
    if (!keys.length) return true
    for (const key of keys) {
      const payload = worksheetDrafts.current(key)
      if (payload === undefined || !(await saveSingleSheet(key, payload))) return false
    }
  }
  return worksheetDrafts.dirtyKeys.value.size === 0
}

async function discardPendingWorksheetDrafts(): Promise<void> {
  if (worksheetSaveInFlight) await worksheetSaveInFlight
  draftsReady.value = false
  for (const key of [...worksheetDrafts.dirtyKeys.value]) {
    const baseline = worksheetDrafts.discard(key)
    applyPayloadToState(key, baseline)
  }
  await nextTick()
  draftsReady.value = true
  workspaceGuard?.notifyStateChange()
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

const SHEET_LABELS: Record<string, string> = {
  info: '基本信息表', cost: '投资明细-成本法', equity_inv: '投资明细-权益法',
  net_asset: '净资产表', equity_sim: '模拟权益法', capital: '资本公积变动',
  post_invest: '抵消后长投', post_income: '抵消后投资收益', minority: '少数股东权益损益',
  internal_arap: '内部往来抵消', internal_trade: '内部交易抵消',
  internal_cashflow: '内部现金流抵消', elimination: '合并抵消分录', share_change: '股比变动表',
}
/** 表的中文名（保存提示、导出文件名用；不把内部键 info / share_change_1 显示给用户） */
function sheetLabel(key: string): string {
  const m = key.match(/^share_change_(\d+)$/)
  return m ? `股比变${m[1]}次` : SHEET_LABELS[key] || key
}
/** 当前 sheet 的中文名 */
const activeSheetLabel = computed(() => sheetLabel(activeSheet.value))

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

    // 基本信息表在企业树锁定时：按企业代码只更新可编辑字段，匹配不上的行列出并跳过（R4.3，与表内导入同一函数）
    if (activeSheet.value === 'info' && treeInfoMembers.value) {
      const merged = mergeImportedInfoRows(data.subsidiaryInfo, mapped, cols.map((c) => c.key))
      if (merged.unmatched.length) {
        ElMessage.warning(`以下行在表中找不到对应企业，已跳过：${merged.unmatched.slice(0, 10).join('、')}`)
      }
      if (!merged.updated) return
      data.subsidiaryInfo = merged.rows
      await onSheetSave('info', merged.rows)
      return
    }

    const imported = await onSheetSave(activeSheet.value, mapped)
    if (imported) {
      ElMessage.success(`已导入 ${mapped.length} 行到「${activeSheetLabel.value}」`)
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

const SERVER_SOURCE_SHEETS = ['equity_sim', 'internal_arap', 'internal_trade'] as const
const serverSourceSheetKeys = computed(() => SERVER_SOURCE_SHEETS.filter((key) => savedSheetKeys.value.has(key)))
const serverSourceVersions = computed(() => Object.fromEntries(
  serverSourceSheetKeys.value.map((key) => [key, sheetVersions[key] ?? 0]),
))

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

/** 分录变化（差额分录抽屉增删改 / 审批）后重读分录汇总表；未打开该表时下次进入会自动重读 */
async function reloadEntrySummary() {
  await entrySummarySheetRef.value?.load()
}

defineExpose({ reload, reloadEntrySummary, activeSheet })
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
