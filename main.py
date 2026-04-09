import discord
from discord.ext import commands
import os
import json
import random
import asyncio
from pathlib import Path
from datetime import datetime, date

# =========================
# 기본 설정
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

DUEL_FILE = DATA_DIR / "duel_stats.json"
TIMER_FILE = DATA_DIR / "timer_logs.json"
PROFILE_FILE = DATA_DIR / "user_profiles.json"

HORDE_BOT_ID = int(os.getenv("HORDE_BOT_ID", "0"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))  # 0이면 모든 채널 허용

active_duels = {}
pending_duels = {}
daily_progress = {}

# =========================
# 유틸
# =========================
def load_json(path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def can_talk_in_channel(channel_id: int):
    return TARGET_CHANNEL_ID == 0 or channel_id == TARGET_CHANNEL_ID


def today_str():
    return date.today().isoformat()


def get_duel_data():
    return load_json(DUEL_FILE, {})


def ensure_duel_user(user_id: int):
    data = get_duel_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "wins": 0,
            "losses": 0,
            "streak": 0,
            "best_streak": 0,
            "boss_wins": 0,
            "boss_losses": 0,
        }
        save_json(DUEL_FILE, data)
    return data


def get_profile_data():
    return load_json(PROFILE_FILE, {})


def ensure_profile(user_id: int):
    data = get_profile_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "stats": {
                "hp": 100,
                "atk": 10,
                "agi": 5,
            },
            "affinity": 0,
            "last_daily": "",
            "daily": None,
            "daily_done": False,
        }
        save_json(PROFILE_FILE, data)
    return data, uid


def change_affinity(user_id: int, amount: int):
    data, uid = ensure_profile(user_id)
    data[uid]["affinity"] = max(-100, min(100, data[uid].get("affinity", 0) + amount))
    save_json(PROFILE_FILE, data)
    return data[uid]["affinity"]


def add_stat_rewards(user_id: int, hp_gain: int = 0, atk_gain: int = 0, agi_gain: int = 0):
    data, uid = ensure_profile(user_id)
    data[uid]["stats"]["hp"] += hp_gain
    data[uid]["stats"]["atk"] += atk_gain
    data[uid]["stats"]["agi"] += agi_gain
    save_json(PROFILE_FILE, data)


def get_user_stats(user_id: int):
    data, uid = ensure_profile(user_id)
    return data[uid]["stats"]


def get_user_affinity(user_id: int):
    data, uid = ensure_profile(user_id)
    return data[uid].get("affinity", 0)


def affinity_tier_name(affinity: int):
    if affinity <= -50:
        return "경멸"
    if affinity < 0:
        return "무관심"
    if affinity < 30:
        return "관찰"
    if affinity < 70:
        return "인정"
    return "스카우트"


def get_daily_for_user(user_id: int):
    data, uid = ensure_profile(user_id)
    profile = data[uid]
    today = today_str()

    if profile.get("last_daily") != today:
        quest_pool = [
            {
                "type": "message",
                "goal": 10,
                "label": "메시지 10번 보내라.",
                "reward": {"hp": 5, "atk": random.randint(1, 2), "agi": 1},
            },
            {
                "type": "duel_participate",
                "goal": 1,
                "label": "결투 1회 참가해라.",
                "reward": {"hp": 5, "atk": random.randint(1, 2), "agi": 1},
            },
            {
                "type": "duel_win",
                "goal": 1,
                "label": "결투 1회 이겨라.",
                "reward": {"hp": 5, "atk": random.randint(1, 2), "agi": 2},
            },
            {
                "type": "boss_attempt",
                "goal": 1,
                "label": "게부라에게 한 번 덤벼라.",
                "reward": {"hp": 5, "atk": random.randint(1, 2), "agi": 1},
            },
            {
                "type": "boss_win",
                "goal": 1,
                "label": "게부라를 이겨봐라.",
                "reward": {"hp": 8, "atk": 2, "agi": 2},
            },
        ]
        quest = random.choice(quest_pool)
        profile["last_daily"] = today
        profile["daily"] = quest
        profile["daily_done"] = False
        save_json(PROFILE_FILE, data)

    return profile["daily"], profile.get("daily_done", False)


def increment_daily_progress(user_id: int, progress_type: str, amount: int = 1):
    quest, done = get_daily_for_user(user_id)
    if not quest or done:
        return None

    daily_progress.setdefault(str(user_id), {})
    current = daily_progress[str(user_id)].get(progress_type, 0)
    daily_progress[str(user_id)][progress_type] = current + amount

    if quest["type"] == progress_type and daily_progress[str(user_id)][progress_type] >= quest["goal"]:
        return complete_daily(user_id)
    return None


