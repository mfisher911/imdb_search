"""Retrieve a page from IMDb and return info."""
import logging
import os
from logging.config import dictConfig

import requests

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


def get_omdb(url):
    """Perform a search via OMDb and return the title and summary."""
    imdb_id = url.split("/")[4]

    omdb_url = (
        f"https://www.omdbapi.com/?apikey={os.getenv('OMDBAPI')}"
        f"&i={imdb_id}"
    )

    response = requests.get(omdb_url)
    logging.debug("OMDb response: %s", response.json())
    try:
        summary = response.json()["Plot"]
    except KeyError as e:
        logging.critical("No Plot in entry: %s", response.json())
        summary = ""
    title = response.json()["Title"]
    year = response.json()["Year"]

    result = {"title": title, "summary": summary, "year": year}
    logging.debug("get_omdb(%s) => %s", url, result)
    return result


def get_tmdb(url):
    """Perform a search via OMDb and return the title and summary."""
    imdb_id = url.split("/")[4]

    tmdb_url = (
        f"https://api.themoviedb.org/3/find/{imdb_id}?"
        f"api_key={os.getenv('TMDBAPI')}&language=en-US"
        f"&external_source=imdb_id"
    )

    response = requests.get(tmdb_url)
    _json = response.json()
    logging.debug("TMDb response: %s", _json)
    return {
        "title": _json["movie_results"][0]["title"],
        "original_title": _json["movie_results"][0]["original_title"],
    }


def process(url):
    """Perform lookups and generate output dict."""
    omdb = get_omdb(url)
    tmdb = get_tmdb(url)

    result = {
        "title": tmdb["title"],
        "original_title": tmdb["original_title"],
        "url": url,
        "summary": omdb["summary"],
        "year": omdb["year"],
    }
    if tmdb["title"] != tmdb["original_title"]:
        result["foreign_title"] = True

    logging.info("returning result: %s", result)
    return result


@app.route("/imdb/", methods=["GET", "POST"])
def hello_world():
    """Handle web request and return result."""
    result = "Hello, world."
    if request.form:
        _input = request.form.get("input")
        logging.info("got input: %s", _input)
        url = ""
        parts = _input.split("\r\n")
        url = parts[-1]
        if len(url) == 0:
            return "No URL was provided", 400
        url = url.replace("\\/", "/")
        result = jsonify(process(url))

    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0")
