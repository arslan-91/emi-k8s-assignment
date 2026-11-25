#!/usr/bin/env python3
"""
Profiling helpers: saves timestamped CSV files while a test runs.

  host_cpu.csv     every 1 s   : timestamp, epoch, host_cpu_percent            (psutil)
  pod_metrics.csv  every 15 s  : timestamp, epoch, pod, cpu_millicores, mem_mi (kubectl top pods)
  hpa.csv          every 15 s  : timestamp, epoch, current_replicas, desired_replicas, cpu_util_percent
  hpa_raw.txt      every 15 s  : raw output of `kubectl get hpa emi-web -n emi`

Can be used standalone:  python scripts/monitor.py --out results/manual --duration 60
"""
import argparse
import csv
import json
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil

NS = "emi"


def kubectl(*args, timeout=30):
    """Run kubectl, return (returncode, stdout)."""
    try:
        p = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except Exception as e:           # kubectl missing / timeout
        return 1, str(e)


def iso(ts):
    return datetime.fromtimestamp(ts).isoformat(timespec="milliseconds")


def parse_cpu_m(s):
    if s.endswith("m"):
        return float(s[:-1])
    if s.endswith("n"):
        return float(s[:-1]) / 1e6
    return float(s) * 1000.0


def parse_mem_mi(s):
    for suf, div in (("Ki", 1024.0), ("Mi", 1.0), ("Gi", 1 / 1024.0)):
        if s.endswith(suf):
            return float(s[:-2]) / div
    return float(s) / (1024 * 1024)


def parse_top(text):
    """'emi-web-abc 45m 62Mi' lines -> [(pod, cpu_m, mem_mi), ...]"""
    rows = []
    for line in text.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                rows.append((parts[0], parse_cpu_m(parts[1]), parse_mem_mi(parts[2])))
            except ValueError:
                pass
    return rows


def parse_hpa(text):
    """kubectl get hpa -o json -> (current_replicas, desired_replicas, cpu_util_percent or '')"""
    try:
        st = json.loads(text)["status"]
    except Exception:
        return "", "", ""
    util = ""
    for m in st.get("currentMetrics", []) or []:
        if m.get("type") == "Resource" and m["resource"]["name"] == "cpu":
            util = m["resource"]["current"].get("averageUtilization", "")
    return st.get("currentReplicas", ""), st.get("desiredReplicas", ""), util


def web_restarts():
    """Total container restarts of the emi-web pods (to detect crashes during a run)."""
    rc, out = kubectl("get", "pods", "-n", NS, "-l", "app=emi-web", "-o", "json")
    try:
        items = json.loads(out)["items"]
        return sum(c["restartCount"] for p in items for c in p["status"].get("containerStatuses", []))
    except Exception:
        return None


def preflight(url="http://emi.local/health"):
    """Fail early if the tunnel / metrics-server are not working."""
    try:
        urllib.request.urlopen(url, timeout=5).read()
    except Exception as e:
        raise SystemExit(f"\n[!] Cannot reach {url}: {e}\n    Is 'minikube tunnel' running (Administrator PowerShell) "
                         f"and is emi.local in the hosts file?")
    rc, out = kubectl("top", "pods", "-n", NS, "--no-headers")
    if rc != 0 or not parse_top(out):
        raise SystemExit("\n[!] 'kubectl top pods -n emi' gives no data. Run: minikube addons enable metrics-server "
                         "and wait 1-2 minutes.")
    print("[ok] ingress reachable, kubectl top works")


class Monitor:
    def __init__(self, out_dir, hpa=False, top_interval=15, host_interval=1):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hpa, self.top_i, self.host_i = hpa, top_interval, host_interval
        self.stop_ev = threading.Event()
        self.threads = []

    def _host(self):
        with open(self.dir / "host_cpu.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "epoch", "host_cpu_percent"])
            psutil.cpu_percent(None)
            while not self.stop_ev.is_set():
                cpu = psutil.cpu_percent(interval=self.host_i)   # blocks ~1 s
                t = time.time()
                w.writerow([iso(t), round(t, 3), cpu])
                f.flush()

    def _every(self, interval, fn):
        nxt = time.time()
        while not self.stop_ev.is_set():
            fn()
            nxt += interval
            self.stop_ev.wait(max(0, nxt - time.time()))

    def _top(self, w, f):
        def fn():
            t = time.time()
            rc, out = kubectl("top", "pods", "-n", NS, "--no-headers")
            if rc == 0:
                for pod, cpu, mem in parse_top(out):
                    w.writerow([iso(t), round(t, 3), pod, round(cpu, 1), round(mem, 1)])
                f.flush()
        return fn

    def _hpa(self, w, f, raw):
        def fn():
            t = time.time()
            _, txt = kubectl("get", "hpa", "emi-web", "-n", NS, "--no-headers")
            raw.write(f"{iso(t)}  {txt.strip()}\n"); raw.flush()
            _, js = kubectl("get", "hpa", "emi-web", "-n", NS, "-o", "json")
            cur, des, util = parse_hpa(js)
            w.writerow([iso(t), round(t, 3), cur, des, util]); f.flush()
        return fn

    def _pods_thread(self):
        with open(self.dir / "pod_metrics.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "epoch", "pod", "cpu_millicores", "mem_mi"])
            self._every(self.top_i, self._top(w, f))

    def _hpa_thread(self):
        with open(self.dir / "hpa.csv", "w", newline="") as f, open(self.dir / "hpa_raw.txt", "w") as raw:
            w = csv.writer(f)
            w.writerow(["timestamp", "epoch", "current_replicas", "desired_replicas", "cpu_util_percent"])
            self._every(self.top_i, self._hpa(w, f, raw))

    def start(self):
        targets = [self._host, self._pods_thread] + ([self._hpa_thread] if self.hpa else [])
        for tgt in targets:
            th = threading.Thread(target=tgt, daemon=True)
            th.start()
            self.threads.append(th)
        return self

    def stop(self):
        self.stop_ev.set()
        for th in self.threads:
            th.join(timeout=40)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/manual")
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--hpa", action="store_true")
    a = ap.parse_args()
    m = Monitor(a.out, hpa=a.hpa).start()
    try:
        time.sleep(a.duration)
    except KeyboardInterrupt:
        pass
    m.stop()
    print("saved to", a.out)
