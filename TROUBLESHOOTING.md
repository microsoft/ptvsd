# Troubleshooting

If you're having trouble with the Debugger package for Visual Studio and VS Code, check below for information which
may help. If something isn't covered here, please file an issue with the information given
in [Filing an issue](#filing-an-issue).

## Known Issues

There are a few known issues in the current version of the debugger:
- Multiprocess debugging on a Linux machine requires the `spawn` setting. See [#943](https://github.com/Microsoft/ptvsd/issues/943).
- If you recieve an error saying  `breakpoint not set`, then look at your path mappings. See Meta-Issue [#2976](https://github.com/Microsoft/vscode-python/issues/2976) for more detail. 
- If you want to debug library files, you have to enable `debugStdLib`. See [#1354](https://github.com/Microsoft/ptvsd/issues/1354).

## Filing an issue

When filing an issue, make sure you do the following:

- Check existing issues for the same problem (also see the "Known Issues" section above for widespread problems).
- Python Extension [Version](https://code.visualstudio.com/docs/editor/extension-gallery#_extensions-view-commands).
- Debugger Version (You can find this by clicking on the launch.json file within your folder. The debugger version number will be located at the top of this file.)
- The code that you are working on as well as any additional files (i.e. requirements.txt file if you're working with a virtual environment or an environment.yml file for Conda environments).
