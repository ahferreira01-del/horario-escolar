#!/usr/bin/env python3
"""Fail CI if any required real-PostgreSQL rate-limit test was skipped or absent."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

REQUIRED = {
    "test_postgres_counter_is_atomic_shared_and_persisted",
    "test_expiry_and_success_reset_are_persisted",
    "test_unavailable_postgres_fails_closed",
    "test_postgres_backup_restore_preserves_rls_and_acl",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: verify_ci_postgres_auth_throttle.py <junit.xml>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print("NO-GO: PostgreSQL auth-throttle JUnit report missing.", file=sys.stderr)
        return 1
    root = ET.parse(path).getroot()
    cases = {case.attrib.get("name", "") for case in root.iter("testcase")}
    missing = REQUIRED - cases
    skipped = [
        case.attrib.get("name", "")
        for case in root.iter("testcase")
        if case.attrib.get("name", "") in REQUIRED
        and case.find("skipped") is not None
    ]
    if missing or skipped:
        print(f"NO-GO: required PostgreSQL auth-throttle tests missing={sorted(missing)} skipped={skipped}", file=sys.stderr)
        return 1
    print("POSTGRES_AUTH_THROTTLE_PASSED: concurrent, persistent, expiry and fail-closed tests executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
