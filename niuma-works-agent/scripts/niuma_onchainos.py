#!/usr/bin/env python3
"""Small OnchainOS adapter for NIUMA WORKS agents.

The rest of the skill should treat this module as the chain operating layer:
identity, balances, approvals, simulation, security scan, gas, signing,
watch sessions, task routing, and earnings snapshots.
"""

import json
import os
import re
import subprocess
import time


DEFAULT_NETWORK = os.environ.get("NIUMA_AGENT_NETWORK", "xlayer-mainnet").strip().lower()
NIUMA_TOKEN = os.environ.get("NIUMA_TOKEN_ADDRESS", "0x87669801A1FaD6DAD9dB70d27Ac752f452989667")


def run(cmd, timeout=90, cwd=None):
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "cmd": " ".join(str(part) for part in cmd),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def parse_json(result):
    try:
        return json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return None


def is_mainnet(network=None):
    return (network or DEFAULT_NETWORK).strip().lower() in {"xlayer", "xlayer-mainnet", "mainnet", "production", "prod"}


def chain(network=None):
    return os.environ.get("NIUMA_ONCHAINOS_CHAIN", "").strip() or ("xlayer" if is_mainnet(network) else "xlayer-testnet")


def _first_address(text):
    match = re.search(r"0x[a-fA-F0-9]{40}", text or "")
    return match.group(0) if match else None


def wallet_address(network=None):
    configured = os.environ.get("NIUMA_AGENT_WALLET")
    if configured:
        return configured
    for cmd in (
        ["onchainos", "wallet", "addresses", "--chain", chain(network)],
        ["onchainos", "wallet", "status"],
    ):
        result = run(cmd, timeout=30)
        address = _first_address(f"{result.get('stdout')}\n{result.get('stderr')}")
        if result.get("returncode") == 0 and address:
            return address
    return None


def account_info(network=None):
    status = run(["onchainos", "wallet", "status"], timeout=30)
    addresses = run(["onchainos", "wallet", "addresses", "--chain", chain(network)], timeout=30)
    status_json = parse_json(status) or {}
    address_json = parse_json(addresses) or {}
    data = status_json.get("data") if isinstance(status_json, dict) else {}
    addr_data = address_json.get("data") if isinstance(address_json, dict) else {}
    wallet = wallet_address(network)
    return {
        "loggedIn": bool(data.get("loggedIn")),
        "loginType": data.get("loginType"),
        "email": data.get("email"),
        "accountId": data.get("currentAccountId") or addr_data.get("accountId"),
        "accountName": data.get("currentAccountName") or addr_data.get("accountName"),
        "wallet": wallet,
        "chain": chain(network),
        "raw": {"status": status, "addresses": addresses},
    }


def role_wallets(default_wallet=None):
    default_wallet = default_wallet or wallet_address()
    return {
        "worker": os.environ.get("NIUMA_AGENT_WORKER_WALLET", default_wallet),
        "reviewer": os.environ.get("NIUMA_AGENT_REVIEWER_WALLET", default_wallet),
        "treasury": os.environ.get("NIUMA_AGENT_TREASURY_WALLET", default_wallet),
        "auditor": os.environ.get("NIUMA_AGENT_AUDITOR_WALLET", default_wallet),
    }


def bind_identity(state, default_wallet=None):
    account = account_info()
    wallet = default_wallet or account.get("wallet")
    identity = {
        "updatedAt": int(time.time()),
        "network": DEFAULT_NETWORK,
        "chain": chain(),
        "accountId": account.get("accountId"),
        "accountName": account.get("accountName"),
        "loginType": account.get("loginType"),
        "loggedIn": account.get("loggedIn"),
        "wallet": wallet,
        "roles": role_wallets(wallet),
    }
    state.setdefault("onchainos", {})["identity"] = identity
    if wallet:
        os.environ["NIUMA_AGENT_WALLET"] = wallet
    return identity


def balance(wallet=None, force=False):
    cmd = ["onchainos", "wallet", "balance", "--chain", chain()]
    if force:
        cmd.append("--force")
    return run(cmd, timeout=45)


def portfolio(wallet=None):
    wallet = wallet or wallet_address()
    if not wallet:
        return {"skipped": True, "reason": "wallet missing"}
    return run(["onchainos", "workflow", "portfolio", "--address", wallet, "--chain", chain()], timeout=60)


def approvals(wallet=None, limit=20):
    wallet = wallet or wallet_address()
    if not wallet:
        return {"skipped": True, "reason": "wallet missing"}
    return run(["onchainos", "security", "approvals", "--address", wallet, "--chain", chain(), "--limit", str(limit)], timeout=45)


def _token_rows(balance_result):
    payload = parse_json(balance_result) or {}
    details = (((payload.get("data") or {}).get("details")) or []) if isinstance(payload, dict) else []
    rows = []
    for detail in details:
        rows.extend(detail.get("tokenAssets") or [])
    return rows


