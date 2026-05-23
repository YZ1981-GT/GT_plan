<template>
  <!-- 路由分发：非 univer 类型使用对应子编辑器 -->
  <component
    v-if="componentType && componentType !== 'univer'"
    :is="editorComponent"
    :project-id="projectId"
    :wp-id="wpId"
    :wp-detail="wpDetail"
    @show-versions="onShowVersions"
    @toggle-panel="showSidePanel = !showSidePanel"
    @saved="onChildSaved"
  />

  <!-- 默认 Univer 编辑器（component_type='univer' 或未配置时） -->
  <div v-else class="gt-wp-editor gt-fade-in">
    <!-- 编辑锁提示 -->
    <el-alert v-if="editLock.locked.value && !editLock.isMine.value" type="warning" :closable="false" style="margin-bottom: 8px">
      {{ editLock.lockedBy.value || '其他用户' }} 正在编辑，当前为只读模式
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
        <el-button text @click="goBack">← 返回</el-button>
        <span class="gt-wp-editor-code" v-if="wpDetail">{{ wpDetail.wp_code }}</span>
        <span class="gt-wp-editor-name" v-if="wpDetail">{{ wpDetail.wp_name }}</span>
        <el-tag v-if="wpDetail" :type="(statusTagType(wpDetail.status)) || undefined" size="small">
          {{ statusLabel(wpDetail.status) }}
        </el-tag>
        <span v-if="dirty" class="gt-dirty-indicator">● 有未保存的变更</span>
      </div>
      <div class="gt-wp-editor-toolbar-right">
        <!-- E1 Sprint 2 Task 2.18: 复核状态 badge（L1-L5 + 专委会/IT/税务） -->
        <ReviewLayerBadges
          v-if="wpDetail?.wp_code?.startsWith('E1')"
          :project-id="projectId"
          :wp-id="wpId"
          :wp-code="wpDetail?.wp_code"
        />
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
      <div v-if="loading" class="gt-wp-editor-loading-overlay">
        <el-icon class="is-loading" :size="32" color="var(--gt-color-primary)"><Loading /></el-icon>
        <p>正在加载底稿...</p>
      </div>
      <!-- 左侧 Sheet 导航：v-show 保持 DOM（数据未就绪也先占位）-->
      <div v-show="!loading" class="gt-wp-editor-left-col">
        <!-- E1 Sprint 2 Task 2.5 + D-sales-cycle UAT #20: 审计导航图（左侧导航最顶部，默认展开可折叠） -->
        <WorkpaperAuditNav
          v-if="wpDetail && wpDetail.wp_code && (wpDetail.wp_code.startsWith('E1') || isDCycle || isFCycle || isHCycle || isICycle || isGCycle || isKCycle || isLCycle || isMCycle || isNCycle)"
          :project-id="projectId"
          :wp-id="wpId"
          :wp-code="wpDetail?.wp_code || 'E1'"
        />
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
        <!-- F-purchase-inventory F-F5 Task 2.9: F2-21~F2-26 监盘 sheet 触发按钮 -->
        <div
          v-if="showStocktakeTrigger"
          class="gt-stocktake-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="stocktakeDialogVisible = true"
          >
            📦 开始监盘
          </el-button>
        </div>
        <!-- H-fixed-assets-cycle H-F5 Task 2.7: H 循环 13 处监盘类 sheet 触发按钮 -->
        <div
          v-if="showHStocktakeTrigger"
          class="gt-stocktake-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="hStocktakeDialogVisible = true"
          >
            🏗️ 固定资产盘点
          </el-button>
        </div>
        <!-- F-purchase-inventory F-F11 Task 3.2: F2-38~F2-44 计价测试自动抽样按钮 -->
        <div
          v-if="showValuationTrigger"
          class="gt-valuation-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            :loading="valuationLoading"
            @click="onTriggerValuationSample"
          >
            🧮 自动抽样
          </el-button>
        </div>
        <!-- F-purchase-inventory F-F12 Task 3.5: F2-47 跌价准备 AI 分析按钮 -->
        <div
          v-if="showImpairmentTrigger"
          class="gt-impairment-trigger"
        >
          <el-button
            size="small"
            type="warning"
            plain
            @click="impairmentDialogVisible = true"
          >
            🤖 AI 分析跌价
          </el-button>
        </div>
        <!-- H-fixed-assets-cycle H-F11 Task 3.2: H1-12 折旧测算 sheet 自动计算按钮 -->
        <div
          v-if="showDepreciationCalcTrigger"
          class="gt-depreciation-calc-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="depreciationCalcDialogVisible = true"
          >
            🧮 自动计算
          </el-button>
        </div>
        <!-- H-fixed-assets-cycle H-F12 Task 3.4: H1-14 减值测算 sheet AI 辅助分析按钮 -->
        <div
          v-if="showAssetImpairmentTrigger"
          class="gt-asset-impairment-trigger"
        >
          <el-button
            size="small"
            type="warning"
            plain
            @click="assetImpairmentDialogVisible = true"
          >
            🤖 AI 辅助分析
          </el-button>
        </div>
        <!-- I-intangible-assets-cycle I-F4 Task 2.8: I3-6/I3-7 商誉减值 DCF 分析按钮 -->
        <div
          v-if="showGoodwillImpairmentTrigger"
          class="gt-goodwill-impairment-trigger"
        >
          <el-button
            size="small"
            type="warning"
            plain
            @click="goodwillImpairmentDialogVisible = true"
          >
            🤖 AI 辅助分析
          </el-button>
        </div>
        <!-- G-investment-cycle G-F4 Task 2.6: G1-6/G6/G8 公允价值测试按钮 -->
        <div
          v-if="showFairValueTestTrigger"
          class="gt-fair-value-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="fairValueTestDialogVisible = true"
          >
            📊 公允价值测试
          </el-button>
        </div>
        <!-- G-investment-cycle G-F5 Task 2.9: G4/G6 ECL 三阶段计算按钮 -->
        <div
          v-if="showECLCalcTrigger"
          class="gt-ecl-calc-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="eclCalcDialogVisible = true"
          >
            🧮 ECL 计算
          </el-button>
        </div>
        <!-- G-investment-cycle G-F11 Task 3.2: G1-8/G1-10 金融资产分类辅助按钮 -->
        <div
          v-if="showClassificationCheckTrigger"
          class="gt-classification-check-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="classificationCheckDialogVisible = true"
          >
            🏷️ 分类辅助
          </el-button>
        </div>
        <!-- I-intangible-assets-cycle I-F5 Task 2.10: I2-6 资本化时点判断按钮 -->
        <div
          v-if="showCapitalizationCheckTrigger"
          class="gt-capitalization-check-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="capitalizationCheckDialogVisible = true"
          >
            🧮 资本化时点判断
          </el-button>
        </div>
        <!-- I-intangible-assets-cycle I-F2 / Sprint 3 Task 3.2: I1-10/I1-11 + I4-6/I4-7 摊销自动计算按钮 -->
        <div
          v-if="amortizationCalcSection"
          class="gt-amortization-calc-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="amortizationCalcDialogVisible = true"
          >
            🧮 自动计算
          </el-button>
        </div>
        <!-- k-admin-cycle-post-review-fix P0 #1: K8/K9 费用分析按钮 -->
        <div
          v-if="isKCycle && /^K[89](\b|-|$|\d)/.test((wpDetail?.wp_code || '').toUpperCase())"
          class="gt-expense-analysis-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="expenseAnalysisDialogVisible = true"
          >
            📊 费用分析
          </el-button>
        </div>
        <!-- k-admin-cycle-post-review-fix P0 #2: K11 减值汇总按钮 -->
        <div
          v-if="isKCycle && /^K11(\b|-|$|\d)/.test((wpDetail?.wp_code || '').toUpperCase())"
          class="gt-impairment-summary-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="impairmentSummaryDialogVisible = true"
          >
            📋 减值汇总
          </el-button>
        </div>
        <!-- workpaper-l-debt-cycle L-F7: L1/L3 利息测算按钮 -->
        <div
          v-if="isLCycle && /^L[13](\b|-|$|\d)/.test((wpDetail?.wp_code || '').toUpperCase())"
          class="gt-interest-calc-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="interestCalcDialogVisible = true"
          >
            🧮 利息测算
          </el-button>
        </div>
        <!-- workpaper-l-debt-cycle L-F8: L5 摊余成本按钮 -->
        <div
          v-if="isLCycle && /^L5(\b|-|$|\d)/.test((wpDetail?.wp_code || '').toUpperCase())"
          class="gt-bond-amortization-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="bondAmortizationDialogVisible = true"
          >
            📊 摊余成本
          </el-button>
        </div>
        <!-- workpaper-m-equity-cycle M-F7: M6 权益变动表按钮 -->
        <div
          v-if="isMCycle && /^M6(\b|-|$|\d)/.test((wpDetail?.wp_code || '').toUpperCase())"
          class="gt-equity-movement-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="equityMovementDialogVisible = true"
          >
            📊 权益变动
          </el-button>
        </div>
        <!-- workpaper-n-tax-cycle N-F7: N5 所得税费用测算按钮 -->
        <div
          v-if="isNCycle && /^N5(\b|-|$|\d)/.test((wpDetail?.wp_code || '').toUpperCase())"
          class="gt-income-tax-calc-trigger"
        >
          <el-button
            size="small"
            type="primary"
            plain
            @click="incomeTaxCalcDialogVisible = true"
          >
            🧮 所得税测算
          </el-button>
        </div>
      </div>
      <!-- Univer 画布容器：始终 mount（Univer 需要 DOM 节点初始化）-->
      <div class="gt-wp-editor-univer-wrapper">
        <div ref="univerContainer" class="gt-wp-editor-univer"></div>
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
      :wp-code="wpDetail?.wp_code"
      :sheet-name="cellDetailSheet"
      :label="cellDetailLabel"
      @update:visible="showCellFormulaDetail = $event"
      @navigate="onCellDetailNavigate"
    />

    <!-- F-purchase-inventory F-F5 Task 2.7~2.9: 存货监盘 D 类弹窗 -->
    <InventoryStocktakeDialog
      v-if="wpDetail && isFCycle"
      :visible="stocktakeDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :wp-code="wpDetail.wp_code || ''"
      :stocktake-id="sheetNav.activeSheetId.value || ''"
      @update:visible="stocktakeDialogVisible = $event"
      @saved="onChildSaved"
    />

    <!-- F-purchase-inventory F-F12 Task 3.5: 跌价准备 AI 分析弹窗 -->
    <InventoryImpairmentDialog
      v-if="wpDetail && isFCycle"
      :visible="impairmentDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="impairmentDialogVisible = $event"
      @applied="onImpairmentApplied"
    />

    <!-- H-fixed-assets-cycle H-F5 Task 2.7: 固定资产监盘 D 类弹窗 -->
    <FixedAssetStocktakeDialog
      v-if="wpDetail && isHCycle"
      :visible="hStocktakeDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :wp-code="wpDetail.wp_code || ''"
      :stocktake-id="sheetNav.activeSheetId.value || ''"
      @update:visible="hStocktakeDialogVisible = $event"
      @saved="onChildSaved"
    />

    <!-- H-fixed-assets-cycle H-F11 Task 3.2: 折旧自动测算弹窗 -->
    <DepreciationCalcDialog
      v-if="wpDetail && isHCycle"
      :visible="depreciationCalcDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="depreciationCalcDialogVisible = $event"
      @applied="onDepreciationCalcApplied"
    />

    <!-- H-fixed-assets-cycle H-F12 Task 3.4: 减值 DCF 分析弹窗 -->
    <AssetImpairmentDialog
      v-if="wpDetail && isHCycle"
      :visible="assetImpairmentDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="assetImpairmentDialogVisible = $event"
      @applied="onAssetImpairmentApplied"
    />

    <!-- I-intangible-assets-cycle I-F4 Task 2.8: I3-6/I3-7 商誉减值 DCF 分析弹窗 -->
    <GoodwillImpairmentDialog
      v-if="wpDetail && isICycle"
      :visible="goodwillImpairmentDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="goodwillImpairmentDialogVisible = $event"
      @applied="onGoodwillImpairmentApplied"
    />

    <!-- I-intangible-assets-cycle I-F5 Task 2.10: I2-6 资本化时点判断弹窗 -->
    <CapitalizationCheckDialog
      v-if="wpDetail && isICycle"
      :visible="capitalizationCheckDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="capitalizationCheckDialogVisible = $event"
      @applied="onCapitalizationCheckApplied"
    />

    <!-- I-intangible-assets-cycle I-F2 / Sprint 3 Task 3.2: I1/I4 摊销自动测算弹窗 -->
    <AmortizationCalcDialog
      v-if="wpDetail && isICycle && amortizationCalcSection"
      :visible="amortizationCalcDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :section="amortizationCalcSection"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="amortizationCalcDialogVisible = $event"
      @applied="onAmortizationCalcApplied"
    />

    <!-- G-investment-cycle G-F4 Task 2.6: G1-6/G6/G8 公允价值测试弹窗 -->
    <FairValueTestDialog
      v-if="wpDetail && isGCycle"
      :visible="fairValueTestDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      :instrument-type="fairValueInstrumentType"
      @update:visible="fairValueTestDialogVisible = $event"
      @applied="onFairValueTestApplied"
    />

    <!-- G-investment-cycle G-F5 Task 2.9: G4/G6 ECL 三阶段计算弹窗 -->
    <ECLCalcDialog
      v-if="wpDetail && isGCycle"
      :visible="eclCalcDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      :instrument-type="eclInstrumentType"
      @update:visible="eclCalcDialogVisible = $event"
      @applied="onECLCalcApplied"
    />

    <!-- G-investment-cycle G-F11 Task 3.2: G1-8/G1-10 金融资产分类辅助弹窗 -->
    <ClassificationCheckDialog
      v-if="wpDetail && isGCycle"
      :visible="classificationCheckDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="classificationCheckDialogVisible = $event"
      @applied="onClassificationCheckApplied"
    />

    <!-- k-admin-cycle-post-review-fix P0 #1: K8/K9 费用分析弹窗 -->
    <ExpenseAnalysisDialog
      v-if="wpDetail && isKCycle"
      :visible="expenseAnalysisDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="expenseAnalysisDialogVisible = $event"
      @applied="onExpenseAnalysisApplied"
    />

    <!-- k-admin-cycle-post-review-fix P0 #2: K11 跨循环减值汇总弹窗 -->
    <ImpairmentSummaryDialog
      v-if="wpDetail && isKCycle"
      :visible="impairmentSummaryDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="impairmentSummaryDialogVisible = $event"
      @applied="onImpairmentSummaryApplied"
    />

    <!-- workpaper-l-debt-cycle L-F7: L1/L3 利息测算弹窗 -->
    <InterestCalcDialog
      v-if="wpDetail && isLCycle"
      :visible="interestCalcDialogVisible"
      :project-id="projectId"
      :workpaper-id="wpId"
      :wp-code="(wpDetail?.wp_code || 'L1').startsWith('L3') ? 'L3' : 'L1'"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="interestCalcDialogVisible = $event"
      @applied="onInterestCalcApplied"
    />

    <!-- workpaper-l-debt-cycle L-F8: L5 摊余成本弹窗 -->
    <BondAmortizationDialog
      v-if="wpDetail && isLCycle"
      :visible="bondAmortizationDialogVisible"
      :project-id="projectId"
      :workpaper-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="bondAmortizationDialogVisible = $event"
      @applied="onBondAmortizationApplied"
    />

    <!-- workpaper-m-equity-cycle M-F7: M6 权益变动表弹窗 -->
    <EquityMovementDialog
      v-if="wpDetail && isMCycle"
      :visible="equityMovementDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="equityMovementDialogVisible = $event"
      @applied="onEquityMovementApplied"
    />

    <!-- workpaper-n-tax-cycle N-F7: N5 所得税费用测算弹窗 -->
    <IncomeTaxCalcDialog
      v-if="wpDetail && isNCycle"
      :visible="incomeTaxCalcDialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :target-sheet="sheetNav.activeSheetId.value || ''"
      @update:visible="incomeTaxCalcDialogVisible = $event"
      @applied="onIncomeTaxCalcApplied"
    />

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
    v-if="componentType && componentType !== 'univer'"
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
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage } from 'element-plus'
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
import { eventBus, type SyncEventPayload, type WorkpaperSavedPayload, type CrossRefUpdatedPayload } from '@/utils/eventBus'
import { useWorkpaperReviewMarkers, type ReviewMarkerTicket } from '@/composables/useWorkpaperReviewMarkers'
import { useEditingLock } from '@/composables/useEditingLock'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { usePrefillMarkers } from '@/composables/usePrefillMarkers'
import { useCrossModuleRefs, TARGET_COLOR_MAP } from '@/composables/useCrossModuleRefs'
import { useReviewMarks, type ReviewStatus } from '@/composables/useReviewMarks'
import { useUserOverrides } from '@/composables/useUserOverrides'
import { useStepMapping } from '@/composables/useStepMapping'
import { useStaleImpact, type StaleAffectedItem } from '@/composables/useStaleImpact'
import { useUniverSheetNav, type SheetGroup } from '@/composables/useUniverSheetNav'
import { useDSalesCycleSheetGroups } from '@/composables/useDSalesCycleSheetGroups'
import { useFPurchaseInventorySheetGroups } from '@/composables/useFPurchaseInventorySheetGroups'
import { useHFixedAssetSheetGroups } from '@/composables/useHFixedAssetSheetGroups'
import { useIIntangibleAssetSheetGroups } from '@/composables/useIIntangibleAssetSheetGroups'
import { useKAdminCycleSheetGroups } from '@/composables/useKAdminCycleSheetGroups'
import { useLDebtCycleSheetGroups } from '@/composables/useLDebtCycleSheetGroups'
import { useMEquityCycleSheetGroups } from '@/composables/useMEquityCycleSheetGroups'
import { useNTaxCycleSheetGroups } from '@/composables/useNTaxCycleSheetGroups'
import { useBAuditPlanSheetGroups } from '@/composables/useBAuditPlanSheetGroups'
import { useCControlTestSheetGroups } from '@/composables/useCControlTestSheetGroups'
import {
  useGInvestmentCycleSheetGroups,
  type GParsedData,
} from '@/composables/useGInvestmentCycleSheetGroups'
import { useDepreciationBranchSelector } from '@/composables/useDepreciationBranchSelector'
import DepreciationBranchSelector from '@/components/workpaper/DepreciationBranchSelector.vue'
import WorkpaperSidePanel from '@/components/workpaper/WorkpaperSidePanel.vue'
import UniverSheetNav from '@/components/workpaper/UniverSheetNav.vue'
import WorkpaperAuditNav from '@/components/workpaper/WorkpaperAuditNav.vue'
import ProcedureDialogLauncher from '@/components/workpaper/ProcedureDialogLauncher.vue'
import InventoryStocktakeDialog from '@/components/workpaper/InventoryStocktakeDialog.vue'
import FixedAssetStocktakeDialog from '@/components/workpaper/FixedAssetStocktakeDialog.vue'
import DepreciationCalcDialog from '@/components/workpaper/DepreciationCalcDialog.vue'
import AssetImpairmentDialog from '@/components/workpaper/AssetImpairmentDialog.vue'
import FairValueTestDialog from '@/components/workpaper/FairValueTestDialog.vue'
import ECLCalcDialog from '@/components/workpaper/ECLCalcDialog.vue'
import ClassificationCheckDialog from '@/components/workpaper/ClassificationCheckDialog.vue'
import GoodwillImpairmentDialog from '@/components/workpaper/GoodwillImpairmentDialog.vue'
import CapitalizationCheckDialog from '@/components/workpaper/CapitalizationCheckDialog.vue'
import AmortizationCalcDialog from '@/components/workpaper/AmortizationCalcDialog.vue'
import InventoryImpairmentDialog from '@/components/workpaper/InventoryImpairmentDialog.vue'
// k-admin-cycle-post-review-fix P0 #1-2: K 循环弹窗 wiring（K8/K9 费用分析 + K11 减值汇总）
import ExpenseAnalysisDialog from '@/components/workpaper/ExpenseAnalysisDialog.vue'
import ImpairmentSummaryDialog from '@/components/workpaper/ImpairmentSummaryDialog.vue'
// workpaper-l-debt-cycle L-F7/L-F8: L 循环弹窗 wiring（L1/L3 利息测算 + L5 摊余成本）
import InterestCalcDialog from '@/components/workpaper/InterestCalcDialog.vue'
import BondAmortizationDialog from '@/components/workpaper/BondAmortizationDialog.vue'
// proposal-remaining-18 task 5.4 (S-4)：历史版本搜索
import VersionHistorySearch from '@/components/workpaper/VersionHistorySearch.vue'
// workpaper-m-equity-cycle M-F7: M6 权益变动表弹窗
import EquityMovementDialog from '@/components/workpaper/EquityMovementDialog.vue'
// workpaper-n-tax-cycle N-F7: N5 所得税费用测算弹窗
import IncomeTaxCalcDialog from '@/components/workpaper/IncomeTaxCalcDialog.vue'
import ReviewLayerBadges from '@/components/workpaper/ReviewLayerBadges.vue'
import { usePrerequisiteStatus } from '@/composables/usePrerequisiteStatus'
import { useWorkpaperRefresh } from '@/composables/useWorkpaperRefresh'
import CellFormulaDetail from '@/components/CellFormulaDetail.vue'
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

