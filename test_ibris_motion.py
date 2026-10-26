"""Real unit tests for ibris_motion.py -- covers what's testable without
a physical webcam: the actual motion-detection algorithm (against
synthetic frames, exercising the same OpenCV pipeline a real camera
frame would go through) and the Vigil-reporting HTTP behavior (mocked).
Does NOT verify a real camera actually opens/streams -- no such hardware
exists to test against as of this writing (see ibris_motion.py's own
top-of-file note).
"""
import unittest
from unittest.mock import patch, MagicMock

import numpy as np

import ibris_motion as im


def make_frame(width=320, height=240, box=None):
    """A plain BGR frame (all zeros/black) with an optional white
    rectangle drawn at `box = (x, y, w, h)` -- simulates a real camera
    frame well enough to exercise cvtColor/GaussianBlur/absdiff/threshold/
    contours exactly as a real frame would."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    if box:
        import cv2
        x, y, w, h = box
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), -1)
    return frame


class DetectMotionTests(unittest.TestCase):
    def test_identical_frames_have_no_motion(self):
        baseline = im.preprocess_frame(make_frame())
        current = im.preprocess_frame(make_frame())
        self.assertFalse(im.detect_motion(baseline, current))

    def test_large_change_is_detected_as_motion(self):
        baseline = im.preprocess_frame(make_frame())
        # A 60x60 white square is well over the 500px-area floor even
        # after the Gaussian blur softens its edges.
        current = im.preprocess_frame(make_frame(box=(100, 80, 60, 60)))
        self.assertTrue(im.detect_motion(baseline, current))

    def test_tiny_change_is_ignored_as_noise(self):
        baseline = im.preprocess_frame(make_frame())
        # A 3x3 speck -- far below the real ibris_core.py's own 500px
        # contourArea floor (a moth/sensor-noise-sized artifact).
        current = im.preprocess_frame(make_frame(box=(100, 80, 3, 3)))
        self.assertFalse(im.detect_motion(baseline, current))

    def test_custom_min_area_threshold_is_respected(self):
        baseline = im.preprocess_frame(make_frame())
        # A 10x10 box measures ~444px contour area after blur+dilate
        # (verified empirically, not guessed) -- below the default 500
        # floor, but well above a lower explicit threshold.
        current = im.preprocess_frame(make_frame(box=(100, 80, 10, 10)))
        self.assertFalse(im.detect_motion(baseline, current, min_area=500))
        self.assertTrue(im.detect_motion(baseline, current, min_area=100))


class PostTriplineStateTests(unittest.TestCase):
    @patch("ibris_motion.urllib.request.urlopen")
    def test_posts_correct_url_and_json_body(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = MagicMock()
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        ok = im.post_tripline_state("TRIPPED")
        self.assertTrue(ok)
        request_obj = mock_urlopen.call_args[0][0]
        self.assertEqual(request_obj.full_url, f"{im.VIGIL_URL}/api/update")
        self.assertEqual(request_obj.data, b'{"perimeter_tripline": "TRIPPED"}')
        self.assertEqual(request_obj.get_header("Content-type"), "application/json")

    @patch("ibris_motion.urllib.request.urlopen", side_effect=OSError("network down"))
    def test_network_failure_is_honest_not_a_crash(self, mock_urlopen):
        ok = im.post_tripline_state("SECURE")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
