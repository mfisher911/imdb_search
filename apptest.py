#!/usr/bin/env python3

import argparse
import logging
import pprint

import application

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def main():
    application.debug = True  # disable sending debug emails
    result = application.process(args.url)
    pprint.pprint(result)
    if args.sheets:
        application.log_to_sheets(result["title"])

    if args.trakt:
        application.trakt_log(args.url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--sheets", action="store_true", default=False)
    parser.add_argument("--trakt", action="store_true", default=False)
    args = parser.parse_args()

    main()
