# Overrides vcpkg's stock x64-windows triplet (picked up through VCPKG_OVERLAY_TRIPLETS, set in the
# root CMakeLists.txt): everything stays a DLL except OpenSSL, which is linked statically.
#
# Why: a shared OpenSSL would ship as chiaki_lib/libcrypto-3-x64.dll. Windows loads a DLL only once
# per process for a given name, so once chiaki_lib is imported, Python's own _ssl module binds to
# that libcrypto instead of the one it was built with. Its libssl then runs against a different
# OpenSSL release, and ssl.create_default_context() fails with
# "[ASN1: NOT_ENOUGH_DATA] not enough data", which breaks requests, aiohttp and anything else that
# uses HTTPS after importing chiaki_lib. Linked statically, OpenSSL stays private to the DLLs that
# use it.
set(VCPKG_TARGET_ARCHITECTURE x64)
set(VCPKG_CRT_LINKAGE dynamic)
set(VCPKG_LIBRARY_LINKAGE dynamic)

if(PORT STREQUAL "openssl")
    set(VCPKG_LIBRARY_LINKAGE static)
endif()
