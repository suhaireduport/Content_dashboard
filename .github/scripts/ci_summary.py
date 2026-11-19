"""Print the test counts from pytest's JUnit XML and add them to the GitHub run's Summary page.

Usage: python .github/scripts/ci_summary.py reports/junit.xml
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def summarize(report: Path) -> tuple[dict[str, int], list[str]]:
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0}
    failed = []
    for case in ET.parse(report).iter("testcase"):
        name = f'{case.get("classname")}::{case.get("name")}'
        if case.find("failure") is not None:
            counts["failed"] += 1
            failed.append(name)
        elif case.find("error") is not None:
            counts["errors"] += 1
            failed.append(f"{name} (error)")
        elif (skipped := case.find("skipped")) is not None:
            counts["xfailed" if skipped.get("type") == "pytest.xfail" else "skipped"] += 1
        else:
            counts["passed"] += 1
    return counts, failed


def main() -> None:
    report = Path(sys.argv[1])
    if report.exists():
        counts, failed = summarize(report)
        line = ", ".join(f"{number} {label}" for label, number in counts.items())
        markdown = [
            f"### Test results: {sum(counts.values())} tests",
            "",
            "| " + " | ".join(label.capitalize() for label in counts) + " |",
            "|" + "---|" * len(counts),
            "| " + " | ".join(str(number) for number in counts.values()) + " |",
        ]
        if failed:
            markdown += ["", "**Failed:**", *(f"- `{name}`" for name in failed)]
    else:
        line = "No test results: the run stopped before pytest finished (see the HTML report)."
        markdown = ["### Test results", "", line]

    print(line)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as out:
            out.write("\n".join(markdown) + "\n")


if __name__ == "__main__":
    main()
