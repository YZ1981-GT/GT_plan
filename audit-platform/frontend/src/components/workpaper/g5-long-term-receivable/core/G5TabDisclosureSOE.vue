<template>
  <div class="g5-disclosure-soe" data-testid="g5-disclosure-soe">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（国企）</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G5-附注国企" :context-project-id="props.projectId" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="onRefresh">
          从 G5-1/2/3 取数
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="onSyncPortfolios">
          同步组合（政策/G5-3）
        </el-button>
        <el-button
          size="small"
          type="primary"
          text
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="fillAiDraft"
        >
          🤖 AI 辅助
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          data-testid="g5-disclosure-soe-sync-notes"
          :loading="isSyncing"
          :disabled="isReadonly || !props.projectId"
          @click="syncToDisclosureNotes"
        >
          同步到附注
        </el-button>
        <GtReviewTrigger section-id="G5-disclosure-soe" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：按国企附注格式披露长期应收款性质分类、终止确认与继续涉入、坏账计提（单项/组合）及账龄，与 G5-1 审定勾稽。"
    />

    <el-alert
      v-if="dis.adjudicatedAmount.value !== null"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已联动审定净值（1531）：{{ fmt(dis.adjudicatedAmount.value) }}
      <template v-if="dis.lastSyncHint.value"> · 取数 {{ dis.lastSyncHint.value }}</template>
    </el-alert>

    <el-alert
      v-if="!dis.tieOut.value.matched"
      type="warning"
      :closable="false"
      :title="`勾稽差异：表(1)合计余额 ${fmt(dis.tieOut.value.natureTotalEnd)} / 坏账 ${fmt(dis.tieOut.value.natureProvEnd)} ≠ 表(4)合计余额 ${fmt(dis.tieOut.value.methodTotalEnd)} / 坏账 ${fmt(dis.tieOut.value.methodProvEnd)}`"
    />

    <el-alert
      :type="dis.portfolioConsistency.value.status === 'matched' ? 'success' : dis.portfolioConsistency.value.status === 'mismatch' ? 'warning' : 'info'"
      :closable="false"
      :title="`【注意：与会计政策中披露的组合保持一致】${dis.portfolioConsistency.value.message}`"
    />

    <!-- (1) 按性质 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">（1）长期应收款按性质披露</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addNatureRow()">
            + 添加行（可无限）
          </el-button>
        </div>
      </template>

      <el-table
        :data="dis.natureDisplayRows.value"
        border
        size="small"
        :row-class-name="natureRowClass"
      >
        <el-table-column label="项目" min-width="180" fixed>
          <template #default="{ row }">
            <span
              :style="{ paddingLeft: `${row.indent * 14}px` }"
              :class="{
                'is-total': row.kind === 'total' || row.kind === 'subtotal',
                'is-highlight': row.rowKey === 'deposit' || row.rowKey === 'related',
              }"
            >
              <el-input
                v-if="row.kind === 'custom' && !isReadonly"
                :model-value="row.label"
                size="small"
                @change="(v: string) => dis.patchNature(row.id, { label: v })"
              />
              <template v-else>{{ row.label }}</template>
            </span>
          </template>
        </el-table-column>

        <el-table-column label="期末余额" align="center">
          <el-table-column label="账面余额" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.end.balance"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchNature(row.id, { end: { balance: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.end.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.end.provision"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchNature(row.id, { end: { provision: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.end.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="110" align="right">
            <template #default="{ row }">
              <span class="amount-cell">{{ fmt(dis.bookValue(row.end)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期初余额" align="center">
          <el-table-column label="账面余额" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.prior.balance"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchNature(row.id, { prior: { balance: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.prior.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.prior.provision"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchNature(row.id, { prior: { provision: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.prior.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="110" align="right">
            <template #default="{ row }">
              <span class="amount-cell">{{ fmt(dis.bookValue(row.prior)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末折现率区间" width="110">
          <template #default="{ row }">
            <el-input
              v-if="row.editable && row.kind !== 'deduction' && !isReadonly"
              :model-value="row.endDiscountRate"
              size="small"
              placeholder="—"
              @change="(v: string) => dis.patchNature(row.id, { endDiscountRate: v })"
            />
            <span v-else>{{ row.endDiscountRate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="" width="48" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.kind === 'custom'"
              size="small"
              type="danger"
              link
              @click="dis.removeNatureRow(row.id)"
            >
              删
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <p class="template-tip">
        注：因金融资产转移而终止确认、但继续涉入形成资产/负债的，分别在下列（2）（3）披露；与保理（G5-7）结论勾稽。
      </p>
    </el-card>

    <!-- (2) 终止确认 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">（2）终止确认的长期应收款</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addDerecogRow()">
            + 添加行
          </el-button>
        </div>
      </template>
      <el-table
        :data="dis.state.value.derecogRows"
        border
        size="small"
        empty-text="本期无终止确认；如有保理/转让请添加行"
      >
        <el-table-column label="项目" min-width="140">
          <template #default="{ row }">
            <el-input
              :model-value="row.item"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => dis.patchDerecog(row.id, { item: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="转移方式" min-width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.transferMethod"
              size="small"
              :disabled="isReadonly"
              placeholder="保理/证券化等"
              @change="(v: string) => dis.patchDerecog(row.id, { transferMethod: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="终止确认金额" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.amount"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number) => dis.patchDerecog(row.id, { amount: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="与终止确认相关的利得或损失" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.gainLoss"
              size="small"
              :controls="false"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number) => dis.patchDerecog(row.id, { gainLoss: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="dis.removeDerecogRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (3) 继续涉入 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <span class="card-title">（3）转移长期应收款且继续涉入形成的资产、负债</span>
      </template>
      <el-table :data="continuingRows" border size="small">
        <el-table-column prop="label" label="项目" min-width="160" />
        <el-table-column label="期末余额" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.amount"
              size="small"
              class="amt-input"
              @change="(v: number) => onContinuingChange(row.key, v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- (4) 坏账方法说明 + 计提概况 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <span class="card-title">（4）坏账准备计提情况</span>
      </template>

      <div class="provision-method-box">
        <div class="provision-method-label">坏账准备计提方法说明（模板红区）</div>
        <el-input
          :model-value="dis.state.value.provisionMethodNote"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          :placeholder="provisionPlaceholder"
          @update:model-value="dis.setProvisionMethodNote"
        />
      </div>

      <el-table
        :data="dis.methodDisplayRows.value"
        border
        size="small"
        class="method-table"
        :row-class-name="methodRowClass"
      >
        <el-table-column label="类别" min-width="160" fixed>
          <template #default="{ row }">
            <span :class="{ 'is-total': row.kind === 'total' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="账面余额" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.end.balance"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchMethod(row.id, { end: { balance: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.end.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="比例(%)" width="88" align="right">
            <template #default="{ row }">
              {{ dis.fmtRate(methodBalanceShare(row, 'end')) }}
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.end.provision"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchMethod(row.id, { end: { provision: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.end.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="ECL率(%)" width="88" align="right">
            <template #default="{ row }">
              {{ dis.fmtRate(dis.safeRate(row.end.provision, row.end.balance)) }}
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="110" align="right">
            <template #default="{ row }">
              <span class="amount-cell">{{ fmt(dis.bookValue(row.end)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初数" align="center">
          <el-table-column label="账面余额" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.prior.balance"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchMethod(row.id, { prior: { balance: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.prior.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="比例(%)" width="88" align="right">
            <template #default="{ row }">
              {{ dis.fmtRate(methodBalanceShare(row, 'prior')) }}
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.editable && !isReadonly"
                :model-value="row.prior.provision"
                size="small"
                class="amt-input"
                @change="(v: number) => dis.patchMethod(row.id, { prior: { provision: v ?? 0 } })"
              />
              <span v-else class="amount-cell">{{ fmt(row.prior.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="ECL率(%)" width="88" align="right">
            <template #default="{ row }">
              {{ dis.fmtRate(dis.safeRate(row.prior.provision, row.prior.balance)) }}
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="110" align="right">
            <template #default="{ row }">
              <span class="amount-cell">{{ fmt(dis.bookValue(row.prior)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 单项明细 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">按单项计提坏账准备</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addIndividualDetail()">
            + 添加行
          </el-button>
        </div>
      </template>
      <el-table :data="individualTableData" border size="small" max-height="360">
        <el-table-column label="债务人名称" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.name"
              size="small"
              @change="(v: string) => dis.patchIndividualDetail(row.id, { name: v })"
            />
            <span v-else class="is-total">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末账面余额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endBalance"
              size="small"
              class="amt-input"
              @change="(v: number) => dis.patchIndividualDetail(row.id, { endBalance: v ?? 0 })"
            />
            <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末坏账准备" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endProvision"
              size="small"
              class="amt-input"
              @change="(v: number) => dis.patchIndividualDetail(row.id, { endProvision: v ?? 0 })"
            />
            <span v-else class="amount-cell">{{ fmt(row.endProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初账面余额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.priorBalance"
              size="small"
              class="amt-input"
              @change="(v: number) => dis.patchIndividualDetail(row.id, { priorBalance: v ?? 0 })"
            />
            <span v-else class="amount-cell">{{ fmt(row.priorBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初坏账准备" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.priorProvision"
              size="small"
              class="amt-input"
              @change="(v: number) => dis.patchIndividualDetail(row.id, { priorProvision: v ?? 0 })"
            />
            <span v-else class="amount-cell">{{ fmt(row.priorProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="ECL率(%)" width="88" align="right">
          <template #default="{ row }">
            {{ dis.fmtRate(dis.safeRate(row.endProvision, row.endBalance)) }}
          </template>
        </el-table-column>
        <el-table-column label="计提理由" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endReason"
              size="small"
              @change="(v: string) => dis.patchIndividualDetail(row.id, { endReason: v })"
            />
            <span v-else>{{ row.endReason }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              size="small"
              type="danger"
              link
              @click="dis.removeIndividualDetail(row.id)"
            >
              删
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 组合账龄 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">按组合计提坏账准备</span>
          <div class="aging-toolbar">
            <span class="muted">账龄口径</span>
            <el-select
              :model-value="dis.state.value.agingPreset || 'THREE_YEAR'"
              size="small"
              style="width: 120px"
              :disabled="isReadonly"
              @change="onAgingPresetChange"
            >
              <el-option label="3年段" value="THREE_YEAR" />
              <el-option label="5年段" value="FIVE_YEAR" />
              <el-option label="自定义" value="CUSTOM" />
            </el-select>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addPortfolio()">
              + 新增组合块
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        class="three-stage-tip"
        title="【提示：若采用三阶段模型对长期应收款计提坏账准备，请参考其他应收款坏账准备的披露。】"
      />

      <div
        v-for="(pf, idx) in dis.state.value.portfolios"
        :key="pf.id"
        class="portfolio-block"
      >
        <div class="portfolio-head">
          <span class="portfolio-idx">组合计提项目：</span>
          <el-input
            :model-value="pf.name"
            size="small"
            class="portfolio-name"
            placeholder="XXX（与会计政策一致）"
            :disabled="isReadonly"
            @change="(v: string) => dis.patchPortfolioName(pf.id, v)"
          />
          <el-tag v-if="pf.fromPolicy" size="small" type="success">政策同步</el-tag>
          <el-tag size="small" type="info">组合{{ idx + 1 }}</el-tag>
          <el-button
            size="small"
            type="primary"
            link
            :disabled="isReadonly"
            @click="dis.addAgingBand(pf.id)"
          >
            + 账龄段（……）
          </el-button>
          <el-button
            v-if="!isReadonly && dis.state.value.portfolios.length > 1"
            size="small"
            type="danger"
            link
            @click="dis.removePortfolio(pf.id)"
          >
            删除组合
          </el-button>
        </div>

        <el-table :data="pf.agingRows" border size="small" :row-class-name="agingRowClass">
          <el-table-column label="账龄" width="120" fixed>
            <template #default="{ row }">
              <span :class="{ 'is-total': row.kind === 'total' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" align="center">
            <el-table-column label="长期应收款" width="120" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.kind === 'band' && !isReadonly"
                  :model-value="row.endBalance"
                  size="small"
                  :controls="false"
                  class="amt-input"
                  @change="(v: number) => dis.patchAgingCell(pf.id, row.id, 'endBalance', v ?? 0)"
                />
                <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="坏账准备" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="row.kind === 'band' && !isReadonly"
                  :model-value="row.endProvision"
                  size="small"
                  class="amt-input"
                  @change="(v: number) => dis.patchAgingCell(pf.id, row.id, 'endProvision', v ?? 0)"
                />
                <span v-else class="amount-cell">{{ fmt(row.endProvision) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="ECL率(%)" width="88" align="right">
              <template #default="{ row }">
                {{ dis.fmtRate(dis.safeRate(row.endProvision, row.endBalance)) }}
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="长期应收款" width="120" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.kind === 'band' && !isReadonly"
                  :model-value="row.priorBalance"
                  size="small"
                  :controls="false"
                  class="amt-input"
                  @change="(v: number) => dis.patchAgingCell(pf.id, row.id, 'priorBalance', v ?? 0)"
                />
                <span v-else class="amount-cell">{{ fmt(row.priorBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="坏账准备" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="row.kind === 'band' && !isReadonly"
                  :model-value="row.priorProvision"
                  size="small"
                  class="amt-input"
                  @change="(v: number) => dis.patchAgingCell(pf.id, row.id, 'priorProvision', v ?? 0)"
                />
                <span v-else class="amount-cell">{{ fmt(row.priorProvision) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="ECL率(%)" width="88" align="right">
              <template #default="{ row }">
                {{ dis.fmtRate(dis.safeRate(row.priorProvision, row.priorBalance)) }}
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="48" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.kind === 'band' && !['within1', 'y1to2', 'y2to3'].includes(row.bandKey)"
                size="small"
                type="danger"
                link
                @click="dis.removeAgingBandRow(pf.id, row.id)"
              >
                删
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="isReadonly"
      :note="dis.noteText.value"
      :show-conclusion="false"
      note-title="附注披露说明"
      note-ai-section="disclosure-soe-note"
      :related-context="{
        科目: '1531',
        披露类型: '国企',
        性质合计: dis.tieOut.value.natureTotalEnd,
        坏账合计: dis.tieOut.value.natureProvEnd,
        组合一致性: dis.portfolioConsistency.value.status,
      }"
      note-placeholder="国企长期应收款附注：性质构成、终止确认与继续涉入、单项/组合计提政策与账龄，并说明与 G5-1 审定勾稽…"
      note-hint="结构化表格自动勾稽；红区填写坏账方法说明。保存后发布 disclosure:note-text-updated。"
      :note-min-rows="4"
      @update:note="(v: string) => { dis.noteText.value = v }"
    />

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企与上市共用取数链（G5-1/2/3），但专有（2）终止确认、（3）继续涉入、（4）方法说明红区。</li>
        <li>组合名须与会计政策一致；优先用账龄口径枚举（3年/5年/自定义），必要时仍可用「+ 账龄段」微调。</li>
        <li>比例/ECL 率分母为零显示「—」，避免 Excel 模板中的 #DIV/0!。</li>
        <li>应收保证金、应收关联方为重点关注行（红色标签样式）。</li>
      </ul>
    </details>

    <el-dialog v-model="showAgingDialog" title="自定义账龄段" width="420px" destroy-on-close @close="cancelAgingDialog">
      <p class="muted">每行一个账龄段名称（至少 2 段，最多 10 段）。</p>
      <el-input v-model="agingDraft" type="textarea" :autosize="{ minRows: 6, maxRows: 12 }" />
      <template #footer>
        <el-button @click="cancelAgingDialog">取消</el-button>
        <el-button type="primary" @click="confirmAgingCustom">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G5TabDisclosureSOE — 附注披露信息（国企）
 * 对齐致同 Excel；共享上市取数/勾稽/组合同步，补国企专有段。
 */
import { computed, onMounted, ref, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { useG5DisclosureSoe } from '../../composables/useG5DisclosureSoe'
import { useG5AiGenerate } from '../../composables/useG5AiGenerate'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildG5SoeSyncPayload } from '../../composables/g5DisclosureSyncPayload'
import { G5_NOTE_SECTION } from '../../composables/g5NoteSectionMap'
import { G5_SOE_PROVISION_METHOD_PLACEHOLDER } from '../../composables/g5SoeDisclosureRows'
import type { G5MethodRow } from '../../composables/g5ListedDisclosureRows'
import type { G5AgingPreset } from '../../composables/g5AgingScheme'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData?: unknown
  wpId: string
  projectId: string
  applicableStandards?: string[]
  readonly?: boolean
}>()

const isReadonly = computed(() => !!props.readonly)
const g5Notes = useInjectedG5FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const dis = useG5DisclosureSoe({
  allResponses: g5Notes.allResponses,
  debouncedSave: g5Notes.debouncedSave,
  isReadonly,
})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG5AiGenerate(wpIdRef)
const provisionPlaceholder = G5_SOE_PROVISION_METHOD_PLACEHOLDER

// ─── 同步到附注（§八、17）───────────────────────────────────────────────
// 🔴 国企附注模版对「坏账准备计提情况」只有交叉引用、无表 → 底稿侧的坏账准备 /
//    按单项 / 组合计提系列表**不推附注**（宁缺勿造），只推 3 张：性质 / 终止确认 / 继续涉入。
//    故本变体无动态表名，不需要 `_removed_table_keys`。
const isSyncing = ref(false)
const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || isReadonly.value || !props.projectId) return
  const st = dis.state.value
  const payload = buildG5SoeSyncPayload(props.wpId, props.applicableStandards, {
    natureRows: dis.natureDisplayRows.value,
    derecogRows: st.derecogRows,
    continuing: st.continuing,
    provisionMethodNote: st.provisionMethodNote ?? '',
    noteText: dis.noteText.value ?? '',
  })
  if (!payload) return
  isSyncing.value = true
  try {
    const res: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const rows = Number((res?.data ?? res)?.rows_synced ?? 0)
    ElMessage.success(`已同步 ${rows} 行到附注模块「${G5_NOTE_SECTION.soe} 长期应收款」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// 数据变更后自动同步（防抖 800ms；只读/失败静默）。监听实际数据，不监听提示横幅状态。
watch(
  [
    dis.natureDisplayRows,
    () => dis.state.value.derecogRows,
    () => dis.state.value.continuing,
    () => dis.state.value.provisionMethodNote,
    dis.noteText,
  ],
  () => { autoSync.scheduleAutoSync(syncToDisclosureNotes) },
  { deep: true },
)

function fmt(n: number | null | undefined): string {
  const v = Number(n) || 0
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function methodBalanceShare(row: G5MethodRow, period: 'end' | 'prior'): number | null {
  const total = dis.methodDisplayRows.value.find((r) => r.kind === 'total')
  const denom = period === 'end' ? total?.end.balance : total?.prior.balance
  const num = period === 'end' ? row.end.balance : row.prior.balance
  return dis.safeRate(num, Number(denom) || 0)
}

const individualTableData = computed(() => {
  const rows = dis.state.value.individualDetails
  const endBalance = rows.reduce((s, r) => s + (Number(r.endBalance) || 0), 0)
  const endProvision = rows.reduce((s, r) => s + (Number(r.endProvision) || 0), 0)
  const priorBalance = rows.reduce((s, r) => s + (Number(r.priorBalance) || 0), 0)
  const priorProvision = rows.reduce((s, r) => s + (Number(r.priorProvision) || 0), 0)
  return [
    ...rows.map((r) => ({ ...r, isTotal: false })),
    {
      id: '__total__',
      name: '合计',
      endBalance,
      endProvision,
      endReason: '',
      priorBalance,
      priorProvision,
      priorReason: '',
      isTotal: true,
    },
  ]
})

const continuingRows = computed(() => [
  { key: 'assetEnd' as const, label: '资产', amount: dis.state.value.continuing.assetEnd },
  { key: 'liabilityEnd' as const, label: '负债', amount: dis.state.value.continuing.liabilityEnd },
])

function onContinuingChange(key: 'assetEnd' | 'liabilityEnd', value: number) {
  dis.patchContinuing({ [key]: value })
}

function natureRowClass({ row }: { row: { kind: string; rowKey: string } }) {
  const cls: string[] = []
  if (row.kind === 'total' || row.kind === 'subtotal') cls.push('row-total')
  if (row.kind === 'subrow') cls.push('row-sub')
  if (row.rowKey === 'deposit' || row.rowKey === 'related') cls.push('row-highlight')
  return cls.join(' ')
}
function methodRowClass({ row }: { row: { kind: string } }) {
  return row.kind === 'total' ? 'row-total' : ''
}
function agingRowClass({ row }: { row: { kind: string } }) {
  return row.kind === 'total' ? 'row-total' : ''
}

const showAgingDialog = ref(false)
const agingDraft = ref('')

function onAgingPresetChange(val: G5AgingPreset) {
  if (val === 'CUSTOM') {
    const labels = dis.state.value.customAgingLabels?.length
      ? dis.state.value.customAgingLabels
      : (dis.state.value.portfolios[0]?.agingRows || [])
          .filter((r) => r.kind === 'band')
          .map((r) => r.label)
    agingDraft.value = (labels.length ? labels : ['1年以内', '1-2年', '2-3年', '3年以上']).join('\n')
    showAgingDialog.value = true
    return
  }
  dis.setAgingPreset(val)
}

function confirmAgingCustom() {
  const labels = agingDraft.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (dis.setAgingPreset('CUSTOM', labels)) showAgingDialog.value = false
}

function cancelAgingDialog() {
  showAgingDialog.value = false
}

function onRefresh() {
  dis.refreshFromSources(true)
  ElMessage.success('已从 G5-1 / G5-2 / G5-3 取数')
}

function onSyncPortfolios() {
  const { count } = dis.syncPortfoliosFromSources(true)
  if (!count) {
    ElMessage.warning('未找到组合名称：请先在 G5-8「组合划分」或 G5-3 组合行维护名称')
    return
  }
  ElMessage.success(`已同步 ${count} 个组合名称`)
}

async function fillAiDraft() {
  if (isReadonly.value) return
  const text = await generateAndConfirm(
    'disclosure-soe-note',
    dis.noteText.value || '',
    {
      section: 'soe',
      natureTotal: dis.tieOut.value.natureTotalEnd,
      provisionTotal: dis.tieOut.value.natureProvEnd,
      provisionMethodNote: dis.state.value.provisionMethodNote,
    },
    'AI 附注披露（国企）',
  )
  if (text) dis.noteText.value = text
}

onMounted(async () => {
  try {
    await g5Notes.loadAll()
  } catch {
    /* ignore */
  }
  dis.loadPersisted()
})
</script>

<style scoped>
.g5-disclosure-soe {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 8px;
  flex-wrap: wrap;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.objective-alert,
.sync-hint,
.three-stage-tip {
  margin-bottom: 10px;
}
.disclosure-card {
  margin-bottom: 12px;
}
.card-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.aging-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.muted {
  font-size: 12px;
  color: #909399;
}
.card-title {
  font-weight: 600;
}
.amt-input {
  width: 100%;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}
.is-total {
  font-weight: 600;
}
.is-highlight {
  color: #c45656;
  font-weight: 500;
}
:deep(.row-total) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}
:deep(.row-sub) {
  color: var(--el-text-color-secondary);
}
:deep(.row-highlight td:first-child) {
  color: #c45656;
}
.template-tip {
  margin: 8px 0 0;
  font-size: 12px;
  color: #409eff;
  line-height: 1.6;
}
.provision-method-box {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 4px;
}
.provision-method-label {
  font-size: 12px;
  font-weight: 600;
  color: #c45656;
  margin-bottom: 6px;
}
.method-table {
  margin-top: 4px;
}
.portfolio-block {
  margin-bottom: 16px;
}
.portfolio-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.portfolio-idx {
  font-weight: 600;
  color: #c45656;
}
.portfolio-name {
  max-width: 280px;
}
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.8;
}
</style>
