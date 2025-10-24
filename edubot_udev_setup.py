#!/usr/bin/env python3
"""
edubot_udev_setup_interactive.py

Interactive udev rule helper for beginners (Ubuntu 24.04, ROS 2 Jazzy baseline).
- Self-escalates to sudo when needed to write /etc/udev/rules.d/99-edubot.rules.
- Supports serial USB devices (/dev/ttyUSB*, /dev/ttyACM*) and USB cameras (/dev/video*).
- Creates stable symlinks, optionally under /dev/edubot/<name> or a custom subdirectory.
- Uses safe permissions by default: MODE=0660, GROUP=dialout (serial) or GROUP=video (cameras), TAG+="uaccess".
- Lets users add multiple devices in one run.
- Offers two identification modes:
    1) Show current candidates and let the user pick.
    2) Guided plug-in: unplug everything, then plug devices one-by-one; script auto-detects each new node.

Notes:
- udev rules are appended to /etc/udev/rules.d/99-edubot.rules.
- After finishing, it prints copy-paste lines to reload and trigger rules.

Author: Edubot
"""

import os
import sys
import re
import glob
import time
import subprocess
from typing import Optional, Tuple, List, Dict

RULES_FILE = "/etc/udev/rules.d/99-edubot.rules"

# -------------------------------
# Shell helpers
# -------------------------------


def run_command(args: List[str]) -> str:
    """Run a command and return stdout text."""
    proc = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.stdout


def try_run_command(args: List[str]) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def require_root_via_sudo():
    """
    If not root, re-exec this script using sudo -E to request elevation.
    Keeps UX simple for first-time Linux users.
    """
    if os.geteuid() == 0:
        return
    script_path = os.path.abspath(sys.argv[0])
    print("\nThis tool needs administrator privileges to write udev rules; a sudo prompt will appear.\n")
    os.execlp("sudo", "sudo", "-E", sys.executable, script_path)


# -------------------------------
# udev attribute discovery
# -------------------------------


def discover_usb_parent_block(attribute_walk_text: str) -> Optional[str]:
    """
    From `udevadm info --attribute-walk --name <dev>`, find the first parent block with SUBSYSTEMS=="usb".
    """
    # Split by "looking at ..." headings
    blocks = re.split(r"\n(?=looking at )", attribute_walk_text, flags=re.IGNORECASE)
    for blk in blocks:
        if re.search(r'SUBSYSTEMS==\s*"usb"', blk, flags=re.IGNORECASE):
            return blk
    return None


def extract_attr(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1) if m else None


def get_device_usb_identifiers(devnode: str) -> Dict[str, Optional[str]]:
    """
    Extract USB identifiers (idVendor, idProduct, serial if present) for a device node.
    Prefers ATTRS{...} from the USB parent; falls back to ID_* properties where helpful.
    """
    # Attribute walk shows device + parent attributes suitable for udev matching
    walk = run_command(["udevadm", "info", "--attribute-walk", "--name", devnode])

    usb_blk = discover_usb_parent_block(walk) or ""
    id_vendor = extract_attr(r'ATTRS\{\s*idVendor\s*\}==\s*"([0-9a-fA-F]{4})"', usb_blk)
    id_product = extract_attr(r'ATTRS\{\s*idProduct\s*\}==\s*"([0-9a-fA-F]{4})"', usb_blk)
    serial = extract_attr(r'ATTRS\{\s*serial\s*\}==\s*"([^"]+)"', usb_blk)

    # Property view as a fallback reference
    props = run_command(["udevadm", "info", "--query=property", "--name", devnode])
    if not id_vendor:
        id_vendor = extract_attr(r"^ID_VENDOR_ID=(\w+)$", props)
    if not id_product:
        id_product = extract_attr(r"^ID_MODEL_ID=(\w+)$", props)
    if not serial:
        serial = extract_attr(r"^ID_SERIAL_SHORT=(.+)$", props)

    return {
        "idVendor": id_vendor.lower() if id_vendor else None,
        "idProduct": id_product.lower() if id_product else None,
        "serial": serial,
    }


# -------------------------------
# Rule generation
# -------------------------------