// ─── component_type 路由逻辑 ─────────────────────────────────────────────────
const componentType = ref<string>('univer')
const editorComponent = computed(() => EDITOR_MAP[componentType.value] || null)

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
// D 类 wp_code 形如 D0/D1/.../D7（含子表 D2-1, D4-22A 等），统一以 /^D\d/ 识别
const isDCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^D\d/.test(code)
})

// F 采购存货循环 task 2.2: F 类 wp_code 形如 F0/F1/.../F5（含子表 F2-1, F2-21A 等），以 /^F\d/ 识别
const isFCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^F\d/.test(code)
})

// H 固定资产循环 task 2.4: H 类 wp_code 形如 H0/H1/.../H10（含子表 H1-12, H8-8 等），以 /^H\d/ 识别
const isHCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^H\d/.test(code)
})

// I 无形资产循环 task 2.1: I 类 wp_code 形如 I0/I1/.../I6（含子表 I1-10, I4-7 等），以 /^I\d/ 识别
const isICycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^I\d/.test(code)
})

// G 投资循环 task 2.2: G 类 wp_code 形如 G0/G1/.../G14（含子表 G1-2, G7-3 等），以 /^G\d/ 识别
const isGCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^G\d/.test(code)
})

// K 管理循环 task 2.3: K 类 wp_code 形如 K0/K1/.../K13（含子表 K8-2, K1-12 等），以 /^K\d/ 识别
const isKCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^K\d/.test(code)
})

