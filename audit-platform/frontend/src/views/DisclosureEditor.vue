<template>
  <div class="gt-disclosure-editor gt-fade-in" :class="{ 'gt-fullscreen': deFullscreen }">
    <!-- 横幅 -->
    <GtPageHeader title="附注编辑" :show-sync-status="true" @back="router.push('/projects')">
      <GtInfoBar
        :show-unit="true"
        :show-year="true"
        :show-template="true"
        :unit-value="selectedProjectId"
        :year-value="selectedYear"
        :template-value="templateType"
        :template-options="deTemplateOptions"
        :badges="[
          { value: noteList.length + ' 个章节' },
          { label: '金额单位', value: displayPrefs.unitSuffix },
        ]"
        @unit-change="onProjectChange"
        @year-change="(v: number) => { selectedYear = v; onYearChange() }"
        @template-change="handleTemplateChange"
      />
      <template #actions>
        <GtToolbar
          :show-copy="true"
          :show-fullscreen="true"
          :is-fullscreen="deFullscreen"
          :show-export="true"
          export-label="导出Word"
          :show-import="true"
          :show-formula="true"
          @copy="copyNoteTable"
          @fullscreen="toggleDeFullscreen()"
          @export="onExportWord"
          @import="showNoteImport = true"
          @formula="showNoteFormulaManager = true"
        >
          <template #left>
            <NoteTemplateSwitch
              v-if="!isEqcrRole"
              :project-id="projectId"
              :year="year"
              :template-type="templateType"
              @update:template-type="handleTemplateChange"
              @switched="fetchTree()"
            />
            <el-button v-if="!isEqcrRole" size="small" @click="onRefreshFromWP" :loading="refreshLoading">🔄 从底稿刷新</el-button>
            <el-button v-if="!isEqcrRole" size="small" @click="onGenerate" :loading="genLoading">📝 生成附注</el-button>
            <el-button v-if="!isEqcrRole" size="small" @click="onValidate" :loading="validateLoading">✅ 执行校验</el-button>
            <el-button v-if="isEqcrRole" size="small" type="info">📋 导出只读副本</el-button>
          </template>
          <template #right-extra>
            <SharedTemplatePicker
              config-type="note_template"
              :project-id="projectId"
              :get-config-data="getNoteTemplateConfigData"
              @applied="onNoteTemplateApplied"
            />
            <!-- Sprint 3 Task 3.1: 新增章节 -->
            <el-button
              v-if="!isEqcrRole"
              size="small"
              data-test="de-add-section"
              @click="openAddSectionDialog"
            >➕ 新增章节</el-button>
            <el-button size="small" @click="openStructureEditor">📐 表样编辑</el-button>
            <el-button size="small" @click="showPrintPreview = true">🖨️ 打印预览</el-button>
            <el-button size="small" @click="showOfflineExport = true">📦 导出离线包</el-button>
            <el-button size="small" @click="showOfflineImport = true">📥 一键导入</el-button>
            <el-button size="small" @click="showAiPanel = true">🤖 AI建议</el-button>
            <el-button size="small" @click="showDocAiChat = true">💬 AI 对话</el-button>
            <el-button size="small" @click="showVersionTree = true">🗂️ 版本</el-button>
            <el-button size="small" @click="showGroupBaseline = true">📦 集团基线</el-button>
            <el-button size="small" @click="showParagraphVars = true">✏️ 段落变量</el-button>
            <el-button size="small" @click="showPriorYear = true">📅 上年对比</el-button>
            <el-button-group size="small" style="margin-left: 4px">
              <el-button :type="numbering.state.value.scope === 'standalone' ? 'primary' : ''" @click="onScopeChange('standalone')">单体</el-button>
              <el-button :type="numbering.state.value.scope === 'consolidated' ? 'primary' : ''" @click="onScopeChange('consolidated')">合并</el-button>
            </el-button-group>
            <el-button size="small" @click="showNoteMappingDialog = true">🔄 转换规则</el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- 归档横幅 -->
    <ArchivedBanner />
    <ConsolLockedBanner />

    <!-- AI 内容 pending 顶部 banner（spec global-refinement-v3 Task 6.4） -->
    <AiContentPendingBanner :project-id="projectId" />

    <!-- 跨模块冲突 banner（spec global-refinement-v3 Task 7.5） -->
    <ConflictBanner :project-id="projectId" @view="conflictPanelVisible = true" />
    <ConflictResolutionPanel
      v-model="conflictPanelVisible"
      :project-id="projectId"
      @resolved="onConflictResolved"
    />

    <!-- 工作流进度条 -->
    <WorkflowProgress :project-id="selectedProjectId" :year="selectedYear" />

    <!-- Sprint 4：StaleIndicator 统一组件 + 横幅 -->
    <div v-if="stale.isStale.value" class="gt-stale-banner">
      <StaleIndicator :stale="true" tooltip="上游数据已变更，附注数据可能过时" />
      <span class="gt-stale-text">
        上游数据已变更（{{ stale.staleCount.value }} 张底稿待重算），附注数据可能过时
      </span>
      <el-button size="small" type="primary" :loading="stale.loading.value" @click="onStaleRecalc">
        🔄 点击重算
      </el-button>
    </div>

    <!-- 编辑锁提示 -->
    <el-alert v-if="editLock.locked.value && !editLock.isMine.value" type="warning" :closable="false" style="margin-bottom: 8px">
      {{ editLock.lockedBy.value || '其他用户' }} 正在编辑，当前为只读模式
    </el-alert>

    <div class="gt-de-body">
      <!-- 左侧：目录树 -->
      <div class="gt-de-sidebar">
        <!-- 单位切换 -->
        <div class="gt-de-unit-bar">
          <span class="gt-de-unit-name">{{ currentProjectName || '—' }}</span>
          <el-select v-if="projectOptions.length > 1" v-model="selectedProjectIdLocal" size="small" style="width: 100%; margin-top: 4px" @change="onSwitchProjectLocal">
            <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </div>
        <!-- 视图切换 -->
        <div class="gt-de-view-toggle">
          <el-radio-group v-model="treeViewMode" size="small">
            <el-radio-button value="tree">树形</el-radio-button>
            <el-radio-button value="flat">平铺</el-radio-button>
          </el-radio-group>
          <el-button size="small" text @click="expandAll" title="全部展开">展开</el-button>
          <el-button size="small" text @click="collapseAll" title="全部收起">收起</el-button>
        </div>
        <el-input v-model="treeSearch" size="small" placeholder="搜索章节..." clearable class="gt-de-tree-search" />
        <div class="gt-de-tree-wrap">
          <!-- 树形视图 -->
          <el-tree
            v-if="treeViewMode === 'tree'"
            :data="filteredTreeData"
            :props="{ label: 'label', children: 'children' }"
            :indent="10"
            highlight-current
            node-key="id"
            :draggable="!isEqcrRole"
            :allow-drop="allowTreeDrop"
            @node-click="onNodeClick"
            @node-contextmenu="onTreeNodeContextMenu"
            @node-drop="onTreeNodeDrop"
            :default-expanded-keys="['chapter_five']"
            ref="noteTreeRef"
          >
            <template #default="{ data }">
              <div v-if="data.isGroup" class="gt-de-tree-group">
                <span class="gt-de-tree-group-label">{{ data.label }}</span>
                <span v-if="getGroupValidationErrorCount(data)" class="gt-de-tree-error-badge">{{ getGroupValidationErrorCount(data) }}</span>
              </div>
              <div v-else class="gt-de-tree-node" :class="{ 'gt-de-tree-node-active': currentNote?.id === data.id, 'gt-de-tree-node-error': hasSectionValidationError(data.data?.note_section) }">
                <span class="gt-de-tree-label">
                  <span v-if="getRenderedNumber(data.data?.note_section)" class="gt-de-tree-number">{{ getRenderedNumber(data.data?.note_section) }}</span>
                  {{ data.data?.section_title || data.label }}
                </span>
                <span v-if="hasSectionValidationError(data.data?.note_section)" class="gt-de-tree-error-dot" title="校验失败">●</span>
                <!-- Sprint 3 Task 3.6: 上游变更红点 -->
                <el-tooltip
                  v-if="noteStale.isStale(data.data?.note_section)"
                  content="上游已变更，建议重算"
                  placement="right"
                  effect="dark"
                >
                  <span class="gt-de-tree-stale-dot" data-test="de-stale-dot">🔴</span>
                </el-tooltip>
                <!-- A.6.2: 协作锁可视化 -->
                <NoteSectionLockBadge
                  v-if="getSectionLock(data.data?.note_section)"
                  :lock-info="getSectionLock(data.data?.note_section)"
                  :project-id="projectId"
                  :section-id="data.data?.note_section || ''"
                  @lock-acquired="fetchTree()"
                />
              </div>
            </template>
          </el-tree>
          <!-- 平铺视图 -->
          <div v-if="treeViewMode === 'flat'" class="gt-de-flat-list">
            <div
              v-for="note in flatNoteList" :key="note.note_section"
              class="gt-de-flat-item"
              :class="{ 'gt-de-flat-item--active': currentNote?.note_section === note.note_section }"
              @click="onFlatItemClick(note)"
            >
              <span class="gt-de-flat-item-title">{{ note.section_title }}</span>
              <el-tag v-if="(note as any).scope === 'consolidated_only'" size="small" type="warning" style="font-size: var(--gt-font-size-xs)">合并</el-tag>
            </div>
          </div>
          <div v-if="!filteredTreeData.length && !treeLoading" class="gt-de-empty-hint">
            暂无附注，点击"生成附注"
          </div>
        </div>
      </div>

      <!-- 中间：编辑区 -->
      <div class="gt-de-main" v-loading="detailLoading">
        <!-- 底稿同步失败提示 -->
        <el-alert
          v-if="syncError"
          type="error"
          title="底稿数据同步失败"
          description="无法自动从底稿刷新附注数据"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        >
          <template #default>
            <el-button size="small" @click="onManualRefresh">手动重试</el-button>
          </template>
        </el-alert>
        <!-- 底稿同步来源提示（design §12.1：底稿 → 模块单向同步） -->
        <el-alert
          v-if="(currentNote as any)?.last_sync_source === 'workpaper'"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        >
          <template #title>
            <span>此数据由底稿同步</span>
          </template>
          <template #default>
            <div class="gt-de-sync-banner">
              <span>建议在底稿编辑入口（C 类附注 sheet）维护，避免双源不一致。</span>
              <span v-if="(currentNote as any)?.last_sync_at" class="gt-de-sync-time">
                · 最近同步：{{ formatSyncTime((currentNote as any).last_sync_at) }}
              </span>
            </div>
          </template>
        </el-alert>
        <template v-if="currentNote">
          <div class="gt-de-editor-header">
            <div>
              <h4 class="gt-de-section-title">
                {{ currentNote.section_title }}
                <transition name="el-fade-in">
                  <span v-if="justSaved" class="gt-de-saved-badge">✓ 已保存</span>
                </transition>
              </h4>
              <span class="gt-de-section-account">{{ currentNote.account_name }}</span>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
              <el-tag :type="currentNote.status === 'confirmed' ? 'success' : 'info'" size="small">
                {{ currentNote.status === 'confirmed' ? '已确认' : '草稿' }}
              </el-tag>
            </div>
          </div>

            <!-- 表格型（支持多表格Tab切换） -->
            <div v-if="currentNote.content_type === 'table' || currentNote.content_type === 'mixed'">
              <!-- 多表格Tab -->
              <el-tabs v-if="currentNoteTables.length > 1" v-model="activeTableTab" type="card" size="small" style="margin-bottom: 8px;">
                <el-tab-pane v-for="(tbl, ti) in currentNoteTables" :key="ti" :name="String(ti)" :label="getTableTabLabel(tbl, ti)" />
              </el-tabs>
              <!-- 当前表格 -->
              <el-table ref="deTableRef" v-if="activeTableData?.rows?.length || activeTableData?.headers?.length" :data="activeTableData.rows || []"
                border size="small" style="margin-bottom: 12px"
                :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
                :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap', padding: '4px 0' }"
                :row-style="{ height: '26px' }"
                :cell-style="{ padding: '2px 6px', fontSize: '12px', lineHeight: '20px' }"
                :cell-class-name="deCellClassName"
                @cell-click="onDeCellClick"
                @cell-contextmenu="onDeCellContextMenu">
                <el-table-column v-for="(h, hiRaw) in (activeTableData.headers || [])" :key="hiRaw"
                  :label="h" :min-width="Number(hiRaw) === 0 ? 160 : 120" :align="Number(hiRaw) === 0 ? 'left' : 'right'" resizable>
                  <template #default="{ row, $index }">
                    <template v-if="Number(hiRaw) === 0">
                      <span :class="{ 'total-label': row.is_total }">{{ row.label }}</span>
                    </template>
                    <template v-else>
                      <el-tooltip
                        :disabled="!getCellValidationError($index, Number(hiRaw) - 1)"
                        :content="getCellValidationError($index, Number(hiRaw) - 1)"
                        placement="top"
                        effect="dark"
                      >
                      <CommentTooltip :comment="deComments.getComment(activeTableData?.section_id || currentNote?.note_section || 'default', $index, Number(hiRaw))">
                      <div class="gt-cell-wrapper" :class="{ 'gt-cell-auto-fill': getCellMode(row, Number(hiRaw) - 1) === 'auto', 'gt-cell-validation-error': !!getCellValidationError($index, Number(hiRaw) - 1) }">
                        <el-input-number v-if="editMode && !row.is_total"
                          v-model="row.values[Number(hiRaw) - 1]" :controls="false" :precision="2"
                          size="small" style="width: 100%; height: 22px"
                          @change="onCellValueChange($index, Number(hiRaw) - 1, $event)" />
                        <span v-else-if="row.is_total" :class="['gt-amt', { 'gt-formula-mismatch': isFormulaMismatch(row, Number(hiRaw) - 1) }]">
                          <GtAmountCell :value="getCellValue(row, Number(hiRaw) - 1)" />
                        </span>
                        <span v-else :class="['gt-amt', { 'total-val': row.is_total }]">
                          <GtAmountCell :value="getCellValue(row, Number(hiRaw) - 1)" />
                        </span>
                        <span v-if="getCellMode(row, Number(hiRaw) - 1) === 'auto'" class="gt-cell-source gt-cell-trace-trigger" title="点击追溯来源" @click.stop="onAutoCellTraceClick($index, Number(hiRaw) - 1, $event)">📊</span>
                        <span v-else-if="getCellMode(row, Number(hiRaw) - 1) === 'manual'" class="gt-cell-manual" title="手动编辑">✏️</span>
                      </div>
                      </CommentTooltip>
                      </el-tooltip>
                    </template>
                  </template>
                </el-table-column>
              </el-table>
              <div v-else-if="activeTableData?.headers?.length" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); padding: 10px; text-align: center; border: 1px dashed var(--gt-color-border-purple); border-radius: 6px;">
                该表格暂无数据行（可在编辑模式下添加）
              </div>
            </div>

            <!-- 文字型 — 富文本编辑器 (Req 48.1-48.7) -->
            <div v-if="currentNote.content_type === 'text' || currentNote.content_type === 'mixed'" class="gt-de-tiptap-wrapper">
              <!-- 增强富文本编辑器：支持标题/加粗/斜体/列表/表格/缩进/颜色/占位符/源码/字数 -->
              <NoteRichTextEditor
                v-model="textContent"
                @update:modelValue="onRichTextChange"
              />
              <!-- AI 工具栏 -->
              <div class="gt-de-ai-toolbar">
                <el-button-group size="small">
                  <el-button @click="onAiContinueWrite" :loading="aiLoading" title="AI续写：在光标位置续写内容">✨ 续写</el-button>
                  <el-button @click="onAiRewriteOpen" :loading="aiLoading" title="AI改写：选中文本后点击改写">✏️ 改写</el-button>
                  <el-button @click="onAiGeneratePolicy" :loading="aiLoading" title="生成标准会计政策文本">📋 生成政策</el-button>
                  <el-button @click="onAiGenerateAnalysis" :loading="aiLoading" title="生成变动分析说明">📊 变动分析</el-button>
                  <el-button @click="onPickKnowledge" title="选择知识库文档作为AI参考上下文">📚 知识库</el-button>
                </el-button-group>
                <span v-if="knowledgeContextText" class="gt-de-ai-hint" style="color: var(--gt-color-teal, #36b37e)">
                  📎 已加载 {{ knowledgeDocCount }} 篇参考文档
                  <el-button size="small" link @click="clearKnowledgeContext" style="margin-left: 4px; font-size: var(--gt-font-size-xs)">清除</el-button>
                </span>
              </div>
            </div>

            <!-- AI改写弹窗 -->
            <el-dialog v-model="aiRewriteDialogVisible" title="AI 改写" width="520px" append-to-body>
              <div style="margin-bottom: 12px;">
                <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-bottom: 6px;">选中的文本：</div>
                <div style="background: var(--gt-color-primary-bg); padding: 10px; border-radius: 6px; font-size: var(--gt-font-size-sm); line-height: 1.6; max-height: 120px; overflow-y: auto;">{{ aiSelectedText }}</div>
              </div>
              <el-input v-model="aiRewriteInstruction" type="textarea" :rows="2" placeholder="改写指令，如：使其更加专业规范 / 简化表述 / 补充细节" />
              <template #footer>
                <el-button @click="aiRewriteDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="onAiRewriteConfirm" :loading="aiLoading">确认改写</el-button>
              </template>
            </el-dialog>

            <!-- 搜索栏（Ctrl+F） -->
            <TableSearchBar
              :is-visible="deSearch.isVisible.value"
              :keyword="deSearch.keyword.value"
              :match-info="deSearch.matchInfo.value"
              :has-matches="deSearch.matches.value.length > 0"
              :case-sensitive="deSearch.caseSensitive.value"
              :show-replace="false"
              @update:keyword="deSearch.keyword.value = $event"
              @update:case-sensitive="deSearch.caseSensitive.value = $event"
              @search="deSearch.search()"
              @next="deSearch.nextMatch()"
              @prev="deSearch.prevMatch()"
              @close="deSearch.close()"
            />

            <!-- 选中区域状态栏 -->
            <SelectionBar :stats="deCtx.selectionStats()" />

            <!-- 表格结构编辑工具栏 (Req 38.1-38.6) -->
            <div v-if="editMode && (currentNote.content_type === 'table' || currentNote.content_type === 'mixed')" class="gt-de-structure-toolbar">
              <el-button-group size="small">
                <el-button @click="onStructureAddRow" title="在末尾新增行">➕ 行</el-button>
                <el-button @click="onStructureDeleteRow" title="删除最后一行（合计行除外）" :disabled="!canDeleteRow">➖ 行</el-button>
                <el-button @click="onStructureAddColumn" title="新增列">➕ 列</el-button>
                <el-button @click="onStructureDeleteColumn" title="删除最后一列" :disabled="!canDeleteColumn">➖ 列</el-button>
              </el-button-group>
              <el-button-group size="small" style="margin-left: 8px;">
                <el-button @click="noteTableStructure.undo()" :disabled="!noteTableStructure.canUndo.value" title="撤销 (Ctrl+Z)">↩ 撤销</el-button>
                <el-button @click="noteTableStructure.redo()" :disabled="!noteTableStructure.canRedo.value" title="重做 (Ctrl+Y)">↪ 重做</el-button>
              </el-button-group>
              <el-button size="small" style="margin-left: 8px;" @click="onRestoreTemplateStructure" title="恢复为模板默认结构">🔄 恢复模板结构</el-button>
            </div>

            <div class="gt-de-editor-footer">
              <el-button v-if="!editMode" @click="enterEdit()" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">编辑</el-button>
              <template v-else>
                <el-button @click="exitEdit(true)">取消</el-button>
                <el-button type="primary" @click="onSave" :loading="saveLoading" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">保存</el-button>
                <el-button type="warning" @click="onClearAllFormulas" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">一键清除公式</el-button>
                <el-button @click="onRestoreAutoMode" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">恢复自动提数</el-button>
              </template>
            </div>
          </template>
          <div v-else class="gt-de-empty-hint">请从左侧目录选择章节</div>
      </div>

      <!-- 右侧：校验面板 -->
      <div class="gt-de-validation">
        <div class="gt-de-sidebar-title">校验结果</div>
        <div v-if="validationFindings.length === 0" class="gt-de-empty-hint">暂无校验结果</div>
        <div v-for="(f, fi) in validationFindings" :key="fi" class="gt-de-finding-item"
          :class="'gt-de-severity-' + f.severity">
          <div class="gt-de-finding-header">
            <el-tag :type="(severityTagType(f.severity)) || undefined" size="small">{{ f.severity }}</el-tag>
            <span class="gt-de-finding-type">{{ f.check_type }}</span>
          </div>
          <div class="gt-de-finding-section">{{ f.note_section }} {{ f.table_name }}</div>
          <div class="gt-de-finding-msg">{{ f.message }}</div>
          <div v-if="f.expected_value || f.actual_value" class="gt-de-finding-values">
            期望: {{ f.expected_value ?? '-' }} | 实际: {{ f.actual_value ?? '-' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 公式管理弹窗（与报表页统一） -->
    <FormulaManagerDialog
      v-model="showNoteFormulaManager"
      :rows="currentNoteFormulaRows"
      :project-id="projectId"
      :year="year"
      @saved="onFormulaApplied"
      @applied="onFormulaApplied"
    />

    <!-- 结构化编辑器弹窗 -->
    <el-dialog v-model="showStructureEditor" title="" width="90%" fullscreen append-to-body :show-close="true">
      <StructureEditor
        v-if="showStructureEditor && currentNote"
        :project-id="projectId"
        module="disclosure_note"
        :module-params="{ note_section: currentNote.note_section, year }"
        :project-name="currentProjectName"
        :template-type="templateType"
        :report-scope="'consolidated'"
        :year="year"
        @saved="onStructureEditorSaved"
        @add-table="onStructureEditorAddTable"
        @add-column="onStructureEditorAddColumn"
        @custom-template-restored="onCustomTemplateRestored"
      />
    </el-dialog>

    <!-- 附注转换规则弹窗（国企↔上市） -->
    <NoteMappingDialog
      v-model="showNoteMappingDialog"
      :project-id="projectId"
      :loading="noteMappingLoading"
      :can-edit="canEdit"
      :rules="noteMappingRules"
      :get-mapping-data="getNoteMappingData"
      @load-preset="loadNoteMappingPreset"
      @save-rules="saveNoteMappingRules"
      @mapping-applied="onNoteMappingApplied"
    />

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showNoteImport"
      import-type="disclosure_note"
      :project-id="projectId"
      :year="year"
      @imported="onNoteImported"
    />

    <!-- D15 离线导出弹窗 -->
    <NoteOfflineExportDialog
      v-model="showOfflineExport"
      :project-id="projectId"
      :year="year"
      :sections="noteList.map(n => ({ section_id: n.note_section, title: n.section_title, has_data: !n.is_empty }))"
    />

    <!-- D15 离线导入弹窗 -->
    <NoteOfflineImportDialog
      v-model="showOfflineImport"
      :project-id="projectId"
      :year="year"
      @imported="fetchTree()"
    />

    <!-- C.1.4: AI 建议侧栏 -->
    <NoteAiSuggestionPanel
      v-model="showAiPanel"
      :project-id="projectId"
      :year="year"
      :current-section-id="currentNote?.note_section || ''"
    />

    <!-- C.2.5: 版本树可视化 -->
    <NoteVersionTreePanel
      v-model="showVersionTree"
      :project-id="projectId"
      :year="year"
      :section-id="currentNote?.note_section || ''"
    />

    <!-- C.3.6: 集团基线对话框 -->
    <NoteGroupBaselineDialog
      v-model="showGroupBaseline"
      :project-id="projectId"
      :year="year"
      @applied="fetchTree()"
    />

    <!-- C.3.7: 段落变量编辑器 -->
    <NoteParagraphVarsEditor
      v-model="showParagraphVars"
      :project-id="projectId"
      :year="year"
      :section-id="currentNote?.note_section || ''"
      @saved="fetchDetail(currentNote?.note_section || '')"
    />

    <!-- C.3.10: 上年对比侧栏 -->
    <NotePriorYearPanel
      v-model="showPriorYear"
      :prior-year-note="priorYearNote"
      :current-note="currentNote"
    />

    <!-- Sprint 3 Task 3.1: 新增章节 dialog -->
    <el-dialog
      v-model="showAddSectionDialog"
      title="➕ 新增章节"
      width="540px"
      append-to-body
      data-test="de-add-section-dialog"
    >
      <el-form label-width="100px" size="small">
        <el-form-item label="章节编号">
          <el-input
            v-model="addSectionForm.section_number"
            placeholder="如：五、X1"
            data-test="de-add-section-number"
          />
        </el-form-item>
        <el-form-item label="章节标题">
          <el-input
            v-model="addSectionForm.section_title"
            placeholder="如：递延收益"
            data-test="de-add-section-title"
          />
        </el-form-item>
        <el-form-item label="科目名">
          <el-input
            v-model="addSectionForm.account_name"
            placeholder="可选"
            data-test="de-add-section-account"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number
            v-model="addSectionForm.sort_order"
            :min="0"
            :max="99999"
            controls-position="right"
            style="width: 100%"
            data-test="de-add-section-sort"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddSectionDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="addSectionLoading"
          data-test="de-add-section-confirm"
          @click="onAddSectionConfirm"
        >确认新增</el-button>
      </template>
    </el-dialog>

    <!-- Sprint 3 Task 3.5/3.6: 章节列表右键菜单 -->
    <teleport to="body">
      <div
        v-if="treeContextMenu.visible"
        class="gt-de-tree-ctx-menu"
        :style="{ top: treeContextMenu.y + 'px', left: treeContextMenu.x + 'px' }"
        data-test="de-tree-context-menu"
        @click.stop
      >
        <div
          class="gt-de-tree-ctx-item"
          data-test="de-tree-recalc"
          @click="onTreeCtxRecalc"
        >🔄 重算此章节</div>
        <div
          v-if="treeContextMenu.section?._custom"
          class="gt-de-tree-ctx-item gt-de-tree-ctx-danger"
          data-test="de-tree-delete-custom"
          @click="onTreeCtxDeleteCustom"
        >🗑 删除自定义章节</div>
      </div>
    </teleport>
  </div>

  <!-- 右键菜单（统一组件 + 查看相关底稿） -->
  <CellContextMenu
    :visible="deCtx.contextMenu.visible"
    :x="deCtx.contextMenu.x"
    :y="deCtx.contextMenu.y"
    :item-name="deCtx.contextMenu.itemName"
    :value="deCtx.selectedCells.value.length === 1 ? deCtx.selectedCells.value[0]?.value : undefined"
    :multi-count="deCtx.selectedCells.value.length"
    @copy="onDeCtxCopy"
    @formula="onDeCtxFormula"
    @trust-score="onDeCtxTrustScore"
    @sum="onDeCtxSum"
    @compare="onDeCtxCompare"
  >
    <!-- R8-S2-12：查看相关底稿 -->
    <div class="gt-ucell-ctx-item" @click="onDeCtxRelatedWp">
      <span class="gt-ucell-ctx-icon">📝</span> 查看相关底稿
    </div>
    <!-- R9-F5：穿透到序时账 -->
    <div class="gt-ucell-ctx-item" @click="onDeCtxPenetrateToLedger">
      <span class="gt-ucell-ctx-icon">📊</span> 穿透到序时账
    </div>
    <!-- Sprint 5.7：查看数据来源 -->
    <div class="gt-ucell-ctx-item" @click="onDeCtxViewDataSource">
      <span class="gt-ucell-ctx-icon">🔍</span> 查看数据来源
    </div>
    <!-- 合并明细穿透（统一组件 ConsolBreakdownDialog，source=note）：合并附注最相关，单体附注无 breakdown 时弹窗友好降级 -->
    <div class="gt-ucell-ctx-item" @click="onDeCtxViewConsolBreakdown">
      <span class="gt-ucell-ctx-icon">🔗</span> 查看合并明细
    </div>
    <!-- Sprint 2 Task 2.4：CellTrace 单元格溯源 -->
    <div class="gt-ucell-ctx-item" @click="onDeCtxOpenCellTrace">
      <span class="gt-ucell-ctx-icon">🔎</span> 溯源到底稿/试算表
    </div>
  </CellContextMenu>

  <!-- V3 Req 9.6: 数字信任度面板 -->
  <TrustScorePanel ref="trustScorePanelRef" :project-id="projectId" />

  <!-- V3 Req 10.4: 可解释状态机面板 -->
  <StatusMachinePanel ref="smPanelRef" module="disclosure" :instance-id="disclosureInstanceId" />

  <!-- V3 Req 11.6: 时光机面板 -->
  <TimeMachineDrawer ref="tmDrawerRef" module="disclosure" :instance-id="disclosureInstanceId" @restored="onTimeMachineRestored" />

  <!-- Sprint 5.7: 数据来源弹窗 -->
  <CellFormulaDetail
    :visible="showCellFormulaDetail"
    module="NOTE"
    :wp-code="cellDetailWpCode"
    :sheet-name="cellDetailSheet"
    :label="cellDetailLabel"
    @update:visible="showCellFormulaDetail = $event"
    @navigate="onCellDetailNavigate"
  />

  <!-- 合并附注穿透弹窗（统一组件，source=note）：右键"查看合并明细"打开 -->
  <ConsolBreakdownDialog
    v-model="consolBreakdownVisible"
    source="note"
    :project-id="projectId"
    :year="year"
    :section-id="consolBreakdownSectionId"
  />

  <!-- Sprint 2 Task 2.4: CellTrace 单元格溯源弹窗 -->
  <CellTraceDialog
    v-if="showCellTrace"
    v-model="showCellTrace"
    :note-id="cellTraceCtx.noteId"
    :row-idx="cellTraceCtx.rowIdx"
    :col-idx="cellTraceCtx.colIdx"
    @penetrate-to-tb="onCellTracePenetrateTb"
  />

  <!-- Phase 3 F1: 来源追溯弹窗 (Requirements: F1.1, F1.3, F1.4) -->
  <teleport to="body">
    <div
      v-if="tracePopoverVisible"
      class="gt-trace-popover-overlay"
      @click.self="tracePopoverVisible = false"
    >
      <div
        class="gt-trace-popover-container"
        :style="{ top: tracePopoverPos.y + 'px', left: tracePopoverPos.x + 'px' }"
      >
        <TraceSourcePopover
          :trace-data="traceData"
          :visible="tracePopoverVisible"
          :loading="traceLoading"
          @update:visible="tracePopoverVisible = $event"
          @jump-to-tb="onTraceJumpToTB"
        >
          <span class="gt-trace-anchor" />
        </TraceSourcePopover>
      </div>
    </div>
  </teleport>

  <!-- 知识库文档选择弹窗 [R3.7] -->
  <KnowledgePickerDialog v-model:visible="knowledgePickerVisible" />

  <!-- 打印预览 (Req 41.1-41.5) -->
  <NotesPrintPreview
    :visible="showPrintPreview"
    :sections="printPreviewSections"
    @close="showPrintPreview = false"
    @insert-page-break="onInsertPageBreak"
  />

  <!-- AI 文档对话面板 -->
  <DocAiChatPanel
    :doc-type="'note'"
    :doc-id="currentNote?.id || currentNote?.note_section || ''"
    :project-id="projectId"
    :year="year"
    :visible="showDocAiChat"
    @update:visible="showDocAiChat = $event"
    @close="showDocAiChat = false"
    @adopt="onDocAiAdopt"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onUnmounted, watch } from 'vue'
import * as P from '@/services/apiPaths'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useCellSelection } from '@/composables/useCellSelection'
import { usePenetrate } from '@/composables/usePenetrate'
import { useEditMode } from '@/composables/useEditMode'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import TrustScorePanel from '@/components/trust/TrustScorePanel.vue'
import StatusMachinePanel from '@/components/status_machine/StatusMachinePanel.vue'
import TimeMachineDrawer from '@/components/time_machine/TimeMachineDrawer.vue'
import CellFormulaDetail from '@/components/CellFormulaDetail.vue'
import ConsolBreakdownDialog from '@/components/consolidation/ConsolBreakdownDialog.vue'
import TraceSourcePopover from '@/components/common/TraceSourcePopover.vue'
import CellTraceDialog from '@/components/notes/CellTraceDialog.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { confirmLeave } from '@/utils/confirm'
import WorkflowProgress from '@/components/common/WorkflowProgress.vue'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { fmtAmount } from '@/utils/formatters'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { ElMessage } from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import StructureEditor from '@/components/formula/StructureEditor.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import NoteRichTextEditor from '@/components/NoteRichTextEditor.vue'
import NotesPrintPreview from '@/components/notes/NotesPrintPreview.vue'
import { refreshDisclosureFromWorkpapers, getProjectWizardState } from '@/services/commonApi'
import { useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { useAuthStore } from '@/stores/auth'

// EQCR 只读访问 (Requirements: 17.1-17.4)
const authStore = useAuthStore()
const isEqcrRole = computed(() => authStore.user?.role === 'eqcr')
import Placeholder from '@tiptap/extension-placeholder'
import {
  generateDisclosureNotes, getDisclosureNoteDetail,
  validateDisclosureNotes, getValidationResults,
  type DisclosureNoteDetail, type NoteValidationFinding,
} from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { useProjectStore } from '@/stores/project'
import { knowledgePickerVisible } from '@/composables/useKnowledge'
import { useAutoSave } from '@/composables/useAutoSave'
import { withLoading } from '@/composables/useLoading'
import KnowledgePickerDialog from '@/components/common/KnowledgePickerDialog.vue'
import { useEditingLock } from '@/composables/useEditingLock'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { useProjectEvents } from '@/composables/useProjectEvents'
import { handleApiError } from '@/utils/errorHandler'
import { useNoteTableStructure, type TableData } from '@/composables/useNoteTableStructure'
import NoteOfflineExportDialog from '@/components/notes/NoteOfflineExportDialog.vue'
import NoteOfflineImportDialog from '@/components/notes/NoteOfflineImportDialog.vue'
import NoteTemplateSwitch from '@/components/notes/NoteTemplateSwitch.vue'
import NoteSectionLockBadge from '@/components/notes/NoteSectionLockBadge.vue'
import NoteAiSuggestionPanel from '@/components/notes/NoteAiSuggestionPanel.vue'
import NoteVersionTreePanel from '@/components/notes/NoteVersionTreePanel.vue'
import NoteGroupBaselineDialog from '@/components/notes/NoteGroupBaselineDialog.vue'
import NoteParagraphVarsEditor from '@/components/notes/NoteParagraphVarsEditor.vue'
import NotePriorYearPanel from '@/components/notes/NotePriorYearPanel.vue'
import DocAiChatPanel from '@/components/DocAiChatPanel.vue'
import { useNoteSectionNumbering } from '@/composables/useNoteSectionNumbering'
import { useNoteTree, type TreeNode } from '@/views/composables/useNoteTree'
import { useNoteDetail } from '@/views/composables/useNoteDetail'
import { useNotePersist } from '@/views/composables/useNotePersist'
import { useNoteRefresh } from '@/views/composables/useNoteRefresh'
import { useNoteTemplate } from '@/views/composables/useNoteTemplate'
import { useNoteExport } from '@/views/composables/useNoteExport'
import { useNoteAi } from '@/views/composables/useNoteAi'
import { useAuditContext } from '@/composables/useAuditContext'
import NoteMappingDialog from '@/views/components/NoteMappingDialog.vue'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import AiContentPendingBanner from '@/components/ai/AiContentPendingBanner.vue'
import ConflictBanner from '@/components/conflict/ConflictBanner.vue'
import ConflictResolutionPanel from '@/components/conflict/ConflictResolutionPanel.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const { canEdit, onContextChange } = useAuditContext()

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
  // 父组件在确认流完成后可刷新附注内容
  if (currentNote.value?.note_section) {
    fetchDetail(currentNote.value.note_section)
  }
}

