import sys

# Remove current dir from sys.path, otherwise setuptools will peek up our
# module instead of system's.
sys.path.pop(0)
import setuptools

sys.path.append("./sdist_upip")
import sdist_upip

with open('README.md') as readme_file:
    README = readme_file.read()

with open('HISTORY.md') as history_file:
    HISTORY = history_file.read()

install_requires = ['uasyncio']

setuptools.setup(
    name="micropython-async_websocket_client",
    version="0.1.9",
    description='Asynchronous websocket client for ESP32 controller.',
    long_description_content_type="text/markdown",
    long_description=README + '\n\n' + HISTORY,
    license='Apache License 2.0',
    author='Vladimir Badashkin',
    author_email='bd_postbox1@mail.ru',
    keywords=['ESP32', 'micropython', 'websocket', 'asynchronous', 'client'],
    url='https://github.com/Vovaman/micropython_async_websocket_client',
    download_url='https://github.com/Vovaman/micropython_async_websocket_client/releases',
    cmdclass={'sdist': sdist_upip.sdist},
    install_requires=install_requires,
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    packages=["async_websocket_client"]
)