def normalize_symlink_target(dir_choice: str, name: str) -> str:
    """
    Build the SYMLINK target string:
    - "edubot" -> "edubot/<name>"
    - "custom:<dir>" -> "<dir>/<name>" (strip a leading '/dev/' if provided)
    - "none" -> "<name>"
    """
    name = name.strip()
    if dir_choice == "edubot":
        return f"edubot/{name}"
    if dir_choice.startswith("custom:"):
        raw = dir_choice.split(":", 1)[1].strip()
        # Accept "/dev/foo" or "foo"; convert to relative under /dev
        if raw.startswith("/dev/"):
            raw = raw[len("/dev/") :]
        raw = raw.strip("/ ")
        if raw:
            return f"{raw}/{name}"
        return name
    return name


def build_serial_rule(id_vendor: str, id_product: str, serial: Optional[str], link_target: str, perms: str) -> str:
    """
    Build udev rule for serial devices (/dev/ttyUSB*, /dev/ttyACM*).
    perms: "safe" -> MODE=0660, GROUP=dialout, TAG+="uaccess"
           "world" -> MODE=0666
    """
    parts = [
        'ACTION=="add"',
        'SUBSYSTEM=="tty"',
        f'ATTRS{{idVendor}}=="{id_vendor}"',
        f'ATTRS{{idProduct}}=="{id_product}"',
    ]
    if serial:
        parts.append(f'ATTRS{{serial}}=="{serial}"')
    assigns = [f'SYMLINK+="{link_target}"']
    if perms == "safe":
        assigns += ['MODE="0660"', 'GROUP="dialout"', 'TAG+="uaccess"']
    else:
        assigns += ['MODE="0666"']
    return ", ".join(parts + assigns)


def build_camera_rule(id_vendor: str, id_product: str, serial: Optional[str], link_target: str, perms: str) -> str:
    """
    Build udev rule for V4L2 cameras (/dev/video*).
    perms: "safe" -> MODE=0660, GROUP=video, TAG+="uaccess"
           "world" -> MODE=0666
    """
    parts = [
        'ACTION=="add"',
        'SUBSYSTEM=="video4linux"',
        'KERNEL=="video[0-9]*"',
        f'ATTRS{{idVendor}}=="{id_vendor}"',
        f'ATTRS{{idProduct}}=="{id_product}"',
    ]
    if serial:
        parts.append(f'ATTRS{{serial}}=="{serial}"')
    assigns = [f'SYMLINK+="{link_target}"']
    if perms == "safe":
        assigns += ['MODE="0660"', 'GROUP="video"', 'TAG+="uaccess"']
    else:
        assigns += ['MODE="0666"']
    return ", ".join(parts + assigns)


def append_rule(rule_line: str) -> None:
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "a", encoding="utf-8") as f:
        f.write(rule_line + "\n")
    print(f"[ok] Appended rule to {RULES_FILE}")


# -------------------------------
# Device discovery UX
# -------------------------------


def list_candidates() -> List[str]:
    """
    Return sorted list of likely device nodes to choose from.
    """
    paths = set()
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/video*"):
        for p in glob.glob(pattern):
            if os.path.exists(p):
                paths.add(p)
    return sorted(paths)


def snapshot_candidate_set() -> set:
    """
    Snapshot set of candidate device nodes for diffing.
    """
    return set(list_candidates())


def diff_new_nodes(before: set, after: set) -> List[str]:
    new_paths = sorted(list(after - before))
    return new_paths


def choose_symlink_dir() -> str:
    print("\nWhere should the symlink live?")
    print("  1) edubot dir (/dev/edubot/<name>; RECOMMENDED)")
    print("  2) custom dir (/dev/<dir>/<name>)")
    print("  3) no dir     (/dev/<name>)")
    while True:
        choice = input("Select 1/2/3: ").strip()
        if choice == "1":
            return "edubot"
        if choice == "2":
            d = input("Enter directory under /dev (e.g., edubot/cameras): ").strip()
            return f"custom:{d}"
        if choice == "3":
            return "none"
        print("Please enter 1, 2, or 3.")


def choose_perms_style() -> str:
    print("\nPermissions style:")
    print("  1) Safe           (MODE=0660 + TAG+=uaccess; RECOMMENDED)")
    print("  2) World-writable (MODE=0666; workaround but less secure)")
    while True:
        choice = input("Select 1/2: ").strip()
        if choice == "1":
            return "safe"
        if choice == "2":
            return "world"
        print("Please enter 1 or 2.")


