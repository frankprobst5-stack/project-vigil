# PROJECT IBRIS // Local Webcam Motion Detector -- headless adaptation
# Licensed under the GNU General Public License v3.0 or later
# (GPL-3.0-or-later) — see LICENSE.
#
# Adapted 2026-09-13 (ROADMAP.md Phase D) from project-ibris's own
# ibris_core.py to run headless inside a Docker container and report
# into Project Vigil's real automation loop, instead of opening a local
# GUI window (cv2.imshow) that has nowhere to display on a server. The
# actual motion-detection algorithm below (grayscale + Gaussian blur +
# frame-delta threshold + contour area filter) is unchanged from the
# original -- that logic doesn't need a display to work, only the
# visualization did.
#
# Honest status: this has not been verified against a real physical
# webcam as of this writing (none attached to the development machine).
# Written correctly against OpenCV's real, standard VideoCapture API --
# for a real tester with a real camera to confirm and report back
# against, same posture as vigil_kernel.py's hardware adapters.

import os
import time
import urllib.request
import urllib.error

import cv2
import numpy as np

# Where Vigil's own API lives -- same container network as everything
# else in Citadel, not the nginx-proxied /api/vigil/* path (this talks
# directly container-to-container, same pattern vault-api uses to reach
# Mealie).
VIGIL_URL = os.environ.get("VIGIL_URL", "http://citadel-vigil:8085")

# How many consecutive motion-free seconds before resetting the tripline
# back to SECURE -- avoids flapping ON/OFF on every single frame with no
# motion, which would fight with vigil_kernel.py's own automation loop
# (which also polls every 4s) and spam the state file with writes.
CLEAR_AFTER_SECONDS = float(os.environ.get("IBRIS_CLEAR_AFTER_SECONDS", "10"))

# cv2.VideoCapture's device index -- 0 is "first camera found", matching
# the original ibris_core.py. Override via env if a specific device
# ordering matters on a multi-camera setup.
CAMERA_INDEX = int(os.environ.get("IBRIS_CAMERA_INDEX", "0"))


def post_tripline_state(state):
    """POSTs {"perimeter_tripline": state} to Vigil's /api/update. Never
    raises -- a network hiccup here shouldn't crash the whole detection
    loop, just skip that one update (the next detection cycle will retry
    with the current, still-accurate state)."""
    body = f'{{"perimeter_tripline": "{state}"}}'.encode("utf-8")
    req = urllib.request.Request(
        f"{VIGIL_URL}/api/update", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3):
            pass
        return True
    except (urllib.error.URLError, OSError) as e:
        print(f"[IBRIS] Could not reach Vigil at {VIGIL_URL}: {e}")
        return False


def preprocess_frame(raw_frame):
    """Grayscale + blur -- the same first two steps ibris_core.py's
    original loop applied before comparing frames. Split out so
    test_ibris_motion.py can feed it synthetic frames directly."""
    gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (21, 21), 0)


def detect_motion(baseline_gray, current_gray, min_area=500):
    """Pure frame-comparison logic, unchanged from the original
    ibris_core.py's algorithm (frame delta -> threshold -> dilate ->
    contours -> area filter), just split out from the camera-read loop
    so it's testable against synthetic frames without a real webcam.
    Returns True if any contiguous change region is at least min_area
    pixels -- small enough to ignore sensor noise, large enough to
    ignore a moth (per the original's own contourArea(contour) < 500
    threshold)."""
    frame_delta = cv2.absdiff(baseline_gray, current_gray)
    threshold_frame = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
    threshold_frame = cv2.dilate(threshold_frame, None, iterations=2)
    contours, _ = cv2.findContours(threshold_frame.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return any(cv2.contourArea(c) >= min_area for c in contours)


def run_headless_motion_detector():
    print("=============================================================")
    print("PROJECT IBRIS: Headless Motion Detector (reports to Vigil)")
    print("=============================================================")
    print(f"[INIT] Opening camera index {CAMERA_INDEX}...")

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        print("[HARDWARE ERROR] Could not open a local camera at that index.")
        print("Check that a real webcam is passed through to this container")
        print("(see docker-compose.yml's 'camera' profile / devices: entry).")
        return

    print("[SUCCESS] Camera opened -- watching for motion.")
    baseline_frame = None
    last_motion_time = 0
    tripline_currently_tripped = False

    while True:
        success, raw_frame = camera.read()
        if not success:
            print("[SIGNAL DROP] Failed to read a frame -- retrying in 2s.")
            time.sleep(2)
            continue

        gray_frame = preprocess_frame(raw_frame)

        if baseline_frame is None:
            baseline_frame = gray_frame
            continue

        movement_detected = detect_motion(baseline_frame, gray_frame)

        # Slowly adapt the baseline so lighting drift doesn't permanently
        # trip the sensor -- the original script never reset this at all.
        baseline_frame = cv2.addWeighted(baseline_frame, 0.98, gray_frame, 0.02, 0)

        now = time.time()
        if movement_detected:
            last_motion_time = now
            if not tripline_currently_tripped:
                print("[ALERT] Motion detected -- reporting TRIPPED to Vigil.")
                if post_tripline_state("TRIPPED"):
                    tripline_currently_tripped = True
        elif tripline_currently_tripped and (now - last_motion_time) >= CLEAR_AFTER_SECONDS:
            print(f"[CLEAR] No motion for {CLEAR_AFTER_SECONDS}s -- reporting SECURE to Vigil.")
            if post_tripline_state("SECURE"):
                tripline_currently_tripped = False

        time.sleep(0.2)


if __name__ == "__main__":
    run_headless_motion_detector()
