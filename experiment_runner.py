import random

from genetic_optimizer import GeneticOptimizer
from Graph import generate_connected_weighted_graph
from simulation_config import SCALE_CONFIGS, get_config
from simulation_core import SimulationEngine
from Vehicle import Vehicle


_EXPERIMENT_CACHE = None


def build_task_blueprints(config):
    random.seed(config.seed)
    graph = generate_connected_weighted_graph(
        num_nodes=config.num_nodes,
        width=config.width,
        height=config.height,
        min_distance=config.min_distance,
        extra_k=config.extra_k,
    )
    warehouse_id = graph.set_central_warehouse(config.width, config.height)
    graph.set_charging_stations_auto(config.num_stations, config.queue_limit)
    targets = [
        node_id
        for node_id, node in graph.nodes.items()
        if node_id != warehouse_id and node.type not in ("warehouse", "charging_station")
    ]

    rng = random.Random(config.seed + 99)
    task_count = {
        "small": 15,
        "medium": 24,
        "large": 36,
    }[config.key]
    blueprints = []
    for task_id in range(task_count):
        appear_time = rng.randint(0, int(config.duration_seconds * 0.65))
        target_id = rng.choice(targets)
        weight = rng.uniform(0.35 * Vehicle.LOAD_CAPACITY_KG, 2.2 * Vehicle.LOAD_CAPACITY_KG)
        blueprints.append({
            "id": task_id,
            "appear_time": float(appear_time),
            "due_time": float(appear_time + 180),
            "target_id": target_id,
            "weight": round(weight, 2),
        })
    blueprints.sort(key=lambda item: item["appear_time"])
    return blueprints


def run_online_experiment(scale_key, strategy, task_blueprints):
    config = get_config(scale_key)
    engine = SimulationEngine(scale_key=scale_key, strategy=strategy, allow_multi_vehicle=True)
    engine.reset(
        scale_key=scale_key,
        strategy=strategy,
        allow_multi_vehicle=True,
        task_blueprints=task_blueprints,
    )
    engine.is_running = True
    for _ in range(config.duration_seconds):
        engine.step()
    metrics = engine.controller.get_metrics()
    return {
        "strategy": strategy,
        "label": "最近任务优先" if strategy == "nearest" else "最大重量优先",
        **metrics,
    }


def run_genetic_experiment(scale_key, task_blueprints):
    config = get_config(scale_key)
    random.seed(config.seed)
    graph = generate_connected_weighted_graph(
        num_nodes=config.num_nodes,
        width=config.width,
        height=config.height,
        min_distance=config.min_distance,
        extra_k=config.extra_k,
    )
    warehouse_id = graph.set_central_warehouse(config.width, config.height)
    graph.set_charging_stations_auto(config.num_stations, config.queue_limit)
    optimizer = GeneticOptimizer(
        graph=graph,
        warehouse_id=warehouse_id,
        task_blueprints=task_blueprints,
        num_vehicles=config.num_vehicles,
        duration_seconds=config.duration_seconds,
        seed=config.seed + 777,
        population_size=28 if scale_key == "large" else 34,
        generations=36 if scale_key == "large" else 48,
    )
    return optimizer.optimize()


def run_all_experiments(force=False):
    global _EXPERIMENT_CACHE
    if _EXPERIMENT_CACHE is not None and not force:
        return _EXPERIMENT_CACHE

    results = []
    for scale_key, config in SCALE_CONFIGS.items():
        task_blueprints = build_task_blueprints(config)
        strategies = [
            run_online_experiment(scale_key, "nearest", task_blueprints),
            run_online_experiment(scale_key, "max_weight", task_blueprints),
            run_genetic_experiment(scale_key, task_blueprints),
        ]
        results.append({
            "scale": scale_key,
            "scale_label": config.label,
            "task_count": len(task_blueprints),
            "strategies": strategies,
        })

    _EXPERIMENT_CACHE = {
        "results": results,
        "summary": _build_summary(results),
    }
    return _EXPERIMENT_CACHE


def _build_summary(results):
    summary = []
    for row in results:
        best = max(row["strategies"], key=lambda item: item["total_score"])
        summary.append({
            "scale": row["scale"],
            "scale_label": row["scale_label"],
            "best_strategy": best["label"],
            "best_score": best["total_score"],
        })
    return summary
