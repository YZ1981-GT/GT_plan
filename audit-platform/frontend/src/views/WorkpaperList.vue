<template>
  <div class="gt-wp-list gt-fade-in">
    <!-- 顶部筛选栏 -->
    <div class="gt-wp-filter-bar">
      <el-button text size="small" style="margin-right: 6px" @click="$router.push('/projects')">← 返回</el-button>
      <h2 class="gt-page-title">底稿管理</h2>
      <div v-if="treeData.length > 0" class="gt-wp-view-toggle">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="list">列表</el-radio-button>
          <el-radio-button value="kanban">看板</el-radio-button>
        </el-radio-group>
      </div>
      <div v-if="treeData.length > 0" class="gt-wp-filters">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索底稿..."
          clearable
          size="default"
          style="width: 200px"
          @input="onSearchDebounce"
        />
        <el-select v-model="filterCycle" placeholder="审计循环" clearable size="default" style="width: 160px">
          <el-option v-for="c in cycleOptions" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable size="default" style="width: 130px">
          <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="filterAssignee" placeholder="编制人" clearable size="default" style="width: 130px">
          <el-option label="全部" value="" />
          <el-option v-for="u in userOptions" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
        </el-select>
        <el-button @click="fetchData" :loading="loading">刷新</el-button>
        <el-button @click="showWpImport = true">📥 Excel导入</el-button>
        <el-button type="primary" :disabled="selectedWpIds.length === 0" @click="onBatchDownload" :loading="downloadLoading">
          批量下载 ({{ selectedWpIds.length }})
        </el-button>
        <el-button type="warning" :disabled="selectedWpIds.length === 0" @click="showBatchAssign = true">
          批量委派 ({{ selectedWpIds.length }})
        </el-button>
      </div>
    </div>

    <!-- 进度指示器（任务 7.2） -->
    <div v-if="wpList.length > 0 && viewMode === 'list'" class="gt-wp-progress-bar">
      <span>总体进度：{{ totalProgress.completed }}/{{ totalProgress.total }}</span>
      <el-progress :percentage="totalProgress.percent" :stroke-width="10" style="width: 200px; display: inline-block" />
      <span>{{ totalProgress.percent }}%</span>
      <template v-if="hasFilter">
        <el-divider direction="vertical" />
        <span>筛选结果：{{ filteredProgress.percent }}%（{{ filteredProgress.completed }}/{{ filteredProgress.total }}）</span>
      </template>
    </div>

    <!-- 主体：看板视图 / 列表视图 -->
    <WorkpaperKanban
      v-if="viewMode === 'kanban'"
      ref="kanbanRef"
      :project-id="projectId"
      :audit-cycle="filterCycle"
      @select="onKanbanSelect"
      @assign="onKanbanAssign"
    />
    <!-- 无底稿时：两栏布局（左操作入口 + 右审计程序总览） -->
    <div v-else-if="!loading && treeData.length === 0" class="gt-wp-intro-layout">
      <!-- 左栏：操作入口 -->
      <div class="gt-wp-intro-half">
        <div class="gt-wp-intro-icon">📋</div>
        <div class="gt-wp-intro-title">暂无底稿</div>
        <div class="gt-wp-intro-desc">前往底稿工作台生成项目底稿</div>
        <el-button type="primary" @click="goToWorkbench" style="margin-top: 20px">前往底稿工作台</el-button>
      </div>

      <!-- 右栏：审计程序总览（简洁列表，点击跳转） -->
      <div class="gt-wp-intro-half gt-wp-intro-half--guide">
        <h3 class="gt-wp-guide-title">审计程序与底稿体系</h3>
        <div class="gt-wp-guide-flow">
          <span class="gt-wp-flow-tag" style="background:#7c5cbf">B 风险评估</span>
          <span class="gt-wp-flow-arrow">→</span>
          <span class="gt-wp-flow-tag" style="background:#6a4fa0">C 控制测试</span>
          <span class="gt-wp-flow-arrow">→</span>
          <span class="gt-wp-flow-tag" style="background:#e6553a">D-N 实质性程序</span>
          <span class="gt-wp-flow-arrow">→</span>
          <span class="gt-wp-flow-tag" style="background:#1a8a5c">A 完成阶段</span>
          <span class="gt-wp-flow-tag" style="background:#7f8c8d;margin-left:4px">S 特定项目</span>
        </div>
        <div class="gt-wp-guide-list">
          <div
            v-for="g in auditCycleGuide" :key="g.cycle"
            class="gt-wp-guide-row"
            @click="onGuideClick(g.cycle)"
          >
            <span class="gt-wp-guide-badge" :style="{ background: g.color }">{{ g.cycle }}</span>
            <span class="gt-wp-guide-name">{{ g.name }}</span>
            <span class="gt-wp-guide-count">{{ g.count }} 个底稿</span>
            <span class="gt-wp-guide-arrow">›</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-else-if="loading" class="gt-wp-empty-full">
      <el-icon class="is-loading" style="font-size: 28px; color: var(--gt-color-primary)"><Loading /></el-icon>
      <div style="margin-top: 12px; font-size: 14px; color: #999">加载中...</div>
    </div>

    <!-- 有数据时：左右分栏 -->
    <div v-else class="gt-wp-body">
      <!-- 左侧索引树 -->
      <div class="gt-wp-tree-panel">
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          highlight-current
          default-expand-all
          show-checkbox
          @check-change="onCheckChange"
          @node-click="onNodeClick"
          ref="treeRef"
        >
          <template #default="{ data }">
            <div class="gt-wp-tree-node">
              <span class="gt-wp-tree-node-label">{{ data.label }}</span>
              <GtStatusTag v-if="data.status" :status-map="WP_STATUS" status-map-name="WP_STATUS" :value="data.status" class="gt-wp-tree-node-tag" />
            </div>
          </template>
        </el-tree>
      </div>

      <!-- 右侧详情面板 -->
      <div class="gt-wp-detail-panel">
        <template v-if="selectedWp">
          <div class="gt-wp-detail-card">
            <h3 class="gt-wp-detail-title">{{ selectedWp.wp_code }} {{ selectedWp.wp_name }}</h3>
            <el-descriptions :column="2" border size="default">
              <el-descriptions-item label="底稿编号">{{ selectedWp.wp_code }}</el-descriptions-item>
              <el-descriptions-item label="底稿名称">{{ selectedWp.wp_name }}</el-descriptions-item>
              <el-descriptions-item label="审计循环">{{ selectedWp.audit_cycle || '-' }}</el-descriptions-item>
              <el-descriptions-item label="编制状态">
                <el-tag size="small" :type="(dictStore.type('wp_status', selectedWp.status)) || undefined">{{ dictStore.label('wp_status', selectedWp.status) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="复核状态">
                <el-tag size="small" :type="(dictStore.type('wp_review_status', selectedWp.review_status)) || undefined">{{ dictStore.label('wp_review_status', selectedWp.review_status) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="编制人">{{ resolveUserName(selectedWp.assigned_to) }}</el-descriptions-item>
              <el-descriptions-item label="复核人">{{ resolveUserName(selectedWp.reviewer) }}</el-descriptions-item>
              <el-descriptions-item label="文件版本">v{{ selectedWp.file_version || 1 }}</el-descriptions-item>
              <el-descriptions-item label="最后解析">{{ selectedWp.last_parsed_at?.slice(0, 19) || '-' }}</el-descriptions-item>
            </el-descriptions>

            <!-- 操作按钮：在线优先+离线兜底双模式 -->
            <div class="gt-wp-detail-actions">
              <el-button-group>
                <el-button type="primary" @click="onOnlineEdit">
                  <el-icon style="margin-right:4px"><Monitor /></el-icon>
                  在线编辑
                </el-button>
                <el-button @click="onDownload">
                  <el-icon style="margin-right:4px"><Download /></el-icon>下载编辑
                </el-button>
              </el-button-group>
              <el-button @click="onUpload">上传</el-button>
              <el-button type="warning" @click="onQCCheck" :loading="qcLoading">自检</el-button>
              <el-tooltip :disabled="!hasBlocking" :content="blockingReasons.join('；')" placement="top">
                <el-button type="success" @click="onSubmitReview" :disabled="hasBlocking || submitLoading" :loading="submitLoading">提交复核</el-button>
              </el-tooltip>
            </div>

            <!-- Phase 14: 门禁阻断面板 -->
            <GateBlockPanel
              :state="gateState"
              :hit-rules="gateHitRules"
              :trace-id="gateTraceId"
              @jump="handleGateJump"
            />

            <!-- Phase 14: SoD 冲突弹窗 -->
            <SoDConflictDialog
              v-model="showSodDialog"
              :conflict-type="sodConflictType"
              :policy-code="sodPolicyCode"
              :trace-id="sodTraceId"
            />

            <!-- QC 结果摘要 -->
            <div v-if="qcResult" class="gt-wp-qc-summary-inline">
              <el-tag :type="qcResult.passed ? 'success' : 'danger'" size="small">
                {{ qcResult.passed ? '自检通过' : '存在问题' }}
              </el-tag>
              <span class="gt-wp-qc-counts">
                阻断 {{ qcResult.blocking_count }} / 警告 {{ qcResult.warning_count }} / 提示 {{ qcResult.info_count }}
              </span>
            </div>

            <!-- 精细化审计检查结果 -->
            <div v-if="fineCheckResults.length" class="gt-wp-fine-checks" style="margin-top: 12px">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                <span style="font-size:13px;font-weight:600;color:#333">审计检查</span>
                <el-tag size="small" :type="fineChecksPassed ? 'success' : 'warning'">
                  {{ fineChecksPassedCount }}/{{ fineCheckResults.length }} 通过
                </el-tag>
                <el-button size="small" text @click="loadFineChecks" :loading="fineChecksLoading">刷新</el-button>
              </div>
              <div v-for="chk in fineCheckResults" :key="chk.code" class="gt-fine-check-item"
                :class="{ 'gt-fine-check-pass': chk.passed === true, 'gt-fine-check-fail': chk.passed === false, 'gt-fine-check-pending': chk.passed === null }">
                <span class="gt-fine-check-code">{{ chk.code }}</span>
                <span class="gt-fine-check-desc">{{ chk.description }}</span>
                <span v-if="chk.passed === true" class="gt-fine-check-status">✓</span>
                <span v-else-if="chk.passed === false" class="gt-fine-check-status" style="color:#e6a23c">
                  ✗ {{ chk.message }}
                  <el-button size="small" text type="primary" style="margin-left:4px;font-size:11px" @click="onCheckJump(chk)">定位</el-button>
                </span>
                <span v-else class="gt-fine-check-status" style="color:#999">待验证</span>
              </div>
            </div>

            <!-- 复核人操作区：仅在底稿处于待复核状态时显示 -->
            <div v-if="isReviewable" class="gt-wp-reviewer-actions" style="margin-top: 16px">
              <h4 style="margin: 0 0 8px; font-size: 14px; color: var(--gt-color-text)">复核操作</h4>

              <!-- TSJ复核提示词清单 -->
              <div v-if="tsjReviewData" class="gt-tsj-review-panel" style="margin-bottom: 12px">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                  <span style="font-size:12px;font-weight:600;color:#4b2d77">📋 复核要点（{{ tsjReviewData.account_name }}）</span>
                  <el-button size="small" text @click="showTsjDetail = !showTsjDetail">{{ showTsjDetail ? '收起' : '展开' }}</el-button>
                </div>
                <!-- 风险领域 -->
                <div v-if="tsjReviewData.risk_areas?.length" style="margin-bottom:6px">
                  <div v-for="(area, i) in tsjReviewData.risk_areas.slice(0, showTsjDetail ? 99 : 3)" :key="i"
                    style="font-size:11px;color:#666;padding:2px 0">
                    <el-tag :type="area.includes('高风险') ? 'danger' : area.includes('中风险') ? 'warning' : 'info'" size="small" style="margin-right:4px">
                      {{ area.includes('高风险') ? '高' : area.includes('中风险') ? '中' : '低' }}
                    </el-tag>
                    {{ area }}
                  </div>
                </div>
                <!-- 复核清单 -->
                <div v-if="showTsjDetail && tsjReviewData.checklist?.length" style="margin-top:8px">
                  <div style="font-size:11px;font-weight:600;color:#333;margin-bottom:4px">复核清单：</div>
                  <div v-for="(item, i) in tsjReviewData.checklist" :key="i"
                    style="font-size:11px;color:#555;padding:1px 0;display:flex;align-items:flex-start;gap:4px">
                    <el-checkbox size="small" style="flex-shrink:0" />
                    <span>{{ item }}</span>
                  </div>
                </div>
              </div>

              <div style="display: flex; gap: 8px; flex-wrap: wrap">
                <el-button type="success" @click="onReviewPass">
                  {{ selectedWp?.review_status === 'pending_level2' ? '二级复核通过' : '一级复核通过' }}
                </el-button>
                <el-button type="warning" @click="onRejectClick">退回修改</el-button>
              </div>
            </div>

            <!-- 退回底稿弹窗 -->
            <el-dialog v-model="showRejectDialog" title="退回底稿" width="450px" append-to-body>
              <el-input v-model="rejectReason" type="textarea" :rows="3"
                placeholder="请填写退回原因（必填）" />
              <template #footer>
                <el-button @click="showRejectDialog = false">取消</el-button>
                <el-button type="warning" @click="onConfirmReject" :disabled="!rejectReason.trim()">
                  确认退回
                </el-button>
              </template>
            </el-dialog>

            <!-- 复核批注面板 -->
            <div class="gt-wp-review-section" style="margin-top: 16px">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
                <h4 style="margin: 0; font-size: 14px; color: var(--gt-color-text)">
                  复核意见
                  <el-badge v-if="unresolvedCount > 0" :value="unresolvedCount" type="danger" style="margin-left: 8px" />
                </h4>
                <div style="display:flex;gap:6px">
                  <el-button size="small" @click="goToConversation" title="发起复核对话（支持多轮讨论）">💬 对话</el-button>
                  <el-button size="small" type="primary" @click="showAddAnnotation = true">新增意见</el-button>
                </div>
              </div>
              <!-- 意见筛选 -->
              <div v-if="annotations.length > 3" style="margin-bottom:6px">
                <el-radio-group v-model="annotationFilter" size="small">
                  <el-radio-button value="">全部 ({{ annotations.length }})</el-radio-button>
                  <el-radio-button value="open">待处理 ({{ annotations.filter(a => a.status === 'open').length }})</el-radio-button>
                  <el-radio-button value="replied">已回复 ({{ annotations.filter(a => a.status === 'replied').length }})</el-radio-button>
                  <el-radio-button value="resolved">已解决 ({{ annotations.filter(a => a.status === 'resolved').length }})</el-radio-button>
                </el-radio-group>
              </div>
              <el-table v-if="filteredAnnotations.length" :data="filteredAnnotations" size="small" stripe max-height="250"
                :row-class-name="annotationRowClass">
                <el-table-column prop="content" label="内容" min-width="200">
                  <template #default="{ row }">
                    <div>
                      <span style="font-size:12px">{{ row.content }}</span>
                      <div v-if="row.reply_content" style="margin-top:4px;padding:4px 8px;background:#f0f9eb;border-radius:4px;font-size:11px;color:#67c23a">
                        ↳ 回复：{{ row.reply_content }}
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="priority" label="优先级" width="60">
                  <template #default="{ row }">
                    <el-tag :type="row.priority === 'high' ? 'danger' : row.priority === 'medium' ? 'warning' : 'info'" size="small">
                      {{ row.priority === 'high' ? '高' : row.priority === 'medium' ? '中' : '低' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="70">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'resolved' ? 'success' : row.status === 'replied' ? 'warning' : 'danger'" size="small">
                      {{ row.status === 'resolved' ? '已解决' : row.status === 'replied' ? '已回复' : '待处理' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="时间" width="70">
                  <template #default="{ row }">
                    <span style="font-size:10px;color:#999">{{ row.created_at?.slice(5, 16) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="120">
                  <template #default="{ row }">
                    <el-button v-if="row.status === 'open'" size="small" text type="primary" @click="replyAnnotation(row)">回复</el-button>
                    <el-button v-if="row.status !== 'resolved'" size="small" text type="success" @click="resolveAnnotation(row.id)">解决</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="暂无复核意见" :image-size="40" />
            </div>

            <!-- 新增意见弹窗 -->
            <el-dialog append-to-body v-model="showAddAnnotation" title="新增复核意见" width="400px">
              <el-form label-width="60px">
                <el-form-item label="内容">
                  <el-input v-model="newAnnotation.content" type="textarea" :rows="3" placeholder="输入复核意见" />
                </el-form-item>
                <el-form-item label="优先级">
                  <el-radio-group v-model="newAnnotation.priority">
                    <el-radio value="high">高</el-radio>
                    <el-radio value="medium">中</el-radio>
                    <el-radio value="low">低</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-form>
              <template #footer>
                <el-button @click="showAddAnnotation = false">取消</el-button>
                <el-button type="primary" @click="submitAnnotation" :disabled="!newAnnotation.content">提交</el-button>
              </template>
            </el-dialog>
          </div>
        </template>
        <el-empty v-else description="请从左侧选择底稿" :image-size="100" />
      </div>
    </div>

    <!-- 上传弹窗（两步：上传文件 → 确认识别数据） -->
    <el-dialog append-to-body v-model="uploadDialogVisible" :title="uploadStep === 1 ? '上传底稿（步骤 1/2）' : '确认识别数据（步骤 2/2）'" width="560px" :close-on-click-modal="false">
      <!-- 步骤条 -->
      <el-steps :active="uploadStep - 1" finish-status="success" style="margin-bottom: 20px">
        <el-step title="上传文件" />
        <el-step title="确认识别数据" />
      </el-steps>

      <!-- 步骤1：上传文件 -->
      <template v-if="uploadStep === 1">
        <el-alert v-if="uploadConflict" type="warning" :closable="false" show-icon style="margin-bottom: 16px">
          版本冲突：服务器版本 v{{ uploadConflict.server_version }}，您的版本 v{{ uploadConflict.uploaded_version }}
        </el-alert>
        <el-upload
          ref="uploadRef"
          drag
          :auto-upload="false"
          :limit="1"
          accept=".xlsx,.xls"
          :on-change="onUploadFileChange"
        >
          <el-icon style="font-size: 40px; color: var(--gt-color-primary)"><Upload /></el-icon>
          <div>拖拽文件到此处，或点击选择</div>
        </el-upload>
      </template>

      <!-- 步骤2：确认识别数据 -->
      <template v-else-if="uploadStep === 2">
        <el-alert v-if="parseLoading" type="info" :closable="false" show-icon style="margin-bottom: 16px">
          正在解析底稿数据，请稍候...
        </el-alert>
        <template v-if="!parseLoading && parsedPreview">
          <el-descriptions title="系统识别结果" :column="2" border size="default" style="margin-bottom: 16px">
            <el-descriptions-item label="底稿名称">{{ parsedPreview.wp_name || selectedWp?.wp_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="审计年度">{{ parsedPreview.year || '-' }}</el-descriptions-item>
            <el-descriptions-item label="审定数">
              <span :class="parsedPreview.audited_amount != null ? 'gt-parsed-value' : 'gt-parsed-empty'">
                {{ parsedPreview.audited_amount != null ? fmtParsed(parsedPreview.audited_amount) : '未识别' }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="未审数">
              <span :class="parsedPreview.unadjusted_amount != null ? 'gt-parsed-value' : 'gt-parsed-empty'">
                {{ parsedPreview.unadjusted_amount != null ? fmtParsed(parsedPreview.unadjusted_amount) : '未识别' }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item v-if="parsedPreview.audited_amount != null && parsedPreview.unadjusted_amount != null" label="差异">
              <span :class="Math.abs(parsedPreview.audited_amount - parsedPreview.unadjusted_amount) > 0 ? 'gt-parsed-diff' : 'gt-parsed-value'">
                {{ fmtParsed(parsedPreview.audited_amount - parsedPreview.unadjusted_amount) }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item v-if="parsedPreview.sheet_count" label="工作表数">{{ parsedPreview.sheet_count }}</el-descriptions-item>
          </el-descriptions>
          <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 8px">
            <template #title>请确认以上识别数据是否正确，确认后将写入系统</template>
          </el-alert>
        </template>
        <el-empty v-else-if="!parseLoading" description="解析未返回数据，仍可确认写入" :image-size="60" />
      </template>

      <template #footer>
        <el-button @click="onUploadCancel" :disabled="uploadLoading || parseLoading">取消</el-button>
        <!-- 步骤1 按钮 -->
        <template v-if="uploadStep === 1">
          <el-button v-if="uploadConflict" type="warning" @click="doUploadStep1(true)" :loading="uploadLoading">
            强制覆盖
          </el-button>
          <el-button type="primary" @click="doUploadStep1(false)" :loading="uploadLoading" :disabled="!uploadFile">
            上传并解析
          </el-button>
        </template>
        <!-- 步骤2 按钮 -->
        <template v-else-if="uploadStep === 2">
          <el-button @click="uploadStep = 1" :disabled="parseLoading">← 重新上传</el-button>
          <el-button type="primary" @click="doConfirmParsed" :loading="parseLoading">
            确认写入
          </el-button>
        </template>
      </template>
    </el-dialog>

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showWpImport"
      import-type="workpaper"
      :project-id="projectId"
      :year="Number(route.query.year) || new Date().getFullYear()"
      @imported="onWpImported"
    />

    <!-- 批量委派弹窗 -->
    <BatchAssignDialog
      v-model="showBatchAssign"
      :project-id="projectId"
      :wp-ids="selectedWpIds"
      :wp-list="batchAssignWpList"
      @assigned="onBatchAssigned"
    />

    <!-- 看板分配弹窗 -->
    <el-dialog
      v-model="showAssignDialog"
      title="分配底稿"
      width="420px"
      append-to-body
    >
      <div v-if="assigningItem" style="margin-bottom: 12px; color: #606266; font-size: 13px;">
        底稿：<strong>{{ assigningItem.wp_code }} {{ assigningItem.wp_name }}</strong>
      </div>
      <el-form :model="assignForm" label-width="70px">
        <el-form-item label="编制人">
          <el-select
            v-model="assignForm.assigned_to"
            placeholder="请选择编制人"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.username"
              :label="`${u.full_name || u.username} (${u.username})`"
              :value="u.username"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="复核人">
          <el-select
            v-model="assignForm.reviewer"
            placeholder="请选择复核人"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.username"
              :label="`${u.full_name || u.username} (${u.username})`"
              :value="u.username"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAssignDialog = false">取消</el-button>
        <el-button type="primary" :loading="assignLoading" @click="onConfirmAssign">确认分配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { Download, Monitor, Upload, Loading } from '@element-plus/icons-vue'
import GateBlockPanel from '@/components/gate/GateBlockPanel.vue'
import SoDConflictDialog from '@/components/gate/SoDConflictDialog.vue'
import WorkpaperKanban from '@/components/workpaper/WorkpaperKanban.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import BatchAssignDialog from '@/components/assignment/BatchAssignDialog.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import { WP_STATUS, WP_REVIEW_STATUS } from '@/utils/statusMaps'
import { useDictStore } from '@/stores/dict'
import {
  listWorkpaperAnnotations, createAnnotation, updateAnnotation,
  getFeatureMaturity, submitWorkpaperReview,
  checkUnconfirmedAI,
  listUsers,
} from '@/services/commonApi'
import {
  downloadWorkpaper,
  downloadWorkpaperPack,
  uploadWorkpaperFile,
  listWorkpapers, runQCCheck, getQCResults,
  getWpIndex, updateReviewStatus, parseWorkpaper,
  assignWorkpaper,
  type WorkpaperDetail, type WpIndexItem, type QCResult,
} from '@/services/workpaperApi'

const route = useRoute()
const router = useRouter()
const dictStore = useDictStore()
const projectId = computed(() => route.params.projectId as string)

const loading = ref(false)
const showWpImport = ref(false)
const qcLoading = ref(false)
const downloadLoading = ref(false)
const submitLoading = ref(false)

// Phase 14: 门禁阻断面板状态
const gateState = ref<'normal' | 'evaluating' | 'blocked' | 'warned' | 'error'>('normal')
const gateHitRules = ref<any[]>([])
const gateTraceId = ref('')

// Phase 14: SoD 冲突弹窗
const showSodDialog = ref(false)
const sodConflictType = ref('')
const sodPolicyCode = ref('')
const sodTraceId = ref('')
const searchKeyword = ref('')
const viewMode = ref('list')
let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearchDebounce() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    fetchData()
  }, 300)
}
const uploadLoading = ref(false)
const parseLoading = ref(false)
const wpList = ref<WorkpaperDetail[]>([])
const wpIndex = ref<WpIndexItem[]>([])
const selectedWp = ref<WorkpaperDetail | null>(null)
const selectedWpIds = ref<string[]>([])
const qcResult = ref<QCResult | null>(null)
const treeRef = ref<any>(null)
const kanbanRef = ref<any>(null)

// 看板分配弹窗
const showAssignDialog = ref(false)
const assigningItem = ref<any>(null)
const assignForm = ref<{ assigned_to: string | null; reviewer: string | null }>({ assigned_to: null, reviewer: null })
const assignLoading = ref(false)
const userOptions = ref<any[]>([])

// 批量委派弹窗
const showBatchAssign = ref(false)
const batchAssignWpList = computed(() => {
  // 合并 wpList 和 wpIndex 信息，提供给 BatchAssignDialog
  return wpList.value.map((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    return {
      id: w.id,
      wp_code: w.wp_code || idx?.wp_code || '',
      wp_name: w.wp_name || idx?.wp_name || '',
      audit_cycle: w.audit_cycle || idx?.audit_cycle || '',
    }
  })
})

function onBatchAssigned(_result: { updated: number; notifications_sent: number; message: string }) {
  // 刷新数据
  fetchData()
}

// 任务 6.1：用户名映射
const userNameMap = ref<Map<string, string>>(new Map())

function resolveUserName(uuid: string | null | undefined): string {
  if (!uuid) return '未分配'
  return userNameMap.value.get(uuid) ?? '未知用户'
}

// 任务 7.1：进度计算
const COMPLETED_STATUSES = new Set(['review_passed', 'archived'])

const totalProgress = computed(() => {
  const total = wpList.value.length
  const completed = wpList.value.filter((w: WorkpaperDetail) => COMPLETED_STATUSES.has(w.status)).length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, percent }
})

const filteredWpList = computed<WorkpaperDetail[]>(() => {
  return wpList.value.filter((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    if (filterCycle.value && !idx?.wp_code?.startsWith(filterCycle.value)) return false
    if (filterStatus.value && w.status !== filterStatus.value) return false
    if (filterAssignee.value && w.assigned_to !== filterAssignee.value) return false
    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      if (!w.wp_code?.toLowerCase().includes(kw) && !w.wp_name?.toLowerCase().includes(kw)) return false
    }
    return true
  })
})

const filteredProgress = computed(() => {
  const total = filteredWpList.value.length
  const completed = filteredWpList.value.filter((w: WorkpaperDetail) => COMPLETED_STATUSES.has(w.status)).length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, percent }
})

const hasFilter = computed(() => {
  return !!(filterCycle.value || filterStatus.value || filterAssignee.value || searchKeyword.value)
})

// 精细化审计检查
const fineCheckResults = ref<any[]>([])
const fineChecksLoading = ref(false)
const fineChecksPassed = computed(() => fineCheckResults.value.length > 0 && fineCheckResults.value.every(c => c.passed !== false))
const fineChecksPassedCount = computed(() => fineCheckResults.value.filter(c => c.passed === true).length)

// TSJ复核提示词
const tsjReviewData = ref<any>(null)
const showTsjDetail = ref(false)

// Upload dialog
const uploadDialogVisible = ref(false)
const uploadFile = ref<File | null>(null)
const uploadConflict = ref<{ server_version: number; uploaded_version: number } | null>(null)
const uploadRef = ref<any>(null)
// 两步上传状态
const uploadStep = ref(1)
const parsedPreview = ref<any>(null)
const pendingWpId = ref('')
const pendingNewVersion = ref(1)

// Feature flags & Univer 在线编辑（纯前端，始终可用）
const onlineEditAvailable = ref(true)
const onlineEditEnabled = ref(true)
const onlineEditMaturity = ref('production')
const _onlineEditReady = computed(() => true)
const _onlineEditNotice = computed(() => '')

// Review annotations
const annotations = ref<any[]>([])
const unresolvedCount = computed(() => annotations.value.filter((a: any) => a.status !== 'resolved').length)
const annotationFilter = ref('')
const filteredAnnotations = computed(() => {
  if (!annotationFilter.value) return annotations.value
  return annotations.value.filter((a: any) => a.status === annotationFilter.value)
})

function annotationRowClass({ row }: { row: any }) {
  if (row.status === 'open' && row.priority === 'high') return 'gt-ann-row-urgent'
  return ''
}

function goToConversation() {
  if (!selectedWp.value) return
  router.push({
    path: `/projects/${projectId.value}/review-conversations`,
    query: { wp_id: selectedWp.value.id, wp_code: selectedWp.value.wp_code },
  })
}
const unconfirmedAiCount = ref(0)
const showAddAnnotation = ref(false)
const newAnnotation = ref({ content: '', priority: 'medium' })

// Reject dialog state
const showRejectDialog = ref(false)
const rejectReason = ref('')
const rejectingWpId = ref('')

// Whether the selected workpaper is in a reviewable state (pending_level1 or pending_level2)
const isReviewable = computed(() => {
  const rs = selectedWp.value?.review_status
  return rs === 'pending_level1' || rs === 'level1_in_progress'
    || rs === 'pending_level2' || rs === 'level2_in_progress'
})

// Filters
const filterCycle = ref('')
const filterStatus = ref('')
const filterAssignee = ref('')

const cycleOptions = [
  { value: 'B', label: 'B类 穿行测试' },
  { value: 'C', label: 'C类 控制测试' },
  { value: 'D', label: 'D类 货币资金' },
  { value: 'E', label: 'E类 应收账款' },
  { value: 'F', label: 'F类 存货' },
  { value: 'G', label: 'G类 固定资产' },
  { value: 'H', label: 'H类 无形资产' },
  { value: 'I', label: 'I类 投资' },
  { value: 'J', label: 'J类 负债' },
  { value: 'K', label: 'K类 收入' },
  { value: 'L', label: 'L类 成本费用' },
  { value: 'M', label: 'M类 权益' },
  { value: 'N', label: 'N类 其他' },
]

const statusOptions = [
  { value: 'not_started', label: '未开始' },
  { value: 'in_progress', label: '编制中' },
  { value: 'draft_complete', label: '初稿完成' },
  { value: 'review_passed', label: '复核通过' },
  { value: 'archived', label: '已归档' },
]

const hasBlocking = computed(() => {
  // 4 项硬门槛：任一不满足则禁止提交复核
  if (!selectedWp.value) return true
  // 0. 编制状态必须为 edit_complete
  if (selectedWp.value.status !== 'edit_complete') return true
  // 1. reviewer 未分配
  if (!selectedWp.value.reviewer) return true
  // 2. 阻断级 QC 未通过
  if (!qcResult.value) return true
  if (qcResult.value && (qcResult.value.blocking_count ?? 0) > 0) return true
  // 3. 存在未解决复核意见
  if (unresolvedCount.value > 0) return true
  // 4. 存在未确认 AI 内容
  if (unconfirmedAiCount.value > 0) return true
  return false
})

const blockingReasons = computed(() => {
  const reasons: string[] = []
  if (!selectedWp.value) return reasons
  if (selectedWp.value.status !== 'edit_complete') reasons.push('底稿尚未完成编制')
  if (!selectedWp.value.reviewer) reasons.push('复核人未分配')
  if (!qcResult.value) reasons.push('未执行质量自检')
  if (qcResult.value && (qcResult.value.blocking_count ?? 0) > 0) reasons.push('存在阻断级 QC 问题')
  if (unresolvedCount.value > 0) reasons.push(`${unresolvedCount.value} 条未解决复核意见`)
  if (unconfirmedAiCount.value > 0) reasons.push(`${unconfirmedAiCount.value} 项未确认的 AI 生成内容`)
  return reasons
})

interface TreeNode {
  id: string
  label: string
  status?: string
  assigned_to?: string | null
  wpId?: string
  children?: TreeNode[]
}

const treeData = computed<TreeNode[]>(() => {
  const groups: Record<string, TreeNode> = {}
  const CYCLE_GROUPS: Record<string, string> = {
    B: 'B类 穿行测试', C: 'C类 控制测试',
  }

  const items = wpIndex.value.filter((w: WpIndexItem) => {
    if (filterCycle.value && !w.wp_code?.startsWith(filterCycle.value)) return false
    if (filterStatus.value && w.status !== filterStatus.value) return false
    if (filterAssignee.value && w.assigned_to !== filterAssignee.value) return false
    return true
  })

  for (const wp of items) {
    const prefix = wp.wp_code?.charAt(0) || '?'
    const groupKey = prefix
    const groupLabel = CYCLE_GROUPS[prefix] || `${prefix}类 实质性程序`
    const matchedWorkpaper = wpList.value.find((item: WorkpaperDetail) => item.wp_index_id === wp.id)

    if (!groups[groupKey]) {
      groups[groupKey] = { id: `group-${groupKey}`, label: groupLabel, children: [] }
    }
    groups[groupKey].children!.push({
      id: matchedWorkpaper?.id || wp.id,
      label: `${wp.wp_code} ${wp.wp_name}`,
      status: matchedWorkpaper?.status || wp.status || undefined,
      assigned_to: matchedWorkpaper?.assigned_to ?? wp.assigned_to,
      wpId: matchedWorkpaper?.id || wp.id,
    })
  }

  return Object.values(groups).sort((a, b) => a.label.localeCompare(b.label))
})



function onKanbanSelect(item: any) {
  if (item.wp_id) {
    // 切换到列表视图并自动选中对应底稿
    viewMode.value = 'list'
    // 等待列表视图渲染后再选中节点
    setTimeout(() => selectWorkpaperById(item.wp_id), 100)
  }
}

async function onKanbanAssign(item: any) {
  assigningItem.value = item
  assignForm.value = {
    assigned_to: item.assigned_to || null,
    reviewer: item.reviewer || null,
  }
  showAssignDialog.value = true
  // 加载用户列表（如果尚未加载）
  if (!userOptions.value.length) {
    try {
      userOptions.value = await listUsers()
    } catch {
      ElMessage.warning('加载用户列表失败')
    }
  }
}

async function onConfirmAssign() {
  if (!assigningItem.value?.wp_id) {
    ElMessage.warning('该底稿尚未生成，无法分配')
    return
  }
  assignLoading.value = true
  try {
    await assignWorkpaper(projectId.value, assigningItem.value.wp_id, {
      assigned_to: assignForm.value.assigned_to || null,
      reviewer: assignForm.value.reviewer || null,
    })
    ElMessage.success('分配成功')
    showAssignDialog.value = false
    // 刷新看板数据
    kanbanRef.value?.refresh()
  } catch {
    ElMessage.error('分配失败，请重试')
  } finally {
    assignLoading.value = false
  }
}

function goToWorkbench() {
  router.push(`/projects/${projectId.value}/workpaper-bench`)
}

function _goToTemplates() {
  router.push(`/projects/${projectId.value}/templates`)
}

// ── 审计程序指南数据（右栏） ──
const _guideExpanded = ref('')

const auditCycleGuide = [
  { cycle: 'B', name: '初步业务活动/风险评估', color: '#7c5cbf', count: 56 },
  { cycle: 'C', name: '控制测试', color: '#6a4fa0', count: 50 },
  { cycle: 'D', name: '收入循环', color: '#e6553a', count: 17 },
  { cycle: 'E', name: '货币资金循环', color: '#d4a017', count: 5 },
  { cycle: 'F', name: '存货循环', color: '#2e86c1', count: 15 },
  { cycle: 'G', name: '投资循环', color: '#1a8a5c', count: 15 },
  { cycle: 'H', name: '固定资产循环', color: '#7d6608', count: 11 },
  { cycle: 'I', name: '无形资产循环', color: '#5b2c6f', count: 6 },
  { cycle: 'J', name: '职工薪酬循环', color: '#c0392b', count: 3 },
  { cycle: 'K', name: '管理循环', color: '#2980b9', count: 14 },
  { cycle: 'L', name: '债务循环', color: '#117a65', count: 9 },
  { cycle: 'M', name: '权益循环', color: '#4b2d77', count: 10 },
  { cycle: 'N', name: '税金循环', color: '#6c3483', count: 5 },
  { cycle: 'A', name: '完成阶段', color: '#1a8a5c', count: 59 },
  { cycle: 'S', name: '特定项目程序', color: '#7f8c8d', count: 87 },
]

function onGuideClick(cycle: string) {
  // 跳转到底稿工作台，按循环筛选
  router.push({ path: `/projects/${projectId.value}/workpaper-bench`, query: { cycle } })
}

function onWpImported() {
  showWpImport.value = false
  fetchData()
}

async function fetchData() {
  loading.value = true
  try {
    const [wps, idx] = await Promise.all([
      listWorkpapers(projectId.value, {
        audit_cycle: filterCycle.value || undefined,
        status: filterStatus.value || undefined,
        assigned_to: filterAssignee.value || undefined,
      }),
      getWpIndex(projectId.value),
    ])
    wpList.value = wps
    wpIndex.value = idx.map((item) => {
      const matchedWorkpaper = wps.find((wp) => wp.wp_index_id === item.id)
      return {
        ...item,
        assigned_to: matchedWorkpaper?.assigned_to ?? item.assigned_to,
        reviewer: matchedWorkpaper?.reviewer ?? item.reviewer,
      }
    })
  } finally {
    loading.value = false
  }
}

async function loadUnconfirmedAi() {
  if (!selectedWp.value) {
    unconfirmedAiCount.value = 0
    return
  }
  try {
    const result = await checkUnconfirmedAI(projectId.value, selectedWp.value.id)
    unconfirmedAiCount.value = Number(result?.unconfirmed_count || 0)
  } catch {
    unconfirmedAiCount.value = 0
  }
}

async function loadFineChecks() {
  if (!selectedWp.value) {
    fineCheckResults.value = []
    return
  }
  fineChecksLoading.value = true
  try {
    const { fineExtractWorkpaper } = await import('@/services/commonApi')
    const result = await fineExtractWorkpaper(projectId.value, selectedWp.value.id)
    fineCheckResults.value = result?.checks || []
  } catch {
    fineCheckResults.value = []
  } finally {
    fineChecksLoading.value = false
  }
}

function onCheckJump(chk: any) {
  // 根据检查类型跳转到对应位置
  const type = chk.type || ''
  if (type === 'balance' && chk.code?.includes('CHK-02')) {
    // 跳转到报表
    router.push({ path: `/projects/${projectId.value}/reports`, query: { highlight: 'BS-002' } })
  } else if (type === 'cross_ref' && chk.code?.includes('CHK-03')) {
    // 跳转到现金明细表（在线编辑）
    if (selectedWp.value) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: selectedWp.value.id } })
    }
  } else if (type === 'cross_ref' && chk.code?.includes('CHK-04')) {
    // 跳转到银行明细表
    if (selectedWp.value) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: selectedWp.value.id } })
    }
  } else if (type === 'balance' && chk.code?.includes('CHK-01')) {
    // 跳转到试算表
    router.push({ path: `/projects/${projectId.value}/trial-balance` })
  } else {
    // 默认跳转到底稿编辑
    if (selectedWp.value) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: selectedWp.value.id } })
    }
  }
}

