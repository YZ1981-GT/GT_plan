<template>
  <div class="g6-tab-interest-calculation">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证其他债权投资按实际利率法确认利息收入的准确性，核实实际利率确定的合理性与摊余成本逐期结转的正确性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :loading="syncing"
          @click="syncFromMain"
        >
          从 G6-1/G6-2 更新
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :loading="writingBack"
          :disabled="!interest.groups.value.length"
          @click="writebackToG62"
        >
          回写利息调整至 G6-2
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          :loading="syncingEcl"
          :disabled="!interest.groups.value.length"
          @click="syncEclStage"
        >
          从 G6-12 同步阶段
        </el-button>
        <el-button
          size="small"
          plain
          :loading="comparingEnding"
          :disabled="!interest.groups.value.length"
          @click="compareEndingToG62"
        >
          核对期末摊余 vs G6-2
        </el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ interest.groups.value.length }} 个投资项目</el-tag>
      </div>
    </div>

    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>实际利率法确认利息收入：</strong></p>
      <p>利息收入 = 摊余成本 × 实际利率 × 计息天数 / 年天数（计息基准 ACT/365、ACT/360 或 30/360）</p>
      <p>现金流入（票息）= 剩余面值 × 票面利率 × 计息天数 / 年天数（剩余面值 = 面值 − 此前收回本金）</p>
      <p>期末摊余成本 = 期初摊余成本 + 实际利息收入 - 现金流入（票息） - 收回本金</p>
      <p style="color: #92400e; font-size: 11px; margin-top: 4px;">
        依据CAS22《金融工具确认和计量》，其他债权投资按实际利率法确认利息收入并调整摊余成本。填写起息日/截止日后可自动推算 ACT/365 天数。
      </p>
    </div>

    <!-- 利率合理性告警 -->
    <el-alert
      v-if="interest.hasRateWarnings.value"
      type="warning"
      :closable="false"
      class="warn-alert"
    >
      <template #title>利率合理性提示（{{ interest.rateWarnings.value.length }}项）</template>
      <ul class="warn-list">
        <li v-for="(w, i) in interest.rateWarnings.value" :key="`${w.groupId}-${i}`">{{ w.message }}</li>
      </ul>
    </el-alert>
    <el-alert
      v-if="interest.hasDayWarnings.value"
      type="warning"
      :closable="false"
      class="warn-alert"
    >
      <template #title>计息期间提示（{{ interest.dayWarnings.value.length }}项）</template>
      <ul class="warn-list">
        <li v-for="(w, i) in interest.dayWarnings.value" :key="`${w.periodId}-${i}`">{{ w.message }}</li>
      </ul>
    </el-alert>
    <el-alert
      v-if="interest.hasPrincipalWarnings.value"
      type="warning"
      :closable="false"
      class="warn-alert"
    >
      <template #title>收回本金/摊余提示（{{ interest.principalWarnings.value.length }}项）</template>
      <ul class="warn-list">
        <li v-for="(w, i) in interest.principalWarnings.value" :key="`${w.groupId}-${w.periodId || i}`">{{ w.message }}</li>
      </ul>
    </el-alert>

    <!-- ═══ 投资项目分组卡片 ═══ -->
    <template v-if="interest.groups.value.length > 0">
      <el-card
        v-for="group in interest.groups.value"
        :key="group.id"
        shadow="never"
        class="group-card"
      >
        <!-- 分组header -->
        <template #header>
          <div class="group-header">
            <div class="group-info">
              <span class="group-name">{{ group.investProject }}</span>
              <div class="group-params">
                <span class="param-item">
                  面值：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.faceValue"
                    size="small" :controls="false" :precision="2"
                    style="width: 120px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'faceValue', v ?? 0)"
                  />
                  <span v-else>{{ fmtNum(group.faceValue) }}</span>
                </span>
                <span class="param-item">
                  票面利率：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.couponRate * 100"
                    size="small" :controls="false" :precision="4"
                    style="width: 90px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'couponRate', (v ?? 0) / 100)"
                  />
                  <span v-else>{{ (group.couponRate * 100).toFixed(4) }}</span>%
                </span>
                <span class="param-item">
                  实际利率：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.effectiveRate * 100"
                    size="small" :controls="false" :precision="4"
                    style="width: 90px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'effectiveRate', (v ?? 0) / 100)"
                  />
                  <span v-else>{{ (group.effectiveRate * 100).toFixed(4) }}</span>%
                </span>
                <span class="param-item">
                  计息基准：
                  <el-select
                    v-if="!isReadonly"
                    :model-value="group.dayCountBasis || 'ACT/365'"
                    size="small"
                    style="width: 110px"
                    @update:model-value="(v: string) => interest.updateGroupHeader(group.id, 'dayCountBasis', v)"
                  >
                    <el-option label="ACT/365" value="ACT/365" />
                    <el-option label="ACT/360" value="ACT/360" />
                    <el-option label="30/360" value="30/360" />
                  </el-select>
                  <span v-else>{{ group.dayCountBasis || 'ACT/365' }}</span>
                </span>
              </div>
              <div class="group-params initial-params">
                <span class="param-item">
                  购买对价：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.purchasePrice"
                    size="small" :controls="false" :precision="2"
                    style="width: 110px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'purchasePrice', v ?? 0)"
                  />
                  <span v-else>{{ fmtNum(group.purchasePrice) }}</span>
                </span>
                <span class="param-item">
                  交易费用：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.transactionCost"
                    size="small" :controls="false" :precision="2"
                    style="width: 110px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'transactionCost', v ?? 0)"
                  />
                  <span v-else>{{ fmtNum(group.transactionCost) }}</span>
                </span>
                <span class="param-item">
                  初始入账：
                  <span class="formula-cell" title="购买对价 + 交易费用">{{ fmtNum(group.initialCarryingAmount) }}</span>
                </span>
                <span class="param-item">
                  初始确认日：
                  <el-date-picker
                    v-if="!isReadonly"
                    :model-value="group.initialDate"
                    type="date" size="small"
                    format="YYYY-MM-DD" value-format="YYYY-MM-DD"
                    style="width: 130px"
                    @update:model-value="(v: string) => interest.updateGroupHeader(group.id, 'initialDate', v || '')"
                  />
                  <span v-else>{{ group.initialDate || '-' }}</span>
                </span>
              </div>
            </div>
            <div class="group-actions">
              <span class="chip-wrap">
                <GtIndexChip
                  :value="group.crossSheetInvestmentId ? `wp:G6-2#${group.crossSheetInvestmentId}` : 'wp:G6-2'"
                  :context-project-id="projectId"
                />
              </span>
              <el-tag size="small" type="info">
                利息小计：{{ fmtNum(interest.getGroupInterestTotal(group.id)) }}
              </el-tag>
              <el-button
                v-if="!isReadonly"
                size="small" type="danger" link
                @click="interest.removeGroup(group.id)"
              >🗑️ 删除项目</el-button>
            </div>
          </div>
        </template>

        <!-- 多期表格 -->
        <el-table :data="group.periods" border size="small" class="period-table">
          <el-table-column label="起息日" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                :model-value="row.periodStart"
                type="date"
                size="small"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="起息日"
                style="width: 110px"
                @update:model-value="(v: string) => interest.updatePeriod(group.id, row.id, 'periodStart', v || '')"
              />
              <span v-else>{{ row.periodStart || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="截止日" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                :model-value="row.periodEnd"
                type="date"
                size="small"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                style="width: 110px"
                @update:model-value="(v: string) => interest.updatePeriod(group.id, row.id, 'periodEnd', v || '')"
              />
              <span v-else>{{ row.periodEnd || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初摊余成本" width="130" align="right">
            <template #default="{ row, $index }">
              <WpAmountInput
                v-if="!isReadonly && $index === 0"
                :model-value="row.openingAmortized"
                size="small"
                style="width: 110px"
                @update:model-value="(v: number | undefined) => interest.updatePeriod(group.id, row.id, 'openingAmortized', v ?? 0)"
              />
              <span v-else class="formula-cell" title="期初摊余 = 上期期末摊余">
                {{ fmtNum(row.openingAmortized) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.stage"
                size="small"
                style="width: 88px"
                @update:model-value="(v: string) => interest.updatePeriod(group.id, row.id, 'stage', v)"
              >
                <el-option label="S1" value="Stage1" />
                <el-option label="S2" value="Stage2" />
                <el-option label="S3" value="Stage3" />
              </el-select>
              <span v-else>{{ row.stage === 'Stage3' ? 'S3' : row.stage === 'Stage2' ? 'S2' : 'S1' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初减值" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.openingImpairment"
                size="small"
                style="width: 95px"
                :disabled="row.stage !== 'Stage3'"
                @update:model-value="(v: number | undefined) => interest.updatePeriod(group.id, row.id, 'openingImpairment', v ?? 0)"
              />
              <span v-else>{{ fmtNum(row.openingImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="实际利息收入" width="130" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="实际利息 = 期初摊余 × 实际利率 × 天数/365">{{ fmtNum(row.effectiveInterest) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="现金流入" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="现金流入 = 面值 × 票面利率 × 天数/365">{{ fmtNum(row.cashInflow) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="收回本金" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.principalRecovered"
                size="small" :controls="false" :precision="2"
                style="width: 95px"
                @update:model-value="(v: number | undefined) => interest.updatePeriod(group.id, row.id, 'principalRecovered', v ?? 0)"
              />
              <span v-else>{{ fmtNum(row.principalRecovered) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末摊余成本" width="130" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末摊余 = 期初 + 实际利息 - 现金流入 - 收回本金">{{ fmtNum(row.endingAmortized) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="天数" width="90" align="center">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.days"
                size="small" :controls="false" :min="1" :max="366"
                style="width: 70px"
                @update:model-value="(v: number | undefined) => interest.updatePeriod(group.id, row.id, 'days', v ?? 180)"
              />
              <span v-else>{{ row.days }}</span>
              <div v-if="row.daysManualOverride" class="days-hint">手工</div>
            </template>
          </el-table-column>
          <el-table-column label="索引" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.indexRef"
                size="small" placeholder="证据"
                @update:model-value="(v: string) => interest.updatePeriod(group.id, row.id, 'indexRef', v)"
              />
              <span v-else-if="!row.indexRef">-</span>
              <div v-if="row.indexRef" class="row-index-chip">
                <GtIndexChip :value="row.indexRef" :context-project-id="projectId" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="90">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.remark"
                size="small" placeholder="备注..."
                @update:model-value="(v: string) => interest.updatePeriod(group.id, row.id, 'remark', v)"
              />
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button
                size="small" type="danger" link
                @click="interest.removePeriod(group.id, row.id)"
              >🗑️</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 组内新增期间 -->
        <div v-if="!isReadonly" class="add-period-bar">
          <el-button size="small" @click="interest.addPeriod(group.id)">
            + 新增期间
          </el-button>
        </div>
      </el-card>
    </template>

    <el-empty v-else description="暂无投资项目，请点击“新增投资项目”添加" :image-size="60" />

    <!-- 底部操作区 -->
    <div class="bottom-actions">
      <el-button v-if="!isReadonly" type="primary" size="small" @click="interest.addGroup()">
        + 新增投资项目
      </el-button>
      <G6SppiImportExportDropdown
        v-if="wpId"
        :wp-id="wpId"
        sheet="G6-6"
        :disabled="isReadonly"
        @imported="onImported"
      />
    </div>

    <!-- ═══ 底部交叉验证（三层勾稽） ═══ -->
    <el-card shadow="never" class="cross-validation-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">交叉验证</span>
        </div>
      </template>
      <div class="cv-grid">
        <div class="cv-item">
          <span class="cv-label">本表实际利息合计</span>
          <span class="cv-value">{{ fmtNum(interest.totalInterest.value) }}</span>
        </div>
        <div class="cv-item">
          <span class="cv-label">本表票息/现金流入</span>
          <span class="cv-value">{{ fmtNum(interest.totalCashInflow.value) }}</span>
        </div>
        <div class="cv-item">
          <span class="cv-label">利息调整摊销额</span>
          <span class="cv-value">{{ fmtNum(interest.totalAmortization.value) }}</span>
          <span class="cv-hint">实际利息 − 票息</span>
        </div>
        <div class="cv-item">
          <span class="cv-label">账面利息收入（损益）</span>
          <el-input-number
            v-if="!isReadonly"
            :model-value="interest.bookInterestIncome.value"
            size="small" :controls="false" :precision="2"
            style="width: 140px"
            @change="(v: number | undefined) => { interest.setBookInterestIncome(v ?? 0); handleSave() }"
          />
          <span v-else class="cv-value">{{ fmtNum(interest.bookInterestIncome.value) }}</span>
        </div>
        <div class="cv-item">
          <span class="cv-label">损益差异</span>
          <span
            class="cv-value"
            :class="{
              'cv-pass': interest.incomePassed.value,
              'cv-fail': interest.incomeLayerActive.value && !interest.incomePassed.value,
            }"
          >
            {{ interest.incomeLayerActive.value ? fmtNum(interest.incomeDiff.value) : '未填基准' }}
            <el-icon v-if="interest.incomeLayerActive.value && interest.incomePassed.value" style="color: #10b981; margin-left: 4px;">✓</el-icon>
            <el-icon v-else-if="interest.incomeLayerActive.value" style="color: #ef4444; margin-left: 4px;">✗</el-icon>
          </span>
        </div>
        <div class="cv-item">
          <span class="cv-label">G6-1利息调整本期变动</span>
          <el-input-number
            v-if="!isReadonly"
            v-model="interest.interestAdjPeriodChange.value"
            size="small" :controls="false" :precision="2"
            style="width: 140px"
            @change="handleSave"
          />
          <span v-else class="cv-value">{{ fmtNum(interest.interestAdjPeriodChange.value) }}</span>
          <span class="cv-hint">摊销口径</span>
        </div>
        <div class="cv-item">
          <span class="cv-label">摊销差异</span>
          <span
            class="cv-value"
            :class="{
              'cv-pass': interest.amortizationPassed.value,
              'cv-fail': !interest.amortizationPassed.value,
            }"
          >
            {{ fmtNum(interest.amortizationDiff.value) }}
            <el-icon v-if="interest.amortizationPassed.value" style="color: #10b981; margin-left: 4px;">✓</el-icon>
            <el-icon v-else style="color: #ef4444; margin-left: 4px;">✗</el-icon>
          </span>
        </div>
        <div class="cv-item">
          <span class="cv-label">实际执行重要性(B15)</span>
          <span class="cv-value">{{ interest.performanceMateriality.value > 0 ? fmtNum(interest.performanceMateriality.value) : '未取到' }}</span>
        </div>
      </div>
      <el-alert
        v-if="interest.materialVariance.value"
        type="error"
        :closable="false"
        show-icon
        title="差异超过实际执行重要性（B15），请追查原因并考虑调整分录"
        style="margin-top: 10px"
      />
      <div
        v-if="!isReadonly && (interest.materialVariance.value || interest.needsVarianceReason.value)"
        style="margin-top: 10px"
      >
        <el-button
          size="small"
          type="danger"
          plain
          :loading="pushingAdj"
          @click="pushVarianceToG64"
        >
          差异 → G6-4 调整草稿
        </el-button>
        <span class="cv-hint" style="margin-left: 8px;">按勾稽差异生成借贷草稿（150302↔6111），须人工确认后写入</span>
      </div>
      <el-alert
        v-else-if="interest.needsVarianceReason.value"
        type="warning"
        :closable="false"
        show-icon
        title="差异超过舍入阈值（0.01），请填写差异说明"
        style="margin-top: 10px"
      />
      <div v-if="interest.needsVarianceReason.value || interest.varianceReason.value" class="variance-reason" style="margin-top: 10px">
        <span class="cv-label">差异说明</span>
        <el-input
          v-model="interest.varianceReason.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          :class="{ 'is-missing': interest.varianceReasonMissing.value }"
          placeholder="说明勾稽差异原因、拟调整/不调整依据…"
          @input="handleSave"
        />
      </div>
      <p class="cv-hint" style="margin-top: 8px;">
        第三层：点「核对期末摊余 vs G6-2」将各项目末期期末摊余与 G6-2「成本+利息调整」勾稽。Stage3 按「摊余−减值」净额计息；票息按剩余面值计算。
      </p>
      <div v-if="interest.endingAmortizedCompare.value.length" class="ending-compare" style="margin-top: 12px">
        <div class="cv-item" style="margin-bottom: 8px">
          <span class="cv-label">第三层差异合计</span>
          <span
            class="cv-value"
            :class="{
              'cv-pass': interest.endingComparePassed.value,
              'cv-fail': !interest.endingComparePassed.value,
            }"
          >
            {{ fmtNum(interest.endingCompareDiffTotal.value) }}
            <el-icon v-if="interest.endingComparePassed.value" style="color: #10b981; margin-left: 4px;">✓</el-icon>
            <el-icon v-else style="color: #ef4444; margin-left: 4px;">✗</el-icon>
          </span>
        </div>
        <el-table :data="interest.endingAmortizedCompare.value" size="small" border>
          <el-table-column prop="investProject" label="投资项目" min-width="140" />
          <el-table-column label="G6-6期末摊余" width="130" align="right">
            <template #default="{ row }">{{ fmtNum(row.g66Ending) }}</template>
          </el-table-column>
          <el-table-column label="G6-2期末摊余" width="130" align="right">
            <template #default="{ row }">{{ row.g62Ending == null ? '未匹配' : fmtNum(row.g62Ending) }}</template>
          </el-table-column>
          <el-table-column label="差异" width="110" align="right">
            <template #default="{ row }">
              <span :class="row.matched ? 'cv-pass' : 'cv-fail'">
                {{ row.diff == null ? '—' : fmtNum(row.diff) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计说明</span>
          <div class="section-actions">
            <el-button
              size="small"
              :disabled="isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAiNote"
            >🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述实际利率法测算的测试情况及结果、与审定表（G6-1）利息调整/利息收入的交叉验证、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button
              size="small"
              :disabled="isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi"
            >🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-6-interest')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="interest.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="对利息测算结果的审计结论：利息收入计算方法是否恰当、实际利率确定是否合理..."
        @input="handleSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 实际利率在初始确认时确定，后续不因市场利率变动而调整</p>
        <p>2. 验证实际利率与票面利率的差异：溢价/折价购入时实际利率≠票面利率</p>
        <p>3. 每期利息收入 = 期初摊余成本 × 实际利率 × 计息天数/年天数（计息基准 ACT/365、ACT/360 或 30/360）</p>
        <p>4. 现金流入（票息）= 剩余面值 × 票面利率 × 计息天数/年天数（剩余面值 = 面值 − 此前收回本金）</p>
        <p>5. 期末摊余成本 = 期初 + 实际利息 - 现金流入 - 收回本金</p>
        <p>6. 三层勾稽：损益（实际利息↔账面利息）／摊销（实际利息−票息↔G6-1利息调整变动）／项目期末摊余↔G6-2</p>
        <p>7. 优先用「从 G6-1/G6-2 更新」带入项目、面值、利率与期初摊余成本（成本+利息调整，不含应计利息）</p>
        <p>8. 测算完成后可用「回写利息调整至 G6-2」将 Σ(实际利息−票息) 写入本期利息调整变动</p>
        <p>9. 填写起息日与截止日可自动推算天数；手工改天数后标记为「手工」不再被覆盖</p>
        <p>10. 关注实际利率与票面利率差异超过 200bp 的合理性提示</p>
        <p>11. 「从 G6-12 同步阶段」仅更新末期阶段/减值；Stage3 按净额计息</p>
        <p>12. 「核对期末摊余 vs G6-2」自动比对第三层（G6-6 末期摊余 ↔ G6-2 成本+利息调整）</p>
        <p>13. 超差可用「差异 → G6-4 调整草稿」生成 150302↔6111 借贷草稿，须人工确认后写入 Main</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G6TabInterestCalculation.vue — G6-6 利息测算表（实际利率法分组结构）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 5.2
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
 *
 * 功能：
 * - 方法论上下文(琥珀色): "实际利率法确认利息收入=摊余成本×实际利率×计息天数/365"
 * - 投资项目分组（每项目一个分组card: 面值|票面利率|实际利率）
 * - 每组内多期表格：截止日|期初摊余|实际利息(公式)|现金流入(公式)|期末摊余(公式)|天数
 * - 动态: +新增投资项目(ElMessageBox.prompt) / +新增期间
 * - 底部交叉验证: 利息合计 vs G6-1审定表利息调整
 * - 审计结论textarea + AI按钮 + 编制提示折叠
 */
import { computed, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useG6SppiInterest } from '../../composables/useG6SppiInterest'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import {
  applyG66InterestToDetailRows,
  buildG66InterestVarianceAdjustmentDrafts,
  compareG66EndingToG62,
  fetchG61InterestAdjPeriodChange,
  fetchG62DetailRows,
  fetchG612ImpairmentRows,
  fetchG64AdjustmentEntries,
  fetchPerformanceMateriality,
  mapG612RowsToInterestStageSeeds,
  mapG62RowsToInterestSeeds,
  mergeG64EntriesWithG66Drafts,
  parseG6ChecklistPayload,
  saveG62DetailRows,
  saveG64AdjustmentEntries,
} from '../../composables/g6CrossHelpers'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import GtIndexChip from '../../GtIndexChip.vue'
import G6SppiImportExportDropdown from '../G6SppiImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

// ─── 复核对话 inject ───
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

// ─── 数据层 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const interest = useG6SppiInterest()
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(wpIdRef)
const syncing = ref(false)
const writingBack = ref(false)
const syncingEcl = ref(false)
const comparingEnding = ref(false)
const pushingAdj = ref(false)

const DATA_KEY = 'G6-6-interest-data'
const ROWS_KEY = 'G6-6-rows'
const NOTE_KEY = 'G6-6-interest-calc-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function initFromData(): void {
  // 1) UI 主键：嵌套 G6-6-interest-data
  const primary = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
  if (primary && (Array.isArray(primary.groups) || primary.crossValidation || primary.conclusion)) {
    interest.loadData(primary)
    return
  }
  // 2) IE 兼容：扁平 G6-6-rows
  const flat = parseG6ChecklistPayload(formData.allResponses.value.get(ROWS_KEY))
  if (Array.isArray(flat) && flat.length) {
    interest.loadData(flat)
    return
  }
  if (flat?.groups) {
    interest.loadData(flat)
    return
  }
  // 3) render-config / sheetCache 兜底
  const content = formData.parseContent()
  if (content.interest) {
    interest.loadData(content.interest as any)
  }
}

// ─── 数据加载 ───
onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const pm = await fetchPerformanceMateriality(props.projectId)
  if (pm != null) {
    interest.setPerformanceMateriality(pm)
    handleSave()
  }
})

watch(() => props.htmlData, (newData) => {
  // 仅本地尚无编制数据时用 htmlData 初始化，避免覆盖未保存编辑
  if (newData && interest.groups.value.length === 0) {
    initFromData()
  }
})

// ─── 保存：嵌套主键 + 扁平兼容双写（同批防抖） ───
function handleSave(): void {
  if (props.isReadonly) return
  const nested = interest.toJSON()
  formData.debouncedSaveBatch([
    { itemId: DATA_KEY, data: { conclusion: JSON.stringify(nested) } },
    { itemId: ROWS_KEY, data: { conclusion: JSON.stringify(interest.flattenGroups()) } },
  ])
}

function flushPersist(): void {
  handleSave()
  formData.flushPending()
}

onBeforeUnmount(() => {
  flushPersist()
})

async function onImported(): Promise<void> {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  emit('imported')
}

async function syncFromMain(): Promise<void> {
  if (props.isReadonly) return
  syncing.value = true
  try {
    const [detailRows, interestAdjChange] = await Promise.all([
      fetchG62DetailRows(props.projectId),
      fetchG61InterestAdjPeriodChange(props.projectId),
    ])
    const seeds = mapG62RowsToInterestSeeds(detailRows)
    const { added, updated } = interest.mergeSeedsFromDetail(seeds)
    if (interestAdjChange != null) {
      interest.interestAdjPeriodChange.value = interestAdjChange
    }
    handleSave()
    if (!seeds.length && interestAdjChange == null) {
      ElMessage.warning('未找到 G6-1/G6-2 数据，请确认 Main 底稿已编制')
    } else {
      ElMessage.success(
        `已同步：新增 ${added} 项，更新 ${updated} 项` +
          (interestAdjChange != null ? `；G6-1利息调整本期变动 ${interestAdjChange}` : ''),
      )
    }
  } catch {
    ElMessage.warning('同步 G6-1/G6-2 失败，请稍后重试')
  } finally {
    syncing.value = false
  }
}

async function writebackToG62(): Promise<void> {
  if (props.isReadonly || !interest.groups.value.length) return
  writingBack.value = true
  try {
    const existing = await fetchG62DetailRows(props.projectId)
    if (!existing.length) {
      ElMessage.warning('未找到 G6-2 明细，请先在 Main 底稿编制明细表')
      return
    }
    const preview = applyG66InterestToDetailRows(existing, interest.groups.value)
    const adjTotal = preview.matchedAdjustmentTotal
    try {
      await ElMessageBox.confirm(
        `将 Σ(实际利息−票息) 回写至 G6-2「本期利息调整变动」：匹配 ${preview.matched.length} 条，未匹配 ${preview.unmatched.length} 条，回写合计 ${adjTotal.toFixed(2)}。`,
        'G6-6 回写预览',
        { confirmButtonText: '确认回写', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
    const mainWpId = await saveG62DetailRows(props.projectId, preview.rows)
    if (!mainWpId) {
      ElMessage.error('未找到 G6 Main 底稿，回写失败')
      return
    }
    ElMessage.success(`已回写 ${preview.matched.length} 条利息调整至 G6-2`)
  } catch {
    ElMessage.error('回写 G6-2 失败，请稍后重试')
  } finally {
    writingBack.value = false
  }
}

async function syncEclStage(): Promise<void> {
  if (props.isReadonly || !interest.groups.value.length) return
  syncingEcl.value = true
  try {
    const rows = await fetchG612ImpairmentRows(props.projectId)
    const seeds = mapG612RowsToInterestStageSeeds(rows)
    if (!seeds.length) {
      ElMessage.warning('未找到 G6-12 减值测算数据，请确认 ECL 底稿已编制')
      return
    }
    const { updated, unmatched } = interest.mergeEclStageSeeds(seeds)
    handleSave()
    ElMessage.success(
      `已同步阶段/减值：更新 ${updated} 项` +
        (unmatched ? `，未匹配 ${unmatched} 项` : ''),
    )
  } catch {
    ElMessage.warning('同步 G6-12 阶段失败，请稍后重试')
  } finally {
    syncingEcl.value = false
  }
}

async function compareEndingToG62(): Promise<void> {
  if (!interest.groups.value.length) return
  comparingEnding.value = true
  try {
    const detailRows = await fetchG62DetailRows(props.projectId)
    if (!detailRows.length) {
      ElMessage.warning('未找到 G6-2 明细，请确认 Main 底稿已编制')
      return
    }
    const rows = compareG66EndingToG62(interest.groups.value, detailRows)
    interest.setEndingAmortizedCompare(rows)
    const unmatched = rows.filter((r) => !r.matched && r.g62Ending == null).length
    const failed = rows.filter((r) => !r.matched && r.g62Ending != null).length
    if (interest.endingComparePassed.value) {
      ElMessage.success(`第三层勾稽通过：已核对 ${rows.length} 项`)
    } else {
      ElMessage.warning(
        `第三层勾稽未完全通过：差异 ${failed} 项` +
          (unmatched ? `，未匹配 ${unmatched} 项` : '') +
          `，差异合计 ${interest.endingCompareDiffTotal.value.toFixed(2)}`,
      )
    }
  } catch {
    ElMessage.warning('核对 G6-2 期末摊余失败，请稍后重试')
  } finally {
    comparingEnding.value = false
  }
}

async function pushVarianceToG64(): Promise<void> {
  if (props.isReadonly) return
  pushingAdj.value = true
  try {
    let { pairs, skipped } = buildG66InterestVarianceAdjustmentDrafts({
      amortizationDiff: interest.amortizationDiff.value,
      incomeDiff: interest.incomeDiff.value,
      incomeLayerActive: interest.incomeLayerActive.value,
      performanceMateriality: interest.performanceMateriality.value,
      varianceReason: interest.varianceReason.value,
      onlyMaterial: true,
    })
    if (!pairs.length) {
      try {
        await ElMessageBox.confirm(
          `无超过 B15 的可生成层（跳过 ${skipped.length} 项）。是否按全部可识别差异（>|0.01|）生成草稿？`,
          '生成 G6-4 调整草稿',
          { type: 'warning', confirmButtonText: '全部生成', cancelButtonText: '取消' },
        )
      } catch {
        return
      }
      ;({ pairs, skipped } = buildG66InterestVarianceAdjustmentDrafts({
        amortizationDiff: interest.amortizationDiff.value,
        incomeDiff: interest.incomeDiff.value,
        incomeLayerActive: interest.incomeLayerActive.value,
        performanceMateriality: interest.performanceMateriality.value,
        varianceReason: interest.varianceReason.value,
        onlyMaterial: false,
      }))
    }
    if (!pairs.length) {
      ElMessage.warning(
        skipped.length
          ? `无法生成草稿：${skipped.map((s) => s.reason).join('；')}`
          : '无可写入的勾稽差异',
      )
      return
    }
    const preview = pairs
      .map((p) => `${p.layerLabel}：差异 ${p.diff.toFixed(2)} → 金额 ${p.amount.toFixed(2)}`)
      .join('\n')
    try {
      await ElMessageBox.confirm(
        `将向 Main 底稿 G6-4 写入 ${pairs.length} 组借贷草稿（150302↔6111，须人工复核）：\n\n${preview}` +
          (skipped.length ? `\n\n另跳过 ${skipped.length} 项` : ''),
        '确认写入 G6-4',
        { confirmButtonText: '确认写入', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
    const { entries } = await fetchG64AdjustmentEntries(props.projectId)
    const merged = mergeG64EntriesWithG66Drafts(entries, pairs)
    const mainWpId = await saveG64AdjustmentEntries(props.projectId, merged)
    if (!mainWpId) {
      ElMessage.warning('未找到 Main 底稿实例，无法写入 G6-4')
      return
    }
    ElMessage.success(`已写入 G6-4 调整草稿 ${pairs.length} 组（${pairs.length * 2} 行）`)
  } catch {
    ElMessage.warning('写入 G6-4 失败，请稍后重试')
  } finally {
    pushingAdj.value = false
  }
}

// watch groups / conclusion 深度变化保存
watch(() => interest.groups.value, () => {
  handleSave()
}, { deep: true })

watch(() => interest.conclusion.value, () => {
  handleSave()
})

function aiContext() {
  const periods = interest.groups.value.flatMap((g) =>
    (g.periods || []).map((p: any) => ({
      project: g.investProject,
      indexRef: p.indexRef || '',
      eclStage: p.eclStage || g.eclStage || '',
      days: p.days,
    })),
  )
  return {
    groupCount: interest.groups.value.length,
    totalInterest: interest.totalInterest.value,
    totalAmortization: interest.totalAmortization.value,
    bookInterestIncome: interest.bookInterestIncome.value,
    interestAdjPeriodChange: interest.interestAdjPeriodChange.value,
    incomeDiff: interest.incomeDiff.value,
    amortizationDiff: interest.amortizationDiff.value,
    projects: interest.groups.value.map((g) => g.investProject),
    indexRefsSample: periods.filter((p) => p.indexRef).slice(0, 8),
    materialVariance:
      Math.abs(Number(interest.incomeDiff.value) || 0) > 0.01
      || Math.abs(Number(interest.amortizationDiff.value) || 0) > 0.01,
  }
}

// ─── AI辅助 ───
async function handleAiNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'interest-note',
    auditNote.value || '',
    aiContext(),
    'AI 利息测算审计说明',
  )
  if (text) saveAuditNote(text)
}

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'interest-conclusion',
    interest.conclusion.value || '',
    aiContext(),
    'AI 利息测算审计结论',
  )
  if (text) {
    interest.conclusion.value = text
    handleSave()
  }
}

// ─── 数字格式化 ───
function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// ─── 暴露接口 ───
defineExpose({
  toJSON: () => interest.toJSON(),
  syncFromMain,
  writebackToG62,
  syncEclStage,
})
</script>

<style scoped>
.g6-tab-interest-calculation {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 审计目标 / 工具栏 ─── */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}
.row-index-chip {
  margin-top: 4px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景）─── */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 2px;
}

.warn-alert {
  margin-bottom: 10px;
}
.warn-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
}
.initial-params {
  margin-top: 6px;
}
.variance-reason .is-missing :deep(.el-textarea__inner) {
  border-color: #f59e0b;
}

/* ─── 分组卡片 ─── */
.group-card {
  margin-bottom: 16px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}

.group-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group-name {
  font-weight: 600;
  font-size: 14px;
}

.group-params {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.param-item {
  font-size: 12px;
  color: #606266;
}

.group-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 期间表格 ─── */
.period-table {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 公式列样式 ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 2px 4px;
  display: inline-block;
}

/* ─── 新增期间 ─── */
.add-period-bar {
  margin-top: 8px;
  text-align: left;
}

/* ─── 底部操作 ─── */
.bottom-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 16px 0;
}

.import-export-dropdown {
  margin-left: 8px;
}

/* ─── 交叉验证 ─── */
.cross-validation-card {
  margin-bottom: 16px;
}

.cv-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  align-items: center;
}

.cv-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cv-label {
  font-size: 12px;
  color: #909399;
}
.cv-hint {
  font-size: 11px;
  color: #a8abb2;
}

.cv-value {
  font-size: 14px;
  font-weight: 600;
}

.cv-pass {
  color: #10b981;
}

.cv-fail {
  color: #ef4444;
}

/* ─── Section卡片通用 ─── */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 审计结论 ─── */
.conclusion-card {
  margin-bottom: 16px;
}

/* ─── 编制提示 ─── */
.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
