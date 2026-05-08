from flask import Flask, jsonify, render_template
from flask_cors import CORS
import threading
import time

from Graph import generate_connected_weighted_graph
from Fleet_Controller import FleetController
from Vehicle import Vehicle
from Task_Manager import TaskManager

app = Flask(__name__)
CORS(app) # 允许前端跨域访问

class SimulationEngine:
    """模拟引擎：负责维护整个系统的状态"""
    def __init__(self):
        self.width, self.height = 200, 200
        self.sim_seconds_per_tick = 1.0
        self.time_scale = 5.0
        self.real_seconds_per_tick = self.sim_seconds_per_tick / self.time_scale
        print("正在构建城市配送网络...")
        # 初始化地图
        self.graph = generate_connected_weighted_graph(
            num_nodes=40, 
            width=self.width, 
            height=self.height, 
            min_distance=15
        )
        self.warehouse_id = self.graph.set_central_warehouse(self.width, self.height)
        print(f"中央仓库已设在节点：{self.warehouse_id}")
        self.graph.set_charging_stations_auto(num_stations=6, queue_limit=6)
        # 初始化任务管理器
        self.task_manager = TaskManager(self.graph, max_tasks_limit=15)
        # 初始化车队 (假设有15辆车，初始都在仓库)
        self.vehicles = []
        for i in range(15):
            v = Vehicle(width=self.width) # 给车辆增加一个实时位置属性（节点ID）
            v.current_node_id = self.warehouse_id
            v.status = "idle"# 增加一个状态属性：idle, moving, charging, loading
            self.vehicles.append(v)

        self.controller = FleetController(
            graph=self.graph,
            task_manager=self.task_manager,
            vehicles=self.vehicles,
            warehouse_id=self.warehouse_id,
            strategy="nearest",
            allow_multi_vehicle=True,
            tick_seconds=self.sim_seconds_per_tick,
        )
            
        self.current_tick = 0
        self.is_running = False
        self.logs = [] # 存储模拟日志

    def step(self):
        """执行一个时间步"""
        # 1. 生成新任务
        new_tasks = self.task_manager.step_generate(self.current_tick)
        
        if new_tasks:
            for i in new_tasks:
                log_msg = f"[{self.current_tick}s] ⚡ 新任务: 目的地 {i.target_id}, 重量 {i.weight:.1f}kg"
                print(log_msg)
                self.logs.append(log_msg)
        if self.current_tick % 5 == 0:
            pending = self.task_manager.get_pending_tasks()
            status_msg = f">>> 时间：{self.current_tick}s | 任务池积压：{len(pending)} 个"
            print(status_msg)
            self.logs.append(status_msg)
        self.controller.step(self.current_tick)
        # 预留算法空间
        self.current_tick += self.sim_seconds_per_tick

    def run_loop(self):
        """后台运行线程"""
        print(f"\n开始后台模拟...")
        self.is_running = True
        while self.is_running:
            self.step()
            time.sleep(self.real_seconds_per_tick) # 调整与现实时间的比例

# 实例化引擎
engine = SimulationEngine()
# 启动后台模拟线程
threading.Thread(target=engine.run_loop, daemon=True).start()

# 开始接口
@app.route('/api/start', methods=['POST'])
def start_simulation():
    engine.is_running = True
    return jsonify({"status": "running", "message": "Simulation started"})

@app.route('/')
def index():
    """访问根路径时，返回前端界面"""
    return render_template('index.html')

@app.route('/api/map', methods=['GET'])
def get_map():
    """获取静态地图数据"""
    nodes = []
    for n in engine.graph.nodes.values():
        nodes.append({
            "id": n.id, 
            "x": n.x, 
            "y": n.y, 
            "type": n.type
        })
    
    links = []
    for u in engine.graph.adj:
        for v, weight in engine.graph.adj[u].items():
            if u < v: 
                links.append({"source": u, "target": v, "weight": round(weight, 2)})
    
    return jsonify({
        "width": engine.width,
        "height": engine.height,
        "nodes": nodes,
        "links": links,
        "warehouse_id": engine.warehouse_id
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取实时的车辆和任务状态"""
    def _vehicle_position(vehicle, state):
        node = engine.graph.nodes[vehicle.current_node_id]
        x, y = node.x, node.y

        if not state or vehicle.status != "moving":
            return x, y
        if not state.route or state.route_index >= len(state.route) - 1:
            return x, y

        current_id = state.route[state.route_index]
        next_id = state.route[state.route_index + 1]
        edge_dist = engine.graph.adj[current_id].get(next_id)
        if not edge_dist or edge_dist <= 0:
            return x, y

        remaining = max(0.0, state.distance_to_next)
        progress = min(1.0, max(0.0, (edge_dist - remaining) / edge_dist))
        current_node = engine.graph.nodes[current_id]
        next_node = engine.graph.nodes[next_id]
        x = current_node.x + (next_node.x - current_node.x) * progress
        y = current_node.y + (next_node.y - current_node.y) * progress
        return x, y

    task_lookup = {t.id: t for t in engine.task_manager.tasks}
    # 车辆信息
    vehicle_list = []
    for idx, v in enumerate(engine.vehicles):
        state = engine.controller.vehicle_states.get(idx)
        pos_x, pos_y = _vehicle_position(v, state)
        task_info = None
        if state and state.task_id is not None:
            task = task_lookup.get(state.task_id)
            if task:
                meta = engine.controller.task_meta.get(task.id, {})
                task_info = {
                    "id": task.id,
                    "target_id": task.target_id,
                    "weight": round(task.weight, 1),
                    "status": task.status,
                    "appear_time": task.appear_time,
                    "assigned_load": round(state.assigned_load, 1),
                    "remaining_weight": round(meta.get("remaining_weight", task.weight), 1),
                }
        vehicle_list.append({
            "id": idx,
            "battery": round(v.current_battery, 1),
            "max_battery": round(v.battery_capacity, 1),
            "load": round(v.current_load, 1),
            "node_id": v.current_node_id,
            "status": v.status,
            "mission": state.mission if state else "idle",
            "task": task_info,
            "x": round(pos_x, 2),
            "y": round(pos_y, 2)
        })
    # 任务信息
    active_tasks = [
        {
            "id": t.id,
            "target_id": t.target_id,
            "weight": round(t.weight, 1),
            "appear_time": t.appear_time,
            "status": t.status,
            "remaining_weight": round(
                engine.controller.task_meta.get(t.id, {}).get("remaining_weight", t.weight),
                1
            ),
            "coords": t.coords
        }
        for t in engine.task_manager.tasks if t.status != "completed"
    ]
    
    return jsonify({
        "tick": engine.current_tick,
        "vehicles": vehicle_list,
        "tasks": active_tasks,
        "width": engine.width,
        "height": engine.height,
        "warehouse_id": engine.warehouse_id  # 这一行至关重要
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
