#!/usr/bin/env python3
"""
A-B 区段列车运行图编制程序
==============================
基于题目 4.11 数据，完成：
  1. 平行运行图通过能力计算
  2. 非平行运行图通过能力计算
  3. 列车运行图铺画（可视化）
  4. 运行图质量指标计算

输出：控制台结果 + 运行图 PNG 图片
"""

import math
import sys, io

# 修复 Windows 控制台 GBK 编码问题
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
import numpy as np

# ============================================================
# 第一部分：基础数据
# ============================================================

# 车站列表（A→B 下行方向）
STATIONS = ["A", "a", "b", "c", "d", "e", "B"]
N_STATIONS = len(STATIONS)

# 区间距离 (km) — 6个区间：A-a, a-b, b-c, c-d, d-e, e-B
DISTANCES = [13, 15, 10, 12, 16, 10]   # e-B 距离约10km
TOTAL_DISTANCE = sum(DISTANCES)  # 76 km

# 下行（A→B，重车方向）纯运行时分 (min)
DOWN_RUNNING = [21, 18, 15, 20, 24, 13]

# 上行（B→A，空车方向）纯运行时分 (min)
UP_RUNNING = [17, 15, 12, 16, 23, 10]

# 各站股道数
TRACKS = [5, 3, 2, 3, 3, 2, 5]

# 起车附加时分 (min)
T_START = 2
# 停车附加时分 (min)
T_STOP = 1
# 起停附加时分合计
T_QITING = T_START + T_STOP  # 3 min

# 车站间隔时间 (min) — 不同时到达/会车间隔
TAU_UNSIM = 4   # 不同时到达间隔 τ不
TAU_MEET = 3    # 会车间隔 τ会
TAU_STOP = 2    # 停车间隔

# 列车停站时间 (min)
STOP_PASSENGER = 2   # 旅客列车停站
STOP_FREIGHT = 5     # 货物列车停站（技术作业）
STOP_PICKUP = 15     # 摘挂列车停站（调车作业）

# 天窗时间 (min)
T_MAINTENANCE = 60   # 综合维修天窗

# ============================================================
# 第二部分：列车数据
# ============================================================

# 旅客列车 2 对
PASSENGER_TRAINS = [
    {"id": "K775", "dir": "down", "depart": 9*60 + 20, "from": "A"},   # 9:20 A→B
    {"id": "K777", "dir": "down", "depart": 17*60 + 20, "from": "A"},  # 17:20 A→B
    {"id": "K776", "dir": "up",   "depart": 13*60 + 10, "from": "B"},  # 13:10 B→A
    {"id": "K778", "dir": "up",   "depart": 21*60 + 0,  "from": "B"},  # 21:00 B→A
]
N_PASSENGER = len(PASSENGER_TRAINS) // 2  # 2 对

# 货物列车（下行 A→B，重车方向）
FREIGHT_DOWN = {
    "直达(空)": 3,      # 车次范围 86001-86997
    "区段": 5,          # 车次范围 30001-39997
    "摘挂": 2,          # 车次范围 40001-44997
}
# 货物列车（上行 B→A，空车方向）
FREIGHT_UP = {
    "直达(重)": 3,      # 车次范围 10002-19998
    "区段": 5,          # 车次范围 30002-39998
    "摘挂": 1,          # 车次范围 40002-44998
}

TOTAL_FREIGHT_DOWN = sum(FREIGHT_DOWN.values())
TOTAL_FREIGHT_UP = sum(FREIGHT_UP.values())
N_FREIGHT = max(TOTAL_FREIGHT_DOWN, TOTAL_FREIGHT_UP)  # 取大值作为对数

# 扣除系数
EPSILON_PASSENGER = 1.3   # ε客
EPSILON_FAST_FREIGHT = 1.6  # ε货（快货）
EPSILON_PICKUP = 1.5      # ε摘挂（追加扣除）

# 货运机车数量
N_LOCOMOTIVES = 4

# B站直达列车一次作业时间（空车到达到重车出发）
B_STATION_OPERATION_TIME = 5 * 60  # 5 小时 = 300 min

