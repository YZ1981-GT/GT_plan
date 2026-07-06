<template>
  <div class="c1-entity-control" :class="{ 'is-readonly': isReadonly }">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="c1-loading">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- ═══ L0 Main Console: 单页向导中控台 ═══ -->

      <!-- 蓝色渐变引导区（4步骤） -->
      <div class="c1-guide">
        <div class="c1-guide-head">
          <el-icon class="c1-guide-head-icon"><InfoFilled /></el-icon>
          C1 企业层面控制测试 · 操作指引
        </div>
        <div class="c1-guide-grid">
          <div v-for="s in GUIDE_STEPS" :key="s.no" class="c1-guide-step">
            <span class="c1-guide-no">{{ s.no }}</span>
            <div class="c1-guide-txt">
              <div class="c1-guide-title">{{ s.title }}</div>
              <div class="c1-guide-desc">{{ s.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 总体完成度看板 -->
      <div class="c1-overall-progress-bar">
        <span class="c1-overall-progress-label">总体进度</span>
        <el-progress
          :percentage="overallProgressPercent"
          :stroke-width="12"
          :color="overallProgressPercent === 100 ? '#67C23A' : '#4b2d77'"
          style="flex: 1"
        />
        <span class="c1-overall-progress-text">{{ overallProgressPercent }}%（{{ completedStepCount }}/{{ totalApplicableStepCount }} 步骤）</span>
      </div>

      <!-- 九段测试程序 (el-collapse) -->
      <el-collapse v-model="activeSections" class="c1-section-nav">
        <el-collapse-item
          v-for="g in sectionGroups"
          :key="g.slug"
          :name="g.slug"
        >
          <template #title>
            <div class="c1-sec-head">
              <span class="c1-sec-title">{{ g.order }}. {{ g.title }}</span>
              <el-tag
                v-if="!g.defaultApplicable"
                size="small"
                type="info"
                effect="plain"
              >{{ g.note || '按需适用' }}</el-tag>
              <!-- 整段适用性裁剪开关 -->
              <span class="c1-sec-applicable" @click.stop>
                <span class="c1-applicable-label">适用</span>
                <el-switch
                  :model-value="isSectionApplicable(g.slug)"
                  :disabled="isReadonly"
                  size="small"
                  inline-prompt
                  active-text="是"
                  inactive-text="否"
                  @change="(val: any) => onToggleSectionApplicable(g.slug, !!val)"
                />
              </span>
              <el-progress
                class="c1-sec-progress"
                :percentage="sectionProgress(g.slug)"
                :stroke-width="8"
                :color="sectionProgress(g.slug) === 100 ? '#67C23A' : '#4b2d77'"
                style="width: 120px"
              />
            </div>
          </template>
          <div class="c1-sec-body">
            <!-- 不适用：显示裁剪理由 -->
            <div v-if="!isSectionApplicable(g.slug)" class="c1-sec-trimmed">
              <el-alert type="info" :closable="false" show-icon>
                <template #title>
                  本段已标记「不适用」，不参与完成进度统计。
                </template>
                <div class="c1-trim-reason">裁剪理由：{{ sectionReason(g.slug) || '（未填写）' }}</div>
              </el-alert>
            </div>
            <template v-else>
              <!-- 方法论上下文（琥珀色左边线区块） -->
              <div v-if="methodologyOf(g.slug)" class="c1-methodology">
                <el-icon class="c1-meth-icon"><InfoFilled /></el-icon>
                <span class="c1-meth-text">{{ methodologyOf(g.slug) }}</span>
              </div>
              <!-- 步骤行表格：点击行打开 L1 Step Dialog -->
              <table class="c1-grid-table c1-step-table">
                <thead>
                  <tr>
                    <th style="width: 40px">#</th>
                    <th style="min-width: 240px">程序名称</th>
                    <th style="width: 60px">状态</th>
                    <th style="width: 80px">适用?</th>
                    <th style="width: 100px">执行人</th>
                    <th style="width: 120px">结果</th>
                    <th style="width: 100px">索引</th>
                    <th v-if="!isReadonly" style="width: 70px">快捷</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(step, si) in groupedPrograms(g.slug)"
                    :key="step.row || si"
                    class="c1-step-row"
                    :class="stepRowClass(g.slug, si)"
                    @click="openStepDialog(g.slug, si, step)"
                  >
                    <td class="c1-cell-idx">{{ si + 1 }}</td>
                    <td class="c1-cell-name">
                      <span class="c1-step-name-text">{{ step.name || `步骤 ${si + 1}` }}</span>
                      <el-tag v-if="step.subItems && step.subItems.length" size="small" type="info" effect="plain" class="c1-sub-count">
                        {{ step.subItems.length }} 子项
                      </el-tag>
                    </td>
                    <td class="c1-cell-center">
                      <span v-if="stepStatus(g.slug, si) === 'done'" class="c1-status-done" title="已完成">✅</span>
                      <span v-else-if="stepStatus(g.slug, si) === 'wip'" class="c1-status-wip" title="进行中">🟡</span>
                      <span v-else class="c1-status-todo" title="未开始">⬜</span>
                    </td>
                    <td class="c1-cell-center">
                      <el-icon v-if="isStepApplicable(g.slug, si)" color="#67C23A"><Select /></el-icon>
                      <el-icon v-else-if="isStepApplicable(g.slug, si) === false" color="#909399"><CloseBold /></el-icon>
                      <span v-else class="c1-cell-empty">—</span>
                    </td>
                    <td>{{ getStepField(g.slug, si, 'executor') || '' }}</td>
                    <td>
                      <el-tag v-if="getStepConclusion(g.slug, si)" :type="conclusionTagType(getStepConclusion(g.slug, si))" size="small" effect="plain">
                        {{ getStepConclusion(g.slug, si) }}
                      </el-tag>
                      <span v-else class="c1-cell-empty">—</span>
                    </td>
                    <td>
                      <GtIndexChip
                        v-if="getStepField(g.slug, si, 'index')"
                        :value="getStepField(g.slug, si, 'index')"
                        :context-project-id="props.projectId"
                      />
                      <span v-else class="c1-cell-empty">—</span>
                    </td>
                    <td v-if="!isReadonly" class="c1-cell-center" @click.stop>
                      <el-button
                        v-if="stepStatus(g.slug, si) !== 'done'"
                        size="small"
                        type="success"
                        link
                        title="快速标记：适用 + 有效 + 当前用户"
                        @click="quickMarkStep(g.slug, si)"
                      >✓有效</el-button>
                      <span v-else class="c1-cell-empty">—</span>
                    </td>
                  </tr>
                  <tr v-if="groupedPrograms(g.slug).length === 0">
                    <td :colspan="isReadonly ? 7 : 8" class="c1-empty-row">本段暂无程序步骤数据</td>
                  </tr>
                </tbody>
              </table>
              <!-- 财务报告段特殊：过程记录按钮 -->
              <div v-if="g.slug === 'fr'" class="c1-fr-link">
                <el-button type="primary" plain size="small" @click="openProcessDialog">
                  📋 过程记录（C1-4 财报内控关键控制）
                </el-button>
              </div>
            </template>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- ═══ 整体结论 + 缺陷登记 (el-card) ═══ -->
      <el-card shadow="never" class="c1-card c1-conclusion-card">
        <template #header>
          <div class="c1-card-head">
            <span class="c1-card-title">企业层面控制整体结论</span>
            <el-tooltip content="就低聚合各适用段结论自动建议整体结论；用户可点选覆盖。结论变更时回写 B50 风险评估。" placement="top">
              <el-icon class="c1-meth-icon"><InfoFilled /></el-icon>
            </el-tooltip>
          </div>
        </template>
        <!-- 各段结论 -->
        <table class="c1-grid-table c1-conclusion-table">
          <thead>
            <tr>
              <th style="min-width: 200px">要素 / 段</th>
              <th style="min-width: 160px">本段测试结论</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in sectionGroups" :key="g.slug">
              <td class="c1-cell-name">
                {{ g.order }}. {{ g.title }}
                <el-tag v-if="!isSectionApplicable(g.slug)" size="small" type="info" effect="plain">不适用</el-tag>
              </td>
              <td>
                <div class="c1-sec-conclusion-cell">
                  <el-select
                    :model-value="getConclusion(sectionConclusionId(g.slug))"
                    :disabled="isReadonly || !isSectionApplicable(g.slug)"
                    size="small"
                    clearable
                    placeholder="结论"
                    @change="(v: any) => setSectionConclusion(g.slug, v)"
                  >
                    <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                  <el-button
                    v-if="!isReadonly && isSectionApplicable(g.slug) && suggestedSectionConclusion(g.slug) && !getConclusion(sectionConclusionId(g.slug))"
                    size="small"
                    type="warning"
                    link
                    @click="setSectionConclusion(g.slug, suggestedSectionConclusion(g.slug))"
                  >采用「{{ suggestedSectionConclusion(g.slug) }}」</el-button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <!-- 整体结论 -->
        <div class="c1-overall-row">
          <span class="c1-overall-label">企业层面控制整体结论</span>
          <el-select
            :model-value="overallConclusion"
            :disabled="isReadonly"
            size="small"
            clearable
            placeholder="请点选整体结论"
            class="c1-overall-select"
            @change="(v: any) => setOverallConclusion(v)"
          >
            <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <el-tag v-if="suggestedOverall" size="small" type="warning" effect="plain" class="c1-suggest-tag">
            建议：{{ suggestedOverall }}
          </el-tag>
          <el-button v-if="!isReadonly" size="small" type="primary" plain :disabled="!suggestedOverall" @click="applySuggestedOverall">采用建议</el-button>
        </div>
      </el-card>

      <!-- 识别缺陷 → 一键跳 A14 -->
      <el-card shadow="never" class="c1-card c1-defect-card">
        <template #header>
          <div class="c1-card-head">
            <span class="c1-card-title">识别的企业层面控制缺陷</span>
            <div class="c1-card-actions">
              <el-tooltip content="登记识别出的企业层面控制缺陷；点击 A14 chip 一键跳转缺陷评价底稿并带入摘要。" placement="top">
                <el-icon class="c1-meth-icon"><InfoFilled /></el-icon>
              </el-tooltip>
              <el-button v-if="!isReadonly" size="small" type="primary" @click="addDefectRow">+ 新增缺陷</el-button>
            </div>
          </div>
        </template>
        <table class="c1-grid-table c1-defect-table">
          <thead>
            <tr>
              <th style="width: 32px">#</th>
              <th style="min-width: 320px">缺陷摘要</th>
              <th style="width: 140px">缺陷评价</th>
              <th v-if="!isReadonly" style="width: 48px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in defectRows" :key="row.__did">
              <td class="c1-cell-idx">{{ i + 1 }}</td>
              <td>
                <el-input
                  :model-value="row.summary"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  size="small"
                  placeholder="描述识别出的企业层面控制缺陷（将带入 A14 缺陷评价）"
                  @input="(v: any) => onDefectSummary(i, v)"
                />
              </td>
              <td class="c1-defect-jump">
                <GtIndexChip :value="A14_WP_CODE" :context-project-id="props.projectId" @click="onDefectJumpToA14(i)" />
              </td>
              <td v-if="!isReadonly">
                <el-button type="danger" size="small" text @click="removeDefectRow(i)">删除</el-button>
              </td>
            </tr>
            <tr v-if="defectRows.length === 0">
              <td :colspan="isReadonly ? 3 : 4" class="c1-empty-row">
                暂无识别的企业层面控制缺陷{{ isReadonly ? '' : '，点击「+ 新增缺陷」登记' }}
              </td>
            </tr>
          </tbody>
        </table>
      </el-card>

      <!-- 右下角浮动按钮: 查看示例 -->
      <div class="c1-fab-area">
        <el-button type="primary" circle size="large" @click="exampleDrawerVisible = true" title="查看示例（C1-1~C1-3）">
          📖
        </el-button>
      </div>

      <!-- ═══ L1 Step Detail Dialog (el-dialog, 55% width) ═══ -->
      <el-dialog
        v-model="stepDialogVisible"
        :title="stepDialogTitle"
        width="55%"
        :close-on-click-modal="false"
        append-to-body
        class="c1-step-dialog"
      >
        <template v-if="activeStep">
          <!-- 方法论上下文 -->
          <div v-if="methodologyOf(activeStep.section)" class="c1-methodology">
            <el-icon class="c1-meth-icon"><InfoFilled /></el-icon>
            <span class="c1-meth-text">{{ methodologyOf(activeStep.section) }}</span>
          </div>

          <!-- ═══ 内嵌编制参考（该步骤有对应示例时显示） ═══ -->
          <div v-if="stepExampleRef" class="c1-step-example-ref">
            <div class="c1-step-example-head">
              <span>📋 编制参考（{{ stepExampleRef.source }}）</span>
              <el-button v-if="!isReadonly" size="small" type="primary" link @click="applyExampleToStep(stepExampleRef.id)">
                一键套用 →
              </el-button>
            </div>
            <div class="c1-step-example-body">
              <div class="c1-step-example-row">
                <span class="c1-step-example-label">控制点：</span>
                <span>{{ stepExampleRef.controlPoint }}</span>
              </div>
              <div class="c1-step-example-row">
                <span class="c1-step-example-label">测试方法：</span>
                <el-tag v-for="m in stepExampleRef.methods" :key="m" size="small" effect="plain" style="margin-right:4px">{{ m }}</el-tag>
              </div>
              <div class="c1-step-example-row">
                <span class="c1-step-example-label">样本量/频率：</span>
                <span>{{ stepExampleRef.sampleInfo }}</span>
              </div>
              <div class="c1-step-example-row">
                <span class="c1-step-example-label">测试程序摘要：</span>
                <span class="c1-step-example-desc">{{ stepExampleRef.procedure }}</span>
              </div>
              <div v-if="stepExampleRef.rollforward" class="c1-step-example-row">
                <span class="c1-step-example-label">前推测试：</span>
                <span class="c1-step-example-desc">{{ stepExampleRef.rollforward }}</span>
              </div>
              <div class="c1-step-example-row">
                <span class="c1-step-example-label">结论：</span>
                <el-tag type="success" size="small" effect="plain">{{ stepExampleRef.conclusion }}</el-tag>
              </div>
            </div>
          </div>

          <!-- 子项检查清单（来自源模板结构化子项） -->
          <div v-if="activeStep.step?.subItems?.length" class="c1-step-subitems">
            <div class="c1-subitem-head">
              该步骤包含以下检查事项：
              <span class="c1-subitem-actions">
                <el-button v-if="!isReadonly" size="small" link type="primary" @click="checkAllSubItems">全选</el-button>
                <el-button v-if="!isReadonly" size="small" link @click="uncheckAllSubItems">全不选</el-button>
                <el-button v-if="!isReadonly && checkedSubItems.length > 0" size="small" type="success" link @click="generateResultFromSubItems">
                  ✨ 根据勾选项生成结果描述
                </el-button>
              </span>
            </div>
            <el-checkbox-group v-model="checkedSubItems" :disabled="isReadonly">
              <div v-for="(sub, si) in activeStep.step.subItems" :key="si" class="c1-subitem-row">
                <el-checkbox :label="si" :value="si">{{ sub }}</el-checkbox>
              </div>
            </el-checkbox-group>
          </div>

          <el-form label-position="top" class="c1-step-form">
            <!-- 是否适用 -->
            <el-form-item label="是否适用">
              <el-radio-group
                :model-value="stepApplicableVal"
                :disabled="isReadonly"
                @change="(v: any) => onStepApplicableChange(v)"
              >
                <el-radio value="Y">适用</el-radio>
                <el-radio value="N">不适用</el-radio>
              </el-radio-group>
              <el-input
                v-if="stepApplicableVal === 'N'"
                :model-value="stepInapplicableReason"
                :disabled="isReadonly"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="不适用理由"
                class="c1-step-reason"
                @input="(v: any) => onStepReasonInput(v)"
              />
            </el-form-item>

            <!-- 测试方法 -->
            <el-form-item label="测试方法">
              <div class="c1-method-row">
                <el-checkbox-group
                  :model-value="stepMethodVal"
                  :disabled="isReadonly"
                  class="c1-method-group"
                  @change="(v: any) => onStepMethodChange(v)"
                >
                  <el-checkbox v-for="o in TEST_METHOD_OPTIONS" :key="o" :label="o" :value="o" />
                </el-checkbox-group>
                <el-tooltip v-if="stepMethodSuggestion && !stepMethodVal.length" :content="stepMethodSuggestion" placement="right">
                  <span class="c1-method-suggest">💡 建议</span>
                </el-tooltip>
              </div>
            </el-form-item>

            <!-- 执行人 -->
            <el-form-item label="执行人">
              <el-input
                :model-value="getActiveStepField('executor')"
                :disabled="isReadonly"
                size="default"
                placeholder="执行人"
                @input="(v: any) => setActiveStepText('executor', v)"
              />
            </el-form-item>

            <!-- 测试结果说明 -->
            <el-form-item label="测试结果说明">
              <div class="c1-field-with-ai">
                <el-input
                  :model-value="getActiveStepField('result')"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  placeholder="测试结果说明"
                  @input="(v: any) => setActiveStepText('result', v)"
                />
                <el-button v-if="!isReadonly" size="small" type="primary" plain :disabled="!aiEnabled" class="c1-ai-btn">
                  <el-icon><MagicStick /></el-icon> AI
                </el-button>
              </div>
            </el-form-item>

            <!-- 测试结论 -->
            <el-form-item label="测试结论">
              <el-select
                :model-value="getActiveStepConclusion()"
                :disabled="isReadonly"
                clearable
                placeholder="测试结论"
                @change="(v: any) => setActiveStepConclusion(v)"
              >
                <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>

            <!-- ═══ 前推测试（参照 C1-1 示例链路） ═══ -->
            <details class="c1-rollforward-details" :open="shouldShowRollforward">
              <summary class="c1-rollforward-summary">▶ 前推测试（期中→期末）</summary>
              <div class="c1-rollforward-content">
                <div class="c1-rollforward-hint">
                  <el-icon><InfoFilled /></el-icon>
                  如已于期中执行控制测试，需评估剩余期间是否前推。参照示例 C1-1：询问负责人确认流程是否变化。
                </div>
                <el-form-item label="是否执行前推测试">
                  <el-radio-group
                    :model-value="getActiveStepField('rollforward')"
                    :disabled="isReadonly"
                    @change="(v: any) => setActiveStepText('rollforward', v)"
                  >
                    <el-radio value="是">是</el-radio>
                    <el-radio value="否">否</el-radio>
                    <el-radio value="不适用">不适用（全年覆盖）</el-radio>
                  </el-radio-group>
                </el-form-item>
                <template v-if="getActiveStepField('rollforward') === '是'">
                  <el-form-item label="前推测试程序">
                    <div class="c1-field-with-ai">
                      <el-input
                        :model-value="getActiveStepField('rollforwardProc')"
                        :disabled="isReadonly"
                        type="textarea"
                        :autosize="{ minRows: 2, maxRows: 5 }"
                        placeholder="描述前推测试程序（如：询问人力资源部负责人，确定流程在剩余期间是否发生变化）"
                        @input="(v: any) => setActiveStepText('rollforwardProc', v)"
                      />
                      <el-button v-if="!isReadonly" size="small" type="primary" plain :disabled="!aiEnabled" class="c1-ai-btn">
                        <el-icon><MagicStick /></el-icon> AI
                      </el-button>
                    </div>
                  </el-form-item>
                  <el-form-item label="前推测试结果">
                    <el-input
                      :model-value="getActiveStepField('rollforwardResult')"
                      :disabled="isReadonly"
                      type="textarea"
                      :autosize="{ minRows: 2, maxRows: 5 }"
                      placeholder="前推测试结果（如：期中测试后未发生变化）"
                      @input="(v: any) => setActiveStepText('rollforwardResult', v)"
                    />
                  </el-form-item>
                </template>
              </div>
            </details>

            <!-- 索引号 -->
            <el-form-item label="索引号">
              <el-input
                :model-value="getActiveStepField('index')"
                :disabled="isReadonly"
                size="default"
                placeholder="关联底稿编码，如 C21-1、A14"
                @input="(v: any) => setActiveStepText('index', v)"
              />
              <div class="c1-ref-chips" style="margin-top: 4px">
                <GtIndexChip
                  v-for="(r, ri) in splitRefs(getActiveStepField('index'))"
                  :key="ri"
                  :value="r"
                  :context-project-id="props.projectId"
                />
              </div>
            </el-form-item>
          </el-form>
        </template>

        <template #footer>
          <el-button @click="stepDialogVisible = false">取消</el-button>
          <el-button type="primary" :disabled="isReadonly" @click="saveAndCloseStep">保存并关闭</el-button>
          <el-button type="primary" :disabled="isReadonly" @click="saveAndNextStep">保存并下一步 →</el-button>
        </template>
      </el-dialog>

      <!-- ═══ L1 Example Drawer (el-drawer, right, 45%) ═══ -->
      <el-drawer
        v-model="exampleDrawerVisible"
        title="测试示例参考（C1-1~C1-3）"
        direction="rtl"
        size="48%"
        append-to-body
        class="c1-example-drawer"
      >
        <el-alert
          title="示例（供参考），不参与进度。可点「参照此示例」将模板文字预填到步骤。"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <el-tabs v-model="activeExampleTab" type="border-card">
          <!-- ═══ C1-1 招聘背景调查 ═══ -->
          <el-tab-pane label="示例1：招聘" name="C1-1">
            <div class="c1-ex-card">
              <div class="c1-ex-section">
                <span class="c1-ex-label">对应程序：</span>
                <span class="c1-ex-val">1.4.1（控制环境 > 人力资源管理）</span>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">控制点：</span>
                <span class="c1-ex-val">对候选员工的背景调查和聘用审批</span>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">控制描述：</span>
                <div class="c1-ex-desc">
                  （1）拟聘用部门拟定招聘计划经部门负责人、人力资源部负责人和总经理批准后，由人力资源部负责招聘。
                  （2）应聘人员经人力资源部经理背景调查→面试→人力资源部+部门共同批准；重要岗位需总经理批准。
                  （3）被聘用人员签订标准劳动合同。
                </div>
              </div>
              <table class="c1-grid-table c1-ex-meta">
                <tbody>
                  <tr><td class="c1-ex-label">控制频率</td><td>每天多次</td></tr>
                  <tr><td class="c1-ex-label">控制属性</td><td>人工控制</td></tr>
                  <tr><td class="c1-ex-label">执行人</td><td>人力资源部负责人</td></tr>
                  <tr><td class="c1-ex-label">测试方法</td><td>抽样</td></tr>
                  <tr><td class="c1-ex-label">样本量</td><td>25（约 300 名新聘员工，每天多次人工控制）</td></tr>
                </tbody>
              </table>
              <div class="c1-ex-section">
                <span class="c1-ex-label">测试程序：</span>
                <div class="c1-ex-desc">
                  查阅 25 名新入职员工档案：招聘计划是否经审批→背景调查→聘用批准→签劳动合同。
                </div>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">样本表检查维度（10 列）：</span>
                <div class="c1-ex-desc">
                  ① 是否有招聘计划 ② 部门负责人审批 ③ 人力资源部审批 ④ 总经理审批
                  ⑤ 是否有背景调查 ⑥ 背景调查与职位相关 ⑦ 聘用经批准 ⑧ 签劳动合同 ⑨ 合同要素完整 ⑩ 结果
                </div>
              </div>
              <div class="c1-ex-section c1-ex-rollforward">
                <span class="c1-ex-label">前推测试：</span>
                <div class="c1-ex-desc">
                  <div>是否前推：<strong>是</strong></div>
                  <div>程序：询问人力资源部负责人，确定员工聘用流程在剩余期间是否发生变化。</div>
                  <div>结果：期中测试后未发生变化。</div>
                </div>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">结论：</span>
                <el-tag type="success" size="small" effect="plain">控制运行有效</el-tag>
              </div>
              <el-button v-if="!isReadonly" type="primary" size="small" style="margin-top: 12px" @click="applyExampleToStep('C1-1')">
                📋 参照此示例填写当前步骤
              </el-button>
            </div>
          </el-tab-pane>

          <!-- ═══ C1-2 审计委员会 ═══ -->
          <el-tab-pane label="示例2：审委会" name="C1-2">
            <div class="c1-ex-card">
              <div class="c1-ex-section">
                <span class="c1-ex-label">对应程序：</span>
                <span class="c1-ex-val">1.7（控制环境 > 审计委员会会议记录）</span>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">测试内容：</span>
                <div class="c1-ex-desc">
                  获取并阅读本年度全部审计委员会会议记录，评价会议频率、报告事项、后续跟踪及职责覆盖情况。
                </div>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">样本表检查维度（6 列）：</span>
                <div class="c1-ex-desc">
                  ① 会议日期 ② 会议名称 ③ 参加人 ④ 会议内容 ⑤ 是否后续跟踪 ⑥ 是否满足职责要求
                </div>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">结论：</span>
                <el-tag type="success" size="small" effect="plain">控制运行有效</el-tag>
              </div>
              <el-button v-if="!isReadonly" type="primary" size="small" style="margin-top: 12px" @click="applyExampleToStep('C1-2')">
                📋 参照此示例填写当前步骤
              </el-button>
            </div>
          </el-tab-pane>

          <!-- ═══ C1-3 审计委员会成员评价 ═══ -->
          <el-tab-pane label="示例3：成员评价" name="C1-3">
            <div class="c1-ex-card">
              <div class="c1-ex-section">
                <span class="c1-ex-label">对应程序：</span>
                <span class="c1-ex-val">1.8（控制环境 > 审计委员会成员独立性与胜任能力）</span>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">测试内容：</span>
                <div class="c1-ex-desc">
                  询问审计委员会主席成员情况，包括：成员基本情况（工作经验/职责/专长/提出问题实例）、评价周期、评价结果与措施、防止舞弊的控制措施、主席的观点。
                </div>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">检查内容结构：</span>
                <div class="c1-ex-desc">
                  1. 成员基本情况表（姓名/职位/工作经验/职责/专长/提问实例）<br/>
                  2. 评价周期：一年一次<br/>
                  3. 评价结果与后续措施表（姓名/职位/评价结果/后续措施）<br/>
                  4. 防舞弊控制措施列示<br/>
                  5. 审计委员会主席观点记录
                </div>
              </div>
              <div class="c1-ex-section">
                <span class="c1-ex-label">结论：</span>
                <el-tag type="success" size="small" effect="plain">控制运行有效</el-tag>
              </div>
              <el-button v-if="!isReadonly" type="primary" size="small" style="margin-top: 12px" @click="applyExampleToStep('C1-3')">
                📋 参照此示例填写当前步骤
              </el-button>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-drawer>

      <!-- ═══ L2 Process Record Dialog (el-dialog, fullscreen) ═══ -->
      <el-dialog
        v-model="processDialogVisible"
        title="C1-4 财报内控过程记录 — 关键控制汇总"
        fullscreen
        :close-on-click-modal="false"
        append-to-body
        class="c1-process-dialog"
      >
        <el-alert
          title="6 项关键控制汇总。点击「进入详情→」可查看/编辑过程记录明细。"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <el-card shadow="never" class="c1-card">
          <template #header>
            <div class="c1-card-head">
              <span class="c1-card-title">财报内控关键控制 — 测试说明</span>
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain :disabled="isReadonly || !aiEnabled" class="c1-ai-btn">
                  <el-icon><MagicStick /></el-icon> AI 辅助
                </el-button>
              </el-tooltip>
            </div>
          </template>
          <table class="c1-grid-table">
            <thead>
              <tr>
                <th style="width: 32px">#</th>
                <th style="min-width: 200px">关键控制</th>
                <th style="min-width: 120px">
                  <el-tooltip content="控制频率：源自客户控制描述" placement="top">
                    <span class="c1-judge-head">控制频率</span>
                  </el-tooltip>
                </th>
                <th style="min-width: 200px">
                  <el-tooltip content="测试方法（可多选）：询问和观察/检查/重新执行/抽样" placement="top">
                    <span class="c1-judge-head">测试方法</span>
                  </el-tooltip>
                </th>
                <th style="min-width: 120px">
                  <el-tooltip content="测试结论：有效/部分有效/无效" placement="top">
                    <span class="c1-judge-head">测试结论</span>
                  </el-tooltip>
                </th>
                <th style="width: 100px">详情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(name, i) in FR_SUMMARY_CONTROLS" :key="i">
                <td class="c1-cell-idx">{{ i + 1 }}</td>
                <td class="c1-cell-name">{{ name }}</td>
                <td>
                  <el-select
                    :model-value="getConclusion(summaryItemId(i + 1, 'freq'))"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    placeholder="频率"
                    @change="(v: any) => setEnum(summaryItemId(i + 1, 'freq'), v)"
                  >
                    <el-option v-for="o in FREQ_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </td>
                <td>
                  <el-checkbox-group
                    :model-value="getMultiEnum(summaryItemId(i + 1, 'method'))"
                    :disabled="isReadonly"
                    size="small"
                    class="c1-method-group"
                    @change="(v: any) => setMultiEnum(summaryItemId(i + 1, 'method'), v)"
                  >
                    <el-checkbox v-for="o in TEST_METHOD_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-checkbox-group>
                </td>
                <td>
                  <el-select
                    :model-value="getConclusion(summaryItemId(i + 1, 'conclusion'))"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    placeholder="结论"
                    @change="(v: any) => setEnum(summaryItemId(i + 1, 'conclusion'), v)"
                  >
                    <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </td>
                <td class="c1-cell-center">
                  <el-button type="primary" link size="small" @click="openDetailDialog(i)">
                    进入详情 →
                  </el-button>
                </td>
              </tr>
            </tbody>
          </table>
        </el-card>
      </el-dialog>

      <!-- ═══ L3 Detail Record Dialog (nested el-dialog, 70%) ═══ -->
      <el-dialog
        v-model="detailDialogVisible"
        :title="detailDialogTitle"
        width="70%"
        :close-on-click-modal="false"
        append-to-body
        class="c1-detail-dialog"
      >
        <template v-if="activeProcessIndex >= 0">
          <!-- 编制提示（源模板示例内容） -->
          <details class="c1-edit-hint" open>
            <summary class="c1-edit-hint-summary">📖 编制提示 — 源模板示例参考</summary>
            <div class="c1-edit-hint-body">
              <template v-if="activeProcessIndex === 0">
                <p><strong>C1-4-1 科目配比：</strong>由适当人员批准账户结构图的变更（FINC-US-002）</p>
                <p>示例控制描述：所有对总账主数据的更改均由财务总监监督。任何新建/删除/关闭账户需经公司秘书/董事长批准并保存记录。</p>
                <p>示例测试方法：<strong>重新执行</strong> — 选择期间发生变化的 GL 主数据样本，检查复核批准文件。</p>
              </template>
              <template v-else-if="activeProcessIndex === 1">
                <p><strong>C1-4-2 会计准则：</strong>评估方法和结果是否符合会计准则（FINC-US-001）</p>
                <p>示例控制描述：新的会计政策或变更经研究、记录、讨论后须经财务总监书面批准，必要时告知审计委员会。</p>
                <p>示例测试方法：<strong>询问和观察</strong> — 询问财务总监评估会计处理变更时的注意事项及资源；检查当年批准的政策变更记录。</p>
              </template>
              <template v-else-if="activeProcessIndex === 2">
                <p><strong>C1-4-3 合并关闭工作表：</strong>信息与结果追踪到原始分录账簿（FINC-US-014）</p>
                <p>示例控制描述：报告系统数据和本地会计系统的对账结果以书面记录。法定账户与报告系统生成软件包的对账须复核批准。</p>
                <p>示例测试方法：<strong>重新执行</strong> — 获取报告软件包，检查子分类账和试算平衡表对账记录；检查编制人和复核人签名。</p>
              </template>
              <template v-else-if="activeProcessIndex === 4">
                <p><strong>C1-4-5 非标准分录：</strong>检查分录，识别非重复分录（FINC-US-008）</p>
                <p>示例控制描述：根据交易性质将分录重分类为人工执行/重复分录，有助于发现异常及例外分录。</p>
                <p>示例测试方法：<strong>询问和观察</strong> — 询问财务总监如何划分标准/非标准分录；每月穿行测试对账软件包分类合理性。</p>
              </template>
              <template v-else-if="activeProcessIndex === 5">
                <p><strong>C1-4-6 财务报告：</strong>评估结果以确定符合会计准则（FINC-US-021/022）</p>
                <p>示例控制描述：财务总监对每条附注复核 GAAP 遵循性和披露一致性；对每个账户金额复核一致性和新准则适用性。</p>
                <p>示例测试方法：<strong>询问和观察</strong> — 向财务总监询问复核财务报表时注意事项；记录使用的数据来源是否符合准则。</p>
              </template>
              <p class="c1-edit-hint-note">💡 上述为源模板示例内容，请根据本项目实际情况修改填写。</p>
            </div>
          </details>

          <!-- 过程记录字段区 -->
          <table class="c1-grid-table c1-proc-table">
            <tbody>
              <tr v-for="f in processFieldsForActive" :key="f.key">
                <td class="c1-proc-label">{{ f.label }}</td>
                <td class="c1-proc-value">
                  <template v-if="f.type === 'freq'">
                    <el-select
                      :model-value="getConclusion(activeDetailItemId(f.key))"
                      :disabled="isReadonly"
                      size="small"
                      clearable
                      placeholder="请选择"
                      @change="(v: any) => setEnum(activeDetailItemId(f.key), v)"
                    >
                      <el-option v-for="o in FREQ_OPTIONS" :key="o" :label="o" :value="o" />
                    </el-select>
                  </template>
                  <template v-else-if="f.type === 'method'">
                    <el-checkbox-group
                      :model-value="getMultiEnum(activeDetailItemId(f.key))"
                      :disabled="isReadonly"
                      size="small"
                      class="c1-method-group"
                      @change="(v: any) => setMultiEnum(activeDetailItemId(f.key), v)"
                    >
                      <el-checkbox v-for="o in TEST_METHOD_OPTIONS" :key="o" :label="o" :value="o" />
                    </el-checkbox-group>
                  </template>
                  <template v-else>
                    <div class="c1-field-with-ai" v-if="f.key === 'howTest' || f.key === 'testResult'">
                      <el-input
                        :model-value="getRemark(activeDetailItemId(f.key)) || ''"
                        :disabled="isReadonly"
                        type="textarea"
                        :autosize="{ minRows: 2, maxRows: 6 }"
                        :placeholder="f.label"
                        @input="(v: any) => setTextDebounced(activeDetailItemId(f.key), v)"
                      />
                      <el-button v-if="!isReadonly" size="small" type="primary" plain :disabled="!aiEnabled" class="c1-ai-btn">
                        <el-icon><MagicStick /></el-icon> AI
                      </el-button>
                    </div>
                    <el-input
                      v-else
                      :model-value="getRemark(activeDetailItemId(f.key)) || ''"
                      :disabled="isReadonly"
                      type="textarea"
                      :autosize="{ minRows: 1, maxRows: 4 }"
                      :placeholder="f.label"
                      @input="(v: any) => setTextDebounced(activeDetailItemId(f.key), v)"
                    />
                  </template>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 📎 附件区 -->
          <div class="c1-ref-row" style="margin-top: 12px">
            <span class="c1-ref-label">📎 附件</span>
            <div class="c1-ref-body">
              <el-upload
                v-if="!isReadonly"
                :show-file-list="false"
                :auto-upload="false"
                accept="image/*,.pdf"
                class="c1-attach-upload"
                @change="(f: any) => onUploadProcOcr(f.raw || f)"
              >
                <el-button link size="small">上传附件 + OCR 识别</el-button>
              </el-upload>
              <el-tooltip v-if="procAttachName()" :content="procAttachName()" placement="top">
                <el-icon class="c1-attach-flag"><Paperclip /></el-icon>
              </el-tooltip>
            </div>
          </div>

          <!-- 关联底稿索引 -->
          <div class="c1-ref-row">
            <span class="c1-ref-label">关联底稿索引</span>
            <div class="c1-ref-body">
              <el-input
                v-if="!isReadonly"
                :model-value="getRemark(activeDetailItemId('refIndex')) || ''"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }"
                size="small"
                placeholder="输入关联底稿编码，如 C21-1、A14（多个用逗号分隔）"
                @input="(v: any) => setTextDebounced(activeDetailItemId('refIndex'), v)"
              />
              <div class="c1-ref-chips">
                <GtIndexChip
                  v-for="(r, ri) in splitRefs(getRemark(activeDetailItemId('refIndex')))"
                  :key="ri"
                  :value="r"
                  :context-project-id="props.projectId"
                />
                <span v-if="splitRefs(getRemark(activeDetailItemId('refIndex'))).length === 0" class="c1-ref-empty">—</span>
              </div>
            </div>
          </div>
          <!-- 过程记录结论（回写汇总表） -->
          <div class="c1-ref-row" style="margin-top: 12px">
            <span class="c1-ref-label">测试结论</span>
            <div class="c1-ref-body">
              <el-select
                :model-value="getConclusion(activeDetailItemId('conclusion'))"
                :disabled="isReadonly"
                size="small"
                clearable
                placeholder="过程记录测试结论"
                @change="(v: any) => onDetailConclusionChange(v)"
              >
                <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
              <span class="c1-sync-hint">保存后自动同步到汇总表</span>
            </div>
          </div>
        </template>

        <template #footer>
          <el-button @click="detailDialogVisible = false">关闭</el-button>
          <el-button type="primary" :disabled="isReadonly" @click="saveAndCloseDetail">保存并同步汇总</el-button>
        </template>
      </el-dialog>

      <!-- ═══ L3 Sample Table Dialog (for C1-4-4, nested el-dialog, 85%) ═══ -->
      <el-dialog
        v-model="sampleDialogVisible"
        title="C1-4-4 会计分录人工授权 — 样本测试"
        width="85%"
        :close-on-click-modal="false"
        append-to-body
        class="c1-sample-dialog"
      >
        <!-- 编制提示 -->
        <details class="c1-edit-hint">
          <summary class="c1-edit-hint-summary">📖 编制提示 — C1-4-4 会计分录人工授权（FINC-US-010）</summary>
          <div class="c1-edit-hint-body">
            <p><strong>控制描述：</strong>总账中的会计分录均由会计记录于正确会计期间，并有恰当解释和数据来源文档。会计分录由财务总监复核、批准和签名。</p>
            <p><strong>测试方法：</strong>抽样 — 从当期 25 个分录中挑选 2 个无偏、未分层的样本，检查是否经恰当人员批准。</p>
            <p><strong>样本表结构：</strong>按区域（如境内/境外）分组，每组列出：日期 | 账户编码 | 引用 | 交易描述 | 借方 | 贷方。多行明细组成一笔分录，借贷成对镜像，最终 Σ借 = Σ贷。</p>
            <p><strong>「a」标记：</strong>源模板中 "a" 表示该分录已通过批准检查（approved）。</p>
            <p class="c1-edit-hint-note">💡 可按区域新增分组标题行（如"境内"/"境外"），每笔分录可含多行明细。</p>
          </div>
        </details>

        <!-- 过程记录字段区（C1-4-4） -->
        <table class="c1-grid-table c1-proc-table">
          <tbody>
            <tr v-for="f in processFieldsForSample" :key="f.key">
              <td class="c1-proc-label">{{ f.label }}</td>
              <td class="c1-proc-value">
                <template v-if="f.type === 'freq'">
                  <el-select
                    :model-value="getConclusion(sampleProcItemId(f.key))"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    placeholder="请选择"
                    @change="(v: any) => setEnum(sampleProcItemId(f.key), v)"
                  >
                    <el-option v-for="o in FREQ_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
                <template v-else-if="f.type === 'method'">
                  <el-checkbox-group
                    :model-value="getMultiEnum(sampleProcItemId(f.key))"
                    :disabled="isReadonly"
                    size="small"
                    class="c1-method-group"
                    @change="(v: any) => setMultiEnum(sampleProcItemId(f.key), v)"
                  >
                    <el-checkbox v-for="o in TEST_METHOD_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-checkbox-group>
                </template>
                <template v-else>
                  <el-input
                    :model-value="getRemark(sampleProcItemId(f.key)) || ''"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    :placeholder="f.label"
                    @input="(v: any) => setTextDebounced(sampleProcItemId(f.key), v)"
                  />
                </template>
              </td>
            </tr>
          </tbody>
        </table>

        <el-divider />

        <!-- 样本明细表 -->
        <div class="c1-card-head" style="margin-bottom: 8px">
          <span class="c1-card-title">样本明细</span>
          <div class="c1-card-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :disabled="isReadonly || !aiEnabled" class="c1-ai-btn">
                <el-icon><MagicStick /></el-icon> AI 辅助
              </el-button>
            </el-tooltip>
            <el-button v-if="!isReadonly" type="warning" size="small" plain @click="addSampleGroupRow">+ 分组标题</el-button>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addSampleRow">+ 新增样本行</el-button>
          </div>
        </div>

        <table class="c1-grid-table c1-sample-table">
          <thead>
            <tr>
              <th style="width: 32px">#</th>
              <th style="min-width: 120px">日期</th>
              <th style="min-width: 120px">账户编码</th>
              <th style="min-width: 120px">引用</th>
              <th style="min-width: 200px">交易描述</th>
              <th style="min-width: 120px">借方金额（元）</th>
              <th style="min-width: 120px">贷方金额（元）</th>
              <th style="min-width: 120px">
                <el-tooltip content="源模板 C1-4-4 借贷勾稽公式：累计 Σ借方 − Σ贷方（只读派生）" placement="top">
                  <span class="c1-formula-head">累计借贷差<sup>ƒ</sup></span>
                </el-tooltip>
              </th>
              <th style="width: 96px">
                <el-tooltip content="上传凭证/记录图片或 PDF，OCR 识别后确认填入" placement="top">
                  <span class="c1-judge-head">📎 附件</span>
                </el-tooltip>
              </th>
              <th v-if="!isReadonly" style="width: 48px">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(row, i) in sampleRows" :key="row.__rid">
              <!-- 分组标题行 -->
              <tr v-if="row.__isGroup" class="c1-sample-group-row">
                <td :colspan="isReadonly ? 9 : 10" class="c1-sample-group-cell">
                  <el-input
                    v-if="!isReadonly"
                    :model-value="row.desc"
                    size="small"
                    placeholder="区域分组名称（如：境内 / 境外）"
                    style="max-width: 300px; font-weight: 600"
                    @input="(v: any) => onSampleCell(i, 'desc', v)"
                  />
                  <strong v-else>{{ row.desc || '区域分组' }}</strong>
                  <el-button v-if="!isReadonly" type="danger" size="small" text style="margin-left: 8px" @click="removeSampleRow(i)">删除</el-button>
                </td>
              </tr>
              <!-- 普通样本数据行 -->
              <tr v-else>
              <td class="c1-cell-idx">{{ i + 1 }}</td>
              <td>
                <el-input :model-value="row.date" :disabled="isReadonly" size="small" placeholder="日期" @input="(v: any) => onSampleCell(i, 'date', v)" />
              </td>
              <td>
                <el-input :model-value="row.account" :disabled="isReadonly" size="small" placeholder="账户编码" @input="(v: any) => onSampleCell(i, 'account', v)" />
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.ref" size="small" placeholder="引用底稿" @input="(v: any) => onSampleCell(i, 'ref', v)" />
                <div class="c1-ref-chips">
                  <GtIndexChip v-for="(r, ri) in splitRefs(row.ref)" :key="ri" :value="r" :context-project-id="props.projectId" />
                  <span v-if="isReadonly && splitRefs(row.ref).length === 0" class="c1-ref-empty">—</span>
                </div>
              </td>
              <td>
                <el-input :model-value="row.desc" :disabled="isReadonly" size="small" placeholder="交易描述" @input="(v: any) => onSampleCell(i, 'desc', v)" />
              </td>
              <td>
                <el-input :model-value="row.debit" :disabled="isReadonly" size="small" placeholder="借方" @input="(v: any) => onSampleCell(i, 'debit', v)" />
              </td>
              <td>
                <el-input :model-value="row.credit" :disabled="isReadonly" size="small" placeholder="贷方" @input="(v: any) => onSampleCell(i, 'credit', v)" />
              </td>
              <td class="c1-formula-cell">
                <span class="c1-formula-val">{{ fmtAmount(rowCumulativeDiff(i)) }}</span>
              </td>
              <td class="c1-attach-cell">
                <el-upload
                  v-if="!isReadonly"
                  :show-file-list="false"
                  :auto-upload="false"
                  accept="image/*,.pdf"
                  @change="(f: any) => onUploadSampleOcr(i, f.raw || f)"
                  style="display: inline-block"
                >
                  <el-button link size="small" title="上传附件并 OCR 识别">📎</el-button>
                </el-upload>
                <el-tooltip v-if="sampleAttachName(row.__rid)" :content="sampleAttachName(row.__rid)" placement="top">
                  <el-icon class="c1-attach-flag"><Paperclip /></el-icon>
                </el-tooltip>
                <span v-else-if="isReadonly" class="c1-ref-empty">—</span>
              </td>
              <td v-if="!isReadonly">
                <el-button type="danger" size="small" text @click="removeSampleRow(i)">删除</el-button>
              </td>
            </tr>
            </template>
            <tr v-if="sampleRows.length === 0">
              <td :colspan="isReadonly ? 9 : 10" class="c1-empty-row">
                暂无样本明细{{ isReadonly ? '' : '，点击「+ 新增样本行」开始录入' }}
              </td>
            </tr>
          </tbody>
          <tfoot v-if="sampleRows.length > 0">
            <tr class="c1-sample-foot">
              <td colspan="5" style="text-align: right">合计（元）</td>
              <td class="c1-formula-cell">
                <el-tooltip content="源模板 C1-4-4：Σ借方金额（只读派生）" placement="top">
                  <span class="c1-formula-val">{{ fmtAmount(sampleBalance.debitTotal) }}</span>
                </el-tooltip>
              </td>
              <td class="c1-formula-cell">
                <el-tooltip content="源模板 C1-4-4：Σ贷方金额（只读派生）" placement="top">
                  <span class="c1-formula-val">{{ fmtAmount(sampleBalance.creditTotal) }}</span>
                </el-tooltip>
              </td>
              <td class="c1-formula-cell">
                <el-tag :type="sampleBalance.balanced ? 'success' : 'danger'" size="small" effect="plain">
                  {{ sampleBalance.balanced ? '借贷平衡' : '借贷不平' }}
                </el-tag>
              </td>
              <td></td>
              <td v-if="!isReadonly"></td>
            </tr>
          </tfoot>
        </table>

        <template #footer>
          <el-button @click="sampleDialogVisible = false">关闭</el-button>
          <el-button type="primary" :disabled="isReadonly" @click="sampleDialogVisible = false">保存</el-button>
        </template>
      </el-dialog>

    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC1EntityControl.vue — C1 企业层面控制测试 向导式中控台
 *
 * 重构后架构：单页向导（L0 Main Console）+ 多级 Dialog/Drawer 交互层
 *   L0: 九段折叠进度 + 整体结论 + 缺陷登记（始终可见）
 *   L1: Step Detail Dialog (55%) + Example Drawer (45% right)
 *   L2: Process Record Dialog (fullscreen) — C1-4 财报内控汇总
 *   L3: Detail Record Dialog (70%) + Sample Table Dialog (85%)
 *
 * 保留所有 composable 调用、数据持久化逻辑、props 接口不变。
 * sheetName prop 仅控制初始焦点/滚动位置，不再切换渲染模式。
 */
import { ref, computed, onMounted, toRef, nextTick, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, InfoFilled, Paperclip, Select, CloseBold } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { fmtAmount } from '@/utils/formatters'
import { useC1ControlData, C1_ITEM_PREFIX } from './composables/useC1ControlData'
import {
  calcSampleBalance,
  mapOcrToSampleCells,
  mergeSampleRow,
  type JeSample,
  type SampleCellMap,
} from './composables/useC1SampleEngine'
import { C1_SECTION_DEFS, sectionProgressPercent } from './composables/useC1SectionEngine'
import { parseC1Programs, getC1ProgramsFallback, filterBySection, type C1ProgramStep, type C1RawItem } from './composables/useC1ProgramParser'
import {
  FREQ_OPTIONS as ENGINE_FREQ_OPTIONS,
  TEST_METHOD_OPTIONS as ENGINE_TEST_METHOD_OPTIONS,
  CONCLUSION_OPTIONS as ENGINE_CONCLUSION_OPTIONS,
  sanitizeEnumValue,
  sanitizeMultiEnum,
  suggestOverallConclusion,
  shouldPublishConclusion,
  normalizeConclusion,
} from './composables/useC1ConclusionEngine'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

// ─── Props / Emits ─────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  year?: number
  readonly?: boolean
  sheetName?: string
  htmlData?: any
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── 枚举点选选项（单一来源） ─────────────────────────────────────────────────

const FREQ_OPTIONS: string[] = [...ENGINE_FREQ_OPTIONS]
const TEST_METHOD_OPTIONS: string[] = [...ENGINE_TEST_METHOD_OPTIONS]
const CONCLUSION_OPTIONS: string[] = [...ENGINE_CONCLUSION_OPTIONS]

// ─── 顶部操作引导区（蓝色渐变 4 步骤） ──────────────────────────────────────

const GUIDE_STEPS = [
  { no: 1, title: '填写项目信息', desc: '确认被审计单位、会计期间与集团/关联方适用范围' },
  { no: 2, title: '逐段执行测试', desc: '按九段展开，点击步骤行打开详情填写测试方法与结论' },
  { no: 3, title: '过程记录', desc: '在财务报告段点击「过程记录」，填写 6 项关键控制详情' },
  { no: 4, title: '形成结论', desc: '汇总各段结论，形成企业层面控制整体结论' },
]

// ─── 方法论上下文 ──────────────────────────────────────────────────────────

const C1_METHODOLOGY: Record<string, string> = {
  ce: '控制环境（COSO 要素一）：内部控制的基础。评价管理层诚信与道德价值观、治理层独立性与监督、组织架构与权责分配、人力资源政策。',
  ra: '风险评估（COSO 要素二）：识别与分析实现财务报告目标相关的风险，关注舞弊风险与经营环境重大变化的识别与应对。',
  mo: '监督（COSO 要素五）：通过持续监督与专项评价，确认内部控制各要素是否持续有效运行、缺陷是否及时沟通整改。',
  bu: '仅集团审计适用：评价集团管理层对业务单元（组成部分）的监控，是否覆盖组成部分层面的重大错报风险。',
  ic: '信息与沟通（COSO 要素四）：确认相关、高质量的信息在组织内部与外部得到识别、获取、处理与传递，支持内部控制运行。',
  fr: '财务报告内部控制：与财务报告认定直接相关的关键控制，是整合审计的核心测试对象（详见 C1-4 过程记录子表）。',
  el: '对业务层面控制的影响：评价企业层面控制对业务流程层面控制的影响，据此确定控制测试的性质、时间与范围。',
  ye: '年终程序：关注期末财务报告编制与列报相关的企业层面控制，如合并、关账与重大会计估计复核。',
  rp: '仅有关联方交易时适用：测试与降低关联方关系及其交易导致重大错报风险相关的控制环境内容。',
}

function methodologyOf(slug: string): string {
  return C1_METHODOLOGY[slug] || ''
}

/** C1-4 财报内控 6 项关键控制 */
const FR_SUMMARY_CONTROLS = [
  'FINC-US-002 账户结构图变更',
  '会计准则符合性评估',
  '追溯原始分录',
  'FINC-US 会计分录人工授权',
  'FINC-US-008 分录分类',
  '会计准则遵循评价',
]

// ─── 过程记录字段配置 ────────────────────────────────────────────────────────

type ProcFieldType = 'text' | 'freq' | 'method'
interface ProcField { key: string; label: string; type: ProcFieldType }

const PROCESS_FIELDS_COMMON: ProcField[] = [
  { key: 'activity', label: '活动名', type: 'text' },
  { key: 'process', label: '流程名', type: 'text' },
  { key: 'control', label: '控制', type: 'text' },
  { key: 'custDesc', label: '客户控制描述', type: 'text' },
  { key: 'custCode', label: '客户控制编码', type: 'text' },
  { key: 'freq', label: '控制频率', type: 'freq' },
  { key: 'execDate', label: '执行日期', type: 'text' },
  { key: 'processOwner', label: '流程负责人', type: 'text' },
  { key: 'controlOwner', label: '控制负责人', type: 'text' },
  { key: 'interviewee', label: '访问的人员', type: 'text' },
  { key: 'interviewDate', label: '访问日期', type: 'text' },
  { key: 'testMethod', label: '测试方法', type: 'method' },
  { key: 'howTest', label: '如何测试', type: 'text' },
  { key: 'testResult', label: '测试结果', type: 'text' },
]

// ─── 九段分组配置 ────────────────────────────────────────────────────────────

interface C1SectionGroup {
  slug: string
  order: number
  title: string
  defaultApplicable: boolean
  note?: string
}

const C1_SECTIONS_FALLBACK: C1SectionGroup[] = C1_SECTION_DEFS.map((d) => ({
  slug: d.slug,
  order: d.order,
  title: d.title,
  defaultApplicable: d.defaultApplicable,
  note: d.note,
}))

// ─── State ───────────────────────────────────────────────────────────────

const isLoading = ref(false)
const isReadonly = computed(() => !!props.readonly)
const sectionGroups = ref<C1SectionGroup[]>([...C1_SECTIONS_FALLBACK])
const activeSections = ref<string[]>(C1_SECTIONS_FALLBACK.map((g) => g.slug))

/** 兼容旧测试的 mode 计算属性（向导模式已不按 mode 分发，仅供测试断言） */
const computedMode = computed<string>(() => {
  const n = props.sheetName || ''
  if (!n || n === 'C1 企业层面控制测试程序表' || n === '未知 sheet') return 'program'
  if (/C1-[123](?!\d)/.test(n) || /示例[123]/.test(n)) return 'example'
  if (/C1-4企业层面内控测试示例4-财务报告内部控制/.test(n)) return 'fr-summary'
  if (/C1-4-4/.test(n)) return 'process-record-sample'
  if (/C1-4-[1-6]/.test(n)) return 'process-record'
  if (/C1-4/.test(n)) return 'fr-summary'
  return 'program'
})

// ─── Dialog / Drawer visibility state ──────────────────────────────────────

const stepDialogVisible = ref(false)
const exampleDrawerVisible = ref(false)
const processDialogVisible = ref(false)
const detailDialogVisible = ref(false)
const sampleDialogVisible = ref(false)

// ─── Active context ────────────────────────────────────────────────────────

const activeStep = ref<{ section: string; stepIndex: number; step: any } | null>(null)
const activeProcessIndex = ref<number>(-1)
const activeExampleTab = ref('C1-1')

/** 已加载的程序步骤（结构化：含 section / stepIndex / name / subItems） */
const programs = ref<C1ProgramStep[]>([])

/** 当前步骤子项勾选状态 */
const checkedSubItems = ref<number[]>([])

// ─── 数据持久化（useC1ControlData） ─────────────────────────────────────────

const c1data = useC1ControlData(toRef(props, 'wpId'), {
  projectId: toRef(props, 'projectId') as any,
  readonly: isReadonly,
})

const getConclusion = (id: string) => c1data.getConclusion(id)
const getRemark = (id: string) => c1data.getRemark(id)
const setEnum = (id: string, v: string | null) => c1data.setConclusion(id, v ?? null)
const setTextDebounced = (id: string, v: string) => c1data.setText(id, v ?? '')

const getMultiEnum = (id: string): string[] => {
  const v = getConclusion(id)
  return v ? v.split(',').map((s) => s.trim()).filter(Boolean) : []
}
const setMultiEnum = (id: string, arr: string[] | null): void => {
  const clean = sanitizeMultiEnum(TEST_METHOD_OPTIONS, arr)
  setEnum(id, clean.length ? clean.join(',') : null)
}
const setPointSelect = (id: string, options: string[], v: unknown): void => {
  setEnum(id, sanitizeEnumValue(options, v))
}

// ─── 跨底稿引用解析 ────────────────────────────────────────────────────────

function splitRefs(text?: string | null): string[] {
  if (!text) return []
  return String(text)
    .split(/[,，;；、\s/]+/)
    .map((s) => s.replace(/[<>【】()（）\[\]]/g, '').trim())
    .filter(Boolean)
}

// ─── AI 辅助 ────────────────────────────────────────────────────────────────

const aiEnabled = ref(false)
const aiTip = computed(() => (aiEnabled.value ? 'AI 辅助生成' : 'AI 辅助生成（服务暂未开启）'))
async function checkAiHealth(): Promise<void> {
  try {
    const resp: any = await api.get('/api/feature-flags', { _silent: true } as any)
    const flags = resp?.flags || resp || {}
    aiEnabled.value = !!flags.WP_AI_SERVICE_ENABLED
  } catch {
    aiEnabled.value = false
  }
}

// ─── item_id 构造 ─────────────────────────────────────────────────────────

const summaryItemId = (n: number, field: string): string => `${C1_ITEM_PREFIX}4-summary-${n}-${field}`
const sampleCellItemId = (rid: number, col: string): string => `${C1_ITEM_PREFIX}4-4-sample-${rid}-${col}`
/** 过程记录详情 item_id（基于 activeProcessIndex，对应 C1-4-{k} sub-table） */
function activeDetailItemId(field: string): string {
  const k = activeProcessIndex.value + 1 // 1-based: C1-4-1 ~ C1-4-6
  return `${C1_ITEM_PREFIX}4-${k}-${field}`
}
/** C1-4-4 样本过程记录字段 item_id */
function sampleProcItemId(field: string): string {
  return `${C1_ITEM_PREFIX}4-4-${field}`
}

// ─── 步骤相关 item_id ─────────────────────────────────────────────────────

function stepItemId(section: string, stepIndex: number, field: string): string {
  return `${C1_ITEM_PREFIX}${section}-${stepIndex}-${field}`
}

// ─── 九段分组渲染辅助 ─────────────────────────────────────────────────────

function groupedPrograms(slug: string): C1ProgramStep[] {
  return filterBySection(programs.value, slug)
}

const sectionApplicableId = (slug: string): string => `${C1_ITEM_PREFIX}${slug}-section-applicable`

function isSectionApplicable(slug: string): boolean {
  return c1data.isApplicable(sectionApplicableId(slug))
}

function sectionReason(slug: string): string {
  return c1data.getRemark(sectionApplicableId(slug)) || ''
}

async function onToggleSectionApplicable(slug: string, applicable: boolean): Promise<void> {
  if (isReadonly.value) return
  if (applicable) {
    c1data.setApplicable(sectionApplicableId(slug), true)
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('请填写该段「不适用」的理由（必填）', '标记不适用', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：本项目非集团审计 / 无关联方交易',
      inputValidator: (v: string) => (v && v.trim() ? true : '不适用理由不能为空'),
    })
    const ok = c1data.setApplicable(sectionApplicableId(slug), false, value)
    if (!ok) c1data.setApplicable(sectionApplicableId(slug), true)
  } catch { /* 用户取消 */ }
}

