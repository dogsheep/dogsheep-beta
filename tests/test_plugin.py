from datasette.app import Datasette
from bs4 import BeautifulSoup as Soup
from dogsheep_beta.cli import index
from dogsheep_beta.utils import parse_metadata
import textwrap
import sqlite_utils
import pytest
import urllib
import httpx


@pytest.mark.asyncio
async def test_search(ds):
    async with httpx.AsyncClient(app=ds.app()) as client:
        response = await client.get("http://localhost/-/beta")
        assert 200 == response.status_code
        assert '<input type="search" name="q" value="" id="q">' in response.text
        response = await client.get("http://localhost/-/beta?q=things")
        assert 200 == response.status_code
        for fragment in (
            "<p>Got 3 results",
            "<p>Email from blah@example.com, subject Hey there",
            "<p>Email from blah@example.com, subject What&#39;s going on",
            "<p>Commit to dogsheep/dogsheep-beta on 2020-08-01T00:05:02",
            '<p>User searched for: "things"</p>',
        ):
            assert fragment in response.text
        # Test facets
        soup = Soup(response.text, "html5lib")
        facet_els = soup.select(".facet")
        facets = [
            {
                "name": el.find("h2").text,
                "values": [
                    {
                        "selected": "selected" in li.get("class", ""),
                        "count": int(li.select(".count")[0].text),
                        "url": li.find("a")["href"],
                        "label": li.select(".label")[0].text,
                    }
                    for li in el.findAll("li")
                ],
            }
            for el in facet_els
        ]
        assert facets == [
            {
                "name": "type",
                "values": [
                    {
                        "selected": False,
                        "count": 2,
                        "url": "?type=emails.db%2Femails&q=things",
                        "label": "emails.db/emails",
                    },
                    {
                        "selected": False,
                        "count": 1,
                        "url": "?type=github.db%2Fcommits&q=things",
                        "label": "github.db/commits",
                    },
                ],
            },
            {
                "name": "category",
                "values": [
                    {
                        "selected": False,
                        "count": 1,
                        "url": "?category=1&q=things",
                        "label": "created",
                    }
                ],
            },
            {
                "name": "is_public",
                "values": [
                    {
                        "selected": False,
                        "count": 2,
                        "url": "?is_public=0&q=things",
                        "label": "0",
                    },
                    {
                        "selected": False,
                        "count": 1,
                        "url": "?is_public=1&q=things",
                        "label": "1",
                    },
                ],
            },
            {
                "name": "timestamp",
                "values": [
                    {
                        "selected": False,
                        "count": 2,
                        "url": "?timestamp__date=2020-08-01&q=things",
                        "label": "2020-08-01",
                    },
                    {
                        "selected": False,
                        "count": 1,
                        "url": "?timestamp__date=2020-08-02&q=things",
                        "label": "2020-08-02",
                    },
                ],
            },
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "q,expected",
    (
        (
            "things NOT email",
            [
                "github.db/commits:a5b39c5049b28997528bb0eca52730ab6febabeaba54cfcba0ab5d70e7207523"
            ],
        ),
        (
            "#dogfest",
            ["emails.db/emails:1"],
        ),
    ),
)
async def test_advanced_search(ds, q, expected):
    async with httpx.AsyncClient(app=ds.app()) as client:
        response = await client.get(
            "http://localhost/-/beta?" + urllib.parse.urlencode({"q": q})
        )
        assert response.status_code == 200
        soup = Soup(response.text, "html5lib")
        results = [el["data-table-key"] for el in soup.select("[data-table-key]")]
        assert results == expected
        # Check that facets exist on the page
        assert len(soup.select(".facet li")), "Could not see any facet results"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sort,expected",
    (
        (
            "",
            ["emails.db/emails:1", "emails.db/emails:2"],
        ),
        (
            "newest",
            ["emails.db/emails:2", "emails.db/emails:1"],
        ),
        (
            "oldest",
            ["emails.db/emails:1", "emails.db/emails:2"],
        ),
    ),
)
async def test_search_order(ds, sort, expected):
    async with httpx.AsyncClient(app=ds.app()) as client:
        q = "email"
        response = await client.get(
            "http://localhost/-/beta?" + urllib.parse.urlencode({"q": q, "sort": sort})
        )
        assert response.status_code == 200
        soup = Soup(response.text, "html5lib")
        results = [el["data-table-key"] for el in soup.select("[data-table-key]")]
        assert results == expected
        # Check that sort links exist and are correct
        sort_label = sort or "relevance"
        assert "<strong>{}</strong>".format(sort_label) in response.text
        if sort_label != "relevance":
            assert (
                '<input type="hidden" name="sort" value="{}">'.format(sort_label)
                in response.text
            )
        for sort_order in ("relevance", "newest", "oldest"):
            if sort_order != sort_label:
                assert ">{}</a>".format(sort_order) in response.text


