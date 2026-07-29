<template>
  <div class="gt-procedure gt-fade-in">
    <!-- 顶部工具栏 -->
    <div class="gt-proc-toolbar">
      <div class="gt-proc-toolbar__left">
        <h2 class="gt-proc-toolbar__title">底稿粗裁与委派</h2>
        <el-tag size="small" type="info">{{ projectId.slice(0, 8) }}</el-tag>
      </div>
      <div class="gt-proc-toolbar__right">
        <el-button size="small" @click="openOverview">📊 全项目概览</el-button>
        <template v-if="canManage">
          <el-button size="small" type="warning" @click="onSmartTrim">🤖 一键智能裁剪</el-button>
          <el-button size="small" @click="openDelegateWizard">🎯 程序委派向导</el-button>
          <el-button size="small" type="primary" @click="saveTrim(true)" :loading="saving">💾 保存粗裁</el-button>
        </template>
        <el-tag v-else size="small" type="info">只读（仅项目经理可裁剪/委派）</el-tag>
        <!-- 低频操作收敛，避免工具栏拥挤/窄屏折行 -->
        <el-dropdown size="small" trigger="click" @command="onToolbarCommand">
          <el-button size="small">更多 <el-icon style="margin-left:2px"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export" :disabled="exporting">📤 导出方案</el-dropdown-item>
              <el-dropdown-item v-if="canManage" command="ref" divided>📋 参照其他项目</el-dropdown-item>
              <el-dropdown-item v-if="canManage" command="reset">🔄 恢复初始</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 角色术语说明（需求 14.1：区分五类角色，不把高阶复核显示为程序行 reviewer） -->
    <el-alert type="info" :closable="false" class="gt-proc-role-legend">
      <template #title>
        <span style="font-size:12px">
          <strong>两层裁剪：</strong>本页做 <strong>粗裁</strong>（{{ TERMS.workpaperScope }}是否执行 + 指定{{ TERMS.workpaperLead }}）；
          进入底稿程序表控制台做 <strong>细裁</strong>（{{ TERMS.procedureApplicability }} + 委派{{ TERMS.procedureAssignee }} / {{ TERMS.operationReviewer }}）。
          {{ TERMS.highOrderReviewer }} 的高阶复核由底稿/项目层机制负责，不在此显示为程序行复核人。
        </span>
      </template>
    </el-alert>

    <!-- 裁剪操作指南（折叠） -->
    <details class="gt-proc-guide-details">
      <summary>📘 裁剪操作指南（展开查看）</summary>
      <div class="gt-proc-guide-content">
        <p><strong>操作步骤：</strong></p>
        <ol>
          <li>按审计循环切换 Tab（A~S），逐个循环处理</li>
          <li>对每条程序切换「适用性开关」（执行/裁剪）</li>
          <li>被裁剪的程序<strong>必须填写裁剪理由</strong>（否则无法保存）</li>
          <li>指定该底稿的<strong>主编人</strong>（底稿主编下拉）</li>
          <li>确认无误后点「💾 保存粗裁」</li>
        </ol>
        <p><strong>快捷功能：</strong></p>
        <ul>
          <li>🤖 <strong>一键智能裁剪</strong>：读取试算表，只裁"科目无数据"的循环（有数据保留；取数失败不裁=安全兜底）</li>
          <li>📋 <strong>参照其他项目</strong>：套用历史项目的裁剪方案（续审项目可快速对齐上年）</li>
          <li>🎯 <strong>程序委派向导</strong>：按循环/人员快速分派</li>
          <li>📊 <strong>全项目概览</strong>：各循环保留/裁剪/缺理由一览，点击跳转对应循环</li>
          <li>📤 <strong>导出方案</strong>：导出全循环裁剪方案 xlsx，供留痕/打印/复核签字</li>
        </ul>
        <p><strong>注意事项：</strong></p>
        <ul>
          <li>切换循环前先保存（未保存改动会丢失）</li>
          <li>「恢复初始」会连已持久化的委派一并回滚</li>
          <li>非项目经理/合伙人角色看到只读视图</li>
        </ul>
      </div>
    </details>

    <!-- 统计卡片（点击联动筛选） -->
    <div class="gt-proc-stats-header">
      <span>以下为<strong>当前循环（{{ activeCycle }}）</strong>统计</span>
      <el-button link type="primary" @click="openOverview">查看全项目概览 ›</el-button>
    </div>
    <div class="gt-proc-stats">
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === '' }" @click="statsFilter = ''">
        <div class="gt-proc-stat-card__num">{{ progressStats.total }}</div>
        <div class="gt-proc-stat-card__label">总程序</div>
      </div>
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === 'execute' }" @click="statsFilter = statsFilter === 'execute' ? '' : 'execute'">
        <div class="gt-proc-stat-card__num" style="color: var(--gt-color-primary)">{{ progressStats.execute }}</div>
        <div class="gt-proc-stat-card__label">保留执行</div>
      </div>
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === 'trimmed' }" @click="statsFilter = statsFilter === 'trimmed' ? '' : 'trimmed'">
        <div class="gt-proc-stat-card__num" style="color: var(--gt-color-coral)">{{ progressStats.trimmed }}</div>
        <div class="gt-proc-stat-card__label">已裁剪</div>
      </div>
      <div class="gt-proc-stat-card" :class="{ 'is-active': statsFilter === 'custom' }" @click="statsFilter = statsFilter === 'custom' ? '' : 'custom'">
        <div class="gt-proc-stat-card__num" style="color: var(--gt-color-success)">{{ progressStats.custom }}</div>
        <div class="gt-proc-stat-card__label">自定义新增</div>
      </div>
      <el-tooltip content="执行率 = 保留执行 / 总程序（本页粗裁口径，非底稿完成率）" placement="top">
        <div class="gt-proc-stat-card gt-proc-stat-card--progress">
          <el-progress
            type="circle"
            :percentage="progressStats.total > 0 ? Math.round(progressStats.execute / progressStats.total * 100) : 0"
            :width="50"
            :stroke-width="5"
          />
          <div class="gt-proc-stat-card__label">执行率</div>
        </div>
      </el-tooltip>
    </div>

    <!-- 循环 Tab -->
    <div class="gt-proc-cycle-bar">
      <el-tabs v-model="activeCycle" :before-leave="onCycleBeforeLeave" @tab-change="loadProcedures" class="gt-proc-tabs">
        <el-tab-pane v-for="c in cycles" :key="c.code" :label="c.label" :name="c.code" />
      </el-tabs>
    </div>

    <!-- 表格工具栏 -->
    <div class="gt-proc-table-toolbar">
      <span class="gt-proc-table-toolbar__label">{{ activeCycle }} 循环 · {{ filteredProcedures.length }} 个程序</span>
      <div class="gt-proc-table-toolbar__actions">
        <el-input
          v-model="searchText"
          placeholder="搜索程序名称 / 编号"
          size="small"
          clearable
          style="width: 200px"
        />
        <template v-if="canManage">
          <el-divider direction="vertical" />
          <el-button size="small" type="primary" text @click="batchSetAll('execute')">✓ 全部执行</el-button>
          <el-button size="small" type="danger" text @click="batchSetAll('not_applicable')">✗ 全部不适用</el-button>
          <el-divider direction="vertical" />
          <el-button size="small" @click="addCustom">+ 新增程序</el-button>
        </template>
      </div>
    </div>

    <!-- 程序列表 -->
    <div class="gt-proc-table-wrap">
      <el-table
        :data="filteredProcedures"
        v-loading="loading"
        border
        stripe
        style="width: 100%; font-size: 13px"
        max-height="calc(100vh - 340px)"
        row-key="id"
      >
        <el-table-column prop="procedure_code" label="编号" min-width="100" resizable sortable />
        <el-table-column prop="procedure_name" label="程序名称" min-width="280" resizable show-overflow-tooltip />
        <el-table-column label="适用性" width="140" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row._applicable"
              active-text="执行"
              inactive-text="裁剪"
              :active-value="true"
              :inactive-value="false"
              :disabled="!canManage"
              @change="onApplicableChange(row)"
              inline-prompt
              style="--el-switch-on-color: var(--gt-color-primary); --el-switch-off-color: var(--gt-color-coral)"
            />
          </template>
        </el-table-column>
        <el-table-column label="裁剪理由" min-width="220" resizable>
          <template #default="{ row }">
            <el-select
              v-if="!row._applicable"
              v-model="row.skip_reason"
              placeholder="选择或输入裁剪理由..."
              size="small"
              clearable
              filterable
              allow-create
              default-first-option
              :disabled="!canManage"
              style="width: 100%"
            >
              <el-option v-for="r in COMMON_SKIP_REASONS" :key="r" :label="r" :value="r" />
            </el-select>
            <span v-else class="gt-proc-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="关联底稿" min-width="140" resizable class-name="gt-proc-wpcode-col">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.wp_code"
              :content="expandWpCodeTooltip(row.wp_code)"
              placement="top"
              :disabled="expandWpCodeTooltip(row.wp_code) === row.wp_code"
            >
              <span>{{ row.wp_code }}</span>
            </el-tooltip>
            <span v-else class="gt-proc-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column width="200" align="center">
          <template #header>
            <el-tooltip content="粗裁层：底稿主编（WorkingPaper.assigned_to），选择后即时保存（无需点保存粗裁）。程序执行人/操作复核人在底稿程序表控制台按行细裁委派。" placement="top">
              <span>底稿主编 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <div v-if="row._applicable" class="gt-proc-assignee-cell">
              <el-select
                v-model="row.assigned_to"
                placeholder="选择底稿主编"
                size="small"
                clearable
                filterable
                :disabled="!canManage"
                style="flex: 1; min-width: 0"
                @change="onAssigneeChange(row)"
              >
                <el-option
                  v-for="m in sortedTeamMembers"
                  :key="m.staff_id"
                  :label="assigneeOptionLabel(m)"
                  :value="m.staff_id"
                />
              </el-select>
              <span v-if="savedAssignees.has(row.id)" class="gt-proc-saved-flag">✓ 已存</span>
            </div>
            <span v-else class="gt-proc-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_custom ? 'success' : 'info'">
              {{ row.is_custom ? '自定义' : '模板' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row._applicable && row.wp_id"
              size="small"
              text
              type="primary"
              @click="enterProgramConsole(row)"
            >
              程序裁剪 ›
            </el-button>
            <el-tooltip
              v-else-if="row._applicable && !row.wp_id"
              content="该程序底稿尚未生成。保存粗裁后，保留执行的程序会进入待执行底稿库；可在「底稿列表 / 生命周期」页生成底稿后再回此处逐条细裁。"
              placement="top"
            >
              <el-button size="small" text disabled>未生成</el-button>
            </el-tooltip>
            <el-button v-if="row.is_custom && canManage" size="small" text type="danger" @click="removeCustom(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 底部提示 -->
    <div class="gt-proc-footer-tip">
      💡 双层裁剪：此处<strong>粗裁</strong>底稿范围（是否执行）并指定<strong>底稿主编</strong>；点「程序裁剪 ›」进入底稿程序表控制台，对每条审计程序做<strong>细裁</strong>（程序适用性）并委派<strong>程序执行人 / 操作复核人</strong>。保存后保留执行的程序即进入待执行底稿库。
    </div>

    <!-- 新增自定义程序弹窗 -->
    <el-dialog append-to-body v-model="showAddCustomDialog" title="新增自定义程序" width="520px">
      <el-form :model="customForm" label-width="100px">
        <el-form-item label="程序名称" required>
          <el-input v-model="customForm.name" placeholder="如：XX 专项核查程序" />
        </el-form-item>
        <el-form-item label="程序编码">
          <el-input v-model="customForm.code" placeholder="可选，留空自动生成（如 D-C01）" />
        </el-form-item>
        <el-form-item label="底稿模板">
          <div class="gt-proc-custom-template-area">
            <el-upload
              :auto-upload="false"
              :limit="1"
              accept=".xlsx,.xls"
              :on-change="onCustomFileChange"
              :file-list="customForm.fileList"
            >
              <el-button size="small" type="primary">📄 上传已有文件</el-button>
            </el-upload>
            <span class="gt-proc-custom-template-or">或</span>
            <el-button size="small" @click="downloadBlankTemplate" :loading="downloadingTemplate">
              📥 下载空白模板
            </el-button>
          </div>
          <div style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 6px">
            下载空白模板包含：编制要求说明 + 数据表（顶部编制信息表头已自动配齐：被审计单位/编制人/复核人/截止日/索引号，并预填试算表科目余额）
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddCustomDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!customForm.name.trim()" @click="submitCustomProcedure">
          {{ customForm.fileList.length ? '创建并上传模板' : '仅创建程序' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 参照弹窗 -->
    <el-dialog append-to-body v-model="showRefDialog" title="参照其他项目程序" width="480px">
      <p style="font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 16px">
        从已有项目复制程序裁剪方案，适用于同类型客户或续聘项目。
      </p>
      <el-form label-width="80px">
        <el-form-item label="参照项目">
          <el-select
            v-model="refProjectId"
            filterable
            placeholder="搜索并选择参照项目"
            style="width: 100%"
          >
            <el-option
              v-for="p in projectOptions"
              :key="p.id"
              :label="p.name || p.client_name || p.id"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRefDialog = false">取消</el-button>
        <el-button type="primary" @click="applyRef" :disabled="!refProjectId">应用方案</el-button>
      </template>
    </el-dialog>

    <!-- 智能裁剪确认弹窗 -->
    <el-dialog append-to-body v-model="showSmartTrimDialog" title="智能裁剪" width="560px">
      <p style="font-size: 13px; color: var(--gt-color-text-secondary); margin-bottom: 12px">
        系统依据<strong>试算表科目余额</strong>自动裁剪无数据的科目程序（有数据的科目一律保留，宁松勿紧）：
      </p>
      <ul class="gt-proc-smart-rules">
        <li><strong>裁剪</strong>：D~N 实质性循环中，<strong>试算表无科目数据（无余额 / 未发生）</strong>的循环所属程序</li>
        <li><strong>保留</strong>：试算表<strong>有数据</strong>的科目循环（有余额即全部保留，供逐条细裁）</li>
        <li><strong>保留</strong>：A 完成阶段 / S 专项 / B 计划 / C 控制测试（非科目余额驱动，不按数据裁剪）</li>
        <li><strong>保留</strong>：标记"必须"（is_mandatory）/ 已有执行进度 / 已手动设置理由的程序</li>
      </ul>

      <!-- 裁剪范围选择 -->
      <div class="gt-proc-smart-scope">
        <div class="gt-proc-smart-scope__title">裁剪范围：</div>
        <el-radio-group v-model="smartTrimScope" style="margin-bottom: 8px">
          <el-radio value="all">全部循环（一键裁剪所有）</el-radio>
          <el-radio value="current">仅当前循环（{{ activeCycle }}）</el-radio>
          <el-radio value="custom">自定义选择循环</el-radio>
        </el-radio-group>
        <div v-if="smartTrimScope === 'custom'" class="gt-proc-smart-scope__cycles">
          <el-checkbox-group v-model="smartTrimCycles">
            <el-checkbox v-for="c in cycles.filter(x => x.code !== 'A' && x.code !== 'S')" :key="c.code" :value="c.code" :label="c.label" />
          </el-checkbox-group>
        </div>
      </div>

      <p style="font-size: 12px; color: var(--gt-color-text-tertiary); margin-top: 8px">
        💡 依据试算表判断：仅裁"无数据"科目对应程序，有数据科目全部保留。需先导入试算表；裁剪后可逐条恢复。
      </p>
      <template #footer>
        <el-button @click="showSmartTrimDialog = false">取消</el-button>
        <el-button type="warning" @click="confirmSmartTrim">确认一键裁剪</el-button>
      </template>
    </el-dialog>

    <!-- 程序委派向导（V105 三粒度委派：materialize 前置 job + 服务端 preview + 真实 applied/unchanged/conflict + TTL/409） -->
    <el-dialog append-to-body v-model="delegateWizard.visible" title="程序委派向导" width="620px">
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        <template #title>
          <span style="font-size:12px">
            按当前循环（{{ activeCycle }}）批量委派程序执行人。未生成任务的程序行会先执行可追踪的
            <strong>物化 job</strong>，job 成功后才产生可消费的服务端预览；应用后展示真实
            <strong>已应用 / 未变更 / 冲突</strong> 统计。
          </span>
        </template>
      </el-alert>

      <el-form label-width="110px">
        <el-form-item :label="TERMS.procedureAssignee" required>
          <el-select v-model="delegateWizard.assigneeId" placeholder="选择程序执行人" filterable clearable style="width:100%">
            <el-option v-for="m in teamMembers" :key="m.staff_id"
              :label="m.staff_name + (m.role_label ? ` (${m.role_label})` : '')" :value="m.staff_id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="TERMS.operationReviewer">
          <el-select v-model="delegateWizard.reviewerId" placeholder="选择操作复核人（可留空，按 reviewer 回退规则）" filterable clearable style="width:100%">
            <el-option v-for="m in teamMembers" :key="m.staff_id"
              :label="m.staff_name + (m.role_label ? ` (${m.role_label})` : '')" :value="m.staff_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="仅未分配">
          <el-switch v-model="delegateWizard.unassignedOnly" />
        </el-form-item>
      </el-form>

      <!-- 物化 job 状态 -->
      <div v-if="delegateWizard.jobStatus" class="gt-proc-wizard-job">
        <el-tag size="small" :type="delegateWizard.jobStatus === 'succeeded' ? 'success' : delegateWizard.jobStatus === 'failed' ? 'danger' : 'warning'">
          物化 job：{{ jobStatusLabel(delegateWizard.jobStatus) }}
        </el-tag>
      </div>

      <!-- 服务端预览统计 -->
      <div v-if="delegateWizard.preview" class="gt-proc-wizard-preview">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="目标数">{{ delegateWizard.preview.target_count ?? delegateWizard.preview.targets ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="冲突数">{{ delegateWizard.preview.conflict_count ?? delegateWizard.preview.conflicts ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="已分配">{{ delegateWizard.preview.assigned_count ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="预览状态">{{ delegateWizard.preview.status || 'ready' }}</el-descriptions-item>
          <el-descriptions-item v-if="delegateWizard.preview.expires_at" label="预览有效期至" :span="2">{{ delegateWizard.preview.expires_at }}</el-descriptions-item>
        </el-descriptions>
        <div class="gt-proc-wizard-tip">预览为一次性凭证：过期 / 篡改 / 目标版本或成员资格变化时应用被拒绝（409），需重新预览。</div>
      </div>

      <!-- 应用结果统计（真实 applied/unchanged/conflict） -->
      <div v-if="delegateWizard.applyResult" class="gt-proc-wizard-result">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="已应用">{{ delegateWizard.applyResult.applied ?? delegateWizard.applyResult.changed ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="未变更">{{ delegateWizard.applyResult.unchanged ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="冲突">{{ delegateWizard.applyResult.conflict ?? delegateWizard.applyResult.conflicts ?? 0 }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <template #footer>
        <el-button @click="delegateWizard.visible = false">关闭</el-button>
        <el-button v-if="!delegateWizard.previewId" type="primary" :loading="delegateWizard.loading" @click="runDelegatePreview">预览</el-button>
        <el-button v-else type="primary" :loading="delegateWizard.loading" @click="runDelegateApply">确认委派</el-button>
      </template>
    </el-dialog>

    <!-- 全项目裁剪概览抽屉（P1-3 / P0-1：各循环 保留/裁剪/缺理由 一览，点击跳转对应循环） -->
    <el-drawer v-model="showOverviewDrawer" title="全项目裁剪概览" size="560px" append-to-body>
      <div v-loading="overviewLoading">
        <el-alert type="info" :closable="false" style="margin-bottom:12px">
          <template #title>
            <span style="font-size:12px">按各审计循环汇总裁剪进度；「缺理由」= 已裁剪但未填裁剪理由（保存会被阻断，需补填）。点击行跳转对应循环。</span>
          </template>
        </el-alert>
        <el-table :data="overviewRows" size="small" border style="font-size:13px" @row-click="(r:any) => !r.uninitialized && jumpToCycleFromOverview(r.code)">
          <el-table-column prop="label" label="循环" min-width="120" />
          <el-table-column label="总程序" width="80" align="center">
            <template #default="{ row }">
              <span v-if="row.uninitialized" class="gt-proc-text-muted">未初始化</span>
              <span v-else>{{ row.total }}</span>
            </template>
          </el-table-column>
          <el-table-column label="保留" width="70" align="center">
            <template #default="{ row }"><span v-if="!row.uninitialized" style="color: var(--gt-color-primary)">{{ row.execute }}</span><span v-else>—</span></template>
          </el-table-column>
          <el-table-column label="裁剪" width="70" align="center">
            <template #default="{ row }"><span v-if="!row.uninitialized" style="color: var(--gt-color-coral)">{{ row.trimmed }}</span><span v-else>—</span></template>
          </el-table-column>
          <el-table-column label="缺理由" width="80" align="center">
            <template #default="{ row }">
              <el-tag
                v-if="!row.uninitialized && row.missingReason > 0"
                size="small"
                type="danger"
                style="cursor:pointer"
                @click.stop="jumpToCycleFromOverview(row.code, 'trimmed')"
              >{{ row.missingReason }}</el-tag>
              <span v-else class="gt-proc-text-muted">{{ row.uninitialized ? '—' : 0 }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-proc-overview-totals">
          <span>合计（已初始化循环）：</span>
          <span>总 <strong>{{ overviewTotals.total }}</strong></span>
          <span>保留 <strong style="color: var(--gt-color-primary)">{{ overviewTotals.execute }}</strong></span>
          <span>裁剪 <strong style="color: var(--gt-color-coral)">{{ overviewTotals.trimmed }}</strong></span>
          <span v-if="overviewTotals.missingReason > 0">缺理由 <strong style="color: var(--el-color-danger)">{{ overviewTotals.missingReason }}</strong></span>
        </div>
        <div style="margin-top:12px; text-align:right">
          <el-button size="small" @click="exportScheme" :loading="exporting">📤 导出方案</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  getProcedures, updateProcedureTrim, initProcedures,
  addCustomProcedure, applyProcedureScheme, listProjects,
  assignProcedures,
  previewProcedureDelegation, applyProcedureDelegation,
} from '@/services/commonApi'
import { listAssignments } from '@/services/staffApi'
import { ROLE_TERMS, newRequestId } from '@/components/workpaper/composables/procedureConsoleOverlay'
import http from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { useAuditContext } from '@/composables/useAuditContext'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'

// 权限：仅项目经理+（admin/partner/manager）可裁剪/委派/新增/删除；其余角色只读
const { currentRole } = usePermissionMatrix()
const canManage = computed(() => ['admin', 'partner', 'manager'].includes(currentRole.value))

// 统一中文术语（需求 14.1）
const TERMS = {
  workpaperScope: '底稿范围',
  workpaperLead: ROLE_TERMS.workpaperLead,
  procedureApplicability: '程序适用性',
  procedureAssignee: ROLE_TERMS.procedureAssignee,
  operationReviewer: ROLE_TERMS.operationReviewer,
  highOrderReviewer: ROLE_TERMS.highOrderReviewer,
}

// P0-2 常见裁剪理由（点选优先 + allow-create 自由输入，统一措辞利于复核/留痕）
const COMMON_SKIP_REASONS = [
  '本期无该类交易或余额',
  '科目在试算表中无数据（无余额/未发生）',
  '金额低于重要性水平（不重要）',
  '相关认定已在其他底稿覆盖',
  '被审计单位无此类业务',
  '经风险评估该程序不适用',
]

// P1-4 底稿主编候选角色排序优先级（审计员/项目经理优先，高阶复核靠后）
const ROLE_PRIORITY: Record<string, number> = {
  auditor: 1, manager: 2, reviewer: 3, eqcr: 4, partner: 5, signing_partner: 6,
}

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const { year } = useAuditContext()

// 科目余额驱动的实质性循环（按试算表科目有无数据判断裁剪；B/C 为计划/控制类非科目余额驱动，A/S 恒保留）
const DATA_DRIVEN_CYCLES = new Set(['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'])

const cycles = [
  { code: 'B', label: 'B 初步业务' }, { code: 'C', label: 'C 控制测试' },
  { code: 'D', label: 'D 收入' }, { code: 'E', label: 'E 货币资金' },
  { code: 'F', label: 'F 存货' }, { code: 'G', label: 'G 投资' },
  { code: 'H', label: 'H 固定资产' }, { code: 'I', label: 'I 无形资产' },
  { code: 'J', label: 'J 职工薪酬' }, { code: 'K', label: 'K 管理' },
  { code: 'L', label: 'L 债务' }, { code: 'M', label: 'M 权益' },
  { code: 'N', label: 'N 税金' }, { code: 'A', label: 'A 完成阶段' },
  { code: 'S', label: 'S 专项' },
]

const activeCycle = ref('D')
const procedures = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const showRefDialog = ref(false)
const showSmartTrimDialog = ref(false)
const smartTrimScope = ref<'all' | 'current' | 'custom'>('all')
const smartTrimCycles = ref<string[]>([])
const refProjectId = ref('')
const projectOptions = ref<any[]>([])
const statsFilter = ref('') // '' | 'execute' | 'trimmed' | 'custom'
const searchText = ref('') // P2-7 按程序名/编号搜索
const teamMembers = ref<{ staff_id: string; staff_name: string; role?: string; role_label?: string }[]>([])
let originalSnapshot: any[] = [] // 用于恢复初始状态

// P1-5 底稿主编"即时保存"瞬时反馈（保存成功后短暂显示 ✓ 已存）
const savedAssignees = ref<Set<string>>(new Set())

// P1-3 / P0-1 全项目裁剪概览（按需懒加载各循环，不在挂载时全量拉取）
const showOverviewDrawer = ref(false)
const overviewLoading = ref(false)
const allCyclesData = ref<Record<string, any[] | null>>({}) // cycleCode → 程序列表（null=未初始化）
const exporting = ref(false)

const filteredProcedures = computed(() => {
  let list = procedures.value
  if (statsFilter.value === 'execute') list = list.filter(p => p._applicable)
  else if (statsFilter.value === 'trimmed') list = list.filter(p => !p._applicable)
  else if (statsFilter.value === 'custom') list = list.filter(p => p.is_custom)
  const kw = searchText.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(p =>
      (p.procedure_name || '').toLowerCase().includes(kw) ||
      (p.procedure_code || '').toLowerCase().includes(kw) ||
      (p.wp_code || '').toLowerCase().includes(kw),
    )
  }
  return list
})

// P1-4 底稿主编候选：按角色优先级排序（审计员/项目经理优先）
const sortedTeamMembers = computed(() =>
  [...teamMembers.value].sort((a, b) =>
    (ROLE_PRIORITY[a.role || ''] ?? 90) - (ROLE_PRIORITY[b.role || ''] ?? 90)),
)

// P1-4 各主编已负责底稿数（仅在全项目概览已加载后有值，用于负载均衡参考）
const assigneeLoadMap = computed(() => {
  const map: Record<string, number> = {}
  for (const list of Object.values(allCyclesData.value)) {
    if (!Array.isArray(list)) continue
    for (const p of list) {
      const applicable = p.status !== 'not_applicable' && p.status !== 'skip'
      if (applicable && p.assigned_to) map[p.assigned_to] = (map[p.assigned_to] || 0) + 1
    }
  }
  return map
})
const assigneeLoadLoaded = computed(() => Object.keys(allCyclesData.value).length > 0)

// 底稿主编下拉显示标签（角色 + 已负责张数）
function assigneeOptionLabel(m: { staff_id: string; staff_name: string; role_label?: string }) {
  const role = m.role_label ? ` (${m.role_label})` : ''
  const load = assigneeLoadLoaded.value ? ` · 已负责${assigneeLoadMap.value[m.staff_id] || 0}张` : ''
  return `${m.staff_name}${role}${load}`
}

// P1-3 / P0-1 全项目裁剪概览行（各循环 保留/裁剪/缺理由/未初始化）
const overviewRows = computed(() => {
  return cycles.map(c => {
    const list = allCyclesData.value[c.code]
    if (!Array.isArray(list)) {
      return { code: c.code, label: c.label, total: 0, execute: 0, trimmed: 0, missingReason: 0, uninitialized: !(c.code in allCyclesData.value) }
    }
    const execute = list.filter(p => p.status !== 'not_applicable' && p.status !== 'skip').length
    const trimmed = list.length - execute
    const missingReason = list.filter(p => (p.status === 'not_applicable' || p.status === 'skip') && !(p.skip_reason || '').trim()).length
    return { code: c.code, label: c.label, total: list.length, execute, trimmed, missingReason, uninitialized: false }
  })
})
const overviewTotals = computed(() => {
  const rows = overviewRows.value.filter(r => !r.uninitialized)
  return {
    total: rows.reduce((s, r) => s + r.total, 0),
    execute: rows.reduce((s, r) => s + r.execute, 0),
    trimmed: rows.reduce((s, r) => s + r.trimmed, 0),
    missingReason: rows.reduce((s, r) => s + r.missingReason, 0),
  }
})
const progressStats = computed(() => {
  const procs = procedures.value
  const total = procs.length
  const execute = procs.filter(p => p._applicable).length
  const trimmed = procs.filter(p => !p._applicable).length
  const custom = procs.filter(p => p.is_custom).length
  return { total, execute, trimmed, custom }
})

// 脏检查：适用性 / 裁剪理由 相对初始快照是否有未保存修改（委派人即时持久化，不计入）
const isDirty = computed(() => {
  const orig = new Map(originalSnapshot.map((o: any) => [o.id, o]))
  for (const p of procedures.value) {
    const o = orig.get(p.id)
    if (!o) return true // 新增行（未保存）
    if (Boolean(p._applicable) !== Boolean(o._applicable)) return true
    if ((p.skip_reason || '').trim() !== (o.skip_reason || '').trim()) return true
  }
  // 数量变化（删除/新增）
  return procedures.value.length !== originalSnapshot.length
})

// 加载程序列表
async function loadProcedures() {
  loading.value = true
  try {
    let procs = await getProcedures(projectId.value, activeCycle.value)
    if (!procs || procs.length === 0) {
      procs = await initProcedures(projectId.value, activeCycle.value)
    }
    // 转换 status → _applicable 布尔值
    procedures.value = (procs || []).map((p: any) => ({
      ...p,
      _applicable: p.status !== 'not_applicable' && p.status !== 'skip',
      is_custom: p.is_custom || p.source === 'custom',
      assigned_to: p.assigned_to || null,
      wp_id: p.wp_id || null,
    }))
    // 保存初始快照用于恢复
    originalSnapshot = JSON.parse(JSON.stringify(procedures.value))
  } finally { loading.value = false }
}

// 适用性切换
function onApplicableChange(row: any) {
  row.status = row._applicable ? 'execute' : 'not_applicable'
  if (row._applicable) row.skip_reason = ''
}

// 恢复初始状态（含回滚已即时持久化的委派人，避免内存与 DB 不一致）
async function resetAll() {
  try {
    await ElMessageBox.confirm('确定恢复到初始状态？所有未保存的修改将丢失（已委派的底稿主编也会一并还原）。', '恢复初始', {
      confirmButtonText: '确定恢复',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  // 回滚已持久化的委派：对比初始快照，assigned_to 变化的行调后端还原
  const origById = new Map(originalSnapshot.map((o: any) => [o.id, o]))
  const changedAssignees = procedures.value.filter(p => {
    const o = origById.get(p.id)
    return o && (o.assigned_to || null) !== (p.assigned_to || null)
  })
  for (const p of changedAssignees) {
    const o: any = origById.get(p.id)
    try {
      await assignProcedures(projectId.value, [{ procedure_id: p.id, staff_id: o.assigned_to || null }])
    } catch (e: any) {
      handleApiError(e, '还原委派')
    }
  }
  procedures.value = JSON.parse(JSON.stringify(originalSnapshot))
  statsFilter.value = ''
  ElMessage.success('已恢复初始状态')
}

// 批量设置（作用于当前筛选后的可见行；无筛选时即全部）
function batchSetAll(status: 'execute' | 'not_applicable') {
  for (const p of filteredProcedures.value) {
    p._applicable = status === 'execute'
    p.status = status
    if (status === 'execute') p.skip_reason = ''
  }
}

// 保存裁剪
// promptDelegate=true（点击「保存粗裁」按钮）保存成功后弹窗确认是否前往人员委派界面；
// 智能裁剪等内部调用传 false，不打断流程
async function saveTrim(promptDelegate = false) {
  // 裁剪理由必填（审计轨迹合规：裁剪必须记录理由）→ 缺失则阻断保存并定位
  const noReason = procedures.value.filter(p => !p._applicable && !p.skip_reason?.trim())
  if (noReason.length > 0) {
    ElMessage.error(`${noReason.length} 个裁剪程序未填写理由，裁剪须记录审计轨迹，请补充后再保存`)
    statsFilter.value = 'trimmed' // 定位到已裁剪项便于补填
    return
  }
  saving.value = true
  let ok = false
  try {
    await updateProcedureTrim(projectId.value, activeCycle.value,
      procedures.value.map(p => ({ id: p.id, status: p._applicable ? 'execute' : 'not_applicable', skip_reason: p.skip_reason })))
    // 保存成功 → 刷新初始快照，isDirty 归位
    originalSnapshot = JSON.parse(JSON.stringify(procedures.value))
    ElMessage.success('裁剪已保存，保留执行的程序已加入待执行底稿库')
    ok = true
  } catch (e: any) {
    handleApiError(e, '保存裁剪')
  } finally { saving.value = false }

  // 保存成功且来自按钮点击 → 确认后跳转人员委派（委派矩阵）界面
  // 确认框放在 try/finally 之外，避免"取消"被 handleApiError 误判为保存失败
  if (ok && promptDelegate) {
    try {
      await ElMessageBox.confirm(
        '粗裁已保存。是否前往「人员委派」界面，将保留执行的程序委派给审计人员？',
        '前往人员委派',
        { type: 'success', confirmButtonText: '前往委派', cancelButtonText: '暂不' },
      )
      router.push({
        name: 'WorkpaperList',
        params: { projectId: projectId.value },
        query: { view: 'matrix' },
      })
    } catch { /* 用户选择"暂不"，留在当前页 */ }
  }
}

// 新增自定义程序
const showAddCustomDialog = ref(false)
const downloadingTemplate = ref(false)
const customForm = ref<{ name: string; code: string; fileList: any[] }>({ name: '', code: '', fileList: [] })

function addCustom() {
  customForm.value = { name: '', code: '', fileList: [] }
  showAddCustomDialog.value = true
}

function onCustomFileChange(file: any) {
  customForm.value.fileList = [file]
}

async function downloadBlankTemplate() {
  const name = customForm.value.name.trim() || '自定义底稿'
  downloadingTemplate.value = true
  try {
    const response = await http.get(
      `/api/projects/${projectId.value}/procedures/${activeCycle.value}/blank-template`,
      {
        params: { procedure_name: name },
        responseType: 'blob',
      },
    )
    // http.ts blob 模式返回完整 response
    const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `底稿模板_${activeCycle.value}_${name}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('模板已下载，编辑后可上传回来')
  } catch (e: any) {
    handleApiError(e, '下载模板')
  } finally {
    downloadingTemplate.value = false
  }
}

async function submitCustomProcedure() {
  const name = customForm.value.name.trim()
  if (!name) return

  try {
    if (customForm.value.fileList.length > 0) {
      // 带模板文件：调用 custom-with-template 接口
      const params = new URLSearchParams({
        procedure_name: name,
        ...(customForm.value.code ? { procedure_code: customForm.value.code } : {}),
      })
      const { data: result } = await http.post(
        `/api/projects/${projectId.value}/procedures/${activeCycle.value}/custom-with-template?${params}`,
      )
      const addedRow = {
        ...result,
        _applicable: true,
        is_custom: true,
        procedure_name: name,
        procedure_code: result.wp_code || customForm.value.code,
      }
      procedures.value.push(addedRow)
      // 自定义程序已即时持久化 → 同步初始快照，避免 isDirty 误报
      originalSnapshot.push(JSON.parse(JSON.stringify(addedRow)))

      // 上传文件到底稿存储（如果有 wp_index_id）
      if (result.wp_index_id && customForm.value.fileList[0]?.raw) {
        const formData = new FormData()
        formData.append('file', customForm.value.fileList[0].raw)
        try {
          await http.post(
            `/api/projects/${projectId.value}/workpapers/${result.wp_index_id}/upload`,
            formData,
            { headers: { 'Content-Type': 'multipart/form-data' } },
          )
          ElMessage.success(`已创建自定义程序 ${result.wp_code} 并上传模板文件`)
        } catch {
          ElMessage.warning(`程序已创建（${result.wp_code}），但模板上传失败，可稍后在底稿列表中重新上传`)
        }
      } else {
        ElMessage.success(`已创建自定义程序 ${result.wp_code}`)
      }
    } else {
      // 不带文件：调用原接口
      const newProc = await addCustomProcedure(projectId.value, activeCycle.value, {
        procedure_name: name,
        procedure_code: customForm.value.code || undefined,
      })
      const addedRow = { ...newProc, _applicable: true, is_custom: true }
      procedures.value.push(addedRow)
      // 自定义程序已即时持久化 → 同步初始快照，避免 isDirty 误报
      originalSnapshot.push(JSON.parse(JSON.stringify(addedRow)))
      ElMessage.success('已添加自定义程序（无模板文件，可稍后在底稿列表中上传）')
    }
    showAddCustomDialog.value = false
  } catch (e: any) { handleApiError(e, '新增程序') }
}

// 删除自定义程序（调后端软删 + 清理 WpIndex，成功后再移除本地行）
async function removeCustom(row: any) {
  const doRemoveLocal = () => {
    const idx = procedures.value.indexOf(row)
    if (idx >= 0) procedures.value.splice(idx, 1)
    // 删除已即时持久化 → 同步移除初始快照条目，避免 isDirty 误报
    if (row?.id) {
      const si = originalSnapshot.findIndex((o: any) => o.id === row.id)
      if (si >= 0) originalSnapshot.splice(si, 1)
    }
  }
  // 未落库的临时行（无 id）直接移除
  if (!row?.id) {
    doRemoveLocal()
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除自定义程序「${row.procedure_name || row.procedure_code || ''}」？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await http.delete(
      `/api/projects/${projectId.value}/procedures/${activeCycle.value}/custom/${row.id}`,
    )
    doRemoveLocal()
    ElMessage.success('已删除自定义程序')
  } catch (e: any) {
    handleApiError(e, '删除自定义程序')
  }
}

// 加载项目团队成员（委派候选人）
async function loadTeamMembers() {
  try {
    const list = await listAssignments(projectId.value)
    const ROLE_LABELS: Record<string, string> = {
      partner: '合伙人', signing_partner: '签字合伙人', manager: '项目经理',
      auditor: '审计员', reviewer: '复核', eqcr: 'EQCR',
    }
    teamMembers.value = (Array.isArray(list) ? list : [])
      .filter((a: any) => a.staff_id)
      .map((a: any) => ({
        staff_id: a.staff_id,
        staff_name: a.staff_name || a.staff_id.slice(0, 8),
        role: a.role || '',
        role_label: ROLE_LABELS[a.role] || a.role || '',
      }))
  } catch {
    teamMembers.value = []
  }
}

// 委派执行人变更 → 立即持久化（P1-5：成功后短暂显示 ✓ 已存，消除"即时保存 vs 批量保存"困惑）
async function onAssigneeChange(row: any) {
  if (!row.id) return
  try {
    await assignProcedures(projectId.value, [{ procedure_id: row.id, staff_id: row.assigned_to }])
    const member = teamMembers.value.find(m => m.staff_id === row.assigned_to)
    ElMessage.success(row.assigned_to ? `已委派给 ${member?.staff_name || '执行人'}` : '已取消委派')
    // 瞬时反馈：行内 ✓ 已存，2.5s 后消失
    savedAssignees.value.add(row.id)
    savedAssignees.value = new Set(savedAssignees.value)
    setTimeout(() => {
      savedAssignees.value.delete(row.id)
      savedAssignees.value = new Set(savedAssignees.value)
    }, 2500)
  } catch (e: any) {
    handleApiError(e, '委派')
  }
}

// ── P1-3 / P0-1 全项目裁剪概览 ──
// 懒加载各循环程序（getProcedures 只读，不 init 避免对全部循环产生物化副作用；空循环标"未初始化"）
async function loadAllCyclesData() {
  // 并发拉取各循环（15 个循环顺序 await 慢网络下明显；Promise.all 并发）
  const results = await Promise.all(
    cycles.map(async (c) => {
      try {
        const procs = await getProcedures(projectId.value, c.code)
        return [c.code, Array.isArray(procs) && procs.length ? procs : null] as const
      } catch {
        return [c.code, null] as const
      }
    }),
  )
  allCyclesData.value = Object.fromEntries(results)
}

async function openOverview() {
  showOverviewDrawer.value = true
  if (Object.keys(allCyclesData.value).length > 0) return // 已加载过
  overviewLoading.value = true
  try {
    await loadAllCyclesData()
  } finally {
    overviewLoading.value = false
  }
}

// 概览行点击 → 切换到该循环（先过脏检查，程序化切换不经 el-tabs before-leave）
// focusFilter='trimmed' 时切换后自动定位到已裁剪项（点「缺理由」用，闭合发现→补填）
async function jumpToCycleFromOverview(code: string, focusFilter: '' | 'trimmed' = '') {
  const applyFilter = () => { statsFilter.value = focusFilter }
  if (code === activeCycle.value) {
    showOverviewDrawer.value = false
    applyFilter()
    return
  }
  if (isDirty.value) {
    try {
      await ElMessageBox.confirm(
        '当前循环有未保存的粗裁修改，切换将丢失。是否放弃并切换？',
        '未保存修改',
        { type: 'warning', confirmButtonText: '放弃并切换', cancelButtonText: '取消' },
      )
    } catch { return }
  }
  activeCycle.value = code
  showOverviewDrawer.value = false
  await loadProcedures()
  applyFilter()
}

// ── P1-6 导出裁剪方案（全循环 xlsx，供留痕/打印/复核签字）──
async function exportScheme() {
  exporting.value = true
  try {
    if (Object.keys(allCyclesData.value).length === 0) {
      await loadAllCyclesData()
    }
    const staffName = (id: string | null) =>
      id ? (teamMembers.value.find(m => m.staff_id === id)?.staff_name || id.slice(0, 8)) : ''
    const aoa: any[][] = [['循环', '编号', '程序名称', '适用性', '裁剪理由', '底稿主编', '来源']]
    for (const c of cycles) {
      const list = allCyclesData.value[c.code]
      if (!Array.isArray(list)) continue
      for (const p of list) {
        const applicable = p.status !== 'not_applicable' && p.status !== 'skip'
        aoa.push([
          c.label,
          p.procedure_code || p.wp_code || '',
          p.procedure_name || '',
          applicable ? '执行' : '裁剪',
          applicable ? '' : (p.skip_reason || ''),
          staffName(p.assigned_to || null),
          (p.is_custom || p.source === 'custom') ? '自定义' : '模板',
        ])
      }
    }
    if (aoa.length <= 1) {
      ElMessage.warning('暂无可导出的程序数据')
      return
    }
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const ws = XLSX.utils.aoa_to_sheet(aoa)
    ws['!cols'] = [{ wch: 12 }, { wch: 12 }, { wch: 40 }, { wch: 8 }, { wch: 32 }, { wch: 14 }, { wch: 8 }]
    XLSX.utils.book_append_sheet(wb, ws, '底稿粗裁方案')
    XLSX.writeFile(wb, `底稿粗裁方案_${projectId.value.slice(0, 8)}.xlsx`)
    ElMessage.success('裁剪方案已导出')
  } catch (e: any) {
    handleApiError(e, '导出裁剪方案')
  } finally {
    exporting.value = false
  }
}

// P2-4 关联底稿区间码（如「D2-6至D2-13」）展开为具体底稿清单供 tooltip；非区间码原样返回
function expandWpCodeTooltip(code: string): string {
  const m = String(code || '').match(/^(.*?)(\d+)\s*至\s*(?:(.+?))?(\d+)$/)
  if (!m) return code
  const prefix = m[1]
  const start = parseInt(m[2], 10)
  const end = parseInt(m[4], 10)
  // 仅当前缀一致（或省略）且区间合法（≤50 张防异常）时展开
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start || end - start > 50) return code
  const endPrefix = m[3]
  if (endPrefix && endPrefix !== prefix) return code
  const list: string[] = []
  for (let i = start; i <= end; i++) list.push(`${prefix}${i}`)
  return `含 ${list.length} 张底稿：${list.join('、')}`
}

// 工具栏「更多 ▾」命令分发（低频操作收敛，避免主栏拥挤）
function onToolbarCommand(cmd: string) {
  if (cmd === 'export') exportScheme()
  else if (cmd === 'ref') openRefDialog()
  else if (cmd === 'reset') resetAll()
}

// 进入该底稿的程序表控制台做逐条程序裁剪
function enterProgramConsole(row: any) {
  if (!row.wp_id) {
    ElMessage.warning('该程序底稿尚未生成，请先生成底稿')
    return
  }
  router.push({
    path: `/projects/${projectId.value}/workpapers/${row.wp_id}/edit`,
  })
}

// 智能裁剪
function onSmartTrim() {
  showSmartTrimDialog.value = true
}
async function confirmSmartTrim() {
  // 确定裁剪范围
  let targetCycles: Set<string>
  if (smartTrimScope.value === 'current') {
    targetCycles = new Set([activeCycle.value])
  } else if (smartTrimScope.value === 'custom') {
    if (smartTrimCycles.value.length === 0) {
      ElMessage.warning('请至少选择一个循环')
      return
    }
    targetCycles = new Set(smartTrimCycles.value)
  } else {
    // all — 除 A/S 外全部
    targetCycles = new Set(cycles.filter(c => c.code !== 'A' && c.code !== 'S').map(c => c.code))
  }

  // 核心判据：从试算表读取有数据（非零余额/已发生）的科目及其业务循环。
  // 只裁"该循环在试算表中完全无科目数据"的 D~N 程序，有数据的科目循环一律保留。
  let accounts: { name: string; amount: number; cycle: string }[] = []
  let scopeLoadFailed = false
  try {
    const resp: any = await http.get('/api/b50/scope-accounts', {
      params: { project_id: projectId.value, year: year.value },
    })
    const env = resp?.data
    const payload = env?.data ?? env
    accounts = Array.isArray(payload?.accounts) ? payload.accounts : []
  } catch {
    scopeLoadFailed = true
  }

  // 安全兜底：拿不到任何试算表科目（未导入/查询失败）时禁止裁剪，避免误把所有循环当"无数据"全裁光
  if (scopeLoadFailed || accounts.length === 0) {
    showSmartTrimDialog.value = false
    ElMessageBox.alert(
      scopeLoadFailed
        ? '未能读取试算表数据，无法按"科目有无数据"智能裁剪。请稍后重试或手动裁剪。'
        : '试算表暂无科目数据（可能尚未导入试算表）。智能裁剪依据科目余额判断，已取消本次裁剪，请先导入试算表或手动裁剪。',
      '无法智能裁剪',
      { type: 'warning', confirmButtonText: '知道了' },
    ).catch(() => {})
    return
  }

  // 有非零余额（含损益已发生额）的实质性循环集合
  const cyclesWithData = new Set<string>()
  for (const a of accounts) {
    const c = (a.cycle || '').toUpperCase()
    if (DATA_DRIVEN_CYCLES.has(c)) cyclesWithData.add(c)
  }

  // 科目底稿级数据可用性（registry 覆盖的 wp_code 前缀，如 D2/E1），比循环级更精确：
  // 同一循环内 D2(应收账款)有数据、D3(预收账款)无数据可分别判定；未覆盖的退回循环级
  const subjectWithData = new Set<string>()
  const subjectNoData = new Set<string>()
  try {
    const av: any = await http.get(
      `/api/projects/${projectId.value}/procedure-scope/data-availability`,
      { params: { year: year.value } },
    )
    const sp = av?.data?.data ?? av?.data ?? {}
    for (const w of (sp.subject_with_data || [])) subjectWithData.add(String(w).toUpperCase())
    for (const w of (sp.subject_no_data || [])) subjectNoData.add(String(w).toUpperCase())
  } catch { /* 科目级不可用时静默降级到循环级 */ }

  const protectedCycles = new Set(['A', 'S'])

  // 单个程序裁剪决策（纯函数，跨循环复用）。返回裁剪理由或 null（保留）。
  // scope 由调用方保证（当前循环 / 跨循环各自迭代），此处不再判 targetCycles。
  const decide = (p: any): string | null => {
    const cc = (p.procedure_code || p.wp_code || '').charAt(0).toUpperCase()
    const applicable = p._applicable !== undefined
      ? p._applicable
      : (p.status !== 'not_applicable' && p.status !== 'skip')
    if (!applicable) return null // 已裁剪
    if (p.is_mandatory) return null // 必须程序
    if (protectedCycles.has(cc)) return null // A/S 保护
    if (['in_progress', 'completed', 'reviewed'].includes(p.execution_status)) return null // 有进度
    if (p.skip_reason) return null // 已手动设置理由
    if (!DATA_DRIVEN_CYCLES.has(cc)) return null // B/C 非科目余额驱动 → 保留
    // 科目底稿级优先：registry 覆盖的科目按标准科目码判断（如 D2 无数据可裁而 D3 有数据保留）
    const prefix = (p.wp_code || p.procedure_code || '').toUpperCase().match(/^([A-Z]+\d+)/)?.[1] || ''
    if (subjectWithData.has(prefix)) return null // 该科目在试算表有数据 → 保留
    if (subjectNoData.has(prefix)) {
      return `智能裁剪：${prefix} 科目在试算表中无数据（无余额/未发生），如实际存在业务可手动恢复`
    }
    // registry 未覆盖该科目 → 退回业务循环级判断
    if (cyclesWithData.has(cc)) return null // 循环有数据 → 保留
    return `智能裁剪：${cc} 循环在试算表中无科目数据（无余额/未发生），如实际存在业务可手动恢复`
  }

  const scopeLabel = smartTrimScope.value === 'all' ? '全部循环' :
    smartTrimScope.value === 'current' ? `${activeCycle.value} 循环` :
    `${smartTrimCycles.value.join('/')} 循环`

  // ── 当前循环：内存应用，用户复核后点「保存粗裁」──
  if (smartTrimScope.value === 'current') {
    let trimCount = 0
    let keepCount = 0
    for (const p of procedures.value) {
      const reason = decide(p)
      if (reason) {
        p._applicable = false
        p.status = 'not_applicable'
        p.skip_reason = reason
        trimCount++
      } else if (p._applicable) {
        keepCount++
      }
    }
    showSmartTrimDialog.value = false
    if (trimCount > 0) {
      ElMessage.success(`[${scopeLabel}] 已裁剪 ${trimCount} 个"试算表无数据"科目的程序（保留 ${keepCount} 个），请检查后保存`)
    } else {
      ElMessage.info(`[${scopeLabel}] 无可裁剪程序：所涉科目在试算表中均有数据或均为必须/进行中`)
    }
    return
  }

  // ── 跨循环（全部 / 自定义）：真拉取每个目标循环 + 直接持久化 ──
  // 当前循环若有未保存修改，跨循环会重载覆盖，先要求处理
  if (isDirty.value) {
    try {
      await ElMessageBox.confirm(
        '当前循环有未保存的粗裁修改。跨循环智能裁剪会直接保存各循环并刷新当前循环，未保存修改将丢失。是否先保存当前循环再继续？',
        '未保存修改',
        { type: 'warning', confirmButtonText: '保存并继续', cancelButtonText: '取消' },
      )
      await saveTrim()
      if (isDirty.value) return // saveTrim 因缺理由被阻断
    } catch {
      return
    }
  }

  try {
    await ElMessageBox.confirm(
      `将对 ${targetCycles.size} 个循环执行智能裁剪并【直接保存】，结果立即生效。是否继续？`,
      '跨循环智能裁剪',
      { type: 'warning', confirmButtonText: '确认裁剪并保存', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  showSmartTrimDialog.value = false
  loading.value = true
  let totalTrim = 0
  let totalKeep = 0
  const failedCycles: string[] = []
  try {
    for (const cyc of targetCycles) {
      try {
        let procs = await getProcedures(projectId.value, cyc)
        if (!procs || procs.length === 0) {
          procs = await initProcedures(projectId.value, cyc)
        }
        const items = (procs || []).map((p: any) => {
          const reason = decide(p)
          if (reason) {
            totalTrim++
            return { id: p.id, status: 'not_applicable', skip_reason: reason }
          }
          const keepApplicable = p.status !== 'not_applicable' && p.status !== 'skip'
          if (keepApplicable) totalKeep++
          return { id: p.id, status: p.status || 'execute', skip_reason: p.skip_reason || '' }
        }).filter((it: any) => it.id)
        if (items.length > 0) {
          await updateProcedureTrim(projectId.value, cyc, items)
        }
      } catch {
        failedCycles.push(cyc)
      }
    }
  } finally {
    loading.value = false
  }

  await loadProcedures() // 刷新当前循环显示

  let msg = `[${scopeLabel}] 已智能裁剪并保存 ${totalTrim} 个"试算表无数据"科目程序（保留 ${totalKeep} 个）`
  if (failedCycles.length > 0) msg += `；${failedCycles.join('/')} 循环处理失败`
  if (totalTrim > 0) ElMessage.success(msg)
  else ElMessage.info(`[${scopeLabel}] 未发现可裁剪的程序${failedCycles.length ? `（${failedCycles.join('/')} 失败）` : ''}`)
}

// 参照其他项目
async function applyRef() {
  if (!refProjectId.value) return
  try {
    await applyProcedureScheme(projectId.value, activeCycle.value, refProjectId.value)
    ElMessage.success('已应用参照方案')
    showRefDialog.value = false
    await loadProcedures()
  } catch (e: any) { handleApiError(e, '应用参照') }
}

// ── 程序委派向导（V105 三粒度 cycle 委派：preview → apply，真实统计 + TTL/409） ──
const delegateWizard = ref<{
  visible: boolean; assigneeId: string; reviewerId: string; unassignedOnly: boolean;
  loading: boolean; jobStatus: string | null; preview: any | null; previewId: string;
  reqId: string; applyResult: any | null;
}>({
  visible: false, assigneeId: '', reviewerId: '', unassignedOnly: false,
  loading: false, jobStatus: null, preview: null, previewId: '', reqId: '', applyResult: null,
})

function jobStatusLabel(s: string): string {
  const m: Record<string, string> = { pending: '排队中', running: '进行中', succeeded: '成功', failed: '失败' }
  return m[s] || s
}

function openDelegateWizard() {
  delegateWizard.value = {
    visible: true, assigneeId: '', reviewerId: '', unassignedOnly: false,
    loading: false, jobStatus: null, preview: null, previewId: '', reqId: '', applyResult: null,
  }
}

function wizardBody() {
  return {
    selector: { kind: 'cycle' as const, cycle: activeCycle.value },
    assignee_staff_id: delegateWizard.value.assigneeId,
    reviewer_staff_id: delegateWizard.value.reviewerId || null,
    unassigned_only: delegateWizard.value.unassignedOnly,
  }
}

async function runDelegatePreview() {
  if (!delegateWizard.value.assigneeId) {
    ElMessage.warning('请选择程序执行人')
    return
  }
  // SOD 自审防护：程序执行人不得同时为操作复核人
  if (delegateWizard.value.reviewerId && delegateWizard.value.reviewerId === delegateWizard.value.assigneeId) {
    ElMessage.error('程序执行人与操作复核人不能为同一人（职责分离），请调整')
    return
  }
  delegateWizard.value.loading = true
  delegateWizard.value.applyResult = null
  try {
    const res = await previewProcedureDelegation(projectId.value, wizardBody())
    delegateWizard.value.preview = res
    delegateWizard.value.jobStatus = res?.materialize_job?.status ?? res?.job_status ?? null
    // 物化 job 未完成 → 不产生可消费 preview（需求 2.8）
    const status = res?.status
    if (status === 'materialization_pending') {
      ElMessage.info('部分程序尚未生成任务，已提交物化 job，请稍后重新预览')
      delegateWizard.value.previewId = ''
    } else {
      delegateWizard.value.previewId = res?.preview_id || res?.preview?.id || ''
      delegateWizard.value.reqId = newRequestId()
    }
  } catch (e: any) {
    handleApiError(e, '委派预览')
  } finally {
    delegateWizard.value.loading = false
  }
}

async function runDelegateApply() {
  if (!delegateWizard.value.previewId) return
  delegateWizard.value.loading = true
  try {
    const res = await applyProcedureDelegation(
      projectId.value, delegateWizard.value.previewId, delegateWizard.value.reqId, wizardBody(),
    )
    delegateWizard.value.applyResult = res
    const applied = res?.applied ?? res?.changed ?? 0
    ElMessage.success(`委派完成：已应用 ${applied} 项`)
    // 一次消费后作废 previewId
    delegateWizard.value.previewId = ''
    await loadProcedures()
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning('预览已失效（过期 / 一次消费 / 目标版本或成员变化），请重新预览')
      delegateWizard.value.previewId = ''
      delegateWizard.value.preview = null
    } else {
      handleApiError(e, '委派应用')
    }
  } finally {
    delegateWizard.value.loading = false
  }
}

// 循环 Tab 切换前脏检查（有未保存粗裁修改时确认）
async function onCycleBeforeLeave(_activeName: string, oldActiveName: string): Promise<boolean> {
  if (!oldActiveName || !isDirty.value) return true
  try {
    await ElMessageBox.confirm(
      '当前循环有未保存的粗裁修改（适用性 / 裁剪理由），切换循环将丢失。是否放弃修改并切换？',
      '未保存修改',
      { type: 'warning', confirmButtonText: '放弃并切换', cancelButtonText: '取消' },
    )
    return true
  } catch {
    return false // 用户取消 → 阻止切换
  }
}

// 路由离开守卫：有未保存修改时确认
onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  try {
    await ElMessageBox.confirm(
      '当前循环有未保存的粗裁修改，离开将丢失。是否放弃修改并离开？',
      '未保存修改',
      { type: 'warning', confirmButtonText: '放弃并离开', cancelButtonText: '留在本页' },
    )
    return true
  } catch {
    return false
  }
})

// 参照其他项目：弹窗打开时才懒加载项目列表（避免页面挂载即全量拉取）
const projectsLoaded = ref(false)
async function openRefDialog() {
  showRefDialog.value = true
  if (projectsLoaded.value) return
  try {
    const list = await listProjects()
    projectOptions.value = Array.isArray(list) ? list : []
    projectsLoaded.value = true
  } catch { /* 静默 */ }
}

onMounted(async () => {
  await loadProcedures()
  await loadTeamMembers()
})
</script>

<style scoped>
.gt-procedure { padding: 16px 20px; height: 100%; display: flex; flex-direction: column; }

/* 工具栏 */
.gt-proc-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.gt-proc-toolbar__left { display: flex; align-items: center; gap: 10px; }
.gt-proc-toolbar__title { margin: 0; font-size: 18px; font-weight: 700; color: var(--gt-color-text-primary); }
.gt-proc-toolbar__right { display: flex; gap: 8px; }

/* 统计卡片 */
.gt-proc-stats-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; color: var(--gt-color-text-tertiary); margin-bottom: 6px;
}
.gt-proc-stats {
  display: flex; gap: 12px; margin-bottom: 14px;
}
.gt-proc-stat-card {
  flex: 1; text-align: center; padding: 12px 8px;
  background: var(--gt-color-bg-white); border-radius: 10px;
  border: 2px solid var(--gt-color-border-light, #f0f0f0);
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
  cursor: pointer; transition: all 0.15s;
}
.gt-proc-stat-card:hover { border-color: var(--gt-color-primary); }
.gt-proc-stat-card.is-active {
  border-color: var(--gt-color-primary); background: var(--gt-color-primary-bg, #f0ebff);
  box-shadow: 0 0 0 3px rgba(103, 80, 164, 0.1);
}
.gt-proc-stat-card--progress { display: flex; align-items: center; justify-content: center; gap: 10px; }
.gt-proc-stat-card__num { font-size: 22px; font-weight: 800; color: var(--gt-color-text-primary); line-height: 1.2; }
.gt-proc-stat-card__label { font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 2px; }

/* 循环 Tab */
.gt-proc-cycle-bar {
  margin-bottom: 0; border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-proc-tabs { }
:deep(.gt-proc-tabs .el-tabs__header) { margin: 0; }
:deep(.gt-proc-tabs .el-tabs__nav-wrap::after) { display: none; }

/* 表格工具栏 */
.gt-proc-table-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; margin-bottom: 8px;
  background: var(--gt-color-bg, #fafafa); border-radius: 8px;
}
.gt-proc-table-toolbar__label { font-size: 13px; font-weight: 600; color: var(--gt-color-text-secondary); }
.gt-proc-table-toolbar__actions { display: flex; align-items: center; gap: 4px; }

/* 表格区 */
.gt-proc-table-wrap {
  flex: 1; min-height: 0; background: var(--gt-color-bg-white);
  border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.03);
  overflow: hidden;
}
/* 红框表格统一 13px（Element Plus 表头/单元格默认 14px，需显式覆盖） */
.gt-proc-table-wrap :deep(.el-table),
.gt-proc-table-wrap :deep(.el-table th.el-table__cell),
.gt-proc-table-wrap :deep(.el-table td.el-table__cell),
.gt-proc-table-wrap :deep(.el-table .cell) {
  font-size: 13px;
}
.gt-proc-text-muted { color: var(--gt-color-text-placeholder); font-size: 12px; }

/* 底稿主编单元格（select + 即时保存反馈） */
.gt-proc-assignee-cell { display: flex; align-items: center; gap: 4px; }
.gt-proc-saved-flag {
  font-size: 11px; color: var(--gt-color-success, #67c23a); white-space: nowrap;
  animation: gt-proc-fade 0.3s ease;
}
@keyframes gt-proc-fade { from { opacity: 0; } to { opacity: 1; } }

/* 概览抽屉合计 */
.gt-proc-overview-totals {
  margin-top: 12px; padding: 10px 14px; font-size: 13px;
  background: var(--gt-color-bg, #fafafa); border-radius: 8px;
  display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
}
.gt-proc-overview-totals > span:first-child { color: var(--gt-color-text-secondary); }

/* 关联底稿列：区间编码（如 D2-6至D2-13）单行显示，不换行 */
:deep(.gt-proc-wpcode-col .cell) {
  white-space: nowrap;
  font-size: 12px;
}

/* 底部提示 */
.gt-proc-footer-tip {
  margin-top: 12px; padding: 10px 14px; font-size: 12px;
  color: var(--gt-color-text-secondary); background: var(--gt-color-primary-bg, #f8f5ff);
  border-radius: 8px; border-left: 3px solid var(--gt-color-primary);
}

/* 智能裁剪规则列表 */
.gt-proc-smart-rules {
  padding-left: 20px; margin: 0; font-size: 13px; color: var(--gt-color-text-primary); line-height: 2;
}
.gt-proc-smart-scope {
  margin-top: 16px; padding: 12px 14px; background: var(--gt-color-bg, #fafafa);
  border-radius: 8px; border: 1px solid var(--gt-color-border-light, #f0f0f0);
}
.gt-proc-smart-scope__title { font-size: 13px; font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 8px; }
.gt-proc-smart-scope__cycles { margin-top: 8px; padding: 8px 12px; background: var(--gt-color-bg-white); border-radius: 6px; }

/* 角色术语说明 */
.gt-proc-role-legend { margin-bottom: 12px; }

/* 裁剪操作指南折叠区 */
.gt-proc-guide-details {
  margin-bottom: 12px;
  border: 1px solid #e8d5f5;
  border-radius: 8px;
  background: #fdf8ff;
}
.gt-proc-guide-details summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: #4b2d77;
}
.gt-proc-guide-details[open] summary {
  border-bottom: 1px solid #e8d5f5;
}
.gt-proc-guide-content {
  padding: 10px 16px;
  font-size: 12px;
  line-height: 1.6;
  color: #303133;
}
.gt-proc-guide-content ol,
.gt-proc-guide-content ul {
  padding-left: 1.5em;
  margin: 4px 0;
}
.gt-proc-guide-content li { margin: 3px 0; }

/* 委派向导 */
.gt-proc-wizard-job { margin: 10px 0; }
.gt-proc-wizard-preview { margin-top: 12px; }
.gt-proc-wizard-result { margin-top: 12px; }
.gt-proc-wizard-tip { margin-top: 8px; font-size: 12px; color: var(--gt-color-warning, #e6a23c); }

/* 自定义模板上传区 */
.gt-proc-custom-template-area {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.gt-proc-custom-template-or {
  font-size: 12px; color: var(--gt-color-text-tertiary); font-style: italic;
}
</style>
