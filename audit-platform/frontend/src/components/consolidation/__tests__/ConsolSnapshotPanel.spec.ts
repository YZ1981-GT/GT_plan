/**
 * 批 7 任务 7.4：合并签字快照面板（列表 / 完整性 / 对比 / 下载 + 诊断快照 / 签字锁定）。
 *
 * 守卫：
 *  - 列表加载失败保留上次成功数据，只显示错误条（不清空表格）
 *  - 年度缺失 / 只读原因下，创建诊断快照与签字锁定按钮按正确规则禁用并给中文原因
 *  - 签字锁定 409 fail-closed 拒绝逐条列明原因（不当成功）
 *  - 签字锁定成功 emit locked + created；诊断快照成功 emit created
 *  - 完整性校验 / 对比 / 下载调用正确的 service 函数
 */
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { service, messages, msgBox } = vi.hoisted(() => ({
  service: {
    listConsolSnapshots: vi.fn(),
    createConsolSnapshot: vi.fn(),
    restoreConsolSnapshot: vi.fn(),
    compareConsolSnapshot: vi.fn(),
    downloadConsolSnapshot: vi.fn(),
  } as Record<string, ReturnType<typeof vi.fn>>,
  messages: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  msgBox: { confirm: vi.fn(), alert: vi.fn() },
}))

vi.mock('@/services/consolidationApi', () => Object.fromEntries(
  Object.keys(service).map((key) => [key, (...args: any[]) => service[key](...args)]),
))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: messages, ElMessageBox: msgBox }
})

import ConsolSnapshotPanel from '../ConsolSnapshotPanel.vue'

const V2_ITEM = {
  id: 'snap-1', year: 2025, trigger_reason: 'sign', created_at: '2026-05-15T10:00:00Z',
  created_by: 'u1', format: 'manifest-v2', locked: true, root_hash: 'abcdef0123456789',
  manifest_version: 2, partial: false, failed_sources: [], captured_sources: ['tree', 'trial'],
  operation_ref: { operation_id: 'op-1234567890', revision: 3, status: 'succeeded', request_hash: 'rh' },
  version_ref: { digest: 'vd-abcdef1234', tree_fingerprint: 'tf' }, counts: { trial: 10 },
}
const PARTIAL_ITEM = {
  id: 'snap-2', year: 2025, trigger_reason: 'manual', created_at: '2026-05-10T09:00:00Z',
  created_by: null, format: 'manifest-v2', locked: false, root_hash: 'deadbeef',
  manifest_version: 2, partial: true, failed_sources: ['report', 'artifact'], captured_sources: ['tree'],
  operation_ref: {}, version_ref: {}, counts: {},
}

function create(props: Record<string, unknown> = {}) {
  return mount(ConsolSnapshotPanel, {
    props: { projectId: 'p1', year: 2025, readonlyReason: '', ...props },
    global: { plugins: [ElementPlus] },
  })
}
const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset())
  Object.values(messages).forEach((fn) => fn.mockReset())
  msgBox.confirm.mockReset(); msgBox.alert.mockReset()
  service.listConsolSnapshots.mockResolvedValue([V2_ITEM, PARTIAL_ITEM])
  service.createConsolSnapshot.mockResolvedValue({ id: 'snap-3', year: 2025, hash: 'h', locked: true })
  service.restoreConsolSnapshot.mockResolvedValue({ hash_valid: true, hash: 'abcdef', locked: true, root_valid: true, shard_mismatches: [] })
  service.compareConsolSnapshot.mockResolvedValue({ by_account: [{ account_code: '1001', snapshot_amount: '100', current_amount: '120', changed: true }], changed_count: 1, hash_valid: true })
  service.downloadConsolSnapshot.mockResolvedValue(undefined)
  msgBox.confirm.mockResolvedValue('confirm')
})

describe('ConsolSnapshotPanel — 列表加载', () => {
  it('挂载即按 projectId/year 拉列表', async () => {
    const w = create()
    await flushPromises()
    expect(service.listConsolSnapshots).toHaveBeenCalledWith('p1')
    expect(state(w).snapshots).toHaveLength(2)
    w.unmount()
  })

  it('列表失败保留上次成功数据，只显示错误条', async () => {
    const w = create()
    await flushPromises()
    expect(state(w).snapshots).toHaveLength(2)
    service.listConsolSnapshots.mockRejectedValueOnce({ message: '网络错误' })
    await state(w).loadList()
    await flushPromises()
    // 保留旧数据
    expect(state(w).snapshots).toHaveLength(2)
    expect(state(w).listError).toContain('网络错误')
    w.unmount()
  })
})

