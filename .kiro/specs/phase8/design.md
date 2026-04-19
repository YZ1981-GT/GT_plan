# Phase 8 — 技术设计

## 1. 数据模型字段缺失修复

### 1a 辅助表字段补充（✅已在 Phase 6 完成，设计保留供参考）

#### 迁移脚本（已通过手动 ALTER TABLE 完成，无需执行）
```python
def upgrade():
    # tb_aux_balance 添加 account_name
    op.add_column('tb_aux_balance', sa.Column('account_name', sa.String(100), nullable=False, server_default=''))
    
    # tb_aux_ledger 添加 account_name
    op.add_column('tb_aux_ledger', sa.Column('account_name', sa.String(100), nullable=False, server_default=''))
    
    # 从 account_chart 同步 account_name
    connection = op.get_bind()
    connection.execute(
        """
        UPDATE tb_aux_balance aux
        SET account_name = (
            SELECT account_name 
            FROM account_chart ac 
            WHERE ac.account_code = aux.account_code
            LIMIT 1
        )
        WHERE aux.account_name = ''
        """
    )
    
    connection.execute(
        """
        UPDATE tb_aux_ledger aux
        SET account_name = (
            SELECT account_name 
            FROM account_chart ac 
            WHERE ac.account_code = aux.account_code
            LIMIT 1
        )
        WHERE aux.account_name = ''
        """
    )
    
    # 创建索引
    op.create_index('idx_tb_aux_balance_account_name', 'tb_aux_balance', ['account_name'])
    op.create_index('idx_tb_aux_ledger_account_name', 'tb_aux_ledger', ['account_name'])

def downgrade():
    op.drop_index('idx_tb_aux_ledger_account_name', 'tb_aux_ledger')
    op.drop_index('idx_tb_aux_balance_account_name', 'tb_aux_balance')
    op.drop_column('tb_aux_ledger', 'account_name')
    op.drop_column('tb_aux_balance', 'account_name')
```

### 1b 试算表字段补充

#### 迁移脚本：034_add_currency_code_to_trial_balance.py
```python
def upgrade():
    # trial_balance 添加 currency_code
    op.add_column('trial_balance', sa.Column('currency_code', sa.String(3), nullable=False, server_default='CNY'))
    
    # 创建索引
    op.create_index('idx_trial_balance_currency_code', 'trial_balance', ['currency_code'])

def downgrade():
    op.drop_index('idx_trial_balance_currency_code', 'trial_balance')
    op.drop_column('trial_balance', 'currency_code')
```

### 1c 穿透查询优化（✅已在 Phase 6 完成）

#### 优化前后对比
```python
# 优化前：需要 JOIN account_chart 获取科目名称
SELECT aux.*, ac.account_name
FROM tb_aux_balance aux
LEFT JOIN account_chart ac ON aux.account_code = ac.account_code
WHERE aux.project_id = :project_id

# 优化后：直接使用 aux.account_name
SELECT aux.*
FROM tb_aux_balance aux
WHERE aux.project_id = :project_id
```

## 2. 查询性能优化

### 2a 穿透查询性能优化（✅缓存已在 Phase 6 完成，游标分页为增量）

#### Redis 缓存策略
```python
class LedgerPenetrationService:
    CACHE_TTL = 300  # 5分钟
    
    async def get_balance(self, project_id: UUID, account_code: str) -> dict:
        cache_key = f"ledger:balance:{project_id}:{account_code}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # 查询数据库
        result = await self._query_balance(project_id, account_code)
        await redis.setex(cache_key, self.CACHE_TTL, json.dumps(result))
        return result
```

#### 游标分页
```python
async def get_ledger_with_cursor(
    project_id: UUID,
    cursor: str = None,
    limit: int = 100
) -> dict:
    query = select(tb_ledger).where(tb_ledger.project_id == project_id)
    
    if cursor:
        query = query.where(tb_ledger.id > cursor)
    
    query = query.order_by(tb_ledger.id).limit(limit + 1)
    results = await db.execute(query)
    items = results.scalars().all()
    
    has_more = len(items) > limit
    next_cursor = items[-1].id if has_more else None
    
    return {
        "items": items[:limit],
        "next_cursor": next_cursor,
        "has_more": has_more
    }
```

### 2b 四表联查性能优化

