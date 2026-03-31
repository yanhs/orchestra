from setuptools import setup, find_packages

setup(
    name="cashbot",
    version="0.1.0",
    description="CLI-утилита для фрилансеров: КП, инвойсы, расчёт стоимости",
    author="Freelancer",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "fpdf2>=2.7.0",
        "jinja2>=3.1.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cashbot=cashbot.main:cli",
        ],
    },
    package_data={
        "cashbot": ["templates/*.txt"],
    },
)
