"""修 M/J 循环披露同步的双重错误：不存在的模块 + 不存在的端点。

## 缺陷（2026-08-12 由 I 循环 spec 的零回归验证发现）

`vite_transform_smoke.mjs` 报 35 个文件 transform 崩溃，唯一错因
``Failed to resolve import "@/utils/request"`` —— **该模块全库不存在**
（`git log --all` 也查无记录，从未存在过；正确的是 `@/utils/http`）。

深查发现是**双重错误**，改 import 只解决一半：

1. **模块不存在**：``const { default: request } = await import('@/utils/request')``
   在运行时抛 `Failed to fetch dynamically imported module`，
   而调用点包在 ``catch { /* fail-open */ }`` 里 ⇒
   **「同步到附注」静默完全失效**（用户点了、没报错、什么都没发生）。
   这比白屏更隐蔽 —— 白屏至少有人报障。
2. **端点不存在**：URL 写的是 ``/api/workpapers/{wpId}/sync-from-workpaper``，
   而后端**没有这个路由**。全库 `sync-from-workpaper` 只有三个真实端点：
   · ``/api/projects/{pid}/disclosure-notes/sync-from-workpaper``（附注同步，canonical，121 处在用）
   · ``/api/projects/{pid}/adjustments/sync-from-workpaper``（集中调整）
   · ``/api/trial-balance/{pid}/{year}/sync-from-workpaper``（试算表）
   即使修好 import，也会 404。

## 为什么现有守卫没拦住

`disclosureSyncUrlContract.spec.ts` 的判据是
``含 sync-from-workpaper + /api/ + disclosure-notes 但不含 canonical 子串 → 违规``。
而**走错端点的调用恰恰不含 `disclosure-notes`** ⇒ 被
``if (!line.includes('disclosure-notes')) return`` 放过。
这是循环论证：用「已经写对了一半」来识别「需要检查的对象」。
（该判据缺陷已在本次一并修正，见 `disclosureSyncUrlContract.spec.ts`。）

## 修法

- ``await import('@/utils/request')`` → 顶层 ``import http from '@/utils/http'``
  （动态 import 本无必要 —— 这些文件的同步函数是常规路径，不是懒加载分支）
- URL → canonical ``/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper``
- payload **无需改**：7 个 M 循环的 `M*SyncPayload` 字段实测已与后端
  `SyncFromWorkpaperRequest` 完全匹配（`wp_id`/`sheet_name`/`section_id`/
  `current_standard`/`sub_table_data`/`columns`）
- 保留 ``catch`` 的 fail-open 语义（不改错误处理策略，只让请求真能发出去）

幂等：已修过的文件跳过。``--check`` 只报不改。

spec: 由 .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 22 发现，
      修复属 M/J 循环域（跨域缺陷，就地修比登记等待更安全 —— 它让附注同步静默失效）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: 🔴 本文件在 `backend/scripts/fix/` ⇒ 仓库根是 parents[3]（parents[2] 只到 `backend/`）。
#:    首版写 parents[2] 导致 rglob 扫的是不存在的 `backend/audit-platform/...`，
#:    脚本报「无待修文件」而实际 13 处未修 —— 典型的「路径算错 = 静默空扫」。
_ROOT = Path(__file__).resolve().parents[3]
_WP = _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
assert _WP.is_dir(), f"底稿目录不存在，_ROOT 算错了：{_WP}"

CHECK = "--check" in sys.argv

_BAD_MODULE = "@/utils/request"
_BAD_URL_RE = re.compile(
    r"`/api/workpapers/\$\{props\.wpId\}/sync-from-workpaper`"
)
_GOOD_URL = "`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`"


def fix_one(path: Path) -> tuple[bool, list[str]]:
    """返回 (是否改动, 说明)。"""
    src = path.read_text(encoding="utf-8")
    notes: list[str] = []
    out = src

    if _BAD_MODULE not in out and not _BAD_URL_RE.search(out):
        return False, ["已修（跳过）"]

    # ① 动态 import 行 → 删除（改用顶层 http）
    dyn = re.compile(
        r"[ \t]*const \{ default: request \} = await import\('@/utils/request'\)\r?\n"
    )
    if dyn.search(out):
        out = dyn.sub("", out)
        notes.append("删动态 import('@/utils/request')")

    # ② request.post → http.post
    if re.search(r"\brequest\.post\(", out):
        out = re.sub(r"\brequest\.post\(", "http.post(", out)
        notes.append("request.post → http.post")

    # ③ URL → canonical
    if _BAD_URL_RE.search(out):
        out = _BAD_URL_RE.sub(_GOOD_URL, out)
        notes.append("URL → canonical /api/projects/{pid}/disclosure-notes/…")

    # ④ 顶层补 `import http from '@/utils/http'`（若缺）
    if "http.post(" in out and not re.search(
        r"^import http from '@/utils/http'", out, re.M
    ):
        m = list(re.finditer(r"^import [^\n]*$", out, re.M))
        if not m:
            return False, ["🔴 无 import 行，无法插入 http"]
        ins = m[-1].end()
        out = out[:ins] + "\nimport http from '@/utils/http'" + out[ins:]
        notes.append("补 import http")

    if out == src:
        return False, ["无变化"]
    if not CHECK:
        path.write_text(out, encoding="utf-8")
    return True, notes


def main() -> int:
    targets = sorted(
        p for p in _WP.rglob("*.vue")
        if _BAD_MODULE in p.read_text(encoding="utf-8", errors="replace")
        or _BAD_URL_RE.search(p.read_text(encoding="utf-8", errors="replace"))
    )
    if not targets:
        print("无待修文件（已全部收敛）")
        return 0

    print(f"{'[--check] ' if CHECK else ''}待修 {len(targets)} 个文件")
    changed = 0
    failed: list[str] = []
    for p in targets:
        ok, notes = fix_one(p)
        rel = p.relative_to(_WP)
        if ok:
            changed += 1
            print(f"  ~ {rel}")
            for n in notes:
                print(f"      · {n}")
        else:
            print(f"  = {rel}: {notes}")
            if any("🔴" in n for n in notes):
                failed.append(str(rel))

    print(f"\n{'待改' if CHECK else '已改'} {changed} 个；失败 {len(failed)}")
    for f in failed:
        print(f"  🔴 {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
