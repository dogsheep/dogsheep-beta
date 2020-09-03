from datasette import hookimpl
from dogsheep_beta.utils import parse_metadata
import html
import urllib
from jinja2 import Template
import json

TIMELINE_SQL = """
select
  search_index.rowid,
  search_index.[table],
  search_index.key,
  search_index.title,
  search_index.category,
  search_index.timestamp,
  search_index.search_1
from
  search_index
{where}
  {where_clauses}
order by
  search_index.timestamp desc
limit 100
"""

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
{where}
  {where_clauses}
order by
  search_index_fts.rank, search_index.timestamp desc
limit 100
"""
FILTER_COLS = ("table", "category", "is_public")


async def beta(request, datasette):
    from datasette.utils.asgi import Response

    config = datasette.plugin_config("dogsheep-beta") or {}
    database_name = config.get("database") or datasette.get_database().name
    dogsheep_beta_config_file = config["config_file"]
    rules = parse_metadata(open(dogsheep_beta_config_file).read())
    q = request.args.get("q") or ""
    results = []
    facets = {}
    count = None

    results = await search(datasette, database_name, request)
    count, facets = await get_count_and_facets(datasette, database_name, request)
    await process_results(datasette, results, rules)

    hiddens = [
        {"name": column, "value": request.args[column]}
        for column in FILTER_COLS
        if column in request.args
    ]
    return Response.html(
        await datasette.render_template(
            "beta.html",
            {
                "q": q or "",
                "count": count,
                "results": results,
                "facets": facets,
                "hiddens": hiddens,
            },
            request=request,
        )
    )


async def search(datasette, database_name, request):
    database = datasette.get_database(database_name)
    q = request.args.get("q") or ""
    params = {"query": q}
    where_clauses = []
    sql = TIMELINE_SQL
    if q:
        sql = SEARCH_SQL
        where_clauses.append("search_index_fts match :query ")
    for arg in FILTER_COLS:
        if arg in request.args:
            where_clauses.append("[{arg}]=:{arg}".format(arg=arg))
            params[arg] = request.args[arg]
    sql_to_execute = sql.format(
        where=" where " if where_clauses else "",
        where_clauses=" and ".join(where_clauses),
    )
    results = await database.execute(sql_to_execute, params)
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
            first = display_results.first()
            if first:
                result["display"] = dict(first)
            else:
                result["display"] = {}
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


async def get_count_and_facets(datasette, database_name, request):
    from datasette.views.table import TableView
    from datasette.utils.asgi import Request, Response

    q = request.args.get("q") or ""
    args = {
        "_facet": ["table", "category", "is_public"],
        "_size": 0,
    }
    if q:
        args["_search"] = q
        args["_searchmode"] = "raw"
    for column in FILTER_COLS:
        if column in request.args:
            args[column] = request.args[column]

    path_with_query_string = "/{}/search_index.json?{}".format(
        database_name,
        urllib.parse.urlencode(
            args,
            doseq=True,
        ),
    )
    request = Request.fake(path_with_query_string)
    view = TableView(datasette)
    data, _, _ = await view.data(
        request, database=database_name, hash=None, table="search_index", _next=None
    )
    count, facets = data["filtered_table_rows_count"], data["facet_results"]
    facets = facets.values()
    # Rewrite toggle_url on facet_results
    # ../search_index.json?_search=wolf&_facet=table&_facet=category&_facet=is_public&_size=0&category=2
    for facet in facets:
        for result in facet["results"]:
            bits = urllib.parse.urlparse(result["toggle_url"])
            qs_bits = dict(urllib.parse.parse_qsl(bits.query))
            to_remove = [k for k in qs_bits if k.startswith("_")]
            for k in to_remove:
                qs_bits.pop(k)
            qs_bits["q"] = q
            result["toggle_url"] = "?" + urllib.parse.urlencode(qs_bits)
    return count, facets


@hookimpl
def register_routes():
    return [("/-/beta", beta)]


@hookimpl
def extra_template_vars():
    return {"intcomma": lambda s: "{:,}".format(int(s))}
