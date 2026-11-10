from glob import glob

from setuptools import find_packages, setup

package_name = 'skills'

setup(
  name=package_name,
  version='0.0.1',
  packages=find_packages(exclude=['tests']),
  data_files=[
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/config', glob('config/*.yaml')),
    ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
  ],
  install_requires=['setuptools'],
  zip_safe=True,
  maintainer='Sneha Chavan',
  maintainer_email='chavansneha599@gmail.com',
  description='Wall-E BT skills (Layer 1), built on hardware_api. Mock skills for now.',
  license='TODO: License declaration',
  tests_require=['pytest'],
  entry_points={
    'console_scripts': [
      'mock_skills_node = skills.mock_skills_node:main',
    ],
  },
)
