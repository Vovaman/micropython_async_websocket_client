from setuptools import setup, find_packages

with open('README.md') as readme_file:
    README = readme_file.read()

with open('HISTORY.md') as history_file:
    HISTORY = history_file.read()

setup_args = dict(
    name='micropython_async_websocket_client',
    version='0.1.0',
    description='Asynchronous websocket client for ESP32 controller.',
    long_description_content_type="text/markdown",
    long_description=README + '\n\n' + HISTORY,
    license='Apache License 2.0',
    packages=find_packages(),
    author='Vladimir Badashkin',
    author_email='bd_postbox1@mail.ru',
    keywords=['ESP32', 'micropython', 'websocket', 'asynchronous', 'client'],
    url='https://github.com/Vovaman/micropython_async_websocket_client',
    download_url='https://pypi.org/project/micropython_async_websocket_client/'
)

install_requires = []

if __name__ == '__main__':
    setup(**setup_args, install_requires=install_requires)