#! /usr/bin/env python
import json
import argparse
from api import log_api
from mod.wft_actions import BuildIncrement, WFTUtils

log = log_api.get_console_logger("update_ecl_sack_base")


def arguments():
    parse = argparse.ArgumentParser()
    parse.add_argument('--gerrit_yaml', '-g', required=True, help="gerrit_yaml")
    parse.add_argument('--ecl_branch', required=True, help="ecl branch in WFT")
    parse.add_argument('--changed_content', required=True, help="content change in sub builds")
    parse.add_argument('--base_branch', required=False, help="Base build branch in WFT")
    parse.add_argument('--base_load', required=False, help="Base build of increment")
    parse.add_argument('--PSINT_cycle', required=False, help="cycle for PS integration")
    return parse.parse_args()


def main():
    args = arguments()
    changed = json.loads(args.changed_content)
    ecl_base_load = ''
    if args.base_load and args.base_branch and args.ecl_branch:
        cb_incrementer = BuildIncrement(args.base_branch, base_build=args.base_load)
        cb_incrementer.run(args.PSINT_cycle)
        ecl_base_load = WFTUtils.get_build_detail(args.base_load)['ecl_sack_base']

    ecl_incrementer = BuildIncrement(args.ecl_branch, changed, ecl_base_load)
    ecl_incrementer.run(int(args.PSINT_cycle) + 1)


if __name__ == "__main__":
    main()
