#!/bin/bash
# Build Valve's Proton, or GE-Proton, for arm64 CPUs without LSE atomics (ARMv8.0), with DXVK-Sarek and
# umu-protonfixes built in.
#
#   build.sh <tag> <workdir>    a Valve tag (proton-11.0-2e, experimental-11.0-<date>) or GE's (GE-Proton11-11)
#
# Produces <workdir>/proton-armv8-<tag>.tar.zst with .sha256 and .sha512 next to it.
# Needs git, make, patch, zstd, python3, llvm-objdump and a container engine (CONTAINER_ENGINE, default docker).
set -euo pipefail

TAG=${1:?usage: build.sh <tag> <workdir>}
WORK=${2:?usage: build.sh <tag> <workdir>}
HERE=$(cd "$(dirname "$0")/.." && pwd)
NAME=proton-armv8-$TAG
case "$TAG" in
GE-Proton*)  # GE-Proton has umu-protonfixes already: not patch 0003
    REPO=https://github.com/GloriousEggroll/proton-ge-custom.git
    PATCHES=("$HERE"/patches/0001-armv8.0.patch "$HERE"/patches/0002-dxvk-sarek.patch)
    CCACHE=  # its configure.sh always uses ccache, and has no --enable-ccache
    DISPLAY="$TAG (ARMv8.0)" ;;
*)
    REPO=https://github.com/ValveSoftware/Proton.git
    PATCHES=("$HERE"/patches/*.patch)
    CCACHE=--enable-ccache
    DISPLAY="Proton ${TAG#*-} (ARMv8.0)" ;;
esac

patch_protonfixes() {  # patches/protonfixes on the umu-protonfixes in $1, then their test
    for p in "$HERE"/patches/protonfixes/*.patch; do
        patch -d "$1" -Np1 --no-backup-if-mismatch -i "$p"
    done
    python3 -B "$HERE/scripts/test-protonfixes-arm64.py" "$1"
}

mkdir -p "$WORK"
cd "$WORK"

if [ ! -d proton ]; then
    git clone --branch "$TAG" --filter=tree:0 "$REPO" proton
    git -C proton submodule update --init --recursive --filter=tree:0 --jobs 8
fi
# -C0: the changed lines must match, their surroundings may move between tags.
git -C proton -c user.name=proton-armv8 -c user.email=proton-armv8@users.noreply.github.com \
    am -C0 "${PATCHES[@]}"
case "$TAG" in
GE-Proton*)
    # As GE's own CI: its patches into the submodules (it exits non-zero when it skips one), and its
    # strip-at-compile-time patch, for the runner's disk.
    (cd proton && ./patches/protonprep-valve-staging.sh) || true
    patch -d proton -Np1 -i .github/patches/0001-build-strip-binaries-early.patch
    patch_protonfixes proton/protonfixes ;;
esac

read -r SAREK_URL SAREK_REV < "$HERE/sarek.pin"
git clone --filter=tree:0 "$SAREK_URL" proton/extras/dxvk-sarek
git -C proton/extras/dxvk-sarek checkout --quiet "$SAREK_REV"
git -C proton/extras/dxvk-sarek submodule update --init --recursive --filter=tree:0

if [[ $TAG != GE-Proton* ]]; then
    read -r PROTONFIXES_URL PROTONFIXES_REV < "$HERE/protonfixes.pin"
    git clone --filter=tree:0 "$PROTONFIXES_URL" proton/extras/protonfixes
    git -C proton/extras/protonfixes checkout --quiet "$PROTONFIXES_REV"
    git -C proton/extras/protonfixes submodule update --init --recursive --filter=tree:0
    patch_protonfixes proton/extras/protonfixes
fi

mkdir -p build
cd build
../proton/configure.sh --build-name="$NAME" --target-arch=arm64 \
    --container-engine="${CONTAINER_ENGINE:-docker}" ${CCACHE:+"$CCACHE"}
make redist
sed -i "s|\"display_name\" \"$NAME\"|\"display_name\" \"$DISPLAY\"|" redist/compatibilitytool.vdf

python3 "$HERE/scripts/scan-lse.py" --objdump "${OBJDUMP:-llvm-objdump}" --allow "$HERE/scan-allow.txt" redist/files \
    redist/protonfixes

cd "$WORK"
tar -C build/redist --transform "s|^\./|$NAME/|" -cf - . | zstd -19 -T0 -o "$NAME.tar.zst"
sha256sum "$NAME.tar.zst" > "$NAME.tar.zst.sha256"
sha512sum "$NAME.tar.zst" > "$NAME.tar.zst.sha512"
echo "built $WORK/$NAME.tar.zst"