# A站机车折返时间
A_LOCO_TURNAROUND = 2.0 * 60  # 2.0 小时 = 120 min
# B站机车折返时间
B_LOCO_TURNAROUND = 1.5 * 60  # 1.5 小时 = 90 min


def get_running_time(direction, section_idx):
    """获取指定方向、指定区间的纯运行时分"""
    if direction == "down":
        return DOWN_RUNNING[section_idx]
    else:
        return UP_RUNNING[section_idx]


def get_distance(section_idx):
    """获取区间距离"""
    return DISTANCES[section_idx]


# ============================================================
# 第三部分：平行运行图通过能力计算
# ============================================================

def calc_restrictive_section():
    """
    计算限制区间（T_运 + τ_起停 最大的区间）
    对于单线半自动闭塞，限制区间决定了平行运行图通过能力
    """
    section_data = []
    for i in range(N_STATIONS - 1):
        t_down = DOWN_RUNNING[i]
        t_up = UP_RUNNING[i]
        # 区间运行时分 + 起停附加
        t_down_total = t_down + T_QITING
        t_up_total = t_up + T_QITING
        # 一对列车占用区间周期
        t_period = t_down_total + t_up_total + TAU_UNSIM + TAU_MEET
        section_data.append({
            "section": f"{STATIONS[i]}-{STATIONS[i+1]}",
            "distance": DISTANCES[i],
            "t_down": t_down,
            "t_up": t_up,
            "t_down_total": t_down_total,
            "t_up_total": t_up_total,
            "t_period": t_period,
        })
    return section_data


def calc_parallel_capacity():
    """
    计算平行运行图通过能力
    N_平行 = (1440 - T_天窗) × n_周期 / T_周期限制

    对于单线成对非追踪运行图（半自动闭塞）：
    N_平行 = (1440 - T_天窗) / T_周期限制
    """
    sections = calc_restrictive_section()
    # 找出限制区间（T_周期最大）
    restrictive = max(sections, key=lambda s: s["t_period"])

    available_time = 1440 - T_MAINTENANCE
    n_parallel = available_time / restrictive["t_period"]

    return {
        "available_time": available_time,
        "restrictive_section": restrictive["section"],
        "restrictive_period": restrictive["t_period"],
        "n_parallel_float": n_parallel,
        "n_parallel": math.floor(n_parallel),
        "section_details": sections,
    }


# ============================================================
# 第四部分：非平行运行图通过能力计算
# ============================================================

def calc_non_parallel_capacity(n_parallel):
    """
    计算非平行运行图通过能力
    N_非 = N_平行 - [ε客 × n客 + (ε快货 - 1) × n快货 + (ε摘挂 - 1) × n摘挂]
    """
    # 旅客列车扣除
    deduction_passenger = EPSILON_PASSENGER * N_PASSENGER

    # 摘挂列车追加扣除
    n_pickup = FREIGHT_DOWN["摘挂"] + FREIGHT_UP["摘挂"]
    deduction_pickup = (EPSILON_PICKUP - 1) * n_pickup

    # 快货列车追加扣除（这里直达和区段视为一般货物列车）
    n_fast = FREIGHT_DOWN["直达(空)"] + FREIGHT_UP["直达(重)"]
    deduction_fast = (EPSILON_FAST_FREIGHT - 1) * n_fast

    total_deduction = deduction_passenger + deduction_pickup + deduction_fast
    n_non_parallel = n_parallel - total_deduction

    return {
        "n_parallel": n_parallel,
        "deduction_passenger": deduction_passenger,
        "deduction_pickup": deduction_pickup,
        "deduction_fast": deduction_fast,
        "total_deduction": total_deduction,
        "n_non_parallel_float": n_non_parallel,
        "n_non_parallel": math.floor(n_non_parallel),
        "n_passenger_pairs": N_PASSENGER,
        "n_pickup": n_pickup,
        "n_fast": n_fast,
    }


# ============================================================
# 第五部分：列车运行图铺画
# ============================================================

