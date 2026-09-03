<template>
  <!-- [platform-ui-editing-consistency MVP-1]
       TODO: Wrap page content with <GtPageShell> to unify header/toolbar/banners -->
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
          <!-- 使用说明入口 -->
          <el-button
            size="small"
            style="margin-left: auto"
            :type="showTbGuide ? 'primary' : 'default'"
            @click="showTbGuide = !showTbGuide"
          >
            📖 使用说明
          </el-button>
        </GtInfoBar>
        <template #actions>
          <GtToolbar
            :show-copy="true"
            :show-fullscreen="true"
            :is-fullscreen="tbFullscreen"
            :show-export="false"
            :show-import="false"
            :show-formula="true"
            @copy="copyTbTable"
            @fullscreen="toggleTbFullscreen()"
            @export="onExport"
            @import="onToolbarImport"
            @formula="showFormulaManager = true"
          >
            <template #left>
              <el-tooltip :content="lastCheckTimeText ? `检查试算表与四表数据的一致性（上次：${lastCheckTimeText}）` : '检查试算表与四表数据的一致性'" placement="bottom">
                <el-button
                  size="small"
                  :type="toolbarHighlight === 'check' ? 'warning' : 'default'"
                  :class="{ 'gt-tb-btn-pulse': toolbarHighlight === 'check' }"
                  @click="onConsistencyCheck"
                  :loading="checkLoading"
                >
                  ✅ 一致性校验
                  <span v-if="lastCheckTimeText" style="font-size:11px;color:var(--el-text-color-secondary);margin-left:4px">({{ lastCheckTimeText }})</span>
                </el-button>
              </el-tooltip>
              <el-tooltip content="执行数据质量检查（借贷平衡/余额一致性/映射完整性）" placement="bottom">
                <el-button
                  size="small"
                  :type="toolbarHighlight === 'quality' ? 'warning' : 'default'"
                  :class="{ 'gt-tb-btn-pulse': toolbarHighlight === 'quality' }"
                  @click="showDataQualityDialog = true"
                >
                  🔍 数据质量检查
                  <el-badge v-if="dataQualityIssueCount > 0" :value="dataQualityIssueCount" :max="999" style="margin-left:4px" />
                </el-button>
              </el-tooltip>
              <el-tooltip :content="isFrozen ? '试算表已锁定，解锁后才能重算' : '从四表数据重新计算未审数、调整数、审定数（需先导入数据）'" placement="bottom">
                <el-button
                  size="small"
                  :type="isFrozen ? 'info' : (toolbarHighlight === 'recalc' ? 'primary' : 'default')"
                  :class="{ 'gt-tb-btn-pulse': !isFrozen && toolbarHighlight === 'recalc' }"
                  @click="isFrozen ? showFrozenConflictAlert() : onRecalc()"
                  :loading="recalcLoading"
                >
                  {{ isFrozen ? '🔒 已锁定' : '🔄 全量重算' }}
                </el-button>
              </el-tooltip>
              <el-tooltip :content="isFrozen ? (frozenBy ? `已锁定（${frozenBy}${frozenAt ? ' · ' + frozenAt.slice(0,10) : ''}），点击解锁` : '点击解锁试算表') : '锁定试算表，防止自动重算'" placement="bottom">
                <el-button size="small" @click="toggleFreeze" :type="isFrozen ? 'danger' : 'default'">
                  {{ isFrozen ? '🔒' : '🔓' }}
                </el-button>
              </el-tooltip>
              <el-button size="small" @click="showVersionDrawer = true" title="查看试算表版本历史（可回滚）">⏱ 版本</el-button>
              <el-dropdown size="small" trigger="click" @command="onComparisonMode">
                <el-button size="small" title="试算表跨年度/跨项目对比">📊 对比</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="cross_year">跨年度对比</el-dropdown-item>
                    <el-dropdown-item command="cross_project">跨项目对比</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </GtToolbar>
        </template>
      </GtPageHeader>

      <!-- 在线成员 [enterprise-linkage 3.2] -->
      <PresenceAvatars :project-id="projectId" view-name="trial_balance" />

      <!-- 工作流进度条 -->
      <WorkflowProgress :project-id="projectId" :year="selectedYear" @step-action="onWorkflowAction" />
    </div>

    <!-- 试算表使用说明面板 -->
    <transition name="el-zoom-in-top">
      <div v-if="showTbGuide" class="gt-tb-guide-panel">
        <div class="gt-tb-guide-panel__header">
          <span class="gt-tb-guide-panel__title">📖 试算表功能介绍与操作指南</span>
          <el-button text size="small" @click="showTbGuide = false">收起 ✕</el-button>
        </div>
        <div class="gt-tb-guide-panel__body">
          <!-- 功能简介 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">一、功能定位</h4>
            <p class="gt-tb-guide-section__text">
              试算表是审计项目的<b>数据枢纽</b>——汇聚四表库（科目余额表 tb_balance、序时账 tb_ledger、辅助余额表 tb_aux_balance）的科目数据，
              经科目映射后生成标准试算平衡表，承载<b>未审数 → 审计调整(AJE) → 重分类调整(RJE) → 审定数</b>的完整链路，
              并向下游报表生成、各循环底稿(D~N)审定表、附注披露模块提供权威取数源。
              各底稿的 <code>TB('科目码','审定数')</code> 公式均取自本页数据。
            </p>
          </div>

          <!-- 工具栏按钮详解 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">二、工具栏按钮功能详解</h4>
            <div class="gt-tb-guide-btn-list">
              <!-- 一致性校验 -->
              <div class="gt-tb-guide-btn-item">
                <div class="gt-tb-guide-btn-item__head">
                  <span class="gt-tb-guide-btn-item__badge gt-tb-guide-btn-item__badge--success">✅</span>
                  <b>一致性校验</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p><b>功能</b>：检查试算表的未审数（由四表库汇总计算得来）与四表库源数据是否严格一致。逐科目比对期初余额、本期借方发生额、本期贷方发生额、期末余额。</p>
                  <p><b>操作</b>：点击按钮后系统自动执行，结果以绿色(通过)/黄色(发现差异)横幅展示于表格上方，差异项逐条列出科目编码、期望值与实际值。按钮旁显示上次校验时间（如"3小时前✓"），方便判断是否需要重新校验。</p>
                  <p><b>智能提示</b>：若刚执行完全量重算但尚未校验，按钮会<b>自动高亮为橙色并脉冲闪烁</b>提醒你执行校验。校验通过后按钮恢复平静。</p>
                  <p><b>使用场景</b>：①导入账套数据后首次确认数据完整性；②全量重算后验证结果正确性；③发现审定数异常时溯源排查。</p>
                  <p><b>注意事项</b>：若提示不一致，常见原因为：重新导入余额表后未重算、科目映射变更后未刷新、部分科目在余额表有数据但未映射到标准科目。建议先全量重算再校验。</p>
                </div>
              </div>

              <!-- 数据质量检查 -->
              <div class="gt-tb-guide-btn-item">
                <div class="gt-tb-guide-btn-item__head">
                  <span class="gt-tb-guide-btn-item__badge gt-tb-guide-btn-item__badge--info">🔍</span>
                  <b>数据质量检查</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p><b>功能</b>：对试算表执行三大维度质量检查——①<b>借贷平衡</b>：全部科目借方合计是否等于贷方合计（试算平衡公理）；②<b>余额一致性</b>：各科目的「期初 + 借方发生 − 贷方发生 = 期末」恒等式是否成立；③<b>映射完整性</b>：是否存在有余额但未映射到报表行的"孤儿科目"。</p>
                  <p><b>操作</b>：点击按钮弹出检查结果弹窗，按维度分组展示通过/未通过项目，未通过项带具体科目编码和金额差异。映射不完整时弹窗内提供<b>「📎 跳转到映射规则修复」</b>按钮，可一步跳转到映射规则编辑页面修复问题。</p>
                  <p><b>智能提示</b>：若上次检查发现未通过项，按钮会<b>自动高亮为橙色并脉冲闪烁</b>，同时按钮上方显示问题数量角标(badge)提醒你关注。</p>
                  <p><b>使用场景</b>：生成报表前建议执行，确保试算表数据质量满足出具要求。未通过项须逐一排查修复后再生成报表。</p>
                  <p><b>注意事项</b>：借贷不平衡通常表示导入数据有缺失或重复；映射不完整会导致报表金额遗漏（资产≠负债+权益）。点击「查看诊断详情」可深入分析借贷不平衡的具体贡献科目。</p>
                </div>
              </div>

              <!-- 全量重算 -->
              <div class="gt-tb-guide-btn-item">
                <div class="gt-tb-guide-btn-item__head">
                  <span class="gt-tb-guide-btn-item__badge gt-tb-guide-btn-item__badge--primary">🔄</span>
                  <b>全量重算</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p><b>功能</b>：从四表库源数据重新汇总计算每个标准科目的未审数（期初余额、借方发生额、贷方发生额、期末余额），同时读取调整分录(AJE/RJE)计算审定数 = 未审数 + AJE + RJE。计算结果覆盖试算表现有数据。</p>
                  <p><b>计算逻辑</b>：按科目映射(account_mapping)将客户科目归集到标准科目 → 汇总余额表(tb_balance)的叶子科目(防止父子重复累加) → 按借贷方向带符号求和(资产借正/负债贷正) → 注入调整分录合计。</p>
                  <p><b>操作</b>：点击后弹出<b>确认对话框</b>，显示当前科目数量、上次重算时间、预估耗时等信息，确认后执行。完成后系统弹出<b>变动摘要通知</b>——告知影响了多少个科目、最大变动的科目及金额，方便快速评估重算影响范围。</p>
                  <p><b>智能提示</b>：当系统检测到有新的调整分录尚未反映到试算表时，按钮会<b>自动变为蓝色(primary)并脉冲闪烁</b>，文案提示"数据已过期"。锁定状态下按钮显示为「🔒 已锁定」明确告知不可操作的原因。</p>
                  <p><b>使用场景</b>：①首次生成试算表（导入+映射完成后）；②重新导入了四表数据；③修改了科目映射规则；④标题栏提示"数据已过期/待重算"时。</p>
                  <p><b>注意事项</b>：重算会覆盖未审数列，但不会覆盖手工录入的AJE/RJE（调整分录来自底稿侧/集中调整模块）。若试算表已锁定则无法重算，需先解锁。重算后建议执行一致性校验确认结果。</p>
                </div>
              </div>

              <!-- 锁定/解锁 -->
              <div class="gt-tb-guide-btn-item">
                <div class="gt-tb-guide-btn-item__head">
                  <span class="gt-tb-guide-btn-item__badge gt-tb-guide-btn-item__badge--danger">🔒</span>
                  <b>锁定 / 解锁</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p><b>功能</b>：切换试算表的锁定状态。锁定后系统不会因底稿保存、调整分录变更等上游事件自动触发重算，数据冻结不变直到手动解锁。解锁后恢复自动重算检测。<b>锁定状态全团队可见</b>——其他成员也能看到试算表已被锁定及锁定人信息。</p>
                  <p><b>操作</b>：点击后弹出<b>二次确认对话框</b>（防止误操作），确认后切换状态。锁定时按钮显示为红色🔒，解锁时显示为🔓。鼠标悬停显示锁定人和锁定时间。解锁别人锁定的试算表时会提示锁定人信息供确认。</p>
                  <p><b>使用场景</b>：①数据确认阶段——审定数已核对完毕、合伙人复核通过，为防止审计助理继续编制底稿时产生的自动重算导致数据变动，锁定冻结试算表；②生成报表/附注前——确保报表取数源不会在生成过程中被改变。</p>
                  <p><b>注意事项</b>：锁定后若有新的调整分录提交，系统会在标题栏显示"⚠ 待重算"提示但不自动执行。解锁并重算后才会反映最新调整。项目归档后试算表自动锁定不可解锁。锁定状态持久化在服务端，换设备/换浏览器仍有效。</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 右上角操作按钮 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">三、右上角操作按钮</h4>
            <div class="gt-tb-guide-btn-list">
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>📋 复制整表</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p>一键将试算表数据复制到剪贴板（制表符分隔），可直接粘贴到 Word 或 Excel。复制内容包含全部可见列的数据行。</p>
                </div>
              </div>
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>🖥 全屏</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p>切换全屏模式，表格铺满整个浏览器窗口（隐藏左侧导航和顶部横幅），适合大屏核对数据。再次点击或按 Esc 退出。</p>
                </div>
              </div>
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>📐 公式管理</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p>打开公式管理中心，查看和编辑各底稿/报表引用试算表数据的公式（如 <code>TB('1001','期末余额')</code>）。可管理自动运算/逻辑审核/合理性检查三类公式。</p>
                </div>
              </div>
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>📤 导出Excel / 📥 Excel导入</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p><b>导出</b>：将科目明细导出为格式化的 xlsx 文件（含期初/未审/调整/审定各列）。<b>导入</b>：上传 xlsx 覆盖更新试算表数据（适用于客户提供新余额表或手工修正个别科目）。导入前建议先导出备份。项目归档状态下导入按钮禁用。</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 三种视图 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">四、三种视图说明</h4>
            <div class="gt-tb-guide-grid">
              <div class="gt-tb-guide-card">
                <div class="gt-tb-guide-card__icon">📋</div>
                <div class="gt-tb-guide-card__name">科目明细</div>
                <div class="gt-tb-guide-card__desc">
                  按标准科目编码逐行展示。列包含：行次、科目名称、未审数（期初/借方/贷方/期末）、审计调整（借方/贷方）、重分类调整（借方/贷方）、审定数。
                  支持排序/筛选/搜索。适合逐科目核对数据、确认调整分录是否正确反映。
                </div>
              </div>
              <div class="gt-tb-guide-card">
                <div class="gt-tb-guide-card__icon">📊</div>
                <div class="gt-tb-guide-card__name">试算平衡表</div>
                <div class="gt-tb-guide-card__desc">
                  按报表项目行次（资产负债表 BS/利润表 IS/现金流量表 CFS/所有者权益变动表 EQ）汇总展示。
                  表头对齐审计报告附表格式。支持按表切换、刷新、导出（含数据/空模板）、导入、保存。
                  每行审定数 = 下属科目审定数之和（遵循映射规则）。
                </div>
              </div>
              <div class="gt-tb-guide-card">
                <div class="gt-tb-guide-card__icon">🔗</div>
                <div class="gt-tb-guide-card__name">映射规则</div>
                <div class="gt-tb-guide-card__desc">
                  管理「客户科目 → 标准科目 → 报表项目」的映射关系。支持一键预设（按企业类型自动分配）、AI 智能匹配、手动拖拽调整。
                  映射变更后需全量重算才能生效。映射不完整会导致报表金额遗漏。
                </div>
              </div>
            </div>
          </div>

          <!-- 操作流程 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">五、完整操作流程</h4>
            <div class="gt-tb-guide-steps">
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num">1</span>
                <div class="gt-tb-guide-step__content">
                  <b>导入四表数据</b>
                  <span>在「查账」页面上传科目余额表（必填，xlsx/csv）和序时账（强烈推荐，供底稿截止测试/抽凭/大额分析使用）。系统自动识别列头映射字段。导入成功后回到试算表页面。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num">2</span>
                <div class="gt-tb-guide-step__content">
                  <b>科目映射（自动+手工）</b>
                  <span>点击「🔗 映射规则」按钮 → 弹窗内点「一键预设」自动按科目编码规则匹配（1xxx=资产/2xxx=负债/4xxx=权益/5xxx=成本/6xxx=损益）。若自动匹配不准确可手动修正个别科目的归属报表项目。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num">3</span>
                <div class="gt-tb-guide-step__content">
                  <b>全量重算 → 生成试算表</b>
                  <span>点击「🔄 全量重算」，系统从余额表汇总各标准科目的未审数，并注入已有调整分录计算审定数。首次需要几秒钟。完成后表格自动刷新。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num">4</span>
                <div class="gt-tb-guide-step__content">
                  <b>一致性校验 + 数据质量检查</b>
                  <span>点击「✅ 一致性校验」确认试算表与源数据一致。再点「🔍 数据质量检查」确认借贷平衡、余额恒等式成立、无孤儿科目。两项都通过才可进入下一步。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num">5</span>
                <div class="gt-tb-guide-step__content">
                  <b>编制底稿 → 调整分录同步</b>
                  <span>审计团队在各科目底稿(D~N循环)编制实质性程序时，发现需调整项目→在底稿调整分录tab录入AJE/RJE→同步到集中调整登记→试算表自动反映新增调整数（或手动重算）。审定数 = 未审数 + AJE + RJE。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num">6</span>
                <div class="gt-tb-guide-step__content">
                  <b>锁定试算表 → 生成报表</b>
                  <span>全部审定数确认后，点🔒锁定试算表冻结数据。然后进入报表模块生成资产负债表/利润表/现金流量表等（报表公式自动从试算表审定数取值）。最后生成附注。</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 表格列含义 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">六、表格各列含义</h4>
            <div class="gt-tb-guide-table-wrap">
              <table class="gt-tb-guide-table">
                <thead>
                  <tr>
                    <th>列名</th>
                    <th>含义</th>
                    <th>数据来源</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>行次</td><td>报表行次编码（如 BS-001）</td><td>科目映射规则</td></tr>
                  <tr><td>项目</td><td>标准科目/报表项目名称</td><td>标准科目表</td></tr>
                  <tr><td>未审数</td><td>审计前客户账面金额（= 期初 + 借方发生 − 贷方发生）</td><td>余额表汇总计算</td></tr>
                  <tr><td>审计调整 · 借方 / 贷方</td><td>审计发现的错报调整分录(AJE)</td><td>底稿/集中调整登记</td></tr>
                  <tr><td>重分类调整 · 借方 / 贷方</td><td>重新分类列报调整(RJE)</td><td>底稿/集中调整登记</td></tr>
                  <tr><td>审定数</td><td>最终审定金额 = 未审数 + AJE净额 + RJE净额</td><td>系统自动计算</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 智能引导提示 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">七、智能引导提示</h4>
            <p class="gt-tb-guide-section__text">
              系统会根据试算表当前状态<b>自动高亮最需要操作的按钮</b>（变色 + 脉冲闪烁），引导你按正确顺序操作：
            </p>
            <div class="gt-tb-guide-steps">
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num" style="background:#409eff">!</span>
                <div class="gt-tb-guide-step__content">
                  <b>🔄 全量重算 变蓝色闪烁</b>
                  <span>含义：系统检测到有新的调整分录或数据变更尚未反映到试算表（数据过期）。建议立即点击重算。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num" style="background:#e6a23c">!</span>
                <div class="gt-tb-guide-step__content">
                  <b>🔍 数据质量检查 变橙色闪烁</b>
                  <span>含义：上次质量检查发现有未通过的检查项（如借贷不平衡/映射不完整），需要关注和修复。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num" style="background:#e6a23c">!</span>
                <div class="gt-tb-guide-step__content">
                  <b>✅ 一致性校验 变橙色闪烁</b>
                  <span>含义：刚执行了全量重算但尚未重新校验一致性（重算可能改动了数据，需验证）。校验通过后恢复平静。</span>
                </div>
              </div>
              <div class="gt-tb-guide-step">
                <span class="gt-tb-guide-step__num" style="background:#67c23a">✓</span>
                <div class="gt-tb-guide-step__content">
                  <b>全部按钮无高亮（平静态）</b>
                  <span>含义：数据新鲜、无质量问题、一致性已验证——当前无需操作，可安心编制底稿或生成报表。</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 高级功能 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">八、高级功能</h4>
            <div class="gt-tb-guide-btn-list">
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>🔍 科目级穿透追溯</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p>点击任意科目的<b>审定数</b>单元格（带虚线下划线），弹出该科目完整溯源链：四表库叶子科目汇总 → 科目映射+全量重算 → 未审数 → AJE调整（金额+来源） → RJE调整（金额+来源） → 最终审定数。如果该科目在本次重算中有变动，还会显示△变动金额。</p>
                  <p><b>用途</b>：审计师/复核人快速理解"这个数怎么来的"，无需翻查多个页面。排查"审定数为何不等于我预期"的首选工具。</p>
                </div>
              </div>
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>△ 重算差异标记</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p>每次全量重算后，系统自动标记所有<b>审定数发生变动的行</b>——行首显示橙色「△」符号，审定数右侧也显示△角标。标记持续到下次重算或页面刷新。</p>
                  <p><b>用途</b>：一眼看清重算影响了哪些科目，无需逐行对比前后数据。配合穿透追溯可查看具体变动金额。</p>
                </div>
              </div>
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>🚫 多人协作锁定冲突提示</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p>当试算表被他人锁定后，你点击「全量重算」或「导入」时系统会弹出<b>醒目的提示弹窗</b>（而非仅按钮灰色），明确告知锁定人、锁定时间以及操作建议（联系锁定人或有权限成员解锁）。</p>
                  <p><b>用途</b>：防止审计师困惑"为什么重算按钮点了没反应"——弹窗比 tooltip 更醒目不会错过。</p>
                </div>
              </div>
              <div class="gt-tb-guide-btn-item gt-tb-guide-btn-item--compact">
                <div class="gt-tb-guide-btn-item__head">
                  <b>⚠️ 导出前自动质量检查</b>
                </div>
                <div class="gt-tb-guide-btn-item__desc">
                  <p>点击「导出Excel」时，若当前有未通过的数据质量检查（如借贷不平衡/映射不完整），系统会弹出<b>确认对话框</b>提醒"导出数据可能不准确"，并提供"取消，去修复"快捷入口直接打开质量检查弹窗。</p>
                  <p><b>用途</b>：防止将有问题的试算表导出给客户或归档，确保对外输出数据的质量底线。</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 常见问题 -->
          <div class="gt-tb-guide-section">
            <h4 class="gt-tb-guide-section__title">九、常见问题与注意事项</h4>
            <ul class="gt-tb-guide-notes">
              <li>❓ <b>导入后试算表仍为空</b>：需先完成科目映射再全量重算，试算表不会自动从余额表生成</li>
              <li>❓ <b>重算后某科目金额翻倍</b>：检查余额表是否有父子科目同时导入（系统会汇总叶子科目防双算，但同一科目编码在多个数据集重复时可能累加）</li>
              <li>❓ <b>审定数不反映最新调整分录</b>：可能试算表已锁定，先解锁再重算；或调整分录尚未同步到集中登记</li>
              <li>❓ <b>报表金额与试算表不一致</b>：检查映射规则——可能有科目未映射（报表遗漏）或映射到错误报表行</li>
              <li>❓ <b>借贷不平衡</b>：说明导入数据有缺失科目或金额错误，需回到账套导入核对源余额表</li>
              <li>⚠️ <b>权限说明</b>：全量重算/导入/锁定需要编辑权限（现场经理及以上角色）；只读用户可查看/导出/校验但不能修改数据</li>
              <li>⚠️ <b>单位统一</b>：金额单位（元/万元/千元）在页面顶部标题栏的「单位」处全局切换，试算表各列和所有引用它的公式自动跟随</li>
              <li>⚠️ <b>期初/期末切换</b>：科目明细表支持切换「期末试算」与「期初试算」两种视角，注意查看的是哪个时点的数据</li>
            </ul>
          </div>
        </div>
      </div>
    </transition>

    <!-- 归档横幅 -->
    <ArchivedBanner />
    <ConsolLockedBanner />

    <!-- 折叠/展开按钮 -->
    <div class="gt-header-toggle" @click="headerCollapsed = !headerCollapsed">
      <span>{{ headerCollapsed ? '▼ 展开工具栏' : '▲ 收起工具栏' }}</span>
    </div>

    <!-- 视图切换：科目明细 / 试算平衡表 / 映射规则 -->
    <div style="display:flex;gap:0;margin-bottom:8px;border-bottom:2px solid var(--gt-color-border-purple);align-items:center">
      <el-tooltip placement="bottom" :show-after="500">
        <template #content>
          <div style="max-width: 280px; line-height: 1.6">
            <b>科目明细</b><br>
            按科目编码逐行展示期初、AJE调整、RJE重分类、审定数。<br>
            <span style="color: var(--gt-color-wheat)">适用：逐科目核对数据、录入调整分录</span>
          </div>
        </template>
        <span class="gt-tb-view-tag" :class="{ 'gt-tb-view-tag--active': tbViewMode === 'detail' }" @click="tbViewMode = 'detail'">科目明细</span>
      </el-tooltip>
      <el-tooltip placement="bottom" :show-after="500">
        <template #content>
          <div style="max-width: 280px; line-height: 1.6">
            <b>试算平衡表</b><br>
            按报表行次（资产负债表/利润表）汇总展示，对应审计报告附表格式。<br>
            <span style="color: var(--gt-color-wheat)">适用：出具报表前核对借贷平衡、查看审定后报表数</span>
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
        <el-button size="small" @click="triggerTbSumImport" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">📥 导入</el-button>
        <input ref="tbSumImportInput" type="file" accept=".xlsx,.xls" style="display:none" @change="onTbSumImportFile" />
        <el-button size="small" @click="saveTbSummary" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">💾 保存</el-button>
        <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary);margin-left:12px">{{ tbSummaryRows.length }} 行</span>
      </template>
      <!-- 科目明细工具栏（导出/导入） -->
      <template v-if="tbViewMode === 'detail'">
        <span style="flex:1" />
        <el-button size="small" @click="onExport">📤 导出Excel</el-button>
        <el-button size="small" @click="onToolbarImport" :disabled="!canEdit" :title="!canEdit ? '项目已归档，无法编辑' : ''">📥 Excel导入</el-button>
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
      <div v-if="!consistencyResult.consistent && consistencyResult.issues.length > 0" style="font-size: var(--gt-font-size-xs); line-height: 1.8; margin-top: 4px">
        <div v-for="(issue, idx) in consistencyResult.issues.slice(0, 5)" :key="idx" style="padding: 2px 0">
          · {{ (issue as any).message || (issue as any).description || JSON.stringify(issue) }}
        </div>
        <div v-if="consistencyResult.issues.length > 5" style="color: var(--gt-color-info); margin-top: 4px">
          还有 {{ consistencyResult.issues.length - 5 }} 项未显示
        </div>
      </div>
    </el-alert>

    <!-- Sprint 4：StaleIndicator 统一组件 + 数据新鲜度提示 -->
    <div v-if="isStale && rows.length > 0" class="gt-stale-banner">
      <StaleIndicator :stale="true" tooltip="数据已过期，请刷新" />
      <span class="gt-stale-text">
        {{ isFrozen ? '试算表已锁定，不会自动重算' : '数据已过期，请刷新（检测到新调整分录）' }}
      </span>
      <el-button v-if="!isFrozen" size="small" type="primary" :loading="recalcLoading" @click="onRecalc">
        立即刷新
      </el-button>
      <div v-if="latestAdjustmentAt" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-info); margin-left: 12px">
        最新调整：{{ displayPrefs.fmtDateTime(latestAdjustmentAt) }}
      </div>
    </div>

    <!-- useStaleRefresh：上游变更事件横幅 -->
    <div v-if="staleRefresh.isStale.value && !isStale" class="gt-stale-banner">
      <StaleIndicator :stale="true" tooltip="上游数据已变更" />
      <span class="gt-stale-text">上游数据已变更，建议重新加载试算表</span>
      <el-button size="small" type="primary" @click="staleRefresh.refresh()">刷新数据</el-button>
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
        <div v-if="setupCurrentStep === 1" style="margin-top: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-info)">
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
            <div style="font-size: var(--gt-font-size-sm); color: var(--gt-color-info); margin-bottom: 12px">
              请先在「查账」页面导入科目余额表和序时账
            </div>
            <el-button type="primary" @click="goToLedgerImport">
              前往导入账套数据
            </el-button>
          </el-empty>
        </div>
      </div>
    </el-dialog>

    <!-- #6: 健康度仪表盘概览卡 -->
    <div class="gt-tb-health-dashboard" v-if="!loading && rows.length > 0 && !showSetupGuide">
      <div class="gt-tb-health-card">
        <span class="gt-tb-health-card__value">{{ rows.length }}</span>
        <span class="gt-tb-health-card__label">科目数</span>
      </div>
      <div class="gt-tb-health-card" v-if="materialityLevels.pm > 0">
        <span class="gt-tb-health-card__value gt-tb-health-card__value--accent">{{ materialExceedsCount }}</span>
        <span class="gt-tb-health-card__label">超重要性</span>
      </div>
      <div class="gt-tb-health-card">
        <span class="gt-tb-health-card__value">{{ adjSummary.count }}</span>
        <span class="gt-tb-health-card__label">有调整科目</span>
      </div>
      <div class="gt-tb-health-card" :class="{ 'gt-tb-health-card--ok': isBalanced, 'gt-tb-health-card--err': !isBalanced }">
        <span class="gt-tb-health-card__value">{{ isBalanced ? '✓' : '✗' }}</span>
        <span class="gt-tb-health-card__label">{{ isBalanced ? '借贷平衡' : '不平衡' }}</span>
      </div>
    </div>

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
    <div v-if="tbViewMode === 'detail' && !comparisonActive && staleAccountCodes.size > 0" style="margin-bottom: 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-info); display: flex; align-items: center; gap: 6px">
      <span style="display: inline-block; width: 14px; height: 14px; background: var(--gt-bg-warning); border-left: 3px solid var(--gt-color-wheat); border-radius: 2px"></span>
      <span>黄底行 = 有新调整分录待重算</span>
    </div>
    <el-table
      ref="tbTableRef"
      v-if="tbViewMode === 'detail' && !comparisonActive"
      :data="groupedRows"
      v-loading="loading"
      border
      stripe
      :max-height="tableMaxHeight"
      style="width: 100%"
      :class="`gt-tb-font-${displayPrefs.fontSize} gt-compact-table`"
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
            <el-icon style="margin-left:2px; font-size: var(--gt-font-size-xs); vertical-align:middle"><Link /></el-icon>
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
          <GtAmountCell v-if="!row._isSubtotal && !row._isTotal"
            :value="row.unadjusted_amount"
            clickable @click="onUnadjustedClick(row)"
          />
          <GtAmountCell v-else :value="row.unadjusted_amount" />
          </CommentTooltip>
        </template>
      </el-table-column>
      <el-table-column label="RJE调整" width="150" align="right" class-name="gt-amt-col">
        <template #default="{ row }">
          <GtAmountCell v-if="!row._isSubtotal && !row._isTotal && row.rje_adjustment !== '0'"
            :value="row.rje_adjustment"
            clickable @click="onAdjClick(row, 'rje')"
          />
          <GtAmountCell v-else :value="row.rje_adjustment" />
        </template>
      </el-table-column>
      <el-table-column label="AJE调整" width="150" align="right" class-name="gt-amt-col">
        <template #default="{ row }">
          <GtAmountCell v-if="!row._isSubtotal && !row._isTotal && row.aje_adjustment !== '0'"
            :value="row.aje_adjustment"
            clickable @click="onAdjClick(row, 'aje')"
          />
          <GtAmountCell v-else :value="row.aje_adjustment" />
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
          <span
            v-if="!row._isSubtotal && !row._isTotal"
            class="gt-trace-clickable"
            @click="openTraceDialog(row)"
            title="点击查看溯源链"
          >
            <GtAmountCell :value="row.audited_amount" />
            <span v-if="recalcDiffMap.has(row.standard_account_code)" class="gt-trace-diff-badge">△</span>
          </span>
          <GtAmountCell v-else :value="row.audited_amount" />
          </CommentTooltip>
        </template>
      </el-table-column>
      <el-table-column label="底稿状态" width="120" align="center" :header-cell-style="{ whiteSpace: 'nowrap' }">
        <template #default="{ row }">
          <el-tooltip v-if="row.wp_consistency?.status === 'consistent'" content="底稿审定数一致" placement="top">
            <span style="color: var(--gt-color-success); cursor: pointer" @dblclick="openWorkpaper(row)">✅</span>
          </el-tooltip>
          <el-tooltip v-else-if="row.wp_consistency?.status === 'stale'" content="上游数据已变更，点击重算">
            <span style="color: var(--gt-color-teal, #009688); cursor: pointer" @click="onRecalcWp(row)">🔄</span>
          </el-tooltip>
          <el-tooltip v-else-if="row.wp_consistency?.status === 'inconsistent'" :content="`差异 ${row.wp_consistency.diff_amount}`" placement="top">
            <span style="color: var(--gt-color-coral); cursor: pointer" @dblclick="openWorkpaper(row)">⚠️</span>
          </el-tooltip>
          <span v-else style="color: var(--gt-color-text-placeholder)">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 试算平衡表视图（报表行次级别） -->
    <div v-if="tbViewMode === 'summary' && !comparisonActive">
      <!-- 期初/期末切换 — 胶囊分段控制器 -->
      <div style="display:flex;gap:12px;margin-bottom:8px;align-items:center">
        <div class="gt-period-segmented">
          <span
            class="gt-period-segmented__item"
            :class="{ 'gt-period-segmented__item--active': tbSumPeriod === 'ending' }"
            @click="tbSumPeriod = 'ending'; loadTbSummary()"
          >期末试算</span>
          <span
            class="gt-period-segmented__item"
            :class="{ 'gt-period-segmented__item--active': tbSumPeriod === 'opening' }"
            @click="tbSumPeriod = 'opening'; loadTbSummary()"
          >期初试算</span>
        </div>
        <span v-if="tbSumPeriod === 'opening'" style="font-size: var(--gt-font-size-xs);color: var(--gt-color-wheat)">
          {{ tbSumOpeningSource === 'prior_year' ? '📎 数据来源：上年审定数' : '✏️ 首次承接：手动填写' }}
        </span>
      </div>
      <!-- 报表类型切换 -->
      <div style="display:flex;gap:0;margin-bottom:8px;border-bottom:2px solid var(--gt-color-border-purple)">
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
        <el-button
          size="small"
          :type="tbSumShowVariance ? 'primary' : 'default'"
          @click="tbSumShowVariance = !tbSumShowVariance"
          title="显示/隐藏变动分析列（调整净额+调整率）"
        >📊 变动</el-button>
        <el-button
          size="small"
          :type="tbSumCollapseAdj ? 'primary' : 'default'"
          @click="tbSumCollapseAdj = !tbSumCollapseAdj"
          title="折叠/展开审计调整和重分类调整的借贷明细列"
        >{{ tbSumCollapseAdj ? '展开调整列' : '折叠调整列' }}</el-button>
        <span style="flex:1" />
        <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary);align-self:center">审计调整从调整分录自动汇总 · 审定数=未审数+调整借-贷+重分类借-贷</span>
      </div>
      <!-- P1-5: 快捷筛选按钮组 -->
      <div class="gt-tb-filter-bar" v-if="tbSummaryRows.length">
        <el-button-group size="small">
          <el-button :type="tbSumFilter === 'all' ? 'primary' : 'default'" @click="tbSumFilter = 'all'">全部</el-button>
          <el-button :type="tbSumFilter === 'has_adj' ? 'primary' : 'default'" @click="tbSumFilter = 'has_adj'">有调整</el-button>
          <el-button :type="tbSumFilter === 'has_diff' ? 'primary' : 'default'" @click="tbSumFilter = 'has_diff'">审定≠未审</el-button>
          <el-button :type="tbSumFilter === 'material' ? 'primary' : 'default'" @click="tbSumFilter = 'material'">金额重大</el-button>
          <el-button :type="tbSumFilter === 'zero_unadj' ? 'primary' : 'default'" @click="tbSumFilter = 'zero_unadj'">未审为0</el-button>
        </el-button-group>
        <span style="font-size:11px;color:var(--gt-color-text-quaternary);margin-left:8px">{{ filteredTbSummaryRows.length }}/{{ tbSummaryRows.length }} 行</span>
      </div>
      <div :class="`gt-tb-font-${displayPrefs.fontSize}`">
        <el-table
          ref="tbSummaryTableRef"
          :data="filteredTbSummaryRows"
          border
          class="gt-compact-table"
          :max-height="tbSummaryMaxHeight"
          style="width: 100%"
          :row-class-name="tbSumRowClassName"
          :cell-class-name="tbSumCellClassName"
          :cell-style="{ padding: '0 8px' }"
          highlight-current-row
          @cell-click="onTbSumCellClick"
          @row-contextmenu="onTbSumElContextMenu"
          @row-dblclick="onTbSumElDblClick"
        >
          <el-table-column prop="row_code" label="行次" width="110" align="center">
            <template #default="{ row }">
              <span style="color: var(--gt-color-text-tertiary);font-size: var(--gt-font-size-xs);white-space:nowrap">{{ row.row_code }}</span>
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
              <span v-else-if="row.unadjusted == null && !row.is_total && !row.is_category" class="gt-tb-nomap" title="该报表行无对应科目映射（不适用）">—</span>
              <span v-else class="gt-amt">
                <el-tooltip v-if="row._formula" :content="'ƒx ' + row._formula" placement="top" :show-after="500">
                  <span>{{ fmt(row.unadjusted) }}</span>
                </el-tooltip>
                <template v-else>{{ fmt(row.unadjusted) }}</template>
              </span>
            </template>
          </el-table-column>
          <el-table-column v-if="!tbSumCollapseAdj" label="审计调整" header-align="center">
            <el-table-column prop="aje_dr" label="借方" width="120" align="right">
              <template #default="{ row }">
                <GtAmountCell v-if="row.aje_dr" class="gt-tb-readonly" :value="row.aje_dr" />
                <span v-else-if="!row.is_total && !row.is_category && row.unadjusted != null" class="gt-tb-quick-adj" @click="onQuickAdjEntry(row)" title="快速录入调整分录">+</span>
              </template>
            </el-table-column>
            <el-table-column prop="aje_cr" label="贷方" width="120" align="right">
              <template #default="{ row }">
                <GtAmountCell v-if="row.aje_cr" class="gt-tb-readonly" :value="row.aje_cr" />
                <span v-else-if="!row.is_total && !row.is_category && row.unadjusted != null && !row.aje_dr" class="gt-tb-quick-adj" @click="onQuickAdjEntry(row)" title="快速录入调整分录">+</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column v-if="!tbSumCollapseAdj" label="重分类调整" header-align="center">
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
                <span v-else class="gt-tb-editable" @click="tbSumLazyEdit.startEdit($index, 2)">
                  <GtAmountCell :value="row.rcl_dr" />
                </span>
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
                <span v-else class="gt-tb-editable" @click="tbSumLazyEdit.startEdit($index, 3)">
                  <GtAmountCell :value="row.rcl_cr" />
                </span>
              </template>
            </el-table-column>
          </el-table-column>
          <!-- P2-13: 折叠时只显示一列调整净额 -->
          <el-table-column v-if="tbSumCollapseAdj" label="调整净额" width="130" align="right">
            <template #default="{ row }">
              <GtAmountCell :value="(Number(row.aje_dr) || 0) - (Number(row.aje_cr) || 0) + (Number(row.rcl_dr) || 0) - (Number(row.rcl_cr) || 0)" />
            </template>
          </el-table-column>
          <el-table-column prop="audited" label="审定数" width="140" align="right" class-name="gt-tb-sum-audited-col">
            <template #default="{ row }">
              <span v-if="row.audited == null && !row.unadjusted && !row.is_total && !row.is_category" class="gt-tb-nomap" title="该报表行无对应科目映射（不适用）">—</span>
              <span v-else-if="row.audited == null && row.unadjusted != null" class="gt-tb-pending" title="有未审数但审定数未计算，请检查调整或重算">
                <el-icon style="font-size:12px;vertical-align:middle"><WarningFilled /></el-icon>
              </span>
              <GtAmountCell v-else :value="row.audited" />
            </template>
          </el-table-column>
          <!-- P2-9: 变动分析（调整净额=审定-未审） -->
          <el-table-column v-if="tbSumShowVariance" label="调整净额" width="120" align="right" class-name="gt-tb-sum-variance-col">
            <template #default="{ row }">
              <template v-if="!row.is_total && !row.is_category && row.unadjusted != null && row.audited != null">
                <span :class="{ 'gt-tb-var-warn': Math.abs(Number(row.audited) - Number(row.unadjusted)) > 0.01 }" :style="{ color: (Number(row.audited) - Number(row.unadjusted)) < 0 ? 'var(--gt-color-coral)' : '' }">
                  {{ fmt(Number(row.audited) - Number(row.unadjusted)) }}
                  <el-tooltip v-if="materialityLevels.sat > 0 && Math.abs(Number(row.audited) - Number(row.unadjusted)) > materialityLevels.sat" content="调整金额超微小错报阈值(SAT)，可能构成未更正错报" placement="top">
                    <span style="color:var(--el-color-warning);margin-left:2px">⚠</span>
                  </el-tooltip>
                </span>
              </template>
            </template>
          </el-table-column>
          <el-table-column v-if="tbSumShowVariance" label="调整率" width="80" align="right">
            <template #default="{ row }">
              <template v-if="!row.is_total && !row.is_category && row.unadjusted != null && row.audited != null && Number(row.unadjusted) !== 0">
                <span :class="{
                  'gt-tb-var-warn': Math.abs((Number(row.audited) - Number(row.unadjusted)) / Number(row.unadjusted)) > 0.3,
                  'gt-tb-var-danger': Math.abs((Number(row.audited) - Number(row.unadjusted)) / Number(row.unadjusted)) > 0.5,
                }">
                  {{ ((Number(row.audited) - Number(row.unadjusted)) / Math.abs(Number(row.unadjusted)) * 100).toFixed(1) }}%
                </span>
              </template>
            </template>
          </el-table-column>
          <!-- P2-4: 行级操作列 — 收敛为单个「更多」下拉，hover 才显示 -->
          <el-table-column label="" width="52" align="center" fixed="right" class-name="gt-tb-row-actions">
            <template #default="{ row }">
              <el-dropdown v-if="!row.is_total && !row.is_category" trigger="click" @command="(cmd: string) => onRowActionCommand(cmd, row)">
                <el-button link size="small" class="gt-tb-row-actions__trigger">
                  <el-icon :size="14"><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="formula"><span style="margin-right:6px">ƒx</span>查看公式</el-dropdown-item>
                    <el-dropdown-item command="trace"><span style="margin-right:6px">🔍</span>数据溯源</el-dropdown-item>
                    <el-dropdown-item command="workpaper"><span style="margin-right:6px">📋</span>定位底稿</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
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

    <!-- #10: 对比视图（激活时替代主表） -->
    <TbComparisonView
      v-if="comparisonActive"
      :project-id="projectId"
      :year="year"
      :current-rows="rows"
      :initial-mode="comparisonMode"
      @close="comparisonActive = false"
    />

    <!-- 选中区域状态栏 -->
    <SelectionBar v-if="!comparisonActive" :stats="tbViewMode === 'summary' ? tbSumCtx.selectionStats() : tbCtx.selectionStats()" />

    <!-- 恒等式校验栏（P0-1：资产=负债+权益 完整展示） -->
    <div class="gt-tb-balance-bar" v-if="!loading && tbViewMode === 'summary' && !comparisonActive && tbSummaryRows.length">
      <div class="gt-tb-balance-bar__equation">
        <span class="gt-tb-balance-bar__term">
          <span class="gt-tb-balance-bar__label">资产合计</span>
          <span class="gt-tb-balance-bar__value">{{ fmt(balanceEquation.assetTotal) }}</span>
        </span>
        <span class="gt-tb-balance-bar__op">=</span>
        <span class="gt-tb-balance-bar__term">
          <span class="gt-tb-balance-bar__label">负债合计</span>
          <span class="gt-tb-balance-bar__value">{{ fmt(balanceEquation.liabilityTotal) }}</span>
        </span>
        <span class="gt-tb-balance-bar__op">+</span>
        <span class="gt-tb-balance-bar__term">
          <span class="gt-tb-balance-bar__label">权益合计</span>
          <span class="gt-tb-balance-bar__value">{{ fmt(balanceEquation.equityTotal) }}</span>
        </span>
        <span class="gt-tb-balance-bar__divider"></span>
        <span class="gt-tb-balance-bar__result" :class="isBalanced ? 'gt-tb-balance-bar__result--ok' : 'gt-tb-balance-bar__result--err'">
          <template v-if="isBalanced">✓ 平衡</template>
          <template v-else>✗ 差额 {{ fmt(Math.abs(balanceEquation.diff)) }}</template>
        </span>
      </div>
      <div v-if="hasPnlRows" class="gt-tb-balance-bar__note">
        含未结转损益类科目，借方合计 {{ fmt(trialBalanceTotals.debit) }} / 贷方合计 {{ fmt(trialBalanceTotals.credit) }}
      </div>
    </div>
    <!-- P1-8: 重要性水平参照条 -->
    <div class="gt-tb-materiality-bar" v-if="!loading && materialityLevels.pm > 0">
      <span class="gt-tb-materiality-bar__item">
        <span class="gt-tb-materiality-bar__dot gt-tb-materiality-bar__dot--pm"></span>
        PM {{ fmt(materialityLevels.pm) }}
      </span>
      <span class="gt-tb-materiality-bar__item">
        <span class="gt-tb-materiality-bar__dot gt-tb-materiality-bar__dot--te"></span>
        TE {{ fmt(materialityLevels.te) }}
      </span>
      <span class="gt-tb-materiality-bar__item" v-if="materialityLevels.sat > 0">
        <span class="gt-tb-materiality-bar__dot gt-tb-materiality-bar__dot--sat"></span>
        SAT {{ fmt(materialityLevels.sat) }}
      </span>
      <span class="gt-tb-materiality-bar__hint">审定数 &gt; PM 的行加粗显示</span>
    </div>
    <div class="gt-tb-materiality-bar gt-tb-materiality-bar--empty" v-else-if="!loading && materialityLevels.pm === 0 && rows.length > 0">
      <span style="color:var(--gt-color-text-quaternary);font-size:11px">⚠ 重要性水平未设定 —</span>
      <el-button text size="small" @click="router.push(`/projects/${projectId}/materiality`)">前往 B15 设定</el-button>
    </div>
    <!-- 借贷平衡指示器（科目明细视图） -->
    <div class="gt-tb-balance-indicator" v-if="!loading && tbViewMode === 'detail' && !comparisonActive">
      <el-tooltip :content="balanceTooltip" placement="top">
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
          <template #default="{ row }"><GtAmountCell :value="row.total_debit" /></template>
        </el-table-column>
        <el-table-column prop="total_credit" label="贷方" width="130" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.total_credit" /></template>
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
          <span style="font-size: var(--gt-font-size-sm)">匹配成功</span>
        </div>
        <div style="display: flex; align-items: center; gap: 12px">
          <el-badge :value="mappingResult.needConfirm" type="warning" />
          <span style="font-size: var(--gt-font-size-sm)">需手动确认</span>
        </div>
        <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-info); margin-top: 4px">
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
      scope="tb"
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
    @trust-score="onTbCtxTrustScore"
    @sum="onTbCtxSum"
    @compare="onTbCtxCompare"
  >
    <div class="gt-ucell-ctx-item" @click="onTbCtxDrillDown"><span class="gt-ucell-ctx-icon">📊</span> 查看明细</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxTrace"><span class="gt-ucell-ctx-icon">🔍</span> 数据溯源</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxOpenWp"><span class="gt-ucell-ctx-icon">📝</span> 打开底稿</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxViewAdj"><span class="gt-ucell-ctx-icon">📋</span> 查看调整分录</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxViewLinkedWp"><span class="gt-ucell-ctx-icon">🔗</span> 查看关联底稿</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxViewReferences"><span class="gt-ucell-ctx-icon">🔎</span> 查看引用方</div>
    <div class="gt-ucell-ctx-item" @click="onTbCtxCellTrace"><span class="gt-ucell-ctx-icon">🔍</span> 数字溯源</div>
  </CellContextMenu>

  <!-- V3 Req 9.6: 数字信任度面板 -->
  <TrustScorePanel ref="trustScorePanelRef" :project-id="projectId" />

  <!-- Sprint 5.8: 引用方弹窗 -->
  <CellFormulaDetail
    :visible="showCellFormulaDetail"
    module="TB"
    :wp-code="cellDetailWpCode"
    :sheet-name="cellDetailSheet"
    :label="cellDetailLabel"
    @update:visible="showCellFormulaDetail = $event"
    @navigate="onCellDetailNavigate"
  />

  <!-- 数字溯源弹窗（lineage endpoint） -->
  <el-dialog v-model="tbTraceDialogVisible" title="🔍 数字溯源" width="700px" append-to-body destroy-on-close>
    <div v-loading="tbTraceLoading" style="min-height:120px">
      <template v-if="tbTraceResult">
        <div v-if="tbTraceResult.upstream.length || tbTraceResult.downstream.length">
          <h4 style="margin:0 0 8px">上游来源</h4>
          <el-table v-if="tbTraceResult.upstream.length" :data="tbTraceResult.upstream" size="small" border stripe max-height="200">
            <el-table-column prop="wp_code" label="底稿编码" width="120" />
            <el-table-column prop="label" label="描述" min-width="200" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="onTbTraceLocate(row)">定位</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无上游来源" :image-size="40" />
          <h4 style="margin:16px 0 8px">下游引用</h4>
          <el-table v-if="tbTraceResult.downstream.length" :data="tbTraceResult.downstream" size="small" border stripe max-height="200">
            <el-table-column prop="wp_code" label="底稿编码" width="120" />
            <el-table-column prop="label" label="描述" min-width="200" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="onTbTraceLocate(row)">定位</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无下游引用" :image-size="40" />
        </div>
        <el-empty v-else description="该数字暂无溯源信息" :image-size="60" />
      </template>
    </div>
  </el-dialog>

  <DataQualityDialog
    v-model="showDataQualityDialog"
    :project-id="projectId"
    :year="year"
    @jump-to-mapping="showDataQualityDialog = false; showMappingDialog = true"
  />

  <!-- #9: 版本时光机抽屉 -->
  <TbVersionDrawer
    :project-id="projectId"
    :year="year"
    :visible="showVersionDrawer"
    @close="showVersionDrawer = false"
    @restored="onVersionRestored"
  />

  <!-- 科目级穿透追溯弹窗 -->
  <el-dialog v-model="traceDialogVisible" title="科目审定数溯源" width="680px" destroy-on-close>
    <div v-if="traceRow" class="gt-trace-dialog">
      <div class="gt-trace-header">
        <span class="gt-trace-code">{{ traceRow.standard_account_code }}</span>
        <span class="gt-trace-name">{{ (traceRow as any).account_name || traceRow.row_name || '' }}</span>
      </div>

      <!-- 溯源链可视化 -->
      <div class="gt-trace-chain">
        <div class="gt-trace-node">
          <div class="gt-trace-node__label">四表库（叶子科目汇总）</div>
          <div class="gt-trace-node__value">期末余额 = {{ displayPrefs.fmtAmount(traceRow.unadjusted_amount || 0) }}</div>
          <div class="gt-trace-node__note">来源：tb_balance 中以 {{ traceRow.standard_account_code }} 开头的叶子科目按方向求和</div>
        </div>
        <div class="gt-trace-arrow">↓ 科目映射 + 全量重算</div>
        <div class="gt-trace-node">
          <div class="gt-trace-node__label">试算表未审数</div>
          <div class="gt-trace-node__value">{{ displayPrefs.fmtAmount(traceRow.unadjusted_amount || 0) }}</div>
        </div>
        <div class="gt-trace-arrow" v-if="getRowAdjustments(traceRow).length > 0">↓ 调整分录</div>
        <div class="gt-trace-node" v-for="adj in getRowAdjustments(traceRow)" :key="adj.type">
          <div class="gt-trace-node__label">{{ adj.type }}</div>
          <div class="gt-trace-node__value" :style="{ color: adj.amount > 0 ? '#67c23a' : '#f56c6c' }">
            {{ adj.amount > 0 ? '+' : '' }}{{ displayPrefs.fmtAmount(adj.amount) }}
          </div>
          <div class="gt-trace-node__note">来源：底稿调整分录 / 集中调整登记</div>
        </div>
        <div class="gt-trace-arrow">↓ 审定数 = 未审 + AJE + RJE</div>
        <div class="gt-trace-node gt-trace-node--result">
          <div class="gt-trace-node__label">最终审定数</div>
          <div class="gt-trace-node__value">{{ displayPrefs.fmtAmount(traceRow.audited_amount || 0) }}</div>
        </div>
      </div>

      <!-- 本次重算变动 -->
      <div v-if="recalcDiffMap.get(traceRow.standard_account_code)" class="gt-trace-diff">
        <el-tag type="warning" size="small">△ 本次重算变动</el-tag>
        <span style="margin-left: 8px; font-weight: 600">
          {{ recalcDiffMap.get(traceRow.standard_account_code)! > 0 ? '+' : '' }}{{ displayPrefs.fmtAmount(recalcDiffMap.get(traceRow.standard_account_code)!) }}
        </span>
      </div>
    </div>
    <template #footer>
      <el-button @click="traceDialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// [platform-context-permission-foundation P0-6.3]
