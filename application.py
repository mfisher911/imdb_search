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


@app.route("/imdb/", methods=["GET", "POST"])
def hello_world():
    """Handle web request and return result."""
    result = "Hello, world."
    if request.form:
        _input = request.form.get("input")
        logging.info("got input: %s", _input)
        title = ""
        _sum = ""
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

        imdb = requests.get(url)
        soup = BeautifulSoup(imdb.content, "html5lib")
        title = soup.title.text.replace(" - IMDb", "")
        summary = ""
        try:
            summary = soup.find_all("div", class_="summary_text")[
                0
            ].text.strip()
        except IndexError:
            summary = _sum

        # strip the year from the end for letterboxd.com
        yindex = title.rfind("(")
        if yindex != -1:
            lb_title = title[0 : yindex - 1]
        else:
            lb_title = title

        result = {
            "title": title,
            "url": url,
            "summary": summary,
            "letterboxd_title": lb_title,
        }
        logging.info("returning result: %s", result)
        result = jsonify(result)

    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0")