// L 筹资循环 task 2.1: L 类 wp_code 形如 L0/L1/.../L8（含子表 L1-2, L8-2 等），以 /^L\d/ 识别
const isLCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^L\d/.test(code)
})

// M 权益循环 task 2.3: M 类 wp_code 形如 M1/M2/.../M10（含子表 M2-2, M6-2 等），以 /^M\d/ 识别
const isMCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^M\d/.test(code)
})

// N 税金循环 task 2.1: N 类 wp_code 形如 N1/N2/.../N5（含子表 N2-1, N5-4 等），以 /^N\d/ 识别
const isNCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^N\d/.test(code)
})

// B 类底稿（控制了解/审计计划）: B1, B10, B15, B22, B23, B30, B40, B50, B51, B52, B60
const isBCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^B\d|^B[1-6]/i.test(code)
})

// C 类底稿（控制测试）: C1~C26
const isCCycle = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  return /^C\d/i.test(code)
})

// 同时实例化三个 nav，按 isDCycle/isFCycle 选择活跃的对外暴露
// 三者接口一致（groups / activeSheetId / totalCount / refresh / switchTo），
// 未激活的一方 sheets/groups 数据虽被算但不显示，不影响功能。
const eUniverNav = useUniverSheetNav(univerAPIRef, scenarioFilter)
const dCycleNav = useDSalesCycleSheetGroups(univerAPIRef, scenarioFilter)
const fCycleNav = useFPurchaseInventorySheetGroups(univerAPIRef, scenarioFilter)
// H 固定资产循环 nav（读取 project measurement_model 控制 H3/H7 sheet 显隐）
const measurementModelRef = computed(() => projectMeta.value?.measurement_model || 'cost')
const hCycleNav = useHFixedAssetSheetGroups(univerAPIRef, measurementModelRef)
// I 无形资产循环 task 2.4: I 循环 nav（10 类分组规则，无 measurement_model 参数）
const iCycleNav = useIIntangibleAssetSheetGroups(univerAPIRef)