async function loadTsjReviewPrompts() {
  if (!selectedWp.value) {
    tsjReviewData.value = null
    return
  }
  try {
    const wpName = selectedWp.value.wp_name || ''
    // 从底稿名称提取科目名（如"货币资金审定表"→"货币资金"）
    const accountName = wpName.replace(/审定表|明细表|程序表|汇总表|盘点表|调节表|核对表/g, '').trim()
    if (!accountName) { tsjReviewData.value = null; return }

    const { data } = await import('@/utils/http').then(m =>
      m.default.get(`/api/projects/${projectId.value}/wp-mapping/tsj/${encodeURIComponent(accountName)}`, {
        validateStatus: (s: number) => s < 600,
      })
    )
    if (data?.tips?.length || data?.checklist?.length || data?.risk_areas?.length) {
      tsjReviewData.value = data
    } else {
      tsjReviewData.value = null
    }
  } catch {
    tsjReviewData.value = null
  }
}

async function selectWorkpaperById(wpId: string) {
  const wp = wpList.value.find((w: WorkpaperDetail) => w.wp_index_id === wpId || w.id === wpId)
  if (wp) {
    selectedWp.value = wp
  } else {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === wpId)
    if (idx) {
      selectedWp.value = {
        id: idx.id, project_id: projectId.value, wp_index_id: idx.id,
        file_path: null, source_type: 'template', status: idx.status || 'not_started',
        assigned_to: idx.assigned_to, reviewer: idx.reviewer,
        file_version: 1, last_parsed_at: null, created_at: null, updated_at: null,
        wp_code: idx.wp_code, wp_name: idx.wp_name, audit_cycle: idx.audit_cycle || undefined,
      }
    }
  }
  // 自动展开并滚动到选中节点
  if (treeRef.value && wpId) {
    try {
      treeRef.value.setCurrentKey(wpId)
      // 滚动到可视区域
      const el = document.querySelector('.el-tree-node.is-current')
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } catch { /* tree node may not exist */ }
  }
  qcResult.value = null
  annotations.value = []
  unconfirmedAiCount.value = 0
  if (selectedWp.value) {
    try { qcResult.value = await getQCResults(projectId.value, selectedWp.value.id) } catch { /* no QC yet */ }
    await loadAnnotations()
    await loadUnconfirmedAi()
    loadFineChecks()  // 非阻塞加载审计检查
    loadTsjReviewPrompts()  // 非阻塞加载TSJ复核提示词
  }
}

