<template>
  <div class="n1-tab-calc-table">
    <!-- 双模式切换栏由入口 GtN1DeferredTaxAssets 统一渲染（避免双层切换栏 + 两个实例状态不同步） -->

    <!-- ═══ OnlyOffice 降级模式 ═══ -->
    <template v-if="dualMode.isOnlyOffice.value">
      <!-- 铁律：sheet-name 必须与源 xlsx tab 名完全一致 -->
      <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="递延所得税资产（负债）测算表N1-4" style="height: 100%; min-height: 600px" />
    </template>

    <!-- ═══ 结构化视图 ═══ -->
    <template v-else>
      <!-- ═══ 蓝色渐变引导区（多步骤引导） ═══ -->
      <div class="n1-guidance-banner">
        <div class="guidance-grid">
          <div class="guidance-step">
            <span class="step-num">①</span>
            <span class="step-text">录入各暂时性差异项目的账面价值和计税基础</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">②</span>
            <span class="step-text">系统自动计算可抵扣/应纳税暂时性差异</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">③</span>
            <span class="step-text">确认条件判断：检查未来应纳税所得额充足性</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">④</span>
            <span class="step-text">资产部分回填N1-1，负债部分联动N3</span>
          </div>
        </div>
      </div>

      <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
      <div class="n1-methodology-ctx">
        <p><strong>递延所得税测算逻辑</strong>：暂时性差异 = 账面价值 − 计税基础。</p>
        <p>资产项：账面 &gt; 计税基础 → 应纳税暂时性差异 → 递延所得税负债(N3)；账面 &lt; 计税基础 → 可抵扣暂时性差异 → 递延所得税资产(N1)</p>
        <p>递延所得税 = 暂时性差异 × 适用税率。确认递延税资产的前提：预期未来有足够应纳税所得额。</p>
      </div>

      <!-- ═══ 资产类科目公式提示 ═══ -->
      <div class="n1-asset-formula-badge">
        <el-icon><WarningFilled /></el-icon>
        <span>本表同源产出递延税资产(N1)和递延税负债(N3)两部分，不能抵销的分列展示</span>
      </div>

      <!-- ═══ 测算表主 Section ═══ -->
      <el-card shadow="never" class="n1-section-card">
        <template #header>
          <div class="section-header">
            <div class="section-title-group">
              <span class="section-title">递延所得税资产(负债)测算表 N1-4</span>
              <el-tag type="info" size="small">63×15 · 21公式</el-tag>
            </div>
            <div class="section-actions">
              <el-button size="small" @click="handleRefreshFromDetail">
                <el-icon><RefreshRight /></el-icon> 从N1-2刷新
              </el-button>
              <el-button size="small" :disabled="isReadonly" @click="handlePullFromLossCheck">
                从N1-5带入可弥补亏损
              </el-button>
              <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handlePushDiffToAdjustment">
                推送差异至N1-3
              </el-button>
              <el-dropdown trigger="click" @command="handleImportExportCmd">
                <el-button size="small">导入导出 ▾</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                    <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                    <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" @click="handleAI('calc')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
              <GtReviewTrigger section-id="N1-4-测算表" label="💬 复核" />
            </div>
          </div>
        </template>

        <!-- 动态行新增 -->
        <div v-if="!isReadonly" class="n1-row-actions">
          <el-button type="primary" size="small" @click="handleAddRow">+ 新增测算项</el-button>
          <span class="row-count">共 {{ calcTable.rows.value.length }} 项</span>
        </div>

        <!-- ═══ 资产类部分（上半·浅绿） ═══ -->
        <div class="dual-part-label asset-part-label">
          <span class="part-dot asset-dot"></span>
          <span>递延所得税资产部分（可抵扣暂时性差异 → N1）</span>
          <GtIndexChip value="N1-1" :context-project-id="projectId" />
          <GtIndexChip value="N1-2" :context-project-id="projectId" />
        </div>

        <el-table
          :data="assetRows"
          border
          size="small"
          style="width: 100%"
          class="calc-table asset-table"
          show-summary
          :summary-method="getAssetSummaries"
        >
          <el-table-column prop="itemName" label="项目" min-width="140" fixed>
            <template #default="{ row }">
              <span class="item-name-cell">{{ row.itemName }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bookValue" label="账面价值" min-width="110" align="right">
            <template #default="{ row }">
              <el-tooltip content="暂时性差异项目的账面价值" placement="top">
                <span class="cell-value">{{ fmtAmt(row.bookValue) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="taxBase" label="计税基础" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cell-value">{{ fmtAmt(row.taxBase) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="deductibleDiff" label="可抵扣暂时性差异" min-width="130" align="right">
            <template #header>
              <el-tooltip content="可抵扣暂时性差异 = max(0, 计税基础 − 账面价值)" placement="top">
                <span class="formula-col">可抵扣暂时性差异</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="计税基础 − 账面价值（资产项账面＜计税基础时产生）" placement="top">
                <span class="formula-value">{{ fmtAmt(row.deductibleDiff) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="taxRate" label="适用税率" min-width="80" align="center">
            <template #default="{ row }">
              <span>{{ fmtPercent(row.taxRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="deferredTaxAsset" label="递延所得税资产" min-width="130" align="right">
            <template #header>
              <el-tooltip content="递延所得税资产 = 可抵扣暂时性差异 × 适用税率" placement="top">
                <span class="formula-col">递延所得税资产</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="可抵扣差异 × 税率" placement="top">
                <span class="formula-value asset-value">{{ fmtAmt(row.deferredTaxAsset) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="assetBookBalance" label="账面余额" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cell-value">{{ fmtAmt(row.assetBookBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="assetDiff" label="应调整" min-width="100" align="right">
            <template #header>
              <el-tooltip content="应调整 = 应确认递延税资产 − 当前账面余额" placement="top">
                <span class="formula-col">应调整</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span :class="['formula-value', { 'text-danger': row.assetDiff !== 0, 'text-success': row.assetDiff === 0 }]">
                {{ fmtAmt(row.assetDiff) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="确认条件" min-width="90" align="center">
            <template #header>
              <el-tooltip content="是否满足确认条件：预期未来有足够应纳税所得额" placement="top">
                <span class="formula-col">确认条件</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span v-if="row.deductibleDiff > 0" :class="getConfirmClass(row)">
                {{ getConfirmLabel(row) }}
              </span>
              <span v-else class="text-muted">—</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- ═══ 负债类部分（下半·浅紫） ═══ -->
        <div class="dual-part-label liability-part-label">
          <span class="part-dot liability-dot"></span>
          <span>递延所得税负债部分（应纳税暂时性差异 → N3）</span>
          <GtIndexChip value="N3-2" :context-project-id="projectId" />
          <GtIndexChip value="N5-8" :context-project-id="projectId" />
        </div>

        <el-table
          :data="liabilityRows"
          border
          size="small"
          style="width: 100%"
          class="calc-table liability-table"
          show-summary
          :summary-method="getLiabilitySummaries"
        >
          <el-table-column prop="itemName" label="项目" min-width="140" fixed>
            <template #default="{ row }">
              <span class="item-name-cell">{{ row.itemName }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bookValue" label="账面价值" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cell-value">{{ fmtAmt(row.bookValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="taxBase" label="计税基础" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cell-value">{{ fmtAmt(row.taxBase) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="taxableDiff" label="应纳税暂时性差异" min-width="130" align="right">
            <template #header>
              <el-tooltip content="应纳税暂时性差异 = max(0, 账面价值 − 计税基础)" placement="top">
                <span class="formula-col">应纳税暂时性差异</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="账面价值 − 计税基础（资产项账面＞计税基础时产生）" placement="top">
                <span class="formula-value">{{ fmtAmt(row.taxableDiff) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="taxRate" label="适用税率" min-width="80" align="center">
            <template #default="{ row }">
              <span>{{ fmtPercent(row.taxRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="deferredTaxLiability" label="递延所得税负债" min-width="130" align="right">
            <template #header>
              <el-tooltip content="递延所得税负债 = 应纳税暂时性差异 × 适用税率" placement="top">
                <span class="formula-col">递延所得税负债</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="应纳税差异 × 税率" placement="top">
                <span class="formula-value liability-value">{{ fmtAmt(row.deferredTaxLiability) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="liabilityBookBalance" label="账面余额" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cell-value">{{ fmtAmt(row.liabilityBookBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="liabilityDiff" label="应调整" min-width="100" align="right">
            <template #header>
              <el-tooltip content="应调整 = 应确认递延税负债 − 当前账面余额" placement="top">
                <span class="formula-col">应调整</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span :class="['formula-value', { 'text-danger': row.liabilityDiff !== 0, 'text-success': row.liabilityDiff === 0 }]">
                {{ fmtAmt(row.liabilityDiff) }}
              </span>
            </template>
          </el-table-column>
        </el-table>

        <!-- ═══ 全量编辑表（结构化视图编辑模式） ═══ -->
        <template v-if="!isReadonly">
          <div class="dual-part-label edit-part-label">
            <span class="part-dot edit-dot"></span>
            <span>编辑区（输入账面价值/计税基础/税率/账面余额）</span>
          </div>

          <el-table
            :data="calcTable.rows.value"
            border
            size="small"
            style="width: 100%"
            class="calc-table edit-table"
            max-height="400"
          >
            <el-table-column prop="itemName" label="项目" min-width="140" fixed>
              <template #default="{ row }">
                <span class="item-name-cell">{{ row.itemName }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="bookValue" label="账面价值" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number :model-value="row.bookValue" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => calcTable.updateRow($index, 'bookValue', v ?? 0)" />
              </template>
            </el-table-column>
            <el-table-column prop="taxBase" label="计税基础" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number :model-value="row.taxBase" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => calcTable.updateRow($index, 'taxBase', v ?? 0)" />
              </template>
            </el-table-column>
            <el-table-column prop="taxRate" label="税率(%)" min-width="80" align="center">
              <template #default="{ row, $index }">
                <el-input-number :model-value="row.taxRate * 100" size="small" :controls="false" :precision="0" :min="0" :max="100" class="cell-input" @change="(v: number) => calcTable.updateRow($index, 'taxRate', (v ?? 25) / 100)" />
              </template>
            </el-table-column>
            <el-table-column prop="assetBookBalance" label="资产账面余额" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number :model-value="row.assetBookBalance" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => calcTable.updateRow($index, 'assetBookBalance', v ?? 0)" />
              </template>
            </el-table-column>
            <el-table-column prop="liabilityBookBalance" label="负债账面余额" min-width="120" align="right">
              <template #default="{ row, $index }">
                <el-input-number :model-value="row.liabilityBookBalance" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => calcTable.updateRow($index, 'liabilityBookBalance', v ?? 0)" />
              </template>
            </el-table-column>
            <el-table-column label="" width="60" align="center" fixed="right">
              <template #default="{ $index }">
                <el-button type="danger" size="small" link @click="calcTable.removeRow($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-card>

      <!-- ═══ 合计 + 回填操作区 ═══ -->
      <div class="n1-calc-totals">
        <div class="total-section total-asset">
          <div class="total-info">
            <span class="total-label">递延所得税资产合计（归N1）</span>
            <span class="total-value asset-value">{{ fmtAmt(calcTable.totals.value.deferredTaxAsset) }}</span>
          </div>
          <el-button
            type="success"
            size="small"
            :disabled="isReadonly"
            :loading="writebackAssetLoading"
            @click="handleWritebackAsset"
          >
            回填 → N1-1
          </el-button>
        </div>
        <div class="total-section total-liability">
          <div class="total-info">
            <span class="total-label">递延所得税负债合计（联动N3）</span>
            <span class="total-value liability-value">{{ fmtAmt(calcTable.totals.value.deferredTaxLiability) }}</span>
          </div>
          <el-button
            type="warning"
            size="small"
            :disabled="isReadonly"
            :loading="writebackLiabilityLoading"
            @click="handlePublishToN3"
          >
            联动 → N3
          </el-button>
        </div>
      </div>

      <!-- ═══ 交叉验证区 ═══ -->
      <div class="n1-cross-validation">
        <div class="cv-title">交叉验证</div>
        <div class="cv-indicators">
          <div class="cv-item" :class="crossSheet.adjudicationVsCalcTable.value.isMatch ? 'cv-match' : 'cv-diff'">
            <span class="cv-label">N1-1审定确认额 vs N1-4测算结果</span>
            <span v-if="crossSheet.adjudicationVsCalcTable.value.isMatch" class="cv-badge cv-badge-ok">✓ 一致</span>
            <span v-else class="cv-badge cv-badge-err">⚠ 差异 {{ fmtAmt(crossSheet.adjudicationVsCalcTable.value.diff) }}</span>
            <GtIndexChip value="N1-1" :context-project-id="projectId" />
          </div>
          <div class="cv-item" :class="calcTable.totals.value.assetDiff === 0 ? 'cv-match' : 'cv-diff'">
            <span class="cv-label">递延税资产应确认额 vs 账面余额</span>
            <span v-if="calcTable.totals.value.assetDiff === 0" class="cv-badge cv-badge-ok">✓ 一致</span>
            <span v-else class="cv-badge cv-badge-err">⚠ 差异 {{ fmtAmt(calcTable.totals.value.assetDiff) }}</span>
          </div>
          <div class="cv-item" :class="calcTable.totals.value.liabilityDiff === 0 ? 'cv-match' : 'cv-diff'">
            <span class="cv-label">递延税负债应确认额 vs 账面余额</span>
            <span v-if="calcTable.totals.value.liabilityDiff === 0" class="cv-badge cv-badge-ok">✓ 一致</span>
            <span v-else class="cv-badge cv-badge-err">⚠ 差异 {{ fmtAmt(calcTable.totals.value.liabilityDiff) }}</span>
            <GtIndexChip value="N3-2" :context-project-id="projectId" />
          </div>
          <div class="cv-item cv-info">
            <span class="cv-label">N1-5可弥补亏损可确认递延税资产</span>
            <span class="cv-badge cv-badge-info">{{ fmtAmt(crossSheet.lossCheckToCalcTable.value.total) }}</span>
            <GtIndexChip value="N1-5" :context-project-id="projectId" />
          </div>
        </div>
      </div>

      <!-- ═══ 确认条件判断区 ═══ -->
      <div class="n1-confirm-condition">
        <div class="confirm-title">确认条件判断（未来应纳税所得额充足性）</div>
        <div class="confirm-items">
          <div v-for="row in assetRows" :key="row.id" class="confirm-item">
            <span class="confirm-name">{{ row.itemName }}</span>
            <span :class="getConfirmClass(row)">{{ getConfirmLabel(row) }}</span>
          </div>
          <div v-if="assetRows.length === 0" class="confirm-empty">暂无可抵扣暂时性差异项目</div>
        </div>
      </div>

      <!-- ═══ N3对应关系 ═══ -->
      <div class="n3-correspondence-section">
        <div class="n3-title">
          <span>N1-4测算表 → N1/N3分列展示</span>
          <GtIndexChip value="N1-1" :context-project-id="projectId" />
          <GtIndexChip value="N3-2" :context-project-id="projectId" />
        </div>
        <div class="n3-details">
          <div class="n3-item">
            <span class="n3-label">可抵扣暂时性差异合计 → 递延税资产（N1）：</span>
            <span class="n3-value asset-value">{{ fmtAmt(crossSheet.n1ToN3Correspondence.value.assetPart) }}</span>
          </div>
          <div class="n3-item">
            <span class="n3-label">应纳税暂时性差异合计 → 递延税负债（N3）：</span>
            <span class="n3-value liability-value">{{ fmtAmt(crossSheet.n1ToN3Correspondence.value.liabilityPart) }}</span>
          </div>
          <div class="n3-item">
            <span class="n3-label">递延税资产本期变动额（供N5核对）：</span>
            <span :class="['n3-value', { 'text-danger': crossSheet.deferredTaxChange.value.change < 0 }]">
              {{ fmtAmt(crossSheet.deferredTaxChange.value.change) }}
            </span>
            <GtIndexChip value="N5-8" :context-project-id="projectId" />
          </div>
        </div>
      </div>

      <!-- ═══ 审计说明与结论 ═══ -->
      <el-card shadow="never" class="n1-section-card">
        <template #header>
          <div class="section-header">
            <span class="section-title">审计说明与结论</span>
            <div class="section-actions">
              <el-button size="small" @click="handleAI('conclusion')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
              <GtReviewTrigger section-id="N1-4-结论" label="💬 复核" />
            </div>
          </div>
        </template>
        <div class="n1-conclusion-area">
          <div class="field-group">
            <label class="field-label">测算说明</label>
            <el-input
              v-model="auditNotes"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="说明测算方法、暂时性差异来源及确认判断依据..."
              @change="handleNotesSave"
            />
          </div>
          <div class="field-group">
            <label class="field-label">审计结论</label>
            <el-input
              v-model="auditConclusion"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="经测算，递延所得税资产/负债确认金额合理..."
              @change="handleConclusionSave"
            />
          </div>
        </div>
      </el-card>

      <!-- ═══ 编制提示（折叠底部） ═══ -->
      <details class="n1-details-tip">
        <summary>编制提示</summary>
        <ul>
          <li>暂时性差异 = 账面价值 − 计税基础</li>
          <li>资产项：账面 &gt; 计税基础 → <strong>应纳税</strong>暂时性差异 → 递延所得税<strong>负债</strong>（归N3）</li>
          <li>资产项：账面 &lt; 计税基础 → <strong>可抵扣</strong>暂时性差异 → 递延所得税<strong>资产</strong>（归N1）</li>
          <li>递延所得税 = 暂时性差异 × 适用税率（一般25%，高新15%，小微5%/10%/20%）</li>
          <li>确认递延税资产前提：预期未来有足够应纳税所得额用以利用可抵扣差异</li>
          <li>N1-5可弥补亏损可确认额 = min(未弥补亏损, 预计未来应纳税所得额) × 税率</li>
          <li>"回填→N1-1"将资产部分合计写入N1-1审定表</li>
          <li>"联动→N3"将负债部分合计通过EventBus发布给N3递延所得税负债底稿</li>
          <li>同一纳税主体递延税资产与负债可抵销后净额列示；不同主体不能抵销</li>
          <li>本表63行×15列，覆盖21个计算公式</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabCalcTable — N1-4 递延所得税资产(负债)测算表（核心）
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 4.4
 * Requirements: 4.1-4.6
 *
 * 核心职责：
 * - 63×15，21公式 + 资产/负债双部分测算
 * - 确认条件判断（未来应纳税所得额充足性）
 * - 回填N1-1（递延税资产部分）/ 联动N3（递延税负债部分）
 * - 与N1-1审定+N3审定交叉验证
 * - GtIndexChip跳转: N1-1, N1-2, N3-2, N5-8
 * - EventBus publish 'deferred-tax:asset-updated'
 * - 双部分分组显示（资产类浅绿 / 负债类浅紫）
 * - 蓝色渐变引导区 + 方法论琥珀块 + 公式虚线 + tooltip
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, computed, onMounted, onUnmounted, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarningFilled, MagicStick, RefreshRight } from '@element-plus/icons-vue'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'
// @ts-ignore
import GtReviewTrigger from '../../GtReviewTrigger.vue'
// @ts-ignore
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import { useN1FormData } from '../../composables/useN1FormData'
import { useN1CalcTable } from '../../composables/useN1CalcTable'
import { useN1CrossSheet } from '../../composables/useN1CrossSheet'
import { useN1DualMode } from '../../composables/useN1DualMode'
import { useN1ImportExport } from '../../composables/useN1ImportExport'
import { generateN1Text } from '../../composables/useN1AiText'
import { deriveDisclosureLossRows } from '../../composables/useN1DisclosureSource'
import { eventBus } from '@/utils/eventBus'
import type { N1CalcTableComputed } from '../../composables/useN1CalcTable'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 审计年度（TB 兜底取数用） */
  year?: number
}>()

// ─── 复核入口 ────────────────────────────────────────────────────────────────
// 改用 GtReviewTrigger（自带蓝/红点，内部 inject openReviewDialog）

// ─── Composables ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const dualMode = useN1DualMode({ wpId: wpIdRef })
const formData = useN1FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  year: computed(() => props.year || undefined),
})
const crossSheet = useN1CrossSheet(formData.allResponses)
const importExport = useN1ImportExport({ wpId: wpIdRef, projectId: projectIdRef })

const calcTable = useN1CalcTable({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: formData.allResponses,
  formData,
})

// ─── State ───────────────────────────────────────────────────────────────────

const writebackAssetLoading = ref(false)
const writebackLiabilityLoading = ref(false)
const aiLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── Computed: 双部分分组 ────────────────────────────────────────────────────

/** 资产部分行：可抵扣暂时性差异 > 0 的行 */
const assetRows = computed<N1CalcTableComputed[]>(() =>
  calcTable.rows.value.filter(r => r.deductibleDiff > 0)
)

/** 负债部分行：应纳税暂时性差异 > 0 的行 */
const liabilityRows = computed<N1CalcTableComputed[]>(() =>
  calcTable.rows.value.filter(r => r.taxableDiff > 0)
)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

/**
 * N1-5「回填 → N1-4/N1-1」发出的事件消费者。
 *
 * 🔴 此前 `loss-check:recognizable-updated` 无任何消费者（死 emit）：
 *    N1-5 点回填后 N1-4 侧的可确认额提示不刷新，除非手工重进本 tab。
 *    这里重新加载 checklist_responses 使 crossSheet.lossCheckToCalcTable 立即更新。
 */
function onLossRecognizableUpdated(): void {
  void formData.loadData()
}

onMounted(async () => {
  await formData.loadData()
  // 恢复审计说明/结论
  const notes = formData.getField('4', 'audit-notes')
  if (notes) auditNotes.value = String(notes)
  const conclusion = formData.getField('4', 'audit-conclusion')
  if (conclusion) auditConclusion.value = String(conclusion)
  eventBus.on('loss-check:recognizable-updated' as any, onLossRecognizableUpdated)
})

onUnmounted(() => {
  eventBus.off('loss-check:recognizable-updated' as any, onLossRecognizableUpdated)
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | undefined): string {
  if (val == null || isNaN(val) || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | undefined): string {
  if (val == null || isNaN(val) || val === 0) return '—'
  return (val * 100).toFixed(0) + '%'
}

/**
 * 确认条件判断：检查未来应纳税所得额是否充足
 * 规则：可抵扣差异 > 0 时，默认"满足"（实际由N1-5亏损检查+审计人员判断确认）
 * 若差异 > N1-5可确认总额且>0，标记为"需关注"
 */
function getConfirmClass(row: N1CalcTableComputed): string {
  if (row.deductibleDiff <= 0) return 'text-muted'
  const lossTotal = crossSheet.lossCheckToCalcTable.value.total
  // 若可确认总额>0且差异大于该值，需关注
  if (lossTotal > 0 && row.deferredTaxAsset > lossTotal) {
    return 'confirm-warning'
  }
  return 'confirm-ok'
}

function getConfirmLabel(row: N1CalcTableComputed): string {
  if (row.deductibleDiff <= 0) return '—'
  const lossTotal = crossSheet.lossCheckToCalcTable.value.total
  if (lossTotal > 0 && row.deferredTaxAsset > lossTotal) {
    return '需关注'
  }
  return '满足'
}

// ─── 合计行方法 ──────────────────────────────────────────────────────────────

function getAssetSummaries({ columns }: any) {
  const sums: string[] = []
  const rows = assetRows.value
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '资产合计'; return }
    const prop = col.property
    if (!prop) { sums[i] = ''; return }
    const numericProps = ['bookValue', 'taxBase', 'deductibleDiff', 'deferredTaxAsset', 'assetBookBalance', 'assetDiff']
    if (numericProps.includes(prop)) {
      const total = rows.reduce((sum, r) => sum + ((r as any)[prop] || 0), 0)
      sums[i] = fmtAmt(total)
    } else {
      sums[i] = ''
    }
  })
  return sums
}

function getLiabilitySummaries({ columns }: any) {
  const sums: string[] = []
  const rows = liabilityRows.value
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '负债合计'; return }
    const prop = col.property
    if (!prop) { sums[i] = ''; return }
    const numericProps = ['bookValue', 'taxBase', 'taxableDiff', 'deferredTaxLiability', 'liabilityBookBalance', 'liabilityDiff']
    if (numericProps.includes(prop)) {
      const total = rows.reduce((sum, r) => sum + ((r as any)[prop] || 0), 0)
      sums[i] = fmtAmt(total)
    } else {
      sums[i] = ''
    }
  })
  return sums
}

// ─── 动态行新增 ──────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入测算项目名称', '新增测算项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) calcTable.addRow(value.trim())
  } catch { /* cancelled */ }
}

// ─── 从N1-2刷新 ─────────────────────────────────────────────────────────────

function handleRefreshFromDetail() {
  const stored = formData.allResponses.value.get('N1-2-detail-rows')
  if (stored?.conclusion) {
    try {
      const items = JSON.parse(stored.conclusion) as Array<{ itemName: string; category: string }>
      calcTable.refreshFromDetail(items)
      ElMessage.success(`已从N1-2刷新，当前共 ${calcTable.rows.value.length} 项`)
    } catch {
      ElMessage.warning('N1-2数据解析失败，请手动新增')
    }
  } else {
    ElMessage.info('N1-2暂无明细数据，请先编制明细表')
  }
}

// ─── 从 N1-5 带入可弥补亏损行 ────────────────────────────────────────────────

const N1_LOSS_ITEM_NAME = '可用以后年度税前利润弥补的亏损'

/**
 * 从 N1-5 亏损检查表带入「可弥补亏损」测算行（新模型 N1-5-rows）。
 *
 * 口径：计税基础 = Σ effectiveRecognized（非届满行），账面价值 = 0
 *      → 可抵扣暂时性差异即该金额；税率取 N1-5 加权税率。
 * 🔴 仅填空不覆盖：已有该行且已录金额时确认后覆盖。
 * 🔴 N1-5-total-recognizable 继续写入且与 Property 4 一致。
 *
 * Spec: n1-loss-check-source-alignment Task 6.1 / Req 5.1, 5.2
 */
async function handlePullFromLossCheck() {
  // 优先读新键 N1-5-rows（新模型 useN1LossCheck）
  const newKeyEntry = formData.allResponses.value.get('N1-5-rows')
  let v2Rows: any[] = []
  if (newKeyEntry) {
    const raw = newKeyEntry?.conclusion ?? newKeyEntry
    if (typeof raw === 'string' && raw) {
      try { v2Rows = JSON.parse(raw) } catch { v2Rows = [] }
    }
    if (!Array.isArray(v2Rows)) v2Rows = []
  }

  if (v2Rows.length > 0) {
    // 新模型取数：按源模板结构派生（同 useN1LossCheck 公式）
    const year = props.year || new Date().getFullYear()
    let base = 0
    let asset = 0
    for (const row of v2Rows) {
      const expiryYear = Number(row.expiryYear) || 0
      const isExpired = expiryYear < year
      if (isExpired) continue
      const bookAmount = Number(row.bookAmount) || 0
      const auditAdjustment = Number(row.auditAdjustment) || 0
      const auditedAmount = bookAmount + auditAdjustment
      const recognizedAmount = Number(row.recognizedAmount) || 0
      const effectiveRecognized = recognizedAmount // non-expired
      const taxRate = Number(row.taxRate) || 0.25
      base += effectiveRecognized
      asset += effectiveRecognized * taxRate
    }
    base = parseFloat(base.toFixed(2))
    asset = parseFloat(asset.toFixed(2))
    if (base <= 0) {
      ElMessage.warning('N1-5 无可确认的可弥补亏损（均已届满或确认额为 0）')
      return
    }
    const rate = base > 0 ? parseFloat((asset / base).toFixed(4)) : 0.25
    await _applyLossToCalcRow(base, rate)
    return
  }

  // 回退旧键 N1-5-loss-rows（legacy 兼容）
  const rows = deriveDisclosureLossRows(
    formData.allResponses.value,
    props.year || new Date().getFullYear(),
  )
  if (rows.length === 0) {
    ElMessage.warning('N1-5 亏损检查表暂无数据，请先编制 N1-5')
    return
  }
  let base = 0
  let asset = 0
  for (const r of rows) {
    if (r.isExpired) continue
    base += Math.min(r.unrecovered, r.futureTaxableIncome)
    asset += r.recognizableAsset
  }
  base = parseFloat(base.toFixed(2))
  if (base <= 0) {
    ElMessage.warning('N1-5 无可确认的可弥补亏损（均已届满或预计应纳税所得额为 0）')
    return
  }
  const rate = asset > 0 ? parseFloat((asset / base).toFixed(4)) : 0.25
  await _applyLossToCalcRow(base, rate)
}

/** 应用可弥补亏损到 N1-4 测算行（仅填空不覆盖，确认后覆盖） */
async function _applyLossToCalcRow(base: number, rate: number) {
  const idx = calcTable.rows.value.findIndex((r) => r.itemName === N1_LOSS_ITEM_NAME)
  if (idx >= 0) {
    const existing = calcTable.rows.value[idx]
    if (existing.taxBase !== 0 || existing.bookValue !== 0) {
      try {
        await ElMessageBox.confirm(
          `「${N1_LOSS_ITEM_NAME}」已录入数值（计税基础 ${fmtAmt(existing.taxBase)}），是否用 N1-5 结果覆盖？`,
          '覆盖确认',
          { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' },
        )
      } catch {
        return
      }
    }
    calcTable.updateRow(idx, 'bookValue', 0)
    calcTable.updateRow(idx, 'taxBase', base)
    calcTable.updateRow(idx, 'taxRate', rate)
  } else {
    calcTable.addRow(N1_LOSS_ITEM_NAME)
    const newIdx = calcTable.rows.value.length - 1
    calcTable.updateRow(newIdx, 'bookValue', 0)
    calcTable.updateRow(newIdx, 'taxBase', base)
    calcTable.updateRow(newIdx, 'taxRate', rate)
  }
  ElMessage.success(`已从 N1-5 带入可弥补亏损 ${fmtAmt(base)}（税率 ${fmtPercent(rate)}）`)
}

// ─── 差异推送 N1-3 建议调整分录 ──────────────────────────────────────────────

interface N1AdjustmentEntryLike {
  id: string
  type: 'AJE' | 'RJE'
  description: string
  category: string
  reportItem: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  refIndex: string
  remark: string
}

const DIFF_PUSH_PREFIX = '【N1-4测算差异】'

/** 应确认额 ≠ 账面余额的行 → N1-3 建议 AJE（去重追加，不覆盖已有分录） */
async function handlePushDiffToAdjustment() {
  const diffRows = calcTable.rows.value.filter((r) => Math.abs(r.assetDiff) > 0.01)
  if (diffRows.length === 0) {
    ElMessage.info('递延所得税资产应确认额与账面余额一致，无需生成调整分录')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将按 ${diffRows.length} 个差异项目生成 N1-3 建议调整分录（借/贷方向按差异正负确定），同名事项不重复追加。是否继续？`,
      '推送差异至 N1-3',
      { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  // 读取 N1-3 现有分录（键与 N1TabAdjustment 一致）
  let entries: N1AdjustmentEntryLike[] = []
  const stored = formData.allResponses.value.get('N1-3-entries')
  if (stored?.conclusion) {
    try {
      const parsed = JSON.parse(stored.conclusion)
      if (Array.isArray(parsed)) entries = parsed
    } catch { /* 解析失败按空处理，不覆盖原始串 */ }
  }
  const existingDesc = new Set(entries.map((e) => String(e.description ?? '')))

  let added = 0
  for (const r of diffRows) {
    const description = `${DIFF_PUSH_PREFIX}${r.itemName}`
    if (existingDesc.has(description)) continue
    const diff = parseFloat(r.assetDiff.toFixed(2))
    entries.push({
      id: `adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type: 'AJE',
      description,
      category: '账项调整',
      reportItem: '递延所得税资产',
      accountName: '递延所得税资产',
      noteItem: '递延所得税资产',
      // 应确认 > 账面 → 补提（借递延所得税资产）；反之冲减（贷方）
      debitAmount: diff > 0 ? diff : 0,
      creditAmount: diff < 0 ? Math.abs(diff) : 0,
      refIndex: 'N1-4',
      remark: `测算应确认 ${fmtAmt(r.deferredTaxAsset)} − 账面 ${fmtAmt(r.assetBookBalance)}`,
    })
    existingDesc.add(description)
    added += 1
  }

  if (added === 0) {
    ElMessage.info('差异项目均已推送过，未新增分录')
    return
  }
  await formData.saveField('N1-3-entries', { conclusion: JSON.stringify(entries) })
  ElMessage.success(`已推送 ${added} 条建议调整分录至 N1-3（需在 N1-3 复核对方科目并配平）`)
}

// ─── 回填N1-1（递延税资产合计） ──────────────────────────────────────────────

async function handleWritebackAsset() {
  writebackAssetLoading.value = true
  try {
    const assetTotal = calcTable.totals.value.deferredTaxAsset
    // 保存到 allResponses 供 N1-1 crossSheet 读取
    await formData.saveField('N1-4-total-deferred-tax-asset', {
      remark: String(assetTotal),
    })
    // 发布事件通知
    eventBus.emit('deferred-tax:asset-updated', {
      accountCode: '1811',
      auditedAmount: assetTotal,
      wpCode: 'N1',
      source: 'N1-4',
      timestamp: Date.now(),
    })
    ElMessage.success(`递延税资产合计 ${fmtAmt(assetTotal)} 已回填N1-1`)
  } catch (err: any) {
    ElMessage.error(`回填失败：${err?.message || '未知错误'}`)
  } finally {
    writebackAssetLoading.value = false
  }
}

// ─── 联动N3（递延税负债合计） ────────────────────────────────────────────────

async function handlePublishToN3() {
  writebackLiabilityLoading.value = true
  try {
    const liabilityTotal = calcTable.totals.value.deferredTaxLiability
    // 保存到 allResponses
    await formData.saveField('N1-4-total-deferred-tax-liability', {
      remark: String(liabilityTotal),
    })
    // 发布EventBus通知N3底稿
    eventBus.emit('deferred-tax:liability-from-n1', {
      liabilityTotal,
      wpCode: 'N1',
      source: 'N1-4',
      timestamp: Date.now(),
    })
    ElMessage.success(`递延税负债合计 ${fmtAmt(liabilityTotal)} 已联动N3`)
  } catch (err: any) {
    ElMessage.error(`联动失败：${err?.message || '未知错误'}`)
  } finally {
    writebackLiabilityLoading.value = false
  }
}

// ─── 导入导出命令 ────────────────────────────────────────────────────────────

async function handleImportExportCmd(cmd: string) {
  // 🔴 必须显式传 'N1-4'：后端 sheet 默认值是 N1-2，漏传会导出/覆盖 N1-2 明细表数据
  switch (cmd) {
    case 'export-template':
      await importExport.exportTemplate('N1-4')
      break
    case 'export-data':
      await importExport.exportData('N1-4')
      break
    case 'import-data': {
      // 创建隐藏的文件输入触发文件选择
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          await importExport.importData(file, 'N1-4')
          // 导入后重新加载
          await formData.loadData()
        }
      }
      input.click()
      break
    }
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

function handleNotesSave() {
  formData.setField('4', 'audit-notes', auditNotes.value)
}

function handleConclusionSave() {
  formData.setField('4', 'audit-conclusion', auditConclusion.value)
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

/**
 * AI 辅助（真回填）。context 值全部转字符串（后端 dict[str,str]，数字会 422）。
 */
async function handleAI(section: string) {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const t = calcTable.totals.value
    const text = await generateN1Text({
      wpId: props.wpId,
      section: `n1-calc-table-${section}`,
      prompt:
        section === 'conclusion'
          ? '请基于递延所得税资产（负债）测算结果，撰写审计结论（应确认额与账面额的差异是否需调整、抵销与列示是否恰当）。'
          : '请基于账面价值与计税基础的测算数据，给出审计分析建议（暂时性差异性质判断、税率适用、应确认与账面差异原因）。',
      context: {
        可抵扣暂时性差异合计: String(t.deductibleDiff),
        应纳税暂时性差异合计: String(t.taxableDiff),
        应确认递延税资产合计: String(t.deferredTaxAsset),
        应确认递延税负债合计: String(t.deferredTaxLiability),
        递延税资产账面合计: String(t.assetBookBalance),
        递延税负债账面合计: String(t.liabilityBookBalance),
        资产差异合计: String(t.assetDiff),
        负债差异合计: String(t.liabilityDiff),
      },
      existingContent: section === 'conclusion' ? auditConclusion.value : auditNotes.value,
    })
    if (!text) return
    if (section === 'conclusion') {
      auditConclusion.value = text
      handleConclusionSave()
      ElMessage.success('AI 已生成审计结论')
    } else {
      auditNotes.value = text
      handleNotesSave()
      ElMessage.success('AI 已生成审计说明')
    }
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.n1-tab-calc-table {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 双模式切换 ─── */
.n1-mode-bar {
  margin-bottom: 12px;
}

/* ─── 蓝色渐变引导区 ─── */
.n1-guidance-banner {
  padding: 14px 20px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: 1px solid #90caf9;
  border-radius: 8px;
}

.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}

.guidance-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #1565c0;
}

.step-num {
  font-weight: 700;
  font-size: 14px;
  color: #0d47a1;
}

.step-text {
  color: #1565c0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.n1-methodology-ctx {
  padding: 12px 16px;
  margin-bottom: 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-left: 4px solid #d97706;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #92400e;
  line-height: 1.7;
}

.n1-methodology-ctx p {
  margin: 0 0 4px;
}

.n1-methodology-ctx p:last-child {
  margin-bottom: 0;
}

/* ─── 资产类科目公式提示 ─── */
.n1-asset-formula-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 1px solid #81c784;
  border-left: 4px solid #43a047;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #1b5e20;
}

.n1-asset-formula-badge .el-icon {
  font-size: 16px;
  color: #43a047;
  flex-shrink: 0;
}

/* ─── Section Header ─── */
.n1-section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 动态行操作 ─── */
.n1-row-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.row-count {
  font-size: 12px;
  color: #909399;
}

/* ─── 双部分标签 ─── */
.dual-part-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  margin: 12px 0 8px;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}

.asset-part-label {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
  color: #2e7d32;
}

.liability-part-label {
  background: #f3e5f5;
  border: 1px solid #ce93d8;
  color: #6a1b9a;
}

.edit-part-label {
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  color: #606266;
}

.part-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.asset-dot { background: #43a047; }
.liability-dot { background: #8e24aa; }
.edit-dot { background: #909399; }

/* ─── 表格通用 ─── */
.calc-table {
  margin-bottom: 0;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-input-number .el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

.cell-input {
  width: 100%;
}

.item-name-cell {
  font-weight: 500;
  color: #303133;
}

.cell-value {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

/* ─── 资产/负债表格区域背景色 ─── */
:deep(.asset-table .el-table__body tr td) {
  background-color: #f1f8e9 !important;
}

:deep(.liability-table .el-table__body tr td) {
  background-color: #fce4ec !important;
}

/* ─── 公式列样式（虚线下划线+cursor:help） ─── */
.formula-col {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
  font-weight: 600;
}

.formula-value {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
  padding-bottom: 1px;
}

.asset-value {
  color: #2e7d32 !important;
  font-weight: 700;
}

.liability-value {
  color: #6a1b9a !important;
  font-weight: 700;
}

.text-danger {
  color: #f56c6c !important;
}

.text-success {
  color: #67c23a !important;
}

.text-muted {
  color: #c0c4cc;
}

/* ─── 合计 + 回填操作区 ─── */
.n1-calc-totals {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
}

.total-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-radius: 8px;
}

.total-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.total-asset {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
}

.total-liability {
  background: #f3e5f5;
  border: 1px solid #ce93d8;
}

.total-label {
  font-size: 12px;
  color: #606266;
  font-weight: 500;
}

.total-value {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}

/* ─── 交叉验证区 ─── */
.n1-cross-validation {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.cv-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
  margin-bottom: 10px;
}

.cv-indicators {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.cv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}

.cv-match {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
}

.cv-diff {
  background: #fef0f0;
  border: 1px solid #fab6b6;
}

.cv-info {
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
}

.cv-label {
  color: #606266;
  font-size: 12px;
}

.cv-badge {
  font-weight: 600;
  font-size: 12px;
}

.cv-badge-ok { color: #43a047; }
.cv-badge-err { color: #f56c6c; }
.cv-badge-info { color: #409eff; }

/* ─── 确认条件判断区 ─── */
.n1-confirm-condition {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.confirm-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
  margin-bottom: 10px;
}

.confirm-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.confirm-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  border-radius: 4px;
  background: #fff;
  border: 1px solid #ebeef5;
  font-size: 12px;
}

.confirm-name {
  color: #606266;
}

.confirm-ok {
  color: #43a047;
  font-weight: 600;
  padding: 2px 8px;
  background: #e8f5e9;
  border-radius: 4px;
}

.confirm-warning {
  color: #e65100;
  font-weight: 600;
  padding: 2px 8px;
  background: #fff3e0;
  border-radius: 4px;
}

.confirm-empty {
  font-size: 12px;
  color: #909399;
  font-style: italic;
}

/* ─── N3对应关系区 ─── */
.n3-correspondence-section {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
}

.n3-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #0369a1;
  margin-bottom: 10px;
}

.n3-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.n3-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.n3-label {
  color: #64748b;
}

.n3-value {
  font-weight: 500;
  color: #303133;
}

/* ─── 审计说明卡片 ─── */
.n1-conclusion-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-group {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

/* ─── 编制提示折叠 ─── */
.n1-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
