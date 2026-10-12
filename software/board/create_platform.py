# Vitis 2024.1 (Python CLI): create + build a standalone platform (BSP) for the ARM program from an XSA, in a NEW workspace folder.
# Run with the Vitis interpreter, not .venv:
#   vitis -s software/board/create_platform.py <design_1_wrapper.xsa> <new_workspace_dir>
# Result: <ws>/m6_platform/export/m6_platform/sw/standalone_ps7_cortexa9_0  ->  use it as SR_BSP for build_elf.sh.
# Never point it at the existing Vitis workspace (~/Desktop/venkat/vitis_workspace): it refuses an existing folder.
import os
import sys

import vitis

if len(sys.argv) != 3:
    sys.exit("usage: vitis -s create_platform.py <xsa> <new_workspace_dir>")
xsa, ws = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
if not os.path.isfile(xsa):
    sys.exit(f"XSA not found: {xsa}")
if os.path.exists(ws):
    sys.exit(f"{ws} already exists: choose a new folder")
os.makedirs(ws)
client = vitis.create_client()
client.set_workspace(path=ws)
platform = client.create_platform_component(name="m6_platform", hw_design=xsa, os="standalone", cpu="ps7_cortexa9_0",
                                            domain_name="standalone_ps7_cortexa9_0")
platform.build()
bsp = os.path.join(ws, "m6_platform", "export", "m6_platform", "sw", "standalone_ps7_cortexa9_0")
ok = os.path.isfile(os.path.join(bsp, "include", "xparameters.h"))
print(("PLATFORM_OK " if ok else "PLATFORM_FAIL no xparameters.h in ") + bsp)
vitis.dispose()
sys.exit(0 if ok else 1)