async function onNodeClick(data: TreeNode) {
  if (!data.wpId) return
  await selectWorkpaperById(data.wpId)
}

function onOnlineEdit() {
  if (!selectedWp.value) return
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: projectId.value, wpId: selectedWp.value.id },
  })
}

async function onDownload() {
  if (!selectedWp.value) return
  try {
    await downloadWorkpaper(projectId.value, selectedWp.value.id)
  } catch {
    ElMessage.error('下载失败')
  }
}

function onUpload() {
  if (!selectedWp.value) return
  uploadFile.value = null
  uploadConflict.value = null
  uploadStep.value = 1
  parsedPreview.value = null
  pendingWpId.value = ''
  uploadDialogVisible.value = true
}

function onUploadFileChange(file: any) {
  uploadFile.value = file.raw
}

/** 格式化解析预览中的金额 */
function fmtParsed(v: number | null | undefined): string {
  if (v == null) return '-'
  return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)
}

/** 取消上传弹窗 */
function onUploadCancel() {
  uploadDialogVisible.value = false
  uploadStep.value = 1
  parsedPreview.value = null
  pendingWpId.value = ''
}

/** 步骤1：上传文件并触发解析预览（dry_run=true，不写入 parsed_data） */
async function doUploadStep1(forceOverwrite: boolean) {
  if (!selectedWp.value || !uploadFile.value) return
  uploadLoading.value = true
  try {
    const version = selectedWp.value.file_version || 1
    const result = await uploadWorkpaperFile(
      projectId.value,
      selectedWp.value.id,
      uploadFile.value,
      version,
      forceOverwrite,
    )
    uploadConflict.value = null
    uploadRef.value?.clearFiles?.()
    pendingWpId.value = selectedWp.value.id
    pendingNewVersion.value = result?.new_version || version + 1

    // 触发 dry_run 解析，仅获取预览数据，不写入 parsed_data
    parseLoading.value = true
    uploadStep.value = 2
    try {
      const parseResult = await parseWorkpaper(projectId.value, pendingWpId.value, true)
      // 后端返回 parsed_data 字段（完整预览）或直接返回顶层字段
      parsedPreview.value = parseResult?.parsed_data || parseResult || null
    } catch {
      parsedPreview.value = null
    } finally {
      parseLoading.value = false
    }
  } catch (err: any) {
    if (err.response?.status === 409) {
      uploadConflict.value = err.response.data?.detail || err.response.data
      ElMessage.warning('版本冲突，请选择操作')
    } else {
      ElMessage.error('上传失败')
    }
  } finally {
    uploadLoading.value = false
  }
}