// G 投资循环 task 2.2: G 循环 nav（12 类分组规则 + G7 三种核算方式 per-investment 显隐）
// - parsed_data 来自 wpDetail.parsed_data（含 g7_accounting_methods 数组）
// - currentInvesteeName 当前 G7 选中投资名（per-investment 选择器为后续打磨项，此处置 null
//   触发 fallback 全显，避免阻塞 G-F2 主体功能）
const gParsedDataRef = computed<GParsedData | null>(() => {
  const pd = (wpDetail.value as any)?.parsed_data
  return (pd ?? null) as GParsedData | null
})
const gCurrentInvesteeNameRef = ref<string | null>(null)
const gCycleNav = useGInvestmentCycleSheetGroups(
  univerAPIRef,
  gParsedDataRef,
  gCurrentInvesteeNameRef,
)

// K 管理循环 task 2.1: K 循环 nav（10 类分组规则）
const kCycleNav = useKAdminCycleSheetGroups(univerAPIRef)

// L 筹资循环 task 2.1: L 循环 nav（10 类分组规则）
const lCycleNav = useLDebtCycleSheetGroups(univerAPIRef)

// M 权益循环 task 2.3: M 循环 nav（8 类分组规则）
const mCycleNav = useMEquityCycleSheetGroups(univerAPIRef)

