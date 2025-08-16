# run_pytest_with_coverage.py
"""
Run all pytest tests and print a coverage summary. Fails with exit code 1 if coverage is below threshold.
"""
import sys
import subprocess

COVERAGE_THRESHOLD = 85  # percent

# Run pytest with coverage
result = subprocess.run([
    sys.executable, "-m", "pytest", "--cov=.", "--cov-report=term-missing", "--cov-fail-under=%d" % COVERAGE_THRESHOLD
])

sys.exit(result.returncode)
