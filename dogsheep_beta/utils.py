import json
import sqlite_utils
import yaml


def run_indexer(db_path, rules, tokenize="porter"):
    # Ensure table exists
    db = sqlite_utils.Database(db_path)
    if not db["search_index"].exists():
        db["search_index"].create(
            {
                "table": str,
                "key": str,
                "title": str,
                "timestamp": str,
                "search_1": str,
                "search_2": str,
                "search_3": str,
            },
            pk=("table", "key"),
        )
        db["search_index"].enable_fts(
            ["title", "search_1"], create_triggers=True, tokenize=tokenize
        )
    db["search_index"].create_index(["timestamp"], if_not_exists=True)
    db.conn.close()

    # We connect to each database in turn and attach our index
    for i, (db_name, table_rules) in enumerate(rules.items()):
        other_db = sqlite_utils.Database(db_name)
        other_db.conn.execute("ATTACH DATABASE '{}' AS index1".format(db_path))
        for table, info in table_rules.items():
            # Execute SQL with limit 0 to figure out the columns
            sql = info["sql"]
            # Bit of a hack - we replace the starting `select ` with one
            # that also includes the hard-coded table
            sql_rest = sql.split("select", 1)[1]
            sql = "select '{}/{}' as [table],{}".format(db_name, table, sql_rest)
            columns = derive_columns(other_db, sql)
            with other_db.conn:
                other_db.conn.execute(
                    "REPLACE INTO index1.search_index ({}) {}".format(
                        ", ".join("[{}]".format(column) for column in columns), sql
                    )
                )
        other_db.conn.close()

    # Run optimize
    db = sqlite_utils.Database(db_path)
    with db.conn:
        db["search_index"].optimize()
    db.vacuum()


def derive_columns(db, sql):
    cursor = db.conn.execute(sql + " limit 0")
    return [r[0] for r in cursor.description]


class BadMetadataError(Exception):
    pass


def parse_metadata(content):
    # content can be JSON or YAML
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError:
            raise BadMetadataError("Metadata is not valid JSON or YAML")
