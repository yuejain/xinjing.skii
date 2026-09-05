#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心镜博士 · 随机生成引擎（纯代码逻辑，与 AI 解读引擎彻底解耦）

铁律：随机性即诚意。
本引擎不经过 AI 推理，产出"纯粹的、不可预设的"随机结果（牌名/卦名/门位），
AI 解读引擎只负责接收结果做心理学翻译，严禁 AI 自行"想一张牌"。

混合熵源算法（每次提问绝对独立随机，无法被 AI 操控）：
    seed = SHA256( user_id | 精确时间戳 | 用户输入前10字符 | random.getrandbits(128) )
    - user_id 与输入文本参与熵源：让用户感到"被回应"的结构延续感；
    - getrandbits(128)（OS 熵播种）：保证每次结果绝对独立、不可预判；
    - SHA256 散列：保证均匀分布，映射到牌组（78 塔罗 / 64 卦 / 24 如尼 / 8 门）。

奇门八门特殊规则（天时 + 人事 复合）：
    - 天时（固定）：按当前北京时间锁定值使门所在宫位，每 2 小时（一个时辰）轮转一宫；
    - 人事（随机）：叠加用户输入哈希值产生偏移，决定"门迫"或"门制"；
    - 最终门位 = 天时 + 人事，尊重传统且无法提前预设。

种子日志：每次抽牌将 {时间戳, 哈希种子, 模式, 结果} 追加写入
    ../memory/logs/<user_hash>.jsonl，用户质疑时可调出日志解释算法构成。

用法：
  python draw.py --mode tarot  --user-id <ID> --text "<用户本轮输入>" [--count 1|3] [--json]
  python draw.py --mode iching --user-id <ID> --text "<用户本轮输入>" [--json]
  python draw.py --mode rune   --user-id <ID> --text "<用户本轮输入>" [--count 1|3] [--json]
  python draw.py --mode qimen  --user-id <ID> --text "<用户本轮输入>" [--json]
  python draw.py --mode hash   --user-id <ID>
  python draw.py --mode log    --user-id <ID> [--tail 5]      # 查看该用户种子日志

