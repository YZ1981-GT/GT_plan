import subprocess, sys, tempfile
from pathlib import Path

def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        print("GIT FAIL:", args[:3], r.stdout[-700:], r.stderr[-700:]); sys.exit(1)
    return r

def commit(title, body, paths):
    git("add", "--", *paths)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8", newline="\n") as fh:
        fh.write(title + "\n\n" + body + "\n"); msg = fh.name
    r = git("commit", "-F", msg, "--", *paths, check=False)
    Path(msg).unlink(missing_ok=True)
    if r.returncode != 0:
        print("COMMIT FAIL:", title); print(r.stdout[-1400:], r.stderr[-1400:]); sys.exit(1)
    print(f"[{git('rev-parse','--short','HEAD').stdout.strip()}] {title}")

# ── 并发中的 D4-2 侧工作，不属本轮，排除 ─────────────────────────────────
CONCURRENT = {
    "backend/app/services/workpaper_sync/excel_materialize.py",
    "backend/tests/workpaper_sync/test_sibling_table_ref_row_shift.py",
    "backend/_d42.txt", "backend/_d42g.txt", "backend/_d42s.txt", "backend/_d42tb.txt",
    "backend/scripts/_d42_repro.py", "backend/scripts/_d42_stage.py",
}

status = [l for l in git("status", "--porcelain").stdout.split("\n") if l.strip()]
paths = []
for line in status:
    p = line[3:].strip().strip('"')
    if p in CONCURRENT:
        continue
    paths.append(p)

docs = [p for p in paths if p.startswith("docs/")]
rest = [p for p in paths if not p.startswith("docs/")]

commit("docs(evidence): suite-triage 全量取证 + 清一次性探针文件",
       """283 failed → 67 failed 的逐簇取证。每份都写清「测得什么」与「没测到什么」，
诚实红都点名 owner 与解阻条件，不用「应该」「预计」代替实测。

本轮新增 g02-g03-restore-and-eol-parse-defect.md（六节）：
DB 探针隔次失败的根因/变异检验 · G0-2/G0-3 假收口的机制与交付物 · AC matrix 的 CRLF
解析缺陷 · pilot 宿主判据重述与 4 项变异 · /d2-sync/* 退网的真实阻塞面（180 宿主 /
0 注入 forcesaveEndpoint / 结构上无法寻址统一端点）· 两次测量口径对齐与「等一次提交」的
36 条。

另附 final-rerun-2026-09-24.txt（全量 58 failed / 8659 passed / 0 errors）与
ws-rerun-after-fixes.txt（五个 workpaper_sync* 目录 67 failed / 8951 passed）原始输出，
便于离线复核逐条 diff。

顺带删掉一次性探针文件（_t13_probe.py / _t26_peek.py / _t26.txt 及四份 _ 前缀 txt）——
按仓库约定 _ 前缀即用完即删。""", docs)

commit("chore(workpaper-sync): 收拢在飞的判据修正与产物重算",
       """suite triage 期间逐簇修复的余下部分，按簇在 docs/operations/evidence/suite-triage/
各文件中已逐条留证，此处只作归集提交：

* 判据侧：stale 绝对常量改为由 live source 现算（沿用「derive from live source，never bump
  the literal」的既定先例，如 assert derived >= len(entries) * 9 // 10 并在注释里留
  186→176→155 的历史）；capability flip 后的逐 entry 快照对齐；前端结构漂移；
  AC14 honest-mode notice；task65 lane registry；task29/27/28/26/15 的 PG 侧判据。
* 产物侧：manifest / overlay / 七份 cycle slice / legacy baseline / writer inventory /
  row-change reachability / task61 probe 由各自生成器重算，未手改 JSON。
* 前端：http.ts 与 d2SyncHostWiring 判据、generated manifest/legacy baseline 投影。

刻意未纳入：并发进行中的 D4-2 侧工作（excel_materialize.py 的 _sheet_table_parts +
test_sibling_table_ref_row_shift.py + 四份 _d42* 探针），那是另一条线上的半成品，
不由本轮代为提交。""", rest)