// ProjectContext + 年度切换协议已接入
// TODO(P1): 逐步替换 selectedYear 本地 ref 为 projectStore.year 直取

import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { Link, ArrowDown, WarningFilled, MoreFilled } from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import TrustScorePanel from '@/components/trust/TrustScorePanel.vue'
import CellFormulaDetail from '@/components/CellFormulaDetail.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useLazyEdit } from '@/composables/useLazyEdit'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
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
import StaleIndicator from '@/components/StaleIndicator.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import DataQualityDialog from '@/components/DataQualityDialog.vue'
import TbVersionDrawer from '@/components/trial-balance/TbVersionDrawer.vue'
import TbComparisonView from '@/components/trial-balance/TbComparisonView.vue'
import ReportLineMappingDialog from '@/components/trial-balance/ReportLineMappingDialog.vue'
import { handleApiError } from '@/utils/errorHandler'
import { exportMultiSheetData, readSheetAoa } from '@/composables/useExcelIO'
import { usePenetrate } from '@/composables/usePenetrate'
import { useDecimalCalc } from '@/composables/useDecimalCalc'
import { useProjectEvents } from '@/composables/useProjectEvents'
import { useStaleRefresh } from '@/composables/useStaleRefresh'
import { usePasteImport } from '@/composables/usePasteImport'
import { usePermission } from '@/composables/usePermission'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
// Domain-split composables (platform-global-hardening Req 6.1/6.3)
import { useTbSummary } from '@/views/composables/useTbSummary'
import { useTbBalanceCheck } from '@/views/composables/useTbBalanceCheck'
import { useTbCellInteraction } from '@/views/composables/useTbCellInteraction'
import * as P from '@/services/apiPaths'
import LinkageBadge from '@/components/LinkageBadge.vue'
import { useLinkageIndicator } from '@/composables/useLinkageIndicator'
import { useAuditContext } from '@/composables/useAuditContext'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const { canEdit, onContextChange } = useAuditContext()
const { add: decAdd, sub: decSub } = useDecimalCalc()