const year = computed(() => {
  const qy = Number(route.query.year)
  return (Number.isFinite(qy) && qy > 2000) ? qy : projectStore.year
})

// ─── 云协同：账套激活/回滚后自动刷新 ─────────────────────────────────────────
const { onDatasetActivated, onDatasetRolledBack } = useProjectEvents(projectId)
onDatasetActivated(() => fetchTree())
onDatasetRolledBack(() => fetchTree())

// R8-S2-03：Stale 状态追踪
import { useStaleStatus } from '@/composables/useStaleStatus'
import StaleIndicator from '@/components/StaleIndicator.vue'
const stale = useStaleStatus(projectId)
// onStaleRecalc provided by useNoteRefresh composable below

// Sprint 3 Task 3.6: 附注章节级 stale 状态追踪
import { useNoteStale } from '@/composables/useNoteStale'
const noteStale = useNoteStale(projectId)

// Sprint 3 Task 3.1/3.5: 自定义附注模板（now in useNoteSectionManage composable）

const editLock = useEditingLock({
  resourceId: computed(() => 'disclosure_' + (route.params.projectId as string || '')),
  resourceType: 'other',  // 附注无后端锁端点，降级为前端检测
  autoAcquire: false,
})

// A.6.2: 章节级协作锁状态
const sectionLocks = ref<Record<string, { locked_by: string; locked_by_name: string; locked_at: string; section_id: string } | null>>({})

