import random
import math
import matplotlib.pyplot as plt
from collections import deque


# =========================
# 基础工具函数
# =========================

def get_distance(node1, node2):
    """计算两个节点之间的欧几里得距离，同时可作为边权"""
    return math.sqrt((node1.x - node2.x) ** 2 + (node1.y - node2.y) ** 2)


def get_point_distance(x1, y1, x2, y2):
    """计算两个坐标点之间的欧几里得距离"""
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


# =========================
# 节点类
# =========================

class Node:
    def __init__(self, node_id, x, y, node_type="road"):
        self.id = node_id
        self.x = x
        self.y = y
        self.type = node_type   # road / warehouse / charging_station / task_point

        # ---------- 充电站相关属性 ----------
        self.queue_count = 0          # 当前排队车辆数
        self.queue_limit = 10         # 最大排队数量
        self.is_full = False          # 是否满负荷

    def can_accept_vehicle(self):
        """判断当前节点是否还能接收车辆进入充电排队"""
        if self.type != "charging_station":
            return False
        return (not self.is_full) and (self.queue_count < self.queue_limit)

    def enter_station(self):
        """
        一辆车尝试进入充电站排队
        返回 True 表示成功进入
        返回 False 表示站点已满，不允许进入
        """
        if self.type != "charging_station":
            return False

        if self.queue_count >= self.queue_limit:
            self.is_full = True
            return False

        self.queue_count += 1

        if self.queue_count >= self.queue_limit:
            self.is_full = True

        return True

    def leave_station(self):
        """一辆车离开充电站"""
        if self.type != "charging_station":
            return False

        if self.queue_count > 0:
            self.queue_count -= 1

        if self.queue_count < self.queue_limit:
            self.is_full = False

        return True

    def __repr__(self):
        return (f"Node(id={self.id}, x={self.x:.2f}, y={self.y:.2f}, "
                f"type={self.type}, queue={self.queue_count}, full={self.is_full})")


# =========================
# 图类
# =========================

