import dlib
import numpy as np
import cv2
import os
import sys
import shutil
import time
import logging
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import csv

detector = dlib.get_frontal_face_detector()

PREDICTOR_PATH   = "data/data_dlib/shape_predictor_68_face_landmarks.dat"
RECOGNITION_PATH = "data/data_dlib/dlib_face_recognition_resnet_model_v1.dat"
FEATURES_CSV     = "data/features_all.csv"
DUPLICATE_THRESHOLD = 0.35

try:
    predictor       = dlib.shape_predictor(PREDICTOR_PATH)
    face_reco_model = dlib.face_recognition_model_v1(RECOGNITION_PATH)
    RECO_LOADED     = True
except Exception as e:
    logging.warning(f"Recognition models not loaded: {e}")
    RECO_LOADED = False


def get_face_descriptor(frame_rgb):
    try:
        faces = detector(frame_rgb, 0)
        if not faces:
            return None
        shape = predictor(frame_rgb, faces[0])
        return np.array(face_reco_model.compute_face_descriptor(frame_rgb, shape))
    except:
        return None


def check_duplicate(descriptor):
    if not RECO_LOADED or not os.path.isfile(FEATURES_CSV):
        return False, None
    try:
        with open(FEATURES_CSV, newline="") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                name = row[0]
                feat_start = 2 if len(row) >= 130 else 1
                saved = np.array([float(x) for x in row[feat_start:feat_start+128]])
                if len(saved) != 128:
                    continue
                if np.linalg.norm(descriptor - saved) < DUPLICATE_THRESHOLD:
                    return True, name
        return False, None
    except Exception as e:
        return False, None


def get_existing_names():
    names = []
    if not os.path.isfile(FEATURES_CSV):
        return names
    try:
        with open(FEATURES_CSV, newline="") as f:
            for row in csv.reader(f):
                if row and row[0].strip().lower() not in names:
                    names.append(row[0].strip().lower())
    except:
        pass
    return names


C = {
    "bg": "#f4f6f9", "white": "#ffffff", "border": "#e2e8f0", "border2": "#cbd5e1",
    "text": "#0f172a", "muted": "#64748b", "faint": "#94a3b8",
    "blue": "#2563eb", "blue_l": "#eff6ff",
    "green": "#059669", "green_l": "#ecfdf5",
    "amber": "#d97706", "amber_l": "#fffbeb",
    "red": "#dc2626", "red_l": "#fef2f2",
    "indigo": "#4338ca",
}

# ── Guided angles ─────────────────────────────────────────────────────────────
ANGLES = [
    {"name": "Front",      "instruction": "Look straight at camera",     "arrow": None,  "color": (37,99,235)},
    {"name": "Turn Left",  "instruction": "Slowly turn your head LEFT",  "arrow": "←",   "color": (5,150,105)},
    {"name": "Turn Right", "instruction": "Slowly turn your head RIGHT", "arrow": "→",   "color": (5,150,105)},
    {"name": "Look Up",    "instruction": "Tilt your head slightly UP",  "arrow": "↑",   "color": (217,119,6)},
    {"name": "Look Down",  "instruction": "Tilt your head slightly DOWN","arrow": "↓",   "color": (217,119,6)},
]
PHOTOS_PER_ANGLE = 6   # 5 angles × 6 = 30 photos total
HOLD_FRAMES      = 18  # frames to hold before auto-capture starts
# ─────────────────────────────────────────────────────────────────────────────


