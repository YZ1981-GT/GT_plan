<template>
  <div class="g2-voucher-check" data-testid="g2-voucher-check">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G2-8 凭证检查表</h3>
        <p class="sheet-sub">抽样计划 → 本期借方（利息确认）/ 期后贷方（回笼）→ 五项核对 → 检查比例 → 说明与结论</p>
      </div>
      <div class="head-actions">
        <G2ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G2-8"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-5" :context-project-id="projectId" /></span>
        <el-button size="small" @click="openReviewDialog('G2-8-voucher-check')">💬复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="objective-list">
        <li>核实账面记录的应收利息是否真实存在；</li>
        <li>核实所有应当记录的应收利息均已记录，且计入正确的会计期间；</li>
        <li>核实应收利息金额及账务处理按合同约定或测算结果准确入账。</li>
      </ol>
    </el-alert>

    <!-- 二、样本选取 -->
    <section class="plan-card">
      <header class="plan-head">
        <div>
          <h4>二、样本选取方法与概括</h4>
          <p>测试范围、总体与样本、抽样方法（可从 G2-2 带入总体，并与抽凭引擎配合）</p>
        </div>
        <el-button size="small" :disabled="isReadonly" @click="vc.seedPopulationFromDetail(true)">
          从 G2-2 带入总体
        </el-button>
      </header>
      <div class="plan-grid">
        <label>
          <span>总体借方发生额</span>
          <el-input-number
            :model-value="vc.samplingPlan.value.populationDebit"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number | undefined) => vc.updateSamplingPlan({ populationDebit: v ?? 0 })"
          />
        </label>
        <label>
          <span>总体贷方发生额</span>
          <el-input-number
            :model-value="vc.samplingPlan.value.populationCredit"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number | undefined) => vc.updateSamplingPlan({ populationCredit: v ?? 0 })"
          />
        </label>
        <label>
          <span>总体笔数</span>
          <el-input-number
            :model-value="vc.samplingPlan.value.populationCount"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number | undefined) => vc.updateSamplingPlan({ populationCount: v ?? 0 })"
          />
        </label>
        <label>
          <span>金额门槛</span>
          <el-input
            :model-value="vc.samplingPlan.value.amountThreshold"
            size="small"
            :disabled="isReadonly"
            placeholder="如：单笔≥重要性水平"
            @update:model-value="(v: string) => vc.updateSamplingPlan({ amountThreshold: v })"
          />
        </label>
        <label>
          <span>抽样方法</span>
          <el-select
            :model-value="vc.samplingPlan.value.method"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => vc.updateSamplingPlan({ method: v as any })"
          >
            <el-option v-for="o in G2_SAMPLING_METHOD_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </label>
        <label>
          <span>误受风险 (%)</span>
          <el-select
            :model-value="vc.samplingPlan.value.riskOfIncorrectAcceptance"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => vc.updateSamplingPlan({ riskOfIncorrectAcceptance: v as 1 | 5 | 10 })"
          >
            <el-option :value="1" label="1%（扩展系数 1.9）" />
            <el-option :value="5" label="5%（扩展系数 1.6）" />
            <el-option :value="10" label="10%（扩展系数 1.5）" />
          </el-select>
        </label>
        <label>
          <span>可容忍错报</span>
          <el-input-number
            :model-value="vc.samplingPlan.value.tolerableMisstatement"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number | undefined) => vc.updateSamplingPlan({ tolerableMisstatement: v ?? 0 })"
          />
        </label>
        <label class="check-label">
          <el-checkbox
            :model-value="vc.samplingPlan.value.includeRelatedParty"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => vc.updateSamplingPlan({ includeRelatedParty: !!v })"
          />
          <span>重大/关联方交易纳入样本</span>
        </label>
      </div>
      <div v-if="vc.suggestedSampleSize.value != null" class="suggest-size">
        建议样本量（账面价值×扩展系数÷可容忍错报）：
        <b>{{ vc.suggestedSampleSize.value }}</b>
        · 当前样本 {{ vc.debitRows.value.length + vc.creditRows.value.length }} 笔
      </div>
      <el-input
        :model-value="vc.samplingPlan.value.criteriaNote"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 3 }"
        size="small"
        :disabled="isReadonly"
        placeholder="选取标准说明（大额、关键项目、特殊风险等）"
        class="plan-note"
        @update:model-value="(v: string) => vc.updateSamplingPlan({ criteriaNote: v })"
      />
      <el-input
        :model-value="vc.samplingPlan.value.processNote"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 2 }"
        size="small"
        :disabled="isReadonly"
        placeholder="抽样过程简述（如 Excel / IDEA 条件、随机起点等）"
        class="plan-note"
        @update:model-value="(v: string) => vc.updateSamplingPlan({ processNote: v })"
      />
    </section>

    <el-collapse v-if="wpId && projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1132）— 按借贷方向填入借方/贷方区" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1132"
          phase="final"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="year"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <div class="status-bar">
      <span>
        样本 <b>{{ vc.debitRows.value.length + vc.creditRows.value.length }}</b> 笔 ·
        借方 {{ fmt(vc.debitTotals.value.amount) }} · 贷方 {{ fmt(vc.creditTotals.value.amount) }}
      </span>
      <span>
        检查比例
        <b :class="{ warn: ratioPct != null && ratioPct < 0.05 }">
          {{ ratioPct == null ? '—' : `${(ratioPct * 100).toFixed(2)}%` }}
        </b>
        <small v-if="ratioPct == null">（请先填写测试总体）</small>
      </span>
      <span>
        异常 <b :class="{ warn: vc.abnormalCount.value > 0 }">{{ vc.abnormalCount.value }}</b> ·
        待核 <b>{{ vc.pendingCheckCount.value }}</b> ·
        利息差异 {{ fmt(vc.debitTotals.value.variance) }}
      </span>
      <el-button
        v-if="!isReadonly && vc.abnormalCount.value > 0"
        size="small"
        type="warning"
        plain
        @click="onFillAbnormalIndex"
      >
        异常行索引 → G2-4
      </el-button>
    </div>

    <p class="check-legend tip-red">
      <strong>测试提示：</strong>
      <span v-for="item in vc.CHECK_ITEMS" :key="item.key" class="legend-item" :title="item.hint">
        {{ item.label }}
      </span>
    </p>

    <div class="seg-row">
      <el-segmented v-model="activeBlock" :options="blockOptions" size="small" />
      <el-segmented v-model="activeTab" :options="tabOptions" size="small" />
    </div>

    <!-- ═══ 借方：本期发生额 / 利息确认 ═══ -->
    <div v-show="activeBlock === 'debit'" class="block-section">
      <div class="block-head">
        <h4 class="block-title">三、1 本期发生额检查 — 借方（利息确认）</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="vc.addDebitRow()">新增借方行</el-button>
      </div>

      <el-table
        :data="vc.debitRows.value"
        border
        size="small"
        max-height="420"
        :row-class-name="({ row }) => row.isAbnormal ? 'abnormal-row' : ''"
      >
        <el-table-column label="#" width="52" fixed>
          <template #default="{ row }">
            {{ row.seq }}
            <el-tooltip v-if="row.source" :content="row.source" placement="top">
              <span class="sample-flag">📌</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <template v-if="activeTab === 'basic'">
          <el-table-column label="凭证日期" width="118">
            <template #default="{ row }">
              <el-date-picker
                :model-value="row.voucherDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: string) => vc.updateDebitCell(row.id, 'voucherDate', v ?? '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="凭证号" width="100">
            <template #default="{ row }">
              <el-input :model-value="row.voucherNo" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateDebitCell(row.id, 'voucherNo', v)" />
            </template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="row.summary" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateDebitCell(row.id, 'summary', v)" />
            </template>
          </el-table-column>
          <el-table-column label="对方科目" width="100">
            <template #default="{ row }">
              <el-input :model-value="row.counterAccount" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateDebitCell(row.id, 'counterAccount', v)" />
            </template>
          </el-table-column>
          <el-table-column label="借方金额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'amount', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="投资标的" width="110">
            <template #default="{ row }">
              <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateDebitCell(row.id, 'investTarget', v)" />
            </template>
          </el-table-column>
          <el-table-column label="面值" width="100" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.faceValue" size="small" :controls="false" :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'faceValue', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="利率(%)" width="88" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.rate" size="small" :controls="false" :disabled="isReadonly"
                style="width:100%" :precision="4"
                @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'rate', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="天数" width="72" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.accruedDays" size="small" :controls="false" :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'accruedDays', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="测算利息" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula-cell" title="面值×利率/100×天数/365">{{ fmt(row.calculatedInterest) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula-cell" :class="{ warn: Math.abs(row.variance) >= 0.01 }">{{ fmt(row.variance) }}</span>
            </template>
          </el-table-column>
        </template>

        <template v-else-if="activeTab === 'check'">
          <el-table-column label="📎" width="56" align="center">
            <template #default="{ row }">
              <el-upload
                :show-file-list="false"
                accept="image/*,.pdf"
                :disabled="isReadonly"
                :before-upload="(file: File) => handleRowOcr('debit', row.id, file)"
              >
                <el-button size="small" link :loading="ocrLoadingKey === `debit:${row.id}`" :disabled="isReadonly">📎</el-button>
              </el-upload>
            </template>
          </el-table-column>
          <el-table-column label="支持性文件" min-width="130">
            <template #default="{ row }">
              <el-input :model-value="row.supportingDocs" size="small" :disabled="isReadonly"
                placeholder="合同/对账单/回单…"
                @change="(v: string) => vc.updateDebitCell(row.id, 'supportingDocs', v)" />
            </template>
          </el-table-column>
          <el-table-column
            v-for="item in vc.CHECK_ITEMS"
            :key="item.key"
            width="72"
            align="center"
          >
            <template #header>
              <el-tooltip :content="item.hint" placement="top">
                <span>{{ item.label.replace(/^[①-⑤]/, '') }}</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-checkbox
                v-if="!isReadonly"
                :model-value="row[item.key] === true"
                :indeterminate="row[item.key] === null"
                @change="(v: boolean | string | number) => vc.setDebitCheck(row.id, item.key, !!v)"
              />
              <span v-else>{{ row[item.key] === true ? '✓' : row[item.key] === false ? '✗' : '—' }}</span>
            </template>
          </el-table-column>
        </template>

        <template v-else>
          <el-table-column label="索引" width="100">
            <template #default="{ row }">
              <el-input :model-value="row.indexRef" size="small" :disabled="isReadonly" placeholder="G2-4…"
                @change="(v: string) => vc.updateDebitCell(row.id, 'indexRef', v)" />
            </template>
          </el-table-column>
          <el-table-column label="异常" width="72" align="center">
            <template #default="{ row }">
              <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
                {{ row.isAbnormal ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="异常说明" min-width="140">
            <template #default="{ row }">
              <el-input :model-value="row.abnormalDesc" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateDebitCell(row.id, 'abnormalDesc', v)" />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="100">
            <template #default="{ row }">
              <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateDebitCell(row.id, 'remark', v)" />
            </template>
          </el-table-column>
        </template>

        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="vc.removeDebitRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        借方样本合计 {{ fmt(vc.debitTotals.value.amount) }} ·
        测算利息 {{ fmt(vc.debitTotals.value.calculatedInterest) }} ·
        差异 {{ fmt(vc.debitTotals.value.variance) }} ·
        总体借方 {{ fmt(vc.samplingPlan.value.populationDebit) }} ·
        检查比例 {{ debitRatioLabel }}
      </div>
    </div>

    <!-- ═══ 贷方：期后回笼 ═══ -->
    <div v-show="activeBlock === 'credit'" class="block-section">
      <div class="block-head">
        <h4 class="block-title">三、2 期后回笼、核销检查 — 贷方（利息收回）</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="vc.addCreditRow()">新增贷方行</el-button>
      </div>

      <el-table
        :data="vc.creditRows.value"
        border
        size="small"
        max-height="420"
        :row-class-name="({ row }) => row.isAbnormal ? 'abnormal-row' : ''"
      >
        <el-table-column label="#" width="52" fixed>
          <template #default="{ row }">
            {{ row.seq }}
            <el-tooltip v-if="row.source" :content="row.source" placement="top">
              <span class="sample-flag">📌</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <template v-if="activeTab === 'basic'">
          <el-table-column label="凭证日期" width="118">
            <template #default="{ row }">
              <el-date-picker
                :model-value="row.voucherDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: string) => vc.updateCreditCell(row.id, 'voucherDate', v ?? '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="凭证号" width="100">
            <template #default="{ row }">
              <el-input :model-value="row.voucherNo" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateCreditCell(row.id, 'voucherNo', v)" />
            </template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="row.summary" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateCreditCell(row.id, 'summary', v)" />
            </template>
          </el-table-column>
          <el-table-column label="对方科目" width="100">
            <template #default="{ row }">
              <el-input :model-value="row.counterAccount" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateCreditCell(row.id, 'counterAccount', v)" />
            </template>
          </el-table-column>
          <el-table-column label="贷方金额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: number) => vc.updateCreditCell(row.id, 'amount', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="收款银行" width="110">
            <template #default="{ row }">
              <el-input :model-value="row.receivingBank" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateCreditCell(row.id, 'receivingBank', v)" />
            </template>
          </el-table-column>
          <el-table-column label="收款日期" width="118">
            <template #default="{ row }">
              <el-date-picker
                :model-value="row.receiptDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width:100%"
                @update:model-value="(v: string) => vc.updateCreditCell(row.id, 'receiptDate', v ?? '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="到期收回" width="90">
            <template #default="{ row }">
              <el-select :model-value="row.isOnTimeRecovery" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateCreditCell(row.id, 'isOnTimeRecovery', v)">
                <el-option value="是" label="是" />
                <el-option value="否" label="否" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="逾期天数" width="88" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula-cell" :class="{ warn: row.overdueDays > 0 }">{{ row.overdueDays || '—' }}</span>
            </template>
          </el-table-column>
        </template>

        <template v-else-if="activeTab === 'check'">
          <el-table-column label="📎" width="56" align="center">
            <template #default="{ row }">
              <el-upload
                :show-file-list="false"
                accept="image/*,.pdf"
                :disabled="isReadonly"
                :before-upload="(file: File) => handleRowOcr('credit', row.id, file)"
              >
                <el-button size="small" link :loading="ocrLoadingKey === `credit:${row.id}`" :disabled="isReadonly">📎</el-button>
              </el-upload>
            </template>
          </el-table-column>
          <el-table-column label="支持性文件" min-width="130">
            <template #default="{ row }">
              <el-input :model-value="row.supportingDocs" size="small" :disabled="isReadonly"
                placeholder="银行回单/核销审批…"
                @change="(v: string) => vc.updateCreditCell(row.id, 'supportingDocs', v)" />
            </template>
          </el-table-column>
          <el-table-column
            v-for="item in vc.CHECK_ITEMS"
            :key="item.key"
            width="72"
            align="center"
          >
            <template #header>
              <el-tooltip :content="item.hint" placement="top">
                <span>{{ item.label.replace(/^[①-⑤]/, '') }}</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-checkbox
                v-if="!isReadonly"
                :model-value="row[item.key] === true"
                :indeterminate="row[item.key] === null"
                @change="(v: boolean | string | number) => vc.setCreditCheck(row.id, item.key, !!v)"
              />
              <span v-else>{{ row[item.key] === true ? '✓' : row[item.key] === false ? '✗' : '—' }}</span>
            </template>
          </el-table-column>
        </template>

        <template v-else>
          <el-table-column label="索引" width="100">
            <template #default="{ row }">
              <el-input :model-value="row.indexRef" size="small" :disabled="isReadonly" placeholder="G2-4/G2-6…"
                @change="(v: string) => vc.updateCreditCell(row.id, 'indexRef', v)" />
            </template>
          </el-table-column>
          <el-table-column label="异常" width="72" align="center">
            <template #default="{ row }">
              <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
                {{ row.isAbnormal ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="异常说明" min-width="140">
            <template #default="{ row }">
              <el-input :model-value="row.abnormalDesc" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateCreditCell(row.id, 'abnormalDesc', v)" />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="100">
            <template #default="{ row }">
              <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
                @change="(v: string) => vc.updateCreditCell(row.id, 'remark', v)" />
            </template>
          </el-table-column>
        </template>

        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="vc.removeCreditRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        贷方样本合计 {{ fmt(vc.creditTotals.value.amount) }} ·
        逾期 {{ vc.creditTotals.value.overdueCount }} 笔 ·
        总体贷方 {{ fmt(vc.samplingPlan.value.populationCredit) }} ·
        检查比例 {{ creditRatioLabel }}
      </div>
    </div>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="voucher-note"
      conclusion-ai-section="voucher-check-conclusion"
      :related-context="{
        样本笔数: vc.debitRows.value.length + vc.creditRows.value.length,
        检查比例: ratioPct == null ? '未填总体' : `${(ratioPct * 100).toFixed(1)}%`,
        异常: vc.abnormalCount.value,
        利息差异: vc.debitTotals.value.variance,
        逾期: vc.creditTotals.value.overdueCount,
      }"
      note-placeholder="三、审计说明：抽样范围与方法、本期/期后检查覆盖、五项核对异常及是否调整（可索引 G2-4）。"
      note-hint="覆盖总体、样本、核对程序、测算差异与异常处理。"
      conclusion-placeholder="四、审计结论：选用下方 A/B/C 模板或自行表述。"
      conclusion-hint="A 未见异常；B 除已调整外未见异常；C 范围受限无法结论。"
    />

    <div v-if="!isReadonly" class="conclusion-templates">
      <span class="tpl-label">结论模板：</span>
      <el-button size="small" @click="applyConclusion('A')">A 未见异常</el-button>
      <el-button size="small" @click="applyConclusion('B')">B 除调整外未见异常</el-button>
      <el-button size="small" @click="applyConclusion('C')">C 范围受限</el-button>
    </div>

    <details class="prep-hint" open>
      <summary>📋 编制说明（方法论）</summary>
      <div class="prep-body">
        <p><strong>说明与结论：</strong>应描述执行的检查程序、结果、已调整/未调整事项及审计范围受限情况。结论可参考 A/B/C。</p>
        <p><strong>选取测试项目：</strong></p>
        <ul>
          <li><b>全部项目</b>：总体较小、存在特殊风险项目、或自动化重复计算时，宜检查全部。</li>
          <li><b>特殊风险</b>：舞弊风险、重大异常交易（债务重组/非货币等）、重大关联方、管理层凌驾等应重点覆盖。</li>
          <li><b>特定项目</b>：大额或关键项目、超过设定金额门槛的项目、用于其他测试目的的项目。</li>
          <li><b>审计抽样</b>：统计抽样需随机选取并用概率评价；细节测试常用货币单位抽样（MUS），抽样单元可为 1 元账面金额。</li>
          <li><b>分层</b>：可将总体按金额等特征分层，降低变异性、提高效率。</li>
        </ul>
        <p><strong>样本量参考：</strong>样本规模 ≈ 账面价值 / 风险系数；预计错报扩展系数：</p>
        <table class="factor-table">
          <thead>
            <tr><th>误受风险 (%)</th><th>扩展系数</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in G2_EXPANSION_FACTORS" :key="r.riskPct">
              <td>{{ r.riskPct }}</td>
              <td>{{ r.factor }}</td>
            </tr>
          </tbody>
        </table>
        <p class="cas-basis">依据：CAS 1301 / 1314 审计抽样；CAS 22 金融工具；细节测试目标见本表「一、审计目标」。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, watch, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useG2VoucherCheck,
  G2_SAMPLING_METHOD_OPTIONS,
  G2_EXPANSION_FACTORS,
  G2_CONCLUSION_TEMPLATES,
  calcInspectionRatio,
} from '../composables/useG2VoucherCheck'
import GtIndexChip from '../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import G2ImportExportDropdown from './G2ImportExportDropdown.vue'
import G2AuditTextCards from './G2AuditTextCards.vue'
import type { SampledVoucher, FillMode, Phase } from '../composables/useSamplingAlgorithms'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
  bsDate?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')

const vc = useG2VoucherCheck({
  wpId: computed(() => props.wpId ?? ''),
  projectId: computed(() => props.projectId ?? ''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

async function onImported() {
  emit('imported')
  await new Promise((r) => setTimeout(r, 400))
  const ok = vc.hydrateFromFlat(props.allResponses.get('G2-8-rows')?.remark)
  if (ok) ElMessage.success('已从导入数据还原借/贷检查区')
}

const activeBlock = ref<'debit' | 'credit'>('debit')
const activeTab = ref<'basic' | 'check' | 'result'>('basic')
const blockOptions = [
  { label: '三、1 本期借方（利息确认）', value: 'debit' },
  { label: '三、2 期后贷方（回笼）', value: 'credit' },
]
const tabOptions = [
  { label: '基础/测算', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '异常/索引', value: 'result' },
]

const year = computed(() => {
  if (props.bsDate && props.bsDate.length >= 4) return parseInt(props.bsDate.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

const ratioPct = computed(() => vc.inspectionRatio.value)

const debitRatioLabel = computed(() => {
  const r = calcInspectionRatio(vc.debitTotals.value.amount, vc.samplingPlan.value.populationDebit)
  return r == null ? '—' : `${(r * 100).toFixed(2)}%`
})
const creditRatioLabel = computed(() => {
  const r = calcInspectionRatio(vc.creditTotals.value.amount, vc.samplingPlan.value.populationCredit)
  return r == null ? '—' : `${(r * 100).toFixed(2)}%`
})

function fmt(v: unknown): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—'
  if (v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  vc.applySamplingResults(payload.samples, payload.fillMode)
  ElMessage.success(`已按借贷方向填入 ${payload.samples.length} 笔抽凭样本`)
}

function applyConclusion(key: keyof typeof G2_CONCLUSION_TEMPLATES): void {
  auditConclusion.value = G2_CONCLUSION_TEMPLATES[key]
}

function onFillAbnormalIndex(): void {
  const n = vc.fillAbnormalIndexToAdjustment(false)
  if (n > 0) ElMessage.success(`已为 ${n} 行异常填入索引 G2-4`)
  else ElMessage.info('异常行均已有索引，或当前无异常')
}

const ocrLoadingKey = ref<string | null>(null)
const OCR_FIELD_MAP: Record<string, string> = {
  date: 'voucherDate', 凭证日期: 'voucherDate', voucher_date: 'voucherDate',
  voucher_no: 'voucherNo', 凭证号: 'voucherNo',
  summary: 'summary', 摘要: 'summary', 业务内容: 'summary',
  amount: 'amount', 金额: 'amount',
  counter_account: 'counterAccount', 对方科目: 'counterAccount',
}

async function handleRowOcr(
  side: 'debit' | 'credit',
  rowId: string,
  file: File,
): Promise<boolean> {
  if (props.isReadonly || !props.wpId) return false
  ocrLoadingKey.value = `${side}:${rowId}`
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return false
    }
    const patch: Record<string, string | number> = {}
    for (const [ocrKey, val] of Object.entries(fields)) {
      const target = OCR_FIELD_MAP[ocrKey]
      if (target && val != null && String(val).trim() !== '') patch[target] = val as string | number
    }
    if (!Object.keys(patch).length) {
      ElMessage.info('OCR完成，识别字段无法匹配')
      return false
    }
    const preview = Object.entries(patch).map(([k, v]) => `${k}: ${v}`).join('，')
    await ElMessageBox.confirm(`识别到凭证信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
    })
    for (const [k, v] of Object.entries(patch)) {
      if (side === 'debit') vc.updateDebitCell(rowId, k as any, v)
      else vc.updateCreditCell(rowId, k as any, v)
    }
    if (side === 'debit') vc.updateDebitCell(rowId, 'supportingDocs', file.name)
    else vc.updateCreditCell(rowId, 'supportingDocs', file.name)
    ElMessage.success('已填入识别结果')
  } catch (e) {
    if (e !== 'cancel') ElMessage.warning('OCR识别失败')
  } finally {
    ocrLoadingKey.value = null
  }
  return false
}

const NOTE_KEY = 'G2-8-audit-note'
const CONCLUSION_KEY = 'G2-8-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')

watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => { if (v != null) auditNote.value = v })
watch(() => props.allResponses.get(CONCLUSION_KEY)?.remark, (v) => { if (v != null) auditConclusion.value = v })
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})

onMounted(() => {
  vc.seedPopulationFromDetail(false)
})
</script>

<style scoped>
.g2-voucher-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-voucher-check :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.title-block { flex: 1; min-width: 200px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.sheet-sub { margin: 4px 0 0; color: #909399; font-size: 12px; }
.head-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }

.objective-alert { margin-bottom: 12px; }
.objective-list { margin: 6px 0 0; padding-left: 18px; line-height: 1.55; }

.plan-card {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
.plan-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}
.plan-head h4 { margin: 0; font-size: 14px; }
.plan-head p { margin: 4px 0 0; color: #909399; font-size: 12px; }
.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}
.plan-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #606266; }
.check-label { flex-direction: row !important; align-items: center; gap: 8px !important; padding-top: 18px; }
.plan-note { margin-top: 8px; }
.suggest-size {
  margin-top: 10px;
  padding: 6px 10px;
  font-size: 12px;
  color: #606266;
  background: #f0f9eb;
  border-radius: 4px;
}
.suggest-size b { color: #67c23a; }

.sampling-collapse { margin-bottom: 12px; }

.status-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
}
.status-bar .warn { color: #e6a23c; }

.check-legend {
  margin: 0 0 10px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.tip-red strong { color: #c45656; }
.legend-item {
  display: inline-block;
  margin-right: 10px;
  padding: 1px 6px;
  background: #fef0f0;
  border-radius: 3px;
  color: #c45656;
  cursor: help;
}

.seg-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }

.block-section { margin-bottom: 16px; }
.block-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}
.block-title { margin: 0; font-size: 14px; }
.block-subtotal {
  margin-top: 8px;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 0;
  border-top: 1px solid #ebeef5;
}

.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.formula-cell.warn, .warn { color: #e6a23c; font-weight: 600; }
.sample-flag { margin-left: 2px; font-size: 11px; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.abnormal-row) { background: #fef0f0 !important; }

.conclusion-templates {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 8px 0 12px;
}
.tpl-label { font-size: 12px; color: #606266; }

.prep-hint {
  margin-top: 8px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-body { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.65; }
.prep-body ul { margin: 4px 0; padding-left: 18px; }
.prep-body p { margin: 6px 0; }
.factor-table {
  border-collapse: collapse;
  margin: 6px 0 10px;
  font-size: 12px;
}
.factor-table th, .factor-table td {
  border: 1px solid #dcdfe6;
  padding: 4px 12px;
  text-align: center;
}
.factor-table th { background: #f5f7fa; }
.cas-basis { color: #909399; }
</style>
