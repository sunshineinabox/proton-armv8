#!/bin/bash
# Build Valve's Proton for arm64 CPUs without LSE atomics (ARMv8.0), with DXVK-Sarek built in.
#
#   build.sh <valve-tag> <workdir>
#
# Produces <workdir>/proton-armv8-<valve-tag>.tar.zst with .sha256 and .sha512 next to it.
# Needs git, make, zstd, python3, llvm-objdump and a container engine (CONTAINER_ENGINE, default docker).
set -euo pipefail

TAG=${1:?usage: build.sh <valve-tag> <workdir>}
WORK=${2:?usage: build.sh <valve-tag> <workdir>}
HERE=$(cd "$(dirname "$0")/.." && pwd)
NAME=proton-armv8-$TAG
DISPLAY="Proton ${TAG#*-} (ARMv8.0)"

mkdir -p "$WORK"
cd "$WORK"

if [ ! -d proton ]; then
    git clone --branch "$TAG" --filter=tree:0 https://github.com/ValveSoftware/Proton.git proton
    git -C proton submodule update --init --recursive --filter=tree:0 --jobs 8
fi
# -C0: the changed lines must match, their surroundings may move between Valve tags.
git -C proton -c user.name=proton-armv8 -c user.email=proton-armv8@users.noreply.github.com \
    am -C0 "$HERE"/patches/*.patch

read -r SAREK_URL SAREK_REV < "$HERE/sarek.pin"
git clone --filter=tree:0 "$SAREK_URL" proton/extras/dxvk-sarek
git -C proton/extras/dxvk-sarek checkout --quiet "$SAREK_REV"
git -C proton/extras/dxvk-sarek submodule update --init --recursive --filter=tree:0

mkdir -p build
cd build
../proton/configure.sh --build-name="$NAME" --target-arch=arm64 \
    --container-engine="${CONTAINER_ENGINE:-docker}" --enable-ccache
make redist
sed -i "s|\"display_name\" \"$NAME\"|\"display_name\" \"$DISPLAY\"|" redist/compatibilitytool.vdf

python3 "$HERE/scripts/scan-lse.py" --objdump "${OBJDUMP:-llvm-objdump}" redist/files

cd "$WORK"
tar -C build/redist --transform "s|^\./|$NAME/|" -cf - . | zstd -19 -T0 -o "$NAME.tar.zst"
sha256sum "$NAME.tar.zst" > "$NAME.tar.zst.sha256"
sha512sum "$NAME.tar.zst" > "$NAME.tar.zst.sha512"
echo "built $WORK/$NAME.tar.zst"
