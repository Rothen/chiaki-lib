# chiaki-lib

Low-level [pybind11](https://github.com/pybind/pybind11) bindings around
[chiaki-ng](https://github.com/streetpea/chiaki-ng), the PS4/PS5 Remote Play client library:
discover consoles (`DiscoveryManager`), register with one (`Backend`), connect and stream one
(`ChiakiPySession`), pull its decoded frames (`CpuFrameHandler`, `CudaFrameHandler`,
`VulkanFrameHandler`), play its audio (`AudioOutput`) and draw it with Vulkan (`VulkanRenderer`).

Most users want [chiaki-py](https://github.com/Rothen/chiaki-py), the Pythonic client built on top
of this package, instead of using it directly.

```python
import chiaki_lib

manager = chiaki_lib.DiscoveryManager()
```

chiaki-ng's log messages go to the `chiaki_lib` logger, libplacebo's to `chiaki_lib.placebo` and
FFmpeg's to `chiaki_lib.ffmpeg`.

## Layout

| Path | What |
| --- | --- |
| `pybind/include`, `pybind/src` | The C++ wrapper around chiaki-ng |
| `pybind/bindings` | The pybind11 bindings; most `pydef_*.cpp` are generated, see below |
| `chiaki_lib/` | The Python package: the compiled `_native` module lands here, next to its stubs in `_native/` |
| `cmake/` | Builds libplacebo on Windows |

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

For development, `pip install -e .` after the CMake build makes `import chiaki_lib` use the module
built in place.

## Regenerating the bindings

After changing a bound header in `pybind/include`, regenerate the `pydef_*.cpp` files and the
stubs in `chiaki_lib/_native/__init__.pyi`, and commit the result:

```sh
pip install -e .[dev]
python pybind/bindings/generate_bindings.py   # or: cmake --build build --target chiaki-lib-generate-bindings
```

## License

AGPL-3.0-only, like chiaki-ng. See [LICENSE](LICENSE).
