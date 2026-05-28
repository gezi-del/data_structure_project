"""
Run all 9 experiments (3 scales x 3 strategies) and generate matplotlib charts
for the report section 6 (Results & Analysis).
"""
import sys, os, io, json, time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from collections import defaultdict

# Suppress experiment print output
_stdout = sys.stdout
sys.stdout = io.StringIO()

from experiment_runner import run_all_experiments

print("Running experiments (this may take 5-10 minutes)...", file=_stdout)
t0 = time.time()
data = run_all_experiments(force=True)
elapsed = time.time() - t0
sys.stdout = _stdout
print(f"Experiments completed in {elapsed:.1f}s\n")

# ── Parse results ──────────────────────────────────────────────────────────
results = data['results']
summary = data['summary']

scales = ['small', 'medium', 'large']
scale_labels = ['Small (25 nodes)', 'Medium (40 nodes)', 'Large (70 nodes)']
strategy_keys = ['nearest', 'max_weight', 'genetic']
strategy_labels = ['Nearest-First', 'Max-Weight', 'Genetic Algorithm']
strategy_colors = ['#58897A', '#356CB0', '#D09E2C']
strategy_hatches = ['/', '\\', '..']

# Build data structures
metrics = ['total_score', 'completed_tasks', 'timeout_tasks',
           'avg_finish_time', 'total_distance', 'charge_sessions',
           'total_charge_wait_time']
metric_labels = [
    'Total Score', 'Completed Tasks', 'Timeout Tasks',
    'Avg Finish Time (s)', 'Total Distance', 'Charge Sessions',
    'Charge Wait Time (s)'
]

data_by_scale = {}
for r in results:
    s = r['scale']
    data_by_scale[s] = {'task_count': r['task_count'], 'strategies': {}}
    for st in r['strategies']:
        data_by_scale[s]['strategies'][st['strategy']] = st

# ── Print results table ────────────────────────────────────────────────────
print("=" * 120)
print(f"{'Scale':<10} {'Strategy':<18} {'Score':>10} {'Completed':>10} {'Timeout':>9} {'AvgTime':>9} {'Distance':>10} {'Charges':>9} {'WaitTime':>9}")
print("-" * 120)
for s in scales:
    for sk in strategy_keys:
        st = data_by_scale[s]['strategies'][sk]
        print(f"{s:<10} {strategy_labels[strategy_keys.index(sk)]:<18} "
              f"{st.get('total_score',0):>10.1f} {st.get('completed_tasks',0):>10} "
              f"{st.get('timeout_tasks',0):>9} {st.get('avg_finish_time',0):>9.1f} "
              f"{st.get('total_distance',0):>10.1f} {st.get('charge_sessions',0):>9} "
              f"{st.get('total_charge_wait_time',0):>9.1f}")
    print("-" * 120)

print("\n=== BEST STRATEGY PER SCALE ===")
for sm in summary:
    print(f"  {sm['scale_label']}: {sm['best_strategy']} (score={sm['best_score']:.1f})")

# ═════════════════════════════════════════════════════════════════════════════
# MATPLOTLIB CHARTS
# ═════════════════════════════════════════════════════════════════════════════
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Segoe UI', 'DejaVu Sans', 'Arial'],
    'font.size': 11,
    'axes.titlesize': 14,
    'axes.labelsize': 12,
    'figure.dpi': 150,
    'savefig.dpi': 150,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1,
})

# ── Figure 1: Total Score comparison (grouped bar) ─────────────────────────
fig, ax = plt.subplots(figsize=(10, 5.5))
x = np.arange(len(scales))
width = 0.25

for i, sk in enumerate(strategy_keys):
    scores = [data_by_scale[s]['strategies'][sk].get('total_score', 0) for s in scales]
    bars = ax.bar(x + i * width, scores, width, label=strategy_labels[i],
                  color=strategy_colors[i], edgecolor='white', linewidth=0.8)
    for bar, val in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(scores)*0.01,
                f'{val:.0f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