function getSectionLock(sectionId: string | undefined) {
  if (!sectionId) return null
  return sectionLocks.value[sectionId] || null
}

// 编辑锁联动 watch 推迟到 useEditMode 定义之后挂载（避免 TDZ）

// R7-S2-05：后端定时自动保存（2 分钟间隔）
const autoSave = useWorkpaperAutoSave(async () => {
  await onSave()
}, 120_000)

// 单位切换 — 使用 projectStore
const selectedProjectId = ref('')
const projectOptions = computed(() => projectStore.projectOptions)
function onProjectChange(newId: string) {
  router.push({ path: `/projects/${newId}/disclosure-notes`, query: route.query })
}

// 年度切换
const selectedYear = ref(new Date().getFullYear() - 1)
const yearOptions = computed(() => projectStore.yearOptions)
function onYearChange() {
  projectStore.changeYear(selectedYear.value)
  fetchTree().then(() => {
    if (noteList.value.length === 0) onGenerate()
  })
  currentNote.value = null
}

// templateType 提前声明：useNoteTemplate + useNoteTree 均依赖它
const templateType = ref('soe')

// 当前项目名称
const currentProjectName = computed(() => {
  if (projectStore.clientName) return projectStore.clientName
  const p = projectOptions.value.find(o => o.id === projectId.value)
  return p?.name || ''
})

