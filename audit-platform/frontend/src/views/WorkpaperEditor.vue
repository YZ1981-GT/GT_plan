<template>
  <!-- spec workpaper-html-renderer Task 13.1: HTML 渲染器路由分发（A/B/C/D/E/H/skip）
       优先级最高：HTML 类（1346 sheet）走 GtWpRenderer，保留 F/G Univer + form/word/table/hybrid 子编辑器走既有路径 -->
  <GtWpRenderer
    v-if="useHtmlRenderer"
    :wp-id="wpId"
    @save-success="onHtmlSaveSuccess"
    @trigger-procedure-trimming-suggestion="onHtmlTrimmingSuggestion"
    @cross-ref-update="onHtmlCrossRefUpdate"
    @sync-to-disclosure-notes="onHtmlSyncToDisclosureNotes"
    @jump-to-reference="onHtmlJumpToReference"
  />

  <!-- 路由分发：非 univer 类型使用对应子编辑器（须等 wpDetail 加载完成） -->
  <component
    v-else-if="componentType && componentType !== 'univer' && wpDetail"
    :is="editorComponent"
    :project-id="projectId"
    :wp-id="wpId"
    :wp-detail="wpDetail"
    @show-versions="onShowVersions"
    @toggle-panel="showSidePanel = !showSidePanel"
    @saved="onChildSaved"
  />

  <!-- 子编辑器加载中占位 -->
  <div v-else-if="componentType && componentType !== 'univer' && !wpDetail" class="gt-wp-editor-loading">
    <el-icon class="is-loading" :size="32" color="var(--gt-color-primary)"><Loading /></el-icon>
    <div style="margin-top: 12px; font-size: 13px; color: var(--gt-color-text-secondary)">加载底稿中...</div>
  </div>

  <!-- 默认 Univer 编辑器（component_type='univer' 或未配置时；univerContainer 必须挂载触发 initUniver） -->
  <div v-else class="gt-wp-editor gt-fade-in">
    <!-- 编辑锁提示 -->
    <el-alert v-if="editLock?.locked?.value && !editLock?.isMine?.value" type="warning" :closable="false" style="margin-bottom: 8px">
      {{ editLock?.lockedBy?.value || '其他用户' }} 正在编辑，当前为只读模式
    </el-alert>

    <!-- E1 Sprint 2 Task 2.17 + D-sales-cycle F8 Task 2.19: 前置状态横幅 -->
    <el-alert
      v-if="prerequisiteBanner && (wpDetail?.wp_code?.startsWith('E1') || isDCycle || isFCycle || isHCycle || isICycle || isGCycle || isKCycle || isLCycle || isMCycle || isNCycle)"
      :type="prerequisiteBanner.type"
      :closable="false"
      class="gt-prereq-banner"
    >
      <template #default>
        <div class="gt-prereq-banner-content">
          <span>{{ prerequisiteBanner.message }}</span>
          <el-button
            v-if="prerequisiteStatus.overall.value !== 'ready'"
            text
            size="small"
            @click="onJumpToPrereq"
          >去完成 →</el-button>
        </div>
      </template>
    </el-alert>

    <!-- 顶部工具栏 -->
    <div class="gt-wp-editor-toolbar">
      <div class="gt-wp-editor-toolbar-left">
        <!-- Sprint 4 Task 11.3: 底稿间导航返回面包屑 -->
        <el-button v-if="wpNavHistory.canGoBack.value" text size="small" @click="wpNavHistory.goBack()" class="gt-wp-nav-breadcrumb">
          ← 返回 {{ wpNavHistory.lastItem.value?.wpCode }} {{ wpNavHistory.lastItem.value?.rowRef || '' }}
        </el-button>
        <el-button v-else text @click="goBack">← 返回</el-button>
        <span class="gt-wp-editor-code" v-if="wpDetail">{{ wpDetail.wp_code }}</span>
        <span class="gt-wp-editor-name" v-if="wpDetail">{{ wpDetail.wp_name }}</span>
        <el-tag v-if="wpDetail" :type="(statusTagType(wpDetail.status)) || undefined" size="small">
          {{ statusLabel(wpDetail.status) }}
        </el-tag>
        <span v-if="dirty" class="gt-dirty-indicator">● 有未保存的变更</span>
        <!-- Sprint 4 Task 9.2: 底稿填写完成度可视化 -->
        <el-progress
          v-if="completionRate.total > 0"
          type="circle"
          :percentage="completionRate.percentage"
          :width="36"
          :stroke-width="3"
          class="gt-wp-completion-circle"
        />
      </div>
      <div class="gt-wp-editor-toolbar-right">
        <!-- E1 Sprint 2 Task 2.18: 复核状态 badge（L1-L5 + 专委会/IT/税务） -->
        <ReviewLayerBadges
          v-if="wpDetail?.wp_code?.startsWith('E1')"
          :project-id="projectId"
          :wp-id="wpId"
          :wp-code="wpDetail?.wp_code"
        />
        <!-- Sprint 4 Task 12.1: 渲染模式手动切换按钮（仅 A/B/D/E 类显示） -->
        <el-button
          v-if="canSwitchRenderer"
          size="small"
          @click="onToggleRendererMode"
          style="margin-right: 8px"
        >{{ useHtmlRenderer ? '切换为表格模式' : '切换为 HTML 模式' }}</el-button>
        <!-- 审计导航图入口：点击弹出全屏抽屉 -->
        <el-button
          v-if="hasAuditNav"
          size="small"
          @click="showAuditNavDrawer = true"
          style="margin-right: 8px"
        >🧭 审计导航图</el-button>
        <!-- 关键操作组：保存 / 一键填充 / 提交复核（高亮） -->
        <el-button-group class="gt-wp-toolbar-primary">
          <el-button
            size="small"
            type="primary"
            @click="onSave"
            :loading="saving"
          >💾 保存</el-button>
          <el-tooltip
            placement="bottom"
            :content="hasPrefillMapping ? '从试算表重新取数填入底稿' : '当前底稿无预设公式配置'"
          >
            <el-button
              size="small"
              type="primary"
              plain
              @click="onRefreshPrefill"
              :loading="prefillLoading"
              :disabled="!hasPrefillMapping"
            >📊 一键填充</el-button>
          </el-tooltip>
          <el-tooltip
            v-if="wpDetail && wpDetail.status === WP_STATUS.DRAFT && fineCheckFailCount > 0"
            placement="bottom"
            :content="`当前有 ${fineCheckFailCount} 项自检未通过`"
          >
            <el-button
              size="small"
              type="warning"
              @click="onSubmitForReview"
              :loading="submitting"
              :disabled="dirty"
            >⚠️ 提交复核 ({{ fineCheckFailCount }})</el-button>
          </el-tooltip>
          <el-button
            v-else-if="wpDetail && wpDetail.status === WP_STATUS.DRAFT"
            size="small"
            type="success"
            @click="onSubmitForReview"
            :loading="submitting"
            :disabled="dirty"
          >📨 提交复核</el-button>
        </el-button-group>

        <!-- 次要操作：更多 dropdown -->
        <el-dropdown trigger="click" placement="bottom-end">
          <el-button size="small" plain>更多 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="onSyncStructure">🔄 同步公式</el-dropdown-item>
              <el-dropdown-item @click="onShowVersions">📋 版本历史</el-dropdown-item>
              <el-dropdown-item @click="onDownload">📥 下载</el-dropdown-item>
              <el-dropdown-item @click="onExportPdf" v-permission="'workpaper:export'">📄 导出 PDF</el-dropdown-item>
              <el-dropdown-item @click="onUpload" divided>📤 上传新版本</el-dropdown-item>
              <el-dropdown-item @click="showOfflineExportDialog = true" divided>📤 导出填写模板</el-dropdown-item>
              <el-dropdown-item @click="showOfflineImportDialog = true">📥 导入填写结果</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <!-- 面板按钮 -->
        <el-badge :value="fineCheckFailCount" :max="99" :hidden="fineCheckFailCount === 0" type="danger">
          <el-button size="small" @click="showSidePanel = !showSidePanel">📋 面板</el-button>
        </el-badge>
        <!-- E1 Sprint 2 Task 2.33: 工具栏"🔄 刷新取数"按钮 -->
        <el-tooltip placement="bottom" content="重新执行预填充并触发受影响 sheet 刷新">
          <el-button size="small" plain :loading="manualRefreshing" @click="onManualRefresh">🔄 刷新取数</el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- Step Navigation Bar (P0: step_sheet_mapping) -->
    <div v-if="stepMapping.data.value?.steps?.length" class="gt-step-nav">
      <div class="gt-step-nav__progress">
        <span class="gt-step-nav__label">
          步骤 {{ stepMapping.currentStepIndex.value + 1 }}/{{ stepMapping.totalSteps.value }}
        </span>
        <span class="gt-step-nav__name">{{ stepMapping.currentStep.value?.step_name }}</span>
        <span v-if="stepMapping.currentTargetSheets.value?.length" class="gt-step-nav__sheet">
          → {{ stepMapping.currentTargetSheets.value[0] }}
        </span>
      </div>
      <div class="gt-step-nav__actions">
        <el-button size="small" :disabled="stepMapping.currentStepIndex.value === 0" @click="stepMapping.prevStep()">上一步</el-button>
        <el-button size="small" type="primary" :disabled="stepMapping.currentStepIndex.value >= stepMapping.totalSteps.value - 1" @click="stepMapping.nextStep()">下一步</el-button>
      </div>
    </div>

    <!-- Stale 影响范围横条（保存后显示，自动收起） -->
    <div v-if="showStaleImpactPanel && staleImpact.totalAffected.value > 0" class="gt-stale-impact-bar">
      <div class="gt-stale-impact-bar__head">
        <span class="gt-stale-impact-bar__title">
          ⚠ 本次保存影响 <strong>{{ staleImpact.totalAffected.value }}</strong> 个下游对象
        </span>
        <el-button text size="small" @click="showStaleImpactPanel = false">收起</el-button>
      </div>
      <div class="gt-stale-impact-bar__list">
        <el-tag
          v-for="(item, idx) in staleImpact.affected.value.slice(0, 12)"
          :key="`stale-${idx}`"
          size="small"
          :type="staleImpactTagType(item)"
          class="gt-stale-impact-bar__tag"
          @click="onStaleItemClick(item)"
        >
          {{ formatStaleItem(item) }}
        </el-tag>
        <span v-if="staleImpact.affected.value.length > 12" class="gt-stale-impact-bar__more">
          +{{ staleImpact.affected.value.length - 12 }} 个
        </span>
      </div>
    </div>

    <!-- 版本历史抽屉（任务 8.19.1）+ S-4 历史版本搜索 -->
    <el-drawer
      v-model="showVersionDrawer"
      title="版本历史"
      direction="rtl"
      size="420px"
    >
      <!-- S-4 (proposal-remaining-18 task 5.4)：历史版本搜索 -->
      <VersionHistorySearch
        v-if="showVersionDrawer && wpId"
        :wp-id="wpId"
        style="margin-bottom: 16px"
        @jump="onVersionSearchJump"
      />
      <el-divider style="margin: 8px 0" />
      <div v-loading="versionLoading">
        <el-empty v-if="!versionLoading && versionList.length === 0" description="暂无历史版本" />
        <el-timeline v-else>
          <el-timeline-item
            v-for="v in versionList"
            :key="v.version || v.id"
            :timestamp="v.created_at ? v.created_at.slice(0, 19) : ''"
            placement="top"
          >
            <div style="font-weight: 600">v{{ v.version ?? v.file_version ?? '—' }}</div>
            <div v-if="v.note || v.description" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-top: 4px">
              {{ v.note || v.description }}
            </div>
            <div v-if="v.created_by_name || v.created_by" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 2px">
              {{ v.created_by_name || v.created_by }}
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>

    <!-- Univer 编辑区（左侧 Sheet 导航 + 右侧 Univer 画布） -->
    <div class="gt-wp-editor-main">
      <!-- Loading overlay（v-if，加载完即移除）-->
      <!-- spec workpaper-editor-refactor Phase 5.1: 用 GtLoadingOverlay 替代内嵌 overlay -->
      <GtLoadingOverlay
        :visible="loading"
        text="正在加载底稿..."
        :hint="loadingHint"
        :size="32"
      />

      <!-- spec workpaper-editor-refactor Phase 4.1: 加载失败友好引导（替代粗暴 goBack）-->
      <div v-if="!loading && loadErrorState" class="gt-wp-editor-error-overlay">
        <div class="gt-wp-editor-error-card">
          <div class="gt-wp-editor-error-icon">
            <span v-if="loadErrorState === 'no_file'">📄</span>
            <span v-else-if="loadErrorState === 'no_index'">🔍</span>
            <span v-else-if="loadErrorState === 'invalid_id'">⚠️</span>
            <span v-else>❌</span>
          </div>
          <div class="gt-wp-editor-error-title">
            <template v-if="loadErrorState === 'no_file'">底稿文件尚未生成</template>
            <template v-else-if="loadErrorState === 'no_index'">底稿不存在</template>
            <template v-else-if="loadErrorState === 'invalid_id'">底稿 ID 不合法</template>
            <template v-else>加载底稿失败</template>
          </div>
          <div class="gt-wp-editor-error-message">{{ loadErrorMessage }}</div>
          <div class="gt-wp-editor-error-actions">
            <el-button size="small" @click="goBack">返回底稿列表</el-button>
            <el-button
              v-if="loadErrorState === 'no_file'"
              size="small"
              type="primary"
              @click="goToLifecycle"
            >前往生命周期</el-button>
            <el-button
              v-if="loadErrorState === 'error'"
              size="small"
              type="primary"
              @click="onRetryLoad"
            >重试</el-button>
          </div>
        </div>
      </div>
      <!-- 左侧 Sheet 导航：v-show 保持 DOM（数据未就绪也先占位）-->
      <div v-show="!loading" class="gt-wp-editor-left-col">
        <UniverSheetNav
          :groups="sheetNav.groups.value"
          :active-sheet-id="sheetNav.activeSheetId.value"
          :total-count="sheetNav.totalCount.value"
          :collapsed="sheetNavCollapsed"
          @switch="onSwitchSheet"
          @toggle-collapsed="sheetNavCollapsed = !sheetNavCollapsed"
        />
        <!-- H 固定资产循环 task 2.4: 折旧/减值分支选择器（多版本 sheet 时显示） -->
        <DepreciationBranchSelector
          v-if="isHCycle && hBranchSelector.branches.value.length > 1"
          :branches="hBranchSelector.branches.value"
          :active-branch="hBranchSelector.activeBranch.value"
          @switch="hBranchSelector.switchBranch"
        />
        <!-- I 无形资产循环 task 2.1: 摊销分支选择器（I1-10/I1-11 / I4-6/I4-7） -->
        <DepreciationBranchSelector
          v-if="isICycle && iBranchSelector.branches.value.length > 1"
          :branches="iBranchSelector.branches.value"
          :active-branch="iBranchSelector.activeBranch.value"
          @switch="iBranchSelector.switchBranch"
        />
        <!-- E1 Sprint 2 Task 2.7: B/C/D/E 类弹窗入口按钮 -->
        <ProcedureDialogLauncher
          v-if="wpDetail && wpDetail.wp_code && wpDetail.wp_code.startsWith('E1')"
          :project-id="projectId"
          :wp-id="wpId"
          :wp-code="wpDetail.wp_code"
        />
        <!-- spec workpaper-editor-slimdown Sprint 2 Task 3.4: CycleDialogSlot 配置驱动替代 17 个 trigger + dialog -->
        <CycleDialogSlot
          v-if="wpDetail"
          :wp-detail="wpDetail"
          :project-id="projectId"
          :wp-id="wpId"
          :active-sheet-id="sheetNav.activeSheetId.value || ''"
          @child-saved="onChildSaved"
        />
      </div>
      <!-- 中间内容区：顶部 sheet tabs + Univer 画布（垂直布局） -->
      <div class="gt-wp-editor-center-col">
        <!-- 顶部水平 sheet 切换栏：避免用户滚到底部找 tab -->
        <SheetTopTabs
          :sheets="flatSheets"
          :active-sheet-id="sheetNav.activeSheetId.value"
          @switch="onSwitchSheet"
        />
        <!-- Univer 画布容器：始终 mount（Univer 需要 DOM 节点初始化）-->
        <div class="gt-wp-editor-univer-wrapper">
          <div ref="univerContainer" class="gt-wp-editor-univer"></div>
        </div>
      </div>

      <!-- Task 2.2: Prefill cell hover tooltip (floating div for canvas-based Univer) -->
      <div
        v-if="prefillTooltip.visible"
        class="gt-wp-prefill-tooltip"
        :style="{ left: prefillTooltip.x + 'px', top: prefillTooltip.y + 'px' }"
      >
        {{ prefillTooltip.text }}
      </div>

      <!-- Task 2.3: Cross-module reference overlay -->
      <div class="gt-cross-ref-overlay" v-if="crossRefTags.length > 0">
        <div
          v-for="tag in crossRefTags"
          :key="tag.id"
          class="gt-cross-ref-tag"
          :style="{ left: tag.x + 'px', top: tag.y + 'px', backgroundColor: tag.color }"
          @click="router.push(tag.route)"
          :title="tag.label"
        >
          {{ tag.label }}
        </div>
      </div>
    </div>

    <!-- Task 2.2: Formula bar showing prefill source when cell selected -->
    <div v-if="formulaBarText" class="gt-wp-formula-bar">
      <span class="gt-wp-formula-bar-label">ƒ</span>
      <span class="gt-wp-formula-bar-text">{{ formulaBarText }}</span>
    </div>

    <!-- Sprint 5.5: 查看公式详情弹窗 -->
    <CellFormulaDetail
      :visible="showCellFormulaDetail"
      :wp-code="wpDetail?.wp_code || ''"
      :sheet-name="cellDetailSheet"
      :label="cellDetailLabel"
      @update:visible="showCellFormulaDetail = $event"
      @navigate="onCellDetailNavigate"
    />

    <!-- 审计导航图全屏对话框（默认全屏，支持拖拽调整） -->
    <el-dialog
      v-model="showAuditNavDrawer"
      :fullscreen="auditNavFullscreen"
      :width="auditNavFullscreen ? '100%' : '85%'"
      :show-close="false"
      append-to-body
      class="gt-audit-nav-dialog"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <template #header>
        <div class="gt-audit-nav-dialog__header">
          <div class="gt-audit-nav-dialog__title">
            <span class="gt-audit-nav-dialog__icon">🧭</span>
            <span>审计导航图</span>
            <span v-if="wpDetail?.wp_code" class="gt-audit-nav-dialog__code">{{ wpDetail.wp_code }}</span>
            <span v-if="wpDetail?.wp_name" class="gt-audit-nav-dialog__name">{{ wpDetail.wp_name }}</span>
          </div>
          <div class="gt-audit-nav-dialog__actions">
            <el-button size="small" text :icon="auditNavFullscreen ? undefined : undefined" @click="auditNavFullscreen = !auditNavFullscreen">
              {{ auditNavFullscreen ? '⊟ 退出全屏' : '⊞ 全屏' }}
            </el-button>
            <el-button size="small" text @click="showAuditNavDrawer = false">✕</el-button>
          </div>
        </div>
      </template>
      <div class="gt-audit-nav-dialog__body">
        <WorkpaperAuditNav
          v-if="hasAuditNav"
          :project-id="projectId"
          :wp-id="wpId"
          :wp-code="wpDetail?.wp_code || 'E1'"
        />
      </div>
    </el-dialog>

    <!-- Task 2.4: Review mark dialog -->
    <el-dialog v-model="showReviewDialog" title="✓ 标记复核" width="400" append-to-body>
      <el-form label-width="70px">
        <el-form-item label="单元格">
          <span>{{ reviewDialogCell.sheet }}!{{ reviewDialogCell.cellRef }}</span>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="reviewDialogStatus">
            <el-radio value="reviewed">已复核</el-radio>
            <el-radio value="pending">待确认</el-radio>
            <el-radio value="questioned">有疑问</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="reviewDialogComment" type="textarea" :rows="3" placeholder="可选：输入复核意见" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReviewDialog = false">取消</el-button>
        <el-button type="primary" @click="onMarkReview">确认标记</el-button>
      </template>
    </el-dialog>

    <!-- 底部状态栏 -->
    <div class="gt-wp-editor-statusbar" v-if="wpDetail">
      <span>编制人: {{ resolveUserName(wpDetail.assigned_to) }}</span>
      <span>复核人: {{ resolveUserName(wpDetail.reviewer) }}</span>
      <span>版本: v{{ wpDetail.file_version || 1 }}</span>
      <span v-if="wpDetail.updated_at">最后修改: {{ wpDetail.updated_at.slice(0, 19) }}</span>
      <span v-if="autoSaveMsg" style="color: var(--gt-color-success)">✓ {{ autoSaveMsg }}</span>
      <span v-if="dirty" style="color: var(--gt-color-wheat)">● 未保存</span>
      <span v-if="smartTip" class="gt-wp-smart-tip" @click="showSmartTipDetail = !showSmartTipDetail">
        💡 {{ smartTip.summary }}
      </span>
    </div>

    <!-- 智能提示详情 -->
    <div v-if="showSmartTipDetail && smartTip" class="gt-wp-smart-tip-detail">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:600;font-size: var(--gt-font-size-sm)">💡 审计关注点</span>
        <el-button size="small" text @click="showSmartTipDetail = false">收起</el-button>
      </div>
      <div v-if="smartTip.warnings?.length" style="margin-bottom:6px">
        <div v-for="(w, i) in smartTip.warnings" :key="i" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); padding: 2px 0">⚠️ {{ w }}</div>
      </div>
      <div v-if="smartTip.tips?.length">
        <div v-for="(t, i) in smartTip.tips" :key="i" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); padding: 1px 0">• {{ t }}</div>
      </div>
    </div>

    <!-- R7-S3-05 Task 25：底稿右栏面板（抽屉模式） -->
    <el-drawer
      v-model="showSidePanel"
      direction="rtl"
      size="400px"
      :with-header="false"
      :modal="false"
      append-to-body
    >
      <WorkpaperSidePanel
        :project-id="projectId"
        :wp-id="wpId"
        :wp-code="wpDetail?.wp_code"
        @finecheck-update="fineCheckFailCount = $event"
      />
    </el-drawer>
  </div>

  <!-- 非 Univer 编辑器的侧面板（共享） -->
  <el-drawer
    v-if="!useHtmlRenderer && componentType && componentType !== 'univer'"
    v-model="showSidePanel"
    direction="rtl"
    size="400px"
    :with-header="false"
    :modal="false"
    append-to-body
  >
    <WorkpaperSidePanel
      :project-id="projectId"
      :wp-id="wpId"
      :wp-code="wpDetail?.wp_code"
      @finecheck-update="fineCheckFailCount = $event"
    />
  </el-drawer>

  <!-- Sprint 4 Task 15.13: 底稿离线导出/导入对话框 -->
  <WpOfflineExportDialog
    v-model="showOfflineExportDialog"
    :wp-id="wpId"
    :available-sheets="availableSheetNames"
  />
  <WpOfflineImportDialog
    v-model="showOfflineImportDialog"
    :wp-id="wpId"
    @imported="onOfflineImported"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmSubmitReview, confirmLeave, confirmVersionConflict } from '@/utils/confirm'
