#!/usr/bin/env python3
"""Autonomous NIUMA WORKS task runner.

Safe by default:
- Without NIUMA_AGENT_AUTONOMOUS=1 it evaluates, simulates, and drafts messages only.
- If requirements are unclear it sends a private clarification message and waits.
- Without NIUMA_API_TOKEN it records private-message outbox items instead of sending.
- Without an authorized signer it cannot write, but still keeps planning and reporting.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import niuma_api
import niuma_chain

CORE = niuma_chain.CORE
STATE_FILE = Path(os.environ.get("NIUMA_AGENT_STATE", ".niuma-agent-state.json"))
ENV_FILE = Path(os.environ.get("NIUMA_AGENT_ENV_FILE", ".niuma-agent.env"))
MIN_CLEARNESS = int(os.environ.get("NIUMA_AGENT_MIN_CLEARNESS", "65"))
DELIVERABLES_ROOT = Path(os.environ.get("NIUMA_AGENT_DELIVERABLES_DIR", "deliverables"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def load_env_file():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith("NIUMA_") and key not in os.environ:
            os.environ[key] = value


load_env_file()

DEFAULT_NETWORK = os.environ.get("NIUMA_AGENT_NETWORK", "xlayer-mainnet").strip().lower()
DEFAULT_LANGUAGE = os.environ.get("NIUMA_AGENT_LANGUAGE", os.environ.get("NIUMA_AGENT_LOCALE", "auto")).strip()
ONCHAINOS_SECURITY_SCAN = os.environ.get("NIUMA_ONCHAINOS_SECURITY_SCAN", "1") != "0"
ONCHAINOS_GAS_PREFLIGHT = os.environ.get("NIUMA_ONCHAINOS_GAS_PREFLIGHT", "1") != "0"
ONCHAINOS_BALANCE_PREFLIGHT = os.environ.get("NIUMA_ONCHAINOS_BALANCE_PREFLIGHT", "1") != "0"


def language_for(text=""):
    requested = (DEFAULT_LANGUAGE or "auto").lower()
    if requested in {"zh", "zh-cn", "cn", "chinese", "中文"}:
        return "zh-CN"
    if requested in {"en", "en-us", "english"}:
        return "en-US"
    return "zh-CN" if any("\u4e00" <= ch <= "\u9fff" for ch in str(text or "")) else "en-US"


def localized(zh, en, text=""):
    return zh if language_for(text) == "zh-CN" else en


DEFAULT_CAPABILITIES = {
    "coding",
    "smart-contract",
    "web3",
    "research",
    "data-analysis",
    "docs",
    "translation",
    "testing",
}

INDEPENDENT_KEYWORDS = {
    "合约": ("smart-contract", 35),
    "contract": ("smart-contract", 25),
    "solidity": ("smart-contract", 30),
    "代码": ("coding", 25),
    "写": ("coding", 15),
    "开发": ("coding", 25),
    "测试": ("testing", 20),
    "分析": ("data-analysis", 20),
    "文档": ("docs", 20),
    "翻译": ("translation", 20),
    "research": ("research", 20),
    "agent": ("coding", 10),
    "macd": ("smart-contract", 25),
}

HUMAN_OR_EXTERNAL_KEYWORDS = {
    "截图": "requires external account or screenshot evidence",
    "推特": "requires social account action",
    "twitter": "requires social account action",
    "关注": "requires social follow action",
    "转发": "requires social repost action",
    "tg": "requires Telegram identity or action",
    "telegram": "requires Telegram identity or action",
    "一键三连": "requires social engagement action",
}

UNCLEAR_KEYWORDS = {
    "私聊": "task asks to discuss privately before scope is clear",
    "详聊": "task asks to discuss privately before scope is clear",
    "联系": "task asks to contact employer before scope is clear",
    "待定": "acceptance criteria are not defined",
    "随意": "deliverable shape is ambiguous",
    "任意": "deliverable shape is ambiguous",
    "看情况": "scope is conditional or ambiguous",
    "private": "task asks for private discussion before scope is clear",
    "dm": "task asks for private discussion before scope is clear",
}

COLLABORATION_KEYWORDS = {
    "前端": "frontend specialist",
    "后端": "backend specialist",
    "审计": "security reviewer",
    "ui": "frontend/UI specialist",
    "设计": "designer",
    "复杂": "additional contributor",
}


def is_autonomous():
    return os.environ.get("NIUMA_AGENT_AUTONOMOUS") == "1"


def normalize_network(network=None):
    return (network or DEFAULT_NETWORK).strip().lower()


def is_mainnet(network=None):
    return normalize_network(network) in {"xlayer", "xlayer-mainnet", "mainnet", "production", "prod"}


def onchainos_chain(network=None):
    configured = os.environ.get("NIUMA_ONCHAINOS_CHAIN")
    if configured:
        return configured.strip()
    return "xlayer" if is_mainnet(network) else "xlayer-testnet"


def okx_wallet_address(network=None):
    chain = onchainos_chain(network)
    for cmd in (
        ["onchainos", "wallet", "addresses", "--chain", chain],
        ["onchainos", "wallet", "status"],
    ):
        result = run(cmd, timeout=30)
        text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
        match = re.search(r"0x[a-fA-F0-9]{40}", text)
        if result.get("returncode") == 0 and match:
            return match.group(0)
    return None


def wallet_setup_status(wallet=None, network=None):
    network = normalize_network(network)
    mode = signing_mode(network)
    has_wallet = bool(wallet or os.environ.get("NIUMA_AGENT_WALLET"))
    has_private_key = bool(os.environ.get("NIUMA_AGENT_PRIVATE_KEY"))
    messages = []
    ok = True

    if is_mainnet(network) and mode != "okx":
        ok = False
        messages.append("XLayer mainnet must use OKX OnchainOS signing mode, not private-key-test.")
    if mode == "private-key-test":
        if is_mainnet(network):
            ok = False
            messages.append("private-key-test is disabled for mainnet.")
        if not has_private_key:
            ok = False
            messages.append("Testnet private-key-test mode requires NIUMA_AGENT_PRIVATE_KEY in local .niuma-agent.env or process env.")
    elif mode == "okx":
        if not has_wallet:
            ok = False
            messages.append("OKX mode requires NIUMA_AGENT_WALLET or an OKX OnchainOS wallet session that can provide the agent wallet address.")
    else:
        ok = False
        messages.append(f"Unsupported NIUMA_AGENT_SIGNER_MODE: {mode}")

    if not os.environ.get("NIUMA_AGENT_AUTONOMOUS"):
        messages.append("Autonomous writes are disabled until NIUMA_AGENT_AUTONOMOUS=1 is configured.")
    if not os.environ.get("NIUMA_AGENT_MAX_TASK_REWARD"):
        messages.append("Set NIUMA_AGENT_MAX_TASK_REWARD to bound autonomous task selection.")

    return {
        "ok": ok,
        "network": network,
        "signerMode": mode,
        "hasWallet": has_wallet,
        "hasPrivateKey": has_private_key,
        "envFile": str(ENV_FILE),
        "messages": messages,
    }


def wallet_setup_instructions(network=None):
    network = normalize_network(network)
    if is_mainnet(network):
        return {
            "mode": "okx",
            "title": "Configure OKX OnchainOS agentic wallet",
            "steps": [
                "Register or connect an OKX OnchainOS agentic wallet for the agent owner.",
                "Authorize the agent wallet/session for XLayer mainnet contract calls inside the owner's policy limits.",
                "Set NIUMA_AGENT_SIGNER_MODE=okx and NIUMA_AGENT_WALLET=<agent wallet address>.",
                "Set NIUMA_AGENT_AUTONOMOUS=1 only after reward, token, chain, and spend limits are configured.",
                "Never configure NIUMA_AGENT_PRIVATE_KEY for mainnet.",
            ],
        }
    return {
        "mode": "private-key-test",
        "title": "Configure disposable XLayer testnet wallet",
        "steps": [
            "Create a new disposable test wallet outside chat. Do not reuse a personal or mainnet wallet.",
            "Fund it only with the minimum testnet tokens needed for NIUMA testing.",
            f"Put the private key only in local {ENV_FILE}; do not paste it into chat, task messages, logs, or proofs.",
            "Run setup-wallet --network xlayer-testnet --write-template to create a safe template, then edit the placeholder locally.",
            "After testing, rotate or discard the wallet.",
        ],
    }


def write_wallet_env_template(network):
    network = normalize_network(network)
    if ENV_FILE.exists():
        return {"wrote": False, "path": str(ENV_FILE), "reason": "env file already exists; not overwriting"}
    if is_mainnet(network):
        lines = [
            "NIUMA_AGENT_NETWORK=xlayer-mainnet",
            "NIUMA_AGENT_SIGNER_MODE=okx",
            "NIUMA_ONCHAINOS_CHAIN=xlayer",
            "NIUMA_AGENT_WALLET=0xYOUR_OKX_AGENTIC_WALLET_ADDRESS",
            "NIUMA_AGENT_AUTONOMOUS=0",
            "NIUMA_AGENT_MAX_TASK_REWARD=0",
            "NIUMA_AGENT_ALLOWED_CHAINS=xlayer",
            "NIUMA_AGENT_ALLOWED_SPEND_TOKENS=NIUMA,OKB,USDT",
        ]
    else:
        lines = [
            "NIUMA_AGENT_NETWORK=xlayer-testnet",
            "NIUMA_AGENT_SIGNER_MODE=private-key-test",
            "NIUMA_AGENT_PRIVATE_KEY=0xREPLACE_WITH_DISPOSABLE_TEST_PRIVATE_KEY",
            "NIUMA_AGENT_AUTONOMOUS=0",
            "NIUMA_AGENT_MAX_TASK_REWARD=0",
            "NIUMA_AGENT_ALLOWED_CHAINS=xlayer-testnet",
            "NIUMA_AGENT_ALLOWED_SPEND_TOKENS=NIUMA,OKB,USDT",
        ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"wrote": True, "path": str(ENV_FILE), "network": network}


def requirements_confirmed(task_state=None):
    return (
        os.environ.get("NIUMA_AGENT_REQUIREMENTS_CONFIRMED") == "1"
        or bool((task_state or {}).get("requirements_confirmed"))
    )


def capabilities():
    raw = os.environ.get("NIUMA_AGENT_CAPABILITIES")
    if not raw:
        return set(DEFAULT_CAPABILITIES)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def run(cmd, timeout=90):
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, encoding="utf-8", errors="replace")
    return {
        "cmd": " ".join(str(part) for part in cmd),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def load_state():
    if not STATE_FILE.exists():
        return {"outbox": [], "tasks": {}}
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    data.setdefault("outbox", [])
    data.setdefault("tasks", {})
    return data


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entry(path, base):
    path = Path(path)
    return {
        "path": str(path.relative_to(base)).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def deliverable_dir(task_id):
    configured = os.environ.get("NIUMA_AGENT_DELIVERABLE_PATH")
    if configured:
        return Path(configured)
    return DELIVERABLES_ROOT / f"task-{task_id}"


def build_delivery_manifest(task_id, title, root=None, delivery_uri=None):
    root = Path(root or deliverable_dir(task_id))
    if not root.exists():
        return {"ok": False, "reason": f"deliverable path does not exist: {root}", "root": str(root)}
    files = [path for path in root.rglob("*") if path.is_file() and path.name not in {"DELIVERY_MANIFEST.json"}]
    if not files:
        return {"ok": False, "reason": f"deliverable path has no files: {root}", "root": str(root)}

    package_path = root / f"task-{task_id}-delivery.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root))
    files.append(package_path)

    manifest = {
        "ok": True,
        "taskId": int(task_id),
        "title": title,
        "createdAt": int(time.time()),
        "root": str(root),
        "deliveryUri": delivery_uri or os.environ.get("NIUMA_AGENT_DELIVERY_URI") or "",
        "package": package_path.name,
        "files": [file_entry(path, root) for path in sorted(files)],
        "instructions": "Open README.md first if present. Verify file SHA-256 values against this manifest.",
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    manifest["manifestSha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = root / "DELIVERY_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def delivery_message(task_id, title, manifest):
    file_lines = "; ".join(f"{item['path']} sha256={item['sha256'][:12]}" for item in manifest.get("files", [])[:6])
    uri = manifest.get("deliveryUri")
    if language_for(title) == "zh-CN":
        uri_text = f"交付链接：{uri}。" if uri else f"交付包已生成在本地路径：{manifest.get('root')}。"
        return (
            f"交付确认：任务 #{task_id}《{title}》已准备交付物。"
            f"{uri_text}"
            f"清单：DELIVERY_MANIFEST.json，manifestSha256={manifest.get('manifestSha256')}。"
            f"文件：{file_lines}。"
        )
    uri_text = f"Delivery link: {uri}. " if uri else f"Delivery package generated locally at: {manifest.get('root')}. "
    return (
        f"Delivery update: task #{task_id} \"{title}\" is ready. "
        f"{uri_text}"
        f"Manifest: DELIVERY_MANIFEST.json, manifestSha256={manifest.get('manifestSha256')}. "
        f"Files: {file_lines}."
    )


def delivery_ready(manifest, message_result):
    if not manifest.get("ok"):
        return False, manifest.get("reason", "delivery manifest failed")
    if manifest.get("deliveryUri"):
        return True, "delivery URI is available"
    if message_result.get("sent"):
        return True, "delivery details sent by private message"
    if os.environ.get("NIUMA_AGENT_ALLOW_UNSENT_DELIVERY") == "1":
        return True, "test override allows local/outbox delivery"
    return False, "no public delivery URI and private delivery message was not sent"


def token_symbols():
    data = niuma_api.chain_data("sj_chain_tokens", 1, 200, "sort_order", "asc")
    return {str(row.get("token_address", "")).lower(): row.get("symbol", "TOKEN") for row in data.get("list", [])}


def open_tasks():
    data = niuma_api.chain_data("sj_tasks", 1, 50, "task_id", "desc")
    tasks = []
    for row in data.get("list", []):
        if int(row.get("status", 0)) != 1:
            continue
        if int(row.get("current_participants", 0)) >= int(row.get("max_participants", 0)):
            continue
        tasks.append(row)
    return tasks


def task_text(task):
    return " ".join(str(task.get(key, "") or "") for key in ("title", "description", "requirements")).lower()


def requirement_clarity(task):
    title = str(task.get("title", "") or "").strip()
    description = str(task.get("description", "") or "").strip()
    requirements = str(task.get("requirements", "") or "").strip()
    combined = " ".join([title, description, requirements]).lower()
    score = 35
    reasons = []
    questions = []

    if title:
        score += 10
    else:
        reasons.append("missing title")
        questions.append("请补充任务标题或一句话目标。")
    if len(description) >= 12:
        score += 20
    else:
        reasons.append("description is too short")
        questions.append("请补充背景、目标和边界。")
    if len(requirements) >= 12:
        score += 20
    else:
        reasons.append("requirements are too short")
        questions.append("请补充验收标准和提交格式。")
    if any(word in combined for word in ("交付", "提交", "proof", "源码", "链接", "地址", "哈希", "测试")):
        score += 10
    else:
        reasons.append("deliverable is not explicit")
        questions.append("请确认最终交付物是文件、链接、仓库、交易哈希还是其他 proof。")
    for word, reason in UNCLEAR_KEYWORDS.items():
        if word in combined:
            score -= 25
            reasons.append(reason)

    if any(word in combined for word in ("合约", "contract", "solidity")):
        questions.append("合约任务请确认：只需要源码文件，还是需要部署地址、测试用例和交易哈希？")
    if any(word in combined for word in ("前端", "后端", "ui", "设计", "复杂")):
        questions.append("如果需要多人协作，请确认可拆分的子任务、预算和截止时间。")

    seen = set()
    unique_questions = []
    for question in questions:
        if question not in seen:
            seen.add(question)
            unique_questions.append(question)

    return {
        "score": max(0, min(100, score)),
        "clear": score >= MIN_CLEARNESS,
        "reasons": reasons,
        "questions": unique_questions[:5],
        "threshold": MIN_CLEARNESS,
    }


def evaluate_task(task, symbols=None):
    symbols = symbols or token_symbols()
    text = task_text(task)
    caps = capabilities()
    clarity = requirement_clarity(task)
    score = 45
    reasons = []
    blockers = []
    matched = []

    for word, (cap, points) in INDEPENDENT_KEYWORDS.items():
        if word.lower() in text:
            matched.append(cap)
            if cap in caps:
                score += points
                reasons.append(f"matches capability: {cap}")
            else:
                score -= 15
                blockers.append(f"missing capability: {cap}")

    for word, reason in HUMAN_OR_EXTERNAL_KEYWORDS.items():
        if word.lower() in text:
            score -= 35
            blockers.append(reason)

    collaboration = []
    for word, role in COLLABORATION_KEYWORDS.items():
        if word.lower() in text:
            collaboration.append(role)

    reward = float(task.get("bounty_per_user", 0) or 0)
    symbol = symbols.get(str(task.get("token_address", "")).lower(), "TOKEN")
    max_reward = float(os.environ.get("NIUMA_AGENT_MAX_TASK_REWARD", "1000000000"))
    allowed_tokens = {x.strip().lower() for x in os.environ.get("NIUMA_AGENT_ALLOWED_SPEND_TOKENS", "NIUMA,OKB,USDT").split(",")}
    if reward > max_reward:
        score -= 100
        blockers.append("reward exceeds authorization policy")
    if symbol.lower() not in allowed_tokens:
        score -= 100
        blockers.append(f"token not allowed by policy: {symbol}")

    if not clarity["clear"]:
        action = "clarify"
    elif score >= 70 and not blockers:
        action = "accept"
    elif score >= 55 and not any("requires social" in item for item in blockers):
        action = "message-first"
    elif collaboration and score >= 35:
        action = "collaborate"
    else:
        action = "skip"

    return {
        "taskId": int(task.get("task_id", 0)),
        "title": task.get("title", ""),
        "creator": task.get("creator", ""),
        "reward": reward,
        "token": symbol,
        "score": max(0, min(100, score)),
        "action": action,
        "clarity": clarity,
        "capabilities": sorted(set(matched)),
        "blockers": blockers,
        "reasons": reasons,
        "collaborationRoles": sorted(set(collaboration)),
    }


def evaluate_tasks():
    symbols = token_symbols()
    tasks = open_tasks()
    evaluations = [evaluate_task(task, symbols) for task in tasks]
    priority = {"accept": 4, "message-first": 3, "collaborate": 2, "clarify": 1, "skip": 0}
    evaluations.sort(key=lambda item: (priority.get(item["action"], 0), item["score"], item["reward"]), reverse=True)
    return evaluations


def choose_task(tasks):
    symbols = token_symbols()
    evaluated = [(evaluate_task(task, symbols), task) for task in tasks]
    eligible = [(ev, task) for ev, task in evaluated if ev["action"] in {"accept", "message-first", "collaborate", "clarify"}]
    if not eligible:
        return None, [ev for ev, _ in evaluated]
    priority = {"accept": 4, "message-first": 3, "collaborate": 2, "clarify": 1}
    eligible.sort(key=lambda item: (priority.get(item[0]["action"], 0), item[0]["score"], item[0]["reward"]), reverse=True)
    return eligible[0][1], [ev for ev, _ in evaluated]


def outbox(state, peer, task_id, content, reason="NIUMA_API_TOKEN missing or unusable"):
    item = {
        "time": int(time.time()),
        "to": peer,
        "taskId": int(task_id),
        "content": content,
        "reason": reason,
    }
    state.setdefault("outbox", []).append(item)
    return {"sent": False, "reason": reason, "outboxItem": item}


def send_progress(state, wallet, peer, task_id, content):
    token = os.environ.get("NIUMA_API_TOKEN") or ensure_api_token(wallet)
    if not token:
        return outbox(state, peer, task_id, content)
    try:
        data = niuma_api.request_json("POST", "/message/send", body={
            "to_address": peer,
            "content": content,
            "task_id": int(task_id),
            "type": "text",
            "sender": wallet,
            "from_address": wallet,
            "wallet": wallet,
        }, token=token)
        return {"sent": True, "data": data}
    except Exception as exc:
        return outbox(state, peer, task_id, content, reason=f"message send failed: {exc}")


def ensure_api_token(wallet):
    try:
        nonce_data = niuma_api.request_json("GET", "/auth/nonce", params={"address": wallet})
        nonce = nonce_data.get("nonce") if isinstance(nonce_data, dict) else nonce_data
        message = f"Sign this message to authenticate: {nonce}"
        sig_scan = run([
            "onchainos",
            "security",
            "sig-scan",
            "--from",
            wallet,
            "--chain",
            onchainos_chain(),
            "--sig-method",
            "personal_sign",
            "--message",
            message,
        ], timeout=30) if signing_mode() == "okx" else {"skipped": True}
        if isinstance(sig_scan, dict) and not sig_scan.get("skipped") and critical_risk_found(sig_scan):
            return None
        if signing_mode() == "okx":
            cmd = [
                "onchainos",
                "wallet",
                "sign-message",
                "--message",
                message,
                "--chain",
                onchainos_chain(),
                "--from",
                wallet,
            ]
            if is_autonomous() or os.environ.get("NIUMA_ONCHAINOS_FORCE") == "1":
                cmd.append("--force")
            signed = run(cmd, timeout=60)
        elif signing_mode() == "private-key-test" and os.environ.get("NIUMA_AGENT_PRIVATE_KEY"):
            script = Path(__file__).with_name("niuma_private_key_signer.mjs")
            signed = run(["node", str(script), "sign-message", "--message", message], timeout=30)
        else:
            return None
        if signed["returncode"] != 0:
            return None
        payload = parse_json_output(signed) or {}
        signature = payload.get("signature")
        if not signature and isinstance(payload.get("data"), dict):
            signature = payload["data"].get("signature")
        if not signature:
            match = re.search(r"0x[a-fA-F0-9]{120,}", signed.get("stdout") or "")
            signature = match.group(0) if match else None
        if not signature:
            return None
        login = niuma_api.request_json("POST", "/auth/login", body={"address": wallet, "signature": signature})
        token = login.get("token") if isinstance(login, dict) else None
        if token:
            os.environ["NIUMA_API_TOKEN"] = token
        return token
    except Exception:
        return None


def progress_text(task_id, title, status, next_action, proof_or_tx=""):
    if language_for(title) == "zh-CN":
        suffix = f" 证明/交易：{proof_or_tx}" if proof_or_tx else ""
        return f"进度更新：任务 #{task_id}《{title}》。状态：{status}。下一步：{next_action}。{suffix}"
    suffix = f" Proof/tx: {proof_or_tx}" if proof_or_tx else ""
    return f"Progress update: task #{task_id} \"{title}\". Status: {status}. Next: {next_action}.{suffix}"


def clarification_message(task_id, title, clarity):
    if language_for(title) == "zh-CN":
        questions = clarity.get("questions") or ["请补充验收标准、提交格式和最终 proof 要求。"]
        question_text = " ".join(f"{idx + 1}. {question}" for idx, question in enumerate(questions))
        return (
            f"需求确认：我已评估任务 #{task_id}《{title}》，当前需求清晰度 "
            f"{clarity.get('score')}/{clarity.get('threshold')}，需要先确认后再接单执行。"
            f"{question_text}"
        )
    questions = clarity.get("questions") or ["Please clarify the acceptance criteria, submission format, and final proof requirements."]
    question_text = " ".join(f"{idx + 1}. {question}" for idx, question in enumerate(questions))
    return (
        f"Scope check: I reviewed task #{task_id} \"{title}\". Current clarity is "
        f"{clarity.get('score')}/{clarity.get('threshold')}; I need confirmation before accepting and executing. "
        f"{question_text}"
    )


def collaboration_plan(task, evaluation):
    title = task.get("title", f"Task #{task.get('task_id')}")
    roles = evaluation.get("collaborationRoles") or ["specialist"]
    subtasks = []
    for role in roles:
        if language_for(title) == "zh-CN":
            subtasks.append({
                "role": role,
                "title": f"协作子任务：{title} - {role}",
                "description": f"协助完成 NIUMA 主任务 #{task.get('task_id')}：{title}。负责 {role} 部分，交付可验证文件、链接或说明。",
                "requirements": "提交可验证交付物链接、关键步骤说明、测试结果或截图证明。",
            })
        else:
            subtasks.append({
                "role": role,
                "title": f"Collaboration subtask: {title} - {role}",
                "description": f"Help complete NIUMA parent task #{task.get('task_id')}: {title}. Own the {role} portion and deliver verifiable files, links, or notes.",
                "requirements": "Submit a verifiable deliverable link, key steps, test results, or screenshot proof.",
            })
    return subtasks


def simulate_with_okx(wallet, to, data):
    return run(["onchainos", "gateway", "simulate", "--from", wallet, "--to", to, "--data", data, "--chain", onchainos_chain()])


def okx_simulation_ok(sim):
    if sim.get("returncode") != 0:
        return False
    try:
        payload = json.loads(sim.get("stdout") or "{}")
    except json.JSONDecodeError:
        return True
    rows = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(rows, list):
        return not any(str(row.get("failReason") or "").strip() for row in rows if isinstance(row, dict))
    return bool(payload.get("ok", True))


def parse_json_output(result):
    try:
        return json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return None


def critical_risk_found(result):
    if result.get("returncode") != 0:
        return True
    text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}".lower()
    critical_words = ("critical", "danger", "malicious", "phishing", "honeypot", "high risk", "high-risk")
    return any(word in text for word in critical_words)


def chain_policy_ok():
    chain = onchainos_chain()
    allowed = {item.strip().lower() for item in os.environ.get("NIUMA_AGENT_ALLOWED_CHAINS", chain).split(",") if item.strip()}
    ok = not allowed or chain.lower() in allowed
    return {"ok": ok, "chain": chain, "allowedChains": sorted(allowed), "reason": "" if ok else f"chain not allowed by policy: {chain}"}


def onchainos_balance_snapshot(wallet, force=False):
    if not wallet or not ONCHAINOS_BALANCE_PREFLIGHT:
        return {"skipped": True, "reason": "wallet missing or balance preflight disabled"}
    cmd = ["onchainos", "wallet", "balance", "--chain", onchainos_chain()]
    if force:
        cmd.append("--force")
    return run(cmd, timeout=45)


def onchainos_approval_snapshot(wallet):
    if not wallet or not ONCHAINOS_SECURITY_SCAN:
        return {"skipped": True, "reason": "wallet missing or security scan disabled"}
    return run(["onchainos", "security", "approvals", "--address", wallet, "--chain", onchainos_chain(), "--limit", "20"], timeout=45)


def onchainos_security_tx_scan(wallet, to, data):
    if not ONCHAINOS_SECURITY_SCAN:
        return {"skipped": True, "reason": "NIUMA_ONCHAINOS_SECURITY_SCAN=0"}
    return run([
        "onchainos",
        "security",
        "tx-scan",
        "--from",
        wallet,
        "--to",
        to,
        "--data",
        data,
        "--value",
        "0x0",
        "--chain",
        onchainos_chain(),
    ], timeout=60)


def onchainos_gas_context(wallet, to, data):
    if not ONCHAINOS_GAS_PREFLIGHT:
        return {"skipped": True, "reason": "NIUMA_ONCHAINOS_GAS_PREFLIGHT=0"}
    return {
        "gas": run(["onchainos", "gateway", "gas", "--chain", onchainos_chain()], timeout=45),
        "gasLimit": run([
            "onchainos",
            "gateway",
            "gas-limit",
            "--from",
            wallet,
            "--to",
            to,
            "--amount",
            "0",
            "--data",
            data,
            "--chain",
            onchainos_chain(),
        ], timeout=45),
    }


def onchainos_preflight(wallet, to, data, purpose="contract-call"):
    policy = chain_policy_ok()
    result = {
        "purpose": purpose,
        "wallet": wallet,
        "to": to,
        "chain": onchainos_chain(),
        "policy": policy,
        "ok": False,
    }
    if not policy["ok"]:
        result["blocker"] = policy["reason"]
        return result
    result["balance"] = onchainos_balance_snapshot(wallet)
    result["simulation"] = simulate_with_okx(wallet, to, data)
    if not okx_simulation_ok(result["simulation"]):
        result["blocker"] = "OKX gateway simulation failed"
        return result
    result["txScan"] = onchainos_security_tx_scan(wallet, to, data)
    if isinstance(result["txScan"], dict) and result["txScan"].get("skipped"):
        pass
    elif critical_risk_found(result["txScan"]):
        result["blocker"] = "OnchainOS security tx-scan reported risk"
        return result
    result["gas"] = onchainos_gas_context(wallet, to, data)
    result["ok"] = True
    return result


def contract_call_with_okx(to, data, wallet=None):
    cmd = ["onchainos", "wallet", "contract-call", "--chain", onchainos_chain(), "--to", to, "--input-data", data, "--amt", "0"]
    if wallet:
        cmd.extend(["--from", wallet])
    if is_autonomous() or os.environ.get("NIUMA_ONCHAINOS_FORCE") == "1":
        cmd.append("--force")
    return run(cmd)


def contract_call_with_private_key(to, data, task_id, action="accept"):
    script = Path(__file__).with_name("niuma_private_key_signer.mjs")
    return run(["node", str(script), action, "--task-id", str(task_id), "--to", to, "--data", data], timeout=180)


def onchainos_status(wallet=None, refresh_balance=False):
    wallet = wallet or os.environ.get("NIUMA_AGENT_WALLET")
    status = run(["onchainos", "wallet", "status"], timeout=30)
    addresses = run(["onchainos", "wallet", "addresses", "--chain", onchainos_chain()], timeout=30)
    detected = wallet or okx_wallet_address()
    return {
        "network": DEFAULT_NETWORK,
        "chain": onchainos_chain(),
        "signerMode": signing_mode(),
        "wallet": detected,
        "walletStatus": status,
        "addresses": addresses,
        "balance": onchainos_balance_snapshot(detected, force=refresh_balance) if detected else {"skipped": True, "reason": "wallet missing"},
        "approvals": onchainos_approval_snapshot(detected) if detected else {"skipped": True, "reason": "wallet missing"},
        "policy": {
            "autonomous": is_autonomous(),
            "chain": chain_policy_ok(),
            "maxTaskReward": os.environ.get("NIUMA_AGENT_MAX_TASK_REWARD", ""),
            "allowedSpendTokens": os.environ.get("NIUMA_AGENT_ALLOWED_SPEND_TOKENS", ""),
        },
    }


def start_onchainos_watch(wallet=None):
    wallet = wallet or os.environ.get("NIUMA_AGENT_WALLET")
    state = load_state()
    result = run(["onchainos", "ws", "start", "--chain", onchainos_chain()], timeout=45)
    session_id = None
    payload = parse_json_output(result)
    if isinstance(payload, dict):
        session_id = payload.get("id") or payload.get("sessionId")
        if not session_id and isinstance(payload.get("data"), dict):
            session_id = payload["data"].get("id") or payload["data"].get("sessionId")
    if not session_id:
        match = re.search(r"[a-fA-F0-9-]{12,}", result.get("stdout") or "")
        session_id = match.group(0) if match else None
    state.setdefault("onchainos", {})["wsSessionId"] = session_id
    state["onchainos"]["wsStart"] = result
    state["onchainos"]["watchWallet"] = wallet
    save_state(state)
    return {"wallet": wallet, "chain": onchainos_chain(), "sessionId": session_id, "result": result}


def poll_onchainos_watch():
    state = load_state()
    session_id = state.get("onchainos", {}).get("wsSessionId")
    if not session_id:
        return {"ok": False, "reason": "no ws session id in state; run start-watch first"}
    result = run(["onchainos", "ws", "poll", "--id", session_id], timeout=45)
    state.setdefault("onchainos", {})["lastPoll"] = {"time": int(time.time()), "result": result}
    save_state(state)
    return {"ok": result.get("returncode") == 0, "sessionId": session_id, "result": result}


def signing_mode(network=None):
    configured = os.environ.get("NIUMA_AGENT_SIGNER_MODE")
    if configured:
        return configured.strip().lower()
    return "okx" if is_mainnet(network) else "private-key-test"


def derive_wallet_from_private_key():
    script = Path(__file__).with_name("niuma_private_key_signer.mjs")
    result = run(["node", str(script), "address"], timeout=30)
    if result["returncode"] != 0:
        raise RuntimeError("wallet required and private-key-test address derivation failed: " + (result["stderr"] or result["stdout"]))
    data = json.loads(result["stdout"])
    if not data.get("ok") or not data.get("address"):
        raise RuntimeError("wallet required and private-key-test address derivation returned no address")
    return data["address"]


def maybe_auto_stake(wallet, task_id, target_stake=None):
    output = {"wrote": False}
    if not is_autonomous():
        output["reason"] = "autonomous writes disabled"
        return output
    if os.environ.get("NIUMA_AGENT_AUTO_STAKE", "1") != "1":
        output["reason"] = "NIUMA_AGENT_AUTO_STAKE disabled"
        return output
    diag = niuma_chain.stake_diagnostics(wallet, target_stake)
    output["diagnostics"] = {k: v for k, v in diag.items() if k not in {"approveCalldata", "stakeCalldata"}}
    if not diag.get("needsStake"):
        output["reason"] = "stake not needed"
        return output
    if not diag.get("hasEnoughBalance"):
        output["reason"] = "NIUMA balance below needed stake"
        return output
    if diag.get("needsApprove"):
        if os.environ.get("NIUMA_AGENT_AUTO_APPROVE", "1") != "1":
            output["reason"] = "approval needed before staking; auto approve disabled"
            return output
        approve_preflight = onchainos_preflight(wallet, niuma_chain.NIUMA_TOKEN, diag["approveCalldata"], purpose="approve-NIUMA-stake")
        output["approvePreflight"] = approve_preflight
        if signing_mode() != "private-key-test" and not approve_preflight.get("ok"):
            output["reason"] = approve_preflight.get("blocker", "approval preflight failed")
            return output
        if signing_mode() == "private-key-test":
            approve_tx = contract_call_with_private_key(niuma_chain.NIUMA_TOKEN, diag["approveCalldata"], task_id)
        else:
            approve_tx = contract_call_with_okx(niuma_chain.NIUMA_TOKEN, diag["approveCalldata"], wallet)
        output["approveTx"] = approve_tx
        if approve_tx["returncode"] != 0:
            output["reason"] = "approval transaction failed"
            return output
        diag = niuma_chain.stake_diagnostics(wallet, target_stake)
        output["diagnosticsAfterApprove"] = {k: v for k, v in diag.items() if k not in {"approveCalldata", "stakeCalldata"}}
        if diag.get("needsApprove"):
            output["reason"] = "approval completed but allowance is still insufficient"
            return output
    stake_preflight = onchainos_preflight(wallet, niuma_chain.USER_PROFILE, diag["stakeCalldata"], purpose="stake-NIUMA")
    output["stakePreflight"] = stake_preflight
    if signing_mode() != "private-key-test" and not stake_preflight.get("ok"):
        output["reason"] = stake_preflight.get("blocker", "stake preflight failed")
        return output
    if signing_mode() == "private-key-test":
        tx = contract_call_with_private_key(niuma_chain.USER_PROFILE, diag["stakeCalldata"], task_id)
    else:
        tx = contract_call_with_okx(niuma_chain.USER_PROFILE, diag["stakeCalldata"], wallet)
    output["stakeTx"] = tx
    output["wrote"] = tx["returncode"] == 0
    return output


def accept_task(state, wallet, chain_task):
    task_id = int(chain_task["id"])
    data = niuma_chain.calldata_participate(task_id)
    can_accept = niuma_chain.can_accept(wallet, chain_task["bountyPerUser"], chain_task["tokenAddress"])
    preflight = onchainos_preflight(wallet, CORE, data, purpose="participateTask")
    result = {
        "canAccept": can_accept,
        "calldata": data,
        "onchainosPreflight": preflight,
        "wrote": False,
    }
    if not can_accept:
        stake_attempt = maybe_auto_stake(wallet, task_id, chain_task["bountyPerUser"])
        result["stakeAttempt"] = stake_attempt
        if stake_attempt.get("wrote"):
            can_accept = niuma_chain.can_accept(wallet, chain_task["bountyPerUser"], chain_task["tokenAddress"])
            result["canAcceptAfterStake"] = can_accept
            result["canAccept"] = can_accept
            if can_accept:
                preflight = onchainos_preflight(wallet, CORE, data, purpose="participateTask-after-stake")
                result["onchainosPreflightAfterStake"] = preflight
            else:
                result["nextAction"] = "Staked but canAcceptTask still returned false."
                return result
        else:
            result["nextAction"] = "Not writing because canAcceptTask returned false and auto-stake did not complete."
            return result
    if not can_accept:
        result["nextAction"] = "Not writing because canAcceptTask returned false."
        return result
    if not is_autonomous():
        result["nextAction"] = "Autonomous writes disabled. Set NIUMA_AGENT_AUTONOMOUS=1 and configure signer."
        return result
    if signing_mode() != "private-key-test" and not preflight.get("ok"):
        result["nextAction"] = f"Not writing because OnchainOS preflight failed: {preflight.get('blocker')}"
        return result
    if signing_mode() == "private-key-test":
        tx = contract_call_with_private_key(CORE, data, task_id)
    else:
        tx = contract_call_with_okx(CORE, data, wallet)
    result["signerMode"] = signing_mode()
    result["contractCall"] = tx
    result["wrote"] = tx["returncode"] == 0
    if tx["returncode"] == 0:
        result["nextAction"] = "Accepted. Execute the work and submit proof when complete."
    else:
        result["nextAction"] = "Contract call failed; inspect stderr/stdout."
    return result


def submit_task(wallet, task_id, proof, metadata):
    data = niuma_chain.calldata_submit(task_id, proof, metadata)
    preflight = onchainos_preflight(wallet, CORE, data, purpose="submitProof")
    result = {"proof": proof, "metadata": metadata, "calldata": data, "onchainosPreflight": preflight, "wrote": False}
    if not is_autonomous():
        result["nextAction"] = "Autonomous writes disabled; proof submission not sent."
        return result
    if signing_mode() != "private-key-test" and not preflight.get("ok"):
        result["nextAction"] = f"Proof submission preflight failed; not sending: {preflight.get('blocker')}"
        return result
    if signing_mode() == "private-key-test":
        tx = contract_call_with_private_key(CORE, data, task_id, action="accept")
    else:
        tx = contract_call_with_okx(CORE, data, wallet)
    result["signerMode"] = signing_mode()
    result["contractCall"] = tx
    result["wrote"] = tx["returncode"] == 0
    result["nextAction"] = "Submitted proof." if result["wrote"] else "Proof submission transaction failed."
    return result


def bind_inviter(wallet, inviter, execute=False):
    current = niuma_chain.inviter(wallet)
    result = {
        "wallet": wallet,
        "requestedInviter": inviter,
        "currentInviter": current,
        "wrote": False,
    }
    if current.lower() == inviter.lower():
        result["ready"] = True
        result["nextAction"] = "Inviter already bound."
        return result
    if current.lower() != niuma_chain.ZERO:
        result["ready"] = False
        result["nextAction"] = "Wallet already has a different inviter."
        return result
    data = niuma_chain.calldata_bind_inviter(inviter)
    preflight = onchainos_preflight(wallet, niuma_chain.REFERRAL_SYSTEM, data, purpose="bindInviter")
    result.update({"calldata": data, "onchainosPreflight": preflight})
    if not preflight.get("ok"):
        result["ready"] = False
        result["nextAction"] = f"Inviter binding preflight failed: {preflight.get('blocker')}"
        return result
    if not execute:
        result["ready"] = True
        result["nextAction"] = "Dry-run only; pass --execute or set NIUMA_AGENT_AUTONOMOUS=1 to bind inviter."
        return result
    tx = contract_call_with_okx(niuma_chain.REFERRAL_SYSTEM, data, wallet)
    result["contractCall"] = tx
    result["wrote"] = tx["returncode"] == 0
    result["ready"] = result["wrote"]
    result["nextAction"] = "Inviter bound." if result["wrote"] else "Inviter binding transaction failed."
    return result


def is_participant(task_id, wallet):
    try:
        return any(addr.lower() == wallet.lower() for addr in niuma_chain.get_task_participants(task_id))
    except Exception:
        return False


def mark_active_task(state, task_id, chain_task, phase="accepted", proof="", metadata="", note=""):
    task_state = state.setdefault("tasks", {}).setdefault(str(task_id), {})
    task_state.update({
        "phase": phase,
        "task_id": task_id,
        "title": chain_task.get("title"),
        "creator": chain_task.get("creator"),
        "acceptedAt": int(time.time()) if not task_state.get("acceptedAt") else task_state.get("acceptedAt"),
        "followupHeartbeat": True,
    })
    if proof:
        task_state["proof"] = proof
    if metadata:
        task_state["metadata"] = metadata
    if note:
        task_state["nextAction"] = note
    state["active_task_id"] = task_id
    state["followup_required"] = True
    return task_state


def complete_task_once(wallet, task_id, proof="", metadata="", inviter="", execute=False):
    if execute:
        os.environ["NIUMA_AGENT_AUTONOMOUS"] = "1"
        os.environ.setdefault("NIUMA_ONCHAINOS_FORCE", "1")
    state = load_state()
    chain_task = niuma_chain.task(task_id)
    output = {
        "taskId": task_id,
        "wallet": wallet,
        "execute": execute,
        "task": {
            "title": chain_task.get("title"),
            "creator": chain_task.get("creator"),
            "status": chain_task.get("status"),
            "currentParticipants": chain_task.get("currentParticipants"),
            "maxParticipants": chain_task.get("maxParticipants"),
        },
        "steps": [],
    }
    setup = wallet_setup_status(wallet)
    output["setup"] = setup
    if not setup["ok"]:
        output["status"] = "setup_required"
        return output
    if inviter:
        step = bind_inviter(wallet, inviter, execute=execute)
        output["steps"].append({"name": "bind-inviter", **step})
        if not step.get("ready"):
            output["status"] = "blocked"
            return output
    accepted_now = False
    if is_participant(task_id, wallet):
        output["steps"].append({"name": "accept", "wrote": False, "ready": True, "nextAction": "Already participating; accept skipped."})
    else:
        step = accept_task(state, wallet, chain_task)
        output["steps"].append({"name": "accept", **step})
        if not step.get("wrote"):
            output["status"] = "accept-blocked"
            save_state(state)
            return output
        accepted_now = True
    if accepted_now or is_participant(task_id, wallet):
        mark_active_task(state, task_id, chain_task, phase="accepted", proof=proof, metadata=metadata, note="Follow heartbeat until submitted or completed.")
    if proof:
        step = submit_task(wallet, task_id, proof, metadata)
        output["steps"].append({"name": "submit", **step})
        output["status"] = "submitted" if step.get("wrote") else "submit-blocked"
        if step.get("wrote"):
            mark_active_task(state, task_id, chain_task, phase="submitted", proof=proof, metadata=metadata, note="Waiting for employer review or index confirmation.")
    else:
        output["status"] = "accepted"
        output["nextAction"] = "Task accepted. Heartbeat will keep following this task until proof is submitted and the task completes."
    save_state(state)
    return output


def prepare_delivery(state, wallet, peer, task_id, title):
    uri = os.environ.get("NIUMA_AGENT_DELIVERY_URI", "")
    manifest = build_delivery_manifest(task_id, title, delivery_uri=uri)
    result = {"manifest": manifest}
    if not manifest.get("ok"):
        result["ready"] = False
        result["reason"] = manifest.get("reason")
        return result
    message = send_progress(state, wallet, peer, task_id, delivery_message(task_id, title, manifest))
    ready, reason = delivery_ready(manifest, message)
    result.update({
        "message": message,
        "ready": ready,
        "reason": reason,
        "proof": uri or manifest.get("manifestSha256"),
        "metadata": json.dumps({
            "deliveryUri": uri,
            "manifestSha256": manifest.get("manifestSha256"),
            "package": manifest.get("package"),
        }, ensure_ascii=False),
    })
    return result


def load_active_task(active_id):
    try:
        if not active_id or int(active_id) <= 0:
            return None
        chain_task = niuma_chain.task(int(active_id))
        if int(chain_task.get("id") or 0) <= 0:
            return None
        return {
            "task_id": chain_task["id"],
            "creator": chain_task["creator"],
            "title": chain_task["title"],
            "description": chain_task["description"],
            "requirements": chain_task["requirements"],
            "bounty_per_user": str(chain_task["bountyPerUser"] / 10**18),
            "token_address": chain_task["tokenAddress"],
        }
    except Exception:
        return None


def heartbeat(wallet):
    state = load_state()
    state.setdefault("tasks", {})

    setup = wallet_setup_status(wallet)
    if not setup["ok"]:
        status = {
            "status": "setup_required",
            "setup": setup,
            "instructions": wallet_setup_instructions(setup["network"]),
            "message": "Wallet setup is incomplete. Configure the agent owner wallet before autonomous task writes.",
        }
        state["last_status"] = status
        save_state(state)
        return status

    active_id = state.get("active_task_id")
    selected_task = load_active_task(active_id) if active_id else None
    if active_id and selected_task is None:
        state.pop("active_task_id", None)
        state["followup_required"] = False
    evaluations = []
    if selected_task is None:
        selected_task, evaluations = choose_task(open_tasks())

    if not selected_task:
        status = {"status": "idle", "evaluations": evaluations, "message": "No suitable open task found."}
        state["last_status"] = status
        save_state(state)
        return status

    task_id = int(selected_task["task_id"])
    chain_task = niuma_chain.task(task_id)
    evaluation = evaluate_task(selected_task)
    peer = chain_task["creator"]
    task_state = state["tasks"].setdefault(str(task_id), {"phase": "selected"})

    status = {
        "taskId": task_id,
        "title": chain_task["title"],
        "creator": peer,
        "wallet": wallet,
        "evaluation": evaluation,
        "phase": task_state.get("phase"),
        "autonomous": is_autonomous(),
    }
    if state.get("onchainos", {}).get("wsSessionId") and os.environ.get("NIUMA_ONCHAINOS_WS_POLL", "1") != "0":
        status["onchainosEvents"] = poll_onchainos_watch()

    phase = task_state.get("phase")
    proof = os.environ.get("NIUMA_AGENT_PROOF_HASH") or task_state.get("proof")
    metadata = os.environ.get("NIUMA_AGENT_PROOF_METADATA") or task_state.get("metadata") or ""

    if int(chain_task.get("status", 0)) == 4:
        task_state["phase"] = "completed"
        task_state["completedAt"] = chain_task.get("completedAt")
        task_state["lockedStake"] = 0
        content = progress_text(task_id, chain_task["title"], "completed", "雇主已验收/结算；等待后续新任务。", task_state.get("proof", ""))
        status["status"] = "completed"
        status["completedAt"] = chain_task.get("completedAt")
        status["message"] = send_progress(state, wallet, peer, task_id, content)
        state.pop("active_task_id", None)
        state["followup_required"] = False
        state["last_status"] = status
        save_state(state)
        return status

    if phase == "submitted":
        content = progress_text(task_id, chain_task["title"], "submitted", "等待雇主验收或链上索引确认", task_state.get("proof", ""))
        status["status"] = "submitted"
        status["followupRequired"] = True
        status["nextHeartbeatAction"] = "Continue checking employer review, payment, rejection, or task completion."
        status["message"] = send_progress(state, wallet, peer, task_id, content)
        state["active_task_id"] = task_id
        state["followup_required"] = True
        state["last_status"] = status
        save_state(state)
        return status

    if phase in {"accepted", "working", "submit-preflight"}:
        status["followupRequired"] = True
        state["followup_required"] = True
        if proof:
            delivery = prepare_delivery(state, wallet, peer, task_id, chain_task["title"])
            status["delivery"] = delivery
            if not delivery.get("ready"):
                task_state["phase"] = "delivery-blocked"
                status["status"] = "delivery-blocked"
                content = progress_text(task_id, chain_task["title"], "delivery-blocked", f"交付物尚未成功送达雇主：{delivery.get('reason')}")
                status["message"] = send_progress(state, wallet, peer, task_id, content)
                state["active_task_id"] = task_id
                state["last_status"] = status
                save_state(state)
                return status
            proof = delivery.get("proof") or proof
            metadata = delivery.get("metadata") or metadata
            submission = submit_task(wallet, task_id, proof, metadata)
            status["submission"] = submission
            task_state["proof"] = proof
            task_state["metadata"] = metadata
            task_state["delivery"] = delivery.get("manifest")
            task_state["phase"] = "submitted" if submission.get("wrote") else "submit-preflight"
            content = progress_text(task_id, chain_task["title"], task_state["phase"], submission.get("nextAction", "等待链上确认"), proof)
        else:
            task_state["phase"] = "working"
            status["status"] = "working"
            content = progress_text(task_id, chain_task["title"], "working", "任务已接单；继续执行工作，产出 proof 后再提交。")
        status["message"] = send_progress(state, wallet, peer, task_id, content)
        state["active_task_id"] = task_id
        state["last_status"] = status
        save_state(state)
        return status

    if task_state.get("waiting_for_employer") and not requirements_confirmed(task_state):
        content = clarification_message(task_id, chain_task["title"], evaluation["clarity"])
        status["status"] = "waiting_for_employer"
        status["message"] = send_progress(state, wallet, peer, task_id, content)
        status["nextAction"] = "Wait for employer clarification before accepting, staking, executing, or submitting."
        state["active_task_id"] = task_id
        state["last_status"] = status
        save_state(state)
        return status

    if evaluation["action"] == "skip":
        content = progress_text(task_id, chain_task["title"], "blocked", "该任务不适合当前 agent 独立完成，继续寻找更匹配任务")
        status["message"] = send_progress(state, wallet, peer, task_id, content)
        task_state["phase"] = "skipped"
        state.pop("active_task_id", None)
        state["followup_required"] = False
        state["last_status"] = status
        save_state(state)
        return status

    if evaluation["action"] in {"clarify", "message-first"} and not requirements_confirmed(task_state):
        content = clarification_message(task_id, chain_task["title"], evaluation["clarity"])
        status["message"] = send_progress(state, wallet, peer, task_id, content)
        status["status"] = "clarifying"
        status["nextAction"] = "Wait for employer clarification before accepting, staking, executing, or submitting."
        task_state["phase"] = "clarifying"
        task_state["waiting_for_employer"] = True
        task_state["clarification_questions"] = evaluation["clarity"].get("questions", [])
        task_state["clarity_score"] = evaluation["clarity"].get("score")
        state["active_task_id"] = task_id
        state["last_status"] = status
        save_state(state)
        return status

    if evaluation["action"] == "collaborate":
        plan = collaboration_plan(selected_task, evaluation)
        task_state["subtasks"] = plan
        content = progress_text(task_id, chain_task["title"], "collaboration-planning", f"已生成 {len(plan)} 个协作子任务计划，等待授权发布或邀请协作者")
        status["subtasks"] = plan
        status["message"] = send_progress(state, wallet, peer, task_id, content)
        task_state["phase"] = "collaboration-planning"
        state["active_task_id"] = task_id
        state["last_status"] = status
        save_state(state)
        return status

    accept = accept_task(state, wallet, chain_task)
    status["accept"] = accept
    task_state["phase"] = "accepted" if accept.get("wrote") else "preflight"
    task_state["waiting_for_employer"] = False
    state["active_task_id"] = task_id

    if accept.get("wrote") and proof:
        delivery = prepare_delivery(state, wallet, peer, task_id, chain_task["title"])
        status["delivery"] = delivery
        if not delivery.get("ready"):
            task_state["phase"] = "delivery-blocked"
            status["status"] = "delivery-blocked"
            content = progress_text(task_id, chain_task["title"], "delivery-blocked", f"交付物尚未成功送达雇主：{delivery.get('reason')}")
            status["message"] = send_progress(state, wallet, peer, task_id, content)
            state["last_status"] = status
            save_state(state)
            return status
        proof = delivery.get("proof") or proof
        metadata = delivery.get("metadata") or metadata
        submission = submit_task(wallet, task_id, proof, metadata)
        status["submission"] = submission
        task_state["proof"] = proof
        task_state["metadata"] = metadata
        task_state["delivery"] = delivery.get("manifest")
        task_state["phase"] = "submitted" if submission.get("wrote") else "submit-preflight"
        content = progress_text(task_id, chain_task["title"], task_state["phase"], submission.get("nextAction", "等待链上确认"), proof)
    else:
        next_action = accept.get("nextAction", "继续执行任务，产出 proof 后再提交")
        if accept.get("wrote") and not proof:
            next_action = "任务已接单；开始执行工作，产出 proof 后再提交。"
        content = progress_text(task_id, chain_task["title"], task_state["phase"], next_action, accept.get("contractCall", {}).get("stdout", "")[:160])

    status["message"] = send_progress(state, wallet, peer, task_id, content)
    if task_state.get("phase") in {"accepted", "working", "submit-preflight", "submitted", "delivery-blocked", "clarifying", "collaboration-planning"}:
        state["followup_required"] = True
        status["followupRequired"] = True
        status["nextHeartbeatAction"] = "Resume this active task on the next heartbeat."
    state["last_status"] = status
    save_state(state)
    return status


def main():
    parser = argparse.ArgumentParser(description="NIUMA autonomous heartbeat runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    hb = sub.add_parser("heartbeat")
    hb.add_argument("--wallet", default=os.environ.get("NIUMA_AGENT_WALLET"))
    setup = sub.add_parser("setup-wallet")
    setup.add_argument("--network", default=DEFAULT_NETWORK, choices=["xlayer-testnet", "xlayer-mainnet"])
    setup.add_argument("--write-template", action="store_true")
    delivery = sub.add_parser("prepare-delivery")
    delivery.add_argument("--task-id", required=True, type=int)
    delivery.add_argument("--title", default="")
    delivery.add_argument("--path", default=None)
    delivery.add_argument("--delivery-uri", default=None)
    ox_status = sub.add_parser("onchainos-status")
    ox_status.add_argument("--wallet", default=os.environ.get("NIUMA_AGENT_WALLET"))
    ox_status.add_argument("--refresh-balance", action="store_true")
    ox_preflight = sub.add_parser("onchainos-preflight")
    ox_preflight.add_argument("--wallet", default=os.environ.get("NIUMA_AGENT_WALLET"))
    ox_preflight.add_argument("--to", required=True)
    ox_preflight.add_argument("--data", required=True)
    ox_preflight.add_argument("--purpose", default="manual-preflight")
    ox_watch = sub.add_parser("start-watch")
    ox_watch.add_argument("--wallet", default=os.environ.get("NIUMA_AGENT_WALLET"))
    sub.add_parser("poll-watch")
    sign_login = sub.add_parser("sign-login")
    sign_login.add_argument("--wallet", default=os.environ.get("NIUMA_AGENT_WALLET"))
    complete = sub.add_parser("complete-task")
    complete.add_argument("--task-id", required=True, type=int)
    complete.add_argument("--wallet", default=os.environ.get("NIUMA_AGENT_WALLET"))
    complete.add_argument("--proof", default="")
    complete.add_argument("--metadata", default="")
    complete.add_argument("--bind-inviter", default="")
    complete.add_argument("--execute", action="store_true", help="Execute writes after simulation; otherwise dry-run only")
    sub.add_parser("evaluate")
    args = parser.parse_args()

    if args.cmd == "evaluate":
        print(json.dumps({"evaluations": evaluate_tasks()}, ensure_ascii=False, indent=2))
        return
    if args.cmd == "setup-wallet":
        output = {
            "instructions": wallet_setup_instructions(args.network),
            "status": wallet_setup_status(network=args.network),
        }
        if args.write_template:
            output["template"] = write_wallet_env_template(args.network)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    if args.cmd == "prepare-delivery":
        print(json.dumps(build_delivery_manifest(args.task_id, args.title or f"Task #{args.task_id}", args.path, args.delivery_uri), ensure_ascii=False, indent=2))
        return
    if args.cmd == "onchainos-status":
        print(json.dumps(onchainos_status(args.wallet, refresh_balance=args.refresh_balance), ensure_ascii=False, indent=2))
        return
    if args.cmd == "onchainos-preflight":
        wallet = args.wallet or okx_wallet_address()
        if not wallet:
            print(json.dumps({"ok": False, "reason": "wallet required"}, ensure_ascii=False, indent=2))
            return
        print(json.dumps(onchainos_preflight(wallet, args.to, args.data, purpose=args.purpose), ensure_ascii=False, indent=2))
        return
    if args.cmd == "start-watch":
        wallet = args.wallet or okx_wallet_address()
        print(json.dumps(start_onchainos_watch(wallet), ensure_ascii=False, indent=2))
        return
    if args.cmd == "poll-watch":
        print(json.dumps(poll_onchainos_watch(), ensure_ascii=False, indent=2))
        return
    if args.cmd == "sign-login":
        wallet = args.wallet or okx_wallet_address()
        token = ensure_api_token(wallet) if wallet else None
        print(json.dumps({"ok": bool(token), "wallet": wallet, "tokenAvailable": bool(os.environ.get("NIUMA_API_TOKEN"))}, ensure_ascii=False, indent=2))
        return
    if args.cmd == "complete-task":
        wallet = args.wallet
        if not wallet and signing_mode() == "private-key-test" and os.environ.get("NIUMA_AGENT_PRIVATE_KEY"):
            wallet = derive_wallet_from_private_key()
        if not wallet and signing_mode() == "okx":
            wallet = okx_wallet_address()
            if wallet:
                os.environ["NIUMA_AGENT_WALLET"] = wallet
        if not wallet:
            print(json.dumps({
                "status": "setup_required",
                "setup": wallet_setup_status(wallet),
                "instructions": wallet_setup_instructions(),
                "message": "wallet required before complete-task can run",
            }, ensure_ascii=False, indent=2))
            return
        print(json.dumps(complete_task_once(
            wallet,
            args.task_id,
            proof=args.proof,
            metadata=args.metadata,
            inviter=args.bind_inviter,
            execute=args.execute,
        ), ensure_ascii=False, indent=2))
        return
    if args.cmd == "heartbeat":
        wallet = args.wallet
        if not wallet and signing_mode() == "private-key-test":
            if os.environ.get("NIUMA_AGENT_PRIVATE_KEY"):
                wallet = derive_wallet_from_private_key()
        if not wallet and signing_mode() == "okx":
            wallet = okx_wallet_address()
            if wallet:
                os.environ["NIUMA_AGENT_WALLET"] = wallet
        if not wallet:
            print(json.dumps({
                "status": "setup_required",
                "setup": wallet_setup_status(wallet),
                "instructions": wallet_setup_instructions(),
                "message": "wallet required: pass --wallet, set NIUMA_AGENT_WALLET, configure OKX OnchainOS, or use private-key-test with a local disposable test key",
            }, ensure_ascii=False, indent=2))
            return
        print(json.dumps(heartbeat(wallet), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
