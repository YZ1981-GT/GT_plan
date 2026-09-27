"""H 循环双向回写的类型门 —— 按「归属文件」判定，而不是按总数。

spec: `h-cycle-sync-foundation-and-first-canary`

═══ 为什么需要这个脚本，而不是直接看 `vue-tsc` 退出码 ═══════════════════════════

本 spec 的类型面包含 **H 循环各宿主 `.vue`**（见 `HOST_FILES`）。把 `.vue` 宿主纳入
type-check 会把整个应用的传递依赖图一起拉进来（stores / eventBus / 其它循环的 Tab），
而那张图**当前不是类型干净的**：总错误数三位数且**随并发会话漂移**（本轮现算 116），
绝大多数与本 spec 无关（`src/stores/project.ts` 的 eventBus 事件名、
`noteDisclosureReverseJump.ts` 的变体类型、`GtAProgramConsole` 的 prop 名等）。
⇒ 总数**故意不设阈值**（设了就会被别人的改动打红，等于没门）；设阈值的只有
  「本 spec 拥有的文件」和「逐宿主」两个面。

仓库既有的 per-spec tsconfig 全都**只列 `.ts` 文件、不列 `.vue` 宿主**，正是为了绕开这个
问题。但绕开的代价是宿主完全不被类型检查 —— 本轮实测代价具体化了：接桥时删掉宿主内联的
`checkOoHealth()` 实现却漏删 `onMounted` 里的调用，**只有把宿主纳入 type-check 才会报**
（`TS2304: Cannot find name 'checkOoHealth'`）。那正是这个门要守的东西。

⇒ 折中：宿主留在 tsconfig 里（保住这道网），但判定改为「**归属本 spec 的文件必须零错误**
  + 宿主自身错误数不得超过钉死的既有基线」。既不因无关的 30 条把门永久卡红（那等于没门），
  也不靠删 include 把宿主藏起来（那等于放弃这道网）。

🔴 基线只能往下调，不许往上调：调高就是「新错误被基线吸收」。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2].parent / "audit-platform" / "frontend"
TSCONFIG = "tsconfig._h-cycle-sync.json"

#: 本 spec **拥有**的文件（新增或改动）—— 必须零类型错误，无基线豁免。
OWNED = (
    "composables/useHSyncMode.ts",
    "sync/hManagedSheets.ts",
    "sync/onlyOfficeHealth.ts",
    "composables/hSeedRowIdentity.ts",
    "composables/useH2Detail.ts",
    "composables/useH3FormData.ts",
    "composables/useH5FormData.ts",
    "composables/useH10FormData.ts",
    "composables/useH10Adjustment.ts",
    "sync/hPendingWrites.ts",
    "d4/composables/useD4SyncMode.ts",
)

#: 宿主自身错误的既有基线。
#:
#: 当前 1 条 = `GtH9LeaseLiabilities.vue(79,10) TS2345`：模板把 `sheet-code="H9A"` 传给
#: `GtAProgramConsole`（实为 `GtCycleAProgramRouter.vue`，声明的必填 prop 是 `sheetName`）。
#: 🔴 **不是本轮引入**：`sheet-code="` 在 `workpaper/Gt*.vue` 里现算 36 处，跨 E1/F1/… 多个
#:    循环，属其它 spec 的作业面（且可能是真实缺陷：prop 名不匹配，运行时靠 attrs 透传）。
#:    已登记上报，本轮不动 —— 跨 36 处宿主的 prop 改名会与并发会话正面冲突。
#:
#: H6 宿主同理：`sheet-code="H6A"` 传 `GtAProgramConsole` 同一形态 ⇒ 基线各 1。
HOST_FILES: tuple[str, ...] = (
    "GtH9LeaseLiabilities.vue",
    "GtH6AssetDisposalClearing.vue",
    "GtH8RightOfUseAssets.vue",
    "GtH4EngineeringMaterials.vue",
    "GtH2ConstructionInProgress.vue",
    "GtH3InvestmentProperty.vue",
    "GtH5OilGasAssets.vue",
    "GtH7BiologicalAssets.vue",
    #: H7 的两张受管明细表是 `per_tab_self_persisting` 载体，键与行模型内联在 Tab 里
    #: ⇒ 接桥必须改它们（`trackHPendingWrite`）。纳入类型面，逐个现算基线。
    "H7TabDetailCost.vue",
    "H7TabDetailFair.vue",
    "GtH10AssetDisposalIncome.vue",
)
#: 🔴 逐宿主基线按**现算**填，不照抄别的宿主。
#:
#: * H9 / H6 各 **1** 条：`sheet-code="…"` 传 `GtAProgramConsole`（其必填 prop 是
#:   `sheetName`）。该 pattern 全仓 `workpaper/Gt*.vue` 现算 36 处、跨 E1/F1/… 多循环，
#:   属其它 spec 作业面，已上报未动。
#: * H8 **8** 条 —— 首次纳入类型检查时现算，逐条核对过**都在本轮 diff hunk 之外**：
#:     L89  `sheet-code` 传 GtAProgramConsole（同 H9/H6 那条）
#:     L735 `inject<(id, label?) => void>('openReviewDialog', undefined)`
#:          —— 默认值 `undefined` 不满足声明的函数类型
#:     L776/778/779/783/785/786 共 6 条 `eventBus.on/off('tb:updated' /
#:          'substantive:adjudicated' / 'h9:liability-updated' /
#:          'h9:lease-payment-updated', …)` —— 这些事件名**未在 eventBus 的 `Events`
#:          类型里声明**，与 `src/stores/project.ts` 的 `'sse:disconnect'` 同族缺陷。
#:   🔴 基线填 8 不是放宽：本轮新增任何一条类型错误都会顶到 9 而打红。
#:   这 8 条本身是**真实缺陷**（eventBus 事件名缺声明会让事件改名时无人报错），
#:   但跨宿主/跨循环，登记上报不在本轮范围。
HOST_ERROR_BASELINE: dict[str, int] = {
    "GtH9LeaseLiabilities.vue": 1,
    "GtH6AssetDisposalClearing.vue": 1,
    "GtH8RightOfUseAssets.vue": 8,
    #: H4 **1** 条（现算）：L62 `sheet-code` 传 GtAProgramConsole —— 与 H9/H6 同一条，
    #: 在本轮 diff hunk 之外。H4 没有 H8 那 7 条（其宿主不用 eventBus.on/off，
    #: 也没有 `inject(..., undefined)`）⇒ 逐宿主基线确实不能照抄。
    "GtH4EngineeringMaterials.vue": 1,
    #: H2 **0** 条 —— 五个宿主里唯一的零基线，且是现算值不是乐观填的。
    #: 没有 H9/H6/H4 那条 `sheet-code` 错误的原因是**结构性**的：H2 程序表走
    #: `shared/CycleTabProcedure.vue`（其 prop 确实声明为 `sheetCode`），
    #: 不是 `GtAProgramConsole`（声明的是 `sheetName`）。
    #: 正向对照已做：在本宿主植入一条 `const x: number = 'y'`，门当场报
    #: `GtH2ConstructionInProgress.vue(350,7) TS2322` 并打红 ⇒ 0 是「真检查过且干净」，
    #: 不是「文件没被编译的假绿」。
    "GtH2ConstructionInProgress.vue": 0,
    "GtH3InvestmentProperty.vue": 0,
    #: H5 / H7 及 H7 两张受管 Tab —— 先填 0 跑一次现算再回填（脚本对「低于基线」会
    #: 打印下调提示，对「高于基线」直接打红 ⇒ 乐观填 0 不会静默放过真实新增错误）。
    "GtH5OilGasAssets.vue": 0,
    "GtH7BiologicalAssets.vue": 0,
    "H7TabDetailCost.vue": 0,
    "H7TabDetailFair.vue": 0,
    #: H10 —— 先填 0 跑一次现算再回填（同上）
    "GtH10AssetDisposalIncome.vue": 0,
}

_ERR_RE = re.compile(r"^(?P<file>[^(]+)\((?P<line>\d+),\d+\): error (?P<code>TS\d+)")


def main() -> int:
    tsc = FRONTEND / "node_modules" / ".bin" / (
        "vue-tsc.cmd" if sys.platform == "win32" else "vue-tsc"
    )
    if not tsc.exists():
        print(f"🔴 找不到 vue-tsc：{tsc}（先在 {FRONTEND} 下 npm install）")
        return 1
    proc = subprocess.run(
        [str(tsc), "--noEmit", "-p", TSCONFIG],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    raw = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", proc.stdout + proc.stderr)
    errors = [m for m in (_ERR_RE.match(ln) for ln in raw.splitlines()) if m]

    owned_errs = [m.group(0) for m in errors if any(o in m.group("file") for o in OWNED)]

    print(f"vue-tsc 总错误数：{len(errors)}（含无关的传递依赖图）")
    print(f"本 spec 拥有文件错误数：{len(owned_errs)}（要求 0）")

    failed = False
    if owned_errs:
        failed = True
        print("\n🔴 本 spec 拥有的文件出现类型错误：")
        for e in owned_errs:
            print(f"   {e}")

    for host in HOST_FILES:
        host_errs = [m.group(0) for m in errors if host in m.group("file")]
        baseline = HOST_ERROR_BASELINE[host]
        print(f"宿主 {host} 错误数：{len(host_errs)}（基线 {baseline}）")
        if len(host_errs) > baseline:
            failed = True
            print(f"\n🔴 {host} 错误数超出基线（新增 {len(host_errs) - baseline} 条）：")
            for e in host_errs:
                print(f"   {e}")
        elif len(host_errs) < baseline:
            print(
                f"✅ {host} 低于基线（{len(host_errs)} < {baseline}）"
                f" —— 请把 HOST_ERROR_BASELINE[{host!r}] 下调到 {len(host_errs)}。"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