def calc_train_schedule_with_occupancy(train, section_occ, depart_time):
    """
    计算单列车在各站的到发时刻 — 带区间占用约束。
    单线半自动闭塞：任一区间同一时刻只能被一列车占用。
    上下行列车只能在车站交会，不能在区间内交叉。

    section_occ: dict, key=section_idx, value=set of (enter_time, exit_time, train_id)
    depart_time: 从始发站出发的时刻（可能因冲突被推迟）
    返回: (schedule, actual_depart_time)
    """
    dir = train["dir"]
    train_id = train["id"]
    train_type = train["type"]

    schedule = {"id": train_id, "type": train_type, "dir": dir, "stations": []}
    current_time = depart_time

    if dir == "down":
        # A→B, 区间编号 0..5 (A-a=0, a-b=1, b-c=2, c-d=3, d-e=4, e-B=5)
        for i in range(N_STATIONS):
            si = {"station": STATIONS[i], "arrive": None, "depart": None}

            if i == 0:  # 始发站 A
                si["depart"] = current_time
                si["arrive"] = None
            else:
                section_idx = i - 1  # 刚经过的区间
                t_run = DOWN_RUNNING[section_idx]

                # 计算到达下一站时间（无等待）
                raw_arrive = current_time + t_run + T_START

                # 检查该区间是否有冲突
                enter_t = current_time
                exit_t = raw_arrive

                # 查找区间占用中的冲突
                conflict_delay = 0
                if section_idx in section_occ:
                    for (occ_enter, occ_exit, occ_id) in section_occ[section_idx]:
                        if occ_id == train_id:
                            continue
                        # 时间重叠检测
                        if enter_t < occ_exit and exit_t > occ_enter:
                            # 冲突！需要等区间清空
                            # 延迟到占用结束后进入
                            conflict_delay = max(conflict_delay, occ_exit - enter_t)

                if conflict_delay > 0:
                    # 在上一站等待，更新上一站出发时间
                    current_time += conflict_delay
                    schedule["stations"][i-1]["depart"] = current_time
                    raw_arrive = current_time + t_run + T_START

                current_time = raw_arrive
                si["arrive"] = current_time

                # 停站时间
                if train_type == "旅客":
                    stop_time = STOP_PASSENGER
                elif train_type == "摘挂":
                    stop_time = STOP_PICKUP
                else:
                    stop_time = 0 if STATIONS[i] in ["a", "b", "c", "d", "e"] else STOP_FREIGHT

                if i == N_STATIONS - 1:
                    si["depart"] = None
                else:
                    current_time += stop_time + T_STOP
                    si["depart"] = current_time

            schedule["stations"].append(si)

        # 记录本列车对各区间的占用
        for i in range(N_STATIONS - 1):
            enter_t = schedule["stations"][i]["depart"]      # 从站i出发 = 进入区间i
            exit_t = schedule["stations"][i+1]["arrive"]      # 到达站i+1 = 离开区间i
            if enter_t is not None and exit_t is not None:
                section_occ.setdefault(i, set()).add((enter_t, exit_t, train_id))

    else:
        # B→A, 区间索引: B-e=5, e-d=4, d-c=3, c-b=2, b-a=1, a-A=0
        for i in range(N_STATIONS - 1, -1, -1):
            si = {"station": STATIONS[i], "arrive": None, "depart": None}

            if i == N_STATIONS - 1:  # 始发站 B
                si["depart"] = current_time
                si["arrive"] = None
            else:
                section_idx = i  # 上行经过的区间 (从 i+1 站到 i 站)
                t_run = UP_RUNNING[section_idx]

                raw_arrive = current_time + t_run + T_START

                enter_t = current_time
                exit_t = raw_arrive

                conflict_delay = 0
                if section_idx in section_occ:
                    for (occ_enter, occ_exit, occ_id) in section_occ[section_idx]:
                        if occ_id == train_id:
                            continue
                        if enter_t < occ_exit and exit_t > occ_enter:
                            conflict_delay = max(conflict_delay, occ_exit - enter_t)

                if conflict_delay > 0:
                    current_time += conflict_delay
                    # 回写上一站出发时间（上行中上一站为i+1，当前在schedule索引0处）
                    schedule["stations"][0]["depart"] = current_time
                    raw_arrive = current_time + t_run + T_START

                current_time = raw_arrive
                si["arrive"] = current_time

                if train_type == "旅客":
                    stop_time = STOP_PASSENGER
                elif train_type == "摘挂":
                    stop_time = STOP_PICKUP
                else:
                    stop_time = 0 if STATIONS[i] in ["a", "b", "c", "d", "e"] else STOP_FREIGHT

                if i == 0:
                    si["depart"] = None
                else:
                    current_time += stop_time + T_STOP
                    si["depart"] = current_time

            schedule["stations"].insert(0, si)

        # 记录本列车对各区间的占用
        for i in range(N_STATIONS - 1):
            # 上行方向: 从 i+1 站出发 → i 站到达，占用区间 i
            enter_t = schedule["stations"][i+1]["depart"]   # 从站i+1出发
            exit_t = schedule["stations"][i]["arrive"]       # 到达站i
            if enter_t is not None and exit_t is not None:
                section_occ.setdefault(i, set()).add((enter_t, exit_t, train_id))

    return schedule, depart_time