describe('ConsolSnapshotPanel — 按钮禁用规则', () => {
  it('年度缺失：两个按钮都禁用并给中文原因', async () => {
    const w = create({ year: null })
    await flushPromises()
    expect(state(w).createDisabledReason).toBe('未设置审计年度')
    expect(state(w).signDisabledReason).toBe('未设置审计年度')
    w.unmount()
  })

  it('项目锁定：签字锁定禁用，但诊断快照仍可用（诊断不写业务数据）', async () => {
    const w = create({ readonlyReason: '项目已锁定，合并工作区仅可查看' })
    await flushPromises()
    expect(state(w).signDisabledReason).toBe('项目已锁定，合并工作区仅可查看')
    expect(state(w).createDisabledReason).toBe('')
    w.unmount()
  })

  it('归档：诊断快照与签字锁定都禁用', async () => {
    const w = create({ readonlyReason: '项目已归档，合并工作区仅可查看' })
    await flushPromises()
    expect(state(w).createDisabledReason).toContain('归档')
    expect(state(w).signDisabledReason).toContain('归档')
    w.unmount()
  })

  it('无编辑权限：诊断快照与签字锁定都禁用', async () => {
    const w = create({ readonlyReason: '当前角色没有合并工作区编辑权限' })
    await flushPromises()
    expect(state(w).createDisabledReason).toContain('权限')
    expect(state(w).signDisabledReason).toContain('权限')
    w.unmount()
  })
})

describe('ConsolSnapshotPanel — 诊断快照', () => {
  it('创建诊断快照成功 ⇒ emit created 并重新加载', async () => {
    const w = create()
    await flushPromises()
    service.listConsolSnapshots.mockClear()
    await state(w).onCreateManual()
    await flushPromises()
    expect(service.createConsolSnapshot).toHaveBeenCalledWith('p1', { year: 2025, reason: 'manual' })
    expect(messages.success).toHaveBeenCalled()
    expect(w.emitted('created')).toBeTruthy()
    expect(service.listConsolSnapshots).toHaveBeenCalled()
    w.unmount()
  })
})

describe('ConsolSnapshotPanel — 签字锁定 fail-closed', () => {
  it('成功 ⇒ emit locked + created', async () => {
    const w = create()
    await flushPromises()
    await state(w).onSignLock()
    await flushPromises()
    expect(service.createConsolSnapshot).toHaveBeenCalledWith('p1', { year: 2025, reason: 'sign' })
    expect(w.emitted('locked')).toBeTruthy()
    expect(w.emitted('created')).toBeTruthy()
    w.unmount()
  })

  it('409 拒绝 ⇒ 逐条列明原因，不当成功、不 emit locked', async () => {
    const w = create()
    await flushPromises()
    service.createConsolSnapshot.mockRejectedValueOnce({
      response: { status: 409, data: { detail: { code: 'readiness_not_ready', message: '未就绪', failures: [
        { category: 'readiness', code: 'readiness_not_ready', message: '合并 readiness 未就绪' },
        { category: 'artifact', code: 'artifact_missing', message: '正式报表产物缺失' },
      ] } } },
    })
    await state(w).onSignLock()
    await flushPromises()
    expect(msgBox.alert).toHaveBeenCalled()
    const alertBody = msgBox.alert.mock.calls[0][0] as string
    expect(alertBody).toContain('合并 readiness 未就绪')
    expect(alertBody).toContain('正式报表产物缺失')
    expect(w.emitted('locked')).toBeFalsy()
    expect(messages.success).not.toHaveBeenCalled()
    w.unmount()
  })

  it('用户取消确认 ⇒ 不调用创建', async () => {
    msgBox.confirm.mockRejectedValueOnce('cancel')
    const w = create()
    await flushPromises()
    await state(w).onSignLock()
    await flushPromises()
    expect(service.createConsolSnapshot).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('ConsolSnapshotPanel — 行操作', () => {
  it('完整性校验调用 restore 并展示结果', async () => {
    const w = create()
    await flushPromises()
    await state(w).onCheckIntegrity(V2_ITEM)
    await flushPromises()
    expect(service.restoreConsolSnapshot).toHaveBeenCalledWith('p1', 'snap-1')
    expect(state(w).integrityResult.hash_valid).toBe(true)
    expect(state(w).integrityVisible).toBe(true)
    w.unmount()
  })

  it('对比当前调用 compare 并可只看已变化', async () => {
    const w = create()
    await flushPromises()
    await state(w).onCompare(V2_ITEM)
    await flushPromises()
    expect(service.compareConsolSnapshot).toHaveBeenCalledWith('p1', 'snap-1')
    expect(state(w).compareResult.changed_count).toBe(1)
    expect(state(w).compareRows).toHaveLength(1)
    w.unmount()
  })

  it('下载走 authed 下载助手（带年度拼文件名）', async () => {
    const w = create()
    await flushPromises()
    await state(w).onDownload(V2_ITEM)
    await flushPromises()
    expect(service.downloadConsolSnapshot).toHaveBeenCalledWith('p1', 'snap-1', 2025)
    w.unmount()
  })
})

describe('ConsolSnapshotPanel — 展示辅助', () => {
  it('partial 快照展示缺失分片中文名', async () => {
    const w = create()
    await flushPromises()
    expect(state(w).failedSourcesText(PARTIAL_ITEM)).toContain('合并报表')
    expect(state(w).failedSourcesText(PARTIAL_ITEM)).toContain('不可变产物')
    expect(state(w).triggerLabel(V2_ITEM)).toBe('签字锁定')
    expect(state(w).triggerLabel(PARTIAL_ITEM)).toBe('诊断快照')
    w.unmount()
  })
})