// N 税金循环 task 2.1: N 循环 nav（8 类分组规则）
const nCycleNav = useNTaxCycleSheetGroups(univerAPIRef)

// B 类底稿（控制了解/审计计划）nav（7 类分组规则）
const bCycleNav = useBAuditPlanSheetGroups(univerAPIRef)

// C 类底稿（控制测试）nav（5 类分组规则）
const cCycleNav = useCControlTestSheetGroups(univerAPIRef)

// 统一对外 facade（保持模板原有 sheetNav.groups.value / sheetNav.activeSheetId.value 调用形态）
const sheetNavGroups = computed<SheetGroup[]>(() => {
  if (isHCycle.value) return hCycleNav.groups.value as unknown as SheetGroup[]
  if (isICycle.value) return iCycleNav.groups.value as unknown as SheetGroup[]
  if (isGCycle.value) return gCycleNav.groups.value as unknown as SheetGroup[]
  if (isKCycle.value) return kCycleNav.groups.value as unknown as SheetGroup[]
  if (isLCycle.value) return lCycleNav.groups.value as unknown as SheetGroup[]
  if (isMCycle.value) return mCycleNav.groups.value as unknown as SheetGroup[]
  if (isNCycle.value) return nCycleNav.groups.value as unknown as SheetGroup[]
  if (isBCycle.value) return bCycleNav.groups.value as unknown as SheetGroup[]
  if (isCCycle.value) return cCycleNav.groups.value as unknown as SheetGroup[]
  if (isFCycle.value) return fCycleNav.groups.value
  if (isDCycle.value) return dCycleNav.groups.value
  return eUniverNav.groups.value
})
const sheetNavActiveId = computed<string>(() => {
  if (isHCycle.value) return hCycleNav.activeSheetId.value
  if (isICycle.value) return iCycleNav.activeSheetId.value
  if (isGCycle.value) return gCycleNav.activeSheetId.value
  if (isKCycle.value) return kCycleNav.activeSheetId.value
  if (isLCycle.value) return lCycleNav.activeSheetId.value
  if (isMCycle.value) return mCycleNav.activeSheetId.value
  if (isNCycle.value) return nCycleNav.activeSheetId.value
  if (isBCycle.value) return bCycleNav.activeSheetId.value
  if (isCCycle.value) return cCycleNav.activeSheetId.value
  if (isFCycle.value) return fCycleNav.activeSheetId.value
  if (isDCycle.value) return dCycleNav.activeSheetId.value
  return eUniverNav.activeSheetId.value
})
const sheetNavTotalCount = computed<number>(() => {
  if (isHCycle.value) return hCycleNav.totalCount.value
  if (isICycle.value) return iCycleNav.totalCount.value
  if (isGCycle.value) return gCycleNav.totalCount.value
  if (isKCycle.value) return kCycleNav.totalCount.value
  if (isLCycle.value) return lCycleNav.totalCount.value
  if (isMCycle.value) return mCycleNav.totalCount.value
  if (isNCycle.value) return nCycleNav.totalCount.value
  if (isBCycle.value) return bCycleNav.totalCount.value
  if (isCCycle.value) return cCycleNav.totalCount.value
  if (isFCycle.value) return fCycleNav.totalCount.value
  if (isDCycle.value) return dCycleNav.totalCount.value
  return eUniverNav.totalCount.value
})
function sheetNavSwitchTo(id: string) {
  if (isHCycle.value) hCycleNav.switchTo(id)
  else if (isICycle.value) iCycleNav.switchTo(id)
  else if (isGCycle.value) gCycleNav.switchTo(id)
  else if (isKCycle.value) kCycleNav.switchTo(id)
  else if (isLCycle.value) lCycleNav.switchTo(id)
  else if (isMCycle.value) mCycleNav.switchTo(id)
  else if (isNCycle.value) nCycleNav.switchTo(id)
  else if (isBCycle.value) bCycleNav.switchTo(id)
  else if (isCCycle.value) cCycleNav.switchTo(id)
  else if (isFCycle.value) fCycleNav.switchTo(id)
  else if (isDCycle.value) dCycleNav.switchTo(id)
  else eUniverNav.switchTo(id)
}
function sheetNavRefresh() {
  if (isHCycle.value) hCycleNav.refresh()
  else if (isICycle.value) iCycleNav.refresh()
  else if (isGCycle.value) gCycleNav.refresh()
  else if (isKCycle.value) kCycleNav.refresh()
  else if (isLCycle.value) lCycleNav.refresh()
  else if (isMCycle.value) mCycleNav.refresh()
  else if (isNCycle.value) nCycleNav.refresh()
  else if (isBCycle.value) bCycleNav.refresh()
  else if (isCCycle.value) cCycleNav.refresh()
  else if (isFCycle.value) fCycleNav.refresh()
  else if (isDCycle.value) dCycleNav.refresh()
  else eUniverNav.refresh()
}
const sheetNav = {
  groups: sheetNavGroups,
  activeSheetId: sheetNavActiveId,
  totalCount: sheetNavTotalCount,
  switchTo: sheetNavSwitchTo,
  refresh: sheetNavRefresh,
  // 仅 E 类（useUniverSheetNav）独有，D/F 类不需要外币显隐
  applyForeignCurrencyVisibility: () => eUniverNav.applyForeignCurrencyVisibility(),
}
const sheetNavCollapsed = ref(false)

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
const iActiveSheetName = computed(() => {
  if (!isICycle.value) return ''
  const activeId = iCycleNav.activeSheetId.value
  const sheet = iCycleNav.sheets.value.find((s: any) => s.id === activeId)
  return sheet?.name || ''
})
const iAllSheetNames = computed(() => {
  if (!isICycle.value) return []
  return iCycleNav.sheets.value.map((s: any) => s.name)
})
const iBranchSelector = useDepreciationBranchSelector(
  iActiveSheetName,
  iAllSheetNames,
  (sheetName: string) => {
    const target = iCycleNav.sheets.value.find((s: any) => s.name === sheetName)
    if (target) iCycleNav.switchTo(target.id)
  },
)

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

