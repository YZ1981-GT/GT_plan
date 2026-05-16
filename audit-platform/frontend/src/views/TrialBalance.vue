<template>
  <div class="gt-trial-balance gt-fade-in" :class="{ 'gt-fullscreen': tbFullscreen }">
    <!-- 顶部区域（可折叠） -->
    <div v-show="!headerCollapsed">
      <!-- 页面横幅 -->
      <GtPageHeader title="试算表" :show-sync-status="true" @back="router.push('/projects')">
        <GtInfoBar
          :show-unit="true"
          :show-year="true"
          :unit-value="selectedProjectId"
          :year-value="selectedYear"
          :badges="[
            { value: rows.length + ' 个科目' },
            { label: '单位', value: displayPrefs.unitSuffix },
            ...(lastRecalcAt ? [{ label: '数据', value: isStale ? '⚠ 待重算' : `✓ ${freshnessText}` }] : []),
            ...(isFrozen ? [{ label: '🔒', value: '已锁定' }] : []),
          ]"
          @unit-change="onProjectChange"
          @year-change="onYearChange"
        >
          <el-select
            v-if="hasMultipleCompanies"
            v-model="companyCode"
            size="small"
            style="width: 160px; margin-left: 8px"
            placeholder="选择子公司"
            @change="onCompanyChange"
          >
            <el-option
              v-for="c in companyList"
              :key="c.code"
              :label="c.name"
              :value="c.code"
            />
          </el-select>
        </GtInfoBar>
        <template #actions>
          <GtToolbar
            :show-copy="true"
            :show-fullscreen="true"
            :is-fullscreen="tbFullscreen"
            :show-export="true"
            :show-import="true"
            import-label="Excel导入"
            :show-formula="true"
            @copy="copyTbTable"
            @fullscreen="toggleTbFullscreen()"
            @export="onExport"
            @import="onToolbarImport"
            @formula="showFormulaManager = true"
          >
            <template #left>
              <el-tooltip content="检查试算表与四表数据的一致性" placement="bottom">
                <el-button size="small" @click="onConsistencyCheck" :loading="checkLoading">✅ 一致性校验</el-button>
              </el-tooltip>
              <el-tooltip content="执行数据质量检查（借贷平衡/余额一致性/映射完整性）" placement="bottom">
                <el-button size="small" @click="showDataQualityDialog = true">🔍 数据质量检查</el-button>
              </el-tooltip>
              <el-tooltip :content="isFrozen ? '试算表已锁定，解锁后才能重算' : '从四表数据重新计算未审数、调整数、审定数（需先导入数据）'" placement="bottom">
                <el-button size="small" @click="onRecalc" :loading="recalcLoading" :disabled="isFrozen">🔄 全量重算</el-button>
              </el-tooltip>
              <el-tooltip :content="isFrozen ? '点击解锁试算表' : '锁定试算表，防止自动重算'" placement="bottom">
                <el-button size="small" @click="toggleFreeze" :type="isFrozen ? 'danger' : 'default'">
                  {{ isFrozen ? '🔒' : '🔓' }}
                </el-button>
              </el-tooltip>
            </template>
          </GtToolbar>
        </template>
      </GtPageHeader>

      <!-- 在线成员 [enterprise-linkage 3.2] -->
      <PresenceAvatars :project-id="projectId" view-name="trial_balance" />

      <!-- 工作流进度条 -->
      <WorkflowProgress :project-id="projectId" :year="selectedYear" @step-action="onWorkflowAction" />
    </div>

    <!-- 折叠/展开按钮 -->
    <div class="gt-header-toggle" @click="headerCollapsed = !headerCollapsed">
      <span>{{ headerCollapsed ? '▼ 展开工具栏' : '▲ 收起工具栏' }}</span>
    </div>

    <!-- 视图切换：科目明细 / 试算平衡表 / 映射规则 -->
    <div style="display:flex;gap:0;margin-bottom:8px;border-bottom:2px solid #f0edf5;align-items:center">
      <el-tooltip placement="bottom" :show-after="500">
        <template #content>
          <div style="max-width: 280px; line-height: 1.6">
            <b>科目明细</b><br>
            按科目编码逐行展示期初、AJE调整、RJE重分类、审定数。<br>
            <span style="color: #e6a23c">适用：逐科目核对数据、录入调整分录</span>
          </div>
        </template>
        <span class="gt-tb-view-tag" :class="{ 'gt-tb-view-tag--active': tbViewMode === 'detail' }" @click="tbViewMode = 'detail'">科目明细</span>
      </el-tooltip>
      <el-tooltip placement="bottom" :show-after="500">
        <template #content>
          <div style="max-width: 280px; line-height: 1.6">
            <b>试算平衡表</b><br>
            按报表行次（资产负债表/利润表）汇总展示，对应审计报告附表格式。<br>
            <span style="color: #e6a23c">适用：出具报表前核对借贷平衡、查看审定后报表数</span>
          </div>
        </template>
        <span class="gt-tb-view-tag" :class="{ 'gt-tb-view-tag--active': tbViewMode === 'summary' }" @click="tbViewMode = 'summary'; loadTbSummary()">试算平衡表</span>
      </el-tooltip>
      <el-tooltip content="查看/编辑科目明细与试算平衡表的对应关系（映射规则）" placement="bottom">
        <el-button size="small" class="gt-mapping-rule-btn" @click="showMappingDialog = true">
          🔗 映射规则
        </el-button>
      </el-tooltip>
      <!-- 试算平衡表工具栏（刷新/导出/保存/导入）移到此处节省垂直空间 -->
      <template v-if="tbViewMode === 'summary'">
        <span style="flex:1" />
        <el-button size="small" @click="loadTbSummary()" :loading="tbSummaryLoading">🔄 刷新</el-button>
        <el-dropdown size="small" trigger="click" @command="onTbSumExportCmd">
          <el-button size="small">📤 导出 <el-icon style="margin-left:4px"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="data">导出数据（含金额）</el-dropdown-item>
              <el-dropdown-item command="template">导出空模板（供填写）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="triggerTbSumImport">📥 导入</el-button>
        <input ref="tbSumImportInput" type="file" accept=".xlsx,.xls" style="display:none" @change="onTbSumImportFile" />
        <el-button size="small" @click="saveTbSummary">💾 保存</el-button>
        <span style="font-size:11px;color:#999;margin-left:12px">{{ tbSummaryRows.length }} 行</span>
      </template>
    </div>

    <!-- 映射规则弹窗 -->
    <ReportLineMappingDialog v-model="showMappingDialog" :project-id="projectId" :account-rows="rows" />

    <!-- 一致性校验结果 -->
    <el-alert
      v-if="consistencyResult"
      :type="consistencyResult.consistent ? 'success' : 'warning'"
      :title="consistencyResult.consistent ? '一致性校验通过：试算表与四表数据一致' : `发现 ${consistencyResult.issues.length} 项不一致`"
      :closable="true"
      show-icon
      style="margin-bottom: 12px"
    >
      <div v-if="!consistencyResult.consistent && consistencyResult.issues.length > 0" style="font-size: 12px; line-height: 1.8; margin-top: 4px">
        <div v-for="(issue, idx) in consistencyResult.issues.slice(0, 5)" :key="idx" style="padding: 2px 0">
          · {{ (issue as any).message || (issue as any).description || JSON.stringify(issue) }}
        </div>
        <div v-if="consistencyResult.issues.length > 5" style="color: #909399; margin-top: 4px">
          还有 {{ consistencyResult.issues.length - 5 }} 项未显示
        </div>
      </div>
    </el-alert>

    <!-- 数据新鲜度提示（有未重算的调整分录时） -->
    <div v-if="isStale && rows.length > 0" class="gt-stale-banner">
      <span class="gt-stale-icon">⚠️</span>
      <span class="gt-stale-text">
        {{ isFrozen ? '试算表已锁定，不会自动重算' : '数据已过期，请刷新（检测到新调整分录）' }}
      </span>
      <el-button v-if="!isFrozen" size="small" type="primary" :loading="recalcLoading" @click="onRecalc">
        立即刷新
      </el-button>
      <div v-if="latestAdjustmentAt" style="font-size: 11px; color: #909399; margin-left: 12px">
        最新调整：{{ new Date(latestAdjustmentAt).toLocaleString('zh-CN') }}
      </div>
    </div>

    <!-- 空数据引导：只在 setup-guide 前简要说明（不重复步骤） -->
    <el-alert
      v-if="!loading && rows.length === 0 && !dataState.hasBalance"
      type="info"
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>
        <span>试算表暂无数据 — 请按下方步骤操作</span>
      </template>
    </el-alert>

    <!-- 步骤引导（空数据时显示） -->
    <div v-if="showSetupGuide" class="gt-setup-guide">
      <el-steps :active="setupCurrentStep" finish-status="success" align-center>
        <el-step title="数据导入" description="上传科目余额表+序时账" :status="setupStepStatus[0]" />
        <el-step title="科目映射" description="从余额表一级科目自动匹配" :status="setupStepStatus[1]" />
        <el-step title="生成试算表" description="汇总计算审定数" :status="setupStepStatus[2]" />
      </el-steps>
      <div style="margin-top: 16px; text-align: center">
        <el-button v-if="setupCurrentStep === 0" type="primary" @click="tbImportVisible = true">
          一键导入数据
        </el-button>
        <el-button v-else-if="setupCurrentStep === 1" type="primary" @click="onAutoMapping" :loading="autoMappingLoading">
          自动匹配科目分类
        </el-button>
        <el-button v-else-if="setupCurrentStep === 2" type="primary" @click="onRecalc">
          生成试算表
        </el-button>
        <div v-if="setupCurrentStep === 1" style="margin-top: 8px; font-size: 12px; color: #909399">
          系统将从已导入的余额表中读取一级科目，按编码规则自动匹配到标准分类（1xxx=资产、2xxx=负债...）
        </div>
      </div>
    </div>

    <!-- 数据源选择弹窗（智能判断：有数据→确认使用，无数据→引导导入） -->
    <el-dialog v-model="tbImportVisible" title="选择数据源" width="520" append-to-body destroy-on-close>
      <div v-loading="checkingData">
        <!-- 已有数据：显示概要，确认使用 -->
        <div v-if="existingDataSummary">
          <el-alert type="success" :closable="false" show-icon style="margin-bottom: 16px">
            <template #title>当前项目已有账套数据</template>
          </el-alert>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="年度">{{ existingDataSummary.year }}</el-descriptions-item>
            <el-descriptions-item label="科目数">{{ existingDataSummary.balance_count }} 个</el-descriptions-item>
            <el-descriptions-item label="序时账">{{ existingDataSummary.ledger_count?.toLocaleString() || 0 }} 条</el-descriptions-item>
            <el-descriptions-item label="数据单位">{{ existingDataSummary.amount_unit || '元' }}</el-descriptions-item>
          </el-descriptions>
          <div style="margin-top: 16px; text-align: center">
            <el-button type="primary" @click="onUseExistingData">
              使用此数据生成试算表
            </el-button>
          </div>
          <div style="margin-top: 12px; text-align: center">
            <el-button text size="small" @click="goToLedgerImport">
              重新导入（覆盖现有数据）→
            </el-button>
          </div>
        </div>

        <!-- 无数据：引导去导入 -->
        <div v-else-if="!checkingData">
          <el-empty description="当前项目暂无账套数据" :image-size="80">
            <div style="font-size: 13px; color: #909399; margin-bottom: 12px">
              请先在「查账」页面导入科目余额表和序时账
            </div>
            <el-button type="primary" @click="goToLedgerImport">
              前往导入账套数据
            </el-button>
          </el-empty>
        </div>
      </div>
    </el-dialog>

    <!-- 搜索栏（Ctrl+F 触发，表格上方） -->
    <TableSearchBar
      :is-visible="tbSearch.isVisible.value"
      :keyword="tbSearch.keyword.value"
      :match-info="tbSearch.matchInfo.value"
      :has-matches="tbSearch.matches.value.length > 0"
      :case-sensitive="tbSearch.caseSensitive.value"
      :show-replace="false"
      @update:keyword="tbSearch.keyword.value = $event"
      @update:case-sensitive="tbSearch.caseSensitive.value = $event"
      @search="tbSearch.search()"
      @next="tbSearch.nextMatch()"
      @prev="tbSearch.prevMatch()"
      @close="tbSearch.close()"
    />

    <!-- 试算表主表（科目明细视图） -->
    <div v-if="tbViewMode === 'detail' && staleAccountCodes.size > 0" style="margin-bottom: 6px; font-size: 12px; color: #909399; display: flex; align-items: center; gap: 6px">
      <span style="display: inline-block; width: 14px; height: 14px; background: #fef9e7; border-left: 3px solid #f0c040; border-radius: 2px"></span>
      <span>黄底行 = 有新调整分录待重算</span>
    </div>
    <el-table
      ref="tbTableRef"
      v-if="tbViewMode === 'detail'"
      :data="groupedRows"
      v-loading="loading"
      border
      stripe
      :max-height="tableMaxHeight"
      style="width: 100%"
      :class="`gt-tb-font-${displayPrefs.fontSize}`"
      :row-class-name="rowClassName"
      :cell-class-name="tbCellClassName"
      @cell-click="onTbCellClick"
      @cell-dblclick="onTbCellDblClick"
      @cell-contextmenu="onTbCellContextMenu"
    >
      <el-table-column prop="standard_account_code" label="科目编码" width="130" class-name="gt-amt-col">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && getLinkedWp(row.standard_account_code)"
            class="clickable" @click="onOpenWorkpaper(row.standard_account_code)"
            :title="'打开底稿 ' + getLinkedWp(row.standard_account_code)?.wp_name">
            {{ row.standard_account_code }}
            <el-icon style="margin-left:2px; font-size:11px; vertical-align:middle"><Link /></el-icon>
          </span>
          <span v-else>{{ row.standard_account_code }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="account_name" label="科目名称" min-width="180" />
      <el-table-column label="方向" width="80" align="center" :header-cell-style="{ whiteSpace: 'nowrap' }">
        <template #default="{ row }">
          <span
            v-if="!row._isSubtotal && !row._isTotal"
            :class="getDirectionClass(row)"
            class="gt-dir-toggle"
            @click="toggleDirection(row)"
            :title="'点击切换借贷方向'"
          >
            {{ getDirection(row) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="未审数" width="160" align="right" class-name="gt-amt-col">
        <template #default="{ row, $index }">
          <CommentTooltip :comment="tbComments.getComment('trial_balance', $index, 2)">
          <span v-if="!row._isSubtotal && !row._isTotal"
            class="clickable gt-amt" @click="onUnadjustedClick(row)"
            :class="displayPrefs.amountClass(row.unadjusted_amount)">
            {{ fmtDir(row, 'unadjusted_amount') }}
          </span>
          <span v-else class="subtotal-val gt-amt" :class="displayPrefs.amountClass(row.unadjusted_amount)">{{ fmtDir(row, 'unadjusted_amount') }}</span>
          </CommentTooltip>
        </template>
      </el-table-column>
      <el-table-column label="RJE调整" width="150" align="right" class-name="gt-amt-col">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && row.rje_adjustment !== '0'"
            class="clickable gt-amt" @click="onAdjClick(row, 'rje')">
            {{ fmt(row.rje_adjustment) }}
          </span>
          <span v-else class="gt-amt" :class="{ 'subtotal-val': row._isSubtotal || row._isTotal }">
            {{ fmt(row.rje_adjustment) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="AJE调整" width="150" align="right" class-name="gt-amt-col">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal && row.aje_adjustment !== '0'"
            class="clickable gt-amt" @click="onAdjClick(row, 'aje')">
            {{ fmt(row.aje_adjustment) }}
          </span>
          <span v-else class="gt-amt" :class="{ 'subtotal-val': row._isSubtotal || row._isTotal }">
            {{ fmt(row.aje_adjustment) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="联动" width="100" align="center">
        <template #default="{ row }">
          <LinkageBadge v-if="row.row_code" :count="getAdjustments(row.row_code).length" type="adjustment" />
        </template>
      </el-table-column>
      <el-table-column label="审定数" width="160" align="right" class-name="gt-amt-col">
        <template #default="{ row, $index }">
          <CommentTooltip :comment="tbComments.getComment('trial_balance', $index, 5)">
          <span :class="['subtotal-val', 'gt-amt', displayPrefs.amountClass(row.audited_amount)]" v-if="row._isSubtotal || row._isTotal">
            {{ fmtDir(row, 'audited_amount') }}
          </span>
          <span v-else :class="['gt-amt', displayPrefs.amountClass(row.audited_amount)]">
            {{ fmtDir(row, 'audited_amount') }}
          </span>
          </CommentTooltip>
        </template>
      </el-table-column>
      <el-table-column label="底稿状态" width="120" align="center" :header-cell-style="{ whiteSpace: 'nowrap' }">
        <template #default="{ row }">
          <el-tooltip v-if="row.wp_consistency?.status === 'consistent'" content="底稿审定数一致" placement="top">
            <span style="color: #28a745; cursor: pointer" @dblclick="openWorkpaper(row)">✅</span>
          </el-tooltip>
          <el-tooltip v-else-if="row.wp_consistency?.status === 'stale'" content="上游数据已变更，点击重算">
            <span style="color: var(--gt-color-teal, #009688); cursor: pointer" @click="onRecalcWp(row)">🔄</span>
          </el-tooltip>
          <el-tooltip v-else-if="row.wp_consistency?.status === 'inconsistent'" :content="`差异 ${row.wp_consistency.diff_amount}`" placement="top">
            <span style="color: #FF5149; cursor: pointer" @dblclick="openWorkpaper(row)">⚠️</span>
          </el-tooltip>
          <span v-else style="color: #ccc">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 试算平衡表视图（报表行次级别） -->
    <div v-if="tbViewMode === 'summary'">
      <!-- 期初/期末切换 -->
      <div style="display:flex;gap:12px;margin-bottom:8px;align-items:center">
        <el-radio-group v-model="tbSumPeriod" size="small" @change="loadTbSummary()">
          <el-radio-button value="ending">期末试算</el-radio-button>
          <el-radio-button value="opening">期初试算</el-radio-button>
        </el-radio-group>
        <span v-if="tbSumPeriod === 'opening'" style="font-size:11px;color:#e6a23c">
          {{ tbSumOpeningSource === 'prior_year' ? '📎 数据来源：上年审定数' : '✏️ 首次承接：手动填写' }}
        </span>
      </div>
      <!-- 报表类型切换 -->
      <div style="display:flex;gap:0;margin-bottom:8px;border-bottom:2px solid #f0edf5">
        <span v-for="rt in tbSummaryTypes" :key="rt.key"
          class="gt-tb-view-tag" :class="{ 'gt-tb-view-tag--active': tbSummaryType === rt.key }"
          @click="tbSummaryType = rt.key; loadTbSummary()">{{ rt.label }}</span>
        <!-- 编辑模式切换按钮 -->
        <el-button
          size="small"
          :type="tbSumEditMode ? 'primary' : 'default'"
          style="margin-left:16px"
          @click="tbSumEditMode = !tbSumEditMode"
        >{{ tbSumEditMode ? '✏️ 编辑中' : '✏️ 编辑' }}</el-button>
        <span style="flex:1" />
        <span style="font-size:11px;color:#999;align-self:center">审计调整从调整分录自动汇总 · 审定数=未审数+调整借-贷+重分类借-贷</span>
      </div>
      <div :class="`gt-tb-font-${displayPrefs.fontSize}`">
        <el-table
          ref="tbSummaryTableRef"
          :data="tbSummaryRows"
          border
          :max-height="tbSummaryMaxHeight"
          style="width: 100%"
          :row-class-name="tbSumRowClassName"
          :cell-class-name="tbSumCellClassName"
          :cell-style="{ padding: '4px 8px' }"
          highlight-current-row
          @cell-click="onTbSumCellClick"
          @row-contextmenu="onTbSumElContextMenu"
          @row-dblclick="onTbSumElDblClick"
        >
          <el-table-column prop="row_code" label="行次" width="110" align="center">
            <template #default="{ row }">
              <span style="color:#999;font-size:11px;white-space:nowrap">{{ row.row_code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="row_name" label="项目" min-width="200">
            <template #default="{ row }">
              <span :style="{ paddingLeft: (row.indent || 0) * 14 + 'px' }">{{ row.row_name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="unadjusted" label="未审数" width="140" align="right" class-name="gt-tb-sum-unadj-col">
            <template #default="{ row, $index }">
              <template v-if="tbSumUnadjEditable || row.formula_detached">
                <el-input-number
                  v-if="tbSumLazyEdit.isEditing($index, 0)"
                  v-model="row.unadjusted"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @blur="tbSumLazyEdit.stopEdit(); recalcTbSummaryAudited()"
                  autofocus
                />
                <span v-else class="gt-tb-editable gt-amt" @click="tbSumLazyEdit.startEdit($index, 0)">
                  <span v-if="row.formula_detached" class="gt-tb-detached-icon" title="已断开公式（手动值）">✂️</span>
                  {{ fmt(row.unadjusted) }}
                </span>
              </template>
              <span v-else class="gt-amt">{{ fmt(row.unadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审计调整" header-align="center">
            <el-table-column prop="aje_dr" label="借方" width="120" align="right">
              <template #default="{ row }">
                <span class="gt-tb-readonly gt-amt">{{ fmt(row.aje_dr) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="aje_cr" label="贷方" width="120" align="right">
              <template #default="{ row }">
                <span class="gt-tb-readonly gt-amt">{{ fmt(row.aje_cr) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="重分类调整" header-align="center">
            <el-table-column prop="rcl_dr" label="借方" width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number
                  v-if="tbSumLazyEdit.isEditing($index, 2)"
                  v-model="row.rcl_dr"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @blur="tbSumLazyEdit.stopEdit(); recalcTbSummaryAudited()"
                  autofocus
                />
                <span v-else class="gt-tb-editable gt-amt" @click="tbSumLazyEdit.startEdit($index, 2)">{{ fmt(row.rcl_dr) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="rcl_cr" label="贷方" width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number
                  v-if="tbSumLazyEdit.isEditing($index, 3)"
                  v-model="row.rcl_cr"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @blur="tbSumLazyEdit.stopEdit(); recalcTbSummaryAudited()"
                  autofocus
                />
                <span v-else class="gt-tb-editable gt-amt" @click="tbSumLazyEdit.startEdit($index, 3)">{{ fmt(row.rcl_cr) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column prop="audited" label="审定数" width="140" align="right" class-name="gt-tb-sum-audited-col">
            <template #default="{ row }">
              <span class="gt-amt" style="font-weight:700;color:#4b2d77">{{ fmt(row.audited) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 试算平衡表右键菜单 -->
      <div v-if="tbSumCtxVisible" class="gt-tb-sum-ctx" :style="{ left: tbSumCtxX + 'px', top: tbSumCtxY + 'px' }" @contextmenu.prevent>
        <div class="gt-ucell-ctx-item" @click="onTbSumCtxCopy">
          <span class="gt-ucell-ctx-icon">📋</span> {{ tbSumSelectedRows.size > 1 ? `复制选中 (${tbSumSelectedRows.size}行)` : '复制值' }}
        </div>
        <div class="gt-ucell-ctx-item" @click="onTbSumCtxFormula"><span class="gt-ucell-ctx-icon">ƒx</span> 查看公式</div>
        <div class="gt-ucell-ctx-item" @click="onTbSumCtxDetail"><span class="gt-ucell-ctx-icon">📊</span> 汇总明细</div>
        <div class="gt-ucell-ctx-item" @click="onTbSumCtxTrace"><span class="gt-ucell-ctx-icon">🔍</span> 数据溯源</div>
        <div class="gt-ucell-ctx-divider"></div>
        <div v-if="tbSumCtxRow?.formula_detached" class="gt-ucell-ctx-item" @click="onTbSumCtxRestoreFormula">
          <span class="gt-ucell-ctx-icon">🔗</span> 恢复公式
        </div>
        <div v-else class="gt-ucell-ctx-item" @click="onTbSumCtxDetachFormula">
          <span class="gt-ucell-ctx-icon">✂️</span> 断开公式（手动填写）
        </div>
      </div>

      <el-empty v-if="!tbSummaryRows.length && !tbSummaryLoading" description="点击刷新从科目明细汇总生成" />
    </div>

    <!-- 选中区域状态栏 -->
    <SelectionBar :stats="tbViewMode === 'summary' ? tbSumCtx.selectionStats() : tbCtx.selectionStats()" />

    <!-- 借贷平衡指示器 -->
    <div class="gt-tb-balance-indicator" v-if="!loading">
      <el-tooltip
        :content="isBalanced ? '资产小计 = 负债和权益合计' : `差额：${fmt(Math.abs(balanceDiff))} 元（资产 - 负债权益）`"
        placement="top"
      >
        <span :class="isBalanced ? 'gt-tb-balanced' : 'gt-tb-unbalanced'">
          {{ isBalanced ? '✓ 借贷平衡' : '✗ 借贷不平衡' }}
        </span>
      </el-tooltip>
    </div>

    <!-- 调整分录明细弹窗 -->
    <el-dialog append-to-body v-model="adjDialogVisible" :title="`${adjDialogType} 调整明细 — ${adjDialogAccount}`" width="700px">
      <el-table :data="adjDialogList" border stripe>
        <el-table-column prop="adjustment_no" label="编号" width="120" />
        <el-table-column prop="description" label="摘要" min-width="180" />
        <el-table-column prop="total_debit" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.total_debit) }}</template>
        </el-table-column>
        <el-table-column prop="total_credit" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmt(row.total_credit) }}</template>
        </el-table-column>
        <el-table-column prop="review_status" label="状态" width="100">
          <template #default="{ row }">
            <GtStatusTag dict-key="adjustment_status" :value="row.review_status" />
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 映射质量面板（Task 1） -->
    <el-dialog v-model="mappingResultVisible" title="科目映射结果" width="460" append-to-body destroy-on-close>
      <div style="display: flex; flex-direction: column; gap: 16px; padding: 8px 0">
        <div style="display: flex; align-items: center; gap: 12px">
          <el-badge :value="mappingResult.matched" type="success" />
          <span style="font-size: 14px">匹配成功</span>
        </div>
        <div style="display: flex; align-items: center; gap: 12px">
          <el-badge :value="mappingResult.needConfirm" type="warning" />
          <span style="font-size: 14px">需手动确认</span>
        </div>
        <div style="font-size: 12px; color: #909399; margin-top: 4px">
          共 {{ mappingResult.total }} 个客户科目，完成率 {{ mappingResult.rate }}%
        </div>
        <el-alert v-if="mappingResult.needConfirm > 0" type="info" :closable="false" show-icon style="margin-top: 8px">
          <template #title>{{ mappingResult.needConfirm }} 个科目未能自动匹配，建议手动确认</template>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="mappingResultVisible = false">关闭</el-button>
        <el-button type="primary" @click="goToMappingEditor">查看映射详情</el-button>
      </template>
    </el-dialog>

    <!-- 公式管理弹窗 -->
    <FormulaManagerDialog
      v-model="showFormulaManager"
      :rows="rows"
      :project-id="projectId"
      :year="year"
      @applied="fetchData"
    />

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showTbImport"
      import-type="trial_balance"
      :project-id="projectId"
      :year="year"
      @imported="onTbImported"
    />
  </div>

  <!-- 右键菜单（统一组件） -->
  <CellContextMenu
    :visible="tbCtx.contextMenu.visible"
    :x="tbCtx.contextMenu.x"
    :y="tbCtx.contextMenu.y"
    :item-name="tbCtx.contextMenu.itemName"
    :value="tbCtx.selectedCells.value.length === 1 ? tbCtx.selectedCells.value[0]?.value : undefined"
    :multi-count="tbCtx.selectedCells.value.length"
    @copy="onTbCtxCopy"
    @formula="onTbCtxFormula"
    @sum="onTbCtxSum"
    @compare="onTbCtxCompare"
  >
    <div class="gt-ucell-ctx-item" @click="onTbCtxDrillDown"><span class="gt-ucell-ctx-icon">📊</span> 查看明细</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxTrace"><span class="gt-ucell-ctx-icon">🔍</span> 数据溯源</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxOpenWp"><span class="gt-ucell-ctx-icon">📝</span> 打开底稿</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxViewAdj"><span class="gt-ucell-ctx-icon">📋</span> 查看调整分录</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxViewLinkedWp"><span class="gt-ucell-ctx-icon">🔗</span> 查看关联底稿</div>
  </CellContextMenu>

  <DataQualityDialog
    v-model="showDataQualityDialog"
    :project-id="projectId"
    :year="year"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Link, ArrowDown } from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useLazyEdit } from '@/composables/useLazyEdit'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { fmtAmount } from '@/utils/formatters'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WorkflowProgress from '@/components/common/WorkflowProgress.vue'
import PresenceAvatars from '@/components/PresenceAvatars.vue'
import { api } from '@/services/apiProxy'
import { eventBus, type WorkpaperParsedPayload, type MaterialityChangedPayload } from '@/utils/eventBus'
import {
  getTrialBalance, recalcTrialBalance, checkConsistency,
  getProjectAuditYear, listAdjustments,
  type TrialBalanceRow, type ConsistencyResult,
} from '@/services/auditPlatformApi'
import { getAllWpMappings, listWorkpapers, type WpAccountMapping, type WorkpaperDetail } from '@/services/workpaperApi'
import { useProjectStore } from '@/stores/project'
import { setupPasteListener, pasteToSelection } from '@/composables/useCopyPaste'
import { withLoading } from '@/composables/useLoading'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import DataQualityDialog from '@/components/DataQualityDialog.vue'
import ReportLineMappingDialog from '@/components/trial-balance/ReportLineMappingDialog.vue'
import { handleApiError } from '@/utils/errorHandler'
import { usePenetrate } from '@/composables/usePenetrate'
import { useProjectEvents } from '@/composables/useProjectEvents'
import { usePasteImport } from '@/composables/usePasteImport'
import { usePermission } from '@/composables/usePermission'
import * as P from '@/services/apiPaths'
import LinkageBadge from '@/components/LinkageBadge.vue'
import { useLinkageIndicator } from '@/composables/useLinkageIndicator'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.projectId || (route.params.projectId as string) || '')
const selectedProjectId = ref(projectStore.projectId)
const projectOptions = computed(() => projectStore.projectOptions)
const selectedYear = ref(projectStore.year)
const yearOptions = computed(() => projectStore.yearOptions)

// ─── 云协同：账套激活/回滚后自动刷新 ─────────────────────────────────────────
const { onDatasetActivated, onDatasetRolledBack } = useProjectEvents(projectId)
onDatasetActivated(() => fetchData())
onDatasetRolledBack(() => fetchData())

// ─── 联动徽章 [enterprise-linkage 3.6] ─────────────────────────────────────────
const linkageProjectId = projectId
const linkageYear = computed(() => selectedYear.value ?? 2025)
const { getAdjustments, getWorkpapers } = useLinkageIndicator(linkageProjectId, linkageYear)

function onProjectChange(pid: string) {
  router.push({
    path: `/projects/${pid}/trial-balance`,
    query: { year: String(selectedYear.value) },
  })
}

function onYearChange(y: number) {
  selectedYear.value = y
  projectStore.changeYear(y)
  router.push({
    path: `/projects/${projectId.value}/trial-balance`,
    query: { year: String(y) },
  })
}

const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

/**
 * 方向感知格式化：
 * - 负债/权益/收入类科目：原始负数取绝对值展示为正数（方向列标"贷"）
 * - 资产类中的备抵科目：保持负数展示（红字），方向列标"贷"，表示是资产减项
 *   这样资产小计 = 各行数字直接相加即可验证
 * - 小计行：直接展示（资产小计已是净额正数，负债小计原始负数取绝对值）
 */
function fmtDir(row: any, field: string) {
  const val = Number(row[field] || 0)
  if (val === 0) return fmt(0)
  // 小计行/合计行：直接展示（已经按方向计算好了）
  // 净利润行：正数=盈利，负数=亏损，直接展示不取绝对值
  if (row._isSubtotal || row._isTotal) return fmt(val)
  // 普通行：取绝对值展示
  return fmt(Math.abs(val))
}

// ─── 科目余额方向判断 ───────────────────────────────────────────────────────
// 用户手动覆盖的方向存储（科目编码 → '借'|'贷'）
const directionOverrides = ref<Record<string, '借' | '贷'>>({})

// 判断科目余额方向：优先用户手动设置 > 数据推断
function getDirection(row: any): string {
  if (!row.standard_account_code && !row.account_category) return ''
  const code = row.standard_account_code || ''
  const cat = row.account_category || ''

  // 小计行/合计行：根据 account_category 判断
  if (!code && cat) {
    if (['liability', 'equity', 'revenue'].includes(cat)) return '贷'
    return '借'
  }

  // 优先使用用户手动设置的方向
  if (code && directionOverrides.value[code]) {
    return directionOverrides.value[code]
  }

  // 默认推断：根据余额正负判断（正数=借方余额，负数=贷方余额）
  const val = Number(row.unadjusted_amount || 0)
  if (val < 0) return '贷'
  return '借'
}

function getDirectionClass(row: any): string {
  const dir = getDirection(row)
  return dir === '贷' ? 'gt-dir-credit' : 'gt-dir-debit'
}

// 用户点击方向列切换借贷
function toggleDirection(row: any) {
  const code = row.standard_account_code
  if (!code) return
  const current = getDirection(row)
  directionOverrides.value[code] = current === '借' ? '贷' : '借'
}

// ─── Task 3: Multi-Company Switcher ─────────────────────────────────────────
const companyCode = ref('001')
const companyList = ref<{ code: string; name: string }[]>([])
const hasMultipleCompanies = computed(() => companyList.value.length > 1)

async function loadCompanyList() {
  try {
    const result = await api.get(`/api/projects/${projectId.value}/child-companies`)
    if (Array.isArray(result) && result.length > 0) {
      companyList.value = result.map((c: any) => ({
        code: c.company_code || c.code || '001',
        name: c.company_name || c.name || c.company_code || '默认',
      }))
    } else {
      companyList.value = []
    }
  } catch {
    companyList.value = []
  }
}

function onCompanyChange(code: string) {
  companyCode.value = code
  fetchData()
}

// ─── Task 4: Trial Balance Freeze Mechanism ─────────────────────────────────
const { can } = usePermission()
const isFrozen = ref(false)
const canToggleFreeze = computed(() => can('admin') || can('project:edit'))

function getFreezeKey() {
  return `tb_frozen_${projectId.value}_${year.value}`
}

function loadFreezeState() {
  try {
    isFrozen.value = localStorage.getItem(getFreezeKey()) === '1'
  } catch {
    isFrozen.value = false
  }
}

function toggleFreeze() {
  if (!canToggleFreeze.value) {
    ElMessage.warning('仅管理员/合伙人/项目经理可操作锁定')
    return
  }
  isFrozen.value = !isFrozen.value
  try {
    if (isFrozen.value) {
      localStorage.setItem(getFreezeKey(), '1')
    } else {
      localStorage.removeItem(getFreezeKey())
    }
  } catch { /* ignore */ }
  ElMessage.success(isFrozen.value ? '试算表已锁定' : '试算表已解锁')
}

const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear())

const loading = ref(false)
const showTbImport = ref(false)
const showDataQualityDialog = ref(false)
const showMappingDialog = ref(false)
const headerCollapsed = ref(false)
const recalcLoading = ref(false)
const checkLoading = ref(false)
const showFormulaManager = ref(false)
const rows = ref<TrialBalanceRow[]>([])
const consistencyResult = ref<ConsistencyResult | null>(null)

// 调整明细弹窗
const adjDialogVisible = ref(false)
const adjDialogType = ref('')
const adjDialogAccount = ref('')
const adjDialogList = ref<any[]>([])

// 底稿-科目映射
const wpMappings = ref<WpAccountMapping[]>([])
const wpMappingIndex = ref<Record<string, WpAccountMapping>>({})
// 已生成的底稿列表（用于直接跳转编辑器）
const wpList = ref<WorkpaperDetail[]>([])

function getLinkedWp(accountCode: string): WpAccountMapping | undefined {
  return wpMappingIndex.value[accountCode]
}

function onOpenWorkpaper(accountCode: string) {
  const mapping = getLinkedWp(accountCode)
  if (!mapping) {
    ElMessage.info('该科目未关联底稿')
    return
  }
  // 直接跳转到底稿编辑器
  const wp = wpList.value.find(w => w.wp_code === mapping.wp_code)
  if (wp) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: wp.id } })
  } else {
    ElMessage.info(`底稿 ${mapping.wp_code}（${mapping.wp_name}）尚未生成，请先点击"生成底稿"`)
  }
}

const CATEGORY_ORDER = ['asset', 'liability', 'equity']
const INCOME_EXPENSE_CATS = ['revenue', 'cost', 'expense']
const CATEGORY_LABELS: Record<string, string> = {
  asset: '资产', liability: '负债', equity: '权益',
  revenue: '收入', cost: '成本', expense: '费用',
}

interface DisplayRow extends TrialBalanceRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
  _highlight?: boolean
}

// 辅助函数：判断科目实际分类（双保险，编码+名称）
function getActualCat(r: any): string {
  const code = r.standard_account_code || ''
  const first = code.charAt(0)
  const name = (r.account_name || '').replace(/_/g, '')
  const dbCat = r.account_category || 'asset'
  let actualCat = dbCat

  if ((first === '3' || first === '4') && (
    name.includes('资本') || name.includes('公积') || name.includes('利润') ||
    name.includes('股本') || name.includes('权益') || name.includes('储备') ||
    name.includes('库存股') || name.includes('盈余')
  )) {
    actualCat = 'equity'
  } else if (first === '2' && (
    name.includes('借款') || name.includes('应付') || name.includes('预收') ||
    name.includes('负债') || name.includes('应交') || name.includes('递延')
  )) {
    actualCat = 'liability'
  }
  return actualCat
}

const groupedRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = []
  // 用于"负债和权益合计"
  const liabEquitySub = { unadjusted: 0, rje: 0, aje: 0, audited: 0 }

  // ── 第一部分：资产 / 负债 / 权益 ──
  for (const cat of CATEGORY_ORDER) {
    const catRows = rows.value.filter(r => getActualCat(r) === cat)
    if (!catRows.length) continue

    const sub = { unadjusted: 0, rje: 0, aje: 0, audited: 0 }
    for (const r of catRows) {
      const u = num(r.unadjusted_amount)
      const rj = num(r.rje_adjustment)
      const aj = num(r.aje_adjustment)
      const au = num(r.audited_amount)

      const dir = getDirection(r)
      const catIsDebit = cat === 'asset'
      const sign = (catIsDebit && dir === '贷') || (!catIsDebit && dir === '借') ? -1 : 1

      sub.unadjusted += Math.abs(u) * sign
      sub.rje += rj
      sub.aje += aj
      sub.audited += Math.abs(au) * sign

      result.push({ ...r, _highlight: r.exceeds_materiality })
    }

    // 小计行
    result.push({
      standard_account_code: '',
      account_name: `${CATEGORY_LABELS[cat] || cat} 小计`,
      account_category: cat,
      unadjusted_amount: String(sub.unadjusted),
      rje_adjustment: String(sub.rje),
      aje_adjustment: String(sub.aje),
      audited_amount: String(sub.audited),
      opening_balance: null,
      exceeds_materiality: false,
      below_trivial: false,
      _isSubtotal: true,
    } as DisplayRow)

    // 累加负债+权益合计
    if (cat === 'liability' || cat === 'equity') {
      liabEquitySub.unadjusted += sub.unadjusted
      liabEquitySub.rje += sub.rje
      liabEquitySub.aje += sub.aje
      liabEquitySub.audited += sub.audited
    }

    // 在权益小计后插入"负债和权益合计"
    if (cat === 'equity') {
      result.push({
        standard_account_code: '',
        account_name: '负债和权益合计',
        account_category: 'equity',
        unadjusted_amount: String(liabEquitySub.unadjusted),
        rje_adjustment: String(liabEquitySub.rje),
        aje_adjustment: String(liabEquitySub.aje),
        audited_amount: String(liabEquitySub.audited),
        opening_balance: null,
        exceeds_materiality: false,
        below_trivial: false,
        _isTotal: true,
      } as DisplayRow)
    }
  }

  // ── 第二部分：损益类（收入 - 成本 - 费用 = 净利润） ──
  const incomeExpenseRows = rows.value.filter(r => INCOME_EXPENSE_CATS.includes(getActualCat(r)))
  if (incomeExpenseRows.length) {
    const netProfit = { unadjusted: 0, rje: 0, aje: 0, audited: 0 }

    for (const r of incomeExpenseRows) {
      const u = num(r.unadjusted_amount)
      const rj = num(r.rje_adjustment)
      const aj = num(r.aje_adjustment)
      const au = num(r.audited_amount)

      // 收入类（贷方）：取绝对值加正数；费用/成本类（借方）：取绝对值减
      const dir = getDirection(r)
      const sign = dir === '贷' ? 1 : -1

      netProfit.unadjusted += Math.abs(u) * sign
      netProfit.rje += rj
      netProfit.aje += aj
      netProfit.audited += Math.abs(au) * sign

      result.push({ ...r, _highlight: r.exceeds_materiality })
    }

    // 净利润行（正数=盈利，负数=亏损）
    result.push({
      standard_account_code: '',
      account_name: '净利润',
      account_category: 'revenue',
      unadjusted_amount: String(netProfit.unadjusted),
      rje_adjustment: String(netProfit.rje),
      aje_adjustment: String(netProfit.aje),
      audited_amount: String(netProfit.audited),
      opening_balance: null,
      exceeds_materiality: false,
      below_trivial: false,
      _isSubtotal: true,
    } as DisplayRow)
  }

  return result
})

// 资产类合计（用展示逻辑：按方向加减）
const assetTotal = computed(() => {
  const assetRows = rows.value.filter(r => getActualCat(r) === 'asset')
  let total = 0
  for (const r of assetRows) {
    const val = Math.abs(num(r.audited_amount))
    const dir = getDirection(r)
    total += dir === '贷' ? -val : val
  }
  return total
})
// 负债+权益合计（用展示逻辑：按方向加减）
const liabEquityTotal = computed(() => {
  const leRows = rows.value.filter(r => ['liability', 'equity'].includes(getActualCat(r)))
  let total = 0
  for (const r of leRows) {
    const val = Math.abs(num(r.audited_amount))
    const dir = getDirection(r)
    // 负债/权益类：贷方加正数，借方减
    total += dir === '借' ? -val : val
  }
  return total
})
// 差额（资产 - 负债和权益），用于平衡校验
const balanceDiff = computed(() => assetTotal.value - liabEquityTotal.value)

// ── 数据新鲜度 ──
const lastRecalcAt = computed(() => {
  const times = rows.value.map(r => r.updated_at).filter(Boolean) as string[]
  if (!times.length) return null
  return times.sort().reverse()[0]  // 最大的 updated_at
})
const latestAdjustmentAt = ref<string | null>(null)
const isStale = computed(() => {
  if (!lastRecalcAt.value || !latestAdjustmentAt.value) return false
  return new Date(latestAdjustmentAt.value) > new Date(lastRecalcAt.value)
})
const freshnessText = computed(() => {
  if (!lastRecalcAt.value) return ''
  const d = new Date(lastRecalcAt.value)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins}分钟前`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}小时前`
  return d.toLocaleDateString('zh-CN')
})

async function loadLatestAdjustmentTime() {
  try {
    const adjs = await listAdjustments(projectId.value, year.value)
    if (adjs && adjs.length > 0) {
      const times = adjs.map((a: any) => a.updated_at).filter(Boolean).sort().reverse()
      latestAdjustmentAt.value = times[0] || null
    } else {
      latestAdjustmentAt.value = null
    }
  } catch { latestAdjustmentAt.value = null }
}

const isBalanced = computed(() => {
  // 正确逻辑：资产类合计 = 负债类合计 + 权益类合计，允许 1 元浮点误差
  if (!rows.value.length) return true
  return Math.abs(balanceDiff.value) < 1
})

// Task 2: Identify stale rows (updated_at older than latest adjustment)
const staleAccountCodes = computed<Set<string>>(() => {
  if (!latestAdjustmentAt.value) return new Set()
  const latestAdj = new Date(latestAdjustmentAt.value).getTime()
  const codes = new Set<string>()
  for (const row of rows.value) {
    if (row.updated_at && row.standard_account_code) {
      if (new Date(row.updated_at).getTime() < latestAdj) {
        codes.add(row.standard_account_code)
      }
    }
  }
  return codes
})

function num(v: string | null | undefined): number {
  return v != null ? parseFloat(v) || 0 : 0
}

// ─── 步骤引导（空数据时显示） ─────────────────────────────────────────────────
// ─── 步骤引导（根据实际数据状态自动检测）─────────────────────────────────────
// 数据状态（不用 localStorage，避免与真实数据状态不一致）
const dataState = ref<{
  hasBalance: boolean
  mappingRate: number  // 0-100
  hasTb: boolean
}>({ hasBalance: false, mappingRate: 0, hasTb: false })

const setupCurrentStep = computed(() => {
  if (!dataState.value.hasBalance) return 0  // 需要导入
  if (dataState.value.mappingRate < 80) return 1  // 需要映射
  if (!dataState.value.hasTb) return 2  // 需要生成试算表
  return 3  // 全部完成
})

const setupStepStatus = computed(() =>
  [0, 1, 2].map(i =>
    i < setupCurrentStep.value ? 'finish' :
    i === setupCurrentStep.value ? 'process' : 'wait'
  ) as ('wait' | 'process' | 'finish')[]
)

/** 检测当前数据状态（用于自动推进步骤） */
async function detectDataState() {
  try {
    const [balance, mapping] = await Promise.allSettled([
      api.get(P.ledger.balance(projectId.value), { params: { year: selectedYear.value } }),
      api.get(P.accountMapping.completionRate(projectId.value), { params: { year: selectedYear.value } }),
    ])
    dataState.value = {
      hasBalance: balance.status === 'fulfilled' && (balance.value?.length ?? 0) > 0,
      mappingRate: mapping.status === 'fulfilled' ? (mapping.value?.rate ?? mapping.value?.completion_rate ?? 0) : 0,
      hasTb: rows.value.length > 0,
    }
  } catch { /* ignore */ }
}

const showSetupGuide = computed(() => rows.value.length === 0)

// 试算表数据源选择弹窗
const tbImportVisible = ref(false)
const checkingData = ref(false)
const existingDataSummary = ref<{
  year: number
  balance_count: number
  ledger_count: number
  amount_unit: string
} | null>(null)

// 打开弹窗时检查是否已有数据
watch(tbImportVisible, async (visible) => {
  if (!visible) return
  checkingData.value = true
  existingDataSummary.value = null
  try {
    // 从余额表查询是否有数据
    const balance = await api.get(P.ledger.balance(projectId.value), { params: { year: selectedYear.value } })
    const balanceRows = balance ?? []
    if (balanceRows.length > 0) {
      // 有数据，获取数据集信息
      const { getActiveLedgerDataset } = await import('@/services/ledgerImportApi')
      const ds = await getActiveLedgerDataset(projectId.value, selectedYear.value)
      existingDataSummary.value = {
        year: selectedYear.value,
        balance_count: balanceRows.length,
        ledger_count: ds?.source_summary?.tb_ledger || 0,
        amount_unit: ds?.source_summary?.amount_unit || '元',
      }
    }
  } catch { /* ignore */ }
  finally { checkingData.value = false }
})

function onUseExistingData() {
  tbImportVisible.value = false
  // 有数据时直接执行映射+重算一条龙
  onAutoMapping()
}

function goToLedgerImport() {
  tbImportVisible.value = false
  router.push({ path: `/projects/${projectId.value}/ledger`, query: { import: '1' } })
}

function onImportDone() {
  tbImportVisible.value = false
  detectDataState()
  fetchData()
}

/** 工作流步骤动作（映射步骤点击时打开映射弹窗，导入步骤打开导入弹窗） */
function onWorkflowAction(action: string) {
  if (action === 'mapping') {
    showMappingDialog.value = true
  } else if (action === 'import') {
    onToolbarImport()
  }
}

/** 工具栏"Excel导入"按钮：弹框让用户选择导入类型 */
async function onToolbarImport() {
  try {
    const action = await ElMessageBox({
      title: 'Excel 导入',
      message: '请选择要导入的数据类型：',
      showCancelButton: true,
      distinguishCancelAndClose: true,
      confirmButtonText: '账套数据（四表）',
      cancelButtonText: '试算表数据',
    })
    if (action === 'confirm') {
      tbImportVisible.value = true  // 走账套导入流程
    }
  } catch (err: any) {
    if (err === 'cancel') {
      showTbImport.value = true  // 走试算表直接导入
    }
  }
}

// 自动科目映射（从已导入的余额表一级科目按编码规则匹配）
const autoMappingLoading = ref(false)
const mappingResultVisible = ref(false)
const mappingResult = ref<{ matched: number; needConfirm: number; total: number; rate: string }>({
  matched: 0, needConfirm: 0, total: 0, rate: '0',
})

function goToMappingEditor() {
  mappingResultVisible.value = false
  ElMessage.info('科目映射已自动完成，如需手动调整请在「查账」页面的「数据管理」中操作')
}

async function onAutoMapping() {
  autoMappingLoading.value = true
  try {
    const result = await api.post(P.accountMapping.autoMatch(projectId.value), { year: selectedYear.value })
    // Capture mapping quality result
    mappingResult.value = {
      matched: result?.saved_count ?? 0,
      needConfirm: result?.unmatched_count ?? 0,
      total: result?.total_client ?? 0,
      rate: String(Math.round(result?.completion_rate ?? 0)),
    }
    if (mappingResult.value.total === 0) {
      ElMessage.warning('未找到客户科目数据，请确认已导入科目余额表')
    } else {
      mappingResultVisible.value = true
      ElMessage.success('科目映射完成，正在生成试算表...')
    }
    await detectDataState()  // 刷新数据状态推进步骤
    // 映射完成后稍等一下再触发重算（避免后端事务竞争）
    await new Promise(r => setTimeout(r, 500))
    await onRecalc()
  } catch (e: any) {
    handleApiError(e, '自动科目映射')
  } finally {
    autoMappingLoading.value = false
  }
}

function rowClassName({ row }: { row: DisplayRow }) {
  if (row._isTotal) return 'total-row'
  if (row._isSubtotal) return 'subtotal-row'
  if (row._highlight) return 'highlight-row'
  // Task 2: stale rows (updated_at older than latest adjustment)
  if (row.standard_account_code && staleAccountCodes.value.has(row.standard_account_code)) return 'stale-row'
  return ''
}



async function ensureProjectYear() {
  if (routeYear.value !== null) {
    projectYear.value = null
    return
  }
  try {
    projectYear.value = await getProjectAuditYear(projectId.value)
  } catch {
    projectYear.value = null
  }
}

const fetchData = withLoading(loading, async () => {
  rows.value = await getTrialBalance(projectId.value, year.value, hasMultipleCompanies.value ? companyCode.value : undefined)
})

const onRecalc = withLoading(recalcLoading, async () => {
  await recalcTrialBalance(projectId.value, year.value)
  ElMessage.success('重算完成')
  await fetchData()
  await loadLatestAdjustmentTime()
})

const onConsistencyCheck = withLoading(checkLoading, async () => {
  consistencyResult.value = await checkConsistency(projectId.value, year.value)
})

function onTbImported() {
  showTbImport.value = false
  fetchData()
}

function onExport() {
  import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
    downloadFileAsBlob(`${P.trialBalance.export(projectId.value)}?year=${year.value}`, `试算表_${year.value}.xlsx`)
  })
}

function openWorkpaper(row: TrialBalanceRow) {
  const wpId = (row as any).wp_consistency?.wp_id
  if (wpId) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
  } else {
    ElMessage.info('该科目未关联底稿')
  }
}

async function onRecalcWp(row: any) {
  try {
    await api.post(P.workpapers.recalc(projectId.value, row.wp_consistency?.wp_id))
    ElMessage.success('重算已触发')
  } catch (e) { handleApiError(e, '重算底稿') }
}

function onUnadjustedClick(row: TrialBalanceRow) {
  // 点击未审数：跳转到余额表定位到对应科目（数据溯源）
  if (!row.standard_account_code) return
  router.push({
    path: `/projects/${projectId.value}/ledger`,
    query: { year: String(year.value), account: row.standard_account_code },
  })
}

async function onAdjClick(row: TrialBalanceRow, type: string) {
  adjDialogType.value = type.toUpperCase()
  adjDialogAccount.value = `${row.standard_account_code} ${row.account_name || ''}`
  adjDialogVisible.value = true
  try {
    const result = await listAdjustments(projectId.value, year.value, {
      adjustment_type: type, page_size: 200,
    })
    // Filter by account code from line_items
    const items = Array.isArray(result) ? result : (result.items || [])
    adjDialogList.value = items.filter((e: any) =>
      e.line_items?.some((li: any) => li.standard_account_code === row.standard_account_code)
    )
  } catch {
    adjDialogList.value = []
  }
}

watch(
  () => [projectId.value, routeYear.value],
  async () => {
    await ensureProjectYear()
    selectedProjectId.value = projectId.value
    selectedYear.value = year.value
    await fetchData()
    await detectDataState()  // 自动检测步骤状态
    await loadLatestAdjustmentTime()  // 加载最新调整时间用于新鲜度检测
    await loadCompanyList()  // Task 3: 加载子公司列表
    loadFreezeState()  // Task 4: 加载冻结状态
    if (!projectStore.projectOptions.length) projectStore.loadProjectOptions()
    // 加载底稿-科目映射
    try {
      wpMappings.value = await getAllWpMappings(projectId.value)
      const idx: Record<string, WpAccountMapping> = {}
      for (const m of wpMappings.value) {
        for (const code of m.account_codes) {
          idx[code] = m
        }
      }
      wpMappingIndex.value = idx
    } catch { /* ignore */ }
    // 加载已生成的底稿列表（用于直接跳转编辑器）
    try {
      wpList.value = await listWorkpapers(projectId.value)
    } catch { /* ignore */ }
  },
  { immediate: true }
)

// ─── Ctrl+F 快捷键注册 + shortcut:save 监听 ─────────────────────────────────
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', _closeTbSumCtx)
  eventBus.on('shortcut:save', onShortcutSave)
  // 底稿解析完成后自动刷新试算表（五环联动）
  eventBus.on('workpaper:parsed', onWorkpaperParsed)
  // 重要性水平变更后刷新试算表（exceeds_materiality 标记更新）
  eventBus.on('materiality:changed', onMaterialityChanged)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', _closeTbSumCtx)
  eventBus.off('shortcut:save', onShortcutSave)
  eventBus.off('workpaper:parsed', onWorkpaperParsed)
})
onBeforeUnmount(() => {
  eventBus.off('materiality:changed', onMaterialityChanged)
})

/** 快捷键保存：根据当前视图保存试算平衡表 */
function onShortcutSave() {
  if (tbViewMode.value === 'summary') {
    saveTbSummary()
  } else {
    onRecalc()
  }
}

/** 底稿解析完成后刷新试算表数据（五环联动） */
function onWorkpaperParsed(_payload: WorkpaperParsedPayload) {
  fetchData()
}

/** 重要性水平变更后刷新试算表（exceeds_materiality 标记更新） */
function onMaterialityChanged(payload: MaterialityChangedPayload) {
  if (payload.projectId !== projectId.value) return
  fetchData()
}

// ─── 试算平衡表（报表行次级别） ──────────────────────────────────────────────
const tbViewMode = ref<'detail' | 'summary'>('detail')
const tbSummaryType = ref('balance_sheet')
const tbSummaryLoading = ref(false)
// 溯源返回支持：记录从 summary 跳到 detail 的上下文
const tbTraceOrigin = ref<{ fromSummary: boolean; rowIndex: number; scrollTop: number } | null>(null)
const tbSummaryRows = ref<any[]>([])
const selectedTemplateType = ref('soe')
const tbSumImportInput = ref<HTMLInputElement | null>(null)

// 编辑模式开关（点击"编辑"按钮切换，编辑中可修改未审数，保存后退出编辑模式恢复双击溯源）
const tbSumEditMode = ref(false)

// 期初/期末切换
const tbSumPeriod = ref<'ending' | 'opening'>('ending')
// 期初数据来源：'prior_year'（连续审计，从上年带入）或 'manual'（首次承接，手动填写）
const tbSumOpeningSource = ref<'prior_year' | 'manual'>('manual')

// 未审数列是否可编辑（编辑模式开启时所有报表类型都可编辑）
const tbSumUnadjEditable = computed(() => tbSumEditMode.value)

// ── 试算平衡表交互 ──
const tbSumCtx = useCellSelection()
const tbSumSelectedRows = ref<Set<number>>(new Set())
const tbSumLastClickedRow = ref(-1)
const tbSumCtxVisible = ref(false)
const tbSumCtxX = ref(0)
const tbSumCtxY = ref(0)
const tbSumCtxRow = ref<any>(null)
const tbSummaryTableRef = ref<any>(null)

// 试算平衡表最大高度（表头固定）
const tbSummaryMaxHeight = computed(() => {
  if (tbFullscreen.value) return 'calc(100vh - 120px)'
  if (headerCollapsed.value) return 'calc(100vh - 220px)'
  return 'calc(100vh - 340px)'
})

// el-table 行样式
function tbSumRowClassName({ row, rowIndex }: { row: any; rowIndex: number }) {
  const classes: string[] = []
  if (row.is_total) classes.push('gt-tb-sum-total')
  if (row.is_category) classes.push('gt-tb-sum-category')
  if (row.formula_detached) classes.push('gt-tb-sum-detached')
  if (tbSumSelectedRows.value.has(rowIndex)) classes.push('gt-tb-sum-selected')
  return classes.join(' ')
}

// el-table 单元格样式（选中高亮 — 使用 useCellSelection composable）
function tbSumCellClassName({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }) {
  return tbSumCtx.cellClassName({ rowIndex, columnIndex })
}

// el-table 单元格点击事件（单选单元格 + 行选择）
function onTbSumCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const ri = tbSummaryRows.value.indexOf(row)
  if (ri < 0) return
  // 列索引映射
  const colIdx = _tbSumColIndex(column.property)
  if (colIdx >= 0) {
    const value = _tbSumGetCellVal(ri, colIdx)
    tbSumCtx.selectCell(ri, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
  }
  // 同时处理行选择逻辑
  onTbSumRowClick(event, ri)
}

// 列属性→列索引映射
const _TB_SUM_COLS = ['row_code', 'row_name', 'unadjusted', 'aje_dr', 'aje_cr', 'rcl_dr', 'rcl_cr', 'audited']
function _tbSumColIndex(prop: string): number {
  return _TB_SUM_COLS.indexOf(prop)
}

// 获取试算平衡表单元格值
function _tbSumGetCellVal(rowIdx: number, colIdx: number): any {
  const row = tbSummaryRows.value[rowIdx]
  if (!row) return null
  return row[_TB_SUM_COLS[colIdx]] ?? null
}

// el-table 行点击事件（保留兼容 — cell-click 已处理行选择）

// el-table 行右键事件
function onTbSumElContextMenu(row: any, _column: any, event: MouseEvent) {
  event.preventDefault()
  const ri = tbSummaryRows.value.indexOf(row)
  if (ri < 0) return
  onTbSumContextMenu(event, row, ri)
}

// el-table 行双击事件
function onTbSumElDblClick(row: any) {
  onTbSumDblClick(row)
}

// 兼容旧代码的单行选中
const tbSumSelectedRow = computed(() => {
  const s = tbSumSelectedRows.value
  return s.size === 1 ? [...s][0] : -1
})

function onTbSumRowClick(event: MouseEvent, ri: number) {
  if (event.shiftKey && tbSumLastClickedRow.value >= 0) {
    // Shift+点击：范围选择
    const start = Math.min(tbSumLastClickedRow.value, ri)
    const end = Math.max(tbSumLastClickedRow.value, ri)
    const newSet = new Set<number>()
    for (let i = start; i <= end; i++) newSet.add(i)
    tbSumSelectedRows.value = newSet
  } else if (event.ctrlKey || event.metaKey) {
    // Ctrl+点击：追加/取消选择
    const newSet = new Set(tbSumSelectedRows.value)
    if (newSet.has(ri)) newSet.delete(ri)
    else newSet.add(ri)
    tbSumSelectedRows.value = newSet
  } else {
    // 普通点击：单选
    tbSumSelectedRows.value = new Set([ri])
  }
  tbSumLastClickedRow.value = ri
}

function onTbSumContextMenu(event: MouseEvent, row: any, _ri: number) {
  tbSumCtxRow.value = row
  tbSumCtxX.value = event.clientX
  tbSumCtxY.value = event.clientY
  // 防超出视口
  const viewH = window.innerHeight
  if (tbSumCtxY.value + 180 > viewH) tbSumCtxY.value = viewH - 180
  tbSumCtxVisible.value = true
}

function onTbSumDblClick(row: any) {
  // 可编辑模式或已断开公式的行双击不跳转
  if (tbSumEditMode.value || row.formula_detached) return
  onTbSumTrace(row)
}

function onTbSumTrace(row: any) {
  // 溯源：跳转到科目明细 Tab 并定位到对应科目
  if (!row.row_name) return
  // 记录来源位置，支持 Backspace 返回
  const scrollEl = tbSummaryTableRef.value?.$el?.querySelector('.el-table__body-wrapper')
  tbTraceOrigin.value = {
    fromSummary: true,
    rowIndex: tbSummaryRows.value.indexOf(row),
    scrollTop: scrollEl?.scrollTop || 0,
  }
  tbViewMode.value = 'detail'
  // 在科目明细中找到对应的科目行并滚动
  setTimeout(() => {
    const target = rows.value.find(r => r.account_name === row.row_name)
    if (target && tbTableRef.value) {
      tbTableRef.value.setCurrentRow(target)
      const idx = groupedRows.value.indexOf(target as any)
      if (idx >= 0) {
        const tbody = tbTableRef.value.$el?.querySelector('.el-table__body-wrapper')
        const rowEls = tbody?.querySelectorAll('tr.el-table__row')
        rowEls?.[idx]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
  }, 200)
}

function onTbSumCtxCopy() {
  tbSumCtxVisible.value = false
  // 多行复制
  const selectedIndices = [...tbSumSelectedRows.value].sort((a, b) => a - b)
  if (!selectedIndices.length && tbSumCtxRow.value) {
    // 没有选中行时复制右键行
    const row = tbSumCtxRow.value
    navigator.clipboard.writeText(`${row.row_code}\t${row.row_name}\t${row.unadjusted || ''}\t${row.audited || ''}`)
    ElMessage.success('已复制')
    return
  }
  const lines = selectedIndices.map(i => {
    const row = tbSummaryRows.value[i]
    return `${row.row_code}\t${row.row_name}\t${row.unadjusted || ''}\t${row.aje_dr || ''}\t${row.aje_cr || ''}\t${row.rcl_dr || ''}\t${row.rcl_cr || ''}\t${row.audited || ''}`
  })
  navigator.clipboard.writeText(lines.join('\n'))
  ElMessage.success(`已复制 ${lines.length} 行`)
}

function onTbSumCtxFormula() {
  tbSumCtxVisible.value = false
  const row = tbSumCtxRow.value
  if (!row) return
  // 查看该行的公式（从 report_config 加载的 formula 字段）
  const formula = row._formula || '无公式（通过映射关系取数）'
  const detail = `【${row.row_code} ${row.row_name}】\n\n公式：${formula}\n\n未审数：${Number(row.unadjusted || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n审定数：${Number(row.audited || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
  ElMessageBox.alert(detail, '公式详情', {
    confirmButtonText: '确定',
    customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'Arial Narrow', monospace", fontSize: '12px' },
  })
}

function onTbSumCtxDetail() {
  tbSumCtxVisible.value = false
  const row = tbSumCtxRow.value
  if (!row) return
  // 汇总明细：展示该行的计算过程
  if (row.is_total || row.is_category) {
    // 合计行：展示子行汇总
    let detail = `【${row.row_name} 计算明细】\n\n`
    const idx = tbSummaryRows.value.indexOf(row)
    for (let i = idx - 1; i >= 0; i--) {
      const prev = tbSummaryRows.value[i]
      if (prev.is_category || prev.is_total) break
      if (prev.unadjusted) {
        detail += `  + ${prev.row_code} ${prev.row_name}：${Number(prev.unadjusted).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n`
      }
    }
    detail += `\n━━━━━━━━━━━━━━━━\n合计 = ${Number(row.unadjusted || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
    ElMessageBox.alert(detail, '汇总明细', {
      confirmButtonText: '确定',
      customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'Arial Narrow', monospace", fontSize: '12px', maxHeight: '70vh', overflow: 'auto' },
    })
  } else {
    // 普通行：展示取数来源
    const detail = `【${row.row_code} ${row.row_name}】\n\n取数来源：通过映射规则从科目明细汇总\n未审数 = Σ 映射到该行次的所有科目余额\n\n当前值：${Number(row.unadjusted || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
    ElMessageBox.alert(detail, '取数明细', {
      confirmButtonText: '确定',
      customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'Arial Narrow', monospace", fontSize: '12px' },
    })
  }
}

function onTbSumCtxTrace() {
  tbSumCtxVisible.value = false
  onTbSumTrace(tbSumCtxRow.value)
}

/** 断开公式：标记该行为手动值，不再被公式计算覆盖 */
function onTbSumCtxDetachFormula() {
  tbSumCtxVisible.value = false
  const row = tbSumCtxRow.value
  if (!row) return
  row.formula_detached = true
  // 自动进入编辑模式方便立即填写
  tbSumEditMode.value = true
  ElMessage.success(`"${row.row_name}" 已断开公式，可直接编辑未审数，编辑完请保存`)
}

/** 恢复公式：取消手动标记，立即刷新恢复公式计算值 */
function onTbSumCtxRestoreFormula() {
  tbSumCtxVisible.value = false
  const row = tbSumCtxRow.value
  if (!row) return
  row.formula_detached = false
  ElMessage.success(`"${row.row_name}" 已恢复公式，正在重新计算...`)
  // 立即刷新以获取公式计算值
  loadTbSummary()
}

// 点击其他地方关闭右键菜单
function _closeTbSumCtx() { tbSumCtxVisible.value = false }


function recalcTbSummaryAudited() {
  for (const r of tbSummaryRows.value) {
    const u = Number(r.unadjusted) || 0
    const ad = Number(r.aje_dr) || 0
    const ac = Number(r.aje_cr) || 0
    const rd = Number(r.rcl_dr) || 0
    const rc = Number(r.rcl_cr) || 0
    const result = u + ad - ac + rd - rc
    r.audited = result !== 0 ? Math.round(result * 100) / 100 : null
  }
}

watch(tbSummaryRows, recalcTbSummaryAudited, { deep: true })
const { isFullscreen: tbFullscreen, toggleFullscreen: toggleTbFullscreen } = useFullscreen()

// 表格最大高度（视口高度 - 顶部区域，实现表头固定）
const tableMaxHeight = computed(() => {
  if (tbFullscreen.value) return 'calc(100vh - 60px)'
  if (headerCollapsed.value) return 'calc(100vh - 160px)'
  return 'calc(100vh - 320px)'
})

function copyTbTable() {
  const data = tbViewMode.value === 'summary' ? tbSummaryRows.value : groupedRows.value
  if (!data?.length) { ElMessage.warning('无数据可复制'); return }
  let headers: string[], dataRows: any[][]
  if (tbViewMode.value === 'summary') {
    headers = ['行次', '项目', '未审数', '审计调整-借', '审计调整-贷', '重分类-借', '重分类-贷', '审定数']
    dataRows = data.map((r: any) => [r.row_code, r.row_name, r.unadjusted, r.aje_dr, r.aje_cr, r.rcl_dr, r.rcl_cr, r.audited])
  } else {
    headers = ['科目编码', '科目名称', '未审数', 'RJE调整', 'AJE调整', '审定数']
    dataRows = data.map((r: any) => [r.standard_account_code, r.account_name, r.unadjusted_amount, r.rje_adjustment, r.aje_adjustment, r.audited_amount])
  }
  const text = [headers.join('\t'), ...dataRows.map(r => r.join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${dataRows.map(r => `<tr>${r.map(c => `<td>${c ?? ''}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${dataRows.length} 行`)
  } catch { navigator.clipboard?.writeText(text); ElMessage.success('已复制') }
}

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
const tbCtx = useCellSelection()
const penetrate = usePenetrate()
const tbComments = useCellComments(() => projectId.value, () => year.value, 'trial_balance')
const tbSumLazyEdit = useLazyEdit()

// ─── 拖拽框选（鼠标左键按住拖动选中连续区域） ──────────────────────────────
const tbTableRef = ref<any>(null)

// [R9 F10 Task 32] usePasteImport 接入：粘贴 AJE 到调整列
usePasteImport({
  containerRef: tbTableRef,
  columns: [
    { key: 'account_code', label: '科目编码' },
    { key: 'debit', label: '借方调整' },
    { key: 'credit', label: '贷方调整' },
  ],
  onInsert: async (rows) => {
    // 将粘贴的 AJE 数据写入调整列（通过 API 批量创建调整分录）
    for (const r of rows) {
      if (!r.account_code) continue
      try {
        await api.post(P.adjustments.create(projectId.value), {
          account_code: r.account_code,
          debit_amount: parseFloat(r.debit) || 0,
          credit_amount: parseFloat(r.credit) || 0,
          year: selectedYear.value,
          summary: '粘贴导入',
        })
      } catch { /* 静默跳过单行失败 */ }
    }
    ElMessage.success(`已粘贴 ${rows.length} 行 AJE 数据`)
    // 刷新试算表
    fetchData()
  },
})

tbCtx.setupTableDrag(tbTableRef, (rowIdx: number, colIdx: number) => {
  const row = groupedRows.value[rowIdx]
  if (!row) return null
  if (colIdx === 0) return row.standard_account_code
  if (colIdx === 1) return row.account_name
  if (colIdx === 2) return row.unadjusted_amount
  if (colIdx === 3) return row.rje_adjustment
  if (colIdx === 4) return row.aje_adjustment
  if (colIdx === 5) return row.audited_amount
  return null
})

// 试算平衡表（summary）拖拽框选
tbSumCtx.setupTableDrag(tbSummaryTableRef, _tbSumGetCellVal)

// ─── 粘贴监听（Ctrl+V 粘贴 Excel 数据到选中区域） ──────────────────────────
const tbColumns = [
  { key: 'standard_account_code', label: '科目编码' },
  { key: 'account_name', label: '科目名称' },
  { key: 'unadjusted_amount', label: '未审数' },
  { key: 'rje_adjustment', label: 'RJE调整' },
  { key: 'aje_adjustment', label: 'AJE调整' },
  { key: 'audited_amount', label: '审定数' },
]

setupPasteListener(tbTableRef, (event: ClipboardEvent) => {
  if (!tbCtx.selectedCells.value.length) return
  pasteToSelection(event, tbCtx.selectedCells.value, groupedRows.value, tbColumns)
})

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const tbSearch = useTableSearch(
  computed(() => tbViewMode.value === 'detail' ? groupedRows.value : tbSummaryRows.value),
  ['standard_account_code', 'account_name'],
)

/** Ctrl+F 快捷键触发搜索栏（拦截浏览器默认搜索） */
function onKeydown(e: KeyboardEvent) {
  // Backspace：从溯源返回试算平衡表原位置
  if (e.key === 'Backspace' && tbTraceOrigin.value?.fromSummary && tbViewMode.value === 'detail') {
    const target = e.target as HTMLElement
    // 不拦截输入框内的 Backspace
    if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable) return
    e.preventDefault()
    const origin = tbTraceOrigin.value
    tbViewMode.value = 'summary'
    tbTraceOrigin.value = null
    // 恢复滚动位置和选中行
    setTimeout(() => {
      const scrollEl = tbSummaryTableRef.value?.$el?.querySelector('.el-table__body-wrapper')
      if (scrollEl && origin.scrollTop) scrollEl.scrollTop = origin.scrollTop
      if (origin.rowIndex >= 0) tbSumSelectedRows.value = new Set([origin.rowIndex])
    }, 100)
    return
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault()
    e.stopPropagation()
    tbSearch.toggle()
  }
  // R7-S3-08：Ctrl+A 全选表格
  if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
    const target = e.target as HTMLElement
    if (target?.closest('.el-table')) {
      e.preventDefault()
      tbCtx.selectAll(groupedRows.value.length, 6)
    }
  }
}

function tbCellClassName({ rowIndex, columnIndex }: any) {
  const classes: string[] = []
  const selClass = tbCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  const ccClass = tbComments.commentCellClass('tb_detail', rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

function onTbCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  tbCtx.closeContextMenu()
  const rowIdx = groupedRows.value.indexOf(row)
  const colLabels: Record<string, number> = { '科目编码': 0, '科目名称': 1, '未审数': 2, 'RJE调整': 3, 'AJE调整': 4, '审定数': 5 }
  const colIdx = colLabels[column.label] ?? -1
  if (rowIdx < 0 || colIdx < 0) return
  const value = colIdx === 2 ? row.unadjusted_amount : colIdx === 3 ? row.rje_adjustment : colIdx === 4 ? row.aje_adjustment : colIdx === 5 ? row.audited_amount : row.account_name
  tbCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
  tbCtx.contextMenu.rowData = row
  tbCtx.contextMenu.itemName = row.account_name || ''
}

// R7-S3-09 Task 44：双击金额穿透到序时账
function onTbCellDblClick(row: any, column: any) {
  const amountCols = ['未审数', 'RJE调整', 'AJE调整', '审定数']
  if (amountCols.includes(column.label) && row.standard_account_code) {
    penetrate.toLedger(row.standard_account_code)
  }
}

function onTbCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const rowIdx = groupedRows.value.indexOf(row)
  const colLabels: Record<string, number> = { '科目编码': 0, '科目名称': 1, '未审数': 2, 'RJE调整': 3, 'AJE调整': 4, '审定数': 5 }
  const colIdx = colLabels[column.label] ?? -1
  // 如果右键点击的单元格已在选区内，保持选区不变
  if (rowIdx >= 0 && colIdx >= 0 && !tbCtx.isCellSelected(rowIdx, colIdx)) {
    const value = colIdx === 2 ? row.unadjusted_amount : colIdx === 3 ? row.rje_adjustment : colIdx === 4 ? row.aje_adjustment : colIdx === 5 ? row.audited_amount : row.account_name
    tbCtx.selectCell(rowIdx, colIdx, value, false)
  }
  tbCtx.contextMenu.rowData = row
  tbCtx.contextMenu.itemName = row.account_name || ''
  tbCtx.openContextMenu(event, tbCtx.contextMenu.itemName, row)
}

function onTbCtxCopy() {
  tbCtx.closeContextMenu()
  tbCtx.copySelectedValues()
  ElMessage.success('已复制')
}

function onTbCtxDrillDown() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  if (!row) return

  // 净利润行：展示计算明细（每个损益科目的加减过程）
  if (row._isSubtotal && row.account_name === '净利润') {
    _showNetProfitDetail()
    return
  }

  // 小计行：展示该类别下所有科目的汇总明细
  if (row._isSubtotal || row._isTotal) {
    _showSubtotalDetail(row)
    return
  }

  // 普通科目行：跳转到余额表溯源
  onUnadjustedClick(row)
}

function _showNetProfitDetail() {
  const incomeExpenseRows = rows.value.filter(r => INCOME_EXPENSE_CATS.includes(getActualCat(r)))
  if (!incomeExpenseRows.length) {
    ElMessage.info('暂无损益类科目数据')
    return
  }

  let detail = '【净利润计算明细】\n\n'
  let totalRevenue = 0
  let totalExpense = 0

  // 收入类
  detail += '━━ 收入类（+）━━\n'
  for (const r of incomeExpenseRows) {
    const dir = getDirection(r)
    if (dir !== '贷') continue
    const val = Math.abs(Number(r.unadjusted_amount || 0))
    if (val === 0) continue
    totalRevenue += val
    detail += `  + ${r.standard_account_code} ${r.account_name}：${val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n`
  }
  detail += `  收入合计：${totalRevenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n\n`

  // 费用/成本类
  detail += '━━ 费用/成本类（-）━━\n'
  for (const r of incomeExpenseRows) {
    const dir = getDirection(r)
    if (dir !== '借') continue
    const val = Math.abs(Number(r.unadjusted_amount || 0))
    if (val === 0) continue
    totalExpense += val
    detail += `  - ${r.standard_account_code} ${r.account_name}：${val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n`
  }
  detail += `  费用合计：${totalExpense.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n\n`

  // 净利润
  const netProfit = totalRevenue - totalExpense
  detail += '━━━━━━━━━━━━━━━━\n'
  detail += `净利润 = 收入 - 费用 = ${netProfit.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n`
  detail += netProfit >= 0 ? '（盈利）' : '（亏损）'

  ElMessageBox.alert(detail, '净利润计算明细', {
    confirmButtonText: '确定',
    customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'Arial Narrow', monospace", fontSize: '12px', maxHeight: '70vh', overflow: 'auto' },
  })
}

function _showSubtotalDetail(row: any) {
  const cat = row.account_category || ''
  const name = row.account_name || ''

  // "负债和权益合计"特殊处理：包含负债+权益两个类别
  let catRows: any[]
  let catLabel: string
  if (name.includes('负债和权益合计')) {
    catRows = rows.value.filter(r => ['liability', 'equity'].includes(getActualCat(r)))
    catLabel = '负债和权益'
  } else {
    catRows = rows.value.filter(r => getActualCat(r) === cat)
    catLabel = ({ asset: '资产', liability: '负债', equity: '权益' } as any)[cat] || cat
  }

  if (!catRows.length) {
    ElMessage.info('暂无明细数据')
    return
  }

  let detail = `【${name} 计算明细】\n\n`
  const catIsDebit = cat === 'asset'

  for (const r of catRows) {
    const val = Math.abs(Number(r.unadjusted_amount || 0))
    if (val === 0) continue
    const dir = getDirection(r)
    // 负债/权益类：贷方加，借方减
    const sign = (catIsDebit && dir === '贷') || (!catIsDebit && dir === '借') ? '-' : '+'
    detail += `  ${sign} ${r.standard_account_code} ${r.account_name}：${val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}（${dir}）\n`
  }
  detail += `\n━━━━━━━━━━━━━━━━\n`
  detail += `${name} = ${Math.abs(Number(row.unadjusted_amount || 0)).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`

  ElMessageBox.alert(detail, `${catLabel}类汇总明细`, {
    confirmButtonText: '确定',
    customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'Arial Narrow', monospace", fontSize: '12px', maxHeight: '70vh', overflow: 'auto' },
  })
}

// ─── 数据溯源：跳转到余额表并定位到对应科目 ───
async function onTbCtxTrace() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  if (!row?.standard_account_code) {
    ElMessage.info('请在科目行上右键')
    return
  }
  // 跳转到查账页面，带上科目编码参数，查账页面会自动定位
  router.push({
    path: `/projects/${projectId.value}/ledger`,
    query: { year: String(year.value), account: row.standard_account_code },
  })
}

function onTbCtxFormula() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  if (!row) {
    ElMessage.info('请选择一个单元格')
    return
  }

  const code = row.standard_account_code || ''
  const name = row.account_name || code || '—'
  const dir = getDirection(row)
  const val = Number(row.unadjusted_amount || 0)

  let formulaDesc = ''

  if (row._isSubtotal || row._isTotal) {
    // 小计/合计行：展示汇总公式
    formulaDesc += `【${name}】\n\n`
    if (name.includes('净利润')) {
      formulaDesc += `= Σ 收入类科目（贷方）- Σ 费用/成本类科目（借方）\n`
      formulaDesc += `\n收入类取绝对值相加，费用类取绝对值相减`
    } else if (name.includes('负债和权益合计')) {
      formulaDesc += `= 负债 小计 + 权益 小计\n`
      formulaDesc += `\n用于与"资产 小计"校对（应相等）`
    } else {
      const cat = row.account_category || ''
      const catLabel = ({ asset: '资产', liability: '负债', equity: '权益' } as Record<string, string>)[cat] || cat
      formulaDesc += `= Σ ${catLabel}类各科目（按方向加减）\n\n`
      formulaDesc += `规则：同方向科目取绝对值相加，反方向科目取绝对值相减\n`
      formulaDesc += `（如资产类中贷方科目为减项）`
    }
  } else {
    // 普通科目行
    formulaDesc += `科目：${code} ${name}\n`
    formulaDesc += `方向：${dir}\n`
    formulaDesc += `未审数：${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}\n`
    formulaDesc += `\n取数公式：\n`

    const first = code.charAt(0)
    if (first === '5' || first === '6') {
      const isRevenue = ['5001', '5051', '5101'].includes(code) ||
        (first === '6' && ['6001', '6051', '6101', '6111', '6115', '6117', '6301'].includes(code.slice(0, 4)))
      if (isRevenue) {
        formulaDesc += `= SUM(tb_balance.credit_amount)\n  [收入类：取贷方发生额]`
      } else {
        formulaDesc += `= SUM(tb_balance.debit_amount)\n  [费用类：取借方发生额]`
      }
    } else {
      formulaDesc += `= SUM(tb_balance.closing_balance)\n  [资产/负债/权益：取期末余额]`
    }
    formulaDesc += `\n\n审定数 = 未审数 + RJE调整 + AJE调整`
  }

  ElMessageBox.alert(formulaDesc, `公式详情`, {
    confirmButtonText: '确定',
    customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'Arial Narrow', monospace", fontSize: '13px' },
  })
}

function onTbCtxOpenWp() {
  tbCtx.closeContextMenu()
  if (tbCtx.contextMenu.rowData?.standard_account_code) onOpenWorkpaper(tbCtx.contextMenu.rowData.standard_account_code)
}

function onTbCtxSum() {
  tbCtx.closeContextMenu()
  const sum = tbCtx.sumSelectedValues()
  ElMessage.info(`选中 ${tbCtx.selectedCells.value.length} 格，合计：${fmtAmount(sum)}`)
}

function onTbCtxCompare() {
  tbCtx.closeContextMenu()
  if (tbCtx.selectedCells.value.length < 2) return
  const vals = tbCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  ElMessage.info(`差异：${fmtAmount(diff)}`)
}

function onTbCtxViewAdj() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  if (!row?.standard_account_code) {
    ElMessage.info('请先选中一个科目行')
    return
  }
  router.push({
    path: `/projects/${projectId.value}/adjustments`,
    query: { year: String(year.value), account: row.standard_account_code },
  })
}

// enterprise-linkage 3.10：右键"查看关联底稿" → 跳转底稿列表筛选该科目
function onTbCtxViewLinkedWp() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  if (!row?.standard_account_code) {
    ElMessage.info('请先选中一个科目行')
    return
  }
  router.push({
    path: `/projects/${projectId.value}/workpapers`,
    query: { account: row.standard_account_code },
  })
}

