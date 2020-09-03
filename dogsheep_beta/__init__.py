from datasette import hookimpl
from dogsheep_beta.utils import parse_metadata
import html
from urllib.parse import urlencode
from jinja2 import Template
import json

SEARCH_SQL = """
select
  search_index_fts.rank,
  search_index.rowid,
  search_index.[table],
  search_index.key,
  search_index.title,
  search_index.category,
  search_index.timestamp,
  search_index.search_1
from
  search_index join search_index_fts on search_index.rowid = search_index_fts.rowid
where
  search_index_fts match :query
order by
  search_index_fts.rank, search_index.timestamp desc
limit 100
"""


async def beta(request, datasette):
    from datasette.utils.asgi import Response

    config = datasette.plugin_config("dogsheep-beta") or {}
    database_name = config.get("database") or datasette.get_database().name
    dogsheep_beta_config_file = config["config_file"]
    rules = parse_metadata(open(dogsheep_beta_config_file).read())
    q = request.args.get("q")
    results = []
    facets = {}
    if q:
        results = await search(datasette, database_name, q)
        count, facets = await get_count_and_facets(datasette, database_name, q)
        await process_results(datasette, results, rules)
    return Response.html(
        await datasette.render_template(
            "beta.html",
            {
                "q": q,
                "count": count,
                "results": results,
                "facets": facets,
            },
            request=request,
        )
    )


async def search(datasette, database_name, query):
    database = datasette.get_database(database_name)
    results = await database.execute(SEARCH_SQL, {"query": query})
    return [dict(r) for r in results.rows]


async def process_results(datasette, results, rules):
    # Adds a 'display' property with HTML to the results
    compiled = {}
    rules_by_table = {}
    for db_name, tables in rules.items():
        for table, meta in tables.items():
            rules_by_table["{}/{}".format(db_name, table)] = meta

    for result in results:
        table = result["table"]
        meta = rules_by_table[table]
        if meta.get("display_sql"):
            db = datasette.get_database(table.split(".")[0])
            display_results = await db.execute(
                meta["display_sql"], {"key": result["key"]}
            )
            result["display"] = dict(display_results.first())
        output = None
        if meta.get("display"):
            if table not in compiled:
                compiled[table] = Template(meta["display"])
            output = compiled[table].render(**result)
        else:
            output = "<pre>{}</pre>".format(
                html.escape(json.dumps(result, default=repr, indent=4))
            )
        result["output"] = output


async def get_count_and_facets(datasette, database_name, q):
    from datasette.views.table import TableView
    from datasette.utils.asgi import Request, Response

    path_with_query_string = "/{}/search_index.json?{}".format(
        database_name,
        urlencode(
            {"_search": q, "_facet": ["table", "category"], "_size": 0}, doseq=True
        ),
    )
    request = Request.fake(path_with_query_string)
    view = TableView(datasette)
    data, _, _ = await view.data(
        request, database=database_name, hash=None, table="search_index", _next=None
    )
    return data["filtered_table_rows_count"], data["facet_results"]


@hookimpl
def register_routes():
    return [("/-/beta", beta)]
