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
        <!-- Task 3.2 / ADR-FMC-05：左栏默认只显精确当前 sheet 的 addr_id（当前页 anchors），
             「全局浏览」是独立显式按钮（不作缺上下文默认回退），缺 location identity 时
             fail-closed（空集 + 告警，不退全局树）。 -->
        <div class="gt-fm-sidebar-title">
          <span v-if="!isCurrentPageContext">数据源</span>
          <span v-else>{{ leftPanelGlobalBrowse ? '数据源（全局浏览）' : '当前页地址' }}</span>
          <!-- 「全局浏览」仅在当前页上下文作为独立显式按钮（ADR-FMC-05 AC4）；
               域级 scope（报表/附注/合并等）本就在浏览整域，不出此切换。 -->
          <el-button
            v-if="isCurrentPageContext && leftPanelGlobalBrowse"
            size="small"
            link
            type="primary"
            class="gt-fm-left-mode-btn"
            data-testid="formula-left-current-page"
            title="返回当前页地址（仅显示本 sheet 的坐标）"
            @click="exitGlobalBrowse"
          >↩ 当前页</el-button>
          <el-button
            v-else-if="isCurrentPageContext"
            size="small"
            link
            type="primary"
            class="gt-fm-left-mode-btn"
            data-testid="formula-left-global-browse"
            title="浏览全平台地址树（跨全部域，非当前页）"
            @click="enterGlobalBrowse"
          >🌐 全局浏览</el-button>
        </div>
        <!-- 缺当前页身份：fail-closed 显式告警（不列地址、不退全局） -->
        <el-alert
          v-if="isCurrentPageContext && !leftPanelGlobalBrowse && leftPanelWarning"
          :title="leftPanelWarning"
          type="warning"
          :closable="false"
          show-icon
          data-testid="formula-left-fail-closed"
          class="gt-fm-left-warning"
        />
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
        <el-alert
          v-if="props.formulaSession?.banner"
          :title="props.formulaSession.banner"
          type="warning"
          :closable="false"
          show-icon
          data-testid="formula-session-pinned-banner"
          style="margin: 0 12px 8px;"
        />
        <!-- 当前选中的路径 + 模板类型切换 -->
        <div class="gt-fm-breadcrumb">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-tag size="small" type="info" effect="plain" style="font-weight: 600;">{{ scopeLabel }}</el-tag>
            <el-tag v-if="!isConsolFormulaNode" size="small" type="success" effect="plain" title="当前页/当前节点已加载的公式数">
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
                ? '本页显示本项目的有效公式（每行标注 全局 / 本项目 / 模板），修改只写本项目'
                : '本页公式取自模板级预设，修改会影响所有使用同一适用准则的项目'"
            >
              {{ activeReportLevelLabel }}
            </el-tag>
          </div>
          <div v-if="!isConsolFormulaNode" style="display: flex; gap: 6px; align-items: center;">
            <el-button size="small" @click="showFormulaDashboard = true">📊 公式看板</el-button>
            <el-button size="small" @click="onOpenGlobalScopeOverview">🌐 全局公式</el-button>
            <!-- formula-global-settings-sync：全局设置 / 保存为模板 / 订阅模板（取代旧共享配置「公式审核配置」） -->
            <FormulaSettingsToolbar ref="settingsToolbarRef" :project-id="projectId" :domain="settingsDomain"
              :default-scope="settingsScope" :can-edit-global="canEditGlobal" :can-edit-project="!formulaReadOnly"
              @navigate="visible = false"
              @changed="onFormulaSettingsChanged" />
            <el-button size="small" @click="onImportPresetFormulas" :loading="loadingData">📥 导入预设</el-button>
            <el-button size="small" @click="onExportFormulaTemplate">📤 导出模板</el-button>
            <el-button size="small" @click="showFormulaImport = true">📥 Excel导入</el-button>
            <el-button v-if="isNoteDomainNodeKey(selectedNodeKey)" size="small" type="primary" plain
              data-testid="fm-note-edit" :disabled="!noteEditTarget"
              :title="noteEditTarget ? '' : '请先在左侧选择具体的附注章节'" @click="openNoteFormulaEditor()">✏️ 编辑本章节公式</el-button>
            <el-button size="small" @click="onAddFormulaRow">+ 新增公式</el-button>
            <el-button size="small" @click="onSaveAllFormulas" :loading="applying">💾 保存</el-button>
            <el-button size="small" type="primary" class="gt-fm-apply-btn" @click="onApplyFormulas" :loading="applying">⚡ 应用自动运算</el-button>
          </div>
        </div>

        <ConsolFormulaManagementPanel
          v-if="isConsolFormulaNode && projectId && year"
          :mode="isConsolNoteNode ? 'note' : 'report'"
          :project-id="projectId"
          :year="year"
          :template-type="fmTemplateType"
          :report-type="activeConsolReportType || 'balance_sheet'"
          :note-section="consolNoteSelectedSection || props.noteSection"
        />

        <!-- 分类 Tab -->
        <!-- Sprint 5.10: 健康度卡片 + URI 搜索 -->
        <div v-if="!isConsolFormulaNode" class="gt-fm-health-bar">
          <div class="gt-fm-health-card">
            <span class="gt-fm-health-label">健康度</span>
            <span class="gt-fm-health-value" :style="{ color: healthPercent >= 80 ? 'var(--gt-color-success)' : healthPercent >= 50 ? 'var(--gt-color-wheat)' : 'var(--gt-color-danger)' }">
              {{ healthPercent }}%
            </span>
            <span class="gt-fm-health-desc">{{ healthDesc }}（未审数列）</span>
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

        <!-- 智能公式建议（复盘修复 #9：当前节点有系统预设但该行尚未配置公式时展示） -->
        <div v-if="!isConsolFormulaNode && formulaSuggestions.length" class="gt-fm-suggest-bar">
          <div class="gt-fm-suggest-header" @click="showSuggestions = !showSuggestions">
            <span>💡 {{ formulaSuggestions.length }} 条公式建议</span>
            <span style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-left: 8px;">
              系统预设中有公式但当前行未配置
            </span>
            <span style="flex: 1;" />
            <el-button size="small" link>{{ showSuggestions ? '收起' : '展开' }}</el-button>
          </div>
          <div v-if="showSuggestions" class="gt-fm-suggest-list">
            <div v-for="s in formulaSuggestions.slice(0, 10)" :key="s.row_code" class="gt-fm-suggest-item">
              <span class="gt-fm-suggest-code">{{ s.row_code }}</span>
              <span class="gt-fm-suggest-name">{{ s.row_name }}</span>
              <code class="gt-fm-suggest-formula">{{ s.formula }}</code>
              <el-button size="small" type="primary" link @click="onApplySuggestion(s)">应用</el-button>
            </div>
            <div v-if="formulaSuggestions.length > 10" style="font-size: 11px; color: var(--gt-color-text-tertiary); padding: 4px 0;">
              还有 {{ formulaSuggestions.length - 10 }} 条，请在公式看板中查看
            </div>
          </div>
        </div>

        <el-tabs v-if="!isConsolFormulaNode" v-model="activeCategory" size="small" style="margin-bottom: 8px;">
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
              :year="year"
              :read-only="formulaReadOnly"
              @rollback-applied="onHistoryRollbackApplied"
            />
            <!-- spec: formula-management-deep-optimization · R6 — 公式版本时间轴 -->
            <FormulaTimelinePanel
              v-if="activeCategory === 'history' && projectId"
              :project-id="projectId"
              :year="year"
            />
          </el-tab-pane>
          <!-- chain-closure-phase2-formula-push-engine：公式推送（四表 / 试算表 / 调整分录 → 底稿 → 附注） -->
          <el-tab-pane v-if="projectId && year" name="formula_push">
            <template #label>📤 公式推送</template>
            <FormulaPushPanel
              v-if="activeCategory === 'formula_push' && pushWpCode"
              :project-id="projectId"
              :year="year"
              :wp-code="pushWpCode"
              :supported-wp-codes="pushWpCodes"
              :can-edit="!formulaReadOnly"
            />
            <div v-else-if="activeCategory === 'formula_push' && !pushWpCode" class="gt-fp-not-connected">
              <!-- formula-management-ux-improvements B3：改进空状态文案；没选底稿时先引导去选（R5 走查：原先一律说「本底稿尚未接入」） -->
              <el-empty :image-size="64">
                <template #description>
                  <p>{{ pushWpSelected ? '本底稿尚未接入自动推送' : '请先在左侧「📋 底稿」里选一张底稿（点工作簿或其中任一页）' }}</p>
                  <p style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">
                    {{ pushNotNeededReason || ('已接入：' + (pushWpCodes.length ? pushWpCodes.join('、') : '暂无')) }}
                  </p>
                </template>
              </el-empty>
            </div>
          </el-tab-pane>
        </el-tabs>

        <!-- 批量操作栏 -->
        <div v-if="!isConsolFormulaNode && selectedRows.length > 0 && !isCrossCheckMode" class="gt-fm-batch-bar">
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
        <el-table v-if="!isConsolFormulaNode && !isCrossCheckMode && !['user_formulas', 'history', 'formula_push'].includes(activeCategory)" v-loading="wpFormulaLoading" ref="formulaTableRef" class="gt-fm-main-table" :data="filteredRows" size="small" border max-height="calc(100vh - 300px)" style="width: 100%"
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
              <div v-if="editingId === row.id" style="display: flex; flex-direction: column; gap: 2px;">
                <!-- formula-management-ux-improvements A3：语法高亮输入 + 实时校验 -->
                <FormulaInput v-model="editFormula" :project-id="projectId" :report-rows="formulaInputReportRows" :wp-codes="formulaInputWpCodes" />
                <!-- formula-management-ux-improvements A4：快捷按钮改为参数选择器 -->
                <div style="display: flex; gap: 2px; flex-wrap: wrap;">
                  <FormulaParamPicker mode="tb" :tb-items="paramPickerTbItems" @select="onParamPickerSelect" />
                  <FormulaParamPicker mode="wp" :wp-items="paramPickerWpItems" @select="onParamPickerSelect" />
                  <FormulaParamPicker mode="note" :note-items="paramPickerNoteItems" @select="onParamPickerSelect" />
                  <FormulaParamPicker mode="row" :row-items="paramPickerRowItems" @select="onParamPickerSelect" />
                </div>
              </div>
              <!-- Task 1.4：只读投影行禁双击/点击进入编辑（dblclick/click 不绑 startEdit）。 -->
              <code v-else-if="row.formula && isReadonlyProjectionRow(row)" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); word-break: break-all;" :title="'只读取数/溯源说明'">{{ row.formula }}</code>
              <code v-else-if="row.formula" @dblclick="startEdit(row)" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular); word-break: break-all; cursor: pointer;" :title="'双击编辑公式'">{{ row.formula }}</code>
              <span v-else-if="isReadonlyProjectionRow(row)" style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs);">—</span>
              <span v-else @click="startEdit(row)" style="color: var(--gt-color-text-placeholder); cursor: pointer; font-size: var(--gt-font-size-xs); border: 1px dashed var(--gt-color-border-light); padding: 2px 8px; border-radius: 4px;" title="点击添加公式">
                + 点击添加公式
              </span>
            </template>
          </el-table-column>
          <!-- V179: 调整列公式（审计调整 / 重分类调整） -->
          <el-table-column label="AJE公式" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <code v-if="row.aje_formula" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-teal); word-break: break-all;">{{ row.aje_formula }}</code>
              <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">未配置（走默认推导）</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE公式" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <code v-if="row.rje_formula" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-teal); word-break: break-all;">{{ row.rje_formula }}</code>
              <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">未配置（走默认推导）</span>
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
          <el-table-column label="来源" width="88" align="center">
            <template #default="{ row }">
              <!-- Task 1.4：只读投影不得包装成「自定义」正式公式；标「只读」去伪装。 -->
              <span v-if="isReadonlyProjectionRow(row)" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">只读</span>
              <!-- formula-global-settings-sync R1.4：有效定义行标层级（全局 / 本项目 / 模板 / 暂缓采用）与待确认 -->
              <span v-else-if="row._layer_label"><el-tag size="small" effect="plain" :type="layerTagType(row._layer)">{{ row._layer_label }}</el-tag><el-tag v-if="row._pending" size="small" type="danger" effect="plain">待确认</el-tag></span>
              <span v-else-if="isPresetFormula(row)" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-teal); background: var(--gt-bg-info); padding: 1px 6px; border-radius: 3px;">预设</span>
              <span v-else-if="row.formula" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">自定义</span>
            </template>
          </el-table-column>
          <el-table-column label="引用方" width="70" align="center">
            <template #default="{ row }">
              <el-badge v-if="row._ref_count > 0" :value="row._ref_count" :max="99" type="info"
                style="cursor: pointer;" @click.native="depPanelRef.value?.load(`report:${selectedReportType.value}:${row.row_code || row.id}`)" title="点击查看依赖关系" />
              <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">0</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button v-if="canRestoreRow(row) && editingId !== row.id" size="small" link @click.stop="onRestoreGlobal(row)">恢复全局</el-button>
              <!-- Task 1.4 / ADR-FMC-02：surfaced/extraction 只读投影 —— 不渲染「编辑」按钮，
                   仅标「只读」，避免把后端 readonly:true 的说明投影当成可编辑权威公式。 -->
              <el-tooltip v-if="isReadonlyProjectionRow(row)" content="取数/溯源说明投影，只读不可编辑" placement="top">
                <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">只读</span>
              </el-tooltip>
              <el-tooltip v-else-if="_isRowOwnedByPush(row)" content="此单元格由系统公式推送维护，不可编辑" placement="top">
                <el-button size="small" link disabled>编辑</el-button>
              </el-tooltip>
              <el-button v-else-if="editingId !== row.id" size="small" link type="primary" @click.stop="startEdit(row)">编辑</el-button>
              <el-button v-else size="small" link @click.stop="saveEdit(row)" style="color: var(--gt-color-success);">保存</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="!isConsolFormulaNode" class="gt-fm-footer">
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">共 {{ currentRows.length }} 行，{{ currentRows.filter(r => r.formula).length }} 个公式{{ Object.values(formulaResults).filter(r => r.value != null).length ? `，${Object.values(formulaResults).filter(r => r.value != null).length} 个已计算` : '' }}</span>
        </div>

        <FormulaDependencyPanel v-if="!isConsolFormulaNode" ref="depPanelRef" :project-id="props.projectId" />

        <!-- 表间审核模式（已拆出为独立组件 FormulaCrossCheckPanel） -->
        <FormulaCrossCheckPanel
          v-if="isCrossCheckMode"
          :selected-path="selectedPath"
          :rules="crossCheckRulesForCurrent"
          :exec-empty="crossCheckExecEmpty"
          :running="crossCheckRunning"
          :show-dialog="showCrossRuleDialog"
          :dialog-title="crossRuleDialogTitle"
          :form="crossRuleForm"
          :project-id="props.projectId"
          :year="props.year"
          :layer-tag-type="layerTagType"
          :layer-label="layerLabel"
          :issue-run="crossCheckIssueRun"
          :exec-loading="crossCheckExecLoading"
          @refresh-exec="cc.refreshExec()"
          @run="onRunCrossCheck"
          @add="onAddCrossRule"
          @edit="onEditCrossRule"
          @remove="onRemoveCrossRule"
          @save="onSaveCrossRule"
          @update:show-dialog="showCrossRuleDialog = $event"
        />
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>

    <!-- 附注章节公式编辑 / 保存 / 应用（spec formula-governance-coverage-closure R4） -->
    <NoteFormulaDialog v-if="projectId && year" v-model="showNoteFormulaDialog" :current-note="noteDialogTarget"
      :project-id="projectId" :year="Number(year)" @saved="onNoteFormulasSaved" @applied="emit('applied')" />

    <!-- 公式看板弹窗（已拆出为独立组件 FormulaDashboardDialog） -->
    <FormulaDashboardDialog
      v-model="showFormulaDashboard"
      :rows="allFormulaRows"
      :loading="dashboardLoading"
      :coverage-text="dashboardCoverageText"
      :category-label="categoryLabel"
      :category-tag-type="categoryTagType"
      :fmt="prefs.fmt"
      :project-id="props.projectId"
      :year="props.year"
      @edit="onDashboardEdit"
      @locate="onDashboardLocate"
    />

    <!-- 公式编辑弹窗 -->
    <FormulaEditDialog
      v-model="showFormulaEdit"
      :row="editingRow"
      :source-rows="currentRows"
      :applicable-standard="`${fmTemplateType}_standalone`"
      :project-id="props.projectId"
      :year="props.year"
      @dirty-change="onFormulaDraftDirtyChange"
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

    <!-- 全局公式总览弹窗（已拆出为独立组件 FormulaGlobalScopeDialog） -->
    <FormulaGlobalScopeDialog
      v-model="showGlobalScopeOverview"
      :total-count="scopeCatalog.totalCount.value"
      :groups="globalScopeGroups"
      :report-preset-hint="reportPresetHint"
      :category-label="categoryLabel"
      :category-tag-type="categoryTagType"
      :master-diff-all="masterDiffAll"
      :master-diff-standard="masterDiffStandard"
      :master-diff-loaded="masterDiffLoaded"
      :master-diff-loading="masterDiffLoading"
      :master-diff-applying="masterDiffApplying"
      @go-report-presets="onGoToReportPresets"
      @go-note-presets="onGoToNotePresets"
      @open-dashboard="onOpenDashboardFromGlobal"
      @load-diff="loadMasterDiff"
      @apply-master="onApplyMasterUpdate"
      @suggest-to-master="onSuggestToMaster"
      @materialize-presets="onMaterializeReportPresets"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete, confirmDangerous } from '@/utils/confirm'
