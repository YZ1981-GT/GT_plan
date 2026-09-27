"""H 循环双向回写的类型门 —— 按「归属文件」判定，而不是按总数。

spec: `h-cycle-sync-foundation-and-first-canary`

═══ 为什么需要这个脚本，而不是直接看 `vue-tsc` 退出码 ═══════════════════════════

本 spec 的类型面包含 **`GtH9LeaseLiabilities.vue` 宿主**。把 `.vue` 宿主纳入
type-check 会把整个应用的传递依赖图一起拉进来（stores / eventBus / 其它循环的 Tab），
而那张图**当前不是类型干净的**：现算 30 条错误，分布在 14 个文件，全部与本 spec 无关
（`src/stores/project.ts` 的 eventBus 事件名、`noteDisclosureReverseJump.ts` 的变体类型、
`GtAProgramConsole` 的 prop 名等）。

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
    "d4/composables/useD4SyncMode.ts",
)

#: 宿主自身错误的既有基线。
#:
#: 当前 1 条 = `GtH9LeaseLiabilities.vue(79,10) TS2345`：模板把 `sheet-code="H9A"` 传给
#: `GtAProgramConsole`（实为 `GtCycleAProgramRouter.vue`，声明的必填 prop 是 `sheetName`）。
#: 🔴 **不是本轮引入**：`sheet-code="` 在 `workpaper/Gt*.vue` 里现算 36 处，跨 E1/F1/… 多个
#:    循环，属其它 spec 的作业面（且可能是真实缺陷：prop 名不匹配，运行时靠 attrs 透传）。
#:    已登记上报，本轮不动 —— 跨 36 处宿主的 prop 改名会与并发会话正面冲突。
HOST_FILE = "GtH9LeaseLiabilities.vue"
HOST_ERROR_BASELINE = 1

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
    host_errs = [m.group(0) for m in errors if HOST_FILE in m.group("file")]

    print(f"vue-tsc 总错误数：{len(errors)}（含无关的传递依赖图）")
    print(f"本 spec 拥有文件错误数：{len(owned_errs)}（要求 0）")
    print(f"宿主 {HOST_FILE} 错误数：{len(host_errs)}（基线 {HOST_ERROR_BASELINE}）")

    failed = False
    if owned_errs:
        failed = True
        print("\n🔴 本 spec 拥有的文件出现类型错误：")
        for e in owned_errs:
            print(f"   {e}")
    if len(host_errs) > HOST_ERROR_BASELINE:
        failed = True
        print(f"\n🔴 宿主错误数超出基线（新增 {len(host_errs) - HOST_ERROR_BASELINE} 条）：")
        for e in host_errs:
            print(f"   {e}")
    if len(host_errs) < HOST_ERROR_BASELINE:
        print(
            f"\n✅ 宿主错误数低于基线（{len(host_errs)} < {HOST_ERROR_BASELINE}）"
            f" —— 请把 HOST_ERROR_BASELINE 下调到 {len(host_errs)}。"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
