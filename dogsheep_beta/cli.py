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
def index(db_path, config):
    "Create a search index based on rules in the config file"
    rules = parse_metadata(open(config).read())
    run_indexer(db_path, rules)