ax.set_xlabel('Scale')
ax.set_ylabel('Total Score')
ax.set_title('Total Score Comparison Across Scales & Strategies')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels)
ax.legend(frameon=True, fancybox=True, shadow=True)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))
fig.tight_layout()
fig.savefig('chart_01_total_score.png')
print("\nSaved: chart_01_total_score.png")

# ── Figure 2: Completed vs Timeout Tasks (grouped bar) ─────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Completed
ax = axes[0]
for i, sk in enumerate(strategy_keys):
    vals = [data_by_scale[s]['strategies'][sk].get('completed_tasks', 0) for s in scales]
    ax.bar(x + i * width, vals, width, label=strategy_labels[i],
           color=strategy_colors[i], edgecolor='white', linewidth=0.8)
ax.set_title('Completed Tasks')
ax.set_xlabel('Scale')
ax.set_ylabel('Count')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels, fontsize=9)
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3, linestyle='--')

# Timeout
ax = axes[1]
for i, sk in enumerate(strategy_keys):
    vals = [data_by_scale[s]['strategies'][sk].get('timeout_tasks', 0) for s in scales]
    ax.bar(x + i * width, vals, width, label=strategy_labels[i],
           color=strategy_colors[i], edgecolor='white', linewidth=0.8)
ax.set_title('Timeout Tasks')
ax.set_xlabel('Scale')
ax.set_ylabel('Count')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels, fontsize=9)
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3, linestyle='--')

fig.suptitle('Task Completion & Timeout Comparison', fontsize=14, fontweight='bold')
fig.tight_layout()
fig.savefig('chart_02_completed_timeout.png')
print("Saved: chart_02_completed_timeout.png")

# ── Figure 3: Avg Finish Time & Total Distance (grouped bar) ───────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Avg finish time
ax = axes[0]
for i, sk in enumerate(strategy_keys):
    vals = [data_by_scale[s]['strategies'][sk].get('avg_finish_time', 0) for s in scales]
    ax.bar(x + i * width, vals, width, label=strategy_labels[i],
           color=strategy_colors[i], edgecolor='white', linewidth=0.8)
ax.set_title('Average Finish Time (seconds)')
ax.set_xlabel('Scale')
ax.set_ylabel('Seconds')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels, fontsize=9)
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3, linestyle='--')

# Total distance
ax = axes[1]
for i, sk in enumerate(strategy_keys):
    vals = [data_by_scale[s]['strategies'][sk].get('total_distance', 0) for s in scales]
    ax.bar(x + i * width, vals, width, label=strategy_labels[i],
           color=strategy_colors[i], edgecolor='white', linewidth=0.8)
ax.set_title('Total Distance Traveled')
ax.set_xlabel('Scale')
ax.set_ylabel('Distance')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels, fontsize=9)
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))

fig.suptitle('Time Efficiency & Travel Distance', fontsize=14, fontweight='bold')
fig.tight_layout()
fig.savefig('chart_03_time_distance.png')
print("Saved: chart_03_time_distance.png")

# ── Figure 4: Charge Sessions & Wait Time ──────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

ax = axes[0]
for i, sk in enumerate(strategy_keys):
    vals = [data_by_scale[s]['strategies'][sk].get('charge_sessions', 0) for s in scales]
    ax.bar(x + i * width, vals, width, label=strategy_labels[i],
           color=strategy_colors[i], edgecolor='white', linewidth=0.8)
ax.set_title('Charge Sessions')
ax.set_xlabel('Scale')
ax.set_ylabel('Count')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels, fontsize=9)
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3, linestyle='--')

ax = axes[1]
for i, sk in enumerate(strategy_keys):
    vals = [data_by_scale[s]['strategies'][sk].get('total_charge_wait_time', 0) for s in scales]
    ax.bar(x + i * width, vals, width, label=strategy_labels[i],
           color=strategy_colors[i], edgecolor='white', linewidth=0.8)