// ─── P0-6.3: ProjectContext + PermissionMatrix facade ────────────────────────
const projectContext = computed(() => projectStore.currentProjectContext)
const { can: canOp, whyCannot } = usePermissionMatrix()
// DEPRECATED: 旧 usePermission().can() 仍保留，后续逐步替换为 canOp()

const projectId = computed(() => projectStore.projectId || (route.params.projectId as string) || '')
const selectedProjectId = ref(projectStore.projectId)
const projectOptions = computed(() => projectStore.projectOptions)
const selectedYear = ref(projectStore.year)
const yearOptions = computed(() => projectStore.yearOptions)

// ─── 云协同：账套激活/回滚后自动刷新 ─────────────────────────────────────────
const { onDatasetActivated, onDatasetRolledBack } = useProjectEvents(projectId)
onDatasetActivated(() => fetchData())
onDatasetRolledBack(() => fetchData())

// ─── useStaleRefresh：补充上游变更事件（dataset 已由 useProjectEvents 覆盖） ────
const staleRefresh = useStaleRefresh(projectId, {
  events: ['trial-balance:updated', 'adjustment:saved', 'year:changed', 'project:updated'],
  mode: 'prompt',
  onRefresh: () => fetchData(),
})

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

  // 按科目类别判断方向（会计准则）：
  // - 负债/权益类：贷方科目，余额无论正负方向恒为"贷"
  //   （如应交税费贷方正常余额为正数，仍是贷方，不能因正数误判为借方）
  // - 资产类：借方科目，方向为"借"；资产备抵科目（累计折旧/摊销、坏账/减值准备等）方向相反为"贷"
  // - 损益类（收入/成本/费用，编码 5/6 开头）：科目编码段无法可靠区分收入与费用，
  //   且常有冲回/调整，统一按余额符号判断（负数=贷=收入方向，正数=借=费用方向）
  const actualCat = getActualCat(row)
  const name = (row.account_name || '').replace(/_/g, '')
  const first = code.charAt(0)
  const isPnl = first === '5' || first === '6' || ['revenue', 'cost', 'expense'].includes(actualCat)
  const val = Number(row.unadjusted_amount || 0)

  if (isPnl) {
    // v2 约定下损益类统一存自然正数（收入取贷方发生额、费用取借方发生额），
    // 不能再靠余额符号判方向。改为按科目类别/编码+名称判断：
    // - 收入类（revenue / 5xxx / 6xxx但名称含"收入/收益"）→ 贷
    // - 费用/成本类（cost / expense / 6xxx 其余）→ 借
    if (actualCat === 'revenue' || first === '5') return '贷'
    // 6xxx 中有些是收入科目(如 6001营业收入/6111投资收益/6301营业外收入)
    if (first === '6') {
      const isRevenueByName = /收入|收益|利得/.test(name)
      return isRevenueByName ? '贷' : '借'
    }
    if (actualCat === 'cost' || actualCat === 'expense') return '借'
    // 兜底（极少见）
    return '借'
  }
  if (['liability', 'equity'].includes(actualCat)) {
    return '贷'
  }
  if (actualCat === 'asset') {
    const isContraAsset = /累计折旧|累计摊销|坏账准备|减值准备|跌价准备|折耗/.test(name)
    return isContraAsset ? '贷' : '借'
  }

  // 兜底：无类别信息时按余额正负推断（正数=借方余额，负数=贷方余额）
  return val < 0 ? '贷' : '借'
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

