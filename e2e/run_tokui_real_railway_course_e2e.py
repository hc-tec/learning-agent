"""
Real railway TokUI course E2E for AI-Shifu.

This script validates the product path with a realistic teacher-authored
railway lesson, not the controlled E2E marker model. It creates a course through
the backend API, saves the full teacher guidance, publishes it, generates the
learner TokUI runtime, submits learner answers, and verifies the continuation.

Usage:
    python ./e2e/run_tokui_real_railway_course_e2e.py

Optional environment:
    AI_SHIFU_URL=http://127.0.0.1:8080
    E2E_REAL_TOKUI_MODEL=deepseek-v4-flash
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from run_tokui_complex_course_e2e import (
    ApiClient,
    CheckFailed,
    ScenarioRecorder,
    require_api_ok,
    resolve_api_base_url,
    start_tokui_validator_if_needed,
)


TARGET_URL = os.getenv("AI_SHIFU_URL", "http://127.0.0.1:8080").rstrip("/")
RESULT_PATH = Path(__file__).resolve().parent / "tokui_real_railway_course_e2e_result.json"
REAL_MODEL = os.getenv("E2E_REAL_TOKUI_MODEL", "deepseek-v4-flash")


REAL_RAILWAY_LESSON_GUIDANCE = """
【模块一・小节 1】铁路行业基本格局与分类

本节学习目标（费曼标准）

学完之后，学生要能用大白话给外行讲清楚：中国的铁路分哪几种，分别跑多快、干嘛用的；以后听到业务需求，第一反应能对应上是哪类铁路的场景，不会犯“给拉煤的铁路做人脸识别检票”的低级错误。

一、开篇：先搞懂「为什么要给铁路分类」

先讲一个所有人都能懂的类比：
我们平时走的路，分小区水泥路、城市马路、国道、高速公路，不是随便起名的。小区路跑慢点、能走人；高速跑很快、只能走汽车，建设标准、成本、规则完全不一样。

铁路也是一个道理。铁路分类的本质，就是按「跑多快」和「拉什么」，给不同需求的铁路定不同的设计标准、建设成本和运营规则。

对数智化部门来说，分类的意义更直接：
- 高铁的核心诉求是“绝对安全、尽量少出故障”，我们做的是高精度故障预测、数字孪生运维。
- 重载铁路的核心诉求是“多拉货、少停车、省成本”，我们做的是载重监测、机车损耗管理。

连代码里的参数阈值都不一样，所以这是入行第一个要掰扯清楚的概念。

二、我国铁路四大核心类型（逐类精讲）

按「速度从快到慢、功能从纯客运到大货运」的顺序，一个个讲透。所有第一次出现的专业词，都必须附带大白话翻译。

1. 高速铁路（简称：高铁）

大白话定义：专门拉旅客、跑得最快、线路最平整的铁路，就是我们平时坐的“G 字头”动车。

- 核心速度标准：设计时速 250 公里及以上，现在国内主流干线是 350 公里/小时。
- 核心特点：全封闭、全立交，没有和马路交叉的平交道口；全程采用无砟轨道。无砟轨道的大白话解释：不用碎石铺床，直接用混凝土板固定钢轨，开快了不晃，维护量小；只拉人，不拉货；对线路平顺度要求极高。
- 典型代表：京沪高铁、京广高铁、沿江高铁。
- 和数智化业务的关系：这是数智化业务最核心的赛道。智慧运维、数字化交付、智能建造，绝大多数标杆项目都在高铁上，要求精度最高、标准最严。

2. 城际铁路

大白话定义：同一个城市群里，城市和城市之间通勤用的“短途高铁”，比如武汉到鄂州、黄石，本质就是大城市的“超长地铁线”。

- 核心速度标准：设计时速 100-200 公里。
- 核心特点：站间距特别短，几公里到十几公里一个站；发车频次高，像公交一样随到随走；大多连接市中心，方便上班族通勤。
- 典型代表：武鄂黄黄城际铁路、广深城际铁路。
- 和数智化业务的关系：核心需求在运营端，比如客流预测、智慧票务、通勤一体化系统，和高铁侧重“设备运维”的逻辑完全不一样。

