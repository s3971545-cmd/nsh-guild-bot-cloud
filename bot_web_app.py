import psycopg2
from psycopg2.extras import RealDictCursor

import os
import json
import io
import threading
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from flask import Flask, render_template_string, request, redirect, url_for

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("環境變數 DATABASE_URL 未設定（Render Postgres 未連上）")
    # Render Postgres 通常需要 SSL
    if "sslmode=" not in DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signups (
                    guild_id BIGINT NOT NULL,
                    user_id  BIGINT NOT NULL,
                    user_name TEXT,
                    display_name TEXT,
                    job TEXT,
                    gear TEXT,
                    availability TEXT,
                    voice TEXT,
                    note TEXT,
                    team TEXT DEFAULT '未分配',
                    timestamp TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (guild_id, user_id)
                );
            """)
        conn.commit()

def db_upsert_signup(guild_id: int, user_id: int, info: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO signups
                (guild_id, user_id, user_name, display_name, job, gear, availability, voice, note, team, timestamp, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    user_name=EXCLUDED.user_name,
                    display_name=EXCLUDED.display_name,
                    job=EXCLUDED.job,
                    gear=EXCLUDED.gear,
                    availability=EXCLUDED.availability,
                    voice=EXCLUDED.voice,
                    note=EXCLUDED.note,
                    team=EXCLUDED.team,
                    timestamp=EXCLUDED.timestamp,
                    updated_at=NOW();
            """, (
                guild_id, user_id,
                info.get("user_name"),
                info.get("display_name"),
                info.get("job"),
                info.get("gear"),
                info.get("availability"),
                info.get("voice"),
                info.get("note"),
                info.get("team", "未分配"),
                info.get("timestamp"),
            ))
        conn.commit()

