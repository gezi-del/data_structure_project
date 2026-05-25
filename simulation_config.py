from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationConfig:
    key: str
    label: str
    num_nodes: int
    width: int
    height: int
    min_distance: int
    extra_k: int
    num_vehicles: int
    num_stations: int
    queue_limit: int
    duration_seconds: int
    max_tasks: int
    seed: int
    spawn_wait_seconds: float = 12.0
    spawn_increase_per_second: float = 0.08


SCALE_CONFIGS = {
    "small": SimulationConfig(
        key="small",
        label="小规模",
        num_nodes=25,
        width=160,
        height=160,
        min_distance=14,
        extra_k=2,
        num_vehicles=8,
        num_stations=4,
        queue_limit=4,
        duration_seconds=300,
        max_tasks=12,
        seed=202601,
    ),
    "medium": SimulationConfig(
        key="medium",
        label="中规模",
        num_nodes=40,
        width=200,
        height=200,
        min_distance=15,
        extra_k=2,
        num_vehicles=15,
        num_stations=6,
        queue_limit=6,
        duration_seconds=450,
        max_tasks=18,
        seed=202602,
    ),
    "large": SimulationConfig(
        key="large",
        label="大规模",
        num_nodes=70,
        width=280,
        height=240,
        min_distance=13,
        extra_k=3,
        num_vehicles=25,
        num_stations=10,
        queue_limit=8,
        duration_seconds=600,
        max_tasks=28,
        seed=202603,
    ),
}


def get_config(scale_key):
    return SCALE_CONFIGS.get(scale_key, SCALE_CONFIGS["medium"])