// C.3.11: 章节序号实时渲染
const numbering = useNoteSectionNumbering(
  () => projectId.value,
  () => year.value
)

// ─── 章节树 composable（useNoteTree 抽取） ──────────────────────────────────
const {
  noteList, treeLoading, treeSearch, noteTreeRef, treeViewMode,
  treeData, filteredTreeData, flatNoteList,
  fetchTree, allowTreeDrop, onTreeNodeDrop, expandAll, collapseAll,
} = useNoteTree({
  projectId,
  year,
  templateType,
  isEqcrRole,
  onTreeLoaded: () => numbering.refreshNumbers(),
})

// ── 转换规则（useNoteTemplate composable 提供，须在 useNoteTree 之后，依赖 noteList/fetchTree） ──
const {
  showNoteMappingDialog, noteMappingLoading, noteMappingRules,
  loadNoteMappingPreset, saveNoteMappingRules, getNoteMappingData, onNoteMappingApplied: onNoteMappingApplied,
  getNoteTemplateConfigData, onNoteTemplateApplied,
} = useNoteTemplate({
  projectId,
  templateType,
  noteList,
  fetchTree,
  onGenerate,
})

const genLoading = ref(false)
const showNoteImport = ref(false)
const showOfflineExport = ref(false)
const showOfflineImport = ref(false)
const showAiPanel = ref(false)
const showDocAiChat = ref(false)
const showVersionTree = ref(false)
const showGroupBaseline = ref(false)
const showParagraphVars = ref(false)
const showPriorYear = ref(false)