const wpDetail = ref<WorkpaperDetail | null>(null)
const loading = ref(true)
const saving = ref(false)
const submitting = ref(false)
const syncLoading = ref(false)
const prefillLoading = ref(false)
const dirty = ref(false)
const showSidePanel = ref(false)
// R8-S2-02：自检未通过项数（由 WorkpaperSidePanel @finecheck-update 同步）
const fineCheckFailCount = ref(0)
const univerContainer = ref<HTMLElement | null>(null)

// F-purchase-inventory F-F5 Task 2.7~2.9: 存货监盘弹窗状态
const stocktakeDialogVisible = ref(false)
// F2 监盘 sheet 触发按钮显示条件：F 循环且 active sheet 名匹配 F2-21~F2-26
const showStocktakeTrigger = computed(() => {
  if (!isFCycle.value) return false
  const wpCode = (wpDetail.value?.wp_code || '').toUpperCase()
  // F2 主底稿（顶层 wp_code 为 F2）或 F2-21~F2-26 子表
  if (!wpCode.startsWith('F2')) return false
  const activeId = sheetNav.activeSheetId.value || ''
  // 匹配 F2-21A、F2-22B、F2-26 等监盘类 sheet
  return /F2-2[1-6]/i.test(activeId) || /监盘|盘点|抽盘/.test(activeId)
})

// H-fixed-assets-cycle H-F5 Task 2.7: 固定资产监盘弹窗状态
const hStocktakeDialogVisible = ref(false)
// H 循环 13 处监盘类 sheet 触发按钮显示条件
const showHStocktakeTrigger = computed(() => {
  if (!isHCycle.value) return false
  const activeId = sheetNav.activeSheetId.value || ''
  // 匹配 H1-9~H1-11 / H2-12~H2-14 / H3-9 / H5-9~H5-11 / H7-8~H7-10
  return /H[1-9]-(?:9|1[0-4])/i.test(activeId) || /监盘|盘点/.test(activeId)
})

// F-purchase-inventory F-F11 Task 3.2: F2-38~F2-44 计价测试自动抽样按钮
const valuationLoading = ref(false)
const showValuationTrigger = computed(() => {
  if (!isFCycle.value) return false
  const wpCode = (wpDetail.value?.wp_code || '').toUpperCase()
  if (!wpCode.startsWith('F2')) return false
  const activeId = sheetNav.activeSheetId.value || ''
  return /F2-(3[89]|4[0-4])/i.test(activeId) || /计价测试|价格测试/.test(activeId)
})

