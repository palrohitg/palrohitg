#!/usr/bin/env python3
"""Update the profile README with authored PRs in selected organizations."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


START = "<!-- PR-TRACKER:START -->"
END = "<!-- PR-TRACKER:END -->"
README = Path(__file__).resolve().parents[1] / "README.md"
AUTHOR = os.getenv("PR_TRACKER_AUTHOR", "palrohitg")
ORGANIZATIONS = tuple(
    org.strip()
    for org in os.getenv("PR_TRACKER_ORGS", "OpenHands,SynthLuvr").split(",")
    if org.strip()
)
LIMIT = int(os.getenv("PR_TRACKER_LIMIT", "20"))


def github_json(url: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "palrohitg-profile-pr-tracker",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned {error.code}: {detail}") from error


def authored_pull_requests() -> list[dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    for organization in ORGANIZATIONS:
        query = f"is:pr author:{AUTHOR} org:{organization}"
        params = urllib.parse.urlencode(
            {"q": query, "sort": "updated", "order": "desc", "per_page": 100}
        )
        payload = github_json(f"https://api.github.com/search/issues?{params}")

        for item in payload.get("items", []):
            repository = "/".join(item["repository_url"].rstrip("/").split("/")[-2:])
            merged_at = item.get("pull_request", {}).get("merged_at")
            if item["state"] == "closed" and not merged_at:
                merged_at = github_json(item["pull_request"]["url"]).get("merged_at")

            if item["state"] != "open" and not merged_at:
                continue

            results[item["html_url"]] = {
                "organization": repository.split("/", 1)[0],
                "repository": repository,
                "number": item["number"],
                "title": item["title"],
                "url": item["html_url"],
                "updated_at": item["updated_at"],
                "merged_at": merged_at,
                "is_open": item["state"] == "open",
            }

    newest_first = sorted(
        results.values(),
        key=lambda pr: pr["updated_at"],
        reverse=True,
    )
    return sorted(
        newest_first,
        key=lambda pr: not pr["is_open"],
    )[:LIMIT]


def markdown(prs: list[dict[str, Any]]) -> str:
    generated = datetime.now().astimezone().strftime("%Y-%m-%d")
    lines = [
        START,
        "| Organization | Pull request | Status | Updated |",
        "|---|---|---|---|",
    ]

    for pr in prs:
        organization = pr["organization"]
        repo = pr["repository"]
        title = pr["title"].replace("|", "\\|")
        status = "🟡 In review" if pr["is_open"] else "✅ Merged"
        updated = pr["updated_at"][:10]
        lines.append(
            f"| [{organization}](https://github.com/{organization}) "
            f"| [{repo}#{pr['number']} — {title}]({pr['url']}) "
            f"| {status} | {updated} |"
        )

    if not prs:
        lines.append("| — | No matching pull requests found | — | — |")

    lines.extend(
        [
            "",
            f"_Last refreshed {generated} · "
            f"Tracking {', '.join(ORGANIZATIONS)} automatically._",
            END,
        ]
    )
    return "\n".join(lines)


def main() -> None:
    contents = README.read_text()
    if START not in contents or END not in contents:
        raise RuntimeError("README is missing PR tracker markers")

    before, remainder = contents.split(START, 1)
    _, after = remainder.split(END, 1)
    README.write_text(f"{before}{markdown(authored_pull_requests())}{after}")


if __name__ == "__main__":
    main()
