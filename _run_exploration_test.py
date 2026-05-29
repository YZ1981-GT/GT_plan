"""Helper script to run the exploration test and capture output."""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest",
     "backend/tests/test_bug_condition_exploration.py",
     "-v", "--tb=short", "-s"],
    capture_output=True,
    text=True,
    timeout=1800,  # 30 min
)

with open("test_exploration_result.txt", "w", encoding="utf-8") as f:
    f.write(f"RETURN CODE: {result.returncode}\n\n")
    f.write("=== STDOUT ===\n")
    f.write(result.stdout)
    f.write("\n\n=== STDERR ===\n")
    f.write(result.stderr)

print(f"Done. RC={result.returncode}")
print("Output saved to test_exploration_result.txt")