ALL_EXPECTED = [
    "github.db/commits:5becbf70d64951e2910314ef5227d19b11c25b0c9586934941366da8997e57cb",
    "emails.db/emails:2",
    "github.db/commits:a5b39c5049b28997528bb0eca52730ab6febabeaba54cfcba0ab5d70e7207523",
    "emails.db/emails:1",
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sort,expected",
    (
        ("", ALL_EXPECTED),
        ("newest", ALL_EXPECTED),
        ("oldest", list(reversed(ALL_EXPECTED))),
    ),
)
async def test_search_order_for_timeline(ds, sort, expected):
    async with httpx.AsyncClient(app=ds.app()) as client:
        url = "http://localhost/-/beta"
        if sort:
            url += "?sort=" + sort
        response = await client.get(url)
        assert response.status_code == 200
        soup = Soup(response.text, "html5lib")
        results = [el["data-table-key"] for el in soup.select("[data-table-key]")]
        assert results == expected
        # Check that sort links exist and are correct
        sort_label = sort or "newest"
        assert "<strong>{}</strong>".format(sort_label) in response.text
        assert ">relevance</a>" not in response.text
        assert (
            ">{}</a>".format("oldest" if sort_label == "newest" else "newest")
            in response.text
        )


@pytest.mark.asyncio
async def test_fixture(ds):
    async with httpx.AsyncClient(app=ds.app()) as client:
        response = await client.get("http://localhost/-/databases.json")
        assert 200 == response.status_code
        assert {d["name"] for d in response.json()} == {"beta", "emails", "github"}


@pytest.mark.asyncio
async def test_plugin_is_installed():
    app = Datasette([], memory=True).app()
    async with httpx.AsyncClient(app=app) as client:
        response = await client.get("http://localhost/-/plugins.json")
        assert 200 == response.status_code
        installed_plugins = {p["name"] for p in response.json()}
        assert "dogsheep-beta" in installed_plugins


@pytest.fixture
def ds(tmp_path_factory, monkeypatch):
    db_directory = tmp_path_factory.mktemp("dbs")
    monkeypatch.chdir(db_directory)
    github_path = db_directory / "github.db"
    emails_path = db_directory / "emails.db"
    beta_path = db_directory / "beta.db"
    beta_config_path = db_directory / "dogsheep-beta.yml"

    beta_config_path.write_text(
        textwrap.dedent(
            """
    emails.db:
        emails:
            display_sql: |-
                select * from emails where id = :key
            display: |-
                <p>Email from {{ display.from_ }}, subject {{ display.subject }}
            sql: |-
                select
                    id as key,
                    subject as title,
                    date as timestamp,
                    0 as is_public,
                    body as search_1
                from
                    emails
    github.db:
        commits:
            display_sql: |-
                select
                    commits.sha,
                    commits.message,
                    commits.committer_date,
                    commits.repo_name,
                    :q as their_query
                from commits where sha = :key
            display: |-
                <p>Commit to {{ display.repo_name }} on {{ display.committer_date }}</p>
                <p>{{ display.message }} - {{ display.sha }}</p>
                <p>User searched for: "{{ display.their_query }}"</p>
            sql: |-
                select
                    sha as key,
                    'Commit to ' || commits.repo_name as title,
                    committer_date as timestamp,
                    1 as category,
                    1 as is_public,
                    message as search_1
                from
                    commits
    """,
        ),
        "utf-8",
    )

    METADATA = textwrap.dedent(
        """
    plugins:
        dogsheep-beta:
            database: beta
            config_file: dogsheep-beta.yml
    """
    )

    github_db = sqlite_utils.Database(github_path)
    github_db["commits"].insert_all(
        [
            {
                "sha": "a5b39c5049b28997528bb0eca52730ab6febabeaba54cfcba0ab5d70e7207523",
                "message": "Another commit to things",
                "repo_name": "dogsheep/dogsheep-beta",
                "committer_date": "2020-08-01T00:05:02",
            },
            {
                "sha": "5becbf70d64951e2910314ef5227d19b11c25b0c9586934941366da8997e57cb",
                "message": "Added some tests",
                "repo_name": "dogsheep/dogsheep-beta",
                "committer_date": "2020-08-02T12:35:48",
            },
        ],
        pk="sha",
    )
    emails_db = sqlite_utils.Database(emails_path)
    emails_db["emails"].insert_all(
        [
            {
                "id": 1,
                "subject": "Hey there #dogfest",
                "body": "An email about things",
                "from_": "blah@example.com",
                "date": "2020-08-01T00:05:02",
            },
            {
                "id": 2,
                "subject": "What's going on",
                "body": "Another email about things",
                "from_": "blah@example.com",
                "date": "2020-08-02T00:05:02",
            },
        ],
        pk="id",
    )
    index.callback(beta_path, beta_config_path, None, [])
    ds = Datasette(
        [str(beta_path), str(github_path), str(emails_path)],
        metadata=parse_metadata(METADATA),
    )
    return ds
