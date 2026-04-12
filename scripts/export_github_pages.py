#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import host.public_site as public_site


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Export the Marathon GitHub Pages snapshot')
    parser.add_argument('--output-dir', default='build/github-pages')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    result = public_site.export_github_pages(output_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
