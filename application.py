"""Retrieve a page from IMDb, return info, log to Trakt/Google Sheets."""
# lots of sample auth code from https://pypi.org/project/Flask-Login/

import json
import logging
import os
import textwrap
import re
from datetime import date, datetime, timedelta, timezone
from logging.config import dictConfig
from logging.handlers import SMTPHandler

import flask_login
import requests
from flask import Flask, jsonify, request
from flask.logging import default_handler
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauth2client.service_account import ServiceAccountCredentials
from trakt import Trakt

# config constants
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
VALUE_INPUT_OPTION = "USER_ENTERED"
INSERT_DATA_OPTION = "INSERT_ROWS"

# The ID and range of the target spreadsheet.
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
RANGE_NAME = os.getenv("RANGE_NAME")


mail_handler = SMTPHandler(
    mailhost="in1-smtp.messagingengine.com",
    fromaddr="server-error@shell.fisher.one",
    toaddrs=["mfisher@myfastmail.com"],
    subject="IMDb Lookup",
)
mail_handler.setLevel(logging.INFO)
mail_handler.setFormatter(
    logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )
)

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": (
                    "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
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
        "root": {"level": "DEBUG", "handlers": ["wsgi"]},
    }
)

login_manager = flask_login.LoginManager()
app = Flask(__name__)
app.config.from_prefixed_env()
logger = logging.getLogger(__name__)
logging.getLogger("trakt.interfaces.sync.core.mixins").addHandler(
    default_handler
)
login_manager.init_app(app)

if not app.debug:
    app.logger.addHandler(mail_handler)


with open("users.json") as _json:
    users = json.load(_json)


class User(flask_login.UserMixin):
    """User class for Flask."""

    pass


def trakt_authenticate():
    """CLI function for getting Trakt access token."""
    app.logger.debug(
        "trakt_authenticate(); TRAKT_CLIENT_ID=%s, TRAKT_CLIENT_SECRET=%s",
        os.getenv("TRAKT_CLIENT_ID")[0:5],
        os.getenv("TRAKT_CLIENT_SECRET")[0:5],
    )

    try:
        with open("trakt_auth.json") as _json:
            auth = json.load(_json)
    except FileNotFoundError as err:
        logger.critical("trakt_auth.json not found: %s", err)
        raise err

    exp = timedelta(seconds=auth["expires_in"]) + datetime.fromtimestamp(
        auth["created_at"], tz=timezone.utc
    )
    now = datetime.now(tz=timezone.utc)

    # check valid date:
    pad_date = now + timedelta(hours=(24 * 2))
    if exp > pad_date:
        logger.debug("exp (%s) > pad_date (%s); using cache", exp, pad_date)
        return auth

    Trakt.configuration.defaults.client(
        id=os.getenv("TRAKT_CLIENT_ID"),
        secret=os.getenv("TRAKT_CLIENT_SECRET"),
    )

    print(
        "Navigate to: %s"
        % Trakt["oauth"].authorize_url("urn:ietf:wg:oauth:2.0:oob")
    )

    code = input("Authorization code:")
    if not code:
        exit(1)

    authorization = Trakt["oauth"].token(code, "urn:ietf:wg:oauth:2.0:oob")
    if not authorization:
        exit(1)

    app.logger.info("New auth: %r" % authorization)
    os.umask(0o002)
    with open("trakt_auth.json", "w") as _json:
        json.dump(authorization, _json, indent=4, sort_keys=True)
    app.logger.debug("returning new auth: %s", authorization)
    return authorization


def trakt_log(url):
    """Create a Trakt history entry based on the IMDb ID passed."""
    imdb_id = url.split("/")[4]

    Trakt.configuration.defaults.client(
        id=os.getenv("TRAKT_CLIENT_ID"),
        secret=os.getenv("TRAKT_CLIENT_SECRET"),
    )

    auth = trakt_authenticate()
    Trakt.configuration.defaults.oauth.from_response(auth)
    app.logger.debug("using auth=%s", auth)

    Trakt["sync/history"].add(
        {
            "movies": [
                {
                    "watched_at": str(datetime.utcnow()),
                    "ids": {"imdb": imdb_id},
                }
            ]
        }
    )


