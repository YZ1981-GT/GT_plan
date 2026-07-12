<template>
  <div class="i1-adjudication">
    <!-- 双模式切换 -->
    <div class="mode-switcher">
      <el-segmented v-model="viewMode" :options="['结构化视图', '在线编辑']" />
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>三角勾稽原理：</strong>审定表按三科目（原值1701/累计摊销1702/减值准备1703）分区块校验。</p>
      <p>原值（资产类借方）：期末余额 = 期初余额 + 本期增加 - 本期减少</p>
      <p>摊销/减值（备抵类贷方）：期末余额 = 期初余额 + 贷方发生（计提）- 借方发生（转回）</p>
      <p>净值合计 = 原值小计 - 摊销小计 - 减值小计。任一行勾稽差额≠0将红色高亮提示。</p>
    </div>

    <!-- 交叉验证警告 -->
    <div v-if="hasCrossWarning" class="cross-validation-warning">
      <el-badge :value="crossWarningCount" type="warning" class="cross-badge">
        <span>⚠ 审定表合计与I1-2明细表不一致，请核对</span>
      </el-badge>
    </div>

    <!-- 区块一：无形资产-原值（1701借方/资产类） -->
    <div class="block-section block-cost">
      <div class="block-header">
        <span class="block-title">一、无形资产-原值（1701借方/资产类）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" text @click="handleAiGenerate('cost')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
          <el-button size="small" type="default" text @click="handleReview('cost')">
            复核
          </el-button>
        </div>
      </div>
      <el-table
        :data="costDisplayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
      >
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              size="small"
              :controls="false"
              @change="onCellChange('cost', row.rowId, 'beginBalance', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.increase"
              size="small"
              :controls="false"
              @change="onCellChange('cost', row.rowId, 'increase', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.decrease"
              size="small"
              :controls="false"
              @change="onCellChange('cost', row.rowId, 'decrease', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="期末余额 = 期初余额 + 本期增加 - 本期减少" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="getReconciliationTooltip(row.rowId)" placement="top" :disabled="isRowBalanced(row.rowId)">
              <span :class="['formula-value', { 'subtotal-text': row.isSubtotal, 'reconciliation-error': !isRowBalanced(row.rowId) }]">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              size="small"
              :controls="false"
              @change="onCellChange('cost', row.rowId, 'unadjusted', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              size="small"
              :controls="false"
              @change="onCellChange('cost', row.rowId, 'aje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              size="small"
              :controls="false"
              @change="onCellChange('cost', row.rowId, 'rje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'subtotal-text': row.isSubtotal }]">
              {{ fmtAmount(row.audited) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区块二：累计摊销（1702贷方/备抵类） -->
    <div class="block-section block-amort">
      <div class="block-header">
        <span class="block-title">二、累计摊销（1702贷方/备抵类）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" text @click="handleAiGenerate('amort')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
          <el-button size="small" type="default" text @click="handleReview('amort')">
            复核
          </el-button>
        </div>
      </div>
      <el-table
        :data="amortDisplayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
      >
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              size="small"
              :controls="false"
              @change="onCellChange('amort', row.rowId, 'beginBalance', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.increase"
              size="small"
              :controls="false"
              @change="onCellChange('amort', row.rowId, 'increase', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.decrease"
              size="small"
              :controls="false"
              @change="onCellChange('amort', row.rowId, 'decrease', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="备抵类：期末 = 期初 + 贷方(增加) - 借方(减少)" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="getReconciliationTooltip(row.rowId)" placement="top" :disabled="isRowBalanced(row.rowId)">
              <span :class="['formula-value', { 'subtotal-text': row.isSubtotal, 'reconciliation-error': !isRowBalanced(row.rowId) }]">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              size="small"
              :controls="false"
              @change="onCellChange('amort', row.rowId, 'unadjusted', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              size="small"
              :controls="false"
              @change="onCellChange('amort', row.rowId, 'aje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              size="small"
              :controls="false"
              @change="onCellChange('amort', row.rowId, 'rje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'subtotal-text': row.isSubtotal }]">
              {{ fmtAmount(row.audited) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区块三：减值准备（1703贷方/备抵类） -->
    <div class="block-section block-impairment">
      <div class="block-header">
        <span class="block-title">三、减值准备（1703贷方/备抵类）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" text @click="handleAiGenerate('impairment')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
          <el-button size="small" type="default" text @click="handleReview('impairment')">
            复核
          </el-button>
        </div>
      </div>
      <el-table
        :data="impairmentDisplayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
      >
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              size="small"
              :controls="false"
              @change="onCellChange('impairment', row.rowId, 'beginBalance', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.increase"
              size="small"
              :controls="false"
              @change="onCellChange('impairment', row.rowId, 'increase', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.decrease"
              size="small"
              :controls="false"
              @change="onCellChange('impairment', row.rowId, 'decrease', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="备抵类：期末 = 期初 + 贷方(增加) - 借方(减少)" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="getReconciliationTooltip(row.rowId)" placement="top" :disabled="isRowBalanced(row.rowId)">
              <span :class="['formula-value', { 'subtotal-text': row.isSubtotal, 'reconciliation-error': !isRowBalanced(row.rowId) }]">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              size="small"
              :controls="false"
              @change="onCellChange('impairment', row.rowId, 'unadjusted', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              size="small"
              :controls="false"
              @change="onCellChange('impairment', row.rowId, 'aje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              size="small"
              :controls="false"
              @change="onCellChange('impairment', row.rowId, 'rje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'subtotal-text': row.isSubtotal }]">
              {{ fmtAmount(row.audited) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 净值合计行 -->
    <div class="net-value-section">
      <el-table :data="[netValueRow]" border size="small" class="adjudication-table net-value-table">
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span class="net-value-text">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="net-value-text">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <span class="net-value-text">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <span class="net-value-text">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="净值 = 原值小计 - 摊销小计 - 减值小计" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="net-value-text formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="net-value-text">{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <span class="net-value-text">{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <span class="net-value-text">{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="净值审定 = 原值审定 - 摊销审定 - 减值审定" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="net-value-text formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- TB取数行 + 差异行 -->
    <div class="tb-section">
      <div class="block-header">
        <span class="block-title">TB取数与差异</span>
      </div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="160" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.tbAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip
              :content="`差异 = 审定数(${fmtAmount(row.audited)}) - TB未审数(${fmtAmount(row.tbAmount)})`"
              placement="top"
            >
              <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">
                {{ fmtAmount(row.difference) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 跨底稿联动跳转 -->
    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="I2" @click="navigateTo('I2')" />
      <GtIndexChip value="I1-3" @click="navigateTo('I1-3')" />
      <GtIndexChip value="I1-5" @click="navigateTo('I1-5')" />
      <GtIndexChip value="I1-9" @click="navigateTo('I1-9')" />
      <GtIndexChip value="A13" @click="navigateTo('A13')" />
    </div>

    <!-- 审计说明 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请填写审计说明..."
        :disabled="isReadonly"
        @blur="onNoteBlur"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请填写审计结论..."
        :disabled="isReadonly"
        @blur="onConclusionBlur"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useI1Adjudication, type I1BlockType, type I1AdjudicationRow } from '../../composables/useI1Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: {
    unadjusted1701: number
    audited1701: number
    unadjusted1702: number
    audited1702: number
    unadjusted1703: number
    audited1703: number
  }
  isReadonly: boolean
  crossSheetCostAudited?: number
  crossSheetAmortAudited?: number
  crossSheetImpairAudited?: number
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  costRows,
  amortRows,
  impairmentRows,
  auditNote,
  auditConclusion,
  costSubtotal,
  amortSubtotal,
  impairmentSubtotal,
  netValueRow,
  reconciliationResults,
  differenceRows,
  crossValidation,
  updateCell,
  saveAdjudication,
  saveNote,
  saveConclusion,
} = useI1Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbData: toRef(props, 'tbData'),
    crossSheetCostAudited: toRef(props, 'crossSheetCostAudited'),
    crossSheetAmortAudited: toRef(props, 'crossSheetAmortAudited'),
    crossSheetImpairAudited: toRef(props, 'crossSheetImpairAudited'),
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── View Mode ───────────────────────────────────────────────────────────────

const viewMode = ref('结构化视图')

// ─── Display Rows (detail + subtotal) ────────────────────────────────────────

const costDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = costRows.value.filter((r) => !r.isSubtotal)
  return [...detail, costSubtotal.value]
})

const amortDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = amortRows.value.filter((r) => !r.isSubtotal)
  return [...detail, amortSubtotal.value]
})

const impairmentDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = impairmentRows.value.filter((r) => !r.isSubtotal)
  return [...detail, impairmentSubtotal.value]
})

