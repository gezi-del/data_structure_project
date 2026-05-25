import threading

from flask import Flask, jsonify, render_template, request
try:
    from flask_cors import CORS
except ModuleNotFoundError:
    def CORS(_app):
        return _app

from experiment_runner import run_all_experiments
from simulation_config import SCALE_CONFIGS
from simulation_core import SimulationEngine


app = Flask(__name__)
CORS(app)

engine = SimulationEngine()
threading.Thread(target=engine.run_loop, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scales", methods=["GET"])
def get_scales():
    return jsonify({
        "scales": [
            {
                "key": config.key,
                "label": config.label,
                "nodes": config.num_nodes,
                "vehicles": config.num_vehicles,
                "stations": config.num_stations,
                "duration_seconds": config.duration_seconds,
            }
            for config in SCALE_CONFIGS.values()
        ]
    })


@app.route("/api/start", methods=["POST"])
def start_simulation():
    payload = request.get_json(silent=True) or {}
    scale = payload.get("scale")
    strategy = payload.get("strategy")
    allow_multi_vehicle = payload.get("allow_multi_vehicle")
    use_fixed_seed = payload.get("use_fixed_seed")

    if scale or strategy or allow_multi_vehicle is not None or use_fixed_seed is not None:
        if (
            scale and scale != engine.config.key
        ) or (
            strategy and strategy != engine.strategy
        ) or (
            allow_multi_vehicle is not None
            and bool(allow_multi_vehicle) != engine.allow_multi_vehicle
        ) or (
            use_fixed_seed is not None
            and bool(use_fixed_seed) != engine.use_fixed_seed
        ):
            engine.configure(
                scale_key=scale or engine.config.key,
                strategy=strategy or engine.strategy,
                allow_multi_vehicle=(
                    engine.allow_multi_vehicle
                    if allow_multi_vehicle is None
                    else bool(allow_multi_vehicle)
                ),
                use_fixed_seed=(
                    engine.use_fixed_seed
                    if use_fixed_seed is None
                    else bool(use_fixed_seed)
                ),
            )

    engine.start()
    return jsonify({"status": "running", "state": engine.get_status_payload()})


@app.route("/api/pause", methods=["POST"])
def pause_simulation():
    engine.pause()
    return jsonify({"status": "paused", "state": engine.get_status_payload()})


@app.route("/api/reset", methods=["POST"])
def reset_simulation():
    payload = request.get_json(silent=True) or {}
    engine.reset(
        scale_key=payload.get("scale", engine.config.key),
        strategy=payload.get("strategy", engine.strategy),
        allow_multi_vehicle=payload.get("allow_multi_vehicle", engine.allow_multi_vehicle),
        use_fixed_seed=payload.get("use_fixed_seed", engine.use_fixed_seed),
    )
    return jsonify({"status": "reset", "map": engine.get_map_payload(), "state": engine.get_status_payload()})


@app.route("/api/step", methods=["POST"])
def step_simulation():
    engine.pause()
    engine.step()
    return jsonify({"status": "stepped", "state": engine.get_status_payload()})


@app.route("/api/map", methods=["GET"])
def get_map():
    return jsonify(engine.get_map_payload())


@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify(engine.get_status_payload())


@app.route("/api/experiments", methods=["GET"])
def get_experiments():
    force = request.args.get("force") == "1"
    return jsonify(run_all_experiments(force=force))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
