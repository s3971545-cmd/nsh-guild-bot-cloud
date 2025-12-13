import os
import io
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from db import init_db, db_upsert_signup, db_get_signup, db_list_signups_by_guild

intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Discord Bot 已登入為 {bot.user}，Slash 指令已同步。")

@bot.tree.command(name="signup", description="幫戰報名 / 更新資料")
@app_commands.describe(
    job="職業 / 流派（例：鐵衣-XX流）",
    gear="裝備 / 境界（例：戰力 25 萬、XX 境）",
    availability="常態可出席時段（例：週三日 20:30 後）",
    voice="語音狀況（可講話 / 只聽指揮 / 無法語音）",
    note="備註（擅長打法、位置、經驗… 可留空）",
)
async def signup(
    interaction: discord.Interaction,
    job: str,
    gear: str,
    availability: str,
    voice: str,
    note: str = "",
):
    guild = interaction.guild
    user = interaction.user

    if guild is None:
        await interaction.response.send_message("⚠️ 請在伺服器頻道內使用此指令。", ephemeral=True)
        return

    try:
        existing = db_get_signup(guild.id, user.id) or {}
        team = existing.get("team", "未分配")

        info = {
            "user_id": user.id,
            "user_name": f"{user.name}#{user.discriminator}",
            "display_name": user.display_name,
            "job": job,
            "gear": gear,
            "availability": availability,
            "voice": voice,
            "note": note,
            "team": team,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

        db_upsert_signup(guild.id, user.id, info)

    except Exception as e:
        await interaction.response.send_message(f"🚫 寫入資料庫失敗：{e}", ephemeral=True)
        return

    embed = discord.Embed(
        title="✅ 幫戰報名成功",
        description="你的資料已登記 / 更新完畢，如需修改再用 `/signup` 即可。",
        color=0x00d1c4,
    )
    embed.add_field(name="顯示名稱", value=info["display_name"], inline=False)
    embed.add_field(name="職業 / 流派", value=job, inline=True)
    embed.add_field(name="裝備 / 境界", value=gear, inline=True)
    embed.add_field(name="可出席時段", value=availability, inline=False)
    embed.add_field(name="語音狀況", value=voice, inline=True)
    embed.add_field(name="備註", value=note if note else "（無）", inline=False)
    embed.add_field(name="目前隊伍", value=team, inline=True)
    embed.set_footer(text="如需修改，直接再次使用 /signup 覆寫即可。")

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="mysignup", description="查看自己幫戰報名資料")
async def mysignup(interaction: discord.Interaction):
    guild = interaction.guild
    user = interaction.user

    if guild is None:
        await interaction.response.send_message("⚠️ 請在伺服器頻道內使用此指令。", ephemeral=True)
        return

    info = db_get_signup(guild.id, user.id)
    if not info:
        await interaction.response.send_message("你還沒有填寫幫戰報名，可以使用 `/signup` 登記。", ephemeral=True)
        return

    embed = discord.Embed(title="📋 你的幫戰報名資料", color=0x00d1c4)
    embed.add_field(name="顯示名稱", value=info.get("display_name", "（無）"), inline=False)
    embed.add_field(name="職業 / 流派", value=info.get("job", "（無）"), inline=True)
    embed.add_field(name="裝備 / 境界", value=info.get("gear", "（無）"), inline=True)
    embed.add_field(name="可出席時段", value=info.get("availability", "（無）"), inline=False)
    embed.add_field(name="語音狀況", value=info.get("voice", "（無）"), inline=True)
    embed.add_field(name="隊伍", value=info.get("team", "未分配"), inline=True)
    embed.add_field(name="備註", value=info.get("note", "（無）"), inline=False)
    embed.set_footer(text=f"最後更新時間：{info.get('timestamp', '未知')}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="list_signups", description="匯出幫戰報名 CSV（管理員用）")
async def list_signups(interaction: discord.Interaction):
    guild = interaction.guild
    user = interaction.user

    if guild is None:
        await interaction.response.send_message("⚠️ 請在伺服器頻道內使用此指令。", ephemeral=True)
        return

    if not user.guild_permissions.manage_guild:
        await interaction.response.send_message("🚫 你沒有使用此指令的權限（需管理伺服器權限）。", ephemeral=True)
        return

    data = db_list_signups_by_guild(guild.id)
    if not data:
        await interaction.response.send_message("目前沒有任何幫戰報名資料。", ephemeral=True)
        return

    output = io.StringIO()
    headers = ["UserID", "顯示名稱", "職業流派", "裝備境界", "可出席時段", "語音狀況", "隊伍", "備註", "最後更新時間"]
    output.write(",".join(headers) + "\n")

    for info in data:
        uid = str(info["user_id"])
        row = [
            uid,
            info.get("display_name", "").replace(",", "，"),
            info.get("job", "").replace(",", "，"),
            info.get("gear", "").replace(",", "，"),
            info.get("availability", "").replace(",", "，"),
            info.get("voice", "").replace(",", "，"),
            info.get("team", "未分配").replace(",", "，"),
            info.get("note", "").replace("\n", " ").replace(",", "，"),
            info.get("timestamp", ""),
        ]
        output.write(",".join(row) + "\n")

    output.seek(0)
    file = discord.File(fp=io.BytesIO(output.getvalue().encode("utf-8")), filename="signups.csv")
    await interaction.response.send_message(
        content=f"📂 共有 **{len(data)}** 筆幫戰報名資料，以下為匯出檔：",
        file=file,
        ephemeral=True,
    )

def main():
    init_db()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("環境變數 DISCORD_BOT_TOKEN 未設定")
    bot.run(token)

if __name__ == "__main__":
    main()