class Graph:
    def __init__(self):
        self.nodes = {}   # {节点id: Node对象}
        self.adj = {}     # {节点id: {邻居id: 边权}}

        self.warehouse_id = None
        self.charging_station_ids = []

    def add_node(self, node):
        self.nodes[node.id] = node
        self.adj[node.id] = {}

    def add_edge(self, id1, id2, weight=None):
        """添加无向边"""
        if id1 == id2:
            return

        if id1 not in self.nodes or id2 not in self.nodes:
            raise ValueError("节点不存在，无法连边")

        if weight is None:
            weight = get_distance(self.nodes[id1], self.nodes[id2])

        self.adj[id1][id2] = weight
        self.adj[id2][id1] = weight

    def has_edge(self, id1, id2):
        return id2 in self.adj[id1]

    def edge_count(self):
        count = sum(len(neighbors) for neighbors in self.adj.values())
        return count // 2

    def is_connected(self):
        if not self.nodes:
            return True

        start = next(iter(self.nodes))
        visited = set()
        queue = deque([start])

        while queue:
            u = queue.popleft()
            if u in visited:
                continue
            visited.add(u)

            for v in self.adj[u]:
                if v not in visited:
                    queue.append(v)

        return len(visited) == len(self.nodes)

    def print_graph_info(self):
        print("图信息：")
        print(f"节点数: {len(self.nodes)}")
        print(f"边数: {self.edge_count()}")
        print(f"是否全联通: {self.is_connected()}")
        print(f"中央仓库节点: {self.warehouse_id}")
        print(f"充电站节点: {self.charging_station_ids}")

    # =========================
    # 1. 设置中央仓库
    # =========================
    def set_central_warehouse(self, width, height):
        """
        选取距离画布几何中心最近的节点作为中央仓库
        """
        center_x, center_y = width / 2, height / 2
        best_node_id = None
        min_dist = float("inf")

        for node_id, node in self.nodes.items():
            dist = get_point_distance(node.x, node.y, center_x, center_y)
            if dist < min_dist:
                min_dist = dist
                best_node_id = node_id

        if best_node_id is not None:
            self.nodes[best_node_id].type = "warehouse"
            self.warehouse_id = best_node_id
            print(f"中央仓库已确定：节点 {best_node_id}，坐标 ({self.nodes[best_node_id].x:.2f}, {self.nodes[best_node_id].y:.2f})")

        return best_node_id

    # =========================
    # 2. 自动选择充电站（优化版）
    # =========================
    def set_charging_stations_auto(
        self,
        num_stations=3,
        queue_limit=10,
        min_station_spacing_ratio=0.16,
        middle_ring_low=0.30,
        middle_ring_high=0.68,
        max_edge_station_ratio=0.25
    ):
        """
        自动选择充电站（优化版）

        核心思路：
        1. 中圈层节点优先
        2. 尽量降低所有节点到最近充电站的加权距离
        3. 充电站之间不要太近
        4. 允许少量边缘站，但不能大多数都在边缘
        """

        if self.warehouse_id is None:
            raise ValueError("请先设置中央仓库，再设置充电站")

        if num_stations <= 0:
            self.charging_station_ids = []
            return []

        # 先清空旧的充电站
        for node in self.nodes.values():
            if node.type == "charging_station":
                node.type = "road"
                node.queue_count = 0
                node.queue_limit = 10
                node.is_full = False

        self.charging_station_ids = []

        warehouse = self.nodes[self.warehouse_id]

        # ---------- 1. 计算地图尺度 ----------
        xs = [node.x for node in self.nodes.values()]
        ys = [node.y for node in self.nodes.values()]
        map_width = max(xs) - min(xs)
        map_height = max(ys) - min(ys)
        diag = math.sqrt(map_width ** 2 + map_height ** 2)

        min_station_spacing = diag * min_station_spacing_ratio

        # ---------- 2. 计算每个节点到仓库的距离 ----------
        dist_to_warehouse = {}
        max_dist = 0

        for nid, node in self.nodes.items():
            d = get_distance(node, warehouse)
            dist_to_warehouse[nid] = d
            if d > max_dist:
                max_dist = d

        if max_dist == 0:
            max_dist = 1

        # ---------- 3. 计算需求权重 ----------
        demand_weight = {}

        for nid, node in self.nodes.items():
            if nid == self.warehouse_id:
                demand_weight[nid] = 0.0
                continue

            r = dist_to_warehouse[nid] / max_dist   # 归一化半径 0~1

            # 中圈层偏好
            if middle_ring_low <= r <= middle_ring_high:
                ring_score = 1.0
            elif r < middle_ring_low:
                ring_score = max(0.2, r / middle_ring_low)
            else:
                denominator = (1 - middle_ring_high)
                if denominator <= 1e-9:
                    denominator = 1e-9
                ring_score = max(0.2, (1 - r) / denominator)

            # 节点度数越高，越像交通中转位置
            degree_score = len(self.adj[nid])

            # 综合评分
            demand_weight[nid] = 0.75 * ring_score + 0.25 * degree_score

        # 归一化
        max_w = max(demand_weight.values()) if demand_weight else 1
        if max_w == 0:
            max_w = 1
        for nid in demand_weight:
            demand_weight[nid] /= max_w

        # ---------- 4. 候选集合 ----------
        candidate_ids = [nid for nid in self.nodes if nid != self.warehouse_id]

        # 外圈候选点
        edge_candidates = set()
        for nid in candidate_ids:
            r = dist_to_warehouse[nid] / max_dist
            if r > middle_ring_high:
                edge_candidates.add(nid)

        max_edge_stations = max(1, round(num_stations * max_edge_station_ratio))

        selected = []
        current_nearest_dist = {nid: float("inf") for nid in self.nodes}

        def spacing_ok(candidate_id):
            cand = self.nodes[candidate_id]
            for sid in selected:
                if get_distance(cand, self.nodes[sid]) < min_station_spacing:
                    return False
            return True

        def edge_quota_ok(candidate_id):
            if candidate_id not in edge_candidates:
                return True
            edge_count = 0
            for sid in selected:
                if sid in edge_candidates:
                    edge_count += 1
            return edge_count < max_edge_stations

        # ---------- 5. 贪心选择充电站 ----------
        for _ in range(num_stations):
            best_id = None
            best_gain = -1

            for cand_id in candidate_ids:
                if cand_id in selected:
                    continue
                if not spacing_ok(cand_id):
                    continue
                if not edge_quota_ok(cand_id):
                    continue

                cand_node = self.nodes[cand_id]
                gain = 0.0

                for nid, node in self.nodes.items():
                    if nid == self.warehouse_id:
                        continue

                    old_dist = current_nearest_dist[nid]
                    new_dist = min(old_dist, get_distance(node, cand_node))
                    gain += demand_weight[nid] * (old_dist - new_dist)

                # 中圈层节点给一点奖励
                r = dist_to_warehouse[cand_id] / max_dist
                if middle_ring_low <= r <= middle_ring_high:
                    gain *= 1.15

                if gain > best_gain:
                    best_gain = gain
                    best_id = cand_id

            # 如果严格约束下选不出来，就放宽边缘数量约束，但仍保持站点间距
            if best_id is None:
                for cand_id in candidate_ids:
                    if cand_id in selected:
                        continue
                    if not spacing_ok(cand_id):
                        continue

                    cand_node = self.nodes[cand_id]
                    gain = 0.0

                    for nid, node in self.nodes.items():
                        if nid == self.warehouse_id:
                            continue

                        old_dist = current_nearest_dist[nid]
                        new_dist = min(old_dist, get_distance(node, cand_node))
                        gain += demand_weight[nid] * (old_dist - new_dist)

                    if gain > best_gain:
                        best_gain = gain
                        best_id = cand_id

            if best_id is None:
                break

            selected.append(best_id)

            station_node = self.nodes[best_id]
            for nid, node in self.nodes.items():
                current_nearest_dist[nid] = min(
                    current_nearest_dist[nid],
                    get_distance(node, station_node)
                )

        # ---------- 6. 正式标记为充电站 ----------
        for sid in selected:
            self.nodes[sid].type = "charging_station"
            self.nodes[sid].queue_limit = queue_limit
            self.nodes[sid].queue_count = 0
            self.nodes[sid].is_full = False

        self.charging_station_ids = selected
        print(f"优化后自动选取充电站节点：{selected}")
        return selected

    # =========================
    # 3. 手动指定充电站位置
    # =========================
    def set_charging_stations_manual(self, manual_positions, queue_limit=10):
        """
        根据用户给定的坐标，选择距离这些坐标最近的现有节点作为充电站
        manual_positions 示例：
        [(30, 40), (160, 50), (120, 150)]
        """
        if self.warehouse_id is None:
            raise ValueError("请先设置中央仓库，再设置充电站")

        # 清空旧的充电站
        for node in self.nodes.values():
            if node.type == "charging_station":
                node.type = "road"
                node.queue_count = 0
                node.queue_limit = 10
                node.is_full = False

        self.charging_station_ids = []
        used_ids = {self.warehouse_id}

        for (target_x, target_y) in manual_positions:
            best_id = None
            best_dist = float("inf")

            for node_id, node in self.nodes.items():
                if node_id in used_ids:
                    continue

                dist = get_point_distance(node.x, node.y, target_x, target_y)
                if dist < best_dist:
                    best_dist = dist
                    best_id = node_id

            if best_id is not None:
                used_ids.add(best_id)
                self.nodes[best_id].type = "charging_station"
                self.nodes[best_id].queue_limit = queue_limit
                self.nodes[best_id].queue_count = 0
                self.nodes[best_id].is_full = False
                self.charging_station_ids.append(best_id)

        print(f"手动指定充电站节点：{self.charging_station_ids}")
        return self.charging_station_ids

    # =========================
    # 4. 充电站队列管理
    # =========================
    def vehicle_enter_charging_station(self, station_id):
        """
        车辆尝试进入充电站排队
        满负荷时返回 False，但节点仍然可以作为通路经过
        """
        node = self.nodes[station_id]
        if node.type != "charging_station":
            print(f"节点 {station_id} 不是充电站")
            return False

        ok = node.enter_station()
        if ok:
            print(f"车辆进入充电站 {station_id} 成功，当前排队数 = {node.queue_count}")
        else:
            print(f"充电站 {station_id} 已满负荷，禁止继续排队；但车辆仍可将其作为通路经过")
        return ok

    def vehicle_leave_charging_station(self, station_id):
        """车辆离开充电站"""
        node = self.nodes[station_id]
        if node.type != "charging_station":
            print(f"节点 {station_id} 不是充电站")
            return False

        node.leave_station()
        print(f"车辆离开充电站 {station_id}，当前排队数 = {node.queue_count}")
        return True


