from setuptools import find_packages, setup

package_name = 'single_node_process'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Yong Jin, Cho',
    maintainer_email='drajin.cho@bosornd.com',
    description='single node process example',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'random = single_node_process.random_source_node:main',
            'square = single_node_process.square_filter_node:main',
            'sqrt   = single_node_process.sqrt_filter_node:main',
            'logger = single_node_process.logger_sink_node:main',
        ],
    },
)
