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

      <!-- F29: 报表平衡检查结果 -->
      <el-alert
        v-if="balanceCheckResult"
        :title="balanceCheckResult.status === 'passed' ? '报表平衡检查通过' : balanceCheckResult.status === 'warning' ? '报表平衡检查有差异' : '报表平衡检查失败'"
        :type="balanceCheckResult.status === 'passed' ? 'success' : balanceCheckResult.status === 'warning' ? 'warning' : 'error'"
        :description="balanceCheckResult.message"
        show-icon
        :closable="true"
        style="margin-bottom: 8px"
        @close="balanceCheckResult = null"
      />

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

    <!-- 所有者权益变动表 — el-table 矩阵视图（动态列 v-for + span-method） -->
    <div v-if="activeTab === 'equity_statement'" class="gt-rv-equity-matrix" v-loading="loading">
      <el-table ref="eqTableRef" :data="rows" border size="small" :span-method="equitySpanMethod"
        :row-class-name="eqRowClassName" style="width: 100%" max-height="600"
        :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
        :cell-class-name="rvCellClassName"
        @cell-click="onRvCellClick"
        @cell-dblclick="onRvCellDblClick"
        @cell-contextmenu="onRvCellContextMenu"
        :header-cell-style="{ background: '#f8f6fb', color: '#333', whiteSpace: 'nowrap', fontSize: '12px' }">
        <el-table-column prop="row_name" label="项目" fixed width="280" :resizable="true">
          <template #default="{ row }">
            <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
          </template>
        </el-table-column>
        <!-- 本年金额 — 动态列（三级表头：本年金额 > 分组 > 明细列） -->
        <el-table-column label="本年金额" header-align="center">
          <el-table-column label="实收资本(股本)" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'paid_in_capital')" /></template>
          </el-table-column>
          <el-table-column label="其他权益工具" header-align="center">
            <el-table-column label="优先股" width="90" align="right" :resizable="true">
              <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_preferred')" /></template>
            </el-table-column>
            <el-table-column label="永续债" width="90" align="right" :resizable="true">
              <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_perpetual')" /></template>
            </el-table-column>
            <el-table-column label="其他" width="90" align="right" :resizable="true">
              <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_other')" /></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="资本公积" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'capital_reserve')" /></template>
          </el-table-column>
          <el-table-column label="减：库存股" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'treasury_stock')" /></template>
          </el-table-column>
          <el-table-column label="其他综合收益" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'oci')" /></template>
          </el-table-column>
          <el-table-column label="专项储备" width="100" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'special_reserve')" /></template>
          </el-table-column>
          <el-table-column label="盈余公积" width="100" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'surplus_reserve')" /></template>
          </el-table-column>
          <el-table-column label="一般风险准备" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'general_risk')" /></template>
          </el-table-column>
          <el-table-column label="未分配利润" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'retained_earnings')" /></template>
          </el-table-column>
          <el-table-column v-if="isConsolidated" label="小计" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'subtotal')" /></template>
          </el-table-column>
          <el-table-column v-if="isConsolidated" label="少数股东权益" width="110" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'minority')" /></template>
          </el-table-column>
          <el-table-column label="所有者权益合计" width="120" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="row.current_period_amount" /></template>
          </el-table-column>
        </el-table-column>
        <!-- 上年金额 — 三级表头（与本年金额结构一致） -->
        <el-table-column label="上年金额" header-align="center">
          <el-table-column label="实收资本(股本)" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="其他权益工具" header-align="center">
            <el-table-column label="优先股" width="90" align="right" :resizable="true">
              <template #default><GtAmountCell :value="0" /></template>
            </el-table-column>
            <el-table-column label="永续债" width="90" align="right" :resizable="true">
              <template #default><GtAmountCell :value="0" /></template>
            </el-table-column>
            <el-table-column label="其他" width="90" align="right" :resizable="true">
              <template #default><GtAmountCell :value="0" /></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="资本公积" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="减：库存股" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="其他综合收益" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="专项储备" width="100" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="盈余公积" width="100" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="一般风险准备" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="未分配利润" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column v-if="isConsolidated" label="小计" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column v-if="isConsolidated" label="少数股东权益" width="110" align="right" :resizable="true">
            <template #default><GtAmountCell :value="0" /></template>
          </el-table-column>
          <el-table-column label="所有者权益合计" width="120" align="right" :resizable="true">
            <template #default="{ row }"><GtAmountCell :value="row.prior_period_amount" /></template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <p v-if="rows.length === 0" class="gt-rv-eq-hint">提示：权益变动表为矩阵结构，各列金额需在项目导入数据后自动填充。</p>
    </div>

    <!-- 资产减值准备表 — el-table 矩阵视图（嵌套列） -->
    <div v-if="activeTab === 'impairment_provision'" class="gt-rv-equity-matrix" v-loading="loading">
      <el-table ref="impTableRef" :data="rows" border size="small"
        :row-class-name="impRowClassName" style="width: 100%" max-height="600"
        :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
        :cell-class-name="rvCellClassName"
        @cell-click="onRvCellClick"
        @cell-dblclick="onRvCellDblClick"
        @cell-contextmenu="onRvCellContextMenu"
        :header-cell-style="{ background: '#f8f6fb', color: '#333', whiteSpace: 'nowrap', fontSize: '12px' }">
        <el-table-column prop="row_name" label="项目" fixed width="280" :resizable="true">
          <template #default="{ row }">
            <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="年初账面余额" width="130" align="right" :resizable="true">
          <template #default="{ row }">
            <GtAmountCell :value="row.prior_period_amount" />
          </template>
        </el-table-column>
        <!-- 本期增加额 — 嵌套列 -->
        <el-table-column label="本期增加额">
          <el-table-column v-for="col in impIncCols" :key="'inc-' + col.key" :label="col.label" width="110" align="right" :resizable="true">
            <template #default>
              <GtAmountCell :value="0" />
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 本期减少额 — 嵌套列 -->
        <el-table-column label="本期减少额">
          <el-table-column v-for="col in impDecCols" :key="'dec-' + col.key" :label="col.label" width="110" align="right" :resizable="true">
            <template #default>
              <GtAmountCell :value="0" />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末账面余额" width="130" align="right" :resizable="true">
          <template #default="{ row }">
            <GtAmountCell :value="row.current_period_amount" />
          </template>
        </el-table-column>
      </el-table>
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

    <!-- Sprint 4 Task 4.3：附注引用我（侧栏 drawer） -->
    <el-drawer
      v-model="noteRefsVisible"
      :title="`附注引用我 — ${noteRefsRowName || ''}`"
      direction="rtl"
      size="380px"
      append-to-body
      :destroy-on-close="false"
    >
      <div v-loading="noteRefsLoading" class="gt-rv-note-refs">
        <div class="gt-rv-note-refs__header">
          <span class="gt-rv-note-refs__label">报表行</span>
          <code class="gt-rv-note-refs__code">{{ noteRefsRowCode || '—' }}</code>
        </div>
        <el-empty
          v-if="!noteRefsLoading && noteRefsList.length === 0"
          :image-size="80"
          description="暂无附注引用此报表项"
        />
        <ul v-else class="gt-rv-note-refs__list">
          <li
            v-for="(ref, i) in noteRefsList"
            :key="`${ref.note_section}-${ref.table_index}-${i}`"
            class="gt-rv-note-refs__item"
            @click="onJumpToNoteSection(ref)"
          >
            <span class="gt-rv-note-refs__sec">{{ ref.note_section }}</span>
            <span v-if="ref.section_title" class="gt-rv-note-refs__title">{{ ref.section_title }}</span>
            <span v-if="ref.table_index > 0" class="gt-rv-note-refs__tbl">表 #{{ ref.table_index + 1 }}</span>
            <span class="gt-rv-note-refs__arrow">→</span>
          </li>
        </ul>
        <div v-if="noteRefsList.length > 0" class="gt-rv-note-refs__footer">
          共 {{ noteRefsList.length }} 处引用 · 点击跳转到附注编辑器
        </div>
      </div>
    </el-drawer>

    <!-- 穿透弹窗 -->
    <el-dialog append-to-body v-model="drilldownVisible" :title="`穿透查询 — ${drilldownData?.row_name || ''}`" width="700px">
      <div v-if="drilldownData" class="gt-rv-drilldown-content">
        <div class="gt-rv-dd-section">
          <span class="gt-rv-dd-label">公式：</span>
          <code>{{ drilldownData.formula }}</code>
        </div>
        <el-table :data="drilldownData.accounts" border size="small" style="margin-top: 12px">
          <el-table-column prop="code" label="科目编码" width="120" />
          <el-table-column prop="name" label="科目名称" min-width="200" />
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.amount" /></template>
          </el-table-column>
          <el-table-column label="底稿" width="100" align="center">
            <template #default="{ row }">
              <el-button v-if="row.wp_id" link type="primary" size="small"
                @click="openWorkpaper(row.wp_id)">打开底稿</el-button>
              <span v-else style="color: var(--gt-color-text-placeholder)">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else v-loading="drilldownLoading" style="min-height: 100px" />
    </el-dialog>

    <!-- Phase 3 F1.2: 报表行构成科目弹窗 -->
    <el-dialog
      append-to-body
      v-model="lineCompVisible"
      :title="`构成科目 — ${lineCompData?.item_name || ''}`"
      width="650px"
    >
      <div v-if="lineCompData" class="gt-rv-line-comp-content">
        <!-- 报表行汇总 -->
        <div class="gt-rv-line-comp-header">
          <span class="gt-rv-line-comp-label">报表行次</span>
          <div class="gt-rv-line-comp-summary">
            <span class="gt-rv-line-comp-name">{{ lineCompData.item_name }}</span>
            <GtAmountCell :value="lineCompData.total_amount" />
          </div>
        </div>

        <!-- 构成科目列表 -->
        <div class="gt-rv-line-comp-accounts">
          <span class="gt-rv-line-comp-label">构成科目（点击跳转试算表）</span>
          <el-table
            :data="lineCompData.accounts"
            border
            size="small"
            style="margin-top: 8px"
            :row-style="{ cursor: 'pointer' }"
            @row-click="(row: any) => onLineCompJumpToTB(row.code)"
          >
            <el-table-column prop="code" label="科目编码" width="120">
              <template #default="{ row }">
                <span class="gt-amt" style="color: var(--gt-color-primary)">{{ row.code }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="科目名称" min-width="180" />
            <el-table-column label="期末余额" width="150" align="right">
              <template #header>
                <span>期末余额</span>
                <span style="font-size: 10px; color: var(--gt-color-text-placeholder); margin-left: 4px">(元)</span>
              </template>
              <template #default="{ row }">
                <GtAmountCell :value="row.closing_balance" />
              </template>
            </el-table-column>
            <el-table-column label="占比" width="90" align="right">
              <template #default="{ row }">
                <span style="color: var(--gt-color-text-secondary); font-size: 12px">{{ row.pct?.toFixed(1) }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="" width="60" align="center">
              <template #default>
                <span style="color: var(--gt-color-primary); font-size: 12px">→</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 底部提示 -->
        <div class="gt-rv-line-comp-footer">
          <span style="color: var(--gt-color-text-tertiary); font-size: 12px">
            点击任意科目行可跳转到试算表定位（支持 Backspace 返回）
          </span>
        </div>
      </div>
      <div v-else v-loading="lineCompLoading" style="min-height: 100px" />
    </el-dialog>

    <!-- 公式管理弹窗 -->
    <FormulaManagerDialog
      v-model="showFormulaManager"
      :rows="rows"
      :project-id="projectId"
      :year="year"
      @saved="fetchReport"
      @applied="fetchReport"
    />

    <!-- 转换规则弹窗 -->
    <el-dialog append-to-body v-model="showMappingDialog" title="国企版 ↔ 上市版 转换规则" width="950px" top="3vh">
      <div class="gt-rv-mapping-dialog">
        <p style="color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); margin: 0 0 10px;">
          配置国企版与上市版各报表项目的映射关系。确认后系统将按规则自动转换，转换结果缓存到数据库。
        </p>
        <div style="display: flex; gap: 8px; margin-bottom: 10px; align-items: center; flex-wrap: wrap;">
          <el-button size="small" @click="loadPresetMappingAll" :loading="mappingLoading">一键加载全部预设</el-button>
          <el-button size="small" type="primary" @click="saveMappingRulesAll" :loading="mappingLoading" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">保存全部规则</el-button>
          <SharedTemplatePicker
            config-type="report_mapping"
            :project-id="projectId"
            :get-config-data="getMappingConfigData"
            @applied="onMappingTemplateApplied"
          />
          <span style="flex:1" />
          <span style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); line-height: 28px;">
            总计已映射 {{ totalMappedCount }} / {{ totalRuleCount }} 项
          </span>
        </div>
        <el-tabs v-model="mappingTab" type="card" size="small">
          <el-tab-pane v-for="rt in mappingReportTypes" :key="rt.key" :label="rt.label" :name="rt.key" />
        </el-tabs>
        <el-table :data="currentMappingRules" border size="small" max-height="420" style="width: 100%">
          <el-table-column label="国企版项目" min-width="200">
            <template #default="{ row }">
              <span>{{ row.soe_row_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="编码" width="110" align="center">
            <template #default="{ row }">
              <span style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">{{ row.soe_row_code }}</span>
            </template>
          </el-table-column>
          <el-table-column label="→" width="30" align="center">
            <template #default><span style="color: var(--gt-color-text-placeholder);">→</span></template>
          </el-table-column>
          <el-table-column label="上市版项目" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.listed_row_code" size="small" filterable clearable placeholder="选择" style="width: 100%;">
                <el-option v-for="opt in currentListedOptions" :key="opt.code" :label="opt.name" :value="opt.code">
                  <span style="font-size: var(--gt-font-size-xs);">{{ opt.code }} {{ opt.name }}</span>
                </el-option>
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="70" align="center">
            <template #default="{ row }">
              <span v-if="row.listed_row_code" style="color: var(--gt-color-success); font-size: var(--gt-font-size-xs);">✓</span>
              <span v-else style="color: var(--gt-color-coral); font-size: var(--gt-font-size-xs);">—</span>
            </template>
          </el-table-column>
        </el-table>
        <div style="margin-top: 8px; text-align: right; color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">
          {{ mappingTabLabel }} 已映射 {{ currentMappingRules.filter(r => r.listed_row_code).length }} / {{ currentMappingRules.length }} 项
        </div>
      </div>
    </el-dialog>

    <!-- 审核结果弹窗 -->
    <el-dialog append-to-body v-model="showAuditDialog" title="✅ 公式审核结果" width="95%" top="2vh" :close-on-click-modal="false">
      <div v-if="consistencyResult" class="gt-rv-audit-dialog">
        <!-- 汇总统计 -->
        <div class="gt-rv-audit-summary">
          <div class="gt-rv-audit-stat">
            <span class="gt-rv-audit-stat-num">{{ consistencyResult.total || 0 }}</span>
            <span class="gt-rv-audit-stat-label">审核公式</span>
          </div>
          <div class="gt-rv-audit-stat gt-rv-audit-stat-pass">
            <span class="gt-rv-audit-stat-num">{{ (consistencyResult.logic_check_passed || 0) + (consistencyResult.reasonability_passed || 0) }}</span>
            <span class="gt-rv-audit-stat-label">通过</span>
          </div>
          <div class="gt-rv-audit-stat gt-rv-audit-stat-fail">
            <span class="gt-rv-audit-stat-num">{{ (consistencyResult.total || 0) - (consistencyResult.logic_check_passed || 0) - (consistencyResult.reasonability_passed || 0) }}</span>
            <span class="gt-rv-audit-stat-label">未通过</span>
          </div>
          <div class="gt-rv-audit-stat" :class="consistencyResult.consistent ? 'gt-rv-audit-stat-pass' : 'gt-rv-audit-stat-fail'">
            <span class="gt-rv-audit-stat-num">{{ consistencyResult.consistent ? '✓' : '✗' }}</span>
            <span class="gt-rv-audit-stat-label">{{ consistencyResult.consistent ? '全部通过' : '存在异常' }}</span>
          </div>
        </div>

        <!-- 按类型分 Tab -->
        <el-tabs v-model="auditTab" type="card" size="small" style="margin-top: 10px;">
          <el-tab-pane name="all">
            <template #label>全部 ({{ consistencyResult.total || 0 }})</template>
          </el-tab-pane>
          <el-tab-pane name="logic_check">
            <template #label>🔍 逻辑审核 ({{ consistencyResult.logic_check_count || 0 }})</template>
          </el-tab-pane>
          <el-tab-pane name="reasonability">
            <template #label>💡 提示性审核 ({{ consistencyResult.reasonability_count || 0 }})</template>
          </el-tab-pane>
        </el-tabs>

        <!-- 逐条审核明细 -->
        <el-table :data="filteredAuditChecks" border size="small" style="width: 100%;"
          max-height="calc(100vh - 300px)"
          :row-class-name="({ row }: any) => row.passed ? '' : 'gt-rv-audit-fail-row'">
          <el-table-column label="结果" width="80" align="center">
            <template #default="{ row }">
              <span v-if="row.passed" style="color: var(--gt-color-success); font-size: var(--gt-font-size-md);">✓</span>
              <span v-else style="color: var(--gt-color-coral); font-size: var(--gt-font-size-md);">✗</span>
            </template>
          </el-table-column>
          <el-table-column label="审核项目" min-width="200">
            <template #default="{ row }">
              <span style="font-weight: 500;">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期望值" width="120" align="right">
            <template #default="{ row }">
              <GtAmountCell :value="row.expected" />
            </template>
          </el-table-column>
          <el-table-column label="实际值" width="120" align="right">
            <template #default="{ row }">
              <GtAmountCell :value="row.actual" />
            </template>
          </el-table-column>
          <el-table-column label="差额" width="110" align="right">
            <template #default="{ row }">
              <GtAmountCell :value="row.diff" />
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100" align="center">
            <template #default="{ row }">
              <span style="font-size: var(--gt-font-size-xs);">{{ row.category_label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公式/来源" min-width="160">
            <template #default="{ row }">
              <code v-if="row.formula" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); word-break: break-all; white-space: normal;">{{ row.formula }}</code>
              <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">{{ row.source || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="溯源定位" min-width="180">
            <template #default="{ row }">
              <div v-if="row.source || row.formula" style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">
                <template v-for="loc in parseTraceLocations(row)" :key="loc.label">
                  <el-button size="small" link type="primary" @click="onTraceJump(loc)" style="font-size: var(--gt-font-size-xs);">
                    📍 {{ loc.label }}
                  </el-button>
                </template>
                <span v-if="!parseTraceLocations(row).length" style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs);">—</span>
              </div>
              <span v-else style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs);">—</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 底部操作栏 -->
        <div style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
            共 {{ filteredAuditChecks.length }} 条审核项
          </span>
          <el-button size="small" @click="onExportAuditExcel" round>📥 导出审核报告</el-button>
        </div>
      </div>
      <div v-else style="text-align: center; padding: 40px; color: var(--gt-color-text-tertiary);">
        暂无审核数据，请先点击"✅ 审核"按钮
      </div>
    </el-dialog>

    <!-- 溯源定位选择弹窗（多个定位时） -->
    <el-dialog append-to-body v-model="showTraceSelectDialog" title="选择溯源定位" width="500px">
      <p style="color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); margin: 0 0 12px;">
        该审核项涉及多个报表位置，请选择要查看的定位：
      </p>
      <div v-if="traceSelectCheck" style="margin-bottom: 12px; padding: 8px 12px; background: var(--gt-color-primary-bg); border-radius: 8px; font-size: var(--gt-font-size-xs);">
        <span style="font-weight: 600;">{{ traceSelectCheck.name }}</span>
        <code v-if="traceSelectCheck.formula" style="display: block; margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ traceSelectCheck.formula }}</code>
      </div>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <el-button v-for="loc in traceSelectOptions" :key="loc.rowCode || loc.label"
          @click="onTraceJump(loc)" style="justify-content: flex-start; text-align: left;">
          📍 {{ loc.label }}
        </el-button>
      </div>
    </el-dialog>

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showReportImport"
      import-type="report"
      :project-id="projectId"
      :year="year"
      :sub-type="activeTab"
      @imported="onReportImported"
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

  <!-- Sprint 5.6: 公式来源弹窗 -->
  <CellFormulaDetail
    :visible="showCellFormulaDetail"
    module="REPORT"
    :wp-code="cellDetailWpCode"
    :sheet-name="cellDetailSheet"
    :label="cellDetailLabel"
    @update:visible="showCellFormulaDetail = $event"
    @navigate="onCellDetailNavigate"
  />

  <!-- 合并报表穿透弹窗（统一组件，source=report）：右键"查看合并明细"打开 -->
  <ConsolBreakdownDialog
    v-model="consolBreakdownVisible"
    source="report"
    :project-id="projectId"
    :year="year"
    :account-code="consolBreakdownAccountCode"
  />

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

  <!-- 数字溯源弹窗（lineage endpoint） -->
  <el-dialog v-model="rvTraceDialogVisible" title="🔍 数字溯源" width="700px" append-to-body destroy-on-close>
    <div v-loading="rvTraceLoading" style="min-height:120px">
      <template v-if="rvTraceResult">
        <div v-if="rvTraceResult.upstream.length || rvTraceResult.downstream.length">
          <h4 style="margin:0 0 8px">上游来源</h4>
          <el-table v-if="rvTraceResult.upstream.length" :data="rvTraceResult.upstream" size="small" border stripe max-height="200">
            <el-table-column prop="wp_code" label="底稿编码" width="120" />
            <el-table-column prop="label" label="描述" min-width="200" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="onRvTraceLocate(row)">定位</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无上游来源" :image-size="40" />
          <h4 style="margin:16px 0 8px">下游引用</h4>
          <el-table v-if="rvTraceResult.downstream.length" :data="rvTraceResult.downstream" size="small" border stripe max-height="200">
            <el-table-column prop="wp_code" label="底稿编码" width="120" />
            <el-table-column prop="label" label="描述" min-width="200" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="onRvTraceLocate(row)">定位</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无下游引用" :image-size="40" />
        </div>
        <el-empty v-else description="该数字暂无溯源信息" :image-size="60" />
      </template>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, watchEffect, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import MultiYearCompare from '@/components/report/MultiYearCompare.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CellFormulaDetail from '@/components/CellFormulaDetail.vue'
import ConsolBreakdownDialog from '@/components/consolidation/ConsolBreakdownDialog.vue'
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

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
const rvCtx = useCellSelection()
const rvPenetrate = usePenetrate()
const rvComments = useCellComments(() => projectId.value, () => year.value, 'report')


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
    bindDrag(eqTableRef)
    bindDrag(impTableRef)
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
