import discord
from discord.ext import commands
import os
import json
import random
import asyncio
from pathlib import Path
from datetime import datetime

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

HORDE_BOT_ID = int(os.getenv("HORDE_BOT_ID", "0"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))  # 0이면 모든 채널 허용

active_duels = {}
pending_duels = {}

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


def update_record(winner_id: int, loser_id: int):
    data = load_json(DUEL_FILE, {})

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
    data = load_json(DUEL_FILE, {})
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


def can_talk_in_channel(channel_id: int):
    return TARGET_CHANNEL_ID == 0 or channel_id == TARGET_CHANNEL_ID


# =========================
# 게부라 대사 데이터
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

sad_lines = [
    "그래서 멈출 거냐?",
    "주저앉을 거면 잠깐만 그래.",
    "버텨. 아직 끝난 거 아니다.",
    "힘들다고 끝은 아니다.",
    "그 상태로 포기할 거냐?"
]

angry_lines = [
    "그 말버릇, 고쳐.",
    "화를 쏟는다고 달라지진 않아.",
    "분노는 쓸모 있게 써라.",
    "그 에너지, 낭비하지 마.",
    "차라리 싸워."
]

sleep_lines = [
    "푹 자고 와.",
    "쉬어. 다음엔 제대로 와라.",
    "컨디션 관리도 실력이다.",
    "쉴 때는 제대로 쉬어."
]

proud_lines = [
    "그 정도는 해야지.",
    "괜찮군.",
    "나쁘지 않다.",
    "계속 그렇게 해.",
    "방심하지 마."
]

bored_lines = [
    "심심하면 싸워.",
    "시간 낭비하지 마.",
    "뭐라도 해.",
    "가만히 있으면 더 지루하다.",
    "움직여."
]

