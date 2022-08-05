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
    name="datasette-scale-to-zero",
    description="Quit Datasette if it has not received traffic for a specified time period",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Simon Willison",
    url="https://github.com/simonw/datasette-scale-to-zero",
    project_urls={
        "Issues": "https://github.com/simonw/datasette-scale-to-zero/issues",
        "CI": "https://github.com/simonw/datasette-scale-to-zero/actions",
        "Changelog": "https://github.com/simonw/datasette-scale-to-zero/releases",
    },
    license="Apache License, Version 2.0",
    classifiers=[
        "Framework :: Datasette",
        "License :: OSI Approved :: Apache Software License",
    ],
    version=VERSION,
    packages=["datasette_scale_to_zero"],
    entry_points={"datasette": ["scale_to_zero = datasette_scale_to_zero"]},
    install_requires=["datasette"],
    extras_require={"test": ["pytest", "pytest-asyncio"]},
    python_requires=">=3.7",
)
