<template>
  <div class="i3-tab-impairment-test">
    <!-- 蓝色渐变引导区 -->
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step">
          <span class="step-num">①</span>
          <span>定性分析内外环境变化对商誉的影响</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">②</span>
          <span>粗化账面：A(资产组)+B1(母公司商誉)+B2(少数股东商誉)</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">③</span>
          <span>可收回金额=MAX(公允减处置费①, 使用价值②)，详见 I3-7</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">④</span>
          <span>先冲全额商誉→再按比例分摊；合并仅确认母公司份额</span>
        </div>
      </div>
    </div>

    <!-- 琥珀色方法论 -->
    <div class="methodology-block">
      <p>
        <strong>CAS8 商誉减值测试要点：</strong>
        无论是否存在减值迹象，商誉应至少于每年年末进行减值测试。
        含商誉的资产组账面价值应包含归属于少数股东的商誉（B2 粗化），再与可收回金额比较；
        减值损失先抵减商誉账面价值（含未确认少数股东商誉），再按比例抵减其他资产；
        合并报表仅确认归属于母公司的商誉减值。商誉减值一经确认不得转回。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确定商誉是否发生减值，以及减值金额的计量是否适当。按资产组(CGU)粗化含少数股东商誉的账面价值，与可收回金额比较；验证分摊及合并确认金额；商誉减值不可转回（CAS8）。"
    />

    <!-- 一、定性分析 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（一）定性分析</span>
        </div>
      </template>
      <p class="section-hint">说明被审计单位内外部环境变化对商誉的影响（如行业政策、业绩承诺、核心人员、竞争格局等）。</p>
      <el-input
        v-model="qualitativeAnalysis"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="记录定性分析结论及主要依据…"
        :disabled="isReadonly"
        @blur="saveMeta('I3-6-qualitative', qualitativeAnalysis)"
      />
      <div class="indicator-grid">
        <el-checkbox-group v-model="impairmentIndicators" :disabled="isReadonly" @change="saveIndicators">
          <el-checkbox v-for="ind in INDICATOR_OPTIONS" :key="ind" :label="ind" :value="ind">
            {{ ind }}
          </el-checkbox>
        </el-checkbox-group>
      </div>
    </el-card>

    <!-- 二、减值测试主表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（二）商誉减值测试 — I3-6（CGU粗化与分摊）</span>
          <div class="section-header-actions">
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportImport">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onImportFileSelected" />
            <el-button size="small" circle @click="openReview('I3-6')">💬</el-button>
          </div>
        </div>
      </template>

      <div class="tab-toolbar">
        <div class="toolbar-left">
          <span class="table-hint">账面价值(1)=A+B1+B2；可收回(2)=MAX(①,②)；减值准备=MAX((1)-(2),0)</span>
        </div>
        <div class="toolbar-right">
          <GtIndexChip value="wp:I3-6" :context-project-id="projectId" />
          <el-tag size="small" type="info">共 {{ cguRows.length }} 行</el-tag>
        </div>
      </div>

      <el-table
        :data="cguRows"
        border
        stripe
        size="small"
        class="impairment-table"
        :row-class-name="getRowClassName"
        row-key="rowId"
      >
        <el-table-column type="expand" width="30">
          <template #default="{ row, $index }">
            <div class="expand-section">
              <div class="expand-title">
                <span>减值损失分摊明细 — {{ row.cguName }}</span>
                <el-button v-if="!isReadonly" size="small" @click="handleAddOtherAsset($index)">
                  + 新增其他资产
                </el-button>
              </div>
              <div class="alloc-summary">
                <span>第一分摊（冲全额商誉 B1+B2）：<strong>{{ fmtAmt(row.goodwillImpairment) }}</strong></span>
                <span>第二分摊（其他资产）：<strong>{{ fmtAmt(calcOtherImpairmentTotal(row)) }}</strong></span>
                <span class="consol-hl">
                  合并报表确认商誉减值：<strong>{{ fmtAmt(row.consolidatedGwImpairment) }}</strong>
                  <el-tooltip content="= 商誉分摊减值 × B1/(B1+B2)；全资子公司 B2=0 时等于第一分摊全额">
                    <span class="help-dot">?</span>
                  </el-tooltip>
                </span>
              </div>
              <el-table :data="buildAllocTable(row)" border size="small" class="other-assets-table">
                <el-table-column type="index" label="#" width="40" align="center" />
                <el-table-column label="资产类别" min-width="120" prop="name">
                  <template #default="{ row: asset, $index: assetIdx }">
                    <template v-if="asset.isGoodwill">
                      <strong>商誉（B1+B2）</strong>
                    </template>
                    <el-input
                      v-else-if="!isReadonly"
                      :model-value="asset.name"
                      size="small"
                      @blur="handleUpdateOtherAsset($index, assetIdx - 1, 'name', ($event.target as HTMLInputElement).value)"
                    />
                    <span v-else>{{ asset.name || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="账面价值" min-width="110" align="right">
                  <template #default="{ row: asset, $index: assetIdx }">
                    <span v-if="asset.isGoodwill" class="amt-cell">{{ fmtAmt(asset.bookValue) }}</span>
                    <el-input-number
                      v-else-if="!isReadonly"
                      :model-value="asset.bookValue"
                      :controls="false"
                      size="small"
                      class="amt-input"
                      @change="handleUpdateOtherAsset($index, assetIdx - 1, 'bookValue', $event)"
                    />
                    <span v-else class="amt-cell">{{ fmtAmt(asset.bookValue) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="可收回金额" min-width="110" align="right">
                  <template #default="{ row: asset, $index: assetIdx }">
                    <span v-if="asset.isGoodwill">—</span>
                    <el-input-number
                      v-else-if="!isReadonly"
                      :model-value="asset.recoverableAmount"
                      :controls="false"
                      size="small"
                      class="amt-input"
                      placeholder="可选"
                      @change="handleUpdateOtherAsset($index, assetIdx - 1, 'recoverableAmount', $event)"
                    />
                    <span v-else class="amt-cell">{{ fmtAmt(asset.recoverableAmount) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="第一分摊" min-width="100" align="right">
                  <template #default="{ row: asset }">
                    <span class="formula-cell">{{ fmtAmt(asset.allocFirst) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="第二分摊" min-width="100" align="right">
                  <template #default="{ row: asset }">
                    <span class="formula-cell" :class="{ 'impaired-amount': asset.belowRecoverable }">
                      {{ fmtAmt(asset.allocSecond) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="分摊后账面" min-width="110" align="right">
                  <template #default="{ row: asset }">
                    <span class="formula-cell">{{ fmtAmt(asset.afterBook) }}</span>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row: asset, $index: assetIdx }">
                    <el-button
                      v-if="!asset.isGoodwill"
                      size="small"
                      type="danger"
                      link
                      @click="handleRemoveOtherAsset($index, assetIdx - 1)"
                    >✕</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <p class="alloc-floor-hint">第二分摊受 CAS8 §23 约束：单项资产抵减后不得低于其可收回金额（未填可收回时上限=账面）。</p>
            </div>
          </template>
        </el-table-column>

        <el-table-column type="index" label="序号" width="50" align="center" />

        <el-table-column prop="cguName" label="项目名称（资产组）" min-width="150" fixed>
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly && cguNameOptions.length"
              :model-value="row.cguName"
              size="small"
              filterable
              allow-create
              default-first-option
              style="width:100%"
              @change="(v: string) => handleUpdateCguName($index, v)"
            >
              <el-option v-for="n in cguNameOptions" :key="n" :label="n" :value="n" />
            </el-select>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.cguName"
              size="small"
              @blur="handleUpdateCguName($index, ($event.target as HTMLInputElement).value)"
            />
            <span v-else>{{ row.cguName || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 账面价值(1) 分组 -->
        <el-table-column label="账面价值(1)" align="center">
          <el-table-column label="A 资产组账面" min-width="120" align="right">
            <template #header>
              <span class="formula-header" title="合并报表层面对应资产组账面价值（不含商誉）">A 资产组账面</span>
            </template>
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.assetGroupCarrying"
                :controls="false"
                size="small"
                class="amt-input"
                @change="handleUpdateAssetGroup($index, $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.assetGroupCarrying) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="B1 母公司商誉" min-width="120" align="right">
            <template #header>
              <span class="formula-header" title="分摊的商誉账面价值（母公司份额）">B1 母公司商誉</span>
            </template>
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.goodwillB1"
                :controls="false"
                size="small"
                class="amt-input"
                @change="handleUpdateGoodwillB1($index, $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.goodwillB1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="B2 少数股东商誉" min-width="130" align="right">
            <template #header>
              <span class="formula-header" title="未确认的少数股东商誉（粗化用）">B2 少数股东商誉</span>
            </template>
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.minorityB2"
                :controls="false"
                size="small"
                class="amt-input"
                @change="handleUpdateMinorityB2($index, $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.minorityB2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计 A+B1+B2" min-width="120" align="right">
            <template #header>
              <span class="formula-header" title="粗化后账面价值 = A+B1+B2">合计(1)</span>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.cguBookValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 可收回金额(2) -->
        <el-table-column label="可收回金额(2)" align="center">
          <el-table-column label="①公允−处置费" min-width="120" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.fairValueLessCost"
                :controls="false"
                size="small"
                class="amt-input"
                placeholder="可选"
                @change="handleUpdateFv($index, $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.fairValueLessCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="②使用价值" min-width="120" align="right">
            <template #header>
              <span class="formula-header" title="来源：I3-7 DCF 或手工录入">②使用价值</span>
            </template>
            <template #default="{ row, $index }">
              <div class="recoverable-cell">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.valueInUse"
                  :controls="false"
                  size="small"
                  class="amt-input"
                  placeholder="I3-7"
                  @change="handleUpdateViu($index, $event)"
                />
                <span v-else class="amt-cell">{{ fmtAmt(row.valueInUse) }}</span>
                <GtIndexChip value="I3-7" label="DCF" @click="navigateToSheet('I3-7')" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="可收回(孰高)" min-width="110" align="right">
            <template #header>
              <span class="formula-header" title="MAX(①,②)；若均未填则用手工可收回金额">可收回(2)</span>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="减值准备" min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="= MAX((1)-(2), 0)">计提减值</span>
          </template>
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'impaired-amount': row.impairmentAmount > 0 }]"
            >
              {{ fmtAmt(row.impairmentAmount) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="商誉分摊" min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="第一分摊：MIN(减值, B1+B2)">商誉分摊</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.goodwillImpairment) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="合并确认" min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="合并报表确认=商誉分摊×B1/(B1+B2)">合并确认</span>
          </template>
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'impaired-amount': row.consolidatedGwImpairment > 0 }]"
            >
              {{ fmtAmt(row.consolidatedGwImpairment) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="减值原因及说明" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.impairmentReason"
              size="small"
              placeholder="原因…"
              @blur="handleUpdateReason($index, ($event.target as HTMLInputElement).value)"
            />
            <span v-else>{{ row.impairmentReason || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="handleRemoveCguRow($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-row">
        <span class="summary-label">合计</span>
        <span class="summary-item">A: <strong>{{ fmtAmt(cguSummary.totalAssetGroupCarrying) }}</strong></span>
        <span class="summary-item">B1: <strong>{{ fmtAmt(cguSummary.totalGoodwillB1) }}</strong></span>
        <span class="summary-item">B2: <strong>{{ fmtAmt(cguSummary.totalMinorityB2) }}</strong></span>
        <span class="summary-item">粗化账面: <strong>{{ fmtAmt(cguSummary.totalCguBookValue) }}</strong></span>
        <span class="summary-item">可收回: <strong>{{ fmtAmt(cguSummary.totalRecoverable) }}</strong></span>
        <span class="summary-item" :class="{ 'impaired-amount': cguSummary.totalImpairment > 0 }">
          减值准备: <strong>{{ fmtAmt(cguSummary.totalImpairment) }}</strong>
        </span>
        <span class="summary-item consol-hl">
          合并确认商誉减值: <strong>{{ fmtAmt(cguSummary.totalConsolidatedGwImpairment) }}</strong>
        </span>
      </div>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddCguRow">+ 新增资产组</el-button>
      </div>
    </el-card>

    <el-alert
      v-if="totalGoodwillImpairment > 0"
      type="warning"
      :closable="false"
      show-icon
      class="reversal-warning"
    >
      <template #title>
        商誉减值不可转回！本期合并报表应确认商誉减值
        <strong>{{ fmtAmt(totalGoodwillImpairment) }}</strong>
        元（已剔除少数股东份额），以后期间不得转回。请同步核对 I3-1 / K11。
      </template>
    </el-alert>

    <!-- 三、可收回金额测试索引 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（三）商誉的可收回金额测试</span>
        </div>
      </template>
      <p class="section-hint">
        详见
        <GtIndexChip value="I3-7" label="可收回金额测试 I3-7" @click="navigateToSheet('I3-7')" />
        ；亦可对照管理层工作底稿「K3-5-3 商誉减值准备测试表—可收回金额」。
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          class="ml-8"
          data-testid="i3-6-sync-from-i37"
          @click="handleSyncFromI37"
        >
          从 I3-7 同步可收回金额
        </el-button>
        <el-tag v-if="i37SyncedCount > 0" size="small" type="success" class="ml-8">
          已联动 {{ i37SyncedCount }} 个 CGU
        </el-tag>
      </p>
    </el-card>

    <!-- 四、利用专家的工作 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（四）利用专家的工作</span>
        </div>
      </template>
      <el-table :data="expertRows" border size="small" class="expert-table">
        <el-table-column type="index" label="#" width="40" align="center" />
        <el-table-column label="事项" min-width="280" prop="label" />
        <el-table-column label="是否利用" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-model="row.used"
              size="small"
              :disabled="isReadonly"
              style="width: 90px"
              @change="saveExpert"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
              <el-option label="不适用" value="N/A" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip :value="row.index" @click="navigateToSheet(row.index)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <el-input
              v-model="row.remark"
              size="small"
              :disabled="isReadonly"
              placeholder="专家姓名/报告日等"
              @blur="saveExpert"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 重大风险提示 -->
    <el-card shadow="never" class="block-card risk-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">重大错报风险联动</span>
        </div>
      </template>
      <el-checkbox
        v-model="isSignificantRisk"
        :disabled="isReadonly"
        @change="saveMeta('I3-6-significant-risk', isSignificantRisk ? 'Y' : 'N')"
      >
        商誉减值被认定为重大错报风险（特别风险）
      </el-checkbox>
      <p class="section-hint" v-if="isSignificantRisk">
        应了解被审计单位与商誉减值相关的内部控制，并评价控制设计与执行。交叉索引：
        <GtIndexChip value="B23-8" />
        <GtIndexChip value="C9" />
        <GtIndexChip value="B21" />
        <GtIndexChip value="C25" />
      </p>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>三、审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 4 }"
        placeholder="记录减值测试执行过程（资产组认定、粗化方法、可收回金额来源、分摊与合并确认等）"
        :disabled="isReadonly"
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计结论</span>
          <el-select
            v-if="!isReadonly"
            size="small"
            placeholder="插入结论模板"
            style="width: 220px"
            @change="applyConclusionTemplate"
          >
            <el-option
              v-for="t in CONCLUSION_TEMPLATES"
              :key="t.key"
              :label="t.label"
              :value="t.key"
            />
          </el-select>
        </div>
      </template>
      <el-input
        v-model="auditConclusionText"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="商誉减值测试的审计结论…"
        :disabled="isReadonly"
        @blur="handleSaveAuditConclusion"
      />
    </el-card>

    <!-- 编制说明 -->
    <details class="edit-tips" open>
      <summary>编制说明（CAS8 / 监管提示）</summary>
      <ol class="prep-list">
        <li>无论是否存在减值迹象，「商誉」应至少于每年年末进行减值测试。</li>
        <li>
          减值迹象包括但不限于：
          <ul>
            <li>（1）经济、技术或法律环境发生重大不利变化；</li>
            <li>（2）监管部门负面行动或评价；</li>
            <li>（3）出现未预计到的竞争；</li>
            <li>（4）关键管理人员流失；</li>
            <li>（5）主体或重要组成部分很可能被出售或处置；</li>
            <li>（6）重要资产组已进行可收回性测试；</li>
            <li>（7）子公司已确认商誉减值；</li>
            <li>（8）商誉所分摊资产组将被处置；</li>
            <li>（9）其他因素。</li>
          </ul>
        </li>
        <li>商誉应结合相关资产组或资产组组合进行测试，且不大于《企业会计准则第35号——分部报告》确定的报告分部。</li>
        <li>资产组是企业可以认定的最小资产组合，其现金流入基本独立于其他资产或资产组。</li>
        <li>总部资产与商誉本身不产生独立现金流，须识别相关资产组后分摊。</li>
        <li>分摊基础：企业合并协同效应；确认商誉的原因决定减值测试时的分摊基础。</li>
        <li>应区分商誉减值与并购业绩补偿；存在业绩补偿承诺不得替代减值测试。</li>
        <li>
          账面价值粗化：合计(1)=A+B1+B2；减值后合并报表仅确认归属于母公司的商誉减值
          （商誉分摊×B1/(B1+B2)）。
        </li>
        <li>
          监管提示（《会计监管风险提示第8号——商誉减值》）：现金流/经营利润持续恶化或显著低于形成商誉时的预期、行业产能过剩或政策剧变、技术壁垒低、核心团队重大不利变化、资质/特许权变更、市场投资回报率显著上升、经营地宏观风险等，应重点关注。
        </li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabImpairmentTest.vue — I3-6 商誉减值测试（对齐 Excel 底稿结构）
 *
 * 结构：定性分析 → A/B1/B2 粗化主表 → 可收回孰高 → 两步分摊与合并确认
 *       → 专家工作(S12/S13) → 重大风险联动 → 审计说明/结论 → 编制说明
 */
import { ref, inject, toRef, computed, watch, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI3Impairment, type CguRow } from '../../composables/useI3Impairment'
import { useI3CrossSheet } from '../../composables/useI3CrossSheet'
import { useI3ImportExport } from '../../composables/useI3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  recoverableByCgu,
  recoverableDetailByCgu,
  cguNameOptions,
} = useI3CrossSheet(allResponsesRef as any)

const {
  cguRows,
  cguSummary,
  totalGoodwillImpairment,
  impairedRowIds,
  addCguRow,
  removeCguRow,
  updateGoodwillB1,
  updateMinorityB2,
  updateAssetGroupCarrying,
  updateFairValueLessCost,
  updateValueInUse,
  updateImpairmentReason,
  updateCguName,
  addOtherAsset,
  removeOtherAsset,
  updateOtherAsset,
  syncRecoverableFromI3_7,
  exportCguRows,
} = useI3Impairment(
  toRef(props, 'wpId'),
  allResponsesRef as any,
  {
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
    recoverableByCgu,
    recoverableDetailByCgu,
  },
)

const CONCLUSION_KEY = 'I3-6-conclusion'
const AUDIT_CONCLUSION_KEY = 'I3-6-audit-conclusion'

const qualitativeAnalysis = ref('')
const impairmentIndicators = ref<string[]>([])
const isSignificantRisk = ref(false)
const auditConclusion = ref('')
const auditConclusionText = ref('')

const INDICATOR_OPTIONS = [
  '经济/技术/法律环境重大不利变化',
  '监管负面行动或评价',
  '未预计竞争',
  '关键管理人员流失',
  '主体或重要组成部分很可能处置',
  '重要资产组已做可收回性测试',
  '子公司已确认商誉减值',
  '商誉所分摊资产组将被处置',
  '业绩显著低于形成商誉时预期',
  '其他',
]

const CONCLUSION_TEMPLATES = [
  {
    key: 'no-impairment',
    label: '无需计提减值',
    text: '经对含商誉资产组进行减值测试（含少数股东商誉粗化），各资产组可收回金额均不低于其账面价值，无需计提商誉减值准备。商誉减值测试过程及结论恰当。',
  },
  {
    key: 'with-impairment',
    label: '需计提减值',
    text: '经对含商誉资产组进行减值测试（含少数股东商誉粗化），部分/全部资产组可收回金额低于账面价值，应按测试结果计提商誉减值准备，合并报表确认金额已按母公司份额调整。减值一经确认不得转回。',
  },
  {
    key: 'expert-relied',
    label: '利用专家工作后结论',
    text: '我们利用了专家工作（参见 S12/S13）复核可收回金额确定的关键假设与模型。在获取充分、适当的审计证据后，我们认为商誉减值测试结果在所有重大方面公允反映。',
  },
]

interface ExpertRow {
  key: string
  label: string
  index: string
  used: string
  remark: string
}

const expertRows = reactive<ExpertRow[]>([
  { key: 'cpa', label: '利用专家的工作（注册会计师的专家）', index: 'S12', used: 'N/A', remark: '' },
  { key: 'mgmt', label: '利用管理层的专家编制的信息作为审计证据', index: 'S13', used: 'N/A', remark: '' },
])

watch(
  () => props.allResponses,
  () => {
    const n = props.allResponses.get(CONCLUSION_KEY)
    if (n?.remark != null) auditConclusion.value = n.remark
    const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
    if (c?.remark != null) auditConclusionText.value = c.remark
    const q = props.allResponses.get('I3-6-qualitative')
    if (q?.remark != null) qualitativeAnalysis.value = q.remark
    const ind = props.allResponses.get('I3-6-indicators')
    if (ind?.remark) {
      try {
        const parsed = JSON.parse(ind.remark)
        if (Array.isArray(parsed)) impairmentIndicators.value = parsed
      } catch { /* ignore */ }
    }
    const risk = props.allResponses.get('I3-6-significant-risk')
    if (risk?.remark != null) isSignificantRisk.value = risk.remark === 'Y'
    const exp = props.allResponses.get('I3-6-expert')
    if (exp?.remark) {
      try {
        const parsed = JSON.parse(exp.remark)
        if (Array.isArray(parsed)) {
          parsed.forEach((p: any, i: number) => {
            if (expertRows[i]) {
              expertRows[i].used = p.used ?? expertRows[i].used
              expertRows[i].remark = p.remark ?? ''
            }
          })
        }
      } catch { /* ignore */ }
    }
  },
  { immediate: true },
)

function getRowClassName({ row }: { row: CguRow }): string {
  return impairedRowIds.value.has(row.rowId) ? 'row-impaired' : ''
}

function calcOtherImpairmentTotal(row: CguRow): number {
  if (!row.otherAllocations?.length) return 0
  return row.otherAllocations.reduce((sum, a) => sum + a.amount, 0)
}

function getOtherAllocationAmount(cguIndex: number, assetIndex: number): number {
  const row = cguRows.value[cguIndex]
  return row?.otherAllocations?.[assetIndex]?.amount ?? 0
}

/** 完整分摊表：商誉行 + 其他资产行 */
function buildAllocTable(row: CguRow) {
  const fullGw = (row.goodwillB1 || 0) + (row.minorityB2 || 0)
  const goodwillRow = {
    isGoodwill: true,
    name: '商誉',
    bookValue: fullGw,
    recoverableAmount: null as number | null,
    allocFirst: row.goodwillImpairment,
    allocSecond: 0,
    afterBook: Math.max(0, fullGw - row.goodwillImpairment),
    belowRecoverable: false,
  }
  const others = (row.otherAssets || []).map((a, i) => {
    const alloc = row.otherAllocations?.[i]?.amount ?? 0
    const after = Math.max(0, a.bookValue - alloc)
    const floor = a.recoverableAmount != null ? Math.max(0, a.recoverableAmount) : null
    return {
      isGoodwill: false,
      name: a.name,
      bookValue: a.bookValue,
      recoverableAmount: a.recoverableAmount ?? null,
      allocFirst: 0,
      allocSecond: alloc,
      afterBook: after,
      belowRecoverable: floor != null && after + 0.01 < floor,
    }
  })
  return [goodwillRow, ...others]
}

const i37SyncedCount = computed(() => {
  const map = recoverableDetailByCgu.value
  return cguRows.value.filter((r) => {
    const d = map[r.cguName]
    if (!d) return false
    return (d.recoverableAmount || 0) > 0
      && Math.abs((r.recoverableAmount || 0) - d.recoverableAmount) < 0.01
  }).length
})

function handleSyncFromI37() {
  const { changed } = syncRecoverableFromI3_7()
  if (changed > 0) {
    ElMessage.success(`已从 I3-7 同步 ${changed} 个资产组的可收回金额`)
  } else {
    ElMessage.info('I3-7 暂无可同步数据，或已与当前一致')
  }
}

async function handleAddCguRow() {
  try {
    const { value: name } = await ElMessageBox.prompt(
      cguNameOptions.value.length
        ? `请输入资产组(CGU)名称（可选已有：${cguNameOptions.value.slice(0, 5).join('、')}）`
        : '请输入资产组(CGU)名称',
      '新增资产组',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '资产组名称不能为空',
      },
    )
    if (name) addCguRow({ cguName: name.trim() })
  } catch { /* cancelled */ }
}

function handleRemoveCguRow(index: number) {
  removeCguRow(index)
}

function handleUpdateGoodwillB1(index: number, value: number | null) {
  updateGoodwillB1(index, value ?? 0)
}

function handleUpdateMinorityB2(index: number, value: number | null) {
  updateMinorityB2(index, value ?? 0)
}

function handleUpdateAssetGroup(index: number, value: number | null) {
  updateAssetGroupCarrying(index, value ?? 0)
}

function handleUpdateFv(index: number, value: number | null) {
  updateFairValueLessCost(index, value)
}

function handleUpdateViu(index: number, value: number | null) {
  updateValueInUse(index, value)
}

function handleUpdateReason(index: number, value: string) {
  updateImpairmentReason(index, value)
}

function handleUpdateCguName(index: number, value: string) {
  updateCguName(index, value)
}

async function handleAddOtherAsset(cguIndex: number) {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入其他资产名称（如：固定资产、无形资产）',
      '新增其他资产',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '资产名称不能为空',
      },
    )
    if (name) addOtherAsset(cguIndex, { name: name.trim(), bookValue: 0 })
  } catch { /* cancelled */ }
}

function handleRemoveOtherAsset(cguIndex: number, assetIndex: number) {
  removeOtherAsset(cguIndex, assetIndex)
}

function handleUpdateOtherAsset(
  cguIndex: number,
  assetIndex: number,
  field: 'name' | 'bookValue' | 'recoverableAmount',
  value: string | number | null,
) {
  if (assetIndex < 0) return
  updateOtherAsset(cguIndex, assetIndex, field, value)
}

function navigateToSheet(code: string) {
  emit('navigate-sheet', code)
}

const {
  exportTemplate,
  exportData,
  importData,
} = useI3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => {
    // allResponses 由父级刷新；本地 watch 会重载
  },
})

const fileInputRef = ref<HTMLInputElement | null>(null)

function handleExportImport(command: string) {
  switch (command) {
    case 'export-template':
      void exportTemplate('I3-6')
      break
    case 'export-data':
      void exportData('I3-6')
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

async function onImportFileSelected(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await importData('I3-6', file)
}

function saveMeta(key: string, value: string) {
  emit('save', key, value)
}

function saveIndicators() {
  emit('save', 'I3-6-indicators', JSON.stringify(impairmentIndicators.value))
}

function saveExpert() {
  emit('save', 'I3-6-expert', JSON.stringify(expertRows.map(r => ({
    key: r.key,
    used: r.used,
    remark: r.remark,
  }))))
}

function handleSaveConclusion() {
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

function handleSaveAuditConclusion() {
  emit('save', AUDIT_CONCLUSION_KEY, auditConclusionText.value)
}

function applyConclusionTemplate(key: string) {
  const t = CONCLUSION_TEMPLATES.find(x => x.key === key)
  if (!t) return
  auditConclusionText.value = t.text
  handleSaveAuditConclusion()
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
.i3-tab-impairment-test { padding: 16px; font-size: var(--wp-font-size, 13px); }

.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border: 1px solid #b3d8f0;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 24px;
}
.guidance-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #1a5276;
  line-height: 1.5;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #2980b9;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.section-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 10px;
  line-height: 1.6;
}
.ml-8 { margin-left: 8px; }
.table-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.objective-alert { margin-bottom: 16px; }

.indicator-grid {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 6px;
}
.indicator-grid :deep(.el-checkbox) {
  margin-right: 16px;
  margin-bottom: 6px;
  height: auto;
  white-space: normal;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 12px;
  flex-wrap: wrap;
}
.tab-toolbar .toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.impairment-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }

.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

.impaired-amount { color: var(--el-color-danger); font-weight: 600; }
.consol-hl { color: #1a5276; }

:deep(.row-impaired) { background-color: #fef0f0 !important; }
:deep(.row-impaired td) { background-color: #fef0f0 !important; }

.recoverable-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.expand-section {
  padding: 12px 16px;
  background: #fafbfc;
}
.expand-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}
.alloc-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 10px;
  font-size: 12px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.help-dot {
  display: inline-flex;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #909399;
  color: #fff;
  font-size: 10px;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
  cursor: help;
}
.other-assets-table { font-size: 12px; }
.alloc-floor-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.expert-table { font-size: 12px; }

.summary-row {
  padding: 12px 0;
  font-size: var(--wp-font-size, 13px);
  border-top: 2px solid var(--el-border-color);
  margin-top: 12px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
}
.summary-label { font-weight: 700; min-width: 40px; }
.summary-item { font-variant-numeric: tabular-nums; }

.add-row-bar { margin-top: 12px; }
.reversal-warning { margin-bottom: 16px; }
.audit-note-card { margin-bottom: 12px; }
.risk-card :deep(.el-card__body) { padding-top: 12px; }

.edit-tips {
  margin-top: 16px;
  font-size: 12px;
  color: #1a5276;
  background: #f5f8fb;
  border: 1px solid #d6e4f0;
  border-radius: 6px;
  padding: 10px 14px;
}
.edit-tips summary { cursor: pointer; font-weight: 600; color: #1a5276; }
.prep-list {
  padding-left: 20px;
  margin: 10px 0 0;
  line-height: 1.85;
  color: #2c5282;
}
.prep-list ul {
  padding-left: 18px;
  margin: 4px 0;
}
</style>
