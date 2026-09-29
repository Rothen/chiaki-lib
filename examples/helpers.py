"""What the 1.4.x streaming examples share, built directly on chiaki_lib: loading the
registration 1.3_register_console.py wrote, waking the console up, connecting, pulling
frames (and playing the audio), and forwarding a DualSense controller's input.

The controller is optional: it is used if dualsense-py is installed and one is plugged in.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Generator

from chiaki_lib import (
    AudioOutput,
    ChiakiPySession,
    ChiakiPySessionConnectInfo,
    DiscoveryHost,
    DiscoveryHostState,
    DiscoveryManager,
    QuitReason,
    Settings,
    Target,
    quit_reason_string,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("chiaki_lib").setLevel(logging.WARNING)

REGISTRATION_FILE = Path("./cache", "host_registration.json")


def load_registration() -> dict[str, Any]:
    """The registration 1.3_register_console.py wrote; exits if there is none yet."""
    if not REGISTRATION_FILE.exists():
        print(f"Registration not found under {REGISTRATION_FILE}. Run examples/1.3_register_console.py first")
        sys.exit(1)
    return json.loads(REGISTRATION_FILE.read_text(encoding="utf-8"))


def find_host(nickname: str, timeout: float = 5.0) -> DiscoveryHost | None:
    """Broadcast-discover consoles for `timeout` seconds and return the one called `nickname`."""
    manager = DiscoveryManager()
    manager.set_active(True)
    try:
        time.sleep(timeout)
        return next((h for h in manager.get_hosts() if h.host_name == nickname), None)
    finally:
        manager.set_active(False)


def wake_up(registration: dict[str, Any], max_tries: int = 3) -> bool:
    """Find the registered console on the network (updating its address if it changed) and wake it
    up if it is in standby. Returns whether it is ready to stream."""
    host = find_host(registration["nickname"])
    if host is None:
        return False
    registration["host"] = host.host_addr

    for _ in range(max_tries):
        if host is not None and host.state == DiscoveryHostState.Ready:
            return True
        DiscoveryManager().send_wakeup(host=registration["host"], regist_key=registration["regist_key"], ps5=registration["ps5"])
        host = find_host(registration["nickname"])
    return host is not None and host.state == DiscoveryHostState.Ready


def create_session(registration: dict[str, Any], settings: Settings) -> ChiakiPySession:
    connect_info = ChiakiPySessionConnectInfo(
        settings=settings,
        target=Target.__members__[registration["target"]],
        host=registration["host"],
        nickname=registration["nickname"],
        regist_key=registration["regist_key"],
        morning=registration["morning"],
        initial_login_pin=registration["initial_login_pin"],
        duid=registration["duid"],
        auto_regist=registration["auto_regist"],
        fullscreen=registration["fullscreen"],
        zoom=registration["zoom"],
        stretch=registration["stretch"],
    )
    return ChiakiPySession(connect_info)


def connect(session: ChiakiPySession) -> None:
    """Start the session and block until it is connected. Raises ConnectionError if the console
    refuses it or the connection fails."""
    connected = threading.Event()
    quit_reasons: list[QuitReason] = []
    subscriptions = [
        session.on_connected_changed().subscribe(lambda c: connected.set() if c else None),
        session.on_session_quit().subscribe(quit_reasons.append),
    ]
    try:
        session.start()
        while not connected.wait(timeout=0.2):
            if quit_reasons:
                raise ConnectionError(f"Session could not be established: {quit_reason_string(quit_reasons[0])}")
    finally:
        for subscription in subscriptions:
            subscription.unsubscribe()


@contextmanager
def stream_session(frame_handler_cls: type, hardware_decoder: str | None = None) -> Generator[tuple[ChiakiPySession, Any, str]]:
    """Wake up the registered console, connect to it and attach a DualSense controller, if there is one.
    Yields the session, its `frame_handler_cls` frame handler and the console's nickname; on leaving,
    releases the controller and disconnects. Exits if the connection can't be established.

    `hardware_decoder` ("cuda", "vulkan") is what the frame handler needs: CudaFrameHandler and
    VulkanFrameHandler only work with the matching decoder."""
    registration = load_registration()
    if not wake_up(registration):
        print(f"'{registration['nickname']}' not found on the network or did not wake up")

    settings = Settings()
    if hardware_decoder is not None:
        settings.set_hardware_decoder(hardware_decoder)
    session = create_session(registration, settings)
    frame_handler = frame_handler_cls(session)  # created before the session starts, like chiaki_py does
    session.on_session_quit().subscribe(lambda reason: print(f"session quit ({quit_reason_string(reason)})"))

    try:
        connect(session)
    except ConnectionError as e:
        print(e)
        sys.exit(1)
    print(f"connected to {registration['nickname']}")

    controller = None
    try:
        controller = attach_controller(session)
        yield session, frame_handler, registration["nickname"]
    finally:
        if controller is not None:
            detach_controller(session, *controller)
        if session.is_connected() or session.is_connecting():
            session.stop()


class FramePump:
    """Hands out the session's decoded frames as they arrive, and plays its audio once its first frame
    arrived (the rate and channel count are only known from then on). Use it as a context manager."""

    def __init__(self, session: ChiakiPySession, frame_handler: Any):
        self.session = session
        self.frame_handler = frame_handler
        self._frame_ready, self._audio_ready = threading.Event(), threading.Event()
        self._subscriptions = [
            session.on_frame_available().subscribe(lambda _: self._frame_ready.set()),
            session.on_audio_frame_available().subscribe(lambda _: self._audio_ready.set()),
        ]
        self._audio = AudioOutput(session)
        self._audio_open = False

    def __enter__(self) -> "FramePump":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def active(self) -> bool:
        """False once the session has ended."""
        return self.session.is_connected()

    def next_frame(self, timeout: float = 0.01) -> Any:
        """The next decoded frame, or None if none arrived within `timeout` seconds (or it couldn't be
        decoded). What a frame is depends on the frame handler."""
        if not self._audio_open and self._audio_ready.is_set():
            self._audio.open()
            self._audio_open = True
        if not self._frame_ready.wait(timeout):
            return None
        self._frame_ready.clear()
        try:
            return self.frame_handler.get_frame()
        except RuntimeError:
            return None  # an undecodable frame, the next one will do

    def close(self) -> None:
        for subscription in self._subscriptions:
            subscription.unsubscribe()
        self._subscriptions = []
        if self._audio_open:
            self._audio.close()
            self._audio_open = False


# DualSense button name in dualsense-py -> ChiakiPySession press_*/release_* suffix
BUTTONS = {
    "cross": "cross", "circle": "circle", "square": "square", "triangle": "triangle",
    "dpad_left": "left", "dpad_right": "right", "dpad_up": "up", "dpad_down": "down",
    "l1": "l1", "r1": "r1", "l3": "l3", "r3": "r3",
    "options": "options", "share": "create", "touch": "touchpad", "ps": "ps",
}


def set_orientation(session: ChiakiPySession, orientation) -> None:
    """Convert dualsense-py's yaw/pitch/roll (degrees) to the quaternion the console expects."""
    cy, sy = math.cos(math.radians(orientation.yaw) / 2), math.sin(math.radians(orientation.yaw) / 2)
    cp, sp = math.cos(math.radians(orientation.pitch) / 2), math.sin(math.radians(orientation.pitch) / 2)
    cr, sr = math.cos(math.radians(orientation.roll) / 2), math.sin(math.radians(orientation.roll) / 2)
    session.set_orientation(
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def attach_controller(session: ChiakiPySession) -> tuple[Any, list[Any]] | None:
    """Forward the first DualSense controller's input to the session. Returns the controller and its
    subscriptions, or None if dualsense-py isn't installed or no controller is plugged in."""
    try:
        from dualsense_py.backends import SDL3Backend
        from dualsense_py.utils import get_available_controllers
    except ImportError:
        print("dualsense-py not installed - streaming without input.")
        return None

    SDL3Backend.init()
    controllers = get_available_controllers()
    if not controllers:
        print("No DualSense controllers found - streaming without input.")
        return None

    controller = controllers[0]
    controller.open()
    subscriptions = []
    for button, action in BUTTONS.items():
        subscriptions.append(getattr(controller, f"{button}_pressed")(getattr(session, f"press_{action}")))
        subscriptions.append(getattr(controller, f"{button}_released")(getattr(session, f"release_{action}")))
    subscriptions += [
        controller.l2_trigger_changed(lambda v: session.set_l2(int(v * 255))),
        controller.r2_trigger_changed(lambda v: session.set_r2(int(v * 255))),
        controller.left_joy_stick_changed(lambda s: session.set_left(int(s.x * 1023), int(s.y * 1023))),
        controller.right_joy_stick_changed(lambda s: session.set_right(int(s.x * 1023), int(s.y * 1023))),
        controller.accelerometer_changed(lambda a: session.set_accelerometer(a.x, a.y, a.z)),
        controller.gyroscope_changed(lambda g: session.set_gyroscope(g.x, g.y, g.z)),
        controller.orientation_changed(lambda o: set_orientation(session, o)),
    ]
    return controller, subscriptions


def detach_controller(session: ChiakiPySession, controller: Any, subscriptions: list[Any]) -> None:
    """Stop forwarding input and release everything, so the console doesn't see anything held down."""
    for subscription in subscriptions:
        subscription.dispose()
    for action in BUTTONS.values():
        getattr(session, f"release_{action}")()
    session.set_left(0, 0)
    session.set_right(0, 0)
    session.send_feedback_state()
    controller.close()
