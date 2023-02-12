#!/usr/bin/env python
"""CLI to handle refresh of Trakt access token."""
import logging
import pprint

import click
from click_loglevel import LogLevel

import application


@click.command()
@click.option("-l", "--log-level", type=LogLevel(), default=logging.INFO)
def main(log_level):
    """Get the Trakt access token."""
    logger = logging.getLogger(__name__)
    logging.getLogger("application").setLevel(log_level)
    logger.setLevel(log_level)

    auth = application.trakt_authenticate()
    logger.debug("token: %s", pprint.pformat(auth))


if __name__ == "__main__":
    main()
