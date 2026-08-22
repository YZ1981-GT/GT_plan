<template>
  <div class="gt-report-view gt-fade-in" :class="{ 'gt-fullscreen': rvFullscreen }">
    <!-- 固定顶部区域 -->
    <div class="gt-rv-sticky-header">
      <!-- 页面横幅 -->
      <GtPageHeader title="财务报表" :show-sync-status="true" @back="goBack">
        <GtInfoBar
          :show-unit="true"
          :show-year="true"
          :show-template="true"
          :show-scope="true"
          :unit-value="selectedProjectId"
          :year-value="selectedYear"
          :template-value="selectedTemplateType"
          :scope-label="scopeLabel"
          :badges="[
            { label: '单位', value: displayPrefs.unitSuffix },
          ]"
          @unit-change="onProjectChange"
          @year-change="onYearChange"
          @template-change="onTemplateTypeChange"
        >
        </GtInfoBar>
        <template #actions>
          <GtToolbar
            :show-copy="true"
            :show-fullscreen="true"
            :is-fullscreen="rvFullscreen"
            :show-export="false"
            @copy="copyReportTable"
            @fullscreen="toggleRvFullscreen()"
          >
            <template #left>
              <el-radio-group v-model="reportMode" size="small" @change="fetchReport" class="gt-rv-mode-radio">
                <el-radio-button value="audited">已审</el-radio-button>
                <el-radio-button value="unadjusted">未审</el-radio-button>
                <el-radio-button value="compare">对比</el-radio-button>
              </el-radio-group>
              <el-button v-if="!isEqcrRole" size="small" type="primary" @click="onGenerate" :loading="genLoading">刷新</el-button>
              <el-button size="small" @click="_onConsistencyCheckWrapper" :loading="checkLoading">审核</el-button>
            </template>
            <template #right-extra>
              <el-dropdown trigger="click" size="small">
                <el-button size="small">📤 导入导出</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="onExportExcel">导出当前表(Excel)</el-dropdown-item>
                    <el-dropdown-item @click="onExportAllExcel">全部导出 — 已审数</el-dropdown-item>
                    <el-dropdown-item @click="onExportAllUnadjusted">全部导出 — 未审数</el-dropdown-item>
                    <el-dropdown-item divided @click="showReportImport = true">导入(Excel)</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" @click="showFormulaManager = true">📐 公式管理</el-button>
              <el-button size="small" type="primary" plain @click="openAiWithContext">🤖 AI</el-button>
              <el-button
                size="small"
                circle
                :type="showRvGuide ? 'primary' : 'default'"
                @click="showRvGuide = !showRvGuide"
                title="操作指南"
              >
                ?
              </el-button>
              <el-dropdown trigger="click" size="small">
                <el-button size="small">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="onEditConfig">
                      编辑结构
                      <span style="font-size:11px;color:var(--el-color-warning);margin-left:4px">⚠</span>
                    </el-dropdown-item>
                    <el-dropdown-item @click="showMappingDialog = true">转换规则（国企版↔上市版）</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </GtToolbar>
        </template>
      </GtPageHeader>

      <!-- 工作流进度条 -->
      <WorkflowProgress
        :project-id="projectId"
        :year="selectedYear"
        @step-action="onWorkflowStepAction"
        @next-action="onWorkflowNext"
      />

      <!-- 归档横幅 -->
      <ArchivedBanner />
      <ConsolLockedBanner />

      <!-- 跨模块冲突 banner（spec global-refinement-v3 Task 7.5） -->
      <ConflictBanner :project-id="projectId" @view="conflictPanelVisible = true" />
      <ConflictResolutionPanel
        v-model="conflictPanelVisible"
        :project-id="projectId"
        @resolved="onConflictResolved"
      />

      <!-- F29: 报表平衡检查结果（紧凑单行可展开） -->
      <div v-if="balanceCheckResult" class="gt-rv-balance-bar" :class="'gt-rv-balance-bar--' + balanceCheckResult.status">
        <span class="gt-rv-balance-bar__icon">{{ balanceCheckResult.status === 'passed' ? '✅' : '❌' }}</span>
        <span class="gt-rv-balance-bar__text">
          {{ balanceCheckResult.status === 'passed' ? '报表平衡检查通过（7/7）' : `报表平衡检查有 ${balanceCheckResult.checks?.filter(c => !c.passed).length || 0} 项差异` }}
        </span>
        <el-button v-if="balanceCheckResult.checks?.some(c => !c.passed)" text size="small" type="primary" @click="rvBalanceExpanded = !rvBalanceExpanded">
          {{ rvBalanceExpanded ? '收起' : '展开明细' }}
        </el-button>
        <el-button text size="small" @click="balanceCheckResult = null" style="margin-left: auto; padding: 0;">✕</el-button>
      </div>
      <transition name="el-zoom-in-top">
        <div v-if="balanceCheckResult && rvBalanceExpanded && balanceCheckResult.checks?.some(c => !c.passed)" class="gt-rv-balance-detail">
          <div
            v-for="(chk, idx) in balanceCheckResult.checks.filter(c => !c.passed)"
            :key="idx"
            class="gt-rv-balance-detail__row"
            @click="scrollToReportRow(chk.name)"
          >
            <span style="color: var(--el-color-danger)">✗</span>
            <span style="flex: 1">{{ chk.name }}</span>
            <span style="color: var(--el-text-color-secondary); font-size: 12px">期望 {{ chk.expected }}，实际 {{ chk.actual }}，差 {{ chk.diff }}</span>
            <el-button text size="small" type="primary" style="padding: 0">定位 →</el-button>
          </div>
        </div>
      </transition>

      <!-- Sprint 4：StaleIndicator 统一组件 + 横幅（三条互斥：stale > staleRefresh > reportStale） -->
      <div v-if="stale.isStale.value" class="gt-stale-banner">
        <StaleIndicator :stale="true" tooltip="上游数据已变更" />
        <span class="gt-stale-text">
          上游数据已变更，当前报表可能基于旧试算表（{{ stale.staleCount.value }} 张底稿待重算）
        </span>
        <el-button size="small" type="primary" :loading="stale.loading.value" @click="onStaleRecalc">
          🔄 点击重算
        </el-button>
      </div>

      <!-- useStaleRefresh：上游变更事件横幅 -->
      <div v-else-if="staleRefresh.isStale.value" class="gt-stale-banner">
        <StaleIndicator :stale="true" tooltip="上游数据已变更" />
        <span class="gt-stale-text">上游数据已变更，建议重新加载报表</span>
        <el-button size="small" type="primary" @click="staleRefresh.refresh()">刷新数据</el-button>
      </div>

      <!-- US-2：底稿数据更新 → 报表 stale 黄色横幅 -->
      <el-alert
        v-else-if="showReportStaleBanner"
        title="底稿数据已更新"
        :description="`${reportStaleRows.length} 个报表行受影响，点击刷新获取最新数据`"
        type="warning"
        show-icon
        :closable="true"
        style="margin-bottom: 8px"
        @close="showReportStaleBanner = false"
      >
        <template #default>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span>{{ reportStaleRows.length }} 个报表行受影响，点击刷新获取最新数据</span>
            <el-button size="small" type="warning" @click="onReportStaleRefresh">🔄 刷新报表</el-button>
          </div>
        </template>
      </el-alert>

      <!-- Tab 切换 -->
      <el-tabs v-model="activeTab" @tab-change="onTabChange" stretch>
        <el-tab-pane label="资产负债表" name="balance_sheet" />
        <el-tab-pane label="利润表" name="income_statement" />
        <el-tab-pane label="现金流量表" name="cash_flow_statement" />
        <el-tab-pane label="权益变动表" name="equity_statement" />
        <el-tab-pane label="现金流附表" name="cash_flow_supplement" />
        <el-tab-pane label="减值准备表" name="impairment_provision" />
        <el-tab-pane label="⚖️跨表核对" name="cross_check" />
        <el-tab-pane label="📊多年对比" name="multi_year_compare" />
        <el-tab-pane label="📈分析" name="report_analysis" />
      </el-tabs>
    </div>

    <!-- 报表使用说明抽屉（右侧，边看边操作） -->
    <el-drawer
      v-model="showRvGuide"
      title="📖 财务报表功能介绍与操作指南"
      direction="rtl"
      size="480px"
      :append-to-body="true"
      :close-on-press-escape="true"
    >
      <div class="gt-rv-guide-panel__body">

          <!-- 功能定位 -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">一、功能定位</h4>
            <p class="gt-rv-guide-section__text">
              财务报表模块是审计数据的<b>最终呈现层</b>——将试算表各科目审定数按报表行次公式汇总为6张标准财务报表（资产负债表/利润表/现金流量表/所有者权益变动表/现金流附表/资产减值准备表），
              是审计报告的核心附表。报表数据<b>自动从试算表审定数经公式驱动计算</b>，无需手工填列；调整分录变更后刷新即自动重算。
              同时提供跨表核对（7条平衡等式）、多年度对比（趋势分析）、报表分析（A2-1/A2-2比率试算）三个增值功能，辅助审计判断。
            </p>
          </div>

          <!-- 工具栏按钮 -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">二、工具栏按钮功能详解</h4>
            <div class="gt-rv-guide-btn-list">
              <div class="gt-rv-guide-btn-item">
                <div class="gt-rv-guide-btn-item__head">
                  <span class="gt-rv-guide-btn-item__badge gt-rv-guide-btn-item__badge--primary">📊</span>
                  <b>已审 / 未审 / 对比</b>
                </div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p><b>已审</b>：显示审定金额（=未审数+AJE+RJE），是最终对外出具的数。</p>
                  <p><b>未审</b>：显示未经审计调整的原始金额（来自试算表未审数），便于对照客户原始账面。</p>
                  <p><b>对比</b>：同时展示未审/调整影响/已审/上年审定/变动额/变动率六列，一表纵览全链路。变动率超过20%的行自动红色标记，提示审计师关注异常波动。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item">
                <div class="gt-rv-guide-btn-item__head">
                  <span class="gt-rv-guide-btn-item__badge gt-rv-guide-btn-item__badge--success">🔄</span>
                  <b>刷新（生成报表）</b>
                </div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p><b>功能</b>：从试算表审定数重新按公式驱动计算全部报表行次金额。底稿编制/调整分录变更后须点此刷新才能反映最新审定数。</p>
                  <p><b>计算逻辑</b>：每行根据 report_config 的 formula（如 <code>TB('1001','期末余额')+TB('1002','期末余额')</code>）从试算表取数汇总。合计行按父子行次自动求和。</p>
                  <p><b>注意</b>：EQCR技术复核人角色下该按钮隐藏（只读复核不改数据）；报表锁定/归档后刷新禁用。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item">
                <div class="gt-rv-guide-btn-item__head">
                  <span class="gt-rv-guide-btn-item__badge gt-rv-guide-btn-item__badge--info">✅</span>
                  <b>审核（一致性校验）</b>
                </div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p><b>功能</b>：执行7条报表间平衡等式检查，是报表出具前的必查项。</p>
                  <p><b>等式示例</b>：资产总计=负债+所有者权益总计、利润总额−所得税费用=净利润、期末现金=期初+经营+投资+筹资净额、所有者权益各项变动净额=期末−期初。</p>
                  <p><b>结果</b>：弹窗逐条展示通过/未通过（含期望值/实际值/差异金额），未通过项可点击定位到对应报表行。全部通过后顶部显示绿色「报表平衡检查通过」横幅。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head">
                  <b>📤 全部导出 / 📥 导入 / 📐 公式</b>
                </div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p><b>全部导出</b>：将6张报表一次性导出为单个格式化xlsx文件（每张报表一个sheet），适合归档或交付客户。</p>
                  <p><b>导入</b>：上传xlsx覆盖报表数据（适用于客户直接提供格式化报表或手工填列权益变动表/现金流量表）。</p>
                  <p><b>公式</b>：打开公式管理中心，查看/编辑各报表行的取数公式（TB/SUM_TB/ROW引用）、逻辑审核规则、合理性提示。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head">
                  <b>更多 ▾（编辑结构/转换规则/AI对话）</b>
                </div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p><b>编辑结构</b>：修改报表行次定义（增/删/改行名、调整缩进层级、设置合计行、修改取数公式）。适合因企业特殊性需要调整报表格式的场景。</p>
                  <p><b>转换规则</b>：管理「国企版↔上市版」报表项目的映射关系，确认后系统按规则自动转换。支持一键预设和手动调整。</p>
                  <p><b>AI对话</b>：打开AI文档对话面板，可针对当前报表数据提问（如"为什么货币资金比上年增长50%"、"应收账款周转率是多少"）。</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 9个Tab -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">三、报表Tab说明</h4>
            <div class="gt-rv-guide-grid">
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">📋</div>
                <div class="gt-rv-guide-card__name">资产负债表</div>
                <div class="gt-rv-guide-card__desc">反映企业特定日期财务状况。资产=负债+所有者权益（平衡等式检查的核心对象）。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">📈</div>
                <div class="gt-rv-guide-card__name">利润表</div>
                <div class="gt-rv-guide-card__desc">反映会计期间经营成果。收入−成本−费用−税=净利润。与资产负债表未分配利润联动。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">💰</div>
                <div class="gt-rv-guide-card__name">现金流量表</div>
                <div class="gt-rv-guide-card__desc">反映现金流入流出，分经营/投资/筹资三大类。期末现金须与资产负债表货币资金一致。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">🔄</div>
                <div class="gt-rv-guide-card__name">权益变动表</div>
                <div class="gt-rv-guide-card__desc">矩阵表：横轴为权益项目（实收资本/资本公积/盈余公积/未分配利润等），纵轴为变动原因。期末余额须与资产负债表所有者权益各项一致。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">📑</div>
                <div class="gt-rv-guide-card__name">现金流附表</div>
                <div class="gt-rv-guide-card__desc">用间接法从净利润调节到经营活动现金净额（加折旧/减存货增加等），与直接法现金流量表互相印证。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">⚠️</div>
                <div class="gt-rv-guide-card__name">减值准备表</div>
                <div class="gt-rv-guide-card__desc">列示各类资产减值准备的期初/本期增加(计提)/本期减少(转回、转销)/期末变动，矩阵表结构。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">⚖️</div>
                <div class="gt-rv-guide-card__name">跨表核对</div>
                <div class="gt-rv-guide-card__desc">7条关键平衡等式自动计算+通过/失败状态标记。差异行可点击定位到对应报表Tab。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">📊</div>
                <div class="gt-rv-guide-card__name">多年度对比</div>
                <div class="gt-rv-guide-card__desc">纵向展示多个年度同一报表行次的数据趋势，辅助识别异常波动和趋势性变化。</div>
              </div>
              <div class="gt-rv-guide-card">
                <div class="gt-rv-guide-card__icon">📈</div>
                <div class="gt-rv-guide-card__name">报表分析</div>
                <div class="gt-rv-guide-card__desc">自动计算常用审计比率（流动比率/速动比率/资产负债率/毛利率等），对应A2-1/A2-2分析性程序底稿。</div>
              </div>
            </div>
          </div>

          <!-- 表格交互 -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">四、表格交互操作</h4>
            <div class="gt-rv-guide-btn-list">
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>点击项目名 → 穿透科目构成</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>点击报表行的「项目」名称，弹出该行由哪些科目构成（如"货币资金"=1001库存现金+1002银行存款+1012其他货币资金），含各科目审定金额和占比。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>点击金额 → 本期金额穿透</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>点击本期金额单元格，弹出该行取数公式的逐项展开（每个TB()函数对应科目及其审定数）。悬停金额可看公式表达式。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>右键菜单（8项功能）</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>在任意单元格右键弹出：📊查看穿透 / 📝跳转附注 / 🔎附注引用我 / 📋打开对应底稿 / 🔗查看调整明细 / 🔗查看合并明细(合并报表) / 🔍查看公式来源 / 🔍数字溯源。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>📝 附注跳转按钮</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>项目名称后的📝按钮可直接跳转到该报表行对应的附注章节（如"货币资金"→五、1），在附注模块查看/编辑该科目披露内容。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>Ctrl+F 表内搜索 / 选区求和</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>按 Ctrl+F 打开表内搜索栏，按关键词高亮匹配行并支持前后跳转。选中多个金额单元格后底部状态栏显示求和/均值/计数。</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 操作流程 -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">五、报表生成完整流程</h4>
            <div class="gt-rv-guide-steps">
              <div class="gt-rv-guide-step">
                <span class="gt-rv-guide-step__num">1</span>
                <div class="gt-rv-guide-step__content">
                  <b>确认试算表审定数完整</b>
                  <span>在试算表页面确认全量重算已完成、一致性校验通过、数据质量检查无异常。试算表审定数是报表的唯一数据源。</span>
                </div>
              </div>
              <div class="gt-rv-guide-step">
                <span class="gt-rv-guide-step__num">2</span>
                <div class="gt-rv-guide-step__content">
                  <b>点击「刷新」生成报表</b>
                  <span>系统自动按报表行次公式从试算表取数，计算全部6张报表。首次生成约需几秒。完成后表格自动刷新显示最新数据。</span>
                </div>
              </div>
              <div class="gt-rv-guide-step">
                <span class="gt-rv-guide-step__num">3</span>
                <div class="gt-rv-guide-step__content">
                  <b>点击「审核」执行平衡检查</b>
                  <span>7条等式逐条校验。全部通过=报表内部自洽可出具。存在差异=需回溯底稿/调整分录排查原因（点击差异项可直接定位）。</span>
                </div>
              </div>
              <div class="gt-rv-guide-step">
                <span class="gt-rv-guide-step__num">4</span>
                <div class="gt-rv-guide-step__content">
                  <b>差异排查与修正</b>
                  <span>若有不平衡，通过右键"查看穿透"/"打开对应底稿"/"查看调整明细"追溯根因。修正后回到试算表全量重算→报表刷新→再次审核。</span>
                </div>
              </div>
              <div class="gt-rv-guide-step">
                <span class="gt-rv-guide-step__num">5</span>
                <div class="gt-rv-guide-step__content">
                  <b>导出交付</b>
                  <span>全部平衡后点击「全部导出」生成归档xlsx。导出前系统自动提示未通过的校验项（若有）。导出文件可直接作为审计报告附表使用。</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 注意事项 -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">六、注意事项</h4>
            <ul class="gt-rv-guide-notes">
              <li>⚠️ 报表数据<b>不可直接编辑</b>——所有金额由公式从试算表审定数自动计算。如需修改某行金额，应回到底稿编制调整分录→试算表重算→报表刷新。</li>
              <li>⚠️ 项目<b>归档后</b>报表只读，刷新/导入/编辑结构按钮全部禁用。</li>
              <li>⚠️ <b>合并报表</b>需先在合并工作底稿模块完成抵消分录编制和合并重算，再来报表页查看合并口径数据。</li>
              <li>⚠️ <b>权益变动表</b>为矩阵表，部分行可能需要通过导入xlsx手工填列（如其他综合收益明细、设定受益计划变动等非公式驱动行）。</li>
              <li>⚠️ 对比模式下<b>变动率超过20%</b>的行自动红色标记，审计师须在分析性程序底稿(A2-1/A2-2)或附注中解释重大波动原因。</li>
              <li>⚠️ 上方黄色横幅「底稿数据已更新 / 上游数据已变更」提示报表可能基于旧数据——点击横幅内🔄按钮即可刷新。</li>
              <li>⚠️ <b>搜索快捷键</b>：Ctrl+F 打开表内搜索 / Esc 关闭。</li>
            </ul>
          </div>

          <!-- 快捷键 -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">七、快捷键与常用操作速查</h4>
            <div class="gt-rv-guide-shortcut-table">
              <div class="gt-rv-guide-shortcut-row gt-rv-guide-shortcut-row--header">
                <span>操作</span><span>说明</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span><kbd>Ctrl</kbd>+<kbd>F</kbd></span><span>表内搜索（关键词高亮+前后跳转）</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span><kbd>Esc</kbd></span><span>关闭搜索栏 / 关闭弹窗</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span>单击项目名</span><span>穿透该行科目构成明细</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span>单击金额</span><span>穿透公式逐项展开（各科目审定数）</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span>右键任意单元格</span><span>弹出8项功能菜单</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span>📝 图标</span><span>跳转对应附注章节</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span>选中多格</span><span>底部状态栏求和/均值/计数</span>
              </div>
              <div class="gt-rv-guide-shortcut-row">
                <span>切换 已审/未审/对比</span><span>同一报表三种视角一键切换</span>
              </div>
            </div>
          </div>

          <!-- 常见问题 -->
          <div class="gt-rv-guide-section">
            <h4 class="gt-rv-guide-section__title">八、常见问题速查</h4>
            <div class="gt-rv-guide-btn-list">
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>Q：报表全是0怎么办？</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>A：先确认试算表有数据（科目映射→全量重算→有审定额），再回报表页点「🔄 刷新」。若试算表也空，需先导入账套余额表。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>Q：资产负债不平衡怎么排查？</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>A：点「✅ 审核」看差异金额→点差异行定位→右键"查看穿透"看构成科目→到试算表/底稿追溯。常见原因：调整分录借贷不平、科目映射遗漏、权益类科目未导入期末余额。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>Q：刷新后数据没变？</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>A：报表取数来自试算表审定数。如果只改了底稿调整分录但没回试算表全量重算，审定数不变报表也不变。流程：底稿编AJE→试算表「全量重算」→报表「刷新」。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>Q：想手工改某行金额？</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>A：报表金额由公式驱动不可直接编辑。如需调整：通过「更多→编辑结构」修改该行取数公式，或在底稿编制对应科目调整分录后重算。权益变动表/现金流量表可通过「导入」直接覆盖。</p>
                </div>
              </div>
              <div class="gt-rv-guide-btn-item gt-rv-guide-btn-item--compact">
                <div class="gt-rv-guide-btn-item__head"><b>Q：导出的xlsx和页面上看到的一样吗？</b></div>
                <div class="gt-rv-guide-btn-item__desc">
                  <p>A：完全一致。导出按当前选中视图（已审/未审/对比）格式化为6张sheet，含表头行次缩进。可直接作为审计报告附表或交付客户。</p>
                </div>
              </div>
            </div>
          </div>

        </div>
    </el-drawer>

    <!-- 可滚动的表格区域 -->
    <div class="gt-rv-table-area">

    <!-- 空数据引导提示 -->
    <GtEmpty
      v-if="!loading && rows.length === 0 && !isTracing"
      title="报表暂无数据"
      description="请先导入账套数据并执行刷新"
      icon="📊"
      action-text="去导入"
      style="margin: 40px 0"
      @action="router.push(`/projects/${projectId}/ledger`)"
    />

    <!-- 溯源返回浮动条 -->
    <div v-if="isTracing" class="gt-rv-trace-bar">
      <span>📍 正在查看溯源数据 — {{ activeTabLabel }}</span>
      <el-button size="small" type="primary" round @click="onTraceReturn">↩ 返回审核</el-button>
    </div>

    <!-- 搜索栏（Ctrl+F 触发，表格上方） -->
    <TableSearchBar
      :is-visible="rvSearch.isVisible.value"
      :keyword="rvSearch.keyword.value"
      :match-info="rvSearch.matchInfo.value"
      :has-matches="rvSearch.matches.value.length > 0"
      :case-sensitive="rvSearch.caseSensitive.value"
      :show-replace="false"
      @update:keyword="rvSearch.keyword.value = $event"
      @update:case-sensitive="rvSearch.caseSensitive.value = $event"
      @search="rvSearch.search()"
      @next="rvSearch.nextMatch()"
      @prev="rvSearch.prevMatch()"
      @close="rvSearch.close()"
    />

    <!-- 所有者权益变动表 — 对比模式：未审 / 审定并排矩阵 -->
    <div v-if="activeTab === 'equity_statement' && reportMode === 'compare'" class="gt-rv-equity-compare" v-loading="loading">
      <div class="gt-rv-equity-compare-block">
        <div class="gt-rv-equity-compare-label">未审数</div>
        <ReportEquityTable
          :rows="equityCompareUnadjusted"
          :eq-columns="eqColumns"
          :eq-total-cols="eqTotalCols"
          :year="year"
          :table-max-height="480"
          :cell-class-name="rvCellClassName"
          :font-size="displayPrefs.fontConfig.tableFont"
          :equity-span-method="equitySpanMethod"
          :eq-row-class-name="eqRowClassName"
          :eq-cell-val="eqCellVal"
          :is-consolidated="isConsolidated"
        />
      </div>
      <div class="gt-rv-equity-compare-block">
        <div class="gt-rv-equity-compare-label">审定数</div>
        <ReportEquityTable
          ref="eqTableRef"
          :rows="equityCompareAudited"
          :eq-columns="eqColumns"
          :eq-total-cols="eqTotalCols"
          :year="year"
          :table-max-height="480"
          :cell-class-name="rvCellClassName"
          :font-size="displayPrefs.fontConfig.tableFont"
          :equity-span-method="equitySpanMethod"
          :eq-row-class-name="eqRowClassName"
          :eq-cell-val="eqCellVal"
          :is-consolidated="isConsolidated"
          @cell-click="onRvCellClick"
          @cell-dblclick="onRvCellDblClick"
          @cell-contextmenu="onRvCellContextMenu"
        />
      </div>
    </div>

    <!-- 所有者权益变动表 — 单表模式 -->
    <div v-else-if="activeTab === 'equity_statement'" class="gt-rv-equity-matrix" v-loading="loading">
      <ReportEquityTable
        ref="eqTableRef"
        :rows="rows"
        :eq-columns="eqColumns"
        :eq-total-cols="eqTotalCols"
        :year="year"
        :table-max-height="600"
        :cell-class-name="rvCellClassName"
        :font-size="displayPrefs.fontConfig.tableFont"
        :equity-span-method="equitySpanMethod"
        :eq-row-class-name="eqRowClassName"
        :eq-cell-val="eqCellVal"
        :is-consolidated="isConsolidated"
        @cell-click="onRvCellClick"
        @cell-dblclick="onRvCellDblClick"
        @cell-contextmenu="onRvCellContextMenu"
      />
    </div>

    <!-- 资产减值准备表 — ReportImpairmentTable 子组件 -->
    <div v-if="activeTab === 'impairment_provision'" class="gt-rv-equity-matrix" v-loading="loading">
      <ReportImpairmentTable
        ref="impTableRef"
        :rows="rows"
        :imp-inc-cols="impIncCols"
        :imp-dec-cols="impDecCols"
        :table-max-height="600"
        :cell-class-name="rvCellClassName"
        :font-size="displayPrefs.fontConfig.tableFont"
        :imp-row-class-name="impRowClassName"
        @cell-click="onRvCellClick"
        @cell-dblclick="onRvCellDblClick"
        @cell-contextmenu="onRvCellContextMenu"
      />
    </div>

    <!-- 报表表格 — 普通模式（非矩阵报表） -->
    <el-table ref="rvTableRef" v-if="reportMode !== 'compare' && activeTab !== 'equity_statement' && activeTab !== 'impairment_provision' && activeTab !== 'cross_check' && activeTab !== 'multi_year_compare' && activeTab !== 'report_analysis'" :data="rows" v-loading="loading" style="width: 100%" class="gt-compact-table"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :row-class-name="rowClassName" :show-header="true" border size="small" :max-height="600"
      :cell-class-name="rvCellClassName"
      @cell-click="onRvCellClick"
      @cell-dblclick="onRvCellDblClick"
      @cell-contextmenu="onRvCellContextMenu">
      <el-table-column label="行次" width="80" align="center" :resizable="true">
        <template #default="{ row, $index }">
          <el-tooltip :content="row.row_code || ''" placement="left" :disabled="!row.row_code" :show-after="400">
            <span style="color: var(--gt-color-text-tertiary); font-size: 11px; white-space: nowrap;">{{ row.row_code || ($index + 1) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="项目" min-width="240" :resizable="true" fixed show-overflow-tooltip>
        <template #default="{ row }">
          <span :class="['report-row-name', `report-indent-${Math.min(row.indent_level || 0, 2)}`]"
                :style="{ paddingLeft: (row.indent_level || 0) * 24 + 8 + 'px', fontWeight: row.is_total_row || getRowType(row) === 'header' ? 700 : 400, fontSize: '13px', cursor: row.row_code && !row.is_total_row && getRowType(row) !== 'header' ? 'pointer' : 'default' }"
                @click="onRowNameClick(row)">
            {{ row.row_name }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="附注" width="52" align="center" :resizable="false" class-name="gt-rv-note-col">
        <template #default="{ row }">
          <el-button v-if="getNoteLabel(row.row_code)" size="small" text type="primary"
            style="font-size: 11px; padding: 0; white-space: nowrap;" :title="`查看附注 ${getNoteLabel(row.row_code)}`"
            @click.stop="goToNote(row.row_code)">{{ getNoteLabel(row.row_code) }}</el-button>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" min-width="160" align="right" header-align="center" :resizable="true" sortable :sort-method="(a: any, b: any) => (Number(a.current_period_amount) || 0) - (Number(b.current_period_amount) || 0)">
        <template #default="{ row, $index }">
          <template v-if="getRowType(row) === 'header'">
            <span class="report-amount">&nbsp;</span>
          </template>
          <template v-else-if="getRowType(row) === 'manual'">
            <span class="report-amount" style="color: var(--gt-color-text-placeholder);">—</span>
          </template>
          <template v-else>
            <el-tooltip :content="row.formula ? `公式：${row.formula}` : `行次 ${row.row_code || ''}`" placement="top" :show-after="500" :disabled="!row.row_code">
              <GtAmountCell
                :value="row.current_period_amount"
                :prior-value="row.prior_period_amount"
                :clickable="true"
                :comment="rvComments.getComment(`report_${activeTab}`, $index, 2)"
                @click="onLineComposition(row)"
              />
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" min-width="160" align="right" header-align="center" :resizable="true" sortable :sort-method="(a: any, b: any) => (Number(a.prior_period_amount) || 0) - (Number(b.prior_period_amount) || 0)">
        <template #default="{ row, $index }">
          <template v-if="getRowType(row) === 'header'">
            <span class="report-amount">&nbsp;</span>
          </template>
          <template v-else-if="getRowType(row) === 'manual'">
            <span class="report-amount" style="color: var(--gt-color-text-placeholder);">—</span>
          </template>
          <template v-else>
            <el-tooltip :content="row.formula ? `公式：${row.formula}` : `行次 ${row.row_code || ''}`" placement="top" :show-after="500" :disabled="!row.row_code">
              <GtAmountCell
                :value="row.prior_period_amount"
                :clickable="false"
                :comment="rvComments.getComment(`report_${activeTab}`, $index, 3)"
              />
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 报表表格 — 对比视图（非权益变动表） -->
    <el-table ref="compareTableRef" v-if="reportMode === 'compare' && activeTab !== 'equity_statement' && activeTab !== 'impairment_provision' && activeTab !== 'cross_check' && activeTab !== 'multi_year_compare' && activeTab !== 'report_analysis'" :data="compareRows" v-loading="loading" style="width: 100%" class="gt-compact-table"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :row-class-name="compareRowClassName"
      :cell-class-name="rvCellClassName"
      @cell-click="onRvCellClick"
      @cell-dblclick="onRvCellDblClick"
      @cell-contextmenu="onRvCellContextMenu"
      border size="small" :max-height="600">
      <el-table-column label="行次" width="80" align="center" :resizable="true">
        <template #default="{ row, $index }">
          <el-tooltip :content="row.row_code || ''" placement="left" :disabled="!row.row_code" :show-after="400">
            <span style="color: var(--gt-color-text-tertiary); font-size: 11px; white-space: nowrap;">{{ row.row_code || ($index + 1) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="项目" min-width="220" :resizable="true" show-overflow-tooltip>
        <template #default="{ row }">
          <span :style="{ paddingLeft: (row.indent_level || 0) * 24 + 8 + 'px', fontWeight: row.is_total_row || getRowType(row) === 'header' ? 700 : 400, fontSize: '13px', cursor: row.row_code && !row.is_total_row && getRowType(row) !== 'header' ? 'pointer' : 'default' }"
                @click="onRowNameClick(row)">{{ row.row_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注" width="52" align="center" :resizable="false" class-name="gt-rv-note-col">
        <template #default="{ row }">
          <el-button v-if="getNoteLabel(row.row_code)" size="small" text type="primary"
            style="font-size: 11px; padding: 0; white-space: nowrap;" :title="`查看附注 ${getNoteLabel(row.row_code)}`"
            @click.stop="goToNote(row.row_code)">{{ getNoteLabel(row.row_code) }}</el-button>
        </template>
      </el-table-column>
      <el-table-column label="未审金额" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.unadjusted_amount" />
        </template>
      </el-table-column>
      <el-table-column label="调整影响" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.adjustment" />
        </template>
      </el-table-column>
      <el-table-column label="已审金额" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.audited_amount" />
        </template>
      </el-table-column>
      <!-- 任务 12.7.1：对比视图新增"上年审定数"列（需求 24.1/24.2） -->
      <el-table-column label="上年审定数" min-width="130" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="row.prior_period_amount" />
        </template>
      </el-table-column>
      <!-- Sprint 11 Task 11.6：变动额+变动率列（需求 33.2/33.3） -->
      <el-table-column label="变动额" min-width="120" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <GtAmountCell :value="(row.audited_amount || 0) - (row.prior_period_amount || 0)" />
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="90" align="right" header-align="center" :resizable="true">
        <template #default="{ row }">
          <span v-if="Number(row.prior_period_amount) !== 0 && row.prior_period_amount != null"
                :class="['gt-rv-change-rate', { 'gt-rv-change-rate--alert': Math.abs(((Number(row.audited_amount) || 0) - Number(row.prior_period_amount)) / Math.abs(Number(row.prior_period_amount)) * 100) > 20 }]">
            {{ (((Number(row.audited_amount) || 0) - Number(row.prior_period_amount)) / Math.abs(Number(row.prior_period_amount)) * 100).toFixed(1) }}%
          </span>
          <span v-else style="color: var(--gt-color-text-placeholder);">-</span>
        </template>
      </el-table-column>
    </el-table>
    <!-- 选中区域状态栏 -->
    <SelectionBar :stats="rvCtx.selectionStats()" />

    <!-- F28: 报表数据覆盖率摘要 + 刷新时间 -->
    <div v-if="rows.length > 0 && (coverageSummary || lastReportRefreshTime) && activeTab !== 'cross_check'" class="gt-rv-coverage-summary">
      <span v-if="coverageSummary" class="gt-rv-coverage-icon">📊</span>
      <span v-if="coverageSummary" class="gt-rv-coverage-text">{{ coverageSummary.text }}</span>
      <span v-if="lastReportRefreshTime" class="gt-rv-refresh-time">🕒 上次刷新：{{ lastReportRefreshTime }}</span>
    </div>

    <!-- R7-S3-10 Task 49-50：跨表核对面板 -->
    <div v-if="activeTab === 'cross_check'" class="gt-rv-cross-check">
      <h3 style="margin: 0 0 16px; font-size: var(--gt-font-size-md)">⚖️ 跨表核对（7 条关键等式）</h3>
      <el-table :data="crossCheckResults" border size="small" style="width: 100%" class="gt-compact-table gt-tb-font-md"
        :cell-class-name="rvCellClassName"
        @cell-click="onRvCellClick"
        @cell-contextmenu="onRvCellContextMenu">
        <el-table-column label="#" width="40" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="核对等式" prop="description" min-width="300" />
        <el-table-column label="左值" prop="leftValue" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.leftValue" /></template>
        </el-table-column>
        <el-table-column label="右值" prop="rightValue" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.rightValue" /></template>
        </el-table-column>
        <el-table-column label="差异" width="120" align="right">
          <template #default="{ row }">
            <GtAmountCell :value="row.diff" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <span>{{ row.passed ? '✅' : '❌' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 12px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">
        核对基于当前已加载的报表数据计算，如数据未加载请先切换到对应报表 Tab。
      </div>
    </div>

    <!-- Phase 4 F2: 多年度对比 -->
    <div v-if="activeTab === 'multi_year_compare'" class="gt-rv-multi-year">
      <MultiYearCompare
        :project-id="projectId"
        :current-year="year"
      />
    </div>

    <!-- 报表分析（A2-1/A2-2 单体报表试算） -->
    <div v-if="activeTab === 'report_analysis'" class="gt-rv-report-analysis">
      <ReportAnalysisPanel
        :project-id="projectId"
        :year="year"
      />
    </div>

    </div><!-- /gt-rv-table-area -->

    <!-- 公式管理弹窗（template-type 必传：否则恒按国企版加载 report_config） -->
    <FormulaManagerDialog
      v-model="showFormulaManager"
      :rows="rows"
      :project-id="projectId"
      :year="year"
      scope="report"
      :template-type="selectedTemplateType"
      @saved="fetchReport"
      @applied="fetchReport"
    />

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showReportImport"
      import-type="report"
      :project-id="projectId"
      :year="year"
      :sub-type="activeTab"
      @imported="onReportImported"
    />

    <!-- ReportDialogs 子组件：穿透/构成科目/审核/溯源/转换规则/附注引用/合并明细/公式来源弹窗 -->
    <ReportDialogs
      :drilldown-visible="drilldownVisible"
      :drilldown-loading="drilldownLoading"
      :drilldown-data="drilldownData"
      :line-comp-visible="lineCompVisible"
      :line-comp-loading="lineCompLoading"
      :line-comp-data="lineCompData"
      :show-audit-dialog="showAuditDialog"
      :consistency-result="consistencyResult"
      :audit-tab="auditTab"
      :filtered-audit-checks="filteredAuditChecks"
      :show-trace-select-dialog="showTraceSelectDialog"
      :trace-select-options="traceSelectOptions"
      :trace-select-check="traceSelectCheck"
      :note-refs-visible="noteRefsVisible"
      :note-refs-loading="noteRefsLoading"
      :note-refs-list="noteRefsList"
      :note-refs-row-code="noteRefsRowCode"
      :note-refs-row-name="noteRefsRowName"
      :rv-trace-dialog-visible="rvTraceDialogVisible"
      :rv-trace-loading="rvTraceLoading"
      :rv-trace-result="rvTraceResult"
      :show-mapping-dialog="showMappingDialog"
      :mapping-loading="mappingLoading"
      :mapping-tab="mappingTab"
      :mapping-report-types="mappingReportTypes"
      :current-mapping-rules="currentMappingRules"
      :current-listed-options="currentListedOptions"
      :total-mapped-count="totalMappedCount"
      :total-rule-count="totalRuleCount"
      :mapping-tab-label="mappingTabLabel"
      :get-mapping-config-data="getMappingConfigData"
      :consol-breakdown-visible="consolBreakdownVisible"
      :consol-breakdown-account-code="consolBreakdownAccountCode"
      :project-id="projectId"
      :year="year"
      :show-cell-formula-detail="showCellFormulaDetail"
      :cell-detail-wp-code="cellDetailWpCode"
      :cell-detail-sheet="cellDetailSheet"
      :cell-detail-label="cellDetailLabel"
      :parse-trace-locations="parseTraceLocations"
      @update:drilldown-visible="drilldownVisible = $event"
      @update:line-comp-visible="lineCompVisible = $event"
      @update:show-audit-dialog="showAuditDialog = $event"
      @update:show-trace-select-dialog="showTraceSelectDialog = $event"
      @update:note-refs-visible="noteRefsVisible = $event"
      @update:rv-trace-dialog-visible="rvTraceDialogVisible = $event"
      @update:show-mapping-dialog="showMappingDialog = $event"
      @update:consol-breakdown-visible="consolBreakdownVisible = $event"
      @update:show-cell-formula-detail="showCellFormulaDetail = $event"
      @update:mapping-tab="mappingTab = $event"
      @update:audit-tab="auditTab = $event"
      @line-comp-jump="onLineCompJumpToTB"
      @audit-drilldown="_onAuditDrilldown"
      @audit-export-excel="onExportAuditExcel"
      @trace-jump="onTraceJump"
      @trace-return="onTraceReturn"
      @trace-locate="onRvTraceLocate"
      @note-ref-jump="onJumpToNoteSection"
      @mapping-load-preset="loadPresetMappingAll"
      @mapping-save="saveMappingRulesAll"
      @mapping-template-applied="onMappingTemplateApplied"
      @cell-detail-navigate="onCellDetailNavigate"
      @open-workpaper="openWorkpaper"
    />
  </div>

  <!-- 右键菜单（统一组件） -->
  <CellContextMenu
    :visible="rvCtx.contextMenu.visible"
    :x="rvCtx.contextMenu.x"
    :y="rvCtx.contextMenu.y"
    :item-name="rvCtx.contextMenu.itemName"
    :value="rvCtx.selectedCells.value.length === 1 ? rvCtx.selectedCells.value[0]?.value : undefined"
    :multi-count="rvCtx.selectedCells.value.length"
    @copy="onRvCtxCopy"
    @formula="onRvCtxFormula"
    @trust-score="onRvCtxTrustScore"
    @sum="onRvCtxSum"
    @compare="onRvCtxCompare"
  >
    <div class="gt-ucell-ctx-item" @click="onRvCtxDrillDown"><span class="gt-ucell-ctx-icon">📊</span> 查看穿透</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxGoNote"><span class="gt-ucell-ctx-icon">📝</span> 跳转附注</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxShowNoteRefs"><span class="gt-ucell-ctx-icon">🔎</span> 附注引用我</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxOpenWorkpaper"><span class="gt-ucell-ctx-icon">📋</span> 打开对应底稿</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxViewAdjustments"><span class="gt-ucell-ctx-icon">🔗</span> 查看调整明细</div>
    <div v-if="isConsolidated" class="gt-ucell-ctx-item" @click="onRvCtxViewConsolBreakdown"><span class="gt-ucell-ctx-icon">🔗</span> 查看合并明细</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxViewFormulaSource"><span class="gt-ucell-ctx-icon">🔍</span> 查看公式来源</div>
    <div class="gt-ucell-ctx-item" @click="onRvCtxCellTrace"><span class="gt-ucell-ctx-icon">🔍</span> 数字溯源</div>
  </CellContextMenu>

  <!-- V3 Req 9.6: 数字信任度面板 -->
  <TrustScorePanel ref="trustScorePanelRef" :project-id="projectId" />

  <!-- V3 Req 10.4: 可解释状态机面板 -->
  <StatusMachinePanel ref="smPanelRef" module="report" :instance-id="reportInstanceId" />

  <!-- AI 对话面板（统一内核；宿主契约由 useAiHostContext 的报表 adapter 构造） -->
  <PlatformAiChatPanel
    :host="aiHost"
    :visible="showDocAiChat"
    @adopt="onDocAiAdopt"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch, watchEffect, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import MultiYearCompare from '@/components/report/MultiYearCompare.vue'
import ReportAnalysisPanel from '@/components/workpaper/ReportAnalysisPanel.vue'
import ReportEquityTable from '@/components/report/ReportEquityTable.vue'
import ReportImpairmentTable from '@/components/report/ReportImpairmentTable.vue'
import ReportDialogs from '@/components/report/ReportDialogs.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtEmpty from '@/components/common/GtEmpty.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useProjectStore } from '@/stores/project'
import { setupPasteListener, pasteToSelection } from '@/composables/useCopyPaste'
import { useAuditContext } from '@/composables/useAuditContext'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import WorkflowProgress from '@/components/common/WorkflowProgress.vue'
import ConflictBanner from '@/components/conflict/ConflictBanner.vue'
import ConflictResolutionPanel from '@/components/conflict/ConflictResolutionPanel.vue'
import TrustScorePanel from '@/components/trust/TrustScorePanel.vue'
import StatusMachinePanel from '@/components/status_machine/StatusMachinePanel.vue'
import { withLoading } from '@/composables/useLoading'
import { usePenetrate } from '@/composables/usePenetrate'
import { useProjectEvents } from '@/composables/useProjectEvents'
import { useStaleRefresh } from '@/composables/useStaleRefresh'
import { recalcTrialBalance } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { useAuthStore } from '@/stores/auth'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { useReportColumns } from './composables/useReportColumns'
import http from '@/utils/http'
import { useReportCrossCheck } from './composables/useReportCrossCheck'
import { useReportData } from './composables/useReportData'
import { useReportExport } from './composables/useReportExport'
import { useReportMapping } from './composables/useReportMapping'
import { useReportCellActions } from './composables/useReportCellActions'
import PlatformAiChatPanel from '@/components/ai/PlatformAiChatPanel.vue'
import { buildReportHost } from '@/composables/useAiHostContext'

const route = useRoute()
const router = useRouter()
const { canEdit, onContextChange } = useAuditContext()

/** 工作流进度条：导入/映射等步骤跳转到试算表页操作 */
function onWorkflowStepAction(action: string) {
  if (!projectId.value) return
  if (action === 'import' || action === 'mapping') {
    router.push(`/projects/${projectId.value}/trial-balance`)
  }
}

/** 工作流进度条「生成报表」下一步：当前已在报表页，直接触发生成（避免跳同路由无反应） */
function onWorkflowNext() {
  if (isEqcrRole.value) {
    ElMessage.info('EQCR 复核角色为只读，无法生成报表')
    return
  }
  onGenerate()
}

// EQCR 只读访问 (Requirements: 17.1-17.4)
const authStore = useAuthStore()
const isEqcrRole = computed(() => authStore.user?.role === 'eqcr')
const projectStore = useProjectStore()

// ─── P0-6.4: ProjectContext + PermissionMatrix facade ────────────────────────
const projectContext = computed(() => projectStore.currentProjectContext)
const { can: canOp, whyCannot } = usePermissionMatrix()
// DEPRECATED: 旧 isEqcrRole 判断仍保留，后续替换为 !canOp('report:edit')

const projectId = computed(() => projectStore.projectId)

// 跨模块冲突调解（spec global-refinement-v3 Task 7.5）
const conflictPanelVisible = ref(false)
function onConflictResolved(_id: string, _resolution: string) {
  // 调解后 banner 自动从列表移除；此处保留 hook 供后续扩展（如局部 reload）
}

// ─── AI 宿主上下文（dsh-agent-panel-integration Req 3.2/3.5） ─────────────────
// 报表宿主的稳定标识是 **report type**（当前 tab），不是项目 ID。
// 旧实现传 `:doc-id="projectId"` —— 项目 ID 当文档 ID，服务端只能查空。
// 跨表核对 / 多年度对比 / 报表分析这些 tab 不是单张报表 → adapter 返回显式不可用 + 中文原因。
const aiHost = computed(() =>
  buildReportHost({
    reportType: activeTab.value,
    projectId: projectId.value,
    year: year.value,
  }),
)

// ─── AI 文档对话采纳 ─────────────────────────────────────────────────────────
function onDocAiAdopt(_payload: { content: string; messageId: string }) {
  // 采纳事件由 DocAiChatPanel 内部调用 adoptContent API（走确认流）
  // D4: AI 内容已经过 wrap_ai_output_with_log → pending 状态，不直接写入
  // 报表视图在确认流完成后刷新数据
  fetchReport()
}

// ─── 云协同：账套激活/回滚后自动刷新 ─────────────────────────────────────────
const { onDatasetActivated, onDatasetRolledBack, onAnyEvent } = useProjectEvents(projectId)
onDatasetActivated(() => fetchReport())
onDatasetRolledBack(() => fetchReport())

// ─── useStaleRefresh：补充上游变更事件（dataset 已由 useProjectEvents 覆盖） ────
const staleRefresh = useStaleRefresh(projectId, {
  events: ['trial-balance:updated', 'adjustment:saved', 'year:changed', 'project:updated'],
  mode: 'prompt',
  onRefresh: () => fetchReport(),
})

// R8-S2-03：Stale 状态追踪（上游数据变更提示）
import { useStaleStatus } from '@/composables/useStaleStatus'
import StaleIndicator from '@/components/StaleIndicator.vue'
const stale = useStaleStatus(projectId)

// US-2：底稿保存后 report.stale SSE 订阅 → 黄色横幅 + 刷新
const reportStaleRows = ref<string[]>([])
const showReportStaleBanner = ref(false)

onAnyEvent((evt) => {
  if (evt.event_type === 'report.stale' && evt.extra?.rows) {
    reportStaleRows.value = evt.extra.rows as string[]
    showReportStaleBanner.value = true
  }
})

async function onReportStaleRefresh() {
  showReportStaleBanner.value = false
  reportStaleRows.value = []
  await fetchReport()
}
async function onStaleRecalc() {
  await stale.recalc()
  // 重算后重新拉取报表数据
  await fetchReport()
}

function goBack() {
  router.push(`/projects`)
}

const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const _templateTypeLabel = computed(() => reportData.templateType.value === 'listed' ? '上市版' : '国企版')
const scopeLabel = computed(() => reportData.reportScope.value === 'consolidated' ? '合并' : '单体')

// 单位（项目）选择器 — 使用 projectStore
const selectedProjectId = ref('')
const projectOptions = computed(() => projectStore.projectOptions)

function onProjectChange(newId: string) {
  router.push({ path: `/projects/${newId}/reports`, query: route.query })
}

// 年度选择器
const selectedYear = ref(new Date().getFullYear() - 1)
const yearOptions = computed(() => projectStore.yearOptions)
function onYearChange(val: number) {
  selectedYear.value = val
  projectStore.changeYear(val)
  fetchReport()
}

// 模板类型切换
const selectedTemplateType = ref('soe')
const _rdReportScope = ref('standalone')
const currentApplicableStandard = computed(() => `${selectedTemplateType.value}_${_rdReportScope.value}`)

async function onTemplateTypeChange(val: string) {
  selectedTemplateType.value = val
  reportData.templateType.value = val
  await reportData.fetchReport()
}

// ─── Other UI state ─────────────────────────────────────────────────────────
const showDocAiChat = ref(false)

const year = computed(() => routeYear.value ?? projectYear.value ?? new Date().getFullYear() - 1)

const activeTab = ref('balance_sheet')
const reportMode = ref<'audited' | 'unadjusted' | 'compare'>('audited')

// ─── useReportData composable ───────────────────────────────────────────────
const reportData = useReportData({
  projectId,
  year,
  activeTab,
  reportMode,
  currentApplicableStandard,
})

const {
  rows,
  compareRows,
  equityCompareAudited,
  equityCompareUnadjusted,
  loading,
  genLoading,
  checkLoading,
  syncLoading,
  balanceCheckResult,
  consistencyResult,
  tableMaxHeight,
  fetchReport,
  onGenerate,
  onConsistencyCheck,
  runBalanceCheck,
  loadTemplateRows,
  ensureProjectYear,
  reloadReportContext,
  activeTabLabel,
  coverageSummary,
  projectName,
  reportScope,
  templateType,
  isConsolidated,
} = reportData

// Sync composable's reportScope → local proxy for currentApplicableStandard
watchEffect(() => { _rdReportScope.value = reportScope.value })

// 追踪报表刷新完成时间
watch(loading, (newVal, oldVal) => {
  if (oldVal === true && newVal === false && rows.value.length > 0) {
    lastReportRefreshAt.value = new Date()
  }
})

// 动态计算表格最大高度（窗口高度 - 顶部固定区域）
function updateTableHeight() {
  const headerEl = document.querySelector('.gt-rv-sticky-header')
  const headerH = headerEl ? headerEl.getBoundingClientRect().height : 200
  tableMaxHeight.value = Math.max(300, window.innerHeight - headerH - 80)
}

// 平衡检查明细项点击跳转：根据检查名称中的关键词定位到报表对应行
function scrollToReportRow(checkName: string) {
  // 提取检查名称中可能包含的行次或表名信息
  // 常见格式: "资产负债表平衡（资产合计=负债+权益）" / "勾稽：CFS期末现金=BS货币资金"
  const table = document.querySelector('.el-table__body-wrapper tbody')
  if (!table) return
  const allRows = table.querySelectorAll('tr')

  // 从检查名中提取可匹配的关键词
  const keywords: string[] = []
  if (checkName.includes('资产负债') || checkName.includes('资产合计')) keywords.push('资产总计', '资产合计', '负债和所有者权益')
  if (checkName.includes('利润表') || checkName.includes('净利润')) keywords.push('净利润', '利润总额')
  if (checkName.includes('CFS') || checkName.includes('现金')) keywords.push('现金及现金等价物', '货币资金')
  if (checkName.includes('权益')) keywords.push('所有者权益合计', '股东权益')
  // 如果没提取到关键词,用原始检查名的各段尝试
  if (!keywords.length) {
    keywords.push(...checkName.split(/[（）()=≠,，]/g).map(s => s.trim()).filter(s => s.length > 1))
  }

  for (const tr of allRows) {
    const text = tr.textContent || ''
    if (keywords.some(kw => text.includes(kw))) {
      tr.scrollIntoView({ behavior: 'smooth', block: 'center' })
      tr.classList.add('gt-highlight-row')
      setTimeout(() => tr.classList.remove('gt-highlight-row'), 3000)
      return
    }
  }
  // fallback: 未找到匹配行时提示
  ElMessage.info('未找到对应行，请手动查看')
}
onMounted(() => {
  updateTableHeight()
  window.addEventListener('resize', updateTableHeight)
  document.addEventListener('keydown', onKeydown)
  projectStore.loadProjectOptions()
  selectedProjectId.value = projectId.value
})
onUnmounted(() => {
  window.removeEventListener('resize', updateTableHeight)
  document.removeEventListener('keydown', onKeydown)
})

// ─── useReportColumns composable ────────────────────────────────────────────
// ─── 附注有内容的章节集合（从 notes-tree 拉取 has_data=true 的节点） ────────
const noteHasDataSections = ref<Set<string>>(new Set())
const showZeroWithNote = ref(true) // 默认自动显示金额=0但附注有内容的科目

// ─── 动态行次→附注章节映射（从后端 report_row_note_mapping.json 按变体加载）────
const rowNoteMapping = ref<Record<string, string>>({})
/** 全局连续附注序号（跨报表类型连续编排：BS→IS→CFS→EQ→CFSS） */
const rowNoteSeqMap = ref<Record<string, number>>({})

async function loadRowNoteMapping() {
  try {
    const standard = `${selectedTemplateType.value}_${reportScope.value}` || 'soe_standalone'
    const data = await api.get('/api/report-config/row-note-mapping', {
      params: { applicable_standard: standard },
      _silent: true,
    } as any)
    if (data && typeof data === 'object') {
      const mapped: Record<string, string> = {}
      const seqs: Record<string, number> = {}
      for (const [code, info] of Object.entries(data)) {
        if (info && typeof info === 'object') {
          const i = info as any
          if (i.section_code) mapped[code] = i.section_code
          if (i.seq) seqs[code] = i.seq
        }
      }
      rowNoteMapping.value = mapped
      rowNoteSeqMap.value = seqs
    }
  } catch { /* fail-open: 动态映射加载失败回退硬编码 */ }
}

// 加载附注各章节是否有内容（best-effort，不阻塞报表渲染）
async function loadNoteHasData() {
  try {
    const { data } = await http.get(
      `/api/disclosure-notes/${projectId.value}/${year.value}/notes-tree`,
      { _silent: true } as any
    )
    const sections = data?.data || data || []
    const set = new Set<string>()
    for (const node of (Array.isArray(sections) ? sections : [])) {
      if (node.has_data && node.note_section) {
        set.add(node.note_section)
      }
      // 子节点
      if (Array.isArray(node.children)) {
        for (const child of node.children) {
          if (child.has_data && child.note_section) {
            set.add(child.note_section)
          }
        }
      }
    }
    noteHasDataSections.value = set
  } catch { /* fail-open: 拿不到附注数据不影响报表渲染 */ }
}
// 报表行数据加载后 best-effort 拉附注就绪状态 + 动态映射
watch(rows, (newRows) => {
  if (newRows.length > 0 && noteHasDataSections.value.size === 0) {
    loadNoteHasData()
  }
  if (newRows.length > 0 && Object.keys(rowNoteMapping.value).length === 0) {
    loadRowNoteMapping()
  }
}, { immediate: true })

/** 缓存资产负债表 tab 的实际附注序号数（供利润表接续用） */
const bsNoteCount = ref(0)
/** 缓存利润表 tab 的实际附注序号数（供现金流量表接续用） */
const isNoteCount = ref(0)

const {
  eqColumns,
  eqTotalCols,
  equitySpanMethod,
  eqRowClassName,
  eqCellVal,
  impIncCols,
  impDecCols,
  impRowClassName,
  getRowType,
  rowClassName,
  compareRowClassName,
  formatReportAmount,
  getNoteSection,
  getNoteLabel,
  goToNote,
} = useReportColumns({ isConsolidated, activeTab, rows, noteHasDataSections, showZeroWithNote, rowNoteMapping, rowNoteSeqMap, bsNoteCount, isNoteCount })

// ─── useReportMapping composable ────────────────────────────────────────────
const {
  showMappingDialog,
  mappingLoading,
  mappingTab,
  allMappingRules,
  allListedOptions,
  mappingReportTypes,
  mappingTabLabel,
  currentMappingRules,
  currentListedOptions,
  totalMappedCount,
  totalRuleCount,
  loadPresetMappingAll,
  saveMappingRulesAll,
  getMappingConfigData,
  onMappingTemplateApplied,
} = useReportMapping({ projectId, reportScope })

// ─── useReportCrossCheck composable ─────────────────────────────────────────
const {
  crossCheckData,
  crossCheckLoading,
  crossCheckResults,
  loadCrossCheckData,
} = useReportCrossCheck({ projectId, year, activeTab, currentApplicableStandard })

// ─── useReportExport composable ─────────────────────────────────────────────
const {
  onExportExcel,
  onExportAllExcel,
  onExportAllUnadjusted,
  copyReportTable,
  showReportImport,
  onReportImported,
} = useReportExport({ projectId, year, activeTab, rows, activeTabLabel, fetchReport })

const _reportModeLabel = computed(() => {
  const m: Record<string, string> = { audited: '已审报表', unadjusted: '未审报表', compare: '对比视图' }
  return m[reportMode.value] || ''
})

// Drilldown + Formula Manager (kept in main file for template binding)
const showFormulaManager = ref(false)
const showRvGuide = ref(false)
const rvBalanceExpanded = ref(false)
const lastReportRefreshAt = ref<Date | null>(null)

// P0-2: AI 对话提升为一级按钮，打开时注入当前报表数据 context
function openAiWithContext() {
  showDocAiChat.value = true
}

const lastReportRefreshTime = computed(() => {
  if (!lastReportRefreshAt.value) return ''
  const d = lastReportRefreshAt.value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

// V3 Req 9.6: 数字信任度
const trustScorePanelRef = ref<InstanceType<typeof TrustScorePanel> | null>(null)
function openTrustScore(context: string) {
  trustScorePanelRef.value?.open(context)
}

// V3 Req 10.4: 可解释状态机
const smPanelRef = ref<InstanceType<typeof StatusMachinePanel> | null>(null)
const reportInstanceId = ref('')
function openStatusMachine() {
  smPanelRef.value?.open()
}

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
// NOTE: 必须在 useReportCellActions 之前声明（被作为参数传入）
const rvCtx = useCellSelection()
const rvPenetrate = usePenetrate()
const rvComments = useCellComments(() => projectId.value, () => year.value, 'report')

// ─── useReportCellActions composable ────────────────────────────────────────
const cellActions = useReportCellActions({
  projectId,
  year,
  activeTab,
  rows,
  reportMode,
  isConsolidated,
  fetchReport,
  activeTabLabel,
  getRowType,
  goToNote,
  consistencyResult,
  showFormulaManager,
  openTrustScore,
  rvCtx,
  rvPenetrate,
  rvComments,
  eqCellVal,
})

const {
  drilldownVisible,
  drilldownLoading,
  drilldownData,
  onDrilldown,
  lineCompVisible,
  lineCompLoading,
  lineCompData,
  onLineComposition,
  onLineCompJumpToTB,
  noteRefsVisible,
  noteRefsLoading,
  noteRefsList,
  noteRefsRowCode,
  noteRefsRowName,
  onRvCtxShowNoteRefs,
  onJumpToNoteSection,
  rvTraceDialogVisible,
  rvTraceLoading,
  rvTraceResult,
  onRvCtxCellTrace,
  onRvTraceLocate,
  showAuditDialog,
  auditTab,
  filteredAuditChecks,
  onExportAuditExcel,
  onAuditDrilldown: _onAuditDrilldown,
  showTraceSelectDialog,
  traceSelectOptions,
  traceSelectCheck,
  isTracing,
  onTraceJump,
  onTraceReturn,
  consolBreakdownVisible,
  consolBreakdownAccountCode,
  onRvCtxViewConsolBreakdown,
  showCellFormulaDetail,
  cellDetailWpCode,
  cellDetailSheet,
  cellDetailLabel,
  onRvCtxViewFormulaSource,
  onCellDetailNavigate,
  onRvCellClick,
  onRvCellDblClick,
  onRvCellContextMenu,
  onRvCtxCopy,
  onRvCtxDrillDown,
  onRvCtxFormula,
  onRvCtxTrustScore,
  onRvCtxGoNote,
  onRvCtxOpenWorkpaper,
  onRvCtxViewAdjustments,
  onRvCtxSum,
  onRvCtxCompare,
  onRowNameClick,
  parseTraceLocations,
  openWorkpaper,
} = cellActions


async function _ensureProjectYearWrapper() {
  if (routeYear.value !== null) {
    projectYear.value = null
    return
  }
  // Delegate to composable (sets projectName, reportScope, templateType, _fetchedAuditYear via API)
  await ensureProjectYear()
  // Sync main-file-owned state from composable results
  projectYear.value = reportData._fetchedAuditYear.value
  selectedYear.value = projectYear.value || new Date().getFullYear() - 1
  selectedTemplateType.value = templateType.value
}

function onTabChange() {
  if (activeTab.value === 'cross_check' || activeTab.value === 'multi_year_compare' || activeTab.value === 'report_analysis') return
  fetchReport()
}

const _onSyncUnadjusted = withLoading(syncLoading, async () => {
  await recalcTrialBalance(projectId.value, year.value)
  await fetchReport()
  ElMessage.success('未审数已按四表账套科目重新同步')
})

// Wrapper: composable's onConsistencyCheck + open dialog
async function _onConsistencyCheckWrapper() {
  await onConsistencyCheck()
  if (consistencyResult.value) {
    showAuditDialog.value = true
  }
}

function onEditConfig() {
  import('element-plus').then(({ ElMessageBox }) => {
    ElMessageBox.confirm(
      '编辑报表结构将改变报表行次定义，可能影响平衡校验和公式取数。建议仅项目经理/合伙人操作。\n\n修改前系统会自动保存当前结构快照，可通过「恢复默认结构」回退。',
      '⚠️ 编辑报表结构',
      { confirmButtonText: '继续编辑', cancelButtonText: '取消', type: 'warning' },
    ).then(() => {
      router.push(`/projects/${projectId.value}/report-config`)
    }).catch(() => {})
  })
}

// Wrapper: calls composable's reloadReportContext + syncs main-file state
async function _reloadReportContextWrapper() {
  await _ensureProjectYearWrapper()
  await fetchReport()
}

// 初次加载（替代 onMounted 一次性加载）
_reloadReportContextWrapper()

// V3 Req 5.1：上下文（projectId/year）变化时自动重载（替代散落的 watch）
onContextChange(() => {
  _reloadReportContextWrapper()
})


const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const rvSearch = useTableSearch(rows, ['row_name', 'row_code'])

// ─── 拖拽框选（鼠标左键按住拖动选中连续区域） ──────────────────────────────
const rvTableRef = ref<any>(null)
const eqTableRef = ref<any>(null)
const impTableRef = ref<any>(null)
const compareTableRef = ref<any>(null)

// 通用取值函数（适配所有报表类型）
function getAnyCellValue(rowIdx: number, colIdx: number): any {
  const row = rows.value[rowIdx]
  if (!row) return null
  if (activeTab.value !== 'equity_statement' && activeTab.value !== 'impairment_provision') {
    if (colIdx === 2) return row.current_period_amount
    if (colIdx === 3) return row.prior_period_amount
    if (colIdx === 1) return row.row_name
    return row.row_code
  }
  if (colIdx === 0) return row.row_name
  return row.current_period_amount ?? ''
}

rvCtx.setupTableDrag(rvTableRef, getAnyCellValue)

// 权益表/减值表/对比表的拖拽支持（tab/mode 切换后动态绑定）
watch([activeTab, () => reportMode.value], () => {
  setTimeout(() => {
    const bindDrag = (tableRef: any) => {
      if (!tableRef.value) return
      const dom = tableRef.value.$el || tableRef.value
      if (!dom || dom._gtDragBound) return
      dom._gtDragBound = true

      function parseCellPos(target: HTMLElement) {
        const td = target.closest('td.el-table__cell') as HTMLElement | null
        if (!td) return null
        const tr = td.closest('tr') as HTMLElement | null
        const tbody = tr?.closest('tbody')
        if (!tr || !tbody) return null
        const rowIdx = Array.from(tbody.children).indexOf(tr)
        const colIdx = Array.from(tr.children).indexOf(td)
        return (rowIdx >= 0 && colIdx >= 0) ? { row: rowIdx, col: colIdx } : null
      }

      dom.addEventListener('mousedown', (e: MouseEvent) => {
        if (e.button !== 0) return
        const tag = (e.target as HTMLElement).tagName
        if (['INPUT', 'BUTTON', 'TEXTAREA', 'SELECT', 'A'].includes(tag)) return
        const pos = parseCellPos(e.target as HTMLElement)
        if (!pos) return
        const value = getAnyCellValue(pos.row, pos.col)
        if (e.shiftKey) {
          e.preventDefault()
          rvCtx.selectCell(pos.row, pos.col, value, false, true)
        } else if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault()
          rvCtx.startDrag(pos.row, pos.col, value)
        }
      })

      dom.addEventListener('mouseover', (e: MouseEvent) => {
        const pos = parseCellPos(e.target as HTMLElement)
        if (!pos) return
        rvCtx.updateDrag(pos.row, pos.col)
      })
    }
    bindDrag({ value: eqTableRef.value?.tableRef })
    bindDrag({ value: impTableRef.value?.tableRef })
    bindDrag(compareTableRef)
  }, 100)
}, { immediate: true })

// ─── 粘贴监听（Ctrl+V 粘贴 Excel 数据到选中区域） ──────────────────────────
const rvColumns = [
  { key: 'row_code', label: '行次' },
  { key: 'row_name', label: '项目' },
  { key: 'current_period_amount', label: '本期金额' },
  { key: 'prior_period_amount', label: '上期金额' },
]

setupPasteListener(rvTableRef, (event: ClipboardEvent) => {
  if (!rvCtx.selectedCells.value.length) return
  pasteToSelection(event, rvCtx.selectedCells.value, rows.value, rvColumns)
})

/** Ctrl+F 快捷键触发搜索栏（拦截浏览器默认搜索） */
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault()
    e.stopPropagation()
    rvSearch.toggle()
  }
}

function rvCellClassName({ rowIndex, columnIndex }: any) {
  const classes: string[] = []
  const selClass = rvCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  const ccClass = rvComments.commentCellClass(`report_${activeTab.value}`, rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

// ─── 全屏与复制 ──────────────────────────────────────────────────────────────
const { isFullscreen: rvFullscreen, toggleFullscreen: toggleRvFullscreen } = useFullscreen()

// 全屏时自动收起使用说明面板
watch(rvFullscreen, (v) => { if (v) showRvGuide.value = false })
</script>

<style scoped src="./report-view.css" />
<style>
/* 平衡检查跳转高亮动画 */
.gt-highlight-row {
  animation: gt-row-flash 0.6s ease-in-out 3;
}
@keyframes gt-row-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: rgba(75, 45, 119, 0.12); }
}

/* ─── 报表使用说明面板 ─── */
.gt-rv-guide-panel {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 8px;
  background: linear-gradient(135deg, #fafbff 0%, #f5f0fa 100%);
  overflow: hidden;
}
.gt-rv-guide-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: linear-gradient(90deg, var(--gt-color-primary, #4b2d77) 0%, #6b4a99 100%);
}
.gt-rv-guide-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 0.5px;
}
.gt-rv-guide-panel__header .el-button {
  color: rgba(255,255,255,0.85) !important;
}
.gt-rv-guide-panel__body {
  padding: 24px 28px 32px;
  height: 100%;
  overflow-y: auto;
}
.gt-rv-guide-section {
  margin-bottom: 20px;
}
.gt-rv-guide-section:last-child {
  margin-bottom: 0;
}
.gt-rv-guide-section__title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  padding-left: 10px;
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
.gt-rv-guide-section__text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular, #606266);
}
.gt-rv-guide-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.gt-rv-guide-card {
  padding: 14px 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  transition: box-shadow 0.2s;
}
.gt-rv-guide-card:hover {
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.1);
}
.gt-rv-guide-card__icon {
  font-size: 20px;
  margin-bottom: 6px;
}
.gt-rv-guide-card__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
  margin-bottom: 4px;
}
.gt-rv-guide-card__desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary, #909399);
}
.gt-rv-guide-btn-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.gt-rv-guide-btn-item {
  padding: 14px 18px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
}
.gt-rv-guide-btn-item--compact {
  padding: 10px 16px;
}
.gt-rv-guide-btn-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 14px;
}
.gt-rv-guide-btn-item--compact .gt-rv-guide-btn-item__head {
  margin-bottom: 4px;
}
.gt-rv-guide-btn-item__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  font-size: 14px;
}
.gt-rv-guide-btn-item__badge--success { background: #f0f9eb; }
.gt-rv-guide-btn-item__badge--info { background: #ecf5ff; }
.gt-rv-guide-btn-item__badge--primary { background: #f3f0f8; }
.gt-rv-guide-btn-item__badge--danger { background: #fef0f0; }
.gt-rv-guide-btn-item__desc {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular, #606266);
}
.gt-rv-guide-btn-item__desc p {
  margin: 4px 0;
}
.gt-rv-guide-btn-item__desc code {
  background: #f5f0fa;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-rv-guide-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.gt-rv-guide-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
}
.gt-rv-guide-step__num {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-rv-guide-step__content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  line-height: 1.5;
}
.gt-rv-guide-step__content b {
  color: var(--el-text-color-primary, #303133);
}
.gt-rv-guide-step__content span {
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
}
.gt-rv-guide-notes {
  margin: 0;
  padding: 0 0 0 4px;
  list-style: none;
  font-size: 13px;
  line-height: 2;
  color: var(--el-text-color-regular, #606266);
}
.gt-rv-guide-notes li {
  padding: 2px 0;
}
.gt-rv-guide-shortcut-table {
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 8px;
  overflow: hidden;
}
.gt-rv-guide-shortcut-row {
  display: grid;
  grid-template-columns: 160px 1fr;
  font-size: 13px;
  line-height: 1.6;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}
.gt-rv-guide-shortcut-row:last-child {
  border-bottom: none;
}
.gt-rv-guide-shortcut-row--header {
  background: #f9f7fc;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.gt-rv-guide-shortcut-row span {
  padding: 8px 14px;
}
.gt-rv-guide-shortcut-row span:first-child {
  border-right: 1px solid var(--el-border-color-extra-light, #f2f6fc);
  color: var(--el-text-color-primary, #303133);
  font-weight: 500;
}
.gt-rv-guide-shortcut-row span:last-child {
  color: var(--el-text-color-regular, #606266);
}
.gt-rv-guide-shortcut-row kbd {
  display: inline-block;
  padding: 1px 5px;
  font-size: 11px;
  font-family: inherit;
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  box-shadow: 0 1px 0 #dcdfe6;
}

/* ─── 报表平衡检查紧凑条 ─── */
.gt-rv-balance-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  margin-bottom: 6px;
  border-radius: 6px;
  font-size: 13px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
}
.gt-rv-balance-bar--warning,
.gt-rv-balance-bar--error {
  background: #fdf6ec;
  border-color: #faecd8;
}
.gt-rv-balance-bar--passed {
  background: #f0f9eb;
  border-color: #e1f3d8;
}
.gt-rv-balance-bar__icon {
  font-size: 14px;
}
.gt-rv-balance-bar__text {
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
}
.gt-rv-balance-detail {
  margin-bottom: 8px;
  padding: 8px 16px;
  background: #fffbf0;
  border: 1px solid #faecd8;
  border-radius: 6px;
  font-size: 12px;
}
.gt-rv-balance-detail__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
  border-bottom: 1px solid rgba(0,0,0,0.04);
}
.gt-rv-balance-detail__row:last-child {
  border-bottom: none;
}
.gt-rv-balance-detail__row:hover {
  background: rgba(75, 45, 119, 0.04);
  border-radius: 4px;
}

/* ─── 报表行分组视觉强化 ─── */
:deep(.report-row--header td) {
  background: rgba(75, 45, 119, 0.04) !important;
  border-top: 2px solid rgba(75, 45, 119, 0.12) !important;
}
:deep(.report-row--total td) {
  background: rgba(75, 45, 119, 0.06) !important;
  font-weight: 700 !important;
}
:deep(.gt-rv-note-col) {
  padding: 0 !important;
}
:deep(.gt-rv-note-col .cell) {
  padding: 0 4px !important;
}
.gt-rv-refresh-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
</style>
