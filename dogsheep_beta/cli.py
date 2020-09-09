import click
from .utils import parse_metadata, run_indexer


@click.group()
@click.version_option()
def cli():
    "Dogsheep search index"


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.argument(
    "config",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=True),
    required=True,
)
@click.option(
    "--tokenize",
    help="Tokenizer to use. Defaults to porter, set to none to disable.",
    default="porter",
)
@click.option(
    "-d",
    "--database",
    multiple=True,
    help="Databases to index - defaults to all",
)
def index(db_path, config, tokenize, database):
    "Create a search index based on rules in the config file"
    rules = parse_metadata(open(config).read())
    run_indexer(
        db_path,
        rules,
        tokenize=None if tokenize == "none" else tokenize,
        databases=database,
    )