function sectionProgress(slug: string): number {
  return sectionProgressPercent(
    [...c1data.responses.value.values()],
    slug,
    isSectionApplicable(slug),
  )
}

// ─── Step table row helpers ──────────────────────────────────────────────

function isStepApplicable(section: string, stepIndex: number): boolean | null {
  const v = getConclusion(stepItemId(section, stepIndex, 'applicable'))
  if (v === 'Y') return true
  if (v === 'N') return false
  return null
}

function isStepDone(section: string, stepIndex: number): boolean {
  return !!(getRemark(stepItemId(section, stepIndex, 'result')) || '').trim()
}

/** 步骤三态：done(有结论) / wip(有部分数据但没结论) / todo(无数据) */
function stepStatus(section: string, stepIndex: number): 'done' | 'wip' | 'todo' {
  const conclusion = getConclusion(stepItemId(section, stepIndex, 'conclusion'))
  if (conclusion) return 'done'
  const hasResult = !!(getRemark(stepItemId(section, stepIndex, 'result')) || '').trim()
  const hasMethod = !!(getConclusion(stepItemId(section, stepIndex, 'method')) || '').trim()
  const hasApplicable = !!(getConclusion(stepItemId(section, stepIndex, 'applicable')) || '').trim()
  if (hasResult || hasMethod || hasApplicable) return 'wip'
  return 'todo'
}