import { api } from '@/services/apiProxy'
import { reportConfig as P_rc, noteTemplates as P_nt, consolNoteSections as P_cn, linkageBus, formulaAuditLog } from '@/services/apiPaths'
// spec: formula-management-runtime-closure Task 14 — 公式端点收敛进 apiPaths（纯搬迁，URL 逐字不变）
import {
  projectFormula,
  reportConfigFormula,
  wpFormula,
  wpUserFormula,
  formulaPush,
} from '@/services/apiPaths/formula'
import { fmtAmount } from '@/utils/formatters'
import { isOwnedKey } from '@/generated/formulaPushOwnedKeys'
import FormulaEditDialog from './FormulaEditDialog.vue'
import FormulaInput from './FormulaInput.vue'
import FormulaParamPicker from './FormulaParamPicker.vue'
import FormulaHistoryTab from './FormulaHistoryTab.vue'
import FormulaTimelinePanel from './FormulaTimelinePanel.vue'
import FormulaPushPanel from './FormulaPushPanel.vue'
import ConsolFormulaManagementPanel from './ConsolFormulaManagementPanel.vue'
import {
  CONSOL_REPORT_TREE_ITEMS,
  consolReportNodeOfType,
  consolReportTypeOfNode,
} from './consolFormulaManagement'
// formula-global-settings-sync：报表行读本项目有效定义 + 保存写本项目适配 + 全局设置 / 模板入口
import FormulaSettingsToolbar from './settings/FormulaSettingsToolbar.vue'
import { canRestoreRow, fetchEffectiveReportRows, invalidateEffectiveReport, markLoaded, restoreReportRows, rowChanged, saveReportRows } from './settings/reportEffectiveRows'
import { layerLabel, layerTagType, showFormulaError } from '@/composables/formula/useFormulaSettings'
import { savedDefinitionVersion, wpFormulaBatchNotice, wpFormulaSaveNotice } from '@/composables/formula/wpFormulaSaveNotice'
import { useTbDetailFormulas } from './composables/useTbDetailFormulas'
import { useCrossCheckRules } from './composables/useCrossCheckRules'
import { issueRunForNode } from './formulaIssueHint'
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
import { noteSectionToNodeKey, buildNoteFormulaRows, isNoteDomainNodeKey, mergeNoteUserFormulaRows, type NoteUserFormula } from './noteScopeTargeting'
// Task 4.1 / ADR-FMC-04：弹窗附注节点改调 list_note_formulas（含用户编辑集 _user_formulas）。
import { noteFormula as P_nf } from '@/services/apiPaths/formula'
import type { CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import type { WorkpaperCapabilitySnapshot } from '@/shell/formula/workpaperCapabilitySnapshot'
import {
  decideSaveDraft,
  discardDraftAndFollowLatest,
  markSessionDirty,
  type FormulaManagerSession,
  type SaveDraftDecision,
} from '@/shell/formula/openFormulaManagerCommand'
import { matchRowToSelectedSheet, sheetCodeEquals } from './sheetIdentityMatch'
// Task 6.2 / MEDIUM-2：表间审核树 key ↔ 规则 map key 单一生成函数（需求 7.4）。
import {
  CROSS_CHECK_DOMAINS,
  CROSS_CHECK_NODE_KEYS,
  crossCheckNodeKey,
} from './crossCheckKey'
// Task 6.3（需求 10.1/10.2/10.4）：缓存按 project key 隔离 + 陈旧响应守卫 + 保存年份口径单一真源。
import {
  projectCacheKey,
  cacheKeyMatches,
  shouldApplyResponse,
  resolveSaveYear,
  createKeyedSingleFlight,
} from './projectCacheKey'
// Task 1.4 / ADR-FMC-02：公式行 kind 分类 + 只读判定 + 保存端点分派单一真源。
import {
  isReadonlyProjectionRow,
  resolveSaveDispatch,
} from './formulaRowKind'
// Task 1.5 / ADR-FMC-02 改动点③：wp 公式行契约字段（category/description）映射单一真源。
import { mapWpItemToRowFields } from './wpFormulaFields'
// Task 3.2 / ADR-FMC-05：左栏当前页 anchors + fail-closed 告警 + location identity 单一真源。
import {
  loadCurrentSheetLeftPanel,
  type LeftPanelAnchorNode,
  type LocationIdentity,
} from './leftPanelAnchors'
// formula-settings-wiring-closure T11：提取面板组件
import CrossCheckHistoryPanel from './panels/CrossCheckHistoryPanel.vue'
import FormulaDependencyPanel from './panels/FormulaDependencyPanel.vue'
import PushCoverageCard from './panels/PushCoverageCard.vue'
import FormulaDashboardDialog from './FormulaDashboardDialog.vue'
import FormulaGlobalScopeDialog from './FormulaGlobalScopeDialog.vue'
import FormulaCrossCheckPanel from './FormulaCrossCheckPanel.vue'
import NoteFormulaDialog from './NoteFormulaDialog.vue'

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
  /**
   * 试算表域：调用页当前正在查看的报表类型（如 `income_statement`）。
   * 当 `scope='tb'` 且此值非空时，弹窗定位到「报表 > 利润表」等对应报表节点，
   * 而非默认的「科目明细」节点。值域与 treeData 报表域 key 后缀一致。
   */
  initialReportType?: string
  canonicalLocation?: CanonicalWorkpaperLocation
  capabilitySnapshot?: WorkpaperCapabilitySnapshot
  formulaSession?: FormulaManagerSession
  readOnly?: boolean
}>(), {
  scope: 'report',
  readOnly: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'saved'): void
  (e: 'applied'): void
  (e: 'session-change', session: FormulaManagerSession): void
}>()

// formula-settings-wiring-closure T11：提取面板组件的 ref
const depPanelRef = ref<InstanceType<typeof FormulaDependencyPanel> | null>(null)
const ccHistoryRef = ref<InstanceType<typeof CrossCheckHistoryPanel> | null>(null)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const formulaReadOnly = computed(() => props.readOnly === true)

