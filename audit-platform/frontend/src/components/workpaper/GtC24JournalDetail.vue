<template>
  <div class="gt-c24-journal-detail">
    <!-- 工具栏：导入导出 dropdown（readonly 时隐藏） -->
    <div v-if="!isReadonly && !isLoading" class="c24-toolbar">
      <div class="toolbar-left" />
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small" @command="onImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <!-- 隐藏文件选择器 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls,.csv"
      style="display: none;"
      @change="onFileSelected"
    />

    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部操作引导区 -->
      <div class="guidance-area">
        <div class="guidance-header">
          <el-icon><InfoFilled /></el-icon>
          <span>操作流程引导</span>
        </div>
        <div class="guidance-steps">
          <div class="step-item">
            <span class="step-num">①</span>
            <span class="step-text">导入分录</span>
          </div>
          <div class="step-item">
            <span class="step-num">②</span>
            <span class="step-text">完整性测试</span>
          </div>
          <div class="step-item">
            <span class="step-num">③</span>
            <span class="step-text">异常/本福特分析</span>
          </div>
          <div class="step-item">
            <span class="step-num">④</span>
            <span class="step-text">汇总结论</span>
          </div>
        </div>
      </div>

      <!-- ═══ C24A 主控台（参照 C1 向导中控台）═══ -->
      <div v-if="currentSheet === 'C24A'" class="c24-console">
        <!-- 数据源状态卡片 -->
        <el-card shadow="never" class="c24-datasource-card">
          <div class="ds-header">
            <span class="ds-title">📁 会计分录数据源</span>
            <div v-if="!isReadonly" class="ds-actions">
              <el-button type="primary" size="small" @click="loadFromLedger(false)">从序时账导入</el-button>
              <el-button size="small" @click="onImportExportCommand('importData')">从 Excel 导入</el-button>
            </div>
          </div>
          <div class="ds-stats">
            <div class="ds-stat">
              <span class="ds-num">{{ journalEntries.length }}</span>
              <span class="ds-lbl">已导入分录</span>
            </div>
            <div class="ds-stat">
              <span class="ds-num-sm">{{ fmtAmount(balanceResult.debitTotal) }}</span>
              <span class="ds-lbl">借方合计</span>
            </div>
            <div class="ds-stat">
              <span class="ds-num-sm">{{ fmtAmount(balanceResult.creditTotal) }}</span>
              <span class="ds-lbl">贷方合计</span>
            </div>
            <div class="ds-stat-tag">
              <el-tag v-if="journalEntries.length === 0" type="info" size="large">待导入数据</el-tag>
              <el-tag v-else :type="balanceResult.balanced ? 'success' : 'danger'" size="large">
                {{ balanceResult.balanced ? '✓ 借贷平衡' : '✗ 借贷不平' }}
              </el-tag>
            </div>
          </div>
          <el-alert
            v-if="journalEntries.length === 0"
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 10px;"
          >
            尚未导入会计分录。点击「从序时账导入」自动读取已入库的序时账数据，或「从 Excel 导入」上传分录明细。
          </el-alert>
        </el-card>

        <!-- 测试项看板 -->
        <div class="c24-test-board">
          <div class="board-title">
            <span>🎯 测试项目</span>
            <span class="board-hint">点击卡片进入测试</span>
          </div>
          <div class="test-grid">
            <div
              v-for="item in TEST_ITEMS"
              :key="item.key"
              class="test-card"
              :class="testCardClass(item.key)"
              @click="openTestDialog(item.key)"
            >
              <div class="test-card-top">
                <span class="test-icon">{{ item.icon }}</span>
                <span class="test-status-dot" :class="'dot-' + testStatus(item.key)" />
              </div>
              <div class="test-name">{{ item.title }}</div>
              <div class="test-desc">{{ item.desc }}</div>
              <div class="test-metric">{{ testMetric(item.key) }}</div>
              <div class="test-footer">
                <el-tag v-if="testConclusionText(item.key)" :type="testConclusionType(item.key)" size="small" effect="plain">
                  {{ testConclusionText(item.key) }}
                </el-tag>
                <span v-else class="test-todo">待测试 →</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 审计程序（10步，可折叠） -->
        <el-collapse v-model="programCollapse" class="c24-program-collapse">
          <el-collapse-item name="program">
            <template #title>
              <span class="collapse-title">📋 审计程序（{{ C24A_PROGRAMS.length }} 步）· 完成 {{ completedStepCount }}/{{ C24A_PROGRAMS.length }}</span>
            </template>
            <table class="c24-grid-table c24-step-table">
              <thead>
                <tr>
                  <th style="width: 40px">#</th>
                  <th style="min-width: 280px">程序</th>
                  <th style="width: 80px">适用?</th>
                  <th style="width: 100px">执行人</th>
                  <th style="width: 140px">执行情况</th>
                  <th style="width: 100px">索引</th>
                  <th v-if="!isReadonly" style="width: 70px">快捷</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(step, si) in C24A_PROGRAMS"
                  :key="si"
                  class="c24-step-row"
                  :class="c24StepRowClass(si)"
                  @click="openC24StepDialog(si)"
                >
                  <td class="c24-cell-idx">{{ step.seq }}</td>
                  <td class="c24-cell-name">
                    <span class="c24-step-text">{{ step.name }}</span>
                    <el-tag v-if="step.linkedSheet" size="small" type="warning" effect="plain" style="margin-left:4px">
                      → {{ step.linkedSheet }}
                    </el-tag>
                  </td>
                  <td class="c24-cell-center">
                    <span v-if="getC24StepVal(si, 'applicable') === 'Y'">✅</span>
                    <span v-else-if="getC24StepVal(si, 'applicable') === 'N'">❌</span>
                    <span v-else class="c24-cell-empty">—</span>
                  </td>
                  <td>{{ getC24StepVal(si, 'executor') || '' }}</td>
                  <td>
                    <el-tag v-if="getC24StepVal(si, 'conclusion')" :type="c24ConclusionType(getC24StepVal(si, 'conclusion'))" size="small" effect="plain">
                      {{ getC24StepVal(si, 'conclusion') }}
                    </el-tag>
                    <span v-else class="c24-cell-empty">—</span>
                  </td>
                  <td>
                    <span v-if="getC24StepVal(si, 'index')" class="c24-index-link">{{ getC24StepVal(si, 'index') }}</span>
                    <span v-else class="c24-cell-empty">—</span>
                  </td>
                  <td v-if="!isReadonly" class="c24-cell-center" @click.stop>
                    <el-button
                      v-if="!getC24StepVal(si, 'conclusion')"
                      size="small" type="success" link
                      title="快速标记：适用 + 执行完毕"
                      @click="quickMarkC24Step(si)"
                    >✓完成</el-button>
                    <span v-else class="c24-cell-empty">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </el-collapse-item>
        </el-collapse>

        <!-- 汇总结论卡片 -->
        <el-card shadow="never" class="c24-summary-conclusion-card">
          <template #header>
            <div class="scc-header">
              <span class="scc-title">📝 C24 细节测试汇总结论</span>
              <el-button v-if="!isReadonly" size="small" @click="onAiSuggest('C24-0-conclusion')">AI 辅助</el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :model-value="summaryForm.conclusion"
            :disabled="isReadonly"
            placeholder="综合各测试项结果，填写 C24 细节测试汇总结论"
            @input="onSummaryFieldChange('conclusion', $event)"
          />
        </el-card>

        <!-- 步骤 Dialog -->
        <el-dialog
          v-model="c24StepDialogVisible"
          :title="c24StepDialogTitle"
          width="55%"
          :close-on-click-modal="false"
          append-to-body
          destroy-on-close
        >
          <template v-if="activeC24Step !== null">
            <!-- 编制说明 -->
            <div v-if="C24A_PROGRAMS[activeC24Step].hint" class="c24-edit-hint">
              <div class="c24-edit-hint-head">📖 编制说明</div>
              <div class="c24-edit-hint-body">{{ C24A_PROGRAMS[activeC24Step].hint }}</div>
            </div>

            <!-- 表单字段 -->
            <el-form label-width="80px" size="small" style="margin-top:12px">
              <el-form-item label="是否适用">
                <el-radio-group
                  :model-value="getC24StepVal(activeC24Step, 'applicable')"
                  :disabled="isReadonly"
                  @update:model-value="setC24StepVal(activeC24Step!, 'applicable', $event as string)"
                >
                  <el-radio-button value="Y">适用</el-radio-button>
                  <el-radio-button value="N">不适用</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="执行人">
                <el-input
                  :model-value="getC24StepVal(activeC24Step, 'executor')"
                  :disabled="isReadonly"
                  placeholder="填写执行人"
                  @update:model-value="setC24StepVal(activeC24Step!, 'executor', $event)"
                />
              </el-form-item>
              <el-form-item label="执行情况">
                <el-input
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  :model-value="getC24StepVal(activeC24Step, 'result')"
                  :disabled="isReadonly"
                  placeholder="描述执行情况"
                  @update:model-value="setC24StepVal(activeC24Step!, 'result', $event)"
                />
              </el-form-item>
              <el-form-item label="执行结论">
                <el-select
                  :model-value="getC24StepVal(activeC24Step, 'conclusion')"
                  :disabled="isReadonly"
                  placeholder="选择结论"
                  clearable
                  @update:model-value="setC24StepVal(activeC24Step!, 'conclusion', $event)"
                >
                  <el-option value="已执行" label="已执行" />
                  <el-option value="无异常" label="无异常" />
                  <el-option value="有异常" label="有异常" />
                  <el-option value="不适用" label="不适用" />
                </el-select>
              </el-form-item>
              <el-form-item label="索引号">
                <el-input
                  :model-value="getC24StepVal(activeC24Step, 'index')"
                  :disabled="isReadonly"
                  placeholder="索引号"
                  @update:model-value="setC24StepVal(activeC24Step!, 'index', $event)"
                />
              </el-form-item>
            </el-form>

            <!-- 联动跳转到对应测试项 Dialog -->
            <div v-if="C24A_PROGRAMS[activeC24Step].linkedSheet" class="c24-dialog-link">
              <el-button type="primary" size="small" @click="jumpFromStepToTest(C24A_PROGRAMS[activeC24Step].linkedSheet!)">
                → 进入 {{ C24A_PROGRAMS[activeC24Step].linkedSheet }} 测试
              </el-button>
            </div>
          </template>
          <template #footer>
            <el-button @click="c24StepDialogVisible = false">关闭</el-button>
            <el-button v-if="!isReadonly && activeC24Step !== null && activeC24Step < C24A_PROGRAMS.length - 1" type="primary" @click="nextC24Step">下一步 →</el-button>
          </template>
        </el-dialog>

        <!-- ═══ 测试项 Dialog（内嵌子组件，全屏）═══ -->
        <el-dialog
          v-model="testDialogVisible"
          :title="testDialogTitle"
          width="90%"
          top="4vh"
          :close-on-click-modal="false"
          append-to-body
          class="c24-test-dialog"
        >
          <div v-if="activeTestKey && journalEntries.length === 0 && activeTestKey !== 'C24-4'" class="c24-empty-data-guide">
            <el-empty description="暂无分录数据">
              <template #description><p>请先导入会计分录数据后再执行本测试项。</p></template>
              <el-button v-if="!isReadonly" type="primary" size="small" @click="loadFromLedger(false)">从序时账导入</el-button>
            </el-empty>
          </div>
          <template v-else>
            <C24BalanceIntegritySheet
              v-if="activeTestKey === 'C24-1'"
              :result="balanceResult"
              :conclusion="conclusions['C24-1']"
              :is-readonly="isReadonly"
              @update:conclusion="onConclusionChange('C24-1', $event)"
              @ai-suggest="onAiSuggest"
              @load-from-ledger="loadFromLedger(false)"
              @import-excel="onImportExportCommand('importData')"
            />
            <C24TrialBalanceSheet
              v-else-if="activeTestKey === 'C24-2'"
              :comparisons="trialBalanceComparisons"
              :conclusion="conclusions['C24-2']"
              :is-readonly="isReadonly"
              @update:conclusion="onConclusionChange('C24-2', $event)"
              @ai-suggest="onAiSuggest"
            />
            <C24GapTestSheet
              v-else-if="activeTestKey === 'C24-3'"
              :gaps="gapResults"
              :gap-notes="gapNotes"
              :has-data="journalEntries.length > 0"
              :conclusion="conclusions['C24-3']"
              :is-readonly="isReadonly"
              @update:conclusion="onConclusionChange('C24-3', $event)"
              @update:gap-note="onGapNoteChange"
              @ai-suggest="onAiSuggest"
            />
            <C24AnomalyAccountSheet
              v-else-if="activeTestKey === 'C24-4'"
              :rows="accountRows"
              :has-data="journalEntries.length > 0"
              :conclusion="conclusions['C24-4']"
              :is-readonly="isReadonly"
              @update:conclusion="onConclusionChange('C24-4', $event)"
              @update:row="onAccountRowChange"
              @ai-suggest="onAiSuggest"
            />
            <C24AnomalyEntrySheet
              v-else-if="activeTestKey === 'C24-5'"
              :wp-id="props.wpId"
              :project-id="props.projectId"
              :enabled-rules="enabledRules"
              :rule-params="ruleParams"
              :anomalies="anomalyResults"
              :anomaly-notes="anomalyNotes"
              :has-data="journalEntries.length > 0"
              :conclusion="conclusions['C24-5']"
              :is-readonly="isReadonly"
              :total-entry-count="journalEntries.length"
              @update:conclusion="onConclusionChange('C24-5', $event)"
              @update:enabled-rules="onEnabledRulesChange"
              @update:rule-param="onRuleParamChange"
              @update:anomaly-note="onAnomalyNoteChange"
              @run-screen="runAnomalyScreen"
              @ai-suggest="onAiSuggest"
              @conclusion-change="onSubConclusionRefresh"
            />
            <C24BenfordSheet
              v-else-if="activeTestKey === 'benford'"
              :distribution="benfordDist"
              :chi-result="benfordChi"
              :sample-count="benfordSampleCount"
              :alpha="benfordAlpha"
              :has-data="journalEntries.length > 0"
              :conclusion="conclusions['benford']"
              :is-readonly="isReadonly"
              @update:conclusion="onConclusionChange('benford', $event)"
              @ai-suggest="onAiSuggest"
            />
          </template>
          <template #footer>
            <div class="test-dialog-footer">
              <el-button @click="testDialogVisible = false">关闭</el-button>
              <div class="test-dialog-nav">
                <el-button :disabled="!hasPrevTest" @click="gotoAdjacentTest(-1)">← 上一项</el-button>
                <el-button type="primary" :disabled="!hasNextTest" @click="gotoAdjacentTest(1)">下一项 →</el-button>
              </div>
            </div>
          </template>
        </el-dialog>
      </div>

      <!-- C24-0 汇总表 -->
      <div v-else-if="currentSheet === 'C24-0'">
        <C24SummarySheet
          :form-data="summaryForm"
          :conclusions="subConclusions"
          :is-readonly="isReadonly"
          @update:field="onSummaryFieldChange"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-1 借贷发生额完整性 -->
      <div v-else-if="currentSheet === 'C24-1'">
        <div v-if="journalEntries.length === 0" class="c24-empty-data-guide">
          <el-empty description="暂无分录数据">
            <template #description>
              <p>请先导入会计分录数据后再执行借贷发生额完整性测试。</p>
            </template>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="loadFromLedger">从序时账导入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="jumpToSheet('C24A')">返回程序表</el-button>
          </el-empty>
        </div>
        <C24BalanceIntegritySheet
          v-else
          :result="balanceResult"
          :conclusion="conclusions['C24-1']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-1', $event)"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-2 分录余额对比 -->
      <div v-else-if="currentSheet === 'C24-2'">
        <div v-if="journalEntries.length === 0" class="c24-empty-data-guide">
          <el-empty description="暂无分录数据">
            <template #description>
              <p>请先导入会计分录数据后再执行科目余额对比测试。</p>
            </template>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="loadFromLedger">从序时账导入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="jumpToSheet('C24A')">返回程序表</el-button>
          </el-empty>
        </div>
        <C24TrialBalanceSheet
          v-else
          :comparisons="trialBalanceComparisons"
          :conclusion="conclusions['C24-2']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-2', $event)"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-3 跳号测试 -->
      <div v-else-if="currentSheet === 'C24-3'">
        <div v-if="journalEntries.length === 0" class="c24-empty-data-guide">
          <el-empty description="暂无分录数据">
            <template #description>
              <p>请先导入会计分录数据后再执行跳号测试。</p>
            </template>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="loadFromLedger">从序时账导入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="jumpToSheet('C24A')">返回程序表</el-button>
          </el-empty>
        </div>
        <C24GapTestSheet
          v-else
          :gaps="gapResults"
          :gap-notes="gapNotes"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['C24-3']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-3', $event)"
          @update:gap-note="onGapNoteChange"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-4 异常账户测试 -->
      <div v-else-if="currentSheet === 'C24-4'">
        <div v-if="journalEntries.length === 0" class="c24-empty-data-guide">
          <el-empty description="暂无分录数据">
            <template #description>
              <p>请先导入会计分录数据后再执行异常账户测试。</p>
            </template>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="loadFromLedger">从序时账导入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="jumpToSheet('C24A')">返回程序表</el-button>
          </el-empty>
        </div>
        <C24AnomalyAccountSheet
          v-else
          :rows="accountRows"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['C24-4']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-4', $event)"
          @update:row="onAccountRowChange"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-5 异常分录测试 -->
      <div v-else-if="currentSheet === 'C24-5'">
        <div v-if="journalEntries.length === 0" class="c24-empty-data-guide">
          <el-empty description="暂无分录数据">
            <template #description>
              <p>请先导入会计分录数据后再执行异常分录测试。</p>
            </template>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="loadFromLedger">从序时账导入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="jumpToSheet('C24A')">返回程序表</el-button>
          </el-empty>
        </div>
        <C24AnomalyEntrySheet
          v-else
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :enabled-rules="enabledRules"
          :rule-params="ruleParams"
          :anomalies="anomalyResults"
          :anomaly-notes="anomalyNotes"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['C24-5']"
          :is-readonly="isReadonly"
          :total-entry-count="journalEntries.length"
          @update:conclusion="onConclusionChange('C24-5', $event)"
          @update:enabled-rules="onEnabledRulesChange"
          @update:rule-param="onRuleParamChange"
          @update:anomaly-note="onAnomalyNoteChange"
          @run-screen="runAnomalyScreen"
          @ai-suggest="onAiSuggest"
          @conclusion-change="onSubConclusionRefresh"
        />
      </div>

      <!-- 本福特定律测试 -->
      <div v-else-if="currentSheet === '本福特'">
        <div v-if="journalEntries.length === 0" class="c24-empty-data-guide">
          <el-empty description="暂无分录数据">
            <template #description>
              <p>请先导入会计分录数据后再执行本福特定律测试。</p>
            </template>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="loadFromLedger">从序时账导入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="jumpToSheet('C24A')">返回程序表</el-button>
          </el-empty>
        </div>
        <C24BenfordSheet
          v-else
          :distribution="benfordDist"
          :chi-result="benfordChi"
          :sample-count="benfordSampleCount"
          :alpha="benfordAlpha"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['benford']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('benford', $event)"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- 本福特-数据 虚拟分录参考 -->
      <div v-else-if="currentSheet === '本福特-数据'">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>虚拟会计分录数据参考（只读）</template>
          <p style="margin-top: 8px; color: #606266;">
            此为本福特分析参考数据，实际测试使用导入的真实分录数据。
          </p>
        </el-alert>
      </div>

      <!-- 假期清单 -->
      <div v-else-if="currentSheet === '假期清单'">
        <C24HolidaySheet
          :holidays="holidays"
          :is-readonly="isReadonly"
          @add-holiday="onAddHoliday"
          @remove-holiday="onRemoveHoliday"
          @update-holiday="onUpdateHoliday"
        />
      </div>

      <!-- Fallback -->
      <div v-else>
        <el-alert type="info" :closable="false">{{ currentSheet }} — 暂无内容</el-alert>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC24JournalDetail — C24 会计分录细节测试专属组件
 *
 * componentType: c24-journal-entry-detail
 * 对齐 D4 标准：sheetName v-if 分发，无内部 el-tabs
 *
 * Sheets: C24A / C24-0 汇总 / C24-1~5 / 本福特 / 本福特-数据 / 假期清单
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 4.2
 * Requirements: 1.1, 1.5, 3.4, 4.3, 4.4, 5.3, 5.4, 6.1, 6.2, 6.3
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { InfoFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useLedgerCache } from '@/composables/useLedgerCache'
import {
  calcBalanceIntegrity,
  compareToTrialBalance,
  detectGaps,
  screenAnomalies,
  benfordDistribution,
  benfordChiSquareTest,
  type JournalEntry,
  type BalanceIntegrityResult,
  type TrialBalanceComparison,
  type GapResult,
  type AnomalyResult,
  type AnomalyRules,
  type BenfordDigitResult,
  type BenfordTestResult,
  type TrialBalanceRow,
} from '@/composables/useC24AnalyticsEngine'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'
import { useC24ImportExport } from '@/composables/useC24ImportExport'
import { fmtAmount } from '@/utils/formatters'
import { resolveEffectiveAuditYear } from '@/utils/resolveAuditYear'
import type { C24SummaryFormData } from './c24/C24SummarySheet.vue'
import type { GapNote } from './c24/C24GapTestSheet.vue'
import type { AccountRow } from './c24/C24AnomalyAccountSheet.vue'
import type { RuleParams, AnomalyNote } from './c24/C24AnomalyEntrySheet.vue'
import type { HolidayRow } from './c24/C24HolidaySheet.vue'

