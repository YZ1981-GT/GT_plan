<template>
  <div class="gt-wp-list gt-fade-in">
    <!-- 页面横幅 [R7-S3-01] -->
    <GtPageHeader :title="projectName ? `${projectName} — 底稿管理` : '底稿管理'" @back="$router.push('/projects')" variant="default">
      <template #actions>
        <GtToolbar :show-import="true" import-label="Excel导入" @import="showWpImport = true">
          <template #left>
            <div v-if="treeData.length > 0" class="gt-wp-view-toggle">
              <el-radio-group v-model="viewMode" size="small">
                <el-radio-button value="lifecycle">生命周期</el-radio-button>
                <el-radio-button value="matrix">委派矩阵</el-radio-button>
                <el-radio-button value="list">列表</el-radio-button>
                <el-radio-button value="workbench">工作台</el-radio-button>
                <el-radio-button value="kanban">看板</el-radio-button>
                <el-radio-button value="graph">依赖图</el-radio-button>
                <el-radio-button value="guide">手册</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <template #right>
            <el-button @click="fetchData" :loading="loading" size="small">刷新</el-button>
            <el-button type="primary" size="small" @click="onBatchDownload" :loading="downloadLoading">
              批量下载 ({{ selectedWpIds.length || '全部' }})
            </el-button>
            <el-button type="warning" size="small" :disabled="selectedWpIds.length === 0" @click="showBatchAssign = true">
              批量委派 ({{ selectedWpIds.length }})
            </el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- 归档横幅 -->
    <ArchivedBanner />

    <!-- Phase 2 F3: 批量状态变更操作栏 -->
    <BatchActionBar
      v-if="selectedWpIds.length > 0"
      :selected-count="selectedWpIds.length"
      :selected-ids="selectedWpIds"
      @batch-action="onBatchStatusChange"
    />

    <!-- 筛选栏（独立行，内容多不塞进 GtToolbar） -->
    <!-- 筛选栏：仅列表视图显示 -->
    <div v-if="viewMode === 'list' && (treeData.length > 0 || showTrimmedFilter === 'active')" class="gt-wp-filter-bar">
      <!-- 裁剪筛选切换 -->
      <el-checkbox
        v-model="showTrimmedChecked"
        size="default"
        :label="trimmedStatsLabel"
        border
      />
      <!-- Task 2.1: 角色视图切换 -->
      <ViewSwitcher
        v-model="roleViewPreset"
        :disabled="loading"
      />
      <el-input
        v-model="searchKeyword"
        placeholder="搜索底稿..."
        clearable
        size="default"
        style="width: 180px"
        @input="onSearchDebounce"
      />
      <el-select v-model="filterCycle" placeholder="审计循环" clearable size="default" style="width: 140px">
        <el-option v-for="c in cycleOptions" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="状态" clearable size="default" style="width: 110px">
        <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-select v-model="filterAssignee" placeholder="编制人" clearable size="default" style="width: 110px">
        <el-option label="全部" value="" />
        <el-option v-for="u in userOptions" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
      </el-select>
    </div>

    <!-- Task 2.4: 角色视图汇总统计面板 -->
    <div v-if="viewMode === 'list' && roleViewSummary" class="gt-wp-role-summary-panel">
      <span class="gt-wp-role-summary-label">{{ roleViewSummary.label }}：</span>
      <span v-for="item in roleViewSummary.items" :key="item.key" class="gt-wp-role-summary-item">
        {{ item.key }} <strong>{{ item.value }}</strong>
      </span>
    </div>

    <!-- 进度指示器（任务 7.2） -->
    <div v-if="wpList.length > 0 && viewMode === 'list'" class="gt-wp-progress-bar">
      <span>总体进度：{{ totalProgress.completed }}/{{ totalProgress.total }}</span>
      <el-progress :percentage="totalProgress.percent" :stroke-width="10" style="width: 200px; display: inline-block" />
      <span>{{ totalProgress.percent }}%</span>
      <template v-if="hasFilter">
        <el-divider direction="vertical" />
        <span>筛选结果：{{ filteredProgress.percent }}%（{{ filteredProgress.completed }}/{{ filteredProgress.total }}）</span>
      </template>
    </div>

    <!-- 主体：看板视图 / 列表视图 -->
    <WorkpaperKanban
      v-if="viewMode === 'kanban'"
      ref="kanbanRef"
      :project-id="projectId"
      :audit-cycle="filterCycle"
      style="flex: 1; min-height: 0"
      @select="onKanbanSelect"
      @assign="onKanbanAssign"
    />
    <!-- 工作台视图：按循环分组 + 进度追踪 + 批量操作 -->
    <div v-else-if="viewMode === 'workbench'" class="gt-wp-workbench-view">
      <!-- 循环进度卡片区（可折叠 + 点击筛选 + 快捷返回） -->
      <div class="gt-wpb-progress-header">
        <span class="gt-wpb-progress-header__title">循环进度概览</span>
        <span v-if="workbenchCycleFilter.length" class="gt-wpb-progress-header__filter-tag">
          筛选：{{ workbenchCycleFilter.map(c => cycleNameMap[c] || c).join('、') }}
          <span class="gt-wpb-progress-header__clear" @click="workbenchCycleFilter = []">✕</span>
        </span>
        <el-button size="small" text @click="workbenchProgressCollapsed = !workbenchProgressCollapsed">
          {{ workbenchProgressCollapsed ? '展开 ▼' : '收起 ▲' }}
        </el-button>
      </div>
      <div v-show="!workbenchProgressCollapsed" class="gt-wpb-progress-summary">
        <div class="gt-wpb-prog-card" v-for="cycle in cycleSummary" :key="cycle.code"
          :class="{ 'is-active': workbenchCycleFilter.includes(cycle.code) }"
          @click="onWorkbenchCycleClick(cycle.code)">
          <div class="gt-wpb-prog-card__header">
            <span class="gt-wpb-prog-card__code">{{ cycle.code }}</span>
            <span class="gt-wpb-prog-card__name">{{ cycle.name }}</span>
          </div>
          <el-progress :percentage="cycle.percent" :stroke-width="6" :color="cycle.percent === 100 ? '#67c23a' : '#4b2d77'" />
          <div class="gt-wpb-prog-card__detail">
            {{ cycle.completed }}/{{ cycle.total }} 完成
          </div>
        </div>
      </div>
      <div class="gt-wpb-workbench-list">
        <el-table :data="pagedWorkbenchData" stripe border style="width: 100%; font-size: 13px" max-height="calc(100vh - 320px)" @row-click="onWorkbenchRowClick">
          <el-table-column prop="wp_code" label="编码" min-width="90" sortable resizable />
          <el-table-column prop="wp_name" label="底稿名称" min-width="220" show-overflow-tooltip resizable />
          <el-table-column prop="cycle_name" label="循环" min-width="110" show-overflow-tooltip resizable />
          <el-table-column prop="status_label" label="状态" min-width="90" resizable>
            <template #default="{ row }">
              <el-tag :type="row.status_type" size="small">{{ row.status_label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="assignee_name" label="编制人" min-width="90" resizable />
          <el-table-column prop="step_progress" label="步骤进度" min-width="90" resizable>
            <template #default="{ row }">
              <span v-if="row.total_steps">{{ row.completed_steps || 0 }}/{{ row.total_steps }}</span>
              <span v-else class="gt-text-tertiary">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <GtRowActions
                :actions="getWpRowActions(row)"
                :max-visible="2"
                @action="(key: string) => handleWpRowAction(key, row)"
              />
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-pagination" v-if="wbTotal > wbPageSize" style="margin-top: 12px; display: flex; justify-content: flex-end;">
          <el-pagination
            v-model:current-page="wbPage"
            :page-size="wbPageSize"
            :total="wbTotal"
            layout="total, prev, pager, next"
            background
            small
          />
        </div>
      </div>
    </div>
    <!-- 生命周期视图：6 阶段流程导航 -->
    <WorkpaperLifecycleView
      v-else-if="viewMode === 'lifecycle'"
      :project-id="projectId"
      :workpapers="lifecycleWpItems"
      :loading="loading"
      style="flex: 1; min-height: 0"
      @switch-view="(v: string) => viewMode = v"
      @open-workpaper="onOpenWorkpaperById"
      @refresh="fetchData"
    />
    <!-- 依赖图视图：圆形布局可视化 -->
    <WorkpaperDependencyGraph
      v-else-if="viewMode === 'graph'"
      :project-id="projectId"
      style="flex: 1; min-height: 0"
      @navigate="onCycleNodeClick"
    />
    <!-- 委派矩阵视图：成员 × 循环网格 -->
    <WorkpaperAssignmentMatrix
      v-else-if="viewMode === 'matrix'"
      :project-id="projectId"
      :workpapers="lifecycleWpItems"
      :members="userOptions"
      style="flex: 1; min-height: 0"
      @cell-click="onMatrixCellClick"
      @assign="onMatrixAssign"
    />
    <!-- 用户手册视图：底稿体系说明 + 流程图 + 关系图 -->
    <div v-else-if="viewMode === 'guide'" class="gt-wp-guide-view">
      <div class="gt-wp-guide-view__nav">
        <el-button-group>
          <el-button :type="guideSection === 'overview' ? 'primary' : ''" size="small" @click="guideSection = 'overview'">体系总览</el-button>
          <el-button :type="guideSection === 'flow' ? 'primary' : ''" size="small" @click="guideSection = 'flow'">审计流程</el-button>
          <el-button :type="guideSection === 'relation' ? 'primary' : ''" size="small" @click="guideSection = 'relation'">底稿关系</el-button>
          <el-button :type="guideSection === 'cycles' ? 'primary' : ''" size="small" @click="guideSection = 'cycles'">循环详解</el-button>
        </el-button-group>
        <el-button v-if="guideBreadcrumb.length > 1" size="small" text @click="guideGoBack">
          ← 返回{{ guideBreadcrumb[guideBreadcrumb.length - 2] }}
        </el-button>
      </div>

      <!-- 体系总览 -->
      <div v-if="guideSection === 'overview'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">底稿体系总览</h3>
        <p class="gt-wp-guide-section__desc">审计底稿按审计循环组织，每个循环包含多个底稿程序，覆盖从风险评估到完成阶段的全流程。</p>
        <div class="gt-wp-guide-overview-grid">
          <div class="gt-wp-guide-overview-card" v-for="cycle in guideOverviewData" :key="cycle.code"
            @click="guideJumpToCycle(cycle.code)">
            <div class="gt-wp-guide-overview-card__badge" :style="{ background: cycle.color }">{{ cycle.code }}</div>
            <div class="gt-wp-guide-overview-card__info">
              <div class="gt-wp-guide-overview-card__name">{{ cycle.name }}</div>
              <div class="gt-wp-guide-overview-card__meta">{{ cycle.count }} 个底稿 · {{ cycle.desc }}</div>
            </div>
            <span class="gt-wp-guide-overview-card__arrow">›</span>
          </div>
        </div>
        <div class="gt-wp-guide-legend">
          <span class="gt-wp-guide-legend__item"><span class="gt-wp-guide-legend__dot" style="background:#6750A4"></span>风险评估与控制</span>
          <span class="gt-wp-guide-legend__item"><span class="gt-wp-guide-legend__dot" style="background:#E8590C"></span>实质性程序</span>
          <span class="gt-wp-guide-legend__item"><span class="gt-wp-guide-legend__dot" style="background:#2E7D32"></span>完成与专项</span>
        </div>
      </div>

      <!-- 审计流程 -->
      <div v-if="guideSection === 'flow'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">风险导向审计流程</h3>
        <p class="gt-wp-guide-section__desc">现代审计采用风险导向方法：先识别风险，再针对性设计审计程序。每个阶段的结论直接影响下一阶段的范围和深度。</p>

        <!-- 流程图 -->
        <div class="gt-wp-guide-flow-chart">
          <div class="gt-wp-guide-flow-step" v-for="(step, idx) in guideFlowSteps" :key="step.id">
            <div class="gt-wp-guide-flow-step__node" :style="{ borderColor: step.color }">
              <div class="gt-wp-guide-flow-step__icon">{{ step.icon }}</div>
              <div class="gt-wp-guide-flow-step__label">{{ step.label }}</div>
              <div class="gt-wp-guide-flow-step__sub">{{ step.sub }}</div>
            </div>
            <div v-if="idx < guideFlowSteps.length - 1" class="gt-wp-guide-flow-step__arrow">
              <span class="gt-wp-guide-flow-arrow-text">{{ step.nextStageLink ? '▸' : '' }}</span>
              <span>→</span>
            </div>
          </div>
        </div>

        <!-- 各阶段详解 -->
        <div class="gt-wp-guide-flow-detail">
          <div class="gt-wp-guide-flow-detail__item" v-for="step in guideFlowSteps" :key="step.id">
            <div class="gt-wp-guide-flow-detail__header">
              <span class="gt-wp-guide-flow-detail__badge" :style="{ background: step.color }">{{ step.icon }}</span>
              <span class="gt-wp-guide-flow-detail__name">{{ step.label }}</span>
              <span class="gt-wp-guide-flow-detail__sub-tag">{{ step.sub }}</span>
            </div>

            <!-- 风险导向要点 -->
            <div class="gt-wp-guide-flow-risk">
              <span class="gt-wp-guide-flow-risk__icon">⚡</span>
              <span class="gt-wp-guide-flow-risk__text">风险导向要点：{{ step.riskFocus }}</span>
            </div>

            <div class="gt-wp-guide-flow-detail__desc">{{ step.detail }}</div>

            <!-- 关键工作 -->
            <div class="gt-wp-guide-flow-actions">
              <div class="gt-wp-guide-flow-actions__title">关键工作：</div>
              <div class="gt-wp-guide-flow-actions__list">
                <div v-for="(action, ai) in step.keyActions" :key="ai" class="gt-wp-guide-flow-actions__item">
                  <span class="gt-wp-guide-flow-actions__bullet">{{ ai + 1 }}</span>
                  <span>{{ action }}</span>
                </div>
              </div>
            </div>

            <!-- 关联底稿 -->
            <div class="gt-wp-guide-flow-wps">
              <div class="gt-wp-guide-flow-wps__title">📎 关联底稿：</div>
              <div class="gt-wp-guide-flow-wps__list">
                <div v-for="wp in step.wpLinks" :key="wp.code" class="gt-wp-guide-flow-wps__item"
                  @click="onGuideWpClick(wp.code)">
                  <span class="gt-wp-guide-flow-wps__code">{{ wp.code }}</span>
                  <span class="gt-wp-guide-flow-wps__name">{{ wp.name }}</span>
                  <span class="gt-wp-guide-flow-wps__rel">{{ wp.relation }}</span>
                </div>
              </div>
            </div>

            <!-- 产出循环 -->
            <div class="gt-wp-guide-flow-detail__outputs">
              产出循环：<span v-for="o in step.outputs" :key="o" class="gt-wp-guide-flow-detail__output-tag"
                @click="guideJumpToCycle(o)">{{ o }}</span>
            </div>

            <!-- 阶段衔接 -->
            <div v-if="step.nextStageLink" class="gt-wp-guide-flow-next">
              ➡️ {{ step.nextStageLink }}
            </div>
          </div>
        </div>
      </div>

      <!-- 底稿关系 -->
      <div v-if="guideSection === 'relation'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">底稿与报表、附注的数据关系</h3>
        <p class="gt-wp-guide-section__desc">审计工作产出物之间存在严密的数据流转关系，理解这些关系是高效完成审计的基础。</p>

        <!-- 数据流转主线 -->
        <div class="gt-wp-guide-dataflow">
          <div class="gt-wp-guide-dataflow__title">📐 数据流转主线</div>
          <div class="gt-wp-guide-dataflow__chain">
            <div v-for="(step, idx) in guideDataFlowPaths" :key="idx" class="gt-wp-guide-dataflow__step">
              <div class="gt-wp-guide-dataflow__node">
                <span class="gt-wp-guide-dataflow__icon">{{ step.icon }}</span>
                <span class="gt-wp-guide-dataflow__name">{{ step.to }}</span>
              </div>
              <div v-if="idx < guideDataFlowPaths.length - 1" class="gt-wp-guide-dataflow__arrow">
                <span class="gt-wp-guide-dataflow__arrow-label">{{ guideDataFlowPaths[idx + 1]?.label }}</span>
                <span class="gt-wp-guide-dataflow__arrow-icon">→</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 模块关系详解 -->
        <div class="gt-wp-guide-modules">
          <div class="gt-wp-guide-modules__title">🔗 模块间关系详解</div>
          <div class="gt-wp-guide-modules__grid">
            <div v-for="rel in guideFullRelations" :key="rel.id" class="gt-wp-guide-module-card">
              <div class="gt-wp-guide-module-card__header">
                <span class="gt-wp-guide-module-card__icon" :style="{ background: rel.color }">{{ rel.icon }}</span>
                <span class="gt-wp-guide-module-card__name">{{ rel.name }}</span>
              </div>
              <div class="gt-wp-guide-module-card__desc">{{ rel.desc }}</div>
              <div class="gt-wp-guide-module-card__connections">
                <div v-for="(conn, ci) in rel.connections" :key="ci" class="gt-wp-guide-module-card__conn">
                  <span class="gt-wp-guide-module-card__conn-dir" :class="conn.direction === 'out' ? 'is-out' : 'is-in'">
                    {{ conn.direction === 'out' ? '→' : '←' }}
                  </span>
                  <span class="gt-wp-guide-module-card__conn-to">{{ conn.to }}</span>
                  <span class="gt-wp-guide-module-card__conn-label">{{ conn.label }}</span>
                  <span class="gt-wp-guide-module-card__conn-style" :class="conn.style === 'solid' ? 'is-auto' : 'is-manual'">
                    {{ conn.style === 'solid' ? '自动' : '引用' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 关键说明 -->
        <div class="gt-wp-guide-relation-notes">
          <div class="gt-wp-guide-relation-notes__title">💡 关键说明</div>
          <div class="gt-wp-guide-relation-notes__list">
            <div class="gt-wp-guide-relation-notes__item">
              <strong>试算表 → 报表</strong>：审定数按科目映射规则自动汇总到报表行，映射关系在「试算表 → 映射规则」中配置
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>报表 → 附注</strong>：附注各章节引用报表对应行的金额，报表数据变动时附注自动同步
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>底稿 → 调整分录</strong>：各循环底稿发现的错报通过 AJE/RJE 反映，调整分录更新试算表后报表自动重算
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>底稿 → 附注</strong>：部分附注数据（如固定资产变动表、借款明细）直接引用底稿中的分析结果
            </div>
            <div class="gt-wp-guide-relation-notes__item">
              <strong>闭环验证</strong>：报表金额 = 试算表审定数汇总 = 未审数 + AJE + RJE，系统自动校验一致性
            </div>
          </div>
        </div>

        <div class="gt-wp-guide-relation-legend">
          <div class="gt-wp-guide-relation-legend__item">
            <span class="gt-wp-guide-relation-legend__dot" style="background: var(--gt-color-primary)"></span>
            <span>自动取数（系统联动）</span>
          </div>
          <div class="gt-wp-guide-relation-legend__item">
            <span class="gt-wp-guide-relation-legend__dot" style="background: var(--gt-color-text-tertiary)"></span>
            <span>交叉引用（人工核对）</span>
          </div>
        </div>
      </div>

      <!-- 循环详解 -->
      <div v-if="guideSection === 'cycles'" class="gt-wp-guide-section">
        <h3 class="gt-wp-guide-section__title">审计循环详解</h3>
        <p class="gt-wp-guide-section__desc">点击循环卡片查看核心底稿、工作内容和关联关系。</p>
        <div class="gt-wp-guide-cycles-grid">
          <div class="gt-wp-guide-cycle-card" v-for="cycle in guideCycleDetails" :key="cycle.code"
            :class="{ 'is-active': guideFocusCycle === cycle.code }"
            @click="guideFocusCycle = guideFocusCycle === cycle.code ? '' : cycle.code">
            <div class="gt-wp-guide-cycle-card__header">
              <span class="gt-wp-guide-cycle-card__badge" :style="{ background: cycle.color }">{{ cycle.code }}</span>
              <span class="gt-wp-guide-cycle-card__name">{{ cycle.name }}</span>
              <span class="gt-wp-guide-cycle-card__count">{{ cycle.wps.length }} 个底稿</span>
            </div>
            <div v-if="guideFocusCycle === cycle.code" class="gt-wp-guide-cycle-card__body">
              <div class="gt-wp-guide-cycle-card__desc">{{ cycle.desc }}</div>

              <!-- 核心底稿 -->
              <div v-if="cycle.coreWps?.length" class="gt-wp-guide-cycle-core">
                <div class="gt-wp-guide-cycle-core__title">📌 核心底稿</div>
                <div class="gt-wp-guide-cycle-core__list">
                  <div v-for="cw in cycle.coreWps" :key="cw.code" class="gt-wp-guide-cycle-core__item"
                    @click.stop="onGuideWpClick(cw.code)">
                    <div class="gt-wp-guide-cycle-core__item-header">
                      <span class="gt-wp-guide-cycle-core__code">{{ cw.code }}</span>
                      <span class="gt-wp-guide-cycle-core__name">{{ cw.name }}</span>
                      <el-tag size="small" :type="cw.role === '总控台' ? 'danger' : cw.role === '核心' ? 'warning' : 'info'">{{ cw.role }}</el-tag>
                    </div>
                    <div class="gt-wp-guide-cycle-core__detail">{{ cw.detail }}</div>
                  </div>
                </div>
              </div>

              <!-- 关联循环 -->
              <div v-if="cycle.relatedTo?.length" class="gt-wp-guide-cycle-rel">
                <div class="gt-wp-guide-cycle-rel__title">🔗 关联循环</div>
                <div class="gt-wp-guide-cycle-rel__desc">{{ cycle.relDesc }}</div>
                <div class="gt-wp-guide-cycle-rel__tags">
                  <span v-for="r in cycle.relatedTo" :key="r" class="gt-wp-guide-cycle-rel__tag"
                    @click.stop="guideFocusCycle = r">{{ r }} {{ guideOverviewData.find(g => g.code === r)?.name }}</span>
                </div>
              </div>

              <!-- 完整底稿清单 -->
              <div v-if="cycle.wps.length" class="gt-wp-guide-cycle-wplist">
                <div class="gt-wp-guide-cycle-wplist__title">📋 完整底稿清单（{{ cycle.wps.length }}）</div>
                <div class="gt-wp-guide-cycle-card__wp-list">
                  <div v-for="wp in cycle.wps" :key="wp.code" class="gt-wp-guide-cycle-card__wp-item"
                    @click.stop="onGuideWpClick(wp.code)">
                    <span class="gt-wp-guide-cycle-card__wp-code">{{ wp.code }}</span>
                    <span class="gt-wp-guide-cycle-card__wp-name">{{ wp.name }}</span>
                    <span class="gt-wp-guide-cycle-card__wp-arrow">→</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 无底稿时：两栏布局（左操作入口 + 右审计程序总览） -->
    <div v-else-if="!loading && treeData.length === 0" class="gt-wp-intro-layout">
      <!-- 左栏：操作入口 -->
      <div class="gt-wp-intro-half">
        <div class="gt-wp-intro-icon">📋</div>
        <div class="gt-wp-intro-title">暂无底稿</div>
        <div class="gt-wp-intro-desc">
          <span v-if="hasTrialBalance">检测到试算表已就绪，建议一键生成底稿+附注</span>
          <span v-else>请先完成账套导入和试算表生成</span>
        </div>
        <!-- F2 修复 / v3 P0-5 / Q4：检测到 tb 已就绪但 wp=0 时显示一键生成 -->
        <el-button
          v-if="hasTrialBalance"
          type="primary"
          :loading="chainLoading"
          @click="onGenerateChain"
          style="margin-top: 20px"
        >
          🚀 一键生成底稿+附注（chain）
        </el-button>
        <el-button
          @click="goToWorkbench"
          style="margin-top: 12px"
        >前往底稿工作台</el-button>
      </div>

      <!-- 右栏：审计程序总览（简洁列表，点击跳转） -->
      <div class="gt-wp-intro-half gt-wp-intro-half--guide">
        <h3 class="gt-wp-guide-title">审计程序与底稿体系</h3>
        <div class="gt-wp-guide-flow">
          <span class="gt-wp-flow-tag" style="background: var(--gt-color-primary)">B 风险评估</span>
          <span class="gt-wp-flow-arrow">→</span>
          <span class="gt-wp-flow-tag" style="background: var(--gt-color-primary-dark)">C 控制测试</span>
          <span class="gt-wp-flow-arrow">→</span>
          <span class="gt-wp-flow-tag" style="background: var(--gt-color-coral)">D-N 实质性程序</span>
          <span class="gt-wp-flow-arrow">→</span>
          <span class="gt-wp-flow-tag" style="background: var(--gt-color-success)">A 完成阶段</span>
          <span class="gt-wp-flow-tag" style="background: var(--gt-color-text-tertiary); margin-left: 4px">S 特定项目</span>
        </div>
        <div class="gt-wp-guide-list">
          <div
            v-for="g in auditCycleGuide" :key="g.cycle"
            class="gt-wp-guide-row"
            @click="onGuideClick(g.cycle)"
          >
            <span class="gt-wp-guide-badge" :style="{ background: g.color }">{{ g.cycle }}</span>
            <span class="gt-wp-guide-name">{{ g.name }}</span>
            <span class="gt-wp-guide-count">{{ g.count }} 个底稿</span>
            <span class="gt-wp-guide-arrow">›</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-else-if="loading" class="gt-wp-empty-full">
      <el-icon class="is-loading" style="font-size: var(--gt-font-size-3xl); color: var(--gt-color-primary)"><Loading /></el-icon>
      <div style="margin-top: 12px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary)">加载中...</div>
    </div>

    <!-- 有数据时：左右分栏 -->
    <div v-else class="gt-wp-body">
      <!-- 左侧索引树 -->
      <div class="gt-wp-tree-panel">
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          highlight-current
          show-checkbox
          @check-change="onCheckChange"
          @node-click="onNodeClick"
          @node-contextmenu="onWpNodeContextMenu"
          ref="treeRef"
        >
          <template #default="{ data }">
            <div class="gt-wp-tree-node" :class="{ 'is-trimmed': data.isTrimmed }" :style="getTreeNodeHighlightStyle(data)">
              <span class="gt-wp-tree-node-label">{{ data.label }}</span>
              <el-tag v-if="data.isTrimmed" size="small" type="info" class="gt-wp-tree-node-trim-tag">已裁剪</el-tag>
              <!-- Task 2.3: 助理视图前置依赖警告图标 -->
              <el-tooltip
                v-if="getTreeNodeHighlight(data)?.tooltip"
                :content="getTreeNodeHighlight(data)?.tooltip"
                placement="top"
              >
                <span class="gt-wp-tree-node-warn">⚠️</span>
              </el-tooltip>
              <!-- Task 2.3: 合伙人视图复核意见 badge -->
              <el-badge
                v-if="getTreeNodeBadge(data)?.visible"
                :value="getTreeNodeBadge(data)?.value"
                :type="getTreeNodeBadge(data)?.type"
                class="gt-wp-tree-node-badge"
              />
              <!-- Task 2.3: 质控视图复核标记 -->
              <span v-if="roleViewPreset === 'qc' && data.wpId" class="gt-wp-tree-node-review-mark">
                {{ getQcReviewMark(data) }}
              </span>
              <GtStatusTag v-if="data.status" dict-key="wp_status" :value="data.status" class="gt-wp-tree-node-tag" />
              <!-- Sprint 4：StaleIndicator 统一组件 -->
              <StaleIndicator
                v-if="data.id && staleWpIdSet.has(data.id)"
                :stale="true"
                tooltip="底稿已过期，建议重新生成"
                size="small"
              />
              <!-- Foundation Task 2.9: 循环级复核状态徽章（仅 group 节点） -->
              <el-tag
                v-if="data.cycleCode && data.totalCount !== undefined"
                :type="data.reviewedCount === data.totalCount && data.totalCount > 0 ? 'success' : (data.reviewedCount > 0 ? 'warning' : 'info')"
                size="small"
                class="gt-wp-tree-cycle-badge"
                @click.stop="onCycleBadgeClick(data)"
              >
                {{ data.reviewedCount === data.totalCount && data.totalCount > 0
                  ? `✓ 全部完成 (${data.totalCount})`
                  : `${data.reviewedCount}/${data.totalCount} 已复核` }}
              </el-tag>
            </div>
          </template>
        </el-tree>

        <!-- 底稿右键菜单 [enterprise-linkage 3.10] -->
        <div
          v-if="wpCtxVisible"
          class="gt-tb-sum-ctx"
          :style="{ left: wpCtxX + 'px', top: wpCtxY + 'px' }"
          @contextmenu.prevent
        >
          <div class="gt-ucell-ctx-item" @click="onWpCtxTraceToTb">
            <span class="gt-ucell-ctx-icon">🔍</span> 溯源到试算表
          </div>
        </div>
      </div>

      <!-- 右侧详情面板 -->
      <div class="gt-wp-detail-panel">
        <template v-if="selectedWp">
          <!-- useWpDetailGuard 三态提示 -->
          <div v-if="wpDetailGuard.loading.value" class="gt-wp-detail-guard-hint gt-wp-detail-guard-hint--loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>正在校验底稿状态...</span>
          </div>
          <div v-else-if="wpDetailGuard.state.value === 'invalid_id'" class="gt-wp-detail-guard-hint gt-wp-detail-guard-hint--error">
            <el-icon><WarningFilled /></el-icon>
            <span>无效底稿 ID</span>
          </div>
          <div v-else-if="wpDetailGuard.state.value === 'no_index' || wpDetailGuard.state.value === 'no_file'" class="gt-wp-detail-guard-hint gt-wp-detail-guard-hint--warning">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ wpDetailGuard.errorMessage.value }}</span>
            <el-button size="small" type="primary" @click="goToLifecycle">前往生命周期</el-button>
          </div>
          <div v-else-if="wpDetailGuard.state.value === 'error'" class="gt-wp-detail-guard-hint gt-wp-detail-guard-hint--error">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ wpDetailGuard.errorMessage.value }}</span>
            <el-button size="small" @click="wpDetailGuard.refresh()">重试</el-button>
          </div>
          <div class="gt-wp-detail-card">
            <h3 class="gt-wp-detail-title">{{ selectedWp.wp_code }} {{ selectedWp.wp_name }}</h3>
            <el-descriptions :column="2" border size="default">
              <el-descriptions-item label="底稿编号">{{ selectedWp.wp_code }}</el-descriptions-item>
              <el-descriptions-item label="底稿名称">{{ selectedWp.wp_name }}</el-descriptions-item>
              <el-descriptions-item label="审计循环">{{ selectedWp.audit_cycle || '-' }}</el-descriptions-item>
              <el-descriptions-item label="编制状态">
                <GtStatusTag dict-key="wp_status" :value="selectedWp.status" />
              </el-descriptions-item>
              <el-descriptions-item label="复核状态">
                <GtStatusTag dict-key="wp_review_status" :value="selectedWp.review_status" />
              </el-descriptions-item>
              <el-descriptions-item label="编制人">{{ resolveUserName(selectedWp.assigned_to) }}</el-descriptions-item>
              <el-descriptions-item label="复核人">{{ resolveUserName(selectedWp.reviewer) }}</el-descriptions-item>
              <el-descriptions-item label="文件版本">v{{ selectedWp.file_version || 1 }}</el-descriptions-item>
              <el-descriptions-item label="最后解析">{{ selectedWp.last_parsed_at?.slice(0, 19) || '-' }}</el-descriptions-item>
            </el-descriptions>

            <!-- 操作按钮：在线优先+离线兜底双模式 -->
            <div class="gt-wp-detail-actions">
              <el-button-group>
                <el-button type="primary" @click="onOnlineEdit">
                  <el-icon style="margin-right:4px"><Monitor /></el-icon>
                  在线编辑
                </el-button>
                <el-button @click="onDownload">
                  <el-icon style="margin-right:4px"><Download /></el-icon>下载编辑
                </el-button>
              </el-button-group>
              <el-button @click="onUpload">上传</el-button>
              <el-button type="warning" @click="onQCCheck" :loading="qcLoading">自检</el-button>
              <el-tooltip :disabled="!hasBlocking" :content="blockingReasons.join('；')" placement="top">
                <el-button type="success" @click="onSubmitReview" :disabled="!canEdit || hasBlocking || submitLoading" :loading="submitLoading" :title="!canEdit ? '项目已归档，无法编辑' : ''">提交复核</el-button>
              </el-tooltip>
            </div>

            <!-- Phase 14: 门禁阻断面板 -->
            <GateBlockPanel
              :state="gateState"
              :hit-rules="gateHitRules"
              :trace-id="gateTraceId"
              @jump="handleGateJump"
            />

            <!-- Phase 14: SoD 冲突弹窗 -->
            <SoDConflictDialog
              v-model="showSodDialog"
              :conflict-type="sodConflictType"
              :policy-code="sodPolicyCode"
              :trace-id="sodTraceId"
            />

            <!-- QC 结果摘要 -->
            <div v-if="qcResult" class="gt-wp-qc-summary-inline">
              <el-tag :type="qcResult.passed ? 'success' : 'danger'" size="small">
                {{ qcResult.passed ? '自检通过' : '存在问题' }}
              </el-tag>
              <span class="gt-wp-qc-counts">
                阻断 {{ qcResult.blocking_count }} / 警告 {{ qcResult.warning_count }} / 提示 {{ qcResult.info_count }}
              </span>
            </div>

            <!-- 精细化审计检查结果 -->
            <div v-if="fineCheckResults.length" class="gt-wp-fine-checks" style="margin-top: 12px">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                <span style="font-size: var(--gt-font-size-sm);font-weight:600;color: var(--gt-color-text-primary)">审计检查</span>
                <el-tag size="small" :type="fineChecksPassed ? 'success' : 'warning'">
                  {{ fineChecksPassedCount }}/{{ fineCheckResults.length }} 通过
                </el-tag>
                <el-button size="small" text @click="loadFineChecks" :loading="fineChecksLoading">刷新</el-button>
              </div>
              <div v-for="chk in fineCheckResults" :key="chk.code" class="gt-fine-check-item"
                :class="{ 'gt-fine-check-pass': chk.passed === true, 'gt-fine-check-fail': chk.passed === false, 'gt-fine-check-pending': chk.passed === null }">
                <span class="gt-fine-check-code">{{ chk.code }}</span>
                <span class="gt-fine-check-desc">{{ chk.description }}</span>
                <span v-if="chk.passed === true" class="gt-fine-check-status">✓</span>
                <span v-else-if="chk.passed === false" class="gt-fine-check-status" style="color: var(--gt-color-wheat)">
                  ✗ {{ chk.message }}
                  <el-button size="small" text type="primary" style="margin-left:4px;font-size: var(--gt-font-size-xs)" @click="onCheckJump(chk)">定位</el-button>
                </span>
                <span v-else class="gt-fine-check-status" style="color: var(--gt-color-text-tertiary)">待验证</span>
              </div>
            </div>

            <!-- 复核人操作区：仅在底稿处于待复核状态时显示 -->
            <div v-if="isReviewable" class="gt-wp-reviewer-actions" style="margin-top: 16px">
              <h4 style="margin: 0 0 8px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text)">复核操作</h4>

              <!-- TSJ复核提示词清单 -->
              <div v-if="tsjReviewData" class="gt-tsj-review-panel" style="margin-bottom: 12px">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                  <span style="font-size: var(--gt-font-size-xs);font-weight:600;color: var(--gt-color-primary)">📋 复核要点（{{ tsjReviewData.account_name }}）</span>
                  <el-button size="small" text @click="showTsjDetail = !showTsjDetail">{{ showTsjDetail ? '收起' : '展开' }}</el-button>
                </div>
                <!-- 风险领域 -->
                <div v-if="tsjReviewData.risk_areas?.length" style="margin-bottom:6px">
                  <div v-for="(area, i) in tsjReviewData.risk_areas.slice(0, showTsjDetail ? 99 : 3)" :key="i"
                    style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);padding:2px 0">
                    <el-tag :type="area.includes('高风险') ? 'danger' : area.includes('中风险') ? 'warning' : 'info'" size="small" style="margin-right:4px">
                      {{ area.includes('高风险') ? '高' : area.includes('中风险') ? '中' : '低' }}
                    </el-tag>
                    {{ area }}
                  </div>
                </div>
                <!-- 复核清单 -->
                <div v-if="showTsjDetail && tsjReviewData.checklist?.length" style="margin-top:8px">
                  <div style="font-size: var(--gt-font-size-xs);font-weight:600;color: var(--gt-color-text-primary);margin-bottom:4px">复核清单：</div>
                  <div v-for="(item, i) in tsjReviewData.checklist" :key="i"
                    style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-regular);padding:1px 0;display:flex;align-items:flex-start;gap:4px">
                    <el-checkbox size="small" style="flex-shrink:0" />
                    <span>{{ item }}</span>
                  </div>
                </div>
              </div>

              <div style="display: flex; gap: 8px; flex-wrap: wrap">
                <el-button type="success" @click="onReviewPass">
                  {{ selectedWp?.review_status === 'pending_level2' ? '二级复核通过' : '一级复核通过' }}
                </el-button>
                <el-button type="warning" @click="onRejectClick">退回修改</el-button>
              </div>
            </div>

            <!-- 退回底稿弹窗 -->
            <el-dialog v-model="showRejectDialog" title="退回底稿" width="450px" append-to-body>
              <el-input v-model="rejectReason" type="textarea" :rows="3"
                placeholder="请填写退回原因（必填）" />
              <template #footer>
                <el-button @click="showRejectDialog = false">取消</el-button>
                <el-button type="warning" @click="onConfirmReject" :disabled="!rejectReason.trim()">
                  确认退回
                </el-button>
              </template>
            </el-dialog>

            <!-- 复核批注面板 -->
            <div class="gt-wp-review-section" style="margin-top: 16px">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
                <h4 style="margin: 0; font-size: var(--gt-font-size-sm); color: var(--gt-color-text)">
                  复核意见
                  <el-badge v-if="unresolvedCount > 0" :value="unresolvedCount" type="danger" style="margin-left: 8px" />
                </h4>
                <div style="display:flex;gap:6px">
                  <el-button size="small" @click="goToConversation" title="发起复核对话（支持多轮讨论）">💬 对话</el-button>
                  <el-button size="small" type="primary" @click="showAddAnnotation = true" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">新增意见</el-button>
                </div>
              </div>
              <!-- 意见筛选 -->
              <div v-if="annotations.length > 3" style="margin-bottom:6px">
                <el-radio-group v-model="annotationFilter" size="small">
                  <el-radio-button value="">全部 ({{ annotations.length }})</el-radio-button>
                  <el-radio-button value="open">待处理 ({{ annotations.filter(a => a.status === 'open').length }})</el-radio-button>
                  <el-radio-button value="replied">已回复 ({{ annotations.filter(a => a.status === 'replied').length }})</el-radio-button>
                  <el-radio-button value="resolved">已解决 ({{ annotations.filter(a => a.status === 'resolved').length }})</el-radio-button>
                </el-radio-group>
              </div>
              <el-table v-if="filteredAnnotations.length" :data="filteredAnnotations" size="small" stripe max-height="250"
                :row-class-name="annotationRowClass">
                <el-table-column prop="content" label="内容" min-width="200">
                  <template #default="{ row }">
                    <div>
                      <span style="font-size: var(--gt-font-size-xs)">{{ row.content }}</span>
                      <div v-if="row.reply_content" style="margin-top:4px;padding:4px 8px;background: var(--gt-bg-success);border-radius:4px;font-size: var(--gt-font-size-xs);color: var(--gt-color-success)">
                        ↳ 回复：{{ row.reply_content }}
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="priority" label="优先级" width="60">
                  <template #default="{ row }">
                    <el-tag :type="row.priority === 'high' ? 'danger' : row.priority === 'medium' ? 'warning' : 'info'" size="small">
                      {{ row.priority === 'high' ? '高' : row.priority === 'medium' ? '中' : '低' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="70">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'resolved' ? 'success' : row.status === 'replied' ? 'warning' : 'danger'" size="small">
                      {{ row.status === 'resolved' ? '已解决' : row.status === 'replied' ? '已回复' : '待处理' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="时间" width="70">
                  <template #default="{ row }">
                    <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">{{ row.created_at?.slice(5, 16) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="120">
                  <template #default="{ row }">
                    <el-button v-if="row.status === 'open'" size="small" text type="primary" @click="replyAnnotation(row)">回复</el-button>
                    <el-button v-if="row.status !== 'resolved'" size="small" text type="success" @click="resolveAnnotation(row.id)">解决</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="暂无复核意见" :image-size="40" />
            </div>

            <!-- 新增意见弹窗 -->
            <el-dialog append-to-body v-model="showAddAnnotation" title="新增复核意见" width="400px">
              <el-form ref="annoFormRef" :model="newAnnotation" :rules="annoRules" label-width="60px">
                <el-form-item label="内容" prop="content">
                  <el-input v-model="newAnnotation.content" type="textarea" :rows="3" placeholder="输入复核意见" />
                </el-form-item>
                <el-form-item label="优先级">
                  <el-radio-group v-model="newAnnotation.priority">
                    <el-radio value="high">高</el-radio>
                    <el-radio value="medium">中</el-radio>
                    <el-radio value="low">低</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-form>
              <template #footer>
                <el-button @click="showAddAnnotation = false">取消</el-button>
                <el-button type="primary" @click="submitAnnotation" :disabled="!canEdit || !newAnnotation.content" :title="!canEdit ? '项目已归档，无法编辑' : ''">提交</el-button>
              </template>
            </el-dialog>
          </div>
        </template>
        <!-- 右侧空态引导 -->
        <div v-else class="gt-wp-empty-guide">
          <div class="gt-wp-empty-guide__header">
            <el-icon :size="36" color="var(--gt-color-primary)" style="opacity: 0.5"><FolderOpened /></el-icon>
            <div class="gt-wp-empty-guide__title">选择底稿查看详情</div>
            <div class="gt-wp-empty-guide__desc">点击左侧底稿名称查看详情并编辑</div>
          </div>
          <div class="gt-wp-empty-guide__body">
            <div class="gt-wp-empty-guide__stats" v-if="totalProgress.total > 0">
              <div class="gt-wp-empty-guide__stat-item">
                <span class="gt-wp-empty-guide__stat-num">{{ totalProgress.total }}</span>
                <span class="gt-wp-empty-guide__stat-label">底稿总数</span>
              </div>
              <div class="gt-wp-empty-guide__stat-divider"></div>
              <div class="gt-wp-empty-guide__stat-item">
                <span class="gt-wp-empty-guide__stat-num" :style="{ color: totalProgress.completed > 0 ? 'var(--gt-color-success)' : 'var(--gt-color-text-tertiary)' }">{{ totalProgress.completed }}</span>
                <span class="gt-wp-empty-guide__stat-label">已完成</span>
              </div>
              <div class="gt-wp-empty-guide__stat-divider"></div>
              <div class="gt-wp-empty-guide__stat-item">
                <span class="gt-wp-empty-guide__stat-num" :style="{ color: (totalProgress.total - totalProgress.completed) > 0 ? 'var(--gt-color-warning)' : 'var(--gt-color-text-tertiary)' }">{{ totalProgress.total - totalProgress.completed }}</span>
                <span class="gt-wp-empty-guide__stat-label">进行中</span>
              </div>
            </div>
            <div class="gt-wp-empty-guide__tips">
              <div class="gt-wp-empty-guide__tip"><span class="gt-wp-empty-guide__tip-icon">💡</span>双击底稿可直接进入在线编辑</div>
              <div class="gt-wp-empty-guide__tip"><span class="gt-wp-empty-guide__tip-icon">🔍</span>使用顶部筛选栏快速定位底稿</div>
              <div class="gt-wp-empty-guide__tip"><span class="gt-wp-empty-guide__tip-icon">☑️</span>勾选多个底稿可批量下载或委派</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传弹窗（两步：上传文件 → 确认识别数据） -->
    <el-dialog append-to-body v-model="uploadDialogVisible" :title="uploadStep === 1 ? '上传底稿（步骤 1/2）' : '确认识别数据（步骤 2/2）'" width="560px" :close-on-click-modal="false">
      <!-- 步骤条 -->
      <el-steps :active="uploadStep - 1" finish-status="success" style="margin-bottom: 20px">
        <el-step title="上传文件" />
        <el-step title="确认识别数据" />
      </el-steps>

      <!-- 步骤1：上传文件 -->
      <template v-if="uploadStep === 1">
        <el-alert v-if="uploadConflict" type="warning" :closable="false" show-icon style="margin-bottom: 16px">
          版本冲突：服务器版本 v{{ uploadConflict.server_version }}，您的版本 v{{ uploadConflict.uploaded_version }}
        </el-alert>
        <el-upload
          ref="uploadRef"
          drag
          :auto-upload="false"
          :limit="1"
          accept=".xlsx,.xls"
          :on-change="onUploadFileChange"
        >
          <el-icon style="font-size: 40px; /* allow-px: emoji-icon (上传图标) */ color: var(--gt-color-primary)"><Upload /></el-icon>
          <div>拖拽文件到此处，或点击选择</div>
        </el-upload>
      </template>

      <!-- 步骤2：确认识别数据 -->
      <template v-else-if="uploadStep === 2">
        <el-alert v-if="parseLoading" type="info" :closable="false" show-icon style="margin-bottom: 16px">
          正在解析底稿数据，请稍候...
        </el-alert>
        <template v-if="!parseLoading && parsedPreview">
          <el-descriptions title="系统识别结果" :column="2" border size="default" style="margin-bottom: 16px">
            <el-descriptions-item label="底稿名称">{{ parsedPreview.wp_name || selectedWp?.wp_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="审计年度">{{ parsedPreview.year || '-' }}</el-descriptions-item>
            <el-descriptions-item label="审定数">
              <span :class="parsedPreview.audited_amount != null ? 'gt-parsed-value' : 'gt-parsed-empty'">
                {{ parsedPreview.audited_amount != null ? fmtParsed(parsedPreview.audited_amount) : '未识别' }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="未审数">
              <span :class="parsedPreview.unadjusted_amount != null ? 'gt-parsed-value' : 'gt-parsed-empty'">
                {{ parsedPreview.unadjusted_amount != null ? fmtParsed(parsedPreview.unadjusted_amount) : '未识别' }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item v-if="parsedPreview.audited_amount != null && parsedPreview.unadjusted_amount != null" label="差异">
              <span :class="Math.abs(parsedPreview.audited_amount - parsedPreview.unadjusted_amount) > 0 ? 'gt-parsed-diff' : 'gt-parsed-value'">
                {{ fmtParsed(parsedPreview.audited_amount - parsedPreview.unadjusted_amount) }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item v-if="parsedPreview.sheet_count" label="工作表数">{{ parsedPreview.sheet_count }}</el-descriptions-item>
          </el-descriptions>
          <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 8px">
            <template #title>请确认以上识别数据是否正确，确认后将写入系统</template>
          </el-alert>
        </template>
        <el-empty v-else-if="!parseLoading" description="解析未返回数据，仍可确认写入" :image-size="60" />
      </template>

      <template #footer>
        <el-button @click="onUploadCancel" :disabled="uploadLoading || parseLoading">取消</el-button>
        <!-- 步骤1 按钮 -->
        <template v-if="uploadStep === 1">
          <el-button v-if="uploadConflict" type="warning" @click="doUploadStep1(true)" :loading="uploadLoading">
            强制覆盖
          </el-button>
          <el-button type="primary" @click="doUploadStep1(false)" :loading="uploadLoading" :disabled="!uploadFile">
            上传并解析
          </el-button>
        </template>
        <!-- 步骤2 按钮 -->
        <template v-else-if="uploadStep === 2">
          <el-button @click="uploadStep = 1" :disabled="parseLoading">← 重新上传</el-button>
          <el-button type="primary" @click="doConfirmParsed" :loading="parseLoading">
            确认写入
          </el-button>
        </template>
      </template>
    </el-dialog>

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showWpImport"
      import-type="workpaper"
      :project-id="projectId"
      :year="Number(route.query.year) || new Date().getFullYear()"
      @imported="onWpImported"
    />

    <!-- 批量委派弹窗 -->
    <BatchAssignDialog
      v-model="showBatchAssign"
      :project-id="projectId"
      :wp-ids="selectedWpIds"
      :wp-list="batchAssignWpList"
      @assigned="onBatchAssigned"
    />

    <!-- 看板分配弹窗 -->
    <el-dialog
      v-model="showAssignDialog"
      title="分配底稿"
      width="420px"
      append-to-body
    >
      <div v-if="assigningItem" style="margin-bottom: 12px; color: var(--gt-color-text-regular); font-size: var(--gt-font-size-sm);">
        底稿：<strong>{{ assigningItem.wp_code }} {{ assigningItem.wp_name }}</strong>
      </div>
      <el-form ref="assignFormRef" :model="assignForm" :rules="assignRules" label-width="70px">
        <el-form-item label="编制人" prop="assigned_to">
          <el-select
            v-model="assignForm.assigned_to"
            placeholder="请选择编制人"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.username"
              :label="`${u.full_name || u.username} (${u.username})`"
              :value="u.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="复核人">
          <el-select
            v-model="assignForm.reviewer"
            placeholder="请选择复核人"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.username"
              :label="`${u.full_name || u.username} (${u.username})`"
              :value="u.username"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAssignDialog = false">取消</el-button>
        <el-button type="primary" :loading="assignLoading" @click="onConfirmAssign">确认分配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import * as P from '@/services/apiPaths'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmForcePass } from '@/utils/confirm'
import { eventBus } from '@/utils/eventBus'
import { Download, Monitor, Upload, Loading, FolderOpened, WarningFilled } from '@element-plus/icons-vue'
import GateBlockPanel from '@/components/gate/GateBlockPanel.vue'
import SoDConflictDialog from '@/components/gate/SoDConflictDialog.vue'
import WorkpaperKanban from '@/components/workpaper/WorkpaperKanban.vue'
import WorkpaperLifecycleView from '@/components/workpaper/WorkpaperLifecycleView.vue'
import WorkpaperDependencyGraph from '@/components/workpaper/WorkpaperDependencyGraph.vue'
import WorkpaperAssignmentMatrix from '@/components/workpaper/WorkpaperAssignmentMatrix.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import BatchAssignDialog from '@/components/assignment/BatchAssignDialog.vue'
import BatchActionBar from '@/components/workpaper/BatchActionBar.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtRowActions from '@/components/common/GtRowActions.vue'
import type { RowAction } from '@/components/common/GtRowActions.vue'
import ViewSwitcher from '@/components/workpaper/ViewSwitcher.vue'
import { useRoleViewPreset } from '@/composables/useRoleViewPreset'
import type { ViewPresetId } from '@/composables/viewPresetConfig'
import { usePermission } from '@/composables/usePermission'
import { useAuthStore } from '@/stores/auth'
import { useDictStore } from '@/stores/dict'
import {
  listWorkpaperAnnotations, createAnnotation, updateAnnotation,
  getFeatureMaturity, submitWorkpaperReview,
  checkUnconfirmedAI,
  listUsers,
} from '@/services/commonApi'
import {
  downloadWorkpaper,
  downloadWorkpaperPack,
  downloadTemplate,
  downloadAllTemplates,
  uploadWorkpaperFile,
  listWorkpapers, runQCCheck, getQCResults,
  getWpIndex, updateReviewStatus, parseWorkpaper,
  assignWorkpaper,
  type WorkpaperDetail, type WpIndexItem, type QCResult,
} from '@/services/workpaperApi'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
// Spec A R1 / R3：跨视图 stale 摘要（推到 6 视图之一）
import { useStaleSummaryFull } from '@/composables/useStaleSummaryFull'
import { useWpDetailGuard } from '@/composables/useWpDetailGuard'
import StaleIndicator from '@/components/StaleIndicator.vue'
import { useAuditContext } from '@/composables/useAuditContext'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'

const route = useRoute()
const router = useRouter()
const dictStore = useDictStore()
const { canEdit, onContextChange } = useAuditContext()
const projectId = computed(() => route.params.projectId as string)
// Spec A: 当前年度（以 route.query.year 为唯一真源）
const currentYear = computed(() => Number(route.query.year) || new Date().getFullYear())
const { workpapers: wpStaleSummary } = useStaleSummaryFull(projectId, currentYear)
// stale wp_id Set，用于 tree 节点判定
const staleWpIdSet = computed(() => new Set(wpStaleSummary.value.items.map((it: any) => it.id)))
const projectName = ref('')

// ─── Task 2.1-2.4: 角色视图切换集成 ─────────────────────────────────────────
// 保存 viewMode 切换前的 activePreset，切回 list 时恢复
const _savedRolePreset = ref<ViewPresetId | null>(null)

// Foundation Task 2.9: 循环级复核状态徽章
interface CycleReviewStat {
  cycle_code: string
  cycle_name: string
  total_workpapers: number
  reviewed_workpapers: number
  workpapers: Array<{ wp_code: string; wp_name: string; is_reviewed: boolean }>
}
const cycleReviewStats = ref<Record<string, CycleReviewStat>>({})
let _reviewStatusTimer: ReturnType<typeof setTimeout> | null = null

async function loadCycleReviewStatus() {
  if (!projectId.value) return
  try {
    const { default: http } = await import('@/utils/http')
    const resp = await http.get(`/api/projects/${projectId.value}/workpapers/review-status`)
    const data = resp.data?.data ?? resp.data
    const cycles: CycleReviewStat[] = data?.cycles || []
    const map: Record<string, CycleReviewStat> = {}
    for (const c of cycles) {
      map[c.cycle_code] = c
    }
    cycleReviewStats.value = map
  } catch {
    // 静默失败：徽章不显示即可，不阻断主流程
  }
}

function _scheduleReviewStatusReload() {
  if (_reviewStatusTimer) clearTimeout(_reviewStatusTimer)
  _reviewStatusTimer = setTimeout(() => loadCycleReviewStatus(), 500)
}

const loading = ref(false)
const showWpImport = ref(false)
const qcLoading = ref(false)
const downloadLoading = ref(false)
const submitLoading = ref(false)

// Phase 14: 门禁阻断面板状态
const gateState = ref<'normal' | 'evaluating' | 'blocked' | 'warned' | 'error'>('normal')
const gateHitRules = ref<any[]>([])
const gateTraceId = ref('')

// Phase 14: SoD 冲突弹窗
const showSodDialog = ref(false)
const sodConflictType = ref('')
const sodPolicyCode = ref('')
const sodTraceId = ref('')
const searchKeyword = ref('')
const viewMode = ref('list')
let searchTimer: ReturnType<typeof setTimeout> | null = null

// ─── 用户手册视图数据 ─────────────────────────────────────────────
const guideSection = ref<'overview' | 'flow' | 'relation' | 'cycles'>('overview')
const guideBreadcrumb = ref<string[]>(['体系总览'])
const guideFocusCycle = ref('')

const guideOverviewData = [
  { code: 'A', name: '报表与调整', color: '#6750A4', count: 20, desc: '总括性程序、报表编制、调整分录',
    coreWps: [
      { code: 'A1', name: '财务报告程序表', role: '总控台', detail: '汇总各循环审计结论，形成整体审计意见的依据' },
      { code: 'A2', name: '调整分录汇总表', role: '枢纽', detail: '归集 D~N 各循环的 AJE/RJE，更新试算表审定数' },
      { code: 'A10', name: '与治理层沟通程序', role: '沟通', detail: '记录与管理层/治理层的关键沟通事项' },
    ],
    relatedTo: ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'],
    relDesc: '接收各循环调整分录 → 汇总到试算表 → 生成报表' },
  { code: 'B', name: '风险评估', color: '#6750A4', count: 15, desc: '穿行测试、了解内控、风险识别',
    coreWps: [
      { code: 'B1', name: '了解被审计单位', role: '总控台', detail: '记录行业环境、经营模式、内控体系的了解过程' },
      { code: 'B2', name: '重大错报风险评估', role: '核心', detail: '识别财务报表层面和认定层面的重大错报风险' },
      { code: 'B3', name: '重要性水平确定', role: '基准', detail: '确定整体重要性、实际执行重要性、明显微小错报临界值' },
    ],
    relatedTo: ['C', 'D', 'E', 'F'],
    relDesc: '风险评估结果 → 决定控制测试范围 → 指导实质性程序设计' },
  { code: 'C', name: '控制测试', color: '#6750A4', count: 14, desc: '控制有效性测试、偏差评估',
    coreWps: [
      { code: 'C1', name: '控制测试总表', role: '总控台', detail: '汇总各业务循环关键控制的测试结论' },
      { code: 'C2', name: '穿行测试记录', role: '验证', detail: '对每个关键控制执行穿行测试，确认控制设计有效' },
      { code: 'C3', name: '控制偏差评估', role: '结论', detail: '评估控制偏差对审计策略的影响，决定是否信赖控制' },
    ],
    relatedTo: ['B', 'D', 'E', 'F'],
    relDesc: '依据 B 风险评估 → 测试关键控制 → 影响 D~N 实质性程序范围' },
  { code: 'D', name: '销售收入', color: '#E8590C', count: 8, desc: '收入确认、应收账款、信用减值',
    coreWps: [
      { code: 'D1', name: '收入循环总控台', role: '总控台', detail: '统筹收入确认测试、应收账款函证、信用减值计算' },
      { code: 'D2', name: '应收账款明细表', role: '核心', detail: '编制应收账款余额明细，执行账龄分析和函证程序' },
      { code: 'D4', name: '收入截止测试', role: '测试', detail: '验证收入确认时点的准确性，检查跨期收入' },
    ],
    relatedTo: ['A', 'E', 'F', 'N'],
    relDesc: '从 TB 取应收/收入余额 → 函证+截止测试 → 调整分录回写 A2' },
  { code: 'E', name: '货币资金', color: '#E8590C', count: 7, desc: '银行存款、现金、银行函证',
    coreWps: [
      { code: 'E1', name: '货币资金总控台', role: '总控台', detail: '统筹银行存款函证、现金盘点、银行余额调节' },
      { code: 'E2', name: '银行存款函证', role: '核心', detail: '向银行发函确认余额，核对银行回函与账面差异' },
      { code: 'E3', name: '银行余额调节表', role: '调节', detail: '编制调节表，核实未达账项的真实性和完整性' },
    ],
    relatedTo: ['A', 'D', 'L'],
    relDesc: '从 TB 取银行/现金余额 → 函证+调节 → 与 D 收入回款/L 借款收付交叉验证' },
  { code: 'F', name: '采购存货', color: '#E8590C', count: 9, desc: '采购循环、存货计价、跌价准备',
    coreWps: [
      { code: 'F1', name: '采购存货总控台', role: '总控台', detail: '统筹存货监盘、计价测试、跌价准备计算' },
      { code: 'F2', name: '存货明细表', role: '核心', detail: '编制存货余额明细，执行计价测试和跌价准备复核' },
      { code: 'F3', name: '存货监盘记录', role: '实证', detail: '记录存货监盘过程、盘点差异及处理结论' },
    ],
    relatedTo: ['A', 'D', 'K'],
    relDesc: '从 TB 取存货/应付余额 → 监盘+计价 → 与 D 成本配比/K 费用归集交叉验证' },
  { code: 'G', name: '投资', color: '#E8590C', count: 6, desc: '长期股权投资、金融资产分类',
    coreWps: [
      { code: 'G1', name: '投资循环总控台', role: '总控台', detail: '统筹长投权益法核算、金融资产分类、公允价值计量' },
      { code: 'G2', name: '长期股权投资明细', role: '核心', detail: '验证投资成本、权益法调整、减值测试' },
    ],
    relatedTo: ['A', 'H', 'M'],
    relDesc: '从 TB 取投资余额 → 权益法/公允价值 → 与 M 权益变动/H 资产联动' },
  { code: 'H', name: '固定资产', color: '#E8590C', count: 8, desc: '固定资产、在建工程、使用权资产',
    coreWps: [
      { code: 'H1', name: '固定资产总控台', role: '总控台', detail: '统筹折旧重算、减值测试、在建工程转固' },
      { code: 'H2', name: '固定资产明细表', role: '核心', detail: '编制固定资产增减变动表，复核折旧计算准确性' },
      { code: 'H8', name: '使用权资产', role: '专项', detail: '新租赁准则下使用权资产确认和租赁负债计量' },
    ],
    relatedTo: ['A', 'K', 'L'],
    relDesc: '从 TB 取固定资产余额 → 折旧重算+减值 → 折旧费用归入 K/租赁负债归入 L' },
  { code: 'I', name: '无形资产', color: '#E8590C', count: 5, desc: '无形资产、商誉、开发支出',
    coreWps: [
      { code: 'I1', name: '无形资产总控台', role: '总控台', detail: '统筹摊销重算、商誉减值、研发支出资本化判断' },
      { code: 'I2', name: '无形资产明细表', role: '核心', detail: '编制无形资产增减变动表，复核摊销和减值' },
    ],
    relatedTo: ['A', 'K'],
    relDesc: '从 TB 取无形资产余额 → 摊销重算+商誉减值 → 摊销费用归入 K' },
  { code: 'J', name: '职工薪酬', color: '#E8590C', count: 4, desc: '薪酬计提、股份支付',
    coreWps: [
      { code: 'J1', name: '薪酬循环总控台', role: '总控台', detail: '统筹工资计提测试、社保核对、股份支付计量' },
      { code: 'J2', name: '薪酬计提测试', role: '核心', detail: '验证 12 个月工资计提的完整性和准确性' },
    ],
    relatedTo: ['A', 'K', 'N'],
    relDesc: '从 TB 取薪酬余额 → 计提测试 → 费用归入 K/个税归入 N' },
  { code: 'K', name: '管理费用', color: '#E8590C', count: 3, desc: '费用分析、跨循环减值汇总',
    coreWps: [
      { code: 'K1', name: '费用分析总控台', role: '总控台', detail: '汇总各循环费用类科目，执行 YoY 波动分析' },
      { code: 'K2', name: '跨循环减值汇总', role: '汇总', detail: '归集 D~I 各循环的减值/跌价准备，验证总额合理性' },
    ],
    relatedTo: ['A', 'D', 'F', 'H', 'I', 'J'],
    relDesc: '归集各循环费用和减值 → YoY 分析 → 异常波动追查到源循环' },
  { code: 'L', name: '筹资', color: '#E8590C', count: 4, desc: '借款、债券、利息计算',
    coreWps: [
      { code: 'L1', name: '筹资循环总控台', role: '总控台', detail: '统筹借款函证、利息重算、摊余成本计量' },
      { code: 'L2', name: '借款明细表', role: '核心', detail: '编制借款增减变动表，验证利息计算和期限分类' },
    ],
    relatedTo: ['A', 'E', 'H'],
    relDesc: '从 TB 取借款余额 → 函证+利息重算 → 与 E 银行流水/H 租赁负债交叉验证' },
  { code: 'M', name: '股东权益', color: '#E8590C', count: 3, desc: '权益变动、利润分配',
    coreWps: [
      { code: 'M1', name: '权益变动总控台', role: '总控台', detail: '编制权益变动表，验证利润分配和资本变动' },
      { code: 'M2', name: '权益变动明细', role: '核心', detail: '核对实收资本、资本公积、盈余公积、未分配利润变动' },
    ],
    relatedTo: ['A', 'G', 'N'],
    relDesc: '从 TB 取权益余额 → 变动核对 → 与 G 投资/N 所得税利润分配联动' },
  { code: 'N', name: '税费', color: '#E8590C', count: 3, desc: '所得税、递延税项',
    coreWps: [
      { code: 'N1', name: '税费循环总控台', role: '总控台', detail: '统筹所得税计算、递延税项确认、税费完整性' },
      { code: 'N2', name: '所得税计算表', role: '核心', detail: '编制应纳税所得额调整表，验证当期和递延所得税' },
    ],
    relatedTo: ['A', 'D', 'H', 'I', 'M'],
    relDesc: '从 TB 取税费余额 → 所得税重算 → 暂时性差异来源于 D~M 各循环' },
  { code: 'S', name: '专项程序', color: '#2E7D32', count: 5, desc: '持续经营、关联方、期后事项',
    coreWps: [
      { code: 'S1', name: '持续经营评估', role: '专项', detail: '评估被审计单位持续经营能力，识别重大不确定性' },
      { code: 'S2', name: '关联方交易', role: '专项', detail: '识别关联方关系，验证关联交易的公允性和披露完整性' },
      { code: 'S3', name: '期后事项', role: '专项', detail: '检查资产负债表日后事项，判断调整/非调整事项' },
    ],
    relatedTo: ['A', 'B'],
    relDesc: '独立于业务循环的特定审计程序 → 结论影响 A 审计报告意见' },
]

const guideFlowSteps = [
  { id: 'plan', icon: '📋', label: '审计计划', sub: '风险识别与策略制定', color: '#6750A4',
    detail: '风险导向审计的起点。了解被审计单位及其环境（行业、经营模式、治理结构），识别和评估重大错报风险，确定重要性水平（整体重要性→实际执行重要性→明显微小错报临界值），制定总体审计策略和具体审计计划。',
    riskFocus: '识别哪些领域可能存在重大错报风险，决定后续审计资源的分配方向',
    keyActions: [
      '了解被审计单位及其环境（行业风险、经营风险、财务风险）',
      '识别和评估重大错报风险（报表层面 + 认定层面）',
      '确定重要性水平（计算基准、百分比、最终金额）',
      '制定审计策略（综合方案 vs 实质性方案）',
      '编制审计计划（人员分工、时间安排、重点领域）',
    ],
    wpLinks: [
      { code: 'A1', name: '财务报告程序表', relation: '记录审计策略和总体计划' },
      { code: 'B1', name: '了解被审计单位', relation: '记录对单位环境的了解过程' },
      { code: 'B2', name: '重大错报风险评估', relation: '识别报表和认定层面风险' },
      { code: 'B3', name: '重要性水平确定', relation: '计算并记录三级重要性' },
    ],
    outputs: ['A', 'B'],
    nextStageLink: '风险评估结果直接决定→穿行测试的范围和重点' },
  { id: 'walkthrough', icon: '🔄', label: '穿行测试', sub: '验证控制设计有效性', color: '#7B1FA2',
    detail: '风险导向审计的第二步。针对计划阶段识别的关键业务流程，选取一笔完整交易从发起到记录全程追踪，验证内部控制是否按设计运行。穿行测试是控制测试的前提——只有设计有效的控制才值得进一步测试执行有效性。',
    riskFocus: '验证"纸面上的控制"是否真正落地执行，筛选出值得信赖的控制点',
    keyActions: [
      '选取关键业务流程（收入、采购、资金、薪酬等）',
      '每个流程选取一笔完整交易从头到尾追踪',
      '观察每个控制节点是否按设计执行（审批、核对、复核）',
      '记录控制设计缺陷（如缺少审批环节、职责未分离）',
      '评估控制设计有效性，决定哪些控制进入控制测试',
    ],
    wpLinks: [
      { code: 'B4', name: '穿行测试-收入循环', relation: '追踪一笔销售从合同→发货→开票→收款' },
      { code: 'B5', name: '穿行测试-采购循环', relation: '追踪一笔采购从请购→审批→验收→付款' },
      { code: 'B6', name: '穿行测试-资金循环', relation: '追踪一笔付款从申请→审批→支付→记账' },
      { code: 'C1', name: '控制测试总表', relation: '穿行测试结论→决定控制测试范围' },
    ],
    outputs: ['B', 'C'],
    nextStageLink: '穿行测试确认设计有效的控制→进入控制测试验证执行有效性' },
  { id: 'control', icon: '🔒', label: '控制测试', sub: '测试控制执行有效性', color: '#1976D2',
    detail: '风险导向审计的关键环节。对穿行测试确认设计有效的关键控制，扩大样本量测试其在整个审计期间是否一贯有效执行。控制测试结果直接影响实质性程序的性质、时间和范围——控制有效则可减少细节测试量。',
    riskFocus: '控制可信赖程度决定实质性程序的范围：控制越有效→细节测试越少',
    keyActions: [
      '确定测试样本量（基于控制频率：日常控制 25 笔、周控制 5 笔、月控制 2 笔）',
      '执行控制测试（检查审批签字、核对记录、系统日志）',
      '记录控制偏差（未执行/执行不当/延迟执行）',
      '评估偏差影响（个别偏差 vs 系统性失效）',
      '形成控制结论（可信赖/部分信赖/不可信赖）→调整实质性程序',
    ],
    wpLinks: [
      { code: 'C1', name: '控制测试总表', relation: '汇总各循环控制测试结论' },
      { code: 'C2', name: '穿行测试记录', relation: '穿行测试→控制测试的衔接依据' },
      { code: 'C3', name: '控制偏差评估', relation: '评估偏差对审计策略的影响' },
    ],
    outputs: ['C'],
    nextStageLink: '控制测试结论→决定实质性程序的范围和深度' },
  { id: 'substantive', icon: '🔍', label: '实质性程序', sub: '获取充分适当审计证据', color: '#E8590C',
    detail: '风险导向审计的核心执行阶段。针对各业务循环（D~N）执行细节测试和实质性分析程序，直接验证财务报表金额和披露的正确性。实质性程序的范围由前三个阶段的风险评估和控制测试结论决定——高风险领域+控制不可信赖=扩大测试范围。',
    riskFocus: '高风险认定（如收入完整性、资产存在性）必须执行更多细节测试，不能仅靠分析程序',
    keyActions: [
      '细节测试：函证（银行/应收/应付）、监盘（存货/现金）、重新计算（折旧/利息/税费）',
      '实质性分析程序：YoY 波动分析、毛利率趋势、费用率合理性',
      '截止测试：验证交易记录在正确期间（收入/成本跨期）',
      '编制审计调整分录（AJE/RJE）修正发现的错报',
      '评估未更正错报的汇总影响是否超过重要性',
    ],
    wpLinks: [
      { code: 'D1', name: '收入循环总控台', relation: '统筹收入确认+应收账款+信用减值' },
      { code: 'E1', name: '货币资金总控台', relation: '统筹银行函证+余额调节+现金盘点' },
      { code: 'F1', name: '采购存货总控台', relation: '统筹存货监盘+计价+跌价准备' },
      { code: 'H1', name: '固定资产总控台', relation: '统筹折旧重算+减值+在建转固' },
      { code: 'A2', name: '调整分录汇总表', relation: '归集各循环 AJE/RJE 更新试算表' },
    ],
    outputs: ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'],
    nextStageLink: '各循环审计结论+调整分录→汇总到完成阶段形成审计意见' },
  { id: 'complete', icon: '✅', label: '审计完成', sub: '汇总结论与出具报告', color: '#2E7D32',
    detail: '风险导向审计的收尾阶段。汇总全部审计发现，评价未更正错报的汇总影响，执行期后事项审查和持续经营评估，复核底稿质量，形成审计意见并出具审计报告。',
    riskFocus: '最终评估：汇总错报是否超过重要性？是否存在影响审计意见的重大事项？',
    keyActions: [
      '汇总未更正错报，评估对报表整体的影响',
      '执行期后事项审查（资产负债表日→报告日之间的重大事项）',
      '评估持续经营假设的适当性',
      '获取管理层声明书',
      '复核底稿质量（项目质量控制复核 EQCR）',
      '形成审计意见（无保留/保留/否定/无法表示）',
      '出具审计报告',
    ],
    wpLinks: [
      { code: 'A1', name: '财务报告程序表', relation: '汇总审计结论，记录意见形成过程' },
      { code: 'A2', name: '调整分录汇总表', relation: '最终确认所有 AJE/RJE 的影响' },
      { code: 'S1', name: '持续经营评估', relation: '评估持续经营能力和重大不确定性' },
      { code: 'S2', name: '关联方交易', relation: '确认关联方披露的完整性' },
      { code: 'S3', name: '期后事项', relation: '检查报告日前的重大事项' },
    ],
    outputs: ['A', 'S'],
    nextStageLink: '' },
]

const guideRelations = [
  { target: 'D', label: '销售收入', desc: '从 TB 取应收/收入余额 → 编制明细表' },
  { target: 'E', label: '货币资金', desc: '从 TB 取银行/现金余额 → 函证核对' },
  { target: 'F', label: '采购存货', desc: '从 TB 取存货/应付余额 → 计价测试' },
  { target: 'H', label: '固定资产', desc: '从 TB 取固定资产余额 → 折旧重算' },
  { target: 'N', label: '税费', desc: '从 TB 取税费余额 → 所得税计算' },
  { target: 'A', label: '报表调整', desc: '各循环调整分录 → 汇总到试算表' },
]

// 底稿与报表/附注/试算表的完整关系图数据
const guideFullRelations = [
  { id: 'tb', name: '试算表', icon: '📊', color: '#6750A4', type: 'center',
    desc: '审计工作的数据枢纽，汇总所有科目的未审数、调整数、审定数',
    connections: [
      { to: '底稿', direction: 'out', label: '提供科目余额', style: 'solid' },
      { to: '调整分录', direction: 'in', label: '接收 AJE/RJE', style: 'solid' },
      { to: '报表', direction: 'out', label: '审定数生成报表', style: 'solid' },
    ] },
  { id: 'wp', name: '底稿 (D~N)', icon: '📋', color: '#E8590C', type: 'node',
    desc: '各业务循环的实质性程序底稿，执行细节测试获取审计证据',
    connections: [
      { to: '试算表', direction: 'in', label: '取数（科目余额）', style: 'solid' },
      { to: '调整分录', direction: 'out', label: '发现错报→建议调整', style: 'solid' },
      { to: '附注', direction: 'out', label: '提供披露数据', style: 'dashed' },
    ] },
  { id: 'adj', name: '调整分录', icon: '✏️', color: '#D32F2F', type: 'node',
    desc: 'AJE（审计调整）和 RJE（重分类），修正报表错报',
    connections: [
      { to: '试算表', direction: 'out', label: '更新审定数', style: 'solid' },
      { to: '报表', direction: 'out', label: '影响报表金额', style: 'solid' },
    ] },
  { id: 'report', name: '财务报表', icon: '📑', color: '#1976D2', type: 'node',
    desc: '资产负债表、利润表、现金流量表等，由试算表审定数自动生成',
    connections: [
      { to: '附注', direction: 'out', label: '报表行→附注明细', style: 'solid' },
      { to: '审计报告', direction: 'out', label: '支撑审计意见', style: 'dashed' },
    ] },
  { id: 'note', name: '附注', icon: '📝', color: '#2E7D32', type: 'node',
    desc: '财务报表附注，对报表项目的详细说明和补充披露',
    connections: [
      { to: '报表', direction: 'in', label: '引用报表金额', style: 'solid' },
      { to: '底稿', direction: 'in', label: '引用底稿数据', style: 'dashed' },
    ] },
  { id: 'opinion', name: '审计报告', icon: '📄', color: '#455A64', type: 'endpoint',
    desc: '最终产出物，基于全部审计证据形成审计意见',
    connections: [
      { to: '报表', direction: 'in', label: '对报表发表意见', style: 'solid' },
      { to: '底稿', direction: 'in', label: '底稿支撑结论', style: 'dashed' },
    ] },
]

// 数据流转路径（从左到右的主线）
const guideDataFlowPaths = [
  { from: '账套导入', to: '试算表', label: '客户 ERP 数据', icon: '📥' },
  { from: '试算表', to: '底稿', label: '科目余额取数', icon: '📊' },
  { from: '底稿', to: '调整分录', label: '发现错报', icon: '📋' },
  { from: '调整分录', to: '试算表', label: '更新审定数', icon: '✏️' },
  { from: '试算表', to: '报表', label: '生成报表', icon: '📑' },
  { from: '报表', to: '附注', label: '明细披露', icon: '📝' },
  { from: '报表+附注', to: '审计报告', label: '形成意见', icon: '📄' },
]

const guideCycleDetails = computed(() => {
  return guideOverviewData.map(cycle => {
    const wps = wpIndex.value
      .filter((w: WpIndexItem) => w.wp_code?.startsWith(cycle.code))
      .map((w: WpIndexItem) => ({ code: w.wp_code, name: w.wp_name }))
      .sort((a, b) => (a.code || '').localeCompare(b.code || ''))
    return { ...cycle, wps }
  })
})

function guideJumpToCycle(code: string) {
  guideBreadcrumb.value.push(guideSection.value === 'overview' ? '体系总览' : guideSection.value === 'flow' ? '审计流程' : '底稿关系')
  guideSection.value = 'cycles'
  guideFocusCycle.value = code
}

function guideGoBack() {
  guideBreadcrumb.value.pop()
  const prev = guideBreadcrumb.value[guideBreadcrumb.value.length - 1]
  if (prev === '体系总览') guideSection.value = 'overview'
  else if (prev === '审计流程') guideSection.value = 'flow'
  else if (prev === '底稿关系') guideSection.value = 'relation'
  else guideSection.value = 'overview'
}

function onGuideWpClick(wpCode: string) {
  // 跳转到列表视图并选中对应底稿
  viewMode.value = 'list'
  guideBreadcrumb.value = ['体系总览']
  nextTick(() => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.wp_code === wpCode)
    if (idx) selectWorkpaperById(idx.id)
  })
}

// Filters (declared early for composable dependency)
const filterCycle = ref('')
const filterStatus = ref('')
const filterAssignee = ref('')
const showTrimmedFilter = ref<'active' | 'all'>('active') // 裁剪筛选：active=仅活跃 / all=全部

// 裁剪筛选 checkbox 双向绑定
const showTrimmedChecked = computed({
  get: () => showTrimmedFilter.value === 'all',
  set: (v: boolean) => { showTrimmedFilter.value = v ? 'all' : 'active' },
})
const trimmedCount = computed(() => wpIndex.value.filter((w: WpIndexItem) => w.status === 'not_applicable').length)
const trimmedStatsLabel = computed(() =>
  trimmedCount.value > 0
    ? `显示已裁剪 (${trimmedCount.value})`
    : '显示已裁剪'
)

// Core data (declared early for composable dependency)
const wpList = ref<WorkpaperDetail[]>([])
const wpIndex = ref<WpIndexItem[]>([])

// ─── Task 2.1-2.4: useRoleViewPreset 集成 ───────────────────────────────────
const { role: currentRole } = usePermission()
const authStore = useAuthStore()
const currentUserId = computed(() => authStore.userId || 'anonymous')

// 将 wpList 转换为 WpItem 格式供 composable 使用
const roleViewWpList = computed(() =>
  wpList.value.map((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    return {
      id: w.id,
      wp_code: w.wp_code || idx?.wp_code || '',
      wp_name: w.wp_name || idx?.wp_name || '',
      status: w.status || 'pending',
      audit_cycle: w.audit_cycle || idx?.audit_cycle || '',
      review_status: w.review_status || 'pending',
      preparer: w.assigned_to || '',
      _openReviewCount: (w as any)._openReviewCount ?? 0,
      _riskLevel: (w as any)._riskLevel ?? 2,
      is_trimmed: (w as any).is_trimmed ?? false,
    }
  })
)

const roleViewManualFilters = computed(() => ({
  audit_cycle: filterCycle.value || undefined,
  status: filterStatus.value || undefined,
  preparer: filterAssignee.value || undefined,
}))

const {
  activePreset: _roleActivePreset,
  processedList: roleProcessedList,
  highlightMap: roleHighlightMap,
  badgeMap: roleBadgeMap,
  groupedList: roleGroupedList,
  summaryData: roleViewSummary,
  switchPreset: roleSwitchPreset,
} = useRoleViewPreset(
  projectId as any,
  currentUserId as any,
  roleViewWpList as any,
  searchKeyword,
  roleViewManualFilters as any,
  { role: currentRole },
)

/** 双向绑定 roleViewPreset（ViewSwitcher v-model） */
const roleViewPreset = computed({
  get: () => _roleActivePreset.value,
  set: (val: ViewPresetId) => roleSwitchPreset(val),
})

/** Task 2.3: 获取树节点高亮样式 */
function getTreeNodeHighlightStyle(data: any): Record<string, string> {
  if (viewMode.value !== 'list' || !data.wpId) return {}
  const highlight = roleHighlightMap.value.get(data.id || data.wpId)
  return highlight?.style ?? {}
}

/** Task 2.3: 获取树节点高亮信息（含 tooltip） */
function getTreeNodeHighlight(data: any): { style: Record<string, string>; tooltip?: string } | undefined {
  if (viewMode.value !== 'list' || !data.wpId) return undefined
  return roleHighlightMap.value.get(data.id || data.wpId)
}

/** Task 2.3: 获取树节点 badge 数据 */
function getTreeNodeBadge(data: any): { value: number; type: 'danger' | 'warning' | 'info'; visible: boolean } | undefined {
  if (viewMode.value !== 'list' || !data.wpId) return undefined
  return roleBadgeMap.value.get(data.id || data.wpId)
}

/** Task 2.3: 质控视图复核标记 */
function getQcReviewMark(data: any): string {
  if (!data.wpId) return ''
  const wp = wpList.value.find((w: WorkpaperDetail) => w.id === data.id || w.id === data.wpId)
  if (!wp) return ''
  return wp.review_status === 'reviewed' || wp.review_status === 'level1_passed' || wp.review_status === 'level2_passed' ? '✓' : '○'
}

// Task 2.1: viewMode 切换时保存/恢复 activePreset
watch(viewMode, (newMode, oldMode) => {
  if (oldMode === 'list' && newMode !== 'list') {
    _savedRolePreset.value = _roleActivePreset.value
  }
  if (newMode === 'list' && oldMode !== 'list' && _savedRolePreset.value) {
    roleSwitchPreset(_savedRolePreset.value)
  }
})

function onSearchDebounce() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    fetchData()
  }, 300)
}
const uploadLoading = ref(false)
const parseLoading = ref(false)
// wpList and wpIndex declared earlier (for composable dependency)
const selectedWp = ref<WorkpaperDetail | null>(null)
const selectedWpId = ref('')
// useWpDetailGuard 三态守卫：详情面板根据底稿加载状态显示不同 UI 提示
const wpDetailGuard = useWpDetailGuard(projectId, selectedWpId)
const selectedWpIds = ref<string[]>([])
const qcResult = ref<QCResult | null>(null)
const treeRef = ref<any>(null)
const kanbanRef = ref<any>(null)

// 看板分配弹窗
const showAssignDialog = ref(false)
const assigningItem = ref<any>(null)
const assignForm = ref<{ assigned_to: string | null; reviewer: string | null }>({ assigned_to: null, reviewer: null })
const assignFormRef = ref<any>(null)
const assignRules = {
  assigned_to: [{ required: true, message: '请选择编制人', trigger: 'change' }],
}
const assignLoading = ref(false)
const userOptions = ref<any[]>([])

// 批量委派弹窗
const showBatchAssign = ref(false)
const batchAssignWpList = computed(() => {
  // 合并 wpList 和 wpIndex 信息，提供给 BatchAssignDialog
  return wpList.value.map((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    return {
      id: w.id,
      wp_code: w.wp_code || idx?.wp_code || '',
      wp_name: w.wp_name || idx?.wp_name || '',
      audit_cycle: w.audit_cycle || idx?.audit_cycle || '',
    }
  })
})

function onBatchAssigned(_result: { updated: number; notifications_sent: number; message: string }) {
  // 刷新数据
  fetchData()
}

// Phase 2 F3: 批量状态变更
async function onBatchStatusChange(payload: { action: string; ids: string[] }) {
  const actionLabels: Record<string, string> = {
    submit_review: '提交复核',
    return_to_draft: '退回修改',
    mark_complete: '标记完成',
  }
  const label = actionLabels[payload.action] || payload.action
  try {
    await ElMessageBox.confirm(
      `确定将 ${payload.ids.length} 个底稿${label}？`,
      '批量操作确认',
      { type: 'warning' }
    )
  } catch { return }

  try {
    const data = await api.post(
      `/api/projects/${projectId.value}/working-papers/batch-status`,
      { wp_ids: payload.ids, action: payload.action }
    ) as any
    ElMessage.success(data?.message || `成功${label}`)
    if (data?.skipped?.length > 0) {
      ElMessage.warning(`${data.skipped.length} 个底稿被跳过（状态不允许）`)
    }
    fetchData()
  } catch (e: any) {
    handleApiError(e, `批量${label}`)
  }
}

// 任务 6.1：用户名映射
const userNameMap = ref<Map<string, string>>(new Map())

function resolveUserName(uuid: string | null | undefined): string {
  if (!uuid) return '未分配'
  return userNameMap.value.get(uuid) ?? '未知用户'
}

// 任务 7.1：进度计算
const COMPLETED_STATUSES = new Set(['review_passed', 'archived'])

const totalProgress = computed(() => {
  const total = wpList.value.length
  const completed = wpList.value.filter((w: WorkpaperDetail) => COMPLETED_STATUSES.has(w.status)).length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, percent }
})

const filteredWpList = computed<WorkpaperDetail[]>(() => {
  return wpList.value.filter((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    if (filterCycle.value && !idx?.wp_code?.startsWith(filterCycle.value)) return false
    if (filterStatus.value && w.status !== filterStatus.value) return false
    if (filterAssignee.value && w.assigned_to !== filterAssignee.value) return false
    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      if (!w.wp_code?.toLowerCase().includes(kw) && !w.wp_name?.toLowerCase().includes(kw)) return false
    }
    return true
  })
})

const filteredProgress = computed(() => {
  const total = filteredWpList.value.length
  const completed = filteredWpList.value.filter((w: WorkpaperDetail) => COMPLETED_STATUSES.has(w.status)).length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, percent }
})

