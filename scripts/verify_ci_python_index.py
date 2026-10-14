#!/usr/bin/env python3
"""Fail closed unless CI installs Python packages from verified public PyPI HTTPS."""
import os
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


EXPECTED_INDEX = "https://pypi.org/simple"


def main() -> None:
    index = os.environ.get("PIP_INDEX_URL", "").rstrip("/")
    if index != EXPECTED_INDEX:
        raise SystemExit("CI Python index must be exactly https://pypi.org/simple.")
    for variable in ("PIP_TRUSTED_HOST", "PIP_EXTRA_INDEX_URL", "PIP_FIND_LINKS"):
        if os.environ.get(variable, "").strip():
            raise SystemExit(f"CI must not use {variable} to bypass or extend the trusted index.")

    context = ssl.create_default_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise SystemExit("CI Python index TLS certificate validation is not enabled.")

    request = Request(f"{EXPECTED_INDEX}/", headers={"User-Agent": "horario-inteligente-ci/1"})
    with urlopen(request, context=context, timeout=20) as response:
        final_url = urlsplit(response.geturl())
        if response.status != 200 or final_url.scheme != "https" or final_url.hostname != "pypi.org":
            raise SystemExit("Official PyPI HTTPS preflight did not return a verified PyPI response.")

    print("CI_PYPI_TLS_VERIFIED: official PyPI HTTPS, certificate validation enabled")


if __name__ == "__main__":
    main()
