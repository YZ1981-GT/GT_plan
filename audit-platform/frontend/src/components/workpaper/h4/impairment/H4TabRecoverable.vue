<template>
  <div class="h4-tab-recoverable">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实工程物资可收回金额是否按 CAS8 以公允净额与预计未来现金流量现值孰高确定；复核关键假设及计算；结果回写 H4-7 减值测算。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:H4-8" :context-project-id="projectId" /></span>
        <el-tag size="small">物资组 {{ state.groups.value.length }}</el-tag>
        <el-tag size="small">预测期 {{ state.assumptions.value.forecastYears }} 年</el-tag>
        <el-tag v-if="state.staleSyncCount.value" size="small" type="danger">
          与 H4-7 不一致 {{ state.staleSyncCount.value }}
        </el-tag>
        <el-tag v-if="state.rateInvalid.value" size="small" type="danger">折现率≤增长率</el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:H4-7" :context-project-id="projectId" />
        <GtIndexChip value="wp:H4-2" :context-project-id="projectId" />
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', '减值测算表H4-7')">← H4-7</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSync">回写当前组</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSyncAll">回写全部</el-button>
        <el-button size="small" circle @click="openReview('H4-8-recoverable')">💬</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>CAS8：</strong>可收回金额 = MAX(公允价值减处置费用后的净额, 预计未来现金流量现值)。
        折现率应为反映当前市场货币时间价值和资产特定风险的<strong>税前利率</strong>；现金流与折现率口径须一致。
        WACC(税后) = E/(D+E)×Ke + D/(D+E)×Kd×(1−t)；Ke = Rf + β×(Rm−Rf)。
      </p>
    </div>

    <!-- 双模式：HTML 测算为主；OO 对照源模板 -->
    <div class="section-header mode-row">
      <span>可收回金额测试表 H4-8</span>
      <el-segmented
        :model-value="dualMode.currentMode.value"
        :options="dualMode.modeOptions"
        size="small"
        @change="dualMode.onModeChange"
      />
    </div>

    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :project-id="projectId"
      class="recoverable-oo"
    />

    <template v-else>
      <!-- 测试对象 -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header">
            <span>测试对象（多物资/资产组切换）</span>
            <div class="section-header-actions">
              <el-button size="small" :disabled="isReadonly" @click="handleAddGroup">+ 新增物资组</el-button>
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="isReadonly || state.groups.value.length <= 1"
                @click="handleRemoveGroup"
              >
                删除当前组
              </el-button>
            </div>
          </div>
        </template>
        <el-form :inline="true" size="small" label-width="88px">
          <el-form-item label="切换物资组">
            <el-select
              :model-value="state.activeGroupId.value"
              style="width: 280px"
              filterable
              @change="(id: string) => state.setActiveGroup(id)"
            >
              <el-option
                v-for="g in state.groups.value"
                :key="g.groupId"
                :label="`${g.name || '未命名'}（账面 ${fmtAmt(g.bookValue)}${g.bookValuePending ? '·待补' : ''}）`"
                :value="g.groupId"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="物资名称">
            <el-input
              :model-value="state.assumptions.value.materialName"
              :disabled="isReadonly"
              placeholder="工程物资名称/类别"
              style="width: 200px"
              @update:model-value="(v: string) => state.updateAssumption('materialName', v)"
            />
          </el-form-item>
          <el-form-item label="账面价值">
            <WpAmountInput
              :model-value="state.assumptions.value.bookValue"
              :disabled="isReadonly"
              @change="(v: number | undefined) => state.updateAssumption('bookValue', v ?? 0)"
            />
          </el-form-item>
          <el-form-item v-if="state.activeGroup.value?.bookValuePending" label="状态">
            <el-tag size="small" type="warning">账面待补录</el-tag>
          </el-form-item>
          <el-form-item v-if="state.activeGroup.value?.source" label="来源">
            <el-tag size="small">{{ state.activeGroup.value.source }}</el-tag>
          </el-form-item>
        </el-form>

        <div class="upstream-bar">
          <span class="upstream-label">从上游带入</span>
          <el-select
            v-model="upstreamKey"
            placeholder="H4-7 / H4-2 / H4-6（盘点关注）"
            filterable
            clearable
            style="width: 360px"
            size="small"
            :disabled="isReadonly || !state.upstreamCandidates.value.length"
          >
            <el-option
              v-for="c in state.upstreamCandidates.value"
              :key="c.key"
              :label="`[${c.source}] ${c.name} — ${c.hint}`"
              :value="c.key"
            />
          </el-select>
          <el-button size="small" :disabled="isReadonly || !upstreamKey" @click="handleImportUpstream">
            载入
          </el-button>
          <el-tag v-if="!state.upstreamCandidates.value.length" size="small" type="info">
            暂无上游候选（可手工填写；完成 H4-2/H4-7 后自动出现）
          </el-tag>
        </div>
      </el-card>

      <!-- 回写一致性 -->
      <el-card v-if="state.syncChecks.value.length" shadow="never" class="block-card">
        <template #header>
          <div class="section-header">
            <span>与 H4-7 回写一致性</span>
            <el-tag v-if="state.staleSyncCount.value" size="small" type="danger">
              {{ state.staleSyncCount.value }} 项待处理
            </el-tag>
            <el-tag v-else size="small" type="success">全部一致/无需测</el-tag>
          </div>
        </template>
        <el-table :data="state.syncChecks.value" border size="small">
          <el-table-column prop="name" label="物资名称" min-width="120" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.status === 'synced' ? 'success' : row.status === 'no-test' ? 'info' : 'danger'"
              >
                {{ syncStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="H4-7⑤" width="110" align="right">
            <template #default="{ row }">{{ fmtAmt(row.h7Recoverable) }}</template>
          </el-table-column>
          <el-table-column label="H4-8可收回" width="110" align="right">
            <template #default="{ row }">{{ fmtAmt(row.h8Recoverable) }}</template>
          </el-table-column>
          <el-table-column prop="message" label="说明" min-width="200" />
        </el-table>
      </el-card>

      <!-- 一、公允净额 -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header"><span>一、公允价值减去处置费用后的净额</span></div>
        </template>

        <h4 class="sub-title">（1）公允价值确定（优先：销售协议 → 活跃市场 → 估计）</h4>
        <el-table :data="fvPriceRows" border size="small" class="mb-12">
          <el-table-column prop="label" label="确定方法" width="160" />
          <el-table-column label="金额" width="160" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.amount"
                size="small"
                @change="row.onAmount"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="200">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.note"
                size="small"
                placeholder="取值依据..."
                @update:model-value="row.onNoteInput"
                @change="row.onNote"
              />
              <span v-else>{{ row.note || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="选用" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.selected" type="success" size="small">选用</el-tag>
            </template>
          </el-table-column>
        </el-table>

        <h4 class="sub-title">（2）处置费用</h4>
        <el-form label-width="110px" size="small">
          <el-row :gutter="12">
            <el-col :span="8">
              <el-form-item label="法律费用">
                <WpAmountInput v-model="state.fvDisposal.value.legalFees" :disabled="isReadonly" @change="persistFv" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="相关税费">
                <el-input-number v-model="state.fvDisposal.value.relatedTaxes" :controls="false" :disabled="isReadonly" @change="persistFv" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="搬运费">
                <el-input-number v-model="state.fvDisposal.value.transportCosts" :controls="false" :disabled="isReadonly" @change="persistFv" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="直接费用">
                <WpAmountInput v-model="state.fvDisposal.value.directCosts" :disabled="isReadonly" @change="persistFv" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="其他费用">
                <WpAmountInput v-model="state.fvDisposal.value.otherCosts" :disabled="isReadonly" @change="persistFv" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="处置费用合计">
                <span class="formula-cell">{{ fmtAmt(state.disposalTotal.value) }}</span>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>

        <div class="result-bar">
          <span>公允价值（{{ state.fairValueResolved.value.source }}）</span>
          <b class="amt-cell">{{ fmtAmt(state.fairValueResolved.value.value) }}</b>
          <span>− 处置费用</span>
          <b class="amt-cell">{{ fmtAmt(state.disposalTotal.value) }}</b>
          <span>= 公允净额</span>
          <b class="highlight">{{ fmtAmt(state.fairValueLessDisposal.value) }}</b>
        </div>

        <el-input
          v-model="state.fvDisposal.value.auditNote"
          type="textarea"
          :autosize="{ minRows: 2 }"
          :disabled="isReadonly"
          placeholder="审计说明：公允价值及处置费用取值依据（协议价/市价/同类交易估计）..."
          class="mt-8"
          @change="persistFv"
        />
      </el-card>

      <!-- 二、DCF -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header"><span>二、预计未来现金流量的现值（使用价值）</span></div>
        </template>

        <h4 class="sub-title">（1）未来现金流量预测（一般不超过5年）</h4>
        <el-form :inline="true" size="small" class="mb-8">
          <el-form-item label="预测期(年)">
            <el-input-number
              :model-value="state.assumptions.value.forecastYears"
              :min="1"
              :max="10"
              :disabled="isReadonly"
              @change="(v: number | undefined) => state.updateAssumption('forecastYears', v ?? 5)"
            />
          </el-form-item>
          <el-form-item label="永续增长率g%">
            <el-input-number
              :model-value="state.assumptions.value.growthRate"
              :min="-5"
              :max="10"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              @change="(v: number | undefined) => state.updateAssumption('growthRate', v ?? 0)"
            />
          </el-form-item>
        </el-form>

        <el-alert
          v-for="(w, i) in state.growthWarnings.value"
          :key="i"
          type="warning"
          :closable="false"
          show-icon
          class="mb-8"
          :title="w"
        />

        <el-table :data="state.cashFlowRows.value" border stripe size="small" class="mb-12">
          <el-table-column prop="year" label="年份" width="80" align="center">
            <template #default="{ row }">第{{ row.year }}年</template>
          </el-table-column>
          <el-table-column label="现金流入" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.revenue"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => state.updateCashFlowCell(row.rowId, 'revenue', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.revenue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="现金流出" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.cost"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => state.updateCashFlowCell(row.rowId, 'cost', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净现金流" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="流入−流出">{{ fmtAmt(row.netCashFlow) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="折现系数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="1/(1+r)^t">{{ row.discountFactor?.toFixed(4) ?? '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="现值" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="净现金流×折现系数">{{ fmtAmt(row.presentValue) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <el-descriptions :column="2" border size="small" class="mb-12">
          <el-descriptions-item label="行业长期平均增长率%">
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.assumptions.value.industryGrowthRate"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateAssumption('industryGrowthRate', v ?? 0)"
            />
            <span v-else>{{ state.assumptions.value.industryGrowthRate }}%</span>
          </el-descriptions-item>
          <el-descriptions-item label="市场长期增长率%">
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.assumptions.value.marketGrowthRate"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateAssumption('marketGrowthRate', v ?? 0)"
            />
            <span v-else>{{ state.assumptions.value.marketGrowthRate }}%</span>
          </el-descriptions-item>
          <el-descriptions-item label="国家/地区长期增长率%">
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.assumptions.value.countryGrowthRate"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateAssumption('countryGrowthRate', v ?? 0)"
            />
            <span v-else>{{ state.assumptions.value.countryGrowthRate }}%</span>
          </el-descriptions-item>
          <el-descriptions-item label="增长率确定依据">
            <el-input
              v-if="!isReadonly"
              :model-value="state.assumptions.value.growthRateBasis"
              size="small"
              placeholder="应≤外部基准；通常为0或负"
              @update:model-value="(v: string) => state.updateAssumption('growthRateBasis', v)"
            />
            <span v-else>{{ state.assumptions.value.growthRateBasis || '-' }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="sub-title">（2）折现率 / 加权平均资金成本（WACC）</h4>
        <el-form label-width="130px" size="small">
          <el-row :gutter="12">
            <el-col :span="8">
              <el-form-item label="所得税率 t%">
                <el-input-number v-model="state.waccParams.value.taxRate" :controls="false" :min="0" :max="100" :disabled="isReadonly" @change="persistWacc" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="付息负债 D">
                <el-input-number v-model="state.waccParams.value.totalDebt" :controls="false" :disabled="isReadonly" @change="persistWacc" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="权益资本 E">
                <el-input-number v-model="state.waccParams.value.totalEquity" :controls="false" :disabled="isReadonly" @change="persistWacc" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="债务成本 Kd%">
                <WpAmountInput v-model="state.waccParams.value.costOfDebt" :disabled="isReadonly" @change="persistWacc" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="无风险利率 Rf%">
                <el-input-number v-model="state.waccParams.value.riskFreeRate" :controls="false" :precision="2" :disabled="isReadonly" @change="persistWacc" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="β系数">
                <el-input-number v-model="state.waccParams.value.beta" :controls="false" :precision="3" :step="0.1" :disabled="isReadonly" @change="persistWacc" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="市场回报 Rm%">
                <el-input-number v-model="state.waccParams.value.marketReturn" :controls="false" :precision="2" :disabled="isReadonly" @change="persistWacc" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="权益成本 Ke%">
                <span class="formula-cell" title="Ke = Rf + β×(Rm−Rf)">{{ state.costOfEquity.value.toFixed(2) }}%</span>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="折现口径">
                <el-radio-group
                  :model-value="state.assumptions.value.usePreTaxRate"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: boolean | string | number) => state.updateAssumption('usePreTaxRate', v === true || v === 'true')"
                >
                  <el-radio-button :value="true">税前(CAS8)</el-radio-button>
                  <el-radio-button :value="false">税后</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>

        <div class="wacc-result-bar">
          <span title="WACC税后 = E/(D+E)×Ke + D/(D+E)×Kd×(1−t)">WACC(税后)</span>
          <b>{{ state.waccAfterTax.value.toFixed(2) }}%</b>
          <span title="税前折现率 ≈ WACC税后/(1−t)">折现率(税前)</span>
          <b>{{ state.preTaxDiscountRate.value.toFixed(2) }}%</b>
          <span>实际折现率</span>
          <b class="highlight">{{ state.effectiveDiscountRate.value.toFixed(2) }}%</b>
          <el-tag v-if="state.rateInvalid.value" type="danger" size="small">折现率≤增长率，终值无效</el-tag>
          <el-tag v-if="state.waccAfterTax.value <= 0" type="warning" size="small">
            未填 D/E，使用手工折现率 {{ state.assumptions.value.discountRate }}%
          </el-tag>
        </div>

        <el-form v-if="state.waccAfterTax.value <= 0" :inline="true" size="small" class="mt-8">
          <el-form-item label="手工折现率%">
            <el-input-number
              :model-value="state.assumptions.value.discountRate"
              :min="0.1"
              :max="50"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              @change="(v: number | undefined) => state.updateAssumption('discountRate', v ?? 10)"
            />
          </el-form-item>
        </el-form>

        <h4 class="sub-title">（3）现值汇总</h4>
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="预测期现值合计">
            <span class="formula-cell">{{ fmtAmt(state.pvTotal.value) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="终值（未折现）">
            <span class="formula-cell" title="TV = CFn×(1+g)/(r−g)">{{ fmtAmt(state.terminalValueUndiscounted.value) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="终值现值">
            <span class="formula-cell">{{ fmtAmt(state.tvPresent.value) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="使用价值(DCF)">
            <b class="highlight">{{ fmtAmt(state.totalPV.value) }}</b>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 三、可收回金额 -->
      <el-card shadow="never" class="block-card recoverable-card">
        <template #header>
          <div class="section-header"><span>三、可收回金额</span></div>
        </template>
        <div class="final-recoverable">
          <div class="cmp-item">
            <div class="cmp-label">公允净额</div>
            <div class="cmp-value">{{ fmtAmt(state.fairValueLessDisposal.value) }}</div>
          </div>
          <div class="cmp-vs">vs</div>
          <div class="cmp-item">
            <div class="cmp-label">使用价值(DCF)</div>
            <div class="cmp-value">{{ fmtAmt(state.totalPV.value) }}</div>
          </div>
          <div class="cmp-vs">→</div>
          <div class="cmp-item highlight-box">
            <div class="cmp-label">可收回金额（取较高者）</div>
            <div class="cmp-value highlight">{{ fmtAmt(state.recoverableAmount.value) }}</div>
            <el-tag size="small" type="primary">{{ state.recoverableSource.value }}</el-tag>
          </div>
        </div>
        <div class="impairment-hint" :class="{ 'has-impairment': state.impliedImpairment.value > 0 }">
          <span>账面价值 {{ fmtAmt(state.assumptions.value.bookValue) }}</span>
          <span>− 可收回金额 {{ fmtAmt(state.recoverableAmount.value) }}</span>
          <span>= 应计提减值</span>
          <b>{{ fmtAmt(state.impliedImpairment.value) }}</b>
          <el-tag v-if="state.impliedImpairment.value > 0" type="danger" size="small">存在减值</el-tag>
          <el-tag v-else type="success" size="small">无需减值</el-tag>
        </div>
      </el-card>

      <!-- 四、敏感性 -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header"><span>四、敏感性分析（折现率 ±2% × 增长率 ±1%）</span></div>
        </template>
        <el-table :data="state.sensitivityMatrix.value" border size="small" class="sensitivity-table">
          <el-table-column prop="label" label="折现率 \\ 增长率" width="120" align="center" fixed />
          <el-table-column
            v-for="col in state.sensitivityCols.value"
            :key="col"
            :label="`g=${col}%`"
            min-width="100"
            align="right"
          >
            <template #default="{ row }">
              <span
                :class="{
                  'error-amount':
                    (row[`g_${col}`] as number) < (state.assumptions.value.bookValue ?? 0)
                    && state.assumptions.value.bookValue > 0,
                }"
              >
                {{ fmtAmt(row[`g_${col}`] as number) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <p class="sensitivity-note">红色 = 该情景下可收回金额低于账面价值；矩阵取 MAX(公允净额, DCF)。</p>
      </el-card>

      <!-- 五、审计说明 / 结论 -->
      <el-card shadow="never" class="audit-note-card">
        <template #header><div class="section-header"><span>五、审计说明</span></div></template>
        <el-input
          :model-value="state.recoverableNote.value"
          type="textarea"
          :autosize="{ minRows: 4 }"
          :disabled="isReadonly"
          placeholder="填写审计说明：公允取值层次、处置费用依据、现金流预测来源（如领用计划/处置计划）、WACC参数取值、与管理层沟通及复核情况等。"
          @change="(v: string) => state.saveRecoverableNote(v)"
        />
      </el-card>

      <el-card shadow="never" class="audit-note-card">
        <template #header><div class="section-header"><span>六、审计结论</span></div></template>
        <el-input
          :model-value="state.recoverableConclusion.value"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="isReadonly"
          placeholder="可收回金额测试结论（如：经测算可收回金额为…，高于/低于账面价值…，减值准备计提是否充分）"
          @change="(v: string) => state.saveRecoverableConclusion(v)"
        />
      </el-card>
    </template>

    <details class="edit-tips">
      <summary>编制提示（CAS8 / 对齐 Excel H4-8）</summary>
      <ol>
        <li>可收回金额 = MAX(公允价值−处置费用净额, 预计未来现金流量现值)。公式对应源模板 N23=MAX(N13,N20)。</li>
        <li>公允净额优先取公平交易中销售协议价格减处置费用；无协议则取活跃市场价格；再无则按最佳信息估计（同类物资近期交易价等）。</li>
        <li>处置费用包括法律费用、相关税费、搬运费以及为使物资达到可销售状态所发生的直接费用。</li>
        <li>预计未来现金流量应基于管理层批准的最近财务预算/领用与处置计划；预测期一般不超过5年；稳定期增长率通常为0或负，且不超过行业/市场/国家长期平均增长率。</li>
        <li>折现率应为反映货币时间价值和资产特定风险的<strong>税前</strong>利率（CAS8）。实务可先算税后WACC再转换为税前；未填 D/E 时可用手工折现率，避免 #DIV/0!。</li>
        <li>WACC：Ke = Rf + β×(Rm−Rf)；WACC税后 = E/(D+E)×Ke + D/(D+E)×Kd×(1−t)。折现率须 &gt; 永续增长率，否则终值模型无效。</li>
        <li>测算完成后点击「回写当前组/全部」，将③公允净额与④现值写入 H4-7；一致性表可核对是否过期。</li>
        <li>工程物资领用结转时，对应减值准备应一并结转（见审计过程提示）；本期已确认减值不得转回（CAS8）。</li>
        <li>可切换「在线编辑」对照源模板 H4-8（58行矩阵）；HTML 模式为可交互测算主路径。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H4TabRecoverable.vue — H4-8 可收回金额测试表
 * 对齐 Excel「工程物资减值准备测试表-可收回金额」：
 * 多物资组 + 公允净额 → DCF/WACC → MAX → 敏感性 → 回写 H4-7
 */
import { ref, computed, inject, toRef, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useH4Recoverable } from '../../composables/useH4Recoverable'
import { useH4DualMode } from '../../composables/useH4DualMode'
import GtIndexChip from '../../GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName: string
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const dualMode = useH4DualMode({
  wpId: toRef(props, 'wpId'),
  sheetName: toRef(props, 'sheetName'),
})

const state = useH4Recoverable({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const upstreamKey = ref('')

const fvPriceRows = computed(() => {
  const fv = state.fvDisposal.value
  const source = state.fairValueResolved.value.source
  return [
    {
      label: '1.销售协议价格',
      amount: fv.salesAgreementPrice,
      note: fv.salesAgreementNote,
      selected: source === '销售协议价格',
      onAmount: (v: number | undefined) => state.updateFvDisposal({ salesAgreementPrice: v ?? 0 }),
      onNoteInput: (v: string) => { fv.salesAgreementNote = v },
      onNote: () => state.updateFvDisposal({ salesAgreementNote: fv.salesAgreementNote }),
    },
    {
      label: '2.活跃市场价格',
      amount: fv.activeMarketPrice,
      note: fv.activeMarketNote,
      selected: source === '活跃市场价格',
      onAmount: (v: number | undefined) => state.updateFvDisposal({ activeMarketPrice: v ?? 0 }),
      onNoteInput: (v: string) => { fv.activeMarketNote = v },
      onNote: () => state.updateFvDisposal({ activeMarketNote: fv.activeMarketNote }),
    },
    {
      label: '3.估计价格',
      amount: fv.estimatedPrice,
      note: fv.estimatedNote,
      selected: source === '估计价格',
      onAmount: (v: number | undefined) => state.updateFvDisposal({ estimatedPrice: v ?? 0 }),
      onNoteInput: (v: string) => { fv.estimatedNote = v },
      onNote: () => state.updateFvDisposal({ estimatedNote: fv.estimatedNote }),
    },
  ]
})

function persistFv() {
  state.updateFvDisposal({})
}

function persistWacc() {
  state.updateWaccParams({})
}

function handleAddGroup() {
  state.addGroup()
  ElMessage.success('已新增物资组')
}

function handleRemoveGroup() {
  const res = state.removeActiveGroup()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleImportUpstream() {
  if (!upstreamKey.value) return
  const res = state.importUpstreamCandidate(upstreamKey.value)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleSync() {
  const res = state.syncToH47()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleSyncAll() {
  const res = state.syncAllGroupsToH47()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function syncStatusLabel(status: string): string {
  if (status === 'synced') return '已同步'
  if (status === 'stale') return '已过期'
  if (status === 'missing-h8') return '缺H4-8'
  return '无需测'
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.nav-chip { cursor: pointer; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px;
  font-size: 12px; line-height: 1.6; color: #92400e;
}
.mode-row { margin-bottom: 12px; }
.recoverable-oo { min-height: 500px; margin-bottom: 12px; }
.block-card, .audit-note-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.section-header-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.upstream-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--el-border-color-lighter);
}
.upstream-label { font-size: 12px; color: var(--el-text-color-secondary); min-width: 72px; }
.sub-title { margin: 8px 0 12px; font-size: 13px; font-weight: 600; color: var(--el-text-color-regular); }
.mb-8 { margin-bottom: 8px; }
.mb-12 { margin-bottom: 12px; }
.mt-8 { margin-top: 8px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help; font-variant-numeric: tabular-nums;
}
.highlight { color: var(--el-color-primary); font-weight: 600; }
.result-bar, .wacc-result-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  padding: 10px 12px; background: var(--el-fill-color-light); border-radius: 4px; margin-top: 8px;
}
.final-recoverable {
  display: flex; flex-wrap: wrap; align-items: center; gap: 16px; justify-content: center;
  padding: 16px 8px;
}
.cmp-item { text-align: center; min-width: 120px; }
.cmp-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.cmp-value { font-size: 16px; font-weight: 600; font-variant-numeric: tabular-nums; }
.cmp-vs { color: var(--el-text-color-secondary); font-weight: 500; }
.highlight-box {
  padding: 12px 16px; background: var(--el-color-primary-light-9); border-radius: 6px;
}
.impairment-hint {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  margin-top: 12px; padding: 10px 12px; border-radius: 4px;
  background: var(--el-fill-color-lighter); font-size: 13px;
}
.impairment-hint.has-impairment { background: var(--el-color-danger-light-9); }
.sensitivity-table { font-size: var(--wp-font-size, 13px); }
.sensitivity-note { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 20px; margin-top: 8px; }
</style>
