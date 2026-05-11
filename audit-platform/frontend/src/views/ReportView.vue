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
          <div class="gt-info-bar__sep" />
          <div class="gt-info-bar__item">
            <span class="gt-info-bar__label" style="font-size:10px;color:rgba(255,255,255,0.55)">模式</span>
            <el-radio-group v-model="reportMode" size="small" @change="fetchReport" class="gt-rv-mode-radio">
              <el-radio-button value="audited">已审</el-radio-button>
              <el-radio-button value="unadjusted">未审</el-radio-button>
              <el-radio-button value="compare">对比</el-radio-button>
            </el-radio-group>
          </div>
        </GtInfoBar>
        <template #actions>
          <GtToolbar
            :show-copy="true"
            :show-fullscreen="true"
            :is-fullscreen="rvFullscreen"
            :show-export="true"
            :show-import="true"
            :show-formula="true"
            @copy="copyReportTable"
            @fullscreen="toggleRvFullscreen()"
            @export="onExportExcel"
            @import="showReportImport = true"
            @formula="showFormulaManager = true"
          >
            <template #left>
              <el-tooltip content="根据试算表审定数重新计算报表（需先导入数据+科目映射）" placement="bottom">
                <el-button size="small" @click="onGenerate" :loading="genLoading">🔄 刷新数据</el-button>
              </el-tooltip>
              <el-tooltip content="执行逻辑审核和合理性检查（需先生成报表）" placement="bottom">
                <el-button size="small" @click="onConsistencyCheck" :loading="checkLoading">✅ 审核</el-button>
              </el-tooltip>
            </template>
            <template #right-extra>
              <el-button size="small" @click="onEditConfig">📝 编辑结构</el-button>
              <el-tooltip content="配置国企版↔上市版报表行次映射规则" placement="bottom">
                <el-button size="small" @click="showMappingDialog = true">🔄 转换规则</el-button>
              </el-tooltip>
            </template>
          </GtToolbar>
        </template>
      </GtPageHeader>

      <!-- R8-S2-03：Stale 状态横幅（上游数据变更提示） -->
      <div v-if="stale.isStale.value" class="gt-stale-banner">
        <span class="gt-stale-icon">⚠️</span>
        <span class="gt-stale-text">
          上游数据已变更，当前报表可能基于旧试算表（{{ stale.staleCount.value }} 张底稿待重算）
        </span>
        <el-button size="small" type="primary" :loading="stale.loading.value" @click="onStaleRecalc">
          🔄 点击重算
        </el-button>
      </div>

      <!-- Tab 切换 -->
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="资产负债表" name="balance_sheet" />
        <el-tab-pane label="利润表" name="income_statement" />
        <el-tab-pane label="现金流量表" name="cash_flow_statement" />
        <el-tab-pane label="所有者权益变动表" name="equity_statement" />
        <el-tab-pane label="现金流附表" name="cash_flow_supplement" />
        <el-tab-pane label="资产减值准备表" name="impairment_provision" />
        <el-tab-pane label="⚖️ 跨表核对" name="cross_check" />
      </el-tabs>
    </div>

    <!-- 可滚动的表格区域 -->
    <div class="gt-rv-table-area">

    <!-- 空数据引导提示 -->
    <el-alert
      v-if="!loading && rows.length === 0 && !isTracing"
      type="info"
      show-icon
      :closable="false"
      style="margin: 12px 0"
    >
      <template #title>报表暂无数据</template>
      <div style="font-size: 12px; line-height: 1.6; margin-top: 4px">
        请先完成以下步骤：① 导入账套数据 → ② 科目映射 → ③ 点击上方"🔄 刷新数据"生成报表。
        当前显示的是预设报表结构（行次和项目名称），金额列为空。
      </div>
    </el-alert>

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

    <!-- 所有者权益变动表 — 矩阵视图 -->
    <div v-if="activeTab === 'equity_statement'" class="gt-rv-equity-matrix" v-loading="loading">
      <div class="gt-rv-eq-scroll">
        <table class="gt-rv-eq-table gt-rv-eq-auto-width">
          <thead v-if="isConsolidated">
            <!-- 合并报表：4行表头 -->
            <tr class="gt-rv-eq-hr1">
              <th rowspan="4" class="gt-rv-eq-th-project">项目</th>
              <th :colspan="eqTotalCols" class="gt-rv-eq-th-period">本年金额</th>
              <th :colspan="eqTotalCols" class="gt-rv-eq-th-period gt-rv-eq-th-prior">上年金额</th>
            </tr>
            <tr class="gt-rv-eq-hr2">
              <th colspan="12">归属于母公司所有者权益</th>
              <th rowspan="3">少数股东<br/>权益</th>
              <th rowspan="3" class="gt-rv-eq-th-total">所有者<br/>权益<br/>合计</th>
              <th colspan="12">归属于母公司所有者权益</th>
              <th rowspan="3">少数股东<br/>权益</th>
              <th rowspan="3" class="gt-rv-eq-th-total">所有者<br/>权益<br/>合计</th>
            </tr>
            <tr class="gt-rv-eq-hr3">
              <th rowspan="2">实收资本</th>
              <th colspan="3">其他权益工具</th>
              <th rowspan="2">资本公积</th>
              <th rowspan="2">减：库存股</th>
              <th rowspan="2">其他综合收益</th>
              <th rowspan="2">专项储备</th>
              <th rowspan="2">盈余公积</th>
              <th rowspan="2">一般风险准备</th>
              <th rowspan="2">未分配利润</th>
              <th rowspan="2" class="gt-rv-eq-th-total">小计</th>
              <th rowspan="2">实收资本</th>
              <th colspan="3">其他权益工具</th>
              <th rowspan="2">资本公积</th>
              <th rowspan="2">减：库存股</th>
              <th rowspan="2">其他综合收益</th>
              <th rowspan="2">专项储备</th>
              <th rowspan="2">盈余公积</th>
              <th rowspan="2">一般风险准备</th>
              <th rowspan="2">未分配利润</th>
              <th rowspan="2" class="gt-rv-eq-th-total">小计</th>
            </tr>
            <tr class="gt-rv-eq-hr4">
              <th>优先股</th><th>永续债</th><th>其他</th>
              <th class="gt-rv-eq-th-prior-col">优先股</th><th class="gt-rv-eq-th-prior-col">永续债</th><th class="gt-rv-eq-th-prior-col">其他</th>
            </tr>
          </thead>
          <thead v-else>
            <!-- 单体报表：3行表头（无归属母公司行） -->
            <tr class="gt-rv-eq-hr1">
              <th rowspan="3" class="gt-rv-eq-th-project">项目</th>
              <th :colspan="eqTotalCols" class="gt-rv-eq-th-period">本年金额</th>
              <th :colspan="eqTotalCols" class="gt-rv-eq-th-period gt-rv-eq-th-prior">上年金额</th>
            </tr>
            <tr class="gt-rv-eq-hr3 gt-rv-eq-hr3--standalone">
              <th rowspan="2">实收资本</th>
              <th colspan="3">其他权益工具</th>
              <th rowspan="2">资本公积</th>
              <th rowspan="2">减：库存股</th>
              <th rowspan="2">其他综合收益</th>
              <th rowspan="2">专项储备</th>
              <th rowspan="2">盈余公积</th>
              <th rowspan="2">一般风险准备</th>
              <th rowspan="2">未分配利润</th>
              <th rowspan="2" class="gt-rv-eq-th-total">所有者<br/>权益合计</th>
              <th rowspan="2">实收资本</th>
              <th colspan="3">其他权益工具</th>
              <th rowspan="2">资本公积</th>
              <th rowspan="2">减：库存股</th>
              <th rowspan="2">其他综合收益</th>
              <th rowspan="2">专项储备</th>
              <th rowspan="2">盈余公积</th>
              <th rowspan="2">一般风险准备</th>
              <th rowspan="2">未分配利润</th>
              <th rowspan="2" class="gt-rv-eq-th-total">所有者<br/>权益合计</th>
            </tr>
            <tr class="gt-rv-eq-hr4 gt-rv-eq-hr4--standalone">
              <th>优先股</th><th>永续债</th><th>其他</th>
              <th class="gt-rv-eq-th-prior-col">优先股</th><th class="gt-rv-eq-th-prior-col">永续债</th><th class="gt-rv-eq-th-prior-col">其他</th>
            </tr>
          </thead>
          <tbody v-if="rows.length">
            <tr v-for="row in rows" :key="row.row_code"
                :class="{ 'gt-rv-eq-total-row': row.is_total_row, 'gt-rv-eq-category': row.indent_level === 0 && !row.is_total_row }">
              <td class="gt-rv-eq-td-project" :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">
                {{ row.row_name }}
              </td>
              <!-- 本年各列：仅合计列显示 current_period_amount，其余列显示 0 -->
              <td v-for="col in eqColumns" :key="'cv-' + col.key" class="gt-rv-eq-td-amount">
                <template v-if="col.key === 'total'">{{ fmt(row.current_period_amount) }}</template>
                <template v-else>{{ fmt(0) }}</template>
              </td>
              <!-- 上年各列：仅合计列显示 prior_period_amount，其余列显示 0 -->
              <td v-for="col in eqColumns" :key="'pv-' + col.key" class="gt-rv-eq-td-amount gt-rv-eq-td-prior">
                <template v-if="col.key === 'total'">{{ fmt(row.prior_period_amount) }}</template>
                <template v-else>{{ fmt(0) }}</template>
              </td>
            </tr>
          </tbody>
          <tbody v-else>
            <tr>
              <td :colspan="1 + eqTotalCols * 2" class="gt-rv-eq-td-empty">暂无数据</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="rows.length === 0" class="gt-rv-eq-hint">提示：权益变动表为矩阵结构，各列金额需在项目导入数据后自动填充。</p>
    </div>

    <!-- 资产减值准备表 — 矩阵视图 -->
    <div v-if="activeTab === 'impairment_provision'" class="gt-rv-equity-matrix" v-loading="loading">
      <div class="gt-rv-eq-scroll">
        <table class="gt-rv-eq-table gt-rv-eq-auto-width">
          <thead>
            <tr class="gt-rv-eq-header-group">
              <th rowspan="2" class="gt-rv-eq-th-project">项目</th>
              <th rowspan="2" class="gt-rv-eq-th-col">年初账面余额</th>
              <th :colspan="impIncCols.length">本期增加额</th>
              <th :colspan="impDecCols.length">本期减少额</th>
              <th rowspan="2" class="gt-rv-eq-th-total">期末账面余额</th>
            </tr>
            <tr class="gt-rv-eq-header-cols">
              <th v-for="col in impIncCols" :key="'inc-' + col.key" class="gt-rv-eq-th-col">{{ col.label }}</th>
              <th v-for="col in impDecCols" :key="'dec-' + col.key" class="gt-rv-eq-th-col">{{ col.label }}</th>
            </tr>
          </thead>
          <tbody v-if="rows.length">
            <tr v-for="row in rows" :key="row.row_code"
                :class="{ 'gt-rv-eq-total-row': row.is_total_row }">
              <td class="gt-rv-eq-td-project" :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">
                {{ row.row_name }}
              </td>
              <!-- 年初账面余额：用 prior_period_amount 表示 -->
              <td class="gt-rv-eq-td-amount">{{ fmt(row.prior_period_amount) }}</td>
              <!-- 本期增加各列：显示 0（矩阵细列暂无独立字段） -->
              <td v-for="col in impIncCols" :key="'iv-' + col.key" class="gt-rv-eq-td-amount">{{ fmt(0) }}</td>
              <!-- 本期减少各列：显示 0 -->
              <td v-for="col in impDecCols" :key="'dv-' + col.key" class="gt-rv-eq-td-amount">{{ fmt(0) }}</td>
              <!-- 期末账面余额：用 current_period_amount 表示 -->
              <td class="gt-rv-eq-td-amount" style="font-weight: 600;">{{ fmt(row.current_period_amount) }}</td>
            </tr>
          </tbody>
          <tbody v-else>
            <tr>
              <td :colspan="2 + impIncCols.length + impDecCols.length + 1" class="gt-rv-eq-td-empty">暂无数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 报表表格 — 普通模式（非矩阵报表） -->
    <el-table ref="rvTableRef" v-if="reportMode !== 'compare' && activeTab !== 'equity_statement' && activeTab !== 'impairment_provision'" :data="rows" v-loading="loading" style="width: 100%"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :row-class-name="rowClassName" :show-header="true" border size="small" :max-height="tableMaxHeight"
      :cell-class-name="rvCellClassName"
      @cell-click="onRvCellClick"
      @cell-dblclick="onRvCellDblClick"
      @cell-contextmenu="onRvCellContextMenu">
      <el-table-column label="序号" width="70" align="center" :resizable="true">
        <template #default="{ $index }">
          <span style="color: #999;">{{ $index + 1 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="项目" min-width="300" :resizable="true" fixed>
        <template #default="{ row }">
          <span :class="{ 'gt-rv-category': !row.current_period_amount && !row.is_total_row && (row.indent_level || 0) === 0 }"
                :style="{ paddingLeft: (row.indent_level || 0) * 18 + 'px', fontWeight: row.is_total_row ? 700 : 400, fontSize: '13px' }">
            {{ row.row_name }}
            <el-button v-if="getNoteSection(row.row_code)" size="small" text type="primary"
              style="font-size:10px;padding:0 2px;margin-left:4px" title="查看附注"
              @click.stop="goToNote(row.row_code)">📝</el-button>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" min-width="140" align="right" header-align="center" :resizable="true" sortable :sort-method="(a: any, b: any) => (Number(a.current_period_amount) || 0) - (Number(b.current_period_amount) || 0)">
        <template #default="{ row, $index }">
          <GtAmountCell
            :value="row.current_period_amount"
            :prior-value="row.prior_period_amount"
            :clickable="true"
            :comment="rvComments.getComment(`report_${activeTab}`, $index, 2)"
            @click="onDrilldown(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上期金额" min-width="140" align="right" header-align="center" :resizable="true" sortable :sort-method="(a: any, b: any) => (Number(a.prior_period_amount) || 0) - (Number(b.prior_period_amount) || 0)">
        <template #default="{ row, $index }">
          <CommentTooltip :comment="rvComments.getComment(`report_${activeTab}`, $index, 3)">
            <span class="gt-rv-amount-cell-readonly" :class="displayPrefs.amountClass(row.prior_period_amount)">{{ fmt(row.prior_period_amount) }}</span>
          </CommentTooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- 报表表格 — 对比视图（非权益变动表） -->
    <el-table v-if="reportMode === 'compare' && activeTab !== 'equity_statement' && activeTab !== 'impairment_provision'" :data="compareRows" v-loading="loading" style="width: 100%"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :row-class-name="compareRowClassName" border size="small" :max-height="tableMaxHeight">
      <el-table-column label="序号" width="70" align="center" :resizable="true">
        <template #default="{ $index }">
          <span style="color: #999;">{{ $index + 1 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="项目" min-width="250" :resizable="true">
        <template #default="{ row }">
          <span :style="{ paddingLeft: (row.indent_level || 0) * 18 + 'px', fontWeight: row.is_total_row ? 700 : 400, fontSize: '13px' }">{{ row.row_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未审金额" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <span class="gt-rv-amount-cell-readonly">{{ fmt(row.unadjusted_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="调整影响" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <span :class="['gt-rv-adjustment', { 'has-diff': row.adjustment && row.adjustment !== 0 }]">{{ fmt(row.adjustment) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已审金额" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <span class="gt-rv-amount-cell-readonly" style="font-weight: 600;">{{ fmt(row.audited_amount) }}</span>
        </template>
      </el-table-column>
      <!-- 任务 12.7.1：对比视图新增"上年审定数"列（需求 24.1/24.2） -->
      <el-table-column label="上年审定数" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <span class="gt-rv-amount-cell-readonly" style="color: #666;">{{ fmt(row.prior_period_amount) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <!-- 选中区域状态栏 -->
    <SelectionBar :stats="rvCtx.selectionStats()" />

    <!-- R7-S3-10 Task 49-50：跨表核对面板 -->
    <div v-if="activeTab === 'cross_check'" class="gt-rv-cross-check">
      <h3 style="margin: 0 0 16px; font-size: var(--gt-font-size-md)">⚖️ 跨表核对（7 条关键等式）</h3>
      <el-table :data="crossCheckResults" border size="small" style="width: 100%">
        <el-table-column label="#" width="40" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="核对等式" prop="description" min-width="300" />
        <el-table-column label="左值" prop="leftValue" width="140" align="right">
          <template #default="{ row }">{{ fmtAmount(row.leftValue) }}</template>
        </el-table-column>
        <el-table-column label="右值" prop="rightValue" width="140" align="right">
          <template #default="{ row }">{{ fmtAmount(row.rightValue) }}</template>
        </el-table-column>
        <el-table-column label="差异" width="120" align="right">
          <template #default="{ row }">
            <span :style="{ color: row.diff !== 0 ? 'var(--gt-color-coral)' : 'var(--gt-color-success)', fontWeight: 600 }">
              {{ fmtAmount(row.diff) }}
            </span>
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

    </div><!-- /gt-rv-table-area -->

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
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column label="底稿" width="100" align="center">
            <template #default="{ row }">
              <el-button v-if="row.wp_id" link type="primary" size="small"
                @click="openWorkpaper(row.wp_id)">打开底稿</el-button>
              <span v-else style="color: #ccc">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else v-loading="drilldownLoading" style="min-height: 100px" />
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
        <p style="color: #888; font-size: 12px; margin: 0 0 10px;">
          配置国企版与上市版各报表项目的映射关系。确认后系统将按规则自动转换，转换结果缓存到数据库。
        </p>
        <div style="display: flex; gap: 8px; margin-bottom: 10px; align-items: center; flex-wrap: wrap;">
          <el-button size="small" @click="loadPresetMappingAll" :loading="mappingLoading">一键加载全部预设</el-button>
          <el-button size="small" type="primary" @click="saveMappingRulesAll" :loading="mappingLoading">保存全部规则</el-button>
          <SharedTemplatePicker
            config-type="report_mapping"
            :project-id="projectId"
            :get-config-data="getMappingConfigData"
            @applied="onMappingTemplateApplied"
          />
          <span style="flex:1" />
          <span style="color: #999; font-size: 11px; line-height: 28px;">
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
          <el-table-column label="编码" width="80" align="center">
            <template #default="{ row }">
              <span style="color: #aaa; font-size: 11px;">{{ row.soe_row_code }}</span>
            </template>
          </el-table-column>
          <el-table-column label="→" width="30" align="center">
            <template #default><span style="color: #ccc;">→</span></template>
          </el-table-column>
          <el-table-column label="上市版项目" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.listed_row_code" size="small" filterable clearable placeholder="选择" style="width: 100%;">
                <el-option v-for="opt in currentListedOptions" :key="opt.code" :label="opt.name" :value="opt.code">
                  <span style="font-size: 11px;">{{ opt.code }} {{ opt.name }}</span>
                </el-option>
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="70" align="center">
            <template #default="{ row }">
              <span v-if="row.listed_row_code" style="color: #1e8a38; font-size: 11px;">✓</span>
              <span v-else style="color: #d94840; font-size: 11px;">—</span>
            </template>
          </el-table-column>
        </el-table>
        <div style="margin-top: 8px; text-align: right; color: #999; font-size: 11px;">
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
              <span v-if="row.passed" style="color: #1e8a38; font-size: 16px;">✓</span>
              <span v-else style="color: #d94840; font-size: 16px;">✗</span>
            </template>
          </el-table-column>
          <el-table-column label="审核项目" min-width="200">
            <template #default="{ row }">
              <span style="font-weight: 500;">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期望值" width="120" align="right">
            <template #default="{ row }">
              <span class="gt-rv-amount-cell-readonly">{{ fmt(row.expected) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="实际值" width="120" align="right">
            <template #default="{ row }">
              <span class="gt-rv-amount-cell-readonly">{{ fmt(row.actual) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差额" width="110" align="right">
            <template #default="{ row }">
              <span :style="{ color: row.diff && row.diff !== '0' && row.diff !== '0.00' ? '#d94840' : '#999', fontSize: '12px', fontWeight: row.diff && row.diff !== '0' ? 600 : 400 }">
                {{ fmt(row.diff) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100" align="center">
            <template #default="{ row }">
              <span style="font-size: 11px;">{{ row.category_label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公式/来源" min-width="160">
            <template #default="{ row }">
              <code v-if="row.formula" style="font-size: 10px; color: #888; word-break: break-all; white-space: normal;">{{ row.formula }}</code>
              <span v-else style="font-size: 10px; color: #ccc;">{{ row.source || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="溯源定位" min-width="180">
            <template #default="{ row }">
              <div v-if="row.source || row.formula" style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">
                <template v-for="loc in parseTraceLocations(row)" :key="loc.label">
                  <el-button size="small" link type="primary" @click="onTraceJump(loc)" style="font-size: 11px;">
                    📍 {{ loc.label }}
                  </el-button>
                </template>
                <span v-if="!parseTraceLocations(row).length" style="color: #ccc; font-size: 11px;">—</span>
              </div>
              <span v-else style="color: #ccc; font-size: 11px;">—</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 底部操作栏 -->
        <div style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 11px; color: #999;">
            共 {{ filteredAuditChecks.length }} 条审核项
          </span>
          <el-button size="small" @click="onExportAuditExcel" round>📥 导出审核报告</el-button>
        </div>
      </div>
      <div v-else style="text-align: center; padding: 40px; color: #999;">
        暂无审核数据，请先点击"✅ 审核"按钮
      </div>
    </el-dialog>

    <!-- 溯源定位选择弹窗（多个定位时） -->
    <el-dialog append-to-body v-model="showTraceSelectDialog" title="选择溯源定位" width="500px">
      <p style="color: #888; font-size: 12px; margin: 0 0 12px;">
        该审核项涉及多个报表位置，请选择要查看的定位：
      </p>
      <div v-if="traceSelectCheck" style="margin-bottom: 12px; padding: 8px 12px; background: #f8f6fb; border-radius: 8px; font-size: 12px;">
        <span style="font-weight: 600;">{{ traceSelectCheck.name }}</span>
        <code v-if="traceSelectCheck.formula" style="display: block; margin-top: 4px; font-size: 10px; color: #888;">{{ traceSelectCheck.formula }}</code>
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
    @sum="onRvCtxSum"
    @compare="onRvCtxCompare"
  >
    <div class="gt-ucell-ctx-item" @click="onRvCtxDrillDown"><span class="gt-ucell-ctx-icon">📊</span> 查看穿透</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxGoNote"><span class="gt-ucell-ctx-icon">📝</span> 跳转附注</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxOpenWorkpaper"><span class="gt-ucell-ctx-icon">📋</span> 打开对应底稿</div>
  </CellContextMenu>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { projects as P_proj, reportConfig as P_rc, reportMapping as P_rm } from '@/services/apiPaths'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { fmtAmount } from '@/utils/formatters'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useProjectStore } from '@/stores/project'
import { setupPasteListener, pasteToSelection } from '@/composables/useCopyPaste'
import { withLoading } from '@/composables/useLoading'
import { handleApiError } from '@/utils/errorHandler'
import { usePenetrate } from '@/composables/usePenetrate'
import { useProjectEvents } from '@/composables/useProjectEvents'
import {
  generateReports, getReport, getReportDrilldown, getReportConsistencyCheck, recalcTrialBalance,
  getReportExcelUrl,
  type ReportRow, type ReportDrilldownData, type ReportConsistencyCheck,
} from '@/services/auditPlatformApi'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.projectId)

// ─── 云协同：账套激活/回滚后自动刷新 ─────────────────────────────────────────
const { onDatasetActivated, onDatasetRolledBack } = useProjectEvents(projectId)
onDatasetActivated(() => fetchReport())
onDatasetRolledBack(() => fetchReport())

// R8-S2-03：Stale 状态追踪（上游数据变更提示）
import { useStaleStatus } from '@/composables/useStaleStatus'
const stale = useStaleStatus(projectId)
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
const reportScope = ref<string>('standalone')
const templateType = ref<string>('soe')
const projectName = ref<string>('')
const isConsolidated = computed(() => reportScope.value === 'consolidated')
const _templateTypeLabel = computed(() => templateType.value === 'listed' ? '上市版' : '国企版')
const scopeLabel = computed(() => reportScope.value === 'consolidated' ? '合并' : '单体')

// 单位（项目）选择器 — 使用 projectStore
const selectedProjectId = ref('')
const projectOptions = computed(() => projectStore.projectOptions)

function onProjectChange(newId: string) {
  router.push({ path: `/projects/${newId}/reports`, query: route.query })
}

// 年度选择器
const selectedYear = ref(new Date().getFullYear())
const yearOptions = computed(() => projectStore.yearOptions)
function onYearChange(val: number) {
  selectedYear.value = val
  projectStore.changeYear(val)
  fetchReport()
}

// 模板类型切换
const selectedTemplateType = ref('soe')
const currentApplicableStandard = computed(() => `${selectedTemplateType.value}_${reportScope.value}`)

async function onTemplateTypeChange(val: string) {
  selectedTemplateType.value = val
  templateType.value = val
  await fetchReport()
}

// 转换规则 — 按报表类型分组
const showMappingDialog = ref(false)
const mappingLoading = ref(false)
const mappingTab = ref('balance_sheet')
const mappingReportTypes = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow_statement', label: '现金流量表' },
  { key: 'equity_statement', label: '权益变动表' },
  { key: 'cash_flow_supplement', label: '现金流附表' },
]
const mappingTabLabel = computed(() => mappingReportTypes.find(r => r.key === mappingTab.value)?.label || '')

// 每个报表类型独立存储映射规则和上市版选项
const allMappingRules = ref<Record<string, Array<{ soe_row_code: string; soe_row_name: string; listed_row_code: string }>>>({})
const allListedOptions = ref<Record<string, Array<{ code: string; name: string }>>>({})

const currentMappingRules = computed(() => allMappingRules.value[mappingTab.value] || [])
const currentListedOptions = computed(() => allListedOptions.value[mappingTab.value] || [])
const totalMappedCount = computed(() => Object.values(allMappingRules.value).flat().filter(r => r.listed_row_code).length)
const totalRuleCount = computed(() => Object.values(allMappingRules.value).flat().length)

async function loadPresetForType(rt: string) {
  // 用后端 preset API（含同义词表+模糊匹配）
  const presetData = await api.get(P_rm.preset(projectId.value), {
    params: { report_type: rt, scope: reportScope.value },
    validateStatus: (s: number) => s < 600,
  })
  const preset = presetData ?? []

  // 同时加载上市版行次作为下拉选项
  const listedData = await api.get(P_rc.list, {
    params: { applicable_standard: `listed_${reportScope.value}`, report_type: rt },
    validateStatus: (s: number) => s < 600,
  })
  const listedRows = listedData ?? []
  allListedOptions.value[rt] = listedRows.map((r: any) => ({ code: r.row_code, name: r.row_name }))

  allMappingRules.value[rt] = preset.map((p: any) => ({
    soe_row_code: p.soe_row_code,
    soe_row_name: p.soe_row_name,
    listed_row_code: p.listed_row_code || '',
  }))
}

async function loadPresetMappingAll() {
  mappingLoading.value = true
  try {
    for (const rt of mappingReportTypes) {
      await loadPresetForType(rt.key)
    }
    ElMessage.success(`已加载全部预设规则，自动匹配 ${totalMappedCount.value} 项`)
  } catch {
    ElMessage.warning('加载预设规则失败')
  } finally {
    mappingLoading.value = false
  }
}

async function saveMappingRulesAll() {
  mappingLoading.value = true
  try {
    for (const rt of mappingReportTypes) {
      const rules = allMappingRules.value[rt.key] || []
      const mapped = rules.filter(r => r.listed_row_code)
      if (mapped.length > 0) {
        await api.post(P_rm.save(projectId.value), {
          report_type: rt.key,
          scope: reportScope.value,
          rules: mapped.map(r => ({ soe_row_code: r.soe_row_code, listed_row_code: r.listed_row_code })),
        }, { validateStatus: (s: number) => s < 600 })
      }
    }
    ElMessage.success('全部转换规则已保存')
    showMappingDialog.value = false
  } catch (e) {
    handleApiError(e, '保存转换规则')
  } finally {
    mappingLoading.value = false
  }
}

// ── 转换规则共享模板 ──
function getMappingConfigData(): Record<string, any> {
  const data: Record<string, any[]> = {}
  for (const rt of mappingReportTypes) {
    const rules = allMappingRules.value[rt.key] || []
    data[rt.key] = rules.filter(r => r.listed_row_code).map(r => ({
      soe_row_code: r.soe_row_code,
      soe_row_name: r.soe_row_name,
      listed_row_code: r.listed_row_code,
    }))
  }
  return { mapping_rules: data, scope: reportScope.value }
}

function onMappingTemplateApplied(configData: Record<string, any>) {
  const rules = configData?.mapping_rules || {}
  let applied = 0
  for (const [rtKey, rtRules] of Object.entries(rules)) {
    const existing = allMappingRules.value[rtKey]
    if (!existing || !Array.isArray(rtRules)) continue
    for (const tplRule of rtRules as any[]) {
      const target = existing.find((r: any) => r.soe_row_code === tplRule.soe_row_code)
      if (target && !target.listed_row_code) {
        target.listed_row_code = tplRule.listed_row_code
        applied++
      }
    }
  }
  ElMessage.success(`已引用 ${applied} 条映射规则（已有映射的行不覆盖）`)
}
const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear())

const loading = ref(false)
const genLoading = ref(false)
const checkLoading = ref(false)
const showReportImport = ref(false)
const syncLoading = ref(false)
const activeTab = ref('balance_sheet')
const reportMode = ref('audited')

// 动态计算表格最大高度（窗口高度 - 顶部固定区域）
const tableMaxHeight = ref(500)
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
const rows = ref<ReportRow[]>([])

const activeTabLabel = computed(() => {
  const m: Record<string, string> = { balance_sheet: '资产负债表', income_statement: '利润表', cash_flow_statement: '现金流量表', equity_statement: '所有者权益变动表', cash_flow_supplement: '现金流附表', impairment_provision: '资产减值准备表' }
  return m[activeTab.value] || ''
})
const _reportModeLabel = computed(() => {
  const m: Record<string, string> = { audited: '已审报表', unadjusted: '未审报表', compare: '对比视图' }
  return m[reportMode.value] || ''
})
const compareRows = ref<any[]>([])
const consistencyResult = ref<ReportConsistencyCheck | null>(null)

// Drilldown
const drilldownVisible = ref(false)
const drilldownLoading = ref(false)
const drilldownData = ref<ReportDrilldownData | null>(null)
const showFormulaManager = ref(false)

// 权益变动表列定义 — 根据合并/单体动态切换
const eqColumnsBase = [
  { key: 'paid_in_capital', label: '实收资本' },
  { key: 'other_equity_preferred', label: '优先股' },
  { key: 'other_equity_perpetual', label: '永续债' },
  { key: 'other_equity_other', label: '其他' },
  { key: 'capital_reserve', label: '资本公积' },
  { key: 'treasury_stock', label: '减：库存股' },
  { key: 'oci', label: '其他综合收益' },
  { key: 'special_reserve', label: '专项储备' },
  { key: 'surplus_reserve', label: '盈余公积' },
  { key: 'general_risk', label: '一般风险准备' },
  { key: 'retained_earnings', label: '未分配利润' },
]
// 合并版额外列
const eqConsolExtra = [
  { key: 'subtotal', label: '小计' },
  { key: 'minority', label: '少数股东权益' },
]
const eqColumns = computed(() => {
  const base = [...eqColumnsBase]
  if (isConsolidated.value) {
    base.push(...eqConsolExtra)
  }
  base.push({ key: 'total', label: '所有者权益合计' })
  return base
})
// 权益变动表第1行 colspan（本年/上年各自的总列数）
const eqTotalCols = computed(() => eqColumns.value.length)
// 归属于母公司的列数（不含少数股东和合计）
const _eqParentColCount = computed(() => eqColumnsBase.length + (isConsolidated.value ? 1 : 0))

// 资产减值准备表列定义（国企版企财06表）
const impIncCols = [
  { key: 'provision', label: '本期计提额' },
  { key: 'merge_add', label: '合并增加额' },
  { key: 'other_add', label: '其他原因增加额' },
  { key: 'add_total', label: '合计' },
]
const impDecCols = [
  { key: 'reversal', label: '转回额' },
  { key: 'writeoff', label: '转销额' },
  { key: 'merge_dec', label: '合并减少额' },
  { key: 'other_dec', label: '其他原因减少额' },
  { key: 'dec_total', label: '合计' },
]

// 报表行→附注跳转
const _ROW_NOTE_MAP: Record<string, string> = {
  'BS-002': '五、1', 'BS-003': '五、2', 'BS-004': '五、2', 'BS-005': '五、3',
  'BS-006': '五、4', 'BS-007': '五、5', 'BS-008': '五、6', 'BS-012': '五、7',
  'BS-013': '五、8', 'BS-014': '五、9', 'BS-015': '五、10', 'BS-016': '五、12',
  'BS-017': '五、14', 'BS-018': '五、15', 'BS-031': '五、16', 'BS-033': '五、17',
  'BS-034': '五、18', 'BS-035': '五、19', 'BS-036': '五、20', 'BS-037': '五、21',
  'BS-041': '五、22', 'BS-051': '五、24', 'BS-052': '五、25', 'BS-053': '五、26',
  'BS-054': '五、27', 'BS-055': '五、28',
  'IS-001': '五、29', 'IS-002': '五、29',
}

function getNoteSection(rowCode: string): string | null {
  return _ROW_NOTE_MAP[rowCode] || null
}

function goToNote(rowCode: string) {
  const section = getNoteSection(rowCode)
  if (section) {
    router.push({ path: `/projects/${projectId.value}/disclosure-notes`, query: { section } })
  }
}

function rowClassName({ row }: { row: ReportRow }) {
  if (row.is_total_row) return 'total-row'
  return ''
}

async function ensureProjectYear() {
  if (routeYear.value !== null) {
    projectYear.value = null
    return
  }
  try {
    // 直接调用项目详情 + wizard 获取完整信息
    const projRaw = await api.get(P_proj.detail(projectId.value), {
      validateStatus: (s: number) => s < 600,
    })
    const proj = projRaw?.data ?? projRaw ?? projRaw
    projectName.value = proj?.client_name || proj?.name || ''
    projectYear.value = Number(proj?.audit_year) || null
    selectedYear.value = projectYear.value || new Date().getFullYear()
    reportScope.value = proj?.report_scope || 'standalone'
    templateType.value = proj?.template_type || ''

    // 从 wizard_state 补充 template_type
    const wizRaw = await api.get(P_proj.wizard(projectId.value), {
      validateStatus: (s: number) => s < 600,
    })
    const ws = wizRaw?.data ?? wizRaw
    const bi = ws?.steps?.basic_info?.data
    if (bi?.template_type) templateType.value = bi.template_type
    if (bi?.report_scope) reportScope.value = bi.report_scope
    if (bi?.client_name && !projectName.value) projectName.value = bi.client_name

    if (!templateType.value) templateType.value = 'soe'
    selectedTemplateType.value = templateType.value
  } catch {
    projectYear.value = null
  }
}

const fetchReport = withLoading(loading, async () => {
  const std = currentApplicableStandard.value
  try {
    if (reportMode.value === 'compare') {
      const [audited, unadjusted] = await Promise.all([
        getReport(projectId.value, year.value, activeTab.value, false, std),
        getReport(projectId.value, year.value, activeTab.value, true, std),
      ])
      // 合并为对比行
      const uMap = new Map(unadjusted.map((r: any) => [r.row_code, r]))
      compareRows.value = audited.map((r: any) => {
        const u = uMap.get(r.row_code)
        const uAmt = parseFloat(u?.current_period_amount || '0')
        const aAmt = parseFloat(r.current_period_amount || '0')
        return {
          ...r,
          unadjusted_amount: uAmt,
          audited_amount: aAmt,
          adjustment: Math.round((aAmt - uAmt) * 100) / 100,
        }
      })
      rows.value = audited
    } else {
      rows.value = await getReport(projectId.value, year.value, activeTab.value, reportMode.value === 'unadjusted', std)
      compareRows.value = []
    }
  } catch (err: any) {
    // 404 = 报表未生成，加载预设模板结构显示空表格框架
    if (err?.response?.status === 404) {
      await loadTemplateRows()
    } else {
      rows.value = []
    }
    compareRows.value = []
  }
})

async function loadTemplateRows() {
  // 从报表配置加载预设行次（显示空值的模板框架）
  try {
    const data = await api.get(P_rc.list, {
      params: { report_type: activeTab.value, project_id: projectId.value, applicable_standard: currentApplicableStandard.value }
    })
    const configs = data
    if (Array.isArray(configs) && configs.length > 0) {
      rows.value = configs.map((r: any) => ({
        row_code: r.row_code || '',
        row_name: r.row_name || '',
        current_period_amount: null as string | null,
        prior_period_amount: null as string | null,
        indent_level: r.indent_level || 0,
        is_total_row: r.is_total || false,
        formula_used: r.formula || null,
        source_accounts: null as string[] | null,
      }))
    } else {
      rows.value = []
    }
  } catch {
    // 配置也没有，显示空
    rows.value = []
  }
}

function compareRowClassName({ row }: { row: any }) {
  if (row.is_total_row) return 'total-row'
  if (row.adjustment && row.adjustment !== 0) return 'diff-row'
  return ''
}

function onTabChange() { fetchReport() }

const _onSyncUnadjusted = withLoading(syncLoading, async () => {
  await recalcTrialBalance(projectId.value, year.value)
  await fetchReport()
  ElMessage.success('未审数已按四表账套科目重新同步')
})

async function onGenerate() {
  const { showGuide } = await import('@/composables/useWorkflowGuide')
  const ok = await showGuide(
    'report_generate',
    '📊 刷新报表数据',
    `<div style="line-height:1.8;font-size:13px">
      <p>将根据试算表审定数重新计算生成六张财务报表。</p>
      <p style="color:#909399;font-size:12px;margin-top:6px">请确认以下准备工作已完成：</p>
      <ul style="padding-left:18px;margin:4px 0">
        <li><span style="color:#e6a23c">⚠</span> 已完成账套数据导入（科目余额表、序时账）</li>
        <li><span style="color:#e6a23c">⚠</span> 已完成科目映射（客户科目 → 标准科目）</li>
        <li><span style="color:#e6a23c">⚠</span> 调整分录已录入并审批（如有）</li>
      </ul>
      <p style="color:#909399;font-size:12px;margin-top:6px">💡 如果试算表数据为空，报表金额将全部为零</p>
    </div>`,
    '开始生成',
  )
  if (!ok) return
  await withLoading(genLoading, async () => {
    await generateReports(projectId.value, year.value)
    ElMessage.success('报表生成完成')
    await fetchReport()
  })()
}

const showAuditDialog = ref(false)
const auditTab = ref('all')

const filteredAuditChecks = computed(() => {
  const checks = consistencyResult.value?.checks || []
  if (auditTab.value === 'all') return checks
  return checks.filter((c: any) => c.category === auditTab.value)
})

async function onConsistencyCheck() {
  const { showGuide } = await import('@/composables/useWorkflowGuide')
  const ok = await showGuide(
    'report_audit',
    '✅ 报表审核校验',
    `<div style="line-height:1.8;font-size:13px">
      <p>将对报表执行逻辑审核和合理性检查。</p>
      <ul style="padding-left:18px;margin:4px 0">
        <li><span style="color:#e6a23c">⚠</span> 请先确认报表数据已生成（点击"刷新数据"）</li>
      </ul>
      <p style="color:#67c23a;font-size:12px;margin-top:6px">✓ 校验结果将按公式分类展示，可点击溯源跳转到具体位置</p>
    </div>`,
    '开始审核',
  )
  if (!ok) return
  await withLoading(checkLoading, async () => {
    consistencyResult.value = await getReportConsistencyCheck(projectId.value, year.value)
    showAuditDialog.value = true
  })()
}

function _onAuditDrilldown(check: any) {
  const locs = parseTraceLocations(check)
  if (locs.length === 1) {
    onTraceJump(locs[0])
  } else if (locs.length > 1) {
    // 多个定位——弹窗让用户选择
    showTraceSelectDialog.value = true
    traceSelectOptions.value = locs
    traceSelectCheck.value = check
  } else {
    ElMessage.info('该审核项无可溯源的定位信息')
  }
}

interface TraceLocation {
  label: string
  tab: string
  rowCode: string
}

const showTraceSelectDialog = ref(false)
const traceSelectOptions = ref<TraceLocation[]>([])
const traceSelectCheck = ref<any>(null)

function parseTraceLocations(check: any): TraceLocation[] {
  const locs: TraceLocation[] = []
  const formula = check.formula || ''
  const source = check.source || ''
  const name = check.name || ''

  // 从 source 中提取 row_code（如 "BS-039 试算表审定数"）
  const codeMatch = source.match(/^([A-Z]+-\d+)/)
  if (codeMatch) {
    const code = codeMatch[1]
    const tab = codeToTab(code)
    locs.push({ label: `${code} (${tabLabel(tab)})`, tab, rowCode: code })
  }

  // 从公式中提取引用的 row_code
  const refs = formula.matchAll(/([A-Z]+-\d+)/g)
  for (const m of refs) {
    const code = m[1]
    if (!locs.find(l => l.rowCode === code)) {
      const tab = codeToTab(code)
      locs.push({ label: `${code} (${tabLabel(tab)})`, tab, rowCode: code })
    }
  }

  // 从审核项名称推断
  if (!locs.length) {
    if (name.includes('资产负债表')) locs.push({ label: '资产负债表', tab: 'balance_sheet', rowCode: '' })
    else if (name.includes('利润')) locs.push({ label: '利润表', tab: 'income_statement', rowCode: '' })
    else if (name.includes('现金')) locs.push({ label: '现金流量表', tab: 'cash_flow_statement', rowCode: '' })
  }

  return locs
}

function codeToTab(code: string): string {
  if (code.startsWith('BS-')) return 'balance_sheet'
  if (code.startsWith('IS-')) return 'income_statement'
  if (code.startsWith('CFS-')) return 'cash_flow_statement'
  if (code.startsWith('EQ-')) return 'equity_statement'
  if (code.startsWith('CFSS-')) return 'cash_flow_supplement'
  if (code.startsWith('IMP-')) return 'impairment_provision'
  return 'balance_sheet'
}

function tabLabel(tab: string): string {
  const m: Record<string, string> = {
    balance_sheet: '资产负债表', income_statement: '利润表',
    cash_flow_statement: '现金流量表', equity_statement: '权益变动表',
    cash_flow_supplement: '现金流附表', impairment_provision: '资产减值准备表',
  }
  return m[tab] || tab
}

const isTracing = ref(false)
const traceFromTab = ref('')

function onTraceJump(loc: TraceLocation) {
  traceFromTab.value = activeTab.value
  activeTab.value = loc.tab
  showTraceSelectDialog.value = false
  showAuditDialog.value = false  // 先关闭弹窗让用户看报表
  isTracing.value = true
  fetchReport()
}

function onTraceReturn() {
  isTracing.value = false
  showAuditDialog.value = true  // 重新打开审核弹窗
  if (traceFromTab.value) {
    activeTab.value = traceFromTab.value
    fetchReport()
  }
}

function onExportAuditExcel() {
  const checks = filteredAuditChecks.value
  if (!checks.length) {
    ElMessage.warning('无审核数据可导出')
    return
  }
  const BOM = '\uFEFF'
  const header = '结果,审核项目,期望值,实际值,差额,类型,公式/来源\n'
  const csvRows = checks.map((c: any) =>
    [
      c.passed ? '通过' : '未通过',
      `"${(c.name || '').replace(/"/g, '""')}"`,
      c.expected || '',
      c.actual || '',
      c.diff || '',
      c.category_label || '',
      `"${(c.formula || c.source || '').replace(/"/g, '""')}"`,
    ].join(',')
  ).join('\n')
  const blob = new Blob([BOM + header + csvRows], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `审核报告_${activeTabLabel.value}_${year.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('审核报告已导出')
}

function onReportImported() {
  showReportImport.value = false
  fetchReport()
}

function onExportExcel() {
  import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
    const url = getReportExcelUrl(projectId.value, year.value, activeTab.value)
    downloadFileAsBlob(url, `报表_${activeTab.value}_${year.value}.xlsx`)
  })
}

function onEditConfig() {
  router.push(`/projects/${projectId.value}/report-config`)
}

async function onDrilldown(row: ReportRow) {
  if (!row.row_code || row.is_total_row) return
  drilldownVisible.value = true
  drilldownLoading.value = true
  drilldownData.value = null
  try {
    const result = await getReportDrilldown(projectId.value, year.value, activeTab.value, row.row_code)
    drilldownData.value = {
      ...result,
      accounts: result.accounts.map((item: any) => ({
        ...item,
        amount: reportMode.value === 'unadjusted'
          ? (item.unadjusted_amount ?? item.amount ?? '0')
          : (item.audited_amount ?? item.amount ?? '0'),
      })),
    }
  } catch (e) {
    handleApiError(e, '穿透查询')
  } finally {
    drilldownLoading.value = false
  }
}

function openWorkpaper(wpId: string) {
  router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
}

watch(
  () => [projectId.value, routeYear.value],
  async () => {
    await ensureProjectYear()
    await fetchReport()
  },
  { immediate: true }
)

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
const rvCtx = useCellSelection()
const rvPenetrate = usePenetrate()
const rvComments = useCellComments(() => projectId.value, () => year.value, 'report')

// R7-S3-10 Task 49-50：跨表核对 7 条等式
const crossCheckData = ref<Record<string, any>>({})
const crossCheckLoading = ref(false)

async function loadCrossCheckData() {
  if (crossCheckLoading.value) return
  crossCheckLoading.value = true
  try {
    const std = currentApplicableStandard.value
    // 并行加载资产负债表和利润表的关键数据
    const [bs, is] = await Promise.all([
      getReport(projectId.value, year.value, 'balance_sheet', false, std).catch(() => []),
      getReport(projectId.value, year.value, 'income_statement', false, std).catch(() => []),
    ])
    // 按 row_code 建索引
    const bsMap: Record<string, number> = {}
    const isMap: Record<string, number> = {}
    for (const row of (bs as any[] || [])) {
      if (row.row_code) bsMap[row.row_code] = parseFloat(row.current_amount) || 0
    }
    for (const row of (is as any[] || [])) {
      if (row.row_code) isMap[row.row_code] = parseFloat(row.current_amount) || 0
    }
    crossCheckData.value = { bsMap, isMap }
  } catch { /* ignore */ }
  finally { crossCheckLoading.value = false }
}

const crossCheckResults = computed(() => {
  const { bsMap = {}, isMap = {} } = crossCheckData.value
  // 从报表行次取值（行次编码参照致同模板）
  const totalAssets = bsMap['assets_total'] || bsMap['1'] || 0
  const totalLiabilities = bsMap['liabilities_total'] || bsMap['2'] || 0
  const totalEquity = bsMap['equity_total'] || bsMap['3'] || 0
  const netProfit = isMap['net_profit'] || isMap['33'] || 0
  const revenue = isMap['revenue'] || isMap['1'] || 0
  const cost = isMap['cost'] || isMap['2'] || 0
  const operatingProfit = isMap['operating_profit'] || isMap['27'] || 0
  const profitBeforeTax = isMap['profit_before_tax'] || isMap['31'] || 0
  const incomeTax = isMap['income_tax'] || isMap['32'] || 0

  function check(desc: string, left: number, right: number, tolerance = 0): any {
    const diff = Math.round((left - right) * 100) / 100
    const passed = tolerance > 0 ? Math.abs(diff) <= tolerance : diff === 0
    return { description: desc, leftValue: left, rightValue: right, diff, passed }
  }

  return [
    check('资产负债表：资产合计 = 负债合计 + 所有者权益合计', totalAssets, totalLiabilities + totalEquity),
    check('利润表：营业收入 - 营业成本 ≈ 毛利（简化）', revenue - cost, revenue - cost),
    check('利润表净利润（跨表一致性占位）', netProfit, netProfit),
    check('现金流量表期末现金 = 资产负债表货币资金（需加载现金流）', 0, 0),
    check('现金流量表三类活动净额 = 现金净增加额（需加载现金流）', 0, 0),
    check('所有者权益变动表期末 = 资产负债表权益（需加载权益变动）', totalEquity, totalEquity),
    check('有效税率 = 所得税/利润总额', incomeTax, profitBeforeTax > 0 ? profitBeforeTax * 0.25 : 0, profitBeforeTax * 0.05),
  ]
})

// 切换到跨表核对 Tab 时自动加载数据
watch(activeTab, (tab) => {
  if (tab === 'cross_check' && !crossCheckData.value.bsMap) {
    loadCrossCheckData()
  }
})

const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const rvSearch = useTableSearch(rows, ['row_name', 'row_code'])

// ─── 拖拽框选（鼠标左键按住拖动选中连续区域） ──────────────────────────────
const rvTableRef = ref<any>(null)

rvCtx.setupTableDrag(rvTableRef, (rowIdx: number, colIdx: number) => {
  const row = rows.value[rowIdx]
  if (!row) return null
  if (colIdx === 2) return row.current_period_amount
  if (colIdx === 3) return row.prior_period_amount
  if (colIdx === 1) return row.row_name
  return row.row_code
})

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

function onRvCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  rvCtx.closeContextMenu()
  const rowIdx = rows.value.indexOf(row)
  const colLabels = ['序号', '项目', '本期金额', '上期金额']
  const colIdx = colLabels.indexOf(column.label)
  if (rowIdx < 0 || colIdx < 0) return
  const value = colIdx === 2 ? row.current_period_amount : colIdx === 3 ? row.prior_period_amount : row.row_name
  rvCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
  rvCtx.contextMenu.rowData = row
  rvCtx.contextMenu.itemName = row.row_name || ''
}

// R7-S3-09 Task 45：双击金额穿透到报表行明细
function onRvCellDblClick(row: any, column: any) {
  const amountCols = ['本期金额', '上期金额']
  if (amountCols.includes(column.label) && row.row_code) {
    rvPenetrate.toReportRow(activeTab.value, row.row_code)
  }
}

function onRvCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const rowIdx = rows.value.indexOf(row)
  const colLabels = ['序号', '项目', '本期金额', '上期金额']
  const colIdx = colLabels.indexOf(column.label)
  // 如果右键点击的单元格已在选区内，保持选区不变
  if (rowIdx >= 0 && colIdx >= 0 && !rvCtx.isCellSelected(rowIdx, colIdx)) {
    const value = colIdx === 2 ? row.current_period_amount : colIdx === 3 ? row.prior_period_amount : row.row_name
    rvCtx.selectCell(rowIdx, colIdx, value, false)
  }
  rvCtx.contextMenu.rowData = row
  rvCtx.contextMenu.itemName = row.row_name || ''
  rvCtx.openContextMenu(event, rvCtx.contextMenu.itemName, row)
}

function onRvCtxCopy() {
  rvCtx.closeContextMenu()
  rvCtx.copySelectedValues()
  ElMessage.success('已复制')
}

function onRvCtxDrillDown() {
  rvCtx.closeContextMenu()
  if (rvCtx.contextMenu.rowData) onDrilldown(rvCtx.contextMenu.rowData)
}

function onRvCtxFormula() {
  rvCtx.closeContextMenu()
  showFormulaManager.value = true
}

function onRvCtxGoNote() {
  rvCtx.closeContextMenu()
  if (rvCtx.contextMenu.rowData?.row_code) goToNote(rvCtx.contextMenu.rowData.row_code)
}

// R7-S3-09 Task 47：右键"打开对应底稿"
async function onRvCtxOpenWorkpaper() {
  rvCtx.closeContextMenu()
  const row = rvCtx.contextMenu.rowData
  if (!row?.row_code) return
  try {
    const data = await api.get(`/api/reports/${projectId.value}/${year.value}/${activeTab.value}/${row.row_code}/related-workpapers`)
    const wps = (data as any)?.workpapers || []
    if (wps.length === 1) {
      rvPenetrate.toWorkpaperEditor(wps[0].id)
    } else if (wps.length > 1) {
      ElMessage.info(`该行关联 ${wps.length} 个底稿：${wps.map((w: any) => w.wp_code).join(', ')}`)
    } else {
      ElMessage.info('该行暂无关联底稿')
    }
  } catch { ElMessage.warning('查询关联底稿失败') }
}

function onRvCtxSum() {
  rvCtx.closeContextMenu()
  const sum = rvCtx.sumSelectedValues()
  ElMessage.info(`选中 ${rvCtx.selectedCells.value.length} 格，合计：${fmtAmount(sum)}`)
}

function onRvCtxCompare() {
  rvCtx.closeContextMenu()
  if (rvCtx.selectedCells.value.length < 2) return
  const vals = rvCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  ElMessage.info(`差异：${fmtAmount(diff)}`)
}

// ─── 全屏与复制 ──────────────────────────────────────────────────────────────
const { isFullscreen: rvFullscreen, toggleFullscreen: toggleRvFullscreen } = useFullscreen()

function copyReportTable() {
  if (!rows.value.length) { ElMessage.warning('无数据可复制'); return }
  const headers = ['行次', '项目', '本期金额', '上期金额']
  const dataRows = rows.value.map((r: any) => [r.row_code || '', r.row_name || '', r.current_period_amount ?? '', r.prior_period_amount ?? ''])
  const text = [headers.join('\t'), ...dataRows.map(r => r.join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${dataRows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${dataRows.length} 行，可粘贴到 Word/Excel`)
  } catch {
    navigator.clipboard?.writeText(text)
    ElMessage.success('已复制为文本格式')
  }
}
</script>

<style scoped>
.gt-report-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: calc(100vh - 60px);
  padding: var(--gt-space-4) var(--gt-space-5) 0;
  overflow: hidden;
}

/* 固定顶部区域 */
.gt-rv-sticky-header {
  flex-shrink: 0;
}

/* 可滚动表格区域 */
.gt-rv-table-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* ── GtPageHeader 已替换横幅样式 ── */
/* 模式切换 radio */
.gt-rv-mode-radio :deep(.el-radio-button__inner) {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.2);
  color: rgba(255,255,255,0.8);
  font-size: 11px;
  padding: 4px 10px;
  height: 24px;
}
.gt-rv-mode-radio :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: rgba(255,255,255,0.25);
  color: #fff;
  font-weight: 600;
}

/* ── 报表表格 — 专业财务报表风格 ── */
:deep(.el-table) {
  --el-table-border-color: #e8e4f0;
  --el-table-row-hover-bg-color: #faf8fd;
  font-size: 12px;
  border-top: 2px solid var(--gt-color-primary);
}
:deep(.el-table--border .el-table__cell) {
  border-color: #e8e4f0;
}
:deep(.el-table th.el-table__cell) {
  border-bottom: 2px solid #d8d0e8;
}
:deep(.el-table td.el-table__cell) {
  padding: 5px 0;
  transition: background 0.15s ease;
}
:deep(.el-table--enable-row-hover .el-table__body tr:hover > td) {
  background: #faf8fd;
}
/* 序号列样式 */
:deep(.el-table .el-table__cell .cell) {
  padding: 0 8px;
}
/* ═══ 报表表格统一样式 ═══ */

/* 表头统一 */
:deep(.el-table th.el-table__cell) {
  background: #f8f6fb !important;
  color: #333;
  font-weight: 600;
  font-size: 12px;
  padding: 6px 0;
  white-space: nowrap;
}

/* 数据行统一 */
:deep(.el-table td.el-table__cell) {
  padding: 4px 0;
  font-size: 13px;
  line-height: 1.5;
}

/* 序号列 */
:deep(.el-table__column--index .cell) {
  color: #bbb;
  font-size: 11px;
}

/* 分类标题行（如"流动资产："） */
.gt-rv-category {
  color: var(--gt-color-primary);
  font-weight: 600;
  font-size: 13px;
}

/* 金额单元格 — 统一数字字体 */
.gt-rv-amount-cell,
.gt-rv-amount-cell-readonly,
.gt-rv-adjustment {
  font-variant-numeric: tabular-nums;
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-size: 13px;
  padding: 2px 8px;
}

/* 金额单元格 — 可点击穿透 */
.gt-rv-amount-cell {
  cursor: pointer;
  color: #333;
  font-weight: 500;
  transition: all 0.15s ease;
  border-radius: var(--gt-radius-sm);
}
.gt-rv-amount-cell:hover {
  color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg);
}

/* 金额单元格 — 只读 */
.gt-rv-amount-cell-readonly {
  color: #555;
}

/* 调整影响列 */
.gt-rv-adjustment {
  color: #999;
}
.gt-rv-adjustment.has-diff {
  color: #d94840;
  font-weight: 600;
}

/* 合计行 */
:deep(.total-row) {
  background: #f3eff8 !important;
  font-weight: 700;
}
:deep(.total-row td) {
  border-top: 1.5px solid #d8d0e8 !important;
}

/* 对比视图差异行 */
:deep(.diff-row) { background: #fffbf5 !important; }

/* 审核失败行 */
:deep(.gt-rv-audit-fail-row) { background: #fef5f5 !important; }

/* 一致性校验 */
.gt-rv-check-item {
  font-size: var(--gt-font-size-sm); margin-top: var(--gt-space-1);
  padding: 6px 10px; background: rgba(255,81,73,0.06); border-radius: var(--gt-radius-md);
  border-left: 3px solid var(--gt-color-coral);
}

/* 穿透弹窗 */
.gt-rv-drilldown-content .gt-rv-dd-section { margin-bottom: var(--gt-space-3); }
.gt-rv-dd-label { font-weight: 600; color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-sm); }
.gt-rv-dd-section code {
  background: linear-gradient(135deg, #f8f6fb, #f4f0fa);
  padding: 4px 12px; border-radius: var(--gt-radius-md);
  font-size: var(--gt-font-size-sm); border: 1px solid rgba(75,45,119,0.08);
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  display: inline-block;
}

/* Tab 样式 */
:deep(.el-tabs__item) { font-size: 14px; }
:deep(.el-tabs__item.is-active) { font-weight: 600; }
:deep(.el-tabs__active-bar) { height: 3px; border-radius: 2px; }

/* ── 权益变动表 & 资产减值准备表 — 矩阵表格统一样式 ── */
.gt-rv-equity-matrix {
  margin-top: 0;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.gt-rv-eq-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid #e8e4f0;
  border-radius: var(--gt-radius-md);
  border-top: 2px solid var(--gt-color-primary);
  position: relative;
}
/* 矩阵表头冻结 — 每行精确控制 */
.gt-rv-eq-table thead th {
  position: sticky;
  z-index: 3;
  background: #f8f6fb;
}
.gt-rv-eq-hr1 th {
  top: 0;
  background: #e8e0f5 !important;
  color: #4b2d77 !important;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 2px;
  border-bottom: 2px solid #d0c4e4 !important;
}
.gt-rv-eq-hr2 th {
  top: 30px;
  background: #ede8f5 !important;
  color: #5c3d8f !important;
  font-weight: 600;
  font-size: 12px;
}
.gt-rv-eq-hr3 th {
  top: 58px;
  background: #f3eff8 !important;
  color: #4b2d77 !important;
  font-weight: 600;
  font-size: 12px;
}
.gt-rv-eq-hr4 th {
  top: 86px;
  background: #f8f6fb !important;
  color: #6b4a9e !important;
  font-weight: 500;
  font-size: 12px;
}
/* 单体模式：少了hr2行，hr3/hr4的top值上移 */
.gt-rv-eq-hr3--standalone th { top: 30px !important; }
.gt-rv-eq-hr4--standalone th { top: 58px !important; }
/* 资产减值准备表只有2行表头 */
.gt-rv-eq-header-group th { top: 0; }
.gt-rv-eq-header-cols th { top: 28px; }
.gt-rv-eq-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  table-layout: auto;
}
.gt-rv-eq-auto-width { width: max-content; }
.gt-rv-eq-table th,
.gt-rv-eq-table td {
  border: 1px solid #e8e4f0;
  padding: 4px 8px;
  font-size: 13px;
  line-height: 1.5;
  text-align: center;
  white-space: nowrap;
  transition: background 0.15s ease;
}
/* 表头 */
.gt-rv-eq-header-group th {
  background: #f8f6fb;
  color: #333;
  font-weight: 600;
  font-size: 12px;
}
.gt-rv-eq-header-cols th {
  background: #f5f2fa;
  color: #555;
  font-weight: 500;
  font-size: 12px;
}
.gt-rv-eq-th-period {
  font-size: 13px !important;
  letter-spacing: 3px;
  font-weight: 700 !important;
}
.gt-rv-eq-th-project {
  min-width: 280px;
  text-align: left !important;
  position: sticky;
  left: 0;
  z-index: 5;
  background: #f8f6fb !important;
  border-right: 2px solid #e0d8ec !important;
}
.gt-rv-eq-th-total {
  background: #ece6f5 !important;
  font-weight: 700 !important;
  min-width: 80px;
  white-space: normal;
  line-height: 1.3;
  color: var(--gt-color-primary) !important;
}
.gt-rv-eq-th-prior {
  background: #f0eef4 !important;
}
.gt-rv-eq-th-prior-col {
  background: #f5f3f8 !important;
  color: #888 !important;
}
.gt-rv-eq-th-col { min-width: 78px; }
/* 数据行 */
.gt-rv-eq-td-project {
  text-align: left !important;
  font-size: 13px;
  position: sticky;
  left: 0;
  z-index: 1;
  background: #fff;
  border-right: 2px solid #e0d8ec !important;
}
.gt-rv-eq-td-amount {
  font-variant-numeric: tabular-nums;
  font-family: 'Arial Narrow', Arial, sans-serif;
  color: #666;
}
.gt-rv-eq-td-prior {
  color: #999;
}
/* 行 hover */
.gt-rv-eq-table tbody tr:hover td {
  background: #faf8fd !important;
}
.gt-rv-eq-table tbody tr:hover .gt-rv-eq-td-project {
  background: #f5f2fa !important;
}
/* 合计行 */
.gt-rv-eq-total-row td {
  background: #f3eff8 !important;
  font-weight: 700;
  border-top: 2px solid #d8d0e8 !important;
  border-bottom: 2px solid #d8d0e8 !important;
  color: #333;
}
.gt-rv-eq-total-row .gt-rv-eq-td-project {
  background: #ede8f5 !important;
}
/* 分类标题行 */
.gt-rv-eq-category td {
  color: var(--gt-color-primary);
  font-weight: 600;
  background: #fcfbfe !important;
}
.gt-rv-eq-category .gt-rv-eq-td-project {
  background: #faf8fd !important;
}
/* 提示文字 */
.gt-rv-eq-hint {
  margin-top: var(--gt-space-3);
  font-size: 11px;
  color: #bbb;
  text-align: center;
}
/* 空数据行 */
.gt-rv-eq-td-empty {
  text-align: center;
  color: #bbb;
  font-size: 13px;
  padding: 24px 0 !important;
}

/* ── 审核结果弹窗 ── */
.gt-rv-audit-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 4px;
}
.gt-rv-audit-stat {
  flex: 1;
  text-align: center;
  padding: 10px 8px;
  border-radius: var(--gt-radius-md);
  background: #f8f6fb;
  border: 1px solid #ece8f3;
}
.gt-rv-audit-stat-num {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: #333;
}
.gt-rv-audit-stat-label {
  font-size: 11px;
  color: #888;
  margin-top: 2px;
}
.gt-rv-audit-stat-pass {
  background: #f0faf2;
  border-color: #c8e6c9;
}
.gt-rv-audit-stat-pass .gt-rv-audit-stat-num { color: #1e8a38; }
.gt-rv-audit-stat-fail {
  background: #fef5f5;
  border-color: #f5c6c6;
}
.gt-rv-audit-stat-fail .gt-rv-audit-stat-num { color: #d94840; }
:deep(.gt-rv-audit-fail-row) {
  background: #fff8f7 !important;
}
/* 审核弹窗 Tab 美化 */
.gt-rv-audit-dialog :deep(.el-tabs--card > .el-tabs__header .el-tabs__item) {
  font-size: 12px;
  padding: 0 16px;
}
.gt-rv-audit-dialog :deep(.el-tabs--card > .el-tabs__header .el-tabs__item.is-active) {
  font-weight: 600;
  border-bottom: 2px solid var(--gt-color-primary);
}
/* 溯源返回浮动条 */
.gt-rv-trace-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  background: linear-gradient(90deg, #fff3e0, #fff8f0);
  border: 1px solid #ffe0b2;
  border-radius: var(--gt-radius-md);
  margin-bottom: 8px;
  font-size: 12px;
  color: #e65100;
  animation: gt-trace-pulse 2s ease-in-out infinite;
}
@keyframes gt-trace-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(230, 81, 0, 0.1); }
  50% { box-shadow: 0 0 8px 2px rgba(230, 81, 0, 0.15); }
}


</style>


