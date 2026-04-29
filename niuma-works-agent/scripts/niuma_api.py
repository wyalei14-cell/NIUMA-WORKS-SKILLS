#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

API_BASE = "https://taskapi.niuma.works"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def request_json(method, path, params=None, body=None, token=None):
    url = API_BASE + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        query = urllib.parse.urlencode(clean)
        if query:
            url += "?" + query
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 NIUMA-WORKS-Agent/1.0",
        "Origin": "https://task.niuma.works",
        "Referer": "https://task.niuma.works/",
    }
    token = token or os.environ.get("NIUMA_API_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    if isinstance(payload, dict) and payload.get("code") not in (None, 200):
        raise RuntimeError(payload.get("message") or "NIUMA API error")
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def chain_data(table, page=1, limit=50, sort_by=None, sort_order=None, **extra):
    params = {"table": table, "page": page, "limit": limit, "sort_by": sort_by, "sort_order": sort_order}
    params.update(extra)
    return request_json("GET", "/chain-data/query", params=params)


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="NIUMA WORKS API helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tasks")
    sub.add_parser("tokens")
    sub.add_parser("categories")
    created = sub.add_parser("user-created")
    created.add_argument("--address", required=True)
    joined = sub.add_parser("user-participated")
    joined.add_argument("--address", required=True)
    related = sub.add_parser("task-related")
    related.add_argument("--ids", required=True, help="Comma-separated task ids, for example <task-id[,task-id...]>")
    related.add_argument("--with-payload", type=int, default=1)
    related.add_argument("--group-by-task", type=int, default=1)
    messages = sub.add_parser("messages")
    messages.add_argument("--address", required=True)
    history = sub.add_parser("history")
    history.add_argument("--contact-address", required=True)
    send = sub.add_parser("send-message")
    send.add_argument("--from-address", required=True)
    send.add_argument("--to-address", required=True)
    send.add_argument("--task-id", required=True, type=int)
    send.add_argument("--content", required=True)
    send.add_argument("--token", default=None)

    args = parser.parse_args()
    if args.cmd == "tasks":
        print_json(chain_data("sj_tasks", 1, 50, "task_id", "desc"))
    elif args.cmd == "tokens":
        print_json(chain_data("sj_chain_tokens", 1, 200, "sort_order", "asc"))
    elif args.cmd == "categories":
        print_json(chain_data("sj_chain_categories", 1, 200, "sort_order", "asc", enabled=1))
    elif args.cmd == "user-created":
        print_json(request_json("GET", "/task/user-created", params={"address": args.address, "page": 1, "limit": 50}))
    elif args.cmd == "user-participated":
        print_json(request_json("GET", "/task/user-participated", params={"address": args.address, "page": 1, "limit": 50}))
    elif args.cmd == "task-related":
        print_json(request_json("GET", "/api/blockchain/task-related", params={
            "task_ids": args.ids,
            "with_payload": args.with_payload,
            "group_by_task": args.group_by_task,
        }))
    elif args.cmd == "messages":
        print_json(request_json("GET", "/api/messages", params={"wallet": args.address, "address": args.address, "page": 1, "limit": 50}))
    elif args.cmd == "history":
        print_json(request_json("GET", "/message/history", params={"contact_address": args.contact_address, "page": 1, "limit": 50}))
    elif args.cmd == "send-message":
        print_json(request_json("POST", "/message/send", body={
            "to_address": args.to_address,
            "content": args.content,
            "task_id": args.task_id,
            "type": "text",
            "sender": args.from_address,
            "from_address": args.from_address,
            "wallet": args.from_address,
        }, token=args.token))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
