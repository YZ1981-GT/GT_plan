<!--
  G6TabDetail.vue — G6-2 明细表（33列 → 3区段Tab）

  3区段Tab切换（el-segmented）：
  - Tab1: 基础信息(10列): 序号|投资项目|投资种类|面值|票面利率|实际利率|到期日|初始投资日|持有数量|合同条件|公允价值层次
  - Tab2: 期初+变动(12列): 序号|投资项目|期初成本|期初利息调整|期初应计利息|期初小计(公式)|期初公允价值|期初OCI累计|本期增加|本期减少|本期利息收入|本期公允价值变动|本期减值
  - Tab3: 期末+审定(11列): 序号|投资项目|期末成本|期末利息调整|期末应计利息|期末小计(公式)|期末公允价值|OCI累计|减值准备|审定调整|审定数|索引

  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  底部合计行：期初小计/增加/减少/利息/公允价值变动/期末小计
  公式列：虚线下划线+cursor:help+tooltip来源

  Spec: .kiro/specs/g6-other-bond-investment-main/ Task 5.1
  Requirements: 5.1, 5.2, 5.3
-->
<template>
  <div class="g6-detail">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认其他债权投资明细的存在与权利归属，成本/利息调整/应计利息/公允价值/减值等计价属性计算准确，分类与列报恰当，为 G6-1 审定表提供明细支撑。"
      style="margin-bottom: 12px"
    />
    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-2 其他债权投资明细表</h3>
      <div class="head-actions">
        <el-segmented v-model="activeTab" :options="segmentOptions" size="small" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 投资项目
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="opt in dropdownOptions"
                :key="opt.command"
                :command="opt.command"
                :disabled="opt.disabled"
              >{{ opt.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G6-2-detail')">💬复核</el-button>
      </div>
    </div>

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-2" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 明细表格 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="detail-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <!-- 投资项目列（始终显示作为锚定列） -->
      <el-table-column label="投资项目" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <span v-else>{{ row.investProject }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 基础信息列 ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="投资种类" min-width="100">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.investType" size="small"
                @change="(v: string) => updateField(row.id, 'investType', v)" />
              <span v-else>{{ row.investType }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="面值" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.faceValue" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'faceValue', v)" />
              <span v-else>{{ fmtNum(row.faceValue) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="票面利率" min-width="90" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.couponRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                @change="(v: number) => updateField(row.id, 'couponRate', v)" />
              <span v-else>{{ fmtPercent(row.couponRate) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="实际利率" min-width="90" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.effectiveRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                @change="(v: number) => updateField(row.id, 'effectiveRate', v)" />
              <span v-else>{{ fmtPercent(row.effectiveRate) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="到期日" min-width="110">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-date-picker v-if="!isReadonly" v-model="row.maturityDate" type="date"
                size="small" format="YYYY-MM-DD" style="width:100%" />
              <span v-else>{{ row.maturityDate || '' }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="初始投资日" min-width="110">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-date-picker v-if="!isReadonly" v-model="row.investDate" type="date"
                size="small" format="YYYY-MM-DD" style="width:100%" />
              <span v-else>{{ row.investDate || '' }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="持有数量" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.holdingQty" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'holdingQty', v)" />
              <span v-else>{{ row.holdingQty }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="合同条件" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.contractTerms" size="small"
                @change="(v: string) => updateField(row.id, 'contractTerms', v)" />
              <span v-else>{{ row.contractTerms }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="公允价值层次" min-width="120">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" :model-value="row.fvLevel" size="small" style="width:100%"
                @change="(v: string) => updateField(row.id, 'fvLevel', v)">
                <el-option value="L1" label="L1" />
                <el-option value="L2" label="L2" />
                <el-option value="L3" label="L3" />
              </el-select>
              <span v-else>{{ row.fvLevel }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 期初+变动列 ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="期初成本" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.openingCost) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingCost" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingCost', v)" />
              <span v-else>{{ fmtNum(row.openingCost) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初利息调整" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.openingInterestAdj) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingInterestAdj" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingInterestAdj', v)" />
              <span v-else>{{ fmtNum(row.openingInterestAdj) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初应计利息" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.openingAccruedInterest) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingAccruedInterest" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingAccruedInterest', v)" />
              <span v-else>{{ fmtNum(row.openingAccruedInterest) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初小计" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.openingSubtotal) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="期初小计 = 成本 + 利息调整 + 应计利息" placement="top">
                <span class="formula-cell">{{ fmtNum(row.openingSubtotal) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初公允价值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.openingFairValue) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingFairValue" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingFairValue', v)" />
              <span v-else>{{ fmtNum(row.openingFairValue) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初OCI累计" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.openingOci) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingOci" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingOci', v)" />
              <span v-else>{{ fmtNum(row.openingOci) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.increase) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.increase" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'increase', v)" />
              <span v-else>{{ fmtNum(row.increase) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.decrease) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.decrease" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'decrease', v)" />
              <span v-else>{{ fmtNum(row.decrease) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本期利息收入" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.interestIncome) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.interestIncome" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'interestIncome', v)" />
              <span v-else>{{ fmtNum(row.interestIncome) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本期公允价值变动" min-width="140" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.fvChange) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.fvChange" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'fvChange', v)" />
              <span v-else>{{ fmtNum(row.fvChange) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本期减值" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.impairment) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.impairment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'impairment', v)" />
              <span v-else>{{ fmtNum(row.impairment) }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab3: 期末+审定列 ═══ -->
      <template v-if="activeTab === 'tab3'">
        <el-table-column label="期末成本" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.closingCost) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.closingCost" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'closingCost', v)" />
              <span v-else>{{ fmtNum(row.closingCost) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末利息调整" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.closingInterestAdj) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.closingInterestAdj" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'closingInterestAdj', v)" />
              <span v-else>{{ fmtNum(row.closingInterestAdj) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末应计利息" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.closingAccruedInterest) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.closingAccruedInterest" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'closingAccruedInterest', v)" />
              <span v-else>{{ fmtNum(row.closingAccruedInterest) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末小计" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.closingSubtotal) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="期末小计 = 期初小计 + 增加 - 减少 + 利息收入" placement="top">
                <span class="formula-cell">{{ fmtNum(row.closingSubtotal) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末公允价值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.closingFairValue) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.closingFairValue" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'closingFairValue', v)" />
              <span v-else>{{ fmtNum(row.closingFairValue) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="OCI累计" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.closingOci) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.closingOci" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'closingOci', v)" />
              <span v-else>{{ fmtNum(row.closingOci) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="减值准备" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.closingImpairment) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.closingImpairment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'closingImpairment', v)" />
              <span v-else>{{ fmtNum(row.closingImpairment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="审定调整" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.auditAdjustment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'auditAdjustment', v)" />
              <span v-else>{{ fmtNum(row.auditAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="审定数" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(row.auditedAmount) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.auditedAmount" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'auditedAmount', v)" />
              <span v-else>{{ fmtNum(row.auditedAmount) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="90" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <GtIndexChip v-else :value="row.indexRef" />
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isTotal" title="确认删除？"
            @confirm="removeRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：其他债权投资明细的存在性、计价（成本/利息调整/应计利息/公允价值/减值）及分类与列报的测试情况及结果。"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述调整事项予以调整外，其余未见异常。C、存在重大未调整事项，不可确认。"
        @change="(v: string) => saveAuditConclusion(v)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>期初小计 = 期初成本 + 期初利息调整 + 期初应计利息</li>
        <li>期末小计 = 期初小计 + 本期增加 - 本期减少 + 本期利息收入</li>
        <li>公允价值层次：L1(活跃市场报价) / L2(可观察输入值) / L3(不可观察输入值)</li>
        <li>Tab3索引列可通过GtIndexChip跳转到相关底稿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDetail.vue — G6-2 其他债权投资明细表（33列→3区段Tab）
 *
 * - el-segmented 切换 Tab1(基础信息) / Tab2(期初+变动) / Tab3(期末+审定)
 * - 行共享同一reactive数组，Tab切换只改可见列
 * - selectedRowIndex跨Tab保持（行同步）
 * - 底部合计行（期初小计/增加/减少/利息/公允价值变动/期末小计）
 * - 公式列tooltip显示来源
 * - 动态行增删（ElMessageBox.prompt输入名称）
 * - 导入导出(useG6MainImportExport, sheet='G6-2')
 */
import { ref, reactive, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import {
  calcSubtotal,
  calcEndingSubtotal,
  parseNum,
} from '@/composables/useG6MainFormulaEngine'
import {
  useG6MainImportExport,
  type G6MainImportableSheet,
} from '@/components/workpaper/composables/useG6MainImportExport'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 审计说明 / 审计结论（走 checklist_responses，conclusion:null + remark 文本） ───
const NOTE_KEY = 'G6-2-detail-audit-note'
const CONCLUSION_KEY = 'G6-2-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function readSaved(key: string): string {
  const cr = props.htmlData?.checklist_responses
  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {
    const v = (cr as Record<string, any>)[key]
    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')
  }
  const resp = props.htmlData?.responses
  if (Array.isArray(resp)) {
    const found = resp.find((r: any) => r?.item_id === key)
    if (found?.remark) return found.remark
  }
  return ''
}

async function saveAudit(key: string, val: string): Promise<void> {
  if (props.isReadonly) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: key, conclusion: null, remark: val }],
    })
  } catch { /* silent */ }
}

function saveAuditNote(val: string): void {
  auditNote.value = val
  void saveAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  auditConclusion.value = val
  void saveAudit(CONCLUSION_KEY, val)
}

// ─── 区段Tab ─────────────────────────────────────────────────────────────────

const activeTab = ref<'tab1' | 'tab2' | 'tab3'>('tab1')

const segmentOptions = [
  { label: '基础信息', value: 'tab1' },
  { label: '期初+变动', value: 'tab2' },
  { label: '期末+审定', value: 'tab3' },
]

// ─── 行数据 ─────────────────────────────────────────────────────────────────

interface DetailRow {
  id: string
  seq: number
  investProject: string
  // Tab1 基础信息
  investType: string
  faceValue: number
  couponRate: number
  effectiveRate: number
  maturityDate: string
  investDate: string
  holdingQty: number
  contractTerms: string
  fvLevel: string
  // Tab2 期初+变动
  openingCost: number
  openingInterestAdj: number
  openingAccruedInterest: number
  openingSubtotal: number // 公式
  openingFairValue: number
  openingOci: number
  increase: number
  decrease: number
  interestIncome: number
  fvChange: number
  impairment: number
  // Tab3 期末+审定
  closingCost: number
  closingInterestAdj: number
  closingAccruedInterest: number
  closingSubtotal: number // 公式
  closingFairValue: number
  closingOci: number
  closingImpairment: number
  auditAdjustment: number
  auditedAmount: number
  indexRef: string
}

interface DisplayRow extends DetailRow {
  _isTotal?: boolean
}

function createEmptyRow(seq: number, name: string): DetailRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investProject: name,
    investType: '',
    faceValue: 0,
    couponRate: 0,
    effectiveRate: 0,
    maturityDate: '',
    investDate: '',
    holdingQty: 0,
    contractTerms: '',
    fvLevel: '',
    openingCost: 0,
    openingInterestAdj: 0,
    openingAccruedInterest: 0,
    openingSubtotal: 0,
    openingFairValue: 0,
    openingOci: 0,
    increase: 0,
    decrease: 0,
    interestIncome: 0,
    fvChange: 0,
    impairment: 0,
    closingCost: 0,
    closingInterestAdj: 0,
    closingAccruedInterest: 0,
    closingSubtotal: 0,
    closingFairValue: 0,
    closingOci: 0,
    closingImpairment: 0,
    auditAdjustment: 0,
    auditedAmount: 0,
    indexRef: '',
  }
}

const rows = reactive<DetailRow[]>([])
const selectedRowIndex = ref(0)

// ─── 公式重算 ────────────────────────────────────────────────────────────────

function recalcRow(row: DetailRow): void {
  row.openingSubtotal = calcSubtotal(row.openingCost, row.openingInterestAdj, row.openingAccruedInterest)
  row.closingSubtotal = calcEndingSubtotal(row.openingSubtotal, row.increase, row.decrease, row.interestIncome)
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

const totalRow = computed<DisplayRow>(() => {
  const t: DisplayRow = { ...createEmptyRow(0, ''), _isTotal: true }
  for (const r of rows) {
    t.openingCost += parseNum(r.openingCost)
    t.openingInterestAdj += parseNum(r.openingInterestAdj)
    t.openingAccruedInterest += parseNum(r.openingAccruedInterest)
    t.openingSubtotal += parseNum(r.openingSubtotal)
    t.openingFairValue += parseNum(r.openingFairValue)
    t.openingOci += parseNum(r.openingOci)
    t.increase += parseNum(r.increase)
    t.decrease += parseNum(r.decrease)
    t.interestIncome += parseNum(r.interestIncome)
    t.fvChange += parseNum(r.fvChange)
    t.impairment += parseNum(r.impairment)
    t.closingCost += parseNum(r.closingCost)
    t.closingInterestAdj += parseNum(r.closingInterestAdj)
    t.closingAccruedInterest += parseNum(r.closingAccruedInterest)
    t.closingSubtotal += parseNum(r.closingSubtotal)
    t.closingFairValue += parseNum(r.closingFairValue)
    t.closingOci += parseNum(r.closingOci)
    t.closingImpairment += parseNum(r.closingImpairment)
    t.auditedAmount += parseNum(r.auditedAmount)
  }
  return t
})

const displayRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = [...rows as DisplayRow[]]
  result.push(totalRow.value)
  return result
})

// ─── 行同步（selectedRowIndex 跨Tab保持） ───────────────────────────────────

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isTotal) return
  const idx = rows.findIndex(r => r.id === row.id)
  if (idx >= 0) selectedRowIndex.value = idx
}

// ─── 行样式 ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'row-total'
  return ''
}

// ─── 字段更新（触发公式重算） ───────────────────────────────────────────────

function updateField(id: string, field: keyof DetailRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value ?? (typeof (row as any)[field] === 'number' ? 0 : '')
  recalcRow(row)
}

// ─── 动态行增删（ElMessageBox.prompt输入名称） ──────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增投资项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '项目名称不能为空',
    })
    if (value?.trim()) {
      const newRow = createEmptyRow(rows.length + 1, value.trim())
      rows.push(newRow)
      recalcRow(newRow)
    }
  } catch {
    // 用户取消
  }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    // 重新编号
    rows.forEach((r, i) => { r.seq = i + 1 })
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const ie = useG6MainImportExport({
  wpId: computed(() => props.wpId),
  onImported: () => reloadData(),
})

const dropdownOptions = computed(() => ie.getDropdownOptions('G6-2'))

async function handleDropdownCommand(command: string) {
  const [action, sheet] = command.split(':') as [string, G6MainImportableSheet]
  if (action === 'export-template') {
    await ie.exportTemplate(sheet)
  } else if (action === 'export-data') {
    await ie.exportData(sheet)
  } else if (action === 'import-data') {
    // 打开文件选择器
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) await ie.importData(sheet, file)
    }
    input.click()
  }
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

function fmtPercent(v: unknown): string {
  if (typeof v === 'number') return `${(v * 100).toFixed(2)}%`
  return String(v ?? '')
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────

function reloadData() {
  loadFromHtmlData(props.htmlData)
}

function loadFromHtmlData(data: Record<string, any> | null) {
  rows.splice(0, rows.length)
  const items: any[] = data?.detail_rows || data?.rows || []
  if (items.length === 0) {
    // 默认5行空行
    for (let i = 1; i <= 5; i++) {
      rows.push(createEmptyRow(i, ''))
    }
  } else {
    items.forEach((item: any, i: number) => {
      const row = createEmptyRow(i + 1, item.investProject || item.invest_project || '')
      Object.assign(row, {
        investType: item.investType || item.invest_type || '',
        faceValue: parseNum(item.faceValue ?? item.face_value),
        couponRate: parseNum(item.couponRate ?? item.coupon_rate),
        effectiveRate: parseNum(item.effectiveRate ?? item.effective_rate),
        maturityDate: item.maturityDate || item.maturity_date || '',
        investDate: item.investDate || item.invest_date || '',
        holdingQty: parseNum(item.holdingQty ?? item.holding_qty),
        contractTerms: item.contractTerms || item.contract_terms || '',
        fvLevel: item.fvLevel || item.fv_level || '',
        openingCost: parseNum(item.openingCost ?? item.opening_cost),
        openingInterestAdj: parseNum(item.openingInterestAdj ?? item.opening_interest_adj),
        openingAccruedInterest: parseNum(item.openingAccruedInterest ?? item.opening_accrued_interest),
        openingFairValue: parseNum(item.openingFairValue ?? item.opening_fair_value),
        openingOci: parseNum(item.openingOci ?? item.opening_oci),
        increase: parseNum(item.increase),
        decrease: parseNum(item.decrease),
        interestIncome: parseNum(item.interestIncome ?? item.interest_income),
        fvChange: parseNum(item.fvChange ?? item.fv_change),
        impairment: parseNum(item.impairment),
        closingCost: parseNum(item.closingCost ?? item.closing_cost),
        closingInterestAdj: parseNum(item.closingInterestAdj ?? item.closing_interest_adj),
        closingAccruedInterest: parseNum(item.closingAccruedInterest ?? item.closing_accrued_interest),
        closingFairValue: parseNum(item.closingFairValue ?? item.closing_fair_value),
        closingOci: parseNum(item.closingOci ?? item.closing_oci),
        closingImpairment: parseNum(item.closingImpairment ?? item.closing_impairment),
        auditAdjustment: parseNum(item.auditAdjustment ?? item.audit_adjustment),
        auditedAmount: parseNum(item.auditedAmount ?? item.audited_amount),
        indexRef: item.indexRef || item.index_ref || '',
      })
      recalcRow(row)
      rows.push(row)
    })
  }
}

onMounted(() => {
  loadFromHtmlData(props.htmlData)
  auditNote.value = readSaved(NOTE_KEY)
  auditConclusion.value = readSaved(CONCLUSION_KEY)
})
</script>

<style scoped>
.g6-detail {
  padding: 12px 16px;
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
/* 工具栏：索引 chip + 行数 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
/* 审计说明/结论卡片 */
.audit-note-card { margin-top: 12px; }
.audit-note-card .card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 500; }
.detail-table {
  font-size: var(--wp-font-size, 13px);
}
.detail-table :deep(.row-total) {
  background-color: #fafafa;
  font-weight: 600;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #303133;
}
.total-num {
  font-weight: 600;
}
.total-label {
  font-weight: 600;
  color: #606266;
}
.compact-num {
  width: 100%;
}
.compact-num :deep(.el-input__inner) {
  text-align: right;
}
.delete-icon {
  cursor: pointer;
  color: #f56c6c;
  font-size: 14px;
}
.delete-icon:hover {
  color: #e6001f;
}
.prep-hint {
  margin-top: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 6px 0 0;
  padding-left: 20px;
}
.prep-hint li {
  margin-bottom: 3px;
}
</style>