import { Loading } from '@element-plus/icons-vue'
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
// @ts-ignore - locale file has no type declarations
import UniverPresetSheetsCoreZhCN from '@univerjs/preset-sheets-core/lib/locales/zh-CN'
import '@univerjs/preset-sheets-core/lib/index.css'
import {
  downloadWorkpaper,
  getWorkpaper,
  type WorkpaperDetail,
} from '@/services/workpaperApi'
import { rebuildWorkpaperStructure, listUsers } from '@/services/commonApi'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { useWorkpaperReviewMarkers, type ReviewMarkerTicket } from '@/composables/useWorkpaperReviewMarkers'
import { useEditingLock } from '@/composables/useEditingLock'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { usePrefillMarkers } from '@/composables/usePrefillMarkers'
import { useCrossModuleRefs, TARGET_COLOR_MAP } from '@/composables/useCrossModuleRefs'
import { useReviewMarks, type ReviewStatus } from '@/composables/useReviewMarks'
import { useUserOverrides } from '@/composables/useUserOverrides'
import { useStepMapping } from '@/composables/useStepMapping'
import { useStaleImpact, type StaleAffectedItem } from '@/composables/useStaleImpact'
import { type SheetGroup } from '@/composables/useUniverSheetNav'
import { useDepreciationBranchSelector } from '@/composables/useDepreciationBranchSelector'
import { useICycleEditor } from '@/composables/useICycleEditor'
import DepreciationBranchSelector from '@/components/workpaper/DepreciationBranchSelector.vue'
import WorkpaperSidePanel from '@/components/workpaper/WorkpaperSidePanel.vue'
import UniverSheetNav from '@/components/workpaper/UniverSheetNav.vue'
import SheetTopTabs from '@/components/workpaper/SheetTopTabs.vue'
import WorkpaperAuditNav from '@/components/workpaper/WorkpaperAuditNav.vue'
import ProcedureDialogLauncher from '@/components/workpaper/ProcedureDialogLauncher.vue'
// spec workpaper-editor-slimdown Sprint 2 Task 3.4: CycleDialogSlot 配置驱动替代 17 个 dialog 组件
import CycleDialogSlot from '@/components/workpaper/CycleDialogSlot.vue'
// Sprint 4 Task 15.13: 底稿离线导出/导入对话框
import WpOfflineExportDialog from '@/components/workpaper/WpOfflineExportDialog.vue'
import WpOfflineImportDialog from '@/components/workpaper/WpOfflineImportDialog.vue'
// proposal-remaining-18 task 5.4 (S-4)：历史版本搜索
import VersionHistorySearch from '@/components/workpaper/VersionHistorySearch.vue'
import ReviewLayerBadges from '@/components/workpaper/ReviewLayerBadges.vue'
import { usePrerequisiteStatus } from '@/composables/usePrerequisiteStatus'
import { useCycleType } from '@/composables/useCycleType'
import { useWorkpaperRefresh } from '@/composables/useWorkpaperRefresh'
// spec workpaper-html-renderer Task 13.1: HTML 渲染器路由分发
import GtWpRenderer from '@/components/workpaper/GtWpRenderer.vue'
import { useWpClassification } from '@/composables/useWpClassification'
import { useWpCompletionRate } from '@/composables/useWpCompletionRate'
import { useWpNavigationHistory } from '@/composables/useWpNavigationHistory'
import CellFormulaDetail from '@/components/CellFormulaDetail.vue'
import GtLoadingOverlay from '@/components/common/GtLoadingOverlay.vue'
import { WP_STATUS } from '@/constants/statusEnum'
import { handleApiError } from '@/utils/errorHandler'

