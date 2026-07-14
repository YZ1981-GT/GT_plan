<template>
<div class="d6-tab-detail">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表列示合同资产（科目1402）明细，按合同类型归集，依 CAS14 收入准则确认——已履约但收款权取决于时间以外因素的部分列示为合同资产。</p>
      <p>2. 灰色底纹列为自动计算列（期初审定/期末未审/期末审定），不可手工编辑；数字列右对齐。</p>
      <p>3. 支持从余额表一键导入，并可切换"含账龄"列组查看期初/期末账龄分布，为 D6-8 ECL 组合计提提供依据。</p>
      <p>4. 各合同类型自动生成小计行、全表生成合计行，请与 D6-1 审定表按类型聚合核对一致。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核实合同资产各明细项目期末余额的存在与准确，确认合同类型分类与账龄划分的恰当性，为审定表聚合及减值测算提供依据。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-input
        v-model="searchFilter"
        placeholder="搜索合同名称/客户名称..."
        size="small"
        style="width:220px"
        clearable
      />
      <el-segmented v-model="columnGroup" :options="columnGroupOptions" size="small" />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加明细行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
      <GtReviewTrigger section-id="D6-2-header" />
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload
                :show-file-list="false"
                accept=".xlsx"
                :auto-upload="false"
                :disabled="isReadonly || importing"
                @change="(f: any) => onImportFile(f.raw || f)"
              >
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-popover trigger="click" :width="260" placement="bottom-end">
        <template #reference>
          <el-button size="small" circle><el-icon><Setting /></el-icon></el-button>
        </template>
        <div class="col-prefs-popover">
          <div class="col-prefs-header">
            <span>列显示设置</span>
            <el-button size="small" text type="primary" @click="resetDefaults">重置默认</el-button>
          </div>
          <div v-for="group in columnGroups" :key="group.label" class="col-prefs-group">
            <div class="col-prefs-group-label">{{ group.label }}</div>
            <div v-for="key in group.keys" :key="key" class="col-prefs-item">
              <el-checkbox
                :model-value="isColVisible(key)"
                :disabled="group.alwaysShow"
                size="small"
                @change="toggleCol(key)"
              >{{ getColLabel(key) }}</el-checkbox>
            </div>
          </div>
        </div>
      </el-popover>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ filteredRows.length }} 行</el-tag>
    </div>
  </div>

  <div v-if="useVirtualScroll" class="virtual-toolbar">
    <el-alert type="info" :closable="false" class="virtual-hint">
      行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
    </el-alert>
    <el-button size="small" @click="toggleBrowseMode">
      {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
    </el-button>
  </div>
  <el-table-v2
    v-if="useVirtualScroll && browseMode"
    :columns="virtualColumns"
    :data="browseRows"
    :width="tableWidth"
    :height="tableHeight"
    :row-height="36"
    :header-height="40"
    :row-event-handlers="rowEventHandlers"
    fixed
    class="virtual-table"
  />

  <div v-if="!useVirtualScroll || !browseMode">
    <el-table
      :data="displayRows"
      size="small"
      border
      stripe
      max-height="600"
      style="width:100%"
    >
      <el-table-column label="序号" width="60" fixed align="center">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal">{{ row.seqNo }}</span>
        </template>
      </el-table-column>

      <el-table-column label="合同名称" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.contractName }}</span>
          </template>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.contractName"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'contractName', v)"
          />
          <span v-else>{{ row.contractName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类型" width="120" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.contractType }}</span>
          </template>
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.contractType"
            size="small"
            placeholder="选择类型"
            @change="(v: string) => updateCell(row.rowId, 'contractType', v)"
          >
            <el-option v-for="t in CONTRACT_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.contractType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="客户名称" width="140" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.customerName"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'customerName', v)"
          />
          <span v-else>{{ row.customerName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="公司代码" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.companyCode"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'companyCode', v)"
          />
          <span v-else>{{ row.companyCode }}</span>
        </template>
      </el-table-column>

      <el-table-column label="关联关系" width="140">
        <template #default="{ row }">
          <el-select
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.relatedPartyType"
            size="small"
            placeholder="选择"
            @change="(v: string) => updateCell(row.rowId, 'relatedPartyType', v)"
          >
            <el-option v-for="t in RELATED_PARTY_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.relatedPartyType }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('priorUnadjusted')" label="期初未审" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorUnadjusted"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('priorAje')" label="期初AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'priorAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('priorRje')" label="期初RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'priorRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorRje) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('priorAudited')" label="期初审定" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
        </template>
      </el-table-column>

      <template v-if="showAgingCols && isColVisible('aging1y')">
        <el-table-column label="期初≤1年" width="100" align="right">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior1y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior1y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior1y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior1y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初1~2年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior1to2y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior1to2y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior1to2y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior1to2y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初2~3年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior2to3y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior2to3y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior2to3y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior2to3y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初3年+" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior3yAbove) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior3yAbove"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior3yAbove', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior3yAbove) }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="isColVisible('debitAmount')" label="借方发生" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.debitAmount) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.debitAmount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('creditAmount')" label="贷方发生" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.creditAmount) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.creditAmount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('endUnadjusted')" label="期末未审" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endUnadjusted) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('endAje')" label="期末AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'endAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endAje) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('endRje')" label="期末RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'endRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endRje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末审定" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endAudited) }}</span>
        </template>
      </el-table-column>

      <template v-if="showAgingCols && isColVisible('aging1y')">
        <el-table-column label="期末≤1年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd1y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd1y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd1y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd1y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末1~2年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd1to2y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd1to2y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd1to2y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd1to2y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末2~3年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd2to3y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd2to3y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd2to3y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd2to3y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末3年+" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd3yAbove) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd3yAbove"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd3yAbove', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd3yAbove) }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="1年以内收款权" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.receivableWithin1y) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.receivableWithin1y"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'receivableWithin1y', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.receivableWithin1y) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="1年以上收款权" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.receivableAbove1y) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.receivableAbove1y"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'receivableAbove1y', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.receivableAbove1y) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="建设期/质保期" width="110" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.isInConstructionPeriod"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'isInConstructionPeriod', v)"
          >
            <el-option v-for="o in CONSTRUCTION_PERIOD_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.isInConstructionPeriod || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="信用风险组合" width="120">
        <template #default="{ row }">
          <el-select
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.creditRiskGroup"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'creditRiskGroup', v)"
          >
            <el-option v-for="g in CREDIT_RISK_GROUPS" :key="g" :label="g" :value="g" />
          </el-select>
          <span v-else>{{ row.creditRiskGroup }}</span>
        </template>
      </el-table-column>

      <el-table-column label="是否函证" width="80" align="center">
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.isConfirmed"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'isConfirmed', v)"
          />
          <span v-else>{{ row.isConfirmed || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('postPeriodSettlement')" label="期后结转" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.postPeriodSettlement) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.postPeriodSettlement"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'postPeriodSettlement', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.postPeriodSettlement) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            v-if="!row._isSubtotal && !row._isTotal"
            type="danger"
            text
            size="small"
            @click="removeRow(row.rowId)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-1" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计说明</span>
        <div class="opinion-actions">
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoading"
              :disabled="isReadonly || !aiAvailable" @click="genDetailChange">🤖 AI辅助</el-button>
          </el-tooltip>
          <GtReviewTrigger section-id="D6-2-note-explanation" label="💬 复核" />
        </div>
      </div>
      <el-input
        v-model="auditExplanation"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 7 }"
        :disabled="isReadonly"
        placeholder="对合同资产明细本期变动的分析说明..."
      />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabDetail.vue — 明细表 D6-2（30列69公式）
 */
