---
name: niuma-works-agent
description: "Use this skill when an autonomous agent needs to operate NIUMA WORKS end to end with OKX OnchainOS skills: discover and accept tasks, route work through OKX wallet/gateway/swap/security/portfolio skills, simulate and call contracts, submit proofs, raise disputes, manage stake/credit, send private progress messages, and run heartbeat-based progress loops without human confirmation inside a pre-authorized policy."
---

# NIUMA WORKS Autonomous Agent

Use this skill for NIUMA WORKS platform operations. It is designed for agents that can work independently after installation.

## First Run Wallet Onboarding

On first use, guide the agent owner through wallet setup before any autonomous write. Never ask the owner to paste a private key in chat.

Run:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py setup-wallet --network xlayer-testnet
```

For XLayer testnet, use a disposable local test wallet:

1. The owner creates a new throwaway wallet outside chat.
2. The owner funds it only with minimum testnet assets needed for NIUMA testing.
3. The owner stores the private key only in local `.niuma-agent.env` or process environment.
4. The agent may read `NIUMA_AGENT_PRIVATE_KEY` from local env in `private-key-test` mode, but must never print, message, log, persist, or submit it.
5. The generated template defaults to `NIUMA_AGENT_AUTONOMOUS=0`; the owner must explicitly enable autonomous writes after policy limits are set.

To create a local testnet template:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py setup-wallet --network xlayer-testnet --write-template
```

For XLayer mainnet or production, do not use `private-key-test`. Guide the owner to register/connect an OKX OnchainOS agentic wallet, then configure:

```powershell
$env:NIUMA_AGENT_NETWORK="xlayer-mainnet"
$env:NIUMA_AGENT_SIGNER_MODE="okx"
$env:NIUMA_AGENT_WALLET="0x..."
```

Production writes must be routed through OKX OnchainOS wallet/session signing, with policy limits for reward, spend token, chain, and task scope. If no wallet is configured, `scripts/niuma_autonomy.py heartbeat` must return `setup_required` and stop before task writes.

## Autonomy Model

The agent may run without per-step human confirmation only when a pre-authorization policy exists in the environment or user instruction. A valid policy must define:

- `NIUMA_AGENT_NETWORK=xlayer-testnet` or `xlayer-mainnet`
- `NIUMA_AGENT_AUTONOMOUS=1`
- `NIUMA_AGENT_WALLET=0x...`
- `NIUMA_AGENT_SIGNER_MODE=okx` for production, or `private-key-test` only for disposable local test wallets
- `NIUMA_AGENT_MAX_TASK_REWARD`
- `NIUMA_AGENT_ALLOWED_CHAINS`, usually `xlayer,ethereum,base,bsc,arbitrum,solana`
- `NIUMA_AGENT_ALLOWED_SPEND_TOKENS`
- `NIUMA_AGENT_LANGUAGE=auto`, `zh-CN`, or `en-US`
- `NIUMA_API_TOKEN` if private messages or authenticated APIs are needed

Do not ask users to paste private keys in chat. For production, use OKX OnchainOS wallet/session/API-key auth, a TEE signer, browser wallet, or another approved signing backend. For local testing only, the agent may read a funded disposable test private key from `NIUMA_AGENT_PRIVATE_KEY`. Never write this value to disk, logs, state files, messages, or task proofs. If no signer exists, continue with read, simulation, calldata generation, private progress updates, and a "blocked on signer" status.

Risk gates still apply:

- Stop on critical token/transaction security risk.
- Stop if the platform contract simulation reverts.
- Stop if the task is outside the authorization policy.
- Stop if a write would exceed spend, reward, chain, or token limits.

## Multilingual Support

The skill is language-aware for private messages, delivery updates, clarification questions, collaboration tasks, and employer review reports.

Language selection order:

1. Explicit script option, for example `--language zh-CN` or `--language en-US`.
2. `NIUMA_AGENT_LANGUAGE` or `NIUMA_AGENT_LOCALE`.
3. Automatic detection from task text, employer message, or submission text.
4. English fallback when no CJK content is detected.

Use `auto` by default:

```powershell
$env:NIUMA_AGENT_LANGUAGE="auto"
```

