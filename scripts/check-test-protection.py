"""TR-S-11: check in a real browser that question text cannot be copied, dragged, printed or opened in a context menu, and
that a student's name and time lie over the page. Run against a throwaway stack, never the live one:

  python -m venv v && v/bin/pip install playwright httpx && v/bin/playwright install chromium
  v/bin/python scripts/check-test-protection.py --api http://127.0.0.1:18000/api/v1 --web http://127.0.0.1:18080 \
      --join-code <the course's join code> --course 1

It registers a throwaway student, so the stack must be one that can be thrown away. Exit status 1 if any check fails.
"""
import argparse
import sys
import uuid

import httpx
from playwright.sync_api import sync_playwright

failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{' - ' + detail if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def student(api: str, join_code: str, course: int) -> tuple[str, str]:
    email = f"protect-{uuid.uuid4().hex[:8]}@eval.local"
    client = httpx.Client(base_url=api, timeout=30)
    token = client.post("/auth/register", json={"email": email, "password": "eval-password-1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    version = client.get("/consent/notice", headers=headers).json()["version"]
    client.post("/consent/accept", headers=headers, json={"version": version, "adult": True}).raise_for_status()
    client.post("/courses/join", headers=headers, json={"code": join_code}).raise_for_status()
    return token, email


PROBE = """(selector) => {
  const el = document.querySelector(selector);
  const out = {style: getComputedStyle(el).userSelect};
  const range = document.createRange(); range.selectNodeContents(el);
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  out.selected = sel.toString().trim();
  for (const type of ['copy', 'cut', 'dragstart', 'contextmenu']) {
    const event = new Event(type, {bubbles: true, cancelable: true});
    el.dispatchEvent(event);
    out[type] = event.defaultPrevented;
  }
  return out;
}"""


def page_checks(page, label: str, email: str) -> None:
    page.wait_for_selector(".protected", timeout=15000)
    result = page.evaluate(PROBE, ".protected")
    check(f"{label}: text is not selectable", result["style"] == "none" and result["selected"] == "", str(result))
    for kind in ("copy", "cut", "dragstart", "contextmenu"):
        check(f"{label}: {kind} is blocked", result[kind] is True)
    page.wait_for_selector(".watermark", timeout=15000)
    mark = page.evaluate(
        "() => { const w = document.querySelector('.watermark'); return {text: w.textContent, events: getComputedStyle(w).pointerEvents}; }"
    )
    check(f"{label}: watermark names the student", email in mark["text"] and "UTC" in mark["text"], mark["text"][:80])
    check(f"{label}: watermark does not catch clicks", mark["events"] == "none")
    page.emulate_media(media="print")
    hidden = page.evaluate("() => getComputedStyle(document.querySelector('.protected')).display")
    check(f"{label}: question text is hidden when printing", hidden == "none", hidden)
    page.emulate_media(media="screen")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--web", required=True)
    parser.add_argument("--join-code", required=True)
    parser.add_argument("--course", type=int, default=1)
    args = parser.parse_args()
    token, email = student(args.api, args.join_code, args.course)
    problems = httpx.get(f"{args.api}/problems", params={"course_id": args.course}, headers={"Authorization": f"Bearer {token}"}).json()
    problem = next(p["id"] for p in problems["problems"] if p.get("kind", "code") == "code")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        context.add_init_script(f"sessionStorage.setItem('lms.session', JSON.stringify({{token: '{token}', role: 'student'}}));")
        page = context.new_page()
        page.goto(f"{args.web}/#/problem/{problem}")
        page_checks(page, "problem page", email)
        editor = page.locator(".monaco-editor").first
        editor.wait_for(timeout=20000)
        editor.click()
        page.keyboard.type("zzqq")
        check("problem page: the code editor still accepts typing", "zzqq" in page.locator(".view-lines").first.inner_text())
        page.goto(f"{args.web}/#/placement/{args.course}")
        page.get_by_role("button", name="Start the test").click()
        page_checks(page, "placement question", email)
        browser.close()
    print(f"\n{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
