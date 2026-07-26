<template>
<div class="d3-detail">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表按债权人（对方单位）逐户列示预付账款（科目1123）明细，填列期初/发生额/期末及三期账龄。</p>
      <p>2. 灰色底纹列为自动计算列（期初审定H / 期末余额O / 期末未审Q / 期末审定X），不可手工编辑。</p>
      <p>3. 期末余额 O = 期初审定 H + 借方发生 M − 贷方发生 N（借方科目）；账龄各段之和须等于对应余额（见账龄逻辑校验行）。</p>
      <p>4. 账龄段支持「3年段 / 5年段 / 自定义」枚举切换（与 F1-1 审定表口径一致）；可用行内「账龄分配」按枚举档位将余额整笔填入。</p>
      <p>5. 账龄超过1年的长期挂账应转入 F1-5 检查，关联方预付款需在 F1-6 单独列示并关注商业实质。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核实预付账款期末余额的存在与准确，确认账龄划分与款项性质恰当，识别长期挂账、关联方预付及减值迹象。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-input v-model="searchQuery" size="small" placeholder="搜索债权人名称..." clearable style="width: 220px" />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
      <span class="muted">账龄口径</span>
      <el-select
        :model-value="agingPreset"
        size="small"
        style="width: 110px"
        :disabled="isReadonly"
        @change="onAgingPresetChange"
      >
        <el-option label="3年段" value="THREE_YEAR" />
        <el-option label="5年段" value="FIVE_YEAR" />
        <el-option label="自定义" value="CUSTOM" />
      </el-select>
    </div>
    <el-dialog v-model="showCustomDialog" title="自定义账龄段" width="420px" destroy-on-close>
      <p class="muted">每行一个段名，至少 2 段、最多 10 段。</p>
      <el-input v-model="customInput" type="textarea" :rows="8" placeholder="1年以内&#10;1-2年&#10;2-3年&#10;3年以上" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>
    <div class="toolbar-right">
      <el-popover placement="bottom-end" :width="280" trigger="click">
        <template #reference>
          <el-button size="small">⚙ 列设置</el-button>
        </template>
        <div class="f1-col-prefs">
          <div class="prefs-presets">
            <el-button
              v-for="p in presetOptions"
              :key="p.name"
              size="small"
              :type="activePreset === p.name ? 'primary' : 'default'"
              @click="applyPreset(p.name)"
            >{{ p.label }}</el-button>
          </div>
          <el-divider style="margin: 8px 0" />
          <div v-for="g in allGroups" :key="g" class="prefs-row">
            <el-checkbox
              :model-value="isGroupVisible(g)"
              @change="(v: boolean | string | number) => toggleGroup(g, !!v)"
            >{{ groupLabels[g] }}</el-checkbox>
          </div>
        </div>
      </el-popover>
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('F1-2')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('F1-2')">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload
                :show-file-list="false"
                accept=".xlsx"
                :disabled="isReadonly || importing"
                :before-upload="(file: any) => handleImport(file, 'F1-2')"
              >
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:F1-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>
  </div>

  <F1SheetAttachments
    :project-id="projectId"
    :wp-id="wpId"
    sheet-code="F1-2"
    label="明细表附件"
  />

  <!-- 宽表：对齐 Excel F1-2 列序 -->
  <el-table
    :data="displayRows"
    size="small"
    border
    stripe
    :height="tableHeight"
    style="width: 100%"
    :row-class-name="rowClassName"
  >
    <!-- A: 债权人名称 -->
    <el-table-column prop="customerName" label="债权人名称" width="140" fixed>
      <template #default="{ row }">
        <template v-if="isMetaRow(row)">
          <span class="subtotal-label">{{ row.customerName }}</span>
        </template>
        <el-input v-else v-model="row.customerName" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'customerName', val)" />
      </template>
    </el-table-column>
    <!-- B: 公司代码 -->
    <el-table-column prop="companyCode" label="公司代码" width="90" fixed>
      <template #default="{ row }">
        <el-input v-if="isDataRow(row)"
          v-model="row.companyCode" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'companyCode', val)" />
      </template>
    </el-table-column>
    <!-- C: 关联方类型（Excel 在款项性质前） -->
    <el-table-column label="关联方类型" width="120">
      <template #default="{ row }">
        <el-select v-if="isDataRow(row)" v-model="row.relationType" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'relationType', val)">
          <el-option value="非关联方" />
          <el-option value="母公司" />
          <el-option value="子公司" />
          <el-option value="联营企业" />
          <el-option value="合营企业" />
          <el-option value="其他关联方" />
        </el-select>
      </template>
    </el-table-column>
    <!-- D: 款项性质 -->
    <el-table-column label="款项性质" width="120">
      <template #default="{ row }">
        <el-select v-if="isDataRow(row)" v-model="row.nature" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'nature', val)">
          <el-option v-for="opt in F1_PAYMENT_NATURE_OPTIONS" :key="opt" :value="opt" :label="opt" />
        </el-select>
      </template>
    </el-table-column>
    <!-- E: 期初未审 -->
    <el-table-column v-if="isGroupVisible('prior')" label="期初未审" width="110" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorUnadjusted" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorUnadjusted', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.priorUnadjusted) }}</span>
      </template>
    </el-table-column>
    <!-- F: 期初账项调整 -->
    <el-table-column v-if="isGroupVisible('prior')" label="期初账项调整" width="110" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorAdjustment" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorAdjustment', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.priorAdjustment) }}</span>
      </template>
    </el-table-column>
    <!-- G: 期初重分类 -->
    <el-table-column v-if="isGroupVisible('prior')" label="期初重分类调整" width="120" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorReclass" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorReclass', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.priorReclass) }}</span>
      </template>
    </el-table-column>
    <!-- H: 期初审定 -->
    <el-table-column v-if="isGroupVisible('prior')" label="期初审定数" width="110" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span v-if="isAmountFooter(row) || isDataRow(row)" class="auto-calc amt">{{ fmtAmount(row.priorAudited) }}</span>
        <span v-else-if="row.rowId === '__aging_check__'" :class="boolClass(row.priorAudited)">{{ boolLabel(row.priorAudited) }}</span>
      </template>
    </el-table-column>
    <!-- 期初审定账龄 -->
    <template v-if="isGroupVisible('priorAging')">
      <el-table-column v-for="band in bands" :key="'prior-' + band.key" :label="`${band.label}(期初)`" width="100" align="right">
        <template #default="{ row }">
          <template v-if="isDataRow(row)">
            <el-input v-model.number="row.agingPrior[band.key]" size="small" :disabled="isReadonly"
              @change="(val: any) => onCellChange(row.rowId, `agingPrior.${band.key}`, val)" />
          </template>
          <span v-else-if="row.rowId === '__aging_pct__'" class="amt pct">{{ fmtPct(row.agingPrior?.[band.key]) }}</span>
          <span v-else-if="row.rowId === '__aging_check__'" :class="boolClass(row.agingPrior?.[band.key])">{{ boolLabel(row.agingPrior?.[band.key]) }}</span>
          <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.agingPrior?.[band.key]) }}</span>
        </template>
      </el-table-column>
    </template>
    <!-- M: 借方发生 -->
    <el-table-column v-if="isGroupVisible('movement')" label="借方发生" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.debit" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'debit', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.debit) }}</span>
      </template>
    </el-table-column>
    <!-- N: 贷方发生 -->
    <el-table-column v-if="isGroupVisible('movement')" label="贷方发生" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.credit" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'credit', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.credit) }}</span>
      </template>
    </el-table-column>
    <!-- O: 期末余额 -->
    <el-table-column v-if="isGroupVisible('movement')" label="期末余额" width="110" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span v-if="isAmountFooter(row) || isDataRow(row)" class="auto-calc amt">{{ fmtAmount(row.endBalance) }}</span>
      </template>
    </el-table-column>
    <!-- P: 被审计单位重分类 -->
    <el-table-column v-if="isGroupVisible('current')" label="被审计单位重分类调整" width="140" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.entityReclass" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'entityReclass', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.entityReclass) }}</span>
      </template>
    </el-table-column>
    <!-- Q: 期末未审 -->
    <el-table-column v-if="isGroupVisible('current')" label="期末未审余额" width="120" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span v-if="isAmountFooter(row) || isDataRow(row)" class="auto-calc amt">{{ fmtAmount(row.endUnadjusted) }}</span>
        <span v-else-if="row.rowId === '__aging_check__'" :class="boolClass(row.endUnadjusted)">{{ boolLabel(row.endUnadjusted) }}</span>
      </template>
    </el-table-column>
    <!-- 期末未审账龄 -->
    <template v-if="isGroupVisible('currentAging')">
      <el-table-column v-for="band in bands" :key="'current-' + band.key" :label="`${band.label}(期末未审)`" width="110" align="right">
        <template #default="{ row }">
          <template v-if="isDataRow(row)">
            <el-input v-model.number="row.agingCurrent[band.key]" size="small" :disabled="isReadonly"
              @change="(val: any) => onCellChange(row.rowId, `agingCurrent.${band.key}`, val)" />
          </template>
          <span v-else-if="row.rowId === '__aging_pct__'" class="amt pct">{{ fmtPct(row.agingCurrent?.[band.key]) }}</span>
          <span v-else-if="row.rowId === '__aging_check__'" :class="boolClass(row.agingCurrent?.[band.key])">{{ boolLabel(row.agingCurrent?.[band.key]) }}</span>
          <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.agingCurrent?.[band.key]) }}</span>
        </template>
      </el-table-column>
    </template>
    <!-- V: 账项调整 -->
    <el-table-column v-if="isGroupVisible('adjust')" label="账项调整" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.endAje" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'endAje', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.endAje) }}</span>
      </template>
    </el-table-column>
    <!-- W: 重分类调整 -->
    <el-table-column v-if="isGroupVisible('adjust')" label="重分类调整" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.endRje" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'endRje', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.endRje) }}</span>
      </template>
    </el-table-column>
    <!-- X: 审定数 -->
    <el-table-column v-if="isGroupVisible('audited')" label="审定数" width="110" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span v-if="isAmountFooter(row) || isDataRow(row)" class="auto-calc amt">{{ fmtAmount(row.endAudited) }}</span>
        <span v-else-if="row.rowId === '__aging_check__'" :class="boolClass(row.endAudited)">{{ boolLabel(row.endAudited) }}</span>
      </template>
    </el-table-column>
    <!-- 期末审定账龄 -->
    <template v-if="isGroupVisible('auditedAging')">
      <el-table-column v-for="band in bands" :key="'audited-' + band.key" :label="`${band.label}(期末审定)`" width="110" align="right">
        <template #default="{ row }">
          <template v-if="isDataRow(row)">
            <el-input v-model.number="row.agingAudited[band.key]" size="small" :disabled="isReadonly"
              @change="(val: any) => onCellChange(row.rowId, `agingAudited.${band.key}`, val)" />
          </template>
          <span v-else-if="row.rowId === '__aging_pct__'" class="amt pct">{{ fmtPct(row.agingAudited?.[band.key]) }}</span>
          <span v-else-if="row.rowId === '__aging_check__'" :class="boolClass(row.agingAudited?.[band.key])">{{ boolLabel(row.agingAudited?.[band.key]) }}</span>
          <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.agingAudited?.[band.key]) }}</span>
        </template>
      </el-table-column>
    </template>
    <!-- AC: 是否函证 -->
    <el-table-column v-if="isGroupVisible('meta')" label="是否函证" width="90" align="center">
      <template #default="{ row }">
        <el-select v-if="isDataRow(row)" v-model="row.isConfirmed" size="small" :disabled="isReadonly" clearable
          @change="(val: string) => onCellChange(row.rowId, 'isConfirmed', val || '')">
          <el-option value="Y" label="是" />
          <el-option value="N" label="否" />
        </el-select>
      </template>
    </el-table-column>
    <!-- AD: 期后回款 -->
    <el-table-column v-if="isGroupVisible('meta')" label="期后回款" width="110" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.postPeriodSettlement" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'postPeriodSettlement', val)" />
        </template>
        <span v-else-if="isAmountFooter(row)" class="amt">{{ fmtAmount(row.postPeriodSettlement) }}</span>
      </template>
    </el-table-column>
    <!-- AE: 备注 -->
    <el-table-column v-if="isGroupVisible('meta')" label="备注" min-width="120">
      <template #default="{ row }">
        <el-input v-if="isDataRow(row)" v-model="row.remark" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'remark', val)" />
      </template>
    </el-table-column>
    <!-- 操作列 -->
    <el-table-column label="操作" width="150" fixed="right" v-if="!isReadonly">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-dropdown
            size="small"
            trigger="click"
            @command="(cmd: string) => handleAgingCommand(row.rowId, cmd)"
          >
            <el-button link type="primary" size="small">账龄分配▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>按期初审定分配</el-dropdown-item>
                <el-dropdown-item
                  v-for="band in bands"
                  :key="`p-${band.key}`"
                  :command="`prior:${band.key}`"
                >{{ band.label }}</el-dropdown-item>
                <el-dropdown-item divided disabled>按期末未审分配</el-dropdown-item>
                <el-dropdown-item
                  v-for="band in bands"
                  :key="`c-${band.key}`"
                  :command="`current:${band.key}`"
                >{{ band.label }}</el-dropdown-item>
                <el-dropdown-item divided disabled>按期末审定分配</el-dropdown-item>
                <el-dropdown-item
                  v-for="band in bands"
                  :key="`a-${band.key}`"
                  :command="`audited:${band.key}`"
                >{{ band.label }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-popconfirm title="确认删除此行？" @confirm="removeRow(row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </template>
    </el-table-column>
  </el-table>

  <!-- F1-7期后结转联动提示 -->
  <el-alert
    v-if="postPeriodLinkageWarning"
    :title="postPeriodLinkageWarning"
    type="warning"
    :closable="false"
    show-icon
    style="margin: 12px 0"
  />

  <!-- 审计说明（对齐 Excel 三问 + 结论） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">三、审计说明</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
          <GtIndexChip value="wp:F1-5" :context-project-id="projectId" />
          <GtIndexChip value="wp:F1-6" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">(1) 期初余额与上年报核对说明</span>
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genNotePrior">🤖AI</el-button>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="核对期初审定余额与上年审计报告/附注披露是否勾稽一致，说明差异原因..."
        v-model="auditNote1" />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">(2) 预付账款重大变动原因分析</span>
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genNoteFluctuation">🤖AI</el-button>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="分析本期预付账款重大增减变动的主要原因（供应商、项目、款项性质等）..."
        v-model="auditNote2" />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">(3) 账龄超过1年的预付款性质及未结转原因</span>
        <div class="opinion-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genNoteOver1">🤖AI</el-button>
          <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
        </div>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="说明账龄超过1年的预付款款项性质、未结转/未收回原因及后续处理计划..."
        v-model="auditNote3" />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">四、审计结论</span>
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genConclusion">🤖AI</el-button>
      </div>
      <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        v-model="auditConclusion" />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabDetail.vue — F1-2 预付账款明细表
 * 对齐 Excel：三期账龄、借方科目公式、账龄占比/校验、审计说明 AI
 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import { useF1Detail } from '../composables/useF1Detail'
import { useF1DetailColumnPrefs } from '../composables/useF1DetailColumnPrefs'
import { F1_PAYMENT_NATURE_OPTIONS } from '../composables/useF1Adjudication'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import { useF1AiGenerate } from '../composables/useF1AiGenerate'
import { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore - GtIndexChip may not have type declarations
import GtIndexChip from '../GtIndexChip.vue'
import F1SheetAttachments from './F1SheetAttachments.vue'
import type { F1AgingScope } from '../composables/useF1AgingScope'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** F1 账龄口径单一真源（主入口注入；未传则内部自建，兼容单独挂载） */
  agingScope?: F1AgingScope
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>

const {
  activePreset,
  presetOptions,
  allGroups,
  groupLabels,
  isGroupVisible,
  toggleGroup,
  applyPreset,
} = useF1DetailColumnPrefs()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const relatedParties = ref<string[]>([])

const NOTE1_KEY = 'F1-det-note-prior-linkage'
const NOTE2_KEY = 'F1-det-note-fluctuation'
const NOTE3_KEY = 'F1-det-note-over1year'
const CONCLUSION_KEY = 'F1-detail-audit-conclusion'

const auditNote1 = ref('')
const auditNote2 = ref('')
const auditNote3 = ref('')
const auditConclusion = ref('')

watch(
  () => [
    allResponsesRef.value.get(NOTE1_KEY)?.remark,
    allResponsesRef.value.get(NOTE2_KEY)?.remark,
    allResponsesRef.value.get(NOTE3_KEY)?.remark,
    allResponsesRef.value.get(CONCLUSION_KEY)?.remark,
  ],
  ([n1, n2, n3, c]) => {
    auditNote1.value = n1 || ''
    auditNote2.value = n2 || ''
    auditNote3.value = n3 || ''
    auditConclusion.value = c || ''
  },
  { immediate: true },
)

watch(auditNote1, (val) => { if (!props.isReadonly) props.debouncedSave(NOTE1_KEY, { remark: val }) })
watch(auditNote2, (val) => { if (!props.isReadonly) props.debouncedSave(NOTE2_KEY, { remark: val }) })
watch(auditNote3, (val) => { if (!props.isReadonly) props.debouncedSave(NOTE3_KEY, { remark: val }) })
watch(auditConclusion, (val) => { if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { remark: val }) })

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(wpIdRef)

const {
  rows,
  filteredRows,
  subtotalRow,
  verificationRow,
  agingPctRow,
  agingCheckRow,
  searchQuery,
  bands,
  agingPreset,
  customSegments,
  setAgingPreset,
  allocateAging,
  addRow,
  removeRow,
  updateCell,
  importFromAuxBalance,
} = useF1Detail({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  relatedParties,
  agingScope: props.agingScope,
})

const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<'THREE_YEAR' | 'FIVE_YEAR'>(
  agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : (agingPreset.value as 'THREE_YEAR' | 'FIVE_YEAR'),
)

function onAgingPresetChange(val: string) {
  if (val === 'CUSTOM') {
    customInput.value = customSegments.value.length
      ? customSegments.value.map((s) => s.label).join('\n')
      : '1年以内\n1-2年\n2-3年\n3年以上'
    showCustomDialog.value = true
    return
  }
  if (val === 'THREE_YEAR' || val === 'FIVE_YEAR') {
    lastNonCustomPreset.value = val
    setAgingPreset(val)
  }
}

function confirmCustomAging() {
  const lines = customInput.value
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  if (lines.length < 2) return
  if (!setAgingPreset('CUSTOM', lines.slice(0, 10))) return
  showCustomDialog.value = false
}

function cancelCustomAging() {
  showCustomDialog.value = false
  if (!customSegments.value.length && agingPreset.value === 'CUSTOM') {
    setAgingPreset(lastNonCustomPreset.value)
  }
}

function handleAgingCommand(rowId: string, command: string): void {
  const [stage, key] = command.split(':')
  if ((stage === 'prior' || stage === 'current' || stage === 'audited') && key) {
    allocateAging(rowId, stage, key)
  }
}

const crossSheet = useF1CrossSheet({ allResponses: allResponsesRef })

const postPeriodLinkageWarning = computed(() => {
  const sync = crossSheet.postPeriodSettlementSync.value
  if (sync.total === 0) return ''
  const mismatched: string[] = []
  for (const [customer, d7Amount] of Object.entries(sync.byCustomer)) {
    if (d7Amount <= 0) continue
    const detailRow = rows.value.find(r => r.customerName === customer)
    if (detailRow && (!detailRow.postPeriodSettlement || detailRow.postPeriodSettlement === 0)) {
      mismatched.push(customer)
    }
  }
  if (mismatched.length === 0) return ''
  return `F1-7期后结转检查中发现 ${mismatched.length} 个客户有贷方金额（合计 ${sync.total.toLocaleString()} 元），但F1-2期后回款列为空：${mismatched.slice(0, 3).join('、')}${mismatched.length > 3 ? '等' : ''}`
})

const tableHeight = computed(() => filteredRows.value.length > 30 ? '600px' : undefined)

const displayRows = computed(() => [
  ...filteredRows.value,
  subtotalRow.value,
  agingPctRow.value,
  agingCheckRow.value,
  verificationRow.value,
])

function isDataRow(row: any): boolean {
  return !String(row.rowId || '').startsWith('__')
}

function isMetaRow(row: any): boolean {
  return String(row.rowId || '').startsWith('__')
}

function isAmountFooter(row: any): boolean {
  return row.rowId === '__subtotal__' || row.rowId === '__verification__'
}

function rowClassName({ row }: { row: any }): string {
  if (row.rowId === '__subtotal__') return 'subtotal-row'
  if (row.rowId === '__verification__') return 'verification-row'
  if (row.rowId === '__aging_pct__') return 'aging-pct-row'
  if (row.rowId === '__aging_check__') return 'aging-check-row'
  if (row.relationType && row.relationType !== '非关联方') return 'related-party-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || !isFinite(val)) return '-'
  if (val === 0) return '-'
  return `${val.toFixed(2)}%`
}

function boolLabel(val: number | null | undefined): string {
  return Number(val) === 1 ? 'TRUE' : 'FALSE'
}

function boolClass(val: number | null | undefined): string {
  return Number(val) === 1 ? 'check-ok' : 'check-fail'
}

function openReview() {
  openReviewDialog?.('F1-det-notes')
}

function noteContext() {
  const sub = subtotalRow.value
  return {
    rowCount: rows.value.length,
    priorAudited: sub.priorAudited,
    endAudited: sub.endAudited,
    endUnadjusted: sub.endUnadjusted,
    debit: sub.debit,
    credit: sub.credit,
    topCustomers: rows.value
      .slice()
      .sort((a, b) => Math.abs(b.endAudited) - Math.abs(a.endAudited))
      .slice(0, 5)
      .map(r => `${r.customerName}:${r.endAudited}`)
      .join('; '),
  }
}

async function genNotePrior() {
  const text = await generateAndConfirm('detail-prior-linkage', auditNote1.value, noteContext(), '期初核对说明')
  if (text) auditNote1.value = text
}

async function genNoteFluctuation() {
  const text = await generateAndConfirm('detail-fluctuation', auditNote2.value, noteContext(), '重大变动分析')
  if (text) auditNote2.value = text
}

async function genNoteOver1() {
  const text = await generateAndConfirm('detail-over1year', auditNote3.value, noteContext(), '超1年预付款说明')
  if (text) auditNote3.value = text
}

async function genConclusion() {
  const text = await generateAndConfirm('detail-conclusion', auditConclusion.value, noteContext(), '审计结论')
  if (text) auditConclusion.value = text
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: wpIdRef })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-detail { padding: 16px; }
.d3-detail :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.d3-detail :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.muted { font-size: 12px; color: #909399; white-space: nowrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.subtotal-label { font-weight: 700; }
.amt { text-align: right; display: inline-block; width: 100%; }
.pct { color: #606266; }
.auto-calc { color: #909399; }
.check-ok { color: #67c23a; font-weight: 600; }
.check-fail { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.verification-row) { background-color: #fff8e1 !important; }
:deep(.aging-pct-row) { background-color: #f0f9eb !important; }
:deep(.aging-check-row) { background-color: #fef0f0 !important; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