def complete_daily(user_id: int):
    data, uid = ensure_profile(user_id)
    quest = data[uid].get("daily")
    if not quest or data[uid].get("daily_done"):
        return None

    reward = quest["reward"]
    add_stat_rewards(user_id, reward.get("hp", 0), reward.get("atk", 0), reward.get("agi", 0))
    affinity = change_affinity(user_id, 5)

    data, uid = ensure_profile(user_id)
    data[uid]["daily_done"] = True
    save_json(PROFILE_FILE, data)

    return {
        "quest": quest,
        "reward": reward,
        "affinity": affinity,
    }


def update_record(winner_id: int, loser_id: int):
    data = get_duel_data()
    for uid in [str(winner_id), str(loser_id)]:
        if uid not in data:
            data[uid] = {
                "wins": 0,
                "losses": 0,
                "streak": 0,
                "best_streak": 0,
                "boss_wins": 0,
                "boss_losses": 0,
            }

    data[str(winner_id)]["wins"] += 1
    data[str(winner_id)]["streak"] += 1
    data[str(winner_id)]["best_streak"] = max(
        data[str(winner_id)]["best_streak"],
        data[str(winner_id)]["streak"]
    )

    data[str(loser_id)]["losses"] += 1
    data[str(loser_id)]["streak"] = 0
    save_json(DUEL_FILE, data)


def update_boss_record(user_id: int, won: bool):
    data = get_duel_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "wins": 0,
            "losses": 0,
            "streak": 0,
            "best_streak": 0,
            "boss_wins": 0,
            "boss_losses": 0,
        }
    if won:
        data[uid]["boss_wins"] += 1
    else:
        data[uid]["boss_losses"] += 1
    save_json(DUEL_FILE, data)


def get_affinity_line(affinity: int):
    if affinity <= -50:
        return random.choice(low_affinity_lines)
    if affinity < 0:
        return random.choice(low_mid_affinity_lines)
    if affinity < 30:
        return random.choice(mid_affinity_lines)
    if affinity < 70:
        return random.choice(high_affinity_lines)
    return random.choice(max_affinity_lines)


# =========================
# 대사 데이터
# =========================
start_lines = [
    "둘 다 준비해라.",
    "도망칠 생각이면 지금 해.",
    "싸울 거면 제대로 와라.",
    "말은 필요 없다. 시작이다.",
    "끝까지 서 있을 자신 있나?",
    "물러날 거면 지금이다.",
    "괜히 시작한 거 아니겠지.",
    "망설이면 진다.",
    "각오는 됐겠지.",
    "한 명은 반드시 쓰러진다."
]

attack_lines = [
    "느리다.",
    "그게 전부냐?",
    "빈틈이다.",
    "막을 수 있겠나?",
    "피할 수 있으면 피해봐.",
    "집중해라.",
    "지금이다.",
    "망설이지 마.",
    "끝을 봐라.",
    "흐름을 놓쳤군."
]

critical_lines = [
    "직격이다.",
    "끝내주지.",
    "버틸 수 있겠나?",
    "이건 아프다.",
    "제대로 들어갔다.",
    "피할 틈도 없었다.",
    "이게 차이다.",
    "여기서 무너진다.",
    "힘의 차이를 봐라."
]

win_lines = [
    "...버텼군.",
    "괜찮군. 인정한다.",
    "이겼다고 방심하지 마.",
    "그 정도면 합격이다.",
    "다음에도 그렇게 해봐라.",
    "나쁘지 않다.",
    "조금은 볼 만했어.",
    "여기까지 온 건 인정한다."
]

lose_lines = [
    "그 정도로는 부족하다.",
    "다시 와라.",
    "끝까지 못 버티는군.",
    "이게 네 한계냐?",
    "실망이다.",
    "그걸로 이길 생각이었나?",
    "아직 멀었다.",
    "다시 시작해라."
]

cancel_lines = [
    "도망쳤군.",
    "흥, 그럴 줄 알았다.",
    "겁났나?",
    "결국 피하는군.",
    "시작도 못 하고 끝났네.",
    "그 정도 각오였나."
]

win_streak_lines = [
    "계속 이기고 있군.",
    "흐름 탔다.",
    "멈출 생각은 없어 보이네.",
    "그 기세 유지해라.",
    "지금 상태 좋다."
]

low_affinity_lines = [
    "입만 살았군.",
    "말은 많은데 결과는 없네.",
    "그 상태로 계속 갈 생각이냐?",
    "관심 줄 가치도 없다.",
    "실망만 늘어간다."
]

low_mid_affinity_lines = [
    "아직 별로군.",
    "계속 이 정도면 기대 안 한다.",
    "적어도 도망치진 마라.",
    "지켜볼 가치가 생기면 다시 보지.",
    "결과를 가져와라."
]

