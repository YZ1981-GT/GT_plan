<template>
  <div class="k1-disclosure-listed" data-testid="k1-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <el-tag size="small" type="info">{{ disc.noteTarget.value.sectionId }} · 其他应收款</el-tag>
        <el-tag size="small" type="warning">{{ agingPresetLabel }}</el-tag>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="disc.refreshFromSources(false)">
          从源底稿取数
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="disc.refreshFromSources(true)">
          强制覆盖
        </el-button>
        <el-button
          size="small"
          type="success"
          :loading="disc.isSyncing.value"
          :disabled="isReadonly || !projectId"
          @click="disc.syncToNotes()"
        >
          同步至附注
        </el-button>
        <el-button size="small" @click="handleReview('K1-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：按上市公司附注格式披露其他应收款账龄、款项性质、ECL 三阶段坏账及前五名等，与 K1-1/K1-2/K1-3 勾稽，并回写附注五、8。"
    />

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 按账龄披露（账龄段随项目配置：三年/五年/自定义）</div>
        <div class="guide-step"><span class="step-num">②</span> 按款项性质披露（账面余额/坏账/账面价值）</div>
        <div class="guide-step"><span class="step-num">③</span> 坏账准备计提情况（ECL 三阶段）</div>
        <div class="guide-step"><span class="step-num">④</span> 变动/转回/核销/前五名 → 同步附注模块</div>
      </div>
    </div>

    <el-alert
      v-if="disc.adjudication.value.receivableEnd"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已联动 K1-1 审定：其他应收款期末 {{ fmt(disc.adjudication.value.receivableEnd) }}
      · 坏账准备 {{ fmt(disc.adjudication.value.badDebtEnd) }}
      <template v-if="disc.lastSyncHint.value"> · 取数 {{ disc.lastSyncHint.value }}</template>
    </el-alert>

    <el-alert
      v-if="!disc.agingTieOut.value.matched && disc.agingTieOut.value.subtotal"
      type="warning"
      :closable="false"
      :title="`账龄小计 ${fmt(disc.agingTieOut.value.subtotal)} ≠ K1-1 审定 ${fmt(disc.adjudication.value.receivableEnd)}（差 ${fmt(disc.agingTieOut.value.diff)}）`"
    />

    <K1DisclosureTracePanel
      :rows="trace.traceRows.value"
      :open-count="trace.openCount.value"
      @navigate-sheet="(s) => emit('navigate-sheet', s)"
    />

    <!-- ① 按账龄披露 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">① 按账龄披露</span>
          <el-tag size="small" type="warning">附注 {{ disc.noteTarget.value.sectionId }}</el-tag>
        </div>
      </template>
      <el-table :data="disc.agingRows.value" border size="small" :row-class-name="agingRowClass">
        <el-table-column label="账龄" min-width="140">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.kind === 'total' || row.kind === 'subtotal' || row.kind === 'provision' }">
              {{ row.label }}
            </span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.endAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => disc.updateAgingRow(row.rowId, 'endAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => disc.updateAgingRow(row.rowId, 'priorAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ② 按款项性质披露 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">② 按款项性质披露</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addNatureRow()">新增行</el-button>
        </div>
      </template>
      <el-table :data="natureTableData" border size="small" :row-class-name="natureRowClass">
        <el-table-column label="项目" min-width="130" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.label"
              size="small"
              @change="(v: string) => disc.updateNatureRow(row.rowId, 'label', v)"
            />
            <span v-else :class="{ 'is-total': row.isTotal }">{{ row.label }}</span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末数">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.endGross"
                size="small"
                :controls="false"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'endGross', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.endGross) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.endProvision"
                size="small"
                :controls="false"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'endProvision', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.endProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.endBookValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上年年末数">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.priorGross"
                size="small"
                :controls="false"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'priorGross', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.priorGross) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.priorProvision"
                size="small"
                :controls="false"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'priorProvision', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.priorProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.priorBookValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              size="small"
              type="danger"
              link
              @click="disc.removeNatureRow(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ③ ECL 三阶段 -->
    <el-card v-for="block in stageBlocks" :key="block.stage" shadow="never" class="disclosure-card">
      <template #header>
        <span class="card-title">{{ block.title }}</span>
      </template>
      <el-table :data="block.rows" border size="small" :row-class-name="stageRowClass">
        <el-table-column label="类别" min-width="180">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.kind === 'total' || row.kind === 'subtotal', 'is-header': row.kind === 'header' }">
              {{ row.label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="账面余额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && row.kind === 'data' && !isReadonly"
              :model-value="row.balance"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => disc.updateStageRow(block.stage, row.rowId, 'balance', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ row.kind === 'header' ? '—' : fmt(row.balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="block.rateLabel" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && row.kind === 'data' && !isReadonly"
              :model-value="row.eclRate ?? 0"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 100%"
              @change="(v: number) => disc.updateStageRow(block.stage, row.rowId, 'eclRate', v ?? 0)"
            />
            <span v-else>{{ row.kind === 'header' ? '—' : formatRate(row.eclRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="坏账准备" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && row.kind === 'data' && !isReadonly"
              :model-value="row.provision"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => disc.updateStageRow(block.stage, row.rowId, 'provision', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ row.kind === 'header' ? '—' : fmt(row.provision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.kind === 'header' ? '—' : fmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="理由" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.editable && row.kind === 'data' && !isReadonly"
              :model-value="row.reason"
              size="small"
              @change="(v: string) => disc.updateStageRow(block.stage, row.rowId, 'reason', v)"
            />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ④ 三阶段坏账变动 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">④ 本期计提、收回或转回的坏账准备情况</span></template>
      <el-table :data="disc.stageMovements.value" border size="small">
        <el-table-column prop="label" label="坏账准备" min-width="160" />
        <el-table-column label="第一阶段" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.stage1) }}</template>
        </el-table-column>
        <el-table-column label="第二阶段" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.stage2) }}</template>
        </el-table-column>
        <el-table-column label="第三阶段" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.stage3) }}</template>
        </el-table-column>
        <el-table-column label="合计" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.stage1 + row.stage2 + row.stage3) }}</template>
        </el-table-column>
      </el-table>
      <p class="template-tip">数据来自 K1-3 三阶段转入转出矩阵；可在 K1-3 修改后重新取数。</p>
    </el-card>

    <!-- ⑤ 重大转回 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑤ 本期转回或收回金额重要的坏账准备</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addReversalRow()">新增行</el-button>
        </div>
      </template>
      <el-table :data="disc.reversalRows.value" border size="small" max-height="320">
        <el-table-column label="单位名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateReversalRow(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转回原因" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => disc.updateReversalRow(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回方式" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.method" size="small" @change="(v: string) => disc.updateReversalRow(row.rowId, 'method', v)" />
            <span v-else>{{ row.method }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确定坏账准备的依据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.basis" size="small" @change="(v: string) => disc.updateReversalRow(row.rowId, 'basis', v)" />
            <span v-else>{{ row.basis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转回或收回金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" style="width: 100%" @change="(v: number) => disc.updateReversalRow(row.rowId, 'amount', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ⑥ 核销 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑥ 本期实际核销的其他应收款情况</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addWriteoffRow()">新增明细</el-button>
        </div>
      </template>
      <div class="writeoff-summary">
        实际核销的其他应收款合计：
        <b>{{ fmt(disc.payload.value.writeoffSummaryAmount) }}</b>
      </div>
      <el-table :data="disc.payload.value.writeoffDetailRows" border size="small" max-height="320">
        <el-table-column label="单位名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="款项性质" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.nature" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'nature', v)" />
            <span v-else>{{ row.nature }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" style="width: 100%" @change="(v: number) => disc.updateWriteoffRow(row.rowId, 'amount', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销程序" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.procedure" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'procedure', v)" />
            <span v-else>{{ row.procedure }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联交易" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.relatedParty" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'relatedParty', v)" />
            <span v-else>{{ row.relatedParty }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ⑦ 前五名 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑦ 按欠款方归集的期末余额前五名其他应收款</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addTop5Row()">新增行</el-button>
        </div>
      </template>
      <el-table :data="disc.top5Rows.value" border size="small">
        <el-table-column label="单位名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateTop5Row(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName }}</span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">K1-2</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="款项性质" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.nature" size="small" @change="(v: string) => disc.updateTop5Row(row.rowId, 'nature', v)" />
            <span v-else>{{ row.nature }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small" :controls="false" style="width: 100%" @change="(v: number) => disc.updateTop5Row(row.rowId, 'endBalance', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.aging" size="small" @change="(v: string) => disc.updateTop5Row(row.rowId, 'aging', v)" />
            <span v-else>{{ row.aging || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比(%)" width="90" align="right">
          <template #default="{ row }">{{ row.proportionPct ? row.proportionPct.toFixed(2) : '—' }}</template>
        </el-table-column>
        <el-table-column label="坏账准备" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.provision" size="small" :controls="false" style="width: 100%" @change="(v: number) => disc.updateTop5Row(row.rowId, 'provision', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmt(row.provision) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ⑧ 资金集中管理 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">⑧ 资金集中管理</span></template>
      <div class="fund-row">
        <span>因资金集中管理列报于其他应收款的金额：</span>
        <el-input-number
          v-if="!isReadonly"
          :model-value="disc.payload.value.fundCentralizationAmount"
          size="small"
          :controls="false"
          @change="(v: number) => disc.updateFundCentralization('amount', v ?? 0)"
        />
        <span v-else class="amount-cell">{{ fmt(disc.payload.value.fundCentralizationAmount) }}</span>
      </div>
      <el-input
        v-model="fundNoteProxy"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="披露因资金集中管理而列报于其他应收款的相关情况（15号文第十九条（五）8）"
        class="note-area"
      />
    </el-card>

    <!-- ⑨ 应收政府补助 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑨ 应收政府补助情况（逐项披露）</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addGovGrantRow()">新增行</el-button>
        </div>
      </template>
      <el-table :data="disc.payload.value.govGrantRows" border size="small" max-height="280">
        <el-table-column label="单位名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="政府补助项目名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.projectName" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'projectName', v)" />
            <span v-else>{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small" :controls="false" style="width: 100%" @change="(v: number) => disc.updateGovGrantRow(row.rowId, 'endBalance', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.aging" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'aging', v)" />
            <span v-else>{{ row.aging }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预计收取的时间、金额及依据" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.expectedCollection" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'expectedCollection', v)" />
            <span v-else>{{ row.expectedCollection }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">审计说明 / 文字披露</span></template>
      <el-input
        v-model="disc.noteText.value"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="ECL 阶段划分依据、账面余额显著变动说明等文字披露…"
        @change="disc.persistNote()"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>账龄段跟随项目 aging config（三年/五年/自定义），与 K1-2 明细账龄列一致</li>
        <li>「从源底稿取数」：K1-1 审定 + K1-2 账龄/性质 + K1-3 三阶段矩阵 + K1-9 转回/核销</li>
        <li>「同步至附注」写入 note_template §五、8 对应子表（按账龄/性质/ECL/前五名等）</li>
        <li>G2/G3 应收利息/股利明细亦在同一附注章节，请勿覆盖其已同步数据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * 对齐致同源模板 + note_template_listed §五、8
 * 账龄枚举 THREE_YEAR / FIVE_YEAR / CUSTOM；联动附注模块 sync-from-workpaper
 */
import { computed, inject, toRef } from 'vue'
import { useK1DisclosureListed } from '../../composables/useK1DisclosureListed'
import { useK1DisclosureTrace } from '../../composables/k1DisclosureTrace'
import K1DisclosureTracePanel from './K1DisclosureTracePanel.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const disc = useK1DisclosureListed({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, value),
  applicableStandards: () => props.applicableStandards,
})

const trace = useK1DisclosureTrace('listed', toRef(props, 'allResponses'))

const agingPresetLabel = computed(() => {
  const p = disc.agingConfig.preset.value
  if (p === 'THREE_YEAR') return '账龄：三年分段'
  if (p === 'FIVE_YEAR') return '账龄：五年分段'
  return '账龄：自定义'
})

const natureTableData = computed(() => [
  ...disc.natureRows.value,
  { ...disc.natureTotal.value, isTotal: true },
])

const stageBlocks = computed(() => [
  {
    stage: 1 as const,
    title: '③ 期末处于第一阶段的坏账准备',
    rateLabel: '未来12个月内ECL率(%)',
    rows: disc.stage1Rows.value,
  },
  {
    stage: 2 as const,
    title: '期末处于第二阶段的坏账准备',
    rateLabel: '整个存续期ECL率(%)',
    rows: disc.stage2Rows.value,
  },
  {
    stage: 3 as const,
    title: '期末处于第三阶段的坏账准备',
    rateLabel: '整个存续期ECL率(%)',
    rows: disc.stage3Rows.value,
  },
])

const fundNoteProxy = computed({
  get: () => disc.payload.value.fundCentralizationNote,
  set: (v: string) => disc.updateFundCentralization('note', v),
})

function fmt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  if (v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatRate(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v.toFixed(2)}%`
}

function agingRowClass({ row }: { row: { kind?: string } }) {
  if (row.kind === 'total' || row.kind === 'subtotal') return 'row-total'
  if (row.kind === 'provision') return 'row-provision'
  return ''
}

function natureRowClass({ row }: { row: { isTotal?: boolean } }) {
  return row.isTotal ? 'row-total' : ''
}

function stageRowClass({ row }: { row: { kind?: string; rowKey?: string } }) {
  if (row.rowKey === 'total' || row.kind === 'total') return 'row-total'
  if (row.kind === 'header') return 'row-header'
  return ''
}

function handleReview(id: string): void {
  openReviewDialog(id)
}
</script>

<style scoped>
.k1-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.objective-alert, .sync-hint { margin-bottom: 12px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.disclosure-card { margin-bottom: 12px; }
.card-title-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-weight: 600; font-size: 14px; }
.amount-cell, .formula-cell { font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); }
.auto-badge { margin-left: 4px; }
.template-tip { font-size: 12px; color: var(--el-text-color-secondary); margin: 8px 0 0; }
.writeoff-summary { margin-bottom: 8px; font-size: 13px; }
.fund-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.note-area { margin-top: 8px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
:deep(.row-total) { font-weight: 600; background: #fafafa; }
:deep(.row-provision) { color: var(--el-color-warning); }
:deep(.row-header) { color: var(--el-text-color-secondary); }
.is-total { font-weight: 600; }
.is-header { color: var(--el-text-color-secondary); }
</style>