function getRenderedNumber(sectionId: string | undefined): string {
  if (!sectionId) return ''
  return numbering.getNumber(sectionId)
}

// C.3.12: scope 切换（单体↔合并）+ 章节序号自动重算
function onScopeChange(scope: 'standalone' | 'consolidated' | 'both') {
  numbering.setScope(scope)
}
const validateLoading = ref(false)
const detailLoading = ref(false)
const showNoteFormulaManager = ref(false)
const showStructureEditor = ref(false)
const showPrintPreview = ref(false)

// design §12.1: 同步时间相对显示
function formatSyncTime(iso: string | Date | null | undefined): string {
  if (!iso) return ''
  try {
    const d = typeof iso === 'string' ? new Date(iso) : iso
    const diff = Date.now() - d.getTime()
    if (Number.isNaN(diff)) return String(iso)
    if (diff < 60_000) return '刚刚'
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch { return String(iso) }
}

const { isEditing: editMode, isDirty: editDirty, enterEdit, exitEdit, markDirty: markEditDirty, clearDirty: clearEditDirty } = useEditMode()

// 编辑锁联动：进入编辑时 acquire，退出时 release；他人持锁时强制退出
watch(() => editMode.value, async (editing) => {
  if (editing) await editLock.acquire()
  else editLock.release()
})
watch(() => editLock.isMine.value, (mine) => {
  if (!mine && editMode.value) exitEdit()
})
const customTemplateId = ref('')
const customTemplateName = ref('')
const customTemplateVersion = ref('')

/** 附注模板选项（含自定义模板） */
const deTemplateOptions = computed(() => {
  const opts = [
    { label: '国企版', value: 'soe' },
    { label: '上市版', value: 'listed' },
  ]
  if (customTemplateId.value) {
    opts.push({ label: customTemplateName.value || '自定义', value: 'custom' })
  }
  return opts
})

const currentNote = ref<DisclosureNoteDetail | null>(null)
const textContent = ref('')
const validationFindings = ref<NoteValidationFinding[]>([])
const priorYearNote = ref<any>(null)
// TipTap 编辑器
const editor = useEditor({
  extensions: [
    StarterKit,
    Placeholder.configure({ placeholder: '请输入附注文字内容...' }),
  ],
  content: '',
  onUpdate: ({ editor: e }) => { textContent.value = e.getHTML(); if (editMode.value) { markEditDirty(); autoSave.markDirty() } },
})

onBeforeUnmount(() => { editor.value?.destroy() })

// ── NoteRichTextEditor change handler (Req 48) ──
function onRichTextChange(html: string) {
  textContent.value = html
  if (editMode.value) { markEditDirty(); autoSave.markDirty() }
}

// ── 自动保存/草稿恢复 [R3.8] ──
const autoSaveKey = computed(() => `disclosure_note_${projectId.value}_${currentNote.value?.note_section || 'none'}`)
const { clearDraft: clearAutoSaveDraft } = useAutoSave(
  autoSaveKey.value,
  () => {
    if (!currentNote.value) return null
    return {
      text_content: textContent.value,
      table_data: currentNote.value.table_data,
      note_section: currentNote.value.note_section,
    }
  },
  (data) => {
    if (!currentNote.value || !data) return
    if (data.text_content != null) {
      textContent.value = data.text_content
      editor.value?.commands.setContent(data.text_content)
    }
    if (data.table_data != null) {
      currentNote.value.table_data = data.table_data
    }
  },
  { enabled: editMode },
)

// ── AI 功能（useNoteAi composable）──
const {
  aiLoading, aiRewriteDialogVisible, aiRewriteInstruction, aiSelectedText,
  knowledgeContextText, knowledgeDocCount,
  onAiContinueWrite, onAiRewriteOpen, onAiRewriteConfirm,
  onAiGeneratePolicy, onAiGenerateAnalysis, onPickKnowledge, clearKnowledgeContext, getSelectedText,
} = useNoteAi({ projectId, year, templateType, currentNote, editor })
// 单位切换（侧边栏）
const selectedProjectIdLocal = ref('')

function onSwitchProjectLocal(newId: string) {
  if (newId && newId !== projectId.value) {
    router.push(`/projects/${newId}/disclosure-notes`)
  }
}

function onFlatItemClick(note: any) {
  currentNote.value = note
}

// 多表格支持
const activeTableTab = ref('0')

const currentNoteTables = computed(() => {
  if (!currentNote.value?.table_data) return []
  const td = currentNote.value.table_data
  // 新格式：_tables 数组
  if (td._tables && Array.isArray(td._tables) && td._tables.length > 0) {
    return td._tables
  }
  // 旧格式：单表格
  if (td.headers && td.rows) {
    return [{ name: currentNote.value.section_title, headers: td.headers, rows: td.rows }]
  }
  return []
})

const activeTableData = computed(() => {
  const idx = parseInt(activeTableTab.value) || 0
  return currentNoteTables.value[idx] || currentNoteTables.value[0] || null
})

// 切换章节时重置表格Tab
watch(() => currentNote.value?.note_section, () => {
  activeTableTab.value = '0'
  noteTableStructure.clearHistory()
})

// ─── 附注表格结构编辑 (Req 38.1-38.6) ─────────────────────────────────────
const noteTableStructure = useNoteTableStructure({
  getActiveTable: () => activeTableData.value as TableData | null,
  markDirty: () => { if (editMode.value) { markEditDirty(); autoSave.markDirty() } },
})

// 表格Tab标签：避免显示无意义的"项 目"等表头值
const _GENERIC_NAMES = new Set(['项  目', '项 目', '项目', '类  别', '类别', ''])
function getTableTabLabel(tbl: any, idx: number): string {
  const name = (tbl.name || '').trim()
  if (!name || _GENERIC_NAMES.has(name)) {
    // 用 headers 中第二列（通常是"期末余额"/"本期金额"等）区分
    const headers = tbl.headers || []
    if (headers.length > 1) {
      const h1 = String(headers[1] || '').trim()
      if (h1 && h1.length <= 8) return `表${idx + 1}·${h1}`
    }
    return `表${idx + 1}`
  }
  // 有意义的名称但太长则截断
  return name.length > 12 ? name.slice(0, 12) + '…' : name
}

function getCellValue(row: any, colIdx: number): any {
  const cells = row.cells || row.values || []
  const cell = cells[colIdx]
  if (cell && typeof cell === 'object') return cell.value ?? cell.manual_value ?? 0
  return cell
}

function getCellMode(row: any, colIdx: number): string {
  const cells = row.cells || row.values || []
  const cell = cells[colIdx]
  if (cell && typeof cell === 'object') return cell.mode || 'auto'
  return ''
}

function onCellValueChange(rowIndex: number, colIndex: number, _newValue: number | undefined) {
  markEditDirty()
  autoSave.markDirty()
  if (!currentNote.value?.table_data?.rows) return
  const rows = currentNote.value.table_data.rows
  const totalRowIndex = rows.findIndex((r: any) => r.is_total)
  if (totalRowIndex < 0) return
  // 纵向合计：所有非合计行的同列求和
  let sum = 0
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].is_total) continue
    const vals = rows[i].values || []
    sum += parseFloat(vals[colIndex]) || 0
  }
  if (!rows[totalRowIndex].values) rows[totalRowIndex].values = []
  rows[totalRowIndex].values[colIndex] = sum
  // 横向公式
  recalcHorizontalFormula(rowIndex)
}

