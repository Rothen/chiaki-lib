# chiaki-lib

Low-level [pybind11](https://github.com/pybind/pybind11) bindings around
[chiaki-ng](https://github.com/streetpea/chiaki-ng), the PS4/PS5 Remote Play client library:
discover consoles (`DiscoveryManager`), register with one (`Backend`), connect and stream one
(`ChiakiPySession`), pull its decoded frames (`CpuFrameHandler`, `CudaFrameHandler`,
`VulkanFrameHandler`), play its audio (`AudioOutput`) and draw it with Vulkan (`VulkanRenderer`).

Most users want [chiaki-py](https://github.com/Rothen/chiaki-py), the Pythonic client built on top
of this package, instead of using it directly.

chiaki-ng's log messages go to the `chiaki_lib` logger, libplacebo's to `chiaki_lib.placebo` and
FFmpeg's to `chiaki_lib.ffmpeg`.

## Examples

`examples/` walks through a whole session using only `chiaki_lib`. Run the scripts from the
repository root, in order: each step saves what the next one needs under `./cache/`.

| Script | What it does |
| --- | --- |
| `1.1_login.py` | Signs in to your PSN account in the terminal (open the printed URL, paste back the one you land on) and saves it to `cache/psn_account.json` |
| `1.2_discover_hosts.py [--timeout SECONDS]` | Lists the PS4/PS5 consoles on the local network; needs no login |
| `1.3_register_console.py <host> <pin> [--ps4] [--console-pin PIN]` | Pairs with a console using the 8-digit code from its Link Device screen and saves `cache/host_registration.json` |
| `1.4.1_stream_cpu.py` | Streams the registered console into an OpenCV window, frames decoded to system memory (`CpuFrameHandler`) |
| `1.4.2_stream_cuda.py` | Streams into a GLFW window, frames converted and drawn on an NVIDIA GPU through CUDA-OpenGL interop (`CudaFrameHandler`) |
| `1.4.3_stream_vulkan.py` | Streams into a GLFW window, frames decoded and drawn on the GPU with Vulkan and never copied (`VulkanFrameHandler`, `VulkanRenderer`) |

```sh
python examples/1.1_login.py
python examples/1.2_discover_hosts.py
python examples/1.3_register_console.py 192.168.1.50 12345678
python examples/1.4.1_stream_cpu.py
```

The streaming examples wake the console up if it is in standby, play its audio, and forward a
DualSense controller's input if [dualsense-py](https://pypi.org/project/dualsense-py/) is
installed and one is plugged in. In the window, F shows the frame rate and Q or Esc quits.
`helpers.py`, `fps_overlay.py`, `glfw_video.py` and `cuda_gl.py` hold the code they share.

Besides `chiaki_lib`, the examples need:

| Script | Packages |
| --- | --- |
| `1.1_login.py` | `requests` |
| `1.4.1_stream_cpu.py` | `opencv-python` |
| `1.4.2_stream_cuda.py` | `cupy-cuda12x cuda-python PyOpenGL glfw opencv-python`, and an NVIDIA GPU that also drives the display |
| `1.4.3_stream_vulkan.py` | `glfw opencv-python`, and a GPU and driver with Vulkan video decoding |

## Layout

| Path | What |
| --- | --- |
| `pybind/include`, `pybind/src` | The C++ wrapper around chiaki-ng |
| `pybind/bindings` | The pybind11 bindings; most `pydef_*.cpp` are generated, see below |
| `chiaki_lib/` | The Python package: the compiled `_native` module lands here, next to its stubs in `_native/` |
| `cmake/` | Builds libplacebo on Windows |
| `examples/` | Login, discovery, pairing and streaming scripts, see [Examples](#examples) |

## Building

The extension module is built with CMake first; `python -m build` then only packages what CMake
put into `chiaki_lib/`. CMake fetches chiaki-ng (`CHIAKI_NG_VERSION`, into `libs/chiaki-ng`) and
pybind11 itself; on Windows it also downloads FFmpeg and builds libplacebo into `deps/`. The
native dependencies each platform needs are listed in the workflows under `.github/workflows/`.

Windows, from a Visual Studio x64 dev shell, with vcpkg and `pip install meson`:

```powershell
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_TOOLCHAIN_FILE="$env:VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" `
  -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl
cmake --build build --target chiaki-lib-py
python -m build --wheel
```

Linux / macOS:

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --target chiaki-lib-py
python -m build --wheel
```

For development, `pip install -e . --config-settings editable_mode=compat` after the CMake build
makes `import chiaki_lib` use the module built in place. `compat` puts this folder on `sys.path`
through a plain `.pth` entry, which Pylance/pyright can follow; the default editable mode uses an
import hook they can't see through.

## Regenerating the bindings

After changing a bound header in `pybind/include`, regenerate the `pydef_*.cpp` files and the
stubs in `chiaki_lib/_native/__init__.pyi`, and commit the result:

```sh
pip install -e .[dev] --config-settings editable_mode=compat
python pybind/bindings/generate_bindings.py   # or: cmake --build build --target chiaki-lib-generate-bindings
```

## License

AGPL-3.0-only, like chiaki-ng. See [LICENSE](LICENSE).