// ─── Task 4: Trial Balance Freeze Mechanism (后端持久化) ─────────────────────
const { can } = usePermission()
const isFrozen = ref(false)
const frozenBy = ref<string | null>(null)
const frozenAt = ref<string | null>(null)
const canToggleFreeze = computed(() => can('admin') || can('project:edit'))

function getFreezeKey() {
  return `tb_frozen_${projectId.value}_${year.value}`
}

async function loadFreezeState() {
  // 优先从后端读取锁定状态（跨设备/团队可见）
  try {
    const res = await api.get(`/api/projects/${projectId.value}/trial-balance/freeze-status`, { params: { year: year.value }, _silent: true } as any)
    const data = res?.data ?? res
    isFrozen.value = !!data?.is_frozen
    frozenBy.value = data?.frozen_by || null
    frozenAt.value = data?.frozen_at || null
  } catch {
    // 后端端点不存在时降级到 localStorage
    try {
      isFrozen.value = localStorage.getItem(getFreezeKey()) === '1'
    } catch {
      isFrozen.value = false
    }
  }
}

async function toggleFreeze() {
  if (!canToggleFreeze.value) {
    ElMessage.warning('仅管理员/合伙人/项目经理可操作锁定')
    return
  }

  const newState = !isFrozen.value

  // 锁定需二次确认（防误操作）
  if (newState) {
    try {
      await ElMessageBox.confirm(
        '锁定后试算表将不会因底稿保存或调整分录变更而自动重算，\n数据冻结不变，直到手动解锁。\n\n确定锁定试算表？',
        '锁定试算表',
        { confirmButtonText: '确定锁定', cancelButtonText: '取消', type: 'warning' }
      )
    } catch { return }
  } else {
    // 解锁也确认（尤其是别人锁的情况）
    const extraMsg = frozenBy.value ? `\n\n当前由「${frozenBy.value}」于 ${frozenAt.value ? displayPrefs.fmtDateTime(frozenAt.value) : '未知时间'} 锁定。` : ''
    try {
      await ElMessageBox.confirm(
        `解锁后系统将恢复自动重算检测。${extraMsg}\n\n确定解锁试算表？`,
        '解锁试算表',
        { confirmButtonText: '确定解锁', cancelButtonText: '取消', type: 'info' }
      )
    } catch { return }
  }

  // 调后端持久化（若端点不存在则降级 localStorage）
  try {
    await api.put(`/api/projects/${projectId.value}/trial-balance/freeze`, { is_frozen: newState, year: year.value })
    isFrozen.value = newState
    frozenBy.value = newState ? '当前用户' : null
    frozenAt.value = newState ? new Date().toISOString() : null
  } catch (e: any) {
    if (e?.response?.status === 404) {
      // 后端端点不存在，降级 localStorage
      isFrozen.value = newState
      try {
        if (newState) { localStorage.setItem(getFreezeKey(), '1') }
        else { localStorage.removeItem(getFreezeKey()) }
      } catch { /* ignore */ }
    } else {
      ElMessage.error('操作失败：' + (e?.response?.data?.message || e?.message || '未知错误'))
      return
    }
  }
  ElMessage.success(isFrozen.value ? '✅ 试算表已锁定，数据已冻结' : '🔓 试算表已解锁，恢复自动重算检测')
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
const showVersionDrawer = ref(false)
// #10: 对比模式
const comparisonActive = ref(false)
const comparisonMode = ref<'cross_year' | 'cross_project'>('cross_year')
const showMappingDialog = ref(false)
const headerCollapsed = ref(false)
const showTbGuide = ref(false)
const recalcLoading = ref(false)
const checkLoading = ref(false)
const showFormulaManager = ref(false)
const rows = ref<TrialBalanceRow[]>([])
const consistencyResult = ref<ConsistencyResult | null>(null)

// 上次校验时间展示（从 localStorage 读取）
const lastCheckTimeText = computed(() => {
  try {
    const ts = localStorage.getItem(`tb_last_check_${projectId.value}_${year.value}`)
    if (!ts) return ''
    const diff = Date.now() - new Date(ts).getTime()
    if (diff < 60000) return '刚刚✓'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前✓`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前✓`
    return `${Math.floor(diff / 86400000)}天前`
  } catch { return '' }
})

// 工具栏智能高亮：根据试算表当前状态决定哪个按钮应该被优先提示
// 优先级：数据过期→高亮重算 > 有质量问题→高亮质量检查 > 重算后未校验→高亮校验 > 无高亮
const toolbarHighlight = computed<'recalc' | 'check' | 'quality' | ''>(() => {
  // 1. 数据过期（有新调整分录尚未重算）→ 高亮「全量重算」
  if (isStale.value && !isFrozen.value) return 'recalc'
  // 2. 上次校验发现问题尚未解决 → 高亮「数据质量检查」
  if (dataQualityIssueCount.value > 0) return 'quality'
  // 3. 刚重算完但尚未校验（上次重算时间 > 上次校验时间）→ 高亮「一致性校验」
  try {
    const lastCheck = localStorage.getItem(`tb_last_check_${projectId.value}_${year.value}`)
    if (lastRecalcAt.value && (!lastCheck || new Date(lastRecalcAt.value) > new Date(lastCheck))) {
      return 'check'
    }
  } catch { /* ignore */ }
  // 4. 无特殊状态 → 全部平静
  return ''
})
// ─── 重算差异标记（△）：记录本次重算哪些科目变动了 ───
const recalcDiffMap = ref<Map<string, number>>(new Map())

function clearRecalcDiff() { recalcDiffMap.value = new Map() }

// ─── 科目级穿透追溯弹窗 ───
const traceDialogVisible = ref(false)
const traceRow = ref<any>(null)

function openTraceDialog(row: any) {
  traceRow.value = row
  traceDialogVisible.value = true
}

// 获取某科目的调整分录列表（审计调整 + 重分类调整）
function getRowAdjustments(row: any): { type: string; amount: number }[] {
  const items: { type: string; amount: number }[] = []
  const aje = Number(row.aje_adjustment) || 0
  const rje = Number(row.rje_adjustment) || 0
  if (aje !== 0) items.push({ type: 'AJE（审计调整）', amount: aje })
  if (rje !== 0) items.push({ type: 'RJE（重分类调整）', amount: rje })
  return items
}

// ─── 多人协作冲突提示 ───
// 锁定后其他人尝试重算时弹出醒目提示（而非仅 disabled tooltip）
function showFrozenConflictAlert() {
  const who = frozenBy.value || '其他成员'
  const when = frozenAt.value ? displayPrefs.fmtDateTime(frozenAt.value) : ''
  ElMessageBox.alert(
    `试算表当前已被「${who}」锁定${when ? `（${when}）` : ''}。\n\n锁定期间无法执行重算、导入等写操作。\n如需操作请联系锁定人解锁，或具有权限的合伙人/经理可直接解锁。`,
    '试算表已锁定',
    { confirmButtonText: '知道了', type: 'warning' }
  )
}
const dataQualityIssueCount = computed(() => {
  if (consistencyResult.value && !consistencyResult.value.consistent) {
    return consistencyResult.value.issues?.length || 0
  }
  return 0
})

// #6: 健康度仪表盘派生数据
const materialExceedsCount = computed(() => {
  if (materialityLevels.value.pm <= 0) return 0
  return rows.value.filter(r => Math.abs(Number(r.audited_amount) || 0) > materialityLevels.value.pm).length
})
const adjSummary = computed(() => {
  let count = 0
  for (const r of rows.value) {
    if ((Number(r.aje_adjustment) || 0) !== 0 || (Number((r as any).rje_adjustment) || 0) !== 0) count++
  }
  return { count }
})

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
    total = Number(decAdd(String(total), String(dir === '贷' ? -val : val)))
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
    total = Number(decAdd(String(total), String(dir === '借' ? -val : val)))
  }
  return total
})
// 差额（资产 - 负债和权益），用于平衡校验
const balanceDiff = computed(() => assetTotal.value - liabEquityTotal.value)