// ─── Cross Validation Warning ────────────────────────────────────────────────

const hasCrossWarning = computed(() => {
  const cv = crossValidation.value
  return cv.hasCostWarning || cv.hasAmortWarning || cv.hasImpairWarning
})

const crossWarningCount = computed(() => {
  const cv = crossValidation.value
  let count = 0
  if (cv.hasCostWarning) count++
  if (cv.hasAmortWarning) count++
  if (cv.hasImpairWarning) count++
  return count
})

// ─── Reconciliation Helpers ──────────────────────────────────────────────────

function isRowBalanced(rowId: string): boolean {
  const result = reconciliationResults.value.find((r) => r.rowId === rowId)
  return result ? result.isBalanced : true
}

function getReconciliationTooltip(rowId: string): string {
  const result = reconciliationResults.value.find((r) => r.rowId === rowId)
  if (!result || result.isBalanced) return ''
  return `三角勾稽差额: ${fmtAmount(result.difference)}（期末 ≠ 期初 + 增加 - 减少）`
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: I1AdjudicationRow }): string {
  const classes: string[] = []
  if (row.isSubtotal) classes.push('subtotal-row')
  if (!isRowBalanced(row.rowId)) classes.push('reconciliation-error-row')
  return classes.join(' ')
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onCellChange(block: I1BlockType, rowId: string, field: keyof I1AdjudicationRow, value: number | null): void {
  updateCell(block, rowId, field, value ?? 0)
  saveAdjudication()
}

// ─── Note / Conclusion ───────────────────────────────────────────────────────

function onNoteBlur(): void {
  saveNote(auditNote.value)
}

function onConclusionBlur(): void {
  saveConclusion(auditConclusion.value)
}

// ─── AI / Review ─────────────────────────────────────────────────────────────

function handleAiGenerate(section: string): void {
  // 由主入口 provide 的 openAiGenerate 处理
  console.log('[I1-Adjudication] AI generate:', section)
}

function handleReview(section: string): void {
  // 由主入口 provide 的 openReviewDialog 处理
  console.log('[I1-Adjudication] Review:', section)
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

// ─── Amount Formatter ────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-adjudication {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

/* 双模式切换 */
.mode-switcher {
  margin-bottom: 16px;
}

/* 方法论上下文 */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p {
  margin: 0;
}
.methodology-context strong {
  color: #78350f;
}

/* 交叉验证警告 */
.cross-validation-warning {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 6px;
}
.cross-badge {
  display: inline-flex;
  align-items: center;
}

/* 区块通用 */
.block-section {
  margin-bottom: 20px;
  border-radius: 8px;
  overflow: hidden;
}
.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  font-weight: 600;
  font-size: 14px;
}
.block-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.block-title {
  font-size: 14px;
}

/* 区块颜色 */
.block-cost .block-header {
  background: #dcfce7;
  color: #166534;
}
.block-cost {
  border: 1px solid #bbf7d0;
}

.block-amort .block-header {
  background: #dbeafe;
  color: #1e3a5f;
}
.block-amort {
  border: 1px solid #bfdbfe;
}

.block-impairment .block-header {
  background: #ede9fe;
  color: #4c1d95;
}
.block-impairment {
  border: 1px solid #ddd6fe;
}

/* 表格 */
.adjudication-table {
  font-size: var(--wp-font-size, 13px);
}
.adjudication-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f8fafc;
}
.adjudication-table :deep(.el-input-number) {
  width: 100%;
}
.adjudication-table :deep(.el-input-number .el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

/* 小计行 */
.subtotal-text {
  font-weight: 700;
}
:deep(.subtotal-row) {
  background-color: #f1f5f9 !important;
}
:deep(.subtotal-row td) {
  font-weight: 700;
}

/* 公式列 */
.formula-col-header {
  border-bottom: 1px dashed #94a3b8;
  cursor: help;
  padding-bottom: 2px;
}
.formula-value {
  border-bottom: 1px dashed #94a3b8;
  cursor: help;
  padding-bottom: 1px;
}

/* 三角勾稽校验失败 */
.reconciliation-error {
  color: #dc2626;
  font-weight: 600;
}
:deep(.reconciliation-error-row) {
  background-color: #fef2f2 !important;
}
:deep(.reconciliation-error-row td) {
  color: #991b1b;
}

/* 净值行 */
.net-value-section {
  margin-bottom: 20px;
}
.net-value-table {
  border: 2px solid #1e293b;
}
.net-value-text {
  font-weight: 700;
  font-size: 14px;
  color: #0f172a;
}

/* TB取数/差异 */
.tb-section {
  margin-bottom: 20px;
}
.tb-section .block-header {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-bottom: none;
  border-radius: 6px 6px 0 0;
}
.tb-table {
  border: 1px solid #e2e8f0;
}
.difference-warning {
  color: #dc2626;
  font-weight: 600;
}

/* 审计说明/结论卡片 */
.audit-note-card {
  margin-bottom: 16px;
}
.audit-note-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #f8fafc;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 14px;
}
.audit-note-card :deep(.el-textarea__inner) {
  font-size: var(--wp-font-size, 13px);
}

/* 跨底稿联动栏 */
.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  margin-bottom: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  border: 1px dashed var(--el-border-color);
  font-size: 12px;
}
.cross-ref-label {
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
</style>