def generate_timetable(parallel_result, non_parallel_result):
    """
    生成完整的列车运行时刻表 — 含单线区间占用冲突检测。
    调度顺序：旅客列车 → 摘挂列车 → 区段/直达货物列车
    """
    section_occ = {}  # section_idx -> set of (enter, exit, train_id)

    # 1. 旅客列车（固定时刻，优先铺画）
    timetable = []
    for pt in PASSENGER_TRAINS:
        train = {"id": pt["id"], "type": "旅客", "dir": pt["dir"]}
        schedule, _ = calc_train_schedule_with_occupancy(train, section_occ, pt["depart"])
        timetable.append(schedule)

    # 2. 摘挂列车
    pickup_specs = []
    # 下行摘挂
    pickup_down_times = [6*60+30, 14*60+30]
    for i in range(FREIGHT_DOWN["摘挂"]):
        pickup_specs.append({
            "id": f"4003{i+5}", "type": "摘挂", "dir": "down",
            "depart_time": pickup_down_times[i % len(pickup_down_times)],
        })
    # 上行摘挂
    pickup_up_times = [10*60+30, 18*60+30]
    for i in range(FREIGHT_UP["摘挂"]):
        pickup_specs.append({
            "id": f"4004{i+5}", "type": "摘挂", "dir": "up",
            "depart_time": pickup_up_times[i % len(pickup_up_times)],
        })

    for ps in pickup_specs:
        train = {"id": ps["id"], "type": ps["type"], "dir": ps["dir"]}
        schedule, _ = calc_train_schedule_with_occupancy(train, section_occ, ps["depart_time"])
        timetable.append(schedule)

    # 3. 区段/直达货物列车 — 均匀排布，检测冲突
    remaining_down = FREIGHT_DOWN["直达(空)"] + FREIGHT_DOWN["区段"]
    remaining_up = FREIGHT_UP["直达(重)"] + FREIGHT_UP["区段"]

    down_specs = []
    start_t = T_MAINTENANCE + 10
    end_t = 23*60 + 30
    interval = (end_t - start_t) / max(remaining_down, 1)
    for i in range(remaining_down):
        t = int(start_t + i * interval)
        down_specs.append({
            "id": f"3000{i+1}", "type": "区段" if i < FREIGHT_DOWN["区段"] else "直达",
            "dir": "down", "depart_time": t,
        })

    up_specs = []
    for i in range(remaining_up):
        t = int(start_t + interval/2 + i * interval)
        if t > end_t:
            t = int(start_t + (i - remaining_up/2) * interval)
        up_specs.append({
            "id": f"1000{i+2}", "type": "区段" if i < FREIGHT_UP["区段"] else "直达",
            "dir": "up", "depart_time": t,
        })

    # 交替调度下行和上行（避免一方全部占满区间）
    all_freight = []
    max_f = max(len(down_specs), len(up_specs))
    for i in range(max_f):
        if i < len(down_specs):
            all_freight.append(down_specs[i])
        if i < len(up_specs):
            all_freight.append(up_specs[i])

    for fs in all_freight:
        train = {"id": fs["id"], "type": fs["type"], "dir": fs["dir"]}
        # 尝试从初始时刻出发，如遇冲突自动顺延
        schedule, actual_dep = calc_train_schedule_with_occupancy(
            train, section_occ, fs["depart_time"])
        timetable.append(schedule)

    return timetable