const hasFilter = computed(() => {
  return !!(filterCycle.value || filterStatus.value || filterAssignee.value || searchKeyword.value)
})

// ════════════════════════════════════════════════════════════════════
// 工作台视图（合并自 WorkpaperWorkbench）：循环进度+底稿表格
// ════════════════════════════════════════════════════════════════════

const cycleNameMap: Record<string, string> = {
  A: '完成阶段',
  B: '计划阶段',
  C: '控制测试',
  D: '收入循环',
  E: '货币资金',
  F: '存货',
  G: '投资',
  H: '固定资产',
  I: '无形资产',
  J: '职工薪酬',
  K: '管理/费用',
  L: '债务',
  M: '权益',
  N: '税金',
  S: '特定项目',
}

// 工作台视图状态
const workbenchProgressCollapsed = ref(false)
const workbenchCycleFilter = ref<string[]>([]) // 支持多选循环筛选

function onWorkbenchCycleClick(code: string) {
  const idx = workbenchCycleFilter.value.indexOf(code)
  if (idx >= 0) {
    workbenchCycleFilter.value.splice(idx, 1) // 取消选中
  } else {
    workbenchCycleFilter.value.push(code) // 添加选中
  }
}

const cycleSummary = computed(() => {
  const groups: Record<string, { total: number; completed: number }> = {}
  for (const w of wpList.value) {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    const code = idx?.wp_code || ''
    const cycleKey = code[0] || '?'
    if (!groups[cycleKey]) groups[cycleKey] = { total: 0, completed: 0 }
    groups[cycleKey].total += 1
    if (COMPLETED_STATUSES.has(w.status)) groups[cycleKey].completed += 1
  }
  return Object.entries(groups)
    .map(([code, g]) => ({
      code,
      name: cycleNameMap[code] || code,
      total: g.total,
      completed: g.completed,
      percent: g.total > 0 ? Math.round((g.completed / g.total) * 100) : 0,
    }))
    .sort((a, b) => a.code.localeCompare(b.code))
})

