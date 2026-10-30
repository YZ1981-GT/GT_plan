from pathlib import Path

log = Path(r"D:\zaqcwrok\GT_plan_sw\_pip_install.log")
if not log.exists():
    print("LOG MISSING")
    raise SystemExit(1)

lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
print("log lines:", len(lines))

succ = [l for l in lines if "Successfully installed" in l]
errs = [l for l in lines if l.startswith("ERROR")]
kills = [l for l in lines if "Killed" in l or "MemoryError" in l]

print("Successfully installed:", len(succ))
print("ERROR lines:", len(errs))
print("killed/oom:", len(kills))
print()
for l in errs[:8]:
    print("  ERR:", l[:200])
for l in succ:
    print("  OK:", l[:300])
print()
print("--- tail 8 ---")
for l in lines[-8:]:
    print("  ", l[:180])
