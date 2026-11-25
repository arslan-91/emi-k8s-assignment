import argparse
import asyncio
import csv
import datetime
import json
import os
import random
import subprocess
import time
import aiohttp
import psutil

URL = "http://emi.local/api/emi"

def random_payload():
    return {
        "principal": random.randint(50000, 2000000),
        "rate": round(random.uniform(6.0, 18.0), 2),
        "months": random.choice([12, 24, 36, 48, 60, 84, 120])
    }

async def send_one(session, latencies, errors):
    t0 = time.perf_counter()
    try:
        async with session.post(URL, json=random_payload(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
            await resp.text()
            dt_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(dt_ms)
            if resp.status >= 400:
                errors.append(resp.status)
    except Exception:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)
        errors.append("EXC")

async def worker_rate(rate_per_sec, duration_sec, latencies, errors):
    end_time = time.monotonic() + duration_sec
    tasks = set()
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        sec_idx = 0
        start_t = time.monotonic()
        while time.monotonic() < end_time:
            now = time.monotonic()
            target_sec_start = start_t + sec_idx
            if now >= target_sec_start and target_sec_start < end_time:
                batch = int(round(rate_per_sec))
                for i in range(batch):
                    if time.monotonic() >= end_time:
                        break
                    t = asyncio.create_task(send_one(session, latencies, errors))
                    tasks.add(t)
                    t.add_done_callback(tasks.discard)
                sec_idx += 1
            await asyncio.sleep(0.05)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

def parse_cpu_millicores(val):
    val = val.strip()
    if val.endswith("m"):
        return float(val[:-1])
    return float(val) * 1000.0

def parse_mem_mib(val):
    val = val.strip()
    for unit, mult in [("Ki", 1/1024), ("Mi", 1.0), ("Gi", 1024.0)]:
        if val.endswith(unit):
            return float(val[:-len(unit)]) * mult
    return float(val) / (1024.0 * 1024.0)

async def profile_loop(duration_sec, pod_rows, host_rows, hpa_rows, record_hpa=False):
    start = time.monotonic()
    last_15s = -15.0
    while True:
        elapsed = time.monotonic() - start
        if elapsed > duration_sec + 1.0:
            break
        ts = datetime.datetime.now().isoformat()

        host_cpu = psutil.cpu_percent(interval=1.0)
        host_rows.append({"timestamp": ts, "elapsed_s": round(time.monotonic() - start, 2), "host_cpu_pct": host_cpu})

        if (time.monotonic() - start) - last_15s >= 15.0 or elapsed < 1.5:
            last_15s = time.monotonic() - start
            try:
                out = subprocess.check_output(["kubectl", "top", "pods", "-n", "emi", "--no-headers"], text=True, stderr=subprocess.DEVNULL)
                for line in out.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        pod, cpu_s, mem_s = parts[0], parts[1], parts[2]
                        pod_rows.append({
                            "timestamp": ts,
                            "elapsed_s": round(last_15s, 2),
                            "pod": pod,
                            "cpu_millicores": parse_cpu_millicores(cpu_s),
                            "mem_mib": round(parse_mem_mib(mem_s), 2)
                        })
            except subprocess.CalledProcessError:
                pass

            if record_hpa:
                try:
                    h_out = subprocess.check_output(["kubectl", "get", "hpa", "emi-web", "-n", "emi", "-o", "json"], text=True, stderr=subprocess.DEVNULL)
                    h_data = json.loads(h_out)
                    replicas = h_data.get("status", {}).get("currentReplicas", 0)
                    avg_cpu = None
                    for m in h_data.get("status", {}).get("currentMetrics", []):
                        if m.get("type") == "Resource":
                            avg_cpu = m.get("resource", {}).get("current", {}).get("averageUtilization")
                    hpa_rows.append({
                        "timestamp": ts,
                        "elapsed_s": round(last_15s, 2),
                        "current_replicas": replicas,
                        "avg_cpu_utilization": avg_cpu
                    })
                except subprocess.CalledProcessError:
                    pass

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fixed", "hpa"], required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()

    os.makedirs("results", exist_ok=True)
    latencies, errors = [], []
    pod_rows, host_rows, hpa_rows = [], [], []

    if args.mode == "fixed":
        total_dur = args.duration
        await asyncio.gather(
            worker_rate(args.rate, total_dur, latencies, errors),
            profile_loop(total_dur, pod_rows, host_rows, hpa_rows, record_hpa=False)
        )
        avg_ms = sum(latencies) / len(latencies) if latencies else 0.0
        summary_file = os.path.join("results", "fixed_summary.csv")
        write_header = not os.path.exists(summary_file)
        with open(summary_file, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["tag", "rate_rps", "duration_s", "total_requests", "errors", "avg_latency_ms"])
            if write_header:
                w.writeheader()
            w.writerow({
                "tag": args.tag,
                "rate_rps": args.rate,
                "duration_s": args.duration,
                "total_requests": len(latencies),
                "errors": len(errors),
                "avg_latency_ms": round(avg_ms, 2)
            })
        print(f"[{args.tag}] rate={args.rate}/s | sent={len(latencies)} | errors={len(errors)} | avg={avg_ms:.2f} ms")
    else:
        async def hpa_schedule():
            stages = [(10, 120), (100, 300), (10, 180)]
            for r, d in stages:
                print(f"HPA stage: {r} req/s for {d}s...")
                await worker_rate(r, d, latencies, errors)

        await asyncio.gather(
            hpa_schedule(),
            profile_loop(600, pod_rows, host_rows, hpa_rows, record_hpa=True)
        )
        with open(os.path.join("results", f"{args.tag}_hpa.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp", "elapsed_s", "current_replicas", "avg_cpu_utilization"])
            w.writeheader()
            w.writerows(hpa_rows)
        print(f"[HPA {args.tag}] total sent={len(latencies)} | errors={len(errors)}")

    if pod_rows:
        with open(os.path.join("results", f"{args.tag}_pods.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp", "elapsed_s", "pod", "cpu_millicores", "mem_mib"])
            w.writeheader()
            w.writerows(pod_rows)
    if host_rows:
        with open(os.path.join("results", f"{args.tag}_host.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp", "elapsed_s", "host_cpu_pct"])
            w.writeheader()
            w.writerows(host_rows)

if __name__ == "__main__":
    asyncio.run(main())
