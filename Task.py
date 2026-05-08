import random
from Vehicle import Vehicle  # 需要获取 Vehicle.LOAD_CAPACITY_KG


class Task:
    """
    任务类：记录单个订单的详细信息
    """

    def __init__(self, task_id, appear_time, target_node_id, target_coords, weight):
        self.id = task_id
        self.appear_time = appear_time  # 产生时间 (单位：秒或tick)
        self.target_id = target_node_id  # 目的节点ID
        self.coords = target_coords  # 目的地点坐标 (x, y)
        self.weight = weight  # 货物重量 (kg)

        # 任务状态：pending (等待中), assigned (已派车), completed (已送达)
        self.status = "pending"
        self.finish_time = None  # 记录完成时间用于评分

    def __repr__(self):
        return (f"[任务#{self.id}] 时间:{self.appear_time}s | "
                f"目标点:{self.target_id} {self.coords} | 重量:{self.weight:.1f}kg | 状态:{self.status}")


class TaskManager:
    """
    任务管理器：负责任务的生成、上限控制和状态维护
    """

    def __init__(self, graph, max_tasks_limit=10):
        self.graph = graph
        self.tasks = []  # 存储所有生成的任务
        self.max_tasks_limit = max_tasks_limit
        self.task_counter = 0  # 用于生成唯一的任务ID

        # 获取所有可作为目的地的节点（排除仓库和充电站节点）
        self.potential_targets = [
            nid for nid, node in graph.nodes.items()
            if node.type not in ("warehouse", "charging_station")
        ]

    def generate_task(self, current_time):
        """
        生成一个随机任务
        """
        if not self.potential_targets:
            return None
        # 1. 检查当前未完成（pending 或 assigned）的任务数量是否达到上限
        active_tasks = [t for t in self.tasks if t.status != "completed"]
        if len(active_tasks) >= self.max_tasks_limit:
            # print(f"提示：当前任务数已达上限 ({self.max_tasks_limit})，暂停生成。")
            return None

        # 2. 确定任务参数
        target_id = random.choice(self.potential_targets)
        target_node = self.graph.nodes[target_id]

        # 货物重量：1kg ~ 单台车最大载重的两倍 (1500 * 2 = 3000kg)
        weight = random.uniform(1.0, 2 * Vehicle.LOAD_CAPACITY_KG)

        # 3. 创建任务对象
        new_task = Task(
            task_id=self.task_counter,
            appear_time=current_time,
            target_node_id=target_id,
            target_coords=(target_node.x, target_node.y),
            weight=weight
        )

        # 4. 更新系统状态
        self.tasks.append(new_task)
        self.task_counter += 1

        # 同时也更新地图节点的类型，以便在 GUI 上显示为橙色任务点
        if self.graph.nodes[target_id].type == "road":
            self.graph.nodes[target_id].type = "task_point"

        return new_task

    def get_pending_tasks(self):
        """返回当前所有待处理的任务"""
        return [t for t in self.tasks if t.status == "pending"]

    def mark_task_completed(self, task_id, finish_time):
        """当车辆送达时，调用此函数更新任务状态"""
        for t in self.tasks:
            if t.id == task_id:
                t.status = "completed"
                t.finish_time = finish_time
                # 任务完成后，如果该点没有其他任务，可以改回 road 类型（可选）
                # self.graph.nodes[t.target_id].type = "road"
                break
