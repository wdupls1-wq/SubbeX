from setuptools import find_packages, setup


APP = ["app_launcher.py"]
OPTIONS = {
    "argv_emulation": False,
    "packages": ["subbex"],
    "plist": {
        "CFBundleName": "SubbeX",
        "CFBundleDisplayName": "SubbeX",
        "CFBundleIdentifier": "io.subbex.menubar",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
}


setup(
    app=APP,
    package_dir={"": "src"},
    packages=find_packages("src"),
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