# =========================
# 生成节点时的最小间距检查
# =========================

def _is_far_enough(existing_nodes, x, y, min_distance):
    """判断候选点 (x, y) 是否与已有节点保持最小间距"""
    if min_distance <= 0:
        return True

    for node in existing_nodes:
        if get_point_distance(node.x, node.y, x, y) < min_distance:
            return False
    return True


# =========================
# 生成随机节点
# =========================

def generate_nodes(num_nodes=30, width=100, height=100, min_distance=0, max_attempts_per_node=2000):
    """
    num_nodes: 控制节点规模（节点总数量）
    width,height: 控制画布规模 / 地图范围
    min_distance: 控制节点之间最小距离，避免节点太密
    """
    graph = Graph()

    for i in range(num_nodes):
        placed = False

        for _ in range(max_attempts_per_node):
            x = random.uniform(0, width)
            y = random.uniform(0, height)

            if _is_far_enough(graph.nodes.values(), x, y, min_distance):
                placed = True
                break

        if not placed:
            raise ValueError(
                "在当前区域和最小间距约束下无法生成足够多的节点。"
                "请减小 min_distance、减少 num_nodes，或增大 width/height。"
            )

        node = Node(i, x, y, node_type="road")
        graph.add_node(node)

    return graph


# =========================
# 第一阶段：先保证全联通
# =========================

