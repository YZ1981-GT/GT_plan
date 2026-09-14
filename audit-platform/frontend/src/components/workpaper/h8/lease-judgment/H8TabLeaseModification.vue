<template>
  <div class="h8-tab-lease-modification">
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：核实租赁变更判定（单独租赁/范围减少/其他变更）及重新计量准确性，确认符合 CAS21 第28-30条。" />

    <div class="methodology-context">
      <p>
        编制逻辑：①判定树（1.1/1.2 互斥）→ ②变更日账面（H8-2 带入 / H8-6 估算）→
        ③折现表或年金测算新负债 PV → ④调整 ROU → ⑤回写 H8-2 变更区段。
      </p>
    </div>

    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-7" />
      <el-tag size="small" type="info">共 {{ rows.length }} 笔</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-2')">→ H8-2</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-5')">→ H8-5</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-6')">→ H8-6</el-tag>
      <el-dropdown size="small" @command="handleExportCommand">
        <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    </div>

    <div class="stats-bar">
      <el-tag type="info" size="small">{{ rows.length }} 笔变更</el-tag>
      <el-tag v-if="typeStats.separateLease > 0" type="success" size="small">单独租赁：{{ typeStats.separateLease }}</el-tag>
      <el-tag v-if="typeStats.scopeReduction > 0" type="warning" size="small">范围减少：{{ typeStats.scopeReduction }}</el-tag>
      <el-tag v-if="typeStats.otherModification > 0" type="primary" size="small">其他变更：{{ typeStats.otherModification }}</el-tag>
      <el-tag type="danger" size="small" effect="plain">调整合计：{{ fmtAmt(totalAdjustment) }}</el-tag>
      <div class="stats-actions">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRow">+ 新增变更</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleSyncH82">回写 H8-2</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'lease-modification')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'lease-modification')">复核</el-button>
      </div>
    </div>

    <!-- 默认汇总表 -->
    <el-card v-if="rows.length > 0" shadow="never" class="summary-card">
      <template #header>
        <div class="summary-header">
          <span class="card-title">变更汇总</span>
          <el-button link type="primary" size="small" @click="expandAll(!allExpanded)">
            {{ allExpanded ? '全部折叠' : '全部展开' }}
          </el-button>
        </div>
      </template>
      <el-table :data="rows" border size="small" class="mod-table" @row-click="onSummaryRowClick">
        <el-table-column prop="contractNo" label="合同号" width="120" />
        <el-table-column prop="modificationDate" label="变更日期" width="110" />
        <el-table-column prop="modificationType" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getModTypeTag(row.modificationType)" size="small">{{ row.modificationType || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="账面负债" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.carryingLiability) }}</template>
        </el-table-column>
        <el-table-column label="新负债PV" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.newLiabilityPV) }}</template>
        </el-table-column>
        <el-table-column label="调整额" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.adjustmentAmount) }}</template>
        </el-table-column>
        <el-table-column label="重计量ROU" width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.remeasuredROUAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="校验" width="70" align="center">
          <template #default="{ row }">
            <el-badge :value="issueCount(row.rowId)" :hidden="issueCount(row.rowId) === 0" type="warning">
              <span>{{ issueCount(row.rowId) ? '!' : '✓' }}</span>
            </el-badge>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" width="70" align="center" />
      </el-table>
      <div class="stat-bar"><span>变更调整合计：{{ fmtAmt(totalAdjustment) }}元</span></div>
    </el-card>

    <div v-if="rows.length === 0" class="empty-state">
      <el-empty description="暂无租赁变更记录" />
    </div>

    <!-- 可折叠明细卡片 -->
    <el-collapse v-model="expandedIds" class="mod-collapse">
      <el-collapse-item v-for="row in rows" :key="row.rowId" :name="row.rowId">
        <template #title>
          <div class="collapse-title" @click.stop>
            <span class="contract-label">{{ row.contractNo || '未命名合同' }}</span>
            <el-tag v-if="row.modificationType" :type="getModTypeTag(row.modificationType)" size="small">
              {{ row.modificationType }}
            </el-tag>
            <el-tag v-if="row.modificationDate" size="small" type="info">{{ row.modificationDate }}</el-tag>
            <el-tag size="small" effect="plain">调整 {{ fmtAmt(row.adjustmentAmount) }}</el-tag>
            <el-tag v-if="issueCount(row.rowId)" size="small" type="warning">
              {{ issueCount(row.rowId) }} 项提示
            </el-tag>
          </div>
        </template>

        <div class="mod-card-body">
          <!-- 校验提示 -->
          <div v-if="issuesOf(row.rowId).length" class="validation-box">
            <div v-for="iss in issuesOf(row.rowId)" :key="iss.code" class="validation-item" :class="iss.level">
              {{ iss.message }}
            </div>
          </div>

          <el-form :inline="true" size="small" class="mod-form">
            <el-form-item label="合同号">
              <el-select
                v-if="!isReadonly && h82Contracts.length"
                :model-value="row.contractNo"
                filterable allow-create default-first-option
                placeholder="选 H8-2 或手输" style="width: 160px"
                @change="(v: string) => onPickContract(row.rowId, v)"
              >
                <el-option v-for="c in h82Contracts" :key="c.contractNo" :label="c.contractNo" :value="c.contractNo" />
              </el-select>
              <el-input v-else :model-value="row.contractNo" :disabled="isReadonly" style="width: 140px"
                @change="(v: string) => onCell(row.rowId, 'contractNo', v)" />
            </el-form-item>
            <el-form-item label="变更日期">
              <el-input :model-value="row.modificationDate" :disabled="isReadonly" placeholder="YYYY-MM-DD" style="width: 130px"
                @change="(v: string) => onCell(row.rowId, 'modificationDate', v)" />
            </el-form-item>
            <el-form-item label="资产名称">
              <el-input :model-value="row.assetName" :disabled="isReadonly" style="width: 140px"
                @change="(v: string) => onCell(row.rowId, 'assetName', v)" />
            </el-form-item>
            <el-form-item label="结论">
              <el-radio-group :model-value="row.conclusion" :disabled="isReadonly"
                @change="(v: string | number | boolean | undefined) => onCell(row.rowId, 'conclusion', v)">
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
                <el-radio-button value="不适用">不适用</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="!isReadonly">
              <el-button size="small" @click="handlePullH82(row.rowId)">从 H8-2 带入</el-button>
              <el-button size="small" @click="handleEstH86(row.rowId)">H8-6 估负债</el-button>
              <el-button v-if="row.modificationType === '单独租赁'" size="small" type="success"
                @click="handleCreateSep(row.rowId)">生成 H8-2 新合同</el-button>
              <el-button type="danger" link size="small" @click="handleDelete(row.rowId)">删除</el-button>
            </el-form-item>
          </el-form>

          <!-- 1 判定树 -->
          <div class="section-block">
            <div class="section-title">1. 租赁变更情况（判定树）</div>
            <div class="option-section" :class="{ active: isSeparate(row) }">
              <div class="option-header">
                <span class="option-title">1.1 是否作为一项单独租赁</span>
                <el-tag v-if="isSeparate(row)" type="success" size="small">适用</el-tag>
              </div>
              <div class="judgment-row">
                <span class="judgment-label">（1）是否扩大租赁范围（增加使用权）</span>
                <el-radio-group :model-value="row.expandsScope" :disabled="isReadonly" size="small"
                  @change="(v: string | number | boolean | undefined) => onCell(row.rowId, 'expandsScope', v)">
                  <el-radio-button value="是">是</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </div>
              <div class="judgment-row">
                <span class="judgment-label">（2）增加对价是否相当于扩大部分单独价格</span>
                <el-radio-group :model-value="row.standalonePrice" :disabled="isReadonly" size="small"
                  @change="(v: string | number | boolean | undefined) => onCell(row.rowId, 'standalonePrice', v)">
                  <el-radio-button value="是">是</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </div>
            </div>

            <div class="option-section" :class="{ muted: isSeparate(row) }">
              <div class="option-header">
                <span class="option-title">1.2 未作为单独租赁</span>
                <el-tag v-if="isSeparate(row)" type="info" size="small">与 1.1 互斥</el-tag>
              </div>
              <div class="judgment-row">
                <span class="judgment-label">范围减少或租赁期缩短？</span>
                <el-radio-group :model-value="row.scopeReduction" :disabled="isReadonly || isSeparate(row)" size="small"
                  @change="(v: string | number | boolean | undefined) => onCell(row.rowId, 'scopeReduction', v)">
                  <el-radio-button value="是">是（范围减少）</el-radio-button>
                  <el-radio-button value="否">否（其他变更）</el-radio-button>
                </el-radio-group>
              </div>
              <el-input type="textarea" :autosize="{ minRows: 2 }" :model-value="row.modificationDesc"
                :disabled="isReadonly || isSeparate(row)" placeholder="变更事项说明…"
                @change="(v: string) => onCell(row.rowId, 'modificationDesc', v)" />
            </div>

            <div class="type-override">
              <span class="override-label">变更类型</span>
              <el-select :model-value="row.modificationType" :disabled="isReadonly" size="small" style="width: 140px"
                @change="(v: string) => onCell(row.rowId, 'modificationType', v)">
                <el-option label="单独租赁" value="单独租赁" />
                <el-option label="范围减少" value="范围减少" />
                <el-option label="其他变更" value="其他变更" />
              </el-select>
              <el-button v-if="!isReadonly && row.typeManualOverride" link type="primary" size="small"
                @click="onCell(row.rowId, 'typeManualOverride', false)">恢复自动推导</el-button>
            </div>
          </div>

          <!-- 2 账面 -->
          <div class="section-block">
            <div class="section-title">2. 变更日账面</div>
            <el-form :inline="true" size="small" class="mod-form">
              <el-form-item label="原条款">
                <el-input :model-value="row.originalTerms" :disabled="isReadonly" style="width: 220px"
                  @change="(v: string) => onCell(row.rowId, 'originalTerms', v)" />
              </el-form-item>
              <el-form-item label="账面负债">
                <WpAmountInput :model-value="row.carryingLiability" :disabled="isReadonly"
                  @change="(v: number | undefined) => onCell(row.rowId, 'carryingLiability', v)" />
              </el-form-item>
              <el-form-item label="账面 ROU">
                <WpAmountInput :model-value="row.carryingROU" :disabled="isReadonly"
                  @change="(v: number | undefined) => onCell(row.rowId, 'carryingROU', v)" />
              </el-form-item>
              <el-form-item v-if="row.sourceTag" label="来源">
                <el-tag size="small" type="info">{{ row.sourceTag }}</el-tag>
              </el-form-item>
            </el-form>
          </div>

          <!-- 3 重计量 -->
          <div class="section-block" :class="{ muted: row.modificationType === '单独租赁' }">
            <div class="section-title">3. 变更后重新计量</div>

            <template v-if="row.modificationType === '范围减少'">
              <el-form :inline="true" size="small" class="mod-form">
                <el-form-item label="终止比例(%)">
                  <el-input-number
                    :model-value="Math.round(row.reductionRatio * 10000) / 100"
                    :controls="false" :disabled="isReadonly" :min="0" :max="100" :precision="2"
                    @change="(v: number | undefined) => onCell(row.rowId, 'reductionRatio', (Number(v) || 0) / 100)"
                  />
                </el-form-item>
                <el-form-item label="终止损益">
                  <span class="formula-value">{{ fmtAmt(row.scopeGainLoss) }}</span>
                  <span class="hint">（终止负债 − 终止 ROU）</span>
                </el-form-item>
              </el-form>
            </template>

            <template v-else>
              <el-form :inline="true" size="small" class="mod-form">
                <el-form-item label="新条款">
                  <el-input :model-value="row.newTerms" :disabled="isReadonly || row.modificationType === '单独租赁'" style="width: 180px"
                    @change="(v: string) => onCell(row.rowId, 'newTerms', v)" />
                </el-form-item>
                <el-form-item label="修订折现率(%)">
                  <el-input-number
                    :model-value="rateAsPercent(row.revisedDiscountRate)"
                    :controls="false" :disabled="isReadonly || row.modificationType === '单独租赁'"
                    :precision="4"
                    @change="(v: number | undefined) => onCell(row.rowId, 'revisedDiscountRate', percentToRate(v))"
                  />
                </el-form-item>
                <el-form-item label="付款时点">
                  <el-radio-group
                    :model-value="row.paymentTiming"
                    :disabled="isReadonly || row.modificationType === '单独租赁'"
                    size="small"
                    @change="(v: string | number | boolean | undefined) => onCell(row.rowId, 'paymentTiming', v)"
                  >
                    <el-radio-button value="期末">期末</el-radio-button>
                    <el-radio-button value="期初">期初</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="等额年付款">
                  <el-input-number :model-value="row.remainingAnnualPayment" :controls="false"
                    :disabled="isReadonly || row.modificationType === '单独租赁' || row.useCustomPayments" :precision="2"
                    @change="(v: number | undefined) => onCell(row.rowId, 'remainingAnnualPayment', v)" />
                </el-form-item>
                <el-form-item label="剩余期数">
                  <el-input-number :model-value="row.remainingPeriods" :controls="false"
                    :disabled="isReadonly || row.modificationType === '单独租赁' || row.useCustomPayments" :min="0" :precision="0"
                    @change="(v: number | undefined) => onCell(row.rowId, 'remainingPeriods', v)" />
                </el-form-item>
                <el-form-item label="ROU摊销期(年)">
                  <WpAmountInput :model-value="row.rouAmortYears" :disabled="isReadonly"
                    @change="(v: number | undefined) => onCell(row.rowId, 'rouAmortYears', v)" />
                </el-form-item>
                <el-form-item label="新负债现值">
                  <el-input-number :model-value="row.newLiabilityPV" :controls="false"
                    :disabled="isReadonly || row.modificationType === '单独租赁'" :precision="2"
                    @change="(v: number | undefined) => onCell(row.rowId, 'newLiabilityPV', v)" />
                  <el-tag v-if="row.autoCalcNewPV" size="small" type="success" class="inline-tag">自动测算</el-tag>
                </el-form-item>
              </el-form>

              <div class="schedule-toolbar" v-if="!isReadonly && row.modificationType !== '单独租赁'">
                <el-checkbox
                  :model-value="row.useCustomPayments"
                  @change="(v: boolean | string | number) => onCell(row.rowId, 'useCustomPayments', !!v)"
                >使用逐期付款折现表</el-checkbox>
                <el-button v-if="row.useCustomPayments" size="small" @click="addCustomPayment(row.rowId)">+ 付款行</el-button>
              </div>

              <el-table
                v-if="scheduleOf(row.rowId).rows.length"
                :data="scheduleOf(row.rowId).rows"
                border size="small" class="schedule-table"
              >
                <el-table-column prop="seq" label="#" width="50" />
                <el-table-column label="付款额" width="120" align="right">
                  <template #default="{ row: pr, $index }">
                    <el-input-number
                      v-if="row.useCustomPayments && !isReadonly"
                      :model-value="pr.amount" :controls="false" size="small" :precision="2"
                      @change="(v: number | undefined) => patchCustomPayment(row.rowId, $index, 'amount', v)"
                    />
                    <span v-else>{{ fmtAmt(pr.amount) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="折现期" width="90" align="right">
                  <template #default="{ row: pr, $index }">
                    <el-input-number
                      v-if="row.useCustomPayments && !isReadonly"
                      :model-value="pr.periods" :controls="false" size="small" :precision="0"
                      @change="(v: number | undefined) => patchCustomPayment(row.rowId, $index, 'periods', v)"
                    />
                    <span v-else>{{ pr.periods }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="折现系数" width="100" align="right">
                  <template #default="{ row: pr }">{{ pr.discountFactor.toFixed(4) }}</template>
                </el-table-column>
                <el-table-column label="现值" width="120" align="right" class-name="formula-col">
                  <template #default="{ row: pr }">{{ fmtAmt(pr.presentValue) }}</template>
                </el-table-column>
                <el-table-column v-if="row.useCustomPayments && !isReadonly" label="" width="50">
                  <template #default="{ $index }">
                    <el-button link type="danger" size="small" @click="removeCustomPayment(row.rowId, $index)">✕</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <div v-if="scheduleOf(row.rowId).rows.length" class="schedule-total">
                折现合计 PV：{{ fmtAmt(scheduleOf(row.rowId).totalPV) }}
              </div>
            </template>

            <el-form :inline="true" size="small" class="mod-form" style="margin-top: 8px">
              <el-form-item label="调整额">
                <el-input-number :model-value="row.adjustmentAmount" :controls="false" :disabled="isReadonly" :precision="2"
                  @change="(v: number | undefined) => onCell(row.rowId, 'adjustmentAmount', v)" />
              </el-form-item>
            </el-form>

            <div class="calc-result">
              <div class="formula-display">
                <template v-if="row.modificationType === '其他变更'">
                  调整额 = 新负债PV({{ fmtAmt(row.newLiabilityPV) }}) − 账面负债({{ fmtAmt(row.carryingLiability) }})
                  = <strong>{{ fmtAmt(row.adjustmentAmount) }}</strong><br />
                  重计量 ROU = 账面ROU({{ fmtAmt(row.carryingROU) }}) + 调整额({{ fmtAmt(row.adjustmentAmount) }})
                  = <strong>{{ fmtAmt(row.remeasuredROUAmount) }}</strong>
                </template>
                <template v-else-if="row.modificationType === '范围减少'">
                  终止比例 {{ (row.reductionRatio * 100).toFixed(1) }}%；
                  终止损益 <strong>{{ fmtAmt(row.scopeGainLoss) }}</strong>；
                  剩余 ROU <strong>{{ fmtAmt(row.remeasuredROUAmount) }}</strong>
                </template>
                <template v-else-if="row.modificationType === '单独租赁'">
                  作为单独租赁核算，原合同不重计量。可「生成 H8-2 新合同」落地计量。
                </template>
                <template v-else>请先完成判定树</template>
              </div>
            </div>
          </div>

          <el-form size="small" label-position="top">
            <el-form-item label="会计处理">
              <el-input type="textarea" :autosize="{ minRows: 2 }" :model-value="row.accountingTreatment"
                :disabled="isReadonly" @change="(v: string) => onCell(row.rowId, 'accountingTreatment', v)" />
            </el-form-item>
          </el-form>
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 4 }" @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }" @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>1.1 与 1.2 互斥；单独租赁不重计量原合同，可生成 H8-2 新行</li>
        <li>其他变更：调整额 = 新负债 PV − 账面负债；支持期末/期初年金或逐期折现表</li>
        <li>范围减少：按终止比例冲减 ROU/负债，差额入损益</li>
        <li>H8-6 无逐年 JSON 时，负债按计量参数滚动估算，须人工复核</li>
        <li>「回写 H8-2」将调整额写入明细变更区段</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, toRef, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH8LeaseModification, type H8LeaseModificationRow } from '../../composables/useH8LeaseModification'
import { isSeparateLease } from '../../composables/useH8CAS21Engine'
import { useH8ImportExport } from '../../composables/useH8ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const {
  rows, totalAdjustment, typeStats, h82Contracts, rowValidations,
  addRow, deleteRow, updateCell, setExpanded,
  getPaymentSchedule, pullFromH82, estimateLiabilityFromH86,
  syncAdjustmentsToH82, createSeparateLeaseOnH82,
  addCustomPayment, removeCustomPayment, load,
} = useH8LeaseModification({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const h8ReloadAll = inject<() => Promise<void>>('h8ReloadAll', async () => {})
const { isExporting, isImporting, exportTemplate, exportData, importData } = useH8ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
  sheetCode: 'H8-7',
  onImported: async () => {
    await h8ReloadAll()
    load()
  },
})
const ieBusy = computed(() => isExporting.value || isImporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(['H8-7'])
  else if (cmd === 'export-data') await exportData(['H8-7'])
  else if (cmd === 'import-data') fileInputRef.value?.click()
}
async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData(file, ['H8-7'])
  ;(e.target as HTMLInputElement).value = ''
}