function recalcHorizontalFormula(rowIndex: number) {
  const row = currentNote.value?.table_data?.rows?.[rowIndex]
  if (!row || !row.formula_type) return
  if (row.formula_type === 'opening_plus_changes') {
    const vals = row.values || []
    if (vals.length >= 3) {
      const opening = parseFloat(vals[0]) || 0
      let changes = 0
      for (let i = 1; i < vals.length - 1; i++) changes += parseFloat(vals[i]) || 0
      vals[vals.length - 1] = opening + changes
    }
  }
}

function isFormulaMismatch(row: any, colIdx: number): boolean {
  if (!row.is_total || !currentNote.value?.table_data?.rows) return false
  const rows = currentNote.value.table_data.rows
  let expected = 0
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].is_total) continue
    const vals = rows[i].values || []
    expected += parseFloat(vals[colIdx]) || 0
  }
  const actual = parseFloat((row.values || [])[colIdx]) || 0
  return Math.abs(expected - actual) > 0.01
}

// ── 刷新功能（useNoteRefresh composable）──
const {
  refreshLoading, syncError,
  onRefreshFromWP, onManualRefresh, onStaleRecalc,
  showRefreshResultMessage, onWorkpaperSaved,
} = useNoteRefresh({
  projectId,
  year,
  currentNote,
  fetchDetail,
  fetchTree,
  staleRecalc: () => stale.recalc(),
})

async function onFormulaApplied() {
  // 公式应用后刷新当前附注数据
  if (currentNote.value) await fetchDetail(currentNote.value.note_section)
}

// 将当前附注表格数据转为公式管理器需要的行格式
const currentNoteFormulaRows = computed(() => {
  if (!currentNote.value?.table_data?.rows) return []
  return currentNote.value.table_data.rows.map((r: any, i: number) => ({
    id: `note_row_${i}`,
    row_code: `${currentNote.value!.note_section}-R${i + 1}`,
    row_name: r.label || `第${i + 1}行`,
    formula: '',
    formula_category: r.is_total ? 'auto_calc' : '',
    formula_description: r.is_total ? '合计行' : '',
    indent_level: 0,
    is_total_row: r.is_total || false,
  }))
})

function openStructureEditor() {
  if (!currentNote.value) {
    ElMessage.warning('请先选择一个附注章节')
    return
  }
  showStructureEditor.value = true
}

async function onStructureEditorSaved() {
  // 结构化编辑器保存后刷新当前附注数据
  showStructureEditor.value = false
  if (currentNote.value) await fetchDetail(currentNote.value.note_section)
  ElMessage.success('表样编辑已同步')
}

// ─── Sprint 3 Task 3.1/3.4: 自定义模板编辑事件处理 ─────────────────────────

function onStructureEditorAddTable(payload: { name: string; headers: string[] }) {
  // R4.1 验收 30: 加表 UI 收到 payload 后传递给后端持久化由表样编辑器内部完成
  // 此处仅做 UI 反馈（具体写库由 StructureEditor 内部 saveEdits 路径承担）
  ElMessage.success(`已记录新增表「${payload.name}」(${payload.headers.length} 列)`)
}

function onStructureEditorAddColumn(payload: { header: string; semantic: string; bindingDraft: any }) {
  // R4.1 验收 31: 列语义自动生成 binding 草稿，由 StructureEditor 写回 _formulas
  ElMessage.success(`已记录新增列「${payload.header}」(语义：${payload.semantic})`)
}

async function onCustomTemplateRestored(payload: { version: number }) {
  // Sprint 3 Task 3.4: 回滚成功后重新拉树（基线 + 自定义 union 重生成）
  ElMessage.success(`自定义模板已回滚至 v${payload.version}，正在刷新章节树…`)
  await fetchTree()
}

// ─── 章节管理（useNoteSectionManage composable）──────────────────────────────
import { useNoteSectionManage } from '@/views/composables/useNoteSectionManage'
const {
  showAddSectionDialog, addSectionLoading, addSectionForm,
  openAddSectionDialog, onAddSectionConfirm,
  treeContextMenu, onTreeNodeContextMenu, closeTreeContextMenu: _closeTreeContextMenu,
  onTreeCtxRecalc, onTreeCtxDeleteCustom,
} = useNoteSectionManage({ projectId, year, currentNote, fetchTree, fetchDetail, noteStale })

// ── 打印预览 (Req 41.1-41.5) ──
const printPreviewSections = computed(() => {
  if (!noteList.value || noteList.value.length === 0) return []
  return noteList.value.map((node: any) => ({
    title: node.title || node.label || '',
    content: node.text_content || '',
    tables: node.table_data ? [{ html: '<table><tr><td>表格数据</td></tr></table>' }] : [],
  }))
})

function onInsertPageBreak(sectionIndex: number) {
  ElMessage.info('分页符已插入（将在 Word 导出时生效）')
}

async function onClearAllFormulas() {
  // 一键清除公式：将所有 auto 单元格切换为 manual 模式
  if (!currentNote.value?.table_data?.rows) return
  try {
    const { default: http } = await import('@/utils/http')
    await http.post(
      P.disclosureNotes.clearFormulas(projectId.value, year.value, currentNote.value.note_section)
    )
    ElMessage.success('公式已清除，所有单元格切换为手动编辑模式')
    await fetchDetail(currentNote.value.note_section)
  } catch {
    // 降级：前端直接修改模式标记
    for (const row of currentNote.value.table_data.rows) {
      if (row._cell_modes) {
        for (const key of Object.keys(row._cell_modes)) {
          if (row._cell_modes[key] === 'auto') {
            row._cell_modes[key] = 'manual'
          }
        }
      }
    }
    ElMessage.success('公式已清除（本地模式）')
  }
}