/** 步骤2：用户确认识别数据，正式调用 parse（dry_run=false）写入 parsed_data */
async function doConfirmParsed() {
  if (!pendingWpId.value) return
  parseLoading.value = true
  try {
    // 正式解析写入（dry_run=false）
    await parseWorkpaper(projectId.value, pendingWpId.value, false)
    uploadDialogVisible.value = false
    uploadStep.value = 1
    parsedPreview.value = null
    // 刷新底稿状态
    await fetchData()
    await selectWorkpaperById(pendingWpId.value)
    // 通知试算表刷新（五环联动：上传→解析→试算表更新→报表更新）
    eventBus.emit('workpaper:parsed', { projectId: projectId.value, wpId: pendingWpId.value })
    ElMessage.success(`底稿已上传（v${pendingNewVersion.value}），识别数据已写入`)
    pendingWpId.value = ''
  } catch {
    ElMessage.error('写入识别数据失败，请重试')
  } finally {
    parseLoading.value = false
  }
}

/** 兼容旧调用（handleUploadRedirect 中使用） */
async function doUpload(forceOverwrite: boolean) {
  await doUploadStep1(forceOverwrite)
}

async function onBatchDownload() {
  if (selectedWpIds.value.length === 0) return
  downloadLoading.value = true
  try {
    await downloadWorkpaperPack(projectId.value, selectedWpIds.value, true)
    ElMessage.success(`已下载 ${selectedWpIds.value.length} 个底稿`)
  } catch {
    ElMessage.error('批量下载失败')
  } finally {
    downloadLoading.value = false
  }
}