mid_affinity_lines = [
    "지켜보고 있다.",
    "조금은 나아졌군.",
    "계속해.",
    "멈추지 마.",
    "아직은 판단 보류다."
]

high_affinity_lines = [
    "괜찮군.",
    "실력은 인정하지.",
    "여기까지 올라온 건 우연 아니다.",
    "계속 그렇게 해.",
    "나쁘지 않다."
]

max_affinity_lines = [
    "너, 우리 쪽으로 올 생각 없나.",
    "여기서 썩히기엔 아까운 실력이다.",
    "같이 싸워도 되겠군.",
    "이 정도면 인정할 수밖에 없다.",
    "…흥, 제법이군."
]

horde_lines = [
    "…그 녀석 말, 너무 깊게 받아들이진 마.",
    "호드가 그렇게 말했으면… 이유는 있을 거다.",
    "지금은 그쪽 말 듣는 게 나을 수도 있겠군.",
    "…괜히 혼자 끌어안지 마.",
    "그 녀석, 그런 말 쉽게 하는 타입 아니다.",
    "호드가 말했으면, 무시하지 마라.",
    "…그래도 버티고 있잖아.",
    "그쪽도 나름 방법을 아는 놈이다.",
    "…혼자서 다 하려 하지 마.",
    "필요하면… 그쪽 말 따라도 된다."
]

horde_bot_reactions = [
    "…거기서 멈추지 마.",
    "천천히는 좋다. 멈추지만 마.",
    "그 말, 무시할 필요는 없겠군.",
    "…그래도 일어나.",
    "버틸 수 있잖아."
]

timer_start_lines = [
    "{minutes}분이다. 집중해.",
    "{minutes}분 준다. 흐트러지지 마.",
    "좋아. {minutes}분 동안 끝내.",
    "{minutes}분이다. 딴짓하지 마."
]

timer_end_lines = [
    "시간 다 됐다.",
    "끝났다. 손 놔.",
    "여기까지다. 결과는?",
    "멈춰. 다음으로 넘어가.",
    "끝이다. 얼마나 했지?"
]

