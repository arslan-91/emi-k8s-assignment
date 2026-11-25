#!/usr/bin/env python3
"""
Milestone 4, step 4: autoscaling test (10 minutes).
  2 min @ 10 req/s  ->  5 min @ 100 req/s  ->  3 min @ 10 req/s
Starts from 1 replica with the HPA applied; logs `kubectl get hpa` every 15 s.

  python scripts/run_hpa.py
"""
import json
import time
from pathlib import Path

from loadgen import run_load
from monitor import Monitor, kubectl, preflight

URL = "http://emi.local/api/emi"
OUT = Path("results/autoscale")
PHASES = [(10, 120), (100, 300), (10, 180)]


def main():
    preflight()
    print("=== resetting: delete old HPA, scale to 1 replica")
    kubectl("delete", "hpa", "emi-web", "-n", "emi", "--ignore-not-found")
    kubectl("scale", "deployment", "emi-web", "--replicas=1", "-n", "emi")
    kubectl("rollout", "status", "deployment/emi-web", "-n", "emi", "--timeout=240s", timeout=260)
    print("=== cooling down 45 s so CPU readings start from idle")
    time.sleep(45)

    print("=== applying k8s/40-hpa.yaml")
    rc, out = kubectl("apply", "-f", "k8s/40-hpa.yaml")
    print(out.strip())
    time.sleep(20)       # HPA needs a first metrics sample

    OUT.mkdir(parents=True, exist_ok=True)
    mon = Monitor(OUT, hpa=True).start()
    print("=== load test started (10 minutes). Do not touch the PC / close the tunnel window.")
    s = run_load(URL, PHASES, str(OUT / "run"))
    time.sleep(15)       # capture one last HPA sample
    mon.stop()
    (OUT / "run_summary.json").write_text(json.dumps(s, indent=2))
    print(json.dumps(s, indent=2))
    _, out = kubectl("describe", "hpa", "emi-web", "-n", "emi")
    (OUT / "hpa_describe.txt").write_text(out)       # contains the scaling events (SuccessfulRescale)
    print("Done. Files in", OUT)


if __name__ == "__main__":
    main()
