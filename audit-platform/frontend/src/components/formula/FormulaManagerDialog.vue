<template>
  <el-dialog
    v-model="visible"
    title="ƒx 公式管理中心"
    fullscreen
    append-to-body
    destroy-on-close
    class="gt-fm-dialog"
  >
    <div class="gt-fm-container">
      <!-- 左侧：树形导航 -->
      <div class="gt-fm-sidebar">
        <div class="gt-fm-sidebar-title">数据源</div>
        <el-tree
          ref="fmTreeRef"
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="key"
          highlight-current
          :default-expanded-keys="expandedKeys"
          :expand-on-click-node="false"
          draggable
          :allow-drop="allowTreeDrop"
          @node-click="onTreeNodeClick"
          class="gt-fm-tree"
        >
          <template #default="{ node, data }">
            <span class="gt-fm-tree-node">
              <span>{{ data.icon }} {{ node.label }}<span v-if="data._isExternalLink" style="color: var(--gt-color-info); font-size: 10px; margin-left: 4px;">↗</span></span>
              <el-badge v-if="data.count" :value="data.count" type="info" :max="999" />
            </span>
          </template>
        </el-tree>
      </div>

      <!-- 右侧：公式配置 -->
      <div class="gt-fm-main">
        <!-- 当前选中的路径 + 模板类型切换 -->
        <div class="gt-fm-breadcrumb">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-tag size="small" type="info" effect="plain" style="font-weight: 600;">{{ scopeLabel }}</el-tag>
            <el-tag size="small" type="success" effect="plain" title="当前页/当前节点已加载的公式数">
              {{ props.wpId ? (selectedWpSheetCode ? '本页公式' : '全册公式') : '本域公式' }}
              {{ props.wpId ? wpFormulaRows.length : scopeFormulas.length }}
            </el-tag>
            <el-select v-model="fmTemplateType" size="small" style="width: 100px;" @change="onFmTemplateChange">
              <el-option label="国企版" value="soe" />
              <el-option label="上市版" value="listed" />
            </el-select>
            <span style="color: var(--gt-color-text-placeholder);">|</span>
            <span style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">{{ selectedPath }}</span>
            <el-tag
              v-if="activeReportLevelLabel"
              size="small"
              :type="activeReportLevelLabel === '项目级' ? 'success' : 'info'"
              effect="plain"
              :title="activeReportLevelLabel === '项目级'
                ? '本页公式取自项目级配置（project:{id}），修改只影响本项目'
                : '本页公式取自模板级预设，修改会影响所有使用同一适用准则的项目'"
            >
              {{ activeReportLevelLabel }}
            </el-tag>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <el-button size="small" @click="showFormulaDashboard = true">📊 公式看板</el-button>
            <el-button size="small" @click="onOpenGlobalScopeOverview">🌐 全局公式</el-button>
            <SharedTemplatePicker
              config-type="formula_config"
              :project-id="projectId"
              :get-config-data="getFormulaConfigData"
              @applied="onTemplateApplied"
            />
            <el-button
              v-if="lastTemplateUndo"
              size="small"
              type="warning"
              plain
              :loading="applying"
              @click="onUndoTemplateApply"
            >
              ↩ 撤销引用（{{ lastTemplateUndo.entries.length }}）
            </el-button>
            <el-button size="small" @click="onImportPresetFormulas" :loading="loadingData">📥 导入预设</el-button>
            <el-button size="small" @click="onExportFormulaTemplate">📤 导出模板</el-button>
            <el-button size="small" @click="showFormulaImport = true">📥 Excel导入</el-button>
            <el-button size="small" @click="onAddFormulaRow">+ 新增公式</el-button>
            <el-button size="small" @click="onSaveAllFormulas" :loading="applying">💾 保存</el-button>
            <el-button size="small" type="primary" class="gt-fm-apply-btn" @click="onApplyFormulas" :loading="applying">⚡ 应用自动运算</el-button>
          </div>
        </div>

        <!-- 分类 Tab -->
        <!-- Sprint 5.10: 健康度卡片 + URI 搜索 -->
        <div class="gt-fm-health-bar">
          <div class="gt-fm-health-card">
            <span class="gt-fm-health-label">健康度</span>
            <span class="gt-fm-health-value" :style="{ color: healthPercent >= 80 ? 'var(--gt-color-success)' : healthPercent >= 50 ? 'var(--gt-color-wheat)' : 'var(--gt-color-danger)' }">
              {{ healthPercent }}%
            </span>
            <span class="gt-fm-health-desc">{{ healthDesc }}</span>
          </div>
          <el-input
            v-model="uriSearchQuery"
            size="small"
            placeholder="按 URI 搜索公式..."
            clearable
            style="width: 260px;"
            prefix-icon="Search"
          />
        </div>

        <el-tabs v-model="activeCategory" size="small" style="margin-bottom: 8px;">
          <el-tab-pane name="all">
            <template #label>全部 ({{ currentRows.length }})</template>
          </el-tab-pane>
          <el-tab-pane name="auto_calc">
            <template #label>⚡ 自动运算 ({{ categoryCounts.auto_calc }})</template>
          </el-tab-pane>
          <el-tab-pane name="logic_check">
            <template #label>🔍 逻辑审核 ({{ categoryCounts.logic_check }})</template>
          </el-tab-pane>
          <el-tab-pane name="reasonability">
            <template #label>💡 提示合理性 ({{ categoryCounts.reasonability }})</template>
          </el-tab-pane>
          <el-tab-pane name="no_formula">
            <template #label>⬜ 未配置 ({{ currentRows.filter(r => !r.formula && _rowNeedsFormula(r)).length }})</template>
          </el-tab-pane>
          <!-- E1 Sprint 2 Task 2.34: 用户自定义公式 Tab -->
          <el-tab-pane name="user_formulas">
            <template #label>✏️ 用户自定义 ({{ userFormulasList.length }})</template>
            <div class="gt-fm-user-formulas">
              <el-alert v-if="userFormulaError" :title="userFormulaError" type="error" :closable="false" show-icon />
              <el-alert type="info" :closable="false" show-icon class="gt-fm-user-alert">
                <span>蓝色背景 = 系统预设公式（来自 prefill_formula_mapping.json）；绿色背景 = 用户自定义公式（覆盖系统预设可恢复）</span>
              </el-alert>
              <el-table
                :data="userFormulasList"
                size="small"
                border
                max-height="calc(100vh - 360px)"
                :row-class-name="userFormulaRowClass"
              >
                <el-table-column label="单元格" prop="cell_key" width="180">
                  <template #default="{ row }">
                    <span class="gt-fm-mono">{{ row.cell_key }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="公式" min-width="260">
                  <template #default="{ row }">
                    <code class="gt-fm-mono">{{ row.formula }}</code>
                  </template>
                </el-table-column>
                <el-table-column label="类型" width="120">
                  <template #default="{ row }">
                    <el-tag :type="row.is_preset_override ? 'warning' : 'success'" size="small">
                      {{ row.is_preset_override ? '已修改预设' : '用户新增' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="200">
                  <template #default="{ row }">
                    <el-button
                      v-if="row.is_preset_override"
                      size="small"
                      type="warning"
                      text
                      @click="onRestorePresetFormula(row)"
                    >↺ 恢复预设</el-button>
                    <el-button size="small" type="danger" text @click="onDeleteUserFormula(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>
          <!-- P2-3: 公式变更历史 Tab -->
          <el-tab-pane name="history">
            <template #label>📜 历史</template>
            <FormulaHistoryTab
              v-if="activeCategory === 'history' && projectId"
              :project-id="projectId"
              :year="year || new Date().getFullYear()"
              @rollback-applied="onHistoryRollbackApplied"
            />
          </el-tab-pane>
        </el-tabs>

        <!-- 批量操作栏 -->
        <div v-if="selectedRows.length > 0 && !isCrossCheckMode" class="gt-fm-batch-bar">
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">已选 <b>{{ selectedRows.length }}</b> 条</span>
          <el-button size="small" @click="onBatchApplyCategory('auto_calc')">⚡ 标记为自动运算</el-button>
          <el-button size="small" @click="onBatchApplyCategory('logic_check')">🔍 标记为逻辑审核</el-button>
          <el-button size="small" @click="onBatchApplyCategory('reasonability')">💡 标记为合理性</el-button>
          <el-button size="small" style="color: var(--gt-color-text-tertiary);" @click="onBatchClearFormula">清除公式</el-button>
          <el-button size="small" style="color: var(--gt-color-text-tertiary);" @click="selectedRows = []">取消选择</el-button>
        </div>

        <!-- 公式表格（报表/附注/底稿） -->
        <el-alert v-if="wpFormulaError" :title="wpFormulaError" type="error" :closable="false" show-icon />
        <el-alert v-if="wpSheetLocateMiss" :title="wpSheetLocateMiss" type="warning" :closable="false" show-icon />
        <el-table v-if="!isCrossCheckMode && !['user_formulas', 'history'].includes(activeCategory)" v-loading="wpFormulaLoading" ref="formulaTableRef" class="gt-fm-main-table" :data="filteredRows" size="small" border max-height="calc(100vh - 300px)" style="width: 100%"
          :header-cell-style="{ background: '#edf3f9', fontSize: '12px', whiteSpace: 'nowrap' }"
          :row-class-name="getRowClassName"
          @selection-change="onSelectionChange"
          @row-click="onRowClick"
          highlight-current-row>
          <el-table-column type="selection" width="40" />
          <el-table-column prop="row_code" label="行次" width="90">
            <template #default="{ row }">
              <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); white-space: nowrap;">{{ row.row_code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="row_name" label="项目" min-width="180" show-overflow-tooltip />
          <el-table-column label="公式" min-width="260">
            <template #default="{ row }">
              <el-input v-if="editingId === row.id" v-model="editFormula" size="small" placeholder="如 TB('1001','期末余额') 或 ROW('BS-001')+ROW('BS-002')" />
              <code v-else-if="row.formula" @dblclick="startEdit(row)" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular); word-break: break-all; cursor: pointer;" :title="'双击编辑公式'">{{ row.formula }}</code>
              <span v-else @click="startEdit(row)" style="color: var(--gt-color-text-placeholder); cursor: pointer; font-size: var(--gt-font-size-xs); border: 1px dashed var(--gt-color-border-light); padding: 2px 8px; border-radius: 4px;" title="点击添加公式">
                + 点击添加公式
              </span>
            </template>
          </el-table-column>
          <el-table-column label="分类" width="110" align="center">
            <template #default="{ row }">
              <el-select v-if="editingId === row.id" v-model="editCategory" size="small" style="width: 95px">
                <el-option label="自动运算" value="auto_calc" />
                <el-option label="逻辑审核" value="logic_check" />
                <el-option label="合理性" value="reasonability" />
              </el-select>
              <el-tag v-else :type="(categoryTagType(row.formula_category)) || undefined" size="small">
                {{ categoryLabel(row.formula_category) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <el-input v-if="editingId === row.id" v-model="editDescription" size="small" />
              <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary)">{{ row.formula_description || '' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计算值" width="110" align="right">
            <template #default="{ row }">
              <el-tooltip v-if="formulaResults[row.row_code || row.id]?.trace?.length" placement="left" :show-after="300">
                <template #content>
                  <div style="max-width:400px;font-size: var(--gt-font-size-xs);line-height:1.6">
                    <div v-for="(t, ti) in formulaResults[row.row_code || row.id]?.trace" :key="ti" style="border-bottom:1px solid rgba(255,255,255,0.1);padding:2px 0">
                      <span v-if="t.type">{{ t.type }}({{ t.name || t.code || t.range || '' }}) = {{ t.value || t.error }}</span>
                      <span v-else-if="t.op">{{ t.left }} {{ t.op }} {{ t.right }} = {{ t.result }}</span>
                    </div>
                  </div>
                </template>
                <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-primary);font-weight:600;cursor:help">
                  {{ typeof formulaResults[row.row_code || row.id]?.value === 'number' ? fmtAmount(formulaResults[row.row_code || row.id]!.value!) : '-' }}
                </span>
              </el-tooltip>
              <span v-else style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-placeholder)">—</span>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="70" align="center">
            <template #default="{ row }">
              <span v-if="isPresetFormula(row)" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-teal); background: var(--gt-bg-info); padding: 1px 6px; border-radius: 3px;">预设</span>
              <span v-else-if="row.formula" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">自定义</span>
            </template>
          </el-table-column>
          <el-table-column label="引用方" width="70" align="center">
            <template #default="{ row }">
              <el-badge v-if="row._ref_count > 0" :value="row._ref_count" :max="99" type="info" />
              <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">0</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button v-if="editingId !== row.id" size="small" link type="primary" @click.stop="startEdit(row)">编辑</el-button>
              <el-button v-else size="small" link @click.stop="saveEdit(row)" style="color: var(--gt-color-success);">保存</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="gt-fm-footer">
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">共 {{ currentRows.length }} 行，{{ currentRows.filter(r => r.formula).length }} 个公式{{ Object.values(formulaResults).filter(r => r.value != null).length ? `，${Object.values(formulaResults).filter(r => r.value != null).length} 个已计算` : '' }}</span>
        </div>

        <!-- 表间审核模式 -->
        <div v-if="isCrossCheckMode" style="flex: 1;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <span style="font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary);">{{ selectedPath }}</span>
            <el-button size="small" type="primary" @click="onAddCrossRule">+ 新增规则</el-button>
          </div>
          <el-table :data="crossCheckRulesForCurrent" size="small" border style="width: 100%;"
            max-height="calc(100vh - 300px)"
            :header-cell-style="{ background: '#edf3f9', fontSize: '12px', whiteSpace: 'nowrap' }">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column label="规则名称" min-width="200">
              <template #default="{ row }">
                <span style="font-size: var(--gt-font-size-xs);">{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="左侧（源）" min-width="180">
              <template #default="{ row }">
                <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ row.left_ref || '—' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="关系" width="60" align="center">
              <template #default><span style="font-size: var(--gt-font-size-sm);">=</span></template>
            </el-table-column>
            <el-table-column label="右侧（目标）" min-width="180">
              <template #default="{ row }">
                <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ row.right_ref || '—' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="center">
              <template #default="{ row, $index }">
                <div style="display: flex; gap: 4px; justify-content: center;">
                  <el-button size="small" link type="primary" @click="onEditCrossRule(row, $index)">编辑</el-button>
                  <el-button size="small" link style="color: var(--gt-color-text-tertiary);" @click="onRemoveCrossRule($index)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 8px; text-align: right; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
            {{ crossCheckRulesForCurrent.length }} 条规则
          </div>

          <!-- 表间审核规则编辑弹窗 -->
          <el-dialog
            v-model="showCrossRuleDialog"
            :title="crossRuleDialogTitle"
            width="640px"
            append-to-body
            destroy-on-close
          >
            <el-form :model="crossRuleForm" label-width="100px" label-position="top" style="padding: 0 10px;">
              <el-form-item label="规则名称" required>
                <el-input v-model="crossRuleForm.label" placeholder="如：BS货币资金 = 附注货币资金合计" />
              </el-form-item>
              <el-form-item label="左侧（源）" required>
                <el-input v-model="crossRuleForm.left_ref" placeholder="报表行次引用，如 REPORT('BS-002','期末')">
                  <template #prepend>源</template>
                </el-input>
                <div style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 4px;">
                  语法：REPORT('行次','字段') 或 ROW('行次')。示例：REPORT('BS-002','期末')
                </div>
              </el-form-item>
              <el-form-item label="关系运算符">
                <el-select v-model="crossRuleForm.operator" style="width: 120px;">
                  <el-option label="=" value="=" />
                  <el-option label="≤" value="<=" />
                  <el-option label="≥" value=">=" />
                </el-select>
              </el-form-item>
              <el-form-item label="右侧（目标）" required>
                <el-input v-model="crossRuleForm.right_ref" placeholder="附注/底稿引用，如 NOTE('货币资金','合计') 或 WP('E1','E1-1','审定数')">
                  <template #prepend>目标</template>
                </el-input>
                <div style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 4px;">
                  语法：NOTE('章节','字段') / WP('底稿','sheet','坐标') / TB('科目','字段')
                </div>
              </el-form-item>
              <el-form-item label="说明（选填）">
                <el-input v-model="crossRuleForm.description" type="textarea" :autosize="{ minRows: 2 }" placeholder="描述该规则的业务含义" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="showCrossRuleDialog = false">取消</el-button>
              <el-button type="primary" @click="onSaveCrossRule" :disabled="!crossRuleForm.label || !crossRuleForm.left_ref || !crossRuleForm.right_ref">确认保存</el-button>
            </template>
          </el-dialog>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>

    <!-- 公式看板弹窗 -->
    <el-dialog
      v-model="showFormulaDashboard"
      title="📊 公式看板 — 全局审核公式总览"
      width="95%"
      top="2vh"
      append-to-body
      destroy-on-close
      class="gt-fm-dashboard-dialog"
    >
      <div style="margin-bottom: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <el-input v-model="dashboardSearch" size="small" placeholder="搜索公式/行次/说明/域..." clearable style="width: 220px;" />
        <el-select v-model="dashboardGroupBy" size="small" style="width: 130px;">
          <el-option label="按域" value="domain" />
          <el-option label="按层级" value="level" />
          <el-option label="按报表类型" value="report_type" />
          <el-option label="按公式分类" value="category" />
          <el-option label="按数据源" value="source" />
          <el-option label="全部平铺" value="flat" />
        </el-select>
        <el-select v-model="dashboardFilterDomain" size="small" style="width: 140px;" clearable placeholder="筛选域">
          <el-option v-for="d in dashboardDomainOptions" :key="d.value" :label="`${d.label}（${d.count}）`" :value="d.value" />
        </el-select>
        <el-select v-model="dashboardFilterLevel" size="small" style="width: 120px;" clearable placeholder="筛选层级">
          <el-option label="模板预设" value="模板预设" />
          <el-option label="项目级" value="项目级" />
        </el-select>
        <el-select v-model="dashboardFilterCategory" size="small" style="width: 130px;" clearable placeholder="筛选分类">
          <el-option v-for="c in dashboardCategoryOptions" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-select v-model="dashboardFilterCategorized" size="small" style="width: 140px;" clearable placeholder="分类健康度">
          <el-option :label="`已分类（${dashboardCategorizedCount.yes}）`" value="yes" />
          <el-option :label="`未分类（${dashboardCategorizedCount.no}）`" value="no" />
        </el-select>
        <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: auto;">
          共 {{ dashboardFilteredRows.length }} / {{ allFormulaRows.length }} 条公式
          <template v-if="dashboardCategorizedCount.no">
            · 未分类 {{ dashboardCategorizedCount.no }} 条
          </template>
        </span>
      </div>

      <el-alert
        v-if="!dashboardLoading && !allFormulaRows.length"
        type="warning"
        :closable="false"
        show-icon
        title="未取到任何公式"
        :description="dashboardCoverageText"
        style="margin-bottom: 10px;"
      />
      <div v-else-if="!dashboardLoading" style="margin-bottom: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
        覆盖：{{ dashboardCoverageText }}
      </div>

      <!-- 分组展示 -->
      <div v-if="dashboardGroupBy !== 'flat'" style="max-height: 80vh; overflow-y: auto;">
        <div v-for="group in dashboardGroupedData" :key="group.key" style="margin-bottom: 12px;">
          <div class="gt-fm-dash-group-title" @click="group._open = !group._open">
            {{ group._open ? '▼' : '▶' }} {{ group.label }}
            <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 6px;">{{ group.rows.length }} 条</span>
          </div>
          <el-table v-show="group._open" :data="group.rows" size="small" border style="width: 100%;"
            :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
            <el-table-column prop="row_code" label="行次" width="90" />
            <el-table-column prop="row_name" label="项目" min-width="150" show-overflow-tooltip />
            <el-table-column prop="formula" label="公式" min-width="240" show-overflow-tooltip>
              <template #default="{ row }">
                <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular);">{{ row.formula }}</code>
              </template>
            </el-table-column>
            <el-table-column label="分类" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="(categoryTagType(row.formula_category)) || undefined" size="small">{{ categoryLabel(row.formula_category) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="formula_description" label="说明" min-width="140" show-overflow-tooltip />
            <el-table-column label="当前值" width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.current_period_amount != null" style="font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-primary-dark); font-variant-numeric: tabular-nums;">
                  {{ prefs.fmt(row.current_period_amount) }}
                </span>
                <span v-else style="color: var(--gt-color-text-placeholder);">-</span>
              </template>
            </el-table-column>
            <el-table-column label="域" width="110" align="center">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ row._domainLabel }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="来源" width="90" align="center">
              <template #default="{ row }">
                <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">{{ row._source_type || '报表' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="86" align="center">
              <template #default="{ row }">
                <el-button v-if="row._editable" size="small" link type="primary" @click="onDashboardEdit(row)">编辑</el-button>
                <el-button v-else size="small" link type="primary" @click="onDashboardLocate(row)">定位</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 平铺展示 -->
      <el-table v-else :data="dashboardFilteredRows" size="small" border max-height="80vh" style="width: 100%;"
        :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
        <el-table-column prop="row_code" label="行次" width="90" />
        <el-table-column prop="row_name" label="项目" min-width="150" show-overflow-tooltip />
        <el-table-column prop="formula" label="公式" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular);">{{ row.formula }}</code>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="(categoryTagType(row.formula_category)) || undefined" size="small">{{ categoryLabel(row.formula_category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="formula_description" label="说明" min-width="140" show-overflow-tooltip />
        <el-table-column label="域" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row._domainLabel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="_level" label="层级" width="86" align="center" />
        <el-table-column prop="_report_type_label" label="报表" width="100" />
        <el-table-column label="操作" width="86" align="center">
          <template #default="{ row }">
            <el-button v-if="row._editable" size="small" link type="primary" @click="onDashboardEdit(row)">编辑</el-button>
            <el-button v-else size="small" link type="primary" @click="onDashboardLocate(row)">定位</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="showFormulaDashboard = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 公式编辑弹窗 -->
    <FormulaEditDialog
      v-model="showFormulaEdit"
      :row="editingRow"
      :source-rows="currentRows"
      :applicable-standard="`${fmTemplateType}_standalone`"
      :project-id="props.projectId"
      :year="props.year"
      @save="onFormulaEditSave"
    />

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showFormulaImport"
      import-type="formula"
      :project-id="props.projectId"
      :year="props.year"
      @imported="onFormulaFileImported"
    />

    <!-- 全局公式总览弹窗（Req 24.3：跨全部 7 类作用域取并集） -->
    <el-dialog
      v-model="showGlobalScopeOverview"
      title="🌐 全局公式管理 — 跨作用域总览"
      width="88%"
      top="3vh"
      append-to-body
      destroy-on-close
      class="gt-fm-global-scope"
    >
      <div style="margin-bottom: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
        本页统计的是<strong>项目级公式</strong>（存储于 wp_formula，按底稿编码派生 7 类作用域），共 {{ scopeCatalog.totalCount.value }} 条。各作用域公式集互不串扰。
      </div>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="报表 / 附注预设是模板级，不计入本页统计"
        description="报表预设存于 report_config（按适用准则共用，报表引擎直接消费），附注校验预设存于附注预设集；两者不会被复制进项目。要查看或修改它们，用下面的按钮跳到对应节点，或打开「📊 公式看板」按域总览。"
        style="margin-bottom: 10px;"
      />
      <div style="margin-bottom: 10px; display: flex; gap: 8px; flex-wrap: wrap;">
        <el-button size="small" plain @click="onGoToReportPresets">📄 查看报表预设（模板级）</el-button>
        <el-button size="small" plain @click="onGoToNotePresets">📝 查看附注预设（模板级）</el-button>
        <el-button size="small" plain @click="onOpenDashboardFromGlobal">📊 打开公式看板</el-button>
      </div>

      <!-- 项目级 vs 主模板差异（复用 report_config_baseline 三端点） -->
      <div class="gt-fm-master-diff">
        <div class="gt-fm-master-diff__head">
          <span class="gt-fm-master-diff__title">项目级 ↔ 主模板差异</span>
          <el-tag v-if="masterDiffLoaded" size="small" :type="masterDiff.length ? 'warning' : 'success'" effect="plain">
            {{ masterDiff.length }} 条
          </el-tag>
          <span v-if="masterDiffStandard" class="gt-fm-master-diff__std">对比准则：{{ masterDiffStandard }}</span>
          <el-checkbox v-if="masterDiffLoaded" v-model="masterDiffOnlyFormula" size="small">
            只看公式差异（全部 {{ masterDiffAll.length }} 条）
          </el-checkbox>
          <el-button size="small" link type="primary" :loading="masterDiffLoading" @click="loadMasterDiff">
            {{ masterDiffLoaded ? '重新比对' : '开始比对' }}
          </el-button>
          <el-button
            v-if="masterDiffLoaded"
            size="small"
            link
            type="primary"
            :loading="masterDiffApplying"
            @click="onApplyMasterUpdate"
          >
            ⬇ 同步主模板更新到本项目
          </el-button>
        </div>
        <div v-if="!masterDiffLoaded" class="gt-fm-master-diff__hint">
          比对本项目 <code>project:{id}</code> 配置与主模板的公式差异：项目改对了可回流主模板，主模板更新了可同步下来。
        </div>
        <el-alert
          v-else-if="!masterDiff.length"
          type="success"
          :closable="false"
          show-icon
          :title="masterDiffAll.length
            ? `无公式层面差异（另有 ${masterDiffAll.length} 条仅结构行差异，多为主模板中无公式的行）`
            : '项目级与主模板一致（或本项目尚未落入项目级配置）'"
          style="margin-bottom: 8px;"
        />
        <el-table v-else :data="masterDiff.slice(0, 50)" size="small" border style="width: 100%; margin-bottom: 8px;"
          :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
          <el-table-column prop="row_code" label="行次" width="100" />
          <el-table-column label="差异" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="masterDiffTagType(row.diff_type)" effect="plain">
                {{ masterDiffLabel(row.diff_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="项目级公式" min-width="200" show-overflow-tooltip>
            <template #default="{ row }"><code class="gt-fm-mono">{{ row.project_formula || '—' }}</code></template>
          </el-table-column>
          <el-table-column label="主模板公式" min-width="200" show-overflow-tooltip>
            <template #default="{ row }"><code class="gt-fm-mono">{{ row.master_formula || '—' }}</code></template>
          </el-table-column>
          <el-table-column label="操作" width="110" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.project_formula"
                size="small"
                link
                type="primary"
                @click="onSuggestToMaster(row)"
              >
                回流主模板
              </el-button>
              <span v-else style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs);">—</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="masterDiff.length > 50" class="gt-fm-master-diff__hint">
          仅展示前 50 条（共 {{ masterDiff.length }} 条）。
        </div>
      </div>
      <div v-if="!globalScopeNonEmpty.length" style="text-align: center; padding: 24px 20px;">
        <el-empty description="暂无公式" :image-size="80" style="margin-bottom: 16px;" />
        <div style="color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-sm); margin-bottom: 20px; line-height: 1.8;">
          本项目尚无项目级公式（底稿域 wp_formula 为空）。项目级公式在各底稿页新增，模板级预设请走上方按钮。
        </div>
        <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 12px;">
          <el-button type="primary" plain @click="onGoToReportPresets">
            📄 去报表预设（{{ reportPresetHint }}）
          </el-button>
          <el-button type="primary" plain @click="onMaterializeReportPresets">
            📥 把报表预设落入项目
          </el-button>
          <el-button plain @click="showGlobalScopeOverview = false">
            ✏️ 手动新增公式
          </el-button>
        </div>
        <div style="margin-top: 16px; padding: 12px 16px; background: var(--gt-color-fill-tertiary, #f5f7fa); border-radius: 6px; text-align: left; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); line-height: 1.8;">
          <div><strong>💡 各类公式存放位置：</strong></div>
          <div>• <strong>报表预设</strong>：report_config（模板级，按适用准则共用）—— 在报表节点直接编辑，保存即生效</div>
          <div>• <strong>附注校验预设</strong>：附注预设集（模板级，按国企版/上市版区分）</div>
          <div>• <strong>项目级公式</strong>：wp_formula（本页统计口径）—— 在各底稿页「新增公式」逐条创建</div>
          <div>• <strong>落入项目</strong>：把模板带公式的报表行复制成 <code>project:{id}</code> 配置，取数层优先用它；幂等可重复执行</div>
        </div>
      </div>
      <div v-else style="max-height: 72vh; overflow-y: auto;">
        <div v-for="group in globalScopeGroups" :key="group.scope" style="margin-bottom: 14px;">
          <div style="font-weight: 600; font-size: var(--gt-font-size-sm); margin-bottom: 6px; color: var(--gt-color-text-primary);">
            {{ group.label }}
            <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 6px;">{{ group.rows.length }} 条</span>
          </div>
          <div v-if="!group.rows.length" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); padding: 2px 0 6px;">
            本作用域暂无项目级公式
          </div>
          <el-table v-else :data="group.rows" size="small" border style="width: 100%;"
            :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
            <el-table-column label="目标单元" prop="targetCell" min-width="150" show-overflow-tooltip>
              <template #default="{ row }"><span class="gt-fm-mono">{{ row.targetCell }}</span></template>
            </el-table-column>
            <el-table-column label="公式" prop="expression" min-width="240" show-overflow-tooltip>
              <template #default="{ row }"><code class="gt-fm-mono">{{ row.expression || '—' }}</code></template>
            </el-table-column>
            <el-table-column label="类型" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="(categoryTagType(row.formulaType)) || undefined" size="small">{{ categoryLabel(row.formulaType) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="来源地址" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ row.sourceLabel || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="最近计算" width="160" align="center">
              <template #default="{ row }">
                <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">{{ row.lastComputedAt || '尚未计算' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button @click="showGlobalScopeOverview = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete, confirmDangerous } from '@/utils/confirm'
import { api } from '@/services/apiProxy'
import { reportConfig as P_rc, noteTemplates as P_nt, linkageBus, formulaAuditLog } from '@/services/apiPaths'
// spec: formula-management-runtime-closure Task 14 — 公式端点收敛进 apiPaths（纯搬迁，URL 逐字不变）
import {
  projectFormula,
  reportConfigFormula,
  wpFormula,
  wpUserFormula,
} from '@/services/apiPaths/formula'
import { fmtAmount } from '@/utils/formatters'
import FormulaEditDialog from './FormulaEditDialog.vue'
import FormulaHistoryTab from './FormulaHistoryTab.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useAddressRegistry } from '@/stores/addressRegistry'
import { useAcnr, type AcnrSheetEntry } from '@/services/acnr/useAcnr'
import { wpCodeNaturalCompare, composeSheetLabelsForGroup } from '@/services/acnr/sheetDisplayName'
import {
  useFormulaScopeCatalog,
  SCOPE_LABEL_MAP as SCOPE_CATALOG_LABEL_MAP,
  type FormulaScope,
} from '@/composables/useFormulaScopeCatalog'
import { noteSectionToNodeKey, buildNoteFormulaRows, isNoteDomainNodeKey } from './noteScopeTargeting'

/**
 * scope：当前公式管理器的目标范围
 *  - 'note'             单体附注（DisclosureEditor）
 *  - 'consol_note'      合并附注（ConsolNoteTab）
 *  - 'consol_worksheet' 合并工作底稿（ConsolWorksheetTabs，需求 7.4）
 *  - 'consol_report'    合并报表（ConsolReport，需求 7.4）
 *  - 'report'           报表（ReportView，默认）
 *  - 'tb'               试算平衡表
 * 仅作显式上下文标识（写入面包屑 + sessionStorage `gt-formula-target-node`），
 * 不改变现有树形导航行为。
 */
type FormulaManagerScope = 'note' | 'consol_note' | 'consol_worksheet' | 'consol_report' | 'report' | 'tb' | 'workpaper'

const props = withDefaults(defineProps<{
  modelValue: boolean
  rows: any[]
  projectId?: string
  wpId?: string
  wpCode?: string
  sheetName?: string
  /**
   * 宿主工作簿真实拥有的 sheet 编码（render-config 下发）。
   *
   * 🔴 跨循环共享页（D2 册内的 D0-1~D0-8、E1 册内的 E26A）在 ACNR 目录里
   * `parent_wp_code` 指向原生工作簿（D0），≠ 宿主 wp_code（D2）。仅按 wp_code
   * 前缀判归属会认不出这些页 ⇒ 定位失败 + 静默退成全册（右侧列出别页公式）。
   * 缺省（旧入口未传）时退回 wp_code 前缀口径，行为不变。
   */
  hostSheetCodes?: string[]
  year?: number
  scope?: FormulaManagerScope
  /**
   * 附注域：调用页当前正在编辑的章节编号（note_section，如「五、1」）。
   * 打开弹窗时据此自动展开+选中该章节节点，避免落到默认的「报表 > 资产负债表」。
   */
  noteSection?: string
  /** 附注域：当前章节标题（如「货币资金」），用于筛选本章节预设公式（编号体系可能与预设集偏移）。 */
  noteSectionTitle?: string
  /** 模板类型（soe / listed / custom）：与调用页保持一致，避免上市版页面加载国企版预设。 */
  templateType?: string
}>(), {
  scope: 'report',
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'saved'): void
  (e: 'applied'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 路由器(用于外链节点跳转)
const router = useRouter()
const prefs = useDisplayPrefsStore()

// R14.6: 本弹窗主要作为壳，托管已迁移至 ACNR 的 FormulaEditDialog（公式构造/选址）；
// 其自身的候选地址列表（tb_detail 科目明细）改走 Req16 store facade（ACNR-backed）tbAddresses，
// 空/未加载时回退 props.rows（无回归）。WP 域 formula_ref 由 FormulaEditDialog 以 grammar_v1
// 三形态（2 参语义列 / 3 参 cell / custom_flat）构造。
const addrStore = useAddressRegistry()

// ── Req 24: 作用域过滤 + 全局公式总览 ──
// 消费后端 GET /api/formula-scope/{project_id}/formulas（Task 20.2），按传入 scope
// 只加载本域公式；全局页取并集。缓存以 (scope, addrKey) 隔离，各域互不串扰（Req 24.5）。
// 来源地址经 ACNR full_resolve 规范化（Req 24.6，与 Req 10/P14 一致）。
const scopeCatalog = useFormulaScopeCatalog()
// 当前作用域（本页）公式列表（Req 24.1/24.2：仅本域，不含他域）。
const scopeFormulas = computed(() => scopeCatalog.getScopeRows(props.scope as FormulaScope))
// 全局公式总览弹窗开关（Req 24.3：跨全部 7 类 scope 总览）。
const showGlobalScopeOverview = ref(false)
/**
 * 全局总览分组。
 *
 * 🔴 全 7 域都列（含 0 条），不再只留非空分组：项目级公式为 0 时整窗只剩一个
 * 「暂无公式」，用户无法判断是「没配」还是「没查到」，也看不出预设去哪了。
 */
const globalScopeGroups = computed(() =>
  (Object.keys(SCOPE_CATALOG_LABEL_MAP) as FormulaScope[])
    .map((s) => ({ scope: s, label: SCOPE_CATALOG_LABEL_MAP[s], rows: scopeCatalog.globalGrouped.value[s] })),
)

/** 有公式的分组（决定是否展示空态引导）。 */
const globalScopeNonEmpty = computed(() => globalScopeGroups.value.filter((g) => g.rows.length > 0))

/** 打开时按当前 scope 加载本域公式，并规范化来源地址（Req 24.1/24.6）。 */
async function loadScopeFormulas() {
  if (!props.projectId) return
  const rows = await scopeCatalog.loadScope(props.projectId, props.scope as FormulaScope)
  await scopeCatalog.resolveSources(rows)
}

/** 报表预设可用条数提示（模板级 report_config，供空态按钮显示真实数量）。 */
const reportPresetHint = computed(() => {
  const n = REPORT_TYPE_KEYS.reduce(
    (sum, rt) => sum + (((allRowsMap.value[rt] as any[] | undefined) || []).filter((r) => r.formula).length),
    0,
  )
  return n ? `${n} 条` : '模板级'
})

/** 跳到报表预设节点（模板级公式的真实编辑入口）。 */
async function onGoToReportPresets() {
  showGlobalScopeOverview.value = false
  const hit = await applyTargetNode('report_balance_sheet')
  if (!hit) {
    selectedNodeKey.value = 'report_balance_sheet'
    selectedPath.value = '报表 > 资产负债表'
    await loadRowsForNode('report_balance_sheet')
  }
}

/** 跳到附注域根节点并加载附注校验预设。 */
async function onGoToNotePresets() {
  showGlobalScopeOverview.value = false
  await applyNoteScopeTarget()
}

// ── 项目级 ↔ 主模板差异（复用 report_config_baseline 的三个既有端点）──────────
// 平台已有 diff-vs-master / apply-master-update / suggest-to-master，但公式中心
// 一直没有入口 ⇒ 项目改对的公式只留在本项目、主模板更新也不会同步下来。
const masterDiffAll = ref<any[]>([])
const masterDiffStandard = ref('')
const masterDiffLoaded = ref(false)
const masterDiffLoading = ref(false)
const masterDiffApplying = ref(false)
/**
 * 只看公式差异（默认开）。
 *
 * 🔴 后端 diff 比的是**全部行**：本项目只落了「带公式」的行（183 条），
 * 主模板另有大量无公式的结构行 ⇒ 实测 169 条差异里绝大多数是
 * 「仅主模板有 + 两侧公式都为空」，对公式治理是纯噪声。
 */
const masterDiffOnlyFormula = ref(true)

/** 面板实际展示的差异行。 */
const masterDiff = computed(() =>
  masterDiffOnlyFormula.value
    ? masterDiffAll.value.filter((d) => d.project_formula || d.master_formula)
    : masterDiffAll.value,
)

const MASTER_DIFF_LABELS: Record<string, string> = {
  modified: '公式不同',
  project_only: '仅项目有',
  master_only: '仅主模板有',
}
function masterDiffLabel(t: string): string {
  return MASTER_DIFF_LABELS[t] || t
}
function masterDiffTagType(t: string): 'warning' | 'success' | 'info' {
  if (t === 'modified') return 'warning'
  if (t === 'project_only') return 'success'
  return 'info'
}

async function loadMasterDiff() {
  if (!props.projectId) return
  masterDiffLoading.value = true
  try {
    const data = await api.get(P_rc.diffVsMaster(props.projectId), {
      validateStatus: (s: number) => s < 600,
    })
    const result = data?.data ?? data
    masterDiffAll.value = Array.isArray(result?.diffs) ? result.diffs : []
    masterDiffStandard.value = String(result?.standard || '')
    masterDiffLoaded.value = true
  } catch (e) {
    handleApiError(e, '比对主模板失败')
  } finally {
    masterDiffLoading.value = false
  }
}

/** 同步主模板更新到本项目（默认保留项目本地覆盖）。 */
async function onApplyMasterUpdate() {
  if (!props.projectId) return
  try {
    await ElMessageBox.confirm(
      '将把主模板的公式更新同步到本项目的项目级配置，默认**保留**项目已改过的行。确认同步？',
      '同步主模板更新',
      { confirmButtonText: '确认同步', cancelButtonText: '取消', type: 'info' },
    )
  } catch { return }
  masterDiffApplying.value = true
  try {
    const data = await api.post(P_rc.applyMasterUpdate, {
      project_id: props.projectId,
      standard: masterDiffStandard.value || undefined,
      keep_local: true,
    })
    const result = data?.data ?? data
    ElMessage.success(`已同步 ${result?.updated_count ?? 0} 行`)
    // 同步后本地缓存的报表行已过期，清掉重新按项目级口径取
    allRowsMap.value = {}
    reportStandardByType.value = {}
    await loadMasterDiff()
  } catch (e) {
    handleApiError(e, '同步主模板更新失败')
  } finally {
    masterDiffApplying.value = false
  }
}

/** 把某条项目级公式提交为主模板候选（admin 审核通过后合并回 standard 级）。 */
async function onSuggestToMaster(row: any) {
  if (!props.projectId || !row?.project_formula) return
  try {
    await ElMessageBox.confirm(
      `将把「${row.row_code}」的项目级公式提交为主模板候选，待管理员审核通过后其他项目才会受益。确认提交？`,
      '回流主模板',
      { confirmButtonText: '确认提交', cancelButtonText: '取消', type: 'info' },
    )
  } catch { return }
  try {
    await api.post(P_rc.suggestToMaster, {
      project_id: props.projectId,
      row_code: row.row_code,
      report_type: row.report_type,
      standard: masterDiffStandard.value || undefined,
      candidate_formula: row.project_formula,
    })
    ElMessage.success(`已提交「${row.row_code}」为主模板候选，等待管理员审核`)
  } catch (e) {
    handleApiError(e, '提交主模板候选失败')
  }
}

/** 从全局公式切到公式看板（看板才是真正的跨域总览）。 */
function onOpenDashboardFromGlobal() {
  showGlobalScopeOverview.value = false
  showFormulaDashboard.value = true
}

/** 打开全局公式总览：跨全部 7 类 scope 取并集（Req 24.3）。 */
async function onOpenGlobalScopeOverview() {
  showGlobalScopeOverview.value = true
  if (props.projectId) {
    await scopeCatalog.loadGlobal(props.projectId)
    // 逐域规范化来源地址（Req 24.6）
    for (const scope of Object.keys(SCOPE_CATALOG_LABEL_MAP) as FormulaScope[]) {
      await scopeCatalog.resolveScopeSources(scope)
    }
  }
}

/**
 * 把报表预设落入项目级配置（`report_config.applicable_standard = 'project:{id}'`）。
 *
 * 🔴 这才是「预设带入项目」的真实动作：项目级行由取数层优先消费
 * （`report_account_mapping` / `four_table.report_line_accounts` /
 * `semantic_account_resolver` / `i_cycle_accounts` 都是 project 优先、standard 兜底），
 * 落进去之后本项目改公式不再影响其他项目。
 *
 * 走既有端点 `POST /api/report-config/clone` 的 `mode: 'sync'`（幂等：已存在跳过，
 * 只落有公式的行）。此前这里打的是后端零实现的 `formula/auto-generate`，恒 404。
 */
async function onMaterializeReportPresets() {
  if (!props.projectId) return
  const standard = `${fmTemplateType.value}_standalone`
  try {
    await ElMessageBox.confirm(
      `将把「${standard}」模板中带公式的报表行落成本项目的项目级配置（project:${props.projectId}）。`
      + '落库后取数层会优先使用项目级公式，本项目的修改不再影响其他项目；'
      + '已存在的项目级行默认保留不覆盖。确认执行？',
      '把报表预设落入项目',
      { confirmButtonText: '确认落入', cancelButtonText: '取消', type: 'info' },
    )
    const data = await api.post(P_rc.clone, {
      project_id: props.projectId,
      applicable_standard: standard,
      mode: 'sync',
      overwrite: false,
    })
    const result = data?.data ?? data
    const created = result?.created ?? result?.count ?? 0
    const skipped = result?.skipped ?? 0
    ElMessage.success(`已落入 ${created} 条项目级公式（跳过已存在 ${skipped} 条）`)
    await onOpenGlobalScopeOverview()
  } catch (e: any) {
    if (e === 'cancel' || e?.toString() === 'cancel') return
    handleApiError(e, '把报表预设落入项目失败')
  }
}

// ── 树形导航数据 ──
const fmTreeRef = ref<any>(null)
const expandedKeys = ref<string[]>([])
const selectedNodeKey = ref('report_balance_sheet')
const selectedPath = ref('报表 > 资产负债表')
/** 归一化调用页模板类型：仅 soe / listed 两版预设，custom 等按国企版兜底。 */
function normalizeTemplateType(t?: string): 'soe' | 'listed' {
  return t === 'listed' ? 'listed' : 'soe'
}
const fmTemplateType = ref<string>(normalizeTemplateType(props.templateType))

// 当前 scope 对应的中文 tag（仅展示用，不影响树形导航行为）
const SCOPE_LABEL_MAP: Record<FormulaManagerScope, string> = {
  note: '单体附注',
  consol_note: '合并附注',
  consol_worksheet: '合并工作底稿',
  consol_report: '合并报表',
  report: '报表',
  tb: '试算平衡表',
  workpaper: '底稿',
}
const scopeLabel = computed(() => SCOPE_LABEL_MAP[props.scope] || '报表')

function onFmTemplateChange() {
  // 切换模板类型后清空缓存，重新加载
  allRowsMap.value = {}
  noteTreeLoaded.value = false
  noteTreeChildren.value = []
  loadNoteTree()
  loadRowsForNode(selectedNodeKey.value)
}

function allowTreeDrop(draggingNode: any, dropNode: any, type: string) {
  return draggingNode.parent === dropNode.parent && type !== 'inner'
}

// ── 动态附注树（从项目实际附注章节加载，项目不同内容不同） ──
const noteTreeChildren = ref<any[]>([])
const noteTreeLoaded = ref(false)

async function loadNoteTree() {
  if (noteTreeLoaded.value) return
  try {
    // 优先从项目级附注 API 加载（项目不同结构不同）
    if (props.projectId && props.year) {
      const { getDisclosureNoteTree } = await import('@/services/auditPlatformApi')
      const notes = await getDisclosureNoteTree(props.projectId, Number(props.year))
      if (Array.isArray(notes) && notes.length) {
        noteTreeChildren.value = buildNoteTreeFromProjectData(notes)
        noteTreeLoaded.value = true
        return
      }
    }
    // 降级：从模板级 API 加载（不区分项目）
    const data = await api.get(P_nt.list(fmTemplateType.value), {
      validateStatus: (s: number) => s < 600,
    })
    const sections = data ?? []
    if (!Array.isArray(sections) || !sections.length) return

    // 按章节分组构建树
    const chapterMap: Record<string, { label: string; children: any[] }> = {}
    const chapterOrder = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

    for (const sec of sections) {
      const title = sec.section_title || sec.title || ''
      const sectionId = sec.section_id || sec.note_section || ''
      // 提取章节编号（如 "五、1" → 章="五"）
      const chapterMatch = sectionId.match(/^([一二三四五六七八九十]+)/)
      const chapter = chapterMatch ? chapterMatch[1] : '其他'

      if (!chapterMap[chapter]) {
        const chapterLabels: Record<string, string> = {
          '一': '一、公司概况', '二': '二、编制基础', '三': '三、会计政策',
          '四': '四、税项', '五': '五、报表科目注释', '六': '六、其他',
          '七': '七、关联方', '八': '八、或有事项', '九': '九、承诺',
          '十': '十、日后事项',
        }
        chapterMap[chapter] = {
          label: chapterLabels[chapter] || `${chapter}、其他`,
          children: [],
        }
      }
      chapterMap[chapter].children.push({
        key: noteSectionToNodeKey(sectionId),
        label: title.length > 20 ? title.slice(0, 20) + '...' : title,
        icon: '',
        _sectionTitle: title,
        _sectionId: sectionId,
        _tableCount: sec.tables?.length || 0,
        count: sec.check_presets ? Object.keys(sec.check_presets).length : 0,
      })
    }

    // 按章节顺序排列
    const result: any[] = []
    for (const ch of chapterOrder) {
      if (chapterMap[ch]) {
        result.push({
          key: `note_chapter_${ch}`,
          label: chapterMap[ch].label,
          icon: '',
          children: chapterMap[ch].children,
        })
      }
    }
    if (chapterMap['其他']) {
      result.push({
        key: 'note_chapter_other',
        label: '其他',
        icon: '',
        children: chapterMap['其他'].children,
      })
    }
    noteTreeChildren.value = result
    noteTreeLoaded.value = true
  } catch { /* ignore, fallback to static tree */ }
}

/** 从项目级附注数据构建章节树（动态，项目不同结构不同） */
function buildNoteTreeFromProjectData(notes: Array<{ note_section: string; section_title?: string; tables?: any[]; check_presets?: Record<string, any> }>): any[] {
  const CHAPTER_ORDER = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四', '十五', '十六', '十七']
  const chapterMap: Record<string, { label: string; children: any[] }> = {}

  for (const n of notes) {
    const sectionId = n.note_section || ''
    const title = n.section_title || sectionId
    // 提取章节编号
    const chMatch = sectionId.match(/^([一二三四五六七八九十]+(?:[一二三四五六七八九十])?)/)
    const chapter = chMatch ? chMatch[1] : '其他'

    if (!chapterMap[chapter]) {
      chapterMap[chapter] = { label: `${chapter}、${title.split('、')[0] || ''}`, children: [] }
    }
    chapterMap[chapter].children.push({
      key: noteSectionToNodeKey(sectionId),
      label: title.length > 24 ? title.slice(0, 24) + '…' : title,
      icon: '',
      _sectionTitle: title,
      _sectionId: sectionId,
      _tableCount: n.tables?.length || 0,
      count: n.check_presets ? Object.keys(n.check_presets).length : 0,
    })
  }

  const result: any[] = []
  for (const ch of CHAPTER_ORDER) {
    if (chapterMap[ch]) {
      result.push({
        key: `note_chapter_${ch}`,
        label: chapterMap[ch].label,
        icon: '',
        children: chapterMap[ch].children,
      })
    }
  }
  if (chapterMap['其他']?.children.length) {
    result.push({ key: 'note_chapter_other', label: '其他', icon: '', children: chapterMap['其他'].children })
  }
  return result
}

// 静态附注树（降级用 / ACNR 尚未覆盖 note 域时显示）
// 结构与致同 2025 修订版附注模板全章节对齐，key 遵循 ACNR note 索引语法 `note:{section_id}`
const staticNoteTree = [
  { key: 'note_chapter_yi', label: '一、公司概况', icon: '', children: [
    { key: 'note_yi_1', label: '公司注册地/组织形式/总部', icon: '', _sectionTitle: '公司概况' },
    { key: 'note_yi_2', label: '经营范围/主要业务', icon: '', _sectionTitle: '经营范围' },
  ]},
  { key: 'note_chapter_er', label: '二、编制基础', icon: '', children: [
    { key: 'note_er_1', label: '编制基础说明', icon: '', _sectionTitle: '编制基础' },
    { key: 'note_er_2', label: '持续经营', icon: '', _sectionTitle: '持续经营' },
  ]},
  { key: 'note_chapter_san', label: '三、重要会计政策及估计', icon: '', children: [
    { key: 'note_san_1', label: '遵循企业准则声明', icon: '', _sectionTitle: '遵循企业准则声明' },
    { key: 'note_san_2', label: '会计期间', icon: '', _sectionTitle: '会计期间' },
    { key: 'note_san_3', label: '营业周期', icon: '', _sectionTitle: '营业周期' },
    { key: 'note_san_4', label: '记账本位币', icon: '', _sectionTitle: '记账本位币' },
    { key: 'note_san_5', label: '金融工具分类', icon: '', _sectionTitle: '金融工具分类' },
    { key: 'note_san_6', label: '金融资产减值', icon: '', _sectionTitle: '金融资产减值' },
    { key: 'note_san_7', label: '存货', icon: '', _sectionTitle: '存货' },
    { key: 'note_san_8', label: '固定资产', icon: '', _sectionTitle: '固定资产' },
    { key: 'note_san_9', label: '无形资产', icon: '', _sectionTitle: '无形资产' },
    { key: 'note_san_10', label: '长期股权投资', icon: '', _sectionTitle: '长期股权投资' },
    { key: 'note_san_11', label: '投资性房地产', icon: '', _sectionTitle: '投资性房地产' },
    { key: 'note_san_12', label: '收入确认', icon: '', _sectionTitle: '收入确认' },
    { key: 'note_san_13', label: '政府补助', icon: '', _sectionTitle: '政府补助' },
    { key: 'note_san_14', label: '所得税', icon: '', _sectionTitle: '所得税' },
    { key: 'note_san_15', label: '租赁', icon: '', _sectionTitle: '租赁' },
    { key: 'note_san_16', label: '重要会计估计和判断', icon: '', _sectionTitle: '重要会计估计和判断' },
  ]},
  { key: 'note_chapter_si', label: '四、税项', icon: '', children: [
    { key: 'note_si_1', label: '主要税种及税率', icon: '', _sectionTitle: '主要税种及税率' },
    { key: 'note_si_2', label: '税收优惠', icon: '', _sectionTitle: '税收优惠' },
  ]},
  { key: 'note_chapter_wu', label: '五、报表科目注释', icon: '', children: [
    // ── 资产类 ──
    { key: 'note_wu_cash', label: '货币资金', icon: '', _sectionTitle: '货币资金' },
    { key: 'note_wu_trading_fa', label: '交易性金融资产', icon: '', _sectionTitle: '交易性金融资产' },
    { key: 'note_wu_notes_recv', label: '应收票据', icon: '', _sectionTitle: '应收票据' },
    { key: 'note_wu_ar', label: '应收账款', icon: '', _sectionTitle: '应收账款' },
    { key: 'note_wu_recv_financing', label: '应收款项融资', icon: '', _sectionTitle: '应收款项融资' },
    { key: 'note_wu_prepay', label: '预付款项', icon: '', _sectionTitle: '预付款项' },
    { key: 'note_wu_other_recv', label: '其他应收款', icon: '', _sectionTitle: '其他应收款' },
    { key: 'note_wu_inventory', label: '存货', icon: '', _sectionTitle: '存货' },
    { key: 'note_wu_contract_asset', label: '合同资产', icon: '', _sectionTitle: '合同资产' },
    { key: 'note_wu_noncurrent_1y', label: '一年内到期非流动资产', icon: '', _sectionTitle: '一年内到期非流动资产' },
    { key: 'note_wu_other_current', label: '其他流动资产', icon: '', _sectionTitle: '其他流动资产' },
    { key: 'note_wu_lt_recv', label: '长期应收款', icon: '', _sectionTitle: '长期应收款' },
    { key: 'note_wu_lt_equity', label: '长期股权投资', icon: '', _sectionTitle: '长期股权投资' },
    { key: 'note_wu_other_equity', label: '其他权益工具投资', icon: '', _sectionTitle: '其他权益工具投资' },
    { key: 'note_wu_other_noncurrent_fa', label: '其他非流动金融资产', icon: '', _sectionTitle: '其他非流动金融资产' },
    { key: 'note_wu_invest_property', label: '投资性房地产', icon: '', _sectionTitle: '投资性房地产' },
    { key: 'note_wu_fixed_asset', label: '固定资产', icon: '', _sectionTitle: '固定资产' },
    { key: 'note_wu_cip', label: '在建工程', icon: '', _sectionTitle: '在建工程' },
    { key: 'note_wu_rou', label: '使用权资产', icon: '', _sectionTitle: '使用权资产' },
    { key: 'note_wu_intangible', label: '无形资产', icon: '', _sectionTitle: '无形资产' },
    { key: 'note_wu_goodwill', label: '商誉', icon: '', _sectionTitle: '商誉' },
    { key: 'note_wu_lt_prepaid', label: '长期待摊费用', icon: '', _sectionTitle: '长期待摊费用' },
    { key: 'note_wu_deferred_tax_asset', label: '递延所得税资产', icon: '', _sectionTitle: '递延所得税资产' },
    { key: 'note_wu_other_noncurrent', label: '其他非流动资产', icon: '', _sectionTitle: '其他非流动资产' },
    // ── 负债类 ──
    { key: 'note_wu_st_borrow', label: '短期借款', icon: '', _sectionTitle: '短期借款' },
    { key: 'note_wu_trading_fl', label: '交易性金融负债', icon: '', _sectionTitle: '交易性金融负债' },
    { key: 'note_wu_notes_payable', label: '应付票据', icon: '', _sectionTitle: '应付票据' },
    { key: 'note_wu_ap', label: '应付账款', icon: '', _sectionTitle: '应付账款' },
    { key: 'note_wu_advance_recv', label: '预收款项/合同负债', icon: '', _sectionTitle: '合同负债' },
    { key: 'note_wu_employee_pay', label: '应付职工薪酬', icon: '', _sectionTitle: '应付职工薪酬' },
    { key: 'note_wu_tax_payable', label: '应交税费', icon: '', _sectionTitle: '应交税费' },
    { key: 'note_wu_other_payable', label: '其他应付款', icon: '', _sectionTitle: '其他应付款' },
    { key: 'note_wu_current_1y', label: '一年内到期非流动负债', icon: '', _sectionTitle: '一年内到期非流动负债' },
    { key: 'note_wu_other_current_liab', label: '其他流动负债', icon: '', _sectionTitle: '其他流动负债' },
    { key: 'note_wu_lt_borrow', label: '长期借款', icon: '', _sectionTitle: '长期借款' },
    { key: 'note_wu_bonds_payable', label: '应付债券', icon: '', _sectionTitle: '应付债券' },
    { key: 'note_wu_lease_liab', label: '租赁负债', icon: '', _sectionTitle: '租赁负债' },
    { key: 'note_wu_lt_payable', label: '长期应付款', icon: '', _sectionTitle: '长期应付款' },
    { key: 'note_wu_deferred_tax_liab', label: '递延所得税负债', icon: '', _sectionTitle: '递延所得税负债' },
    { key: 'note_wu_provision', label: '预计负债', icon: '', _sectionTitle: '预计负债' },
    { key: 'note_wu_deferred_income', label: '递延收益', icon: '', _sectionTitle: '递延收益' },
    // ── 权益类 ──
    { key: 'note_wu_share_capital', label: '股本/实收资本', icon: '', _sectionTitle: '股本' },
    { key: 'note_wu_capital_reserve', label: '资本公积', icon: '', _sectionTitle: '资本公积' },
    { key: 'note_wu_other_ci', label: '其他综合收益', icon: '', _sectionTitle: '其他综合收益' },
    { key: 'note_wu_surplus_reserve', label: '盈余公积', icon: '', _sectionTitle: '盈余公积' },
    { key: 'note_wu_undist_profit', label: '未分配利润', icon: '', _sectionTitle: '未分配利润' },
    // ── 损益类 ──
    { key: 'note_wu_revenue', label: '营业收入/营业成本', icon: '', _sectionTitle: '营业收入' },
    { key: 'note_wu_tax_surcharge', label: '税金及附加', icon: '', _sectionTitle: '税金及附加' },
    { key: 'note_wu_selling_exp', label: '销售费用', icon: '', _sectionTitle: '销售费用' },
    { key: 'note_wu_admin_exp', label: '管理费用', icon: '', _sectionTitle: '管理费用' },
    { key: 'note_wu_rd_exp', label: '研发费用', icon: '', _sectionTitle: '研发费用' },
    { key: 'note_wu_finance_exp', label: '财务费用', icon: '', _sectionTitle: '财务费用' },
    { key: 'note_wu_other_income', label: '其他收益', icon: '', _sectionTitle: '其他收益' },
    { key: 'note_wu_invest_income', label: '投资收益', icon: '', _sectionTitle: '投资收益' },
    { key: 'note_wu_credit_loss', label: '信用减值损失', icon: '', _sectionTitle: '信用减值损失' },
    { key: 'note_wu_asset_loss', label: '资产减值损失', icon: '', _sectionTitle: '资产减值损失' },
    { key: 'note_wu_asset_disposal', label: '资产处置收益', icon: '', _sectionTitle: '资产处置收益' },
    { key: 'note_wu_non_op_income', label: '营业外收入', icon: '', _sectionTitle: '营业外收入' },
    { key: 'note_wu_non_op_exp', label: '营业外支出', icon: '', _sectionTitle: '营业外支出' },
    { key: 'note_wu_income_tax', label: '所得税费用', icon: '', _sectionTitle: '所得税费用' },
  ]},
  { key: 'note_chapter_liu', label: '六、其他重要事项', icon: '', children: [
    { key: 'note_liu_1', label: '分部报告', icon: '', _sectionTitle: '分部报告' },
    { key: 'note_liu_2', label: '金融工具风险', icon: '', _sectionTitle: '金融工具风险' },
    { key: 'note_liu_3', label: '公允价值层次', icon: '', _sectionTitle: '公允价值层次' },
  ]},
  { key: 'note_chapter_qi', label: '七、关联方关系及交易', icon: '', children: [
    { key: 'note_qi_1', label: '关联方清单', icon: '', _sectionTitle: '关联方清单' },
    { key: 'note_qi_2', label: '关联交易', icon: '', _sectionTitle: '关联交易' },
    { key: 'note_qi_3', label: '关联方应收应付', icon: '', _sectionTitle: '关联方应收应付' },
  ]},
  { key: 'note_chapter_ba', label: '八、或有事项', icon: '', children: [
    { key: 'note_ba_1', label: '未决诉讼', icon: '', _sectionTitle: '未决诉讼' },
    { key: 'note_ba_2', label: '担保事项', icon: '', _sectionTitle: '担保事项' },
  ]},
  { key: 'note_chapter_jiu', label: '九、承诺事项', icon: '', children: [
    { key: 'note_jiu_1', label: '资本承诺', icon: '', _sectionTitle: '资本承诺' },
    { key: 'note_jiu_2', label: '经营租赁承诺', icon: '', _sectionTitle: '经营租赁承诺' },
  ]},
  { key: 'note_chapter_shi', label: '十、资产负债表日后事项', icon: '', children: [
    { key: 'note_shi_1', label: '日后调整事项', icon: '', _sectionTitle: '日后调整事项' },
    { key: 'note_shi_2', label: '日后非调整事项', icon: '', _sectionTitle: '日后非调整事项' },
  ]},
]

// ── ACNR 五域导航树（动态构建，与地址坐标名称库一致） ──
// 域标签与图标映射（五域 + 合并/表间/质量规则扩展）
const DOMAIN_TREE_META: Record<string, { label: string; icon: string }> = {
  tb: { label: '试算平衡表', icon: '📑' },
  report: { label: '报表', icon: '📊' },
  note: { label: '附注', icon: '📝' },
  wp: { label: '底稿', icon: '📋' },
  aux: { label: '辅助余额', icon: '📎' },
}

// WP 域循环中文标签
const CYCLE_LABEL_MAP: Record<string, string> = {
  D: 'D 销售循环', E: 'E 货币资金', F: 'F 采购循环',
  G: 'G 生产循环', H: 'H 固定资产', I: 'I 无形资产',
  J: 'J 投资循环', K: 'K 筹资循环', L: 'L 人力循环',
  M: 'M 权益循环', N: 'N 税项循环', S: 'S 特定项目',
}

// 报表子类（动态从 report_config API 获取，项目不同可能有不同报表类型）
// 初始值即为静态降级列表，确保树打开时报表域不为空
const REPORT_SUBTYPE_LABELS_FALLBACK: Record<string, string> = {
  balance_sheet: '资产负债表',
  income_statement: '利润表',
  cash_flow_statement: '现金流量表',
  equity_statement: '权益变动表',
  cash_flow_supplement: '现金流附表',
  impairment_provision: '资产减值准备表',
}
const reportTypes = ref<Array<{ type: string; label: string; count: number }>>(
  Object.entries(REPORT_SUBTYPE_LABELS_FALLBACK).map(([type, label]) => ({ type, label, count: 0 }))
)
const reportTypesLoaded = ref(false)

async function loadReportTypes() {
  if (reportTypesLoaded.value) return
  try {
    const data = await api.get('/api/report-config/types', {
      params: { project_id: props.projectId },
      _silent: true,  // 404 不弹全局错误 toast
    } as any)
    const items = Array.isArray(data) ? data : (data?.data ?? [])
    if (Array.isArray(items) && items.length) {
      reportTypes.value = items.map((r: any) => ({
        type: r.report_type || r.type,
        label: r.label || REPORT_SUBTYPE_LABELS_FALLBACK[r.report_type || r.type] || r.report_type,
        count: r.formula_count ?? 0,
      }))
      reportTypesLoaded.value = true
      return
    }
  } catch { /* 降级到静态 */ }
  // 降级：API 不可用时用静态
  reportTypes.value = Object.entries(REPORT_SUBTYPE_LABELS_FALLBACK).map(([type, label]) => ({
    type, label, count: countFormulas(type),
  }))
  reportTypesLoaded.value = true
}

// ACNR sheet 列表缓存（从 useAcnr 加载）
const acnrSheets = shallowRef<AcnrSheetEntry[]>([])
const acnrTreeLoaded = ref(false)

async function loadAcnrTree() {
  if (acnrTreeLoaded.value) return
  try {
    const acnr = useAcnr()
    acnrSheets.value = await acnr.listSheets()
    acnrTreeLoaded.value = true
  } catch (e) {
    console.warn('[FormulaManager] ACNR listSheets 降级为静态树', e)
  }
}

/** 从 ACNR sheet 列表按域构建 wp 子树（cycle → parent → sheet）；
 *  显示名/排序/序号消歧统一走单一真源 composeSheetLabelsForGroup（sheetDisplayName.ts） */
function buildWpDomainTree(sheets: AcnrSheetEntry[]) {
  // 过滤掉 sheet_code === parent_wp_code 的幻影条目（catalog 中"底稿自身作为子 sheet"的占位，
  // 如 D1 parent 下有 sheet_code='D1' 与 sheet_code='D1-1' 重复，前者是冗余占位应排除）
  const wpSheets = sheets.filter(s => s.domain === 'wp' && s.sheet_code !== s.parent_wp_code)
  // 按 cycle 分组
  const byCycle = new Map<string, AcnrSheetEntry[]>()
  for (const s of wpSheets) {
    const c = s.cycle || s.parent_wp_code?.charAt(0) || '?'
    if (!byCycle.has(c)) byCycle.set(c, [])
    byCycle.get(c)!.push(s)
  }
  // 每个 cycle 下按 parent_wp_code 再分组（全部自然排序，避免 D10 排在 D2 前）
  const cycleNodes: any[] = []
  for (const [cycle, cycleSheets] of [...byCycle.entries()].sort((a, b) => wpCodeNaturalCompare(a[0], b[0]))) {
    const byParent = new Map<string, AcnrSheetEntry[]>()
    for (const s of cycleSheets) {
      const p = s.parent_wp_code
      if (!byParent.has(p)) byParent.set(p, [])
      byParent.get(p)!.push(s)
    }
    const parentNodes = [...byParent.entries()]
      .sort((a, b) => wpCodeNaturalCompare(a[0], b[0]))
      .map(([parentCode, parentSheets]) => {
        const subjectAbbr = parentSheets.find(s => s.account_name)?.account_name || ''
        const children = composeSheetLabelsForGroup(parentSheets).map(({ entry, label }) => ({
          key: `wp_${entry.sheet_code?.replace(/-/g, '_')?.toLowerCase() || entry.addr_id}`,
          label,
          icon: '',
          _addrId: entry.addr_id,
          _wpCode: parentCode,               // 所属底稿(工作簿)编码，供 wp-id-by-code 解析 wp_id
          _sheetCode: entry.sheet_code || '', // 具体 sheet 编码（如 E1-1），用于筛选该页公式
        }))
        return {
          key: `wp_${parentCode.toLowerCase()}`,
          // 父节点也带科目简称：如「D2 应收账款」，避免裸编码难辨识
          label: subjectAbbr ? `${parentCode} ${subjectAbbr}` : parentCode,
          icon: '',
          children,
          _wpCode: parentCode,
          _sheetCode: '',
        }
      })
    cycleNodes.push({
      key: `wp_cycle_${cycle.toLowerCase()}`,
      label: CYCLE_LABEL_MAP[cycle.toUpperCase()] || `${cycle} 循环`,
      icon: '',
      children: parentNodes,
    })
  }
  return cycleNodes
}

const treeData = computed(() => {
  // ACNR 五域树（动态，来自 catalog；与地址坐标名称库一致）
  const acnrDrivenTree: any[] = []

  // 1. 试算平衡表域
  acnrDrivenTree.push({
    key: 'trial_balance', label: DOMAIN_TREE_META.tb.label, icon: DOMAIN_TREE_META.tb.icon, children: [
      { key: 'tb_detail', label: '科目明细', icon: '' },
      { key: 'tb_summary', label: '试算平衡表', icon: '' },
    ],
  })

  // 2. 报表域（动态从 API 获取，项目不同可能有不同报表类型）
  acnrDrivenTree.push({
    key: 'report', label: DOMAIN_TREE_META.report.label, icon: DOMAIN_TREE_META.report.icon, children:
      reportTypes.value.map(r => ({
        key: `report_${r.type}`, label: r.label, icon: '', count: r.count || countFormulas(r.type),
      })),
  })

  // 3. 附注域（动态加载，降级静态）
  acnrDrivenTree.push({
    key: 'note', label: DOMAIN_TREE_META.note.label, icon: DOMAIN_TREE_META.note.icon,
    children: noteTreeChildren.value.length ? noteTreeChildren.value : staticNoteTree,
  })

  // 4. 底稿域（wp）— 从 ACNR catalog 动态构建，按 cycle → parent → sheet 三级
  if (acnrSheets.value.length) {
    acnrDrivenTree.push({
      key: 'workpaper', label: DOMAIN_TREE_META.wp.label, icon: DOMAIN_TREE_META.wp.icon,
      children: buildWpDomainTree(acnrSheets.value),
    })
  } else {
    // 降级：ACNR 未加载时展示静态骨架
    acnrDrivenTree.push({
      key: 'workpaper', label: DOMAIN_TREE_META.wp.label, icon: DOMAIN_TREE_META.wp.icon, children: [
        { key: 'wp_loading', label: '加载中…', icon: '⏳' },
      ],
    })
  }

  // 5. 辅助余额域（aux）
  const auxSheets = acnrSheets.value.filter(s => s.domain === 'aux')
  if (auxSheets.length) {
    acnrDrivenTree.push({
      key: 'aux', label: DOMAIN_TREE_META.aux.label, icon: DOMAIN_TREE_META.aux.icon,
      children: auxSheets.map(s => ({
        key: `aux_${s.sheet_code || s.addr_id}`,
        label: s.sheet_name || s.sheet_code || s.addr_id,
        icon: '',
        _addrId: s.addr_id,
      })),
    })
  }

  // ── 扩展节点（非五域核心，保留合并/表间/数据质量规则） ──
  // 合并报表（收敛为 ACNR report 域子集；保留为独立入口方便审计师直达）
  acnrDrivenTree.push({
    key: 'consol_report', label: '合并报表', icon: '🔗', children: [
      { key: 'consol_report_bs', label: '合并资产负债表', icon: '' },
      { key: 'consol_report_is', label: '合并利润表', icon: '' },
    ],
  })

  // 合并工作底稿
  acnrDrivenTree.push({
    key: 'consolidation', label: '合并工作底稿', icon: '🔗', children: [
      { key: 'consol_info', label: '基本信息表', icon: '', _consolSheet: 'info' },
      { key: 'consol_cost', label: '投资明细-成本法和公允值', icon: '', _consolSheet: 'cost' },
      { key: 'consol_equity_inv', label: '投资明细-权益法', icon: '', _consolSheet: 'equity_inv' },
      { key: 'consol_net_asset', label: '净资产表', icon: '', _consolSheet: 'net_asset' },
      { key: 'consol_equity_sim', label: '模拟权益法', icon: '', _consolSheet: 'equity_sim' },
      { key: 'consol_elimination', label: '合并抵消分录', icon: '', _consolSheet: 'elimination' },
      { key: 'consol_capital', label: '资本公积变动', icon: '', _consolSheet: 'capital' },
    ],
  })

  // 表间审核
  acnrDrivenTree.push({
    key: 'cross_check', label: '表间审核', icon: '🔗', children: [
      { key: 'cross_report_note', label: '报表 ↔ 附注', icon: '🔄', children: crossCheckItems.value.report_note },
      { key: 'cross_report_wp', label: '报表 ↔ 底稿', icon: '🔄', children: crossCheckItems.value.report_wp },
      { key: 'cross_note_wp', label: '附注 ↔ 底稿', icon: '🔄', children: crossCheckItems.value.note_wp },
      { key: 'cross_consol', label: '合并 ↔ 报表', icon: '🔄', children: [
        { key: 'cross_cr_1', label: '合并抵消分录 ↔ 合并试算表', icon: '📌' },
        { key: 'cross_cr_2', label: '模拟权益法 ↔ 净资产表', icon: '📌' },
        { key: 'cross_cr_3', label: '资本公积变动 ↔ 合并报表', icon: '📌' },
      ]},
    ],
  })

  // 数据质量规则（外链）
  acnrDrivenTree.push({
    key: 'data_quality', label: '数据质量规则', icon: '📐',
    _isExternalLink: true,
    _externalRoute: '/ledger-import/validation-rules',
    children: [
      { key: 'dq_l1', label: 'L1 基础格式校验', icon: '📌', _isExternalLink: true, _externalRoute: '/ledger-import/validation-rules' },
      { key: 'dq_l2', label: 'L2 逻辑一致性', icon: '📌', _isExternalLink: true, _externalRoute: '/ledger-import/validation-rules' },
      { key: 'dq_l3', label: 'L3 跨表核对', icon: '📌', _isExternalLink: true, _externalRoute: '/ledger-import/validation-rules' },
    ],
  })

  return acnrDrivenTree
})

function countFormulas(reportType: string): number {
  return (allRowsMap.value[reportType] || []).filter(r => r.formula).length
}

// ── 表间审核自定义规则 ──
// ── 表间审核规则（动态从 logic_check API 加载，项目不同规则不同） ──
const crossCheckItems = ref<Record<string, any[]>>({
  report_note: [],
  report_wp: [],
  note_wp: [],
})
const crossCheckLoaded = ref(false)

async function loadCrossCheckItems() {
  if (crossCheckLoaded.value || !props.projectId) return
  try {
    const data = await api.get(projectFormula.reportCrossCheck(props.projectId), {
      _silent: true,  // 404 不弹全局错误 toast
    } as any)
    const rules: any[] = Array.isArray(data) ? data : (data?.data?.rules ?? data?.data?.items ?? data?.rules ?? data?.items ?? [])
    if (rules.length) {
      // 按勾稽类型分组（source_domain ↔ target_domain）
      const grouped: Record<string, any[]> = { report_note: [], report_wp: [], note_wp: [] }
      for (const rule of rules) {
        const src = rule.source_domain || rule.source_type || ''
        const tgt = rule.target_domain || rule.target_type || ''
        const label = rule.description || rule.label || `${rule.source_label || src} = ${rule.target_label || tgt}`
        const item = {
          key: `cross_${rule.id || rule.rule_id || Math.random().toString(36).slice(2, 8)}`,
          label,
          icon: rule.status === 'pass' ? '✅' : rule.status === 'fail' ? '❌' : '📌',
          _ruleId: rule.id || rule.rule_id,
          _status: rule.status,
        }
        // 分类到对应分组
        if ((src === 'report' && tgt === 'note') || (src === 'note' && tgt === 'report')) {
          grouped.report_note.push(item)
        } else if ((src === 'report' && tgt === 'wp') || (src === 'wp' && tgt === 'report')) {
          grouped.report_wp.push(item)
        } else if ((src === 'note' && tgt === 'wp') || (src === 'wp' && tgt === 'note')) {
          grouped.note_wp.push(item)
        } else {
          // 无法分类的放到 report_note（兜底）
          grouped.report_note.push(item)
        }
      }
      crossCheckItems.value = grouped
      crossCheckLoaded.value = true
      return
    }
  } catch { /* 降级到静态 */ }
  // 降级：API 不可用时使用静态示例
  crossCheckItems.value = {
    report_note: [
      { key: 'cross_rn_1', label: 'BS货币资金 = 附注货币资金合计', icon: '📌' },
      { key: 'cross_rn_2', label: 'BS应收账款 = 附注应收账款合计', icon: '📌' },
      { key: 'cross_rn_3', label: 'IS营业收入 = 附注营业收入合计', icon: '📌' },
    ],
    report_wp: [
      { key: 'cross_rw_1', label: 'BS货币资金 = E1-1审定数', icon: '📌' },
      { key: 'cross_rw_2', label: 'BS应收账款 = D2-1审定数', icon: '📌' },
    ],
    note_wp: [
      { key: 'cross_nw_1', label: '附注货币资金 = E1-1审定数', icon: '📌' },
    ],
  }
  crossCheckLoaded.value = true
}

// ── 数据加载 ──
const allRowsMap = ref<Record<string, any[]>>({})
const loadingData = ref(false)
const showFormulaImport = ref(false)

// 公式执行结果缓存（独立于行数据，确保响应式）
const formulaResults = ref<Record<string, { value: number | null; trace: any[] }>>({})

const notePresetFormulas = ref<any[]>([])

// ── 底稿(wp)节点公式：从 GET /api/workpapers/{wp_id}/formulas 加载（含 wp_formula 网格公式、
//    专属组件取数公式 surfaced、D-cycle 四表提取 extraction）。此前底稿节点无加载分支恒空。 ──
const wpFormulaRows = ref<any[]>([])

// ── tb_detail「科目明细」公式覆盖 + 自定义新增（持久化于 wizard_state.tb_detail_formulas）──
const tbDetailOverrides = ref<Record<string, any>>({})
const tbDetailAdded = ref<any[]>([])
// 第三级兜底：当 addrStore.tbAddresses 和 props.rows 都为空时，从 API 拉取试算表科目列表
const tbDetailFallbackAccounts = ref<Array<{ code: string; name: string }>>([])

async function loadTbDetailFormulas() {
  if (!props.projectId) return
  try {
    const data: any = await api.get(reportConfigFormula.tbDetail(props.projectId), {
      _silent: true, validateStatus: (s: number) => s < 600,
    } as any)
    tbDetailOverrides.value = data?.overrides || {}
    tbDetailAdded.value = Array.isArray(data?.added) ? data.added : []
  } catch { /* silent */ }
  // 当 addrStore.tbAddresses 和 props.rows 都为空时，从试算表 API 拉科目作兜底
  if (!(addrStore.loaded && addrStore.tbAddresses.length > 0) && !(props.rows && props.rows.length > 0) && !tbDetailFallbackAccounts.value.length) {
    try {
      const tbData: any = await api.get(`/api/projects/${props.projectId}/trial-balance`, {
        params: { year: props.year || new Date().getFullYear() },
        _silent: true, validateStatus: (s: number) => s < 600,
      } as any)
      const items = Array.isArray(tbData) ? tbData : (tbData?.items || tbData?.data || [])
      if (Array.isArray(items) && items.length) {
        tbDetailFallbackAccounts.value = items.map((r: any) => ({
          code: r.standard_account_code || r.account_code || '',
          name: r.account_name || '',
        })).filter((r: { code: string }) => r.code)
      }
    } catch { /* silent fallback */ }
  }
}

async function persistTbDetailFormulas() {
  if (!props.projectId) return
  try {
    await api.put(reportConfigFormula.tbDetail(props.projectId), {
      overrides: tbDetailOverrides.value,
      added: tbDetailAdded.value,
    }, { validateStatus: (s: number) => s < 600 })
  } catch (e) { handleApiError(e, '保存失败') }
}
const wpFormulaLoading = ref(false)
const wpFormulaError = ref('')
/** 「调用页给了具体 sheet 但坐标目录里定位不到」的显式告警（≠ 加载失败，≠ 全册视图）。 */
const wpSheetLocateMiss = ref('')
let wpRequest = 0
let dialogSession = 0
const formulaSubject = () => JSON.stringify([props.wpId, props.projectId, props.year])
const selectedWpCode = ref('')
const selectedWpSheetCode = ref('')

function normalizeWpCode(value: string): string {
  return (value || '').trim().toLowerCase().replace(/—/g, '-').replace(/_/g, '-')
}

function normalizeWpSheetCode(sheetName: string, _wpCode: string): string {
  return normalizeWpCode(sheetName)
}

function normalizeSheetToken(value: string): string {
  return normalizeWpCode(value).replace(/^wp-|^sheet-/, '')
}

function matchSheetCode(actual: string, expected: string): boolean {
  const a = normalizeSheetToken(actual)
  const b = normalizeSheetToken(expected)
  if (!a || !b) return false
  return a === b || a.includes(b) || b.includes(a)
}

function matchesWpExtractionSheet(row: any, sheetCode: string, wpCode: string): boolean {
  if (!sheetCode) return true
  if (row?.sheet_name) return matchSheetCode(String(row.sheet_name), sheetCode)
  // 兼容部分 D 循环 extractor 只给 anchor（如 D6-1-tb-amount）而无 sheet_name。
  const anchor = normalizeWpCode(String(row?.anchor || row?.target_cell || ''))
  return !!anchor && (anchor.startsWith(normalizeWpCode(sheetCode)) || anchor.includes(normalizeWpCode(sheetCode)))
}

/** 宿主 render-config 下发的 sheet 集（归一化）；未下发时为空集 = 退回前缀口径。 */
const hostSheetCodeSet = computed<Set<string>>(
  () => new Set((props.hostSheetCodes || []).map((c) => normalizeWpCode(c)).filter(Boolean)),
)

/** 该 ACNR 条目的 sheet 名/别名/编码是否指向 `sheetName` 这一页。 */
function matchesSheetIdentity(s: AcnrSheetEntry, sheetName: string): boolean {
  const canonical = normalizeWpCode(s.sheet_code || '')
  const names = [s.sheet_name, ...(s.sheet_name_aliases || [])].filter(Boolean).map(String)
  const normalizedName = normalizeWpCode(sheetName)
  return names.includes(sheetName)
    || (!!canonical && normalizedName === canonical)
    || (!!canonical && normalizedName.endsWith(canonical))
}

/**
 * 把调用页的 sheet 名解析成 ACNR 目录条目。
 *
 * 两轮匹配：
 *  1. 宿主自有页 —— ACNR 的 `parent_wp_code` 与宿主 wp_code 同源（原有口径，优先）。
 *  2. 跨循环共享页 —— 不限 parent，但要求该页在宿主 render-config 的 sheet 集里。
 *     🔴 第 2 轮是 D0-2 缺陷的修复点：`核实被函证单位信息D0-2` 的 ACNR 父是 D0、
 *     宿主是 D2，第 1 轮必然落空；此前落空后会退回 D2 父节点并被当成命中，
 *     导致左树停在 D2、右侧列出全册（含 D2-1）公式。
 * 两轮都要求唯一命中，避免同名页误定位。
 */
function resolveCurrentWpSheet(sheets: AcnrSheetEntry[], wpCode: string, sheetName: string) {
  const name = (sheetName || '').trim()
  if (!name) return null
  const requested = normalizeWpCode(wpCode)
  const wpSheets = sheets.filter((s) => s.domain === 'wp')

  const owned = wpSheets.filter((s) => {
    const parent = normalizeWpCode(s.parent_wp_code || s._wpCode || '')
    if (!(parent === requested || requested.startsWith(`${parent}-`))) return false
    return matchesSheetIdentity(s, name)
  })
  if (owned.length === 1) return owned[0]

  // 第 2 轮：宿主册内的共享页（归属真源 = render-config 的 sheet 集）
  if (!hostSheetCodeSet.value.size) return null
  const shared = wpSheets.filter((s) => {
    const canonical = normalizeWpCode(s.sheet_code || '')
    if (!canonical || !hostSheetCodeSet.value.has(canonical)) return false
    return matchesSheetIdentity(s, name)
  })
  return shared.length === 1 ? shared[0] : null
}

/**
 * 在树中定位「底稿域 > 指定 wp_code > 指定 sheet」的节点。
 * 用于从底稿页打开公式管理时直接落到该页（用户诉求：左侧定位到该底稿节点、
 * 右侧只显示该页公式）。未命中返回 null（保留全册视图，零回归）。
 *
 * 树实际结构是三层：底稿域 > 循环 > 底稿(wp_code) > sheet，
 * 底稿父节点位于「循环」之下而非域根的直接子节点 —— 必须下钻一层，
 * 否则永远找不到父节点（此前的缺陷：只查一层 ⇒ 定位恒失败、右侧恒 No Data）。
 * 同时兼容循环层缺失（域根直接挂底稿）的退化结构。
 */
function resolveWpSheetNode(wpCode: string, sheetName: string): any | null {
  const resolvedSheet = sheetName ? resolveCurrentWpSheet(acnrSheets.value, wpCode, sheetName) : null
  const wantSheet = resolvedSheet ? normalizeWpCode(resolvedSheet.sheet_code) : ''
  // 共享页的树节点挂在它的原生工作簿下（D0-2 在 D0 名下），按真实归属找，
  // 否则只在宿主(D2)子树里找必然落空。
  const ownerWpCode = resolvedSheet
    ? normalizeWpCode(resolvedSheet.parent_wp_code || resolvedSheet._wpCode || wpCode)
    : ''
  const keyOf = (n: any) => String(n?.key || '').toLowerCase()
  const same = (a: string, b: string) => (a || '').trim().toLowerCase() === (b || '').trim().toLowerCase()
  const normalizeCode = (value: string) => (value || '').trim().toLowerCase().replace(/—/g, '-').replace(/_/g, '-')
  const requestedCode = normalizeCode(wpCode)

  const workpaper = treeData.value.find((n) => keyOf(n) === 'workpaper')
  const roots: any[] = workpaper?.children?.length ? workpaper.children : []
  if (!roots.length) return null
  if (!wpCode) return null

  // 域根的直接子节点，或（循环层存在时）循环的子节点，都是底稿父节点
  const wpNodes: any[] = []
  for (const c of roots) {
    const isCycle = String(c?.key || '').startsWith('wp_cycle_')
    if (isCycle) {
      for (const pc of c.children || []) wpNodes.push(pc)
    } else {
      wpNodes.push(c)
    }
  }
  // 先精确查找具体页：只接受 catalog 中真实存在的 _sheetCode，不用自由文本正则猜测。
  if (wantSheet) {
    const want = normalizeCode(wantSheet)
    for (const parent of wpNodes) {
      const parentCode = normalizeCode(parent?._wpCode || '')
      const belongsToParent = parentCode === requestedCode
        || requestedCode.startsWith(`${parentCode}-`)
        || (!!ownerWpCode && parentCode === ownerWpCode)
      if (!belongsToParent) continue
      const child = (parent.children || []).find((c: any) => {
        const catalogCode = normalizeCode(c?._sheetCode || '')
        const extracted = normalizeCode(normalizeWpSheetCode(sheetName, parent?._wpCode || wpCode))
        return !!catalogCode && (catalogCode === want || catalogCode === extracted)
      })
      if (child) return child
    }
  }

  const parent = wpNodes.find((n) => n && n._wpCode && same(n._wpCode, wpCode))
    || wpNodes.find((n) => n && n._wpCode && requestedCode.startsWith(`${normalizeCode(n._wpCode)}-`))
  if (!parent) return null
  return parent
}

async function loadWpFormulas(wpCode: string, sheetCode: string) {
  const request = ++wpRequest
  const session = dialogSession
  const subject = formulaSubject()
  const isCurrent = () => visible.value && request === wpRequest && session === dialogSession && subject === formulaSubject()
  wpFormulaRows.value = []
  wpFormulaError.value = ''
  wpFormulaLoading.value = false
  // 加载身份 = 宿主实例（props.wpId）。共享页（D2 册内的 D0-2）的 wpCode 是它的
  // 原生工作簿 D0，但公式确实存在当前实例里 ⇒ 只要该页在宿主 sheet 集内就放行；
  // 真正的外册（不在本册 sheet 集）仍然拒绝，避免用本实例 id 加载别册公式。
  const isHostWorkbook = normalizeWpCode(wpCode) === normalizeWpCode(props.wpCode || '')
  const isHostSheet = !!sheetCode && hostSheetCodeSet.value.has(normalizeWpCode(sheetCode))
  if (!props.wpId || !props.projectId || !(isHostWorkbook || isHostSheet)) {
    wpFormulaError.value = '缺少匹配的底稿实例，请从目标底稿页面打开公式管理。'
    return
  }
  wpFormulaLoading.value = true
  try {
    const data: any = await api.get(wpFormula.list(props.wpId))
    const rows: any[] = []
    for (const it of (data?.items || [])) {
      // 用户 wp_formula 行按 sheet 过滤：选中具体 sheet 时只留该 sheet 的公式
      // （未选具体 sheet = 工作簿级视图，恒显示），避免把全册其他页公式混进本页。
      // sheet_name 是自由字符串（可能是中文页名或编码），故用「编码相等 OR 编码包含」
      // 双口径，避免严格相等把中文页名的公式误滤掉。
      if (sheetCode) {
        const sc = normalizeWpSheetCode(sheetCode, wpCode)
        const sn = normalizeWpSheetCode(String(it.sheet_name || ''), wpCode)
        // 双口径：编码相等 OR 双向包含。items 的 sheet_name 是自由字符串（可能存中文页名），
        // 严格相等会把中文页名的公式误滤掉；无 sheet 标识的行无法归属到具体页，本页视图下丢弃。
        if (!sn || !matchSheetCode(sn, sc)) continue
      }
      rows.push({
        id: it.id, row_code: it.target_cell || it.sheet_name || '', row_name: it.sheet_name || '',
        formula: it.formula || it.expression || '', formula_category: it.formula_category || '取数',
        formula_description: it.formula_description || '', formula_source: '底稿公式(wp_formula)',
      })
    }
    // surfaced 按选中 sheet 过滤：条目带 sheet_codes（归属 sheet 列表）时，仅在选中该 sheet
    // 时显示；无 sheet_codes（工作簿级）恒显示；未选具体 sheet（父节点）显示全部。
    for (const s of (data?.surfaced || [])) {
      const scs = s.sheet_codes
      if (sheetCode) {
        const sc = normalizeWpSheetCode(sheetCode, wpCode)
        // 条目带 sheet_codes（归属 sheet 列表）时，仅在选中该 sheet 时显示；
        // 无 sheet_codes（工作簿级）恒显示，避免误把全局公式算成本页。
        if (Array.isArray(scs) && scs.length && !scs.some((c: string) => matchSheetCode(c, sc))) continue
      }
      rows.push({ ...s })
    }
    // extraction 按选中 sheet 过滤，但不因选了具体页就丢弃整段四表库溯源。
    // D 循环 Tier A/B 常以 workbook 级对象返回，真实归属写在每项 sheet_name；
    // 若继续只在未选 sheet 时展示，D6-1 这类「有 surfaced / extraction、无 wp_formula」
    // 的底稿会在本页视图恒空。
    const ex = data?.extraction
    for (const b of (ex?.tierA || [])) {
      if (!matchesWpExtractionSheet(b, sheetCode, wpCode)) continue
      rows.push({
        id: b.id || `tierA-${b.anchor || b.target_cell || rows.length}`, row_code: b.target_cell || b.anchor || '', row_name: b.label || '',
        formula: b.expression || '', formula_category: '取数',
        formula_description: b.semantic || b.note || '', formula_source: '四表提取(Tier A)',
      })
    }
    for (const b of (ex?.tierB || [])) {
      if (!matchesWpExtractionSheet(b, sheetCode, wpCode)) continue
      rows.push({
        id: `tierB-${b.anchor || rows.length}`, readonly: true, row_code: b.anchor || '', row_name: b.label || '',
        formula: b.description || b.expression || '', formula_category: '只读溯源',
        formula_description: b.semantic || '', formula_source: 'Tier B 溯源',
      })
    }
    // 防御：任何缺 id 的只读行补稳定 id，避免 editingId(null)===row.id(null) 误触发编辑输入框（公式列变空）
    if (isCurrent()) wpFormulaRows.value = rows.map((r, i) => (r.id == null ? { ...r, id: `wpf-${i}` } : r))
  } catch {
    if (isCurrent()) wpFormulaError.value = '底稿公式加载失败，请检查权限或网络后重新打开。'
  } finally {
    if (isCurrent()) wpFormulaLoading.value = false
  }
}

async function loadRowsForNode(nodeKey: string) {
  // 底稿(wp)节点：解析 wp_id → 加载该底稿取数公式（含专属组件 surfaced）
  if (nodeKey.startsWith('wp_') && selectedWpCode.value) {
    await loadWpFormulas(selectedWpCode.value, selectedWpSheetCode.value)
    return
  }
  // 试算平衡表节点：tb_detail 用 props.rows + 加载覆盖/自定义；tb_summary 加载 report_config
  if (nodeKey === 'tb_detail') {
    // 科目明细预设来自 props.rows，另加载用户覆盖 + 自定义新增
    loadTbDetailFormulas()
    return
  }
  if (nodeKey === 'tb_summary') {
    // 加载资产负债表的 report_config 作为试算平衡表行次
    nodeKey = 'report_balance_sheet'
  }
  if (nodeKey === 'tb_summary') {
    // 加载资产负债表的 report_config 作为试算平衡表行次
    nodeKey = 'report_balance_sheet'
  }

  if (nodeKey.startsWith('report_')) {
    const reportType = nodeKey.replace('report_', '')
    const cacheKey = `${fmTemplateType.value}_${reportType}`
    if (allRowsMap.value[cacheKey]) {
      allRowsMap.value[reportType] = allRowsMap.value[cacheKey]
      return
    }
    loadingData.value = true
    try {
      const rows = await fetchReportRows(reportType)
      allRowsMap.value[reportType] = rows
      allRowsMap.value[cacheKey] = rows
    } catch { /* ignore */ }
    finally { loadingData.value = false }
  }
}

/** 在树数据中递归查找目标 key 的祖先链（含该节点自身），未找到返回 []。 */
function findNodePath(nodes: any[], key: string, trail: any[] = []): any[] {
  for (const n of nodes || []) {
    const nextTrail = [...trail, n]
    if (n.key === key) return nextTrail
    if (n.children?.length) {
      const found = findNodePath(n.children, key, nextTrail)
      if (found.length) return found
    }
  }
  return []
}

/**
 * 从 sessionStorage `gt-formula-target-node` 读取目标节点（由外部入口如底稿页
 * openFormulaManager 写入，如 wp_e1_1），打开弹窗后自动展开祖先 + 选中 + 加载其公式，
 * 让用户从审定表点「公式管理」直接落到该底稿 sheet 节点，无需再手动切换。
 */
async function applyTargetNode(explicitTarget?: string): Promise<boolean> {
  const session = dialogSession
  const subject = formulaSubject()
  let target = explicitTarget || ''
  if (!target) {
    try { target = sessionStorage.getItem('gt-formula-target-node') || '' } catch { /* ignore */ }
    if (!target) return false
    try { sessionStorage.removeItem('gt-formula-target-node') } catch { /* ignore */ }
  }
  // 底稿域树来自 ACNR catalog、附注域树来自项目附注 API，均需先加载完成（idempotent）
  await loadAcnrTree()
  if (target.startsWith('note_')) await loadNoteTree()
  await nextTick()
  if (!visible.value || session !== dialogSession || subject !== formulaSubject()) return false
  const path = findNodePath(treeData.value, target)
  if (!path.length) return false  // 未匹配（如附注/程序表 sheet_code 不对应）→ 保持默认，不打断
  const node = path[path.length - 1]
  const isLeaf = !node.children || node.children.length === 0
  // 叶子 → 展开到父；父节点 → 展开自身使子节点可见
  const toExpand = isLeaf ? path.slice(0, -1) : path
  expandedKeys.value = [...new Set([...expandedKeys.value, ...toExpand.map((n) => n.key)])]
  await nextTick()
  try { fmTreeRef.value?.setCurrentKey(target) } catch { /* ignore */ }
  // 叶子节点触发与 onTreeNodeClick 一致的选择逻辑（设 selectedWpCode/SheetCode + 加载公式）
  if (isLeaf) onTreeNodeClick(node)
  return true
}

/**
 * 附注域打开时定位到调用页当前章节（Fix：此前默认停在「报表 > 资产负债表」）。
 *
 * 优先按 note_section 精确定位到树节点；无章节上下文（如全局 ƒx 入口）或章节未在树中
 * （附注尚未生成）时，退到「附注」域根节点，也不会跑到报表域。
 */
async function applyNoteScopeTarget() {
  await loadNoteTree()
  const sectionId = (props.noteSection || '').trim()
  if (sectionId) {
    const hit = await applyTargetNode(noteSectionToNodeKey(sectionId))
    if (hit) return
  }
  // 兜底：停在附注域根节点，展开可见，面包屑显示附注（含章节标题，若有）
  selectedNodeKey.value = 'note'
  selectedPath.value = props.noteSectionTitle
    ? `附注 > ${props.noteSectionTitle}`
    : '附注'
  expandedKeys.value = [...new Set([...expandedKeys.value, 'note'])]
  if (!notePresetFormulas.value.length) await onImportPresetFormulas()
  await nextTick()
  try { fmTreeRef.value?.setCurrentKey('note') } catch { /* ignore */ }
}

/**
 * 合并工作底稿打开时定位到当前 worksheet（此前入口只传 nodeKey，
 * 无 wpId 会被兜底成「报表 > 资产负债表」，右侧显示的也不是本页公式）。
 *
 * 合并模块是项目级的，没有普通底稿实例，故身份 = projectId + year + 当前 worksheet。
 * 本模块 sheet key（info/cost/elimination…）对应树节点 `consol_{key}`；
 * 树中不存在该页（如内部抵消类尚未建节点）时退到合并工作底稿域根，不跑到报表域。
 */
async function applyConsolWorksheetTarget() {
  await loadAcnrTree()
  const sheet = (props.sheetName || '').trim()
  if (sheet) {
    const hit = await applyTargetNode(`consol_${sheet}`)
    if (hit) return
  }
  selectedNodeKey.value = 'consolidation'
  selectedPath.value = '合并工作底稿'
  expandedKeys.value = [...new Set([...expandedKeys.value, 'consolidation'])]
  await nextTick()
  try { fmTreeRef.value?.setCurrentKey('consolidation') } catch { /* ignore */ }
}

// 初始加载当前报表的数据
watch([visible, () => props.wpId, () => props.wpCode, () => props.projectId, () => props.year, () => props.sheetName], async ([v]) => {
  ++dialogSession
  ++wpRequest
  wpFormulaLoading.value = false
  if (v) {
    activeCategory.value = 'all'
    uriSearchQuery.value = ''
    selectedRows.value = []
    editingId.value = null
    wpFormulaRows.value = []
    wpFormulaError.value = ''
    wpSheetLocateMiss.value = ''
    if (props.wpId || props.scope === 'workpaper') {
      selectedWpCode.value = props.wpCode || ''
      selectedWpSheetCode.value = ''
      selectedNodeKey.value = 'wp_current_workbook'
      selectedPath.value = `底稿 > ${props.wpCode || props.wpId || '未知底稿'} > 全册（当前位置：${props.sheetName || '全册'}；${props.year || ''}年度）`
      // 先加载 WP 域树（ACNR catalog），再按 sheet 名定位到具体节点；
      // 未命中（sheet 名与 catalog 不匹配）时退回全册视图，保证零回归。
      try {
        await loadAcnrTree()
      } catch { /* ACNR 树加载失败不阻断实例级公式加载 */ }
      if (!visible.value || props.wpCode !== (selectedWpCode.value || '')) return
      const targetNode = props.sheetName
        ? resolveWpSheetNode(props.wpCode || '', props.sheetName)
        : null
      // 🔴 只有拿到具体页（_sheetCode 非空）才算定位成功。父节点（_sheetCode 为空）
      // 曾被当成命中，面包屑却回落到 props.sheetName 显示成本页 —— 于是「面包屑对、
      // 左树停在父节点、右侧是全册公式」，把定位失败伪装成成功。
      if (targetNode && targetNode._sheetCode) {
        const ownerWpCode = String(targetNode._wpCode || props.wpCode || '')
        const sharedFromOtherWorkbook =
          normalizeWpCode(ownerWpCode) !== normalizeWpCode(props.wpCode || '')
        selectedNodeKey.value = targetNode.key
        // 加载身份恒为宿主实例（公式存在 props.wpId 这一册里），共享页也不例外
        selectedWpCode.value = props.wpCode || ownerWpCode
        selectedWpSheetCode.value = targetNode._sheetCode || ''
        selectedPath.value = sharedFromOtherWorkbook
          ? `底稿 > ${props.wpCode || '未知底稿'} > ${targetNode._sheetCode}（共享自 ${ownerWpCode}）`
          : `底稿 > ${ownerWpCode || '未知底稿'} > ${targetNode._sheetCode}`
        await nextTick()
        // 展开到该叶子节点的全部祖先（workpaper → 循环 → 底稿），否则 D 销售循环
        // 折叠态下用户看不到「定位到了哪」——只加 'workpaper' 是此前定位失效的观感来源。
        const path = findNodePath(treeData.value, targetNode.key)
        expandedKeys.value = [...new Set([...expandedKeys.value, ...path.slice(0, -1).map((n) => n.key)])]
        await nextTick()
        try { fmTreeRef.value?.setCurrentKey(targetNode.key) } catch { /* ignore */ }
      } else {
        // 未命中具体页 → 落到该底稿父节点（工作簿级，显示全册公式）
        const parentNode = resolveWpSheetNode(props.wpCode || '', '')
        selectedNodeKey.value = parentNode?.key || 'workpaper'
        selectedPath.value = `底稿 > ${props.wpCode || props.wpId || '未知底稿'} > 全册（当前位置：${props.sheetName || '全册'}；${props.year || ''}年度）`
        // 「调用页带了具体 sheet 却定位不到」与「本就是工作簿级视图」是两种状态：
        // 前者必须显式告警，否则用户会把全册公式当成本页公式（D0-2 缺陷的观感来源）。
        if (props.sheetName) {
          wpSheetLocateMiss.value = `未能在坐标目录中定位当前页「${props.sheetName}」，`
            + `已退回 ${props.wpCode || '本底稿'} 全册视图 —— 下表不是本页公式，请核对页名或坐标目录。`
        }
        await nextTick()
        expandedKeys.value = [...new Set([...expandedKeys.value, 'workpaper'])]
        await nextTick()
        try { fmTreeRef.value?.setCurrentKey(selectedNodeKey.value) } catch { /* ignore */ }
      }
      await loadWpFormulas(selectedWpCode.value, selectedWpSheetCode.value)
      return
    }
    selectedNodeKey.value = 'report_balance_sheet'
    selectedPath.value = '报表 > 资产负债表'
    // 同步 scope 到 sessionStorage（与 ThreeColumnLayout 全局入口保持一致）
    try {
      sessionStorage.setItem('gt-formula-scope', props.scope || 'report')
    } catch { /* sessionStorage 不可用时忽略 */ }
    // 模板版本跟随调用页（上市版页面不应加载国企版预设）；弹窗内手动切换仅本次有效
    const pageTemplate = normalizeTemplateType(props.templateType)
    if (props.templateType && fmTemplateType.value !== pageTemplate) {
      fmTemplateType.value = pageTemplate
      allRowsMap.value = {}
      notePresetFormulas.value = []
      noteTreeLoaded.value = false
      noteTreeChildren.value = []
    }
    // Req 24.1: 按当前 scope 加载本域公式（不含他域），来源地址经 ACNR 规范化
    loadScopeFormulas()
    // 加载动态附注树
    loadNoteTree()
    // 加载 ACNR 五域导航树（底稿域动态从 catalog 构建）
    loadAcnrTree()
    // 加载报表类型（项目级动态）
    loadReportTypes()
    // 加载表间审核规则（项目级动态）
    loadCrossCheckItems()
    if (props.scope === 'tb') {
      // 试算表页打开 → 定位「科目明细」节点，用 TB() 预设 + 覆盖/自定义（props.rows 提供科目来源）。
      // props.rows 是试算表行（standard_account_code/account_name），不是报表行次（无 row_code），
      // 故不能走下方报表启发式（否则被误判为 report_balance_sheet 而公式列全空、树也定位不到）。
      selectedNodeKey.value = 'tb_detail'
      selectedPath.value = '试算平衡表 > 科目明细'
      await loadTbDetailFormulas()
      await nextTick()
      expandedKeys.value = [...new Set([...expandedKeys.value, 'trial_balance'])]
      await nextTick()
      try { fmTreeRef.value?.setCurrentKey('tb_detail') } catch { /* ignore */ }
    } else if (props.scope === 'consol_worksheet') {
      // 合并工作底稿：项目级入口，按当前 worksheet 定位（无 wpId 不代表无当前页）
      await applyConsolWorksheetTarget()
    } else if (props.scope === 'note' || props.scope === 'consol_note') {
      // 附注页打开 → 定位到调用页当前章节节点。
      // props.rows 是附注表格行（row_code 形如「五、1-R1」），不能走下方报表启发式，
      // 否则前缀全不匹配被兜底成 report_balance_sheet，弹窗默认显示资产负债表公式。
      await applyNoteScopeTarget()
    } else if (props.rows?.length) {
      // 报表页传入 report_config 行次（row_code 如 BS-001）→ 定位对应报表节点
      const firstCode = props.rows[0]?.row_code || ''
      let rt = 'balance_sheet'
      if (firstCode.startsWith('IS-')) rt = 'income_statement'
      else if (firstCode.startsWith('CFS-')) rt = 'cash_flow_statement'
      else if (firstCode.startsWith('EQ-')) rt = 'equity_statement'
      else if (firstCode.startsWith('CFSS-')) rt = 'cash_flow_supplement'
      else if (firstCode.startsWith('IMP-')) rt = 'impairment_provision'
      const nodeKey = `report_${rt}`
      selectedNodeKey.value = nodeKey
      selectedPath.value = `报表 > ${REPORT_SUBTYPE_LABELS_FALLBACK[rt] || rt}`
      // 从 API 加载含公式的完整 report_config（props.rows 可能无 formula 字段）
      await loadRowsForNode(nodeKey)
      // 展开「报表」父节点 + 高亮当前报表类型节点
      await nextTick()
      expandedKeys.value = [...new Set([...expandedKeys.value, 'report'])]
      await nextTick()
      try { fmTreeRef.value?.setCurrentKey(nodeKey) } catch { /* ignore */ }
    }
    // 外部入口指定目标节点（如底稿页跳转 wp_e1_1）→ 自动展开+选中+加载公式
    applyTargetNode()
  }
})

function onTreeNodeClick(data: any) {
  // 外链节点: 跳转到独立页面
  if (data._isExternalLink && data._externalRoute) {
    ElMessageBox.confirm(
      `即将跳转到「${data.label}」独立页面查看/编辑。\n\n当前公式管理弹窗的未保存修改将丢失,是否继续?`,
      '跳转确认',
      { confirmButtonText: '跳转', cancelButtonText: '取消', type: 'info' }
    ).then(() => {
      visible.value = false
      router.push(data._externalRoute)
    }).catch(() => {})
    return
  }

  if (!data.children || data.children.length === 0) {
    selectedNodeKey.value = data.key
    // 构建路径
    if (data.key.startsWith('tb_')) {
      selectedPath.value = `试算平衡表 > ${data.label}`
    } else if (data.key.startsWith('report_')) {
      selectedPath.value = `报表 > ${data.label}`
    } else if (data.key.startsWith('note_')) {
      selectedPath.value = `附注 > ${data._sectionTitle || data.label}`
      if (!notePresetFormulas.value.length) {
        onImportPresetFormulas()
      }
    } else if (data.key.startsWith('wp_')) {
      selectedPath.value = `底稿 > ${data.label}`
      selectedWpCode.value = data._wpCode || ''
      selectedWpSheetCode.value = data._sheetCode || ''
    } else if (data._consolSheet) {
      // 合并工作底稿页（带 _consolSheet 元数据）与合并报表同为 consol_ 前缀，
      // 但域名不同：不区分会让审计师在合并工作底稿页看到「合并报表 > …」的错误位置。
      selectedPath.value = `合并工作底稿 > ${data.label}`
    } else if (data.key.startsWith('consol_')) {
      selectedPath.value = `合并报表 > ${data.label}`
    } else if (data.key.startsWith('cross_')) {
      selectedPath.value = `表间审核 > ${data.label}`
    }
    loadRowsForNode(data.key)
  }
}

// ── 当前显示的行 ──
const currentRows = computed(() => {
  // 试算平衡表节点
  if (selectedNodeKey.value === 'tb_detail') {
    // 科目明细：按科目生成 TB() 取数预设（分类默认「自动运算」），叠加用户覆盖 + 自定义新增
    // 覆盖/新增持久化于 wizard_state.tb_detail_formulas，避免预设不对且支持二次编辑。
    // R14.6: 候选地址源优先走 Req16 store facade（ACNR-backed）tbAddresses，空/未加载时回退 props.rows。
    // 第三级兜底：从 trial-balance API 拉取的科目列表（全局入口打开时 props.rows 为空）。
    const ov = tbDetailOverrides.value
    const base = (addrStore.loaded && addrStore.tbAddresses.length > 0)
      ? addrStore.tbAddresses.map((e) => ({ code: e.account_code || '', name: e.label || '', computed: undefined as any }))
      : (props.rows && props.rows.length > 0)
        ? props.rows.map((r: any) => ({ code: r.standard_account_code || '', name: r.account_name || '', computed: r.unadjusted_amount }))
        : tbDetailFallbackAccounts.value.map((r) => ({ code: r.code, name: r.name, computed: undefined as any }))
    const rows: any[] = base.map((b) => {
      const o = ov[b.code]
      return {
        id: `tbd-${b.code}`,
        row_code: b.code,
        row_name: b.name,
        formula: (o && o.formula != null) ? o.formula : `TB('${b.code}','期末余额')`,
        formula_category: (o && o.formula_category) ? o.formula_category : 'auto_calc',
        formula_description: (o && o.formula_description != null) ? o.formula_description : '从余额表取期末余额',
        _computed_value: b.computed,
        _tbDetail: true,
        _overridden: !!o,
      }
    })
    // 追加用户自定义新增行
    for (let i = 0; i < tbDetailAdded.value.length; i++) {
      const a = tbDetailAdded.value[i]
      rows.push({
        id: a.row_code ? `tbd-add-${a.row_code}` : `tbd-add-${i}`,
        row_code: a.row_code || '',
        row_name: a.row_name || '',
        formula: a.formula || '',
        formula_category: a.formula_category || 'auto_calc',
        formula_description: a.formula_description || '',
        _computed_value: undefined,
        _tbDetail: true,
        _tbAdded: true,
      })
    }
    return rows
  }
  if (selectedNodeKey.value === 'tb_summary') {
    // 试算平衡表：显示 report_config 的行次公式
    return allRowsMap.value['balance_sheet'] || []
  }

  if (selectedNodeKey.value.startsWith('report_')) {
    const rt = selectedNodeKey.value.replace('report_', '')
    return allRowsMap.value[rt] || []
  }
  // 附注节点：显示该章节的预设公式
  if (isNoteDomainNodeKey(selectedNodeKey.value) && notePresetFormulas.value.length) {
    // 从树节点获取 _sectionTitle / _sectionId
    const nodeKey = selectedNodeKey.value
    let targetTitle = ''
    let targetSectionId = ''

    // 在动态树中查找
    for (const chapter of noteTreeChildren.value) {
      for (const child of (chapter.children || [])) {
        if (child.key === nodeKey) {
          targetTitle = child._sectionTitle || child.label
          targetSectionId = child._sectionId || ''
          break
        }
      }
      if (targetTitle) break
    }
    // 降级到静态树
    if (!targetTitle) {
      for (const group of staticNoteTree) {
        for (const child of (group.children || [])) {
          if (child.key === nodeKey) {
            targetTitle = (child as any)._sectionTitle || child.label
            break
          }
        }
        if (targetTitle) break
      }
    }
    // 树中未命中且当前落在「本页章节」或附注域根节点 → 用调用页传入的章节上下文，
    // 仍能列出本页对应公式（附注未生成/树未加载时也不至于一把倒出全部）。
    // 章级节点（note_chapter_*）不套用，否则点章节会错显示成本页章节的公式。
    if (!targetTitle && !targetSectionId) {
      const propSection = (props.noteSection || '').trim()
      const isPageSectionNode = nodeKey === 'note'
        || (!!propSection && nodeKey === noteSectionToNodeKey(propSection))
      if (isPageSectionNode) {
        targetTitle = (props.noteSectionTitle || '').trim()
        targetSectionId = propSection
      }
    }

    // 章节命中 → 只列本章节公式；章级节点/无上下文 → 列全部（规则见 noteScopeTargeting）
    return buildNoteFormulaRows(notePresetFormulas.value, {
      sectionId: targetSectionId,
      sectionTitle: targetTitle,
    })
  }
  // 合并报表节点：显示对应表样的行结构
  if (selectedNodeKey.value.startsWith('consol_')) {
    return allRowsMap.value[selectedNodeKey.value] || consolSheetRows(selectedNodeKey.value)
  }
  // 底稿(wp)节点：显示该底稿取数公式（wp_formula + 专属组件 surfaced + 四表提取）
  if (selectedNodeKey.value.startsWith('wp_')) {
    return wpFormulaRows.value
  }
  return []
})

const isCrossCheckMode = computed(() => selectedNodeKey.value.startsWith('cross_'))

// 表间审核规则
const crossCheckRulesMap = ref<Record<string, any[]>>({
  cross_report_note: [
    { label: 'BS货币资金 = 附注货币资金合计', left_ref: "REPORT('BS-002','期末')", right_ref: "NOTE('货币资金','合计','期末')", _editing: false },
    { label: 'BS应收账款 = 附注应收账款合计', left_ref: "REPORT('BS-008','期末')", right_ref: "NOTE('应收账款','合计','期末')", _editing: false },
    { label: 'IS营业收入 = 附注营业收入合计', left_ref: "REPORT('IS-002','本期')", right_ref: "NOTE('营业收入','合计','本期')", _editing: false },
  ],
  cross_report_wp: [
    { label: 'BS货币资金 = E1-1审定数', left_ref: "REPORT('BS-002','期末')", right_ref: "WP('E1-1','审定数')", _editing: false },
    { label: 'BS应收账款 = D2-1审定数', left_ref: "REPORT('BS-008','期末')", right_ref: "WP('D2-1','审定数')", _editing: false },
  ],
  cross_note_wp: [
    { label: '附注货币资金 = E1-1审定数', left_ref: "NOTE('货币资金','合计','期末')", right_ref: "WP('E1-1','审定数')", _editing: false },
  ],
  cross_consol: [
    { label: '合并抵消分录借贷平衡', left_ref: "CONSOL('抵消分录','借方合计')", right_ref: "CONSOL('抵消分录','贷方合计')", _editing: false },
    { label: '模拟权益法长投 = 净资产×持股比例', left_ref: "CONSOL('模拟权益法','期末长投小计')", right_ref: "CONSOL('净资产表','期末净资产') × 持股比例", _editing: false },
    { label: '资本公积变动期末 = 合并报表期末', left_ref: "CONSOL('资本公积变动','期末金额')", right_ref: "REPORT('BS-资本公积','期末')", _editing: false },
  ],
})

// ── 合并报表表样行结构（供公式配置用） ──
function consolSheetRows(nodeKey: string): any[] {
  const sheetMap: Record<string, { rows: { code: string; name: string; formula?: string; category?: string; desc?: string }[] }> = {
    consol_info: { rows: [
      { code: 'CI-001', name: '子企业名称' }, { code: 'CI-002', name: '企业代码' },
      { code: 'CI-003', name: '核算科目' }, { code: 'CI-004', name: '核算方式' },
      { code: 'CI-005', name: '持股比例变动' }, { code: 'CI-006', name: '变动次数' },
    ]},
    consol_cost: { rows: [
      { code: 'CC-001', name: '本期现金红利' },
      { code: 'CC-010', name: '期初-投资比例' }, { code: 'CC-011', name: '期初-金额' },
      { code: 'CC-012', name: '期初-减值准备' }, { code: 'CC-013', name: '期初-长投净额' },
      { code: 'CC-020', name: '增加-金额' }, { code: 'CC-021', name: '增加-减值准备' },
      { code: 'CC-030', name: '减少-金额' }, { code: 'CC-031', name: '减少-减值准备' },
      { code: 'CC-040', name: '期末-投资成本' }, { code: 'CC-041', name: '期末-减值准备' },
      { code: 'CC-042', name: '期末-长投净额' }, { code: 'CC-043', name: '期末-公允价值' },
      { code: 'CC-099', name: '成本法小计' },
    ]},
    consol_equity_inv: { rows: [
      { code: 'CE-010', name: '期初-投资比例' }, { code: 'CE-011', name: '期初-长投金额' },
      { code: 'CE-012', name: '期初-减值准备' },
      { code: 'CE-020', name: '增加-投资成本' }, { code: 'CE-021', name: '增加-损益调整' },
      { code: 'CE-022', name: '增加-其他综合收益' }, { code: 'CE-023', name: '增加-其他权益变动' },
      { code: 'CE-024', name: '增加-权益增加小计' },
      { code: 'CE-030', name: '减少-投资成本' }, { code: 'CE-031', name: '减少-分回利润' },
      { code: 'CE-040', name: '期末-投资比例' }, { code: 'CE-041', name: '期末-长投金额' },
      { code: 'CE-042', name: '期末-减值准备' },
      { code: 'CE-099', name: '小计' },
    ]},
    consol_net_asset: { rows: [
      // ── 第1部分：所有者权益变动 ──
      { code: 'CN-S1', name: '所有者权益/股东权益', formula: '', category: '', desc: '分节标题' },
      // 期初
      { code: 'CN-001', name: '期初合计：', formula: 'SUM(CN-002:CN-010)', category: 'auto_calc', desc: '=下方9项之和' },
      { code: 'CN-002', name: '实收资本（或股本）', formula: "TB({company_code},'实收资本','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-003', name: '其他权益工具', formula: "TB({company_code},'其他权益工具','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-004', name: '资本公积', formula: "TB({company_code},'资本公积','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-005', name: '减：库存股', formula: "TB({company_code},'库存股','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-006', name: '其他综合收益', formula: "TB({company_code},'其他综合收益','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-007', name: '专项储备', formula: "TB({company_code},'专项储备','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-008', name: '盈余公积', formula: "TB({company_code},'盈余公积','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-009', name: '△一般风险准备', formula: "TB({company_code},'一般风险准备','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      { code: 'CN-010', name: '未分配利润', formula: "TB({company_code},'未分配利润','期初余额')", category: 'auto_calc', desc: '从子企业试算表提取' },
      // 本期增加
      { code: 'CN-011', name: '本期增加', formula: 'SUM(CN-012:CN-020)', category: 'auto_calc', desc: '=下方9项之和' },
      { code: 'CN-012', name: '实收资本（或股本）', formula: '', category: '', desc: '本期增加-实收资本' },
      { code: 'CN-013', name: '其他权益工具', formula: '', category: '', desc: '本期增加-其他权益工具' },
      { code: 'CN-014', name: '资本公积', formula: '', category: '', desc: '本期增加-资本公积' },
      { code: 'CN-015', name: '减：库存股', formula: '', category: '', desc: '' },
      { code: 'CN-016', name: '其他综合收益', formula: '', category: '', desc: '' },
      { code: 'CN-017', name: '专项储备', formula: '', category: '', desc: '' },
      { code: 'CN-018', name: '盈余公积', formula: '', category: '', desc: '' },
      { code: 'CN-019', name: '△一般风险准备', formula: '', category: '', desc: '' },
      { code: 'CN-020', name: '未分配利润', formula: '', category: '', desc: '' },
      // 本期减少
      { code: 'CN-021', name: '本期减少', formula: 'SUM(CN-022:CN-030)', category: 'auto_calc', desc: '=下方9项之和' },
      { code: 'CN-022', name: '实收资本（或股本）', formula: '', category: '', desc: '' },
      { code: 'CN-023', name: '其他权益工具', formula: '', category: '', desc: '' },
      { code: 'CN-024', name: '资本公积', formula: '', category: '', desc: '' },
      { code: 'CN-025', name: '减：库存股', formula: '', category: '', desc: '' },
      { code: 'CN-026', name: '其他综合收益', formula: '', category: '', desc: '' },
      { code: 'CN-027', name: '专项储备', formula: '', category: '', desc: '' },
      { code: 'CN-028', name: '盈余公积', formula: '', category: '', desc: '' },
      { code: 'CN-029', name: '△一般风险准备', formula: '', category: '', desc: '' },
      { code: 'CN-030', name: '未分配利润', formula: '', category: '', desc: '' },
      // 期末
      { code: 'CN-031', name: '期末金额', formula: 'CN-001+CN-011-CN-021', category: 'auto_calc', desc: '=期初+增加-减少' },
      { code: 'CN-032', name: '实收资本（或股本）', formula: 'CN-002+CN-012-CN-022', category: 'auto_calc', desc: '=期初+增加-减少' },
      { code: 'CN-033', name: '其他权益工具', formula: 'CN-003+CN-013-CN-023', category: 'auto_calc', desc: '' },
      { code: 'CN-034', name: '资本公积', formula: 'CN-004+CN-014-CN-024', category: 'auto_calc', desc: '' },
      { code: 'CN-035', name: '减：库存股', formula: 'CN-005+CN-015-CN-025', category: 'auto_calc', desc: '' },
      { code: 'CN-036', name: '其他综合收益', formula: 'CN-006+CN-016-CN-026', category: 'auto_calc', desc: '' },
      { code: 'CN-037', name: '专项储备', formula: 'CN-007+CN-017-CN-027', category: 'auto_calc', desc: '' },
      { code: 'CN-038', name: '盈余公积', formula: 'CN-008+CN-018-CN-028', category: 'auto_calc', desc: '' },
      { code: 'CN-039', name: '△一般风险准备', formula: 'CN-009+CN-019-CN-029', category: 'auto_calc', desc: '' },
      { code: 'CN-040', name: '未分配利润', formula: 'CN-010+CN-020-CN-030', category: 'auto_calc', desc: '' },
      // ── 第2部分：利润及利润分配 ──
      { code: 'CN-S2', name: '利润及利润分配表', formula: '', category: '', desc: '分节标题' },
      { code: 'CN-050', name: '一、期初金额', formula: 'CN-010', category: 'auto_calc', desc: '=期初未分配利润' },
      { code: 'CN-051', name: '二、本年增减变动金额', formula: 'CN-052+CN-056+CN-060+CN-063+CN-072', category: 'auto_calc', desc: '=综合收益+投入减少+专项储备+利润分配+内部结转' },
      { code: 'CN-052', name: '（一）综合收益总额', formula: "TB({company_code},'净利润','本期发生额')", category: 'auto_calc', desc: '从子企业试算表提取净利润' },
      { code: 'CN-053', name: '其中：当期归母净利润', formula: '', category: '', desc: '' },
      { code: 'CN-056', name: '（二）所有者投入和减少资本', formula: 'SUM(CN-057:CN-059)', category: 'auto_calc', desc: '' },
      { code: 'CN-057', name: '2-1所有者投入的普通股', formula: '', category: '', desc: '' },
      { code: 'CN-058', name: '2-3股份支付计入所有者权益的金额', formula: '', category: '', desc: '' },
      { code: 'CN-059', name: '2-4其他', formula: '', category: '', desc: '' },
      { code: 'CN-060', name: '（三）专项储备提取和使用', formula: 'CN-061+CN-062', category: 'auto_calc', desc: '' },
      { code: 'CN-061', name: '3-1提取专项储备', formula: '', category: '', desc: '' },
      { code: 'CN-062', name: '3-2使用专项储备', formula: '', category: '', desc: '' },
      { code: 'CN-063', name: '（四）利润分配', formula: 'SUM(CN-064:CN-071)', category: 'auto_calc', desc: '' },
      { code: 'CN-064', name: '4-1提取盈余公积', formula: 'CN-065+CN-066', category: 'auto_calc', desc: '' },
      { code: 'CN-065', name: '4-1-1法定公积金', formula: '', category: '', desc: '' },
      { code: 'CN-066', name: '4-1-2任意公积金', formula: '', category: '', desc: '' },
      { code: 'CN-067', name: '4-2△提取一般风险准备', formula: '', category: '', desc: '' },
      { code: 'CN-068', name: '4-3对所有者（或股东）的分配', formula: '', category: '', desc: '' },
      { code: 'CN-069', name: '4-4其他', formula: '', category: '', desc: '' },
      { code: 'CN-070', name: '4-1-3#储备基金', formula: '', category: '', desc: '' },
      { code: 'CN-071', name: '4-1-4#企业发展基金', formula: '', category: '', desc: '' },
      { code: 'CN-072', name: '（五）所有者权益内部结转', formula: 'SUM(CN-073:CN-078)', category: 'auto_calc', desc: '' },
      { code: 'CN-073', name: '5-1资本公积转增资本', formula: '', category: '', desc: '' },
      { code: 'CN-074', name: '5-2盈余公积转增资本', formula: '', category: '', desc: '' },
      { code: 'CN-075', name: '5-3弥补亏损', formula: '', category: '', desc: '' },
      { code: 'CN-076', name: '5-5其他综合收益结转留存收益', formula: '', category: '', desc: '' },
      { code: 'CN-077', name: '5-6其他', formula: '', category: '', desc: '' },
      { code: 'CN-078', name: '三、本年年末余额', formula: 'CN-050+CN-051', category: 'auto_calc', desc: '=期初+本年增减变动' },
      // ── 第3部分：资本公积变动 ──
      { code: 'CN-S3', name: '资本公积变动表', formula: '', category: '', desc: '分节标题' },
      { code: 'CN-080', name: '期初金额', formula: 'CN-004', category: 'auto_calc', desc: '=期初资本公积' },
      { code: 'CN-081', name: '本期变动', formula: 'CN-014-CN-024', category: 'auto_calc', desc: '=增加-减少' },
      { code: 'CN-082', name: '期末金额', formula: 'CN-080+CN-081', category: 'auto_calc', desc: '=期初+变动' },
      // ── 校验公式 ──
      { code: 'CN-V01', name: '校验：期末合计=期初+增加-减少', formula: 'CN-031-(CN-001+CN-011-CN-021)', category: 'logic_check', desc: '应为0' },
      { code: 'CN-V02', name: '校验：期末未分配利润=利润表年末余额', formula: 'CN-040-CN-078', category: 'logic_check', desc: '应为0' },
      { code: 'CN-V03', name: '校验：资本公积期末=变动表期末', formula: 'CN-034-CN-082', category: 'logic_check', desc: '应为0' },
    ]},
    consol_equity_sim: { rows: [
      { code: 'CS-001', name: '期初长投模拟-损益调整' }, { code: 'CS-002', name: '期初长投模拟-其他权益变动' },
      { code: 'CS-010', name: '当期模拟-损益调整' }, { code: 'CS-011', name: '当期模拟-投资收益' },
      { code: 'CS-020', name: '还原分红-投资收益' }, { code: 'CS-021', name: '还原分红-损益调整' },
      { code: 'CS-030', name: '股比变动影响' },
      { code: 'CS-040', name: '期末长投-投资成本' }, { code: 'CS-041', name: '期末长投-损益调整' },
      { code: 'CS-042', name: '期末长投-其他权益变动' }, { code: 'CS-043', name: '期末长投-小计' },
    ]},
    consol_elimination: { rows: [
      { code: 'CX-001', name: '权益抵消-实收资本' }, { code: 'CX-002', name: '权益抵消-资本公积' },
      { code: 'CX-003', name: '权益抵消-盈余公积' }, { code: 'CX-004', name: '权益抵消-未分配利润' },
      { code: 'CX-005', name: '权益抵消-商誉' }, { code: 'CX-006', name: '权益抵消-长投' },
      { code: 'CX-007', name: '权益抵消-少数股东权益' },
      { code: 'CX-010', name: '损益抵消-年初未分配利润' }, { code: 'CX-011', name: '损益抵消-投资收益' },
      { code: 'CX-012', name: '损益抵消-少数股权损益' },
      { code: 'CX-020', name: '抵销后少数股东权益' }, { code: 'CX-021', name: '抵销后少数股东损益' },
    ]},
    consol_capital: { rows: [
      { code: 'CK-001', name: '期初金额' }, { code: 'CK-002', name: '当期变动' },
      { code: 'CK-003', name: '+权益法模拟' }, { code: 'CK-004', name: '-合并抵消数' },
      { code: 'CK-005', name: '+自身报表变动' }, { code: 'CK-006', name: '期末金额' },
      { code: 'CK-007', name: '合并报表期末金额' }, { code: 'CK-008', name: '差异' },
    ]},
  }
  const sheet = sheetMap[nodeKey]
  if (!sheet) return []
  return sheet.rows.map((r: any, i: number) => ({
    id: `${nodeKey}_${i}`,
    row_code: r.code,
    row_name: r.name,
    formula: r.formula || '',
    formula_category: r.category || '',
    formula_description: r.desc || '',
  }))
}

const crossCheckRulesForCurrent = computed(() => {
  const key = selectedNodeKey.value
  return crossCheckRulesMap.value[key] || []
})

// ── 表间审核规则弹窗编辑 ──
const showCrossRuleDialog = ref(false)
const crossRuleDialogTitle = ref('新增规则')
const crossRuleEditIndex = ref(-1)  // -1 = 新增，>= 0 = 编辑已有行
const crossRuleForm = ref({
  label: '',
  left_ref: '',
  operator: '=',
  right_ref: '',
  description: '',
})

function onAddCrossRule() {
  crossRuleDialogTitle.value = '新增表间审核规则'
  crossRuleEditIndex.value = -1
  crossRuleForm.value = { label: '', left_ref: '', operator: '=', right_ref: '', description: '' }
  showCrossRuleDialog.value = true
}

function onEditCrossRule(row: any, index: number) {
  crossRuleDialogTitle.value = '编辑表间审核规则'
  crossRuleEditIndex.value = index
  crossRuleForm.value = {
    label: row.label || '',
    left_ref: row.left_ref || '',
    operator: row.operator || '=',
    right_ref: row.right_ref || '',
    description: row.description || '',
  }
  showCrossRuleDialog.value = true
}

function onSaveCrossRule() {
  const key = selectedNodeKey.value
  if (!crossCheckRulesMap.value[key]) crossCheckRulesMap.value[key] = []

  const ruleData = {
    label: crossRuleForm.value.label,
    left_ref: crossRuleForm.value.left_ref,
    operator: crossRuleForm.value.operator,
    right_ref: crossRuleForm.value.right_ref,
    description: crossRuleForm.value.description,
    _editing: false,
  }

  if (crossRuleEditIndex.value >= 0) {
    // 编辑已有行
    Object.assign(crossCheckRulesMap.value[key][crossRuleEditIndex.value], ruleData)
  } else {
    // 新增
    crossCheckRulesMap.value[key].push(ruleData)
  }

  showCrossRuleDialog.value = false
  ElMessage.success(crossRuleEditIndex.value >= 0 ? '规则已更新' : '规则已新增')
}

function onRemoveCrossRule(index: number) {
  const key = selectedNodeKey.value
  crossCheckRulesMap.value[key]?.splice(index, 1)
}

// ── 分类筛选 ──
const activeCategory = ref('all')

// Sprint 5.10: URI search + health
const uriSearchQuery = ref('')

/**
 * 判断报表行是否"需要公式"：标题行、「其中」补充披露行、占位行等不需要。
 * 合计行有 is_total_row 标记但可能已配 ROW() 公式，不排除。
 */
function _rowNeedsFormula(r: any): boolean {
  const name = (r.row_name || '').trim()
  // 标题行：以冒号结尾（流动资产：/非流动资产：/流动负债：/二、投资活动产生的现金流量：）
  if (name.endsWith('：') || name.endsWith(':')) return false
  // 「其中」补充披露行（其中：应收股利/其中：原材料 等，仅展示无独立取数公式）
  if (name.startsWith('其中：') || name.startsWith('其中:')) return false
  // 「#其中」变体（部分模板用 # 标注补充行）
  if (name.startsWith('#其中') || name.startsWith('＃其中')) return false
  // △占位行（△买入返售金融资产 等，表示该行次对该企业可能不适用）
  if (name.startsWith('△') || name.startsWith('-') || name.startsWith('—')) return false
  // 纯占位/空名
  if (!name) return false
  return true
}

const healthPercent = computed(() => {
  const rows = currentRows.value
  const meaningful = rows.filter(_rowNeedsFormula)
  if (!meaningful.length) return 100
  const withFormula = meaningful.filter(r => r.formula).length
  return Math.round((withFormula / meaningful.length) * 100)
})

const healthDesc = computed(() => {
  const rows = currentRows.value
  const meaningful = rows.filter(_rowNeedsFormula)
  const withFormula = meaningful.filter(r => r.formula).length
  return `${withFormula}/${meaningful.length} 已配置`
})

const filteredRows = computed(() => {
  let rows = currentRows.value

  // URI search filter
  if (uriSearchQuery.value.trim()) {
    const q = uriSearchQuery.value.trim().toLowerCase()
    rows = rows.filter(r =>
      (r.row_code || '').toLowerCase().includes(q) ||
      (r.row_name || '').toLowerCase().includes(q) ||
      (r.formula || '').toLowerCase().includes(q)
    )
  }

  if (activeCategory.value === 'all') return rows
  if (activeCategory.value === 'no_formula') return rows.filter(r => !r.formula && _rowNeedsFormula(r))
  return rows.filter(r => r.formula && r.formula_category === activeCategory.value)
})

const categoryCounts = computed(() => ({
  auto_calc: currentRows.value.filter(r => r.formula && r.formula_category === 'auto_calc').length,
  logic_check: currentRows.value.filter(r => r.formula && r.formula_category === 'logic_check').length,
  reasonability: currentRows.value.filter(r => r.formula && r.formula_category === 'reasonability').length,
}))

// ── 选择 ──
const selectedRows = ref<any[]>([])
const formulaTableRef = ref<any>(null)

function onSelectionChange(rows: any[]) {
  selectedRows.value = rows
}

function onRowClick(_row: any) {
  // 单击行时高亮，不自动打开编辑
}

function getRowClassName({ row }: { row: any }) {
  if (row.formula && row.formula_category === 'auto_calc') return 'gt-fm-row-auto'
  if (row.formula && row.formula_category === 'logic_check') return 'gt-fm-row-logic'
  if (row.formula && row.formula_category === 'reasonability') return 'gt-fm-row-reason'
  if (!row.formula) return 'gt-fm-row-empty'
  return ''
}

function isPresetFormula(row: any): boolean {
  const src = row.formula_source || ''
  return src.startsWith('check_presets.') || src === '试算表审定数' || src === '报表行次引用'
}

function onBatchApplyCategory(cat: string) {
  for (const row of selectedRows.value) {
    row.formula_category = cat
  }
  ElMessage.success(`已将 ${selectedRows.value.length} 条标记为 ${categoryLabel(cat)}`)
}

function onBatchClearFormula() {
  for (const row of selectedRows.value) {
    row.formula = ''
    row.formula_category = ''
    row.formula_description = ''
  }
  ElMessage.success(`已清除 ${selectedRows.value.length} 条公式`)
  selectedRows.value = []
}

// ── 编辑 ──
const editingId = ref<string | null>(null)
const editFormula = ref('')
const editCategory = ref('auto_calc')
const editDescription = ref('')
const applying = ref(false)

// 公式编辑弹窗
const showFormulaEdit = ref(false)
const editingRow = ref<any>(null)

function startEdit(row: any) {
  editingRow.value = row
  showFormulaEdit.value = true
}

async function onFormulaEditSave(data: { formula: string; category: string; description: string }) {
  const row = editingRow.value
  if (!row) return

  row.formula = data.formula
  row.formula_category = data.category
  row.formula_description = data.description

  // tb_detail 科目明细：覆盖默认预设 / 自定义新增 → 持久化 wizard_state.tb_detail_formulas
  if (selectedNodeKey.value === 'tb_detail') {
    const cat = data.category || 'auto_calc'
    if (row._isNew) {
      if (!data.formula) return
      tbDetailAdded.value.push({
        row_code: row.row_code, row_name: row.row_name,
        formula: data.formula, formula_category: cat, formula_description: data.description,
      })
      row._isNew = false
    } else if (row._tbAdded) {
      const t = tbDetailAdded.value.find((a: any) => a.row_code === row.row_code)
      if (t) { t.formula = data.formula; t.formula_category = cat; t.formula_description = data.description }
    } else {
      // 覆盖某科目默认预设
      tbDetailOverrides.value[row.row_code] = {
        row_code: row.row_code, row_name: row.row_name,
        formula: data.formula, formula_category: cat, formula_description: data.description,
      }
    }
    await persistTbDetailFormulas()
    ElMessage.success('公式已保存')
    emit('saved')
    return
  }

  if (row._isNew) {
    // 新增公式行——添加到当前列表并尝试保存到后端
    if (data.formula) {
      const rows = currentRows.value
      row.row_number = rows.length + 1
      rows.push(row)

      if (selectedNodeKey.value.startsWith('report_')) {
        const reportType = selectedNodeKey.value.replace('report_', '')
        try {
          const saved = await api.post(P_rc.list, {
            report_type: reportType,
            // 与当前实际读取口径一致：看的是项目级就写项目级（否则新增行写进模板级、波及所有项目）
            applicable_standard: reportStandardByType.value[reportType]
              || `${fmTemplateType.value}_standalone`,
            row_number: row.row_number,
            row_code: row.row_code,
            row_name: row.row_name,
            formula: data.formula,
            formula_category: data.category,
            formula_description: data.description,
          }, { validateStatus: (s: number) => s < 600 })
          if (saved?.id) row.id = saved.id
          row._isNew = false
          ElMessage.success('新公式已保存')
          emit('saved')
        } catch {
          ElMessage.warning('公式已添加到列表，保存到后端失败')
        }
      }
    }
    return
  }

  // 已有行——更新到后端
  if (row.id) {
    try {
      await api.put(P_rc.detail(row.id), {
        formula: data.formula || null,
        formula_category: data.category,
        formula_description: data.description,
      })
      ElMessage.success('公式已保存')
      emit('saved')
    } catch (e) {
      handleApiError(e, '保存失败')
    }
  }
}

async function saveEdit(row: any) {
  // 兼容行内编辑（保留）
  if (!row.id) return
  try {
    await api.put(P_rc.detail(row.id), {
      formula: editFormula.value || null,
      formula_category: editCategory.value,
      formula_description: editDescription.value,
    })
    row.formula = editFormula.value
    row.formula_category = editCategory.value
    row.formula_description = editDescription.value
    editingId.value = null
    ElMessage.success('公式已保存')
    emit('saved')
  } catch (e) {
    handleApiError(e, '保存失败')
  }
}

function categoryTagType(cat: string | null): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (cat === 'auto_calc') return 'primary'
  if (cat === 'logic_check') return 'warning'
  if (cat === 'reasonability') return 'info'
  if (cat === '取数') return 'success'   // 跨 sheet / 四表库取数
  if (cat === '计算') return 'primary'   // 表间计算公式
  if (cat === '只读溯源') return 'info'
  return ''
}

function categoryLabel(cat: string | null) {
  if (cat === 'auto_calc') return '自动运算'
  if (cat === 'logic_check') return '逻辑审核'
  if (cat === 'reasonability') return '合理性'
  // 专属组件 surfacing 分类（取数/计算/只读溯源）原样显示，不再回退"未分类"
  if (cat === '取数' || cat === '计算' || cat === '只读溯源') return cat
  return cat || '未分类'
}

async function onApplyFormulas() {
  if (!props.projectId || !props.year) {
    ElMessage.warning('缺少项目信息')
    return
  }

  // 收集当前节点所有带公式的行
  const formulaRows = currentRows.value.filter((r: any) => r.formula && r.formula_category === 'auto_calc')
  if (!formulaRows.length) {
    ElMessage.info('当前节点没有自动运算公式')
    return
  }

  applying.value = true
  try {
    const formulas = formulaRows.map((r: any) => ({
      row_code: r.row_code || r.id,
      formula: r.formula,
    }))

    const data = await api.post(P_rc.executeFormulasBatch, {
      project_id: props.projectId,
      year: props.year,
      formulas,
    }, { validateStatus: (s: number) => s < 600 })

    const result = data
    const results = result?.results || []
    const rowValues = result?.row_values || {}

    // 统计执行结果
    const successCount = results.filter((r: any) => r.value != null && !r.error).length
    const errorCount = results.filter((r: any) => r.error).length

    // 将计算结果写入响应式缓存
    for (const r of results) {
      if (r.row_code) {
        formulaResults.value[r.row_code] = {
          value: r.value != null && !r.error ? r.value : null,
          trace: r.trace || [],
        }
      }
    }

    // 如果是报表节点，将结果回写到 report_config
    if (selectedNodeKey.value.startsWith('report_') && Object.keys(rowValues).length) {
      try {
        const reportType = selectedNodeKey.value.replace('report_', '')
        const updates = Object.entries(rowValues).map(([code, val]) => ({
          row_code: code,
          current_period_amount: val,
        }))
        await api.post(P_rc.batchUpdate, {
          project_id: props.projectId,
          report_type: reportType,
          applicable_standard: `soe_standalone`,
          updates,
        }, { validateStatus: (s: number) => s < 600 })
      } catch { /* 回写失败不影响主流程 */ }
    }

    if (errorCount > 0) {
      ElMessage.warning(`执行完成：${successCount} 条成功，${errorCount} 条失败`)
    } else {
      ElMessage.success(`已执行 ${successCount} 条自动运算公式`)
    }
    emit('applied')
  } catch (e: any) {
    handleApiError(e, '公式执行失败')
  } finally {
    applying.value = false
  }
}

function onFormulaFileImported() {
  showFormulaImport.value = false
  loadRowsForNode(selectedNodeKey.value)
}

/**
 * 导出公式模板 — 导出当前报表/节点的公式为 Excel（含编制说明 sheet）
 * 逻辑抽到独立文件 exportFormulaTemplate.ts（避免巨型 Vue 文件中动态 import exceljs 被 Vite 拦截）
 */
async function onExportFormulaTemplate() {
  // 获取当前节点数据；如果没有（未选节点或节点无数据），导出通用空白模板
  const nodeKey = selectedNodeKey.value || ''
  const currentRows = allRowsMap.value[nodeKey.replace('report_', '')] || []

  // 如果当前节点有数据，导出该节点的公式
  // 如果没有数据，传空数组——exportFormulaTemplate 内部会生成通用模板骨架
  const { exportFormulaTemplate } = await import('./exportFormulaTemplate')
  await exportFormulaTemplate(currentRows, nodeKey || '通用模板', selectedPath.value || '公式管理中心')
}

async function onImportPresetFormulas() {
  loadingData.value = true

  // 报表类：从 report_config 加载
  if (selectedNodeKey.value.startsWith('report_')) {
    const reportType = selectedNodeKey.value.replace('report_', '')
    try {
      const standard = `${fmTemplateType.value}_standalone`
      const data = await api.get(P_rc.list, {
        params: { report_type: reportType, applicable_standard: standard },
        validateStatus: (s: number) => s < 600,
      })
      const rows = data ?? []
      allRowsMap.value[reportType] = rows
      const formulaCount = rows.filter((r: any) => r.formula).length
      ElMessage.success(`已导入 ${rows.length} 行，其中 ${formulaCount} 个预设公式`)
    } catch (e) { handleApiError(e, '导入失败') }
    finally { loadingData.value = false }
    return
  }

  // 附注类 / 表间审核：从附注校验预设公式加载
  if (isNoteDomainNodeKey(selectedNodeKey.value) || selectedNodeKey.value.startsWith('cross_')) {
    try {
      const data = await api.get(P_nt.presetFormulas(fmTemplateType.value), {
        validateStatus: (s: number) => s < 600,
      })
      const presets = data ?? []
      notePresetFormulas.value = presets
      ElMessage.success(`已加载 ${presets.length} 条附注校验预设公式（${fmTemplateType.value === 'soe' ? '国企版' : '上市版'}）`)
    } catch (e) { handleApiError(e, '加载附注预设公式失败') }
    finally { loadingData.value = false }
    return
  }

  loadingData.value = false
  ElMessage.info('当前节点暂无预设公式')
}

// ── 共享模板 ──

/**
 * 确保 6 类报表的 report_config 行都已加载。
 *
 * 🔴 模板保存/引用都必须先补齐：`allRowsMap` 只装"用户点过的报表"，
 * 直接采集会存下**只含当前已看过部分**的残缺模板（用户无从察觉），
 * 引用时也会因目标报表未加载而**静默跳过**整类行。
 */
async function ensureAllReportRowsLoaded(): Promise<void> {
  for (const rt of REPORT_TYPE_KEYS) {
    if (allRowsMap.value[rt]?.length) continue
    allRowsMap.value[rt] = await fetchReportRows(rt)
  }
}

/**
 * 保存为模板：采集全 6 类报表公式（异步补齐后再采集）+ 附注校验预设 + 项目级底稿公式。
 *
 * 三段各自可独立引用：报表段可写回 report_config；附注段与底稿段属**只读快照**
 * （附注预设是模板级、底稿公式绑定具体 wp 实例，跨项目行号/实例都不同，
 * 直接写回会串项目），故引用时只回填报表段，另两段仅作留档与比对。
 */
async function getFormulaConfigData(): Promise<Record<string, any>> {
  await ensureAllReportRowsLoaded()
  const formulaRows: any[] = []
  const perType: Record<string, number> = {}
  // 与看板同源：只遍历 6 类报表键白名单（`key.includes('_')` 会把全部报表键跳掉）
  for (const key of REPORT_TYPE_KEYS) {
    const rows = (allRowsMap.value[key] as any[] | undefined) || []
    let n = 0
    for (const r of rows) {
      if (r.formula) {
        formulaRows.push({
          row_code: r.row_code,
          row_name: r.row_name,
          formula: r.formula,
          formula_category: r.formula_category,
          formula_description: r.formula_description,
          report_type: key,
        })
        n += 1
      }
    }
    perType[key] = n
  }
  // ── 附注段：模板级校验预设（先补齐，避免"没点过附注就存不到"）──
  if (!notePresetFormulas.value.length) {
    try {
      const data = await api.get(P_nt.presetFormulas(fmTemplateType.value), {
        validateStatus: (s: number) => s < 600,
      })
      notePresetFormulas.value = data ?? []
    } catch { /* 附注预设不可用不阻断报表段 */ }
  }
  const noteRows = buildNoteFormulaRows(notePresetFormulas.value, {}).map((r: any) => ({
    note_section: r.row_code,
    section_title: r.row_name,
    formula: r.formula,
    formula_category: r.formula_category,
    formula_description: r.formula_description,
  }))

  // ── 底稿段：项目级 wp_formula（按 7 类作用域）──
  if (props.projectId && !scopeCatalog.totalCount.value) {
    try { await scopeCatalog.loadGlobal(props.projectId) } catch { /* 不阻断 */ }
  }
  const wpRows = scopeCatalog.allRows.value.map((r) => ({
    scope: r.scope,
    sheet_name: r.sheetName,
    target_cell: r.targetCell,
    formula: r.expression,
    formula_type: r.formulaType,
  }))

  const total = formulaRows.length + noteRows.length + wpRows.length
  if (!total) ElMessage.warning('当前无公式可保存为模板')
  return {
    formulas: formulaRows,
    // 新增两段（引用时只回填 formulas；这两段作留档/比对，避免跨项目串行号与实例）
    note_formulas: noteRows,
    workpaper_formulas: wpRows,
    template_type: fmTemplateType.value,
    // 存下采集口径，便于引用时判断是否同版（此前只有 template_type，无准则/覆盖信息）
    applicable_standard: `${fmTemplateType.value}_standalone`,
    coverage: {
      ...perType,
      note_presets: noteRows.length,
      workpaper_project: wpRows.length,
    },
    captured_at: new Date().toISOString(),
  }
}

/**
 * 引用模板：填入 + **落库**，并给出准确的三类计数。
 *
 * 修掉三处旧问题：
 *  1. 只改内存不落库 —— 弹窗关掉就丢，提示却是「已引用 N 条」（假成功）；
 *  2. 目标报表未加载时整类静默跳过（`if (!rows) continue`）；
 *  3. 模板版本（国企/上市）与当前页不同也直接套用。
 */
async function onTemplateApplied(data: Record<string, any>) {
  const formulas = data?.formulas || []
  if (!formulas.length) {
    ElMessage.warning('模板中无公式数据')
    return
  }

  const tplType = normalizeTemplateType(data?.template_type)
  if (data?.template_type && tplType !== fmTemplateType.value) {
    try {
      await ElMessageBox.confirm(
        `模板是「${tplType === 'listed' ? '上市版' : '国企版'}」，当前页是`
        + `「${fmTemplateType.value === 'listed' ? '上市版' : '国企版'}」，行次编码体系可能不同。仍要引用？`,
        '模板版本不一致',
        { confirmButtonText: '仍要引用', cancelButtonText: '取消', type: 'warning' },
      )
    } catch { return }
  }

  applying.value = true
  try {
    await ensureAllReportRowsLoaded()

    // ── 先算 plan（不改任何数据）：可写 / 跳过 / 不存在 ──
    const writable: any[] = []
    let skippedExisting = 0
    let unmatched = 0
    for (const f of formulas) {
      const rows = (allRowsMap.value[f.report_type] as any[] | undefined) || []
      const target = rows.find((r: any) => r.row_code === f.row_code)
      if (!target) { unmatched += 1; continue }
      if (target.formula) { skippedExisting += 1; continue }
      writable.push({ target, source: f })
    }

    if (!writable.length) {
      ElMessage.warning(
        `无可写入行：跳过已有公式 ${skippedExisting} 条，模板行次在当前报表中不存在 ${unmatched} 条`,
      )
      return
    }

    // ── 预览 + 确认（此前是直接落库，用户看不到将写什么）──
    const preview = writable.slice(0, 8)
      .map(({ target, source }) => `${target.row_code} ${target.row_name || ''} ← ${source.formula}`)
      .join('\n')
    try {
      await ElMessageBox.confirm(
        `将写入 ${writable.length} 条公式；跳过已有 ${skippedExisting} 条；`
        + `模板行次不存在 ${unmatched} 条。\n\n前 ${preview ? Math.min(8, writable.length) : 0} 条预览：\n${preview}`
        + (writable.length > 8 ? `\n…（其余 ${writable.length - 8} 条）` : ''),
        '引用模板 — 写入预览',
        {
          confirmButtonText: '确认写入',
          cancelButtonText: '取消',
          type: 'info',
          customClass: 'gt-fm-tpl-preview',
        },
      )
    } catch { return }

    // ── 落库；逐条记录 undo 快照（失败/回滚都要能还原）──
    const undo: { row: any; before: { formula: any; category: any; description: any } }[] = []
    let saved = 0
    let failed = 0
    for (const { target, source } of writable) {
      const before = {
        formula: target.formula ?? null,
        category: target.formula_category ?? null,
        description: target.formula_description ?? null,
      }
      target.formula = source.formula
      target.formula_category = source.formula_category
      target.formula_description = source.formula_description
      if (!target.id) { failed += 1; continue }
      try {
        await api.put(P_rc.detail(target.id), {
          formula: target.formula || null,
          formula_category: target.formula_category,
          formula_description: target.formula_description,
        })
        undo.push({ row: target, before })
        saved += 1
      } catch {
        // 该行写库失败 → 内存也还原，避免"界面显示已写、库里没有"
        target.formula = before.formula
        target.formula_category = before.category
        target.formula_description = before.description
        failed += 1
      }
    }

    lastTemplateUndo.value = undo.length
      ? { templateName: String(data?.template_name || '模板'), entries: undo }
      : null

    const parts = [`已引用并保存 ${saved} 条`]
    if (failed) parts.push(`保存失败 ${failed} 条`)
    if (skippedExisting) parts.push(`跳过已有公式 ${skippedExisting} 条`)
    if (unmatched) parts.push(`模板行次在当前报表中不存在 ${unmatched} 条`)
    // 附注/底稿段是只读留档：如实说明未写回，避免用户以为整包都进来了
    const noteCount = Array.isArray(data?.note_formulas) ? data.note_formulas.length : 0
    const wpCount = Array.isArray(data?.workpaper_formulas) ? data.workpaper_formulas.length : 0
    if (noteCount || wpCount) {
      parts.push(`模板另含附注预设 ${noteCount} 条 / 底稿公式 ${wpCount} 条（只读留档，未写回）`)
    }
    const text = parts.join('，')
    if (failed) ElMessage.warning(text)
    else ElMessage.success(`${text}（可点「↩ 撤销引用」还原）`)
    if (saved) emit('saved')
  } finally {
    applying.value = false
  }
}

/** 上一次引用模板的可撤销快照（仅本次会话内有效）。 */
const lastTemplateUndo = ref<{
  templateName: string
  entries: { row: any; before: { formula: any; category: any; description: any } }[]
} | null>(null)

/** 撤销上一次引用模板：把写过的行逐条还原回引用前的值。 */
async function onUndoTemplateApply() {
  const snapshot = lastTemplateUndo.value
  if (!snapshot?.entries.length) return
  try {
    await ElMessageBox.confirm(
      `将把「${snapshot.templateName}」写入的 ${snapshot.entries.length} 条公式还原为引用前的值。确认撤销？`,
      '撤销引用模板',
      { confirmButtonText: '确认撤销', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }

  applying.value = true
  let restored = 0
  let failed = 0
  try {
    for (const { row, before } of snapshot.entries) {
      try {
        await api.put(P_rc.detail(row.id), {
          formula: before.formula,
          formula_category: before.category,
          formula_description: before.description,
        })
        row.formula = before.formula
        row.formula_category = before.category
        row.formula_description = before.description
        restored += 1
      } catch { failed += 1 }
    }
    if (failed) ElMessage.warning(`已还原 ${restored} 条，${failed} 条还原失败`)
    else {
      ElMessage.success(`已还原 ${restored} 条`)
      lastTemplateUndo.value = null
    }
    if (restored) emit('saved')
  } finally {
    applying.value = false
  }
}

function onAddFormulaRow() {
  // 打开公式编辑弹窗，不绑定具体行——用户自由编辑
  editingRow.value = {
    id: null,
    row_code: `CUSTOM-${(currentRows.value?.length || 0) + 1}`,
    row_name: '自定义公式',
    formula: '',
    // 用户要求：分类默认为自动运算类型
    formula_category: 'auto_calc',
    formula_description: '',
    _isNew: true,
  }
  showFormulaEdit.value = true
}

async function onSaveAllFormulas() {
  const rows = currentRows.value.filter(r => r.formula)
  if (!rows.length) {
    ElMessage.warning('无公式可保存')
    return
  }
  applying.value = true
  let saved = 0
  try {
    for (const row of rows) {
      if (row._isNew && row.formula) {
        // 新增
        const reportType = selectedNodeKey.value.replace('report_', '')
        await api.post(P_rc.list, {
          report_type: reportType,
          // 与当前读取口径一致（项目级优先），避免新增行落到模板级影响其他项目
          applicable_standard: reportStandardByType.value[reportType]
            || `${fmTemplateType.value}_standalone`,
          row_number: row.row_number || 0,
          row_code: row.row_code,
          row_name: row.row_name,
          formula: row.formula,
          formula_category: row.formula_category,
          formula_description: row.formula_description,
        }, { validateStatus: (s: number) => s < 600 })
        row._isNew = false
        saved++
      } else if (row.id) {
        // 更新
        await api.put(P_rc.detail(row.id), {
          formula: row.formula,
          formula_category: row.formula_category,
          formula_description: row.formula_description,
        })
        saved++
      }
    }
    ElMessage.success(`已保存 ${saved} 个公式`)
    emit('saved')

    // Sprint 5.10: 保存后调 stale_engine 传播变更
    try {
      await api.post(linkageBus.impact, {
        source_uri: `FORMULA:${selectedNodeKey.value}::config_changed`,
        project_id: props.projectId,
        year: new Date().getFullYear(),
      }, { validateStatus: (s: number) => s < 600 })
    } catch {
      // stale propagation failure is non-blocking
    }
  } catch (e) {
    handleApiError(e, '保存失败')
  } finally {
    applying.value = false
  }
}

// ── 公式看板 ──
const showFormulaDashboard = ref(false)
const dashboardSearch = ref('')
const dashboardGroupBy = ref('domain')
const dashboardFilterCategory = ref('')
/** 维度筛选：域（报表/附注/底稿各作用域/试算表）与层级（模板预设/项目级）。 */
const dashboardFilterDomain = ref('')
const dashboardFilterLevel = ref('')
/** 分类健康度维度：'' 全部 / 'yes' 已分类 / 'no' 未分类。 */
const dashboardFilterCategorized = ref('')
const dashboardLoading = ref(false)
/** 看板加载后的覆盖情况（空态要说清「哪一类没取到」，不能只显示 No Data）。 */
const dashboardCoverage = ref<{ label: string; count: number }[]>([])

const REPORT_TYPE_LABELS: Record<string, string> = {
  balance_sheet: '资产负债表', income_statement: '利润表',
  cash_flow_statement: '现金流量表', equity_statement: '权益变动表',
  cash_flow_supplement: '现金流附表', impairment_provision: '资产减值准备表',
}

/**
 * 报表键白名单 = 报表行的唯一真源。
 *
 * 🔴 原实现用 `if (key.includes('_')) continue` 想跳过缓存键（`soe_balance_sheet`），
 * 但 `balance_sheet` / `income_statement` 等**每个报表键都含下划线** ⇒ 报表行被全部
 * 跳掉，公式看板与「保存为模板」恒 0 条（实测 report_config 有 183 条带公式）。
 * 改为显式白名单，缓存键（带 soe_/listed_ 前缀）自然不在其中。
 */
const REPORT_TYPE_KEYS = Object.keys(REPORT_TYPE_LABELS)

/**
 * 每类报表实际取自哪个 `applicable_standard`（`project:{id}` 或 `{soe|listed}_standalone`）。
 * 保存/新增公式必须回写同一口径，否则「看的是项目级、写的是模板级」。
 */
const reportStandardByType = ref<Record<string, string>>({})

/** 该口径是否为项目级。 */
function isProjectStandard(standard?: string): boolean {
  return !!standard && standard.startsWith('project:')
}

/** 当前报表节点取自项目级还是模板级（主表头展示，让用户知道在改谁）。 */
const activeReportLevelLabel = computed(() => {
  if (!selectedNodeKey.value.startsWith('report_')) return ''
  const std = reportStandardByType.value[selectedNodeKey.value.replace('report_', '')]
  if (!std) return ''
  return isProjectStandard(std) ? '项目级' : '模板预设'
})

/**
 * 取某类报表的行：**项目级优先、模板级兜底**。
 *
 * 🔴 「把报表预设落入项目」写出的是 `report_config.applicable_standard = 'project:{id}'`，
 * 取数层早已优先读它；但公式中心此前恒读 `{soe|listed}_standalone` ⇒ 落库后界面
 * 毫无变化（用户以为按钮没生效），改公式还改在模板级（波及所有项目）。
 */
async function fetchReportRows(reportType: string): Promise<any[]> {
  const candidates: string[] = []
  if (props.projectId) candidates.push(`project:${props.projectId}`)
  candidates.push(`${fmTemplateType.value}_standalone`)

  for (const standard of candidates) {
    try {
      const data = await api.get(P_rc.list, {
        params: { report_type: reportType, applicable_standard: standard },
        validateStatus: (s: number) => s < 600,
      })
      const rows = (data ?? []) as any[]
      // 项目级为空 = 尚未落入，继续退到模板级（不能把空数组当"已配置"）
      if (!rows.length && isProjectStandard(standard)) continue
      // 后端未给分类时的兜底（`formula_category` 现已随 ReportConfigRow 下发；
      // 仅对历史脏数据生效，并打标便于识别，避免把「兜底值」当成已配置分类）。
      for (const r of rows) {
        if (r.formula && !r.formula_category) {
          r.formula_category = 'auto_calc'
          r._category_inferred = true
        }
      }
      reportStandardByType.value[reportType] = standard
      return rows
    } catch { /* 该口径取失败 → 试下一个 */ }
  }
  return []
}

/** 看板行的「层级」维度：模板预设（跨项目共用）vs 项目级（本项目自有）。 */
const LEVEL_TEMPLATE = '模板预设'
const LEVEL_PROJECT = '项目级'

/** 报表域：report_config 模板预设（PUT 可改，编辑后落库）。 */
function reportBoardRows(): any[] {
  const out: any[] = []
  for (const rt of REPORT_TYPE_KEYS) {
    const rows = (allRowsMap.value[rt] as any[] | undefined) || []
    for (const r of rows) {
      if (!r.formula) continue
      out.push({
        ...r,
        _domain: 'report',
        _domainLabel: '报表',
        // 层级取实际读取口径：已落入项目的报表行是「项目级」，未落入才是「模板预设」
        _level: isProjectStandard(reportStandardByType.value[rt])
          ? LEVEL_PROJECT
          : LEVEL_TEMPLATE,
        _report_type: rt,
        _report_type_label: REPORT_TYPE_LABELS[rt] || rt,
        _source_type: '报表预设',
        _editable: !!r.id,
        _locateKey: `report_${rt}`,
      })
    }
  }
  return out
}

/** 附注域：附注校验预设（模板级），复用 noteScopeTargeting 的单一映射。 */
function noteBoardRows(): any[] {
  if (!notePresetFormulas.value.length) return []
  return buildNoteFormulaRows(notePresetFormulas.value, {}).map((r: any) => ({
    ...r,
    _domain: 'note',
    _domainLabel: '附注',
    _level: LEVEL_TEMPLATE,
    _report_type_label: '—',
    _source_type: '附注预设',
    _editable: false,
    _locateKey: r.row_code ? noteSectionToNodeKey(String(r.row_code).split('-')[0]) : 'note',
  }))
}

/** 项目级公式（wp_formula，按 7 类作用域派生）；编辑须回各自底稿页，看板只提供定位。 */
function projectScopeBoardRows(): any[] {
  return scopeCatalog.allRows.value.map((r) => ({
    id: r.id,
    row_code: r.targetCell || r.sheetName || '',
    row_name: r.sheetName || '',
    formula: r.expression || '',
    formula_category: r.formulaType || '',
    formula_description: r.issueDescription || r.hintText || r.sourceLabel || '',
    _domain: r.scope,
    _domainLabel: r.scopeLabel || SCOPE_CATALOG_LABEL_MAP[r.scope] || r.scope,
    _level: LEVEL_PROJECT,
    _report_type_label: '—',
    _source_type: '底稿公式',
    _editable: false,
    _locateKey: r.sheetName
      ? `wp_${String(r.sheetName).replace(/-/g, '_').toLowerCase()}`
      : '',
  }))
}

/** 试算平衡表域：用户对科目预设的覆盖 / 自定义新增（项目级，持久化在 wizard_state）。 */
function tbBoardRows(): any[] {
  const rows = [
    ...Object.values(tbDetailOverrides.value || {}),
    ...(tbDetailAdded.value || []),
  ] as any[]
  return rows.filter((r) => r?.formula).map((r) => ({
    ...r,
    _domain: 'tb',
    _domainLabel: '试算平衡表',
    _level: LEVEL_PROJECT,
    _report_type_label: '—',
    _source_type: '科目取数',
    _editable: false,
    _locateKey: 'tb_detail',
  }))
}

/** 看板行 = 模板预设（报表/附注）∪ 项目级（底稿各作用域 / 试算表覆盖）。 */
const allFormulaRows = computed(() => [
  ...reportBoardRows(),
  ...noteBoardRows(),
  ...projectScopeBoardRows(),
  ...tbBoardRows(),
])

/** 域下拉选项（带条数），按实际数据派生。 */
const dashboardDomainOptions = computed(() => {
  const counter = new Map<string, { value: string; label: string; count: number }>()
  for (const r of allFormulaRows.value) {
    const value = String(r._domain || '')
    if (!value) continue
    const hit = counter.get(value)
    if (hit) hit.count += 1
    else counter.set(value, { value, label: String(r._domainLabel || value), count: 1 })
  }
  return [...counter.values()]
})

/** 覆盖情况文案：空态时必须说清哪一类没取到，而不是只给 No Data。 */
const dashboardCoverageText = computed(() =>
  dashboardCoverage.value.map((c) => `${c.label} ${c.count} 条`).join(' · ')
  || '尚未加载',
)

/** 分类健康度计数（未分类条数直接暴露，供批量补齐）。 */
const dashboardCategorizedCount = computed(() => {
  let yes = 0
  let no = 0
  for (const r of allFormulaRows.value) {
    if (r.formula_category) yes += 1
    else no += 1
  }
  return { yes, no }
})

/** 分类下拉选项按实际数据派生，避免写死三类而漏掉底稿公式的类型。 */
const dashboardCategoryOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const r of allFormulaRows.value) {
    const key = r.formula_category || ''
    if (!key || seen.has(key)) continue
    seen.set(key, categoryLabel(key))
  }
  return [...seen.entries()].map(([value, label]) => ({ value, label }))
})

const dashboardFilteredRows = computed(() => {
  let rows = allFormulaRows.value
  if (dashboardFilterCategory.value) {
    rows = rows.filter(r => r.formula_category === dashboardFilterCategory.value)
  }
  if (dashboardFilterDomain.value) {
    rows = rows.filter(r => r._domain === dashboardFilterDomain.value)
  }
  if (dashboardFilterLevel.value) {
    rows = rows.filter(r => r._level === dashboardFilterLevel.value)
  }
  // 「未分类」是数据现状（实测 183 条报表预设里 38 条无 formula_category），
  // 给一个显式维度便于批量补齐，而不是让用户在满屏「未分类」里肉眼找。
  if (dashboardFilterCategorized.value === 'yes') {
    rows = rows.filter(r => !!r.formula_category)
  } else if (dashboardFilterCategorized.value === 'no') {
    rows = rows.filter(r => !r.formula_category)
  }
  const kw = dashboardSearch.value.toLowerCase()
  if (kw) {
    rows = rows.filter(r =>
      (r.row_code || '').toLowerCase().includes(kw) ||
      (r.row_name || '').toLowerCase().includes(kw) ||
      (r.formula || '').toLowerCase().includes(kw) ||
      (r.formula_description || '').toLowerCase().includes(kw) ||
      (r._domainLabel || '').toLowerCase().includes(kw) ||
      (r._source_type || '').toLowerCase().includes(kw)
    )
  }
  return rows
})

const dashboardGroupedData = computed(() => {
  const rows = dashboardFilteredRows.value
  const groups: Record<string, { key: string; label: string; rows: any[]; _open: boolean }> = {}

  for (const r of rows) {
    let gKey = '', gLabel = ''
    if (dashboardGroupBy.value === 'domain') {
      gKey = r._domain || 'unknown'
      gLabel = `${r._domainLabel || gKey}（${r._level || ''}）`
    } else if (dashboardGroupBy.value === 'level') {
      gKey = r._level || 'unknown'
      gLabel = r._level || gKey
    } else if (dashboardGroupBy.value === 'report_type') {
      gKey = r._report_type || 'unknown'
      gLabel = r._report_type_label || gKey
    } else if (dashboardGroupBy.value === 'category') {
      gKey = r.formula_category || 'none'
      gLabel = categoryLabel(r.formula_category)
    } else if (dashboardGroupBy.value === 'source') {
      // 按公式中引用的数据源分组
      const formula = r.formula || ''
      if (formula.includes('TB(') || formula.includes('SUM_TB(')) gKey = 'tb'
      else if (formula.includes('NOTE(')) gKey = 'note'
      else if (formula.includes('WP(')) gKey = 'wp'
      else if (formula.includes('ROW(') || formula.includes('SUM_ROW(')) gKey = 'row'
      else gKey = 'other'
      const sourceLabels: Record<string, string> = { tb: '📈 试算表', note: '📝 附注', wp: '📋 底稿', row: '📊 报表行次', other: '其他' }
      gLabel = sourceLabels[gKey] || gKey
    }
    if (!groups[gKey]) groups[gKey] = { key: gKey, label: gLabel, rows: [], _open: true }
    groups[gKey].rows.push(r)
  }
  return Object.values(groups)
})

/**
 * 看板行可编辑性分两类：
 *  - 报表预设（report_config，有 id）→ 直接编辑，保存走 PUT /api/report-config/{id}；
 *  - 项目级底稿公式 / 附注预设 / 试算表覆盖 → 存储与保存路径各不相同，
 *    看板不代写（否则会把 wp_formula 的 id 发到 report-config 端点），改为「定位」
 *    到左树对应节点，由该域自己的编辑链路落库。
 */
function onDashboardEdit(row: any) {
  if (!row?._editable) return
  editingRow.value = row
  showFormulaEdit.value = true
}

/** 定位：关闭看板并把左树选到该公式所属节点（各域用自己的编辑链路保存）。 */
async function onDashboardLocate(row: any) {
  const target = String(row?._locateKey || '')
  if (!target) {
    ElMessage.info('该公式未提供可定位的坐标节点')
    return
  }
  showFormulaDashboard.value = false
  const hit = await applyTargetNode(target)
  if (!hit) ElMessage.warning(`未能在坐标目录中定位「${target}」`)
}

/**
 * 看板打开时加载全部来源：报表预设（6 类 report_config）+ 附注预设 +
 * 项目级公式（wp_formula 的 7 类作用域）。
 *
 * 🔴 只加载报表是此前「全局总览」名不符实的一半原因；另一半是报表键过滤 bug。
 */
watch(showFormulaDashboard, async (v) => {
  if (!v) return
  dashboardLoading.value = true
  try {
    // 与主面板同一入口：项目级优先、模板级兜底（看板的层级标签也据此得出）
    await ensureAllReportRowsLoaded()
    if (!notePresetFormulas.value.length) {
      try {
        const data = await api.get(P_nt.presetFormulas(fmTemplateType.value), {
          validateStatus: (s: number) => s < 600,
        })
        notePresetFormulas.value = data ?? []
      } catch { /* 附注预设不可用不阻断 */ }
    }
    if (props.projectId) {
      try {
        await scopeCatalog.loadGlobal(props.projectId)
      } catch { /* 项目级公式不可用不阻断 */ }
    }
  } finally {
    dashboardCoverage.value = [
      { label: '报表预设', count: reportBoardRows().length },
      { label: '附注预设', count: noteBoardRows().length },
      { label: '项目级公式', count: projectScopeBoardRows().length },
      { label: '试算表覆盖', count: tbBoardRows().length },
    ]
    dashboardLoading.value = false
  }
})

// ─── E1 Sprint 2 Task 2.34/2.36: 用户自定义公式 Tab ──────────────────────────

interface UserFormulaItem {
  cell_key: string  // 'sheet!cell_ref'
  formula: string
  is_preset_override: boolean
  formula_type?: string
  modified_at?: string
}

const userFormulasList = ref<UserFormulaItem[]>([])
const wpIdForUserFormulas = ref<string>('')
const userFormulaError = ref('')
let userRequest = 0

function userFormulaRowClass(_ctx: { row: UserFormulaItem; rowIndex: number }) {
  return _ctx.row.is_preset_override ? 'gt-fm-user-override' : 'gt-fm-user-new'
}

async function loadUserFormulas(wpId: string) {
  const request = ++userRequest
  const session = dialogSession
  const subject = formulaSubject()
  const isCurrent = () => visible.value && request === userRequest && session === dialogSession && subject === formulaSubject()
  userFormulasList.value = []
  userFormulaError.value = ''
  if (!wpId) {
    userFormulaError.value = '请从底稿页面打开以查看用户公式。'
    return
  }
  wpIdForUserFormulas.value = wpId
  try {
    const data: any = await api.get(wpUserFormula.list(wpId))
    const list = data?.user_formulas || data?.items || data || {}
    const arr: UserFormulaItem[] = []
    if (Array.isArray(list)) {
      for (const it of list) arr.push(it)
    } else if (typeof list === 'object') {
      for (const [k, v] of Object.entries(list)) {
        const o = v as any
        arr.push({
          cell_key: k,
          formula: o?.formula || '',
          is_preset_override: !!o?.is_preset_override,
          formula_type: o?.formula_type,
          modified_at: o?.modified_at,
        })
      }
    }
    if (isCurrent()) userFormulasList.value = arr
  } catch {
    if (isCurrent()) userFormulaError.value = '用户公式加载失败，请检查权限或网络后重试。'
  }
}

async function onRestorePresetFormula(row: UserFormulaItem) {
  const wpId = wpIdForUserFormulas.value
  const session = dialogSession
  if (!wpId) return
  const isCurrent = () => visible.value && session === dialogSession && wpId === props.wpId
  try {
    await confirmDangerous(
      `确认将单元格 ${row.cell_key} 恢复为预设公式？当前自定义公式将被覆盖。`,
      '恢复预设公式',
    )
  } catch {
    return
  }
  try {
    if (!isCurrent()) return
    await api.delete(
      wpUserFormula.restorePreset(wpId, encodeURIComponent(row.cell_key)),
    )
    if (!isCurrent()) return
    userFormulasList.value = userFormulasList.value.filter((u) => u.cell_key !== row.cell_key)
    ElMessage.success(`已恢复 ${row.cell_key} 的预设公式`)
  } catch (err) {
    handleApiError(err, '恢复预设')
  }
}

async function onDeleteUserFormula(row: UserFormulaItem) {
  const wpId = wpIdForUserFormulas.value
  const session = dialogSession
  if (!wpId) return
  const isCurrent = () => visible.value && session === dialogSession && wpId === props.wpId
  try {
    await confirmDelete(`单元格 ${row.cell_key} 的自定义公式`)
  } catch {
    return
  }
  try {
    if (!isCurrent()) return
    await api.delete(
      wpUserFormula.restorePreset(wpId, encodeURIComponent(row.cell_key)),
    )
    if (!isCurrent()) return
    userFormulasList.value = userFormulasList.value.filter((u) => u.cell_key !== row.cell_key)
    ElMessage.success('已删除用户自定义公式')
  } catch (err) {
    handleApiError(err, '删除用户公式')
  }
}

watch([activeCategory, visible, () => props.wpId, () => props.projectId, () => props.year], ([category, open]) => {
  ++userRequest
  userFormulasList.value = []
  wpIdForUserFormulas.value = props.wpId || ''
  if (open && category === 'user_formulas') loadUserFormulas(props.wpId || '')
})

// ─── P2-3: 公式变更历史回滚回调 ──────────────────────────────────────────────

function onHistoryRollbackApplied(rowCode: string, formula: string) {
  // 回滚成功后，更新当前显示的行数据
  const rows = currentRows.value
  const target = rows.find((r: any) => r.row_code === rowCode)
  if (target) {
    target.formula = formula
  }
  emit('saved')
}
</script>

<style scoped>
.gt-fm-container {
  display: flex;
  gap: 12px;
  height: calc(100vh - 110px);
  min-height: 500px;
}
.gt-fm-sidebar {
  width: 220px;
  flex-shrink: 0;
  border: 1px solid var(--gt-color-border-info);
  border-radius: 8px;
  overflow-y: auto;
  background: var(--gt-color-primary-bg);
}
.gt-fm-sidebar-title {
  padding: 10px 14px 6px;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 1px;
}
/* 主公式表格统一 12 号字（用户要求：公式管理中心字号 12） */
.gt-fm-main-table :deep(.el-table__cell) {
  font-size: 12px;
}
.gt-fm-main-table :deep(.cell),
.gt-fm-main-table :deep(.cell code),
.gt-fm-main-table :deep(.el-input__inner),
.gt-fm-main-table :deep(.el-tag) {
  font-size: 12px !important;
}

.gt-fm-tree {
  background: transparent;
  --el-tree-node-hover-bg-color: #e8f0f8;
}
.gt-fm-tree :deep(.el-tree-node__content) {
  height: 30px;
  font-size: var(--gt-font-size-xs);
}
.gt-fm-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: var(--gt-bg-info);
  font-weight: 600;
  color: var(--gt-color-teal);
}
.gt-fm-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}
.gt-fm-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.gt-fm-breadcrumb {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.gt-fm-footer {
  margin-top: 8px;
  text-align: right;
}
.gt-fm-batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: linear-gradient(135deg, #edf3f9 0%, #d6e6f5 100%);
  border: 1px solid var(--gt-color-border-info);
  border-radius: 6px;
  margin-bottom: 6px;
}
/* 行样式 */
:deep(.gt-fm-row-auto) { background: var(--gt-color-success-light) !important; }
:deep(.gt-fm-row-logic) { background: var(--gt-color-wheat-light) !important; }
:deep(.gt-fm-row-reason) { background: var(--gt-bg-info) !important; }
:deep(.gt-fm-row-empty) { opacity: 0.7; }
:deep(.el-table__row:hover .gt-fm-row-auto),
:deep(.el-table__row:hover .gt-fm-row-logic),
:deep(.el-table__row:hover .gt-fm-row-reason) {
  background: var(--gt-bg-info) !important;
}
.gt-fm-dash-group-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-regular);
  padding: 8px 10px;
  background: var(--gt-color-primary-bg);
  border: 1px solid var(--gt-color-border-info);
  border-radius: 6px;
  margin-bottom: 4px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}
.gt-fm-dash-group-title:hover {
  background: var(--gt-bg-info);
}
.gt-fm-health-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.gt-fm-health-card {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-fm-health-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-fm-health-value {
  font-size: 18px;
  font-weight: 700;
}
.gt-fm-health-desc {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>

<!-- 公式管理弹窗独立配色（非 scoped，因为 el-dialog 渲染在 body） -->
<style>
.gt-fm-dialog .el-dialog__header {
  background: linear-gradient(135deg, #1a3a5c 0%, #2d5a87 60%, #3a7cb8 100%);
  padding: 14px 20px;
  margin: 0;
  border-radius: 8px 8px 0 0;
}
.gt-fm-dialog .el-dialog__title {
  color: var(--gt-color-text-inverse) !important;
  font-size: var(--gt-font-size-md);
  font-weight: 700;
  letter-spacing: 0.5px;
}
.gt-fm-dialog .el-dialog__headerbtn .el-dialog__close {
  color: rgba(255,255,255,0.9);
  font-size: 24px;
}
.gt-fm-dialog .el-dialog__headerbtn {
  top: 12px;
  right: 16px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(255,255,255,0.15);
  transition: background 0.2s;
}
.gt-fm-dialog .el-dialog__headerbtn:hover {
  background: rgba(255,255,255,0.3);
}
.gt-fm-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: var(--gt-color-text-inverse);
}
.gt-fm-dialog .el-dialog__body {
  border-top: 3px solid var(--gt-color-teal);
}
.gt-fm-dialog .el-dialog__footer {
  background: var(--gt-color-primary-bg);
  border-top: 1px solid var(--gt-color-border-info);
}
/* 应用自动运算按钮蓝色 */
.gt-fm-dialog .gt-fm-apply-btn {
  background: linear-gradient(135deg, #2d5a87, #3a7cb8) !important;
  border-color: var(--gt-color-teal) !important;
  color: var(--gt-color-text-inverse) !important;
}
.gt-fm-dialog .gt-fm-apply-btn:hover {
  background: linear-gradient(135deg, #1a3a5c, #2d5a87) !important;
}
/* 表头行蓝色系 */
.gt-fm-dialog :deep(.el-table th.el-table__cell) {
  background: var(--gt-bg-info) !important;
}
/* 项目级 ↔ 主模板差异面板 */
.gt-fm-master-diff {
  border: 1px solid var(--gt-color-border-light, #e8e4f0);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 10px;
  background: var(--gt-color-fill-lighter, #fafafa);
}
.gt-fm-master-diff__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.gt-fm-master-diff__title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-fm-master-diff__std {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
.gt-fm-master-diff__hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  line-height: 1.7;
}

/* 公式看板弹窗：最大化内容区 */
.gt-fm-dashboard-dialog .el-dialog__body {
  padding: 12px 16px !important;
  max-height: calc(96vh - 120px);
  overflow-y: auto;
}
</style>


<style scoped>
/* E1 Sprint 2 Task 2.34: 用户自定义公式 Tab 样式 */
.gt-fm-user-formulas {
  padding: 8px;
}
.gt-fm-user-alert {
  margin-bottom: 8px;
}
.gt-fm-mono {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--gt-color-text-regular);
}
:deep(.el-table__row.gt-fm-user-override) {
  background: rgba(230, 244, 234, 0.5) !important;  /* 绿色 */
}
:deep(.el-table__row.gt-fm-user-new) {
  background: rgba(232, 244, 253, 0.5) !important;  /* 蓝色 */
}
</style>