// ─── 动态编辑器组件（按 component_type 路由分发） ───────────────────────────

const WorkpaperFormEditor = defineAsyncComponent(() => import('./WorkpaperFormEditor.vue'))
const WorkpaperWordEditor = defineAsyncComponent(() => import('./WorkpaperWordEditor.vue'))
const WorkpaperTableEditor = defineAsyncComponent(() => import('./WorkpaperTableEditor.vue'))
const WorkpaperHybridEditor = defineAsyncComponent(() => import('./WorkpaperHybridEditor.vue'))

const EDITOR_MAP: Record<string, any> = {
  form: WorkpaperFormEditor,
  word: WorkpaperWordEditor,
  table: WorkpaperTableEditor,
  hybrid: WorkpaperHybridEditor,
}
// ─────────────────────────────────────────────────────────────────────────────

const DIRTY_COMMAND_PATTERNS = [
  'set-range-values', 'set-cell',
  'set-formula', 'formula.', 'array-formula',
  'set-style', 'set-border', 'set-number-format', 'set-font',
  'clear-selection', 'delete-range',
  'insert-row', 'insert-col', 'remove-row', 'remove-col',
  'merge-cells', 'unmerge-cells',
]

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const wpId = computed(() => route.params.wpId as string)

// 核心数据 ref（必须在所有依赖它们的 computed/composable 调用前定义，否则触发 ReferenceError）
const wpDetail = ref<WorkpaperDetail | null>(null)
const loading = ref(true)
// 加载阶段提示（用户感知）：null/空字符串则不显示 hint
const loadingHint = ref('')
// 加载失败状态（spec workpaper-editor-refactor Phase 4.1：错误友好提示，不再粗暴 goBack）
// 参考 useWpDetailGuard 状态机：'no_file' / 'no_index' / 'invalid_id' / 'error'
const loadErrorState = ref<'no_file' | 'no_index' | 'invalid_id' | 'error' | null>(null)
const loadErrorMessage = ref('')

// ─── component_type 路由逻辑 ─────────────────────────────────────────────────
const componentType = ref<string>('univer')
const editorComponent = computed(() => EDITOR_MAP[componentType.value] || null)

// spec workpaper-html-renderer Task 13.1: HTML 渲染器路由分发（9 类）
// HTML 类 componentType 白名单（与 GtWpRenderer 子组件分发一致）
const HTML_COMPONENT_TYPES = new Set([
  'a-program-console',
  'b-index',
  'c-note-table',
  'd-form-table',
  'd-form-paragraph',
  'd-form-qa',
  'd-form-confirmation',
  'd-form-review',
  'e-control-test',
  'h-static-doc',
  'skip',
])
// 通过 useWpClassification 解析 wp_code 对应的 HTML componentType；保留 Univer 类（F/G 558 sheet）走既有路径
const wpCodeRef = computed(() => wpDetail.value?.wp_code || '')
const wpClassification = useWpClassification(wpCodeRef, projectId)
const htmlComponentType = computed(() => {
  // 仅当后端归类成功加载（非默认 skip 兜底）且为 HTML 类时返回具体 componentType
  // 其他情况（loading / load 失败 / Univer 类 / 委派模块）返回空字符串走既有 Univer/子编辑器路径
  // 这样不会因为后端归类记录缺失而让旧 Univer 底稿被错误地路由到 skip placeholder
  if (!wpClassification.classification.value) return ''
  if (!wpClassification.classification.value.classifications?.length) return ''
  const ct = wpClassification.componentType.value
  return HTML_COMPONENT_TYPES.has(ct as string) ? (ct as string) : ''
})
const useHtmlRenderer = computed(() => !!htmlComponentType.value)

// Sprint 4 Task 12: 渲染模式手动切换
const rendererOverride = ref<string | null>(null)
const canSwitchRenderer = computed(() => {
  // 仅 A/B/D/E 类显示切换按钮
  const code = wpDetail.value?.wp_code || ''
  return /^[ABDE]/i.test(code)
})

async function onToggleRendererMode() {
  const newMode = useHtmlRenderer.value ? 'univer' : (htmlComponentType.value || 'univer')
  try {
    await httpApi.post('/api/wp-classifications/override', {
      project_id: projectId.value,
      wp_code: wpDetail.value?.wp_code,
      renderer_override: newMode,
    })
    rendererOverride.value = newMode
    // Reload to apply new mode
    window.location.reload()
  } catch (e) {
    handleApiError(e, '切换渲染模式失败')
  }
}

// Sprint 4 Task 9.2: 底稿填写完成度（Univer 路径使用 wpDetail.parsed_data 简化计算）
const _completionComponentType = computed(() => htmlComponentType.value || componentType.value)
const _completionSchema = computed(() => ({}))
const _completionHtmlData = computed(() => wpDetail.value?.parsed_data?.html_data ?? {})
const { rate: completionRate } = useWpCompletionRate(_completionComponentType, _completionSchema, _completionHtmlData)

// Sprint 4 Task 11: 底稿间导航历史
const wpNavHistory = useWpNavigationHistory()

// wp_code 就绪后自动加载归类
watch(
  () => [wpCodeRef.value, projectId.value] as const,
  ([code, pid]) => {
    if (code && pid) {
      wpClassification.load().catch(() => { /* 静默：归类失败回退到 Univer 路径 */ })
    }
  },
  { immediate: true },
)

/** 从后端获取 component_type（wp_template_metadata 或底稿详情） */
async function fetchComponentType() {
  try {
    const detail = await httpApi.get(P_wp.detail(projectId.value, wpId.value))
    // component_type 可能来自 detail 本身或 template_metadata
    const ct = detail?.component_type || detail?.template_metadata?.component_type || 'univer'
    componentType.value = ct
    // 同时缓存 wpDetail 供子编辑器使用
    if (detail) wpDetail.value = detail
  } catch {
    componentType.value = 'univer'
  }
}

/** 子编辑器保存后的回调 */
function onChildSaved() {
  eventBus.emit('workpaper:saved', {
    projectId: projectId.value,
    wpId: wpId.value,
  } as WorkpaperSavedPayload)
}

/** HTML 渲染器保存成功回调 — 检测 c-note-table 类型触发附注同步（US-3） */
async function onHtmlSaveSuccess(payload: { sheet_name: string; html_data: Record<string, any> }) {
  // 先触发通用保存事件
  onChildSaved()

  // US-3: 检测 c-note-table 类型触发 disclosure_notes 同步
  if (htmlComponentType.value === 'c-note-table' && payload?.html_data?.sub_table_data) {
    try {
      await httpApi.post(
        `/api/wp-disclosure-sync/${wpId.value}/sync-html`,
        {
          sheet_name: payload.sheet_name,
          sub_table_data: payload.html_data.sub_table_data,
        },
      )
    } catch (e: any) {
      if (e?.response?.status === 409 || e?.status === 409) {
        // 冲突弹窗（US-3 验收标准 4）
        try {
          await ElMessageBox.confirm(
            '附注模块有更新的手动编辑，是否覆盖？',
            '同步冲突',
            {
              distinguishCancelAndClose: true,
              confirmButtonText: '覆盖',
              cancelButtonText: '保留附注版本',
              type: 'warning',
            },
          )
          // 用户选择覆盖 → 强制同步
          await httpApi.post(
            `/api/wp-disclosure-sync/${wpId.value}/sync-html?force=true`,
            {
              sheet_name: payload.sheet_name,
              sub_table_data: payload.html_data.sub_table_data,
            },
          )
          ElMessage.success('附注已同步')
        } catch {
          // 用户取消或关闭 → 保留附注版本，不做任何操作
        }
      } else {
        // 非冲突错误 → 静默记录（不阻断保存主流程）
        console.warn('[WorkpaperEditor] disclosure sync failed:', e)
      }
    }
  }
}

