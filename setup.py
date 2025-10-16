from setuptools import setup
from glob import glob

package_name = "edubot"

setup(
    name=package_name,
    version="1.0.0",
    packages=[package_name],
    data_files=[  # Add all the files to be built and installed by colcon build
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name, glob("launch/*.py")),
        ("share/" + package_name + "/urdf/", glob("urdf/*")),
        ("share/" + package_name + "/meshes/", glob("meshes/*")),
        ("share/" + package_name + "/config/", glob("config/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Devson Butani",
    maintainer_email="dbutani@ltu.edu",
    description="EduBot robot description package",
    license="MIT",
    entry_points={  # Add executable scripts and their entry points here
        "console_scripts": [],
    },
)
