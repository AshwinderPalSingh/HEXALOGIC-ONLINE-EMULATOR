#!/usr/bin/env python3
"""
HexaLogic Performance Benchmark Suite

Measures:
  1. Assembly throughput (lines/sec)
  2. Forward simulation speed (instructions/sec, machine-cycles/sec)
  3. Reverse-step overhead (% slowdown vs forward-only)
  4. Memory footprint per session (bytes)

Usage:
    python3 scripts/benchmark.py [--json-out path.json]
"""
import sys, os, time, json, argparse, statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sim8051.session import SimulatorSession


def _aggregate_runs(runs: list[dict], rate_keys: list[str]) -> dict:
    """Collapse N repeated-run result dicts into one, replacing each rate_key
    with its mean and reporting the observed min/max range alongside it.

    Single-sample benchmark numbers can swing 2x run-to-run from machine
    load/cache warmup alone (observed directly on assembly throughput), so a
    lone sample is not a trustworthy figure to publish.
    """
    merged = dict(runs[0])
    merged["repeats"] = len(runs)
    for key in rate_keys:
        values = [r[key] for r in runs]
        merged[key] = round(statistics.mean(values), 1)
        merged[f"{key}_min"] = round(min(values), 1)
        merged[f"{key}_max"] = round(max(values), 1)
    return merged


# ── Test programs ──────────────────────────────────────────────────────

SMALL_PROGRAM = """\
ORG 0000H
MOV A,#01H
MOV R0,#20H
MOV @R0,A
INC A
MOV P1,A
SJMP $
END
"""

MEDIUM_PROGRAM = """\
ORG 0000H
MOV A,#01H
START:
MOV P1,A
ACALL DELAY
RL A
SJMP START
DELAY:
MOV R7,#200
D1: MOV R6,#250
D2: DJNZ R6,D2
DJNZ R7,D1
RET
END
"""

LARGE_PROGRAM_LINES = 200
def _generate_large_program():
    lines = ["ORG 0000H"]
    for i in range(LARGE_PROGRAM_LINES):
        lines.append(f"MOV A,#{i % 256}")
        lines.append(f"MOV R{i % 8},A")
    lines.append("SJMP $")
    lines.append("END")
    return "\n".join(lines)


# ── Benchmark functions ───────────────────────────────────────────────

def benchmark_assembly(program: str, label: str, iterations: int = 10) -> dict:
    """Measure assembly throughput."""
    line_count = len(program.strip().split("\n"))
    times = []
    for _ in range(iterations):
        session = SimulatorSession(session_id="bench-asm")
        t0 = time.perf_counter()
        session.assemble(program)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    avg_ms = (sum(times) / len(times)) * 1000
    lines_per_sec = line_count / (sum(times) / len(times)) if sum(times) > 0 else float("inf")
    return {
        "benchmark": f"assembly_{label}",
        "lines": line_count,
        "iterations": iterations,
        "avg_ms": round(avg_ms, 3),
        "lines_per_sec": round(lines_per_sec, 1),
    }


def benchmark_simulation(program: str, label: str, max_steps: int = 10000) -> dict:
    """Measure forward simulation speed."""
    session = SimulatorSession(session_id="bench-sim")
    session.set_clock(12_000_000)
    session.assemble(program)
    t0 = time.perf_counter()
    result = session.run(max_steps=max_steps)
    t1 = time.perf_counter()
    elapsed_s = t1 - t0
    steps = result["metrics"]["steps"]
    cycles = result["metrics"].get("cycles_executed", 0)
    inst_per_sec = steps / elapsed_s if elapsed_s > 0 else float("inf")
    cycles_per_sec = cycles / elapsed_s if elapsed_s > 0 else float("inf")
    return {
        "benchmark": f"simulation_{label}",
        "max_steps": max_steps,
        "actual_steps": steps,
        "machine_cycles": cycles,
        "elapsed_ms": round(elapsed_s * 1000, 3),
        "instructions_per_sec": round(inst_per_sec, 0),
        "machine_cycles_per_sec": round(cycles_per_sec, 0),
    }


def benchmark_reverse_step(program: str, label: str, forward_steps: int = 1000, back_steps: int = 100) -> dict:
    """Measure reverse-step overhead."""
    session = SimulatorSession(session_id="bench-rev")
    session.set_clock(12_000_000)
    session.assemble(program)

    # Forward timing
    t0 = time.perf_counter()
    session.run(max_steps=forward_steps)
    t1 = time.perf_counter()
    forward_ms = (t1 - t0) * 1000

    # Reverse timing
    t2 = time.perf_counter()
    for _ in range(back_steps):
        result = session.step_back()
        if result.get("reason") == "history_empty":
            break
    t3 = time.perf_counter()
    reverse_ms = (t3 - t2) * 1000

    forward_per_step = forward_ms / forward_steps if forward_steps > 0 else 0
    reverse_per_step = reverse_ms / back_steps if back_steps > 0 else 0
    overhead_pct = ((reverse_per_step / forward_per_step) - 1) * 100 if forward_per_step > 0 else 0

    return {
        "benchmark": f"reverse_step_{label}",
        "forward_steps": forward_steps,
        "back_steps": back_steps,
        "forward_ms": round(forward_ms, 3),
        "reverse_ms": round(reverse_ms, 3),
        "forward_us_per_step": round(forward_per_step * 1000, 2),
        "reverse_us_per_step": round(reverse_per_step * 1000, 2),
        "overhead_percent": round(overhead_pct, 1),
    }


