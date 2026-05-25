import heapq
import math
from dataclasses import dataclass, field


@dataclass
class VehicleState:
    route: list = field(default_factory=list)
    route_index: int = 0
    distance_to_next: float = 0.0
    mission: str = "idle"  # idle/pickup/task/charge/return
    task_id: int | None = None
    assigned_load: float = 0.0
    pending_task_id: int | None = None
    charging_station_id: int | None = None
    wait_time_left: float = 0.0
    charge_time_left: float = 0.0
    travelled_on_task: float = 0.0


class ShortestPathCache:
    def __init__(self, graph):
        self.graph = graph
        self.cache = {}

    def shortest_path(self, start, end):
        if start == end:
            return 0.0, [start]

        key = (start, end)
        if key in self.cache:
            return self.cache[key]

        distances = {start: 0.0}
        previous = {}
        visited = set()
        heap = [(0.0, start)]

        while heap:
            dist, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)

            if node == end:
                break

            for neighbor, weight in self.graph.adj[node].items():
                nd = dist + weight
                if nd < distances.get(neighbor, math.inf):
                    distances[neighbor] = nd
                    previous[neighbor] = node
                    heapq.heappush(heap, (nd, neighbor))

        if end not in distances:
            return math.inf, [start]

        path = [end]
        cur = end
        while cur != start:
            cur = previous[cur]
            path.append(cur)
        path.reverse()

        result = (distances[end], path)
        self.cache[key] = result
        self.cache[(end, start)] = (distances[end], list(reversed(path)))
        return result


