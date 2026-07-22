<template>
  <div class="h2-tab-review-record">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：按工程项目记录在建工程核查过程（资料/历年发生额/本期增加/利息/状态/挂账/关联方/受限/减值），与 H2-2/H2-5/H2-8/H2-10·11/H2-15/H2-17 勾稽，形成按项目审核记录与总体结论。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          size="small"
          clearable
          placeholder="搜索工程名称"
          style="width:180px"
          @change="state.setFilterKeyword(keyword)"
        />
        <el-select
          v-model="riskFilter"
          size="small"
          clearable
          placeholder="风险筛选"
          style="width:140px"
          @change="state.setFilterRisk(riskFilter)"
        >
          <el-option v-for="r in riskOptions" :key="r" :label="r" :value="r" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">{{ state.riskSummary.value.total }} 个工程</el-tag>
        <el-tag size="small" type="success">已填妥 {{ state.riskSummary.value.filled }}</el-tag>
        <el-button v-if="!isReadonly" size="small" @click="handleSyncH22">从 H2-2 带入</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="openDialog()">+ 新增工程核查</el-button>
        <el-button size="small" circle @click="openReview('H2-6-records')">💬</el-button>
      </div>
    </div>

    <!-- 风险总览 -->
    <div class="risk-bar" v-if="state.riskSummary.value.total > 0">
      <span class="risk-label">跨工程风险：</span>
      <el-tag v-if="state.riskSummary.value.transferRisk" size="small" type="danger">
        未转固 {{ state.riskSummary.value.transferRisk }}
      </el-tag>
      <el-tag v-if="state.riskSummary.value.longTerm" size="small" type="warning">
        长期挂账/无发生 {{ state.riskSummary.value.longTerm }}
      </el-tag>
      <el-tag v-if="state.riskSummary.value.suspended" size="small" type="warning">
        停工 {{ state.riskSummary.value.suspended }}
      </el-tag>
      <el-tag v-if="state.riskSummary.value.relatedParty" size="small">
        关联方 {{ state.riskSummary.value.relatedParty }}
      </el-tag>
      <el-tag v-if="state.riskSummary.value.impairment" size="small" type="danger">
        减值 {{ state.riskSummary.value.impairment }}
      </el-tag>
      <span v-if="!hasAnyRisk" class="muted">暂无自动风险标记</span>
    </div>

    <!-- 多项目汇总表 -->
    <el-card shadow="never" class="review-card">
      <template #header>
        <div class="section-header">
          <span>工程项目核查一览（点击「填写」打开弹窗）</span>
        </div>
      </template>
      <el-table :data="state.filteredRecords.value" border stripe size="small" empty-text="暂无工程记录，请从 H2-2 带入或新增">
        <el-table-column type="index" label="序" width="44" />
        <el-table-column label="工程项目" min-width="140">
          <template #default="{ row }">
            <div class="proj-name">{{ row.projectName || '（未命名）' }}</div>
            <div v-if="row.subProjectName" class="proj-sub">{{ row.subProjectName }}</div>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }"><span class="amt">{{ fmtAmt(row.cipEnd) }}</span></template>
        </el-table-column>
        <el-table-column label="本期增加" width="100" align="right">
          <template #default="{ row }"><span class="amt">{{ fmtAmt(row.cipIncrease) }}</span></template>
        </el-table-column>
        <el-table-column label="进度%" width="72" align="right">
          <template #default="{ row }">{{ row.completionRate != null ? row.completionRate.toFixed(1) : '—' }}</template>
        </el-table-column>
        <el-table-column label="风险" min-width="140">
          <template #default="{ row }">
            <el-tag
              v-for="f in calcRiskFlags(row)"
              :key="f"
              size="small"
              :type="flagType(f)"
              class="flag-tag"
            >{{ f }}</el-tag>
            <span v-if="!calcRiskFlags(row).length" class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="勾稽" width="88" align="center">
          <template #default="{ row }">
            <el-tag v-if="reconErrorCount(row) > 0" size="small" type="danger">差异{{ reconErrorCount(row) }}</el-tag>
            <el-tag v-else-if="reconWarnCount(row) > 0" size="small" type="warning">提示{{ reconWarnCount(row) }}</el-tag>
            <el-tag v-else size="small" type="success">一致</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="填写进度" width="120">
          <template #default="{ row }">
            <el-progress
              :percentage="calcFillProgress(row)"
              :stroke-width="10"
              :status="calcFillProgress(row) >= 80 ? 'success' : undefined"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openDialog(row)">
              {{ isReadonly ? '查看' : '填写' }}
            </el-button>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="danger"
              link
              @click="handleRemove(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 总体说明与结论 -->
    <el-card shadow="never" class="review-card">
      <template #header>
        <div class="section-header"><span>跨项目审计说明</span></div>
      </template>
      <el-input
        :model-value="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="概述核查范围、抽样覆盖、跨工程共性问题及与 H2-2/H2-5/H2-8 等勾稽情况…"
        :disabled="isReadonly"
        @change="(v: string) => state.saveAuditNote(v)"
      />
    </el-card>

    <el-card shadow="never" class="review-card">
      <template #header>
        <div class="section-header"><span>审计结论与签章</span></div>
      </template>
      <el-input
        v-model="state.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="综合各工程核查结论：存在性、完整性、计价与转固时点、减值与披露…"
        :disabled="isReadonly"
        @blur="state.saveConclusion(state.conclusion.value)"
      />
      <div class="sign-section">
        <div class="meta-row sign-row">
          <span class="meta-label">编制：</span>
          <el-input
            v-if="!isReadonly"
            v-model="state.signature.value.preparedBy"
            size="small"
            style="width:120px"
            placeholder="编制人"
            @change="onSignChange"
          />
          <span v-else class="sign-placeholder">{{ state.signature.value.preparedBy || '________' }}</span>
          <el-date-picker
            v-if="!isReadonly"
            v-model="state.signature.value.preparedDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            style="width:140px;margin-left:8px"
            @change="onSignChange"
          />
          <span style="margin-left:16px">复核：</span>
          <el-input
            v-if="!isReadonly"
            v-model="state.signature.value.reviewedBy"
            size="small"
            style="width:120px"
            placeholder="复核人"
            @change="onSignChange"
          />
          <span v-else class="sign-placeholder">{{ state.signature.value.reviewedBy || '________' }}</span>
          <el-date-picker
            v-if="!isReadonly"
            v-model="state.signature.value.reviewedDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            style="width:140px;margin-left:8px"
            @change="onSignChange"
          />
        </div>
      </div>
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>本表按<strong>工程项目</strong>编制；单工程在弹窗内完成 1–9 节核查，多工程在汇总表管理进度与风险。</li>
        <li>优先「从 H2-2 带入」同步账面期初/增加/减少/期末，再逐项弹窗填写定性结论。</li>
        <li>状态查验与历年/本期发生额联动：达预定可使用且仍有余额 →「未转固」；本期无发生且有余额 →「长期挂账」。</li>
        <li>弹窗内可「同步上游状态」自动勾稽 H2-5 转固时点与 H2-13 盘点状态；「一键生成本工程结论草稿」汇总 1–9 节与勾稽差异。</li>
        <li>索引默认指向 H2-8 / H2-10·11 / H2-15 / H2-17，可按实际修改。</li>
      </ul>
    </details>

    <!-- ═══ 单工程弹窗填充 ═══ -->
    <el-dialog
      v-model="dialog.visible"
      :title="dialogTitle"
      width="860px"
      top="4vh"
      destroy-on-close
      class="h2-6-fill-dialog"
      :close-on-click-modal="false"
    >
      <div v-if="dialog.draft" class="dialog-body">
        <!-- 工程标识 -->
        <el-form label-width="100px" size="small" class="dialog-form">
          <div class="dlg-section">
            <div class="dlg-title">工程标识</div>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="工程项目">
                  <el-select
                    v-if="!isReadonly && state.projectList.value.length"
                    v-model="dialog.draft.projectName"
                    filterable
                    allow-create
                    default-first-option
                    placeholder="选择或输入工程名称"
                    style="width:100%"
                  >
                    <el-option v-for="p in state.projectList.value" :key="p" :label="p" :value="p" />
                  </el-select>
                  <el-input v-else v-model="dialog.draft.projectName" :disabled="isReadonly" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="子项目">
                  <el-input v-model="dialog.draft.subProjectName" :disabled="isReadonly" placeholder="可选" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="施工单位">
                  <el-input v-model="dialog.draft.contractor" :disabled="isReadonly" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="监理单位">
                  <el-input v-model="dialog.draft.supervisor" :disabled="isReadonly" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="账面期末">
                  <span class="amt">{{ fmtAmt(dialog.draft.cipEnd) }}</span>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <!-- 1 -->
          <div class="dlg-section">
            <div class="dlg-title">1、项目综合描述</div>
            <p class="hint">{{ tips.s1 }}</p>
            <el-input
              v-model="dialog.draft.projectDescription"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="工程性质、地点、合同主体、预算与工期…"
            />
          </div>

          <!-- 2 -->
          <div class="dlg-section">
            <div class="dlg-title">2、资料及合同核对情况</div>
            <p class="hint">{{ tips.s2 }}</p>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="A 资料索引">
                  <el-input v-model="dialog.draft.docCheckIndex" :disabled="isReadonly" placeholder="索引（ ）" />
                </el-form-item>
                <el-input
                  v-model="dialog.draft.docCheckNote"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  :disabled="isReadonly"
                  placeholder="资料核对情况说明"
                />
              </el-col>
              <el-col :span="12">
                <el-form-item label="B 合同索引">
                  <el-input v-model="dialog.draft.contractCheckIndex" :disabled="isReadonly" placeholder="索引（ ）" />
                </el-form-item>
                <el-input
                  v-model="dialog.draft.contractCheckNote"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  :disabled="isReadonly"
                  placeholder="合同核对情况说明"
                />
              </el-col>
            </el-row>
          </div>

          <!-- 3 -->
          <div class="dlg-section">
            <div class="dlg-title">3、历年发生额情况</div>
            <p class="hint">{{ tips.s3 }}</p>
            <el-table :data="dialog.draft.yearBalances" border size="small" class="yb-table">
              <el-table-column label="年份" width="100">
                <template #default="{ row }">
                  <el-input v-if="!isReadonly" v-model="row.yearLabel" size="small" />
                  <span v-else>{{ row.yearLabel }}</span>
                </template>
              </el-table-column>
              <el-table-column label="年度" width="90">
                <template #default="{ row }">
                  <el-input v-if="!isReadonly" v-model="row.year" size="small" placeholder="YYYY" />
                  <span v-else>{{ row.year || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="期初数" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!isReadonly && row.yearLabel !== '合计'"
                    v-model="row.begin"
                    :controls="false"
                    size="small"
                    style="width:100%"
                  />
                  <span v-else class="amt">{{ fmtAmt(row.begin) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="本期借方" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!isReadonly && row.yearLabel !== '合计'"
                    v-model="row.debit"
                    :controls="false"
                    size="small"
                    style="width:100%"
                  />
                  <span v-else class="amt">{{ fmtAmt(row.debit) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="本期贷方" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!isReadonly && row.yearLabel !== '合计'"
                    v-model="row.credit"
                    :controls="false"
                    size="small"
                    style="width:100%"
                  />
                  <span v-else class="amt">{{ fmtAmt(row.credit) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="期末数" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!isReadonly && row.yearLabel !== '合计'"
                    v-model="row.end"
                    :controls="false"
                    size="small"
                    style="width:100%"
                  />
                  <span v-else class="amt">{{ fmtAmt(row.end) }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!isReadonly" class="yb-actions">
              <el-button size="small" @click="addYearRow">+ 插入中间年</el-button>
              <el-button size="small" @click="pullCurrentYearFromSnapshot">用账面快照填「本年」</el-button>
            </div>
          </div>

          <!-- 4 -->
          <div class="dlg-section">
            <div class="dlg-title">4、本期发生额查验</div>
            <p class="hint">{{ tips.s4 }}</p>
            <el-form-item label="索引">
              <el-input v-model="dialog.draft.additionCheckIndex" :disabled="isReadonly" style="width:200px" />
              <span class="chip-inline"><GtIndexChip value="wp:H2-8" :context-project-id="projectId" /></span>
            </el-form-item>
            <el-input
              v-model="dialog.draft.additionCheckNote"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :disabled="isReadonly"
              placeholder="抽凭范围、覆盖率、异常事项…"
            />
          </div>

          <!-- 5 -->
          <div class="dlg-section">
            <div class="dlg-title">5、利息资本化审核</div>
            <p class="hint">{{ tips.s5 }}</p>
            <el-form-item label="索引">
              <el-input v-model="dialog.draft.interestCapIndex" :disabled="isReadonly" style="width:200px" />
              <span class="chip-inline"><GtIndexChip value="wp:H2-10" :context-project-id="projectId" /></span>
            </el-form-item>
            <el-input
              v-model="dialog.draft.interestCapNote"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :disabled="isReadonly"
              placeholder="是否资本化、与测算表差异…"
            />
          </div>

          <!-- 6 -->
          <div class="dlg-section">
            <div class="dlg-title">6、状态查验</div>
            <p class="hint blue-hint">{{ tips.s6 }}</p>
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="(1)是否存在">
                  <el-radio-group v-model="dialog.draft.assetExists" :disabled="isReadonly">
                    <el-radio value="yes">是</el-radio>
                    <el-radio value="no">否</el-radio>
                    <el-radio value="na">不适用</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="达预定可用">
                  <el-radio-group v-model="dialog.draft.reachedUsableState" :disabled="isReadonly" @change="onUsableChange">
                    <el-radio value="yes">是</el-radio>
                    <el-radio value="partial">部分</el-radio>
                    <el-radio value="no">否</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="是否停工">
                  <el-switch v-model="dialog.draft.isSuspended" :disabled="isReadonly" @change="onSuspendedChange" />
                </el-form-item>
                <el-form-item label="未转固风险">
                  <el-switch v-model="dialog.draft.transferRisk" :disabled="isReadonly" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="存在说明">
              <el-input v-model="dialog.draft.assetExistsNote" :disabled="isReadonly" placeholder="现场观察结论…" />
            </el-form-item>
            <el-form-item label="(2)现状描述">
              <el-input
                v-model="dialog.draft.statusDescription"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                :disabled="isReadonly"
                placeholder="完工进度、是否达预定可使用状态、是否停工…"
              />
            </el-form-item>

            <!-- H2-5 / H2-13 自动勾稽 -->
            <div class="recon-panel">
              <div class="recon-header">
                <span class="dlg-title" style="margin:0">与 H2-5 / H2-13 状态勾稽</span>
                <div class="recon-actions">
                  <span class="chip-inline"><GtIndexChip value="wp:H2-5" :context-project-id="projectId" /></span>
                  <span class="chip-inline"><GtIndexChip value="wp:H2-13" :context-project-id="projectId" /></span>
                  <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleApplyReconcile">
                    同步上游状态
                  </el-button>
                </div>
              </div>
              <div class="recon-summary" v-if="liveReconcile">
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="H2-5">
                    <template v-if="liveReconcile.h25?.found">
                      五条件{{ liveReconcile.h25.allConditionsMet ? '✓' : '✗' }}；
                      转固日 {{ liveReconcile.h25.transferDate || '无' }}；
                      及时 {{ liveReconcile.h25.timelyTransfer == null ? '—' : liveReconcile.h25.timelyTransfer ? '是' : '否' }}
                    </template>
                    <span v-else class="muted">无本工程行 / 未取数</span>
                  </el-descriptions-item>
                  <el-descriptions-item label="H2-13">
                    <template v-if="liveReconcile.h213?.found">
                      {{ liveReconcile.h213.result }}；达可用 {{ liveReconcile.h213.readyForUse || '—' }}；
                      {{ liveReconcile.h213.constructionStatus || '—' }}（{{ liveReconcile.h213.rowCount }} 行）
                    </template>
                    <span v-else class="muted">无抽盘行 / 未取数</span>
                  </el-descriptions-item>
                </el-descriptions>
                <ul v-if="liveReconcile.issues.length" class="recon-issues">
                  <li
                    v-for="(iss, idx) in liveReconcile.issues"
                    :key="idx"
                    :class="'lvl-' + iss.level"
                  >
                    <el-tag size="small" :type="iss.level === 'error' ? 'danger' : iss.level === 'warn' ? 'warning' : 'info'">
                      {{ iss.source }}
                    </el-tag>
                    {{ iss.message }}
                  </li>
                </ul>
                <p v-else class="hint" style="margin-top:8px">未见勾稽差异或提示。</p>
              </div>
            </div>
          </div>

          <!-- 7 -->
          <div class="dlg-section">
            <div class="dlg-title">7、是否长期挂账</div>
            <p class="hint blue-hint">{{ tips.s7 }}</p>
            <el-row :gutter="12">
              <el-col :span="10">
                <el-form-item label="长期挂账">
                  <el-radio-group v-model="dialog.draft.isLongTermOutstanding" :disabled="isReadonly">
                    <el-radio value="yes">是</el-radio>
                    <el-radio value="no">否</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :span="10">
                <el-form-item label="无发生年数">
                  <el-input-number
                    v-model="dialog.draft.noMovementYears"
                    :disabled="isReadonly"
                    :min="0"
                    :controls="true"
                    size="small"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-input
              v-model="dialog.draft.longTermNote"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :disabled="isReadonly"
              placeholder="原因及拟采取的进一步程序…"
            />
          </div>

          <!-- 8 -->
          <div class="dlg-section">
            <div class="dlg-title">8、有无关联方交易</div>
            <p class="hint blue-hint">{{ tips.s8 }}</p>
            <el-form-item label="关联方">
              <el-radio-group v-model="dialog.draft.hasRelatedParty" :disabled="isReadonly">
                <el-radio value="yes">有</el-radio>
                <el-radio value="no">无</el-radio>
              </el-radio-group>
              <el-input
                v-model="dialog.draft.relatedPartyIndex"
                :disabled="isReadonly"
                placeholder="索引"
                style="width:140px;margin-left:12px"
              />
              <span class="chip-inline"><GtIndexChip value="wp:H2-17" :context-project-id="projectId" /></span>
            </el-form-item>
            <el-input
              v-model="dialog.draft.relatedPartyNote"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :disabled="isReadonly"
              placeholder="关联方、交易内容、授权与定价、披露提醒…"
            />
          </div>

          <!-- 9 -->
          <div class="dlg-section">
            <div class="dlg-title">9、是否受限 / 是否存在减值</div>
            <p class="hint blue-hint">{{ tips.s9a }}</p>
            <el-form-item label="是否受限">
              <el-radio-group v-model="dialog.draft.isRestricted" :disabled="isReadonly">
                <el-radio value="yes">是</el-radio>
                <el-radio value="no">否</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-input
              v-model="dialog.draft.restrictedNote"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }"
              :disabled="isReadonly"
              placeholder="抵押/担保情况及披露…"
              class="mb-8"
            />
            <p class="hint blue-hint">{{ tips.s9b }}</p>
            <el-form-item label="是否减值">
              <el-radio-group v-model="dialog.draft.hasImpairment" :disabled="isReadonly">
                <el-radio value="yes">是</el-radio>
                <el-radio value="no">否</el-radio>
              </el-radio-group>
              <el-input
                v-model="dialog.draft.impairmentIndex"
                :disabled="isReadonly"
                placeholder="索引"
                style="width:140px;margin-left:12px"
              />
              <span class="chip-inline"><GtIndexChip value="wp:H2-15" :context-project-id="projectId" /></span>
            </el-form-item>
            <el-input
              v-model="dialog.draft.impairmentNote"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :disabled="isReadonly"
              placeholder="减值迹象与测算结论…"
            />
          </div>

          <div class="dlg-section">
            <div class="dlg-title-row">
              <span class="dlg-title" style="margin:0">本工程核查结论</span>
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                @click="handleGenerateConclusion"
              >一键生成本工程结论草稿</el-button>
            </div>
            <p class="hint">依据 1–9 节填写内容及 H2-5/H2-13 勾稽结果生成规则草稿，请复核后定稿。</p>
            <el-input
              v-model="dialog.draft.projectConclusion"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 12 }"
              :disabled="isReadonly"
              placeholder="点击上方按钮生成，或手工填写本工程核查结论…"
            />
            <el-form-item label="备注" style="margin-top:12px">
              <el-input v-model="dialog.draft.remark" type="textarea" :autosize="{ minRows: 1 }" :disabled="isReadonly" />
            </el-form-item>
            <div class="dlg-progress">
              本工程填写进度：
              <el-progress
                :percentage="calcFillProgress(dialog.draft)"
                :stroke-width="12"
                style="width:200px;display:inline-flex;margin-left:8px"
              />
              <template v-if="calcRiskFlags(dialog.draft).length">
                <el-tag
                  v-for="f in calcRiskFlags(dialog.draft)"
                  :key="f"
                  size="small"
                  :type="flagType(f)"
                  class="flag-tag"
                >{{ f }}</el-tag>
              </template>
            </div>
          </div>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="dialog.visible = false">{{ isReadonly ? '关闭' : '取消' }}</el-button>
        <el-button v-if="!isReadonly" type="primary" @click="saveDialog">确认回写</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabReviewRecord.vue — H2-6 按项目审核记录
 * 多工程汇总表 + 弹窗填充（对齐致同 Excel 1–9 节）+ 风险联动
 */
import { ref, reactive, computed, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH2ReviewRecord,
  createEmptyRecord,
  calcFillProgress,
  calcRiskFlags,
  reconcileProjectStatus,
  applyReconcileSuggestions,
  buildProjectConclusionDraft,
  H2_6_SECTION_TIPS,
  type H2ProjectReviewRecord,
} from '../../composables/useH2ReviewRecord'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2ReviewRecord({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const tips = H2_6_SECTION_TIPS
const keyword = ref('')
const riskFilter = ref('')
const riskOptions = ['未转固', '停工', '长期挂账', '本期无发生', '关联方', '受限', '减值']

const hasAnyRisk = computed(() => {
  const s = state.riskSummary.value
  return s.transferRisk + s.longTerm + s.suspended + s.relatedParty + s.impairment > 0
})

const dialog = reactive<{
  visible: boolean
  draft: H2ProjectReviewRecord | null
  isNew: boolean
}>({
  visible: false,
  draft: null,
  isNew: false,
})

const dialogTitle = computed(() => {
  if (!dialog.draft) return '工程核查记录'
  const name = dialog.draft.projectName || '未命名工程'
  const sub = dialog.draft.subProjectName ? `－${dialog.draft.subProjectName}` : ''
  return `在建工程审核记录：${name}${sub}`
})

/** 弹窗内实时勾稽（随 draft 字段变化重算） */
const liveReconcile = computed(() => {
  if (!dialog.draft?.projectName) return null
  return reconcileProjectStatus(dialog.draft, props.allResponses)
})

function reconErrorCount(row: H2ProjectReviewRecord): number {
  return reconcileProjectStatus(row, props.allResponses).issues.filter(i => i.level === 'error').length
}

function reconWarnCount(row: H2ProjectReviewRecord): number {
  return reconcileProjectStatus(row, props.allResponses).issues.filter(i => i.level === 'warn').length
}

function openDialog(row?: H2ProjectReviewRecord): void {
  if (row) {
    dialog.draft = JSON.parse(JSON.stringify(row)) as H2ProjectReviewRecord
    if (dialog.draft.projectConclusion == null) dialog.draft.projectConclusion = ''
    dialog.isNew = false
  } else {
    dialog.draft = createEmptyRecord()
    dialog.isNew = true
  }
  dialog.visible = true
}

function saveDialog(): void {
  if (!dialog.draft || props.isReadonly) return
  if (!dialog.draft.projectName.trim()) {
    ElMessage.warning('请填写工程项目名称')
    return
  }
  const cur = dialog.draft.yearBalances.find(y => y.yearLabel === '本年')
  if (cur) {
    dialog.draft.cipBegin = cur.begin
    dialog.draft.cipIncrease = cur.debit
    dialog.draft.cipDecrease = cur.credit
    dialog.draft.cipEnd = cur.end
  }
  state.saveRecordDraft(dialog.draft)
  dialog.visible = false
  ElMessage.success('已回写本工程核查记录')
}

async function handleRemove(rowId: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该工程核查记录？', '删除确认', { type: 'warning' })
    state.removeRecord(rowId)
  } catch { /* cancel */ }
}

function handleSyncH22(): void {
  const { added, updated } = state.syncFromH22()
  if (!added && !updated) {
    ElMessage.info('H2-2 暂无工程行，或已全部同步')
    return
  }
  ElMessage.success(`已同步：新增 ${added}，更新账面 ${updated}`)
}

function handleApplyReconcile(): void {
  if (!dialog.draft || props.isReadonly) return
  const result = reconcileProjectStatus(dialog.draft, props.allResponses)
  const keys = Object.keys(result.suggestedPatch)
  if (!keys.length) {
    ElMessage.info(result.issues.some(i => i.level === 'error')
      ? '存在勾稽差异但无自动回填项，请人工核实'
      : '无需同步，或上游无本工程数据')
    return
  }
  dialog.draft = applyReconcileSuggestions(dialog.draft, result)
  ElMessage.success(`已按 H2-5/H2-13 回填 ${keys.length} 项建议字段，请复核`)
}

async function handleGenerateConclusion(): Promise<void> {
  if (!dialog.draft || props.isReadonly) return
  if (!dialog.draft.projectName.trim()) {
    ElMessage.warning('请先填写工程项目名称')
    return
  }
  const recon = reconcileProjectStatus(dialog.draft, props.allResponses)
  const draft = buildProjectConclusionDraft(dialog.draft, recon)
  if (dialog.draft.projectConclusion.trim()) {
    try {
      await ElMessageBox.confirm('本工程结论已有内容，是否覆盖为规则草稿？', '生成结论草稿', { type: 'warning' })
    } catch {
      return
    }
  }
  dialog.draft.projectConclusion = draft
  ElMessage.success('已生成本工程结论草稿，请复核后定稿')
}

function addYearRow(): void {
  if (!dialog.draft || props.isReadonly) return
  const totalIdx = dialog.draft.yearBalances.findIndex(y => y.yearLabel === '合计')
  const insertAt = totalIdx >= 0 ? totalIdx : dialog.draft.yearBalances.length
  dialog.draft.yearBalances.splice(insertAt, 0, {
    rowId: `yb-${Date.now().toString(36)}`,
    yearLabel: '中间年',
    year: '',
    begin: 0,
    debit: 0,
    credit: 0,
    end: 0,
  })
}

function pullCurrentYearFromSnapshot(): void {
  if (!dialog.draft || props.isReadonly) return
  const name = dialog.draft.projectName
  const src = state.detailProjects.value.find(
    p => p.rowId === dialog.draft!.sourceDetailRowId || p.name === name,
  )
  if (!src) {
    ElMessage.warning('未在 H2-2 找到对应工程，请先选择工程名称或从 H2-2 带入')
    return
  }
  dialog.draft.cipBegin = src.cipBegin
  dialog.draft.cipIncrease = src.cipIncrease
  dialog.draft.cipDecrease = src.cipDecrease
  dialog.draft.cipEnd = src.cipEnd
  dialog.draft.completionRate = src.completionRate
  if (!dialog.draft.contractor) dialog.draft.contractor = src.contractor
  if (!dialog.draft.supervisor) dialog.draft.supervisor = src.supervisor
  const cur = dialog.draft.yearBalances.find(y => y.yearLabel === '本年')
  if (cur) {
    cur.begin = src.cipBegin
    cur.debit = src.cipIncrease
    cur.credit = src.cipDecrease
    cur.end = src.cipEnd
  }
  ElMessage.success('已用 H2-2 账面填入「本年」行')
}

function onUsableChange(): void {
  if (!dialog.draft) return
  if (dialog.draft.reachedUsableState === 'yes' && dialog.draft.cipEnd > 0) {
    dialog.draft.transferRisk = true
  }
}

function onSuspendedChange(): void {
  if (!dialog.draft) return
  if (dialog.draft.isSuspended && dialog.draft.hasImpairment === '') {
    dialog.draft.hasImpairment = 'yes'
  }
}

function onSignChange(): void {
  state.saveSignature(state.signature.value)
}

function openReview(id: string): void {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function flagType(f: string): 'danger' | 'warning' | 'info' | 'success' | undefined {
  if (f === '未转固' || f === '减值') return 'danger'
  if (f === '停工' || f === '长期挂账' || f === '本期无发生') return 'warning'
  return 'info'
}
</script>

<style scoped>
.h2-tab-review-record { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap, .chip-inline { display: inline-flex; align-items: center; margin-left: 8px; }
.risk-bar {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  margin-bottom: 12px; padding: 8px 12px;
  background: var(--el-fill-color-lighter); border-radius: 4px;
}
.risk-label { color: var(--el-text-color-secondary); font-size: 12px; }
.review-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.proj-name { font-weight: 600; }
.proj-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.amt { font-variant-numeric: tabular-nums; }
.flag-tag { margin: 0 2px 2px 0; }
.muted { color: var(--el-text-color-placeholder); font-size: 12px; }
.sign-section { margin-top: 12px; }
.sign-row { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.meta-label { font-weight: 500; color: var(--el-text-color-secondary); }
.sign-placeholder { font-weight: 600; text-decoration: underline; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }

.dialog-body { max-height: 70vh; overflow-y: auto; padding-right: 4px; }
.dlg-section {
  margin-bottom: 16px; padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.dlg-section:last-child { border-bottom: none; }
.dlg-title { font-weight: 600; margin-bottom: 6px; color: var(--el-text-color-primary); }
.dlg-title-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 6px; flex-wrap: wrap;
}
.hint {
  font-size: 12px; color: var(--el-text-color-secondary);
  margin: 0 0 8px; line-height: 1.5;
}
.blue-hint { color: #3b82c4; }
.yb-table { margin-bottom: 8px; }
.yb-actions { display: flex; gap: 8px; margin-top: 4px; }
.dlg-progress { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.mb-8 { margin-bottom: 8px; }
.recon-panel {
  margin-top: 12px; padding: 10px 12px;
  background: var(--el-fill-color-lighter); border-radius: 4px;
  border: 1px solid var(--el-border-color-extra-light);
}
.recon-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.recon-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.recon-issues {
  margin: 8px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.7;
}
.recon-issues .lvl-error { color: var(--el-color-danger); }
.recon-issues .lvl-warn { color: var(--el-color-warning-dark-2); }
.recon-issues li { margin-bottom: 2px; }
</style>