# =========================
# 150개 이상 키워드 반응 세트
# =========================
KEYWORD_SETS = [
    {
        "name": "sad",
        "chance": 0.45,
        "keywords": [
            "힘들", "지쳐", "우울", "괴롭", "포기", "못하겠", "망했", "죽고싶", "무기력", "버겁",
            "힘드네", "힘들다", "지친다", "우울해", "지옥같", "허무", "멘붕", "스트레스", "번아웃", "괴로워"
        ],
        "lines": [
            "그래서 멈출 거냐?",
            "버텨. 아직 끝난 거 아니다.",
            "그 정도로 끝낼 거냐?",
            "포기할 이유는 아니다.",
            "주저앉기엔 이르다.",
            "버틸 수 있잖아.",
            "끝까지 가봐라.",
            "지금 무너지면 여기까지다."
        ]
    },
    {
        "name": "anger",
        "chance": 0.5,
        "keywords": [
            "씨발", "ㅅㅂ", "좆", "짜증", "열받", "빡쳐", "개같", "화남", "환장", "열받네",
            "킹받", "개빡", "화나", "성질", "빡치", "개열받", "미치겠", "ㅈ같", "극혐", "혐오"
        ],
        "lines": [
            "그 말버릇, 고쳐.",
            "화를 쏟는다고 해결 안 된다.",
            "분노는 쓸모 있게 써라.",
            "에너지 낭비하지 마.",
            "싸울 거면 제대로 써."
        ]
    },
    {
        "name": "sleep",
        "chance": 0.5,
        "keywords": [
            "잘자", "굿나잇", "자러", "졸려", "피곤", "자야", "잠와", "졸림", "기절", "눈감겨",
            "쿨쿨", "잠온다", "자고싶", "피곤해", "졸리다", "자는중", "밤샘", "수면", "자러간", "눕고싶"
        ],
        "lines": [
            "푹 자고 와.",
            "쉬어. 다음엔 제대로 와라.",
            "컨디션 관리도 실력이다.",
            "쉴 때는 제대로 쉬어.",
            "잠 부족한 놈은 금방 무너진다."
        ]
    },
    {
        "name": "proud",
        "chance": 0.4,
        "keywords": [
            "잘했", "해냈", "이겼", "성공", "합격", "통과", "클리어", "깼다", "깨버", "해냄",
            "완료", "이김", "잘했다", "승리", "됐다", "붙었", "성공적", "완수", "클리어함", "일냈"
        ],
        "lines": [
            "그 정도는 해야지.",
            "괜찮군.",
            "나쁘지 않다.",
            "계속 그렇게 해.",
            "방심하지 마."
        ]
    },
    {
        "name": "bored",
        "chance": 0.4,
        "keywords": [
            "심심", "노잼", "할거없", "재미없", "지루", "무료", "심심해", "노잼이", "지루해", "무기력해",
            "할거없다", "따분", "심심하다", "재밌는거", "재미좀", "놀자", "뭐하지", "심심하네", "놀거리", "지겨워"
        ],
        "lines": [
            "심심하면 싸워.",
            "시간 낭비하지 마.",
            "뭐라도 해.",
            "가만히 있으면 더 지루하다.",
            "움직여."
        ]
    },
    {
        "name": "provocation",
        "chance": 0.7,
        "keywords": [
            "쫄", "못함", "약함", "개못", "노답", "허접", "잡몹", "쫄보", "못하네", "약하네",
            "허접하", "초보", "하수", "못하냐", "못하는데", "구리다", "구려", "못깬", "못이김", "느리네"
        ],
        "lines": [
            "그 말, 책임질 수 있냐?",
            "증명해.",
            "입은 쉬운데, 실력은?",
            "싸울 생각이면 바로 와.",
            "말 말고 결과로 보여."
        ]
    },
    {
        "name": "study",
        "chance": 0.45,
        "keywords": [
            "공부", "시험", "과제", "중간고사", "기말", "레포트", "수업", "강의", "복습", "예습",
            "시험기간", "학점", "문제집", "공책", "필기", "숙제", "암기", "벼락치기", "강의실", "공부중"
        ],
        "lines": [
            "할 거면 집중해.",
            "머리만 굴리지 말고 손도 움직여.",
            "버티는 놈이 끝내 가져간다.",
            "결과로 말해.",
            "공부도 결국 싸움이다."
        ]
    },
    {
        "name": "game",
        "chance": 0.45,
        "keywords": [
            "게임", "롤", "발로", "오버워치", "메이플", "던파", "로아", "피파", "서든", "마크",
            "에펙", "스팀", "배그", "원신", "스타", "라오루", "협곡", "랭크", "듀오", "큐돌"
        ],
        "lines": [
            "이길 거면 제대로 해.",
            "집중 안 하면 진다.",
            "말고 결과로 보여.",
            "실력으로 증명해.",
            "패배는 변명 안 받아준다."
        ]
    },
    {
        "name": "food",
        "chance": 0.4,
        "keywords": [
            "배고", "밥", "먹을거", "야식", "굶", "라면", "치킨", "피자", "햄버거", "간식",
            "점심", "저녁", "아침", "먹자", "배불", "맛있", "배달", "국밥", "떡볶이", "커피"
        ],
        "lines": [
            "먹어. 굶어서 강해지진 않는다.",
            "기본은 챙겨라.",
            "컨디션도 실력이다.",
            "먹을 건 먹고 와.",
            "배고픈 놈은 오래 못 버틴다."
        ]
    },
    {
        "name": "exercise",
        "chance": 0.4,
        "keywords": [
            "운동", "헬스", "러닝", "산책", "조깅", "근력", "스트레칭", "푸쉬업", "스쿼트", "달리기",
            "체력", "근육", "체지방", "유산소", "무산소", "등운동", "하체", "상체", "운동감", "운동함"
        ],
        "lines": [
            "계속해.",
            "멈추지 마.",
            "그게 쌓인다.",
            "결과는 나중에 온다.",
            "몸은 거짓말 안 한다."
        ]
    },
    {
        "name": "money",
        "chance": 0.35,
        "keywords": [
            "돈", "용돈", "알바", "월급", "부자", "거지", "가난", "지갑", "통장", "잔고",
            "카드", "현금", "대출", "저축", "적금", "비싸", "싸다", "할인", "쿠폰", "쇼핑"
        ],
        "lines": [
            "돈도 결국 관리다.",
            "있을 때 아껴라.",
            "낭비만 하면 남는 게 없다.",
            "필요한 데 써라.",
            "빈 통장 핑계는 약하다."
        ]
    },
    {
        "name": "love",
        "chance": 0.35,
        "keywords": [
            "사랑", "연애", "고백", "썸", "헤어졌", "짝사랑", "여친", "남친", "애인", "플러팅",
            "호감", "고백함", "커플", "솔로", "차였", "연락", "데이트", "사귄", "설렘", "짝녀"
        ],
        "lines": [
            "감정에 휘둘려서 무너지진 마라.",
            "좋다면 말해. 숨기다 끝내지 말고.",
            "상처는 남아도 끝은 아니다.",
            "망설이다 놓치는 것도 실력 부족이다.",
            "연애도 결국 선택이다."
        ]
    },
    {
        "name": "weather",
        "chance": 0.3,
        "keywords": [
            "비", "눈", "날씨", "더워", "추워", "태풍", "맑음", "흐림", "우산", "미세먼지",
            "장마", "폭염", "한파", "비온다", "비옴", "눈온", "날씨좋", "바람", "쌀쌀", "습하"
        ],
        "lines": [
            "날씨 탓만 하지 마.",
            "덥든 춥든 해야 할 건 해야지.",
            "비 온다고 멈추진 않는다.",
            "환경이 불편한 건 핑계가 안 된다.",
            "몸 챙길 건 챙겨라."
        ]
    },
    {
        "name": "greeting",
        "chance": 0.5,
        "keywords": [
            "안녕", "ㅎㅇ", "하이", "반가", "좋은아침", "좋은밤", "좋은저녁", "오하요", "헬로", "인사",
            "왔어", "들어왔", "복귀", "컴백", "안뇽", "하잇", "하이요", "헬롱", "반갑다", "반갑네"
        ],
        "lines": [
            "왔군.",
            "늦지 않았으면 됐다.",
            "무슨 일이지?",
            "반갑다는 말은 안 한다. 대신 들어주지.",
            "말해봐라."
        ]
    },
    {
        "name": "farewell",
        "chance": 0.5,
        "keywords": [
            "잘가", "바이", "ㅂㅂ", "다녀올", "간다", "나간다", "퇴장", "사라짐", "이만", "빠잉",
            "bye", "수고", "간다잉", "잘있", "간다ㅏ", "나감", "갔다옴", "잠수", "가볼", "퇴근"
        ],
        "lines": [
            "가라. 돌아올 거면 제대로 와.",
            "수고했으면 됐다.",
            "도망은 아니겠지.",
            "쉬고 와라.",
            "다음엔 결과 들고 와."
        ]
    },
    {
        "name": "laugh",
        "chance": 0.35,
        "keywords": [
            "ㅋㅋ", "ㅎㅎ", "lol", "웃김", "웃기", "개웃", "빵터", "터짐", "현웃", "ㅋㅋㅋ",
            "하하", "호호", "크크", "웃겨", "웃었다", "재밌", "개그", "드립", "유머", "농담"
        ],
        "lines": [
            "웃을 여유가 있군.",
            "나쁘지 않다.",
            "긴장 풀린 건 좋은데 방심은 마라.",
            "적당히 웃고 다시 움직여.",
            "그 정도면 볼 만하네."
        ]
    },
]