defineOptions({ name: 'GtC24JournalDetail' })

// ─── Lazy child components ───
const C24SummarySheet = defineAsyncComponent(() => import('./c24/C24SummarySheet.vue'))
const C24BalanceIntegritySheet = defineAsyncComponent(() => import('./c24/C24BalanceIntegritySheet.vue'))
const C24TrialBalanceSheet = defineAsyncComponent(() => import('./c24/C24TrialBalanceSheet.vue'))
const C24GapTestSheet = defineAsyncComponent(() => import('./c24/C24GapTestSheet.vue'))
const C24AnomalyAccountSheet = defineAsyncComponent(() => import('./c24/C24AnomalyAccountSheet.vue'))
const C24AnomalyEntrySheet = defineAsyncComponent(() => import('./c24/C24AnomalyEntrySheet.vue'))
const C24BenfordSheet = defineAsyncComponent(() => import('./c24/C24BenfordSheet.vue'))
const C24HolidaySheet = defineAsyncComponent(() => import('./c24/C24HolidaySheet.vue'))

// ─── Props / Emits ───
const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  year?: string
  sheetName?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── State ───
const route = useRoute()
const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

/** 序时账查询年度：props > 路由 > 项目 store > 通用兜底 */
const effectiveYear = computed(() => {
  try {
    const store = useProjectStore()
    return resolveEffectiveAuditYear({
      propYear: props.year,
      routeYear: route?.query?.year,
      storeAuditYear: store.auditYear,
      storeYear: store.year,
    })
  } catch {
    return resolveEffectiveAuditYear({
      propYear: props.year,
      routeYear: route?.query?.year,
    })
  }
})

