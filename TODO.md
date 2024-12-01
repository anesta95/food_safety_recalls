# Documentation
* Add docstrings to classes & functions. Some examples [here](https://www.programiz.com/python-programming/docstrings), [here](https://www.dataquest.io/blog/documenting-in-python-with-docstrings/), [here](https://pandas.pydata.org/docs/development/contributing_docstring.html), [here](https://www.datacamp.com/tutorial/docstrings-python), and [here](https://www.geeksforgeeks.org/python-docstrings/).
* Comment explainers for a bit more code, especially in `transform_fda_recalls.py` file.

# Operation
* Figure out how to deal with edge case of multiple FDA or USDA recalls issued with identical `notification_dttm` values.
* Get back to USDA FSIS Recall API webmaster team about optimizing HTTP GET data query (do I need request headers/cookies?)

# Optimization
* Figure out way to access functions, classes and objects shared between multiple different python file from one singular location.
* Implement in-place transform and write to `transformed_staged_data` so uid isn't always edited and code is more efficient.
* Implement logic to not add duplicate USDA recalls by notice_id_number that are available in Spanish.
* Use [dataclasses](https://docs.python.org/3/library/dataclasses.html) to enforce static typing and a common schema. More info [here](https://www.dataquest.io/blog/how-to-use-python-data-classes/) & [here](https://www.datacamp.com/tutorial/python-data-classes).
* Check out [BLN WARN project](https://github.com/biglocalnews/warn-github-flow) for mypy hinting and unit testing.
* Switch over library & virtual environment manager to [uv](https://docs.astral.sh/uv/).

# Expansion
* Publish final JSON to GH pages.
* Build an [Observable Framework](https://observablehq.com/framework/) site that's built on underlying JSON that has cool custom dashboard.
* Publish the dashboard as it's own page on GH pages.
* Use an LLM or ML to use FDA recall text to try and "pre-classify" it as Class I-III.