async function onRestoreAutoMode() {
  // 恢复自动提数：从底稿重新提取数据并恢复 auto 模式
  if (!currentNote.value) return
  try {
    await refreshDisclosureFromWorkpapers(projectId.value, year.value)
    ElMessage.success('已恢复自动提数模式')
    await fetchDetail(currentNote.value.note_section)
  } catch (e: any) {
    handleApiError(e, '恢复')
  }
}

// ── 导出功能（useNoteExport composable）──
const { exportLoading, onExportWord } = useNoteExport({ projectId, year })

function severityTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { error: 'danger', warning: 'warning', info: 'info' }
  return m[s] || 'info'
}

async function loadProjectTemplateConfig() {
  try {
    const state = await getProjectWizardState(projectId.value)
    const basicInfo = state?.steps?.basic_info?.data || state?.basic_info?.data || {}
    customTemplateId.value = basicInfo.custom_template_id || ''
    customTemplateName.value = basicInfo.custom_template_name || ''
    customTemplateVersion.value = basicInfo.custom_template_version || ''
    templateType.value = basicInfo.template_type || 'soe'
    if (templateType.value === 'custom' && !customTemplateId.value) {
      templateType.value = 'soe'
    }
  } catch {
    templateType.value = 'soe'
    customTemplateId.value = ''
    customTemplateName.value = ''
    customTemplateVersion.value = ''
  }
}

async function onNodeClick(node: TreeNode) {
  // 分组节点不加载详情
  if (node.isGroup || !node.data?.note_section) return
  await withLoading(detailLoading, async () => {
    editMode.value = false
    editDirty.value = false
    try {
      await fetchDetail(node.data.note_section)
    } catch { currentNote.value = null }
  })()
}

async function fetchDetail(noteSection: string) {
  currentNote.value = await getDisclosureNoteDetail(projectId.value, year.value, noteSection)
  textContent.value = currentNote.value.text_content || ''
  if (editor.value) {
    const raw = textContent.value
    if (raw && !raw.startsWith('<')) {
      const html = raw.split(/\n\n+/).filter(Boolean).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('')
      editor.value.commands.setContent(html)
    } else {
      editor.value.commands.setContent(raw)
    }
  }
  // 并行加载上年数据
  try {
    priorYearNote.value = await api.get(
      P.disclosureNotes.priorYear(projectId.value, year.value, noteSection)
    )
  } catch { priorYearNote.value = null }
}

function onNoteImported() {
  showNoteImport.value = false
  fetchTree()
}

async function onGenerate() {
  if (templateType.value === 'custom' && !customTemplateId.value) {
    ElMessage.warning('当前项目未绑定自定义附注模板，请先在项目基本信息中选择')
    return
  }
  const { showGuide } = await import('@/composables/useWorkflowGuide')
  const tplLabel = templateType.value === 'listed' ? '上市版' : '国企版'
  const ok = await showGuide('note_generate', '📝 生成附注',
    `<div style="line-height:1.8;font-size:var(--gt-font-size-sm)"><p>将根据 <b>${tplLabel}</b> 模板生成全部附注章节。</p><p style="color:var(--gt-color-info);font-size:var(--gt-font-size-xs);margin-top:6px">请确认以下准备工作已完成：</p><ul style="padding-left:18px;margin:4px 0"><li>⚠ 已选择正确的模板类型（当前：${tplLabel}）</li><li>⚠ 建议先完成报表生成</li><li>⚠ 如有上年附注，建议先上传到知识库供 AI 参照</li></ul><p style="color:var(--gt-color-success);font-size:var(--gt-font-size-xs);margin-top:6px">✓ 将生成 170+ 个附注章节</p></div>`,
    '开始生成')
  if (!ok) return
  await withLoading(genLoading, async () => {
    try {
      await generateDisclosureNotes(projectId.value, year.value, templateType.value)
      ElMessage.success('附注生成完成')
      await fetchTree()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.response?.data?.message || e?.message || ''
      if (msg) ElMessage.warning('附注生成：' + msg)
    }
  })()
}

// ── 模板切换（已定义在 useNoteTemplate 中但此处保留简化版调用 onGenerate）──
async function handleTemplateChange(value: string) {
  if (value === 'custom' && !customTemplateId.value) {
    ElMessage.warning('当前项目未绑定自定义附注模板，请先在项目基本信息中选择')
    templateType.value = 'soe'
    return
  }
  await onGenerate()
}

const onValidate = withLoading(validateLoading, async () => {
  await validateDisclosureNotes(projectId.value, year.value)
  validationFindings.value = await getValidationResults(projectId.value, year.value)
  ElMessage.success(`校验完成，发现 ${validationFindings.value.length} 项`)
})

// ── 保存功能（useNotePersist composable）──
const { saveLoading, justSaved, onSave } = useNotePersist({
  currentNote,
  textContent,
  editMode,
  clearEditDirty,
  autoSaveClearDirty: () => autoSave.clearDirty(),
  clearAutoSaveDraft,
})

/** 快捷键保存：保存当前附注 */
function onShortcutSave() {
  if (currentNote.value && editMode.value) {
    onSave()
  }
}

// ─── 表格结构编辑操作 (Req 38.1-38.6) ─────────────────────────────────────
const canDeleteRow = computed(() => {
  const table = activeTableData.value
  if (!table) return false
  // Must have at least one non-total row to delete
  return table.rows.some((r: any) => !r.is_total) && table.rows.filter((r: any) => !r.is_total).length > 1
})

const canDeleteColumn = computed(() => {
  const table = activeTableData.value
  if (!table) return false
  // Must have more than 1 value column (headers[0] is label column)
  return table.headers.length > 2
})

function onStructureAddRow() {
  const table = activeTableData.value
  if (!table) return
  // Insert before the last total row, or at end
  const totalIdx = table.rows.findIndex((r: any) => r.is_total)
  const insertIdx = totalIdx >= 0 ? totalIdx : table.rows.length
  noteTableStructure.addRow(insertIdx)
}

function onStructureDeleteRow() {
  const table = activeTableData.value
  if (!table) return
  // Delete the last non-total row
  for (let i = table.rows.length - 1; i >= 0; i--) {
    if (!table.rows[i].is_total) {
      noteTableStructure.deleteRow(i)
      return
    }
  }
}

function onStructureAddColumn() {
  const table = activeTableData.value
  if (!table) return
  const colCount = table.headers.length - 1 // exclude label column
  const name = `列${colCount + 1}`
  noteTableStructure.addColumn(colCount, name)
}

function onStructureDeleteColumn() {
  const table = activeTableData.value
  if (!table) return
  const colCount = table.headers.length - 1
  if (colCount <= 1) return
  noteTableStructure.deleteColumn(colCount - 1)
}

async function onRestoreTemplateStructure() {
  if (!currentNote.value) return
  const section = currentNote.value.note_section
  try {
    const res = await api.get(P.disclosureNotes.templateStructure(projectId.value, year.value, section))
    if (res && res.headers && res.rows) {
      noteTableStructure.restoreTemplateStructure(res as TableData)
      ElMessage.success('已恢复为模板默认结构')
    } else {
      ElMessage.warning('未找到该章节的模板结构')
    }
  } catch (e: any) {
    handleApiError(e, '恢复模板结构')
  }
}

onMounted(async () => {
  selectedProjectId.value = projectId.value
  selectedProjectIdLocal.value = projectId.value
  selectedYear.value = year.value
  projectStore.loadProjectOptions()
  eventBus.on('shortcut:save', onShortcutSave)
  eventBus.on('workpaper:saved', onWorkpaperSaved)
  await loadProjectTemplateConfig()
  await fetchTree()
  // 如果没有附注数据，自动从模板生成
  if (noteList.value.length === 0) {
    await onGenerate()
  }
  // R8-S2-14：关闭浏览器/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)
  // Sprint 3 Task 3.5/3.6: 全局点击关闭右键菜单
  window.addEventListener('click', _closeTreeContextMenu)
  window.addEventListener('contextmenu', _onWindowContextMenuFallback)
})

// V3 Req 5.1：上下文（projectId/year）变化时自动重载附注树
onContextChange(async () => {
  selectedProjectId.value = projectId.value
  selectedProjectIdLocal.value = projectId.value
  selectedYear.value = year.value
  await loadProjectTemplateConfig()
  await fetchTree()
})

onUnmounted(() => {
  eventBus.off('shortcut:save', onShortcutSave)
  eventBus.off('workpaper:saved', onWorkpaperSaved)
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('click', _closeTreeContextMenu)
  window.removeEventListener('contextmenu', _onWindowContextMenuFallback)
})

// 右键菜单点开后，再次右键于其他位置 → 关闭旧菜单（el-tree 已自行 emit
// node-contextmenu 重新打开）
function _onWindowContextMenuFallback(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  if (!target) return
  // 树节点上不关闭（el-tree 节点会触发 node-contextmenu 重新定位）
  if (target.closest('.el-tree-node')) return
  // 菜单内不关闭
  if (target.closest('.gt-de-tree-ctx-menu')) return
  _closeTreeContextMenu()
}