const currentSheet = computed(() => {
  const name = props.sheetName || 'C24A'
  if (name.includes('C24A') || name.includes('程序表')) return 'C24A'
  if (name === 'C24-0' || name.includes('汇总')) return 'C24-0'
  if (name === 'C24-1' || name.includes('借贷')) return 'C24-1'
  if (name === 'C24-2' || name.includes('余额')) return 'C24-2'
  if (name === 'C24-3' || name.includes('跳号')) return 'C24-3'
  if (name === 'C24-4' || name.includes('异常账户')) return 'C24-4'
  if (name === 'C24-5' || name.includes('异常分录')) return 'C24-5'
  if (name === '本福特-数据') return '本福特-数据'
  if (name.includes('本福特')) return '本福特'
  if (name.includes('假期')) return '假期清单'
  return name
})

// ─── C24A 程序表 10 步定义 ───
interface C24ProgramStep {
  seq: number
  name: string
  hint?: string
  linkedSheet?: string
}

const C24A_PROGRAMS: C24ProgramStep[] = [
  {
    seq: 1,
    name: '确定会计分录细节测试的范围，选定需要检查的会计科目和期间。',
    hint: '根据风险评估结果(B50)，确定需要进行细节测试的科目范围和期间范围。重点关注重大错报风险较高的领域。',
    linkedSheet: 'C24-0',
  },
  {
    seq: 2,
    name: '获取全部会计分录数据，了解被审计单位日记账分录处理流程。',
    hint: '向被审计单位获取序时账/明细账全量数据导出。了解分录录入流程：手工/系统自动生成、审批流程、过账机制等。',
    linkedSheet: 'C24-0',
  },
  {
    seq: 3,
    name: '对会计分录数据的完整性进行测试（借贷发生额一致性）。',
    hint: '验证导入数据的借方发生额合计与贷方发生额合计是否一致（Σ借 = Σ贷）。不一致时查明原因。',
    linkedSheet: 'C24-1',
  },
  {
    seq: 4,
    name: '将分录数据按科目汇总与科目余额表进行比较。',
    hint: '按科目编码汇总分录借贷方发生额，与试算平衡表中的发生额进行对比，确认数据完整性和准确性。',
    linkedSheet: 'C24-2',
  },
  {
    seq: 5,
    name: '执行凭证号跳号测试，识别缺失的凭证编号。',
    hint: '对凭证编号进行连续性检查，识别缺号区间。对缺号逐一确认是否为正常作废或异常缺失。',
    linkedSheet: 'C24-3',
  },
  {
    seq: 6,
    name: '对操作账户和人员进行异常测试（未授权人员/异常使用账户）。',
    hint: '结合C23授权清单，识别未授权人员录入的分录、高管/IT人员直接制作的分录、以及账户活动异常的分录。',
    linkedSheet: 'C24-4',
  },
  {
    seq: 7,
    name: '设计并执行日常异常会计分录筛选规则。',
    hint: '运用多维度规则筛选异常分录：假期/非工作时间录入、大额分录、约整数、重复分录、空摘要、模糊描述等。',
    linkedSheet: 'C24-5',
  },
  {
    seq: 8,
    name: '运用本福特定律测试对金额首位数分布进行分析。',
    hint: '利用本福特定律（首位数规律）检验分录金额分布是否异常。卡方检验显著时需关注偏离较大的数字。',
    linkedSheet: '本福特',
  },
  {
    seq: 9,
    name: '对高层调整分录、结账分录和抵消分录进行测试。',
    hint: '关注重大会计分录、与实体无关联的分录、权益类异常分录、与舞弊风险相关的分录及非惯常分录。',
    linkedSheet: 'C24-5',
  },
  {
    seq: 10,
    name: '汇总各项测试结果，形成会计分录细节测试的总体结论。',
    hint: '综合C24-1至C24-5及本福特测试结果，评价是否存在管理层通过不当日记账分录凌驾于控制之上的情况。',
    linkedSheet: 'C24-0',
  },
]