def get_keyword_response(content: str):
    for entry in KEYWORD_SETS:
        if any(word in content for word in entry["keywords"]):
            if random.random() < entry["chance"]:
                return random.choice(entry["lines"])
    return None


# =========================
# 전투 로직
# =========================
async def check_and_send_daily_completion(ctx, user_id: int):
    result = None
    for progress_type in ["message", "duel_participate", "duel_win", "boss_attempt", "boss_win"]:
        # 이미 함수 호출되는 상황별로만 따로 처리하므로 여기선 사용 안 함
        pass
    return result


async def send_daily_reward_message(ctx, member, result):
    if not result:
        return
    reward = result["reward"]
    affinity = result["affinity"]
    complete_lines = [
        "오늘 할 일은 제대로 했군.",
        "끝내고 왔군. 좋다.",
        "그 정도는 해낼 줄 알았다.",
    ]
    await ctx.send(
        await ctx.send(
    f"**일일 퀘스트 완료 - {member.display_name}**\n"
    f"{random.choice(complete_lines)}\n"
    f"보상: HP +{reward.get('hp', 0)}, ATK +{reward.get('atk', 0)}, AGI +{reward.get('agi', 0)}\n"
    f"호감도: {affinity} ({affinity_tier_name(affinity)})"
)
        f"{random.choice(complete_lines)}\n"
"
        f"보상: HP +{reward.get('hp', 0)}, ATK +{reward.get('atk', 0)}, AGI +{reward.get('agi', 0)}
"
        f"호감도: {affinity} ({affinity_tier_name(affinity)})"
    )