def token_amount(balance_result, symbol="", token_address=""):
    symbol = symbol.lower()
    token_address = token_address.lower()
    for row in _token_rows(balance_result):
        row_symbol = str(row.get("symbol") or "").lower()
        row_token = str(row.get("tokenAddress") or "").lower()
        if (symbol and row_symbol == symbol) or (token_address and row_token == token_address):
            try:
                return float(row.get("balance") or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def allowance_amount(approvals_result, spender, token_address=NIUMA_TOKEN):
    payload = parse_json(approvals_result) or {}
    spender = spender.lower()
    token_address = token_address.lower()
    total = 0.0
    for page in (payload.get("data") or []):
        for row in page.get("dataList") or []:
            if str(row.get("approvalAddress") or "").lower() == spender and str(row.get("tokenAddress") or "").lower() == token_address:
                try:
                    total += float(row.get("remainAmtPrecise") or 0)
                except (TypeError, ValueError):
                    pass
    return total


def asset_readiness(wallet, required_niuma=0, spender="", gas_floor_okb=None):
    balances = balance(wallet)
    approval_data = approvals(wallet)
    okb = token_amount(balances, symbol="OKB")
    niuma = token_amount(balances, symbol="NIUMA", token_address=NIUMA_TOKEN)
    allowance = allowance_amount(approval_data, spender) if spender else 0.0
    gas_floor = float(gas_floor_okb if gas_floor_okb is not None else os.environ.get("NIUMA_AGENT_MIN_OKB_GAS", "0.001"))
    required = float(required_niuma or 0)
    return {
        "ok": okb >= gas_floor and niuma >= required and (not spender or allowance >= required),
        "wallet": wallet,
        "okb": okb,
        "niuma": niuma,
        "allowance": allowance,
        "requiredNiuma": required,
        "gasFloorOkb": gas_floor,
        "needsApprove": bool(spender and allowance < required),
        "needsStakeFunds": niuma < required,
        "needsGas": okb < gas_floor,
        "balance": balances,
        "approvals": approval_data,
    }


def policy():
    current_chain = chain()
    allowed_chains = {item.strip().lower() for item in os.environ.get("NIUMA_AGENT_ALLOWED_CHAINS", current_chain).split(",") if item.strip()}
    return {
        "ok": not allowed_chains or current_chain.lower() in allowed_chains,
        "chain": current_chain,
        "allowedChains": sorted(allowed_chains),
        "autonomous": os.environ.get("NIUMA_AGENT_AUTONOMOUS") == "1",
        "maxTaskReward": os.environ.get("NIUMA_AGENT_MAX_TASK_REWARD", ""),
        "allowedSpendTokens": os.environ.get("NIUMA_AGENT_ALLOWED_SPEND_TOKENS", ""),
    }


def simulation_ok(result):
    if result.get("returncode") != 0:
        return False
    payload = parse_json(result)
    if not isinstance(payload, dict):
        return True
    rows = payload.get("data")
    if isinstance(rows, list):
        return not any(str(row.get("failReason") or "").strip() for row in rows if isinstance(row, dict))
    return bool(payload.get("ok", True))


def critical_risk(result):
    if result.get("returncode") != 0:
        return True
    text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}".lower()
    return any(word in text for word in ("critical", "danger", "malicious", "phishing", "honeypot", "high risk", "high-risk"))


def simulate(wallet, to, data):
    return run(["onchainos", "gateway", "simulate", "--from", wallet, "--to", to, "--data", data, "--chain", chain()], timeout=60)


def tx_scan(wallet, to, data):
    return run(["onchainos", "security", "tx-scan", "--from", wallet, "--to", to, "--data", data, "--value", "0x0", "--chain", chain()], timeout=60)


def gas_context(wallet, to, data):
    return {
        "gas": run(["onchainos", "gateway", "gas", "--chain", chain()], timeout=45),
        "gasLimit": run(["onchainos", "gateway", "gas-limit", "--from", wallet, "--to", to, "--amount", "0", "--data", data, "--chain", chain()], timeout=45),
    }


def preflight(wallet, to, data, purpose="contract-call", required_niuma=0, spender=""):
    current_policy = policy()
    result = {
        "purpose": purpose,
        "wallet": wallet,
        "to": to,
        "chain": chain(),
        "policy": current_policy,
        "ok": False,
    }
    if not current_policy["ok"]:
        result["blocker"] = f"chain not allowed by policy: {current_policy['chain']}"
        return result
    result["assets"] = asset_readiness(wallet, required_niuma=required_niuma, spender=spender)
    result["simulation"] = simulate(wallet, to, data)
    if not simulation_ok(result["simulation"]):
        result["blocker"] = "gateway simulation failed"
        return result
    result["txScan"] = tx_scan(wallet, to, data)
    if critical_risk(result["txScan"]):
        result["blocker"] = "security tx-scan reported risk"
        return result
    result["gas"] = gas_context(wallet, to, data)
    result["ok"] = True
    return result


