#!/usr/bin/env python3
"""Plot a data file written by a dsp function testbench.

The file is CSV with a leading comment line naming the configuration, then a header row.
The last two columns are always the function result and the reference. The column before
them is the swept input. Any columns to the left of that are series keys, and each distinct
combination of their values is drawn as its own pair of lines.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import OrderedDict
from pathlib import Path

import matplotlib

MISMATCH_COLOR = "#d62728"


class DataError(Exception):
    """A data file that does not match the format the testbenches write."""


class DataFile:
    """One testbench data file: its configuration line, column names, and rows."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.config = path.name
        with path.open(newline="") as fh:
            first = fh.readline()
            if first.startswith("#"):
                self.config = first[1:].strip()
            else:
                fh.seek(0)
            reader = csv.reader(fh)
            try:
                self.columns = next(reader)
            except StopIteration as err:
                raise DataError(f"{path}: no header row") from err
            if len(self.columns) < 3:
                raise DataError(
                    f"{path}: need at least x,y,exp columns, got {self.columns}"
                )
            self.rows = [[int(v) for v in row] for row in reader if row]
        if not self.rows:
            raise DataError(f"{path}: no data rows")

    @property
    def keys(self) -> list[str]:
        return self.columns[:-3]

    @property
    def x_name(self) -> str:
        return self.columns[-3]

    def series(
        self, keep: dict[str, int] | None = None
    ) -> "OrderedDict[tuple[int, ...], list[list[int]]]":
        """Group rows by the values of the leading key columns, preserving file order."""
        nkeys = len(self.keys)
        wanted = {
            self.keys.index(n): v for n, v in (keep or {}).items() if n in self.keys
        }
        out: OrderedDict[tuple[int, ...], list[list[int]]] = OrderedDict()
        for row in self.rows:
            key = tuple(row[:nkeys])
            if any(key[i] != v for i, v in wanted.items()):
                continue
            out.setdefault(key, []).append(row)
        return out


def label_for(data: DataFile, key: tuple[int, ...]) -> str:
    return ", ".join(f"{n}={v}" for n, v in zip(data.keys, key))


def draw(data: DataFile, axes, keep: dict[str, int] | None = None) -> int:
    """Draw one data file onto one axes. Returns the number of mismatching rows."""
    mismatches = 0
    series = data.series(keep)
    if not series:
        raise DataError(f"{data.path}: --key selected no rows; keys are {data.keys}")
    for key, rows in series.items():
        nkeys = len(data.keys)
        xs = [r[nkeys] for r in rows]
        ys = [r[nkeys + 1] for r in rows]
        exps = [r[nkeys + 2] for r in rows]
        suffix = f" [{label_for(data, key)}]" if data.keys else ""
        (line,) = axes.plot(xs, ys, linewidth=1.2, label=f"y{suffix}")
        axes.plot(
            xs,
            exps,
            linewidth=1.0,
            linestyle="--",
            color=line.get_color(),
            alpha=0.7,
            label=f"exp{suffix}",
        )
        bad = [(x, y) for x, y, e in zip(xs, ys, exps) if y != e]
        mismatches += len(bad)
        if bad:
            axes.plot(
                [b[0] for b in bad],
                [b[1] for b in bad],
                linestyle="none",
                marker="o",
                markersize=4,
                markerfacecolor="none",
                markeredgecolor=MISMATCH_COLOR,
                markeredgewidth=1.2,
            )

    title = data.config
    if mismatches:
        title = f"{title}  --  {mismatches} mismatches"
    axes.set_title(title, fontsize=9)
    axes.set_xlabel(data.x_name)
    axes.set_ylabel("value")
    axes.grid(True, alpha=0.3)
    # A curve per (sh, frac) is 64 entries; a legend that size hides the plot it labels.
    handles, _ = axes.get_legend_handles_labels()
    if len(handles) <= 12:
        axes.legend(fontsize=7)
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="+", type=Path, help="data CSV files")
    parser.add_argument(
        "--out", type=Path, help="write a PNG here instead of opening a window"
    )
    parser.add_argument(
        "--key",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="keep only this series, e.g. --key frac=3 --key sh=0 "
        "(repeatable; a data file with 64 series is unreadable otherwise)",
    )
    args = parser.parse_args()

    keep = {}
    for item in args.key:
        name, _, value = item.partition("=")
        if not value.lstrip("-").isdigit():
            print(f"error: --key wants NAME=INTEGER, got {item!r}", file=sys.stderr)
            return 2
        keep[name] = int(value)

    if args.out:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # With no display matplotlib quietly falls back to a file-only backend, and plt.show()
    # then does nothing at all. Say so rather than appearing to have drawn something.
    if not args.out:
        interactive = {b.lower() for b in matplotlib.rcsetup.interactive_bk}
        if matplotlib.get_backend().lower() not in interactive:
            print(
                f"error: no interactive display (backend is "
                f"{matplotlib.get_backend()}); use --out FILE.png",
                file=sys.stderr,
            )
            return 2

    try:
        datafiles = [DataFile(p) for p in args.files]
    except (DataError, OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    fig, axs = plt.subplots(
        len(datafiles),
        1,
        figsize=(9, 4 * len(datafiles)),
        sharex=len(datafiles) > 1,
        squeeze=False,
    )
    try:
        total = sum(draw(d, axs[i][0], keep) for i, d in enumerate(datafiles))
    except DataError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    fig.tight_layout()

    if args.out:
        fig.savefig(args.out, dpi=120)
        print(f"wrote {args.out}")
    else:
        plt.show()

    print(f"{total} mismatching rows across {len(datafiles)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