#### CTE 优化
```sql
WITH balance AS (
    SELECT account_code, closing_balance
    FROM tb_balance
    WHERE project_id = :project_id
),
ledger_summary AS (
    SELECT account_code, SUM(debit_amount) as total_debit, SUM(credit_amount) as total_credit
    FROM tb_ledger
    WHERE project_id = :project_id
    GROUP BY account_code
)
SELECT b.account_code, b.closing_balance, l.total_debit, l.total_credit
FROM balance b
LEFT JOIN ledger_summary l ON b.account_code = l.account_code
```

### 2c 报表生成性能优化

#### 缓存策略
```python
class ReportEngine:
    CACHE_TTL = 600  # 10分钟
    
    async def calculate_report(self, project_id: UUID, report_type: str) -> dict:
        cache_key = f"report:{project_id}:{report_type}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # 计算报表
        result = await self._calculate(project_id, report_type)
        await redis.setex(cache_key, self.CACHE_TTL, json.dumps(result))
        return result
    
    async def _generate_report(self, project_id, year, report_type, ...):
        # ... 生成逻辑 ...
        # 生成完成后发布事件，供附注/导出等下游服务监听
        await event_bus.publish(EventPayload(
            event_type=EventType.REPORT_GENERATED,
            project_id=project_id,
            data={"report_type": report_type, "year": year}
        ))
```

### 2d 核心表复合索引补齐

#### 迁移脚本（合并到 034）
```python
# 在 034_add_currency_code_to_trial_balance.py 中一并创建
def upgrade():
    # ... currency_code 字段 ...
    
    # 核心查询路径复合索引
    op.create_index(
        "idx_trial_balance_project_year_std_code",
        "trial_balance",
        ["project_id", "year", "standard_account_code"],
    )
    op.create_index(
        "idx_tb_balance_project_year_deleted",
        "tb_balance",
        ["project_id", "year", "is_deleted"],
    )
    op.create_index(
        "idx_adjustments_project_year_account_code",
        "adjustments",
        ["project_id", "year", "account_code"],
    )
    op.create_index(
        "idx_import_batches_project_year",
        "import_batches",
        ["project_id", "year"],
    )
```

#### 索引覆盖的查询路径
| 索引 | 覆盖的服务方法 | 预期提升 |
|------|--------------|---------|
| trial_balance(project_id,year,standard_account_code) | TrialBalanceService.recalc_* / ReportEngine._generate_report | 试算表重算+报表生成 |
| tb_balance(project_id,year,is_deleted) | import_service._soft_delete_existing / _count_existing | 导入前清理+计数 |
| adjustments(project_id,year,account_code) | AdjustmentService.list_entries / TrialBalanceService.recalc_adjustments | 调整分录按科目查询 |
| import_batches(project_id,year) | import_service.get_import_batches | 导入批次列表 |

### 2e 事件总线去重与合并

#### EventBus debounce 机制
```python
class EventBus:
    def __init__(self) -> None:
        self._handlers = defaultdict(list)
        self._sse_queues = []
        self._pending: dict[str, asyncio.TimerHandle] = {}  # debounce 缓冲
        self._debounce_ms: int = 500  # 默认 500ms 窗口
    
    async def publish(self, payload: EventPayload) -> None:
        """发布事件，相同 key 在 debounce 窗口内合并为一次"""
        dedup_key = f"{payload.event_type.value}:{payload.project_id}"
        
        # 合并 account_codes
        if dedup_key in self._pending:
            self._pending[dedup_key]["handle"].cancel()
            existing_codes = self._pending[dedup_key]["payload"].account_codes or []
            new_codes = payload.account_codes or []
            payload.account_codes = list(set(existing_codes + new_codes))
        
        loop = asyncio.get_running_loop()
        handle = loop.call_later(
            self._debounce_ms / 1000,
            lambda p=payload: asyncio.create_task(self._dispatch(p))
        )
        self._pending[dedup_key] = {"handle": handle, "payload": payload}
    
    async def _dispatch(self, payload: EventPayload) -> None:
        """实际分发事件到处理器"""
        dedup_key = f"{payload.event_type.value}:{payload.project_id}"
        self._pending.pop(dedup_key, None)
        # ... 原有的 handler 调用逻辑 ...
```

### 2f 公式引擎超时控制