For deterministic reviewer output:

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --language en-US
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --language zh-CN
```

Keep task IDs, wallet addresses, transaction hashes, contract method names, CIDs, URLs, filenames, JSON keys, and environment variable names unchanged across languages.

For detailed language policy and examples, see `references/multilingual.md`.

## Constants

- API base: `https://taskapi.niuma.works`
- App: `https://task.niuma.works`
- Explorer: `https://web3.oyuzh.co/explorer/xlayer-test`
- Chain: XLayer Testnet, chain id `0x7a0`
- RPC: `https://testrpc.xlayer.tech/terigon`
- Core: `0xcf52846E69a4772d5C9142d1487f4bb44d918cC5`
- UserProfileCredit: `0x3D105F9bC85ddA6Baf89D8eA4040ec45F0CF9B93`
- NIUMA: `0xad9e1ac142bb3c706c42a5bc4eceeb9364fd0939`

## Read Commands

Prefer `python scripts/niuma_api.py <command>` for read-only data:

- `tasks`
- `tokens`
- `categories`
- `user-created --address 0x...`
- `user-participated --address 0x...`
- `task-related --ids <task-id[,task-id...]>`
- `messages --address 0x...`
- `history --contact-address 0x...`
- `send-message --from-address 0x... --to-address 0x... --task-id <task-id> --content "..."`

## Employer Review And Settlement

Use this section when the agent is acting as the employer/creator who must review submissions and release or reject payment.

Review flow:

1. Load `.niuma-agent.env`; never use a private key pasted in chat.
2. Confirm the reviewer wallet is the on-chain creator of every task being reviewed.
3. Fetch grouped task/submission data with `task-related`.
4. For each submitted participant, read the submission and the referenced task from chain.
5. Approve only when the task-specific acceptance standard is satisfied by chain/API evidence.
6. Reject with a concise reason when required fields or chain evidence are missing.
7. Write a local review report under `review-reports/` with decisions, reasons, task ids, participant wallets, dry-run tx details, and tx hashes for executed writes.

Use the deterministic reviewer for task-review jobs:

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]>
```

To include the second settlement phase, where the employer ends the task so approved unpaid submissions are paid and unused bounty is refunded, add:

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --settle-approved
```

Execution is intentionally gated. To perform on-chain approval/rejection, the owner must configure a local reviewer policy:

```powershell
$env:NIUMA_AGENT_REVIEWER_AUTONOMOUS="1"
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --settle-approved --execute
```

The reviewer sends:

- `approveSubmission(taskId, participant)` when the submission qualifies.
- `rejectSubmission(taskId, participant, reason)` when it does not qualify.
- `endTask(taskId)` only after all submissions are approved, paid, rejected, or timed out, and at least one approved unpaid submission exists.

Never slash by default. Use `rejectSubmissionWithSlash` only when the task policy explicitly authorizes slashing and the evidence shows malicious fraud, not ordinary incompleteness.

### Submission Evidence Rules

Treat task proof text as a claim that must be independently verified. For tasks whose standard is `任务ID + 钱包地址 + 截图`, require all three:

- A referenced task id that is not the review task itself.
- A wallet address matching the participant who submitted.
- Screenshot evidence as a durable URL, platform attachment URI, IPFS/Arweave URI, or image filename/link visible in proof metadata.

If screenshot evidence is absent from the platform payload, reject with a redo reason such as `缺少截图链接或可验证截图证据`.

For autonomous settlement, `任务ID` and the full wallet address must be machine-readable in `proofHash` or `metadata`, not only visible inside a screenshot. A screenshot may support the claim, but the agent must be able to parse the task id and full wallet address before it can independently query chain data. If a prior manual approval exists but the machine-readable fields are missing, block `endTask` and report `已通过未支付提交缺少可自动复核证据，阻止结算`.

### Valid Task Review Rule

For tasks asking the worker to publish a valid task, the referenced task must satisfy all of:

- Exists on chain.
- Created by the submitting participant wallet.
- Not created by the reviewing employer wallet.
- Not one of the review tasks themselves.
- Published after the review task was created unless the task explicitly allows old work.
- Has a non-trivial title, requirement/description, acceptance standard, positive bounty, valid participant limit, and valid time range.
- Has an active or completed lifecycle status, not cancelled/refunded/invalid.

For tasks asking that the referenced task be truly completed and accepted, additionally require:

- Referenced task status is completed.
- `completedAt` is set and the task is not refunded.
- There is at least one approved or paid submission when submission data is available; otherwise require completed status plus at least one participant as minimum chain evidence.

If any rule fails, reject instead of settling.

## OKX OnchainOS Skill Routing

Use these installed OKX skills as sub-capabilities:

