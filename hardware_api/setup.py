from glob import glob

from setuptools import find_packages, setup

package_name = 'hardware_api'

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
  maintainer='Adi Kalavala',
  maintainer_email='akalaval@purdue.edu',
  description='Wall-E hardware API: ROS 2 interface to motors, sensors, servos and the can crusher.',
  license='TODO: License declaration',
  tests_require=['pytest'],
  entry_points={
    'console_scripts': [
      'drive_node = hardware_api.drive_node:main',
      'head_eyes_node = hardware_api.head_eyes_node:main',
      'audio_node = hardware_api.audio_node:main',
      'camera_node = hardware_api.camera_node:main',
      'arm_node = hardware_api.arm_node:main',
      'crusher_node = hardware_api.crusher_node:main',
    ],
  },
)
