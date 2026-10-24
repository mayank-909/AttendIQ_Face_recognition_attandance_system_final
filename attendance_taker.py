import dlib
import numpy as np
import cv2
import os
import sys
import pandas as pd
import time
import logging
import sqlite3
import datetime
from scipy.spatial import distance as dist

# Dlib setup
detector    = dlib.get_frontal_face_detector()
predictor   = dlib.shape_predictor('data/data_dlib/shape_predictor_68_face_landmarks.dat')
face_reco   = dlib.face_recognition_model_v1("data/data_dlib/dlib_face_recognition_resnet_model_v1.dat")

# DB setup
conn   = sqlite3.connect("attendance.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS attendance (name TEXT, time TEXT, date DATE, UNIQUE(name, date))")
conn.commit()
conn.close()

# ── Blink Detection ───────────────────────────────────────────────────────────
EAR_THRESH        = 0.22   # EAR below this = eye closed
EAR_CONSEC        = 2      # consecutive frames for blink
STABLE_FRAMES     = 20     # frames before asking to blink
BLINK_TIMEOUT     = 8      # seconds to blink

LEFT_EYE  = list(range(42, 48))
RIGHT_EYE = list(range(36, 42))

def ear(eye):
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    return (A + B) / (2.0 * C)

def eye_pts(shape, idx):
    return [(shape.part(i).x, shape.part(i).y) for i in idx]
# ─────────────────────────────────────────────────────────────────────────────

def send_notify(name, date, time_val):
    try:
        import urllib.request, json as _j
        payload = _j.dumps({"name": name, "date": date, "time": time_val}).encode()
        req = urllib.request.Request("http://127.0.0.1:5000/notify/attendance",
            data=payload, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"Email notify error: {e}")

def already_marked_today(name):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn  = sqlite3.connect("attendance.db")
    row   = conn.execute("SELECT * FROM attendance WHERE name=? AND date=?", (name, today)).fetchone()
    conn.close()
    return row is not None

def mark_attendance(name):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    now   = datetime.datetime.now().strftime('%H:%M:%S')
    conn  = sqlite3.connect("attendance.db")
    try:
        conn.execute("INSERT INTO attendance (name, time, date) VALUES (?,?,?)", (name, now, today))
        conn.commit()
        print(f"{name} marked as present for {today} at {now}")
        send_notify(name, today, now)
    except sqlite3.IntegrityError:
        print(f"{name} already marked for {today}")
    conn.close()


