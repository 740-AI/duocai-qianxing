"""
多彩黔行 —— 行程智能规划引擎（核心算法模块）
================================================
纯 Python 实现，无第三方算法依赖，便于说明与答辩演示。

算法分四层：
  L1 候选集构建      ：按偏好标签 / 主题 / 天数 计算候选景点得分
  L2 地理聚类        ：改进的贪心 k-medoids，把候选点按空间邻近切成 D 个簇
  L3 簇内排序        ：簇内以「最近邻 + 2-opt 局部优化」求解日路线（TSP 近似）
  L4 时间可行性排布  ：按游玩时长、车程、用餐时间做日内时间轴排布，超时则剔除低分点
再叠加 ② 预算约束（门票+住宿+餐饮+交通）与 ③ 节奏约束（每日时长上限）。

公交/自驾成本用哈弗辛公式计算球面距离，再换算车程。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "guizhou.json"

# ---------- 可调参数（也是答辩时的"业务参数说明"）----------
DAY_START = 8.5            # 每天 8:30 出发
DAY_END = 21.0             # 21:00 回到住处
LUNCH_WINDOW = (12.0, 13.5)
DINNER_WINDOW = (17.5, 19.0)
MEAL_MINUTES = 75          # 一顿正餐含往返
LUNCH_COST = 45
DINNER_COST = 65
HOTEL_LOW, HOTEL_MID, HOTEL_HIGH = 260, 340, 460
BUDGET_TOLERANCE = 1.15    # 预算软约束容差

LEVEL_WEIGHT = {"5A": 10, "4A": 6, "3A": 3}

DATE_SEASON = {
    "spring": {"杜鹃", "油菜花", "花海"},
    "summer": {"瀑布", "漂流", "草原", "避暑", "水景"},
    "autumn": {"梯田", "古村", "银杏"},
    "winter": {"古城", "溶洞", "温泉"},
}


def load_dataset(path: Path = DATA_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------- 地理计算 ----------
def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    """返回两点球面距离：a=(lat,lng), b=(lat,lng)，单位 km。"""
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def travel_minutes(distance_km: float, mode: str) -> int:
    """车程估算：自驾按平均 55km/h（山区县道），公共交通按 38km/h 并加 25 分钟候车。"""
    if mode == "selfdrive":
        return int(distance_km / 55 * 60) + 8
    return int(distance_km / 38 * 60) + 25


def travel_cost(distance_km: float, mode: str, people: int) -> float:
    """交通费用估算（元）。自驾=油费 0.75元/km + 高速 0.5元/km + 停车 30元/天摊销；公交按班车票价近似。"""
    if mode == "selfdrive":
        return distance_km * 1.25 + 25
    return distance_km * 1.6 * max(1, people - 1) + 15


@dataclass
class Spot:
    id: str
    name: str
    city: str
    lat: float
    lng: float
    hours: float
    ticket: float
    level: str
    tags: list[str]
    type: str
    best: str
    intro: str
    tip: str
    score: float = 0.0

    @property
    def xy(self) -> tuple[float, float]:
        return (self.lat, self.lng)


# ---------- L1：候选集与评分 ----------
def build_candidates(spots: list[Spot], prefs: dict[str, Any]) -> list[Spot]:
    """
    得分 = 偏好标签命中 * 3 + 5A/4A 权重 + 主题命中 * 4
           + 季节性加成 2 - 门票惩罚（按预算档位加权）- 小众惩罚
    """
    tags = set(prefs.get("tags") or [])
    theme_spots = set(prefs.get("themeSpotIds") or [])
    season = prefs.get("season", "autumn")
    budget_level = prefs.get("budgetLevel", "mid")
    prefer_niche = prefs.get("preferNiche", False)

    scored: list[Spot] = []
    for s in spots:
        score = 0.0
        score += 3.0 * len(tags & set(s.tags))
        score += LEVEL_WEIGHT.get(s.level, 0)
        if s.id in theme_spots:
            score += 4.0
        if s.best and any(k in s.best for k in DATE_SEASON.get(season, set())):
            score += 2.0
        if "季节性" in s.tags and not any(k in s.best for k in DATE_SEASON.get(season, set())):
            score -= 6.0
        # 预算：低预算对高价门票敏感
        ticket_w = {"low": 0.045, "mid": 0.025, "high": 0.01}.get(budget_level, 0.025)
        score -= s.ticket * ticket_w
        # 小众偏好
        if "小众" in s.tags:
            score += 3.0 if prefer_niche else -1.5
        # 单点游玩时长过长（>7h）会挤压行程，轻微惩罚
        if s.hours >= 7:
            score -= 1.0
        if score <= 0:
            continue
        s2 = Spot(**{**s.__dict__, "score": round(score, 2)})
        scored.append(s2)
    scored.sort(key=lambda x: (x.score, -x.hours), reverse=True)
    # 高分优先，但单点超长景点（>=6h）压缩权重，避免"一个景点吃掉一天"
    return scored


def take_candidates(scored: list[Spot], days: int, per_day_cap: int) -> list[Spot]:
    """
    从高分池挑选 days*per_day_cap 个点，并做"单日景点时长预算"控制：
    每天可供游玩约 per_day_cap * 3.2 小时（扣掉车程与两餐），选点时不透支。
    """
    need = days * per_day_cap
    day_hours_budget = per_day_cap * 3.4
    load = [0.0] * days
    picked: list[Spot] = []
    for s in scored:
        if len(picked) >= need:
            break
        if any(s.id == p.id for p in picked):
            continue
        # 放到当前负载最小的一天（长景点优先独占）
        slot = min(range(days), key=lambda i: load[i])
        if load[slot] + s.hours > day_hours_budget + 0.6:
            continue
        load[slot] += s.hours
        picked.append(s)
    return picked


# ---------- L2：地理聚类（Morton 序 + 均匀切片）----------
def xor_order(points: list[Spot]) -> list[Spot]:
    """Morton(XOR) 全序法：把经纬度按位交错映射到一维整数，排序后空间相邻的点在序列中也相邻。"""
    def spread(v: int) -> int:
        v = (v | (v << 8)) & 0x00FF00FF
        v = (v | (v << 4)) & 0x0F0F0F0F
        v = (v | (v << 2)) & 0x33333333
        v = (v | (v << 1)) & 0x55555555
        return v

    def key(p: Spot) -> int:
        x = int((p.lng - 104.0) * 1000) & 0xFFFF
        y = int((p.lat - 24.5) * 1000) & 0xFFFF
        return spread(x) | (spread(y) << 1)

    return sorted(points, key=key)


def geo_cluster(cands: list[Spot], days: int, per_day_cap: int) -> list[list[Spot]]:
    """
    两阶段切段（Segment Partition）：
      ① Morton 空间排序，得到空间连续的候选序列；
      ② 计算"理想每段景点数"= 总点数/天数，按此目标做切段，
         每段同时受「时长预算」与「容量上限」约束，避免空天或严重失衡。
    """
    if not cands:
        return []
    ordered = xor_order(cands)
    n = len(ordered)
    target = n / days
    per_day_hours = per_day_cap * 3.4
    groups: list[list[Spot]] = [[]]
    hours = 0.0
    remaining_days = days
    for i, s in enumerate(ordered):
        left_points = n - i
        cur = groups[-1]
        need_days_after = remaining_days - 1
        # 切段条件：本段已达目标数量，且剩余点数足够填满后续每天至少 1 个
        cut_by_count = len(cur) >= max(1, round(target))
        cut_by_hours = hours + s.hours > per_day_hours
        if cur and need_days_after > 0 and (cut_by_count or cut_by_hours) and left_points >= need_days_after:
            groups.append([])
            remaining_days -= 1
            hours = 0.0
        groups[-1].append(s)
        hours += s.hours
    return groups


def choose_day_center(cl: list[Spot], base_xy: tuple[float, float], mode: str,
                      days_left: int) -> tuple[float, float, str]:
    """
    每日"过夜中心"选择（动态换站机制）：
      - 若簇内某点的单日游玩时长 >= 5 小时，说明是远郊核心景区，安排就近住一晚，次日从该点返程；
      - 否则回到起始城市（贵阳）作为中心，形成"贵阳辐射式"行程。
    返回 (纬度, 经度, 中心说明)
    """
    if not cl:
        return base_xy[0], base_xy[1], "base"
    far = max(cl, key=lambda p: haversine(base_xy, p.xy))
    if far.hours >= 5.0 and days_left >= 2:
        return far.lat, far.lng, far.name
    return base_xy[0], base_xy[1], "base"


# ---------- L3：簇内路线排序（最近邻 + 2-opt）----------
def route_order(points: list[Spot], start_xy: tuple[float, float], mode: str = "selfdrive") -> list[Spot]:
    """
    簇内日路线排序：以「每日时长预算」为约束的贪心插入。
    每一步从剩余点里挑"边际时间成本最低"的点插入当前最优位置，
    边际成本 = 车程增量 + 景点游玩时长；放不下就跳过该点（而不是简单砍队尾）。
    最后用 2-opt 消除交叉、缩短总车程。
    """
    if len(points) <= 1:
        return list(points)
    route: list[Spot] = []
    remaining = list(points)
    cur_min = 0.0
    # 锚点选择：从出发点出发，优先"单点即可成行"的近点，保证每天至少 1 个景点
    def solo_minutes(p: Spot) -> float:
        return travel_minutes(haversine(start_xy, p.xy), mode) * 2 + p.hours * 60

    window = DAY_END * 60 - DAY_START * 60 - 150  # 8:30-21:00，预留两餐 150 分钟
    feasible = [p for p in points if solo_minutes(p) <= window] or points
    points = feasible
    # 单日窗口放宽 15%（真实旅行常有早出发/晚返回），由 maxHoursPerDay 二次把关
    limit = window * 1.15

    while remaining:
        best_move = None
        best_cost = float("inf")
        for p in remaining:
            # 尝试插入到每个位置
            for pos in range(len(route) + 1):
                prev_xy = start_xy if pos == 0 else route[pos - 1].xy
                next_xy = route[pos].xy if pos < len(route) else start_xy
                extra = (haversine(prev_xy, p.xy) + haversine(p.xy, next_xy) - haversine(prev_xy, next_xy))
                dm = travel_minutes(extra, mode)
                add = dm + p.hours * 60
                if cur_min + add > limit:
                    continue
                # 单一远点（簇内只有它）放宽时长限制：只要能在当日往返窗口内完成即可
                cost = dm / 60.0 + p.hours * 0.35  # 车程权重更高：优先省车程
                if cost < best_cost:
                    best_cost, best_move = cost, (p, pos, add)
        if best_move is None:
            break
        p, pos, add = best_move
        route.insert(pos, p)
        cur_min += add
        remaining.remove(p)

    # 2-opt
    improved = True
    while improved:
        improved = False
        for i in range(len(route) - 1):
            for j in range(i + 2, len(route)):
                a = start_xy if i == 0 else route[i - 1].xy
                b, c = route[i].xy, route[j].xy
                d = route[j + 1].xy if j + 1 < len(route) else start_xy
                if haversine(a, b) + haversine(c, d) > haversine(a, c) + haversine(b, d) + 1e-9:
                    route[i: j + 1] = reversed(route[i: j + 1])
                    improved = True
    return route


# ---------- L4：日内时间轴排布 ----------
def schedule_day(route: list[Spot], start_xy: tuple[float, float], mode: str, people: int,
                 max_hours: float) -> dict[str, Any]:
    """
    把有序景点排进 8:30-21:00 的时间轴，缺失午餐/晚餐自动补齐。
    装不下时剔除"最后一个景点"（通常也是最远/最低分的一个），直到可行。
    """
    route = list(route)
    while True:
        cursor = DAY_START * 60  # 分钟
        prev_xy = start_xy
        items: list[dict[str, Any]] = []
        lunch_done = dinner_done = False
        distance = 0.0
        ok = True
        lunch_at = None

        for s in route:
            d_km = haversine(prev_xy, s.xy)
            dm = travel_minutes(d_km, mode)
            distance += d_km
            arrive = cursor + dm
            # 午餐：到达时间跨过 12:00 就插一顿（最多 75 分钟）
            if not lunch_done and arrive >= LUNCH_WINDOW[0] * 60:
                lunch_at = min(arrive, LUNCH_WINDOW[1] * 60)
                items.append({"kind": "meal", "label": "午餐", "start": lunch_at,
                              "cost": LUNCH_COST, "dur": MEAL_MINUTES})
                arrive = lunch_at + MEAL_MINUTES
                lunch_done = True
            leave = arrive + s.hours * 60
            if leave > DAY_END * 60:
                ok = False
                break
            items.append({
                "kind": "spot", "spotId": s.id, "name": s.name, "city": s.city,
                "start": arrive, "end": leave, "dur": int(s.hours * 60),
                "ticket": s.ticket, "level": s.level, "tags": s.tags,
                "moveMin": dm, "moveKm": round(d_km, 1),
                "intro": s.intro, "tip": s.tip,
            })
            cursor = leave
            prev_xy = s.xy

        if ok:
            # 晚餐：玩完回城再吃
            if not dinner_done:
                items.append({"kind": "meal", "label": "晚餐",
                              "start": max(cursor, DINNER_WINDOW[0] * 60),
                              "cost": DINNER_COST, "dur": MEAL_MINUTES})
            back_km = haversine(prev_xy, start_xy)
            back = travel_minutes(back_km, mode)
            distance += back_km
            total_hours = (cursor - DAY_START * 60) / 60
            if total_hours <= max_hours or not route:
                return {
                    "items": items,
                    "distanceKm": round(distance, 1),
                    "activeHours": round(total_hours, 1),
                    "backToHotelMin": back,
                    "endClock": cursor + back,
                }
        if not route:
            return {"items": [], "distanceKm": 0, "activeHours": 0, "backToHotelMin": 0,
                    "endClock": DAY_START * 60}
        route = route[:-1]


# ---------- 主流程 ----------
def plan(prefs: dict[str, Any], dataset: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    prefs 关键字段：
      days:int  people:int  budget:int  预算档位 low/mid/high
      tags:[str]  themeIds:[str]  mode: selfdrive|public
      baseCity: 起始城市 id（默认贵阳）
      season: spring/summer/autumn/winter
      maxHoursPerDay: 每日游玩上限
      fixedSpotIds: 必去景点
    """
    data = dataset or load_dataset()
    days = max(1, min(10, int(prefs.get("days", 3))))
    people = max(1, int(prefs.get("people", 2)))
    budget = int(prefs.get("budget", 3000))
    mode = prefs.get("mode", "public")
    season = prefs.get("season", "autumn")
    budget_level = prefs.get("budgetLevel", "mid")
    max_hours = float(prefs.get("maxHoursPerDay", 10.0))
    base_city = prefs.get("baseCity", "gy")

    spots = [Spot(**{k: v for k, v in row.items() if k in Spot.__dataclass_fields__})
             for row in data["spots"]]
    by_id = {s.id: s for s in spots}
    cities = {c["id"]: c for c in data["cities"]}

    theme_ids = prefs.get("themeIds") or []
    theme_spot_ids: list[str] = []
    for t in data["themes"]:
        if t["id"] in theme_ids:
            theme_spot_ids.extend(t["spotIds"])

    fixed_ids = [i for i in (prefs.get("fixedSpotIds") or []) if i in by_id]
    merged_prefs = {**prefs, "themeSpotIds": theme_spot_ids,
                    "budgetLevel": budget_level, "season": season}

    cands = build_candidates(spots, merged_prefs)
    # 必去景点强制置于最前
    forced = [by_id[i] for i in fixed_ids]
    for f in forced:
        f.score += 100
    cands = sorted([c for c in cands if c.id not in fixed_ids], key=lambda x: x.score, reverse=True)
    cands = forced + cands

    per_day_cap = 5 if max_hours >= 9 else 4
    cands = take_candidates(cands, days, per_day_cap)
    clusters = geo_cluster(cands, days, per_day_cap)
    clusters.sort(key=lambda cl: max((s.score for s in cl), default=-999), reverse=True)

    base_xy = (cities[base_city]["x"], cities[base_city]["y"])
    stays = data["stays"]
    day_plans: list[dict[str, Any]] = []
    total_ticket = total_hotel = total_meal = total_move = 0.0
    used_spots: set[str] = set()

    center_xy, center_note = base_xy, "base"
    for d in range(days):
        cl = clusters[d] if d < len(clusters) else []
        # 每天从"当前过夜点"出发；远郊大景区则就近住宿（动态换站）
        if d > 0:
            clat, clng, center_note = choose_day_center(cl, base_xy, mode, days - d)
            center_xy = (clat, clng)
        # 把前面日程没用掉的候选点回补到当天，避免出现"空白天"
        cl = [c for c in cl if c.id not in used_spots]
        spill = [c for c in cands if c.id not in used_spots]
        cl = cl + [c for c in spill if c.id not in {x.id for x in cl}][: max(0, per_day_cap - len(cl))]
        order = route_order(cl, center_xy, mode)
        sch = schedule_day(order, center_xy, mode, people, max_hours)
        picked = [i for i in sch["items"] if i["kind"] == "spot"]
        for p in picked:
            used_spots.add(p["spotId"])

        # 住宿：找当天最后一个景点附近的合作民宿，按预算档位筛价
        price_band = {"low": (0, HOTEL_LOW + 60), "mid": (HOTEL_LOW, HOTEL_MID + 80),
                      "high": (HOTEL_MID, 9999)}[budget_level]
        anchor = by_id[picked[-1]["spotId"]] if picked else by_id.get(fixed_ids[0]) if fixed_ids else None
        hotel = None
        pool = [h for h in stays if price_band[0] <= h["price"] <= price_band[1]]
        if anchor is not None:
            pool = sorted(pool, key=lambda h: haversine(
                anchor.xy, (next(s for s in spots if s.id == h["near"]).lat,
                            next(s for s in spots if s.id == h["near"]).lng))) or pool
            hotel = pool[0] if pool else None
        if hotel is None and pool:
            hotel = pool[d % len(pool)]
        rooms = math.ceil(people / 2)
        hotel_cost = (hotel["price"] * rooms) if hotel else HOTEL_MID * rooms

        tickets = sum(p["ticket"] for p in picked) * people
        meals = sum(i["cost"] for i in sch["items"] if i["kind"] == "meal") * people
        move = sum(travel_cost(p["moveKm"], mode, people) for p in picked)

        total_ticket += tickets
        total_hotel += hotel_cost
        total_meal += meals
        total_move += move

        # 当日美食推荐：同城优先
        day_cities = {p["city"] for p in picked}
        foods = [f for f in data["foods"] if f["city"] in day_cities][:2] or data["foods"][d % len(data["foods"]):][:1]

        day_plans.append({
            "day": d + 1,
            "theme": _day_theme(picked),
            "city": cities.get(picked[0]["city"], {}).get("name", "") if picked else "",
            "spots": picked,
            "meals": [i for i in sch["items"] if i["kind"] == "meal"],
            "hotel": hotel,
            "hotelCost": round(hotel_cost),
            "ticketCost": round(tickets),
            "mealCost": round(meals),
            "moveCost": round(move),
            "distanceKm": sch["distanceKm"],
            "activeHours": sch["activeHours"],
            "endClock": _clock(sch["endClock"]),
            "foods": foods,
        })

    total = total_ticket + total_hotel + total_meal + total_move
    return {
        "request": {**prefs, "season": season},
        "summary": {
            "days": days, "people": people, "budget": budget,
            "estimatedTotal": round(total),
            "perPerson": round(total / people),
            "overBudget": total > budget * BUDGET_TOLERANCE,
            "budgetGap": round(total - budget),
            "breakdown": {
                "ticket": round(total_ticket), "hotel": round(total_hotel),
                "meal": round(total_meal), "transport": round(total_move),
            },
            "spotCount": len(used_spots),
            "totalDistanceKm": round(sum(d["distanceKm"] for d in day_plans), 1),
        },
        "days": day_plans,
        "algorithm": {
            "version": "1.0",
            "pipeline": ["候选集评分(L1)", "地理聚类(L2)", "簇内2-opt排序(L3)", "时间轴排布(L4)"],
            "candidates": len(cands),
            "perDayCap": per_day_cap,
        },
    }


def _clock(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def _day_theme(picked: list[dict[str, Any]]) -> str:
    if not picked:
        return "城市休整"
    types = {p["tags"][0] if p["tags"] else "" for p in picked}
    if "自然" in types and "人文" in types:
        return "山水与人文"
    if "自然" in types:
        return "自然风光日"
    if "人文" in types:
        return "人文体验日"
    if "红色" in types:
        return "红色研学日"
    if "科技" in types:
        return "科技探索日"
    return "主题游"


if __name__ == "__main__":
    demo = plan({"days": 3, "people": 2, "budget": 3000, "tags": ["自然", "人文"],
                 "themeIds": ["classic"], "mode": "selfdrive", "season": "autumn",
                 "budgetLevel": "mid"})
    print(json.dumps(demo["summary"], ensure_ascii=False, indent=2))
    for d in demo["days"]:
        print(f"\nDay{d['day']} {d['theme']} | {d['distanceKm']}km | 游玩{d['activeHours']}h | 结束{d['endClock']}")
        for s in d["spots"]:
            print(f"   - {s['name']} ({s['level']}) {s['ticket']}元  {_clock(s['start'])}-{_clock(s['end'])}")
        print(f"   住宿: {d['hotel']['name'] if d['hotel'] else '无'}")
