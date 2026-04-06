#!/usr/bin/env python3
"""ANAF data parsers."""
import argparse

from parsers.iban.parser import IbanParser

PARSERS = {
    "iban": IbanParser,
}


def main():
    parser = argparse.ArgumentParser(description="ANAF data parsers")
    parser.add_argument("parser", choices=PARSERS.keys(), help="Parser to run")
    parser.add_argument("-o", "--output", default="output", help="Output directory")
    args = parser.parse_args()

    p = PARSERS[args.parser](output_dir=args.output)
    p.run()


if __name__ == "__main__":
    main()