def calc_train_schedule(train):
    """
    兼容旧接口：不做区间冲突检测，直接计算单列车时刻。
    供 calc_tables.py 等外部调用。
    """
    empty_occ = {}
    depart_time = train.get("depart_time", train.get("depart", 0))
    schedule, _ = calc_train_schedule_with_occupancy(
        {"id": train.get("id", ""), "type": train.get("type", "区段"), "dir": train.get("dir", "down")},
        empty_occ, depart_time)
    return schedule


def draw_train_diagram(timetable, filename="train_diagram.png"):
    """
    铺画列车运行图（时-距图）
    横轴：时间 (0:00 - 24:00)
    纵轴：车站 (A → B)，按运行时间比例
    """
    # 设置中文字体
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(20, 12))

    # 计算纵轴位置 — 按重车方向运行时间比例
    cumulative_times = [0]
    for i in range(N_STATIONS - 1):
        cumulative_times.append(cumulative_times[-1] + DOWN_RUNNING[i])

    y_positions = [1.0 - (t / cumulative_times[-1]) for t in cumulative_times]  # 归一化，A在上

    # 颜色方案
    color_map = {
        "旅客": "#E74C3C",  # 红色
        "直达": "#2980B9",  # 蓝色
        "区段": "#27AE60",  # 绿色
        "摘挂": "#8E44AD",  # 紫色
    }

    line_style_map = {
        "旅客": "-",
        "直达": "-",
        "区段": "-",
        "摘挂": "--",
    }

    line_width_map = {
        "旅客": 2.0,
        "直达": 1.5,
        "区段": 1.5,
        "摘挂": 1.2,
    }

    # 绘制网格
    # 时间网格（每小时）
    for h in range(0, 25):
        ax.axvline(x=h*60, color="#E0E0E0", linewidth=0.5, linestyle="-")

    # 十分格（每10分钟浅线）
    for m in range(0, 1441, 10):
        ax.axvline(x=m, color="#F0F0F0", linewidth=0.2, linestyle="-")

    # 车站横线
    for i, station in enumerate(STATIONS):
        y = y_positions[i]
        ax.axhline(y=y, color="#333333", linewidth=1.0 if station in ["A", "B"] else 0.6)
        ax.text(-25, y, station, fontsize=10, fontweight="bold" if station in ["A", "B"] else "normal",
                verticalalignment="center", horizontalalignment="right")

    # 天窗区域
    ax.axvspan(0, T_MAINTENANCE, alpha=0.15, color="gray", label=f"天窗 (0:00-{T_MAINTENANCE//60}:00)")

    # 绘制列车运行线
    for train in timetable:
        train_type = train["type"]
        color = color_map.get(train_type, "#000000")
        ls = line_style_map.get(train_type, "-")
        lw = line_width_map.get(train_type, 1.0)

        points = []

        for i, station_info in enumerate(train["stations"]):
            y = y_positions[i]
            if station_info["arrive"] is not None:
                points.append((station_info["arrive"], y))
            if station_info["depart"] is not None:
                points.append((station_info["depart"], y))

        # 按时间排序，确保上行/下行运行线都正确向右延伸
        points.sort(key=lambda p: p[0])
        times = [p[0] for p in points]
        ys = [p[1] for p in points]

        # 绘制运行线
        if len(times) >= 2:
            ax.plot(times, ys, color=color, linewidth=lw, linestyle=ls, alpha=0.85)

            # 标注车次号
            mid_idx = len(times) // 2
            if mid_idx < len(times):
                ax.annotate(
                    train["id"],
                    xy=(times[mid_idx], ys[mid_idx]),
                    fontsize=7,
                    color=color,
                    fontweight="bold",
                    ha="left",
                    va="bottom",
                    alpha=0.9,
                )

    # 设置坐标轴
    ax.set_xlim(-40, 1480)
    ax.set_ylim(-0.05, 1.05)

    # 时间轴刻度
    hour_ticks = [h * 60 for h in range(0, 25)]
    hour_labels = [f"{h}:00" for h in range(0, 25)]
    ax.set_xticks(hour_ticks)
    ax.set_xticklabels(hour_labels, rotation=45, fontsize=8)

    # 隐藏纵轴刻度
    ax.set_yticks([])

    # 标题和标签
    ax.set_title("A-B 区段列车运行图", fontsize=16, fontweight="bold", pad=20)
    ax.set_xlabel("时间", fontsize=12)

    # 图例
    legend_patches = [
        mpatches.Patch(color="#E74C3C", label="旅客列车"),
        mpatches.Patch(color="#2980B9", label="直达列车"),
        mpatches.Patch(color="#27AE60", label="区段列车"),
        mpatches.Patch(color="#8E44AD", label="摘挂列车"),
        mpatches.Patch(color="#CCCCCC", alpha=0.5, label="天窗"),
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=9)

    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [OK] 运行图已保存: {filename}")
    return filename