def connect_graph_guaranteed(graph):
    """
    用类似 Prim 的思想，从已连通集合到未连通集合不断接入最近点
    保证整张图全联通
    """
    node_ids = list(graph.nodes.keys())
    if len(node_ids) <= 1:
        return

    connected = {node_ids[0]}
    unconnected = set(node_ids[1:])

    while unconnected:
        best_u = None
        best_v = None
        best_dist = float("inf")

        for u in connected:
            for v in unconnected:
                dist = get_distance(graph.nodes[u], graph.nodes[v])
                if dist < best_dist:
                    best_dist = dist
                    best_u = u
                    best_v = v

        graph.add_edge(best_u, best_v, best_dist)
        connected.add(best_v)
        unconnected.remove(best_v)


# =========================
# 第二阶段：补充额外近邻边
# =========================

def add_extra_nearest_edges(graph, extra_k=2):
    """
    extra_k: 控制每个节点额外补多少条近邻边
    数值越大，图越稠密
    """
    for i in graph.nodes:
        distances = []

        for j in graph.nodes:
            if i == j:
                continue
            if graph.has_edge(i, j):
                continue

            dist = get_distance(graph.nodes[i], graph.nodes[j])
            distances.append((j, dist))

        distances.sort(key=lambda x: x[1])

        for j, dist in distances[:extra_k]:
            graph.add_edge(i, j, dist)


# =========================
# 总生成函数
# =========================

def generate_connected_weighted_graph(
    num_nodes=30,      # 控制节点规模
    width=100,         # 控制画布宽度
    height=100,        # 控制画布高度
    extra_k=2,         # 控制图的稠密程度
    min_distance=0,    # 控制节点最小间距
    max_attempts_per_node=2000,
):
    graph = generate_nodes(
        num_nodes=num_nodes,
        width=width,
        height=height,
        min_distance=min_distance,
        max_attempts_per_node=max_attempts_per_node,
    )

    connect_graph_guaranteed(graph)
    add_extra_nearest_edges(graph, extra_k=extra_k)

    return graph


# =========================
# 可视化
# =========================

