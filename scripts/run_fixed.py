#!/usr/bin/env python3
"""
Milestone 4, step 2+3: 15 runs = replicas {1,2,3} x rates {10,25,50,100,200} req/s, 60 s each.
For every run it saves requests, pod CPU/memory (every 15 s) and host CPU (every 1 s).

  python scripts/run_fixed.py                 # all 15 runs (~25 min)
  python scripts/run_fixed.py --replicas 3    # only one replica count
Finished runs are skipped automatically, so you can re-run after an interruption.
"""
import argparse
import csv
import json
import time
from pathlib import Path

from loadgen import run_load
from monitor import Monitor, kubectl, preflight, web_restarts

URL = "http://emi.local/api/emi"
SUMMARY = Path("results/fixed_summary.csv")
FIELDS = ["replicas", "rate", "duration_s", "planned", "sent", "ok", "errors",
          "avg_ms", "p95_ms", "achieved_rps", "pod_restarts_during_run"]


def set_replicas(n):
    print(f"\n=== scaling emi-web to {n} replica(s)")
    kubectl("scale", "deployment", "emi-web", f"--replicas={n}", "-n", "emi")
    rc, out = kubectl("rollout", "status", "deployment/emi-web", "-n", "emi", "--timeout=240s", timeout=260)
    print(out.strip().splitlines()[-1] if out.strip() else "(no output)")
    time.sleep(15)       # let ingress endpoints settle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicas", default="1,2,3")
    ap.add_argument("--rates", default="10,25,50,100,200")
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--cooldown", type=int, default=20)
    a = ap.parse_args()

    preflight()
    kubectl("delete", "hpa", "emi-web", "-n", "emi", "--ignore-not-found")   # fixed replicas: no HPA
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    new = not SUMMARY.exists()
    with open(SUMMARY, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for n in [int(x) for x in a.replicas.split(",")]:
            set_replicas(n)
            for rate in [int(x) for x in a.rates.split(",")]:
                d = Path(f"results/fixed/replicas{n}_rate{rate}")
                if (d / "run_summary.json").exists():
                    print(f"[skip] replicas={n} rate={rate} already done")
                    continue
                print(f"\n--- replicas={n}  rate={rate}/s  for {a.duration}s")
                r0 = web_restarts()
                mon = Monitor(d).start()
                s = run_load(URL, [(rate, a.duration)], str(d / "run"))
                mon.stop()
                r1 = web_restarts()
                restarts = (r1 - r0) if (r0 is not None and r1 is not None) else ""
                row = {"replicas": n, "rate": rate, "duration_s": a.duration, "planned": s["planned"],
                       "sent": s["sent"], "ok": s["ok"], "errors": s["errors"], "avg_ms": s["avg_ms"],
                       "p95_ms": s["p95_ms"], "achieved_rps": s["achieved_rps"],
                       "pod_restarts_during_run": restarts}
                w.writerow(row); f.flush()
                (d / "run_summary.json").write_text(json.dumps(row, indent=2))
                print(f"    sent={s['sent']} ok={s['ok']} errors={s['errors']} avg={s['avg_ms']} ms "
                      f"p95={s['p95_ms']} ms restarts={restarts}")
                time.sleep(a.cooldown)
    print("\nDone. Summary:", SUMMARY)


if __name__ == "__main__":
    main()