// ─── C24A 步骤状态 ───
const c24StepDialogVisible = ref(false)
const activeC24Step = ref<number | null>(null)
/** 步骤数据缓存 Map: `C24A-{seq}-{field}` → value */
const c24StepData = ref<Map<string, string>>(new Map())

function c24StepItemId(stepIdx: number, field: string): string {
  return `C24A-${stepIdx + 1}-${field}`
}

function getC24StepVal(stepIdx: number, field: string): string {
  return c24StepData.value.get(c24StepItemId(stepIdx, field)) || ''
}

function setC24StepVal(stepIdx: number, field: string, value: string | null): void {
  if (isReadonly.value) return
  const key = c24StepItemId(stepIdx, field)
  if (value) {
    c24StepData.value.set(key, value)
  } else {
    c24StepData.value.delete(key)
  }
  debounceSave()
}

function c24StepStatus(stepIdx: number): 'done' | 'wip' | 'todo' {
  if (getC24StepVal(stepIdx, 'conclusion')) return 'done'
  if (getC24StepVal(stepIdx, 'result') || getC24StepVal(stepIdx, 'applicable')) return 'wip'
  return 'todo'
}

function c24StepRowClass(stepIdx: number): Record<string, boolean> {
  const s = c24StepStatus(stepIdx)
  return { 'c24-step-done': s === 'done', 'c24-step-wip': s === 'wip' }
}

function c24ConclusionType(conclusion: string): string {
  if (conclusion === '已执行' || conclusion === '无异常') return 'success'
  if (conclusion === '有异常') return 'danger'
  return 'warning'
}

const c24StepDialogTitle = computed(() => {
  if (activeC24Step.value === null) return '步骤详情'
  const step = C24A_PROGRAMS[activeC24Step.value]
  return `步骤 ${step.seq}：${step.name.substring(0, 30)}...`
})

function openC24StepDialog(stepIdx: number): void {
  activeC24Step.value = stepIdx
  c24StepDialogVisible.value = true
}

function nextC24Step(): void {
  if (activeC24Step.value === null) return
  flushPendingSaves()
  const next = activeC24Step.value + 1
  if (next < C24A_PROGRAMS.length) {
    activeC24Step.value = next
  } else {
    c24StepDialogVisible.value = false
  }
}

function quickMarkC24Step(stepIdx: number): void {
  if (isReadonly.value) return
  setC24StepVal(stepIdx, 'applicable', 'Y')
  setC24StepVal(stepIdx, 'conclusion', '已执行')
}

// ─── navigate-sheet ───
function jumpToSheet(sheet: string): void {
  emit('navigate-sheet', sheet)
}

// ─── 主控台：测试项看板 + Dialog ───
const programCollapse = ref<string[]>([])

const completedStepCount = computed(() =>
  C24A_PROGRAMS.reduce((n, _, i) => (getC24StepVal(i, 'conclusion') ? n + 1 : n), 0),
)

interface TestItem {
  key: string
  icon: string
  title: string
  desc: string
}

const TEST_ITEMS: TestItem[] = [
  { key: 'C24-1', icon: '⚖️', title: 'C24-1 借贷发生额完整性', desc: 'Σ借 = Σ贷 一致性校验' },
  { key: 'C24-2', icon: '📊', title: 'C24-2 分录&余额表对比', desc: '按科目核对试算平衡表' },
  { key: 'C24-3', icon: '🔢', title: 'C24-3 跳号测试', desc: '凭证号连续性检测' },
  { key: 'C24-4', icon: '👤', title: 'C24-4 异常账户测试', desc: '人员/账户异常识别' },
  { key: 'C24-5', icon: '🔍', title: 'C24-5 异常分录测试', desc: '13 条规则筛选异常分录' },
  { key: 'benford', icon: '📈', title: '本福特定律测试', desc: '首位数分布卡方检验' },
]

const testDialogVisible = ref(false)
const activeTestKey = ref<string>('')

const testDialogTitle = computed(() => {
  const item = TEST_ITEMS.find(t => t.key === activeTestKey.value)
  return item ? item.title : '测试项'
})

/** 测试项状态：done(有结论) / active(有数据/指标) / todo */
function testStatus(key: string): 'done' | 'active' | 'todo' {
  if (conclusions.value[key]) return 'done'
  if (journalEntries.value.length === 0) return 'todo'
  return 'active'
}

function testCardClass(key: string): Record<string, boolean> {
  const s = testStatus(key)
  return { 'card-done': s === 'done', 'card-active': s === 'active' }
}

function testConclusionText(key: string): string {
  return conclusions.value[key] ? '已结论' : ''
}

function testConclusionType(key: string): string {
  const c = conclusions.value[key] || ''
  if (c.includes('异常') || c.includes('不一致') || c.includes('偏离')) return 'danger'
  return 'success'
}

/** 卡片关键指标（点点点看一眼即知结果） */
function testMetric(key: string): string {
  if (journalEntries.value.length === 0) return '待导入分录'
  switch (key) {
    case 'C24-1': {
      const diff = Math.abs(balanceResult.value.debitTotal - balanceResult.value.creditTotal)
      return balanceResult.value.balanced ? '借贷平衡 ✓' : `差额 ${fmtAmount(diff)} 元`
    }
    case 'C24-2': {
      const diffCount = trialBalanceComparisons.value.filter(c => Math.abs(c.diff) > 0.01).length
      return diffCount > 0 ? `${diffCount} 个科目有差异` : `${trialBalanceComparisons.value.length} 科目已核对`
    }
    case 'C24-3':
      return gapResults.value.length > 0 ? `${gapResults.value.length} 处跳号` : '无跳号 ✓'
    case 'C24-4':
      return `${accountRows.value.length} 个操作用户`
    case 'C24-5':
      return anomalyResults.value.length > 0 ? `${anomalyResults.value.length} 条异常分录` : '未筛选出异常 ✓'
    case 'benford':
      if (benfordSampleCount.value === 0) return '待分析'
      return benfordChi.value.significant ? '显著偏离 ⚠' : '符合分布 ✓'
    default:
      return ''
  }
}

function openTestDialog(key: string): void {
  activeTestKey.value = key
  testDialogVisible.value = true
}

const hasPrevTest = computed(() => TEST_ITEMS.findIndex(t => t.key === activeTestKey.value) > 0)
const hasNextTest = computed(() => {
  const idx = TEST_ITEMS.findIndex(t => t.key === activeTestKey.value)
  return idx >= 0 && idx < TEST_ITEMS.length - 1
})

