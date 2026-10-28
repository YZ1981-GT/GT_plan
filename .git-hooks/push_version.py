#!/usr/bin/env python3
"""推送版本标记：pre-push 钩子校验 + 打版本标签 / 推送工具（单文件，只用标准库）。

规则（2026-10-27 用户要求：推送时要标记版本号和变动的主要内容）
- 推送带新提交的分支时，分支最新提交上必须有附注标签 vX.Y.Z，并与分支同一次推送（远端已有指向
  该提交的版本标签也算）；标签说明里要有「主要变动：」段，至少一条要点，每条至少 4 个字。
- 版本号只能往上走：新标签必须大于远端已有的最大版本号；远端已有同名标签 = 版本号被别人先用了。
- 不带新提交的推送（新建分支指向远端已有提交、删除分支、只推标签等）不要求版本标签；「新提交」=
  远端任何分支上都还没有的提交（恢复已删分支时，远端已经没有的提交同样算新提交）。
- 起点：远端 dev1.0 分支（2026-10-27 他人所建，用来标记版本）= 1.0，默认每次推送修订号 +1；
  换次版本 / 大版本用 --bump minor / --bump major。

用法（在要推送的工作树里执行；分离头 worktree 里加 --branch）：
    python .git-hooks/push_version.py push -c "主要变动一" -c "主要变动二"
    python .git-hooks/push_version.py push --notes-file 变动.txt       # UTF-8，每行一条
    python .git-hooks/push_version.py push --branch spec/xxx -c "…"    # 分离头 worktree
    python .git-hooks/push_version.py push --dry-run -c "…"            # 只看版本号和标签说明
    python .git-hooks/push_version.py next                              # 下一个版本号
    python .git-hooks/push_version.py list [-n 10 | --all]              # 已发布版本与主要变动
    （check-push 由 pre-push 钩子调用：从标准输入读 git 传入的推送清单逐条校验）

push 依次：同步远端分支和标签 → 确认远端分支没有 HEAD 之外的提交 → 取下一个版本号 → 在 HEAD 打
附注标签（主要变动 + 自上一版本以来的提交清单）→ git push --atomic 同时推分支和标签。推送失败时
删掉本次新建的本地标签，下次重新取号。

安装：仓库根执行 powershell -ExecutionPolicy Bypass -File .git-hooks/install.ps1
（把 pre-push / pre-commit / 本文件复制到 .git/hooks/，各 worktree 共用）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# 以「v + 数字」开头的标签就是想当版本标签，必须严格符合 VERSION_RE（防 v1.0、v1.0.3-rc 混进来）
VERSION_LIKE_RE = re.compile(r"^v\d")
INITIAL_VERSION = (1, 0, 0)  # 远端 dev1.0 分支 = 1.0，第一个标签是 v1.0.1
BASELINE_BRANCH = "dev1.0"
NOTES_HEADING = "主要变动"
MIN_ITEM_CHARS = 4
COMMIT_LIST_CAP = 60
_BULLET_RE = re.compile(r"^(?:[-*•·]|\d+[.、．)）])\s*(.*)$")
_SIGNATURE_MARK = "-----BEGIN "
HOOK_TAG = "[pre-push][版本]"
TOOL_TAG = "[push_version]"


class GitError(RuntimeError):
    pass


def _env() -> dict[str, str]:
    # 钩子和工具里都不弹终端凭据输入：连不上就直接失败，不卡住推送
    return dict(os.environ, GIT_TERMINAL_PROMPT="0")


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, env=_env())
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git {' '.join(args)} 失败：{err}")
    return proc.stdout.decode("utf-8", errors="replace")


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], capture_output=True, env=_env()).returncode == 0


def is_zero(sha: str) -> bool:
    return bool(sha) and set(sha) == {"0"}


def peel_commit(obj: str) -> str | None:
    out = git("rev-parse", "--verify", "--quiet", f"{obj}^{{commit}}", check=False).strip()
    return out or None


def parse_version(name: str) -> tuple[int, int, int] | None:
    m = VERSION_RE.match(name)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def fmt_version(v: tuple[int, int, int]) -> str:
    return f"v{v[0]}.{v[1]}.{v[2]}"


def bump(v: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = v
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def local_version_tags() -> dict[str, str]:
    """本地版本标签 {名字: 标签对象 sha}，只含严格的 vX.Y.Z。"""
    out = git("for-each-ref", "refs/tags/v*", "--format=%(refname:strip=2)%09%(objectname)")
    tags: dict[str, str] = {}
    for line in out.splitlines():
        name, _, obj = line.partition("\t")
        if VERSION_RE.match(name):
            tags[name] = obj
    return tags


def remote_tag_map(remote: str) -> dict[str, tuple[str, str]] | None:
    """远端全部标签 {名字: (标签对象 sha, 指向的提交 sha)}；连不上返回 None。"""
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", remote], capture_output=True, env=_env(), timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    objs: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            peeled[name[:-3]] = sha
        else:
            objs[name] = sha
    return {name: (obj, peeled.get(name, obj)) for name, obj in objs.items()}


def published_top(remote_tags: dict[str, tuple[str, str]] | None) -> tuple[tuple[int, int, int], str]:
    """已发布的最大版本号和名字：以远端为准，连不上远端时用本地标签；一个都没有时是 1.0（dev1.0）。"""
    names = list(remote_tags) if remote_tags is not None else list(local_version_tags())
    versions = [(v, n) for n in names if (v := parse_version(n))]
    return max(versions) if versions else (INITIAL_VERSION, f"{BASELINE_BRANCH}（= 1.0）")


def tag_message(obj: str) -> str:
    """附注标签的说明正文（去掉签名块）。"""
    _, _, body = git("cat-file", "tag", obj).partition("\n\n")
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith(_SIGNATURE_MARK):
            break
        lines.append(line)
    return "\n".join(lines)


def change_items(message: str) -> list[str]:
    """「主要变动」段下的要点：段标题之后以 - / * / 1. / 1、 开头的行，遇到空行或别的段落为止。"""
    items: list[str] = []
    in_section = False
    for raw in message.splitlines():
        line = raw.strip()
        if not in_section:
            in_section = line.lstrip("#").strip().startswith(NOTES_HEADING)
            continue
        if not line:
            if items:
                break
            continue
        m = _BULLET_RE.match(line)
        if m:
            items.append(m.group(1).strip())
        elif raw[:1].isspace() and items:
            continue  # 上一条要点的续行
        else:
            break
    return items


def short_items(items: list[str]) -> list[str]:
    return [i for i in items if len(i) < MIN_ITEM_CHARS]


def tag_problems(name: str, obj: str) -> list[str]:
    """版本标签不合格的原因；空列表 = 合格。"""
    if not VERSION_RE.match(name):
        return [f"标签名「{name}」不是版本号格式 vX.Y.Z（如 v1.0.3）"]
    if git("cat-file", "-t", obj, check=False).strip() != "tag":
        return [f"{name} 是轻量标签：版本标签必须是附注标签（git tag -a），说明里写「{NOTES_HEADING}：」和要点"]
    if peel_commit(obj) is None:
        return [f"{name} 没有指向提交"]
    items = change_items(tag_message(obj))
    if not items:
        return [f"{name} 的说明里没有「{NOTES_HEADING}：」段，或段下没有以「- 」开头的要点"]
    short = short_items(items)
    if short:
        listed = "、".join(f"「{i}」" for i in short)
        return [f"{name} 的「{NOTES_HEADING}」要点太短（每条至少 {MIN_ITEM_CHARS} 个字）：{listed}"]
    return []


@dataclass
class RefUpdate:
    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str


def parse_push_lines(text: str) -> list[RefUpdate]:
    """git 传给 pre-push 的标准输入：每行「本地引用 本地sha 远端引用 远端sha」。"""
    updates: list[RefUpdate] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4:
            updates.append(RefUpdate(*parts))
    return updates


def count_new_commits(remote: str, local_sha: str, remote_sha: str) -> int:
    """local_sha 上有几个提交是远端还没有的（按本地已知的远端跟踪分支和远端当前值算）。"""
    args = ["rev-list", "--count", local_sha, "--not", f"--remotes={remote}"]
    if not is_zero(remote_sha) and git_ok("cat-file", "-e", f"{remote_sha}^{{commit}}"):
        args.append(remote_sha)
    out = git(*args, check=False).strip()
    return int(out) if out.isdigit() else 1  # 算不出来按「有新提交」处理，宁严勿松


def tool_command() -> str:
    """提示里给出的工具命令：优先主工作树里的源文件（临时 worktree 里不一定有这个文件）。"""
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", check=False).strip()
    if common:
        candidate = Path(common).parent / ".git-hooks" / "push_version.py"
        if candidate.is_file():
            return f"python {candidate.as_posix()}"
    return f"python {Path(__file__).resolve().as_posix()}"


def check_push(remote: str, updates: list[RefUpdate]) -> int:
    """pre-push：本次推送的版本标签逐个校验；带新提交的分支更新必须有合格的版本标签。"""

    def tag_name(u: RefUpdate) -> str:
        return u.remote_ref[len("refs/tags/"):]

    branches = [u for u in updates if u.remote_ref.startswith("refs/heads/") and not is_zero(u.local_sha)]
    version_tags = [
        u for u in updates
        if u.remote_ref.startswith("refs/tags/") and not is_zero(u.local_sha) and VERSION_LIKE_RE.match(tag_name(u))
    ]
    if not branches and not version_tags:
        return 0

    remote_tags = remote_tag_map(remote)
    if remote_tags is None:
        print(f"{HOOK_TAG} ⚠️ 取不到远端标签清单，版本号只和本地已知的标签比较")
    known = list(remote_tags) if remote_tags is not None else list(local_version_tags())
    pushing = {tag_name(u) for u in version_tags}
    others = [(v, n) for n in known if n not in pushing and (v := parse_version(n))]
    top_v, top_name = max(others) if others else (INITIAL_VERSION, f"{BASELINE_BRANCH}（= 1.0）")

    errors: list[str] = []
    ok_lines: list[str] = []
    valid_by_commit: dict[str, str] = {}
    tagged_commits: set[str] = set()  # 本次推送里带了版本标签（不论合格与否）的提交
    for u in version_tags:
        name = tag_name(u)
        commit = peel_commit(u.local_sha)
        if commit:
            tagged_commits.add(commit)
        problems = tag_problems(name, u.local_sha)
        ver = parse_version(name)
        if not problems and ver:
            if remote_tags is not None and name in remote_tags:
                problems.append(f"远端已有 {name}（版本号被别人先用了）：git tag -d {name} 后重新取号")
            elif ver <= top_v:
                problems.append(f"{name} 不大于已有的 {top_name}：版本号只能往上走")
        if problems:
            errors.extend(problems)
        elif commit:
            valid_by_commit[commit] = name
            ok_lines.append(f"版本标签 {name} 合格（指向 {commit[:9]}）")

    remote_by_commit: dict[str, str] = {}
    for n, (_, commit) in (remote_tags or {}).items():
        v = parse_version(n)
        if v and (commit not in remote_by_commit or v > parse_version(remote_by_commit[commit])):
            remote_by_commit[commit] = n

    for u in branches:
        branch = u.remote_ref[len("refs/heads/"):]
        new = count_new_commits(remote, u.local_sha, u.remote_sha)
        if new == 0:
            ok_lines.append(f"{branch}：没有远端还没有的提交，不需要版本标签")
        elif u.local_sha in valid_by_commit:
            ok_lines.append(f"{branch}：{new} 个新提交，版本 {valid_by_commit[u.local_sha]}")
        elif u.local_sha in remote_by_commit:
            ok_lines.append(f"{branch}：{new} 个新提交，远端已有版本 {remote_by_commit[u.local_sha]}")
        elif u.local_sha not in tagged_commits:  # 带了版本标签但不合格的，原因上面已列
            msg = f"{branch} 带 {new} 个新提交，但最新提交 {u.local_sha[:9]} 没有随本次推送的版本标签"
            points_at = git("tag", "--points-at", u.local_sha, check=False).split()
            local = sorted((t for t in points_at if VERSION_RE.match(t)), key=parse_version)
            if local:
                msg += (f"；本地已有 {local[-1]} 指向它，推送时带上："
                        f"git push --atomic {remote} {u.local_ref}:{u.remote_ref} refs/tags/{local[-1]}")
            errors.append(msg)

    for line in ok_lines:
        print(f"{HOOK_TAG} ✅ {line}")
    if not errors:
        return 0
    print(f"{HOOK_TAG} ❌ 版本标记不合格，拒绝 push：")
    for e in errors:
        print(f"  - {e}")
    print(f"  规则：推送新提交时，最新提交上要有附注标签 vX.Y.Z（大于远端已有版本），"
          f"说明里写「{NOTES_HEADING}：」和要点，并与分支同一次推送")
    print("  一步完成（自动取下一个版本号、写标签说明、原子推送分支和标签）：")
    print(f'    {tool_command()} push -c "主要变动一" -c "主要变动二"')
    print("  分离头 worktree 里加 --branch <远端分支>；先看版本号和说明加 --dry-run；看历史版本用 list")
    return 1


def notes_from_args(args: argparse.Namespace) -> list[str]:
    items = [c.strip() for c in (args.change or []) if c.strip()]
    if args.notes_file:
        for raw in Path(args.notes_file).read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.lstrip("#").strip().rstrip("：:") == NOTES_HEADING:
                continue
            m = _BULLET_RE.match(line)
            line = m.group(1).strip() if m else line
            if line:
                items.append(line)
    return items


def previous_version_base(remote: str, head: str, local_tags: dict[str, str]) -> tuple[str | None, str]:
    """上一个版本的提交：HEAD 祖先里版本号最大的版本标签；一个都没有就用 dev1.0 分支。"""
    for name in sorted(local_tags, key=parse_version, reverse=True):
        commit = peel_commit(local_tags[name])
        if commit and commit != head and git_ok("merge-base", "--is-ancestor", commit, head):
            return commit, f"自 {name} 起"
    commit = git("rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{BASELINE_BRANCH}", check=False).strip()
    if commit and commit != head and git_ok("merge-base", "--is-ancestor", commit, head):
        return commit, f"自 {BASELINE_BRANCH} 起"
    return None, ""


def compose_message(name: str, branch: str, items: list[str], head: str, base: str | None, label: str) -> str:
    """标签说明：首行版本 + 时间 + 分支；「主要变动」要点；自上一版本以来的提交清单。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"{name}（{now}，分支 {branch}）", "", f"{NOTES_HEADING}：", *(f"- {i}" for i in items), ""]
    if base:
        total = int(git("rev-list", "--count", f"{base}..{head}").strip())
        log = git("log", f"--max-count={COMMIT_LIST_CAP}", "--format=%h %s", f"{base}..{head}").splitlines()
        lines.append(f"包含提交（{label}，共 {total} 个）：")
    else:
        log = git("log", "--max-count=20", "--format=%h %s", head).splitlines()
        total = len(log)
        lines.append("最近的提交（没找到上一个版本）：")
    lines += [f"- {entry}" for entry in log]
    if total > len(log):
        lines.append(f"- ……另有 {total - len(log)} 个未列出")
    return "\n".join(lines) + "\n"


