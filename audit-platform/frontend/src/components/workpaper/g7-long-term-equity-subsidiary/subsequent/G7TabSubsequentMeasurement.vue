<!--
  G7TabSubsequentMeasurement.vue — G7-10 子公司后续计量测试表

  对齐致同源模板三区段：
  1、被投资单位分配股利测算（应享股利=宣告×持股，差异=应享−入账）
  2、购买少数股东股权（个别按成本法增记；合并⑤=②−④调权益，不确认商誉）
  3、处置子公司权益但不丧失控制权（个别⑤=④−①×③/②；合并⑧=④−⑦调权益）

  编号统一：①②③④⑤ / ⑥⑦⑧ 各区段内唯一，修正源模板右表复用①②的歧义。
-->
<template>
  <div class="g7-tab-subsequent">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G7-10 子公司后续计量测试表</h3>
        <div class="sheet-subtitle">股利测算 · 购买少数股权 · 不丧失控制权处置</div>
      </div>
      <div class="head-actions">
        <el-dropdown v-if="!isReadonly" @command="handleAddCommand">
          <el-button size="small" type="primary">新增测试 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="dividend">股利分配测算</el-dropdown-item>
              <el-dropdown-item command="nci">购买少数股权</el-dropdown-item>
              <el-dropdown-item command="partialDisposal">不丧失控制权处置</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" link @click="handleAiConclusion">🤖 AI辅助</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          :loading="syncingFromG79"
          @click="syncFromG79"
        >从G7-9带入</el-button>
        <el-button size="small" @click="openReviewDialog('G7-10-subsequent')">💬复核</el-button>
        <GtIndexChip value="wp:G7-10" :context-project-id="projectId" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      审计目标：确定子公司长期股权投资及其相关账户后续计量是否正确——成本法下股利确认、
      购买少数股权与不丧失控制权处置在个别报表与合并报表的差异处理是否符合 CAS2 / CAS33。
    </el-alert>

    <div class="methodology-context">
      <strong>核心逻辑：</strong>
      个别报表子公司投资按<strong>成本法</strong>；合并报表母公司购买/处置少数股权且不改变控制权时按<strong>权益性交易</strong>处理，
      差额调整资本公积（不足冲减留存收益），不确认商誉或损益。
    </div>

    <div class="summary-bar">
      <div class="summary-left">
        <el-tag type="info">股利测算 {{ dividendRows.length }} 笔</el-tag>
        <el-tag type="info">购买少数股权 {{ nciRows.length }} 家</el-tag>
        <el-tag type="info">不丧失控制权处置 {{ partialDisposalRows.length }} 家</el-tag>
        <el-tag v-if="investeeOptions.length" type="success">G7-4 子公司 {{ investeeOptions.length }} 家</el-tag>
        <el-tag v-if="errorCount" type="danger">{{ errorCount }} 项错误</el-tag>
        <el-tag v-if="warningCount" type="warning">{{ warningCount }} 项待关注</el-tag>
      </div>
    </div>

    <div class="materiality-bar">
      <span class="materiality-label">重要性水平：</span>
      <el-input-number
        v-if="!isReadonly"
        v-model="materialityLevel"
        :controls="false"
        :precision="2"
        size="small"
        style="width: 160px"
        placeholder="元"
        @change="persistRows"
      />
      <span v-else class="materiality-value">{{ formatAmount(materialityLevel) }}</span>
      <span class="materiality-hint">（|股利差异| / |权益调整| 超过此值将标红并提示）</span>
      <el-button
        v-if="!isReadonly && investeeOptions.length"
        size="small"
        text
        type="primary"
        @click="loadG74Investees"
      >
        刷新 G7-4 名册
      </el-button>
    </div>

    <el-alert
      v-if="issues.length"
      :type="errorCount ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="validation-alert"
    >
      <div v-for="(issue, index) in issues.slice(0, 8)" :key="`${issue.rowId}-${index}`">
        {{ issue.message }}
      </div>
      <div v-if="issues.length > 8">……另有 {{ issues.length - 8 }} 项</div>
    </el-alert>

    <!-- ═══ 1、股利分配测算 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-head">
          <div>
            <strong>1、被投资单位分配股利测算</strong>
            <span class="section-note">应享股利 = 宣告金额 × 持股比例；差异 = 应享 − 实际入账</span>
          </div>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addDividendRow">
            新增公司
          </el-button>
        </div>
      </template>

      <el-table :data="dividendRows" border size="small" row-key="id" empty-text="暂无股利分配测算" max-height="420">
        <el-table-column label="公司名称" min-width="160" fixed="left">
          <template #default="{ row }">
            <CompanyPicker
              v-if="!isReadonly"
              :model-value="row.investeeId || row.companyName"
              :options="investeeOptions"
              @update:model-value="(v: string) => onDividendCompanyChange(row, v)"
            />
            <span v-else>{{ display(row.companyName) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分配方案、股东/董事会决议" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.distributionPlan" size="small" @change="persistRows" />
            <span v-else>{{ display(row.distributionPlan) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持股比例" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.shareholdingRatio"
              :controls="false"
              :precision="6"
              :min="0"
              :max="1"
              size="small"
              class="cell-number"
              @change="(v: number | undefined) => updateDividendNumber(row, 'shareholdingRatio', v)"
            />
            <span v-else>{{ formatPercent(row.shareholdingRatio) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="宣告分派股利日" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.declarationDate" size="small" placeholder="YYYY-MM-DD" @change="persistRows" />
            <span v-else>{{ display(row.declarationDate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="主要股利分配政策" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.dividendPolicy" size="small" @change="persistRows" />
            <span v-else>{{ display(row.dividendPolicy) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="宣告分派的股利金额" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.declaredAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-number"
              @change="(v: number | undefined) => updateDividendNumber(row, 'declaredAmount', v)"
            />
            <span v-else>{{ formatAmount(row.declaredAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="被审计单位应分配股利" min-width="150" align="right">
          <template #default="{ row }">
            <el-tooltip content="应享股利 = 宣告金额 × 持股比例" placement="top">
              <span class="formula-cell">{{ formatAmount(row.entitledDividend) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="实际入账股利" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.recordedDividend"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-number"
              @change="(v: number | undefined) => updateDividendNumber(row, 'recordedDividend', v)"
            />
            <span v-else>{{ formatAmount(row.recordedDividend) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="差异 = 应享股利 − 实际入账" placement="top">
              <span class="formula-cell" :class="varianceClass(row.variance)">{{ formatAmount(row.variance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.auditConclusion" clearable size="small" @change="persistRows">
              <el-option label="无差异" value="无差异" />
              <el-option label="差异可接受" value="差异可接受" />
              <el-option label="需进一步调查" value="需进一步调查" />
              <el-option label="需调整" value="需调整" />
            </el-select>
            <span v-else>{{ display(row.auditConclusion) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="62" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeDividendRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 2、购买少数股东股权 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-head">
          <div>
            <strong>2、购买少数股东股权的处理</strong>
            <span class="section-note">④=③×①；⑤=②−④（合并调权益，不确认商誉）</span>
          </div>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addNciRow">
            新增公司
          </el-button>
        </div>
      </template>

      <div v-if="!nciRows.length" class="empty-hint">暂无购买少数股权测试</div>
      <div v-for="row in nciRows" :key="row.id" class="company-block">
        <div class="company-block-head">
          <CompanyPicker
            v-if="!isReadonly"
            :model-value="row.investeeId || row.companyName"
            :options="investeeOptions"
            style="max-width: 280px"
            @update:model-value="(v: string) => onNciCompanyChange(row, v)"
          />
          <strong v-else>{{ display(row.companyName) }}</strong>
          <div class="company-block-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              @click="fillNciSplit(row)"
            >
              一键填资本公积
            </el-button>
            <el-button v-if="!isReadonly" type="danger" link size="small" @click="removeNciRow(row.id)">删除</el-button>
          </div>
        </div>
        <div class="dual-grid">
          <div class="dual-pane">
            <div class="pane-title">个别报表（成本法）</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="购买前长投账面价值">
                <NumField :row="row" field="priorCarryingAmount" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="原持股比例">
                <RatioField :row="row" field="originalRatio" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="新增持股比例①">
                <RatioField :row="row" field="addedRatio" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="购买成本② — 现金">
                <NumField :row="row" field="costCash" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="② — 非现金资产公允价值">
                <NumField :row="row" field="costNonCashFV" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="② — 发行或承担债务账面价值">
                <NumField :row="row" field="costDebtBV" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="② — 发行权益性证券面值">
                <NumField :row="row" field="costEquityFace" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="② — 或有对价">
                <NumField :row="row" field="costContingent" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="购买成本②（合计）">
                <span class="formula-cell">{{ formatAmount(row.purchaseCost) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="购买后长投账面价值">
                <el-tooltip content="购买前账面 + 购买成本②" placement="top">
                  <span class="formula-cell">{{ formatAmount(row.carryingAfterPurchase) }}</span>
                </el-tooltip>
              </el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="dual-pane">
            <div class="pane-title">合并报表（权益性交易）</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="持续计算可辨认净资产公允价值③">
                <NumField :row="row" field="netAssetsFV" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="按新增比例享有份额④=③×①">
                <span class="formula-cell">{{ formatAmount(row.shareOfNetAssets) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="调整资本公积/留存收益⑤=②−④">
                <span class="formula-cell">{{ formatAmount(row.equityAdjustment) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="其中：调整资本公积">
                <NumField :row="row" field="adjCapitalReserve" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="其中：调整盈余公积">
                <NumField :row="row" field="adjSurplusReserve" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="其中：调整未分配利润">
                <NumField :row="row" field="adjRetainedEarnings" :readonly="isReadonly" @change="updateNciNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="索引号">
                <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="persistRows" />
                <span v-else>{{ display(row.indexRef) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="审计结论">
                <el-select v-if="!isReadonly" v-model="row.auditConclusion" clearable size="small" @change="persistRows">
                  <el-option label="无差异" value="无差异" />
                  <el-option label="差异可接受" value="差异可接受" />
                  <el-option label="需进一步调查" value="需进一步调查" />
                  <el-option label="需调整" value="需调整" />
                </el-select>
                <span v-else>{{ display(row.auditConclusion) }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </div>
    </el-card>

    <!-- ═══ 3、不丧失控制权处置 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-head">
          <div>
            <strong>3、处置子公司权益但不丧失控制权</strong>
            <span class="section-note">个别⑤=④−①×③/②；合并⑧=④−⑦（调权益，不确认损益）</span>
          </div>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addPartialDisposalRow">
            新增公司
          </el-button>
        </div>
      </template>

      <div v-if="!partialDisposalRows.length" class="empty-hint">暂无不丧失控制权处置测试</div>
      <div v-for="row in partialDisposalRows" :key="row.id" class="company-block">
        <div class="company-block-head">
          <CompanyPicker
            v-if="!isReadonly"
            :model-value="row.investeeId || row.companyName"
            :options="investeeOptions"
            style="max-width: 280px"
            @update:model-value="(v: string) => onPartialCompanyChange(row, v)"
          />
          <strong v-else>{{ display(row.companyName) }}</strong>
          <div class="company-block-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              @click="fillPartialSplit(row)"
            >
              一键填资本公积
            </el-button>
            <el-button v-if="!isReadonly" type="danger" link size="small" @click="removePartialDisposalRow(row.id)">删除</el-button>
          </div>
        </div>
        <div class="dual-grid">
          <div class="dual-pane">
            <div class="pane-title">个别报表（成本法）</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="处置日长投账面价值①">
                <NumField :row="row" field="bookValueAtDisposal" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="原持股比例②">
                <RatioField :row="row" field="originalRatio" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="减少的持股比例③">
                <RatioField :row="row" field="reducedRatio" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="处置对价④ — 现金">
                <NumField :row="row" field="considerationCash" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="④ — 非现金资产公允价值">
                <NumField :row="row" field="considerationNonCashFV" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="④ — 解除债务账面价值">
                <NumField :row="row" field="considerationDebtBV" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="④ — 发行权益性证券面值">
                <NumField :row="row" field="considerationEquityFace" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="④ — 或有对价">
                <NumField :row="row" field="considerationContingent" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="处置对价④（合计）">
                <span class="formula-cell">{{ formatAmount(row.consideration) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="计入个别报表的投资收益⑤=④−①×③/②">
                <span class="formula-cell">{{ formatAmount(row.individualGain) }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="dual-pane">
            <div class="pane-title">合并报表（权益性交易）</div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="持续计算可辨认净资产公允价值⑥">
                <NumField :row="row" field="netAssetsFV" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="按减少比例享有份额⑦=⑥×③">
                <span class="formula-cell">{{ formatAmount(row.consolShare) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="调整资本公积/留存收益⑧=④−⑦">
                <span class="formula-cell">{{ formatAmount(row.consolEquityAdj) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="其中：调整资本公积">
                <NumField :row="row" field="adjCapitalReserve" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="其中：调整盈余公积">
                <NumField :row="row" field="adjSurplusReserve" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="其中：调整未分配利润">
                <NumField :row="row" field="adjRetainedEarnings" :readonly="isReadonly" @change="updatePartialNumber" />
              </el-descriptions-item>
              <el-descriptions-item label="索引号">
                <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="persistRows" />
                <span v-else>{{ display(row.indexRef) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="审计结论">
                <el-select v-if="!isReadonly" v-model="row.auditConclusion" clearable size="small" @change="persistRows">
                  <el-option label="无差异" value="无差异" />
                  <el-option label="差异可接受" value="差异可接受" />
                  <el-option label="需进一步调查" value="需进一步调查" />
                  <el-option label="需调整" value="需调整" />
                </el-select>
                <span v-else>{{ display(row.auditConclusion) }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header><span>三、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="概述所执行程序、股利核对情况、购买/处置少数股权的个别与合并处理差异、拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>四、审计结论</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiConclusion">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对子公司后续计量（股利确认、购买少数股权、不丧失控制权处置）的综合评价……"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li><strong>1、股利测算：</strong>成本法下于被投资方<strong>宣告</strong>日按持股比例确认投资收益；应享与入账差异需追查凭证/决议。超重要性水平标红。</li>
        <li><strong>2、购买少数股权：</strong>个别报表按 CAS2 以支付对价确定新增投资成本；合并报表按 CAS33，⑤=购买成本②−按新增比例①享有的持续计算净资产份额④，差额调资本公积（不足冲留存收益），不确认商誉。可用「一键填资本公积」。</li>
        <li><strong>3、不丧失控制权处置：</strong>个别报表确认投资收益⑤=④−①×③/②；合并报表按权益性交易，⑧=④−⑦，不确认损益。剩余持股≤50%时提示复核控制权；若丧失控制权，改用 G7-11/G7-12。</li>
        <li>公司名称优先从 <strong>G7-4</strong> 子公司名册选择，自动预填持股比例与投资账面。</li>
        <li>编号①~⑧在各区段内唯一；合并侧净资产须自购买日/合并日<strong>持续计算</strong>。</li>
      </ul>
    </details>

    <G7VoucherSampleSection
      :wp-id="wpId"
      :project-id="projectId"
      :is-readonly="isReadonly"
      storage-key="G7-10-voucher-samples"
      account-code="1511"
      title="后续计量凭证抽查（G7-10）"
      :html-data="htmlData"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, inject, onMounted, reactive, ref, toRef } from 'vue'
import { ElInputNumber, ElMessage, ElMessageBox, ElOption, ElSelect } from 'element-plus'
import {
  createDividendRow,
  createNciPurchaseRow,
  createPartialDisposalRow,
  fillNciEquitySplitToCapitalReserve,
  fillPartialDisposalEquitySplitToCapitalReserve,
  parseSubsequentPayload,
  recalcDividendRow,
  recalcNciPurchaseRow,
  recalcPartialDisposalRow,
  syncDividendRowsFromG79Carry,
  validateSubsequentRows,
  type G7DividendRow,
  type G7NciPurchaseRow,
  type G7PartialDisposalRow,
  type G7SubsequentStoredRow,
} from './g7SubsequentModel'
import { extractG79CarryToSubsequent, normalizeNotSameControlRows } from '../initial/g7NotSameControlModel'
import {
  G7_4_ROWS_KEY,
  loadSubsidiaryInvestees,
  type G7SubsidiaryInvesteeOption,
} from '../../composables/g7EquityMethodCrossSheet'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import GtIndexChip from '../../GtIndexChip.vue'
import G7VoucherSampleSection from '../../g7-shared/G7VoucherSampleSection.vue'
import http from '@/utils/http'
import { extractG7AiText } from '../../composables/g7AiText'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: { rows: G7SubsequentStoredRow[]; materialityLevel: number; conclusion: string }): void
}>()

const isReadonly = computed(() => props.readonly ?? false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const wpIdRef = toRef(props, 'wpId')
const { exportTemplate, exportData, importData } = useG7SubImportExport({ wpId: wpIdRef })

const dividendRows = reactive<G7DividendRow[]>([])
const nciRows = reactive<G7NciPurchaseRow[]>([])
const partialDisposalRows = reactive<G7PartialDisposalRow[]>([])
const conclusion = ref('')
const auditNote = ref('')
const materialityLevel = ref(0)
const investeeOptions = ref<G7SubsidiaryInvesteeOption[]>([])
const syncingFromG79 = ref(false)

const auditFormData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const ROWS_KEY = 'G7-10-rows'
const NOTE_KEY = 'G7-10-subsequent-audit-note'
const CONCLUSION_KEY = 'G7-10-subsequent-audit-conclusion'

const allRows = computed<G7SubsequentStoredRow[]>(() => [
  ...dividendRows,
  ...nciRows,
  ...partialDisposalRows,
])
const issues = computed(() =>
  validateSubsequentRows(allRows.value, { materialityLevel: materialityLevel.value }),
)
const errorCount = computed(() => issues.value.filter(i => i.severity === 'error').length)
const warningCount = computed(() => issues.value.filter(i => i.severity === 'warning').length)

function display(value: unknown): string {
  return value === '' || value == null ? '—' : String(value)
}
function formatAmount(value: unknown): string {
  const n = Number(value ?? 0)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function formatPercent(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${(value * 100).toFixed(2)}%`
}
function varianceClass(variance: number): string {
  const level = materialityLevel.value
  if (level > 0 && Math.abs(variance) > level) return 'variance-warning'
  if (Math.abs(variance) > 0.01) return 'variance-exists'
  return ''
}

function findInvestee(nameOrId: string): G7SubsidiaryInvesteeOption | undefined {
  return investeeOptions.value.find(o => o.name === nameOrId || o.id === nameOrId)
}

function applyInvesteePick(
  row: { companyName: string; investeeId?: string },
  nameOrId: string,
): G7SubsidiaryInvesteeOption | undefined {
  const opt = findInvestee(nameOrId)
  if (opt) {
    row.companyName = opt.name
    row.investeeId = opt.id
  } else {
    row.companyName = nameOrId
    row.investeeId = undefined
  }
  return opt
}

function persistRows(): void {
  if (isReadonly.value) return
  const payload = {
    rows: allRows.value,
    materialityLevel: materialityLevel.value,
  }
  auditFormData.debouncedSave(ROWS_KEY, {
    conclusion: JSON.stringify(payload),
    remark: 'G7-10后续计量三区段测试',
  })
  emit('save', {
    rows: [...allRows.value],
    materialityLevel: materialityLevel.value,
    conclusion: conclusion.value,
  })
}

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}
function saveAuditConclusion(val: string): void {
  if (isReadonly.value) return
  conclusion.value = val
  auditFormData.debouncedSave(CONCLUSION_KEY, { remark: val, conclusion: null })
}

function updateDividendNumber(row: G7DividendRow, field: keyof G7DividendRow, value: unknown): void {
  ;(row as any)[field] = value == null || value === '' ? null : Number(value)
  Object.assign(row, recalcDividendRow(row))
  persistRows()
}
function updateNciNumber(row: G7NciPurchaseRow, field: string, value: unknown): void {
  ;(row as any)[field] = value == null || value === '' ? null : Number(value)
  Object.assign(row, recalcNciPurchaseRow(row))
  persistRows()
}
function updatePartialNumber(row: G7PartialDisposalRow, field: string, value: unknown): void {
  ;(row as any)[field] = value == null || value === '' ? null : Number(value)
  Object.assign(row, recalcPartialDisposalRow(row))
  persistRows()
}

function onDividendCompanyChange(row: G7DividendRow, name: string): void {
  const opt = applyInvesteePick(row, name)
  if (opt?.shareholdingRatio != null && (row.shareholdingRatio == null || row.shareholdingRatio === 0)) {
    row.shareholdingRatio = opt.shareholdingRatio
  }
  Object.assign(row, recalcDividendRow(row))
  persistRows()
}
function onNciCompanyChange(row: G7NciPurchaseRow, name: string): void {
  const opt = applyInvesteePick(row, name)
  if (opt) {
    if (opt.shareholdingRatio != null && (row.originalRatio == null || row.originalRatio === 0)) {
      row.originalRatio = opt.shareholdingRatio
    }
    if (opt.carryingAmount != null && (row.priorCarryingAmount == null || row.priorCarryingAmount === 0)) {
      row.priorCarryingAmount = opt.carryingAmount
    }
  }
  Object.assign(row, recalcNciPurchaseRow(row))
  persistRows()
}
function onPartialCompanyChange(row: G7PartialDisposalRow, name: string): void {
  const opt = applyInvesteePick(row, name)
  if (opt) {
    if (opt.shareholdingRatio != null && (row.originalRatio == null || row.originalRatio === 0)) {
      row.originalRatio = opt.shareholdingRatio
    }
    if (opt.carryingAmount != null && (row.bookValueAtDisposal == null || row.bookValueAtDisposal === 0)) {
      row.bookValueAtDisposal = opt.carryingAmount
    }
  }
  Object.assign(row, recalcPartialDisposalRow(row))
  persistRows()
}

function fillNciSplit(row: G7NciPurchaseRow): void {
  Object.assign(row, fillNciEquitySplitToCapitalReserve(recalcNciPurchaseRow(row)))
  persistRows()
  ElMessage.success('已将权益调整⑤全额填入资本公积')
}
function fillPartialSplit(row: G7PartialDisposalRow): void {
  Object.assign(row, fillPartialDisposalEquitySplitToCapitalReserve(recalcPartialDisposalRow(row)))
  persistRows()
  ElMessage.success('已将合并权益调整⑧全额填入资本公积')
}

async function promptName(title: string): Promise<string | null> {
  if (investeeOptions.value.length > 0) {
    try {
      const { value } = await ElMessageBox.prompt(
        '可从 G7-4 名册选择，或直接输入新公司名称',
        title,
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '公司名称不能为空',
          inputPlaceholder: investeeOptions.value.map(o => o.name).slice(0, 3).join(' / ') + '…',
        },
      )
      return value.trim()
    } catch {
      return null
    }
  }
  try {
    const { value } = await ElMessageBox.prompt('请输入公司名称', title, {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '公司名称不能为空',
    })
    return value.trim()
  } catch {
    return null
  }
}

async function addDividendRow(): Promise<void> {
  const name = await promptName('新增股利分配测算')
  if (!name) return
  if (dividendRows.some(r => r.companyName === name)) {
    ElMessage.warning(`「${name}」已存在`)
    return
  }
  const row = createDividendRow(dividendRows.length + 1, name)
  const opt = findInvestee(name)
  if (opt?.shareholdingRatio != null) row.shareholdingRatio = opt.shareholdingRatio
  dividendRows.push(recalcDividendRow(row))
  persistRows()
}
function removeDividendRow(id: string): void {
  const idx = dividendRows.findIndex(r => r.id === id)
  if (idx < 0) return
  dividendRows.splice(idx, 1)
  dividendRows.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

async function addNciRow(): Promise<void> {
  const name = await promptName('新增购买少数股权')
  if (!name) return
  if (nciRows.some(r => r.companyName === name)) {
    ElMessage.warning(`「${name}」已存在`)
    return
  }
  const row = createNciPurchaseRow(nciRows.length + 1, name)
  const opt = findInvestee(name)
  if (opt?.shareholdingRatio != null) row.originalRatio = opt.shareholdingRatio
  if (opt?.carryingAmount != null) row.priorCarryingAmount = opt.carryingAmount
  nciRows.push(recalcNciPurchaseRow(row))
  persistRows()
}
function removeNciRow(id: string): void {
  const idx = nciRows.findIndex(r => r.id === id)
  if (idx < 0) return
  nciRows.splice(idx, 1)
  nciRows.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

async function addPartialDisposalRow(): Promise<void> {
  const name = await promptName('新增不丧失控制权处置')
  if (!name) return
  if (partialDisposalRows.some(r => r.companyName === name)) {
    ElMessage.warning(`「${name}」已存在`)
    return
  }
  const row = createPartialDisposalRow(partialDisposalRows.length + 1, name)
  const opt = findInvestee(name)
  if (opt?.shareholdingRatio != null) row.originalRatio = opt.shareholdingRatio
  if (opt?.carryingAmount != null) row.bookValueAtDisposal = opt.carryingAmount
  partialDisposalRows.push(recalcPartialDisposalRow(row))
  persistRows()
}
function removePartialDisposalRow(id: string): void {
  const idx = partialDisposalRows.findIndex(r => r.id === id)
  if (idx < 0) return
  partialDisposalRows.splice(idx, 1)
  partialDisposalRows.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

function handleAddCommand(cmd: string): void {
  if (cmd === 'dividend') void addDividendRow()
  else if (cmd === 'nci') void addNciRow()
  else if (cmd === 'partialDisposal') void addPartialDisposalRow()
}

async function loadG74Investees(): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = responses.find((r: any) => r.item_id === G7_4_ROWS_KEY)
    investeeOptions.value = loadSubsidiaryInvestees(item?.conclusion)
    if (investeeOptions.value.length) {
      ElMessage.success(`已加载 G7-4 子公司 ${investeeOptions.value.length} 家`)
    }
  } catch {
    // G7-4 可能在同项目其他 wp；静默失败，仍可手输
    investeeOptions.value = []
  }
}

async function syncFromG79(): Promise<void> {
  if (isReadonly.value || syncingFromG79.value || !props.wpId) return
  syncingFromG79.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = responses.find((r: any) => r.item_id === 'G7-9-rows')
    let raw: unknown = item?.conclusion
    if (typeof raw === 'string' && raw.trim()) {
      try { raw = JSON.parse(raw) } catch { /* keep string */ }
    }
    const carry = extractG79CarryToSubsequent(normalizeNotSameControlRows(raw))
    if (!carry.length) {
      ElMessage.warning('G7-9 中暂无可带入的非同控子公司')
      return
    }
    const result = syncDividendRowsFromG79Carry([...dividendRows], carry)
    dividendRows.splice(0, dividendRows.length, ...result.rows)
    persistRows()
    ElMessage.success(`已从 G7-9 带入股利测算名单：新增 ${result.added} 家（已有公司未覆盖）`)
  } catch {
    ElMessage.error('从 G7-9 带入失败')
  } finally {
    syncingFromG79.value = false
  }
}

async function handleAiConclusion(): Promise<void> {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/subsequent-conclusion`,
      {
        existingContent: conclusion.value,
        relatedContext: {
          sheet: 'G7-10',
          materialityLevel: materialityLevel.value,
          dividendCount: dividendRows.length,
          nciCount: nciRows.length,
          partialDisposalCount: partialDisposalRows.length,
          dividendRows: [...dividendRows],
          nciRows: [...nciRows],
          partialDisposalRows: [...partialDisposalRows],
        },
      },
    )
    const text = extractG7AiText(res?.data)
    if (text) {
      conclusion.value = String(text)
      auditFormData.debouncedSave(CONCLUSION_KEY, { remark: conclusion.value, conclusion: null })
      ElMessage.success('AI结论已生成')
    } else {
      ElMessage.warning('AI未返回内容，请手动填写')
    }
  } catch {
    ElMessage.warning('AI结论生成暂不可用，请手动填写')
  }
}

async function handleImportExportCommand(command: string): Promise<void> {
  if (command === 'template') {
    await exportTemplate('G7-10')
  } else if (command === 'export') {
    await exportData('G7-10')
  } else if (command === 'import') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      const result = await importData('G7-10', file)
      if (result) {
        await auditFormData.load()
        const saved = auditFormData.data.value.get(ROWS_KEY)
        let parsed: unknown = null
        if (saved?.conclusion) {
          try { parsed = JSON.parse(String(saved.conclusion)) } catch { parsed = saved.conclusion }
        }
        const list = Array.isArray(parsed)
          ? parsed
          : (parsed && typeof parsed === 'object' && Array.isArray((parsed as any).rows)
            ? (parsed as any).rows
            : [])
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          const mat = Number((parsed as any).materialityLevel ?? (parsed as any).materiality_level ?? NaN)
          if (Number.isFinite(mat)) materialityLevel.value = mat
        }
        if (list.length) {
          applyRows(list as any)
          ElMessage.success(`导入完成，已刷新 ${list.length} 行`)
        } else {
          ElMessage.success('导入完成，请核对数据')
        }
      }
    }
    input.click()
  }
}

function applyRows(rows: G7SubsequentStoredRow[]): void {
  dividendRows.length = 0
  nciRows.length = 0
  partialDisposalRows.length = 0
  for (const row of rows) {
    if (row.section === 'dividend') dividendRows.push(row)
    else if (row.section === 'nci') nciRows.push(row)
    else if (row.section === 'partialDisposal') partialDisposalRows.push(row)
  }
}

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) return
  const subData = data.subsequentMeasurement || data.subsequent_measurement || data
  conclusion.value = subData?.conclusion || conclusion.value || ''
  if (subData?.materialityLevel != null || subData?.materiality_level != null) {
    materialityLevel.value = Number(subData.materialityLevel ?? subData.materiality_level) || 0
  }
  const rawRows = subData?.rows || []
  if (Array.isArray(rawRows) && rawRows.length > 0) {
    const parsed = parseSubsequentPayload({ rows: rawRows, materialityLevel: materialityLevel.value })
    applyRows(parsed.rows)
  }
}

function getData(): { rows: G7SubsequentStoredRow[]; materialityLevel: number; conclusion: string } {
  return {
    rows: [...allRows.value],
    materialityLevel: materialityLevel.value,
    conclusion: conclusion.value,
  }
}

defineExpose({ getData, loadFromHtmlData })

const CompanyPicker = defineComponent({
  props: {
    modelValue: { type: String, default: '' },
    options: { type: Array as () => G7SubsidiaryInvesteeOption[], default: () => [] },
  },
  emits: ['update:modelValue'],
  setup(p, { emit }) {
    return () => h(
      ElSelect,
      {
        modelValue: p.modelValue,
        filterable: true,
        allowCreate: true,
        defaultFirstOption: true,
        size: 'small',
        placeholder: p.options.length ? '选择或输入公司' : '输入公司名称',
        style: { width: '100%' },
        'onUpdate:modelValue': (v: string) => emit('update:modelValue', v ?? ''),
      },
      {
        default: () => p.options.map(o =>
          h(ElOption, {
            key: o.id || o.name,
            label: o.shareholdingRatio != null
              ? `${o.name}（${(o.shareholdingRatio * 100).toFixed(2)}%）`
              : o.name,
            value: o.id || o.name,
          }),
        ),
      },
    )
  },
})

const NumField = defineComponent({
  props: { row: { type: Object, required: true }, field: { type: String, required: true }, readonly: Boolean },
  emits: ['change'],
  setup(p, { emit }) {
    return () => p.readonly
      ? h('span', formatAmount((p.row as any)[p.field]))
      : h(ElInputNumber, {
          modelValue: (p.row as any)[p.field],
          controls: false,
          precision: 2,
          size: 'small',
          class: 'cell-number',
          onChange: (v: number | undefined) => emit('change', p.row, p.field, v),
        })
  },
})
const RatioField = defineComponent({
  props: { row: { type: Object, required: true }, field: { type: String, required: true }, readonly: Boolean },
  emits: ['change'],
  setup(p, { emit }) {
    return () => p.readonly
      ? h('span', formatPercent((p.row as any)[p.field]))
      : h(ElInputNumber, {
          modelValue: (p.row as any)[p.field],
          controls: false,
          precision: 6,
          min: 0,
          max: 1,
          step: 0.01,
          size: 'small',
          class: 'cell-number',
          onChange: (v: number | undefined) => emit('change', p.row, p.field, v),
        })
  },
})

onMounted(async () => {
  loadFromHtmlData(props.htmlData)
  await Promise.all([auditFormData.load(), loadG74Investees()])
  const stored = auditFormData.data.value.get(ROWS_KEY)
  if (stored?.conclusion) {
    const parsed = parseSubsequentPayload(stored.conclusion)
    applyRows(parsed.rows)
    if (parsed.materialityLevel) materialityLevel.value = parsed.materialityLevel
  }
  const n = auditFormData.data.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = auditFormData.data.value.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
})
</script>

<style scoped>
.g7-tab-subsequent { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; gap: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.sheet-subtitle { margin-top: 4px; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.objective-alert { margin-bottom: 12px; }
.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  line-height: 1.7;
  color: #78350f;
}
.summary-bar { margin-bottom: 12px; }
.summary-left { display: flex; gap: 8px; flex-wrap: wrap; }
.materiality-bar {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.materiality-label { font-weight: 500; color: #303133; white-space: nowrap; }
.materiality-value { font-weight: 600; color: #409eff; }
.materiality-hint { font-size: 11px; color: #909399; }
.validation-alert { margin-bottom: 12px; }
.section-card { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.section-note { margin-left: 8px; font-size: 12px; color: #909399; font-weight: 400; }
.cell-number { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}
.variance-warning { color: #f56c6c; font-weight: 600; }
.variance-exists { color: #e6a23c; font-weight: 500; }
.empty-hint { padding: 16px; color: #909399; text-align: center; }
.company-block {
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
.company-block-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  gap: 12px;
}
.company-block-actions { display: flex; align-items: center; gap: 4px; }
.dual-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 1100px) {
  .dual-grid { grid-template-columns: 1fr; }
}
.pane-title {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 6px;
}
.audit-note-card, .conclusion-card { margin-top: 16px; }
.prep-hint { margin-top: 16px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
