"""覆盖面分母 —— 把「变异全 RED」与「守卫都被反证过」拆成两个判据。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.2 · Property 21

## 为什么必须有分母

`mutate_e_cycle_guards.py` 的实测记录（2026-08-10）：**21 条变异全 RED**，但按守卫
文件逐一核对后发现 **7 个前端守卫文件从未被任何变异打红** —— 它们全绿，却从未经过
反证。「20 条变异全红」按**清单**计数，「全部守卫都被反证过」按**文件**计数，
这是两件事。补齐那 7 个缺口后该脚本才成为 11/11 的范式基准。

分母 = 调用方显式声明的守卫文件全集（本 spec 创建或扩展的守卫）。
分子 = 由各条变异的**实测失败名**反查出的文件集合（不是声明，是跑出来的）。

## 子集运行不给覆盖面结论

`--run M01,M02` 时天然只覆盖少数文件，此时输出覆盖面缺口会产生大量噪声假红。
:meth:`CoverageTally.report` 靠 ``full_run`` 参数区分。
"""

from __future__ import annotations


def guard_files_of(failed: list[str], name2file: dict[str, str]) -> set[str]:
    """把失败测试名映射回守卫文件名。

    后端失败名首段即文件名（`test_x.py::TestY::test_z`），前端 vitest 的 `fullName`
    不含文件名 —— 靠 ``name2file`` 反查，该表在每次运行时按 `testResults[].name`
    重建，故是**实测**而非声明。
    """
    out: set[str] = set()
    for n in failed:
        f = name2file.get(n)
        if f:
            out.add(f)
        elif "::" in n:
            out.add(n.split("::")[0])
    return out


class CoverageTally:
    """守卫文件覆盖面统计。

    :param guard_files: 守卫文件名 → 归属说明（例如 ``"Task 7 新建"``）。
        **必填**，且不允许为空 —— 空分母会让覆盖面结论恒成立。
    """

    def __init__(self, guard_files: dict[str, str]) -> None:
        if not guard_files:
            raise ValueError(
                "guard_files 不能为空 —— 空分母会让「守卫都被反证过」这个结论恒成立"
            )
        self.guard_files = dict(guard_files)
        self.covered: set[str] = set()

    def record(self, files: set[str] | list[str]) -> None:
        self.covered |= set(files)

    @property
    def missing(self) -> list[str]:
        return sorted(set(self.guard_files) - self.covered)

    @property
    def extra(self) -> list[str]:
        """被打红但未登记的文件（多为他 spec 守卫，作 INFO 而非错误）。"""
        return sorted(self.covered - set(self.guard_files))

    def report(self, full_run: bool) -> list[str]:
        """返回可直接打印的报告行。"""
        lines: list[str] = []
        if not full_run:
            lines.append(
                "守卫文件覆盖面：本次为子集运行，不做覆盖面结论"
                "（子集天然只覆盖少数文件，报缺口会是噪声）"
            )
            return lines
        total = len(self.guard_files)
        miss = self.missing
        lines.append(
            f"守卫文件覆盖面：{total - len(miss)}/{total} 个登记守卫文件被至少一条变异打红"
        )
        for f in miss:
            lines.append(f"  [GAP] {f}  （{self.guard_files[f]}）—— 全绿但未经反证，需补一条变异")
        if miss:
            lines.append(
                "  🔴 「变异全 RED」不等于「守卫都被反证过」："
                "前者按清单计数，后者按文件计数"
            )
        if self.extra:
            lines.append(
                f"  [INFO] 另打红 {len(self.extra)} 个未登记文件"
                f"（多为他 spec 守卫）：{self.extra[:6]}"
            )
        return lines

    def is_complete(self, full_run: bool) -> bool:
        """全量运行且无缺口时为 True（供退出码判定）。"""
        return full_run and not self.missing
