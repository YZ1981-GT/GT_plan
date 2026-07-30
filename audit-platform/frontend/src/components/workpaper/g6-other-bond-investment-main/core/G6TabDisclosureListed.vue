<template>
  <div class="g6-disc-listed" data-testid="g6-disclosure-listed">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G6 其他债权投资附注披露（上市公司）</h3>
        <div class="cross-index">
          <GtIndexChip value="wp:G6-1" />
          <span class="chip-note">Note:{{ G6_NOTE_SECTION.listed }}</span>
        </div>
      </div>
      <div class="head-actions">
        <el-button
          size="small"
          type="primary"
          plain
          data-testid="g6-disclosure-listed-sync-notes"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <GtReviewTrigger section-id="G6-disclosure-listed" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective"
      title="审计目标：按上市公司附注格式列示其他债权投资，主表按公允价值列示、扣减一年内到期部分后与资产负债表及 G6-1 审定数一致；损失准备在其他综合收益中确认，不冲减资产负债表列示的账面价值。"
    />

    <!-- 内部勾稽面板 -->
    <div class="tie-bar" :class="{ 'has-issue': dis.hasTieIssue.value }" data-testid="g6-listed-tie-bar">
      <span class="tie-title">
        {{ dis.hasTieIssue.value ? '⚠ 勾稽存在差异' : '✓ 勾稽一致' }}
        （{{ dis.tieChecks.value.filter((c) => c.ok).length }}/{{ dis.tieChecks.value.length }}）
      </span>
      <el-button link size="small" @click="tieOpen = !tieOpen">{{ tieOpen ? '收起' : '明细' }}</el-button>
    </div>
    <el-table
      v-if="tieOpen"
      :data="dis.tieChecks.value"
      border
      size="small"
      class="disc-table"
      data-testid="g6-listed-tie-table"
    >
      <el-table-column label="勾稽项" min-width="240">
        <template #default="{ row }">
          <span :class="{ 'tie-bad': !row.ok }">{{ row.ok ? '✓' : '✗' }} {{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="左值" width="140" align="right">
        <template #default="{ row }">{{ fmt(row.left) }}</template>
      </el-table-column>
      <el-table-column label="右值" width="140" align="right">
        <template #default="{ row }">{{ fmt(row.right) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="140" align="right">
        <template #default="{ row }">
          <span :class="{ 'tie-bad': !row.ok }">{{ fmt(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="口径" min-width="220" prop="detail" />
    </el-table>

    <!-- 主表：其他债权投资 -->
    <div class="tbl-head">
      <h4 class="tbl-title">{{ G6_LISTED_SUBTABLE.balance }}</h4>
      <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addBalanceRow()">+ 添加行</el-button>
    </div>
    <el-table :data="dis.state.value.balanceRows" border size="small" class="disc-table"
      :row-class-name="rowClass" data-testid="g6-listed-balance-table">
      <el-table-column label="项目" min-width="220">
        <template #default="{ row }">
          <span v-if="row.fixed" class="fixed-label">{{ row.label }}</span>
          <el-input v-else-if="!isReadonly" :model-value="row.label" size="small" placeholder="项目（可改名）"
            @update:model-value="(v: string) => dis.patchBalance(row.id, { label: v })" />
          <span v-else>{{ row.label || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="160" align="right">
        <template #default="{ row }">
          <span v-if="isFormulaRow(row)" class="formula-cell">{{ fmt(row.endBalance) }}</span>
          <WpAmountInput v-else :model-value="row.endBalance" :disabled="isReadonly"
            @update:model-value="(v: number) => dis.patchBalance(row.id, { endBalance: v })" />
        </template>
      </el-table-column>
      <el-table-column label="上年年末余额" width="160" align="right">
        <template #default="{ row }">
          <span v-if="isFormulaRow(row)" class="formula-cell">{{ fmt(row.priorBalance) }}</span>
          <WpAmountInput v-else :model-value="row.priorBalance" :disabled="isReadonly"
            @update:model-value="(v: number) => dis.patchBalance(row.id, { priorBalance: v })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.fixed && !isReadonly" link size="small" type="danger"
            @click="dis.removeBalanceRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- （1）其他债权投资情况 -->
    <div class="tbl-head">
      <h4 class="tbl-title">（1）{{ G6_LISTED_SUBTABLE.fairValue }}</h4>
      <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addFairValueRow()">+ 添加行</el-button>
    </div>
    <el-table :data="dis.state.value.fairValueRows" border size="small" class="disc-table"
      :row-class-name="rowClass" max-height="360" data-testid="g6-listed-fv-table">
      <el-table-column label="项目" min-width="150" fixed>
        <template #default="{ row }">
          <span v-if="row.fixed" class="fixed-label">{{ row.label }}</span>
          <el-input v-else-if="!isReadonly" :model-value="row.label" size="small" placeholder="投资项目"
            @update:model-value="(v: string) => dis.patchFairValue(row.id, { label: v })" />
          <span v-else>{{ row.label || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-for="col in FV_COLS" :key="col.key" :label="col.label" width="150" align="right">
        <template #default="{ row }">
          <span v-if="row.fixed || col.key === 'closingFv'" class="formula-cell">{{ fmt(row[col.key]) }}</span>
          <WpAmountInput v-else :model-value="row[col.key]" :disabled="isReadonly"
            @update:model-value="(v: number) => dis.patchFairValue(row.id, { [col.key]: v })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.fixed && !isReadonly" link size="small" type="danger"
            @click="dis.removeFairValueRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="inline-note">
      <span class="note-label">说明：</span>
      <el-input :model-value="dis.state.value.fvNote" size="small" :disabled="isReadonly"
        placeholder="H列按投资项目填列，合计应与坏账准备明细表G6-3期末审定数勾稽。"
        @update:model-value="(v: string) => dis.setNote('fvNote', v)" />
    </div>
    <details class="src-hint">
      <summary>源模板红字提示</summary>
      <p>{{ G6_LISTED_FORMULA_HINT }}</p>
      <p>{{ G6_LISTED_OCI_HINT }}</p>
    </details>

    <!-- （2）减值准备本期变动情况 -->
    <div class="tbl-head">
      <h4 class="tbl-title">（2）{{ G6_LISTED_SUBTABLE.provision }}</h4>
      <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addProvisionRow()">+ 添加行</el-button>
    </div>
    <el-table :data="dis.state.value.provisionRows" border size="small" class="disc-table"
      :row-class-name="rowClass" data-testid="g6-listed-provision-table">
      <el-table-column label="项目" min-width="220">
        <template #default="{ row }">
          <span v-if="row.fixed" class="fixed-label">{{ row.label }}</span>
          <el-input v-else-if="!isReadonly" :model-value="row.label" size="small" placeholder="项目"
            @update:model-value="(v: string) => dis.patchProvision(row.id, { label: v })" />
          <span v-else>{{ row.label || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-for="col in PROV_COLS" :key="col.key" :label="col.label" width="150" align="right">
        <template #default="{ row }">
          <span v-if="row.kind === 'total'" class="formula-cell">{{ fmt(row[col.key]) }}</span>
          <WpAmountInput v-else :model-value="row[col.key]" :disabled="isReadonly"
            @update:model-value="(v: number) => dis.patchProvision(row.id, { [col.key]: v })" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="150" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmt(provisionClosing(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.fixed && !isReadonly" link size="small" type="danger"
            @click="dis.removeProvisionRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- （3）期末重要的其他债权投资 + 续表 -->
    <template v-for="grp in IMPORTANT_GROUPS" :key="grp.key">
      <div class="tbl-head">
        <h4 class="tbl-title">{{ grp.title }}</h4>
        <el-button v-if="!isReadonly" size="small" link type="primary"
          @click="dis.addImportantRow(grp.key)">+ 添加行</el-button>
      </div>
      <el-table :data="dis.state.value[grp.key]" border size="small" class="disc-table"
        :row-class-name="rowClass" :data-testid="`g6-listed-${grp.testid}-table`">
        <el-table-column label="项目" min-width="180">
          <template #default="{ row }">
            <span v-if="row.fixed" class="fixed-label">{{ row.label }}</span>
            <el-input v-else-if="!isReadonly" :model-value="row.label" size="small" placeholder="项目（可改名）"
              @update:model-value="(v: string) => dis.patchImportant(grp.key, row.id, { label: v })" />
            <span v-else>{{ row.label || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="grp.group" align="center">
          <el-table-column label="面值" width="140" align="right">
            <template #default="{ row }">
              <span v-if="row.fixed" class="formula-cell">{{ fmt(row.faceValue) }}</span>
              <WpAmountInput v-else :model-value="row.faceValue" :disabled="isReadonly"
                @update:model-value="(v: number) => dis.patchImportant(grp.key, row.id, { faceValue: v })" />
            </template>
          </el-table-column>
          <el-table-column v-for="t in IMPORTANT_TEXT_COLS" :key="t.key" :label="t.label" width="120">
            <template #default="{ row }">
              <span v-if="row.fixed" class="dash">--</span>
              <el-input v-else-if="!isReadonly" :model-value="row[t.key]" size="small"
                @update:model-value="(v: string) => dis.patchImportant(grp.key, row.id, { [t.key]: v })" />
              <span v-else>{{ row[t.key] || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="逾期本金" width="140" align="right">
            <template #default="{ row }">
              <span v-if="row.fixed" class="formula-cell">{{ fmt(row.overduePrincipal) }}</span>
              <WpAmountInput v-else :model-value="row.overduePrincipal" :disabled="isReadonly"
                @update:model-value="(v: number) => dis.patchImportant(grp.key, row.id, { overduePrincipal: v })" />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.fixed && !isReadonly" link size="small" type="danger"
              @click="dis.removeImportantRow(grp.key, row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- （4）减值准备计提情况：六张三阶段表 -->
    <h4 class="tbl-title section-gap">（4）减值准备计提情况</h4>
    <el-alert type="warning" :closable="false" class="stage-hint"
      title="【15号文第十九条（十一）】披露减值输入值、假设及信用风险是否显著增加的判断依据。「其中」默认 1 行 + 预留行；只在对应「按单项/按组合」与下一父行之间增删行。" />
    <template v-for="block in dis.state.value.stageBlocks" :key="block.id">
      <div class="tbl-head">
        <h5 class="stage-title">{{ block.title }}</h5>
      </div>
      <el-table :data="stageTableRows(block)" border size="small" class="disc-table"
        :row-class-name="stageRowClass" :data-testid="`g6-listed-stage-${block.id}`">
        <el-table-column label="类别" min-width="200">
          <template #default="{ row }">
            <span v-if="row.type !== 'detail'" class="fixed-label">{{ row.label }}</span>
            <el-input v-else-if="!isReadonly" :model-value="row.detail.name" size="small" placeholder="其中：明细项"
              @update:model-value="(v: string) => dis.patchStage(block.id, row.method, row.detail.id, { name: v })" />
            <span v-else>{{ row.detail.name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面余额" width="150" align="right">
          <template #default="{ row }">
            <span v-if="row.type !== 'detail'" class="formula-cell">{{ fmt(row.gross) }}</span>
            <WpAmountInput v-else :model-value="row.detail.bookBalance" :disabled="isReadonly"
              @update:model-value="(v: number) => dis.patchStage(block.id, row.method, row.detail.id, { bookBalance: v })" />
          </template>
        </el-table-column>
        <el-table-column :label="block.rateLabel" width="170" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ pct(row.type === 'detail' ? detailRate(row.detail) : row.rate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="150" align="right">
          <template #default="{ row }">
            <span v-if="row.type !== 'detail'" class="formula-cell">{{ fmt(row.provision) }}</span>
            <WpAmountInput v-else :model-value="row.detail.impairment" :disabled="isReadonly"
              @update:model-value="(v: number) => dis.patchStage(block.id, row.method, row.detail.id, { impairment: v })" />
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="150" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(stageNet(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="block.reasonHeader" min-width="160">
          <template #default="{ row }">
            <el-input v-if="row.type === 'detail' && !isReadonly" :model-value="row.detail.reason" size="small"
              @update:model-value="(v: string) => dis.patchStage(block.id, row.method, row.detail.id, { reason: v })" />
            <span v-else-if="row.type === 'detail'">{{ row.detail.reason || '—' }}</span>
            <span v-else class="dash">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button v-if="row.type === 'which' && !isReadonly" link size="small" type="primary"
              @click="dis.addStageRow(block.id, row.method)">+ 其中行</el-button>
            <el-button v-else-if="row.type === 'detail' && !isReadonly" link size="small" type="danger"
              @click="dis.removeStageRow(block.id, row.method, row.detail.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="block.id === 'ending-s3'" class="stage-notes">
        <div class="inline-note">
          <span class="note-label">说明：本期发生损失准备的其他债权投资账面余额显著变动的情况</span>
          <el-button size="small" link type="primary" :disabled="isReadonly" :loading="aiLoading"
            @click="onAiAssist('significantChangeNote')">AI 辅助</el-button>
          <el-input :model-value="dis.state.value.significantChangeNote" type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
            @update:model-value="(v: string) => dis.setNote('significantChangeNote', v)" />
        </div>
        <div class="inline-note">
          <span class="note-label">说明：本期减值准备计提金额以及评估信用风险是否显著增加的采用依据</span>
          <el-button size="small" link type="primary" :disabled="isReadonly" :loading="aiLoading"
            @click="onAiAssist('judgementBasisNote')">AI 辅助</el-button>
          <el-input :model-value="dis.state.value.judgementBasisNote" type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
            @update:model-value="(v: string) => dis.setNote('judgementBasisNote', v)" />
        </div>
      </div>
    </template>

    <!-- （5）本期计提、收回或转回的减值准备情况 -->
    <div class="tbl-head">
      <h4 class="tbl-title">（5）{{ G6_LISTED_SUBTABLE.stageMove }}</h4>
    </div>
    <el-alert v-if="dis.transferImbalances.value.length" type="warning" :closable="false" show-icon
      class="stage-hint" data-testid="g6-listed-transfer-imbalance"
      :title="`阶段转移行三个阶段金额代数和应为 0，以下行不平：${transferImbalanceLabels}`" />
    <el-table :data="dis.state.value.stageMoveRows" border size="small" class="disc-table"
      :row-class-name="moveRowClass" data-testid="g6-listed-stage-move-table">
      <el-table-column label="减值准备" min-width="180">
        <template #default="{ row }">
          <span class="fixed-label">{{ row.label }}</span>
          <el-tooltip v-if="row.signHint" :content="row.signHint" placement="top">
            <span class="sign-hint">ⓘ</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column v-for="st in STAGE_MOVE_COLS" :key="st.key" :label="st.parent" align="center">
        <el-table-column :label="st.label" width="200" align="right">
          <template #default="{ row }">
            <WpAmountInput :model-value="row[st.key]" :disabled="isReadonly"
              @update:model-value="(v: number) => dis.patchStageMove(row.rowKey, { [st.key]: v })" />
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="合计" width="150" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmt(stageMoveTotal(row)) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- （6）本期实际核销 -->
    <div class="tbl-head">
      <h4 class="tbl-title">（6）{{ G6_LISTED_SUBTABLE.writeoff }}</h4>
    </div>
    <el-table :data="[{ label: G6_WRITEOFF_ROW_LABEL }]" border size="small" class="disc-table"
      data-testid="g6-listed-writeoff-table">
      <el-table-column label="项目" min-width="240" prop="label" />
      <el-table-column label="核销金额" width="180" align="right">
        <template #default>
          <WpAmountInput :model-value="dis.state.value.writeoffTotal" :disabled="isReadonly"
            @update:model-value="(v: number) => dis.setWriteoffTotal(v)" />
        </template>
      </el-table-column>
    </el-table>

    <div class="tbl-head">
      <h5 class="stage-title">{{ G6_LISTED_SUBTABLE.writeoffDetail }}</h5>
      <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addWriteoffRow()">+ 添加行</el-button>
    </div>
    <el-table :data="dis.state.value.writeoffRows" border size="small" class="disc-table"
      empty-text="无重要核销；可点击添加行" data-testid="g6-listed-writeoff-detail-table">
      <el-table-column label="项目" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.label" size="small"
            @update:model-value="(v: string) => dis.patchWriteoff(row.id, { label: v })" />
          <span v-else>{{ row.label || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="其他债权投资性质" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.nature" size="small"
            @update:model-value="(v: string) => dis.patchWriteoff(row.id, { nature: v })" />
          <span v-else>{{ row.nature || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="核销金额" width="150" align="right">
        <template #default="{ row }">
          <WpAmountInput :model-value="row.amount" :disabled="isReadonly"
            @update:model-value="(v: number) => dis.patchWriteoff(row.id, { amount: v })" />
        </template>
      </el-table-column>
      <el-table-column label="核销原因" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reason" size="small"
            @update:model-value="(v: string) => dis.patchWriteoff(row.id, { reason: v })" />
          <span v-else>{{ row.reason || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="履行的核销程序" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.procedure" size="small"
            @update:model-value="(v: string) => dis.patchWriteoff(row.id, { procedure: v })" />
          <span v-else>{{ row.procedure || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否由关联交易产生" width="150" align="center">
        <template #default="{ row }">
          <el-select :model-value="row.relatedParty ? '是' : '否'" size="small" :disabled="isReadonly"
            @update:model-value="(v: string) => dis.patchWriteoff(row.id, { relatedParty: v === '是' })">
            <el-option label="否" value="否" />
            <el-option label="是" value="是" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link size="small" type="danger"
            @click="dis.removeWriteoffRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <p class="regulation-note">{{ G6_WRITEOFF_REG_NOTE }}</p>

    <details class="prep-hint">
      <summary>📋 编制说明（源模板 R174~R180）</summary>
      <ol>
        <li v-for="(n, i) in G6_LISTED_PREP_NOTES" :key="i">{{ n }}</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDisclosureListed — 其他债权投资 附注披露信息（上市公司）
 *
 * 🔴 **本组件为重写版**。旧版是**自造**的 7 个虚构小节（一、其他债权投资成本 /
 * 二、利息调整 / … / 七、其他披露事项）+ `generateRows()` 批量生成 137 行
 * `成本项目N`，列头亦自拟，与源模板对不上任何一张表 —— 接附注同步会把假数据推进
 * 附注。现按**权威模板** `backend/wp_templates/G/G6 其他债权投资.xlsx` sheet
 * 「附注披露信息（上市公司）」逐格重建为 6 小节 / 14 张表。
 *
 * 行模型与派生：`g6ListedDisclosureRows.ts`（纯函数，可单测）
 * 状态与勾稽：  `useG6DisclosureListed.ts`（7 条内部勾稽）
 * 同步载荷：    `g6DisclosureSyncPayload.ts`
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.3
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { dispatchG6SaveItems } from '../../composables/g6CrossHelpers'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { useG6MainAiGenerate } from '../../composables/useG6MainAiGenerate'
import {
  bookValue,
  eclRatePct,
  methodTotals,
  stageTotals,
  type G4StageBlock,
  type G4StageDetailRow,
  type G4StageMethod,
} from '../../composables/g4ListedStageDisclosure'
import {
  G6_LISTED_FORMULA_HINT,
  G6_LISTED_OCI_HINT,
  G6_LISTED_PREP_NOTES,
  G6_TOTAL_LABEL,
  G6_WRITEOFF_REG_NOTE,
  G6_WRITEOFF_ROW_LABEL,
  provisionClosing,
  stageMoveTotal,
  type G6ProvisionMovementRow,
  type G6StageMoveRow,
} from '../../composables/g6ListedDisclosureRows'
import { G6_LISTED_SUBTABLE, G6_NOTE_SECTION } from '../../composables/g6NoteSectionMap'
import { buildG6ListedSyncPayload } from '../../composables/g6DisclosureSyncPayload'
import { useG6DisclosureListed } from '../../composables/useG6DisclosureListed'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = withDefaults(
  defineProps<{
    htmlData: Record<string, any> | null
    wpId: string
    projectId: string
    isReadonly: boolean
    allResponses?: Map<string, ChecklistResponse>
    applicableStandards?: string[]
  }>(),
  { allResponses: undefined, applicableStandards: () => [] },
)

const isReadonly = computed(() => props.isReadonly)
const allResponses = computed<Map<string, ChecklistResponse>>(
  () => props.allResponses ?? new Map(),
)

// ─── 持久化：本地 500ms 防抖后一次性派发（同批次按 item_id 去重，避免整批被拒）─
const pendingSave = new Map<string, Partial<ChecklistResponse>>()
let saveTimer: ReturnType<typeof setTimeout> | null = null

function flushSave(): void {
  saveTimer = null
  if (!pendingSave.size || !props.wpId) return
  const items = Array.from(pendingSave, ([item_id, v]) => ({
    item_id,
    conclusion: v.conclusion ?? null,
    remark: v.remark ?? null,
  }))
  pendingSave.clear()
  dispatchG6SaveItems(props.wpId, items)
}

function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
  if (props.isReadonly) return
  pendingSave.set(itemId, data)
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(flushSave, 500)
}

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    flushSave()
  }
})

const dis = useG6DisclosureListed({ allResponses, debouncedSave, isReadonly })

// ─── 展示常量 ────────────────────────────────────────────────────────────────
const tieOpen = ref(false)

/** （1）表七个金额列；期末余额 D = A + B + C 为公式列，由 isFormulaRow 之外的
 *  `col.key === 'closingFv'` 分支渲染（见模板）。 */
const FV_COLS = [
  { key: 'openingFv', label: '期初余额' },
  { key: 'accruedInterest', label: '应计利息' },
  { key: 'fvChangeCurrent', label: '本期公允价值变动' },
  { key: 'closingFv', label: '期末余额' },
  { key: 'cost', label: '成本' },
  { key: 'fvChangeCumulative', label: '累计公允价值变动' },
  { key: 'ociImpairment', label: '累计在其他综合收益中确认的减值准备' },
] as const

/** （2）表可录入列（期末余额为公式列，模板中单列渲染） */
const PROV_COLS = [
  { key: 'opening', label: '期初余额' },
  { key: 'increase', label: '本期增加' },
  { key: 'decrease', label: '本期减少' },
] as const

/** （3）期末重要 + 续表：两张同构表，父表头为期间 */
const IMPORTANT_GROUPS = [
  {
    key: 'importantEndRows' as const,
    testid: 'important-end',
    title: `（3）${G6_LISTED_SUBTABLE.importantEnd}`,
    group: '期末余额',
  },
  {
    key: 'importantPriorRows' as const,
    testid: 'important-prior',
    title: G6_LISTED_SUBTABLE.importantPrior,
    group: '上年年末余额',
  },
]

/** 重要投资表的三个文本列（合计行源模板列示为「--」，不加总） */
const IMPORTANT_TEXT_COLS = [
  { key: 'couponRate' as const, label: '票面利率' },
  { key: 'effectiveRate' as const, label: '实际利率' },
  { key: 'maturityDate' as const, label: '到期日' },
]

/** （5）表三阶段列（两级表头：父 = 阶段，子 = 预期信用损失口径） */
const STAGE_MOVE_COLS = [
  { key: 'stage1' as const, parent: '第一阶段', label: '未来12个月预期信用损失' },
  {
    key: 'stage2' as const,
    parent: '第二阶段',
    label: '整个存续期预期信用损失（未发生信用减值）',
  },
  {
    key: 'stage3' as const,
    parent: '第三阶段',
    label: '整个存续期预期信用损失（已发生信用减值）',
  },
]

// ─── 展示辅助 ────────────────────────────────────────────────────────────────
// 金额格式单一真源 = displayPrefs 的 fmtAmount（千分符 + 2 位小数 + 默认「元」）
const prefs = useDisplayPrefsStore()

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** null / undefined → 「—」（结构行的不适用格，如「其中：」标签行）*/
function fmt(v: unknown): string {
  if (v == null) return '—'
  return prefs.fmtAmount(num(v))
}

function pct(v: number | null | undefined): string {
  return v == null ? '--' : `${v.toFixed(2)}%`
}

/** 结构行（小计 / 合计）为公式列，不可直接录入 */
function isFormulaRow(row: { kind?: string }): boolean {
  return row.kind === 'subtotal' || row.kind === 'total'
}

function rowClass({ row }: { row: { kind?: string; fixed?: boolean } }): string {
  if (row.kind === 'total') return 'row-total'
  if (row.kind === 'subtotal') return 'row-subtotal'
  return ''
}

// ─── （4）三阶段表行视图 ─────────────────────────────────────────────────────
/**
 * 一张阶段表的展示行：
 * 按单项（父，汇总）→ 其中：（结构行）→ 逐条明细 → 按组合（父）→ 其中： → 明细
 * → 合 计。
 *
 * 🔴「其中：」结构行不能省 —— 附注是交付物，缺了读者看不出下面明细属于哪个父行；
 * 与 `buildG6StageRows` 推给附注的行序保持一致。
 */
type StageTableRow =
  | {
      id: string
      type: 'parent' | 'total'
      method: G4StageMethod
      label: string
      gross: number
      provision: number
      rate: number | null
    }
  | { id: string; type: 'which'; method: G4StageMethod; label: string }
  | { id: string; type: 'detail'; method: G4StageMethod; detail: G4StageDetailRow }

const METHOD_LABELS: Record<G4StageMethod, string> = {
  individual: '按单项计提减值准备',
  portfolio: '按组合计提减值准备',
}

function stageTableRows(block: G4StageBlock): StageTableRow[] {
  const rows: StageTableRow[] = []
  for (const method of ['individual', 'portfolio'] as const) {
    const mb = method === 'individual' ? block.individual : block.portfolio
    const t = methodTotals(mb)
    rows.push({
      id: `${block.id}-${method}-parent`,
      type: 'parent',
      method,
      label: METHOD_LABELS[method],
      gross: t.bookBalance,
      provision: t.impairment,
      rate: t.ratePct,
    })
    rows.push({ id: `${block.id}-${method}-which`, type: 'which', method, label: '其中：' })
    for (const d of mb.details) {
      rows.push({ id: d.id, type: 'detail', method, detail: d })
    }
  }
  const t = stageTotals(block)
  rows.push({
    id: `${block.id}-total`,
    type: 'total',
    method: 'individual',
    label: G6_TOTAL_LABEL,
    gross: t.bookBalance,
    provision: t.impairment,
    rate: t.ratePct,
  })
  return rows
}

function detailRate(d: G4StageDetailRow): number | null {
  return eclRatePct(num(d.impairment), num(d.bookBalance))
}

/** 账面价值：明细/父/合计取差额；「其中：」结构行不适用 → null（显示「—」）*/
function stageNet(row: StageTableRow): number | null {
  if (row.type === 'which') return null
  if (row.type === 'detail') {
    return bookValue(num(row.detail.bookBalance), num(row.detail.impairment))
  }
  return bookValue(row.gross, row.provision)
}

function stageRowClass({ row }: { row: StageTableRow }): string {
  if (row.type === 'total') return 'row-total'
  if (row.type === 'parent') return 'row-subtotal'
  if (row.type === 'which') return 'row-which'
  return ''
}

function moveRowClass({ row }: { row: G6StageMoveRow }): string {
  return row.rowKey === 'opening' || row.rowKey === 'closing' ? 'row-subtotal' : ''
}

const transferImbalanceLabels = computed(() =>
  dis.state.value.stageMoveRows
    .filter((r) => dis.transferImbalances.value.includes(r.rowKey))
    .map((r) => r.label)
    .join('、'),
)

// ─── AI 辅助（只补写文本域，不生成披露数字）─────────────────────────────────
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, checkAiHealth, loading: aiLoading } = useG6MainAiGenerate(wpIdRef)

type G6ListedAiNote = 'significantChangeNote' | 'judgementBasisNote'

const AI_TITLES: Record<G6ListedAiNote, string> = {
  significantChangeNote: '本期发生损失准备的账面余额显著变动情况',
  judgementBasisNote: '本期减值准备计提金额与信用风险显著增加的判断依据',
}

async function onAiAssist(key: G6ListedAiNote): Promise<void> {
  if (props.isReadonly) return
  const s = dis.state.value
  const text = await generateAndConfirm(
    'disclosure-listed-note',
    s[key],
    {
      focus: key,
      endingBalance: dis.balanceTotalRow.value?.endBalance ?? 0,
      provisionClosing: dis.provisionTotalRow.value
        ? provisionClosing(dis.provisionTotalRow.value as G6ProvisionMovementRow)
        : 0,
      stageMoveRows: s.stageMoveRows,
      transferImbalances: dis.transferImbalances.value,
    },
    AI_TITLES[key],
  )
  if (text) dis.setNote(key, text)
}

onMounted(() => {
  void checkAiHealth()
})

// ─── 同步到附注（§五、15 其他债权投资）──────────────────────────────────────
const isSyncing = ref(false)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId) return
  const payload = buildG6ListedSyncPayload(
    props.wpId,
    props.applicableStandards,
    dis.state.value,
  )
  if (!payload) return
  isSyncing.value = true
  try {
    const res: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const rows = Number((res?.data ?? res)?.rows_synced ?? 0)
    ElMessage.success(
      `已同步 ${rows} 行到附注模块「${G6_NOTE_SECTION.listed} 其他债权投资」`,
    )
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// 数据变更后自动同步（防抖 800ms，只读 / 失败静默）。监听实际披露数据；
// **不加** `_xxxMounted` 一次性防护 —— 它会吞掉"切走再切回"后的第一次真实编辑。
watch(
  () => dis.state.value,
  () => {
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)
</script>

<style scoped>
.g6-disc-listed {
  font-size: 13px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.sheet-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
}

.cross-index {
  display: flex;
  align-items: center;
  gap: 6px;
}

.chip-note {
  font-size: 12px;
  color: #909399;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.objective {
  margin-bottom: 12px;
}

.tie-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  margin-bottom: 8px;
  border-left: 3px solid var(--el-color-success);
  background: var(--el-color-success-light-9);
  border-radius: 3px;
}

.tie-bar.has-issue {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.tie-title {
  font-weight: 600;
}

.tie-bad {
  color: var(--el-color-danger);
  font-weight: 600;
}

.tbl-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0 6px;
}

.tbl-title,
.stage-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.section-gap {
  margin-top: 18px;
}

.tbl-head .el-button {
  margin-left: auto;
}

.disc-table {
  width: 100%;
  font-size: 13px;
}

.formula-cell {
  color: var(--el-color-primary);
  font-variant-numeric: tabular-nums;
}

.fixed-label {
  font-weight: 600;
}

.dash {
  color: #c0c4cc;
}

.row-total :deep(.cell),
.row-subtotal :deep(.cell) {
  font-weight: 600;
}

.row-which :deep(.cell) {
  color: #909399;
}

.inline-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.note-label {
  color: #606266;
  white-space: nowrap;
}

.src-hint {
  margin-top: 8px;
  padding: 6px 10px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 3px;
}

.src-hint p {
  margin: 4px 0;
  color: #8a6d3b;
  font-size: 12px;
  line-height: 1.6;
}

.stage-hint {
  margin-bottom: 10px;
}

.stage-notes {
  margin: 10px 0 16px;
}

.regulation-note {
  margin: 8px 0 0;
  color: #8a6d3b;
  font-size: 12px;
  line-height: 1.6;
}

.sign-hint {
  margin-left: 6px;
  color: #e6a23c;
  cursor: help;
}

.prep-hint {
  margin: 14px 0 4px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 3px;
}

.prep-hint summary {
  cursor: pointer;
  color: #606266;
  font-size: 12px;
}

.prep-hint ol {
  margin: 8px 0 0;
  padding-left: 20px;
  color: #606266;
  font-size: 12px;
  line-height: 1.7;
}
</style>
