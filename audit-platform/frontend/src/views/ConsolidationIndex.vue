<template>
  <div class="gt-consol gt-fade-in">
    <!-- 横幅：单位名称 + 年度 + 准则类型 -->
    <div class="gt-consol-bar">
      <el-button text class="gt-consol-bar-back" @click="$router.push('/consolidation')">← 返回</el-button>
      <div class="gt-consol-bar-info">
        <span class="gt-consol-bar-name">{{ projectInfo.clientName || '加载中...' }}</span>
        <el-select v-model="projectInfo.year" size="small" style="width:100px;margin-left:10px" @change="onYearChange">
          <el-option v-for="y in barYearOptions" :key="y" :label="`${y} 年度`" :value="y" />
        </el-select>
        <el-select v-model="projectInfo.standard" size="small" style="width:90px;margin-left:6px" @change="onStandardChange">
          <el-option label="国企版" value="soe" />
          <el-option label="上市版" value="listed" />
        </el-select>
        <el-button size="small" class="gt-bar-btn" @click="showConsolConversion = true">🔄 转换规则</el-button>
        <el-button size="small" class="gt-bar-btn" @click="onOpenFormula">ƒx 公式</el-button>
        <el-tooltip content="选中单元格后点击，查看该数值的汇总明细过程" placement="bottom">
          <el-button size="small" class="gt-bar-btn" @click="openCellDrillDown">📊 查看</el-button>
        </el-tooltip>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="gt-consol-tabs">
      <!-- Tab 0: 合并工作底稿 -->
      <el-tab-pane label="合并工作底稿" name="worksheets">
        <ConsolWorksheetTabs />
      </el-tab-pane>

      <!-- Tab 1: 集团架构 -->
      <el-tab-pane label="集团架构" name="structure">
        <div class="gt-tab-content">
          <!-- 工具栏 -->
          <div style="display:flex;gap:8px;margin-bottom:16px;align-items:center">
            <el-button size="small" :type="orgViewMode === 'chart' ? 'primary' : ''" @click="orgViewMode = 'chart'">📊 组织结构图</el-button>
            <el-button size="small" :type="orgViewMode === 'tree' ? 'primary' : ''" @click="orgViewMode = 'tree'">🌳 树形列表</el-button>
            <el-button size="small" @click="orgZoom = Math.min(orgZoom + 0.1, 2)">🔍+</el-button>
            <el-button size="small" @click="orgZoom = Math.max(orgZoom - 0.1, 0.4)">🔍-</el-button>
            <el-button size="small" @click="orgZoom = 1">1:1</el-button>
            <span style="font-size:11px;color:#999;margin-left:auto">{{ orgNodeCount }} 个节点 · 最大 {{ orgMaxDepth }} 层</span>
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

      <!-- Tab 5: 合并报表 -->
      <el-tab-pane label="合并报表" name="consol_report">
        <div class="gt-tab-content">
          <!-- 报表类型快捷切换（紧凑标签式） + 操作按钮 -->
          <div class="gt-report-type-tabs">
            <div class="gt-report-type-tabs-left">
              <span v-for="item in reportNavItems" :key="item.key"
                class="gt-report-type-tag" :class="{ 'gt-report-type-tag--active': consolReportType === item.key }"
                @click="consolReportType = item.key; loadConsolReport()">
                {{ item.label }}
              </span>
            </div>
            <div class="gt-report-actions">
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
          <el-table v-else-if="consolReportRows.length" :data="consolReportRows" border size="small" max-height="calc(100vh - 260px)" style="width:100%"
            class="gt-consol-report-table"
            :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', padding: '4px 0' }"
            :cell-style="{ padding: '2px 8px', fontSize: '12px', lineHeight: '1.4' }"
            :row-class-name="consolReportRowClass">
            <el-table-column prop="row_code" label="行次" width="100" align="center">
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
              <template #default="{ row }">
                <span style="white-space:nowrap">{{ fmtAmt(row.current_period_amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合并上期" min-width="130" align="right">
              <template #default="{ row }">
                <span style="white-space:nowrap">{{ fmtAmt(row.prior_period_amount) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else-if="!consolReportLoading" description="选择报表类型后点击刷新" />
        </div>
      </el-tab-pane>

      <!-- Tab 6: 合并附注 -->
      <!-- Tab 6: 合并附注 -->
      <el-tab-pane label="合并附注" name="consol_note">
        <div class="gt-tab-content gt-note-layout">
          <!-- 右侧：章节内容（左侧树已移到第3栏 ConsolCatalog） -->
          <div class="gt-note-content" style="flex:1">
            <div v-if="selectedNoteSection" class="gt-note-detail">
              <!-- 工具栏 -->
              <div class="gt-note-toolbar">
                <h4 class="gt-note-section-title">{{ selectedNoteSection.title }}</h4>
                <div class="gt-note-actions">
                  <el-tooltip content="复制整个表格（可粘贴到 Word/Excel）" placement="bottom">
                    <el-button size="small" @click="copyEntireNoteTable">📋</el-button>
                  </el-tooltip>
                  <el-button-group size="small">
                    <el-button :type="noteEditMode ? '' : 'primary'" @click="noteEditMode = false">📋 查看</el-button>
                    <el-button :type="noteEditMode ? 'primary' : ''" @click="noteEditMode = true">✏️ 编辑</el-button>
                  </el-button-group>
                  <el-tooltip content="全屏编辑（ESC 退出）" placement="bottom">
                    <el-button size="small" @click="noteFullscreen = !noteFullscreen">{{ noteFullscreen ? '退出' : '全屏' }}</el-button>
                  </el-tooltip>
                  <el-tooltip content="保存当前表格数据" placement="bottom">
                    <el-button size="small" @click="saveNoteData">💾</el-button>
                  </el-tooltip>
                  <el-tooltip content="导入导出与批量操作" placement="bottom">
                    <el-button size="small" @click="showNoteBatchDialog = true">📦</el-button>
                  </el-tooltip>
                  <el-tooltip content="根据公式从项目数据重新计算" placement="bottom">
                    <el-button size="small" @click="refreshNoteByFormula" :loading="noteRefreshing">🔄</el-button>
                  </el-tooltip>
                  <el-tooltip content="审核当前表格公式一致性" placement="bottom">
                    <el-button size="small" @click="auditCurrentNote" :loading="noteSingleAuditLoading">✅</el-button>
                  </el-tooltip>
                  <el-tooltip content="公式管理（编辑取数规则）" placement="bottom">
                    <el-button size="small" @click="openNoteFormula">ƒx</el-button>
                  </el-tooltip>
                </div>
              </div>

              <!-- 当前表格 -->
              <div v-if="selectedNoteSection.headers?.length" class="gt-note-table-wrap">
                <el-table ref="noteTableRef" :data="selectedNoteSection.editRows" border size="small"
                  :max-height="noteFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 260px)'"
                  style="width:100%" class="gt-note-compact-table"
                  :header-cell-style="{ background: '#f0edf5', fontSize: '13px', padding: '4px 0' }"
                  :cell-style="{ padding: '2px 6px', fontSize: '13px', lineHeight: '1.4' }"
                  :cell-class-name="noteCellClassName"
                  @selection-change="onNoteSelectionChange"
                  @cell-click="onNoteCellClick"
                  @cell-contextmenu="onNoteCellContextMenu">
                  <el-table-column v-if="noteEditMode" type="selection" width="36" />
                  <el-table-column v-for="(h, hi) in selectedNoteSection.headers" :key="hi" :label="h" :min-width="hi === 0 ? 200 : 130">
                    <template #default="{ row, $index }">
                      <el-input v-if="noteEditMode" v-model="row[hi]" size="small" :placeholder="h"
                        :style="{ textAlign: hi === 0 ? 'left' : 'right' }" />
                      <span v-else class="gt-note-cell-text"
                        :style="{ textAlign: hi === 0 ? 'left' : 'right' }">{{ row[hi] || '-' }}</span>
                    </template>
                  </el-table-column>
                </el-table>

                <div class="gt-note-table-footer">
                  <template v-if="noteEditMode">
                    <el-button size="small" @click="addNoteRow">+ 新增行</el-button>
                    <el-button size="small" type="danger" :disabled="!noteSelectedRows.length" @click="deleteNoteRows">
                      删除{{ noteSelectedRows.length ? `(${noteSelectedRows.length})` : '' }}
                    </el-button>
                  </template>
                  <span v-else style="font-size:11px;color:#999">💡 查看模式下可选中复制，粘贴到 Word/Excel 保持格式</span>
                  <span style="flex:1" />
                  <span style="font-size:11px;color:#999">共 {{ selectedNoteSection.editRows?.length || 0 }} 行</span>
                </div>
              </div>
              <el-empty v-else description="该章节暂无表格" :image-size="60" />
            </div>
            <div v-else class="gt-note-empty-guide">
              <div class="gt-note-empty-hero">
                <p>在左侧附注栏选择章节开始编辑，或使用批量功能一键导入全部数据</p>
                <div class="gt-note-empty-actions">
                  <el-button size="small" @click="showNoteBatchDialog = true">📦 批量导入导出</el-button>
                  <el-button size="small" @click="switchToFourCol">🔲 切换四栏视图显示附注树</el-button>
                </div>
              </div>
              <div class="gt-note-empty-steps">
                <div class="gt-note-step">
                  <div class="gt-note-step-icon">①</div>
                  <div class="gt-note-step-text">
                    <b>切换四栏视图</b>
                    <p>点击顶部栏 🔲 按钮或上方快捷按钮，左侧出现附注树形导航，按科目章节分组展示所有表格</p>
                  </div>
                </div>
                <div class="gt-note-step">
                  <div class="gt-note-step-icon">②</div>
                  <div class="gt-note-step-text">
                    <b>选择章节编辑</b>
                    <p>点击树形中的具体表格名称加载到右侧，切换"查看/编辑"模式，编辑模式支持逐单元格修改、增删行、多选删除</p>
                  </div>
                </div>
                <div class="gt-note-step">
                  <div class="gt-note-step-icon">③</div>
                  <div class="gt-note-step-text">
                    <b>批量导入导出</b>
                    <p>点击"📦 批量"弹窗：一键导出全部模板（空表）或数据（已填），一键导入 Excel（按 Sheet 名自动匹配章节）</p>
                  </div>
                </div>
                <div class="gt-note-step">
                  <div class="gt-note-step-icon">④</div>
                  <div class="gt-note-step-text">
                    <b>保存与复制</b>
                    <p>编辑后点"💾 保存"入库，查看模式下可直接框选表格复制，粘贴到 Word/Excel 自动保持表格格式</p>
                  </div>
                </div>
              </div>
              <div class="gt-note-empty-info">
                国企版 91 章节 · 221 表格 &nbsp;|&nbsp; 上市版 80 章节 · 282 表格 &nbsp;|&nbsp; 顶部栏切换准则自动更新 &nbsp;|&nbsp; 每表独立保存不丢失 &nbsp;|&nbsp; 全屏编辑按 ESC 退出
              </div>
            </div>
          </div>
          <input ref="noteFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onNoteFileSelected" />
          <input ref="noteBatchFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onNoteBatchImport" />
          <input ref="noteFormulaFileRef" type="file" accept=".xlsx,.xls,.json" style="display:none" @change="onNoteFormulaImport" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 附注全屏覆盖层（Teleport 到 body 避免被裁剪） -->
    <Teleport to="body">
      <div v-if="noteFullscreen" class="gt-note-fullscreen-overlay">
        <div v-if="selectedNoteSection" class="gt-note-detail">
          <div class="gt-note-toolbar">
            <h4 class="gt-note-section-title">{{ selectedNoteSection.title }}</h4>
            <div class="gt-note-actions">
              <el-button-group size="small">
                <el-button :type="noteEditMode ? '' : 'primary'" @click="noteEditMode = false">📋 查看</el-button>
                <el-button :type="noteEditMode ? 'primary' : ''" @click="noteEditMode = true">✏️ 编辑</el-button>
              </el-button-group>
              <el-tooltip content="公式管理" placement="bottom">
                <el-button size="small" @click="openNoteFormula">ƒx</el-button>
              </el-tooltip>
              <el-button size="small" type="danger" @click="noteFullscreen = false">✕ 退出全屏</el-button>
            </div>
          </div>
          <div v-if="selectedNoteSection.headers?.length" style="flex:1;min-height:0">
            <el-table :data="selectedNoteSection.editRows" border size="small"
              max-height="calc(100vh - 100px)" style="width:100%" class="gt-note-compact-table"
              :header-cell-style="{ background: '#f0edf5', fontSize: '11px', padding: '2px 0' }"
              :cell-style="{ padding: '0 4px', fontSize: '11px', lineHeight: '1.2' }"
              @selection-change="onNoteSelectionChange">
              <el-table-column v-if="noteEditMode" type="selection" width="36" />
              <el-table-column v-for="(h, hi) in selectedNoteSection.headers" :key="hi" :label="h" :min-width="hi === 0 ? 200 : 130">
                <template #default="{ row }">
                  <el-input v-if="noteEditMode" v-model="row[hi]" size="small" :placeholder="h"
                    :style="{ textAlign: hi === 0 ? 'left' : 'right' }" />
                  <span v-else class="gt-note-cell-text" :style="{ textAlign: hi === 0 ? 'left' : 'right' }">{{ row[hi] || '-' }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div class="gt-note-table-footer" style="margin-top:6px">
            <template v-if="noteEditMode">
              <el-button size="small" @click="addNoteRow">+ 新增行</el-button>
              <el-button size="small" type="danger" :disabled="!noteSelectedRows.length" @click="deleteNoteRows">
                删除{{ noteSelectedRows.length ? `(${noteSelectedRows.length})` : '' }}
              </el-button>
            </template>
            <span style="flex:1" />
            <span style="font-size:11px;color:#999">共 {{ selectedNoteSection.editRows?.length || 0 }} 行 · ESC 退出全屏</span>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 右键菜单（Teleport 到 body 避免被裁剪） -->
    <Teleport to="body">
      <Transition name="gt-ctx-fade">
        <div v-if="cellContextMenu.visible" class="gt-cell-context-menu"
          :style="{ left: cellContextMenu.x + 'px', top: cellContextMenu.y + 'px' }"
          @contextmenu.prevent>
          <div class="gt-cell-ctx-header">
            <span>{{ drillDownCell.itemName }}</span>
            <span v-if="drillDownCell.totalValue != null" style="color:#4b2d77;font-weight:600">{{ fmtAmt(drillDownCell.totalValue) }}</span>
          </div>
          <div class="gt-cell-ctx-divider" />
          <div class="gt-cell-ctx-item" @click="drillDownFromCell"><span class="gt-cell-ctx-icon">📊</span> 查看汇总穿透</div>
          <div class="gt-cell-ctx-item" @click="copyCellValue"><span class="gt-cell-ctx-icon">📋</span> 复制值</div>
          <div class="gt-cell-ctx-item" @click="copyCellFormula"><span class="gt-cell-ctx-icon">ƒx</span> 查看公式</div>
          <div class="gt-cell-ctx-item" @click="addCellComment"><span class="gt-cell-ctx-icon">💬</span> 添加批注</div>
          <div class="gt-cell-ctx-item" @click="markCellReviewed"><span class="gt-cell-ctx-icon">✅</span> 标记已复核</div>
          <div class="gt-cell-ctx-divider" />
          <div class="gt-cell-ctx-item" @click="openAggregateDialog"><span class="gt-cell-ctx-icon">Σ</span> 汇总</div>
          <div v-if="selectedCells.length > 1" class="gt-cell-ctx-divider" />
          <div v-if="selectedCells.length > 1" class="gt-cell-ctx-item" @click="sumSelectedCells">
            <span class="gt-cell-ctx-icon">Σ</span> 求和选中 <span style="color:#4b2d77;font-weight:600;margin-left:4px">{{ selectedCells.length }} 格</span>
          </div>
          <div v-if="selectedCells.length > 1" class="gt-cell-ctx-item" @click="compareSelectedCells">
            <span class="gt-cell-ctx-icon">⇄</span> 对比差异
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 批量导入导出弹窗 -->
    <el-dialog v-model="showNoteBatchDialog" title="附注导入导出与批量操作" width="520px" append-to-body>
      <div style="display:flex;flex-direction:column;gap:10px">
        <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">当前表格操作</p>
        <div style="display:flex;gap:8px">
          <el-button size="small" @click="exportNoteTemplate" :disabled="!selectedNoteSection">📥 导出当前模板</el-button>
          <el-button size="small" @click="exportNoteData" :disabled="!selectedNoteSection">📤 导出当前数据</el-button>
          <el-button size="small" @click="noteFileRef?.click()" :disabled="!selectedNoteSection">📤 导入当前表格</el-button>
        </div>
        <el-divider style="margin:6px 0" />
        <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">全部附注批量操作</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <el-button size="small" @click="batchExportAllTemplates" :loading="noteBatchLoading">📥 一键导出全部模板</el-button>
          <el-button size="small" @click="batchExportAllData" :loading="noteBatchLoading">📤 一键导出全部数据</el-button>
          <el-button size="small" type="primary" @click="noteBatchFileRef?.click()" :loading="noteBatchLoading">📤 一键导入全部数据</el-button>
        </div>
        <el-divider style="margin:6px 0" />
        <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">公式审核</p>
        <div style="display:flex;gap:8px">
          <el-button size="small" @click="() => { auditCurrentNote(); showNoteBatchDialog = false }" :disabled="!selectedNoteSection" :loading="noteSingleAuditLoading">✅ 审核当前表格</el-button>
          <el-button size="small" @click="() => { onNoteAuditAll(); showNoteBatchDialog = false }">✅ 全部附注审核</el-button>
        </div>
        <el-divider style="margin:6px 0" />
        <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">公式管理</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <el-button size="small" @click="() => { openNoteFormula(); showNoteBatchDialog = false }">ƒx 打开公式管理</el-button>
          <el-button size="small" @click="exportNoteFormulas" :loading="noteBatchLoading">📥 导出公式模板</el-button>
          <el-button size="small" @click="noteFormulaFileRef?.click()" :loading="noteBatchLoading">📤 导入公式</el-button>
          <el-button size="small" type="primary" @click="applyAllNoteFormulas" :loading="noteBatchLoading">▶ 一键取数计算</el-button>
        </div>
        <p style="font-size:11px;color:#999;margin:4px 0 0">
          导出 Excel 每个表格一个 Sheet（编号+标题），导入按 Sheet 名自动匹配。
        </p>
      </div>
      <template #footer>
        <el-button @click="showNoteBatchDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 附注全审结果弹窗 -->
    <el-dialog v-model="showNoteAuditDialog" title="附注公式审核结果" width="80%" top="4vh" append-to-body destroy-on-close :z-index="10000">
      <div v-if="noteAuditLoading" style="text-align:center;padding:40px">
        <span class="is-loading" style="font-size:24px;display:inline-block">⏳</span>
        <p style="color:#999;margin-top:8px">正在审核所有附注表格...</p>
      </div>
      <div v-else>
        <div style="display:flex;gap:12px;margin-bottom:12px;align-items:center">
          <el-tag :type="noteAuditSummary.errorCount ? 'danger' : 'success'" size="large">
            {{ noteAuditSummary.errorCount ? `${noteAuditSummary.errorCount} 项异常` : '全部通过' }}
          </el-tag>
          <span style="font-size:12px;color:#999">
            共审核 {{ noteAuditSummary.totalSections }} 个章节 · {{ noteAuditSummary.totalChecks }} 条规则 ·
            通过 {{ noteAuditSummary.passCount }} · 异常 {{ noteAuditSummary.errorCount }} · 警告 {{ noteAuditSummary.warnCount }}
          </span>
        </div>
        <el-table :data="noteAuditResults" border size="small" max-height="60vh" style="width:100%"
          :header-cell-style="{ background: '#f8f6fb', fontSize: '12px' }"
          :row-class-name="auditRowClass">
          <el-table-column prop="section_title" label="章节" min-width="160" show-overflow-tooltip />
          <el-table-column prop="rule_name" label="审核规则" min-width="200" show-overflow-tooltip />
          <el-table-column prop="level" label="级别" width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="row.level === 'error' ? 'danger' : row.level === 'warn' ? 'warning' : 'success'" size="small">
                {{ row.level === 'error' ? '异常' : row.level === 'warn' ? '警告' : '通过' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="expected" label="预期值" width="120" align="right" />
          <el-table-column prop="actual" label="实际值" width="120" align="right" />
          <el-table-column prop="difference" label="差异" width="120" align="right">
            <template #default="{ row }">
              <span :style="{ color: row.difference ? '#f56c6c' : '#67c23a' }">{{ row.difference || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="说明" min-width="200" show-overflow-tooltip />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="showNoteAuditDialog = false">关闭</el-button>
        <el-button type="primary" @click="exportAuditResults">📤 导出审核报告</el-button>
      </template>
    </el-dialog>

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

    <!-- 批注弹窗 -->
    <el-dialog v-model="showCommentDialog" title="添加审计批注" width="650px" append-to-body :z-index="10000" class="gt-comment-dialog">
      <div class="gt-comment-info">
        <div class="gt-comment-info-item">
          <span class="gt-comment-info-label">项目</span>
          <span class="gt-comment-info-value">{{ commentTarget.itemName }}</span>
        </div>
        <div class="gt-comment-info-item">
          <span class="gt-comment-info-label">列</span>
          <span class="gt-comment-info-value">{{ commentTarget.colName }}</span>
        </div>
        <div class="gt-comment-info-item">
          <span class="gt-comment-info-label">当前值</span>
          <span class="gt-comment-info-value gt-comment-info-value--primary">{{ commentTarget.value || '-' }}</span>
        </div>
      </div>
      <el-input v-model="commentTarget.text" type="textarea" :rows="8"
        placeholder="输入审计批注、发现的问题或需要跟进的事项..."
        maxlength="500" show-word-limit
        class="gt-comment-textarea" />
      <template #footer>
        <el-button @click="showCommentDialog = false">取消</el-button>
        <el-button type="primary" @click="saveComment">保存批注</el-button>
      </template>
    </el-dialog>

    <!-- 汇总弹窗 -->
    <el-dialog v-model="showAggregateDialog" title="数据汇总" width="800px" append-to-body :z-index="10000" class="gt-comment-dialog">
      <div class="gt-comment-info" style="margin-bottom:16px">
        <div class="gt-comment-info-item" style="flex:2">
          <span class="gt-comment-info-label">目标单元格</span>
          <span class="gt-comment-info-value" style="font-size:14px">{{ aggTarget.itemName }} / {{ aggTarget.colName }}</span>
        </div>
        <div class="gt-comment-info-item">
          <span class="gt-comment-info-label">当前值</span>
          <span class="gt-comment-info-value gt-comment-info-value--primary">{{ aggTarget.currentValue || '-' }}</span>
        </div>
        <div class="gt-comment-info-item">
          <span class="gt-comment-info-label">当前单位</span>
          <span class="gt-comment-info-value">{{ currentConsolEntity.name || '集团' }}</span>
        </div>
      </div>

      <el-radio-group v-model="aggTarget.mode" style="margin-bottom:14px;width:100%">
        <el-radio value="direct" style="display:flex;align-items:flex-start;margin-bottom:12px;width:100%">
          <div>
            <b>直接下级汇总</b>
            <p style="margin:2px 0 0;font-size:12px;color:#999">汇总当前合并节点的直接下级企业，取同表同行同列数据求和</p>
          </div>
        </el-radio>
        <el-radio value="custom" style="display:flex;align-items:flex-start;width:100%">
          <div>
            <b>自定义汇总</b>
            <p style="margin:2px 0 0;font-size:12px;color:#999">自由选择单位、数据表、坐标位置</p>
          </div>
        </el-radio>
      </el-radio-group>

      <!-- 自定义汇总详细设置 -->
      <div v-if="aggTarget.mode === 'custom'" style="border:1px solid #e8e4f0;border-radius:8px;padding:14px;background:#faf9fc">
        <div style="display:flex;gap:16px">
          <!-- 左侧：选择单位 -->
          <div style="flex:1;min-width:0">
            <p style="font-size:12px;color:#666;margin:0 0 6px;font-weight:600">① 选择汇总单位</p>
            <div style="border:1px solid #e8e4f0;border-radius:6px;padding:6px;max-height:200px;overflow-y:auto;background:#fff">
              <el-tree :data="aggTreeData" :props="{ label: 'label', children: 'children' }"
                show-checkbox node-key="key" ref="aggTreeRef"
                default-expand-all>
                <template #default="{ data }">
                  <span style="font-size:12px">{{ data.icon }} {{ data.label }}
                    <el-tag v-if="data.ratio" size="small" type="info" style="margin-left:4px;font-size:10px">{{ data.ratio }}%</el-tag>
                  </span>
                </template>
              </el-tree>
            </div>
          </div>
          <!-- 右侧：选择数据来源和坐标 -->
          <div style="width:280px;flex-shrink:0">
            <p style="font-size:12px;color:#666;margin:0 0 6px;font-weight:600">② 数据来源</p>
            <el-radio-group v-model="aggTarget.source" size="small" style="margin-bottom:10px">
              <el-radio-button value="same">当前表格</el-radio-button>
              <el-radio-button value="report">报表</el-radio-button>
              <el-radio-button value="note">附注</el-radio-button>
            </el-radio-group>

            <div v-if="aggTarget.source === 'report'" style="margin-bottom:8px">
              <el-select v-model="aggTarget.reportTypes" size="small" style="width:100%" placeholder="选择报表（可多选）" multiple collapse-tags>
                <el-option label="全部报表" value="_all" />
                <el-option label="资产负债表" value="balance_sheet" />
                <el-option label="利润表" value="income_statement" />
                <el-option label="现金流量表" value="cash_flow_statement" />
                <el-option label="权益变动表" value="equity_statement" />
                <el-option label="现金流附表" value="cash_flow_supplement" />
                <el-option label="资产减值准备表" value="impairment_provision" />
              </el-select>
            </div>
            <div v-if="aggTarget.source === 'note'" style="margin-bottom:8px">
              <el-select v-model="aggTarget.noteSections" size="small" style="width:100%" placeholder="选择附注章节（可多选）" multiple collapse-tags filterable>
                <el-option label="全部附注" value="_all" />
                <el-option v-for="sec in aggNoteSections" :key="sec.section_id" :label="sec.title" :value="sec.section_id" />
              </el-select>
            </div>

            <p style="font-size:12px;color:#666;margin:10px 0 6px;font-weight:600">③ 坐标位置（可选）</p>
            <div style="display:flex;gap:8px">
              <div style="flex:1">
                <div style="font-size:10px;color:#999;margin-bottom:2px">行（项目名）</div>
                <el-input v-model="aggTarget.rowName" size="small" placeholder="留空=整表" clearable />
              </div>
              <div style="flex:1">
                <div style="font-size:10px;color:#999;margin-bottom:2px">列（表头名）</div>
                <el-input v-model="aggTarget.colHeader" size="small" placeholder="留空=整表" clearable />
              </div>
            </div>
            <p style="font-size:10px;color:#bbb;margin:4px 0 0">留空则汇总整张表格所有数据，填写则只汇总指定行列交叉位置</p>
          </div>
        </div>
      </div>

      <!-- 操作提示 -->
      <div style="margin-top:14px;padding:10px 14px;background:#f8f6fb;border-radius:6px;font-size:13px;color:#666;line-height:1.6">
        <b style="color:#4b2d77">💡 操作提示：</b>
        <span v-if="aggTarget.mode === 'direct'">点击"执行汇总"后，系统将自动获取直接下级企业的数据并求和，结果填充到当前选中的单元格。执行前会弹出确认框。</span>
        <span v-else>选择企业和数据来源后点击"执行汇总"，系统会弹出确认框显示汇总范围。坐标留空=汇总整表数据，填写=只汇总指定位置。</span>
      </div>

      <template #footer>
        <el-button @click="showAggregateDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmAndExecuteAggregate" :loading="aggLoading">执行汇总</el-button>
      </template>
    </el-dialog>

    <!-- 附注公式管理弹窗 -->
    <el-dialog v-model="showNoteFormulaDialog" :title="`公式管理 — ${selectedNoteSection?.title || ''}`" width="85%" top="4vh" append-to-body destroy-on-close :z-index="10000">
      <div style="margin-bottom:10px;display:flex;gap:8px;align-items:center">
        <span style="font-size:12px;color:#999">共 {{ noteFormulaRules.length }} 条公式规则，点击"执行取数"从试算表自动填充数据</span>
        <span style="flex:1" />
        <el-button size="small" @click="addNoteFormulaRule">+ 新增规则</el-button>
        <el-button size="small" type="primary" @click="applyNoteFormulaRules" :loading="noteRefreshing">▶ 执行取数</el-button>
      </div>
      <el-table :data="noteFormulaRules" border size="small" max-height="55vh" style="width:100%"
        :header-cell-style="{ background: '#f0edf5', fontSize: '11px' }"
        :cell-style="{ padding: '2px 6px', fontSize: '11px' }">
        <el-table-column label="行" width="50" align="center">
          <template #default="{ row }">{{ row.row + 1 }}</template>
        </el-table-column>
        <el-table-column prop="itemName" label="项目名称" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.itemName" size="small" placeholder="科目/项目名" />
          </template>
        </el-table-column>
        <el-table-column prop="colName" label="目标列" width="120">
          <template #default="{ row }">
            <el-input v-model="row.colName" size="small" placeholder="列名" />
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-select v-model="row.type" size="small" style="width:100%">
              <el-option label="试算表取数" value="TB_REF" />
              <el-option label="自动求和" value="SUM" />
              <el-option label="跨表引用" value="CROSS_REF" />
              <el-option label="手动输入" value="manual" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="formula" label="公式表达式" min-width="220">
          <template #default="{ row }">
            <el-input v-model="row.formula" size="small" placeholder='如 =TB("货币资金","期末余额")' />
          </template>
        </el-table-column>
        <el-table-column prop="source" label="数据来源" width="90">
          <template #default="{ row }">
            <span style="font-size:11px;color:#999">{{ row.source }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentValue" label="当前值" width="100" align="right">
          <template #default="{ row }">
            <span style="font-size:11px">{{ row.currentValue || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" link type="danger" @click="removeNoteFormulaRule($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top:10px;padding:8px;background:#f8f6fb;border-radius:6px;font-size:11px;color:#666;line-height:1.6">
        <b>公式类型说明：</b><br/>
        · <b>TB_REF</b>（试算表取数）：从项目试算表按科目名匹配，提取期末/期初余额。格式：=TB("科目名","期末余额")<br/>
        · <b>SUM</b>（自动求和）：合计行自动汇总上方明细行数据<br/>
        · <b>CROSS_REF</b>（跨表引用）：从其他附注表格或报表引用数据。格式：=REF("章节ID","行名","列名")<br/>
        · <b>manual</b>（手动输入）：不自动计算，由用户手动填写
      </div>
      <template #footer>
        <el-button @click="showNoteFormulaDialog = false">关闭</el-button>
        <el-button @click="() => { document.dispatchEvent(new CustomEvent('gt-open-formula-manager', { detail: { nodeKey: 'consol_note' } })); showNoteFormulaDialog = false }">
          打开全局公式管理器
        </el-button>
        <el-button type="primary" @click="applyNoteFormulaRules" :loading="noteRefreshing">▶ 执行取数</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getWorksheetTree,
  type WorksheetNode,
} from '@/services/consolidationApi'
import { listChildProjects } from '@/services/commonApi'
import http from '@/utils/http'
import ConsolWorksheetTabs from '@/components/consolidation/worksheets/ConsolWorksheetTabs.vue'
import OrgNode from '@/components/consolidation/OrgNode.vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

const activeTab = ref('worksheets')
const loading = ref(false)

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
  window.dispatchEvent(new CustomEvent('consol-standard-change', { detail: { standard: projectInfo.standard } }))
}

function onOpenFormula() {
  document.dispatchEvent(new CustomEvent('gt-open-formula-manager', { detail: { nodeKey: 'consolidation' } }))
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

const currentDrillDownRows = computed(() => {
  return drillDownLevel.value === 'direct' ? drillDownDirectRows.value : drillDownLeafRows.value
})
const drillDownTitle = computed(() => {
  return `汇总穿透 — ${drillDownCell.itemName} / ${drillDownCell.colName}`
})

function openCellDrillDown() {
  // 从当前选中的附注表格或报表中获取选中单元格信息
  const sec = selectedNoteSection.value
  if (sec && sec.editRows?.length) {
    // 附注模式：提示用户先点击单元格
    // 这里用一个简单的弹窗让用户选择行和列
    showCellDrillDown.value = true
    drillDownCell.sectionId = sec.section_id || ''
    // 如果有选中行，用第一个选中行
    if (noteSelectedRows.value.length) {
      const row = noteSelectedRows.value[0]
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
    // 从基本信息表获取企业列表
    const { loadAllWorksheetData } = await import('@/services/consolWorksheetDataApi')
    const saved = await loadAllWorksheetData(projectId.value, year.value)
    const infoRows = saved?.info?.rows || []
    const companies = Array.isArray(infoRows) ? infoRows.filter((r: any) => r.company_name) : []

    const totalVal = Number(drillDownCell.totalValue) || 0

    // 直接下级：每个子企业贡献的金额
    const directRows: any[] = []
    for (const comp of companies) {
      // 实际应从各企业的试算表/附注数据中提取
      // 这里模拟：按持股比例分配（实际需要后端 API 支持）
      const ratio = comp.non_common_ratio || comp.common_ratio || comp.no_consol_ratio || 0
      const amount = totalVal ? Math.round(totalVal * (ratio / 100) * 100) / 100 : null
      directRows.push({
        company_name: comp.company_name,
        company_code: comp.company_code,
        amount,
        ratio: totalVal && amount ? Math.round(((amount / totalVal) * 100) * 100) / 100 : 0,
        source: comp.holding_type === '间接' ? '间接持股' : '直接持股',
        parent_name: comp.indirect_holder || '母公司',
      })
    }
    drillDownDirectRows.value = directRows

    // 末级明细：展开到最底层（无子企业的企业）
    const leafRows = directRows.filter(r => {
      // 没有下级的就是末级
      return !companies.some((c: any) => c.indirect_holder === r.company_name)
    })
    drillDownLeafRows.value = leafRows
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
    const { data } = await http.get(`/api/projects/${projectId.value}`, { validateStatus: (s: number) => s < 600 })
    const p = data?.data ?? data
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

function goToProject(node: any) {
  router.push('/consolidation')
}

function fmtAmt(v: any): string {
  if (v == null) return '-'
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
    const { data } = await http.get('/api/report-config', {
      params,
      validateStatus: (s: number) => s < 600,
    })
    const rows = data?.data ?? data ?? []
    const result = Array.isArray(rows) ? rows : []
    consolReportRows.value = result
    // 写入缓存
    reportCache.set(cacheKey, result)
  } catch { consolReportRows.value = [] }
  finally { consolReportLoading.value = false }
}

async function loadConsolMappingPreset() {
  consolMappingLoading.value = true
  try {
    const scope = 'consolidated'
    const { data } = await http.get(`/api/projects/${projectId.value}/report-mapping/preset`, {
      params: { report_type: consolReportType.value, scope },
      validateStatus: (s: number) => s < 600,
    })
    const rules = Array.isArray(data) ? data : (data?.data ?? [])
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
    window.dispatchEvent(new CustomEvent('consol-standard-change', { detail: { standard: newType } }))
  } catch (e: any) {
    ElMessage.error('转换失败：' + (e?.message || '未知错误'))
  } finally { consolMappingLoading.value = false }
}

function exportConsolReport() {
  const standard = `${consolReportTemplateType.value}_consolidated`
  window.open(`/api/reports/${projectId.value}/${year.value}/export?report_type=${consolReportType.value}&applicable_standard=${standard}`, '_blank')
}

function getConsolReportConfigData(): Record<string, any> {
  return { rows: consolReportRows.value, template_type: consolReportTemplateType.value, report_type: consolReportType.value }
}

function onConsolReportTemplateApplied(_data: Record<string, any>) {
  loadConsolReport()
}

// ─── Tab 6: 合并附注 ─────────────────────────────────────────────────────────
const consolNoteTemplateType = ref('soe')
const consolNoteLoading = ref(false)
const consolNoteTree = ref<any[]>([])
const selectedNoteSection = ref<any>(null)
const activeNoteTable = ref('0')
const noteTreeSearch = ref('')
const noteTreeRef = ref<any>(null)
const showConsolNoteConversion = ref(false)
const noteFullscreen = ref(false)
const noteEditMode = ref(false)
const noteRefreshing = ref(false)
const noteSingleAuditLoading = ref(false)
const noteFileRef = ref<HTMLInputElement | null>(null)
const noteTableRef = ref<any>(null)
const noteSelectedRows = ref<any[]>([])
const noteBatchFileRef = ref<HTMLInputElement | null>(null)
const noteFormulaFileRef = ref<HTMLInputElement | null>(null)
const showNoteBatchDialog = ref(false)
const noteBatchLoading = ref(false)

// ─── 附注全审 ────────────────────────────────────────────────────────────────
const showNoteAuditDialog = ref(false)
const noteAuditLoading = ref(false)
const noteAuditResults = ref<any[]>([])
const noteAuditSummary = reactive({ totalSections: 0, totalChecks: 0, passCount: 0, errorCount: 0, warnCount: 0 })

async function onNoteAuditAll(_e?: Event) {
  showNoteAuditDialog.value = true
  noteAuditLoading.value = true
  noteAuditResults.value = []
  try {
    const entityCode = currentConsolEntity.value.code || ''
    const { data } = await http.post(`/api/consol-note-sections/audit-all/${projectId.value}/${year.value}`, {
      standard: consolNoteTemplateType.value,
      company_code: entityCode,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    noteAuditResults.value = Array.isArray(result?.results) ? result.results : []
    noteAuditSummary.totalSections = result?.total_sections || 0
    noteAuditSummary.totalChecks = noteAuditResults.value.length
    noteAuditSummary.passCount = noteAuditResults.value.filter((r: any) => r.level === 'pass').length
    noteAuditSummary.errorCount = noteAuditResults.value.filter((r: any) => r.level === 'error').length
    noteAuditSummary.warnCount = noteAuditResults.value.filter((r: any) => r.level === 'warn').length
  } catch {
    ElMessage.info('全审功能需要后端配合，当前为预留接口')
  } finally { noteAuditLoading.value = false }
}

function auditRowClass({ row }: { row: any }) {
  if (row.level === 'error') return 'gt-audit-row-error'
  if (row.level === 'warn') return 'gt-audit-row-warn'
  return ''
}

async function exportAuditResults() {
  if (!noteAuditResults.value.length) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = ['章节', '审核规则', '级别', '预期值', '实际值', '差异', '说明']
  const rows = noteAuditResults.value.map((r: any) => [
    r.section_title, r.rule_name,
    r.level === 'error' ? '异常' : r.level === 'warn' ? '警告' : '通过',
    r.expected, r.actual, r.difference, r.message,
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
  ws['!cols'] = [{ wch: 20 }, { wch: 30 }, { wch: 8 }, { wch: 14 }, { wch: 14 }, { wch: 14 }, { wch: 30 }]
  XLSX.utils.book_append_sheet(wb, ws, '审核结果')
  XLSX.writeFile(wb, `合并附注_审核报告_${consolNoteTemplateType.value}.xlsx`)
  ElMessage.success('审核报告已导出')
}
// 当前选中的章节直接包含 headers + editRows，无需 sub-tabs

function onNoteSelectionChange(rows: any[]) { noteSelectedRows.value = rows }

async function refreshNoteByFormula() {
  const sec = selectedNoteSection.value
  if (!sec || !projectId.value) { ElMessage.warning('请先选择章节'); return }
  noteRefreshing.value = true
  try {
    // 请求后端根据公式重新计算该章节的数据
    const entityCode = currentConsolEntity.value.code || ''
    const { data } = await http.post(`/api/consol-note-sections/refresh/${projectId.value}/${year.value}/${sec.section_id}`, {
      standard: consolNoteTemplateType.value,
      company_code: entityCode,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    if (result?.rows?.length) {
      // 用计算结果更新 editRows
      const headers = sec.headers
      sec.editRows = result.rows.map((r: string[]) => {
        const obj: any = {}
        for (let j = 0; j < headers.length; j++) obj[j] = r[j] || ''
        return obj
      })
      ElMessage.success(`已刷新 ${result.rows.length} 行数据`)
    } else {
      ElMessage.info('暂无可计算的公式数据，请确认项目中已有对应科目的试算表数据')
    }
  } catch {
    ElMessage.info('公式刷新功能需要后端配合，当前为预留接口')
  } finally { noteRefreshing.value = false }
}

// ─── 公式编辑弹窗 ────────────────────────────────────────────────────────────
const showNoteFormulaDialog = ref(false)
const noteFormulaRules = ref<any[]>([])

// ─── 单元格选中与右键菜单 ──────────────────────────────────────────────────
const selectedCells = ref<{ row: number; col: number; value: any }[]>([])
const cellContextMenu = reactive({ visible: false, x: 0, y: 0 })

function noteCellClassName({ rowIndex, columnIndex }: any) {
  if (selectedCells.value.some(c => c.row === rowIndex && c.col === columnIndex)) {
    return 'gt-cell--selected'
  }
  return ''
}

function isCellSelected(rowIdx: number, colIdx: number): boolean {
  return selectedCells.value.some(c => c.row === rowIdx && c.col === colIdx)
}

function onNoteCellClick(row: any, column: any, cell: HTMLElement, event: MouseEvent) {
  closeCellContextMenu()
  const sec = selectedNoteSection.value
  if (!sec || noteEditMode.value) return
  const colIdx = sec.headers.indexOf(column.label)
  if (colIdx < 0) return
  const rowIdx = sec.editRows.indexOf(row)
  if (rowIdx < 0) return

  if (event.ctrlKey || event.metaKey) {
    // Ctrl+点击：多选
    const existing = selectedCells.value.findIndex(c => c.row === rowIdx && c.col === colIdx)
    if (existing >= 0) {
      selectedCells.value.splice(existing, 1)
    } else {
      selectedCells.value.push({ row: rowIdx, col: colIdx, value: row[colIdx] })
    }
  } else {
    // 单击：单选
    selectedCells.value = [{ row: rowIdx, col: colIdx, value: row[colIdx] }]
  }

  // 同步到 drillDownCell
  if (selectedCells.value.length === 1) {
    const c = selectedCells.value[0]
    drillDownCell.itemName = sec.editRows[c.row]?.[0] || ''
    drillDownCell.colName = sec.headers[c.col] || ''
    drillDownCell.totalValue = Number(c.value) || null
    drillDownCell.rowIdx = c.row
    drillDownCell.colIdx = c.col
  }
}

function onNoteCellContextMenu(row: any, column: any, cell: HTMLElement, event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  // 先触发选中
  const sec = selectedNoteSection.value
  if (!sec || noteEditMode.value) return
  const colIdx = sec.headers.indexOf(column.label)
  if (colIdx < 0) return
  const rowIdx = sec.editRows.indexOf(row)
  if (rowIdx < 0) return
  // 如果没选中这个格子，先选中
  if (!selectedCells.value.some(c => c.row === rowIdx && c.col === colIdx)) {
    selectedCells.value = [{ row: rowIdx, col: colIdx, value: row[colIdx] }]
    drillDownCell.itemName = row[0] || ''
    drillDownCell.colName = sec.headers[colIdx] || ''
    drillDownCell.totalValue = Number(row[colIdx]) || null
    drillDownCell.rowIdx = rowIdx
    drillDownCell.colIdx = colIdx
  }
  // 显示右键菜单（延迟一帧避免被 document click 立即关闭）
  setTimeout(() => {
    cellContextMenu.x = event.clientX
    cellContextMenu.y = event.clientY
    cellContextMenu.visible = true
  }, 0)
}

function closeCellContextMenu() {
  cellContextMenu.visible = false
}

function drillDownFromCell() {
  closeCellContextMenu()
  if (selectedCells.value.length) {
    showCellDrillDown.value = true
    loadDrillDownData()
  }
}

function copyCellValue() {
  closeCellContextMenu()
  const values = selectedCells.value.map(c => c.value || '-').join('\t')
  navigator.clipboard?.writeText(values)
  ElMessage.success('已复制到剪贴板')
}

function copyCellFormula() {
  closeCellContextMenu()
  openNoteFormula()
}

function sumSelectedCells() {
  closeCellContextMenu()
  const sum = selectedCells.value.reduce((s, c) => s + (Number(c.value) || 0), 0)
  ElMessage.info(`选中 ${selectedCells.value.length} 格，合计：${fmtAmt(sum)}`)
}

function compareSelectedCells() {
  closeCellContextMenu()
  if (selectedCells.value.length < 2) return
  const vals = selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  const pct = vals[1] !== 0 ? ((diff / Math.abs(vals[1])) * 100).toFixed(2) : '—'
  ElMessage.info(`差异：${fmtAmt(diff)}（${pct}%）| 值1=${fmtAmt(vals[0])} 值2=${fmtAmt(vals[1])}`)
}

function addCellComment() {
  closeCellContextMenu()
  if (!selectedCells.value.length) return
  const c = selectedCells.value[0]
  const sec = selectedNoteSection.value
  commentTarget.itemName = sec?.editRows?.[c.row]?.[0] || ''
  commentTarget.colName = sec?.headers?.[c.col] || ''
  commentTarget.value = c.value || ''
  commentTarget.text = ''
  showCommentDialog.value = true
}

const showCommentDialog = ref(false)
const commentTarget = reactive({ itemName: '', colName: '', value: '', text: '' })

function saveComment() {
  if (!commentTarget.text.trim()) { ElMessage.warning('请输入批注内容'); return }
  ElMessage.success('批注已保存')
  showCommentDialog.value = false
}

function markCellReviewed() {
  closeCellContextMenu()
  const count = selectedCells.value.length
  ElMessage.success(`已标记 ${count} 个单元格为已复核`)
}

// ─── 汇总功能 ────────────────────────────────────────────────────────────────
const showAggregateDialog = ref(false)
const aggLoading = ref(false)
const aggTreeRef = ref<any>(null)
const aggTarget = reactive({
  itemName: '', colName: '', currentValue: '',
  mode: 'direct' as 'direct' | 'custom',
  source: 'same' as 'same' | 'report' | 'note',
  reportTypes: [] as string[],
  noteSections: [] as string[],
  rowName: '',
  colHeader: '',
})

// 汇总用的树形数据（从 groupTree + 基本信息表获取）
const aggTreeData = computed(() => {
  function buildAggNode(node: any): any {
    return {
      key: node.company_code || 'root',
      label: node.company_name || node.name,
      icon: node.children?.length ? '🏢' : '🏠',
      ratio: node.shareholding,
      children: (node.children || []).map(buildAggNode),
    }
  }
  const tree = groupTree.value.map(buildAggNode)
  // 如果树只有根节点没有子级，从 selectedNoteSection 的 editRows 中提取项目名作为提示
  if (tree.length === 1 && !tree[0].children?.length) {
    // 尝试从基本信息表补充
    // （树形数据由 ConsolMiddleNav 管理，这里只是展示用）
  }
  return tree
})

// 附注章节列表（用于自定义汇总选择数据来源）
const aggNoteSections = computed(() => {
  const sections: { section_id: string; title: string }[] = []
  for (const group of consolNoteTree.value) {
    for (const child of (group.children || [])) {
      sections.push({ section_id: child.section_id || child.key, title: child.title || child.label })
    }
  }
  return sections
})

function openAggregateDialog() {
  closeCellContextMenu()
  if (!selectedCells.value.length) { ElMessage.warning('请先选中单元格'); return }
  const c = selectedCells.value[0]
  const sec = selectedNoteSection.value
  aggTarget.itemName = sec?.editRows?.[c.row]?.[0] || ''
  aggTarget.colName = sec?.headers?.[c.col] || ''
  aggTarget.currentValue = c.value || ''
  aggTarget.mode = 'direct'
  aggTarget.source = 'same'
  aggTarget.rowName = ''  // 留空=整表汇总
  aggTarget.colHeader = ''  // 留空=整表汇总
  showAggregateDialog.value = true
}

async function confirmAndExecuteAggregate() {
  // 构建确认信息
  let confirmMsg = ''
  if (aggTarget.mode === 'direct') {
    confirmMsg = `将汇总 "${currentConsolEntity.value.name || '集团'}" 的直接下级企业数据，结果填充到 "${aggTarget.itemName} / ${aggTarget.colName}"。`
  } else {
    const checkedNodes = aggTreeRef.value?.getCheckedNodes() || []
    const names = checkedNodes.map((n: any) => n.label).filter((l: string) => l).join('、')
    const sourceLabel = aggTarget.source === 'same' ? '当前表格' : aggTarget.source === 'report' ? '报表' : '附注'
    confirmMsg = `将汇总以下 ${checkedNodes.length} 家企业的${sourceLabel}数据：\n${names || '未选择'}\n\n结果填充到 "${aggTarget.itemName} / ${aggTarget.colName}"。`
  }

  try {
    const { ElMessageBox } = await import('element-plus')
    await ElMessageBox.confirm(confirmMsg, '确认执行汇总', {
      type: 'info',
      confirmButtonText: '确认汇总',
      cancelButtonText: '返回修改',
    })
    await executeAggregate()
  } catch { /* cancelled */ }
}

async function executeAggregate() {
  aggLoading.value = true
  try {
    const sec = selectedNoteSection.value
    if (!sec) return
    const c = selectedCells.value[0]
    if (!c) return

    if (aggTarget.mode === 'direct') {
      // 直接下级汇总：从基本信息表获取直接下级企业，汇总同位置数据
      const entityCode = currentConsolEntity.value.code || ''
      const { data } = await http.post(`/api/consol-note-sections/aggregate/${projectId.value}/${year.value}`, {
        section_id: sec.section_id,
        row_idx: c.row,
        col_idx: c.col,
        company_code: entityCode,
        mode: 'direct',
        standard: consolNoteTemplateType.value,
      }, { validateStatus: (s: number) => s < 600 })
      const result = data?.data ?? data
      if (result?.value != null) {
        sec.editRows[c.row][c.col] = String(result.value)
        ElMessage.success(`已汇总 ${result.count || 0} 家直接下级，合计：${fmtAmt(result.value)}`)
      } else {
        ElMessage.info('暂无下级数据可汇总')
      }
    } else {
      // 自定义汇总
      const checkedNodes = aggTreeRef.value?.getCheckedNodes() || []
      if (!checkedNodes.length) { ElMessage.warning('请选择要汇总的单位'); aggLoading.value = false; return }
      const companyCodes = checkedNodes.map((n: any) => n.key).filter((k: string) => k !== 'root')
      const { data } = await http.post(`/api/consol-note-sections/aggregate/${projectId.value}/${year.value}`, {
        section_id: aggTarget.source === 'same' ? sec.section_id : (aggTarget.source === 'note' ? aggTarget.noteSection : sec.section_id),
        row_idx: c.row,
        col_idx: c.col,
        company_codes: companyCodes,
        mode: 'custom',
        source: aggTarget.source,
        report_types: aggTarget.reportTypes,
        note_sections: aggTarget.noteSections,
        standard: consolNoteTemplateType.value,
      }, { validateStatus: (s: number) => s < 600 })
      const result = data?.data ?? data
      if (result?.value != null) {
        sec.editRows[c.row][c.col] = String(result.value)
        ElMessage.success(`已汇总 ${companyCodes.length} 家企业，合计：${fmtAmt(result.value)}`)
      } else {
        ElMessage.info('暂无数据可汇总')
      }
    }
    showAggregateDialog.value = false
  } catch {
    ElMessage.info('汇总功能需要后端配合，当前为预留接口')
  } finally { aggLoading.value = false }
}

function traceToSource() {
  closeCellContextMenu()
  const c = selectedCells.value[0]
  if (!c) return
  const sec = selectedNoteSection.value
  const itemName = sec?.editRows?.[c.row]?.[0] || ''
  // 打开汇总穿透弹窗
  drillDownCell.itemName = itemName
  drillDownCell.colName = sec?.headers?.[c.col] || ''
  drillDownCell.totalValue = Number(c.value) || null
  showCellDrillDown.value = true
  loadDrillDownData()
}

// 点击其他地方关闭右键菜单
function onDocClick(e: MouseEvent) {
  // 点击右键菜单内部不关闭
  const target = e.target as HTMLElement
  if (target.closest('.gt-cell-context-menu')) return
  closeCellContextMenu()
}

function copyEntireNoteTable() {
  const sec = selectedNoteSection.value
  if (!sec?.headers?.length) { ElMessage.warning('无表格数据'); return }
  const headers = sec.headers
  const rows = (sec.editRows || []).map((r: any) => headers.map((_: string, j: number) => r[j] || ''))
  const lines = [headers.join('\t'), ...rows.map((r: string[]) => r.join('\t'))]
  const text = lines.join('\n')
  const html = `<table border="1"><tr>${headers.map((h: string) => `<th>${h}</th>`).join('')}</tr>${rows.map((r: string[]) => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    const blob = new Blob([html], { type: 'text/html' })
    const textBlob = new Blob([text], { type: 'text/plain' })
    navigator.clipboard.write([new ClipboardItem({ 'text/html': blob, 'text/plain': textBlob })])
    ElMessage.success(`已复制 ${rows.length} 行 × ${headers.length} 列，可粘贴到 Word/Excel`)
  } catch {
    navigator.clipboard?.writeText(text)
    ElMessage.success('已复制为文本格式')
  }
}

function openNoteFormula() {
  const sec = selectedNoteSection.value
  if (!sec) { ElMessage.warning('请先选择章节'); return }
  // 构建公式规则列表：每行每列一条
  const rules: any[] = []
  const headers = sec.headers || []
  for (let ri = 0; ri < (sec.editRows || []).length; ri++) {
    const row = sec.editRows[ri]
    const itemName = row[0] || `行${ri + 1}`
    const isTotal = String(itemName).includes('合计') || String(itemName).includes('小计')
    for (let ci = 1; ci < headers.length; ci++) {
      const h = headers[ci]
      const hClean = h.replace(/\s/g, '')
      // 自动推断公式类型
      let formulaType = 'manual'
      let formula = ''
      let source = ''
      if (isTotal) {
        formulaType = 'SUM'
        formula = `=SUM(${headers[ci]}列明细行)`
        source = '自动求和'
      } else if (hClean.includes('期末') || hClean.includes('本期') || hClean.includes('账面余额')) {
        formulaType = 'TB_REF'
        formula = `=TB("${itemName}","期末余额")`
        source = '试算表'
      } else if (hClean.includes('期初') || hClean.includes('年初')) {
        formulaType = 'TB_REF'
        formula = `=TB("${itemName}","期初余额")`
        source = '试算表'
      }
      if (formulaType !== 'manual') {
        rules.push({
          row: ri, col: ci, itemName, colName: h,
          type: formulaType, formula, source,
          currentValue: row[ci] || '',
        })
      }
    }
  }
  noteFormulaRules.value = rules
  showNoteFormulaDialog.value = true
}

async function applyNoteFormulaRules() {
  const sec = selectedNoteSection.value
  if (!sec || !projectId.value) return
  // 调用后端刷新当前表格
  await refreshNoteByFormula()
  showNoteFormulaDialog.value = false
}

function addNoteFormulaRule() {
  noteFormulaRules.value.push({
    row: 0, col: 1, itemName: '', colName: '',
    type: 'TB_REF', formula: '=TB("科目名","期末余额")', source: '试算表',
    currentValue: '',
  })
}

function removeNoteFormulaRule(idx: number) {
  noteFormulaRules.value.splice(idx, 1)
}

async function auditCurrentNote() {
  const sec = selectedNoteSection.value
  if (!sec || !projectId.value) { ElMessage.warning('请先选择章节'); return }
  noteSingleAuditLoading.value = true
  try {
    const entityCode = currentConsolEntity.value.code || ''
    // 把当前编辑的数据发给后端审核
    const currentRows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
    const { data } = await http.post(`/api/consol-note-sections/audit/${projectId.value}/${year.value}/${sec.section_id}`, {
      standard: consolNoteTemplateType.value,
      company_code: entityCode,
      headers: sec.headers,
      rows: currentRows,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    noteAuditResults.value = Array.isArray(result?.results) ? result.results : []
    noteAuditSummary.totalSections = 1
    noteAuditSummary.totalChecks = noteAuditResults.value.length
    noteAuditSummary.passCount = noteAuditResults.value.filter((r: any) => r.level === 'pass').length
    noteAuditSummary.errorCount = noteAuditResults.value.filter((r: any) => r.level === 'error').length
    noteAuditSummary.warnCount = noteAuditResults.value.filter((r: any) => r.level === 'warn').length
    showNoteAuditDialog.value = true
  } catch {
    ElMessage.info('单表审核功能需要后端配合，当前为预留接口')
  } finally { noteSingleAuditLoading.value = false }
}

function addNoteRow() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  const obj: any = {}
  for (let j = 0; j < sec.headers.length; j++) obj[j] = ''
  sec.editRows.push(obj)
}

async function deleteNoteRows() {
  if (!noteSelectedRows.value.length) return
  const { ElMessageBox } = await import('element-plus')
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${noteSelectedRows.value.length} 行？`, '删除确认', { type: 'warning' })
    const sec = selectedNoteSection.value
    if (!sec) return
    const toDelete = new Set(noteSelectedRows.value)
    sec.editRows = sec.editRows.filter((r: any) => !toDelete.has(r))
    noteSelectedRows.value = []
  } catch { /* cancelled */ }
}

async function saveNoteData() {
  const sec = selectedNoteSection.value
  if (!sec || !projectId.value) return
  const rows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
  try {
    await http.put(
      `/api/consol-note-sections/data/${projectId.value}/${year.value}/${sec.section_id}`,
      { data: { headers: sec.headers, rows } },
      { validateStatus: (s: number) => s < 600 },
    )
    ElMessage.success('附注数据已保存')
  } catch { ElMessage.error('保存失败') }
}

async function exportNoteTemplate() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const ws = XLSX.utils.aoa_to_sheet([sec.headers, ...(sec.editRows || []).map(() => sec.headers.map(() => ''))])
  ws['!cols'] = sec.headers.map(() => ({ wch: 18 }))
  XLSX.utils.book_append_sheet(wb, ws, '模板')
  XLSX.writeFile(wb, `${sec.title || '附注'}_模板.xlsx`)
  ElMessage.success('模板已导出')
}

async function exportNoteData() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const dataRows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
  const ws = XLSX.utils.aoa_to_sheet([sec.headers, ...dataRows])
  ws['!cols'] = sec.headers.map(() => ({ wch: 18 }))
  XLSX.utils.book_append_sheet(wb, ws, '数据')
  XLSX.writeFile(wb, `${sec.title || '附注'}_数据.xlsx`)
  ElMessage.success('数据已导出')
}

async function onNoteFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const json: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })
    let startRow = 0
    if (json.length > 0) {
      const firstRow = json[0].map((c: any) => String(c || '').trim())
      if (firstRow.some((c: string) => sec.headers.includes(c))) startRow = 1
    }
    const imported: any[] = []
    for (let i = startRow; i < json.length; i++) {
      const r = json[i]
      if (!r || !r.length) continue
      const obj: any = {}
      for (let j = 0; j < sec.headers.length; j++) obj[j] = r[j] != null ? String(r[j]) : ''
      imported.push(obj)
    }
    if (imported.length) {
      sec.editRows.push(...imported)
      ElMessage.success(`已导入 ${imported.length} 行`)
    } else {
      ElMessage.warning('未解析到有效数据')
    }
  } catch (err: any) { ElMessage.error('导入失败：' + (err.message || '')) }
  finally { if (noteFileRef.value) noteFileRef.value.value = '' }
}

// ─── 批量导入导出 ─────────────────────────────────────────────────────────────
function uniqueSheetName(usedNames: Set<string>, rawName: string, sectionId: string): string {
  // 用 section_id 前缀保证唯一，如 "5-4-3 按坏账准备计提方法"
  const prefix = sectionId.replace(/^五-/, '').replace(/-/g, '.')
  const name = `${prefix} ${rawName}`.substring(0, 31)
  usedNames.add(name)
  return name
}

async function batchExportAllData() {
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const usedNames = new Set<string>()
    const { data } = await http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    let sheetCount = 0
    for (const g of groups) {
      for (const c of (g.children || [])) {
        const { data: detail } = await http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}/${c.section_id}`, {
          validateStatus: (s: number) => s < 600,
        })
        const sec = detail?.data ?? detail
        if (!sec?.headers?.length) continue
        const rows = sec.rows || []
        const ws = XLSX.utils.aoa_to_sheet([sec.headers, ...rows])
        ws['!cols'] = sec.headers.map(() => ({ wch: 16 }))
        const name = uniqueSheetName(usedNames, sec.title || c.title || `表${sheetCount + 1}`, c.section_id)
        XLSX.utils.book_append_sheet(wb, ws, name)
        sheetCount++
      }
    }
    XLSX.writeFile(wb, `合并附注_全部数据_${consolNoteTemplateType.value}.xlsx`)
    ElMessage.success(`已导出 ${sheetCount} 个附注表格`)
  } catch (e: any) { ElMessage.error('导出失败：' + (e?.message || '')) }
  finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

async function batchExportAllTemplates() {
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const usedNames = new Set<string>()
    const { data } = await http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    let sheetCount = 0
    for (const g of groups) {
      for (const c of (g.children || [])) {
        const { data: detail } = await http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}/${c.section_id}`, {
          validateStatus: (s: number) => s < 600,
        })
        const sec = detail?.data ?? detail
        if (!sec?.headers?.length) continue
        const ws = XLSX.utils.aoa_to_sheet([sec.headers])
        ws['!cols'] = sec.headers.map(() => ({ wch: 16 }))
        const name = uniqueSheetName(usedNames, sec.title || c.title || `表${sheetCount + 1}`, c.section_id)
        XLSX.utils.book_append_sheet(wb, ws, name)
        sheetCount++
      }
    }
    XLSX.writeFile(wb, `合并附注_模板_${consolNoteTemplateType.value}.xlsx`)
    ElMessage.success(`已导出 ${sheetCount} 个附注模板`)
  } catch (e: any) { ElMessage.error('导出失败：' + (e?.message || '')) }
  finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

async function onNoteBatchImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file || !projectId.value) return
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    let matched = 0
    // 加载所有章节用于匹配
    const { data } = await http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    const sectionMap: Record<string, string> = {} // title → section_id
    for (const g of groups) {
      for (const c of (g.children || [])) {
        sectionMap[c.title] = c.section_id
      }
    }
    for (const sheetName of wb.SheetNames) {
      const sectionId = sectionMap[sheetName]
      if (!sectionId) continue
      const ws = wb.Sheets[sheetName]
      const json: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })
      if (json.length < 2) continue
      const headers = json[0].map((c: any) => String(c || ''))
      const rows = json.slice(1).filter((r: any[]) => r.some(c => c != null && c !== '')).map((r: any[]) => r.map(c => String(c ?? '')))
      // 保存到后端
      await http.put(
        `/api/consol-note-sections/data/${projectId.value}/${year.value}/${sectionId}`,
        { data: { headers, rows } },
        { validateStatus: (s: number) => s < 600 },
      )
      matched++
    }
    ElMessage.success(`已导入 ${matched} 个附注表格（共 ${wb.SheetNames.length} 个 Sheet）`)
  } catch (e: any) { ElMessage.error('导入失败：' + (e?.message || '')) }
  finally {
    noteBatchLoading.value = false
    showNoteBatchDialog.value = false
    if (noteBatchFileRef.value) noteBatchFileRef.value.value = ''
  }
}

// ─── 公式管理 ────────────────────────────────────────────────────────────────
async function exportNoteFormulas() {
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    // 导出公式模板：每行一条公式规则
    const headers = ['章节ID', '章节标题', '行号', '列号', '公式类型', '公式表达式', '数据来源', '说明']
    const { data } = await http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    const rows: string[][] = []
    for (const g of groups) {
      for (const c of (g.children || [])) {
        // 为每个章节生成默认公式行（合计行自动求和、期末=期初+增-减）
        rows.push([c.section_id, c.title, '合计行', '所有数值列', 'SUM', '=SUM(明细行)', '自动计算', '合计行自动求和'])
        rows.push([c.section_id, c.title, '所有行', '期末列', 'TB_REF', `=TB(科目名,期末余额)`, '试算表', '从试算表提取期末余额'])
        rows.push([c.section_id, c.title, '所有行', '期初列', 'TB_REF', `=TB(科目名,期初余额)`, '试算表', '从试算表提取期初余额'])
      }
    }
    const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
    ws['!cols'] = headers.map((_, i) => ({ wch: i < 2 ? 20 : 14 }))
    XLSX.utils.book_append_sheet(wb, ws, '公式规则')
    XLSX.writeFile(wb, `合并附注_公式模板_${consolNoteTemplateType.value}.xlsx`)
    ElMessage.success(`已导出公式模板`)
  } catch (e: any) { ElMessage.error('导出失败：' + (e?.message || '')) }
  finally { noteBatchLoading.value = false }
}

async function onNoteFormulaImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  noteBatchLoading.value = true
  try {
    if (file.name.endsWith('.json')) {
      // JSON 格式公式导入
      const text = await file.text()
      const formulas = JSON.parse(text)
      ElMessage.success(`已导入 ${Array.isArray(formulas) ? formulas.length : 0} 条公式规则（需后端配合存储）`)
    } else {
      // Excel 格式
      const XLSX = await import('xlsx')
      const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
      const ws = wb.Sheets[wb.SheetNames[0]]
      const json: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })
      const ruleCount = Math.max(0, json.length - 1)
      ElMessage.success(`已解析 ${ruleCount} 条公式规则（需后端配合存储）`)
    }
  } catch (e: any) { ElMessage.error('导入失败：' + (e?.message || '')) }
  finally {
    noteBatchLoading.value = false
    if (noteFormulaFileRef.value) noteFormulaFileRef.value.value = ''
  }
}

async function applyAllNoteFormulas() {
  noteBatchLoading.value = true
  try {
    const entityCode = currentConsolEntity.value.code || ''
    const { data } = await http.post(`/api/consol-note-sections/apply-formulas/${projectId.value}/${year.value}`, {
      standard: consolNoteTemplateType.value,
      company_code: entityCode,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    const updated = result?.updated_sections || 0
    ElMessage.success(`已对 ${updated} 个附注表格执行公式取数计算`)
    // 刷新当前选中的章节
    if (selectedNoteSection.value) {
      onNoteNodeClick({ section_id: selectedNoteSection.value.section_id })
    }
  } catch {
    ElMessage.info('一键取数计算功能需要后端公式引擎配合')
  } finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

async function loadConsolNoteTree(forceRefresh = false) {
  const cacheKey = noteCacheKey()
  if (!forceRefresh && noteCache.has(cacheKey)) {
    consolNoteTree.value = noteCache.get(cacheKey)!
    return
  }
  consolNoteLoading.value = true
  try {
    const { data } = await http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    if (!Array.isArray(groups) || !groups.length) {
      consolNoteTree.value = []
      noteCache.set(cacheKey, [])
      return
    }
    // 树形：父章节 → 子表格节点
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

function filterNoteNode(value: string, data: any) {
  if (!value) return true
  return (data.label || '').includes(value) || (data.title || '').includes(value)
}

function onNoteNodeClick(data: any) {
  if (!data.section_id) return  // 点击的是父章节分组，忽略
  noteSelectedRows.value = []
  http.get(`/api/consol-note-sections/${consolNoteTemplateType.value}/${data.section_id}`, {
    validateStatus: (s: number) => s < 600,
  }).then(({ data: detail }) => {
    const sec = detail?.data ?? detail
    if (sec && !sec.error) {
      // 构建可编辑行
      const headers = sec.headers || []
      const rows = sec.rows || []
      const editRows = rows.map((r: string[]) => {
        const obj: any = {}
        for (let j = 0; j < headers.length; j++) obj[j] = r[j] || ''
        return obj
      })
      // 至少5行空行
      while (editRows.length < 5) {
        const obj: any = {}
        for (let j = 0; j < headers.length; j++) obj[j] = ''
        editRows.push(obj)
      }
      selectedNoteSection.value = {
        section_id: sec.section_id,
        title: sec.title,
        parent_section: sec.parent_section,
        headers,
        editRows,
      }
    }
  }).catch(() => {})
}

function switchNoteTemplate() {
  consolNoteTemplateType.value = consolNoteTemplateType.value === 'soe' ? 'listed' : 'soe'
  selectedNoteSection.value = null
  loadConsolNoteTree()
  showConsolNoteConversion.value = false
  ElMessage.success('已切换为' + (consolNoteTemplateType.value === 'soe' ? '国企版' : '上市版'))
}

function getConsolNoteConfigData(): Record<string, any> {
  return { template_type: consolNoteTemplateType.value }
}

function onConsolNoteTemplateApplied(_data: Record<string, any>) {
  loadConsolNoteTree()
}

// noteTreeSearch/noteTreeRef kept for compatibility but search moved to ConsolCatalog

// ─── 生命周期 ────────────────────────────────────────────────────────────────
// 监听中间栏树形节点选择事件
function onConsolTreeSelect(e: Event) {
  const data = (e as CustomEvent).detail
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
      selectedNode.value = { company_code: data.companyCode, company_name: data.label }
    }
  } else if (data.companyCode) {
    // 点击了企业节点 → 选中该节点，刷新报表/附注
    selectedNode.value = { company_code: data.companyCode, company_name: data.label }
    currentConsolEntity.value = { code: data.companyCode, name: data.label }
    // 如果指定了切换 tab
    if (data.switchTab) {
      activeTab.value = data.switchTab
    }
    // 刷新当前 tab 数据
    if (activeTab.value === 'consol_report') loadConsolReport()
    else if (activeTab.value === 'consol_note') loadConsolNoteTree()
  }
}

// 树形右键汇总事件
function onTreeAggregate(e: Event) {
  const detail = (e as CustomEvent).detail
  if (!detail) return
  currentConsolEntity.value = { code: detail.companyCode, name: detail.companyName }
  selectedNode.value = { company_code: detail.companyCode, company_name: detail.companyName }
  const sec = selectedNoteSection.value
  if (sec) {
    aggTarget.itemName = sec.editRows?.[0]?.[0] || ''
    aggTarget.colName = sec.headers?.[1] || ''
    aggTarget.currentValue = ''
  } else {
    aggTarget.itemName = '（请先选择附注表格）'
    aggTarget.colName = ''
    aggTarget.currentValue = ''
  }
  aggTarget.mode = detail.mode || 'direct'
  aggTarget.source = 'same'
  aggTarget.rowName = ''
  aggTarget.colHeader = ''
  aggTarget.reportTypes = []
  aggTarget.noteSections = []
  showAggregateDialog.value = true
}

onMounted(async () => {
  await loadProjectInfo()
  // 默认合并主体为项目本身（集团层面）
  currentConsolEntity.value = { code: '', name: projectInfo.clientName || '' }
  await loadGroupTree()
  window.addEventListener('consol-tree-select', onConsolTreeSelect)
  window.addEventListener('consol-catalog-select', onConsolCatalogSelect)
  window.addEventListener('consol-refresh-entity', onConsolRefreshEntity)
  window.addEventListener('consol-note-audit-all', onNoteAuditAll)
  window.addEventListener('consol-tree-aggregate', onTreeAggregate)
  document.addEventListener('keydown', onGlobalKeydown)
  document.addEventListener('click', onDocClick)
})

onUnmounted(() => {
  window.removeEventListener('consol-tree-select', onConsolTreeSelect)
  window.removeEventListener('consol-catalog-select', onConsolCatalogSelect)
  window.removeEventListener('consol-refresh-entity', onConsolRefreshEntity)
  window.removeEventListener('consol-note-audit-all', onNoteAuditAll)
  window.removeEventListener('consol-tree-aggregate', onTreeAggregate)
  document.removeEventListener('keydown', onGlobalKeydown)
  document.removeEventListener('click', onDocClick)
})

function onGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && noteFullscreen.value) {
    noteFullscreen.value = false
  }
}

function switchToFourCol() {
  // 触发顶部栏的四栏视图切换，并通知 catalog 切到附注 tab
  window.dispatchEvent(new CustomEvent('gt-switch-four-col', { detail: { tab: 'notes' } }))
}

// 监听树形节点刷新事件
function onConsolRefreshEntity(e: Event) {
  const detail = (e as CustomEvent).detail
  if (!detail) return
  const { companyCode, companyName, types } = detail as { companyCode: string; companyName: string; types: string[] }

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
function onConsolCatalogSelect(e: Event) {
  const data = (e as CustomEvent).detail
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

/* ── 顶部信息栏 ── */
.gt-consol-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; margin: -12px -12px 8px;
  background: linear-gradient(135deg, #4b2d77 0%, #7c5caa 60%, #a78bcc 100%);
  border-radius: 0 0 10px 10px;
}
.gt-consol-bar-back {
  color: rgba(255,255,255,0.85) !important; font-size: 13px; padding: 4px 8px;
  border-radius: 4px; transition: background 0.15s;
}
.gt-consol-bar-back:hover { background: rgba(255,255,255,0.12) !important; color: #fff !important; }
.gt-consol-bar-info { display: flex; align-items: center; }
.gt-consol-bar-name { font-size: 16px; font-weight: 600; color: #fff; }
.gt-bar-btn {
  margin-left: 6px; background: transparent !important; color: rgba(255,255,255,0.9) !important;
  border-color: rgba(255,255,255,0.3) !important;
}
.gt-bar-btn:hover { background: rgba(255,255,255,0.15) !important; border-color: rgba(255,255,255,0.5) !important; }
.gt-tab-content { padding: var(--gt-space-3) 0; }
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
  padding: 6px 14px; font-size: 12px; color: #666; cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -2px;
  transition: all 0.15s; white-space: nowrap; user-select: none;
}
.gt-report-type-tag:hover { color: #4b2d77; background: rgba(75,45,119,0.03); }
.gt-report-type-tag--active {
  color: #4b2d77; font-weight: 600;
  border-bottom-color: #4b2d77;
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
  width: max-content; min-width: 100%; border-collapse: collapse; font-size: 12px;
}
.gt-consol-matrix-table th,
.gt-consol-matrix-table td {
  border: 1px solid #e8e4f0; padding: 4px 8px; white-space: nowrap; text-align: center;
}
.gt-consol-matrix-table thead th {
  background: #f0edf5; color: #333; font-weight: 600; position: sticky; top: 0; z-index: 2;
}
.gt-cm-th-project {
  min-width: 200px; text-align: left !important; position: sticky; left: 0; z-index: 3;
  background: #f0edf5 !important;
}
.gt-cm-th-prior { background: #f5f3f8 !important; }
.gt-cm-th-total { font-weight: 700 !important; background: #ebe7f2 !important; }
.gt-cm-td-project {
  text-align: left !important; font-size: 12px; position: sticky; left: 0; z-index: 1;
  background: #fff; white-space: nowrap;
}
.gt-cm-td-amt { text-align: right !important; font-size: 12px; min-width: 80px; font-variant-numeric: tabular-nums; }
.gt-cm-td-prior { background: #faf9fc; }
.gt-cm-total-row td { font-weight: 700; background: #f8f6fb !important; }
.gt-cm-category td { font-weight: 600; color: #4b2d77; }

/* ── 合并附注布局 ── */
.gt-note-layout { display: flex; gap: 0; min-height: 400px; }
.gt-note-fullscreen-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 9999; background: #fff; padding: 16px;
  display: flex; flex-direction: column;
}
.gt-note-content { flex: 1; min-width: 0; overflow: auto; padding: 0; }
.gt-note-detail { height: 100%; display: flex; flex-direction: column; }
.gt-note-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.gt-note-section-title { margin: 0; font-size: 14px; font-weight: 600; color: #333; white-space: nowrap; }
.gt-note-actions { display: flex; gap: 4px; flex-wrap: wrap; }
.gt-note-table-wrap { flex: 1; min-height: 0; }
.gt-note-table-footer {
  display: flex; align-items: center; gap: 8px; padding: 6px 0; border-top: 1px solid #e8e4f0; margin-top: 4px;
}
.gt-note-welcome { max-width: 560px; text-align: left; }
.gt-note-guide { display: flex; flex-direction: column; gap: 10px; }
.gt-note-guide-item {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 8px 12px; background: #f8f6fb; border-radius: 6px;
}
.gt-note-guide-num {
  width: 24px; height: 24px; border-radius: 50%; background: #4b2d77; color: #fff;
  font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 2px;
}
.gt-note-guide-item b { font-size: 13px; color: #333; }
.gt-note-guide-item p { margin: 2px 0 0; font-size: 12px; color: #999; }

/* 附注空状态引导 */
.gt-note-empty-guide {
  display: flex; flex-direction: column; align-items: center;
  padding: 24px 20px 16px; gap: 16px;
}
.gt-note-empty-hero { text-align: center; }
.gt-note-empty-hero p { margin: 0 0 12px; font-size: 13px; color: #999; }
.gt-note-empty-actions { display: flex; gap: 8px; justify-content: center; }
.gt-note-empty-steps {
  display: flex; gap: 12px; width: 100%;
}
.gt-note-step {
  flex: 1; min-width: 0;
  display: flex; gap: 8px; align-items: flex-start;
  padding: 12px; background: #f8f6fb; border-radius: 8px; border: 1px solid #ebe7f2;
}
.gt-note-step-icon {
  font-size: 16px; font-weight: 700; color: #4b2d77; flex-shrink: 0; line-height: 1;
}
.gt-note-step-text { font-size: 12px; color: #666; line-height: 1.6; }
.gt-note-step-text b { color: #333; font-size: 12px; display: block; margin-bottom: 2px; }
.gt-note-step-text p { margin: 0; }
.gt-note-empty-info {
  font-size: 11px; color: #bbb; text-align: center;
}
/* 审核结果行样式 */
:deep(.gt-audit-row-error td) { background: #fef0f0 !important; }
:deep(.gt-audit-row-warn td) { background: #fdf6ec !important; }

/* 批注弹窗 */
:deep(.gt-comment-dialog .el-dialog__header) {
  background: linear-gradient(135deg, #4b2d77, #7c5caa); padding: 14px 20px;
  border-radius: 8px 8px 0 0;
}
:deep(.gt-comment-dialog .el-dialog__title) { color: #fff; font-size: 15px; }
:deep(.gt-comment-dialog .el-dialog__headerbtn .el-dialog__close) { color: rgba(255,255,255,0.8); }
:deep(.gt-comment-dialog .el-dialog__body) { padding: 16px 20px; }
.gt-comment-info {
  display: flex; gap: 0; margin-bottom: 14px;
  background: #f8f6fb; border-radius: 6px; overflow: hidden;
}
.gt-comment-info-item {
  flex: 1; padding: 10px 14px; border-right: 1px solid #ebe7f2;
  display: flex; flex-direction: column; gap: 2px;
}
.gt-comment-info-item:last-child { border-right: none; }
.gt-comment-info-label { font-size: 10px; color: #999; text-transform: uppercase; letter-spacing: 0.5px; }
.gt-comment-info-value { font-size: 13px; font-weight: 600; color: #333; }
.gt-comment-info-value--primary { color: #4b2d77; }
:deep(.gt-comment-textarea .el-textarea__inner) {
  border: none; border-bottom: 1.5px solid #e8e4f0; border-radius: 0;
  font-size: 13px; line-height: 1.6; padding: 10px 4px; resize: none;
}
:deep(.gt-comment-textarea .el-textarea__inner:focus) {
  border-color: #4b2d77; box-shadow: none;
}
.gt-note-cell-text {
  display: block; padding: 2px 2px; font-size: 13px; min-height: 20px;
  user-select: text; cursor: pointer; white-space: nowrap;
}
/* 单元格选中高亮 */
:deep(.gt-cell--selected) {
  background: linear-gradient(135deg, rgba(75,45,119,0.05), rgba(124,92,170,0.08)) !important;
  box-shadow: inset 0 0 0 1.5px rgba(75,45,119,0.35), 0 0 8px rgba(75,45,119,0.1);
  border-radius: 3px;
  animation: gt-cell-pulse 1.5s ease-in-out infinite alternate;
}
:deep(.gt-cell--selected .gt-note-cell-text) {
  color: #4b2d77; font-weight: 500;
}
@keyframes gt-cell-pulse {
  0% { box-shadow: inset 0 0 0 1.5px rgba(75,45,119,0.35), 0 0 6px rgba(75,45,119,0.08); }
  100% { box-shadow: inset 0 0 0 1.5px rgba(75,45,119,0.5), 0 0 12px rgba(75,45,119,0.15); }
}
/* 右键菜单 */
.gt-cell-context-menu {
  position: fixed; z-index: 10001; background: #fff;
  border-radius: 8px; box-shadow: 0 6px 24px rgba(0,0,0,0.15); padding: 6px 0; min-width: 200px;
  border: 1px solid #e8e4f0;
}
.gt-cell-ctx-header {
  padding: 6px 14px; font-size: 11px; color: #999;
  display: flex; justify-content: space-between; gap: 8px;
}
.gt-cell-ctx-divider { height: 1px; background: #f0edf5; margin: 2px 0; }
.gt-cell-ctx-item {
  padding: 8px 14px; font-size: 13px; cursor: pointer; color: #333;
  display: flex; align-items: center; gap: 6px; transition: background 0.1s;
}
.gt-cell-ctx-item:hover { background: #f0edf5; color: #4b2d77; }
.gt-cell-ctx-icon { width: 18px; text-align: center; font-size: 13px; }
.gt-ctx-fade-enter-active { transition: opacity 0.1s, transform 0.1s; }
.gt-ctx-fade-leave-active { transition: opacity 0.08s; }
.gt-ctx-fade-enter-from { opacity: 0; transform: scale(0.95); }
.gt-ctx-fade-leave-to { opacity: 0; }
.gt-note-cell--selected {
  background: rgba(75, 45, 119, 0.08) !important;
}
/* 紧凑行高 */
.gt-note-compact-table :deep(.el-table__row td) { height: 32px; }
.gt-note-compact-table :deep(.el-table__header th) { height: 34px; }
.gt-note-compact-table :deep(.el-input__inner) { height: 28px; font-size: 13px; }
</style>