// R8-S2-14：未保存拦截
onBeforeRouteLeave(async (_to, _from, next) => {
  if (!editDirty.value && !autoSave.isDirty.value) { next(); return }
  try {
    await confirmLeave('附注')
    next()
  } catch {
    next(false)
  }
})

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (editDirty.value || autoSave.isDirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

// ─── 全屏与复制 ──────────────────────────────────────────────────────────────
const { isFullscreen: deFullscreen, toggleFullscreen: toggleDeFullscreen } = useFullscreen()

function copyNoteTable() {
  const note = currentNote.value
  if (!note?.table_data?.rows?.length) { ElMessage.warning('当前章节无表格数据'); return }
  const headers = note.table_data.headers || []
  const rows = note.table_data.rows || []
  const text = [headers.join('\t'), ...rows.map((r: any) => (r.values || []).join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map((h: string) => `<th>${h}</th>`).join('')}</tr>${rows.map((r: any) => `<tr>${(r.values || []).map((v: any) => `<td>${v ?? ''}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${rows.length} 行，可粘贴到 Word/Excel`)
  } catch { navigator.clipboard?.writeText(text); ElMessage.success('已复制') }
}

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
const deCtx = useCellSelection()
const penetrate = usePenetrate()
const deTableRef = ref<any>(null)
deCtx.setupTableDrag(deTableRef, (rowIdx: number, colIdx: number) => {
  const tableRows = activeTableData.value?.rows || []
  const row = tableRows[rowIdx]
  if (!row) return null
  if (colIdx === 0) return row.label || row[0]
  const values = row.values || row.cells || []
  return values[colIdx - 1] ?? null
})
const deComments = useCellComments(() => projectId.value, () => year.value, 'disclosure')

const displayPrefs = useDisplayPrefsStore()

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const deSearch = useTableSearch(
  computed(() => (activeTableData.value?.rows || []) as any[]),
  ['label']
)

function deCellClassName({ rowIndex, columnIndex }: any) {
  const classes: string[] = []
  const selClass = deCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  const sec = activeTableData.value
  const sheetKey = sec?.section_id || currentNote.value?.note_section || 'default'
  const ccClass = deComments.commentCellClass(sheetKey, rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

function onDeCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  deCtx.closeContextMenu()
  const tableRows = activeTableData.value?.rows || []
  const rowIdx = tableRows.indexOf(row)
  const headers = activeTableData.value?.headers || []
  const colIdx = headers.indexOf(column.label)
  if (rowIdx < 0 || colIdx < 0) return
  const values = row.values || row.cells || []
  const value = values[colIdx] ?? ''
  deCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
  deCtx.contextMenu.itemName = values[0] || `行${rowIdx + 1}`
}

function onDeCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const tableRows = activeTableData.value?.rows || []
  const rowIdx = tableRows.indexOf(row)
  const headers = activeTableData.value?.headers || []
  const colIdx = headers.indexOf(column.label)
  // 如果右键点击的单元格已在选区内，保持选区不变
  if (rowIdx >= 0 && colIdx >= 0 && !deCtx.isCellSelected(rowIdx, colIdx)) {
    const values = row.values || row.cells || []
    const value = values[colIdx] ?? ''
    deCtx.selectCell(rowIdx, colIdx, value, false)
    deCtx.contextMenu.itemName = values[0] || `行${rowIdx + 1}`
  }
  deCtx.openContextMenu(event, deCtx.contextMenu.itemName)
}

function onDeCtxCopy() {
  deCtx.closeContextMenu()
  deCtx.copySelectedValues()
  ElMessage.success('已复制')
}

function onDeCtxFormula() {
  deCtx.closeContextMenu()
  showNoteFormulaManager.value = true
}

// V3 Req 9.6: 数字信任度
const trustScorePanelRef = ref<InstanceType<typeof TrustScorePanel> | null>(null)

// V3 Req 10.4: 可解释状态机
const smPanelRef = ref<InstanceType<typeof StatusMachinePanel> | null>(null)
const disclosureInstanceId = ref('')

// V3 Req 11.6: 时光机
const tmDrawerRef = ref<InstanceType<typeof TimeMachineDrawer> | null>(null)
function onTimeMachineRestored(_snap: any) {
  window.location.reload()
}

function onDeCtxTrustScore() {
  deCtx.closeContextMenu()
  const section = currentNote.value?.note_section || ''
  const cell = deCtx.contextMenu.rowData ? `row${deCtx.selectedCells.value[0]?.row || 0}` : ''
  const context = `note:${section}|${cell}`
  trustScorePanelRef.value?.open(context)
}

function onDeCtxSum() {
  deCtx.closeContextMenu()
  const sum = deCtx.sumSelectedValues()
  ElMessage.info(`选中 ${deCtx.selectedCells.value.length} 格，合计：${fmtAmount(sum)}`)
}

function onDeCtxCompare() {
  deCtx.closeContextMenu()
  if (deCtx.selectedCells.value.length < 2) return
  const vals = deCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  ElMessage.info(`差异：${fmtAmount(diff)}`)
}

// ─── 单元格右键动作（useNoteCellActions composable）─────────────────────────
import { useNoteCellActions } from '@/views/composables/useNoteCellActions'
const {
  showCellFormulaDetail, cellDetailWpCode, cellDetailSheet, cellDetailLabel,
  consolBreakdownVisible, consolBreakdownSectionId,
  showCellTrace, cellTraceCtx,
  tracePopoverVisible, traceLoading, traceData, tracePopoverPos,
  onDeCtxRelatedWp, onDeCtxPenetrateToLedger, onDeCtxViewDataSource,
  onDeCtxViewConsolBreakdown, onDeCtxOpenCellTrace, onCellTracePenetrateTb,
  onCellDetailNavigate, onAutoCellTraceClick, onTraceJumpToTB,
} = useNoteCellActions({ projectId, year, currentNote, activeTableData, deCtx, router, route })

// ─── 校验错误标记（左侧目录树红色标记 + 单元格红色边框） ─────────────────────
/** 判断某章节是否有校验错误 */
function hasSectionValidationError(noteSection: string | undefined): boolean {
  if (!noteSection || !validationFindings.value.length) return false
  return validationFindings.value.some(f => f.note_section === noteSection && f.severity === 'error')
}

/** 获取分组节点下的校验错误数量 */
function getGroupValidationErrorCount(groupNode: any): number {
  if (!validationFindings.value.length) return 0
  const sections = new Set<string>()
  function collectSections(node: any) {
    if (node.data?.note_section) sections.add(node.data.note_section)
    if (node.children) node.children.forEach(collectSections)
  }
  collectSections(groupNode)
  return validationFindings.value.filter(f => sections.has(f.note_section) && f.severity === 'error').length
}

/** 获取单元格的校验错误信息（用于 tooltip） */
function getCellValidationError(rowIndex: number, colIndex: number): string {
  if (!currentNote.value || !validationFindings.value.length) return ''
  const section = currentNote.value.note_section
  // 匹配当前章节的校验错误，检查是否有针对特定行列的错误
  const findings = validationFindings.value.filter(f => f.note_section === section && f.severity === 'error')
  if (!findings.length) return ''
  // 对合计行（最后一行或 is_total）显示余额类校验错误
  const rows = activeTableData.value?.rows || []
  const row = rows[rowIndex]
  if (row?.is_total) {
    const balanceFinding = findings.find(f => f.check_type === '余额' || f.check_type === '其中项')
    if (balanceFinding) {
      const expected = balanceFinding.expected_value ?? '-'
      const actual = balanceFinding.actual_value ?? '-'
      return `${balanceFinding.message}（期望: ${expected}, 实际: ${actual}）`
    }
  }
  // 对宽表行检查横向公式错误
  if (row?.formula_type === 'opening_plus_changes') {
    const wideFinding = findings.find(f => f.check_type === '宽表')
    if (wideFinding) {
      return `${wideFinding.message}`
    }
  }
  return ''
}
</script>

<style scoped>
@import './DisclosureEditor.css';
</style>

<!-- 全局样式：teleport 到 body 的右键菜单脱离 scoped 作用域 -->
<style>
.gt-de-tree-ctx-menu { position: fixed; z-index: 9999; background: var(--gt-color-bg-white, #fff); border: 1px solid var(--gt-color-border-purple, #d8caee); border-radius: 6px; box-shadow: 0 4px 16px rgba(75, 45, 119, 0.18); padding: 4px 0; min-width: 160px; font-size: var(--gt-font-size-xs, 12px); }
.gt-de-tree-ctx-item { padding: 6px 14px; cursor: pointer; color: var(--gt-color-text-primary, #303133); white-space: nowrap; user-select: none; }
.gt-de-tree-ctx-item:hover { background: var(--gt-color-primary-bg, #f5f0ff); }
.gt-de-tree-ctx-item.gt-de-tree-ctx-danger { color: var(--gt-color-coral, #e6443e); }
.gt-de-tree-ctx-item.gt-de-tree-ctx-danger:hover { background: var(--gt-bg-danger, #fdecea); }
</style>


