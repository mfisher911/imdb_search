"""Retrieve a page from IMDb and return info."""
import logging
import os
from logging.config import dictConfig

import requests

from flask import Flask, request, jsonify
from tmdbapis import TMDbAPIs


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
        f"api_key={os.getenv('TMPDBAPI')}&language=en-US"
        f"&external_source=imdb_id"
    )

    tmdb = TMDbAPIs(os.getenv("TMDBAPI"))
    results = tmdb.find_by_id(imdb_id=imdb_id)
    return {
        "title": results.movie_results[0].title,
        "original_title": results.movie_results[0].original_title,
    }


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

        omdb = get_omdb(url)
        tmdb = get_tmdb(url)

        result = {
            "title": tmdb["title"],
            "original_title": tmdb["original_title"],
            "url": url,
            "summary": omdb["summary"],
            "letterboxd_title": tmdb["title"],
            "year": omdb["year"],
        }
        if tmdb["title"] != tmdb["original_title"]:
            result["foreign_title"] = True
        logging.info("returning result: %s", result)
        result = jsonify(result)

    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0")
