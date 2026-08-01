from __future__ import annotations

import sqlite3


def render_daily_report(connection: sqlite3.Connection, report_date: str) -> str:
    scan_rows = connection.execute(
        """SELECT source_name, status, discovered, new_count, changed,
                  skipped_unchanged, failed, deferred_budget
           FROM scan_runs WHERE substr(started_at, 1, 10) = ? ORDER BY source_name""",
        (report_date,),
    ).fetchall()
    decision_rows = connection.execute(
        """SELECT d.decision, r.repo_key, s.provider, s.native_id, d.reasons_json
           FROM decisions d
           JOIN repositories r ON r.id = d.repository_id
           JOIN candidates c ON c.id = d.candidate_id
           JOIN source_versions sv ON sv.id = c.source_version_id
           JOIN sources s ON s.id = sv.source_id
           WHERE substr(d.decided_at, 1, 10) = ?
           ORDER BY CASE d.decision
             WHEN 'URGENT_INVESTIGATION' THEN 1 WHEN 'INVESTIGATE' THEN 2
             WHEN 'WATCH' THEN 3 ELSE 4 END""",
        (report_date,),
    ).fetchall()

    lines = ["# Günlük Teknoloji Fayda Radarı", "", f"Tarih: {report_date}", ""]
    lines.extend(["## Tarama durumu", ""])
    if not scan_rows:
        lines.append("Bu tarih için tarama kaydı bulunmuyor.")
    else:
        for row in scan_rows:
            lines.append(
                f"- {row['source_name']}: {row['status']} — "
                f"{row['discovered']} bulundu, {row['new_count']} yeni, "
                f"{row['changed']} değişti, {row['failed']} hata, "
                f"{row['deferred_budget']} bütçe nedeniyle ertelendi."
            )
    lines.extend(["", "## Bugün mutlaka bakılması gereken", ""])
    urgent = [row for row in decision_rows if row["decision"] == "URGENT_INVESTIGATION"]
    if not urgent:
        lines.extend(["Bulgu yok.", "", "`IMPORTANT_FINDINGS=0`  ", "`SCAN_STATUS=SUCCESS`"])
    else:
        for row in urgent:
            lines.append(f"- **{row['repo_key']}** — {row['provider']}:{row['native_id']}")
    lines.extend(["", "## Diğer araştırma kararları", ""])
    others = [row for row in decision_rows if row["decision"] != "URGENT_INVESTIGATION"]
    if not others:
        lines.append("Başka karar yok.")
    else:
        for row in others:
            lines.append(
                f"- {row['decision']}: **{row['repo_key']}** — "
                f"{row['provider']}:{row['native_id']}"
            )
    lines.append("")
    return "\n".join(lines)

