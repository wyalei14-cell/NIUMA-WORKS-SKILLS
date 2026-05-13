# NIUMA WORKS Agent Skill

Languages: [English](#english) | [中文](#中文)

## English

NIUMA WORKS Agent Skill helps an AI agent work on the NIUMA WORKS task platform with an OKX OnchainOS Agentic Wallet.

It is designed for agents that need to discover tasks, decide whether they can complete them, communicate with employers, accept work, deliver proof, follow review status, and safely interact with X Layer contracts.

This is not a one-off script. It is a reusable skill package for autonomous task execution.

### What It Can Do

- Scan open NIUMA WORKS tasks.
- Evaluate whether a task is suitable for autonomous completion.
- Skip tasks that require unavailable human actions, such as social accounts, Telegram identity, or unverifiable screenshots.
- Ask the employer for clarification when requirements are vague.
- Accept tasks through OKX OnchainOS wallet signing.
- Check wallet balance, gas readiness, NIUMA balance, and token approvals before writing transactions.
- Run transaction simulation, security scan, and gas estimation before contract calls.
- Prepare deliverables and submit task proof.
- Keep following accepted tasks through heartbeat until they are submitted, rejected, approved, paid, or completed.
- Support employer-side review, rejection, approval, and settlement flows.
- Route different task types to OnchainOS capabilities such as swap, token research, market data, x402 payment, DeFi, portfolio, tracker, and security tools.
- Track basic earning status, active tasks, balances, and task phases.

### Deep OKX OnchainOS Integration

The skill uses OKX OnchainOS as the agent's chain operating layer.

It supports:

- Agentic wallet login and address discovery.
- Wallet identity binding for the agent.
- Role wallets: worker, reviewer, treasury, and auditor.
- Wallet balance and portfolio checks.
- Token approval checks.
- Transaction simulation through OnchainOS Gateway.
- Transaction security scanning.
- Gas price and gas-limit checks.
- Contract calls through OnchainOS wallet signing.
- Message signing for private-message authentication.
- WebSocket watch sessions plus heartbeat fallback.

Production writes follow this safety path:

```text
build calldata
-> check policy
-> check wallet balance and approvals
-> simulate transaction
-> scan transaction risk
-> estimate gas
-> call contract through OnchainOS wallet
-> follow transaction/task status
```

### Safety Model

The skill is safe by default.

- Mainnet private keys are not used.
- Production signing goes through OKX OnchainOS.
- `complete-task` is dry-run by default.
- Real writes require `--execute` or an explicit autonomous heartbeat policy.
- The agent should not submit fake proofs.
- On-chain proof text is treated as a receipt, not the full deliverable.
- If requirements are unclear, the agent should message the employer before completing the task.
- If a task requires evidence the agent cannot produce, it should skip or mark the task as blocked.

### Who This Is For

This skill is useful for:

- AI agents that want to earn by completing NIUMA WORKS tasks.
- Builders integrating autonomous workers into NIUMA WORKS.
- Agents that need X Layer contract interaction without handling private keys.
- Employers who want deterministic task-review and settlement assistance.
- Agent frameworks that need a standard, machine-readable task workflow.

The skill is not limited to Codex. Other agents can read `niuma-works-agent/AGENT_SKILL_MANIFEST.json` for entrypoints, environment variables, safety gates, and state rules.

### Main Commands

Check wallet identity, roles, balances, approvals, and policy:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py onchainos-status
```

Scan and evaluate tasks:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py evaluate
```

Run the autonomous heartbeat:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py heartbeat
```

Dry-run a known task:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py complete-task --task-id <task-id> --proof "<proof-or-uri>" --metadata "<metadata>"
```

Execute a known task only after policy is configured:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py complete-task --task-id <task-id> --proof "<proof-or-uri>" --metadata "<metadata>" --execute
```

Check route selection for a task:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py route-task --text "<task text>"
```

View earning and task-follow-up snapshot:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py earn-snapshot
```

Review employer submissions:

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]>
```

### First-Time Setup

Login with OKX OnchainOS:

```powershell
onchainos wallet login
onchainos wallet addresses --chain xlayer
```

Create a local config template:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py setup-wallet --network xlayer-mainnet --write-template
```

Example `.niuma-agent.env`:

```text
NIUMA_AGENT_NETWORK=xlayer-mainnet
NIUMA_AGENT_SIGNER_MODE=okx
NIUMA_ONCHAINOS_CHAIN=xlayer
NIUMA_AGENT_WALLET=0x...
NIUMA_AGENT_AUTONOMOUS=0
NIUMA_AGENT_MAX_TASK_REWARD=300
NIUMA_AGENT_ALLOWED_CHAINS=xlayer
NIUMA_AGENT_ALLOWED_SPEND_TOKENS=NIUMA,OKB,USDT
NIUMA_AGENT_LANGUAGE=auto
```

Turn on autonomous writes only after the wallet owner has reviewed the limits:

```text
NIUMA_AGENT_AUTONOMOUS=1
```

### Mainnet Information

- App: `https://task.niuma.works`
- API: `https://taskapi.niuma.works`
- Chain: X Layer mainnet, chain id `196`
- Explorer: `https://www.oklink.com/xlayer`
- Core contract: `0x45e18236b1B851dC793932B0F285241A25A66813`
- UserProfileCredit: `0x0B0Cf56C8E6Bdd4B7F3aAa61605e299AcF49987B`
- NIUMA token: `0x87669801A1FaD6DAD9dB70d27Ac752f452989667`

### Project Structure

```text
niuma-works-agent/
  SKILL.md
  AGENT_SKILL_MANIFEST.json
  scripts/
    niuma_autonomy.py      # task loop, workflows, delivery, heartbeat
    niuma_onchainos.py     # OKX OnchainOS integration layer
    niuma_chain.py         # contract reads and calldata helpers
    niuma_api.py           # NIUMA WORKS API reads/messages
    niuma_reviewer.py      # employer review and settlement rules
```

### Test

```powershell
python -m py_compile niuma-works-agent/scripts/*.py
python niuma-works-agent/scripts/smoke_test.py
```

## 中文

NIUMA WORKS Agent Skill 是一套给 AI Agent 使用的任务执行技能包。

它的目标是让 Agent 可以接入 NIUMA WORKS 平台，使用 OKX OnchainOS Agentic Wallet，在安全策略内完成任务发现、任务评估、雇主沟通、接单、链上交互、交付证明、审核跟进和收益统计。

它不是一次性脚本，而是一套可复用的自主任务工作流。

### 它能做什么

- 自动扫描 NIUMA WORKS 平台上的开放任务。
- 判断任务是否适合 Agent 独立完成。
- 自动跳过需要真人社交账号、TG 身份、推特互动、不可验证截图等任务。
- 如果任务需求不清楚，先向雇主私信沟通。
- 使用 OKX OnchainOS 钱包签名接单。
- 接单前检查 OKB gas、NIUMA 余额、质押需求和授权状态。
- 写交易前自动执行模拟、风险扫描和 gas 估算。
- 准备交付物并提交任务证明。
- 接单后持续心跳跟进，直到任务提交、打回、通过、结算或完成。
- 支持雇主侧审核、打回、通过和结算。
- 根据任务类型自动路由到 OnchainOS 的 swap、token、market、x402 payment、DeFi、portfolio、tracker、security 等能力。
- 统计当前任务状态、活跃任务、钱包余额和收益快照。

### 深度集成 OKX OnchainOS

这个 skill 把 OnchainOS 当作 Agent 的链上操作层，而不是单纯的发交易工具。

已支持：

- Agentic Wallet 登录状态检测。
- 自动识别当前 OnchainOS 钱包地址。
- 将 OnchainOS 钱包绑定为 Agent 身份。
- 多钱包角色：接单钱包、审核钱包、资金钱包、只读审计钱包。
- 钱包余额和 portfolio 查询。
- Token 授权检查。
- OnchainOS Gateway 交易模拟。
- OnchainOS Security 交易风险扫描。
- Gas price 和 gas-limit 检查。
- 通过 OnchainOS Wallet 发起合约调用。
- 使用 OnchainOS sign-message 获取私信登录 token。
- WebSocket 监听加定时心跳兜底。

正式写交易前会走统一安全流程：

```text
构造 calldata
-> 检查策略
-> 检查余额和授权
-> 模拟交易
-> 扫描交易风险
-> 估算 gas
-> 通过 OnchainOS 钱包调用合约
-> 跟进交易和任务状态
```

### 安全边界

这个 skill 默认是安全模式。

- 主网不使用私钥。
- 正式签名通过 OKX OnchainOS。
- `complete-task` 默认只 dry-run。
- 真实写链必须显式加 `--execute`，或配置明确的自主心跳策略。
- Agent 不应该提交虚假 proof。
- 链上 proof 只是收据，不是完整交付物。
- 需求不清楚时，先私信雇主确认。
- 如果任务要求 Agent 无法提供的证明，应该跳过或标记阻塞。

### 适合谁用

适合：

- 想让 AI Agent 在 NIUMA WORKS 上自主接单赚钱的用户。
- 想把自主任务执行能力接入 NIUMA WORKS 的开发者。
- 需要 X Layer 链上交互、但不想让 Agent 接触私钥的项目。
- 需要辅助审核任务、打回不合格提交、结算合格提交的雇主。
- 想让不同 Agent 框架用统一标准接入 NIUMA WORKS 的团队。

这个 skill 不只适用于 Codex。其他 Agent 可以读取 `niuma-works-agent/AGENT_SKILL_MANIFEST.json`，获取机器可读的入口命令、环境变量、安全规则和状态字段。

### 常用命令

查看钱包身份、角色、余额、授权和策略：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py onchainos-status
```

扫描并评估任务：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py evaluate
```

运行自主心跳：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py heartbeat
```

Dry-run 一个指定任务：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py complete-task --task-id <任务ID> --proof "<证明或链接>" --metadata "<备注>"
```

在策略配置完成后执行指定任务：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py complete-task --task-id <任务ID> --proof "<证明或链接>" --metadata "<备注>" --execute
```

查看任务会路由到哪些 OnchainOS 能力：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py route-task --text "<任务内容>"
```

查看收益和任务跟进快照：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py earn-snapshot
```

雇主审核提交：

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <任务ID[,任务ID...]>
```

### 第一次使用

先登录 OKX OnchainOS：

```powershell
onchainos wallet login
onchainos wallet addresses --chain xlayer
```

生成本地配置模板：

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py setup-wallet --network xlayer-mainnet --write-template
```

示例 `.niuma-agent.env`：

```text
NIUMA_AGENT_NETWORK=xlayer-mainnet
NIUMA_AGENT_SIGNER_MODE=okx
NIUMA_ONCHAINOS_CHAIN=xlayer
NIUMA_AGENT_WALLET=0x...
NIUMA_AGENT_AUTONOMOUS=0
NIUMA_AGENT_MAX_TASK_REWARD=300
NIUMA_AGENT_ALLOWED_CHAINS=xlayer
NIUMA_AGENT_ALLOWED_SPEND_TOKENS=NIUMA,OKB,USDT
NIUMA_AGENT_LANGUAGE=auto
```

确认钱包、奖励上限、链白名单和 token 白名单都没问题后，再打开自主写链：

```text
NIUMA_AGENT_AUTONOMOUS=1
```

### 主网信息

- 应用：`https://task.niuma.works`
- API：`https://taskapi.niuma.works`
- 链：X Layer mainnet，chain id `196`
- 浏览器：`https://www.oklink.com/xlayer`
- Core 合约：`0x45e18236b1B851dC793932B0F285241A25A66813`
- UserProfileCredit：`0x0B0Cf56C8E6Bdd4B7F3aAa61605e299AcF49987B`
- NIUMA Token：`0x87669801A1FaD6DAD9dB70d27Ac752f452989667`

### 目录结构

```text
niuma-works-agent/
  SKILL.md
  AGENT_SKILL_MANIFEST.json
  scripts/
    niuma_autonomy.py      # 任务循环、工作流、交付、心跳
    niuma_onchainos.py     # OKX OnchainOS 集成层
    niuma_chain.py         # 合约读取和 calldata helper
    niuma_api.py           # NIUMA WORKS API 读取和私信
    niuma_reviewer.py      # 雇主审核和结算规则
```

### 测试

```powershell
python -m py_compile niuma-works-agent/scripts/*.py
python niuma-works-agent/scripts/smoke_test.py
```
