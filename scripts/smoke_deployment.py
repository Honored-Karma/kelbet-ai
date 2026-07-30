"""Small public smoke test for a deployed KELBET API and Mini App."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Check:
    name: str
    url: str
    contains: str | None = None


def _normalized_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _run_check(check: Check, timeout: float) -> tuple[bool, str]:
    request = Request(
        check.url,
        headers={"User-Agent": "KELBET-Deployment-Smoke/1.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(512_000).decode("utf-8", errors="replace")
            status = response.status
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except URLError as exc:
        return False, str(exc.reason)

    if status != 200:
        return False, f"HTTP {status}"
    if check.contains and check.contains.lower() not in body.lower():
        return False, f"ответ не содержит {check.contains!r}"
    return True, "HTTP 200"


def build_checks(api_url: str, web_url: str) -> list[Check]:
    api = _normalized_base_url(api_url)
    web = _normalized_base_url(web_url)
    return [
        Check("API health", f"{api}/health", '"status":"ok"'),
        Check("Mini App home", f"{web}/", "KELBET"),
        Check("Mini App create route", f"{web}/create", "KELBET"),
        Check("Mini App history route", f"{web}/history", "KELBET"),
        Check("Mini App plans route", f"{web}/plans", "KELBET"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Проверить публичные KELBET API и Mini App после деплоя."
    )
    parser.add_argument("--api", required=True, help="https://...up.railway.app")
    parser.add_argument("--web", required=True, help="https://...vercel.app")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    results: list[dict[str, object]] = []
    for check in build_checks(args.api, args.web):
        passed, detail = _run_check(check, args.timeout)
        results.append(
            {
                "name": check.name,
                "url": check.url,
                "passed": passed,
                "detail": detail,
            }
        )

    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for result in results:
            marker = "PASS" if result["passed"] else "FAIL"
            print(f"[{marker}] {result['name']}: {result['detail']} ({result['url']})")

    if not all(bool(result["passed"]) for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
