"""
MeshIdentity - 本地Agent多终端统一身份与记忆同步

setup.py for pip package
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="mesh-identity",
    version="0.1.0",
    author="Nyx (硅基文明数据库项目)",
    author_email="nyx@anima.org",
    description="本地Agent多终端统一身份与记忆同步SDK - 让本地部署的AI Agent具备跨设备身份连续性和记忆同步能力",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/deanhan2026-lang/mesh-identity",
    project_urls={
        "Bug Tracker": "https://github.com/deanhan2026-lang/mesh-identity/issues",
        "Documentation": "https://github.com/deanhan2026-lang/mesh-identity/docs",
        "Source Code": "https://github.com/deanhan2026-lang/mesh-identity",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Distributed Computing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Framework :: Agent",
        "Environment :: Console",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pynacl>=1.5.0",
        "cryptography>=41.0.0",  # 私钥加密存储
        "watchdog>=3.0.0",
        "pyyaml>=6.0",
        "requests>=2.28.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
        "nas": [
            "pysmb>=1.2.0",  # SMB协议支持
            "paramiko>=3.0.0",  # SFTP支持
        ],
    },
    entry_points={
        "console_scripts": [
            "mesh-id=cli.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "mesh_identity": [
            "docs/*.md",
            "config/*.yaml",
            "templates/*.json",
        ],
    },
    keywords=[
        "ai-agent",
        "identity",
        "memory-sync",
        "multi-terminal",
        "decentralized",
        "local-deployment",
        "did",
        "mesh-network",
    ],
)