/** 步骤行 CSS class（三态视觉） */
function stepRowClass(section: string, stepIndex: number): Record<string, boolean> {
  const s = stepStatus(section, stepIndex)
  return {
    'c1-step-done': s === 'done',
    'c1-step-wip': s === 'wip',
    'c1-step-todo': s === 'todo',
  }
}

/** 快速标记：一键设置适用 + 结论有效 + 当前用户（优化4） */
function quickMarkStep(section: string, stepIndex: number): void {
  if (isReadonly.value) return
  const idApplicable = stepItemId(section, stepIndex, 'applicable')
  const idConclusion = stepItemId(section, stepIndex, 'conclusion')
  const idResult = stepItemId(section, stepIndex, 'result')
  c1data.setFieldImmediate(idApplicable, { conclusion: 'Y', remark: null })
  setPointSelect(idConclusion, CONCLUSION_OPTIONS, '有效')
  // 如果没有已填结果说明，自动填入默认文字
  if (!(getRemark(idResult) || '').trim()) {
    setTextDebounced(idResult, '经执行相关测试程序，未发现异常，控制运行有效。')
  }
  ElMessage.success(`步骤 ${stepIndex + 1} 已快速标记为「有效」`)
}

// ─── 总体完成度（优化6）────────────────────────────────────────────────────