class FleetController:
    def __init__(
        self,
        graph,
        task_manager,
        vehicles,
        warehouse_id,
        strategy="nearest",
        allow_multi_vehicle=True,
        tick_seconds=1.0,
        speed_scale=45.0,
        reserve_battery_ratio=0.1,
        task_timeout=180,
    ):
        self.graph = graph
        self.task_manager = task_manager
        self.vehicles = vehicles
        self.warehouse_id = warehouse_id
        self.strategy = strategy
        self.allow_multi_vehicle = allow_multi_vehicle
        self.tick_seconds = tick_seconds
        self.speed_scale = speed_scale
        self.reserve_battery_ratio = reserve_battery_ratio
        self.task_timeout = task_timeout

        self.path_cache = ShortestPathCache(graph)
        self.vehicle_states = {i: VehicleState() for i in range(len(vehicles))}
        self.task_meta = {}

        self.base_score = 100.0
        self.weight_bonus_per_kg = 0.05
        self.time_penalty_per_s = 0.6
        self.distance_penalty_per_km = 0.3
        self.timeout_penalty = 50.0
        self.timeout_penalty_per_s = 1.0
        self.total_score = 0.0
        self.total_distance = 0.0
        self.completed_tasks = 0
        self.timeout_tasks = 0
        self.charge_sessions = 0
        self.total_charge_wait_time = 0.0
        self.completed_task_records = []

    def set_strategy(self, strategy):
        self.strategy = strategy

    def step(self, current_tick):
        self._handle_timeouts(current_tick)
        self._update_charging(current_tick)
        self._advance_vehicles(current_tick)
        self._assign_tasks(current_tick)
        self._return_idle_vehicles(current_tick)

    def _handle_timeouts(self, current_tick):
        for task in self.task_manager.tasks:
            if task.status == "completed":
                continue
            meta = self._ensure_task_meta(task)
            if meta["timeout_penalized"]:
                continue
            if current_tick - task.appear_time > self.task_timeout:
                self.total_score -= self.timeout_penalty
                meta["timeout_penalized"] = True
                task.timeout = True
                self.timeout_tasks += 1

    def _update_charging(self, current_tick):
        _ = current_tick
        for idx, vehicle in enumerate(self.vehicles):
            state = self.vehicle_states[idx]
            if state.mission != "charge":
                continue

            if state.wait_time_left > 0:
                state.wait_time_left = max(0.0, state.wait_time_left - self.tick_seconds)
                vehicle.status = "charging"
                continue

            if state.charge_time_left > 0:
                state.charge_time_left = max(0.0, state.charge_time_left - self.tick_seconds)
                vehicle.status = "charging"
                if state.charge_time_left <= 0:
                    vehicle.set_current_battery(vehicle.battery_capacity)
                    self.graph.vehicle_leave_charging_station(state.charging_station_id)
                    state.charging_station_id = None
                    state.mission = "idle"
                    state.route = []
                    state.route_index = 0
                    state.distance_to_next = 0.0
                    vehicle.status = "idle"
                continue

    def _advance_vehicles(self, current_tick):
        for idx, vehicle in enumerate(self.vehicles):
            state = self.vehicle_states[idx]
            if state.mission == "idle":
                continue
            if state.mission == "charge" and (state.wait_time_left > 0 or state.charge_time_left > 0):
                continue
            if not state.route or state.route_index >= len(state.route) - 1:
                continue

            vehicle.status = "moving"
            distance_budget = self._speed_km_per_s(vehicle) * self.tick_seconds

            while distance_budget > 1e-6 and state.route_index < len(state.route) - 1:
                current_node = state.route[state.route_index]
                next_node = state.route[state.route_index + 1]
                edge_distance = self.graph.adj[current_node][next_node]

                if state.distance_to_next <= 1e-9:
                    required_battery = edge_distance * vehicle.energy_per_km
                    if vehicle.current_battery < required_battery + self._reserve_battery(vehicle):
                        self._plan_charge_route(idx)
                        break
                    state.distance_to_next = edge_distance

                travel = min(distance_budget, state.distance_to_next)
                vehicle.drive(travel)
                self.total_distance += travel
                state.distance_to_next -= travel
                distance_budget -= travel

                if state.mission == "task":
                    state.travelled_on_task += travel

                if state.distance_to_next <= 1e-6:
                    state.route_index += 1
                    vehicle.current_node_id = next_node
                    state.distance_to_next = 0.0

                    if state.route_index >= len(state.route) - 1:
                        self._on_arrival(idx, current_tick)
                        break

    def _assign_tasks(self, current_tick):
        for idx, vehicle in enumerate(self.vehicles):
            state = self.vehicle_states[idx]
            if vehicle.status != "idle":
                continue

            if state.pending_task_id is not None:
                task = self._get_task_by_id(state.pending_task_id)
                if task is None or task.status == "completed":
                    if task is not None:
                        meta = self._ensure_task_meta(task)
                        if meta["locked_vehicle_id"] == idx:
                            meta["locked_vehicle_id"] = None
                    state.pending_task_id = None
                    continue

                if vehicle.current_node_id != self.warehouse_id:
                    if self._can_reach_warehouse(vehicle):
                        self._route_to_warehouse(state, vehicle.current_node_id, mission="pickup")
                        vehicle.status = "moving"
                    else:
                        self._plan_charge_route(idx)
                    continue

                self._start_pickup(idx, task, current_tick)
                continue

            if vehicle.current_node_id != self.warehouse_id:
                continue

            task = self._select_task_for_vehicle(vehicle, idx)
            if task is None:
                continue

            self._assign_task(idx, task, current_tick)

    def _return_idle_vehicles(self, current_tick):
        _ = current_tick
        for idx, vehicle in enumerate(self.vehicles):
            state = self.vehicle_states[idx]
            if vehicle.status != "idle":
                continue
            if state.pending_task_id is not None:
                continue
            if vehicle.current_node_id == self.warehouse_id:
                continue

            if self._can_reach_warehouse(vehicle):
                if self._route_to_warehouse(state, vehicle.current_node_id, mission="return"):
                    vehicle.status = "moving"
            else:
                self._plan_charge_route(idx)

    def _select_task_for_vehicle(self, vehicle, vehicle_idx):
        candidates = []

        for task in self.task_manager.tasks:
            if task.status == "completed":
                continue

            meta = self._ensure_task_meta(task)
            if meta["remaining_weight"] <= 0:
                continue

            if meta["locked_vehicle_id"] is not None and meta["locked_vehicle_id"] != vehicle_idx:
                continue

            if self.allow_multi_vehicle:
                max_needed = math.ceil(meta["remaining_weight"] / vehicle.load_capacity)
                if meta["active_assignments"] >= max_needed:
                    continue

            dist, path = self.path_cache.shortest_path(vehicle.current_node_id, task.target_id)
            if dist == math.inf:
                continue

            candidates.append((task, dist, path))

        if not candidates:
            return None

        if self.strategy == "max_weight":
            candidates.sort(key=lambda x: (-x[0].weight, x[1]))
        else:
            candidates.sort(key=lambda x: x[1])

        return candidates[0][0]

    def _assign_task(self, vehicle_idx, task, current_tick):
        vehicle = self.vehicles[vehicle_idx]
        state = self.vehicle_states[vehicle_idx]
        meta = self._ensure_task_meta(task)
        if meta["remaining_weight"] <= 0:
            return

        if vehicle.current_node_id != self.warehouse_id:
            state.pending_task_id = task.id
            state.assigned_load = 0.0
            if not self.allow_multi_vehicle:
                meta["locked_vehicle_id"] = vehicle_idx
                task.status = "assigned"
            if self._can_reach_warehouse(vehicle):
                self._route_to_warehouse(state, vehicle.current_node_id, mission="pickup")
                vehicle.status = "moving"
            else:
                self._plan_charge_route(vehicle_idx)
            return

        if not self._has_enough_battery_from_warehouse(vehicle, task):
            if not self.allow_multi_vehicle:
                meta["locked_vehicle_id"] = vehicle_idx
                state.pending_task_id = task.id
                task.status = "assigned"
            self._plan_charge_route(vehicle_idx)
            return

        assigned_load = min(meta["remaining_weight"], vehicle.load_capacity)
        if assigned_load <= 0:
            return

        vehicle.set_current_load(0.0)
        vehicle.add_load(assigned_load)

        meta["active_assignments"] += 1
        if not self.allow_multi_vehicle:
            meta["locked_vehicle_id"] = vehicle_idx
        task.status = "assigned"

        state.task_id = task.id
        state.assigned_load = assigned_load
        state.travelled_on_task = 0.0
        state.pending_task_id = None

        dist, path = self.path_cache.shortest_path(vehicle.current_node_id, task.target_id)
        if dist == math.inf:
            return

        self._set_route(state, path, mission="task")
        vehicle.status = "moving"

        meta["assigned_tick"] = current_tick

    def _start_pickup(self, vehicle_idx, task, current_tick):
        vehicle = self.vehicles[vehicle_idx]
        state = self.vehicle_states[vehicle_idx]
        meta = self._ensure_task_meta(task)

        if meta["remaining_weight"] <= 0:
            state.pending_task_id = None
            return

        if not self._has_enough_battery_from_warehouse(vehicle, task):
            self._plan_charge_route(vehicle_idx)
            return

        assigned_load = min(meta["remaining_weight"], vehicle.load_capacity)
        if assigned_load <= 0:
            state.pending_task_id = None
            return

        vehicle.set_current_load(0.0)
        vehicle.add_load(assigned_load)

        meta["active_assignments"] += 1
        if not self.allow_multi_vehicle:
            meta["locked_vehicle_id"] = vehicle_idx
        task.status = "assigned"

        state.task_id = task.id
        state.assigned_load = assigned_load
        state.pending_task_id = None
        state.travelled_on_task = 0.0

        dist, path = self.path_cache.shortest_path(self.warehouse_id, task.target_id)
        if dist == math.inf:
            return

        self._set_route(state, path, mission="task")
        vehicle.status = "moving"
        meta["assigned_tick"] = current_tick

    def _has_enough_battery_from_warehouse(self, vehicle, task):
        dist_to_task, _ = self.path_cache.shortest_path(self.warehouse_id, task.target_id)
        if dist_to_task == math.inf:
            return False

        dist_to_safe = self._distance_to_safe_node(task.target_id)
        if dist_to_safe == math.inf:
            return False

        required = dist_to_task + dist_to_safe + self._reserve_battery(vehicle)
        return vehicle.current_battery >= required

    def _can_reach_warehouse(self, vehicle):
        dist, _ = self.path_cache.shortest_path(vehicle.current_node_id, self.warehouse_id)
        if dist == math.inf:
            return False
        return vehicle.current_battery >= dist + self._reserve_battery(vehicle)

    def _route_to_warehouse(self, state, start_node_id, mission="return"):
        dist, path = self.path_cache.shortest_path(start_node_id, self.warehouse_id)
        if dist == math.inf:
            return False
        self._set_route(state, path, mission=mission)
        return True

    def _distance_to_safe_node(self, node_id):
        dist_to_warehouse, _ = self.path_cache.shortest_path(node_id, self.warehouse_id)
        if not self.graph.charging_station_ids:
            return dist_to_warehouse

        best = dist_to_warehouse
        for station_id in self.graph.charging_station_ids:
            dist, _ = self.path_cache.shortest_path(node_id, station_id)
            if dist < best:
                best = dist
        return best

    def _plan_charge_route(self, vehicle_idx):
        vehicle = self.vehicles[vehicle_idx]
        state = self.vehicle_states[vehicle_idx]
        station_id, path, _ = self._select_charging_station(vehicle)
        if station_id is None:
            vehicle.status = "stranded"
            state.route = []
            state.route_index = 0
            state.distance_to_next = 0.0
            state.mission = "idle"
            return

        state.charging_station_id = station_id
        self._set_route(state, path, mission="charge")
        vehicle.status = "moving"

    def _select_charging_station(self, vehicle):
        if not self.graph.charging_station_ids:
            return None, None, math.inf

        speed = self._speed_km_per_s(vehicle)
        best = (None, None, math.inf)

        for station_id in self.graph.charging_station_ids:
            node = self.graph.nodes[station_id]
            if node.queue_count >= node.queue_limit:
                continue

            dist, path = self.path_cache.shortest_path(vehicle.current_node_id, station_id)
            if dist == math.inf:
                continue
            if vehicle.current_battery < dist + self._reserve_battery(vehicle):
                continue

            travel_time = dist / max(speed, 1e-6)
            wait_time = node.queue_count * vehicle.get_charge_time_seconds()
            score = travel_time + wait_time

            if score < best[2]:
                best = (station_id, path, score)

        if best[0] is None:
            return None, None, math.inf

        return best

    def _on_arrival(self, vehicle_idx, current_tick):
        vehicle = self.vehicles[vehicle_idx]
        state = self.vehicle_states[vehicle_idx]

        if state.mission == "task":
            self._deliver_task(vehicle_idx, current_tick)
        elif state.mission == "charge":
            self._start_charging(vehicle_idx)
        elif state.mission == "pickup":
            task = self._get_task_by_id(state.pending_task_id)
            if task is None or task.status == "completed":
                state.pending_task_id = None
                state.mission = "idle"
                vehicle.status = "idle"
            else:
                self._start_pickup(vehicle_idx, task, current_tick)
        elif state.mission == "return":
            state.mission = "idle"
            vehicle.status = "idle"

    def _deliver_task(self, vehicle_idx, current_tick):
        vehicle = self.vehicles[vehicle_idx]
        state = self.vehicle_states[vehicle_idx]
        task = self._get_task_by_id(state.task_id)
        if task is None:
            self._clear_mission(vehicle_idx)
            return

        meta = self._ensure_task_meta(task)
        meta["distance_accum"] += state.travelled_on_task
        state.travelled_on_task = 0.0

        meta["active_assignments"] = max(0, meta["active_assignments"] - 1)
        meta["remaining_weight"] = max(0.0, meta["remaining_weight"] - state.assigned_load)

        vehicle.add_load(-state.assigned_load)
        state.assigned_load = 0.0

        if meta["remaining_weight"] <= 1e-6:
            task.status = "completed"
            task.finish_time = current_tick
            self._score_task(task, meta, current_tick)
            meta["locked_vehicle_id"] = None
            self.completed_tasks += 1
            self._restore_task_node_if_finished(task)
        else:
            if not self.allow_multi_vehicle:
                task.status = "assigned"
                state.task_id = None
                state.assigned_load = 0.0
                state.pending_task_id = task.id

                if vehicle.current_node_id == self.warehouse_id:
                    self._start_pickup(vehicle_idx, task, current_tick)
                else:
                    if self._can_reach_warehouse(vehicle):
                        self._route_to_warehouse(state, vehicle.current_node_id, mission="pickup")
                        vehicle.status = "moving"
                    else:
                        self._plan_charge_route(vehicle_idx)
                return
            else:
                if meta["active_assignments"] > 0:
                    task.status = "assigned"
                else:
                    task.status = "pending"

        self._clear_mission(vehicle_idx)

    def _start_charging(self, vehicle_idx):
        vehicle = self.vehicles[vehicle_idx]
        state = self.vehicle_states[vehicle_idx]
        station_id = state.charging_station_id
        if station_id is None:
            self._clear_mission(vehicle_idx)
            return

        if not self.graph.vehicle_enter_charging_station(station_id):
            state.charging_station_id = None
            self._plan_charge_route(vehicle_idx)
            return

        wait_slots = max(0, self.graph.nodes[station_id].queue_count - 1)
        state.wait_time_left = wait_slots * vehicle.get_charge_time_seconds()
        state.charge_time_left = vehicle.get_charge_time_seconds()
        self.charge_sessions += 1
        self.total_charge_wait_time += state.wait_time_left
        state.mission = "charge"
        vehicle.status = "charging"

    def _score_task(self, task, meta, current_tick):
        time_taken = current_tick - task.appear_time
        distance = meta["distance_accum"]

        score = self.base_score
        score += self.weight_bonus_per_kg * task.weight
        score -= self.time_penalty_per_s * time_taken
        score -= self.distance_penalty_per_km * distance

        if time_taken > self.task_timeout:
            extra = time_taken - self.task_timeout
            score -= self.timeout_penalty_per_s * extra
            if not meta["timeout_penalized"]:
                score -= self.timeout_penalty
                meta["timeout_penalized"] = True

        self.total_score += score
        meta["last_score"] = score
        task.score = score
        task.distance = distance
        task.timeout = time_taken > self.task_timeout
        self.completed_task_records.append({
            "id": task.id,
            "appear_time": task.appear_time,
            "finish_time": current_tick,
            "time_taken": time_taken,
            "weight": task.weight,
            "distance": distance,
            "score": score,
            "timeout": task.timeout,
        })
        return score

    def _restore_task_node_if_finished(self, task):
        has_active_task = any(
            other.target_id == task.target_id and other.status != "completed"
            for other in self.task_manager.tasks
        )
        if not has_active_task and self.graph.nodes[task.target_id].type == "task_point":
            self.graph.nodes[task.target_id].type = "road"

    def get_metrics(self):
        total_finished_time = sum(item["time_taken"] for item in self.completed_task_records)
        avg_finish_time = (
            total_finished_time / self.completed_tasks
            if self.completed_tasks
            else 0.0
        )
        return {
            "total_score": round(self.total_score, 2),
            "completed_tasks": self.completed_tasks,
            "timeout_tasks": self.timeout_tasks,
            "avg_finish_time": round(avg_finish_time, 2),
            "total_distance": round(self.total_distance, 2),
            "charge_sessions": self.charge_sessions,
            "total_charge_wait_time": round(self.total_charge_wait_time, 2),
        }

    def _clear_mission(self, vehicle_idx):
        vehicle = self.vehicles[vehicle_idx]
        state = self.vehicle_states[vehicle_idx]
        state.route = []
        state.route_index = 0
        state.distance_to_next = 0.0
        state.mission = "idle"
        state.task_id = None
        state.assigned_load = 0.0
        state.pending_task_id = None
        state.charging_station_id = None
        state.wait_time_left = 0.0
        state.charge_time_left = 0.0
        state.travelled_on_task = 0.0
        vehicle.status = "idle"

    def _set_route(self, state, path, mission):
        state.route = path
        state.route_index = 0
        state.distance_to_next = 0.0
        state.mission = mission

    def _reserve_battery(self, vehicle):
        return vehicle.battery_capacity * self.reserve_battery_ratio

    def _speed_km_per_s(self, vehicle):
        return (vehicle.average_speed / 3600.0) * self.speed_scale

    def _ensure_task_meta(self, task):
        if task.id not in self.task_meta:
            self.task_meta[task.id] = {
                "remaining_weight": task.weight,
                "active_assignments": 0,
                "locked_vehicle_id": None,
                "assigned_tick": None,
                "timeout_penalized": False,
                "distance_accum": 0.0,
                "last_score": 0.0,
            }
        return self.task_meta[task.id]

    def _get_task_by_id(self, task_id):
        for task in self.task_manager.tasks:
            if task.id == task_id:
                return task
        return None
