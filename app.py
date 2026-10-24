from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, flash
import sqlite3
import os
import io
import subprocess
import sys
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_OK = True
except ImportError:
    EXCEL_OK = False

app = Flask(__name__)
app.secret_key = "attendiq-secret-key"

DB = "attendance.db"
FACES_DIR = "data/data_faces_from_camera"

# Create students email table on startup
def init_db():
    conn = sqlite3.connect(DB)
    # Main attendance table
    conn.execute("""CREATE TABLE IF NOT EXISTS attendance
                    (name TEXT, time TEXT, date DATE, UNIQUE(name, date))""")
    # Students table with course info
    conn.execute("""CREATE TABLE IF NOT EXISTS students
                    (name TEXT PRIMARY KEY, email TEXT,
                     roll_no TEXT, course TEXT, year TEXT)""")
    # Add columns if upgrading from old version
    try:
        conn.execute("ALTER TABLE students ADD COLUMN roll_no TEXT")
    except: pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN course TEXT")
    except: pass
    try:
        conn.execute("ALTER TABLE students ADD COLUMN year TEXT")
    except: pass
    conn.commit()
    conn.close()

init_db()

# ── Email Config ───────────────────────────────────────────────────────────────
EMAIL_SENDER   = "mayankprajapat909@gmail.com"
EMAIL_PASSWORD = "ldwwomabwnzpcvvv"
EMAIL_RECEIVER = "mayankprajapat909@gmail.com"  # jisko email jaaye
EMAIL_ENABLED  = True
# ─────────────────────────────────────────────────────────────────────────────

# Track background processes
_proc = {}