function gotoAdjacentTest(delta: number): void {
  flushPendingSaves()
  const idx = TEST_ITEMS.findIndex(t => t.key === activeTestKey.value)
  const next = idx + delta
  if (next >= 0 && next < TEST_ITEMS.length) {
    activeTestKey.value = TEST_ITEMS[next].key
  }
}

/** 从程序步骤 Dialog 跳转到对应测试项 Dialog */
function jumpFromStepToTest(linkedSheet: string): void {
  const key = linkedSheet === '本福特' ? 'benford' : linkedSheet
  if (TEST_ITEMS.some(t => t.key === key)) {
    c24StepDialogVisible.value = false
    openTestDialog(key)
  } else {
    // C24-0 等非测试项 → 走外层 tab 跳转
    jumpToSheet(linkedSheet)
  }
}

// ─── Journal data source (序时账不重复落库全量分录) ───
const JOURNAL_SOURCE_ITEM = 'C24-journal-source'
type JournalDataSource = 'none' | 'ledger' | 'excel'
const journalDataSource = ref<JournalDataSource>('none')

function mapLedgerRow(r: Record<string, unknown>): JournalEntry {
  return {
    voucherDate: String(r.voucher_date || r.voucherDate || ''),
    voucherNo: String(r.voucher_no || r.voucherNo || ''),
    accountCode: String(r.account_code || r.accountCode || ''),
    accountName: String(r.account_name || r.accountName || ''),
    debit: Number(r.debit_amount || r.debitAmount || r.debit || 0),
    credit: Number(r.credit_amount || r.creditAmount || r.credit || 0),
    summary: String(r.summary || r.description || ''),
    preparer: String(r.preparer || ''),
    poster: String(r.poster || ''),
    reviewer: String(r.reviewer || ''),
  }
}

// ─── loadFromLedger 四表联动（使用项目级缓存） ───
const ledgerCache = useLedgerCache()

async function loadFromLedger(silent = false): Promise<void> {
  const year = effectiveYear.value
  if (isReadonly.value || !props.projectId || !year) {
    if (!silent) ElMessage.warning('缺少项目或年度信息，无法从序时账导入')
    return
  }

  // 手动触发时确认覆盖（缓存命中则跳过确认 — 只是从缓存读取，秒级）
  const hasCached = ledgerCache.hasCacheFor(props.projectId, year)
  if (!silent && !hasCached) {
    try {
      await ElMessageBox.confirm(
        '将从序时账（全量分录）导入数据，当前已有数据将被覆盖。确定继续？',
        '从序时账导入',
        { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return // user cancelled
    }
  }

  let loadingMsg: { close: () => void } | null = null
  if (!silent && !hasCached) {
    loadingMsg = ElMessage({ message: '正在从序时账拉取分录...', type: 'info', duration: 0 })
  }

  // 抑制全局超时弹窗
  ;(globalThis as any).__suppressTimeoutToast = true
  try {
    const cached = await ledgerCache.getEntries(props.projectId, year, {
      force: !silent && !hasCached, // 手动触发 + 无缓存 → 强制拉取
      onProgress: (loaded, total) => {
        if (loadingMsg && total > 0) {
          loadingMsg.close()
          loadingMsg = ElMessage({
            message: `正在导入分录 ${loaded.toLocaleString()} / ${total.toLocaleString()}...`,
            type: 'info',
            duration: 0,
          })
        }
      },
    })

    if (cached.length === 0) {
      if (!silent) ElMessage.warning('序时账中暂无分录数据，请确认已导入序时账')
      return
    }

    // 映射缓存数据到 JournalEntry
    journalEntries.value = cached.map(r => mapLedgerRow(r as unknown as Record<string, unknown>))
    journalDataSource.value = 'ledger'

    const cacheInfo = ledgerCache.getCacheInfo()
    if (!silent) {
      const suffix = cacheInfo && !cacheInfo.complete ? '（数据可能不完整）' : ''
      ElMessage.success(`成功加载 ${cached.length.toLocaleString()} 条分录${hasCached ? '（缓存）' : ''}，正在运行分析...${suffix}`)
    }
    runAllAnalytics()
    debounceSave()
  } catch (err: any) {
    if (!silent) {
      const isTimeout = err?.code === 'ECONNABORTED' || err?.message?.includes('timeout')
      if (isTimeout) {
        ElMessage.error('序时账分录量较大，请求超时。建议稍后重试或使用 Excel 导入。')
      } else if (err?.message !== '用户取消') {
        ElMessage.error('从序时账导入失败：' + (err?.message || '网络错误'))
      }
    }
    // 即使失败，缓存中如果有部分数据也可使用
    const cacheInfo = ledgerCache.getCacheInfo()
    if (cacheInfo && cacheInfo.count > 0 && journalEntries.value.length === 0) {
      const partial = await ledgerCache.getEntries(props.projectId, year)
      if (partial.length > 0) {
        journalEntries.value = partial.map(r => mapLedgerRow(r as unknown as Record<string, unknown>))
        journalDataSource.value = 'ledger'
        runAllAnalytics()
        debounceSave()
        if (!silent) {
          ElMessage.warning(`已加载部分分录（${partial.length.toLocaleString()} 条），可能不完整`)
        }
      }
    }
  } finally {
    ;(globalThis as any).__suppressTimeoutToast = false
    loadingMsg?.close()
  }
}

// ─── Journal entries (core data) ───
const journalEntries = ref<JournalEntry[]>([])
const trialBalance = ref<TrialBalanceRow[]>([])

// ─── C24-0 Summary form ───
const summaryForm = ref<C24SummaryFormData>({
  sourceAppName: '', sourceAppVersion: '', sourceExportTime: '',
  sourceFileRef: '', toolUsed: '', toolName: '', toolVersion: '',
  toolTime: '', conclusion: '',
})

// ─── Conclusions ───
const conclusions = ref<Record<string, string>>({
  'C24-1': '', 'C24-2': '', 'C24-3': '', 'C24-4': '', 'C24-5': '', 'benford': '',
})
const subConclusions = computed(() => conclusions.value)

// ─── C24-1 Balance Integrity ───
const balanceResult = ref<BalanceIntegrityResult>({ debitTotal: 0, creditTotal: 0, balanced: true })

// ─── C24-2 Trial Balance Comparison ───
const trialBalanceComparisons = ref<TrialBalanceComparison[]>([])

// ─── C24-3 Gap Test ───
const gapResults = ref<GapResult[]>([])
const gapNotes = ref<GapNote[]>([])

// ─── C24-4 Anomaly Accounts ───
const accountRows = ref<AccountRow[]>([])

// ─── C24-5 Anomaly Entries ───
const enabledRules = ref<string[]>([
  'holidays', 'night', 'frequent', 'large', 'approval',
  'round', 'tail', 'duplicate', 'unusual', 'volume',
  'special', 'vague', 'empty',
])
const ruleParams = ref<RuleParams>({
  nightStartHour: 22, nightEndHour: 6,
  largeAmountThreshold: 1000000, approvalLimit: 500000,
  roundAmountDigits: 4, vagueKeywordsText: '调整,暂估,其他,冲销',
})
const anomalyResults = ref<AnomalyResult[]>([])
const anomalyNotes = ref<AnomalyNote[]>([])

// ─── Benford ───
const benfordDist = ref<BenfordDigitResult[]>([])
const benfordChi = ref<BenfordTestResult>({ chi2Total: 0, criticalValue: 15.507, significant: false })
const benfordSampleCount = ref(0)
const benfordAlpha = ref(0.05)

// ─── Holidays ───
const holidays = ref<HolidayRow[]>([])

// ─── AI ───
const ai = useWpAiSuggest({ wpId: props.wpId, sheetName: 'C24' })

// ─── Import/Export ───
const importExport = useC24ImportExport(computed(() => props.wpId))
const fileInputRef = ref<HTMLInputElement | null>(null)

function onImportExportCommand(command: string) {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate()
      break
    case 'exportData':
      importExport.exportData()
      break
    case 'importData':
      fileInputRef.value?.click()
      break
  }
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  // Reset file input so same file can be re-selected
  input.value = ''
  const result = await importExport.importData(file)
  if (result && result.rowCount > 0) {
    // Re-load data after successful import then re-run analytics
    await selfLoad()
  }
}

// ─── Debounce ───
let saveTimer: ReturnType<typeof setTimeout> | null = null

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { persistAll() }, 2000)
}

function flushPendingSaves() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistAll()
  }
}

