# dogsheep-beta

[![PyPI](https://img.shields.io/pypi/v/dogsheep-beta.svg)](https://pypi.org/project/dogsheep-beta/)
[![Changelog](https://img.shields.io/github/v/release/dogsheep/beta?include_prereleases&label=changelog)](https://github.com/dogsheep/beta/releases)
[![Tests](https://github.com/dogsheep/beta/workflows/Test/badge.svg)](https://github.com/dogsheep/beta/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/dogsheep/beta/blob/main/LICENSE)

Dogsheep search index

## Installation

Install this tool like so:

    $ pip install dogsheep-beta

## Usage

Run the indexer using the `dogsheep-beta` command-line tool:

    $ dogsheep-beta index dogsheep.db config.yml

The `config.yml` file contains details of the databases and tables that should be indexed:

```yaml
twitter.db:
    tweets:
        sql: |-
            select
                tweets.id as key,
                'Tweet by @' || users.screen_name as title,
                tweets.created_at as timestamp,
                tweets.full_text as search_1
            from tweets join users on tweets.user = users.id
    users:
        sql: |-
            select
                id as key,
                name || ' @' || screen_name as title,
                created_at as timestamp,
                description as search_1
            from users
```

This will create a `search_index` table in the `dogsheep.db` database populated by data from those SQL queries.

By default the search index that this tool creates will be configured for Porter stemming. This means that searches for words like `run` will match documents containing `runs` or `running`.

If you don't want to use Porter stemming, use the `--tokenize none` option:

    $ dogsheep-beta index dogsheep.db config.yml --tokenize none

You can pass other SQLite tokenize argumenst here, see [the SQLite FTS tokenizers documentation](https://www.sqlite.org/fts5.html#tokenizers).

## Columns

The columns that can be returned by our query are:

- `key` - a unique (within that table) primary key
- `title` - the title for the item
- `timestamp` - an ISO8601 timestamp, e.g. `2020-09-02T21:00:21`
- `search_1` - a larger chunk of text to be included in the search index
- `category` - an integer category ID, see below

## Categories

Indexed items can be assigned a category. Categories are integers that correspond to records in the `categories` table, which defaults to containing the following:

|   id | name    |
|------|---------|
|    1 | created |
|    2 | saved   |

`created` is intended for items that have been created by the Dogsheep instance owner. `saved` is intended for items that they have saved, liked or favourited.

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:

    cd dogsheep-beta
    python3 -mvenv venv
    source venv/bin/activate

Or if you are using `pipenv`:

    pipenv shell

Now install the dependencies and tests:

    pip install -e '.[test]'

To run the tests:

    pytest
