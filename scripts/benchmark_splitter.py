#!/usr/bin/env python3
"""Benchmark text splitter performance."""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.parsers.text_splitter import (
    _embedder,
    create_text_splitter,
    _semantic_split,
)


def benchmark(func, *args, iterations=3, **kwargs):
    times = []
    result = None
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return {
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "min": min(times),
        "max": max(times),
        "result": result,
    }


def main():
    test_text = "这是一个测试句子，用于评估切分器性能。" * 500

    print("=" * 60)
    print("Text Splitter Performance Benchmark")
    print("=" * 60)

    # Benchmark: full splitter strategies
    print("\n--- Full Splitter Comparison ---")
    for strategy in ["markdown", "semantic", "legacy"]:
        splitter = create_text_splitter(strategy, chunk_size=512, chunk_overlap=100)
        result = benchmark(splitter.split_text, test_text, iterations=3)
        print(
            f"{strategy:12s}: {result['mean']:.3f}s "
            f"(median {result['median']:.3f}s, {len(result['result'])} chunks)"
        )

    # Benchmark: hierarchical vs flat
    print("\n--- Hierarchical Overhead ---")
    flat = create_text_splitter("markdown", enable_hierarchical=False)
    hier = create_text_splitter("markdown", enable_hierarchical=True)

    flat_result = benchmark(flat.split_text, test_text, iterations=3)
    hier_result = benchmark(hier.split_text, test_text, iterations=3)

    overhead = (hier_result["mean"] / flat_result["mean"] - 1) * 100
    print(f"Flat:     {flat_result['mean']:.3f}s")
    print(f"Hier:     {hier_result['mean']:.3f}s")
    print(f"Overhead: {overhead:+.1f}%")

    # Benchmark: semantic split standalone
    print("\n--- Semantic Split Standalone ---")
    semantic_result = benchmark(
        _semantic_split, test_text, chunk_size=512, overlap=100, iterations=3
    )
    print(
        f"Mean: {semantic_result['mean']:.3f}s, "
        f"chunks: {len(semantic_result['result'])}"
    )

    print("\n" + "=" * 60)
    print("Benchmark complete")

    # Assertions
    assert hier_result["mean"] < flat_result["mean"] * 2.0, (
        f"Hierarchical splitting exceeds 2x slowdown: "
        f"{hier_result['mean']:.3f}s vs {flat_result['mean']:.3f}s"
    )


if __name__ == "__main__":
    main()
