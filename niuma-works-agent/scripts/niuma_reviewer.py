#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

import niuma_api
import niuma_chain
import niuma_onchainos as ox

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".niuma-agent.env"
REPORT_DIR = ROOT / "review-reports"
ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
URL_RE = re.compile(r"(https?://\S+|ipfs://\S+|ar://\S+|\b\S+\.(?:png|jpg|jpeg|webp|gif)\b)", re.I)
DEFAULT_LANGUAGE = os.environ.get("NIUMA_AGENT_LANGUAGE", os.environ.get("NIUMA_AGENT_LOCALE", "auto")).strip()

MESSAGES = {
    "zh-CN": {
        "missing_participant": "提交记录缺少接单人地址",
        "already_approved_or_paid": "提交已通过或已支付",
        "already_rejected": "提交已被拒绝",
        "missing_task_id": "缺少任务ID",
        "missing_wallet": "缺少钱包地址",
        "wallet_mismatch": "提交的钱包地址与接单人地址不一致",
        "missing_screenshot": "缺少截图链接或可验证截图证据",
        "read_task_failed": "无法读取被引用任务链上数据",
        "task_self_reference": "提交的任务ID不能是验收任务本身",
        "task_creator_mismatch": "提交的钱包不是被引用任务的创建者",
        "task_creator_is_employer": "被引用任务不能由雇主钱包创建",
        "task_status_invalid": "被引用任务状态无效",
        "task_title_short": "被引用任务标题过短",
        "task_description_short": "被引用任务需求描述不足",
        "task_requirements_missing": "被引用任务验收标准缺失",
        "task_no_bounty": "被引用任务没有有效赏金",
        "task_bad_participant_limit": "被引用任务接单人数设置无效",
        "task_bad_time_range": "被引用任务时间范围无效",
        "task_too_old": "被引用任务早于验收任务发布，不能证明是为本任务完成",
        "task_must_be_completed": "本任务要求被引用任务已真实完成并通过验收/结算",
        "qualified": "符合验收标准",
        "missing_machine_task_id": "缺少机器可读任务ID",
        "missing_machine_wallet": "缺少机器可读完整钱包地址",
        "missing_screenshot_evidence": "缺少截图证据",
        "approved_needs_completed_recheck": "本任务的已通过提交需要复核被引用任务是否已完成验收",
        "no_approved_unpaid": "没有已通过但未支付的提交",
        "approved_claim_gaps": "已通过未支付提交缺少可自动复核证据，阻止结算",
        "open_reviews": "仍有未审核提交，先完成审核再结束任务",
    },
    "en-US": {
        "missing_participant": "Submission record is missing participant address",
        "already_approved_or_paid": "Submission is already approved or paid",
        "already_rejected": "Submission was already rejected",
        "missing_task_id": "Missing task ID",
        "missing_wallet": "Missing wallet address",
        "wallet_mismatch": "Submitted wallet address does not match participant address",
        "missing_screenshot": "Missing screenshot link or verifiable screenshot evidence",
        "read_task_failed": "Unable to read referenced task on-chain data",
        "task_self_reference": "Submitted task ID cannot be the review task itself",
        "task_creator_mismatch": "Submitted wallet is not the referenced task creator",
        "task_creator_is_employer": "Referenced task cannot be created by the reviewing employer wallet",
        "task_status_invalid": "Referenced task has an invalid status",
        "task_title_short": "Referenced task title is too short",
        "task_description_short": "Referenced task description is insufficient",
        "task_requirements_missing": "Referenced task acceptance criteria are missing",
        "task_no_bounty": "Referenced task has no valid bounty",
        "task_bad_participant_limit": "Referenced task participant limit is invalid",
        "task_bad_time_range": "Referenced task time range is invalid",
        "task_too_old": "Referenced task predates the review task and cannot prove task-specific completion",
        "task_must_be_completed": "This task requires the referenced task to be truly completed and accepted/settled",
        "qualified": "Meets acceptance criteria",
        "missing_machine_task_id": "Missing machine-readable task ID",
        "missing_machine_wallet": "Missing machine-readable full wallet address",
        "missing_screenshot_evidence": "Missing screenshot evidence",
        "approved_needs_completed_recheck": "Approved submission must be rechecked for referenced-task completion",
        "no_approved_unpaid": "No approved unpaid submissions",
        "approved_claim_gaps": "Approved unpaid submissions lack auto-verifiable evidence; settlement blocked",
        "open_reviews": "There are still unreviewed submissions; finish review before ending the task",
    },
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def load_env_file(path=ENV_FILE):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def language_for(text=""):
    requested = (DEFAULT_LANGUAGE or "auto").lower()
    if requested in {"zh", "zh-cn", "cn", "chinese", "中文"}:
        return "zh-CN"
    if requested in {"en", "en-us", "english"}:
        return "en-US"
    return "zh-CN" if any("\u4e00" <= ch <= "\u9fff" for ch in str(text or "")) else "en-US"


def msg(key, text="", **values):
    template = MESSAGES[language_for(text)].get(key, key)
    return template.format(**values) if values else template


def intish(value, default=0):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return default


def normalize_network(network=None):
    raw = (network or os.environ.get("NIUMA_AGENT_NETWORK") or "xlayer-mainnet").strip().lower()
    aliases = {
        "xlayer": "xlayer-mainnet",
        "mainnet": "xlayer-mainnet",
        "production": "xlayer-mainnet",
        "prod": "xlayer-mainnet",
        "testnet": "xlayer-testnet",
    }
    return aliases.get(raw, raw)


def is_mainnet(network=None):
    return normalize_network(network) == "xlayer-mainnet"


def signing_mode(network=None):
    configured = os.environ.get("NIUMA_AGENT_SIGNER_MODE")
    if configured:
        return configured.strip().lower()
    return "okx" if is_mainnet(network) else "private-key-test"


def onchainos_chain(network=None):
    return ox.chain(network)


def run_command(cmd, timeout=180):
    result = ox.run(cmd, timeout=timeout, cwd=str(ROOT))
    return {
        "returncode": result["returncode"],
        "stdout": result.get("stdout", "").strip(),
        "stderr": result.get("stderr", "").strip(),
        "cmd": cmd,
    }


def okx_wallet_address():
    return ox.wallet_address()


def signer_address():
    if os.environ.get("NIUMA_AGENT_WALLET"):
        return os.environ["NIUMA_AGENT_WALLET"]
    if signing_mode() == "okx":
        return okx_wallet_address()
    if signing_mode() != "private-key-test":
        return None
    cmd = ["node", str(SKILL_DIR / "scripts" / "niuma_private_key_signer.mjs"), "address"]
    data = json.loads(subprocess.check_output(cmd, cwd=str(ROOT), text=True, encoding="utf-8"))
    return data.get("address")


def task_related(ids):
    data = niuma_api.request_json("GET", "/api/blockchain/task-related", params={
        "task_ids": ",".join(str(i) for i in ids),
        "with_payload": 1,
        "group_by_task": 1,
    })
    if isinstance(data, dict):
        for key in ("grouped", "items", "list", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return data if isinstance(data, list) else []


def normalize_task(group):
    task = group.get("task") if isinstance(group.get("task"), dict) else group
    return {
        "id": int(task.get("task_id") or task.get("id") or task.get("taskId") or 0),
        "creator": task.get("creator") or task.get("creator_address") or task.get("creatorAddress") or "",
        "title": task.get("title") or "",
        "description": task.get("description") or "",
        "requirements": task.get("requirements") or task.get("requirement") or "",
        "status": intish(task.get("status") if task.get("status") is not None else task.get("chain_status")),
        "bountyPerUser": intish(task.get("bounty_per_user_wei") or task.get("bountyPerUser") or task.get("bounty_per_user")),
        "maxParticipants": intish(task.get("max_participants") or task.get("maxParticipants")),
        "currentParticipants": intish(task.get("current_participants") or task.get("currentParticipants")),
        "startTime": intish(task.get("start_time") or task.get("startTime")),
        "endTime": intish(task.get("end_time") or task.get("endTime")),
        "createdAt": intish(task.get("created_at") or task.get("createdAt")),
        "completedAt": intish(task.get("completed_at") or task.get("completedAt")),
        "isRefunded": bool(task.get("is_refunded") or task.get("isRefunded") or False),
    }


def normalize_submission(raw):
    participant = raw.get("participant") or raw.get("participant_address") or raw.get("participantAddress") or ""
    return {
        "participant": participant,
        "proofHash": raw.get("proof_hash") or raw.get("proofHash") or raw.get("proof_ipfs_hash") or "",
        "metadata": raw.get("metadata") or raw.get("payload") or raw.get("proof_metadata") or "",
        "status": raw.get("status") if raw.get("status") is not None else raw.get("chain_status") or raw.get("submission_status"),
        "rejectedAt": intish(raw.get("rejectedAt") or raw.get("rejected_at")),
        "isApproved": bool(raw.get("is_approved") or raw.get("isApproved") or False),
        "isPaid": bool(raw.get("is_paid") or raw.get("isPaid") or False),
        "isRejected": bool(raw.get("is_rejected") or raw.get("isRejected") or False),
        "rejectReason": raw.get("reject_reason") or raw.get("rejectReason") or "",
    }


def group_submissions(group, task_id):
    rows = group.get("submissions") or group.get("participants") or []
    submissions = [normalize_submission(row) for row in rows if isinstance(row, dict)]
    if submissions:
        return submissions
    try:
        participants = niuma_chain.get_task_participants(task_id)
    except Exception:
        return []
    output = []
    for participant in participants:
        try:
            output.append(niuma_chain.submission(task_id, participant))
        except Exception as exc:
            output.append({"participant": participant, "error": str(exc)})
    return output


def extract_claim(parent_task_id, submission):
    text = f"{submission.get('proofHash') or ''}\n{submission.get('metadata') or ''}"
    addresses = ADDRESS_RE.findall(text)
    task_numbers = []
    for match in re.finditer(r"(?:任务\s*ID|任务号|任务|task\s*id|#)\D{0,12}(\d+)", text, re.I):
        value = match.group(1)
        if value:
            task_numbers.append(int(value))
    claimed_task_ids = [tid for tid in task_numbers if tid != parent_task_id]
    return {
        "text": text.strip(),
        "claimedTaskId": claimed_task_ids[0] if claimed_task_ids else None,
        "claimedWallet": addresses[0] if addresses else None,
        "hasScreenshotEvidence": bool(URL_RE.search(text)),
    }


def requires_completed_acceptance(parent_task):
    text = " ".join([
        str(parent_task.get("title") or ""),
        str(parent_task.get("description") or ""),
        str(parent_task.get("requirements") or ""),
    ]).lower()
    completed_words = ("完成", "真实完成", "已完成", "completed", "done")
    accepted_words = ("验收", "通过", "accepted", "approved")
    return any(word in text for word in completed_words) and any(word in text for word in accepted_words)


def requires_settled_reference(parent_task):
    text = " ".join([
        str(parent_task.get("title") or ""),
        str(parent_task.get("description") or ""),
        str(parent_task.get("requirements") or ""),
    ]).lower()
    settled_words = ("结束", "结算", "支付", "已支付", "任务结束", "settled", "paid", "ended", "closed")
    return any(word in text for word in settled_words)

def valid_task_shape(task, parent_task, participant):
    lang_text = parent_task.get("title") or parent_task.get("description") or parent_task.get("requirements") or ""
    reasons = []
    if task["id"] == parent_task["id"]:
        reasons.append(msg("task_self_reference", lang_text))
    if task["creator"].lower() != participant.lower():
        reasons.append(msg("task_creator_mismatch", lang_text))
    if task["creator"].lower() == parent_task["creator"].lower():
        reasons.append(msg("task_creator_is_employer", lang_text))
    if task["status"] not in (1, 2, 3, 4):
        reasons.append(f"{msg('task_status_invalid', lang_text)}: {task['status']}")
    if len(task["title"].strip()) < 3:
        reasons.append(msg("task_title_short", lang_text))
    if len(task["description"].strip()) < 10:
        reasons.append(msg("task_description_short", lang_text))
    if len(task["requirements"].strip()) < 3:
        reasons.append(msg("task_requirements_missing", lang_text))
    if task["bountyPerUser"] <= 0:
        reasons.append(msg("task_no_bounty", lang_text))
    if task["maxParticipants"] <= 0:
        reasons.append(msg("task_bad_participant_limit", lang_text))
    if task["startTime"] and task["endTime"] and task["endTime"] <= task["startTime"]:
        reasons.append(msg("task_bad_time_range", lang_text))
    if parent_task.get("createdAt") and task.get("createdAt") and task["createdAt"] + 60 < parent_task["createdAt"]:
        reasons.append(msg("task_too_old", lang_text))
    return reasons


def completed_with_acceptance(task, related_group):
    if task["isRefunded"]:
        return False
    rows = [normalize_submission(row) for row in (related_group.get("submissions") or []) if isinstance(row, dict)]
    if not rows:
        return False
    return any(row["isPaid"] or row["isApproved"] or str(row["status"]) in ("2", "7") for row in rows)


def settled_with_acceptance(task, related_group):
    if task["status"] != 4 or task["completedAt"] <= 0 or task["isRefunded"]:
        return False
    rows = [normalize_submission(row) for row in (related_group.get("submissions") or []) if isinstance(row, dict)]
    if not rows:
        return task["currentParticipants"] > 0
    return any(row["isPaid"] or row["isApproved"] or str(row["status"]) in ("2", "7") for row in rows)

def evaluate_submission(parent_task, parent_group, submission, related_cache):
    lang_text = parent_task.get("title") or parent_task.get("description") or parent_task.get("requirements") or ""
    participant = submission.get("participant") or ""
    if not participant:
        return {"decision": "reject", "reason": msg("missing_participant", lang_text), "submission": submission}
    if submission.get("isPaid") or submission.get("isApproved"):
        return {"decision": "skip", "reason": msg("already_approved_or_paid", lang_text), "participant": participant}
    if submission.get("isRejected") or submission.get("rejectedAt") or str(submission.get("status")) == "6":
        return {"decision": "skip", "reason": f"{msg('already_rejected', lang_text)}: {submission.get('rejectReason') or ''}", "participant": participant}

    claim = extract_claim(parent_task["id"], submission)
    reasons = []
    if not claim["claimedTaskId"]:
        reasons.append(msg("missing_task_id", lang_text))
    if not claim["claimedWallet"]:
        reasons.append(msg("missing_wallet", lang_text))
    elif claim["claimedWallet"].lower() != participant.lower():
        reasons.append(msg("wallet_mismatch", lang_text))
    if not claim["hasScreenshotEvidence"]:
        reasons.append(msg("missing_screenshot", lang_text))

    claimed_task = None
    claimed_group = None
    if claim["claimedTaskId"]:
        if claim["claimedTaskId"] not in related_cache:
            groups = task_related([claim["claimedTaskId"]])
            related_cache[claim["claimedTaskId"]] = groups[0] if groups else {}
        claimed_group = related_cache.get(claim["claimedTaskId"]) or {}
        try:
            claimed_task = niuma_chain.task(claim["claimedTaskId"])
        except Exception as exc:
            reasons.append(f"{msg('read_task_failed', lang_text)}: {exc}")
        if claimed_task:
            reasons.extend(valid_task_shape(claimed_task, parent_task, participant))
            if requires_completed_acceptance(parent_task) and not completed_with_acceptance(claimed_task, claimed_group):
                reasons.append(msg("task_must_be_completed", lang_text))
            if requires_settled_reference(parent_task) and not settled_with_acceptance(claimed_task, claimed_group):
                reasons.append(msg("task_must_be_completed", lang_text))

    decision = "approve" if not reasons else "reject"
    return {
        "decision": decision,
        "reason": msg("qualified", lang_text) if decision == "approve" else "; ".join(reasons),
        "participant": participant,
        "claimed": claim,
        "claimedTask": claimed_task,
        "submission": submission,
    }


def send_core_tx(action, task_id, data, dry_run):
    mode = signing_mode()
    if is_mainnet() and mode == "private-key-test":
        return {
            "ok": False,
            "action": action,
            "taskId": task_id,
            "signerMode": mode,
            "error": "private-key-test is disabled for X Layer mainnet; use OKX OnchainOS signing",
        }
    reviewer = signer_address()
    if mode == "okx":
        if not reviewer:
            return {
                "ok": False,
                "action": action,
                "taskId": task_id,
                "signerMode": mode,
                "error": "NIUMA_AGENT_WALLET or OKX OnchainOS wallet session is required",
            }
        preflight = ox.preflight(reviewer, niuma_chain.CORE, data, purpose=f"reviewer:{action}")
        preflight_ok = bool(preflight.get("ok"))
        if dry_run:
            return {
                "ok": preflight_ok,
                "dryRun": True,
                "action": action,
                "taskId": task_id,
                "signerMode": mode,
                "signer": reviewer,
                "chain": onchainos_chain(),
                "to": niuma_chain.CORE,
                "data": data,
                "preflight": preflight,
            }
        if not preflight_ok:
            return {
                "ok": False,
                "dryRun": False,
                "action": action,
                "taskId": task_id,
                "signerMode": mode,
                "signer": reviewer,
                "chain": onchainos_chain(),
                "to": niuma_chain.CORE,
                "data": data,
                "error": preflight.get("blocker", "OnchainOS reviewer preflight failed"),
                "preflight": preflight,
            }
        cmd = [
            "onchainos",
            "wallet",
            "contract-call",
            "--chain",
            onchainos_chain(),
            "--to",
            niuma_chain.CORE,
            "--input-data",
            data,
            "--amt",
            "0",
            "--from",
            reviewer,
        ]
        if os.environ.get("NIUMA_AGENT_REVIEWER_AUTONOMOUS") == "1" or os.environ.get("NIUMA_ONCHAINOS_FORCE") == "1":
            cmd.append("--force")
        result = run_command(cmd)
        return {
            "ok": result["returncode"] == 0,
            "dryRun": False,
            "action": action,
            "taskId": task_id,
            "signerMode": mode,
            "signer": reviewer,
            "chain": onchainos_chain(),
            "to": niuma_chain.CORE,
            "data": data,
            "preflight": preflight,
            "result": result,
        }

    cmd = [
        "node",
        str(SKILL_DIR / "scripts" / "niuma_private_key_signer.mjs"),
        "send",
        "--task-id",
        str(task_id),
        "--to",
        niuma_chain.CORE,
        "--data",
        data,
    ]
    if dry_run:
        cmd.append("--dry-run")
    return json.loads(subprocess.check_output(cmd, cwd=str(ROOT), text=True, encoding="utf-8"))


def send_review_tx(action, task_id, participant, reason, dry_run):
    if action == "approve":
        data = niuma_chain.calldata_approve_submission(task_id, participant)
    else:
        data = niuma_chain.calldata_reject_submission(task_id, participant, reason[:220])
    return send_core_tx(action, task_id, data, dry_run)


def settle_plan(task_id, parent_task, submissions, reviewer, execute):
    lang_text = parent_task.get("title") or parent_task.get("description") or parent_task.get("requirements") or ""
    approved_unpaid = [
        sub
        for sub in submissions
        if (sub.get("isApproved") and not sub.get("isPaid"))
    ]
    open_review = [
        sub.get("participant")
        for sub in submissions
        if not (sub.get("isApproved") or sub.get("isPaid") or sub.get("isRejected") or sub.get("rejectedAt") or str(sub.get("status")) == "6")
    ]
    approved_claim_gaps = []
    for sub in approved_unpaid:
        claim = extract_claim(task_id, sub)
        gaps = []
        if not claim["claimedTaskId"]:
            gaps.append(msg("missing_machine_task_id", lang_text))
        if not claim["claimedWallet"]:
            gaps.append(msg("missing_machine_wallet", lang_text))
        elif claim["claimedWallet"].lower() != (sub.get("participant") or "").lower():
            gaps.append(msg("wallet_mismatch", lang_text))
        if not claim["hasScreenshotEvidence"]:
            gaps.append(msg("missing_screenshot_evidence", lang_text))
        if requires_settled_reference(parent_task):
            gaps.append(msg("approved_needs_completed_recheck", lang_text))
        if gaps:
            approved_claim_gaps.append({
                "participant": sub.get("participant"),
                "gaps": gaps,
                "proofHash": sub.get("proofHash"),
                "metadata": sub.get("metadata"),
            })
    plan = {
        "taskId": task_id,
        "action": "endTask",
        "approvedUnpaidParticipants": [sub.get("participant") for sub in approved_unpaid],
        "openReviewParticipants": open_review,
        "approvedClaimGaps": approved_claim_gaps,
        "eligible": bool(approved_unpaid) and not open_review,
        "reason": "",
    }
    if not approved_unpaid:
        plan["reason"] = msg("no_approved_unpaid", lang_text)
        return plan
    if approved_claim_gaps:
        plan["eligible"] = False
        plan["reason"] = msg("approved_claim_gaps", lang_text)
        return plan
    if open_review:
        plan["reason"] = msg("open_reviews", lang_text)
        return plan
    if reviewer:
        try:
            plan["dryRunTx"] = send_core_tx("end-task", task_id, niuma_chain.calldata_end_task(task_id), dry_run=not execute)
        except subprocess.CalledProcessError as exc:
            plan["eligible"] = False
            plan["dryRunTx"] = {"ok": False, "error": (exc.output or str(exc)).strip()}
            plan["reason"] = "endTask 预执行失败"
    return plan


def audit(task_ids, execute=False, settle_approved=False):
    load_env_file()
    reviewer = signer_address()
    groups = task_related(task_ids)
    by_id = {normalize_task(group)["id"]: group for group in groups}
    report = {
        "createdAt": int(time.time()),
        "reviewer": reviewer,
        "execute": execute,
        "language": DEFAULT_LANGUAGE or "auto",
        "taskIds": task_ids,
        "results": [],
        "writes": [],
        "blockers": [],
    }
    if execute and os.environ.get("NIUMA_AGENT_REVIEWER_AUTONOMOUS") != "1":
        report["blockers"].append("NIUMA_AGENT_REVIEWER_AUTONOMOUS=1 is required for approve/reject writes")
        execute = False

    related_cache = dict(by_id)
    for task_id in task_ids:
        group = by_id.get(task_id)
        if not group:
            report["results"].append({"taskId": task_id, "error": "task-related API returned no group"})
            continue
        parent_task = niuma_chain.task(task_id)
        if reviewer and parent_task["creator"].lower() != reviewer.lower():
            report["blockers"].append(f"reviewer {reviewer} is not task {task_id} creator {parent_task['creator']}")
        submissions = group_submissions(group, task_id)
        task_result = {"taskId": task_id, "parentTask": parent_task, "submissions": []}
        for sub in submissions:
            decision = evaluate_submission(parent_task, group, sub, related_cache)
            task_result["submissions"].append(decision)
            if execute and decision["decision"] in ("approve", "reject") and not report["blockers"]:
                tx = send_review_tx(decision["decision"], task_id, decision["participant"], decision["reason"], dry_run=False)
                report["writes"].append({"taskId": task_id, "participant": decision["participant"], "action": decision["decision"], "tx": tx})
            elif decision["decision"] in ("approve", "reject"):
                if reviewer:
                    try:
                        decision["dryRunTx"] = send_review_tx(decision["decision"], task_id, decision["participant"], decision["reason"], dry_run=True)
                    except subprocess.CalledProcessError as exc:
                        decision["dryRunTx"] = {"ok": False, "error": (exc.output or str(exc)).strip()}
        if settle_approved:
            task_result["settlement"] = settle_plan(task_id, parent_task, submissions, reviewer, execute and not report["blockers"])
            if execute and task_result["settlement"].get("dryRunTx", {}).get("ok") and task_result["settlement"].get("eligible") and not report["blockers"]:
                report["writes"].append({
                    "taskId": task_id,
                    "action": "endTask",
                    "tx": task_result["settlement"]["dryRunTx"],
                })
        report["results"].append(task_result)

    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"task-review-{int(time.time())}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = str(path)
    return report


def main():
    parser = argparse.ArgumentParser(description="NIUMA employer reviewer and settlement helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--task-ids", required=True, help="Comma-separated employer task ids")
    p_audit.add_argument("--execute", action="store_true", help="Approve/reject on-chain when autonomous reviewer policy is enabled")
    p_audit.add_argument("--settle-approved", action="store_true", help="Also plan or execute endTask for approved unpaid submissions")
    p_audit.add_argument("--language", default=None, help="Report language: auto, zh-CN, or en-US")
    args = parser.parse_args()
    if args.cmd == "audit":
        global DEFAULT_LANGUAGE
        if args.language:
            DEFAULT_LANGUAGE = args.language
        task_ids = [int(x.strip()) for x in args.task_ids.split(",") if x.strip()]
        print_json(audit(task_ids, execute=args.execute, settle_approved=args.settle_approved))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
