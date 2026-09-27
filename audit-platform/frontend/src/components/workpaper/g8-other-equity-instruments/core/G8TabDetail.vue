<template>
  <div class="g8-detail" data-testid="g8-detail-table">
    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><b>定位</b>：本表是科目 1503 其他权益工具投资（<b>FVOCI</b>）的被投资单位明细锚点，向上勾稽 G8-1 审定，向下供 G8-4 / G8-5 / G8-6 取数。</p>
        <p><b>编制顺序</b>：①「辅助核算取数」或手工录入被投资单位 → ②「期初余额」填成本与累计公允价值变动两分量 → ③「本期变动」填成本净额 / 公允价值变动 / 处置结转 / OCI 转留存 → ④ 填指定 OCI 原因 →「回写 G8-1」。</p>
        <p><b>模板公式</b>（8 列自动重算，UI 只读）：期初合计 <code>E=C+D</code>；期初审定 <code>H=E+G</code>；本期变动合计 <code>M=I+J+K+L</code>；期末成本 <code>O=C+I</code>；期末累计公允价值变动 <code>P=D+J+K</code>；期末合计 <code>Q=O+P</code>；期末 OCI 累计 <code>R=F+J+L</code>；期末审定 <code>T=Q+S</code>。</p>
        <p><b>口径要点</b>：本期变动的「成本」是<b>净额</b>列（增加为正、减少为负，模板无单独减少列）；FVOCI 下<b>本期公允价值变动就是本期 OCI</b>（不另设一列）；「本期确认的股利收入」是损益项，不进任何余额；层次 / 估值方法 / 持股数 / 每股公允价值在 <b>G8-4</b> 填报。</p>
        <p><b>与 Excel 联动</b>：期末的「计入 OCI 的累计利得或损失」与「审定数」两列，权威模板在部分行漏写了公式，因此在 Excel 在线编辑里是<b>可填</b>的 —— 但回到本页会按恒等式 <code>R=F+J+L</code> / <code>T=Q+S</code> 重算覆盖。请在本页填写分量，不要在 Excel 侧直接改这两列。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他权益工具投资各被投资单位期末成本、公允价值及 OCI 累计变动明细的准确与完整，验证指定为 FVOCI 恰当，为审定表 G8-1（科目1503）提供明细支撑。"
      class="objective-alert"
    />

    <div class="toolbar">
      <div class="title-block">
        <h3>G8-2 明细表</h3>
        <p class="sheet-sub">被投资单位明细锚点 · 向上勾稽 G8-1 · 向下供 G8-4/G8-5/G8-6 取数</p>
      </div>
      <div class="head-actions">
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-2" @imported="onImported" />
        <GtReviewTrigger section-id="G8-2-detail" />
        <el-button
          v-if="!isReadonly"
          size="small"
          :loading="detail.auxLoading.value"
          data-testid="g8-detail-seed-aux"
          @click="onSeedAux"
        >
          辅助核算取数
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g8-detail-push-adj"
          @click="onPushAdj"
        >
          回写 G8-1
        </el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" data-testid="g8-detail-add" @click="detail.addRow()">
          + 新增行
        </el-button>
      </div>
    </div>
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-5" :context-project-id="projectId" /></span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <div v-if="detail.rows.value.length" class="summary-bar" data-testid="g8-detail-summary">
      <span>审定合计 {{ fmt(detail.totals.value.closingAdjusted) }}</span>
      <span>期末未审 {{ fmt(detail.totals.value.closingTotal) }}</span>
      <span>本期 OCI {{ fmt(detail.totals.value.movementFvChange) }}</span>
      <span>期末 OCI 累计 {{ fmt(detail.totals.value.closingOciCumulative) }}</span>
      <span :class="detail.hasAdjCrossMismatch.value ? 'bad' : 'ok'">
        ↔ G8-1 {{ detail.hasAdjCrossMismatch.value ? '差异' : '一致' }}
      </span>
    </div>

    <el-alert
      v-if="detail.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g8-detail-adj-cross-alert"
    >
      <template #title>
        明细审定合计 {{ fmt(detail.totals.value.closingAdjusted) }} 与 G8-1 审定合计
        {{ fmt(detail.adjudicationClosingTotal.value ?? 0) }} 差异 {{ fmt(detail.adjCrossVariance.value ?? 0) }}
        <el-button link type="primary" size="small" @click="goSheet('G8-1')">去 G8-1</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="detail.integrityIssues.value.length"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g8-detail-integrity-alert"
      :title="integrityTitle"
    />

    <div class="fine-checks">
      <el-tag size="small" :type="detail.hasAdjCrossMismatch.value ? 'warning' : 'success'">G8-CHK 明细↔G8-1</el-tag>
      <el-tag size="small" :type="detail.missingDesignationCount.value ? 'warning' : 'success'">
        指定原因 {{ detail.missingDesignationCount.value ? `缺 ${detail.missingDesignationCount.value}` : '齐' }}
      </el-tag>
      <el-tag size="small" :type="detail.ociRollIssueCount.value ? 'warning' : 'success'">
        OCI滚动 {{ detail.ociRollIssueCount.value ? `差 ${detail.ociRollIssueCount.value}` : '齐' }}
      </el-tag>
      <el-tag size="small" :type="detail.integrityIssues.value.length ? 'warning' : 'success'">
        行完整性 {{ detail.integrityIssues.value.length ? detail.integrityIssues.value.length : '通过' }}
      </el-tag>
    </div>

    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" data-testid="g8-detail-tabs" />
    <el-table
      :data="detail.rows.value"
      border
      size="small"
      style="width:100%;font-size:13px;margin-top:8px"
      highlight-current-row
      :current-row-key="currentRowKey"
      row-key="rowId"
      :row-class-name="rowClassName"
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />

      <!-- ── 基础信息：A / B + U / V / W（模板跨两行合并的单列）───────────── -->
      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="被投资单位" :render-header="th('被投资单位')" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.investeeName" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { investeeName: v })" />
            <span v-else>{{ row.investeeName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投资比例%" :render-header="th('投资比例%')" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="ratioPct(row.investmentRatio)"
              size="small"
              :controls="false"
              :precision="2"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { investmentRatio: pctToRatio(v) })"
            />
            <span v-else>{{ ratioPct(row.investmentRatio) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定数" :render-header="th('期末审定数')" width="110" align="right">
          <template #default="{ row }">
            <strong class="formula-cell" title="T = Q+S">{{ fmt(row.closingAdjusted) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="指定为FVOCI的原因" :render-header="th('指定为以公允价值计量且其变动计入其他综合收益的原因')" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.designationReason"
              size="small"
              :class="{ 'field-warn': needsDesignation(row) }"
              placeholder="非交易性持有目的（指定不可撤销）"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { designationReason: v })"
            />
            <span v-else>{{ row.designationReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI转留存原因" :render-header="th('其他综合收益转入留存收益的原因')" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.transferReason"
              size="small"
              :class="{ 'field-warn': needsTransferReason(row) }"
              placeholder="处置 / 转为长期股权投资"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { transferReason: v })"
            />
            <span v-else>{{ row.transferReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函情况" :render-header="th('发函情况')" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.confirmationStatus || undefined"
              size="small"
              clearable
              filterable
              allow-create
              placeholder="选/填"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v ?? '' })"
            >
              <el-option v-for="o in detail.confirmationStatusOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.confirmationStatus }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ── 期初余额：C / D / E / F + G / H（模板 C9:F9 分组 + 两单列）────── -->
      <template v-else-if="detail.activeTab.value === 'opening'">
        <el-table-column label="被投资单位" :render-header="th('被投资单位')" prop="investeeName" min-width="120" fixed show-overflow-tooltip />
        <el-table-column label="期初余额" :render-header="th('期初余额')" align="center">
          <el-table-column label="成本" :render-header="th('成本')" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingCost" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingCost: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" :render-header="th('累计公允价值变动')" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingFvAccum" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingFvAccum: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingFvAccum) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" :render-header="th('合计')" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="E = SUM(C:D)">{{ fmt(row.openingTotal) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入OCI的累计利得或损失" :render-header="th('计入其他综合收益的累计利得或损失')" width="150" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingOciCumulative" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingOciCumulative: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingOciCumulative) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初调整数" :render-header="th('期初调整数')" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定数" :render-header="th('期初审定数')" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="H = E+G">{{ fmt(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ── 本期变动：I / J / K / L / M / N（模板 I9:N9 分组）────────────── -->
      <template v-else-if="detail.activeTab.value === 'movement'">
        <el-table-column label="被投资单位" :render-header="th('被投资单位')" prop="investeeName" min-width="120" fixed show-overflow-tooltip />
        <el-table-column label="本期变动" :render-header="th('本期变动')" align="center">
          <el-table-column label="成本（净额）" :render-header="th('成本（增加为正 / 减少为负）')" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.movementCost" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { movementCost: v ?? 0 })" />
              <span v-else>{{ fmt(row.movementCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期公允价值变动" :render-header="th('本期公允价值变动（FVOCI 下即本期 OCI）')" width="140" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.movementFvChange" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { movementFvChange: v ?? 0 })" />
              <span v-else>{{ fmt(row.movementFvChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="处置时公允价值变动结转" :render-header="th('处置时公允价值变动结转')" width="150" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.disposalFvTransfer" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { disposalFvTransfer: v ?? 0 })" />
              <span v-else>{{ fmt(row.disposalFvTransfer) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="OCI转入留存收益" :render-header="th('其他综合收益转入留存收益')" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.ociToRetainedEarnings"
                size="small"
                style="width:100%"
                :class="{ 'field-warn': needsTransferReason(row) }"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociToRetainedEarnings: v ?? 0 })"
              />
              <span v-else>{{ fmt(row.ociToRetainedEarnings) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" :render-header="th('合计')" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="M = I+J+K+L">{{ fmt(row.movementTotal) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期确认的股利收入" :render-header="th('本期确认的股利收入（损益项，不进余额）')" width="140" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.dividendIncome" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { dividendIncome: v ?? 0 })" />
              <span v-else>{{ fmt(row.dividendIncome) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </template>

      <!-- ── 期末余额：O / P / Q / R + S / T（模板 O9:R9 分组 + 两单列）────── -->
      <template v-else>
        <el-table-column label="被投资单位" :render-header="th('被投资单位')" prop="investeeName" min-width="120" fixed show-overflow-tooltip />
        <el-table-column label="期末余额" :render-header="th('期末余额')" align="center">
          <el-table-column label="成本" :render-header="th('成本')" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="O = C+I">{{ fmt(row.closingCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" :render-header="th('累计公允价值变动')" width="130" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="P = D+J+K（含处置时结转）">{{ fmt(row.closingFvAccum) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" :render-header="th('合计')" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="Q = O+P">{{ fmt(row.closingTotal) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入OCI的累计利得或损失" :render-header="th('计入其他综合收益的累计利得或损失')" width="150" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="R = F+J+L">{{ fmt(row.closingOciCumulative) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="调整数" :render-header="th('调整数')" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" :render-header="th('审定数')" width="110" align="right">
          <template #default="{ row }">
            <strong class="formula-cell" title="T = Q+S">{{ fmt(row.closingAdjusted) }}</strong>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行（模板 R21，逐列 =SUM(x11:x20)）—— 按模板列顺序展示 -->
    <el-table v-if="detail.rows.value.length" :data="[detail.totals.value]" border size="small" class="totals-table" style="font-size:13px;margin-top:8px">
      <el-table-column label="合计" :render-header="th('合计')" width="72" />
      <el-table-column label="期初成本" :render-header="th('期初成本')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.openingCost) }}</template>
      </el-table-column>
      <el-table-column label="期初审定" :render-header="th('期初审定数')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.openingAdjusted) }}</template>
      </el-table-column>
      <el-table-column label="本期成本" :render-header="th('本期变动 / 成本（净额）')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.movementCost) }}</template>
      </el-table-column>
      <el-table-column label="本期FV变动" :render-header="th('本期公允价值变动')" width="110" align="right">
        <template #default="{ row }">{{ fmt(row.movementFvChange) }}</template>
      </el-table-column>
      <el-table-column label="处置结转" :render-header="th('处置时公允价值变动结转')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.disposalFvTransfer) }}</template>
      </el-table-column>
      <el-table-column label="OCI转留存" :render-header="th('其他综合收益转入留存收益')" width="110" align="right">
        <template #default="{ row }">{{ fmt(row.ociToRetainedEarnings) }}</template>
      </el-table-column>
      <el-table-column label="变动合计" :render-header="th('本期变动合计')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.movementTotal) }}</template>
      </el-table-column>
      <el-table-column label="股利收入" :render-header="th('本期确认的股利收入')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.dividendIncome) }}</template>
      </el-table-column>
      <el-table-column label="期末未审" :render-header="th('期末余额 / 合计')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.closingTotal) }}</template>
      </el-table-column>
      <el-table-column label="期末OCI累计" :render-header="th('期末 计入其他综合收益的累计利得或损失')" width="120" align="right">
        <template #default="{ row }">{{ fmt(row.closingOciCumulative) }}</template>
      </el-table-column>
      <el-table-column label="审定数" :render-header="th('审定数')" width="110" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.closingAdjusted) }}</strong></template>
      </el-table-column>
    </el-table>

    <G8AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      note-placeholder="填写审计说明：（1）明细核对程序及结果；（2）各被投资单位成本、公允价值、OCI 变动的核实情况；（3）与 G8-1/G8-4 勾稽及异常事项。"
      note-hint="覆盖被投资单位明细、指定 OCI 原因、OCI 转留存与跨表勾稽。"
      conclusion-placeholder="填写审计结论：A、明细准确完整，与 G8-1 勾稽一致，指定恰当。B、除已注明事项外未见异常。C、存在重大未决差异或范围受限，不可确认。"
      conclusion-hint="按 A/B/C 口径评价明细充分性。"
      :related-context="{
        rowCount: detail.rows.value.length,
        closingAdjustedTotal: detail.totals.value.closingAdjusted,
        closingUnauditedTotal: detail.totals.value.closingTotal,
        closingOciCumulativeTotal: detail.totals.value.closingOciCumulative,
        integrityIssueCount: detail.integrityIssues.value.length,
        adjCrossVariance: detail.adjCrossVariance.value,
      }"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, inject, ref, watch, h } from 'vue'
import { ElMessage, ElTooltip } from 'element-plus'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import G8AuditTextCards from '../G8AuditTextCards.vue'
import { useG8Detail, type G8DetailRow } from '../../composables/useG8Detail'
import { jumpToG8Sheet } from '../../composables/g8CrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'

/** 表头悬停显示完整列名（避免窄列截断） */
function th(label: string) {
  return () =>
    h(
      ElTooltip,
      { content: label, placement: 'top', showAfter: 200, effect: 'dark' },
      { default: () => h('span', { class: 'th-label' }, label) },
    )
}

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const detail = useG8Detail({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
  projectId: computed(() => props.projectId ?? ''),
})

const AUDIT_NOTE_KEY = 'G8-2-audit-note'
const AUDIT_CONCLUSION_KEY = 'G8-2-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const _detailConcl = props.allResponses.get(AUDIT_CONCLUSION_KEY)
const auditConclusion = ref(String(_detailConcl?.conclusion ?? _detailConcl?.remark ?? ''))
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: v, remark: null })
})

/**
 * 🔴 C-8：四段对齐模板的四个一级分组（原先 `basic`/`fv_oci` 两段是按「自研列 vs OCI 列」
 * 切的，与模板 C9:F9 / I9:N9 / O9:R9 三组 + 单列说明列不对应）。
 */
const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '期初余额', value: 'opening' },
  { label: '本期变动', value: 'movement' },
  { label: '期末余额', value: 'closing' },
]

const currentRowKey = computed(() => {
  const r = detail.rows.value[detail.activeRowIndex.value]
  return r?.rowId
})

const integrityTitle = computed(() => {
  const issues = detail.integrityIssues.value
  if (!issues.length) return ''
  const sample = issues.slice(0, 3).map((i) => `${i.investeeName}：${i.message}`).join('；')
  const more = issues.length > 3 ? `…等共 ${issues.length} 项` : ''
  return `明细完整性提示：${sample}${more}`
})

function onRowChange(row: G8DetailRow | undefined) {
  if (row?.seq) detail.activeRowIndex.value = row.seq - 1
}

function rowClassName({ row }: { row: G8DetailRow }) {
  const hit = detail.integrityIssues.value.some((i) => i.rowId === row.rowId)
  return hit ? 'row-warn' : ''
}

async function onSeedAux() {
  const r = await detail.seedFromAuxBalance()
  if (r.error) {
    ElMessage.warning(r.error)
    return
  }
  ElMessage.success(`辅助核算（${r.dimType}）已同步：新增 ${r.added}，更新 ${r.updated}`)
}

function onPushAdj() {
  if (!detail.rows.value.length) {
    ElMessage.warning('明细为空，无法回写 G8-1')
    return
  }
  if (detail.pushTotalsToAdjudication()) {
    ElMessage.success('已将明细期初审定/期末未审合计回写 G8-1 首行')
  }
}

function onImported() { emit('imported') }

function goSheet(code: string) {
  jumpToG8Sheet(code, jumpToSection)
}

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function ratioPct(ratio: number) {
  return Math.round(Number(ratio || 0) * 10000) / 100
}

function pctToRatio(pct: number | undefined | null) {
  return Math.round(Number(pct || 0) * 100) / 10000
}

function needsDesignation(row: G8DetailRow) {
  return Math.abs(row.closingAdjusted) > 0.01 && !row.designationReason?.trim()
}

function needsTransferReason(row: G8DetailRow) {
  return Math.abs(row.ociToRetainedEarnings) > 0.01 && !row.transferReason?.trim()
}
</script>

<style scoped>
.g8-detail { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.title-block h3 { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
}
.summary-bar .ok { color: #67c23a; font-weight: 600; }
.summary-bar .bad { color: #e6a23c; font-weight: 600; }
.tab-toolbar .toolbar-left { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.guidance-content code { background: #fff; padding: 0 3px; border-radius: 2px; color: #c7254e; }
.objective-alert { margin-bottom: 10px; }
.cross-alert { margin-bottom: 8px; }
.fine-checks { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
.field-warn :deep(.el-input__wrapper),
.field-warn :deep(.el-select__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}
:deep(.row-warn) { background: #fdf6ec !important; }
.th-label {
  display: inline-block;
  max-width: 100%;
  line-height: 1.25;
  white-space: normal;
  word-break: keep-all;
  vertical-align: middle;
  cursor: help;
}
:deep(.el-table th.el-table__cell > .cell) {
  white-space: normal;
  line-height: 1.25;
  overflow: visible;
  text-overflow: unset;
}
</style>
