<template>
  <div class="m9-tab-adjudication">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M9-1 其他综合收益审定表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额·4103
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

    <!-- ═══ 蓝色渐变引导区（序号步骤,2列grid） ═══ -->
    <div class="m9-guide">
      <div class="m9-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>审定表填写步骤</span>
      </div>
      <div class="m9-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">核对试算表科目4103期初/未审数据</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">按双大类填入贷方(OCI增加)/借方(减少)发生额</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">录入AJE/RJE调整分录，系统自动计算审定数</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">保存后自动回写TB(4103)并通知附注组件</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>其他综合收益（4103）为权益类贷方科目：</strong>
        期末余额 = 期初 + 贷方（OCI增加） − 借方（OCI减少/重分类进损益）。
        审定数 = 未审数 + AJE + RJE。
        OCI分两大类：①以后不能重分类进损益（其他权益工具投资公允变动G8、设定受益计划重计量J2）；
        ②以后能重分类进损益（其他债权投资公允变动、现金流量套期损益、外币财务报表折算差额）。
        审定数变化自动回写试算表（4103）并发布'substantive:adjudicated'事件通知附注等组件。
      </div>
    </div>

    <!-- ═══ 双区块 el-table: 以后不能重分类进损益的OCI ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">一、以后不能重分类进损益的其他综合收益</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow('nonReclass')"
        >
          + 新增项目
        </el-button>
      </div>

      <el-table
        :data="nonReclassTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- 项目列 -->
        <el-table-column prop="itemName" label="项目" min-width="180" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="OCI项目名称"
                @change="(val: string) => handleUpdateRow(row, 'itemName', val)"
              />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方发生（OCI增加） -->
        <el-table-column label="贷方发生(OCI增加)" width="155" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'creditAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 借方发生（减少/重分类） -->
        <el-table-column label="借方发生(减少/重分类)" width="170" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'debitAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 期末（公式列） -->
        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(OCI增加) − 借方(减少/重分类)" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 未审 -->
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'unadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'aje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'rje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定（公式列） -->
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

        <!-- 试算平衡表数 -->
        <el-table-column label="试算平衡表数" width="130" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.tbBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'tbBalance', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.tbBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 审定与试算差异（公式列） -->
        <el-table-column label="审定与试算差异" width="130" align="right">
          <template #header>
            <el-tooltip content="差异 = 审定 − 试算平衡表数" placement="top">
              <span class="formula-col-header">审定与试算差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'diff-warning': Math.abs(row.tbDiff) > 0.01 }]">
              {{ fmtAmount(row.tbDiff) }}
            </span>
          </template>
        </el-table-column>

        <!-- 变动率 -->
        <el-table-column label="变动率" width="90" align="right">
          <template #header>
            <el-tooltip content="变动率: IF(期初=0且期末=0,0; 期初=0,100%; 否则期末/期初)" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'high-change': Math.abs(row.changeRate) > 0.2 }">
              {{ row.changeRate !== 0 ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveRowByKey(row.key)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 双区块 el-table: 以后能重分类进损益的OCI ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">二、以后能重分类进损益的其他综合收益</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow('reclass')"
        >
          + 新增项目
        </el-button>
      </div>

      <el-table
        :data="reclassTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- 项目列 -->
        <el-table-column prop="itemName" label="项目" min-width="180" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="OCI项目名称"
                @change="(val: string) => handleUpdateRow(row, 'itemName', val)"
              />
            </template>
            <template v-else>{{ row.itemName || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方发生（OCI增加） -->
        <el-table-column label="贷方发生(OCI增加)" width="155" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'creditAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 借方发生（减少/重分类） -->
        <el-table-column label="借方发生(减少/重分类)" width="170" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'debitAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 期末（公式列） -->
        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(OCI增加) − 借方(减少/重分类)" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 未审 -->
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'unadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.aje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'aje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.rje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'rje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定（公式列） -->
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

        <!-- 试算平衡表数 -->
        <el-table-column label="试算平衡表数" width="130" align="right">
          <template #default="{ row }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number :model-value="row.tbBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdateRow(row, 'tbBalance', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.tbBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 审定与试算差异（公式列） -->
        <el-table-column label="审定与试算差异" width="130" align="right">
          <template #header>
            <el-tooltip content="差异 = 审定 − 试算平衡表数" placement="top">
              <span class="formula-col-header">审定与试算差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'diff-warning': Math.abs(row.tbDiff) > 0.01 }]">
              {{ fmtAmount(row.tbDiff) }}
            </span>
          </template>
        </el-table-column>

        <!-- 变动率 -->
        <el-table-column label="变动率" width="90" align="right">
          <template #header>
            <el-tooltip content="变动率: IF(期初=0且期末=0,0; 期初=0,100%; 否则期末/期初)" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'high-change': Math.abs(row.changeRate) > 0.2 }">
              {{ row.changeRate !== 0 ? (row.changeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button v-if="isDataRow(row)" type="danger" size="small" link @click="handleRemoveRowByKey(row.key)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 合计行（双区块汇总） ═══ -->
    <div class="grand-total-section">
      <el-table :data="[grandTotalDisplayRow]" border size="small" style="width: 100%">
        <el-table-column label="项目" min-width="180" fixed>
          <template #default><span class="grand-total-label">合 计</span></template>
        </el-table-column>
        <el-table-column label="期初" width="120" align="right">
          <template #default>{{ fmtAmount(totalRow.beginning) }}</template>
        </el-table-column>
        <el-table-column label="贷方发生(OCI增加)" width="155" align="right">
          <template #default>{{ fmtAmount(totalRow.creditAmount) }}</template>
        </el-table-column>
        <el-table-column label="借方发生(减少/重分类)" width="170" align="right">
          <template #default>{{ fmtAmount(totalRow.debitAmount) }}</template>
        </el-table-column>
        <el-table-column label="期末" width="120" align="right">
          <template #default><span class="formula-value">{{ fmtAmount(totalRow.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="未审" width="120" align="right">
          <template #default>{{ fmtAmount(totalRow.unadjusted) }}</template>
        </el-table-column>
        <el-table-column label="AJE" width="110" align="right">
          <template #default>{{ fmtAmount(totalRow.aje) }}</template>
        </el-table-column>
        <el-table-column label="RJE" width="110" align="right">
          <template #default>{{ fmtAmount(totalRow.rje) }}</template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default><span class="formula-value">{{ fmtAmount(totalRow.audited) }}</span></template>
        </el-table-column>
        <el-table-column label="试算平衡表数" width="130" align="right">
          <template #default>{{ fmtAmount(totalRow.tbBalance) }}</template>
        </el-table-column>
        <el-table-column label="审定与试算差异" width="130" align="right">
          <template #default>
            <span :class="['formula-value', { 'diff-warning': Math.abs(totalRow.tbDiff) > 0.01 }]">
              {{ fmtAmount(totalRow.tbDiff) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default>
            <span :class="{ 'high-change': Math.abs(totalChangeRate) > 0.2 }">
              {{ totalChangeRate !== 0 ? (totalChangeRate * 100).toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 校验状态 + TB回写状态 ═══ -->
    <div class="adjudication-footer">
      <el-tag type="primary" size="small" effect="dark">合计审定: {{ fmtAmount(totalRow.audited) }}</el-tag>
      <el-tag type="success" size="small" effect="plain">TB回写: 科目4103 其他综合收益（贷方/权益类）</el-tag>
      <el-tag :type="equityEndCheck.isMatch ? 'success' : 'danger'" size="small" effect="plain">
        期末校验: {{ fmtAmount(equityEndCheck.actual) }}
        {{ equityEndCheck.isMatch ? '=' : '≠' }}
        期初+贷方−借方{{ fmtAmount(equityEndCheck.expected) }}
        <template v-if="!equityEndCheck.isMatch">（差异: {{ fmtAmount(equityEndCheck.diff) }}）</template>
      </el-tag>
      <el-tag v-if="totalChangeRate !== 0" :type="Math.abs(totalChangeRate) > 0.2 ? 'warning' : 'info'" size="small" effect="plain">
        总变动率: {{ (totalChangeRate * 100).toFixed(1) }}%
      </el-tag>
    </div>

    <!-- ═══ 区块小计摘要 ═══ -->
    <div class="category-summary">
      <el-tag type="info" size="small" effect="plain">不可重分类小计: {{ fmtAmount(nonReclassSubtotal.audited) }}</el-tag>
      <el-tag type="info" size="small" effect="plain">可重分类小计: {{ fmtAmount(reclassSubtotal.audited) }}</el-tag>
    </div>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写其他综合收益审定表审计结论..."
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="m9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>其他综合收益（4103）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（OCI增加） − 借方（OCI减少/重分类进损益）</li>
        <li>以后不能重分类进损益：其他权益工具投资公允价值变动(G8)、设定受益计划重计量(J2)</li>
        <li>以后能重分类进损益：其他债权投资公允变动、现金流量套期损益、外币财务报表折算差额</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>审定数变化自动回写 TB（科目 4103）并通知附注组件</li>
        <li>合计行应与M9-2明细表合计一致（交叉验证）</li>
        <li>变动率: IF(AND(期初=0,期末=0),0; IF(期初=0,100%; 否则期末/期初))</li>
        <li>试算差异≠0时，检查是否遗漏调整分录或TB数据需更新</li>
      </ul>
    </details>
  </div>
</template>


<script setup lang="ts">
/**
 * M9TabAdjudication — M9-1 其他综合收益审定表（权益类贷方！双大类）
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 权益类双区块（4103 其他综合收益, 贷方权益类）
 * 区块1: 以后不能重分类进损益的OCI（G8公允变动+J2重计量）
 * 区块2: 以后能重分类进损益的OCI（其他债权投资+套期+外币折算）
 * Columns: 项目 | 期初 | 贷方发生(OCI增加) | 借方发生(减少/重分类) | 期末 | 未审 | AJE | RJE | 审定
 *          | 试算平衡表数 | 审定与试算差异 | 变动率
 * - useM9FormData + useM9Adjudication composable
 * - Font 13px, formula columns with dashed underline + cursor:help + tooltip
 * - TB回写(4103) on 审定数变化
 * - EventBus 'substantive:adjudicated' publish
 * - el-segmented 双模式 (HTML/OO) via useM9DualMode
 * - 蓝色渐变引导区(序号步骤,2列grid)
 * - 方法论上下文琥珀色块 (权益类贷方方向说明)
 * - el-card for 审计结论区
 * - Section标题行右侧AI辅助按钮 + 复核对话按钮
 * - 编制提示details折叠底部
 * - Version trail integration (useVersionTrail)
 *
 * 47×12 structure, 41 formulas
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check, InfoFilled } from '@element-plus/icons-vue'
import { useM9FormData } from '../../composables/useM9FormData'
import { useM9DualMode } from '../../composables/useM9DualMode'
import {
  useM9Adjudication,
  type M9AdjudicationRow,
  type M9AdjudicationBlock,
  type M9RowCategory,
} from '../../composables/useM9Adjudication'
import { useVersionTrail } from '../../composables/useVersionTrail'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM9FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useM9DualMode({ wpId: computed(() => props.wpId) })
const rows = ref<M9AdjudicationRow[]>([])

const {
  computedRows,
  nonReclassSubtotal,
  reclassSubtotal,
  totalRow,
  totalChangeRate,
  equityEndCheck,
  addRow,
  removeRow,
  updateRow: composableUpdateRow,
  saveAndWriteback,
  subscribeAdjudicated,
  subscribeDisclosure,
} = useM9Adjudication(formData, rows)

// Version trail (autoSnapshot on save)
const versionTrail = useVersionTrail({ projectId: computed(() => props.projectId), workpaperId: computed(() => props.wpId) })

// ─── 表格数据构建（per block: data rows + 小计） ─────────────────────────────
interface TableRow extends M9AdjudicationRow { _rowType?: 'data' | 'subtotal' }

const nonReclassTableRows = computed<TableRow[]>(() => {
  const dataRows = computedRows.value.filter(r => r.block === 'nonReclass')
  const result: TableRow[] = dataRows.map(r => ({ ...r, _rowType: 'data' as const }))
  // 小计行
  result.push(_buildSubtotalRow('nonReclass', '不可重分类小计', nonReclassSubtotal.value))
  return result
})

const reclassTableRows = computed<TableRow[]>(() => {
  const dataRows = computedRows.value.filter(r => r.block === 'reclass')
  const result: TableRow[] = dataRows.map(r => ({ ...r, _rowType: 'data' as const }))
  // 小计行
  result.push(_buildSubtotalRow('reclass', '可重分类小计', reclassSubtotal.value))
  return result
})

/** 合计行（供单独el-table展示） */
const grandTotalDisplayRow = computed(() => ({ id: 'grand-total' }))

function _buildSubtotalRow(block: M9AdjudicationBlock, label: string, subtotal: any): TableRow {
  return {
    key: `${block}-subtotal`,
    itemName: label,
    block,
    category: 'other' as M9RowCategory,
    beginning: subtotal.beginning,
    creditAmount: subtotal.creditAmount,
    debitAmount: subtotal.debitAmount,
    endBalance: subtotal.endBalance,
    unadjusted: subtotal.unadjusted,
    aje: subtotal.aje,
    rje: subtotal.rje,
    audited: subtotal.audited,
    tbBalance: subtotal.tbBalance,
    tbDiff: subtotal.tbDiff,
    changeRate: 0,
    _rowType: 'subtotal',
  }
}

// ─── 行类型判断 ──────────────────────────────────────────────────────────────
function isDataRow(row: TableRow): boolean { return row._rowType === 'data' }
function isSubtotalRow(row: TableRow): boolean { return row._rowType === 'subtotal' }
function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  if (row._rowType === 'subtotal') return 'subtotal-row'
  return ''
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleUpdateRow(row: TableRow, field: string, value: string | number): void {
  const rawIdx = rows.value.findIndex(r => r.key === row.key)
  if (rawIdx >= 0) composableUpdateRow(rawIdx, field as any, value)
}

function handleRemoveRowByKey(key: string): void {
  const rawIdx = rows.value.findIndex(r => r.key === key)
  if (rawIdx >= 0) removeRow(rawIdx)
}

async function handleAddRow(block: M9AdjudicationBlock): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入OCI项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: block === 'nonReclass'
        ? '如：其他权益工具投资公允变动'
        : '如：其他债权投资公允变动',
      inputValidator: (v: string) => (v && v.trim() ? true : '项目名称不能为空'),
    })
    if (!name || !name.trim()) return

    // 选择分类
    const categoryOptions = block === 'nonReclass'
      ? '1. 其他权益工具投资公允变动(G8)\n2. 设定受益计划重计量(J2)\n3. 其他'
      : '1. 其他债权投资公允变动\n2. 现金流量套期损益\n3. 外币财务报表折算差额\n4. 其他'
    const validValues = block === 'nonReclass' ? ['1', '2', '3'] : ['1', '2', '3', '4']
    const { value: cat } = await ElMessageBox.prompt(
      `请选择分类（输入编号）：\n${categoryOptions}`,
      '选择分类',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: validValues.join('/'),
        inputValidator: (v: string) => (validValues.includes(v?.trim()) ? true : `请输入${validValues.join('/')}`),
      },
    )

    const nonReclassMap: Record<string, M9RowCategory> = {
      '1': 'equity-instrument-fair-value',
      '2': 'defined-benefit-remeasure',
      '3': 'other',
    }
    const reclassMap: Record<string, M9RowCategory> = {
      '1': 'debt-instrument-fair-value',
      '2': 'cashflow-hedge',
      '3': 'foreign-currency-translation',
      '4': 'other',
    }
    const categoryMap = block === 'nonReclass' ? nonReclassMap : reclassMap
    const category = categoryMap[cat?.trim() || '1'] || 'other'
    addRow(name.trim(), block, category)
  } catch { /* 用户取消 */ }
}

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditConclusion = ref('')

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleSave(): Promise<void> {
  isSaving.value = true
  try {
    await saveAndWriteback()
    // autoSnapshot via version trail
    await versionTrail.createSnapshot('M9-1 审定表保存')
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAuditConclusion(): void {
  formData.debouncedSave('M9-1-auditConclusion', { remark: auditConclusion.value || null })
}

function handleAI(_section: string): void { /* AI辅助钩子：后续集成 */ }
function handleReview(): void { openReviewDialog?.('M9-1-adjudication', '其他综合收益审定表') }

// ─── EventBus + Lifecycle ────────────────────────────────────────────────────
function handleAdjustmentCreated(): void { formData.loadData() }
let unsubAdjudicated: (() => void) | null = null
let unsubDisclosure: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()
  // 恢复行数据
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) rows.value = restored
  }
  // 恢复审计结论
  const noteResp = formData.allResponses.value.get('M9-1-auditConclusion')
  if (noteResp?.remark) auditConclusion.value = noteResp.remark

  // EventBus subscriptions
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  unsubAdjudicated = subscribeAdjudicated(() => { formData.loadData() })
  unsubDisclosure = subscribeDisclosure(() => { formData.loadData() })
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  if (unsubAdjudicated) { unsubAdjudicated(); unsubAdjudicated = null }
  if (unsubDisclosure) { unsubDisclosure(); unsubDisclosure = null }
})

// ─── 从 checklist_responses 恢复行数据 ───────────────────────────────────────
function _restoreRows(): M9AdjudicationRow[] {
  const restored: M9AdjudicationRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M9-1-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m9-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          block: d.block || 'nonReclass',
          category: d.category || 'other',
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
          changeRate: 0,
        })
      } catch { /* skip corrupt data */ }
    }
  }
  return restored
}
</script>