async def run_pvp_duel(ctx, challenger, target):
    duel_key = tuple(sorted([challenger.id, target.id]))
    active_duels[duel_key] = True

    challenger_stats = get_user_stats(challenger.id)
    target_stats = get_user_stats(target.id)

    hp = {
        challenger.id: challenger_stats["hp"],
        target.id: target_stats["hp"]
    }

    order = [challenger, target]
    random.shuffle(order)

    increment_daily_progress(challenger.id, "duel_participate", 1)
    increment_daily_progress(target.id, "duel_participate", 1)
    change_affinity(challenger.id, 1)
    change_affinity(target.id, 1)

    await ctx.send(f"**{challenger.display_name} vs {target.display_name}**\n{random.choice(start_lines)}")
    await asyncio.sleep(1)

    turn = 1

    while hp[challenger.id] > 0 and hp[target.id] > 0:
        attacker = order[turn % 2]
        defender = order[(turn + 1) % 2]
        attacker_stats = get_user_stats(attacker.id)
        defender_stats = get_user_stats(defender.id)

        base_damage = random.randint(8, 16) + attacker_stats["atk"]
        crit = random.random() < 0.15
        dodge = random.random() < min(0.35, 0.05 + defender_stats["agi"] * 0.01)

        if dodge:
            await ctx.send(
                f"**{attacker.display_name}**의 공격 — **{defender.display_name}** 회피!\n"
                f"> {random.choice(attack_lines)}"
            )
        else:
            damage = base_damage
            if crit:
                damage *= 2
                await ctx.send(
                    f"**{attacker.display_name}**의 공격 — **크리티컬 {damage} 데미지!**\n"
                    f"> {random.choice(critical_lines)}"
                )
            else:
                await ctx.send(
                    f"**{attacker.display_name}**의 공격 — **{damage} 데미지**\n"
                    f"> {random.choice(attack_lines)}"
                )
            hp[defender.id] -= damage
            hp[defender.id] = max(0, hp[defender.id])

        await ctx.send(
            f"남은 체력\n"
            f"- {challenger.display_name}: {hp[challenger.id]} HP\n"
            f"- {target.display_name}: {hp[target.id]} HP"
        )
        await asyncio.sleep(1.2)
        turn += 1

    winner = challenger if hp[challenger.id] > 0 else target
    loser = target if winner == challenger else challenger

    update_record(winner.id, loser.id)
    increment_daily_progress(winner.id, "duel_win", 1)

    winner_affinity = change_affinity(winner.id, 3)
    loser_affinity = change_affinity(loser.id, -2)

    data = get_duel_data()
    streak = data.get(str(winner.id), {}).get("streak", 0)

    end_msg = f"**승자: {winner.display_name}**\n{random.choice(win_lines)}"
    if streak >= 3:
        end_msg += f"\n{random.choice(win_streak_lines)} (현재 {streak}연승)"
        change_affinity(winner.id, 2)

    end_msg += f"\n{get_affinity_line(winner_affinity)}"
    end_msg += f"\n패자 {loser.display_name}: {get_affinity_line(loser_affinity)}"
    await ctx.send(end_msg)

    for member in [challenger, target]:
        result = increment_daily_progress(member.id, "duel_participate", 0)
        if result:
            await send_daily_reward_message(ctx, member, result)

    result = increment_daily_progress(winner.id, "duel_win", 0)
    if result:
        await send_daily_reward_message(ctx, winner, result)

    active_duels.pop(duel_key, None)


async def run_boss_duel(ctx, user):
    user_stats = get_user_stats(user.id)
    gebura_hp = 300
    user_hp = user_stats["hp"]

    increment_daily_progress(user.id, "boss_attempt", 1)
    change_affinity(user.id, 1)

    await ctx.send(f"**{user.display_name} vs 게부라**\n나랑 붙겠다고? 살아남아 봐.")
    await asyncio.sleep(1)

    player_turn = True
    rage_triggered = False

    while gebura_hp > 0 and user_hp > 0:
        if player_turn:
            damage = random.randint(8, 16) + user_stats["atk"]
            crit = random.random() < 0.18
            if crit:
                damage *= 2
                gebura_hp -= damage
                await ctx.send(f"**{user.display_name}**의 공격 — 크리티컬 {damage} 데미지!\n> 제법이군.")
            else:
                gebura_hp -= damage
                await ctx.send(f"**{user.display_name}**의 공격 — {damage} 데미지")
        else:
            if gebura_hp <= 150 and not rage_triggered:
                rage_triggered = True
                await ctx.send("...조금, 진심으로 가볼까.")

            if rage_triggered:
                damage = int(random.randint(12, 24) * 2.5)
            else:
                damage = int(random.randint(12, 24) * 1.5)

            crit = random.random() < 0.22
            dodge = random.random() < min(0.35, 0.05 + user_stats["agi"] * 0.01)

            if dodge:
                await ctx.send(f"**{user.display_name}**가 게부라의 공격을 피했다.\n> 운은 좋군.")
            else:
                if crit:
                    damage *= 2
                    user_hp -= damage
                    await ctx.send(f"**게부라**의 공격 — 크리티컬 {damage} 데미지!\n> {random.choice(critical_lines)}")
                else:
                    user_hp -= damage
                    await ctx.send(f"**게부라**의 공격 — {damage} 데미지\n> {random.choice(attack_lines)}")

        gebura_hp = max(0, gebura_hp)
        user_hp = max(0, user_hp)
        await ctx.send(f"남은 체력\n- {user.display_name}: {user_hp} HP\n- 게부라: {gebura_hp} HP")
        await asyncio.sleep(1.2)
        player_turn = not player_turn

    if user_hp > 0:
        update_boss_record(user.id, True)
        increment_daily_progress(user.id, "boss_win", 1)
        affinity = change_affinity(user.id, 10)
        await ctx.send(f"**승리: {user.display_name}**\n...버텼군. 인정한다.\n{get_affinity_line(affinity)}")
        result = increment_daily_progress(user.id, "boss_win", 0)
        if result:
            await send_daily_reward_message(ctx, user, result)
    else:
        update_boss_record(user.id, False)
        affinity = change_affinity(user.id, -2)
        await ctx.send(f"**패배: {user.display_name}**\n그 정도로는 부족하다.\n{get_affinity_line(affinity)}")

    result = increment_daily_progress(user.id, "boss_attempt", 0)
    if result:
        await send_daily_reward_message(ctx, user, result)


