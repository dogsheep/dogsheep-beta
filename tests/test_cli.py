from click.testing import CliRunner
from dogsheep_beta.cli import cli
import sqlite_utils
import datetime
import textwrap
import pytest


def test_version():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["--version"])
        assert 0 == result.exit_code
        assert result.output.startswith("cli, version ")


@pytest.mark.parametrize("use_porter", [True, False])
def test_basic(tmp_path_factory, monkeypatch, use_porter):
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
                "likes": "running",
                "age": 5,
                "created": "2020-08-22 04:41:33",
            },
            {
                "id": 2,
                "name": "Pancakes",
                "likes": "chasing",
                "age": 4,
                "created": "2020-08-17 11:35:42",
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
                    created as timestamp,
                    case name when 'Cleo' then 1 else 2 end as category,
                    likes as search_1
                from dogs
    """
        ),
        "utf-8",
    )

    runner = CliRunner()
    args = ["index", str(beta_path), str(config_path)]
    if not use_porter:
        args.extend(["--tokenize", "none"])
    result = runner.invoke(cli, args)
    assert result.exit_code == 0

    beta_db = sqlite_utils.Database(beta_path)

    assert list(beta_db["categories"].rows) == [
        {"id": 1, "name": "created"},
        {"id": 2, "name": "saved"},
        {"id": 3, "name": "received"},
    ]
    assert list(beta_db["search_index"].rows) == [
        {
            "table": "dogs.db/dogs",
            "key": "1",
            "title": "Cleo",
            "timestamp": "2020-08-22 04:41:33",
            "category": 1,
            "is_public": 0,
            "search_1": "running",
            "search_2": None,
            "search_3": None,
        },
        {
            "table": "dogs.db/dogs",
            "key": "2",
            "title": "Pancakes",
            "timestamp": "2020-08-17 11:35:42",
            "category": 2,
            "is_public": 0,
            "search_1": "chasing",
            "search_2": None,
            "search_3": None,
        },
    ]
    indexes = [i.columns for i in beta_db["search_index"].indexes]
    assert indexes == [["is_public"], ["category"], ["timestamp"], ["table", "key"]]

    # Test that search works, with porter stemming
    results = beta_db["search_index"].search("run")
    if use_porter:
        assert results == [
            (
                "dogs.db/dogs",
                "1",
                "Cleo",
                "2020-08-22 04:41:33",
                1,
                0,
                "running",
                None,
                None,
            )
        ]
    else:
        assert results == []
