<template>
  <div class="gt-report-view gt-fade-in" :class="{ 'gt-fullscreen': rvFullscreen }">
    <!-- 固定顶部区域 -->
    <div class="gt-rv-sticky-header">
      <!-- 页面横幅 -->
      <GtPageHeader title="财务报表" :show-sync-status="true" @back="goBack">
        <GtInfoBar
          :show-unit="true"
          :show-year="true"
          :show-template="true"
          :show-scope="true"
          :unit-value="selectedProjectId"
          :year-value="selectedYear"
          :template-value="selectedTemplateType"
          :scope-label="scopeLabel"
          :badges="[
            { label: '单位', value: displayPrefs.unitSuffix },
          ]"
          @unit-change="onProjectChange"
          @year-change="onYearChange"
          @template-change="onTemplateTypeChange"
        >
        </GtInfoBar>
        <template #actions>
          <GtToolbar
            :show-copy="true"
            :show-fullscreen="true"
            :is-fullscreen="rvFullscreen"
            :show-export="true"
            @copy="copyReportTable"
            @fullscreen="toggleRvFullscreen()"
            @export="onExportExcel"
          >
            <template #left>
              <el-radio-group v-model="reportMode" size="small" @change="fetchReport" class="gt-rv-mode-radio">
                <el-radio-button value="audited">已审</el-radio-button>
                <el-radio-button value="unadjusted">未审</el-radio-button>
                <el-radio-button value="compare">对比</el-radio-button>
              </el-radio-group>
              <el-button v-if="!isEqcrRole" size="small" type="primary" @click="onGenerate" :loading="genLoading">刷新</el-button>
              <el-button size="small" @click="_onConsistencyCheckWrapper" :loading="checkLoading">审核</el-button>
            </template>
            <template #right-extra>
              <el-button size="small" @click="onExportAllExcel">全部导出</el-button>
              <el-button size="small" @click="showReportImport = true">导入</el-button>
              <el-button size="small" @click="showFormulaManager = true">公式</el-button>
              <el-dropdown trigger="click" size="small">
                <el-button size="small">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="onEditConfig">编辑结构</el-dropdown-item>
                    <el-dropdown-item @click="showMappingDialog = true">转换规则</el-dropdown-item>
                    <el-dropdown-item @click="showDocAiChat = true">AI 对话</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </GtToolbar>
        </template>
      </GtPageHeader>

      <!-- 归档横幅 -->
      <ArchivedBanner />
      <ConsolLockedBanner />

      <!-- 跨模块冲突 banner（spec global-refinement-v3 Task 7.5） -->
      <ConflictBanner :project-id="projectId" @view="conflictPanelVisible = true" />
      <ConflictResolutionPanel
        v-model="conflictPanelVisible"
        :project-id="projectId"
        @resolved="onConflictResolved"
      />

      <!-- F29: 报表平衡检查结果（展示明细+跳转） -->
      <el-alert
        v-if="balanceCheckResult"
        :title="balanceCheckResult.status === 'passed' ? '报表平衡检查通过' : balanceCheckResult.status === 'warning' ? '报表平衡检查有差异' : '报表平衡检查失败'"
        :type="balanceCheckResult.status === 'passed' ? 'success' : balanceCheckResult.status === 'warning' ? 'warning' : 'error'"
        show-icon
        :closable="true"
        style="margin-bottom: 8px"
        @close="balanceCheckResult = null"
      >
        <template #default>
          <div>{{ balanceCheckResult.message }}</div>
          <div v-if="balanceCheckResult.checks?.length" style="margin-top: 6px; font-size: 12px; line-height: 1.8">
            <div
              v-for="(chk, idx) in balanceCheckResult.checks.filter(c => !c.passed)"
              :key="idx"
              style="display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 2px 0;"
              @click="scrollToReportRow(chk.name)"
            >
              <span style="color: var(--el-color-danger)">✗</span>
              <span style="flex: 1">{{ chk.name }}</span>
              <span style="color: var(--el-text-color-secondary)">期望 {{ chk.expected }}，实际 {{ chk.actual }}，差 {{ chk.diff }}</span>
              <el-button text size="small" type="primary" style="padding: 0">定位 →</el-button>
            </div>
          </div>
        </template>
      </el-alert>

      <!-- Sprint 4：StaleIndicator 统一组件 + 横幅 -->
      <div v-if="stale.isStale.value" class="gt-stale-banner">
        <StaleIndicator :stale="true" tooltip="上游数据已变更" />
        <span class="gt-stale-text">
          上游数据已变更，当前报表可能基于旧试算表（{{ stale.staleCount.value }} 张底稿待重算）
        </span>
        <el-button size="small" type="primary" :loading="stale.loading.value" @click="onStaleRecalc">
          🔄 点击重算
        </el-button>
      </div>

      <!-- useStaleRefresh：上游变更事件横幅 -->
      <div v-if="staleRefresh.isStale.value && !stale.isStale.value" class="gt-stale-banner">
        <StaleIndicator :stale="true" tooltip="上游数据已变更" />
        <span class="gt-stale-text">上游数据已变更，建议重新加载报表</span>
        <el-button size="small" type="primary" @click="staleRefresh.refresh()">刷新数据</el-button>
      </div>

      <!-- US-2：底稿数据更新 → 报表 stale 黄色横幅 -->
      <el-alert
        v-if="showReportStaleBanner"
        title="底稿数据已更新"
        :description="`${reportStaleRows.length} 个报表行受影响，点击刷新获取最新数据`"
        type="warning"
        show-icon
        :closable="true"
        style="margin-bottom: 8px"
        @close="showReportStaleBanner = false"
      >
        <template #default>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span>{{ reportStaleRows.length }} 个报表行受影响，点击刷新获取最新数据</span>
            <el-button size="small" type="warning" @click="onReportStaleRefresh">🔄 刷新报表</el-button>
          </div>
        </template>
      </el-alert>

      <!-- Tab 切换 -->
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="资产负债表" name="balance_sheet" />
        <el-tab-pane label="利润表" name="income_statement" />
        <el-tab-pane label="现金流量表" name="cash_flow_statement" />
        <el-tab-pane label="所有者权益变动表" name="equity_statement" />
        <el-tab-pane label="现金流附表" name="cash_flow_supplement" />
        <el-tab-pane label="资产减值准备表" name="impairment_provision" />
        <el-tab-pane label="⚖️ 跨表核对" name="cross_check" />
        <el-tab-pane label="📊 多年度对比" name="multi_year_compare" />
      </el-tabs>
    </div>

    <!-- 可滚动的表格区域 -->
    <div class="gt-rv-table-area">

    <!-- 空数据引导提示 -->
    <GtEmpty
      v-if="!loading && rows.length === 0 && !isTracing"
      title="报表暂无数据"
      description="请先导入账套数据并执行刷新"
      icon="📊"
      action-text="去导入"
      style="margin: 40px 0"
      @action="router.push(`/projects/${projectId}/ledger`)"
    />

    <!-- 溯源返回浮动条 -->
    <div v-if="isTracing" class="gt-rv-trace-bar">
      <span>📍 正在查看溯源数据 — {{ activeTabLabel }}</span>
      <el-button size="small" type="primary" round @click="onTraceReturn">↩ 返回审核</el-button>
    </div>

    <!-- 搜索栏（Ctrl+F 触发，表格上方） -->
    <TableSearchBar
      :is-visible="rvSearch.isVisible.value"
      :keyword="rvSearch.keyword.value"
      :match-info="rvSearch.matchInfo.value"
      :has-matches="rvSearch.matches.value.length > 0"
      :case-sensitive="rvSearch.caseSensitive.value"
      :show-replace="false"
      @update:keyword="rvSearch.keyword.value = $event"
      @update:case-sensitive="rvSearch.caseSensitive.value = $event"
      @search="rvSearch.search()"
      @next="rvSearch.nextMatch()"
      @prev="rvSearch.prevMatch()"
      @close="rvSearch.close()"
    />

    <!-- 所有者权益变动表 — 对比模式：未审 / 审定并排矩阵 -->
    <div v-if="activeTab === 'equity_statement' && reportMode === 'compare'" class="gt-rv-equity-compare" v-loading="loading">
      <div class="gt-rv-equity-compare-block">
        <div class="gt-rv-equity-compare-label">未审数</div>
        <ReportEquityTable
          :rows="equityCompareUnadjusted"
          :eq-columns="eqColumns"
          :eq-total-cols="eqTotalCols"
          :year="year"
          :table-max-height="480"
          :cell-class-name="rvCellClassName"
          :font-size="displayPrefs.fontConfig.tableFont"
          :equity-span-method="equitySpanMethod"
          :eq-row-class-name="eqRowClassName"
          :eq-cell-val="eqCellVal"
          :is-consolidated="isConsolidated"
        />
      </div>
      <div class="gt-rv-equity-compare-block">
        <div class="gt-rv-equity-compare-label">审定数</div>
        <ReportEquityTable
          ref="eqTableRef"
          :rows="equityCompareAudited"
          :eq-columns="eqColumns"
          :eq-total-cols="eqTotalCols"
          :year="year"
          :table-max-height="480"
          :cell-class-name="rvCellClassName"
          :font-size="displayPrefs.fontConfig.tableFont"
          :equity-span-method="equitySpanMethod"
          :eq-row-class-name="eqRowClassName"
          :eq-cell-val="eqCellVal"
          :is-consolidated="isConsolidated"
          @cell-click="onRvCellClick"
          @cell-dblclick="onRvCellDblClick"
          @cell-contextmenu="onRvCellContextMenu"
        />
      </div>
    </div>

    <!-- 所有者权益变动表 — 单表模式 -->
    <div v-else-if="activeTab === 'equity_statement'" class="gt-rv-equity-matrix" v-loading="loading">
      <ReportEquityTable
        ref="eqTableRef"
        :rows="rows"
        :eq-columns="eqColumns"
        :eq-total-cols="eqTotalCols"
        :year="year"
        :table-max-height="600"
        :cell-class-name="rvCellClassName"
        :font-size="displayPrefs.fontConfig.tableFont"
        :equity-span-method="equitySpanMethod"
        :eq-row-class-name="eqRowClassName"
        :eq-cell-val="eqCellVal"
        :is-consolidated="isConsolidated"
        @cell-click="onRvCellClick"
        @cell-dblclick="onRvCellDblClick"
        @cell-contextmenu="onRvCellContextMenu"
      />
    </div>

    <!-- 资产减值准备表 — ReportImpairmentTable 子组件 -->
    <div v-if="activeTab === 'impairment_provision'" class="gt-rv-equity-matrix" v-loading="loading">
      <ReportImpairmentTable
        ref="impTableRef"
        :rows="rows"
        :imp-inc-cols="impIncCols"
        :imp-dec-cols="impDecCols"
        :table-max-height="600"
        :cell-class-name="rvCellClassName"
        :font-size="displayPrefs.fontConfig.tableFont"
        :imp-row-class-name="impRowClassName"
        @cell-click="onRvCellClick"
        @cell-dblclick="onRvCellDblClick"
        @cell-contextmenu="onRvCellContextMenu"
      />
    </div>

    <!-- 报表表格 — 普通模式（非矩阵报表） -->
    <el-table ref="rvTableRef" v-if="reportMode !== 'compare' && activeTab !== 'equity_statement' && activeTab !== 'impairment_provision' && activeTab !== 'cross_check' && activeTab !== 'multi_year_compare'" :data="rows" v-loading="loading" style="width: 100%"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :row-class-name="rowClassName" :show-header="true" border size="small" :max-height="600"
      :cell-class-name="rvCellClassName"
      @cell-click="onRvCellClick"
      @cell-dblclick="onRvCellDblClick"
      @cell-contextmenu="onRvCellContextMenu">
      <el-table-column label="序号" width="70" align="center" :resizable="true">
        <template #default="{ $index }">
          <span style="color: var(--gt-color-text-tertiary);">{{ $index + 1 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="项目" min-width="300" :resizable="true" fixed>
        <template #default="{ row }">
          <span :class="['report-row-name', `report-indent-${Math.min(row.indent_level || 0, 2)}`]"
                :style="{ paddingLeft: (row.indent_level || 0) * 24 + 8 + 'px', fontWeight: row.is_total_row || getRowType(row) === 'header' ? 700 : 400, fontSize: '13px', cursor: row.row_code && !row.is_total_row && getRowType(row) !== 'header' ? 'pointer' : 'default' }"
                @click="onRowNameClick(row)">
            {{ row.row_name }}
            <el-button v-if="getNoteSection(row.row_code)" size="small" text type="primary"
              style="font-size: var(--gt-font-size-xs);padding:0 2px;margin-left:4px" title="查看附注"
              @click.stop="goToNote(row.row_code)">📝</el-button>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" min-width="160" align="right" header-align="center" :resizable="true" sortable :sort-method="(a: any, b: any) => (Number(a.current_period_amount) || 0) - (Number(b.current_period_amount) || 0)">
        <template #default="{ row, $index }">
          <template v-if="getRowType(row) === 'header'">
            <span class="report-amount">&nbsp;</span>
          </template>
          <template v-else-if="getRowType(row) === 'manual'">
            <span class="report-amount" style="color: var(--gt-color-text-placeholder);">—</span>
          </template>
          <template v-else>
            <el-tooltip :content="row.formula ? `公式：${row.formula}` : `行次 ${row.row_code || ''}`" placement="top" :show-after="500" :disabled="!row.row_code">
              <GtAmountCell
                :value="row.current_period_amount"
                :prior-value="row.prior_period_amount"
                :clickable="true"
                :comment="rvComments.getComment(`report_${activeTab}`, $index, 2)"
                @click="onLineComposition(row)"
              />
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" min-width="160" align="right" header-align="center" :resizable="true" sortable :sort-method="(a: any, b: any) => (Number(a.prior_period_amount) || 0) - (Number(b.prior_period_amount) || 0)">
        <template #default="{ row, $index }">
          <template v-if="getRowType(row) === 'header'">
            <span class="report-amount">&nbsp;</span>
          </template>
          <template v-else-if="getRowType(row) === 'manual'">
            <span class="report-amount" style="color: var(--gt-color-text-placeholder);">—</span>
          </template>
          <template v-else>
            <el-tooltip :content="row.formula ? `公式：${row.formula}` : `行次 ${row.row_code || ''}`" placement="top" :show-after="500" :disabled="!row.row_code">
              <GtAmountCell
                :value="row.prior_period_amount"
                :clickable="false"
                :comment="rvComments.getComment(`report_${activeTab}`, $index, 3)"
              />
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 报表表格 — 对比视图（非权益变动表） -->
    <el-table ref="compareTableRef" v-if="reportMode === 'compare' && activeTab !== 'equity_statement' && activeTab !== 'impairment_provision' && activeTab !== 'cross_check' && activeTab !== 'multi_year_compare'" :data="compareRows" v-loading="loading" style="width: 100%"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :row-class-name="compareRowClassName"
      :cell-class-name="rvCellClassName"
      @cell-click="onRvCellClick"
      @cell-dblclick="onRvCellDblClick"
      @cell-contextmenu="onRvCellContextMenu"
      border size="small" :max-height="600">
      <el-table-column label="序号" width="70" align="center" :resizable="true">
        <template #default="{ $index }">
          <span style="color: var(--gt-color-text-tertiary);">{{ $index + 1 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="项目" min-width="250" :resizable="true">
        <template #default="{ row }">
          <span :style="{ paddingLeft: (row.indent_level || 0) * 24 + 8 + 'px', fontWeight: row.is_total_row || getRowType(row) === 'header' ? 700 : 400, fontSize: '13px', cursor: row.row_code && !row.is_total_row && getRowType(row) !== 'header' ? 'pointer' : 'default' }"
                @click="onRowNameClick(row)">{{ row.row_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未审金额" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.unadjusted_amount" />
        </template>
      </el-table-column>
      <el-table-column label="调整影响" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.adjustment" />
        </template>
      </el-table-column>
      <el-table-column label="已审金额" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.audited_amount" />
        </template>
      </el-table-column>
      <!-- 任务 12.7.1：对比视图新增"上年审定数"列（需求 24.1/24.2） -->
      <el-table-column label="上年审定数" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.prior_period_amount" />
        </template>
      </el-table-column>
      <!-- Sprint 11 Task 11.6：变动额+变动率列（需求 33.2/33.3） -->
      <el-table-column label="变动额" min-width="120" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="(row.audited_amount || 0) - (row.prior_period_amount || 0)" />
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="90" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <span v-if="row.prior_period_amount && row.prior_period_amount !== 0"
                :class="['gt-rv-change-rate', { 'gt-rv-change-rate--alert': Math.abs(((row.audited_amount || 0) - row.prior_period_amount) / Math.abs(row.prior_period_amount) * 100) > 20 }]">
            {{ (((row.audited_amount || 0) - row.prior_period_amount) / Math.abs(row.prior_period_amount) * 100).toFixed(1) }}%
          </span>
          <span v-else style="color: var(--gt-color-text-placeholder);">-</span>
        </template>
      </el-table-column>
    </el-table>
    <!-- 选中区域状态栏 -->
    <SelectionBar :stats="rvCtx.selectionStats()" />

    <!-- F28: 报表数据覆盖率摘要 -->
    <div v-if="coverageSummary && activeTab !== 'cross_check'" class="gt-rv-coverage-summary">
      <span class="gt-rv-coverage-icon">📊</span>
      <span class="gt-rv-coverage-text">{{ coverageSummary.text }}</span>
    </div>

    <!-- R7-S3-10 Task 49-50：跨表核对面板 -->
    <div v-if="activeTab === 'cross_check'" class="gt-rv-cross-check">
      <h3 style="margin: 0 0 16px; font-size: var(--gt-font-size-md)">⚖️ 跨表核对（7 条关键等式）</h3>
      <el-table :data="crossCheckResults" border size="small" style="width: 100%"
        :cell-class-name="rvCellClassName"
        @cell-click="onRvCellClick"
        @cell-contextmenu="onRvCellContextMenu">
        <el-table-column label="#" width="40" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="核对等式" prop="description" min-width="300" />
        <el-table-column label="左值" prop="leftValue" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.leftValue" /></template>
        </el-table-column>
        <el-table-column label="右值" prop="rightValue" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.rightValue" /></template>
        </el-table-column>
        <el-table-column label="差异" width="120" align="right">
          <template #default="{ row }">
            <GtAmountCell :value="row.diff" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <span>{{ row.passed ? '✅' : '❌' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 12px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">
        核对基于当前已加载的报表数据计算，如数据未加载请先切换到对应报表 Tab。
      </div>
    </div>

    <!-- Phase 4 F2: 多年度对比 -->
    <div v-if="activeTab === 'multi_year_compare'" class="gt-rv-multi-year">
      <MultiYearCompare
        :project-id="projectId"
        :current-year="year"
      />
    </div>

    </div><!-- /gt-rv-table-area -->

    <!-- 公式管理弹窗 -->
    <FormulaManagerDialog
      v-model="showFormulaManager"
      :rows="rows"
      :project-id="projectId"
      :year="year"
      @saved="fetchReport"
      @applied="fetchReport"
    />

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showReportImport"
      import-type="report"
      :project-id="projectId"
      :year="year"
      :sub-type="activeTab"
      @imported="onReportImported"
    />

    <!-- ReportDialogs 子组件：穿透/构成科目/审核/溯源/转换规则/附注引用/合并明细/公式来源弹窗 -->
    <ReportDialogs
      :drilldown-visible="drilldownVisible"
      :drilldown-loading="drilldownLoading"
      :drilldown-data="drilldownData"
      :line-comp-visible="lineCompVisible"
      :line-comp-loading="lineCompLoading"
      :line-comp-data="lineCompData"
      :show-audit-dialog="showAuditDialog"
      :consistency-result="consistencyResult"
      :audit-tab="auditTab"
      :filtered-audit-checks="filteredAuditChecks"
      :show-trace-select-dialog="showTraceSelectDialog"
      :trace-select-options="traceSelectOptions"
      :trace-select-check="traceSelectCheck"
      :note-refs-visible="noteRefsVisible"
      :note-refs-loading="noteRefsLoading"
      :note-refs-list="noteRefsList"
      :note-refs-row-code="noteRefsRowCode"
      :note-refs-row-name="noteRefsRowName"
      :rv-trace-dialog-visible="rvTraceDialogVisible"
      :rv-trace-loading="rvTraceLoading"
      :rv-trace-result="rvTraceResult"
      :show-mapping-dialog="showMappingDialog"
      :mapping-loading="mappingLoading"
      :mapping-tab="mappingTab"
      :mapping-report-types="mappingReportTypes"
      :current-mapping-rules="currentMappingRules"
      :current-listed-options="currentListedOptions"
      :total-mapped-count="totalMappedCount"
      :total-rule-count="totalRuleCount"
      :mapping-tab-label="mappingTabLabel"
      :get-mapping-config-data="getMappingConfigData"
      :consol-breakdown-visible="consolBreakdownVisible"
      :consol-breakdown-account-code="consolBreakdownAccountCode"
      :project-id="projectId"
      :year="year"
      :show-cell-formula-detail="showCellFormulaDetail"
      :cell-detail-wp-code="cellDetailWpCode"
      :cell-detail-sheet="cellDetailSheet"
      :cell-detail-label="cellDetailLabel"
      :parse-trace-locations="parseTraceLocations"
      @update:drilldown-visible="drilldownVisible = $event"
      @update:line-comp-visible="lineCompVisible = $event"
      @update:show-audit-dialog="showAuditDialog = $event"
      @update:show-trace-select-dialog="showTraceSelectDialog = $event"
      @update:note-refs-visible="noteRefsVisible = $event"
      @update:rv-trace-dialog-visible="rvTraceDialogVisible = $event"
      @update:show-mapping-dialog="showMappingDialog = $event"
      @update:consol-breakdown-visible="consolBreakdownVisible = $event"
      @update:show-cell-formula-detail="showCellFormulaDetail = $event"
      @update:mapping-tab="mappingTab = $event"
      @update:audit-tab="auditTab = $event"
      @line-comp-jump="onLineCompJumpToTB"
      @audit-drilldown="_onAuditDrilldown"
      @audit-export-excel="onExportAuditExcel"
      @trace-jump="onTraceJump"
      @trace-return="onTraceReturn"
      @trace-locate="onRvTraceLocate"
      @note-ref-jump="onJumpToNoteSection"
      @mapping-load-preset="loadPresetMappingAll"
      @mapping-save="saveMappingRulesAll"
      @mapping-template-applied="onMappingTemplateApplied"
      @cell-detail-navigate="onCellDetailNavigate"
      @open-workpaper="openWorkpaper"
    />
  </div>

  <!-- 右键菜单（统一组件） -->
  <CellContextMenu
    :visible="rvCtx.contextMenu.visible"
    :x="rvCtx.contextMenu.x"
    :y="rvCtx.contextMenu.y"
    :item-name="rvCtx.contextMenu.itemName"
    :value="rvCtx.selectedCells.value.length === 1 ? rvCtx.selectedCells.value[0]?.value : undefined"
    :multi-count="rvCtx.selectedCells.value.length"
    @copy="onRvCtxCopy"
    @formula="onRvCtxFormula"
    @trust-score="onRvCtxTrustScore"
    @sum="onRvCtxSum"
    @compare="onRvCtxCompare"
  >
    <div class="gt-ucell-ctx-item" @click="onRvCtxDrillDown"><span class="gt-ucell-ctx-icon">📊</span> 查看穿透</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxGoNote"><span class="gt-ucell-ctx-icon">📝</span> 跳转附注</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxShowNoteRefs"><span class="gt-ucell-ctx-icon">🔎</span> 附注引用我</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxOpenWorkpaper"><span class="gt-ucell-ctx-icon">📋</span> 打开对应底稿</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxViewAdjustments"><span class="gt-ucell-ctx-icon">🔗</span> 查看调整明细</div>
    <div v-if="isConsolidated" class="gt-ucell-ctx-item" @click="onRvCtxViewConsolBreakdown"><span class="gt-ucell-ctx-icon">🔗</span> 查看合并明细</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxViewFormulaSource"><span class="gt-ucell-ctx-icon">🔍</span> 查看公式来源</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxCellTrace"><span class="gt-ucell-ctx-icon">🔍</span> 数字溯源</div>
  </CellContextMenu>

  <!-- V3 Req 9.6: 数字信任度面板 -->
  <TrustScorePanel ref="trustScorePanelRef" :project-id="projectId" />

  <!-- V3 Req 10.4: 可解释状态机面板 -->
  <StatusMachinePanel ref="smPanelRef" module="report" :instance-id="reportInstanceId" />

  <!-- AI 文档对话面板 -->
  <DocAiChatPanel
    :doc-type="'report'"
    :doc-id="projectId"
    :project-id="projectId"
    :year="year"
    :visible="showDocAiChat"
    @update:visible="showDocAiChat = $event"
    @close="showDocAiChat = false"
    @adopt="onDocAiAdopt"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch, watchEffect, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import MultiYearCompare from '@/components/report/MultiYearCompare.vue'
import ReportEquityTable from '@/components/report/ReportEquityTable.vue'
import ReportImpairmentTable from '@/components/report/ReportImpairmentTable.vue'
import ReportDialogs from '@/components/report/ReportDialogs.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtEmpty from '@/components/common/GtEmpty.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useProjectStore } from '@/stores/project'
import { setupPasteListener, pasteToSelection } from '@/composables/useCopyPaste'
import { useAuditContext } from '@/composables/useAuditContext'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import ConflictBanner from '@/components/conflict/ConflictBanner.vue'
import ConflictResolutionPanel from '@/components/conflict/ConflictResolutionPanel.vue'
import TrustScorePanel from '@/components/trust/TrustScorePanel.vue'
import StatusMachinePanel from '@/components/status_machine/StatusMachinePanel.vue'
import { withLoading } from '@/composables/useLoading'
import { usePenetrate } from '@/composables/usePenetrate'
import { useProjectEvents } from '@/composables/useProjectEvents'
import { useStaleRefresh } from '@/composables/useStaleRefresh'
import { recalcTrialBalance } from '@/services/auditPlatformApi'
import { useAuthStore } from '@/stores/auth'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { useReportColumns } from './composables/useReportColumns'
import { useReportCrossCheck } from './composables/useReportCrossCheck'
import { useReportData } from './composables/useReportData'
import { useReportExport } from './composables/useReportExport'
import { useReportMapping } from './composables/useReportMapping'
import { useReportCellActions } from './composables/useReportCellActions'
import DocAiChatPanel from '@/components/DocAiChatPanel.vue'

const route = useRoute()
const router = useRouter()
const { canEdit, onContextChange } = useAuditContext()

// EQCR 只读访问 (Requirements: 17.1-17.4)
const authStore = useAuthStore()
const isEqcrRole = computed(() => authStore.user?.role === 'eqcr')
const projectStore = useProjectStore()

// ─── P0-6.4: ProjectContext + PermissionMatrix facade ────────────────────────
const projectContext = computed(() => projectStore.currentProjectContext)
const { can: canOp, whyCannot } = usePermissionMatrix()
// DEPRECATED: 旧 isEqcrRole 判断仍保留，后续替换为 !canOp('report:edit')

const projectId = computed(() => projectStore.projectId)

// 跨模块冲突调解（spec global-refinement-v3 Task 7.5）
const conflictPanelVisible = ref(false)
function onConflictResolved(_id: string, _resolution: string) {
  // 调解后 banner 自动从列表移除；此处保留 hook 供后续扩展（如局部 reload）
}

// ─── AI 文档对话采纳 ─────────────────────────────────────────────────────────
function onDocAiAdopt(_payload: { content: string; messageId: string }) {
  // 采纳事件由 DocAiChatPanel 内部调用 adoptContent API（走确认流）
  // D4: AI 内容已经过 wrap_ai_output_with_log → pending 状态，不直接写入
  // 报表视图在确认流完成后刷新数据
  fetchReport()
}

// ─── 云协同：账套激活/回滚后自动刷新 ─────────────────────────────────────────
const { onDatasetActivated, onDatasetRolledBack, onAnyEvent } = useProjectEvents(projectId)
onDatasetActivated(() => fetchReport())
onDatasetRolledBack(() => fetchReport())

// ─── useStaleRefresh：补充上游变更事件（dataset 已由 useProjectEvents 覆盖） ────
const staleRefresh = useStaleRefresh(projectId, {
  events: ['trial-balance:updated', 'adjustment:saved', 'year:changed', 'project:updated'],
  mode: 'prompt',
  onRefresh: () => fetchReport(),
})

// R8-S2-03：Stale 状态追踪（上游数据变更提示）
import { useStaleStatus } from '@/composables/useStaleStatus'
import StaleIndicator from '@/components/StaleIndicator.vue'
const stale = useStaleStatus(projectId)

// US-2：底稿保存后 report.stale SSE 订阅 → 黄色横幅 + 刷新
const reportStaleRows = ref<string[]>([])
const showReportStaleBanner = ref(false)

onAnyEvent((evt) => {
  if (evt.event_type === 'report.stale' && evt.extra?.rows) {
    reportStaleRows.value = evt.extra.rows as string[]
    showReportStaleBanner.value = true
  }
})

async function onReportStaleRefresh() {
  showReportStaleBanner.value = false
  reportStaleRows.value = []
  await fetchReport()
}
async function onStaleRecalc() {
  await stale.recalc()
  // 重算后重新拉取报表数据
  await fetchReport()
}

function goBack() {
  router.push(`/projects`)
}

const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const _templateTypeLabel = computed(() => reportData.templateType.value === 'listed' ? '上市版' : '国企版')
const scopeLabel = computed(() => reportData.reportScope.value === 'consolidated' ? '合并' : '单体')

// 单位（项目）选择器 — 使用 projectStore
const selectedProjectId = ref('')
const projectOptions = computed(() => projectStore.projectOptions)

function onProjectChange(newId: string) {
  router.push({ path: `/projects/${newId}/reports`, query: route.query })
}

// 年度选择器
const selectedYear = ref(new Date().getFullYear() - 1)
const yearOptions = computed(() => projectStore.yearOptions)
function onYearChange(val: number) {
  selectedYear.value = val
  projectStore.changeYear(val)
  fetchReport()
}

// 模板类型切换
const selectedTemplateType = ref('soe')
const _rdReportScope = ref('standalone')
const currentApplicableStandard = computed(() => `${selectedTemplateType.value}_${_rdReportScope.value}`)

async function onTemplateTypeChange(val: string) {
  selectedTemplateType.value = val
  reportData.templateType.value = val
  await reportData.fetchReport()
}

// ─── Other UI state ─────────────────────────────────────────────────────────
const showDocAiChat = ref(false)

const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear() - 1)

const activeTab = ref('balance_sheet')
const reportMode = ref<'audited' | 'unadjusted' | 'compare'>('audited')

// ─── useReportData composable ───────────────────────────────────────────────
const reportData = useReportData({
  projectId,
  year,
  activeTab,
  reportMode,
  currentApplicableStandard,
})

const {
  rows,
  compareRows,
  equityCompareAudited,
  equityCompareUnadjusted,
  loading,
  genLoading,
  checkLoading,
  syncLoading,
  balanceCheckResult,
  consistencyResult,
  tableMaxHeight,
  fetchReport,
  onGenerate,
  onConsistencyCheck,
  runBalanceCheck,
  loadTemplateRows,
  ensureProjectYear,
  reloadReportContext,
  activeTabLabel,
  coverageSummary,
  projectName,
  reportScope,
  templateType,
  isConsolidated,
} = reportData

// Sync composable's reportScope → local proxy for currentApplicableStandard
watchEffect(() => { _rdReportScope.value = reportScope.value })

// 动态计算表格最大高度（窗口高度 - 顶部固定区域）
function updateTableHeight() {
  const headerEl = document.querySelector('.gt-rv-sticky-header')
  const headerH = headerEl ? headerEl.getBoundingClientRect().height : 200
  tableMaxHeight.value = Math.max(300, window.innerHeight - headerH - 80)
}

// 平衡检查明细项点击跳转：根据检查名称中的关键词定位到报表对应行
function scrollToReportRow(checkName: string) {
  // 提取检查名称中可能包含的行次或表名信息
  // 常见格式: "资产负债表平衡（资产合计=负债+权益）" / "勾稽：CFS期末现金=BS货币资金"
  const table = document.querySelector('.el-table__body-wrapper tbody')
  if (!table) return
  const allRows = table.querySelectorAll('tr')

  // 从检查名中提取可匹配的关键词
  const keywords: string[] = []
  if (checkName.includes('资产负债') || checkName.includes('资产合计')) keywords.push('资产总计', '资产合计', '负债和所有者权益')
  if (checkName.includes('利润表') || checkName.includes('净利润')) keywords.push('净利润', '利润总额')
  if (checkName.includes('CFS') || checkName.includes('现金')) keywords.push('现金及现金等价物', '货币资金')
  if (checkName.includes('权益')) keywords.push('所有者权益合计', '股东权益')
  // 如果没提取到关键词,用原始检查名的各段尝试
  if (!keywords.length) {
    keywords.push(...checkName.split(/[（）()=≠,，]/g).map(s => s.trim()).filter(s => s.length > 1))
  }

  for (const tr of allRows) {
    const text = tr.textContent || ''
    if (keywords.some(kw => text.includes(kw))) {
      tr.scrollIntoView({ behavior: 'smooth', block: 'center' })
      tr.classList.add('gt-highlight-row')
      setTimeout(() => tr.classList.remove('gt-highlight-row'), 3000)
      return
    }
  }
  // fallback: 未找到匹配行时提示
  import('element-plus').then(({ ElMessage }) => {
    ElMessage.info('未找到对应行，请手动查看')
  })
}
onMounted(() => {
  updateTableHeight()
  window.addEventListener('resize', updateTableHeight)
  document.addEventListener('keydown', onKeydown)
  projectStore.loadProjectOptions()
  selectedProjectId.value = projectId.value
})
onUnmounted(() => {
  window.removeEventListener('resize', updateTableHeight)
  document.removeEventListener('keydown', onKeydown)
})

// ─── useReportColumns composable ────────────────────────────────────────────
const {
  eqColumns,
  eqTotalCols,
  equitySpanMethod,
  eqRowClassName,
  eqCellVal,
  impIncCols,
  impDecCols,
  impRowClassName,
  getRowType,
  rowClassName,
  compareRowClassName,
  formatReportAmount,
  getNoteSection,
  goToNote,
} = useReportColumns({ isConsolidated, activeTab, rows })

// ─── useReportMapping composable ────────────────────────────────────────────
const {
  showMappingDialog,
  mappingLoading,
  mappingTab,
  allMappingRules,
  allListedOptions,
  mappingReportTypes,
  mappingTabLabel,
  currentMappingRules,
  currentListedOptions,
  totalMappedCount,
  totalRuleCount,
  loadPresetMappingAll,
  saveMappingRulesAll,
  getMappingConfigData,
  onMappingTemplateApplied,
} = useReportMapping({ projectId, reportScope })

// ─── useReportCrossCheck composable ─────────────────────────────────────────
const {
  crossCheckData,
  crossCheckLoading,
  crossCheckResults,
  loadCrossCheckData,
} = useReportCrossCheck({ projectId, year, activeTab, currentApplicableStandard })

// ─── useReportExport composable ─────────────────────────────────────────────
const {
  onExportExcel,
  onExportAllExcel,
  copyReportTable,
  showReportImport,
  onReportImported,
} = useReportExport({ projectId, year, activeTab, rows, activeTabLabel, fetchReport })

const _reportModeLabel = computed(() => {
  const m: Record<string, string> = { audited: '已审报表', unadjusted: '未审报表', compare: '对比视图' }
  return m[reportMode.value] || ''
})

// Drilldown + Formula Manager (kept in main file for template binding)
const showFormulaManager = ref(false)

// V3 Req 9.6: 数字信任度
const trustScorePanelRef = ref<InstanceType<typeof TrustScorePanel> | null>(null)
function openTrustScore(context: string) {
  trustScorePanelRef.value?.open(context)
}

// V3 Req 10.4: 可解释状态机
const smPanelRef = ref<InstanceType<typeof StatusMachinePanel> | null>(null)
const reportInstanceId = ref('')
function openStatusMachine() {
  smPanelRef.value?.open()
}

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
// NOTE: 必须在 useReportCellActions 之前声明（被作为参数传入）
const rvCtx = useCellSelection()
const rvPenetrate = usePenetrate()
const rvComments = useCellComments(() => projectId.value, () => year.value, 'report')

// ─── useReportCellActions composable ────────────────────────────────────────
const cellActions = useReportCellActions({
  projectId,
  year,
  activeTab,
  rows,
  reportMode,
  isConsolidated,
  fetchReport,
  activeTabLabel,
  getRowType,
  goToNote,
  consistencyResult,
  showFormulaManager,
  openTrustScore,
  rvCtx,
  rvPenetrate,
  rvComments,
  eqCellVal,
})

const {
  drilldownVisible,
  drilldownLoading,
  drilldownData,
  onDrilldown,
  lineCompVisible,
  lineCompLoading,
  lineCompData,
  onLineComposition,
  onLineCompJumpToTB,
  noteRefsVisible,
  noteRefsLoading,
  noteRefsList,
  noteRefsRowCode,
  noteRefsRowName,
  onRvCtxShowNoteRefs,
  onJumpToNoteSection,
  rvTraceDialogVisible,
  rvTraceLoading,
  rvTraceResult,
  onRvCtxCellTrace,
  onRvTraceLocate,
  showAuditDialog,
  auditTab,
  filteredAuditChecks,
  onExportAuditExcel,
  onAuditDrilldown: _onAuditDrilldown,
  showTraceSelectDialog,
  traceSelectOptions,
  traceSelectCheck,
  isTracing,
  onTraceJump,
  onTraceReturn,
  consolBreakdownVisible,
  consolBreakdownAccountCode,
  onRvCtxViewConsolBreakdown,
  showCellFormulaDetail,
  cellDetailWpCode,
  cellDetailSheet,
  cellDetailLabel,
  onRvCtxViewFormulaSource,
  onCellDetailNavigate,
  onRvCellClick,
  onRvCellDblClick,
  onRvCellContextMenu,
  onRvCtxCopy,
  onRvCtxDrillDown,
  onRvCtxFormula,
  onRvCtxTrustScore,
  onRvCtxGoNote,
  onRvCtxOpenWorkpaper,
  onRvCtxViewAdjustments,
  onRvCtxSum,
  onRvCtxCompare,
  onRowNameClick,
  parseTraceLocations,
  openWorkpaper,
} = cellActions


async function _ensureProjectYearWrapper() {
  if (routeYear.value !== null) {
    projectYear.value = null
    return
  }
  // Delegate to composable (sets projectName, reportScope, templateType, _fetchedAuditYear via API)
  await ensureProjectYear()
  // Sync main-file-owned state from composable results
  projectYear.value = reportData._fetchedAuditYear.value
  selectedYear.value = projectYear.value || new Date().getFullYear() - 1
  selectedTemplateType.value = templateType.value
}

function onTabChange() {
  if (activeTab.value === 'cross_check' || activeTab.value === 'multi_year_compare') return
  fetchReport()
}

const _onSyncUnadjusted = withLoading(syncLoading, async () => {
  await recalcTrialBalance(projectId.value, year.value)
  await fetchReport()
  ElMessage.success('未审数已按四表账套科目重新同步')
})

// Wrapper: composable's onConsistencyCheck + open dialog
async function _onConsistencyCheckWrapper() {
  await onConsistencyCheck()
  if (consistencyResult.value) {
    showAuditDialog.value = true
  }
}

function onEditConfig() {
  router.push(`/projects/${projectId.value}/report-config`)
}

// Wrapper: calls composable's reloadReportContext + syncs main-file state
async function _reloadReportContextWrapper() {
  await _ensureProjectYearWrapper()
  await fetchReport()
}

// 初次加载（替代 onMounted 一次性加载）
_reloadReportContextWrapper()

// V3 Req 5.1：上下文（projectId/year）变化时自动重载（替代散落的 watch）
onContextChange(() => {
  _reloadReportContextWrapper()
})


const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const rvSearch = useTableSearch(rows, ['row_name', 'row_code'])

// ─── 拖拽框选（鼠标左键按住拖动选中连续区域） ──────────────────────────────
const rvTableRef = ref<any>(null)
const eqTableRef = ref<any>(null)
const impTableRef = ref<any>(null)
const compareTableRef = ref<any>(null)

// 通用取值函数（适配所有报表类型）
function getAnyCellValue(rowIdx: number, colIdx: number): any {
  const row = rows.value[rowIdx]
  if (!row) return null
  if (activeTab.value !== 'equity_statement' && activeTab.value !== 'impairment_provision') {
    if (colIdx === 2) return row.current_period_amount
    if (colIdx === 3) return row.prior_period_amount
    if (colIdx === 1) return row.row_name
    return row.row_code
  }
  if (colIdx === 0) return row.row_name
  return row.current_period_amount ?? ''
}

rvCtx.setupTableDrag(rvTableRef, getAnyCellValue)

// 权益表/减值表/对比表的拖拽支持（tab/mode 切换后动态绑定）
watch([activeTab, () => reportMode.value], () => {
  setTimeout(() => {
    const bindDrag = (tableRef: any) => {
      if (!tableRef.value) return
      const dom = tableRef.value.$el || tableRef.value
      if (!dom || dom._gtDragBound) return
      dom._gtDragBound = true

      function parseCellPos(target: HTMLElement) {
        const td = target.closest('td.el-table__cell') as HTMLElement | null
        if (!td) return null
        const tr = td.closest('tr') as HTMLElement | null
        const tbody = tr?.closest('tbody')
        if (!tr || !tbody) return null
        const rowIdx = Array.from(tbody.children).indexOf(tr)
        const colIdx = Array.from(tr.children).indexOf(td)
        return (rowIdx >= 0 && colIdx >= 0) ? { row: rowIdx, col: colIdx } : null
      }

      dom.addEventListener('mousedown', (e: MouseEvent) => {
        if (e.button !== 0) return
        const tag = (e.target as HTMLElement).tagName
        if (['INPUT', 'BUTTON', 'TEXTAREA', 'SELECT', 'A'].includes(tag)) return
        const pos = parseCellPos(e.target as HTMLElement)
        if (!pos) return
        const value = getAnyCellValue(pos.row, pos.col)
        if (e.shiftKey) {
          e.preventDefault()
          rvCtx.selectCell(pos.row, pos.col, value, false, true)
        } else if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault()
          rvCtx.startDrag(pos.row, pos.col, value)
        }
      })

      dom.addEventListener('mouseover', (e: MouseEvent) => {
        const pos = parseCellPos(e.target as HTMLElement)
        if (!pos) return
        rvCtx.updateDrag(pos.row, pos.col)
      })
    }
    bindDrag({ value: eqTableRef.value?.tableRef })
    bindDrag({ value: impTableRef.value?.tableRef })
    bindDrag(compareTableRef)
  }, 100)
}, { immediate: true })

// ─── 粘贴监听（Ctrl+V 粘贴 Excel 数据到选中区域） ──────────────────────────
const rvColumns = [
  { key: 'row_code', label: '行次' },
  { key: 'row_name', label: '项目' },
  { key: 'current_period_amount', label: '本期金额' },
  { key: 'prior_period_amount', label: '上期金额' },
]

setupPasteListener(rvTableRef, (event: ClipboardEvent) => {
  if (!rvCtx.selectedCells.value.length) return
  pasteToSelection(event, rvCtx.selectedCells.value, rows.value, rvColumns)
})

/** Ctrl+F 快捷键触发搜索栏（拦截浏览器默认搜索） */
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault()
    e.stopPropagation()
    rvSearch.toggle()
  }
}

function rvCellClassName({ rowIndex, columnIndex }: any) {
  const classes: string[] = []
  const selClass = rvCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  const ccClass = rvComments.commentCellClass(`report_${activeTab.value}`, rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

// ─── 全屏与复制 ──────────────────────────────────────────────────────────────
const { isFullscreen: rvFullscreen, toggleFullscreen: toggleRvFullscreen } = useFullscreen()
</script>

<style scoped src="./report-view.css" />
<style>
/* 平衡检查跳转高亮动画 */
.gt-highlight-row {
  animation: gt-row-flash 0.6s ease-in-out 3;
}
@keyframes gt-row-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: rgba(75, 45, 119, 0.12); }
}
</style>