type FormulaMutationGate = SaveDraftDecision | { allow: true; location?: undefined }

function evaluateFormulaMutation(baseVersionOk = true): FormulaMutationGate {
  if (formulaReadOnly.value) {
    return { allow: false, reasonCode: 'read_only', detail: '当前账号只有公式查看权限，不能修改或执行公式' }
  }
  if (props.scope !== 'workpaper') return { allow: true }
  if (!props.formulaSession || !props.capabilitySnapshot || !props.canonicalLocation) {
    return {
      allow: false,
      reasonCode: 'context_expired',
      detail: '公式能力上下文已失效，请关闭后从当前底稿重新打开',
    }
  }
  const pinned = props.formulaSession.pinnedLocation
  return decideSaveDraft({
    session: props.formulaSession,
    capability: props.capabilitySnapshot,
    routeOwnerValid: pinned.projectId === props.projectId && pinned.wpId === props.wpId,
    baseVersionOk,
  })
}

function guardFormulaMutation(baseVersionOk = true): boolean {
  const decision = evaluateFormulaMutation(baseVersionOk)
  if (!decision.allow) ElMessage.warning(decision.detail)
  return decision.allow
}

function onFormulaDraftDirtyChange(dirty: boolean) {
  if (props.scope !== 'workpaper' || !props.formulaSession) return
  const next = dirty
    ? markSessionDirty(props.formulaSession)
    : discardDraftAndFollowLatest(props.formulaSession)
  emit('session-change', next)
}

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

// globalScopeNonEmpty 已移到 FormulaGlobalScopeDialog 内部

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
// masterDiff 筛选/标签/颜色已移到 FormulaGlobalScopeDialog 内部
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
  if (!guardFormulaMutation()) return
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
  if (!guardFormulaMutation()) return
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
  if (!guardFormulaMutation()) return
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

/** 合并报表 / 合并附注使用独立 CRUD 面板，禁止落入单体 report_config / note preset 分支。 */
const activeConsolReportType = computed(() => consolReportTypeOfNode(selectedNodeKey.value))
const isConsolNoteNode = computed(() => {
  const k = selectedNodeKey.value
  // 合并附注根节点、或具体科目子节点（排除章级节点 consol_note_chapter_* 和加载占位）
  return k === 'consol_note'
    || (k.startsWith('consol_note_') && !k.startsWith('consol_note_chapter_') && k !== 'consol_note_loading')
})
const isConsolFormulaNode = computed(() => !!activeConsolReportType.value || isConsolNoteNode.value)

// ── 合并附注树（动态加载，按章 → 科目分组，与单体附注树同构） ──
const consolNoteTreeChildren = ref<any[]>([])
const consolNoteTreeLoaded = ref(false)
/** 用户在合并附注树上选中的 section_id（如 "五、1"），传递给 ConsolFormulaManagementPanel */
const consolNoteSelectedSection = ref('')
// 合并附注入口会从 watch 与 applyConsolNoteTarget 两处同时调用：同一模板只发一次（见 createKeyedSingleFlight）
const consolNoteTreeFlight = createKeyedSingleFlight()
function loadConsolNoteTree(): Promise<void> {
  return consolNoteTreeFlight(fmTemplateType.value, fetchConsolNoteTree)
}

async function fetchConsolNoteTree() {
  if (consolNoteTreeLoaded.value) return
  try {
    const data = await api.get<any[]>(P_cn.list(fmTemplateType.value), {
      validateStatus: (s: number) => s < 600,
    })
    const groups: any[] = data ?? []
    if (!Array.isArray(groups) || !groups.length) return

    const CHAPTER_ORDER = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
      '十一', '十二', '十三', '十四', '十五', '十六', '十七']
    const chapterMap: Record<string, { label: string; children: any[] }> = {}

    for (const group of groups) {
      for (const section of group.children || []) {
        const sectionId: string = section.section_id || ''
        const title: string = section.title || sectionId
        const chMatch = sectionId.match(/^([一二三四五六七八九十]+(?:[一二三四五六七八九十])?)/)
        const chapter = chMatch ? chMatch[1] : '其他'

        if (!chapterMap[chapter]) {
          const chapterLabels: Record<string, string> = {
            '一': '一、公司概况', '二': '二、编制基础', '三': '三、会计政策',
            '四': '四、税项', '五': '五、报表科目注释', '六': '六、其他',
            '七': '七、关联方', '八': '八、或有事项', '九': '九、承诺',
            '十': '十、日后事项',
          }
          chapterMap[chapter] = {
            label: chapterLabels[chapter] || group.label || `${chapter}、其他`,
            children: [],
          }
        }
        chapterMap[chapter].children.push({
          key: `consol_note_${sectionId}`,
          label: title.length > 24 ? title.slice(0, 24) + '…' : title,
          icon: '',
          _sectionId: sectionId,
          _sectionTitle: title,
        })
      }
    }

    const result: any[] = []
    for (const ch of CHAPTER_ORDER) {
      if (chapterMap[ch]) {
        result.push({
          key: `consol_note_chapter_${ch}`,
          label: chapterMap[ch].label,
          icon: '',
          children: chapterMap[ch].children,
        })
      }
    }
    if (chapterMap['其他']?.children.length) {
      result.push({
        key: 'consol_note_chapter_other',
        label: '其他',
        icon: '',
        children: chapterMap['其他'].children,
      })
    }
    consolNoteTreeChildren.value = result
    consolNoteTreeLoaded.value = true
  } catch { /* 降级：保持空子节点 */ }
}

/**
 * 节点 key → 报表类型（`balance_sheet` 等），非报表类节点返回 ''。
 *
 * 🔴 报表域 `report_{rt}` 与试算平衡表域 `tb_summary_{rt}` 共用同一套 report_config
 * 行次 —— 试算平衡表就是「按报表行次汇总的试算视图」，行次定义同源、公式同源，
 * 只是列口径不同（未审/调整/审定 vs 报表数）。两者都必须解析到同一个 rt，否则
 * 试算平衡表侧的节点会被所有 `startsWith('report_')` 判断漏掉 ⇒ 右侧空表、
 * 保存/应用/导入全部静默失效。
 */
function reportTypeOfNode(nodeKey: string): string {
  if (nodeKey.startsWith('tb_summary_')) return nodeKey.slice('tb_summary_'.length)
  if (nodeKey.startsWith('report_')) return nodeKey.slice('report_'.length)
  return ''
}

/** 当前选中节点对应的报表类型（空串 = 当前不是报表类节点）。 */
const activeReportType = computed(() => reportTypeOfNode(selectedNodeKey.value))

/** 归一化调用页模板类型：仅 soe / listed 两版预设，custom 等按国企版兜底。 */
function normalizeTemplateType(t?: string): 'soe' | 'listed' {
  return t === 'listed' ? 'listed' : 'soe'
}
const fmTemplateType = ref<string>(normalizeTemplateType(props.templateType))

// Task 6.3（需求 10.1）：当前上下文的项目隔离缓存键（project + 模板版本 + 年度）。
// report/note/cross-check 三个加载态都以它为准判缓存命中；切项目后此键变化 → 旧缓存失效。
const currentProjectCacheKey = computed(() =>
  projectCacheKey({
    projectId: props.projectId,
    templateType: fmTemplateType.value,
    year: props.year,
  }),
)

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
  consolNoteTreeLoaded.value = false
  consolNoteTreeChildren.value = []
  loadNoteTree()
  loadConsolNoteTree()
  loadRowsForNode(selectedNodeKey.value)
}

function allowTreeDrop(draggingNode: any, dropNode: any, type: string) {
  return draggingNode.parent === dropNode.parent && type !== 'inner'
}

// ── 动态附注树（从项目实际附注章节加载，项目不同内容不同） ──
const noteTreeChildren = ref<any[]>([])
const noteTreeLoaded = ref(false)
// Task 6.3（需求 10.1）：缓存命中记录的项目键。切项目后与 currentProjectCacheKey 不等 → 失效。
const noteTreeCacheKey = ref<string | null>(null)
// 打开链路会从 watch 与 applyNoteScopeTarget 两处同时调用：同一项目键只发一次（见 createKeyedSingleFlight）
const noteTreeFlight = createKeyedSingleFlight()
function loadNoteTree(): Promise<void> {
  return noteTreeFlight(currentProjectCacheKey.value, fetchNoteTree)
}