def cmd_push(args: argparse.Namespace) -> int:
    remote = args.remote
    branch = args.branch or git("symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()
    branch = branch.removeprefix("refs/heads/")
    if not branch:
        return fail("当前是分离头：用 --branch 指定要推送到的远端分支（如 --branch spec/xxx）")
    if git("status", "--porcelain=v1", "--untracked-files=all").strip():
        return fail("工作树有未提交 / 未跟踪的文件，pre-push 会拒推：先提交，或在干净的临时 worktree 里推送（加 --branch）")
    head = git("rev-parse", "HEAD").strip()

    print(f"{TOOL_TAG} 同步远端 {remote} 的分支和标签…", flush=True)
    fetch = subprocess.run(["git", "fetch", "--prune", "--tags", remote], capture_output=True, env=_env())
    if fetch.returncode != 0:
        tail = fetch.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        print(f"{TOOL_TAG} ⚠️ fetch 没有完全成功：{' / '.join(tail)}")
    tracking = f"refs/remotes/{remote}/{branch}"
    if git_ok("rev-parse", "--verify", "--quiet", tracking):
        behind = int(git("rev-list", "--count", f"HEAD..{tracking}").strip())
        if behind:
            return fail(f"远端 {branch} 有 {behind} 个提交不在 HEAD 里：先合并 / 变基到 {remote}/{branch} 再推送")
        if int(git("rev-list", "--count", f"{tracking}..HEAD").strip()) == 0:
            print(f"{TOOL_TAG} HEAD 已在远端 {branch} 上，没有要推送的新提交")
            return 0

    remote_tags = remote_tag_map(remote)
    local_tags = local_version_tags()
    head_tags = sorted((t for t in git("tag", "--points-at", head).split() if t in local_tags), key=parse_version)
    created = False
    if head_tags:
        name = head_tags[-1]
        problems = tag_problems(name, local_tags[name])
        if remote_tags is not None and name in remote_tags and remote_tags[name][0] != local_tags[name]:
            problems.append(f"本地 {name} 和远端同名标签不是同一个（版本号被别人先用了）")
        if problems:
            return fail(f"HEAD 上已有版本标签 {name} 但不能用：{problems[0]}；git tag -d {name} 后重跑")
        print(f"{TOOL_TAG} HEAD 已有版本标签 {name}，沿用（本次 -c / --notes-file 不写入）")
    else:
        items = notes_from_args(args)
        if not items:
            return fail('至少写一条主要变动：-c "…"（可重复）或 --notes-file <文件>')
        short = short_items(items)
        if short:
            return fail(f"主要变动每条至少 {MIN_ITEM_CHARS} 个字：" + "、".join(f"「{i}」" for i in short))
        top, top_name = published_top(remote_tags)
        if args.version:
            ver = parse_version(args.version)
            if ver is None:
                return fail(f"--version 要写成 vX.Y.Z（如 v1.0.3），收到「{args.version}」")
            if ver <= top:
                return fail(f"{args.version} 不大于已有的 {top_name}：版本号只能往上走")
        else:
            ver = bump(top, args.bump)
        name = fmt_version(ver)
        if git_ok("rev-parse", "--verify", "--quiet", f"refs/tags/{name}"):
            return fail(f"本地已有标签 {name}（指向别的提交，可能是上次推送没成功留下的）：git tag -d {name} 后重跑")
        base, label = previous_version_base(remote, head, local_tags)
        message = compose_message(name, branch, items, head, base, label)
        if args.dry_run:
            print(f"{TOOL_TAG} 下一个版本 {name}（--dry-run：没打标签、没推送），标签说明如下：\n")
            print(message)
            return 0
        fd, path = tempfile.mkstemp(prefix="push_version_", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(message)
            git("tag", "-a", "-F", path, "--cleanup=whitespace", name, head)
        finally:
            os.unlink(path)
        created = True
        print(f"{TOOL_TAG} 已在 {head[:9]} 打附注标签 {name}")

    refspecs = [f"HEAD:refs/heads/{branch}", f"refs/tags/{name}"]
    if args.dry_run:
        print(f"{TOOL_TAG} --dry-run：将执行 git push --atomic {remote} {' '.join(refspecs)}")
        return 0
    if args.no_push:
        print(f"{TOOL_TAG} 没推送（--no-push）；推送命令：git push --atomic {remote} {' '.join(refspecs)}")
        return 0
    cmd = ["git", "push", "--atomic", remote, *refspecs]
    print(f"{TOOL_TAG} {' '.join(cmd)}", flush=True)
    rc = subprocess.run(cmd, env=_env()).returncode
    if rc == 0:
        print(f"{TOOL_TAG} ✅ 已推送 {branch} 和 {name}")
        return 0
    # 命令失败先核对远端：见过推送命令被打断、远端其实已经更新的情况
    remote_head = git("ls-remote", remote, f"refs/heads/{branch}", check=False).partition("\t")[0].strip()
    tag_obj = git("rev-parse", "--verify", "--quiet", f"refs/tags/{name}", check=False).strip()
    remote_tag = (remote_tag_map(remote) or {}).get(name, ("", ""))[0]
    if remote_head == head and tag_obj and remote_tag == tag_obj:
        print(f"{TOOL_TAG} ⚠️ 推送命令返回失败，但远端已经是本次结果（{branch} = {head[:9]}，{name} 已在远端），按成功处理")
        return 0
    if created:
        git("tag", "-d", name, check=False)
        print(f"{TOOL_TAG} ❌ 推送没成功，已删掉本次新建的本地标签 {name}（下次重新取号）")
    else:
        print(f"{TOOL_TAG} ❌ 推送没成功")
    return rc or 1


def cmd_next(args: argparse.Namespace) -> int:
    subprocess.run(["git", "fetch", "--tags", args.remote], capture_output=True, env=_env())
    top, _ = published_top(remote_tag_map(args.remote))
    print(fmt_version(bump(top, args.bump)))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    subprocess.run(["git", "fetch", "--tags", args.remote], capture_output=True, env=_env())
    fmt = ("%(refname:strip=2)%09%(objectname)%09%(objecttype)%09"
           "%(taggerdate:format:%Y-%m-%d %H:%M)%09%(*objectname:short)")
    rows = []
    for line in git("for-each-ref", "refs/tags/v*", f"--format={fmt}").splitlines():
        name, obj, kind, date, commit = (line.split("\t") + [""] * 5)[:5]
        ver = parse_version(name)
        if ver:
            rows.append((ver, name, obj, kind, date, commit))
    if not rows:
        first = fmt_version(bump(INITIAL_VERSION, "patch"))
        print(f"还没有版本标签；下一个是 {first}（{BASELINE_BRANCH} = 1.0）")
        return 0
    rows.sort(reverse=True)
    shown = rows if args.all else rows[: args.limit]
    for _, name, obj, kind, date, commit in shown:
        print(f"{name}  {date or '-'}  {commit or obj[:9]}")
        items = change_items(tag_message(obj)) if kind == "tag" else []
        for item in items or ["（没有主要变动说明）"]:
            print(f"  - {item}")
    if len(shown) < len(rows):
        print(f"……另有 {len(rows) - len(shown)} 个较早的版本（加 --all 全部列出）")
    return 0


def fail(msg: str) -> int:
    print(f"{TOOL_TAG} ❌ {msg}", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="推送版本标记：打版本标签并和分支一起推送；pre-push 钩子校验")
    sub = parser.add_subparsers(dest="cmd", required=True)

    push = sub.add_parser("push", help="取下一个版本号、在 HEAD 打附注标签、原子推送分支和标签")
    push.add_argument("-c", "--change", action="append", help="一条主要变动（可重复；每条至少 4 个字）")
    push.add_argument("--notes-file", help="主要变动写在文件里（UTF-8，每行一条）")
    push.add_argument("--branch", help="推送到的远端分支（默认当前分支；分离头必须指定）")
    push.add_argument("--remote", default="origin")
    push.add_argument("--bump", choices=("patch", "minor", "major"), default="patch", help="默认修订号 +1")
    push.add_argument("--version", help="直接指定版本号 vX.Y.Z（必须大于已有版本）")
    push.add_argument("--dry-run", action="store_true", help="只显示版本号和标签说明，不打标签、不推送")
    push.add_argument("--no-push", action="store_true", help="只打标签，不推送")

    nxt = sub.add_parser("next", help="打印下一个版本号")
    nxt.add_argument("--remote", default="origin")
    nxt.add_argument("--bump", choices=("patch", "minor", "major"), default="patch")

    lst = sub.add_parser("list", help="查看版本标签和主要变动")
    lst.add_argument("--remote", default="origin")
    lst.add_argument("-n", "--limit", type=int, default=10)
    lst.add_argument("--all", action="store_true")

    chk = sub.add_parser("check-push", help="pre-push 钩子用：从标准输入读推送清单逐条校验")
    chk.add_argument("remote")
    chk.add_argument("url", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.cmd == "check-push":
        try:
            text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
            return check_push(args.remote, parse_push_lines(text))
        except Exception as exc:  # 校验自己出错也拒推（宁严勿松），并把原因打出来
            print(f"{HOOK_TAG} ❌ 版本校验出错，拒绝 push：{type(exc).__name__}: {exc}")
            return 1
    handlers = {"push": cmd_push, "next": cmd_next, "list": cmd_list}
    try:
        return handlers[args.cmd](args)
    except GitError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
