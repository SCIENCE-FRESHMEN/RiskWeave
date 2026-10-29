from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'riskweave_console'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),

        (os.path.join('share', package_name, 'config'), glob('config/*')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*')),

    ],
    install_requires=['setuptools'],
    zip_safe=True,
    author='Suraj Borate, Bhavish Rai B',
    maintainer='Local development (unassigned)',
    maintainer_email='maintainer@example.invalid',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'chat_gui = riskweave_console.chat_gui:main',
            'chat_manager = riskweave_console.chat_manager:main',
            'task_manager = riskweave_console.task_manager:main',
            'riskweave_replanner = riskweave_console.riskweave_replanner:main',

            'speak = riskweave_console.speak:main',
            'time = riskweave_console.time:main',

            'microphone = riskweave_console.microphone:main',
            'listen = riskweave_console.listen:main',

        ],
    },
)