#### asyncio.wait_for 包装
```python
class FormulaEngine:
    EXECUTE_TIMEOUT = 10  # 秒
    
    async def execute(self, db, project_id, year, formula_str, **kwargs):
        try:
            return await asyncio.wait_for(
                self._execute_inner(db, project_id, year, formula_str, **kwargs),
                timeout=self.EXECUTE_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(
                "Formula timeout: %s (project=%s, account=%s)",
                formula_str, project_id, kwargs.get("account_code")
            )
            return FormulaError(code="TIMEOUT", message=f"公式执行超时({self.EXECUTE_TIMEOUT}s): {formula_str[:50]}")
```

### 2g 数据导入流式处理

#### openpyxl read_only 模式
```python
async def _parse_excel_streaming(file_path: str, data_type: str, chunk_size: int = 1000):
    """流式读取 Excel，每次 yield 一批行，避免一次性加载到内存"""
    from openpyxl import load_workbook
    
    wb = load_workbook(file_path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        chunk = []
        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx == 0:
                headers = [str(c) if c else "" for c in row]
                continue
            chunk.append(dict(zip(headers, row)))
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
    wb.close()
```

#### 导入流程改造
```python
async def start_import_streaming(project_id, file, data_type, year, db):
    total_rows = 0
    async for chunk in _parse_excel_streaming(file_path, data_type):
        # 分批校验
        validation_result = validation_engine.validate_batch(chunk)
        # 分批写入
        await db.execute(table_model.__table__.insert(), chunk)
        total_rows += len(chunk)
        # 发布进度
        await event_bus.publish(EventPayload(
            event_type=EventType.IMPORT_PROGRESS,
            project_id=project_id,
            data={"rows_imported": total_rows}
        ))
    await db.commit()
```

## 3. 底稿编辑体验优化

### 3a ONLYOFFICE 编辑器性能优化

#### 异步事件处理
```python
class WOPIHostService:
    async def put_file(self, file_id: UUID, content: bytes) -> dict:
        # 保存文件
        await self._save_file(file_id, content)
        
        # 异步发布事件
        asyncio.create_task(event_bus.publish(
            EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                data={"file_id": str(file_id)}
            )
        ))
        
        return {"status": "success"}
```

### 3b 底稿列表加载优化

#### 虚拟滚动
```vue
<template>
  <VirtualScroller
    :items="workpapers"
    :item-size="60"
    :buffer="10"
  >
    <template #default="{ item }">
      <WorkpaperItem :workpaper="item" />
    </template>
  </VirtualScroller>
</template>
```

### 3c 底稿预填性能优化

#### 并发预填
```python
class PrefillService:
    async def batch_prefill(self, project_id: UUID, wp_ids: List[UUID]) -> dict:
        tasks = [self._prefill_single(wp_id) for wp_id in wp_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            wp_id: result for wp_id, result in zip(wp_ids, results)
            if not isinstance(result, Exception)
        }
```

## 4. 报表导出优化

### 4a Word 导出性能优化

#### 模板缓存
```python
class ReportExportEngine:
    _template_cache = {}
    
    async def _load_template(self, template_name: str) -> Document:
        if template_name not in self._template_cache:
            self._template_cache[template_name] = Document(template_name)
        return self._template_cache[template_name]
```

### 4b PDF 导出性能优化

#### 异步导出
```python
class PDFExportEngine:
    async def export_async(self, content: str, task_id: UUID) -> str:
        # 更新任务状态
        await task_center.update(task_id, status="processing")
        
        try:
            # 生成 PDF
            pdf_path = await self._generate_pdf(content)
            
            # 更新任务状态
            await task_center.update(task_id, status="success", result=pdf_path)
            
            return pdf_path
        except Exception as e:
            await task_center.update(task_id, status="failed", error=str(e))
            raise
```

### 4c 导出格式一致性

