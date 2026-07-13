/**
 * useJ1Integration — J1 应付职工薪酬 集成联动 composable
 *
 * 覆盖6大集成：
 * 1. EventBus: TB回写(2211期末余额) + substantive:adjudicated
 * 2. EventBus: compensation:adjusted → K8/K9联动
 * 3. cross_wp_references: J1→K8/K9
 * 4. GtIndexChip: J1→K8管理费用 / J1→K9销售费用 跳转
 * 5. 分配检查J1-7 ↔ K8/K9交叉验证
 * 6. 附注EventBus + 双模式OO
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 6.1-6.6
 */
import http from '@/utils/http'

export interface CompensationAdjustedPayload {
  accountCode: string
  sellingExpenseSalary: number   // 销售费用-薪酬 → K8
  adminExpenseSalary: number     // 管理费用-薪酬 → K9
  researchExpenseSalary: number  // 研发费用-薪酬
  productionCostSalary: number   // 生产成本-薪酬
  wpId: string
}

export function useJ1Integration(projectId: string, wpId: string, year?: string | number) {
  // ─── 6.1 TB回写 + substantive:adjudicated ──────────────────────────────

  async function writebackAndPublish(auditedEndBalance: number) {
    // TB回写 2211
    await http.post(`/api/projects/${projectId}/trial-balance/writeback`, {
      account_code: '2211',
      audited_amount: auditedEndBalance,
      year,
      source_wp_id: wpId,
    }).catch(e => console.warn('[J1] TB writeback failed:', e))

    // EventBus publish substantive:adjudicated
    await http.post(`/api/projects/${projectId}/events/publish`, {
      event_type: 'substantive:adjudicated',
      payload: {
        accountCode: '2211',
        accountName: '应付职工薪酬',
        auditedAmount: auditedEndBalance,
        wpId,
        direction: 'credit',
      },
    }).catch(e => console.warn('[J1] substantive:adjudicated publish failed:', e))
  }

  // ─── 6.2 compensation:adjusted → K8/K9 ────────────────────────────────

  async function publishCompensationAdjusted(payload: CompensationAdjustedPayload) {
    await http.post(`/api/projects/${projectId}/events/publish`, {
      event_type: 'compensation:adjusted',
      payload,
    }).catch(e => console.warn('[J1] compensation:adjusted publish failed:', e))
  }

  // ─── 6.3 cross_wp_references ──────────────────────────────────────────

  async function registerCrossWpReferences(k8WpId: string, k9WpId: string) {
    const refs = [
      { source_wp_id: wpId, target_wp_id: k8WpId, ref_type: 'salary_allocation', field: 'selling_expense_salary' },
      { source_wp_id: wpId, target_wp_id: k9WpId, ref_type: 'salary_allocation', field: 'admin_expense_salary' },
    ]
    for (const ref of refs) {
      await http.post(`/api/projects/${projectId}/cross-wp-references`, ref)
        .catch(e => console.warn('[J1] cross_wp_ref register failed:', e))
    }
  }

  // ─── 6.4 GtIndexChip 跳转辅助 ────────────────────────────────────────

  function getK8ChipConfig() {
    return { label: 'K8 销售费用', targetWpCode: 'K8', targetSheet: 'K8-1' }
  }

  function getK9ChipConfig() {
    return { label: 'K9 管理费用', targetWpCode: 'K9', targetSheet: 'K9-1' }
  }

  // ─── 6.5 分配闭合交叉验证 ─────────────────────────────────────────────

  async function crossValidateAllocation(
    j1SellingExpense: number,
    j1AdminExpense: number,
  ): Promise<{ k8Match: boolean; k9Match: boolean; k8Diff: number; k9Diff: number }> {
    // 从K8/K9读取薪酬数据做交叉验证
    let k8Match = true
    let k9Match = true
    let k8Diff = 0
    let k9Diff = 0

    try {
      const k8Res = await http.get(`/api/projects/${projectId}/events/latest`, {
        params: { event_type: 'substantive:adjudicated', account_code: '6601' },
        _silent: true,
      } as Record<string, unknown>)
      if (k8Res.data?.data?.payload?.salaryComponent !== undefined) {
        const k8Salary = Number(k8Res.data.data.payload.salaryComponent) || 0
        k8Diff = j1SellingExpense - k8Salary
        k8Match = Math.abs(k8Diff) < 0.01
      }
    } catch { /* K8 not ready */ }

    try {
      const k9Res = await http.get(`/api/projects/${projectId}/events/latest`, {
        params: { event_type: 'substantive:adjudicated', account_code: '6602' },
        _silent: true,
      } as Record<string, unknown>)
      if (k9Res.data?.data?.payload?.salaryComponent !== undefined) {
        const k9Salary = Number(k9Res.data.data.payload.salaryComponent) || 0
        k9Diff = j1AdminExpense - k9Salary
        k9Match = Math.abs(k9Diff) < 0.01
      }
    } catch { /* K9 not ready */ }

    return { k8Match, k9Match, k8Diff, k9Diff }
  }

  // ─── 6.6 附注EventBus + 双模式 ───────────────────────────────────────

  async function publishDisclosureUpdate(noteText: string) {
    await http.post(`/api/projects/${projectId}/events/publish`, {
      event_type: 'disclosure:note-text-updated',
      payload: {
        accountCode: '2211',
        accountName: '应付职工薪酬',
        noteText,
        wpId,
      },
    }).catch(e => console.warn('[J1] disclosure update publish failed:', e))
  }

  return {
    writebackAndPublish,
    publishCompensationAdjusted,
    registerCrossWpReferences,
    getK8ChipConfig,
    getK9ChipConfig,
    crossValidateAllocation,
    publishDisclosureUpdate,
  }
}