async function onTriggerValuationSample() {
  valuationLoading.value = true
  try {
    const year = new Date().getFullYear()
    // P0-3 写回联动：apply_to_sheet 传当前 active sheet 名，让结果落到 parsed_data
    const activeSheet = sheetNav.activeSheetId.value || ''
    const resp: any = await httpApi.post(
      `/api/projects/${projectId.value}/workpapers/${wpId.value}/f2/valuation-sample`,
      {
        method: 'weighted_average',
        account_code: '1403',
        year,
        sample_size: 20,
        high_value_threshold: 100000,
        period: '全年',
        apply_to_sheet: activeSheet,
      },
    )
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已抽样 ${resp?.total_samples || 0} 笔并写回 ${resp.applied_to_sheet}`)
      // 触发底稿刷新使 parsed_data 重读
      eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
    } else {
      ElMessage.success(`已抽样 ${resp?.total_samples || 0} 笔（${resp?.method}），未写回`)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '抽样失败')
  } finally {
    valuationLoading.value = false
  }
}

// F-purchase-inventory F-F12 Task 3.5: F2-47 跌价准备 AI 分析弹窗状态
const impairmentDialogVisible = ref(false)
const showImpairmentTrigger = computed(() => {
  if (!isFCycle.value) return false
  const wpCode = (wpDetail.value?.wp_code || '').toUpperCase()
  if (!wpCode.startsWith('F2')) return false
  const activeId = sheetNav.activeSheetId.value || ''
  return /F2-4[789]/i.test(activeId) || /跌价|减值|可变现/.test(activeId)
})

// P0-3 写回联动：弹窗写回成功后刷新底稿
function onImpairmentApplied(sheet: string) {
  ElMessage.success(`跌价分析已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// H-fixed-assets-cycle H-F11 Task 3.2: H1-12 折旧测算 sheet 自动计算按钮
const depreciationCalcDialogVisible = ref(false)
const showDepreciationCalcTrigger = computed(() => {
  if (!isHCycle.value) return false
  const activeId = sheetNav.activeSheetId.value || ''
  // 匹配折旧测算表 H1-12 / H3-7 / H5-12 / H7-11 / H8-8
  return /折旧测算表.*H1-12|H3-7|H5-12|H7-11|H8-8/i.test(activeId) || /折旧测算/.test(activeId)
})

// H-F11 写回联动：弹窗写回成功后刷新底稿
function onDepreciationCalcApplied(sheet: string) {
  ElMessage.success(`折旧测算已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// H-fixed-assets-cycle H-F12 Task 3.4: H1-14 减值测算 sheet AI 辅助分析按钮
const assetImpairmentDialogVisible = ref(false)
const showAssetImpairmentTrigger = computed(() => {
  if (!isHCycle.value) return false
  const activeId = sheetNav.activeSheetId.value || ''
  // 匹配减值测算表 H1-14 / 减值测试相关 sheet
  return /减值测算表.*H1-14|减值测算.*H\d/i.test(activeId) || /减值测算表H1-14/.test(activeId)
})

// H-F12 写回联动：弹窗写回成功后刷新底稿
function onAssetImpairmentApplied(sheet: string) {
  ElMessage.success(`减值分析已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// I-intangible-assets-cycle I-F4 Task 2.8: I3-6/I3-7 商誉减值 DCF 分析按钮
const goodwillImpairmentDialogVisible = ref(false)
const showGoodwillImpairmentTrigger = computed(() => {
  if (!isICycle.value) return false
  const activeId = sheetNav.activeSheetId.value || ''
  // 匹配 I3 商誉减值 sheet（I3-6/I3-7 + 商誉减值/可收回金额）
  return /商誉减值|可收回金额.*I3|减值.*I3-[67]|I3-[67]/i.test(activeId)
})

// I-F4 写回联动：弹窗写回成功后刷新底稿
function onGoodwillImpairmentApplied(sheet: string) {
  ElMessage.success(`商誉减值分析已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// I-intangible-assets-cycle I-F5 Task 2.10: I2-6 资本化时点判断按钮
const capitalizationCheckDialogVisible = ref(false)
const showCapitalizationCheckTrigger = computed(() => {
  if (!isICycle.value) return false
  const activeId = sheetNav.activeSheetId.value || ''
  // 匹配 I2-6 资本化时点判断 sheet（按真实命名"项目成立条件 / 资本化时点 / I2-6"匹配）
  return /资本化时点|项目成立条件.*I2|I2-6/i.test(activeId)
})

// I-F5 写回联动：弹窗写回成功后刷新底稿
function onCapitalizationCheckApplied(sheet: string) {
  ElMessage.success(`资本化时点判断已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// I-intangible-assets-cycle I-F2 / Sprint 3 Task 3.2: I1-10/I1-11 + I4-6/I4-7 摊销自动测算
const amortizationCalcDialogVisible = ref(false)

// 当前 sheet 是否命中 I1 / I4 摊销 sheet — 命中时返回对应 section（'I1' / 'I4'），否则返回 null
const amortizationCalcSection = computed<'I1' | 'I4' | null>(() => {
  if (!isICycle.value) return null
  const activeId = sheetNav.activeSheetId.value || ''
  // I1-10（不含减值-剩余年限法） / I1-11（含减值）
  if (/摊销测算.*I1-1[01]|I1-1[01].*摊销/.test(activeId)) return 'I1'
  // I4-6（直线法） / I4-7（工作量法）
  if (/摊销测算.*I4-[67]|I4-[67].*摊销/.test(activeId)) return 'I4'
  return null
})

// I-F2 写回联动：弹窗写回成功后刷新底稿
function onAmortizationCalcApplied(sheet: string) {
  ElMessage.success(`摊销测算已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// G-investment-cycle G-F4 Task 2.6: G1-6/G6/G8 公允价值测试弹窗
const fairValueTestDialogVisible = ref(false)
// 显示条件：G 循环 && 当前 sheet 名匹配公允价值测试类（G1-6 / G6 / G8 公允价值测试 sheet）
// 与 ADR-G6 sheet 分组规则保持一致：/公允价值测试|公允价值计量|第三层次/
const showFairValueTestTrigger = computed(() => {
  if (!isGCycle.value) return false
  const activeId = sheetNav.activeSheetId.value || ''
  return /公允价值测试|公允价值计量|第三层次/.test(activeId)
})

// 按当前 wp_code 推荐 instrumentType 默认值（G1=交易性金融资产 / G6=其他债权投资 / G8=其他权益工具投资）
const fairValueInstrumentType = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  if (code.startsWith('G1') && !code.startsWith('G10') && !code.startsWith('G11') && !code.startsWith('G12') && !code.startsWith('G13') && !code.startsWith('G14')) {
    return '交易性金融资产'
  }
  if (code.startsWith('G6')) return '其他债权投资'
  if (code.startsWith('G8')) return '其他权益工具投资'
  if (code.startsWith('G10')) return '交易性金融负债'
  if (code.startsWith('G12')) return '净敞口套期'
  if (code.startsWith('G13')) return '公允价值变动收益'
  return '交易性金融资产'
})

// G-F4 写回联动：弹窗写回成功后刷新底稿
function onFairValueTestApplied(sheet: string) {
  ElMessage.success(`公允价值测试已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// G-investment-cycle G-F5 Task 2.9: G4/G6 ECL 三阶段计算弹窗
const eclCalcDialogVisible = ref(false)

// 显示条件：G 循环 && wp_code 以 G4 或 G6 开头 && 当前 sheet 名匹配减值/信用损失/ECL 模式
// 与 ADR-G6 sheet 分组规则保持一致：/减值|信用损失|ECL/
const showECLCalcTrigger = computed(() => {
  if (!isGCycle.value) return false
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  // G4*（如 G4 / G4-2 等） 或 G6*（如 G6 / G6-2 等）
  if (!(/^G4(\b|-|$|\d)/.test(code) || /^G6(\b|-|$|\d)/.test(code))) {
    return false
  }
  const activeId = sheetNav.activeSheetId.value || ''
  return /减值|信用损失|ECL/.test(activeId)
})

// 按当前 wp_code 推荐 instrumentType 默认值（G4=债权投资 / G6=其他债权投资）
const eclInstrumentType = computed(() => {
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  if (code.startsWith('G4')) return '债权投资'
  if (code.startsWith('G6')) return '其他债权投资'
  return '债权投资'
})

// G-F5 写回联动：弹窗写回成功后刷新底稿
function onECLCalcApplied(sheet: string) {
  ElMessage.success(`ECL 计算已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// G-investment-cycle G-F11 Task 3.2: G1-8/G1-10 金融资产分类辅助弹窗
const classificationCheckDialogVisible = ref(false)
// 显示条件：G 循环 && wp_code 以 G1 开头（含 G1-8/G1-10）&& active sheet 命中分类相关 sheet
// 与 ADR-G6 sheet 分组规则保持一致：/业务模式|合同现金流|分类.*适当性|SPPI/
const showClassificationCheckTrigger = computed(() => {
  if (!isGCycle.value) return false
  const code = (wpDetail.value?.wp_code || '').toUpperCase()
  // 仅 G1 开头（排除 G10/G11/G12/G13/G14）
  if (!/^G1(\b|-|$)/.test(code) && !/^G1\d?$/.test(code)) {
    // 允许 G1 / G1-8 / G1-10 等
    if (!code.startsWith('G1') || code.startsWith('G10') || code.startsWith('G11') || code.startsWith('G12') || code.startsWith('G13') || code.startsWith('G14')) {
      return false
    }
  }
  const activeId = sheetNav.activeSheetId.value || ''
  return /业务模式|合同现金流|分类.*适当性|SPPI/.test(activeId)
})

// G-F11 写回联动：弹窗写回成功后刷新底稿
function onClassificationCheckApplied(sheet: string) {
  ElMessage.success(`分类辅助已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// k-admin-cycle-post-review-fix P0 #1: K8/K9 费用分析弹窗（visible ref + applied handler）
const expenseAnalysisDialogVisible = ref(false)
function onExpenseAnalysisApplied(sheet: string) {
  ElMessage.success(`费用分析已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// k-admin-cycle-post-review-fix P0 #2: K11 跨循环减值汇总弹窗（visible ref + applied handler）
const impairmentSummaryDialogVisible = ref(false)
function onImpairmentSummaryApplied(sheet: string) {
  ElMessage.success(`减值汇总已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// workpaper-l-debt-cycle L-F7: L1/L3 利息测算弹窗（visible ref + applied handler）
const interestCalcDialogVisible = ref(false)
function onInterestCalcApplied(sheet: string) {
  ElMessage.success(`利息测算已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// workpaper-l-debt-cycle L-F8: L5 摊余成本弹窗（visible ref + applied handler）
const bondAmortizationDialogVisible = ref(false)
function onBondAmortizationApplied(sheet: string) {
  ElMessage.success(`摊余成本已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// workpaper-m-equity-cycle M-F7: M6 权益变动表弹窗（visible ref + applied handler）
const equityMovementDialogVisible = ref(false)
function onEquityMovementApplied(sheet: string) {
  ElMessage.success(`权益变动已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

// workpaper-n-tax-cycle N-F7: N5 所得税费用测算弹窗（visible ref + applied handler）
const incomeTaxCalcDialogVisible = ref(false)
function onIncomeTaxCalcApplied(sheet: string) {
  ElMessage.success(`所得税测算已写回 ${sheet}`)
  eventBus.emit('workpaper:saved', { wp_id: wpId.value } as any)
}

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

async function initUniver() {
  if (!univerContainer.value) return

  // 1. 加载底稿详情
  try {
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch (e: any) {
    handleApiError(e, '底稿不存在')
    goBack()
    return
  }

  // E1 Sprint 2: 加载项目元数据（scenario + has_foreign_currency）
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
  setTimeout(() => {
    sheetNav.refresh()
    // E1 Sprint 2 Task 2.37: 应用 has_foreign_currency 显隐规则到 E1-1
    if (wpDetail.value?.wp_code?.startsWith('E1')) {
      sheetNav.applyForeignCurrencyVisibility()
    }
  }, 100)

  loading.value = false

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

/**
 * F6 D 销售循环 task 2.12: 响应 cross-ref:updated 事件
 * 当 D0 函证回函触发 stale 传播后，如果当前打开的底稿是目标 wp_code，
 * 自动刷新 sheet nav + 重新触发 prefill 显示
 */
function onCrossRefUpdated(payload: CrossRefUpdatedPayload) {
  const pid = projectId.value
  if (payload.projectId && payload.projectId !== pid) return
  // 仅当目标 wp_code 匹配当前底稿时刷新
  const currentWpCode = wpDetail.value?.wp_code
  if (payload.targetWpCode && currentWpCode && payload.targetWpCode !== currentWpCode) return
  // 刷新 sheet 分组 + 重新触发 prefill
  sheetNav.refresh()
  onRefreshPrefill()
}

/**
 * H-F8: SSE → cross-ref:updated 映射
 * 当后端发布 CROSS_REF_UPDATED 事件（如 H9→H8 租赁回填），
 * 将 SSE payload 转换为 cross-ref:updated eventBus 事件
 */
function onSSECrossRefUpdated(payload: SyncEventPayload) {
  if (!payload || (payload.event_type as string) !== 'cross_ref.updated') return
  const extra = payload.extra || {}
  eventBus.emit('cross-ref:updated', {
    projectId: payload.project_id || '',
    targetWpCode: extra.target_wp_code || '',
    sourceWpCode: extra.source_wp_code || '',
    refId: extra.ref_id || '',
  })
}

onMounted(() => {
  // 先获取 component_type 决定路由，再初始化对应编辑器
  fetchComponentType().then(() => {
    if (componentType.value === 'univer' || !componentType.value) {
      initUniver()
    }
  })
  // P0: 加载程序步骤映射
  stepMapping.loadMapping()
  // R8-S2-02：订阅 workpaper:locate-cell 事件，定位到 Univer 单元格
  eventBus.on('workpaper:locate-cell', onLocateCell)
  // F6 D 销售循环 task 2.12: 订阅 cross-ref:updated 自动刷新 D2-1
  eventBus.on('cross-ref:updated', onCrossRefUpdated)
  // H-F8: 订阅 SSE cross_ref.updated → 转发为 cross-ref:updated（H9→H8 租赁回填）
  eventBus.on('sse:sync-event', onSSECrossRefUpdated)
  // R8-S2-14：关闭浏览器/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)

  // [R9 F9 Task 30] 确认 Univer Ctrl+Z/Y 不被 shortcutManager 拦截
  // shortcutManager 已在 R9 Task 31 中移除 Ctrl+Z 和 Ctrl+Shift+Z 的注册
  // Univer 内置 UndoCommand/RedoCommand 原生处理撤销/重做，无需额外绑定
})

onUnmounted(() => {
  eventBus.off('workpaper:locate-cell', onLocateCell)
  eventBus.off('cross-ref:updated', onCrossRefUpdated)
  eventBus.off('sse:sync-event', onSSECrossRefUpdated)
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
.gt-wp-editor-univer-wrapper { flex: 1; min-width: 0; position: relative; overflow: hidden; }
.gt-wp-editor-univer { width: 100%; height: 100%; }
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
.gt-stocktake-trigger {
  padding: 6px;
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-radius: 6px;
  background: var(--gt-color-bg-white, #fff);
  text-align: center;
}
.gt-stocktake-trigger :deep(.el-button) {
  width: 100%;
}
.gt-wp-editor-loading-overlay {
  position: absolute; inset: 0; z-index: 100;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; color: var(--gt-color-text-tertiary);
  background: var(--gt-color-bg-white);
}
.gt-wp-editor-loading {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 12px; color: var(--gt-color-text-tertiary);
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
</style>
