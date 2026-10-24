# proton-armv8

Valve's [Proton](https://github.com/ValveSoftware/Proton) for arm64 CPUs **without LSE atomics** (ARMv8.0:
Cortex-A53/A57/A72/A73, e.g. Snapdragon 662 / SM6115, Tegra X1), with
[DXVK-Sarek](https://github.com/pythonlover02/DXVK-Sarek) and
[umu-protonfixes](https://github.com/Open-Wine-Components/umu-protonfixes) built in.

Valve builds Proton ARM64 with `-march=armv8.2-a`, so on these CPUs its Wine, DXVK and FEX components fault
on the first atomic instruction, or run only through slow kernel emulation. These builds use `-march=armv8-a`.

## Releases

CI builds each new Valve and GE-Proton tag on GitHub's arm64 runners:

| Channel | Tags | Release tag |
|---|---|---|
| stable | Valve's `proton-11.0-*` (no betas) | `armv8-proton-11.0-<n>` |
| experimental | Valve's `experimental-11.0-*` | `armv8-experimental-11.0-<date>` (pre-release) |
| ge | [GE-Proton](https://github.com/GloriousEggroll/proton-ge-custom)'s `GE-Proton<n>-<m>` | `armv8-GE-Proton<n>-<m>` (never marked latest) |

GE publishes aarch64 builds of its own, with Valve's `-march=armv8.2-a`. Ours take its tree as GE's CI
builds it (`protonprep-valve-staging.sh`, its strip patch) with patches 0001 and 0002; GE has
umu-protonfixes already, with the Wine patches some of its fixes expect (wine-staging's
`HideWineExports`, the upscaler DLL overrides).

A release is published only when every native arm64 binary passes `scripts/scan-lse.py`: no LSE/RCpc
instruction outside the compiler's runtime-checked outline-atomics helpers. The exceptions are in
`scan-allow.txt`: today only Xalia's prebuilt arm64 `xalia.exe` (experimental), which runs only for apps
Proton enables Xalia for.

## Install

```sh
mkdir -p ~/.steam/root/compatibilitytools.d
tar -C ~/.steam/root/compatibilitytools.d --zstd -xf proton-armv8-<tag>.tar.zst
```

Restart Steam and pick "Proton … (ARMv8.0)" or "GE-Proton… (ARMv8.0)" per game or as the default. `PROTON_DXVK_SAREK=1 %command%` in a
game's launch options selects DXVK-Sarek.

## protonfixes

Before each game, Proton runs umu-protonfixes' fixes for it, as GE-Proton does: a Steam game's by its app id, a
GOG or Epic game's by `UMU_ID` and `STORE` (`gog`, `egs`), which umu-run or a launcher sets from the
[umu-database](https://github.com/Open-Wine-Components/umu-database). `PROTONFIXES_DISABLE=1 %command%` turns
them off for a game.

They were written for x86 GE-Proton: their `winetricks` verbs install x86 redistributables, which run
through FEX here. Both builds patch protonfixes for that (`patches/protonfixes`):

- verbs whose installers do not run through FEX (.NET, XNA, `mdx`, `ie8`, `powershell`, `webview2`,
  `ubisoftconnect`) are skipped, and the rest of the fix still runs; `PROTONFIXES_ARM64_VERBS=<verb>,...`
  (or `=all`) runs them anyway;
- a verb that fails is not tried again in that prefix for a week (`pfx/winetricks.log.arm64-failed`);
- winetricks is stopped after `PROTONFIXES_WINETRICKS_TIMEOUT` seconds (900), so a hung installer cannot
  hold a launch;
- the x86-64-only EasyAntiCheat and BattlEye runtimes are not installed.

The Valve builds do not have GE's upscaler upgrades (`PROTON_DLSS_UPGRADE` and the like), which need GE's
Wine patch.

## FEX

Native x86 Linux games run on arm64 Steam through Valve's FEX tool (app 3127680, `steamapps/common/FEX-Emu`),
which is built for ARMv8.1+ as well: its binaries have ~390 inline LSE sites. `fex.pin` names the FEX commit
Valve's tool is built from, and the FEX workflow builds that commit for ARMv8.0 with Steam support
(`scripts/build-fex.sh`, the same compiler as Valve's) as release `fex-armv8-<describe>`. Valve's tool is
owners-only on Steam, so the pin is bumped by hand.

The tarball is the tool's folder without Valve's own `fex-compat-tool` and `unshare.py`, which its manifest
runs: copy those two from `FEX-Emu` into it. Then either put it in `compatibilitytools.d` and pick "FEX
ARMv8.0" per game, or, while Valve's `VERSIONS.txt` names the same version, copy its `usr/bin/*` and
`FEXCompatTool` over Valve's. On the Air X (SM6115) at SuperTux's menu, Valve's FEX caused ~3,000 kernel LSE
emulations a second, this build none.

## Contents

- `patches/0001-armv8.0.patch`: `-march=armv8-a` for the arm64 Wine sides, and `TUNE_CPU=generic` for FEX.
- `patches/0002-dxvk-sarek.patch`: DXVK-Sarek's build rules and its `PROTON_DXVK_SAREK` switch, ported from
  [Proton-CachyOS](https://github.com/CachyOS/proton-cachyos).
- `sarek.pin`: the DXVK-Sarek commit built.
- `patches/0003-protonfixes.patch`: umu-protonfixes' build rules and GE-Proton's protonfixes hook in `proton`,
  ported from [GE-Proton](https://github.com/GloriousEggroll/proton-ge-custom). Its cabextract, unzip and pgrep
  build with the same flags; the scan covers them and the prebuilt zenity it downloads.
- `protonfixes.pin`: the umu-protonfixes commit built, bumped by hand.
- `patches/protonfixes/`: our patches on protonfixes, in both builds (the ARM64 winetricks handling above);
  `scripts/test-protonfixes-arm64.py <dir>` checks them, and the build runs it before compiling.
- `scripts/build.sh <tag> <workdir>`: the build of a Valve or GE-Proton tag (Proton's containerized
  `make redist`, then the scan).
- `fex.pin`, `scripts/build-fex.sh <workdir>`, `scan-allow-fex.txt`: the FEX build, in a Debian 13 arm64
  container, and its one scan exception (`FEXGetConfig`'s hand-written fault-granularity probe).

## Credits

The ARMv8.0 approach follows [Azkali/proton-arm64-a57](https://github.com/Azkali/proton-arm64-a57). DXVK-Sarek
integration is from Proton-CachyOS, protonfixes integration from GE-Proton. Proton is © Valve and its component
authors, under their own licenses; umu-protonfixes is © its authors, BSD-2-Clause.
FEX is © the FEX-Emu authors, MIT (its LICENSE is in each FEX tarball).