纯标准库实现，无第三方依赖。
"""

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "memory", "logs"))
COMBO_DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "references", "qimen_72_combos.json"))

SCHEMA_VERSION = "2.0"

# ---------------------------------------------------------------- 牌库数据

TAROT_MAJOR = [
    ("愚人 The Fool", "起点的天真与勇气，对未知的开放"),
    ("魔术师 The Magician", "意志与资源整合"),
    ("女祭司 The High Priestess", "潜意识智慧，内在直觉"),
    ("皇后 The Empress", "滋养与接纳，自我照顾"),
    ("皇帝 The Emperor", "秩序、责任与边界"),
    ("教皇 The Hierophant", "传统与信念系统"),
    ("恋人 The Lovers", "价值选择与内在整合"),
    ("战车 The Chariot", "意志驱动与硬撑"),
    ("力量 Strength", "温柔的力量，驯服而非压制"),
    ("隐士 The Hermit", "独处与内省"),
    ("命运之轮 Wheel of Fortune", "周期感与时机"),
    ("正义 Justice", "平衡与自我审判"),
    ("倒吊人 The Hanged Man", "视角转换，悬置的智慧"),
    ("死神 Death", "阶段终结与告别"),
    ("节制 Temperance", "调和、耐心与融合"),
    ("恶魔 The Devil", "束缚与欲望的诚实"),
    ("高塔 The Tower", "价值观重建：既定框架松动后的重建"),
    ("星星 The Star", "废墟后的希望与信念"),
    ("月亮 The Moon", "恐惧与幻象之辨"),
    ("太阳 The Sun", "生命力与真我"),
    ("审判 Judgement", "内在召唤与觉醒"),
    ("世界 The World", "完成与整合"),
]

TAROT_SUITS = {
    "Wands": ("权杖", "火：行动力、热情、事业冲动"),
    "Cups": ("圣杯", "水：情感、关系、内在流动"),
    "Swords": ("宝剑", "风：思维、冲突、语言与真相"),
    "Pentacles": ("星币", "土：物质、身体、现实根基"),
}

TAROT_RANKS = {
    "Ace": "起点", "Two": "平衡", "Three": "扩张", "Four": "稳定",
    "Five": "冲突", "Six": "修复", "Seven": "考验", "Eight": "调整",
    "Nine": "临近完成", "Ten": "完成与重启",
}

TAROT_COURT = {
    "Page": "学习心态", "Knight": "行动姿态",
    "Queen": "内化成熟", "King": "外化掌控",
}

BAGUA = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]  # 先天数 1-8

ICHING = [
    # (卦名, 心理映射)  索引 = (上卦-1)*8 + (下卦-1)
    ("乾为天", "自强，警惕过度刚进"), ("天泽履", "谨慎前行，如履薄冰的自我要求"),
    ("天火同人", "寻找志同道合者"), ("天雷无妄", "真诚无伪"),
    ("天风姤", "相遇与诱惑"), ("天水讼", "冲突与沟通方式"),
    ("天山遁", "战略后退不是逃跑"), ("天地否", "蛰伏蓄力，不与世界对抗"),
    ("泽天夬", "决断时刻"), ("兑为泽", "喜悦与表达"),
    ("泽火革", "变革的勇气"), ("泽雷随", "跟随与自主的平衡"),
    ("泽风大过", "非常之时，非常承担"), ("泽水困", "受限中的选择空间：困顿中仍有可动之处"),
    ("泽山咸", "感应与亲密"), ("泽地萃", "凝聚与连接"),
    ("火天大有", "丰盛与分享"), ("火泽睽", "差异可以共存"),
    ("离为火", "依附与清明"), ("火雷噬嗑", "破除阻碍"),
    ("火风鼎", "更新与稳固"), ("火水未济", "未完成的美，永远在路上"),
    ("火山旅", "漂泊与归属感"), ("火地晋", "进取与晋升"),
    ("雷天大壮", "强大时勿亢进"), ("雷泽归妹", "关系中的位置感"),
    ("雷火丰", "丰盛时的不安"), ("震为雷", "惊雷与唤醒"),
    ("雷风恒", "持久的承诺"), ("雷水解", "松绑与释放"),
    ("雷山小过", "小事可为，大事缓行"), ("雷地豫", "顺势而为"),
    ("风天小畜", "小步积累"), ("风泽中孚", "内在诚信"),
    ("风火家人", "家庭与角色期待"), ("风雷益", "增益与共好"),
    ("巽为风", "渗透与柔顺"), ("风水涣", "涣散后重建连接"),
    ("风山渐", "循序渐进"), ("风地观", "观察与自省"),
    ("水天需", "等待的智慧"), ("水泽节", "节制与分寸"),
    ("水火既济", "完成后的守成"), ("水雷屯", "初创艰难，先扎根"),
    ("水风井", "深泉与稳定价值"), ("坎为水", "险中修习：水不盈科不行，困难是学习形态"),
    ("水山蹇", "艰险中的互助"), ("水地比", "归属与亲附"),
    ("山天大畜", "蓄力待发"), ("山泽损", "减法的智慧"),
    ("山火贲", "表里之辨"), ("山雷颐", "滋养自己，谨言"),
    ("山风蛊", "清理积弊，修复旧问题"), ("山水蒙", "求知与启蒙"),
    ("艮为山", "止与静，暂停的智慧"), ("山地剥", "剥落后必有重生"),
    ("地天泰", "通达时保持谦逊"), ("地泽临", "面对与亲近"),
    ("地火明夷", "韬光养晦"), ("地雷复", "回归初心"),
    ("地风升", "渐进上升"), ("地水师", "纪律与团队"),
    ("地山谦", "谦逊的力量"), ("坤为地", "承载，练习设立边界"),
]

RUNES = [
    ("Fehu ᚠ", "资源与安全感"), ("Uruz ᚢ", "原始生命力，被压抑的野性"),
    ("Thurisaz ᚦ", "阻力与边界"), ("Ansuz ᚨ", "语言、启示与表达"),
    ("Raido ᚱ", "旅程与节奏"), ("Kenaz ᚲ", "火把、技能与领悟"),
    ("Gebo ᚷ", "给予与关系的对等"), ("Wunjo ᚹ", "喜悦的合法性"),
    ("Hagalaz ᚺ", "破坏与重建：旧结构碎裂后的新材料"), ("Nauthiz ᚾ", "匮乏与真实需要"),
    ("Isa ᛁ", "停滞与沉淀：冰封期也是澄清期"), ("Jera ᛃ", "收获与周期感"),
    ("Eihwaz ᛇ", "韧性与转化"), ("Perthro ᛈ", "未知与敞开"),
    ("Algiz ᛉ", "保护与直觉"), ("Sowilo ᛋ", "内在太阳与胜利感"),
    ("Tiwaz ᛏ", "正义与勇气"), ("Berkano ᛒ", "生长与孕育"),
    ("Ehwaz ᛖ", "信任与合作"), ("Mannaz ᛗ", "自我与群体的平衡"),
    ("Laguz ᛚ", "流动与潜意识"), ("Ingwaz ᛜ", "种子与酝酿期"),
    ("Dagaz ᛞ", "黎明与转化"), ("Othala ᛟ", "传承与归属"),
]

# 奇门八门：门名、所配后天宫位、五行、心理映射
QIMEN_GATES = [
    ("休门", 1, "水", "休整与回血，暂停的合法性"),
    ("生门", 8, "土", "生长与机遇，资源所在"),
    ("伤门", 3, "木", "伤耗与冲动，行动的反噬"),
    ("杜门", 4, "木", "封闭与保密，信息静默"),
    ("景门", 9, "火", "表演与虚华，外在展示"),
    ("死门", 2, "土", "停滞与终结，旧阶段收束"),
    ("惊门", 7, "金", "惊扰与警觉，恐惧的讯号"),
    ("开门", 6, "金", "开启与破局，新阶段的闸门"),
]

WUXING = {"木": 0, "火": 1, "土": 2, "金": 3, "水": 4}
# 五行生克：生 = (我生者)，克 = (我克者)
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# 后天八卦宫位数字 → 宫五行（1坎水 8艮土 3震木 4巽木 9离火 2坤土 7兑金 6乾金）
# 注：星门联动模式下八门不落宫，此表保留供扩展用
PALACE_WUXING = {1: "水", 8: "土", 3: "木", 4: "木", 9: "火", 2: "土", 7: "金", 6: "金"}

# 奇门九星：星名、别称、五行、传统意象、心理动力学映射（天盘·内在禀赋）
NINE_STARS = [
    ("天蓬", "贪狼", "水", "盗贼·大风险", "原始求生欲的放大器：对危险与机会都极度敏感，本能趋利避害；焦虑时容易过度警觉或孤注一掷"),
    ("天芮", "巨门", "土", "疾病·问题", "内在批判家的雷达：天生擅长发现问题、预判漏洞，但容易陷入问题无底洞，把自己的身心当成待修的病体"),
    ("天冲", "禄存", "木", "雷震·爆发", "压抑愤怒的活火山：行动力与爆发力极强，压力下容易一言不合就开干，事后又后悔冲动"),
    ("天辅", "文曲", "木", "教化·仁慈", "认知防御的堡垒：习惯用知识和道理消解恐惧；一旦知识失效，会陷入懂了很多却依然过不好的巨大崩塌"),
    ("天禽", "廉贞", "土", "中正·帝王", "内在最高审判庭：极度追求公平与秩序，对自己的道德要求极高；焦虑往往源于我这样做是不是不够体面/正确"),
    ("天心", "武曲", "金", "谋略·医疗", "理性工程师的人格面具：擅长拆解问题、制定计划；当问题无法被拆解时（如情绪问题），陷入工具失灵的恐慌"),
    ("天柱", "破军", "金", "毁坏·破败", "崩塌重建的使徒：天生对废墟有亲近感，压力下习惯先打碎再重来；容易把打碎当成唯一出路，忽略修补的可能"),
    ("天任", "左辅", "土", "包容·承载", "过度承受的骆驼：本能地扛起责任，像大地一样包容别人；所有重量都压在脊梁上，焦虑来自万斤压顶的窒息感"),
    ("天英", "右弼", "火", "热烈·虚幻", "表演型灵魂的火苗：需要被看见才能确认自己存在；压力下容易过度在意形象，或陷入我是不是在演一场空戏的虚无"),
]

EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]


# ---------------------------------------------------------------- 随机生成引擎


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def make_seed(user_id: str, text: str, now: datetime = None) -> dict:
    """
    混合熵源，每次调用绝对独立随机：
    seed = SHA256(user_id | 精确时间戳 | 输入前10字符 | random.getrandbits(128))
    返回 {seed, timestamp, user_hash, input_len, input_prefix_hash}
    """
    if now is None:
        now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")
    text_prefix = (text or "")[:10]
    entropy_string = f"{user_id}_{timestamp}_{text_prefix}_{random.getrandbits(128)}"
    seed = sha256_hex(entropy_string)
    return {
        "seed": seed,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "user_hash": sha256_hex(user_id)[:16],
        "input_len": len(text or ""),
        "input_prefix_hash": sha256_hex(text_prefix)[:16],
    }


def index_from_seed(seed: str, purpose: str, pool_size: int) -> int:
    """从种子派生子哈希，均匀映射到 [0, pool_size)。"""
    sub = sha256_hex(f"{seed}|{purpose}")
    return int(sub[:8], 16) % pool_size


def seeded_rng(seed: str, purpose: str) -> random.Random:
    sub = int(sha256_hex(f"{seed}|{purpose}"), 16)
    return random.Random(sub)


def draw_without_replacement(pool: list, count: int, rng: random.Random) -> list:
    pool = list(pool)
    picked = []
    for _ in range(min(count, len(pool))):
        i = rng.randrange(len(pool))
        picked.append(pool.pop(i))
    return picked


# ---------------------------------------------------------------- 各模式


def draw_tarot(seed: str, count: int) -> dict:
    deck = []
    for name, mapping in TAROT_MAJOR:
        deck.append({"type": "大阿卡纳", "name": name, "mapping": mapping})
    for suit_en, (suit_cn, theme) in TAROT_SUITS.items():
        for rank, stage in TAROT_RANKS.items():
            deck.append({
                "type": "小阿卡纳",
                "name": f"{rank} of {suit_en}（{suit_cn}）",
                "mapping": f"{theme}；数字阶段：{stage}",
            })
        for court, face in TAROT_COURT.items():
            deck.append({
                "type": "小阿卡纳",
                "name": f"{court} of {suit_en}（{suit_cn}）",
                "mapping": f"{theme}；人格面：{face}",
            })
    rng = seeded_rng(seed, "tarot")
    cards = draw_without_replacement(deck, count, rng)
    for c in cards:
        c["orientation"] = "正位" if rng.random() < 0.5 else "逆位"
        if c["orientation"] == "逆位":
            c["mapping"] = c["mapping"] + "（该能量处于隐性或被压抑状态，未被承认或过度补偿）"
    return {"mode": "tarot", "count": len(cards), "cards": cards}


def draw_iching(seed: str) -> dict:
    upper = index_from_seed(seed, "upper", 8) + 1
    lower = index_from_seed(seed, "lower", 8) + 1
    moving = index_from_seed(seed, "moving", 6) + 1
    idx = (upper - 1) * 8 + (lower - 1)
    name, mapping = ICHING[idx]

    def trigram_bits(n):  # 三爻自下而上，1=阳 0=阴
        return [(n >> b) & 1 for b in range(3)]

    upper_bits = trigram_bits(upper - 1)
    lower_bits = trigram_bits(lower - 1)
    hexagram_bits = lower_bits + upper_bits  # 自下而上六爻
    pos = moving - 1
    hexagram_bits[pos] ^= 1
    new_lower = sum(b << i for i, b in enumerate(hexagram_bits[0:3])) + 1
    new_upper = sum(b << i for i, b in enumerate(hexagram_bits[3:6])) + 1
    new_idx = (new_upper - 1) * 8 + (new_lower - 1)
    changed_name, changed_mapping = ICHING[new_idx]

    return {
        "mode": "iching",
        "upper_trigram": BAGUA[upper - 1],
        "lower_trigram": BAGUA[lower - 1],
        "moving_line": moving,
        "hexagram": {"name": name, "mapping": mapping},
        "changed_hexagram": {"name": changed_name, "mapping": changed_mapping},
    }


def draw_rune(seed: str, count: int) -> dict:
    rng = seeded_rng(seed, "rune")
    picked = draw_without_replacement(RUNES, count, rng)
    return {
        "mode": "rune",
        "count": len(picked),
        "runes": [{"name": n, "mapping": m} for n, m in picked],
    }


def current_earthly_branch(now: datetime = None) -> tuple:
    """当前北京时间对应的时辰（每 2 小时轮转一宫）与时辰序。"""
    if now is None:
        now = datetime.now()
    branch_index = ((now.hour + 1) // 2) % 12  # 23-1 子=0 ... 21-23 亥=11
    return EARTHLY_BRANCHES[branch_index], branch_index


def wuxing_relation(a: str, b: str) -> str:
    """五行关系：a 对 b 的作用。返回：我克(门迫方向)、克我、我生、生我、比和"""
    if a == b:
        return "比和"
    if WUXING_KE[a] == b:
        return "克"  # a 克 b
    if WUXING_KE[b] == a:
        return "被克"  # b 克 a
    if WUXING_SHENG[a] == b:
        return "生"  # a 生 b
    return "被生"  # b 生 a


def load_combo_db() -> dict:
    """加载 72 组合速查表数据库（9 星 × 8 门，summary/action/taboo 三字段）。"""
    try:
        with open(COMBO_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("qimen_star_door_72", {})
    except (OSError, ValueError):
        return {}


def lookup_combo(star_name: str, gate_name: str) -> dict:
    """以『星名_门名』为键查询 72 组合库，返回 summary/action/taboo。"""
    db = load_combo_db()
    return db.get(star_name + "星", {}).get(gate_name)


def draw_qimen(user_id: str, text: str, now: datetime = None) -> dict:
    """
    奇门 · 星门联动双随机抽签：
    - 九星（天时·内在禀赋）：熵源 = 用户ID + 当前日期(年月日) + 问题关键词哈希 + 当前时辰，独立抽取 1/9；
    - 八门（人事·当前心流）：熵源 = 输入文本尾数 + 分钟时间戳，独立抽取 1/8；
    - 星门五行相克时强制触发『星门冲克』话术；
    - 输出强制格式：『天星·[星名]』+『人门·[门名]』。
    """
    if now is None:
        now = datetime.now()
    branch, _ = current_earthly_branch(now)

    # --- 九星抽取：用户ID + 年月日 + 关键词哈希 + 时辰 ---
    date_str = now.strftime("%Y%m%d")
    keyword_hash = sha256_hex((text or "")[:10])[:16]
    star_entropy = f"{user_id}|{date_str}|{keyword_hash}|{branch}时"
    star_idx = int(sha256_hex(star_entropy)[:8], 16) % len(NINE_STARS)
    star = NINE_STARS[star_idx]

    # --- 八门抽取：输入文本尾数 + 分钟时间戳（独立熵源） ---
    minute_stamp = now.strftime("%Y%m%d%H%M")
    text_tail = (text or "")[-2:]
    gate_entropy = f"{text_tail}|{minute_stamp}"
    gate_idx = int(sha256_hex(gate_entropy)[:8], 16) % len(QIMEN_GATES)
    gate = QIMEN_GATES[gate_idx]

    # --- 星门五行生克 ---
    star_wx, gate_wx = star[2], gate[2]
    relation = wuxing_relation(star_wx, gate_wx)
    chong_ke = relation in ("克", "被克")

    # --- 72 组合速查表联动查询 ---
    combo = lookup_combo(star[0], gate[0])

    return {
        "mode": "qimen",
        "engine": "star-gate-linked",
        "shichen": branch + "时",
        "star": {
            "name": star[0],
            "alias": star[1],
            "wuxing": star_wx,
            "imagery": star[3],
            "mapping": star[4],
            "note": "天盘·内在禀赋（熵源：用户ID+年月日+关键词哈希+时辰）",
        },
        "gate": {
            "name": gate[0],
            "palace": gate[1],
            "wuxing": gate_wx,
            "mapping": gate[3],
            "note": "人事·当前心流（熵源：输入文本尾数+分钟时间戳）",
        },
        "link": {
            "relation": relation,
            "chong_ke": chong_ke,
            "formula": "你的天星（禀赋）想用「{}」的方式应对现实，但当下的人门（状态）只能给出「{}」的环境。两者的摩擦/共振，就是你此刻心理张力的全部秘密。".format(star[0], gate[0]),
        },
        "chong_ke_script": (
            "你的天性和当前状态正在剧烈撕扯，这种撕裂感本身是最重要的信号——"
            "它在告诉你，你需要做一个比普通选择更底层的价值排序。"
            if chong_ke else None
        ),
        "combo": combo,  # 72 库查询结果：{summary, action, taboo} 或 None
    }


# ---------------------------------------------------------------- 种子日志


def append_log(entropy: dict, result: dict) -> str:
    """将 {时间戳, 哈希种子, 模式, 结果} 追加写入用户日志，供质疑时调出解释。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{entropy['user_hash']}.jsonl")
    record = {
        "timestamp": entropy["timestamp"],
        "seed": entropy["seed"],
        "mode": result["mode"],
        "result": result,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log_path


def read_log(user_hash: str, tail: int = 5) -> str:
    log_path = os.path.join(LOG_DIR, f"{user_hash}.jsonl")
    if not os.path.exists(log_path):
        return f"该用户（{user_hash}）暂无抽牌日志。"
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    return "\n".join(lines[-tail:])


# ---------------------------------------------------------------- 输出


def render(result: dict) -> str:
    """人类可读输出，供 AI 在会话中引用（AI 实际解读须参照 references/symbol_map.md）。"""
    lines = []
    if result["mode"] == "tarot":
        for i, c in enumerate(result["cards"], 1):
            lines.append(f"第 {i} 张：{c['name']}（{c['orientation']}）")
            lines.append(f"心理映射：{c['mapping']}")
    elif result["mode"] == "iching":
        lines.append(f"本卦：{result['lower_trigram']}下{result['upper_trigram']}上 · {result['hexagram']['name']}（动爻：第 {result['moving_line']} 爻）")
        lines.append(f"心理映射：{result['hexagram']['mapping']}")
        lines.append(f"变卦：{result['changed_hexagram']['name']} · {result['changed_hexagram']['mapping']}")
    elif result["mode"] == "rune":
        for i, r in enumerate(result["runes"], 1):
            lines.append(f"第 {i} 个符文：{r['name']}")
            lines.append(f"心理映射：{r['mapping']}")
    elif result["mode"] == "qimen":
        rel_cn = {"克": "星克门", "被克": "门克星", "生": "星生门", "被生": "门生星", "比和": "星门比和"}[result["link"]["relation"]]
        lines.append(f"『天星·{result['star']['name']}（{result['star']['alias']}·{result['star']['wuxing']}）』{result['star']['imagery']}")
        lines.append(f"禀赋映射：{result['star']['mapping']}")
        lines.append(f"『人门·{result['gate']['name']}（{result['gate']['wuxing']}）』")
        lines.append(f"心流映射：{result['gate']['mapping']}")
        lines.append(f"星门联动（{rel_cn}）：{result['link']['formula']}")
        if result["link"]["chong_ke"]:
            lines.append(f"⚠ 星门冲克：{result['chong_ke_script']}")
        if result.get("combo"):
            c = result["combo"]
            lines.append(f"🧭 72库速查（{result['star']['name']}星+{result['gate']['name']}）：")
            lines.append(f"精髓句：{c['summary']}")
            lines.append(f"今日专属微行动：{c['action']}")
            lines.append(f"特别禁忌：{c['taboo']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="心镜博士 · 随机生成引擎（纯代码，无 AI 参与）")
    parser.add_argument("--mode", required=True, choices=["tarot", "iching", "rune", "qimen", "hash", "log"])
    parser.add_argument("--user-id", default="anonymous", help="用户标识（无需真实身份，稳定即可）")
    parser.add_argument("--text", default="", help="用户本轮输入文本")
    parser.add_argument("--count", type=int, default=1, help="抽牌/符文数量（1 或 3）")
    parser.add_argument("--tail", type=int, default=5, help="log 模式：显示最近 N 条日志")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--no-log", action="store_true", help="本次不写入种子日志")
    args = parser.parse_args()

    if args.mode == "hash":
        print(sha256_hex(args.user_id)[:16])
        return 0

    if args.mode == "log":
        print(read_log(sha256_hex(args.user_id)[:16], args.tail))
        return 0

    entropy = make_seed(args.user_id, args.text)
    seed = entropy["seed"]
    if args.mode == "tarot":
        result = draw_tarot(seed, args.count)
    elif args.mode == "iching":
        result = draw_iching(seed)
    elif args.mode == "rune":
        result = draw_rune(seed, args.count)
    else:
        result = draw_qimen(args.user_id, args.text)

    if not args.no_log:
        append_log(entropy, result)

    if args.json:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "engine": "random-generator",
            "timestamp": entropy["timestamp"],
            "seed": seed,
            "user_hash": entropy["user_hash"],
            **result,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