// ─── Analytics engine runner ───
function runAllAnalytics() {
  if (journalEntries.value.length === 0) return

  // C24-1 Balance integrity
  balanceResult.value = calcBalanceIntegrity(journalEntries.value)

  // C24-2 Trial balance comparison
  trialBalanceComparisons.value = compareToTrialBalance(journalEntries.value, trialBalance.value)

  // C24-3 Gap detection
  const voucherNos = journalEntries.value.map(e => e.voucherNo).filter(Boolean)
  gapResults.value = detectGaps(voucherNos)
  // Ensure gapNotes matches length
  while (gapNotes.value.length < gapResults.value.length) {
    gapNotes.value.push({ abnormal: '', note: '' })
  }

  // C24-4 Account analysis
  buildAccountRows()

  // C24-5 Anomaly screening
  runAnomalyScreen()

  // Benford
  runBenfordAnalysis()
}

function buildAccountRows() {
  const userStats = new Map<string, { prepare: number; post: number; review: number }>()
  for (const e of journalEntries.value) {
    if (e.preparer) {
      const s = userStats.get(e.preparer) || { prepare: 0, post: 0, review: 0 }
      s.prepare++
      userStats.set(e.preparer, s)
    }
    if (e.poster) {
      const s = userStats.get(e.poster) || { prepare: 0, post: 0, review: 0 }
      s.post++
      userStats.set(e.poster, s)
    }
    if (e.reviewer) {
      const s = userStats.get(e.reviewer) || { prepare: 0, post: 0, review: 0 }
      s.review++
      userStats.set(e.reviewer, s)
    }
  }

  // Preserve existing user-editable fields
  const existingMap = new Map(accountRows.value.map(r => [r.user, r]))
  const rows: AccountRow[] = []
  for (const [user, stats] of userStats) {
    const existing = existingMap.get(user)
    rows.push({
      user,
      role: existing?.role || '',
      prepareCount: stats.prepare,
      postCount: stats.post,
      reviewCount: stats.review,
      inList: false, // TODO: cross-check with C23 personnel
      abnormal: existing?.abnormal || '',
      note: existing?.note || '',
      conclusion: existing?.conclusion || '',
      indexRef: existing?.indexRef || '',
    })
  }
  accountRows.value = rows
}

function runAnomalyScreen() {
  if (journalEntries.value.length === 0) return
  const rules: AnomalyRules = {
    holidays: enabledRules.value.includes('holidays')
      ? holidays.value.map(h => h.date).filter(Boolean)
      : [],
    nightStartHour: enabledRules.value.includes('night') ? ruleParams.value.nightStartHour : 99,
    nightEndHour: enabledRules.value.includes('night') ? ruleParams.value.nightEndHour : 0,
    largeAmountThreshold: enabledRules.value.includes('large') ? ruleParams.value.largeAmountThreshold : Infinity,
    approvalLimit: enabledRules.value.includes('approval') ? ruleParams.value.approvalLimit : 0,
    roundAmountDigits: enabledRules.value.includes('round') ? ruleParams.value.roundAmountDigits : 0,
    vagueKeywords: enabledRules.value.includes('vague')
      ? ruleParams.value.vagueKeywordsText.split(',').map(s => s.trim()).filter(Boolean)
      : [],
    checkEmptySummary: enabledRules.value.includes('empty'),
    duplicateCheck: enabledRules.value.includes('duplicate'),
  }
  anomalyResults.value = screenAnomalies(journalEntries.value, rules)
  // Preserve existing notes
  while (anomalyNotes.value.length < anomalyResults.value.length) {
    anomalyNotes.value.push({ checkContent: '', conclusion: '', indexRef: '' })
  }
  anomalyNotes.value.length = anomalyResults.value.length
}

function runBenfordAnalysis() {
  const amounts = journalEntries.value
    .map(e => Math.max(e.debit, e.credit))
    .filter(a => a > 0)
  benfordSampleCount.value = amounts.length
  benfordDist.value = benfordDistribution(amounts)
  benfordChi.value = benfordChiSquareTest(benfordDist.value, benfordAlpha.value)
}

// ─── Event handlers ───

function onSummaryFieldChange(field: keyof C24SummaryFormData, value: string) {
  (summaryForm.value as any)[field] = value
  if (field === 'conclusion') {
    saveConclusion('C24-0-conclusion', value)
  } else {
    debounceSave()
  }
}

function onConclusionChange(key: string, value: string) {
  conclusions.value[key] = value
  const itemId = key === 'benford' ? 'C24-benford-conclusion' : `${key}-conclusion`
  saveConclusion(itemId, value)
  // Req 11.2: 结论回填 C24-0 汇总表（即时保存 + 保留来源索引 Req 11.4）
  writeConclusionToSummary(key, value)
}

/**
 * Req 11.2 + 11.4: 测试项结论变更 → 回填 C24-0 汇总表对应测试项
 * 保留来源测试项索引用于双向追溯
 */
function writeConclusionToSummary(sourceKey: string, conclusionText: string) {
  if (!props.wpId || isReadonly.value) return
  // 持久化到 C24-0 summary 的 subConclusions（item_id 带来源标识）
  const sourceIndex = sourceKey === 'benford' ? 'C24-本福特' : sourceKey
  const summaryItemId = `C24-0-sub-${sourceKey}`
  // 写入 conclusion=结论文本, remark=来源测试项索引
  api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    project_id: props.projectId || undefined,
    items: [{ item_id: summaryItemId, conclusion: conclusionText || null, remark: sourceIndex }],
  }).catch(() => { /* silent - best effort */ })
}

/** Req 11.2: 异常分录结论变更时触发刷新（来自 C24AnomalyEntrySheet） */
function onSubConclusionRefresh() {
  // 子表结论变更会触发 C24-5 整体结论的联动感知，但不自动覆盖
  // 主要通过 onConclusionChange 路径走回填
}

function onGapNoteChange(index: number, field: 'abnormal' | 'note', value: string) {
  if (!gapNotes.value[index]) gapNotes.value[index] = { abnormal: '', note: '' }
  gapNotes.value[index][field] = value
  debounceSave()
}

function onAccountRowChange(index: number, field: string, value: string) {
  if (accountRows.value[index]) {
    ;(accountRows.value[index] as any)[field] = value
    debounceSave()
  }
}

function onEnabledRulesChange(rules: string[]) {
  enabledRules.value = rules
  debounceSave()
}

function onRuleParamChange(key: keyof RuleParams, value: any) {
  ;(ruleParams.value as any)[key] = value
  debounceSave()
}

function onAnomalyNoteChange(index: number, field: string, value: string) {
  if (!anomalyNotes.value[index]) anomalyNotes.value[index] = { checkContent: '', conclusion: '' }
  ;(anomalyNotes.value[index] as any)[field] = value
  debounceSave()
}

function onAddHoliday() {
  if (isReadonly.value) return
  holidays.value.push({ date: '', name: '' })
  debounceSave()
}

function onRemoveHoliday(index: number) {
  if (isReadonly.value) return
  holidays.value.splice(index, 1)
  debounceSave()
}

function onUpdateHoliday(index: number, field: 'date' | 'name', value: string) {
  if (isReadonly.value) return
  holidays.value[index][field] = value
  debounceSave()
}

async function onAiSuggest(fieldId: string) {
  if (isReadonly.value || !ai.aiEnabled.value) return
  const fieldName = fieldId.replace('C24-', '').replace('-conclusion', '') + ' 测试结论'
  let currentVal = ''
  if (fieldId === 'C24-0-conclusion') currentVal = summaryForm.value.conclusion
  else if (fieldId === 'C24-benford-conclusion') currentVal = conclusions.value['benford']
  else {
    const key = fieldId.replace('-conclusion', '')
    currentVal = conclusions.value[key] || ''
  }
  await ai.requestSuggestion(fieldName, currentVal)
  const text = ai.adoptSuggestion()
  if (text) {
    if (fieldId === 'C24-0-conclusion') {
      summaryForm.value.conclusion = text
      saveConclusion('C24-0-conclusion', text)
    } else if (fieldId === 'C24-benford-conclusion') {
      conclusions.value['benford'] = text
      saveConclusion('C24-benford-conclusion', text)
    } else {
      const key = fieldId.replace('-conclusion', '')
      conclusions.value[key] = text
      saveConclusion(fieldId, text)
    }
  }
}

// ─── Persistence ───

async function saveConclusion(itemId: string, value: string) {
  if (!props.wpId || isReadonly.value) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: itemId, conclusion: value || null, remark: null }],
    })
    emit('save')
  } catch { /* silent */ }
}