def db_get_signup(guild_id: int, user_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM signups WHERE guild_id=%s AND user_id=%s;", (guild_id, user_id))
            return cur.fetchone()

def db_list_signups_by_guild(guild_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM signups WHERE guild_id=%s ORDER BY display_name ASC;", (guild_id,))
            return cur.fetchall()

def db_list_all_signups():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM signups ORDER BY guild_id ASC, display_name ASC;")
            return cur.fetchall()

def db_update_team(guild_id: int, user_id: int, team: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE signups SET team=%s, updated_at=NOW()
                WHERE guild_id=%s AND user_id=%s;
            """, (team, guild_id, user_id))
        conn.commit()


# ========= Discord Bot =========

intents = discord.Intents.default()
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

    embed = discord.Embed(
        title="📋 你的幫戰報名資料",
        color=0x00d1c4,
    )
    embed.add_field(name="顯示名稱", value=info.get("display_name", "（無）"), inline=False)
    embed.add_field(name="職業 / 流派", value=info.get("job", "（無）"), inline=True)
    embed.add_field(name="裝備 / 境界", value=info.get("gear", "（無）"), inline=True)
    embed.add_field(name="可出席時段", value=info.get("availability", "（無）"), inline=False)
    embed.add_field(name="語音狀況", value=info.get("voice", "（無）"), inline=True)
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
    # ⭐ 標題多一欄「隊伍」
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



        row = [
            uid,
            info.get("display_name", "").replace(",", "，"),
            info.get("job", "").replace(",", "，"),
            info.get("gear", "").replace(",", "，"),
            info.get("availability", "").replace(",", "，"),
            info.get("voice", "").replace(",", "，"),
            info.get("team", "未分配").replace(",", "，"),  # ⭐ 新增：隊伍欄位
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


# ========= Flask Web 後台 =========

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <title>幫戰報名管理後台</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #020617; color: #e6edf7; }
    h1 { color: #00e8d1; margin-bottom: 4px; }
    .sub { color:#9ca3af; font-size:12px; margin-bottom:16px; }

    .summary-bar { display:flex; flex-wrap:wrap; gap:8px; margin: 12px 0 20px; }
    .summary-pill {
      padding:6px 10px;
      border-radius:999px;
      border:1px solid #1f2937;
      font-size:12px;
      background:#020617;
    }
    .summary-pill.total { border-color:#00e8d1; color:#00e8d1; }

    .summary-pill.team-off1 { border-color:#f97316; color:#fed7aa; }
    .summary-pill.team-off2 { border-color:#facc15; color:#fef9c3; }
    .summary-pill.team-def  { border-color:#22c55e; color:#bbf7d0; }
    .summary-pill.team-sub  { border-color:#6366f1; color:#c7d2fe; }
    .summary-pill.team-unassigned { border-color:#4b5563; color:#e5e7eb; }
    .summary-pill.team-leave { border-color:#fb7185; color:#fecdd3; }

    .team-block {
      border-radius:16px;
      padding:14px 16px 12px;
      margin-bottom:18px;
      background: radial-gradient(circle at top left, #0f172a, #020617 55%);
      border:1px solid #111827;
      box-shadow:0 18px 40px rgba(0,0,0,.45);
    }
    .team-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
    .team-title { display:flex; align-items:center; gap:8px; }
    .team-name { font-weight:600; font-size:14px; }
    .muted { color:#9ca3af; font-size:12px; }
    .empty { padding:4px 0 4px 2px; }

    table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 4px; }
    th, td { border-bottom: 1px solid #1f2937; padding: 4px 6px; text-align: left; }
    th { background: #020617; color:#9ca3af; font-weight:500; }
    tr:last-child td { border-bottom: none; }

    select {
      background:#020617;
      color:#e5e7eb;
      border:1px solid #374151;
      padding:2px 6px;
      border-radius:6px;
      font-size:11px;
    }
    button {
      margin-top:12px;
      padding:6px 14px;
      border-radius:999px;
      border:none;
      background:#00e8d1;
      color:#020617;
      font-weight:600;
      cursor:pointer;
      font-size:13px;
    }
    button:hover { opacity:0.92; }

    .badge {
      display:inline-flex;
      align-items:center;
      padding:2px 8px;
      border-radius:999px;
      font-size:11px;
      font-weight:500;
    }
    .badge.team-off1 { background:#f97316; color:#0b1120; }
    .badge.team-off2 { background:#facc15; color:#0b1120; }
    .badge.team-def  { background:#22c55e; color:#022c22; }
    .badge.team-sub  { background:#6366f1; color:#e5e7eb; }
    .badge.team-unassigned { background:#4b5563; color:#e5e7eb; }
    .badge.team-leave { background:#fb7185; color:#0f0f0f; } /* 粉紅色 */

  </style>
</head>
<body>
  <h1>⚔ 幫戰報名管理後台</h1>
  <p class="sub">
    這裡可以檢視所有報名名單，並調整每位成員的隊伍（進攻1 / 進攻2 / 防守 / 替補 / 請假/未分配）。<br>
    調整後記得按下方「儲存隊伍調整」，隊伍會同步寫入資料庫，並反映在匯出的 CSV。
  </p>

  <div class="summary-bar">
    <div class="summary-pill total">總人數：{{ total }}</div>
    {% for s in summary %}
      <div class="summary-pill {{ s.team_class }}">{{ s.team }}：{{ s.count }}</div>
    {% endfor %}
  </div>

  <form method="post" action="{{ url_for('index') }}">
    {% for sec in sections %}
      <div class="team-block">
        <div class="team-header">
          <div class="team-title">
            <span class="badge {{ sec.badge_class }}">{{ sec.team }}</span>
            <span class="team-name">{{ sec.team }}</span>
            <span class="muted">（{{ sec.count }} 人）</span>
          </div>
        </div>

        {% if sec.rows %}
          <table>
            <tr>
              <th>伺服器 ID</th>
              <th>顯示名稱</th>
              <th>職業 / 流派</th>
              <th>裝備 / 境界</th>
              <th>可出席時段</th>
              <th>語音</th>
              <th>備註</th>
              <th>現在隊伍</th>
              <th>調整隊伍</th>
              <th>最後更新</th>
            </tr>
            {% for row in sec.rows %}
              <tr>
                <td>{{ row.guild_id }}</td>
                <td>{{ row.display_name }}</td>
                <td>{{ row.job }}</td>
                <td>{{ row.gear }}</td>
                <td>{{ row.availability }}</td>
                <td>{{ row.voice }}</td>
                <td>{{ row.note }}</td>
                <td>
                  <span class="badge {{ row.team_class }}">{{ row.team }}</span>
                </td>
                <td>
                  <select name="team_{{ row.guild_id }}_{{ row.user_id }}">
    <option value="未分配" {% if row.team == "未分配" %}selected{% endif %}>未分配</option>
    <option value="進攻1" {% if row.team == "進攻1" %}selected{% endif %}>進攻1</option>
    <option value="進攻2" {% if row.team == "進攻2" %}selected{% endif %}>進攻2</option>
    <option value="防守" {% if row.team == "防守" %}selected{% endif %}>防守</option>
    <option value="替補" {% if row.team == "替補" %}selected{% endif %}>替補</option>
    <option value="請假" {% if row.team == "請假" %}selected{% endif %}>請假</option>
</select>

                </td>
                <td>{{ row.timestamp }}</td>
              </tr>
            {% endfor %}
          </table>
        {% else %}
          <p class="muted empty">目前這個隊伍沒有成員。</p>
        {% endif %}
      </div>
    {% endfor %}

    <button type="submit">💾 儲存隊伍調整</button>
  </form>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    # ===== POST：儲存隊伍（寫入 PostgreSQL）=====
    if request.method == "POST":
        for key, value in request.form.items():
            if not key.startswith("team_"):
                continue
            _, gid, uid = key.split("_", 2)
            db_update_team(int(gid), int(uid), value)
        return redirect(url_for("index"))

    # ===== GET：從 PostgreSQL 讀取資料 =====
    rows_raw = db_list_all_signups()  # ← 關鍵：不再用 data.items()

    teams_order = ["進攻1", "進攻2", "防守", "替補", "請假", "未分配"]
    class_map = {
        "進攻1": "team-off1",
        "進攻2": "team-off2",
        "防守": "team-def",
        "替補": "team-sub",
        "請假": "team-leave",
        "未分配": "team-unassigned",
    }

    # 依隊伍分組
    team_blocks = {t: [] for t in teams_order}

    for r in rows_raw:
        team = r.get("team") or "未分配"
        if team not in team_blocks:
            team = "未分配"

        row = {
            "guild_id": str(r["guild_id"]),
            "user_id": str(r["user_id"]),
            "display_name": r.get("display_name", ""),
            "job": r.get("job", ""),
            "gear": r.get("gear", ""),
            "availability": r.get("availability", ""),
            "voice": r.get("voice", ""),
            "note": r.get("note", ""),
            "team": team,
            "team_class": class_map.get(team, "team-unassigned"),
            "timestamp": r.get("timestamp", ""),
        }

        team_blocks[team].append(row)

    # 組合給 HTML 用的 sections
    sections = []
    summary = []
    total = 0

    for t in teams_order:
        rows = sorted(team_blocks[t], key=lambda x: (x["guild_id"], x["display_name"]))
        count = len(rows)
        total += count

        sections.append({
            "team": t,
            "rows": rows,
            "count": count,
            "badge_class": class_map.get(t, "team-unassigned"),
        })

        summary.append({
            "team": t,
            "count": count,
            "team_class": class_map.get(t, "team-unassigned"),
        })

    guild_count = len(set(r["guild_id"] for r in rows_raw))

    return render_template_string(
        HTML_TEMPLATE,
        sections=sections,
        summary=summary,
        total=total,
        guild_count=guild_count,
    )



# ========= 同時啟動 Bot + Web =========

def run_discord_bot():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("環境變數 DISCORD_BOT_TOKEN 未設定")
    bot.run(token)

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    t = threading.Thread(target=run_discord_bot, daemon=True)
    t.start()
    run_flask()

