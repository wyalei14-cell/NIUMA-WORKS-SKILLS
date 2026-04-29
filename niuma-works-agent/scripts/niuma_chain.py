#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.request

from Crypto.Hash import keccak

RPC_URL = "https://testrpc.xlayer.tech/terigon"
CORE = "0xcf52846E69a4772d5C9142d1487f4bb44d918cC5"
USER_PROFILE = "0x3D105F9bC85ddA6Baf89D8eA4040ec45F0CF9B93"
NIUMA_TOKEN = "0xad9e1ac142bb3c706c42a5bc4eceeb9364fd0939"
ZERO = "0x0000000000000000000000000000000000000000"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def selector(hex_selector, *words):
    return "0x" + hex_selector + "".join(word.rjust(64, "0") for word in words)


def method_selector(signature):
    digest = keccak.new(digest_bits=256)
    digest.update(signature.encode("utf-8"))
    return digest.hexdigest()[:8]


def uint_word(value):
    return hex(int(value))[2:]


def addr_word(address):
    return address.lower().replace("0x", "").rjust(64, "0")


def bool_word(value):
    return "1" if value else "0"


def encode_string(value):
    raw = str(value or "").encode("utf-8")
    padded_len = ((len(raw) + 31) // 32) * 32
    return uint_word(len(raw)).rjust(64, "0") + raw.hex().ljust(padded_len * 2, "0")


def encode_abi(types, values):
    head = []
    tail = []
    dynamic = {"string", "bytes"}
    head_size = 32 * len(types)
    tail_size = 0
    for typ, value in zip(types, values):
        if typ in dynamic:
            encoded = encode_string(value)
            head.append(uint_word(head_size + tail_size).rjust(64, "0"))
            tail.append(encoded)
            tail_size += len(encoded) // 2
        elif typ.startswith("uint") or typ.startswith("int"):
            head.append(uint_word(value).rjust(64, "0"))
        elif typ == "address":
            head.append(addr_word(value))
        elif typ == "bool":
            head.append(bool_word(value).rjust(64, "0"))
        else:
            raise ValueError(f"unsupported ABI type: {typ}")
    return "".join(head + tail)


def encode_call(signature, types, values):
    return "0x" + method_selector(signature) + encode_abi(types, values)


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        RPC_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "NIUMA-WORKS-Agent/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]


def eth_call(to, data):
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])


def split_words(hex_data):
    payload = hex_data[2:] if hex_data.startswith("0x") else hex_data
    return [payload[i:i + 64] for i in range(0, len(payload), 64)]


def as_int(word):
    return int(word or "0", 16)


def as_addr(word):
    return "0x" + word[-40:]


