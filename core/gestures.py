"""
core/gestures.py — control the PC with hand gestures through the webcam.

Uses MediaPipe's GestureRecognizer (models/gesture_recognizer.task, ~8 MB),
which recognises seven hand shapes, plus a swipe detector built on the wrist
position it reports.

DEFAULT ACTIONS ("gesture_actions" in config overrides any of them)
    Open_Palm      ✋  play / pause media
    Closed_Fist    ✊  mute / unmute
    Thumb_Up       👍  volume up 10   (repeats while held)
    Thumb_Down     👎  volume down 10 (repeats while held)
    Victory        ✌️  next track
    Pointing_Up    ☝️  previous track
    ILoveYou       🤟  wake SAM
    swipe_left     ←   back      (browser / explorer)
    swipe_right    →   forward

    A value is any computer_settings action ("volume_up", "go_back", ...),
    "wake_sam", or "" to disable that gesture.

KEEPING IT CHEAP AND SAFE
    * OFF by default ("gestures_enabled"); nothing is imported or opened until
      it is switched on.
    * 320x240 frames, ~8 per second, on its own thread.
    * A gesture fires only after it has been seen steadily for STABLE_SECONDS,
      then rests for COOLDOWN_SECONDS — a hand passing through the frame does
      nothing. Only volume repeats while held.
    * Nothing destructive is ever mapped: media, volume, navigation, waking.
    * The camera is released while SAM itself uses it (screen_process with
      the webcam) and taken back afterwards.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "gesture_recognizer.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
             "gesture_recognizer/float16/latest/gesture_recognizer.task")

DEFAULT_ACTIONS = {
    "Open_Palm": "media_play_pause",
    "Closed_Fist": "toggle_mute",
    "Thumb_Up": "volume_up",
    "Thumb_Down": "volume_down",
    "Victory": "media_next",
    "Pointing_Up": "media_previous",
    "ILoveYou": "wake_sam",
    "swipe_left": "go_back",
    "swipe_right": "go_forward",
}
REPEATING = {"Thumb_Up", "Thumb_Down"}
LABELS = {
    "Open_Palm": "✋ open palm", "Closed_Fist": "✊ fist", "Thumb_Up": "👍 thumbs up",
    "Thumb_Down": "👎 thumbs down", "Victory": "✌️ victory", "Pointing_Up": "☝️ pointing up",
    "ILoveYou": "🤟 rock", "swipe_left": "← swipe", "swipe_right": "→ swipe",
}

FRAME_W, FRAME_H = 320, 240          # what the recogniser sees
VIEW_W, VIEW_H = 640, 480            # what is captured, shown and snapshotted
TARGET_FPS = 8
VIEW_FPS = 15                        # loop rate while the HUD shows the feed
MIN_SCORE = 0.6
STABLE_SECONDS = 0.5
COOLDOWN_SECONDS = 1.5
REPEAT_SECONDS = 0.9
SWIPE_WINDOW = 0.5          # seconds of wrist history a swipe is judged over
SWIPE_DISTANCE = 0.30       # fraction of the frame width the wrist must travel


# ── pure logic (tested without a camera) ─────────────────────────────────────

class GestureLogic:
    """Turns a stream of (time, gesture, score, wrist_x) into actions to fire."""

    def __init__(self, actions: dict | None = None):
        self.actions = dict(DEFAULT_ACTIONS)
        if actions:
            self.actions.update({k: str(v or "") for k, v in actions.items()})
        self._current: Optional[str] = None
        self._since = 0.0
        self._last_fire: dict[str, float] = {}
        self._wrist: deque = deque()

    def feed(self, t: float, gesture: Optional[str], score: float,
             wrist_x: Optional[float]) -> Optional[str]:
        """Returns the gesture name to fire now, or None."""
        # swipe first: a moving hand is not a held pose
        if wrist_x is not None:
            self._wrist.append((t, wrist_x))
        while self._wrist and t - self._wrist[0][0] > SWIPE_WINDOW:
            self._wrist.popleft()
        if len(self._wrist) >= 3:
            dx = self._wrist[-1][1] - self._wrist[0][1]
            if abs(dx) >= SWIPE_DISTANCE:
                name = "swipe_right" if dx > 0 else "swipe_left"
                self._wrist.clear()
                self._current = None
                if self._ready(name, t):
                    return name
                return None

        if not gesture or gesture == "None" or score < MIN_SCORE:
            self._current = None
            return None
        if gesture != self._current:
            self._current, self._since = gesture, t
            return None
        if t - self._since < STABLE_SECONDS:
            return None
        if gesture in REPEATING:
            if t - self._last_fire.get(gesture, 0.0) >= REPEAT_SECONDS:
                self._last_fire[gesture] = t
                return gesture
            return None
        if self._ready(gesture, t):
            return gesture
        return None

    def _ready(self, name: str, t: float) -> bool:
        if not self.actions.get(name):
            return False
        if t - self._last_fire.get(name, -1e9) < COOLDOWN_SECONDS:
            return False
        self._last_fire[name] = t
        # a held non-repeating pose fires once until the hand changes
        self._current = None if name.startswith("swipe") else name
        self._since = float("inf") if not name.startswith("swipe") else self._since
        return True


# ── the controller (camera + model on a thread) ─────────────────────────────

class GestureController:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._status = "off"
        self._running = False
        self.last_gesture = ""
        self.log: Callable[[str], None] = print
        self.on_wake: Callable[[], None] = lambda: None
        # When set, every captured frame is also handed to the HUD as JPEG, so
        # the camera view and gestures share ONE camera handle (Windows usually
        # lets only one open it).
        self.frame_sink: Optional[Callable[[bytes], None]] = None
        self.latest_jpeg: bytes = b""
        self.latest_at = 0.0

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, val: str) -> None:
        self._status = val

    # public ---------------------------------------------------------------
    def running(self) -> bool:
        return self._running and bool(self._thread and self._thread.is_alive())

    def start(self) -> str:
        if self.running():
            return "already running"
        problem = missing()
        if problem:
            self.status = "unavailable"
            return problem
        self._stop.clear()
        self._paused.clear()
        self._running = True
        self.status = "starting"
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gestures")
        self._thread.start()
        return "started"

    def stop(self) -> None:
        self._stop.set()
        self._status = 'off'
        self._running = False
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=1.0)

    def pause(self) -> None:
        """Release the camera (SAM is about to use it)."""
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    # internals ------------------------------------------------------------
    def _open_camera(self):
        import cv2
        try:
            from actions.screen_processor import _get_camera_index, _cv2_backend
            index, backend = _get_camera_index(), _cv2_backend()
        except Exception:
            index, backend = 0, getattr(cv2, "CAP_DSHOW", 0)
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIEW_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIEW_H)
        return cap

    def _loop(self) -> None:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        try:
            recognizer = vision.GestureRecognizer.create_from_options(
                vision.GestureRecognizerOptions(
                    base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
                    running_mode=vision.RunningMode.VIDEO, num_hands=1))
        except Exception as e:
            self.status = "error"
            self.log(f"SYS: Gestures could not start — {e}")
            return

        logic = GestureLogic(_configured_actions())
        cap = None
        t0 = time.monotonic()
        n_frames = 0
        try:
            while not self._stop.is_set():
                if self._paused.is_set():
                    if cap is not None:
                        cap.release()
                        cap = None
                    self.status = "paused"
                    time.sleep(0.3)
                    continue
                if cap is None:
                    cap = self._open_camera()
                    if cap is None:
                        self.status = "no camera"
                        self.log("SYS: Gestures: no camera could be opened — retrying in 10 s.")
                        if self._stop.wait(10):
                            break
                        continue
                    self.status = "watching"
                    self.log("SYS: Gesture control is watching the camera.")
                started = time.monotonic()
                ok, frame = cap.read()
                if not ok:
                    cap.release()
                    cap = None
                    continue
                frame = cv2.flip(frame, 1)                       # mirror view
                ok_jpg, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok_jpg:
                    self.latest_jpeg, self.latest_at = jpg.tobytes(), time.monotonic()
                    sink = self.frame_sink
                    if sink:
                        try:
                            sink(self.latest_jpeg)
                        except Exception:
                            pass
                n_frames += 1
                # While the feed is on screen the loop runs faster for a smooth
                # picture, but the model still sees about 8 frames a second.
                if self.frame_sink and n_frames % 2:
                    spare = 1.0 / VIEW_FPS - (time.monotonic() - started)
                    if spare > 0 and self._stop.wait(spare):
                        break
                    continue
                small = cv2.resize(frame, (FRAME_W, FRAME_H))
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = int((time.monotonic() - t0) * 1000)
                res = recognizer.recognize_for_video(image, ts)
                gesture, score, wrist = None, 0.0, None
                if res.gestures:
                    top = res.gestures[0][0]
                    gesture, score = top.category_name, float(top.score)
                if res.hand_landmarks:
                    wrist = float(res.hand_landmarks[0][0].x)
                fire = logic.feed(time.monotonic(), gesture, score, wrist)
                if fire:
                    self._fire(fire, logic.actions.get(fire, ""))
                fps = VIEW_FPS if self.frame_sink else TARGET_FPS
                spare = 1.0 / fps - (time.monotonic() - started)
                if spare > 0 and self._stop.wait(spare):
                    break
        except Exception as e:
            self.status = "error"
            self.log(f"SYS: Gesture control stopped — {e}")
        finally:
            if cap is not None:
                cap.release()
            try:
                recognizer.close()
            except Exception:
                pass
            self._running = False
            if self.status not in ("error",):
                self.status = "off"

    def _fire(self, gesture: str, action: str) -> None:
        self.last_gesture = gesture
        label = LABELS.get(gesture, gesture)
        try:
            if action == "wake_sam":
                self.on_wake()
                self.log(f"SYS: Gesture {label} — waking SAM.")
                return
            from actions.computer_settings import computer_settings
            params = {"action": action}
            if action in ("volume_up", "volume_down"):
                params["value"] = 10
            computer_settings(params)
            self.log(f"SYS: Gesture {label} → {action.replace('_', ' ')}")
        except Exception as e:
            self.log(f"SYS: Gesture {label} failed — {e}")


def _configured_actions() -> dict:
    try:
        from memory.config_manager import load_api_keys
        v = load_api_keys().get("gesture_actions")
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def missing() -> str:
    """'' when gestures can run, otherwise what is missing, in one sentence."""
    import importlib.util
    if importlib.util.find_spec("mediapipe") is None:
        return "mediapipe is not installed (pip install mediapipe)"
    if importlib.util.find_spec("cv2") is None:
        return "OpenCV is not installed (pip install opencv-contrib-python)"
    if not MODEL_PATH.exists():
        return "the gesture model is missing (models/gesture_recognizer.task)"
    return ""


def download_model() -> str:
    """Fetch models/gesture_recognizer.task if it is missing. Returns '' or an error."""
    if MODEL_PATH.exists():
        return ""
    try:
        import urllib.request
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = MODEL_PATH.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(MODEL_PATH)
        return ""
    except Exception as e:
        return f"download failed: {e}"


_controller: Optional[GestureController] = None


def controller() -> GestureController:
    global _controller
    if _controller is None:
        _controller = GestureController()
    return _controller