const STATUS_LABELS: Record<string, { label: string; type: string }> = {
  draft: { label: '待编', type: 'info' },
  in_progress: { label: '编制中', type: 'warning' },
  edit_complete: { label: '已完成', type: 'primary' },
  pending_review: { label: '待复核', type: 'warning' },
  reviewed: { label: '已复核', type: 'success' },
  approved: { label: '已通过', type: 'success' },
}

const workbenchTableData = computed(() => {
  return filteredWpList.value
    .filter((w: WorkpaperDetail) => {
      // 工作台循环筛选（支持多选）
      if (workbenchCycleFilter.value.length) {
        const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
        const code = idx?.wp_code || ''
        if (!workbenchCycleFilter.value.some(c => code.startsWith(c))) return false
      }
      return true
    })
    .map((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    const code = idx?.wp_code || ''
    const cycleKey = code[0] || '?'
    const statusInfo = STATUS_LABELS[w.status] || { label: w.status, type: 'info' }
    return {
      id: w.id,
      wp_code: code,
      wp_name: idx?.wp_name || '',
      cycle_name: cycleNameMap[cycleKey] || cycleKey,
      status: w.status,
      status_label: statusInfo.label,
      status_type: statusInfo.type,
      assignee_name: (w as any).assignee_name || '',
      total_steps: (w as any).total_steps || 0,
      completed_steps: (w as any).completed_steps || 0,
    }
  })
})

