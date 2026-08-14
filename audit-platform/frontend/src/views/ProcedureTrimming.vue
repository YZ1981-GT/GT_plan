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
        <!-- 复核视图对所有角色开放：它只读，且复核恰恰应由不执行裁剪的人做（R12.6） -->
        <el-button size="small" @click="openTrimReview">🔍 裁剪充分性复核</el-button>
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

    <!--
      B50 认定层次风险评估填写状态（spec procedure-trimming-and-delegation-intelligence Task 4）

      为什么要在裁剪页显示它：裁剪的风险维度判据（max_risk / has_special）唯一来源是
      B50 认定层次矩阵。若不区分「B50 未填」与「B50 已填且风险为低」，就会把「未评估」
      当成「低风险」处理 —— 那正是本 spec 要消除的错误。徽标让审计师在裁剪之前就看到
      风险维度是否可用。

      🔴 徽标取值与 B50 面板**同一个纯函数**（resolveB50Completeness），禁在此另算一份。
    -->
    <!-- 🔴 未知态（尚未加载 / 读取失败）下 b50Completeness 为 null —— 模板里每一处
         取 .state 都必须在 b50Loaded 分支内。改造前外层 :class 与跳转按钮的 v-if
         无守卫直接读 .state，而 onMounted 里 loadB50Status() 未 await ⇒ 首帧必为 null
         ⇒ 整个裁剪页渲染失败（TypeError: reading 'state'）。 -->
    <div class="gt-proc-b50-bar" :class="b50Loaded ? `is-${b50Completeness!.state}` : 'is-unknown'">
      <el-tooltip placement="bottom-start">
        <template #content>
          <div style="max-width: 380px; line-height: 1.7">
            <strong>程序裁剪的风险维度依赖 B50 认定层次风险矩阵。</strong><br />
            <template v-if="b50Loaded">{{ B50_COMPLETENESS_HINT[b50Completeness!.state] }}<br /></template>
            未评估的科目在裁剪时不会被当作低风险 —— 系统会如实标注「风险维度不可用」
            并降级为仅按数据存在性与重要性判断。
          </div>
        </template>
        <el-tag
          v-if="b50Loaded"
          :type="B50_COMPLETENESS_TAG_TYPE[b50Completeness!.state]"
          size="small"
          effect="dark"
        >
          B50 风险评估：{{ B50_COMPLETENESS_LABEL[b50Completeness!.state] }}
        </el-tag>
        <el-tag v-else type="info" size="small" effect="plain">B50 风险评估：状态未知</el-tag>
      </el-tooltip>
      <span v-if="b50Loaded" class="gt-proc-b50-counts">
        已导入 <strong>{{ b50Completeness!.importedCount }}</strong> 个科目 ·
        已评估 <strong>{{ b50Completeness!.assessedCount }}</strong> 个
      </span>
      <span v-else class="gt-proc-b50-counts gt-proc-b50-unknown">状态未知（读取失败或尚未加载）</span>
      <el-button
        v-if="!b50Loaded || b50Completeness!.state !== 'completed'"
        size="small"
        type="primary"
        link
        @click="goToB50"
      >
        前往 B50-3 填写 →
      </el-button>
    </div>

    <!--
      完整性敏感清单状态条（spec procedure-trimming-and-delegation-intelligence Task 14 / R5.6）

      为什么要在裁剪页显眼位置显示它：「金额低于实际执行重要性」这条裁剪建议判据，对
      完整性风险高的循环必须失效。失效范围在项目组未逐循环确认时取**平台默认清单**，
      而"平台按行业经验给的默认值"与"本项目组确认过的判断"在复核时的证明力完全不同 ——
      故未确认的循环必须如实标注，让质控与项目质量控制复核人一眼看出哪些判断没人签过字。

      🔴 标注开关取 `usingPlatformDefault`（`resolveCompletenessExemption` 的输出），
         不在此另判「覆盖表是否为空」。读取失败时显示"状态未知"而非"全部平台默认"。
    -->
    <div
      class="gt-proc-cscope-bar"
      :class="completenessDefaultNotice ? 'is-default' : (completenessOverrides === null ? 'is-unknown' : 'is-confirmed')"
    >
      <el-tooltip placement="bottom-start">
        <template #content>
          <div style="max-width: 420px; line-height: 1.7">
            <strong>完整性敏感的循环不适用「金额低于重要性」这条裁剪建议。</strong><br />
            少记负债 / 少记费用 / 跨期少记收入本身就会压低账面金额，用金额豁免完整性风险
            等于用症状豁免病因。<br />
            判据两级：优先读 B50 该科目的<strong>完整性认定</strong>；认定未填时退回
            <strong>循环级清单</strong>（平台默认 + 项目组可逐循环覆盖，覆盖须填理由并留痕）。
          </div>
        </template>
        <el-tag
          :type="completenessOverrides === null ? 'info' : (completenessDefaultNotice ? 'warning' : 'success')"
          size="small"
          effect="dark"
        >完整性敏感清单</el-tag>
      </el-tooltip>
      <span v-if="completenessOverrides === null" class="gt-proc-cscope-unknown">
        状态未知（{{ completenessError || '尚未加载' }}）—— 未据此标注平台默认项
      </span>
      <span v-else-if="completenessDefaultNotice" class="gt-proc-cscope-notice">
        {{ completenessDefaultNotice.text }}
      </span>
      <span v-else class="gt-proc-cscope-ok">
        本项目已逐循环确认完整性敏感范围（无使用平台默认的循环）
      </span>
      <el-button size="small" type="primary" link @click="openCompletenessPanel">
        逐循环设置 →
      </el-button>
      <!--
        附注反向联动入口（Task 21 / R13.1）。裁剪保存后会自动弹一次，此处提供**随时可开**
        的入口 —— 否则审计师只能在保存那一刻看到一次，事后想复核「哪些附注章节被标了
        不适用」就无路可走。
      -->
      <el-button
        size="small"
        type="primary"
        link
        :loading="noteLinkageLoading"
        @click="openNoteLinkagePanel"
      >附注联动{{ noteLinkageActionable > 0 ? `（${noteLinkageActionable}）` : '' }} →</el-button>
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

    <!-- 降级标注（R4.1 / R4.2 / R4.5，spec Task 22 修）─────────────────────────
         🔴 本块必须是**独立宿主**，不得嵌在建议态条内。
         改造前它嵌在 `v-if="suggestionStats.suggested > 0"` 里面，而「未做重要性
         联动」这条标注存在的前提恰恰是重要性维度不可用 ⇒ 该维度不产生任何建议
         ⇒ `suggested === 0` ⇒ 宿主整块不渲染 ⇒ **该标注在它唯一该出现的场景下
         永远不显示**（自相矛盾的门控：条件与内容互斥）。表现为「平台安静地跳过了
         一个法定判据维度而不告知」，这正是 R4.5 要禁的「假装做了联动」。
         风险维度那条同理：它此前只在「风险缺失但重要性可用、且恰好有建议」时才
         偶然可见。故一律独立成块，只由 `degradationNotes.length` 门控。 -->
    <div v-if="degradationNotes.length > 0" class="gt-proc-degrade-bar">
      <span class="gt-proc-degrade-bar__label">本次裁剪判据的维度可用性：</span>
      <el-tag
        v-for="d in degradationNotes"
        :key="d.dimension"
        type="warning"
        size="small"
        effect="plain"
      >
        {{ d.text }}
      </el-tag>
    </div>

    <!-- 建议态条（spec procedure-trimming-and-delegation-intelligence Task 13）──────────
         「建议裁剪」与「已裁剪」是两种状态：建议态**不改适用性**，等审计师确认。
         批量确认前过汇总闸 —— 若干各自低于实际执行重要性的科目，汇总错报可能超过
         可容忍水平，故 blocked 时只允许逐条确认。 -->
    <div v-if="suggestionStats.suggested > 0" class="gt-proc-suggest-bar" :class="{ 'is-blocked': aggregateGate.blocked }">
      <div class="gt-proc-suggest-bar__head">
        <el-tag :type="aggregateGate.blocked ? 'danger' : 'warning'" size="small" effect="dark">
          建议裁剪 {{ suggestionStats.suggested }} 项（待确认）
        </el-tag>
        <span class="gt-proc-suggest-bar__stat">
          已确认 <strong>{{ suggestionStats.confirmed }}</strong> ·
          已驳回 <strong>{{ suggestionStats.rejected }}</strong>
        </span>
        <template v-if="canManage">
          <el-button
            size="small"
            type="warning"
            :disabled="aggregateGate.blocked"
            :title="aggregateGate.blocked ? '汇总金额已达实际执行重要性，请逐条确认' : ''"
            @click="confirmAllSuggestions"
          >批量确认全部建议</el-button>
        </template>
      </div>
      <div class="gt-proc-suggest-bar__gate">{{ aggregateGate.narrative }}</div>
      <!-- 降级标注**不在此处** —— 见本文件上方 `.gt-proc-degrade-bar` 独立宿主。
           嵌回来会重新引入「条件与内容互斥」的门控（Task 22 定性并修复）。 -->
    </div>

    <!-- 表格工具栏 -->
    <div class="gt-proc-table-toolbar">
      <span class="gt-proc-table-toolbar__label">{{ activeCycle }} 循环 · {{ filteredProcedures.length }} 个程序</span>
      <div class="gt-proc-table-toolbar__actions">
        <!-- 复核视图跳转过来的定位提示（Task 20 / R12.5）：明示当前是被过滤到单条的状态，
             否则复核者会以为该循环只剩一个程序 -->
        <el-tag
          v-if="locatedWpCode"
          size="small"
          type="warning"
          closable
          @close="locatedWpCode = null; searchText = ''"
        >已定位 {{ locatedWpCode }}（点 × 取消定位）</el-tag>
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
        :row-class-name="procedureRowClass"
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
        <!-- 建议态列（Task 13）：视觉上与「已裁剪」区分 —— 建议是未落地的判断，
             必须显示判据数值让审计师能自行复核，不能只给一个结论词。 -->
        <el-table-column label="裁剪建议" min-width="200" resizable>
          <template #default="{ row }">
            <div v-if="suggestionOf(row)" class="gt-proc-suggest-cell">
              <el-tooltip :content="suggestionOf(row)!.narrative" placement="top">
                <el-tag type="warning" size="small" effect="plain">
                  {{ reasonCodeLabel(suggestionOf(row)!.reasonCode) || '建议裁剪' }}
                </el-tag>
              </el-tooltip>
              <template v-if="canManage">
                <el-button size="small" type="warning" text @click="confirmSuggestion(row)">确认</el-button>
                <el-button size="small" text @click="rejectSuggestion(row)">驳回</el-button>
              </template>
            </div>
            <el-tooltip
              v-else-if="row.suggestion_state?.rejected"
              content="审计师已驳回系统建议，不再重复提示"
              placement="top"
            >
              <el-tag type="info" size="small" effect="plain">已驳回建议</el-tag>
            </el-tooltip>
            <span v-else-if="!row._applicable && row.suggestion_state?.reason_code">
              <el-tag type="success" size="small" effect="plain">
                {{ reasonCodeLabel(row.suggestion_state.reason_code) }}
              </el-tag>
            </span>
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

      <!-- 服务端预览统计（计数取嵌套 summary 的真实键；读不到显示「—」不猜别的字段名） -->
      <div v-if="delegateWizard.preview" class="gt-proc-wizard-preview">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="目标数">{{ previewSummary?.targets ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="将新分配">{{ previewSummary?.would_assign ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="将转派">{{ previewSummary?.would_reassign ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="冲突数">{{ previewSummary?.conflict ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="已分配">{{ previewSummary?.already_assigned ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="无需变更">{{ previewSummary?.unchanged ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="预览状态">{{ delegateWizard.preview.status || 'ready' }}</el-descriptions-item>
          <el-descriptions-item label="执行人当前负载">
            <span v-if="previewAssigneeLoad !== null">在办 {{ previewAssigneeLoad }} 项</span>
            <span v-else class="gt-proc-load-unknown">负载未知</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="delegateWizard.preview.expires_at" label="预览有效期至" :span="2">{{ delegateWizard.preview.expires_at }}</el-descriptions-item>
        </el-descriptions>

        <!-- 受影响底稿清单（后端已下发，改造前完全未展示 = 审计师盲选） -->
        <div v-if="affectedWorkpapers.count > 0" class="gt-proc-wizard-affected">
          <el-collapse>
            <el-collapse-item :title="`受影响底稿（${affectedWorkpapers.count} 张）`" name="aff">
              <div v-if="affectedWorkpapers.codes.length" class="gt-proc-affected-tags">
                <el-tag v-for="c in affectedWorkpapers.codes" :key="c" size="small" type="info">{{ c }}</el-tag>
              </div>
              <div v-else class="gt-proc-wizard-tip">
                共 {{ affectedWorkpapers.count }} 张（编号待解析：本次目标含当前循环之外的底稿）
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

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
        <!-- 智能建议分配入口（Task 18）：加法式并存，不替换左侧单执行人整循环流程 -->
        <el-button type="warning" plain @click="openSuggestionPanel">🤖 智能建议分配</el-button>
        <el-button @click="delegateWizard.visible = false">关闭</el-button>
        <el-button v-if="!delegateWizard.previewId" type="primary" :loading="delegateWizard.loading" @click="runDelegatePreview">预览</el-button>
        <el-button v-else type="primary" :loading="delegateWizard.loading" @click="runDelegateApply">确认委派</el-button>
      </template>
    </el-dialog>

    <!-- 智能建议分配（Task 18）：底稿粒度建议表，与上方「单执行人整循环」流程并存而非替换 -->
    <el-dialog
      append-to-body
      v-model="suggestPanel.visible"
      title="智能建议分配（底稿粒度）"
      width="1080px"
      top="6vh"
    >
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        <template #title>
          <span style="font-size:12px">
            按<strong>底稿粒度</strong>给出建议：风险等级越高优先分配资历越高的成员，同时按
            <strong>加权负载</strong>均衡（权重 = 1 + 风险系数 + 行数/20）。建议<strong>仅供参考</strong>，
            每行的执行人/复核人可改、可移除；下方「为何这样分」写明了每行的判据数值。
            点「应用建议分配」后<strong>按执行人分组</strong>逐组走既有委派「预览 → 应用」两阶段，
            每组独立提交、独立幂等，<strong>某组失败不影响其他组</strong>。
          </span>
        </template>
      </el-alert>

      <!-- 🔴 取数失败必须与「算法未产出建议」区分显示：前者是缺陷（要重试/报修），
           后者可能是正常结论（如本循环无底稿）。两者都显示空表会让缺陷被静默吞掉。 -->
      <el-alert
        v-if="suggestPanel.error"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom:12px"
        title="建议分配取数失败"
        :description="suggestPanel.error + '（未生成任何建议；请重试或联系管理员，不要据空表判断本循环无需委派）'"
      />

      <div v-loading="suggestPanel.loading">
        <GtDelegationSuggestionTable
          v-if="suggestPanel.result"
          :suggestion="suggestPanel.result"
          :members="suggestionMembers"
          @change="onSuggestionRowsChange"
          @apply="onSuggestionApplyRequest"
        />
        <el-empty
          v-else-if="!suggestPanel.loading && !suggestPanel.error"
          description="尚未生成建议，点击下方「生成建议」"
        />
      </div>

      <!--
        逐组应用结果（Task 19 / R11.7）—— `suggestApply` / `suggestApplyTotals` /
        `suggestApplyStatusLabel` / `suggestApplyStatusTagType` / `retrySuggestionGroup`
        的**唯一渲染宿主**。

        🔴 缺了它，脚本侧那套状态机就是「声明而无消费方」的死代码：点「应用建议分配」
           会真的发请求，但审计师看不到哪组成功、哪组要重预览 —— 于是只能整体重做，
           把已成功的组重复委派一遍。Volar / vitest / get_diagnostics / HEAD-swap
           对这种缺失四层全绿（Task 14 已在本文件踩过一次）。
      -->
      <div v-if="suggestApply.groups.length" class="gt-proc-sugapply">
        <div class="gt-proc-sugapply__title">
          逐组应用结果
          <el-tag size="small" type="info" effect="plain">
            共 {{ suggestApplyTotals.total }} 组 · 成功 {{ suggestApplyTotals.applied }} ·
            需重新预览 {{ suggestApplyTotals.retryable }} ·
            无目标 {{ suggestApplyTotals.noTarget }} ·
            受阻 {{ suggestApplyTotals.blocked }} · 共应用 {{ suggestApplyTotals.rows }} 项
          </el-tag>
        </div>

        <el-alert
          v-if="suggestApplyTotals.retryable > 0"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom:8px"
          title="部分组的预览已失效，需单独重新预览"
        >
          <template #default>
            <span style="font-size:12px">
              失效组<strong>零写入</strong>（后端在任何写入前判定并回滚），
              <strong>已成功的组不受影响、无需重做</strong> —— 请只对下表中标为
              「需重新预览」的组点「重新应用」，不要整体重来（那会对已成功组重复委派）。
            </span>
          </template>
        </el-alert>

        <el-table :data="suggestApply.groups" size="small" style="font-size:12px">
          <el-table-column label="程序执行人" min-width="120">
            <template #default="{ row }">{{ row.assigneeName }}</template>
          </el-table-column>
          <el-table-column label="底稿" min-width="150">
            <template #default="{ row }">
              <span>{{ row.wpIndexIds.length }} 张</span>
              <span v-if="row.wpCodes.length" style="color:var(--gt-color-text-secondary)">
                （{{ row.wpCodes.join('、') }}）
              </span>
            </template>
          </el-table-column>
          <el-table-column label="目标任务" width="90" align="right">
            <template #default="{ row }">
              {{ row.targets === null ? '—' : row.targets }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-tag size="small" :type="suggestApplyStatusTagType(row.status)">
                {{ suggestApplyStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="已应用 / 未变更 / 冲突" width="160" align="right">
            <template #default="{ row }">
              {{ row.applied }} / {{ row.unchanged }} / {{ row.conflict }}
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="260">
            <template #default="{ row }">
              <span style="font-size:12px; line-height:1.6">{{ row.message || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110" align="center">
            <template #default="{ row, $index }">
              <el-button
                v-if="row.status !== 'applied' && row.status !== 'pending'"
                size="small"
                link
                type="primary"
                :disabled="suggestApply.running"
                @click="retrySuggestionGroup($index)"
              >重新应用</el-button>
              <span v-else style="color:var(--gt-color-text-secondary)">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="suggestPanel.visible = false">关闭</el-button>
        <el-button type="primary" :loading="suggestPanel.loading" @click="openSuggestionPanel">
          {{ suggestPanel.result ? '重新生成建议' : '生成建议' }}
        </el-button>
      </template>
    </el-dialog>

    <!--
      完整性敏感清单逐循环覆盖面板（spec procedure-trimming-and-delegation-intelligence Task 14 / R5.5~R5.7）

      🔴 这是 `completenessPanelVisible` / `completenessScopeRows` / `setCompletenessScope` /
         `revertCompletenessScope` / `completenessSourceLabel` / `completenessSaving` 的**唯一渲染宿主**。
         缺了它，上面那颗「逐循环设置 →」按钮只会把一个没人读的 ref 置真 —— 脚本侧全部就绪、
         四层检查（Volar / vitest / get_diagnostics / HEAD-swap）全绿，而功能完全不存在。
         守卫 `completenessScopeOverride.spec.ts` 有一条按「脚本声明的每个标识符都要有模板消费方」
         钉死本宿主，防后续会话重构时再次把它整段删掉。
    -->
    <el-dialog
      append-to-body
      v-model="completenessPanelVisible"
      title="完整性敏感清单（逐循环项目级覆盖）"
      width="960px"
      top="6vh"
    >
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        <template #title>
          <span style="font-size:12px; line-height:1.8">
            <strong>为什么完整性敏感的循环不能用金额裁：</strong>少记负债 / 少记费用 / 跨期少记收入
            本身就会压低账面金额，用「余额低于实际执行重要性」去豁免完整性风险，等于用症状豁免病因。<br />
            <strong>判据两级：</strong>优先读 B50 该科目的<strong>完整性认定</strong>；认定未填时才退回本表的
            <strong>循环级清单</strong>。故本表管的是「认定缺失时的兜底口径」，不覆盖已填认定的科目。<br />
            <strong>覆盖须填理由</strong>并留痕操作人与时间 —— 平台默认值是按行业经验给的，
            与项目组确认过的判断在复核时证明力不同；未确认的循环会在裁剪页如实标注。
          </span>
        </template>
      </el-alert>

      <!-- 🔴 未知态（读取失败）必须与「一条都没覆盖过」区分：后者是本项目没做这个判断，
           前者是平台不知道本项目做没做。两者都显示成"全部平台默认"会把技术故障说成实质结论。 -->
      <el-alert
        v-if="completenessOverrides === null"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom:12px"
        title="覆盖清单读取失败，下表仅显示平台默认值"
        :description="(completenessError || '尚未加载') + '（此时未据此标注平台默认项；请重试后再作判断，不要按空表认为本项目一条都没确认过）'"
      >
        <template #default>
          <div style="margin-top:6px">
            <el-button size="small" @click="loadCompletenessOverrides">重新加载</el-button>
          </div>
        </template>
      </el-alert>

      <el-table :data="completenessScopeRows" size="small" border style="font-size:13px">
        <el-table-column prop="label" label="循环" min-width="130" />
        <el-table-column label="平台默认" width="92" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.platformDefault ? 'warning' : 'info'" effect="plain">
              {{ row.platformDefault ? '敏感' : '不敏感' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="当前生效" width="92" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.sensitive ? 'warning' : 'success'" effect="dark">
              {{ row.sensitive ? '敏感' : '不敏感' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="判据来源" min-width="160">
          <template #default="{ row }">
            <span :class="row.usingPlatformDefault ? 'gt-proc-cscope-notice' : 'gt-proc-cscope-ok'">
              {{ completenessSourceLabel(row) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="平台默认依据 / 覆盖理由" min-width="300">
          <template #default="{ row }">
            <div v-if="row.reason" class="gt-proc-cscope-reason">
              <strong>覆盖理由：</strong>{{ row.reason }}
            </div>
            <div class="gt-proc-cscope-rationale">{{ row.rationale }}</div>
          </template>
        </el-table-column>
        <el-table-column label="最后修改" min-width="170">
          <template #default="{ row }">
            <span v-if="row.updatedByName || row.updatedAt" class="gt-proc-cscope-trace">
              {{ row.updatedByName || '（用户已删）' }}
              <br />{{ row.updatedAt ? new Date(row.updatedAt).toLocaleString('zh-CN') : '—' }}
            </span>
            <span v-else class="gt-proc-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" align="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="!canManage || (row.sensitive && !row.usingPlatformDefault)"
              :loading="completenessSaving === row.cycle"
              @click="setCompletenessScope(row, true)"
            >设为敏感</el-button>
            <el-button
              size="small"
              plain
              :disabled="!canManage || (!row.sensitive && !row.usingPlatformDefault)"
              :loading="completenessSaving === row.cycle"
              @click="setCompletenessScope(row, false)"
            >设为不敏感</el-button>
            <el-button
              size="small"
              type="danger"
              link
              :disabled="!canManage || row.usingPlatformDefault"
              :loading="completenessSaving === row.cycle"
              @click="revertCompletenessScope(row)"
            >撤销</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="gt-proc-cscope-foot">
        <span v-if="completenessDefaultNotice">
          {{ completenessDefaultNotice.cycles.length }} 个循环仍取平台默认（{{ completenessDefaultNotice.cycles.join(' / ') }}）
        </span>
        <span v-else-if="completenessOverrides !== null">本项目已逐循环确认，无使用平台默认的循环</span>
        <span v-else>覆盖状态未知，未统计平台默认项</span>
      </div>

      <template #footer>
        <el-button @click="completenessPanelVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!--
      附注反向联动面板（spec procedure-trimming-and-delegation-intelligence Task 21 / R13.1~R13.4、R13.6）

      🔴 这是 `noteLinkagePanelVisible` / `noteLinkage` / `noteLinkageError` /
         `noteLinkageLoading` / `noteLinkageApplying` / `noteLinkageActionable` /
         `applyNoteLinkage` / `loadNoteLinkage` / `noteLinkageBuckets` 的**唯一渲染宿主**。
         缺了它，裁剪保存后那次 `loadNoteLinkage()` 只会把数据塞进没人读的 ref ——
         脚本侧全部就绪、四层检查（Volar / vitest / get_diagnostics / HEAD-swap）全绿，
         而功能完全不存在（Task 14 已在本文件踩过一次同款）。
    -->
    <el-dialog
      append-to-body
      v-model="noteLinkagePanelVisible"
      title="附注章节联动（本期不适用）"
      width="920px"
      top="6vh"
    >
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        <template #title>
          <span style="font-size:12px">
            某科目循环的程序被<b>整体裁剪</b>后，其对应附注章节可标注为「本期不适用」，避免交付件出现空白披露。
            标注<b>只改呈现</b>（写 <code>is_empty</code>），<b>不删除</b>章节或模板结构，裁剪恢复后自动撤销。
            已有录入内容的章节<b>只提示不自动标注</b>，也不自动撤销 —— 请在附注模块自行决定。
          </span>
        </template>
      </el-alert>

      <el-alert
        v-if="noteLinkageError"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom:12px"
      >
        <template #title>
          <span style="font-size:12px">
            附注联动状态未知：{{ noteLinkageError }}。<b>这不等于「没有需要标注的章节」</b>，请重试后再判断。
          </span>
        </template>
        <el-button size="small" link type="primary" :loading="noteLinkageLoading" @click="loadNoteLinkage()">
          重新加载
        </el-button>
      </el-alert>

      <div v-loading="noteLinkageLoading">
        <div v-if="noteLinkage" class="gt-proc-nlink">
          <div class="gt-proc-nlink__bar">
            <span>已整体裁剪循环：<b>{{ noteLinkage.cycles_fully_trimmed.join('、') || '—' }}</b></span>
            <span>将标注 <b>{{ noteLinkage.summary.to_mark }}</b> 节</span>
            <span>将撤销 <b>{{ noteLinkage.summary.to_revoke }}</b> 节</span>
            <span>已是该状态 <b>{{ noteLinkage.summary.already_marked }}</b> 节</span>
          </div>

          <div v-for="b in noteLinkageBuckets" :key="b.key" v-show="b.items.length > 0" class="gt-proc-nlink__group">
            <div class="gt-proc-nlink__title">
              <el-tag size="small" :type="b.tag" effect="plain">{{ b.label }}</el-tag>
              <span class="gt-proc-nlink__hint">{{ b.hint }}</span>
            </div>
            <el-table :data="b.items" size="small" border style="font-size:13px">
              <el-table-column prop="note_section" label="附注章节" width="110" />
              <el-table-column label="章节标题" min-width="180">
                <template #default="{ row }">{{ row.section_title || '—' }}</template>
              </el-table-column>
              <el-table-column label="对应底稿" width="140">
                <template #default="{ row }">{{ (row.owners || []).join('、') || '—' }}</template>
              </el-table-column>
              <el-table-column label="判据" min-width="240">
                <template #default="{ row }">
                  <span class="gt-proc-nlink__why">{{ row.narrative }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <el-alert
            v-if="noteLinkage.degradations.length > 0"
            type="warning"
            :closable="false"
            show-icon
            style="margin-top:10px"
          >
            <template #title>
              <span style="font-size:12px">
                本次联动有降级：{{ noteLinkage.degradations.map(d => `${d.stage}（${d.reason}）`).join('；') }}
              </span>
            </template>
          </el-alert>

          <el-empty
            v-if="noteLinkageActionable === 0 && noteLinkage.degradations.length === 0"
            description="没有需要变更的附注章节"
            :image-size="60"
          />
        </div>
      </div>

      <template #footer>
        <el-button @click="noteLinkagePanelVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :disabled="!canManage || !noteLinkage || (noteLinkage.summary.to_mark + noteLinkage.summary.to_revoke) === 0"
          :loading="noteLinkageApplying"
          @click="applyNoteLinkage()"
        >应用到附注</el-button>
      </template>
    </el-dialog>

    <!-- 全项目裁剪概览抽屉（P1-3 / P0-1：各循环 保留/裁剪/缺理由 一览，点击跳转对应循环） -->
    <el-drawer v-model="showOverviewDrawer" title="全项目裁剪概览" size="720px" append-to-body>
      <div v-loading="overviewLoading">
        <el-alert type="info" :closable="false" style="margin-bottom:12px">
          <template #title>
            <span style="font-size:12px">按各审计循环汇总裁剪进度；「缺理由」= 已裁剪但未填裁剪理由（保存会被阻断，需补填）。点击行跳转对应循环。「建议已确认」= 按系统建议落不适用；「建议已驳回」= 人工驳回建议、程序保留并留痕。</span>
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
          <el-table-column label="建议已确认" width="90" align="center">
            <template #default="{ row }">
              <span v-if="row.uninitialized" class="gt-proc-text-muted">—</span>
              <span v-else :style="row.suggestConfirmed > 0 ? 'color: var(--gt-color-primary)' : ''">{{ row.suggestConfirmed }}</span>
            </template>
          </el-table-column>
          <el-table-column label="建议已驳回" width="90" align="center">
            <template #default="{ row }">
              <span v-if="row.uninitialized" class="gt-proc-text-muted">—</span>
              <span v-else :style="row.suggestRejected > 0 ? 'color: var(--el-color-warning)' : ''">{{ row.suggestRejected }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-proc-overview-totals">
          <span>合计（已初始化循环）：</span>
          <span>总 <strong>{{ overviewTotals.total }}</strong></span>
          <span>保留 <strong style="color: var(--gt-color-primary)">{{ overviewTotals.execute }}</strong></span>
          <span>裁剪 <strong style="color: var(--gt-color-coral)">{{ overviewTotals.trimmed }}</strong></span>
          <span v-if="overviewTotals.missingReason > 0">缺理由 <strong style="color: var(--el-color-danger)">{{ overviewTotals.missingReason }}</strong></span>
          <span v-if="overviewTotals.suggestConfirmed > 0">建议已确认 <strong style="color: var(--gt-color-primary)">{{ overviewTotals.suggestConfirmed }}</strong></span>
          <span v-if="overviewTotals.suggestRejected > 0">建议已驳回 <strong style="color: var(--el-color-warning)">{{ overviewTotals.suggestRejected }}</strong></span>
        </div>
        <div style="margin-top:12px; text-align:right">
          <el-button size="small" @click="exportScheme" :loading="exporting">📤 导出方案</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 裁剪充分性复核视图（Task 20 / R12.1~R12.7）─────────────────────────────
         🔴 只读抽屉：内部组件零 IO、零写入调用；定位经 `locate` 事件回到本页执行。
         🔴 `review` 由 `buildTrimAdequacyReview` 派生，与本页 `aggregateGate` 共用
            同一批建议项与同一个阈值来源 ⇒ 两处统计逐项相等。 -->
    <el-drawer v-model="showReviewDrawer" title="裁剪充分性复核（只读）" size="960px" append-to-body>
      <GtTrimAdequacyReview
        :review="trimAdequacyReview"
        :loading="reviewLoading"
        @locate="onReviewLocate"
        @jump-cycle="onReviewJumpCycle"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  getProcedures, initProcedures,
  addCustomProcedure, listProjects,
  assignProcedures,
  previewProcedureDelegation, applyProcedureDelegation,
  fetchDelegationMemberLoads, fetchB50RiskRows,
  canonicalTrimPreview, canonicalTrimApply,
  fetchTrimDecisionContext, rejectTrimSuggestions,
  fetchCompletenessScopeOverrides, saveCompletenessScopeOverride,
  clearCompletenessScopeOverride,
  fetchTrimNoteLinkage, applyTrimNoteLinkage,
  type TrimDecisionContext, type TrimDecisionDegradation,
  type CompletenessScopeOverride,
  type NoteLinkageView, type NoteLinkageItem,
} from '@/services/commonApi'
// 裁剪三维判据决策内核（spec procedure-trimming-and-delegation-intelligence Task 13）：
// 🔴 本页**不再自行判断**裁剪与否 —— 判据顺序（风险保护 → 强制保留 → 数据存在性 →
//    完整性豁免 → 重要性）全部收敛在 `decideTrim` 纯函数里。改造前这里有一份内联
//    `decide()` 只看「科目在试算表有无数据」单一维度，且其 `p.is_mandatory` 判据
//    因后端不下发该字段而恒为死判据。
import {
  decideTrim,
  type TrimDecision, type SubjectDataState, type TrimRiskInput,
} from '@/components/workpaper/composables/procedureTrimDecision'
import { evaluateAggregateGate } from '@/components/workpaper/composables/trimAggregateGate'
import {
  COMPLETENESS_CYCLE_RULES,
  resolveCompletenessExemption,
  type CompletenessExemptionSource,
} from '@/components/workpaper/composables/completenessExemption'
import {
  formatTrimReason, reasonCodeLabel, isMachineReasonCode,
} from '@/components/workpaper/composables/trimReasonCodes'
// B50 填写完成度（spec procedure-trimming-and-delegation-intelligence Task 4）：
// 🔴 与 GtB50RiskAssessment.vue 的完成度面板共用**同一个**纯函数，禁在此另算一份 ——
// 两处口径分叉会让「裁剪页说已完成、B50 页说部分完成」，审计师无从判断哪个可信。
import {
  resolveB50Completeness, normalizeFromReader,
  B50_COMPLETENESS_LABEL, B50_COMPLETENESS_TAG_TYPE, B50_COMPLETENESS_HINT,
} from '@/components/workpaper/composables/b50Completeness'
// 委派建议分配（Task 17 算法 + Task 18 表格组件）：
// 🔴 `roleSeniority` 是 role → 资历的**唯一**折算入口 —— 平台不下发资历数值
//    （`staff_members.role_level` 后端 0 命中），而 `suggestDelegation` 要
//    `seniority: number`。绝不可挪用本文件的 `ROLE_PRIORITY`（那是主编下拉排序
//    优先级，键集更少且未登记 role 兜底 90 = 反而最高，详见 delegationSeniority.ts）。
import {
  suggestDelegation,
  type DelegationMember, type DelegationTarget, type DelegationSuggestionResult,
} from '@/components/workpaper/composables/delegationSuggestion'
import { roleSeniority } from '@/components/workpaper/composables/delegationSeniority'
import GtDelegationSuggestionTable, {
  type DelegationApplyGroup,
} from '@/components/workpaper/delegation/GtDelegationSuggestionTable.vue'
// 裁剪充分性复核视图（Task 20）：
// 🔴 统计**全部**由 `buildTrimAdequacyReview` 派生，而它的金额汇总走本页同一个
//    `evaluateAggregateGate`、理由码分类走同一个 `trimReasonCodes` ⇒ 与本页统计
//    同输入同输出（R12.7）。禁在复核视图里另算一份计数。
// 🔴 组件只读（零 IO、零写入调用），定位只发 `locate` 事件由本页执行。
import GtTrimAdequacyReview from '@/components/workpaper/trim/GtTrimAdequacyReview.vue'
import {
  buildTrimAdequacyReview,
  type ReviewProcedureRow, type ReviewCycleInput, type ReviewAnomalyKind,
  type PlatformDefaultCompletenessCycle,
} from '@/components/workpaper/composables/trimAdequacyReview'
import { listWorkpapersPaged } from '@/services/workpaperApi'
import { listAssignments } from '@/services/staffApi'
import { ROLE_TERMS, newRequestId } from '@/components/workpaper/composables/procedureConsoleOverlay'
import http from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { exportMultiSheetData } from '@/composables/useExcelIO'
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

// ── 成员负载（单一真源 = 后端 member-loads 端点）──
// 🔴 口径 = 各执行人当前**非终态任务数**，与委派 preview 的
// membership_load.active_task_count 同源。改造前这里是前端自算的"底稿张数"，
// 与后端口径不同，且仅在打开「全项目概览」后才有值 —— 而委派界面正是最需要它
// 的地方。禁再自行聚合负载（双真源），改动会被 delegationLoadSingleSource 守卫打红。
//
// 三态：null = 尚未加载 / 加载失败（显示"负载未知"，绝不显示 0，
// 后者会误导为"这个人很空闲"）；dict 中缺该成员 = 该成员负载确实为 0。
const memberLoads = ref<Record<string, number> | null>(null)

async function loadMemberLoads() {
  try {
    memberLoads.value = await fetchDelegationMemberLoads(projectId.value)
  } catch {
    memberLoads.value = null // 保持"负载未知"，不退化为 0
  }
}

/** 某成员负载；`null` = 未知（未加载或加载失败） */
function memberLoadOf(staffId: string): number | null {
  if (memberLoads.value === null) return null
  return memberLoads.value[staffId] ?? 0
}

/** 负载展示文案：未知与 0 必须可区分 */
function memberLoadLabel(staffId: string): string {
  const n = memberLoadOf(staffId)
  return n === null ? '负载未知' : `在办${n}项`
}

// 底稿主编下拉显示标签（角色 + 当前负载）
function assigneeOptionLabel(m: { staff_id: string; staff_name: string; role_label?: string }) {
  const role = m.role_label ? ` (${m.role_label})` : ''
  return `${m.staff_name}${role} · ${memberLoadLabel(m.staff_id)}`
}

// ── B50 认定层次风险评估填写状态（Task 4）──
// 🔴 完成度判定复用 Task 3 的同一纯函数 `resolveB50Completeness`，**禁在此另算一份**
// （另算 = 双真源，B50 面板与裁剪页徽标会漂移；守卫 b50BadgeSingleSource.spec.ts 钉死）。
//
// 取数走既有端点 GET /api/b60/b50-risk-rows（它已返回 load_b50_accounts() 输出），
// **零后端改动**；后端字段是 `account` + `cells[*].rmm`，故用 normalizeFromReader 归一。
//
// 三态 null = 尚未加载/加载失败 ⇒ 徽标不显示（不能把"没查到"显示成"未开始"，
// 那会让审计师以为自己没填过而重复劳动）。
const b50Accounts = ref<{ account?: unknown; cells?: unknown }[] | null>(null)

async function loadB50Status() {
  try {
    b50Accounts.value = await fetchB50RiskRows(projectId.value)
  } catch {
    b50Accounts.value = null
  }
}

/** B50 完成度（与 GtB50RiskAssessment 面板同源）；null = 未知 */
const b50Completeness = computed(() => {
  if (b50Accounts.value === null) return null
  return resolveB50Completeness({ accounts: normalizeFromReader(b50Accounts.value) })
})

/**
 * B50 完成度是否已知。
 *
 * 🔴 模板里凡取 `b50Completeness.state` 一律要在本标志的分支内 —— 未知态该 computed
 * 返回 `null`（有意保留该契约：把未知补成 `not_started` 会谎报「B50 未开始」，
 * 而实际是接口坏了，审计师据此去填 B50 也解决不了）。
 */
const b50Loaded = computed(() => b50Accounts.value !== null)

// ═══════════════════════════════════════════════════════════════════════════
// 裁剪三维判据：程序对象 → 决策内核入参的映射（Task 13）
// ═══════════════════════════════════════════════════════════════════════════
//
// 🔴 本段只做**映射**，不含任何判据逻辑 —— 判据全在 `decideTrim`（Task 7）里。
//    在这里补一个「顺手的小判断」就会形成第二份判据真源，随后两处结论分叉时
//    无从裁决谁对（本 spec 全程在治的缺陷模式）。
//
// ## 科目名解析：为什么必须容忍解析不出
//
// `ctx.accounts` 按**科目名**索引（`{货币资金: {amount, cycle}}`），而程序按
// `wp_code` 组织 —— 两者之间没有现成映射。故：
//
// - 解析得到科目名 → 取该科目 `amount` 与 B50 该科目风险，走完整三维判据；
// - 解析不出 → `accountAmount = null` + `risk = null`，决策内核据此**跳过**
//   重要性与风险两个维度（档 4/6 会接住它），**不会**把它当成「余额为 0」。
//
// 这是「宁缺勿造」在本处的落法：编造 0 会让该程序被误判成「低于任何阈值」而
// 产生裁剪建议，而正确结论是「该维度对它不可用」。

/** 从 `wp_code` 取科目底稿前缀（`D2-1` → `D2`），用于科目级数据可用性判定。 */
function subjectPrefixOf(p: any): string {
  const code = String(p?.wp_code || p?.procedure_code || '').toUpperCase()
  return code.match(/^([A-Z]+\d+)/)?.[1] || ''
}

/**
 * 按科目名在判据上下文里定位该程序对应的科目。
 *
 * 判定顺序：程序名包含科目名（最长优先，避免「应收账款」被「应收」抢走）→
 * 科目名包含程序名。两者都不成立返回 null（不猜）。
 */
function resolveAccountName(p: any, ctx: TrimDecisionContext): string | null {
  const names = Object.keys(ctx.accounts || {})
  if (!names.length) return null
  const procName = String(p?.procedure_name || '').trim()
  if (!procName) return null
  // 最长匹配优先：科目名越长越具体（「应收账款」优于「应收」）
  const sorted = [...names].sort((a, b) => b.length - a.length)
  for (const n of sorted) {
    if (n && procName.includes(n)) return n
  }
  return null
}

/** B50 科目项 → 决策内核的 `TrimRiskInput`；缺该科目返回 null（未评估 ≠ 低风险）。 */
function toRiskInput(raw: any): TrimRiskInput | null {
  if (!raw || typeof raw !== 'object') return null
  const cells = (raw.cells && typeof raw.cells === 'object') ? raw.cells : {}
  const comp = cells.completeness && typeof cells.completeness === 'object' ? cells.completeness : {}
  const rmm = comp.rmm ?? null
  return {
    maxRisk: (raw.max_risk ?? null) as TrimRiskInput['maxRisk'],
    hasSpecial: raw.has_special === true,
    completenessRmm: (rmm === 'H' || rmm === 'M' || rmm === 'L') ? rmm : null,
    completenessSpecial: comp.special === true,
    approach: raw.approach ?? null,
    reliance: raw.reliance ?? null,
  }
}

/**
 * 组装决策入参并调用内核。
 *
 * `subjectWithData` / `subjectNoData` 来自既有 `/procedure-scope/data-availability`
 * （按 `wp_code` 前缀），比循环级更精确；两者都不命中 → `'unknown'` 退回循环级。
 */
function buildAndDecide(
  p: any,
  ctx: TrimDecisionContext,
  subjectWithData: Set<string>,
  subjectNoData: Set<string>,
): TrimDecision {
  const cycle = String(p?.procedure_code || p?.wp_code || '').charAt(0).toUpperCase()
  const prefix = subjectPrefixOf(p)
  const subjectDataState: SubjectDataState = subjectWithData.has(prefix)
    ? 'with_data'
    : subjectNoData.has(prefix)
      ? 'no_data'
      : 'unknown'

  // 循环级数据存在性：由 ctx.accounts 的 cycle 字段派生（不另发请求）
  let cycleHasData = false
  for (const info of Object.values(ctx.accounts || {})) {
    if (String((info as any)?.cycle || '').toUpperCase() === cycle) { cycleHasData = true; break }
  }

  const accountName = resolveAccountName(p, ctx)
  const accountAmount = accountName !== null
    ? Number((ctx.accounts as any)[accountName]?.amount)
    : null

  // 完整性豁免：项目级覆盖优先于平台默认清单，`source` 如实标注来源
  const override = ctx.completeness_override
  const hasOverride = override !== null && override !== undefined
    && Object.prototype.hasOwnProperty.call(override, cycle)
  const cycleRule = COMPLETENESS_CYCLE_RULES.find(r => r.cycle === cycle) ?? null
  const completenessSensitiveCycle = hasOverride
    ? (override as Record<string, boolean>)[cycle] === true
    : (cycleRule ? cycleRule.sensitiveByDefault : false)
  const completenessSource: CompletenessExemptionSource = hasOverride
    ? 'cycle_override'
    : 'cycle_default'

  const mat = ctx.materiality
  const suggestion = (p?.suggestion_state && typeof p.suggestion_state === 'object')
    ? p.suggestion_state
    : null

  return decideTrim({
    procedure: {
      wpCode: String(p?.wp_code || p?.procedure_code || ''),
      cycle,
      // 🔴 `ProcedureInstance` 无 `is_mandatory` 列（2026-08-09 实证）——
      //    强制保留改由「A/S 循环 + 非科目余额驱动循环 + 已有进度 + 已手工理由 +
      //    底稿已录入」五档承担，此处如实传 false 而不是读一个不存在的字段。
      isMandatory: false,
      executionStatus: p?.execution_status ?? null,
      hasManualReason: Boolean(String(p?.skip_reason || '').trim()),
      suggestionRejected: suggestion?.rejected === true,
      hasWorkpaperEntry: (ctx.workpaper_entry || {})[String(p?.wp_code || '')] === true,
    },
    accountAmount: (accountAmount !== null && Number.isFinite(accountAmount)) ? accountAmount : null,
    subjectDataState,
    cycleHasData,
    materiality: mat
      ? {
        performanceMateriality: mat.performance_materiality,
        trivialThreshold: mat.trivial_threshold,
      }
      : null,
    risk: toRiskInput((ctx.risk || {})[accountName ?? '']),
    riskDimensionAvailable: ctx.risk_dimension_available === true,
    completenessSensitiveCycle,
    completenessSource,
  })
}

/** 跳转 B50 底稿（走既有 wp_code 深链，不新建路由） */
function goToB50() {
  router.push({
    path: `/projects/${projectId.value}/workpapers`,
    query: { wp_code: 'B50' },
  })
}

// ════════════════════════════════════════════════════════════════════════════
// 裁剪三维判据（spec Task 13：风险评估 → 数据存在性 → 重要性）
// ════════════════════════════════════════════════════════════════════════════
//
// 🔴 本页**不再自行判断**裁剪与否 —— 全部决策委托给纯函数 `decideTrim`。
//    改造前的 `confirmSmartTrim` 内联一个 `decide()`，唯一判据是「科目在试算表
//    有无数据」；风险评估与重要性两个法定判据完全没参与。内联判据的问题不只是
//    少了两维，而是它**无法被单独测试**：判据顺序、短路性、降级行为都只能靠
//    端到端点一遍来验证，而「特别风险科目不得被裁」这种审计红线恰恰需要用
//    变异检验钉死。
//
// 🔴 `degradations` 是降级标注的**唯一来源**，本页不得自行判断「某维度是不是空的」。
//    自行判断会产生「标注说没做重要性联动、结果集里却有重要性类理由码」这种
//    自相矛盾状态（Property 12 双向锁死的正是这一点）。

/** 三维判据上下文；null = 尚未加载或加载失败（后者会阻断裁剪） */
const trimContext = ref<TrimDecisionContext | null>(null)
/** 上下文请求本身失败（网络/权限/500）—— 与「后端说某维度降级」是两回事 */
const trimContextError = ref<string | null>(null)
/** 科目底稿级数据可用性（registry 覆盖的 wp_code 前缀） */
const subjectWithData = ref<Set<string>>(new Set())
const subjectNoData = ref<Set<string>>(new Set())
/**
 * 本次 `trimContext` 覆盖的循环（大写代号集合）。
 *
 * 🔴 复核视图（Task 20）据此决定「哪些循环的科目余额可解析」——
 * 后端 `_load_accounts` 按 `cycles` 过滤，拿 D 循环的 accounts 去给 E 循环的程序
 * 做最长匹配会解析出**别的循环的科目金额**，那比解析不出更坏（数字看起来合理、
 * 实际张冠李戴）。故未覆盖的循环一律按「金额未知」如实统计。
 */
const trimContextCycles = ref<Set<string>>(new Set())

// 建议态的持有形态、统计、汇总闸与逐条/批量确认，统一声明在下方
// 「建议态：逐条确认 / 批量确认 / 逐条驳回」一节 —— 建议态挂在**程序行**上
// （`p._suggest` / `p._suggestReasonCode` / `p._suggestNarrative`）而不是另存一个
// 以 id 为键的 Map：两者并存会让「行上说是建议、Map 里已被删掉」这类不一致出现，
// 而模板渲染读的是行。此处刻意不再声明第二份（重复顶层声明会让 Vite transform
// 直接失败，且 `get_diagnostics` 查不出）。

/**
 * 降级标注（直接来自后端 `degradations`，不自行推断）。
 *
 * 维度 → 中文说明的映射只做措辞，不做判断。
 */
const degradationNotes = computed(() => {
  const list = trimContext.value?.degradations ?? []
  return list.map(d => ({
    dimension: String(d.dimension ?? ''),
    text: degradationText(d),
  }))
})

function degradationText(d: TrimDecisionDegradation): string {
  const dim = String(d?.dimension ?? '')
  if (dim === 'materiality') {
    return '未做重要性联动：本项目未确定重要性水平，不产生金额类裁剪建议'
  }
  if (dim === 'risk') {
    return '未做风险联动：B50 认定层次风险矩阵尚未填写，风险保护判据不生效'
  }
  if (dim === 'accounts') {
    const cause = String(d?.cause ?? '')
    if (cause === 'query_failed') return '试算表读取失败：已阻断本次裁剪'
    if (cause === 'not_imported') return '试算表尚未导入：已阻断本次裁剪'
    return '试算表无实质科目数据：已阻断本次裁剪'
  }
  // 🔴 维度名必须是后端 `DIM_COMPLETENESS_OVERRIDE` 的字面量 `completeness_override`。
  //    此处曾写 `completeness` ⇒ 该分支**永不命中**，落到末尾的 `d.reason` 兜底上。
  //    兜底恰好也是中文，所以界面看不出异常 —— 这类"措辞映射键写错"的分支只能靠
  //    与后端取值域交叉锁死的守卫发现（`completenessScopeOverride.spec.ts` 有一条）。
  if (dim === 'completeness_override') {
    return '完整性敏感清单项目覆盖读取失败：已退回平台默认清单（标注为「使用平台默认，未经本项目确认」）'
  }
  if (dim === 'workpaper_entry') {
    return '底稿录入探测失败：已按"全部已录入"保守保留（不产生裁剪建议）'
  }
  return String(d?.reason ?? dim)
}

// 🔴 此处曾有第二套「程序 → 决策入参」映射（`accountNameOf` + `buildDecisionInput`），
//    与上方的 `resolveAccountName` + `buildAndDecide` 构成**双真源**且科目名解析策略
//    完全不同：那一套按「wp_code 前缀所在循环恰好只有一个科目」对应，实测几乎永不
//    命中（一个循环通常有多个科目）⇒ `accountAmount` 恒 null ⇒ 重要性维度整体空转；
//    而它自身**零消费方**（只被自己的声明引用）。两套并存时无从裁决「同一程序两种
//    金额」谁对，故整体删除，统一走按程序名最长匹配科目名的那一套。
//
//    留此说明是为了让后续会话不再把它"补回来"：需要改进科目名解析时改
//    `resolveAccountName` 一处，不要新增第二个解析函数。

/** 加载三维判据上下文 + 科目级数据可用性 */
async function loadTrimContext(cycleList: string[]): Promise<boolean> {
  trimContextError.value = null
  try {
    trimContext.value = await fetchTrimDecisionContext(projectId.value, year.value, cycleList)
    // 🔴 覆盖面与上下文**同一次**更新：分开更新会出现「上下文是 D 的、覆盖面标着 E」
    //    这种复核视图按错循环解析金额的中间态。
    trimContextCycles.value = new Set(
      (cycleList || []).map(c => String(c).trim().toUpperCase()).filter(Boolean),
    )
  } catch (e: any) {
    trimContext.value = null
    trimContextCycles.value = new Set()
    trimContextError.value = e?.message ? String(e.message) : '判据上下文读取失败'
    return false
  }
  try {
    const av: any = await http.get(
      `/api/projects/${projectId.value}/procedure-scope/data-availability`,
      { params: { year: year.value } },
    )
    const sp = av?.data?.data ?? av?.data ?? {}
    subjectWithData.value = new Set((sp.subject_with_data || []).map((w: any) => String(w).toUpperCase()))
    subjectNoData.value = new Set((sp.subject_no_data || []).map((w: any) => String(w).toUpperCase()))
  } catch {
    // 科目级不可用时静默降级到循环级（决策内核的 `unknown` 态承载该降级）
    subjectWithData.value = new Set()
    subjectNoData.value = new Set()
  }
  return true
}

// ════════════════════════════════════════════════════════════════════════════
// 完整性敏感清单的项目级覆盖（Task 14，R5.5 / R5.6 / R5.7）
// ════════════════════════════════════════════════════════════════════════════
//
// ## 它在裁剪链条里的位置
//
// 「科目余额低于实际执行重要性 ⇒ 建议裁掉该科目程序」这条金额判据，对**完整性风险高**
// 的科目必须失效 —— 少记负债 / 少记费用 / 跨期少记收入本身就会压低账面金额，用金额去
// 豁免它等于用症状豁免病因。失效范围两级判据：① 认定级（B50 该科目 completeness 认定）
// 优先；② 认定缺失时退回**循环级清单**。本面板管的就是 ② 的项目级覆盖。
//
// 🔴 判据逻辑一行都不在这里 —— 全在 `resolveCompletenessExemption`（Task 6 的单一真源）。
//    本段只做三件事：把覆盖表读出来、写回去、按同一真源的 `usingPlatformDefault` 标注。
//    在这里补一个"顺手的判断"（例如「一条覆盖都没有就算全部平台默认」）就会形成第二份
//    判据真源，而那种写法在**读取失败**时同样得出"全部平台默认"，把技术故障说成实质结论。
//
// 🔴 决策内核的入参**仍走后端下发的 `ctx.completeness_override`**（见 `buildAndDecide`），
//    本面板不给内核喂第二份覆盖表。故写入后必须刷新**两处**：面板列表（回显理由与留痕）
//    与判据上下文（内核据以重算）。只刷一处会出现「面板说已确认、裁剪判据仍按平台默认」。

/**
 * R5.6 的标注措辞。
 *
 * 🔴 与 `resolveCompletenessExemption` 在 `cycle_default` 分支给出的 rationale 前缀
 * **交叉锁死**（守卫读 `completenessExemption.ts` 源码比对该字面量）：一侧改措辞而另一侧
 * 不动，会让复核视图与判据说明用两套说法描述同一件事。
 */
const PLATFORM_DEFAULT_NOTICE = '使用平台默认，未经本项目确认'

/** 项目级覆盖清单；`null` = 尚未加载 / 读取失败（**未知**，不等于"没覆盖过"） */
const completenessOverrides = ref<CompletenessScopeOverride[] | null>(null)
const completenessError = ref<string | null>(null)
const completenessPanelVisible = ref(false)
/** 正在写入的循环代号（逐行 loading，避免整表禁用） */
const completenessSaving = ref<string | null>(null)

async function loadCompletenessOverrides(): Promise<boolean> {
  try {
    completenessOverrides.value = await fetchCompletenessScopeOverrides(projectId.value)
    completenessError.value = null
    return true
  } catch (e: any) {
    // 🔴 失败保持 `null`（未知），**不退化为 `[]`** —— 空数组会让 11 个循环全被标注
    //    「使用平台默认，未经本项目确认」，而真实原因是覆盖表读不到。两者在审计上
    //    的含义完全不同：前者是"本项目没做这个判断"，后者是"平台不知道本项目做没做"。
    completenessOverrides.value = null
    completenessError.value = e?.message ? String(e.message) : '完整性敏感清单覆盖读取失败'
    return false
  }
}

/** `{cycle: sensitive}`；`null` = 未知（与「已加载且为空」可区分） */
const completenessOverrideMap = computed<Record<string, boolean> | null>(() => {
  const list = completenessOverrides.value
  if (list === null) return null
  const out: Record<string, boolean> = {}
  for (const o of list) out[String(o.cycle).toUpperCase()] = o.sensitive === true
  return out
})

const CYCLE_LABEL: Record<string, string> = Object.fromEntries(cycles.map(c => [c.code, c.label]))

interface CompletenessScopeRow {
  cycle: string
  label: string
  /** 平台默认取值（清单声明式真源） */
  platformDefault: boolean
  /** 平台默认的审计依据（R5.4：不得只有布尔值） */
  rationale: string
  /** 当前生效结论（项目覆盖优先） */
  sensitive: boolean
  source: CompletenessExemptionSource
  /** R5.6 标注开关；恒等价于 `source === 'cycle_default'`（Property 9） */
  usingPlatformDefault: boolean
  reason: string
  updatedByName: string | null
  updatedAt: string | null
}

/**
 * 逐循环面板行：结论 / 判据来源 / 平台默认标注**全部取自纯函数**，本 computed 只做拼装。
 */
const completenessScopeRows = computed<CompletenessScopeRow[]>(() => {
  const map = completenessOverrideMap.value
  const byCycle = new Map(
    (completenessOverrides.value ?? []).map(o => [String(o.cycle).toUpperCase(), o]),
  )
  return COMPLETENESS_CYCLE_RULES.map((rule) => {
    // 循环级视图固定传「认定缺失」（`completenessRmm: null` + `completenessSpecial: false`）——
    // 认定级判据是逐**科目**的，本面板管的是循环级默认与覆盖，二者不同层。
    const resolved = resolveCompletenessExemption({
      completenessRmm: null,
      completenessSpecial: false,
      cycle: rule.cycle,
      projectOverride: map,
    })
    const rec = byCycle.get(rule.cycle) ?? null
    return {
      cycle: rule.cycle,
      label: CYCLE_LABEL[rule.cycle] || rule.cycle,
      platformDefault: rule.sensitiveByDefault,
      rationale: rule.rationale,
      sensitive: resolved.exempt,
      source: resolved.source,
      usingPlatformDefault: resolved.usingPlatformDefault,
      reason: rec?.reason ?? '',
      updatedByName: rec?.updated_by_name ?? null,
      updatedAt: rec?.updated_at ?? null,
    }
  })
})

/**
 * 裁剪摘要的「使用平台默认，未经本项目确认」标注（R5.6）。
 *
 * 🔴 触发条件**只看** `usingPlatformDefault`（`resolveCompletenessExemption` 的输出），
 * 不看「覆盖列表是否为空」这类等价条件 —— 那是第二份判据，与 Property 9 分叉时无从裁决。
 * 🔴 未知态（读取失败）返回 `null` 而不是"全部平台默认"：否则接口一坏，摘要就会宣称
 * 本项目 11 个循环全未确认，审计师照此去逐个确认也修不好真正的问题。
 */
const completenessDefaultNotice = computed<{ cycles: string[]; text: string } | null>(() => {
  if (completenessOverrides.value === null) return null
  const list = completenessScopeRows.value
    .filter(r => r.usingPlatformDefault)
    .map(r => r.cycle)
  if (list.length === 0) return null
  return {
    cycles: list,
    text: `${PLATFORM_DEFAULT_NOTICE}：${list.join(' / ')} 循环的完整性敏感判据取平台默认值（共 ${list.length} 个，建议由项目组逐循环确认）`,
  }
})

function openCompletenessPanel() {
  completenessPanelVisible.value = true
  if (completenessOverrides.value === null) loadCompletenessOverrides()
}

/** 覆盖来源的中文标签（纯措辞，判据在 `source` 上） */
function completenessSourceLabel(row: CompletenessScopeRow): string {
  return row.source === 'cycle_override' ? '本项目已确认' : PLATFORM_DEFAULT_NOTICE
}

/**
 * 写一条项目级覆盖（`true` / `false` **都算已表态**）。
 *
 * 理由必填有三道：弹窗 `inputValidator`（交互）→ 本函数发请求前的独立判断（程序化调用
 * 也拦住）→ 后端 400（唯一权威）。三道都保留：只靠第一道会被"改用别的调用方式"绕过，
 * 只靠第三道会把可预期的必填校验显示成"保存失败"。
 */
async function setCompletenessScope(row: CompletenessScopeRow, sensitive: boolean) {
  if (!canManage.value) return
  let reason = ''
  try {
    const res = await ElMessageBox.prompt(
      `确认本项目${sensitive ? '视' : '不视'} ${row.label} 循环为完整性敏感`
      + `（${sensitive ? '豁免' : '适用'}「科目余额低于实际执行重要性」这条裁剪建议判据）。`
      + `平台默认为「${row.platformDefault ? '敏感' : '不敏感'}」。请填写理由（必填，供质控与复核评价其适当性）：`,
      sensitive ? '设为完整性敏感' : '设为非完整性敏感',
      {
        confirmButtonText: '保存覆盖',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '例如：本期存在大量未开票暂估，完整性方向风险显著高于账面金额所反映的水平',
        inputValidator: (v: string) => (String(v || '').trim().length > 0
          ? true
          : '必须填写覆盖理由（无理由的覆盖在复核时无法评价其适当性）'),
      },
    )
    reason = String((res as any)?.value ?? '').trim()
  } catch {
    return // 用户取消
  }
  if (!reason) {
    ElMessage.warning('必须填写覆盖理由，未保存')
    return
  }
  completenessSaving.value = row.cycle
  try {
    await saveCompletenessScopeOverride(projectId.value, row.cycle, sensitive, reason)
    ElMessage.success(`已记录 ${row.label} 循环的项目级覆盖（操作人与时间已留痕）`)
    await loadCompletenessOverrides()
    // 🔴 同时刷判据上下文：决策内核读的是后端下发的 completeness_override，
    //    只刷面板会让「面板显示已确认、裁剪判据仍按平台默认」。
    await loadTrimContext([activeCycle.value])
  } catch (e) {
    handleApiError(e, '保存完整性敏感清单覆盖失败')
  } finally {
    completenessSaving.value = null
  }
}

/** 撤销覆盖 → 该循环退回平台默认（后端删行，不写空值） */
async function revertCompletenessScope(row: CompletenessScopeRow) {
  if (!canManage.value) return
  try {
    await ElMessageBox.confirm(
      `撤销后 ${row.label} 循环将退回平台默认（${row.platformDefault ? '视为' : '不视为'}完整性敏感），`
      + `并在裁剪摘要中重新标注「${PLATFORM_DEFAULT_NOTICE}」。是否继续？`,
      '撤销项目级覆盖',
      { type: 'warning', confirmButtonText: '撤销覆盖', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  completenessSaving.value = row.cycle
  try {
    await clearCompletenessScopeOverride(projectId.value, row.cycle)
    ElMessage.success(`${row.label} 循环已退回平台默认`)
    await loadCompletenessOverrides()
    await loadTrimContext([activeCycle.value])
  } catch (e) {
    handleApiError(e, '撤销覆盖失败')
  } finally {
    completenessSaving.value = null
  }
}

// ─── 附注反向联动（Task 21 / R13.1~R13.4、R13.6）────────────────────────────
//
// 🔴 三态 ref：`null` = 未加载或加载失败（**不是**「无可标注章节」）。退化成空对象会把
//    技术故障显示成「附注侧没有需要标注的章节」这一实质结论 —— 那是审计师据以判断
//    交付件里会不会出现空白披露的依据。
const noteLinkage = ref<NoteLinkageView | null>(null)
const noteLinkageError = ref<string | null>(null)
const noteLinkageLoading = ref(false)
const noteLinkageApplying = ref(false)
const noteLinkagePanelVisible = ref(false)

/**
 * 面板分组（每组自带"这组意味着什么"的说明）。
 *
 * 🔴 `conflicts` / `unlocatable` 不能与 `to_mark` 混在一张表里：三者对审计师的含义
 * 完全不同（会改 / 不会改但要你决定 / 附注侧压根没这一节），合成一张表会让「有内容
 * 所以没标」看起来像「已标」。
 */
const noteLinkageBuckets = computed<{
  key: string; label: string; tag: 'success' | 'warning' | 'info' | 'danger'
  hint: string; items: NoteLinkageItem[]
}[]>(() => {
  const v = noteLinkage.value
  if (!v) return []
  return [
    { key: 'to_mark', label: '将标注为本期不适用', tag: 'warning', items: v.to_mark,
      hint: '对应底稿已全部裁剪且所属循环已整体裁剪；只改呈现，不删章节' },
    { key: 'to_revoke', label: '将撤销标注', tag: 'success', items: v.to_revoke,
      hint: '裁剪已恢复执行 → 本联动此前标的「不适用」相应撤销' },
    { key: 'conflicts', label: '已有内容，只提示不自动标注', tag: 'danger', items: v.conflicts,
      hint: '章节里已有正文或表格数据 —— 自动标注会把它压在导出之外，请在附注模块自行决定' },
    { key: 'unlocatable', label: '附注侧未找到该章节', tag: 'info', items: v.unlocatable,
      hint: '本年度尚未生成该章节，已跳过并记录，不影响裁剪保存' },
    { key: 'skipped_foreign_mark', label: '人工标注，本联动不撤销', tag: 'info', items: v.skipped_foreign_mark,
      hint: '该「不适用」由审计师手工设置，程序裁剪恢复也不会自动清掉' },
  ]
})

/** 有没有需要审计师看一眼的东西（标注 / 撤销 / 有内容冲突 / 定位不到） */
const noteLinkageActionable = computed(() => {
  const v = noteLinkage.value
  if (!v) return 0
  return v.to_mark.length + v.to_revoke.length + v.conflicts.length + v.unlocatable.length
})

/**
 * 只读加载联动预览。**自吞异常**（R13.6：联动不得阻断裁剪保存），但把失败记进
 * `noteLinkageError` 而不是静默 —— 静默会让「读不到」与「没有可标注章节」不可区分。
 */
async function loadNoteLinkage(): Promise<void> {
  if (!projectId.value) return
  noteLinkageLoading.value = true
  noteLinkageError.value = null
  try {
    const view = await fetchTrimNoteLinkage(projectId.value, year.value)
    noteLinkage.value = view
    if (noteLinkageActionable.value > 0) noteLinkagePanelVisible.value = true
  } catch (e: any) {
    noteLinkage.value = null
    noteLinkageError.value = e?.message || '附注联动预览读取失败'
  } finally {
    noteLinkageLoading.value = false
  }
}

/**
 * 手动打开面板：先开再加载，使「加载失败」这一状态也有地方显示。
 *
 * 🔴 反过来（加载成功才开）会让读取失败**完全不可见** —— 点了没反应，审计师无从判断
 * 是"没有需要标注的章节"还是"读不到"。
 */
function openNoteLinkagePanel() {
  noteLinkagePanelVisible.value = true
  void loadNoteLinkage()
}

/** 应用联动：后端只写 `disclosure_notes.is_empty` + provenance 面包屑，幂等。 */
async function applyNoteLinkage(): Promise<void> {
  if (!projectId.value || !canManage.value) return
  noteLinkageApplying.value = true
  try {
    const res = await applyTrimNoteLinkage(projectId.value, year.value)
    noteLinkage.value = res
    if (res.marked || res.revoked) {
      ElMessage.success(`附注章节已更新（标注 ${res.marked} 节，撤销 ${res.revoked} 节）`)
    } else {
      ElMessage.info('附注章节无需变更')
    }
  } catch (e) {
    handleApiError(e, '应用附注联动失败')
  } finally {
    noteLinkageApplying.value = false
  }
}

// P1-3 / P0-1 全项目裁剪概览行（各循环 保留/裁剪/缺理由/未初始化）
const overviewRows = computed(() => {
  return cycles.map(c => {
    const list = allCyclesData.value[c.code]
    if (!Array.isArray(list)) {
      return { code: c.code, label: c.label, total: 0, execute: 0, trimmed: 0, missingReason: 0, suggestConfirmed: 0, suggestRejected: 0, uninitialized: !(c.code in allCyclesData.value) }
    }
    const execute = list.filter(p => p.status !== 'not_applicable' && p.status !== 'skip').length
    const trimmed = list.length - execute
    const missingReason = list.filter(p => (p.status === 'not_applicable' || p.status === 'skip') && !(p.skip_reason || '').trim()).length
    // 建议态口径（Task 13 / R6.6）：概览侧消费的是 `getProcedures` 的**原始行**，
    // 上面没有 `_suggest` / `_applicable` —— 那两个字段是本页 loadProcedures 里经
    // `decideTrim` 派生后才写回 procedures.value 的。跨循环重跑 decideTrim 需要 per-cycle
    // 的三维判据上下文（科目数据态 / 风险 / 重要性），概览侧拿不到；若在此另造一套判据
    // 就会形成第二真源（判据真源只能是 procedureTrimDecision.decideTrim）。
    // 故概览侧只统计**已落地的事实**，不做二次判断：
    //   已确认 = 已落不适用/跳过 且 理由码是机器判据码（isMachineReasonCode，真源 trimReasonCodes）
    //   已驳回 = suggestion_state.rejected === true（后端 /reject 只写这一位，不动适用性）
    // 「待确认（suggested）」不可从原始行派生，概览侧明确不展示；单循环口径见 suggestionStats。
    const suggestConfirmed = list.filter(p => (p.status === 'not_applicable' || p.status === 'skip') && isMachineReasonCode(p.suggestion_state?.reason_code)).length
    const suggestRejected = list.filter(p => p.suggestion_state?.rejected === true).length
    return { code: c.code, label: c.label, total: list.length, execute, trimmed, missingReason, suggestConfirmed, suggestRejected, uninitialized: false }
  })
})
const overviewTotals = computed(() => {
  const rows = overviewRows.value.filter(r => !r.uninitialized)
  return {
    total: rows.reduce((s, r) => s + r.total, 0),
    execute: rows.reduce((s, r) => s + r.execute, 0),
    trimmed: rows.reduce((s, r) => s + r.trimmed, 0),
    missingReason: rows.reduce((s, r) => s + r.missingReason, 0),
    suggestConfirmed: rows.reduce((s, r) => s + r.suggestConfirmed, 0),
    suggestRejected: rows.reduce((s, r) => s + r.suggestRejected, 0),
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

// 保存裁剪（canonical preview → apply 两阶段）
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
    // 构建 canonical scope entries（粗裁：每条 procedure 对应一条 scope entry）
    const entries = procedures.value.map(p => ({
      kind: 'scope' as const,
      cycle: activeCycle.value,
      wp_index_code: p.wp_code || p.procedure_code,
      target_status: p._applicable ? 'execute' : 'not_applicable',
      skip_reason: p._applicable ? undefined : (p.skip_reason || undefined),
    }))

    // 阶段 1：preview（一次性凭证）
    const preview = await canonicalTrimPreview(projectId.value, entries)
    const previewId: string = preview.preview_id

    // 409 migration_conflict → 要求重新预览
    if (preview.migration_conflicts?.length > 0) {
      ElMessage.warning(`${preview.migration_conflicts.length} 个条目含旧 UUID 无法自动转换，请联系管理员`)
      return
    }

    // 阶段 2：apply（消费 preview 凭证 + request_id 幂等）
    const requestId = newRequestId()
    const result = await canonicalTrimApply(projectId.value, entries, previewId, requestId)

    // 保存成功 → 刷新初始快照，isDirty 归位
    originalSnapshot = JSON.parse(JSON.stringify(procedures.value))
    const applied = result.applied ?? result.changed ?? 0
    const unchanged = result.unchanged ?? 0
    ElMessage.success(`裁剪已保存（变更 ${applied}，未变 ${unchanged}），保留执行的程序已加入待执行底稿库`)
    ok = true
    // 附注反向联动（Task 21 / R13.1）：裁剪已落库 → 看附注侧有没有章节该标「本期不适用」。
    // 🔴 放在 `ok = true` 之后且自吞异常：联动是加法式的，R13.6 要求它任何情况下都不
    //    阻断裁剪保存。裁剪本身已 commit，此处失败只是少提示一次。
    void loadNoteLinkage()
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning('目标版本已变化或预览过期，请重试')
    } else {
      handleApiError(e, '保存裁剪')
    }
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
    // 🔴 理由码列与理由文本列**并列**（Requirement 8.6 / Property 35）：
    //    「理由码」是机器判据（no_data / below_trivial / below_materiality / covered_elsewhere），
    //    「裁剪理由」是自由文本（含存量纯手工填写的理由）。二者不得合并成一列 ——
    //    Requirement 8.8 明令不得把理由码编码进文本列（那样复核方无法按码做全项目统计）。
    const aoa: any[][] = [['循环', '编号', '程序名称', '适用性', '裁剪理由', '理由码', '底稿主编', '来源']]
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
          applicable ? '' : (p.suggestion_state?.reason_code || ''),
          staffName(p.assigned_to || null),
          (p.is_custom || p.source === 'custom') ? '自定义' : '模板',
        ])
      }
    }
    if (aoa.length <= 1) {
      ElMessage.warning('暂无可导出的程序数据')
      return
    }
    // 走 useExcelIO 单一入口（B6 批）。三个显式关闭保持产物不变。
    await exportMultiSheetData({
      sheets: [{
        sheetName: '底稿粗裁方案',
        rows: aoa,
        colWidths: [{ wch: 12 }, { wch: 12 }, { wch: 40 }, { wch: 8 }, { wch: 32 }, { wch: 16 }, { wch: 14 }, { wch: 8 }],
      }],
      fileName: `底稿粗裁方案_${projectId.value.slice(0, 8)}.xlsx`,
      applyStyles: false,
      successMessage: false,
    })
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

  // ── 三维判据上下文（风险评估 → 重要性 → 数据存在性）─────────────────────────
  //
  // 🔴 改造要点：本函数**不再自行判断**，一律委托 `decideTrim` 决策内核（Task 7）。
  //    改造前这里只有一维判据（科目在试算表有无数据），且 `if (p.is_mandatory)`
  //    是死判据（`ProcedureInstance` 无该列，恒 undefined）。
  //
  // 取数走后端统一装配的 `/procedure-scope/trim-decision-context`（Task 9），
  // 三个维度各自 fail-soft 并在 `degradations` 里如实标注 —— 前端**不自行判断**
  // 某维度是不是空的（那会让「后端说没有降级」与「前端猜到空」不可区分）。
  // 🔴 取数**只走 `loadTrimContext` 一条路**（模块级 ref 是唯一持有处）。
  //
  //    改造前此处内联了第二份取数：自己 `fetchTrimDecisionContext` 存进局部 `ctx`、
  //    自己 `http.get` data-availability 存进**同名局部** `const subjectWithData`
  //    （遮蔽了模块级 ref），并把结果写向一个**从未声明**的 `decisionContext`。
  //    三个后果都是静默的：
  //      ① `decisionContext.value = ctx` 运行即 `ReferenceError`（模板/脚本四层检查全绿）
  //      ② `loadTrimContext` 因此零调用点 = 死代码 ⇒ `trimContext` 永不被写
  //      ③ ②又导致 `degradationNotes` 恒空 ⇒ 降级标注（R4.4）从未渲染过
  //    故一律收敛到 `loadTrimContext`：它同时写 `trimContext` / `subjectWithData` /
  //    `subjectNoData` 三个模块 ref，摘要区的降级标注与本函数的判据自然同源。
  const cycleList = Array.from(targetCycles)
  const ctxOk = await loadTrimContext(cycleList)
  const ctx = trimContext.value

  // 安全兜底：判据整体不可用时禁止裁剪（避免把所有循环当"无数据"全裁光）。
  // 🔴 「读取失败」与「未导入试算表」必须分开措辞 —— 前者要重试，后者要先导入，
  //    合并成一句话会让审计师做错下一步动作（R4.4）。
  const accountsEmpty = !ctx || Object.keys(ctx.accounts).length === 0
  if (!ctxOk || accountsEmpty) {
    const cause = ctx?.degradations?.find(d => d.dimension === 'accounts')?.cause
    showSmartTrimDialog.value = false
    ElMessageBox.alert(
      !ctxOk || cause === 'query_failed'
        ? '未能读取裁剪判据（试算表科目数据）。请稍后重试或手动裁剪。'
        : '试算表暂无科目数据（可能尚未导入试算表）。智能裁剪依据科目余额判断，已取消本次裁剪，请先导入试算表或手动裁剪。',
      '无法智能裁剪',
      { type: 'warning', confirmButtonText: '知道了' },
    ).catch(() => {})
    return
  }

  // 科目底稿级数据可用性已由 `loadTrimContext` 一并写入模块级
  // `subjectWithData` / `subjectNoData`（registry 覆盖的 wp_code 前缀，如 D2/E1，
  // 比循环级更精确：同一循环内 D2 有数据、D3 无数据可分别判定；未覆盖的退回循环级）。
  // 🔴 此处不得再声明同名局部去接一次 —— 那正是改造前让模块 ref 恒空的遮蔽写法。

  // 单个程序裁剪决策：**全部委托决策内核**，此处只做「程序对象 → 决策入参」的映射。
  // scope 由调用方保证（当前循环 / 跨循环各自迭代），此处不再判 targetCycles。
  const decide = (p: any): TrimDecision | null => {
    const applicable = p._applicable !== undefined
      ? p._applicable
      : (p.status !== 'not_applicable' && p.status !== 'skip')
    if (!applicable) return null // 已裁剪，不重复判定
    return buildAndDecide(p, ctx as TrimDecisionContext, subjectWithData.value, subjectNoData.value)
  }

  const scopeLabel = smartTrimScope.value === 'all' ? '全部循环' :
    smartTrimScope.value === 'current' ? `${activeCycle.value} 循环` :
    `${smartTrimCycles.value.join('/')} 循环`

  // ── 当前循环：内存应用，用户复核后点「保存粗裁」──
  //
  // 🔴 三态分流（本 spec 的核心行为变更）：
  //   `auto_trim`    → 立即在内存应用（同改造前，`no_data` 是事实判断）
  //   `suggest_trim` → **只挂建议态、不改适用性**，等审计师逐条/批量确认
  //   `keep`         → 不动
  //
  // 重要性类判据（余额低于实际执行重要性）永不走 `auto_trim` —— 那是职业判断，
  // 且若干各自低于阈值的科目汇总错报可能超过可容忍水平（汇总闸负责拦批量确认）。
  if (smartTrimScope.value === 'current') {
    let trimCount = 0
    let keepCount = 0
    let suggestCount = 0
    for (const p of procedures.value) {
      // 🔴 重跑前必须清掉上一轮建议 —— 否则上轮建议、本轮已改判为保留的行会残留
      //    `_suggest = true`，建议条计数与汇总闸都会把它继续算进去。
      clearRowSuggestion(p)
      const d = decide(p)
      if (!d) { if (p._applicable) keepCount++; continue }
      if (d.verdict === 'auto_trim') {
        p._applicable = false
        p.status = 'not_applicable'
        p.skip_reason = d.narrative
        p._reason_code = d.reasonCode
        trimCount++
      } else if (d.verdict === 'suggest_trim') {
        // 🔴 只挂建议态，**不碰** `_applicable` / `status` / `skip_reason` ——
        //    重要性类判据是职业判断，落地只能经审计师确认（R6.2 / R6.3）。
        //    改造前这里写向一个从未声明的 `suggestions` ref（`ReferenceError`）、
        //    类型标注引用了全仓不存在的 `TrimSuggestion`、且 `resolveAccountName(p)`
        //    少传 `ctx` 参数；连带 `_suggest*` / `_decision*` 五个字段全无赋值点，
        //    整条建议态链（建议条 → 汇总闸 → 批量确认）从未跑通过。
        p._suggest = true
        p._suggestReasonCode = d.reasonCode
        p._suggestNarrative = d.narrative
        p._decisionAccountName = resolveAccountName(p, ctx as TrimDecisionContext)
        p._decisionEvidence = d.evidence
        suggestCount++
        if (p._applicable) keepCount++
      } else if (p._applicable) {
        keepCount++
      }
    }
    showSmartTrimDialog.value = false
    const parts: string[] = []
    if (trimCount > 0) parts.push(`已自动裁剪 ${trimCount} 个（科目在试算表无数据）`)
    if (suggestCount > 0) parts.push(`产生 ${suggestCount} 条待确认建议（金额低于重要性水平）`)
    if (parts.length > 0) {
      ElMessage.success(`[${scopeLabel}] ${parts.join('；')}，保留 ${keepCount} 个${trimCount > 0 ? '，请检查后保存' : ''}`)
    } else {
      ElMessage.info(`[${scopeLabel}] 无可裁剪程序：所涉科目均有数据、金额不低于重要性水平，或为必须/进行中/底稿已录入`)
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
  let totalSuggest = 0
  const suggestByCycle: Record<string, number> = {}
  const failedCycles: string[] = []
  try {
    for (const cyc of targetCycles) {
      try {
        let procs = await getProcedures(projectId.value, cyc)
        if (!procs || procs.length === 0) {
          procs = await initProcedures(projectId.value, cyc)
        }
        // 🔴 跨循环只落 `auto_trim`；`suggest_trim` 计数后不改状态 ——
        //    建议必须由审计师在对应循环页逐条看判据数值后确认，跨循环批量直接落
        //    等于绕过「重要性类只产生建议」这条红线。
        let cycleSuggest = 0
        const items = (procs || []).map((p: any) => {
          const d = decide(p)
          if (d && d.verdict === 'auto_trim') {
            totalTrim++
            return {
              id: p.id, wp_code: p.wp_code || p.procedure_code,
              status: 'not_applicable', skip_reason: d.narrative, reason_code: d.reasonCode,
            }
          }
          if (d && d.verdict === 'suggest_trim') { cycleSuggest++; totalSuggest++ }
          const keepApplicable = p.status !== 'not_applicable' && p.status !== 'skip'
          if (keepApplicable) totalKeep++
          return { id: p.id, wp_code: p.wp_code || p.procedure_code, status: p.status || 'execute', skip_reason: p.skip_reason || '' }
        }).filter((it: any) => it.id)
        if (cycleSuggest > 0) suggestByCycle[cyc] = cycleSuggest
        if (items.length > 0) {
          // 走 canonical preview/apply（同 saveTrim）；理由码随**同一次**请求提交
          const entries = items.map((it: any) => ({
            kind: 'scope' as const,
            cycle: cyc,
            wp_index_code: it.wp_code || it.id,
            target_status: it.status,
            skip_reason: it.skip_reason || undefined,
            ...(it.reason_code ? { reason_code: it.reason_code } : {}),
          }))
          const pv = await canonicalTrimPreview(projectId.value, entries)
          if (pv?.preview_id) {
            await canonicalTrimApply(projectId.value, entries, pv.preview_id, newRequestId())
          }
        }
      } catch {
        failedCycles.push(cyc)
      }
    }
  } finally {
    loading.value = false
  }

  await loadProcedures() // 刷新当前循环显示

  // 🔴 建议数必须单独告知并指明「在哪里确认」 —— 跨循环路径刻意不落建议态，
  //    若只报「已裁剪 N 个」会让审计师以为处理完了，而重要性维度的建议
  //    （往往是本次最有价值的产出）无声消失。
  let msg = `[${scopeLabel}] 已自动裁剪并保存 ${totalTrim} 个"无数据"科目程序（保留 ${totalKeep} 个）`
  if (totalSuggest > 0) {
    const detail = Object.entries(suggestByCycle)
      .map(([c, n]) => `${c} ${n} 项`).join('、')
    msg += `；另有 ${totalSuggest} 项金额类建议待确认（${detail}），请逐循环打开后确认`
  }
  if (failedCycles.length > 0) msg += `；${failedCycles.join('/')} 循环处理失败`
  if (totalTrim > 0 || totalSuggest > 0) ElMessage.success(msg)
  else ElMessage.info(`[${scopeLabel}] 未发现可裁剪或可建议的程序${failedCycles.length ? `（${failedCycles.join('/')} 失败）` : ''}`)
}

// ═══════════════════════════════════════════════════════════════════════════
// 建议态：逐条确认 / 批量确认 / 逐条驳回（Task 13，R6.1~R6.7 / R7.3）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 建议态在程序行上的持有形态（五个 `_` 前缀字段）。
 *
 * 🔴 建议态**只挂在行上**，不另存一个以 id 为键的 Map —— 两者并存会出现「行上说是
 * 建议、Map 里已删掉」这类不一致，而模板渲染读的是行。这里把「读」（`suggestionOf`）
 * 与「清」（`clearRowSuggestion`）都收在一处，是为了让字段清单只出现一遍：
 * 新增字段时若忘了在清理里跟进，重跑会残留旧建议。
 */
interface RowSuggestion {
  verdict: 'suggest_trim'
  reasonCode: string
  narrative: string
  accountName: string | null
  amount: number | null
}

/**
 * 读取某行的建议态；非建议态返回 `null`（模板以 `v-if="suggestionOf(row)"` 门控）。
 *
 * 🔴 判据是 `_suggest === true` 而不是「有没有 `_suggestReasonCode`」—— 后者在
 * 清理不彻底时会把已改判为保留的行当成建议。
 */
function suggestionOf(row: any): RowSuggestion | null {
  if (!row || row._suggest !== true) return null
  return {
    verdict: 'suggest_trim',
    reasonCode: String(row._suggestReasonCode ?? ''),
    narrative: String(row._suggestNarrative ?? ''),
    accountName: row._decisionAccountName ?? null,
    amount: row._decisionEvidence?.accountAmount ?? null,
  }
}

/** 清空某行的建议态与判据留痕（重跑智能裁剪前逐行调用）。 */
function clearRowSuggestion(row: any) {
  if (!row) return
  row._suggest = false
  row._suggestReasonCode = null
  row._suggestNarrative = null
  row._decisionAccountName = null
  row._decisionEvidence = null
}

/** 当前循环的建议态行（供建议态列与批量确认消费）。 */
const suggestedRows = computed(() => procedures.value.filter(p => p._suggest === true))

/** 建议态统计（建议 / 已确认 / 已驳回），裁剪页与全项目概览共用。 */
const suggestionStats = computed(() => {
  let suggested = 0
  let confirmed = 0
  let rejected = 0
  for (const p of procedures.value) {
    if (p._suggest === true) suggested += 1
    if (p.suggestion_state?.rejected === true) rejected += 1
    // 已确认 = 已落不适用且带机器判据理由码
    if (!p._applicable && isMachineReasonCode(p.suggestion_state?.reason_code)) confirmed += 1
  }
  return { suggested, confirmed, rejected }
})

/**
 * 汇总闸结果（批量确认前的准则要求）。
 *
 * 🔴 只喂**当前仍处建议态**的行 —— 已确认的行不该反复计入，否则闸门会随确认
 * 进度单调收紧、最后恒亮。
 */
/**
 * 实际执行重要性（唯一读取点）。
 *
 * 🔴 读模块级 `trimContext`（`loadTrimContext` 的唯一写入目标）。此处曾读一个
 *    从未声明的 `decisionContext` ⇒ 运行即 ReferenceError，整条汇总闸从未跑通。
 * 🔴 抽成 computed 的用处不是省字：汇总闸与复核视图（Task 20）必须用**同一个**
 *    阈值来源，各写一遍 `?? null` 表达式时，一侧哪天改成读 overall_materiality
 *    都不会有任何检查发现（两处结论分叉，而界面上都显示得出数）。
 */
const performanceMateriality = computed<number | null>(
  () => trimContext.value?.materiality?.performance_materiality ?? null,
)

/**
 * 喂汇总闸的建议项（唯一构造点）。
 *
 * 🔴 汇总闸与复核视图共用本 computed ⇒ 「相同输入下两处逐项相等」（R12.7）由
 *    结构保证，而不是靠两处各写一份映射再期望它们一致。
 */
const suggestedGateItems = computed(() => suggestedRows.value.map(p => ({
  accountName: String(p._decisionAccountName ?? p.wp_code ?? p.procedure_code ?? ''),
  amount: Number(p._decisionEvidence?.accountAmount ?? 0),
  reasonCode: String(p._suggestReasonCode ?? ''),
})))

const aggregateGate = computed(() => evaluateAggregateGate({
  items: suggestedGateItems.value,
  performanceMateriality: performanceMateriality.value,
}))

/** 把一批建议态行落成不适用（走既有 canonical preview → apply，理由码同请求提交）。 */
async function applySuggestions(rows: any[]) {
  if (rows.length === 0) return
  // 🔴 entries 的 wp_index_code 必须与 saveTrim 用同一表达式，否则 canonical key
  //    不一致 → apply 报 409。
  const entries = rows.map(p => ({
    kind: 'scope' as const,
    cycle: activeCycle.value,
    wp_index_code: p.wp_code || p.procedure_code,
    target_status: 'not_applicable',
    skip_reason: p._suggestNarrative || undefined,
    // additive：与 target_status 同一次请求提交（禁两次写入，见 commonApi 注释）
    reason_code: p._suggestReasonCode || undefined,
  }))
  const pv = await canonicalTrimPreview(projectId.value, entries)
  if (!pv?.preview_id) throw new Error('预览失败，未获得 preview 凭证')
  await canonicalTrimApply(projectId.value, entries, pv.preview_id, newRequestId())
}

/** 逐条确认建议。 */
async function confirmSuggestion(row: any) {
  try {
    await applySuggestions([row])
    ElMessage.success(`已确认裁剪：${row.wp_code || row.procedure_code}`)
    await loadProcedures()
    await loadTrimContext([activeCycle.value])
  } catch (e) {
    handleApiError(e, '确认裁剪失败')
  }
}

/**
 * 批量确认建议 —— 先过汇总闸。
 *
 * 闸门 `blocked` 时**只阻断批量、仍允许逐条**：准则要求的是「汇总考虑」，
 * 不是「禁止裁剪」；逐条确认时审计师是在对每个科目单独作判断。
 */
async function confirmAllSuggestions() {
  const rows = suggestedRows.value
  if (rows.length === 0) {
    ElMessage.info('当前循环没有待确认的裁剪建议')
    return
  }
  const gate = aggregateGate.value
  if (gate.blocked) {
    ElMessageBox.alert(
      `${gate.narrative}\n\n仍可对确实不需实施程序的科目逐条确认。`,
      '汇总错报可能超过可容忍水平，已阻断批量确认',
      { type: 'warning', confirmButtonText: '知道了' },
    ).catch(() => {})
    return
  }
  try {
    await ElMessageBox.confirm(
      `${gate.narrative}\n\n将把 ${rows.length} 项建议确认为不适用（理由与判据数值一并留痕）。是否继续？`,
      '批量确认裁剪建议',
      { type: 'warning', confirmButtonText: '确认裁剪', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  loading.value = true
  try {
    await applySuggestions(rows)
    ElMessage.success(`已确认 ${rows.length} 项裁剪建议`)
    await loadProcedures()
    await loadTrimContext([activeCycle.value])
  } catch (e) {
    handleApiError(e, '批量确认失败')
  } finally {
    loading.value = false
  }
}

/** 驳回建议：写 `suggestion_state.rejected`，此后决策内核恒判保留。 */
async function rejectSuggestion(row: any) {
  let reason = ''
  try {
    const r = await ElMessageBox.prompt(
      '驳回后本程序不再被自动建议裁剪。请说明驳回理由（选填，将随驳回一并留痕）：',
      `驳回裁剪建议：${row.wp_code || row.procedure_code}`,
      { confirmButtonText: '驳回', cancelButtonText: '取消', inputType: 'textarea' },
    )
    reason = String(r?.value ?? '').trim()
  } catch {
    return
  }
  try {
    await rejectTrimSuggestions(
      projectId.value,
      activeCycle.value,
      [row.wp_code || row.procedure_code],
      reason || null,
    )
    ElMessage.success('已驳回该裁剪建议')
    await loadProcedures()
    await loadTrimContext([activeCycle.value])
  } catch (e) {
    handleApiError(e, '驳回失败')
  }
}

// ════════════════════════════════════════════════════════════════════════════
// 裁剪充分性复核视图（Task 20，R12.1~R12.7）
// ════════════════════════════════════════════════════════════════════════════
//
// ## 它回答的问题
//
// EQCR 与质控复核合伙人要判断「裁得对不对」，而不是「裁了多少」。故视图的重点是
// 异常组合（高风险科目被裁 / 裁了没写理由 / 完整性判据取平台默认未经确认）与
// 「因金额裁掉的那批加起来是否已达可容忍水平」，而不是漂亮的汇总数字。
//
// 🔴 视图**只读**：`GtTrimAdequacyReview.vue` 不 import 任何 api 模块，改动一律
//    回到本页由有权限的角色执行（R12.6）。定位只发事件，由本页 `onReviewLocate` 落地。
//
// 🔴 统计**不在这里算**，一律走 `buildTrimAdequacyReview`，而它内部：
//      金额汇总 → `evaluateAggregateGate`（与本页 `aggregateGate` 同一函数）
//      理由码分类 → `isMachineReasonCode` / `reasonCodeLabel`（与本页同一真源）
//    本段只做「行 → 复核视图入参」的映射，且科目名解析复用 `resolveAccountName`
//    （与决策内核入参同一个函数）。在这里补一份"顺手的解析"就会让复核视图与裁剪页
//    对同一个程序算出两个金额，而复核者无从知道该信哪个。

const showReviewDrawer = ref(false)
const reviewLoading = ref(false)
/** 定位命中的 wp_code（表格行高亮）；`null` = 无定位 */
const locatedWpCode = ref<string | null>(null)

/**
 * 单行 → 复核视图行。
 *
 * `trimmed` 判据与本页 `decide()` / `progressStats` 逐字一致（`_applicable` 优先、
 * 缺省退回 status），故本页与复核视图的保留/已裁计数天然相等；换成只看 status 会让
 * 有未保存改动时两处数字不一样，而复核者看不出差异来自"未保存"。
 */
function toReviewRow(p: any, cycle: string): ReviewProcedureRow {
  const applicable = p?._applicable !== undefined
    ? Boolean(p._applicable)
    : (p?.status !== 'not_applicable' && p?.status !== 'skip')
  const ctx = trimContext.value
  // 🔴 只有判据上下文覆盖了该循环才解析科目 —— 否则最长匹配会跨循环命中别的科目，
  //    产出一个看起来合理但张冠李戴的金额。未覆盖时如实置 null（视图统计为"金额未知"）。
  const covered = ctx !== null && trimContextCycles.value.has(String(cycle).toUpperCase())
  const accountName = covered ? resolveAccountName(p, ctx as TrimDecisionContext) : null
  const rawAmount = accountName !== null
    ? Number((ctx as TrimDecisionContext).accounts?.[accountName]?.amount)
    : Number.NaN
  const risk = covered ? toRiskInput(((ctx as TrimDecisionContext).risk || {})[accountName ?? '']) : null
  return {
    wpCode: String(p?.wp_code || ''),
    procedureCode: String(p?.procedure_code || ''),
    procedureName: String(p?.procedure_name || ''),
    trimmed: !applicable,
    skipReason: String(p?.skip_reason || ''),
    reasonCode: p?.suggestion_state?.reason_code ?? null,
    rejected: p?.suggestion_state?.rejected === true,
    accountName,
    accountAmount: Number.isFinite(rawAmount) ? rawAmount : null,
    riskLevel: risk?.maxRisk ?? null,
    riskSpecial: risk?.hasSpecial === true,
    // 🔴 风险维度整体不可用（B50 未填）时 riskKnown 恒 false ——「未评估」不得被
    //    当成「非高风险」，否则「高风险被裁」这条异常永不触发，而它是本视图最要紧的一条。
    riskKnown: covered
      && (ctx as TrimDecisionContext).risk_dimension_available === true
      && risk !== null,
  }
}

/** 复核视图入参：当前循环取内存行（与本页统计同源），其余循环取概览已加载的原始行。 */
const reviewCycleInputs = computed<ReviewCycleInput[]>(() => cycles.map((c) => {
  const isActive = c.code === activeCycle.value
  const raw = isActive ? procedures.value : allCyclesData.value[c.code]
  const loaded = Array.isArray(raw)
  return {
    cycle: c.code,
    label: c.label,
    loaded,
    rows: loaded ? (raw as any[]).map(p => toReviewRow(p, c.code)) : [],
    // 🔴 建议态只在本页跑过 `decideTrim` 的循环上存在（挂在内存行的 `_suggest`）。
    //    其余循环消费的是 `getProcedures` 原始行，上面没有该字段；跨循环重跑决策需要
    //    per-cycle 三维上下文，另造一套判据即第二真源。故如实传 null（视图显示
    //    「需打开该循环」而不是 0）。
    suggested: isActive && loaded ? suggestionStats.value.suggested : null,
  }
}))

/** 取平台默认、未经本项目确认的循环；`null` = 覆盖表读取失败（未知，不等于全部默认）。 */
const reviewPlatformDefaults = computed<PlatformDefaultCompletenessCycle[] | null>(() => {
  if (completenessOverrides.value === null) return null
  return completenessScopeRows.value
    .filter(r => r.usingPlatformDefault)
    .map(r => ({
      cycle: r.cycle,
      label: r.label,
      rationale: r.rationale,
      sensitiveByDefault: r.platformDefault,
    }))
})

const trimAdequacyReview = computed(() => buildTrimAdequacyReview({
  cycles: reviewCycleInputs.value,
  platformDefaultCompleteness: reviewPlatformDefaults.value,
  // 与 `aggregateGate` 同一个阈值来源与同一批建议项 ⇒ 两处逐项相等（R12.7）
  performanceMateriality: performanceMateriality.value,
  suggestedGateItems: suggestedGateItems.value,
}))

/** 打开复核视图：懒加载全循环数据 + 完整性覆盖表 + 判据上下文（全部只读）。 */
async function openTrimReview() {
  showReviewDrawer.value = true
  reviewLoading.value = true
  try {
    if (Object.keys(allCyclesData.value).length === 0) await loadAllCyclesData()
    if (completenessOverrides.value === null) await loadCompletenessOverrides()
    if (trimContext.value === null) await loadTrimContext([activeCycle.value])
  } finally {
    reviewLoading.value = false
  }
}

/**
 * 从异常项跳转并定位（R12.5）。
 *
 * 「定位」= 切到该循环 + 把表格过滤到那一条 + 行高亮，而不是只切个 Tab 让复核者
 * 自己在几十行里找。循环级异常（完整性判据）没有具体程序，改为打开对应面板。
 */
async function onReviewLocate(payload: { cycle: string; wpCode: string | null; kind: ReviewAnomalyKind }) {
  if (payload.kind === 'platform_default_completeness' || !payload.wpCode) {
    showReviewDrawer.value = false
    openCompletenessPanel()
    return
  }
  await jumpToCycleFromOverview(payload.cycle)
  showReviewDrawer.value = false
  // 过滤到该条 + 高亮（searchText 是既有的程序名/编号/底稿号搜索，不新建筛选机制）
  statsFilter.value = ''
  searchText.value = payload.wpCode
  locatedWpCode.value = payload.wpCode
}

/** 点击循环行：只切循环，不做定位。 */
async function onReviewJumpCycle(cycle: string) {
  await jumpToCycleFromOverview(cycle)
  showReviewDrawer.value = false
  locatedWpCode.value = null
}

/** 定位命中的行高亮（`row-class-name`）。 */
function procedureRowClass({ row }: { row: any }): string {
  const code = locatedWpCode.value
  if (!code) return ''
  return (row?.wp_code === code || row?.procedure_code === code)
    ? 'gt-proc-row--located'
    : ''
}

// 参照其他项目（需求 2：读源项目当前 wp_code/status 构造 canonical entries，不消费 UUID scheme）
async function applyRef() {
  if (!refProjectId.value) return
  try {
    // 阶段 1：读源项目当前循环程序（wp_code + status）
    let sourceProcs = await getProcedures(refProjectId.value, activeCycle.value)
    if (!sourceProcs || sourceProcs.length === 0) {
      ElMessage.warning('参照项目该循环无程序数据')
      return
    }
    // 阶段 2：以源项目 wp_code+status 为蓝本，按 wp_code 匹配当前项目的程序
    const sourceMap = new Map(sourceProcs.map((p: any) => [p.wp_code || p.procedure_code, p]))
    const entries = procedures.value.map(p => {
      const src = sourceMap.get(p.wp_code || p.procedure_code)
      const applicable = src ? (src.status !== 'not_applicable' && src.status !== 'skip') : p._applicable
      return {
        kind: 'scope' as const,
        cycle: activeCycle.value,
        wp_index_code: p.wp_code || p.procedure_code,
        target_status: applicable ? 'execute' : 'not_applicable',
        skip_reason: applicable ? undefined : (src?.skip_reason || '参照项目裁剪'),
      }
    })
    // 阶段 3：canonical preview/apply
    const preview = await canonicalTrimPreview(projectId.value, entries)
    if (!preview?.preview_id) {
      ElMessage.warning('预览创建失败')
      return
    }
    const result = await canonicalTrimApply(projectId.value, entries, preview.preview_id, newRequestId())
    const applied = result.applied ?? result.changed ?? 0
    ElMessage.success(`已应用参照方案（变更 ${applied} 条）`)
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

// 委派预览统计视图（🔴 后端把计数放在嵌套的 `summary` 对象里，不是顶层）
// 改造前这里读 `preview.target_count ?? preview.targets` / `preview.conflict_count`
// / `preview.assigned_count` —— 三个字段名后端都不存在，故目标数与已分配恒显示
// 「—」、冲突数恒显示 0，而这正是审计师判断本次委派影响面的唯一依据。
// 此处只读 summary 的真实键，读不到就显示「—」（绝不 fallback 到别的字段名，
// 那会让"读错层"以显示错数的形式被掩盖）。
const previewSummary = computed<Record<string, any> | null>(() => {
  const s = delegateWizard.value.preview?.summary
  return s && typeof s === 'object' ? s : null
})

/** 执行人当前负载（preview 侧口径，与 member-loads 端点同源）；null = 未下发 */
const previewAssigneeLoad = computed<number | null>(() => {
  const n = delegateWizard.value.preview?.membership_load?.active_task_count
  return typeof n === 'number' ? n : null
})

// 受影响底稿：后端只给 id 数组（wp_index_ids / wp_ids），审计师看 UUID 无意义
// → 用当前循环已加载的 procedures 把 wp_ids 映射成 wp_code；映射不到时如实显示
// 「N 张（编号待解析）」而不是空列表。
// 🔴 注意 `affected_workpapers` 在平台是同名不同源字段：委派 preview 侧是
// {wp_index_ids, wp_ids} 对象，而调整分录影响预览侧是字符串/对象数组 —— 不得
// 复用 ImpactPreviewPanel / AdjustmentImpactPreview 的渲染组件。
const affectedWorkpapers = computed<{ count: number; codes: string[] }>(() => {
  const aw = delegateWizard.value.preview?.affected_workpapers
  const wpIds: string[] = Array.isArray(aw?.wp_ids) ? aw.wp_ids.map(String) : []
  const idxIds: string[] = Array.isArray(aw?.wp_index_ids) ? aw.wp_index_ids.map(String) : []
  const count = idxIds.length || wpIds.length
  if (!count) return { count: 0, codes: [] }
  const idSet = new Set(wpIds)
  const codes = [...new Set(
    procedures.value
      .filter(p => p.wp_id && idSet.has(String(p.wp_id)))
      .map(p => String(p.wp_code || p.procedure_code || '').trim())
      .filter(Boolean),
  )]
  return { count, codes }
})

function jobStatusLabel(s: string): string {
  const m: Record<string, string> = { pending: '排队中', running: '进行中', succeeded: '成功', failed: '失败' }
  return m[s] || s
}

// ── 智能建议分配（Task 18：底稿粒度建议表，可逐行改/移除 + 负载对比）──
//
// 🔴 这是**加法式**入口，与上方的单执行人 preview → apply 流程并存，不替换它
//    （那条路径是 Task 15/16 已交付并有守卫的现存能力）。
// 🔴 本任务到「表格可见可编辑」为止；应用（按执行人分组多次 preview/apply）归
//    Task 19，故此处只 emit 出编辑后的行集，不发任何写入请求。

const suggestPanel = ref<{
  visible: boolean
  loading: boolean
  result: DelegationSuggestionResult | null
  /** 用户编辑后的行集（组件 emit 上报）；Task 19 的应用入口消费它 */
  editedRows: DelegationSuggestionResult['assignments']
  /**
   * 按执行人分组的待应用载荷（组件算好后 emit 上报，Task 19 逐组消费）。
   *
   * 🔴 类型取组件导出的 `DelegationApplyGroup` 单一真源，不在本文件再镜像一份 ——
   * Task 18 落地时这里镜像成了 `{ assigneeStaffId; wpIndexIds }`，而组件 emit 的是
   * `{ ..., selector: { kind, wp_index_ids } }`：字段名根本不存在，`wpIndexIds.length`
   * 运行时抛 TypeError，且 Volar / vitest / get_diagnostics / HEAD-swap 四层全绿。
   */
  pendingApplyGroups: DelegationApplyGroup[]
  /** 取数阶段的错误（与「算法产不出建议」是两回事，必须可区分） */
  error: string | null
}>({
  visible: false,
  loading: false,
  result: null,
  editedRows: [],
  pendingApplyGroups: [],
  error: null,
})

/**
 * 项目组成员 → `suggestDelegation` 的 `members` 入参。
 *
 * 🔴 `currentLoad` 缺失一律 `null`（不是 0）：0 会被算法读成「这个人很空闲」，
 *    于是把所有工作堆给数据缺失的那个人 —— 恰好是最不该被堆工作的人。
 *    `memberLoadOf` 已按三态返回（null = 未知），此处原样透传。
 */
const suggestionMembers = computed<DelegationMember[]>(() =>
  teamMembers.value.map(m => ({
    staffId: m.staff_id,
    name: m.staff_name,
    seniority: roleSeniority(m.role),
    currentLoad: memberLoadOf(m.staff_id),
  })),
)

/**
 * 取当前循环的底稿粒度目标。
 *
 * `wpIndexId` 来自 `listWorkpapersPaged` 的 `wp_index_id`（**不是** `wp_id`）；
 * `risk` 取 `trimContext.risk[科目名].max_risk`，科目名用与裁剪判据同一个
 * `resolveAccountName`（不另造一套解析，否则同一底稿在两处得到不同风险等级）。
 */
async function buildSuggestionTargets(): Promise<DelegationTarget[]> {
  const env = await listWorkpapersPaged(projectId.value, {
    audit_cycle: activeCycle.value, page: 1, page_size: 100,
  })
  const ctx = trimContext.value
  // 每张底稿的程序行数（权重的 rowCount 项）：按 wp_code 聚合当前循环已加载的程序
  const rowCountByCode = new Map<string, number>()
  for (const p of procedures.value) {
    const code = String(p.wp_code || p.procedure_code || '').trim().toUpperCase()
    if (!code) continue
    rowCountByCode.set(code, (rowCountByCode.get(code) ?? 0) + 1)
  }
  const targets: DelegationTarget[] = []
  for (const item of env.items) {
    const wpIndexId = String(item.wp_index_id || '').trim()
    if (!wpIndexId) continue
    const wpCode = String(item.wp_code || '').trim()
    let risk: DelegationTarget['risk'] = null
    if (ctx) {
      // 用底稿名/编号在判据上下文里定位科目（与裁剪判据同一函数）
      const accountName = resolveAccountName(
        { procedure_name: String(item.wp_name || wpCode) }, ctx,
      )
      const raw = accountName !== null ? (ctx.risk || {})[accountName] : null
      const mx = raw && typeof raw === 'object' ? (raw as any).max_risk : null
      risk = (mx === 'H' || mx === 'M' || mx === 'L') ? mx : null
    }
    targets.push({
      wpIndexId,
      wpCode,
      cycle: String(item.audit_cycle || activeCycle.value),
      risk,
      rowCount: rowCountByCode.get(wpCode.toUpperCase()) ?? 0,
    })
  }
  return targets
}

/** 打开建议分配面板：取数 → 调纯函数 → 渲染。 */
async function openSuggestionPanel() {
  suggestPanel.value.visible = true
  suggestPanel.value.loading = true
  suggestPanel.value.error = null
  suggestPanel.value.result = null
  suggestPanel.value.editedRows = []
  try {
    // 负载与风险判据尽量补齐（失败不阻断：算法会如实标注负载未知 / 未做风险匹配）
    if (memberLoads.value === null) await loadMemberLoads()
    if (trimContext.value === null) await loadTrimContext([activeCycle.value])
    const targets = await buildSuggestionTargets()
    const res = suggestDelegation({
      members: suggestionMembers.value,
      targets,
      // 🔴 风险维度可用性只认后端下发的这一位，前端不自行推断
      riskDimensionAvailable: trimContext.value?.risk_dimension_available === true,
    })
    suggestPanel.value.result = res
    suggestPanel.value.editedRows = [...res.assignments]
  } catch (e: any) {
    // 取数失败与「算法没产出建议」必须可区分：前者是缺陷，后者可能是正常结论
    suggestPanel.value.error = e?.message ? String(e.message) : '建议分配取数失败'
  } finally {
    suggestPanel.value.loading = false
  }
}

/** 组件上报用户编辑后的行集（Task 19 的应用入口消费）。 */
function onSuggestionRowsChange(rows: DelegationSuggestionResult['assignments']) {
  suggestPanel.value.editedRows = rows
}

// ── 建议分配的应用（Task 19 / R11.7 / R14.1）─────────────────────────────
//
// 🔴 写入路径唯一：一律走既有 `previewProcedureDelegation` → `applyProcedureDelegation`
//    两阶段（含 `request_id` 幂等、preview 一次消费、逐 task `assert_sod_distinct`）。
//    本 spec **不新增任何直接写 `procedure_row_tasks` 分配字段的代码路径**，也不借用
//    `assignProcedures`（那是底稿主编层的另一真源，见 twoLayer 守卫）。走捷径会同时
//    绕过后端的版本校验、SOD 双查、history / outbox / policy epoch。
// 🔴 逐组独立：后端 preview/apply 一次只接一个 `assignee_staff_id`，故多执行人必须
//    分组多次调用。**一组失败绝不能影响已成功组** —— 故每组自带 try/catch 与自己的
//    `request_id`，循环体内不 break。

/**
 * 逐组应用状态。
 *
 * 🔴 `no_target` 必须是**独立态**，不得与 `applied` 合并：preview 返回
 * `summary.targets === 0` 时 apply 也会「成功」并返回 `applied: 0`，屏幕上就成了
 * 「委派成功」而实际一行未动 —— 真实库 `procedure_row_tasks` 仅 46 行 / 3 个项目，
 * 多数项目正是这个形态（行任务尚未物化 / 已被粗裁 / applicability 非 execute）。
 * 🔴 409 必须**三分**：`stale` 重新预览有用；`assigned_conflict` 要改冲突策略；
 * `sod` 重新预览一万次也没用（得换复核人）。合成一句「请重新预览」会让审计师做无用功。
 */
type SuggestionApplyStatus =
  | 'pending'
  | 'previewing'
  | 'applying'
  | 'applied'
  | 'no_target'
  | 'stale'
  | 'assigned_conflict'
  | 'sod'
  | 'failed'

interface SuggestionApplyGroupState {
  assigneeStaffId: string
  assigneeName: string
  reviewerStaffId: string | null
  /** 🔴 `wp_index.id` 列表（来自组件 `selector.wp_index_ids`），**不是** `wp_id` */
  wpIndexIds: string[]
  wpCodes: string[]
  status: SuggestionApplyStatus
  targets: number | null
  applied: number
  unchanged: number
  conflict: number
  requestId: string
  message: string
}

const suggestApply = ref<{
  running: boolean
  groups: SuggestionApplyGroupState[]
}>({ running: false, groups: [] })

const SUGGEST_APPLY_LABELS: Record<SuggestionApplyStatus, string> = {
  pending: '待应用',
  previewing: '预览中',
  applying: '应用中',
  applied: '已应用',
  no_target: '无可委派目标',
  stale: '需重新预览',
  assigned_conflict: '目标已被他人分配',
  sod: '职责分离冲突',
  failed: '失败',
}

function suggestApplyStatusLabel(s: SuggestionApplyStatus): string {
  return SUGGEST_APPLY_LABELS[s] ?? s
}

function suggestApplyStatusTagType(s: SuggestionApplyStatus): 'success' | 'warning' | 'danger' | 'info' {
  if (s === 'applied') return 'success'
  if (s === 'stale' || s === 'no_target') return 'warning'
  if (s === 'assigned_conflict' || s === 'sod' || s === 'failed') return 'danger'
  return 'info'
}

/** 逐组结果汇总（成功 / 可重试 / 失败），供面板一眼看清「哪些组白做了、哪些没有」。 */
const suggestApplyTotals = computed(() => {
  const gs = suggestApply.value.groups
  return {
    total: gs.length,
    applied: gs.filter(g => g.status === 'applied').length,
    retryable: gs.filter(g => g.status === 'stale').length,
    blocked: gs.filter(
      g => g.status === 'assigned_conflict' || g.status === 'sod' || g.status === 'failed',
    ).length,
    noTarget: gs.filter(g => g.status === 'no_target').length,
    rows: gs.reduce((s, g) => s + g.applied, 0),
  }
})

/**
 * 409 三分类。
 *
 * 后端 409 有三个来源、指向三种完全不同的处置，不能揉成一句话：
 * - `consume_and_apply` 的 TTL / 一次消费 / 防篡改 / 成员快照，以及 `apply_fn` 的
 *   `target_versions` 复核 → **重新预览该组**即可（`stale`）。
 * - `DelegationConflictError`（`detail.error === 'delegation_conflict'`）→ 目标已被
 *   他人分配，默认原子模式拒绝整批；要改 `conflict_policy` 或 `best_effort`。
 * - `assert_sod_distinct` → 执行人与复核人归一到同一 user，**必须改人**。
 */
function classifyDelegationConflict(e: any): { status: SuggestionApplyStatus; message: string } {
  const detail = e?.response?.data?.detail ?? e?.data?.detail
  const code = typeof detail === 'object' && detail ? String(detail.error ?? '') : ''
  const text = typeof detail === 'string'
    ? detail
    : String((detail && (detail.message ?? detail.detail)) ?? '')
  if (code === 'delegation_conflict') {
    return {
      status: 'assigned_conflict',
      message: (text || '目标任务已被他人分配')
        + '；默认原子模式拒绝整批（本组零写），需改用替换策略或逐张处理',
    }
  }
  if (text.includes('职责分离')) {
    return {
      status: 'sod',
      message: text + '；重新预览无效，请为本组改选操作复核人',
    }
  }
  return {
    status: 'stale',
    message: (text || '预览已失效（过期 / 已消费 / 目标版本或成员变化）')
      + '；本组零写，可单独重新预览并应用，已成功的组不受影响',
  }
}

/**
 * 单组的 preview → apply 请求体。
 *
 * 🔴 **同一个 body 对象**必须同时喂给 preview 与 apply：后端
 * `canonical_request_hash(request_payload)` 在 apply 侧重算并与 preview 存储的 hash
 * 比对（防篡改），两侧只要有一个字段不同就是 409「预览请求已被篡改」。故本函数
 * 每组只调用一次，结果复用。
 * 🔴 `selector.kind` 是 `workpaper` 而非 `cycle` —— 建议分配是**底稿粒度**的，
 * 用 cycle 会把整循环的任务都改成本组执行人，正好抹掉逐行调整的意义。
 */
function suggestionGroupBody(state: SuggestionApplyGroupState) {
  return {
    selector: { kind: 'workpaper' as const, wp_index_ids: state.wpIndexIds },
    assignee_staff_id: state.assigneeStaffId,
    reviewer_staff_id: state.reviewerStaffId || null,
    unassigned_only: false,
  }
}

/**
 * 应用单组：preview → 校验目标数 → apply。
 *
 * 本函数**自吞异常**（把结论写进 `state.status` / `state.message`），使调用方的循环
 * 不会因为某一组 409 而中断后续组。
 */
async function applySuggestionGroup(state: SuggestionApplyGroupState): Promise<void> {
  state.applied = 0
  state.unchanged = 0
  state.conflict = 0
  state.targets = null
  state.message = ''
  if (state.wpIndexIds.length === 0) {
    state.status = 'no_target'
    state.message = '本组无底稿（selector 需非空 wp_index_ids），已跳过'
    return
  }
  // 🔴 形参一律叫 `state`（本页的 SuggestionApplyGroupState，字段 camelCase）；
  //    `g` 只留给组件 emit 的 `DelegationApplyGroup`（字段 selector.wp_index_ids）。
  //    两种形状共用一个变量名，正是 Task 18 宿主把 `selector.wp_index_ids` 写成
  //    `wpIndexIds` 的温床。
  const body = suggestionGroupBody(state)
  try {
    state.status = 'previewing'
    const pv = await previewProcedureDelegation(projectId.value, body)
    // 🔴 目标数读嵌套 `summary.targets`（后端真键）；顶层 `target_count` 不存在，
    //    读它会恒得 undefined 而把「0 个目标」误显示成「—」。
    const targets = Number(pv?.summary?.targets ?? 0)
    state.targets = Number.isFinite(targets) ? targets : 0
    const previewId: string = pv?.preview_id || pv?.preview?.id || ''
    if (!previewId) {
      state.status = 'failed'
      state.message = `未获得可消费的预览凭证（status=${pv?.status ?? '未知'}），请重试`
      return
    }
    if (state.targets === 0) {
      // 有 preview 也不 apply：apply 会返回 applied=0 并被读成"成功"
      state.status = 'no_target'
      state.message = '预览目标数为 0：本组底稿的行任务尚未物化，或已被粗裁为不适用，'
        + '或 applicability 非 execute。请先在底稿内生成程序行任务后重试'
      return
    }
    state.status = 'applying'
    state.requestId = newRequestId()
    const res = await applyProcedureDelegation(
      projectId.value, previewId, state.requestId, body,
    )
    state.applied = Number(res?.applied ?? 0)
    state.unchanged = Number(res?.unchanged ?? 0)
    state.conflict = Number(res?.conflict ?? 0)
    state.status = 'applied'
    state.message = `已应用 ${state.applied} 项，未变更 ${state.unchanged} 项`
  } catch (e: any) {
    const status = e?.response?.status || e?.status || 0
    if (status === 409) {
      const c = classifyDelegationConflict(e)
      state.status = c.status
      state.message = c.message
      return
    }
    state.status = 'failed'
    const detail = e?.response?.data?.detail ?? e?.data?.detail
    const text = typeof detail === 'string' ? detail : (detail?.message ?? e?.message ?? '')
    state.message = text ? String(text) : `请求失败（HTTP ${status || '网络不通'}）`
  }
}

/**
 * 组件请求应用建议分配：按执行人分组逐组走既有两阶段。
 *
 * 🔴 逐组**顺序**执行而非 `Promise.all`：并行会让多组同时锁同一批
 * `procedure_row_tasks` 行（`resolve_targets(..., for_update=True)`），先提交的那组
 * 改变 `lock_version` ⇒ 其余组全部 409「目标任务版本已变化」。顺序执行时后一组的
 * preview 拿到的是前一组落库后的版本，不会自相冲突。
 */
async function onSuggestionApplyRequest(
  groups: DelegationApplyGroup[],
  rows: DelegationSuggestionResult['assignments'],
) {
  suggestPanel.value.editedRows = rows
  suggestPanel.value.pendingApplyGroups = groups
  if (suggestApply.value.running) {
    ElMessage.warning('上一次应用尚未完成，请等待逐组结果')
    return
  }
  if (!groups.length) {
    ElMessage.warning('没有可应用的分配行')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将按执行人分成 ${groups.length} 组、共 `
      + `${groups.reduce((s, g) => s + g.selector.wp_index_ids.length, 0)} 张底稿，`
      + '逐组走「预览 → 应用」两阶段委派。'
      + '每组独立提交，某组失败不影响其他组。是否继续？',
      '应用建议分配',
      { type: 'warning', confirmButtonText: '逐组应用', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  // 🔴 `wpIndexIds` 取组件的 `selector.wp_index_ids`（snake_case，与后端
  //    `DelegationSelector.wp_index_ids` 同名同源）。组件并**没有** `wpIndexIds`
  //    这个字段 —— 读它会得 undefined，`.length` 直接抛 TypeError，而 Volar /
  //    vitest / get_diagnostics 四层全绿（本任务落地时实测如此）。
  suggestApply.value.groups = groups.map(g => ({
    assigneeStaffId: g.assigneeStaffId,
    assigneeName: g.assigneeName,
    reviewerStaffId: g.reviewerStaffId,
    wpIndexIds: [...g.selector.wp_index_ids],
    wpCodes: [...g.wpCodes],
    status: 'pending' as SuggestionApplyStatus,
    targets: null,
    applied: 0,
    unchanged: 0,
    conflict: 0,
    requestId: '',
    message: '',
  }))
  suggestApply.value.running = true
  try {
    for (const state of suggestApply.value.groups) {
      await applySuggestionGroup(state)
    }
  } finally {
    suggestApply.value.running = false
  }
  const t = suggestApplyTotals.value
  if (t.applied === t.total) {
    ElMessage.success(`逐组应用完成：${t.total} 组全部成功，共应用 ${t.rows} 项`)
  } else {
    ElMessage.warning(
      `逐组应用完成：成功 ${t.applied} 组 / 需重新预览 ${t.retryable} 组 / `
      + `无目标 ${t.noTarget} 组 / 受阻 ${t.blocked} 组。已成功的组无需重做`,
    )
  }
  // 负载与程序状态都变了 → 两处同源刷新（负载读后端唯一口径，不前端自算）
  await Promise.all([loadMemberLoads(), loadProcedures()])
}

/**
 * 单组重试（409 / 失败后）。
 *
 * 🔴 只重跑这一组，**不重建 `groups` 数组** —— 重建会把已成功组的 `applied`
 * 计数抹成 0，屏幕上看起来像「上次全白做了」，审计师会去重复委派。
 */
async function retrySuggestionGroup(index: number) {
  const state = suggestApply.value.groups[index]
  if (!state || suggestApply.value.running) return
  suggestApply.value.running = true
  try {
    await applySuggestionGroup(state)
  } finally {
    suggestApply.value.running = false
  }
  if (state.status === 'applied') {
    ElMessage.success(`${state.assigneeName}：已应用 ${state.applied} 项`)
    await Promise.all([loadMemberLoads(), loadProcedures()])
  } else {
    ElMessage.warning(`${state.assigneeName}：${suggestApplyStatusLabel(state.status)}`)
  }
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
  // SOD 自审防护：程序执行人不得同时为操作复核人。
  // 🔴 这里只是**即时提示**，不是校验真源 —— 后端 `assert_sod_distinct` 在
  // preview 与 apply 两侧**逐 task 双查**（`procedure_delegation_service.py`），
  // 即便绕过本前端判断也无法落库。故此处不得改成"前端放行即视为合规"，
  // 也不要因为"后端已经查了"而删掉它（删掉会让审计师点了预览才知道选错人）。
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
  // 负载在进入界面时即可用（不依赖先打开全项目概览抽屉）；失败保持"负载未知"
  loadMemberLoads()
  // B50 填写状态（风险维度可用性）；失败保持"未知"故徽标不显示
  loadB50Status()
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

/* B50 填写状态条（风险维度可用性提示；spec procedure-trimming-and-delegation-intelligence Task 4）*/
.gt-proc-b50-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 10px; margin-bottom: 10px;
  border-radius: 4px; font-size: 12px;
  border-left: 3px solid var(--el-color-info);
  background: var(--el-color-info-light-9);
}
.gt-proc-b50-bar.is-partial {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
.gt-proc-b50-bar.is-completed {
  border-left-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}
.gt-proc-b50-counts { color: var(--gt-color-text-secondary); }
.gt-proc-b50-hint { color: var(--gt-color-text-tertiary); }

/* 判据维度降级标注（R4.1 / R4.2 / R4.5；spec Task 22 独立成宿主）──────────────
   琥珀色左边线 = 平台既有的「方法论/告知类上下文」视觉约定。此处刻意与建议态条
   区分：它说的不是「有几条建议」而是「有一个法定判据维度这次没做」，两者混排会
   让后者被读成前者的脚注。 */
.gt-proc-degrade-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 10px; margin-bottom: 10px;
  border-left: 3px solid var(--el-color-warning);
  border-radius: 3px;
  background: var(--el-color-warning-light-9);
  font-size: 12px;
}
.gt-proc-degrade-bar__label {
  color: var(--gt-color-text-secondary);
  font-weight: 600;
}

/* 完整性敏感清单状态条与逐循环覆盖面板（Task 14 / R5.5~R5.7）*/
.gt-proc-cscope-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 10px; margin-bottom: 10px;
  border-radius: 4px; font-size: 12px;
  border-left: 3px solid var(--el-color-success);
  background: var(--el-color-success-light-9);
}
.gt-proc-cscope-bar.is-default {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
.gt-proc-cscope-bar.is-unknown {
  border-left-color: var(--el-color-info);
  background: var(--el-color-info-light-9);
}
.gt-proc-cscope-unknown { color: var(--gt-color-text-tertiary); }
.gt-proc-cscope-notice { color: var(--el-color-warning); }
.gt-proc-cscope-ok { color: var(--gt-color-text-secondary); }
.gt-proc-cscope-reason { color: var(--gt-color-text-primary); margin-bottom: 2px; }
.gt-proc-cscope-rationale { color: var(--gt-color-text-tertiary); font-size: 12px; line-height: 1.6; }
.gt-proc-cscope-trace { color: var(--gt-color-text-secondary); font-size: 12px; }
.gt-proc-cscope-foot {
  margin-top: 10px; font-size: 12px; color: var(--gt-color-text-tertiary); text-align: right;
}

/* 附注反向联动面板（Task 21 / R13.1~R13.4）
   🔴 模板引用了这些类，缺样式**不报错也不影响渲染** —— get_diagnostics 与 vitest 全查不出，
   只表现为五个分组视觉上完全一样（Task 14 已在本文件踩过一次）。 */
.gt-proc-nlink__bar {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 6px 10px; margin-bottom: 10px;
  font-size: 12px; color: var(--gt-color-text-secondary);
  border-left: 3px solid var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.gt-proc-nlink__group { margin-bottom: 14px; }
.gt-proc-nlink__title {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 5px;
}
.gt-proc-nlink__hint { font-size: 12px; color: var(--gt-color-text-tertiary); line-height: 1.6; }
.gt-proc-nlink__why { font-size: 12px; color: var(--gt-color-text-secondary); line-height: 1.6; }

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
.gt-proc-wizard-affected { margin-top: 10px; }
.gt-proc-affected-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.gt-proc-load-unknown { color: var(--gt-color-text-secondary, #909399); }

/* 建议分配逐组应用结果（Task 19）
   —— 模板引用了却没写样式属于「只有浏览器能暴露」的一类：scoped CSS 缺类不报错、
   渲染照旧，get_diagnostics 与 vitest 全查不出，表现为各态没有视觉分层。 */
.gt-proc-sugapply { margin-top: 14px; }
.gt-proc-sugapply__title {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 700; margin-bottom: 8px;
  color: var(--gt-color-text-primary);
}

/* 自定义模板上传区 */
.gt-proc-custom-template-area {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.gt-proc-custom-template-or {
  font-size: 12px; color: var(--gt-color-text-tertiary); font-style: italic;
}

/* 复核视图定位命中的行（Task 20 / R12.5）
   —— 「定位」必须在表格上看得见，只切 Tab + 过滤而不高亮时，复核者仍要自己确认
   到底命中了哪一行。scoped 下 el-table 的行类要经 :deep 才生效。 */
.gt-procedure :deep(.gt-proc-row--located) > td {
  background: var(--el-color-warning-light-8) !important;
}
</style>
