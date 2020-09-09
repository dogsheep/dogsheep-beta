import json
import sqlite_utils
import yaml

COLUMNS = {
    "type": str,
    "key": str,
    "title": str,
    "timestamp": str,
    "category": int,
    "is_public": int,
    "search_1": str,
    "search_2": str,
    "search_3": str,
}
INDEXES = [("timestamp",), ("category",), ("is_public",)]
FOREIGN_KEYS = [("category", "categories", "id")]
DEFAULTS = {"is_public": 0}
NOT_NULL = {
    "is_public",
}

CATEGORIES = [
    {"id": 1, "name": "created"},
    {"id": 2, "name": "saved"},
    {"id": 3, "name": "received"},
]


def run_indexer(db_path, rules, tokenize="porter", databases=None):
    db = sqlite_utils.Database(db_path)
    ensure_table_and_indexes(db, tokenize)
    db.conn.close()

    # We connect to each database in turn and attach our index
    for i, (db_name, type_rules) in enumerate(rules.items()):
        if databases and db_name not in databases:
            continue
        other_db = sqlite_utils.Database(db_name)
        other_db.conn.execute("ATTACH DATABASE '{}' AS index1".format(db_path))
        for type_, info in type_rules.items():
            # Execute SQL with limit 0 to figure out the columns
            sql = info["sql"]
            # Bit of a hack - we replace the starting `select ` with one
            # that also includes the hard-coded type
            sql_rest = sql.split("select", 1)[1]
            sql = "select '{}/{}' as type,{}".format(db_name, type_, sql_rest)
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


def ensure_table_and_indexes(db, tokenize):
    db["categories"].insert_all(CATEGORIES, pk="id", replace=True)
    table = db["search_index"]
    if not table.exists():
        table.create(
            COLUMNS,
            pk=("type", "key"),
            not_null=NOT_NULL,
            defaults=DEFAULTS,
        )
    else:
        # Ensure all the column exists
        existing_columns = table.columns_dict.keys()
        for key, type_ in COLUMNS.items():
            if key not in existing_columns:
                table.add_column(key, type_, not_null_default=DEFAULTS.get(key))
    if not db["search_index_fts"].exists():
        table.enable_fts(["title", "search_1"], create_triggers=True, tokenize=tokenize)
    for index in INDEXES:
        table.create_index(index, if_not_exists=True)
    for fk in FOREIGN_KEYS:
        try:
            table.add_foreign_key(*fk)
        except sqlite_utils.db.AlterError:
            pass


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