#### 致同规范校验引擎
```python
class ExportFormatValidator:
    """导出格式一致性校验，确保与致同规范一致"""
    
    GT_SPEC = {
        "font_cn": "仿宋_GB2312",
        "font_en": "Arial Narrow",
        "margins": {"top": 3.0, "bottom": 3.18, "left": 3.2, "right": 2.54},  # cm
        "table_border": {"top": 1, "bottom": 1, "left": 0, "right": 0},  # pt
        "page_footer": True,  # 页脚页码
    }
    
    def validate_word(self, doc_path: str) -> list[dict]:
        """校验 Word 导出格式是否符合致同规范"""
        findings = []
        doc = Document(doc_path)
        
        # 检查字体
        for para in doc.paragraphs:
            for run in para.runs:
                if run.font.name and run.font.name not in [self.GT_SPEC["font_cn"], self.GT_SPEC["font_en"]]:
                    findings.append({"type": "font", "message": f"非规范字体: {run.font.name}", "location": para.text[:30]})
        
        # 检查页边距
        section = doc.sections[0]
        margins = {
            "top": section.top_margin.cm, "bottom": section.bottom_margin.cm,
            "left": section.left_margin.cm, "right": section.right_margin.cm
        }
        for key, expected in self.GT_SPEC["margins"].items():
            if abs(margins[key] - expected) > 0.1:
                findings.append({"type": "margin", "message": f"{key}页边距 {margins[key]:.2f}cm，规范要求 {expected}cm"})
        
        return findings
```

#### 导出预览 API
```python
@router.post("/api/projects/{project_id}/export/preview")
async def preview_export(project_id: UUID, export_type: str = "word"):
    """导出前预览，返回 HTML 渲染结果供 iframe 展示"""
    content = await report_export_engine.render_preview(project_id, export_type)
    return {"html": content, "validation": await format_validator.validate_preview(content)}
```

## 5. 移动端适配

### 5a 响应式布局

#### 断点配置
```scss
$breakpoints: (
  mobile: 768px,
  tablet: 1024px,
  desktop: 1280px
);

@media (max-width: map-get($breakpoints, mobile)) {
  .three-column-layout {
    flex-direction: column;
  }
  
  .nav-sidebar {
    position: fixed;
    z-index: 1000;
  }
}
```

### 5b 移动端底稿编辑

#### 移动端组件
```vue
<template>
  <div class="mobile-workpaper-editor">
    <MobileToolbar @download="handleDownload" />
    <div class="workpaper-content">
      <CellEditor
        v-for="cell in cells"
        :key="cell.ref"
        :cell="cell"
        @update="handleCellUpdate"
      />
    </div>
  </div>
</template>
```

## 6. 审计程序精细化

### 6a 细分程序打磨

#### 程序裁剪引擎
```python
class ProcedureTrimEngine:
    async def trim_procedures(self, project_id: UUID) -> dict:
        # 获取项目风险评估
        risk_assessment = await self._get_risk_assessment(project_id)
        
        # 获取程序模板
        procedures = await self._get_procedures(project_id)
        
        # 根据风险等级裁剪
        trimmed = []
        for proc in procedures:
            risk_level = self._calculate_risk_level(proc, risk_assessment)
            if risk_level >= self._get_threshold(project_id):
                trimmed.append(proc)
        
        return {"trimmed_procedures": trimmed}
```

## 7. 数据校验增强

### 7a 数据一致性校验

#### 校验引擎
```python
class DataValidationEngine:
    async def validate_project(self, project_id: UUID) -> dict:
        findings = []
        
        # 余额表与辅助表一致性
        findings.extend(await self._validate_balance_aux(project_id))
        
        # 报表与附注一致性
        findings.extend(await self._validate_report_note(project_id))
        
        # 底稿与试算表一致性
        findings.extend(await self._validate_workpaper_tb(project_id))
        
        return {
            "findings": findings,
            "total": len(findings),
            "blocking": len([f for f in findings if f.severity == "high"])
        }
```

### 7b 数据校验面板

#### 前端组件
```vue
<template>
  <div class="data-validation-panel">
    <el-tabs>
      <el-tab-pane label="数据一致性">
        <ValidationList
          :findings="consistencyFindings"
          @fix="handleFix"
        />
      </el-tab-pane>
      <el-tab-pane label="数据完整性">
        <ValidationList
          :findings="completenessFindings"
          @fix="handleFix"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
```

## 8. 性能监控

### 8a Prometheus 指标收集

#### 指标定义
```python
from prometheus_client import Counter, Histogram, Gauge

# API 响应时间
api_response_time = Histogram(
    'api_response_time_seconds',
    'API response time',
    ['endpoint', 'method']
)

# 数据库查询时间
db_query_time = Histogram(
    'db_query_time_seconds',
    'Database query time',
    ['query_type']
)

# 缓存命中率
cache_hit_rate = Gauge(
    'cache_hit_rate',
    'Cache hit rate',
    ['cache_name']
)
```