# ============================================================
# 第六部分：质量指标计算
# ============================================================

def calc_quality_indicators(timetable):
    """
    计算运行图质量指标
    包括：货物列车旅行速度、速度系数、机车周转时间、机车日车公里
    """
    # 筛选货物列车（含摘挂）
    freight_timetable = [t for t in timetable if t["type"] in ("区段", "直达", "摘挂")]

    total_travel_time = 0
    total_run_time = 0
    total_stop_time = 0
    total_distance_all = 0
    train_count = 0

    for train in freight_timetable:
        stations = train["stations"]
        # 找最早出发和最晚到达时刻（按时间值，而非站序）
        departure_times = [s["depart"] for s in stations if s["depart"] is not None]
        arrival_times = [s["arrive"] for s in stations if s["arrive"] is not None]

        if departure_times and arrival_times:
            start_time = min(departure_times)
            end_time = max(arrival_times)
            travel_time = end_time - start_time  # min
            total_travel_time += travel_time
            total_distance_all += TOTAL_DISTANCE

            # 计算纯运行时间（所有区间之和）
            run_time = 0
            dir = train["dir"]
            if dir == "down":
                run_time = sum(DOWN_RUNNING)
            else:
                run_time = sum(UP_RUNNING)
            total_run_time += run_time
            total_stop_time += (travel_time - run_time)
            train_count += 1

    if train_count == 0:
        return {"error": "无货物列车数据"}

    # 技术速度 (km/h) = 总距离 / 纯运行时间
    avg_tech_speed_km_per_min = total_distance_all / total_run_time
    avg_tech_speed = avg_tech_speed_km_per_min * 60  # km/h

    # 旅行速度 (km/h) = 总距离 / 总旅行时间（含停站）
    avg_travel_speed_km_per_min = total_distance_all / total_travel_time
    avg_travel_speed = avg_travel_speed_km_per_min * 60  # km/h

    # 速度系数 = 旅行速度 / 技术速度
    speed_coefficient = avg_travel_speed / avg_tech_speed if avg_tech_speed > 0 else 0

    # 机车周转时间
    # 一台机车完成一次完整循环的时间
    # 单程运行 + 两端折返时间
    avg_one_way_time = total_travel_time / train_count  # 平均单程时间
    loco_cycle_time = avg_one_way_time * 2 + A_LOCO_TURNAROUND + B_LOCO_TURNAROUND  # min

    # 机车日车公里
    # 每台机车一天走行公里数
    trips_per_loco_per_day = (24 * 60) / loco_cycle_time  # 每台机车每日周转次数
    loco_daily_km = trips_per_loco_per_day * TOTAL_DISTANCE * 2  # 往返算两次距离
    # 平均到每台机车
    loco_daily_km_per_loco = loco_daily_km

    return {
        "train_count": train_count,
        "total_distance_km": TOTAL_DISTANCE,
        "avg_tech_speed_kmh": round(avg_tech_speed, 2),
        "avg_travel_speed_kmh": round(avg_travel_speed, 2),
        "speed_coefficient": round(speed_coefficient, 4),
        "loco_cycle_time_min": round(loco_cycle_time, 0),
        "loco_cycle_time_h": round(loco_cycle_time / 60, 2),
        "loco_daily_km": round(loco_daily_km, 0),
        "loco_daily_km_total": round(loco_daily_km * N_LOCOMOTIVES, 0),
        "n_locomotives": N_LOCOMOTIVES,
        "avg_one_way_time_min": round(avg_one_way_time, 0),
    }


