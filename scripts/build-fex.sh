#!/bin/bash
# Build Valve's FEX tool commit (fex.pin) for arm64 CPUs without LSE atomics (ARMv8.0), as a Steam tool.
#
#   build-fex.sh <workdir>
#
# Produces <workdir>/fex-armv8-<describe>.tar.zst with .sha256 and .sha512 next to it: the tool's folder
# as Valve ships it, from FEX's own install with Steam support (usr/bin/FEX and its helpers, FEXCompatTool,
# toolmanifest.vdf, emulator.json, ConfigTemplate.json, VERSIONS.txt), plus a compatibilitytool.vdf and
# FEX's LICENSE. The manifest runs Valve's fex-compat-tool (with its unshare.py), which is not FEX's and
# is not in it: the device copies those two from Steam's FEX tool.
# Everything runs in a Debian 13 arm64 container with clang 19, as Valve's tool is built. Needs a host
# that runs arm64 containers and a container engine (CONTAINER_ENGINE, default docker).
set -euo pipefail

WORK=${1:?usage: build-fex.sh <workdir>}
HERE=$(cd "$(dirname "$0")/.." && pwd)
COMMIT=$(sed -n 's/^commit: *//p' "$HERE/fex.pin")
DESCRIBE=$(sed -n 's/^describe: *//p' "$HERE/fex.pin")
NAME=fex-armv8-$DESCRIBE

mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd)
"${CONTAINER_ENGINE:-docker}" run --rm --platform linux/arm64 -v "$WORK":/w -v "$HERE":/repo:ro \
    -e COMMIT="$COMMIT" -e DESCRIBE="$DESCRIBE" -e NAME="$NAME" -e OWNER="$(id -u):$(id -g)" \
    debian:trixie bash -euo pipefail -c '
apt-get -qq update
apt-get -qq install -y --no-install-recommends git ca-certificates cmake ninja-build clang-19 lld-19 llvm-19 \
    python3 python3-setuptools pkg-config zstd >/dev/null
git config --global --add safe.directory "*"
cd /w
[ -d FEX ] || git clone -q https://github.com/FEX-Emu/FEX.git
git -C FEX fetch -q --tags origin
git -C FEX checkout -q "$COMMIT"
git -C FEX submodule update -q --init --recursive
rm -rf build stage
# TUNE_CPU defaults to native (-mcpu=native tunes for the build machine): none, with -march=armv8-a.
cmake -S FEX -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_C_COMPILER=clang-19 -DCMAKE_CXX_COMPILER=clang++-19 -DUSE_LINKER=lld-19 \
    -DENABLE_LTO=TRUE -DBUILD_TESTING=FALSE -DBUILD_FEXCONFIG=FALSE -DBUILD_THUNKS=FALSE \
    -DENABLE_ASSERTIONS=FALSE -DENABLE_CCACHE=FALSE -DBUILD_STEAM_SUPPORT=TRUE \
    -DTUNE_CPU=none -DTUNE_ARCH=armv8-a >/dev/null
ninja -C build | tail -1
DESTDIR=/w/stage ninja -C build install >/dev/null
grep -qxF "FEX describe	$DESCRIBE" stage/VERSIONS.txt || { echo "stage/VERSIONS.txt is not $DESCRIBE:"; cat stage/VERSIONS.txt; exit 1; }
mkdir -p stage/rootfs stage/EmptySteamDepot  # as in Valve'\''s tool
cp FEX/LICENSE stage/LICENSE
printf "\"compatibilitytools\"\n{\n  \"compat_tools\"\n  {\n    \"%s\"\n    {\n      \"install_path\" \".\"\n      \"display_name\" \"FEX ARMv8.0\"\n      \"from_oslist\" \"linux\"\n      \"to_oslist\" \"linux\"\n    }\n  }\n}\n" "$NAME" > stage/compatibilitytool.vdf
python3 /repo/scripts/scan-lse.py --objdump llvm-objdump-19 --allow /repo/scan-allow-fex.txt stage
tar -C stage --transform "s|^\./|$NAME/|" -cf - . | zstd -q -19 -T0 -o "$NAME.tar.zst" -f
sha256sum "$NAME.tar.zst" > "$NAME.tar.zst.sha256"
sha512sum "$NAME.tar.zst" > "$NAME.tar.zst.sha512"
chown -R "$OWNER" /w
'
echo "built $WORK/$NAME.tar.zst"