// ── 完整试算平衡（全科目借贷合计，含损益类） ──
// 资产负债表恒等式「资产=负债+权益」仅在结账后成立；
// 若余额表含未结转的损益类科目（5/6 开头），此式必然不平，差额=本期利润。
// 真正普适的平衡校验是「全部科目借方合计 = 贷方合计」。
const trialBalanceTotals = ref<{ debit: number; credit: number; diff: number }>({ debit: 0, credit: 0, diff: 0 })
const balanceCheckLoaded = ref(false)

async function loadBalanceCheck() {
  try {
    const { data } = await api.get(
      `/api/projects/${projectId.value}/trial-balance/balance-check`,
      { params: { year: year.value } }
    )
    const result = data && typeof data === 'object' && 'debit_total' in data ? data : (data?.data || data)
    trialBalanceTotals.value = {
      debit: result.debit_total || 0,
      credit: result.credit_total || 0,
      diff: result.diff || 0,
    }
    balanceCheckLoaded.value = true
  } catch {
    balanceCheckLoaded.value = false
  }
}

// P1-8: 重要性水平（PM/TE/SAT）
const materialityLevels = ref<{ pm: number; te: number; sat: number }>({ pm: 0, te: 0, sat: 0 })
async function loadMaterialityLevels() {
  try {
    const mat = await api.get(`${P.materiality.get(projectId.value)}?year=${year.value}`)
    if (mat) {
      materialityLevels.value = {
        pm: Number(mat.overall_materiality) || 0,
        te: Number(mat.performance_materiality) || 0,
        sat: Number(mat.trivial_threshold) || 0,
      }
    }
  } catch { /* B15 未设定时静默 */ }
}
// 是否含未结转损益类科目（影响平衡口径解释）
const hasPnlRows = computed(() =>
  rows.value.some(r => {
    const f = (r.standard_account_code || '').charAt(0)
    return (f === '5' || f === '6') && Math.abs(num(r.audited_amount)) > 0
  })
)

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
  if (!rows.value.length) return true
  if (!balanceCheckLoaded.value) return true  // API 未返回前不误报
  // 后端 balance-check 从 tb_balance 原始数据验证(同源,保持恒等式)
  return Math.abs(trialBalanceTotals.value.diff) < 1
})