provocation_lines = [
    "그 말, 책임질 수 있냐?",
    "증명해.",
    "입은 쉬운데, 실력은?",
    "싸울 생각이면 바로 와.",
    "말 말고 결과로 보여."
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
# PvP 결투
# =========================
async def run_pvp_duel(ctx, challenger, target):
    duel_key = tuple(sorted([challenger.id, target.id]))
    active_duels[duel_key] = True

    hp = {
        challenger.id: 100,
        target.id: 100
    }

    order = [challenger, target]
    random.shuffle(order)

    await ctx.send(f"**{challenger.display_name} vs {target.display_name}**\n{random.choice(start_lines)}")
    await asyncio.sleep(1)

    turn = 1

    while hp[challenger.id] > 0 and hp[target.id] > 0:
        attacker = order[turn % 2]
        defender = order[(turn + 1) % 2]

        damage = random.randint(10, 20)
        crit = random.random() < 0.18
        dodge = random.random() < 0.12

        if dodge:
            await ctx.send(
                f"**{attacker.display_name}**의 공격 — **{defender.display_name}** 회피!\n"
                f"> {random.choice(attack_lines)}"
            )
        else:
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
        await asyncio.sleep(1.5)
        turn += 1

    winner = challenger if hp[challenger.id] > 0 else target
    loser = target if winner == challenger else challenger

    update_record(winner.id, loser.id)

    data = load_json(DUEL_FILE, {})
    streak = data.get(str(winner.id), {}).get("streak", 0)

    end_msg = f"**승자: {winner.display_name}**\n{random.choice(win_lines)}"
    if streak >= 3:
        end_msg += f"\n{random.choice(win_streak_lines)} (현재 {streak}연승)"

    end_msg += f"\n{random.choice(lose_lines)}"

    await ctx.send(end_msg)
    active_duels.pop(duel_key, None)


# =========================
# 게부라 보스전
# =========================
async def run_boss_duel(ctx, user):
    gebura_hp = 300
    user_hp = 100

    await ctx.send(f"**{user.display_name} vs 게부라**\n나랑 붙겠다고? 살아남아 봐.")
    await asyncio.sleep(1)

    player_turn = True
    rage_triggered = False

    while gebura_hp > 0 and user_hp > 0:
        if player_turn:
            damage = random.randint(10, 22)
            crit = random.random() < 0.20

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
            dodge = random.random() < 0.10

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

        await ctx.send(
            f"남은 체력\n"
            f"- {user.display_name}: {user_hp} HP\n"
            f"- 게부라: {gebura_hp} HP"
        )
        await asyncio.sleep(1.5)
        player_turn = not player_turn

    if user_hp > 0:
        update_boss_record(user.id, True)
        await ctx.send(f"**승리: {user.display_name}**\n...버텼군. 인정한다.")
    else:
        update_boss_record(user.id, False)
        await ctx.send(f"**패배: {user.display_name}**\n그 정도로는 부족하다.")


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

    # 호드봇 반응
    if message.author.bot:
        if HORDE_BOT_ID != 0 and message.author.id == HORDE_BOT_ID:
            if random.random() < 0.25:
                await message.channel.send(random.choice(horde_bot_reactions))
        await bot.process_commands(message)
        return

    responded = False

    if "호드" in content and random.random() < 0.8:
        await message.channel.send(random.choice(horde_lines))
        responded = True

    elif any(word in content for word in ["힘들", "지침", "우울", "지쳐", "괴롭"]):
        if random.random() < 0.35:
            await message.channel.send(random.choice(sad_lines))
            responded = True

    elif any(word in content for word in ["씨발", "ㅅㅂ", "좆", "개빡", "짜증", "열받"]):
        if random.random() < 0.45:
            await message.channel.send(random.choice(angry_lines))
            responded = True

    elif any(word in content for word in ["잘자", "굿나잇", "자러"]):
        if random.random() < 0.5:
            await message.channel.send(random.choice(sleep_lines))
            responded = True

    elif any(word in content for word in ["잘했", "해냈", "이겼", "성공"]):
        if random.random() < 0.35:
            await message.channel.send(random.choice(proud_lines))
            responded = True

    elif any(word in content for word in ["심심", "노잼", "할거없"]):
        if random.random() < 0.35:
            await message.channel.send(random.choice(bored_lines))
            responded = True

    elif any(word in content for word in ["쫄", "못함", "약함", "개못", "노답"]):
        if random.random() < 0.65:
            await message.channel.send(random.choice(provocation_lines))
            responded = True

    elif "게부라" in content and not responded:
        if random.random() < 0.6:
            await message.channel.send(random.choice([
                "불렀나?",
                "무슨 일이지?",
                "쓸데없는 말이면 받지 않는다.",
                "말해봐라."
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
        "`!타이머 분 내용` - 타이머 시작\n"
        "예: `!타이머 25 공부`, `!타이머 10 게임`"
    )
    await ctx.send(text)


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

    for key, info in pending_duels.items():
        if info["target"] == ctx.author.id and info["channel_id"] == ctx.channel.id:
            found_key = key
            break

    if not found_key:
        await ctx.send("거절할 결투가 없다.")
        return

    pending_duels.pop(found_key, None)
    await ctx.send(random.choice(cancel_lines))


@bot.command(name="게부라결투")
async def gebura_duel(ctx):
    await run_boss_duel(ctx, ctx.author)


@bot.command(name="전적")
async def record(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_json(DUEL_FILE, {})

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
    data = load_json(DUEL_FILE, {})
    if not data:
        await ctx.send("아직 기록이 없다.")
        return

    ranking_data = sorted(
        data.items(),
        key=lambda x: (x[1].get("wins", 0), x[1].get("best_streak", 0)),
        reverse=True,
    )[:10]

    lines = ["**강함 랭킹**"]
    for i, (uid, stats) in enumerate(ranking_data, start=1):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"유저 {uid}"
        lines.append(
            f"{i}. {name} - 승 {stats.get('wins', 0)} | 패 {stats.get('losses', 0)} | 최고연승 {stats.get('best_streak', 0)}"
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