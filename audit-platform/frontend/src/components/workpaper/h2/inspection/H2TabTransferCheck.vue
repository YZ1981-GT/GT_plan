<template>
  <div class="h2-tab-transfer-check">
    <!-- 一、审计目标（对齐致同） -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>核实账面在建工程真实存在，且属于被审计单位（存在性/权利义务）</li>
        <li>核实应予记录的在建工程均已入账，账面金额准确（完整性/计价）</li>
        <li>核实在建工程转入固定资产的时点恰当：不存在延迟转固少计折旧，亦不存在提前转固</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H2-5" :context-project-id="projectId" /></span>
      <GtIndexChip value="wp:H2-2" :context-project-id="projectId" context="明细带入" />
      <GtIndexChip value="wp:H2-9" :context-project-id="projectId" context="减少检查" />
      <GtIndexChip value="H1-1" label="→ H1固定资产" />
      <el-tag size="small" type="info">挂账 {{ state.cipRows.value.length }} / 已转固 {{ state.rows.value.length }}</el-tag>
      <el-tag v-if="state.cipAbnormalCount.value > 0" size="small" type="danger">
        挂账异常 {{ state.cipAbnormalCount.value }}
      </el-tag>
      <el-tag v-if="state.transferAbnormalCount.value > 0" size="small" type="warning">
        时点异常 {{ state.transferAbnormalCount.value }}
      </el-tag>
      <el-tag
        size="small"
        :type="state.crossValidationH1.value.isMatch ? 'success' : 'warning'"
      >
        vs H2-2 {{ state.crossValidationH1.value.isMatch ? '勾稽一致' : `差异 ${fmtAmt(state.crossValidationH1.value.diff)}` }}
      </el-tag>
      <el-tag
        v-if="state.h1RecordedTotal.value > 0.01"
        size="small"
        :type="state.h1TransferReconcile.value.matched ? 'success' : 'danger'"
      >
        vs H1入账 {{ state.h1TransferReconcile.value.matched ? '勾稽一致' : `差异 ${fmtAmt(state.h1TransferReconcile.value.diff)}` }}
      </el-tag>
      <el-tag v-if="state.missedDepTotal.value > 0.01" size="small" type="danger">
        少计折旧 {{ fmtAmt(state.missedDepTotal.value) }}
      </el-tag>
    </div>

    <!-- 方法论：预定可使用状态 / CAS4 -->
    <div class="methodology-context">
      <p><strong>达到预定可使用状态的判断标准（CAS4 实务五条件，均须满足方可转固）：</strong></p>
      <ol>
        <li>实体建造/安装工作已经完成（条件①）</li>
        <li>建造结果与设计要求相符，可投入使用（条件②）</li>
        <li>试运转/试生产结果表明能够正常运行（条件③）</li>
        <li>归属于达到预定可使用状态前的必要支出已能可靠确定（条件④）</li>
        <li>资产已投入使用或具备投入使用条件（条件⑤）</li>
      </ol>
      <p class="method-note">
        编制思路：<strong>实质重于形式</strong>——表一查「该转未转」（防少计折旧），表二查「已转时点」（对照验收/投产证据）；暂估转固在决算后只调成本、不调已提折旧。
      </p>
    </div>

    <!-- 二、审计程序 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、审计程序</span>
          <div class="section-header-actions" v-if="!isReadonly">
            <el-button size="small" type="primary" @click="handleSyncFromH2">从 H2-2 带入</el-button>
            <el-button size="small" @click="handleSyncFromH213">H2-13 达可用→挂账</el-button>
            <el-button size="small" type="success" plain :loading="state.h1Pulling.value" @click="handlePullH1Amounts">
              勾稽 H1 入账
            </el-button>
            <el-button size="small" :loading="state.postPeriodPulling.value" @click="handlePullPostPeriod">
              拉期后转固凭证
            </el-button>
            <el-button
              size="small"
              type="warning"
              :disabled="!(state.missedDepTotal.value > 0.01)"
              @click="handlePushDepAje"
            >
              折旧影响→H2-3
            </el-button>
            <el-button size="small" @click="handlePublishToH1">联动 → H1</el-button>
          </div>
        </div>
      </template>

      <div class="proc-hint">
        <ol>
          <li>选取重大在建工程项目，结合预算进度、合同工期、现场盘点（H2-13）判断是否已达预定可使用状态</li>
          <li>对期末仍挂列在建者，核查未转固原因及期后转固；对已转固者，核对验收/投产时点与入账时点</li>
          <li>转固金额与 H2-2「本期转固」、H1 固定资产增加勾稽；差异须说明或调整（→H2-3）</li>
        </ol>
      </div>
    </el-card>

    <!-- 表一：CIP 挂账（延迟转固风险） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>（1）检查重大在建工程完工及转固情况</span>
          <div class="section-header-actions">
            <el-tag size="small">净值合计 {{ fmtAmt(state.cipNetTotal.value) }}</el-tag>
            <el-button size="small" circle @click="openReview('H2-5')">💬</el-button>
          </div>
        </div>
      </template>
      <p class="table-purpose">目的：识别已达预定可使用状态仍挂列在建、可能延迟转固少计折旧的项目。</p>

      <el-table
        :data="state.cipRows.value"
        border
        stripe
        size="small"
        max-height="420"
        class="transfer-table"
        :row-class-name="cipRowClass"
      >
        <el-table-column type="index" label="#" width="40" fixed align="center" />
        <el-table-column prop="name" label="工程项目名称及设备" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCipChange(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="在建工程期末余额" align="center">
          <el-table-column prop="cipOriginal" label="原值" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.cipOriginal" size="small" class="amt-input"
                @change="onCipChange(row.rowId, 'cipOriginal', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.cipOriginal) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="capitalizedInterest" label="利息资本化" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.capitalizedInterest" :controls="false" size="small" class="amt-input"
                @change="onCipChange(row.rowId, 'capitalizedInterest', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.capitalizedInterest) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="减值准备" min-width="90" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.impairment" size="small" class="amt-input"
                @change="onCipChange(row.rowId, 'impairment', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell amt-cell" title="=原值-减值">{{ fmtAmt(row.cipNet) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="budget" label="总预算" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.budget" :controls="false" size="small" class="amt-input"
              @change="onCipChange(row.rowId, 'budget', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.budget) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投入占预算%" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=原值/预算×100">
              {{ row.budgetRatio == null ? '-' : row.budgetRatio.toFixed(1) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="plannedReadyDate" label="预计完工/到货" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.plannedReadyDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCipChange(row.rowId, 'plannedReadyDate', $event)" />
            <span v-else>{{ row.plannedReadyDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="startDate" label="开工/供货" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.startDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCipChange(row.rowId, 'startDate', $event)" />
            <span v-else>{{ row.startDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="readyCriteria" label="达可用状态标准" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.readyCriteria" size="small"
              placeholder="合同/设计/投产标准"
              @change="onCipChange(row.rowId, 'readyCriteria', $event)" />
            <span v-else>{{ row.readyCriteria || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="readyForUse" label="是否已达可用/在用" min-width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="readySelectValue(row.readyForUse)" size="small" style="width:100%"
              @change="(v: string) => onCipChange(row.rowId, 'readyForUse', v === '是' ? true : v === '否' ? false : null)">
              <el-option label="—" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.readyForUse === true ? 'danger' : 'info'" size="small">
              {{ row.readyForUse === true ? '是' : row.readyForUse === false ? '否' : '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="readyDate" label="达可用状态时间" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.readyDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCipChange(row.rowId, 'readyDate', $event)" />
            <span v-else>{{ row.readyDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="notTransferReason" label="未转固原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.notTransferReason" size="small"
              @change="onCipChange(row.rowId, 'notTransferReason', $event)" />
            <span v-else>{{ row.notTransferReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="proposedTransferPct" label="拟转固%" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.proposedTransferPct" :controls="false" size="small" class="amt-input"
              @change="onCipChange(row.rowId, 'proposedTransferPct', $event)" />
            <span v-else>{{ row.proposedTransferPct ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="postPeriodTransfer" label="期后转固情况" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.postPeriodTransfer" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
              @change="onCipChange(row.rowId, 'postPeriodTransfer', $event)" />
            <span v-else :title="row.postPeriodVoucherNos">{{ row.postPeriodTransfer || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLifeYears" label="年限" width="64" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLifeYears" :controls="false" size="small" class="amt-input"
              @change="onCipChange(row.rowId, 'usefulLifeYears', $event)" />
            <span v-else>{{ row.usefulLifeYears || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="salvageRatePct" label="残值%" width="64" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.salvageRatePct" size="small" class="amt-input"
              @change="onCipChange(row.rowId, 'salvageRatePct', $event)" />
            <span v-else>{{ row.salvageRatePct ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="少计折旧" min-width="100" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell amt-cell', { 'error-amount': row.missedDepAmount > 0.01 }]"
              :title="`${row.missedDepMonths}个月×月折旧`"
            >
              {{ fmtAmt(row.missedDepAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="60" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isAbnormal" type="danger" size="small">是</el-tag>
            <span v-else>否</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="44" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeCipRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddCipRow">+ 新增挂账工程</el-button>
      </div>
    </el-card>

    <!-- 表二：已转固时点检查 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>（2）对本期重大转固在建工程的时点检查</span>
          <div class="section-header-actions">
            <el-tag size="small">转固合计 {{ fmtAmt(state.totalTransfer.value) }}</el-tag>
            <el-tag size="small" type="info">五条件满足 {{ state.metCount.value }}/{{ state.rows.value.length }}</el-tag>
          </div>
        </div>
      </template>
      <p class="table-purpose">目的：以验收、试生产、正式投产等实质证据核验转固时点，并完成 CAS4 五条件判定与 H1 金额勾稽。</p>

      <el-table
        :data="state.rows.value"
        border
        stripe
        size="small"
        max-height="480"
        class="transfer-table"
        :row-class-name="transferRowClass"
      >
        <el-table-column type="index" label="#" width="40" fixed align="center" />
        <el-table-column prop="name" label="工程项目名称及设备" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCellChange(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="固定资产相关金额" align="center">
          <el-table-column prop="faOriginal" label="原值" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.faOriginal" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'faOriginal', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.faOriginal) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="faAccumDep" label="累计折旧" min-width="90" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.faAccumDep" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'faAccumDep', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.faAccumDep) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="faImpairment" label="减值" min-width="80" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.faImpairment" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'faImpairment', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.faImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell amt-cell" title="=原值-累计折旧-减值">{{ fmtAmt(row.faNet) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="transferDate" label="转固时点" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.transferDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'transferDate', $event)" />
            <span v-else>{{ row.transferDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transferAmount" label="转固金额" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.transferAmount" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'transferAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transferAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetCategory" label="转入资产类别" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small"
              @change="onCellChange(row.rowId, 'assetCategory', $event)" />
            <span v-else>{{ row.assetCategory || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="施工验收（决算）" align="center">
          <el-table-column prop="acceptanceDate" label="验收日期" min-width="110">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.acceptanceDate" type="date" size="small"
                value-format="YYYY-MM-DD" style="width:100%"
                @change="onCellChange(row.rowId, 'acceptanceDate', $event)" />
              <span v-else>{{ row.acceptanceDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="acceptanceAmount" label="决算金额" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" v-model="row.acceptanceAmount" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'acceptanceAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.acceptanceAmount) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="readyCriteria" label="达可用状态标准" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.readyCriteria" size="small"
              @change="onCellChange(row.rowId, 'readyCriteria', $event)" />
            <span v-else>{{ row.readyCriteria || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="trialProductionDate" label="试生产日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.trialProductionDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'trialProductionDate', $event)" />
            <span v-else>{{ row.trialProductionDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="officialProductionDate" label="正式投产日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.officialProductionDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'officialProductionDate', $event)" />
            <span v-else>{{ row.officialProductionDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="延迟天数" min-width="80" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'error-amount': row.delayDays > 180, 'warning-value': row.delayDays > 30 }]"
              title="=转固日期−实质可用日（投产/试生产/验收）"
            >
              {{ row.delayDays ?? '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLifeYears" label="年限" width="64" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLifeYears" :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'usefulLifeYears', $event)" />
            <span v-else>{{ row.usefulLifeYears || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="salvageRatePct" label="残值%" width="64" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.salvageRatePct" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'salvageRatePct', $event)" />
            <span v-else>{{ row.salvageRatePct ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="少计折旧" min-width="100" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell amt-cell', { 'error-amount': row.missedDepAmount > 0.01 }]"
              :title="`${row.missedDepMonths}个月`"
            >
              {{ fmtAmt(row.missedDepAmount) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="CAS4条件" align="center">
          <el-table-column label="①" width="48" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.condition1" :disabled="isReadonly"
                @change="onCellChange(row.rowId, 'condition1', $event)" />
            </template>
          </el-table-column>
          <el-table-column label="②" width="48" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.condition2" :disabled="isReadonly"
                @change="onCellChange(row.rowId, 'condition2', $event)" />
            </template>
          </el-table-column>
          <el-table-column label="③" width="48" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.condition3" :disabled="isReadonly"
                @change="onCellChange(row.rowId, 'condition3', $event)" />
            </template>
          </el-table-column>
          <el-table-column label="④" width="48" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.condition4" :disabled="isReadonly"
                @change="onCellChange(row.rowId, 'condition4', $event)" />
            </template>
          </el-table-column>
          <el-table-column label="⑤" width="48" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.condition5" :disabled="isReadonly"
                @change="onCellChange(row.rowId, 'condition5', $event)" />
            </template>
          </el-table-column>
          <el-table-column label="判定" width="72" align="center">
            <template #default="{ row }">
              <el-tag :type="row.allConditionsMet ? 'success' : 'danger'" size="small">
                {{ row.allConditionsMet ? '满足' : '不满足' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="h1Amount" label="H1入账金额" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.h1Amount" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'h1Amount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.h1Amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell amt-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]"
              title="=转固金额-H1入账">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="isAbnormal" label="是否异常" min-width="90" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="abnormalSelectValue(row.isAbnormal)"
              size="small"
              style="width:100%"
              @change="(v: string) => onCellChange(row.rowId, 'isAbnormal', v === '是' ? true : v === '否' ? false : null)"
            >
              <el-option label="自动" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.isAbnormal ? 'danger' : 'success'" size="small">
              {{ row.isAbnormal ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="44" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-line">
        转固合计 <strong>{{ fmtAmt(state.totalTransfer.value) }}</strong>
        <span class="sum-gap">H1入账合计 {{ fmtAmt(state.h1Total.value) }}</span>
        <span class="sum-gap" :class="{ 'error-amount': Math.abs(state.totalDifference.value) > 0.01 }">
          差异 {{ fmtAmt(state.totalDifference.value) }}
        </span>
        <span class="sum-gap" :class="{ 'error-amount': state.missedDepTotal.value > 0.01 }">
          少计折旧合计 {{ fmtAmt(state.missedDepTotal.value) }}
        </span>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增已转固工程</el-button>
      </div>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>三、审计说明</span></div>
      </template>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        placeholder="说明样本选取、挂账项目未转固原因核查、已转固时点与验收/投产证据比对结果、与 H2-2/H1 勾稽差异及拟调整事项…"
        :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>四、审计结论</span></div>
      </template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="结论示例：抽查重大项目转固时点与实质可用时点一致，CAS4 五条件满足，未见延迟/提前转固；或说明异常项目影响及调整。"
        :disabled="isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>表一聚焦「该转未转」：已达可用仍挂账且无合理原因/期后转固说明 → 红色异常，关注少计折旧</li>
        <li>「拉期后转固凭证」扫描截止日次日起 3 个月 1601/1604 序时账，按工程名/转固关键词回填</li>
        <li>少计折旧=直线法月折旧×（达可用次月起至转固日或报表日）月数；「折旧影响→H2-3」生成借管理费用/贷累计折旧</li>
        <li>「H2-13 达可用→挂账」将盘点表 readyForUse=是 回写表一（亦可在 H2-13 一键推送）</li>
        <li>表二聚焦「已转时点」：延迟天数=转固日−实质可用日；＞30 天黄、＞180 天红</li>
        <li>CAS4 五条件须全部勾选才判定「满足」；暂估转固决算后调成本、不调已提折旧</li>
        <li>转固合计应与 H2-2 转固列勾稽；「联动 H1」推送固定资产增加</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H2TabTransferCheck.vue — H2-5 转固时点检查
 * 对齐致同：双表（CIP挂账 + 已转固时点）+ CAS4 + 延迟高亮 + H1联动
 */
import { inject, toRef, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH2TransferCheck } from '../../composables/useH2TransferCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2TransferCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  year: toRef(props, 'year'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
  onPublishEvent(event: string, payload: any) {
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: event,
      payload,
    }, { _silent: true } as any).catch(() => { /* best effort */ })
  },
})

function readySelectValue(v: boolean | null): string {
  if (v === true) return '是'
  if (v === false) return '否'
  return ''
}

function abnormalSelectValue(v: boolean | null): string {
  if (v === true) return '是'
  if (v === false) return '否'
  return ''
}

function cipRowClass({ row }: any) {
  if (row.isAbnormal) return 'severe-delay-row'
  return ''
}

function transferRowClass({ row }: any) {
  if (row.delayDays > 180 || (row.allConditionsMet && !row.transferDate)) return 'severe-delay-row'
  if (row.delayDays > 30 || Math.abs(row.difference) > 0.01) return 'delay-row'
  return ''
}

function onCipChange(rowId: string, field: string, value: any) {
  state.updateCipCell(rowId, field, value)
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

async function handleAddCipRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增挂账工程', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addCipRow(value)
  } catch { /* cancelled */ }
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增已转固工程', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value)
  } catch { /* cancelled */ }
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handleSyncFromH2() {
  const { cipAdded, transferAdded } = state.syncFromH2Detail()
  if (cipAdded || transferAdded) {
    ElMessage.success(`已带入：挂账 ${cipAdded} 项，已转固 ${transferAdded} 项`)
  } else {
    ElMessage.info('H2-2 无可新增项目（或明细为空）')
  }
}

function handleSyncFromH213() {
  const res = state.syncReadyFromH213()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

async function handlePullH1Amounts() {
  const res = await state.pullH1RecordedAmounts()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

async function handlePullPostPeriod() {
  const res = await state.pullPostPeriodTransfers()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handlePushDepAje() {
  const res = state.pushDelayDepAjeToH23()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handlePublishToH1() {
  state.publishTransferToH1()
  ElMessage.success('已推送转固事项至 H1')
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
.h2-tab-transfer-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; }
.obj-list { margin: 6px 0 0; padding-left: 20px; line-height: 1.6; }
.tab-toolbar {
  display: flex; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.methodology-context ol { padding-left: 20px; margin: 8px 0 0; }
.method-note { margin: 10px 0 0; color: var(--el-text-color-regular); }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.section-header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.proc-hint, .table-purpose {
  font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 10px; line-height: 1.55;
}
.proc-hint ol { margin: 4px 0 0; padding-left: 18px; }
.transfer-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color); cursor: help;
  font-variant-numeric: tabular-nums;
}
.warning-value { color: var(--el-color-warning); font-weight: 600; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.summary-line {
  padding: 12px 0; font-size: var(--wp-font-size, 13px);
  border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px;
}
.sum-gap { margin-left: 20px; }
.add-row-bar { margin-top: 12px; display: flex; gap: 8px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.severe-delay-row) { background-color: #fef0f0 !important; }
:deep(.delay-row) { background-color: #fdf6ec !important; }
</style>
