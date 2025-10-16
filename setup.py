from glob import glob

from setuptools import setup

package_name = "edubot"

setup(
    name=package_name,
    version="1.0.0",
    packages=[package_name],
    # Files we want to install with the package
    data_files=[
        # Install marker for ament to find this package - REQUIRED
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        # Install package.xml for ROS to find and setup dependencies - REQUIRED
        ("share/" + package_name, ["package.xml"]),
        # Install launch files - OPTIONAL
        ("share/" + package_name, glob("launch/*.launch.py")),
        # Install all other files such as URDF, meshes, and config files - OPTIONAL
        ("share/" + package_name + "/urdf/", glob("urdf/*")),
        ("share/" + package_name + "/meshes/", glob("meshes/*")),
        ("share/" + package_name + "/config/", glob("config/*")),
    ],
    # Python dependencies for this package, setuptools REQUIRED
    install_requires=["setuptools"],
    zip_safe=True,
    author="Devson Butani",
    author_email="dbutani@ltu.edu",
    maintainer="Devson Butani",
    maintainer_email="dbutani@ltu.edu",
    description="EduBot robot description package",
    license="MIT",
    # Add executable Python scripts and their entry points (usually 'main') here
    entry_points={  # example: 'my_script = my_package.my_script:main'
        "console_scripts": [],
    },
)