### 8b 性能分析面板

#### 前端组件
```vue
<template>
  <div class="performance-monitor">
    <el-row :gutter="20">
      <el-col :span="8">
        <StatCard title="API 响应时间" :value="apiAvgTime" unit="ms" />
      </el-col>
      <el-col :span="8">
        <StatCard title="数据库查询时间" :value="dbAvgTime" unit="ms" />
      </el-col>
      <el-col :span="8">
        <StatCard title="缓存命中率" :value="cacheHitRate" unit="%" />
      </el-col>
    </el-row>
    
    <div class="charts">
      <ResponseTimeChart :data="responseTimeData" />
      <CacheHitRateChart :data="cacheHitRateData" />
    </div>
  </div>
</template>
```

## 9. 用户体验优化

### 9a 加载状态优化

#### 统一加载状态组件
```vue
<template>
  <div class="loading-state">
    <el-skeleton v-if="skeleton" :rows="3" animated />
    <el-empty v-else-if="empty" description="暂无数据" />
    <el-alert v-else-if="error" type="error" :title="errorMessage" />
  </div>
</template>
```

#### 骨架屏优化
```vue
<template>
  <el-skeleton :rows="5" animated :loading="loading">
    <div class="content">
      <!-- 实际内容 -->
    </div>
  </el-skeleton>
</template>
```

### 9b 操作反馈优化

#### 操作提示组件
```vue
<template>
  <div class="operation-feedback">
    <el-notification
      v-if="success"
      title="操作成功"
      type="success"
      :message="successMessage"
    />
    <el-notification
      v-if="error"
      title="操作失败"
      type="error"
      :message="errorMessage"
    />
    <el-progress
      v-if="progress"
      :percentage="progressValue"
      :status="progressStatus"
    />
  </div>
</template>
```

#### 操作撤销
```typescript
class OperationHistory {
  private history: Operation[] = []

  async execute(operation: Operation) {
    const result = await operation.execute()
    this.history.push(operation)
    return result
  }

  async undo() {
    const lastOp = this.history.pop()
    if (lastOp) {
      await lastOp.undo()
    }
  }
}
```

### 9c 快捷键支持

#### 快捷键管理
```typescript
class ShortcutManager {
  private shortcuts: Map<string, () => void> = new Map()

  register(key: string, handler: () => void) {
    this.shortcuts.set(key, handler)
  }

  handleKeydown(event: KeyboardEvent) {
    const key = this.getShortcutKey(event)
    const handler = this.shortcuts.get(key)
    if (handler) {
      handler()
      event.preventDefault()
    }
  }

  private getShortcutKey(event: KeyboardEvent): string {
    const modifiers = []
    if (event.ctrlKey) modifiers.push('Ctrl')
    if (event.shiftKey) modifiers.push('Shift')
    if (event.altKey) modifiers.push('Alt')
    modifiers.push(event.key)
    return modifiers.join('+')
  }
}
```

#### 快捷键提示
```vue
<template>
  <div class="shortcut-hint">
    <el-tooltip content="保存 (Ctrl+S)">
      <el-button>保存</el-button>
    </el-tooltip>
    <el-tooltip content="撤销 (Ctrl+Z)">
      <el-button>撤销</el-button>
    </el-tooltip>
  </div>
</template>
```

#### 默认快捷键映射表

| 快捷键 | 功能 | 适用页面 |
|--------|------|---------|
| Ctrl+S | 保存当前编辑内容 | 底稿编辑/附注编辑/报告编辑 |
| Ctrl+Z | 撤销上一步操作 | 全局 |
| Ctrl+Shift+Z | 重做 | 全局 |
| Ctrl+F | 搜索 | 全局 |
| Ctrl+G | 跳转到指定科目 | 试算表/穿透查询 |
| Ctrl+E | 导出当前页面 | 报表/附注/底稿 |
| Ctrl+Enter | 提交/确认 | 表单/弹窗 |
| Escape | 关闭弹窗/退出全屏 | 全局 |
| Tab | 切换栏目焦点 | 三栏/四栏布局 |
| ↑/↓ | 列表项导航 | 项目列表/底稿列表/科目列表 |
| Enter | 打开选中项详情 | 列表页 |
| F5 | 刷新当前数据 | 全局 |
| Ctrl+/ | 显示快捷键帮助面板 | 全局 |

