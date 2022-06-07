# Wizard Kitchen

*Wizard Kitchen* is a small site that aims to provide some sort of guidance on how well certain cooking ingredients might go together.
Materials are compared to one another by looking at how many (and which) flavor molecules they share.

## Running the application

You will need a Python (3.9+) environment with [Django](https://docs.djangoproject.com) and [Requests](https://requests.readthedocs.io/en/latest/) installed.
Compiling the stylesheets also requires [Sass](https://sass-lang.com/).

If you are using the [Nix](https://nixos.org/) package manager, there is a [Flake](https://nixos.wiki/wiki/Flakes) in this repository that allows the environment to be set up automatically:

```shell
$ nix build ".#devEnv" -o .env
# Or:
$ nix develop
```

The default configuration will use an SQLite database located in the `data` directory.
You can change this (and other settings) by creating a configuration file called `local_settings.py`.
Place it somewhere in your Python path – while developing, you can just leave it in the project's root directory.
In there, you can set any [Django setting](https://docs.djangoproject.com/en/4.0/ref/settings/).
Most notably, you might want to change [`DATABASES`](https://docs.djangoproject.com/en/4.0/ref/settings/#databases) (the database is called `default`).
When deploying to production, [`ALLOWED_HOSTS`](https://docs.djangoproject.com/en/4.0/ref/settings/#allowed-hosts), [`DEBUG`](https://docs.djangoproject.com/en/4.0/ref/settings/#debug) and [`SECRET_KEY`](https://docs.djangoproject.com/en/4.0/ref/settings/#secret-key) might also be interesting.

Once the environment is set up, download [FooDB's JSON dump](https://foodb.ca/downloads) and extract it somewhere.
Then you can populate the database:

```shell
$ python -m migrate
$ python -m cookpot sync --foodb-path /path/to/foodb_2020_04_07_json
```

## Data sources

Data is currently sourced from these two projects:

- Neelansh Garg, Apuroop Sethupathy, Rudraksh Tuwani, Rakhi Nk, Shubham Dokania, Arvind Iyer, Ayushi Gupta, Shubhra Agrawal, Navjot Singh, Shubham Shukla, Kriti Kathuria, Rahul Badhwar, Rakesh Kanji, Anupam Jain, Avneet Kaur, Rashmi Nagpal and Ganesh Bagler. 2018. [FlavorDB: a database of flavor molecules](https://cosylab.iiitd.edu.in/flavordb/). *Nucleic Acids Research* 46, D1 (January 2018), D1210–D1216. DOI:[10.1093/nar/gkx957](https://doi.org/10.1093/nar/gkx957).
- The Metabolomics Innovation Centre (TMIC), Canada Foundation for Innovation and Canadian Institutes of Health Research. [FooDB](https://foodb.ca/).

Both are used according to their creative commons licenses.
Note that most records there denote more explicit references for individual ingredient data.
Please check there for exact sources.

There is also a third research project which follows similar ambitions as the two aforementioned references.
Data from there has not been included yet:

- Andreas Dunkel, Luo Guangjuan and Somoza Veronika. 2021. [Food Systems Biology Database (FSBI-DB)](https://fsbi-db.de/flavordb/). Freising, Germany.