async function persistAll() {
  if (!props.wpId || isReadonly.value) return
  const items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }> = []

  // C24-0 summary fields
  items.push({ item_id: 'C24-0-source-appName', conclusion: null, remark: summaryForm.value.sourceAppName || null })
  items.push({ item_id: 'C24-0-source-appVersion', conclusion: null, remark: summaryForm.value.sourceAppVersion || null })
  items.push({ item_id: 'C24-0-source-exportTime', conclusion: null, remark: summaryForm.value.sourceExportTime || null })
  items.push({ item_id: 'C24-0-source-fileRef', conclusion: null, remark: summaryForm.value.sourceFileRef || null })
  items.push({ item_id: 'C24-0-tool-used', conclusion: summaryForm.value.toolUsed || null, remark: null })
  items.push({ item_id: 'C24-0-tool-name', conclusion: summaryForm.value.toolName || null, remark: null })
  items.push({ item_id: 'C24-0-tool-version', conclusion: null, remark: summaryForm.value.toolVersion || null })
  items.push({ item_id: 'C24-0-tool-time', conclusion: null, remark: summaryForm.value.toolTime || null })
  items.push({ item_id: 'C24-0-conclusion', conclusion: summaryForm.value.conclusion || null, remark: null })

  // C24A 程序步骤
  for (const [key, val] of c24StepData.value) {
    items.push({ item_id: key, conclusion: val || null, remark: val || null })
  }

  // Conclusions
  for (const [key, val] of Object.entries(conclusions.value)) {
    const itemId = key === 'benford' ? 'C24-benford-conclusion' : `${key}-conclusion`
    items.push({ item_id: itemId, conclusion: val || null, remark: null })
  }

  // 序时账导入：只存来源元数据，避免 30 万+ 行 JSON 撑爆请求体
  if (journalDataSource.value === 'ledger') {
    items.push({
      item_id: JOURNAL_SOURCE_ITEM,
      conclusion: null,
      remark: JSON.stringify({
        source: 'ledger',
        year: effectiveYear.value,
        count: journalEntries.value.length,
        importedAt: new Date().toISOString(),
      }),
    })
    items.push({ item_id: 'C24-journal-entries', conclusion: null, remark: '[]' })
  } else {
    items.push({ item_id: 'C24-journal-entries', conclusion: null, remark: JSON.stringify(journalEntries.value) })
    if (journalEntries.value.length > 0) {
      items.push({
        item_id: JOURNAL_SOURCE_ITEM,
        conclusion: null,
        remark: JSON.stringify({ source: 'excel', count: journalEntries.value.length }),
      })
    }
  }

  // Gap notes
  gapNotes.value.forEach((gn, i) => {
    items.push({ item_id: `C24-3-gap-${i}-abnormal`, conclusion: gn.abnormal || null, remark: null })
    items.push({ item_id: `C24-3-gap-${i}-note`, conclusion: null, remark: gn.note || null })
  })

  // Account rows (user-editable fields only)
  accountRows.value.forEach((row, i) => {
    items.push({ item_id: `C24-4-row-${i}-role`, conclusion: null, remark: row.role || null })
    items.push({ item_id: `C24-4-row-${i}-abnormal`, conclusion: row.abnormal || null, remark: null })
    items.push({ item_id: `C24-4-row-${i}-note`, conclusion: null, remark: row.note || null })
    items.push({ item_id: `C24-4-row-${i}-conclusion`, conclusion: row.conclusion || null, remark: null })
    items.push({ item_id: `C24-4-row-${i}-indexRef`, conclusion: null, remark: row.indexRef || null })
  })

  // C24-5 rules config
  items.push({
    item_id: 'C24-5-rules',
    conclusion: null,
    remark: JSON.stringify({ enabledRules: enabledRules.value, params: ruleParams.value }),
  })

  // Anomaly notes — JSON 打包存储（避免逐行存储产生百万级记录）
  const filledNotes = anomalyNotes.value.filter(an => an.checkContent || an.conclusion || an.indexRef)
  items.push({
    item_id: 'C24-5-anomaly-notes',
    conclusion: null,
    remark: filledNotes.length > 0 ? JSON.stringify(filledNotes) : null,
  })

  // Holidays
  items.push({ item_id: 'C24-holidays', conclusion: null, remark: JSON.stringify(holidays.value) })

  // Benford params
  items.push({ item_id: 'C24-benford-alpha', conclusion: null, remark: String(benfordAlpha.value) })

  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items,
    })
    emit('save')
  } catch (err: any) {
    ElMessage.error('保存失败，数据已保留在本地')
    console.warn('[C24] persist failed:', err)
  }
}