# =========================
# 이벤트
# =========================
@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if not can_talk_in_channel(message.channel.id):
        return

    content = message.content.lower()

    if message.guild:
        guild_name = message.guild.name.lower()
        if any(word in guild_name for word in ["ruina", "library", "도서관", "루이나"]):
            pass

    # 호드봇 반응
    if message.author.bot:
        if HORDE_BOT_ID != 0 and message.author.id == HORDE_BOT_ID:
            if random.random() < 0.25:
                await message.channel.send(random.choice(horde_bot_reactions))
        await bot.process_commands(message)
        return

    # 일반 메시지 일일퀘스트 progress
    result = increment_daily_progress(message.author.id, "message", 1)
    if result:
        await send_daily_reward_message(message.channel, message.author, result)

    # 호드 언급 우선 반응
    if "호드" in content and random.random() < 0.8:
        await message.channel.send(random.choice(horde_lines))
    else:
        response = get_keyword_response(content)
        if response:
            await message.channel.send(response)
        elif "게부라" in content and random.random() < 0.6:
            affinity = get_user_affinity(message.author.id)
            await message.channel.send(random.choice([
                "불렀나?",
                "무슨 일이지?",
                "쓸데없는 말이면 받지 않는다.",
                "말해봐라.",
                get_affinity_line(affinity)
            ]))

    await bot.process_commands(message)


# =========================
# 명령어
# =========================
@bot.command(name="도움")
async def help_command(ctx):
    text = (
        "**게부라 명령어 목록**\n"
        "`!결투 @유저` - 다른 유저에게 결투 신청\n"
        "`!수락` - 받은 결투 수락\n"
        "`!거절` - 받은 결투 거절\n"
        "`!게부라결투` - 게부라와 보스전\n"
        "`!전적 [@유저]` - 전적 확인\n"
        "`!랭킹` - 서버 결투 랭킹\n"
        "`!스탯 [@유저]` - 스탯 / 호감 확인\n"
        "`!일일` - 오늘의 일일 퀘스트 확인\n"
        "`!타이머 분 내용` - 타이머 시작\n"
        "예: `!타이머 25 공부`, `!타이머 10 게임`"
    )
    await ctx.send(text)


@bot.command(name="일일")
async def daily_command(ctx):
    quest, done = get_daily_for_user(ctx.author.id)
    reward = quest["reward"]
    status = "완료" if done else "진행 중"
    await ctx.send(
        f"**오늘의 일일 퀘스트**\n"
        f"목표: {quest['label']}\n"
        f"상태: {status}\n"
        f"보상: HP +{reward.get('hp', 0)}, ATK +{reward.get('atk', 0)}, AGI +{reward.get('agi', 0)}"
    )


@bot.command(name="스탯")
async def stat_command(ctx, member: discord.Member = None):
    member = member or ctx.author
    stats = get_user_stats(member.id)
    affinity = get_user_affinity(member.id)
    await ctx.send(
        f"**{member.display_name} 스탯**\n"
        f"HP: {stats['hp']}\n"
        f"ATK: {stats['atk']}\n"
        f"AGI: {stats['agi']}\n"
        f"호감도: {affinity} ({affinity_tier_name(affinity)})"
    )