const expandedIds = ref<string[]>([])
watch(rows, (list) => {
  const ids = list.filter(r => r.expanded !== false).map(r => r.rowId)
  expandedIds.value = ids.length ? ids : list.slice(0, 1).map(r => r.rowId)
}, { immediate: true })
watch(expandedIds, (ids) => {
  const set = new Set(ids)
  for (const r of rows.value) {
    const want = set.has(r.rowId)
    if (r.expanded !== want) setExpanded(r.rowId, want)
  }
})

const allExpanded = computed(() =>
  rows.value.length > 0 && expandedIds.value.length >= rows.value.length,
)
function expandAll(open: boolean) {
  expandedIds.value = open ? rows.value.map(r => r.rowId) : []
}

const AUDIT_NOTE_KEY = 'H8-lease-modification-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-lease-modification-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}

function fmtAmt(v: number): string {
  if (v == null || Number.isNaN(v)) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function rateAsPercent(rate: number): number {
  return Math.round((Number(rate) || 0) * 10000) / 100
}
function percentToRate(pct: number | undefined): number {
  return (Number(pct) || 0) / 100
}
function isSeparate(row: H8LeaseModificationRow): boolean {
  return isSeparateLease(row.expandsScope, row.standalonePrice)
}
function getModTypeTag(type: string): 'success' | 'warning' | 'primary' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'primary'> = {
    '单独租赁': 'success', '范围减少': 'warning', '其他变更': 'primary',
  }
  return map[type] ?? 'info'
}
function issuesOf(rowId: string) {
  return rowValidations.value.get(rowId) ?? []
}
function issueCount(rowId: string) {
  return issuesOf(rowId).filter(i => i.level !== 'info').length || issuesOf(rowId).length
}
function scheduleOf(rowId: string) {
  return getPaymentSchedule(rowId)
}

