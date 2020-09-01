from setuptools import setup
import os

VERSION = "0.2"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="dogsheep-beta",
    description="Dogsheep search index",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Simon Willison",
    url="https://github.com/dogsheep/beta",
    project_urls={
        "Issues": "https://github.com/dogsheep/beta/issues",
        "CI": "https://github.com/dogsheep/beta/actions",
        "Changelog": "https://github.com/dogsheep/beta/releases",
    },
    license="Apache License, Version 2.0",
    version=VERSION,
    packages=["dogsheep_beta"],
    entry_points={
        "datasette": ["beta = dogsheep_beta"],
        "console_scripts": ["dogsheep-beta = dogsheep_beta.cli:cli"],
    },
    install_requires=["datasette", "click", "PyYAML", "sqlite-utils"],
    extras_require={"test": ["pytest", "pytest-asyncio", "httpx"]},
    tests_require=["dogsheep-beta[test]"],
)