async function fetchNoteTree() {
  // 缓存按 project key 隔离：仅当已加载且缓存键 == 当前键才复用（切项目后判未命中、重新加载）。
  if (noteTreeLoaded.value && cacheKeyMatches(noteTreeCacheKey.value, currentProjectCacheKey.value)) return
  // 本次请求绑定发起时的项目键；响应回来若已切项目则丢弃（旧响应不覆盖新项目，需求 10.1）。
  const reqKey = currentProjectCacheKey.value
  try {
    // 优先从项目级附注 API 加载（项目不同结构不同）
    if (props.projectId && props.year) {
      const { getDisclosureNoteTree } = await import('@/services/auditPlatformApi')
      let notes: unknown = []
      try {
        // 附注未生成（404）是正常空态：静默改用下面的模板目录（原先弹「附注数据不存在」且跳过模板目录）
        notes = await getDisclosureNoteTree(props.projectId, Number(props.year), { _silent: true } as any)
      } catch (e: any) {
        if ((e?.response?.status ?? e?.status) !== 404) ElMessage.warning('本项目附注目录加载失败，暂按模板目录显示')
      }
      if (!shouldApplyResponse(reqKey, currentProjectCacheKey.value)) return
      if (Array.isArray(notes) && notes.length) {
        noteTreeChildren.value = buildNoteTreeFromProjectData(notes)
        noteTreeLoaded.value = true
        noteTreeCacheKey.value = reqKey
        return
      }
    }
    // 降级：从模板级 API 加载（不区分项目）
    const data = await api.get(P_nt.list(fmTemplateType.value), {
      validateStatus: (s: number) => s < 600,
    })
    if (!shouldApplyResponse(reqKey, currentProjectCacheKey.value)) return
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
    noteTreeCacheKey.value = reqKey
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
/**
 * 试算平衡表视图支持的报表类型，与 `TrialBalance.vue` 的 `tbSummaryTypes` 严格对齐。
 * 试算表页只按这 4 张表做试算汇总（无权益变动表/资产减值准备表），多列会得到空节点。
 */
const TB_SUMMARY_REPORT_TYPES = [
  'balance_sheet',
  'income_statement',
  'cash_flow_statement',
  'cash_flow_supplement',
] as const

const reportTypes = ref<Array<{ type: string; label: string; count: number }>>(
  Object.entries(REPORT_SUBTYPE_LABELS_FALLBACK).map(([type, label]) => ({ type, label, count: 0 }))
)
const reportTypesLoaded = ref(false)
// Task 6.3（需求 10.1）：报表类型缓存命中记录的项目键。
const reportTypesCacheKey = ref<string | null>(null)

async function loadReportTypes() {
  // 缓存按 project key 隔离：切项目后缓存键不等 → 判未命中、重新加载（需求 10.1）。
  if (reportTypesLoaded.value && cacheKeyMatches(reportTypesCacheKey.value, currentProjectCacheKey.value)) return
  const reqKey = currentProjectCacheKey.value
  try {
    const data = await api.get('/api/report-config/types', {
      params: { project_id: props.projectId },
      _silent: true,  // 404 不弹全局错误 toast
    } as any)
    // 旧项目的 late response 不覆盖新项目结果（需求 10.1）。
    if (!shouldApplyResponse(reqKey, currentProjectCacheKey.value)) return
    const items = Array.isArray(data) ? data : (data?.data ?? [])
    if (Array.isArray(items) && items.length) {
      reportTypes.value = items.map((r: any) => ({
        type: r.report_type || r.type,
        label: r.label || REPORT_SUBTYPE_LABELS_FALLBACK[r.report_type || r.type] || r.report_type,
        count: r.formula_count ?? 0,
      }))
      reportTypesLoaded.value = true
      reportTypesCacheKey.value = reqKey
      return
    }
  } catch { /* 降级到静态 */ }
  if (!shouldApplyResponse(reqKey, currentProjectCacheKey.value)) return
  // 降级：API 不可用时用静态
  reportTypes.value = Object.entries(REPORT_SUBTYPE_LABELS_FALLBACK).map(([type, label]) => ({
    type, label, count: countFormulas(type),
  }))
  reportTypesLoaded.value = true
  reportTypesCacheKey.value = reqKey
}

// ACNR sheet 列表缓存（从 useAcnr 加载）
const acnrSheets = shallowRef<AcnrSheetEntry[]>([])
const acnrTreeLoaded = ref(false)

// ── Task 3.2 / ADR-FMC-05：左栏当前页 anchors 状态 ──
// 「当前页上下文」= 从某张底稿实例页打开（props.wpId 存在或 scope='workpaper'）。
// 此上下文左栏默认只显精确当前 sheet 的 anchors（缺身份 fail-closed）。报表/附注/试算表/
// 合并等域级 scope 没有单一当前 sheet，属域级浏览，仍走全局域树（非「缺上下文回退」，
// 而是这些 scope 本就在浏览整域）。
const isCurrentPageContext = computed(() => !!props.wpId || props.scope === 'workpaper')
// 默认模式 = 当前页 anchors（只显精确当前 sheet 的 addr_id）；leftPanelGlobalBrowse=true
// 时才切换到全局五域树（显式「全局浏览」按钮触发，非缺上下文默认回退）。
const leftPanelGlobalBrowse = ref(false)
// 当前页 anchors 节点（current-sheet 模式的左栏数据）；每行带同一 location identity。
const currentSheetAnchors = shallowRef<LeftPanelAnchorNode[]>([])
// fail-closed 告警文案（缺当前页身份时非空；current-sheet / global-browse 为空串）。
const leftPanelWarning = ref('')
// 命中的当前页 location identity（左右栏对齐用；current-sheet 有值）。
const currentPageIdentity = shallowRef<LocationIdentity | null>(null)

/** 当前页 location identity（project_id + wp_id + sheet_uid=解析后结构化 sheet_code）。 */
function currentLocationIdentity(): Partial<LocationIdentity> {
  return {
    projectId: props.projectId || '',
    wpId: props.wpId || '',
    sheetUid: selectedWpSheetCode.value || '',
  }
}

/**
 * 加载左栏当前页 anchors（Task 3.2 默认行为）。
 * identity 完整 → 调当前 sheet anchors（useAcnr().listCells = GET /api/acnr/anchors），
 * 只显精确当前 sheet 的 addr_id；identity 不完整 → fail-closed（空集 + 告警，不退全局树）。
 */
async function loadCurrentSheetAnchors() {
  const identity = currentLocationIdentity()
  // sheet_uid 口径 = 解析后的结构化 sheet_code（selectedWpSheetCode）；wp_code 用于拼 anchors 命名空间。
  const wpCode = props.wpCode || selectedWpCode.value || ''
  const sheet = selectedWpSheetCode.value || ''
  // Task 6.3（需求 10.4）：ACNR listCells 是 **项目级** GET（useAcnr(props.projectId)）。
  // 记录发起时的项目键；若 await 期间切了项目（含 http 去重取消→重发的 abort 后重发场景），
  // 丢弃旧响应、不写入新项目的左栏状态，避免跨项目陈旧上下文污染。
  const reqKey = currentProjectCacheKey.value
  const result = await loadCurrentSheetLeftPanel(identity, async () => {
    if (!wpCode || !sheet) return []
    try {
      return await useAcnr(props.projectId).listCells(wpCode, sheet)
    } catch (e) {
      console.warn('[FormulaManager] 当前页 anchors 加载失败', e)
      return []
    }
  })
  if (!shouldApplyResponse(reqKey, currentProjectCacheKey.value)) return
  currentSheetAnchors.value = result.nodes
  leftPanelWarning.value = result.warning
  currentPageIdentity.value = result.identity
}

/** 显式进入全局浏览（独立按钮触发，非缺上下文默认回退）。 */
async function enterGlobalBrowse() {
  leftPanelGlobalBrowse.value = true
  leftPanelWarning.value = ''
  await loadAcnrTree()
}

/** 退回当前页地址模式（重新加载当前页 anchors）。 */
async function exitGlobalBrowse() {
  leftPanelGlobalBrowse.value = false
  await loadCurrentSheetAnchors()
}

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
  // Task 3.2 / ADR-FMC-05：当前页上下文（底稿实例页）左栏默认只显精确当前 sheet 的 anchors。
  //   - current-sheet 模式：返回当前页 anchors 节点（每行带 location identity）。
  //   - fail-closed（缺当前页身份）：空集（告警已由 leftPanelWarning 独立显示，不退全局树）。
  // 域级浏览上下文（报表/附注/试算表/合并等 scope，无单一当前 sheet）与用户显式点
  // 「全局浏览」(leftPanelGlobalBrowse=true) 时，才构建下方全局五域树。
  if (isCurrentPageContext.value && !leftPanelGlobalBrowse.value) {
    return currentSheetAnchors.value
  }

  // ACNR 五域树（动态，来自 catalog；与地址坐标名称库一致）
  const acnrDrivenTree: any[] = []

  // 1. 试算平衡表域
  // 「试算平衡表」按报表类型分子节点，与试算表页的 4 个 tab 一一对应 —— 否则从
  // 利润表 tab 点公式管理只能落到一个笼统的父节点（旧实现恒按资产负债表取数），
  // 用户看到的是别张表的行次。
  acnrDrivenTree.push({
    key: 'trial_balance', label: DOMAIN_TREE_META.tb.label, icon: DOMAIN_TREE_META.tb.icon, children: [
      { key: 'tb_detail', label: '科目明细', icon: '' },
      {
        key: 'tb_summary', label: '试算平衡表', icon: '',
        children: TB_SUMMARY_REPORT_TYPES.map((rt) => ({
          key: `tb_summary_${rt}`,
          label: REPORT_SUBTYPE_LABELS_FALLBACK[rt] || rt,
          icon: '',
          count: countFormulas(rt),
        })),
      },
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
    key: 'consol_report', label: '合并报表', icon: '🔗', children:
      CONSOL_REPORT_TREE_ITEMS.map((item) => ({ ...item, icon: '' })),
  })

  // 合并附注公式（模板级单元格公式，独立于单体附注校验预设）
  acnrDrivenTree.push({
    key: 'consol_note', label: '合并附注', icon: '📝',
    children: consolNoteTreeChildren.value.length
      ? consolNoteTreeChildren.value
      : [{ key: 'consol_note_loading', label: '加载中…', icon: '⏳' }],
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

  // 表间审核（Task 6.2 / MEDIUM-2：父节点 key 一律经 crossCheckNodeKey 生成，
  // 与 crossCheckRulesMap 的 key 同源——避免树 key 与规则 map key 偏移致右栏恒空）
  acnrDrivenTree.push({
    key: 'cross_check', label: '表间审核', icon: '🔗', children: [
      { key: crossCheckNodeKey('report_note'), label: '报表 ↔ 附注', icon: '🔄', children: crossCheckItems.value.report_note },
      { key: crossCheckNodeKey('report_wp'), label: '报表 ↔ 底稿', icon: '🔄', children: crossCheckItems.value.report_wp },
      { key: crossCheckNodeKey('note_wp'), label: '附注 ↔ 底稿', icon: '🔄', children: crossCheckItems.value.note_wp },
      { key: crossCheckNodeKey('consol'), label: '合并 ↔ 报表', icon: '🔄', children: [
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

// ── cross_check composable（拆出 useCrossCheckRules.ts，原 ~130 行） ──
const cc = useCrossCheckRules({
  projectId: computed(() => props.projectId || ''),
  year: computed(() => props.year),
  selectedNodeKey, currentProjectCacheKey,
  cacheKeyMatches, shouldApplyResponse, api, projectFormula, P_rc: P_rc,
  guardFormulaMutation, showFormulaError,
  askApplyScope: (d: string, s: string[]) => { settingsToolbarRef.value?.askApplyScope(d, s) },
  CROSS_CHECK_NODE_KEYS,
})
const crossCheckItems = cc.execItems
const crossCheckLoaded = cc.execLoaded
const crossCheckExecEmpty = cc.execEmpty
const crossCheckExecLoading = cc.execLoading
// 问题清单 / 提醒取自同一次勾稽响应，按当前树节点裁剪（spec formula-governance-coverage-closure R4）
const crossCheckIssueRun = computed(() => issueRunForNode(cc.execRun.value, selectedNodeKey.value))
const loadCrossCheckItems = cc.loadExecItems
const crossCheckTokens = cc.tokens
function applyCrossCheckRules(data: any) { cc.applyRulesData(data) }
async function persistCrossCheckRules() { await cc.persist() }
async function loadCrossCheckUserRules() { await cc.loadUserRules() }

// ── 数据加载 ──
const allRowsMap = ref<Record<string, any[]>>({})
const loadingData = ref(false)
const showFormulaImport = ref(false)

// 公式执行结果缓存（独立于行数据，确保响应式）
const formulaResults = ref<Record<string, { value: number | null; trace: any[] }>>({})

const notePresetFormulas = ref<any[]>([])

// Task 4.1 / ADR-FMC-04：当前选中附注章节的用户编辑集公式（来自 list_note_formulas，
// 含 table_data._user_formulas）。按 section 缓存最近一次加载结果，避免切节点时串章。
const noteUserFormulas = ref<NoteUserFormula[]>([])
const noteUserFormulasSection = ref<string>('')

/**
 * Task 4.1 / ADR-FMC-04：加载指定附注章节的用户编辑集公式（list_note_formulas）。
 *
 * 弹窗附注节点此前只读模板预设（notePresetFormulas）、看不到用户在附注页保存的公式。
 * 此处补齐：有 projectId/year/sectionId 时调 `GET list_note_formulas`，把用户集并入显示。
 * 缺上下文（章级节点 / 无 sectionId）时清空用户集，不串到别的章节。
 *
 * 附注页带章节打开时会调两次：applyNoteScopeTarget 预取（不 await）+ 定位到章节叶子后
 * onTreeNodeClick 再调一次，第一发还在飞 ⇒ 同一项目 + 章节只发一次（见 createKeyedSingleFlight）。
 */
const noteUserFormulasFlight = createKeyedSingleFlight()
/** force：附注公式弹窗保存后重取（不用「已加载过本章节」的缓存） */
function loadNoteUserFormulas(sectionId: string, force = false): Promise<void> {
  const sid = (sectionId || '').trim()
  return noteUserFormulasFlight(`${currentProjectCacheKey.value}|${sid}|${force ? 'f' : ''}`,
    () => fetchNoteUserFormulas(sid, force))
}

async function fetchNoteUserFormulas(sid: string, force = false): Promise<void> {
  if (!props.projectId || !props.year || !sid) {
    noteUserFormulas.value = []
    noteUserFormulasSection.value = ''
    return
  }
  if (!force && noteUserFormulasSection.value === sid && noteUserFormulas.value.length) return
  try {
    const data = await api.get<{ formulas?: NoteUserFormula[] }>(
      P_nf.list(props.projectId, Number(props.year), sid),
      { validateStatus: (s: number) => s < 600 },
    )
    noteUserFormulas.value = Array.isArray(data?.formulas) ? data.formulas : []
    noteUserFormulasSection.value = sid
  } catch {
    // 用户集加载失败不阻断：保持预设行可见
    noteUserFormulas.value = []
    noteUserFormulasSection.value = ''
  }
}

// ── 附注章节公式的编辑 / 保存（spec formula-governance-coverage-closure R4）：附注行不是报表配置行，
//    保存走附注章节公式集接口（整套 + 载入令牌），交给 NoteFormulaDialog；原先编辑后发 report-config 必失败。 ──
const showNoteFormulaDialog = ref(false)
type NoteEditTarget = { note_section: string; section_title: string; content_type: string }
/** 当前树节点对应的附注章节（章级节点 / 附注未生成的静态树没有章节编号 ⇒ null） */
const noteEditTarget = computed<NoteEditTarget | null>(() => {
  if (!isNoteDomainNodeKey(selectedNodeKey.value)) return null
  const { sectionId, sectionTitle } = resolveNoteSectionRef(selectedNodeKey.value)
  return sectionId ? { note_section: sectionId, section_title: sectionTitle, content_type: '' } : null
})
/** 弹窗实际编辑的章节 */
const noteDialogTarget = ref<NoteEditTarget | null>(null)
/** 本项目附注树里的章节（预设行的章节号来自模板，国企 / 上市编号不同，不一定是本项目的章节） */
function projectNoteSection(code: string): NoteEditTarget | null {
  for (const chapter of noteTreeChildren.value) {
    for (const child of (chapter.children || [])) {
      if (code && child._sectionId === code) return { note_section: code, section_title: child._sectionTitle || child.label, content_type: '' }
    }
  }
  return null
}
/** 选中了具体章节就编辑它；在附注根节点 / 章级节点从某行进入时，用该行所属章节（须是本项目附注里的章节） */
function openNoteFormulaEditor(row?: any) {
  if (!guardFormulaMutation()) return
  if (!props.projectId || !props.year) { ElMessage.warning('缺少项目信息'); return }
  const target = noteEditTarget.value || (row ? projectNoteSection(String(row.row_code || '')) : null)
  if (!target) {
    ElMessage.warning(row?.row_code
      ? `该公式所属章节「${row.row_code}」在本项目附注里找不到，请先在左侧选择具体的附注章节`
      : '请先在左侧选择具体的附注章节（章级节点或附注尚未生成时不能编辑章节公式）')
    return
  }
  noteDialogTarget.value = target
  showNoteFormulaDialog.value = true
}
async function onNoteFormulasSaved() {
  const sid = noteDialogTarget.value?.note_section
  // 右栏只并入「当前选中章节」的用户集：弹窗编辑的正是它才重取（从附注根节点某行进入时右栏列的是预设全集）
  if (sid && sid === noteEditTarget.value?.note_section) await loadNoteUserFormulas(sid, true)
  emit('saved')
}

// ── 底稿(wp)节点公式：从 GET /api/workpapers/{wp_id}/formulas 加载（含 wp_formula 网格公式、
//    专属组件取数公式 surfaced、D-cycle 四表提取 extraction）。此前底稿节点无加载分支恒空。 ──
const wpFormulaRows = ref<any[]>([])

// ── tb_detail composable（拆出 useTbDetailFormulas.ts，原 ~52 行） ──
const tbDetail = useTbDetailFormulas({
  projectId: computed(() => props.projectId || ''),
  year: computed(() => props.year),
  rows: computed(() => props.rows),
  addrStore, api, reportConfigFormula, guardFormulaMutation, showFormulaError,
  askApplyScope: (d: string, s: string[]) => { settingsToolbarRef.value?.askApplyScope(d, s) },
})
const tbDetailOverrides = tbDetail.overrides
const tbDetailAdded = tbDetail.added
const tbDetailLoaded = tbDetail.loaded
const tbDetailFallbackAccounts = tbDetail.fallbackAccounts
const loadTbDetailFormulas = tbDetail.load
const persistTbDetailFormulas = tbDetail.persist
const wpFormulaLoading = ref(false)
const wpFormulaError = ref('')
/** 「调用页给了具体 sheet 但坐标目录里定位不到」的显式告警（≠ 加载失败，≠ 全册视图）。 */
const wpSheetLocateMiss = ref('')
let wpRequest = 0
let dialogSession = 0
const formulaSubject = () => JSON.stringify([props.wpId, props.projectId, props.year])
const selectedWpCode = ref('')
/** 后端公式推送接入清单；请求失败保持空集，页签 fail-closed。 */
const pushWpCodes = ref<string[]>([])
let pushBindingsRequest = 0

async function loadPushBindings(): Promise<void> {
  const request = ++pushBindingsRequest
  pushWpCodes.value = []
  if (!props.projectId) return
  try {
    const data: any = await api.get(formulaPush.bindings(props.projectId), {
      _silent: true,
      validateStatus: (s: number) => s < 600,
    } as any)
    if (request !== pushBindingsRequest || !visible.value) return
    const codes = Array.isArray(data?.supported_wp_codes)
      ? data.supported_wp_codes
      : Array.isArray(data?.bindings) ? data.bindings.map((item: any) => item?.wp_code) : []
    pushWpCodes.value = codes
      .filter((code: unknown): code is string => typeof code === 'string' && !!code.trim())
      .map((code: string) => code.trim().toUpperCase())
  } catch {
    if (request === pushBindingsRequest) pushWpCodes.value = []
  }
}

const pushWpCode = computed(() => {
  // normalizeWpCode 产出小写形态（e1-1），推送 binding 按大写主编码登记
  const code = normalizeWpCode(selectedWpCode.value || props.wpCode || '').split('-')[0].toUpperCase()
  return pushWpCodes.value.includes(code) ? code : ''
})
/** 推送页空状态区分「还没选底稿」与「选了但未接入」 */
const pushWpSelected = computed(() => !!(selectedWpCode.value || props.wpCode))

// formula-management-ux-improvements B3：不需推送循环的具体原因
const _PUSH_NOT_NEEDED_REASONS: Record<string, string> = {
  A: '报表/调整类底稿不涉及数值回写试算表',
  B: '控制了解/计划类底稿，审计程序不产出数值',
  C: '控制测试底稿只记录测试结论，不涉及科目金额',
  S: '专项底稿按项目自定义，不走统一推送通道',
}
const pushNotNeededReason = computed(() => {
  const code = normalizeWpCode(selectedWpCode.value || props.wpCode || '').split('-')[0].toUpperCase()
  const letter = code.charAt(0)
  return _PUSH_NOT_NEEDED_REASONS[letter] || ''
})

const selectedWpSheetCode = ref('')

function normalizeWpCode(value: string): string {
  return (value || '').trim().toLowerCase().replace(/—/g, '-').replace(/_/g, '-')
}

function normalizeWpSheetCode(sheetName: string, _wpCode: string): string {
  return normalizeWpCode(sheetName)
}

// 右栏「当前页公式」sheet 归属匹配：结构化精确等值 + fail-closed（Task 1.2 / ADR-FMC-01）。
// 旧 matchSheetCode 的 `a.includes(b) || b.includes(a)` 子串匹配致 E1-1 串入 E1-10/14/15、
// D2-1 串入 D2-10/12 —— 已删除，替换为 sheetIdentityMatch.ts 的结构化精确等值。

function matchesWpExtractionSheet(row: any, sheetCode: string, _wpCode: string): boolean {
  if (!sheetCode) return true
  // 优先用结构身份（stable_sheet_key / sheet_codes / sheet_name）做精确等值匹配。
  if (row?.stable_sheet_key || (Array.isArray(row?.sheet_codes) && row.sheet_codes.length) || row?.sheet_name) {
    return matchRowToSelectedSheet(row, sheetCode)
  }
  // 兼容部分 D 循环 extractor 只给 anchor（如 D6-1-tb-amount）而无 sheet_name：
  // 结构化前缀归属（anchor === code 或 anchor 以 `code-` 开头），用边界锚定避免
  // `D6-10-...` 被 `D6-1` 子串串页（禁 includes）。
  const anchor = normalizeWpCode(String(row?.anchor || row?.target_cell || ''))
  const code = normalizeWpCode(sheetCode)
  if (!anchor || !code) return false
  return anchor === code || anchor.startsWith(`${code}-`)
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
    const parent = normalizeWpCode(s.parent_wp_code || '')
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
    ? normalizeWpCode(resolvedSheet.parent_wp_code || wpCode)
    : ''
  const keyOf = (n: any) => String(n?.key || '').toLowerCase()
  const same = (a: string, b: string) => (a || '').trim().toLowerCase() === (b || '').trim().toLowerCase()
  const normalizeCode = (value: string) => (value || '').trim().toLowerCase().replace(/—/g, '-').replace(/_/g, '-')
  const requestedCode = normalizeCode(wpCode)

  // Task 3.2：sheet 解析源独立于左栏显示模式 —— 直接从 ACNR catalog 构建 wp 域树，
  // 不读 treeData（默认模式下 treeData 已是当前页 anchors，不含全局 wp 树）。
  const roots: any[] = acnrSheets.value.length ? buildWpDomainTree(acnrSheets.value) : []
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
        // 结构化精确等值 + fail-closed（Task 1.2 / ADR-FMC-01）：按 stable_sheet_key /
        // sheet_name 结构身份精确归属当前 sheet，禁 includes 子串串页；缺可解析结构身份的行
        // 本页视图下排除（fail-closed，不退回 includes）。
        if (!matchRowToSelectedSheet(it, sheetCode)) continue
      }
      rows.push({
        id: it.id, row_code: it.target_cell || it.sheet_name || '', row_name: it.sheet_name || '',
        formula: it.formula || it.expression || '',
        // Task 1.5 / ADR-FMC-02 改动点③（§1 #2b）：wp_formula item 的契约字段是
        // `category`/`description`（后端 _formula_to_dict 实测），旧代码误读
        // `it.formula_category`/`it.formula_description`（恒 undefined → 落兜底，分类/说明错位）。
        // 经 mapWpItemToRowFields 从契约字段正确映射进内部行键。
        ...mapWpItemToRowFields(it),
        formula_source: '底稿公式(wp_formula)',
        // Task 1.4：保留回源字段，供保存链按 kind 分派到 wpFormula.upsert 组装请求体
        // （PUT /api/workpapers/{wp_id}/formulas 需 sheet_name/target_cell/expression）。
        sheet_name: it.sheet_name || '', target_cell: it.target_cell || '',
        stable_sheet_key: it.stable_sheet_key || null,
        definition_version: it.definition_version ?? null,
      })
    }
    // surfaced 按选中 sheet 过滤：条目带 sheet_codes（归属 sheet 列表）时，仅在选中该 sheet
    // 时显示；无 sheet_codes（工作簿级）恒显示；未选具体 sheet（父节点）显示全部。
    for (const s of (data?.surfaced || [])) {
      const scs = s.sheet_codes
      if (sheetCode) {
        // 条目带 sheet_codes（结构化归属 sheet 列表）时，仅在某编码与选中 sheet 精确等值
        // 时显示（禁 includes，避免 E1-1 串入 E1-10）；无 sheet_codes（工作簿级）恒显示。
        if (Array.isArray(scs) && scs.length && !scs.some((c: string) => sheetCodeEquals(c, sheetCode))) continue
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
    // 「试算平衡表」父节点（无具体报表类型）→ 按资产负债表兜底，与旧行为一致
    nodeKey = 'report_balance_sheet'
  }

  // 报表域 `report_{rt}` 与试算平衡表域 `tb_summary_{rt}` 同源取数（见 reportTypeOfNode）
  const reportType = reportTypeOfNode(nodeKey)
  if (reportType) {
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
  // Task 4.1 / ADR-FMC-04：定位到本页章节前先加载其用户编辑集公式（list_note_formulas）。
  if (sectionId) void loadNoteUserFormulas(sectionId)
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

/** 合并报表入口：按调用页当前六类报表定位，默认资产负债表。 */
async function applyConsolReportTarget() {
  const nodeKey = consolReportNodeOfType(props.initialReportType)
  const item = CONSOL_REPORT_TREE_ITEMS.find((entry) => entry.key === nodeKey)
  selectedNodeKey.value = nodeKey
  selectedPath.value = `合并报表 > ${item?.label || '合并资产负债表'}`
  expandedKeys.value = [...new Set([...expandedKeys.value, 'consol_report'])]
  await nextTick()
  try { fmTreeRef.value?.setCurrentKey(nodeKey) } catch { /* ignore */ }
}

/** 合并附注入口：独立单元格公式面板，章节由 noteSection 传入面板定位。 */
async function applyConsolNoteTarget() {
  // 先加载合并附注树数据
  await loadConsolNoteTree()
  await nextTick()

  const sectionId = (props.noteSection || '').trim()
  if (sectionId && consolNoteTreeChildren.value.length) {
    // 尝试定位到具体章节节点
    const targetKey = `consol_note_${sectionId}`
    consolNoteSelectedSection.value = sectionId

    // 查找父章节 key 以便展开
    let parentChapterKey = ''
    for (const chapter of consolNoteTreeChildren.value) {
      if (chapter.children?.some((c: any) => c.key === targetKey)) {
        parentChapterKey = chapter.key
        break
      }
    }

    selectedNodeKey.value = targetKey
    selectedPath.value = props.noteSectionTitle
      ? `合并附注 > ${props.noteSectionTitle}`
      : `合并附注 > ${sectionId}`
    const keysToExpand = ['consol_note']
    if (parentChapterKey) keysToExpand.push(parentChapterKey)
    expandedKeys.value = [...new Set([...expandedKeys.value, ...keysToExpand])]
    await nextTick()
    try { fmTreeRef.value?.setCurrentKey(targetKey) } catch { /* ignore */ }
  } else {
    // 无具体章节：展开合并附注根节点
    selectedNodeKey.value = 'consol_note'
    consolNoteSelectedSection.value = ''
    selectedPath.value = props.noteSectionTitle ? `合并附注 > ${props.noteSectionTitle}` : '合并附注'
    expandedKeys.value = [...new Set([...expandedKeys.value, 'consol_note'])]
    await nextTick()
    try { fmTreeRef.value?.setCurrentKey('consol_note') } catch { /* ignore */ }
  }
}

// 初始加载当前报表的数据
watch([visible, () => props.wpId, () => props.wpCode, () => props.projectId, () => props.year, () => props.sheetName, () => props.initialReportType], async ([v]) => {
  ++dialogSession
  ++wpRequest
  wpFormulaLoading.value = false
  if (v) {
    void loadPushBindings()
    activeCategory.value = 'all'
    uriSearchQuery.value = ''
    selectedRows.value = []
    editingId.value = null
    wpFormulaRows.value = []
    wpFormulaError.value = ''
    wpSheetLocateMiss.value = ''
    // Task 3.2 / ADR-FMC-05：每次打开回到默认「当前页地址」模式（非全局浏览）。
    leftPanelGlobalBrowse.value = false
    currentSheetAnchors.value = []
    leftPanelWarning.value = ''
    currentPageIdentity.value = null
    // Task 6.2（需求 7.3）：每次打开重置表间审核加载态，以便重新拉取执行结果与
    // 用户落库规则（关闭再打开仍可见已保存的规则）。
    crossCheckLoaded.value = false
    crossCheckExecEmpty.value = false
    // formula-global-settings-sync：报表行是本项目有效定义，每次打开 / 换项目都重取（全局发布、待确认处理后不读旧缓存）
    invalidateEffectiveReport(props.projectId); allRowsMap.value = {}; reportStandardByType.value = {}
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
      // Task 3.2 / ADR-FMC-05：左栏默认加载当前页 anchors（selectedWpSheetCode 已解析为
      // 当前页结构化 sheet_code；缺 identity 时 loadCurrentSheetAnchors 内部 fail-closed）。
      await loadCurrentSheetAnchors()
      await loadWpFormulas(selectedWpCode.value, selectedWpSheetCode.value)
      return
    }
    // 非 wp 入口（报表/附注/tb/合并）为域级浏览上下文：左栏走全局域树（见 treeData），
    // 不属于「缺当前页身份」范畴，故不在此加载当前页 anchors。
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
    // 加载合并附注树（按章节分组）
    loadConsolNoteTree()
    // 加载 ACNR 五域导航树（底稿域动态从 catalog 构建）
    loadAcnrTree()
    // 加载报表类型（项目级动态）
    loadReportTypes()
    // 加载表间审核规则（项目级动态）
    loadCrossCheckItems()
    if (props.scope === 'tb') {
      // 试算表页打开 → 根据调用页当前视图定位：
      //   - 有 initialReportType（用户在试算平衡表的某个报表 tab，如利润表）
      //     → 定位「试算平衡表 > {该报表}」
      //   - 无 initialReportType（用户在科目明细视图）→ 定位「试算平衡表 > 科目明细」
      if (props.initialReportType && REPORT_SUBTYPE_LABELS_FALLBACK[props.initialReportType]) {
        // 🔴 落到「试算平衡表 > {报表}」而非「报表 > {报表}」：调用页是试算平衡表视图
        // （未审/调整/审定列口径），不是报表域的正式报表。两者行次同源但域不同，
        // 定位到报表域会让审计师以为自己在改报表。
        const rt = props.initialReportType
        const nodeKey = `tb_summary_${rt}`
        selectedNodeKey.value = nodeKey
        selectedPath.value = `试算平衡表 > ${REPORT_SUBTYPE_LABELS_FALLBACK[rt]}`
        await loadRowsForNode(nodeKey)
        await nextTick()
        // 展开到叶子：trial_balance → tb_summary → tb_summary_{rt}
        expandedKeys.value = [...new Set([...expandedKeys.value, 'trial_balance', 'tb_summary'])]
        await nextTick()
        try { fmTreeRef.value?.setCurrentKey(nodeKey) } catch { /* ignore */ }
      } else {
        // props.rows 是试算表行（standard_account_code/account_name），不是报表行次（无 row_code），
        // 故不能走下方报表启发式（否则被误判为 report_balance_sheet 而公式列全空、树也定位不到）。
        selectedNodeKey.value = 'tb_detail'
        selectedPath.value = '试算平衡表 > 科目明细'
        await loadTbDetailFormulas()
        await nextTick()
        expandedKeys.value = [...new Set([...expandedKeys.value, 'trial_balance'])]
        await nextTick()
        try { fmTreeRef.value?.setCurrentKey('tb_detail') } catch { /* ignore */ }
      }
    } else if (props.scope === 'consol_worksheet') {
      // 合并工作底稿：项目级入口，按当前 worksheet 定位（无 wpId 不代表无当前页）
      await applyConsolWorksheetTarget()
    } else if (props.scope === 'consol_report') {
      await applyConsolReportTarget()
    } else if (props.scope === 'consol_note') {
      await applyConsolNoteTarget()
    } else if (props.scope === 'note') {
      // 单体附注页打开 → 定位到调用页当前章节节点。
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
    // 外部入口指定目标节点（如底稿页跳转 wp_e1_1）→ 自动展开+选中+加载公式；
    // 没有目标且停在报表节点时补加载当前报表（打开时已清报表行缓存）
    if (!(await applyTargetNode()) && activeReportType.value && !allRowsMap.value[activeReportType.value]) await loadRowsForNode(selectedNodeKey.value)
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

  // 表间审核分组节点（报表 ↔ 附注 / 合并 ↔ 报表 …）本身挂着规则集与内置勾稽问题清单，有子节点也要能选中
  // （原先只认叶子 ⇒ 有内置勾稽结论时的「报表 ↔ 附注」、恒有三个子项的「合并 ↔ 报表」，规则永远点不到）
  const isCrossCheckGroup = (Object.values(CROSS_CHECK_NODE_KEYS) as string[]).includes(data.key)
  // 底稿工作簿节点（「E1 货币资金」，有子页、带 _wpCode 无 _sheetCode）：选中整本 —— 公式表列全册公式、
  // 公式推送页按本底稿。原先只认叶子：点工作簿只高亮不切换，推送页还提示「本底稿尚未接入自动推送」（R5 走查）
  const isWorkbookNode = data.key.startsWith('wp_') && !!data._wpCode && !data._sheetCode
  if (!data.children || data.children.length === 0 || isCrossCheckGroup || isWorkbookNode) {
    selectedNodeKey.value = data.key
    // 构建路径
    if (data.key.startsWith('tb_')) {
      selectedPath.value = `试算平衡表 > ${data.label}`
    } else if (data.key.startsWith('report_')) {
      selectedPath.value = `报表 > ${data.label}`
    } else if (consolReportTypeOfNode(data.key)) {
      selectedPath.value = `合并报表 > ${data.label}`
    } else if (data.key.startsWith('consol_note_') && data._sectionId) {
      // 合并附注科目子节点：设置选中的 section_id，面板通过 prop 响应切换
      consolNoteSelectedSection.value = data._sectionId
      selectedPath.value = `合并附注 > ${data._sectionTitle || data.label}`
    } else if (data.key.startsWith('note_')) {
      selectedPath.value = `附注 > ${data._sectionTitle || data.label}`
      if (!notePresetFormulas.value.length) {
        onImportPresetFormulas()
      }
      // Task 4.1 / ADR-FMC-04：选中具体附注章节 → 加载其用户编辑集公式（list_note_formulas）。
      loadNoteUserFormulas(data._sectionId || '')
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

/**
 * 附注树节点 → 章节编号 / 标题（动态树优先，降级静态树；树中未命中且落在「本页章节」或附注域根节点时，
 * 用调用页传入的章节上下文）。章级节点（note_chapter_*）不套用调用页章节，否则点章节会错显示成本页章节。
 * 静态树没有章节编号 ⇒ sectionId 为空（附注未生成，不能按章节读写公式）。
 */
function resolveNoteSectionRef(nodeKey: string): { sectionId: string; sectionTitle: string } {
  for (const chapter of noteTreeChildren.value) {
    for (const child of (chapter.children || [])) {
      if (child.key === nodeKey) return { sectionId: child._sectionId || '', sectionTitle: child._sectionTitle || child.label }
    }
  }
  for (const group of staticNoteTree) {
    for (const child of (group.children || [])) {
      if (child.key === nodeKey) return { sectionId: '', sectionTitle: (child as any)._sectionTitle || child.label }
    }
  }
  const propSection = (props.noteSection || '').trim()
  const isPageSectionNode = nodeKey === 'note'
    || (!!propSection && nodeKey === noteSectionToNodeKey(propSection))
  if (isPageSectionNode) {
    return { sectionId: propSection, sectionTitle: (props.noteSectionTitle || '').trim() }
  }
  return { sectionId: '', sectionTitle: '' }
}

// ── 当前显示的行 ──
const currentRows = computed(() => {
  // 试算平衡表节点
  if (selectedNodeKey.value === 'tb_detail') {
    const base = (addrStore.loaded && addrStore.tbAddresses.length > 0)
      ? addrStore.tbAddresses.map((e) => ({ code: e.account_code || '', name: e.label || '', computed: undefined as any }))
      : (props.rows && props.rows.length > 0)
        ? props.rows.map((r: any) => ({ code: r.standard_account_code || '', name: r.account_name || '', computed: r.unadjusted_amount }))
        : tbDetailFallbackAccounts.value.map((r) => ({ code: r.code, name: r.name, computed: undefined as any }))
    return tbDetail.buildRows(base)
  }
  if (selectedNodeKey.value === 'tb_summary') {
    // 试算平衡表：显示 report_config 的行次公式
    return allRowsMap.value['balance_sheet'] || []
  }

  if (activeReportType.value) {
    const rt = activeReportType.value
    return allRowsMap.value[rt] || []
  }
  // 附注节点：显示该章节的预设公式（含用户编辑集，Task 4.1 / ADR-FMC-04）
  if (isNoteDomainNodeKey(selectedNodeKey.value) && (notePresetFormulas.value.length || noteUserFormulas.value.length)) {
    const { sectionId: targetSectionId, sectionTitle: targetTitle } = resolveNoteSectionRef(selectedNodeKey.value)
    // 章节命中 → 只列本章节公式；章级节点/无上下文 → 列全部（规则见 noteScopeTargeting）
    const presetRows = buildNoteFormulaRows(notePresetFormulas.value, {
      sectionId: targetSectionId,
      sectionTitle: targetTitle,
    })
    // Task 4.1 / ADR-FMC-04：并入用户编辑集公式（list_note_formulas），用户集优先/去重。
    // 仅当当前已加载的用户集属于本章节时并入，避免切章时把上一章的用户公式串过来。
    const userForSection =
      noteUserFormulasSection.value && noteUserFormulasSection.value === targetSectionId
        ? noteUserFormulas.value
        : []
    return mergeNoteUserFormulaRows(presetRows, userForSection, {
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

// ── cross_check CRUD + 执行（委托 composable，原 ~311 行） ──
const isCrossCheckMode = cc.isCrossCheckMode
const crossCheckRulesMap = cc.rulesMap
const crossCheckRulesForCurrent = cc.rulesForCurrent
const showCrossRuleDialog = cc.showDialog
const crossRuleDialogTitle = cc.dialogTitle
const crossRuleEditIndex = cc.editIndex
const crossRuleForm = cc.form
const onAddCrossRule = cc.onAdd
const onEditCrossRule = cc.onEdit
const onSaveCrossRule = cc.onSave
const onRemoveCrossRule = cc.onRemove
const crossCheckRunning = cc.running
const onRunCrossCheck = cc.run

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
  // Task 1.4：只读投影（surfaced/Tier B 溯源）不是可配置公式，从健康度分母剔除，
  // 否则「说明元数据恒带 formula」会把健康度虚抬成 100%（伪装）。
  const meaningful = rows.filter(r => _rowNeedsFormula(r) && !isReadonlyProjectionRow(r))
  if (!meaningful.length) return 100
  const withFormula = meaningful.filter(r => r.formula).length
  return Math.round((withFormula / meaningful.length) * 100)
})

const healthDesc = computed(() => {
  const rows = currentRows.value
  const meaningful = rows.filter(r => _rowNeedsFormula(r) && !isReadonlyProjectionRow(r))
  const withFormula = meaningful.filter(r => r.formula).length
  return `${withFormula}/${meaningful.length} 已配置`
})

// ── 智能公式建议（复盘修复 #9）──────────────────────────────────────────────
/** 系统预设中有公式、但当前行无公式的那些行 = 建议列表。
 * _upstream 来自 reportEffectiveRows 的全局/预设定义快照。 */
const showSuggestions = ref(false)
const formulaSuggestions = computed(() => {
  const rows = currentRows.value
  if (!rows.length) return []
  return rows.filter((r: any) =>
    _rowNeedsFormula(r)
    && !isReadonlyProjectionRow(r)
    && !r.formula
    && r._upstream?.formula,  // 上游（全局或预设）中该行有公式
  ).map((r: any) => ({
    row_code: r.row_code,
    row_name: r.row_name || '',
    formula: r._upstream.formula,
    formula_type: r._upstream.formula_category || 'auto_calc',
    id: r.id,
  }))
})

function onApplySuggestion(s: { row_code: string; formula: string; id?: string }) {
  const row = currentRows.value.find((r: any) => r.row_code === s.row_code)
  if (!row) return
  // 打开编辑弹窗，预填建议公式（走统一编辑+保存链路，不直接写入避免绕过校验）
  editingRow.value = row
  editFormula.value = s.formula
  editCategory.value = s.formula_type || 'auto_calc'
  editDescription.value = ''
  showFormulaEdit.value = true
  ElMessage.info(`已预填建议公式到编辑弹窗，确认后保存`)
}

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

/**
 * 判断行是否由系统公式推送独占（policy=system/derived）。
 * 独占行不允许用户在公式管理面板中编辑自定义公式。
 * spec: formula-push-user-custom-cross-module T6
 */
function _isRowOwnedByPush(row: any): boolean {
  const wpCode = pushWpCode.value || (props.wpCode || '').split('-')[0].toUpperCase()
  if (!wpCode) return false
  const itemId = row.row_code || row.cell_key || ''
  if (!itemId) return false
  return isOwnedKey(wpCode, itemId)
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

// formula-management-ux-improvements A4/A5：参数选择器的数据源
const paramPickerTbItems = computed(() => {
  const store = addrStore
  const addrs = store.tbAddresses || []
  return addrs.map((a: any) => ({ code: a.code || a.account_code || '', name: a.name || a.account_name || a.label || '' }))
})
const paramPickerWpItems = computed(() => {
  // 从当前行列表提取已知底稿
  const seen = new Set<string>()
  const items: Array<{ wpCode: string; label: string }> = []
  for (const r of currentRows.value) {
    const wc = r.wp_code || props.wpCode || ''
    if (wc && !seen.has(wc)) {
      seen.add(wc)
      items.push({ wpCode: wc, label: wc })
    }
  }
  return items
})
const paramPickerNoteItems = computed(() => {
  // 从附注树提取章节
  const items: Array<{ section: string; title: string }> = []
  function walk(nodes: any[]) {
    for (const n of nodes) {
      if (n.section || n.note_section) {
        items.push({ section: n.section || n.note_section, title: n.label || n.title || '' })
      }
      if (n.children?.length) walk(n.children)
    }
  }
  walk(noteTreeChildren.value)
  return items
})
const paramPickerRowItems = computed(() =>
  currentRows.value
    .filter((r: any) => r.row_code)
    .map((r: any) => ({ rowCode: r.row_code, rowName: r.row_name || '' })),
)
// formula-input-param-completion Task 4：给 FormulaInput 传入报表行次和底稿编码
const formulaInputReportRows = computed(() =>
  currentRows.value
    .filter((r: any) => r.row_code)
    .map((r: any) => ({ row_code: r.row_code as string, row_name: (r.row_name || '') as string })),
)
const formulaInputWpCodes = computed(() => {
  const seen = new Set<string>()
  for (const r of currentRows.value) {
    const wc = (r as any).wp_code || props.wpCode || ''
    if (wc && !seen.has(wc)) seen.add(wc)
  }
  return [...seen]
})

function onParamPickerSelect(formulaText: string) {
  editFormula.value += formulaText
}

// 公式编辑弹窗
const showFormulaEdit = ref(false)
const editingRow = ref<any>(null)

function startEdit(row: any) {
  // Task 1.4 / ADR-FMC-02：只读投影（surfaced/Tier B）不可进入编辑态（纵深防御：
  // 即便模板上有入口被误绑，这里也拦截）。
  if (isReadonlyProjectionRow(row)) {
    ElMessage.info('取数/溯源说明为只读投影，不可编辑')
    return
  }
  if (resolveSaveDispatch(row) === 'note') { openNoteFormulaEditor(row); return }
  if (!guardFormulaMutation()) return
  editingRow.value = row
  showFormulaEdit.value = true
}

async function onFormulaEditSave(data: { formula: string; category: string; description: string; target_cell?: string }) {
  const row = editingRow.value
  const gate = evaluateFormulaMutation(row?.definition_version != null || row?._isNew === true)
  if (!row || !gate.allow) {
    if (!gate.allow) ElMessage.warning(gate.detail)
    return
  }

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
    Object.assign(row, {
      formula: data.formula,
      formula_category: data.category,
      formula_description: data.description,
    })
    if (!await persistTbDetailFormulas()) return
    showFormulaEdit.value = false
    ElMessage.success('公式已保存')
    emit('saved')
    await propagateFormulaStale()  // Task 6.3（需求 10.3）：单行保存触发统一 stale 传播
    return
  }

  if (row._isNew) {
    // 新增公式行——添加到当前列表并尝试保存到后端
    if (data.formula) {
      const rows = currentRows.value
      Object.assign(row, {
        formula: data.formula,
        formula_category: data.category,
        formula_description: data.description,
      })
      row.row_number = rows.length + 1
      rows.push(row)

      if (activeReportType.value) {
        const reportType = activeReportType.value
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
          if (saved?.id) Object.assign(row, { id: saved.id, formula_version: saved.formula_version })
          row._isNew = false
          showFormulaEdit.value = false
          ElMessage.success('新公式已保存')
          emit('saved')
          await propagateFormulaStale()  // Task 6.3（需求 10.3）：单行保存触发统一 stale 传播
        } catch {
          ElMessage.warning('公式已添加到列表，保存到后端失败')
        }
      }
    }
    return
  }

  // 已有行——先按 kind 分派目标端点（Task 1.4 / ADR-FMC-02 / 改动点②）：
  //   wp         → PUT /api/workpapers/{wp_id}/formulas（wpFormula.upsert）
  //   surfaced   → 拒绝（只读投影，禁保存）
  //   extraction → 拒绝（只读溯源，禁保存）
  //   report     → PUT report-config detail（仅报表模板行）
  // 旧逻辑「任何有 id 的行都发 report-config detail」无 kind 校验，会把底稿公式误写进
  // 全局报表模板（§1 #2）。
  if (!row.id) return

  const dispatch = resolveSaveDispatch(row)

  if (dispatch === 'reject') {
    ElMessage.info('取数/溯源说明为只读投影，不可保存')
    return
  }
  if (dispatch === 'note') {  // 附注章节公式集只能整套保存（附注公式弹窗），不能发 report-config
    showFormulaEdit.value = false
    openNoteFormulaEditor(row)
    return
  }

  if (dispatch === 'wp') {
    const targetLocation = gate.location
    if (!targetLocation) {
      ElMessage.warning('缺少固定的底稿位置，无法保存底稿公式')
      return
    }
    try {
      const saved: any = await api.put(wpFormula.upsert(targetLocation.wpId), {
        sheet_name: row.sheet_name || targetLocation.display.sheetName || selectedWpSheetCode.value || '',
        target_cell: data.target_cell || row.target_cell || row.row_code || '',
        expression: data.formula || '',
        year: targetLocation.fiscalYear,
        template_type: fmTemplateType.value,
        category: data.category,
        description: data.description,
        expected_version: row.definition_version ?? undefined,
      })
      // 版本在回执的 saved 下（原读顶层恒取不到 ⇒ 同一行第二次保存必 409）
      const savedVersion = savedDefinitionVersion(saved)
      if (savedVersion != null) row.definition_version = savedVersion
      Object.assign(row, {
        formula: data.formula,
        formula_category: data.category,
        formula_description: data.description,
        target_cell: data.target_cell || row.target_cell,
      })
      showFormulaEdit.value = false
      // R6.3：取不到数时格子留空，提示写明原因（不能只说「公式已保存」）
      const notice = wpFormulaSaveNotice(saved, data.target_cell || row.target_cell || '')
      ElMessage[notice.level]({ message: notice.text, duration: notice.level === 'warning' ? 8000 : 3000 })
      emit('saved')
      await propagateFormulaStale(targetLocation)
    } catch (e) {
      handleApiError(e, '保存失败')
    }
    return
  }

  // dispatch === 'report'：项目上下文写本项目适配（有效定义行），否则写报表配置行（全局行 = 直接发布，带版本）
  await saveReportRowDraft(row, { formula: data.formula || null, formula_category: data.category, formula_description: data.description },
    () => { showFormulaEdit.value = false })
}

async function saveEdit(row: any) {
  // 兼容行内编辑（保留）
  if (!row.id || !guardFormulaMutation(row.definition_version != null)) return
  await saveReportRowDraft(row, { formula: editFormula.value || null, formula_category: editCategory.value, formula_description: editDescription.value },
    () => { editingId.value = null })
}

/** 单行保存：先存草稿副本，成功才回写到行（失败不留「界面已改、库里没有」）；本项目保存后问应用范围（R7.1）。 */
async function saveReportRowDraft(row: any, fields: Record<string, any>, onDone: () => void) {
  try {
    const draft = { ...row, ...fields }
    const { projectSlotKeys } = await saveReportRows(props.projectId, [draft])
    Object.assign(row, draft)
    onDone()
    ElMessage.success('公式已保存')
    emit('saved')
    await propagateFormulaStale()  // Task 6.3（需求 10.3）：单行保存触发统一 stale 传播
    askApplyScope(projectSlotKeys)
  } catch (e) {
    showFormulaError(e, '保存失败')
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
  if (!guardFormulaMutation()) return
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

    // 计算结果只在本弹窗展示；报表金额由报表生成 / 合并推送写入 financial_report
    // （原「回写报表配置」写的是报表配置上不存在的金额列，从未落库；该后端接口已删除）

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
  const currentRows = allRowsMap.value[reportTypeOfNode(nodeKey) || nodeKey] || []

  // 如果当前节点有数据，导出该节点的公式
  // 如果没有数据，传空数组——exportFormulaTemplate 内部会生成通用模板骨架
  const { exportFormulaTemplate } = await import('./exportFormulaTemplate')
  await exportFormulaTemplate(currentRows, nodeKey || '通用模板', selectedPath.value || '公式管理中心')
}

async function onImportPresetFormulas() {
  loadingData.value = true

  // 报表类：从 report_config 加载
  if (activeReportType.value) {
    const reportType = activeReportType.value
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

// ── 报表行全量加载（看板等全览场景用） ──

/**
 * 确保 6 类报表的 report_config 行都已加载。
 *
 * 🔴 全览前必须先补齐：`allRowsMap` 只装"用户点过的报表"，直接统计会只含已看过的部分（用户无从察觉）。
 */
async function ensureAllReportRowsLoaded(): Promise<void> {
  for (const rt of REPORT_TYPE_KEYS) {
    if (allRowsMap.value[rt]?.length) continue
    allRowsMap.value[rt] = await fetchReportRows(rt)
  }
}

// ── 全局设置 / 本项目适配 / 公式模板（spec formula-global-settings-sync）──
// 旧「保存为模板 / 引用模板 / 撤销引用」走共享配置 formula_config（只回填报表段、引用会写全局行）已下线（R13.10 / R14.2），
// 改为顶栏 FormulaSettingsToolbar：模板 = 订阅一层，只写本项目层，模板更新经同一同步内核与待确认弹窗。

const settingsToolbarRef = ref<InstanceType<typeof FormulaSettingsToolbar> | null>(null)
/** 当前用户是否 admin（本项目有效定义接口给出）：应用范围里显示「设为全局」还是「提交为全局候选」 */
const canEditGlobal = ref(false)
/** 本项目报表域的作用范围（有效定义接口给出）：跳转全局设置、保存模板时默认带上 */
const projectReportScope = ref('')
/** 当前节点对应的公式域 */
const settingsDomain = computed(() => {
  const k = selectedNodeKey.value
  if (k === 'tb_detail') return 'tb_detail'
  if (k.startsWith('cross_')) return 'cross_check'
  return isNoteDomainNodeKey(k) ? 'note' : 'report'
})
const settingsScope = computed(() => projectReportScope.value || `${fmTemplateType.value}_standalone`)

/** 订阅 / 退订 / 应用到其他 / 恢复全局 / 导入公式包之后：本项目有效定义变了，丢掉报表行缓存重取当前节点 */
async function onFormulaSettingsChanged(domain?: string) {
  invalidateEffectiveReport(props.projectId)
  allRowsMap.value = {}
  reportStandardByType.value = {}
  await loadRowsForNode(selectedNodeKey.value)
  // 表间审核规则不在报表行缓存里，单独重取
  if (domain === 'cross_check') await loadCrossCheckUserRules()
  emit('saved')
}

/** 本项目保存成功后问应用范围：仅本项目（默认）/ 设为全局 / 应用到指定项目（R7.1） */
function askApplyScope(slotKeys: string[]) {
  if (slotKeys.length) settingsToolbarRef.value?.askApplyScope('report', slotKeys)
}

/** 恢复为全局（R6.2）：删除本项目适配；来自订阅模板的回到模板定义 */
async function onRestoreGlobal(row: any) {
  if (!guardFormulaMutation() || !props.projectId) return
  try {
    await confirmDangerous({
      title: '恢复为全局', confirmText: '恢复',
      message: `「${row.row_code} ${row.row_name || ''}」将去掉本项目的改动，回到全局（或订阅模板）的定义。`,
    })
  } catch { return }
  try {
    await restoreReportRows(props.projectId, [row])
    ElMessage.success('已恢复为全局定义')
    await onFormulaSettingsChanged()
    await propagateFormulaStale()
  } catch (e) {
    showFormulaError(e, '恢复为全局失败')
  }
}

function onAddFormulaRow() {
  if (isNoteDomainNodeKey(selectedNodeKey.value)) { openNoteFormulaEditor(); return }  // 附注公式在附注公式弹窗里新增
  if (!guardFormulaMutation()) return
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
  const gate = evaluateFormulaMutation()
  if (!gate.allow) {
    ElMessage.warning(gate.detail)
    return
  }
  // 附注章节公式只能整套保存：交给附注公式弹窗（原先这里对附注行一条不存还报「已保存 0 个」）
  if (isNoteDomainNodeKey(selectedNodeKey.value)) { openNoteFormulaEditor(); return }
  // 改过的行也算（含「清除公式」后为空的行，此前被 `r.formula` 过滤掉、清除从未落库）
  const rows = currentRows.value.filter(r => r.formula || rowChanged(r))
  if (!rows.length) {
    ElMessage.warning('无公式可保存')
    return
  }
  applying.value = true
  let saved = 0
  let skippedReadonly = 0
  const reportBatch: any[] = []
  const wpEvalFailures: Array<{ cell: string; warnings: string[] }> = []
  try {
    for (const row of rows) {
      // Task 1.4 / ADR-FMC-02 触类旁通：批量「保存全部」同样先按 kind 分派，
      // 否则在 wp 节点点保存会把底稿行 + surfaced 只读投影全批量发到 report-config
      // detail（与 onFormulaEditSave 旧 bug 同源）。
      const dispatch = resolveSaveDispatch(row)
      if (dispatch === 'reject') { skippedReadonly++; continue }

      if (row._isNew && row.formula) {
        // 新增（仅报表节点有「新增行」入口，走 report-config list POST）
        const reportType = activeReportType.value
        if (dispatch !== 'report') continue
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
      } else if (row.id && dispatch === 'wp') {
        // 底稿行 → wpFormula.upsert；URL/年度/sheet 必须来自 session pinnedLocation。
        const targetLocation = gate.location
        if (!targetLocation) continue
        const savedRow: any = await api.put(wpFormula.upsert(targetLocation.wpId), {
          sheet_name: row.sheet_name || targetLocation.display.sheetName || selectedWpSheetCode.value || '',
          target_cell: row.target_cell || row.row_code || '',
          expression: row.formula || '',
          year: targetLocation.fiscalYear,
          template_type: fmTemplateType.value,
          category: row.formula_category,
          description: row.formula_description,
          expected_version: row.definition_version ?? undefined,
        }, { validateStatus: (s: number) => s < 600 })
        const savedRowVersion = savedDefinitionVersion(savedRow)
        if (savedRowVersion != null) row.definition_version = savedRowVersion
        const rowNotice = wpFormulaSaveNotice(savedRow)
        if (rowNotice.warnings.length) {
          wpEvalFailures.push({ cell: row.target_cell || row.row_code || '', warnings: rowNotice.warnings })
        }
        saved++
      } else if (row.id && dispatch === 'report' && rowChanged(row)) {
        // 报表行只收改过的，循环后一次保存（项目上下文 = 一次写本项目适配，原子）
        reportBatch.push(row)
      }
    }
    const { projectSlotKeys } = reportBatch.length ? await saveReportRows(props.projectId, reportBatch) : { projectSlotKeys: [] }
    saved += reportBatch.length
    askApplyScope(projectSlotKeys)
    // R6.3：底稿公式算不出值（格子已留空）时列出单元格与原因
    const batchNotice = wpFormulaBatchNotice(saved, wpEvalFailures,
      skippedReadonly ? `（跳过 ${skippedReadonly} 条只读投影）` : '')
    ElMessage[batchNotice.level]({ message: batchNotice.text, duration: batchNotice.level === 'warning' ? 8000 : 3000 })
    emit('saved')

    // 保存全部与单行保存共用传播；工作底稿域继续使用固定位置的项目/年度。
    await propagateFormulaStale(gate.location)
  } catch (e) {
    showFormulaError(e, '保存失败')
  } finally {
    applying.value = false
  }
}

/**
 * Task 6.3（需求 10.2 / 10.3）：统一 stale 传播。
 *
 * 「保存全部」(`onSaveAllFormulas`) 与单行保存 (`onFormulaEditSave`) 都调本函数，使单行保存
 * 触发**与保存全部相同**的传播（需求 10.3）。年份一律取 `props.year`（项目年），经
 * `resolveSaveYear` 口径——缺可解析年份时跳过传播，**不** fallback 到系统当前年（需求 10.2）。
 */
async function propagateFormulaStale(location?: CanonicalWorkpaperLocation) {
  const projectId = location?.projectId || props.projectId
  const year = resolveSaveYear(location?.fiscalYear ?? props.year)
  if (!projectId || year == null) return  // 缺项目/年份则跳过（不以系统年顶替）
  try {
    await api.post(linkageBus.impact, {
      source_uri: `FORMULA:${selectedNodeKey.value}::config_changed`,
      project_id: projectId,
      year,
    }, { validateStatus: (s: number) => s < 600 })
  } catch {
    // stale propagation failure is non-blocking
  }
}

// ── 公式看板 ──
const showFormulaDashboard = ref(false)
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
  if (!activeReportType.value) return ''
  const std = reportStandardByType.value[activeReportType.value]
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
  // formula-global-settings-sync R1.2：项目上下文读本项目有效定义（全局 → 订阅模板 / 本项目适配，逐行标层级）；
  // 「有项目行就只显示项目行」的旧口径会把只适配了几行的项目其余全局行全部藏掉。接口不可用才回退旧口径。
  if (props.projectId) {
    const eff = await fetchEffectiveReportRows(props.projectId, reportType)
    if (eff) {
      reportStandardByType.value[reportType] = `project:${props.projectId}`
      canEditGlobal.value = eff.canEditGlobal
      projectReportScope.value = eff.scope
      return eff.rows
    }
  }
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
      return markLoaded(rows)
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

/** 覆盖情况文案：空态时必须说清哪一类没取到，而不是只给 No Data。 */
const dashboardCoverageText = computed(() =>
  dashboardCoverage.value.map((c) => `${c.label} ${c.count} 条`).join(' · ')
  || '尚未加载',
)


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
  if (!guardFormulaMutation()) return
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
  if (!guardFormulaMutation()) return
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
/* Task 3.2：左栏模式切换按钮（全局浏览 / 当前页）不随标题大写变形。 */
.gt-fm-left-mode-btn {
  text-transform: none;
  letter-spacing: normal;
  font-weight: 500;
}
/* Task 3.2：缺当前页身份 fail-closed 告警（不退全局树）。 */
.gt-fm-left-warning {
  margin: 0 8px 6px;
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
/* 智能公式建议条 */
.gt-fm-suggest-bar {
  margin-bottom: 8px;
  padding: 8px 10px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 6px;
}
.gt-fm-suggest-header {
  display: flex;
  align-items: center;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-primary, #409eff);
}
.gt-fm-suggest-list {
  margin-top: 6px;
}
.gt-fm-suggest-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  margin-bottom: 3px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
  font-size: 11px;
}
.gt-fm-suggest-code {
  font-weight: 600;
  min-width: 70px;
  color: var(--gt-color-text-primary);
}
.gt-fm-suggest-name {
  min-width: 80px;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gt-color-text-secondary);
}
.gt-fm-suggest-formula {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gt-color-text-regular);
  font-family: 'Consolas', monospace;
  font-size: 11px;
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