def read_string(words, index):
    offset = as_int(words[index]) // 32
    length = as_int(words[offset])
    raw = "".join(words[offset + 1:offset + 1 + ((length + 31) // 32)])
    return bytes.fromhex(raw[:length * 2]).decode("utf-8", errors="replace")


def task(task_id):
    # tasks(uint256): 0x8d977672
    result = eth_call(CORE, selector("8d977672", uint_word(task_id)))
    words = split_words(result)
    return {
        "id": as_int(words[0]),
        "creator": as_addr(words[1]),
        "hunter": as_addr(words[2]),
        "title": read_string(words, 3),
        "description": read_string(words, 4),
        "bountyPerUser": as_int(words[5]),
        "totalBounty": as_int(words[6]),
        "maxParticipants": as_int(words[7]),
        "currentParticipants": as_int(words[8]),
        "startTime": as_int(words[9]),
        "endTime": as_int(words[10]),
        "taskType": as_int(words[11]),
        "status": as_int(words[12]),
        "disputeStatus": as_int(words[13]),
        "requirements": read_string(words, 14),
        "createdAt": as_int(words[15]),
        "completedAt": as_int(words[16]),
        "isRefunded": bool(as_int(words[17])),
        "tokenAddress": as_addr(words[18]),
        "categoryId": as_int(words[19]),
        "isPaused": bool(as_int(words[20])),
    }


def can_accept(address, reward_wei, token):
    # canAcceptTask(address,uint256,address): 0xb44d0157
    result = eth_call(USER_PROFILE, selector("b44d0157", addr_word(address), uint_word(reward_wei), addr_word(token)))
    return bool(as_int(split_words(result)[0]))


def call_uint(signature, types, values, contract=USER_PROFILE):
    result = eth_call(contract, encode_call(signature, types, values))
    words = split_words(result)
    if not words or words == [""]:
        raise RuntimeError(f"empty return for {signature}")
    return as_int(words[0])


def call_bool(signature, types, values, contract=USER_PROFILE):
    return bool(call_uint(signature, types, values, contract))


def profile(address):
    output = {"address": address, "errors": {}}
    fields = {
        "hunterStake": ("hunterStake(address)", ["address"], [address], "uint"),
        "lockedStake": ("lockedStake(address)", ["address"], [address], "uint"),
        "lastTaskTime": ("lastTaskTime(address)", ["address"], [address], "uint"),
        "taskCooldown": ("taskCooldown()", [], [], "uint"),
        "minCreditScore": ("minCreditScore()", [], [], "uint"),
        "minHunterStake": ("minHunterStake()", [], [], "uint"),
        "isStakeExempt": ("isStakeExempt(address)", ["address"], [address], "bool"),
    }
    for name, (sig, types, values, kind) in fields.items():
        try:
            output[name] = call_bool(sig, types, values) if kind == "bool" else call_uint(sig, types, values)
        except Exception as exc:
            output[name] = None
            output["errors"][name] = str(exc)
    try:
        credit_raw = eth_call(USER_PROFILE, encode_call("getCredit(address)", ["address"], [address]))
        credit_words = split_words(credit_raw)
        if len(credit_words) < 5:
            raise RuntimeError(f"short return: {credit_raw}")
        output["credit"] = {
            "hunter": as_int(credit_words[0]),
            "employer": as_int(credit_words[1]),
            "hunterSuccess": as_int(credit_words[2]),
            "employerSuccess": as_int(credit_words[3]),
            "initialized": bool(as_int(credit_words[4])),
        }
    except Exception as exc:
        output["credit"] = None
        output["errors"]["credit"] = str(exc)
    return output


def accept_diagnostics(address, task_id):
    info = task(task_id)
    prof = profile(address)
    available = max(0, (prof.get("hunterStake") or 0) - (prof.get("lockedStake") or 0))
    now = int(__import__("time").time())
    cooldown_remaining = max(0, (prof.get("lastTaskTime") or 0) + (prof.get("taskCooldown") or 0) - now)
    reasons = []
    if info["creator"].lower() == address.lower():
        reasons.append("wallet is task creator")
    if info["status"] != 1:
        reasons.append(f"task status is not open: {info['status']}")
    if info["currentParticipants"] >= info["maxParticipants"]:
        reasons.append("task participant slots are full")
    if prof.get("minHunterStake") is not None and available < prof["minHunterStake"] and not prof.get("isStakeExempt"):
        reasons.append("available hunter stake is below minHunterStake")
    if prof.get("credit") and prof.get("minCreditScore") is not None and prof["credit"]["hunter"] < prof["minCreditScore"]:
        reasons.append("hunter credit is below minCreditScore")
    if cooldown_remaining > 0:
        reasons.append("task cooldown is still active")
    can = can_accept(address, info["bountyPerUser"], info["tokenAddress"])
    if not can and not reasons:
        reasons.append("canAcceptTask returned false without a locally decoded reason")
    return {
        "taskId": task_id,
        "address": address,
        "canAccept": can,
        "reasons": reasons,
        "cooldownRemainingSeconds": cooldown_remaining,
        "availableStake": available,
        "task": info,
        "profile": prof,
    }


def calldata_participate(task_id):
    return encode_call("participateTask(uint256)", ["uint256"], [task_id])


def calldata_submit(task_id, proof_hash, metadata):
    return encode_call(
        "submitTask(uint256,string,string)",
        ["uint256", "string", "string"],
        [task_id, proof_hash, metadata],
    )


def calldata_dispute(task_id, participant, reason, evidence_hash):
    return encode_call(
        "createDispute(uint256,address,string,string)",
        ["uint256", "address", "string", "string"],
        [task_id, participant, reason, evidence_hash],
    )


def calldata_approve_submission(task_id, participant):
    return encode_call(
        "approveSubmission(uint256,address)",
        ["uint256", "address"],
        [task_id, participant],
    )


def calldata_reject_submission(task_id, participant, reason):
    return encode_call(
        "rejectSubmission(uint256,address,string)",
        ["uint256", "address", "string"],
        [task_id, participant, reason],
    )


def calldata_reject_submission_with_slash(task_id, participant, reason, slash=False):
    return encode_call(
        "rejectSubmissionWithSlash(uint256,address,string,bool)",
        ["uint256", "address", "string", "bool"],
        [task_id, participant, reason, slash],
    )


def calldata_end_task(task_id):
    return encode_call("endTask(uint256)", ["uint256"], [task_id])


def calldata_force_end_task(task_id):
    return encode_call("forceEndTask(uint256)", ["uint256"], [task_id])


def get_task_participants(task_id):
    result = eth_call(CORE, encode_call("getTaskParticipants(uint256)", ["uint256"], [task_id]))
    words = split_words(result)
    if not words or words == [""]:
        return []
    offset = as_int(words[0]) // 32
    length = as_int(words[offset])
    return [as_addr(words[offset + 1 + i]) for i in range(length)]


def submission(task_id, participant):
    result = eth_call(CORE, encode_call("submissions(uint256,address)", ["uint256", "address"], [task_id, participant]))
    words = split_words(result)
    if len(words) < 11:
        raise RuntimeError(f"short submission return: {result}")
    return {
        "taskId": as_int(words[0]),
        "participant": as_addr(words[1]),
        "proofHash": read_string(words, 2),
        "metadata": read_string(words, 3),
        "submittedAt": as_int(words[4]),
        "participantJoinTime": as_int(words[5]),
        "rejectedAt": as_int(words[6]),
        "isApproved": bool(as_int(words[7])),
        "isPaid": bool(as_int(words[8])),
        "isRejected": bool(as_int(words[9])),
        "rejectReason": read_string(words, 10),
    }


def calldata_create_task(title, description, task_type, bounty_per_user, max_participants, start_time, end_time, requirements, token_address, category_id, expand_key="", expand_value=""):
    return encode_call(
        "createTask(string,string,uint8,uint256,uint256,uint256,uint256,string,address,uint256,string,string)",
        ["string", "string", "uint8", "uint256", "uint256", "uint256", "uint256", "string", "address", "uint256", "string", "string"],
        [title, description, task_type, bounty_per_user, max_participants, start_time, end_time, requirements, token_address, category_id, expand_key, expand_value],
    )


def erc20_balance(token, owner):
    return call_uint("balanceOf(address)", ["address"], [owner], token)


def erc20_allowance(token, owner, spender):
    return call_uint("allowance(address,address)", ["address", "address"], [owner, spender], token)


def calldata_approve(spender, amount):
    return encode_call("approve(address,uint256)", ["address", "uint256"], [spender, amount])


def calldata_stake_hunter(amount):
    return encode_call("stakeHunter(uint256)", ["uint256"], [amount])


def stake_diagnostics(address, target_stake=None):
    prof = profile(address)
    min_stake = max(prof.get("minHunterStake") or 0, int(target_stake or 0))
    current = prof.get("hunterStake") or 0
    needed = max(0, min_stake - current)
    balance = erc20_balance(NIUMA_TOKEN, address)
    allowance = erc20_allowance(NIUMA_TOKEN, address, USER_PROFILE)
    return {
        "address": address,
        "token": NIUMA_TOKEN,
        "profileContract": USER_PROFILE,
        "hunterStake": current,
        "minHunterStake": min_stake,
        "neededStake": needed,
        "niumaBalance": balance,
        "allowanceToProfile": allowance,
        "needsApprove": needed > 0 and allowance < needed,
        "needsStake": needed > 0,
        "hasEnoughBalance": balance >= needed,
        "approveCalldata": calldata_approve(USER_PROFILE, needed) if needed > 0 else None,
        "stakeCalldata": calldata_stake_hunter(needed) if needed > 0 else None,
    }


def main():
    parser = argparse.ArgumentParser(description="NIUMA WORKS chain helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_task = sub.add_parser("task")
    p_task.add_argument("--id", required=True, type=int)
    p_accept = sub.add_parser("can-accept")
    p_accept.add_argument("--address", required=True)
    p_accept.add_argument("--task-id", required=True, type=int)
    p_profile = sub.add_parser("profile")
    p_profile.add_argument("--address", required=True)
    p_diag = sub.add_parser("diagnose-accept")
    p_diag.add_argument("--address", required=True)
    p_diag.add_argument("--task-id", required=True, type=int)
    p_participants = sub.add_parser("participants")
    p_participants.add_argument("--task-id", required=True, type=int)
    p_submission = sub.add_parser("submission")
    p_submission.add_argument("--task-id", required=True, type=int)
    p_submission.add_argument("--participant", required=True)
    p_stake = sub.add_parser("stake-diagnostics")
    p_stake.add_argument("--address", required=True)
    p_stake.add_argument("--target-stake", type=int, default=None)
    p_data = sub.add_parser("calldata")
    p_data.add_argument("method", choices=[
        "participate",
        "submit",
        "dispute",
        "approve-profile",
        "stake-hunter",
        "approve-submission",
        "reject-submission",
        "reject-submission-with-slash",
        "end-task",
        "force-end-task",
    ])
    p_data.add_argument("--task-id", required=True, type=int)
    p_data.add_argument("--proof")
    p_data.add_argument("--metadata", default="")
    p_data.add_argument("--participant")
    p_data.add_argument("--reason")
    p_data.add_argument("--evidence", default="")
    args = parser.parse_args()

    if args.cmd == "task":
        print(json.dumps(task(args.id), ensure_ascii=False, indent=2))
    elif args.cmd == "can-accept":
        info = task(args.task_id)
        value = can_accept(args.address, info["bountyPerUser"], info["tokenAddress"])
        print(json.dumps({"taskId": args.task_id, "address": args.address, "canAccept": value, "task": info}, ensure_ascii=False, indent=2))
    elif args.cmd == "profile":
        print(json.dumps(profile(args.address), ensure_ascii=False, indent=2))
    elif args.cmd == "diagnose-accept":
        print(json.dumps(accept_diagnostics(args.address, args.task_id), ensure_ascii=False, indent=2))
    elif args.cmd == "participants":
        print(json.dumps({"taskId": args.task_id, "participants": get_task_participants(args.task_id)}, ensure_ascii=False, indent=2))
    elif args.cmd == "submission":
        print(json.dumps(submission(args.task_id, args.participant), ensure_ascii=False, indent=2))
    elif args.cmd == "stake-diagnostics":
        print(json.dumps(stake_diagnostics(args.address, args.target_stake), ensure_ascii=False, indent=2))
    elif args.cmd == "calldata":
        if args.method == "participate":
            data = calldata_participate(args.task_id)
        elif args.method == "submit":
            if not args.proof:
                raise RuntimeError("--proof is required")
            data = calldata_submit(args.task_id, args.proof, args.metadata)
        else:
            if args.method == "approve-profile":
                data = calldata_approve(USER_PROFILE, args.task_id)
                print(json.dumps({"method": args.method, "amount": args.task_id, "to": NIUMA_TOKEN, "calldata": data}, ensure_ascii=False, indent=2))
                return
            if args.method == "stake-hunter":
                data = calldata_stake_hunter(args.task_id)
                print(json.dumps({"method": args.method, "amount": args.task_id, "to": USER_PROFILE, "calldata": data}, ensure_ascii=False, indent=2))
                return
            if args.method == "approve-submission":
                if not args.participant:
                    raise RuntimeError("--participant is required")
                data = calldata_approve_submission(args.task_id, args.participant)
                print(json.dumps({"method": args.method, "taskId": args.task_id, "participant": args.participant, "calldata": data}, ensure_ascii=False, indent=2))
                return
            if args.method == "reject-submission":
                if not args.participant or not args.reason:
                    raise RuntimeError("--participant and --reason are required")
                data = calldata_reject_submission(args.task_id, args.participant, args.reason)
                print(json.dumps({"method": args.method, "taskId": args.task_id, "participant": args.participant, "reason": args.reason, "calldata": data}, ensure_ascii=False, indent=2))
                return
            if args.method == "reject-submission-with-slash":
                if not args.participant or not args.reason:
                    raise RuntimeError("--participant and --reason are required")
                data = calldata_reject_submission_with_slash(args.task_id, args.participant, args.reason, slash=True)
                print(json.dumps({"method": args.method, "taskId": args.task_id, "participant": args.participant, "reason": args.reason, "slash": True, "calldata": data}, ensure_ascii=False, indent=2))
                return
            if args.method == "end-task":
                data = calldata_end_task(args.task_id)
                print(json.dumps({"method": args.method, "taskId": args.task_id, "calldata": data}, ensure_ascii=False, indent=2))
                return
            if args.method == "force-end-task":
                data = calldata_force_end_task(args.task_id)
                print(json.dumps({"method": args.method, "taskId": args.task_id, "calldata": data}, ensure_ascii=False, indent=2))
                return
            if not args.participant or not args.reason:
                raise RuntimeError("--participant and --reason are required")
            data = calldata_dispute(args.task_id, args.participant, args.reason, args.evidence)
        print(json.dumps({"method": args.method, "taskId": args.task_id, "calldata": data}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
