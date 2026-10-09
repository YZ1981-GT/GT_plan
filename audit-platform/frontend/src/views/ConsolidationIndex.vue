<template>
  <div class="gt-consol gt-fade-in">
    <!-- F5 合并页 stale 实时感知（需求 7 / ADR-CONSOL-304）：子公司数据变更后 SSE 提示，warning 不阻断 -->
    <el-alert
      v-if="consolStale"
      type="warning"
      :closable="true"
      show-icon
      style="margin-bottom: 12px"
      @close="consolStale = false"
    >
      <template #title>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <span>子公司数据已更新，建议重新汇总以获取最新合并结果</span>
          <el-button size="small" type="primary" @click="onReaggregateNow">立即重新汇总</el-button>
        </div>
      </template>
    </el-alert>

    <!-- 合并推送过期/失败与旧附注重新汇总是两种语义：过期必须重新推送，不能只切换附注页 -->
    <el-alert v-if="consolPushStatus?.is_stale" type="warning" :closable="false" show-icon
      style="margin-bottom: 12px" data-testid="consol-push-stale-banner">
      <template #title>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <span>子企业数据已变化，建议重新推送<span v-if="consolPushStatus.stale_rows">（{{ consolPushStatus.stale_rows }} 行待更新）</span></span>
          <el-button size="small" type="primary" :loading="consolPushQueuing" @click="queueConsolPush">立即重新推送</el-button>
        </div>
      </template>
    </el-alert>
    <el-alert v-if="consolPushFailure" type="error" :closable="true" show-icon style="margin-bottom: 12px"
      data-testid="consol-push-failure-banner" :title="consolPushFailure" @close="consolPushFailure = ''" />

    <!-- 企业树诊断（需求 9.4）：脱挂、口径冲突、母公司未建单户、未归属分录等，警告在前 -->
    <el-alert
      v-if="treeDiagnostics.length && !diagnosticsDismissed"
      :type="treeWarnings.length ? 'warning' : 'info'"
      show-icon
      :closable="true"
      style="margin-bottom: 12px"
      data-testid="consol-tree-diagnostics"
      @close="diagnosticsDismissed = true"
    >
      <template #title>
        {{ treeWarnings.length ? `企业树有 ${treeWarnings.length} 条需要关注的提示` : `企业树说明（${treeDiagnostics.length} 条）` }}
      </template>
      <ul class="gt-consol-diag-list">
        <li v-for="(d, i) in visibleDiagnostics" :key="`${d.code}-${i}`" :class="`gt-consol-diag--${d.level}`">
          {{ d.message }}
        </li>
      </ul>
      <el-link v-if="treeDiagnostics.length > DIAG_PREVIEW" type="primary" style="font-size: var(--gt-font-size-xs)"
        @click="showAllDiagnostics = !showAllDiagnostics">
        {{ showAllDiagnostics ? '收起' : `展开全部 ${treeDiagnostics.length} 条` }}
      </el-link>
    </el-alert>

    <!-- 横幅：单位名称 + 年度 + 准则类型 -->
    <GtPageHeader title="合并报表" @back="$router.push('/consolidation')">
      <GtInfoBar
        :show-year="true"
        :show-template="true"
        :year-value="projectInfo.year"
        :template-value="projectInfo.standard"
        :badges="[{ label: '单位', value: displayPrefs.unitSuffix }]"
        @year-change="(y: number) => { projectInfo.year = y; onYearChange() }"
        @template-change="(s: string) => { projectInfo.standard = s as 'soe' | 'listed'; onStandardChange() }"
      />
      <template #actions>
        <GtToolbar
          :show-formula="true"
          @formula="onOpenFormula"
        >
          <template #left>
            <el-tooltip
              content="合并方式按下级企业的与上级关系自动识别：只有子公司为母子合并，只有分公司为总分汇总，两者都有则同时进行"
              placement="bottom"
            >
              <el-tag size="small" :type="treeMode === 'none' ? 'warning' : 'info'" effect="plain" style="margin-right: 8px" data-testid="consol-mode-tag">
                合并方式：{{ consolModeLabel }}
              </el-tag>
            </el-tooltip>
            <SharedTemplatePicker
              config-type="consol_scope"
              :project-id="projectId"
              :get-config-data="getConsolScopeConfigData"
              @applied="onConsolScopeTemplateApplied"
            />
            <el-tooltip content="选中单元格后点击，查看该数值的汇总明细过程" placement="bottom">
              <el-button size="small" @click="openCellDrillDown">📊 查看</el-button>
            </el-tooltip>
          </template>
          <template #right-extra>
            <el-button size="small" type="primary" :loading="refreshAllLoading" @click="onRefreshAll">🔄 一键刷新全部</el-button>
            <span v-if="refreshState.note === 'failed' || refreshState.note === 'skipped'" class="gt-consol-refresh-note-status" data-testid="consol-note-refresh-status">
              附注{{ refreshState.note === 'failed' ? '刷新失败' : '已跳过' }}：{{ refreshState.noteReason }}
            </span>
            <span v-if="refreshProgress.visible && refreshProgress.total" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin: 0 8px;">
              {{ refreshProgress.current }}/{{ refreshProgress.total }} {{ refreshProgress.step }}
            </span>
            <el-button size="small" :loading="reaggregateLoading" @click="onReaggregateNotes">📝 重新汇总附注</el-button>
            <el-button size="small" @click="showConsolConversion = true">🔄 转换规则</el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <el-tabs v-model="activeTab" class="gt-consol-tabs">
      <!-- Tab 0: 合并工作底稿 -->
      <el-tab-pane label="合并工作底稿" name="worksheets">
        <ConsolWorksheetTabs
          v-if="worksheetContextReady"
          :key="worksheetContextKey"
          ref="consolWorksheetTabsRef"
          :project-id="projectId"
          :year="effectiveConsolYear()"
          :consol-mode="treeMode"
          :is-root-selection="currentConsolEntity.nodeKey === groupTree[0]?.node_key"
        />
      </el-tab-pane>

      <!-- Tab 1: 集团架构 -->
      <el-tab-pane label="集团架构" name="structure">
        <div class="gt-tab-content">
          <!-- 工具栏 -->
          <div class="gt-ctb-toolbar" style="margin-bottom:12px">
            <div class="gt-ctb-toolbar-left">
              <el-button size="small" :type="orgViewMode === 'chart' ? 'primary' : ''" @click="orgViewMode = 'chart'">📊 组织结构图</el-button>
              <el-button size="small" :type="orgViewMode === 'tree' ? 'primary' : ''" @click="orgViewMode = 'tree'">🌳 树形列表</el-button>
              <span class="gt-ctb-sep" />
              <el-button size="small" @click="orgZoom = Math.min(orgZoom + 0.1, 2)">🔍+</el-button>
              <el-button size="small" @click="orgZoom = Math.max(orgZoom - 0.1, 0.4)">🔍-</el-button>
              <el-button size="small" @click="orgZoom = 1">1:1</el-button>
            </div>
            <div class="gt-ctb-toolbar-right">
              <!-- 自动建树 5.4：手动刷新树兜底（CONSOL_SCOPE_CHANGED 事件丢失时，EH4） -->
              <el-button size="small" :loading="treeRefreshing" @click="refreshGroupTree">🔄 刷新树</el-button>
              <el-button size="small" type="warning" @click="showScopeConfirmDialog = true" data-testid="scope-confirm-entry">📋 确认合并范围</el-button>
              <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin-left:8px">{{ orgNodeCount }} 个节点 · 最大 {{ orgMaxDepth }} 层</span>
            </div>
          </div>

          <!-- 组织结构图模式 -->
          <div v-if="orgViewMode === 'chart'" class="org-chart-wrapper" :style="{ transform: `scale(${orgZoom})`, transformOrigin: 'top left' }">
            <div v-if="groupTree.length" class="org-chart">
              <org-node :node="groupTree[0]" :depth="0" @select="onTreeNodeClick" @enter-project="onEnterProject" :selected-key="selectedNode?.node_key" />
            </div>
            <el-empty v-else :description="treeEmptyText" />
          </div>

          <!-- 树形列表模式（节点键 node_key：同一企业的合并户与母公司户是两个节点） -->
          <div v-else class="gt-structure-layout">
            <div class="gt-structure-tree">
              <el-tree :data="groupTree" :props="{ label: 'display_name', children: 'children' }"
                default-expand-all node-key="node_key" highlight-current @node-click="onTreeNodeClick">
                <template #default="{ data }">
                  <span class="gt-tree-node" :data-node-key="data.node_key">
                    <span>{{ nodeLabel(data) }}</span>
                    <el-tag v-if="relationLabel(data.relation)" size="small" effect="plain" style="margin-left:8px">{{ relationLabel(data.relation) }}</el-tag>
                    <el-tag v-for="tag in flagTags(data)" :key="tag.code" size="small" effect="plain" :type="tag.type" style="margin-left:4px">{{ tag.label }}</el-tag>
                    <!-- 双向导航 4.2：只对有项目的节点显示（阻止冒泡，避免触发 node-click） -->
                    <el-link
                      v-if="canEnterProject(data)"
                      type="primary"
                      style="margin-left:8px;font-size: var(--gt-font-size-xs)"
                      @click.stop="onEnterProject(data)"
                    >进入项目</el-link>
                  </span>
                </template>
              </el-tree>
              <el-empty v-if="!groupTree.length" :description="treeEmptyText" />
            </div>
            <div v-if="selectedNode" class="gt-structure-card">
              <el-descriptions :column="1" border size="small" title="节点信息">
                <el-descriptions-item label="节点">{{ nodeLabel(selectedNode) }}</el-descriptions-item>
                <el-descriptions-item label="企业代码">{{ selectedNode.company_code || '—' }}</el-descriptions-item>
                <el-descriptions-item label="角色">{{ roleLabel(selectedNode.role) || '—' }}</el-descriptions-item>
                <el-descriptions-item v-if="relationLabel(selectedNode.relation)" label="与上级关系">{{ relationLabel(selectedNode.relation) }}</el-descriptions-item>
                <el-descriptions-item v-if="viaLabel(selectedNode, treeNames)" label="持有方式">{{ viaLabel(selectedNode, treeNames) }}</el-descriptions-item>
              </el-descriptions>
              <el-button v-if="canOpenSubConsol(selectedNode)" type="primary" size="small" style="margin-top:12px" @click="goToProject(selectedNode)">查看该企业合并</el-button>
            </div>
          </div>

          <!-- 选中节点信息卡（组织图模式） -->
          <div v-if="orgViewMode === 'chart' && selectedNode" class="org-detail-card">
            <h4 style="margin:0 0 8px;color: var(--gt-color-primary)">{{ nodeLabel(selectedNode) }}</h4>
            <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:4px 0">代码：{{ selectedNode.company_code || '—' }}</p>
            <p v-if="roleLabel(selectedNode.role)" style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:4px 0">角色：{{ roleLabel(selectedNode.role) }}<template v-if="relationLabel(selectedNode.relation)"> · {{ relationLabel(selectedNode.relation) }}</template></p>
            <p v-if="viaLabel(selectedNode, treeNames)" style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:4px 0">{{ viaLabel(selectedNode, treeNames) }}</p>
            <p v-if="selectedNode.children?.length" style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary);margin:4px 0">下级节点：{{ selectedNode.children.length }} 个</p>
            <el-button v-if="canOpenSubConsol(selectedNode)" type="primary" size="small" style="margin-top:8px" @click="goToProject(selectedNode)">查看该企业合并</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab: 试算平衡表（独立组件） -->
      <el-tab-pane label="试算平衡表" name="consol_tb">
        <!-- 只读：按报表行次读时计算五列净额（与合并报表同一求值）；年度取企业树的审计年度 -->
        <ConsolTrialBalanceTab
          ref="consolTbTabRef"
          :project-id="projectId"
          :year="effectiveConsolYear()"
          :tree="groupTree[0] || null"
          :selected-node-key="currentEntityNodeKey"
          @audit="onTbAudit"
          @cell-context-menu="onTbCellContextMenu"
        />
      </el-tab-pane>

      <!-- Tab 5: 合并报表 -->
      <el-tab-pane label="合并报表" name="consol_report">
        <div class="gt-tab-content">
          <!-- 报表类型标签 -->
          <div class="gt-report-type-tabs" style="margin-bottom:0">
            <div class="gt-report-type-tabs-left">
              <span v-for="item in reportNavItems" :key="item.key"
                class="gt-report-type-tag" :class="{ 'gt-report-type-tag--active': consolReportType === item.key }"
                @click="selectConsolReportType(item.key)">
                {{ item.label }}
              </span>
            </div>
          </div>
          <!-- 工具栏 -->
          <div class="gt-ctb-toolbar" style="margin-top:8px">
            <div class="gt-ctb-toolbar-left">
              <!-- 差额表（需求 5.4）：所选汇总节点下各直接子节点对每一行的贡献，与合并报表同一求值 -->
              <el-radio-group :model-value="consolReportView" size="small" data-testid="consol-report-view"
                @change="(v: any) => setConsolReportView(v)">
                <el-radio-button value="report">合并报表</el-radio-button>
                <el-radio-button value="breakdown">差额表</el-radio-button>
              </el-radio-group>
              <span v-if="consolReportView === 'report'" style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary)">{{ consolReportRows.length }} 行 · {{ currentReportLabel }}</span>
              <span v-else style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary)">{{ currentReportLabel }} · 差额表</span>
            </div>
            <div v-if="consolReportView === 'report'" class="gt-ctb-toolbar-right">
              <el-button size="small" type="primary" @click="loadConsolReport(true)" :loading="consolReportLoading">🔄 刷新</el-button>
              <el-button size="small" @click="exportConsolReport">📤 导出</el-button>
            </div>
          </div>
          <ConsolReportBreakdownView
            v-if="consolReportView === 'breakdown'"
            ref="consolBreakdownViewRef"
            :project-id="projectId"
            :year="effectiveConsolYear()"
            :report-type="consolReportType"
            :tree="groupTree[0] || null"
            :selected-node-key="currentEntityNodeKey"
          />
          <!-- 权益变动表 — 与单户 ReportEquityTable 共用 eq_matrix 契约 -->
          <div v-else-if="consolReportType === 'equity_statement' && consolReportRows.length" v-loading="consolReportLoading" class="gt-consol-equity-matrix">
            <ReportEquityTable
              :rows="consolReportRows"
              :eq-columns="eqColumns"
              :eq-total-cols="eqTotalCols"
              :year="effectiveConsolYear()"
              :table-max-height="consolEquityTableHeight"
              :cell-class-name="() => ''"
              :font-size="displayPrefs.fontConfig.tableFont"
              :equity-span-method="equitySpanMethod"
              :eq-row-class-name="eqRowClassName"
              :eq-cell-val="eqCellVal"
              :is-consolidated="true"
            />
          </div>

          <!-- 资产减值准备表 — el-table 矩阵视图 -->
          <div v-else-if="consolReportType === 'impairment_provision' && consolReportRows.length" v-loading="consolReportLoading">
            <el-table :data="consolReportRows" border size="small" max-height="calc(100vh - 280px)" style="width:100%"
              :header-cell-style="{ background: '#f4f0fa', fontSize: '12px', whiteSpace: 'nowrap' }"
              :cell-style="{ padding: '2px 8px', fontSize: '13px' }"
              :row-class-name="impairRowClassName">
              <el-table-column prop="row_name" label="项目" fixed="left" min-width="200">
                <template #default="{ row }">
                  <span style="white-space:nowrap" :style="{ paddingLeft: (row.indent_level || 0) * 14 + 'px' }">{{ row.row_name }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="opening_balance" label="年初账面余额" min-width="120" align="right">
                <template #default="{ row }"><GtAmountCell :value="row.opening_balance" /></template>
              </el-table-column>
              <el-table-column label="本期增加额">
                <el-table-column prop="provision" label="本期计提额" min-width="110" align="right">
                  <template #default="{ row }"><span class="gt-amt">{{ fmtAmt(row.provision) }}</span></template>
                </el-table-column>
                <el-table-column prop="merge_add" label="合并增加额" min-width="110" align="right">
                  <template #default="{ row }"><span class="gt-amt">{{ fmtAmt(row.merge_add) }}</span></template>
                </el-table-column>
                <el-table-column prop="other_add" label="其他原因增加额" min-width="120" align="right">
                  <template #default="{ row }"><span class="gt-amt">{{ fmtAmt(row.other_add) }}</span></template>
                </el-table-column>
                <el-table-column prop="add_total" label="合计" min-width="100" align="right">
                  <template #default="{ row }"><GtAmountCell :value="row.add_total" style="font-weight:600" /></template>
                </el-table-column>
              </el-table-column>
              <el-table-column label="本期减少额">
                <el-table-column prop="reversal" label="转回额" min-width="100" align="right">
                  <template #default="{ row }"><span class="gt-amt">{{ fmtAmt(row.reversal) }}</span></template>
                </el-table-column>
                <el-table-column prop="writeoff" label="转销额" min-width="100" align="right">
                  <template #default="{ row }"><span class="gt-amt">{{ fmtAmt(row.writeoff) }}</span></template>
                </el-table-column>
                <el-table-column prop="merge_dec" label="合并减少额" min-width="110" align="right">
                  <template #default="{ row }"><span class="gt-amt">{{ fmtAmt(row.merge_dec) }}</span></template>
                </el-table-column>
                <el-table-column prop="other_dec" label="其他原因减少额" min-width="120" align="right">
                  <template #default="{ row }"><span class="gt-amt">{{ fmtAmt(row.other_dec) }}</span></template>
                </el-table-column>
                <el-table-column prop="dec_total" label="合计" min-width="100" align="right">
                  <template #default="{ row }"><GtAmountCell :value="row.dec_total" style="font-weight:600" /></template>
                </el-table-column>
              </el-table-column>
              <el-table-column prop="closing_balance" label="期末账面余额" min-width="120" align="right">
                <template #default="{ row }"><GtAmountCell :value="row.closing_balance" style="font-weight:700" /></template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 普通报表（资产负债表/利润表/现金流量表/现金流附表） -->
          <el-table ref="consolTableRef" v-else-if="consolReportRows.length" :data="consolReportRows" border size="small" max-height="calc(100vh - 260px)" style="width:100%"
            class="gt-consol-report-table"
            :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
            :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', padding: '4px 0' }"
            :cell-style="{ padding: '2px 8px', fontSize: '12px', lineHeight: '1.4' }"
            :cell-class-name="reportCellClassName"
            :row-class-name="consolReportRowClass"
            @cell-click="onReportCellClick"
            @cell-contextmenu="onReportCellContextMenu">
            <el-table-column prop="row_code" label="行次" width="80" align="center">
              <template #default="{ row }">
                <!-- 报表行 account 引用经 ACNR TB 域可解析 → GtIndexChip（REPORT/TB 域，Req 20.1/20.2）；miss 回退纯文本（Req 20.7/20.9） -->
                <GtIndexChip
                  v-if="reportAccountChip(row)"
                  :value="reportAccountChip(row) as string"
                  :context-project-id="projectId"
                  context="经 ACNR TB 域解析跳转到试算表科目"
                />
                <span v-else style="white-space:nowrap">{{ row.row_code }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="row_name" label="项目" min-width="300">
              <template #default="{ row }">
                <span style="white-space:nowrap" :style="{ paddingLeft: (row.indent_level || 0) * 14 + 'px', fontWeight: row.is_total_row ? 700 : 400 }">{{ row.row_name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合并本期" min-width="130" align="right">
              <template #default="{ row, $index }">
                <CommentTooltip :comment="consolComments.getComment(`consol_report_${consolReportType}`, $index, 2)">
                <span style="white-space:nowrap">{{ fmtAmt(row.current_period_amount) }}</span>
                </CommentTooltip>
              </template>
            </el-table-column>
            <el-table-column label="合并上期" min-width="130" align="right">
              <template #default="{ row, $index }">
                <CommentTooltip :comment="consolComments.getComment(`consol_report_${consolReportType}`, $index, 3)">
                <span style="white-space:nowrap">{{ fmtAmt(row.prior_period_amount) }}</span>
                </CommentTooltip>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else-if="!consolReportLoading" description="选择报表类型后点击刷新" />
        </div>
      </el-tab-pane>

      <!-- Tab 6: 合并附注 -->
      <el-tab-pane label="合并附注" name="consol_note">
        <ConsolNoteTab
          ref="consolNoteTabRef"
          :project-id="projectId"
          :year="effectiveConsolYear()"
          :standard="consolNoteTemplateType"
          :current-entity="currentConsolEntity"
          :group-tree="groupTree"
          :consol-note-tree="consolNoteTree"
          @revert-standard="consolNoteTemplateType = $event"
        />
      </el-tab-pane>
    </el-tabs>


    <!-- 报表转换规则弹窗 -->
    <el-dialog v-model="showConsolConversion" title="国企/上市报表转换规则" width="80%" top="4vh" append-to-body destroy-on-close>
      <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
        <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">{{ consolReportTemplateType === 'soe' ? '国企版 → 上市版' : '上市版 → 国企版' }}</span>
        <el-button size="small" @click="loadConsolMappingPreset" :loading="consolMappingLoading">一键加载预设</el-button>
        <el-button size="small" type="primary" @click="applyConsolConversion" :loading="consolMappingLoading">应用转换</el-button>
      </div>
      <el-table :data="consolMappingRules" border size="small" max-height="60vh" style="width:100%"
        :header-cell-style="{ background: '#f8f6fb', fontSize: '12px' }">
        <el-table-column label="源行次" prop="source_code" width="100" />
        <el-table-column label="源项目" prop="source_name" min-width="200" show-overflow-tooltip />
        <el-table-column label="→" width="40" align="center"><template #default><span>→</span></template></el-table-column>
        <el-table-column label="目标行次" width="100">
          <template #default="{ row }"><el-input v-model="row.target_code" size="small" /></template>
        </el-table-column>
        <el-table-column label="目标项目" min-width="200">
          <template #default="{ row }"><el-input v-model="row.target_name" size="small" /></template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 附注转换弹窗（由顶部栏准则切换驱动） -->
    <el-dialog v-model="showConsolNoteConversion" title="国企/上市附注模板切换" width="400px" append-to-body>
      <p style="font-size: var(--gt-font-size-sm);color: var(--gt-color-text-secondary);margin-bottom:16px">
        请使用顶部栏的准则选择器（国企版/上市版）切换模板，附注章节结构会自动更新。
      </p>
      <template #footer>
        <el-button @click="showConsolNoteConversion = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 单元格汇总穿透查看弹窗 -->
    <el-dialog v-model="showCellDrillDown" :title="drillDownTitle" width="80%" top="4vh" append-to-body destroy-on-close>
      <div style="display:flex;gap:10px;margin-bottom:10px;align-items:center">
        <el-tag type="info" size="small">{{ drillDownCell.itemName }}</el-tag>
        <el-tag size="small">{{ drillDownCell.colName }}</el-tag>
        <span style="font-size: var(--gt-font-size-sm);font-weight:700;color: var(--gt-color-primary)">合计：{{ fmtAmt(drillDownCell.totalValue) }}</span>
        <span style="flex:1" />
        <el-switch v-model="drillDownTransposed" active-text="转置" size="small" style="margin-right:6px" />
        <el-radio-group v-model="drillDownLevel" size="small">
          <el-radio-button value="direct">直接下级</el-radio-button>
          <el-radio-button value="leaf">末级明细</el-radio-button>
        </el-radio-group>
        <el-tooltip content="复制表格到剪贴板" placement="bottom">
          <el-button size="small" @click="copyDrillDownTable">📋 复制</el-button>
        </el-tooltip>
        <el-button size="small" @click="exportDrillDown">📤 导出</el-button>
        <!-- consolBreakdown drill：经 ACNR TB 域解析取 jump_route 后跳转到试算表科目（Req 20.1）；miss 时不显示 -->
        <el-tooltip v-if="drillDownJumpRoute" content="经 ACNR TB 域跳转到该科目试算表" placement="bottom">
          <el-button size="small" type="primary" @click="onConsolBreakdownJump">🔗 跳转科目</el-button>
        </el-tooltip>
      </div>

      <!-- 正常视图 -->
      <template v-if="!drillDownTransposed">
        <!-- 直接下级汇总 -->
        <el-table v-if="drillDownLevel === 'direct'" ref="drillDownTableRef" :data="drillDownDirectRows" border size="small" max-height="55vh" style="width:100%"
          show-summary :summary-method="drillDownSummary"
          :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }"
          :cell-style="{ padding: '2px 8px', fontSize: '12px' }">
          <el-table-column type="index" label="序号" width="50" align="center" />
          <el-table-column prop="company_name" label="企业名称" min-width="200" />
          <el-table-column prop="company_code" label="企业代码" width="180" />
          <el-table-column prop="amount" label="金额" width="150" align="right">
            <template #default="{ row }">
              <GtAmountCell :value="row.amount" />
            </template>
          </el-table-column>
          <el-table-column prop="ratio" label="占比" width="90" align="right">
            <template #default="{ row }">{{ row.ratio }}%</template>
          </el-table-column>
          <el-table-column prop="source" label="数据来源" width="120" />
        </el-table>

        <!-- 末级明细 -->
        <el-table v-else ref="drillDownTableRef" :data="drillDownLeafRows" border size="small" max-height="55vh" style="width:100%"
          show-summary :summary-method="drillDownSummary"
          :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }"
          :cell-style="{ padding: '2px 8px', fontSize: '12px' }">
          <el-table-column type="index" label="序号" width="50" align="center" />
          <el-table-column prop="company_name" label="末级企业" min-width="200" />
          <el-table-column prop="company_code" label="企业代码" width="180" />
          <el-table-column prop="parent_name" label="上级单位" width="160" />
          <el-table-column prop="amount" label="金额" width="150" align="right">
            <template #default="{ row }">
              <GtAmountCell :value="row.amount" />
            </template>
          </el-table-column>
          <el-table-column prop="ratio" label="占比" width="90" align="right">
            <template #default="{ row }">{{ row.ratio }}%</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- 转置视图：列变行 — el-table -->
      <template v-else>
        <el-table :data="drillDownTransposedRows" border size="small" max-height="55vh" style="width:100%"
          :header-cell-style="{ background: '#f0edf5', fontSize: '12px', whiteSpace: 'nowrap' }"
          :cell-style="{ padding: '2px 8px', fontSize: '12px' }">
          <el-table-column prop="field" label="字段" fixed="left" min-width="120" />
          <el-table-column v-for="(row, ri) in currentDrillDownRows" :key="ri" :label="row.company_name" min-width="120" align="right">
            <template #default="{ row: transRow }">
              <span :style="{ color: transRow.field === '金额' && Number(transRow['col_' + ri]) < 0 ? '#f56c6c' : '' }">
                {{ transRow['col_' + ri] }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="合计" min-width="120" align="right">
            <template #default="{ row: transRow }">
              <span :style="{ fontWeight: transRow.field === '金额' ? '700' : '600' }">{{ transRow.total }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <el-empty v-if="!drillDownDirectRows.length && !drillDownLoading" description="请先在表格中选中一个单元格，再点击查看" />
    </el-dialog>

    <!-- 右键菜单（统一组件） -->
    <CellContextMenu
      :visible="consolCtx.contextMenu.visible"
      :x="consolCtx.contextMenu.x"
      :y="consolCtx.contextMenu.y"
      :item-name="consolCtx.contextMenu.itemName"
      :value="consolCtx.selectedCells.value.length === 1 ? consolCtx.selectedCells.value[0]?.value : undefined"
      :multi-count="consolCtx.selectedCells.value.length"
      @copy="onConsolCtxCopy"
      @formula="onConsolCtxFormula"
      @sum="onConsolCtxSum"
      @compare="onConsolCtxCompare"
    >
      <div class="gt-ucell-ctx-item" @click="onConsolCtxDrillDown"><span class="gt-ucell-ctx-icon">📊</span> 汇总穿透</div>
      <div class="gt-ucell-ctx-item" @click="onConsolCtxCellTrace"><span class="gt-ucell-ctx-icon">🔍</span> 数字溯源</div>
    </CellContextMenu>

    <!-- 选中区域状态栏 -->
    <SelectionBar :stats="consolCtx.selectionStats()" />

    <!-- 数字溯源弹窗（lineage endpoint） -->
    <el-dialog v-model="consolTraceDialogVisible" title="🔍 数字溯源" width="700px" append-to-body destroy-on-close>
      <div v-loading="consolTraceLoading" style="min-height:120px">
        <template v-if="consolTraceResult">
          <div v-if="consolTraceResult.upstream.length || consolTraceResult.downstream.length">
            <h4 style="margin:0 0 8px">上游来源</h4>
            <el-table v-if="consolTraceResult.upstream.length" :data="consolTraceResult.upstream" size="small" border stripe max-height="200">
              <el-table-column prop="wp_code" label="底稿编码" width="120" />
              <el-table-column prop="label" label="描述" min-width="200" />
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button size="small" link type="primary" @click="onConsolTraceLocate(row)">定位</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="无上游来源" :image-size="40" />
            <h4 style="margin:16px 0 8px">下游引用</h4>
            <el-table v-if="consolTraceResult.downstream.length" :data="consolTraceResult.downstream" size="small" border stripe max-height="200">
              <el-table-column prop="wp_code" label="底稿编码" width="120" />
              <el-table-column prop="label" label="描述" min-width="200" />
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button size="small" link type="primary" @click="onConsolTraceLocate(row)">定位</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="无下游引用" :image-size="40" />
          </div>
          <el-empty v-else description="该数字暂无溯源信息" :image-size="60" />
        </template>
      </div>
    </el-dialog>

    <!-- 差额分录面板（需求 9.3）：点击企业树的合并差额 / 母分差额节点打开 -->
    <ConsolElimNodePanel
      v-model="elimPanelVisible"
      :project-id="projectId"
      :year="effectiveConsolYear()"
      :node="elimPanelNode"
      :tree="groupTree[0] || null"
      @changed="onElimChanged"
    />

    <!-- D5 合并范围确认弹窗 -->
    <ConsolScopeConfigDialog
      v-model="showScopeConfirmDialog"
      :project-id="projectId"
      @confirmed="onScopeConfirmed"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { exportMultiSheetData } from '@/composables/useExcelIO'
import {
  getConsolPushStatus,
  getWorksheetTree,
  pushConsolidation,
  type ConsolMode,
  type ConsolPushStatus,
  type ConsolTreeDiagnostic,
  type ConsolTreeNode,
  type CurrentConsolEntity,
} from '@/services/consolidationApi'
import { api } from '@/services/apiProxy'
import { projects as P_proj, reportConfig as P_rc, reportMapping as P_rm, consolNoteSections as P_cn, reports as reportPaths, consolidation as P_consol } from '@/services/apiPaths'
import { subscribeProjectEvent, type ProjectEventSubscription } from '@/services/sse/projectEventStream'
import ConsolWorksheetTabs from '@/components/consolidation/worksheets/ConsolWorksheetTabs.vue'
import ConsolNoteTab from '@/components/consolidation/ConsolNoteTab.vue'
import ConsolScopeConfigDialog from '@/components/wizard/ConsolScopeConfigDialog.vue'
import ConsolTrialBalanceTab from '@/components/consolidation/ConsolTrialBalanceTab.vue'
import ConsolReportBreakdownView from '@/components/consolidation/ConsolReportBreakdownView.vue'
import OrgNode from '@/components/consolidation/OrgNode.vue'
import ConsolElimNodePanel from '@/components/consolidation/ConsolElimNodePanel.vue'
import {
  buildNameIndex,
  canEnterProject,
  countNodes,
  currentConsolEntityForNode,
  findNodeByKey,
  flagTags,
  isElimNode,
  maxDepth,
  modeLabel,
  nodeLabel,
  roleLabel,
  sortDiagnostics,
  viaLabel,
} from '@/components/consolidation/composables/consolTreeView'
import { relationLabel } from '@/utils/groupRelation'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useTableSearch } from '@/composables/useTableSearch'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { eventBus } from '@/utils/eventBus'
import type { ConsolTreeSelectPayload, ConsolCatalogSelectPayload, ConsolRefreshEntityPayload } from '@/utils/eventBus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useConsolReportAddress } from '@/components/consolidation/composables/useConsolReportAddress'
import {
  cacheScopeKey as _cacheScopeKey,
  reportCacheKey as _reportCacheKey,
  noteCacheKey as _noteCacheKey,
  clearEntityCache as _clearEntityCache,
} from '@/components/consolidation/composables/consolCacheKeys'
import { createConsolRequestGuard } from '@/components/consolidation/composables/consolRequestGuard'
import ReportEquityTable from '@/components/report/ReportEquityTable.vue'
import { useReportColumns } from '@/views/composables/useReportColumns'
import { handleApiError } from '@/utils/errorHandler'
import { downloadFile, isRequestCancelled } from '@/utils/http'
import { useNavigationStack } from '@/composables/useNavigationStack'
import { useProjectEvents } from '@/composables/useProjectEvents'
import {
  CONSOL_PUSH_EVENTS,
  isCurrentConsolPushEvent,
  isFailedPushStatus,
  isPartialPushStatus,
  pushEventMessage,
  type ConsolPushEventPayload,
} from '@/components/consolidation/composables/consolPushEvents'

const route = useRoute()
const router = useRouter()
const { push: navPush } = useNavigationStack()
const projectId = computed(() => route.params.projectId as string)
// 自动建树 5.3：项目级事件流（含 CONSOL_SCOPE_CHANGED）
const consolEvents = useProjectEvents(projectId)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

// ─── 批注与复核持久化（合并报表/试算表共用） ─────────────────────────────────
const consolComments = useCellComments(() => projectId.value, effectiveConsolYear, 'consol_report')

const activeTab = ref('worksheets')

// D5 合并范围确认弹窗
const showScopeConfirmDialog = ref(false)
function onScopeConfirmed() {
  showScopeConfirmDialog.value = false
  // 确认后刷新企业树以反映最新状态
  refreshGroupTree()
  ElMessage.success('合并范围已确认，正在刷新企业树')
}
const projectInfoLoaded = ref(false)
const groupTreeLoaded = ref(false)
const worksheetContextReady = computed(() => (
  projectInfoLoaded.value
  && groupTreeLoaded.value
  && Boolean(projectId.value && effectiveConsolYear())
))
const worksheetContextKey = computed(() => `${projectId.value}:${effectiveConsolYear()}`)
const consolWorksheetTabsRef = ref<InstanceType<typeof ConsolWorksheetTabs> | null>(null)
const consolNoteTabRef = ref<InstanceType<typeof ConsolNoteTab> | null>(null)
const consolTbTabRef = ref<InstanceType<typeof ConsolTrialBalanceTab> | null>(null)

// ─── F5 合并页 stale 实时感知（需求 7 / ADR-CONSOL-304）────────────────────────
const consolStale = ref(false)

// ─── 合并推送状态与 raw SSE（spec consol-elimination-single-source-push 任务 14）────────
const consolPushStatus = ref<ConsolPushStatus | null>(null)
const consolPushQueuing = ref(false)
const consolPushFailure = ref('')
let consolPushSubs: ProjectEventSubscription[] = []

function effectiveConsolYear(): number {
  return treeYear.value ?? projectInfo.year ?? year.value
}

async function loadConsolPushStatus() {
  const effectiveYear = effectiveConsolYear()
  if (!projectId.value || !effectiveYear) return
  try {
    consolPushStatus.value = await getConsolPushStatus(projectId.value, effectiveYear)
    if (!isFailedPushStatus(consolPushStatus.value.last_run?.status)) consolPushFailure.value = ''
    else if (!consolPushFailure.value) consolPushFailure.value = '最近一次合并推送失败，请在公式管理的“合并推送”页查看完整步骤与警告'
  } catch {
    consolPushStatus.value = null
  }
}

async function queueConsolPush() {
  if (consolPushQueuing.value) return
  consolPushQueuing.value = true
  try {
    const ack = await pushConsolidation(projectId.value, effectiveConsolYear(), 'manual')
    if (ack.queued) ElMessage.success(ack.message || '已开始推送，完成后自动刷新')
    else ElMessage.info(ack.message || '已有推送在排队，本次请求已并入')
    // 不能提前清过期：等 pushed 后查权威 push-status，确认 stale 已归零再清
  } finally {
    consolPushQueuing.value = false
  }
}

async function refreshCurrentAfterConsolPush() {
  if (activeTab.value === 'worksheets') await consolWorksheetTabsRef.value?.reload()
  else if (activeTab.value === 'structure') await refreshGroupTree()
  else if (activeTab.value === 'consol_tb') loadConsolTb()
  else if (activeTab.value === 'consol_report') reloadConsolReportView(true)
  else if (activeTab.value === 'consol_note') loadConsolNoteTree(true)
}

async function onConsolPushEvent(raw: unknown, eventName: string) {
  if (!raw || typeof raw !== 'object') return
  const payload = raw as ConsolPushEventPayload
  if (!isCurrentConsolPushEvent(payload, projectId.value, effectiveConsolYear())) return
  if (eventName === CONSOL_PUSH_EVENTS.stale) {
    await loadConsolPushStatus()
    return
  }
  if (eventName === CONSOL_PUSH_EVENTS.failed) {
    const message = pushEventMessage(payload, '合并推送失败，请在公式管理的“合并推送”页查看完整步骤与警告')
    consolPushFailure.value = message
    ElNotification({ title: '合并推送失败', message, type: 'error', duration: 8000 })
    await loadConsolPushStatus()
    return
  }
  if (eventName !== CONSOL_PUSH_EVENTS.pushed) return
  await Promise.all([loadConsolPushStatus(), refreshCurrentAfterConsolPush()])
  if (isPartialPushStatus(payload.status)) {
    ElMessage.warning(pushEventMessage(payload, '合并推送部分成功，请在“合并推送”页查看警告'))
  } else {
    ElMessage.success('合并推送完成，当前视图已刷新')
  }
}

function stopConsolPushEvents() {
  for (const sub of consolPushSubs) sub.close()
  consolPushSubs = []
}

function bindConsolPushEvents() {
  stopConsolPushEvents()
  for (const eventName of Object.values(CONSOL_PUSH_EVENTS)) {
    consolPushSubs.push(subscribeProjectEvent(projectId.value, eventName, onConsolPushEvent))
  }
}

// ─── F3 一键刷新全部 + 重新汇总附注（需求 9 / Phase 2 A5 + V2 接线）──────────────
import {
  useConsolRefreshTracking,
  type RefreshContext,
  type RefreshPartStatus,
} from '@/components/consolidation/composables/useConsolRefreshTracking'

const refreshAllLoading = ref(false)
const reaggregateLoading = ref(false)

const refreshTracking = useConsolRefreshTracking({
  reloadReportView: () => reloadConsolReportView(),
  loadGroupTree: () => loadGroupTree(),
  reloadNoteForRefresh: (ctx) => reloadNoteForRefresh(ctx),
  captureRefreshContext: () => captureRefreshContext(),
  getActiveTab: () => activeTab.value,
})
const refreshState = refreshTracking.state
const refreshProgress = refreshTracking.progress

/**
 * 一键级联刷新全部（需求 9 / Phase 2 A5）。
 * POST refresh-all 入队后台 worker 返回 job_id；进度经既有 events/stream SSE
 * 推送（consol.refresh.progress/completed/error），SSE 不可用时轮询 refresh-status 兜底（EH6）。
 */
async function onRefreshAll() {
  if (refreshAllLoading.value) return
  const effectiveYear = effectiveConsolYear()
  if (!projectId.value || !effectiveYear) {
    refreshAllLoading.value = false
    refreshProgress.visible = false
    return
  }
  // 冻结刷新上下文：完成回调只向该快照提交（设计 §六 / 需求 6.1）
  const context = captureRefreshContext()
  refreshAllLoading.value = true
  refreshProgress.visible = true
  refreshProgress.step = ''
  refreshProgress.current = 0
  refreshProgress.total = 0
  refreshProgress.node = ''
  try {
    const res: any = await api.post(P_consol.refreshAll(context.projectId, context.year))
    const jobId = res?.job_id || ''
    const resPid = String(res?.project_id || '')
    const resYear = Number(res?.year || 0)
    // 校验后端返回的项目/年度与冻结上下文一致
    if (!jobId || (resPid && resPid !== context.projectId) || (resYear && resYear !== context.year)) {
      refreshAllLoading.value = false
      refreshProgress.visible = false
      refreshState.tree = 'failed'
      refreshState.treeReason = '刷新任务返回异常'
      refreshState.note = 'failed'
      refreshState.noteReason = '刷新任务返回异常'
      ElMessage.error('一键刷新返回数据异常，请重试')
      return
    }
    ElMessage.success('已开始一键刷新，正在更新整棵树的报表与附注…')
    refreshTracking.start(jobId, context)
  } catch (e) {
    refreshAllLoading.value = false
    refreshProgress.visible = false
    refreshState.tree = 'failed'
    refreshState.treeReason = '请求失败'
    refreshState.note = 'failed'
    refreshState.noteReason = '请求失败'
    handleApiError(e, '一键刷新全部')
  }
}

/**
 * 重新汇总合并附注（需求 9 / V2 接线 / 需求 6.5）。
 * POST notes/reaggregate 消费子公司单体附注重新汇总；成功后重读当前章节，
 * 只有当前章节持久化 GET 返回 done 才清除 consolStale。
 */
async function onReaggregateNotes() {
  if (reaggregateLoading.value) return
  reaggregateLoading.value = true
  const context = captureRefreshContext()
  try {
    const body: Record<string, unknown> = {
      section_ids: context.sectionId ? [context.sectionId] : [],
      node_key: context.nodeKey || null,
      standard: consolNoteTemplateType.value,
      template_type: consolNoteTemplateType.value,
    }
    const res: any = await api.post(P_consol.notes.reaggregate(context.projectId, context.year), body)
    const updated = res?.sections_updated ?? res?.sections_processed ?? 0
    const errCount = Array.isArray(res?.errors) ? res.errors.length : 0
    if (errCount > 0) {
      ElMessage.warning(`附注重新汇总完成（更新 ${updated} 个章节，${errCount} 个章节有告警）`)
    } else {
      ElMessage.success(`附注重新汇总完成（更新 ${updated} 个章节）`)
    }
    activeTab.value = 'consol_note'
    await loadConsolNoteTree(true)
    // 持久化重读当前章节作为完成证据
    const noteResult = await reloadNoteForRefresh(context)
    if (noteResult?.status === 'done') {
      consolStale.value = false
    } else {
      // POST 成功但章节重读不是 done → 保持 stale
      const reason = noteResult?.reason || '附注章节重读未完成'
      ElMessage.warning(`重新汇总完成，但章节重读${noteResult?.status === 'failed' ? '失败' : '跳过'}：${reason}`)
    }
  } catch (e) {
    handleApiError(e, '重新汇总附注')
  } finally {
    reaggregateLoading.value = false
  }
}

// ─── 合并方式与企业树诊断（consol-tree-three-code-autobuild 需求 4.4 / 9.4）────────────
// 不再手工切换：按下级企业的与上级关系自动识别（项目配置接口写 consolidation_type 已返回 400）。
// 识别结果与诊断都取企业树接口；取数失败时显示「自动识别」。
const treeMode = ref<ConsolMode | null>(null)
const treeModeLabel = ref<string | null>(null)
const treeYear = ref<number | null>(null)
const treeMessage = ref('')
const treeDiagnostics = ref<ConsolTreeDiagnostic[]>([])
const diagnosticsDismissed = ref(false)
const showAllDiagnostics = ref(false)
const DIAG_PREVIEW = 5
const consolModeLabel = computed(() => modeLabel(treeMode.value, treeModeLabel.value) || '自动识别')
const treeWarnings = computed(() => treeDiagnostics.value.filter((d) => d.level !== 'info'))
const visibleDiagnostics = computed(() => {
  const sorted = sortDiagnostics(treeDiagnostics.value)
  return showAllDiagnostics.value ? sorted : sorted.slice(0, DIAG_PREVIEW)
})

// ─── 项目基本信息 ─────────────────────────────────────────────────────────────
const projectInfo = reactive({
  clientName: '',
  year: new Date().getFullYear() - 1,
  standard: 'soe' as 'soe' | 'listed',
})

const currentYear = new Date().getFullYear()
const barYearOptions = computed(() => {
  const years = []
  for (let y = currentYear; y >= currentYear - 5; y--) years.push(y)
  return years
})

function onYearChange() {
  // 年度切换后让企业树年度与报表/附注读取口径保持一致。
  groupTreeLoaded.value = false
  treeYear.value = projectInfo.year
  reportCache.clear()
  noteCache.clear()
  loadConsolReport(true)
  loadConsolNoteTree(true)
  void loadGroupTree()
}

function onStandardChange() {
  consolReportTemplateType.value = projectInfo.standard
  consolNoteTemplateType.value = projectInfo.standard
  loadConsolReport(true)
  loadConsolNoteTree(true)
  // 通知 ConsolCatalog 更新准则
  eventBus.emit('standard-change', { standard: projectInfo.standard })
}

function onOpenFormula() {
  const effectiveYear = effectiveConsolYear()
  if (activeTab.value === 'consol_note') {
    const section = consolNoteTabRef.value?.selectedNoteSection
    eventBus.emit('open-formula-manager', {
      nodeKey: 'consol_note', scope: 'consol_note', projectId: projectId.value, year: effectiveYear,
      templateType: consolNoteTemplateType.value, noteSection: section?.section_id, noteSectionTitle: section?.title,
    })
    return
  }
  if (activeTab.value === 'worksheets') {
    eventBus.emit('open-formula-manager', {
      nodeKey: 'consolidation', scope: 'consol_worksheet', projectId: projectId.value, year: effectiveYear,
      templateType: consolReportTemplateType.value,
    })
    return
  }
  const reportType = activeTab.value === 'consol_tb' ? consolTbType.value : consolReportType.value
  eventBus.emit('open-formula-manager', {
    nodeKey: 'consol_report', scope: 'consol_report', projectId: projectId.value, year: effectiveYear,
    templateType: consolReportTemplateType.value, initialReportType: reportType,
  })
}

// ─── 单元格汇总穿透查看 ──────────────────────────────────────────────────────
const showCellDrillDown = ref(false)
const drillDownLoading = ref(false)
const drillDownLevel = ref<'direct' | 'leaf'>('direct')
const drillDownCell = reactive({ itemName: '', colName: '', totalValue: 0 as number | null, sectionId: '', rowIdx: -1, colIdx: -1 })
// consolBreakdown drill：当前穿透科目的 ACNR TB 域 jump_route（Req 20.1），miss 时为 null
const drillDownAccountCode = ref('')
const drillDownJumpRoute = ref<string | null>(null)
const drillDownDirectRows = ref<any[]>([])
const drillDownLeafRows = ref<any[]>([])
const drillDownTransposed = ref(false)
const drillDownTableRef = ref<any>(null)

// ─── 单元格选中与右键菜单（统一 composable） ──────────────────────────────
const consolCtx = useCellSelection()
const consolTableRef = ref<any>(null)
consolCtx.setupTableDrag(consolTableRef, (rowIdx: number, colIdx: number) => {
  const row = consolReportRows.value[rowIdx]
  if (!row) return null
  if (colIdx === 0) return row.row_code
  if (colIdx === 1) return row.row_name
  if (colIdx === 2) return row.current_period_amount
  if (colIdx === 3) return row.prior_period_amount
  return null
})

// ─── 显示偏好（全局单位/字号） ──────────────────────────────────────────────
const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const consolSearch = useTableSearch(computed(() => []), ['row_name'])

// 兼容别名（供 drillDown 等已有逻辑使用）
const selectedCells = consolCtx.selectedCells

const currentDrillDownRows = computed(() => {
  return drillDownLevel.value === 'direct' ? drillDownDirectRows.value : drillDownLeafRows.value
})
const drillDownTitle = computed(() => {
  return `汇总穿透 — ${drillDownCell.itemName} / ${drillDownCell.colName}`
})

const consolEquityTableHeight = ref(600)
function updateConsolEquityTableHeight() {
  consolEquityTableHeight.value = Math.max(400, window.innerHeight - 280)
}
function impairRowClassName({ row }: { row: any }): string {
  if (row.is_total_row) return 'gt-cm-total-row'
  return ''
}

// ─── 穿透转置视图 el-table 辅助 ──────────────────────────────────────────────
const drillDownTransposedRows = computed(() => {
  const rows: any[] = []
  const items = currentDrillDownRows.value
  // 企业代码行
  const codeRow: any = { field: '企业代码', total: '—' }
  items.forEach((r, i) => { codeRow['col_' + i] = r.company_code })
  rows.push(codeRow)
  // 上级单位行（仅末级明细）
  if (drillDownLevel.value === 'leaf') {
    const parentRow: any = { field: '上级单位', total: '—' }
    items.forEach((r, i) => { parentRow['col_' + i] = r.parent_name || '—' })
    rows.push(parentRow)
  }
  // 金额行
  const amtRow: any = { field: '金额', total: fmtAmt(drillDownCell.totalValue) }
  items.forEach((r, i) => { amtRow['col_' + i] = fmtAmt(r.amount) })
  rows.push(amtRow)
  // 占比行
  const ratioRow: any = { field: '占比', total: '100%' }
  items.forEach((r, i) => { ratioRow['col_' + i] = r.ratio + '%' })
  rows.push(ratioRow)
  // 数据来源行（仅直接下级）
  if (drillDownLevel.value === 'direct') {
    const srcRow: any = { field: '数据来源', total: '—' }
    items.forEach((r, i) => { srcRow['col_' + i] = r.source })
    rows.push(srcRow)
  }
  return rows
})

function openCellDrillDown() {
  // 合并附注：走新附注差额内核（四度量 + 子节点贡献），不再读旧 info JSON / 持股比例估算
  const noteTab = consolNoteTabRef.value
  if (activeTab.value === 'consol_note') {
    if (!noteTab?.selectedNoteSection) {
      ElMessage.info('请先打开一个附注表格并选中单元格')
      return
    }
    noteTab.openNoteBreakdownForSelection()
    return
  }

  // 报表模式
  if (consolReportRows.value.length) {
    showCellDrillDown.value = true
    drillDownCell.itemName = '请在报表中选择科目'
    drillDownCell.colName = '合并本期'
    drillDownCell.totalValue = null
    loadDrillDownData()
    return
  }

  ElMessage.info('请先打开一个附注表格或报表，选中行后再点击查看')
}

async function loadDrillDownData() {
  // 每次穿透先清空 consolBreakdown drill 的 jump_route（避免上次残留，Req 20.1）
  drillDownJumpRoute.value = null
  drillDownAccountCode.value = ''
  if (!drillDownCell.itemName || drillDownCell.itemName.startsWith('请')) {
    drillDownDirectRows.value = []
    drillDownLeafRows.value = []
    return
  }
  drillDownLoading.value = true
  try {
    // 确定当前查看的报表类型和行次
    const reportType = activeTab.value === 'consol_tb' ? consolTbType.value : consolReportType.value
    const sourceRows = activeTab.value === 'consol_tb' ? consolTbRows.value : consolReportRows.value
    const selectedRow = selectedCells.value.length ? sourceRows[selectedCells.value[0].row] : null
    const rowCode = selectedRow?.row_code || ''
    const colField = drillDownCell.colName?.includes('上期') ? 'prior_period_amount' : 'current_period_amount'

    // consolBreakdown drill：account_code 经 ACNR TB 域解析取 jump_route（Req 20.1）。
    // 数值穿透仍走既有 P_rc.drillDown（逻辑不变，Req 20.9）；此处仅附加地址跳转能力，miss 回退纯文本。
    const acctCode = consolReportAddr.accountForRow(selectedRow) || (activeTab.value === 'consol_tb' ? (selectedRow?.standard_account_code || '') : '')
    drillDownAccountCode.value = acctCode
    if (acctCode) {
      consolReportAddr.resolveAccountJump(acctCode).then((r) => {
        drillDownJumpRoute.value = r.found ? r.jumpRoute : null
      }).catch(() => { drillDownJumpRoute.value = null })
    }

    // 按企业树取该行的构成（与报表差额表同一求值；上期列暂无树上构成，只穿透本期）
    if (colField === 'prior_period_amount') {
      drillDownDirectRows.value = []
      drillDownLeafRows.value = []
      ElMessage.info('上期数取自上年合并报表，不按企业树穿透')
      return
    }
    const result: any = await api.post(P_rc.drillDown, {
      project_id: projectId.value,
      year: effectiveConsolYear(),
      report_type: reportType,
      row_code: rowCode,
      // 试算页选了下级汇总节点 ⇒ 按该节点的直接下级分解（与页面显示的数同一节点）
      ...(activeTab.value === 'consol_tb' && consolTbTabRef.value?.nodeKey ? { node_key: consolTbTabRef.value.nodeKey } : {}),
    })
    const toRow = (r: any) => ({
      company_name: r.company_name,
      company_code: r.company_code,
      amount: r.amount == null ? null : Number(r.amount),
      ratio: r.pct == null ? 0 : Number(r.pct),
      source: r.reason ? `${r.source}（${r.reason}）` : r.source,
      parent_name: r.parent_name || '',
    })
    drillDownDirectRows.value = (result?.rows || []).map(toRow)
    drillDownLeafRows.value = (result?.leaf_rows || []).map(toRow)
    if (result?.note) ElMessage.info(result.note)
  } catch (err: any) {
    drillDownDirectRows.value = []
    drillDownLeafRows.value = []
    handleApiError(err, '汇总穿透')
  } finally { drillDownLoading.value = false }
}

/**
 * consolBreakdown drill 跳转：使用 ACNR TB 域解析得到的 jump_route 打开试算表科目（Req 20.1/20.2）。
 * jump_route 由 `resolveAccountJump` 经 ACNR 统一出口取得（不自行拼底稿路由，R7.3 铁律）；
 * 含 {project_id} 占位符则替换。miss 时按钮不显示，故此处 route 必非空。
 */
function onConsolBreakdownJump() {
  const route = drillDownJumpRoute.value
  if (!route) { ElMessage.warning('该科目地址已失效'); return }
  const finalRoute = route.replace('{project_id}', projectId.value)
  window.open(finalRoute, '_blank', 'noopener')
}

function drillDownSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums.push('合计'); return }
    if (col.property === 'amount') {
      const total = data.reduce((s: number, r: any) => s + (Number(r.amount) || 0), 0)
      sums.push(fmtAmt(total))
    } else if (col.property === 'ratio') {
      const total = data.reduce((s: number, r: any) => s + (Number(r.ratio) || 0), 0)
      sums.push(`${Math.round(total * 100) / 100}%`)
    } else {
      sums.push('')
    }
  })
  return sums
}

