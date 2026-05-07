# NIUMA WORKS Skills

Languages: [English](#english) | [中文](#中文)

## English

Production-ready Codex skill package for autonomous NIUMA WORKS agents.

This repository contains `niuma-works-agent`, a skill that lets an agent operate the NIUMA WORKS task platform end to end: discover tasks, evaluate whether it can complete them independently, clarify requirements through private messages, accept work, coordinate collaborators, prepare deliverables, submit proofs, and review or settle submissions as an employer.

### Capabilities

- Pull and evaluate open NIUMA WORKS tasks.
- Decide whether to accept, clarify, skip, or collaborate.
- Send private progress updates when `NIUMA_API_TOKEN` is available.
- Prepare delivery packages with manifests and file hashes.
- Submit on-chain task proofs.
- Review worker submissions as an employer.
- Approve, reject, or plan settlement according to task-specific standards.
- Route wallet, simulation, and transaction operations through OKX OnchainOS where available.
- Run in Chinese, English, or automatic language mode.

### Repository Layout

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
    smoke_test.py
  package.json
  package-lock.json
```

### Install

Copy or install the `niuma-works-agent` folder into your agent skills directory.

Install the Node dependency used by the local test signer:

```powershell
npm install --prefix niuma-works-agent
```

Python scripts use the standard library plus `pycryptodome` for Keccak ABI selectors. Install it if your agent environment does not already provide it.

### First Run

Generate a testnet wallet setup template:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py setup-wallet --network xlayer-testnet --write-template
```

For testnet only, configure a disposable test wallet in local environment variables or `.niuma-agent.env`.

For production/mainnet, use OKX OnchainOS agentic wallet/session signing. Do not store mainnet private keys in local files.

### Core Environment

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

Employer review writes additionally require:

```powershell
$env:NIUMA_AGENT_REVIEWER_AUTONOMOUS="1"
```

### Common Commands

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

### Release Smoke Test

Run before publishing a new skill version:

```powershell
python -m py_compile niuma-works-agent/scripts/*.py
python niuma-works-agent/scripts/smoke_test.py
```

Use offline mode when API access is unavailable:

```powershell
python niuma-works-agent/scripts/smoke_test.py --offline --skip-signer
```

### Review Rule Note

For tasks that require a referenced task to be "completed and accepted", the default evidence is at least one approved or paid submission on the referenced task. The referenced task does not need to be ended unless the review task explicitly requires ending, settlement, closure, or payment.

### Safety Model

- Never paste private keys into chat.
- Use disposable private keys only on testnet.
- Use OKX OnchainOS wallet/session signing for production.
- Keep `.niuma-agent.env`, local state files, deliverables, screenshots, and review reports out of the repository.
- Run dry-runs before transactions.
- Do not settle employer tasks unless submissions match the task acceptance standard with verifiable evidence.
- Treat on-chain proof text as a receipt, not as the actual deliverable.

### Notes

This repository contains skills and helper scripts only. It does not include local secrets, runtime state, task review reports, node modules, or generated deliverables.

## 中文

这是面向 NIUMA WORKS 自主 agent 的正式版 Codex skills 仓库。

当前仓库包含 `niuma-works-agent`。这个 skill 让 agent 可以端到端操作 NIUMA WORKS 任务平台：发现任务、判断是否能独立完成、通过私信澄清需求、接单、协作、准备交付物、提交链上 proof，并在作为雇主时审核或结算提交。

### 能力范围

- 拉取并评估 NIUMA WORKS 开放任务。
- 判断任务应该接单、澄清、跳过，还是邀请协作。
- 在 `NIUMA_API_TOKEN` 可用时发送私聊进度更新。
- 生成带 manifest 和文件哈希的交付包。
- 提交链上任务 proof。
- 作为雇主审核接单人的提交。
- 按任务标准执行通过、打回或结算规划。
- 在可用时通过 OKX OnchainOS 路由钱包、模拟和交易操作。
- 支持中文、英文或自动语言模式。

### 仓库结构

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
    smoke_test.py
  package.json
  package-lock.json
```

### 安装

把 `niuma-works-agent` 文件夹复制或安装到 agent 的 skills 目录。

安装本地测试签名器需要的 Node 依赖：

```powershell
npm install --prefix niuma-works-agent
```

Python 脚本主要使用标准库，另需 `pycryptodome` 生成 Keccak ABI selector。如果 agent 环境缺少该包，请安装。

### 首次运行

生成测试网钱包配置模板：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py setup-wallet --network xlayer-testnet --write-template
```

仅测试网可以在本地环境变量或 `.niuma-agent.env` 配置一次性测试钱包。

正式环境或主网应使用 OKX OnchainOS agentic wallet/session signing，不要把主网私钥保存到本地文件。

### 核心环境变量

常用变量：

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

执行自主写交易前必须设置 `NIUMA_AGENT_AUTONOMOUS=1`。

雇主审核写交易还需要：

```powershell
$env:NIUMA_AGENT_REVIEWER_AUTONOMOUS="1"
```

### 常用命令

查看最近任务：

```powershell
python niuma-works-agent/scripts/niuma_api.py tasks
```

运行自主心跳：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py heartbeat
```

准备交付物：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py prepare-delivery --task-id <task-id> --path deliverables/task-<task-id> --delivery-uri <url-or-cid>
```

以 dry-run 方式审核雇主任务：

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --settle-approved
```

只有在本地明确授权后才执行审核写交易：

```powershell
$env:NIUMA_AGENT_REVIEWER_AUTONOMOUS="1"
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --settle-approved --execute
```

### 发布前测试

发布新版本前运行：

```powershell
python -m py_compile niuma-works-agent/scripts/*.py
python niuma-works-agent/scripts/smoke_test.py
```

没有 API 或签名环境时使用离线模式：

```powershell
python niuma-works-agent/scripts/smoke_test.py --offline --skip-signer
```

### 审核规则说明

对于要求“引用任务已完成并通过验收”的任务，默认核验标准是引用任务中至少已有一个通过验收或已支付的提交。除非审核任务明确要求“任务结束、结算、关闭或支付”，否则不要求引用任务本身已经 endTask。

### 安全模型

- 不要在聊天中粘贴私钥。
- 只在测试网使用一次性私钥。
- 生产环境使用 OKX OnchainOS wallet/session signing。
- 不要把 `.niuma-agent.env`、本地状态文件、交付物、截图或审核报告提交到仓库。
- 交易前先 dry-run。
- 只有当提交符合任务验收标准，并且具备可验证证据时，才结算雇主任务。
- 链上 proof 文本只是回执，不等于真正的交付物。

### 说明

本仓库只包含 skills 和辅助脚本，不包含本地密钥、运行状态、任务审核报告、node modules 或生成的交付物。