// P0-1: 恒等式各段金额（从试算平衡表行直接派生）
const balanceEquation = computed(() => {
  const rows = tbSummaryRows.value
  // 按报表行次识别合计行：BS-039资产合计 / BS-099负债和权益合计 / BS-091所有者权益合计
  let assetTotal = 0, liabilityTotal = 0, equityTotal = 0
  for (const r of rows) {
    const code = (r.row_code || '').trim()
    const name = (r.row_name || '').trim()
    const audited = Number(r.audited) || 0
    if (code === 'BS-039' || name.includes('资产合计') || name.includes('资产总计')) {
      assetTotal = audited
    } else if (code === 'BS-091' || name.includes('所有者权益合计') || name.includes('股东权益合计')) {
      equityTotal = audited
    } else if (code === 'BS-099' || name.includes('负债和所有者权益合计') || name.includes('负债和股东权益合计')) {
      // 负债合计 = 负债和权益合计 - 权益合计
      liabilityTotal = audited - equityTotal
    }
  }
  // 兜底：直接用后端 balance-check 差额
  const diff = assetTotal - liabilityTotal - equityTotal
  return { assetTotal, liabilityTotal, equityTotal, diff }
})

// 平衡指示器悬浮提示文案
const balanceTooltip = computed(() => {
  if (hasPnlRows.value) {
    const { debit, credit, diff } = trialBalanceTotals.value
    if (isBalanced.value) {
      return `试算平衡：借方合计 ${fmt(debit)} = 贷方合计 ${fmt(credit)}`
    }
    return `试算不平衡：借方合计 ${fmt(debit)}，贷方合计 ${fmt(credit)}，差额 ${fmt(Math.abs(diff))} 元（含未结转损益类科目，请核对源数据）`
  }
  return isBalanced.value
    ? '资产小计 = 负债和权益合计'
    : `差额：${fmt(Math.abs(balanceDiff.value))} 元（资产 - 负债权益）`
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
  const classes: string[] = []
  if (row._isTotal) return 'total-row'
  if (row._isSubtotal) return 'subtotal-row'
  if (row._highlight) classes.push('highlight-row')
  // Task 2: stale rows (updated_at older than latest adjustment)
  if (row.standard_account_code && staleAccountCodes.value.has(row.standard_account_code)) classes.push('stale-row')
  // #1: 审定数 > PM 重大科目加粗
  if (materialityLevels.value.pm > 0 && Math.abs(Number(row.audited_amount) || 0) > materialityLevels.value.pm) classes.push('gt-tb-sum-material')
  // 重算差异△标记：本次重算中变动的科目行
  if (row.standard_account_code && recalcDiffMap.value.has(row.standard_account_code)) classes.push('gt-tb-row-changed')
  return classes.join(' ')
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
  const result = await getTrialBalance(projectId.value, year.value, hasMultipleCompanies.value ? companyCode.value : undefined)
  rows.value = Array.isArray(result) ? result : []
  await loadBalanceCheck()
})

const onRecalc = withLoading(recalcLoading, async () => {
  // 重算前确认弹窗（含上下文提示）
  const rowCount = rows.value.length
  const lastTime = lastRecalcAt.value ? displayPrefs.fmtDateTime(lastRecalcAt.value) : '从未重算'
  try {
    await ElMessageBox.confirm(
      `全量重算将从四表库重新汇总计算所有科目的未审数，并注入调整分录计算审定数。\n\n` +
      `• 当前科目数：${rowCount} 个\n` +
      `• 上次重算：${lastTime}\n` +
      `• 预估耗时：${rowCount > 500 ? '约 5-10 秒' : rowCount > 200 ? '约 3-5 秒' : '约 1-3 秒'}\n\n` +
      `重算会覆盖未审数列（不会覆盖 AJE/RJE 调整分录）。\n确定执行？`,
      '全量重算确认',
      { confirmButtonText: '确定重算', cancelButtonText: '取消', type: 'info' }
    )
  } catch { return }

  // 记录重算前的审定数快照（用于摘要对比）
  const beforeSnapshot = new Map<string, number>()
  for (const row of rows.value) {
    if (row.standard_account_code && row.audited_amount != null) {
      beforeSnapshot.set(row.standard_account_code, Number(row.audited_amount) || 0)
    }
  }

  await recalcTrialBalance(projectId.value, year.value)
  await fetchData()
  await loadLatestAdjustmentTime()

  // 计算差异摘要 + 填充 recalcDiffMap（表格行△标记用）
  let changedCount = 0
  let maxChangeCode = ''
  let maxChangeAmount = 0
  const diffMap = new Map<string, number>()
  for (const row of rows.value) {
    if (!row.standard_account_code) continue
    const before = beforeSnapshot.get(row.standard_account_code) ?? 0
    const after = Number(row.audited_amount) || 0
    const diff = after - before
    if (Math.abs(diff) > 0.005) {
      changedCount++
      diffMap.set(row.standard_account_code, diff)
      if (Math.abs(diff) > Math.abs(maxChangeAmount)) {
        maxChangeAmount = diff
        maxChangeCode = `${row.standard_account_code} ${(row as any).account_name || ''}`
      }
    }
  }
  recalcDiffMap.value = diffMap

  // 展示重算摘要
  if (changedCount === 0) {
    ElMessage.success('✅ 重算完成，数据无变化')
  } else {
    const sign = maxChangeAmount > 0 ? '+' : ''
    ElNotification({
      title: '重算完成',
      message: `影响 ${changedCount} 个科目\n最大变动：${maxChangeCode.trim()}\n审定数 ${sign}${displayPrefs.fmtAmount(maxChangeAmount)}`,
      type: 'success',
      duration: 8000,
    })
  }
  // #9: 重算后 best-effort 创建快照
  createSnapshotBestEffort('recalc')
})

const onConsistencyCheck = withLoading(checkLoading, async () => {
  consistencyResult.value = await checkConsistency(projectId.value, year.value)
  // 持久化校验时间到本地（用于显示"最近校验时间"）
  try {
    localStorage.setItem(`tb_last_check_${projectId.value}_${year.value}`, new Date().toISOString())
  } catch { /* ignore */ }
  // 校验通过/不通过的详细提示
  if (consistencyResult.value?.consistent) {
    ElMessage.success('✅ 一致性校验通过：试算表与四表源数据完全一致')
  } else {
    const issueCount = consistencyResult.value?.issues?.length || 0
    ElNotification({
      title: '⚠️ 一致性校验发现差异',
      message: `共 ${issueCount} 项不一致，请查看上方详情横幅。\n建议：先全量重算再重新校验。`,
      type: 'warning',
      duration: 10000,
    })
  }
})

function onTbImported() {
  showTbImport.value = false
  fetchData()
}

async function onExport() {
  // 导出前自动检查：若有未通过的质量问题则弹提示
  if (dataQualityIssueCount.value > 0) {
    try {
      await ElMessageBox.confirm(
        `当前有 ${dataQualityIssueCount.value} 项数据质量问题未解决（借贷不平衡/映射不完整等），\n导出数据可能不准确。\n\n确定继续导出？`,
        '导出提醒',
        { confirmButtonText: '仍然导出', cancelButtonText: '取消，去修复', type: 'warning' }
      )
    } catch {
      // 用户选择"取消，去修复" → 打开数据质量检查弹窗
      showDataQualityDialog.value = true
      return
    }
  }
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

async function reloadTrialBalanceContext() {
  await ensureProjectYear()
  selectedProjectId.value = projectId.value
  selectedYear.value = year.value
  await fetchData()
  await detectDataState()  // 自动检测步骤状态
  await loadLatestAdjustmentTime()  // 加载最新调整时间用于新鲜度检测
  await loadCompanyList()  // Task 3: 加载子公司列表
  loadFreezeState()  // Task 4: 加载冻结状态
  loadMaterialityLevels()  // P1-8: 加载重要性水平
  // P1-1: 自动执行一次数据质量检查（best-effort 填充 badge）
  if (rows.value.length > 0) {
    checkConsistency(projectId.value, year.value)
      .then(r => { consistencyResult.value = r })
      .catch(() => { /* 静默 */ })
  }
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
}

// 初次加载（替代 onMounted 一次性加载）
reloadTrialBalanceContext()

// V3 Req 5.1：上下文（projectId/year）变化时自动重载（替代散落的 watch）
onContextChange(() => {
  reloadTrialBalanceContext()
})

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

// #9: 版本时光机辅助
function onVersionRestored() {
  fetchData()
  if (tbViewMode.value === 'summary') loadTbSummary()
}

// #10: 对比模式切换
function onComparisonMode(cmd: string) {
  comparisonMode.value = cmd as 'cross_year' | 'cross_project'
  comparisonActive.value = true
}
/** Best-effort 创建快照（不阻塞主操作） */
async function createSnapshotBestEffort(trigger: string) {
  try {
    const detailRows = rows.value.map(r => ({
      standard_account_code: r.standard_account_code,
      unadjusted_amount: r.unadjusted_amount,
      aje_adjustment: r.aje_adjustment,
      rje_adjustment: (r as any).rje_adjustment,
      audited_amount: r.audited_amount,
    }))
    const summaryRows = tbSummaryRows.value.map(r => ({
      row_code: r.row_code, row_name: r.row_name,
      unadjusted: r.unadjusted, aje_dr: r.aje_dr, aje_cr: r.aje_cr,
      rcl_dr: r.rcl_dr, rcl_cr: r.rcl_cr, audited: r.audited,
    }))
    await api.post(
      `/api/projects/${projectId.value}/trial-balance/snapshots`,
      { trigger, detail_rows: detailRows, summary_rows: summaryRows },
      { params: { year: year.value } }
    )
  } catch { /* fail-open: 快照失败不影响主操作 */ }
}

// ─── 试算平衡表（报表行次级别） ──────────────────────────────────────────────
const tbViewMode = ref<'detail' | 'summary'>('detail')
const tbSummaryType = ref('balance_sheet')
const tbSummaryLoading = ref(false)
// 溯源返回支持：记录从 summary 跳到 detail 的上下文
const tbTraceOrigin = ref<{ fromSummary: boolean; rowIndex: number; scrollTop: number } | null>(null)
const tbSummaryRows = ref<any[]>([])
// P1-5: 快捷筛选
const tbSumFilter = ref<'all' | 'has_adj' | 'has_diff' | 'material' | 'zero_unadj'>('all')
const filteredTbSummaryRows = computed(() => {
  const all = tbSummaryRows.value
  if (tbSumFilter.value === 'all') return all
  return all.filter(r => {
    // 合计/小计行始终显示
    if (r.is_total || r.is_category) return true
    const unadj = Number(r.unadjusted) || 0
    const audited = Number(r.audited) || 0
    const adj = (Number(r.aje_dr) || 0) + (Number(r.aje_cr) || 0) + (Number(r.rcl_dr) || 0) + (Number(r.rcl_cr) || 0)
    switch (tbSumFilter.value) {
      case 'has_adj': return adj !== 0
      case 'has_diff': return Math.abs(audited - unadj) > 0.01
      case 'material': return Math.abs(audited) > (materialityLevels.value.pm || 1000000) // 优先用 B15 整体重要性
      case 'zero_unadj': return unadj === 0 && r.unadjusted != null
      default: return true
    }
  })
})
const selectedTemplateType = ref('soe')
const tbSumImportInput = ref<HTMLInputElement | null>(null)

// 编辑模式开关（点击"编辑"按钮切换，编辑中可修改未审数，保存后退出编辑模式恢复双击溯源）
const tbSumEditMode = ref(false)
// P2-9: 变动分析列显隐
const tbSumShowVariance = ref(false)
// P2-13: 调整列折叠（4列→1列调整净额）
const tbSumCollapseAdj = ref(false)

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
  // P1-8: 审定数 > PM 的行加粗（重大科目醒目）
  if (materialityLevels.value.pm > 0 && !row.is_total && !row.is_category) {
    const audited = Math.abs(Number(row.audited) || 0)
    if (audited > materialityLevels.value.pm) classes.push('gt-tb-sum-material')
  }
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
  // #7: 优先跳转底稿（如有关联底稿），否则溯源到科目明细
  if (row.row_name && wpMappingIndex.value) {
    const found = Object.values(wpMappingIndex.value).find((m: any) => m.wp_name?.includes(row.row_name))
    if (found) {
      const wp = wpList.value.find((w: any) => w.wp_code === found.wp_code)
      if (wp?.wp_id) {
        router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: wp.wp_id } })
        return
      }
    }
  }
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
  const detail = `【${row.row_code} ${row.row_name}】\n\n公式：${formula}\n\n未审数：${fmt(row.unadjusted)}\n审定数：${fmt(row.audited)}`
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
        detail += `  + ${prev.row_code} ${prev.row_name}：${fmt(prev.unadjusted)}\n`
      }
    }
    detail += `\n━━━━━━━━━━━━━━━━\n合计 = ${fmt(row.unadjusted)}`
    ElMessageBox.alert(detail, '汇总明细', {
      confirmButtonText: '确定',
      customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'Arial Narrow', monospace", fontSize: '12px', maxHeight: '70vh', overflow: 'auto' },
    })
  } else {
    // 普通行：展示取数来源
    const detail = `【${row.row_code} ${row.row_name}】\n\n取数来源：通过映射规则从科目明细汇总\n未审数 = Σ 映射到该行次的所有科目余额\n\n当前值：${fmt(row.unadjusted)}`
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

// P2-4: 行级操作 — 统一分发
function onRowActionCommand(cmd: string, row: any) {
  switch (cmd) {
    case 'formula': onTbSumShowFormula(row); break
    case 'trace': onTbSumTrace(row); break
    case 'workpaper': onTbSumGoWorkpaper(row); break
  }
}

// P2-4: 行级操作按钮（直接接收 row，不经右键菜单）
function onTbSumShowFormula(row: any) {
  if (!row) return
  const formula = row._formula || row.formula_used || '无公式（通过映射关系取数）'
  const detail = `【${row.row_code} ${row.row_name}】\n\n公式：${formula}\n\n未审数：${fmt(row.unadjusted)}\n审定数：${fmt(row.audited)}`
  ElMessageBox.alert(detail, '公式详情', {
    confirmButtonText: '确定',
    customStyle: { whiteSpace: 'pre-wrap', fontFamily: "'JetBrains Mono', monospace", fontSize: '12px' },
  })
}

function onTbSumGoWorkpaper(row: any) {
  if (!row?.row_name) return
  // 从映射索引找到对应底稿
  const mapping = wpMappingIndex.value
  if (!mapping) { ElMessage.info('未加载底稿映射'); return }
  // 按报表行名在底稿映射中找
  const found = Object.values(mapping).find((m: any) => m.wp_name?.includes(row.row_name))
  if (found) {
    const wp = wpList.value.find((w: any) => w.wp_code === found.wp_code)
    if (wp?.wp_id) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: wp.wp_id } })
      return
    }
  }
  ElMessage.info('该报表行未关联底稿')
}