/** 所有适用段的适用步骤总数 */
const totalApplicableStepCount = computed<number>(() => {
  let total = 0
  for (const g of sectionGroups.value) {
    if (!isSectionApplicable(g.slug)) continue
    const steps = groupedPrograms(g.slug)
    for (let i = 0; i < steps.length; i++) {
      if (isStepApplicable(g.slug, i) !== false) total++
    }
  }
  return total
})

/** 已完成步骤数（有结论） */
const completedStepCount = computed<number>(() => {
  let count = 0
  for (const g of sectionGroups.value) {
    if (!isSectionApplicable(g.slug)) continue
    const steps = groupedPrograms(g.slug)
    for (let i = 0; i < steps.length; i++) {
      if (isStepApplicable(g.slug, i) === false) continue
      if (stepStatus(g.slug, i) === 'done') count++
    }
  }
  return count
})

/** 总体完成百分比 */
const overallProgressPercent = computed<number>(() => {
  if (totalApplicableStepCount.value === 0) return 0
  return Math.round((completedStepCount.value / totalApplicableStepCount.value) * 100)
})

// ─── 段结论自动推导（优化2）──────────────────────────────────────────────────

/** 根据段内步骤结论推导段结论建议 */
function suggestedSectionConclusion(slug: string): string | null {
  if (!isSectionApplicable(slug)) return null
  const steps = groupedPrograms(slug)
  if (steps.length === 0) return null
  const conclusions: string[] = []
  for (let i = 0; i < steps.length; i++) {
    if (isStepApplicable(slug, i) === false) continue
    const c = getConclusion(stepItemId(slug, i, 'conclusion'))
    if (c) conclusions.push(c)
  }
  if (conclusions.length === 0) return null // 没有任何步骤有结论
  // 全部有效 → 建议有效
  if (conclusions.every((c) => c === '有效')) return '有效'
  // 有任一无效 → 建议无效
  if (conclusions.some((c) => c === '无效')) return '无效'
  // 有部分有效 → 建议部分有效
  return '部分有效'
}

