import math
import random

from Fleet_Controller import ShortestPathCache
from Vehicle import Vehicle


class GeneticOptimizer:
    """上帝视角离线优化器：用遗传算法近似求解任务顺序与车辆分配。"""

    def __init__(
        self,
        graph,
        warehouse_id,
        task_blueprints,
        num_vehicles,
        duration_seconds,
        population_size=34,
        generations=48,
        mutation_rate=0.18,
        seed=42,
    ):
        self.graph = graph
        self.warehouse_id = warehouse_id
        self.task_blueprints = task_blueprints
        self.num_vehicles = num_vehicles
        self.duration_seconds = duration_seconds
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.random = random.Random(seed)
        self.path_cache = ShortestPathCache(graph)
        self.vehicle_capacity = Vehicle.LOAD_CAPACITY_KG
        self.vehicle_battery = graph.nodes[warehouse_id].x * 0 + max(
            1.0,
            max(node.x for node in graph.nodes.values()) * 1.5,
        )
        self.speed_km_per_s = (Vehicle.AVERAGE_SPEED_KMH / 3600.0) * 45.0
        self.units = self._build_delivery_units()

    def optimize(self):
        if not self.units:
            return self._empty_result()

        population = self._seed_population()
        best = None
        history = []

        for _ in range(self.generations):
            scored = [(self._evaluate(chromosome), chromosome) for chromosome in population]
            scored.sort(key=lambda item: item[0]["fitness"], reverse=True)
            if best is None or scored[0][0]["fitness"] > best[0]["fitness"]:
                best = scored[0]
            history.append(round(best[0]["score"], 2))

            next_population = [scored[0][1], scored[1][1]]
            while len(next_population) < self.population_size:
                parent_a = self._tournament(scored)
                parent_b = self._tournament(scored)
                child = self._crossover(parent_a, parent_b)
                self._mutate(child)
                next_population.append(child)
            population = next_population

        result = best[0]
        result["history"] = history
        result["strategy"] = "genetic"
        result["label"] = "遗传算法"
        return result

    def _build_delivery_units(self):
        units = []
        for task in self.task_blueprints:
            trips = max(1, math.ceil(task["weight"] / self.vehicle_capacity))
            remaining = task["weight"]
            for _ in range(trips):
                load = min(self.vehicle_capacity, remaining)
                units.append({
                    "task_id": task["id"],
                    "target_id": task["target_id"],
                    "appear_time": task["appear_time"],
                    "due_time": task["due_time"],
                    "weight": task["weight"],
                    "load": load,
                })
                remaining -= load
        return units

    def _random_chromosome(self):
        order = list(range(len(self.units)))
        self.random.shuffle(order)
        assignments = [self.random.randrange(self.num_vehicles) for _ in self.units]
        return {"order": order, "assignments": assignments}

    def _seed_population(self):
        population = [
            self._heuristic_chromosome("appear"),
            self._heuristic_chromosome("distance"),
            self._heuristic_chromosome("weight"),
        ]
        while len(population) < self.population_size:
            population.append(self._random_chromosome())
        return population

    def _heuristic_chromosome(self, mode):
        indices = list(range(len(self.units)))
        if mode == "distance":
            indices.sort(key=lambda idx: self.path_cache.shortest_path(self.warehouse_id, self.units[idx]["target_id"])[0])
        elif mode == "weight":
            indices.sort(key=lambda idx: (-self.units[idx]["weight"], self.units[idx]["appear_time"]))
        else:
            indices.sort(key=lambda idx: (self.units[idx]["appear_time"], self.units[idx]["due_time"]))

        assignments = [0] * len(self.units)
        available_time = [0.0] * self.num_vehicles
        for unit_idx in indices:
            vehicle_id = min(range(self.num_vehicles), key=lambda vid: available_time[vid])
            outbound, _ = self.path_cache.shortest_path(self.warehouse_id, self.units[unit_idx]["target_id"])
            route_distance = outbound * 2
            start_time = max(available_time[vehicle_id], self.units[unit_idx]["appear_time"])
            available_time[vehicle_id] = start_time + route_distance / max(self.speed_km_per_s, 1e-6)
            assignments[unit_idx] = vehicle_id
        return {"order": indices, "assignments": assignments}

    def _evaluate(self, chromosome):
        vehicle_time = [0.0] * self.num_vehicles
        vehicle_battery = [self.vehicle_battery] * self.num_vehicles
        task_remaining = {task["id"]: task["weight"] for task in self.task_blueprints}
        task_completion = {}
        task_distance = {task["id"]: 0.0 for task in self.task_blueprints}
        total_distance = 0.0
        total_charge_wait = 0.0
        charge_sessions = 0

        for unit_idx in chromosome["order"]:
            unit = self.units[unit_idx]
            vehicle_id = chromosome["assignments"][unit_idx] % self.num_vehicles
            outbound, _ = self.path_cache.shortest_path(self.warehouse_id, unit["target_id"])
            if outbound == math.inf:
                continue
            route_distance = outbound * 2
            required = route_distance + self.vehicle_battery * 0.1

            start_time = max(vehicle_time[vehicle_id], unit["appear_time"])
            if vehicle_battery[vehicle_id] < required:
                wait_time = 10.0 + charge_sessions * 0.8
                start_time += wait_time
                total_charge_wait += wait_time
                charge_sessions += 1
                vehicle_battery[vehicle_id] = self.vehicle_battery

            outbound_time = outbound / max(self.speed_km_per_s, 1e-6)
            round_trip_time = route_distance / max(self.speed_km_per_s, 1e-6)
            finish_time = start_time + outbound_time
            vehicle_time[vehicle_id] = start_time + round_trip_time
            vehicle_battery[vehicle_id] = max(0.0, vehicle_battery[vehicle_id] - route_distance)
            task_remaining[unit["task_id"]] = max(0.0, task_remaining[unit["task_id"]] - unit["load"])
            task_distance[unit["task_id"]] += outbound
            total_distance += route_distance
            if task_remaining[unit["task_id"]] <= 1e-6:
                task_completion[unit["task_id"]] = max(
                    task_completion.get(unit["task_id"], 0.0),
                    finish_time,
                )

        score = 0.0
        completed = 0
        timeout_tasks = 0
        total_finish_time = 0.0
        records = []
        for task in self.task_blueprints:
            finish_time = task_completion.get(task["id"])
            if finish_time is None or finish_time > self.duration_seconds:
                timeout_tasks += 1
                score -= 80.0
                continue

            completed += 1
            time_taken = finish_time - task["appear_time"]
            task_score = 100.0
            task_score += 0.05 * task["weight"]
            task_score -= 0.6 * time_taken
            task_score -= 0.3 * task_distance[task["id"]]
            timeout = time_taken > 180
            if timeout:
                timeout_tasks += 1
                task_score -= 50.0 + (time_taken - 180) * 1.0
            score += task_score
            total_finish_time += time_taken
            records.append({
                "id": task["id"],
                "finish_time": round(finish_time, 2),
                "time_taken": round(time_taken, 2),
                "score": round(task_score, 2),
                "timeout": timeout,
            })

        avg_finish = total_finish_time / completed if completed else 0.0
        fitness = score + completed * 180.0 - timeout_tasks * 75.0 - total_charge_wait * 0.05
        return {
            "fitness": fitness,
            "score": round(score, 2),
            "total_score": round(score, 2),
            "completed_tasks": completed,
            "timeout_tasks": timeout_tasks,
            "avg_finish_time": round(avg_finish, 2),
            "total_distance": round(total_distance, 2),
            "charge_sessions": charge_sessions,
            "total_charge_wait_time": round(total_charge_wait, 2),
            "records": records[:10],
        }

    def _tournament(self, scored):
        sample = self.random.sample(scored[: max(4, len(scored))], k=3)
        sample.sort(key=lambda item: item[0]["fitness"], reverse=True)
        parent = sample[0][1]
        return {"order": parent["order"][:], "assignments": parent["assignments"][:]}

    def _crossover(self, parent_a, parent_b):
        size = len(parent_a["order"])
        left = self.random.randrange(size)
        right = self.random.randrange(left, size)
        child_order = [None] * size
        child_order[left:right + 1] = parent_a["order"][left:right + 1]
        fill = [gene for gene in parent_b["order"] if gene not in child_order]
        fill_index = 0
        for idx in range(size):
            if child_order[idx] is None:
                child_order[idx] = fill[fill_index]
                fill_index += 1

        assignments = [
            parent_a["assignments"][idx]
            if self.random.random() < 0.5
            else parent_b["assignments"][idx]
            for idx in range(size)
        ]
        return {"order": child_order, "assignments": assignments}

    def _mutate(self, chromosome):
        if self.random.random() < self.mutation_rate and len(chromosome["order"]) > 1:
            i, j = self.random.sample(range(len(chromosome["order"])), 2)
            chromosome["order"][i], chromosome["order"][j] = chromosome["order"][j], chromosome["order"][i]
        for idx in range(len(chromosome["assignments"])):
            if self.random.random() < self.mutation_rate * 0.25:
                chromosome["assignments"][idx] = self.random.randrange(self.num_vehicles)

    def _empty_result(self):
        return {
            "strategy": "genetic",
            "label": "遗传算法",
            "fitness": 0.0,
            "score": 0.0,
            "total_score": 0.0,
            "completed_tasks": 0,
            "timeout_tasks": 0,
            "avg_finish_time": 0.0,
            "total_distance": 0.0,
            "charge_sessions": 0,
            "total_charge_wait_time": 0.0,
            "records": [],
            "history": [],
        }