class Face_Register:
    def __init__(self):
        self.existing_faces_cnt       = 0
        self.input_name_char          = ""
        self.out_of_range_flag        = False
        self.face_folder_created_flag = False
        self.frame_start_time         = time.time()
        self.fps                      = 0
        self.path_photos              = "data/data_faces_from_camera/"
        self.current_face_dir         = ""
        self.font_cv                  = cv2.FONT_HERSHEY_SIMPLEX
        self.current_frame            = np.ndarray
        self.face_ROI_w_start = self.face_ROI_h_start = 0
        self.face_ROI_w = self.face_ROI_h = 0
        self.ww = self.hh = 0
        self._db_val = self._frm_val = None

        # Guided registration state
        self.guided_active   = False
        self.angle_idx       = 0
        self.hold_cnt        = 0
        self.angle_photos    = 0
        self.total_saved     = 0
        self.capture_flash   = 0

        self.cap = cv2.VideoCapture(0)
        self._registration_done = False
        self._build_ui()

    def _build_ui(self):
        self.win = tk.Tk()
        self.win.title("AttendIQ — Face Register")
        self.win.geometry("1280x680")
        self.win.resizable(True, True)
        self.win.configure(bg=C["bg"])
        self.win.state('zoomed')

        # Header
        header = tk.Frame(self.win, bg=C["white"], height=58)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        logo = tk.Frame(header, bg=C["blue"], width=36, height=36)
        logo.place(x=16, y=11)
        tk.Label(logo, text="👁", bg=C["blue"], fg="white",
                 font=("Segoe UI Emoji", 16)).place(relx=.5, rely=.5, anchor="center")
        tk.Label(header, text="AttendIQ", bg=C["white"], fg=C["text"],
                 font=("Segoe UI", 14, "bold")).place(x=60, y=17)
        tk.Label(header, text="|", bg=C["white"], fg=C["faint"],
                 font=("Segoe UI", 14)).place(x=152, y=17)
        tk.Label(header, text="Face Registration", bg=C["white"], fg=C["muted"],
                 font=("Segoe UI", 10)).place(x=168, y=21)
        badge = tk.Frame(header, bg=C["green_l"], padx=10, pady=3)
        badge.place(relx=1.0, x=-16, y=14, anchor="ne")
        tk.Label(badge, text="●", bg=C["green_l"], fg=C["green"],
                 font=("Segoe UI", 8)).pack(side=tk.LEFT)
        tk.Label(badge, text="Camera Active", bg=C["green_l"], fg=C["green"],
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(4,0))

        tk.Frame(self.win, bg=C["border"], height=1).pack(fill=tk.X)

        body = tk.Frame(self.win, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # LEFT — camera
        left = tk.Frame(body, bg=C["white"], highlightbackground=C["border"], highlightthickness=1)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,16))

        cam_hdr = tk.Frame(left, bg=C["white"], pady=10)
        cam_hdr.pack(fill=tk.X, padx=16)
        tk.Label(cam_hdr, text="📷  Camera Preview", bg=C["white"], fg=C["text"],
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.fps_label = tk.Label(cam_hdr, text="FPS: --", bg=C["blue_l"], fg=C["blue"],
                                   font=("Segoe UI", 9, "bold"), padx=8, pady=3)
        self.fps_label.pack(side=tk.RIGHT)
        tk.Frame(left, bg=C["border"], height=1).pack(fill=tk.X)

        self.camera_label = tk.Label(left, bg="#1a1a2e")
        self.camera_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.status_bar = tk.Label(left, text="Waiting for camera...",
                                    bg=C["amber_l"], fg=C["amber"],
                                    font=("Segoe UI", 9), pady=6)
        self.status_bar.pack(fill=tk.X)

        # RIGHT panel
        right_outer = tk.Frame(body, bg=C["bg"], width=340)
        right_outer.pack(side=tk.RIGHT, fill=tk.Y)
        right_outer.pack_propagate(False)

        canvas = tk.Canvas(right_outer, bg=C["bg"], highlightthickness=0)
        sb = tk.Scrollbar(right_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = tk.Frame(canvas, bg=C["bg"], width=320)
        canvas.create_window((0,0), window=right, anchor="nw")
        right.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Stat cards
        stats = tk.Frame(right, bg=C["bg"])
        stats.pack(fill=tk.X, pady=(0,14))
        self._stat_card(stats, "Faces in DB",   "0", C["blue"],  C["blue_l"],  "db").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,6))
        self._stat_card(stats, "Current Frame", "0", C["green"], C["green_l"], "frm").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Step 1 — Clear
        self._section(right, "1", "Clear Face Data", "Remove all registered faces", C["red"], C["red_l"])
        tk.Button(right, text="🗑  Clear All Data", command=self.GUI_clear_data,
                  bg=C["red_l"], fg=C["red"], font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", activebackground="#fecaca", pady=8
                  ).pack(fill=tk.X, pady=(0,14))

        # Step 2 — Name
        self._section(right, "2", "Enter Student Name", "Type name then click Input", C["blue"], C["blue_l"])
        name_row = tk.Frame(right, bg=C["bg"])
        name_row.pack(fill=tk.X, pady=(0,8))
        self.input_name = tk.Entry(name_row, font=("Segoe UI", 11), relief="flat",
                                    bg=C["white"], fg=C["text"], insertbackground=C["blue"],
                                    highlightthickness=1, highlightbackground=C["border"],
                                    highlightcolor=C["blue"])
        self.input_name.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0,8))
        self.input_name.bind("<Return>", lambda e: self.GUI_get_input_name())
        tk.Button(name_row, text="Input", command=self.GUI_get_input_name,
                  bg=C["blue"], fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", activebackground="#1d4ed8",
                  padx=16, pady=8).pack(side=tk.RIGHT)

        tk.Label(right, text="Email (optional)", bg=C["bg"], fg=C["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0,4))
        self.input_email = tk.Entry(right, font=("Segoe UI", 11), relief="flat",
                                     bg=C["white"], fg=C["text"], insertbackground=C["blue"],
                                     highlightthickness=1, highlightbackground=C["border"],
                                     highlightcolor=C["blue"])
        self.input_email.pack(fill=tk.X, ipady=8, pady=(0,14))

        # Step 3 — Guided capture
        self._section(right, "3", "Guided Face Capture",
                      "5 angles captured automatically", C["green"], C["green_l"])

        # Angle progress indicators
        self.angle_frame = tk.Frame(right, bg=C["bg"])
        self.angle_frame.pack(fill=tk.X, pady=(0,8))
        self.angle_labels = []
        for i, a in enumerate(ANGLES):
            lbl = tk.Label(self.angle_frame, text=f"{a['name']}", bg=C["border"],
                           fg=C["muted"], font=("Segoe UI", 8, "bold"),
                           padx=4, pady=4, relief="flat")
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.angle_labels.append(lbl)

        self.progress_label = tk.Label(right, text="Click 'Start Guided Capture' to begin",
                                        bg=C["blue_l"], fg=C["blue"],
                                        font=("Segoe UI", 9, "bold"), pady=6)
        self.progress_label.pack(fill=tk.X, pady=(0,8))

        self.start_btn = tk.Button(right, text="▶  Start Guided Capture",
                                    command=self.start_guided,
                                    bg=C["green"], fg="white",
                                    font=("Segoe UI", 11, "bold"),
                                    relief="flat", cursor="hand2",
                                    activebackground="#047857", pady=12)
        self.start_btn.pack(fill=tk.X, pady=(0,8))

        # Finish button
        tk.Frame(right, bg=C["border"], height=1).pack(fill=tk.X, pady=(0,8))
        tk.Button(right, text="✅  Finish Registration & Close",
                  command=self._finish_registration,
                  bg=C["blue"], fg="white", font=("Segoe UI", 11, "bold"),
                  relief="flat", cursor="hand2",
                  activebackground="#1d4ed8", pady=12).pack(fill=tk.X, pady=(0,14))

        # Log
        log_frame = tk.Frame(right, bg=C["white"],
                              highlightbackground=C["border"], highlightthickness=1)
        log_frame.pack(fill=tk.X)
        tk.Label(log_frame, text="Activity Log", bg=C["white"], fg=C["muted"],
                 font=("Segoe UI", 9, "bold"), pady=6, padx=10, anchor="w").pack(fill=tk.X)
        tk.Frame(log_frame, bg=C["border"], height=1).pack(fill=tk.X)
        self.log_all = tk.Label(log_frame, text="Enter name and click Input to begin.",
                                 bg=C["white"], fg=C["muted"], font=("Segoe UI", 9),
                                 wraplength=290, justify=tk.LEFT, padx=10, pady=8, anchor="w")
        self.log_all.pack(fill=tk.X)

    def _stat_card(self, parent, label, value, color, bg_color, key):
        card = tk.Frame(parent, bg=bg_color, padx=12, pady=10,
                        highlightbackground=color, highlightthickness=1)
        val = tk.Label(card, text=value, bg=bg_color, fg=color, font=("Segoe UI", 22, "bold"))
        val.pack()
        tk.Label(card, text=label, bg=bg_color, fg=color, font=("Segoe UI", 8)).pack()
        if key == "db":   self._db_val  = val
        elif key == "frm": self._frm_val = val
        return card

    def _section(self, parent, number, title, subtitle, color, bg_color):
        frame = tk.Frame(parent, bg=bg_color, padx=10, pady=8,
                         highlightbackground=color, highlightthickness=1)
        frame.pack(fill=tk.X, pady=(0,8))
        num_box = tk.Frame(frame, bg=color, width=28, height=28)
        num_box.pack(side=tk.LEFT, padx=(0,10))
        num_box.pack_propagate(False)
        tk.Label(num_box, text=number, bg=color, fg="white",
                 font=("Segoe UI", 11, "bold")).place(relx=.5, rely=.5, anchor="center",
                                                       relwidth=1.0, relheight=1.0)
        col = tk.Frame(frame, bg=bg_color)
        col.pack(side=tk.LEFT)
        tk.Label(col, text=title, bg=bg_color, fg=C["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(col, text=subtitle, bg=bg_color, fg=color,
                 font=("Segoe UI", 8)).pack(anchor="w")

    def _set_log(self, msg, color=None):
        self.log_all["text"] = msg
        if color: self.log_all["fg"] = color

    def _set_status(self, msg, fg, bg):
        self.status_bar["text"] = msg
        self.status_bar["fg"]   = fg
        self.status_bar["bg"]   = bg

    def start_guided(self):
        if not self.face_folder_created_flag:
            self._set_log("Please enter name and click Input first!", C["red"])
            return
        self.guided_active = True
        self.angle_idx     = 0
        self.hold_cnt      = 0
        self.angle_photos  = 0
        self.total_saved   = 0
        self.start_btn.config(state=tk.DISABLED, text="Capturing...")
        self._update_angle_ui()
        self._set_log(f"Guided capture started! Follow the instructions.", C["blue"])

    def _update_angle_ui(self):
        if self.angle_idx >= len(ANGLES):
            return
        for i, lbl in enumerate(self.angle_labels):
            if i < self.angle_idx:
                lbl.config(bg=C["green"], fg="white")
            elif i == self.angle_idx:
                lbl.config(bg=C["blue"], fg="white")
            else:
                lbl.config(bg=C["border"], fg=C["muted"])
        a = ANGLES[self.angle_idx]
        self.progress_label.config(
            text=f"Angle {self.angle_idx+1}/5: {a['name']} — {self.angle_photos}/{PHOTOS_PER_ANGLE} photos",
            bg=C["blue_l"], fg=C["blue"]
        )

    def GUI_clear_data(self):
        if not messagebox.askyesno("Confirm", "Delete ALL registered face data?"):
            return
        for folder in os.listdir(self.path_photos):
            shutil.rmtree(self.path_photos + folder)
        if os.path.isfile(FEATURES_CSV):
            os.remove(FEATURES_CSV)
        self.existing_faces_cnt = 0
        if self._db_val: self._db_val["text"] = "0"
        self._set_log("All face data cleared.", C["red"])
        self._set_status("Database cleared.", C["amber"], C["amber_l"])

    def GUI_get_input_name(self):
        self.input_name_char = self.input_name.get().strip()
        if not self.input_name_char:
            self._set_log("Please enter a name first!", C["red"])
            return

        new_name_lower = self.input_name_char.strip().lower()
        existing = get_existing_names()

        if new_name_lower in existing:
            messagebox.showerror("Name Already Registered",
                f"'{self.input_name_char}' is already registered!")
            self._set_log(f"Blocked — '{self.input_name_char}' exists!", C["red"])
            return

        new_first = new_name_lower.split()[0]
        for ex in existing:
            if new_first == ex.split()[0]:
                if not messagebox.askyesno("Similar Name",
                    f"'{ex.title()}' already registered.\n\nIs '{self.input_name_char}' a different person?"):
                    self._set_log("Cancelled.", C["amber"])
                    return
                break

        if RECO_LOADED and isinstance(self.current_frame, np.ndarray):
            self._set_log("Checking duplicate face...", C["amber"])
            self.win.update()
            desc = get_face_descriptor(self.current_frame)
            if desc is not None:
                is_dup, matched = check_duplicate(desc)
                if is_dup:
                    messagebox.showerror("Duplicate Face",
                        f"Face already registered as:\n\"{matched}\"\n\nEach person registers once.")
                    self._set_log(f"Blocked — matches '{matched}'", C["red"])
                    return

        self._create_folder()
        if self._db_val: self._db_val["text"] = str(self.existing_faces_cnt)
        self._set_log(f"Ready! Click 'Start Guided Capture' for {self.input_name_char}", C["green"])
        self._set_status(f"Registered: {self.input_name_char} — now start guided capture", C["blue"], C["blue_l"])

    def _create_folder(self):
        self.existing_faces_cnt += 1
        self.current_face_dir = (self.path_photos +
                                  f"person_{self.existing_faces_cnt}_{self.input_name_char}")
        os.makedirs(self.current_face_dir, exist_ok=True)
        self.face_folder_created_flag = True
        self.total_saved = 0

    def _finish_registration(self):
        if self._registration_done:
            return
        if not self.face_folder_created_flag:
            self._set_log("Please complete Steps 2 & 3 first!", C["red"])
            return
        if self.total_saved < 10:
            if not messagebox.askyesno("Low Photos",
                f"Only {self.total_saved} photos saved.\nRecommended: 30\n\nClose anyway?"):
                return
        self._registration_done = True
        email = self.input_email.get().strip() if hasattr(self, 'input_email') else ""
        if email:
            try:
                import urllib.request, json as _j
                payload = _j.dumps({"name": self.input_name_char, "email": email}).encode()
                req = urllib.request.Request("http://127.0.0.1:5000/register/email",
                    data=payload, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=3)
            except Exception as e:
                print(f"Email save error: {e}")

        name_saved  = self.input_name_char
        total_saved = self.total_saved
        email_saved = email
        cwd         = os.path.dirname(os.path.abspath(__file__))

        self._set_log("Updating face database... please wait.", C["amber"])
        self._set_status("Extracting features in background...", C["amber"], C["amber_l"])
        self.win.update()

        import threading as _th
        import subprocess as sp

        def do_extract():
            try:
                sp.run([sys.executable, "features_extraction_to_csv.py"],
                       cwd=cwd, timeout=120)
            except Exception as e:
                print(f"Extract error: {e}")
            self.win.after(0, lambda: self._on_extract_done(name_saved, total_saved, email_saved))

        _th.Thread(target=do_extract, daemon=True).start()

    def _on_extract_done(self, name, total, email):
        """Called after feature extraction completes."""
        messagebox.showinfo("Registration Complete!",
            f"✅ '{name}' registered successfully!\n\n"
            f"Photos captured: {total}\n"
            f"Email: {email if email else 'Not provided'}\n\n"
            f"Face database updated! Ready to mark attendance.")
        self.cap.release()
        self.win.destroy()

    def pre_work_mkdir(self):
        os.makedirs(self.path_photos, exist_ok=True)

    def check_existing_faces_cnt(self):
        nums = []
        for f in os.listdir("data/data_faces_from_camera/"):
            try:
                nums.append(int(f.split('_')[1]))
            except:
                pass
        self.existing_faces_cnt = max(nums) if nums else 0
        if self._db_val: self._db_val["text"] = str(self.existing_faces_cnt)

    def get_frame(self):
        try:
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    frame = cv2.resize(frame, (640, 480))
                    return ret, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except:
            pass

    def _guided_capture(self, display, faces):
        """Handle guided angle capture. Returns overlay display."""
        if not self.guided_active or self.angle_idx >= len(ANGLES):
            return display

        a = ANGLES[self.angle_idx]
        h, w = display.shape[:2]

        # Overlay instruction panel at bottom
        overlay = display.copy()
        cv2.rectangle(overlay, (0, h-80), (w, h), (0,0,0), -1)
        cv2.addWeighted(overlay, 0.6, display, 0.4, 0, display)

        # Arrow + instruction
        instruction = f"{a['name']}: {a['instruction']}"
        if a["arrow"]:
            instruction = f"{a['arrow']}  {instruction}  {a['arrow']}"

        cv2.putText(display, instruction, (20, h-45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255,255,255), 2)

        progress = f"Angle {self.angle_idx+1}/5  |  Photo {self.angle_photos}/{PHOTOS_PER_ANGLE}  |  Total: {self.total_saved}/30"
        cv2.putText(display, progress, (20, h-15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,220,255), 1)

        # Progress bar
        bar_total = w - 40
        bar_filled = int(bar_total * (self.total_saved / 30))
        cv2.rectangle(display, (20, h-88), (20+bar_total, h-82), (50,50,50), -1)
        cv2.rectangle(display, (20, h-88), (20+bar_filled, h-82), (0,200,100), -1)

        if len(faces) == 1:
            face = faces[0]
            self.hold_cnt += 1

            # Countdown circle
            countdown = max(0, HOLD_FRAMES - self.hold_cnt)
            if countdown > 0:
                cv2.putText(display, f"Hold... {countdown}", (face.left(), face.top()-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
            else:
                # Auto capture
                roi_h = face.bottom() - face.top()
                roi_w = face.right() - face.left()
                hh = int(roi_h / 2)
                ww = int(roi_w / 2)

                y1 = max(0, face.top() - hh)
                y2 = min(480, face.bottom() + hh)
                x1 = max(0, face.left() - ww)
                x2 = min(640, face.right() + ww)

                if y2 > y1 and x2 > x1:
                    roi = self.current_frame[y1:y2, x1:x2]
                    if roi.size > 0:
                        fname = f"{self.current_face_dir}/img_face_{self.total_saved+1}.jpg"
                        cv2.imwrite(fname, cv2.cvtColor(roi, cv2.COLOR_RGB2BGR))
                        self.angle_photos += 1
                        self.total_saved  += 1
                        self.hold_cnt      = 0
                        self.capture_flash = 5

                        self._set_log(
                            f"📸 {a['name']}: {self.angle_photos}/{PHOTOS_PER_ANGLE} — Total: {self.total_saved}/30",
                            C["green"]
                        )
                        self._update_angle_ui()

                        if self.angle_photos >= PHOTOS_PER_ANGLE:
                            self.angle_idx   += 1
                            self.angle_photos = 0
                            self.hold_cnt     = 0
                            if self.angle_idx >= len(ANGLES):
                                self.guided_active = False
                                self.start_btn.config(state=tk.NORMAL, text="✓ Capture Complete!")
                                self.start_btn.config(bg=C["green"])
                                for lbl in self.angle_labels:
                                    lbl.config(bg=C["green"], fg="white")
                                self.progress_label.config(
                                    text=f"✅ All 30 photos captured! Click Finish.",
                                    bg=C["green_l"], fg=C["green"]
                                )
                                self._set_log("✅ All angles captured! Click Finish Registration.", C["green"])
                                self._set_status("Registration complete — click Finish!", C["green"], C["green_l"])
                            else:
                                next_a = ANGLES[self.angle_idx]
                                self._set_log(f"Next: {next_a['name']} — {next_a['instruction']}", C["blue"])
                                self._update_angle_ui()
        else:
            self.hold_cnt = 0
            msg = "No face detected" if len(faces) == 0 else "Multiple faces — only 1 allowed"
            cv2.putText(display, msg, (20, h-50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)

        # Flash effect on capture
        if self.capture_flash > 0:
            flash = display.copy()
            cv2.rectangle(flash, (0,0), (w,h), (255,255,255), -1)
            cv2.addWeighted(flash, 0.3, display, 0.7, 0, display)
            self.capture_flash -= 1

        return display

    def process(self):
        result = self.get_frame()
        if result is None:
            self.win.after(20, self.process)
            return

        ret, self.current_frame = result
        faces = detector(self.current_frame, 0)

        if ret:
            now = time.time()
            elapsed = now - self.frame_start_time
            self.fps = 1.0 / elapsed if elapsed > 0 else 0
            self.frame_start_time = now
            self.fps_label["text"] = f"FPS: {self.fps:.1f}"
            if self._frm_val: self._frm_val["text"] = str(len(faces))

            display = self.current_frame.copy()

            for d in faces:
                oor = ((d.right() + int((d.right()-d.left())/2)) > 640 or
                       (d.bottom() + int((d.bottom()-d.top())/2)) > 480 or
                       (d.left() - int((d.right()-d.left())/2)) < 0 or
                       (d.top() - int((d.bottom()-d.top())/2)) < 0)
                color = (220,38,38) if oor else (37,99,235)
                cv2.rectangle(display, (d.left(), d.top()), (d.right(), d.bottom()), color, 2)
                if not oor and not self.guided_active:
                    self._set_status("Face detected — ready to capture", C["green"], C["green_l"])

            if len(faces) == 0 and not self.guided_active:
                self._set_status("No face detected — position yourself", C["amber"], C["amber_l"])

            if self.guided_active:
                display = self._guided_capture(display, faces)

            img_tk = ImageTk.PhotoImage(image=Image.fromarray(display))
            self.camera_label.img_tk = img_tk
            self.camera_label.configure(image=img_tk)

        self.win.after(20, self.process)

    def _safe_close(self):
        """Called when X button is pressed — just close without registering."""
        if self._registration_done:
            return
        if self.face_folder_created_flag and self.total_saved > 0:
            if not messagebox.askyesno("Close?",
                f"Registration not complete.\n{self.total_saved} photos saved.\n\nClose without saving?"):
                return
            # Delete incomplete folder
            import shutil
            if os.path.exists(self.current_face_dir):
                shutil.rmtree(self.current_face_dir)
        self.cap.release()
        self.win.destroy()

    def run(self):
        self.pre_work_mkdir()
        self.check_existing_faces_cnt()
        self.win.protocol("WM_DELETE_WINDOW", self._safe_close)
        self.process()
        self.win.mainloop()


def main():
    logging.basicConfig(level=logging.INFO)
    Face_Register().run()

if __name__ == '__main__':
    main()