// ─── selfLoad ───
async function selfLoad() {
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> = Array.isArray(res) ? res : (res as any)?.data || []

    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const item of items) {
      if (item.item_id?.startsWith('C24-') || item.item_id?.startsWith('C24A-')) {
        map.set(item.item_id, { conclusion: item.conclusion, remark: item.remark })
      }
    }

    // Summary fields
    summaryForm.value.sourceAppName = map.get('C24-0-source-appName')?.remark || ''
    summaryForm.value.sourceAppVersion = map.get('C24-0-source-appVersion')?.remark || ''
    summaryForm.value.sourceExportTime = map.get('C24-0-source-exportTime')?.remark || ''
    summaryForm.value.sourceFileRef = map.get('C24-0-source-fileRef')?.remark || ''
    summaryForm.value.toolUsed = map.get('C24-0-tool-used')?.conclusion || ''
    summaryForm.value.toolName = map.get('C24-0-tool-name')?.conclusion || ''
    summaryForm.value.toolVersion = map.get('C24-0-tool-version')?.remark || ''
    summaryForm.value.toolTime = map.get('C24-0-tool-time')?.remark || ''
    summaryForm.value.conclusion = map.get('C24-0-conclusion')?.conclusion || ''

    // C24A 程序步骤数据
    for (let i = 0; i < C24A_PROGRAMS.length; i++) {
      const fields = ['applicable', 'executor', 'result', 'conclusion', 'index']
      for (const field of fields) {
        const itemId = `C24A-${i + 1}-${field}`
        const entry = map.get(itemId)
        if (entry) {
          const val = entry.conclusion || entry.remark || ''
          if (val) c24StepData.value.set(itemId, val)
        }
      }
    }

    // Conclusions
    conclusions.value['C24-1'] = map.get('C24-1-conclusion')?.conclusion || ''
    conclusions.value['C24-2'] = map.get('C24-2-conclusion')?.conclusion || ''
    conclusions.value['C24-3'] = map.get('C24-3-conclusion')?.conclusion || ''
    conclusions.value['C24-4'] = map.get('C24-4-conclusion')?.conclusion || ''
    conclusions.value['C24-5'] = map.get('C24-5-conclusion')?.conclusion || ''
    conclusions.value['benford'] = map.get('C24-benford-conclusion')?.conclusion || ''

    // Journal entries / data source
    journalDataSource.value = 'none'
    const sourceRemark = map.get(JOURNAL_SOURCE_ITEM)?.remark
    if (sourceRemark) {
      try {
        const meta = JSON.parse(sourceRemark) as { source?: string; year?: number }
        if (meta.source === 'ledger') {
          journalDataSource.value = 'ledger'
        } else if (meta.source === 'excel') {
          journalDataSource.value = 'excel'
        }
      } catch { /* ignore */ }
    }

    const jeRemark = map.get('C24-journal-entries')?.remark
    if (journalDataSource.value !== 'ledger' && jeRemark) {
      try {
        const parsed = JSON.parse(jeRemark)
        journalEntries.value = Array.isArray(parsed) ? parsed : []
        if (journalEntries.value.length > 0 && journalDataSource.value === 'none') {
          journalDataSource.value = 'excel'
        }
      } catch { journalEntries.value = [] }
    } else {
      journalEntries.value = []
    }

    // Holidays
    const holRemark = map.get('C24-holidays')?.remark
    if (holRemark) {
      try { holidays.value = JSON.parse(holRemark) } catch { holidays.value = [] }
    }

    // C24-5 rules config
    const rulesRemark = map.get('C24-5-rules')?.remark
    if (rulesRemark) {
      try {
        const parsed = JSON.parse(rulesRemark)
        if (parsed.enabledRules) enabledRules.value = parsed.enabledRules
        if (parsed.params) Object.assign(ruleParams.value, parsed.params)
      } catch { /* use defaults */ }
    }

    // Benford alpha
    const alphaStr = map.get('C24-benford-alpha')?.remark
    if (alphaStr) benfordAlpha.value = parseFloat(alphaStr) || 0.05

    // Gap notes
    const loadedGapNotes: GapNote[] = []
    for (let i = 0; i < 100; i++) {
      const abn = map.get(`C24-3-gap-${i}-abnormal`)
      const note = map.get(`C24-3-gap-${i}-note`)
      if (!abn && !note) break
      loadedGapNotes.push({ abnormal: abn?.conclusion || '', note: note?.remark || '' })
    }
    gapNotes.value = loadedGapNotes

    // Account row editable fields
    const loadedAccountEdits: Array<{ role: string; abnormal: string; note: string; conclusion: string; indexRef: string }> = []
    for (let i = 0; i < 200; i++) {
      const role = map.get(`C24-4-row-${i}-role`)
      if (!role && !map.get(`C24-4-row-${i}-abnormal`)) break
      loadedAccountEdits.push({
        role: role?.remark || '',
        abnormal: map.get(`C24-4-row-${i}-abnormal`)?.conclusion || '',
        note: map.get(`C24-4-row-${i}-note`)?.remark || '',
        conclusion: map.get(`C24-4-row-${i}-conclusion`)?.conclusion || '',
        indexRef: map.get(`C24-4-row-${i}-indexRef`)?.remark || '',
      })
    }

    // Anomaly notes
    // Anomaly notes — 从 JSON 打包格式加载（兼容旧逐行格式）
    const anomalyNotesJson = map.get('C24-5-anomaly-notes')?.remark
    const loadedAnomalyNotes: AnomalyNote[] = []
    if (anomalyNotesJson) {
      try {
        const parsed = JSON.parse(anomalyNotesJson)
        if (Array.isArray(parsed)) {
          for (const an of parsed) {
            loadedAnomalyNotes.push({
              checkContent: an.checkContent || '',
              conclusion: an.conclusion || '',
              indexRef: an.indexRef || '',
            })
          }
        }
      } catch { /* ignore parse errors */ }
    } else {
      // 兼容旧格式（逐行存储，最多读 500 行）
      for (let i = 0; i < 500; i++) {
        const cc = map.get(`C24-5-row-${i}-checkContent`)
        const conc = map.get(`C24-5-row-${i}-conclusion`)
        const idxRef = map.get(`C24-5-row-${i}-indexRef`)
        if (!cc && !conc && !idxRef) break
        loadedAnomalyNotes.push({
          checkContent: cc?.remark || '',
          conclusion: conc?.conclusion || '',
          indexRef: idxRef?.remark || '',
        })
      }
    }
    anomalyNotes.value = loadedAnomalyNotes

    // Run analytics after loading data
    if (journalEntries.value.length > 0) {
      runAllAnalytics()
      // Merge loaded account edits into computed account rows
      accountRows.value.forEach((row, i) => {
        if (loadedAccountEdits[i]) {
          row.role = loadedAccountEdits[i].role || row.role
          row.abnormal = loadedAccountEdits[i].abnormal || row.abnormal
          row.note = loadedAccountEdits[i].note || row.note
          row.conclusion = loadedAccountEdits[i].conclusion || row.conclusion
          row.indexRef = loadedAccountEdits[i].indexRef || row.indexRef
        }
      })
    }
  } catch (err) {
    console.warn('[GtC24JournalDetail] selfLoad failed:', err)
  } finally {
    isLoading.value = false
    const canAutoImport = props.projectId
      && effectiveYear.value
      && !isReadonly.value
      && currentSheet.value !== 'C24-0'
      && currentSheet.value !== '假期清单'
      && currentSheet.value !== '本福特-数据'

    // 序时账来源：重新从 ledger 拉全量（不读 checklist 大 JSON）
    if (canAutoImport && journalDataSource.value === 'ledger') {
      await loadFromLedger(true)
      return
    }

    // 无分录时首次自动从序时账拉取（含 C24A 主控台）
    if (canAutoImport && journalEntries.value.length === 0) {
      await loadFromLedger(true)
    }
  }
}

// ─── Lifecycle ───
onMounted(async () => {
  if (props.projectId) {
    try {
      const store = useProjectStore()
      if (store.projectId !== props.projectId || !store.auditYear) {
        await store.loadProjectContext(props.projectId)
      }
    } catch { /* unit tests without pinia */ }
  }
  await selfLoad()
})
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: selfLoad })
</script>

<style scoped>
.gt-c24-journal-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.c24-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 0 4px;
}
.toolbar-left {}
.toolbar-right {
  display: flex;
  gap: 8px;
}
.loading-container {
  padding: 24px;
}
.guidance-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #d9ecff 100%);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.guidance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  margin-bottom: 12px;
}
.guidance-header .el-icon {
  color: #409eff;
  font-size: 16px;
}
.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 6px;
}
.step-num {
  font-weight: 700;
  color: #409eff;
  font-size: 14px;
}
.step-text {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

/* ─── C24A 程序表样式 ─── */
.c24-program-html {
  margin-bottom: 16px;
}
.c24-grid-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
}
.c24-grid-table th,
.c24-grid-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  text-align: left;
}
.c24-grid-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #606266;
  font-size: 12px;
}
.c24-step-row {
  cursor: pointer;
  transition: background 0.15s;
}
.c24-step-row:hover {
  background: #ecf5ff;
}
.c24-step-done {
  background: #f0f9eb;
}
.c24-step-done:hover {
  background: #e1f3d8;
}
.c24-step-wip {
  background: #fdf6ec;
}
.c24-step-wip:hover {
  background: #faecd8;
}
.c24-cell-idx {
  text-align: center;
  font-weight: 600;
  color: #409eff;
}
.c24-cell-center {
  text-align: center;
}
.c24-cell-name {
  line-height: 1.5;
}
.c24-step-text {
  font-size: var(--wp-font-size, 13px);
}
.c24-cell-empty {
  color: #c0c4cc;
}
.c24-index-link {
  color: #409eff;
  cursor: pointer;
  text-decoration: underline;
}
.c24-edit-hint {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3cd 100%);
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.c24-edit-hint-head {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  margin-bottom: 4px;
}
.c24-edit-hint-body {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
.c24-dialog-link {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #dcdfe6;
}
.c24-link-area {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

/* ─── 空数据引导区 ─── */
.c24-empty-data-guide {
  padding: 40px 20px;
  text-align: center;
}
.c24-empty-data-guide p {
  color: #909399;
  margin: 8px 0 16px;
}

/* ─── 主控台 ─── */
.c24-console {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
/* 数据源卡片 */
.c24-datasource-card :deep(.el-card__body) {
  padding: 14px 16px;
}
.ds-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.ds-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}
.ds-actions {
  display: flex;
  gap: 8px;
}
.ds-stats {
  display: flex;
  align-items: center;
  gap: 28px;
  flex-wrap: wrap;
}
.ds-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ds-num {
  font-size: 24px;
  font-weight: 700;
  color: #4b2d77;
  line-height: 1.1;
}
.ds-num-sm {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  line-height: 1.1;
}
.ds-lbl {
  font-size: 12px;
  color: #909399;
}
.ds-stat-tag {
  margin-left: auto;
}

/* 测试项看板 */
.c24-test-board {
  background: #fff;
}
.board-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  margin-bottom: 12px;
}
.board-hint {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}
.test-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.test-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.18s;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.test-card:hover {
  border-color: #4b2d77;
  box-shadow: 0 4px 12px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}
.test-card.card-done {
  background: #f0f9eb;
  border-color: #c2e7b0;
}
.test-card.card-active {
  border-color: #d3adf7;
}
.test-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.test-icon {
  font-size: 22px;
}
.test-status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.dot-done { background: #67c23a; }
.dot-active { background: #e6a23c; }
.dot-todo { background: #dcdfe6; }
.test-name {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.test-desc {
  font-size: 12px;
  color: #909399;
}
.test-metric {
  font-size: var(--wp-font-size, 13px);
  color: #4b2d77;
  font-weight: 600;
  margin-top: 2px;
}
.test-footer {
  margin-top: 4px;
}
.test-todo {
  font-size: 12px;
  color: #409eff;
}

/* 审计程序折叠 */
.c24-program-collapse {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 0 12px;
}
.collapse-title {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

/* 汇总结论卡片 */
.scc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.scc-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

/* 测试项 Dialog */
.c24-test-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
  max-height: 78vh;
  overflow-y: auto;
}
.test-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.test-dialog-nav {
  display: flex;
  gap: 8px;
}
</style>