function getStepField(section: string, stepIndex: number, field: string): string {
  return getRemark(stepItemId(section, stepIndex, field)) || ''
}

function getStepConclusion(section: string, stepIndex: number): string | null {
  return getConclusion(stepItemId(section, stepIndex, 'conclusion'))
}

function conclusionTagType(conclusion: string | null): string {
  if (conclusion === '有效') return 'success'
  if (conclusion === '无效') return 'danger'
  if (conclusion === '部分有效') return 'warning'
  return 'info'
}

// ─── L1 Step Dialog logic ────────────────────────────────────────────────

const stepDialogTitle = computed(() => {
  if (!activeStep.value) return '步骤详情'
  const g = sectionGroups.value.find((s) => s.slug === activeStep.value!.section)
  const stepName = activeStep.value.step?.name || activeStep.value.step?.title || `步骤 ${activeStep.value.stepIndex + 1}`
  return `${g?.order || ''}. ${g?.title || ''} > ${stepName}`
})

// ─── 步骤内嵌编制参考（示例数据来自 C1-1~C1-3 源模板） ──────────────────────

interface StepExampleRefData {
  id: string
  source: string
  controlPoint: string
  methods: string[]
  sampleInfo: string
  procedure: string
  rollforward?: string
  conclusion: string
}

/**
 * 示例映射表：step.name 中的关键词 → 对应示例。
 * 逻辑：用户打开某个步骤时，如果该步骤的程序名与某个示例对应，直接显示编制参考。
 * C1-1 → 程序 4（人力资源/背景调查）
 * C1-2 → 程序 7（审计委员会会议记录）
 * C1-3 → 程序 8（审计委员会成员）
 */
const STEP_EXAMPLE_MAP: { match: (section: string, stepIndex: number, name: string) => boolean; data: StepExampleRefData }[] = [
  {
    match: (sec, idx, name) => sec === 'ce' && (/人力资源/.test(name) || /调查/.test(name) || idx === 3),
    data: {
      id: 'C1-1', source: 'C1-1 招聘背景调查',
      controlPoint: '对候选员工的背景调查和聘用审批',
      methods: ['抽样'],
      sampleInfo: '25 人（约 300 名新聘员工，每天多次人工控制）',
      procedure: '查阅新入职员工档案：招聘计划审批→背景调查→聘用批准→签劳动合同。检查 10 个维度。',
      rollforward: '询问人力资源部负责人确定流程在剩余期间是否变化 → 未发生变化',
      conclusion: '控制运行有效',
    },
  },
  {
    match: (sec, idx, name) => sec === 'ce' && (/审计委员会.*会议/.test(name) || /会议记录/.test(name) || idx === 6),
    data: {
      id: 'C1-2', source: 'C1-2 审计委员会会议记录',
      controlPoint: '获取并阅读审计委员会全部会议记录',
      methods: ['询问', '观察', '检查'],
      sampleInfo: '全年全部会议（100%）',
      procedure: '评价会议频率适当性、报告事项性质、后续跟踪措施、出席率、财务报表批准、非审计服务审批等。',
      conclusion: '控制运行有效',
    },
  },
  {
    match: (sec, idx, name) => sec === 'ce' && (/审计委员会主席/.test(name) || /成员.*组成/.test(name) || idx === 7),
    data: {
      id: 'C1-3', source: 'C1-3 审计委员会成员评价',
      controlPoint: '询问审计委员会主席关于成员情况',
      methods: ['询问'],
      sampleInfo: '不适用（全量询问）',
      procedure: '了解成员组成/经验/职责/专长→评价周期→评价结果与措施→防舞弊控制→主席观点。',
      conclusion: '控制运行有效',
    },
  },
]

