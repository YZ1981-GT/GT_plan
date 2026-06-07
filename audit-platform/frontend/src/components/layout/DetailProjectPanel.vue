<template>
  <div class="gt-detail-panel">
    <template v-if="project">
      <!-- Tab 页签 -->
      <el-tabs v-model="activeTab" class="gt-detail-tabs">
        <!-- 项目概览 -->
        <el-tab-pane label="概览" name="overview">
          <div class="gt-detail-section">
            <div class="gt-title-row">
              <h3 class="gt-detail-title">{{ project.name }}</h3>
              <el-button size="small" type="primary" @click="editProject">
                <el-icon><Edit /></el-icon> 编辑
              </el-button>
            </div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="客户名称">{{ project.client_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="项目类型">
                <el-tag size="small">{{ typeLabel(project.project_type) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="当前状态">
                <el-tooltip :content="statusTooltip" placement="bottom" :show-after="200">
                  <span style="cursor: help">
                    <GtStatusTag dict-key="project_status" :value="project.status" />
                  </span>
                </el-tooltip>
                <span v-if="project.status === 'planning'" class="gt-status-hint">
                  — 请先导入账套数据，完成后状态将自动推进
                </span>
                <span v-else-if="project.status === 'created'" class="gt-status-hint">
                  — 新建项目，请开始配置
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="报表准则">
                <el-tag :type="project.template_type === 'soe' ? 'warning' : 'primary'" size="small">
                  {{ project.template_type === 'soe' ? '国企版' : project.template_type === 'listed' ? '上市版' : '未设置' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="企业代码">{{ project.company_code || project.client_code || '-' }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatDate(project.created_at) }}</el-descriptions-item>
              <!-- 双向导航 4.1：单体项目所属集团链接 → 跳合并项目 -->
              <el-descriptions-item v-if="project.parent_project_id" label="所属集团">
                <el-link type="primary" @click="goToParentConsol">
                  {{ project.parent_project_name || '查看合并项目' }}
                </el-link>
              </el-descriptions-item>
            </el-descriptions>

            <!-- 配置缺失提示 -->
            <el-alert
              v-if="!project.template_type"
              type="warning"
              show-icon
              :closable="false"
              style="margin-top: 10px"
            >
              <template #title>请设置报表模板类型</template>
              <div style="font-size: var(--gt-font-size-xs); line-height: 1.6">
                当前项目未设置模板类型（国企版/上市版），报表和附注生成将使用默认配置。
                <el-button type="primary" text size="small" @click="editProject">前往设置 →</el-button>
              </div>
            </el-alert>
          </div>

          <!-- 快捷入口 -->
          <div class="gt-detail-section">
            <div class="gt-workflow-hint">
              <span class="gt-workflow-hint-label">建议流程：</span>
              <span class="gt-workflow-step">① 导入</span>
              <span class="gt-workflow-arrow">→</span>
              <span class="gt-workflow-step">② 映射</span>
              <span class="gt-workflow-arrow">→</span>
              <span class="gt-workflow-step">③ 底稿</span>
              <span class="gt-workflow-arrow">→</span>
              <span class="gt-workflow-step">④ 报表</span>
              <span class="gt-workflow-arrow">→</span>
              <span class="gt-workflow-step">⑤ 附注</span>
            </div>
            <div class="gt-quick-tip">
              💡 提示：首次使用请按建议流程操作。先导入账套数据，完成科目映射后系统自动生成试算表，再依次编制底稿、生成报表和附注。
            </div>
            <div class="gt-quick-grid">
              <!-- 第一行：核心流程（按建议流程顺序） -->
              <el-tooltip content="上传企业导出的科目余额表、序时账等文件" placement="top">
                <div class="gt-quick-btn" @click="goToLedgerImport()">
                  <el-icon :size="20" color="var(--gt-color-primary-dark)"><Upload /></el-icon>
                  <span>账套导入</span>
                </div>
              </el-tooltip>
              <el-tooltip content="查看试算表（需先导入数据+科目映射）" placement="top">
                <div class="gt-quick-btn" @click="goTo('trial-balance')">
                  <el-icon :size="20" color="var(--gt-color-primary)"><DataLine /></el-icon>
                  <span>试算表</span>
                </div>
              </el-tooltip>
              <el-tooltip content="录入审计调整分录（AJE）和重分类调整（RJE）" placement="top">
                <div class="gt-quick-btn" @click="goTo('adjustments')">
                  <el-icon :size="20" color="var(--gt-color-teal)"><Edit /></el-icon>
                  <span>调整分录</span>
                </div>
              </el-tooltip>
              <el-tooltip content="查看和编辑审计底稿（需先生成底稿）" placement="top">
                <div class="gt-quick-btn" @click="goTo('workpapers')">
                  <el-icon :size="20" color="var(--gt-color-primary-light)"><Document /></el-icon>
                  <span>底稿</span>
                </div>
              </el-tooltip>
              <el-tooltip content="查看财务报表（需先导入数据并生成报表）" placement="top">
                <div class="gt-quick-btn" @click="goTo('reports')">
                  <el-icon :size="20" color="var(--gt-color-success)"><TrendCharts /></el-icon>
                  <span>报表</span>
                </div>
              </el-tooltip>
              <el-tooltip content="编辑附注章节（需先选择模板并生成附注）" placement="top">
                <div class="gt-quick-btn" @click="goTo('disclosure-notes')">
                  <el-icon :size="20" color="var(--gt-color-wheat)"><Notebook /></el-icon>
                  <span>附注</span>
                </div>
              </el-tooltip>
              <!-- 第二行：辅助功能 -->
              <el-tooltip content="设置整体重要性水平、实际执行重要性和明显微小错报" placement="top">
                <div class="gt-quick-btn" @click="goTo('materiality')">
                  <el-icon :size="20" color="var(--gt-color-coral)"><Aim /></el-icon>
                  <span>重要性</span>
                </div>
              </el-tooltip>
              <el-tooltip content="执行审计检查清单" placement="top">
                <div class="gt-quick-btn" @click="goTo('audit-checks')">
                  <el-icon :size="20" color="var(--gt-color-success)"><CircleCheck /></el-icon>
                  <span>审计检查</span>
                </div>
              </el-tooltip>
              <el-tooltip content="查询科目余额、序时账、辅助余额等四表数据" placement="top">
                <div class="gt-quick-btn" @click="goTo('ledger')">
                  <el-icon :size="20" color="var(--gt-color-primary-dark)"><Search /></el-icon>
                  <span>查账</span>
                </div>
              </el-tooltip>
              <el-tooltip content="清除卡住的导入任务，释放导入锁" placement="top">
                <div class="gt-quick-btn gt-quick-btn--danger" @click="handleResetImport">
                  <el-icon :size="20" color="#f56c6c"><RefreshRight /></el-icon>
                  <span>重置</span>
                </div>
              </el-tooltip>
              <el-tooltip content="一键创建当年项目（继承上年配置）" placement="top">
                <div class="gt-quick-btn" @click="onCreateNextYear">
                  <el-icon :size="20" color="var(--gt-color-success)"><CopyDocument /></el-icon>
                  <span>创建下年</span>
                </div>
              </el-tooltip>
              <el-tooltip content="为项目分配团队成员" placement="top">
                <div class="gt-quick-btn" @click="showTeamAssign = true">
                  <el-icon :size="20" color="var(--gt-color-primary)"><User /></el-icon>
                  <span>人员委派</span>
                </div>
              </el-tooltip>
              <el-tooltip content="交付件管理中心：导出、版本、预览、审批、归档" placement="top">
                <div class="gt-quick-btn" @click="goTo('deliverable-center')">
                  <el-icon :size="20" color="var(--gt-color-primary-dark)"><Finished /></el-icon>
                  <span>交付物</span>
                </div>
              </el-tooltip>
              <div
                v-if="project.report_scope === 'consolidated'"
                class="gt-quick-btn"
                @click="goTo('workpaper-summary')"
              >
                <el-icon :size="20" color="var(--gt-color-teal)"><Grid /></el-icon>
                <span>底稿汇总</span>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 项目看板（指标 + 团队 + 底稿分配） -->
        <el-tab-pane label="指标" name="metrics" lazy>
          <div v-if="metricsLoading" class="gt-board-loading">
            <el-skeleton :rows="6" animated />
          </div>
          <template v-else>
            <!-- 顶部指标卡片 3×2 -->
            <div class="gt-board-cards">
              <div class="gt-board-card" @dblclick="goTo('workpapers')">
                <div class="gt-board-card__icon" style="background: var(--gt-color-primary-bg)">📋</div>
                <div class="gt-board-card__body">
                  <span class="gt-board-card__value">{{ metrics.wpRate !== null ? metrics.wpRate + '%' : '-' }}</span>
                  <span class="gt-board-card__label">底稿完成率</span>
                </div>
                <el-progress v-if="metrics.wpRate !== null" :percentage="metrics.wpRate" :stroke-width="3" :show-text="false" color="var(--gt-color-primary)" class="gt-board-card__bar" />
              </div>
              <div class="gt-board-card" @dblclick="goTo('workpapers')">
                <div class="gt-board-card__icon" style="background: #e8f8f5">✅</div>
                <div class="gt-board-card__body">
                  <span class="gt-board-card__value">{{ metrics.reviewRate !== null ? metrics.reviewRate + '%' : '-' }}</span>
                  <span class="gt-board-card__label">复核完成率</span>
                </div>
                <el-progress v-if="metrics.reviewRate !== null" :percentage="metrics.reviewRate" :stroke-width="3" :show-text="false" color="var(--gt-color-teal)" class="gt-board-card__bar" />
              </div>
              <div class="gt-board-card" @dblclick="goTo('adjustments')">
                <div class="gt-board-card__icon" style="background: #fff3e0">📝</div>
                <div class="gt-board-card__body">
                  <span class="gt-board-card__value" style="color: var(--gt-color-teal)">{{ metrics.ajeCount ?? '-' }}</span>
                  <span class="gt-board-card__label">审计调整</span>
                </div>
              </div>
              <div class="gt-board-card" @dblclick="goTo('adjustments')">
                <div class="gt-board-card__icon" style="background: #fef3e2">🔄</div>
                <div class="gt-board-card__body">
                  <span class="gt-board-card__value" style="color: var(--gt-color-wheat)">{{ metrics.rjeCount ?? '-' }}</span>
                  <span class="gt-board-card__label">重分类调整</span>
                </div>
              </div>
              <div class="gt-board-card" @dblclick="goTo('audit-checks')">
                <div class="gt-board-card__icon" style="background: #fde8e8">⚠️</div>
                <div class="gt-board-card__body">
                  <span class="gt-board-card__value" :style="{ color: (metrics.openIssues ?? 0) > 0 ? 'var(--gt-color-coral)' : '' }">{{ metrics.openIssues ?? '-' }}</span>
                  <span class="gt-board-card__label">未决问题</span>
                </div>
              </div>
              <div class="gt-board-card" @dblclick="goTo('workpapers')">
                <div class="gt-board-card__icon" style="background: #fde8e8">🕐</div>
                <div class="gt-board-card__body">
                  <span class="gt-board-card__value" :style="{ color: (metrics.staleCount ?? 0) > 0 ? 'var(--gt-color-coral)' : '' }">{{ metrics.staleCount ?? '-' }}</span>
                  <span class="gt-board-card__label">数据过期</span>
                </div>
              </div>
            </div>

            <!-- 财务数据概览 -->
            <div class="gt-board-section">
              <h4 class="gt-board-section__title">💰 财务分析指标</h4>
              <div class="gt-fa">
                <div v-for="(cat, ci) in finCategories" :key="cat.key" class="gt-fa__card" :style="{ animationDelay: ci * 0.08 + 's' }">
                  <div class="gt-fa__header" :class="`gt-fa__header--${cat.key}`">
                    <span class="gt-fa__header-icon">{{ cat.icon }}</span>
                    <span>{{ cat.label }}</span>
                  </div>
                  <div class="gt-fa__body">
                    <el-tooltip
                      v-for="item in cat.items"
                      :key="item.label"
                      :content="`${item.label} = ${item.formula}`"
                      placement="top"
                      :show-after="300"
                    >
                      <div class="gt-fa__row" @dblclick="item.link && goTo(item.link)">
                        <span class="gt-fa__label">{{ item.label }}</span>
                        <span class="gt-fa__value" :class="{ 'gt-fa__value--negative': item.negative, 'gt-fa__value--link': item.link }">
                          {{ item.display }}
                        </span>
                      </div>
                    </el-tooltip>
                  </div>
                </div>
              </div>
            </div>

            <!-- 团队成员 & 工时 -->
            <div class="gt-board-section">
              <h4 class="gt-board-section__title">👥 项目团队与工时</h4>
              <el-table v-if="teamMembers.length" :data="teamMembers" size="small" stripe :max-height="200">
                <el-table-column prop="staff_name" label="姓名" width="90" />
                <el-table-column prop="role_label" label="角色" width="80">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.role === 'preparer' ? undefined : row.role === 'reviewer' ? 'success' : 'info'">
                      {{ row.role_label }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="工时(h)" width="70" align="right">
                  <template #default="{ row }">{{ row.total_hours ?? '-' }}</template>
                </el-table-column>
                <el-table-column label="分配底稿" width="80" align="right">
                  <template #default="{ row }">{{ row.assigned_wp ?? '-' }}</template>
                </el-table-column>
                <el-table-column label="已完成" width="70" align="right">
                  <template #default="{ row }">{{ row.completed_wp ?? '-' }}</template>
                </el-table-column>
                <el-table-column label="完成率" min-width="100">
                  <template #default="{ row }">
                    <el-progress
                      v-if="row.assigned_wp"
                      :percentage="row.assigned_wp ? Math.round((row.completed_wp || 0) / row.assigned_wp * 100) : 0"
                      :stroke-width="8"
                      color="var(--gt-color-primary)"
                    />
                    <span v-else style="color: var(--gt-color-text-placeholder)">-</span>
                  </template>
                </el-table-column>
              </el-table>
              <div v-else class="gt-board-empty-hint">暂无团队成员，请先进行人员委派</div>
            </div>

            <!-- 空态 -->
            <div v-if="!metrics.wpRate && !metrics.ajeCount && !metrics.rjeCount && !teamMembers.length" class="gt-board-empty">
              <el-empty :image-size="60" description="暂无数据，导入账套并分配人员后将自动显示" />
            </div>
          </template>
        </el-tab-pane>

        <!-- 底稿索引 + 分配详情 -->
        <el-tab-pane label="底稿" name="workpapers" lazy>
          <!-- 循环完成度进度条 -->
          <div class="gt-board-section">
            <h4 class="gt-board-section__title">📊 审计流程底稿完成度</h4>
            <!-- 流程步骤条 -->
            <div class="gt-flow">
              <div
                v-for="(stage, si) in cycleStages"
                :key="stage.label"
                class="gt-flow__step"
              >
                <div class="gt-flow__node" :class="`gt-flow__node--s${si}`">
                  <span class="gt-flow__step-num">{{ si + 1 }}</span>
                  <span class="gt-flow__step-label">{{ stage.label }}</span>
                  <span class="gt-flow__step-pct">{{ stage.pct }}%</span>
                </div>
                <div v-if="si < cycleStages.length - 1" class="gt-flow__connector">
                  <span class="gt-flow__arrow">→</span>
                </div>
              </div>
            </div>
            <!-- 各阶段展开明细 -->
            <div class="gt-flow-detail">
              <div
                v-for="(stage, si) in cycleStages"
                :key="stage.label"
                class="gt-flow-detail__group"
                :class="{ 'gt-flow-detail__group--wide': stage.items.length > 3 }"
              >
                <div class="gt-flow-detail__header" :class="`gt-flow-detail__header--s${si}`">
                  {{ stage.label }}
                  <span class="gt-flow-detail__summary">{{ stage.done }}/{{ stage.total }}</span>
                </div>
                <div class="gt-flow-detail__items" :class="{ 'gt-flow-detail__items--grid': stage.items.length > 3 }">
                  <el-tooltip
                    v-for="item in stage.items"
                    :key="item.code"
                    :content="`${item.code} ${item.name}：已完成 ${item.done}/${item.total}，双击查看底稿`"
                    placement="top"
                    :show-after="200"
                  >
                    <div class="gt-flow-detail__row" @dblclick="goTo(`workpapers?cycle=${item.code}`)">
                      <span class="gt-flow-detail__code">{{ item.code }}</span>
                      <span class="gt-flow-detail__name">{{ item.name }}</span>
                      <el-progress
                        :percentage="item.pct"
                        :stroke-width="8"
                        :show-text="false"
                        color="var(--gt-color-primary)"
                        class="gt-flow-detail__bar"
                      />
                      <span class="gt-flow-detail__stat">{{ item.done }}/{{ item.total }}</span>
                    </div>
                  </el-tooltip>
                  <div v-if="!stage.items.length" class="gt-flow-detail__empty">暂无底稿</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 底稿明细表（编制人/复核人/状态） -->
          <div class="gt-board-section">
            <h4 class="gt-board-section__title">📋 底稿分配明细</h4>
            <div v-if="wpDetailLoading" style="padding: 12px 0"><el-skeleton :rows="4" animated /></div>
            <el-table v-else-if="wpDetailList.length" :data="wpDetailList" size="small" stripe :max-height="360" style="width: 100%">
              <el-table-column prop="wp_code" label="编号" width="70" sortable />
              <el-table-column prop="wp_name" label="底稿名称" min-width="140" show-overflow-tooltip />
              <el-table-column prop="cycle" label="循环" width="50" align="center" />
              <el-table-column prop="preparer_name" label="编制人" width="80">
                <template #default="{ row }">{{ row.preparer_name || '-' }}</template>
              </el-table-column>
              <el-table-column prop="reviewer_name" label="复核人" width="80">
                <template #default="{ row }">{{ row.reviewer_name || '-' }}</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="wpStatusType(row.status)">{{ wpStatusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无底稿数据" :image-size="50">
              <el-button size="small" type="primary" @click="goTo('workpapers')">查看底稿</el-button>
            </el-empty>
          </div>

          <!-- 人员汇总统计 -->
          <div v-if="wpStaffSummary.length" class="gt-board-section">
            <h4 class="gt-board-section__title">👤 人员负责汇总</h4>
            <el-table :data="wpStaffSummary" size="small" :max-height="200">
              <el-table-column prop="name" label="姓名" width="90" />
              <el-table-column prop="as_preparer" label="编制(负责)" width="90" align="center" />
              <el-table-column prop="prepared_done" label="编制(完成)" width="90" align="center" />
              <el-table-column prop="as_reviewer" label="复核(负责)" width="90" align="center" />
              <el-table-column prop="reviewed_done" label="复核(完成)" width="90" align="center" />
              <el-table-column label="编制完成率" min-width="100">
                <template #default="{ row }">
                  <el-progress
                    v-if="row.as_preparer"
                    :percentage="Math.round((row.prepared_done / row.as_preparer) * 100)"
                    :stroke-width="8"
                    color="var(--gt-color-primary)"
                  />
                  <span v-else>-</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

        </el-tab-pane>

        <!-- 报表预览 -->
        <el-tab-pane label="报表" name="reports" lazy>
          <div class="gt-report-links">
            <div
              v-for="(rpt, ri) in reportList"
              :key="rpt.type"
              class="gt-report-card"
              :style="{ animationDelay: ri * 0.06 + 's' }"
              @dblclick="goTo(`reports?type=${rpt.type}`)"
            >
              <span class="gt-report-card__icon">{{ rpt.icon }}</span>
              <span class="gt-report-card__name">{{ rpt.label }}</span>
            </div>
          </div>
          <div class="gt-report-hint">双击报表卡片跳转查看</div>
        </el-tab-pane>

        <!-- 附件管理 -->
        <el-tab-pane label="附件" name="attachments" lazy>
          <div class="gt-att">
            <!-- 已上传附件按循环分组卡片 -->
            <div class="gt-att__header">
              <h4 class="gt-att__title">📎 项目附件</h4>
              <el-button type="primary" size="small" @click="showAttUpload = true">
                + 新增附件
              </el-button>
            </div>

            <!-- 附件卡片网格 -->
            <div v-if="attachmentList.length" class="gt-att__grid">
              <div
                v-for="(att, ai) in attachmentList"
                :key="att.id || ai"
                class="gt-att__card"
                :style="{ animationDelay: ai * 0.05 + 's' }"
                @dblclick="goTo('attachments')"
              >
                <span class="gt-att__card-icon">{{ attFileIcon(att.file_type) }}</span>
                <div class="gt-att__card-body">
                  <span class="gt-att__card-name">{{ att.file_name }}</span>
                  <span class="gt-att__card-meta">
                    <el-tag size="small" type="info">{{ attachTypeLabel(att.attachment_type) }}</el-tag>
                    <span>{{ formatSize(att.file_size) }}</span>
                  </span>
                </div>
                <span v-if="att.wp_code" class="gt-att__card-wp">{{ att.wp_code }}</span>
              </div>
            </div>
            <el-empty v-else :image-size="80" description="">
              <template #description>
                <div style="text-align: center; line-height: 1.8">
                  <p style="font-size: 14px; color: var(--gt-color-text-secondary); margin: 0">暂无附件</p>
                  <p style="font-size: 12px; color: var(--gt-color-text-placeholder); margin: 4px 0 0">
                    上传后将按循环和科目分组展示，支持关联底稿快速查阅
                  </p>
                </div>
              </template>
              <el-button type="primary" size="small" @click="showAttUpload = true">+ 上传第一个附件</el-button>
            </el-empty>
          </div>

          <!-- 新增附件弹窗 -->
          <el-dialog v-model="showAttUpload" title="新增附件" width="600px" append-to-body destroy-on-close>
            <el-form label-width="80px" size="default">
              <el-form-item label="关联底稿">
                <el-select v-model="attForm.wpCode" filterable clearable placeholder="选择关联底稿（可选）" style="width: 100%">
                  <el-option
                    v-for="wp in attWpOptions"
                    :key="wp.value"
                    :label="wp.label"
                    :value="wp.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="附件分类">
                <el-select v-model="attForm.type" placeholder="选择分类" style="width: 100%">
                  <el-option label="通用" value="general" />
                  <el-option label="底稿" value="workpaper" />
                  <el-option label="函证" value="confirmation" />
                  <el-option label="合同" value="contract" />
                  <el-option label="证据" value="evidence" />
                  <el-option label="报告" value="report" />
                </el-select>
              </el-form-item>
              <el-form-item label="上传文件">
                <el-upload
                  action=""
                  :auto-upload="false"
                  :limit="5"
                  :on-change="onAttFileChange"
                  multiple
                  drag
                >
                  <div style="padding: 20px 0; color: var(--gt-color-text-secondary); font-size: 13px">
                    拖拽文件到此处或点击选择
                  </div>
                </el-upload>
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="showAttUpload = false">取消</el-button>
              <el-button type="primary" @click="submitAttachment">确认上传</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 未选择项目 -->
    <div v-else class="gt-empty-state">
      <el-empty description="请从左侧选择一个项目" :image-size="100" />
    </div>

    <!-- 人员委派弹窗 -->
    <el-dialog v-model="showTeamAssign" title="人员委派" width="900px" append-to-body destroy-on-close>
      <div style="min-height: 500px;">
        <TeamAssignmentStep v-if="showTeamAssign" :project-id="project.id" />
      </div>
      <template #footer>
        <el-button @click="showTeamAssign = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  DataLine, Edit, Document, TrendCharts, Notebook, Aim, Search, Grid, Paperclip, CopyDocument, Upload, RefreshRight, User, CircleCheck, Finished,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { confirmForceReset, confirmDangerous } from '@/utils/confirm'
import { api } from '@/services/apiProxy'
import { projects as P_proj, attachments as P_att, accountChart as P_ac, adjustments as P_adj } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import TeamAssignmentStep from '@/components/wizard/TeamAssignmentStep.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import { useNavigationStack } from '@/composables/useNavigationStack'

const props = defineProps<{ project: any | null }>()
const router = useRouter()
const { push: navPush } = useNavigationStack()
const activeTab = ref('overview')
const showTeamAssign = ref(false)
const showAttUpload = ref(false)
const attForm = ref({ wpCode: '', type: 'general' })
const attFiles = ref<any[]>([])
const attWpOptions = ref<{ label: string; value: string }[]>([])
const projectYear = computed(() => Number(props.project?.audit_year) || new Date().getFullYear())

// 项目状态悬停提示（当前阶段 + 后续步骤）
const statusTooltip = computed(() => {
  const s = props.project?.status || 'created'
  const tips: Record<string, string> = {
    created: '【新建】项目刚创建，下一步：导入账套数据（科目余额表+序时账）',
    planning: '【计划中】已建项，下一步：①导入账套 ②完成科目映射 → 系统自动生成试算表并推进到执行阶段',
    execution: '【执行中】账套已导入，当前：①编制审计底稿 ②录入调整分录 ③执行审计程序',
    completion: '【完成阶段】底稿基本完成，当前：①生成财务报表 ②复核底稿 ③处理未决问题',
    reporting: '【报告阶段】报表已生成，当前：①编辑附注 ②出具审计报告 ③合伙人签发',
    archived: '【已归档】项目已完成并归档，所有底稿和报告已锁定',
  }
  return tips[s] || s
})

// 附件列表
const attachmentList = ref<any[]>([])

// 指标数据
const metricsLoading = ref(false)
const metrics = ref<{
  wpRate: number | null
  reviewRate: number | null
  ajeCount: number | null
  rjeCount: number | null
  openIssues: number | null
  staleCount: number | null
  byCycle: Record<string, any> | null
}>({
  wpRate: null, reviewRate: null, ajeCount: null, rjeCount: null,
  openIssues: null, staleCount: null, byCycle: null,
})

// 团队成员（带工时和底稿分配）
const teamMembers = ref<any[]>([])

// 底稿明细
const wpDetailLoading = ref(false)
const wpDetailList = ref<any[]>([])
const wpStaffSummary = ref<any[]>([])

// 财务数据
const financialData = ref<{
  loaded: boolean
  totalAssets: number | null
  totalLiabilities: number | null
  totalEquity: number | null
  revenue: number | null
  netProfit: number | null
  debtRatio: number | null
  grossMargin: number | null
  netMargin: number | null
  roe: number | null
  assetTurnover: number | null
  receivableTurnover: number | null
  inventoryTurnover: number | null
  currentRatio: number | null
  quickRatio: number | null
  revenueGrowth: number | null
  profitGrowth: number | null
  assetGrowth: number | null
}>({
  loaded: false, totalAssets: null, totalLiabilities: null, totalEquity: null,
  revenue: null, netProfit: null, debtRatio: null,
  grossMargin: null, netMargin: null, roe: null,
  assetTurnover: null, receivableTurnover: null, inventoryTurnover: null,
  currentRatio: null, quickRatio: null,
  revenueGrowth: null, profitGrowth: null, assetGrowth: null,
})
// 选中项目变化时加载数据
watch(() => props.project?.id, async (newId) => {
  if (!newId) { return }
  // 加载附件列表（前10条，静默失败）
  try {
    const raw = await api.get(P_att.list(newId), {
      params: { page_size: 10 },
      validateStatus: (s: number) => s < 600,
    })
    const data = raw?.data ?? raw
    if (data) {
      attachmentList.value = Array.isArray(data) ? data.slice(0, 10) : (data?.items ?? []).slice(0, 10)
    } else {
      attachmentList.value = []
    }
  } catch { attachmentList.value = [] }
  // 加载指标数据（多源并发，各自降级）
  metricsLoading.value = true
  try {
    const [wpRes, adjRes, dashRes, staleRes, teamRes, hoursRes] = await Promise.allSettled([
      api.get(`/api/projects/${newId}/workpapers/progress`, { validateStatus: (s: number) => s < 600 }),
      api.get(P_adj.summary(newId), { params: { year: projectYear.value }, validateStatus: (s: number) => s < 600 }),
      api.get(`/api/projects/${newId}/dashboard/summary`, { validateStatus: (s: number) => s < 600 }),
      api.get(`/api/projects/${newId}/stale-summary`, { validateStatus: (s: number) => s < 600 }),
      api.get(`/api/projects/${newId}/assignments`, { validateStatus: (s: number) => s < 600 }),
      api.get(`/api/projects/${newId}/work-hours`, { validateStatus: (s: number) => s < 600 }),
    ])
    const wp = wpRes.status === 'fulfilled' ? wpRes.value : null
    const adj = adjRes.status === 'fulfilled' ? adjRes.value : null
    const dash = dashRes.status === 'fulfilled' ? dashRes.value : null
    const stale = staleRes.status === 'fulfilled' ? staleRes.value : null
    const team = teamRes.status === 'fulfilled' ? teamRes.value : null
    const hours = hoursRes.status === 'fulfilled' ? hoursRes.value : null
    metrics.value = {
      wpRate: wp?.rate ?? null,
      reviewRate: dash?.review_completion_rate ?? null,
      ajeCount: adj?.aje_count ?? null,
      rjeCount: adj?.rje_count ?? null,
      openIssues: dash?.open_reviews?.total ?? null,
      staleCount: stale?.stale_count ?? null,
      byCycle: wp?.by_cycle ?? null,
    }
    // 合并团队成员 + 工时
    const roleMap: Record<string, string> = { preparer: '编制', reviewer: '复核', partner: '合伙人', manager: '经理', assistant: '助理' }
    const rawTeam = Array.isArray(team) ? team : (team?.items ?? team?.data ?? [])
    const rawHours = Array.isArray(hours) ? hours : (hours?.items ?? hours?.data ?? [])
    // 构建工时映射 (staff_id -> total_hours)
    const hoursMap = new Map<string, number>()
    for (const h of rawHours) {
      const key = h.staff_id || h.user_id
      if (key) hoursMap.set(key, (hoursMap.get(key) || 0) + (h.total_hours || h.hours || 0))
    }
    // 从 wp progress 的 by_staff 提取底稿分配（如果有的话）
    const wpByStaff = wp?.by_staff || {}
    teamMembers.value = rawTeam.map((m: any) => {
      const staffId = m.staff_id || m.user_id || m.id
      const staffWp = wpByStaff[staffId]
      return {
        staff_name: m.staff_name || m.name || m.display_name || '-',
        role: m.role || m.assignment_role || 'assistant',
        role_label: roleMap[m.role || m.assignment_role || ''] || m.role || '成员',
        total_hours: hoursMap.get(staffId) ?? (m.total_hours || null),
        assigned_wp: staffWp?.total ?? m.assigned_count ?? null,
        completed_wp: staffWp?.completed ?? m.completed_count ?? null,
      }
    })
  } catch {
    metrics.value = { wpRate: null, reviewRate: null, ajeCount: null, rjeCount: null, openIssues: null, staleCount: null, byCycle: null }
    teamMembers.value = []
  } finally {
    metricsLoading.value = false
  }
  // 加载财务数据（从报表端点获取资产负债表+利润表关键指标，计算四大类比率）
  try {
    const year = projectYear.value
    const [bsRes, isRes] = await Promise.allSettled([
      api.get(`/api/reports/${newId}/${year}/balance_sheet`, { validateStatus: (s: number) => s < 600 }),
      api.get(`/api/reports/${newId}/${year}/income_statement`, { validateStatus: (s: number) => s < 600 }),
    ])
    const bs = bsRes.status === 'fulfilled' ? bsRes.value : null
    const is_ = isRes.status === 'fulfilled' ? isRes.value : null
    const bsRows = Array.isArray(bs) ? bs : (bs?.rows ?? bs?.data ?? [])
    const isRows = Array.isArray(is_) ? is_ : (is_?.rows ?? is_?.data ?? [])
    const findRow = (rows: any[], codes: string[]) => {
      for (const code of codes) {
        const row = rows.find((r: any) => r.row_code === code || r.line_code === code || r.code === code)
        if (row) return row.current_period_amount ?? row.audited_amount ?? row.amount ?? null
      }
      return null
    }
    // 基础数据
    const totalAssets = findRow(bsRows, ['assets_total', 'ASSETS_TOTAL', '资产合计', 'total_assets'])
    const totalLiabilities = findRow(bsRows, ['liabilities_total', 'LIABILITIES_TOTAL', '负债合计', 'total_liabilities'])
    const totalEquity = findRow(bsRows, ['equity_total', 'EQUITY_TOTAL', '所有者权益合计', 'total_equity', 'owners_equity_total'])
    const currentAssets = findRow(bsRows, ['current_assets_total', 'CURRENT_ASSETS_TOTAL', '流动资产合计', 'total_current_assets'])
    const currentLiabilities = findRow(bsRows, ['current_liabilities_total', 'CURRENT_LIABILITIES_TOTAL', '流动负债合计', 'total_current_liabilities'])
    const inventory = findRow(bsRows, ['inventory', 'INVENTORY', '存货', 'inventories'])
    const receivables = findRow(bsRows, ['accounts_receivable', 'ACCOUNTS_RECEIVABLE', '应收账款', 'trade_receivables'])
    const revenue = findRow(isRows, ['revenue', 'REVENUE', '营业收入', 'operating_revenue', 'total_revenue'])
    const costOfSales = findRow(isRows, ['cost_of_sales', 'COST_OF_SALES', '营业成本', 'operating_cost', 'cost_of_revenue'])
    const netProfit = findRow(isRows, ['net_profit', 'NET_PROFIT', '净利润', 'net_income'])
    const hasData = totalAssets !== null || revenue !== null
    // 计算比率（安全除法）
    const safeDiv = (a: number | null, b: number | null) => (a !== null && b !== null && b !== 0) ? a / b : null
    const pct = (v: number | null) => v !== null ? Math.round(v * 10000) / 100 : null
    const grossProfit = (revenue !== null && costOfSales !== null) ? revenue - costOfSales : null
    financialData.value = {
      loaded: hasData,
      totalAssets,
      totalLiabilities,
      totalEquity,
      revenue,
      netProfit,
      // 盈利能力
      grossMargin: pct(safeDiv(grossProfit, revenue)),
      netMargin: pct(safeDiv(netProfit, revenue)),
      roe: pct(safeDiv(netProfit, totalEquity)),
      // 偿债能力
      debtRatio: pct(safeDiv(totalLiabilities, totalAssets)),
      currentRatio: safeDiv(currentAssets, currentLiabilities) !== null ? Math.round(safeDiv(currentAssets, currentLiabilities)! * 100) / 100 : null,
      quickRatio: (currentAssets !== null && inventory !== null && currentLiabilities !== null && currentLiabilities !== 0) ? Math.round((currentAssets - inventory) / currentLiabilities * 100) / 100 : null,
      // 运营能力
      assetTurnover: safeDiv(revenue, totalAssets) !== null ? Math.round(safeDiv(revenue, totalAssets)! * 100) / 100 : null,
      receivableTurnover: safeDiv(revenue, receivables) !== null ? Math.round(safeDiv(revenue, receivables)! * 100) / 100 : null,
      inventoryTurnover: safeDiv(costOfSales, inventory) !== null ? Math.round(safeDiv(costOfSales, inventory)! * 100) / 100 : null,
      // 成长能力（需要上期数据，当前暂不可用，标 null）
      revenueGrowth: null,
      profitGrowth: null,
      assetGrowth: null,
    }
  } catch {
    financialData.value = {
      loaded: false, totalAssets: null, totalLiabilities: null, totalEquity: null,
      revenue: null, netProfit: null, debtRatio: null,
      grossMargin: null, netMargin: null, roe: null,
      assetTurnover: null, receivableTurnover: null, inventoryTurnover: null,
      currentRatio: null, quickRatio: null,
      revenueGrowth: null, profitGrowth: null, assetGrowth: null,
    }
  }
  // 加载底稿明细（编制人/复核人/状态）
  wpDetailLoading.value = true
  try {
    const wpListRaw = await api.get(`/api/projects/${newId}/working-papers-kanban`, { validateStatus: (s: number) => s < 600 })
    const list = Array.isArray(wpListRaw) ? wpListRaw : (wpListRaw?.items ?? wpListRaw?.data ?? [])
    wpDetailList.value = list.map((item: any) => ({
      wp_code: item.wp_code || item.code || '-',
      wp_name: item.wp_name || item.name || '-',
      cycle: item.audit_cycle || item.cycle || (item.wp_code || '').charAt(0) || '-',
      preparer_name: item.preparer_name || item.assigned_to_name || '-',
      reviewer_name: item.reviewer_name || '-',
      status: item.status || item.wp_status || 'draft',
    }))
    // 汇总人员统计
    const staffMap = new Map<string, { name: string; as_preparer: number; prepared_done: number; as_reviewer: number; reviewed_done: number }>()
    const doneStatuses = new Set(['prepared', 'reviewed', 'archived', 'completed', 'signed_off'])
    for (const wp of wpDetailList.value) {
      if (wp.preparer_name && wp.preparer_name !== '-') {
        if (!staffMap.has(wp.preparer_name)) staffMap.set(wp.preparer_name, { name: wp.preparer_name, as_preparer: 0, prepared_done: 0, as_reviewer: 0, reviewed_done: 0 })
        const s = staffMap.get(wp.preparer_name)!
        s.as_preparer++
        if (doneStatuses.has(wp.status)) s.prepared_done++
      }
      if (wp.reviewer_name && wp.reviewer_name !== '-') {
        if (!staffMap.has(wp.reviewer_name)) staffMap.set(wp.reviewer_name, { name: wp.reviewer_name, as_preparer: 0, prepared_done: 0, as_reviewer: 0, reviewed_done: 0 })
        const s = staffMap.get(wp.reviewer_name)!
        s.as_reviewer++
        if (doneStatuses.has(wp.status)) s.reviewed_done++
      }
    }
    wpStaffSummary.value = [...staffMap.values()]
  } catch {
    wpDetailList.value = []
    wpStaffSummary.value = []
  } finally {
    wpDetailLoading.value = false
  }
}, { immediate: true })

function goTo(page: string) {
  if (!props.project) return
  router.push({
    path: `/projects/${props.project.id}/${page}`,
    query: { year: String(projectYear.value) },
  })
}

/**
 * 双向导航 4.1：跳转到所属集团（合并项目）。
 * 跳转前 push 当前路由到导航栈（direction:'up' 上钻），支持 Backspace 返回（T3）。
 */
function goToParentConsol() {
  if (!props.project?.parent_project_id) return
  const cur = router.currentRoute.value
  navPush({
    source_view: cur.path,
    label: props.project.name || '单体项目',
    direction: 'up',
    scroll_position: window.scrollY,
    query: cur.query as Record<string, string>,
  })
  router.push({ path: `/projects/${props.project.parent_project_id}/consolidation` })
}

async function goToLedgerImport() {
  if (!props.project) return
  // 检查是否已有账套数据：有数据跳查账页，无数据跳导入页
  try {
    const res: any = await api.get(
      `/api/projects/${props.project.id}/trial-balance/`,
      { params: { page: 1, page_size: 1 }, _silent: true } as any,
    )
    const rows = res?.items ?? res?.data ?? res
    if (Array.isArray(rows) && rows.length > 0) {
      // 已有数据：直接跳查账页面
      router.push({ path: `/projects/${props.project.id}/ledger` })
      return
    }
  } catch {
    // 查询失败（404/401/无数据）不阻塞，继续走导入流程
  }
  // 无数据或查询失败：直接跳导入页面（不再弹引导弹窗，减少点击）
  router.push({ path: `/projects/${props.project.id}/ledger-import` })
}

async function handleResetImport() {
  if (!props.project) return
  try {
    await confirmForceReset('将清除当前项目卡住的导入任务，释放导入锁，并刷新页面。\n已入库的数据不受影响。')
    await api.post(P_ac.importReset(props.project.id), null, {
      params: { force: true },
    })
    window.location.reload()
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') {
      const detail = e?.response?.data?.detail
      if (detail?.code === 'IMPORT_RESET_JOB_ID_REQUIRED') {
        ElMessage.warning('请在导入历史中选择具体作业后重置，或由管理员执行项目级强制重置。')
      } else {
        // 即使 API 失败也刷新，防止前端状态残留
        window.location.reload()
      }
    }
  }
}

function editProject() {
  if (!props.project) return
  router.push(`/projects/new?projectId=${props.project.id}`)
}

async function onCreateNextYear() {
  if (!props.project) return
  try {
    await confirmDangerous('确定要基于「' + props.project.name + '」创建下年项目吗？将继承科目映射、团队委派、试算表审定数等配置。', '创建下年项目')
    const data = await api.post(`${P_proj.detail(props.project.id)}/create-next-year`)
    const result = data
    ElMessage.success(`已创建下年项目，新项目ID: ${result.new_project_id?.slice(0, 8)}...`)
    router.push(`/projects/new?projectId=${result.new_project_id}`)
  } catch (err: any) {
    if (err !== 'cancel') {
      handleApiError(err, '创建')
    }
  }
}


function typeLabel(t: string) {
  const m: Record<string, string> = { annual: '年度审计', special: '专项审计', ipo: 'IPO审计', internal_control: '内控审计' }
  return m[t] || t || '-'
}
function formatDate(d: string) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('zh-CN')
}

function attachTypeLabel(t: string) {
  const m: Record<string, string> = {
    general: '通用', workpaper: '底稿', confirmation: '函证',
    contract: '合同', evidence: '证据', report: '报告',
  }
  return m[t] || t || '通用'
}

function wpStatusLabel(s: string) {
  const m: Record<string, string> = {
    draft: '草稿', in_progress: '进行中', prepared: '已编制',
    reviewed: '已复核', archived: '已归档', completed: '已完成',
    signed_off: '已签发',
  }
  return m[s] || s || '草稿'
}

function wpStatusType(s: string): 'success' | 'warning' | 'info' | 'danger' | undefined {
  if (s === 'reviewed' || s === 'archived' || s === 'completed' || s === 'signed_off') return 'success'
  if (s === 'prepared') return undefined
  if (s === 'in_progress') return 'warning'
  return 'info'
}

function fmtFinance(val: number | null): string {
  if (val === null || val === undefined) return '-'
  const abs = Math.abs(val)
  if (abs >= 1e8) return (val / 1e8).toFixed(2) + ' 亿'
  if (abs >= 1e4) return (val / 1e4).toFixed(2) + ' 万'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtPct(val: number | null): string {
  if (val === null || val === undefined) return '-'
  return val.toFixed(2) + '%'
}

function fmtTimes(val: number | null): string {
  if (val === null || val === undefined) return '-'
  return val.toFixed(2) + ' 次'
}

// 按循环标准顺序排列（A~N + S）+ 中文名称
const CYCLE_ORDER = 'Q B C D E F G H I J K L M N S A'.split(' ')
const CYCLE_NAMES: Record<string, string> = {
  Q: '业务约定与计划', A: '审计总结与报告', B: '承接/计划/了解', C: '控制测试', D: '销售与收入',
  E: '货币资金', F: '采购与存货', G: '投资', H: '固定资产',
  I: '无形资产', J: '职工薪酬', K: '管理费用', L: '筹资',
  M: '股东权益', N: '税费', S: '专项',
}
const sortedCycles = computed(() => {
  const raw = metrics.value.byCycle
  if (!raw) return []
  return CYCLE_ORDER
    .filter(code => raw[code])
    .map(code => {
      const v = raw[code]
      const done = (v.prepared || 0) + (v.reviewed || 0) + (v.archived || 0)
      return { code, name: CYCLE_NAMES[code] || code, done, total: v.total || 0, pct: v.total ? Math.round(done / v.total * 100) : 0 }
    })
})

// 按审计流程4阶段分组（致同体系：B=承接计划与了解, C=控制测试, D~S=实质性, A=完成）
// 注：B 循环同时包含立项承接（B1A/B1B/B2/B3）和计划了解（B10~B60）底稿，不可按字母级拆分
const cycleStages = computed(() => {
  const items = sortedCycles.value
  const stages = [
    { label: '承接与计划', codes: ['Q', 'B'] },
    { label: '控制测试', codes: ['C'] },
    { label: '实质性程序', codes: ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'S'] },
    { label: '完成与报告', codes: ['A'] },
  ]
  return stages.map(s => {
    const matched = items.filter(i => s.codes.includes(i.code))
    const done = matched.reduce((sum, i) => sum + i.done, 0)
    const total = matched.reduce((sum, i) => sum + i.total, 0)
    return { label: s.label, items: matched, done, total, pct: total ? Math.round(done / total * 100) : 0 }
  })
})

// 报表列表（基于 FinancialReportType 枚举，资产减值准备表仅国企版）
const reportList = computed(() => {
  const base = [
    { type: 'balance_sheet', label: '资产负债表', icon: '📊' },
    { type: 'income_statement', label: '利润表', icon: '📈' },
    { type: 'cash_flow_statement', label: '现金流量表', icon: '💰' },
    { type: 'equity_statement', label: '所有者权益变动表', icon: '📋' },
    { type: 'cash_flow_supplement', label: '现金流量表补充资料', icon: '📑' },
  ]
  if (props.project?.template_type === 'soe') {
    base.push({ type: 'impairment_provision', label: '资产减值准备表', icon: '🛡️' })
  }
  return base
})

// 四大类财务指标（每类 5 个，含 tooltip 公式和跳转链接）
const finCategories = computed(() => {
  const d = financialData.value
  return [
    {
      key: 'profit', label: '盈利能力', icon: '📈',
      items: [
        { label: '营业收入', display: fmtFinance(d.revenue), formula: '主营业务收入 + 其他业务收入', link: 'reports', negative: false },
        { label: '净利润', display: fmtFinance(d.netProfit), formula: '利润总额 − 所得税费用', link: 'reports', negative: (d.netProfit ?? 0) < 0 },
        { label: '毛利率', display: fmtPct(d.grossMargin), formula: '(营业收入 − 营业成本) ÷ 营业收入 × 100%', link: '', negative: false },
        { label: '净利率', display: fmtPct(d.netMargin), formula: '净利润 ÷ 营业收入 × 100%', link: '', negative: false },
        { label: '净资产收益率', display: fmtPct(d.roe), formula: '净利润 ÷ 所有者权益 × 100%（ROE）', link: '', negative: false },
      ],
    },
    {
      key: 'ops', label: '运营能力', icon: '⚙️',
      items: [
        { label: '总资产周转率', display: fmtTimes(d.assetTurnover), formula: '营业收入 ÷ 平均资产总额', link: '', negative: false },
        { label: '应收账款周转率', display: fmtTimes(d.receivableTurnover), formula: '营业收入 ÷ 平均应收账款余额', link: 'trial-balance', negative: false },
        { label: '存货周转率', display: fmtTimes(d.inventoryTurnover), formula: '营业成本 ÷ 平均存货余额', link: 'trial-balance', negative: false },
        { label: '应收账款周转天数', display: d.receivableTurnover ? (365 / d.receivableTurnover).toFixed(0) + ' 天' : '-', formula: '365 ÷ 应收账款周转率', link: '', negative: false },
        { label: '存货周转天数', display: d.inventoryTurnover ? (365 / d.inventoryTurnover).toFixed(0) + ' 天' : '-', formula: '365 ÷ 存货周转率', link: '', negative: false },
      ],
    },
    {
      key: 'debt', label: '偿债能力', icon: '🛡️',
      items: [
        { label: '资产总额', display: fmtFinance(d.totalAssets), formula: '流动资产 + 非流动资产', link: 'trial-balance', negative: false },
        { label: '负债总额', display: fmtFinance(d.totalLiabilities), formula: '流动负债 + 非流动负债', link: 'trial-balance', negative: false },
        { label: '资产负债率', display: fmtPct(d.debtRatio), formula: '负债总额 ÷ 资产总额 × 100%', link: '', negative: false },
        { label: '流动比率', display: d.currentRatio !== null ? d.currentRatio.toFixed(2) : '-', formula: '流动资产 ÷ 流动负债（≥2 为优）', link: '', negative: false },
        { label: '速动比率', display: d.quickRatio !== null ? d.quickRatio.toFixed(2) : '-', formula: '(流动资产 − 存货) ÷ 流动负债（≥1 为优）', link: '', negative: false },
      ],
    },
    {
      key: 'growth', label: '成长能力', icon: '🚀',
      items: [
        { label: '营收增长率', display: fmtPct(d.revenueGrowth), formula: '(本期营收 − 上期营收) ÷ 上期营收 × 100%', link: '', negative: false },
        { label: '净利润增长率', display: fmtPct(d.profitGrowth), formula: '(本期净利润 − 上期净利润) ÷ |上期净利润| × 100%', link: '', negative: false },
        { label: '总资产增长率', display: fmtPct(d.assetGrowth), formula: '(期末资产 − 期初资产) ÷ 期初资产 × 100%', link: '', negative: false },
        { label: '所有者权益', display: fmtFinance(d.totalEquity), formula: '资产总额 − 负债总额', link: 'trial-balance', negative: false },
        { label: '资本积累率', display: '-', formula: '(期末权益 − 期初权益) ÷ 期初权益 × 100%（需上期数据）', link: '', negative: false },
      ],
    },
  ]
})

function formatSize(bytes: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

function attFileIcon(type: string): string {
  if (!type) return '📄'
  const t = type.toLowerCase()
  if (t.includes('pdf')) return '📕'
  if (t.includes('xls') || t.includes('csv')) return '📗'
  if (t.includes('doc')) return '📘'
  if (t.includes('ppt')) return '📙'
  if (t.includes('img') || t.includes('jpg') || t.includes('png')) return '🖼️'
  return '📄'
}

function onAttFileChange(file: any) {
  attFiles.value.push(file)
}

async function submitAttachment() {
  if (!props.project?.id) return
  // TODO: 实际上传逻辑（POST /api/projects/{pid}/attachments）
  ElMessage.success('附件上传成功（功能开发中）')
  showAttUpload.value = false
  attForm.value = { wpCode: '', type: 'general' }
  attFiles.value = []
}

// 弹窗打开时加载底稿索引
watch(showAttUpload, async (open) => {
  if (!open || !props.project?.id) return
  if (attWpOptions.value.length) return // 已加载过
  try {
    const raw = await api.get(`/api/projects/${props.project.id}/wp-index`, { validateStatus: (s: number) => s < 600 })
    const list = Array.isArray(raw) ? raw : (raw?.items ?? raw?.data ?? [])
    attWpOptions.value = list.map((item: any) => ({
      label: `${item.wp_code || item.code || ''} ${item.wp_name || item.name || ''}`.trim(),
      value: item.wp_code || item.code || item.id || '',
    })).filter((o: any) => o.value)
  } catch {
    // 降级用 wpDetailList
    attWpOptions.value = wpDetailList.value.map(wp => ({
      label: `${wp.wp_code} ${wp.wp_name}`,
      value: wp.wp_code,
    }))
  }
})
</script>

<style scoped>
.gt-detail-panel { height: 100%; display: flex; flex-direction: column; }
.gt-detail-tabs { flex: 1; display: flex; flex-direction: column; }
.gt-detail-tabs :deep(.el-tabs__header) {
  padding: 0 var(--gt-space-4);
  margin-bottom: 0;
  border-bottom: 1px solid var(--gt-color-border-light);
}
.gt-detail-tabs :deep(.el-tabs__content) {
  flex: 1; overflow-y: auto; padding: var(--gt-space-4);
}

.gt-detail-section { margin-bottom: var(--gt-space-5); }
.gt-detail-title {
  font-size: var(--gt-font-size-xl); font-weight: 700;
  color: var(--gt-color-primary-dark); margin-bottom: var(--gt-space-3);
}
.gt-title-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-3);
}
.gt-title-row .gt-detail-title { margin-bottom: 0; }
.gt-section-label {
  font-size: var(--gt-font-size-sm); font-weight: 600;
  color: var(--gt-color-text-secondary); margin-bottom: var(--gt-space-2);
}

.gt-status-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
  margin-left: 4px;
}

.gt-quick-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--gt-space-2);
}
.gt-workflow-hint {
  display: flex; align-items: center; gap: 4px; margin-bottom: 8px;
  padding: 6px 10px; background: linear-gradient(135deg, #f5f0ff 0%, #faf8fd 100%);
  border-radius: 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-primary-light); flex-wrap: wrap;
}
.gt-workflow-hint-label { font-weight: 600; color: var(--gt-color-primary-dark); margin-right: 2px; }
.gt-workflow-step { background: var(--gt-color-bg-white); padding: 1px 6px; border-radius: 4px; border: 1px solid var(--gt-color-border-purple); white-space: nowrap; }
.gt-workflow-arrow { color: var(--gt-color-primary-lighter); font-size: var(--gt-font-size-xs); }
.gt-quick-tip {
  font-size: var(--gt-font-size-xs); color: var(--gt-color-info); line-height: 1.5;
  padding: 6px 10px; margin-bottom: 10px;
  background: var(--gt-color-bg); border-radius: 6px; border-left: 3px solid var(--gt-color-primary);
}
.gt-quick-btn {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: var(--gt-space-3); border-radius: var(--gt-radius-sm);
  cursor: pointer; transition: all var(--gt-transition-fast);
  border: 1px solid transparent; font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}