@bot.command(name="결투")
async def duel(ctx, target: discord.Member):
    if target.bot:
        await ctx.send("봇 상대로는 안 된다.")
        return
    if target.id == ctx.author.id:
        await ctx.send("자기 자신이랑 싸우려는 건가? 그건 안 된다.")
        return

    duel_key = tuple(sorted([ctx.author.id, target.id]))
    if duel_key in active_duels or duel_key in pending_duels:
        await ctx.send("이미 진행 중인 결투가 있다.")
        return

    pending_duels[duel_key] = {
        "challenger": ctx.author.id,
        "target": target.id,
        "channel_id": ctx.channel.id,
    }

    await ctx.send(
        f"{target.mention} 도전이 들어왔다. 받을 거냐?\n"
        "30초 안에 `!수락` 또는 `!거절` 해라."
    )

    await asyncio.sleep(30)
    if duel_key in pending_duels:
        pending_duels.pop(duel_key, None)
        change_affinity(ctx.author.id, -1)
        await ctx.send(random.choice(cancel_lines))


@bot.command(name="수락")
async def accept_duel(ctx):
    found_key = None
    challenger_id = None
    for key, info in pending_duels.items():
        if info["target"] == ctx.author.id and info["channel_id"] == ctx.channel.id:
            found_key = key
            challenger_id = info["challenger"]
            break

    if not found_key:
        await ctx.send("받은 결투가 없다.")
        return

    pending_duels.pop(found_key, None)
    challenger = ctx.guild.get_member(challenger_id)
    if challenger is None:
        await ctx.send("도전자가 없다. 다시 걸어라.")
        return

    await run_pvp_duel(ctx, challenger, ctx.author)


@bot.command(name="거절")
async def decline_duel(ctx):
    found_key = None
    challenger_id = None
    for key, info in pending_duels.items():
        if info["target"] == ctx.author.id and info["channel_id"] == ctx.channel.id:
            found_key = key
            challenger_id = info["challenger"]
            break

    if not found_key:
        await ctx.send("거절할 결투가 없다.")
        return

    pending_duels.pop(found_key, None)
    if challenger_id:
        change_affinity(challenger_id, -1)
    await ctx.send(random.choice(cancel_lines))


@bot.command(name="게부라결투")
async def gebura_duel(ctx):
    await run_boss_duel(ctx, ctx.author)


@bot.command(name="전적")
async def record(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = get_duel_data()
    record_data = data.get(str(member.id), {
        "wins": 0,
        "losses": 0,
        "streak": 0,
        "best_streak": 0,
        "boss_wins": 0,
        "boss_losses": 0,
    })

    msg = (
        f"**{member.display_name} 전적**\n"
        f"- PvP 승: {record_data['wins']}\n"
        f"- PvP 패: {record_data['losses']}\n"
        f"- 현재 연승: {record_data['streak']}\n"
        f"- 최고 연승: {record_data['best_streak']}\n"
        f"- 게부라전 승: {record_data['boss_wins']}\n"
        f"- 게부라전 패: {record_data['boss_losses']}"
    )
    await ctx.send(msg)


@bot.command(name="랭킹")
async def ranking(ctx):
    data = get_duel_data()
    if not data:
        await ctx.send("아직 기록이 없다.")
        return

    ranking_data = sorted(
        data.items(),
        key=lambda x: (x[1].get("wins", 0), x[1].get("best_streak", 0), x[1].get("boss_wins", 0)),
        reverse=True,
    )[:10]

    lines = ["**강함 랭킹**"]
    for i, (uid, stats) in enumerate(ranking_data, start=1):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"유저 {uid}"
        lines.append(
            f"{i}. {name} - 승 {stats.get('wins', 0)} | 패 {stats.get('losses', 0)} | 최고연승 {stats.get('best_streak', 0)} | 보스승 {stats.get('boss_wins', 0)}"
        )
    await ctx.send("\n".join(lines))


@bot.command(name="타이머")
async def timer(ctx, minutes: int, *, label: str = ""):
    if minutes <= 0:
        await ctx.send("시간은 1분 이상으로 해라.")
        return
    if minutes > 180:
        await ctx.send("너무 길다. 180분 이하로 해라.")
        return

    start_msg = random.choice(timer_start_lines).format(minutes=minutes)
    if label:
        await ctx.send(f"{ctx.author.mention} {start_msg}\n목표: **{label}**")
    else:
        await ctx.send(f"{ctx.author.mention} {start_msg}")

    timer_log = load_json(TIMER_FILE, [])
    timer_log.append({
        "user_id": ctx.author.id,
        "minutes": minutes,
        "label": label,
        "started_at": datetime.now().isoformat(timespec="seconds")
    })
    save_json(TIMER_FILE, timer_log)

    await asyncio.sleep(minutes * 60)

    end_msg = random.choice(timer_end_lines)
    if label:
        await ctx.send(f"{ctx.author.mention} {end_msg}\n끝난 항목: **{label}**")
    else:
        await ctx.send(f"{ctx.author.mention} {end_msg}")


# =========================
# 실행
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN 환경변수가 설정되지 않았습니다.")

bot.run(TOKEN)
