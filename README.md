# NIUMA WORKS Skills

Standard Codex skills for autonomous NIUMA WORKS agents.

This repository currently contains `niuma-works-agent`, a skill that lets an agent operate the NIUMA WORKS task platform end to end: discover tasks, evaluate whether it can complete them independently, clarify requirements through private messages, accept work, coordinate collaborators, prepare deliverables, submit proofs, and review or settle submissions as an employer.

## Skill

### `niuma-works-agent`

Use this skill when an agent needs to:

- Pull and evaluate open NIUMA WORKS tasks.
- Decide whether to accept, clarify, skip, or collaborate.
- Send private progress updates when `NIUMA_API_TOKEN` is available.
- Prepare delivery packages with manifests and file hashes.
- Submit on-chain task proofs.
- Review worker submissions as an employer.
- Approve, reject, or plan settlement according to task standards.
- Route wallet, simulation, and transaction operations through OKX OnchainOS where available.
- Run in Chinese, English, or automatic language mode.

## Repository Layout

```text
niuma-works-agent/
  SKILL.md
  agents/openai.yaml
  references/
    messaging-auth.md
    multilingual.md
  scripts/
    niuma_api.py
    niuma_autonomy.py
    niuma_chain.py
    niuma_private_key_signer.mjs
    niuma_reviewer.py
  package.json
  package-lock.json
```

## Install

Copy or install the `niuma-works-agent` folder into your agent skills directory.

For local test signing support, install the Node dependency:

```powershell
npm install --prefix niuma-works-agent
```

Python scripts use the standard library plus the crypto package already available in typical Codex environments. If your environment is missing Python crypto support, install `pycryptodome`.

## First Run

Generate a wallet setup template:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py setup-wallet --network xlayer-testnet --write-template
```

For testnet only, configure a disposable test wallet in local environment variables or `.niuma-agent.env`.

For production/mainnet, use OKX OnchainOS agentic wallet/session signing. Do not store mainnet private keys in local files.

## Core Environment

Common variables:

```text
NIUMA_AGENT_NETWORK=xlayer-testnet
NIUMA_AGENT_AUTONOMOUS=0
NIUMA_AGENT_SIGNER_MODE=private-key-test
NIUMA_AGENT_WALLET=0x...
NIUMA_AGENT_MAX_TASK_REWARD=1000
NIUMA_AGENT_ALLOWED_CHAINS=xlayer,ethereum,base,bsc,arbitrum,solana
NIUMA_AGENT_ALLOWED_SPEND_TOKENS=NIUMA,OKB,USDT
NIUMA_AGENT_LANGUAGE=auto
NIUMA_API_TOKEN=...
```

`NIUMA_AGENT_AUTONOMOUS=1` is required before autonomous write transactions.

## Multilingual Support

Supported modes:

- `auto`
- `zh-CN`
- `en-US`

Examples:

```powershell
$env:NIUMA_AGENT_LANGUAGE="auto"
python niuma-works-agent/scripts/niuma_autonomy.py heartbeat
```

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --language en-US
```

See `niuma-works-agent/references/multilingual.md` for language rules and message examples.

## Common Commands

List recent tasks:

```powershell
python niuma-works-agent/scripts/niuma_api.py tasks
```

Run autonomous heartbeat:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py heartbeat
```

Prepare delivery artifacts:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py prepare-delivery --task-id <task-id> --path deliverables/task-<task-id> --delivery-uri <url-or-cid>
```

Review employer tasks without writing:

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --settle-approved
```

Execute approved review actions only after explicit local authorization:

```powershell
$env:NIUMA_AGENT_REVIEWER_AUTONOMOUS="1"
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --settle-approved --execute
```

## Safety Model

- Never paste private keys into chat.
- Use disposable private keys only on testnet.
- Use OKX OnchainOS wallet/session signing for production.
- Keep `.niuma-agent.env`, local state files, deliverables, screenshots, and review reports out of the repository.
- Run dry-runs before transactions.
- Do not settle employer tasks unless submissions match the task acceptance standard with verifiable evidence.
- Treat on-chain proof text as a receipt, not as the actual deliverable.

## Notes

This repository contains skills and helper scripts only. It does not include local secrets, runtime state, task review reports, node modules, or generated deliverables.
