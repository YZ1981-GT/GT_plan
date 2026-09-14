<template>
  <div class="h2-tab-decrease-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 一、审计目标（对齐致同模板） -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>核实已记录的在建工程减少确已发生，且已记入恰当账户（存在/发生）</li>
        <li>核实所有应记录的在建工程减少均已入账，相关披露完整（完整性/截止）</li>
        <li>核实转固及其他减少金额准确（含利息资本化结转），计价与列报恰当（准确性/计价）</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H2-9" :context-project-id="projectId" /></span>
      <GtIndexChip value="wp:H2-2" :context-project-id="projectId" context="明细勾稽" />
      <GtIndexChip value="wp:H2-5" :context-project-id="projectId" context="转固时点" />
      <GtIndexChip value="wp:H2-3" :context-project-id="projectId" context="调整分录" />
      <el-tag size="small" type="info">样本 {{ state.rows.value.length }} 项</el-tag>
      <el-tag v-if="state.summary.value.anomalyCount > 0" size="small" type="danger">
        异常 {{ state.summary.value.anomalyCount }} 项
      </el-tag>
      <el-tag v-if="state.summary.value.acceptanceDiffCount > 0" size="small" type="warning">
        验收差异 {{ state.summary.value.acceptanceDiffCount }} 项
      </el-tag>
      <el-tag v-if="state.summary.value.evidenceGapCount > 0" size="small" type="warning">
        证据缺口 {{ state.summary.value.evidenceGapCount }} 项
      </el-tag>
      <el-tag v-if="state.summary.value.provisionalCount > 0" size="small" type="warning">
        暂估转固 {{ state.summary.value.provisionalCount }} 项
      </el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ state.summary.value.coverageRate.toFixed(2) }}%
      </el-tag>
      <el-button
        v-if="!isReadonly"
        size="small"
        :disabled="state.summary.value.acceptanceDiffCount <= 0 && state.summary.value.evidenceGapCount <= 0"
        @click="handleAutoMark"
      >
        自动标记异常
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        :disabled="state.pushableSettlementAmount.value <= 0"
        @click="handlePushAje"
      >
        推送决算/差异AJE至 H2-3
        <template v-if="state.pushableSettlementAmount.value > 0">
          ({{ fmtAmt(state.pushableSettlementAmount.value) }})
        </template>
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="warning"
        :disabled="state.summary.value.evidenceGapCount <= 0"
        @click="handlePushEvidenceGap"
      >
        证据缺口推送至 H2-3
        <template v-if="state.summary.value.evidenceGapCount > 0">
          ({{ state.summary.value.evidenceGapCount }})
        </template>
      </el-button>
    </div>

    <el-alert
      v-if="state.summary.value.acceptanceDiffCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`有 ${state.summary.value.acceptanceDiffCount} 项验收金额与转入固定资产不一致，可推送成本调整草稿至 H2-3（不调已提折旧）。`"
    />
    <el-alert
      v-if="state.summary.value.evidenceGapCount > 0"
      type="info"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`有 ${state.summary.value.evidenceGapCount} 项转固样本审批未确认或验收盖章不全，可「证据缺口推送至 H2-3」生成索引说明行。`"
    />

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、样本选取标准与规模</span>
          <div class="section-header-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(state.linkedDecrease.value.amount > 0)"
              @click="handleSyncPopulation"
            >
              从 {{ state.linkedDecrease.value.source || 'H2-2' }} 带入本期减少
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="本期减少合计（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.samplingParams.value.populationAmount"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => onParamChange('populationAmount', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(state.samplingParams.value.populationAmount) }}</span>
            <el-tag v-if="state.linkedDecrease.value.source" size="small" type="info" class="src-tag">
              源 H2-2: {{ fmtAmt(state.linkedDecrease.value.amount) }}
            </el-tag>
            <el-tag v-if="state.populationManual.value" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="其中：转入固定资产">
          <el-input-number
            v-if="!isReadonly"
            :model-value="state.samplingParams.value.transferPopulation"
            :controls="false"
            size="small"
            @change="(v: number | undefined) => onParamChange('transferPopulation', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(state.samplingParams.value.transferPopulation) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="其中：其他减少">
          <el-input-number
            v-if="!isReadonly"
            :model-value="state.samplingParams.value.otherPopulation"
            :controls="false"
            size="small"
            @change="(v: number | undefined) => onParamChange('otherPopulation', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(state.samplingParams.value.otherPopulation) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法">
          <el-select
            v-if="!isReadonly"
            :model-value="state.samplingParams.value.samplingMethod"
            size="small"
            style="width:140px"
            @change="(v: string) => onParamChange('samplingMethod', v)"
          >
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随机抽样" value="随机抽样" />
            <el-option label="判断抽样" value="判断抽样" />
          </el-select>
          <span v-else>{{ state.samplingParams.value.samplingMethod || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="样本量">
          {{ state.rows.value.length }}
        </el-descriptions-item>
        <el-descriptions-item label="重要性水平">
          <el-input-number
            v-if="!isReadonly"
            :model-value="state.samplingParams.value.materialityLevel"
            :controls="false"
            size="small"
            @change="(v: number | undefined) => onParamChange('materialityLevel', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(state.samplingParams.value.materialityLevel) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="检查比例">
          <span :class="{ 'warn-coverage': state.summary.value.coverageRate < 20 && state.samplingParams.value.populationAmount > 0 }">
            {{ state.summary.value.coverageRate.toFixed(2) }}%
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <div class="specific-sample" v-if="!isReadonly || state.samplingParams.value.specificSampleNote">
        <span class="param-label">特定样本：</span>
        <el-input
          v-if="!isReadonly"
          :model-value="state.samplingParams.value.specificSampleNote"
          size="small"
          placeholder="大额、关联方/关联交易、异常款项全部测试说明…"
          @change="(v: string) => onParamChange('specificSampleNote', v)"
        />
        <span v-else>{{ state.samplingParams.value.specificSampleNote }}</span>
      </div>
      <el-alert
        v-if="populationDrift"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`总体与 H2-2（${fmtAmt(state.linkedDecrease.value.amount)}）不一致，可重新带入或保留手工数。`"
      />
    </el-card>

    <!-- 三、测试 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、测试 — 本期减少检查明细（H2-9）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-9')">💬</el-button>
          </div>
        </div>
      </template>

      <div class="test-content-hint">
        <p>测试内容：</p>
        <ol>
          <li>检查原始凭证（竣工决算/验收交接单/其他转出凭证）是否齐全</li>
          <li>记账凭证与原始凭证是否相符，账务处理是否正确</li>
          <li>是否记录于恰当会计期间；利息资本化结转是否准确</li>
          <li>关键证据（审批单、验收单盖章）要素是否完整（可按被审计单位情况调整）</li>
        </ol>
      </div>

      <el-table
        :data="state.rows.value"
        border
        stripe
        size="small"
        max-height="520"
        class="check-table"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="序号" width="48" fixed align="center" />

        <el-table-column prop="name" label="工程项目名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCellChange(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decreaseDate" label="减少日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.decreaseDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'decreaseDate', $event)" />
            <span v-else>{{ row.decreaseDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证编号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
              @change="onCellChange(row.rowId, 'voucherNo', $event)" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decreaseType" label="减少类型" min-width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.decreaseType" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'decreaseType', $event)">
              <el-option label="转入固定资产" value="转入固定资产" />
              <el-option label="报废" value="报废" />
              <el-option label="毁损" value="毁损" />
              <el-option label="出售" value="出售" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.decreaseType || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="转入固定资产" align="center">
          <el-table-column prop="transferToFaAmount" label="金额" min-width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.transferToFaAmount"
                size="small" class="amt-input" @change="onCellChange(row.rowId, 'transferToFaAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.transferToFaAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="transferInterestCap" label="其中：利息资本化" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.transferInterestCap" :controls="false"
                size="small" class="amt-input" @change="onCellChange(row.rowId, 'transferInterestCap', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.transferInterestCap) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="其他减少" align="center">
          <el-table-column prop="otherDecreaseAmount" label="金额" min-width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.otherDecreaseAmount"
                size="small" class="amt-input" @change="onCellChange(row.rowId, 'otherDecreaseAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.otherDecreaseAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="otherInterestCap" label="其中：利息资本化" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.otherInterestCap" :controls="false"
                size="small" class="amt-input" @change="onCellChange(row.rowId, 'otherInterestCap', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.otherInterestCap) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="审批单" align="center">
          <el-table-column prop="approvalRef" label="日期/编号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.approvalRef" size="small"
                @change="onCellChange(row.rowId, 'approvalRef', $event)" />
              <span v-else>{{ row.approvalRef || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="isApproved" label="恰当审批" width="90" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.isApproved" size="small" style="width:70px"
                @change="onCellChange(row.rowId, 'isApproved', $event)">
                <el-option label="-" value="" />
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ row.isApproved || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="验收单" align="center">
          <el-table-column prop="acceptanceDate" label="验收日期" min-width="110">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.acceptanceDate" type="date" size="small"
                value-format="YYYY-MM-DD" style="width:100%"
                @change="onCellChange(row.rowId, 'acceptanceDate', $event)" />
              <span v-else>{{ row.acceptanceDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="acceptanceAmount" label="金额" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.acceptanceAmount"
                size="small" class="amt-input" @change="onCellChange(row.rowId, 'acceptanceAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.acceptanceAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="验收−转固" min-width="100" align="right">
            <template #default="{ row }">
              <span
                class="amt-cell"
                :class="{ 'diff-warn': Math.abs(acceptanceDiffOf(row)) >= 0.01 }"
                :title="flagTip(row.rowId)"
              >
                {{ fmtDiff(acceptanceDiffOf(row)) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="stampEngineering" label="工程部" width="72" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.stampEngineering" size="small" style="width:60px"
                @change="onCellChange(row.rowId, 'stampEngineering', $event)">
                <el-option label="-" value="" />
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ row.stampEngineering || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="stampContractor" label="施工方" width="72" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.stampContractor" size="small" style="width:60px"
                @change="onCellChange(row.rowId, 'stampContractor', $event)">
                <el-option label="-" value="" />
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ row.stampContractor || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="stampSupervisor" label="监理方" width="72" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.stampSupervisor" size="small" style="width:60px"
                @change="onCellChange(row.rowId, 'stampSupervisor', $event)">
                <el-option label="-" value="" />
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ row.stampSupervisor || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="isProvisional" label="暂估转固" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isProvisional" size="small" style="width:70px"
              @change="onCellChange(row.rowId, 'isProvisional', $event)">
              <el-option label="-" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isProvisional || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="isRelatedParty" label="关联方" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRelatedParty" size="small" style="width:70px"
              @change="onCellChange(row.rowId, 'isRelatedParty', $event)">
              <el-option label="-" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isRelatedParty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relatedPartyName" label="关联方名称" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isRelatedParty === '是'"
              v-model="row.relatedPartyName" size="small"
              placeholder="供 H2-17 带入"
              @change="onCellChange(row.rowId, 'relatedPartyName', $event)"
            />
            <span v-else>{{ row.isRelatedParty === '是' ? (row.relatedPartyName || '-') : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联关系" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isRelatedParty === '是'"
              v-model="row.relationship" size="small"
              placeholder="可选"
              @change="onCellChange(row.rowId, 'relationship', $event)"
            />
            <span v-else>{{ row.isRelatedParty === '是' ? (row.relationship || '-') : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalIncome" label="处置收入" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly && (row.decreaseType === '出售' || row.decreaseType === '报废' || row.otherDecreaseAmount > 0)"
              v-model="row.disposalIncome"
              size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'disposalIncome', $event)"
            />
            <span v-else class="amt-cell">{{ row.disposalIncome ? fmtAmt(row.disposalIncome) : '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="otherEvidence" label="其他关键证据" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.otherEvidence" size="small"
              @change="onCellChange(row.rowId, 'otherEvidence', $event)" />
            <span v-else>{{ row.otherEvidence || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="queryNo" label="查询号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.queryNo" size="small"
              @change="onCellChange(row.rowId, 'queryNo', $event)" />
            <span v-else>{{ row.queryNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="校验提示" min-width="140">
          <template #default="{ row }">
            <span v-if="flagTip(row.rowId)" class="flag-tip" :title="flagTip(row.rowId)">
              {{ flagTip(row.rowId) }}
            </span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="isAbnormal" label="是否异常" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isAbnormal" size="small" style="width:70px"
              @change="onCellChange(row.rowId, 'isAbnormal', $event)">
              <el-option label="-" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isAbnormal || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="auditConclusion" label="检查结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.auditConclusion" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'auditConclusion', $event)">
              <el-option label="无异常" value="无异常" />
              <el-option label="存疑" value="存疑" />
              <el-option label="需调整" value="需调整" />
            </el-select>
            <el-tag v-else :type="row.auditConclusion === '无异常' ? 'success' : 'warning'" size="small">
              {{ row.auditConclusion || '待检' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-block">
        <div class="summary-line">
          样本合计：转入固定资产 <strong>{{ fmtAmt(state.transferSampleTotal.value) }}</strong>
          <span class="sep">其他减少 <strong>{{ fmtAmt(state.otherSampleTotal.value) }}</strong></span>
          <span class="sep">合计 <strong>{{ fmtAmt(state.sampleTotal.value) }}</strong></span>
          <span class="sep">利息资本化 <strong>{{ fmtAmt(state.interestCapSampleTotal.value) }}</strong></span>
        </div>
        <div class="summary-line">
          本期减少在建工程合计（总体）：
          <strong>{{ fmtAmt(state.samplingParams.value.populationAmount) }}</strong>
          <span class="sep">
            检查比例：
            <strong :class="{ 'warn-coverage': state.summary.value.coverageRate < 20 && state.samplingParams.value.populationAmount > 0 }">
              {{ state.summary.value.coverageRate.toFixed(2) }}%
            </strong>
          </span>
          <span class="sep muted">
            转固检查比例 {{ state.transferCoverageRate.value.toFixed(2) }}%
            ／ 其他减少检查比例 {{ state.otherCoverageRate.value.toFixed(2) }}%
          </span>
        </div>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>四、审计说明</span></div>
      </template>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        placeholder="概述抽样与逐项检查情况；若检查比例偏低，说明扩大样本或判断抽样的理由；关注暂估转固与延迟转固风险。"
        :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>五、审计结论</span></div>
      </template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="如：所抽减少真实、转固/其他减少计量准确、审批与验收证据充分，未见异常；或列明拟调整事项（→ H2-3）及范围受限影响。"
        :disabled="isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>

    <!-- 提示（对齐致同模板） -->
    <details class="edit-tips" open>
      <summary>提示（编制要点）</summary>
      <ol>
        <li>本表用于汇总本年度减少在建工程的测试情况。</li>
        <li>检查已完工程项目的竣工决算报告、验收交接单等相关凭证以及其他转出数的原始凭证，检查会计处理是否正确。</li>
        <li>
          对已达到预定可使用状态但尚未办理竣工决算的在建工程，检查是否按估计价值转出固定资产并计提折旧；
          竣工决算后按实际成本调整暂估价值，但<strong>不调整</strong>原已计提的折旧额。可在「暂估转固」列标记，
          并填写验收/决算金额后「推送决算/差异AJE至 H2-3」。
        </li>
        <li>关注是否存在已达预定可使用状态仍挂列在建工程、少计折旧的情形（可交叉索引 H2-5 转固时点检查）。</li>
        <li>
          概述：（1）程序的测试情况、结果；
          （2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。
        </li>
        <li>
          验收金额与转固金额差异超阈值（重要性×1%与100元取高）时自动提示；推送 AJE 为借/贷 1601↔1604 成本调整，重复推送替换旧自动草稿。
        </li>
      </ol>
    </details>

    <el-dialog
      v-model="showSamplingDialog"
      title="抽凭引擎（科目 1604 在建工程-减少）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="1604"
        phase="final"
        :year="samplingYear"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H2TabDecreaseCheck.vue — H2-9 在建工程减少检查
 * 对齐致同：目标 → 抽样 → 转入固定资产/其他减少 + 审批验收证据 → 检查比例 → 说明/结论 → 提示
 */
import { ref, inject, toRef, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useH2DecreaseCheck } from '../../composables/useH2DecreaseCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

/** 抽凭引擎所需审计年度：优先父级传入，回退当前年 */
const samplingYear = computed(() => props.year || new Date().getFullYear())

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const showSamplingDialog = ref(false)

const state = useH2DecreaseCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isReadonly = computed(() => props.isReadonly)

const coverageTagType = computed(() => {
  const rate = state.summary.value.coverageRate
  const pop = state.samplingParams.value.populationAmount
  if (!pop) return 'info'
  if (rate < 20) return 'warning'
  if (rate >= 50) return 'success'
  return ''
})

const populationDrift = computed(() => {
  const linked = state.linkedDecrease.value
  if (!linked.source || linked.amount <= 0) return false
  if (!state.populationManual.value) return false
  return Math.abs(linked.amount - state.samplingParams.value.populationAmount) > 0.01
})

function onParamChange(field: string, value: any) {
  state.updateSamplingParams({ [field]: value } as any)
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

function handleSyncPopulation() {
  const ok = state.syncPopulationFromH22()
  if (ok) {
    ElMessage.success(`已从 H2-2 带入本期减少合计 ${fmtAmt(state.linkedDecrease.value.amount)}`)
  } else {
    ElMessage.warning('H2-2 暂无可带入的本期减少数据（转固+其他减少）')
  }
}

function handlePushAje() {
  const res = state.pushSettlementAjeToH23()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handlePushEvidenceGap() {
  const res = state.pushEvidenceGapsToH23()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleAutoMark() {
  const n = state.autoMarkAnomalies()
  if (n > 0) ElMessage.success(`已标记 ${n} 行异常`)
  else ElMessage.info('无需新标记（已标记或无校验命中）')
}

function acceptanceDiffOf(row: { acceptanceAmount?: number; transferToFaAmount?: number }): number {
  const f = state.rowFlagsMap.value.get((row as any).rowId)
  if (f) return f.acceptanceDiff
  const acc = Number(row.acceptanceAmount) || 0
  const fa = Number(row.transferToFaAmount) || 0
  if (acc <= 0 || fa <= 0) return 0
  return Math.round((acc - fa) * 100) / 100
}

function flagTip(rowId: string): string {
  return state.rowFlagsMap.value.get(rowId)?.messages.join('；') || ''
}

function fmtDiff(val: number): string {
  if (!val || Math.abs(val) < 0.01) return '-'
  const s = val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return val > 0 ? `+${s}` : s
}

function handleSampling() {
  showSamplingDialog.value = true
}

const rawMethodologyPersist = buildChecklistDirectPersist({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const methodologyDirectPersist = rawMethodologyPersist
/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'H2',
  allResponses: toRef(props, 'allResponses') as never,
  persist: methodologyDirectPersist,
  isReadonly: computed(() => props.isReadonly === true),
})

function onSampleFilled(payload: any) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  showSamplingDialog.value = false
  // 引擎 emit('filled', { samples, phase, fillMode, ... })；兼容旧数组形态
  const samples: any[] = Array.isArray(payload) ? payload : (payload?.samples ?? [])
  if (!samples.length) return
  for (const s of samples) {
    state.addRow()
    const lastRow = state.rows.value[state.rows.value.length - 1]
    if (lastRow) {
      // 减少=贷方(资产1604)；SampledVoucher 字段 creditAmount/voucherDate/voucherNo/summary
      const amt = Number(s.creditAmount ?? s.amount ?? s.debitAmount) || 0
      if (s.summary || s.description) lastRow.name = s.summary || s.description
      const d = s.voucherDate ?? s.date
      if (d) lastRow.decreaseDate = d
      if (s.voucherNo || s.voucher_no) lastRow.voucherNo = s.voucherNo || s.voucher_no
      // 默认记入转入固定资产；用户可改到其他减少
      lastRow.transferToFaAmount = amt
      lastRow.decreaseType = '转入固定资产'
      lastRow.samplingStatus = '待检查'
    }
  }
  state.fillSamplingResults(
    samples.map((_s, i) => ({
      rowId: state.rows.value[state.rows.value.length - samples.length + i]?.rowId ?? '',
      status: '待检查',
    })),
  )
}

function handleAddRow() {
  state.addRow()
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function rowClassName({ row }: { row: any }) {
  const f = state.rowFlagsMap.value.get(row.rowId)
  if (row.isAbnormal === '是' || row.auditConclusion === '需调整' || f?.hasAcceptanceDiff) return 'row-anomaly'
  if (row.isProvisional === '是' || f?.missingApproval || f?.missingStamps) return 'row-provisional'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-decrease-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.check-alert { margin-bottom: 8px; }
.obj-title { font-weight: 600; }
.obj-list { margin: 4px 0 0; padding-left: 20px; line-height: 1.6; }
.tab-toolbar {
  display: flex; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.pop-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.src-tag { margin-left: 2px; }
.specific-sample {
  display: flex; align-items: center; gap: 8px; margin-top: 10px;
}
.param-label { font-weight: 500; white-space: nowrap; }
.test-content-hint {
  margin-bottom: 12px; padding: 8px 12px;
  background: var(--el-fill-color-lighter); border-radius: 4px; font-size: 12px;
}
.test-content-hint p { margin: 0 0 4px; font-weight: 500; }
.test-content-hint ol { margin: 0; padding-left: 18px; line-height: 1.55; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.diff-warn { color: var(--el-color-warning); font-weight: 600; }
.flag-tip {
  color: var(--el-color-warning-dark-2); font-size: 12px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.summary-block {
  padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px;
}
.summary-line { font-size: var(--wp-font-size, 13px); line-height: 1.8; }
.sep { margin-left: 16px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.warn-coverage { color: var(--el-color-warning); font-weight: 600; }
.add-row-bar { margin-top: 12px; }
.edit-tips {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 10px 12px; background: var(--el-fill-color-lighter); border-radius: 4px;
  border-left: 3px solid var(--el-color-primary-light-5);
}
.edit-tips summary { cursor: pointer; font-weight: 600; color: var(--el-color-primary); }
.edit-tips ol { padding-left: 20px; margin: 8px 0 0; line-height: 1.65; }
:deep(.row-anomaly) { background-color: var(--el-color-danger-light-9) !important; }
:deep(.row-provisional) { background-color: var(--el-color-warning-light-9) !important; }
</style>
