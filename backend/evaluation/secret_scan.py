"""Secret scan (TR-S-03): run before each push and in CI. Standard library only; run from anywhere in the repo.

    python backend/evaluation/secret_scan.py

It fails (exit 1) if, in any tracked file or anywhere in the git history:
  * a value from your local .env (4 characters or more of secret-looking text) appears, or
  * a well-known credential pattern appears (API keys, private keys, tokens).
It also fails if .env is tracked. Placeholders in .env.example are fine because they are empty.
"""
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Groq key": re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    "OpenRouter key": re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}"),
    "JSON web token": re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"),
}
SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
MIN_SECRET_LENGTH = 8
# Not secrets: wording that is meant to be public, and example values used in tests and documentation.
ALLOWED_TEXT = ("ci-only", "test-secret", "not-the-token", "forged", "mock.jwt.token", "eval-password", "long-enough")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def env_secrets(root: Path) -> dict[str, str]:
    path = root / ".env"
    found = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            value = value.strip().strip("\"'")
            if sep and SECRET_NAME.search(name) and len(value) >= MIN_SECRET_LENGTH:
                found[name.strip()] = value
    return found


def scan() -> list[str]:
    root = Path(git("rev-parse", "--show-toplevel").strip())
    problems = []
    tracked = git("ls-files").splitlines()
    if ".env" in tracked or any(f.endswith("/.env") for f in tracked):
        problems.append(".env is tracked by git")

    revisions = git("rev-list", "--all").split()
    secrets = env_secrets(root)
    for name, value in secrets.items():
        for revision in revisions:
            hit = subprocess.run(
                ["git", "grep", "-l", "-F", "-e", value, revision], capture_output=True, text=True, encoding="utf-8",
                errors="replace",
            ).stdout.strip()
            if hit:
                problems.append(f"the value of {name} from .env appears in {hit.splitlines()[0]}")
                break

    for revision in revisions:
        for kind, pattern in PATTERNS.items():
            for line in git("grep", "-n", "-I", "-E", pattern.pattern, revision).splitlines():
                if not any(word in line for word in ALLOWED_TEXT):
                    problems.append(f"{kind} in {line[:110]}")
    return sorted(set(problems))


def main() -> int:
    problems = scan()
    revisions = len(git("rev-list", "--all").split())
    if problems:
        print(f"SECRET SCAN FAILED ({len(problems)} finding(s)):")
        for problem in problems:
            print("  -", problem)
        return 1
    print(f"secret scan passed: {revisions} commits, {len(git('ls-files').splitlines())} tracked files, no secrets found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
