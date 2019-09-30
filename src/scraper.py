import os
import time
import re
import multiprocessing
import sys

import click
from github3 import login, GitHub
from getpass import getpass
import pickle
from PyRepo import PyRepo
from joblib import Parallel, delayed
import lockfile


def _login_github(githubUser):
    password = getpass('GitHub password for {0}: '.format(githubUser))
    g = login(githubUser, password)
    return g


def _pull_repo(name, full_name, description,
               clone_url, num_stars, num_forks,
               created_at, pushed_at, outputDirectory,
               dbFile, repos):
    repo = PyRepo(name, full_name, description, clone_url,
                  time.time(), num_stars, num_forks, created_at, pushed_at)
    if repo in repos:
        print("Skipping %s because it has already been cloned" % repo)
    else:
        try:
            # TODO: block all non-english descriptions
            if len(re.findall(r'[\u4e00-\u9fff]+', description)) > 0:
                print("Skipping %s because it contains chinese characters" % repo)
                return
            repo.clone(outputDirectory)

            with lockfile.LockFile(dbFile):
                repos.append(repo)
                print("Cloned %s" % repo.details())

                outfile = open(dbFile, "wb")
                pickle.dump(repos, outfile)
                outfile.close()

        except Exception as e:
            print("Failed to clone %s due to %s" % (repo, e))


def new(repos, githubUser, searchQuery, min_stars, language, limit, outputDirectory, dbFile):
    g = _login_github(githubUser)
    query = searchQuery + (" " if len(searchQuery) > 0 else "") + \
        "stars:>" + str(min_stars) + " language:" + language

    searchResults = g.search_repositories(query, number=limit, sort="forks")

    num_cores = multiprocessing.cpu_count()

    results = Parallel(n_jobs=2*num_cores)(
        delayed(_pull_repo)(repo.repository.name,
                            repo.repository.full_name,
                            repo.repository.description,
                            repo.repository.clone_url,
                            repo.repository.watchers,
                            repo.repository.forks_count,
                            repo.repository.created_at,
                            repo.repository.pushed_at,
                            outputDirectory,
                            dbFile,
                            repos) for repo in searchResults)


def recreate(repos, outputDirectory):
    for repo in repos:
        repo.checkout(outputDirectory)
        print("Checked out: %s" % repo.details())


def create_repos(dbFile):
    repos = []
    if os.path.exists(dbFile):
        infile = open(dbFile, "rb")
        repos = pickle.load(infile)
        infile.close()
    return repos


@click.command()
@click.option('-m', '--mode', default='new', required=True, show_default=True,
              help="'new' to generate new corpus or 'recreate' to clone corpus from dbfile.")
@click.option('-o', '--outdir', default='./.data/repos', required=True, show_default=True,
              help="Directory into which repos are cloned.")
@click.option('-d', '--dbfile', default='./.data/repos.pickle', required=True, show_default=True,
              help="List of repos to clone in 'recreate' mode or save in 'new' mode.")
@click.option('-u', '--githubuser', required=True, show_default=True,
              help="Github username.")
@click.option('-n', '--limit', default=1000, type=click.IntRange(1, 900), show_default=True, required=True,
              help="Number of repos to obtain in 'new' mode. Note that GitHub will not allow more than 900. Run this command multiple times with --search to get more than 900.")
@click.option('-s', '--search', default='', show_default=True,
              help="Search query used in 'new' mode. Use forks<[last clone forks] to get more than 900 repos.")
@click.option('-t', '--stars', default=100, type=int, show_default=True,
              help="Minimum number of stars threshold. Used in 'new' mode to search.")
@click.option('-l', '--language', default='python', show_default=True,
              help="Repo language, used in 'new' mode to search.")
def main(mode, outdir, dbfile, githubuser, limit, search, stars, language):

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    repos = create_repos(dbfile)

    if mode == "new":
        new(repos, githubuser, search, stars, language, limit, outdir, dbfile)
    elif mode == "recreate":
        recreate(repos, outdir)
    else:
        print("Mode parameter must be 'new' or 'recreate'")

    print("Done")


if __name__ == "__main__":
    main()