def benchmark_memory() -> dict:
    """Measure memory footprint per session."""
    import tracemalloc
    tracemalloc.start()
    sessions = []
    snapshot_before = tracemalloc.take_snapshot()
    for i in range(10):
        s = SimulatorSession(session_id=f"bench-mem-{i}")
        s.set_clock(12_000_000)
        s.assemble(MEDIUM_PROGRAM)
        s.run(max_steps=100)
        sessions.append(s)
    snapshot_after = tracemalloc.take_snapshot()
    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_bytes = sum(s.size_diff for s in stats if s.size_diff > 0)
    per_session = total_bytes / 10
    tracemalloc.stop()
    return {
        "benchmark": "memory_footprint",
        "sessions_created": 10,
        "total_bytes": total_bytes,
        "bytes_per_session": round(per_session, 0),
        "kb_per_session": round(per_session / 1024, 1),
    }


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HexaLogic performance benchmarks")
    parser.add_argument("--json-out", default="", help="Output JSON results to file")
    parser.add_argument(
        "--repeats", type=int, default=5,
        help="Re-run each benchmark this many times and report mean + min/max range "
             "(a single sample can swing ~2x from machine load/cache warmup alone)",
    )
    args = parser.parse_args()

    large_program = _generate_large_program()
    results = []

    print("=" * 60)
    print("  HexaLogic Performance Benchmark Suite")
    print(f"  ({args.repeats} repeats per benchmark; reporting mean [min, max])")
    print("=" * 60)

    # Assembly benchmarks
    print("\n── Assembly Throughput ──")
    for label, prog in [("small_8line", SMALL_PROGRAM), ("medium_13line", MEDIUM_PROGRAM), ("large_400line", large_program)]:
        runs = [benchmark_assembly(prog, label) for _ in range(args.repeats)]
        r = _aggregate_runs(runs, ["avg_ms", "lines_per_sec"])
        results.append(r)
        print(f"  {label}: {r['avg_ms']:.1f} ms ({r['lines_per_sec']:.0f} lines/sec, "
              f"range {r['lines_per_sec_min']:.0f}-{r['lines_per_sec_max']:.0f})")

    # Simulation benchmarks
    print("\n── Simulation Speed ──")
    for label, prog, steps in [("small_1k", SMALL_PROGRAM, 1000), ("medium_10k", MEDIUM_PROGRAM, 10000), ("medium_100k", MEDIUM_PROGRAM, 100000)]:
        runs = [benchmark_simulation(prog, label, steps) for _ in range(args.repeats)]
        r = _aggregate_runs(runs, ["elapsed_ms", "instructions_per_sec", "machine_cycles_per_sec"])
        results.append(r)
        print(f"  {label}: {r['elapsed_ms']:.1f} ms, {r['instructions_per_sec']:.0f} inst/sec "
              f"(range {r['instructions_per_sec_min']:.0f}-{r['instructions_per_sec_max']:.0f}), "
              f"{r['machine_cycles_per_sec']:.0f} cycles/sec")

    # Reverse-step benchmarks
    print("\n── Reverse-Step Overhead ──")
    for label, prog, fwd, bck in [("medium_1k_100back", MEDIUM_PROGRAM, 1000, 100), ("medium_10k_500back", MEDIUM_PROGRAM, 10000, 500)]:
        runs = [benchmark_reverse_step(prog, label, fwd, bck) for _ in range(args.repeats)]
        r = _aggregate_runs(runs, ["forward_us_per_step", "reverse_us_per_step", "overhead_percent"])
        results.append(r)
        print(f"  {label}: fwd={r['forward_us_per_step']:.1f} µs/step, rev={r['reverse_us_per_step']:.1f} µs/step, "
              f"overhead={r['overhead_percent']:.1f}% (range {r['overhead_percent_min']:.1f}-{r['overhead_percent_max']:.1f}%)")

    # Memory benchmark
    print("\n── Memory Footprint ──")
    runs = [benchmark_memory() for _ in range(args.repeats)]
    r = _aggregate_runs(runs, ["bytes_per_session", "kb_per_session"])
    results.append(r)
    print(f"  Per session: {r['kb_per_session']:.1f} KB ({r['bytes_per_session']:.0f} bytes)")

    print("\n" + "=" * 60)
    print(f"  Total benchmarks: {len(results)}")
    print("=" * 60)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.json_out}")

    return results


if __name__ == "__main__":
    main()