def print_timetable(timetable):
    """打印列车时刻表"""
    print("\n" + "=" * 90)
    print("  列车运行时刻表")
    print("=" * 90)

    for train in timetable:
        print(f"\n  [{train['type']}] {train['id']}  ({'下行 A→B' if train['dir']=='down' else '上行 B→A'})")
        print(f"  {'─' * 70}")

        for s in train["stations"]:
            arr_str = f"{s['arrive']//60:02d}:{s['arrive']%60:02d}" if s['arrive'] is not None else "  ---  "
            dep_str = f"{s['depart']//60:02d}:{s['depart']%60:02d}" if s['depart'] is not None else "  ---  "
            print(f"    {s['station']:>4s}    到 {arr_str}    发 {dep_str}")


# ============================================================
# 第七部分：主程序
# ============================================================

def main():
    print("=" * 70)
    print("  A-B 区段列车运行图编制")
    print("  题目 4.11 — 单线半自动闭塞")
    print("=" * 70)

    # ---------------------------
    # 1. 基础信息
    # ---------------------------
    print(f"\n{'─' * 50}")
    print("  基础数据汇总")
    print(f"{'─' * 50}")
    print(f"  区段总长: {TOTAL_DISTANCE} km")
    print(f"  车站数量: {N_STATIONS} 个 (含两端)")
    print(f"  闭塞方式: 半自动闭塞")
    print(f"  旅客列车: {N_PASSENGER} 对 (K775/776, K777/778)")
    print(f"  货物列车(下行): 直达{FREIGHT_DOWN['直达(空)']}列, 区段{FREIGHT_DOWN['区段']}列, 摘挂{FREIGHT_DOWN['摘挂']}列")
    print(f"  货物列车(上行): 直达{FREIGHT_UP['直达(重)']}列, 区段{FREIGHT_UP['区段']}列, 摘挂{FREIGHT_UP['摘挂']}列")
    print(f"  货运机车: {N_LOCOMOTIVES} 台")
    print(f"  天窗时间: {T_MAINTENANCE} min")

    # 区间数据
    print(f"\n  {'区间':<12} {'距离(km)':<10} {'下行(min)':<10} {'上行(min)':<10} {'股道(下行站)':<12}")
    print(f"  {'─' * 55}")
    for i in range(N_STATIONS - 1):
        print(f"  {STATIONS[i]+'-'+STATIONS[i+1]:<12} {DISTANCES[i]:<10} {DOWN_RUNNING[i]:<10} {UP_RUNNING[i]:<10} {TRACKS[i]:<12}")

    # ---------------------------
    # 2. 平行运行图通过能力
    # ---------------------------
    parallel = calc_parallel_capacity()
    print(f"\n{'─' * 50}")
    print("  (1) 平行运行图通过能力计算")
    print(f"{'─' * 50}")
    print(f"  可用时间: 1440 - {T_MAINTENANCE} = {parallel['available_time']} min")
    print(f"  限制区间: {parallel['restrictive_section']}")
    print(f"  限制区间周期 T_周 = {parallel['restrictive_period']} min")
    print(f"  N_平行 = {parallel['available_time']} / {parallel['restrictive_period']} = {parallel['n_parallel_float']:.1f}")
    print(f"  N_平行(取整) = {parallel['n_parallel']} 对/天")

    # 各区间详细
    print(f"\n  各区间周期分析:")
    print(f"  {'区间':<12} {'T下行':<8} {'T上行':<8} {'T周期':<8}")
    print(f"  {'─' * 36}")
    for s in parallel["section_details"]:
        print(f"  {s['section']:<12} {s['t_down_total']:<8} {s['t_up_total']:<8} {s['t_period']:<8}")

    # ---------------------------
    # 3. 非平行运行图通过能力
    # ---------------------------
    non_parallel = calc_non_parallel_capacity(parallel["n_parallel"])
    print(f"\n{'─' * 50}")
    print("  (2) 非平行运行图通过能力计算")
    print(f"{'─' * 50}")
    print(f"  N_平行 = {non_parallel['n_parallel']} 对/天")
    print(f"  旅客列车扣除: ε客 × n客 = {EPSILON_PASSENGER} × {N_PASSENGER} = {non_parallel['deduction_passenger']} 对")
    print(f"  摘挂列车追加扣除: (ε摘挂-1) × n摘挂 = ({EPSILON_PICKUP}-1) × {non_parallel['n_pickup']} = {non_parallel['deduction_pickup']:.1f} 对")
    print(f"  快货列车追加扣除: (ε快货-1) × n快货 = ({EPSILON_FAST_FREIGHT}-1) × {non_parallel['n_fast']} = {non_parallel['deduction_fast']:.1f} 对")
    print(f"  总扣除: {non_parallel['total_deduction']:.1f} 对")
    print(f"  N_非平行 = {non_parallel['n_parallel']} - {non_parallel['total_deduction']:.1f} = {non_parallel['n_non_parallel_float']:.1f}")
    print(f"  N_非平行(取整) = {non_parallel['n_non_parallel']} 对/天")

    # ---------------------------
    # 4. 铺画列车运行图
    # ---------------------------
    print(f"\n{'─' * 50}")
    print("  (3) 铺画列车运行图")
    print(f"{'─' * 50}")

    timetable = generate_timetable(parallel, non_parallel)
    print_timetable(timetable)

    # 绘制作图
    img_file = draw_train_diagram(timetable, "A-B_train_diagram.png")

    # ---------------------------
    # 5. 质量指标
    # ---------------------------
    quality = calc_quality_indicators(timetable)
    print(f"\n{'─' * 50}")
    print("  (4) 运行图质量指标")
    print(f"{'─' * 50}")
    print(f"  (a) 货物列车速度指标:")
    print(f"      技术速度 (纯运行):   {quality['avg_tech_speed_kmh']} km/h")
    print(f"      旅行速度 (含停站):   {quality['avg_travel_speed_kmh']} km/h")
    print(f"      速度系数:             {quality['speed_coefficient']}")
    print(f"      统计货物列车数:       {quality['train_count']} 列")

    print(f"\n  (b) 机车运用指标:")
    print(f"      机车全周转时间:       {quality['loco_cycle_time_min']:.0f} min ({quality['loco_cycle_time_h']} h)")
    print(f"      机车日车公里(单台):   {quality['loco_daily_km']:.0f} km/台·日")
    print(f"      {N_LOCOMOTIVES}台机车总日车公里:       {quality['loco_daily_km_total']:.0f} km/日")
    print(f"      机车需要系数:         {quality['train_count'] / N_LOCOMOTIVES:.2f} 列/台")

    # ---------------------------
    # 6. 汇总输出
    # ---------------------------
    print(f"\n{'=' * 70}")
    print("  成果汇总")
    print(f"{'=' * 70}")
    print(f"""
  ┌─────────────────────────────────────────────────────────┐
  │  A-B 区段列车运行图编制成果                               │
  ├─────────────────────────────────────────────────────────┤
  │  区段: A—a—b—c—d—e—B                                    │
  │  总长: {TOTAL_DISTANCE} km      闭塞: 单线半自动闭塞               │
  ├─────────────────────────────────────────────────────────┤
  │  1. 平行运行图通过能力:     {parallel['n_parallel']:>4d} 对/天          │
  │  2. 非平行运行图通过能力:   {non_parallel['n_non_parallel']:>4d} 对/天  │
  │  3. 运行图铺画:            {len(timetable)} 列车 ({N_PASSENGER*2} 客 + {len(timetable)-N_PASSENGER*2} 货)       │
  │  4. 货物列车旅行速度:      {quality['avg_travel_speed_kmh']} km/h          │
  │  5. 速度系数:              {quality['speed_coefficient']}              │
  │  6. 机车日车公里:          {quality['loco_daily_km']:.0f} km/台·日    │
  └─────────────────────────────────────────────────────────┘
""")

    print(f"  输出文件: {img_file}")
    print(f"\n  计算完成！")


if __name__ == "__main__":
    main()
