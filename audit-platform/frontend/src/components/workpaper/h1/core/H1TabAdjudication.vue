<template>
  <div class="h1-tab-adjudication">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：复核固定资产原值(1601)、累计折旧(1602)、减值准备(1603)审定数；三角勾稽平衡；AJE/RJE 与 H1-3 一致；净值=原值−折旧−减值，与报表及 H1-2 勾稽。"
    />

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-1" :context-project-id="projectId" />
      <el-tag size="small" type="info">分类 {{ costDetailRows.length }}</el-tag>
      <el-tag v-if="significantNetChanges.length" size="small" type="warning">
        净值变动≥{{ CHANGE_RATE_THRESHOLD }}%：{{ significantNetChanges.length }} 项
      </el-tag>
      <div class="toolbar-spacer" />
      <el-button
        v-if="!isReadonly"
        size="small"
        :disabled="!hasCategoryPrefill"
        @click="handlePrefillTb"
      >
        从TB子科目预填
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        :disabled="!adjustmentCheck.h3Aje && !adjustmentCheck.h3Rje && !hasH3Rows"
        @click="handleSyncH3"
      >
        从 H1-3 按科目分摊
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        plain
        :loading="adjPullCost.loading.value"
        @click="openBringInCost"
      >
        <el-icon><Download /></el-icon>带入调整(原值)
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        plain
        :loading="adjPullDep.loading.value"
        @click="openBringInDep"
      >
        <el-icon><Download /></el-icon>带入调整(累计折旧)
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        plain
        :loading="adjPullImpair.loading.value"
        @click="openBringInImpair"
      >
        <el-icon><Download /></el-icon>带入调整(减值)
      </el-button>
      <el-button size="small" link type="default" @click="handleReview('H1-1')">💬 复核</el-button>
    </div>

    <!-- 一、原值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、固定资产原值（科目1601）</span>
          <el-button size="small" type="default" link @click="handleReview('H1-1-cost')">💬 复核</el-button>
        </div>
      </template>
      <el-table
        :data="costDisplayRows"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="adjRowClass"
      >
        <el-table-column prop="category" label="资产分类" min-width="120" fixed />
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('cost', row.rowId, 'beginBalance', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方(增加)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.debit"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('cost', row.rowId, 'debit', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方(减少)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.credit"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('cost', row.rowId, 'credit', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+借方−贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('cost', row.rowId, 'unadjusted', $event)"
            />
            <span v-else class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('cost', row.rowId, 'aje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('cost', row.rowId, 'rje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、累计折旧 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、累计折旧（科目1602·备抵）</span>
          <el-button size="small" type="default" link @click="handleReview('H1-1-dep')">💬 复核</el-button>
        </div>
      </template>
      <el-table
        :data="depDisplayRows"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="adjRowClass"
      >
        <el-table-column prop="category" label="资产分类" min-width="120" fixed />
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('dep', row.rowId, 'beginBalance', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方(减少)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.debit"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('dep', row.rowId, 'debit', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方(增加)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.credit"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('dep', row.rowId, 'credit', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+贷方−借方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('dep', row.rowId, 'unadjusted', $event)"
            />
            <span v-else class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('dep', row.rowId, 'aje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('dep', row.rowId, 'rje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、减值准备 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、减值准备（科目1603·备抵）</span>
          <el-button size="small" type="default" link @click="handleReview('H1-1-impair')">💬 复核</el-button>
        </div>
      </template>
      <el-table
        :data="impairDisplayRows"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="adjRowClass"
      >
        <el-table-column prop="category" label="资产分类" min-width="120" fixed />
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('impair', row.rowId, 'beginBalance', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方(转销)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.debit"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('impair', row.rowId, 'debit', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方(计提)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.credit"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('impair', row.rowId, 'credit', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+贷方−借方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('impair', row.rowId, 'unadjusted', $event)"
            />
            <span v-else class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('impair', row.rowId, 'aje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onCellChange('impair', row.rowId, 'rje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 四、净值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title"><span>四、净值（原值−累计折旧−减值准备）</span></div>
      </template>
      <el-table
        :data="netRows"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="netRowClass"
      >
        <el-table-column prop="category" label="资产分类" min-width="120" fixed />
        <el-table-column label="期初净值" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期初原值−期初折旧−期初减值">{{ fmtAmt(row.beginNet) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定净值" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定原值−审定折旧−审定减值">{{ fmtAmt(row.endNet) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末审定净值−期初净值">{{ fmtAmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'sig-change': row.isSignificant }]">
              {{ fmtPct(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动说明（↔H1-6）" min-width="200">
          <template #default="{ row }">
            <template v-if="!row.isSubtotal">
              <el-input
                v-if="!isReadonly"
                :model-value="row.explanation"
                size="small"
                :placeholder="row.isSignificant ? '重大变动须说明…' : '可选说明…'"
                @change="(v: string) => onNetExplanation(row.category, v)"
              />
              <span v-else>{{ row.explanation || '—' }}</span>
            </template>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="net-hint">
        审定净值合计 <b>{{ fmtAmt(netValueAudited) }}</b>
        （期初 {{ fmtAmt(netValueBegin) }}）；变动率绝对值≥{{ CHANGE_RATE_THRESHOLD }}% 须在下方说明原因。
      </p>
    </el-card>

    <!-- 勾稽校验 -->
    <el-card shadow="never" class="reconciliation-card">
      <template #header>
        <div class="section-title"><span>勾稽校验</span></div>
      </template>
      <el-table :data="reconciliationResults" size="small" border class="mb-12">
        <el-table-column prop="layer" label="三角勾稽层" width="120" />
        <el-table-column label="差额" width="150" align="right">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': !row.isBalanced }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isBalanced ? 'success' : 'danger'" size="small">
              {{ row.isBalanced ? '平衡' : '不平' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <h4 class="sub-h">与试算平衡表核对</h4>
      <el-table :data="differenceRows" size="small" border class="mb-12">
        <el-table-column prop="label" label="项目" min-width="160" />
        <el-table-column label="审定数" align="right" width="130">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.audited) }}</span></template>
        </el-table-column>
        <el-table-column label="TB / 明细参考" align="right" width="130">
          <template #default="{ row }"><span class="amount-cell tb-auto">{{ fmtAmt(row.tbAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" align="right" width="130">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div
        v-if="crossValidation.hasCostWarning || crossValidation.hasDepWarning || crossValidation.hasImpairWarning"
        class="cross-warning"
      >
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>
            与 H1-2 明细交叉验证异常：
            <span v-if="crossValidation.hasCostWarning">原值差 {{ fmtAmt(crossValidation.costDiff) }}</span>
            <span v-if="crossValidation.hasDepWarning">；折旧差 {{ fmtAmt(crossValidation.depDiff) }}</span>
            <span v-if="crossValidation.hasImpairWarning">；减值差 {{ fmtAmt(crossValidation.impairDiff) }}</span>
          </template>
        </el-alert>
      </div>
      <div v-if="adjustmentCheck.hasAjeWarning || adjustmentCheck.hasRjeWarning" class="cross-warning">
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>
            与 H1-3 调整勾稽：
            <span v-if="adjustmentCheck.hasAjeWarning">AJE 差 {{ fmtAmt(adjustmentCheck.ajeDiff) }}</span>
            <span v-if="adjustmentCheck.hasRjeWarning">；RJE 差 {{ fmtAmt(adjustmentCheck.rjeDiff) }}</span>
            （可用「从 H1-3 同步调整」预填）
          </template>
        </el-alert>
      </div>
    </el-card>

    <!-- 定性说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title"><span>审计说明事项（对齐源模板）</span></div>
      </template>
      <div class="qual-grid">
        <div class="qual-item">
          <label>(1) 净值重大变动原因（变动率≥{{ CHANGE_RATE_THRESHOLD }}%）</label>
          <el-input
            v-model="qualitativeNotes.fluctuation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="isReadonly"
            :placeholder="fluctuationPlaceholder"
            @blur="saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(2) 在建工程转入固定资产情况</label>
          <el-input
            v-model="qualitativeNotes.cipTransfer"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="说明本期自在建工程转入的金额、项目及与 H2 勾稽…"
            @blur="saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(3) 抵押、担保情况</label>
          <el-input
            v-model="qualitativeNotes.pledge"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="列示用于抵押/担保的固定资产原值、净值及权证索引（可与 H1-16/H1-17 勾稽）…"
            @blur="saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(4) 出售、置换情况</label>
          <el-input
            v-model="qualitativeNotes.disposal"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="说明本期出售/置换资产、处置损益及与 H1-8 勾稽…"
            @blur="saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(5) 租赁情况（融资租入 / 经营租出）</label>
          <el-input
            v-model="qualitativeNotes.lease"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="融资租入：原值/累计折旧/净值；经营租出：账面价值及租金（可与 H1-19/H1-20 勾稽）…"
            @blur="saveQualitativeNotes()"
          />
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <el-button
            size="small"
            type="primary"
            link
            :loading="aiNoteLoading"
            :disabled="isReadonly"
            @click="handleAi('adj-note')"
          >
            <el-icon><MagicStick /></el-icon> AI 生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="概述三角勾稽、重大变动、调整事项及与 H1-2/TB 勾稽结果…"
        :disabled="isReadonly"
        @blur="saveNote(auditNote)"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-select
              v-if="!isReadonly"
              size="small"
              placeholder="套用结论模板"
              style="width: 160px"
              @change="applyConclusionTemplate"
            >
              <el-option label="A 公允反映" value="A" />
              <el-option label="B 存在调整" value="B" />
              <el-option label="C 重大错报" value="C" />
            </el-select>
            <el-button
              size="small"
              type="primary"
              link
              :loading="aiConcLoading"
              :disabled="isReadonly"
              @click="handleAi('adj-conclusion')"
            >
              <el-icon><MagicStick /></el-icon> AI 生成
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="评价固定资产及相关备抵科目在重大方面是否公允反映…"
        :disabled="isReadonly"
        @blur="saveConclusion(auditConclusion)"
      />
    </el-card>

    <div v-if="!isReadonly" class="action-bar">
      <el-button type="primary" :loading="publishing" @click="handlePublish">
        确认审定 → 回写TB
      </el-button>
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>结构对齐源模板：原值 → 累计折旧 → 减值准备 → 净值（含变动额/率）</li>
        <li>「从TB子科目预填」按 1601/1602/1603 子科目名称映射五类未审数（仅填空行；可强制覆盖）</li>
        <li>「从 H1-3 按科目分摊」按 1601/1602/1603 + 名称关键词写入各分类 AJE/RJE</li>
        <li>「带入调整(原值/累计折旧/减值)」：从集中登记按科目 1601/1602/1603 拉取调整分录，逐笔分配到各分类的 AJE/RJE（原值借方净额、折旧/减值贷方净额），带入后审定数自动更新并联动附注</li>
        <li>净值变动说明与 H1-6 分析表共用键，双向联动</li>
        <li>净值变动率≥{{ CHANGE_RATE_THRESHOLD }}% 须在说明事项(1)或分类说明中解释</li>
        <li>「确认审定」回写 1601/1602/1603 并发布 EventBus</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInCostVisible"
      :matches="adjPullCost.matches.value"
      :row-options="bringInCostRowOptions"
      subject-label="1601 固定资产原值"
      :loading="adjPullCost.loading.value"
      @apply="onBringInCostApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInDepVisible"
      :matches="adjPullDep.matches.value"
      :row-options="bringInDepRowOptions"
      subject-label="1602 累计折旧"
      :loading="adjPullDep.loading.value"
      @apply="onBringInDepApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInImpairVisible"
      :matches="adjPullImpair.matches.value"
      :row-options="bringInImpairRowOptions"
      subject-label="1603 减值准备"
      :loading="adjPullImpair.loading.value"
      @apply="onBringInImpairApply"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import {
  useH1Adjudication,
  type AdjudicationBlock,
  type AdjudicationRow,
} from '../../composables/useH1Adjudication'
import { useH1CrossSheet } from '../../composables/useH1CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  htmlData?: any
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)
const publishing = ref(false)
const aiNoteLoading = ref(false)
const aiConcLoading = ref(false)

const { adjudicationFromDetail, adjustmentSync, detailTotals } = useH1CrossSheet(allResponsesRef as any)

const crossCost = computed(() => adjudicationFromDetail.value.costAudited)
const crossDep = computed(() => adjudicationFromDetail.value.depAudited)
const crossImpair = computed(() => adjudicationFromDetail.value.impairAudited)
const h3Aje = computed(() => adjustmentSync.value.totalAje)
const h3Rje = computed(() => adjustmentSync.value.totalRje)

const tbUnadjusted = computed(() => {
  const tb = props.htmlData?.tb_values || {}
  return {
    cost1601: Number(tb.cost_1601_unadjusted ?? tb.cost_unadjusted ?? detailTotals.value.originalCost) || 0,
    dep1602: Number(tb.dep_1602_unadjusted ?? tb.dep_unadjusted ?? detailTotals.value.accDep) || 0,
    impair1603: Number(tb.impair_1603_unadjusted ?? tb.impair_unadjusted ?? detailTotals.value.impairment) || 0,
  }
})

const categoryPrefill = computed(() => {
  const p = props.htmlData?.adjudication_category_prefill
  return p?.categories?.length ? p : null
})
const hasCategoryPrefill = computed(() => !!categoryPrefill.value)
const hasH3Rows = computed(() => {
  try {
    const raw = props.allResponses.get('H1-3-rows')?.remark
    const arr = typeof raw === 'string' ? JSON.parse(raw || '[]') : raw
    return Array.isArray(arr) && arr.length > 0
  } catch {
    return false
  }
})

const {
  costRows,
  depRows,
  impairRows,
  auditNote,
  auditConclusion,
  qualitativeNotes,
  costSubtotal,
  depSubtotal,
  impairSubtotal,
  netValueAudited,
  netValueBegin,
  netRows,
  significantNetChanges,
  reconciliationResults,
  differenceRows,
  crossValidation,
  adjustmentCheck,
  updateCell,
  syncAdjustmentsFromH3,
  applyCategoryPrefill,
  setChangeExplanation,
  publishAdjudicated,
  saveNote,
  saveConclusion,
  saveQualitativeNotes,
  CHANGE_RATE_THRESHOLD,
} = useH1Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    tbUnadjusted: tbUnadjusted as any,
    crossSheetCostAudited: crossCost,
    crossSheetDepAudited: crossDep,
    crossSheetImpairAudited: crossImpair,
    h3AjeTotal: h3Aje,
    h3RjeTotal: h3Rje,
    categoryPrefill: categoryPrefill as any,
    onSave: (itemId, value) => {
      const existing = props.allResponses.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
      const remark = typeof value === 'string' ? value : JSON.stringify(value)
      props.allResponses.set(itemId, { ...existing, item_id: itemId, remark })
      saveResponse(itemId, value)
    },
    onWritebackTB: async (cost, dep, impair) => {
      const codes: Array<{ code: string; amount: number }> = [
        { code: '1601', amount: cost },
        { code: '1602', amount: dep },
        { code: '1603', amount: impair },
      ]
      try {
        for (const { code, amount } of codes) {
          await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
            account_code: code,
            audited_amount: amount,
          })
        }
        ElMessage.success('已回写试算平衡表 1601/1602/1603')
      } catch {
        ElMessage.warning('审定数回写失败，请手动确认试算表数据')
      }
    },
    onPublishEvent: (event, payload) => {
      eventBus.emit(event as any, payload)
    },
  },
)

const costDetailRows = computed(() => costRows.value.filter((r) => !r.isSubtotal))
const costDisplayRows = computed(() => [...costDetailRows.value, { ...costSubtotal.value }])
const depDisplayRows = computed(() => [
  ...depRows.value.filter((r) => !r.isSubtotal),
  { ...depSubtotal.value },
])
const impairDisplayRows = computed(() => [
  ...impairRows.value.filter((r) => !r.isSubtotal),
  { ...impairSubtotal.value },
])

// ─── 从集中登记带入调整（三科目：1601原值[资产借]/1602累计折旧[备抵贷]/1603减值[备抵贷]；带入AJE/RJE） ───
const bringInCostRows = computed(() =>
  costRows.value
    .filter((r) => !r.isSubtotal)
    .map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullCost,
  visible: bringInCostVisible,
  rowOptions: bringInCostRowOptions,
  open: openBringInCost,
  apply: onBringInCostApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1601',
  direction: 'debit',
  subjectCode: '1601',
  wpCode: 'H1',
  subjectLabel: '固定资产原值(1601)',
  rows: bringInCostRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell('cost', rowKey, field, value),
  totalAudited: () => costSubtotal.value.audited,
})

const bringInDepRows = computed(() =>
  depRows.value
    .filter((r) => !r.isSubtotal)
    .map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullDep,
  visible: bringInDepVisible,
  rowOptions: bringInDepRowOptions,
  open: openBringInDep,
  apply: onBringInDepApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1602',
  direction: 'credit',
  subjectCode: '1602',
  wpCode: 'H1',
  subjectLabel: '累计折旧(1602)',
  rows: bringInDepRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell('dep', rowKey, field, value),
  totalAudited: () => depSubtotal.value.audited,
})

const bringInImpairRows = computed(() =>
  impairRows.value
    .filter((r) => !r.isSubtotal)
    .map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullImpair,
  visible: bringInImpairVisible,
  rowOptions: bringInImpairRowOptions,
  open: openBringInImpair,
  apply: onBringInImpairApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1603',
  direction: 'credit',
  subjectCode: '1603',
  wpCode: 'H1',
  subjectLabel: '减值准备(1603)',
  rows: bringInImpairRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell('impair', rowKey, field, value),
  totalAudited: () => impairSubtotal.value.audited,
})

const fluctuationPlaceholder = computed(() => {
  if (!significantNetChanges.value.length) {
    return '若无重大变动可简述「本期净值变动未超过30%，主要为正常增减折旧」…'
  }
  const names = significantNetChanges.value.map((r) => r.category).join('、')
  return `请说明「${names}」净值变动≥${CHANGE_RATE_THRESHOLD}% 的原因…`
})

function onCellChange(
  block: AdjudicationBlock,
  rowId: string,
  field: string,
  value: number | undefined,
) {
  updateCell(block, rowId, field as any, value ?? 0)
}

function handleSyncH3() {
  const r = syncAdjustmentsFromH3()
  if (r.applied) ElMessage.success(r.message)
  else ElMessage.info(r.message)
}

async function handlePrefillTb() {
  const soft = applyCategoryPrefill(false)
  if (soft.applied) {
    ElMessage.success(soft.message)
    return
  }
  // 已有数据时确认强制覆盖
  try {
    await ElMessageBox.confirm(
      '各分类已有数据。是否用 TB 子科目预填覆盖期初/发生额/未审数？（不覆盖 AJE/RJE）',
      '强制预填',
      { type: 'warning', confirmButtonText: '覆盖预填', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const hard = applyCategoryPrefill(true)
  if (hard.applied) ElMessage.success(hard.message)
  else ElMessage.info(hard.message)
}

function onNetExplanation(category: string, text: string) {
  setChangeExplanation(category, text)
}

async function handlePublish() {
  publishing.value = true
  try {
    await publishAdjudicated()
  } finally {
    publishing.value = false
  }
}

function handleReview(id: string) {
  openReviewDialog(id)
}

function adjRowClass({ row }: { row: AdjudicationRow }) {
  return row.isSubtotal ? 'row-subtotal' : ''
}

function netRowClass({ row }: { row: { isSubtotal?: boolean; isSignificant?: boolean } }) {
  if (row.isSubtotal) return 'row-subtotal'
  if (row.isSignificant) return 'row-significant'
  return ''
}

function applyConclusionTemplate(key: string) {
  const net = fmtAmt(netValueAudited.value)
  const templates: Record<string, string> = {
    A: `经审计，固定资产原值、累计折旧及减值准备审定净值合计 ${net} 元，与明细表及试算平衡表勾稽一致，三角勾稽平衡。我们认为，固定资产及相关备抵科目在所有重大方面公允反映。`,
    B: `经审计，固定资产审定净值合计 ${net} 元。审计过程中已提出账项/重分类调整（见 H1-3），调整后与明细及试算勾稽一致。除已调整事项外，固定资产在重大方面公允反映。`,
    C: `经审计，固定资产及相关备抵科目存在尚未消除的重大错报/勾稽差异（详见本表勾稽校验与说明事项），审定净值 ${net} 元尚不能作为报表列报依据，须进一步追查并调整。`,
  }
  const text = templates[key]
  if (!text) return
  auditConclusion.value = text
  saveConclusion(text)
}

async function handleAi(section: 'adj-note' | 'adj-conclusion') {
  if (!props.wpId) return
  const loading = section === 'adj-note' ? aiNoteLoading : aiConcLoading
  loading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/ai-generate`,
      {
        section,
        existingContent: section === 'adj-note' ? auditNote.value : auditConclusion.value,
        relatedContext: {
          costAudited: String(costSubtotal.value.audited),
          depAudited: String(depSubtotal.value.audited),
          impairAudited: String(impairSubtotal.value.audited),
          netValue: String(netValueAudited.value),
          reconciliation: JSON.stringify(reconciliationResults.value),
          significantChanges: JSON.stringify(significantNetChanges.value),
          qualitativeNotes: JSON.stringify(qualitativeNotes.value),
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    if (section === 'adj-note') {
      auditNote.value = text
      saveNote(text)
    } else {
      auditConclusion.value = text
      saveConclusion(text)
    }
    ElMessage.success('已生成')
  } catch {
    ElMessage.error('AI 生成失败')
  } finally {
    loading.value = false
  }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return '—'
  return `${val.toFixed(2)}%`
}
</script>

<style scoped>
.h1-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.toolbar-spacer { flex: 1; }
.block-card, .reconciliation-card, .note-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.title-actions { display: flex; gap: 8px; align-items: center; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; }
.error-amount, .sig-change { color: var(--el-color-danger); font-weight: 600; }
.net-hint { margin-top: 8px; font-size: 13px; color: var(--el-text-color-regular); }
.sub-h { margin: 8px 0; font-size: var(--wp-font-size, 13px); }
.mb-12 { margin-bottom: 12px; }
.cross-warning { margin-top: 12px; }
.qual-grid { display: flex; flex-direction: column; gap: 12px; }
.qual-item label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--el-text-color-regular);
}
.action-bar { margin-top: 16px; text-align: right; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-subtotal) { font-weight: 600; background: var(--el-fill-color-light) !important; }
:deep(.row-significant) { background: #fef0f0 !important; }
</style>
