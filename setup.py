import setuptools
import versioneer

setuptools.setup(
    name="project_inspect",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    url="https://github.com/Anaconda-Platform/project_inspect",
    author="Anaconda, Inc.",
    description="Analyze and inspect Anaconda Enterprise projects",
    long_description=open('README.md').read(),
    packages=setuptools.find_packages(),
    include_package_data=True,
    zip_safe=False,
)
