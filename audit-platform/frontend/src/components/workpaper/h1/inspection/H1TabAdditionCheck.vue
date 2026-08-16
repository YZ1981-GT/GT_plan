<template>
  <div class="h1-tab-addition-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 一、审计目标（对齐致同模板） -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>确定资产负债表日记录的固定资产是否存在（存在认定）</li>
        <li>所有应记录的固定资产是否均已记录（完整性；本表含证→账追查）</li>
        <li>确定记录的固定资产是否由被审计单位拥有或控制（权利与义务）</li>
        <li>确定固定资产以恰当金额列示，减值计提是否恰当（计价与分摊）</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-7" :context-project-id="projectId" />
      <el-tag size="small" type="info">样本 {{ state.rows.value.length }} 项</el-tag>
      <el-tag
        v-if="state.summary.value.anomalyCount > 0"
        size="small"
        type="danger"
      >异常 {{ state.summary.value.anomalyCount }} 项</el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ state.summary.value.coverageRate.toFixed(2) }}%
      </el-tag>
    </div>

    <!-- 二、样本选取 + 测试内容说明 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title"><span>二、样本选取标准与规模</span></div>
      </template>
      <div class="test-reason-row">
        <span class="reason-label">特定样本（重点选取）：</span>
        <el-checkbox-group
          :model-value="state.testReasons.value"
          :disabled="isReadonly"
          @change="onTestReasonsChange"
        >
          <el-checkbox label="largeAmount">大额</el-checkbox>
          <el-checkbox label="relatedParty">关联方</el-checkbox>
          <el-checkbox label="abnormal">异常</el-checkbox>
          <el-checkbox label="newCategory">新增类别</el-checkbox>
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
        <p>测试内容说明（抽查核对）：</p>
        <ol>
          <li>原始凭证是否齐全</li>
          <li>记账凭证与原始凭证是否相符</li>
          <li>账务处理是否正确（含资本化条件、入账科目）</li>
          <li>是否记录于恰当会计期间（截止测试）</li>
          <li>关键证据（验收单、合同/订单、采购发票）要素是否完整；金额与账面原值勾稽</li>
        </ol>
        <p class="hint-note">
          账→证抽查支撑存在与计价；下方「证→账追查」从表外源文件追查至账面，支撑完整性认定。
        </p>
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
              :disabled="isReadonly || !(state.linkedIncrease.value.amount > 0)"
              @click="handleSyncPopulation"
            >
              从 {{ state.linkedIncrease.value.source || 'H1-2/H1-1' }} 带入本期增加
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              🎲 抽凭引擎
            </el-button>
          </div>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="本期增加合计（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.samplingParams.value.totalPopulation"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateSamplingParams({ totalPopulation: v ?? 0 })"
            />
            <span v-else class="amount-cell">{{ fmtAmt(state.samplingParams.value.totalPopulation) }}</span>
            <el-tag v-if="state.linkedIncrease.value.source" size="small" type="info" class="src-tag">
              源 {{ state.linkedIncrease.value.source }}: {{ fmtAmt(state.linkedIncrease.value.amount) }}
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
            <el-option label="系统抽样" value="系统抽样" />
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
        :title="`总体与 ${state.linkedIncrease.value.source}（${fmtAmt(state.linkedIncrease.value.amount)}）不一致，可重新带入或保留手工数。`"
      />
    </el-card>

    <!-- 在建工程转入 ↔ H2 转固勾稽（含完整性：H2 已转固但 H1 漏记场景） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>在建工程转入 ↔ H2 转固勾稽</span>
          <div class="title-actions">
            <el-button size="small" :loading="isPullingH2" :disabled="!projectId" @click="handleReconcileH2">
              勾稽 H2 转固
            </el-button>
            <GtIndexChip value="wp:H2-2" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="H1 在建转入增加合计">
          <span class="amount-cell">{{ fmtAmt(cipReconcile.h1CipTransferIn) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="H2 转入固定资产合计">
          <span v-if="h2Pull" class="amount-cell">{{ fmtAmt(cipReconcile.h2TransferToFa) }}</span>
          <span v-else class="muted">点「勾稽 H2 转固」取数</span>
        </el-descriptions-item>
        <el-descriptions-item label="差异">
          <span :class="['amount-cell', { 'error-amount': h2Pull && !cipReconcile.matched }]">
            {{ h2Pull ? fmtAmt(cipReconcile.diff) : '—' }}
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="h2Pull && h2Pull.status !== 'ok'"
        type="info"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="h2Pull.message"
      />
      <el-alert
        v-else-if="h2Pull && !cipReconcile.matched"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`H1 在建转入(${fmtAmt(cipReconcile.h1CipTransferIn)}) 与 H2 转固(${fmtAmt(cipReconcile.h2TransferToFa)}) 不一致，差异 ${fmtAmt(cipReconcile.diff)}，请查明（未达可使用状态误转 / 漏转 / 分期转固）。`"
      />
      <el-alert
        v-else-if="h2Pull && cipReconcile.matched"
        type="success"
        :closable="false"
        show-icon
        style="margin-top:8px"
        title="H1 在建工程转入与 H2 转固合计勾稽一致。"
      />

      <!-- 购建固定资产支付现金 → 现金流量表勾稽（提示：差额=应付/预付/票据/在建挂账） -->
      <div class="cfs-xref">
        <span>购建固定资产支付现金合计（本期）：<b class="amount-cell">{{ fmtAmt(state.cashPaidTotal.value) }}</b></span>
        <el-tooltip
          content="应与现金流量表『购建固定资产、无形资产和其他长期资产支付的现金』勾稽；差额=应付账款/预付款/应付票据/在建工程等挂账未付部分。"
          placement="top"
        >
          <span class="cfs-hint">↔ 现金流量表投资活动 <span class="hint-dot">?</span></span>
        </el-tooltip>
      </div>
    </el-card>

    <!-- 三、测试过程：增加检查明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、测试过程 — 增加检查明细（{{ state.rows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
            <el-button
              size="small"
              :disabled="isReadonly || !state.rows.value.length"
              @click="handlePushH12"
            >
              推送折旧起算 → H1-12
            </el-button>
            <el-button size="small" type="default" link @click="navigateTo('H1-12')">
              <GtIndexChip value="wp:H1-12" :context-project-id="projectId" />
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-7')">💬 复核</el-button>
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

        <!-- 账面基础信息 -->
        <el-table-column label="账面记录" align="center">
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
          <el-table-column prop="additionMethod" label="增加方式" width="110">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.additionMethod" size="small" style="width:98px"
                @change="state.updateCell(row.rowId, 'additionMethod', $event)">
                <el-option label="外购" value="外购" />
                <el-option label="在建工程转入" value="在建工程转入" />
                <el-option label="更新改造" value="更新改造" />
                <el-option label="盘盈" value="盘盈" />
                <el-option label="融资租赁" value="融资租赁" />
                <el-option label="投资者投入" value="投资者投入" />
                <el-option label="非货币交换" value="非货币交换" />
                <el-option label="债务重组" value="债务重组" />
                <el-option label="企业合并" value="企业合并" />
                <el-option label="其他" value="其他" />
              </el-select>
              <span v-else>{{ row.additionMethod || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="acquisitionDate" label="增加日期" width="118">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.acquisitionDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:108px"
                @change="state.updateCell(row.rowId, 'acquisitionDate', $event)"
              />
              <span v-else>{{ row.acquisitionDate || '-' }}</span>
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
                placeholder="如1604"
                @change="state.updateCell(row.rowId, 'counterpartAccount', row.counterpartAccount)" />
              <span v-else>{{ row.counterpartAccount || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 账面金额 -->
        <el-table-column label="账面金额" align="center">
          <el-table-column prop="originalCost" label="原值" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                v-model="row.originalCost"
                size="small"
                class="amt-input"
                :class="{ 'warn-input': state.needsAmountMismatchWarning(row) }"
                @change="state.updateCell(row.rowId, 'originalCost', row.originalCost)"
              />
              <span
                v-else
                :class="['amount-cell', { 'warn-text': state.needsAmountMismatchWarning(row) }]"
              >{{ fmtAmt(row.originalCost) }}</span>
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

        <!-- 关键证据 -->
        <el-table-column label="关键证据核对" align="center">
          <el-table-column prop="acceptanceRef" label="验收单号" width="90">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.acceptanceRef"
                size="small"
                :class="{ 'warn-input': state.needsCipAcceptanceWarning(row) }"
                :placeholder="state.needsCipAcceptanceWarning(row) ? '在建转入需验收' : ''"
                @change="state.updateCell(row.rowId, 'acceptanceRef', row.acceptanceRef)"
              />
              <span v-else :class="{ 'warn-text': state.needsCipAcceptanceWarning(row) }">
                {{ row.acceptanceRef || (state.needsCipAcceptanceWarning(row) ? '⚠缺验收' : '-') }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="acceptanceDate" label="验收日期" width="118">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.acceptanceDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:108px"
                @change="state.updateCell(row.rowId, 'acceptanceDate', $event)"
              />
              <span v-else>{{ row.acceptanceDate || '-' }}</span>
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
          <el-table-column prop="contractAmount" label="合同金额" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.contractAmount" size="small"
                class="amt-input"
                @change="state.updateCell(row.rowId, 'contractAmount', row.contractAmount)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.contractAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="invoiceRef" label="发票号" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.invoiceRef" size="small"
                @change="state.updateCell(row.rowId, 'invoiceRef', row.invoiceRef)" />
              <span v-else>{{ row.invoiceRef || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="invoiceParty" label="发票对方" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.invoiceParty" size="small"
                @change="state.updateCell(row.rowId, 'invoiceParty', row.invoiceParty)" />
              <span v-else>{{ row.invoiceParty || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="invoiceAmount" label="发票金额" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                v-model="row.invoiceAmount"
                size="small"
                class="amt-input"
                :class="{ 'warn-input': state.needsAmountMismatchWarning(row) }"
                @change="state.updateCell(row.rowId, 'invoiceAmount', row.invoiceAmount)"
              />
              <span
                v-else
                :class="['amount-cell', { 'warn-text': state.needsAmountMismatchWarning(row) }]"
              >{{ fmtAmt(row.invoiceAmount) }}</span>
              <div v-if="state.needsAmountMismatchWarning(row)" class="mismatch-hint" title="账面原值与发票/合同金额不符">
                ⚠ 金额不符
              </div>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 资本化 / 折旧起算 -->
        <el-table-column label="资本化与折旧" align="center">
          <el-table-column prop="expenseOrCapital" label="费用/资本化" width="100">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.expenseOrCapital" size="small" style="width:88px"
                @change="state.updateCell(row.rowId, 'expenseOrCapital', $event)">
                <el-option label="资本化" value="资本化" />
                <el-option label="费用化" value="费用化" />
                <el-option label="部分资本化" value="部分资本化" />
              </el-select>
              <span v-else>{{ row.expenseOrCapital || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="depStartDate" label="折旧起算日" width="118">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.depStartDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:108px"
                :class="{ 'warn-input': state.needsProvisionalDepWarning(row) }"
                @change="state.updateCell(row.rowId, 'depStartDate', $event)"
              />
              <span v-else :class="{ 'warn-text': state.needsProvisionalDepWarning(row) }">
                {{ row.depStartDate || (state.needsProvisionalDepWarning(row) ? '⚠缺起算' : '-') }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="isProvisional" label="暂估" width="72" align="center">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" v-model="row.isProvisional" size="small" style="width:58px"
                @change="state.updateCell(row.rowId, 'isProvisional', $event)">
                <el-option label="否" value="N" />
                <el-option label="是" value="Y" />
              </el-select>
              <span v-else :class="{ 'warn-text': row.isProvisional === 'Y' }">
                {{ row.isProvisional === 'Y' ? '是' : '否' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="专项清单" width="100" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                link
                :type="state.needsChecklistIncompleteWarning(row) ? 'warning' : 'primary'"
                :disabled="!row.additionMethod"
                @click="openChecklist(row)"
              >
                {{ checklistLabel(row) }}
              </el-button>
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
        <span>样本原值合计: <b class="amount-cell">{{ fmtAmt(state.summary.value.checkedAmount) }}</b></span>
        <span>净值合计: <b class="amount-cell">{{ fmtAmt(state.summary.value.netValueTotal) }}</b></span>
        <span>
          本期增加合计: <b class="amount-cell">{{ fmtAmt(state.samplingParams.value.totalPopulation) }}</b>
        </span>
        <span :class="{ 'warn-coverage': state.summary.value.coverageRate < 20 && state.samplingParams.value.totalPopulation > 0 }">
          检查比例: <b>{{ state.summary.value.coverageRate.toFixed(2) }}%</b>
        </span>
        <span>异常: <b :class="{ 'error-amount': state.summary.value.anomalyCount > 0 }">{{ state.summary.value.anomalyCount }}</b> 项</span>
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
        v-if="state.summary.value.amountMismatchCount > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.amountMismatchCount} 笔账面原值与发票/合同金额不符：请核实计价、价外费用或暂估差异。`"
      />
      <el-alert
        v-if="state.summary.value.cipNoAcceptanceCount > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.cipNoAcceptanceCount} 笔在建转入缺验收单：请检查竣工决算、验收移交及达到预定可使用状态依据。`"
      />
      <el-alert
        v-if="state.summary.value.provisionalNoDepStartCount > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.provisionalNoDepStartCount} 笔暂估入账缺折旧起算日：请填写起算日并推送至 H1-12。`"
      />
      <el-alert
        v-if="state.summary.value.checklistIncompleteCount > 0"
        type="info"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.checklistIncompleteCount} 笔专项清单未完成：点击「专项清单」按增加方式勾选。`"
      />
    </el-card>

    <!-- 三-B、证→账追查（完整性） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三-B、证→账追查明细（完整性 · {{ state.traceRows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSeedTrace">
              从账→证样本生成
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddTrace">
              + 追查行
            </el-button>
          </div>
        </div>
      </template>
      <p class="trace-hint">
        从验收单/合同/发票等源文件追查至固定资产账：是否入账、金额是否一致。未入账或差额须跟进。
      </p>
      <el-table
        :data="state.traceRows.value"
        border
        stripe
        size="small"
        max-height="360"
        class="check-table"
        :row-class-name="traceRowClassName"
      >
        <el-table-column type="index" label="序号" width="48" align="center" />
        <el-table-column prop="sourceType" label="源文件类型" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.sourceType" size="small" style="width:88px"
              @change="state.updateTraceCell(row.rowId, 'sourceType', $event)">
              <el-option label="发票" value="发票" />
              <el-option label="合同" value="合同" />
              <el-option label="验收单" value="验收单" />
              <el-option label="发运单" value="发运单" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.sourceType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceRef" label="源文件编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.sourceRef" size="small"
              @change="state.updateTraceCell(row.rowId, 'sourceRef', row.sourceRef)" />
            <span v-else>{{ row.sourceRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceDate" label="源文件日期" width="118">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.sourceDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:108px"
              @change="state.updateTraceCell(row.rowId, 'sourceDate', $event)"
            />
            <span v-else>{{ row.sourceDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceParty" label="对方名称" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.sourceParty" size="small"
              @change="state.updateTraceCell(row.rowId, 'sourceParty', row.sourceParty)" />
            <span v-else>{{ row.sourceParty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceAmount" label="源文件金额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.sourceAmount" size="small"
              class="amt-input"
              @change="state.updateTraceCell(row.rowId, 'sourceAmount', row.sourceAmount)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.sourceAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recordedInBooks" label="已入账" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.recordedInBooks" size="small" style="width:64px"
              @change="state.updateTraceCell(row.rowId, 'recordedInBooks', $event)">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else :type="row.recordedInBooks === 'N' ? 'danger' : 'success'" size="small">
              {{ row.recordedInBooks === 'Y' ? '是' : row.recordedInBooks === 'N' ? '否' : '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="bookVoucherNo" label="账面凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.bookVoucherNo" size="small"
              @change="state.updateTraceCell(row.rowId, 'bookVoucherNo', row.bookVoucherNo)" />
            <span v-else>{{ row.bookVoucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAssetName" label="账面资产" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.bookAssetName" size="small"
              @change="state.updateTraceCell(row.rowId, 'bookAssetName', row.bookAssetName)" />
            <span v-else>{{ row.bookAssetName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAmount" label="账面金额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.bookAmount" size="small"
              class="amt-input"
              @change="state.updateTraceCell(row.rowId, 'bookAmount', row.bookAmount)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差额" width="100" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'error-amount': Math.abs(row.amountDiff) > 1 }]"
              title="差额=源文件金额−账面金额"
            >{{ fmtAmt(row.amountDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="checkResult" label="结果" width="72" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkResult" size="small" style="width:60px"
              @change="state.updateTraceCell(row.rowId, 'checkResult', $event)">
              <el-option label="OK" value="OK" />
              <el-option label="异常" value="ERR" />
            </el-select>
            <el-tag v-else :type="row.checkResult === 'OK' ? 'success' : row.checkResult === 'ERR' ? 'danger' : 'info'" size="small">
              {{ row.checkResult || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="state.updateTraceCell(row.rowId, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="48" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeTraceRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>追查笔数: <b>{{ state.summary.value.traceCount }}</b></span>
        <span>
          未入账/异常:
          <b :class="{ 'error-amount': state.summary.value.traceUnrecordedCount > 0 }">
            {{ state.summary.value.traceUnrecordedCount }}
          </b>
        </span>
      </div>
      <el-alert
        v-if="state.summary.value.traceUnrecordedCount > 0"
        type="danger"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.traceUnrecordedCount} 笔源文件未入账或追查异常：完整性认定存在风险，请扩大追查或调整。`"
      />
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计说明</span></template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：抽样方法与检查比例、凭证核对、资本化判断、金额勾稽差异、关联方购入；检查比例偏低时须说明原因。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>五、审计结论</span></template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="基于检查结果，就固定资产增加的存在、完整、权利与义务、计价认定发表结论……"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（按增加方式）</summary>
      <ul>
        <li>本表含账→证抽查与证→账追查；检查比例 = 样本原值合计 ÷ 本期增加合计</li>
        <li>本期增加合计优先从 H1-2「原值本期增加」带入，无则回退 H1-1 原值借方合计</li>
        <li>选择增加方式后，点击「专项清单」按来源勾选关键检查程序</li>
        <li>暂估转固须标注「暂估=是」并填写折旧起算日，可一键推送至 H1-12（或在 H1-12 跨表联动拉取）</li>
        <li>外购：合同/发票/发运；关注延期付款融资成分</li>
        <li>在建转入：竣工决算、验收移交、借款费用资本化、暂估与折旧起算</li>
        <li>关联方购入可带入 H1-18；舞弊风险关注虚高计价输送利益</li>
      </ul>
    </details>

    <!-- 专项清单抽屉 -->
    <el-drawer
      v-model="checklistVisible"
      :title="checklistTitle"
      size="420px"
      destroy-on-close
    >
      <template v-if="checklistRow">
        <p class="drawer-meta">
          {{ checklistRow.name || '未命名' }}
          <el-tag size="small" style="margin-left:8px">{{ checklistRow.additionMethod }}</el-tag>
        </p>
        <el-table :data="checklistItems" border size="small">
          <el-table-column prop="label" label="检查程序" min-width="220" />
          <el-table-column label="结论" width="120" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="checklistRow.methodChecks[row.key] || ''"
                size="small"
                style="width:100px"
                :disabled="isReadonly"
                @change="(v: string) => state.updateMethodCheck(checklistRow!.rowId, row.key, v)"
              >
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
                <el-option label="N/A" value="NA" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
        <p class="drawer-progress">
          完成度 {{ checklistProgress.done }}/{{ checklistProgress.total }}
        </p>
      </template>
    </el-drawer>

    <el-dialog
      v-model="showSamplingDialog"
      title="⚡ 抽凭引擎（科目 1601 固定资产-增加）"
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
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH1AdditionCheck,
  type AdditionTestReason,
  type AdditionRow,
  type TraceRow,
  getMethodChecklist,
  calcChecklistProgress,
} from '../../composables/useH1AdditionCheck'
import type { MethodChecklistItem } from '../../composables/h1AdditionMethodChecklist'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import {
  pullH2CipTransferForH1,
  buildCipH2Reconcile,
  type H2CipTransferPullResult,
} from '../../composables/h1CipH2Pull'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

/** 抽凭引擎所需审计年度：优先父级传入，回退当前年 */
const samplingYear = computed(() => props.year || new Date().getFullYear())

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const auditNoteText = ref('')
const otherReasonText = ref('')
const NOTE_KEY = 'H1-7-audit-note'
const CONCLUSION_KEY = 'H1-7-audit-conclusion'

function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
})

const showSamplingDialog = ref(false)
const checklistVisible = ref(false)
const checklistRow = ref<AdditionRow | null>(null)

const state = useH1AdditionCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    onSave: (itemId, value) => saveResponse(itemId, value),
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

const populationDrift = computed(() => {
  const linked = state.linkedIncrease.value
  const pop = state.samplingParams.value.totalPopulation
  if (!(linked.amount > 0) || !(pop > 0)) return false
  return Math.abs(linked.amount - pop) > 0.01
})

const checklistItems = computed<MethodChecklistItem[]>(() => {
  if (!checklistRow.value) return []
  return getMethodChecklist(checklistRow.value.additionMethod)
})

const checklistTitle = computed(() => {
  const m = checklistRow.value?.additionMethod || ''
  return m ? `专项检查清单 — ${m}` : '专项检查清单'
})

const checklistProgress = computed(() =>
  calcChecklistProgress(checklistRow.value?.methodChecks, checklistItems.value),
)

function openChecklist(row: AdditionRow) {
  checklistRow.value = row
  checklistVisible.value = true
}

function checklistLabel(row: AdditionRow): string {
  const items = getMethodChecklist(row.additionMethod)
  if (!items.length) return '—'
  const p = calcChecklistProgress(row.methodChecks, items)
  return `${p.done}/${p.total}`
}

function onTestReasonsChange(vals: AdditionTestReason[]) {
  state.updateTestReasons(vals, otherReasonText.value)
}

function persistOtherReason() {
  state.updateTestReasons(state.testReasons.value, otherReasonText.value)
}

function handleSyncPopulation() {
  const r = state.syncPopulationFromLinked(true)
  if (r.ok) {
    ElMessage.success(`已从 ${r.source} 带入本期增加合计 ${fmtAmt(r.amount)}`)
  } else {
    ElMessage.warning('未找到可带入的本期增加合计，请确认 H1-2 / H1-1 已填报')
  }
}

function handlePushH12() {
  const r = state.pushDepStartToH12()
  if (r.linked > 0) {
    ElMessage.success(`已推送 ${r.linked} 项折旧起算至 H1-12${r.notes.length ? '；' + r.notes.slice(0, 2).join('；') : ''}`)
  } else {
    ElMessage.warning(r.notes[0] || '未推送任何行')
  }
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增增加检查项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  })
  if (name) state.addRow(name)
}

function handleAddTrace() {
  state.addTraceRow()
}

function handleSeedTrace() {
  const n = state.seedTraceFromVouchRows()
  if (n > 0) ElMessage.success(`已从账→证样本生成 ${n} 条追查行`)
  else ElMessage.info('无可生成线索（需样本含发票/合同/验收单号）')
}

function handleSampling() {
  showSamplingDialog.value = true
}

// ─── 在建工程转入 ↔ H2 转固勾稽 ─────────────────────────────────────────────
const isPullingH2 = ref(false)
const h2Pull = ref<H2CipTransferPullResult | null>(null)
const cipReconcile = computed(() =>
  buildCipH2Reconcile(state.cipTransferInTotal.value, h2Pull.value?.transferToFaTotal ?? 0),
)

async function handleReconcileH2() {
  if (!props.projectId) return
  isPullingH2.value = true
  try {
    const r = await pullH2CipTransferForH1(props.projectId)
    h2Pull.value = r
    if (r.status === 'ok') ElMessage.success(r.message)
    else ElMessage.info(r.message)
  } catch {
    ElMessage.warning('勾稽 H2 转固失败')
  } finally {
    isPullingH2.value = false
  }
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
    state.addRow(s.summary || '抽样项')
    const lastRow = state.rows.value[state.rows.value.length - 1]
    if (!lastRow) continue
    // 固定资产增加在原值借方；无借方额时回退贷方
    lastRow.originalCost = Math.abs(Number(s.debitAmount ?? s.creditAmount ?? 0) || 0)
    lastRow.voucherNo = s.voucherNo || ''
    lastRow.acquisitionDate = s.voucherDate || ''
    lastRow.counterpartAccount = s.counterpartAccount || ''
    lastRow.voucherSampleId = s.voucherNo || ''
    lastRow.isAbnormal = s.abnormal ? 'Y' : 'N'
    lastRow.checkResult = s.abnormal ? 'ERR' : ''
    lastRow.remark = s.selectionReason || s.remark || (s.isHighValue ? 'MUS高值必选' : '')
    state.updateCell(lastRow.rowId, 'originalCost', lastRow.originalCost)
  }
  ElMessage.success(`已回填 ${samples.length} 笔抽样凭证`)
}

async function handleOcr(row: AdditionRow) {
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
        ElMessageBox.alert('OCR完成，未识别到可填充字段', '提示')
        return
      }
      const preview = Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(`识别结果：\n${preview}\n\n确认填入？`, 'OCR识别结果', {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
      })
      state.applyOcrFields(row.rowId, fields)
    } catch { /* user cancelled or request failed */ }
  }
  input.click()
}

function handleReview(id: string) { openReviewDialog(id) }
function navigateTo(sheet: string) { emit('navigate-sheet', sheet) }

function rowClassName({ row }: { row: AdditionRow }) {
  if (row.isAbnormal === 'Y' || row.checkResult === 'ERR') return 'row-anomaly'
  if (state.needsAmountMismatchWarning(row)) return 'row-mismatch-warn'
  if (state.needsCipAcceptanceWarning(row) || state.needsProvisionalDepWarning(row)) return 'row-cip-warn'
  return ''
}

function traceRowClassName({ row }: { row: TraceRow }) {
  if (row.recordedInBooks === 'N' || row.checkResult === 'ERR') return 'row-anomaly'
  if (Math.abs(row.amountDiff) > 1) return 'row-mismatch-warn'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-addition-check {
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
.hint-note {
  margin-top: 8px !important;
  font-weight: 400 !important;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.error-amount { color: var(--el-color-danger); }
.warn-coverage { color: var(--el-color-warning); font-weight: 600; }
.muted { color: var(--el-text-color-placeholder); font-size: 12px; }
.cfs-xref { margin-top: 10px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--el-text-color-regular); }
.cfs-hint { color: var(--el-text-color-secondary); display: inline-flex; align-items: center; gap: 4px; }
.hint-dot { display: inline-flex; align-items: center; justify-content: center; width: 14px; height: 14px; border-radius: 50%; font-size: 10px; background: var(--el-color-info-light-7); cursor: help; }
.warn-input :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-warning) inset;
}
.warn-text { color: var(--el-color-warning); }
.amt-input { width: 100%; }
.pop-cell { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.src-tag { margin-left: 2px; }
.mismatch-hint {
  font-size: 10px;
  color: var(--el-color-warning);
  line-height: 1.2;
  margin-top: 2px;
}
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
.trace-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 8px;
}
.drawer-meta { font-size: 13px; margin-bottom: 12px; }
.drawer-progress { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
:deep(.row-anomaly) { background: #fef0f0 !important; }
:deep(.row-mismatch-warn) { background: #fdf6ec !important; }
:deep(.row-cip-warn) { background: #fdf6ec !important; }
</style>
