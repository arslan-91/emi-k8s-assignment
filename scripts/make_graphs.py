import csv
import os
import matplotlib.pyplot as plt

os.makedirs("results/graphs", exist_ok=True)

# 1. Graph 1: Avg response time (ms) vs request rate for 1, 2, 3 replicas
rows = []
if os.path.exists("results/fixed_summary.csv"):
    with open("results/fixed_summary.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "tag": r["tag"],
                "rate": float(r["rate_rps"]),
                "avg_ms": float(r["avg_latency_ms"]),
            })

plt.figure(figsize=(8, 5))
for rep in [1, 2, 3]:
    pts = sorted([x for x in rows if x["tag"].startswith(f"rep{rep}_")], key=lambda x: x["rate"])
    if pts:
        plt.plot([p["rate"] for p in pts], [p["avg_ms"] for p in pts], marker="o", label=f"{rep} Replica(s)")

plt.title("Average Response Time vs. Request Rate")
plt.xlabel("Request Rate (req/s)")
plt.ylabel("Average Response Time (ms)")
plt.grid(True, linestyle="--", alpha=0.5)
plt.legend()
plt.tight_layout()
plt.savefig("results/graphs/graph1_latency_vs_rate.png", dpi=200)
plt.close()

# 2. Graph 2: CPU usage over time per pod during 100 req/s with 3 replicas
pod_file = "results/rep3_r100_pods.csv"
if os.path.exists(pod_file):
    by_pod = {}
    with open(pod_file, newline="") as f:
        for r in csv.DictReader(f):
            pod = r["pod"]
            if not pod.startswith("emi-web-"):
                continue
            by_pod.setdefault(pod, []).append((float(r["elapsed_s"]), float(r["cpu_millicores"])))

    plt.figure(figsize=(8, 5))
    for pod, series in sorted(by_pod.items()):
        series.sort(key=lambda x: x[0])
        plt.plot([t for t, _ in series], [c for _, c in series], marker="o", label=pod)

    plt.title("Pod CPU Usage Over Time (100 req/s, 3 Replicas)")
    plt.xlabel("Elapsed Time (s)")
    plt.ylabel("CPU Usage (m / % of 100m request)")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig("results/graphs/graph2_pod_cpu_100rps_rep3.png", dpi=200)
    plt.close()

# 3. Graph 3: HPA timeline (request rate, avg CPU %, replicas)
hpa_file = "results/hpa_10m_hpa.csv"
if os.path.exists(hpa_file):
    times, reps, cpus, rates = [], [], [], []
    with open(hpa_file, newline="") as f:
        for r in csv.DictReader(f):
            t = float(r["elapsed_s"])
            times.append(t)
            reps.append(int(r["current_replicas"] or 0))
            cpus.append(float(r["avg_cpu_utilization"]) if r["avg_cpu_utilization"] not in (None, "", "None") else 0.0)
            rates.append(100.0 if 120.0 <= t < 420.0 else 10.0)

    if times:
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True, figsize=(9, 7))
        ax1.step(times, rates, where="post")
        ax1.set_ylabel("Target Rate (req/s)")
        ax1.set_title("HPA Autoscaling Profile")
        ax1.grid(True, linestyle="--", alpha=0.5)

        ax2.plot(times, cpus, marker="o")
        ax2.axhline(50, linestyle="--", label="Target 50%")
        ax2.set_ylabel("Avg CPU (%)")
        ax2.legend(loc="upper right")
        ax2.grid(True, linestyle="--", alpha=0.5)

        ax3.step(times, reps, where="post")
        ax3.set_ylabel("Web Replicas")
        ax3.set_xlabel("Elapsed Time (s)")
        ax3.set_yticks([1, 2, 3, 4, 5])
        ax3.grid(True, linestyle="--", alpha=0.5)

        plt.tight_layout()
        plt.savefig("results/graphs/graph3_hpa_10min.png", dpi=200)
        plt.close()

print("Graphs saved in results/graphs/")
