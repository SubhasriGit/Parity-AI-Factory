"""Token and cost report for Copilot Chat agent runs, such as the Orchestrator agent.

Reads the per-session debug logs Copilot Chat writes and sums the llm_request events
in main.jsonl and runSubagent-<agent>-<uuid>.jsonl. Cost is computed from the
token_prices in each session's models.json. Standard library only.

Usage: python cost_usage.py [--log-dir DIR] [--out-dir DIR] [--latest]
"""
import argparse
import csv
import glob
import json
import os
from collections import defaultdict
from datetime import datetime

WORKSPACE_STORAGE = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "Code", "User", "workspaceStorage")


def discover_log_dir():
    override = os.environ.get("COPILOT_CHAT_LOG_DIR")
    if override:
        return override
    candidates = [path for path in glob.glob(os.path.join(
        WORKSPACE_STORAGE, "*", "GitHub.copilot-chat", "debug-logs")) if os.path.isdir(path)]
    return max(candidates, key=os.path.getmtime) if candidates else os.path.join(
        WORKSPACE_STORAGE, "unknown-workspace", "GitHub.copilot-chat", "debug-logs")


DEFAULT_LOG_DIR = discover_log_dir()
SUBAGENT_PREFIX = "runSubagent-"
REQUEST_FIELDS = ["time", "session", "agent", "model", "input_tokens", "cached_tokens", "output_tokens",
                  "duration_ms", "status", "cost", "logged_cost"]
CALL_FIELDS = ["time", "session", "caller", "callee", "duration_ms", "status"]


def agent_from_file(path):
    """Return the agent name from runSubagent-<agent>-<uuid>.jsonl."""
    stem = os.path.basename(path)[len(SUBAGENT_PREFIX):-len(".jsonl")]
    return stem.rsplit("-", 5)[0]