def visualize_graph(graph, show_weights=False):
    plt.figure(figsize=(10, 8))

    drawn_edges = set()

    # 先画边
    for u in graph.adj:
        for v, w in graph.adj[u].items():
            if (v, u) in drawn_edges:
                continue

            x1, y1 = graph.nodes[u].x, graph.nodes[u].y
            x2, y2 = graph.nodes[v].x, graph.nodes[v].y

            plt.plot([x1, x2], [y1, y2], linewidth=1, color="gray", alpha=0.7)

            if show_weights:
                mx = (x1 + x2) / 2
                my = (y1 + y2) / 2
                plt.text(mx, my, f"{w:.1f}", fontsize=8)

            drawn_edges.add((u, v))

    # 再画节点
    for node_id, node in graph.nodes.items():
        if node.type == "warehouse":
            color = "red"
            size = 180
            label = f"W{node_id}"

        elif node.type == "charging_station":
            color = "green"
            size = 140

            if node.is_full:
                label = f"C{node_id}\n{node.queue_count}/{node.queue_limit}\nFULL"
            else:
                label = f"C{node_id}\n{node.queue_count}/{node.queue_limit}"

        else:
            color = "skyblue"
            size = 100
            label = str(node_id)

        plt.scatter(node.x, node.y, s=size, c=color, edgecolors="black", zorder=5)
        plt.text(node.x + 1, node.y + 1, label, fontsize=8, fontweight='bold')

    plt.title("Logistics Road Network Graph")
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.axis("equal")
    plt.show()


# =========================
# 主程序入口
# =========================

if __name__ == "__main__":
    # 是否固定随机种子：
    # True  -> 每次生成相同地图，方便调试
    # False -> 每次生成不同地图，方便模拟
    use_fixed_seed = False

    if use_fixed_seed:
        random.seed(42)
    else:
        random.seed()

    # ----------------------------------------
    # 下面这些参数就是控制规模和地图范围的地方
    # ----------------------------------------

    # 1. 节点规模：控制地图里总共有多少个节点
    num_nodes = 40

    # 2. 画布规模：控制地图的物理范围大小
    width = 200
    height = 160

    # 3. 图的稠密程度：控制每个节点额外补几条近邻边
    extra_k = 2

    # 4. 节点最小间距：避免节点挤得太近
    min_distance = 15

    # 5. 充电站数量
    num_charging_stations = 8

    # 6. 充电站最大排队容量
    charging_queue_limit = 10

    graph = generate_connected_weighted_graph(
        num_nodes=num_nodes,
        width=width,
        height=height,
        extra_k=extra_k,
        min_distance=min_distance
    )

    # 设置中央仓库：自动选择距离画布几何中心最近的点
    graph.set_central_warehouse(width, height)

    # =========================
    # 方式A：自动选充电站（推荐）
    # =========================
    graph.set_charging_stations_auto(
        num_stations=num_charging_stations,
        queue_limit=charging_queue_limit,
        min_station_spacing_ratio=0.14, #0.16  # 站点最小间距比例,调大一点，站点更分散，调小一点，站点更容易聚到中间区域
        middle_ring_low=0.25,           #0.30  # 中圈层下界,调小一点，站点会更靠中心
        middle_ring_high=0.60,          #0.68  # 中圈层上界,调小一点，站点不容易跑到外圈
        max_edge_station_ratio=0.20     #0.25  # 边缘站比例上限,允许边缘站的比例，调小一点，边缘站更少
    )

    # =========================
    # 方式B：手动指定充电站位置
    # 如果要手动指定，就把上面的自动方式注释掉，再启用下面这段
    # =========================
    # manual_positions = [(50, 60), (140, 60), (80, 110), (150, 110)]
    # graph.set_charging_stations_manual(
    #     manual_positions=manual_positions,
    #     queue_limit=charging_queue_limit
    # )

    graph.print_graph_info()

    # 演示充电站排队逻辑
    if graph.charging_station_ids:
        station_id = graph.charging_station_ids[0]
        for _ in range(3):
            graph.vehicle_enter_charging_station(station_id)
        graph.vehicle_leave_charging_station(station_id)

    visualize_graph(graph, show_weights=False)