import { ref, computed, inject, watch, toRef, type Ref } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import {
  useD6Detail,
  CONTRACT_TYPES,
  RELATED_PARTY_TYPES,
  CREDIT_RISK_GROUPS,
  CONSTRUCTION_PERIOD_OPTIONS,
  type DetailRow,
} from '../composables/useD6Detail'
import type { ChecklistResponse } from '../composables/useD6FormData'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useD6AiGenerate } from '../composables/useD6AiGenerate'
import { useD6DetailColumnPrefs } from '../composables/useD6DetailColumnPrefs'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import { calcSubtotal } from '../composables/useD6FormulaEngine'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtReviewTrigger from '../GtReviewTrigger.vue'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Column Preferences ──────────────────────────────────────────────────────
const { columnGroups, isColVisible, toggleCol, resetDefaults } = useD6DetailColumnPrefs()

const COL_LABELS: Record<string, string> = {
  seqNo: '序号', contractType: '合同类型', customerName: '客户名称',
  contractName: '合同名称', endAudited: '期末审定', remark: '备注',
  priorUnadjusted: '期初未审', priorAje: '期初AJE', priorRje: '期初RJE',
  priorAudited: '期初审定', debitAmount: '借方发生', creditAmount: '贷方发生',
  endUnadjusted: '期末未审', endAje: '期末AJE', endRje: '期末RJE',
  aging1y: '≤1年', aging1to2: '1~2年', aging2to3: '2~3年', aging3plus: '3年以上',
  postPeriodSettlement: '期后结转', postPeriodDate: '期后日期',
}
function getColLabel(key: string): string { return COL_LABELS[key] || key }

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-2',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
}

type ColumnGroup = 'basic' | 'full'
const columnGroup = ref<ColumnGroup>('basic')
const columnGroupOptions = [
  { label: '基本列', value: 'basic' as const },
  { label: '含账龄', value: 'full' as const },
]
const showAgingCols = computed(() => columnGroup.value === 'full')

