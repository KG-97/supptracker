import random
import time


def generate_data(num_interactions=10000):
    """Generate synthetic interactions data for benchmarking."""
    interactions = []
    inter_map = {}
    for i in range(num_interactions):
        a = f"C{i}"
        b = f"C{i+1}"
        inter = {
            "id": str(i),
            "a": a,
            "b": b,
            "bidirectional": True,
            "mechanism": [],
            "severity": "Mild",
            "evidence": "A",
            "effect": "",
            "action": "",
            "sources": [],
        }
        interactions.append(inter)
        inter_map[(a, b)] = inter
        inter_map[(b, a)] = inter
    return interactions, inter_map


def baseline_lookup(interactions, pair):
    a, b = pair
    for inter in interactions:
        if (inter["a"] == a and inter["b"] == b) or (
            inter["bidirectional"] and inter["a"] == b and inter["b"] == a
        ):
            return inter
    return None


def dict_lookup(inter_map, pair):
    return inter_map.get(pair)


def benchmark(num_interactions=10000, num_lookups=1000):
    interactions, inter_map = generate_data(num_interactions)
    pairs = [
        (f"C{i}", f"C{i+1}") for i in random.sample(range(num_interactions), num_lookups)
    ]

    start = time.perf_counter()
    for pair in pairs:
        baseline_lookup(interactions, pair)
    list_time = time.perf_counter() - start

    start = time.perf_counter()
    for pair in pairs:
        dict_lookup(inter_map, pair)
    dict_time = time.perf_counter() - start

    print(f"List scan time: {list_time:.4f}s")
    print(f"Dict lookup time: {dict_time:.4f}s")
    if dict_time > 0:
        print(f"Speedup: {list_time / dict_time:.1f}x")


if __name__ == "__main__":
    benchmark()
