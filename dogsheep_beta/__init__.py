from datasette import hookimpl
from dogsheep_beta.utils import parse_metadata
import html
import urllib
from jinja2 import Template
import json

TIMELINE_SQL = """
select
  search_index.rowid,
  search_index.type,
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
  {order_by}
limit 40
"""

SEARCH_SQL = """
select
  search_index_fts.rank,
  search_index.rowid,
  search_index.type,
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
  {order_by}
limit 100
"""
FILTER_COLS = ("type", "category", "is_public")
SORT_ORDERS = {
    "oldest": "search_index.timestamp",
    "newest": "search_index.timestamp desc",
}


class InnerResponseError(Exception):
    pass


async def beta(request, datasette):
    from datasette.utils.asgi import Response
    from datasette.utils import path_with_removed_args, path_with_replaced_args

    config = datasette.plugin_config("dogsheep-beta") or {}
    database_name = config.get("database") or datasette.get_database().name
    dogsheep_beta_config_file = config["config_file"]
    template_debug = bool(config.get("template_debug"))
    rules = parse_metadata(open(dogsheep_beta_config_file).read())
    q = (request.args.get("q") or "").strip()
    sorted_by = "relevance" if q else "newest"
    if request.args.get("sort") in SORT_ORDERS:
        sorted_by = request.args["sort"]
    other_sort_orders = []
    for sort_order in ("relevance", "newest", "oldest"):
        if not q and sort_order == "relevance":
            continue
        if sort_order != sorted_by:
            other_sort_orders.append(
                {
                    "label": sort_order,
                    "url": path_with_replaced_args(request, {"sort": sort_order})
                    if sort_order != "relevance"
                    else path_with_removed_args(request, {"sort"}),
                }
            )
    results = []
    facets = {}
    count = None

    results = await search(datasette, database_name, request)
    count, facets = await get_count_and_facets(datasette, database_name, request)
    await process_results(datasette, results, rules, q, template_debug)

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
                "sorted_by": sorted_by,
                "other_sort_orders": other_sort_orders,
            },
            request=request,
        )
    )


async def search(datasette, database_name, request):
    from datasette.utils import sqlite3, escape_fts

    database = datasette.get_database(database_name)
    q = (request.args.get("q") or "").strip()

    if q:
        default_sort = "search_index_fts.rank, search_index.timestamp desc"
    else:
        default_sort = "search_index.timestamp desc"
    order_by = SORT_ORDERS.get(request.args.get("sort"), default_sort)

    params = {"query": q}
    where_clauses = []
    if request.args.get("timestamp__date"):
        where_clauses.append('date("timestamp") = :date')
        params["date"] = request.args["timestamp__date"]
    sql = TIMELINE_SQL
    if q:
        sql = SEARCH_SQL
        where_clauses.append("search_index_fts match :query")
    for arg in FILTER_COLS:
        if arg in request.args:
            where_clauses.append("[{arg}]=:{arg}".format(arg=arg))
            params[arg] = request.args[arg]
    sql_to_execute = sql.format(
        where=" where " if where_clauses else "",
        where_clauses=" and ".join(where_clauses),
        order_by=order_by,
    )
    try:
        results = await database.execute(sql_to_execute, params)
    except sqlite3.OperationalError as e:
        params["query"] = escape_fts(params["query"])
        results = await database.execute(sql_to_execute, params)
    return [dict(r) for r in results.rows]


async def process_results(datasette, results, rules, q, template_debug=False):
    # Adds a 'display' property with HTML to the results
    templates_by_type = {}
    rules_by_type = {}
    for db_name, types in rules.items():
        for type_, meta in types.items():
            rules_by_type["{}/{}".format(db_name, type_)] = meta

    for result in results:
        type_ = result["type"]
        meta = rules_by_type[type_]
        result["display"] = {}
        if meta.get("display_sql"):
            db = datasette.get_database(type_.split(".")[0])
            display_results = await db.execute(
                meta["display_sql"], {"key": result["key"], "q": q}
            )
            first = display_results.first()
            if first:
                result["display"] = dict(first)
        output = None
        if meta.get("display"):
            if type_ not in templates_by_type:
                compiled = Template(meta["display"], autoescape=True)
                templates_by_type[type_] = compiled
            else:
                compiled = templates_by_type[type_]
            try:
                output = compiled.render({**result, **{"json": json}})
            except Exception as e:
                if not template_debug:
                    raise
                output = '<p style="color: red">{}</p><pre>{}</pre><p>Template:</p><pre>{}</pre>'.format(
                    html.escape(str(e)),
                    html.escape(json.dumps(result, default=repr, indent=4)),
                    html.escape(meta["display"]),
                )
        else:
            output = "<pre>{}</pre>".format(
                html.escape(json.dumps(result, default=repr, indent=4))
            )
        result["output"] = output


async def get_count_and_facets(datasette, database_name, request):
    from datasette.utils.asgi import Request, Response
    from datasette.utils import sqlite3, escape_fts

    q = (request.args.get("q") or "").strip()
    timestamp__date = request.args.get("timestamp__date") or ""

    async def execute_search(searchmode_raw):
        args = {
            "_facet": ["type", "category", "is_public"],
            "_facet_date": ["timestamp"],
            "_size": 0,
        }
        if q:
            args["_search"] = q
            if searchmode_raw:
                args["_searchmode"] = "raw"
        if timestamp__date:
            args["timestamp__date"] = timestamp__date
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
        inner_response = await datasette.client.get(
            path_with_query_string, cookies=request.cookies
        )
        if inner_response.status_code != 200:
            raise InnerResponseError(inner_response.status_code)
        data = inner_response.json()
        count, facets = data["filtered_table_rows_count"], data["facet_results"]
        return count, facets

    try:
        count, facets = await execute_search(True)
    except InnerResponseError as e:
        count, facets = await execute_search(False)

    facets = facets.values()
    # Rewrite toggle_url on facet_results
    # ../search_index.json?_search=wolf&_facet=type&_facet=category&_facet=is_public&_size=0&category=2
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
