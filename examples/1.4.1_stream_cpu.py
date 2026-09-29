"""OpenCV remote-play viewer built directly on chiaki_lib. Frames are decoded to
system memory; see 1.4.2_stream_cuda.py and 1.4.3_stream_vulkan.py for GPU versions.

Usage:
    python examples/1.4.1_stream_cpu.py

The registration is the one written by 1.3_register_console.py. Press F in the
window to show the frame rate, Q or Esc to quit. A DualSense controller is used
for input if dualsense-py is installed and one is plugged in.

Needs: pip install opencv-python (and optionally dualsense-py)
"""

import cv2

from chiaki_lib import CpuFrameHandler
from fps_overlay import FpsCounter, draw_text_top_right
from helpers import FramePump, stream_session


def main() -> None:
    with stream_session(CpuFrameHandler) as (session, frame_handler, nickname), FramePump(session, frame_handler) as frames:
        title = f"chiaki_lib - {nickname}"
        fps_counter = FpsCounter()
        show_fps = False

        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        try:
            while frames.active:
                frame = frames.next_frame()  # a (H, W, 3) uint8 RGB numpy array
                if frame is not None:
                    fps = fps_counter.tick()
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    if show_fps and fps is not None:
                        draw_text_top_right(frame, f"FPS: {fps:.2f}")
                    cv2.imshow(title, frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("f"):
                    show_fps = not show_fps
                if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                    break  # the window was closed
        finally:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
