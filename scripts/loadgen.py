#!/usr/bin/env python3
"""
Open-loop HTTP load generator (httperf-style: fixed request RATE, not fixed concurrency).

Every request is POST /api/emi with random valid inputs, so every request also writes to MongoDB.
Phases let one run have several rates, e.g. --phases 10:120,100:300,10:180
(rate:seconds, comma separated). A normal single run is just one phase: --rate 50 --duration 60

Outputs (prefix = --out, e.g. results/test/run):
  <prefix>_requests.csv   sent_epoch, latency_ms, status, pod   (one row per request)
  <prefix>_summary.json   sent, ok, errors, avg_ms, p95_ms, achieved_rps ...
"""
import argparse
import asyncio
import csv
import json
import random
import statistics
import time
from pathlib import Path

import aiohttp


def parse_phases(s):
    phases = []
    for part in s.split(","):
        rate, dur = part.split(":")
        phases.append((float(rate), int(dur)))
    return phases


def random_payload():
    return {
        "principal": random.randint(50_000, 5_000_000),
        "rate": round(random.uniform(5, 25), 2),
        "months": random.randint(6, 120),
    }


async def _one(session, url, records):
    sent = time.time()
    t0 = time.perf_counter()
    status, pod = -1, ""          # -1 = connection error / timeout
    try:
        async with session.post(url, json=random_payload()) as resp:
            status = resp.status
            data = await resp.json(content_type=None)
            if isinstance(data, dict):
                pod = data.get("servedBy", "")
    except Exception:
        status = -1
    records.append((sent, (time.perf_counter() - t0) * 1000.0, status, pod))


async def _run(url, phases, timeout):
    records, tasks = [], set()
    conn = aiohttp.TCPConnector(limit=500, ttl_dns_cache=300)
    tmo = aiohttp.ClientTimeout(total=timeout)
    start_epoch = time.time()
    async with aiohttp.ClientSession(connector=conn, timeout=tmo) as session:
        t_start = time.perf_counter()
        offset = 0.0
        for rate, dur in phases:
            interval = 1.0 / rate
            for i in range(int(rate * dur)):
                delay = (t_start + offset + i * interval) - time.perf_counter()
                await asyncio.sleep(max(delay, 0))     # if behind schedule, fire immediately
                t = asyncio.create_task(_one(session, url, records))
                tasks.add(t)
                t.add_done_callback(tasks.discard)
            offset += dur
        if tasks:
            await asyncio.gather(*list(tasks), return_exceptions=True)
    return records, start_epoch, time.time()


def run_load(url, phases, out_prefix, timeout=10):
    """Run the load, write CSV + JSON, return the summary dict."""
    records, start_epoch, end_epoch = asyncio.run(_run(url, phases, timeout))
    records.sort()
    Path(out_prefix).parent.mkdir(parents=True, exist_ok=True)
    with open(f"{out_prefix}_requests.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sent_epoch", "latency_ms", "status", "pod"])
        w.writerows(records)

    ok_lat = [r[1] for r in records if 200 <= r[2] < 300]
    total_s = sum(d for _, d in phases)
    summary = {
        "url": url,
        "phases": phases,
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "planned": int(sum(r * d for r, d in phases)),
        "sent": len(records),
        "ok": len(ok_lat),
        "errors": len(records) - len(ok_lat),
        "avg_ms": round(statistics.mean(ok_lat), 2) if ok_lat else None,
        "p95_ms": round(statistics.quantiles(ok_lat, n=20)[18], 2) if len(ok_lat) >= 20 else None,
        "achieved_rps": round(len(records) / total_s, 2),
    }
    with open(f"{out_prefix}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://emi.local/api/emi")
    ap.add_argument("--rate", type=float, help="requests per second (single phase)")
    ap.add_argument("--duration", type=int, default=60, help="seconds (single phase)")
    ap.add_argument("--phases", help="rate:seconds,rate:seconds,... (overrides --rate/--duration)")
    ap.add_argument("--out", default="results/loadgen/run", help="output prefix")
    ap.add_argument("--timeout", type=int, default=10)
    a = ap.parse_args()
    ph = parse_phases(a.phases) if a.phases else [(a.rate, a.duration)]
    print(json.dumps(run_load(a.url, ph, a.out, a.timeout), indent=2))