/** 当前步骤对应的示例参考（如果有） */
const stepExampleRef = computed<StepExampleRefData | null>(() => {
  if (!activeStep.value) return null
  const { section, stepIndex, step } = activeStep.value
  const name = step?.name || ''
  const found = STEP_EXAMPLE_MAP.find((e) => e.match(section, stepIndex, name))
  return found?.data ?? null
})

/**
 * 前推测试智能折叠（优化7）：
 * 只有当步骤已填了前推相关数据，或者有对应示例含前推时才默认展开。
 * 否则折叠，减少视觉噪音。
 */
const shouldShowRollforward = computed<boolean>(() => {
  if (!activeStep.value) return false
  const hasRollforwardData = !!(getActiveStepField('rollforward') || '').trim()
  const exHasRollforward = !!(stepExampleRef.value?.rollforward)
  return hasRollforwardData || exHasRollforward
})

/**
 * 测试方法建议（优化5）：根据步骤程序名的动词推导建议的测试方法。
 * 当步骤没有对应完整示例时，给出轻量提示。
 */
const stepMethodSuggestion = computed<string | null>(() => {
  if (!activeStep.value) return null
  // 如果有完整示例，不需要额外建议（编制参考区已展示）
  if (stepExampleRef.value) return null
  const name = (activeStep.value.step?.name || '').trim()
  if (/询问/.test(name)) return '建议：询问（该步骤程序涉及"询问"）'
  if (/观察/.test(name)) return '建议：观察（该步骤程序涉及"观察"）'
  if (/检查|获取|阅读|复核/.test(name)) return '建议：检查（该步骤程序涉及文件检查/获取/复核）'
  if (/调查|了解/.test(name)) return '建议：询问 + 观察（该步骤涉及调查了解）'
  return null
})

function openStepDialog(section: string, stepIndex: number, step: any): void {
  activeStep.value = { section, stepIndex, step }
  // 加载子项勾选状态
  loadCheckedSubItems(section, stepIndex)
  stepDialogVisible.value = true
}

/** 子项勾选 item_id: C1-{section}-{stepIndex}-checked */
function checkedSubItemsId(section: string, stepIndex: number): string {
  return `${C1_ITEM_PREFIX}${section}-${stepIndex}-checked`
}

/** 从持久化加载子项勾选 */
function loadCheckedSubItems(section: string, stepIndex: number): void {
  const stored = getRemark(checkedSubItemsId(section, stepIndex))
  if (stored) {
    checkedSubItems.value = stored.split(',').map(Number).filter((n) => !isNaN(n))
  } else {
    checkedSubItems.value = []
  }
}

/** 保存子项勾选到持久化 */
function saveCheckedSubItems(): void {
  if (!activeStep.value || isReadonly.value) return
  const id = checkedSubItemsId(activeStep.value.section, activeStep.value.stepIndex)
  const val = checkedSubItems.value.length ? checkedSubItems.value.sort((a, b) => a - b).join(',') : ''
  c1data.setFieldDebounced(id, { remark: val })
}

// Step dialog field accessors (bound to activeStep)
const stepApplicableVal = computed(() => {
  if (!activeStep.value) return null
  return getConclusion(stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'applicable'))
})

const stepInapplicableReason = computed(() => {
  if (!activeStep.value) return ''
  return getRemark(stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'applicable')) || ''
})

const stepMethodVal = computed(() => {
  if (!activeStep.value) return [] as string[]
  return getMultiEnum(stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'method'))
})

function onStepApplicableChange(v: string): void {
  if (!activeStep.value || isReadonly.value) return
  const id = stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'applicable')
  c1data.setFieldImmediate(id, { conclusion: v, remark: v === 'N' ? stepInapplicableReason.value : null })
}

function onStepReasonInput(v: string): void {
  if (!activeStep.value || isReadonly.value) return
  const id = stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'applicable')
  c1data.setFieldDebounced(id, { remark: v })
}

function onStepMethodChange(v: string[]): void {
  if (!activeStep.value || isReadonly.value) return
  const id = stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'method')
  const clean = sanitizeMultiEnum(TEST_METHOD_OPTIONS, v)
  setEnum(id, clean.length ? clean.join(',') : null)
}

function getActiveStepField(field: string): string {
  if (!activeStep.value) return ''
  return getRemark(stepItemId(activeStep.value.section, activeStep.value.stepIndex, field)) || ''
}

function setActiveStepText(field: string, v: string): void {
  if (!activeStep.value || isReadonly.value) return
  setTextDebounced(stepItemId(activeStep.value.section, activeStep.value.stepIndex, field), v)
}

function getActiveStepConclusion(): string | null {
  if (!activeStep.value) return null
  return getConclusion(stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'conclusion'))
}

function setActiveStepConclusion(v: unknown): void {
  if (!activeStep.value || isReadonly.value) return
  setPointSelect(
    stepItemId(activeStep.value.section, activeStep.value.stepIndex, 'conclusion'),
    CONCLUSION_OPTIONS,
    v,
  )
}

/** 全选子项 */
function checkAllSubItems(): void {
  if (!activeStep.value || isReadonly.value) return
  const subs = activeStep.value.step?.subItems
  if (!subs?.length) return
  checkedSubItems.value = subs.map((_: unknown, i: number) => i)
}

/** 全不选子项 */
function uncheckAllSubItems(): void {
  if (isReadonly.value) return
  checkedSubItems.value = []
}

/** 根据已勾选子项自动生成测试结果描述 */
function generateResultFromSubItems(): void {
  if (!activeStep.value || isReadonly.value) return
  const subs = activeStep.value.step?.subItems
  if (!subs?.length || !checkedSubItems.value.length) return
  const checked = checkedSubItems.value
    .sort((a, b) => a - b)
    .map((i) => subs[i])
    .filter(Boolean)
  const prefix = `经执行以下检查程序（共${checked.length}项），已确认：\n`
  const items = checked.map((s: string, i: number) => `${i + 1}. ${s.replace(/^（\d+）\s*/, '')}`).join('\n')
  const suffix = '\n\n结论：上述各项控制均按设计运行有效。'
  const result = prefix + items + suffix
  setActiveStepText('result', result)
  ElMessage.success(`已根据 ${checked.length} 项勾选内容生成测试结果描述`)
}

/** 示例 Drawer 一键参照：将示例模板文字预填到当前步骤 */
function applyExampleToStep(exampleId: string): void {
  if (isReadonly.value || !activeStep.value) {
    ElMessage.info(activeStep.value ? '只读模式不可操作' : '请先在左侧点击某个步骤行打开详情后再参照')
    return
  }
  const templates: Record<string, { method: string[]; result: string; rollforward?: string; rollforwardProc?: string; rollforwardResult?: string }> = {
    'C1-1': {
      method: ['抽样'],
      result: '查阅当年度新入职员工档案资料，确定其招聘计划是否经部门负责人、人力资源部负责人和总经理审批；是否已进行背景调查；聘用是否经适当批准；是否已签订标准劳动合同。',
      rollforward: '是',
      rollforwardProc: '询问人力资源部负责人，确定员工的聘用流程在剩余期间是否发生变化。',
      rollforwardResult: '期中测试后未发生变化。',
    },
    'C1-2': {
      method: ['询问', '观察', '检查'],
      result: '获取并阅读本年度全部审计委员会会议记录，确认会议频率适当，报告事项覆盖了管理层、内审和外审的关键信息，均有后续跟踪且满足职责要求。',
    },
    'C1-3': {
      method: ['询问'],
      result: '询问审计委员会主席关于：成员组成和经验适当性、成员职责了解程度、讨论参与情况、财务专长成员、向管理层/内外审提出的问题实例、定期评价及措施、防舞弊控制措施、主席对有效性的观点。',
    },
  }
  const tpl = templates[exampleId]
  if (!tpl) return
  // 预填测试方法
  if (tpl.method?.length) {
    onStepMethodChange(tpl.method)
  }
  // 预填测试结果
  if (tpl.result) {
    setActiveStepText('result', tpl.result)
  }
  // 预填前推测试
  if (tpl.rollforward) {
    setActiveStepText('rollforward', tpl.rollforward)
  }
  if (tpl.rollforwardProc) {
    setActiveStepText('rollforwardProc', tpl.rollforwardProc)
  }
  if (tpl.rollforwardResult) {
    setActiveStepText('rollforwardResult', tpl.rollforwardResult)
  }
  ElMessage.success(`已参照 ${exampleId} 示例预填步骤内容，请按实际情况修改`)
}

function saveAndCloseStep(): void {
  saveCheckedSubItems()
  c1data.flushPendingSave()
  stepDialogVisible.value = false
}

/** 保存并下一步：自动前进到同段下一个适用步骤 */
function saveAndNextStep(): void {
  saveCheckedSubItems()
  c1data.flushPendingSave()
  if (!activeStep.value) return
  const steps = groupedPrograms(activeStep.value.section)
  let nextIdx = activeStep.value.stepIndex + 1
  // 跳过不适用的步骤
  while (nextIdx < steps.length && isStepApplicable(activeStep.value.section, nextIdx) === false) {
    nextIdx++
  }
  if (nextIdx < steps.length) {
    activeStep.value = { section: activeStep.value.section, stepIndex: nextIdx, step: steps[nextIdx] }
    loadCheckedSubItems(activeStep.value.section, nextIdx)
  } else {
    // 当前段已结束，尝试跳到下一个适用段
    const currentSectionIdx = sectionGroups.value.findIndex((g) => g.slug === activeStep.value!.section)
    for (let si = currentSectionIdx + 1; si < sectionGroups.value.length; si++) {
      const nextSlug = sectionGroups.value[si].slug
      if (!isSectionApplicable(nextSlug)) continue
      const nextSteps = groupedPrograms(nextSlug)
      if (nextSteps.length > 0) {
        activeStep.value = { section: nextSlug, stepIndex: 0, step: nextSteps[0] }
        loadCheckedSubItems(nextSlug, 0)
        return
      }
    }
    // 全部完成
    stepDialogVisible.value = false
    ElMessage.success('所有步骤已完成')
  }
}

// ─── L2 Process Record Dialog ─────────────────────────────────────────────

function openProcessDialog(): void {
  processDialogVisible.value = true
}

// ─── L3 Detail Record Dialog ──────────────────────────────────────────────

const detailDialogTitle = computed(() => {
  if (activeProcessIndex.value < 0) return '过程记录详情'
  const name = FR_SUMMARY_CONTROLS[activeProcessIndex.value] || ''
  return `C1-4-${activeProcessIndex.value + 1} ${name}`
})

/** 当前过程记录详情字段集（C1-4-2 额外含「重要性」） */
const processFieldsForActive = computed<ProcField[]>(() => {
  const k = activeProcessIndex.value + 1
  if (k === 2) {
    const fields = [...PROCESS_FIELDS_COMMON]
    const idx = fields.findIndex((f) => f.key === 'process')
    fields.splice(idx + 1, 0, { key: 'materiality', label: '重要性', type: 'text' })
    return fields
  }
  return PROCESS_FIELDS_COMMON
})

/** C1-4-4 样本过程记录字段 */
const processFieldsForSample = computed<ProcField[]>(() => PROCESS_FIELDS_COMMON)

function openDetailDialog(summaryIdx: number): void {
  if (summaryIdx === 3) {
    // C1-4-4 会计分录人工授权 → 打开 L3 样本表 dialog
    activeProcessIndex.value = 3
    sampleDialogVisible.value = true
  } else {
    activeProcessIndex.value = summaryIdx
    detailDialogVisible.value = true
  }
}

/** 过程记录结论变更（优化3：联动回写汇总表） */
function onDetailConclusionChange(v: unknown): void {
  if (isReadonly.value || activeProcessIndex.value < 0) return
  const cleaned = sanitizeEnumValue(CONCLUSION_OPTIONS, v)
  setEnum(activeDetailItemId('conclusion'), cleaned)
}

/** 保存过程记录详情并回写汇总表结论（优化3） */
function saveAndCloseDetail(): void {
  if (!isReadonly.value && activeProcessIndex.value >= 0) {
    // 将过程记录的结论同步到汇总表对应行
    const detailConclusion = getConclusion(activeDetailItemId('conclusion'))
    if (detailConclusion) {
      const summaryId = summaryItemId(activeProcessIndex.value + 1, 'conclusion')
      setEnum(summaryId, detailConclusion)
    }
    c1data.flushPendingSave()
  }
  detailDialogVisible.value = false
}

// ─── C1-4-4 样本明细 ─────────────────────────────────────────────────────

interface SampleRow {
  __rid: number
  __isGroup?: boolean
  date: string
  account: string
  ref: string
  desc: string
  debit: string
  credit: string
}

const SAMPLE_COLS = ['date', 'account', 'ref', 'desc', 'debit', 'credit'] as const
const sampleRows = ref<SampleRow[]>([])
let sampleRidSeq = 0

