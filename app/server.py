"""
多彩黔行 —— 后端服务（Flask）
提供：数据接口、行程规划接口、行程分享与反馈接口
运行：python run.py  → http://127.0.0.1:5000
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, render_template, g, send_from_directory

from planner import load_dataset, plan

BASE_DIR = Path(__file__).resolve().parent
# 生产环境可通过环境变量 QX_DB 指向持久化卷，如 /data/app.db
DB_PATH = Path(os.environ.get("QX_DB", BASE_DIR.parent / "data" / "app.db"))

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 请求体上限 1MB
DATASET = load_dataset()


# ---------------- 数据库 ----------------
def get_db() -> sqlite3.Connection:
    """每请求一个连接。WAL 模式 + 忙等超时，保证多 worker 下并发写不报 locked。"""
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=8000")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS itineraries (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            request_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            itinerary_id TEXT,
            rating INTEGER,
            comment TEXT
        );
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            action TEXT,
            payload TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_itineraries_created ON itineraries(created_at);
        CREATE INDEX IF NOT EXISTS idx_event_action ON event_log(action);
        """
    )
    con.commit()
    con.close()


def log_event(action: str, payload: dict) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO event_log(created_at, action, payload) VALUES (?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), action, json.dumps(payload, ensure_ascii=False)),
    )
    db.commit()


# ---------------- 页面 ----------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/s/<sid>")
def share_page(sid: str):
    """分享页：打开即渲染该行程（前端从 /api/share/<sid> 拉取数据）。"""
    return render_template("index.html", share_id=sid)


@app.route("/manifest.json")
def manifest():
    return send_from_directory(BASE_DIR / "static", "manifest.json")


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(BASE_DIR / "static", "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# ---------------- API ----------------
@app.get("/api/meta")
def api_meta():
    """返回城市、主题、标签、景点列表，供前端渲染筛选器。"""
    spots = DATASET["spots"]
    tags: dict[str, int] = {}
    for s in spots:
        for t in s["tags"]:
            tags[t] = tags.get(t, 0) + 1
    return jsonify({
        "cities": DATASET["cities"],
        "themes": DATASET["themes"],
        "tags": sorted(tags.items(), key=lambda kv: -kv[1]),
        "spots": spots,
        "counts": {"spots": len(spots), "stays": len(DATASET["stays"]), "foods": len(DATASET["foods"])},
    })


@app.post("/api/plan")
def api_plan():
    body = request.get_json(force=True, silent=True) or {}
    # 参数校验（服务端二次校验，防止异常输入）
    try:
        days = int(body.get("days", 3))
        people = int(body.get("people", 2))
        budget = int(body.get("budget", 3000))
    except (TypeError, ValueError):
        return jsonify({"error": "参数类型错误：days/people/budget 必须为整数"}), 400
    if not 1 <= days <= 10:
        return jsonify({"error": "天数需在 1-10 之间"}), 400
    if not 1 <= people <= 20:
        return jsonify({"error": "人数需在 1-20 之间"}), 400
    if not 500 <= budget <= 200000:
        return jsonify({"error": "预算需在 500-200000 元之间"}), 400

    prefs = {
        "days": days,
        "people": people,
        "budget": budget,
        "tags": body.get("tags", [])[:6],
        "themeIds": body.get("themeIds", [])[:3],
        "mode": body.get("mode", "public"),
        "baseCity": body.get("baseCity", "gy"),
        "season": body.get("season", "autumn"),
        "budgetLevel": body.get("budgetLevel", "mid"),
        "maxHoursPerDay": float(body.get("maxHoursPerDay", 10)),
        "fixedSpotIds": body.get("fixedSpotIds", [])[:8],
        "preferNiche": bool(body.get("preferNiche", False)),
    }
    result = plan(prefs, DATASET)
    log_event("plan", {"days": days, "people": people, "budget": budget, "mode": prefs["mode"]})
    return jsonify(result)


@app.post("/api/share")
def api_share():
    body = request.get_json(force=True, silent=True) or {}
    result = body.get("result")
    if not result:
        return jsonify({"error": "缺少行程数据"}), 400
    sid = uuid.uuid4().hex[:10]
    db = get_db()
    db.execute(
        "INSERT INTO itineraries(id, created_at, request_json, result_json) VALUES (?,?,?,?)",
        (sid, datetime.now().isoformat(timespec="seconds"),
         json.dumps(body.get("request", {}), ensure_ascii=False),
         json.dumps(result, ensure_ascii=False)),
    )
    db.commit()
    log_event("share", {"id": sid})
    return jsonify({"id": sid, "url": f"/s/{sid}"})


@app.get("/api/share/<sid>")
def api_get_share(sid: str):
    db = get_db()
    row = db.execute("SELECT * FROM itineraries WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({"error": "行程不存在或已过期"}), 404
    db.execute("UPDATE itineraries SET views = views + 1 WHERE id=?", (sid,))
    db.commit()
    return jsonify({
        "id": row["id"],
        "createdAt": row["created_at"],
        "views": row["views"] + 1,
        "likes": row["likes"],
        "request": json.loads(row["request_json"]),
        "result": json.loads(row["result_json"]),
    })


@app.post("/api/share/<sid>/like")
def api_like(sid: str):
    db = get_db()
    db.execute("UPDATE itineraries SET likes = likes + 1 WHERE id=?", (sid,))
    db.commit()
    row = db.execute("SELECT likes FROM itineraries WHERE id=?", (sid,)).fetchone()
    return jsonify({"likes": row["likes"] if row else 0})


@app.post("/api/feedback")
def api_feedback():
    body = request.get_json(force=True, silent=True) or {}
    rating = int(body.get("rating", 0))
    comment = str(body.get("comment", ""))[:500]
    if not 1 <= rating <= 5:
        return jsonify({"error": "评分需在 1-5 之间"}), 400
    db = get_db()
    db.execute(
        "INSERT INTO feedback(created_at, itinerary_id, rating, comment) VALUES (?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), body.get("itineraryId"), rating, comment),
    )
    db.commit()
    avg = db.execute("SELECT ROUND(AVG(rating),2) a, COUNT(*) c FROM feedback").fetchone()
    return jsonify({"ok": True, "avgRating": avg["a"], "count": avg["c"]})


@app.get("/api/health")
def api_health():
    return jsonify({"status": "ok", "spots": len(DATASET["spots"]),
                    "time": datetime.now().isoformat(timespec="seconds")})


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "接口不存在"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "服务器内部错误", "detail": str(e)}), 500


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