const {
  addRow,
  removeRow,
  updateCell,
  importFromAuxBalance,
  searchFilter,
  filteredRows,
} = useD6Detail({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

interface DisplayRow extends DetailRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
}

function sumDisplayRows(rows: DetailRow[], label: string, flags: { _isSubtotal?: boolean; _isTotal?: boolean }): DisplayRow {
  return {
    rowId: `__${label}__`,
    seqNo: 0,
    contractName: label,
    contractType: label,
    customerName: '',
    companyCode: '',
    relatedPartyType: '',
    priorUnadjusted: calcSubtotal(rows.map(r => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map(r => r.priorAje)),
    priorRje: calcSubtotal(rows.map(r => r.priorRje)),
    priorAudited: calcSubtotal(rows.map(r => r.priorAudited)),
    agePrior1y: calcSubtotal(rows.map(r => r.agePrior1y)),
    agePrior1to2y: calcSubtotal(rows.map(r => r.agePrior1to2y)),
    agePrior2to3y: calcSubtotal(rows.map(r => r.agePrior2to3y)),
    agePrior3yAbove: calcSubtotal(rows.map(r => r.agePrior3yAbove)),
    debitAmount: calcSubtotal(rows.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(rows.map(r => r.creditAmount)),
    endUnadjusted: calcSubtotal(rows.map(r => r.endUnadjusted)),
    endAje: calcSubtotal(rows.map(r => r.endAje)),
    endRje: calcSubtotal(rows.map(r => r.endRje)),
    endAudited: calcSubtotal(rows.map(r => r.endAudited)),
    ageEnd1y: calcSubtotal(rows.map(r => r.ageEnd1y)),
    ageEnd1to2y: calcSubtotal(rows.map(r => r.ageEnd1to2y)),
    ageEnd2to3y: calcSubtotal(rows.map(r => r.ageEnd2to3y)),
    ageEnd3yAbove: calcSubtotal(rows.map(r => r.ageEnd3yAbove)),
    receivableWithin1y: calcSubtotal(rows.map(r => r.receivableWithin1y)),
    receivableAbove1y: calcSubtotal(rows.map(r => r.receivableAbove1y)),
    isInConstructionPeriod: '',
    creditRiskGroup: '',
    isConfirmed: '',
    postPeriodSettlement: calcSubtotal(rows.map(r => r.postPeriodSettlement)),
    ...flags,
  }
}

const displayRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = []
  const typeSet = new Set<string>(CONTRACT_TYPES)

  for (const cType of CONTRACT_TYPES) {
    const typeRows = filteredRows.value.filter(r => r.contractType === cType)
    if (typeRows.length > 0) {
      result.push(...typeRows.map(r => ({ ...r })))
      result.push(sumDisplayRows(typeRows, `${cType}小计`, { _isSubtotal: true }))
    }
  }

  const uncategorized = filteredRows.value.filter(r => !typeSet.has(r.contractType) || r.contractType === '')
  if (uncategorized.length > 0) {
    result.push(...uncategorized.map(r => ({ ...r })))
  }

  if (filteredRows.value.length > 0) {
    result.push(sumDisplayRows(filteredRows.value, '合计', { _isTotal: true }))
  }

  return result
})

const browseRows = filteredRows
const browseRowCount = computed(() => filteredRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('contractName', '合同名称', 150),
  virtualTextCol('customerName', '客户名称', 140),
  virtualTextCol('contractType', '类型', 120),
  virtualNumCol('endAudited', '期末审定', 110, fmtAmount),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 1400,
})

const auditExplanation = ref('')

watch(
  () => allResponsesRef.value.get('D6-2-note-explanation')?.remark,
  (val) => { auditExplanation.value = val || '' },
  { immediate: true },
)

watch(auditExplanation, (val) => {
  props.debouncedSave('D6-2-note-explanation', { remark: val })
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD6AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genDetailChange() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('detail-change', auditExplanation.value, {
    task: '合同资产明细变动分析',
    rowCount: filteredRows.value.length,
    endAuditedTotal: calcSubtotal(filteredRows.value.map(r => r.endAudited)),
  }, 'AI · 变动分析')
  if (text) auditExplanation.value = text
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d6-tab-detail { padding: 16px; }
.d6-tab-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-detail :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.virtual-hint { flex: 1; margin: 0; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.subtotal-label { font-weight: 700; }
.subtotal-amount { font-weight: 700; }

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* 列设置 popover */
.col-prefs-popover { max-height: 320px; overflow-y: auto; }
.col-prefs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
.col-prefs-group { margin-bottom: 8px; }
.col-prefs-group-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.col-prefs-item { margin-left: 8px; }
</style>