3. 客货共线铁路（俗称：普速铁路）

大白话定义：最传统的铁路，既能跑绿皮火车拉人，也能跑货车拉货，客货混跑，是铁路网里的“全能选手”，覆盖范围最广。

- 核心速度标准：设计时速 120-160 公里。
- 核心特点：以有砟轨道为主。有砟轨道的大白话解释：就是印象里铺碎石的轨道；同一条线路上同时跑客车和货车；大部分是既有老线路，通到全国绝大多数县城。
- 典型代表：老京广铁路、京九铁路。
- 和数智化业务的关系：这类线路大多面临老旧设备改造，业务主要是智能巡检、货运组织优化，以改造升级类项目居多。

4. 重载铁路

大白话定义：专门拉煤炭、矿石这类大宗货物的“货运巨无霸”，只拉货不拉人，拉得多、跑得稳，是国家能源运输的大动脉。

- 核心速度标准：设计时速 80-120 公里。
- 核心特点：列车牵引重量极大，普遍万吨级以上，一列火车好几公里长；轴重高。轴重的大白话解释：每根车轴压在轨道上的重量更大，对线路和车轮损耗极快；只跑货运，不跑客运。
- 典型代表：大秦铁路、浩吉铁路。
- 和数智化业务的关系：核心需求是货运效率和设备寿命管理，比如机车 PHM 健康管理、装载量智能监测，技术侧重点和高铁完全不同。

【素材插入位置 1：讲完四类铁路的文字讲解后，立即插入】
素材类型：短视频
素材时长：1 分 30 秒
素材名称：四类铁路实景对比短片
详细内容描述：
视频采用「分屏切换 + 实景画面 + 字幕标注」的形式，按高铁、城际、客货共线、重载的顺序依次呈现：
0-20 秒：高铁画面，CR400 动车组在高架桥上飞驰，车窗外景色快速后退，配平稳的行进音效；画面右下角白色字幕：高速铁路 | 350km/h | 纯客运 | 高平顺性。
20-40 秒：城际铁路画面，城际列车进出市区车站，镜头连续扫过多个密集的站台，配车站广播背景音；字幕：城际铁路 | 200km/h | 公交化通勤 | 站间距短。
40-60 秒：客货共线画面，先出现绿皮客车通过，镜头一转货运列车紧随其后通过同一条线路；字幕：客货共线铁路 | 160km/h | 客货混跑 | 覆盖最广。
60-90 秒：重载铁路画面，高空俯拍绵延数公里的万吨重载列车，行驶在煤炭专线上；字幕：重载铁路 | 80km/h | 万吨级牵引 | 大宗货运。
素材作用：用直观的视觉差异替代抽象文字，让新人一眼建立体感，避免死记硬背。

【素材插入位置 2：视频播放结束后，立即插入】
素材类型：静态信息图
素材名称：中国四类铁路核心参数对比图
详细画面描述：
整体采用横向四栏对比布局，浅灰色底色，每一栏对应一类铁路，用不同主题色区分，从上到下按统一维度对齐，关键数据用高亮色标注：
第一栏，蓝色主题，高速铁路：高铁车头图标 +「高速铁路」标题，速度 250-350km/h，核心功能是长途主干客运，核心特点是无砟轨道、高平顺性，数智化侧重是智能运维、数字化交付。
第二栏，绿色主题，城际铁路：城际列车图标 +「城际铁路」标题，速度 100-200km/h，核心功能是都市圈通勤，核心特点是站距短、公交化运营，数智化侧重是客流预测、智慧票务。
第三栏，橙色主题，客货共线：绿皮火车图标 +「客货共线铁路」标题，速度 120-160km/h，核心功能是客货兼顾、普速干线，核心特点是有砟轨道、覆盖范围广，数智化侧重是智能巡检、老旧改造。
第四栏，棕色主题，重载铁路：货运列车图标 +「重载铁路」标题，速度 80-120km/h，核心功能是大宗货物运输，核心特点是大轴重、大牵引重量，数智化侧重是载重监测、设备健康管理。
画面最底部加一行灰色小字备注：设计时速为线路设计上限，不等于日常实际运营时速。
素材作用：把零散的知识点结构化，形成清晰的对比框架，方便学员暂停截图、回顾记忆。