const tbSummaryTypes = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow_statement', label: '现金流量表' },
  { key: 'cash_flow_supplement', label: '现金流量附表' },
]

async function loadTbSummary() {
  tbSummaryLoading.value = true
  try {
    if (tbSumPeriod.value === 'opening') {
      // 期初试算：尝试从上年项目获取审定数，否则从 consol_worksheet_data 加载手动数据
      await _loadOpeningTbSummary()
      return
    }
    // 期末试算：调用新接口从 adjustments 表自动汇总 AJE/RJE
    const result = await api.get(
      P.trialBalance.summaryWithAdjustments(projectId.value),
      {
        params: { year: year.value, report_type: tbSummaryType.value },
        validateStatus: (s: number) => s < 600,
      }
    )
    const apiRows = result?.rows ?? []

    if (apiRows.length > 0) {
      // 新接口返回完整数据（含 AJE/RJE 自动汇总）
      tbSummaryRows.value = apiRows.map((r: any) => ({
        row_code: r.row_code || '',
        row_name: r.row_name || '',
        indent: r.indent || 0,
        is_total: r.is_total || false,
        is_category: r.is_category || false,
        unadjusted: r.unadjusted ?? null,
        aje_dr: r.aje_dr ?? null,
        aje_cr: r.aje_cr ?? null,
        rcl_dr: r.rcl_dr ?? null,
        rcl_cr: r.rcl_cr ?? null,
        audited: r.audited ?? null,
      }))
    } else {
      // 新接口无数据（报表行次未配置），降级：从报表配置+科目明细构建
      const standard = `${selectedTemplateType.value}_standalone`
      const reportData = await api.get(P.reportConfig.list, {
        params: { report_type: tbSummaryType.value, applicable_standard: standard, project_id: projectId.value },
        validateStatus: (s: number) => s < 600,
      })
      const reportRows = Array.isArray(reportData) ? reportData : []

      // 从科目明细汇总未审数
      const unadjMap: Record<string, number> = {}
      for (const r of rows.value) {
        if (r.account_name && r.unadjusted_amount) {
          unadjMap[r.account_name.trim()] = (unadjMap[r.account_name.trim()] || 0) + Number(r.unadjusted_amount || 0)
        }
      }

      // 从科目明细汇总 AJE/RCL（只读，不可手动编辑）
      const ajeMap: Record<string, { dr: number; cr: number }> = {}
      const rclMap: Record<string, { dr: number; cr: number }> = {}
      for (const r of rows.value) {
        const name = (r.account_name || '').trim()
        if (!name) continue
        const aje = Number(r.aje_adjustment || 0)
        const rje = Number(r.rje_adjustment || 0)
        if (aje > 0) { ajeMap[name] = ajeMap[name] || { dr: 0, cr: 0 }; ajeMap[name].dr += aje }
        else if (aje < 0) { ajeMap[name] = ajeMap[name] || { dr: 0, cr: 0 }; ajeMap[name].cr += Math.abs(aje) }
        if (rje > 0) { rclMap[name] = rclMap[name] || { dr: 0, cr: 0 }; rclMap[name].dr += rje }
        else if (rje < 0) { rclMap[name] = rclMap[name] || { dr: 0, cr: 0 }; rclMap[name].cr += Math.abs(rje) }
      }

      tbSummaryRows.value = reportRows.map((r: any) => {
        const name = (r.row_name || '').trim().replace(/^[△▲*#\s]+/, '')
        const unadj = unadjMap[name] || Number(r.current_period_amount || 0) || null
        const aje = ajeMap[name] || { dr: 0, cr: 0 }
        const rcl = rclMap[name] || { dr: 0, cr: 0 }
        return {
          row_code: r.row_code || '',
          row_name: r.row_name || '',
          indent: r.indent_level || 0,
          is_total: r.is_total_row || false,
          is_category: (r.indent_level === 0 && !r.is_total_row),
          unadjusted: unadj,
          aje_dr: aje.dr || null,
          aje_cr: aje.cr || null,
          rcl_dr: rcl.dr || null,
          rcl_cr: rcl.cr || null,
          audited: null as number | null,
        }
      })
      recalcTbSummaryAudited()
    }

    // 合并已保存的手动编辑数据（用户手动填写的未审数不被公式计算覆盖）
    await _mergeSavedTbSummary()
  } catch { tbSummaryRows.value = [] }
  finally { tbSummaryLoading.value = false }
}

/**
 * 加载期初试算平衡表
 * 1. 尝试从上年项目获取审定数（连续审计）
 * 2. 无上年数据时从 consol_worksheet_data 加载手动保存的期初数据（首次承接）
 * 3. 都没有则加载空行次结构供手动填写
 */
async function _loadOpeningTbSummary() {
  try {
    // 先尝试从上年获取（连续审计场景）
    const priorYear = year.value - 1
    let priorRows: any[] = []
    try {
      const priorResult = await api.get(
        P.trialBalance.summaryWithAdjustments(projectId.value),
        { params: { year: priorYear, report_type: tbSummaryType.value }, validateStatus: (s: number) => s < 600 }
      )
      priorRows = priorResult?.rows ?? []
    } catch { /* 上年无数据，静默 */ }

    if (priorRows.length > 0) {
      // 检查上年数据是否有实质内容（全 0/null 视为无效）
      const hasSubstance = priorRows.some((r: any) => r.audited || r.unadjusted)
      if (hasSubstance) {
        // 连续审计：上年审定数作为本年期初
        tbSumOpeningSource.value = 'prior_year'
        tbSummaryRows.value = priorRows.map((r: any) => ({
          row_code: r.row_code || '',
          row_name: r.row_name || '',
          indent: r.indent || 0,
          is_total: r.is_total || false,
          is_category: r.is_category || false,
          unadjusted: r.audited ?? r.unadjusted ?? null,  // 上年审定数作为期初未审数
          aje_dr: null,  // 期初的审计调整需要单独记录
          aje_cr: null,
          rcl_dr: null,
          rcl_cr: null,
          audited: r.audited ?? null,
        }))
      } else {
        priorRows = []  // 全空数据视为无上年，走首次承接
      }
    }
    if (priorRows.length === 0) {
      // 首次承接：加载空行次结构
      tbSumOpeningSource.value = 'manual'
      const standard = `${selectedTemplateType.value}_standalone`
      const reportData = await api.get(P.reportConfig.list, {
        params: { report_type: tbSummaryType.value, applicable_standard: standard, project_id: projectId.value },
        validateStatus: (s: number) => s < 600,
      })
      const reportRows = Array.isArray(reportData) ? reportData : []
      tbSummaryRows.value = reportRows.map((r: any) => ({
        row_code: r.row_code || '',
        row_name: r.row_name || '',
        indent: r.indent_level || 0,
        is_total: r.is_total_row || false,
        is_category: (r.indent_level === 0 && !r.is_total_row),
        unadjusted: null,
        aje_dr: null,
        aje_cr: null,
        rcl_dr: null,
        rcl_cr: null,
        audited: null,
      }))
    }

    // 合并已保存的期初手动数据（覆盖上年带入值或填充空行）
    await _mergeSavedTbSummary('opening')
    recalcTbSummaryAudited()
  } catch { tbSummaryRows.value = [] }
  finally { tbSummaryLoading.value = false }
}

/**
 * 合并已保存的手动数据：对于公式计算结果为空（null/0）的行，
 * 用之前手动保存的值覆盖（典型场景：现金流量表无公式，全靠手动填写）
 */
async function _mergeSavedTbSummary(periodOverride?: string) {
  try {
    const period = periodOverride || tbSumPeriod.value
    const sheetKey = period === 'opening'
      ? `tb_summary_opening_${tbSummaryType.value}`
      : `tb_summary_${tbSummaryType.value}`
    const saved = await api.get(
      P.consolWorksheetData.get(projectId.value, selectedYear.value, sheetKey),
      { validateStatus: (s: number) => s < 600 }
    )
    const savedRows: any[] = saved?.data?.rows || saved?.rows || []
    if (!savedRows.length) return

    // 按 row_code 建索引
    const savedMap = new Map<string, any>()
    for (const sr of savedRows) {
      if (sr.row_code) savedMap.set(sr.row_code, sr)
    }

    // 对当前行：如果公式计算结果为空但已保存有值，用保存值覆盖
    // formula_detached=true 的行强制用保存值（不管公式是否有值）
    for (const row of tbSummaryRows.value) {
      const saved = savedMap.get(row.row_code)
      if (!saved) continue
      // 恢复 formula_detached 标记
      if (saved.formula_detached) {
        row.formula_detached = true
        // 断开公式的行：强制用保存值覆盖
        if (saved.unadjusted != null) row.unadjusted = saved.unadjusted
        if (saved.rcl_dr != null) row.rcl_dr = saved.rcl_dr
        if (saved.rcl_cr != null) row.rcl_cr = saved.rcl_cr
      } else {
        // 未断开的行：仅公式无值时用保存值
        if (!row.unadjusted && saved.unadjusted) row.unadjusted = saved.unadjusted
        if (!row.rcl_dr && saved.rcl_dr) row.rcl_dr = saved.rcl_dr
        if (!row.rcl_cr && saved.rcl_cr) row.rcl_cr = saved.rcl_cr
      }
    }
    // 重算审定数
    recalcTbSummaryAudited()
  } catch { /* 无保存数据或接口不可用，静默跳过 */ }
}

async function saveTbSummary() {
  try {
    const saveRows = tbSummaryRows.value.map((r: any) => ({
      row_code: r.row_code, row_name: r.row_name,
      unadjusted: r.unadjusted, aje_dr: r.aje_dr, aje_cr: r.aje_cr,
      rcl_dr: r.rcl_dr, rcl_cr: r.rcl_cr,
      formula_detached: r.formula_detached || false,
    }))
    const sheetKey = tbSumPeriod.value === 'opening'
      ? `tb_summary_opening_${tbSummaryType.value}`
      : `tb_summary_${tbSummaryType.value}`
    await api.put(
      P.consolWorksheetData.get(projectId.value, selectedYear.value, sheetKey),
      { sheet_key: sheetKey, data: { rows: saveRows } },
      { validateStatus: (s: number) => s < 600 }
    )
    ElMessage.success('试算平衡表已保存')
    tbSumEditMode.value = false  // 保存后退出编辑模式，恢复双击溯源
  } catch (e) { handleApiError(e, '保存试算平衡表') }
}

async function exportTbSummary() {
  if (!tbSummaryRows.value.length) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = ['行次', '项目', '未审数', '审计调整-借', '审计调整-贷', '重分类-借', '重分类-贷', '审定数']
  const dataRows = tbSummaryRows.value.map((r: any) => [
    r.row_code, r.row_name, r.unadjusted, r.aje_dr, r.aje_cr, r.rcl_dr, r.rcl_cr, r.audited,
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map((_, i) => ({ wch: i < 2 ? 20 : 14 }))
  XLSX.utils.book_append_sheet(wb, ws, '试算平衡表')
  const label = tbSummaryTypes.find(t => t.key === tbSummaryType.value)?.label || ''
  XLSX.writeFile(wb, `试算平衡表_${label}.xlsx`)
  ElMessage.success('已导出')
}

/** 导出命令分发 */
function onTbSumExportCmd(cmd: string) {
  if (cmd === 'data') exportTbSummary()
  else if (cmd === 'template') exportTbSumTemplate()
}

/** 导出空模板（只有行次+项目名称+空的未审数列） */
async function exportTbSumTemplate() {
  if (!tbSummaryRows.value.length) {
    ElMessage.warning('请先刷新加载行次结构')
    return
  }
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = ['行次', '项目', '未审数']
  const dataRows = tbSummaryRows.value.map((r: any) => [r.row_code, r.row_name, null])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = [{ wch: 12 }, { wch: 30 }, { wch: 16 }]
  XLSX.utils.book_append_sheet(wb, ws, '模板')
  const label = tbSummaryTypes.find(t => t.key === tbSummaryType.value)?.label || ''
  XLSX.writeFile(wb, `试算平衡表模板_${label}.xlsx`)
  ElMessage.success('模板已导出，填写未审数后导入')
}

/** 触发文件选择 */
function triggerTbSumImport() {
  tbSumImportInput.value?.click()
}

/** 导入 Excel 文件并按行次编码+名称双保险匹配覆盖未审数 */
async function onTbSumImportFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  // 重置 input 以便重复选同一文件
  if (tbSumImportInput.value) tbSumImportInput.value.value = ''

  const XLSX = await import('xlsx')
  const buf = await file.arrayBuffer()
  const workbook = XLSX.read(buf, { type: 'array' })
  const sheet = workbook.Sheets[workbook.SheetNames[0]]
  const rows: any[][] = XLSX.utils.sheet_to_json(sheet, { header: 1 })

  if (rows.length < 2) {
    ElMessage.warning('文件为空或格式不正确')
    return
  }

  // 解析表头找到列索引
  const headerRow = rows[0].map((h: any) => String(h || '').trim())
  const codeIdx = headerRow.findIndex((h: string) => h === '行次' || h === 'row_code')
  const nameIdx = headerRow.findIndex((h: string) => h === '项目' || h === 'row_name')
  const amtIdx = headerRow.findIndex((h: string) => h.includes('未审') || h === 'unadjusted')

  if (amtIdx < 0) {
    ElMessage.error('未找到"未审数"列，请检查模板格式')
    return
  }

  // 构建匹配索引
  const codeMap = new Map<string, any>()
  const nameMap = new Map<string, any>()
  for (const row of tbSummaryRows.value) {
    if (row.row_code) codeMap.set(row.row_code, row)
    if (row.row_name) nameMap.set(row.row_name.trim(), row)
  }

  let matched = 0
  let skipped = 0
  for (let i = 1; i < rows.length; i++) {
    const dataRow = rows[i]
    const code = codeIdx >= 0 ? String(dataRow[codeIdx] || '').trim() : ''
    const name = nameIdx >= 0 ? String(dataRow[nameIdx] || '').trim() : ''
    const amount = Number(dataRow[amtIdx])

    if (isNaN(amount) && !dataRow[amtIdx]) {
      skipped++
      continue
    }

    // 双保险匹配：优先行次编码，其次名称
    let target = code ? codeMap.get(code) : null
    if (!target && name) target = nameMap.get(name)

    if (target) {
      target.unadjusted = isNaN(amount) ? null : amount
      // 重算审定数
      target.audited = (target.unadjusted || 0) + (target.aje_dr || 0) - (target.aje_cr || 0) + (target.rcl_dr || 0) - (target.rcl_cr || 0)
      matched++
    } else {
      skipped++
    }
  }

  ElMessage.success(`导入完成：${matched} 行匹配成功${skipped ? `，${skipped} 行跳过` : ''}`)
  recalcTbSummaryAudited()
}
</script>

<style scoped>
  .gt-trial-balance { padding: var(--gt-space-5); }

  /* 折叠/展开按钮 */
  .gt-header-toggle {
    text-align: center;
    padding: 2px 0;
    cursor: pointer;
    font-size: 11px;
    color: #909399;
    border-bottom: 1px solid #f0edf5;
    margin-bottom: 6px;
    user-select: none;
    transition: color 0.15s;
  }
  .gt-header-toggle:hover { color: #4b2d77; }

  /* ── 金额列统一字体（Arial Narrow + tabular-nums + 不折行） ── */
  .gt-amt {
    font-family: 'Arial Narrow', Arial, sans-serif;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  :deep(.gt-amt-col) {
    font-family: 'Arial Narrow', Arial, sans-serif;
    font-variant-numeric: tabular-nums;
  }

  /* ── 表格字号由 displayPrefs 控制（Aa 按钮），通过 class 切换 ── */
  :deep(.gt-tb-font-xs),
  :deep(.gt-tb-font-xs) th .cell,
  :deep(.gt-tb-font-xs) td .cell,
  :deep(.gt-tb-font-xs) .el-table__body { font-size: 11px !important; }

  :deep(.gt-tb-font-sm),
  :deep(.gt-tb-font-sm) th .cell,
  :deep(.gt-tb-font-sm) td .cell,
  :deep(.gt-tb-font-sm) .el-table__body { font-size: 12px !important; }

  :deep(.gt-tb-font-md),
  :deep(.gt-tb-font-md) th .cell,
  :deep(.gt-tb-font-md) td .cell,
  :deep(.gt-tb-font-md) .el-table__body { font-size: 13px !important; }

  :deep(.gt-tb-font-lg),
  :deep(.gt-tb-font-lg) th .cell,
  :deep(.gt-tb-font-lg) td .cell,
  :deep(.gt-tb-font-lg) .el-table__body { font-size: 14px !important; }

  :deep(.el-table th .cell) {
    font-weight: 600;
    white-space: nowrap;
  }
  :deep(.el-table td .cell) {
    line-height: 1.4;
  }

  /* ── 科目明细表样式统一（与试算平衡表风格一致） ── */
  :deep(.el-table thead th) {
    background: #f0edf5 !important;
    color: #303133;
    border-bottom: 1px solid #e8e4f0 !important;
  }
  :deep(.el-table--border td) {
    border-color: #e8e4f0 !important;
  }
  :deep(.el-table--border th) {
    border-color: #e8e4f0 !important;
  }
  :deep(.el-table__row td) {
    padding: 4px 0;
  }

  /* ── GtPageHeader 已替换横幅样式 ── */

  .clickable {
    cursor: pointer; color: var(--gt-color-primary); font-weight: 500;
    transition: color var(--gt-transition-fast);
  }
  .clickable:hover { color: var(--gt-color-primary-light); text-decoration: underline; }
  .subtotal-val { font-weight: 700; }

  /* 方向列样式 */
  .gt-dir-debit { color: #303133; font-size: 11px; }
  .gt-dir-credit { color: #e6a23c; font-size: 11px; font-weight: 600; }
  .gt-dir-toggle { cursor: pointer; user-select: none; padding: 2px 6px; border-radius: 3px; }
  .gt-dir-toggle:hover { background: #f0edf5; }

  .gt-tb-balance-indicator {
    margin-top: var(--gt-space-4); text-align: right;
    font-size: var(--gt-font-size-base);
  }
  .gt-tb-balanced {
    color: var(--gt-color-success); font-weight: 600;
    padding: 6px 14px; border-radius: var(--gt-radius-full);
    background: var(--gt-color-success-light);
    display: inline-flex; align-items: center; gap: 4px;
  }
  .gt-tb-unbalanced {
    color: var(--gt-color-coral); font-weight: 600;
    padding: 6px 14px; border-radius: var(--gt-radius-full);
    background: var(--gt-color-coral-light);
    display: inline-flex; align-items: center; gap: 4px;
  }

  :deep(.subtotal-row) {
    background: linear-gradient(90deg, #f8f5fd, var(--gt-color-primary-bg)) !important;
    font-weight: 600;
  }
  :deep(.subtotal-row td) { border-bottom: 1px solid var(--gt-color-primary-lighter) !important; }
  :deep(.total-row) {
    background: linear-gradient(90deg, #ece4f5, #e8e0f0) !important;
    font-weight: 700;
  }
  :deep(.total-row td) { border-bottom: 2px solid var(--gt-color-primary-lighter) !important; }
  :deep(.highlight-row) {
    background: linear-gradient(90deg, #fffbf0, var(--gt-color-wheat-light)) !important;
  }
  :deep(.stale-row) {
    background: #fef9e7 !important;
    border-left: 3px solid #f0c040;
  }

  :deep(.el-tabs__item.is-active) { font-weight: 600; }

/* 视图切换标签 */

.gt-tb-view-tag {
  padding: 6px 16px; font-size: 13px; cursor: pointer; color: #999;
  border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.15s; user-select: none;
}
.gt-tb-view-tag:hover { color: #4b2d77; }
.gt-tb-view-tag--active { color: #4b2d77; font-weight: 600; border-bottom-color: #4b2d77; }

.gt-mapping-rule-btn {
  margin-left: 16px;
  border-color: #d9d2e8;
  color: #4b2d77;
  font-size: 12px;
}
.gt-mapping-rule-btn:hover {
  border-color: #4b2d77;
  background: #f8f5fd;
}

/* 试算平衡表 el-table 样式 */
:deep(.gt-tb-sum-unadj-col) { background: rgba(75,45,119,0.03); }
:deep(.gt-tb-sum-audited-col .cell) { font-weight: 700; color: #4b2d77; }
:deep(.gt-tb-sum-audited-col) { background: rgba(75,45,119,0.06); }
.gt-tb-editable { cursor: text; border-bottom: 1px dashed #e5e5ea; padding: 2px 4px; border-radius: 2px; display: inline-block; min-width: 60px; text-align: right; }
.gt-tb-editable:hover { background: #f4f0fa; }
.gt-tb-readonly { display: inline-block; min-width: 60px; text-align: right; padding: 2px 4px; color: #606266; }
:deep(.gt-tb-sum-total td) { font-weight: 700 !important; background: #f8f6fb !important; }
:deep(.gt-tb-sum-category td) { font-weight: 600 !important; color: #4b2d77 !important; }
:deep(.gt-tb-sum-selected td) { background: rgba(75, 45, 119, 0.14) !important; border-left: 3px solid #4b2d77 !important; }
:deep(.gt-tb-sum-selected td:first-child) { border-left: 3px solid #4b2d77 !important; }
:deep(.gt-tb-sum-selected td:not(:first-child)) { border-left: none !important; }

/* 试算平衡表 hover 效果 */
:deep(.el-table__body tr:hover > td) { background: rgba(75, 45, 119, 0.04) !important; }
:deep(.el-table__body tr.gt-tb-sum-selected:hover > td) { background: rgba(75, 45, 119, 0.16) !important; }

/* 试算平衡表右键菜单 */
.gt-tb-sum-ctx {
  position: fixed;
  z-index: 10001;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  padding: 6px 0;
  min-width: 160px;
}
.gt-ucell-ctx-divider { height: 1px; background: #e8e4f0; margin: 4px 8px; }
.gt-tb-detached-icon { font-size: 10px; margin-right: 2px; opacity: 0.7; }
:deep(.gt-tb-sum-detached td) { background: #fffdf5 !important; border-left: 2px solid #f0c040 !important; }

/* 步骤引导 */
.gt-setup-guide {
  padding: 24px 32px;
  background: #faf8fd;
  border: 1px solid #e8e0f0;
  border-radius: var(--gt-radius-lg, 8px);
  margin-bottom: 16px;
}
</style>


