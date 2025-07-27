> Outdated method.
> Install this package using mip, as described in README.md.

Delete previous versions first.

# build package
```bash
$ pipenv shell
$ python -m build
```
# ...and upload to PyPi
```bash
$ twine upload dist/*
```