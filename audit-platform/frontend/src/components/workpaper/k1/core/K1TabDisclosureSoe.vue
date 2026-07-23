<template>
  <div class="k1-disclosure-soe">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（国企）</h3>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip :value="noteTarget.chipValue" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">八、9 · 其他应收款项</el-tag>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="dis.refreshFromSources(true)">
          从源底稿取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          :loading="dis.isSyncing.value"
          :disabled="isReadonly || !projectId"
          @click="dis.syncToNotes()"
        >
          同步至附注
        </el-button>
        <el-button size="small" @click="openReviewDialog('K1-disclosure-soe')">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：按国有企业附注格式披露其他应收款账龄、计提方法、ECL三阶段坏账变动及前五名等，与 K1-1/K1-2/K1-3 勾稽，并回写附注八、9。" />

    <el-alert
      v-if="dis.adjudication.value.receivableEnd"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已联动 K1-1：其他应收款期末 {{ fmt(dis.adjudication.value.receivableEnd) }}
      · 坏账准备 {{ fmt(dis.adjudication.value.badDebtEnd) }}
      <template v-if="dis.lastSyncHint.value"> · 取数 {{ dis.lastSyncHint.value }}</template>
    </el-alert>

    <K1DisclosureTracePanel
      :rows="trace.traceRows.value"
      :open-count="trace.openCount.value"
      @navigate-sheet="(s) => emit('navigate-sheet', s)"
    />

    <el-alert
      v-if="!dis.agingTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`账龄勾稽：小计 ${fmt(dis.agingTieOut.value.subtotal)} ≠ K1-1 审定 ${fmt(dis.adjudication.value.receivableEnd)}（差额 ${fmt(dis.agingTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="!dis.provisionTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`坏账勾稽：账龄表坏账 ${fmt(dis.provisionTieOut.value.agingProvision)} ≠ ECL期末合计 ${fmt(dis.provisionTieOut.value.eclClosing)}（差额 ${fmt(dis.provisionTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="dis.balanceStageMovements.value.length && !dis.balanceStageTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`账面余额三阶段：期末合计 ${fmt(dis.balanceStageTieOut.value.closingTotal)} ≠ K1-1 审定 ${fmt(dis.adjudication.value.receivableEnd)}（差额 ${fmt(dis.balanceStageTieOut.value.diff)}）`"
    />

    <el-collapse v-model="activeSections" class="section-collapse">
      <!-- ① 按账龄 -->
      <el-collapse-item name="aging">
        <template #title>
          <span class="collapse-title">① 按账龄列示其他应收款</span>
          <el-tag size="small" type="warning" class="collapse-tag">附注子表</el-tag>
        </template>
        <SectionHint :guide="sectionGuide('aging')" />
        <el-table :data="dis.agingRows.value" border size="small" :row-class-name="agingRowClass">
          <el-table-column prop="label" label="账龄" min-width="140" />
          <el-table-column label="期末数" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.endAmount"
                size="small"
                :controls="false"
                style="width: 100%"
                @change="(v: number) => dis.updateAgingRow(row.rowId, 'endAmount', v)"
              />
              <span v-else :class="{ 'auto-fill': row.autoFilled }">{{ fmt(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.priorAmount"
                size="small"
                :controls="false"
                style="width: 100%"
                @change="(v: number) => dis.updateAgingRow(row.rowId, 'priorAmount', v)"
              />
              <span v-else :class="{ 'auto-fill': row.autoFilled }">{{ fmt(row.priorAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>

      <!-- ② 按计提方法 -->
      <el-collapse-item name="method">
        <template #title>
          <span class="collapse-title">② 按坏账准备计提方法分类披露</span>
        </template>
        <SectionHint :guide="sectionGuide('method')" />
        <div class="dual-table-label">期末余额</div>
        <el-table :data="dis.methodRows.value" border size="small" class="method-table">
          <el-table-column prop="label" label="类别" min-width="200" />
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.editable && !isReadonly" :model-value="row.endBalance" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updateMethodRow(row.rowKey, 'endBalance', v)" />
              <span v-else>{{ fmt(row.endBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="比例(%)" width="90" align="right">
            <template #default="{ row }">{{ row.endBalancePct != null ? row.endBalancePct.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.editable && !isReadonly" :model-value="row.endProvision" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updateMethodRow(row.rowKey, 'endProvision', v)" />
              <span v-else>{{ fmt(row.endProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="ECL率(%)" width="90" align="right">
            <template #default="{ row }">{{ row.endEclRate != null ? row.endEclRate.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.endBookValue) }}</template>
          </el-table-column>
        </el-table>
        <div class="dual-table-label">期初余额</div>
        <el-table :data="dis.methodRows.value" border size="small" class="method-table">
          <el-table-column prop="label" label="类别" min-width="200" />
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.editable && !isReadonly" :model-value="row.priorBalance" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updateMethodRow(row.rowKey, 'priorBalance', v)" />
              <span v-else>{{ fmt(row.priorBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="比例(%)" width="90" align="right">
            <template #default="{ row }">{{ row.priorBalancePct != null ? row.priorBalancePct.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.editable && !isReadonly" :model-value="row.priorProvision" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updateMethodRow(row.rowKey, 'priorProvision', v)" />
              <span v-else>{{ fmt(row.priorProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="ECL率(%)" width="90" align="right">
            <template #default="{ row }">{{ row.priorEclRate != null ? row.priorEclRate.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.priorBookValue) }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>

      <!-- ③ 单项计提明细 -->
      <el-collapse-item name="individual">
        <template #title><span class="collapse-title">③ 单项计提坏账准备的其他应收款</span></template>
        <SectionHint :guide="sectionGuide('individual')" />
        <el-empty v-if="!dis.individualDetailRows.value.length" description="无单项计提行（可从 K1-3 取数）" :image-size="48" />
        <el-table v-else :data="dis.individualDetailRows.value" border size="small">
          <el-table-column label="债务人名称" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small"
                @change="(v: string) => dis.updateIndividualRow(row.rowId, 'debtorName', v)" />
              <span v-else>{{ row.debtorName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.balance" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updateIndividualRow(row.rowId, 'balance', v)" />
              <span v-else>{{ fmt(row.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.provision" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updateIndividualRow(row.rowId, 'provision', v)" />
              <span v-else>{{ fmt(row.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="ECL率(%)" width="90" align="right">
            <template #default="{ row }">{{ row.eclRate != null ? row.eclRate.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column label="计提理由" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.reason" size="small"
                @change="(v: string) => dis.updateIndividualRow(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>

      <!-- ④ 组合·账龄 -->
      <el-collapse-item name="portfolioAging">
        <template #title><span class="collapse-title">④ 组合计提·账龄组合</span></template>
        <SectionHint :guide="sectionGuide('portfolioAging')" />
        <el-table :data="dis.portfolioAgingRows.value" border size="small">
          <el-table-column prop="label" label="账龄" min-width="120" />
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.editable && !isReadonly" :model-value="row.endBalance" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updatePortfolioRow(row.rowId, 'endBalance', v)" />
              <span v-else :class="{ 'auto-fill': row.autoFilled }">{{ fmt(row.endBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="比例(%)" width="80" align="right">
            <template #default="{ row }">{{ row.endBalancePct != null ? row.endBalancePct.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.editable && !isReadonly" :model-value="row.endProvision" size="small" :controls="false" style="width:100%"
                @change="(v: number) => dis.updatePortfolioRow(row.rowId, 'endProvision', v)" />
              <span v-else>{{ fmt(row.endProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.priorBalance) }}</template>
          </el-table-column>
          <el-table-column label="期初坏账" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.priorProvision) }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>

      <!-- ⑤ ECL三阶段 -->
      <el-collapse-item name="ecl">
        <template #title><span class="collapse-title">⑤ 其他应收款坏账准备计提情况（ECL三阶段）</span></template>
        <SectionHint :guide="sectionGuide('ecl')" />
        <el-table :data="dis.stageMovements.value" border size="small">
          <el-table-column prop="label" label="项目" min-width="180" />
          <el-table-column label="第一阶段" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage1) }}</template>
          </el-table-column>
          <el-table-column label="第二阶段" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage2) }}</template>
          </el-table-column>
          <el-table-column label="第三阶段" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage3) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage1 + row.stage2 + row.stage3) }}</template>
          </el-table-column>
        </el-table>
        <p class="hint-text">数据来自 K1-3 三阶段转入转出；请在 K1-3 维护后点击「从源底稿取数」刷新。</p>
      </el-collapse-item>

      <!-- ⑤b 账面余额三阶段 -->
      <el-collapse-item name="balanceStage">
        <template #title>
          <span class="collapse-title">⑤b 其他应收款账面余额三阶段变动</span>
          <el-tag v-if="dis.balanceStageMovements.value.length" size="small" type="success" class="collapse-tag">K1-7</el-tag>
        </template>
        <SectionHint :guide="sectionGuide('balanceStage')" />
        <el-empty v-if="!dis.balanceStageMovements.value.length" description="K1-7 暂无三阶段划分数据" :image-size="48" />
        <el-table v-else :data="dis.balanceStageMovements.value" border size="small">
          <el-table-column prop="label" label="项目" min-width="180" />
          <el-table-column label="第一阶段" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage1) }}</template>
          </el-table-column>
          <el-table-column label="第二阶段" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage2) }}</template>
          </el-table-column>
          <el-table-column label="第三阶段" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage3) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.stage1 + row.stage2 + row.stage3) }}</template>
          </el-table-column>
        </el-table>
        <p class="hint-text">自 K1-7 按户汇总：期初取 K1-2 期初余额按 priorStage 归集；阶段迁移取 priorStage→stage 变动；同阶段差额计入本期新增/收回。</p>
      </el-collapse-item>

      <!-- ⑥ 前五名 -->
      <el-collapse-item name="top5">
        <template #title><span class="collapse-title">⑥ 期末余额前五名欠款方</span></template>
        <SectionHint :guide="sectionGuide('top5')" />
        <el-table :data="dis.top5Rows.value" border size="small">
          <el-table-column label="单位名称" min-width="130">
            <template #default="{ row }">
              <span :class="{ 'auto-fill': row.autoFilled }">{{ row.unitName || '（未命名）' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="nature" label="款项性质" min-width="100" />
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.endBalance) }}</template>
          </el-table-column>
          <el-table-column prop="aging" label="账龄" width="90" />
          <el-table-column label="占比(%)" width="80" align="right">
            <template #default="{ row }">{{ row.proportionPct?.toFixed(2) ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="坏账准备" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.provision) }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>

      <!-- ⑦ 转回/核销 -->
      <el-collapse-item name="reversal">
        <template #title><span class="collapse-title">⑦ 本期转回/收回及核销</span></template>
        <SectionHint :guide="sectionGuide('reversal')" />
        <div class="sub-block-title">转回/收回</div>
        <el-table :data="dis.reversalRows.value" border size="small" class="sub-table">
          <el-table-column prop="unitName" label="债务人" min-width="120" />
          <el-table-column prop="reason" label="转回原因" min-width="120" />
          <el-table-column prop="method" label="收回方式" width="100" />
          <el-table-column label="金额" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
        </el-table>
        <div class="sub-block-title">实际核销</div>
        <el-table :data="dis.writeoffDetailRows.value" border size="small" class="sub-table">
          <el-table-column prop="unitName" label="债务人" min-width="110" />
          <el-table-column prop="nature" label="性质" width="90" />
          <el-table-column label="金额" width="100" align="right">
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="100" />
          <el-table-column prop="procedure" label="核销程序" min-width="100" />
        </el-table>
        <SectionHint :guide="sectionGuide('writeoff')" />
      </el-collapse-item>

      <!-- ⑧ 政府补助 -->
      <el-collapse-item name="govGrant">
        <template #title><span class="collapse-title">⑧ 涉及政府补助的应收款项</span></template>
        <SectionHint :guide="sectionGuide('govGrant')" />
        <el-empty v-if="!dis.govGrantRows.value.length" description="K1-2 无政府补助性质明细" :image-size="48" />
        <el-table v-else :data="dis.govGrantRows.value" border size="small">
          <el-table-column prop="unitName" label="单位名称" min-width="120" />
          <el-table-column prop="projectName" label="补助项目" min-width="140" />
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.endBalance) }}</template>
          </el-table-column>
          <el-table-column prop="aging" label="账龄" width="90" />
          <el-table-column prop="expectedCollection" label="预计收取时间/依据" min-width="160" />
        </el-table>
      </el-collapse-item>

      <!-- ⑨ 转移 -->
      <el-collapse-item name="transfer">
        <template #title><span class="collapse-title">⑨ 金融资产转移终止确认及继续涉入</span></template>
        <SectionHint :guide="sectionGuide('transfer')" />
        <el-button v-if="!isReadonly" size="small" type="primary" link @click="dis.addTransferRow()">＋ 新增终止确认行</el-button>
        <el-table :data="dis.transferRows.value" border size="small" class="sub-table">
          <el-table-column prop="item" label="债务人/项目" min-width="140" />
          <el-table-column prop="method" label="转移方式" width="120" />
          <el-table-column label="终止确认金额" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.derecognizedAmount) }}</template>
          </el-table-column>
          <el-table-column label="利得/损失" width="110" align="right">
            <template #default="{ row }">{{ fmt(row.gainLoss) }}</template>
          </el-table-column>
        </el-table>
        <div class="continued-row">
          <span>继续涉入形成资产：</span>
          <el-input-number v-if="!isReadonly" :model-value="dis.payload.value.continuedInvolvementAssets" size="small" :controls="false"
            @change="(v: number) => dis.updateContinuedInvolvement('assets', v)" />
          <span v-else>{{ fmt(dis.payload.value.continuedInvolvementAssets) }}</span>
          <span class="continued-gap">负债：</span>
          <el-input-number v-if="!isReadonly" :model-value="dis.payload.value.continuedInvolvementLiabilities" size="small" :controls="false"
            @change="(v: number) => dis.updateContinuedInvolvement('liabilities', v)" />
          <span v-else>{{ fmt(dis.payload.value.continuedInvolvementLiabilities) }}</span>
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-card shadow="never" class="note-card">
      <template #header><span class="card-title">审计说明（同步至附注文字）</span></template>
      <el-input
        v-model="dis.noteText.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明账龄变动、阶段迁移、核销原因及与 K1-8 测算衔接等"
        @change="dis.persistNote()"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（结构 vs 内容 · 非打印）</summary>
      <ul>
        <li><strong>结构</strong>：国企版 130 行×10 列，分 9 大区块；本页用折叠面板对应 Excel 各表。</li>
        <li><strong>内容</strong>：各区块自动取数来源见区块内提示；浅蓝色/「自动」标签为跨表联动。</li>
        <li><strong>附注联动</strong>：点击「同步至附注」写入 note_template_soe §八、9 对应子表名。</li>
        <li><strong>勾稽</strong>：账龄小计=K1-1 其他应收款合计；坏账准备=ECL 三阶段期末合计。</li>
        <li>与上市版区别：国企含「按计提方法」双表、单项明细、组合账龄、政府补助及转移披露。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, defineComponent, h } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useK1DisclosureSoe } from '../../composables/useK1DisclosureSoe'
import { useK1DisclosureTrace } from '../../composables/k1DisclosureTrace'
import K1DisclosureTracePanel from './K1DisclosureTracePanel.vue'
import { K1_SOE_SECTION_GUIDES } from '../../composables/k1NoteSectionMap'
import type { K1AgingDisclosureRow } from '../../composables/k1DisclosureModel'

const SectionHint = defineComponent({
  props: { guide: { type: Object, default: null } },
  setup(props) {
    return () => {
      const g = props.guide as { structure?: string; source?: string; noteTarget?: string } | null
      if (!g) return null
      return h('el-alert', {
        type: 'info',
        closable: false,
        class: 'section-hint',
        title: `结构：${g.structure}`,
        description: `取数：${g.source} → ${g.noteTarget}`,
      })
    }
  },
})

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const activeSections = ref(['aging', 'method', 'ecl', 'balanceStage', 'top5'])

const dis = useK1DisclosureSoe({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, { remark: typeof value === 'string' ? value : JSON.stringify(value) }),
})

const trace = useK1DisclosureTrace('soe', allResponsesRef)

const noteTarget = dis.noteTarget

function sectionGuide(id: string) {
  return K1_SOE_SECTION_GUIDES.find((g) => g.id === id)
}

function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function agingRowClass({ row }: { row: K1AgingDisclosureRow }) {
  if (row.kind === 'total' || row.kind === 'subtotal') return 'is-total-row'
  if (row.kind === 'provision') return 'is-provision-row'
  return ''
}
</script>

<style scoped>
.k1-disclosure-soe { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.objective-alert, .sync-hint, .tie-out-alert { margin-bottom: 8px; }
.section-collapse { margin-bottom: 12px; }
.collapse-title { font-weight: 600; margin-right: 8px; }
.collapse-tag { margin-left: 8px; }
.section-hint { margin-bottom: 8px; }
.dual-table-label { font-size: 12px; font-weight: 600; margin: 8px 0 4px; color: var(--el-text-color-secondary); }
.method-table { margin-bottom: 10px; }
.sub-block-title { font-size: 12px; font-weight: 600; margin: 10px 0 6px; }
.sub-table { margin-bottom: 8px; }
.hint-text { font-size: 12px; color: var(--el-text-color-secondary); margin: 6px 0 0; }
.continued-row { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 12px; }
.continued-gap { margin-left: 16px; }
.note-card { margin-top: 12px; }
.card-title { font-weight: 600; }
.auto-fill { color: var(--el-color-primary); }
:deep(.is-total-row) { font-weight: 600; background: #f5f7fa; }
:deep(.is-provision-row) { color: var(--el-color-warning); }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
