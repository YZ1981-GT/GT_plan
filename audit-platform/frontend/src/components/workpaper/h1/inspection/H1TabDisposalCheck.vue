<template>
  <div class="h1-tab-disposal-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 一、审计目标（对齐致同模板） -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>核实已记录的固定资产减少确已发生（存在/发生认定）</li>
        <li>核实所有应记录的固定资产减少均已入账（完整性）</li>
        <li>核实原值、累计折旧、减值、清理净损益计算正确且披露恰当（准确性/计价/列报）</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-8" :context-project-id="projectId" />
      <el-tag size="small" type="info">样本 {{ state.rows.value.length }} 项</el-tag>
      <el-tag
        v-if="state.summary.value.anomalyCount > 0"
        size="small"
        type="danger"
      >异常 {{ state.summary.value.anomalyCount }} 项</el-tag>
      <el-tag
        size="small"
        :type="coverageTagType"
      >检查比例 {{ state.summary.value.coverageRate.toFixed(2) }}%</el-tag>
    </div>

    <!-- 二、测试原因 + 测试内容说明 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title"><span>二、测试</span></div>
      </template>
      <div class="test-reason-row">
        <span class="reason-label">测试原因：</span>
        <el-checkbox-group
          :model-value="state.testReasons.value"
          :disabled="isReadonly"
          @change="onTestReasonsChange"
        >
          <el-checkbox label="largeAmount">大额</el-checkbox>
          <el-checkbox label="relatedParty">关联方</el-checkbox>
          <el-checkbox label="frequentLarge">大额交易频繁</el-checkbox>
          <el-checkbox label="abnormal">异常</el-checkbox>
          <el-checkbox label="other">其他</el-checkbox>
        </el-checkbox-group>
        <el-input
          v-if="state.testReasons.value.includes('other')"
          v-model="otherReasonText"
          size="small"
          placeholder="其他原因说明"
          style="width:200px;margin-left:8px"
          :disabled="isReadonly"
          @change="persistOtherReason"
        />
      </div>
      <div class="test-content-hint">
        <p>测试内容说明：</p>
        <ol>
          <li>原始凭证是否齐全</li>
          <li>记账凭证与原始凭证是否相符</li>
          <li>账务处理是否正确（原值−累计折旧−减值=净值；清理净损益=清理收入−净值−清理费用）</li>
          <li>是否记录于恰当会计期间</li>
          <li>关键证据（申报审批、合同、发票）要素是否完整；关联方出售须关注评估定价</li>
        </ol>
      </div>
    </el-card>

    <!-- 抽样参数 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>抽样参数</span>
          <div class="title-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(state.linkedDecrease.value.amount > 0)"
              @click="handleSyncPopulation"
            >
              从 {{ state.linkedDecrease.value.source || 'H1-2/H1-1' }} 带入本期减少
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              🎲 抽凭引擎
            </el-button>
          </div>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="本期减少合计（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.samplingParams.value.totalPopulation"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateSamplingParams({ totalPopulation: v ?? 0 })"
            />
            <span v-else class="amount-cell">{{ fmtAmt(state.samplingParams.value.totalPopulation) }}</span>
            <el-tag v-if="state.linkedDecrease.value.source" size="small" type="info" class="src-tag">
              源 {{ state.linkedDecrease.value.source }}: {{ fmtAmt(state.linkedDecrease.value.amount) }}
            </el-tag>
            <el-tag v-if="state.populationManual.value" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="样本量">
          {{ state.summary.value.checkedCount }}
        </el-descriptions-item>
        <el-descriptions-item label="检查比例">
          <span :class="{ 'warn-coverage': state.summary.value.coverageRate < 20 && state.samplingParams.value.totalPopulation > 0 }">
            {{ state.summary.value.coverageRate.toFixed(2) }}%
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法">
          <el-select
            v-if="!isReadonly"
            :model-value="state.samplingParams.value.samplingMethod"
            size="small"
            style="width:140px"
            @change="(v: string) => state.updateSamplingParams({ samplingMethod: v })"
          >
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随机抽样" value="随机抽样" />
            <el-option label="判断抽样" value="判断抽样" />
          </el-select>
          <span v-else>{{ state.samplingParams.value.samplingMethod || '待确定' }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="populationDrift"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`总体与 ${state.linkedDecrease.value.source}（${fmtAmt(state.linkedDecrease.value.amount)}）不一致，可重新带入或保留手工数。`"
      />
    </el-card>

    <!-- 减少检查明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H1-8 减少检查明细（{{ state.rows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-8')">💬 复核</el-button>
          </div>
        </div>
      </template>

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

        <!-- 基础信息 -->
        <el-table-column label="基础信息" align="center">
          <el-table-column prop="category" label="类别" width="80">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.category" size="small"
                @change="state.updateCell(row.rowId, 'category', row.category)" />
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="assetNo" label="资产编号" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.assetNo" size="small"
                @change="state.updateCell(row.rowId, 'assetNo', row.assetNo)" />
              <span v-else>{{ row.assetNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="资产名称" min-width="110" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.name" size="small"
                @change="state.updateCell(row.rowId, 'name', row.name)" />
              <span v-else>{{ row.name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="disposalMethod" label="减少方式" width="88">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.disposalMethod" size="small" style="width:76px"
                @change="state.updateCell(row.rowId, 'disposalMethod', $event)">
                <el-option label="出售" value="出售" />
                <el-option label="报废" value="报废" />
                <el-option label="损毁" value="损毁" />
                <el-option label="捐赠" value="捐赠" />
                <el-option label="盘亏" value="盘亏" />
                <el-option label="其他" value="其他" />
              </el-select>
              <span v-else>{{ row.disposalMethod || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="disposalDate" label="减少日期" width="118">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.disposalDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:108px"
                @change="state.updateCell(row.rowId, 'disposalDate', $event)"
              />
              <span v-else>{{ row.disposalDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="voucherNo" label="凭证号" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
                @change="state.updateCell(row.rowId, 'voucherNo', row.voucherNo)" />
              <span v-else>{{ row.voucherNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="counterpartAccount" label="对方科目" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.counterpartAccount" size="small"
                placeholder="如1606"
                @change="state.updateCell(row.rowId, 'counterpartAccount', row.counterpartAccount)" />
              <span v-else>{{ row.counterpartAccount || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 转入清理 -->
        <el-table-column label="转入清理的固定资产" align="center">
          <el-table-column prop="originalCost" label="原值" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.originalCost" size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'originalCost', row.originalCost)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="accDep" label="累计折旧" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.accDep" size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'accDep', row.accDep)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.accDep) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="减值准备" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.impairment" size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'impairment', row.impairment)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="净值=原值−累计折旧−减值准备">{{ fmtAmt(row.netValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 清理净收入 / 损益 -->
        <el-table-column label="清理净收入与损益" align="center">
          <el-table-column prop="disposalCost" label="清理费用" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.disposalCost" size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'disposalCost', row.disposalCost)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.disposalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="disposalIncome" label="清理收入" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                v-model="row.disposalIncome"
                size="small"
                class="amt-input"
                :class="{ 'warn-input': state.needsScrapResidualWarning(row) }"
                @change="state.updateCell(row.rowId, 'disposalIncome', row.disposalIncome)"
              />
              <span
                v-else
                :class="['amount-cell', { 'warn-text': state.needsScrapResidualWarning(row) }]"
              >{{ fmtAmt(row.disposalIncome) }}</span>
              <div v-if="state.needsScrapResidualWarning(row)" class="scrap-hint" title="报废/损毁无清理收入且净值>0">
                ⚠ 核实残值/赔款
              </div>
            </template>
          </el-table-column>
          <el-table-column label="清理净损益" width="110" align="right">
            <template #default="{ row }">
              <span
                :class="['formula-cell', { 'error-amount': row.disposalGainLoss < 0 }]"
                title="清理净损益=清理收入−净值−清理费用"
              >
                {{ fmtAmt(row.disposalGainLoss) }}
              </span>
              <GtIndexChip
                v-if="row.disposalMethod === '出售' || row.disposalIncome > 0"
                value="wp:H10"
                class="h10-chip"
                :context-project-id="projectId"
                context="处置损益 H10"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 关键证据 -->
        <el-table-column label="关键证据核对" align="center">
          <el-table-column prop="applicationRef" label="申报单号" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.applicationRef" size="small"
                @change="state.updateCell(row.rowId, 'applicationRef', row.applicationRef)" />
              <span v-else>{{ row.applicationRef || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="isApproved" label="恰当审批" width="80" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.isApproved" size="small" style="width:64px"
                @change="state.updateCell(row.rowId, 'isApproved', $event)">
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <span v-else>{{ row.isApproved === 'Y' ? '是' : row.isApproved === 'N' ? '否' : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="contractRef" label="合同编号" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.contractRef" size="small"
                @change="state.updateCell(row.rowId, 'contractRef', row.contractRef)" />
              <span v-else>{{ row.contractRef || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="contractParty" label="合同对方" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.contractParty" size="small"
                @change="state.updateCell(row.rowId, 'contractParty', row.contractParty)" />
              <span v-else>{{ row.contractParty || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="invoiceRef" label="发票号" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.invoiceRef" size="small"
                @change="state.updateCell(row.rowId, 'invoiceRef', row.invoiceRef)" />
              <span v-else>{{ row.invoiceRef || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="evaluationReport" label="评估报告" width="90">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.evaluationReport"
                size="small"
                :class="{ 'warn-input': state.needsEvalWarning(row) }"
                :placeholder="state.needsEvalWarning(row) ? '关联方出售需评估' : ''"
                @change="state.updateCell(row.rowId, 'evaluationReport', row.evaluationReport)"
              />
              <span v-else :class="{ 'warn-text': state.needsEvalWarning(row) }">
                {{ row.evaluationReport || (state.needsEvalWarning(row) ? '⚠缺评估' : '-') }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="关联方" width="72" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRelatedParty" size="small" style="width:58px"
              @change="state.updateCell(row.rowId, 'isRelatedParty', $event)">
              <el-option label="否" value="N" />
              <el-option label="是" value="Y" />
            </el-select>
            <span v-else>{{ row.isRelatedParty === 'Y' ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relatedPartyName" label="关联方名称" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isRelatedParty === 'Y'"
              v-model="row.relatedPartyName"
              size="small"
              @change="state.updateCell(row.rowId, 'relatedPartyName', row.relatedPartyName)"
            />
            <span v-else>{{ row.isRelatedParty === 'Y' ? (row.relatedPartyName || '-') : '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="isAbnormal" label="是否异常" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isAbnormal" size="small" style="width:64px"
              @change="state.updateCell(row.rowId, 'isAbnormal', $event)">
              <el-option label="否" value="N" />
              <el-option label="是" value="Y" />
            </el-select>
            <el-tag v-else :type="row.isAbnormal === 'Y' ? 'danger' : 'success'" size="small">
              {{ row.isAbnormal === 'Y' ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="checkResult" label="结果" width="72" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkResult" size="small" style="width:60px"
              @change="state.updateCell(row.rowId, 'checkResult', $event)">
              <el-option label="OK" value="OK" />
              <el-option label="异常" value="ERR" />
            </el-select>
            <el-tag v-else :type="row.checkResult === 'OK' ? 'success' : row.checkResult === 'ERR' ? 'danger' : 'info'" size="small">
              {{ row.checkResult || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="indexRef" label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
              @change="state.updateCell(row.rowId, 'indexRef', row.indexRef)" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="48" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="state.updateCell(row.rowId, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="48" fixed="right" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>样本原值合计: <b class="amount-cell">{{ fmtAmt(state.summary.value.disposalAmountTotal) }}</b></span>
        <span>净值合计: <b class="amount-cell">{{ fmtAmt(state.summary.value.netValueTotal) }}</b></span>
        <span>清理收入合计: <b class="amount-cell">{{ fmtAmt(state.incomeTotal.value) }}</b></span>
        <span>清理净损益合计: <b :class="['amount-cell', { 'error-amount': state.gainLossTotal.value < 0 }]">{{ fmtAmt(state.gainLossTotal.value) }}</b></span>
        <span>
          本期减少合计: <b class="amount-cell">{{ fmtAmt(state.samplingParams.value.totalPopulation) }}</b>
        </span>
        <span :class="{ 'warn-coverage': state.summary.value.coverageRate < 20 && state.samplingParams.value.totalPopulation > 0 }">
          检查比例: <b>{{ state.summary.value.coverageRate.toFixed(2) }}%</b>
        </span>
        <GtIndexChip value="wp:H10" :context-project-id="projectId" context="处置损益 H10" />
      </div>
      <el-alert
        v-if="state.summary.value.coverageRate < 20 && state.samplingParams.value.totalPopulation > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        title="检查比例偏低：请扩大样本量，或在审计说明中解释原因。"
      />
      <el-alert
        v-if="state.summary.value.scrapNoIncomeCount > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.scrapNoIncomeCount} 笔报废/损毁净值>0但清理收入为0：请核实残值回收、废料变卖或保险赔款是否漏记。`"
      />
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>三、审计说明</span>
          <el-button
            size="small"
            type="primary"
            link
            :loading="aiLoading"
            :disabled="isReadonly"
            @click="handleAiDraft"
          >
            <el-icon><MagicStick /></el-icon> AI 生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：抽样方法与检查比例、审批与凭证核对、清理损益核算、报废残值、与 H6/H10 勾稽；检查比例偏低时须说明原因。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="publishDisposalCompleted">
              📤 发布联动 H6/H10
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="基于检查结果，就固定资产减少的发生、完整、计价认定发表结论……"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>勾稽：净值 = 原值 − 累计折旧 − 减值；清理净损益 = 清理收入 − 净值 − 清理费用</li>
        <li>本期减少合计优先从 H1-2「原值本期减少」带入，无则回退 H1-1 原值贷方合计</li>
        <li>检查比例 = 样本原值合计 ÷ 本期减少合计；偏低时扩大样本或说明原因</li>
        <li>📎 上传合同/发票 OCR 填入；关联方出售须评估定价；报废无收入须核实残值/赔款</li>
        <li>处置结果通过 EventBus 联动 H10；对方科目多为 1606 固定资产清理（H6）</li>
      </ul>
    </details>

    <el-dialog
      v-model="showSamplingDialog"
      title="⚡ 抽凭引擎（科目 1601 固定资产-减少）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="1601"
        phase="final"
        :year="samplingYear"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import {
  useH1DisposalCheck,
  type DisposalTestReason,
  type DisposalRow,
} from '../../composables/useH1DisposalCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
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
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const auditNoteText = ref('')
const otherReasonText = ref('')
const aiLoading = ref(false)
const NOTE_KEY = 'H1-8-audit-note'
const CONCLUSION_KEY = 'H1-8-audit-conclusion'

function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
})

const showSamplingDialog = ref(false)

const state = useH1DisposalCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    onSave: (itemId, value) => saveResponse(itemId, value),
    onPublishEvent(event: string, payload: any) {
      if (event === 'h1:disposal-completed') {
        // 仅 eventBus：crossWpEventBridge 会转发到 window，避免 H6 双次入库
        eventBus.emit('h1:disposal-completed' as any, payload)
      }
    },
  },
)

watch(
  () => state.testReasonOther.value,
  (v) => { otherReasonText.value = v },
  { immediate: true },
)

const coverageTagType = computed(() => {
  const rate = state.summary.value.coverageRate
  const hasPop = state.samplingParams.value.totalPopulation > 0
  if (!hasPop) return 'info'
  if (rate < 20) return 'danger'
  if (rate < 50) return 'warning'
  return 'success'
})

/** 手工总体与 H1-1/H1-2 源金额不一致 */
const populationDrift = computed(() => {
  const linked = state.linkedDecrease.value
  const pop = state.samplingParams.value.totalPopulation
  if (!(linked.amount > 0) || !(pop > 0)) return false
  return Math.abs(linked.amount - pop) > 0.5
})

function onTestReasonsChange(vals: DisposalTestReason[]) {
  state.updateTestReasons(vals, otherReasonText.value)
}

function persistOtherReason() {
  state.updateTestReasons(state.testReasons.value, otherReasonText.value)
}

function handleSyncPopulation() {
  const r = state.syncPopulationFromLinked(true)
  if (r.ok) {
    ElMessage.success(`已从 ${r.source} 带入本期减少合计 ${fmtAmt(r.amount)}`)
  } else {
    ElMessage.warning('H1-2 / H1-1 暂无本期减少金额，请先完成明细或审定表')
  }
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增减少检查项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  })
  if (name) state.addRow(name)
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
  wpCode: 'H1',
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
    state.addRow(s.summary || '处置项')
    const lastRow = state.rows.value[state.rows.value.length - 1]
    if (!lastRow) continue
    // 固定资产减少：原值转出在贷方；无贷方额时回退借方
    lastRow.originalCost = Math.abs(Number(s.creditAmount ?? s.debitAmount ?? 0) || 0)
    lastRow.voucherNo = s.voucherNo || ''
    lastRow.disposalDate = s.voucherDate || ''
    lastRow.counterpartAccount = s.counterpartAccount || ''
    lastRow.voucherSampleId = s.voucherNo || ''
    lastRow.isAbnormal = s.abnormal ? 'Y' : 'N'
    lastRow.checkResult = s.abnormal ? 'ERR' : ''
    lastRow.remark = s.selectionReason || s.remark || (s.isHighValue ? 'MUS高值必选' : '')
    state.updateCell(lastRow.rowId, 'originalCost', lastRow.originalCost)
  }
  ElMessage.success(`已回填 ${samples.length} 笔抽样凭证`)
}

/** 行级 OCR：上传 → contract-ocr → 确认 → merge */
async function handleOcr(row: DisposalRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = data?.extracted_fields || {}
      if (!Object.keys(fields).length) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段', '提示')
        return
      }
      const preview = Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(`识别结果：\n${preview}\n\n确认填入？`, 'OCR 识别结果', {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
      })
      state.applyOcrFields(row.rowId, fields)
      ElMessage.success('已填入 OCR 识别字段')
    } catch { /* 取消或请求失败 */ }
  }
  input.click()
}

/** AI 生成审计说明（section=disposal-note） */
async function handleAiDraft() {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/ai-generate`,
      {
        section: 'disposal-note',
        existingContent: auditNoteText.value || '',
        relatedContext: {
          sampleCount: state.summary.value.checkedCount,
          coverageRate: state.summary.value.coverageRate,
          totalPopulation: state.samplingParams.value.totalPopulation,
          linkedDecrease: state.linkedDecrease.value,
          incomeTotal: state.incomeTotal.value,
          gainLossTotal: state.gainLossTotal.value,
          anomalyCount: state.summary.value.anomalyCount,
          scrapNoIncomeCount: state.summary.value.scrapNoIncomeCount,
          testReasons: state.testReasons.value,
          rows: state.rows.value.slice(0, 20).map((r) => ({
            name: r.name,
            assetNo: r.assetNo,
            disposalMethod: r.disposalMethod,
            originalCost: r.originalCost,
            netValue: r.netValue,
            disposalIncome: r.disposalIncome,
            disposalGainLoss: r.disposalGainLoss,
            isRelatedParty: r.isRelatedParty,
            isAbnormal: r.isAbnormal,
            needsEval: state.needsEvalWarning(r),
            needsScrapResidual: state.needsScrapResidualWarning(r),
          })),
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    await ElMessageBox.confirm(
      text.slice(0, 800) + (text.length > 800 ? '…' : ''),
      'AI 起草确认',
      { confirmButtonText: '填入说明', cancelButtonText: '取消' },
    )
    auditNoteText.value = text
    saveAuditNote()
    ElMessage.success('已填入审计说明，可继续编辑')
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.warning('AI 起草失败，请手工填写')
    }
  } finally {
    aiLoading.value = false
  }
}

function publishDisposalCompleted() {
  state.publishDisposalCompleted?.()
}

function handleReview(id: string) { openReviewDialog(id) }

function rowClassName({ row }: { row: DisposalRow }) {
  if (row.isAbnormal === 'Y' || row.checkResult === 'ERR') return 'row-anomaly'
  if (state.needsEvalWarning(row)) return 'row-eval-warn'
  if (state.needsScrapResidualWarning(row)) return 'row-scrap-warn'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-disposal-check {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; }
.obj-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.6;
}
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.block-card { margin-bottom: 12px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.title-actions { display: flex; gap: 8px; }
.test-reason-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.reason-label { font-size: 12px; color: var(--el-text-color-secondary); margin-right: 4px; }
.test-content-hint {
  border-left: 3px solid var(--el-color-danger);
  background: #fff5f5;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-color-danger);
}
.test-content-hint p { margin: 0 0 4px; font-weight: 500; }
.test-content-hint ol { margin: 0; padding-left: 18px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.error-amount { color: var(--el-color-danger); }
.warn-coverage { color: var(--el-color-warning); font-weight: 600; }
.warn-input :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-warning) inset;
}
.warn-text { color: var(--el-color-warning); }
.amt-input { width: 100%; }
.pop-cell { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.src-tag { margin-left: 2px; }
.scrap-hint {
  font-size: 10px;
  color: var(--el-color-warning);
  line-height: 1.2;
  margin-top: 2px;
}
.h10-chip { margin-left: 4px; vertical-align: middle; }
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
}
.note-card { margin-top: 12px; }
.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-anomaly) { background: #fef0f0 !important; }
:deep(.row-eval-warn) { background: #fdf6ec !important; }
:deep(.row-scrap-warn) { background: #fdf6ec !important; }
</style>
