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
                    <th style="min-width: 260px">程序名称</th>
                    <th style="width: 80px">适用?</th>
                    <th style="width: 100px">执行人</th>
                    <th style="width: 120px">结果</th>
                    <th style="width: 100px">索引</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(step, si) in groupedPrograms(g.slug)"
                    :key="step.row || si"
                    class="c1-step-row"
                    :class="{ 'c1-step-done': isStepDone(g.slug, si) }"
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
                  </tr>
                  <tr v-if="groupedPrograms(g.slug).length === 0">
                    <td colspan="6" class="c1-empty-row">本段暂无程序步骤数据</td>
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

          <!-- 子项检查清单（来自源模板结构化子项） -->
          <div v-if="activeStep.step?.subItems?.length" class="c1-step-subitems">
            <div class="c1-subitem-head">该步骤包含以下检查事项：</div>
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
              <el-checkbox-group
                :model-value="stepMethodVal"
                :disabled="isReadonly"
                class="c1-method-group"
                @change="(v: any) => onStepMethodChange(v)"
              >
                <el-checkbox v-for="o in TEST_METHOD_OPTIONS" :key="o" :label="o" :value="o" />
              </el-checkbox-group>
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
        title="测试示例参考"
        direction="rtl"
        size="45%"
        append-to-body
        class="c1-example-drawer"
      >
        <el-alert
          title="示例（供参考），不参与进度"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <el-tabs v-model="activeExampleTab" type="border-card">
          <el-tab-pane label="示例1" name="C1-1">
            <GtOnlyOfficeSheet
              :wp-id="props.wpId"
              :project-id="props.projectId"
              sheet-name="C1-1"
              :readonly="true"
              style="height: calc(100vh - 260px)"
            />
          </el-tab-pane>
          <el-tab-pane label="示例2" name="C1-2">
            <GtOnlyOfficeSheet
              :wp-id="props.wpId"
              :project-id="props.projectId"
              sheet-name="C1-2"
              :readonly="true"
              style="height: calc(100vh - 260px)"
            />
          </el-tab-pane>
          <el-tab-pane label="示例3" name="C1-3">
            <GtOnlyOfficeSheet
              :wp-id="props.wpId"
              :project-id="props.projectId"
              sheet-name="C1-3"
              :readonly="true"
              style="height: calc(100vh - 260px)"
            />
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
        </template>

        <template #footer>
          <el-button @click="detailDialogVisible = false">关闭</el-button>
          <el-button type="primary" :disabled="isReadonly" @click="detailDialogVisible = false">保存</el-button>
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
            <tr v-for="(row, i) in sampleRows" :key="row.__rid">
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

// ─── C1-4-4 样本明细 ─────────────────────────────────────────────────────

interface SampleRow {
  __rid: number
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
  const re = /^C1-4-4-sample-(\d+)-(date|account|ref|desc|debit|credit)$/
  for (const [itemId, r] of c1data.responses.value.entries()) {
    const m = itemId.match(re)
    if (!m) continue
    const rid = Number(m[1])
    const col = m[2] as (typeof SAMPLE_COLS)[number]
    const cur = byRid.get(rid) ?? { __rid: rid }
    ;(cur as any)[col] = r.remark ?? ''
    byRid.set(rid, cur)
  }
  const rows = [...byRid.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([rid, v]) => ({
      __rid: rid,
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
  return rows.map((r) => ({
    date: r.date, account: r.account, ref: r.ref, desc: r.desc,
    debit: Number(r.debit) || 0, credit: Number(r.credit) || 0,
  }))
}

function rowCumulativeDiff(i: number): number {
  const slice = toJeSamples(sampleRows.value.slice(0, i + 1))
  const b = calcSampleBalance(slice)
  return b.debitTotal - b.creditTotal
}

function addSampleRow(): void {
  if (isReadonly.value) return
  sampleRows.value.push({
    __rid: sampleRidSeq++, date: '', account: '', ref: '', desc: '', debit: '', credit: '',
  })
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
</style>