// #8: 调整分录快录入口（点击空的审计调整格子 → 打开调整弹窗预填科目）
function onQuickAdjEntry(row: any) {
  if (!row?.row_name) return
  adjDialogType.value = 'AJE'
  adjDialogAccount.value = `${row.row_code || ''} ${row.row_name}`
  adjDialogVisible.value = true
  adjDialogList.value = [] // 无既有分录，引导新增
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
    detail += `  + ${r.standard_account_code} ${r.account_name}：${fmt(val)}\n`
  }
  detail += `  收入合计：${fmt(totalRevenue)}\n\n`

  // 费用/成本类
  detail += '━━ 费用/成本类（-）━━\n'
  for (const r of incomeExpenseRows) {
    const dir = getDirection(r)
    if (dir !== '借') continue
    const val = Math.abs(Number(r.unadjusted_amount || 0))
    if (val === 0) continue
    totalExpense += val
    detail += `  - ${r.standard_account_code} ${r.account_name}：${fmt(val)}\n`
  }
  detail += `  费用合计：${fmt(totalExpense)}\n\n`

  // 净利润
  const netProfit = Number(decSub(String(totalRevenue), String(totalExpense)))
  detail += '━━━━━━━━━━━━━━━━\n'
  detail += `净利润 = 收入 - 费用 = ${fmt(netProfit)}\n`
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
    detail += `  ${sign} ${r.standard_account_code} ${r.account_name}：${fmt(val)}（${dir}）\n`
  }
  detail += `\n━━━━━━━━━━━━━━━━\n`
  detail += `${name} = ${fmt(Math.abs(Number(row.unadjusted_amount || 0)))}`

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

// ─── 数字溯源：调 lineage 端点展示 upstream/downstream ───
const tbTraceDialogVisible = ref(false)
const tbTraceLoading = ref(false)
const tbTraceResult = ref<{ upstream: any[]; downstream: any[] } | null>(null)

async function onTbCtxCellTrace() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  if (!row?.standard_account_code) {
    ElMessage.info('请在科目行上右键')
    return
  }
  tbTraceDialogVisible.value = true
  tbTraceLoading.value = true
  tbTraceResult.value = null
  try {
    const data: any = await api.get(
      `/api/projects/${projectId.value}/lineage`,
      { params: { object_type: 'tb_row', object_id: row.standard_account_code, direction: 'both' } },
    )
    const upstream = data?.upstream || []
    const downstream = data?.downstream || []
    tbTraceResult.value = { upstream, downstream }
    if (!upstream.length && !downstream.length) {
      tbTraceDialogVisible.value = false
      ElMessage.info('该数字暂无溯源信息')
    }
  } catch (e: any) {
    tbTraceDialogVisible.value = false
    handleApiError(e, '数字溯源')
  } finally {
    tbTraceLoading.value = false
  }
}

function onTbTraceLocate(node: any) {
  tbTraceDialogVisible.value = false
  if (node.wp_code) {
    eventBus.emit('workpaper:locate-cell', {
      wpId: node.wp_code,
      sheetName: node.sheet_name || undefined,
      cellRef: node.cell_ref || '',
    })
  }
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
    formulaDesc += `未审数：${fmt(Math.abs(val))}\n`
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

// V3 Req 9.6: 数字信任度
const trustScorePanelRef = ref<InstanceType<typeof TrustScorePanel> | null>(null)
function onTbCtxTrustScore() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  const context = `tb:${row?.standard_account_code || ''}`
  trustScorePanelRef.value?.open(context)
}

function onTbCtxSum() {
  tbCtx.closeContextMenu()
  const sum = tbCtx.sumSelectedValues()
  ElMessage.info(`选中 ${tbCtx.selectedCells.value.length} 格，合计：${fmt(sum)}`)
}