// spec workpaper-html-renderer Task 13.1: GtWpRenderer 事件 → 既有 handlers 桥接
/** HTML E 控制测试结论 → 程序裁剪建议（forward 到 ProcedureTrimming 联动）
 *  设计文档说明：E 控制测试组件检测到"控制有效"时建议项目级 ProcedureTrimming 对应项；
 *  本 forward 只做日志 + 复用 procedure-status:changed 通知 procedureTrimming 联动；
 *  实际写回（项目级 ProcedureTrimming 标记）由后端 GtEControlTest save 端点处理。
 */
function onHtmlTrimmingSuggestion(payload: Record<string, any>) {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.debug('[WorkpaperEditor] procedure trimming suggestion from HTML renderer:', payload)
  }
}

/** HTML 跨底稿引用变更 → 复用既有 cross-ref:updated 事件 */
function onHtmlCrossRefUpdate(payload: { source_wp_code: string; target_wp_code: string; cell: string; old_value?: any; new_value?: any }) {
  eventBus.emit('cross-ref:updated', {
    projectId: projectId.value,
    targetWpCode: payload.target_wp_code,
    changedSheets: [],
  } as any)
}

/** HTML C 附注 → disclosure_notes 单向同步触发（占位：实际 API 调用由组件内部处理） */
function onHtmlSyncToDisclosureNotes(_payload: Record<string, any>) {
  // C 附注组件已直接调用 /api/projects/{pid}/disclosure-notes/sync-from-workpaper
  // 此处仅触发 UI 提示，避免重复调用
}

/** HTML 索引跳转：跨底稿 / 同底稿 sheet */
function onHtmlJumpToReference(refCode: string) {
  if (!refCode) return
  // 简化实现：直接走 WorkpaperList 高亮（GtIndexChip 内部已处理大多数路由场景）
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { highlight: refCode },
  })
}
// ─────────────────────────────────────────────────────────────────────────────

const editLock = useEditingLock({
  resourceId: computed(() => wpId.value || ''),
  // WorkpaperEditor 天然编辑模式，mount 时即 acquire
})

// P0: 程序步骤→Sheet映射导航
const stepMapping = useStepMapping(wpId.value || '')

// Address Registry V2: 单元格变更影响范围（stale 传播链）
const staleImpact = useStaleImpact(computed(() => wpDetail.value?.wp_code?.split('-')[0] || ''))
const showStaleImpactPanel = ref(false)

// 左侧 Sheet 导航（univerAPIRef 在 createUniver 后赋值，参见下方 init() 函数）
const univerAPIRef = ref<any>(null)
// E1 Sprint 2 Task 2.3 + 2.37: scenarioFilter 驱动 sheet 显隐 + 双区显隐
const projectMeta = ref<{ scenario: string; has_foreign_currency: boolean; measurement_model?: string } | null>(null)
const scenarioFilter = computed(() => {
  if (!projectMeta.value) return null
  return {
    scenario: projectMeta.value.scenario || 'normal',
    hasForeignCurrency: !!projectMeta.value.has_foreign_currency,
  }
})
// Sprint 2 F5 task 2.6: D 销售循环按 wp_code 路由到 useDSalesCycleSheetGroups，其余用 useUniverSheetNav
// spec workpaper-editor-refactor Phase 2 — 11 处 isXCycle computed 集中到 useCycleType composable
const cycleType = useCycleType(wpDetail)
const isBCycle = cycleType.isBCycle
const isCCycle = cycleType.isCCycle
const isDCycle = cycleType.isDCycle
const isFCycle = cycleType.isFCycle
const isGCycle = cycleType.isGCycle
const isHCycle = cycleType.isHCycle
const isICycle = cycleType.isICycle
const isKCycle = cycleType.isKCycle
const isLCycle = cycleType.isLCycle
const isMCycle = cycleType.isMCycle
const isNCycle = cycleType.isNCycle

// spec workpaper-editor-refactor Phase 2-3: Sheet 导航 facade 集中到 useSheetNavFacade composable
import { useSheetNavFacade } from '@/composables/useSheetNavFacade'
const measurementModelRef = computed(() => projectMeta.value?.measurement_model || 'cost')
const sheetNavFacade = useSheetNavFacade(univerAPIRef, wpDetail, cycleType, scenarioFilter, measurementModelRef)
const sheetNav = {
  groups: sheetNavFacade.groups,
  activeSheetId: sheetNavFacade.activeSheetId,
  totalCount: sheetNavFacade.totalCount,
  switchTo: sheetNavFacade.switchTo,
  refresh: sheetNavFacade.refresh,
  applyForeignCurrencyVisibility: sheetNavFacade.applyForeignCurrencyVisibility,
}
const sheetNavGroups = sheetNavFacade.groups
const sheetNavActiveId = sheetNavFacade.activeSheetId
const flatSheets = sheetNavFacade.flatSheets
// 暴露各循环 nav 实例供 branch selector 使用
const hCycleNav = sheetNavFacade.hCycleNav
const iCycleNav = sheetNavFacade.iCycleNav
const sheetNavCollapsed = ref(false)

// spec workpaper-editor-refactor Phase 2 Task 2.3: D 循环逻辑接入 useDCycleEditor composable
import { useDCycleEditor } from '@/composables/useDCycleEditor'
const dCycle = useDCycleEditor(wpDetail, projectId, sheetNavFacade, onRefreshPrefill)

// spec workpaper-editor-refactor Phase 3 Task 3.1: E 循环逻辑接入 useECycleEditor composable
import { useECycleEditor } from '@/composables/useECycleEditor'
const hasForeignCurrency = computed(() => !!projectMeta.value?.has_foreign_currency)
const eCycle = useECycleEditor(wpDetail, sheetNavFacade, hasForeignCurrency)

// spec workpaper-editor-refactor Phase 3 Task 3.2: F 循环逻辑接入 useFCycleEditor composable（实例化在 cycleDialogs 之后）
import { useFCycleEditor } from '@/composables/useFCycleEditor'

// H 固定资产循环 task 2.4: 折旧/减值分支选择器
const hActiveSheetName = computed(() => {
  if (!isHCycle.value) return ''
  const activeId = hCycleNav.activeSheetId.value
  const sheet = hCycleNav.sheets.value.find((s: any) => s.id === activeId)
  return sheet?.name || ''
})
const hAllSheetNames = computed(() => {
  if (!isHCycle.value) return []
  return hCycleNav.sheets.value.map((s: any) => s.name)
})
const hBranchSelector = useDepreciationBranchSelector(
  hActiveSheetName,
  hAllSheetNames,
  (sheetName: string) => {
    // 找到目标 sheet 的 id 并切换
    const target = hCycleNav.sheets.value.find((s: any) => s.name === sheetName)
    if (target) hCycleNav.switchTo(target.id)
  },
)

// I 无形资产循环 task 2.1 + task 2.4: 摊销分支选择器（I1-10/I1-11 / I4-6/I4-7）
// 委托 useICycleEditor composable（Phase 3 Task 3.4） — 实例化在 cycleDialogs 之后
import { useGCycleEditor } from '@/composables/useGCycleEditor'
import { useKCycleEditor } from '@/composables/useKCycleEditor'
import { useLCycleEditor } from '@/composables/useLCycleEditor'
import { useMCycleEditor } from '@/composables/useMCycleEditor'
import { useNCycleEditor } from '@/composables/useNCycleEditor'

// E1 Sprint 2 Task 2.17: 前置状态横幅（B23-2/C3/B51-3）
// D-sales-cycle F8 Task 2.19: 扩展支持 D 循环前置状态横幅（B23-1/C2/B51-5）
// F-purchase-inventory F-F9 Task 2.22: 扩展支持 F 循环前置状态横幅（B23-3/C4/B51-4）
// I-intangible-assets-cycle I-F9 Task 2.22: 扩展支持 I 循环前置状态横幅（C8 + C9）
// G-investment-cycle G-F9 Task 2.23: 扩展支持 G 循环前置状态横幅（C5 投资循环控制测试）
const prerequisiteCycleCode = computed(() => {
  if (isHCycle.value) return wpDetail.value?.wp_code || 'H1'
  if (isICycle.value) return wpDetail.value?.wp_code || 'I1'
  if (isGCycle.value) return wpDetail.value?.wp_code || 'G1'
  if (isLCycle.value) return wpDetail.value?.wp_code || 'L1'
  if (isMCycle.value) return wpDetail.value?.wp_code || 'M2'
  if (isNCycle.value) return wpDetail.value?.wp_code || 'N2'
  if (isFCycle.value) return wpDetail.value?.wp_code || 'F2'
  if (isDCycle.value) return wpDetail.value?.wp_code || 'D2'
  return 'E1'
})
const prerequisiteStatus = usePrerequisiteStatus(projectId.value, prerequisiteCycleCode.value)
const prerequisiteBanner = computed(() => prerequisiteStatus.banner.value)

function onJumpToPrereq() {
  // 跳转到第一个未完成的前置底稿
  const target = prerequisiteStatus.items.value.find((i) => i.state !== 'completed')
  if (!target) return
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { highlight: target.wp_code },
  })
}

// E1 Sprint 2 Task 2.33: 数据刷新（6 种事件 + 手动刷新按钮）
const manualRefreshing = ref(false)
const wpRefresh = useWorkpaperRefresh({
  projectId: () => projectId.value,
  wpId: () => wpId.value,
  onRefresh: async () => {
    if (manualRefreshing.value) return
    manualRefreshing.value = true
    try {
      // 重新调用 prefill init（与 onRefreshPrefill 复用）
      await httpApi.post(
        `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/init`,
        { user_overrides: userOverrides.serializeOverrides() },
      ).catch(() => null)
    } finally {
      manualRefreshing.value = false
    }
  },
})

async function onManualRefresh() {
  manualRefreshing.value = true
  try {
    await onRefreshPrefill()
  } finally {
    manualRefreshing.value = false
  }
}

function onSwitchSheet(sheetId: string) {
  sheetNav.switchTo(sheetId)
}

function formatStaleItem(item: StaleAffectedItem): string {
  if (item.target_module) {
    const code = item.note_section_code || item.report_row_code || ''
    const moduleName = item.target_module === 'disclosure_notes' ? '附注'
      : item.target_module === 'audit_report' ? '审计报告'
      : item.target_module === 'financial_report' ? '财务报表'
      : item.target_module === 'trial_balance' ? '试算表'
      : item.target_module === 'adjustments' ? '调整分录'
      : item.target_module === 'misstatements' ? '错报'
      : item.target_module
    return code ? `${moduleName}.${code}` : moduleName
  }
  const wp = item.wp_code || '?'
  const cell = item.cell ? `.${item.cell}` : ''
  const sheet = item.sheet ? `[${item.sheet.slice(0, 12)}]` : ''
  return `${wp}${sheet}${cell}`
}

function staleImpactTagType(item: StaleAffectedItem): 'success' | 'warning' | 'danger' | 'info' {
  if (item.severity === 'blocking' || item.severity === 'required') return 'danger'
  if (item.severity === 'warning') return 'warning'
  if (item.severity === 'info') return 'info'
  return 'warning'
}

function onStaleItemClick(item: StaleAffectedItem) {
  if (item.target_module === 'disclosure_notes' && item.note_section_code) {
    router.push(`/projects/${projectId.value}/disclosure-notes?section=${item.note_section_code}`)
  } else if (item.target_module === 'audit_report') {
    router.push(`/projects/${projectId.value}/audit-report`)
  } else if (item.target_module === 'financial_report' && item.report_row_code) {
    router.push(`/projects/${projectId.value}/reports?row=${item.report_row_code}`)
  } else if (item.target_module === 'trial_balance') {
    router.push(`/projects/${projectId.value}/trial-balance`)
  } else if (item.target_module === 'adjustments') {
    router.push(`/projects/${projectId.value}/adjustments`)
  } else if (item.wp_code) {
    // 跳转到列表视图按 wp_code 筛选
    router.push({
      name: 'WorkpaperList',
      params: { projectId: projectId.value },
      query: { highlight: item.wp_code },
    })
  }
}

