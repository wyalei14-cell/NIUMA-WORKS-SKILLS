#!/usr/bin/env python3
"""Release smoke tests for the NIUMA WORKS agent skill.

The default mode is read-only and safe for CI or a newly installed agent. It
checks imports, ABI encoding, reviewer parsing rules, public API access, and
optional local signer availability without broadcasting transactions.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ROOT = SKILL_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))

import niuma_api  # noqa: E402
import niuma_chain  # noqa: E402
import niuma_reviewer  # noqa: E402


def ok(name, detail=None):
    return {"name": name, "ok": True, "detail": detail or ""}


def fail(name, detail):
    return {"name": name, "ok": False, "detail": str(detail)}


def run_json(cmd, cwd=ROOT):
    output = subprocess.check_output(cmd, cwd=str(cwd), text=True, encoding="utf-8")
    return json.loads(output)


def test_reviewer_rules():
    address = "0x1234567890abcdef1234567890abcdef12345678"
    claim = niuma_reviewer.extract_claim(46, {
        "proofHash": "https://example.com/proof.png",
        "metadata": f"任务ID：54 钱包地址：{address}",
    })
    if claim["claimedTaskId"] != 54:
        raise AssertionError(f"expected task 54, got {claim}")
    if claim["claimedWallet"].lower() != address.lower():
        raise AssertionError(f"expected wallet {address}, got {claim}")
    if not claim["hasScreenshotEvidence"]:
        raise AssertionError("expected screenshot evidence")

    task = {
        "status": 1,
        "completedAt": 0,
        "isRefunded": False,
        "currentParticipants": 1,
    }
    group = {"submissions": [{"is_approved": 1, "status": 2}]}
    if not niuma_reviewer.completed_with_acceptance(task, group):
        raise AssertionError("approved submission should satisfy completed+accepted requirement")
    if niuma_reviewer.settled_with_acceptance(task, group):
        raise AssertionError("active task should not satisfy explicit settlement requirement")


def test_calldata():
    data = niuma_chain.calldata_approve_submission(
        46,
        "0x1234567890abcdef1234567890abcdef12345678",
    )
    if not data.startswith("0x0494808d"):
        raise AssertionError(f"unexpected approveSubmission calldata: {data[:10]}")


def test_network_config():
    if niuma_chain.NETWORK != "xlayer-mainnet":
        return f"custom network: {niuma_chain.NETWORK}"
    expected = "0x45e18236b1B851dC793932B0F285241A25A66813".lower()
    if niuma_chain.CORE.lower() != expected:
        raise AssertionError(f"unexpected mainnet core: {niuma_chain.CORE}")
    if niuma_chain.RPC_URL != "https://rpc.xlayer.tech":
        raise AssertionError(f"unexpected mainnet rpc: {niuma_chain.RPC_URL}")
    return f"{niuma_chain.NETWORK} chain={niuma_chain.ONCHAINOS_CHAIN}"


def test_api_read():
    tasks = niuma_api.request_json("GET", "/chain-data/query", params={
        "table": "sj_tasks",
        "page": 1,
        "limit": 1,
    })
    if not isinstance(tasks, (dict, list)):
        raise AssertionError(f"unexpected task list payload type: {type(tasks).__name__}")


def test_signer_address():
    mode = os.environ.get("NIUMA_AGENT_SIGNER_MODE", "").strip().lower()
    if mode not in {"private-key-test", ""}:
        return f"skipped: signer mode is {mode}"
    if not os.environ.get("NIUMA_AGENT_PRIVATE_KEY"):
        return "skipped: NIUMA_AGENT_PRIVATE_KEY not configured"
    result = run_json([
        "node",
        str(SCRIPT_DIR / "niuma_private_key_signer.mjs"),
        "address",
    ])
    if not result.get("ok") or not str(result.get("address", "")).startswith("0x"):
        raise AssertionError(result)
    return result["address"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Skip public API read")
    parser.add_argument("--skip-signer", action="store_true", help="Skip local signer check")
    args = parser.parse_args()

    checks = []
    for name, fn in [
        ("network-config", test_network_config),
        ("reviewer-rules", test_reviewer_rules),
        ("calldata", test_calldata),
    ]:
        try:
            detail = fn()
            checks.append(ok(name, detail))
        except Exception as exc:
            checks.append(fail(name, exc))

    if not args.offline:
        try:
            test_api_read()
            checks.append(ok("api-read"))
        except Exception as exc:
            checks.append(fail("api-read", exc))

    if not args.skip_signer:
        try:
            detail = test_signer_address()
            checks.append(ok("signer-address", detail))
        except Exception as exc:
            checks.append(fail("signer-address", exc))

    passed = all(item["ok"] for item in checks)
    print(json.dumps({"ok": passed, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