<style scoped>
.m9-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }

/* ─── 蓝色渐变引导区 ─── */
.m9-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfc 100%);
  border: 1px solid #b3d8fd;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
}
.m9-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #1a73e8;
  margin-bottom: 10px;
}
.m9-guide-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.step-item { display: flex; align-items: flex-start; gap: 6px; }
.step-num { font-weight: 700; color: #1a73e8; min-width: 18px; }
.step-text { font-size: var(--wp-font-size, 13px); color: #333; line-height: 1.5; }

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* ─── 区块 ─── */
.block-section { margin-bottom: 24px; }
.block-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }

/* ─── 合计区域 ─── */
.grand-total-section { margin-bottom: 16px; }
:deep(.grand-total-section .el-table) { font-weight: 700; }
:deep(.grand-total-section .el-table tr td) { background: #ecf5ff !important; border-top: 2px solid #409eff; }

/* ─── 公式列虚线下划线 + cursor:help ─── */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.diff-warning { color: #f56c6c; font-weight: 600; }

/* ─── 行样式 ─── */
.total-row-label { font-weight: 700; color: #303133; }
.grand-total-label { font-weight: 700; color: #303133; font-size: var(--wp-font-size, 13px); }
.high-change { color: #e6a23c; font-weight: 600; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.subtotal-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.subtotal-row td) { border-top: 2px solid #67c23a; }

/* ─── Footer ─── */
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

/* ─── 区块小计摘要 ─── */
.category-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

/* ─── 审计结论卡片 ─── */
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* ─── 编制提示折叠 ─── */
.m9-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m9-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m9-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m9-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
