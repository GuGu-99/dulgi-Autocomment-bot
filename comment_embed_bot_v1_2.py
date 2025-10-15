# -*- coding: utf-8 -*-
# comment_embed_bot_v1_2.py
# Render 무료버전 안전형 댓글요약봇 — 다중 채널 + 7일 유지 제한

# === Fix for missing audioop in Render Python 3.13 ===
import sys, types
if 'audioop' not in sys.modules:
    sys.modules['audioop'] = types.ModuleType('audioop')


import os
import json
import asyncio
import datetime
import pytz
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread

# ===== 기본 설정 =====
KST = pytz.timezone("Asia/Seoul")
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "data.json"

# ✅ 감시할 채널 ID 리스트 (수정 쉬움)
CHANNEL_IDS = [
    1427893169994858526, 
]

MESSAGE_RETENTION_DAYS = 7  # ✅ 7일 전까지만 유지

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
data = {}

# ===== Flask Keep-Alive =====
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot is running!"
def run_flask():
    app.run(host="0.0.0.0", port=8080)
Thread(target=run_flask).start()

# ===== 데이터 로드 & 저장 =====
def load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = {}
    else:
        data = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_now():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

# ===== 데이터 정리 (7일 경과 메시지 삭제) =====
def cleanup_old_data():
    now = datetime.datetime.now(KST)
    to_delete = []
    for msg_id, info in data.items():
        try:
            t = datetime.datetime.strptime(info["created"], "%Y-%m-%d %H:%M:%S")
            if (now - t).days >= MESSAGE_RETENTION_DAYS:
                to_delete.append(msg_id)
        except:
            continue
    for msg_id in to_delete:
        del data[msg_id]
    if to_delete:
        print(f"🧹 {len(to_delete)}개 오래된 데이터 삭제됨")
        save_data()

# ===== 봇 이벤트 =====
@bot.event
async def on_ready():
    print(f"✅ 로그인 완료: {bot.user}")
    load_data()
    comment_updater.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id not in CHANNEL_IDS:
        return  # ✅ 지정된 채널 외 메시지는 무시

    # 이미지 메시지 등록
    if message.attachments:
        data[str(message.id)] = {
            "author": message.author.name,
            "channel_id": message.channel.id,
            "embed_id": None,
            "comments": [],
            "created": get_now(),
            "updated": get_now()
        }
        save_data()

    # 답글 수집
    if message.reference:
        parent_id = str(message.reference.message_id)
        if parent_id in data:
            comment = {
                "user": message.author.name,
                "content": message.content[:100],
                "time": get_now()
            }
            data[parent_id]["comments"].append(comment)
            data[parent_id]["updated"] = get_now()
            save_data()

    await bot.process_commands(message)

# ===== 5분마다 댓글 요약 갱신 =====
@tasks.loop(minutes=5)
async def comment_updater():
    cleanup_old_data()
    for img_id, info in list(data.items()):
        try:
            channel = bot.get_channel(info["channel_id"])
            if not channel:
                continue
            msg = await channel.fetch_message(int(img_id))

            comments = info["comments"][-3:]
            if not comments:
                continue

            desc = "\n".join([f"💬 **{c['user']}**: {c['content']}" for c in comments])
            embed = discord.Embed(
                title=f"🖼️ 최근 댓글 {len(comments)}개 요약",
                description=desc,
                color=0x5DBB63,
                timestamp=datetime.datetime.now(KST)
            )
            embed.set_footer(text=f"마지막 갱신: {info['updated']}")

            if info["embed_id"]:
                try:
                    e_msg = await channel.fetch_message(int(info["embed_id"]))
                    await e_msg.edit(embed=embed)
                except:
                    e_msg = await channel.send(embed=embed)
                    data[img_id]["embed_id"] = str(e_msg.id)
            else:
                e_msg = await channel.send(embed=embed)
                data[img_id]["embed_id"] = str(e_msg.id)

            data[img_id]["updated"] = get_now()
            save_data()
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[Error] {img_id}: {e}")

# ===== 관리자 명령어 =====
@bot.command()
async def 백업(ctx):
    save_data()
    await ctx.send("📦 수동 백업 완료!")

@bot.command()
async def 복원(ctx):
    load_data()
    await ctx.send("♻️ 데이터 복원 완료!")

@bot.command()
async def 채널목록(ctx):
    text = "\n".join([f"- <#{cid}> ({cid})" for cid in CHANNEL_IDS])
    await ctx.send(f"📡 현재 감시중인 채널 목록:\n{text}")

# ===== 실행 =====
bot.run(TOKEN)