class Face_Recognizer:
    def __init__(self):
        self.font     = cv2.FONT_HERSHEY_SIMPLEX
        self.fps      = 0
        self.frame_cnt = 0
        self.frame_start_time = time.time()

        self.face_features = []
        self.face_names    = []

        self.last_face_cnt  = 0
        self.cur_face_cnt   = 0
        self.last_names     = []
        self.cur_names      = []
        self.last_centroids = []
        self.cur_centroids  = []
        self.reclassify_cnt = 0
        self.reclassify_int = 10

        # Blink state per person
        self.blink = {}
        # {name: {status, stable, t_start, ear_cnt, blinked}}

    def load_db(self):
        if os.path.exists("data/features_all.csv"):
            df = pd.read_csv("data/features_all.csv", header=None)
            for i in range(df.shape[0]):
                self.face_names.append(df.iloc[i][0])
                feats = []
                for j in range(1, 129):
                    v = df.iloc[i][j]
                    feats.append(float(v) if v != '' else 0.0)
                self.face_features.append(feats)
            logging.info("Faces in Database: %d", len(self.face_names))
            return True
        else:
            logging.warning("features_all.csv not found! Auto-extracting...")
            try:
                import subprocess as sp
                sp.run([sys.executable, 'features_extraction_to_csv.py'],
                       cwd=os.path.dirname(os.path.abspath(__file__)), timeout=120)
                if os.path.exists("data/features_all.csv"):
                    return self.load_db()
            except Exception as e:
                logging.error(f"Auto-extract failed: {e}")
            return False

    def euclid(self, f1, f2):
        return float(np.sqrt(np.sum(np.square(np.array(f1) - np.array(f2)))))

    def recognize(self, img, face):
        shape    = predictor(img, face)
        desc     = face_reco.compute_face_descriptor(img, shape)
        dists    = [self.euclid(desc, f) for f in self.face_features]
        min_dist = min(dists)
        if min_dist < 0.4:
            return self.face_names[dists.index(min_dist)], shape
        return "unknown", shape

    def blink_check(self, img, name, face, shape):
        """Returns (rect_color, label_text)"""

        # Already marked today — just show green
        if already_marked_today(name):
            return (0, 200, 0), f"Present: {name.title()}"

        if name == "unknown":
            return (100, 100, 100), "Unknown"

        # Init blink state
        if name not in self.blink:
            self.blink[name] = {
                "status": "stabilizing",
                "stable": 0,
                "t_start": None,
                "ear_cnt": 0,
                "blinked": False
            }

        s = self.blink[name]

        # Eye landmarks
        le = eye_pts(shape, LEFT_EYE)
        re = eye_pts(shape, RIGHT_EYE)
        e  = (ear(le) + ear(re)) / 2.0

        # Draw eye dots
        for pt in le + re:
            cv2.circle(img, pt, 2, (0, 255, 255), -1)

        # ── STABILIZING ──
        if s["status"] == "stabilizing":
            s["stable"] += 1
            pct = int((s["stable"] / STABLE_FRAMES) * 100)
            # Progress bar
            bar_w = face.right() - face.left()
            cv2.rectangle(img, (face.left(), face.top() - 12),
                          (face.left() + bar_w, face.top() - 4), (50, 50, 50), -1)
            cv2.rectangle(img, (face.left(), face.top() - 12),
                          (face.left() + int(bar_w * s["stable"] / STABLE_FRAMES), face.top() - 4),
                          (0, 255, 255), -1)
            if s["stable"] >= STABLE_FRAMES:
                s["status"]  = "blink_req"
                s["t_start"] = time.time()
            return (0, 255, 255), f"Hold still... {name.title()}"

        # ── BLINK REQUIRED ──
        elif s["status"] == "blink_req":
            elapsed   = time.time() - s["t_start"]
            remaining = max(0, int(BLINK_TIMEOUT - elapsed))

            if e < EAR_THRESH:
                s["ear_cnt"] += 1
            else:
                if s["ear_cnt"] >= EAR_CONSEC:
                    s["blinked"] = True
                s["ear_cnt"] = 0

            if s["blinked"]:
                s["status"] = "verified"
                mark_attendance(name)
                return (0, 255, 0), f"Verified: {name.title()}"

            if elapsed > BLINK_TIMEOUT:
                s["status"] = "stabilizing"
                s["stable"] = 0
                s["blinked"] = False
                s["ear_cnt"] = 0
                return (0, 0, 255), f"Timeout - retry: {name.title()}"

            # Flash orange warning
            color = (0, 165, 255) if int(elapsed * 2) % 2 == 0 else (0, 100, 200)
            return color, f"BLINK NOW! {name.title()} ({remaining}s)"

        # ── VERIFIED ──
        elif s["status"] == "verified":
            return (0, 255, 0), f"Present: {name.title()}"

        return (255, 255, 255), name.title()

    def draw_hud(self, img):
        h, w = img.shape[:2]
        # Top bar
        cv2.rectangle(img, (0, 0), (w, 50), (20, 20, 20), -1)
        cv2.putText(img, "AttendIQ - Face Recognition", (10, 22),
                    self.font, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f"FPS: {self.fps:.1f}   Faces: {self.cur_face_cnt}   Frame: {self.frame_cnt}",
                    (10, 42), self.font, 0.45, (0, 255, 150), 1)
        # Bottom bar
        cv2.rectangle(img, (0, h - 36), (w, h), (20, 20, 20), -1)
        cv2.putText(img, "Anti-Spoof ON  |  Blink to verify  |  Press Q to quit",
                    (10, h - 12), self.font, 0.5, (0, 220, 255), 1)

    def process(self, cap):
        if not self.load_db():
            print("No face database found. Please register students first.")
            return

        cv2.namedWindow("AttendIQ", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("AttendIQ", 860, 540)

        while cap.isOpened():
            self.frame_cnt += 1
            ok, img = cap.read()
            if not ok or img is None:
                continue

            key = cv2.waitKey(1)
            if key == ord('q'):
                break

            faces = detector(img, 0)
            self.cur_face_cnt = len(faces)

            # Reclassify logic
            if (self.cur_face_cnt == self.last_face_cnt and
                    self.reclassify_cnt < self.reclassify_int):

                if "unknown" in self.cur_names:
                    self.reclassify_cnt += 1

                for k, face in enumerate(faces):
                    name = self.cur_names[k] if k < len(self.cur_names) else "unknown"
                    shape = predictor(img, face)
                    color, label = self.blink_check(img, name, face, shape)
                    cv2.rectangle(img, (face.left(), face.top()),
                                  (face.right(), face.bottom()), color, 2)
                    cv2.putText(img, label,
                                (face.left(), face.bottom() + 22),
                                self.font, 0.6, color, 2)
            else:
                self.reclassify_cnt = 0
                self.cur_names = []

                for k, face in enumerate(faces):
                    name, shape = self.recognize(img, face)
                    self.cur_names.append(name)
                    color, label = self.blink_check(img, name, face, shape)
                    cv2.rectangle(img, (face.left(), face.top()),
                                  (face.right(), face.bottom()), color, 2)
                    cv2.putText(img, label,
                                (face.left(), face.bottom() + 22),
                                self.font, 0.6, color, 2)

            self.last_face_cnt = self.cur_face_cnt
            self.last_names    = self.cur_names[:]

            # FPS
            now = time.time()
            elapsed = now - self.frame_start_time
            if elapsed > 0:
                self.fps = 1.0 / elapsed
            self.frame_start_time = now

            self.draw_hud(img)
            cv2.imshow("AttendIQ", img)

    def run(self):
        cap = cv2.VideoCapture(0)
        self.process(cap)
        cap.release()
        cv2.destroyAllWindows()


def main():
    logging.basicConfig(level=logging.INFO)
    Face_Recognizer().run()

if __name__ == '__main__':
    main()