// ─── 工作台分页 ─────────────────────────────────────────────────────────────────
const wbPage = ref(1)
const wbPageSize = ref(50)
const wbTotal = computed(() => workbenchTableData.value.length)
const pagedWorkbenchData = computed(() => {
  const start = (wbPage.value - 1) * wbPageSize.value
  return workbenchTableData.value.slice(start, start + wbPageSize.value)
})

function onWorkbenchRowClick(row: any) {
  if (row.id) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: row.id } })
  }
}

function openEditor(row: any) {
  if (row.id) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: row.id } })
  }
}

// ── GtRowActions 行操作 ──
function getWpRowActions(_row: any): RowAction[] {
  return [
    { key: 'edit', label: '编辑', priority: 1 },
    { key: 'download', label: '下载', priority: 2 },
    { key: 'assign', label: '委派', priority: 3 },
  ]
}

function handleWpRowAction(key: string, row: any) {
  switch (key) {
    case 'edit':
      openEditor(row)
      break
    case 'download':
      if (row.id) downloadWorkpaper(projectId.value, row.id)
      break
    case 'assign':
      // 触发委派弹窗（复用现有逻辑）
      break
  }
}

// 精细化审计检查
const fineCheckResults = ref<any[]>([])
const fineChecksLoading = ref(false)
const fineChecksPassed = computed(() => fineCheckResults.value.length > 0 && fineCheckResults.value.every(c => c.passed !== false))
const fineChecksPassedCount = computed(() => fineCheckResults.value.filter(c => c.passed === true).length)