ax.set_title('Total Charge Wait Time (seconds)')
ax.set_xlabel('Scale')
ax.set_ylabel('Seconds')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels, fontsize=9)
ax.legend(fontsize=8)
ax.grid(axis='y', alpha=0.3, linestyle='--')

fig.suptitle('Charging Behavior Comparison', fontsize=14, fontweight='bold')
fig.tight_layout()
fig.savefig('chart_04_charging.png')
print("Saved: chart_04_charging.png")

# ── Figure 5: Strategy Score Trend (line chart) ────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
for i, sk in enumerate(strategy_keys):
    scores = [data_by_scale[s]['strategies'][sk].get('total_score', 0) for s in scales]
    ax.plot(scale_labels, scores, 'o-', color=strategy_colors[i],
            label=strategy_labels[i], linewidth=2.5, markersize=10,
            markerfacecolor='white', markeredgewidth=2)
ax.set_xlabel('Scale')
ax.set_ylabel('Total Score')
ax.set_title('Strategy Performance Trends Across Scales')
ax.legend(frameon=True, fancybox=True, shadow=True, fontsize=11)
ax.grid(True, alpha=0.3, linestyle='--')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))
fig.tight_layout()
fig.savefig('chart_05_trend.png')
print("Saved: chart_05_trend.png")

# ── Figure 6: Genetic Algorithm Convergence ────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
for r in results:
    s = r['scale']
    st = r['strategies'][2]  # genetic is index 2
    if 'history' in st and st['history']:
        hist = st['history']
        ax.plot(range(1, len(hist)+1), hist, linewidth=2,
                label=f"{scale_labels[scales.index(s)]} (best={max(hist):.0f})")
ax.set_xlabel('Generation')
ax.set_ylabel('Fitness')
ax.set_title('Genetic Algorithm Convergence by Scale')
ax.legend(frameon=True, fancybox=True, shadow=True, fontsize=10)
ax.grid(True, alpha=0.3, linestyle='--')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))
fig.tight_layout()
fig.savefig('chart_06_ga_convergence.png')
print("Saved: chart_06_ga_convergence.png")

# ── Figure 7: Radar / Summary dashboard ────────────────────────────────────
# Normalized radar chart comparing strategies on the large scale
fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))

# Metrics for radar (normalize 0-1 across all strategies for the scale)
radar_metrics = ['total_score', 'completed_tasks', 'avg_finish_time',
                 'total_distance', 'charge_sessions', 'total_charge_wait_time']
radar_labels = ['Score', 'Completed', 'Avg Time', 'Distance', 'Charges', 'Wait Time']
# For avg_finish_time, total_distance, charge_sessions, total_charge_wait_time: lower is better
# Invert them so higher = better on the radar
invert_metrics = {'avg_finish_time', 'total_distance', 'charge_sessions', 'total_charge_wait_time'}

target_scale = 'large'
all_vals = {m: [] for m in radar_metrics}
for sk in strategy_keys:
    for m in radar_metrics:
        all_vals[m].append(data_by_scale[target_scale]['strategies'][sk].get(m, 0))

# Normalize
norm_vals = {}
for m in radar_metrics:
    vals = all_vals[m]
    mn, mx = min(vals), max(vals)
    if mx == mn:
        norm_vals[m] = [0.5] * len(vals)
    elif m in invert_metrics:
        norm_vals[m] = [(mx - v) / (mx - mn) for v in vals]
    else:
        norm_vals[m] = [(v - mn) / (mx - mn) for v in vals]

N = len(radar_metrics)
angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
angles += angles[:1]

