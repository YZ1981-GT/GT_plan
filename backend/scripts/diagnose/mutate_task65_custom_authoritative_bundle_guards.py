r"""Task 65 custom 侧守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 65
被检验的守卫：
* ``backend/tests/workpaper_sync/test_task65_custom_authoritative_bundle.py``（离线）
* ``backend/tests/workpaper_sync/test_task65_custom_authoritative_bundle_pg.py``（真实 PG）

## 为什么每条变异都不是无效变异

本任务最贵的三类缺陷各有对应变异：

1. **custom 悄悄转成 JSON projection** —— 服务层那两条「custom 通道必须交权威字节 / 不得
   带 per-entry contract」的判据，以及端点那条「交出去的是 substrate 字节而不是投影」的
   数据流判据，任一被短路都必须打红（M09~M11、M14、M18）。这是 AC 2.11 / 12.6 的全部
   约束力所在：两条判据共用 `AuthorityModelMismatchError`，所以只断言异常类型的守卫对
   短路其一是无感的 —— 本组变异证明新守卫比的是**原因文案**且互不命中。
2. **五类非法空值被合成一条判据** —— 改造前 NULL / 空串 / 全零 / 非法 hex 共用
   `BundleIntegrityError` 与共用消息，短路任一类都会被另一类抛出同类型顶上来。M01~M03
   逐类短路，M04~M06 打「首个非法 slot」的确定性（声明序 vs dict 插入序）。
3. **application key 不再冻结 bundle/authority digest** —— 把任一 digest 钉成常量，
   「相同 incoming 在不同 bundle / authority model 下」立刻折叠成同一 application
   （M07、M08），真库那半用**真实 digest** 复验同一条性质。

另有两条落在**必需步骤集合**上（M12、M13）：「custom 进入统一 representation」如果只是
一句注释，把 `representation` 从 content commit 步骤里摘掉、或塞进 html-only 步骤里，
守卫都不该有反应；打红才说明那句承诺是可执行判据。

## 刻意**不**变异的三个文件

`writer_migration.py` · `opaque_entry_gate.py` · `adapters/registry.py` 在并发会话的在途
清单里，禁并行编辑 —— 变异是「临时改写 + 复原」，与并发写同一文件会互相覆盖。因此
`test_custom_commit_passes_no_adapter_and_no_contract`（锚在 `writer_migration`）与
`test_class5_unregistered_marker_version_is_rejected_with_its_own_type`（锚在
`opaque_entry_gate`）这两条判据**本轮没有配对变异**，其强度未经变异证明；两个文件解锁后
应补 M19/M20（把 `contract=None` 改成透传、把 registry 成员判断短路成 `if False:`）。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task65_custom_authoritative_bundle_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task65_custom_authoritative_bundle_guards.py --run M01,M02
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task65_custom_authoritative_bundle_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed rc=5）；**绝不 `--restore`**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

MODELS = "backend/app/services/workpaper_sync/models.py"
CMUT = "backend/app/services/workpaper_sync/content_mutation.py"
CELLS = "backend/app/routers/custom_workpaper_cells.py"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task65_custom_authoritative_bundle.py"
_G = "test_task65_custom_authoritative_bundle_pg.py"

MUTATIONS: list[Mutation] = [
    # ═══ 一、五类非法空值：逐类短路（AC 6.19 / Task 65 正文②）═════════════════
    Mutation(
        id="M01", side="be", path=MODELS, kind="replace",
        anchor="    if value is None:",
        new="    if False:",
        want=f"{_T}::test_class2_sql_or_json_null_is_rejected_with_its_own_type",
        wants=(f"{_T}::test_the_five_classes_are_mutually_exclusive",),
        why="② SQL NULL / JSON NULL。短路后 `None` 会落进 `str(None)`（= 'None'，非空）"
            "⇒ 被「非法 hex」那条顶上来抛 `BundleSlotMalformedDigestError` —— 类型不同，"
            "所以新守卫红；旧式「只断言 BundleIntegrityError」的守卫会判 GREEN。"
            "改 `if` 而不是删 `raise`：要测的是「判断成立却不拦」这一形态，且单行替换"
            "不会把跨行 `raise` 打成 SyntaxError（那会让 pytest 报 ERROR，`-rf` 不列 ⇒ 四态误判）",
    ),
    Mutation(
        id="M02", side="be", path=MODELS, kind="replace",
        anchor="    if not str(value).strip():",
        new="    if False:",
        want=f"{_T}::test_class3_empty_string_is_rejected_with_its_own_type",
        wants=(f"{_T}::test_the_five_classes_are_mutually_exclusive",),
        why="③ 空串/纯空白。空串是一个合法但无身份的值：短路后空 slot_type 会一路走到"
            "marker 正则那条，报出的原因变成「既非 definition 也非版本化 marker」——"
            "运维照着修会去查 marker 版本，而真正的问题是那一格根本没写",
    ),
    Mutation(
        id="M03", side="be", path=MODELS, kind="replace",
        anchor='    if str(digest).strip() == "0" * 64:',
        new="    if False:",
        want=f"{_T}::test_class4_all_zero_hash_is_rejected_with_its_own_type",
        wants=(
            f"{_T}::test_the_five_classes_are_mutually_exclusive",
            f"{_T}::test_first_illegal_slot_follows_declaration_order",
        ),
        why="④ 全零 hash。`is_digest` 对全零也返回 False，所以短路这条**不会**让全零通过 ——"
            "它会被「非法 hex」接住抛另一个类型。这正是「两条判据合成一条时短路其一被另一条"
            "遮蔽」的教科书形态：唯一能锁住它的判据是「全零必须抛全零那个类型」",
    ),
    Mutation(
        id="M04", side="be", path=MODELS, kind="replace",
        anchor="    missing = [s for s in BundleSlot if s not in slots]",
        new="    missing = []",
        want=f"{_T}::test_class1_slot_omission_is_rejected_with_its_own_type",
        wants=(
            f"{_T}::test_the_five_classes_are_mutually_exclusive",
            f"{_T}::test_first_illegal_slot_follows_declaration_order",
        ),
        why="① slot omission。缺席检查失效后下一行 `slots[slot]` 抛 `KeyError` —— 一个**不带"
            "任何 AC 语义**的裸异常：调用方的 `except BundleIntegrityError` 接不住它，"
            "于是「缺席不表示可选」这条承诺在 HTTP 层表现为 500 而不是 fail-closed 拒绝",
    ),
    Mutation(
        id="M05", side="be", path=MODELS, kind="replace",
        anchor="            slot=missing[0],",
        new="            slot=missing[-1],",
        want=f"{_T}::test_first_illegal_slot_follows_declaration_order",
        why="「首个非法 slot」取成了**最后**一个。两个 slot 同时缺席时运维会照着修错的那一"
            "格，而 `pytest.raises(BundleSlotOmissionError)` 这类只看类型的判据全绿 ——"
            "这条证明 `first_illegal_slot` 是被断言的语义而不是顺手带上的字段",
    ),
    Mutation(
        id="M06", side="be", path=MODELS, kind="replace",
        anchor="    for slot in BundleSlot:",
        scope="    missing = [s for s in BundleSlot if s not in slots]",
        offset=8,
        new="    for slot in slots:",
        want=f"{_T}::test_first_illegal_slot_follows_declaration_order",
        why="逐 slot 校验改按 **dict 插入序**（`for slot in slots`）而不是 `BundleSlot` 声明序。"
            "同一份坏 bundle 在不同代码路径（repository 构造 / descriptor 构造 / 离线导入）"
            "会报出不同的「首个非法 slot」。`compute_bundle_slots_digest` 里还有一条同形的 "
            "`for slot in BundleSlot:`，故本条用 `missing = [...]` 那行相对定位而不是绝对行号",
    ),
    # ═══ 二、custom 通道结构性不得转 JSON projection（AC 2.11 / 12.6）═══════════
    Mutation(
        id="M09", side="be", path=CMUT, kind="replace",
        anchor="        if mutation.authoritative_payload is None:",
        new="        if False:",
        want=f"{_T}::test_custom_channel_refuses_a_projection_only_mutation",
        wants=(f"{_T}::test_the_two_custom_channel_reasons_do_not_overlap",),
        why="custom 通道「只交 projection、不交权威字节」被放行 ⇒ 标准结构化 JSON projection "
            "writer 就能改写 custom 的权威内容（AC 2.11 逐字禁止）。它与紧随其后的 "
            "contract 判据**共用** `AuthorityModelMismatchError`，所以只断言类型的守卫"
            "对本条无感 —— 打红证明守卫比的是原因文案",
    ),
    Mutation(
        id="M10", side="be", path=CMUT, kind="replace",
        anchor="        if plan.contract is not None:",
        new="        if False:",
        want=f"{_T}::test_custom_channel_refuses_a_per_entry_contract",
        wants=(f"{_T}::test_the_two_custom_channel_reasons_do_not_overlap",),
        why="custom bundle 携带 per-entry contract 被放行 ⇒ 「contract slot 必须是版本化 typed "
            "null marker」失守，custom 事实上变成了 projection 三方协议（AC 6.19）。"
            "与 M09 成对：两条各自可 falsify 才说明它们不是同一条判据的两种说法",
    ),
    Mutation(
        id="M11", side="be", path=CMUT, kind="replace",
        anchor="        if plan.is_projection_based:",
        new="        if False:",
        want=f"{_T}::test_projection_channel_refuses_authoritative_bytes",
        why="**反方向**：通道判别恒假之后，`projection_contract` entry 会掉进 custom 分支 ——"
            "它交的权威字节被当成合法输入，per-entry contract 与 adapter 的三步校验全被跳过。"
            "两条通道不得混用是双向的，这条锁的是另一半",
    ),
    Mutation(
        id="M12", side="be", path=CMUT, kind="replace",
        anchor='    "representation",',
        scope="CONTENT_COMMIT_STEPS: tuple[str, ...] = (",
        offset=3,
        new='    "entry_pointer",',
        want=f"{_T}::test_only_the_content_commit_lane_writes_a_representation",
        why="把 `representation` 从统一 commit 的必需步骤里摘掉（换成重复的 entry_pointer，"
            "保持元组长度不变以免被别的长度判据顺手打红）。「custom 进入统一 representation」"
            "如果只是注释，本条不该有反应；打红说明它是可执行判据",
    ),
    Mutation(
        id="M13", side="be", path=CMUT, kind="replace",
        anchor='    "current_pointer",',
        scope="HTML_ONLY_COMMIT_STEPS: tuple[str, ...] = (",
        offset=3,
        new='    "representation",',
        want=f"{_T}::test_only_the_content_commit_lane_writes_a_representation",
        why="反向：把 `representation` 塞进 html-only 步骤集 ⇒ 两条 lane 的必需步骤不再互斥，"
            "谁把 mutation 声明成 html-only 就能借那条 lane 写 representation（源码注释里"
            "明写「两个**互不重叠**的必需步骤元组才能让两条 lane 各自可 falsify」）",
    ),
    # ═══ 三、application key 必须冻结两个 digest（AC 5.5 / Property 64）════════
    Mutation(
        id="M07", side="be", path=MODELS, kind="replace",
        anchor='        _require_digest("definition_bundle_sha256", definition_bundle_sha256),',
        # 🔴 `compute_application_key` 与 `compute_frozen_request_fingerprint` 各有一份同形行；
        #    用 application key 独有的 `frozen_client_base_version_id` 相对定位。
        scope="        str(frozen_client_base_version_id),",
        offset=3,
        new='        "b" * 64,',
        want=f"{_T}::test_only_the_bundle_digest_changes_the_key",
        wants=(f"{_G}::test_the_real_frozen_identity_does_not_fold_across_bundles",),
        why="bundle digest 被钉成常量 ⇒ 它不再参与 application key。于是「相同 incoming 在"
            "不同 definition bundle 下」算出同一个 key，两次写入折叠成一次 application"
            "（AC 5.5 明令「相同 incoming 在不同 frozen base/representation/bundle/authority "
            "model 下必须产生不同 key」）",
    ),
    Mutation(
        id="M08", side="be", path=MODELS, kind="replace",
        anchor='            "authority_model_definition_sha256", authority_model_definition_sha256',
        scope="        str(frozen_client_base_version_id),",
        offset=5,
        new='            "authority_model_definition_sha256", "f" * 64',
        want=f"{_T}::test_only_the_authority_model_digest_changes_the_key",
        wants=(f"{_G}::test_the_real_frozen_identity_does_not_fold_across_bundles",),
        why="同 M07 但落在 authority model digest：custom（`custom_authoritative_ooxml`）与 "
            "opaque（`opaque_single_onlyoffice`）两条 lane 的写入会被折叠成一个 application"
            "（Property 64）。两条**分开**是刻意的 —— 合成一条时删掉其一会被另一条顶住",
    ),
    # ═══ 四、custom 端点：权威载荷与 lane 声明（AC 2.11 / 6.19）════════════════
    Mutation(
        id="M14", side="be", path=CELLS, kind="replace",
        anchor="            payload=authoritative_bytes,",
        new="            payload=grid,",
        want=f"{_T}::test_custom_endpoint_commits_the_substrate_bytes_not_a_projection",
        why="端点把**重投影结果**（`grid`，一份 JSON 投影）当权威载荷提交。这是 AC 2.11 最直接"
            "的违背形态，且四层静态检查（Volar / vitest / get_diagnostics / HEAD-swap）全查"
            "不出：`grid` 在那一行是合法名字、类型注解也没有。只有数据流判据能红 —— "
            "「源码里出现 read_bytes」这种存在性判据在本变异下照样绿",
    ),
    Mutation(
        id="M15", side="be", path=CELLS, kind="replace",
        anchor='            lane_id="custom_cells",',
        new='            lane_id="offline_upload",',
        want=f"{_T}::test_custom_endpoint_declares_lane_and_xlsx_document_type",
        why="端点声明了**别的 lane** ⇒ authority model 从 `custom_authoritative_ooxml` 静默"
            "变成 `opaque_single_onlyoffice`。改造前 `commit_bytes` 有一个带默认值的 "
            "`authority_model` 参数，正是这类静默漂移的来源；lane_id 取代它之后必须有判据"
            "锁住「声明的 lane 就是自己那条」，否则只是把同一个坑换了个参数名",
    ),
    Mutation(
        id="M16", side="be", path=CELLS, kind="replace",
        anchor="    await writer.publish_committed_events(receipt)",
        new="    await db.commit()\n    await writer.publish_committed_events(receipt)",
        want=f"{_T}::test_custom_endpoint_has_no_self_commit_and_no_version_counter",
        why="**反向变异**：端点自己 `db.commit()` ⇒ 事务边界从统一提交入口漏到 router，"
            "「bundle 与随后的 content version/representation 落在同一个业务事务里」这条"
            "单事务见证当场作废。同文件的另一个端点合法地 `db.commit()`，所以判据必须"
            "限定在函数节点内 —— 本条同时验证守卫没有退化成全文件 grep",
    ),
    Mutation(
        id="M17", side="be", path=CELLS, kind="replace",
        anchor="    grid = refresh_custom_projection(ctx.wp, sheet_name)",
        # 🔴 该行在本文件出现两次（两个端点各一次）。按 `update_custom_cells` 独有的
        #    下一行相对定位 —— 绝对行号在清 import 后会漂。
        scope="    ctx.wp.updated_by = current_user.id",
        offset=-1,
        new="    grid = refresh_custom_projection(ctx.wp, sheet_name)\n    ctx.wp.file_version += 1",
        want=f"{_T}::test_custom_endpoint_has_no_self_commit_and_no_version_counter",
        why="**反向变异**：把改造前那行「JSON projection 端点自己推进权威 xlsx 的版本计数器」"
            "加回来。它与 `commit_bytes` 推进的 `content_revision` 会各自走一套，前端拿到的 "
            "`file_version` 与真正的 business revision 分叉 ⇒ 乐观锁比对的是两个不同的数。"
            "🔴 本条同时是 M16 的对照：两条打同一个测试的**不同一半**（commit / 计数器）",
    ),
    Mutation(
        id="M18", side="be", path=CELLS, kind="replace",
        anchor="    await writer.publish_committed_events(receipt)",
        new="    await writer.commit_projection(project_id=ctx.wp.project_id, wp_id=wp_id, "
            "entry_id=entry_id, capability=\"custom\", html_data=grid, "
            "expected_revision=expected_revision)\n"
            "    await writer.publish_committed_events(receipt)",
        want=f"{_T}::test_custom_endpoint_never_calls_the_json_projection_writer",
        why="**反向变异**：端点在权威提交之后又调一次标准 JSON projection 持久化面 ⇒ 同一次"
            "请求产生两个 business revision，且第二个的内容是投影（AC 12.6「不得转为 JSON "
            "三方 projection」）。这条证明「不调 JSON projection writer」是被枚举断言的，"
            "不是靠没人写过这行代码",
    ),
]

GUARD_FILES = {
    _T: "Task 65 custom 侧离线守卫：xlsx 本体唯一权威（数据流）、不调 JSON projection "
        "writer、五类非法空值各自一型 + 首个非法 slot、两条通道双向、application key "
        "冻结两个 digest",
    _G: "Task 65 custom 侧真库守卫：生产装配面在真库上跑通一次，plan 的权威载荷/无 adapter/"
        "无 contract/published representation/三 marker slot 逐项实证，真 digest 复验不折叠",
}

if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 65 custom authoritative bundle 守卫变异检验",
            # 🔴 只跑自己的两个守卫文件：跑整目录会把并发会话在途的 12 条既存红混进差集，
            #    让四态判定不可解读。
            backend_args=[
                "backend/tests/workpaper_sync/test_task65_custom_authoritative_bundle.py",
                "backend/tests/workpaper_sync/test_task65_custom_authoritative_bundle_pg.py",
            ],
        )
    )