// TSJ复核提示词
const tsjReviewData = ref<any>(null)
const showTsjDetail = ref(false)

// Upload dialog
const uploadDialogVisible = ref(false)
const uploadFile = ref<File | null>(null)
const uploadConflict = ref<{ server_version: number; uploaded_version: number } | null>(null)
const uploadRef = ref<any>(null)
// 两步上传状态
const uploadStep = ref(1)
const parsedPreview = ref<any>(null)
const pendingWpId = ref('')
const pendingNewVersion = ref(1)

// Feature flags & Univer 在线编辑（纯前端，始终可用）
const onlineEditAvailable = ref(true)
const onlineEditEnabled = ref(true)
const onlineEditMaturity = ref('production')
const _onlineEditReady = computed(() => true)
const _onlineEditNotice = computed(() => '')

// Review annotations
const annotations = ref<any[]>([])
const unresolvedCount = computed(() => annotations.value.filter((a: any) => a.status !== 'resolved').length)
const annotationFilter = ref('')
const filteredAnnotations = computed(() => {
  if (!annotationFilter.value) return annotations.value
  return annotations.value.filter((a: any) => a.status === annotationFilter.value)
})

function annotationRowClass({ row }: { row: any }) {
  if (row.status === 'open' && row.priority === 'high') return 'gt-ann-row-urgent'
  return ''
}

function goToConversation() {
  if (!selectedWp.value) return
  router.push({
    path: `/projects/${projectId.value}/review-conversations`,
    query: { wp_id: selectedWp.value.id, wp_code: selectedWp.value.wp_code },
  })
}
const unconfirmedAiCount = ref(0)
const showAddAnnotation = ref(false)
const newAnnotation = ref({ content: '', priority: 'medium' })
const annoFormRef = ref<any>(null)
const annoRules = {
  content: [{ required: true, message: '请输入意见内容', trigger: 'blur' }],
}

// Reject dialog state
const showRejectDialog = ref(false)
const rejectReason = ref('')
const rejectingWpId = ref('')

// Whether the selected workpaper is in a reviewable state (pending_level1 or pending_level2)
const isReviewable = computed(() => {
  const rs = selectedWp.value?.review_status
  return rs === 'pending_level1' || rs === 'level1_in_progress'
    || rs === 'pending_level2' || rs === 'level2_in_progress'
})

// Filters (moved up for composable dependency)
// const filterCycle = ref('')  -- already declared above
// const filterStatus = ref('')
// const filterAssignee = ref('')

const cycleOptions = [
  { value: 'B', label: 'B类 计划阶段' },
  { value: 'C', label: 'C类 控制测试' },
  { value: 'D', label: 'D类 收入循环' },
  { value: 'E', label: 'E类 货币资金' },
  { value: 'F', label: 'F类 存货' },
  { value: 'G', label: 'G类 投资' },
  { value: 'H', label: 'H类 固定资产' },
  { value: 'I', label: 'I类 无形资产' },
  { value: 'J', label: 'J类 职工薪酬' },
  { value: 'K', label: 'K类 管理/费用' },
  { value: 'L', label: 'L类 债务' },
  { value: 'M', label: 'M类 权益' },
  { value: 'N', label: 'N类 税金' },
  { value: 'A', label: 'A类 完成阶段' },
  { value: 'S', label: 'S类 特定项目' },
]

const statusOptions = [
  { value: 'not_started', label: '未开始' },
  { value: 'in_progress', label: '编制中' },
  { value: 'draft_complete', label: '初稿完成' },
  { value: 'review_passed', label: '复核通过' },
  { value: 'archived', label: '已归档' },
]

const hasBlocking = computed(() => {
  // 4 项硬门槛：任一不满足则禁止提交复核
  if (!selectedWp.value) return true
  // 0. 编制状态必须为 edit_complete
  if (selectedWp.value.status !== 'edit_complete') return true
  // 1. reviewer 未分配
  if (!selectedWp.value.reviewer) return true
  // 2. 阻断级 QC 未通过
  if (!qcResult.value) return true
  if (qcResult.value && (qcResult.value.blocking_count ?? 0) > 0) return true
  // 3. 存在未解决复核意见
  if (unresolvedCount.value > 0) return true
  // 4. 存在未确认 AI 内容
  if (unconfirmedAiCount.value > 0) return true
  return false
})

const blockingReasons = computed(() => {
  const reasons: string[] = []
  if (!selectedWp.value) return reasons
  if (selectedWp.value.status !== 'edit_complete') reasons.push('底稿尚未完成编制')
  if (!selectedWp.value.reviewer) reasons.push('复核人未分配')
  if (!qcResult.value) reasons.push('未执行质量自检')
  if (qcResult.value && (qcResult.value.blocking_count ?? 0) > 0) reasons.push('存在阻断级 QC 问题')
  if (unresolvedCount.value > 0) reasons.push(`${unresolvedCount.value} 条未解决复核意见`)
  if (unconfirmedAiCount.value > 0) reasons.push(`${unconfirmedAiCount.value} 项未确认的 AI 生成内容`)
  return reasons
})

interface TreeNode {
  id: string
  label: string
  status?: string
  assigned_to?: string | null
  wpId?: string
  children?: TreeNode[]
}

