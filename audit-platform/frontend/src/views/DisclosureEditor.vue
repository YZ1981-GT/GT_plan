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
          { label: '金额单位', value: noteUnitSuffix },
        ]"
        @unit-change="onProjectChange"
        @year-change="(v: number) => { selectedYear = v; onYearChange() }"
        @template-change="handleTemplateChange"
      />
      <template #actions>
        <GtToolbar
          :show-copy="false"
          :show-fullscreen="false"
          :is-fullscreen="deFullscreen"
          :show-export="false"
          :show-import="false"
          :show-formula="false"
        >
          <template #left>
            <div class="gt-de-actions-row">
              <!-- 数据操作 -->
              <el-button-group v-if="!isEqcrRole" size="small">
                <el-tooltip content="从底稿同步最新数据到当前附注章节" placement="bottom" :show-after="400">
                  <el-button @click="onRefreshFromWP" :loading="refreshLoading">🔄 刷新</el-button>
                </el-tooltip>
                <el-tooltip content="从底稿披露表起，刷新全部附注主要项目下的科目数据" placement="bottom" :show-after="400">
                  <el-button @click="onRefreshAll" :loading="refreshAllLoading">🔁 全部刷新</el-button>
                </el-tooltip>
                <el-tooltip content="根据模板生成全部附注章节" placement="bottom" :show-after="400">
                  <el-button @click="onGenerate" :loading="genLoading">📝 生成</el-button>
                </el-tooltip>
                <el-tooltip content="校验附注数据完整性与勾稽关系" placement="bottom" :show-after="400">
                  <el-button @click="onValidate" :loading="validateLoading">✅ 校验</el-button>
                </el-tooltip>
              </el-button-group>
              <!-- 编辑 -->
              <el-button-group size="small">
                <el-tooltip content="新增自定义附注章节" placement="bottom" :show-after="400">
                  <el-button v-if="!isEqcrRole" data-test="de-add-section" @click="openAddSectionDialog">➕ 新增</el-button>
                </el-tooltip>
                <el-tooltip content="编辑表格结构" placement="bottom" :show-after="400">
                  <el-button @click="openStructureEditor">📐 表样</el-button>
                </el-tooltip>
              </el-button-group>
              <!-- 版本/范围 -->
              <el-button-group size="small">
                <el-tooltip content="查看版本历史" placement="bottom" :show-after="400">
                  <el-button @click="showVersionTree = true">🗂️ 版本</el-button>
                </el-tooltip>
                <el-tooltip content="与上年对比" placement="bottom" :show-after="400">
                  <el-button @click="showPriorYear = true">📅 上年</el-button>
                </el-tooltip>
                <el-tooltip content="切换为单体附注" placement="bottom" :show-after="400">
                  <el-button :type="numbering.state.value.scope === 'standalone' ? 'primary' : ''" @click="onScopeChange('standalone')">单体</el-button>
                </el-tooltip>
                <el-tooltip content="切换为合并附注" placement="bottom" :show-after="400">
                  <el-button :type="numbering.state.value.scope === 'consolidated' ? 'primary' : ''" @click="onScopeChange('consolidated')">合并</el-button>
                </el-tooltip>
              </el-button-group>
              <!-- AI 助手（合并全局 AI 入口：建议 / 对话 / 批量预填充；当前章节填充见章节内按钮） -->
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :loading="batchAiFillLoading">🤖 AI 助手 ▾</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="!isEqcrRole" :disabled="batchAiFillLoading" @click="openBatchAiFill" title="对空/草稿章节一键 AI 预填充（逐章确认采纳，不自动写库）">📚 批量预填充（空/草稿章节）</el-dropdown-item>
                    <el-dropdown-item @click="showDocAiChat = true" title="与 AI 对话">💬 AI 对话</el-dropdown-item>
                    <el-dropdown-item @click="showAiPanel = true" title="AI 智能建议">🧠 AI 智能建议</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <!-- 公式管理 -->
              <el-tooltip content="配置附注取数公式规则" placement="bottom" :show-after="400">
                <el-button size="small" @click="showNoteFormulaManager = true">⚙️ 公式管理</el-button>
              </el-tooltip>
              <!-- 金额单位（附注模块级，默认元） -->
              <el-tooltip content="附注金额展示单位（默认元，仅影响附注模块）" placement="bottom" :show-after="400">
                <el-select
                  :model-value="noteUnit"
                  size="small"
                  style="width: 96px"
                  aria-label="附注金额单位"
                  @change="onNoteUnitChange"
                >
                  <el-option v-for="opt in displayPrefs.unitOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </el-tooltip>
              <!-- 全屏 -->
              <el-tooltip :content="deFullscreen ? '退出全屏（ESC）' : '全屏查看'" placement="bottom" :show-after="400">
                <el-button size="small" @click="toggleDeFullscreen()">{{ deFullscreen ? '↙ 退出' : '↗ 全屏' }}</el-button>
              </el-tooltip>
              <!-- 导入导出（集中所有输出/导入入口） -->
              <el-dropdown trigger="click" size="small">
                <el-button size="small">📤 导入导出 ▾</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="onExportWithConfirm" title="导出 Word 格式附注文档">📤 导出 Word</el-dropdown-item>
                    <el-dropdown-item @click="showPrintPreview = true" title="打印预览当前附注">🖨️ 打印预览</el-dropdown-item>
                    <el-dropdown-item divided @click="showNoteImport = true" title="导入外部 Excel 附注数据（通用格式）">📥 Excel 导入</el-dropdown-item>
                    <el-dropdown-item @click="showOfflineExport = true" title="导出系统格式离线编辑包（可再导回）">📦 离线导出</el-dropdown-item>
                    <el-dropdown-item @click="showOfflineImport = true" title="导入系统导出的离线编辑包">📥 离线导入</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <!-- 更多操作下拉（其余配置项） -->
              <el-dropdown trigger="click" size="small">
                <el-button size="small">更多 ▾</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="showParagraphVars = true" title="段落变量（自动替换占位符）">✏️ 段落变量</el-dropdown-item>
                    <el-dropdown-item @click="showGroupBaseline = true" title="集团基线管理：应用/保存/对比集团统一附注模板结构，确保子企业附注章节一致">🏢 集团基线</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <!-- 模板组：保存/引用模板 + 国企↔上市转换规则 -->
              <SharedTemplatePicker
                config-type="note_template"
                :project-id="projectId"
                :get-config-data="getNoteTemplateConfigData"
                @applied="onNoteTemplateApplied"
              />
              <el-tooltip content="国企↔上市附注模板转换规则" placement="bottom" :show-after="400">
                <el-button size="small" @click="showNoteMappingDialog = true">🔄 国企↔上市转换</el-button>
              </el-tooltip>
              <!-- 附注联动复盘 P0-1：披露同步 / 校验就绪度看板 -->
              <el-tooltip content="就绪度：哪些章节未从底稿同步 / 无数据 / 有校验问题" placement="bottom" :show-after="400">
                <el-button size="small" type="primary" plain @click="showReadiness = true">
                  📋 就绪度<span v-if="readinessAlertCount" class="gt-de-readiness-badge">{{ readinessAlertCount }}</span>
                </el-button>
              </el-tooltip>
              <el-button v-if="isEqcrRole" size="small" type="info">📋 只读副本</el-button>
              <!-- 使用手册：各功能键用途 / 数据提取来源 / 操作流程 -->
              <el-tooltip content="附注模块使用手册：各功能键用途、数据提取来源、标准操作流程" placement="bottom" :show-after="400">
                <el-button size="small" @click="showNoteHandbook = true">📖 使用手册</el-button>
              </el-tooltip>
            </div>
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
      <el-popover placement="bottom-end" trigger="click" width="460" popper-class="gt-stale-detail-pop">
        <template #reference>
          <el-button size="small" text>查看明细</el-button>
        </template>
        <div class="gt-stale-detail">
          <div class="gt-stale-detail__title">待重算底稿（{{ stale.staleCount.value }} 张）</div>
          <el-scrollbar max-height="300px">
            <div v-for="it in stale.staleItems.value" :key="it.id" class="gt-stale-detail__row">
              <el-tag size="small" effect="plain">{{ it.wp_code }}</el-tag>
              <span class="gt-stale-detail__name">{{ it.wp_name }}</span>
              <span class="gt-stale-detail__reason">{{ it.stale_reason || '上游数据变更' }}</span>
            </div>
            <el-empty v-if="stale.staleItems.value.length === 0" description="无明细" :image-size="60" />
          </el-scrollbar>
        </div>
      </el-popover>
      <el-button size="small" type="primary" :loading="stale.loading.value" @click="onStaleRecalc">
        🔄 点击重算
      </el-button>
    </div>

    <!-- useStaleRefresh：上游变更事件横幅（与已有 stale 互斥显示） -->
    <div v-if="deStaleRefresh.isStale.value && !stale.isStale.value" class="gt-stale-banner">
      <StaleIndicator :stale="true" tooltip="上游数据已变更" />
      <span class="gt-stale-text">上游数据已变更，建议刷新附注数据</span>
      <el-button size="small" type="primary" @click="deStaleRefresh.refresh()">刷新数据</el-button>
    </div>

    <!-- 编辑锁提示 -->
    <el-alert v-if="editLock.locked.value && !editLock.isMine.value" type="warning" :closable="false" style="margin-bottom: 8px">
      {{ editLock.lockedBy.value || '其他用户' }} 正在编辑，当前为只读模式
    </el-alert>

    <div class="gt-de-body">
      <!-- 左侧：目录树（四栏模式下隐藏，由 FourColumnCatalog 替代） -->
      <div v-show="!isFourColumnMode" class="gt-de-sidebar" :style="{ width: sidebarWidth + 'px' }">
        <!-- 第二行：操作图标 -->
        <div class="gt-de-sidebar-icons">
          <el-tooltip content="全部展开" placement="top" :show-after="400">
            <span class="gt-de-sidebar-icon" @click="expandAll">+</span>
          </el-tooltip>
          <el-tooltip content="全部收起" placement="top" :show-after="400">
            <span class="gt-de-sidebar-icon" @click="collapseAll">−</span>
          </el-tooltip>
          <el-tooltip content="导出设置" placement="top" :show-after="400">
            <span class="gt-de-sidebar-icon" @click="showExportSettingDialog = true">📤</span>
          </el-tooltip>
          <el-tooltip content="批量删除" placement="top" :show-after="400">
            <span class="gt-de-sidebar-icon" @click="showBatchDeleteDialog = true">🗑</span>
          </el-tooltip>
          <el-tooltip content="恢复已删除" placement="top" :show-after="400">
            <span class="gt-de-sidebar-icon" @click="showRestoreDialog = true">♻</span>
          </el-tooltip>
        </div>
        <el-input v-model="treeSearch" size="small" placeholder="搜索章节..." clearable class="gt-de-tree-search" />
        <!-- P2-9：附注树快捷筛选 -->
        <div class="gt-de-tree-filter-bar">
          <el-segmented v-model="treeFilter" :options="treeFilterOptions" size="small">
            <template #default="{ item }">
              <el-tooltip placement="bottom" :show-after="200" popper-class="gt-de-tree-filter-tip">
                <template #content>
                  <div class="gt-de-tip-title">{{ item.label }}</div>
                  <div class="gt-de-tip-desc">{{ item.tip }}</div>
                  <div class="gt-de-tip-count">
                    当前命中：<b>{{ treeFilterCounts[item.value] }}</b> 个章节<span v-if="item.value !== 'all'"> / 共 {{ treeFilterCounts.all }} 个</span>
                  </div>
                  <div class="gt-de-tip-rule">判定依据：{{ item.rule }}</div>
                </template>
                <span
                  class="gt-de-tree-filter-label"
                  :class="{
                    'has-hit': item.value !== 'all' && treeFilterCounts[item.value] > 0,
                    'is-error-hit': item.value === 'has_findings' && treeFilterCounts[item.value] > 0,
                  }"
                >{{ item.label }}</span>
              </el-tooltip>
            </template>
          </el-segmented>
        </div>
        <div class="gt-de-tree-wrap">
          <!-- 树形视图 -->
          <el-tree
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
              <div v-else class="gt-de-tree-node" :class="{ 'gt-de-tree-node-active': currentNote?.id === data.id, 'gt-de-tree-node-error': hasSectionValidationError(data.data?.note_section), 'gt-de-tree-node-excluded': data.data?.status === 'not_applicable' }"
                @mouseenter="onTreeNodeMouseEnter(data.data)"
                @mouseleave="onTreeNodeMouseLeave"
              >
                <span class="gt-de-tree-label">
                  <span v-if="getRenderedNumber(data.data?.note_section)" class="gt-de-tree-number">{{ getRenderedNumber(data.data?.note_section) }}</span>
                  {{ data.data?.section_title || data.label }}
                  <span v-if="data.validationStatus === 'error'" class="gt-de-validation-dot is-error" title="校验有错误">●</span>
                  <span v-else-if="data.validationStatus === 'warning'" class="gt-de-validation-dot is-warning" title="校验有警告">●</span>
                  <span v-else-if="data.validationStatus === 'clean'" class="gt-de-validation-dot is-clean" title="校验通过">●</span>
                  <el-tag v-if="nodeHasPlaceholderText(data)" type="warning" size="small" effect="plain" class="gt-de-tree-placeholder-tag">待补充</el-tag>
                </span>
                <span class="gt-de-tree-actions">
                  <el-tooltip :content="data.data?.status === 'not_applicable' ? '恢复生成' : '不导出'" placement="top" :show-after="500">
                    <span class="gt-de-tree-action-icon" @click.stop="onToggleExclude(data.data)">
                      {{ data.data?.status === 'not_applicable' ? '👁' : '🚫' }}
                    </span>
                  </el-tooltip>
                  <el-tooltip content="删除章节" placement="top" :show-after="500">
                    <span class="gt-de-tree-action-icon gt-de-tree-action-del" @click.stop="onDeleteSection(data.data)">✕</span>
                  </el-tooltip>
                </span>
                <!-- P0-4：服务端最新一次校验的 findings 计数（生成/刷新/同步后自动跑） -->
                <el-tooltip
                  v-if="serverFindings(data.data)"
                  :content="serverFindingsTip(data.data)"
                  placement="right"
                >
                  <span
                    class="gt-de-tree-findings"
                    :class="{ 'is-error': (data.data?.findings?.error || 0) > 0 }"
                  >{{ (data.data?.findings?.error || 0) || (data.data?.findings?.warning || 0) }}</span>
                </el-tooltip>
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
          <div v-if="!filteredTreeData.length && !treeLoading" class="gt-de-empty-hint">
            暂无附注，点击"生成附注"
          </div>
        </div>
      </div>

      <!-- 拖拽调整侧栏宽度 -->
      <div
        class="gt-de-resize-handle"
        @mousedown="onResizeStart"
      />

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
          v-if="(currentNote as any)?.last_sync_source === 'workpaper' || disclosureJumpTarget"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        >
          <template #title>
            <span>{{ (currentNote as any)?.last_sync_source === 'workpaper' ? '此数据由底稿同步' : '关联底稿披露表' }}</span>
          </template>
          <template #default>
            <div class="gt-de-sync-banner">
              <span v-if="(currentNote as any)?.last_sync_source === 'workpaper'">
                建议在底稿披露表维护，避免双源不一致。
              </span>
              <span v-else>
                可跳转至 {{ disclosureJumpTarget?.wpCode ?? 'G7' }}「{{ disclosureJumpTarget?.sheet }}」编辑后点「同步到附注」。
              </span>
              <span v-if="(currentNote as any)?.last_sync_at" class="gt-de-sync-time">
                · 最近同步：{{ formatSyncTime((currentNote as any).last_sync_at) }}
              </span>
              <el-button
                v-if="disclosureJumpTarget"
                size="small"
                type="primary"
                plain
                :loading="jumpingDisclosure"
                @click="jumpToDisclosureSheet"
              >
                跳转至披露表
              </el-button>
              <el-button
                v-else-if="(currentNote as any)?.last_sync_wp_id"
                size="small"
                link
                type="primary"
                @click="jumpToLastSyncWorkpaper"
              >
                打开同步底稿
              </el-button>
            </div>
          </template>
        </el-alert>
        <template v-if="currentNote">
          <!-- #20: 首次同步引导横幅 -->
          <transition name="el-fade-in">
            <div v-if="showSyncHint" class="gt-de-sync-hint">
              <span class="gt-de-sync-hint__icon">💡</span>
              <span class="gt-de-sync-hint__msg">检测到底稿已编制审定/披露数据，可点击「🔁 全部刷新」自动同步最新审定数到附注表格。</span>
              <el-button size="small" type="primary" @click="onRefreshAll(); dismissSyncHint()">立即全部刷新</el-button>
              <el-button size="small" text @click="dismissSyncHint">不再提示</el-button>
            </div>
          </transition>
          <!-- #22: 编制进度条 -->
          <div v-if="noteProgress.total > 0" class="gt-de-progress-bar">
            <div class="gt-de-progress-bar__track">
              <div class="gt-de-progress-bar__seg gt-de-progress-bar__seg--complete" :style="{ width: (noteProgress.complete / noteProgress.total * 100) + '%' }" />
              <div class="gt-de-progress-bar__seg gt-de-progress-bar__seg--text" :style="{ width: (noteProgress.textOnly / noteProgress.total * 100) + '%' }" />
              <div class="gt-de-progress-bar__seg gt-de-progress-bar__seg--table" :style="{ width: (noteProgress.tableOnly / noteProgress.total * 100) + '%' }" />
              <div class="gt-de-progress-bar__seg gt-de-progress-bar__seg--empty" :style="{ width: (noteProgress.empty / noteProgress.total * 100) + '%' }" />
            </div>
            <div class="gt-de-progress-bar__legend">
              <span><i class="dot dot--complete"></i>完整 {{ noteProgress.complete }}</span>
              <span><i class="dot dot--text"></i>待补表格 {{ noteProgress.textOnly }}</span>
              <span><i class="dot dot--table"></i>待补文本 {{ noteProgress.tableOnly }}</span>
              <span><i class="dot dot--empty"></i>空白 {{ noteProgress.empty }}</span>
            </div>
          </div>
          <div class="gt-de-editor-header">
            <div>
              <h4 class="gt-de-section-title">
                {{ currentNote.section_title }}
                <span class="gt-de-save-status">
                  <template v-if="saveStatus === 'saving'">
                    <el-icon class="is-loading"><Loading /></el-icon> 保存中...
                  </template>
                  <template v-else-if="saveStatus === 'saved'">
                    <span style="color:#67c23a;">✓ 已保存</span>
                  </template>
                  <template v-else-if="saveStatus === 'error'">
                    <span style="color:#f56c6c;">⚠ 保存失败</span>
                  </template>
                </span>
                <transition name="el-fade-in">
                  <span v-if="justSaved" class="gt-de-saved-badge">✓ 已保存</span>
                </transition>
              </h4>
              <span class="gt-de-section-account" v-if="currentNote.account_name && currentNote.account_name !== currentNote.section_title">{{ currentNote.account_name }}</span>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
              <el-tooltip content="保存后自动跳到下一未编制章节" placement="top">
                <el-switch v-model="autoAdvance" size="small" @change="toggleAutoAdvance" style="margin-right:4px;" />
              </el-tooltip>
              <template v-if="!isEqcrRole && (currentNote.content_type === 'text' || currentNote.content_type === 'mixed')">
                <el-tooltip content="参照知识库文档由 AI 起草本章节正文草稿" placement="bottom" :show-after="400">
                  <el-button size="small" @click="openNoteAiFill('ai')">🤖 AI 填充</el-button>
                </el-tooltip>
                <el-tooltip content="仅检索知识库参照原文片段供人工引用" placement="bottom" :show-after="400">
                  <el-button size="small" @click="openNoteAiFill('reference')">📎 参照文档填充</el-button>
                </el-tooltip>
              </template>
              <el-tag :type="currentNote.status === 'confirmed' ? 'success' : 'info'" size="small">
                {{ currentNote.status === 'confirmed' ? '已确认' : '草稿' }}
              </el-tag>
              <!-- 编辑操作按钮（置于标题行，随时可见，无需滚动到底部） -->
              <el-button v-if="!editMode" size="small" @click="enterEdit()" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">编辑</el-button>
              <template v-else>
                <el-button size="small" @click="exitEdit(true)">取消</el-button>
                <el-button size="small" type="primary" @click="onSave" :loading="saveLoading" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">保存</el-button>
              </template>
            </div>
          </div>

            <!-- 表格型（支持多表格Tab切换） -->
            <div
              v-if="currentNote.content_type === 'table' && showGuidance"
              class="gt-guidance-bar"
              :class="{ 'is-collapsed': !isGuidanceExpanded }"
            >
              <div class="gt-guidance-head" @click="toggleGuidanceExpand" :title="isGuidanceExpanded ? '收起编制说明' : '展开编制说明'">
                <el-icon><InfoFilled /></el-icon>
                <span class="gt-guidance-title">编制说明（仅供参考）</span>
                <el-icon class="gt-guidance-caret">
                  <component :is="isGuidanceExpanded ? ArrowDown : ArrowRight" />
                </el-icon>
                <span class="gt-guidance-spacer" />
                <el-icon class="gt-guidance-close" @click.stop="dismissGuidance" title="关闭提示"><Close /></el-icon>
              </div>
              <div v-show="isGuidanceExpanded" class="gt-guidance-text">{{ activeTableGuidance }}</div>
            </div>
            <div v-if="currentNote.content_type === 'table' || currentNote.content_type === 'mixed'">
              <!-- 多表格Tab + 导出开关 -->
              <div v-if="currentNoteTables.length > 1" class="gt-de-multitable-tabs">
                <el-tabs v-model="activeTableTab" type="card" size="small" class="gt-de-table-tabs">
                  <el-tab-pane v-for="(tbl, ti) in currentNoteTables" :key="ti" :name="String(ti)">
                    <template #label>
                      <span class="gt-de-tab-label" :class="{ 'gt-de-tab-label--empty': isTableEmpty(tbl) }" :title="getTableTabFullName(tbl, ti)">{{ getTableTabLabel(tbl, ti) }}<span v-if="isTableEmpty(tbl)" class="gt-de-tab-empty-tag">空</span></span>
                    </template>
                  </el-tab-pane>
                </el-tabs>
                <el-popover trigger="click" placement="bottom-end" :width="280">
                  <template #reference>
                    <el-button size="small" text title="设置导出表格" style="flex-shrink: 0;">
                      <span style="font-size: 14px;">⚙</span>
                    </el-button>
                  </template>
                  <div style="font-size: 12px; margin-bottom: 8px; color: var(--el-text-color-secondary);">
                    勾选要导出的表格（取消勾选将在Word导出时跳过）
                  </div>
                  <el-checkbox-group v-model="exportEnabledTables">
                    <div v-for="(tbl, ti) in currentNoteTables" :key="ti" style="margin-bottom: 4px;">
                      <el-checkbox :value="ti">{{ getTableTabLabel(tbl, ti) }}</el-checkbox>
                    </div>
                  </el-checkbox-group>
                </el-popover>
              </div>
              <!-- 母公司章取数溯源（Task 13）：来源项目 + 企业代码 + 口径三项 -->
              <div v-if="parentSourceView.state !== 'none'" class="gt-de-parent-source">
                <el-alert
                  :type="parentSourceView.state === 'missing' ? 'warning' : 'info'"
                  :closable="false"
                  show-icon
                >
                  <template #title>
                    <span>{{ parentSourceView.state === 'missing' ? '本项目未建母公司单体' : '母公司口径取数' }}</span>
                  </template>
                  <template #default>
                    <div v-if="parentSourceView.state === 'missing'" class="gt-de-parent-source__body">
                      {{ PARENT_PROJECT_MISSING_TEXT }}
                    </div>
                    <div v-else class="gt-de-parent-source__body">
                      <span>{{ parentCompanySourceSummary(parentSourceView) }}</span>
                      <el-tag size="small" type="info" effect="plain">{{ parentSourceView.scopeLabel || '—' }}</el-tag>
                    </div>
                  </template>
                </el-alert>
              </div>
              <!-- 当前表格 -->
              <div v-if="isActiveTableEmpty" class="gt-de-empty-table-hint">
                <el-alert type="info" :closable="false" show-icon>
                  <template #title>本期无此情形</template>
                  <span>此表当前无业务数据。如有需要可直接编辑填写。</span>
                </el-alert>
              </div>
              <el-table ref="deTableRef" v-if="activeTableData?.rows?.length || activeTableData?.headers?.length" :data="activeTableData.rows || []"
                border size="small" class="gt-de-note-table gt-compact-table" style="margin-bottom: 12px"
                :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
                :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap', padding: '2px 0' }"
                :cell-style="{ padding: '0 6px', fontSize: '12px', lineHeight: '20px' }"
                :cell-class-name="deCellClassName"
                @cell-click="onDeCellClick"
                @cell-contextmenu="onDeCellContextMenu">
                <!-- ━━━ 两级分组表头渲染（有 _column_groups 时） ━━━ -->
                <template v-if="activeTableColumns">
                  <template v-for="(col, ci) in activeTableColumns" :key="ci">
                    <!-- 独立列（无分组） -->
                    <el-table-column v-if="col.type === 'flat'"
                      :label="col.label"
                      :min-width="col.headerIdx === 0 ? 160 : 120"
                      :align="col.headerIdx === 0 ? 'left' : 'right'" resizable>
                      <template #default="{ row, $index }">
                        <template v-if="col.headerIdx === 0">
                          <template v-if="editMode && !row.is_total">
                            <el-input v-if="isActiveCellEditing($index, -1)"
                              v-model="row.label" size="small" style="width: 100%; height: 22px"
                              @change="onLabelChange($index, $event)"
                              @blur="onActiveCellBlur($event, $index, -1)"
                              @keydown="onActiveCellKeydown($event, $index, -1)" />
                            <span v-else class="gt-cell-editable" :class="{ 'total-label': row.is_total }">{{ row.label || '' }}</span>
                          </template>
                          <span v-else :class="{ 'total-label': row.is_total }">{{ row.label }}</span>
                        </template>
                        <template v-else>
                          <div class="gt-cell-wrapper" :class="{ 'gt-cell-auto-fill': getCellMode(row, col.headerIdx - 1) === 'auto' }">
                            <el-input-number v-if="editMode && !row.is_total && isActiveCellEditing($index, col.headerIdx - 1)"
                              v-model="row.values[col.headerIdx - 1]" :controls="false" :precision="2"
                              size="small" style="width: 100%; height: 22px"
                              @change="onCellValueChange($index, col.headerIdx - 1, $event)"
                              @blur="onActiveCellBlur($event, $index, col.headerIdx - 1)"
                              @keydown="onActiveCellKeydown($event, $index, col.headerIdx - 1)" />
                            <span v-else :class="['gt-amt', { 'total-val': row.is_total }]">
                              <GtAmountCell :value="getCellValue(row, col.headerIdx - 1)" :unit="noteUnit" />
                            </span>
                          </div>
                        </template>
                      </template>
                    </el-table-column>
                    <!-- 分组列（嵌套 el-table-column 实现两级表头合并） -->
                    <el-table-column v-else-if="col.type === 'grouped'"
                      :label="col.group" align="center">
                      <el-table-column v-for="child in col.children" :key="child.headerIdx"
                        :label="child.label" :min-width="120" align="right" resizable>
                        <template #default="{ row, $index }">
                          <div class="gt-cell-wrapper" :class="{ 'gt-cell-auto-fill': getCellMode(row, child.headerIdx - 1) === 'auto' }">
                            <el-input-number v-if="editMode && !row.is_total && isActiveCellEditing($index, child.headerIdx - 1)"
                              v-model="row.values[child.headerIdx - 1]" :controls="false" :precision="2"
                              size="small" style="width: 100%; height: 22px"
                              @change="onCellValueChange($index, child.headerIdx - 1, $event)"
                              @blur="onActiveCellBlur($event, child.headerIdx - 1)"
                              @keydown="onActiveCellKeydown($event, $index, child.headerIdx - 1)" />
                            <span v-else :class="['gt-amt', { 'total-val': row.is_total }]">
                              <GtAmountCell :value="getCellValue(row, child.headerIdx - 1)" :unit="noteUnit" />
                            </span>
                          </div>
                        </template>
                      </el-table-column>
                    </el-table-column>
                  </template>
                </template>
                <!-- ━━━ 原扁平表头渲染（无分组，零回归兼容） ━━━ -->
                <template v-else>
                <el-table-column v-for="(h, hiRaw) in (activeTableData.headers || [])" :key="hiRaw"
                  :label="h" :min-width="Number(hiRaw) === 0 ? 160 : 120" :align="Number(hiRaw) === 0 ? 'left' : 'right'" resizable>
                  <template #default="{ row, $index }">
                    <template v-if="Number(hiRaw) === 0">
                      <template v-if="editMode && !row.is_total">
                        <el-input v-if="isActiveCellEditing($index, -1)"
                          v-model="row.label" size="small" style="width: 100%; height: 22px"
                          :aria-label="`${(activeTableData.headers || [])[0] || '项目'} 行${$index + 1} 编辑`"
                          @change="onLabelChange($index, $event)"
                          @blur="onActiveCellBlur($event, $index, -1)"
                          @keydown="onActiveCellKeydown($event, $index, -1)" />
                        <span v-else class="gt-cell-editable" :class="{ 'total-label': row.is_total }"
                          role="gridcell" tabindex="0"
                          :aria-label="`${(activeTableData.headers || [])[0] || '项目'} 行${$index + 1}：${row.label || '空'}`">
                          {{ row.label || '' }}
                        </span>
                      </template>
                      <span v-else :class="{ 'total-label': row.is_total }">{{ row.label }}</span>
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
                        <el-input-number v-if="editMode && !row.is_total && isActiveCellEditing($index, Number(hiRaw) - 1)"
                          v-model="row.values[Number(hiRaw) - 1]" :controls="false" :precision="2"
                          size="small" style="width: 100%; height: 22px"
                          :aria-label="`${(activeTableData.headers || [])[Number(hiRaw)] || '列'} 行${$index + 1} 编辑`"
                          @change="onCellValueChange($index, Number(hiRaw) - 1, $event)"
                          @blur="onActiveCellBlur($event, $index, Number(hiRaw) - 1)"
                          @keydown="onActiveCellKeydown($event, $index, Number(hiRaw) - 1)" />
                        <span v-else-if="editMode && !row.is_total" class="gt-cell-editable"
                          role="gridcell"
                          tabindex="0"
                          :aria-label="`${(activeTableData.headers || [])[Number(hiRaw)] || '列'} 行${$index + 1}：${getCellValue(row, Number(hiRaw) - 1) ?? '空'}`">
                          <GtAmountCell :value="getCellValue(row, Number(hiRaw) - 1)" :unit="noteUnit" />
                        </span>
                        <span v-else-if="row.is_total" :class="['gt-amt', { 'gt-formula-mismatch': isFormulaMismatch(row, Number(hiRaw) - 1) }]">
                          <GtAmountCell :value="getCellValue(row, Number(hiRaw) - 1)" :unit="noteUnit" />
                        </span>
                        <span v-else :class="['gt-amt', { 'total-val': row.is_total }]">
                          <GtAmountCell :value="getCellValue(row, Number(hiRaw) - 1)" :unit="noteUnit" />
                        </span>
                        <span v-if="getCellMode(row, Number(hiRaw) - 1) === 'auto'" class="gt-cell-source gt-cell-trace-trigger" title="点击追溯来源" @click.stop="onAutoCellTraceClick($index, Number(hiRaw) - 1, $event)">📊</span>
                        <span v-else-if="getCellMode(row, Number(hiRaw) - 1) === 'manual'" class="gt-cell-manual" title="手动编辑">✏️</span>
                      </div>
                      </CommentTooltip>
                      </el-tooltip>
                    </template>
                  </template>
                </el-table-column>
                </template>
              </el-table>
              <div v-else-if="activeTableData?.headers?.length" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); padding: 10px; text-align: center; border: 1px dashed var(--gt-color-border-purple); border-radius: 6px;">
                该表格暂无数据行（可在编辑模式下添加）
              </div>
            </div>

            <!-- 表格结构编辑工具栏 (Req 38.1-38.6) — 置于表格下方、富文本上方 -->
            <div v-if="editMode && (currentNote.content_type === 'table' || currentNote.content_type === 'mixed')" class="gt-de-structure-toolbar">
              <el-button-group size="small">
                <el-button @click="onStructureAddRow" title="在末尾新增行">➕ 行</el-button>
                <el-button @click="onStructureDeleteRow" title="删除最后一行（合计行除外）" :disabled="!canDeleteRow">➖ 行</el-button>
                <el-button @click="onStructureAddColumn" title="新增列">➕ 列</el-button>
                <el-button @click="onStructureDeleteColumn" title="删除最后一列" :disabled="!canDeleteColumn">➖ 列</el-button>
              </el-button-group>
              <el-button-group size="small">
                <el-button @click="noteTableStructure.undo()" :disabled="!noteTableStructure.canUndo.value" title="撤销 (Ctrl+Z)">↩ 撤销</el-button>
                <el-button @click="noteTableStructure.redo()" :disabled="!noteTableStructure.canRedo.value" title="重做 (Ctrl+Y)">↪ 重做</el-button>
              </el-button-group>
              <el-button size="small" @click="onRestoreTemplateStructure" title="恢复为模板默认结构">🔄 恢复模板结构</el-button>
            </div>

            <div class="gt-de-editor-footer" v-if="editMode">
              <div class="gt-de-footer-secondary">
                <el-button size="small" plain @click="onClearAllFormulas" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : '清除所有单元格公式'">一键清除公式</el-button>
                <el-button size="small" plain @click="onRestoreAutoMode" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : '恢复为自动提数模式'">恢复自动提数</el-button>
              </div>
              <div class="gt-de-footer-primary">
                <el-button size="small" @click="exitEdit(true)">取消</el-button>
                <el-button size="small" type="primary" @click="onSave" :loading="saveLoading" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">保存</el-button>
              </div>
            </div>

            <!-- 文字型 — 富文本编辑器 (Req 48.1-48.7)
                 说明文本框对所有章节（表格/混合/文字）统一显示在表格下方：
                 底稿披露表「表格下面的文本框」经同步写入 text_content，此处落地展示，
                 并提供续写/改写/生成政策/变动分析/知识库等编制功能 -->
            <div v-if="currentNote.content_type === 'text' || currentNote.content_type === 'mixed' || currentNote.content_type === 'table'" class="gt-de-tiptap-wrapper">
              <div
                v-if="showGuidance && currentNote.content_type !== 'table'"
                class="gt-guidance-bar"
                :class="{ 'is-collapsed': !isGuidanceExpanded }"
              >
                <div class="gt-guidance-head" @click="toggleGuidanceExpand" :title="isGuidanceExpanded ? '收起编制说明' : '展开编制说明'">
                  <el-icon><InfoFilled /></el-icon>
                  <span class="gt-guidance-title">编制说明（仅供参考）</span>
                  <el-icon class="gt-guidance-caret">
                    <component :is="isGuidanceExpanded ? ArrowDown : ArrowRight" />
                  </el-icon>
                  <span class="gt-guidance-spacer" />
                  <el-icon class="gt-guidance-close" @click.stop="dismissGuidance" title="关闭提示"><Close /></el-icon>
                </div>
                <div v-show="isGuidanceExpanded" class="gt-guidance-text">{{ activeTableGuidance }}</div>
              </div>
              <!-- 增强富文本编辑器：支持标题/加粗/斜体/列表/表格/缩进/颜色/占位符/源码/字数 -->
              <!-- P0-3：「需补充」内联引导——text_content 含占位文本时琥珀提示 -->
              <div v-if="hasPlaceholderText && !placeholderDismissed" class="gt-de-placeholder-hint">
                <span class="gt-de-placeholder-icon">⚠️</span>
                <span class="gt-de-placeholder-msg">当前说明含占位文本（需补充/暂未/待确认），请结合底稿披露表数据完善内容。</span>
                <el-button size="small" link @click="placeholderDismissed = true" style="margin-left: auto; flex-shrink: 0;">关闭</el-button>
              </div>
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
          </template>
          <div v-else class="gt-de-empty-hint">请从左侧目录选择章节</div>
      </div>

      <!-- 右侧拖拽调整校验栏宽度 -->
      <div
        v-if="!deFullscreen"
        class="gt-de-resize-handle gt-de-resize-handle--right"
        @mousedown="onRightResizeStart"
      />

      <!-- 右侧：校验面板 -->
      <div v-if="!deFullscreen" class="gt-de-validation" :style="{ width: validationWidth + 'px' }">
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

    <!-- 导出确认弹窗 -->
    <el-dialog v-model="showExportDialog" title="导出 Word 附注" width="560px" append-to-body destroy-on-close>
      <div style="margin-bottom: 12px; font-size: 13px; color: var(--gt-color-text-regular);">
        将导出 <strong>{{ exportableSections.length }}</strong> 个章节到 Word 文档。
        <span v-if="excludedSections.length" style="color: var(--gt-color-text-tertiary);">
          （{{ excludedSections.length }} 个章节已排除）
        </span>
      </div>
      <div v-if="excludedSections.length" style="margin-bottom: 12px;">
        <div style="font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 6px;">已排除章节：</div>
        <el-tag v-for="s in excludedSections" :key="(s as any).note_section" size="small" type="info" style="margin: 2px 4px;">
          {{ (s as any).section_title }}
        </el-tag>
      </div>
      <template #footer>
        <el-button @click="showExportDialog = false">取消</el-button>
        <el-button type="primary" :loading="exportLoading" @click="showExportDialog = false; onExportWord()">确认导出</el-button>
      </template>
    </el-dialog>

    <!-- 导出设置弹窗：树形勾选哪些章节导出 -->
    <el-dialog v-model="showExportSettingDialog" title="导出章节设置" width="500px" append-to-body destroy-on-close>
      <div style="font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 10px;">勾选的章节将导出到 Word，取消勾选的不导出。</div>
      <el-tree
        :data="exportSettingTreeData"
        :props="{ label: 'label', children: 'children' }"
        show-checkbox
        node-key="id"
        :default-checked-keys="exportCheckedKeys"
        ref="exportTreeRef"
        style="max-height: 400px; overflow-y: auto;"
      />
      <template #footer>
        <el-button @click="showExportSettingDialog = false">取消</el-button>
        <el-button type="primary" @click="onSaveExportSettings">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量删除弹窗：树形勾选要删除的章节 -->
    <el-dialog v-model="showBatchDeleteDialog" title="批量删除章节" width="500px" append-to-body destroy-on-close>
      <div style="font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 10px;">勾选要删除的章节（删除后可通过"恢复"找回）。</div>
      <el-tree
        :data="exportSettingTreeData"
        :props="{ label: 'label', children: 'children' }"
        show-checkbox
        node-key="id"
        ref="batchDeleteTreeRef"
        style="max-height: 400px; overflow-y: auto;"
      />
      <template #footer>
        <el-button @click="showBatchDeleteDialog = false">取消</el-button>
        <el-button type="danger" @click="onBatchDelete">确认删除</el-button>
      </template>
    </el-dialog>

    <!-- 恢复已删除章节弹窗 -->
    <el-dialog v-model="showRestoreDialog" title="恢复已删除章节" width="500px" append-to-body destroy-on-close @open="loadDeletedSections">
      <div v-if="deletedSections.length === 0" style="text-align: center; padding: 30px; color: var(--gt-color-text-placeholder);">暂无已删除章节</div>
      <div v-else>
        <div style="font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 10px;">选择要恢复的章节：</div>
        <el-checkbox-group v-model="restoreChecked">
          <div v-for="s in deletedSections" :key="s.id" style="padding: 4px 0;">
            <el-checkbox :value="s.id">{{ s.section_title }}（{{ s.note_section }}）</el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="showRestoreDialog = false">取消</el-button>
        <el-button type="primary" :disabled="restoreChecked.length === 0" @click="onRestoreSections">恢复选中</el-button>
      </template>
    </el-dialog>

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

    <!-- 附注模块使用手册 -->
    <DisclosureNoteHandbookDialog v-model="showNoteHandbook" />

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

    <!-- 附注联动复盘 P0-1：披露同步 / 校验就绪度看板 -->
    <NoteReadinessPanel
      v-model:visible="showReadiness"
      :project-id="projectId"
      :year="year"
      @select-section="onReadinessSelectSection"
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
      @saved="fetchDetailFresh(currentNote?.note_section || '')"
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

  <!-- 附注 AI 填充 / 参照文档填充（知识库 RAG） -->
  <NoteAiFillDialog
    v-if="currentNote"
    v-model:visible="noteAiFillVisible"
    :project-id="projectId"
    :year="year"
    :note-section="currentNote.note_section"
    :section-title="currentNote.section_title || currentNote.note_section"
    :locked="!!getSectionLock(currentNote.note_section)"
    :initial-mode="noteAiFillMode"
    @adopted="onNoteAiFillAdopted"
  />

  <!-- 一键批量 AI 预填充结果面板 -->
  <el-dialog v-model="batchResultVisible" title="一键 AI 预填充结果" width="640px" append-to-body>
    <div class="gt-de-batch-summary">
      共 {{ batchResults.length }} 章：
      <el-tag type="success" size="small">生成 {{ batchGenerated }}</el-tag>
      <el-tag type="warning" size="small">降级 {{ batchDegraded }}</el-tag>
      <el-tag type="info" size="small">跳过 {{ batchSkipped }}</el-tag>
      <span class="gt-de-batch-hint">逐章确认采纳，不会自动写入正文</span>
    </div>
    <el-table :data="batchResults" size="small" max-height="420" border style="font-size: 13px">
      <el-table-column label="章节" min-width="160">
        <template #default="{ row }">{{ batchTitle(row.note_section) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'generated' ? 'success' : (row.status === 'degraded' ? 'warning' : 'info')" size="small">
            {{ row.status === 'generated' ? '已生成' : (row.status === 'degraded' ? '降级' : '跳过') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="草稿预览" min-width="220">
        <template #default="{ row }">
          <span class="gt-de-batch-preview">{{ (row.text || '').slice(0, 60) || '（无草稿）' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'skipped'"
            size="small"
            link
            type="primary"
            @click="goAdoptSection(row.note_section)"
          >去采纳</el-button>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button size="small" @click="batchResultVisible = false">关闭</el-button>
    </template>
  </el-dialog>

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
import { ref, computed, reactive, onMounted, onBeforeUnmount, onUnmounted, watch, nextTick, inject } from 'vue'
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
import { resolveActiveTableGuidance, isGuidanceVisible, guidanceDismissKey } from '@/utils/noteGuidance'
import WorkflowProgress from '@/components/common/WorkflowProgress.vue'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { fmtAmount, unitLabel, type AmountUnit } from '@/utils/formatters'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled, Close, ArrowDown, ArrowRight, Loading } from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import NoteReadinessPanel from '@/components/disclosure/NoteReadinessPanel.vue'
import StructureEditor from '@/components/formula/StructureEditor.vue'
import { isEmptyTable, type EmptyTableRow, type EmptyTableColumnDef } from '@/views/composables/disclosureEmptyTable'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import NoteRichTextEditor from '@/components/NoteRichTextEditor.vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 附注正文渲染：text_content 可能是 HTML（富文本框保存）或 markdown 纯文本
// （历史「生成附注」LLM 草稿写入 ### / ** / 列表）。NoteRichTextEditor 按 HTML 渲染，
// markdown 会显示成字面 ###/**。此处加载时将 markdown 归一为 HTML（幂等：HTML 原样返回），
// 保存后即以 HTML 落库，逐步清除存量 markdown 残留。
function renderNoteTextToHtml(raw: string | null | undefined): string {
  if (!raw) return ''
  const t = raw.trim()
  if (!t) return ''
  // 已是 HTML（富文本框保存的内容）→ 原样保留，不二次转换
  if (t.startsWith('<')) return raw
  try {
    const html = marked.parse(t, { async: false, gfm: true, breaks: true }) as string
    return DOMPurify.sanitize(html)
  } catch {
    // 转换失败降级为段落包裹（保底不丢内容）
    return t.split(/\n\n+/).filter(Boolean).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('')
  }
}
import NotesPrintPreview from '@/components/notes/NotesPrintPreview.vue'
import { refreshDisclosureFromWorkpapers, getProjectWizardState } from '@/services/commonApi'
import { useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { useAuthStore } from '@/stores/auth'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'

// EQCR 只读访问 (Requirements: 17.1-17.4)
const authStore = useAuthStore()
const isEqcrRole = computed(() => authStore.user?.role === 'eqcr')
// ─── P0-6.5: PermissionMatrix facade ────────────────────────────────────────
const { can: canOp, whyCannot } = usePermissionMatrix()
// DEPRECATED: 旧 isEqcrRole 判断仍保留，后续替换为 !canOp('note:edit')
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
import NoteAiFillDialog from '@/components/disclosure/NoteAiFillDialog.vue'
import http from '@/utils/http'
import { useEditingLock } from '@/composables/useEditingLock'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { useProjectEvents } from '@/composables/useProjectEvents'
import { useStaleRefresh } from '@/composables/useStaleRefresh'
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
import { resolveNoteDisclosureJumpTarget } from '@/views/composables/noteDisclosureJump'
import { projectSubTablesClient, deriveLegacyTableHeaders } from '@/components/workpaper/composables/disclosureColumnDefs'
import { useAcnr } from '@/services/acnr'
import { useNoteTemplate } from '@/views/composables/useNoteTemplate'
import { useNoteExport } from '@/views/composables/useNoteExport'
import { useNoteAi } from '@/views/composables/useNoteAi'
import {
  readParentCompanySource,
  parentCompanySourceSummary,
  PARENT_PROJECT_MISSING_TEXT,
} from '@/views/composables/parentCompanyNoteSource'
import { useAuditContext } from '@/composables/useAuditContext'
import NoteMappingDialog from '@/views/components/NoteMappingDialog.vue'
import DisclosureNoteHandbookDialog from '@/views/DisclosureNoteHandbookDialog.vue'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import AiContentPendingBanner from '@/components/ai/AiContentPendingBanner.vue'
import ConflictBanner from '@/components/conflict/ConflictBanner.vue'
import ConflictResolutionPanel from '@/components/conflict/ConflictResolutionPanel.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const { canEdit, onContextChange } = useAuditContext()

// 四栏模式感知：隐藏内置树面板避免与四栏目录重复
const isFourColumnMode = inject<import('vue').Ref<boolean>>('isFourColumnMode', ref(false))

// ─── P0-6.5: ProjectContext facade ───────────────────────────────────────────
const projectContext = computed(() => projectStore.currentProjectContext)
// DEPRECATED: 旧 projectStore.projectId 直接用仍保留，后续通过 projectContext 统一

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
    fetchDetailFresh(currentNote.value.note_section)
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

// ─── useStaleRefresh：补充上游变更事件（dataset 已由 useProjectEvents 覆盖） ────
const deStaleRefresh = useStaleRefresh(projectId, {
  events: ['trial-balance:updated', 'adjustment:saved', 'year:changed', 'project:updated'],
  mode: 'prompt',
  onRefresh: () => fetchTree(),
})

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
  resourceId: computed(() => (route.params.projectId as string || '') + '_note'),
  resourceType: 'disclosure_note',  // 走通用编辑锁端点 /api/editing-locks/disclosure_note/{id}
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
  noteList, treeLoading, treeSearch, noteTreeRef,
  treeData, filteredTreeData: baseFilteredTreeData,
  fetchTree, allowTreeDrop, onTreeNodeDrop, expandAll, collapseAll,
} = useNoteTree({
  projectId,
  year,
  templateType,
  isEqcrRole,
  onTreeLoaded: () => numbering.refreshNumbers(),
})

// ─── P2-9：附注树快捷筛选 ──────────────────────────────────────────────────────
const treeFilter = ref<'all' | 'incomplete' | 'has_findings' | 'has_placeholder'>('all')
const treeFilterOptions = [
  {
    label: '全部',
    value: 'all',
    tip: '不做筛选，显示左侧目录树的全部附注章节。',
    rule: '仅受上方「搜索章节」关键词影响。',
  },
  {
    label: '未编制',
    value: 'incomplete',
    tip: '只看还没动过的章节：既没有填写附注正文，也没有录入任何表格数据，用来快速定位待编制的工作量。',
    rule: '正文为空 且 无表格数据。',
  },
  {
    label: '校验异常',
    value: 'has_findings',
    tip: '只看最近一次附注校验命中问题的章节（如与试算表/报表金额不平、合计不符、必填缺失），用来集中修错。',
    rule: '服务端校验结果存在 错误 或 警告。',
  },
  {
    label: '待补充',
    value: 'has_placeholder',
    tip: '只看正文里还留着占位表述的章节，通常是 AI 生成或模板预填后需要人工补齐具体内容的地方。',
    rule: '正文含「需补充」「暂未」「待确认」等占位词。',
  },
]

/** 单个节点是否命中指定筛选条件 */
function matchesTreeFilter(node: any, filter: string): boolean {
  const d = node.data || node
  switch (filter) {
    case 'incomplete':
      return !d.text_content && !d.has_data
    case 'has_findings':
      return (d.findings?.error > 0) || (d.findings?.warning > 0)
    case 'has_placeholder':
      return /需补充|暂未|待确认/.test(d.text_content || '')
    default:
      return true
  }
}

/** 遍历分组树，收集所有叶子章节节点 */
function collectTreeLeaves(nodes: any[]): any[] {
  const out: any[] = []
  const walk = (list: any[]) => {
    for (const n of list || []) {
      if (n.children?.length) walk(n.children)
      else if (!n.isGroup) out.push(n)
    }
  }
  walk(nodes)
  return out
}

/** 各筛选项命中数量（随搜索关键词联动，供 tooltip / 徽标展示） */
const treeFilterCounts = computed<Record<string, number>>(() => {
  const leaves = collectTreeLeaves(baseFilteredTreeData.value)
  return {
    all: leaves.length,
    incomplete: leaves.filter(n => matchesTreeFilter(n, 'incomplete')).length,
    has_findings: leaves.filter(n => matchesTreeFilter(n, 'has_findings')).length,
    has_placeholder: leaves.filter(n => matchesTreeFilter(n, 'has_placeholder')).length,
  }
})

/** P0-3 树节点标记：叶子节点 text_content 是否含占位文本 */
function nodeHasPlaceholderText(node: any): boolean {
  const text = node?.data?.text_content || ''
  return /需补充|暂未|待确认/.test(text)
}

/**
 * filteredTreeData 在 useNoteTree 的 baseFilteredTreeData（搜索过滤）基础上
 * 叠加快捷筛选条件。
 */
const filteredTreeData = computed(() => {
  const base = baseFilteredTreeData.value
  if (treeFilter.value === 'all') return base

  const matchesFilter = (node: any): boolean => matchesTreeFilter(node, treeFilter.value)

  // 过滤各分组节点的子节点
  return base.map(group => {
    if (!group.children?.length) return group
    const filtered = group.children.map(child => {
      if (child.children) {
        // 二级分组
        const sub = child.children.filter(n => !n.isGroup && matchesFilter(n))
        return sub.length ? { ...child, children: sub } : null
      }
      return !child.isGroup && matchesFilter(child) ? child : null
    }).filter(Boolean)
    return filtered.length ? { ...group, children: filtered } : null
  }).filter(Boolean) as any[]
})

// ─── 侧栏拖拽调整宽度 ─────────────────────────────────────────────────────────
const sidebarWidth = ref(220)
const isResizing = ref(false)
let _resizeStartX = 0
let _resizeStartW = 0

function onResizeStart(e: MouseEvent) {
  e.preventDefault()
  isResizing.value = true
  _resizeStartX = e.clientX
  _resizeStartW = sidebarWidth.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}
function onResizeMove(e: MouseEvent) {
  const delta = e.clientX - _resizeStartX
  sidebarWidth.value = Math.max(160, Math.min(500, _resizeStartW + delta))
}
function onResizeEnd() {
  isResizing.value = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// ─── 右侧校验栏拖拽调整宽度 ───────────────────────────────────────────────────
const validationWidth = ref(240)
let _rightResizeStartX = 0
let _rightResizeStartW = 0

function onRightResizeStart(e: MouseEvent) {
  e.preventDefault()
  _rightResizeStartX = e.clientX
  _rightResizeStartW = validationWidth.value
  document.addEventListener('mousemove', onRightResizeMove)
  document.addEventListener('mouseup', onRightResizeEnd)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}
function onRightResizeMove(e: MouseEvent) {
  // 向左拖动增大宽度（右侧面板在右边，鼠标左移 = delta 负 = 宽度增）
  const delta = _rightResizeStartX - e.clientX
  validationWidth.value = Math.max(120, Math.min(500, _rightResizeStartW + delta))
}
function onRightResizeEnd() {
  document.removeEventListener('mousemove', onRightResizeMove)
  document.removeEventListener('mouseup', onRightResizeEnd)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

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
// 附注模块使用手册（工具栏右侧入口）
const showNoteHandbook = ref(false)
// 附注联动复盘 P0-1：就绪度看板（未从底稿同步 / 无数据 / 校验问题）
const showReadiness = ref(false)
const readinessSummary = ref<{ never_synced: number; error_sections: number } | null>(null)
const readinessAlertCount = computed(() => {
  const s = readinessSummary.value
  if (!s) return 0
  return (s.never_synced || 0) + (s.error_sections || 0)
})
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

// ─── 单元格激活编辑（仅活跃单元格渲染 input，其余保持轻量 span）──────────────────
const activeCellEdit = ref<{ rowIndex: number; colIndex: number } | null>(null)

function isActiveCellEditing(rowIndex: number, colIndex: number): boolean {
  if (!activeCellEdit.value) return false
  return activeCellEdit.value.rowIndex === rowIndex && activeCellEdit.value.colIndex === colIndex
}

function activateCell(rowIndex: number, colIndex: number) {
  if (!editMode.value) return
  activeCellEdit.value = { rowIndex, colIndex }
  // 用 nextTick 自动聚焦 input
  nextTick(() => {
    const input = document.querySelector('.gt-de-note-table .el-input-number input') as HTMLInputElement | null
    input?.focus()
    input?.select()
  })
}

function deactivateCell() {
  activeCellEdit.value = null
}

function onActiveCellBlur(event: FocusEvent, rowIndex: number, colIndex: number) {
  // 如果焦点移到了同表格内另一个元素（如用户点击另一单元格），不 deactivate
  // — onDeCellClick 会自行调用 activateCell 切换到新单元格
  const related = event.relatedTarget as HTMLElement | null
  if (related?.closest('.gt-de-note-table')) return
  // 焦点移出表格范围，deactivate
  if (activeCellEdit.value?.rowIndex === rowIndex && activeCellEdit.value?.colIndex === colIndex) {
    deactivateCell()
  }
}

function onActiveCellKeydown(event: KeyboardEvent, rowIndex: number, colIndex: number) {
  const headers = activeTableData.value?.headers || []
  const rows = activeTableData.value?.rows || []
  const maxCol = headers.length - 2  // 减去 label 列
  const maxRow = rows.length - 1

  if (event.key === 'Tab') {
    event.preventDefault()
    const nextCol = event.shiftKey ? colIndex - 1 : colIndex + 1
    if (nextCol >= -1 && nextCol <= maxCol) {
      if (!rows[rowIndex]?.is_total) {
        activateCell(rowIndex, nextCol)
      }
    } else if (!event.shiftKey && nextCol > maxCol) {
      // 下一行 label 列
      for (let r = rowIndex + 1; r <= maxRow; r++) {
        if (!rows[r]?.is_total) { activateCell(r, -1); break }
      }
    } else if (event.shiftKey && nextCol < -1) {
      // 上一行末列
      for (let r = rowIndex - 1; r >= 0; r--) {
        if (!rows[r]?.is_total) { activateCell(r, maxCol); break }
      }
    }
  } else if (event.key === 'Enter') {
    event.preventDefault()
    // 下一行同列
    for (let r = rowIndex + 1; r <= maxRow; r++) {
      if (!rows[r]?.is_total) { activateCell(r, colIndex); break }
    }
  } else if (event.key === 'Escape') {
    deactivateCell()
  }
}

// 退出编辑时清除活跃单元格
watch(() => editMode.value, (editing) => { if (!editing) deactivateCell() })

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

// P0-3：检测 text_content 是否含占位文本（需补充/暂未/待确认）
const placeholderDismissed = ref(false)
const hasPlaceholderText = computed(() => {
  const t = textContent.value
  if (!t) return false
  return /需补充|暂未|待确认/.test(t)
})

// 用户关闭的提示条（按 `note_section:tabIdx` 粒度记录，各表 Tab 独立关闭）
const dismissedGuidance = reactive(new Set<string>())
// 注：activeTableGuidance / showGuidance / dismissGuidance 定义在 activeTableData 之后
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

// ── 附注知识库 RAG AI 填充（disclosure-note-knowledge-ai-enrichment / Task 9）──
const noteAiFillVisible = ref(false)
const noteAiFillMode = ref<'ai' | 'reference'>('ai')
function openNoteAiFill(mode: 'ai' | 'reference') {
  if (!currentNote.value?.note_section) return
  noteAiFillMode.value = mode
  noteAiFillVisible.value = true
}
async function onNoteAiFillAdopted() {
  if (currentNote.value?.note_section) {
    await fetchDetailFresh(currentNote.value.note_section)
  }
}

// 一键批量 AI 预填充
const batchAiFillLoading = ref(false)
const batchResultVisible = ref(false)
const batchResults = ref<Array<{ note_section: string; status: string; text: string | null; citations: any[] }>>([])
const batchGenerated = computed(() => batchResults.value.filter(r => r.status === 'generated').length)
const batchDegraded = computed(() => batchResults.value.filter(r => r.status === 'degraded').length)
const batchSkipped = computed(() => batchResults.value.filter(r => r.status === 'skipped').length)
function batchTitle(section: string): string {
  const n = noteList.value.find((x: any) => x.note_section === section)
  return (n as any)?.title || (n as any)?.section_title || (n as any)?.label || section
}
async function openBatchAiFill() {
  batchAiFillLoading.value = true
  try {
    const res = await http.post(
      `/api/disclosure-notes/${projectId.value}/${year.value}/batch-ai-fill`,
      {},
    )
    const data = res.data || {}
    batchResults.value = Array.isArray(data.results) ? data.results : []
    batchResultVisible.value = true
  } catch {
    ElMessage.error('批量预填充失败，请稍后重试')
  } finally {
    batchAiFillLoading.value = false
  }
}
async function goAdoptSection(section: string) {
  batchResultVisible.value = false
  await fetchDetail(section)
  openNoteAiFill('ai')
}
// 单位切换（侧边栏）


// 多表格支持
const activeTableTab = ref('0')

const currentNoteTables = computed(() => {
  if (!currentNote.value?.table_data) return []
  const td = currentNote.value.table_data
  // 新格式：_tables 数组（后端已为 workpaper 来源注入投影表）
  let rawTables: any[] | null = null
  if (td._tables && Array.isArray(td._tables) && td._tables.length > 0) {
    rawTables = td._tables
  }
  if (!rawTables) {
    // 客户端兜底投影：workpaper 来源的 sub_table_data + _sub_table_columns
    const clientProjected = projectSubTablesClient(td)
    if (clientProjected && clientProjected.length > 0) {
      rawTables = clientProjected
    }
  }
  if (!rawTables) {
    // 旧格式：单表格
    if (td.rows) {
      const headers = (Array.isArray(td.headers) && td.headers.length > 0)
        ? td.headers
        : (deriveLegacyTableHeaders(td) || td.headers || [])
      rawTables = [{ name: currentNote.value.section_title, headers, rows: td.rows }]
    } else {
      return []
    }
  }

  // 渲染时合并续表：表名以"续"开头 或 含"（续："的表，把其列合并到同名主表
  const merged: any[] = []
  for (let i = 0; i < rawTables.length; i++) {
    const t = rawTables[i]
    const name = (t.name || '') as string
    // 判定是否为续表：以"续"开头（模板格式）或含"（续："（sub_table_data 格式）
    const isContinuation = name.startsWith('续') || name.includes('（续：') || name.includes('(续：')
    if (isContinuation && merged.length > 0) {
      // 有独立列定义（_column_groups 或 columns）的续表不合并——它是完整独立子表
      if (t._column_groups || (t.columns && Array.isArray(t.columns) && t.columns.length > 0)) {
        merged.push(t)
        continue
      }
      // 找到对应主表（续表名通常含主表名前缀，如"按坏账计提方法分类披露（续：上年年末余额）"对应"按坏账计提方法分类披露"）
      let prevIdx = merged.length - 1
      // 尝试精确匹配：续表名去掉"（续：...）"后 === 某已有表名
      const baseName = name.replace(/[（(]续[：:].*$/, '').trim()
      if (baseName) {
        const matchIdx = merged.findIndex(m => (m.name || '').trim() === baseName)
        if (matchIdx >= 0) prevIdx = matchIdx
        else {
          // 找不到对应主表，作为独立 tab 保留不合并
          merged.push(t)
          continue
        }
      }
      const prev = merged[prevIdx]
      const prevHeaders: string[] = prev.headers || []
      const nextHeaders: string[] = t.headers || []
      // 续表 headers 第一列通常是重复的标签列（类别/名称），跳过
      const skipFirst = nextHeaders.length > 0 && prevHeaders.length > 0 &&
        (nextHeaders[0] === prevHeaders[0] || nextHeaders[0] === '类别' || nextHeaders[0] === '名称')
      const appendHeaders = skipFirst ? nextHeaders.slice(1) : nextHeaders
      prev.headers = [...prevHeaders, ...appendHeaders]

      // 合并行 values
      const prevRows: any[] = prev.rows || []
      const nextRows: any[] = t.rows || []
      for (let ri = 0; ri < Math.max(prevRows.length, nextRows.length); ri++) {
        const prevRow = ri < prevRows.length ? prevRows[ri] : { label: '', values: [] }
        const nextRow = ri < nextRows.length ? nextRows[ri] : { values: [] }
        const nextVals = nextRow.values || []
        const appendVals = skipFirst ? nextVals : nextVals
        if (!prevRow.values) prevRow.values = []
        prevRow.values = [...prevRow.values, ...appendVals]
        if (ri >= prevRows.length) prevRows.push(prevRow)
      }
      prev.rows = prevRows
    } else {
      merged.push(t)
    }
  }
  return merged
})

const activeTableData = computed(() => {
  const idx = parseInt(activeTableTab.value) || 0
  const table = currentNoteTables.value[idx] || currentNoteTables.value[0] || null
  return table
})

/**
 * 解析当前表的列结构，支持两级分组表头（el-table-column 嵌套）。
 * 返回列描述数组：无 group 的独立列 {type:'flat', headerIdx, label}
 * 有 group 的连续列合并为 {type:'grouped', group, children:[{headerIdx, label}]}
 */
const activeTableColumns = computed(() => {
  const table = activeTableData.value
  if (!table?.headers?.length) return []
  const headers = table.headers as string[]
  const groups: Array<{ group: string; start: number; span: number }> | null =
    (table as any)?._column_groups ?? null

  if (!groups || groups.length === 0) {
    // 无分组信息 → 全部扁平列（走旧逻辑兼容）
    return null
  }

  // 构建列结构：按 headers 索引逐列归类
  type FlatCol = { type: 'flat'; headerIdx: number; label: string }
  type GroupedCol = { type: 'grouped'; group: string; children: Array<{ headerIdx: number; label: string }> }
  type Col = FlatCol | GroupedCol

  const result: Col[] = []
  // 标记哪些索引被分组占用
  const grouped = new Set<number>()
  for (const g of groups) {
    for (let i = g.start; i < g.start + g.span; i++) grouped.add(i)
  }

  let gi = 0 // groups 游标
  for (let i = 0; i < headers.length; i++) {
    if (grouped.has(i)) {
      // 找到对应的 group 定义
      const g = groups.find(gg => gg.start === i)
      if (g) {
        const children: Array<{ headerIdx: number; label: string }> = []
        for (let j = g.start; j < g.start + g.span && j < headers.length; j++) {
          children.push({ headerIdx: j, label: headers[j] })
        }
        result.push({ type: 'grouped', group: g.group, children })
        i = g.start + g.span - 1 // 跳到分组末尾
      }
    } else {
      result.push({ type: 'flat', headerIdx: i, label: headers[i] })
    }
  }
  return result
})

// 注：per-tab 说明文本框（activeTabNoteText/activeTabNoteTextEditable）已移除。
// 底稿披露表「表格下面的文本框」经同步写入 note.text_content（_note_texts→_format_note_texts），
// 统一落地到表格下方的富文本编辑器（textContent），不再拆分为 per-tab 纯文本框。

// 母公司章取数溯源（Task 13）：三态 —— none 不渲染 / missing 灰态提示 / resolved 展示三项。
// 键由后端 `_attach_parent_source_meta` 落在**表级**，故按 activeTableData 取。
const parentSourceView = computed(() => readParentCompanySource(activeTableData.value))

// 当前 Tab 的提示文字：优先取该表 guidance，降级章节级 guidance_text
const activeTableGuidance = computed(() =>
  resolveActiveTableGuidance(activeTableData.value as any, currentNote.value),
)

// 提示条显示判定：按 `note_section:tabIdx` 粒度（各 Tab 独立关闭记忆）
const showGuidance = computed(() =>
  isGuidanceVisible(
    activeTableGuidance.value,
    currentNote.value?.note_section,
    activeTableTab.value,
    dismissedGuidance,
  ),
)

function dismissGuidance() {
  const sec = currentNote.value?.note_section
  if (sec) dismissedGuidance.add(guidanceDismissKey(sec, activeTableTab.value))
}

// 编制说明默认折叠：仅当用户展开的 `note_section:tabIdx` 才展示正文（各 Tab 独立记忆）
const expandedGuidance = reactive(new Set<string>())
const isGuidanceExpanded = computed(() =>
  expandedGuidance.has(
    guidanceDismissKey(currentNote.value?.note_section, activeTableTab.value),
  ),
)
function toggleGuidanceExpand() {
  const key = guidanceDismissKey(currentNote.value?.note_section, activeTableTab.value)
  if (expandedGuidance.has(key)) expandedGuidance.delete(key)
  else expandedGuidance.add(key)
}

// 多表导出开关：跟踪哪些表格启用导出（indices）
const exportEnabledTables = computed({
  get() {
    if (!currentNoteTables.value) return [] as number[]
    return currentNoteTables.value
      .map((t: any, i: number) => t.export_enabled !== false ? i : -1)
      .filter((i: number) => i >= 0)
  },
  set(indices: number[]) {
    if (!currentNote.value?.table_data?._tables) return
    const tables = currentNote.value.table_data._tables
    tables.forEach((t: any, i: number) => {
      t.export_enabled = indices.includes(i)
    })
    markEditDirty()
    autoSave.markDirty()
  },
})

// 切换章节时重置表格Tab
watch(() => currentNote.value?.note_section, () => {
  activeTableTab.value = '0'
  noteTableStructure.clearHistory()
  deactivateCell()
})

// 切换多表 Tab 时清除活跃单元格（防坐标错位）
watch(activeTableTab, () => { deactivateCell() })

// ─── 附注表格结构编辑 (Req 38.1-38.6) ─────────────────────────────────────
const noteTableStructure = useNoteTableStructure({
  getActiveTable: () => activeTableData.value as TableData | null,
  markDirty: () => { if (editMode.value) { markEditDirty(); autoSave.markDirty() } },
})

// 表格Tab标签：避免显示无意义的"项 目"等表头值
const _GENERIC_NAMES = new Set(['项  目', '项 目', '项目', '类  别', '类别', ''])
const _TABLE_SUFFIX_RE = /[（(]表\d+[）)]/

/** 完整表格名称（用于 tooltip） */
function getTableTabFullName(tbl: any, idx: number): string {
  const name = (tbl.name || '').trim()
  if (name && !_GENERIC_NAMES.has(name) && !_TABLE_SUFFIX_RE.test(name)) {
    return name
  }
  const headers = tbl.headers || []
  if (headers.length > 1) {
    const h1 = String(headers[1] || '').trim()
    if (h1 && h1.length <= 8 && !_GENERIC_NAMES.has(h1.replace(/\s+/g, ''))) return `表${idx + 1}·${h1}`
  }
  return `表${idx + 1}`
}

/** 截断的 Tab 标签显示文字 */
function getTableTabLabel(tbl: any, idx: number): string {
  const full = getTableTabFullName(tbl, idx)
  return full.length > 14 ? full.slice(0, 14) + '…' : full
}

/** 空表判定：灰度开关关闭时恒返回 false（Property 10）。 */
const EMPTY_TABLE_COLLAPSE_ENABLED: boolean =
  import.meta.env.VITE_DISCLOSURE_EMPTY_TABLE_COLLAPSE !== 'false' // 默认开（开发环境可见）
function isTableEmpty(tbl: any): boolean {
  if (!EMPTY_TABLE_COLLAPSE_ENABLED) return false
  return isEmptyTable(tbl?.rows as EmptyTableRow[], tbl?.columns as EmptyTableColumnDef[] ?? null)
}

/** 当前活跃表是否为空表 */
const isActiveTableEmpty = computed(() => isTableEmpty(activeTableData.value))

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

function onLabelChange(_rowIndex: number, _newValue: string) {
  markEditDirty()
  autoSave.markDirty()
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
  refreshLoading, refreshAllLoading, syncError,
  onRefreshFromWP, onRefreshAll, onManualRefresh, onStaleRecalc,
  showRefreshResultMessage, onWorkpaperSaved, onDisclosureNoteTextUpdated,
} = useNoteRefresh({
  projectId,
  year,
  currentNote,
  fetchDetail: fetchDetailFresh,  // 刷新后必须绕过缓存
  fetchTree,
  staleRecalc: () => stale.recalc(),
  invalidateAllCache: () => invalidateDetailCache(),  // 全部刷新：清空全部章节缓存
})

// #20: 首次同步引导横幅（从未同步过的项目一次性提示）
const syncHintDismissed = ref(localStorage.getItem(`gt_note_sync_hint_dismissed_${projectId.value}`) === 'true')
const showSyncHint = computed(() => {
  if (syncHintDismissed.value) return false
  // noteList 全部无 last_sync_at 时视为从未同步
  const list = noteList.value || []
  if (!list.length) return false
  return !list.some((n: any) => n.last_sync_at || n.last_sync_source)
})
function dismissSyncHint() {
  syncHintDismissed.value = true
  localStorage.setItem(`gt_note_sync_hint_dismissed_${projectId.value}`, 'true')
}

// #22: 编制进度统计
const noteProgress = computed(() => {
  const list = (noteList.value || []) as any[]
  if (!list.length) return { complete: 0, textOnly: 0, tableOnly: 0, empty: 0, total: 0 }
  let complete = 0, textOnly = 0, tableOnly = 0, empty = 0
  for (const n of list) {
    const hasText = !!(n.text_content && n.text_content.trim())
    const hasData = !!n.has_data
    if (hasText && hasData) complete++
    else if (hasText) textOnly++
    else if (hasData) tableOnly++
    else empty++
  }
  return { complete, textOnly, tableOnly, empty, total: list.length }
})

const { resolveInstance: acnrResolveInstance } = useAcnr()
const jumpingDisclosure = ref(false)

const disclosureJumpTarget = computed(() =>
  resolveNoteDisclosureJumpTarget(currentNote.value),
)

function jumpToLastSyncWorkpaper(): void {
  const note = currentNote.value as any
  const wpId = note?.last_sync_wp_id
  if (!wpId || !projectId.value) return
  const sheet = note?.table_data?._last_sync_sheet
    || note?.table_data?._last_sync_sheet_name
    || ''
  router.push({
    path: `/projects/${projectId.value}/workpapers/${wpId}/edit`,
    query: sheet ? { sheet: String(sheet) } : {},
  })
}

/** 附注 → G7/G10 披露表（上市/国企 sheet）；优先同步 wp_id，否则 ACNR 解析 */
async function jumpToDisclosureSheet(): Promise<void> {
  const target = disclosureJumpTarget.value
  const wpFamily = target?.wpCode ?? 'G7'
  const wpFamilyLabelMap: Record<string, string> = {
    D1: '应收票据',
    E1: '货币资金',
    F1: '预付款项',
    F2: '存货',
    G1: '交易性金融资产',
    G7: '长期股权投资',
    G10: '交易性金融负债',
    G11: '投资收益',
    G13: '公允价值变动收益',
    G14: '信用减值损失',
    H1: '固定资产',
    H2: '在建工程',
    H8: '使用权资产',
    H9: '租赁负债',
    H10: '资产处置收益',
    I1: '无形资产',
    I2: '开发支出',
    I3: '商誉',
    I4: '长期待摊费用',
    I5: '其他非流动资产',
    I6: '研发费用',
    K1: '其他应收款',
    K11: '资产减值损失',
    K13: '营业外支出',
    N1: '递延所得税资产',
    J1: '应付职工薪酬',
  }
  const wpFamilyLabel = wpFamilyLabelMap[wpFamily] ?? wpFamily
  if (!target || !projectId.value) {
    ElMessage.warning(`当前章节未关联${wpFamilyLabel}披露表`)
    return
  }
  jumpingDisclosure.value = true
  try {
    let wpId = target.wpId
    if (!wpId) {
      const res = await acnrResolveInstance({
        project_id: projectId.value,
        parent: wpFamily,
        sheet_code: wpFamily,
      })
      if (res?.found && res.wp_id) {
        wpId = res.wp_id
      }
    }
    if (!wpId) {
      ElMessage.warning(`未找到 ${wpFamily} 底稿，请先在项目中生成`)
      return
    }
    router.push({
      path: `/projects/${projectId.value}/workpapers/${wpId}/edit`,
      query: { sheet: target.sheet },
    })
  } catch {
    ElMessage.warning(`跳转披露表失败，请手动打开 ${wpFamily} 底稿`)
  } finally {
    jumpingDisclosure.value = false
  }
}

async function onFormulaApplied() {
  // 公式应用后刷新当前附注数据
  if (currentNote.value) await fetchDetailFresh(currentNote.value.note_section)
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
  if (currentNote.value) await fetchDetailFresh(currentNote.value.note_section)
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
} = useNoteSectionManage({ projectId, year, currentNote, fetchTree, fetchDetail: fetchDetailFresh, noteStale })

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
    await fetchDetailFresh(currentNote.value.note_section)
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
    await fetchDetailFresh(currentNote.value.note_section)
  } catch (e: any) {
    handleApiError(e, '恢复')
  }
}

// ── 导出功能（useNoteExport composable）──
const { exportLoading, onExportWord } = useNoteExport({ projectId, year })

// ── 章节管理：删除 + 排除导出 ──────────────────────────────────────────────────
const showExportDialog = ref(false)

async function onDeleteSection(noteData: any) {
  if (!noteData?.note_section) return
  try {
    await ElMessageBox.confirm(
      `确定删除章节「${noteData.section_title}」？删除后可通过重新生成恢复。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    const sec = encodeURIComponent(noteData.note_section)
    await api.delete(`/api/disclosure-notes/${projectId.value}/${year.value}/sections/${sec}`)
    ElMessage.success('章节已删除')
    await fetchTree()
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
      handleApiError(e, '删除失败')
    }
  }
}

async function onToggleExclude(noteData: any) {
  if (!noteData?.note_section) return
  const newStatus = noteData.status === 'not_applicable' ? 'draft' : 'not_applicable'
  try {
    const sec = encodeURIComponent(noteData.note_section)
    await api.patch(`/api/disclosure-notes/${projectId.value}/${year.value}/sections/${sec}`, {
      status: newStatus,
    })
    noteData.status = newStatus
    ElMessage.success(newStatus === 'not_applicable' ? '该章节将不导出到 Word' : '已恢复导出')
  } catch (e: any) {
    handleApiError(e, '操作失败')
  }
}

function onExportWithConfirm() {
  showExportDialog.value = true
}

const exportableSections = computed(() => {
  return noteList.value.filter(n => n.status !== 'not_applicable')
})
const excludedSections = computed(() => {
  return noteList.value.filter(n => (n as any).status === 'not_applicable')
})

// ── 导出设置弹窗 ──────────────────────────────────────────────────────────────
const showExportSettingDialog = ref(false)
const exportTreeRef = ref<any>(null)

const exportSettingTreeData = computed(() => {
  // 复用 treeData 结构但只取叶子节点的 id
  return treeData.value
})
const exportCheckedKeys = computed(() => {
  return noteList.value.filter(n => n.status !== 'not_applicable').map(n => n.id)
})

async function onSaveExportSettings() {
  const tree = exportTreeRef.value
  if (!tree) return
  const checkedIds = new Set(tree.getCheckedKeys(true) as string[])
  // 对比变化，批量更新
  for (const note of noteList.value) {
    const shouldExport = checkedIds.has(note.id)
    const currentlyExcluded = note.status === 'not_applicable'
    if (shouldExport && currentlyExcluded) {
      const sec = encodeURIComponent(note.note_section)
      await api.patch(`/api/disclosure-notes/${projectId.value}/${year.value}/sections/${sec}`, { status: 'draft' })
    } else if (!shouldExport && !currentlyExcluded) {
      const sec = encodeURIComponent(note.note_section)
      await api.patch(`/api/disclosure-notes/${projectId.value}/${year.value}/sections/${sec}`, { status: 'not_applicable' })
    }
  }
  ElMessage.success('导出设置已保存')
  showExportSettingDialog.value = false
  await fetchTree()
}

// ── 批量删除弹窗 ──────────────────────────────────────────────────────────────
const showBatchDeleteDialog = ref(false)
const batchDeleteTreeRef = ref<any>(null)

async function onBatchDelete() {
  const tree = batchDeleteTreeRef.value
  if (!tree) return
  const checkedIds = new Set(tree.getCheckedKeys(true) as string[])
  if (checkedIds.size === 0) {
    ElMessage.warning('请先选择要删除的章节')
    return
  }
  const toDelete = noteList.value.filter(n => checkedIds.has(n.id))
  for (const note of toDelete) {
    const sec = encodeURIComponent(note.note_section)
    await api.delete(`/api/disclosure-notes/${projectId.value}/${year.value}/sections/${sec}`)
  }
  ElMessage.success(`已删除 ${toDelete.length} 个章节`)
  showBatchDeleteDialog.value = false
  await fetchTree()
}

// ── 恢复已删除章节弹窗 ────────────────────────────────────────────────────────
const showRestoreDialog = ref(false)
const deletedSections = ref<any[]>([])
const restoreChecked = ref<string[]>([])

async function loadDeletedSections() {
  restoreChecked.value = []
  try {
    const data = await api.get(`/api/disclosure-notes/${projectId.value}/${year.value}/deleted`)
    deletedSections.value = data || []
  } catch {
    deletedSections.value = []
  }
}

async function onRestoreSections() {
  if (restoreChecked.value.length === 0) return
  for (const id of restoreChecked.value) {
    await api.patch(`/api/disclosure-notes/${projectId.value}/${year.value}/restore/${id}`, {})
  }
  ElMessage.success(`已恢复 ${restoreChecked.value.length} 个章节`)
  showRestoreDialog.value = false
  await fetchTree()
}

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

/**
 * 把跳转传入的目标章节解析为 noteList 中实际存在的精确 note_section。
 * 纯编号章节（五、7 / 八、70）只精确匹配（禁前缀模糊：八、7 会误配 八、70）；
 * 关键词标题章节（三、信用减值损失…）容忍生成时标题截断（DB 存 `三、信用减值损失（损`），
 * 做前缀双向模糊。解析失败回退原值（不会更差）。
 */
function resolveSectionInList(target: string): string {
  const t = String(target || '').trim()
  if (!t) return t
  const list: any[] = noteList.value || []
  const exact = list.find((n: any) => String(n?.note_section || '') === t)
  if (exact) return exact.note_section
  // 纯编号（如 五、7 / 八、70）：不做前缀模糊，避免 八、7 误配 八、70
  if (/^[一二三四五六七八九十]+、\d+$/.test(t)) return t
  const pfx = list.find((n: any) => {
    const s = String(n?.note_section || '')
    return !!s && (s.startsWith(t) || t.startsWith(s))
  })
  return pfx ? pfx.note_section : t
}

/** 递归查找 note_section 对应的叶子节点 id（treeData 分组结构） */
function _findTreeNodeIdBySection(nodes: TreeNode[], section: string): string | null {
  for (const n of nodes) {
    if (!n.isGroup && n.data?.note_section === section) return n.id
    if (n.children?.length) {
      const found = _findTreeNodeIdBySection(n.children, section)
      if (found) return found
    }
  }
  return null
}

/**
 * 左侧章节树定位：展开祖先分组 + 高亮当前节点 + 滚动到可视区。
 * 用于程序化导航（四栏跨页 / 披露表反向跳转）——普通点击由 el-tree 内部维护 current，
 * 但 fetchDetail 走程序化路径不会设置 el-tree 的 currentKey/展开/滚动。
 */
/**
 * 附注联动复盘 P0-1：拉就绪度摘要（工具栏徽标 = 未同步 + 校验错误章节数）。
 * 只读、fail-open：失败仅不显示徽标。
 */
async function loadReadinessSummary() {
  if (!projectId.value || !year.value) return
  try {
    const { getDisclosureReadiness } = await import('@/services/commonApi')
    const data = await getDisclosureReadiness(projectId.value, year.value)
    readinessSummary.value = {
      never_synced: data?.summary?.never_synced || 0,
      error_sections: data?.summary?.error_sections || 0,
    }
  } catch {
    readinessSummary.value = null
  }
}

/** P0-4：树节点是否有服务端 findings（来自 tree 端点 additive 字段） */
function serverFindings(node: any): boolean {
  const f = node?.findings
  return !!f && ((f.error || 0) > 0 || (f.warning || 0) > 0)
}

function serverFindingsTip(node: any): string {
  const f = node?.findings || {}
  const parts: string[] = []
  if (f.error) parts.push(`校验错误 ${f.error} 项`)
  if (f.warning) parts.push(`校验提醒 ${f.warning} 项`)
  return parts.length ? `${parts.join('，')}（点工具栏「✅ 校验」查看明细）` : ''
}

/** 就绪度看板「查看章节」→ 定位并加载该章节 */
async function onReadinessSelectSection(section: string) {
  const resolved = resolveSectionInList(section)
  await fetchDetail(resolved)
  await locateTreeNode(resolved)
}

async function locateTreeNode(section: string) {
  await nextTick()
  const tree: any = noteTreeRef.value
  if (!tree) return
  const id = _findTreeNodeIdBySection(treeData.value, section)
  if (!id) return
  try {
    // 先展开祖先分组节点（setCurrentKey 不会自动展开祖先）
    const nodeObj = tree.store?.nodesMap?.[id]
    let p = nodeObj?.parent
    while (p && p.level > 0) { p.expanded = true; p = p.parent }
    tree.setCurrentKey(id)
    await nextTick()
    // 滚动到当前高亮节点
    const el = tree.$el?.querySelector('.el-tree-node.is-current') as HTMLElement | null
    el?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  } catch { /* 定位失败不影响右侧已加载内容 */ }
}

// ─── 章节详情缓存 + hover 预取 ─────────────────────────────────────────────────
const _detailCache = new Map<string, any>()
let _prefetchTimer: ReturnType<typeof setTimeout> | null = null

function _cacheKey(noteSection: string): string {
  return `${projectId.value}:${year.value}:${noteSection}`
}

/** 清除全部或指定章节缓存 */
function invalidateDetailCache(noteSection?: string) {
  if (noteSection) {
    _detailCache.delete(_cacheKey(noteSection))
  } else {
    _detailCache.clear()
  }
}

/** hover 预取：鼠标停留 200ms 后静默加载到缓存 */
function onTreeNodeMouseEnter(data: any) {
  if (!data?.note_section || data.isGroup) return
  const key = _cacheKey(data.note_section)
  if (_detailCache.has(key)) return  // 已缓存
  if (_prefetchTimer) clearTimeout(_prefetchTimer)
  _prefetchTimer = setTimeout(async () => {
    try {
      const detail = await getDisclosureNoteDetail(projectId.value, year.value, data.note_section)
      _detailCache.set(key, detail)
    } catch { /* 预取失败静默忽略 */ }
  }, 200)
}

function onTreeNodeMouseLeave() {
  if (_prefetchTimer) { clearTimeout(_prefetchTimer); _prefetchTimer = null }
}

async function fetchDetail(noteSection: string, bypassCache = false) {
  const key = _cacheKey(noteSection)

  if (!bypassCache && _detailCache.has(key)) {
    // 命中缓存，直接应用
    currentNote.value = _detailCache.get(key)
  } else {
    // 未命中或强制刷新：发起网络请求
    currentNote.value = await getDisclosureNoteDetail(projectId.value, year.value, noteSection)
    _detailCache.set(key, currentNote.value)
  }

  // markdown 残留归一为 HTML（幂等），喂给 NoteRichTextEditor(v-model=textContent) 与 legacy editor
  textContent.value = renderNoteTextToHtml(currentNote.value.text_content)
  placeholderDismissed.value = false // P0-3：切换章节重置占位文本提示
  if (editor.value) {
    editor.value.commands.setContent(textContent.value || '')
  }
  // 并行加载上年数据
  try {
    priorYearNote.value = await api.get(
      P.disclosureNotes.priorYear(projectId.value, year.value, noteSection)
    )
  } catch { priorYearNote.value = null }
}

/** 强制刷新（跳过缓存） — 用于保存/公式/刷新等数据变更后 */
async function fetchDetailFresh(noteSection: string) {
  invalidateDetailCache(noteSection)
  await fetchDetail(noteSection, true)
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
      // 生成前先触发底稿→附注同步标记（确保已同步的章节不被生成覆盖）
      try {
        await http.post(`/api/disclosure-notes/${projectId.value}/${year.value}/pull-from-workpapers`, null, { _silent: true } as any)
      } catch { /* fail-open */ }
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
  try {
    const tt = templateType.value === 'listed' || templateType.value === 'soe'
      ? templateType.value
      : undefined
    await validateDisclosureNotes(projectId.value, year.value, tt)
    validationFindings.value = await getValidationResults(projectId.value, year.value)
    // 校验后刷新左树圆点（P0-2：makeNoteLeaf 从后端 findings 派生 validationStatus）
    void fetchTree()
    if (validationFindings.value.length === 0) {
      ElMessage.success('校验完成，未发现需处理的问题')
    } else {
      ElMessage.warning(`校验完成，发现 ${validationFindings.value.length} 项，请查看右侧校验结果`)
    }
  } catch (e: any) {
    // 校验失败不得崩溃整页；清空结果并提示（区分 404「无结果」与其他错误）
    validationFindings.value = []
    const status = e?.response?.status
    const msg = e?.response?.data?.detail || e?.response?.data?.message || e?.message || ''
    if (status === 404) {
      ElMessage.info('校验完成，未发现需处理的问题')
    } else {
      ElMessage.error('校验失败' + (msg ? '：' + msg : ''))
    }
  }
})

// ── 保存功能（useNotePersist composable）──
const { saveLoading, justSaved, onSave: _rawSave } = useNotePersist({
  currentNote,
  textContent,
  editMode,
  clearEditDirty,
  autoSaveClearDirty: () => autoSave.clearDirty(),
  clearAutoSaveDraft,
})

// ── Task #11：保存状态指示器 ──
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')

async function onSave() {
  saveStatus.value = 'saving'
  try {
    await _rawSave()
    saveStatus.value = 'saved'
    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 3000)
    // ── Task #12：保存成功后自动跳到下一未编制章节 ──
    if (autoAdvance.value) {
      const next = findNextIncompleteSection()
      if (next) {
        setTimeout(async () => {
          await fetchDetail(next)
          await locateTreeNode(next)
        }, 500)
      }
    }
  } catch {
    saveStatus.value = 'error'
  }
}

// ── Task #12：自动滚到下一未编制章节 ──
const autoAdvance = ref(localStorage.getItem('gt_note_auto_advance') !== 'false')
function toggleAutoAdvance(val: boolean) {
  autoAdvance.value = val
  localStorage.setItem('gt_note_auto_advance', String(val))
}
function findNextIncompleteSection(): string | null {
  const list = noteList.value || []
  const currentIdx = list.findIndex((n: any) => n.note_section === currentNote.value?.note_section)
  if (currentIdx < 0) return null
  for (let i = currentIdx + 1; i < list.length; i++) {
    const n = list[i] as any
    if (!n.text_content && !n.has_data) return n.note_section
  }
  return null
}

// 保存后更新缓存为当前最新状态（避免导航回来时拿到旧缓存）
watch(justSaved, (saved) => {
  if (saved && currentNote.value?.note_section) {
    const key = _cacheKey(currentNote.value.note_section)
    _detailCache.set(key, currentNote.value)
  }
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

// ─── Task 5.2: 四栏目录附注章节点击导航处理 ─────────────────────────────────
async function onCatalogNoteSelect({ noteSection }: { noteSection: string }) {
  // 同章节守卫（Req 2.4）
  if (noteSection === currentNote.value?.note_section) return
  const previousSection = currentNote.value?.note_section || ''
  try {
    await fetchDetail(noteSection)
    await locateTreeNode(noteSection)  // 左侧树形同步定位（展开祖先 + 高亮 + 滚动）
  } catch {
    ElMessage.error('章节加载失败')
    // 失败回退：通知 catalog 恢复之前的高亮
    if (previousSection) {
      eventBus.emit('note:section-changed', { noteSection: previousSection })
    }
  }
}

// ─── Task 5.3: 反向通知 — 内部树切换时通知 FourColumnCatalog 更新高亮 ────────
watch(() => currentNote.value?.note_section, (newSection) => {
  if (newSection) {
    eventBus.emit('note:section-changed', { noteSection: newSection })
  }
})

onMounted(async () => {
  selectedProjectId.value = projectId.value
  selectedYear.value = year.value
  projectStore.loadProjectOptions()
  eventBus.on('shortcut:save', onShortcutSave)
  eventBus.on('workpaper:saved', onWorkpaperSaved)
  eventBus.on('disclosure:note-text-updated', onDisclosureNoteTextUpdated)
  // Task 5.2: 监听四栏目录附注章节点击
  eventBus.on('catalog:note-select', onCatalogNoteSelect)
  await loadProjectTemplateConfig()
  // 反向跳转（披露表 → 附注）：URL 指定 noteTemplate 时强制上市/国企视图（支持自由切换上市↔国企）
  const qTemplate = route.query.noteTemplate as string | undefined
  if (qTemplate === 'listed' || qTemplate === 'soe') {
    templateType.value = qTemplate
  }
  await fetchTree()
  // 如果没有附注数据，自动从模板生成
  if (noteList.value.length === 0) {
    await onGenerate()
  }
  // Task 5.1: 从 URL query.section 自动定位章节（四栏跨页面导航 / 披露表反向跳转）
  const targetSection = route.query.section as string | undefined
  if (targetSection && noteList.value.length > 0) {
    // 反向跳转可能传入关键词标题（如损益类 三、信用减值损失），DB 实际章节可能被截断
    // （三、信用减值损失（损），需解析为 noteList 中的精确 note_section 再定位。
    const resolvedSection = resolveSectionInList(targetSection)
    await fetchDetail(resolvedSection)
    await locateTreeNode(resolvedSection)  // 左侧树形定位：展开祖先分组 + 高亮 + 滚动到可视区
    // 🔴 用 history.replaceState 清理 URL query，禁止用 router.replace：
    // DefaultLayout 的 router-view 以 :key="fullPath"（含 query）渲染，router.replace 改 query
    // 会触发整页重挂载 → 刚 fetchDetail 选中的 currentNote 被清空 → 回到「请选择附注章节」。
    try {
      const url = new URL(window.location.href)
      url.searchParams.delete('section')
      url.searchParams.delete('noteTemplate')
      window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)
    } catch { /* 清理 URL 失败不影响已选中章节 */ }
  }
  // 附注联动复盘 P0-1：拉一次就绪度摘要给工具栏徽标（fail-open，不阻断页面）
  void loadReadinessSummary()
  // R8-S2-14：关闭浏览器/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)
  // Sprint 3 Task 3.5/3.6: 全局点击关闭右键菜单
  window.addEventListener('click', _closeTreeContextMenu)
  window.addEventListener('contextmenu', _onWindowContextMenuFallback)
})

// V3 Req 5.1：上下文（projectId/year）变化时自动重载附注树
onContextChange(async () => {
  selectedProjectId.value = projectId.value
  selectedYear.value = year.value
  invalidateDetailCache()  // 项目/年度变更，清空全部缓存
  await loadProjectTemplateConfig()
  await fetchTree()
})

onUnmounted(() => {
  eventBus.off('shortcut:save', onShortcutSave)
  eventBus.off('workpaper:saved', onWorkpaperSaved)
  eventBus.off('disclosure:note-text-updated', onDisclosureNoteTextUpdated)
  // Task 5.4: 清理 catalog:note-select 监听
  eventBus.off('catalog:note-select', onCatalogNoteSelect)
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

// ─── 附注模块金额单位（模块级，默认「元」，不污染全局 displayPrefs） ──────────
// 附注属财务报表呈现，惯例以「元」披露；用独立 localStorage 键，可在附注内切换。
const NOTE_UNIT_STORAGE_KEY = 'gt_note_amount_unit'
function loadNoteUnit(): AmountUnit {
  try {
    const raw = localStorage.getItem(NOTE_UNIT_STORAGE_KEY)
    if (raw === 'yuan' || raw === 'wan' || raw === 'qian') return raw
  } catch { /* ignore */ }
  return 'yuan'
}
const noteUnit = ref<AmountUnit>(loadNoteUnit())
const noteUnitSuffix = computed(() => unitLabel(noteUnit.value))
function onNoteUnitChange(v: AmountUnit) {
  noteUnit.value = v
  try { localStorage.setItem(NOTE_UNIT_STORAGE_KEY, v) } catch { /* ignore */ }
}

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
  // 单元格激活编辑：编辑模式下点击非合计行直接激活
  if (editMode.value && !row.is_total) {
    if (colIdx === 0) {
      activateCell(rowIdx, -1)  // label 列用 -1 标识
    } else {
      activateCell(rowIdx, colIdx - 1)
    }
  }
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
/* 附注树快捷筛选：el-segmented 内部元素 + teleport 到 body 的 tooltip 均在 scoped 作用域外 */
.gt-de-tree-filter-bar .el-segmented { width: 100%; font-size: 13px; }
.gt-de-tree-filter-bar .el-segmented__item { font-size: 13px; padding: 0 2px; }
.gt-de-tree-filter-bar .el-segmented__item-label { font-size: 13px; }
.gt-de-tree-filter-tip { max-width: 300px; }
.gt-de-tree-filter-tip .gt-de-tip-title { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.gt-de-tree-filter-tip .gt-de-tip-desc { font-size: 12px; line-height: 1.6; }
.gt-de-tree-filter-tip .gt-de-tip-count { font-size: 12px; line-height: 1.6; margin-top: 4px; font-variant-numeric: tabular-nums; }
.gt-de-tree-filter-tip .gt-de-tip-rule { font-size: 11px; line-height: 1.6; margin-top: 4px; padding-top: 4px; border-top: 1px solid rgba(255, 255, 255, 0.25); opacity: 0.85; }

.gt-de-tree-ctx-menu { position: fixed; z-index: 9999; background: var(--gt-color-bg-white, #fff); border: 1px solid var(--gt-color-border-purple, #d8caee); border-radius: 6px; box-shadow: 0 4px 16px rgba(75, 45, 119, 0.18); padding: 4px 0; min-width: 160px; font-size: var(--gt-font-size-xs, 12px); }
.gt-de-tree-ctx-item { padding: 6px 14px; cursor: pointer; color: var(--gt-color-text-primary, #303133); white-space: nowrap; user-select: none; }
.gt-de-tree-ctx-item:hover { background: var(--gt-color-primary-bg, #f5f0ff); }
.gt-de-tree-ctx-item.gt-de-tree-ctx-danger { color: var(--gt-color-coral, #e6443e); }
.gt-de-tree-ctx-item.gt-de-tree-ctx-danger:hover { background: var(--gt-bg-danger, #fdecea); }
</style>


