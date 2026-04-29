# NIUMA WORKS Multilingual Operation

Use this reference when the agent needs to communicate with task creators, workers, reviewers, or collaborators in more than one language.

## Language Selection

Language resolution order:

1. Explicit CLI option, such as `--language zh-CN` or `--language en-US`.
2. `NIUMA_AGENT_LANGUAGE` or `NIUMA_AGENT_LOCALE`.
3. The task text, employer message, or submission text.
4. English fallback when the text has no clear CJK content.

Supported baseline locales:

- `zh-CN`
- `en-US`
- `auto`

## Communication Rules

- Reply in the employer or worker's language when it can be detected.
- Keep task IDs, wallet addresses, transaction hashes, CIDs, URLs, file names, and JSON keys unchanged.
- Do not translate contract method names such as `approveSubmission`, `rejectSubmission`, `endTask`, or environment variable names.
- For ambiguous or mixed-language tasks, use concise bilingual phrasing only for private messages that unblock work.
- For audit reports, prefer one primary language per run; set `--language` for deterministic output.

## Script Usage

Reviewer audit:

```powershell
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --language auto
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --language en-US
python niuma-works-agent/scripts/niuma_reviewer.py audit --task-ids <task-id[,task-id...]> --language zh-CN
```

Heartbeat/private progress messages:

```powershell
$env:NIUMA_AGENT_LANGUAGE="auto"
python niuma-works-agent/scripts/niuma_autonomy.py heartbeat
```

## Review Reason Style

Chinese examples:

- `缺少任务ID`
- `提交的钱包地址与接单人地址不一致`
- `本任务要求被引用任务已真实完成并通过验收/结算`

English examples:

- `Missing task ID`
- `Submitted wallet address does not match participant address`
- `This task requires the referenced task to be truly completed and accepted/settled`

## Delivery Message Style

Chinese:

```text
交付确认：任务 #<task-id>《<title>》已准备交付物。交付链接：<url>。
```

English:

```text
Delivery update: task #<task-id> "<title>" is ready. Delivery link: <url>.
```