function onCell(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }

function onPickContract(rowId: string, contractNo: string) {
  const hit = h82Contracts.value.find(c => c.contractNo === contractNo)
  if (hit) {
    const res = pullFromH82(rowId, contractNo)
    if (!res.ok) ElMessage.warning(res.message)
    else ElMessage.success(res.message)
  } else {
    onCell(rowId, 'contractNo', contractNo)
  }
}

function onSummaryRowClick(row: H8LeaseModificationRow) {
  if (!expandedIds.value.includes(row.rowId)) {
    expandedIds.value = [...expandedIds.value, row.rowId]
  }
}

function patchCustomPayment(rowId: string, index: number, field: 'amount' | 'periods', value: number | undefined) {
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return
  const next = row.customPayments.map((p, i) =>
    i === index ? { ...p, [field]: Number(value) || 0 } : { ...p },
  )
  updateCell(rowId, 'customPayments', next)
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号（可稍后从 H8-2 选择）', '新增租赁变更', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：ZL-2024-001',
  })
  if (value) addRow(value)
}
function handleDelete(rowId: string) { deleteRow(rowId) }

function handlePullH82(rowId: string) {
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row?.contractNo) {
    ElMessage.warning('请先选择或填写合同号')
    return
  }
  const res = pullFromH82(rowId, row.contractNo)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleEstH86(rowId: string) {
  const res = estimateLiabilityFromH86(rowId)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleSyncH82() {
  const res = syncAdjustmentsToH82()
  if (res.updated > 0) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}

function handleCreateSep(rowId: string) {
  const res = createSeparateLeaseOnH82(rowId)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}
</script>

<style scoped>
.h8-tab-lease-modification { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.audit-note-card, .audit-conclusion-card, .summary-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }
.summary-header { display: flex; align-items: center; justify-content: space-between; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}
.methodology-context p { margin: 0; }

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.nav-chip { cursor: pointer; }
.nav-chip:hover { opacity: 0.85; }
.stats-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.stats-actions { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; }
.empty-state { padding: 40px 0; }

.mod-collapse { margin-bottom: 16px; border: none; }
.collapse-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.contract-label { font-weight: 600; }
.mod-card-body { padding: 4px 0 8px; }

.validation-box {
  margin-bottom: 10px; padding: 8px 10px; border-radius: 6px;
  background: #fffbeb; border: 1px solid #fde68a;
}
.validation-item { font-size: 12px; margin-bottom: 4px; }
.validation-item:last-child { margin-bottom: 0; }
.validation-item.error { color: #b91c1c; }
.validation-item.warning { color: #b45309; }
.validation-item.info { color: #1d4ed8; }

.section-block {
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  padding: 12px; margin-bottom: 12px;
}
.section-block.muted { opacity: 0.55; }
.section-title { font-weight: 600; margin-bottom: 10px; font-size: 13px; }

.option-section {
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  padding: 10px 12px; margin-bottom: 10px; background: #fafafa;
}
.option-section.active { background: #f0f9ff; border-color: #93c5fd; }
.option-section.muted { opacity: 0.5; pointer-events: none; }
.option-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.option-title { font-weight: 600; }

.judgment-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px; margin-bottom: 8px; flex-wrap: wrap;
}
.judgment-label { flex: 1; min-width: 180px; line-height: 1.5; }

.type-override { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.override-label { font-size: 12px; color: var(--el-text-color-secondary); }

.mod-form { margin-bottom: 4px; }
.inline-tag { margin-left: 6px; }
.hint { margin-left: 6px; font-size: 12px; color: var(--el-text-color-secondary); }

.schedule-toolbar { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
.schedule-table { margin-top: 6px; }
.schedule-total { margin-top: 6px; font-size: 12px; color: var(--el-color-primary); }

.calc-result { background: #f0f9ff; border-radius: 6px; padding: 10px 14px; margin-top: 8px; }
.formula-display { font-size: var(--wp-font-size, 13px); color: var(--el-color-primary); line-height: 1.7; }

.mod-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; color: #409eff; }
.stat-bar { padding: 10px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
