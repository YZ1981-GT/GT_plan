<template>
  <div class="g13-detail" data-testid="g13-detail">
    <div class="g13-toolbar tab-toolbar">
      <h3 class="g13-title">G13-2 公允价值变动收益明细表</h3>
      <div class="g13-actions">
        <el-input v-model="searchQuery" placeholder="搜索工具名/科目/类型…" size="small"
          clearable style="width:200px" data-testid="g13-detail-search" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">+ 新增行</el-button>
        <el-button
          size="small"
          plain
          :disabled="isReadonly || !projectId"
          :loading="detail.pullLoading.value"
          data-testid="g13-detail-pull-sources"
          @click="detail.pullFromSourceDetails(projectId)"
        >
          ↓ 从源科目带入
        </el-button>
        <el-button
          size="small"
          plain
          :disabled="isReadonly"
          data-testid="g13-detail-sync-ofwhich"
          @click="detail.syncDesignatedOfWhich()"
        >
          ↑ 同步「其中：指定」
        </el-button>
        <el-tag size="small" type="info" effect="plain" data-testid="g13-detail-count">共 {{ detail.rows.value.length }} 行</el-tag>
        <GtIndexChip value="wp:G13-2" :validate="false" />
        <CycleImportExportDropdown :wp-id="wpId" api-prefix="g13" sheet="G13-2"
          :disabled="isReadonly" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G13-2-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        <div class="obj-list">
          <div>审计目标（CAS 39）：</div>
          <div>1. 损益表中记录的公允价值变动收益/损失确实发生，且与被审计单位有关（发生）</div>
          <div>2. 所有应记录的公允价值变动收益/损失均已记录，相关披露均已包含（完整性）</div>
          <div>3. 与公允价值变动收益/损失有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性/计价）</div>
        </div>
      </template>
    </el-alert>

    <el-alert v-if="detail.hasFvMismatch.value" type="error" :closable="false" show-icon
      :title="`存在勾稽不符：${detail.mismatchSummary.value || '请核查 FV变动/对应科目恒等式/计入损益'}`"
      style="margin-bottom:8px" data-testid="g13-detail-mismatch" />

    <el-alert
      v-if="adjWritebackMsg"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g13-detail-adj-writeback-mismatch"
      :title="`G13-2 调整数与 G13-3 回写不一致：${adjWritebackMsg}`"
    />
    <el-alert
      v-else-if="hasG13AdjRows && detail.rows.value.length"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g13-detail-adj-writeback-ok"
      title="G13-2 调整数与 G13-3 账项回写按所属科目一致"
    />

    <el-alert
      v-if="extCross.crossMessage.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g13-detail-ext-cross-bar"
    >
      {{ extCross.crossMessage.value }}
      <el-button
        v-if="extCross.pendingSources.value.length"
        size="small"
        link
        type="primary"
        :loading="extCross.pullLoading.value"
        class="warn-chip"
        @click="extCross.pullSourceFvFromProject()"
      >
        重新拉取源 FV
      </el-button>
    </el-alert>
    <el-alert
      v-else-if="extCross.isReconciled.value"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g13-detail-ext-cross-ok"
    >
      G13-2 与明细涉及的源科目 FV 变动一致
      <span v-if="extCross.activeSources.value.length" class="ok-chip">
        （{{ extCross.activeSources.value.join('、') }}）
      </span>
    </el-alert>
    <el-alert
      v-else-if="detail.rows.value.length && !extCross.activeSources.value.length"
      type="info"
      :closable="false"
      class="cross-alert"
      data-testid="g13-detail-ext-cross-idle"
      title="明细未指定 G1/G8/G9/G10/H3 所属科目，暂不勾稽源 FV"
    />

    <el-alert
      v-if="categoryFilter"
      type="info"
      :closable="true"
      class="cross-alert"
      data-testid="g13-detail-category-filter"
      @close="clearCategoryFilter"
    >
      已筛选分类「{{ categoryFilterLabel }}」共 {{ displayInstrumentCount }} 行
      <el-button size="small" link type="primary" @click="clearCategoryFilter">清除筛选</el-button>
    </el-alert>

    <el-segmented v-model="viewMode" :options="viewOptions" size="small" data-testid="g13-detail-view" style="margin-right:8px" />
    <el-segmented v-if="viewMode === 'instrument'" v-model="activeTab" :options="tabOptions" size="small" data-testid="g13-detail-tab" />

    <!-- 分类汇总（对齐致同固定行） -->
    <el-table
      v-if="viewMode === 'category'"
      :data="detail.categoryDisplayRows.value"
      border
      size="small"
      style="font-size:13px;margin-top:8px"
      max-height="520"
      :row-class-name="categoryRowClass"
      highlight-current-row
      data-testid="g13-detail-category-table"
      class="g13-detail-category-table"
      @row-click="onCategoryRowClick"
    >
      <el-table-column label="项目" min-width="280" fixed>
        <template #default="{ row }">
          <span
            :style="{ paddingLeft: `${(row.indent || 0) * 16}px` }"
            :class="{
              'label-main': row.kind === 'main' || row.rowKey === 'total',
              'label-ofwhich': row.kind === 'ofWhich',
              'label-derivative': row.emphasize,
              'label-clickable': row.rowKey !== 'total' && row.instrumentCount > 0,
            }"
            :title="row.rowKey !== 'total' && row.instrumentCount ? '点击查看对应工具明细' : ''"
          >{{ row.label }}</span>
          <el-tag v-if="row.instrumentCount && row.rowKey !== 'total'" size="small" type="info" effect="plain" style="margin-left:6px">
            {{ row.instrumentCount }} 项 →
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="本期数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">{{ fmt(row.currentUnadjusted) }}</template>
        </el-table-column>
        <el-table-column label="调整数" width="100" align="right">
          <template #default="{ row }">{{ fmt(row.adjustment) }}</template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'cell-error': !row.plReconciled }">{{ fmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="对应科目 — 公允价值变动" align="center">
        <el-table-column label="成本" width="96" align="right">
          <template #default="{ row }">{{ fmt(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="本期FV变动" width="100" align="right">
          <template #default="{ row }">{{ fmt(row.periodFvChange) }}</template>
        </el-table-column>
        <el-table-column label="累计FV变动" width="100" align="right">
          <template #default="{ row }">{{ fmt(row.cumulativeFvChange) }}</template>
        </el-table-column>
        <el-table-column label="公允价值" width="96" align="right">
          <template #default="{ row }">
            <span :class="{ 'cell-error': !row.bsReconciled }">{{ fmt(row.fairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计入损益" width="96" align="right">
          <template #default="{ row }">
            <span :class="{ 'cell-error': !row.plReconciled }">{{ fmt(row.amountInPl) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="核对" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.rowKey === 'total'" size="small" type="info">—</el-tag>
          <el-tag v-else size="small" :type="row.bsReconciled && row.plReconciled ? 'success' : 'danger'">
            {{ row.bsReconciled && row.plReconciled ? 'TRUE' : 'FALSE' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="100">
        <template #default="{ row }">
          <GtIndexChip v-if="row.sourceIndex" :value="row.sourceIndex" />
        </template>
      </el-table-column>
    </el-table>

    <el-table v-else :data="displayRows" border size="small" style="font-size:13px;margin-top:8px" max-height="520"
      :row-class-name="rowClassName" data-testid="g13-detail-table">
      <el-table-column label="序号" prop="seq" width="56" align="center" fixed />

      <template v-if="activeTab === 'basic'">
        <el-table-column label="金融工具名称" min-width="140">
          <template #default="{ row }">
            <template v-if="row.rowId !== 'total'">
              <GtReviewDot row-prefix="G13-detail" :row-key="row.rowId" />
            </template>
            <el-input v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.instrumentName" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'instrumentName', v)" />
            <span v-else>{{ row.instrumentName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所属科目" width="168">
          <template #default="{ row }">
            <el-select v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.belongAccount" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'belongAccount', v)">
              <el-option v-for="a in detail.G13_BELONG_ACCOUNTS" :key="a" :label="G13_BELONG_ACCOUNT_LABELS[a] ?? a" :value="a" />
              <el-option label="其他" value="" />
            </el-select>
            <span v-else>{{ row.belongAccount ? (G13_BELONG_ACCOUNT_LABELS[row.belongAccount] ?? row.belongAccount) : '其他' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金融工具类型" width="120">
          <template #default="{ row }">
            <el-select v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.instrumentType" size="small" filterable allow-create
              @change="(v: string) => detail.updateCell(row.rowId, 'instrumentType', v)">
              <el-option v-for="t in G13_INSTRUMENT_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.instrumentType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="源科目索引" width="108">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.sourceIndex" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'sourceIndex', v)" />
            <GtIndexChip v-else-if="row.sourceIndex" :value="row.sourceIndex" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.remark" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else-if="activeTab === 'fv'">
        <el-table-column label="期初FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.openingFairValue"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowId, 'openingFairValue', v ?? 0)" />
            <span v-else>{{ fmt(row.openingFairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.closingFairValue"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowId, 'closingFairValue', v ?? 0)" />
            <span v-else>{{ fmt(row.closingFairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="FV变动 = 期末 − 期初">{{ fmt(row.fvChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期未审" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.currentUnadjusted"
              size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.rowId, 'currentUnadjusted', v ?? 0)" />
            <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整数" width="110" align="right">
          <template #default="{ row }">
            <div :class="{ 'adj-mismatch-cell': isBelongAdjMismatch(row.belongAccount) }">
              <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.adjustment"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowId, 'adjustment', v ?? 0)" />
              <span v-else :class="{ 'cell-error': isBelongAdjMismatch(row.belongAccount) }">{{ fmt(row.adjustment) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'cell-error': row.rowId !== 'total' && !row.fvReconciled }]"
              title="审定 = 未审 + 调整；应与 FV变动、计入损益一致">{{ fmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="交叉验证" width="100">
          <template #default="{ row }">
            <el-select v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.crossVerification" size="small"
              @change="(v: string) => detail.updateCell(row.rowId, 'crossVerification', v)">
              <el-option v-for="o in G13_CROSS_VERIFY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-tag v-else-if="row.rowId !== 'total'" size="small"
              :type="row.crossVerification === 'consistent' ? 'success' : row.crossVerification === 'inconsistent' ? 'danger' : 'info'">
              {{ G13_CROSS_VERIFY_OPTIONS.find(o => o.value === row.crossVerification)?.label ?? '待验证' }}
            </el-tag>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="对应科目 — 公允价值变动" align="center">
          <el-table-column label="成本" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.cost"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowId, 'cost', v ?? 0)" />
              <span v-else>{{ fmt(row.cost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期FV变动" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.periodFvChange"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowId, 'periodFvChange', v ?? 0)" />
              <span v-else>{{ fmt(row.periodFvChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计FV变动" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.cumulativeFvChange"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowId, 'cumulativeFvChange', v ?? 0)" />
              <span v-else>{{ fmt(row.cumulativeFvChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.fairValue"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowId, 'fairValue', v ?? 0)" />
              <span v-else :class="{ 'cell-error': !row.bsReconciled }">{{ fmt(row.fairValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入损益" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== 'total' && !isReadonly" :model-value="row.amountInPl"
                size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => detail.updateCell(row.rowId, 'amountInPl', v ?? 0)" />
              <span v-else :class="{ 'cell-error': !row.plReconciled }">{{ fmt(row.amountInPl) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="核对" width="88" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.rowId === 'total'" size="small" type="info">—</el-tag>
            <el-tag v-else size="small" :type="row.bsReconciled && row.plReconciled ? 'success' : 'danger'"
              :title="row.bsReconciled && row.plReconciled
                ? '成本+累计FV=公允价值 且 计入损益=审定数'
                : (!row.bsReconciled ? '成本+累计FV≠公允价值' : '计入损益≠审定数')">
              {{ row.bsReconciled && row.plReconciled ? 'TRUE' : 'FALSE' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="来自「损益审定」区：未审+调整">{{ fmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="row.rowId !== 'total'" title="确认删除？" @confirm="detail.removeRow(row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="viewMode === 'instrument' && Object.keys(detail.groupSubtotals.value).length" shadow="never" class="group-card">
      <template #header>按所属科目分组小计（对齐 G13-1 分类）</template>
      <el-table :data="groupRows" border size="small" style="font-size:13px" data-testid="g13-detail-groups">
        <el-table-column label="对应科目/分组" prop="label" min-width="180" />
        <el-table-column label="审定数合计" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.currentAudited) }}</template>
        </el-table-column>
        <el-table-column label="计入损益合计" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.amountInPl) }}</template>
        </el-table-column>
        <el-table-column label="FV变动合计" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.fvChange) }}</template>
        </el-table-column>
        <el-table-column label="公允价值合计" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.fairValue) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>三、审计说明</template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="概述测试情况、结果；拟调整事项及调整分录；未调整事项及对报表的影响；审计范围受限情况。可说明与源科目（G1/G8/G9/G10/H3）交叉验证及对应科目 FV 勾稽结果。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-select
            v-if="!isReadonly"
            placeholder="套用结论模板"
            size="small"
            clearable
            style="width:280px"
            data-testid="g13-detail-conclusion-tpl"
            @change="applyConclusionTpl"
          >
            <el-option label="A · 未见异常" value="A" />
            <el-option label="B · 除拟调整外未见异常" value="B" />
            <el-option label="C · 重大未调整/证据不足不可确认" value="C" />
          </el-select>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论，或上方套用模板后微调。"
        @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint" open>
      <summary>📋 编制说明</summary>
      <p>1. 编制思路：损益侧（未审→调整→审定）与对应科目侧（成本 / 本期FV / 累计FV / 公允价值 / 计入损益）双向勾稽，验证 6101 计量准确。</p>
      <p>2. 恒等式（对齐致同模板「核对」列）：成本 + 累计公允价值变动 = 公允价值；计入损益 = 审定数；FV变动(期末−期初) = 审定数。</p>
      <p>3. 「工具明细 / 分类汇总」双视图：分类汇总对齐致同固定行；点击有明细的分类行可跳转并筛选工具；「其中：指定」为备忘子集，不计入合计。</p>
      <p>4. 「从源科目带入」拉取 G1/G8/G9/G10/H3，空字段合并并自动交叉验证；有指定类时自动同步 G13-1「其中」备忘行。</p>
      <p>5. 「调整数」应与 G13-3 账项调整按所属科目回写净额一致；不符时本表会高亮并提示，可至 G13-3「确认调整」重新同步。</p>
      <p>6. 审计说明应含测试结果、拟调整/未调整事项及影响、范围受限；结论可套用 A/B/C。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, onMounted } from 'vue'
import { useG13Detail } from '../composables/useG13Detail'
import { useG13ExternalCross } from '../composables/useG13ExternalCross'
import {
  findG13AdjustmentWritebackMismatches,
  formatG13AdjWritebackMismatchMessage,
  G13_AJE_ITEM_ID,
} from '../composables/g13FvCrossHelpers'
import {
  G13_BELONG_ACCOUNT_LABELS,
  G13_INSTRUMENT_TYPES,
  G13_CROSS_VERIFY_OPTIONS,
  G13_ADJ_BY_KEY,
  detailRowMatchesCategory,
} from '../composables/g13Constants'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const projectId = computed(() => props.projectId ?? '')

const NOTE_KEY = 'G13-detail-audit-note'
const CONCLUSION_KEY = 'G13-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

const CONCLUSION_TEMPLATES: Record<string, string> = {
  A: '经审计，未见异常。',
  B: '经审计，除上述重大不符事项应予调整外，其余未见异常。',
  C: '经审计，由于存在重大未调整事项 / 未能获取充分适当的审计证据，不可确认。',
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val } as ChecklistResponse)
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: val, remark: null } as ChecklistResponse)
  props.debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })
}

function applyConclusionTpl(key: string): void {
  if (!key || props.isReadonly) return
  const text = CONCLUSION_TEMPLATES[key]
  if (text) saveAuditConclusion(text)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.conclusion || c?.remark) auditConclusion.value = String(c.conclusion ?? c.remark ?? '')
})

const activeTab = ref<'basic' | 'fv' | 'bs'>('basic')
const viewMode = ref<'instrument' | 'category'>('instrument')
const categoryFilter = ref<string | null>(null)
const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '损益审定', value: 'fv' },
  { label: '对应科目FV', value: 'bs' },
]
const viewOptions = [
  { label: '工具明细', value: 'instrument' },
  { label: '分类汇总', value: 'category' },
]

const detail = useG13Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})
const searchQuery = detail.searchQuery

const extCross = useG13ExternalCross({
  allResponses: toRef(props, 'allResponses'),
  detailRows: computed(() => detail.rows.value),
  debouncedSave: props.debouncedSave,
  projectId,
})

const g13AdjRows = computed(() => {
  const raw = props.allResponses.get(G13_AJE_ITEM_ID)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
})

const hasG13AdjRows = computed(() => g13AdjRows.value.length > 0)

const adjWritebackMismatches = computed(() =>
  findG13AdjustmentWritebackMismatches(detail.rows.value, g13AdjRows.value),
)

const adjWritebackMsg = computed(() =>
  formatG13AdjWritebackMismatchMessage(adjWritebackMismatches.value),
)

const mismatchBelongSet = computed(() =>
  new Set(adjWritebackMismatches.value.map((m) => m.belong)),
)

function isBelongAdjMismatch(belong: string | undefined): boolean {
  if (!mismatchBelongSet.value.size) return false
  const raw = String(belong || '').trim()
  const key = raw && ['G1', 'G8', 'G9', 'G10', 'H3'].includes(raw) ? raw : 'other'
  return mismatchBelongSet.value.has(key)
}

const categoryFilterLabel = computed(() => {
  if (!categoryFilter.value) return ''
  return G13_ADJ_BY_KEY[categoryFilter.value]?.label ?? categoryFilter.value
})

const displayInstrumentCount = computed(() => {
  const data = searchQuery.value.trim() ? detail.filteredRows.value : detail.rows.value
  if (!categoryFilter.value) return data.length
  return data.filter((r) => detailRowMatchesCategory(r, categoryFilter.value!)).length
})

const displayRows = computed(() => {
  let data = searchQuery.value.trim() ? detail.filteredRows.value : detail.rows.value
  if (categoryFilter.value) {
    data = data.filter((r) => detailRowMatchesCategory(r, categoryFilter.value!))
  }
  // 筛选时合计仅汇总可见行，避免与全表明细混淆
  if (categoryFilter.value || searchQuery.value.trim()) {
    const currentUnadjusted = data.reduce((s, r) => s + r.currentUnadjusted, 0)
    const adjustment = data.reduce((s, r) => s + r.adjustment, 0)
    const currentAudited = data.reduce((s, r) => s + r.currentAudited, 0)
    const fvChange = data.reduce((s, r) => s + r.fvChange, 0)
    const cost = data.reduce((s, r) => s + r.cost, 0)
    const periodFvChange = data.reduce((s, r) => s + r.periodFvChange, 0)
    const cumulativeFvChange = data.reduce((s, r) => s + r.cumulativeFvChange, 0)
    const fairValue = data.reduce((s, r) => s + r.fairValue, 0)
    const amountInPl = data.reduce((s, r) => s + r.amountInPl, 0)
    const openingFairValue = data.reduce((s, r) => s + r.openingFairValue, 0)
    const closingFairValue = data.reduce((s, r) => s + r.closingFairValue, 0)
    const subtotal = {
      ...detail.totalRow.value,
      rowId: 'total',
      seq: 0,
      instrumentName: categoryFilter.value ? `小计（${categoryFilterLabel.value}）` : '小计（筛选）',
      currentUnadjusted,
      adjustment,
      currentAudited,
      fvChange,
      cost,
      periodFvChange,
      cumulativeFvChange,
      fairValue,
      amountInPl,
      openingFairValue,
      closingFairValue,
      fvReconciled: true,
      bsReconciled: true,
      plReconciled: true,
      allReconciled: true,
    }
    return [...data, subtotal]
  }
  return [...data, detail.totalRow.value]
})

function onCategoryRowClick(row: { rowKey: string; label: string; instrumentCount: number }): void {
  if (row.rowKey === 'total') return
  if (!row.instrumentCount) return
  categoryFilter.value = row.rowKey
  viewMode.value = 'instrument'
  activeTab.value = 'bs'
}

function clearCategoryFilter(): void {
  categoryFilter.value = null
}

const groupRows = computed(() =>
  Object.entries(detail.groupSubtotals.value)
    .filter(([, v]) => v.currentAudited !== 0 || v.fvChange !== 0 || v.amountInPl !== 0 || v.fairValue !== 0)
    .map(([, v]) => v),
)

function rowClassName({ row }: { row: { rowId: string; allReconciled?: boolean } }): string {
  if (row.rowId === 'total') return 'g13-row-total'
  if (row.allReconciled === false) return 'g13-row-mismatch'
  return ''
}

function categoryRowClass({ row }: { row: { rowKey: string; kind?: string; bsReconciled?: boolean; plReconciled?: boolean } }): string {
  if (row.rowKey === 'total') return 'g13-row-total'
  if (row.kind === 'ofWhich') return 'g13-row-ofwhich'
  if (row.bsReconciled === false || row.plReconciled === false) return 'g13-row-mismatch'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.cross-alert { margin-bottom: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.audit-objective { margin-bottom: 8px; }
.obj-list { font-size: 12px; line-height: 1.55; }
.g13-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g13-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.g13-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.g13-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #fafafa; display: inline-block; width: 100%; }
.cell-error { color: #f56c6c; font-weight: 600; }
.adj-mismatch-cell {
  background: #fef0f0;
  border-radius: 2px;
  padding: 0 2px;
}
:deep(.g13-row-total) { font-weight: 700; background: #f5f7fa; }
:deep(.g13-row-mismatch) { background: #fef0f0 !important; }
:deep(.g13-row-ofwhich) { color: #606266; font-style: italic; }
.label-main { font-weight: 600; }
.label-ofwhich { color: #909399; }
.label-derivative { color: #c45656; }
.label-clickable { cursor: pointer; border-bottom: 1px dashed #409eff; }
:deep(.el-table__row) { cursor: default; }
:deep(.g13-detail-category-table .el-table__row) { cursor: pointer; }
.group-card { margin-top: 12px; }
.audit-note-card { margin-top: 12px; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
.compile-hint p { margin: 4px 0; }
</style>
