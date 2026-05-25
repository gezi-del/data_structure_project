import random
from Task import Task
from Vehicle import Vehicle


class TaskManager:
    """
    任务管理器：负责任务的按概率生成、上限控制和状态维护
    """

    def __init__(
        self,
        graph,
        max_tasks_limit=10,
        spawn_wait_seconds=30.0,
        spawn_increase_per_second=0.02,
        task_blueprints=None,
    ):
        self.graph = graph
        self.tasks = []  # 存储所有生成的任务
        self.max_tasks_limit = max_tasks_limit
        self.task_counter = 0  # 用于生成唯一的任务ID
        self.last_generate_time = 0.0
        self.spawn_wait_seconds = spawn_wait_seconds
        self.spawn_increase_per_second = spawn_increase_per_second
        self.task_blueprints = sorted(task_blueprints or [], key=lambda item: item["appear_time"])
        self.next_blueprint_index = 0

        # 获取所有可作为目的地的节点（排除仓库和充电站节点）
        self.potential_targets = [
            nid for nid, node in graph.nodes.items()
            if node.type not in ("warehouse", "charging_station")
        ]

    def step_generate(self, current_time):
        """
        每个单位时间调用一次，按概率生成随机数量的任务
        """
        if self.task_blueprints:
            return self._release_blueprint_tasks(current_time)

        if not self.potential_targets:
            return []

        spawn_prob = self._spawn_probability(current_time)
        if spawn_prob <= 0.0 or random.random() >= spawn_prob:
            return []

        num_to_generate = 1

        generated_this_step = []
        for _ in range(num_to_generate):
            # 检查未完成任务是否达到上限
            active_tasks = [t for t in self.tasks if t.status != "completed"]
            if len(active_tasks) >= self.max_tasks_limit:
                break

            task = self._create_single_task(current_time)
            if task is None:
                break
            generated_this_step.append(task)

        if generated_this_step:
            self.last_generate_time = current_time

        return generated_this_step

    def _release_blueprint_tasks(self, current_time):
        generated_this_step = []
        while self.next_blueprint_index < len(self.task_blueprints):
            blueprint = self.task_blueprints[self.next_blueprint_index]
            if blueprint["appear_time"] > current_time:
                break

            active_tasks = [t for t in self.tasks if t.status != "completed"]
            if len(active_tasks) >= self.max_tasks_limit:
                break

            task = self._create_task_from_blueprint(blueprint)
            generated_this_step.append(task)
            self.next_blueprint_index += 1

        return generated_this_step

    def _spawn_probability(self, current_time):
        elapsed = current_time - self.last_generate_time
        if elapsed < self.spawn_wait_seconds:
            return 0.0

        steps = int(elapsed - self.spawn_wait_seconds)
        return min(1.0, steps * self.spawn_increase_per_second)

    def _create_single_task(self, current_time):
        """内部私有方法：执行具体的随机属性生成逻辑"""
        if not self.potential_targets:
            return None
        target_id = random.choice(self.potential_targets)
        target_node = self.graph.nodes[target_id]

        # 货物重量：1kg ~ 2倍载重
        weight = random.uniform(1.0, 2 * Vehicle.LOAD_CAPACITY_KG)

        new_task = Task(
            task_id=self.task_counter,
            appear_time=current_time,
            target_node_id=target_id,
            target_coords=(target_node.x, target_node.y),
            weight=weight,
            due_time=current_time + 180,
        )

        self.tasks.append(new_task)
        self.task_counter += 1

        # 联动修改地图节点类型，以便在可视化时显示为橙色
        if self.graph.nodes[target_id].type == "road":
            self.graph.nodes[target_id].type = "task_point"

        return new_task

    def _create_task_from_blueprint(self, blueprint):
        target_id = blueprint["target_id"]
        target_node = self.graph.nodes[target_id]
        new_task = Task(
            task_id=self.task_counter,
            appear_time=blueprint["appear_time"],
            target_node_id=target_id,
            target_coords=(target_node.x, target_node.y),
            weight=blueprint["weight"],
            due_time=blueprint.get("due_time"),
        )
        self.tasks.append(new_task)
        self.task_counter += 1
        if self.graph.nodes[target_id].type == "road":
            self.graph.nodes[target_id].type = "task_point"
        return new_task

    def get_pending_tasks(self):
        """返回当前所有待分配的任务"""
        return [t for t in self.tasks if t.status == "pending"]

    def mark_task_completed(self, task_id, finish_time):
        """任务完成回调"""
        for t in self.tasks:
            if t.id == task_id:
                t.status = "completed"
                t.finish_time = finish_time
                if self.graph.nodes[t.target_id].type == "task_point":
                    has_active_task = any(
                        other.target_id == t.target_id and other.status != "completed"
                        for other in self.tasks
                    )
                    if not has_active_task:
                        self.graph.nodes[t.target_id].type = "road"
                break
