#!/usr/bin/env python3
"""Fail if olddefconfig silently drops requested NetHunter features."""
import argparse
import re
import sys
from pathlib import Path

YES = re.compile(r"^(CONFIG_[A-Z0-9_]+)=(.+)$")
NO = re.compile(r"^# (CONFIG_[A-Z0-9_]+) is not set$")


def parse(path):
    result = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        hit = YES.fullmatch(line)
        if hit:
            key, value = hit.groups()
        else:
            hit = NO.fullmatch(line)
            if not hit:
                continue
            key, value = hit.group(1), "n"
        if key in result and result[key] != value:
            raise ValueError(f"{path}: conflict for {key}")
        result[key] = value
    return result


def verify(config, fragments, board=True):
    actual = parse(config)
    expected = {}
    for fragment in fragments:
        expected.update(parse(fragment))
    if board:
        expected.update({
            "CONFIG_USB_GADGET": "y",
            "CONFIG_USB_CONFIGFS": "y",
            "CONFIG_USB_CONFIGFS_F_HID": "y",
            "CONFIG_QCA_CLD_WLAN": "m",
            "CONFIG_MODULE_SIG_FORCE": "y",
        })
    return [
        f"{key}: expected {value}, got {actual.get(key, '<missing>')}"
        for key, value in sorted(expected.items())
        if actual.get(key) != value
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--fragment", action="append", type=Path, default=[])
    args = parser.parse_args()
    try:
        errors = verify(args.config, args.fragment)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    print("Config audit passed" if not errors else "Config audit FAILED")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