for i, sk in enumerate(strategy_keys):
    values = [norm_vals[m][i] for m in radar_metrics]
    values += values[:1]
    ax.fill(angles, values, alpha=0.15, color=strategy_colors[i])
    ax.plot(angles, values, 'o-', linewidth=2, label=strategy_labels[i],
            color=strategy_colors[i], markersize=6)

ax.set_xticks(angles[:-1])
ax.set_xticklabels(radar_labels, fontsize=11)
ax.set_title(f'Strategy Comparison Radar — {scale_labels[2]}', fontsize=14,
             fontweight='bold', pad=20)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10)
fig.tight_layout()
fig.savefig('chart_07_radar.png')
print("Saved: chart_07_radar.png")

# ── Figure 8: Task Completion Rate ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
for i, sk in enumerate(strategy_keys):
    rates = []
    for s in scales:
        d = data_by_scale[s]
        completed = d['strategies'][sk].get('completed_tasks', 0)
        total = d['task_count']
        rates.append(completed / total * 100 if total > 0 else 0)
    ax.bar(x + i * width, rates, width, label=strategy_labels[i],
           color=strategy_colors[i], edgecolor='white', linewidth=0.8)
    for j, (bar, val) in enumerate(zip(x + i * width, rates)):
        ax.text(bar, val + 0.5, f'{val:.0f}%', ha='center', va='bottom',
                fontsize=9, fontweight='bold')

ax.set_xlabel('Scale')
ax.set_ylabel('Completion Rate (%)')
ax.set_title('Task Completion Rate by Strategy & Scale')
ax.set_xticks(x + width)
ax.set_xticklabels(scale_labels)
ax.set_ylim(0, 110)
ax.legend(frameon=True, fancybox=True, shadow=True)
ax.grid(axis='y', alpha=0.3, linestyle='--')
fig.tight_layout()
fig.savefig('chart_08_completion_rate.png')
print("Saved: chart_08_completion_rate.png")

# ── Figure 9: Multi-Vehicle Coordination — Nearest-First completion ──────
fig, ax = plt.subplots(figsize=(9, 5))
nf_data = [data_by_scale[s]['strategies']['nearest'] for s in scales]
x = np.arange(len(scales))
width = 0.25

completed_vals = [d.get('completed_tasks', 0) for d in nf_data]
timeout_vals = [d.get('timeout_tasks', 0) for d in nf_data]
task_counts = [data_by_scale[s]['task_count'] for s in scales]
rates = [c / t * 100 if t > 0 else 0 for c, t in zip(completed_vals, task_counts)]

bars1 = ax.bar(x - width, completed_vals, width, label='Completed', color='#58897A', edgecolor='white')
bars2 = ax.bar(x, timeout_vals, width, label='Timeout', color='#C47E35', edgecolor='white')
bars3 = ax.bar(x + width, [r for r in rates], width, label='Completion Rate (%)', color='#356CB0', edgecolor='white')

for bar, val in zip(bars1, completed_vals):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, str(val), ha='center', fontsize=10, fontweight='bold')
for bar, val in zip(bars2, timeout_vals):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, str(val), ha='center', fontsize=10, fontweight='bold')
for bar, val in zip(bars3, rates):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, f'{val:.0f}%', ha='center', fontsize=9, fontweight='bold')

ax.set_xlabel('Scale')
ax.set_ylabel('Count / Percentage')
ax.set_title('Nearest-First Multi-Vehicle Coordination: Task Completion by Scale')
ax.set_xticks(x)
ax.set_xticklabels(scale_labels)
ax.legend(frameon=True, fancybox=True, shadow=True, fontsize=10)
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.set_ylim(0, max(max(completed_vals), max(timeout_vals), max(rates)) * 1.2)
fig.tight_layout()
fig.savefig('chart_09_multi_vehicle_completion.png')
print("Saved: chart_09_multi_vehicle_completion.png")

# ── Figure 10: Multi-Vehicle Coordination cost (distance & charge wait) ──
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