def identify_device_interactively() -> Optional[str]:
    print("\nDevice identification:")
    print("  1) List of current serial/camera nodes and pick one")
    print("  2) Guided plug-in (RECOMMENDED for first-time users)")
    print("  3) Type the full path manually (/dev/ttyUSB0)")
    while True:
        choice = input("Select 1/2/3: ").strip()
        if choice == "1":
            candidates = list_candidates()
            if not candidates:
                print("No candidate devices found.")
                return None
            for idx, p in enumerate(candidates, 1):
                print(f"  {idx}) {p}")
            while True:
                sel = input(f"Pick 1-{len(candidates)}: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(candidates):
                    return candidates[int(sel) - 1]
                print("Invalid selection.")
        elif choice == "2":
            input("Unplug the robot/devices now, then press Enter...")
            base = snapshot_candidate_set()
            input("Plug in ONE device now, wait 2-3 seconds, then press Enter...")
            time.sleep(2.0)
            after = snapshot_candidate_set()
            new_nodes = diff_new_nodes(base, after)
            if not new_nodes:
                print("No new device nodes detected.")
                return None
            # If multiple nodes appeared (e.g., some cameras), let user pick
            print("Detected new device nodes:")
            for idx, p in enumerate(new_nodes, 1):
                print(f"  {idx}) {p}")
            while True:
                sel = input(f"Pick 1-{len(new_nodes)}: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(new_nodes):
                    return new_nodes[int(sel) - 1]
                print("Invalid selection.")
        elif choice == "3":
            p = input("Enter device path (e.g., /dev/ttyUSB0 or /dev/video0): ").strip()
            if os.path.exists(p):
                return p
            print("That path does not exist.")
        else:
            print("Please enter 1, 2, or 3.")


def classify_device(devnode: str) -> str:
    """
    Return 'serial' or 'camera' based on path.
    """
    if os.path.basename(devnode).startswith(("ttyUSB", "ttyACM")):
        return "serial"
    if os.path.basename(devnode).startswith("video"):
        return "camera"
    # Fallback heuristic: treat tty* as serial
    if "/tty" in devnode:
        return "serial"
    return "camera"


# -------------------------------
# Main workflow
# -------------------------------


def add_one_device():
    devnode = identify_device_interactively()
    if not devnode:
        print("Skipping; could not identify a device.")
        return

    dev_type = classify_device(devnode)
    print(f"\nSelected device: {devnode} [{dev_type}]")

    # Ask for link name and placement
    link_name = ""
    while not link_name:
        link_name = input("Enter desired symlink name (e.g., prizm, imu, camera, lidar): ").strip()
    link_dir_choice = choose_symlink_dir()
    link_target = normalize_symlink_target(link_dir_choice, link_name)

    perms = choose_perms_style()

    # Read identifiers
    print("\nReading USB identifiers (idVendor, idProduct, serial if present)...")
    ids = get_device_usb_identifiers(devnode)
    if not ids.get("idVendor") or not ids.get("idProduct"):
        print("Could not determine idVendor/idProduct; is this a USB-backed device?")
        return

    # Build rule per class
    if dev_type == "serial":
        rule_line = build_serial_rule(ids["idVendor"], ids["idProduct"], ids.get("serial"), link_target, perms)
    else:
        rule_line = build_camera_rule(ids["idVendor"], ids["idProduct"], ids.get("serial"), link_target, perms)

    # Show preview and append
    print("\n[preview] udev rule:")
    print(rule_line)
    append_rule(rule_line)


def main():
    # Elevate early so the flow is uniform for beginners
    require_root_via_sudo()

    print("Edubot udev setup — create /dev symlinks for serial devices and USB cameras.\n")
    print("You can add multiple devices (one by one).\n")

    while True:
        add_one_device()
        again = input("\nAdd another device? (y/n): ").strip().lower()
        if again not in ("y", "yes"):
            break

    # Exit instructions: clearly copy-pasteable
    print("\n=== Copy-paste these to apply rules now ===")
    print("sudo udevadm control --reload")
    print("sudo udevadm trigger")
    print("==========================================\n")
    print(f"Rules file: {RULES_FILE}")
    print("If a symlink doesn’t appear immediately, try replugging the device.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