const treeData = computed<TreeNode[]>(() => {
  const groups: Record<string, TreeNode> = {}
  const CYCLE_GROUPS: Record<string, string> = {
    A: 'A类 报表与调整',
    B: 'B类 穿行测试',
    C: 'C类 控制测试',
    D: 'D类 销售收入',
    E: 'E类 货币资金',
    F: 'F类 采购存货',
    G: 'G类 投资',
    H: 'H类 固定资产',
    I: 'I类 无形资产',
    J: 'J类 职工薪酬',
    K: 'K类 管理费用',
    L: 'L类 筹资',
    M: 'M类 股东权益',
    N: 'N类 税费',
    S: 'S类 专项程序',
  }

  const items = wpIndex.value.filter((w: WpIndexItem) => {
    if (filterCycle.value && !w.wp_code?.startsWith(filterCycle.value)) return false
    if (filterStatus.value && w.status !== filterStatus.value) return false
    if (filterAssignee.value && w.assigned_to !== filterAssignee.value) return false
    return true
  })

  // 已有底稿的循环前缀集合
  const existingPrefixes = new Set<string>()

  for (const wp of items) {
    const prefix = wp.wp_code?.charAt(0) || '?'
    existingPrefixes.add(prefix)
    const groupKey = prefix
    const groupLabel = CYCLE_GROUPS[prefix] || `${prefix}类 实质性程序`
    const matchedWorkpaper = wpList.value.find((item: WorkpaperDetail) => item.wp_index_id === wp.id)
    const isTrimmed = wp.status === 'not_applicable' || matchedWorkpaper?.status === 'not_applicable'

    // 提取科目名称：去掉常见底稿类型后缀，让树节点更简洁
    const wpName = wp.wp_name || ''
    const shortName = wpName
      .replace(/审定表$/, '')
      .replace(/明细表$/, '')
      .replace(/总控台$/, '')
      .replace(/函证$/, '')
      .replace(/测试表$/, '')
      .replace(/计算表$/, '')
      .replace(/汇总表$/, '')
      .replace(/变动表$/, '')
      .replace(/分析表$/, '')
      .replace(/核对表$/, '')
      .trim() || wpName

    if (!groups[groupKey]) {
      groups[groupKey] = { id: `group-${groupKey}`, label: groupLabel, children: [] }
    }
    groups[groupKey].children!.push({
      id: matchedWorkpaper?.id || wp.id,
      label: `${wp.wp_code} ${shortName}`,
      status: matchedWorkpaper?.status || wp.status || undefined,
      assigned_to: matchedWorkpaper?.assigned_to ?? wp.assigned_to,
      wpId: matchedWorkpaper?.id || wp.id,
      isTrimmed,
    } as any)
  }

  // 补充模板库中存在但项目未生成的循环（灰度显示为"未生成"）
  if (showTrimmedFilter.value === 'all') {
    for (const [prefix, label] of Object.entries(CYCLE_GROUPS)) {
      if (!existingPrefixes.has(prefix) && !filterCycle.value) {
        groups[prefix] = {
          id: `group-${prefix}`,
          label: `${label}`,
          children: [{
            id: `placeholder-${prefix}`,
            label: `${prefix} 循环底稿未生成（试算表中无对应科目）`,
            isTrimmed: true,
            isPlaceholder: true,
          } as any],
        }
      }
    }
  }

  // 裁剪筛选：active 模式下过滤掉全部裁剪的分组（但保留有活跃子项的分组）
  if (showTrimmedFilter.value === 'active') {
    for (const [key, group] of Object.entries(groups)) {
      const activeChildren = group.children?.filter((c: any) => !c.isTrimmed) || []
      const trimmedChildren = group.children?.filter((c: any) => c.isTrimmed) || []
      if (activeChildren.length === 0 && trimmedChildren.length > 0) {
        delete groups[key]
      }
    }
  }

  // Foundation Task 2.9: 注入循环级复核状态到 group 节点
  for (const [key, group] of Object.entries(groups)) {
    const stat = cycleReviewStats.value[key]
    if (stat) {
      ;(group as any).cycleCode = key
      ;(group as any).totalCount = stat.total_workpapers
      ;(group as any).reviewedCount = stat.reviewed_workpapers
    }
  }

  return Object.values(groups).sort((a, b) => a.label.localeCompare(b.label))
})

// Foundation Task 2.9: 点击循环徽章展开 per-workpaper 复核状态列表
function onCycleBadgeClick(data: any) {
  const stat = cycleReviewStats.value[data.cycleCode]
  if (!stat) return
  const lines = stat.workpapers.slice(0, 30).map((w: any) =>
    `${w.is_reviewed ? '✓' : '○'} ${w.wp_code} ${w.wp_name}`
  )
  ElMessage({
    message: `${stat.cycle_name}：${stat.reviewed_workpapers}/${stat.total_workpapers} 已复核\n${lines.join('\n')}`,
    type: 'info',
    duration: 6000,
    showClose: true,
  })
}



function onKanbanSelect(item: any) {
  if (item.wp_id) {
    // 切换到列表视图并自动选中对应底稿
    viewMode.value = 'list'
    // 等待列表视图渲染后再选中节点
    setTimeout(() => selectWorkpaperById(item.wp_id), 100)
  }
}

async function onKanbanAssign(item: any) {
  assigningItem.value = item
  assignForm.value = {
    assigned_to: item.assigned_to || null,
    reviewer: item.reviewer || null,
  }
  showAssignDialog.value = true
  // 加载用户列表（如果尚未加载）
  if (!userOptions.value.length) {
    try {
      userOptions.value = await listUsers()
    } catch {
      ElMessage.warning('加载用户列表失败')
    }
  }
}

async function onConfirmAssign() {
  if (!assigningItem.value?.wp_id) {
    ElMessage.warning('该底稿尚未生成，无法分配')
    return
  }
  assignLoading.value = true
  try {
    await assignWorkpaper(projectId.value, assigningItem.value.wp_id, {
      assigned_to: assignForm.value.assigned_to || null,
      reviewer: assignForm.value.reviewer || null,
    })
    ElMessage.success('分配成功')
    showAssignDialog.value = false
    // 刷新看板数据
    kanbanRef.value?.refresh()
  } catch (e: any) {
    handleApiError(e, '分配')
  } finally {
    assignLoading.value = false
  }
}

function goToWorkbench() {
  // 本地切换到工作台视图（不再跳转独立页面）
  viewMode.value = 'workbench'
}

// F2 修复 / v3 P0-5 / Q4：一键生成底稿（chain 端点）
const hasTrialBalance = ref(false)
const chainLoading = ref(false)

function _resolveYear(): number {
  return Number(route.query.year) || new Date().getFullYear()
}

async function checkTrialBalanceReady() {
  try {
    const r: any = await api.get(
      `/api/projects/${projectId.value}/trial-balance?year=${_resolveYear()}`,
      { validateStatus: (s: number) => s < 600 },
    )
    const rows = (r?.rows || r?.items || (Array.isArray(r) ? r : [])) as any[]
    hasTrialBalance.value = rows.length > 0
  } catch {
    hasTrialBalance.value = false
  }
}

async function onGenerateChain() {
  chainLoading.value = true
  try {
    await api.post(
      `/api/projects/${projectId.value}/workflow/execute-full-chain`,
      { year: _resolveYear(), force: true },
      { timeout: 120000 },
    )
    ElMessage.success('已生成底稿+附注，正在刷新...')
    await fetchData()
  } catch (e: any) {
    handleApiError(e, '一键生成 chain')
  } finally {
    chainLoading.value = false
  }
}

function _goToTemplates() {
  router.push(`/projects/${projectId.value}/templates`)
}

// ── 审计程序指南数据（右栏） ──
const _guideExpanded = ref('')

const auditCycleGuide = [
  { cycle: 'B', name: '初步业务活动/风险评估', color: '#7c5cbf', count: 56 },
  { cycle: 'C', name: '控制测试', color: '#6a4fa0', count: 50 },
  { cycle: 'D', name: '收入循环', color: '#e6553a', count: 17 },
  { cycle: 'E', name: '货币资金循环', color: '#d4a017', count: 5 },
  { cycle: 'F', name: '存货循环', color: '#2e86c1', count: 15 },
  { cycle: 'G', name: '投资循环', color: '#1a8a5c', count: 15 },
  { cycle: 'H', name: '固定资产循环', color: '#7d6608', count: 11 },
  { cycle: 'I', name: '无形资产循环', color: '#5b2c6f', count: 6 },
  { cycle: 'J', name: '职工薪酬循环', color: '#c0392b', count: 3 },
  { cycle: 'K', name: '管理循环', color: '#2980b9', count: 14 },
  { cycle: 'L', name: '债务循环', color: '#117a65', count: 9 },
  { cycle: 'M', name: '权益循环', color: '#4b2d77', count: 10 },
  { cycle: 'N', name: '税金循环', color: '#6c3483', count: 5 },
  { cycle: 'A', name: '完成阶段', color: '#1a8a5c', count: 59 },
  { cycle: 'S', name: '特定项目程序', color: '#7f8c8d', count: 87 },
]

function onGuideClick(cycle: string) {
  // 切换到工作台视图，按循环筛选
  viewMode.value = 'workbench'
  filterCycle.value = cycle
}

function onWpImported() {
  showWpImport.value = false
  fetchData()
}

// ════════════════════════════════════════════════════════════
// 新视图（生命周期/依赖图/委派矩阵）helpers
// ════════════════════════════════════════════════════════════

// 给 LifecycleView 和 AssignmentMatrix 提供合并好的 wp 列表（含 wp_code/wp_name）
const lifecycleWpItems = computed(() =>
  wpList.value.map((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    return {
      id: w.id,
      wp_code: w.wp_code || idx?.wp_code || '',
      wp_name: w.wp_name || idx?.wp_name || '',
      audit_cycle: w.audit_cycle || idx?.audit_cycle || '',
      status: w.status,
      review_status: w.review_status,
      assigned_to: w.assigned_to,
      reviewer: w.reviewer,
      wp_index_id: w.wp_index_id,
    }
  })
)

function onOpenWorkpaperById(wpId: string) {
  router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
}

function onMatrixAssign(payload: { wp_ids: string[]; member_id: string }) {
  selectedWpIds.value = payload.wp_ids
  showBatchAssign.value = true
}

function onMatrixCellClick(_payload: { member_id: string; cycle: string }) {
  // 只用作选中提示，真正分配走 onMatrixAssign
}

function onCycleNodeClick(code: string) {
  // 依赖图 wp_code → 跳转编辑器（必须有 WorkingPaper 记录才能编辑）
  const matchedIdx = wpIndex.value.find((i: WpIndexItem) => i.wp_code === code || i.wp_code?.startsWith(code + '-'))
  if (!matchedIdx) {
    ElMessage.info(`未找到底稿 ${code}（可能未生成）`)
    return
  }
  // 查找对应的 WorkingPaper 记录
  const wp = wpList.value.find((w: WorkpaperDetail) => w.wp_index_id === matchedIdx.id)
  if (wp) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: wp.id } })
  } else {
    // 有索引但无文件记录 → 切换到列表视图选中（不跳编辑器避免报错）
    viewMode.value = 'list'
    nextTick(() => selectWorkpaperById(matchedIdx.id))
    ElMessage.warning(`底稿 ${code} 尚未生成文件，请先在生命周期中生成`)
  }
}

async function fetchData() {
  loading.value = true
  try {
    const [wps, idx] = await Promise.all([
      listWorkpapers(projectId.value, {
        audit_cycle: filterCycle.value || undefined,
        status: filterStatus.value || undefined,
        assigned_to: filterAssignee.value || undefined,
      }),
      getWpIndex(projectId.value),
    ])
    wpList.value = wps
    wpIndex.value = idx.map((item) => {
      const matchedWorkpaper = wps.find((wp) => wp.wp_index_id === item.id)
      return {
        ...item,
        assigned_to: matchedWorkpaper?.assigned_to ?? item.assigned_to,
        reviewer: matchedWorkpaper?.reviewer ?? item.reviewer,
      }
    })
  } finally {
    loading.value = false
  }
  // F2 / Q4: 加载完底稿列表后检查是否有 TB 但无底稿（用于显示一键生成按钮）
  if (wpIndex.value.length === 0) {
    checkTrialBalanceReady()
  }
}

async function loadUnconfirmedAi() {
  if (!selectedWp.value) {
    unconfirmedAiCount.value = 0
    return
  }
  try {
    const result = await checkUnconfirmedAI(projectId.value, selectedWp.value.id)
    unconfirmedAiCount.value = Number(result?.unconfirmed_count || 0)
  } catch {
    unconfirmedAiCount.value = 0
  }
}

async function loadFineChecks() {
  if (!selectedWp.value) {
    fineCheckResults.value = []
    return
  }
  fineChecksLoading.value = true
  try {
    const { fineExtractWorkpaper } = await import('@/services/commonApi')
    const result = await fineExtractWorkpaper(projectId.value, selectedWp.value.id)
    fineCheckResults.value = result?.checks || []
  } catch {
    fineCheckResults.value = []
  } finally {
    fineChecksLoading.value = false
  }
}

function onCheckJump(chk: any) {
  // 根据检查类型跳转到对应位置
  const type = chk.type || ''
  if (type === 'balance' && chk.code?.includes('CHK-02')) {
    // 跳转到报表
    router.push({ path: `/projects/${projectId.value}/reports`, query: { highlight: 'BS-002' } })
  } else if (type === 'cross_ref' && chk.code?.includes('CHK-03')) {
    // 跳转到现金明细表（在线编辑）
    if (selectedWp.value) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: selectedWp.value.id } })
    }
  } else if (type === 'cross_ref' && chk.code?.includes('CHK-04')) {
    // 跳转到银行明细表
    if (selectedWp.value) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: selectedWp.value.id } })
    }
  } else if (type === 'balance' && chk.code?.includes('CHK-01')) {
    // 跳转到试算表
    router.push({ path: `/projects/${projectId.value}/trial-balance` })
  } else {
    // 默认跳转到底稿编辑
    if (selectedWp.value) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: selectedWp.value.id } })
    }
  }
}

async function loadTsjReviewPrompts() {
  if (!selectedWp.value) {
    tsjReviewData.value = null
    return
  }
  try {
    const wpName = selectedWp.value.wp_name || ''
    // 从底稿名称提取科目名（如"货币资金审定表"→"货币资金"）
    const accountName = wpName.replace(/审定表|明细表|程序表|汇总表|盘点表|调节表|核对表/g, '').trim()
    if (!accountName) { tsjReviewData.value = null; return }

    const { data } = await import('@/utils/http').then(m =>
      m.default.get(P.workpapers.wpMappingTsj(projectId.value, accountName), {
        validateStatus: (s: number) => s < 600,
      })
    )
    if (data?.tips?.length || data?.checklist?.length || data?.risk_areas?.length) {
      tsjReviewData.value = data
    } else {
      tsjReviewData.value = null
    }
  } catch {
    tsjReviewData.value = null
  }
}

async function selectWorkpaperByCode(wpCode: string): Promise<boolean> {
  // 联动全景图节点跳转入口：按 wp_code 查找节点 ID 后调用 selectWorkpaperById
  // tree node-key 是 working_paper.id（或 wp_index.id 当无 wp 记录时）
  // 优先精确匹配；如无则用前缀匹配（如 H1 匹配 H1-1/H1-13 第一个）
  const exact = wpList.value.find((w: WorkpaperDetail) => w.wp_code === wpCode)
  if (exact) {
    await selectWorkpaperById(exact.id)
    return true
  }
  const exactIdx = wpIndex.value.find((i: WpIndexItem) => i.wp_code === wpCode)
  if (exactIdx) {
    await selectWorkpaperById(exactIdx.id)
    return true
  }
  // 前缀匹配：H1 → H1-1 / H1-13 等
  const prefix = wpCode + '-'
  const prefixWp = wpList.value.find((w: WorkpaperDetail) => w.wp_code?.startsWith(prefix))
  if (prefixWp) {
    await selectWorkpaperById(prefixWp.id)
    return true
  }
  const prefixIdx = wpIndex.value.find((i: WpIndexItem) => i.wp_code?.startsWith(prefix))
  if (prefixIdx) {
    await selectWorkpaperById(prefixIdx.id)
    return true
  }
  return false
}

async function selectWorkpaperById(wpId: string) {
  // 设置 selectedWpId 触发 useWpDetailGuard 守卫刷新
  selectedWpId.value = wpId
  const wp = wpList.value.find((w: WorkpaperDetail) => w.wp_index_id === wpId || w.id === wpId)
  if (wp) {
    selectedWp.value = wp
  } else {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === wpId)
    if (idx) {
      selectedWp.value = {
        id: idx.id, project_id: projectId.value, wp_index_id: idx.id,
        file_path: null, source_type: 'template', status: idx.status || 'not_started',
        assigned_to: idx.assigned_to, reviewer: idx.reviewer,
        file_version: 1, last_parsed_at: null, created_at: null, updated_at: null,
        wp_code: idx.wp_code, wp_name: idx.wp_name, audit_cycle: idx.audit_cycle || undefined,
      }
    }
  }
  // 自动展开并滚动到选中节点
  if (treeRef.value && wpId) {
    try {
      treeRef.value.setCurrentKey(wpId)
      // 滚动到可视区域
      const el = document.querySelector('.el-tree-node.is-current')
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } catch { /* tree node may not exist */ }
  }
  qcResult.value = null
  annotations.value = []
  unconfirmedAiCount.value = 0
  if (selectedWp.value) {
    try { qcResult.value = await getQCResults(projectId.value, selectedWp.value.id) } catch { /* no QC yet */ }
    await loadAnnotations()
    await loadUnconfirmedAi()
    loadFineChecks()  // 非阻塞加载审计检查
    loadTsjReviewPrompts()  // 非阻塞加载TSJ复核提示词
  }
}

async function onNodeClick(data: TreeNode, _node: any, _event: any) {
  if (!data.wpId) return
  if ((data as any).isTrimmed) return // 裁剪的底稿不可选中
  await selectWorkpaperById(data.wpId)
}

/** 跳转到生命周期视图（useWpDetailGuard no_file/no_index 状态引导） */
function goToLifecycle() {
  viewMode.value = 'lifecycle'
}

// ─── 底稿右键菜单 [enterprise-linkage 3.10] ────────────────────────────────
const wpCtxVisible = ref(false)
const wpCtxX = ref(0)
const wpCtxY = ref(0)
let wpCtxNodeData: TreeNode | null = null

function onWpNodeContextMenu(event: Event, data: TreeNode, _node?: any) {
  if (!data.wpId) return // 只对叶子节点（底稿）显示菜单
  const e = event as MouseEvent
  e.preventDefault()
  wpCtxNodeData = data
  wpCtxX.value = e.clientX
  wpCtxY.value = e.clientY
  wpCtxVisible.value = true

  const closeHandler = () => {
    wpCtxVisible.value = false
    document.removeEventListener('click', closeHandler)
  }
  setTimeout(() => document.addEventListener('click', closeHandler), 0)
}

function onWpCtxTraceToTb() {
  wpCtxVisible.value = false
  if (!wpCtxNodeData) return
  // Extract account code from wp_code (first char is cycle letter, rest is account-related)
  // Navigate to trial balance with highlight
  const label = wpCtxNodeData.label || ''
  const wpCode = label.split(' ')[0] || ''
  router.push({
    path: `/projects/${projectId.value}/trial-balance`,
    query: { highlight_wp: wpCode },
  })
}

function onOnlineEdit() {
  if (!selectedWp.value) return
  // 检查是否有真实的 WorkingPaper 记录（非 wp_index 占位）
  const hasRealWp = wpList.value.some((w: WorkpaperDetail) => w.id === selectedWp.value!.id)
  if (!hasRealWp) {
    ElMessage.warning('该底稿尚未生成文件，请先在生命周期中执行"一键生成底稿"')
    return
  }
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: projectId.value, wpId: selectedWp.value.id },
  })
}

async function onDownload() {
  if (!selectedWp.value) return
  const code = selectedWp.value.wp_code || ''
  if (!code) {
    ElMessage.warning('当前底稿未绑定模板编码')
    return
  }
  try {
    await downloadTemplate(projectId.value, code)
  } catch (e: any) {
    handleApiError(e, '下载模板')
  }
}

function onUpload() {
  if (!selectedWp.value) return
  uploadFile.value = null
  uploadConflict.value = null
  uploadStep.value = 1
  parsedPreview.value = null
  pendingWpId.value = ''
  uploadDialogVisible.value = true
}

function onUploadFileChange(file: any) {
  uploadFile.value = file.raw
}