ax = axes[0]
dist_vals = [d.get('total_distance', 0) for d in nf_data]
bars = ax.bar(scale_labels, dist_vals, color=['#58897A', '#356CB0', '#C47E35'], edgecolor='white', linewidth=0.8)
for bar, val in zip(bars, dist_vals):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(dist_vals)*0.02,
            f'{val:,.0f}', ha='center', fontsize=10, fontweight='bold')
ax.set_title('Total Distance (Nearest-First)')
ax.set_ylabel('Distance')
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))

ax = axes[1]
wait_vals = [d.get('total_charge_wait_time', 0) for d in nf_data]
charge_vals = [d.get('charge_sessions', 0) for d in nf_data]
bars = ax.bar(scale_labels, wait_vals, color=['#58897A', '#356CB0', '#C47E35'], edgecolor='white', linewidth=0.8)
for bar, val, chg in zip(bars, wait_vals, charge_vals):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(wait_vals)*0.02,
            f'{val:,.0f}s\n({chg} chg)', ha='center', fontsize=9, fontweight='bold')
ax.set_title('Charge Wait Time (Nearest-First)')
ax.set_ylabel('Seconds')
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))

fig.suptitle('Multi-Vehicle Coordination Cost: Distance & Charging', fontsize=14, fontweight='bold')
fig.tight_layout()
fig.savefig('chart_10_multi_vehicle_cost.png')
print("Saved: chart_10_multi_vehicle_cost.png")

print("\n=== All charts generated ===")
print("Generated 10 chart files:")
print("  chart_01_total_score.png")
print("  chart_02_completed_timeout.png")
print("  chart_03_time_distance.png")
print("  chart_04_charging.png")
print("  chart_05_trend.png")
print("  chart_06_ga_convergence.png")
print("  chart_07_radar.png")
print("  chart_08_completion_rate.png")
print("  chart_09_multi_vehicle_completion.png")
print("  chart_10_multi_vehicle_cost.png")

# ── Print detailed analysis ────────────────────────────────────────────────
print("\n" + "=" * 80)
print("RESULTS ANALYSIS")
print("=" * 80)

for s_idx, s in enumerate(scales):
    print(f"\n--- {scale_labels[s_idx]} ({data_by_scale[s]['task_count']} tasks) ---")
    best_score = -999999
    best_strategy = ''
    for sk in strategy_keys:
        st = data_by_scale[s]['strategies'][sk]
        sc = st.get('total_score', 0)
        comp = st.get('completed_tasks', 0)
        tout = st.get('timeout_tasks', 0)
        dist = st.get('total_distance', 0)
        avg_t = st.get('avg_finish_time', 0)
        strategy_name = strategy_labels[strategy_keys.index(sk)]
        comp_rate = comp / data_by_scale[s]['task_count'] * 100

        print(f"  {strategy_name}: score={sc:.0f}, completed={comp} ({comp_rate:.0f}%), "
              f"timeout={tout}, avg_time={avg_t:.1f}s, distance={dist:.0f}")
        if sc > best_score:
            best_score = sc
            best_strategy = strategy_name
    print(f"  >>> Best: {best_strategy} (score={best_score:.0f})")

# Compare online vs genetic
print("\n--- Online (Nearest/MaxWeight) vs Offline (Genetic) ---")
for s_idx, s in enumerate(scales):
    online_best = max(
        data_by_scale[s]['strategies']['nearest'].get('total_score', 0),
        data_by_scale[s]['strategies']['max_weight'].get('total_score', 0)
    )
    genetic_score = data_by_scale[s]['strategies']['genetic'].get('total_score', 0)
    diff = genetic_score - online_best
    pct = (diff / abs(online_best) * 100) if online_best != 0 else 0
    print(f"  {scale_labels[s_idx]}: Online Best={online_best:.0f}, Genetic={genetic_score:.0f}, "
          f"Diff={diff:+.0f} ({pct:+.1f}%)")