// R7-S2-05：统一自动保存（60s 间隔，合并原 30s UI 反馈 + 120s 后端保存）
const autoSave = useWorkpaperAutoSave(async () => {
  const ok = await onSave()
  if (!ok) {
    ElMessage.warning({ message: '自动保存失败，请手动保存', duration: 5000 })
  }
}, 60_000)

// UI 反馈：绑定 autoSave 状态
const autoSaveMsg = computed(() => {
  if (autoSave.saving.value) return '保存中...'
  if (autoSave.lastSavedAt.value) {
    const sec = Math.round((Date.now() - autoSave.lastSavedAt.value.getTime()) / 1000)
    if (sec < 5) return '已自动保存'
  }
  return ''
})

// R1 需求 2：底稿复核红点（任务 5）
const reviewMarkers = useWorkpaperReviewMarkers({
  projectId: () => projectId.value,
  wpId: () => wpId.value,
  onJumpToIssue: (ticket: ReviewMarkerTicket) => {
    // 跳转到项目问题单列表，高亮该工单
    router.push({
      name: 'IssueTicketList',
      params: { projectId: projectId.value },
      query: { highlight_id: ticket.id },
    })
  },
})

const saving = ref(false)
const submitting = ref(false)
const syncLoading = ref(false)
const prefillLoading = ref(false)
const dirty = ref(false)
const showSidePanel = ref(false)
// R8-S2-02：自检未通过项数（由 WorkpaperSidePanel @finecheck-update 同步）
const fineCheckFailCount = ref(0)
const univerContainer = ref<HTMLElement | null>(null)

// spec workpaper-editor-refactor Phase 2-3: 所有循环弹窗状态集中到 useCycleDialogs composable
import { useCycleDialogs } from '@/composables/useCycleDialogs'
const cycleDialogs = useCycleDialogs(wpDetail, wpId, sheetNavActiveId, cycleType)

// spec workpaper-editor-refactor Phase 3 Task 3.2: F 循环逻辑接入 useFCycleEditor composable
const fCycle = useFCycleEditor(wpDetail, projectId, wpId, sheetNavFacade, cycleDialogs)

// spec workpaper-editor-refactor Phase 3 Task 3.4-3.9: 6 个循环 composable 实例化（必须在 cycleDialogs 之后）
const iCycle = useICycleEditor(wpDetail, sheetNavFacade, cycleDialogs)
const iBranchSelector = iCycle.branchSelector
const gCycle = useGCycleEditor(wpDetail, sheetNavFacade, cycleDialogs)
const kCycle = useKCycleEditor(wpDetail, cycleDialogs)
const lCycle = useLCycleEditor(wpDetail, cycleDialogs)
const mCycle = useMCycleEditor(wpDetail, cycleDialogs)
const nCycle = useNCycleEditor(wpDetail, cycleDialogs)
// spec workpaper-editor-slimdown Sprint 2 Task 3.3: dialog 状态已由 CycleDialogSlot 内部管理
// 保留 cycleDialogs composable 供 F/I/G/K/L/M/N cycle editor composables 使用

// ─── Sprint 2: Foundation composables ─────────────────────────────────────────
const prefillMarkers = usePrefillMarkers()
const crossModuleRefs = useCrossModuleRefs(
  computed(() => wpDetail.value?.wp_code || ''),
  projectId,
)
const reviewMarksComposable = useReviewMarks(projectId)
const userOverrides = useUserOverrides()

// Sprint 2.1: Track whether prefill mapping exists for current workpaper
const hasPrefillMapping = ref(true)

// Sprint 2.2: Prefill tooltip state
const prefillTooltip = ref<{ visible: boolean; text: string; x: number; y: number }>({
  visible: false, text: '', x: 0, y: 0,
})
const formulaBarText = ref('')

// Sprint 2.3: Cross-module refs overlay
const crossRefTags = ref<Array<{ id: string; label: string; color: string; x: number; y: number; route: string }>>([])

// Sprint 2.4: Review mark dialog
const showReviewDialog = ref(false)
const reviewDialogCell = ref<{ sheet: string; cellRef: string }>({ sheet: '', cellRef: '' })
const reviewDialogComment = ref('')

// Sprint 5.5: Cell formula detail dialog
const showCellFormulaDetail = ref(false)

// 审计导航图抽屉
const showAuditNavDrawer = ref(false)
const auditNavFullscreen = ref(true)

// Sprint 4 Task 15.13: 底稿离线导出/导入
const showOfflineExportDialog = ref(false)
const showOfflineImportDialog = ref(false)
const availableSheetNames = computed(() => {
  return flatSheets.value?.map((s: any) => s.name || s.id || '') || []
})
function onOfflineImported() {
  // Reload workpaper data after import
  getWorkpaper(projectId.value, wpId.value).then((data) => {
    if (data) wpDetail.value = data
  })
}

const hasAuditNav = computed(() => {
  const code = wpDetail.value?.wp_code || ''
  return !!code && (
    code.startsWith('E1') ||
    isDCycle.value || isFCycle.value || isHCycle.value || isICycle.value ||
    isGCycle.value || isKCycle.value || isLCycle.value || isMCycle.value || isNCycle.value
  )
})
const cellDetailSheet = ref('')
const cellDetailLabel = ref('')
const reviewDialogStatus = ref<ReviewStatus>('reviewed')

// Sprint 2.6: User override indicators
const overrideIndicators = ref<Array<{ cellRef: string; sheet: string }>>([])


// 任务 8.18.1：用户名映射（UUID → 显示名）
const userNameMap = ref<Map<string, string>>(new Map())

function resolveUserName(uuid: string | null | undefined): string {
  if (!uuid) return '未分配'
  return userNameMap.value.get(uuid) ?? '未知用户'
}

async function loadUserMap() {
  try {
    const users = await listUsers()
    userNameMap.value = new Map(
      (users || []).map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch { /* 静默：状态栏降级显示 UUID */ }
}

// 任务 8.19.1：版本历史
const showVersionDrawer = ref(false)
const versionList = ref<any[]>([])
const versionLoading = ref(false)

async function onShowVersions() {
  showVersionDrawer.value = true
  versionLoading.value = true
  try {
    const data = await httpApi.get(P_wp.versions(wpId.value), {
      validateStatus: (s: number) => s < 600,
    })
    versionList.value = Array.isArray(data) ? data : (data?.versions || data?.items || [])
  } catch (e: any) {
    versionList.value = []
    handleApiError(e, '加载版本历史')
  } finally {
    versionLoading.value = false
  }
}

/**
 * S-4 (proposal-remaining-18 task 5.4)：历史版本搜索结果点击跳转
 * 通过已有的 workpaper:locate-cell 事件触发 Univer 跳转 + 高亮。
 * v1 实现仅在当前活跃版本上定位 cell；切换到具体快照版本数据源由后续迭代实现。
 */
function onVersionSearchJump(payload: { versionId: string; sheet: string; cellRef: string }) {
  if (!payload.cellRef || !wpId.value) return
  eventBus.emit('workpaper:locate-cell', {
    wpId: wpId.value,
    sheetName: payload.sheet || undefined,
    cellRef: payload.cellRef,
  })
  // 关闭抽屉，聚焦到编辑区
  showVersionDrawer.value = false
}

// （旧 30s 自动保存已合并到 useWorkpaperAutoSave 60s 统一方案）

let univerInstance: any = null
let univerAPI: any = null
// univerAPIRef 已在 sheetNav 初始化处声明（顶部）

// 智能提示
const smartTip = ref<any>(null)
const showSmartTipDetail = ref(false)

// P0-2/P0-3: Track whether workpaper was loaded from xlsx (component scope for onSave access)
let loadedFromXlsx = false
// P2-2: 记录文件打开时间戳（用于 xlsx 保存冲突检测）
let fileOpenedAt = 0

function statusTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    not_started: 'info', in_progress: 'warning', draft: 'warning',
    draft_complete: '', edit_complete: '', review_passed: 'success', archived: 'info',
  }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = {
    not_started: '未开始', in_progress: '编制中', draft: '草稿',
    draft_complete: '初稿完成', edit_complete: '编辑完成',
    review_passed: '复核通过', archived: '已归档',
  }
  return m[s] || s
}

function goBack() {
  if (dirty.value) {
    if (!confirm('有未保存的修改，确定离开？')) return
  }
  router.push({ name: 'WorkpaperList', params: { projectId: projectId.value } })
}

// spec workpaper-editor-refactor Phase 4.1：no_file 状态时跳转生命周期视图（用户可一键生成底稿）
function goToLifecycle() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { tab: 'lifecycle' },
  })
}

// spec workpaper-editor-refactor Phase 4.1：error 状态时重试加载
async function onRetryLoad() {
  loadErrorState.value = null
  loadErrorMessage.value = ''
  loading.value = true
  loadingHint.value = '重新加载'
  await initUniver()
}