function onTbCtxCompare() {
  tbCtx.closeContextMenu()
  if (tbCtx.selectedCells.value.length < 2) return
  const vals = tbCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  ElMessage.info(`差异：${fmt(diff)}`)
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

// Sprint 5.8: 查看引用方
const showCellFormulaDetail = ref(false)
const cellDetailWpCode = ref('')
const cellDetailSheet = ref('')
const cellDetailLabel = ref('')

function onTbCtxViewReferences() {
  tbCtx.closeContextMenu()
  const row = tbCtx.contextMenu.rowData
  if (!row?.standard_account_code) {
    ElMessage.info('请先选中一个科目行')
    return
  }
  cellDetailWpCode.value = row.standard_account_code
  cellDetailSheet.value = ''
  cellDetailLabel.value = ''
  showCellFormulaDetail.value = true
}

function onCellDetailNavigate(uri: string) {
  showCellFormulaDetail.value = false
  const parts = uri.split(':')
  const mod = parts[0]?.toUpperCase()
  if (mod === 'WP' && parts[1]) {
    router.push({ name: 'WorkpaperEditor', params: { id: projectId.value }, query: { wp: parts[1] } })
  } else if (mod === 'REPORT') {
    router.push({ name: 'ReportView', params: { id: projectId.value } })
  } else if (mod === 'NOTE') {
    router.push({ name: 'DisclosureEditor', params: { id: projectId.value } })
  }
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
  const headers = ['行次', '项目', '未审数', '审计调整-借', '审计调整-贷', '重分类-借', '重分类-贷', '审定数']
  const dataRows = tbSummaryRows.value.map((r: any) => [
    r.row_code, r.row_name, r.unadjusted, r.aje_dr, r.aje_cr, r.rcl_dr, r.rcl_cr, r.audited,
  ])
  const label = tbSummaryTypes.find(t => t.key === tbSummaryType.value)?.label || ''
  // 走 useExcelIO 单一入口（B6 批）。三个显式关闭保持产物不变。
  await exportMultiSheetData({
    sheets: [{
      sheetName: '试算平衡表',
      rows: [headers, ...dataRows],
      colWidths: headers.map((_, i) => ({ wch: i < 2 ? 20 : 14 })),
    }],
    fileName: `试算平衡表_${label}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
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
  const headers = ['行次', '项目', '未审数']
  const dataRows = tbSummaryRows.value.map((r: any) => [r.row_code, r.row_name, null])
  const label = tbSummaryTypes.find(t => t.key === tbSummaryType.value)?.label || ''
  await exportMultiSheetData({
    sheets: [{
      sheetName: '模板',
      rows: [headers, ...dataRows],
      colWidths: [{ wch: 12 }, { wch: 30 }, { wch: 16 }],
    }],
    fileName: `试算平衡表模板_${label}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
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

  // 走 useExcelIO 单一入口（B6 批）。原先取第一个 sheet + sheet_to_json(header:1)，
  // readSheetAoa 不传 sheetName 时同样取第一个，选项逐项透传保持等价。
  const { rows } = await readSheetAoa(file)

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

  /* 期初/期末 胶囊分段控制器 */
  .gt-period-segmented {
    display: inline-flex;
    background: #f3f0f8;
    border-radius: 6px;
    padding: 3px;
    gap: 2px;
  }
  .gt-period-segmented__item {
    padding: 4px 14px;
    font-size: 13px;
    border-radius: 4px;
    cursor: pointer;
    color: var(--gt-color-text-secondary, #606266);
    transition: all 0.2s ease;
    user-select: none;
    font-weight: 500;
  }
  .gt-period-segmented__item:hover {
    color: var(--gt-color-primary, #4b2d77);
  }
  .gt-period-segmented__item--active {
    background: var(--gt-color-primary, #4b2d77);
    color: #fff;
    box-shadow: 0 1px 3px rgba(75, 45, 119, 0.3);
  }

  /* 折叠/展开按钮 */
  .gt-header-toggle {
    text-align: center;
    padding: 2px 0;
    cursor: pointer;
    font-size: var(--gt-font-size-xs);
    color: var(--gt-color-info);
    border-bottom: 1px solid var(--gt-color-border-purple);
    margin-bottom: 6px;
    user-select: none;
    transition: color 0.15s;
  }
  .gt-header-toggle:hover { color: var(--gt-color-primary); }

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
  :deep(.gt-tb-font-xs) .el-table__body { font-size: var(--gt-font-size-xs) !important; }

  :deep(.gt-tb-font-sm),
  :deep(.gt-tb-font-sm) th .cell,
  :deep(.gt-tb-font-sm) td .cell,
  :deep(.gt-tb-font-sm) .el-table__body { font-size: var(--gt-font-size-xs) !important; }

  :deep(.gt-tb-font-md),
  :deep(.gt-tb-font-md) th .cell,
  :deep(.gt-tb-font-md) td .cell,
  :deep(.gt-tb-font-md) .el-table__body { font-size: var(--gt-font-size-sm) !important; }

  :deep(.gt-tb-font-lg),
  :deep(.gt-tb-font-lg) th .cell,
  :deep(.gt-tb-font-lg) td .cell,
  :deep(.gt-tb-font-lg) .el-table__body { font-size: var(--gt-font-size-sm) !important; }

  :deep(.el-table th .cell) {
    font-weight: 600;
    white-space: nowrap;
  }
  :deep(.el-table td .cell) {
    line-height: 1.4;
  }

  /* ── 科目明细表样式统一（与试算平衡表风格一致） ── */
  :deep(.el-table thead th) {
    background: var(--gt-color-primary-bg) !important;
    color: var(--gt-color-text-primary);
    border-bottom: 1px solid var(--gt-color-border-purple) !important;
  }
  :deep(.el-table--border td) {
    border-color: var(--gt-color-border-purple) !important;
  }
  :deep(.el-table--border th) {
    border-color: var(--gt-color-border-purple) !important;
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
  .gt-dir-debit { color: var(--gt-color-text-primary); font-size: var(--gt-font-size-xs); }
  .gt-dir-credit { color: var(--gt-color-wheat); font-size: var(--gt-font-size-xs); font-weight: 600; }
  .gt-dir-toggle { cursor: pointer; user-select: none; padding: 2px 6px; border-radius: 3px; }
  .gt-dir-toggle:hover { background: var(--gt-color-primary-bg); }

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

  /* P0-1: 恒等式校验栏 */
  .gt-tb-balance-bar {
    margin-top: 12px;
    padding: 10px 16px;
    background: linear-gradient(90deg, #f8f9fa, #f0f2f5);
    border-radius: 8px;
    border: 1px solid #e8e8e8;
  }
  .gt-tb-balance-bar__equation {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    font-size: 13px;
  }
  .gt-tb-balance-bar__term {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
  }
  .gt-tb-balance-bar__label {
    color: var(--gt-color-text-tertiary);
    font-size: 12px;
  }
  .gt-tb-balance-bar__value {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--gt-color-text-primary);
  }
  .gt-tb-balance-bar__op {
    color: var(--gt-color-text-quaternary);
    font-weight: 700;
    font-size: 14px;
  }
  .gt-tb-balance-bar__divider {
    width: 1px;
    height: 20px;
    background: #dcdfe6;
    margin: 0 4px;
  }
  .gt-tb-balance-bar__result {
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 12px;
  }
  .gt-tb-balance-bar__result--ok {
    color: var(--gt-color-success);
    background: var(--gt-color-success-light, #f0f9eb);
  }
  .gt-tb-balance-bar__result--err {
    color: var(--gt-color-coral, #f56c6c);
    background: var(--gt-color-coral-light, #fef0f0);
  }
  .gt-tb-balance-bar__note {
    margin-top: 4px;
    font-size: 11px;
    color: var(--gt-color-text-quaternary);
  }

  /* P0-2: 三态样式 */
  .gt-tb-nomap {
    color: var(--gt-color-text-quaternary);
    font-style: italic;
  }
  .gt-tb-pending {
    color: var(--el-color-warning);
    font-size: 12px;
  }

  /* P1-5: 筛选栏 */
  .gt-tb-filter-bar {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
    padding: 4px 0;
  }

  /* P2-9: 变动分析列 */
  .gt-tb-var-warn { color: var(--el-color-warning); font-weight: 600; }
  .gt-tb-var-danger { color: var(--gt-color-coral, #f56c6c); font-weight: 700; }

  /* P1-8: 重要性参照条 */
  .gt-tb-materiality-bar {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 6px 16px;
    margin-top: 6px;
    font-size: 12px;
    background: #fafbfc;
    border-radius: 6px;
    border: 1px dashed #e4e7ed;
  }
  .gt-tb-materiality-bar--empty {
    border-color: var(--el-color-warning-light-5);
    background: #fffbe6;
  }
  .gt-tb-materiality-bar__item {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-variant-numeric: tabular-nums;
    color: var(--gt-color-text-secondary);
  }
  .gt-tb-materiality-bar__dot {
    width: 8px; height: 8px; border-radius: 50%;
  }
  .gt-tb-materiality-bar__dot--pm { background: var(--gt-color-coral, #f56c6c); }
  .gt-tb-materiality-bar__dot--te { background: var(--el-color-warning, #e6a23c); }
  .gt-tb-materiality-bar__dot--sat { background: var(--gt-color-success, #67c23a); }
  .gt-tb-materiality-bar__hint {
    margin-left: auto;
    font-size: 11px;
    color: var(--gt-color-text-quaternary);
  }

  /* P1-8: 重大行加粗 */
  :deep(.gt-tb-sum-material) {
    font-weight: 700 !important;
  }
  :deep(.gt-tb-sum-material td:nth-child(3)),
  :deep(.gt-tb-sum-material td:last-child) {
    color: var(--gt-color-primary) !important;
  }

  /* #6: 健康度仪表盘 */
  .gt-tb-health-dashboard {
    display: flex;
    gap: 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }
  .gt-tb-health-card {
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding: 6px 14px;
    background: #f8f9fa;
    border-radius: 8px;
    border: 1px solid #ebeef5;
    font-size: 12px;
  }
  .gt-tb-health-card--ok { border-color: var(--gt-color-success-light); background: #f0f9eb; }
  .gt-tb-health-card--err { border-color: var(--gt-color-coral-light); background: #fef0f0; }
  .gt-tb-health-card__value {
    font-size: 16px;
    font-weight: 700;
    color: var(--gt-color-text-primary);
    font-variant-numeric: tabular-nums;
  }
  .gt-tb-health-card__value--accent { color: var(--gt-color-coral); }
  .gt-tb-health-card__label {
    color: var(--gt-color-text-tertiary);
  }

  /* #8: 快录入口按钮 */
  .gt-tb-quick-adj {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 1px dashed #dcdfe6;
    color: var(--gt-color-text-quaternary);
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    transition: all 0.15s;
  }
  .gt-tb-quick-adj:hover {
    border-color: var(--gt-color-primary);
    color: var(--gt-color-primary);
    background: var(--gt-color-primary-bg);
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
    background: var(--gt-bg-warning) !important;
    border-left: 3px solid var(--gt-color-wheat);
  }

  :deep(.el-tabs__item.is-active) { font-weight: 600; }

/* 视图切换标签 */

.gt-tb-view-tag {
  padding: 6px 16px; font-size: var(--gt-font-size-sm); cursor: pointer; color: var(--gt-color-text-tertiary);
  border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.15s; user-select: none;
}
.gt-tb-view-tag:hover { color: var(--gt-color-primary); }
.gt-tb-view-tag--active { color: var(--gt-color-primary); font-weight: 600; border-bottom-color: var(--gt-color-primary); }

.gt-mapping-rule-btn {
  margin-left: 16px;
  border-color: var(--gt-color-border-purple-mid);
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-xs);
}
.gt-mapping-rule-btn:hover {
  border-color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg);
}

/* 试算平衡表 el-table 样式 */
:deep(.gt-tb-sum-unadj-col) { background: rgba(75,45,119,0.03); }
:deep(.gt-tb-sum-audited-col .cell) { font-weight: 700; color: var(--gt-color-primary); }
:deep(.gt-tb-sum-audited-col) { background: rgba(75,45,119,0.06); }
.gt-tb-editable { cursor: text; border-bottom: 1px dashed var(--gt-color-border); padding: 2px 4px; border-radius: 2px; display: inline-block; min-width: 60px; text-align: right; }
.gt-tb-editable:hover { background: var(--gt-color-primary-bg); }
.gt-tb-readonly { display: inline-block; min-width: 60px; text-align: right; padding: 2px 4px; color: var(--gt-color-text-regular); }
:deep(.gt-tb-sum-total td) { font-weight: 700 !important; background: var(--gt-color-primary-bg) !important; }
:deep(.gt-tb-sum-category td) { font-weight: 600 !important; color: var(--gt-color-primary) !important; }
:deep(.gt-tb-sum-selected td) { background: rgba(75, 45, 119, 0.14) !important; border-left: 3px solid var(--gt-color-primary) !important; }
:deep(.gt-tb-sum-selected td:first-child) { border-left: 3px solid var(--gt-color-primary) !important; }
:deep(.gt-tb-sum-selected td:not(:first-child)) { border-left: none !important; }

/* 试算平衡表 hover 效果 */
:deep(.el-table__body tr:hover > td) { background: rgba(75, 45, 119, 0.04) !important; }
:deep(.el-table__body tr.gt-tb-sum-selected:hover > td) { background: rgba(75, 45, 119, 0.16) !important; }

/* 试算平衡表右键菜单 */
.gt-tb-sum-ctx {
  position: fixed;
  z-index: 10001;
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  padding: 6px 0;
  min-width: 160px;
}
.gt-ucell-ctx-divider { height: 1px; background: var(--gt-color-border-light); margin: 4px 8px; }
.gt-tb-detached-icon { font-size: var(--gt-font-size-xs); margin-right: 2px; opacity: 0.7; }
:deep(.gt-tb-sum-detached td) { background: var(--gt-color-wheat-light) !important; border-left: 2px solid var(--gt-color-wheat) !important; }

/* 步骤引导 */
.gt-setup-guide {
  padding: 24px 32px;
  background: var(--gt-color-primary-bg);
  border: 1px solid var(--gt-color-border-purple);
  border-radius: var(--gt-radius-lg, 8px);
  margin-bottom: 16px;
}

/* ─── 试算表使用说明面板 ─── */
.gt-tb-guide-panel {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 8px;
  background: linear-gradient(135deg, #fafbff 0%, #f5f0fa 100%);
  overflow: hidden;
}
.gt-tb-guide-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: linear-gradient(90deg, var(--gt-color-primary, #4b2d77) 0%, #6b4a99 100%);
}
.gt-tb-guide-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 0.5px;
}
.gt-tb-guide-panel__header .el-button {
  color: rgba(255,255,255,0.85) !important;
}
.gt-tb-guide-panel__body {
  padding: 20px 24px;
  max-height: 480px;
  overflow-y: auto;
}
.gt-tb-guide-section {
  margin-bottom: 20px;
}
.gt-tb-guide-section:last-child {
  margin-bottom: 0;
}
.gt-tb-guide-section__title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  padding-left: 10px;
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
.gt-tb-guide-section__text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular, #606266);
}
.gt-tb-guide-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.gt-tb-guide-card {
  padding: 14px 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  transition: box-shadow 0.2s;
}
.gt-tb-guide-card:hover {
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.1);
}
.gt-tb-guide-card__icon {
  font-size: 20px;
  margin-bottom: 6px;
}
.gt-tb-guide-card__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
  margin-bottom: 4px;
}
.gt-tb-guide-card__desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary, #909399);
}
.gt-tb-guide-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.gt-tb-guide-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
}
.gt-tb-guide-step__num {
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
.gt-tb-guide-step__content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  line-height: 1.5;
}
.gt-tb-guide-step__content b {
  color: var(--el-text-color-primary, #303133);
}
.gt-tb-guide-step__content span {
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
}
.gt-tb-guide-notes {
  margin: 0;
  padding: 0 0 0 4px;
  list-style: none;
  font-size: 13px;
  line-height: 2;
  color: var(--el-text-color-regular, #606266);
}
.gt-tb-guide-notes li {
  padding: 2px 0;
}
/* 按钮功能详解列表 */
.gt-tb-guide-btn-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.gt-tb-guide-btn-item {
  padding: 14px 18px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
}
.gt-tb-guide-btn-item--compact {
  padding: 10px 16px;
}
.gt-tb-guide-btn-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 14px;
}
.gt-tb-guide-btn-item--compact .gt-tb-guide-btn-item__head {
  margin-bottom: 4px;
}
.gt-tb-guide-btn-item__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  font-size: 14px;
}
.gt-tb-guide-btn-item__badge--success { background: #f0f9eb; }
.gt-tb-guide-btn-item__badge--info { background: #ecf5ff; }
.gt-tb-guide-btn-item__badge--primary { background: #f3f0f8; }
.gt-tb-guide-btn-item__badge--danger { background: #fef0f0; }
.gt-tb-guide-btn-item__desc {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular, #606266);
}
.gt-tb-guide-btn-item__desc p {
  margin: 4px 0;
}
.gt-tb-guide-btn-item__desc code {
  background: #f5f0fa;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
  color: var(--gt-color-primary, #4b2d77);
}
/* 表格列含义 */
.gt-tb-guide-table-wrap {
  overflow-x: auto;
}
.gt-tb-guide-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.gt-tb-guide-table th,
.gt-tb-guide-table td {
  padding: 8px 12px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  text-align: left;
}
.gt-tb-guide-table th {
  background: #f5f0fa;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  white-space: nowrap;
}
.gt-tb-guide-table td:first-child {
  font-weight: 500;
  white-space: nowrap;
}
@media (max-width: 900px) {
  .gt-tb-guide-grid {
    grid-template-columns: 1fr;
  }
}

/* 工具栏按钮智能高亮脉冲动效 */
.gt-tb-btn-pulse {
  animation: gt-btn-pulse 2s ease-in-out infinite;
  position: relative;
}
.gt-tb-btn-pulse::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 5px;
  border: 2px solid currentColor;
  opacity: 0;
  animation: gt-btn-ring 2s ease-in-out infinite;
}
@keyframes gt-btn-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.03); }
}
@keyframes gt-btn-ring {
  0% { opacity: 0; transform: scale(0.95); }
  40% { opacity: 0.4; transform: scale(1); }
  100% { opacity: 0; transform: scale(1.08); }
}

/* 科目级穿透追溯弹窗 */
.gt-trace-dialog { padding: 8px 0; }
.gt-trace-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.gt-trace-code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 15px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
  background: #f5f0fa;
  padding: 4px 10px;
  border-radius: 4px;
}
.gt-trace-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.gt-trace-chain {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
}
.gt-trace-node {
  padding: 12px 16px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin: 4px 0;
}
.gt-trace-node--result {
  background: linear-gradient(135deg, #f5f0fa, #ece5f7);
  border-color: var(--gt-color-primary, #4b2d77);
}
.gt-trace-node__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.gt-trace-node__value {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.gt-trace-node__note {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}
.gt-trace-arrow {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 4px 0;
}
.gt-trace-diff {
  margin-top: 16px;
  padding: 10px 14px;
  background: #fdf6ec;
  border-radius: 6px;
  border: 1px solid #faecd8;
  display: flex;
  align-items: center;
}

/* 重算差异△行标记（通过 row-class-name 动态添加） */
:deep(.gt-tb-row-changed) {
  position: relative;
}
:deep(.gt-tb-row-changed td:first-child::before) {
  content: '△';
  position: absolute;
  left: 2px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  color: #e6a23c;
  font-weight: 700;
}

/* 审定数可点击溯源 */
.gt-trace-clickable {
  cursor: pointer;
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  border-bottom: 1px dashed var(--gt-color-primary, #4b2d77);
  transition: border-color 0.2s;
}
.gt-trace-clickable:hover {
  border-color: var(--el-color-primary);
}
.gt-trace-diff-badge {
  font-size: 10px;
  color: #e6a23c;
  font-weight: 700;
  margin-left: 2px;
}

/* 行级操作列：默认透明，hover 行才显示 */
:deep(.gt-tb-row-actions) {
  .cell { padding: 0 4px; }
}
:deep(.gt-tb-row-actions__trigger) {
  opacity: 0;
  transition: opacity .15s;
  color: var(--el-text-color-secondary);
  &:hover { color: var(--el-color-primary); }
}
:deep(.el-table__row:hover) .gt-tb-row-actions__trigger {
  opacity: 1;
}
</style>


