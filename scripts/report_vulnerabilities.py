# Source-File AI Declaration
# AI contribution: 50% or more AI-generated

"""
Scan the backend and frontend dependencies for known vulnerabilities.

By default the findings are only reported, as workflow warnings and in the job summary, and
the exit code is always 0 so a pull request is never blocked. Advisories below MIN_SEVERITY
appear in the job summary alone. With --open-issues, each package with an advisory at or above
it also gets one open GitHub issue, which later runs update instead of duplicating. Issues are
never closed here: the pull request that fixes one closes it. A scan that cannot run fails the
job in this mode, so a broken scanner does not look like a clean one.

Run it from anywhere, with pip-audit installed and, for --open-issues, gh authenticated:

    python scripts/report_vulnerabilities.py
    python scripts/report_vulnerabilities.py --open-issues
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

ISSUE_LABEL = "dependency-scan"
SEVERITY_RANK = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
# Advisories below this, or with no known severity, only reach the job summary.
MIN_SEVERITY = "high"
UNKNOWN_SEVERITY = "unknown"
OSV_VULNERABILITY_URL = "https://api.osv.dev/v1/vulns/"
# Accepted Python advisories, e.g. "GHSA-xxxx-xxxx-xxxx". Without an entry here, an issue closed
# while the package is still vulnerable is opened again on the next run.
IGNORED_PIP_VULNS: tuple[str, ...] = ()


class ScanError(Exception):
    """A scanner could not run, which says nothing about the dependencies."""


@dataclass(frozen=True)
class Advisory:
    identifier: str
    severity: str
    summary: str
    fix: str


@dataclass(frozen=True)
class Finding:
    scope: str
    package: str
    version: str
    advisories: tuple[Advisory, ...]

    @property
    def title(self) -> str:
        return f"[deps] {self.scope}: {self.package}"


def load_report(output: str, required_key: str) -> dict[str, Any]:
    """Parse scanner output, which only counts as a scan if it holds the expected results."""
    try:
        report = json.loads(output)
    except json.JSONDecodeError as error:
        raise ScanError(f"output is not valid JSON: {error}") from error
    if not isinstance(report, dict) or required_key not in report or "error" in report:
        raise ScanError(f"output has no '{required_key}' results: {output[:500]}")
    return report


def lookup_severity(vulnerability: dict[str, Any]) -> str:
    """Find a Python advisory's severity, which pip-audit does not report, through its GHSA ID."""
    identifiers = [vulnerability["id"], *vulnerability.get("aliases", [])]
    for identifier in identifiers:
        if not identifier.startswith("GHSA-"):
            continue
        try:
            with urllib.request.urlopen(
                f"{OSV_VULNERABILITY_URL}{identifier}", timeout=30
            ) as response:
                record = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue
            raise ScanError(f"severity lookup failed for {identifier}: {error}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise ScanError(f"severity lookup failed for {identifier}: {error}") from error
        severity = str(record.get("database_specific", {}).get("severity", "")).lower()
        if severity in SEVERITY_RANK:
            return severity
    return UNKNOWN_SEVERITY


def pip_advisory(vulnerability: dict[str, Any]) -> Advisory:
    return Advisory(
        identifier=vulnerability["id"],
        severity=lookup_severity(vulnerability),
        summary=vulnerability.get("description", "").split("\n")[0],
        fix=", ".join(vulnerability.get("fix_versions", [])) or "no fix released",
    )


def parse_pip_audit(scope: str, output: str) -> list[Finding]:
    findings = []
    for dependency in load_report(output, "dependencies")["dependencies"]:
        # pip-audit can list the same advisory more than once for a package
        unique = {
            vulnerability["id"]: vulnerability for vulnerability in dependency.get("vulns", [])
        }
        if unique:
            findings.append(
                Finding(
                    scope=scope,
                    package=dependency["name"],
                    version=dependency["version"],
                    advisories=tuple(pip_advisory(item) for item in unique.values()),
                )
            )
    return findings


def npm_fix(fix_available: bool | dict[str, Any]) -> str:
    if isinstance(fix_available, dict):
        major = " (major upgrade)" if fix_available.get("isSemVerMajor") else ""
        return f"upgrade {fix_available['name']} to {fix_available['version']}{major}"
    return "run npm audit fix" if fix_available else "no fix released"


def parse_npm_audit(scope: str, output: str) -> list[Finding]:
    """Keep only packages with their own advisory.

    npm also lists every package that merely depends on a vulnerable one, with strings instead
    of advisories in `via`. Those would be many issues for what is a single fix.
    """
    findings = []
    for name, entry in load_report(output, "vulnerabilities")["vulnerabilities"].items():
        advisories = tuple(
            Advisory(
                identifier=source["url"],
                severity=source["severity"],
                summary=source["title"],
                fix=npm_fix(entry["fixAvailable"]),
            )
            for source in entry["via"]
            if isinstance(source, dict)
        )
        if advisories:
            findings.append(
                Finding(
                    scope=scope,
                    package=name,
                    version=entry["range"],
                    advisories=advisories,
                )
            )
    return findings


def meets_threshold(advisory: Advisory) -> bool:
    rank = SEVERITY_RANK.get(advisory.severity)
    return rank is not None and rank >= SEVERITY_RANK[MIN_SEVERITY]


def split_by_severity(findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    """Split into (at or above MIN_SEVERITY, everything else); a package can land in both."""
    serious = []
    minor = []
    for finding in findings:
        above = tuple(item for item in finding.advisories if meets_threshold(item))
        below = tuple(item for item in finding.advisories if not meets_threshold(item))
        if above:
            serious.append(replace(finding, advisories=above))
        if below:
            minor.append(replace(finding, advisories=below))
    return serious, minor


def run_scanner(command: list[str], directory: str) -> str:
    # Both scanners exit non-zero when they find something, so the exit code proves nothing.
    # load_report decides whether the scan actually ran.
    result = subprocess.run(
        command,
        cwd=REPO_ROOT / directory,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout or result.stderr


def scan_backend() -> list[Finding]:
    ignored = [
        argument for identifier in IGNORED_PIP_VULNS for argument in ("--ignore-vuln", identifier)
    ]
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "--requirement",
        "requirements-dev.txt",
        "--format",
        "json",
        "--progress-spinner",
        "off",
        *ignored,
    ]
    return parse_pip_audit("backend", run_scanner(command, "backend"))


def scan_npm(scope: str, directory: str) -> list[Finding]:
    # npm is a .cmd file on Windows, which subprocess only finds through its full path
    command = [shutil.which("npm") or "npm", "audit", "--json"]
    return parse_npm_audit(scope, run_scanner(command, directory))


SCANS: dict[str, Callable[[], list[Finding]]] = {
    "backend": scan_backend,
    "frontend": lambda: scan_npm("frontend", "frontend"),
    "e2e": lambda: scan_npm("e2e", "."),
}


def issue_body(finding: Finding) -> str:
    rows = "\n".join(
        f"| {advisory.identifier} | {advisory.severity} "
        f"| {advisory.summary.replace('|', '/')} | {advisory.fix} |"
        for advisory in finding.advisories
    )
    return (
        f"`{finding.package}` ({finding.version}) in `{finding.scope}` has known "
        "vulnerabilities.\n\n"
        "| Advisory | Severity | Summary | Fix |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows}\n\n"
        "Opened by the dependency scan, which keeps this list up to date. Close it from the "
        "fixing pull request with `Closes #<this issue>`. If the risk is accepted instead, add "
        "the advisory to the ignore list in `scripts/report_vulnerabilities.py`, or this issue "
        "comes back on the next run.\n"
    )


def gh(*arguments: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        [shutil.which("gh") or "gh", *arguments],
        cwd=REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


def sync_issues(findings: list[Finding]) -> None:
    gh("label", "create", ISSUE_LABEL, "--force", "--color", "B60205")
    listing = gh(
        "issue",
        "list",
        "--label",
        ISSUE_LABEL,
        "--state",
        "open",
        "--limit",
        "500",
        "--json",
        "number,title,body",
    )
    open_issues = {issue["title"]: issue for issue in json.loads(listing)}
    for finding in findings:
        body = issue_body(finding)
        issue = open_issues.get(finding.title)
        if issue is None:
            gh(
                "issue",
                "create",
                "--title",
                finding.title,
                "--label",
                ISSUE_LABEL,
                "--body-file",
                "-",
                stdin=body,
            )
            print(f"Opened issue: {finding.title}")
        elif issue["body"].strip() != body.strip():
            gh("issue", "edit", str(issue["number"]), "--body-file", "-", stdin=body)
            print(f"Updated issue #{issue['number']}: {finding.title}")


def annotation(text: str) -> str:
    """Escape text for a workflow command, so it stays on one annotation line."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report(serious: list[Finding], minor: list[Finding], failures: dict[str, str]) -> None:
    lines = ["## Dependency scan", ""]
    if not serious:
        lines.append("No vulnerabilities at or above the reporting threshold.")
    for finding in serious:
        identifiers = ", ".join(advisory.identifier for advisory in finding.advisories)
        lines.append(f"- **{finding.title}**: {identifiers}")
        print(f"::warning::{annotation(f'{finding.title}: {identifiers}')}")
    for scan, reason in failures.items():
        lines.append(f"- **{scan} scan failed**: {reason}")
        print(f"::warning::{annotation(f'{scan} scan failed: {reason}')}")
    if minor:
        lines.extend(["", f"### Below {MIN_SEVERITY} or unknown severity (no issue opened)", ""])
    for finding in minor:
        details = ", ".join(
            f"{advisory.identifier} ({advisory.severity})" for advisory in finding.advisories
        )
        lines.append(f"- **{finding.title}**: {details}")

    summary = "\n".join(lines)
    print(summary)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write(f"{summary}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--open-issues",
        action="store_true",
        help="open or update a GitHub issue per vulnerable package",
    )
    arguments = parser.parse_args()

    findings: list[Finding] = []
    failures: dict[str, str] = {}
    for name, scan in SCANS.items():
        try:
            findings.extend(scan())
        except ScanError as error:
            failures[name] = str(error)

    serious, minor = split_by_severity(findings)
    report(serious, minor, failures)
    if not arguments.open_issues:
        return 0
    sync_issues(serious)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
