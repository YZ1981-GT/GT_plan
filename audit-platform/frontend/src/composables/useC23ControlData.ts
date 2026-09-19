/**
 * useC23ControlData — C23 会计分录控制测试：人员核对
 *
 * 纯函数，检查样本分录的 编制人/过账人/审核人 是否在授权清单内。
 * 供 GtC23JournalControl 组件 C23-2 sheet 使用。
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 3.2
 * Requirements: 2.4, 2.5
 */

// ─── 类型定义 ───────────────────────────────────────────────

export interface AuthorizedPerson {
  name: string
  role: string  // 创建/授权/记录
}

export interface JeControlSample {
  seq: number
  voucherDate: string
  voucherNo: string
  preparer: string
  poster: string
  reviewer: string
  supportDoc: string
  approval: string
}

export interface PersonnelCheckResult {
  sample: JeControlSample
  deviation: boolean       // true if any person not in authorized list
  deviationDetails: string // 具体哪个人不在清单
}

// ─── 核心函数 ───────────────────────────────────────────────

/**
 * 人员核对：检查样本中的编制人/过账人/审核人是否在授权清单内
 *
 * 规则：
 * - 授权清单以姓名为准（不区分角色类型）
 * - 样本中任一字段（preparer/poster/reviewer）的人员不在清单内即标记偏差
 * - 空值字段（无人员）不标记偏差
 * - 姓名比对去除前后空格
 */
export function checkPersonnel(
  samples: JeControlSample[],
  authorized: AuthorizedPerson[],
): PersonnelCheckResult[] {
  // 构建授权人员姓名集合（去空格、去重）
  const authorizedNames = new Set(
    authorized
      .map(p => p.name.trim())
      .filter(name => name.length > 0),
  )

  return samples.map((sample) => {
    const deviations: string[] = []

    // 检查编制人
    const preparer = sample.preparer?.trim() || ''
    if (preparer && !authorizedNames.has(preparer)) {
      deviations.push(`编制人"${preparer}"不在授权清单`)
    }

    // 检查过账人
    const poster = sample.poster?.trim() || ''
    if (poster && !authorizedNames.has(poster)) {
      deviations.push(`过账人"${poster}"不在授权清单`)
    }

    // 检查审核人
    const reviewer = sample.reviewer?.trim() || ''
    if (reviewer && !authorizedNames.has(reviewer)) {
      deviations.push(`审核人"${reviewer}"不在授权清单`)
    }

    return {
      sample,
      deviation: deviations.length > 0,
      deviationDetails: deviations.join('；'),
    }
  })
}