function buildSampleRows(): void {
  const byRid = new Map<number, Partial<SampleRow>>()
  const re = /^C1-4-4-sample-(\d+)-(date|account|ref|desc|debit|credit|isGroup)$/
  for (const [itemId, r] of c1data.responses.value.entries()) {
    const m = itemId.match(re)
    if (!m) continue
    const rid = Number(m[1])
    const col = m[2]
    const cur = byRid.get(rid) ?? { __rid: rid }
    if (col === 'isGroup') {
      ;(cur as any).__isGroup = r.remark === 'true'
    } else {
      ;(cur as any)[col] = r.remark ?? ''
    }
    byRid.set(rid, cur)
  }
  const rows = [...byRid.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([rid, v]) => ({
      __rid: rid,
      __isGroup: !!(v as any).__isGroup,
      date: v.date ?? '',
      account: v.account ?? '',
      ref: v.ref ?? '',
      desc: v.desc ?? '',
      debit: v.debit ?? '',
      credit: v.credit ?? '',
    }))
  sampleRows.value = rows
  sampleRidSeq = rows.reduce((mx, r) => Math.max(mx, r.__rid), -1) + 1
}

const sampleBalance = computed(() => calcSampleBalance(toJeSamples(sampleRows.value)))

function toJeSamples(rows: SampleRow[]): JeSample[] {
  return rows.filter((r) => !r.__isGroup).map((r) => ({
    date: r.date, account: r.account, ref: r.ref, desc: r.desc,
    debit: Number(r.debit) || 0, credit: Number(r.credit) || 0,
  }))
}

function rowCumulativeDiff(i: number): number {
  const slice = toJeSamples(sampleRows.value.slice(0, i + 1))
  if (slice.length === 0) return 0
  const b = calcSampleBalance(slice)
  return b.debitTotal - b.creditTotal
}

function addSampleRow(): void {
  if (isReadonly.value) return
  sampleRows.value.push({
    __rid: sampleRidSeq++, __isGroup: false, date: '', account: '', ref: '', desc: '', debit: '', credit: '',
  })
}

function addSampleGroupRow(): void {
  if (isReadonly.value) return
  const rid = sampleRidSeq++
  sampleRows.value.push({
    __rid: rid, __isGroup: true, date: '', account: '', ref: '', desc: '', debit: '', credit: '',
  })
  // 持久化 isGroup 标记
  c1data.setFieldDebounced(sampleCellItemId(rid, 'isGroup'), { remark: 'true' })
}

function removeSampleRow(i: number): void {
  if (isReadonly.value) return
  const row = sampleRows.value[i]
  if (!row) return
  for (const col of SAMPLE_COLS) {
    if (c1data.responses.value.has(sampleCellItemId(row.__rid, col))) {
      c1data.setFieldDebounced(sampleCellItemId(row.__rid, col), { remark: '' })
    }
  }
  sampleRows.value.splice(i, 1)
}

function onSampleCell(i: number, col: (typeof SAMPLE_COLS)[number], val: string): void {
  if (isReadonly.value) return
  const row = sampleRows.value[i]
  if (!row) return
  ;(row as any)[col] = val
  c1data.setFieldDebounced(sampleCellItemId(row.__rid, col), { remark: val })
}

// ─── 附件上传 + OCR ──────────────────────────────────────────────────────

const sampleAttachItemId = (rid: number): string => `${C1_ITEM_PREFIX}4-4-sample-${rid}-attach`
const procAttachItemId = (): string => {
  const k = activeProcessIndex.value + 1
  return `${C1_ITEM_PREFIX}4-${k}-attach`
}

function sampleAttachName(rid: number): string {
  return c1data.getRemark(sampleAttachItemId(rid)) || ''
}

const SAMPLE_COL_LABELS: Record<string, string> = {
  date: '日期', account: '账户编码', ref: '引用', desc: '交易描述', debit: '借方金额', credit: '贷方金额',
}

function unwrapOcrFields(res: any): Record<string, any> {
  const data = res?.data?.data ?? res?.data ?? {}
  return data.extracted_fields || {}
}

async function onUploadSampleOcr(i: number, rawFile: File): Promise<void> {
  if (isReadonly.value) return
  const row = sampleRows.value[i]
  if (!row || !rawFile) return
  c1data.setFieldDebounced(sampleAttachItemId(row.__rid), { remark: rawFile.name })
  const formData = new FormData()
  formData.append('file', rawFile)
  let ocrFields: Record<string, any>
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = unwrapOcrFields(res)
  } catch {
    ElMessage.warning('识别失败，请手动填写')
    return
  }
  const mapped = mapOcrToSampleCells(ocrFields)
  const existing: SampleCellMap = {
    date: row.date, account: row.account, ref: row.ref,
    desc: row.desc, debit: row.debit, credit: row.credit,
  }
  const preview = mergeSampleRow(existing, mapped)
  if (preview.filledCols.length === 0) {
    ElMessage.info(mapped && Object.keys(mapped).length
      ? 'OCR 识别字段均已有值，未覆盖既有内容' : '识别失败，请手动填写')
    return
  }
  const previewMsg = preview.filledCols.map((c) => `${SAMPLE_COL_LABELS[c] || c}：${mapped[c]}`).join('\n')
  const skippedMsg = preview.skippedCols.length
    ? `\n\n以下字段已有值，将保留不覆盖：${preview.skippedCols.map((c) => SAMPLE_COL_LABELS[c] || c).join('、')}` : ''
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下字段，确认填入？\n\n${previewMsg}${skippedMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
    )
  } catch { return }
  for (const col of preview.filledCols) {
    onSampleCell(i, col as (typeof SAMPLE_COLS)[number], preview.merged[col])
  }
  ElMessage.success(`已填入 ${preview.filledCols.length} 个字段`)
}

async function onUploadProcOcr(rawFile: File): Promise<void> {
  if (isReadonly.value) return
  if (!rawFile) return
  c1data.setFieldDebounced(procAttachItemId(), { remark: rawFile.name })
  const formData = new FormData()
  formData.append('file', rawFile)
  let ocrFields: Record<string, any>
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = unwrapOcrFields(res)
  } catch {
    ElMessage.warning('识别失败，请手动填写')
    return
  }
  const mapped = mapOcrToSampleCells(ocrFields)
  const targets = [
    { col: 'date', field: 'execDate', label: '执行日期' },
    { col: 'desc', field: 'testResult', label: '测试结果' },
  ]
  const fillable = targets.filter(
    (t) => mapped[t.col] && !((c1data.getRemark(activeDetailItemId(t.field)) || '').trim()),
  )
  if (fillable.length === 0) {
    ElMessage.info(Object.keys(mapped).length
      ? 'OCR 识别字段均已有值，未覆盖既有内容' : '识别失败，请手动填写')
    return
  }
  const previewMsg = fillable.map((t) => `${t.label}：${mapped[t.col]}`).join('\n')
  try {
    await ElMessageBox.confirm(`OCR 识别到以下字段，确认填入？\n\n${previewMsg}`, 'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' })
  } catch { return }
  for (const t of fillable) setTextDebounced(activeDetailItemId(t.field), mapped[t.col])
  ElMessage.success(`已填入 ${fillable.length} 个字段`)
}

function procAttachName(): string {
  return c1data.getRemark(procAttachItemId()) || ''
}

// ─── 整体结论 + EventBus 回写 B50 ─────────────────────────────────────────

const OVERALL_ITEM_ID = `${C1_ITEM_PREFIX}overall-conclusion`
const sectionConclusionId = (slug: string): string => `${C1_ITEM_PREFIX}${slug}-conclusion`

const sectionConclusions = computed<(string | null)[]>(() =>
  sectionGroups.value
    .filter((g) => isSectionApplicable(g.slug))
    .map((g) => getConclusion(sectionConclusionId(g.slug))),
)

const suggestedOverall = computed<string | null>(() => suggestOverallConclusion(sectionConclusions.value))
const overallConclusion = computed<string | null>(() => getConclusion(OVERALL_ITEM_ID))

function setSectionConclusion(slug: string, v: unknown): void {
  setPointSelect(sectionConclusionId(slug), CONCLUSION_OPTIONS, v)
}

function setOverallConclusion(v: unknown): void {
  if (isReadonly.value) return
  const oldVal = normalizeConclusion(getConclusion(OVERALL_ITEM_ID))
  const cleaned = sanitizeEnumValue(CONCLUSION_OPTIONS, v)
  setEnum(OVERALL_ITEM_ID, cleaned)
  publishConclusionIfChanged(oldVal, cleaned)
}

function applySuggestedOverall(): void {
  if (isReadonly.value) return
  const s = suggestedOverall.value
  if (!s) { ElMessage.info('各段结论尚未填写，暂无可建议的整体结论'); return }
  setOverallConclusion(s)
  ElMessage.success(`已应用建议结论：${s}`)
}

function publishConclusionIfChanged(oldVal: string | null | undefined, newVal: string | null | undefined): void {
  if (!shouldPublishConclusion(oldVal, newVal)) return
  eventBus.emit('c1:entity-control-conclusion', {
    projectId: props.projectId,
    wpId: props.wpId,
    wpCode: props.wpCode,
    conclusion: normalizeConclusion(newVal),
    previousConclusion: normalizeConclusion(oldVal),
  })
}

// ─── 识别缺陷 → A14 ──────────────────────────────────────────────────────

const A14_WP_CODE = 'A14'

interface DefectRow { __did: number; summary: string }
const defectRows = ref<DefectRow[]>([])
let defectDidSeq = 0

const defectItemId = (did: number): string => `${C1_ITEM_PREFIX}defect-${did}-summary`

function buildDefectRows(): void {
  const re = /^C1-defect-(\d+)-summary$/
  const rows: DefectRow[] = []
  for (const [itemId, r] of c1data.responses.value.entries()) {
    const m = itemId.match(re)
    if (!m) continue
    rows.push({ __did: Number(m[1]), summary: r.remark ?? '' })
  }
  rows.sort((a, b) => a.__did - b.__did)
  defectRows.value = rows
  defectDidSeq = rows.reduce((mx, r) => Math.max(mx, r.__did), -1) + 1
}

function addDefectRow(): void {
  if (isReadonly.value) return
  defectRows.value.push({ __did: defectDidSeq++, summary: '' })
}

function removeDefectRow(i: number): void {
  if (isReadonly.value) return
  const row = defectRows.value[i]
  if (!row) return
  if (c1data.responses.value.has(defectItemId(row.__did))) {
    c1data.setFieldDebounced(defectItemId(row.__did), { remark: '' })
  }
  defectRows.value.splice(i, 1)
}

function onDefectSummary(i: number, val: string): void {
  if (isReadonly.value) return
  const row = defectRows.value[i]
  if (!row) return
  row.summary = val
  c1data.setFieldDebounced(defectItemId(row.__did), { remark: val })
}

function onDefectJumpToA14(i: number): void {
  const row = defectRows.value[i]
  if (!row) return
  eventBus.emit('c1:defect-identified', {
    projectId: props.projectId,
    wpId: props.wpId,
    wpCode: props.wpCode,
    defectSummary: (row.summary || '').trim(),
    itemId: defectItemId(row.__did),
  })
}

// ─── selfLoad ────────────────────────────────────────────────────────────

async function selfLoad(): Promise<void> {
  const applyGroups = (data: any) => {
    const groups = data?.section_groups
    if (Array.isArray(groups) && groups.length) {
      sectionGroups.value = groups.map((g: any, i: number) => ({
        slug: String(g.slug ?? ''),
        order: Number(g.order ?? i + 1),
        title: String(g.title ?? ''),
        defaultApplicable: g.defaultApplicable ?? g.default_applicable ?? true,
        note: g.note,
      }))
      activeSections.value = sectionGroups.value.map((g) => g.slug)
    }
  }
  if (props.htmlData) {
    applyGroups(props.htmlData)
  } else if (props.wpId) {
    try {
      const res = await api.get<any>(
        `/api/workpapers/${props.wpId}/render-config?force_component_type=c1-entity-level-control`,
        { _silent: true } as any,
      )
      const data = res?.sheets?.[0]?.html_data ?? res?.htmlData ?? res
      applyGroups(data)
    } catch (e) {
      console.warn('[GtC1EntityControl] selfLoad render-config 失败，使用九段常量兜底:', e)
    }
  }
}

async function loadPrograms(): Promise<void> {
  // 直接使用内置的 131 条 C1 程序步骤（hardcoded from procedure_table_templates.json）
  // 无需网络请求，数据是静态的源模板内容
  programs.value = getC1ProgramsFallback()
}

