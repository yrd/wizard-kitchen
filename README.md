# Wizard Kitchen

## Running the application

You will need a Python (3.9+) environment with [Django](https://docs.djangoproject.com) and [Requests](https://requests.readthedocs.io/en/latest/) installed.
Compiling the stylesheets also requires [Sass](https://sass-lang.com/).

If you are using the [Nix](https://nixos.org/) package manager, there is a [Flake](https://nixos.wiki/wiki/Flakes) in this repository that allows the environment to be set up automatically:

```shell
$ nix build .#devEnv -o .env
# Or:
$ nix develop
```

Once the environment is set up, download [FooDB's JSON dump](https://foodb.ca/downloads) and extract it somewhere.
Then you can set up the database:

```shell
python -m cookpot sync --foodb-path /path/to/foodb_2020_04_07_json
```