def read_events(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_models(session_dir):
    path = os.path.join(session_dir, "models.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {m["id"]: m for m in json.load(f)}


def price_request(model, input_tokens, output_tokens, cached_tokens=0):
    prices = model.get("billing", {}).get("token_prices") if model else None
    if not prices:
        return None
    tier = prices["default"]
    if input_tokens > tier.get("max_prompt_tokens", float("inf")):
        tier = prices.get("long_context", tier)
    cache_price = tier.get("cache_read_price", tier["input_price"])
    uncached = max(input_tokens - cached_tokens, 0)
    cost = uncached * tier["input_price"] + cached_tokens * \
        cache_price + output_tokens * tier["output_price"]
    return cost / (prices.get("batch_size") or 1000000)


def to_time(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def session_mtime(session_dir):
    return max((os.path.getmtime(os.path.join(session_dir, f)) for f in os.listdir(session_dir)), default=0)


def collect(log_dir, latest=False):
    rows, edges = [], []
    attr_keys = set()
    session_dirs = [d for d in sorted(
        glob.glob(os.path.join(log_dir, "*"))) if os.path.isdir(d)]
    if latest and session_dirs:
        session_dirs = [max(session_dirs, key=session_mtime)]
    for session_dir in session_dirs:
        session = os.path.basename(session_dir)
        models = load_models(session_dir)
        sources = [("main", os.path.join(session_dir, "main.jsonl"))]
        sources += [(agent_from_file(p), p)
                    for p in glob.glob(os.path.join(session_dir, SUBAGENT_PREFIX + "*.jsonl"))]
        sources = [(agent, path)
                   for agent, path in sources if os.path.exists(path)]
        span_owner = {}
        for agent, path in sources:
            for event in read_events(path):
                if event.get("spanId"):
                    span_owner[event["spanId"]] = agent
        for agent, path in sources:
            for event in read_events(path):
                attrs = event.get("attrs", {})
                if event.get("type") == "subagent":
                    edges.append({
                        "time": to_time(event.get("ts", 0)),
                        "session": session,
                        "caller": span_owner.get(event.get("parentSpanId"), "unknown"),
                        "callee": attrs.get("agentName", event.get("name", "unknown")),
                        "duration_ms": event.get("dur", 0),
                        "status": event.get("status", ""),
                    })
                    continue
                if event.get("type") != "llm_request":
                    continue
                attr_keys.update(attrs.keys())
                model_id = attrs.get("model", "unknown")
                inp = int(attrs.get("inputTokens") or 0)
                out = int(attrs.get("outputTokens") or 0)
                cached = int(attrs.get("cachedTokens") or 0)
                nano = attrs.get("copilotUsageNanoAiu")
                rows.append({
                    "time": to_time(event.get("ts", 0)),
                    "session": session,
                    "agent": agent,
                    "model": model_id,
                    "input_tokens": inp,
                    "cached_tokens": cached,
                    "output_tokens": out,
                    "duration_ms": event.get("dur", 0),
                    "status": event.get("status", ""),
                    "cost": price_request(models.get(model_id), inp, out, cached),
                    "logged_cost": float(nano) / 1e9 if nano else None,
                })
    rows.sort(key=lambda r: r["time"])
    edges.sort(key=lambda e: e["time"])
    return rows, edges, attr_keys


def summarize(rows, key):
    totals = defaultdict(lambda: {"requests": 0, "input_tokens": 0, "output_tokens": 0,
                                  "cost": 0.0, "unpriced": 0})
    for r in rows:
        t = totals[r[key]]
        t["requests"] += 1
        t["input_tokens"] += r["input_tokens"]
        t["output_tokens"] += r["output_tokens"]
        if r["cost"] is None:
            t["unpriced"] += 1
        else:
            t["cost"] += r["cost"]
    return totals


def print_table(title, totals):
    print("\n%s" % title)
    print("%-30s %9s %14s %12s %14s" %
          ("name", "requests", "input", "output", "cost"))
    for name, t in sorted(totals.items(), key=lambda kv: -kv[1]["cost"]):
        print("%-30s %9d %14s %12s %14.4f" % (name, t["requests"], format(t["input_tokens"], ","),
                                              format(t["output_tokens"], ","), t["cost"]))


def usage_summary(rows, edges, _log_dir):
    priced_rows = [row for row in rows if row["cost"] is not None]
    total_cost = sum(row["cost"] for row in priced_rows)
    return {
        "capture_status": "measured" if rows else "unavailable",
        "capture_source": "copilot_chat_otel",
        "log_dir": "${USER_WORKSPACE_STORAGE}/GitHub.copilot-chat/debug-logs",
        "requests": len(rows),
        "agent_calls": len(edges),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "cached_tokens": sum(row["cached_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "duration_ms": sum(row["duration_ms"] for row in rows),
        "priced_requests": len(priced_rows),
        "unpriced_requests": len(rows) - len(priced_rows),
        "computed_cost": total_cost if priced_rows else None,
        "logged_cost": sum(row["logged_cost"] or 0 for row in rows) if rows else None,
        "in_pipeline_model_requests": 0,
        "in_pipeline_ai_cost": 0.0,
        "note": "The deterministic CPP synthetic pipeline uses validated JSON for the LLM hand-off and makes no in-process model request. Copilot Chat cost requires llm_request OTEL events.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    parser.add_argument("--out-dir", default=".",
                        help="folder for usage_requests.csv and agent_calls.csv")
    parser.add_argument("--latest", action="store_true",
                        help="only the most recently modified session")
    args = parser.parse_args()

    rows, edges, attr_keys = collect(args.log_dir, args.latest)
    os.makedirs(args.out_dir, exist_ok=True)
    write_csv(os.path.join(args.out_dir, "usage_requests.csv"),
              rows, REQUEST_FIELDS)
    write_csv(os.path.join(args.out_dir, "agent_calls.csv"), edges, CALL_FIELDS)
    summary = usage_summary(rows, edges, args.log_dir)
    with open(os.path.join(args.out_dir, "usage_summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    if not rows:
        print("No llm_request events found in %s" % args.log_dir)
        print("Set github.copilot.chat.otel.enabled to true (or env COPILOT_OTEL_ENABLED=true), "
              "reload VS Code, run the agent, then rerun this script.")
        print("Wrote empty usage CSVs and unavailable cost telemetry to %s" %
              os.path.abspath(args.out_dir))
        return

    print_table("By agent (main = top-level chat session)",
                summarize(rows, "agent"))
    print_table("By session", summarize(rows, "session"))
    print_table("By model", summarize(rows, "model"))

    total_cost = sum(r["cost"] or 0 for r in rows)
    print("\nTotal: %d requests, %s input, %s output, cost %.4f"
          % (len(rows), format(sum(r["input_tokens"] for r in rows), ","),
             format(sum(r["output_tokens"] for r in rows), ","), total_cost))
    print("Logged usage cost (copilotUsageNanoAiu): %.4f" %
          sum(r["logged_cost"] or 0 for r in rows))

    print("\nAgent calls (caller -> callee):")
    for e in edges:
        print("  %s  %s -> %s  (%d ms, %s)" %
              (e["time"], e["caller"], e["callee"], e["duration_ms"], e["status"]))

    print("\nllm_request attribute keys seen: %s" %
          ", ".join(sorted(attr_keys)))
    print("Cost uses token_prices from models.json; units are as stored there and not labeled in the file.")

    print("\nWrote %d requests to usage_requests.csv and %d agent calls to agent_calls.csv in %s"
          % (len(rows), len(edges), os.path.abspath(args.out_dir)))


if __name__ == "__main__":
    main()
