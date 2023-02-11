"""Retrieve a page from IMDb, return info, and log to Google Sheets."""
from datetime import date
# lots of sample auth code from https://pypi.org/project/Flask-Login/

import logging
import os
import textwrap
from datetime import date
from logging.config import dictConfig

import flask_login
import requests

from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauth2client.service_account import ServiceAccountCredentials

# config constants
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
VALUE_INPUT_OPTION = "USER_ENTERED"
INSERT_DATA_OPTION = "INSERT_ROWS"

# The ID and range of the target spreadsheet.
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
RANGE_NAME = os.getenv("RANGE_NAME")


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

login_manager = flask_login.LoginManager()
app = Flask(__name__)
app.config.from_prefixed_env()
logger = logging.getLogger(__name__)
login_manager.init_app(app)

with open("users.json") as _json:
    users = json.load(_json)


class User(flask_login.UserMixin):
    """User class for Flask."""
    pass


def get_omdb(url):
    """Perform a search via OMDb and return the title and summary."""
    imdb_id = url.split("/")[4]

    omdb_url = (
        f"https://www.omdbapi.com/?apikey={os.getenv('OMDBAPI')}"
        f"&i={imdb_id}"
    )

    response = requests.get(omdb_url)
    logger.debug("OMDb response: %s", response.json())
    try:
        summary = response.json()["Plot"]
    except KeyError as err:
        logger.critical("No Plot in entry: %s (%s)", response.json(), err)
        summary = ""
    title = response.json()["Title"]
    year = response.json()["Year"]

    result = {"title": title, "summary": summary, "year": year}
    logger.debug("get_omdb(%s) => %s", url, result)
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
    logger.debug("TMDb response: %s", _json)
    return {
        "title": _json["movie_results"][0]["title"],
        "original_title": _json["movie_results"][0]["original_title"],
    }


def log_to_sheets(title):
    """Append TITLE into SPREADSHEET_ID as a new row below RANGE_NAME."""
    # Get the credentials.json by creating a new service account via
    #   https://console.cloud.google.com/iam-admin/serviceaccounts
    # and then give the new service account's email address write
    # permissions on the target spreadsheet
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", SCOPES
    )
    try:
        service = build(
            "sheets", "v4", credentials=credentials, cache_discovery=False
        )

        # Call the Sheets API
        sheet = service.spreadsheets()

        body = {"values": [[title, str(date.today())]]}

        request = sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption=VALUE_INPUT_OPTION,
            insertDataOption=INSERT_DATA_OPTION,
            body=body,
        )
        response = request.execute()
        logger.debug("%s", response)

    except HttpError as err:
        logger.critical("HttpError: %s", err)


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

    logger.info("returning result: %s", result)
    return result


@login_manager.user_loader
def user_loader(email):
    """Return a user object based on email address search."""
    if email not in users:
        return

    user = User()
    user.id = email
    return user


@login_manager.request_loader
def request_loader(request):
    """Get remote user object if possible."""
    email = request.form.get("email")
    return user_loader(email)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Return a simple login form if needed."""
    if flask.request.method == "GET":
        form = """
        <form action='login' method='POST'>
        <input type='text' name='email' id='email' placeholder='email'/>
        <input type='password' name='password' id='password'
            placeholder='password'/>
        <input type='submit' name='submit'/>
        </form>
        """
        return textwrap.dedent(form)

    email = flask.request.form["email"]
    if (
        email in users
        and flask.request.form["password"] == users[email]["password"]
    ):
        user = User()
        user.id = email
        flask_login.login_user(user)
        return flask.redirect(flask.url_for("protected"))

    return "Bad login (%s)" % email


@app.route("/imdb/", methods=["GET", "POST"])
@flask_login.login_required
def hello_world():
    """Handle web request and return result."""
    result = "Hello, world."
    if request.form:
        _input = request.form.get("input")
        logger.info("got input: %s", _input)
        url = ""
        parts = _input.split("\r\n")
        url = parts[-1]
        if len(url) == 0:
            return "No URL was provided", 400
        url = url.replace("\\/", "/")
        result = process(url)
        log_to_sheets(result["title"])
        result = jsonify(result)

    return result


@login_manager.unauthorized_handler
def unauthorized_handler():
    return "Unauthorized", 401


if __name__ == "__main__":
    app.run(host="0.0.0.0")