/** 格式化解析预览中的金额 */
function fmtParsed(v: number | null | undefined): string {
  if (v == null) return '-'
  return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)
}

/** 取消上传弹窗 */
function onUploadCancel() {
  uploadDialogVisible.value = false
  uploadStep.value = 1
  parsedPreview.value = null
  pendingWpId.value = ''
}

/** 步骤1：上传文件并触发解析预览（dry_run=true，不写入 parsed_data） */
async function doUploadStep1(forceOverwrite: boolean) {
  if (!selectedWp.value || !uploadFile.value) return
  uploadLoading.value = true
  try {
    const version = selectedWp.value.file_version || 1
    const result = await uploadWorkpaperFile(
      projectId.value,
      selectedWp.value.id,
      uploadFile.value,
      version,
      forceOverwrite,
    )
    uploadConflict.value = null
    uploadRef.value?.clearFiles?.()
    pendingWpId.value = selectedWp.value.id
    pendingNewVersion.value = result?.new_version || version + 1

    // 触发 dry_run 解析，仅获取预览数据，不写入 parsed_data
    parseLoading.value = true
    uploadStep.value = 2
    try {
      const parseResult = await parseWorkpaper(projectId.value, pendingWpId.value, true)
      // 后端返回 parsed_data 字段（完整预览）或直接返回顶层字段
      parsedPreview.value = parseResult?.parsed_data || parseResult || null
    } catch {
      parsedPreview.value = null
    } finally {
      parseLoading.value = false
    }
  } catch (err: any) {
    if (err.response?.status === 409) {
      uploadConflict.value = err.response.data?.detail || err.response.data
      ElMessage.warning('版本冲突，请选择操作')
    } else {
      handleApiError(err, '上传')
    }
  } finally {
    uploadLoading.value = false
  }
}

/** 步骤2：用户确认识别数据，正式调用 parse（dry_run=false）写入 parsed_data */
async function doConfirmParsed() {
  if (!pendingWpId.value) return
  parseLoading.value = true
  try {
    // 正式解析写入（dry_run=false）
    await parseWorkpaper(projectId.value, pendingWpId.value, false)
    uploadDialogVisible.value = false
    uploadStep.value = 1
    parsedPreview.value = null
    // 刷新底稿状态
    await fetchData()
    await selectWorkpaperById(pendingWpId.value)
    // 通知试算表刷新（五环联动：上传→解析→试算表更新→报表更新）
    eventBus.emit('workpaper:parsed', { projectId: projectId.value, wpId: pendingWpId.value })
    ElMessage.success(`底稿已上传（v${pendingNewVersion.value}），识别数据已写入`)
    pendingWpId.value = ''
  } catch (e: any) {
    handleApiError(e, '写入识别数据')
  } finally {
    parseLoading.value = false
  }
}

/** 兼容旧调用（handleUploadRedirect 中使用） */
async function doUpload(forceOverwrite: boolean) {
  await doUploadStep1(forceOverwrite)
}

async function onBatchDownload() {
  downloadLoading.value = true
  try {
    await downloadAllTemplates(projectId.value)
    ElMessage.success('全部底稿模板下载完成')
  } catch (e: any) {
    handleApiError(e, '批量下载模板')
  } finally {
    downloadLoading.value = false
  }
}

function onCheckChange() {
  if (!treeRef.value) return
  const checked = treeRef.value.getCheckedNodes(true) // leaf only
  selectedWpIds.value = checked.filter((n: any) => n.wpId).map((n: any) => n.wpId)
}

async function onQCCheck() {
  if (!selectedWp.value) return
  qcLoading.value = true
  try {
    qcResult.value = await runQCCheck(projectId.value, selectedWp.value.id)
    ElMessage.success('自检完成')
  } catch (e: any) {
    handleApiError(e, '自检')
  } finally {
    qcLoading.value = false
  }
}

async function onSubmitReview() {
  if (!selectedWp.value) return
  // 引导提示
  const { showGuide } = await import('@/composables/useWorkflowGuide')
  const ok = await showGuide(
    'submit_review',
    '📤 提交复核',
    `<div style="line-height:1.8;font-size: var(--gt-font-size-sm)">
      <p>将底稿 <b>${selectedWp.value.wp_code || ''}</b> 提交给复核人审阅。</p>
      <p style="color: var(--gt-color-info);font-size: var(--gt-font-size-xs);margin-top:6px">请确认以下条件已满足：</p>
      <ul style="padding-left:18px;margin:4px 0">
        <li><span style="color: var(--gt-color-wheat)">⚠</span> 底稿内容已编制完成</li>
        <li><span style="color: var(--gt-color-wheat)">⚠</span> 已分配复核人</li>
        <li><span style="color: var(--gt-color-wheat)">⚠</span> 质量自检（QC）无阻断级问题</li>
        <li><span style="color: var(--gt-color-wheat)">⚠</span> 所有未解决的复核意见已回复</li>
      </ul>
      <p style="color: var(--gt-color-info);font-size: var(--gt-font-size-xs);margin-top:6px">💡 不满足条件时系统会自动阻断并提示具体原因</p>
    </div>`,
    '提交复核',
  )
  if (!ok) return
  submitLoading.value = true
  gateState.value = 'evaluating'
  gateHitRules.value = []
  gateTraceId.value = ''
  try {
    const currentWpId = selectedWp.value.id
    // 使用专用提交复核端点（后端统一校验门禁引擎 + 4 项门禁）
    const data = await submitWorkpaperReview(projectId.value, selectedWp.value.id)
    if (data?.status === 'blocked') {
      // Phase 14: 展示门禁阻断面板
      gateState.value = 'blocked'
      gateHitRules.value = data.hit_rules || []
      gateTraceId.value = data.trace_id || ''
      if (!gateHitRules.value.length) {
        // 旧格式兼容
        ElMessage.warning(`无法提交复核：${(data.blocking_reasons || []).join('；')}`)
      }
      return
    }
    gateState.value = 'normal'
    ElMessage.success('已提交复核')
    await fetchData()
    await selectWorkpaperById(currentWpId)
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    if (detail?.hit_rules) {
      // 409 门禁阻断响应
      gateState.value = 'blocked'
      gateHitRules.value = detail.hit_rules || []
      gateTraceId.value = detail.trace_id || ''
    } else if (detail?.error_code === 'SOD_CONFLICT_DETECTED') {
      // SoD 冲突
      sodConflictType.value = detail.message || ''
      sodPolicyCode.value = detail.policy_code || ''
      sodTraceId.value = detail.trace_id || ''
      showSodDialog.value = true
    } else {
      gateState.value = 'error'
      gateTraceId.value = detail?.trace_id || ''
      handleApiError(err, '提交')
    }
  } finally {
    submitLoading.value = false
  }
}

// Phase 14: 门禁阻断项跳转处理
function handleGateJump(location: Record<string, any>) {
  const section = location.section
  if (section === 'procedure_status' && location.procedure_ids?.length) {
    // 跳转到程序裁剪页
    router.push(`/projects/${projectId.value}/procedures?highlight=${location.procedure_ids[0]}`)
  } else if (section === 'audit_explanation') {
    // 跳转到底稿工作台说明编辑区
    router.push(`/projects/${projectId.value}/workpaper-bench`)
  } else if (section === 'audit_conclusion') {
    router.push(`/projects/${projectId.value}/workpaper-bench`)
  } else if (section === 'consistency') {
    // 跳转到一致性看板
    router.push(`/projects/${projectId.value}/consistency`)
  } else if (section === 'disclosure_notes') {
    router.push(`/projects/${projectId.value}/disclosure-notes`)
  } else if (section === 'audit_report') {
    router.push(`/projects/${projectId.value}/audit-report`)
  }
}

async function loadAnnotations() {
  if (!selectedWp.value) { annotations.value = []; return }
  try {
    annotations.value = await listWorkpaperAnnotations(projectId.value, 'workpaper', selectedWp.value.id)
  } catch { annotations.value = [] }
}

async function submitAnnotation() {
  if (!selectedWp.value || !newAnnotation.value.content) return
  try {
    await createAnnotation(projectId.value, {
      object_type: 'workpaper',
      object_id: selectedWp.value.id,
      content: newAnnotation.value.content,
      priority: newAnnotation.value.priority,
    })
    ElMessage.success('复核意见已提交')
    showAddAnnotation.value = false
    newAnnotation.value = { content: '', priority: 'medium' }
    await loadAnnotations()
  } catch (e: any) { handleApiError(e, '提交') }
}

async function resolveAnnotation(id: string) {
  try {
    await updateAnnotation(id, { status: 'resolved' })
    ElMessage.success('已标记为解决')
    await loadAnnotations()
    await loadUnconfirmedAi()
  } catch (e: any) { handleApiError(e, '操作') }
}

// 回复批注
const showReplyDialog = ref(false)
const replyTarget = ref<any>(null)
const replyContent = ref('')

function replyAnnotation(row: any) {
  replyTarget.value = row
  replyContent.value = ''
  showReplyDialog.value = true
}

async function _submitReply() {
  if (!replyTarget.value || !replyContent.value) return
  try {
    await updateAnnotation(replyTarget.value.id, { status: 'replied', reply_content: replyContent.value })
    ElMessage.success('回复已提交')
    showReplyDialog.value = false
    await loadAnnotations()
  } catch (e: any) { handleApiError(e, '回复') }
}

function onRejectClick() {
  if (!selectedWp.value) return
  rejectingWpId.value = selectedWp.value.id
  rejectReason.value = ''
  showRejectDialog.value = true
}

async function onConfirmReject() {
  if (!rejectingWpId.value || !rejectReason.value.trim()) return
  const rs = selectedWp.value?.review_status
  const rejectStatus = (rs === 'pending_level2' || rs === 'level2_in_progress')
    ? 'level2_rejected' : 'level1_rejected'
  try {
    await updateReviewStatus(projectId.value, rejectingWpId.value, rejectStatus, rejectReason.value)
    showRejectDialog.value = false
    ElMessage.success('已退回')
    await fetchData()
    await selectWorkpaperById(rejectingWpId.value)
  } catch (err: any) {
    handleApiError(err, '退回')
  }
}

async function onReviewPass() {
  if (!selectedWp.value) return
  // 强制检查：所有批注必须已解决
  if (unresolvedCount.value > 0) {
    try {
      const result = await confirmForcePass('当前有 ' + unresolvedCount.value + ' 条未解决的复核意见，建议先处理后再通过复核。确定强制通过吗？')
      // result.note 可用于记录强制通过原因（如需要）
      void result
    } catch {
      return  // 用户选择返回处理
    }
  }
  const rs = selectedWp.value.review_status
  const passStatus = (rs === 'pending_level2' || rs === 'level2_in_progress')
    ? 'level2_passed' : 'level1_passed'
  try {
    await updateReviewStatus(projectId.value, selectedWp.value.id, passStatus)
    ElMessage.success('复核通过')
    await fetchData()
    await selectWorkpaperById(selectedWp.value.id)
  } catch (err: any) {
    handleApiError(err, '操作')
  }
}

async function refreshOnlineEditState() {
  // Univer 纯前端，无需探测服务可用性
  onlineEditEnabled.value = true
  onlineEditAvailable.value = true
}

async function handleUploadRedirect() {
  const uploadWpId = typeof route.query.upload === 'string' ? route.query.upload : ''
  if (!uploadWpId) return
  await selectWorkpaperById(uploadWpId)
  if (selectedWp.value?.id === uploadWpId) {
    onUpload()
  }
  const nextQuery = { ...route.query }
  delete nextQuery.upload
  await router.replace({ query: nextQuery })
}

watch([filterCycle, filterStatus, filterAssignee], () => fetchData())
onMounted(async () => {
  // 从 URL query 读取视图模式（用于 /workpaper-bench 重定向兼容）
  const queryView = route.query.view as string
  if (queryView && ['list', 'kanban', 'workbench', 'lifecycle', 'graph', 'matrix'].includes(queryView)) {
    viewMode.value = queryView
  }
  await fetchData()
  // 加载项目名称
  try {
    const { default: http } = await import('@/utils/http')
    const resp = await http.get(`/api/projects/${projectId.value}`)
    const proj = resp.data
    projectName.value = proj?.name || proj?.project_name || ''
  } catch { /* 静默 */ }
  // 任务 8.17.1：加载用户列表，同时赋值 userOptions 和 userNameMap
  try {
    const users = await listUsers()
    userOptions.value = users
    userNameMap.value = new Map(
      users.map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch {
    ElMessage.warning('加载用户列表失败')
  }
  try {
    const maturity = await getFeatureMaturity()
    onlineEditMaturity.value = maturity?.online_editing || 'pilot'
  } catch { /* 默认 pilot */ }
  await refreshOnlineEditState()
  await handleUploadRedirect()

  // 联动全景图跳转入口：query.wp_code 触发底稿预选
  const wpCodeQuery = typeof route.query.wp_code === 'string' ? route.query.wp_code : ''
  if (wpCodeQuery) {
    // 等 tree 渲染完成再调 setCurrentKey
    await nextTick()
    const found = await selectWorkpaperByCode(wpCodeQuery)
    if (!found) {
      ElMessage.warning(`底稿 ${wpCodeQuery} 在当前项目中尚未创建`)
    }
  }

  // Foundation Task 2.9: 初次加载循环复核状态 + 订阅 review-mark:changed 事件刷新
  await loadCycleReviewStatus()
  eventBus.on('review-mark:changed', _scheduleReviewStatusReload)
})

// V3 Req 5.1：上下文（projectId/year）变化时自动重载底稿列表
onContextChange(async () => {
  await fetchData()
  await loadCycleReviewStatus()
})
</script>

<style scoped>
.gt-wp-list { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; }
.gt-wp-filter-bar {
  display: flex; align-items: center; gap: 8px; margin-bottom: var(--gt-space-3);
  padding: 8px 12px; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); flex-wrap: nowrap; overflow-x: auto;
}
.gt-wp-view-toggle { margin: 0 12px; }
.gt-wp-filters { display: flex; gap: var(--gt-space-2); align-items: center; }
.gt-wp-body { display: flex; gap: var(--gt-space-4); flex: 1; min-height: 0; }
.gt-wp-tree-panel {
  width: 360px; min-width: 360px; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-3); overflow-y: auto;
}
.gt-wp-detail-panel {
  flex: 1; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-5); overflow-y: auto;
}
/* useWpDetailGuard 三态提示横幅 */
.gt-wp-detail-guard-hint {
  display: flex; align-items: center; gap: 8px; padding: 10px 14px;
  border-radius: var(--gt-radius-md); margin-bottom: 12px; font-size: 13px;
}
.gt-wp-detail-guard-hint--loading {
  background: var(--gt-color-primary-bg, #f5f0ff); color: var(--gt-color-primary);
}
.gt-wp-detail-guard-hint--warning {
  background: var(--gt-bg-warning, #fdf6ec); color: var(--gt-color-warning, #e6a23c);
}
.gt-wp-detail-guard-hint--error {
  background: var(--gt-bg-danger, #fef0f0); color: var(--gt-color-danger, #f56c6c);
}
.gt-wp-tree-node { display: flex; align-items: center; gap: 6px; width: 100%; padding: 4px 0; }
.gt-wp-tree-node.is-trimmed { opacity: 0.45; pointer-events: none; }
.gt-wp-tree-node.is-trimmed .gt-wp-tree-node-label { text-decoration: line-through; color: var(--gt-color-text-tertiary); }
.gt-wp-tree-node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.gt-wp-tree-node-trim-tag { flex-shrink: 0; font-size: 10px; }
.gt-wp-tree-node-tag { flex-shrink: 0; }
.gt-wp-tree-stale-badge { flex-shrink: 0; font-size: var(--gt-font-size-xs); opacity: 0.85; cursor: help; }
.gt-wp-tree-cycle-badge { flex-shrink: 0; cursor: pointer; margin-left: 4px; }
.gt-wp-detail-card { }
.gt-wp-detail-title { margin: 0 0 var(--gt-space-4); color: var(--gt-color-primary); font-size: var(--gt-font-size-xl); }
.gt-wp-detail-actions { display: flex; gap: var(--gt-space-2); margin-top: var(--gt-space-4); flex-wrap: wrap; }
.gt-wp-qc-summary-inline { margin-top: var(--gt-space-3); display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wp-qc-counts { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }

/* 加载中全宽 */
.gt-wp-empty-full {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); min-height: 300px;
}

/* 全宽空状态 */
.gt-wp-empty-full {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); min-height: 300px;
}
.gt-wp-empty-icon { font-size: 48px; /* allow-px: emoji-icon (空状态大图标) */ margin-bottom: 12px; opacity: 0.7; }
.gt-wp-empty-title { font-size: var(--gt-font-size-xl); font-weight: 600; color: var(--gt-color-text-regular); margin-bottom: 6px; }
.gt-wp-empty-desc { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); }
/* 精细化审计检查 */
.gt-fine-check-item {
  display: flex; align-items: center; gap: 8px; padding: 4px 8px;
  font-size: var(--gt-font-size-xs); border-radius: 4px; margin-bottom: 2px;
}
.gt-fine-check-pass { background: var(--gt-bg-success); }
.gt-fine-check-fail { background: var(--gt-bg-warning); }
.gt-fine-check-pending { background: var(--gt-color-bg); }
.gt-fine-check-code { font-weight: 600; color: var(--gt-color-text-secondary); min-width: 70px; }
.gt-fine-check-desc { flex: 1; color: var(--gt-color-text-primary); }
.gt-fine-check-status { font-size: var(--gt-font-size-xs); white-space: nowrap; }
:deep(.gt-ann-row-urgent) { background: var(--gt-bg-danger) !important; }

/* 解析预览数值样式 */
.gt-parsed-value { color: var(--gt-color-primary); font-weight: 600; }
.gt-parsed-empty { color: var(--gt-color-text-tertiary); font-style: italic; }
.gt-parsed-diff { color: var(--gt-color-coral); font-weight: 600; }

/* ── 两栏引导布局 ── */
.gt-wp-intro-layout {
  flex: 1; display: flex; gap: var(--gt-space-4); min-height: 0;
}
.gt-wp-intro-half {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-5);
}
.gt-wp-intro-half--guide {
  align-items: stretch; justify-content: flex-start; overflow-y: auto;
}
.gt-wp-intro-icon { font-size: 48px; /* allow-px: emoji-icon (引导页大图标) */ margin-bottom: 12px; opacity: 0.7; }
.gt-wp-intro-title { font-size: var(--gt-font-size-xl); font-weight: 600; color: var(--gt-color-text-regular); margin-bottom: 6px; }
.gt-wp-intro-desc { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); text-align: center; }

.gt-wp-guide-title {
  margin: 0 0 12px; font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-primary);
}

/* 流程横条 */
.gt-wp-guide-flow {
  display: flex; align-items: center; gap: 6px; margin-bottom: 16px;
  padding: 10px 12px; background: var(--gt-color-primary-bg); border-radius: 8px; flex-wrap: wrap;
}
.gt-wp-flow-tag {
  display: inline-block; padding: 3px 10px; border-radius: 10px;
  font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-text-inverse); white-space: nowrap;
}
.gt-wp-flow-arrow { color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-sm); }