function onCheckChange() {
  if (!treeRef.value) return
  const checked = treeRef.value.getCheckedNodes(true) // leaf only
  selectedWpIds.value = checked.filter((n: any) => n.wpId).map((n: any) => n.wpId)
}

async function onQCCheck() {
  if (!selectedWp.value) return
  qcLoading.value = true
  try {
    qcResult.value = await runQCCheck(projectId.value, selectedWp.value.id)
    ElMessage.success('自检完成')
  } catch {
    ElMessage.error('自检失败')
  } finally {
    qcLoading.value = false
  }
}

async function onSubmitReview() {
  if (!selectedWp.value) return
  // 引导提示
  const { showGuide } = await import('@/composables/useWorkflowGuide')
  const ok = await showGuide(
    'submit_review',
    '📤 提交复核',
    `<div style="line-height:1.8;font-size:13px">
      <p>将底稿 <b>${selectedWp.value.wp_code || ''}</b> 提交给复核人审阅。</p>
      <p style="color:#909399;font-size:12px;margin-top:6px">请确认以下条件已满足：</p>
      <ul style="padding-left:18px;margin:4px 0">
        <li><span style="color:#e6a23c">⚠</span> 底稿内容已编制完成</li>
        <li><span style="color:#e6a23c">⚠</span> 已分配复核人</li>
        <li><span style="color:#e6a23c">⚠</span> 质量自检（QC）无阻断级问题</li>
        <li><span style="color:#e6a23c">⚠</span> 所有未解决的复核意见已回复</li>
      </ul>
      <p style="color:#909399;font-size:12px;margin-top:6px">💡 不满足条件时系统会自动阻断并提示具体原因</p>
    </div>`,
    '提交复核',
  )
  if (!ok) return
  submitLoading.value = true
  gateState.value = 'evaluating'
  gateHitRules.value = []
  gateTraceId.value = ''
  try {
    const currentWpId = selectedWp.value.id
    // 使用专用提交复核端点（后端统一校验门禁引擎 + 4 项门禁）
    const data = await submitWorkpaperReview(projectId.value, selectedWp.value.id)
    if (data?.status === 'blocked') {
      // Phase 14: 展示门禁阻断面板
      gateState.value = 'blocked'
      gateHitRules.value = data.hit_rules || []
      gateTraceId.value = data.trace_id || ''
      if (!gateHitRules.value.length) {
        // 旧格式兼容
        ElMessage.warning(`无法提交复核：${(data.blocking_reasons || []).join('；')}`)
      }
      return
    }
    gateState.value = 'normal'
    ElMessage.success('已提交复核')
    await fetchData()
    await selectWorkpaperById(currentWpId)
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    if (detail?.hit_rules) {
      // 409 门禁阻断响应
      gateState.value = 'blocked'
      gateHitRules.value = detail.hit_rules || []
      gateTraceId.value = detail.trace_id || ''
    } else if (detail?.error_code === 'SOD_CONFLICT_DETECTED') {
      // SoD 冲突
      sodConflictType.value = detail.message || ''
      sodPolicyCode.value = detail.policy_code || ''
      sodTraceId.value = detail.trace_id || ''
      showSodDialog.value = true
    } else {
      gateState.value = 'error'
      gateTraceId.value = detail?.trace_id || ''
      ElMessage.error(detail?.message || detail || '提交失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// Phase 14: 门禁阻断项跳转处理
function handleGateJump(location: Record<string, any>) {
  const section = location.section
  if (section === 'procedure_status' && location.procedure_ids?.length) {
    // 跳转到程序裁剪页
    router.push(`/projects/${projectId.value}/procedures?highlight=${location.procedure_ids[0]}`)
  } else if (section === 'audit_explanation') {
    // 跳转到底稿工作台说明编辑区
    router.push(`/projects/${projectId.value}/workpaper-bench`)
  } else if (section === 'audit_conclusion') {
    router.push(`/projects/${projectId.value}/workpaper-bench`)
  } else if (section === 'consistency') {
    // 跳转到一致性看板
    router.push(`/projects/${projectId.value}/consistency`)
  } else if (section === 'disclosure_notes') {
    router.push(`/projects/${projectId.value}/disclosure-notes`)
  } else if (section === 'audit_report') {
    router.push(`/projects/${projectId.value}/audit-report`)
  }
}

async function loadAnnotations() {
  if (!selectedWp.value) { annotations.value = []; return }
  try {
    annotations.value = await listWorkpaperAnnotations(projectId.value, 'workpaper', selectedWp.value.id)
  } catch { annotations.value = [] }
}

async function submitAnnotation() {
  if (!selectedWp.value || !newAnnotation.value.content) return
  try {
    await createAnnotation(projectId.value, {
      object_type: 'workpaper',
      object_id: selectedWp.value.id,
      content: newAnnotation.value.content,
      priority: newAnnotation.value.priority,
    })
    ElMessage.success('复核意见已提交')
    showAddAnnotation.value = false
    newAnnotation.value = { content: '', priority: 'medium' }
    await loadAnnotations()
  } catch { ElMessage.error('提交失败') }
}

async function resolveAnnotation(id: string) {
  try {
    await updateAnnotation(id, { status: 'resolved' })
    ElMessage.success('已标记为解决')
    await loadAnnotations()
    await loadUnconfirmedAi()
  } catch { ElMessage.error('操作失败') }
}

// 回复批注
const showReplyDialog = ref(false)
const replyTarget = ref<any>(null)
const replyContent = ref('')

function replyAnnotation(row: any) {
  replyTarget.value = row
  replyContent.value = ''
  showReplyDialog.value = true
}

async function _submitReply() {
  if (!replyTarget.value || !replyContent.value) return
  try {
    await updateAnnotation(replyTarget.value.id, { status: 'replied', reply_content: replyContent.value })
    ElMessage.success('回复已提交')
    showReplyDialog.value = false
    await loadAnnotations()
  } catch { ElMessage.error('回复失败') }
}

function onRejectClick() {
  if (!selectedWp.value) return
  rejectingWpId.value = selectedWp.value.id
  rejectReason.value = ''
  showRejectDialog.value = true
}

async function onConfirmReject() {
  if (!rejectingWpId.value || !rejectReason.value.trim()) return
  const rs = selectedWp.value?.review_status
  const rejectStatus = (rs === 'pending_level2' || rs === 'level2_in_progress')
    ? 'level2_rejected' : 'level1_rejected'
  try {
    await updateReviewStatus(projectId.value, rejectingWpId.value, rejectStatus, rejectReason.value)
    showRejectDialog.value = false
    ElMessage.success('已退回')
    await fetchData()
    await selectWorkpaperById(rejectingWpId.value)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '退回失败')
  }
}

async function onReviewPass() {
  if (!selectedWp.value) return
  // 强制检查：所有批注必须已解决
  if (unresolvedCount.value > 0) {
    try {
      await ElMessageBox.confirm(
        `当前有 ${unresolvedCount.value} 条未解决的复核意见，建议先处理后再通过复核。确定强制通过吗？`,
        '复核确认',
        {
          type: 'warning',
          confirmButtonText: '强制通过',
          cancelButtonText: '返回处理',
          confirmButtonClass: 'el-button--danger',
        }
      )
    } catch {
      return  // 用户选择返回处理
    }
  }
  const rs = selectedWp.value.review_status
  const passStatus = (rs === 'pending_level2' || rs === 'level2_in_progress')
    ? 'level2_passed' : 'level1_passed'
  try {
    await updateReviewStatus(projectId.value, selectedWp.value.id, passStatus)
    ElMessage.success('复核通过')
    await fetchData()
    await selectWorkpaperById(selectedWp.value.id)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  }
}

async function refreshOnlineEditState() {
  // Univer 纯前端，无需探测服务可用性
  onlineEditEnabled.value = true
  onlineEditAvailable.value = true
}

async function handleUploadRedirect() {
  const uploadWpId = typeof route.query.upload === 'string' ? route.query.upload : ''
  if (!uploadWpId) return
  await selectWorkpaperById(uploadWpId)
  if (selectedWp.value?.id === uploadWpId) {
    onUpload()
  }
  const nextQuery = { ...route.query }
  delete nextQuery.upload
  await router.replace({ query: nextQuery })
}

watch([filterCycle, filterStatus, filterAssignee], () => fetchData())
onMounted(async () => {
  await fetchData()
  // 任务 8.17.1：加载用户列表，同时赋值 userOptions 和 userNameMap
  try {
    const users = await listUsers()
    userOptions.value = users
    userNameMap.value = new Map(
      users.map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch {
    ElMessage.warning('加载用户列表失败')
  }
  try {
    const maturity = await getFeatureMaturity()
    onlineEditMaturity.value = maturity?.online_editing || 'pilot'
  } catch { /* 默认 pilot */ }
  await refreshOnlineEditState()
  await handleUploadRedirect()
})
</script>

<style scoped>
.gt-wp-list { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; }
.gt-wp-filter-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); flex-wrap: wrap; gap: 8px; }
.gt-wp-view-toggle { margin: 0 12px; }
.gt-wp-filters { display: flex; gap: var(--gt-space-2); align-items: center; }
.gt-wp-body { display: flex; gap: var(--gt-space-4); flex: 1; min-height: 0; }
.gt-wp-tree-panel {
  width: 320px; min-width: 320px; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-3); overflow-y: auto;
}
.gt-wp-detail-panel {
  flex: 1; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-5); overflow-y: auto;
}
.gt-wp-tree-node { display: flex; align-items: center; gap: 6px; width: 100%; }
.gt-wp-tree-node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-wp-tree-node-tag { flex-shrink: 0; }
.gt-wp-detail-card { }
.gt-wp-detail-title { margin: 0 0 var(--gt-space-4); color: var(--gt-color-primary); font-size: var(--gt-font-size-xl); }
.gt-wp-detail-actions { display: flex; gap: var(--gt-space-2); margin-top: var(--gt-space-4); flex-wrap: wrap; }
.gt-wp-qc-summary-inline { margin-top: var(--gt-space-3); display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wp-qc-counts { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }

/* 加载中全宽 */
.gt-wp-empty-full {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); min-height: 300px;
}

/* 全宽空状态 */
.gt-wp-empty-full {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); min-height: 300px;
}
.gt-wp-empty-icon { font-size: 48px; margin-bottom: 12px; opacity: 0.7; }
.gt-wp-empty-title { font-size: 18px; font-weight: 600; color: #444; margin-bottom: 6px; }
.gt-wp-empty-desc { font-size: 14px; color: #999; }
/* 精细化审计检查 */
.gt-fine-check-item {
  display: flex; align-items: center; gap: 8px; padding: 4px 8px;
  font-size: 12px; border-radius: 4px; margin-bottom: 2px;
}
.gt-fine-check-pass { background: #f0f9eb; }
.gt-fine-check-fail { background: #fdf6ec; }
.gt-fine-check-pending { background: #f5f5f5; }
.gt-fine-check-code { font-weight: 600; color: #666; min-width: 70px; }
.gt-fine-check-desc { flex: 1; color: #333; }
.gt-fine-check-status { font-size: 11px; white-space: nowrap; }
:deep(.gt-ann-row-urgent) { background: #fef0f0 !important; }

/* 解析预览数值样式 */
.gt-parsed-value { color: var(--gt-color-primary); font-weight: 600; }
.gt-parsed-empty { color: #999; font-style: italic; }
.gt-parsed-diff { color: var(--gt-color-coral); font-weight: 600; }

/* ── 两栏引导布局 ── */
.gt-wp-intro-layout {
  flex: 1; display: flex; gap: var(--gt-space-4); min-height: 0;
}
.gt-wp-intro-half {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-5);
}
.gt-wp-intro-half--guide {
  align-items: stretch; justify-content: flex-start; overflow-y: auto;
}
.gt-wp-intro-icon { font-size: 48px; margin-bottom: 12px; opacity: 0.7; }
.gt-wp-intro-title { font-size: 18px; font-weight: 600; color: #444; margin-bottom: 6px; }
.gt-wp-intro-desc { font-size: 13px; color: #999; text-align: center; }

.gt-wp-guide-title {
  margin: 0 0 12px; font-size: 16px; font-weight: 600; color: var(--gt-color-primary);
}

/* 流程横条 */
.gt-wp-guide-flow {
  display: flex; align-items: center; gap: 6px; margin-bottom: 16px;
  padding: 10px 12px; background: #f8f5fd; border-radius: 8px; flex-wrap: wrap;
}
.gt-wp-flow-tag {
  display: inline-block; padding: 3px 10px; border-radius: 10px;
  font-size: 11px; font-weight: 600; color: #fff; white-space: nowrap;
}
.gt-wp-flow-arrow { color: #bbb; font-size: 13px; }

/* 循环列表 */
.gt-wp-guide-list { display: flex; flex-direction: column; }
.gt-wp-guide-row {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-bottom: 1px solid #f5f5f5; cursor: pointer; border-radius: 6px;
  transition: background 0.15s;
}
.gt-wp-guide-row:hover { background: #f8f5fd; }
.gt-wp-guide-row:last-child { border-bottom: none; }
.gt-wp-guide-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 26px; height: 22px; padding: 0 7px;
  border-radius: 11px; font-size: 11px; font-weight: 700; color: #fff;
}
.gt-wp-guide-name { flex: 1; font-size: 13px; color: #333; }
.gt-wp-guide-count { font-size: 12px; color: #aaa; white-space: nowrap; }
.gt-wp-guide-arrow { font-size: 16px; color: #ccc; font-weight: 300; }

/* 进度条区域 */
.gt-wp-progress-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 8px 12px; margin-bottom: var(--gt-space-3);
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); font-size: 13px; color: var(--gt-color-text-secondary);
}
</style>