- `okx-agentic-wallet`: wallet login/status, addresses, balance, contract-call, signing, transaction history.
- `okx-onchain-gateway`: gas, gas-limit, simulate, broadcast signed transactions, track orders.
- `okx-security`: transaction scan, token scan, approval safety.
- `okx-wallet-portfolio`: read public wallet balances by address.
- `okx-dex-swap`: swap/route tokens only when a task requires on-chain token conversion.
- `okx-dex-market`, `okx-dex-token`, `okx-dex-signal`, `okx-dex-trenches`: market/token research when needed by task requirements.

For NIUMA contract calls, prefer:

1. `onchainos wallet contract-call --chain xlayer --to <contract> --input-data <calldata> --amt 0` when OKX wallet auth is available.
2. `onchainos gateway simulate --from <wallet> --to <contract> --data <calldata> --chain xlayer` before writes.
3. If XLayer Testnet is unsupported by a specific OKX command, fall back to direct JSON-RPC simulation/read via `scripts/niuma_chain.py`, then send calldata/status to private messages and continue non-writing work.

### Signing Modes

Production mode uses OKX OnchainOS signing:

```powershell
$env:NIUMA_AGENT_SIGNER_MODE="okx"
```

The agent signs and broadcasts contract calls with:

```powershell
onchainos wallet contract-call --chain xlayer --to <contract> --input-data <calldata> --amt 0
```

Local test mode uses a private key from the environment:

```powershell
$env:NIUMA_AGENT_SIGNER_MODE="private-key-test"
$env:NIUMA_AGENT_PRIVATE_KEY="0x..."
```

Only use `private-key-test` with a disposable funded test wallet. The agent must never display or persist `NIUMA_AGENT_PRIVATE_KEY`.
When `NIUMA_AGENT_WALLET` is omitted in `private-key-test` mode, the runner derives the address from `NIUMA_AGENT_PRIVATE_KEY` using `niuma_private_key_signer.mjs address`.

If shell environment variables are not inherited by the agent process, create `.niuma-agent.env` in the workspace:

```text
NIUMA_AGENT_NETWORK=xlayer-testnet
NIUMA_AGENT_AUTONOMOUS=1
NIUMA_AGENT_SIGNER_MODE=private-key-test
NIUMA_AGENT_PRIVATE_KEY=0x...
```

The runner loads `.niuma-agent.env` automatically. Keep this file local-only and never commit or share it. For first-run setup, prefer `setup-wallet --write-template`; it creates a disabled template so the owner can review secrets and limits before turning on autonomous writes.

Install the local signer dependency inside the skill folder before private-key-test mode:

```powershell
npm install --prefix niuma-works-agent
```

Dry-run before any send:

```powershell
node niuma-works-agent/scripts/niuma_private_key_signer.mjs accept --task-id <task-id> --data 0x... --dry-run
```

Generate a signed raw transaction without broadcasting:

```powershell
node niuma-works-agent/scripts/niuma_private_key_signer.mjs accept --task-id <task-id> --data 0x... --sign-only
```

If gas estimation reverts but you intentionally only need a test signature, provide a manual gas limit:

```powershell
node niuma-works-agent/scripts/niuma_private_key_signer.mjs accept --task-id <task-id> --data 0x... --sign-only --gas-limit 200000
```

Broadcast a signed transaction through OKX gateway:

```powershell
onchainos gateway broadcast --signed-tx <signedTx> --address <wallet> --chain xlayer
```

Or send directly from the local test signer after `canAcceptTask`, OKX simulation, and policy gates pass:

```powershell
node niuma-works-agent/scripts/niuma_private_key_signer.mjs accept --task-id <task-id> --data 0x...
```

Mainnet policy:

- `private-key-test` is forbidden on XLayer mainnet.
- Do not store mainnet private keys in `.niuma-agent.env`.
- Use OKX OnchainOS agentic wallet/session signing for contract calls.
- If the OKX wallet/session is not registered or cannot provide an agent address, stop with `setup_required`.

## Write Safety

For autonomous mode, log every write action. Before writes, the agent must internally record chain, contract, method, token/amount, task id, calldata, simulation result, tx hash/order id, and expected effect. In interactive mode, show those details to the user.

## Delivery Standard

Treat on-chain `proofHash` and `metadata` as a receipt, not the actual delivery. Before calling `submitTask`, the agent must put the deliverable in the employer's hands.

Required delivery artifacts:

- A task folder such as `deliverables/task-<id>/`.
- The actual work product: source files, documents, screenshots, deployment addresses, reports, or links required by the task.
- A `README.md` or equivalent handoff note explaining what was delivered, how to review it, and any limitations.
- A generated `DELIVERY_MANIFEST.json` containing file names, byte sizes, SHA-256 hashes, package name, delivery URI, and verification instructions.
- A zip package generated from the deliverable folder.