/** sheetName → 初始焦点（滚动到对应段或自动打开对应 dialog） */
function applyInitialFocus(): void {
  const n = props.sheetName || ''
  if (!n) return
  if (/C1-4-4/.test(n)) {
    activeProcessIndex.value = 3
    nextTick(() => { processDialogVisible.value = true; sampleDialogVisible.value = true })
  } else if (/C1-4-[1-6]/.test(n)) {
    const m = n.match(/C1-4-([1-6])/)
    if (m) {
      activeProcessIndex.value = Number(m[1]) - 1
      nextTick(() => { processDialogVisible.value = true; detailDialogVisible.value = true })
    }
  } else if (/C1-4/.test(n) || /财务报告内部控制/.test(n)) {
    nextTick(() => { processDialogVisible.value = true })
  } else if (/C1-[123](?!\d)/.test(n) || /示例/.test(n)) {
    nextTick(() => { exampleDrawerVisible.value = true })
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────

onMounted(async () => {
  isLoading.value = true
  try {
    await Promise.all([selfLoad(), c1data.loadAll(), loadPrograms(), checkAiHealth()])
    buildSampleRows()
    buildDefectRows()
    applyInitialFocus()
  } finally {
    isLoading.value = false
  }
})

// ─── Expose ──────────────────────────────────────────────────────────────

defineExpose({
  activeStep,
  splitRefs,
  aiEnabled,
  GUIDE_STEPS,
  methodologyOf,
  getMultiEnum,
  setMultiEnum,
  TEST_METHOD_OPTIONS,
  sectionGroups,
  sectionProgress,
  isSectionApplicable,
  sectionReason,
  onToggleSectionApplicable,
  summaryItemId,
  sampleCellItemId,
  sampleRows,
  sampleBalance,
  rowCumulativeDiff,
  addSampleRow,
  addSampleGroupRow,
  removeSampleRow,
  onSampleCell,
  buildSampleRows,
  setPointSelect,
  CONCLUSION_OPTIONS,
  OVERALL_ITEM_ID,
  sectionConclusionId,
  sectionConclusions,
  suggestedOverall,
  overallConclusion,
  setSectionConclusion,
  setOverallConclusion,
  applySuggestedOverall,
  A14_WP_CODE,
  defectRows,
  defectItemId,
  buildDefectRows,
  addDefectRow,
  removeDefectRow,
  onDefectSummary,
  onDefectJumpToA14,
  // 增强项
  checkAllSubItems,
  uncheckAllSubItems,
  generateResultFromSubItems,
  applyExampleToStep,
  // 优化项
  stepStatus,
  quickMarkStep,
  overallProgressPercent,
  completedStepCount,
  totalApplicableStepCount,
  suggestedSectionConclusion,
  stepMethodSuggestion,
  shouldShowRollforward,
  // 向后兼容测试 expose（向导模式已无独立 mode/processFields/procItemId，此处为兼容）
  get mode() { return computedMode.value },
  get processFields() { return processFieldsForActive.value },
  procItemId: (field: string) => {
    // 基于当前 activeProcessIndex 或从 sheetName 推导
    const k = activeProcessIndex.value >= 0 ? activeProcessIndex.value + 1 : (() => {
      const m = (props.sheetName || '').match(/C1-4-([1-6])/)
      return m ? Number(m[1]) : 4
    })()
    return `${C1_ITEM_PREFIX}4-${k}-${field}`
  },
  // Dialog visibility (for testing)
  stepDialogVisible,
  exampleDrawerVisible,
  processDialogVisible,
  detailDialogVisible,
  sampleDialogVisible,
})
</script>

<style scoped>
.c1-entity-control {
  padding: 12px;
  font-size: 13px;
}

.c1-loading {
  padding: 24px;
}

/* 顶部操作引导区（蓝色渐变） */
.c1-guide {
  margin-bottom: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  background: linear-gradient(135deg, #e6f0ff 0%, #d6e4ff 100%);
  border: 1px solid #b9d2ff;
}

.c1-guide-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 13px;
  color: #1d4ed8;
  margin-bottom: 10px;
}

.c1-guide-head-icon {
  color: #2563eb;
}

.c1-guide-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 20px;
}

.c1-guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.c1-guide-no {
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.c1-guide-txt {
  flex: 1 1 auto;
  min-width: 0;
}

.c1-guide-title {
  font-weight: 600;
  font-size: 13px;
  color: #1e293b;
}

.c1-guide-desc {
  font-size: 12px;
  color: #475569;
  line-height: 1.4;
}

/* 方法论上下文（琥珀色左边线区块） */
.c1-methodology {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 4px 0 10px;
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #d97706;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #92400e;
  line-height: 1.5;
}

.c1-meth-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  color: #d97706;
}

.c1-meth-text {
  flex: 1 1 auto;
}

/* 九段分组导航 */
.c1-section-nav {
  margin-bottom: 12px;
}

.c1-sec-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.c1-sec-title {
  font-weight: 600;
  font-size: 13px;
}

.c1-sec-applicable {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
}

.c1-applicable-label {
  color: #909399;
  font-size: 12px;
}

.c1-sec-progress {
  margin-left: auto;
}

.c1-sec-body {
  padding: 4px 0;
}

.c1-sec-trimmed {
  padding: 4px 0;
}

.c1-trim-reason {
  margin-top: 4px;
  color: #606266;
  font-size: 12px;
}

/* 步骤表格（L0 九段内的步骤行） */
.c1-step-table {
  margin-top: 8px;
}

.c1-step-row {
  cursor: pointer;
  transition: background 0.15s;
}

.c1-step-row:hover {
  background: #f3eefb;
}

.c1-step-row.c1-step-done {
  background: #f0fdf4;
}

.c1-cell-center {
  text-align: center;
}

.c1-cell-empty {
  color: #c0c4cc;
}

/* 财务报告段过程记录按钮 */
.c1-fr-link {
  margin-top: 10px;
  padding: 8px 0;
}

/* el-card */
.c1-card {
  margin-top: 8px;
}

.c1-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.c1-card-title {
  font-weight: 600;
  font-size: 13px;
}

.c1-card-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.c1-ai-btn .el-icon {
  margin-right: 2px;
}

/* 浮动按钮区（右下角） */
.c1-fab-area {
  position: fixed;
  right: 32px;
  bottom: 32px;
  z-index: 1000;
}

/* 通用网格表格（13px 铁律） */
.c1-grid-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.c1-grid-table th,
.c1-grid-table td {
  border: 1px solid #ebeef5;
  padding: 4px 8px;
  text-align: left;
  vertical-align: middle;
}

.c1-grid-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}

.c1-cell-idx {
  text-align: center;
  color: #909399;
}

.c1-cell-name {
  font-weight: 500;
}

.c1-empty-row {
  text-align: center;
  color: #909399;
  padding: 12px;
}

/* 过程记录字段表 */
.c1-proc-table {
  margin-top: 8px;
}

.c1-proc-label {
  width: 140px;
  background: #fafafa;
  color: #606266;
  font-weight: 500;
}

.c1-proc-value {
  padding: 2px 6px;
}

/* AI辅助字段行 */
.c1-field-with-ai {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.c1-field-with-ai .el-input,
.c1-field-with-ai .el-textarea {
  flex: 1 1 auto;
}

/* 只读派生/公式列 */
.c1-formula-head,
.c1-formula-val {
  border-bottom: 1px dashed #b88230;
  cursor: help;
  color: #b88230;
}

/* 判断列表头 */
.c1-judge-head {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

/* 测试方法多选 */
.c1-method-group {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
}

.c1-formula-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.c1-sample-foot td {
  background: #fdf6ec;
  font-weight: 600;
}

/* 附件相关 */
.c1-attach-flag {
  color: #4b2d77;
  font-size: 15px;
  vertical-align: middle;
}

.c1-attach-upload {
  display: inline-block;
}

.c1-attach-cell {
  text-align: center;
}

/* 关联底稿索引行 */
.c1-ref-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #ebeef5;
  font-size: 13px;
}

.c1-ref-label {
  flex: 0 0 96px;
  color: #606266;
  font-weight: 500;
  padding-top: 4px;
}

.c1-ref-body {
  flex: 1 1 auto;
  min-width: 0;
}

.c1-ref-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
  align-items: center;
}

.c1-ref-empty {
  color: #c0c4cc;
}

/* 整体结论 */
.c1-conclusion-card,
.c1-defect-card {
  margin-top: 12px;
}

.c1-conclusion-table {
  margin-bottom: 12px;
}

.c1-overall-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #f3eefb;
  border-radius: 6px;
}

.c1-overall-label {
  font-weight: 600;
  font-size: 13px;
  color: #4b2d77;
}

.c1-overall-select {
  min-width: 160px;
}

.c1-suggest-tag {
  margin-left: 2px;
}

.c1-defect-jump {
  text-align: center;
}

/* Step Dialog form */
.c1-step-form {
  padding: 0 8px;
}

.c1-step-reason {
  margin-top: 8px;
}

/* readonly state */
.is-readonly .c1-step-row {
  cursor: default;
}

/* ─── 步骤内嵌编制参考 ─── */
.c1-step-example-ref {
  margin-bottom: 14px;
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  background: linear-gradient(135deg, #eef2ff 0%, #e8ecfb 100%);
  overflow: hidden;
}
.c1-step-example-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #dbeafe;
  font-weight: 600;
  font-size: 13px;
  color: #1e40af;
}
.c1-step-example-body {
  padding: 10px 14px;
  font-size: 12px;
  line-height: 1.7;
}
.c1-step-example-row {
  margin-bottom: 4px;
}
.c1-step-example-label {
  font-weight: 600;
  color: #4338ca;
  display: inline-block;
  min-width: 90px;
}
.c1-step-example-desc {
  color: #374151;
}

/* ─── C1 子项检查清单 ─── */
.c1-step-subitems {
  background: #fdf8e8;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.c1-subitem-head {
  font-weight: 600;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}
.c1-subitem-row {
  padding: 4px 0;
  line-height: 1.6;
}
.c1-subitem-row .el-checkbox {
  display: flex;
  align-items: flex-start;
  white-space: normal;
}
.c1-subitem-row .el-checkbox__label {
  white-space: normal;
  word-break: break-all;
  font-size: 13px;
}

/* ─── 步骤行子项计数标签 ─── */
.c1-sub-count {
  margin-left: 8px;
  font-size: 11px;
}
.c1-step-name-text {
  font-weight: 500;
}

/* ─── 子项批量操作按钮 ─── */
.c1-subitem-actions {
  float: right;
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

/* ─── 前推测试区域 ─── */
.c1-divider-rollforward {
  margin: 16px 0 8px;
}
.c1-rollforward-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  margin-bottom: 12px;
  background: #f0f9ff;
  border-left: 3px solid #3b82f6;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #1e40af;
}

/* ─── 编制提示（details 折叠） ─── */
.c1-edit-hint {
  margin-bottom: 12px;
  border: 1px solid #fde68a;
  border-radius: 6px;
  background: #fffbeb;
  overflow: hidden;
}
.c1-edit-hint-summary {
  padding: 8px 12px;
  font-weight: 600;
  font-size: 13px;
  color: #92400e;
  cursor: pointer;
  background: #fef3c7;
  border-bottom: 1px solid #fde68a;
}
.c1-edit-hint-body {
  padding: 10px 14px;
  font-size: 12px;
  color: #78350f;
  line-height: 1.7;
}
.c1-edit-hint-body p {
  margin: 4px 0;
}
.c1-edit-hint-note {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed #d97706;
  color: #b45309;
  font-style: italic;
}

/* ─── 示例 Drawer 结构化展示 ─── */
.c1-ex-card {
  padding: 8px;
}
.c1-ex-section {
  margin-bottom: 10px;
}
.c1-ex-label {
  font-weight: 600;
  color: #4b5563;
  font-size: 12px;
  display: inline-block;
  min-width: 80px;
}
.c1-ex-val {
  color: #1f2937;
  font-size: 13px;
}
.c1-ex-desc {
  margin-top: 4px;
  padding: 6px 10px;
  background: #f9fafb;
  border-radius: 4px;
  font-size: 12px;
  color: #374151;
  line-height: 1.6;
}
.c1-ex-meta {
  margin: 8px 0;
  font-size: 12px;
}
.c1-ex-meta td {
  padding: 3px 8px !important;
}
.c1-ex-rollforward {
  border-left: 3px solid #3b82f6;
  padding-left: 10px;
  background: #eff6ff;
  border-radius: 0 4px 4px 0;
  padding: 8px 12px;
}

/* ─── 样本表区域分组行 ─── */
.c1-sample-group-row {
  background: #f3f0ff;
}
.c1-sample-group-cell {
  padding: 6px 12px !important;
  text-align: left;
  font-weight: 600;
  color: #4b2d77;
  border-bottom: 2px solid #8b5cf6;
}

/* ─── 步骤三态视觉（优化1） ─── */
.c1-step-wip {
  background: #fffde6;
}
.c1-status-done, .c1-status-wip, .c1-status-todo {
  font-size: 14px;
}

/* ─── 总体完成度看板（优化6） ─── */
.c1-overall-progress-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.c1-overall-progress-label {
  font-weight: 600;
  font-size: 13px;
  color: #4b2d77;
  white-space: nowrap;
}
.c1-overall-progress-text {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}

/* ─── 段结论自动推导（优化2） ─── */
.c1-sec-conclusion-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ─── 汇总联动提示（优化3） ─── */
.c1-sync-hint {
  font-size: 11px;
  color: #9ca3af;
  margin-left: 8px;
}

/* ─── 测试方法建议（优化5） ─── */
.c1-method-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.c1-method-suggest {
  font-size: 11px;
  color: #d97706;
  cursor: help;
  white-space: nowrap;
  border-bottom: 1px dashed #d97706;
}

/* ─── 前推折叠（优化7） ─── */
.c1-rollforward-details {
  margin-top: 16px;
  margin-bottom: 8px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.c1-rollforward-details[open] {
  border-color: #3b82f6;
}
.c1-rollforward-summary {
  cursor: pointer;
  padding: 10px 14px;
  background: #f9fafb;
  font-weight: 600;
  font-size: 13px;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
  user-select: none;
  list-style: none;
}
.c1-rollforward-summary::-webkit-details-marker {
  display: none;
}
.c1-rollforward-details[open] .c1-rollforward-summary {
  background: #eff6ff;
  color: #1e40af;
  border-bottom-color: #bfdbfe;
}
.c1-rollforward-content {
  padding: 12px 14px;
}
</style>
