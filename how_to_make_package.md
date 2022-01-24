# build package
```bash
$ pipenv shell
$ python setup.py sdist
```
# ...and upload to PyPi
```bash
$ rm dist/*.orig
$ python -m twine upload dist/*
```