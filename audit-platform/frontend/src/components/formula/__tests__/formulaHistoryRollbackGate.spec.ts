/**
 * 公式回滚按钮的角色门控 —— 前后端权限逐值对齐守卫
 *
 * 🔴 缘起（第四轮复盘）：后端 `rollback_formula` 原先**零鉴权**（任何人可 UPDATE
 * 全局 `report_config.formula`），2026-09-28 补 `require_role(["admin","partner","manager"])`
 * 后成为权限收紧。前端若不同步门控，无权角色仍看到「一键回滚」按钮、点了必 403
 * —— 「能点但必失败」是坏体验，且让用户以为系统坏了。
 *
 * 本守卫钉死：① 前端有角色门控 ② 前端角色集合与后端 `require_role` 参数**逐值一致**。
 * 任一侧改动都会让另一侧判红。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const FRONT = resolve(__dirname, '..', 'FormulaHistoryTab.vue')
const BACK = resolve(
  __dirname, '../../../../../../backend/app/routers/formula_audit_log.py',
)

/** 去 HTML/块/行注释，防说明文字被数成真实代码 */
function stripComments(code: string): string {
  return code
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('公式回滚按钮角色门控', () => {
  const frontSrc = readFileSync(FRONT, 'utf-8')
  const frontClean = stripComments(frontSrc)

  it('前端定义了回滚角色白名单', () => {
    expect(frontClean).toMatch(/const\s+ROLLBACK_ROLES\s*=\s*\[/)
  })

  it('canRollback 先判角色再判数据条件（否则无权角色仍看到按钮）', () => {
    const m = frontClean.match(/function canRollback[\s\S]*?\n}/)
    expect(m, '未找到 canRollback').toBeTruthy()
    expect(m![0]).toContain('canRollbackByRole')
  })

  it('模板里的回滚按钮受 canRollback 门控', () => {
    const template = frontSrc.match(/<template>([\s\S]*?)\n<\/template>/)?.[1] ?? ''
    expect(template).toMatch(/v-if="canRollback\(entry\)"/)
    expect(template).toContain('一键回滚')
  })

  it('🔴 前端角色集合与后端 require_role 参数逐值一致', () => {
    const feRoles = new Set(
      (frontClean.match(/const\s+ROLLBACK_ROLES\s*=\s*\[([^\]]+)\]/)?.[1] ?? '')
        .split(',')
        .map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
        .filter(Boolean),
    )
    expect(feRoles.size).toBeGreaterThan(0)

    const backSrc = readFileSync(BACK, 'utf-8')
    // 🔴 取段两个坑（首版都踩了）：
    //   ① `split(...)[0]` 取的是函数**之前**的内容 —— 要 `[1]`，签名在 def 行之后
    //   ② 文件头注释里写了「对齐 populate-formulas（用 require_role(["admin"])）」，
    //      不剔注释会抓到说明文字里的角色集合
    const backNoComment = backSrc
      .replace(/"""[\s\S]*?"""/g, '')
      .replace(/^\s*#.*$/gm, '')
    const afterDef = backNoComment.split('async def rollback_formula')[1] ?? ''
    // 只看签名段（到函数体第一行 `):` 为止），避免抓到函数体内其他调用
    const signature = afterDef.split(/\n\):/)[0]
    const beMatch = [...signature.matchAll(/require_role\(\[([^\]]+)\]\)/g)].pop()
    expect(
      beMatch,
      `后端 rollback_formula 签名里未挂 require_role。签名段：${signature.slice(0, 300)}`,
    ).toBeTruthy()
    const beRoles = new Set(
      beMatch![1]
        .split(',')
        .map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
        .filter(Boolean),
    )

    // 后端角色必须都在前端白名单里（否则有权的人看不到按钮）
    const missingInFe = [...beRoles].filter((r) => !feRoles.has(r))
    expect(
      missingInFe,
      `后端允许但前端隐藏了按钮的角色：${missingInFe.join(', ')}`,
    ).toEqual([])

    // 前端多出的角色只允许是 signing_partner（平台把它视作 partner 的细分）
    const extraInFe = [...feRoles].filter(
      (r) => !beRoles.has(r) && r !== 'signing_partner',
    )
    expect(
      extraInFe,
      `前端显示按钮但后端会 403 的角色：${extraInFe.join(', ')}（点了必失败）`,
    ).toEqual([])
  })

  it('自检：stripComments 不误删真实代码', () => {
    expect(frontClean).toContain('ROLLBACK_ROLES')
    expect(stripComments('<!-- ROLLBACK_ROLES -->\nconst a = 1')).not.toContain(
      'ROLLBACK_ROLES',
    )
  })
})
