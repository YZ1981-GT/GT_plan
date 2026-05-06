<template>
  <div class="gt-consol gt-fade-in">
    <!-- 横幅：单位名称 + 年度 + 准则类型 -->
    <GtPageHeader title="合并报表" @back="$router.push('/consolidation')">
      <GtInfoBar
        :show-year="true"
        :show-template="true"
        :year-value="projectInfo.year"
        :template-value="projectInfo.standard"
        :badges="[{ label: '单位', value: displayPrefs.unitSuffix }]"
        @year-change="(y: number) => { projectInfo.year = y; onYearChange() }"
        @template-change="(s: string) => { projectInfo.standard = s; onStandardChange() }"
      />
      <template #actions>
        <GtToolbar
          :show-formula="true"
          @formula="onOpenFormula"
        >
          <template #left>
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
            <el-button size="small" @click="showConsolConversion = true">🔄 转换规则</el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <el-tabs v-model="activeTab" class="gt-consol-tabs">
      <!-- Tab 0: 合并工作底稿 -->
      <el-tab-pane label="合并工作底稿" name="worksheets">
        <ConsolWorksheetTabs />
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
              <span style="font-size:12px;color:#666">{{ orgNodeCount }} 个节点 · 最大 {{ orgMaxDepth }} 层</span>
            </div>
          </div>

          <!-- 组织结构图模式 -->
          <div v-if="orgViewMode === 'chart'" class="org-chart-wrapper" :style="{ transform: `scale(${orgZoom})`, transformOrigin: 'top left' }">
            <div v-if="groupTree.length" class="org-chart">
              <org-node :node="groupTree[0]" :depth="0" @select="onTreeNodeClick" :selected-code="selectedNode?.company_code" />
            </div>
            <el-empty v-else description="暂无集团架构数据，请先配置合并范围" />
          </div>

          <!-- 树形列表模式 -->
          <div v-else class="gt-structure-layout">
            <div class="gt-structure-tree">
              <el-tree :data="groupTree" :props="{ label: 'company_name', children: 'children' }"
                default-expand-all node-key="company_code" highlight-current @node-click="onTreeNodeClick">
                <template #default="{ data }">
                  <span class="gt-tree-node">
                    <span>{{ data.company_name || data.name }}</span>
                    <el-tag v-if="data.shareholding" size="small" type="info" style="margin-left:8px">{{ data.shareholding }}%</el-tag>
                  </span>
                </template>
              </el-tree>
              <el-empty v-if="!groupTree.length" description="暂无集团架构数据" />
            </div>
            <div v-if="selectedNode" class="gt-structure-card">
              <el-descriptions :column="1" border size="small" title="节点信息">
                <el-descriptions-item label="企业名称">{{ selectedNode.company_name }}</el-descriptions-item>
                <el-descriptions-item label="企业代码">{{ selectedNode.company_code }}</el-descriptions-item>
                <el-descriptions-item label="持股比例" v-if="selectedNode.shareholding">{{ selectedNode.shareholding }}%</el-descriptions-item>
              </el-descriptions>
              <el-button type="primary" size="small" style="margin-top:12px" @click="goToProject(selectedNode)">查看合并</el-button>
            </div>
          </div>

          <!-- 选中节点信息卡（组织图模式） -->
          <div v-if="orgViewMode === 'chart' && selectedNode" class="org-detail-card">
            <h4 style="margin:0 0 8px;color:#4b2d77">{{ selectedNode.company_name }}</h4>
            <p style="font-size:12px;color:#666;margin:4px 0">代码：{{ selectedNode.company_code || '—' }}</p>
            <p v-if="selectedNode.shareholding" style="font-size:12px;color:#666;margin:4px 0">持股：{{ selectedNode.shareholding }}%</p>
            <p v-if="selectedNode.children?.length" style="font-size:12px;color:#999;margin:4px 0">下级：{{ selectedNode.children.length }} 家</p>
            <el-button type="primary" size="small" style="margin-top:8px" @click="goToProject(selectedNode)">查看合并</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab: 试算平衡表（独立组件） -->
      <el-tab-pane label="试算平衡表" name="consol_tb">
        <ConsolTrialBalanceTab
          ref="consolTbTabRef"
          :project-id="projectId"
          :year="year"
          :template-type="consolReportTemplateType"
          :entity-code="currentConsolEntity.code || ''"
          @audit="onTbAudit"
          @generate-report-done="onTbGenerateReportDone"
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
                @click="consolReportType = item.key; loadConsolReport()">
                {{ item.label }}
              </span>
            </div>
          </div>
          <!-- 工具栏 -->
          <div class="gt-ctb-toolbar" style="margin-top:8px">
            <div class="gt-ctb-toolbar-left">
              <span style="font-size:12px;color:#666">{{ consolReportRows.length }} 行 · {{ currentReportLabel }}</span>
            </div>
            <div class="gt-ctb-toolbar-right">
              <el-button size="small" type="primary" @click="loadConsolReport(true)" :loading="consolReportLoading">🔄 刷新</el-button>
              <el-button size="small" @click="exportConsolReport">📤 导出</el-button>
            </div>
          </div>
          <!-- 权益变动表 — 矩阵视图 -->
          <div v-if="consolReportType === 'equity_statement' && consolReportRows.length" class="gt-consol-matrix" v-loading="consolReportLoading">
            <div class="gt-consol-matrix-scroll">
              <table class="gt-consol-matrix-table">
                <thead>
                  <tr>
                    <th rowspan="4" class="gt-cm-th-project">项目</th>
                    <th :colspan="consolEqCols.length">本年金额</th>
                    <th :colspan="consolEqCols.length" class="gt-cm-th-prior">上年金额</th>
                  </tr>
                  <tr>
                    <th :colspan="consolEqCols.length - 2">归属于母公司所有者权益</th>
                    <th rowspan="3">少数股东<br/>权益</th>
                    <th rowspan="3" class="gt-cm-th-total">所有者<br/>权益合计</th>
                    <th :colspan="consolEqCols.length - 2">归属于母公司所有者权益</th>
                    <th rowspan="3">少数股东<br/>权益</th>
                    <th rowspan="3" class="gt-cm-th-total">所有者<br/>权益合计</th>
                  </tr>
                  <tr>
                    <th rowspan="2">实收资本</th>
                    <th colspan="3">其他权益工具</th>
                    <th rowspan="2">资本公积</th>
                    <th rowspan="2">减：库存股</th>
                    <th rowspan="2">其他综合收益</th>
                    <th rowspan="2">专项储备</th>
                    <th rowspan="2">盈余公积</th>
                    <th rowspan="2">一般风险准备</th>
                    <th rowspan="2">未分配利润</th>
                    <th rowspan="2" class="gt-cm-th-total">小计</th>
                    <th rowspan="2">实收资本</th>
                    <th colspan="3">其他权益工具</th>
                    <th rowspan="2">资本公积</th>
                    <th rowspan="2">减：库存股</th>
                    <th rowspan="2">其他综合收益</th>
                    <th rowspan="2">专项储备</th>
                    <th rowspan="2">盈余公积</th>
                    <th rowspan="2">一般风险准备</th>
                    <th rowspan="2">未分配利润</th>
                    <th rowspan="2" class="gt-cm-th-total">小计</th>
                  </tr>
                  <tr>
                    <th>优先股</th><th>永续债</th><th>其他</th>
                    <th>优先股</th><th>永续债</th><th>其他</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in consolReportRows" :key="row.row_code"
                      :class="{ 'gt-cm-total-row': row.is_total_row, 'gt-cm-category': row.indent_level === 0 && !row.is_total_row }">
                    <td class="gt-cm-td-project" :style="{ paddingLeft: (row.indent_level || 0) * 14 + 'px' }">{{ row.row_name }}</td>
                    <td v-for="col in consolEqCols" :key="'cv-' + col" class="gt-cm-td-amt">{{ fmtAmt(row['current_' + col]) }}</td>
                    <td v-for="col in consolEqCols" :key="'pv-' + col" class="gt-cm-td-amt gt-cm-td-prior">{{ fmtAmt(row['prior_' + col]) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 资产减值准备表 — 矩阵视图 -->
          <div v-else-if="consolReportType === 'impairment_provision' && consolReportRows.length" class="gt-consol-matrix" v-loading="consolReportLoading">
            <div class="gt-consol-matrix-scroll">
              <table class="gt-consol-matrix-table">
                <thead>
                  <tr>
                    <th rowspan="2" class="gt-cm-th-project">项目</th>
                    <th rowspan="2">年初账面余额</th>
                    <th colspan="4">本期增加额</th>
                    <th colspan="5">本期减少额</th>
                    <th rowspan="2" class="gt-cm-th-total">期末账面余额</th>
                  </tr>
                  <tr>
                    <th>本期计提额</th><th>合并增加额</th><th>其他原因增加额</th><th class="gt-cm-th-total">合计</th>
                    <th>转回额</th><th>转销额</th><th>合并减少额</th><th>其他原因减少额</th><th class="gt-cm-th-total">合计</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in consolReportRows" :key="row.row_code"
                      :class="{ 'gt-cm-total-row': row.is_total_row }">
                    <td class="gt-cm-td-project" :style="{ paddingLeft: (row.indent_level || 0) * 14 + 'px' }">{{ row.row_name }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.opening_balance) }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.provision) }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.merge_add) }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.other_add) }}</td>
                    <td class="gt-cm-td-amt" style="font-weight:600">{{ fmtAmt(row.add_total) }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.reversal) }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.writeoff) }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.merge_dec) }}</td>
                    <td class="gt-cm-td-amt">{{ fmtAmt(row.other_dec) }}</td>
                    <td class="gt-cm-td-amt" style="font-weight:600">{{ fmtAmt(row.dec_total) }}</td>
                    <td class="gt-cm-td-amt" style="font-weight:700">{{ fmtAmt(row.closing_balance) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
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
                <span style="white-space:nowrap">{{ row.row_code }}</span>
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
          :year="projectInfo.year"
          :standard="consolReportTemplateType"
          :current-entity="currentConsolEntity"
          :group-tree="groupTree"
          :consol-note-tree="consolNoteTree"
        />
      </el-tab-pane>
    </el-tabs>


    <!-- 报表转换规则弹窗 -->
    <el-dialog v-model="showConsolConversion" title="国企/上市报表转换规则" width="80%" top="4vh" append-to-body destroy-on-close>
      <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
        <span style="font-size:12px;color:#999">{{ consolReportTemplateType === 'soe' ? '国企版 → 上市版' : '上市版 → 国企版' }}</span>
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
      <p style="font-size:13px;color:#666;margin-bottom:16px">
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
        <span style="font-size:14px;font-weight:700;color:#4b2d77">合计：{{ fmtAmt(drillDownCell.totalValue) }}</span>
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
              <span :style="{ color: row.amount < 0 ? '#f56c6c' : '' }">{{ fmtAmt(row.amount) }}</span>
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
              <span :style="{ color: row.amount < 0 ? '#f56c6c' : '' }">{{ fmtAmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="ratio" label="占比" width="90" align="right">
            <template #default="{ row }">{{ row.ratio }}%</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- 转置视图：列变行 -->
      <template v-else>
        <div class="gt-consol-matrix" style="max-height:55vh">
          <div class="gt-consol-matrix-scroll">
            <table class="gt-consol-matrix-table">
              <thead>
                <tr>
                  <th class="gt-cm-th-project">字段</th>
                  <th v-for="(row, ri) in currentDrillDownRows" :key="ri">{{ row.company_name }}</th>
                  <th class="gt-cm-th-total">合计</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="gt-cm-td-project">企业代码</td>
                  <td v-for="(row, ri) in currentDrillDownRows" :key="'code'+ri" class="gt-cm-td-amt">{{ row.company_code }}</td>
                  <td class="gt-cm-td-amt">—</td>
                </tr>
                <tr v-if="drillDownLevel === 'leaf'">
                  <td class="gt-cm-td-project">上级单位</td>
                  <td v-for="(row, ri) in currentDrillDownRows" :key="'parent'+ri" class="gt-cm-td-amt">{{ row.parent_name || '—' }}</td>
                  <td class="gt-cm-td-amt">—</td>
                </tr>
                <tr>
                  <td class="gt-cm-td-project" style="font-weight:600">金额</td>
                  <td v-for="(row, ri) in currentDrillDownRows" :key="'amt'+ri" class="gt-cm-td-amt" :style="{ color: row.amount < 0 ? '#f56c6c' : '' }">{{ fmtAmt(row.amount) }}</td>
                  <td class="gt-cm-td-amt" style="font-weight:700">{{ fmtAmt(drillDownCell.totalValue) }}</td>
                </tr>
                <tr>
                  <td class="gt-cm-td-project">占比</td>
                  <td v-for="(row, ri) in currentDrillDownRows" :key="'ratio'+ri" class="gt-cm-td-amt">{{ row.ratio }}%</td>
                  <td class="gt-cm-td-amt" style="font-weight:600">100%</td>
                </tr>
                <tr v-if="drillDownLevel === 'direct'">
                  <td class="gt-cm-td-project">数据来源</td>
                  <td v-for="(row, ri) in currentDrillDownRows" :key="'src'+ri" class="gt-cm-td-amt">{{ row.source }}</td>
                  <td class="gt-cm-td-amt">—</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
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
    </CellContextMenu>

    <!-- 选中区域状态栏 -->
    <SelectionBar :stats="consolCtx.selectionStats()" />

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getWorksheetTree,
} from '@/services/consolidationApi'
import { listChildProjects } from '@/services/commonApi'
import { api } from '@/services/apiProxy'
import ConsolWorksheetTabs from '@/components/consolidation/worksheets/ConsolWorksheetTabs.vue'
import ConsolNoteTab from '@/components/consolidation/ConsolNoteTab.vue'
import ConsolTrialBalanceTab from '@/components/consolidation/ConsolTrialBalanceTab.vue'
import OrgNode from '@/components/consolidation/OrgNode.vue'
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

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

// ─── 批注与复核持久化（合并报表/试算表共用） ─────────────────────────────────
const consolComments = useCellComments(() => projectId.value, () => year.value, 'consol_report')

const activeTab = ref('worksheets')
const consolNoteTabRef = ref<InstanceType<typeof ConsolNoteTab> | null>(null)
const consolTbTabRef = ref<InstanceType<typeof ConsolTrialBalanceTab> | null>(null)

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
  // 年度切换后重新加载数据
  loadConsolReport()
}

function onStandardChange() {
  consolReportTemplateType.value = projectInfo.standard
  consolNoteTemplateType.value = projectInfo.standard
  loadConsolReport()
  loadConsolNoteTree()
  // 通知 ConsolCatalog 更新准则
  eventBus.emit('standard-change', { standard: projectInfo.standard })
}

function onOpenFormula() {
  eventBus.emit('open-formula-manager', { nodeKey: 'consolidation' })
}

// ─── 单元格汇总穿透查看 ──────────────────────────────────────────────────────
const showCellDrillDown = ref(false)
const drillDownLoading = ref(false)
const drillDownLevel = ref<'direct' | 'leaf'>('direct')
const drillDownCell = reactive({ itemName: '', colName: '', totalValue: 0 as number | null, sectionId: '', rowIdx: -1, colIdx: -1 })
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

function openCellDrillDown() {
  // 从当前选中的附注表格或报表中获取选中单元格信息
  const noteTab = consolNoteTabRef.value
  const sec = noteTab?.selectedNoteSection
  if (sec && sec.editRows?.length) {
    // 附注模式：提示用户先点击单元格
    // 这里用一个简单的弹窗让用户选择行和列
    showCellDrillDown.value = true
    drillDownCell.sectionId = sec.section_id || ''
    // 如果有选中行，用第一个选中行
    if (noteTab?.noteSelectedRows?.length) {
      const row = noteTab.noteSelectedRows[0]
      drillDownCell.itemName = row[0] || '未选中'
      drillDownCell.colName = sec.headers?.[1] || '期末余额'
      drillDownCell.totalValue = Number(row[1]) || null
      drillDownCell.rowIdx = sec.editRows.indexOf(row)
      drillDownCell.colIdx = 1
    } else {
      drillDownCell.itemName = '请先选中表格中的行'
      drillDownCell.colName = ''
      drillDownCell.totalValue = null
    }
    loadDrillDownData()
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
  if (!drillDownCell.itemName || drillDownCell.itemName.startsWith('请')) {
    drillDownDirectRows.value = []
    drillDownLeafRows.value = []
    return
  }
  drillDownLoading.value = true
  try {
    // 确定当前查看的报表类型和行次
    const reportType = activeTab.value === 'consol_tb' ? consolTbType.value : consolReportType.value
    const rowCode = selectedCells.value.length ? (() => {
      const cell = selectedCells.value[0]
      // 从试算表或报表行中提取 row_code
      const sourceRows = activeTab.value === 'consol_tb' ? consolTbRows.value : consolReportRows.value
      return sourceRows[cell.row]?.row_code || ''
    })() : ''
    const colField = drillDownCell.colName?.includes('上期') ? 'prior_period_amount' : 'current_period_amount'

    // 调用后端真实穿透 API
    const data = await api.post('/api/report-config/drill-down', {
      project_id: projectId.value,
      year: year.value,
      report_type: reportType,
      row_code: rowCode,
      col_field: colField,
    }, { validateStatus: (s: number) => s < 600 })

    const result = data
    if (result?.rows?.length) {
      drillDownDirectRows.value = result.rows.map((r: any) => ({
        company_name: r.company_name,
        company_code: r.company_code,
        amount: r.amount,
        ratio: r.pct || 0,
        source: r.source,
        parent_name: r.parent_name || '母公司',
      }))
      // 末级明细：无下级的企业
      drillDownLeafRows.value = result.rows.filter((r: any) => {
        return !result.rows.some((c: any) => c.parent_name === r.company_name)
      }).map((r: any) => ({
        company_name: r.company_name,
        company_code: r.company_code,
        amount: r.amount,
        ratio: r.pct || 0,
        source: r.source,
        parent_name: r.parent_name || '母公司',
      }))
    } else {
      // 降级：从基本信息表按持股比例估算
      const { loadAllWorksheetData } = await import('@/services/consolWorksheetDataApi')
      const saved = await loadAllWorksheetData(projectId.value, year.value)
      const infoRows = saved?.info?.rows || []
      const companies = Array.isArray(infoRows) ? infoRows.filter((r: any) => r.company_name) : []
      const totalVal = Number(drillDownCell.totalValue) || 0
      const directRows: any[] = []
      for (const comp of companies) {
        const ratio = comp.non_common_ratio || comp.common_ratio || comp.no_consol_ratio || 0
        const amount = totalVal ? Math.round(totalVal * (ratio / 100) * 100) / 100 : null
        directRows.push({
          company_name: comp.company_name, company_code: comp.company_code,
          amount, ratio: totalVal && amount ? Math.round(((amount / totalVal) * 100) * 100) / 100 : 0,
          source: '按持股比例估算', parent_name: comp.indirect_holder || '母公司',
        })
      }
      drillDownDirectRows.value = directRows
      drillDownLeafRows.value = directRows.filter(r => !companies.some((c: any) => c.indirect_holder === r.company_name))
    }
  } catch { drillDownDirectRows.value = []; drillDownLeafRows.value = [] }
  finally { drillDownLoading.value = false }
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
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const isLeaf = drillDownLevel.value === 'leaf'
  const headers = isLeaf
    ? ['序号', '末级企业', '企业代码', '上级单位', '金额', '占比']
    : ['序号', '企业名称', '企业代码', '金额', '占比', '数据来源']
  const dataRows = rows.map((r: any, i: number) => isLeaf
    ? [i + 1, r.company_name, r.company_code, r.parent_name, r.amount, `${r.ratio}%`]
    : [i + 1, r.company_name, r.company_code, r.amount, `${r.ratio}%`, r.source]
  )
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map(() => ({ wch: 16 }))
  XLSX.utils.book_append_sheet(wb, ws, '汇总穿透')
  XLSX.writeFile(wb, `汇总穿透_${drillDownCell.itemName}.xlsx`)
  ElMessage.success('已导出')
}

async function loadProjectInfo() {
  try {
    const data = await api.get(`/api/projects/${projectId.value}`, { validateStatus: (s: number) => s < 600 })
    const p = data
    if (p) {
      projectInfo.clientName = p.client_name || p.name || ''
      projectInfo.year = p.audit_year || year.value
      projectInfo.standard = (p.applicable_standard || '').includes('listed') ? 'listed' : 'soe'
    }
  } catch { /* ignore */ }
}

// ─── Tab 1: 集团架构 ─────────────────────────────────────────────────────────
const groupTree = ref<any[]>([])
const selectedNode = ref<any>(null)
const orgViewMode = ref<'chart' | 'tree'>('chart')
const orgZoom = ref(0.85)

// 统计节点数和最大深度
function countNodes(node: any): number {
  let c = 1
  if (node.children) for (const ch of node.children) c += countNodes(ch)
  return c
}
function maxDepth(node: any, d = 1): number {
  if (!node.children?.length) return d
  return Math.max(...node.children.map((ch: any) => maxDepth(ch, d + 1)))
}
const orgNodeCount = computed(() => groupTree.value.length ? countNodes(groupTree.value[0]) : 0)
const orgMaxDepth = computed(() => groupTree.value.length ? maxDepth(groupTree.value[0]) : 0)

async function loadGroupTree() {
  try {
    const res = await getWorksheetTree(projectId.value)
    if (res?.tree) {
      groupTree.value = [res.tree]
    } else {
      const projects = await listChildProjects(projectId.value)
      if (Array.isArray(projects) && projects.length) {
        groupTree.value = projects.map((p: any) => ({
          company_code: p.company_code || p.id,
          company_name: p.client_name || p.name,
          children: [],
        }))
      } else {
        groupTree.value = []
      }
    }
  } catch { groupTree.value = [] }
}

function onTreeNodeClick(data: any) {
  selectedNode.value = data
}

// ── 合并范围模板保存/引用 ──
function getConsolScopeConfigData(): Record<string, any> {
  return {
    group_tree: groupTree.value,
    standard: projectInfo.standard,
  }
}

function onConsolScopeTemplateApplied(data: Record<string, any>) {
  if (data?.group_tree) {
    groupTree.value = data.group_tree
  }
  // 重新加载合并范围数据
  loadGroupTree()
  ElMessage.success('合并范围模板已应用')
}

function goToProject(_node: any) {
  router.push('/consolidation')
}

function fmtAmt(v: any): string {
  return fmt(v)
}

// ─── 合并试算平衡表（已拆分为 ConsolTrialBalanceTab 组件） ──────────────────
// 兼容别名：供 drillDown 等逻辑引用
const consolTbRows = computed(() => consolTbTabRef.value?.consolTbRows || [])
const consolTbType = computed(() => consolTbTabRef.value?.consolTbType || 'balance_sheet')
const consolTbLoading = computed(() => consolTbTabRef.value?.consolTbLoading || false)

function loadConsolTb(forceRefresh = false) {
  consolTbTabRef.value?.loadConsolTb(forceRefresh)
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

function onTbGenerateReportDone() {
  clearEntityCache(currentConsolEntity.value.code || '', ['all_reports'])
}

function onTbCellContextMenu(e: MouseEvent, row: any, ri: number) {
  selectedCells.value = [{ row: ri, col: 2, value: row.summary }]
  drillDownCell.itemName = row.row_name
  drillDownCell.colName = '审定汇总'
  drillDownCell.totalValue = row.summary
  consolCtx.openContextMenu(e, row.row_name, row)
}

// ─── Tab 5: 合并报表 ─────────────────────────────────────────────────────────
const consolReportTemplateType = ref('soe')
const consolReportType = ref('balance_sheet')
const consolReportLoading = ref(false)

// 当前选中的合并主体（树形节点），每个合并节点有独立的报表和附注
const currentConsolEntity = ref<{ code: string; name: string }>({ code: '', name: '' })

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
const showConsolConversion = ref(false)
const consolMappingLoading = ref(false)
const consolMappingRules = ref<any[]>([])

// 权益变动表列 key（合并版：含小计+少数股东）
const consolEqCols = [
  'paid_in_capital', 'other_equity_preferred', 'other_equity_perpetual', 'other_equity_other',
  'capital_reserve', 'treasury_stock', 'oci', 'special_reserve',
  'surplus_reserve', 'general_risk', 'retained_earnings',
  'subtotal', 'minority', 'total',
]

// ─── 前端缓存：按 entity+reportType 缓存，切换秒开，刷新时清缓存 ──────────
const reportCache = new Map<string, any[]>()
const noteCache = new Map<string, any[]>()

function reportCacheKey(): string {
  return `${currentConsolEntity.value.code || '_root'}_${consolReportType.value}_${consolReportTemplateType.value}`
}
function noteCacheKey(): string {
  return `${currentConsolEntity.value.code || '_root'}_${consolNoteTemplateType.value}`
}
/** 清除指定企业的缓存（刷新时调用） */
function clearEntityCache(companyCode: string, types?: string[]) {
  const prefix = companyCode || '_root'
  if (!types || types.includes('all_reports')) {
    // 清除该企业所有报表缓存
    for (const key of reportCache.keys()) {
      if (key.startsWith(prefix + '_')) reportCache.delete(key)
    }
  } else {
    // 清除指定报表类型
    for (const t of types) {
      if (['balance_sheet','income_statement','cash_flow_statement','equity_statement','cash_flow_supplement','impairment_provision'].includes(t)) {
        for (const std of ['soe', 'listed']) {
          reportCache.delete(`${prefix}_${t}_${std}`)
        }
      }
    }
  }
  if (!types || types.includes('notes')) {
    for (const key of noteCache.keys()) {
      if (key.startsWith(prefix + '_')) noteCache.delete(key)
    }
  }
}

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

function onConsolCtxFormula() {
  consolCtx.closeContextMenu()
  eventBus.emit('open-formula-manager', {})
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
  consolReportLoading.value = true
  try {
    const standard = `${consolReportTemplateType.value}_consolidated`
    const params: Record<string, any> = {
      report_type: consolReportType.value,
      applicable_standard: standard,
      project_id: projectId.value,
    }
    if (currentConsolEntity.value.code && currentConsolEntity.value.code !== 'root') {
      params.company_code = currentConsolEntity.value.code
    }
    const data = await api.get('/api/report-config', {
      params,
      validateStatus: (s: number) => s < 600,
    })
    const rows = data ?? []
    const result = Array.isArray(rows) ? rows : []
    consolReportRows.value = result
    // 写入缓存
    reportCache.set(cacheKey, result)
    // 加载批注/复核标记
    consolComments.loadComments(`report_${consolReportType.value}`)
  } catch { consolReportRows.value = [] }
  finally { consolReportLoading.value = false }
}

async function loadConsolMappingPreset() {
  consolMappingLoading.value = true
  try {
    const scope = 'consolidated'
    const data = await api.get(`/api/projects/${projectId.value}/report-mapping/preset`, {
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
    ElMessage.error('转换失败：' + (e?.message || '未知错误'))
  } finally { consolMappingLoading.value = false }
}

function exportConsolReport() {
  const standard = `${consolReportTemplateType.value}_consolidated`
  window.open(`/api/reports/${projectId.value}/${year.value}/export?report_type=${consolReportType.value}&applicable_standard=${standard}`, '_blank')
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
    const data = await api.get(`/api/consol-note-sections/${consolNoteTemplateType.value}`, {
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
  if (data.isReport && data.reportType) {
    // 点击了报表类型节点 → 切换到合并报表 tab 并加载对应报表
    activeTab.value = 'consol_report'
    consolReportType.value = data.reportType
    loadConsolReport()
  } else if (data.isDiff) {
    // 差额表节点 → 切换到合并报表 tab
    activeTab.value = 'consol_report'
    if (data.companyCode) {
      selectedNode.value = { company_code: data.companyCode, company_name: data.label || '' }
    }
  } else if (data.companyCode) {
    // 点击了企业节点 → 选中该节点，刷新报表/附注
    selectedNode.value = { company_code: data.companyCode, company_name: data.label || '' }
    currentConsolEntity.value = { code: data.companyCode, name: data.label || '' }
    // 如果指定了切换 tab
    if (data.switchTab) {
      activeTab.value = data.switchTab
    }
    // 刷新当前 tab 数据
    if (activeTab.value === 'consol_report') loadConsolReport()
    else if (activeTab.value === 'consol_note') loadConsolNoteTree()
  }
}

onMounted(async () => {
  await loadProjectInfo()
  // 默认合并主体为项目本身（集团层面）
  currentConsolEntity.value = { code: '', name: projectInfo.clientName || '' }
  await loadGroupTree()
  eventBus.on('consol-tree-select', onConsolTreeSelect)
  eventBus.on('consol-catalog-select', onConsolCatalogSelect)
  eventBus.on('consol-refresh-entity', onConsolRefreshEntity)
})

onUnmounted(() => {
  eventBus.off('consol-tree-select', onConsolTreeSelect)
  eventBus.off('consol-catalog-select', onConsolCatalogSelect)
  eventBus.off('consol-refresh-entity', onConsolRefreshEntity)
})

// 监听树形节点刷新事件
function onConsolRefreshEntity(detail: ConsolRefreshEntityPayload) {
  if (!detail) return
  const { companyCode, companyName, types } = detail

  // 切换到该合并主体
  currentConsolEntity.value = { code: companyCode, name: companyName }
  selectedNode.value = { company_code: companyCode, company_name: companyName }

  // 清除该企业的缓存
  clearEntityCache(companyCode, types)

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
  }
}

// 监听四栏 catalog 选择事件
function onConsolCatalogSelect(data: ConsolCatalogSelectPayload) {
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
    // 全部刷新
    loadConsolReport()
    loadConsolNoteTree()
  } else if (data.type === 'refresh-report' && data.reportType) {
    // 刷新单个报表
    consolReportType.value = data.reportType
    activeTab.value = 'consol_report'
    loadConsolReport()
  } else if (data.type === 'refresh-note' && data.sectionId) {
    // 刷新单个附注
    activeTab.value = 'consol_note'
    loadConsolNoteTree()
  }
}

watch(activeTab, (tab) => {
  if (tab === 'consol_report') loadConsolReport()
  if (tab === 'consol_note' && !consolNoteTree.value.length) loadConsolNoteTree()
  if (tab === 'consol_tb' && !consolTbRows.value.length) loadConsolTb()
})
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

/* ── 组织结构图 ── */
.org-chart-wrapper {
  overflow: auto; padding: 20px; min-height: 300px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f3f8 100%);
  border: 1px solid #e8e4f0; border-radius: 10px;
  transition: transform 0.2s ease;
}
.org-chart { display: flex; justify-content: center; }
.org-detail-card {
  position: fixed; bottom: 20px; right: 20px; z-index: 100;
  background: #fff; border: 1px solid #e8e4f0; border-radius: 10px;
  padding: 14px 18px; box-shadow: 0 4px 20px rgba(75,45,119,0.12);
  min-width: 200px; max-width: 280px;
}

/* ── 合并报表左右布局 ── */
.gt-report-layout { display: flex; gap: 0; height: calc(100vh - 200px); margin: -12px 0; }
.gt-report-nav {
  width: 240px; flex-shrink: 0; background: #fafafa; border-right: 1px solid #e8e4f0;
  display: flex; flex-direction: column; overflow: hidden;
}
.gt-report-nav-header {
  padding: 10px 12px; border-bottom: 1px solid #e8e4f0; display: flex;
  justify-content: space-between; align-items: center; flex-shrink: 0;
}
.gt-report-tree { flex: 1; overflow-y: auto; padding: 6px; }
.gt-report-tree-node { display: flex; align-items: center; font-size: 12px; }
.gt-report-tree-node--diff { color: #e6a23c; font-style: italic; }

/* 报表类型切换栏（底部） */
.gt-report-type-bar {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 8px; border-top: 1px solid #e8e4f0;
  background: #f5f3f8; flex-shrink: 0;
}
.gt-report-type-item {
  display: flex; align-items: center; gap: 3px; padding: 4px 8px; border-radius: 4px;
  cursor: pointer; font-size: 11px; color: #666; transition: all 0.15s;
}
.gt-report-type-item:hover { background: rgba(75,45,119,0.06); }
.gt-report-type-item--active { background: #4b2d77; color: #fff; }

.gt-report-nav-list { flex: 1; overflow-y: auto; padding: 8px; }
.gt-report-content { flex: 1; min-width: 0; padding: 12px 16px; overflow: auto; }

/* ── 合并报表/附注内容区工具栏 ── */
.gt-report-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; gap: 8px;
}
.gt-report-title {
  margin: 0; font-size: 14px; font-weight: 600; color: #333;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gt-report-actions { display: flex; gap: 6px; flex-shrink: 0; }

/* 当前合并主体标识 */
.gt-entity-badge {
  display: inline-block; padding: 2px 8px; margin-right: 6px;
  background: linear-gradient(135deg, #4b2d77, #7c5caa); color: #fff;
  border-radius: 4px; font-size: 11px; font-weight: 600; white-space: nowrap;
  vertical-align: middle;
}

/* 报表类型标签切换（紧凑） */
.gt-report-type-tabs {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; border-bottom: 2px solid #f0edf5;
}
.gt-report-type-tabs-left {
  display: flex; gap: 0;
}
.gt-report-type-tag {
  padding: 8px 20px; font-size: 14px; color: #666; cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -2px;
  transition: all 0.15s; white-space: nowrap; user-select: none;
  letter-spacing: 0.5px;
}
.gt-report-type-tag:hover { color: #4b2d77; background: rgba(75,45,119,0.04); border-radius: 6px 6px 0 0; }
.gt-report-type-tag--active {
  color: #4b2d77; font-weight: 600;
  border-bottom-color: #4b2d77;
  background: rgba(75,45,119,0.03); border-radius: 6px 6px 0 0;
}

/* ── 合并报表表格紧凑样式 ── */
.gt-consol-report-table :deep(.el-table__row td) {
  height: 32px; line-height: 1.3;
}
.gt-consol-report-table :deep(.el-table__header th) {
  height: 34px;
}

/* ── 矩阵表格（权益变动表 & 资产减值准备表） ── */
.gt-consol-matrix {
  overflow: hidden; border: 1px solid #e8e4f0; border-radius: 6px;
}
.gt-consol-matrix-scroll {
  overflow-x: auto; max-height: calc(100vh - 280px);
}
.gt-consol-matrix-table {
  width: max-content; min-width: 100%; border-collapse: collapse; font-size: 13px;
}
.gt-consol-matrix-table th,
.gt-consol-matrix-table td {
  border: 1px solid #e8e4f0; padding: 6px 10px; white-space: nowrap; text-align: center;
}
.gt-consol-matrix-table thead th {
  background: linear-gradient(180deg, #f4f0fa, #ece6f5); color: #333; font-weight: 600; position: sticky; top: 0; z-index: 2; font-size: 12px;
}
/* 斑马纹 */
.gt-consol-matrix-table tbody tr:nth-child(even) td { background: #faf9fd; }
.gt-consol-matrix-table tbody tr:hover td { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-cm-th-project {
  min-width: 200px; text-align: left !important; position: sticky; left: 0; z-index: 3;
  background: linear-gradient(180deg, #f4f0fa, #ece6f5) !important;
}
.gt-cm-th-prior { background: #f5f3f8 !important; }
.gt-cm-th-total { font-weight: 700 !important; background: #ebe7f2 !important; }
.gt-cm-td-project {
  text-align: left !important; font-size: 12px; position: sticky; left: 0; z-index: 1;
  background: #fff; white-space: nowrap;
}
.gt-cm-td-amt { text-align: right !important; font-size: 13px; min-width: 90px; font-variant-numeric: tabular-nums; }
.gt-tb-editable { cursor: text; border-bottom: 1px dashed var(--gt-color-border, #e5e5ea); padding: 2px 6px; border-radius: 2px; display: inline-block; min-width: 70px; text-align: right; }
.gt-tb-editable:hover { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-cm-td-prior { background: #faf9fc; }
.gt-cm-total-row td { font-weight: 700; background: #f0edf5 !important; }
.gt-cm-category td { font-weight: 600; color: #4b2d77; }
.gt-cm-th-total { background: #e8e0f0 !important; color: #4b2d77; font-weight: 700; }
.gt-tb-audited { font-weight: 700; color: #4b2d77; background: rgba(75,45,119,0.06); }

/* 审核结果行样式 */
:deep(.gt-audit-row-error td) { background: #fef0f0 !important; }
:deep(.gt-audit-row-warn td) { background: #fdf6ec !important; }


</style>
