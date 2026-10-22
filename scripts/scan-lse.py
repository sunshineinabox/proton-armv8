#!/usr/bin/env python3
"""Find ARMv8.1+ LSE and ARMv8.3 RCpc instructions in arm64 ELF and PE binaries.

A site is "helper" when it sits in an outline-atomics helper (a __aarch64_* function, or a stripped
one whose code tests w16 just before, as the helpers do) and so is chosen at run time; anything else
is "inline" and faults on ARMv8.0. Exit 1 if any inline site is found.

usage: scan-lse.py [--objdump PATH] FILE_OR_DIR...
"""
import os, re, subprocess, sys

LSE = re.compile(r"\s(cas[a-z]*|casp[a-z]*|swp[a-z]*|ld(add|clr|eor|set|smax|smin|umax|umin)[a-z]*|"
                 r"st(add|clr|eor|set|smax|smin|umax|umin)[a-z]*|ldapr[a-z]*|ldapur[a-z]*)\s")
FUNC = re.compile(r"^[0-9a-f]+ <([^>]+)>:")
INSN = re.compile(r"^\s*([0-9a-f]+):\s+(.*)$")
HELPER = re.compile(r"^__aarch64_(cas|casp|swp|ldadd|ldclr|ldeor|ldset)")


def is_arm64(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    if head[:4] == b"\x7fELF":
        return head[18:20] == b"\xb7\x00"                      # e_machine EM_AARCH64
    if head[:2] == b"MZ" and len(head) > 0x40:
        pe = int.from_bytes(head[0x3c:0x40], "little")
        if pe + 6 <= len(head) and head[pe:pe + 4] == b"PE\0\0":
            return int.from_bytes(head[pe + 4:pe + 6], "little") in (0xaa64, 0xa641, 0xa64e)  # ARM64, ARM64EC, ARM64X
    return False


def scan(path, objdump):
    out = subprocess.run([objdump, "-d", "--no-show-raw-insn", path], capture_output=True, text=True).stdout
    func, recent, helper, inline = "", [], 0, []
    for line in out.splitlines():
        m = FUNC.match(line)
        if m:
            func, recent = m.group(1), []
            continue
        m = INSN.match(line)
        if not m:
            continue
        addr, insn = m.groups()
        hit = LSE.search(" " + insn + " ")
        if hit:
            dispatched = any(re.search(r"\bcbz\s+w16\b|\bldrb\s+w16,", r) for r in recent[-6:])
            if HELPER.match(func) or dispatched:
                helper += 1
            else:
                inline.append((addr, hit.group(1), func))
        recent.append(insn)
    return helper, inline


def main(argv):
    objdump = "llvm-objdump"
    if argv[:1] == ["--objdump"]:
        objdump, argv = argv[1], argv[2:]
    files = []
    for arg in argv:
        if os.path.isdir(arg):
            for root, _, names in os.walk(arg):
                files += [os.path.join(root, n) for n in sorted(names)]
        else:
            files.append(arg)
    bad = 0
    for path in files:
        if os.path.islink(path) or not is_arm64(path):
            continue
        helper, inline = scan(path, objdump)
        if helper or inline:
            print(f"{path}  total {helper + len(inline)}  helper {helper}  inline {len(inline)}")
            for off, mnem, func in inline[:5]:
                print(f"    {off} {mnem} {func}")
        bad += len(inline)
    print(f"inline LSE/RCpc sites: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