async function initUniver() {
  if (!univerContainer.value) return

  // spec workpaper-editor-refactor Phase 4.1：UUID 格式校验（提前拦截，避免后端 404 误导）
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  if (!wpId.value || !UUID_RE.test(wpId.value)) {
    loadErrorState.value = 'invalid_id'
    loadErrorMessage.value = '底稿 ID 格式不合法（不是 UUID）'
    loading.value = false
    loadingHint.value = ''
    return
  }

  // 1. 加载底稿详情
  loadingHint.value = '加载底稿详情'
  try {
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    if (!wpDetail.value) {
      // spec Phase 4.1：底稿数据为空 → 显示 no_file 引导，不再粗暴 goBack
      loadErrorState.value = 'no_file'
      loadErrorMessage.value = '底稿数据为空，可能尚未生成文件。请先在生命周期中执行"一键生成底稿"。'
      loading.value = false
      loadingHint.value = ''
      return
    }
  } catch (e: any) {
    // spec Phase 4.1：404 → no_index/no_file 引导；其他错误 → error 状态
    const status = e?.response?.status
    if (status === 404) {
      loadErrorState.value = 'no_index'
      loadErrorMessage.value = '该底稿不在当前项目中（可能编码已变更或被删除）。请回到底稿列表选择有效的底稿。'
    } else {
      loadErrorState.value = 'error'
      loadErrorMessage.value = e?.message || '加载底稿时发生错误'
    }
    loading.value = false
    loadingHint.value = ''
    return
  }

  // E1 Sprint 2: 加载项目元数据（scenario + has_foreign_currency）
  loadingHint.value = '读取项目元数据'
  try {
    const proj: any = await httpApi.get(`/api/projects/${projectId.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    projectMeta.value = {
      scenario: proj?.scenario || 'normal',
      has_foreign_currency: !!proj?.has_foreign_currency,
      measurement_model: proj?.measurement_model || 'cost',
    }
  } catch {
    projectMeta.value = { scenario: 'normal', has_foreign_currency: false, measurement_model: 'cost' }
  }

  // 2. 直接从后端 GET /xlsx-to-json 加载完整 Univer JSON（D2 PoC 最终方案）
  // 不再下载 xlsx blob 尝试 importXLSX（Core Preset 不支持，会静默创建空白 workbook）
  loadingHint.value = '加载工作簿数据'
  let workbookData: any = null
  loadedFromXlsx = false
  try {
    const jsonData = await httpApi.get(
      `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/xlsx-to-json`,
    )
    if (jsonData && jsonData.sheets && Object.keys(jsonData.sheets).length > 0) {
      workbookData = jsonData
      loadedFromXlsx = true
      fileOpenedAt = Date.now() / 1000
      console.info(`[WorkpaperEditor] xlsx-to-json loaded: ${Object.keys(jsonData.sheets).length} sheets`)
    }
  } catch (e: any) {
    console.warn('[WorkpaperEditor] xlsx-to-json failed, trying univerData fallback:', e?.message || e)
  }

  // 2b. 降级：从后端加载 Univer JSON 数据（parsed_data 存储的 snapshot）
  if (!workbookData) {
    try {
      const data = await httpApi.get(
        P_wp.univerData(projectId.value, wpId.value),
        { validateStatus: (s: number) => s < 600 },
      )
      workbookData = data
    } catch {
      workbookData = null
    }
  }

  if (!workbookData || !workbookData.sheets) {
    // 兜底：创建空白工作簿
    workbookData = {
      id: wpDetail.value.wp_code || 'wp',
      name: `${wpDetail.value.wp_code} ${wpDetail.value.wp_name}`,
      sheetOrder: ['sheet0'],
      sheets: {
        sheet0: {
          id: 'sheet0',
          name: wpDetail.value.wp_name || 'Sheet1',
          rowCount: 100,
          columnCount: 20,
          cellData: {},
        },
      },
    }
  }

  // 3. 初始化 Univer
  // Advanced Preset 需要 Univer Server（:3010），当前未部署，跳过
  // 如需启用：部署 Univer Server 后取消下方注释
  loadingHint.value = '初始化 Univer 引擎'
  const extraPresets: any[] = []
  // try {
  //   const { UniverSheetsDrawingPreset } = await import('@univerjs/preset-sheets-drawing')
  //   const { UniverSheetsAdvancedPreset } = await import('@univerjs/preset-sheets-advanced')
  //   extraPresets.push(UniverSheetsDrawingPreset())
  //   extraPresets.push(UniverSheetsAdvancedPreset({
  //     universerEndpoint: window.location.origin.replace(/:\d+$/, ':3010'),
  //   }))
  // } catch { /* Advanced Preset 不可用 */ }

  const { univerAPI: api, univer } = createUniver({
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: mergeLocales(UniverPresetSheetsCoreZhCN),
    },
    presets: [
      UniverSheetsCorePreset({
        container: univerContainer.value,
      }),
      ...extraPresets,
    ],
  })

  univerInstance = univer
  univerAPI = api
  univerAPIRef.value = api  // sync to ref for sheetNav composable

  // 4. 创建工作簿
  if (workbookData && workbookData.sheets && Object.keys(workbookData.sheets).length > 0) {
    univerAPI.createWorkbook(workbookData)
  } else {
    // Final fallback: empty workbook（仅当后端也失败时）
    console.error('[WorkpaperEditor] No workbook data available, creating empty workbook')
    univerAPI.createWorkbook({
      id: wpDetail.value.wp_code || 'wp',
      name: `${wpDetail.value.wp_code} ${wpDetail.value.wp_name}`,
      sheetOrder: ['sheet0'],
      sheets: { sheet0: { id: 'sheet0', name: 'Sheet1', rowCount: 100, columnCount: 20, cellData: {} } },
    })
  }

  // 5. 监听数据变化
  univerAPI.onCommandExecuted((command: any) => {
    if (DIRTY_COMMAND_PATTERNS.some(p => command.id?.includes(p))) {
      dirty.value = true
      autoSave.markDirty()

      // Task 2.6: Detect user override on prefilled cells
      if (command.id?.includes('set-range-values') && command.params) {
        _detectUserOverride(command)
      }
    }
    // 监听 sheet 切换/增删，刷新左侧 Sheet 导航
    if (
      command.id?.includes('set-worksheet-activate') ||
      command.id?.includes('insert-sheet') ||
      command.id?.includes('remove-sheet') ||
      command.id?.includes('set-worksheet-name')
    ) {
      sheetNav.refresh()
    }
  })

  // 初次刷新 sheet 导航（workbook 创建完毕）
  loadingHint.value = '渲染工作表'
  setTimeout(() => {
    sheetNav.refresh()
    // E1 Sprint 2 Task 2.37: 应用 has_foreign_currency 显隐规则到 E1-1
    // spec workpaper-editor-refactor Phase 3 Task 3.1: 委托 useECycleEditor 处理
    eCycle.handlers.applyForeignCurrencyVisibility()
  }, 100)

  loading.value = false
  loadingHint.value = ''

  // 6. 非阻塞加载智能提示和用户名映射
  loadSmartTips()
  loadUserMap()

  // ─── Sprint 2: Post-load integrations ─────────────────────────────────────
  // Task 2.2: Load prefill markers from workbook data
  if (workbookData?.sheets) {
    prefillMarkers.loadFromWorkbook(workbookData.sheets)
    hasPrefillMapping.value = prefillMarkers.totalPrefillCells.value > 0
  }

  // Task 2.3: Load cross-module references
  // wp_step_mapping endpoint uses wp_index_id (查 wp_index 表)
  const wpIndexId = wpDetail.value?.wp_index_id || wpId.value
  try {
    const refsData = await httpApi.get(
      `/api/workpapers/${wpIndexId}/references`,
      { validateStatus: (s: number) => s < 600 },
    )
    if (refsData?.references || refsData?.incoming || refsData?.outgoing) {
      crossModuleRefs.loadFromJson(refsData)
    }
  } catch { /* cross refs not available, non-blocking */ }

  // Task 2.8: Load user overrides from parsed_data on workbook load
  if (wpDetail.value?.parsed_data) {
    userOverrides.loadOverrides(wpDetail.value.parsed_data)
  }

  // Task 2.2: Listen for cell selection changes to show formula bar text
  univerAPI.onCommandExecuted((cmd: any) => {
    if (cmd.id?.includes('set-selections') || cmd.id?.includes('set-select')) {
      _updatePrefillTooltipOnSelection()
    }
  })

  // ─── Sprint 6 Task 6.4: Univer 右键菜单证据链入口 ─────────────────────────
  // TODO: 完整 Univer 右键菜单集成需要 @univerjs/ui 的 IMenuService
  // 注册位置：在 univerAPI 就绪后，通过 IMenuService.addMenuItem 注册以下三项：
  //   1. "引用附件" — 打开附件选择器，选中后调用 useEvidenceLink.createLink
  //   2. "上传并引用" — 打开上传对话框，上传完成后自动建立 link
  //   3. "查看引用的附件" — 读取当前单元格 cellRef，展示该单元格所有 evidence links
  // 当前为占位注释，完整集成在 Univer 插件体系稳定后实施。
  // ──────────────────────────────────────────────────────────────────────────

  // 7. R1 需求 2：加载复核意见红点（失败不阻断底稿）
  loadReviewMarkers()
}

/**
 * R1 需求 2：拉取 ReviewRecord 并在 Univer 单元格挂红点。
 * - 任何错误都被 composable 内部吞掉，不影响底稿编辑；
 * - 路由 query.cell 或 query.review_id 存在时，红点挂载完成后滚动到对应单元格。
 */
async function loadReviewMarkers() {
  try {
    await reviewMarkers.loadData()
    // Univer API 已在 initUniver 中就绪（univerAPI 变量）
    reviewMarkers.attachMarkers(univerAPI)

    // 路由跳转支持：?cell=B5 直接定位；?review_id=<uuid> 查出 cell 再定位
    const q = route.query
    let targetCell: string | null = null
    if (typeof q.cell === 'string' && q.cell.trim()) {
      targetCell = q.cell.trim()
    } else if (typeof q.review_id === 'string' && q.review_id.trim()) {
      targetCell = reviewMarkers.findCellRefByReviewId(q.review_id.trim())
    }
    if (targetCell) {
      // 下一帧滚动，避免 Univer 内部异步布局未完成
      requestAnimationFrame(() => {
        reviewMarkers.scrollToCell(univerAPI, targetCell as string)
      })
    }
  } catch {
    /* ignore — 红点仅为辅助功能 */
  }
}

async function onSave(): Promise<boolean> {
  if (!univerAPI || !wpDetail.value) return false
  saving.value = true
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) throw new Error('无法获取工作簿数据')

    const snapshot = workbook.getSnapshot()

    // 如果底稿从 xlsx 模板加载，同时导出 xlsx 回写到后端
    if (loadedFromXlsx) {
      try {
        let xlsxBlob: Blob | null = null

        // P0-3: Try exportXLSXBySnapshotAsync (Univer 0.21.x with advanced preset)
        if (typeof univerAPI.exportXLSXBySnapshotAsync === 'function') {
          xlsxBlob = await univerAPI.exportXLSXBySnapshotAsync(snapshot)
        }
        // Fallback: try exportWorkbookToXLSX
        else if (typeof univerAPI.exportWorkbookToXLSX === 'function') {
          xlsxBlob = await univerAPI.exportWorkbookToXLSX()
        }

        if (xlsxBlob && xlsxBlob.size > 0) {
          const formData = new FormData()
          formData.append('file', xlsxBlob, `${wpId.value}.xlsx`)
          await fetch(
            `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/upload-xlsx`,
            {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
                'X-File-Opened-At': String(fileOpenedAt),
              },
              body: formData,
            },
          )
        }
        // If no export API available, just save the JSON snapshot (existing behavior below)
      } catch (e) {
        console.warn('xlsx export failed (non-blocking):', e)
      }
    }

    // 调用完整保存 API（xlsx 回写 + structure.json + 审计留痕 + 事件发布）
    // 需求 45.1：携带 expected_version 触发后端并发冲突检测
    // Task 2.8: Include user_overrides in save payload
    const data = await httpApi.post(
      P_wp.univerSave(projectId.value, wpId.value),
      {
        snapshot,
        expected_version: wpDetail.value.file_version,
        parsed_data_patch: { user_overrides: userOverrides.serializeOverrides() },
      },
      { validateStatus: (s: number) => s < 600 },
    )

    // 需求 45.2：处理 409 版本冲突（axios 在 validateStatus 放行后，409 不会抛错，需手动判断）
    if (data?.detail?.error_code === 'VERSION_CONFLICT' || data?.error_code === 'VERSION_CONFLICT') {
      const detail = data.detail || data
      try {
        await confirmVersionConflict(detail.server_version, detail.expected_version)
        // 刷新放弃：重新加载最新数据
        await initUniver()
        return false
      } catch (action) {
        if (action === 'cancel') {
          // 强制覆盖：不带 expected_version 重发
          const retryData = await httpApi.post(
            P_wp.univerSave(projectId.value, wpId.value),
            { snapshot },
          )
          dirty.value = false
          autoSave.clearDirty()
          ElMessage.success(retryData?.message || '已强制覆盖保存')
          eventBus.emit('workpaper:saved', {
            projectId: projectId.value,
            wpId: wpId.value,
          } as WorkpaperSavedPayload)
          wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
          return true
        }
        return false
      }
    }

    const result = data
    dirty.value = false
    autoSave.clearDirty()
    ElMessage.success(result?.message || '保存成功')

    // 发布底稿保存事件，触发附注自动同步
    eventBus.emit('workpaper:saved', {
      projectId: projectId.value,
      wpId: wpId.value,
    } as WorkpaperSavedPayload)

    // Global Linkage Bus: 通知单元格变更，调用统一联动总线计算下游 stale 影响
    // 取当前活动 sheet（不传 cell，按 sheet 级触发 stale 传播）
    try {
      const activeSheet = workbook.getActiveSheet?.()
      const sheetName = activeSheet?.getSheetName?.() || activeSheet?.getName?.() || ''
      const impactResp = await staleImpact.notify({
        sheet: sheetName,
        max_depth: 3,
        project_id: projectId.value,
        year: wpDetail.value?.year || new Date().getFullYear(),
      })
      if (impactResp && (impactResp.total || impactResp.total_affected) > 0) {
        const total = impactResp.total || impactResp.total_affected
        ElMessage.info({
          message: `已识别 ${total} 个下游影响点（点击右侧"影响范围"查看）`,
          duration: 4000,
        })
        showStaleImpactPanel.value = true
      }
    } catch (e) {
      console.warn('[stale-impact] notify failed (non-blocking):', e)
    }

    // 刷新版本信息
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    return true
  } catch (err: any) {
    handleApiError(err, '保存底稿')
    return false
  } finally {
    saving.value = false
  }
}

async function onSubmitForReview() {
  if (!wpDetail.value) return
  if (dirty.value) {
    ElMessage.warning('请先保存当前修改')
    return
  }
  try {
    await confirmSubmitReview(wpDetail.value?.wp_code || '', wpDetail.value?.wp_name || '')
  } catch { return }

  submitting.value = true
  try {
    await httpApi.put(
      P_wp.status(projectId.value, wpId.value),
      { status: 'pending_review' },
    )
    ElMessage.success('已提交复核，等待复核人审阅')
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch (err: any) {
    handleApiError(err, '提交复核')
  } finally {
    submitting.value = false
  }
}

async function onSyncStructure() {
  syncLoading.value = true
  try {
    // 先保存当前数据
    if (dirty.value) {
      const saveOk = await onSave()
      if (!saveOk) return
    }
    // 重建 structure
    await rebuildWorkpaperStructure(projectId.value, wpId.value)
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    ElMessage.success('公式坐标已同步')
  } catch (e: any) {
    handleApiError(e, '同步')
  } finally {
    syncLoading.value = false
  }
}

async function onRefreshPrefill() {
  if (!hasPrefillMapping.value) return
  prefillLoading.value = true
  try {
    // 先保存当前编辑
    if (dirty.value) {
      const saveOk = await onSave()
      if (!saveOk) return
    }
    // Task 2.7: Pass user_overrides to backend so it skips those cells
    const overrides = userOverrides.serializeOverrides()
    const overrideCount = userOverrides.overrideCount.value

    // 调用后端重新初始化（强制从模板复制+prefill），传递 user_overrides
    const result = await httpApi.post(
      `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/init`,
      { user_overrides: overrides },
    )
    // 重新加载 Univer
    if (univerInstance) {
      try { univerInstance.dispose() } catch { /* ignore */ }
      univerInstance = null
      univerAPI = null
    }
    loading.value = true
    await initUniver()

    // Task 2.1 + 2.7: Show summary toast with filled count and skipped count
    const filledCount = result?.filled_count ?? result?.prefill_count ?? 0
    const skippedCount = overrideCount
    if (filledCount > 0 || skippedCount > 0) {
      ElMessage.success(`已刷新 ${filledCount} 个单元格，跳过 ${skippedCount} 个手动修改的单元格`)
    } else {
      ElMessage.success('取数刷新完成，已从试算表重新填入最新数据')
    }
  } catch (e: any) {
    handleApiError(e, '刷新取数')
  } finally {
    prefillLoading.value = false
  }
}

async function onDownload() {
  try {
    await downloadWorkpaper(projectId.value, wpId.value)
  } catch (e: any) {
    handleApiError(e, '下载')
  }
}

// 任务 10.6.2：导出 PDF
const exportingPdf = ref(false)
async function onExportPdf() {
  if (!wpDetail.value) return
  exportingPdf.value = true
  try {
    // 使用 axios http 客户端直接获取 blob（apiProxy.api 会 unwrap data 不适合 blob）
    const http = (await import('@/utils/http')).default
    const response = await http.get(
      P_wp.exportPdf(projectId.value, wpId.value),
      { responseType: 'blob', validateStatus: (s: number) => s < 600 },
    )
    const blob: Blob = response.data
    // 后端出错时返回 JSON（blob），需检测
    if (blob.type && blob.type.includes('application/json')) {
      const txt = await blob.text()
      let msg = 'PDF 导出失败'
      try { msg = JSON.parse(txt)?.detail || msg } catch { /* ignore */ }
      handleApiError({ response: { status: 500, data: { detail: msg } } }, 'PDF 导出')
      return
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${wpDetail.value.wp_code || 'workpaper'}_${wpDetail.value.wp_name || ''}.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (err: any) {
    handleApiError(err, 'PDF 导出')
  } finally {
    exportingPdf.value = false
  }
}

function onUpload() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { upload: wpId.value },
  })
}

async function loadSmartTips() {
  if (!wpDetail.value) return
  try {
    const wpName = wpDetail.value.wp_name || ''
    const accountName = wpName.replace(/审定表|明细表|程序表|汇总表|盘点表|调节表|核对表/g, '').trim()
    if (!accountName) return

    const data = await httpApi.get(
      P_wp.wpMappingTsj(projectId.value, accountName),
      { validateStatus: (s: number) => s < 600 },
    )
    if (data?.tips?.length || data?.risk_areas?.length) {
      smartTip.value = {
        summary: data.risk_areas?.find((a: string) => a.includes('高风险')) || data.tips?.[0]?.slice(0, 30) || '查看审计关注点',
        warnings: (data.risk_areas || []).filter((a: string) => a.includes('高风险')),
        tips: (data.tips || []).slice(0, 3),
      }
    }
  } catch { /* ignore */ }
}

// ─── Sprint 2 Helper Functions ─────────────────────────────────────────────────

/** Task 2.6: Detect if edited cell has prefill_source → mark as override */
function _detectUserOverride(command: any) {
  if (!univerAPI) return
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) return
    const activeSheet = workbook.getActiveSheet?.()
    if (!activeSheet) return
    const sheetName = activeSheet.getSheetName?.() || activeSheet.getName?.() || 'Sheet1'

    // Extract cell coordinates from command params
    const rangeData = command.params?.range || command.params?.cellValue
    if (!rangeData) return

    const row = rangeData.startRow ?? rangeData.row ?? 0
    const col = rangeData.startColumn ?? rangeData.col ?? 0
    const cellRef = _colToLetter(col) + (row + 1)

    // Check if this cell has prefill source
    if (prefillMarkers.hasPrefill(sheetName, cellRef)) {
      userOverrides.markAsOverride(sheetName, cellRef)
    }
  } catch { /* ignore detection errors */ }
}

/** Task 2.2: Update formula bar text when cell selection changes */
function _updatePrefillTooltipOnSelection() {
  if (!univerAPI) return
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) return
    const activeSheet = workbook.getActiveSheet?.()
    if (!activeSheet) return
    const sheetName = activeSheet.getSheetName?.() || activeSheet.getName?.() || 'Sheet1'

    const selection = activeSheet.getActiveRange?.()
    if (!selection) { formulaBarText.value = ''; return }

    const row = selection.getRow?.() ?? 0
    const col = selection.getColumn?.() ?? 0
    const cellRef = _colToLetter(col) + (row + 1)

    formulaBarText.value = prefillMarkers.getFormulaBarText(sheetName, cellRef)
  } catch {
    formulaBarText.value = ''
  }
}

/** Task 2.4: Handle right-click "标记复核" */
async function onMarkReview() {
  if (!showReviewDialog.value) return
  const { sheet, cellRef } = reviewDialogCell.value
  if (!sheet || !cellRef || !wpId.value) return

  const mark = await reviewMarksComposable.createReviewMark(
    wpId.value,
    sheet,
    cellRef,
    reviewDialogStatus.value,
    reviewDialogComment.value,
  )
  if (mark) {
    ElMessage.success('复核标记已保存')
    eventBus.emit('review-mark:changed', { projectId: projectId.value, wpId: wpId.value })
  }
  showReviewDialog.value = false
  reviewDialogComment.value = ''
}

/** Task 2.6: Right-click "恢复预填充" */
async function onRestorePrefill(sheet: string, cellRef: string) {
  userOverrides.removeOverride(sheet, cellRef)
  ElMessage.success(`已恢复 ${cellRef} 的预填充值，下次刷新取数时将重新填入`)
}

/** Sprint 5.5: 查看公式详情 — 打开 CellFormulaDetail 弹窗 */
function onViewCellFormulaDetail() {
  cellDetailSheet.value = ''
  cellDetailLabel.value = ''
  showCellFormulaDetail.value = true
}

/** Sprint 5.5: 公式详情弹窗导航回调 */
function onCellDetailNavigate(uri: string) {
  showCellFormulaDetail.value = false
  const parts = uri.split(':')
  const mod = parts[0]?.toUpperCase()
  if (mod === 'REPORT') {
    router.push({ name: 'ReportView', params: { id: projectId.value } })
  } else if (mod === 'NOTE') {
    router.push({ name: 'DisclosureEditor', params: { id: projectId.value } })
  } else if (mod === 'WP' && parts[1]) {
    router.push({ name: 'WorkpaperEditor', params: { id: projectId.value }, query: { wp: parts[1] } })
  }
}


/** Column number to letter (0-based) */
function _colToLetter(col: number): string {
  let result = ''
  let c = col
  while (c >= 0) {
    result = String.fromCharCode(65 + (c % 26)) + result
    c = Math.floor(c / 26) - 1
  }
  return result
}

onBeforeRouteLeave(async (_to, _from, next) => {
  if (!dirty.value) { next(); return }
  try {
    await confirmLeave('底稿')
    next()
  } catch {
    next(false)
  }
})

// spec workpaper-editor-refactor Phase 2 Task 2.3: onCrossRefUpdated + onSSECrossRefUpdated
// 已迁移到 useDCycleEditor composable（含生命周期事件订阅/清理）

onMounted(() => {
  // spec workpaper-html-renderer Task 13.1: 路由分发顺序
  // 1. fetchComponentType 加载 wpDetail（提供 wpCodeRef 给 useWpClassification）
  // 2. 等待 wpClassification.load() 完成（避免 Univer init 抢跑后被 HTML 路由覆盖造成实例泄漏）
  // 3. 按优先级判定：HTML 类 → 跳过 Univer init / Univer 类 → initUniver / 子编辑器（form/word/table/hybrid）→ 关 loading
  ;(async () => {
    await fetchComponentType()
    // wpClassification 已在 watch(immediate: true) 中触发 load；这里再 await 一次确保完成
    // （load() 内部已防止重复请求，第二次调用即拿到上次结果或等当前请求完成）
    try {
      await wpClassification.load()
    } catch { /* 静默：归类失败回退到 Univer/子编辑器路径 */ }

    if (useHtmlRenderer.value) {
      // HTML 类：GtWpRenderer 自行处理加载/错误/渲染，外层关 loading
      loading.value = false
      return
    }
    if (componentType.value === 'univer' || !componentType.value) {
      initUniver()
    } else {
      // 子编辑器（form/word/table/hybrid）不走 initUniver，需要在这里关闭 loading
      loading.value = false
    }
  })()
  // P0: 加载程序步骤映射
  stepMapping.loadMapping()
  // R8-S2-02：订阅 workpaper:locate-cell 事件，定位到 Univer 单元格
  eventBus.on('workpaper:locate-cell', onLocateCell)
  // R8-S2-14：关闭浏览器/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)

  // [R9 F9 Task 30] 确认 Univer Ctrl+Z/Y 不被 shortcutManager 拦截
  // shortcutManager 已在 R9 Task 31 中移除 Ctrl+Z 和 Ctrl+Shift+Z 的注册
  // Univer 内置 UndoCommand/RedoCommand 原生处理撤销/重做，无需额外绑定
})

onUnmounted(() => {
  eventBus.off('workpaper:locate-cell', onLocateCell)
  window.removeEventListener('beforeunload', onBeforeUnload)
  if (univerInstance) {
    try { univerInstance.dispose() } catch { /* ignore */ }
    univerInstance = null
    univerAPI = null
  }
})

/** R8-S2-14：浏览器关闭/刷新前警告（仅在 dirty 时阻止） */
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

/**
 * R8-S2-02：响应 workpaper:locate-cell 事件，通过 Univer API 定位到指定单元格
 * - 事件来源：WorkpaperSidePanel 自检 Tab 的"定位"按钮
 * - 仅处理属于当前底稿的事件（wpId 匹配）
 */
function onLocateCell(payload: { wpId: string; sheetName?: string; cellRef: string }) {
  if (!univerAPI || payload.wpId !== wpId.value) return
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) return
    // 如果指定 sheetName，先切到对应 sheet
    if (payload.sheetName) {
      const sheet = workbook.getSheetByName?.(payload.sheetName)
      if (sheet) workbook.setActiveSheet?.(sheet)
    }
    // cellRef 支持 "B5" 或 "Sheet1!B5" 两种格式
    const cellRef = payload.cellRef.includes('!') ? payload.cellRef.split('!')[1] : payload.cellRef
    const activeSheet = workbook.getActiveSheet?.()
    if (!activeSheet) return
    // 解析 A1 格式为 row/col
    const m = cellRef.match(/^([A-Z]+)(\d+)$/i)
    if (!m) return
    const colStr = m[1].toUpperCase()
    const row = parseInt(m[2], 10) - 1
    let col = 0
    for (const ch of colStr) col = col * 26 + (ch.charCodeAt(0) - 64)
    col -= 1
    const range = activeSheet.getRange?.(row, col)
    if (range) {
      activeSheet.setActiveRange?.(range)
      // 滚动到目标单元格
      try { range.activate?.() } catch { /* ignore */ }
    }
    // 切回编辑区焦点
    showSidePanel.value = false
  } catch {
    /* Univer API 不稳定时静默忽略 */
  }
}
</script>

<style scoped>
.gt-wp-editor {
  display: flex; flex-direction: column; height: 100vh;
  background: var(--gt-color-bg);
}
.gt-step-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--gt-color-bg-light, #f8f7fc);
  border-bottom: 1px solid var(--gt-color-border, #e8e5f0);
  font-size: 13px;
}
.gt-step-nav__progress {
  display: flex;
  align-items: center;
  gap: 4px;
}
.gt-step-nav__label {
  color: var(--gt-color-text-secondary);
  margin-right: 8px;
}
.gt-step-nav__name {
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-step-nav__sheet {
  color: var(--gt-color-text-tertiary);
  margin-left: 8px;
  font-size: 12px;
}
.gt-step-nav__actions {
  display: flex;
  gap: 8px;
}

/* Stale 影响范围横条（保存后展示） */
.gt-stale-impact-bar {
  background: var(--gt-bg-warning, #fff8e6);
  border-bottom: 1px solid var(--gt-color-coral, #f5a700);
  padding: 8px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.gt-stale-impact-bar__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gt-stale-impact-bar__title {
  color: var(--gt-color-coral, #d49500);
  font-weight: 600;
}
.gt-stale-impact-bar__title strong {
  color: var(--gt-color-primary);
  font-size: 14px;
  margin: 0 2px;
}
.gt-stale-impact-bar__list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.gt-stale-impact-bar__tag {
  cursor: pointer;
  transition: opacity 0.15s;
}
.gt-stale-impact-bar__tag:hover {
  opacity: 0.7;
}
.gt-stale-impact-bar__more {
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
  margin-left: 4px;
}
.gt-wp-editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2) var(--gt-space-4);
  background: var(--gt-color-bg-white); box-shadow: var(--gt-shadow-sm); z-index: 10;
  flex-wrap: wrap; row-gap: 6px;
}
.gt-wp-editor-toolbar-left { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.gt-wp-editor-toolbar-right { display: flex; align-items: center; gap: var(--gt-space-2); flex-shrink: 0; }
.gt-wp-toolbar-primary { margin-right: 4px; }
.gt-wp-editor-code { font-weight: 700; color: var(--gt-color-primary); font-size: var(--gt-font-size-md); white-space: nowrap; }
.gt-wp-editor-name { color: var(--gt-color-text); font-size: var(--gt-font-size-md); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px; }
.gt-wp-editor-main {
  flex: 1; min-height: 0; position: relative; overflow: hidden;
  display: flex; flex-direction: row;
}
.gt-wp-editor-univer-wrapper { flex: 1; min-width: 0; min-height: 0; position: relative; overflow: hidden; }
.gt-wp-editor-center-col { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.gt-wp-editor-univer { width: 100%; height: 100%; }

/* 审计导航图对话框：基础布局（详细样式见全局 style 块，因 dialog 通过 append-to-body 传送脱离 scoped 作用域） */
.gt-audit-nav-dialog__body { height: 100%; }
.gt-wp-editor-left-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 240px;
  min-width: 0;
  border-right: 1px solid var(--gt-color-border-lighter, #e4e7ed);
  background: var(--gt-color-bg-page, #f8f7fc);
  padding: 6px;
  overflow-y: auto;
}
.gt-wp-editor-loading {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 12px; color: var(--gt-color-text-tertiary);
}
/* spec workpaper-editor-refactor Phase 4.1: 加载失败友好引导 overlay */
.gt-wp-editor-error-overlay {
  position: absolute; inset: 0; z-index: 100;
  display: flex; align-items: center; justify-content: center;
  background: var(--gt-color-bg-page, #f5f7fa);
  padding: 32px;
}
.gt-wp-editor-error-card {
  display: flex; flex-direction: column; align-items: center;
  gap: 16px; max-width: 480px;
  padding: 32px 40px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  text-align: center;
}
.gt-wp-editor-error-icon { font-size: 48px; line-height: 1; }
.gt-wp-editor-error-title {
  font-size: 18px; font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-wp-editor-error-message {
  font-size: 14px; line-height: 1.6;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-wp-editor-error-actions {
  display: flex; gap: 8px; margin-top: 8px;
}
.gt-wp-editor-statusbar {
  display: flex; gap: var(--gt-space-5); padding: 6px var(--gt-space-4);
  background: var(--gt-color-bg-white);
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-xs);
  border-top: 1px solid var(--gt-color-border-lighter);
  align-items: center;
}
.gt-wp-editor-statusbar > span {
  display: inline-flex; align-items: center; gap: 4px;
  padding-right: 12px; border-right: 1px solid var(--gt-color-border-lighter);
}
.gt-wp-editor-statusbar > span:last-of-type {
  border-right: none;
}
.gt-wp-smart-tip {
  margin-left: auto; cursor: pointer; color: var(--gt-color-wheat); font-weight: 500;
}
.gt-wp-smart-tip-detail {
  position: absolute; bottom: 30px; right: 12px; left: 12px;
  background: var(--gt-color-bg-white); border: 1px solid var(--gt-color-border-purple); border-radius: 8px;
  padding: 12px 16px; box-shadow: 0 -4px 16px rgba(0,0,0,0.08);
  z-index: 20; max-height: 300px; overflow-y: auto;
}
.gt-dirty-indicator {
  color: var(--gt-color-wheat);
  font-size: var(--gt-font-size-xs);
  font-weight: 500;
}
.gt-wp-completion-circle {
  flex-shrink: 0;
  margin-left: 4px;
}

/* ─── Sprint 2: Prefill tooltip ─── */
.gt-wp-prefill-tooltip {
  position: absolute;
  z-index: 100;
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-purple);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text);
  box-shadow: var(--gt-shadow-md);
  white-space: pre-line;
  max-width: 320px;
  pointer-events: none;
}

/* ─── Sprint 2: Formula bar ─── */
.gt-wp-formula-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px var(--gt-space-4);
  background: var(--gt-color-bg-elevated);
  border-bottom: 1px solid var(--gt-color-border-light);
  font-size: var(--gt-font-size-xs);
}
.gt-wp-formula-bar-label {
  font-weight: 700;
  color: var(--gt-color-primary);
  font-style: italic;
}
.gt-wp-formula-bar-text {
  color: var(--gt-color-text-secondary);
  font-family: monospace;
}

/* ─── Sprint 2: Cross-module reference overlay ─── */
.gt-cross-ref-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 50;
}
.gt-cross-ref-tag {
  position: absolute;
  pointer-events: auto;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  color: #fff;
  cursor: pointer;
  white-space: nowrap;
  opacity: 0.9;
  transition: opacity 0.15s;
}
.gt-cross-ref-tag:hover {
  opacity: 1;
  box-shadow: var(--gt-shadow-sm);
}

</style>

<!-- R1 需求 2：复核红点样式需全局生效（Univer overlay 在 Vue scope 外渲染） -->
<style>
.gt-review-marker-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--gt-color-coral);
  box-shadow: 0 0 0 2px rgba(230, 68, 62, 0.18), 0 1px 3px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  transition: transform 0.15s ease;
}
.gt-review-marker-dot:hover {
  transform: scale(1.2);
}
.gt-review-marker-popover {
  padding: 12px !important;
}

/* ─── 审计导航图对话框（全局样式：dialog append-to-body 已脱离 scoped 作用域） ─── */
.gt-audit-nav-dialog .el-dialog {
  resize: both; overflow: hidden; min-width: 700px; min-height: 500px;
  display: flex; flex-direction: column;
  border-radius: 12px;
}
.gt-audit-nav-dialog .el-dialog__header {
  margin: 0; padding: 14px 20px;
  background: linear-gradient(135deg, #6750A4 0%, #8b5cf6 100%);
  border-radius: 12px 12px 0 0;
}
.gt-audit-nav-dialog .el-dialog__body {
  flex: 1; overflow: auto; padding: 0 !important;
  background: #fafafa;
}
.gt-audit-nav-dialog.is-fullscreen .el-dialog {
  resize: none; border-radius: 0;
}
.gt-audit-nav-dialog.is-fullscreen .el-dialog__header {
  border-radius: 0;
}
/* 隐藏内嵌 WorkpaperAuditNav 自带的标题栏 */
.gt-audit-nav-dialog .gt-audit-nav-header {
  display: none !important;
}
.gt-audit-nav-dialog .gt-audit-nav {
  border: none !important; box-shadow: none !important; background: transparent !important;
}
.gt-audit-nav-dialog .gt-audit-nav-body {
  padding: 16px 20px;
}
/* dialog 自定义 header */
.gt-audit-nav-dialog__header {
  display: flex; align-items: center; gap: 12px;
}
.gt-audit-nav-dialog__title {
  display: flex; align-items: center; gap: 10px; flex: 1; color: #fff; font-size: 15px; font-weight: 600;
}
.gt-audit-nav-dialog__icon { font-size: 18px; }
.gt-audit-nav-dialog__code {
  padding: 2px 8px; background: rgba(255,255,255,0.25); border-radius: 4px;
  font-size: 12px; font-weight: 700;
}
.gt-audit-nav-dialog__name {
  font-size: 13px; font-weight: 400; color: rgba(255,255,255,0.9);
}
.gt-audit-nav-dialog__actions { display: flex; gap: 4px; }
.gt-audit-nav-dialog__actions .el-button {
  color: #fff !important;
}
.gt-audit-nav-dialog__actions .el-button:hover {
  background: rgba(255,255,255,0.15) !important;
}
</style>
