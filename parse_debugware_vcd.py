#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse debugware VCD and split the debug_data bus into fields.

The script can handle any debug_data width as long as a matching layout file
is provided with --layout. If --layout is omitted, it falls back to the
built-in 420-bit layout for backward compatibility.

Usage:
    python parse_debugware_vcd.py debugware_420_0.vcd \
        --layout debug_data_layout.txt \
        --addr 0x0684 --context 5

    python parse_debugware_vcd.py debugware_640_0.vcd \
        --layout debug_data_layout_640.txt \
        --addr 0x19a5 --context 3
"""

import sys
import re
import argparse
from collections import OrderedDict

# Default field definition for the legacy 420-bit debug_data bus.
# Order is from MSB (bit 419) down to LSB (bit 0).
DEFAULT_FIELDS = [
    ("reserved",        13),
    ("data_fwd_word_addr", 30),
    ("data_fwd_data",   32),
    ("data_fwd_hit_current", 1),
    ("data_fwd_valid",  1),
    ("data_r_b",        32),
    ("data_we_b",        4),
    ("data_addr_a",     10),
    ("data_r_a",        32),
    ("data_w_b",        32),
    ("data_addr_b",     10),
    ("state",            4),
    ("accept_cpu_req",   1),
    ("cpu_access_valid", 1),
    ("hit",              1),
    ("wb_addr_cnt",      3),
    ("refill_cnt",       3),
    ("miss_write_reg",   1),
    ("cpu_haddr",       32),
    ("cpu_hwdata",      32),
    ("cpu_hrdata",      32),
    ("cpu_hwrite",       1),
    ("cpu_hsize",        2),
    ("cpu_hsel",         1),
    ("cpu_htrans",       2),
    ("cpu_hready_in",    1),
    ("cpu_hready_out",   1),
    ("mem_haddr",       32),
    ("mem_hwdata",      32),
    ("mem_hrdata",      32),
    ("mem_hwrite",       1),
    ("mem_hsize",        2),
    ("mem_htrans",       2),
    ("mem_hburst",       3),
    ("mem_hready",       1),
]


def build_field_map(fields=None):
    """Return OrderedDict field->(msb, lsb) within the word."""
    if fields is None:
        fields = DEFAULT_FIELDS
    total = sum(w for _, w in fields)
    field_map = OrderedDict()
    pos = total - 1
    for name, width in fields:
        field_map[name] = (pos, pos - width + 1)
        pos -= width
    return total, field_map


TOTAL_BITS, FIELD_MAP = build_field_map()


def load_layout(path):
    """
    Load a debug_data layout from a file containing the Verilog assignment block.
    The file may look like:

        assign debug_data = {
            data_fwd_word_addr[29:0], data_fwd_data[31:0], ...
        };

    or just the body between '{' and '}'.
    Returns a list of (name, width) from MSB to LSB.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Strip /* */ and // comments.
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    raw = re.sub(r"//.*", "", raw)

    if "{" not in raw or "}" not in raw:
        raise ValueError(f"Layout file {path} must contain a '{{ ... }}' block")

    body = raw[raw.find("{") + 1: raw.rfind("}")]

    # Split on commas not inside nested braces.
    items = []
    depth = 0
    current = []
    for ch in body:
        if ch == "{":
            depth += 1
            current.append(ch)
        elif ch == "}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        items.append("".join(current))
    items = [p.strip() for p in items if p.strip()]

    fields = []
    reserved_idx = 0
    for item in items:
        # Numeric constant: 13'b0
        const_match = re.match(r"^(\d+)'[bBdDhHoO][0-9a-fA-FxXzZ?]+$", item)
        if const_match:
            reserved_idx += 1
            fields.append((f"reserved_{reserved_idx}", int(const_match.group(1))))
            continue

        # Signal slice: name[msb:lsb]
        slice_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\s*:\s*(\d+)\]$", item)
        if slice_match:
            name = slice_match.group(1)
            msb = int(slice_match.group(2))
            lsb = int(slice_match.group(3))
            fields.append((name, msb - lsb + 1))
            continue

        # Single-bit signal
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", item):
            fields.append((item, 1))
            continue

        raise ValueError(f"Cannot infer width for layout item: {item!r}")

    return fields