/* 循环列表 */
.gt-wp-guide-list { display: flex; flex-direction: column; }
.gt-wp-guide-row {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-bottom: 1px solid var(--gt-color-border-light); cursor: pointer; border-radius: 6px;
  transition: background 0.15s;
}
.gt-wp-guide-row:hover { background: var(--gt-color-primary-bg); }
.gt-wp-guide-row:last-child { border-bottom: none; }
.gt-wp-guide-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 26px; height: 22px; padding: 0 7px;
  border-radius: 11px; font-size: var(--gt-font-size-xs); font-weight: 700; color: var(--gt-color-text-inverse);
}
.gt-wp-guide-name { flex: 1; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-primary); }
.gt-wp-guide-count { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); white-space: nowrap; }
.gt-wp-guide-arrow { font-size: var(--gt-font-size-md); color: var(--gt-color-text-placeholder); font-weight: 300; }

/* 进度条区域 */
.gt-wp-progress-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 16px; margin-bottom: var(--gt-space-3);
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary);
  border-left: 3px solid var(--gt-color-primary);
}

/* 工作台视图（合并自 WorkpaperWorkbench） */
.gt-wp-workbench-view {
  flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--gt-space-3);
}
.gt-wpb-progress-summary {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;
  padding: 12px; background: var(--gt-color-bg-white); border-radius: 0 0 var(--gt-radius-md) var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
}
/* 进度区头部 */
.gt-wpb-progress-header {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md) var(--gt-radius-md) 0 0;
  box-shadow: var(--gt-shadow-sm); border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wpb-progress-header__title { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); flex: 1; }
.gt-wpb-progress-header__filter-tag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px; border-radius: 4px; font-size: 12px;
  background: var(--gt-color-primary-bg, #f0ebff); color: var(--gt-color-primary); font-weight: 500;
}
.gt-wpb-progress-header__clear {
  cursor: pointer; font-size: 14px; opacity: 0.7; transition: opacity 0.15s;
}
.gt-wpb-progress-header__clear:hover { opacity: 1; }
.gt-wpb-prog-card {
  padding: 10px 12px; background: var(--gt-color-bg-light, #f8f7fc);
  border-radius: var(--gt-radius-sm); border: 1px solid var(--gt-color-border, #e8e5f0);
  cursor: pointer; transition: all 0.15s;
}
.gt-wpb-prog-card:hover { border-color: var(--gt-color-primary); background: var(--gt-color-primary-bg, #f8f5ff); }
.gt-wpb-prog-card.is-active {
  border-color: var(--gt-color-primary); background: var(--gt-color-primary-bg, #f0ebff);
  box-shadow: 0 0 0 2px rgba(103, 80, 164, 0.15);
}
.gt-wpb-prog-card__header {
  display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px;
}
.gt-wpb-prog-card__code {
  font-size: 14px; font-weight: 700; color: var(--gt-color-primary);
}
.gt-wpb-prog-card__name {
  font-size: 12px; color: var(--gt-color-text-secondary);
}
.gt-wpb-prog-card__detail {
  font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 4px;
}
.gt-wpb-workbench-list {
  flex: 1; min-height: 0; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); padding: 12px; box-shadow: var(--gt-shadow-sm);
}
.gt-text-tertiary { color: var(--gt-color-text-tertiary, #999); }

/* Task 2.3-2.4: 角色视图集成样式 */
.gt-wp-role-summary-panel {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 8px 12px; margin-bottom: var(--gt-space-3);
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); font-size: var(--gt-font-size-sm);
  border-left: 3px solid var(--gt-color-primary);
}
.gt-wp-role-summary-label { color: var(--gt-color-text-secondary); font-weight: 600; }
.gt-wp-role-summary-item { color: var(--gt-color-text-primary); }
.gt-wp-role-summary-item strong { color: var(--gt-color-primary); margin-left: 4px; }
.gt-wp-tree-node-warn { font-size: 14px; flex-shrink: 0; cursor: help; }
.gt-wp-tree-node-badge { flex-shrink: 0; margin-left: 4px; }
.gt-wp-tree-node-review-mark {
  flex-shrink: 0; font-size: var(--gt-font-size-xs); font-weight: 600;
  color: var(--gt-color-success); margin-left: 4px;
}

/* ── 用户手册视图 ── */
.gt-wp-guide-view {
  flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 16px;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: 20px 24px; overflow-y: auto;
}
.gt-wp-guide-view__nav {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  padding-bottom: 12px; border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-guide-section { }
.gt-wp-guide-section__title {
  margin: 0 0 6px; font-size: 16px; font-weight: 600; color: var(--gt-color-text-primary);
}
.gt-wp-guide-section__desc {
  margin: 0 0 20px; font-size: 13px; color: var(--gt-color-text-tertiary); line-height: 1.6;
}

/* 体系总览网格 */
.gt-wp-guide-overview-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px;
}
.gt-wp-guide-overview-card {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px;
  border: 1px solid var(--gt-color-border-light, #f0f0f0); border-radius: 10px;
  cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-overview-card:hover {
  background: var(--gt-color-primary-bg, #f8f5ff); border-color: var(--gt-color-primary);
}
.gt-wp-guide-overview-card__badge {
  min-width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
  border-radius: 8px; font-size: 14px; font-weight: 700; color: #fff;
}
.gt-wp-guide-overview-card__info { flex: 1; min-width: 0; }
.gt-wp-guide-overview-card__name { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-overview-card__meta { font-size: 12px; color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-wp-guide-overview-card__arrow { font-size: 18px; color: var(--gt-color-text-placeholder); }
.gt-wp-guide-legend {
  display: flex; gap: 16px; margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-guide-legend__item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--gt-color-text-secondary); }
.gt-wp-guide-legend__dot { width: 10px; height: 10px; border-radius: 3px; }

/* 审计流程图 */
.gt-wp-guide-flow-chart {
  display: flex; align-items: flex-start; gap: 0; flex-wrap: wrap; justify-content: center;
  padding: 20px 0; margin-bottom: 20px;
}
.gt-wp-guide-flow-step { display: flex; align-items: center; }
.gt-wp-guide-flow-step__node {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 16px 20px; border: 2px solid; border-radius: 12px;
  background: var(--gt-color-bg-white); min-width: 120px; text-align: center;
}
.gt-wp-guide-flow-step__icon { font-size: 24px; }
.gt-wp-guide-flow-step__label { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-flow-step__sub { font-size: 11px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-flow-step__arrow { font-size: 20px; color: var(--gt-color-text-placeholder); margin: 0 8px; }

/* 流程详情 */
.gt-wp-guide-flow-detail { display: flex; flex-direction: column; gap: 12px; }
.gt-wp-guide-flow-detail__item {
  padding: 12px 16px; border-radius: 8px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-guide-flow-detail__header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.gt-wp-guide-flow-detail__badge {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border-radius: 6px; font-size: 14px;
}
.gt-wp-guide-flow-detail__name { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-flow-detail__sub-tag {
  font-size: 11px; color: var(--gt-color-text-tertiary); padding: 2px 8px;
  background: var(--gt-color-bg, #fafafa); border-radius: 4px;
}
.gt-wp-guide-flow-detail__desc { font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 12px; line-height: 1.6; }

/* 风险导向要点 */
.gt-wp-guide-flow-risk {
  display: flex; align-items: flex-start; gap: 6px; margin-bottom: 10px;
  padding: 8px 12px; background: #fff8e1; border-radius: 6px; border-left: 3px solid #f9a825;
}
.gt-wp-guide-flow-risk__icon { flex-shrink: 0; }
.gt-wp-guide-flow-risk__text { font-size: 12px; color: #e65100; line-height: 1.5; font-weight: 500; }

/* 关键工作列表 */
.gt-wp-guide-flow-actions { margin-bottom: 12px; }
.gt-wp-guide-flow-actions__title { font-size: 12px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 6px; }
.gt-wp-guide-flow-actions__list { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-flow-actions__item {
  display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--gt-color-text-secondary); line-height: 1.5;
}
.gt-wp-guide-flow-actions__bullet {
  flex-shrink: 0; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center;
  border-radius: 50%; background: var(--gt-color-primary-bg, #f0ebff); color: var(--gt-color-primary);
  font-size: 10px; font-weight: 700;
}

/* 关联底稿 */
.gt-wp-guide-flow-wps { margin-bottom: 10px; }
.gt-wp-guide-flow-wps__title { font-size: 12px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 6px; }
.gt-wp-guide-flow-wps__list { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-flow-wps__item {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  border-radius: 6px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
  cursor: pointer; transition: all 0.15s; font-size: 12px;
}
.gt-wp-guide-flow-wps__item:hover { background: var(--gt-color-primary-bg, #f8f5ff); border-color: var(--gt-color-primary); }
.gt-wp-guide-flow-wps__code { font-weight: 700; color: var(--gt-color-primary); min-width: 36px; }
.gt-wp-guide-flow-wps__name { font-weight: 600; color: var(--gt-color-text-primary); min-width: 120px; }
.gt-wp-guide-flow-wps__rel { flex: 1; color: var(--gt-color-text-tertiary); }

/* 阶段衔接提示 */
.gt-wp-guide-flow-next {
  font-size: 12px; color: var(--gt-color-primary); font-weight: 500;
  padding: 6px 10px; background: var(--gt-color-primary-bg, #f8f5ff);
  border-radius: 6px; margin-top: 4px;
}
.gt-wp-guide-flow-arrow-text { font-size: 10px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-flow-detail__outputs { font-size: 12px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-flow-detail__output-tag {
  display: inline-block; padding: 2px 8px; margin: 2px 4px; border-radius: 4px;
  background: var(--gt-color-primary-bg, #f8f5ff); color: var(--gt-color-primary);
  font-weight: 600; cursor: pointer; transition: background 0.15s;
}
.gt-wp-guide-flow-detail__output-tag:hover { background: var(--gt-color-primary); color: #fff; }

/* 底稿关系图 - 数据流转主线 */
.gt-wp-guide-dataflow {
  margin-bottom: 24px; padding: 16px; background: var(--gt-color-bg, #fafafa); border-radius: 12px;
}
.gt-wp-guide-dataflow__title { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 12px; }
.gt-wp-guide-dataflow__chain {
  display: flex; align-items: center; gap: 0; overflow-x: auto; padding: 8px 0;
}
.gt-wp-guide-dataflow__step { display: flex; align-items: center; }
.gt-wp-guide-dataflow__node {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 10px 14px; background: var(--gt-color-bg-white); border-radius: 10px;
  border: 1px solid var(--gt-color-border-light, #e8e8e8); min-width: 70px;
}
.gt-wp-guide-dataflow__icon { font-size: 20px; }
.gt-wp-guide-dataflow__name { font-size: 11px; font-weight: 600; color: var(--gt-color-text-primary); white-space: nowrap; }
.gt-wp-guide-dataflow__arrow {
  display: flex; flex-direction: column; align-items: center; gap: 2px; margin: 0 6px;
}
.gt-wp-guide-dataflow__arrow-label { font-size: 10px; color: var(--gt-color-text-tertiary); white-space: nowrap; }
.gt-wp-guide-dataflow__arrow-icon { font-size: 16px; color: var(--gt-color-primary); }

/* 模块关系详解 */
.gt-wp-guide-modules { margin-bottom: 20px; }
.gt-wp-guide-modules__title { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 12px; }
.gt-wp-guide-modules__grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px;
}
.gt-wp-guide-module-card {
  padding: 14px 16px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
  border-radius: 10px; transition: border-color 0.15s;
}
.gt-wp-guide-module-card:hover { border-color: var(--gt-color-primary); }
.gt-wp-guide-module-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.gt-wp-guide-module-card__icon {
  width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
  border-radius: 8px; font-size: 16px;
}
.gt-wp-guide-module-card__name { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-module-card__desc { font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 10px; line-height: 1.5; }
.gt-wp-guide-module-card__connections { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-module-card__conn {
  display: flex; align-items: center; gap: 6px; font-size: 12px;
  padding: 4px 8px; border-radius: 4px; background: var(--gt-color-bg, #fafafa);
}
.gt-wp-guide-module-card__conn-dir { font-weight: 700; font-size: 14px; }
.gt-wp-guide-module-card__conn-dir.is-out { color: var(--gt-color-primary); }
.gt-wp-guide-module-card__conn-dir.is-in { color: var(--gt-color-success); }
.gt-wp-guide-module-card__conn-to { font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-module-card__conn-label { flex: 1; color: var(--gt-color-text-secondary); }
.gt-wp-guide-module-card__conn-style {
  padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600;
}
.gt-wp-guide-module-card__conn-style.is-auto { background: #e8f5e9; color: #2e7d32; }
.gt-wp-guide-module-card__conn-style.is-manual { background: #fff3e0; color: #e65100; }

/* 关键说明 */
.gt-wp-guide-relation-notes { margin-bottom: 16px; }
.gt-wp-guide-relation-notes__title { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 10px; }
.gt-wp-guide-relation-notes__list { display: flex; flex-direction: column; gap: 8px; }
.gt-wp-guide-relation-notes__item {
  font-size: 13px; color: var(--gt-color-text-secondary); line-height: 1.6;
  padding: 8px 12px; border-radius: 6px; background: var(--gt-color-bg, #fafafa);
  border-left: 3px solid var(--gt-color-primary);
}
.gt-wp-guide-relation-notes__item strong { color: var(--gt-color-text-primary); }

.gt-wp-guide-relation-legend { display: flex; gap: 20px; margin-top: 12px; }
.gt-wp-guide-relation-legend__item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--gt-color-text-secondary); }
.gt-wp-guide-relation-legend__dot { width: 10px; height: 10px; border-radius: 3px; }

/* 循环详解 */
.gt-wp-guide-cycles-grid { display: flex; flex-direction: column; gap: 8px; }
.gt-wp-guide-cycle-card {
  border: 1px solid var(--gt-color-border-light, #f0f0f0); border-radius: 10px;
  overflow: hidden; cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-cycle-card:hover { border-color: var(--gt-color-primary); }
.gt-wp-guide-cycle-card.is-active { border-color: var(--gt-color-primary); background: var(--gt-color-primary-bg, #faf8ff); }
.gt-wp-guide-cycle-card__header {
  display: flex; align-items: center; gap: 10px; padding: 12px 16px;
}
.gt-wp-guide-cycle-card__badge {
  min-width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border-radius: 6px; font-size: 13px; font-weight: 700; color: #fff;
}
.gt-wp-guide-cycle-card__name { flex: 1; font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-wp-guide-cycle-card__count { font-size: 12px; color: var(--gt-color-text-tertiary); }
.gt-wp-guide-cycle-card__body { padding: 0 16px 14px; }
.gt-wp-guide-cycle-card__desc { font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 10px; }
.gt-wp-guide-cycle-card__wp-list { display: flex; flex-direction: column; gap: 4px; }
.gt-wp-guide-cycle-card__wp-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  border-radius: 6px; transition: background 0.15s;
}
.gt-wp-guide-cycle-card__wp-item:hover { background: var(--gt-color-bg-white); }
.gt-wp-guide-cycle-card__wp-code { font-size: 12px; font-weight: 600; color: var(--gt-color-primary); min-width: 50px; }
.gt-wp-guide-cycle-card__wp-name { flex: 1; font-size: 13px; color: var(--gt-color-text-primary); }
.gt-wp-guide-cycle-card__wp-arrow { font-size: 14px; color: var(--gt-color-text-placeholder); }

/* 核心底稿区块 */
.gt-wp-guide-cycle-core { margin-bottom: 14px; }
.gt-wp-guide-cycle-core__title {
  font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 8px;
}
.gt-wp-guide-cycle-core__list { display: flex; flex-direction: column; gap: 8px; }
.gt-wp-guide-cycle-core__item {
  padding: 10px 12px; border-radius: 8px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
  cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-cycle-core__item:hover { background: var(--gt-color-bg-white); border-color: var(--gt-color-primary); }
.gt-wp-guide-cycle-core__item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.gt-wp-guide-cycle-core__code { font-size: 13px; font-weight: 700; color: var(--gt-color-primary); }
.gt-wp-guide-cycle-core__name { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); flex: 1; }
.gt-wp-guide-cycle-core__detail { font-size: 12px; color: var(--gt-color-text-secondary); line-height: 1.5; }

/* 关联循环区块 */
.gt-wp-guide-cycle-rel { margin-bottom: 14px; }
.gt-wp-guide-cycle-rel__title {
  font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 4px;
}
.gt-wp-guide-cycle-rel__desc {
  font-size: 12px; color: var(--gt-color-text-secondary); margin-bottom: 8px; line-height: 1.5;
}
.gt-wp-guide-cycle-rel__tags { display: flex; flex-wrap: wrap; gap: 6px; }
.gt-wp-guide-cycle-rel__tag {
  display: inline-block; padding: 4px 10px; border-radius: 6px;
  background: var(--gt-color-primary-bg, #f8f5ff); color: var(--gt-color-primary);
  font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s;
}
.gt-wp-guide-cycle-rel__tag:hover { background: var(--gt-color-primary); color: #fff; }

/* 完整底稿清单区块 */
.gt-wp-guide-cycle-wplist { }
.gt-wp-guide-cycle-wplist__title {
  font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 8px;
}

/* 右侧空态引导面板 */
.gt-wp-empty-guide {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; padding: 32px;
}
.gt-wp-empty-guide__header {
  display: flex; flex-direction: column; align-items: center; margin-bottom: 32px;
}
.gt-wp-empty-guide__title {
  font-size: 16px; font-weight: 600; color: var(--gt-color-text-primary); margin-top: 12px; margin-bottom: 4px;
}
.gt-wp-empty-guide__desc {
  font-size: 13px; color: var(--gt-color-text-tertiary);
}
.gt-wp-empty-guide__body {
  display: flex; flex-direction: column; align-items: center; gap: 24px; width: 100%; max-width: 360px;
}
.gt-wp-empty-guide__stats {
  display: flex; align-items: center; gap: 0; width: 100%;
  padding: 20px 16px; background: var(--gt-color-bg, #fafafa);
  border-radius: 12px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-wp-empty-guide__stat-item {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;
}
.gt-wp-empty-guide__stat-divider {
  width: 1px; height: 36px; background: var(--gt-color-border-light, #e8e8e8);
}
.gt-wp-empty-guide__stat-num {
  font-size: 26px; font-weight: 700; color: var(--gt-color-primary); line-height: 1;
}
.gt-wp-empty-guide__stat-label {
  font-size: 12px; color: var(--gt-color-text-tertiary);
}
.gt-wp-empty-guide__tips {
  display: flex; flex-direction: column; gap: 8px; width: 100%;
}
.gt-wp-empty-guide__tip {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--gt-color-text-secondary);
  padding: 10px 14px; background: var(--gt-color-bg-white, #fff);
  border-radius: 8px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
  transition: background 0.15s;
}
.gt-wp-empty-guide__tip:hover {
  background: var(--gt-color-primary-bg, #f8f5ff);
}
.gt-wp-empty-guide__tip-icon {
  flex-shrink: 0; font-size: 14px;
}

/* 树面板增强：分组节点样式 */
:deep(.el-tree-node__content) {
  height: 36px;
  border-radius: 6px;
  transition: background 0.15s;
}
:deep(.el-tree-node__content:hover) {
  background: var(--gt-color-primary-bg, #f8f5ff);
}
:deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: var(--gt-color-primary-bg, #f0ebff);
  border-left: 3px solid var(--gt-color-primary);
}
/* 一级分组节点（循环标题）加粗 + 上间距 */
:deep(.el-tree > .el-tree-node > .el-tree-node__content) {
  font-weight: 600;
  margin-top: 8px;
  height: 40px;
  background: var(--gt-color-bg, #fafafa);
  border-radius: 8px;
}
:deep(.el-tree > .el-tree-node:first-child > .el-tree-node__content) {
  margin-top: 0;
}
</style>
