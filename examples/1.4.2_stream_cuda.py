"""GLFW remote-play viewer that renders on the GPU - the pixels never touch the CPU.

With the CudaFrameHandler every frame is converted to RGB on the GPU into a CuPy
array and drawn straight from GPU memory through CUDA-OpenGL interop (see
cuda_gl.py and glfw_video.py). Compare 1.4.1_stream_cpu.py, which decodes to
system memory.

Usage:
    python examples/1.4.2_stream_cuda.py

The registration is the one written by 1.3_register_console.py. Press F in the
window to show the frame rate, Q or Esc to quit. A DualSense controller is used
for input if dualsense-py is installed and one is plugged in.

Needs: an NVIDIA GPU that also renders the window, and
    pip install cupy-cuda12x cuda-python PyOpenGL glfw opencv-python (and optionally dualsense-py)
"""

import glfw

from chiaki_lib import CudaFrameHandler
from cuda_gl import CudaGLTexture
from fps_overlay import FpsCounter
from glfw_video import GLVideoSurface
from helpers import FramePump, stream_session


def main() -> None:
    with stream_session(CudaFrameHandler, hardware_decoder="cuda") as (session, frame_handler, nickname), \
            FramePump(session, frame_handler) as frames:
        profile = session.get_video_profile()
        with GLVideoSurface(profile.width, profile.height, f"chiaki_lib - {nickname}", show_fps=False) as surface:

            def on_key(window, key, scancode, action, mods) -> None:
                if key == glfw.KEY_F and action == glfw.PRESS:
                    surface.fps = None if surface.fps is not None else FpsCounter()
                    surface.texture.set_overlay(None)

            glfw.set_key_callback(surface.window, on_key)

            while frames.active and not surface.should_close:
                frame = frames.next_frame()  # a (H, W, 3) uint8 RGB CuPy array
                if frame is None:
                    glfw.poll_events()
                    continue
                height, width = frame.shape[:2]
                if (width, height) != (surface.texture.width, surface.texture.height):
                    surface.texture.close()  # the stream changed size (a PS4 may fall back from 1080p to 720p)
                    surface.texture = CudaGLTexture(width, height)
                surface.show(frame.transpose(2, 0, 1))  # the (3, H, W) view GLVideoSurface takes


if __name__ == "__main__":
    main()
