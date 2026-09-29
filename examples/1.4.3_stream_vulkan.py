"""GLFW remote-play viewer that renders with Vulkan - the pixels are never copied.

The Vulkan hardware decoder decodes on the GPU and, with the VulkanFrameHandler, the
frames stay right where it put them: chiaki_lib's VulkanRenderer draws them into the
window on that same Vulkan device with libplacebo, which converts the NV12 frames to
RGB. Unlike 1.4.2_stream_cuda.py there is no CUDA or OpenGL involved, so it is not
tied to NVIDIA. Compare 1.4.1_stream_cpu.py, which decodes to system memory.

Usage:
    python examples/1.4.3_stream_vulkan.py

The registration is the one written by 1.3_register_console.py. Press F in the
window to show the frame rate (drawn over the video by libplacebo), Q or Esc to quit.
A DualSense controller is used for input if dualsense-py is installed and one is
plugged in.

Needs: a GPU and driver with Vulkan video decoding (H.264 for a PS4, H.264 or HEVC
for a PS5), Windows or Linux (X11 or Wayland), and
    pip install glfw opencv-python (and optionally dualsense-py)
"""

import sys

import glfw
import numpy as np

from chiaki_lib import ChiakiPySession, VulkanFrameHandler, VulkanRenderer, VulkanWindowSystem
from fps_overlay import FpsCounter, rasterize_text
from helpers import FramePump, stream_session


def create_renderer(session: ChiakiPySession, window) -> VulkanRenderer:
    """A VulkanRenderer drawing into the GLFW window, whichever window system it is on."""
    if sys.platform == "win32":
        return VulkanRenderer(session, glfw.get_win32_window(window), 0, VulkanWindowSystem.Win32)
    if glfw.get_platform() == glfw.PLATFORM_WAYLAND:
        renderer = VulkanRenderer(session, glfw.get_wayland_window(window), glfw.get_wayland_display(),
                                  VulkanWindowSystem.Wayland)
        renderer.set_size(*glfw.get_framebuffer_size(window))  # a Wayland surface has no size of its own
        glfw.set_framebuffer_size_callback(window, lambda _, w, h: renderer.set_size(w, h))
        return renderer
    return VulkanRenderer(session, glfw.get_x11_window(window), glfw.get_x11_display(), VulkanWindowSystem.X11)


def premultiplied(rgba: np.ndarray) -> np.ndarray:
    """`rgba` with its colour multiplied by its alpha, as VulkanRenderer.set_overlay() wants it."""
    out = rgba.copy()
    out[..., :3] = (rgba[..., :3].astype(np.uint16) * rgba[..., 3:4] // 255).astype(np.uint8)
    return out


def main() -> None:
    with stream_session(VulkanFrameHandler, hardware_decoder="vulkan") as (session, frame_handler, nickname), \
            FramePump(session, frame_handler) as frames:
        if not glfw.init():
            raise RuntimeError("Failed to initialise GLFW")
        glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)  # Vulkan draws into it, not OpenGL
        profile = session.get_video_profile()
        window = glfw.create_window(profile.width, profile.height, f"chiaki_lib - {nickname}", None, None)
        if not window:
            glfw.terminate()
            raise RuntimeError("Failed to create the window")

        renderer = create_renderer(session, window)
        fps_counter: FpsCounter | None = None
        fps_text = None

        def on_key(_, key, scancode, action, mods) -> None:
            nonlocal fps_counter, fps_text
            if action != glfw.PRESS:
                return
            if key in (glfw.KEY_Q, glfw.KEY_ESCAPE):
                glfw.set_window_should_close(window, True)
            elif key == glfw.KEY_F:
                fps_counter = None if fps_counter is not None else FpsCounter()
                fps_text = None
                renderer.clear_overlay()

        glfw.set_key_callback(window, on_key)

        try:
            while frames.active and not glfw.window_should_close(window):
                glfw.poll_events()
                frame = frames.next_frame()  # a VulkanFrame, still on the GPU
                if frame is None:
                    continue
                try:
                    renderer.render(frame)  # waits for vsync
                except (ValueError, RuntimeError) as e:
                    print(f"Dropping unusable frame: {e}")
                    continue
                if fps_counter is not None and (fps := fps_counter.tick()) is not None:
                    text = f"FPS: {fps:.2f}"
                    if text != fps_text:
                        fps_text = text
                        renderer.set_overlay(premultiplied(rasterize_text(text)))
        finally:
            renderer.close()  # before the window it draws into goes away
            glfw.destroy_window(window)
            glfw.terminate()


if __name__ == "__main__":
    main()