def contract_call(to, data, wallet=None, force=False):
    wallet = wallet or wallet_address()
    cmd = ["onchainos", "wallet", "contract-call", "--chain", chain(), "--to", to, "--input-data", data, "--amt", "0"]
    if wallet:
        cmd.extend(["--from", wallet])
    if force or os.environ.get("NIUMA_AGENT_AUTONOMOUS") == "1" or os.environ.get("NIUMA_ONCHAINOS_FORCE") == "1":
        cmd.append("--force")
    return run(cmd, timeout=180)


def sign_message(wallet, message, force=False):
    sig_scan = run(["onchainos", "security", "sig-scan", "--from", wallet, "--chain", chain(), "--sig-method", "personal_sign", "--message", message], timeout=30)
    if critical_risk(sig_scan):
        return {"ok": False, "reason": "signature scan reported risk", "sigScan": sig_scan}
    cmd = ["onchainos", "wallet", "sign-message", "--message", message, "--chain", chain(), "--from", wallet]
    if force or os.environ.get("NIUMA_AGENT_AUTONOMOUS") == "1" or os.environ.get("NIUMA_ONCHAINOS_FORCE") == "1":
        cmd.append("--force")
    signed = run(cmd, timeout=60)
    payload = parse_json(signed) or {}
    signature = payload.get("signature")
    if not signature and isinstance(payload.get("data"), dict):
        signature = payload["data"].get("signature")
    if not signature:
        match = re.search(r"0x[a-fA-F0-9]{120,}", signed.get("stdout") or "")
        signature = match.group(0) if match else None
    return {"ok": bool(signature), "signature": signature, "sigScan": sig_scan, "result": signed}


def start_watch(state, wallet=None):
    wallet = wallet or wallet_address()
    result = run(["onchainos", "ws", "start", "--chain", chain()], timeout=45)
    payload = parse_json(result) or {}
    session_id = payload.get("id") or payload.get("sessionId")
    if not session_id and isinstance(payload.get("data"), dict):
        session_id = payload["data"].get("id") or payload["data"].get("sessionId")
    if not session_id:
        match = re.search(r"[a-fA-F0-9-]{12,}", result.get("stdout") or "")
        session_id = match.group(0) if match else None
    state.setdefault("onchainos", {})["wsSessionId"] = session_id
    state["onchainos"]["watchWallet"] = wallet
    state["onchainos"]["wsStart"] = result
    return {"wallet": wallet, "chain": chain(), "sessionId": session_id, "result": result}


def poll_watch(state):
    session_id = state.get("onchainos", {}).get("wsSessionId")
    if not session_id:
        return {"ok": False, "reason": "no ws session id in state"}
    result = run(["onchainos", "ws", "poll", "--id", session_id], timeout=45)
    state.setdefault("onchainos", {})["lastPoll"] = {"time": int(time.time()), "result": result}
    return {"ok": result.get("returncode") == 0, "sessionId": session_id, "result": result}


ROUTES = [
    (("swap", "兑换", "买币", "卖币"), ["wallet", "gateway", "security", "swap", "token-scan"]),
    (("价格", "行情", "market", "token"), ["market", "token", "signal"]),
    (("聪明钱", "whale", "kol", "leaderboard"), ["tracker", "leaderboard", "signal"]),
    (("x402", "402", "付费api", "payment"), ["payment", "wallet", "security"]),
    (("defi", "staking", "质押", "借贷", "流动性"), ["defi", "portfolio", "security"]),
]


def route_task(text):
    lowered = str(text or "").lower()
    for keys, route in ROUTES:
        if any(key.lower() in lowered for key in keys):
            return route
    return ["wallet", "gateway", "security"]


def earnings_snapshot(state, wallet=None):
    wallet = wallet or wallet_address()
    tasks = state.get("tasks") or {}
    counts = {}
    for task in tasks.values():
        phase = task.get("phase", "unknown") if isinstance(task, dict) else "unknown"
        counts[phase] = counts.get(phase, 0) + 1
    balances = balance(wallet) if wallet else {"skipped": True, "reason": "wallet missing"}
    return {
        "wallet": wallet,
        "time": int(time.time()),
        "taskCounts": counts,
        "activeTaskId": state.get("active_task_id"),
        "followupRequired": bool(state.get("followup_required")),
        "okb": token_amount(balances, symbol="OKB") if wallet else 0,
        "niuma": token_amount(balances, symbol="NIUMA", token_address=NIUMA_TOKEN) if wallet else 0,
        "balance": balances,
    }
