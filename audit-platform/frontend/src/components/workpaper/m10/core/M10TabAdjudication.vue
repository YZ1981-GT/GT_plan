<template>
  <div class="m10-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M10-1 其他权益工具审定表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <el-button size="small" @click="handleAI('adjudication')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>权益类贷方科目：</strong>期末 = 期初 + 贷方 − 借方。
        发行计入贷方增加，赎回/转换计入借方减少。
        审定数 = 未审数 + AJE + RJE。
        其他权益工具（4003）按工具类型分组：永续债 / 优先股 / 其他权益工具。
        审定数变化自动回写试算表（4003）并通知附注组件。
      </div>
    </div>

    <!-- ═══ M10-2 交叉验证指示器 ═══ -->
    <div v-if="crossValidation" class="cross-validation-bar">
      <el-tag
        :type="crossValidation.isMatch ? 'success' : 'danger'"
        size="small"
        effect="plain"
      >
        <el-icon v-if="crossValidation.isMatch"><CircleCheck /></el-icon>
        <el-icon v-else><WarningFilled /></el-icon>
        与M10-2明细表{{ crossValidation.isMatch ? '一致' : '存在差异' }}
        <template v-if="!crossValidation.isMatch">（差额: {{ fmtAmount(crossValidation.diff) }}）</template>
      </el-tag>
    </div>

    <!-- ═══ 区块一：永续债 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">永续债</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow('perpetualBond')"
        >
          + 新增项目
        </el-button>
      </div>

      <el-table
        :data="perpetualBondTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <el-table-column prop="itemName" label="项目" min-width="150" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="永续债名称"
                @change="(val: string) => handleUpdateRow('perpetualBond', $index, 'itemName', val)"
              />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
          </template>
        </el-table-column>

        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('perpetualBond', $index, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="贷方发生（发行）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('perpetualBond', $index, 'creditAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="借方发生（赎回/转换）" width="160" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('perpetualBond', $index, 'debitAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(发行) − 借方(赎回/转换)" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('perpetualBond', $index, 'unadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('perpetualBond', $index, 'aje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('perpetualBond', $index, 'rje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="审定" width="120" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.endBalance - row.beginning) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'high-change': row.changeRate !== null && Math.abs(row.changeRate) > 0.2 }">
              {{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input
                :model-value="row._reason || ''"
                size="small"
                placeholder="填写原因..."
                @change="(val: string) => handleReasonChange('perpetualBond', $index, val)"
              />
            </template>
            <span v-else>{{ row._reason || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveRow('perpetualBond', $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">永续债小计审定: {{ fmtAmount(perpetualBondSubtotal.audited) }}</el-tag>
      </div>
    </div>

    <!-- ═══ 区块二：优先股 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">优先股</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow('preferredStock')">+ 新增项目</el-button>
      </div>

      <el-table :data="preferredStockTableRows" border size="small" style="width:100%" :row-class-name="getRowClassName">
        <el-table-column prop="itemName" label="项目" min-width="150" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)"><span class="total-row-label">{{ row.itemName }}</span></template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input :model-value="row.itemName" size="small" placeholder="优先股名称" @change="(val: string) => handleUpdateRow('preferredStock', $index, 'itemName', val)" />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('preferredStock', $index, 'beginning', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方发生（发行）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('preferredStock', $index, 'creditAmount', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方发生（赎回/转换）" width="160" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('preferredStock', $index, 'debitAmount', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" width="120" align="right">
          <template #header><el-tooltip content="权益类贷方: 期初+贷方(发行)−借方(赎回/转换)" placement="top"><span class="formula-col-header">期末</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('preferredStock', $index, 'unadjusted', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('preferredStock', $index, 'aje', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('preferredStock', $index, 'rje', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #header><el-tooltip content="审定=未审+AJE+RJE" placement="top"><span class="formula-col-header">审定</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.audited) }}</span></template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }"><span>{{ fmtAmount(row.endBalance - row.beginning) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'high-change': row.changeRate !== null && Math.abs(row.changeRate) > 0.2 }">{{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input :model-value="row._reason || ''" size="small" placeholder="填写原因..." @change="(val: string) => handleReasonChange('preferredStock', $index, val)" />
            </template>
            <span v-else>{{ row._reason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveRow('preferredStock', $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">优先股小计审定: {{ fmtAmount(preferredStockSubtotal.audited) }}</el-tag>
      </div>
    </div>

    <!-- ═══ 区块三：其他权益工具 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">其他权益工具</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow('other')">+ 新增项目</el-button>
      </div>

      <el-table :data="otherTableRows" border size="small" style="width:100%" :row-class-name="getRowClassName">
        <el-table-column prop="itemName" label="项目" min-width="150" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)"><span class="total-row-label">{{ row.itemName }}</span></template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input :model-value="row.itemName" size="small" placeholder="工具名称" @change="(val: string) => handleUpdateRow('other', $index, 'itemName', val)" />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('other', $index, 'beginning', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方发生（发行）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('other', $index, 'creditAmount', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方发生（赎回/转换）" width="160" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('other', $index, 'debitAmount', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" width="120" align="right">
          <template #header><el-tooltip content="权益类贷方: 期初+贷方−借方" placement="top"><span class="formula-col-header">期末</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('other', $index, 'unadjusted', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('other', $index, 'aje', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly"><el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow('other', $index, 'rje', val ?? 0)" /></template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #header><el-tooltip content="审定=未审+AJE+RJE" placement="top"><span class="formula-col-header">审定</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.audited) }}</span></template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }"><span>{{ fmtAmount(row.endBalance - row.beginning) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'high-change': row.changeRate !== null && Math.abs(row.changeRate) > 0.2 }">{{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input :model-value="row._reason || ''" size="small" placeholder="填写原因..." @change="(val: string) => handleReasonChange('other', $index, val)" />
            </template>
            <span v-else>{{ row._reason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveRow('other', $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">其他权益工具小计审定: {{ fmtAmount(otherSubtotal.audited) }}</el-tag>
      </div>
    </div>

    <!-- ═══ 合计 + 期末校验 + TB回写状态 ═══ -->
    <div class="adjudication-footer">
      <el-tag type="primary" size="small" effect="dark">合计审定: {{ fmtAmount(totalRow.audited) }}</el-tag>
      <el-tag type="success" size="small" effect="plain">TB回写: 科目4003 其他权益工具（贷方/权益类）</el-tag>
      <el-tag :type="equityEndCheck.isMatch ? 'success' : 'danger'" size="small" effect="plain">
        期末校验: {{ fmtAmount(equityEndCheck.actual) }}
        {{ equityEndCheck.isMatch ? '=' : '≠' }}
        期初+贷方−借方 {{ fmtAmount(equityEndCheck.expected) }}
        <template v-if="!equityEndCheck.isMatch">（差异: {{ fmtAmount(equityEndCheck.diff) }}）</template>
      </el-tag>
      <el-tag v-if="totalChangeRate != null && totalChangeRate !== 0" :type="Math.abs(totalChangeRate!) > 0.2 ? 'warning' : 'info'" size="small" effect="plain">
        变动率: {{ ((totalChangeRate!) * 100).toFixed(1) }}%
      </el-tag>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">原因分析及审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写其他权益工具审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他权益工具（4003）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（发行） − 借方（赎回/转换）</li>
        <li>永续债：无固定到期日、无强制付息义务的债券，CAS37判定为权益工具</li>
        <li>优先股：如发行方无赎回义务且股息非强制，CAS37判定为权益工具</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>三组展示：永续债 / 优先股 / 其他权益工具</li>
        <li>审定数变化自动回写 TB（科目 4003）并通知附注组件</li>
        <li>合计行应与明细表M10-2的合计一致（交叉验证）</li>
        <li>如有工具被CAS37判定为负债，应从M10移出计入负债科目（参见M10-4区分检查表）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabAdjudication — M10-1 其他权益工具审定表（权益类贷方！）
 * Requirements: 2.1-2.7
 * 单区块按工具类型(永续债/优先股/其他)分三组 + 各组小计 + 合计行
 * 公式列虚线下划线+cursor:help+tooltip
 * TB回写(4003) + EventBus 'substantive:adjudicated'
 * 与M10-2明细表交叉验证（绿勾/红警）
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check, CircleCheck, WarningFilled } from '@element-plus/icons-vue'
import { useM10FormData } from '../../composables/useM10FormData'
import { useM10DualMode } from '../../composables/useM10DualMode'
import {
  useM10Adjudication,
  type M10AdjudicationRow,
  type M10InstrumentGroup,
  M10_INSTRUMENT_GROUPS,
} from '../../composables/useM10Adjudication'
import { useM10CrossSheet } from '../../composables/useM10CrossSheet'
import { fmtAmount } from '@/utils/formatters'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useM10FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useM10DualMode({ wpId: computed(() => props.wpId) })
const rows = ref<M10AdjudicationRow[]>([])

const {
  computedRows,
  perpetualBondSubtotal,
  preferredStockSubtotal,
  otherSubtotal,
  totalRow,
  totalChangeRate,
  equityEndCheck,
  addRow,
  removeRow,
  updateRow: composableUpdateRow,
  saveAndWriteback,
  crossValidateWithDetail,
  subscribeDisclosure,
} = useM10Adjudication(formData, rows)

const { adjudicationVsDetail: crossValidation } = useM10CrossSheet(formData.allResponses)

// ─── 原因分析存储 ────────────────────────────────────────────────────────────

const reasons = ref<Map<string, string>>(new Map())

// ─── 表格数据：按分组拆分 + 小计行 ──────────────────────────────────────────

interface TableRow extends M10AdjudicationRow { _rowType?: 'data' | 'subtotal'; _reason?: string }

function buildGroupTableRows(group: M10InstrumentGroup, subtotalData: any, label: string): TableRow[] {
  const result: TableRow[] = computedRows.value
    .filter(r => r.group === group)
    .map(r => ({
      ...r,
      _rowType: 'data' as const,
      _reason: reasons.value.get(r.key) || '',
    }))
  result.push({
    key: `${group}-subtotal`,
    itemName: `${label}小计`,
    group,
    beginning: subtotalData.beginning,
    creditAmount: subtotalData.creditAmount,
    debitAmount: subtotalData.debitAmount,
    endBalance: subtotalData.endBalance,
    unadjusted: subtotalData.unadjusted,
    aje: subtotalData.aje,
    rje: subtotalData.rje,
    audited: subtotalData.audited,
    tbBalance: subtotalData.tbBalance,
    tbDiff: subtotalData.tbDiff,
    changeRate: null,
    _rowType: 'subtotal',
    _reason: '',
  })
  return result
}

const perpetualBondTableRows = computed<TableRow[]>(() =>
  buildGroupTableRows('perpetualBond', perpetualBondSubtotal.value, '永续债'))

const preferredStockTableRows = computed<TableRow[]>(() =>
  buildGroupTableRows('preferredStock', preferredStockSubtotal.value, '优先股'))

const otherTableRows = computed<TableRow[]>(() =>
  buildGroupTableRows('other', otherSubtotal.value, '其他权益工具'))

function isDataRow(row: TableRow): boolean { return row._rowType === 'data' }
function isSubtotalRow(row: TableRow): boolean { return row._rowType === 'subtotal' }
function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  return row._rowType === 'subtotal' ? 'subtotal-row' : ''
}

// ─── 行操作代理（按分组） ────────────────────────────────────────────────────

function getGroupRawIndex(tableIndex: number, group: M10InstrumentGroup): number {
  const groupRows = computedRows.value.filter(r => r.group === group)
  if (tableIndex < 0 || tableIndex >= groupRows.length) return -1
  const targetKey = groupRows[tableIndex].key
  return rows.value.findIndex(r => r.key === targetKey)
}

function handleUpdateRow(group: M10InstrumentGroup, tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getGroupRawIndex(tableIndex, group)
  if (rawIdx >= 0) composableUpdateRow(rawIdx, field as any, value)
}

function handleRemoveRow(group: M10InstrumentGroup, tableIndex: number): void {
  const rawIdx = getGroupRawIndex(tableIndex, group)
  if (rawIdx >= 0) removeRow(rawIdx)
}

function handleReasonChange(group: M10InstrumentGroup, tableIndex: number, val: string): void {
  const groupRows = computedRows.value.filter(r => r.group === group)
  if (tableIndex < 0 || tableIndex >= groupRows.length) return
  const key = groupRows[tableIndex].key
  reasons.value.set(key, val)
  // 持久化原因分析
  formData.debouncedSave(`M10-1-reason-${key}`, { remark: val })
}

async function handleAddRow(group: M10InstrumentGroup): Promise<void> {
  const labels: Record<M10InstrumentGroup, string> = {
    perpetualBond: '永续债',
    preferredStock: '优先股',
    other: '其他权益工具',
  }
  const label = labels[group]
  try {
    const { value } = await ElMessageBox.prompt(`请输入${label}名称`, `新增${label}`, {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: `如：XX${label}`,
      inputValidator: (v: string) => (v && v.trim() ? true : '名称不能为空'),
    })
    if (value && value.trim()) addRow(value.trim(), group)
  } catch { /* 用户取消 */ }
}

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAuditNote() {
  formData.debouncedSave('M10-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(_section: string) { /* AI辅助钩子 — Phase 6 集成 */ }
function handleReview() { openReviewDialog?.('M10-1-adjudication', '其他权益工具审定表') }

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjustmentCreated() { formData.loadData() }
let unsubscribeDisclosure: (() => void) | null = null

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 恢复行数据
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) rows.value = restored
  }
  // 恢复原因分析
  _restoreReasons()
  // 恢复审计说明
  const noteResp = formData.allResponses.value.get('M10-1-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  // EventBus 监听
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  unsubscribeDisclosure = subscribeDisclosure(() => { formData.loadData() })
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  if (unsubscribeDisclosure) { unsubscribeDisclosure(); unsubscribeDisclosure = null }
})

// ─── 恢复数据 ────────────────────────────────────────────────────────────────

function _restoreRows(): M10AdjudicationRow[] {
  const restored: M10AdjudicationRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M10-1-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m10-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          group: d.group || 'perpetualBond',
          beginning: Number(d.beginning) || 0,
          creditAmount: Number(d.creditAmount) || 0,
          debitAmount: Number(d.debitAmount) || 0,
          endBalance: 0,
          unadjusted: Number(d.unadjusted) || 0,
          aje: Number(d.aje) || 0,
          rje: Number(d.rje) || 0,
          audited: 0,
          tbBalance: Number(d.tbBalance) || 0,
          tbDiff: 0,
          changeRate: null,
        })
      } catch { /* skip corrupted row */ }
    }
  }
  return restored
}

function _restoreReasons(): void {
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M10-1-reason-') && resp.remark) {
      const rowKey = key.replace('M10-1-reason-', '')
      reasons.value.set(rowKey, resp.remark)
    }
  }
}
</script>

<style scoped>
.m10-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* 交叉验证指示器 */
.cross-validation-bar { margin-bottom: 12px; }

/* 分组区块 */
.block-section { margin-bottom: 24px; }
.block-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.block-subtotal { margin-top: 8px; }

/* 公式列样式 */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }

/* 行样式 */
.total-row-label { font-weight: 700; color: #303133; }
.high-change { color: #e6a23c; font-weight: 600; }

/* 表格全局字体 */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.subtotal-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.subtotal-row td) { border-top: 2px solid #67c23a; }

/* 合计footer */
.adjudication-footer {
  margin-top: 8px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

/* 审计说明卡片 */
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* 编制提示 */
.m10-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m10-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m10-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m10-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