def parse_args():
    p = argparse.ArgumentParser(description="Parse debugware VCD")
    p.add_argument("vcd", help="Path to VCD file")
    p.add_argument("--signal", "-s", default="data_in_0",
                   help="Hierarchical name or leaf name of the debug bus (default: data_in_0)")
    p.add_argument("--layout", "-l", type=str, default=None,
                   help="File containing the Verilog 'assign debug_data = {...}' block")
    p.add_argument("--start", "-t0", type=str, default=None,
                   help="Start time (e.g. 1000ns or 1000)")
    p.add_argument("--end", "-t1", type=str, default=None,
                   help="End time")
    p.add_argument("--addr", "-a", type=str, default=None,
                   help="Only dump cycles where cpu_haddr equals this value")
    p.add_argument("--fields", "-f", type=str, default=None,
                   help="Comma-separated list of fields to print (default: all)")
    p.add_argument("--csv", action="store_true",
                   help="Output CSV format")
    p.add_argument("--output", "-o", type=str, default=None,
                   help="Output file path (default: print to stdout)")
    p.add_argument("--context", "-c", type=int, default=None,
                   help="With --addr, also output N rows before/after each match")
    return p.parse_args()


def parse_time(s):
    if s is None:
        return None
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(s|ms|us|ns|ps|fs)?\s*$", s)
    if not m:
        return float(s)
    val, unit = m.groups()
    scale = {"s": 1e0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9,
             "ps": 1e-12, "fs": 1e-15}.get(unit, 1e-9)
    return float(val) * scale