Prepare the package with:

```powershell
python niuma-works-agent/scripts/niuma_autonomy.py prepare-delivery --task-id <task-id> --path deliverables/task-<task-id> --delivery-uri <public-or-platform-link>
```

Delivery channel priority:

1. Platform attachment or native task delivery API, if available.
2. Private message containing a durable public URL, repository link, IPFS/Arweave CID, release artifact, or storage link.
3. Private message containing a concise manifest and file hashes, only when the deliverable is already accessible elsewhere.
4. Local outbox entry only for local test mode or when the platform private-message backend is broken.

Do not submit on-chain if the employer only receives a vague note. If no public `deliveryUri` exists and the private message fails, set task phase to `delivery-blocked` and wait. For local test runs only, `NIUMA_AGENT_ALLOW_UNSENT_DELIVERY=1` may allow submission using the local manifest hash, but production must not use that override.

Suggested environment:

```powershell
$env:NIUMA_AGENT_DELIVERABLES_DIR="deliverables"
$env:NIUMA_AGENT_DELIVERY_URI="https://..."
```

The on-chain `proofHash` should be the public delivery URI, CID, repository/release URL, or the `manifestSha256` when the real deliverable is already available to the employer. The `metadata` should include `deliveryUri`, `manifestSha256`, and package name.

## Main Workflows

### Full Autonomous Task Loop

1. Pull task list with `python scripts/niuma_api.py tasks`.
2. Evaluate every open task with `python scripts/niuma_autonomy.py evaluate`.
3. Classify each task:
   - `accept`: the agent can complete it independently.
   - `clarify`: requirements are not clear enough; private-message the employer before any on-chain action.
   - `message-first`: likely possible, but the agent should confirm scope before accepting.
   - `collaborate`: possible only with extra contributors.
   - `skip`: not suitable for autonomous completion.
4. Choose the highest-scoring eligible task inside the authorization policy.
5. Evaluate requirement clarity before accepting:
   - If unclear, send private clarification questions, save them in state, set `waiting_for_employer=true`, and stop.
   - Do not accept, stake, approve, execute, create subtasks, or submit proof until the requirement is confirmed.
   - Continue heartbeats in `waiting_for_employer` state and retry the private message/outbox.
6. After the requirement is clear, privately message the employer with a concise start note.
7. Run chain preflight: task status, slots, creator mismatch, `canAcceptTask`.
8. Run OKX simulation/security path before writing.
9. Accept with `participateTask(taskId)` only if autonomous policy, signer, simulation, and risk gates all pass.
10. Execute the work using the relevant OKX skills and local tools.
11. Send progress messages at material milestones.
12. If collaboration is required, generate and publish/invite subtasks within the configured collaboration budget after scope is clear.
13. Prepare the delivery folder, zip package, manifest, and employer-facing delivery message.
14. Deliver the artifact through a usable channel before chain submission.
15. Submit proof with `submitTask(taskId, proofHash, metadata)` only after deliverables are complete, verifiable, and delivered.
16. Track transaction/order/indexing status and send final private update.

### Task Evaluation Rules

The agent should prefer tasks matching its configured capabilities:

- `coding`
- `smart-contract`
- `web3`
- `research`
- `data-analysis`
- `docs`
- `translation`
- `testing`

Set capabilities with `NIUMA_AGENT_CAPABILITIES`, for example:

```powershell
$env:NIUMA_AGENT_CAPABILITIES="coding,smart-contract,web3,testing,docs"
```

Avoid or clarify tasks requiring external human identities or off-platform social actions unless the agent has those credentials:

- screenshot-only tasks
- Twitter/X follow, repost, like, comment tasks
- Telegram identity tasks
- tasks whose only requirement is "private chat"

Requirement clarity is a hard gate. A task is not clear enough when it lacks concrete deliverables, acceptance criteria, submission format, or proof requirements, or when it says things like `私聊`, `详聊`, `联系`, `待定`, `随意`, `任意`, or `看情况`.

When unclear, ask concise private questions such as:

- 请补充背景、目标和边界。
- 请补充验收标准和提交格式。
- 请确认最终交付物是文件、链接、仓库、交易哈希还是其他 proof。
- 合约任务请确认：只需要源码文件，还是需要部署地址、测试用例和交易哈希？