def run_script(key, script):
    def target():
        _proc[key] = {"status": "running", "pid": None}
        try:
            pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
            p = subprocess.Popen(
                [pythonw, script],
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            _proc[key]["pid"] = p.pid
            p.wait()
            _proc[key]["status"] = "done"
        except Exception as e:
            _proc[key] = {"status": "error", "msg": str(e)}
    threading.Thread(target=target, daemon=True).start()


def get_student_email(name):
    """Get student email from database."""
    try:
        conn = sqlite3.connect(DB)
        row = conn.execute("SELECT email FROM students WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
        conn.close()
        return row[0] if row else None
    except:
        return None

def save_student_email(name, email):
    """Save student email to database."""
    try:
        conn = sqlite3.connect(DB)
        conn.execute("INSERT OR IGNORE INTO students (name) VALUES (?)", (name,))
        conn.execute("UPDATE students SET email=? WHERE LOWER(name)=LOWER(?)", (email, name))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Save email error: {e}")

def save_student_info(name, email, roll_no, course, year):
    """Save complete student info."""
    try:
        conn = sqlite3.connect(DB)
        conn.execute("""INSERT OR REPLACE INTO students (name, email, roll_no, course, year)
                        VALUES (?, ?, ?, ?, ?)""", (name, email, roll_no, course, year))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Save student info error: {e}")

def get_student_info(name):
    """Get student course info."""
    try:
        conn = sqlite3.connect(DB)
        row = conn.execute("SELECT * FROM students WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
        conn.close()
        return dict(row) if row else {}
    except:
        return {}

def send_email_notification(name, date, time_val):
    """Send email when attendance is marked."""
    if not EMAIL_ENABLED:
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = EMAIL_SENDER
        msg["Subject"] = f"✅ Attendance Marked — {name}"

        # Get student email — send to their email, fallback to admin
        student_email = get_student_email(name)
        receiver = student_email if student_email else EMAIL_RECEIVER
        msg["To"] = receiver

        html = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f4f6f9;padding:20px;">
        <div style="max-width:500px;margin:0 auto;background:white;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
          <div style="background:#2563eb;padding:20px;text-align:center;">
            <h2 style="color:white;margin:0;">AttendIQ Notification</h2>
          </div>
          <div style="padding:24px;">
            <p style="color:#64748b;margin-bottom:16px;">Your attendance has been marked successfully.</p>
            <table style="width:100%;border-collapse:collapse;">
              <tr style="background:#eff6ff;">
                <td style="padding:12px;font-weight:bold;color:#2563eb;">Student</td>
                <td style="padding:12px;color:#0f172a;">{name.title()}</td>
              </tr>
              <tr>
                <td style="padding:12px;font-weight:bold;color:#2563eb;">Date</td>
                <td style="padding:12px;color:#0f172a;">{date}</td>
              </tr>
              <tr style="background:#eff6ff;">
                <td style="padding:12px;font-weight:bold;color:#2563eb;">Time</td>
                <td style="padding:12px;color:#0f172a;">{time_val}</td>
              </tr>
              <tr>
                <td style="padding:12px;font-weight:bold;color:#059669;">Status</td>
                <td style="padding:12px;color:#059669;font-weight:bold;">✅ Present</td>
              </tr>
            </table>
          </div>
          <div style="background:#f4f6f9;padding:12px;text-align:center;">
            <p style="color:#94a3b8;font-size:12px;margin:0;">AttendIQ — Face Recognition Attendance System</p>
          </div>
        </div>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {receiver} for {name}")
    except Exception as e:
        print(f"Email error: {e}")


# ── helpers ───────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def count_registered_students():
    """Count student folders directly."""
    faces_dir = "data/data_faces_from_camera"
    if not os.path.exists(faces_dir):
        return 0
    seen = set()
    for folder in os.listdir(faces_dir):
        path = os.path.join(faces_dir, folder)
        if not os.path.isdir(path):
            continue
        parts = folder.split("_")
        clean = [p for p in parts if p.lower() != "person" and not p.isdigit()]
        name = " ".join(clean).strip().lower()
        if name:
            seen.add(name)
    return len(seen)

def sidebar_stats():
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    total_today = conn.execute("SELECT COUNT(*) FROM attendance WHERE date=?", (today,)).fetchone()[0]
    courses = conn.execute(
        "SELECT DISTINCT course FROM students WHERE course IS NOT NULL AND course != '' ORDER BY course"
    ).fetchall()
    conn.close()
    total_all = count_registered_students()
    sidebar_courses = [c[0] for c in courses]
    return {"total_today": total_today, "total_all": total_all, "today": today, "sidebar_courses": sidebar_courses}

def get_registered_students():
    merged = {}
    if os.path.exists(FACES_DIR):
        for folder in sorted(os.listdir(FACES_DIR)):
            path = os.path.join(FACES_DIR, folder)
            if not os.path.isdir(path):
                continue
            parts = folder.split("_")
            clean = [p for p in parts if p.lower() != "person" and not p.isdigit()]
            name = " ".join(clean).strip().title() if clean else folder.title()
            photo_count = len([f for f in os.listdir(path) if f.lower().endswith((".jpg",".jpeg",".png"))])
            if name in merged:
                merged[name]["photos"] += photo_count
                merged[name]["folders"].append(folder)
            else:
                merged[name] = {"folders": [folder], "photos": photo_count}
    students = []
    for name, data in merged.items():
        students.append({"folder": data["folders"][0], "name": name, "photos": data["photos"], "folder_count": len(data["folders"])})
    return sorted(students, key=lambda x: x["name"])

def get_monthly_percentage(name):
    """Calculate monthly attendance percentage for a student."""
    conn = get_db()
    # Total unique dates in DB (total working days)
    total_days = conn.execute("SELECT COUNT(DISTINCT date) FROM attendance").fetchone()[0]
    # Days present for this student
    present_days = conn.execute(
        "SELECT COUNT(DISTINCT date) FROM attendance WHERE name=?", (name.lower(),)
    ).fetchone()[0]
    conn.close()
    if total_days == 0:
        return 0
    return round((present_days / total_days) * 100, 1)

# ── Save student full info ───────────────────────────────────────────────────
@app.route("/register/student-info", methods=["POST"])
def register_student_info():
    data = request.json
    name     = data.get("name","").strip()
    email    = data.get("email","").strip()
    roll_no  = data.get("roll_no","").strip()
    course   = data.get("course","").strip()
    year     = data.get("year","").strip()
    if not name or not roll_no or not course or not year:
        return jsonify({"ok": False, "msg": "Name, Roll No, Course and Year are required"})
    # Check duplicate roll no
    conn = get_db()
    existing = conn.execute(
        "SELECT name FROM students WHERE roll_no=? AND LOWER(name)!=LOWER(?)",
        (roll_no, name)
    ).fetchone()
    conn.close()
    if existing:
        return jsonify({"ok": False, "msg": f"Roll No {roll_no} already used by {existing[0]}"})
    save_student_info(name, email, roll_no, course, year)
    return jsonify({"ok": True})

# ── Delete student ───────────────────────────────────────────────────────────
@app.route("/delete/student", methods=["POST"])
def delete_student():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "msg": "Name missing"})
    try:
        # Delete face photos folder
        if os.path.exists(FACES_DIR):
            for folder in os.listdir(FACES_DIR):
                path = os.path.join(FACES_DIR, folder)
                if os.path.isdir(path):
                    parts = folder.split("_")
                    clean = " ".join([p for p in parts if p.lower() != "person" and not p.isdigit()]).strip()
                    if clean.lower() == name.lower():
                        import shutil
                        shutil.rmtree(path)
                        print(f"Deleted folder: {path}")

        # Delete from attendance DB
        conn = get_db()
        conn.execute("DELETE FROM attendance WHERE LOWER(name)=LOWER(?)", (name,))
        conn.execute("DELETE FROM students WHERE LOWER(name)=LOWER(?)", (name,))
        conn.commit()
        conn.close()

        # Remove from CSV
        csv_path = "data/features_all.csv"
        if os.path.isfile(csv_path):
            import csv as _csv
            rows = []
            with open(csv_path, newline="") as f:
                for row in _csv.reader(f):
                    if row and row[0].strip().lower() != name.lower():
                        rows.append(row)
            with open(csv_path, "w", newline="") as f:
                _csv.writer(f).writerows(rows)

        return jsonify({"ok": True, "msg": f"'{name}' deleted successfully!"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

@app.route("/delete/student/date", methods=["POST"])
def delete_student_date():
    data = request.json
    name = data.get("name","").strip()
    date = data.get("date","").strip()
    if not name or not date:
        return jsonify({"ok": False, "msg": "Name or date missing"})
    try:
        conn = get_db()
        conn.execute("DELETE FROM attendance WHERE LOWER(name)=LOWER(?) AND date=?", (name, date))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "msg": f"Attendance of '{name}' for {date} deleted."})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

# ── Student email registration ────────────────────────────────────────────────
@app.route("/register/email", methods=["POST"])
def register_email():
    data = request.json
    name  = data.get("name", "").strip()
    email = data.get("email", "").strip()
    if name and email:
        save_student_email(name, email)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Name or email missing"})

# ── Attendance hook — send email when marked ──────────────────────────────────
@app.route("/notify/attendance", methods=["POST"])
def notify_attendance():
    data = request.json
    name     = data.get("name", "")
    date     = data.get("date", "")
    time_val = data.get("time", "")
    threading.Thread(
        target=send_email_notification,
        args=(name, date, time_val),
        daemon=True
    ).start()
    return jsonify({"ok": True})

# ── camera routes ─────────────────────────────────────────────────────────────

@app.route("/launch/attendance", methods=["POST"])
def launch_attendance():
    if _proc.get("attendance", {}).get("status") == "running":
        return jsonify({"ok": False, "msg": "Attendance camera already running."})
    run_script("attendance", "attendance_taker.py")
    return jsonify({"ok": True, "msg": "Attendance camera launched! It will open on your screen."})

@app.route("/launch/register", methods=["POST"])
def launch_register():
    if _proc.get("register", {}).get("status") == "running":
        return jsonify({"ok": False, "msg": "Registration camera already running."})
    run_script("register", "get_faces_from_camera_tkinter.py")
    return jsonify({"ok": True, "msg": "Registration camera launched! Enter name and save photos."})

@app.route("/launch/extract", methods=["POST"])
def launch_extract():
    if _proc.get("extract", {}).get("status") == "running":
        return jsonify({"ok": False, "msg": "Feature extraction already running."})
    # Use python.exe (not pythonw) for this script — it needs console
    def run_extract():
        _proc["extract"] = {"status": "running", "pid": None}
        try:
            p = subprocess.Popen(
                [sys.executable, "features_extraction_to_csv.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            _proc["extract"]["pid"] = p.pid
            p.wait()
            _proc["extract"]["status"] = "done"
        except Exception as e:
            _proc["extract"] = {"status": "error", "msg": str(e)}
    threading.Thread(target=run_extract, daemon=True).start()
    return jsonify({"ok": True, "msg": "Feature extraction started! This updates the face database."})

@app.route("/launch/status")
def launch_status():
    return jsonify({k: v.get("status","idle") for k,v in _proc.items()})

@app.route("/api/live")
def api_live():
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    total_today = conn.execute("SELECT COUNT(*) FROM attendance WHERE date=?", (today,)).fetchone()[0]
    total_all   = count_registered_students()
    recent_rows = conn.execute(
        "SELECT name, time, date FROM attendance ORDER BY date DESC, time DESC LIMIT 5"
    ).fetchall()
    latest = conn.execute(
        "SELECT name FROM attendance WHERE date=? ORDER BY time DESC LIMIT 1", (today,)
    ).fetchone()
    conn.close()

    latest_name = latest["name"].title() if latest else ""

    # Build recent HTML rows
    rows_html = ""
    for row in recent_rows:
        name = row["name"].title()
        initial = name[0].upper()
        rows_html += f"""
        <tr>
          <td><div style="display:flex;align-items:center;gap:10px;">
            <div class="name-av">{initial}</div>
            <span style="font-weight:600;">{name}</span>
          </div></td>
          <td style="color:var(--muted);">{row["date"]}</td>
          <td><span class="badge badge-blue"><i class="ti ti-clock"></i> {row["time"]}</span></td>
          <td><span class="badge badge-green"><i class="ti ti-check"></i> Present</span></td>
        </tr>"""

    return jsonify({
        "today": total_today,
        "total": total_all,
        "latest_name": latest_name,
        "recent_html": rows_html
    })

# ── main routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    s = sidebar_stats()
    conn = get_db()
    recent = conn.execute("SELECT name, time, date FROM attendance ORDER BY date DESC, time DESC LIMIT 5").fetchall()
    conn.close()
    return render_template("index.html", page="dashboard", recent=recent, **s)

@app.route("/attendance", methods=["GET","POST"])
def attendance():
    s = sidebar_stats()
    selected_date = ""
    attendance_data = []
    no_data = False
    if request.method == "POST":
        selected_date = request.form.get("selected_date","")
    else:
        selected_date = request.args.get("date","")
    if selected_date:
        conn = get_db()
        rows = conn.execute("SELECT name, time FROM attendance WHERE date=? ORDER BY time", (selected_date,)).fetchall()
        conn.close()
        attendance_data = rows
        no_data = len(rows) == 0
    conn2 = get_db()
    months = conn2.execute(
        "SELECT DISTINCT strftime('%Y-%m', date) as m FROM attendance ORDER BY m DESC"
    ).fetchall()
    conn2.close()
    available_months = [r["m"] for r in months]
    return render_template("attendance.html", page="attendance", selected_date=selected_date,
                           attendance_data=attendance_data, no_data=no_data,
                           available_months=available_months, **s)

@app.route("/students")
def students():
    s = sidebar_stats()
    student_list = get_registered_students()
    conn = get_db()
    attendance_counts = {}
    percentages = {}
    student_info = {}
    for st in student_list:
        count = conn.execute("SELECT COUNT(DISTINCT date) FROM attendance WHERE name=?", (st["name"].lower(),)).fetchone()[0]
        attendance_counts[st["name"]] = count
        percentages[st["name"]] = get_monthly_percentage(st["name"])
        info = conn.execute("SELECT * FROM students WHERE LOWER(name)=LOWER(?)", (st["name"],)).fetchone()
        student_info[st["name"]] = dict(info) if info else {}
    conn.close()
    # Group by course
    courses = {}
    for st in student_list:
        info = student_info.get(st["name"], {})
        course = info.get("course", "Unassigned")
        year   = info.get("year", "")
        key    = f"{course} — {year}" if year else course
        if key not in courses:
            courses[key] = []
        courses[key].append(st)

    return render_template("students.html", page="students", students=student_list,
                           attendance_counts=attendance_counts, percentages=percentages,
                           student_info=student_info, courses=courses, **s)

@app.route("/analytics")
def analytics():
    s = sidebar_stats()
    conn = get_db()
    daily = []
    for i in range(6,-1,-1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        count = conn.execute("SELECT COUNT(*) FROM attendance WHERE date=?", (day,)).fetchone()[0]
        daily.append({"date": day, "label": (datetime.now()-timedelta(days=i)).strftime("%a"), "count": count})
    top_rows = conn.execute("SELECT name, COUNT(DISTINCT date) as cnt FROM attendance GROUP BY name ORDER BY cnt DESC LIMIT 8").fetchall()
    top = [(r["name"], r["cnt"]) for r in top_rows]
    monthly_rows = conn.execute("SELECT strftime('%Y-%m', date) as month, COUNT(*) as cnt FROM attendance GROUP BY month ORDER BY month DESC LIMIT 6").fetchall()
    monthly = [{"month": r["month"], "cnt": r["cnt"]} for r in monthly_rows]

    # Monthly percentage per student
    student_rows = conn.execute("SELECT DISTINCT name FROM attendance").fetchall()
    total_days = conn.execute("SELECT COUNT(DISTINCT date) FROM attendance").fetchone()[0]
    student_percentages = []
    for row in student_rows:
        name = row["name"]
        present = conn.execute("SELECT COUNT(DISTINCT date) FROM attendance WHERE name=?", (name,)).fetchone()[0]
        pct = round((present / total_days) * 100, 1) if total_days > 0 else 0
        student_percentages.append({"name": name.title(), "present": present, "total": total_days, "pct": pct})
    student_percentages.sort(key=lambda x: x["pct"], reverse=True)

    conn.close()
    return render_template("analytics.html", page="analytics", daily=daily, top=top,
                           monthly=monthly, student_percentages=student_percentages, **s)

@app.route("/settings", methods=["GET","POST"])
def settings():
    s = sidebar_stats()
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "clear_date":
            date = request.form.get("clear_date")
            if date:
                conn = get_db()
                conn.execute("DELETE FROM attendance WHERE date=?", (date,))
                conn.commit()
                conn.close()
                message = {"type": "success", "text": f"Records for {date} deleted."}
        elif action == "clear_all":
            conn = get_db()
            conn.execute("DELETE FROM attendance")
            conn.commit()
            conn.close()
            message = {"type": "warning", "text": "All attendance records deleted."}
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    dates = conn.execute("SELECT DISTINCT date FROM attendance ORDER BY date DESC").fetchall()
    conn.close()
    # Get registered students and their emails
    reg_students = get_registered_students()
    conn2 = get_db()
    email_rows = conn2.execute("SELECT name, email FROM students").fetchall()
    conn2.close()
    student_emails = {r["name"]: r["email"] for r in email_rows}

    return render_template("settings.html", page="settings", message=message, total_records=total, dates=dates,
                           email_enabled=EMAIL_ENABLED, email_receiver=EMAIL_RECEIVER,
                           registered_students=reg_students, student_emails=student_emails, **s)

@app.route("/export/excel")
def export_excel():
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    if not EXCEL_OK:
        return "Run: pip install openpyxl", 500
    conn = get_db()
    rows = conn.execute("SELECT name, time, date FROM attendance WHERE date=? ORDER BY time", (date_str,)).fetchall()
    conn.close()
    return _make_excel(rows, f"attendance_{date_str}.xlsx")

@app.route("/export/monthly")
def export_monthly():
    if not EXCEL_OK:
        return "Run: pip install openpyxl", 500
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    conn = get_db()
    rows = conn.execute(
        "SELECT name, time, date FROM attendance WHERE strftime('%Y-%m', date)=? ORDER BY date, time",
        (month,)
    ).fetchall()
    conn.close()
    return _make_excel(rows, f"attendance_{month}.xlsx")

@app.route("/export/all")
def export_all():
    if not EXCEL_OK:
        return "Run: pip install openpyxl", 500
    conn = get_db()
    rows = conn.execute("SELECT name, time, date FROM attendance ORDER BY date DESC, time").fetchall()
    conn.close()
    return _make_excel(rows, "attendance_all.xlsx")

def _make_excel(rows, filename):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(["#","Name","Time","Date"])
    hfill = PatternFill("solid", fgColor="2563EB")
    hfont = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = hfill; cell.font = hfont; cell.alignment = Alignment(horizontal="center")
    for i, r in enumerate(rows, 1):
        ws.append([i, r["name"].title(), r["time"], r["date"]])
    for col, w in zip(["A","B","C","D"], [5,28,15,15]):
        ws.column_dimensions[col].width = w
    out = io.BytesIO()
    wb.save(out); out.seek(0)
    return send_file(out, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=filename)

if __name__ == "__main__":
    app.run(debug=True)