function copyDrillDownTable() {
  const rows = currentDrillDownRows.value
  if (!rows.length) { ElMessage.warning('无数据可复制'); return }
  const isLeaf = drillDownLevel.value === 'leaf'
  const headers = isLeaf ? ['末级企业', '企业代码', '上级单位', '金额', '占比'] : ['企业名称', '企业代码', '金额', '占比', '数据来源']
  const lines = [headers.join('\t')]
  for (const r of rows) {
    const vals = isLeaf
      ? [r.company_name, r.company_code, r.parent_name, r.amount ?? '', `${r.ratio}%`]
      : [r.company_name, r.company_code, r.amount ?? '', `${r.ratio}%`, r.source]
    lines.push(vals.join('\t'))
  }
  navigator.clipboard?.writeText(lines.join('\n'))
  ElMessage.success('已复制到剪贴板（可粘贴到 Excel）')
}

async function exportDrillDown() {
  const rows = currentDrillDownRows.value
  if (!rows.length) return
  const isLeaf = drillDownLevel.value === 'leaf'
  const headers = isLeaf
    ? ['序号', '末级企业', '企业代码', '上级单位', '金额', '占比']
    : ['序号', '企业名称', '企业代码', '金额', '占比', '数据来源']
  const dataRows = rows.map((r: any, i: number) => isLeaf
    ? [i + 1, r.company_name, r.company_code, r.parent_name, r.amount, `${r.ratio}%`]
    : [i + 1, r.company_name, r.company_code, r.amount, `${r.ratio}%`, r.source]
  )
  // 走 useExcelIO 单一入口（B7 批）。
  await exportMultiSheetData({
    sheets: [{
      sheetName: '汇总穿透',
      rows: [headers, ...dataRows],
      colWidths: headers.map(() => ({ wch: 16 })),
    }],
    fileName: `汇总穿透_${drillDownCell.itemName}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('已导出')
}

async function loadProjectInfo() {
  projectInfoLoaded.value = false
  try {
    const data = await api.get(P_proj.detail(projectId.value), { validateStatus: (s: number) => s < 600 })
    const p = data
    if (p) {
      projectInfo.clientName = p.client_name || p.name || ''
      projectInfo.year = p.audit_year || year.value
      projectInfo.standard = (p.applicable_standard || '').includes('listed') ? 'listed' : 'soe'
      // 非合并项目不应进入合并模块，弹提示并跳回
      const scope = p.report_scope || p.scope || ''
      if (scope && scope !== 'consolidated') {
        ElMessage.warning('当前为单体项目，无合并报表功能')
        router.push(`/projects/${projectId.value}`)
        return
      }
    }
    projectInfoLoaded.value = true
  } catch {
    projectInfoLoaded.value = false
  }
}

// ─── Tab 1: 集团架构（企业树只渲染后端三码推导结果，需求 9.1）─────────────────────
const groupTree = ref<ConsolTreeNode[]>([])
const selectedNode = ref<ConsolTreeNode | null>(null)
const orgViewMode = ref<'chart' | 'tree'>('chart')
const orgZoom = ref(0.85)

const orgNodeCount = computed(() => countNodes(groupTree.value[0]))
const orgMaxDepth = computed(() => maxDepth(groupTree.value[0]))
const treeNames = computed(() => buildNameIndex(groupTree.value[0]))
const treeEmptyText = computed(() => treeMessage.value || '暂无企业树：请在各子公司/分公司项目的基本信息中填写上级代码')

// ─── 差额分录面板（需求 9.3）──────────────────────────────────────────────────
const elimPanelVisible = ref(false)
const elimPanelNode = ref<ConsolTreeNode | null>(null)

function openElimPanel(node: ConsolTreeNode) {
  elimPanelNode.value = node
  elimPanelVisible.value = true
}

/** 差额分录变更（新增/修改/审批…）后重读企业树：未归属分录诊断可能变化 */
function onElimChanged() {
  loadGroupTree()
}

// 自动建树 5.3/5.4：手动刷新 + CONSOL_SCOPE_CHANGED 事件自动刷新的状态标记
const treeRefreshing = ref(false)

/**
 * 自动建树 5.4：手动刷新企业树（EH4 兜底，事件丢失时用户可手动触发）。
 * 同时复用为 5.3 SSE 事件回调的实现。
 */
async function refreshGroupTree() {
  treeRefreshing.value = true
  try {
    await loadGroupTree()
  } finally {
    treeRefreshing.value = false
  }
}

/**
 * 自动建树 5.3：CONSOL_SCOPE_CHANGED 事件回调 → 自动刷新企业树。
 * F5 6A.2：consol.note_stale 事件 → 显示"建议重新汇总"提示（warning 不阻断）。
 * 仅响应合并相关事件（其他项目事件忽略；项目过滤由 useProjectEvents 完成）。
 */
function onConsolScopeChanged(evt: { event_type: string }) {
  if (evt.event_type === 'consol.scope_changed') {
    refreshGroupTree()
  } else if (evt.event_type === 'consol.note_stale') {
    // F5：子公司数据变更导致母项目 stale → 提示重新汇总
    consolStale.value = true
  }
}

/**
 * F5 6A.3：立即重新汇总快捷入口 → 跳合并附注 Tab 并真正调用重新汇总 API（需求 6.5）。
 */
async function onReaggregateNow() {
  activeTab.value = 'consol_note'
  await nextTick()
  await onReaggregateNotes()
}

/**
 * 读取企业树（三码推导）+ 合并方式 + 诊断 + 年度。
 * 不再回退 listChildProjects：项目列表接口不支持按上级项目过滤，回退结果是全部可见项目（F13）。
 */
async function loadGroupTree(): Promise<boolean> {
  groupTreeLoaded.value = false
  try {
    const res = await getWorksheetTree(projectId.value)
    groupTree.value = res?.tree ? [res.tree] : []
    treeMode.value = res?.mode ?? null
    treeModeLabel.value = res?.mode_label ?? null
    treeYear.value = res?.year ?? null
    treeMessage.value = res?.tree ? '' : (res?.message || '')
    treeDiagnostics.value = Array.isArray(res?.diagnostics) ? res.diagnostics : []
    diagnosticsDismissed.value = false
    groupTreeLoaded.value = true
  } catch (e: any) {
    // GET 去重导致的 cancel（axios abort）不是真正的失败——静默忽略，
    // 后发的请求会带回正确数据（http.ts addPending GET 去重机制）。
    if (isRequestCancelled(e)) return false
    groupTree.value = []
    treeMode.value = null
    treeModeLabel.value = null
    treeDiagnostics.value = []
    treeMessage.value = '加载企业树失败，请稍后重试'
    groupTreeLoaded.value = false
    return false
  }
  // 树变化后刷新选中节点与面板节点的引用（节点可能已消失）
  const root = groupTree.value[0]
  if (selectedNode.value) selectedNode.value = findNodeByKey(root, selectedNode.value.node_key)
  if (elimPanelNode.value) {
    const fresh = findNodeByKey(root, elimPanelNode.value.node_key)
    if (fresh) elimPanelNode.value = fresh
  }
  if (!currentConsolEntity.value.nodeKey || currentConsolEntity.value.nodeKey === ROOT_CONSOL_NODE_KEY) {
    currentConsolEntity.value.nodeKey = root?.node_key || ROOT_CONSOL_NODE_KEY
  }
  return true
}

function onTreeNodeClick(data: ConsolTreeNode) {
  selectedNode.value = data
  if (isElimNode(data)) {
    openElimPanel(data)
    return
  }
  currentConsolEntity.value = currentConsolEntityForNode(data)
  if (activeTab.value === 'consol_report') reloadConsolReportView()
  else if (activeTab.value === 'consol_note') {
    // 切换节点后重读当前章节（不只刷新目录）
    const section = consolNoteTabRef.value?.selectedNoteSection
    if (section?.section_id) {
      consolNoteTabRef.value?.onNoteNodeClick({ section_id: section.section_id, title: section.title })
    } else {
      loadConsolNoteTree()
    }
  }
}

// ── 合并范围模板保存/引用 ──
function getConsolScopeConfigData(): Record<string, any> {
  return {
    group_tree: groupTree.value,
    standard: projectInfo.standard,
  }
}

function onConsolScopeTemplateApplied(_data: Record<string, any>) {
  // 企业树只来自后端按三码推导（需求 9.1）：模板里存的旧树不再覆盖当前树，只重新读取一次
  loadGroupTree()
  ElMessage.success('合并范围模板已应用（企业树按各项目的企业代码自动生成）')
}

/** 下级合并企业（不是本项目）可以跳到它自己的合并页 */
function canOpenSubConsol(node: ConsolTreeNode | null): boolean {
  return !!node && node.role === 'consol' && !!node.project_id && node.project_id !== projectId.value
}

function goToProject(node: ConsolTreeNode | null) {
  if (!canOpenSubConsol(node)) return
  router.push({ path: `/projects/${node!.project_id}/consolidation`, query: { year: String(effectiveConsolYear()) } })
}

/**
 * 双向导航 4.2：从合并树节点进入对应项目（合并节点 = 合并项目，数据节点 = 单户项目）。
 * 跳转前 push 当前路由到导航栈（direction:'down' 下钻），支持 Backspace 返回（T3）。
 * 差额节点与有分公司的汇总节点没有自己的项目，不显示入口。
 */
function onEnterProject(node: ConsolTreeNode) {
  const targetId = node?.project_id
  if (!targetId) {
    ElMessage.info('该节点没有对应的项目')
    return
  }
  const cur = router.currentRoute.value
  navPush({
    source_view: cur.path,
    label: '合并项目',
    direction: 'down',
    scroll_position: window.scrollY,
    query: cur.query as Record<string, string>,
  })
  // 单体项目默认落地页：entry 路由按角色重定向到仪表盘/试算表
  router.push({ path: `/projects/${targetId}/entry` })
}

function fmtAmt(v: any): string {
  return fmt(v)
}

// ─── 合并试算平衡表（ConsolTrialBalanceTab：只读，按报表行次读时计算） ──────────
// 兼容别名：供「汇总穿透」等逻辑引用当前表的行与报表类型
const consolTbRows = computed(() => consolTbTabRef.value?.rows || [])
const consolTbType = computed(() => consolTbTabRef.value?.reportType || 'balance_sheet')

function loadConsolTb() {
  consolTbTabRef.value?.load()
}

function onTbAudit(results: any[]) {
  noteAuditResults.value = results
  noteAuditSummary.totalSections = 1
  noteAuditSummary.totalChecks = results.length
  noteAuditSummary.passCount = results.filter(r => r.level === 'pass').length
  noteAuditSummary.errorCount = results.filter(r => r.level === 'error').length
  noteAuditSummary.warnCount = results.filter(r => r.level === 'warn').length
  showNoteAuditDialog.value = true
}

/** 试算页右键：「汇总穿透」按合并审定数看企业树构成（单元格本身点开是分录 / 个别数穿透） */
function onTbCellContextMenu(e: MouseEvent, row: any, ri: number) {
  const value = row.consolidated == null ? null : Number(row.consolidated)
  selectedCells.value = [{ row: ri, col: 2, value }]
  drillDownCell.itemName = row.row_name
  drillDownCell.colName = '合并审定数'
  drillDownCell.totalValue = value
  consolCtx.openContextMenu(e, row.row_name, row)
}

// ─── Tab 5: 合并报表 ─────────────────────────────────────────────────────────
const consolReportTemplateType = ref('soe')
const consolReportType = ref('balance_sheet')
const consolReportLoading = ref(false)

// 当前选中的合并主体（树形节点），每个合并节点有独立的报表和附注
const ROOT_CONSOL_NODE_KEY = 'root:consol'
const currentConsolEntity = ref<CurrentConsolEntity>({ code: '', name: '', nodeKey: ROOT_CONSOL_NODE_KEY })

function effectiveEntityYear(): number {
  return treeYear.value ?? projectInfo.year ?? year.value
}

const currentEntityNodeKey = computed((): string => {
  return currentConsolEntity.value.nodeKey || groupTree.value[0]?.node_key || ROOT_CONSOL_NODE_KEY
})

function captureRefreshContext(): RefreshContext {
  return {
    projectId: String(projectId.value || ''),
    year: effectiveConsolYear(),
    nodeKey: currentEntityNodeKey.value,
    sectionId: String(consolNoteTabRef.value?.selectedNoteSection?.section_id || ''),
  }
}

function isRefreshBaseContextCurrent(context: RefreshContext): boolean {
  return String(projectId.value || '') === context.projectId
    && effectiveConsolYear() === context.year
    && currentEntityNodeKey.value === context.nodeKey
    && String(consolNoteTabRef.value?.selectedNoteSection?.section_id || '') === context.sectionId
}

async function reloadNoteForRefresh(context: RefreshContext): Promise<any> {
  if (!context.sectionId) {
    return { status: 'skipped', reason: '刷新开始时未选择附注章节' }
  }
  if (!isRefreshBaseContextCurrent(context)) {
    return { status: 'skipped', reason: '刷新期间合并节点已切换' }
  }
  await nextTick()
  const child = consolNoteTabRef.value
  if (!child?.reloadCurrentSectionAfterRefresh) {
    return { status: 'failed', reason: '附注组件未提供持久化重读方法' }
  }
  return child.reloadCurrentSectionAfterRefresh({
    projectId: context.projectId,
    year: context.year,
    nodeKey: context.nodeKey,
    sectionId: context.sectionId,
  })
}

const reportNavItems = [
  { key: 'balance_sheet', label: '资产负债表', desc: '合并资产负债表', icon: '📋' },
  { key: 'income_statement', label: '利润表', desc: '合并利润表', icon: '📈' },
  { key: 'cash_flow_statement', label: '现金流量表', desc: '合并现金流量表', icon: '💰' },
  { key: 'equity_statement', label: '权益变动表', desc: '合并所有者权益变动表', icon: '📊' },
  { key: 'cash_flow_supplement', label: '现金流附表', desc: '现金流量表补充资料', icon: '📑' },
  { key: 'impairment_provision', label: '资产减值准备表', desc: '合并资产减值准备明细', icon: '⚠️' },
]
const currentReportLabel = computed(() => {
  return reportNavItems.find(i => i.key === consolReportType.value)?.label || '合并报表'
})
const consolReportRows = ref<any[]>([])

// 合并报表页视图：合并报表 / 差额表（需求 5.4，默认显示根合并节点）
const consolReportView = ref<'report' | 'breakdown'>('report')
const consolBreakdownViewRef = ref<InstanceType<typeof ConsolReportBreakdownView> | null>(null)

/** 切报表类型：合并报表视图读已生成的报表；差额表视图由组件监听报表类型自行重读 */
function selectConsolReportType(key: string) {
  consolReportType.value = key
  if (consolReportView.value === 'report') loadConsolReport()
}

async function setConsolReportView(view: 'report' | 'breakdown') {
  if (consolReportView.value === view) return
  consolReportView.value = view
  if (view === 'report') {
    loadConsolReport()
    return
  }
  await nextTick()
  consolBreakdownViewRef.value?.load()
}

/** 刷新合并报表页的当前视图（推送完成等场景） */
function reloadConsolReportView(force = false) {
  if (consolReportView.value === 'breakdown') consolBreakdownViewRef.value?.load()
  else loadConsolReport(force)
}

// ─── 合并报表 报表行 / account 引用 → ACNR REPORT/TB 域（Req 20.1/20.2/20.7/20.9）──
// 报表行地址/坐标名称真源收敛到 ACNR-backed 注册表；account 引用经 TB 域解析取 jump_route。
// 仅改地址/跳转来源，不改报表数值/生成/balance-check 逻辑（Req 20.9）。
const consolReportAddr = useConsolReportAddress()
/** 报表行 行次 单元格：可经 ACNR TB 域解析的 account 引用 → GtIndexChip 索引语法；否则 null 回退纯文本。 */
function reportAccountChip(row: any): string | null {
  return consolReportAddr.accountIndexRef(consolReportAddr.accountForRow(row))
}

const showConsolConversion = ref(false)
const consolMappingLoading = ref(false)
const consolMappingRules = ref<any[]>([])

const consolIsConsolidated = computed(() => true)
const {
  eqColumns,
  eqTotalCols,
  equitySpanMethod,
  eqRowClassName,
  eqCellVal,
} = useReportColumns({
  isConsolidated: consolIsConsolidated,
  activeTab: consolReportType,
  rows: consolReportRows,
})

// ─── 前端缓存：按项目/年度/节点身份/报表类型缓存，刷新时精确清理 ──────────
// 纯逻辑已提取到 consolCacheKeys.ts（可测试）；这里仅组装当前 reactive 参数。
const reportCache = new Map<string, any[]>()
const noteCache = new Map<string, any[]>()

function cacheScopeKey(nodeKey = currentEntityNodeKey.value): string {
  return _cacheScopeKey(projectId.value, effectiveEntityYear(), nodeKey)
}

function reportCacheKey(): string {
  return _reportCacheKey(projectId.value, effectiveEntityYear(), currentEntityNodeKey.value, consolReportType.value, consolReportTemplateType.value)
}
function noteCacheKey(): string {
  return _noteCacheKey(projectId.value, effectiveEntityYear(), currentEntityNodeKey.value, consolNoteTemplateType.value)
}
/** 清除指定树节点的缓存（刷新时调用；不能按企业代码清理同企业的其他角色节点） */
function clearEntityCache(nodeKey: string, types?: string[]) {
  _clearEntityCache(reportCache, noteCache, projectId.value, effectiveEntityYear(), nodeKey, types)
}

// ─── 请求上下文保护：切项目/年度/nodeKey 后旧响应不得提交（设计 §七、P9）──────
// 每次异步加载前 startRequest 递增序号并快照上下文；响应提交前 isStale 校验。
const reportRequestGuard = createConsolRequestGuard(() => ({
  projectId: projectId.value,
  year: effectiveEntityYear(),
  nodeKey: currentEntityNodeKey.value,
}))

function consolReportRowClass({ row }: { row: any }) {
  if (row.is_total_row) return 'gt-total-row'
  return ''
}

function reportCellClassName({ rowIndex, columnIndex }: any) {
  const classes: string[] = []
  const selClass = consolCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  const sheetKey = `report_${consolReportType.value}`
  const ccClass = consolComments.commentCellClass(sheetKey, rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

function onReportCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  consolCtx.closeContextMenu()
  const rowIdx = consolReportRows.value.indexOf(row)
  const colMap: Record<string, number> = { '行次': 0, '项目': 1, '合并本期': 2, '合并上期': 3 }
  const colIdx = colMap[column.label] ?? -1
  if (rowIdx < 0 || colIdx < 0) return
  const value = colIdx === 2 ? row.current_period_amount : colIdx === 3 ? row.prior_period_amount : row.row_name
  consolCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
  if (consolCtx.selectedCells.value.length === 1) {
    drillDownCell.itemName = row.row_name || ''
    drillDownCell.colName = column.label || ''
    drillDownCell.totalValue = Number(value) || null
  }
}

function onReportCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const rowIdx = consolReportRows.value.indexOf(row)
  const colMap: Record<string, number> = { '行次': 0, '项目': 1, '合并本期': 2, '合并上期': 3 }
  const colIdx = colMap[column.label] ?? -1
  // 如果右键点击的单元格已在选区内，保持选区不变
  if (rowIdx >= 0 && colIdx >= 0 && !consolCtx.isCellSelected(rowIdx, colIdx)) {
    const value = colIdx === 2 ? row.current_period_amount : colIdx === 3 ? row.prior_period_amount : row.row_name
    consolCtx.selectCell(rowIdx, colIdx, value, false)
    drillDownCell.itemName = row.row_name || ''
    drillDownCell.colName = column.label || ''
    drillDownCell.totalValue = Number(value) || null
  }
  consolCtx.openContextMenu(event, drillDownCell.itemName || row.row_name, row)
}

function onConsolCtxCopy() {
  consolCtx.closeContextMenu()
  consolCtx.copySelectedValues()
  ElMessage.success('已复制')
}

function onConsolCtxDrillDown() {
  consolCtx.closeContextMenu()
  openCellDrillDown()
}

// ─── 数字溯源：调 lineage 端点展示 upstream/downstream ───
const consolTraceDialogVisible = ref(false)
const consolTraceLoading = ref(false)
const consolTraceResult = ref<{ upstream: any[]; downstream: any[] } | null>(null)

async function onConsolCtxCellTrace() {
  consolCtx.closeContextMenu()
  const row = consolCtx.contextMenu.rowData as any
  const objectType = row?.row_code ? 'report_row' : row?.standard_account_code ? 'tb_row' : null
  const objectId = row?.row_code || row?.standard_account_code
  if (!objectType || !objectId) {
    ElMessage.info('请在数据行上右键')
    return
  }
  consolTraceDialogVisible.value = true
  consolTraceLoading.value = true
  consolTraceResult.value = null
  try {
    const data: any = await api.get(
      `/api/projects/${projectId.value}/lineage`,
      { params: { object_type: objectType, object_id: objectId, direction: 'both' } },
    )
    const upstream = data?.upstream || []
    const downstream = data?.downstream || []
    consolTraceResult.value = { upstream, downstream }
    if (!upstream.length && !downstream.length) {
      consolTraceDialogVisible.value = false
      ElMessage.info('该数字暂无溯源信息')
    }
  } catch (e: any) {
    consolTraceDialogVisible.value = false
    handleApiError(e, '数字溯源')
  } finally {
    consolTraceLoading.value = false
  }
}

function onConsolTraceLocate(node: any) {
  consolTraceDialogVisible.value = false
  if (node.wp_code) {
    eventBus.emit('workpaper:locate-cell', {
      wpId: node.wp_code,
      sheetName: node.sheet_name || undefined,
      cellRef: node.cell_ref || '',
    })
  }
}

function onConsolCtxFormula() {
  consolCtx.closeContextMenu()
  onOpenFormula()
}

function onConsolCtxSum() {
  consolCtx.closeContextMenu()
  const sum = consolCtx.sumSelectedValues()
  ElMessage.info(`选中 ${consolCtx.selectedCells.value.length} 格，合计：${fmtAmt(sum)}`)
}

function onConsolCtxCompare() {
  consolCtx.closeContextMenu()
  if (consolCtx.selectedCells.value.length < 2) return
  const vals = consolCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  ElMessage.info(`差异：${fmtAmt(diff)}`)
}

async function loadConsolReport(forceRefresh = false) {
  const cacheKey = reportCacheKey()
  // 优先读缓存
  if (!forceRefresh && reportCache.has(cacheKey)) {
    consolReportRows.value = reportCache.get(cacheKey)!
    return
  }
  // §七 请求上下文保护：快照当前上下文与序号，响应提交前校验（P9）
  const ticket = reportRequestGuard.startRequest()
  consolReportLoading.value = true
  try {
    const nodeKey = currentEntityNodeKey.value
    const rows = await api.get(
      P_consol.reports.list(projectId.value, effectiveEntityYear()),
      { params: { report_type: consolReportType.value, node_key: nodeKey } },
    )
    // 响应到达：上下文或序号已变则丢弃（切换节点后旧请求先返回的场景）
    if (reportRequestGuard.isStale(ticket)) return
    const result = Array.isArray(rows) ? rows : []
    consolReportRows.value = result
    reportCache.set(cacheKey, result)
    consolComments.loadComments(`report_${consolReportType.value}`)
  } catch (err: any) {
    // 过期请求的错误也丢弃，不清空当前节点数据
    if (reportRequestGuard.isStale(ticket)) return
    if (err?.response?.status === 404) {
      consolReportRows.value = []
    } else {
      consolReportRows.value = []
    }
  }
  finally { consolReportLoading.value = false }
}

async function loadConsolMappingPreset() {
  consolMappingLoading.value = true
  try {
    const scope = 'consolidated'
    const data = await api.get(P_rm.preset(projectId.value), {
      params: { report_type: consolReportType.value, scope },
      validateStatus: (s: number) => s < 600,
    })
    const rules = Array.isArray(data) ? data : (data ?? [])
    // 转换字段名适配前端表格
    consolMappingRules.value = rules.map((r: any) => ({
      source_code: r.soe_row_code ?? r.source_code ?? '',
      source_name: r.soe_row_name ?? r.source_name ?? '',
      target_code: r.listed_row_code ?? r.target_code ?? '',
      target_name: r.listed_row_name ?? r.target_name ?? '',
    }))
    if (!consolMappingRules.value.length) {
      ElMessage.info('当前报表类型暂无预设映射规则')
    } else {
      ElMessage.success(`已加载 ${consolMappingRules.value.length} 条预设规则`)
    }
  } catch { consolMappingRules.value = [] }
  finally { consolMappingLoading.value = false }
}

async function applyConsolConversion() {
  consolMappingLoading.value = true
  try {
    // 切换模板类型
    const newType = consolReportTemplateType.value === 'soe' ? 'listed' : 'soe'
    consolReportTemplateType.value = newType
    projectInfo.standard = newType as 'soe' | 'listed'
    consolNoteTemplateType.value = newType
    await loadConsolReport()
    showConsolConversion.value = false
    ElMessage.success('已切换为' + (newType === 'soe' ? '国企版' : '上市版'))
    // 通知其他组件
    eventBus.emit('standard-change', { standard: newType as 'soe' | 'listed' })
  } catch (e: any) {
    handleApiError(e, '切换合并映射')
  } finally { consolMappingLoading.value = false }
}

async function exportConsolReport() {
  const reportType = consolReportType.value
  const exportYear = effectiveEntityYear()
  const mainReportTypes = ['balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement']
  try {
    if (mainReportTypes.includes(reportType)) {
      await downloadFile(reportPaths.exportAllExcel(projectId.value), {
        method: 'post',
        data: {
          year: exportYear,
          mode: 'audited',
          report_types: [reportType],
          include_prior_year: true,
        },
        fileName: `合并报表_${reportType}_${exportYear}.xlsx`,
      })
      return
    }

    // 项目级整包导出器目前只接受四张主表；两张特殊表走已有单表 GET 导出。
    await downloadFile(reportPaths.exportExcel(projectId.value, exportYear, reportType), {
      fileName: `合并报表_${reportType}_${exportYear}.xlsx`,
    })
  } catch (e) {
    handleApiError(e, '导出合并报表')
  }
}

function _getConsolReportConfigData(): Record<string, any> {
  return { rows: consolReportRows.value, template_type: consolReportTemplateType.value, report_type: consolReportType.value }
}

function _onConsolReportTemplateApplied(_data: Record<string, any>) {
  loadConsolReport()
}

// ─── Tab 6: 合并附注 ─────────────────────────────────────────────────────────
const consolNoteTemplateType = ref('soe')
const consolNoteLoading = ref(false)
const consolNoteTree = ref<any[]>([])
const showConsolNoteConversion = ref(false)

// ─── 附注全审（delegated to ConsolNoteTab, kept for TB audit reuse） ─────────
const noteAuditResults = ref<any[]>([])
const noteAuditSummary = reactive({ totalSections: 0, totalChecks: 0, passCount: 0, errorCount: 0, warnCount: 0 })
const showNoteAuditDialog = ref(false)
const _noteAuditLoading = ref(false)

function _auditRowClass({ row }: { row: any }) {
  if (row.level === 'error') return 'gt-audit-row-error'
  if (row.level === 'warn') return 'gt-audit-row-warn'
  return ''
}

async function loadConsolNoteTree(forceRefresh = false) {
  const cacheKey = noteCacheKey()
  if (!forceRefresh && noteCache.has(cacheKey)) {
    consolNoteTree.value = noteCache.get(cacheKey)!
    return
  }
  consolNoteLoading.value = true
  try {
    const data = await api.get(P_cn.list(consolNoteTemplateType.value), {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data ?? [])
    if (!Array.isArray(groups) || !groups.length) {
      consolNoteTree.value = []
      noteCache.set(cacheKey, [])
      return
    }
    const tree = groups.map((g: any) => ({
      label: `${g.parent_seq}. ${g.label}`,
      parent_seq: g.parent_seq,
      table_count: g.table_count,
      children: (g.children || []).map((c: any) => ({
        section_id: c.section_id,
        label: c.title,
        title: c.title,
        seq: c.seq,
      })),
    }))
    consolNoteTree.value = tree
    noteCache.set(cacheKey, tree)
  } catch { consolNoteTree.value = [] }
  finally { consolNoteLoading.value = false }
}

function _switchNoteTemplate() {
  consolNoteTemplateType.value = consolNoteTemplateType.value === 'soe' ? 'listed' : 'soe'
  loadConsolNoteTree()
  showConsolNoteConversion.value = false
  ElMessage.success('已切换为' + (consolNoteTemplateType.value === 'soe' ? '国企版' : '上市版'))
}

function _getConsolNoteConfigData(): Record<string, any> {
  return { template_type: consolNoteTemplateType.value }
}

function _onConsolNoteTemplateApplied(_data: Record<string, any>) {
  loadConsolNoteTree()
}

// Delegate note node click to child component
function onNoteNodeClick(data: any) {
  consolNoteTabRef.value?.onNoteNodeClick(data)
}

// noteTreeSearch/noteTreeRef kept for compatibility but search moved to ConsolCatalog


// 监听中间栏树形节点选择事件
function onConsolTreeSelect(data: ConsolTreeSelectPayload) {
  if (!data) return
  const node = findNodeByKey(groupTree.value[0], data.nodeKey)
  if (data.isReport && data.reportType) {
    // 点击了报表类型节点 → 切换到合并报表 tab 并加载对应报表
    activeTab.value = 'consol_report'
    consolReportType.value = data.reportType
    loadConsolReport()
  } else if (data.kind === 'elim') {
    // 差额节点（合并差额 / 母分差额）→ 打开差额分录面板（需求 9.3）
    if (node) {
      selectedNode.value = node
      openElimPanel(node)
    }
  } else if (data.companyCode) {
    // 点击了企业节点 → 选中该节点，刷新报表/附注
    if (node) selectedNode.value = node
    currentConsolEntity.value = {
      code: data.companyCode,
      name: data.label || '',
      nodeKey: data.nodeKey || node?.node_key || `${data.companyCode}:unknown`,
    }
    // 如果指定了切换 tab
    if (data.switchTab) {
      activeTab.value = data.switchTab
    }
    // 刷新当前 tab 数据
    if (activeTab.value === 'consol_report') reloadConsolReportView()
    else if (activeTab.value === 'consol_tb') consolTbTabRef.value?.load()
    else if (activeTab.value === 'consol_note') {
      // 企业节点切换：重读当前章节，不只刷新目录
      const section = consolNoteTabRef.value?.selectedNoteSection
      if (section?.section_id) {
        consolNoteTabRef.value?.onNoteNodeClick({ section_id: section.section_id, title: section.title })
      } else {
        loadConsolNoteTree()
      }
    }
  }
}

// route.query.tab 别名 → 真实 el-tab-pane name（A3 中控台 route: chip 跳转用）
const TAB_ALIAS: Record<string, string> = {
  scope: 'structure',
  structure: 'structure',
  eliminations: 'worksheets',
  'internal-trade': 'worksheets',
  worksheets: 'worksheets',
  trial: 'consol_tb',
  consol_tb: 'consol_tb',
  report: 'consol_report',
  consol_report: 'consol_report',
  notes: 'consol_note',
  consol_note: 'consol_note',
}

function syncTabFromQuery() {
  const q = route.query.tab
  if (typeof q === 'string' && TAB_ALIAS[q]) {
    activeTab.value = TAB_ALIAS[q]
  }
}

onMounted(async () => {
  syncTabFromQuery()
  updateConsolEquityTableHeight()
  window.addEventListener('resize', updateConsolEquityTableHeight)
  await loadProjectInfo()
  // 默认合并主体为项目本身（集团层面）；树加载后用后端根节点稳定身份替换占位键。
  currentConsolEntity.value = { code: '', name: projectInfo.clientName || '', nodeKey: ROOT_CONSOL_NODE_KEY }
  await loadGroupTree()
  bindConsolPushEvents()
  await loadConsolPushStatus()
  // P3 防误用标记：获取模块开发状态
  try {
    const status = await api.get(`/api/consolidation/${projectId.value}/module-status`)
    // dev_mode banner removed — module is production-ready
  } catch {
    // 静默忽略（端点不可用时不影响页面）
  }
  eventBus.on('consol-tree-select', onConsolTreeSelect)
  eventBus.on('consol-catalog-select', onConsolCatalogSelect)
  eventBus.on('consol-refresh-entity', onConsolRefreshEntity)
  eventBus.on('consol-open-scope-confirm' as any, () => { showScopeConfirmDialog.value = true })
  // 自动建树 5.3：监听 CONSOL_SCOPE_CHANGED（SSE）→ 自动刷新企业树（ADR-CONSOL-303）
  consolEvents.onAnyEvent(onConsolScopeChanged)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateConsolEquityTableHeight)
  eventBus.off('consol-tree-select', onConsolTreeSelect)
  eventBus.off('consol-catalog-select', onConsolCatalogSelect)
  eventBus.off('consol-refresh-entity', onConsolRefreshEntity)
  eventBus.off('consol-open-scope-confirm' as any)
  refreshTracking.stop()
  stopConsolPushEvents()
})

// 监听树形节点刷新事件
function onConsolRefreshEntity(detail: ConsolRefreshEntityPayload) {
  if (!detail) return
  const { companyCode, companyName, nodeKey, types } = detail

  // 切换到指定树节点；nodeKey 是同企业不同角色之间的唯一身份。
  currentConsolEntity.value = { code: companyCode, name: companyName, nodeKey }
  const entityNode = findNodeByKey(groupTree.value[0], nodeKey)
  if (entityNode) selectedNode.value = entityNode

  // 清除该节点的缓存
  clearEntityCache(nodeKey, types)

  // 按选择的类型强制刷新
  const hasReports = types.includes('all_reports') || types.some(t =>
    ['balance_sheet','income_statement','cash_flow_statement','equity_statement','cash_flow_supplement','impairment_provision'].includes(t)
  )
  if (hasReports) {
    const specificReport = types.find(t => t !== 'all_reports' && t !== 'notes' && t !== 'worksheet' &&
      ['balance_sheet','income_statement','cash_flow_statement','equity_statement','cash_flow_supplement','impairment_provision'].includes(t))
    if (specificReport) consolReportType.value = specificReport
    loadConsolReport(true)
  }
  if (types.includes('notes')) {
    loadConsolNoteTree(true)
    // 同时重读当前章节（不只刷新目录）
    const section = consolNoteTabRef.value?.selectedNoteSection
    if (section?.section_id) {
      consolNoteTabRef.value?.onNoteNodeClick({ section_id: section.section_id, title: section.title })
    }
  }
}

// 监听四栏 catalog 选择事件
async function onConsolCatalogSelect(data: ConsolCatalogSelectPayload) {
  if (!data) return
  if (data.type === 'report' && data.reportType) {
    activeTab.value = 'consol_report'
    consolReportType.value = data.reportType
    if (data.standard) consolReportTemplateType.value = data.standard
    loadConsolReport()
  } else if (data.type === 'note' && data.sectionId) {
    activeTab.value = 'consol_note'
    if (data.standard) consolNoteTemplateType.value = data.standard
    // 直接加载该章节详情
    onNoteNodeClick({ section_id: data.sectionId, title: data.title })
  } else if (data.type === 'refresh-all') {
    // 全部刷新：报表+目录+当前章节
    reloadConsolReportView()
    await loadConsolNoteTree()
    const section = consolNoteTabRef.value?.selectedNoteSection
    if (section?.section_id) {
      consolNoteTabRef.value?.onNoteNodeClick({ section_id: section.section_id, title: section.title })
    }
  } else if (data.type === 'refresh-report' && data.reportType) {
    // 刷新单个报表
    consolReportType.value = data.reportType
    activeTab.value = 'consol_report'
    reloadConsolReportView()
  } else if (data.type === 'refresh-note' && data.sectionId) {
    // 刷新单个附注：加载目录后重读指定章节
    activeTab.value = 'consol_note'
    await loadConsolNoteTree()
    onNoteNodeClick({ section_id: data.sectionId, title: data.title })
  }
}

watch(activeTab, (tab) => {
  // 差额表读时计算：每次进入都按最新分录与子企业数据重读
  if (tab === 'consol_report') reloadConsolReportView()
  if (tab === 'consol_note' && !consolNoteTree.value.length) loadConsolNoteTree()
  // 试算页读时计算：每次进入都按最新分录与子企业数据重读
  if (tab === 'consol_tb') loadConsolTb()
})

// 同一路由组件切换项目/企业树年度时重绑项目级 raw SSE，并重读权威推送状态
watch(() => [projectId.value, effectiveConsolYear()] as const, ([pid, y], old) => {
  if (!pid || !y || (old && old[0] === pid && old[1] === y)) return
  bindConsolPushEvents()
  loadConsolPushStatus()
})

// 在合并页内通过 route: chip 二次跳转（query.tab 变化但组件不重挂载）时同步 Tab
watch(() => route.query.tab, syncTabFromQuery)
</script>

<style>
/* 全局：确保 MessageBox 和 Select 下拉在所有弹窗之上 */
.el-overlay.is-message-box { z-index: 10010 !important; }
.el-select__popper { z-index: 10005 !important; }
</style>

<style scoped>
.gt-consol { padding: 12px; overflow: hidden; }
.gt-consol-tabs { margin-top: 8px; }

.gt-tab-content { padding: var(--gt-space-3) 0; }

/* 共享工具栏样式（试算表/报表/集团架构通用） */
.gt-ctb-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; margin-bottom: 8px;
  background: var(--gt-color-bg-elevated, #faf9fd);
  border: 1px solid var(--gt-color-border-light, #f0f0f5);
  border-radius: var(--gt-radius-md, 8px);
}
.gt-ctb-toolbar-left, .gt-ctb-toolbar-right {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.gt-ctb-sep {
  display: inline-block; width: 1px; height: 20px;
  background: var(--gt-color-border, #e5e5ea); margin: 0 4px;
}

.gt-structure-layout { display: flex; gap: 24px; }
.gt-structure-tree { flex: 1; min-width: 300px; }
.gt-structure-card { width: 320px; flex-shrink: 0; }
.gt-tree-node { display: flex; align-items: center; }
.gt-consol-diag-list { margin: 4px 0 0; padding-left: 18px; font-size: var(--gt-font-size-xs); line-height: 1.7; }
.gt-consol-diag--info { color: var(--gt-color-text-secondary); }

/* ── 组织结构图 ── */
.org-chart-wrapper {
  overflow: auto; padding: 20px; min-height: 300px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f3f8 100%);
  border: 1px solid var(--gt-color-border-purple); border-radius: 10px;
  transition: transform 0.2s ease;
}
/* 内容宽于容器时按内容撑宽（向右溢出可滚动）；居中只在内容窄于容器时生效，否则左侧节点会溢出到滚动不到的负区 */
.org-chart { display: flex; justify-content: center; width: max-content; min-width: 100%; }
.org-detail-card {
  position: fixed; bottom: 20px; right: 20px; z-index: 100;
  background: var(--gt-color-bg-white); border: 1px solid var(--gt-color-border-purple); border-radius: 10px;
  padding: 14px 18px; box-shadow: 0 4px 20px rgba(75,45,119,0.12);
  min-width: 200px; max-width: 280px;
}

/* ── 合并报表左右布局 ── */
.gt-report-layout { display: flex; gap: 0; height: calc(100vh - 200px); margin: -12px 0; }
.gt-report-nav {
  width: 240px; flex-shrink: 0; background: var(--gt-color-bg); border-right: 1px solid var(--gt-color-border-purple);
  display: flex; flex-direction: column; overflow: hidden;
}
.gt-report-nav-header {
  padding: 10px 12px; border-bottom: 1px solid var(--gt-color-border-purple); display: flex;
  justify-content: space-between; align-items: center; flex-shrink: 0;
}
.gt-report-tree { flex: 1; overflow-y: auto; padding: 6px; }
.gt-report-tree-node { display: flex; align-items: center; font-size: var(--gt-font-size-xs); }
.gt-report-tree-node--diff { color: var(--gt-color-wheat); font-style: italic; }

/* 报表类型切换栏（底部） */
.gt-report-type-bar {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 8px; border-top: 1px solid var(--gt-color-border-purple);
  background: var(--gt-color-primary-bg); flex-shrink: 0;
}
.gt-report-type-item {
  display: flex; align-items: center; gap: 3px; padding: 4px 8px; border-radius: 4px;
  cursor: pointer; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); transition: all 0.15s;
}
.gt-report-type-item:hover { background: rgba(75,45,119,0.06); }
.gt-report-type-item--active { background: var(--gt-color-primary); color: var(--gt-color-text-inverse); }

.gt-report-nav-list { flex: 1; overflow-y: auto; padding: 8px; }
.gt-report-content { flex: 1; min-width: 0; padding: 12px 16px; overflow: auto; }

/* ── 合并报表/附注内容区工具栏 ── */
.gt-report-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; gap: 8px;
}
.gt-report-title {
  margin: 0; font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gt-report-actions { display: flex; gap: 6px; flex-shrink: 0; }

/* 当前合并主体标识 */
.gt-entity-badge {
  display: inline-block; padding: 2px 8px; margin-right: 6px;
  background: linear-gradient(135deg, #4b2d77, #7c5caa); color: #fff;
  border-radius: 4px; font-size: var(--gt-font-size-xs); font-weight: 600; white-space: nowrap;
  vertical-align: middle;
}

/* 报表类型标签切换（紧凑） */
.gt-report-type-tabs {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; border-bottom: 2px solid var(--gt-color-border-purple);
}
.gt-report-type-tabs-left {
  display: flex; gap: 0;
}
.gt-report-type-tag {
  padding: 8px 20px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -2px;
  transition: all 0.15s; white-space: nowrap; user-select: none;
  letter-spacing: 0.5px;
}
.gt-report-type-tag:hover { color: #4b2d77; background: rgba(75,45,119,0.04); border-radius: 6px 6px 0 0; }
.gt-report-type-tag--active {
  color: var(--gt-color-primary); font-weight: 600;
  border-bottom-color: var(--gt-color-primary);
  background: rgba(75,45,119,0.03); border-radius: 6px 6px 0 0;
}

/* ── 合并报表表格紧凑样式 ── */
.gt-consol-report-table :deep(.el-table__row td) {
  height: 32px; line-height: 1.3;
}
.gt-consol-report-table :deep(.el-table__header th) {
  height: 34px;
}

/* ── 合并报表 el-table 行样式 ── */
:deep(.gt-cm-total-row td) { font-weight: 700; background: var(--gt-color-primary-bg) !important; }
:deep(.gt-cm-category td) { font-weight: 600; color: var(--gt-color-primary); }
.gt-tb-editable { cursor: text; border-bottom: 1px dashed var(--gt-color-border, #e5e5ea); padding: 2px 6px; border-radius: 2px; display: inline-block; min-width: 70px; text-align: right; }
.gt-tb-editable:hover { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-tb-audited { font-weight: 700; color: #4b2d77; background: rgba(75,45,119,0.06); }

/* 审核结果行样式 */
:deep(.gt-audit-row-error td) { background: var(--gt-bg-danger) !important; }
:deep(.gt-audit-row-warn td) { background: var(--gt-bg-warning) !important; }


</style>
