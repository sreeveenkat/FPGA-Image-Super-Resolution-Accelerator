"""Check that the read-only part of a program in DDR (dumped physically by run_board.tcl, SR_VERIFY_DUMP) equals the ELF.

    python3 software/board/verify_load.py <elf> <dump.bin>        exit 0 = intact, 1 = corrupted, 2 = usage / tool error
    python3 software/board/verify_load.py --bytes <elf>           prints the number of bytes to dump (0x00100000 .. start of .bss)
Compared sections: everything the program never writes (.text, .init, .fini, .rodata, .mmu_tbl, .ARM.exidx, .init_array, .fini_array, .drvcfg_sec).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path.home() / "Desktop/vivado_install/Vitis/2024.1/gnu/aarch32/lin/gcc-arm-none-eabi/bin"
BASE = 0x00100000
RO = [".text", ".init", ".fini", ".rodata", ".mmu_tbl", ".ARM.exidx", ".init_array", ".fini_array", ".drvcfg_sec"]


def sections(elf):
    out = subprocess.run([str(TOOLS / "arm-none-eabi-objdump"), "-h", elf], capture_output=True, text=True, check=True).stdout
    res = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 4 and f[0].isdigit():
            res[f[1]] = (int(f[3], 16), int(f[2], 16))      # name -> (vma, size)
    return res


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--bytes":
        print(sections(sys.argv[2])[".bss"][0] - BASE)
        return 0
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    elf, dump = sys.argv[1], Path(sys.argv[2]).read_bytes()
    sec = sections(elf)
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        for name in RO:
            if name not in sec or sec[name][1] == 0:
                continue
            vma, size = sec[name]
            fn = Path(td) / "s.bin"
            subprocess.run([str(TOOLS / "arm-none-eabi-objcopy"), "-O", "binary", "-j", name, elf, str(fn)], check=True)
            want = fn.read_bytes()[:size]
            got = dump[vma - BASE: vma - BASE + size]
            if got != want:
                diff = [i for i in range(min(len(got), len(want))) if got[i] != want[i]]
                first = diff[0] if diff else min(len(got), len(want))
                print(f"CORRUPTED {name}: {len(diff)} of {size} bytes differ, first at 0x{vma + first:08x}")
                bad += 1
    print("program image in DDR: " + ("INTACT (read-only sections equal the ELF)" if not bad else f"CORRUPTED in {bad} section(s)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