def read_vcd_timescale(vcd_path):
    """Return timescale in seconds, e.g. 1e-9 for 1ns."""
    with open(vcd_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("$timescale"):
                # Could be on same line: $timescale 1ps $end
                m = re.search(r"([0-9]+)\s*(s|ms|us|ns|ps|fs)", line)
                if not m:
                    # Or multi-line
                    for inner in f:
                        inner = inner.strip()
                        m = re.search(r"([0-9]+)\s*(s|ms|us|ns|ps|fs)", inner)
                        if m:
                            break
                        if inner.startswith("$end"):
                            break
                if m:
                    val, unit = m.groups()
                    scale = {"s": 1e0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9,
                             "ps": 1e-12, "fs": 1e-15}.get(unit, 1e-9)
                    return float(val) * scale
            if line.startswith("$enddefinitions"):
                break
    return 1e-9


def _base_name(name):
    """Strip Verilog bit-slice suffix: data_in_0[419:0] -> data_in_0."""
    m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\[", name)
    if m:
        return m.group(1)
    return name


def _target_width(target_name):
    """If target contains a slice like data[419:0], return its width."""
    m = re.search(r"\[(\d+)\s*:\s*(\d+)\]", target_name)
    if m:
        return int(m.group(1)) - int(m.group(2)) + 1
    return None


def find_signal_id(vcd_path, target_name):
    """Scan VCD header and return (identifier, size, hierarchical name)."""
    scope_stack = []
    target_leaf = target_name.split(".")[-1]
    target_base = _base_name(target_leaf)
    target_width = _target_width(target_leaf)
    candidates = []
    in_def = False
    with open(vcd_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    scope_stack.append(parts[2])
                in_def = True
            elif line.startswith("$upscope"):
                if scope_stack:
                    scope_stack.pop()
            elif line.startswith("$var"):
                parts = line.split()
                # $var wire <size> <id> <name> ... $end
                if len(parts) >= 5:
                    size = int(parts[2])
                    sid = parts[3]
                    name = parts[4]
                    name_base = _base_name(name)
                    width_ok = (target_width is None and size == TOTAL_BITS) or \
                               (target_width is not None and size == target_width)
                    if name_base == target_base and width_ok:
                        hpath = ".".join(scope_stack + [name])
                        candidates.append((sid, size, hpath))
            elif line.startswith("$enddefinitions"):
                break
    if not candidates:
        return None, None, None
    # Prefer exact hierarchical match if provided
    if "." in target_name:
        for sid, size, hpath in candidates:
            if hpath == target_name or hpath.endswith("." + target_name):
                return sid, size, hpath
    return candidates[0]


def split_value(value_bin, fields=None):
    """Given a 420-bit binary string (MSB first), return field values."""
    if len(value_bin) != TOTAL_BITS:
        return None
    out = OrderedDict()
    for name, (msb, lsb) in FIELD_MAP.items():
        if fields and name not in fields:
            continue
        msb_idx = TOTAL_BITS - 1 - msb
        lsb_idx = TOTAL_BITS - 1 - lsb
        bits = value_bin[msb_idx:lsb_idx + 1]
        out[name] = bits
    return out


def format_field(name, bits):
    if name in ("cpu_haddr", "cpu_hwdata", "cpu_hrdata",
                "mem_haddr", "mem_hwdata", "mem_hrdata",
                "data_fwd_data", "data_r_a", "data_r_b", "data_w_b"):
        return f"0x{int(bits, 2):08x}"
    width = len(bits)
    if width <= 4:
        return f"0b{bits} ({int(bits, 2)})"
    return f"0x{int(bits, 2):x}"


def format_row(csv_fmt, current_time, field_list, vals):
    if csv_fmt:
        return ",".join([f"{current_time:.0f}"] + [format_field(n, vals[n]) for n in field_list])
    return " ".join([f"{current_time:>14.0f}"] + [f"{format_field(n, vals[n]):>14}" for n in field_list])


def main():
    args = parse_args()

    global TOTAL_BITS, FIELD_MAP
    if args.layout:
        field_defs = load_layout(args.layout)
    else:
        field_defs = DEFAULT_FIELDS
    TOTAL_BITS, FIELD_MAP = build_field_map(field_defs)

    t_start = parse_time(args.start)
    t_end = parse_time(args.end)
    addr_filter = None
    if args.addr:
        addr_filter = int(args.addr, 0)
    selected_fields = None
    if args.fields:
        selected_fields = set(f.strip() for f in args.fields.split(","))

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    timescale = read_vcd_timescale(args.vcd)

    sid, size, hpath = find_signal_id(args.vcd, args.signal)
    if sid is None:
        print(f"Error: could not find {TOTAL_BITS}-bit signal '{args.signal}' in {args.vcd}", file=out)
        print("Available candidates (run with --signal leaf_name):", file=out)
        # Fallback: list all signals matching the requested name regardless of width
        with open(args.vcd, "r", encoding="utf-8", errors="ignore") as f:
            scope_stack = []
            for line in f:
                line = line.strip()
                if line.startswith("$scope"):
                    scope_stack.append(line.split()[2])
                elif line.startswith("$upscope"):
                    scope_stack.pop()
                elif line.startswith("$var"):
                    parts = line.split()
                    if len(parts) >= 5 and _base_name(parts[4]) == _base_name(args.signal.split(".")[-1]):
                        print(f"  {'.'.join(scope_stack + [parts[4]])} (width={parts[2]})", file=out)
                elif line.startswith("$enddefinitions"):
                    break
        if args.output:
            out.close()
        sys.exit(1)

    if size != TOTAL_BITS:
        print(f"Error: signal '{hpath}' width ({size}) does not match layout width ({TOTAL_BITS}).", file=out)
        print(f"       Provide a --layout file whose field widths sum to {size}.", file=out)
        if args.output:
            out.close()
        sys.exit(1)

    print(f"# Monitoring signal: {hpath} (id={sid}, size={size})", file=out)

    field_list = list(FIELD_MAP.keys())
    if selected_fields:
        field_list = [n for n in field_list if n in selected_fields]

    if args.csv:
        print("time," + ",".join(field_list), file=out)
    else:
        print(f"{'time':>14} " + " ".join(f"{n:>14}" for n in field_list), file=out)

    # VCD value-change regex
    re_bin = re.compile(r"^b([01x]+)\s+" + re.escape(sid) + r"\s*$")
    re_bit = re.compile(r"^([01x])" + re.escape(sid) + r"\s*$")
    re_time = re.compile(r"^#([0-9.eE+-]+)$")

    use_context = (args.context is not None and args.context > 0 and addr_filter is not None)

    if use_context:
        # First pass: collect all candidate rows and mark matches.
        rows = []
        current_val = "0" * TOTAL_BITS
        current_time = 0.0
        in_vars = False
        with open(args.vcd, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("$dumpvars"):
                    in_vars = True
                    continue
                if not in_vars and not line.startswith("#"):
                    continue

                m = re_time.match(line)
                if m:
                    current_time = float(m.group(1)) * timescale
                    continue

                m = re_bin.match(line)
                if m:
                    val = m.group(1)
                    if len(val) < TOTAL_BITS:
                        val = val[0] * (TOTAL_BITS - len(val)) + val
                    elif len(val) > TOTAL_BITS:
                        val = val[-TOTAL_BITS:]
                    current_val = val
                else:
                    m = re_bit.match(line)
                    if m:
                        current_val = m.group(1) * TOTAL_BITS
                    else:
                        continue

                if t_start is not None and current_time < t_start:
                    continue
                if t_end is not None and current_time > t_end:
                    continue

                vals = split_value(current_val, selected_fields)
                if vals is None:
                    continue

                is_match = False
                cpu_haddr_bits = vals.get("cpu_haddr")
                if cpu_haddr_bits and int(cpu_haddr_bits, 2) == addr_filter:
                    is_match = True

                row = format_row(args.csv, current_time, field_list, vals)
                rows.append((current_time, row, is_match))

        if not rows:
            print("# No samples matched the filter.", file=out)
            if args.output:
                out.close()
            return

        match_indices = [i for i, (_, _, is_match) in enumerate(rows) if is_match]
        if not match_indices:
            print("# No samples matched the filter.", file=out)
            if args.output:
                out.close()
            return

        output_indices = set()
        for idx in match_indices:
            lo = max(0, idx - args.context)
            hi = min(len(rows), idx + args.context + 1)
            for i in range(lo, hi):
                output_indices.add(i)

        for i in sorted(output_indices):
            print(rows[i][1], file=out)
    else:
        current_val = "0" * TOTAL_BITS
        current_time = 0.0
        printed_header = False
        in_vars = False
        with open(args.vcd, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("$dumpvars"):
                    in_vars = True
                    continue
                if line.startswith("$end") and in_vars:
                    pass
                if not in_vars and not line.startswith("#"):
                    continue

                m = re_time.match(line)
                if m:
                    current_time = float(m.group(1)) * timescale
                    continue

                m = re_bin.match(line)
                if m:
                    val = m.group(1)
                    if len(val) < TOTAL_BITS:
                        val = val[0] * (TOTAL_BITS - len(val)) + val
                    elif len(val) > TOTAL_BITS:
                        val = val[-TOTAL_BITS:]
                    current_val = val
                else:
                    m = re_bit.match(line)
                    if m:
                        current_val = m.group(1) * TOTAL_BITS
                    else:
                        continue

                if t_start is not None and current_time < t_start:
                    continue
                if t_end is not None and current_time > t_end:
                    continue

                vals = split_value(current_val, selected_fields)
                if vals is None:
                    continue

                if addr_filter is not None:
                    cpu_haddr_bits = vals.get("cpu_haddr")
                    if cpu_haddr_bits:
                        if int(cpu_haddr_bits, 2) != addr_filter:
                            continue

                print(format_row(args.csv, current_time, field_list, vals), file=out)
                printed_header = True

        if not printed_header:
            print("# No samples matched the filter.", file=out)

    if args.output:
        out.close()


if __name__ == "__main__":
    main()
