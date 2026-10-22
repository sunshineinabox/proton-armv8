#!/usr/bin/env python3
"""Find ARMv8.1+ LSE and ARMv8.3 RCpc instructions in arm64 ELF and PE binaries.

A site is "helper" when it sits in an outline-atomics helper (a __aarch64_* function, or a stripped
one whose code tests w16 just before, as the helpers do) and so is chosen at run time; anything else
is "inline" and faults on ARMv8.0. Exit 1 if any inline site is found.

usage: scan-lse.py [--objdump PATH] [--allow FILE] FILE_OR_DIR...

--allow names files whose inline sites are accepted, one `<glob> <reason>` per line, the glob relative to
the directory scanned (# starts a comment). They are reported but do not fail the scan.
"""
import fnmatch, os, re, subprocess, sys

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


def read_allow(path):
    rules = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if line:
            glob, _, reason = line.partition(" ")
            rules.append((glob, reason.strip()))
    return rules


def main(argv):
    objdump, allow = "llvm-objdump", []
    while argv[:1] in (["--objdump"], ["--allow"]):
        if argv[0] == "--objdump":
            objdump = argv[1]
        else:
            allow = read_allow(argv[1])
        argv = argv[2:]
    files = []
    for arg in argv:
        if os.path.isdir(arg):
            for root, _, names in os.walk(arg):
                files += [(os.path.join(root, n), os.path.relpath(os.path.join(root, n), arg)) for n in sorted(names)]
        else:
            files.append((arg, os.path.basename(arg)))
    bad = 0
    for path, rel in files:
        if os.path.islink(path) or not is_arm64(path):
            continue
        helper, inline = scan(path, objdump)
        if not (helper or inline):
            continue
        reason = next((r for g, r in allow if fnmatch.fnmatchcase(rel, g)), None)
        note = f"  allowed: {reason}" if inline and reason is not None else ""
        print(f"{path}  total {helper + len(inline)}  helper {helper}  inline {len(inline)}{note}")
        for off, mnem, func in inline[:5]:
            print(f"    {off} {mnem} {func}")
        if reason is None:
            bad += len(inline)
    print(f"inline LSE/RCpc sites: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
