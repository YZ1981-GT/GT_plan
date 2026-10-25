"""变异检验：Excel 模板覆盖层 + OnlyOffice 模板编辑器（T5 / Task 23）。

spec: .kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/
Requirements: 1.4

## 归属说明（为什么这个文件现在才建）

本文件在 5-lane 分工书（`docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md`）
§2 里划给 lane **E**（`backend/scripts/diagnose/mutate_*.py` 归 E），而 tasks.md 的文件记号表
把它列为 T5（lane D 的产物）。D 在 §12.5 登记了这处冲突、按规则 1 让路、用一次性 tmp 脚本
完成 Task 5 要求的那次变异检验（结论 RED，脚本按规则 8 已清理），并「请 A 确认口径」。

D lane 已于 2026-09-04 / 09-05 收口（§12.8 / §12.13），而该口径**至今无确认记录**
⇒ Task 23 长期停在 `[-]`。2026-09-30 现算后接手，依据三条：

1. `_mutation_kit` 已成熟（9 个模块）且 **89 / 186** 个 mutate 脚本已采纳 —— 分工书 §10.3
   当时记的是「E 已交 1 个」。用 kit 范式建**不产生**新的待迁移债务（这正是当初让路时
   最该担心的那件事：按老范式建会立刻变成第 21 个待迁移项，让那个 CI job 红得更久）。
2. 变异清单与预期态由 D 在 tasks.md Task 23 里列全了（六类结构性判据），不需要重新设计。
3. D 移交的三条必守项（§12.7）在本文件逐条落实，见下。

## D 移交的三条必守项（§12.7）落实情况

① **预期信号写异常类名，不写 `error_code`** —— pytest traceback 打印的是类名
   （`OverrideRootEscapeError`），`error_code` 是类属性值（`template_override_root_escape`），
   写后者会把真 RED 误判成 WRONG-TEST。本文件的 `want` 一律写 **测试节点 id**，
   由 kit 的 `judge()` 按 nodeid 匹配，从根上避开这个坑。
② **必须 `read_bytes` / `write_bytes`** —— `core.autocrlf=true` 下 `write_text` 会把 LF
   写成 CRLF、还原后 md5 必然不一致、报假 FATAL。kit 的 `apply.py` / `anchor.py` 已按字节
   处理并自带 md5 还原核验，本文件不自行读写文件。
③ **import 期断言的变异形态是收集期 ERROR（炸整个模块）而非单条 FAILED** —— 不算
   WRONG-TEST。M02 因此用 `wants` 给出多个预期信号，「同时命中」即判 RED。

## 不可变异的一条（如实登记，不假装覆盖）

Task 23 清单里的 **V154 部分唯一索引 COALESCE**（`TestProperty18ConcurrentCurrentVersion`）
无法用本脚本变异：索引由 `backend/migrations/V154__*.sql` 建，改 SQL 文件不会让**已应用**
的索引改变（迁移按 version 去重、不重跑），变异后判据照常绿 ⇒ 那会是一条**假 GREEN**，
比没有更糟。它的保护由 `test_the_partial_unique_index_really_exists`（真库现查索引存在）
＋ `TestProperty18ConcurrentCurrentVersion`（真库并发实测）承担。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

SVC = "backend/app/services/wp_template_override.py"

# 守卫文件用**纯文件名**：kit 的 `guard_files_of` 从 pytest 失败名首段反查文件，
# `--list` 又按 DEFAULT_GUARD_ROOTS（`backend/tests` / `audit-platform/frontend/src`）
# 校验它们真的存在 —— 给完整仓库相对路径会被拼成 `backend/tests/backend/tests/…` 而找不到。
_GATES = "test_template_override_write_gates.py"
_RESO = "test_template_override_resolution.py"
_LOSS = "test_template_override_lossless.py"

_TESTS_DIR = "backend/tests/workpaper_sync"


MUTATIONS = [
    # ── 一、Property 5：覆盖层根与权威目录互不包含（三形态）───────────────────
    Mutation(
        id="M01", side="be", path=SVC, kind="replace",
        anchor="    if _is_within(override, authoritative):",
        new="    if False and _is_within(override, authoritative):",
        want=f"{_GATES}::TestProperty5RootDisjoint::test_override_root_as_descendant_raises",
        why="「覆盖层根是权威目录后代」这一形态不再抛：此时每次覆盖层写入都是写权威目录，"
            "Requirement 1.1 结构性失守。三形态必须逐条可达 —— 只保留「相等」那条会漏掉"
            "最可能真发生的一种（有人把覆盖层设成 wp_templates/overrides）。",
    ),
    Mutation(
        id="M02", side="be", path=SVC, kind="replace",
        anchor="    if _is_within(authoritative, override):",
        new="    if False and _is_within(authoritative, override):",
        want=f"{_GATES}::TestProperty5RootDisjoint::test_override_root_as_ancestor_raises",
        why="「覆盖层根是权威目录祖先」不再抛：覆盖层的清理/回滚会波及权威基线。"
            "与 M01 分成两条而不是合一，是因为两个分支各覆盖一个独立方向 ——"
            "合并变异时只要有一条判据红就看不出另一个方向有没有被保护。",
    ),

    # ── 二、import 期断言真的执行（必守项③：形态是收集期 ERROR）──────────────
    Mutation(
        id="M03", side="be", path=SVC, kind="replace",
        anchor="assert_override_root_disjoint_from_authoritative()",
        new="pass  # mutation: 不在 import 期断言",
        want=f"{_GATES}::TestImportTimeAssertion::test_module_body_calls_the_assertions",
        why="把 import 期调用摘掉：函数还在、判据还能自己调它通过，但真实接线错误"
            "（有人改了 OVERRIDE_ROOT 常量）不再于 import 期暴露，要等某个请求真去写盘。"
            "这条是**单条 FAILED**形态（AST 扫不到模块级调用）。",
    ),
    Mutation(
        id="M04", side="be", path=SVC, kind="replace",
        anchor='OVERRIDE_ROOT: Final[Path] = BACKEND_DIR / "storage" / "template_overrides"',
        new='OVERRIDE_ROOT: Final[Path] = BACKEND_DIR / "wp_templates" / "overrides"',
        want="*",
        why="🔴 **必守项③的形态样本**：把覆盖层根改成权威目录的后代 ⇒ import 期断言真的抛 ⇒ "
            "整个模块 import 失败 ⇒ 三个守卫文件全部变**收集期 ERROR**。"
            "按 §12.7 第三条这不算 WRONG-TEST，但**也不能写方法级 nodeid 当预期信号** —— "
            "收集期错误的名字是**文件级**的（`test_x.py` 而非 `test_x.py::Cls::method`），"
            "写方法级会一条都匹配不上而判假 GREEN（首轮实测踩到）。故按 kit 的约定显式写 "
            '`want=\"*\"`（任何新增失败即 RED），并靠 `-rfE` 让 ERROR 行真的进摘要。',
    ),

    # ── 三、越界门必须用 resolve 后的路径（否则只是装饰）─────────────────────
    Mutation(
        id="M05", side="be", path=SVC, kind="replace",
        anchor="    return resolved",
        new="    return target",
        want=f"{_GATES}::TestProperty1RootEscapeGate::test_inside_root_passes_and_returns_resolved",
        why="门返回**原始未 resolve** 的路径：检查本身还在做，但调用方拿回去落盘的是"
            "没解过 `..` 与符号链接的路径 ⇒ 这道门退化成装饰（docstring 原话："
            "「若用原始未 resolve 的路径写盘，这道门就只是个装饰」）。"
            "🔴 首轮用的锚点 `root = OVERRIDE_ROOT.resolve()` 是**无效变异**："
            "测试环境下 `OVERRIDE_ROOT` 路径本身不含符号链接，去掉 `.resolve()` 行为不变，"
            "判据照常绿 —— 换成返回值这条才真的改变可观测行为。",
    ),

    # ── 四、CURRENT_METADATA_SUFFIXES 双向锁死 ──────────────────────────────
    Mutation(
        id="M06", side="be", path=SVC, kind="replace",
        anchor="CURRENT_METADATA_SUFFIXES: Final[frozenset[str]] = frozenset({CURRENT_VERSION_MARKER_SUFFIX})",
        new='CURRENT_METADATA_SUFFIXES: Final[frozenset[str]] = frozenset({CURRENT_VERSION_MARKER_SUFFIX, ".bogus"})',
        want=f"{_GATES}::TestProperty16And17VersionChain::test_metadata_suffixes_cover_what_activate_writes",
        why="**双向**锁死的反方向：多登记一个从来不写的后缀。少登记会让一致性检查把元数据"
            "文件当成第二个 current 模板（误报）；多登记会让真正的杂项文件被静默忽略"
            "（漏报）。只测一个方向的判据挡不住另一个方向。",
    ),

    # ── 五、Property 2：AST 扫描器 —— 写入目标位不得出现权威目录 ──────────────
    Mutation(
        id="M07", side="be", path=SVC, kind="replace",
        anchor="    versions_dir.mkdir(parents=True, exist_ok=True)",
        new="    (AUTHORITATIVE_ROOT / VERSIONS_DIRNAME).mkdir(parents=True, exist_ok=True)",
        want=f"{_GATES}::TestProperty2NoAuthoritativeInWriteTargets::test_write_targets_never_mention_authoritative_root",
        why="把**写入调用的接收者**换成权威目录：运行时会被越界门拦下（Property 1），"
            "但 AST 判据的价值在于**更早**发现 —— 代码审查阶段就看见有人把权威目录写进了"
            "写入目标，而不是等某次请求撞上 500。"
            "🔴 首轮把锚点选成 `assert_target_within_override_root(AUTHORITATIVE_ROOT / …)` "
            "判成 **WRONG-TEST**：那不是写入调用，而扫描器只看四类写入形态"
            "（`_WRITE_ATTRS` 的方法接收者 / `os.replace` 第二参 / `shutil.copy*` 第二参 / "
            "`open(..., 'w')` 第一参）⇒ 变异必须落在它真正扫的位置上。",
    ),

    # ── 六、Property 15：落盘路径不得出现有损中间层 ─────────────────────────
    Mutation(
        id="M08", side="be", path=SVC, kind="insert",
        anchor="import zipfile",
        new="import openpyxl  # mutation: 引入有损中间层",
        want=f"{_LOSS}::TestProperty15NoLossyIntermediateLayer::test_write_path_modules_do_not_import_lossy_layers",
        why="在落盘路径可达的模块里 import openpyxl：openpyxl 读写会丢 VBA、printerSettings、"
            "自定义 XML 部件等它不认识的 zip 部件 —— 覆盖层的全部价值就是**字节级**保真，"
            "一旦有人图方便用它改一格，模板的打印设置与宏就静默蒸发。"
            "用 `insert`（new 可多行）而不是 `replace`：`anchor` 必须单行，"
            "而这条变异要**新增**一行而不是改掉某行。",
    ),

    # ── 七、pageSetup 业务属性集合与设备属性集合不相交（Property 20）──────────
    Mutation(
        id="M09", side="be", path=SVC, kind="replace",
        anchor='    "blackAndWhite", "draft", "firstPageNumber", "useFirstPageNumber",',
        new='    "blackAndWhite", "draft", "firstPageNumber", "useFirstPageNumber", "horizontalDpi",',
        want=f"{_LOSS}::TestProperty20PageSetupDiffIsSound::test_device_bound_attrs_are_excluded_from_comparison",
        why="把设备绑定属性 `horizontalDpi` 混进业务属性集合：OO 往返必然改写它"
            "（实测显式写 600）⇒ 每次保存都报一条假差异 ⇒ 真差异被噪声淹没，"
            "这道观测手段就等于关掉了。两集合不相交必须由判据锁死，不能只靠注释。",
    ),

    # ── 八、xlsm 仍在可编辑集合之外（Gate 3 现状锚点）────────────────────────
    Mutation(
        id="M10", side="be", path=SVC, kind="replace",
        anchor='EDITABLE_FORMATS: Final[frozenset[str]] = frozenset({".xlsx"})',
        new='EDITABLE_FORMATS: Final[frozenset[str]] = frozenset({".xlsx", ".xlsm"})',
        want=f"{_GATES}::TestOverrideConstants::test_editable_formats_excludes_xlsm",
        wants=(
            f"{_GATES}::TestProperty9ExtensionGate::test_xlsm_rejected_for_in_browser_edit",
        ),
        why="放开 xlsm 浏览器内编辑。技术上 VBA 两条路径都已证实保留（tasks.md Task 103），"
            "但这是**产品口径决策**（宏模板要不要让人在浏览器里改）⇒ 现状必须被锁住。"
            "Task 103 原话：「上面两条一绿，下一个读它的人很容易顺手把 xlsm 加进去」——"
            "这条变异就是那句担心的可执行形式。",
    ),
]


#: 覆盖面分母 —— kit 必填。列全本 spec 的守卫文件，缺一个就等于默认「那个文件不用被变异覆盖」。
GUARD_FILES = {
    _GATES: "Wave 1~5 写入门与版本链（Property 1/2/5/9/16/17/18/19/22/23 + Task 101 备份面）",
    _RESO: "Wave 1~2 解析与作用域优先级（Property 3/6/7/8 + Task 24 范围边界）",
    _LOSS: "Wave 3~6 无损往返（Property 10~15/20 + Task 103 xlsm VBA 与 pageSetup）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                f"{_TESTS_DIR}/{_GATES}",
                f"{_TESTS_DIR}/{_RESO}",
                f"{_TESTS_DIR}/{_LOSS}",
                # `-rfE`：E 不能少 —— kit 的 run_pytest 同时按 `^FAILED` 与 `^ERROR` 收名，
                # 而只给 `-rf` 时 pytest 的 short summary **不打印 ERROR 行** ⇒ 收集期
                # 失败（整模块 import 炸，正是 M04 的形态）收不到任何名字 ⇒ 判成假 GREEN。
                "-q", "--tb=no", "-rfE", "-p", "no:randomly",
            ],
            baseline_backend_passed=129,
        )
    )