## 10. 安全增强

### 10a 数据加密

#### 敏感数据加密
```python
from cryptography.fernet import Fernet

class EncryptionService:
    def __init__(self):
        self.key = os.getenv('ENCRYPTION_KEY')
        self.cipher = Fernet(self.key)
    
    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        return self.cipher.decrypt(encrypted.encode()).decode()
```

### 10b 审计日志增强

#### 审计日志记录
```python
class AuditLogger:
    async def log_action(
        self,
        user_id: UUID,
        action: str,
        object_type: str,
        object_id: UUID,
        details: dict = None
    ):
        await db.execute(
            insert(logs).values(
                user_id=user_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                details=details or {},
                request_id=getattr(request.state, 'request_id', None)
            )
        )
```

### 10c 安全监控

#### 登录失败监控
```python
class SecurityMonitor:
    MAX_FAILED_ATTEMPTS = 5
    LOCK_DURATION = 1800  # 30分钟
    
    async def check_login_attempts(self, username: str) -> bool:
        cache_key = f"login_attempts:{username}"
        attempts = await redis.get(cache_key)
        
        if attempts and int(attempts) >= self.MAX_FAILED_ATTEMPTS:
            return False
        
        return True
    
    async def record_failed_attempt(self, username: str):
        cache_key = f"login_attempts:{username}"
        await redis.incr(cache_key)
        await redis.expire(cache_key, self.LOCK_DURATION)
```

### 10d 权限查询缓存

#### Redis 缓存策略
```python
# deps.py 中 require_project_access 改造
PERM_CACHE_TTL = 300  # 5分钟

async def _get_cached_permission(
    user_id: UUID, project_id: UUID, redis_client
) -> str | None:
    """从 Redis 获取缓存的权限级别，不可用时返回 None（降级查库）"""
    try:
        cache_key = f"perm:{user_id}:{project_id}"
        cached = await redis_client.get(cache_key)
        return cached.decode() if cached else None
    except Exception:
        return None  # Redis 不可用时降级

async def _set_cached_permission(
    user_id: UUID, project_id: UUID, level: str, redis_client
) -> None:
    try:
        cache_key = f"perm:{user_id}:{project_id}"
        await redis_client.setex(cache_key, PERM_CACHE_TTL, level)
    except Exception:
        pass  # 写缓存失败不阻断

async def invalidate_permission_cache(
    user_id: UUID, project_id: UUID, redis_client
) -> None:
    """权限变更时主动失效缓存（在 project_users CRUD 中调用）"""
    try:
        cache_key = f"perm:{user_id}:{project_id}"
        await redis_client.delete(cache_key)
    except Exception:
        pass
```

## 数据库变更汇总

### 新增表（0个）
Phase 8 不新增表，只修改现有表字段

### 修改现有表（3个）
1. ~~`tb_aux_balance` - 添加 `account_name` 字段~~（✅Phase 6 已完成）
2. ~~`tb_aux_ledger` - 添加 `account_name` 字段~~（✅Phase 6 已完成）
3. `trial_balance` - 添加 `currency_code` 字段

### 新增索引（7个）
1. ~~`idx_tb_aux_balance_account_name` - 辅助余额表科目名称索引~~（✅Phase 6 已完成）
2. ~~`idx_tb_aux_ledger_account_name` - 辅助账表科目名称索引~~（✅Phase 6 已完成）
3. `idx_trial_balance_currency_code` - 试算表货币代码索引
4. `idx_trial_balance_project_year_std_code` - 试算表核心查询路径索引
5. `idx_tb_balance_project_year_deleted` - 余额表软删除查询索引
6. `idx_adjustments_project_year_account_code` - 调整分录按科目查询索引
7. `idx_import_batches_project_year` - 导入批次查询索引

## API变更汇总

### 修改API（预计2个）
1. `/api/projects/{id}/ledger/penetrate` - 穿透查询优化（避免额外JOIN）
2. `/api/projects/{id}/trial-balance` - 试算表查询支持货币代码筛选

