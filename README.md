# OnlyLauncher
 A yet simple alternate to Multimc5/ATlauncher/..., written in python

 The goal was to make me a complete Minecraft Launcher with access to pretty much all of the minecraft loaders, and a mod gestion. It is an alternative to Multimc5 or for those who want to test offline Minecraft, to Tlauncher. The main advantage is that it is completely open in one of the easiest to understand programming language, with the most standard UI possible.
 It allows to manage mods seamlessly (for downloads/dependencies/suppression) using a very complete Modrinth API that anyone can reuse in any projects.
 It should work on most platforms, including pretty much all flavors of Linux and Windows.

## Installation/Use
Once you installed all the dependencies that are listed in `mcLaunch/requirements.txt` (the way depends on the OS/Linux distribution you are using, I'm not a big fan of having multiple separate venvs for each program), the  program starts just by running the `mcLaunch` folder with python (or whatever you renamed it to):
```sh
python mcLaunch
```

## Contribution

- This code may have some bugs... It is not very welcoming to networks errors, but that might be one of the first next things I will fix...
- Issues are welcome, AI-generated content is allowed, but should be understood, and clearly indicated. I myself used an ollama-based agent to finish it quickly without taking much time on my preparatory school.

Thanks to [Théo Rozier](https://github.com/theorzr) who wrote the python version of portablemc, an amazing work on which I was able to build my user interface pretty easely.