三、补充：路网与“八纵八横”是什么

讲完单条铁路的分类，再把视角放大到全国。

大白话解释「路网」：就像全国高速公路网，一条条单独的高铁、铁路互相连接，组成的全国铁路大网络，就叫铁路路网。

我们国家的高铁网，有一个核心骨架叫「八纵八横」：8 条南北走向的纵向大通道，加 8 条东西走向的横向大通道，共同组成全国高铁的主干线。铁四院的核心业务，就集中在长江经济带沿线的“沿江通道”上。

【素材插入位置 3：讲完“八纵八横”概念后立即插入】
素材类型：静态地图
素材名称：中国高铁“八纵八横”主通道示意图
详细画面描述：
底图为简化的中国地图，只保留省界轮廓，不标注冗余地名，视觉干净清爽。
用 8 条红色粗实线标注纵向通道，8 条蓝色粗实线标注横向通道，每条线条旁标注简称，如“京哈 - 京港澳通道”“沿江通道”。
用黄色五角星重点标注武汉的位置，用加亮加粗的线条突出「沿江通道」，旁边加白色气泡备注：铁四院核心参建区域。
图例放在右下角，区分纵向通道、横向通道、核心枢纽城市。
素材作用：建立空间认知，让新人快速理解国家路网的整体格局，以及本院业务的核心覆盖区域。

四、本节收尾：一句话总结 + 费曼小测试

一句话总结：
铁路按速度和功能分四大类：高铁跑长途快客、城际跑都市通勤、普速客货混跑、重载拉大宗货物；数智化产品必须对应不同类型的核心需求定制，不能一套方案打天下。

费曼小测试：
1. 客户说“我们这条线要做万吨列车的制动系统健康预测”，这属于哪类铁路？
2. 客户说“我们要做市域内的通勤客流预测系统”，这大概率对应哪类铁路？
3. 用自己的话讲：为什么高铁一般不跑货运列车？

