from click.testing import CliRunner
from dogsheep_beta.cli import cli
import sqlite_utils
import datetime
import textwrap


def test_version():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["--version"])
        assert 0 == result.exit_code
        assert result.output.startswith("cli, version ")


def test_basic(tmp_path_factory, monkeypatch):
    db_directory = tmp_path_factory.mktemp("dbs")
    monkeypatch.chdir(db_directory)
    db_path = db_directory / "dogs.db"
    beta_path = db_directory / "beta.db"
    config_path = db_directory / "config.yml"
    db = sqlite_utils.Database(db_path)
    db["dogs"].insert_all(
        [
            {
                "id": 1,
                "name": "Cleo",
                "age": 5,
                "created": "2020-08-22 04:41:33",
            },
            {
                "id": 2,
                "name": "Pancakes",
                "age": 4,
                "created": "2020-08-17 11:35:42"
            },
        ],
        pk="id",
    )

    config_path.write_text(
        textwrap.dedent(
            """
    dogs.db:
        dogs:
            sql: |-
                select
                    id as key,
                    name as title,
                    created as timestamp
                from dogs
    """
        ),
        "utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["index", str(beta_path), str(config_path)])
    assert result.exit_code == 0

    beta_db = sqlite_utils.Database(beta_path)
    assert list(beta_db["search_index"].rows) == [
        {
            "table": "dogs.db/dogs",
            "key": "1",
            "title": "Cleo",
            "timestamp": "2020-08-22 04:41:33",
            "search_1": None,
            "search_2": None,
            "search_3": None,
        },
        {
            "table": "dogs.db/dogs",
            "key": "2",
            "title": "Pancakes",
            "timestamp": "2020-08-17 11:35:42",
            "search_1": None,
            "search_2": None,
            "search_3": None,
        },
    ]
