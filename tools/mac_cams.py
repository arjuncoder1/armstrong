"""macOS cameras for dreamcli's "your own class" camera option (OpenCV over AVFoundation, by index).

In the dreamcli setup wizard, camera source "class", value:
    /Users/arjun/Desktop/hackathons/makermodshack/tools/mac_cams.py:Overhead     # index 1
    /Users/arjun/Desktop/hackathons/makermodshack/tools/mac_cams.py:LeftWrist    # index 0
    /Users/arjun/Desktop/hackathons/makermodshack/tools/mac_cams.py:RightWrist   # index 2
Indices can move after a replug or reboot; change INDEX below (or use Cam0..Cam3) if a view is wrong.
"""

import cv2


class _MacCam:
    INDEX = 0

    def __init__(self, camera=None):
        self.cap = cv2.VideoCapture(self.INDEX, cv2.CAP_AVFOUNDATION)
        if camera is not None:  # honour the wizard's requested size and rate when the camera allows it
            for prop, attr in ((cv2.CAP_PROP_FRAME_WIDTH, "width"), (cv2.CAP_PROP_FRAME_HEIGHT, "height"),
                               (cv2.CAP_PROP_FPS, "fps")):
                value = getattr(camera, attr, None)
                if value:
                    self.cap.set(prop, value)

    def read(self):
        return self.cap.read()  # (ok, BGR frame)

    def release(self):
        self.cap.release()

    def isOpened(self):  # noqa: N802 - cv2.VideoCapture shape
        return self.cap.isOpened()


class Overhead(_MacCam):
    INDEX = 1


class LeftWrist(_MacCam):
    INDEX = 0


class RightWrist(_MacCam):
    INDEX = 2


class Cam0(_MacCam):
    INDEX = 0


class Cam1(_MacCam):
    INDEX = 1


class Cam2(_MacCam):
    INDEX = 2


class Cam3(_MacCam):
    INDEX = 3
