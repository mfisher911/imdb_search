# imdb_search

Scrape IMDb for Day One entry templates.

Expects a POSTed form with a variable "input", which can either be a
URL (from "Copy URL") or the text from an iOS Share Sheet action.

Returns a JSON dictionary with the following keys:

- title -- IMDb page title
- url -- IMDb page URL
- summary -- Full IMDb summary
- letterbox_title -- title with the year removed

## Deployment Notes

Runs behind a reverse proxy with the following tooling:

- uWSGI application server
- Supervisor Process Control System
