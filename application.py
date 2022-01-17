"""Retrieve a page from IMDb and return info."""
import logging
from logging.config import dictConfig

import requests

from bs4 import BeautifulSoup
from flask import Flask, request, jsonify


dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": (
                    "[%(asctime)s] %(levelname)s in "
                    "%(module)s: %(message)s"
                ),
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["wsgi"]},
    }
)

app = Flask(__name__)


def filter_summary(tag):
    """Return true if the tag has a data-testid attribute."""
    return (
        tag.name == "span"
        and tag.has_attr("class")
        and "GenresAndPlot__TextContainerBreakpointXL" in tag.get("class")[0]
    )


def get_imdb(url):
    """Perform a search at IMDb and return the title and summary."""
    imdb = requests.get(url)
    soup = BeautifulSoup(imdb.content, "html5lib")
    title = soup.title.text.replace(" - IMDb", "")
    summary = None
    try:
        summary = soup.find_all(filter_summary)[0].text.strip()
    except IndexError:
        summary = ""

    return {"title": title, "summary": summary}


@app.route("/imdb/", methods=["GET", "POST"])
def hello_world():
    """Handle web request and return result."""
    result = "Hello, world."
    if request.form:
        _input = request.form.get("input")
        logging.info("got input: %s", _input)
        title = ""
        url = ""
        parts = _input.split("\r\n")
        if len(parts) == 3:
            title, _sum, url = parts
        elif len(parts) == 2:
            title, url = parts
        elif len(parts) == 1:
            url = _input
        if len(url) == 0:
            return "No URL was provided", 400
        url = url.replace("\\/", "/")

        imdb = get_imdb(url)
        if not title:
            title = imdb["title"]

        # strip the year from the end for letterboxd.com
        yindex = title.rfind("(")
        if yindex != -1:
            lb_title = title[0 : yindex - 1]
        else:
            lb_title = title

        result = {
            "title": title,
            "url": url,
            "summary": imdb["summary"],
            "letterboxd_title": lb_title,
        }
        logging.info("returning result: %s", result)
        result = jsonify(result)

    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0")
