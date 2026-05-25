import random
import threading
import time

from Fleet_Controller import FleetController
from Graph import generate_connected_weighted_graph
from Task_Manager import TaskManager
from Vehicle import Vehicle
from simulation_config import get_config


class SimulationEngine:
    """维护一组可重置、可配置的在线动态仿真。"""

    def __init__(
        self,
        scale_key="medium",
        strategy="nearest",
        allow_multi_vehicle=True,
        use_fixed_seed=True,
    ):
        self.lock = threading.RLock()
        self.sim_seconds_per_tick = 1.0
        self.time_scale = 6.0
        self.real_seconds_per_tick = self.sim_seconds_per_tick / self.time_scale
        self.is_running = False
        self.logs = []
        self.reset(
            scale_key=scale_key,
            strategy=strategy,
            allow_multi_vehicle=allow_multi_vehicle,
            use_fixed_seed=use_fixed_seed,
        )

    def reset(
        self,
        scale_key="medium",
        strategy="nearest",
        allow_multi_vehicle=True,
        task_blueprints=None,
        use_fixed_seed=True,
    ):
        with self.lock:
            self.config = get_config(scale_key)
            self.strategy = strategy if strategy in ("nearest", "max_weight") else "nearest"
            self.allow_multi_vehicle = bool(allow_multi_vehicle)
            self.use_fixed_seed = bool(use_fixed_seed)
            if self.use_fixed_seed:
                random.seed(self.config.seed)
            else:
                random.seed()

            self.width = self.config.width
            self.height = self.config.height
            self.graph = generate_connected_weighted_graph(
                num_nodes=self.config.num_nodes,
                width=self.config.width,
                height=self.config.height,
                min_distance=self.config.min_distance,
                extra_k=self.config.extra_k,
            )
            self.warehouse_id = self.graph.set_central_warehouse(self.width, self.height)
            self.graph.set_charging_stations_auto(
                num_stations=self.config.num_stations,
                queue_limit=self.config.queue_limit,
            )

            self.task_manager = TaskManager(
                self.graph,
                max_tasks_limit=self.config.max_tasks,
                spawn_wait_seconds=self.config.spawn_wait_seconds,
                spawn_increase_per_second=self.config.spawn_increase_per_second,
                task_blueprints=task_blueprints,
            )
            self.vehicles = []
            for _ in range(self.config.num_vehicles):
                vehicle = Vehicle(width=self.width)
                vehicle.current_node_id = self.warehouse_id
                vehicle.status = "idle"
                self.vehicles.append(vehicle)

            self.controller = FleetController(
                graph=self.graph,
                task_manager=self.task_manager,
                vehicles=self.vehicles,
                warehouse_id=self.warehouse_id,
                strategy=self.strategy,
                allow_multi_vehicle=self.allow_multi_vehicle,
                tick_seconds=self.sim_seconds_per_tick,
            )
            self.current_tick = 0
            self.logs = []
            self.is_running = False

    def configure(self, scale_key=None, strategy=None, allow_multi_vehicle=None, use_fixed_seed=None):
        with self.lock:
            self.reset(
                scale_key=scale_key or self.config.key,
                strategy=strategy or self.strategy,
                allow_multi_vehicle=(
                    self.allow_multi_vehicle
                    if allow_multi_vehicle is None
                    else allow_multi_vehicle
                ),
                use_fixed_seed=(
                    self.use_fixed_seed
                    if use_fixed_seed is None
                    else use_fixed_seed
                ),
            )

    def step(self):
        with self.lock:
            new_tasks = self.task_manager.step_generate(self.current_tick)
            for task in new_tasks:
                self.logs.append(
                    f"[{self.current_tick:.0f}s] 新任务: 节点 {task.target_id}, "
                    f"重量 {task.weight:.1f}kg"
                )
            self.controller.step(self.current_tick)
            self.current_tick += self.sim_seconds_per_tick
            if self.current_tick >= self.config.duration_seconds:
                self.is_running = False

    def run_loop(self):
        while True:
            if self.is_running:
                self.step()
            time.sleep(self.real_seconds_per_tick)

    def start(self):
        with self.lock:
            self.is_running = True

    def pause(self):
        with self.lock:
            self.is_running = False

    def get_map_payload(self):
        with self.lock:
            nodes = [
                {
                    "id": node.id,
                    "x": node.x,
                    "y": node.y,
                    "type": node.type,
                    "queue_count": node.queue_count,
                    "queue_limit": node.queue_limit,
                }
                for node in self.graph.nodes.values()
            ]
            links = []
            for u in self.graph.adj:
                for v, weight in self.graph.adj[u].items():
                    if u < v:
                        links.append({"source": u, "target": v, "weight": round(weight, 2)})
            return {
                "scale": self.config.key,
                "scale_label": self.config.label,
                "use_fixed_seed": self.use_fixed_seed,
                "width": self.width,
                "height": self.height,
                "nodes": nodes,
                "links": links,
                "warehouse_id": self.warehouse_id,
                "charging_station_ids": list(self.graph.charging_station_ids),
            }

    def get_status_payload(self):
        with self.lock:
            task_lookup = {task.id: task for task in self.task_manager.tasks}
            vehicles = []
            for idx, vehicle in enumerate(self.vehicles):
                state = self.controller.vehicle_states.get(idx)
                pos_x, pos_y = self._vehicle_position(vehicle, state)
                task_info = None
                if state and state.task_id is not None:
                    task = task_lookup.get(state.task_id)
                    if task:
                        meta = self.controller.task_meta.get(task.id, {})
                        task_info = {
                            "id": task.id,
                            "target_id": task.target_id,
                            "weight": round(task.weight, 1),
                            "status": task.status,
                            "appear_time": task.appear_time,
                            "assigned_load": round(state.assigned_load, 1),
                            "remaining_weight": round(meta.get("remaining_weight", task.weight), 1),
                        }
                vehicles.append({
                    "id": idx,
                    "battery": round(vehicle.current_battery, 1),
                    "max_battery": round(vehicle.battery_capacity, 1),
                    "load": round(vehicle.current_load, 1),
                    "node_id": vehicle.current_node_id,
                    "status": vehicle.status,
                    "mission": state.mission if state else "idle",
                    "task": task_info,
                    "x": round(pos_x, 2),
                    "y": round(pos_y, 2),
                })

            active_tasks = []
            for task in self.task_manager.tasks:
                if task.status == "completed":
                    continue
                meta = self.controller.task_meta.get(task.id, {})
                active_tasks.append({
                    "id": task.id,
                    "target_id": task.target_id,
                    "weight": round(task.weight, 1),
                    "appear_time": task.appear_time,
                    "due_time": task.due_time,
                    "status": task.status,
                    "remaining_weight": round(meta.get("remaining_weight", task.weight), 1),
                    "coords": task.coords,
                })

            completed_tasks = [
                {
                    "id": item["id"],
                    "finish_time": round(item["finish_time"], 1),
                    "time_taken": round(item["time_taken"], 1),
                    "score": round(item["score"], 2),
                    "timeout": item["timeout"],
                }
                for item in self.controller.completed_task_records[-8:]
            ]
            station_loads = [
                {
                    "id": station_id,
                    "queue_count": self.graph.nodes[station_id].queue_count,
                    "queue_limit": self.graph.nodes[station_id].queue_limit,
                }
                for station_id in self.graph.charging_station_ids
            ]

            return {
                "tick": round(self.current_tick, 1),
                "running": self.is_running,
                "scale": self.config.key,
                "scale_label": self.config.label,
                "strategy": self.strategy,
                "allow_multi_vehicle": self.allow_multi_vehicle,
                "use_fixed_seed": self.use_fixed_seed,
                "duration_seconds": self.config.duration_seconds,
                "refresh_interval_ms": max(100, round(self.real_seconds_per_tick * 1000)),
                "vehicles": vehicles,
                "tasks": active_tasks,
                "completed_tasks": completed_tasks,
                "station_loads": station_loads,
                "metrics": self.controller.get_metrics(),
                "logs": self.logs[-8:],
                "width": self.width,
                "height": self.height,
                "warehouse_id": self.warehouse_id,
            }

    def _vehicle_position(self, vehicle, state):
        node = self.graph.nodes[vehicle.current_node_id]
        x, y = node.x, node.y
        if not state or vehicle.status != "moving":
            return x, y
        if not state.route or state.route_index >= len(state.route) - 1:
            return x, y

        current_id = state.route[state.route_index]
        next_id = state.route[state.route_index + 1]
        edge_dist = self.graph.adj[current_id].get(next_id)
        if not edge_dist or edge_dist <= 0:
            return x, y

        remaining = max(0.0, state.distance_to_next)
        progress = min(1.0, max(0.0, (edge_dist - remaining) / edge_dist))
        current_node = self.graph.nodes[current_id]
        next_node = self.graph.nodes[next_id]
        return (
            current_node.x + (next_node.x - current_node.x) * progress,
            current_node.y + (next_node.y - current_node.y) * progress,
        )
