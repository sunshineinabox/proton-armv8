#!/usr/bin/env python3
"""Check patches/protonfixes/0001-arm64-winetricks.patch in a patched umu-protonfixes checkout, with a fake
winetricks and wineserver: skipped verbs, PROTONFIXES_ARM64_VERBS, no retry after a failure, the timeout,
and the EasyAntiCheat/BattlEye runtimes. Linux only (protonfixes reads /proc).

usage: test-protonfixes-arm64.py PROTONFIXES_DIR
"""
import os, shutil, sys, tempfile, time

SRC = os.path.abspath(sys.argv[1])
T = tempfile.mkdtemp()
os.symlink(SRC, os.path.join(T, "protonfixes"))
BIN = os.path.join(T, "bin")
os.makedirs(BIN)
CALLS = os.path.join(T, "calls")
FAKE = """#!/bin/sh
echo "$(basename "$0") $*" >> {calls}
[ "$(basename "$0")" = winetricks ] || exit 0
case "$*" in
  *hang*) sleep 60 ;;
  *bad*) exit 1 ;;
esac
for v in "$@"; do [ "$v" = --unattended ] || echo "$v" >> "$WINEPREFIX/winetricks.log"; done
"""
for name in ("winetricks", "wineserver", "wine"):
    with open(os.path.join(BIN, name), "w") as f:
        f.write(FAKE.format(calls=CALLS))
    os.chmod(os.path.join(BIN, name), 0o755)
os.environ.update(PATH=BIN + ":" + os.environ["PATH"], STEAM_COMPAT_DATA_PATH=os.path.join(T, "compat"),
                  PROTONFIXES_DISABLE="1")  # no early stage at import
os.makedirs(os.path.join(T, "compat", "pfx"))
sys.argv = [os.path.join(T, "proton"), "waitforexitandrun", "game.exe"]
sys.path.insert(0, T)


class Session:  # what protonfixes reads from proton's __main__
    env = dict(os.environ)


class Proton:
    wine_bin, wineserver_bin = os.path.join(BIN, "wine"), os.path.join(BIN, "wineserver")


g_session, g_proton = Session(), Proton()

from protonfixes import util  # noqa: E402

util.ARM64 = True  # as on the device, whatever runs this
util.check_internet = lambda: True
installs = []
util.install_app = installs.append
FAILED = os.path.join(T, "compat", "pfx", util.ARM64_FAILED)
PASS = FAIL = 0


def ok(cond, what):
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(("  ok   " if cond else "  FAIL ") + what)


def tricks(verb, **env):
    """(protontricks' result, the fake winetricks' and wineserver's calls, seconds)"""
    if os.path.exists(CALLS):
        os.remove(CALLS)
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    start = time.time()
    try:
        result = util.protontricks(verb)
    finally:
        for k, v in old.items():
            os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
    calls = open(CALLS).read().splitlines() if os.path.exists(CALLS) else []
    return result, [c for c in calls if not c.endswith(" -w")], time.time() - start


r, calls, _ = tricks("dotnet48")
ok(r is False and calls == [], "a verb FEX cannot install is skipped")
r, calls, _ = tricks("dotnet48 vcrun2019")
ok(r is True and calls == ["winetricks --unattended vcrun2019"], "the rest of the call still runs")
r, calls, _ = tricks("dotnet35sp1", PROTONFIXES_ARM64_VERBS="xna40,dotnet35sp1")
ok(r is True and calls == ["winetricks --unattended dotnet35sp1"], "PROTONFIXES_ARM64_VERBS runs one anyway")
r, calls, _ = tricks("webview2", PROTONFIXES_ARM64_VERBS="all")
ok(r is True and calls == ["winetricks --unattended webview2"], "and =all runs them all")
r, calls, _ = tricks("corefonts")
ok(r is True and calls == ["winetricks --unattended corefonts"], "any other verb runs as before")

r, calls, _ = tricks("badverb")
ok(r is False and calls and open(FAILED).read().startswith("badverb "), "a verb that fails is recorded")
r, calls, _ = tricks("badverb")
ok(r is False and calls == [], "and not tried again the next launch")
with open(FAILED, "w") as f:
    f.write(f"badverb {int(time.time()) - 8 * 86400}\n")
r, calls, _ = tricks("badverb")
ok(calls == ["winetricks --unattended badverb"], "a week later it is tried again")

r, calls, took = tricks("hangverb", PROTONFIXES_WINETRICKS_TIMEOUT="2")
ok(r is False and took < 20 and calls[-1].endswith("wineserver -k") and "hangverb " in open(FAILED).read(),
   f"a winetricks that hangs is stopped at the timeout, its wine processes killed ({took:.0f} s)")
os.environ["PROTONFIXES_WINETRICKS_TIMEOUT"] = "soon"
ok(util._winetricks_timeout() == 900, "a timeout that is not a number is the default")

util.install_eac_runtime()
util.install_battleye_runtime()
ok(installs == [], "the x86-64-only EasyAntiCheat and BattlEye runtimes are not installed")

shutil.rmtree(T, ignore_errors=True)
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