.gt-quick-btn:hover {
  background: var(--gt-color-primary-bg);
  border-color: var(--gt-color-primary-lighter);
  color: var(--gt-color-primary);
}

.gt-board-loading { padding: var(--gt-space-6) 0; }
.gt-board-empty { padding: var(--gt-space-4) 0; }
.gt-board-empty-hint {
  font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary);
  text-align: center; padding: var(--gt-space-4) 0;
}

/* 指标卡片 */
.gt-board-cards {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
  margin-bottom: var(--gt-space-4);
}
.gt-board-card {
  position: relative; overflow: hidden;
  display: flex; align-items: center; gap: 10px;
  padding: 12px 14px; border-radius: 10px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  cursor: pointer;
  animation: gt-card-pop 0.4s ease-out both;
}
.gt-board-card:nth-child(1) { animation-delay: 0s; }
.gt-board-card:nth-child(2) { animation-delay: 0.06s; }
.gt-board-card:nth-child(3) { animation-delay: 0.12s; }
.gt-board-card:nth-child(4) { animation-delay: 0.18s; }
.gt-board-card:nth-child(5) { animation-delay: 0.24s; }
.gt-board-card:nth-child(6) { animation-delay: 0.3s; }
@keyframes gt-card-pop {
  from { opacity: 0; transform: scale(0.92) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
.gt-board-card:hover {
  transform: translateY(-3px) scale(1.02);
  box-shadow: 0 6px 20px rgba(75, 45, 119, 0.12);
  border-color: var(--gt-color-primary-lighter, #a78bca);
}
.gt-board-card:active {
  transform: scale(0.97);
  transition-duration: 0.08s;
}
.gt-board-card__icon {
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.gt-board-card__body { flex: 1; min-width: 0; }
.gt-board-card__value {
  display: block; font-size: 18px; font-weight: 700;
  color: var(--gt-color-primary); line-height: 1.2;
}
.gt-board-card__label {
  display: block; font-size: 11px;
  color: var(--gt-color-text-secondary); margin-top: 2px;
}
.gt-board-card__bar {
  position: absolute; bottom: 0; left: 0; right: 0;
}

/* Section */
.gt-board-section { margin-bottom: var(--gt-space-4); }
.gt-board-section__title {
  font-size: var(--gt-font-size-sm); font-weight: 600;
  color: var(--gt-color-primary-dark); margin-bottom: 10px;
}

/* 审计流程图 */
.gt-flow {
  display: flex; align-items: center; justify-content: center;
  padding: 12px 0; margin-bottom: 14px;
  background: linear-gradient(135deg, #f9f7fc 0%, #fff 100%);
  border-radius: 10px; border: 1px solid var(--gt-color-border-light);
}
.gt-flow__step { display: flex; align-items: center; }
.gt-flow__node {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 8px 14px; border-radius: 8px;
  transition: transform 0.2s, box-shadow 0.2s;
  min-width: 72px;
}
.gt-flow__node:hover { transform: scale(1.05); box-shadow: 0 2px 8px rgba(75,45,119,0.12); }
.gt-flow__node--s0 { background: var(--gt-color-primary); color: #fff; }
.gt-flow__node--s1 { background: #e67e22; color: #fff; }
.gt-flow__node--s2 { background: #8e44ad; color: #fff; }
.gt-flow__node--s3 { background: #27ae60; color: #fff; }
.gt-flow__step-num { font-size: 10px; opacity: 0.8; }
.gt-flow__step-label { font-size: 11px; font-weight: 700; white-space: nowrap; }
.gt-flow__step-pct { font-size: 13px; font-weight: 800; }
.gt-flow__connector { padding: 0 4px; }
.gt-flow__arrow { font-size: 14px; color: var(--gt-color-primary-lighter); }

/* 流程明细展开 */
.gt-flow-detail {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;
}
.gt-flow-detail__group {
  border-radius: 8px; overflow: hidden;
  border: 1px solid var(--gt-color-border-light);
}
.gt-flow-detail__group--wide {
  grid-column: 1 / -1;
}
.gt-flow-detail__header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 12px; font-size: 11px; font-weight: 700; color: #fff;
}
.gt-flow-detail__header--s0 { background: var(--gt-color-primary); }
.gt-flow-detail__header--s1 { background: #e67e22; }
.gt-flow-detail__header--s2 { background: #8e44ad; }
.gt-flow-detail__header--s3 { background: #27ae60; }
.gt-flow-detail__summary { font-weight: 400; opacity: 0.9; }
.gt-flow-detail__items { padding: 4px 0; background: #fff; }
.gt-flow-detail__items--grid {
  display: grid; grid-template-columns: repeat(2, 1fr);
}
.gt-flow-detail__row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 12px; font-size: 12px; cursor: pointer;
  transition: background 0.15s;
}
.gt-flow-detail__row:hover { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-flow-detail__code { font-weight: 700; color: var(--gt-color-primary); min-width: 14px; }
.gt-flow-detail__name { color: var(--gt-color-text-secondary); min-width: 56px; font-size: 11px; }
.gt-flow-detail__bar { flex: 1; min-width: 30px; }
.gt-flow-detail__stat {
  font-size: 11px; font-weight: 600; color: var(--gt-color-primary-dark);
  min-width: 30px; text-align: right; font-variant-numeric: tabular-nums;
}
.gt-flow-detail__empty {
  padding: 8px 12px; font-size: 11px; color: var(--gt-color-text-placeholder);
  text-align: center;
}

/* 财务分析指标（致同紫体系 + 动画） */
.gt-fa {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;
}
.gt-fa__card {
  border-radius: 10px; overflow: hidden;
  border: 1px solid var(--gt-color-border-light);
  animation: gt-fa-slide-in 0.4s ease-out both;
  transition: transform 0.2s, box-shadow 0.2s;
}
.gt-fa__card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(75, 45, 119, 0.1);
}
@keyframes gt-fa-slide-in {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.gt-fa__header {
  display: flex; align-items: center; gap: 6px;
  padding: 9px 14px; font-size: 12px; font-weight: 700; color: #fff;
}
.gt-fa__header-icon { font-size: 14px; }
.gt-fa__header--profit { background: linear-gradient(135deg, var(--gt-color-primary-dark, #3a1f5e), var(--gt-color-primary, #4b2d77)); }
.gt-fa__header--ops { background: linear-gradient(135deg, #1a6b5c, var(--gt-color-teal, #2db89a)); }
.gt-fa__header--debt { background: linear-gradient(135deg, #7c2d2d, var(--gt-color-coral, #e74c3c)); }
.gt-fa__header--growth { background: linear-gradient(135deg, #8b5e0b, #e6a817); }
.gt-fa__body { padding: 6px 0; background: #fff; }
.gt-fa__row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 7px 14px; font-size: 12px; cursor: default;
  transition: background 0.15s;
}
.gt-fa__row:hover { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-fa__label { color: var(--gt-color-text-secondary); }
.gt-fa__value {
  font-weight: 600; color: var(--gt-color-primary-dark);
  font-variant-numeric: tabular-nums;
}
.gt-fa__value--negative { color: var(--gt-color-coral); }
.gt-fa__value--link {
  color: var(--gt-color-primary); cursor: pointer;
  text-decoration: underline dotted; text-underline-offset: 2px;
}
.gt-fa__value--link:hover { color: var(--gt-color-primary-dark); }

.gt-empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
}

/* 报表卡片 */
.gt-report-links { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.gt-report-card {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 20px 12px; border-radius: 10px;
  border: 1px solid var(--gt-color-border-light); cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary);
  animation: gt-card-pop 0.4s ease-out both;
}
.gt-report-card:hover {
  transform: translateY(-3px) scale(1.03);
  border-color: var(--gt-color-primary-lighter);
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
  box-shadow: 0 6px 16px rgba(75, 45, 119, 0.1);
}
.gt-report-card:active { transform: scale(0.96); transition-duration: 0.08s; }
.gt-report-card__icon { font-size: 28px; }
.gt-report-card__name { font-weight: 600; text-align: center; }
.gt-report-hint {
  text-align: center; font-size: 11px; color: var(--gt-color-text-placeholder);
  margin-top: 10px;
}

/* 附件区 */
.gt-att__header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
}
.gt-att__title { margin: 0; font-size: var(--gt-font-size-sm); font-weight: 700; color: var(--gt-color-primary-dark); }
.gt-att__grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;
}
.gt-att__card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-radius: 8px;
  border: 1px solid var(--gt-color-border-light);
  cursor: pointer; transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  animation: gt-card-pop 0.4s ease-out both;
}
.gt-att__card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(75,45,119,0.08);
  border-color: var(--gt-color-primary-lighter);
}
.gt-att__card-icon { font-size: 24px; flex-shrink: 0; }
.gt-att__card-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.gt-att__card-name {
  font-size: 12px; font-weight: 600; color: var(--gt-color-text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gt-att__card-meta { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--gt-color-text-secondary); }
.gt-att__card-wp {
  font-size: 10px; font-weight: 700; color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg); padding: 2px 6px; border-radius: 4px;
  white-space: nowrap;
}
</style>
