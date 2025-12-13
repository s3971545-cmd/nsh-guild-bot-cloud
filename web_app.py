import os
from flask import Flask, render_template_string, request, redirect, url_for

from db import init_db, db_list_all_signups, db_update_team

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
    .summary-pill { padding:6px 10px; border-radius:999px; border:1px solid #1f2937; font-size:12px; background:#020617; }
    .summary-pill.total { border-color:#00e8d1; color:#00e8d1; }
    .summary-pill.team-off1 { border-color:#f97316; color:#fed7aa; }
    .summary-pill.team-off2 { border-color:#facc15; color:#fef9c3; }
    .summary-pill.team-def  { border-color:#22c55e; color:#bbf7d0; }
    .summary-pill.team-sub  { border-color:#6366f1; color:#c7d2fe; }
    .summary-pill.team-leave { border-color:#fb7185; color:#fecdd3; }
    .summary-pill.team-unassigned { border-color:#4b5563; color:#e5e7eb; }

    .team-block { border-radius:16px; padding:14px 16px 12px; margin-bottom:18px;
      background: radial-gradient(circle at top left, #0f172a, #020617 55%);
      border:1px solid #111827; box-shadow:0 18px 40px rgba(0,0,0,.45);
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

    select { background:#020617; color:#e5e7eb; border:1px solid #374151; padding:2px 6px; border-radius:6px; font-size:11px; }
    button { margin-top:12px; padding:6px 14px; border-radius:999px; border:none; background:#00e8d1; color:#020617; font-weight:600; cursor:pointer; font-size:13px; }
    button:hover { opacity:0.92; }

    .badge { display:inline-flex; align-items:center; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:500; }
    .badge.team-off1 { background:#f97316; color:#0b1120; }
    .badge.team-off2 { background:#facc15; color:#0b1120; }
    .badge.team-def  { background:#22c55e; color:#022c22; }
    .badge.team-sub  { background:#6366f1; color:#e5e7eb; }
    .badge.team-leave { background:#fb7185; color:#0f0f0f; }
    .badge.team-unassigned { background:#4b5563; color:#e5e7eb; }
  </style>
</head>
<body>
  <h1>⚔ 幫戰報名管理後台</h1>
  <p class="sub">
    這裡可以檢視所有報名名單，並調整每位成員的隊伍（進攻1 / 進攻2 / 防守 / 替補 / 請假 / 未分配）。<br>
    調整後按「儲存隊伍調整」，隊伍會寫入資料庫（不會再 reset）。
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
                <td><span class="badge {{ row.team_class }}">{{ row.team }}</span></td>
                <td>
                  <select name="team_{{ row.guild_id }}_{{ row.user_id }}">
                    {% for t in teams_order %}
                      <option value="{{ t }}" {% if row.team == t %}selected{% endif %}>{{ t }}</option>
                    {% endfor %}
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
    if request.method == "POST":
        for key, value in request.form.items():
            if not key.startswith("team_"):
                continue
            _, gid, uid = key.split("_", 2)
            db_update_team(int(gid), int(uid), value)
        return redirect(url_for("index"))

    rows_raw = db_list_all_signups()
    teams_order = ["進攻1", "進攻2", "防守", "替補", "請假", "未分配"]
    class_map = {
        "進攻1": "team-off1",
        "進攻2": "team-off2",
        "防守": "team-def",
        "替補": "team-sub",
        "請假": "team-leave",
        "未分配": "team-unassigned",
    }

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

    sections, summary, total = [], [], 0
    for t in teams_order:
        rows = sorted(team_blocks[t], key=lambda x: (x["guild_id"], x["display_name"]))
        count = len(rows)
        total += count
        sections.append({"team": t, "rows": rows, "count": count, "badge_class": class_map.get(t, "team-unassigned")})
        summary.append({"team": t, "count": count, "team_class": class_map.get(t, "team-unassigned")})

    return render_template_string(
        HTML_TEMPLATE,
        sections=sections,
        summary=summary,
        total=total,
        teams_order=teams_order,
    )

def main():
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
