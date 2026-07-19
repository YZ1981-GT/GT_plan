<!--
  G7TabEquityMethodCalc.vue — G7-14 权益法测算表（对齐原底稿三段）

  4区段Tab：
  - Tab1 本期权益法调整: 净利润调整→测算份额→账面确认→差异⑩=⑨-⑤+⑧
  - Tab2 期末余额审核: 成本/损益调整/OCI/其他权益滚存→应享净资产→账面差额
  - Tab3 差额拆解与滚存: 商誉/累计FV/减值→未解释差额→权益法期末余额→审计结论；商誉/FV明细附表
  - Tab4 净资产调整: 按被投资单位滚存所有者权益→回写经审计净资产；差异→建议分录推送G7-3
  - 工具栏「从关联表带入」: G7-2/G7-5/G7-15/G7-13 → G7-14

  公式：
  - adjustedNetProfit / equityShare / ociShare / otherEquityShare
  - incomeDifference = calcIncomeDifference(confirmed, equityShare, dividend)  // ⑩=⑨-⑤+⑧
  - lteiBookBalance / netAssetShareVariance / unexplainedVariance
  - closingBalance = calcEquityMethodBalance(...)

  Spec: .kiro/specs/g7-long-term-equity-method/
-->
<template>
  <div class="g7-tab-equity-method-calc">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-14 权益法测算表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-button
          size="small"
          type="warning"
          :disabled="isReadonly || !suggestedLines.length"
          :loading="pushingG73"
          @click="handlePushToG73"
        >
          推送建议分录至 G7-3
        </el-button>
        <el-dropdown
          trigger="click"
          size="small"
          :disabled="isReadonly || syncingCross"
          @command="handleSyncCommand"
        >
          <el-button size="small" :loading="syncingCross">从关联表带入 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="g74">G7-4 被投资单位（含ID）</el-dropdown-item>
              <el-dropdown-item command="g72">G7-2 期初/本期变动</el-dropdown-item>
              <el-dropdown-item command="g75">G7-5 净利润/净资产</el-dropdown-item>
              <el-dropdown-item command="g715">G7-15 内部交易抵销</el-dropdown-item>
              <el-dropdown-item command="g713">G7-13 商誉/FV明细</el-dropdown-item>
              <el-dropdown-item divided command="all">全部带入</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown trigger="click" size="small" :disabled="importExport.importing.value" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          style="display:none"
          @change="onFileSelected"
        />
        <el-button size="small" @click="openReviewDialog('G7-14-equity-method-calc')">💬复核</el-button>
      </div>
    </div>

    <!-- 蓝色渐变引导区（5步骤指引, 2列grid） -->
    <div class="guidance-steps">
      <div class="step-item">
        <span class="step-num">①</span>
        <span class="step-text">填入被投资方报告净利润</span>
      </div>
      <div class="step-item">
        <span class="step-num">②</span>
        <span class="step-text">填入各项调整（内部交易/FV折旧/政策/其他）</span>
      </div>
      <div class="step-item">
        <span class="step-num">③</span>
        <span class="step-text">系统自动计算调整后净利润和享有份额</span>
      </div>
      <div class="step-item">
        <span class="step-num">④</span>
        <span class="step-text">填入企业确认投资收益，系统自动计算差异</span>
      </div>
      <div class="step-item">
        <span class="step-num">⑤</span>
        <span class="step-text">填入OCI/其他权益变动/股利，系统自动计算期末余额</span>
      </div>
    </div>

    <!-- 方法论上下文区域 -->
    <div class="methodology-context">
      <p><strong>权益法核算公式（CAS2 / 原底稿G7-14）：</strong></p>
      <p>• 调整后净利润 = 报告净利润 − 内部交易抵销 − 公允价值折旧摊销 ± 会计政策调整 ± 其他调整</p>
      <p>• 测算投资收益⑤ = 调整后净利润 × 持股比例；OCI⑥/其他权益⑦同理</p>
      <p>• 投资收益差异⑩ = 账面确认⑨ − 测算⑤ ＋ 已宣告股利⑧（⑨建议取损益调整本期净增加）</p>
      <p>• 长投账面余额 = 投资成本＋损益调整＋OCI＋其他权益变动；差额须用商誉/累计FV调整/减值解释</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：复核权益法下投资收益、其他综合收益及其他权益变动的确认是否恰当，验证应享有份额计算准确、收益差异在可接受范围内。"
      class="objective-alert"
    />

    <!-- 重要性水平设置 -->
    <div class="materiality-bar">
      <span class="materiality-label">重要性水平：</span>
      <el-input-number
        v-if="!isReadonly"
        v-model="materialityLevel"
        :controls="false"
        :precision="2"
        size="small"
        style="width: 160px"
        placeholder="重要性水平(元)"
        @change="emitSave"
      />
      <span v-else class="materiality-value">{{ fmtAmount(materialityLevel) }}</span>
      <span class="materiality-hint">（|投资收益差异| 或 |未解释差额| 超过此值将红色高亮；未填时按分位 0.005 提示）</span>
    </div>

    <el-alert
      v-if="exceptionSummary.length"
      type="warning"
      :closable="false"
      show-icon
      class="objective-alert"
    >
      <template #title>发现 {{ exceptionSummary.length }} 项待关注差异</template>
      <div v-for="msg in exceptionSummary.slice(0, 6)" :key="msg">• {{ msg }}</div>
      <div v-if="suggestedAjeHint" class="aje-hint">{{ suggestedAjeHint }}</div>
      <div v-if="suggestedLines.length" class="aje-hint">
        已生成 {{ suggestedLines.length }} 行建议分录（借贷平衡），可点「推送建议分录至 G7-3」。
      </div>
    </el-alert>

    <!-- 区段Tab切换 -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="activeTab === 'tab4' && !isReadonly"
          size="small"
          @click="syncNetAssetAdjustmentsFromRows"
        >
          按被投资单位刷新
        </el-button>
        <el-button
          v-if="activeTab === 'tab4' && !isReadonly"
          size="small"
          type="primary"
          @click="syncAllAuditedNetAssets"
        >
          回写经审计净资产
        </el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-14" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
        <el-tag v-if="suggestedLines.length" size="small" type="warning">建议分录 {{ suggestedLines.length }} 行</el-tag>
      </div>
    </div>

    <!-- Tab4: 多公司净资产调整 -->
    <div v-if="activeTab === 'tab4'" class="na-adjust-panel">
      <el-alert
        type="info"
        :closable="false"
        class="objective-alert"
        title="按被投资单位填列所有者权益滚存与公允价值/内部交易调整；期末调整后净资产回写至「期末余额审核」的经审计净资产。"
      />
      <div v-if="netAssetAdjustments.length === 0" class="empty-state">
        <p>请先在 Tab1 添加被投资单位，或点击「按被投资单位刷新」</p>
      </div>
      <el-card
        v-for="adj in netAssetAdjustments"
        :key="adj.id"
        class="na-card"
        shadow="never"
      >
        <div class="na-card-head">
          <strong>{{ adj.investeeName }}</strong>
          <div class="na-card-meta">
            <span>持股比例</span>
            <el-input-number
              v-if="!isReadonly"
              :model-value="adj.ownershipRatio"
              :controls="false"
              :step="0.01"
              :precision="4"
              size="small"
              style="width: 110px"
              @update:model-value="(v: number) => { adj.ownershipRatio = normalizeOwnershipRatio(v); onNetAssetChanged(adj) }"
            />
            <span v-else>{{ fmtPercent(adj.ownershipRatio) }}</span>
            <span class="na-summary">调整后净资产期末 {{ fmtAmount(calcAdjustedEquityTotal(adj, 'end')) }}</span>
            <span class="na-summary">应享份额 {{ fmtAmount(calcShareOfAdjustedEquity(adj)) }}</span>
          </div>
        </div>
        <el-table :data="naLineDefs" border size="small" class="na-table">
          <el-table-column label="项目" min-width="160" fixed>
            <template #default="{ row }">{{ row.label }}</template>
          </el-table-column>
          <el-table-column label="期初" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="(adj as any)[row.key].begin"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateNaField(adj, row.key, 'begin', v)"
              />
              <span v-else>{{ fmtAmount((adj as any)[row.key].begin) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="(adj as any)[row.key].increase"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateNaField(adj, row.key, 'increase', v)"
              />
              <span v-else>{{ fmtAmount((adj as any)[row.key].increase) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期减少" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="(adj as any)[row.key].decrease"
                size="small"
                :controls="false"
                style="width:100%"
                @update:model-value="(v: number) => updateNaField(adj, row.key, 'decrease', v)"
              />
              <span v-else>{{ fmtAmount((adj as any)[row.key].decrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmount(rollforwardEnd((adj as any)[row.key])) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!isReadonly" class="na-card-actions">
          <el-button size="small" type="primary" link @click="syncOneAuditedNetAssets(adj)">
            回写本单位经审计净资产
          </el-button>
        </div>
      </el-card>

      <!-- 建议分录预览 -->
      <el-card v-if="suggestedLines.length" class="aje-preview-card" shadow="never">
        <div class="conclusion-head">
          <span class="conclusion-title">建议调整分录预览（⑩自动；⑮需选差额性质）</span>
          <el-button
            size="small"
            type="warning"
            :disabled="isReadonly"
            :loading="pushingG73"
            @click="handlePushToG73"
          >
            推送至 G7-3
          </el-button>
        </div>
        <el-table :data="suggestedLines" border size="small" max-height="280">
          <el-table-column prop="investeeName" label="被投资单位" min-width="120" />
          <el-table-column prop="accountCode" label="科目" width="80" />
          <el-table-column prop="accountName" label="科目名称" min-width="110" />
          <el-table-column label="借方" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.debitAmount) }}</template>
          </el-table-column>
          <el-table-column label="贷方" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.creditAmount) }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="说明" min-width="180" show-overflow-tooltip />
        </el-table>
      </el-card>
    </div>

    <!-- Tab1–3: 分组测算表 -->
    <div v-else class="equity-scroll-container">
      <template v-for="group in groups" :key="group.investeeName">
        <!-- 分组标题 -->
        <div class="group-header" @click="toggleGroup(group.investeeName)">
          <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[group.investeeName] }">
            <ArrowDown />
          </el-icon>
          <span class="group-name">{{ group.investeeName }}</span>
          <span class="group-count">({{ group.rows.length }}行)</span>
          <div class="group-actions" v-if="!isReadonly" @click.stop>
            <el-button size="small" type="primary" link @click="addRowToGroup(group.investeeName)">
              + 添加行
            </el-button>
          </div>
        </div>

        <!-- 分组表格 -->
        <div v-show="expandedMap[group.investeeName]" class="group-body">
          <el-table
            :data="group.rows"
            border
            size="small"
            class="equity-calc-table"
            :max-height="400"
            highlight-current-row
            row-key="id"
            @current-change="(row: any) => onCurrentChange(row)"
          >
            <!-- 序号 -->
            <el-table-column type="index" label="#" width="45" align="center" fixed />

            <!-- ═══ Tab1: 净利润调整(10列) ═══ -->
            <template v-if="activeTab === 'tab1'">
              <!-- 报告净利润 -->
              <el-table-column label="报告净利润" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.reportedNetProfit" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'reportedNetProfit', v)" />
                  <span v-else>{{ fmtAmount(row.reportedNetProfit) }}</span>
                </template>
              </el-table-column>

              <!-- 内部交易抵销 -->
              <el-table-column label="内部交易抵销" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.internalTransactionAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'internalTransactionAdj', v)" />
                  <span v-else>{{ fmtAmount(row.internalTransactionAdj) }}</span>
                </template>
              </el-table-column>

              <!-- FV折旧摊销 -->
              <el-table-column label="FV折旧摊销" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.fvDepreciationAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'fvDepreciationAdj', v)" />
                  <span v-else>{{ fmtAmount(row.fvDepreciationAdj) }}</span>
                </template>
              </el-table-column>

              <!-- 会计政策调整 -->
              <el-table-column label="会计政策调整" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.accountingPolicyAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'accountingPolicyAdj', v)" />
                  <span v-else>{{ fmtAmount(row.accountingPolicyAdj) }}</span>
                </template>
              </el-table-column>

              <!-- 其他调整 -->
              <el-table-column label="其他调整" min-width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.otherAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'otherAdj', v)" />
                  <span v-else>{{ fmtAmount(row.otherAdj) }}</span>
                </template>
              </el-table-column>

              <!-- 调整后净利润（公式列） -->
              <el-table-column label="调整后净利润" min-width="130" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :title="'调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他调整'"
                  >{{ fmtAmount(row.adjustedNetProfit) }}</span>
                </template>
              </el-table-column>

              <!-- 持股比例 -->
              <el-table-column label="持股比例" min-width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.investmentRatio" size="small"
                    :controls="false" :precision="4" :step="0.01" :min="0" :max="1"
                    style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'investmentRatio', v)" />
                  <span v-else>{{ fmtPercent(row.investmentRatio) }}</span>
                </template>
              </el-table-column>

              <!-- 享有份额（公式列） -->
              <el-table-column label="享有份额" min-width="120" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :title="'享有份额 = 调整后净利润 × 持股比例'"
                  >{{ fmtAmount(row.equityShare) }}</span>
                </template>
              </el-table-column>

              <!-- 企业确认收益 -->
              <el-table-column label="账面确认投资收益⑨" min-width="150" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.confirmedIncome" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'confirmedIncome', v)" />
                  <span v-else>{{ fmtAmount(row.confirmedIncome) }}</span>
                </template>
              </el-table-column>

              <!-- 已宣告股利 -->
              <el-table-column label="已宣告股利⑧" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.dividendDistributed" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'dividendDistributed', v)" />
                  <span v-else>{{ fmtAmount(row.dividendDistributed) }}</span>
                </template>
              </el-table-column>

              <!-- 投资收益差异（原底稿⑩） -->
              <el-table-column label="投资收益差异⑩" min-width="140" align="right">
                <template #default="{ row }">
                  <el-tooltip
                    v-if="isOverMateriality(row.incomeDifference)"
                    content="投资收益差异超过重要性水平"
                    placement="top"
                  >
                    <span class="formula-cell income-diff-warning">
                      {{ fmtAmount(row.incomeDifference) }}
                    </span>
                  </el-tooltip>
                  <span v-else
                    class="formula-cell"
                    :title="'⑩=⑨−⑤＋⑧（账面确认−测算投资收益＋已宣告股利）'"
                  >{{ fmtAmount(row.incomeDifference) }}</span>
                </template>
              </el-table-column>
            </template>

            <!-- ═══ Tab2: 期末余额审核 ═══ -->
            <template v-if="activeTab === 'tab2'">
              <el-table-column label="成本期初" min-width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.costOpening" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'costOpening', v)" />
                  <span v-else>{{ fmtAmount(row.costOpening) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="成本增减" min-width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.costChange" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'costChange', v)" />
                  <span v-else>{{ fmtAmount(row.costChange) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="成本期末" min-width="110" align="right">
                <template #default="{ row }">
                  <span class="formula-cell" title="期初+本期增减">{{ fmtAmount(row.costClosing) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="损益调整期初" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.pnlAdjOpening" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'pnlAdjOpening', v)" />
                  <span v-else>{{ fmtAmount(row.pnlAdjOpening) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="损益调整增减" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.pnlAdjChange" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'pnlAdjChange', v)" />
                  <span v-else>{{ fmtAmount(row.pnlAdjChange) }}</span>
                  <div class="hint-line" title="建议=测算投资收益−已宣告股利">建议 {{ fmtAmount(suggestedPnlAdjChange(row)) }}</div>
                </template>
              </el-table-column>
              <el-table-column label="OCI期初" min-width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.ociBalOpening" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'ociBalOpening', v)" />
                  <span v-else>{{ fmtAmount(row.ociBalOpening) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="其他权益期初" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.otherEqBalOpening" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'otherEqBalOpening', v)" />
                  <span v-else>{{ fmtAmount(row.otherEqBalOpening) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="经审计净资产" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.auditedNetAssets" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'auditedNetAssets', v)" />
                  <span v-else>{{ fmtAmount(row.auditedNetAssets) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="应享净资产" min-width="120" align="right">
                <template #default="{ row }">
                  <span class="formula-cell" title="经审计净资产×持股比例">{{ fmtAmount(row.shareOfAuditedNetAssets) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="长投账面余额" min-width="130" align="right">
                <template #default="{ row }">
                  <span class="formula-cell" title="成本+损益调整+OCI+其他权益">{{ fmtAmount(row.lteiBookBalance) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="与享有净资产差额" min-width="140" align="right">
                <template #default="{ row }">
                  <span class="formula-cell" title="长投账面余额−应享净资产">{{ fmtAmount(row.netAssetShareVariance) }}</span>
                </template>
              </el-table-column>
            </template>

            <!-- ═══ Tab3: 差额拆解与滚存 ═══ -->
            <template v-if="activeTab === 'tab3'">
              <el-table-column label="OCI变动" min-width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.ociChange" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'ociChange', v)" />
                  <span v-else>{{ fmtAmount(row.ociChange) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="享有OCI" min-width="110" align="right">
                <template #default="{ row }">
                  <span class="formula-cell" title="OCI变动×持股比例">{{ fmtAmount(row.ociShare) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="其他权益变动" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.otherEquityChange" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'otherEquityChange', v)" />
                  <span v-else>{{ fmtAmount(row.otherEquityChange) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="商誉/初始差额" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.goodwill" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'goodwill', v)" />
                  <span v-else>{{ fmtAmount(row.goodwill) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="累计FV调整" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.cumulativeFvAdj" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'cumulativeFvAdj', v)" />
                  <span v-else>{{ fmtAmount(row.cumulativeFvAdj) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="减值准备" min-width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.impairment" size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'impairment', v)" />
                  <span v-else>{{ fmtAmount(row.impairment) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="未解释差额" min-width="120" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :class="{ 'income-diff-warning': isOverMateriality(row.unexplainedVariance) }"
                    title="与享有净资产差额−商誉−累计FV调整＋减值"
                  >{{ fmtAmount(row.unexplainedVariance) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="差额性质" min-width="160">
                <template #default="{ row }">
                  <el-select
                    v-if="!isReadonly"
                    :model-value="row.unexplainedNature || 'pending'"
                    size="small"
                    style="width:100%"
                    @update:model-value="(v: string) => updateUnexplainedNature(row, v as any)"
                  >
                    <el-option
                      v-for="opt in UNEXPLAINED_NATURE_OPTIONS"
                      :key="opt.value"
                      :value="opt.value"
                      :label="opt.label"
                    />
                  </el-select>
                  <span v-else>{{ UNEXPLAINED_NATURE_OPTIONS.find(o => o.value === row.unexplainedNature)?.label || '待拆解' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="差额解释" min-width="160">
                <template #default="{ row }">
                  <el-input v-if="!isReadonly" v-model="row.varianceExplanation" size="small"
                    placeholder="商誉/FV/减值等" @change="emitSave" />
                  <span v-else>{{ row.varianceExplanation }}</span>
                </template>
              </el-table-column>
              <el-table-column label="权益法期末余额" min-width="130" align="right">
                <template #default="{ row }">
                  <span class="formula-cell" title="期初+投资收益+OCI+其他权益−股利">{{ fmtAmount(row.closingBalance) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="审计结论" min-width="120" align="center">
                <template #default="{ row }">
                  <el-select v-if="!isReadonly" v-model="row.auditConclusion" size="small"
                    style="width:100%" @change="emitSave">
                    <el-option value="无差异" label="无差异" />
                    <el-option value="差异可接受" label="差异可接受" />
                    <el-option value="差异需调整" label="差异需调整" />
                  </el-select>
                  <el-tag v-else size="small" :type="conclusionTagType(row.auditConclusion)">
                    {{ row.auditConclusion }}
                  </el-tag>
                </template>
              </el-table-column>
            </template>

            <!-- 操作列（删除） -->
            <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
              <template #default="{ row }">
                <el-popconfirm :title="`确认删除此行?`" @confirm="deleteRow(row)">
                  <template #reference>
                    <el-button type="danger" link size="small">✕</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-if="groups.length === 0" class="empty-state">
        <p>暂无权益法测算数据</p>
        <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddRow">
          + 新增被投资单位
        </el-button>
      </div>

      <!-- Tab3: 商誉/累计FV明细附表 -->
      <el-card v-if="activeTab === 'tab3'" class="gwf-detail-card" shadow="never">
        <div class="conclusion-head">
          <span class="conclusion-title">商誉 / 累计公允价值调整明细</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            link
            @click="handleAddGoodwillFvLine"
          >
            + 明细行
          </el-button>
        </div>
        <p class="gwf-hint">
          明细合计回写「商誉」「累计FV调整」「FV折旧摊销」列；累计FV可填期初/本期摊销/其他变动自动重算期末。
          <span v-if="lastCrossSheetSync?.at" class="gwf-sync-meta">
            最近带入：{{ lastCrossSheetSync.sources.join('+') }}（{{ lastCrossSheetSync.changeCount }}项）
          </span>
        </p>
        <el-table :data="goodwillFvDetails" border size="small" max-height="320">
          <el-table-column label="被投资单位" min-width="130">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                v-model="row.investeeName"
                size="small"
                filterable
                allow-create
                default-first-option
                style="width:100%"
                @change="onGoodwillFvChanged"
              >
                <el-option
                  v-for="name in investeeNameOptions"
                  :key="name"
                  :label="name"
                  :value="name"
                />
              </el-select>
              <span v-else>{{ row.investeeName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                v-model="row.kind"
                size="small"
                style="width:100%"
                @change="onGoodwillFvChanged"
              >
                <el-option label="商誉" value="goodwill" />
                <el-option label="累计FV" value="fvAdj" />
              </el-select>
              <span v-else>{{ row.kind === 'goodwill' ? '商誉' : '累计FV' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.description"
                size="small"
                @change="emitSave"
              />
              <span v-else>{{ row.description }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初未摊销" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.kind === 'fvAdj'">
                <el-input-number
                  v-if="!isReadonly"
                  v-model="row.openingUnamortized"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @change="onGoodwillFvChanged"
                />
                <span v-else>{{ fmtAmount(row.openingUnamortized) }}</span>
              </template>
              <span v-else class="gwf-na">—</span>
            </template>
          </el-table-column>
          <el-table-column label="本期摊销" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.kind === 'fvAdj'">
                <el-input-number
                  v-if="!isReadonly"
                  v-model="row.currentDepreciationAdj"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @change="onGoodwillFvChanged"
                />
                <span v-else>{{ fmtAmount(row.currentDepreciationAdj) }}</span>
              </template>
              <span v-else class="gwf-na">—</span>
            </template>
          </el-table-column>
          <el-table-column label="其他变动" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.kind === 'fvAdj'">
                <el-input-number
                  v-if="!isReadonly"
                  v-model="row.otherChange"
                  size="small"
                  :controls="false"
                  style="width:100%"
                  @change="onGoodwillFvChanged"
                />
                <span v-else>{{ fmtAmount(row.otherChange) }}</span>
              </template>
              <span v-else class="gwf-na">—</span>
            </template>
          </el-table-column>
          <el-table-column label="期末/金额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.kind === 'goodwill'"
                v-model="row.amount"
                size="small"
                :controls="false"
                style="width:100%"
                @change="onGoodwillFvChanged"
              />
              <span v-else class="formula-cell">{{ fmtAmount(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="索引" min-width="90">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.indexRef"
                size="small"
                @change="emitSave"
              />
              <span v-else>{{ row.indexRef }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="70" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="handleRemoveGoodwillFvLine(row.id)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-head">
        <span class="conclusion-title">审计说明</span>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-head">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link @click="handleAiConclusion">
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="根据权益法测算结果，总结投资收益差异是否在可接受范围内..."
        @change="emitSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 调整后净利润 = 报告净利润 − 内部交易 − FV折旧 ± 政策/其他调整；测算投资收益⑤ = 调整后净利润 × 持股比例</p>
        <p>2. 投资收益差异⑩ = 账面确认⑨ − 测算⑤ ＋ 已宣告股利⑧（⑨建议取损益调整本期净增加，正确时⑩≈0）</p>
        <p>3. 长投账面余额 = 投资成本＋损益调整＋OCI＋其他权益变动；应享净资产 = 经审计净资产 × 持股比例</p>
        <p>4. 与享有净资产差额须拆解为商誉/累计公允价值调整/减值；未解释差额应接近0</p>
        <p>5. 经审计净资产取自「4.净资产调整」期末调整后所有者权益，或 G7-5/G7-15 相关测算后回写</p>
        <p>6. |投资收益差异| 或 |未解释差额| 超过重要性水平时红色高亮（未填重要性时按分位 0.005）；可一键生成借贷平衡建议分录并推送 G7-3</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabEquityMethodCalc — G7-14 权益法测算表（★最核心★）
 *
 * 54行×20列→2区段Tab + 虚拟滚动 + 按被投资单位分组
 *
 * 公式引擎调用：
 * - calcAdjustedNetProfit → Tab1 调整后净利润
 * - calcEquityShare → Tab1 享有份额 / Tab2 OCI份额 / Tab2 其他权益份额
 * - calcEquityMethodBalance → Tab2 期末余额
 *
 * |收益差异| > materialityLevel → 红色高亮 + tooltip
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 7.4, 7.5
 */
import { ref, reactive, computed, inject, onMounted, watch } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  parseNum,
  calcAdjustedNetProfit,
  calcEquityShare,
  calcEquityMethodBalance,
  calcIncomeDifference,
  calcLteiBookBalance,
  calcNetAssetShareVariance,
  calcUnexplainedVariance,
} from '../../composables/useG7EquityMethodFormulaEngine'
import { fmtAmount } from '@/utils/formatters'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { EquityMethodCalcRow } from '../../composables/useG7EquityMethodFormData'
import {
  buildSuggestedAdjustments,
  calcAdjustedEquityTotal,
  calcShareOfAdjustedEquity,
  ensureNetAssetAdjustments,
  hydrateNetAssetAdjustment,
  isAmountOverMateriality,
  normalizeOwnershipRatio,
  rollforwardEnd,
  syncAuditedNetAssetsFromAdjustment,
  UNEXPLAINED_NATURE_OPTIONS,
  type NetAssetAdjustment,
  type SuggestedAdjustmentLine,
  type UnexplainedNature,
} from './g7EquityMethodCalcModel'
import { pushSuggestedAdjustmentsToG73, resolveG7MainWorkpaperId } from './g7EquityMethodPushG73'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import {
  G7_2_ROWS_KEY,
  G7_5_ROWS_KEY,
  G7_13_ROWS_KEY,
  G7_15_ROWS_KEY,
  G7_15_SECTION_KEY,
  applyFinancialInfoToG714Payload,
  applyG72EquityToG714Payload,
  applyG74InvesteesToG714Payload,
  applyGoodwillFvDetailsToRows,
  applyInternalElimToG714Payload,
  applyInvestmentCostToG714Payload,
  addGoodwillFvDetail,
  buildG714SyncPreview,
  formatSyncPreviewMessage,
  removeGoodwillFvDetail,
  stampLastCrossSheetSync,
  G7_4_ROWS_KEY,
  type GoodwillFvDetailLine,
  type LastCrossSheetSyncMeta,
} from '../../composables/g7EquityMethodCrossSheet'
import http from '@/utils/http'

// ═══ Props ═══════════════════════════════════════════════════════════════════

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

// ═══ Types ═══════════════════════════════════════════════════════════════════

interface EquityCalcGroup {
  investeeName: string
  rows: EquityMethodCalcRow[]
}

interface EquityMethodCalcSavePayload {
  rows: EquityMethodCalcRow[]
  materialityLevel: number
  conclusion: string
  groups: EquityCalcGroup[]
  netAssetAdjustments: NetAssetAdjustment[]
  goodwillFvDetails: GoodwillFvDetailLine[]
  lastCrossSheetSync?: LastCrossSheetSyncMeta | null
}

const SECTION_KEY = 'G7-14-equity-method-calc'
const ROWS_KEY = 'G7-14-rows'
const AUDIT_NOTE_KEY = 'G7-14-audit-note'

// ═══ Injections ═══════════════════════════════════════════════════════════════

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ═══ State ═══════════════════════════════════════════════════════════════════

const isReadonly = computed(() => !!props.readonly)
const groups = reactive<EquityCalcGroup[]>([])
const expandedMap = reactive<Record<string, boolean>>({})
const materialityLevel = ref<number>(0)
const conclusion = ref<string>('')
const selectedRowIndex = ref<number>(-1)
const netAssetAdjustments = reactive<NetAssetAdjustment[]>([])
const goodwillFvDetails = reactive<GoodwillFvDetailLine[]>([])
/** 商誉/FV 明细曾驱动过的被投资单位，改名时用于清零旧汇总 */
const gwfTrackedNames = ref<string[]>([])
const lastCrossSheetSync = ref<LastCrossSheetSyncMeta | null>(null)
const pushingG73 = ref(false)
const syncingCross = ref(false)

const naLineDefs: { key: keyof NetAssetAdjustment; label: string }[] = [
  { key: 'shareCapital', label: '实收资本（或股本）' },
  { key: 'capitalReserve', label: '资本公积' },
  { key: 'treasuryStock', label: '减：库存股' },
  { key: 'oci', label: '其他综合收益' },
  { key: 'surplusReserve', label: '盈余公积' },
  { key: 'specialReserve', label: '专项储备' },
  { key: 'retainedEarnings', label: '未分配利润' },
  { key: 'nonControllingInterest', label: '少数股东权益（展示项，不计入归母调整后净资产）' },
  { key: 'fvDiffAtAcquisition', label: '加：取得投资时公允价值差额' },
  { key: 'otherProfitAdj', label: '加：其他需调整损益的项目' },
  { key: 'openingFvDiffCumulative', label: '加：期初累计公允价值调整' },
  { key: 'unrealizedInternalElim', label: '减：未实现内部交易损益' },
]

// ═══ 持久化（checklist_responses） ═══════════════════════════════════════════

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const importExport = useG7EquityMethodImportExport({
  wpId: computed(() => props.wpId),
})
const fileInput = ref<HTMLInputElement | null>(null)
const auditNote = ref('')
const rowCount = computed(() => groups.reduce((n, g) => n + g.rows.length, 0))

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

type TabKey = 'tab1' | 'tab2' | 'tab3' | 'tab4'
const activeTab = ref<TabKey>('tab1')

const segmentOptions = [
  { label: '1.本期权益法调整', value: 'tab1' },
  { label: '2.期末余额审核', value: 'tab2' },
  { label: '3.差额与滚存', value: 'tab3' },
  { label: '4.净资产调整/建议分录', value: 'tab4' },
]

// ═══ 折叠状态持久化 ═══════════════════════════════════════════════════════

const STORAGE_KEY_PREFIX = 'g7-equity-method-calc-collapse-'

function getStorageKey(): string {
  return `${STORAGE_KEY_PREFIX}${props.wpId}`
}

function loadCollapseState(): void {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (raw) {
      const saved = JSON.parse(raw) as Record<string, boolean>
      Object.assign(expandedMap, saved)
    }
  } catch { /* ignore */ }
}

function saveCollapseState(): void {
  try {
    localStorage.setItem(getStorageKey(), JSON.stringify({ ...expandedMap }))
  } catch { /* ignore */ }
}

function toggleGroup(name: string): void {
  expandedMap[name] = !expandedMap[name]
  saveCollapseState()
}

// ═══ 行同步 ═══════════════════════════════════════════════════════════════════

function onCurrentChange(row: EquityMethodCalcRow | null) {
  if (row) {
    const allRows = groups.flatMap(g => g.rows)
    selectedRowIndex.value = allRows.findIndex(r => r.id === row.id)
  }
}

// ═══ 公式自动计算 ═══════════════════════════════════════════════════════════

/**
 * 重新计算单行所有公式列（对齐原底稿三段逻辑）
 */
function recalcRow(row: EquityMethodCalcRow): void {
  row.adjustedNetProfit = calcAdjustedNetProfit(
    row.reportedNetProfit,
    row.internalTransactionAdj,
    row.fvDepreciationAdj,
    row.accountingPolicyAdj,
    row.otherAdj,
  )
  row.equityShare = calcEquityShare(row.adjustedNetProfit, row.investmentRatio)
  row.ociShare = calcEquityShare(row.ociChange, row.investmentRatio)
  row.otherEquityShare = calcEquityShare(row.otherEquityChange, row.investmentRatio)

  // 原底稿 ⑩=⑨-⑤+⑧
  row.incomeDifference = calcIncomeDifference(
    row.confirmedIncome,
    row.equityShare,
    row.dividendDistributed,
  )
  row.ociDifference = Math.round(
    (parseNum(row.confirmedOci) - parseNum(row.ociShare)) * 100,
  ) / 100
  row.otherEquityDifference = Math.round(
    (parseNum(row.confirmedOtherEquity) - parseNum(row.otherEquityShare)) * 100,
  ) / 100

  row.costClosing = Math.round(
    (parseNum(row.costOpening) + parseNum(row.costChange)) * 100,
  ) / 100
  row.pnlAdjClosing = Math.round(
    (parseNum(row.pnlAdjOpening) + parseNum(row.pnlAdjChange)) * 100,
  ) / 100
  // OCI/其他权益本期增减取测算份额
  row.ociBalChange = row.ociShare
  row.otherEqBalChange = row.otherEquityShare
  row.ociBalClosing = Math.round(
    (parseNum(row.ociBalOpening) + parseNum(row.ociBalChange)) * 100,
  ) / 100
  row.otherEqBalClosing = Math.round(
    (parseNum(row.otherEqBalOpening) + parseNum(row.otherEqBalChange)) * 100,
  ) / 100

  row.lteiBookBalance = calcLteiBookBalance(
    row.costClosing,
    row.pnlAdjClosing,
    row.ociBalClosing,
    row.otherEqBalClosing,
  )
  row.shareOfAuditedNetAssets = calcEquityShare(row.auditedNetAssets, row.investmentRatio)
  row.netAssetShareVariance = calcNetAssetShareVariance(
    row.lteiBookBalance,
    row.auditedNetAssets,
    row.investmentRatio,
  )
  row.unexplainedVariance = calcUnexplainedVariance(
    row.netAssetShareVariance,
    row.goodwill,
    row.cumulativeFvAdj,
    row.impairment,
  )

  row.closingBalance = calcEquityMethodBalance(
    row.openingBalance,
    row.equityShare,
    row.ociShare,
    row.otherEquityShare,
    row.dividendDistributed,
  )
}

// ═══ 字段更新 + 触发重算 ═══════════════════════════════════════════════════

function updateNumField(row: EquityMethodCalcRow, field: keyof EquityMethodCalcRow, value: number): void {
  let next = value ?? 0
  if (field === 'investmentRatio') next = normalizeOwnershipRatio(next)
  ;(row as any)[field] = next
  recalcRow(row)
  emitSave()
}

function updateUnexplainedNature(row: EquityMethodCalcRow, nature: UnexplainedNature): void {
  row.unexplainedNature = nature || 'pending'
  emitSave()
}

// ═══ 重要性水平判断 ═══════════════════════════════════════════════════════

/**
 * |差异| > 有效重要性水平 → true（红色高亮）
 * 重要性未设置(≤0)时与建议分录一致，按分位 0.005 判断。
 */
function isOverMateriality(amount: number): boolean {
  return isAmountOverMateriality(amount, materialityLevel.value)
}

function suggestedPnlAdjChange(row: EquityMethodCalcRow): number {
  return Math.round((parseNum(row.equityShare) - parseNum(row.dividendDistributed)) * 100) / 100
}

const allRows = computed(() => groups.flatMap(g => g.rows))

const exceptionSummary = computed(() => {
  const msgs: string[] = []
  for (const row of allRows.value) {
    const name = row.investeeName || `第${row.seq}行`
    if (isOverMateriality(row.incomeDifference)) {
      msgs.push(`${name}：投资收益差异 ${row.incomeDifference.toFixed(2)} 超过重要性水平`)
    }
    if (isOverMateriality(row.unexplainedVariance)) {
      msgs.push(`${name}：未解释差额 ${row.unexplainedVariance.toFixed(2)} 超过重要性水平`)
    }
    const suggested = suggestedPnlAdjChange(row)
    if (
      Math.abs(parseNum(row.pnlAdjChange) - suggested) > 0.005
      && (parseNum(row.equityShare) !== 0 || parseNum(row.dividendDistributed) !== 0)
    ) {
      msgs.push(`${name}：损益调整增减与建议值(测算收益−股利=${suggested.toFixed(2)})不一致`)
    }
  }
  return msgs
})

const suggestedAjeHint = computed(() => {
  if (!exceptionSummary.value.length) return ''
  return '建议分录：⑩自动生成；⑮需在「差额性质」中选择可入账类型后才会生成。商誉/累计FV请改填对应列，勿重复推送。'
})

const suggestedLines = computed<SuggestedAdjustmentLine[]>(() =>
  buildSuggestedAdjustments(allRows.value, materialityLevel.value),
)

function replaceNetAssetAdjustments(list: NetAssetAdjustment[]): void {
  netAssetAdjustments.splice(0, netAssetAdjustments.length, ...list)
}

function replaceGoodwillFvDetails(list: GoodwillFvDetailLine[]): void {
  goodwillFvDetails.splice(0, goodwillFvDetails.length, ...list.map((d) => ({
    id: d.id || `gwf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    investeeName: String(d.investeeName || ''),
    investeeId: String(d.investeeId || '') || undefined,
    kind: d.kind === 'fvAdj' ? 'fvAdj' : 'goodwill',
    description: String(d.description || ''),
    amount: parseNum(d.amount),
    indexRef: String(d.indexRef || ''),
    openingUnamortized: d.openingUnamortized != null ? parseNum(d.openingUnamortized) : undefined,
    currentDepreciationAdj: d.currentDepreciationAdj != null ? parseNum(d.currentDepreciationAdj) : undefined,
    otherChange: d.otherChange != null ? parseNum(d.otherChange) : undefined,
  })))
  gwfTrackedNames.value = [
    ...new Set(goodwillFvDetails.map((d) => d.investeeName).filter(Boolean)),
  ]
}

const investeeNameOptions = computed(() =>
  groups.map((g) => g.investeeName).filter(Boolean),
)

function applyPayloadToUi(payload: any): void {
  groups.length = 0
  Object.keys(expandedMap).forEach((k) => delete expandedMap[k])
  replaceNetAssetAdjustments([])
  replaceGoodwillFvDetails([])
  lastCrossSheetSync.value = payload?.lastCrossSheetSync ?? null
  hydrateFromData(payload)
}

async function persistPayloadNow(payload?: EquityMethodCalcSavePayload): Promise<void> {
  if (isReadonly.value) return
  const data = payload ?? buildPayload()
  const pageJson = JSON.stringify(data)
  const rowsJson = JSON.stringify(data.rows)
  await formData.saveBatch([
    { itemId: SECTION_KEY, data: { conclusion: pageJson, remark: null } },
    { itemId: ROWS_KEY, data: { conclusion: rowsJson, remark: rowsJson } },
  ])
}

async function fetchChecklistConclusion(wpId: string, itemIds: string[]): Promise<unknown> {
  const res: any = await http.get(`/api/workpapers/${wpId}/checklist-responses`, {
    _silent: true,
  } as any)
  const items = Array.isArray(res) ? res : res?.data || []
  for (const id of itemIds) {
    const hit = items.find((it: any) => it?.item_id === id)
    if (hit?.conclusion != null && hit.conclusion !== '') return hit.conclusion
    if (hit?.remark != null && hit.remark !== '') return hit.remark
  }
  return null
}

async function loadLocalChecklist(itemIds: string[]): Promise<unknown> {
  await formData.loadResponses()
  for (const id of itemIds) {
    const raw = formData.data.value.get(id)?.conclusion
      ?? formData.data.value.get(id)?.remark
    if (raw != null && raw !== '') return raw
  }
  // fallback：直读接口（formData 可能尚未含该键）
  return fetchChecklistConclusion(props.wpId, itemIds)
}

async function runCrossSheetSync(
  kind: 'g74' | 'g72' | 'g75' | 'g715' | 'g713' | 'all',
): Promise<void> {
  if (isReadonly.value) return
  syncingCross.value = true
  try {
    let payload: any = buildPayload()
    const messages: string[] = []
    const failMessages: string[] = []
    const warningMessages: string[] = []

    const applyOne = (
      result: { ok: boolean; message: string; payload?: any; warnings?: string[] },
    ) => {
      if (result.warnings?.length) warningMessages.push(...result.warnings)
      if (result.ok && result.payload) {
        payload = result.payload
        messages.push(result.message)
      } else {
        failMessages.push(result.message)
      }
    }

    if (kind === 'g74' || kind === 'all') {
      const g74 = await loadLocalChecklist([G7_4_ROWS_KEY])
        ?? formData.parseContent()?.basicInfo
        ?? (props.htmlData as any)?.basicInfo
      applyOne(applyG74InvesteesToG714Payload(payload, g74))
    }
    if (kind === 'g72' || kind === 'all') {
      const mainWpId = await resolveG7MainWorkpaperId(props.projectId, props.wpId)
      if (!mainWpId) {
        failMessages.push('未找到 G7 主表底稿，无法读取 G7-2')
      } else {
        const g72 = await fetchChecklistConclusion(mainWpId, [G7_2_ROWS_KEY])
        applyOne(applyG72EquityToG714Payload(payload, g72))
      }
    }
    if (kind === 'g75' || kind === 'all') {
      const g75 = await loadLocalChecklist([G7_5_ROWS_KEY])
        ?? formData.parseContent()?.financialInfo
        ?? (props.htmlData as any)?.financialInfo
      let g75Result = applyFinancialInfoToG714Payload(payload, g75, { includeUnaudited: false })
      // 单源带入时：若有未审被跳过，询问是否强制一并带入
      if (
        kind === 'g75'
        && g75Result.warnings?.length
        && (g75Result.ok || g75Result.message.includes('未审'))
      ) {
        try {
          await ElMessageBox.confirm(
            `${g75Result.warnings.join('；')}。是否一并带入未审/待确认数据？`,
            'G7-5 含未审数据',
            {
              confirmButtonText: '一并带入',
              cancelButtonText: g75Result.ok ? '仅保留已审' : '取消',
              type: 'warning',
              distinguishCancelAndClose: true,
            },
          )
          g75Result = applyFinancialInfoToG714Payload(payload, g75, { includeUnaudited: true })
        } catch (action) {
          if (action === 'close' || (!g75Result.ok && action === 'cancel')) {
            ElMessage.info('已取消 G7-5 带入')
            return
          }
          // cancel + 已有已审结果：继续用仅已审
        }
      }
      applyOne(g75Result)
    }
    if (kind === 'g715' || kind === 'all') {
      const g715 = await loadLocalChecklist([G7_15_SECTION_KEY, G7_15_ROWS_KEY])
        ?? formData.parseContent()?.internalTransaction
        ?? (props.htmlData as any)?.internalTransaction
      applyOne(applyInternalElimToG714Payload(payload, g715))
    }
    if (kind === 'g713' || kind === 'all') {
      const g713 = await loadLocalChecklist([G7_13_ROWS_KEY])
        ?? formData.parseContent()?.investmentCostTest
        ?? (props.htmlData as any)?.investmentCostTest
      applyOne(applyInvestmentCostToG714Payload(payload, g713))
    }

    if (!messages.length) {
      const tip = [
        ...failMessages,
        ...warningMessages,
      ].filter(Boolean).join('；') || '未同步到任何数据'
      ElMessage.warning(tip)
      return
    }

    const beforePayload = buildPayload()
    const previewLines = buildG714SyncPreview(beforePayload, payload)
    const sources = messages.map((m) => {
      if (m.includes('G7-4')) return 'G7-4'
      if (m.includes('G7-2')) return 'G7-2'
      if (m.includes('G7-5')) return 'G7-5'
      if (m.includes('G7-15')) return 'G7-15'
      if (m.includes('G7-13')) return 'G7-13'
      return '关联表'
    })
    try {
      await ElMessageBox.confirm(
        formatSyncPreviewMessage(previewLines),
        '确认带入并覆盖',
        {
          confirmButtonText: '确认覆盖',
          cancelButtonText: '取消',
          type: 'warning',
          dangerouslyUseHTMLString: true,
        },
      )
    } catch {
      ElMessage.info('已取消带入')
      return
    }

    stampLastCrossSheetSync(payload, [...new Set(sources)], previewLines.length)
    applyPayloadToUi(payload)
    await persistPayloadNow(buildPayload())

    if (failMessages.length || warningMessages.length) {
      ElMessage.warning(
        [
          `部分完成：${messages.join('；')}`,
          failMessages.length ? `未成功：${failMessages.join('；')}` : '',
          warningMessages.length ? `注意：${warningMessages.join('；')}` : '',
        ].filter(Boolean).join('。'),
      )
    } else {
      ElMessage.success(messages.join('；'))
    }
  } catch {
    ElMessage.error('关联表带入失败，请稍后重试')
  } finally {
    syncingCross.value = false
  }
}

function handleSyncCommand(command: string): void {
  if (
    command === 'g74'
    || command === 'g72'
    || command === 'g75'
    || command === 'g715'
    || command === 'g713'
    || command === 'all'
  ) {
    void runCrossSheetSync(command)
  }
}

function onGoodwillFvChanged(): void {
  const payload = buildPayload()
  const previousNames = [...gwfTrackedNames.value]
  applyGoodwillFvDetailsToRows(payload, previousNames)
  gwfTrackedNames.value = [
    ...new Set((payload.goodwillFvDetails || []).map((d: GoodwillFvDetailLine) => d.investeeName).filter(Boolean)),
  ]
  // 仅回写公式列，保留用户明细编辑
  groups.length = 0
  Object.keys(expandedMap).forEach((k) => delete expandedMap[k])
  const keepDetails = [...(payload.goodwillFvDetails || [])]
  const keepNa = [...(payload.netAssetAdjustments || [])]
  hydrateFromData({
    ...payload,
    goodwillFvDetails: keepDetails,
    netAssetAdjustments: keepNa,
  })
  emitSave()
}

function handleAddGoodwillFvLine(): void {
  const name = investeeNameOptions.value[0] || ''
  const result = addGoodwillFvDetail(buildPayload(), {
    investeeName: name,
    kind: 'goodwill',
    description: '',
    amount: 0,
    indexRef: '',
  })
  if (result.payload) {
    applyPayloadToUi(result.payload)
    void persistPayloadNow(buildPayload())
  }
}

function handleRemoveGoodwillFvLine(id: string): void {
  const result = removeGoodwillFvDetail(buildPayload(), id)
  if (result.payload) {
    applyPayloadToUi(result.payload)
    void persistPayloadNow(buildPayload())
  }
}

function syncNetAssetAdjustmentsFromRows(): void {
  replaceNetAssetAdjustments(ensureNetAssetAdjustments(allRows.value, [...netAssetAdjustments]))
  emitSave()
}

function updateNaField(
  adj: NetAssetAdjustment,
  key: keyof NetAssetAdjustment,
  field: 'begin' | 'increase' | 'decrease',
  value: number,
): void {
  const item = (adj as any)[key]
  if (!item || typeof item !== 'object') return
  item[field] = value ?? 0
  onNetAssetChanged(adj)
}

function onNetAssetChanged(adj: NetAssetAdjustment): void {
  void adj
  emitSave()
}

function syncOneAuditedNetAssets(adj: NetAssetAdjustment): void {
  const targets = allRows.value.filter((r) => r.investeeName === adj.investeeName)
  for (const row of targets) {
    syncAuditedNetAssetsFromAdjustment(row, adj)
    recalcRow(row)
  }
  emitSave()
  ElMessage.success(`已回写「${adj.investeeName}」经审计净资产`)
}

function syncAllAuditedNetAssets(): void {
  syncNetAssetAdjustmentsFromRows()
  for (const adj of netAssetAdjustments) {
    const targets = allRows.value.filter((r) => r.investeeName === adj.investeeName)
    for (const row of targets) {
      syncAuditedNetAssetsFromAdjustment(row, adj)
      recalcRow(row)
    }
  }
  emitSave()
  ElMessage.success(`已回写 ${netAssetAdjustments.length} 家经审计净资产`)
}

async function handlePushToG73(): Promise<void> {
  if (isReadonly.value) return
  const lines = suggestedLines.value
  if (!lines.length) {
    ElMessage.info('当前无超过重要性（或非零）差异，无需推送')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将写入 ${lines.length} 行建议分录至 G7-3（替换此前同源【G7-14】分录），是否继续？`,
      '推送至 G7-3',
      { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  pushingG73.value = true
  try {
    const result = await pushSuggestedAdjustmentsToG73({
      projectId: props.projectId,
      currentWpId: props.wpId,
      lines,
    })
    if (result.ok) ElMessage.success(result.message)
    else ElMessage.warning(result.message)
  } catch {
    ElMessage.error('推送 G7-3 失败，请检查主表底稿是否已生成')
  } finally {
    pushingG73.value = false
  }
}

watch(
  () => groups.map((g) => g.investeeName).join('|'),
  () => {
    if (!groups.length) return
    replaceNetAssetAdjustments(ensureNetAssetAdjustments(allRows.value, [...netAssetAdjustments]))
  },
)

// ═══ 动态行增删 ═══════════════════════════════════════════════════════════════

function createEmptyRow(investeeName: string, seq: number): EquityMethodCalcRow {
  return {
    id: `emc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeName,
    investeeId: '',
    reportedNetProfit: 0,
    internalTransactionAdj: 0,
    fvDepreciationAdj: 0,
    accountingPolicyAdj: 0,
    otherAdj: 0,
    adjustedNetProfit: 0,
    investmentRatio: 0,
    equityShare: 0,
    confirmedIncome: 0,
    confirmedOci: 0,
    ociDifference: 0,
    confirmedOtherEquity: 0,
    otherEquityDifference: 0,
    incomeDifference: 0,
    ociChange: 0,
    ociShare: 0,
    otherEquityChange: 0,
    otherEquityShare: 0,
    dividendDistributed: 0,
    openingBalance: 0,
    closingBalance: 0,
    costOpening: 0,
    costChange: 0,
    costClosing: 0,
    pnlAdjOpening: 0,
    pnlAdjChange: 0,
    pnlAdjClosing: 0,
    ociBalOpening: 0,
    ociBalChange: 0,
    ociBalClosing: 0,
    otherEqBalOpening: 0,
    otherEqBalChange: 0,
    otherEqBalClosing: 0,
    auditedNetAssets: 0,
    shareOfAuditedNetAssets: 0,
    lteiBookBalance: 0,
    netAssetShareVariance: 0,
    goodwill: 0,
    cumulativeFvAdj: 0,
    impairment: 0,
    unexplainedVariance: 0,
    unexplainedNature: 'pending',
    varianceExplanation: '',
    auditConclusion: '无差异',
  }
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入被投资单位名称',
      '新增被投资单位',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      },
    )
    const name = value.trim()
    // 检查是否已有该分组
    const existing = groups.find(g => g.investeeName === name)
    if (existing) {
      // 组内添加行
      const newRow = createEmptyRow(name, existing.rows.length + 1)
      existing.rows.push(newRow)
    } else {
      // 新建分组
      const newRow = createEmptyRow(name, 1)
      groups.push({ investeeName: name, rows: [newRow] })
      expandedMap[name] = true
      saveCollapseState()
    }
    emitSave()
    syncNetAssetAdjustmentsFromRows()
    ElMessage.success(`已添加「${name}」`)
  } catch {
    // 用户取消
  }
}

function addRowToGroup(groupName: string): void {
  const group = groups.find(g => g.investeeName === groupName)
  if (!group) return
  const newRow = createEmptyRow(groupName, group.rows.length + 1)
  group.rows.push(newRow)
  emitSave()
}

function deleteRow(row: EquityMethodCalcRow): void {
  const group = groups.find(g => g.investeeName === row.investeeName)
  if (!group) return
  const idx = group.rows.findIndex(r => r.id === row.id)
  if (idx >= 0) {
    group.rows.splice(idx, 1)
    group.rows.forEach((r, i) => { r.seq = i + 1 })
    // 如果组为空则删除整个组
    if (group.rows.length === 0) {
      const gIdx = groups.findIndex(g => g.investeeName === row.investeeName)
      if (gIdx >= 0) groups.splice(gIdx, 1)
    }
    emitSave()
  }
}

// ═══ AI辅助 ═══════════════════════════════════════════════════════════════════

async function handleAiConclusion(): Promise<void> {
  ElMessage.info('正在生成AI审计结论...')
  try {
    const { default: http } = await import('@/utils/http')
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/equity-method-conclusion`,
      { rows: groups.flatMap(g => g.rows), materialityLevel: materialityLevel.value },
    )
    const text = res?.data?.conclusion || res?.data?.text || res?.data || ''
    if (text) {
      conclusion.value = String(text)
      emitSave()
      ElMessage.success('AI结论生成完成')
    }
  } catch {
    ElMessage.warning('AI结论生成暂未连接，请手动填写')
  }
}

// ═══ 导入导出 ═══════════════════════════════════════════════════════════════

async function handleDropdownCommand(command: string): Promise<void> {
  if (command === 'template') await importExport.exportTemplate('G7-14')
  else if (command === 'export') await importExport.exportData('G7-14')
  else if (command === 'import') fileInput.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || isReadonly.value) return
  // 导入前保留本地 Tab4 / 商誉明细 / 重要性 / 结论，后端也会尽量保留；此处防 UI 闪空
  const keepNa = [...netAssetAdjustments]
  const keepGwf = [...goodwillFvDetails]
  const keepMateriality = materialityLevel.value
  const keepConclusion = conclusion.value
  const result = await importExport.importData('G7-14', file)
  if (!result) return
  await formData.loadResponses()
  groups.length = 0
  Object.keys(expandedMap).forEach((k) => delete expandedMap[k])

  const pageRaw = formData.data.value.get(SECTION_KEY)?.conclusion
  let pageSaved: any = null
  if (typeof pageRaw === 'string') {
    try { pageSaved = JSON.parse(pageRaw) } catch { pageSaved = null }
  } else if (pageRaw && typeof pageRaw === 'object') {
    pageSaved = pageRaw
  }
  if (pageSaved && (pageSaved.groups?.length || pageSaved.rows?.length)) {
    if (!Array.isArray(pageSaved.netAssetAdjustments) || !pageSaved.netAssetAdjustments.length) {
      pageSaved.netAssetAdjustments = keepNa
    }
    if (!('goodwillFvDetails' in pageSaved) && !('goodwill_fv_details' in pageSaved)) {
      pageSaved.goodwillFvDetails = keepGwf
    } else if (Array.isArray(pageSaved.goodwill_fv_details) && !pageSaved.goodwillFvDetails) {
      pageSaved.goodwillFvDetails = pageSaved.goodwill_fv_details
    }
    if (pageSaved.materialityLevel == null) pageSaved.materialityLevel = keepMateriality
    if (pageSaved.conclusion == null || pageSaved.conclusion === '') pageSaved.conclusion = keepConclusion
    hydrateFromData(pageSaved)
    return
  }
  const rowsRaw = formData.data.value.get(ROWS_KEY)?.conclusion
  let rowsSaved: any = null
  if (typeof rowsRaw === 'string') {
    try { rowsSaved = JSON.parse(rowsRaw) } catch { rowsSaved = null }
  } else {
    rowsSaved = rowsRaw
  }
  if (Array.isArray(rowsSaved) && rowsSaved.length) {
    hydrateFromData({
      rows: rowsSaved,
      materialityLevel: keepMateriality,
      conclusion: keepConclusion,
      netAssetAdjustments: keepNa,
      goodwillFvDetails: keepGwf,
    })
  }
}

// ═══ 保存 ═══════════════════════════════════════════════════════════════════

function buildPayload(): EquityMethodCalcSavePayload {
  return {
    rows: groups.flatMap(g => g.rows),
    materialityLevel: materialityLevel.value,
    conclusion: conclusion.value,
    groups: groups.map(g => ({ investeeName: g.investeeName, rows: g.rows })),
    netAssetAdjustments: [...netAssetAdjustments],
    goodwillFvDetails: goodwillFvDetails.map((d) => ({ ...d })),
    lastCrossSheetSync: lastCrossSheetSync.value,
  }
}

function emitSave(): void {
  if (isReadonly.value) return
  const payload = buildPayload()
  const pageJson = JSON.stringify(payload)
  const rowsJson = JSON.stringify(payload.rows)
  formData.debouncedSaveBatch([
    { itemId: SECTION_KEY, data: { conclusion: pageJson, remark: null } },
    { itemId: ROWS_KEY, data: { conclusion: rowsJson, remark: rowsJson } },
  ])
}

// ═══ 辅助格式化 ═══════════════════════════════════════════════════════════════

function fmtPercent(v: unknown): string {
  if (typeof v === 'number') return `${(v * 100).toFixed(2)}%`
  return String(v ?? '')
}

function conclusionTagType(c: string): '' | 'success' | 'warning' | 'danger' {
  switch (c) {
    case '无差异': return 'success'
    case '差异可接受': return 'warning'
    case '差异需调整': return 'danger'
    default: return ''
  }
}

// ═══ 数据水合 ═══════════════════════════════════════════════════════════════

function hydrateData(): void {
  hydrateFromData(props.htmlData)
}

// ═══ 对外暴露 ═══════════════════════════════════════════════════════════════

function getData(): EquityMethodCalcSavePayload {
  return buildPayload()
}

function loadFromHtmlData(data: Record<string, any> | null): void {
  groups.length = 0
  Object.keys(expandedMap).forEach(k => delete expandedMap[k])
  replaceNetAssetAdjustments([])
  replaceGoodwillFvDetails([])
  lastCrossSheetSync.value = null
  if (data) {
    hydrateFromData(data)
  }
}

/**
 * 通用水合：支持从任意数据源恢复（props.htmlData 或外部传入）
 */
function hydrateFromData(data: Record<string, any> | null): void {
  const calcData = data?.equityMethodCalc ?? data?.equity_method_calc ?? data

  materialityLevel.value = parseNum(calcData?.materialityLevel ?? calcData?.materiality_level ?? 0)
  conclusion.value = calcData?.conclusion ?? ''

  const rawGroups = calcData?.groups ?? []
  if (Array.isArray(rawGroups) && rawGroups.length > 0) {
    for (const g of rawGroups) {
      const name = g.investeeName ?? g.investee_name ?? '未命名'
      const rows: EquityMethodCalcRow[] = (g.rows ?? []).map((r: any, idx: number) => {
        const row = hydrateRow(r, name, idx)
        recalcRow(row)
        return row
      })
      groups.push({ investeeName: name, rows })
      if (expandedMap[name] === undefined) expandedMap[name] = true
    }
  } else {
    const rawRows = calcData?.rows ?? []
    if (Array.isArray(rawRows) && rawRows.length > 0) {
      const groupMap = new Map<string, EquityMethodCalcRow[]>()
      for (const r of rawRows) {
        const name = r.investeeName ?? r.investee_name ?? '未分组'
        if (!groupMap.has(name)) groupMap.set(name, [])
        const row = hydrateRow(r, name, groupMap.get(name)!.length)
        recalcRow(row)
        groupMap.get(name)!.push(row)
      }
      for (const [name, rows] of groupMap.entries()) {
        groups.push({ investeeName: name, rows })
        if (expandedMap[name] === undefined) expandedMap[name] = true
      }
    }
  }

  const rawNa = calcData?.netAssetAdjustments ?? calcData?.net_asset_adjustments ?? []
  if (Array.isArray(rawNa) && rawNa.length > 0) {
    replaceNetAssetAdjustments(rawNa.map((item: any) => hydrateNetAssetAdjustment(item)))
  }
  replaceNetAssetAdjustments(ensureNetAssetAdjustments(allRows.value, [...netAssetAdjustments]))

  const rawGwf = calcData?.goodwillFvDetails ?? calcData?.goodwill_fv_details ?? []
  if (Array.isArray(rawGwf) && rawGwf.length > 0) {
    replaceGoodwillFvDetails(rawGwf as GoodwillFvDetailLine[])
  }

  const syncMeta = calcData?.lastCrossSheetSync ?? calcData?.last_cross_sheet_sync
  if (syncMeta && typeof syncMeta === 'object') {
    lastCrossSheetSync.value = {
      at: String(syncMeta.at || ''),
      sources: Array.isArray(syncMeta.sources) ? syncMeta.sources.map(String) : [],
      changeCount: parseNum(syncMeta.changeCount ?? syncMeta.change_count),
    }
  }
}

function hydrateRow(r: any, name: string, idx: number): EquityMethodCalcRow {
  return {
    id: r.id ?? `emc-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
    seq: r.seq ?? idx + 1,
    investeeName: name,
    investeeId: String(r.investeeId ?? r.investee_id ?? ''),
    reportedNetProfit: parseNum(r.reportedNetProfit ?? r.reported_net_profit),
    internalTransactionAdj: parseNum(r.internalTransactionAdj ?? r.internal_transaction_adj),
    fvDepreciationAdj: parseNum(r.fvDepreciationAdj ?? r.fv_depreciation_adj),
    accountingPolicyAdj: parseNum(r.accountingPolicyAdj ?? r.accounting_policy_adj),
    otherAdj: parseNum(r.otherAdj ?? r.other_adj),
    adjustedNetProfit: 0,
    investmentRatio: normalizeOwnershipRatio(r.investmentRatio ?? r.investment_ratio),
    equityShare: 0,
    confirmedIncome: parseNum(r.confirmedIncome ?? r.confirmed_income),
    confirmedOci: parseNum(r.confirmedOci ?? r.confirmed_oci),
    ociDifference: 0,
    confirmedOtherEquity: parseNum(r.confirmedOtherEquity ?? r.confirmed_other_equity),
    otherEquityDifference: 0,
    incomeDifference: 0,
    ociChange: parseNum(r.ociChange ?? r.oci_change),
    ociShare: 0,
    otherEquityChange: parseNum(r.otherEquityChange ?? r.other_equity_change),
    otherEquityShare: 0,
    dividendDistributed: parseNum(r.dividendDistributed ?? r.dividend_distributed),
    openingBalance: parseNum(r.openingBalance ?? r.opening_balance),
    closingBalance: 0,
    costOpening: parseNum(r.costOpening ?? r.cost_opening),
    costChange: parseNum(r.costChange ?? r.cost_change),
    costClosing: 0,
    pnlAdjOpening: parseNum(r.pnlAdjOpening ?? r.pnl_adj_opening),
    pnlAdjChange: parseNum(r.pnlAdjChange ?? r.pnl_adj_change),
    pnlAdjClosing: 0,
    ociBalOpening: parseNum(r.ociBalOpening ?? r.oci_bal_opening),
    ociBalChange: 0,
    ociBalClosing: 0,
    otherEqBalOpening: parseNum(r.otherEqBalOpening ?? r.other_eq_bal_opening),
    otherEqBalChange: 0,
    otherEqBalClosing: 0,
    auditedNetAssets: parseNum(r.auditedNetAssets ?? r.audited_net_assets),
    shareOfAuditedNetAssets: 0,
    lteiBookBalance: 0,
    netAssetShareVariance: 0,
    goodwill: parseNum(r.goodwill),
    cumulativeFvAdj: parseNum(r.cumulativeFvAdj ?? r.cumulative_fv_adj),
    impairment: parseNum(r.impairment),
    unexplainedVariance: 0,
    unexplainedNature: (r.unexplainedNature ?? r.unexplained_nature ?? 'pending') as UnexplainedNature,
    varianceExplanation: String(r.varianceExplanation ?? r.variance_explanation ?? ''),
    auditConclusion: r.auditConclusion ?? r.audit_conclusion ?? '无差异',
  }
}

defineExpose({ getData, loadFromHtmlData })

// ═══ 生命周期 ═══════════════════════════════════════════════════════════════

onMounted(async () => {
  loadCollapseState()
  await formData.load()

  const savedRaw = formData.data.value.get(SECTION_KEY)?.conclusion
  let saved: any = null
  if (typeof savedRaw === 'string') {
    try { saved = JSON.parse(savedRaw) } catch { saved = null }
  } else if (savedRaw && typeof savedRaw === 'object') {
    saved = savedRaw
  }

  if (saved && (saved.groups?.length || saved.rows?.length)) {
    hydrateFromData(saved)
  } else {
    const rowsRaw = formData.data.value.get(ROWS_KEY)?.conclusion
    let rowsSaved: any = null
    if (typeof rowsRaw === 'string') {
      try { rowsSaved = JSON.parse(rowsRaw) } catch { rowsSaved = null }
    } else {
      rowsSaved = rowsRaw
    }
    if (Array.isArray(rowsSaved) && rowsSaved.length) {
      hydrateFromData({ rows: rowsSaved })
    } else {
      hydrateData()
    }
  }

  auditNote.value = formData.data.value.get(AUDIT_NOTE_KEY)?.remark ?? ''
})
</script>

<style scoped>
.g7-tab-equity-method-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* Section 标题栏 */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 蓝色渐变引导区 */
.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
  padding: 14px 18px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, #ecf5ff 0%, #e6f7ff 100%);
  border: 1px solid #b3d8ff;
  border-radius: 6px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-num {
  font-size: 16px;
  font-weight: 700;
  color: #409eff;
  flex-shrink: 0;
}
.step-text {
  font-size: 12px;
  color: #303133;
  line-height: 1.5;
}

/* 方法论上下文区域 */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.methodology-context p {
  margin: 2px 0;
}

/* 重要性水平栏 */
.materiality-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.materiality-label {
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
}
.materiality-value {
  font-weight: 600;
  color: #409eff;
}
.materiality-hint {
  font-size: 11px;
  color: #909399;
}

/* 区段Tab */
.segment-bar {
  margin-bottom: 12px;
}

/* 虚拟滚动容器（54行阈值） */
.equity-scroll-container {
  max-height: calc(54 * 34px + 120px);
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 4px;
}

/* 分组标题 */
.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
  margin-top: 8px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}
.group-header:first-child {
  margin-top: 0;
}
.group-header:hover {
  background: #d9ecff;
}
.group-name {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.group-count {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}
.group-actions {
  margin-left: auto;
}
.collapse-icon {
  transition: transform 0.2s;
  font-size: 14px;
}
.collapse-icon.is-collapsed {
  transform: rotate(-90deg);
}

/* 分组内容 */
.group-body {
  margin-bottom: 4px;
}

/* 表格 */
.equity-calc-table {
  margin-top: 4px;
  font-size: var(--wp-font-size, 13px);
}

/* 公式列样式（虚线下划线+cursor:help） */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* 收益差异超过重要性水平 → 红色高亮 */
.income-diff-warning {
  color: #f56c6c;
  font-weight: 700;
  border-bottom-color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}
.conclusion-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.conclusion-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #909399;
}
.empty-state p {
  margin-bottom: 12px;
}

/* 编制提示 */
.guidance-details {
  margin-top: 16px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}
.guidance-content p {
  margin: 4px 0;
}
.hint-line {
  font-size: 11px;
  color: #909399;
  line-height: 1.2;
  margin-top: 2px;
}
.aje-hint {
  margin-top: 6px;
  color: #606266;
}

.gwf-detail-card {
  margin-top: 12px;
}
.gwf-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #909399;
}
.gwf-sync-meta {
  margin-left: 8px;
  color: #67c23a;
}
.gwf-na {
  color: #c0c4cc;
}

/* Tab4 净资产调整 */
.na-adjust-panel {
  margin-bottom: 16px;
}
.na-card {
  margin-bottom: 12px;
}
.na-card-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.na-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: #606266;
}
.na-summary {
  color: #409eff;
  font-weight: 500;
}
.na-card-actions {
  margin-top: 8px;
}
.aje-preview-card {
  margin-top: 12px;
}
.tab-toolbar .toolbar-left {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