学生回答后，AI 必须先判断答案质量，再决定后续讲解策略：
- 答对：用“答得对”或“判断正确”确认，并说明为什么。
- 答错：用“这里有误区”指出错误，再补讲相关概念。
- 答得含糊：用“还不够具体”指出不充分，再给对比例子或追问。
- 答非所问：用“先回到问题”把学生拉回原问题。
不要无论学生答什么都机械进入下一段；不要清空前文；不要重新进入课程开头。
""".strip()


def real_material_refs() -> list[dict[str, Any]]:
    return [
        {
            "placement_id": "railway_scene_video",
            "position": "1",
            "insertion_point": "讲完四类铁路的文字讲解后，立即插入",
            "media_type": "video",
            "title": "四类铁路实景对比短片",
            "description": "高铁、城际、客货共线、重载四段实景分屏对比，带速度、功能和特点字幕。",
            "purpose": "用直观的视觉差异替代抽象文字，让新人一眼建立体感。",
        },
        {
            "placement_id": "railway_compare_chart",
            "position": "2",
            "insertion_point": "视频播放结束后，立即插入",
            "media_type": "image",
            "title": "中国四类铁路核心参数对比图",
            "description": "横向四栏对比高铁、城际、客货共线、重载铁路的速度、功能、特点和数智化侧重。",
            "purpose": "把零散知识点结构化，方便学员回顾记忆。",
        },
        {
            "placement_id": "eight_vertical_eight_horizontal_map",
            "position": "3",
            "insertion_point": "讲完八纵八横概念后立即插入",
            "media_type": "image",
            "title": "中国高铁“八纵八横”主通道示意图",
            "description": "简化中国地图，突出八纵八横、武汉和沿江通道。",
            "purpose": "建立空间认知，让新人理解全国路网和本院业务区域。",
        },
    ]


def real_interaction_points() -> list[dict[str, Any]]:
    return [
        {
            "interaction_id": "heavy_haul_reasoning_check",
            "position": "1",
            "insertion_point": "讲完重载铁路定义、典型代表和数智化业务关系后插入",
            "kind": "feynman_check",
            "prompt": "客户说“我们这条线要做万吨列车的制动系统健康预测”，这属于哪类铁路？请用一句话说明判断依据。",
            "response_schema": {"field_type": "short_text"},
            "blocking": True,
            "continue_on_submit": True,
            "continuation_hint": "根据答案判断学生是否理解重载铁路的业务诉求，答错时补讲大宗货运、轴重和设备寿命管理。",
        },
        {
            "interaction_id": "intercity_flow_check",
            "position": "2",
            "insertion_point": "讲完城际铁路的通勤属性、短站距和运营端需求后插入",
            "kind": "scenario_mapping",
            "prompt": "客户说“我们要做市域内的通勤客流预测系统”，这大概率对应哪类铁路？",
            "response_schema": {
                "field_type": "single_choice",
                "options": [
                    {"value": "high_speed", "label": "高速铁路"},
                    {"value": "intercity", "label": "城际铁路"},
                    {"value": "mixed_passenger_freight", "label": "客货共线铁路"},
                    {"value": "heavy_haul", "label": "重载铁路"},
                ],
            },
            "blocking": True,
            "continue_on_submit": True,
            "continuation_hint": "根据答案补强城际铁路和高铁的区别，尤其是站间距、公交化运营和客流预测。",
        },
        {
            "interaction_id": "railway_type_feature_check",
            "position": "3",
            "insertion_point": "讲完四类铁路核心特点对比表后插入",
            "kind": "multi_select_understanding",
            "prompt": "下面哪些特征通常能帮助你判断一个需求属于重载铁路场景？",
            "response_schema": {
                "field_type": "multi_choice",
                "options": [
                    {"value": "ten_thousand_ton_train", "label": "万吨级列车"},
                    {"value": "bulk_cargo", "label": "煤炭、矿石等大宗货物"},
                    {"value": "high_frequency_commute", "label": "高频公交化通勤"},
                    {"value": "high_axle_load", "label": "大轴重和设备寿命管理"},
                ],
            },
            "blocking": True,
            "continue_on_submit": True,
            "continuation_hint": "根据选择结果判断学生是否能把重载铁路和城际/高铁需求分开。",
        },
        {
            "interaction_id": "high_speed_freight_true_false",
            "position": "4",
            "insertion_point": "讲完高铁只拉客、重载只拉货以及四类铁路对比后插入",
            "kind": "true_false_misconception",
            "prompt": "判断对错：高铁速度快，所以通常适合承担大宗货运列车运输。",
            "response_schema": {"field_type": "true_false"},
            "blocking": True,
            "continue_on_submit": True,
            "continuation_hint": "如果学生选对，确认高铁和货运需求冲突；如果选错，补讲线路平顺度、安全标准、轴重和运营组织差异。",
        },
        {
            "interaction_id": "high_speed_freight_reasoning",
            "position": "5",
            "insertion_point": "讲完高铁只拉客、重载只拉货以及四类铁路对比后插入",
            "kind": "explain_in_own_words",
            "prompt": "用自己的话讲：为什么高铁一般不跑货运列车？",
            "response_schema": {"field_type": "short_text"},
            "blocking": True,
            "continue_on_submit": True,
            "continuation_hint": "针对学生解释补充线路平顺度、安全标准、运营组织和客货需求差异。",
        },
    ]


def real_template() -> dict[str, Any]:
    return {
        "teacher_intent": "让铁路数智化部门新人用大白话讲清中国铁路四大类型、速度/功能差异、业务需求映射，以及八纵八横路网概念。",
        "prompt_template": REAL_RAILWAY_LESSON_GUIDANCE,
        "concept": "铁路行业基本格局与分类",
        "audience": "铁路数智化部门新人",
        "material_refs": real_material_refs(),
        "media_refs": [],
        "generation_options": {
            "model": REAL_MODEL,
            "temperature": 0.1,
            "interaction_mode": "checkpoint",
            "blocking_checkpoint": True,
            "interaction_points": real_interaction_points(),
        },
        "context_policy": {
            "allowed_context": [
                "course_title",
                "chapter_title",
                "outline_title",
                "teacher_material_refs",
                "teacher_media_refs",
                "learning_progress",
                "prior_learning_summary",
                "tokui_responses",
                "course_profile_variables",
            ]
        },
    }


def create_real_course_tree(client: ApiClient, stamp: str) -> dict[str, str]:
    course = require_api_ok(
        client.request(
            "PUT",
            "/api/shifu/shifus",
            json_body={
                "name": f"铁路行业基本格局与分类真实课程 {stamp}",
                "description": "由真实铁路课程脚本驱动的 TokUI 课程验收",
                "avatar": "",
            },
            token=True,
        ),
        "create real railway course",
    )
    shifu_bid = str(course.get("bid") or "")
    chapter = require_api_ok(
        client.request(
            "PUT",
            f"/api/shifu/shifus/{shifu_bid}/outlines",
            json_body={
                "parent_bid": "",
                "name": "模块一：铁路行业基础",
                "description": "",
                "type": "guest",
                "index": 1,
                "is_hidden": False,
            },
            token=True,
        ),
        "create real railway chapter",
    )
    lesson = require_api_ok(
        client.request(
            "PUT",
            f"/api/shifu/shifus/{shifu_bid}/outlines",
            json_body={
                "parent_bid": chapter.get("bid"),
                "name": "小节 1：铁路行业基本格局与分类",
                "description": "",
                "type": "trial",
                "index": 1,
                "is_hidden": False,
            },
            token=True,
        ),
        "create real railway lesson",
    )
    return {
        "shifu_bid": shifu_bid,
        "chapter_bid": str(chapter.get("bid") or ""),
        "outline_bid": str(lesson.get("bid") or ""),
    }


def count_terms(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


ANSWER_CASES = ("correct", "incorrect", "vague", "off_topic")


def answer_for_field(field: dict[str, Any], index: int, answer_case: str) -> Any:
    field_text = json.dumps(field, ensure_ascii=False)
    field_type = str(field.get("field_type") or "").strip()
    options = field.get("options") if isinstance(field.get("options"), list) else []

    def option_value_containing(*terms: str, default: str = "") -> str:
        for option in options:
            if not isinstance(option, dict):
                continue
            option_text = json.dumps(option, ensure_ascii=False)
            if any(term in option_text for term in terms):
                return str(option.get("value") or "")
        return default or str(options[0].get("value") if options and isinstance(options[0], dict) else "")

    if field_type == "single_choice":
        if answer_case == "correct":
            if "市域" in field_text or "通勤" in field_text:
                return option_value_containing("城际", "intercity")
            if "万吨" in field_text or "重载" in field_text:
                return option_value_containing("重载", "heavy_haul")
        return option_value_containing("高铁", "高速", "high_speed")

    if field_type == "multi_choice":
        if answer_case == "correct":
            selected = [
                option_value_containing("万吨", "ten_thousand"),
                option_value_containing("大宗", "bulk"),
                option_value_containing("轴重", "axle"),
            ]
            return [value for value in selected if value]
        if answer_case == "incorrect":
            return [option_value_containing("通勤", "commute")]
        if answer_case == "vague":
            return [option_value_containing("万吨", "ten_thousand")]
        return []

    if field_type == "true_false":
        return answer_case == "incorrect"

    if answer_case == "incorrect":
        return "这肯定属于高铁，因为高铁速度最快，所以所有高级系统都应该先用在高铁。"
    if answer_case == "vague":
        return "可能是重载铁路吧，但我只知道它比较重，和制动系统有关，具体为什么还说不清楚。"
    if answer_case == "off_topic":
        return "我坐过高铁，觉得座椅挺舒服，车站也很大。"
    if "万吨" in field_text or "重载" in field_text or index == 0:
        return "这属于重载铁路，因为万吨列车、大宗货运、制动系统健康预测都对应高轴重和设备寿命管理。"
    if "市域" in field_text or "通勤" in field_text or index == 1:
        return "这大概率是城际铁路，因为它服务城市群通勤，重点是高频发车、短站距和客流预测。"
    return "高铁一般不跑货运，因为它主要服务高速客运，对线路平顺度、安全冗余和运营组织要求很高，货运会带来轴重、停靠和调度冲突。"


def build_responses(schema: list[dict[str, Any]], answer_case: str) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for index, field in enumerate(schema):
        if not isinstance(field, dict):
            continue
        field_id = str(field.get("field_id") or "").strip()
        if not field_id:
            continue
        responses.append(
            {
                "field_id": field_id,
                "field_type": str(field.get("field_type") or "short_text"),
                "value": answer_for_field(field, index, answer_case),
            }
        )
    return responses


def feedback_terms_for_case(answer_case: str) -> list[str]:
    if answer_case == "correct":
        return ["答得对", "判断正确", "正确", "很准确", "回答很准确", "理解得很到位"]
    if answer_case == "incorrect":
        return ["这里有误区", "误区", "不属于高铁", "不是高铁", "重载铁路"]
    if answer_case == "vague":
        return ["回答不够具体", "还不够具体", "含糊", "不够具体", "太笼统", "比较笼统", "对比例子", "需要区分", "需要更明确", "抓住关键词"]
    return ["答非所问", "先回到问题", "回到原问题", "拉回", "有点跑题", "没有回答问题", "与问题无关", "和问题无关", "问题无关", "题目问的是", "先看题目关键词"]


def run_real_course_scenario(client: ApiClient, answer_case: str) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    recorder = ScenarioRecorder(f"real_railway_course_{answer_case}")
    ids = create_real_course_tree(client, f"{answer_case}_{stamp}")
    template = real_template()

    saved = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{ids['shifu_bid']}/outlines/{ids['outline_bid']}/tokui-template",
            json_body=template,
            token=True,
            timeout=60,
        ),
        "save real railway template",
    )
    saved_prompt = str(saved.get("prompt_template") or "")
    recorder.check(
        "teacher_guidance_is_full_real_railway_article",
        len(saved_prompt) >= 3000
        and count_terms(
            saved_prompt,
            ["高速铁路", "城际铁路", "客货共线", "重载铁路", "八纵八横", "素材插入位置"],
        )
        >= 6,
        "saved teacher guidance must be the full real railway lesson, not a short placeholder",
        {"prompt_len": len(saved_prompt), "prompt_prefix": saved_prompt[:300]},
    )
    recorder.check(
        "teacher_design_has_real_materials_and_interactions",
        len(saved.get("material_refs") or []) == 3
        and len(saved.get("interaction_points") or []) >= 5,
        "real lesson stores three material placements and multiple Feynman checks",
        {
            "material_refs": saved.get("material_refs"),
            "interaction_points": saved.get("interaction_points"),
        },
    )
    saved_interaction_types = {
        str((point.get("response_schema") or {}).get("field_type") or "")
        for point in saved.get("interaction_points") or []
        if isinstance(point, dict)
    }
    recorder.check(
        "teacher_design_has_all_rich_question_types",
        {"short_text", "single_choice", "multi_choice", "true_false"}.issubset(
            saved_interaction_types
        ),
        "real persisted teacher design must include short answer, single choice, multiple choice, and true/false checkpoints",
        {
            "saved_interaction_types": sorted(saved_interaction_types),
            "interaction_points": saved.get("interaction_points"),
        },
    )

    publish = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{ids['shifu_bid']}/publish",
            json_body={},
            token=True,
            timeout=120,
        ),
        "publish real railway course",
    )

    learner_1 = require_api_ok(
        client.request(
            "GET",
            f"/api/learn/shifu/{ids['shifu_bid']}/outlines/{ids['outline_bid']}/tokui",
            token=True,
            timeout=180,
        ),
        "generate real railway learner artifact",
    )
    dsl_1 = str(learner_1.get("dsl") or "")
    schema_1 = learner_1.get("interaction_schema") or []
    continuing_fields_1 = [
        field
        for field in schema_1
        if isinstance(field, dict)
        and (field.get("blocking") or field.get("continue_on_submit"))
    ]
    recorder.check(
        "learner_generation_uses_real_railway_content",
        learner_1.get("validation_status") == "validated"
        and "E2E_TEMPLATE_MARKER" not in dsl_1
        and count_terms(dsl_1, ["高速铁路", "城际铁路", "客货共线", "重载铁路"]) >= 3
        and len(schema_1) >= 1,
        "first learner artifact must be validated, contain real railway terms, and expose learner checkpoints",
        {
            "validation_status": learner_1.get("validation_status"),
            "dsl_len": len(dsl_1),
            "schema": schema_1,
            "dsl_prefix": dsl_1[:700],
        },
    )
    recorder.check(
        "first_runtime_uses_in_flow_checkpoint_not_question_dump",
        len(continuing_fields_1) == 1,
        "first runtime artifact should teach to the next in-flow checkpoint, not dump all lesson interactions together",
        {"schema": schema_1, "dsl_prefix": dsl_1[:900]},
    )
    recorder.check(
        "first_runtime_uses_richer_tokui_presentation",
        count_terms(dsl_1, ["[callout", "[table", "[row", "[steps", "[desc"]) >= 1,
        "real learner artifact should use supported TokUI structure beyond plain paragraphs",
        {"dsl_prefix": dsl_1[:1200]},
    )

    responses = build_responses(schema_1, answer_case)
    recorder.check(
        "real_course_has_submittable_schema",
        len(responses) >= 1,
        "real generated schema must provide at least one submittable learner answer",
        schema_1,
    )
    response_1 = require_api_ok(
        client.request(
            "POST",
            f"/api/learn/shifu/{ids['shifu_bid']}/outlines/{ids['outline_bid']}/tokui/responses",
            json_body={
                "tokui_artifact_bid": learner_1.get("tokui_artifact_bid"),
                "responses": responses,
            },
            token=True,
            timeout=60,
        ),
        "submit real railway learner answers",
    )
    recorder.check(
        "real_answers_are_saved_and_request_continuation",
        response_1.get("saved") == len(responses)
        and response_1.get("continue_required") is True,
        "submitting real railway answers should persist and request continuation",
        response_1,
    )

    learner_2 = require_api_ok(
        client.request(
            "GET",
            f"/api/learn/shifu/{ids['shifu_bid']}/outlines/{ids['outline_bid']}/tokui",
            token=True,
            timeout=180,
        ),
        "generate real railway continuation",
    )
    dsl_2 = str(learner_2.get("dsl") or "")
    chain = learner_2.get("artifact_chain") or []
    answered_field_ids = {
        str(response.get("field_id") or "")
        for response in responses
        if isinstance(response, dict)
    }
    schema_2 = learner_2.get("interaction_schema") or []
    repeated_answered_fields = [
        str(field.get("field_id") or "")
        for field in schema_2
        if isinstance(field, dict)
        and str(field.get("field_id") or "") in answered_field_ids
    ]
    recorder.check(
        "real_continuation_preserves_chain_and_uses_answer_context",
        learner_2.get("validation_status") == "validated"
        and learner_2.get("tokui_artifact_bid") != learner_1.get("tokui_artifact_bid")
        and len(chain) >= 2
        and "E2E_TEMPLATE_MARKER" not in dsl_2
        and count_terms(dsl_2 + json.dumps(learner_2, ensure_ascii=False), ["重载铁路", "城际铁路", "高铁"]) >= 1,
        "continuation must append a new validated artifact, preserve prior chain, and use real answer context",
        {
            "round1_artifact": learner_1.get("tokui_artifact_bid"),
            "round2_artifact": learner_2.get("tokui_artifact_bid"),
            "chain_count": len(chain),
            "dsl_prefix": dsl_2[:700],
        },
    )
    expected_feedback_terms = feedback_terms_for_case(answer_case)
    recorder.check(
        "real_continuation_uses_differentiated_feedback",
        any(term in dsl_2 for term in expected_feedback_terms),
        "continuation must diagnose answer quality instead of mechanically moving on",
        {
            "answer_case": answer_case,
            "expected_terms": expected_feedback_terms,
            "submitted_responses": responses,
            "dsl_prefix": dsl_2[:900],
        },
    )
    recorder.check(
        "real_continuation_moves_to_later_flow_instead_of_repeating_checkpoint",
        not repeated_answered_fields,
        "continuation should continue after the submitted in-flow checkpoint, not ask the same checkpoint again",
        {"answered_field_ids": sorted(answered_field_ids), "schema_2": schema_2},
    )

    recorder.evidence["ids"] = ids
    recorder.evidence["publish"] = publish
    recorder.evidence["learnerArtifacts"] = {
        "round1": learner_1,
        "round2": learner_2,
    }
    recorder.evidence["submittedResponses"] = responses
    return {
        "scenario": recorder.to_result(),
        "ids": ids,
        "learner_url": f"{TARGET_URL}/c/{ids['shifu_bid']}?lessonid={ids['outline_bid']}",
    }


async def main() -> int:
    result: dict[str, Any] = {
        "target_url": TARGET_URL,
        "model": REAL_MODEL,
        "started_at": datetime.now().isoformat(),
        "passed": False,
        "scenarios": [],
    }
    validator_process: subprocess.Popen[bytes] | None = None
    try:
        validator_process = start_tokui_validator_if_needed()
        client = ApiClient(resolve_api_base_url(TARGET_URL))
        login = client.login()
        result["login"] = login
        if not client.token:
            raise CheckFailed(f"login did not return token: {login}")
        learner_urls: dict[str, str] = {}
        ids_by_case: dict[str, dict[str, str]] = {}
        for answer_case in ANSWER_CASES:
            scenario_result = run_real_course_scenario(client, answer_case)
            result["scenarios"].append(scenario_result["scenario"])
            ids_by_case[answer_case] = scenario_result["ids"]
            learner_urls[answer_case] = scenario_result["learner_url"]
        result["ids_by_case"] = ids_by_case
        result["learner_urls"] = learner_urls
        result["ids"] = ids_by_case.get("correct")
        result["learner_url"] = learner_urls.get("correct")
        result["passed"] = all(scenario.get("passed") for scenario in result["scenarios"])
    except Exception as exc:
        result.update(
            {
                "passed": False,
                "error": f"{exc.__class__.__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if validator_process is not None:
            validator_process.terminate()
            try:
                validator_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                validator_process.kill()

    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": result.get("passed"),
                "model": result.get("model"),
                "learner_url": result.get("learner_url"),
                "result_path": str(RESULT_PATH),
                "scenarios": [
                    {
                        "name": scenario.get("name"),
                        "passed": scenario.get("passed"),
                        "failed_checks": [
                            check
                            for check in scenario.get("checks", [])
                            if not check.get("passed")
                        ],
                    }
                    for scenario in result.get("scenarios", [])
                ],
                "error": result.get("error"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
