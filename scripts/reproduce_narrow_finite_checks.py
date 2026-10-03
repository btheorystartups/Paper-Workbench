"""Independent finite calculations for two explicitly fixed distance tables.

Standard library only; no file reads, network requests, or source-code execution.
Run directly to print a machine-readable JSON evidence supplement.
"""

import itertools
import json


def upper_sets(size, order):
    return {
        frozenset(i for i in range(size) if mask & (1 << i))
        for mask in range(1 << size)
        if all(not mask & (1 << i) or mask & (1 << j) for i, j in order)
    }


def ball_topology(distance):
    """Generate the topology, checking every distinct positive-radius regime.

    For these nonnegative integer tables, half-integers between successive
    distances and one radius above the maximum realize every strict ball.
    Finite intersections and unions then construct the generated topology.
    """
    size = len(distance)
    levels = sorted({value for row in distance for value in row} | {0})
    radii = [(left + right) / 2 for left, right in zip(levels, levels[1:], strict=False)]
    radii.append(levels[-1] + 1)
    balls = {frozenset(j for j in range(size) if row[j] < radius) for row in distance for radius in radii}
    topology = balls | {frozenset(), frozenset(range(size))}
    while True:
        previous = set(topology)
        for left, right in itertools.product(previous, repeat=2):
            topology.add(left | right)
            topology.add(left & right)
        if topology == previous:
            return radii, balls, topology


def serialize_sets(sets):
    return [sorted(value) for value in sorted(sets, key=lambda value: (len(value), sorted(value)))]


def check_instance(name, distance, cells, order, coarse_distance=None):
    size = len(distance)
    triples = list(itertools.product(range(size), repeat=3))
    failures = [[i, j, k] for i, j, k in triples if distance[i][k] > max(distance[i][j], distance[j][k])]
    cross = [
        [i, j, distance[i][j]] for i, j in itertools.product(range(size), repeat=2) if cells[i] != cells[j]
    ]
    radii, balls, topology = ball_topology(distance)
    expected = upper_sets(size, order)
    return {
        "name": name,
        "distance_matrix": distance,
        "coarse_cells": cells,
        "order_pairs": [list(pair) for pair in order],
        "diagonal_zero": all(distance[i][i] == 0 for i in range(size)),
        "nonnegative": all(value >= 0 for row in distance for value in row),
        "directed_ultrametric": {
            "triples_checked": len(triples),
            "passed": not failures,
            "failing_triples": failures,
        },
        "strict_forward_balls": {
            "definition": "B(x,r) = {y: D(x,y) < r}, r > 0",
            "representative_radii": radii,
            "distinct_balls": serialize_sets(balls),
        },
        "generated_topology": serialize_sets(topology),
        "expected_upper_sets": serialize_sets(expected),
        "topology_matches_upper_sets": topology == expected,
        "cross_cell_check": {
            "ordered_pairs": cross,
            "pair_count": len(cross),
            "expected_distance": coarse_distance,
            "status": ("passed" if all(value == coarse_distance for _, _, value in cross) else "failed")
            if cross
            else "not_applicable_no_cross_cell_pairs",
        },
    }


def reproduce():
    return {
        "format_version": 1,
        "assumptions": {
            "epsilon": 1,
            "q": 2,
            "strict_forward_balls": True,
            "scope": "Explicit finite parameter specializations only.",
            "conditional_instance": "Four-state instance is conditional, not source-stated.",
            "limitations": (
                "Not a proof of a general theorem, source verification, or human scientific review."
            ),
        },
        "instances": [
            check_instance(
                "one_coarse_cell_two_states", [[0, 0], [1, 0]], ["c", "c"], [(0, 0), (0, 1), (1, 1)]
            ),
            check_instance(
                "conditional_two_coarse_cells_four_states",
                [[0, 0, 2, 2], [1, 0, 2, 2], [2, 2, 0, 0], [2, 2, 1, 0]],
                ["c", "c", "d", "d"],
                [(0, 0), (0, 1), (1, 1), (2, 2), (2, 3), (3, 3)],
                2,
            ),
        ],
    }


if __name__ == "__main__":
    print(json.dumps(reproduce(), indent=2, sort_keys=True))