### 新增API（预计11个）
1. `/api/projects/{id}/data-validation` - 数据校验API
2. `/api/projects/{id}/data-validation/findings` - 数据校验结果查询
3. `/api/projects/{id}/data-validation/fix` - 数据校验一键修复
4. `/api/projects/{id}/data-validation/export` - 数据校验导出
5. `/api/admin/performance-stats` - 性能统计API
6. `/api/admin/performance-metrics` - 性能指标查询
7. `/api/admin/slow-queries` - 慢查询查询
8. `/api/security/login-attempts` - 登录失败监控API
9. `/api/security/lock-account` - 锁定账户API
10. `/api/security/sessions` - 会话管理API
11. `/api/audit-logs/export` - 审计日志导出API

## 前端组件变更

### 优化组件（预计5-8个）
- WorkpaperEditor.vue - 底稿编辑器优化
- LedgerPenetration.vue - 穿透查询优化
- ExportPanel.vue - 报表导出优化
- ThreeColumnLayout.vue - 响应式布局优化
- FourColumnCatalog.vue - 四栏视图优化

### 新增组件（预计3-5个）
- DataValidationPanel.vue - 数据校验面板
- PerformanceMonitor.vue - 性能监控面板
- SecurityMonitor.vue - 安全监控面板
- MobileWorkpaperEditor.vue - 移动端底稿编辑器
- ValidationList.vue - 校验结果列表

## 依赖项变更

### Python依赖（预计新增3个）
```txt
# 性能监控
prometheus-client>=0.19.0
# 数据校验
pandas>=2.0.0
# 数据加密
cryptography>=41.0.0
```

### 前端依赖（预计新增3个）
```json
{
  "echarts": "^5.4.0",
  "vue-virtual-scroller": "^2.0.0",
  "@vueuse/core": "^10.0.0"
}
```

## 跨Phase兼容性说明

| 冲突点 | 涉及 Phase | 解决方案 |
|--------|-----------|---------|
| account_name字段 | Phase 8 vs Phase 6 | ✅已在 Phase 6 完成，Phase 8 无需重复 |
| currency_code字段 | Phase 8 vs Phase 5 | Phase 5 已有多准则适配，currency_code 字段作为补充 |
| 穿透查询缓存 | Phase 8 vs Phase 6 | ✅缓存已在 Phase 6 完成，Phase 8 仅做游标分页增量 |
| 移动端适配 | Phase 8 vs Phase 5 | Phase 5 已有响应式布局，Phase 8 进一步优化移动端体验 |
| 底稿编辑优化 | Phase 8 vs Phase 7 | Phase 7 有 WOPI 企业级重写，Phase 8 仅做编辑器预加载增量 |
| 报表导出优化 | Phase 8 vs Phase 1c | Phase 1c 有 PDF 导出引擎，Phase 8 优化性能，不冲突 |
| 审计程序精细化 | Phase 8 vs Phase 6 | Phase 6 有程序裁剪方案，Phase 8 仅做高风险科目打磨增量 |
| 安全增强 | Phase 8 vs Phase 7 | Phase 7 有权限精细化，Phase 8 数据加密和审计日志告警，不冲突 |
| 性能监控 | Phase 8 vs Phase 5 | Phase 5 有大数据处理优化，Phase 8 新增 Prometheus 后端监控 |
| 数据校验 | Phase 8 vs Phase 6 | Phase 6 有 ConsistencyCheckService 5项校验，Phase 8 新增完整性校验+校验面板 |
| 登录失败监控 | Phase 8 vs Phase 0 | ✅已在 Phase 0 完成，Phase 8 无需重复 |
| 敏感导出日志 | Phase 8 vs Phase 7 | ✅已在 Phase 7 复盘修复完成，Phase 8 无需重复 |
| 事件去重 | Phase 8 vs Phase 6 | Phase 6 EventBus 无去重，Phase 8 新增 debounce 机制，向后兼容（新增 publish_immediate） |
| 公式超时 | Phase 8 vs Phase 1b | Phase 1b FormulaEngine 无超时，Phase 8 新增 wait_for 包装，不改变接口 |
| 流式导入 | Phase 8 vs Phase 1a | Phase 1a GenericParser 一次性加载，Phase 8 新增 parse_streaming 方法，原方法保留 |
| 权限缓存 | Phase 8 vs Phase 0 | Phase 0 deps.py 每次查库，Phase 8 加 Redis 缓存层，Redis 不可用时降级查库 |