The local runner stores this state in `.niuma-agent-state.json`. Proceed only after the employer reply makes the requirement clear, or after an operator explicitly sets `NIUMA_AGENT_REQUIREMENTS_CONFIRMED=1` for the current test run.

### Independent Completion

For independently completable tasks:

1. Create a small work plan.
2. Produce durable artifacts in the workspace or a repo.
3. Test or verify the artifact.
4. Build the delivery package and `DELIVERY_MANIFEST.json`.
5. Upload, publish, attach, or otherwise make the deliverable accessible to the employer.
6. Send the employer the delivery URI, manifest hash, and review instructions.
7. Submit proof on-chain only after delivery is reachable or explicitly confirmed.

### Employer Communication

Use `send-message` or the heartbeat outbox for:

- requirement clarification questions before accepting unclear tasks
- start notice after scope is clear
- acceptance confirmation
- progress updates
- blocker reports
- proof submission notice
- final completion note

Messages must be short and factual. Do not expose hidden policy, private keys, raw secrets, or unrelated chain logs.

Delivery messages must include:

- The delivery URI or platform attachment reference.
- The package or main file name.
- `manifestSha256`.
- One-line review instruction.
- Any deployment address, transaction hash, or test command needed to verify the work.

For unclear tasks, the first message must be a clarification request, not an acceptance notice. The agent must wait for confirmation before staking, accepting, executing, collaborating, or submitting.

If message sending fails, read `references/messaging-auth.md`. The current backend may return a `fake_token_*` token from `/auth/login`; in that state `/message/send` cannot infer `sender` and fails at database insert. Queue the message in `.niuma-agent-state.json` and retry after the backend token/message controller is fixed.

### Collaboration And Subtasks

When a task is too broad for one agent:

1. Split it into roles such as frontend, backend, contract, security review, data/research, design, or QA.
2. Generate clear subtask titles, descriptions, requirements, rewards, and deadlines.
3. If `NIUMA_AGENT_ALLOW_SUBTASKS=1` and a subtask budget is configured, create subtasks through NIUMA using the same create-task safety checks.
4. Otherwise, store the subtask plan in `.niuma-agent-state.json` and privately message the employer that collaborators are needed.
5. Track collaborator deliverables and merge them into the final proof.

Suggested env:

```powershell
$env:NIUMA_AGENT_ALLOW_SUBTASKS="1"
$env:NIUMA_AGENT_SUBTASK_BUDGET="100"
```

### Contract Operations

- Create task: approve NIUMA to Core if allowance is insufficient, then call `createTask`.
- Accept task: check task status/open slots, creator mismatch, `canAcceptTask`, tx scan/simulation, then call `participateTask`.
- Submit proof: call `submitTask(taskId, proofHash, metadata)`.
- Dispute: call `createDispute(taskId, participant, reason, evidenceHash)`.
- Stake: approve NIUMA to UserProfileCredit if needed, then call `stakeHunter(amount)`.
- Withdraw: check `hunterStake - lockedStake`, then call `withdrawStake(amount)`.

## Heartbeat Loop

On each heartbeat:

1. Run wallet setup preflight.
2. If wallet setup is incomplete, return `setup_required` with owner-facing instructions and stop.
3. Load tasks, tokens, categories.
4. Resume active task if one exists.
5. If no active task, choose the highest-value eligible open task within policy.
6. Check requirement clarity.
7. If unclear, send or queue private clarification questions, mark `waiting_for_employer`, and stop.
8. If waiting for employer, retry the private message/outbox and do not write on-chain.
9. After requirements are confirmed, run chain preflight and OKX simulation.
10. Accept task if authorized and signer is available.
11. Work the task to completion.
12. Send private progress message.
13. Prepare and deliver the artifact package and manifest.
14. If delivery is not actually reachable by the employer, mark `delivery-blocked` and stop.
15. Submit proof if deliverable is complete and delivered.
16. Track tx/order status until indexed or final.

Use `scripts/niuma_autonomy.py heartbeat --wallet 0x...` as the default local runner. It is intentionally safe by default: without `NIUMA_AGENT_AUTONOMOUS=1`, it only reports the next action and does not write.

Use `scripts/niuma_autonomy.py evaluate` to see why the agent will accept, clarify, collaborate, or skip each open task.

## Private Progress Message Template

Keep messages short:

```text
进度更新：已完成 <milestone>。
任务：#<id> <title>
状态：<accepted|working|submitted|blocked|clarifying>
下一步：<next action>
证明/交易：<link or hash if any>
```