def get_omdb(url):
    """Perform a search via OMDb and return the title and summary."""
    imdb_id = url.split("/")[4]

    omdb_url = (
        f"https://www.omdbapi.com/?apikey={os.getenv('OMDBAPI')}"
        f"&i={imdb_id}"
    )

    response = requests.get(omdb_url)
    app.logger.debug("OMDb response: %s", response.json())
    try:
        summary = response.json()["Plot"]
    except KeyError as err:
        app.logger.critical("No Plot in entry: %s (%s)", response.json(), err)
        summary = ""
    title = response.json()["Title"]
    year = response.json()["Year"]

    result = {"title": title, "summary": summary, "year": year}
    app.logger.debug("get_omdb(%s) => %s", url, result)
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
    app.logger.debug("TMDb response: %s", _json)
    return {
        "title": _json["movie_results"][0]["title"],
        "original_title": _json["movie_results"][0]["original_title"],
        "summary": _json["movie_results"][0]["overview"],
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
        app.logger.debug("%s", response)

    except HttpError as err:
        app.logger.critical("HttpError: %s", err)


def process(url):
    """Perform lookups and generate output dict."""
    omdb = get_omdb(url)
    tmdb = get_tmdb(url)

    result = {
        "title": tmdb["title"],
        "original_title": tmdb["original_title"],
        "url": url,
        "year": omdb["year"],
    }

    if "..." not in omdb["summary"]:
        result["summary"] = omdb["summary"]
    else:
        result["summary"] = tmdb["summary"]

    if tmdb["title"] != tmdb["original_title"]:
        result["foreign_title"] = True

    app.logger.info("returning result: %s", result)
    return result


@login_manager.user_loader
def user_loader(email):
    """Return a user object based on email address search."""
    app.logger.debug("user_loader(email=%s)", email)
    if email not in users:
        return None

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
    if request.method == "GET":
        form = """
        <form action='login' method='POST'>
        <input type='text' name='email' id='email' placeholder='email'/>
        <input type='password' name='password' id='password'
            placeholder='password'/>
        <input type='submit' name='submit'/>
        </form>
        """
        return textwrap.dedent(form)

    email = request.form["email"]
    if (
        email in users
        and request.form["password"] == users[email]["password"]
    ):
        user = User()
        user.id = email
        flask_login.login_user(user)
        app.logger.info("logged in user: %s", user)
        return app.redirect(app.url_for("imdb"))

    app.logger.critical(
        "bad user: %s (%s)", email, request.form["password"][0:5]
    )
    return "Bad login (%s)" % email


@app.route("/logout")
def logout():
    flask_login.logout_user()
    return app.redirect(app.url_for("imdb"))


@app.route("/imdb/", methods=["GET", "POST"])
@app.route("/imdb/<imdb_id>", methods=["GET"])
@flask_login.login_required
def imdb(imdb_id=None):
    """Handle web request and return result."""
    result = "Hello, world."
    if request.form:
        _input = request.form.get("input")
        app.logger.debug("got input: %s", _input)
        url = ""
        parts = _input.split("\r\n")
        url = parts[-1]
        if len(url) == 0:
            return "No URL was provided", 400
        url = url.replace("\\/", "/")
        url = re.sub(r"\?.*$", "", url)
        result = process(url)
        log_to_sheets(result["title"])
        trakt_log(url)
        result = jsonify(result)
    elif imdb_id:
        app.logger.info("got IMDb id: %s", imdb_id)
        url = f"https://www.imdb.com/title/{imdb_id}"
        result = process(url)
        trakt_log(url)
        result = jsonify(result)

    return result


@login_manager.unauthorized_handler
def unauthorized_handler():
    return "Unauthorized", 401


if __name__ == "__main__":
    app.run(host="0.0.0.0")
