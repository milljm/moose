#!/usr/bin/env python3
#* This file is part of the MOOSE framework
#* https://www.mooseframework.org
#*
#* All rights reserved, see COPYRIGHT for full restrictions
#* https://github.com/idaholab/moose/blob/master/COPYRIGHT
#*
#* Licensed under LGPL 2.1, please see LICENSE for details
#* https://www.gnu.org/licenses/lgpl-2.1.html

import sys
import os
import re
import argparse
import configparser
import datetime
from collections import namedtuple
from jinja2 import Environment, DictLoader
try:
    import requests # type: ignore # for exceptions
except ModuleNotFoundError:
    print('Could not load `requests`. Please install this package.')
    sys.exit(1)
try:
    import github # type: ignore # for exceptions
    from github import Github, Auth, GithubException # type: ignore
except ModuleNotFoundError:
    print('Could not load `pygithub` module. Please install the GitHub Python API module.')
    sys.exit(1)

# ASCII Color codes
RED    = '\033[91m'
GREEN  = '\033[92m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
MOOSE_DIR = os.environ.get('MOOSE_DIR',
                           os.path.abspath(os.path.join(SCRIPT_DIR, '..')))

TEMPLATE_FILE = os.path.join(MOOSE_DIR, 'framework',
                                        'doc',
                                        'content',
                                        'templates',
                                        'sqa',
                                        'create_release.md.template')

# Keys represent the current template items in create_release.template
TEMPLATE_ENVS = {'APPLICATION'      : 'name of the application',
                 'VERSION'          : 'version of release (or date)',
                 'DEVEL_URL'        : 'URL to Civet displaying testing results for devel branch',
                 'MAIN_URL'         : 'URL to Civet displaying testing results for main branch',
                 'PROJECT_URL'      : 'URL to projects GitHub page',
                 'CIVET_RECIPE_SHA' : 'Civet Recipe SHA at the time of testing',
                 'SUBMODULES'       : 'Submodules and their SHA',
                 'SYNTAX_NAME'      : f'{RED}<YourName>{RESET}',
                 'CIVET_VERSION'    : 'CIVETs version at the time of CIVET_RECIPE_SHA'
                 }

# Syntax helper
parser = argparse.ArgumentParser(description='Output links associated with CI/CD',
                                 epilog=f'Example usage: {os.path.basename(__file__)} '
                                        '-t /path/to/token'
                                        f' github.com/idaholab/moose abc123')

class GitHubAPI():
    """ handle GH calls """
    def __init__(self, github_args):
        auth = Auth.Token(github_args.token)
        (self.__host, self.__owner, self.__repo) = github_args.uri.split('/')
        self.sha = github_args.sha
        if self.__host != 'github.com':
            self.__base_url = f'https://{self.__host}/api/v3'
            self.gh = Github(base_url=self.__base_url, auth=auth)
        else:
            self.__base_url = f'https://api.{self.__host}'
            self.gh = Github(auth=auth)

    def __del__(self):
        self.gh.close()

    @staticmethod
    def get_merge(commit)->str:
        """ return SHA responsible for creating SHA """
        return commit.raw_data['parents'][-1]['sha']

    def get_commbined_status(self, commit) ->str:
        """
        return status dictionary of supplied commit
        (only works with PR commits)
        """
        return commit.get_combined_status()

    def get_repo(self)->object:
        """ return repo object """
        try:
            repo = self.gh.get_repo(f'{self.__owner}/{self.__repo}')
        except github.GithubException as e:
            if e.status == 401:
                print('\nLooks like your token is invalid, or possibly expired.\n'
                      'Navigate to the following URL to generate a token:'
                      f'\n\n\thttps://{self.__host}/settings/tokens/new\n\n'
                      'The token will need the minimum following attributes:\n\n'
                      'for public repos:\trepo:status, repo_deployment\n'
                      'for private repos:\trepo  (full control)')
            elif e.status == 404:
                print(f'404: Not found {self.__base_url}/repos/{self.__owner}/{self.__repo}')

            sys.exit(1)
        except requests.exceptions.ConnectionError as e:
            print(f'Error connecting to server: {self.__host}\n\n{e}')
            sys.exit(1)
        return repo

    def get_commit(self, sha=None)->object:
        """ get {OWNER}/{REPO}/commits/{HASH} """
        repo = self.get_repo()
        sha = sha if sha is not None else self.sha
        try:
            commit = repo.get_commit(sha=sha)
        except github.GithubException as e:
            print(e.status, e.data['message'])
            sys.exit(1)
        return commit

class CreateRelease():
    """
    Analyze output from GitHub API for status on supplied hash,
    presenting the user with a summary of all tests involved and
    their final status.
    """
    def __init__(self, args):
        self.gh = GitHubAPI(args)
        cgh = Github()
        self.civet_repo = cgh.get_repo('idaholab/civet')
        self.commit = self.gh.get_commit()
        self.repo = self.gh.get_repo()
        self.sha = args.sha
        self.combined_status = self.commit.get_combined_status()

    @staticmethod
    def get_submodules(repo: object)->list[tuple[str: 'name', str: 'path', str: 'sha']]:
        """ return a list of namedtuple(submodule, path) for provided commit """
        config = configparser.ConfigParser()
        named_module = namedtuple('module', ('name', 'path', 'sha'))
        modules = []
        try:
            gitmodule_file = repo.get_contents('.gitmodules')
        except GithubException:
            return []
        if gitmodule_file:
            config_content = gitmodule_file.decoded_content.decode()
            config.read_string(config_content)
            for section in config:
                # configparse is weird bro. Like it needs to initialize before populating
                # values (read_string aint enough?). Must be a constuctor or something
                if config[section].get('path', None) is None:
                    continue
                # Bug: I've seen 'path' return 'path', 'url', and 'update' in the same value...
                # hence the line split[0]. (the mfem submodule in moose does triggers the bug)
                m_path = config[section]['path'].split()[0]
                # create namedtuple(module_name, path)
                repo_file = repo.get_contents(m_path)
                modules.append(named_module(os.path.basename(m_path), m_path, repo_file.sha))
        return modules

    @staticmethod
    def get_parent(commit)->bool:
        """ return if multiple parent commits exist """
        return len(commit.parents) > 1

    @staticmethod
    def decorate(args, commit, pre_msg)->str:
        """ Depending on the pre_msg, print a civet_event """
        civet_event = ('Civet Event: '
        f'https://civet.inl.gov/sha_events/{"/".join(args.uri.split("/")[1:])}/{commit.sha[:7]}')
        github_event = f'GitHub Push: {"/".join(commit.html_url.split("/")[:-1])}/{commit.sha[:7]}'
        if pre_msg == 'PR':
            return github_event
        return f'{github_event}\n{civet_event}'

    def yield_statuses(self, status_list)->namedtuple:
        """ yield all statuses for a given status list """
        yield from status_list

    @staticmethod
    def uniqueify_statuses(status_tuples, final_status)->list[namedtuple]:
        """
        GitHub returns all status including those which ran multiple time. This
        will lead to duplicate tests (invalidations on Civet) with different
        statuses.

        This method seeks to remove those duplicates by adjusting their status
        to the final combined status as seen by GitHub (all tests eventually
        passed).
        """
        commit_status = namedtuple('CommitStatus', ('state',
                                                    'context',
                                                    'target_url',
                                                    'description',
                                                    'updated_at'))
        tests = {}
        for status in status_tuples:
            if status.context not in tests:
                tests[status.context] = commit_status(status.state,
                                                      status.context,
                                                      status.target_url,
                                                      status.description,
                                                      status.updated_at)
                continue
            if tests[status.context] == commit_status(status.state,
                                                      status.context,
                                                      status.target_url,
                                                      status.description,
                                                      status.updated_at):
                continue
            # This is our duplicate invalidated test. Assume 'group' status.
            override_status = f'{"success" if final_status else "failure"}'
            tests[status.context] = commit_status(override_status,
                                                  status.context,
                                                  status.target_url,
                                                  status.description,
                                                  status.updated_at)

        # return the same object type we started with
        return list(value for value in tests.values())

    def _loop_statuses(self, commit)->list[namedtuple]:
        """ iterate over commit SHA to get statuses involved """
        _group = []
        tuple_list = commit.get_statuses()
        for status in self.yield_statuses(tuple_list):
            _group.append(status)
        _group = self.uniqueify_statuses(_group, self.did_pass())
        return _group

    def get_statuses(self, commit=None)->list[tuple[str,list[namedtuple]]]:
        """
        return all statuses involved with given commit SHA, this
        will recursively delve into parent commits involved
        main <- devel <- PR (whenever there was a merge)
        """
        commit = self.commit if self.commit else commit
        statuses = []
        while self.get_parent(commit):
            statuses.append((commit, self._loop_statuses(commit)))
            commit = self.gh.get_commit(commit.parents[-1].sha)
        # One last time, as we are sitting on the last commit of [-1]
        # from above loop.
        statuses.append((commit, self._loop_statuses(commit)))
        return statuses

    def did_pass(self):
        """ BOOL if every status is successful """
        return self.combined_status.state == 'success'

    def get_civet_version(self, date):
        """ return CIVET version based on date of release """
        return self.civet_repo.get_commits(until=date)[0].sha

def get_recipe_sha(group: int, statuses: list[tuple[str: 'state',
                                                    str: 'context',
                                                    str: 'target_url',
                                                    str: 'description',
                                                    str: 'updated_at']])->str:
    """
    Return Civet recipe SHA for given group in statuses. While not 100% accurate,
    the returned SHA will be the last recipe returned. See 'get_test_groups' for
    an understanding on groups.
    """
    recipe_re = re.compile(r'recipe:([0-9a-f]+),')
    groups = [statuses[:1]]
    if statuses[1:-1] == statuses[-1:]:
        groups.append(statuses[-1:])
    else:
        groups.extend([statuses[1:-1], statuses[-1:]])
    recipe_sha = recipe_re.findall(groups[group][0][1][0].description)
    recipe_sha = ''.join(recipe_sha) if recipe_sha else 'N/A'
    return recipe_sha

def get_test_groups(statuses: list[tuple[str: 'state',
                                         str: 'context',
                                         str: 'target_url',
                                         str: 'description',
                                         str: 'updated_At']])->tuple[list[str],list[tuple]]:
    """
    Statuses contains a list of lists of GitHub status tuples. Each list consists of
    a group of tests performed by a branch. In the case of MOOSE, with a tiered CI system:
    [[main],[devel],[next],[pr]] means: [1:-1] is the 'middle' (devel, next, etc) therefor
    edge cases will be main [:1] and PRs [-1:].

    This method returns two lists of identical sizes. One, the statuses, the other, the
    branch name/identifier:

    return (['MAIN/MASTER', 'DEVEL/NEXT', 'DEVEL/NEXT', 'PR'],
           [[Status for MAIN],[Status for Devel],[Status for Next],[Status for PR]])
    """
    groups = [statuses[:1]]
    labels = ['MAIN/MASTER:']
    # if project only has 'PR --> MAIN'
    if statuses[1:-1] == statuses[-1:]:
        groups.append(statuses[-1:])
        labels.append('PR:')
    else:
        groups.extend([statuses[1:-1], statuses[-1:]])
        labels.extend(['DEVEL/NEXT:', 'PR:'])
    return (labels, groups)

def create_release(statuses: list[tuple[str: 'state',
                                        str: 'context',
                                        str: 'target_url',
                                        str: 'description',
                                        str: 'updated_at']],
                   modules: list[tuple[str: 'name', str: 'path', str: 'sha']],
                   civet_url: str,
                   cr: CreateRelease,
                   **kwargs)->None:
    """ print the statuses to stdout """
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        contents = f.read()

    env = Environment(loader = DictLoader({'' : contents}),
                      trim_blocks=True,
                      lstrip_blocks=True)
    modules_str = ''
    if modules:
        max_length = max(len(module.name) for module in modules) + 3
        for module in modules:
            modules_str += f'\t\t{module.name.ljust(max_length)}{module.sha[-8:]}\n'

    meta_template = env.get_template('')
    _, groups = get_test_groups(statuses)
    release_date = groups[0][0][1][0].updated_at
    civet_sha = cr.get_civet_version(release_date)
    TEMPLATE_ENVS['APPLICATION'] = f'{GREEN}{os.path.basename(kwargs["uri"]).upper()}{RESET}'
    TEMPLATE_ENVS['VERSION'] = f'{GREEN}{kwargs["create_release"]}{RESET}'
    TEMPLATE_ENVS['DEVEL_URL'] = f'{GREEN}{civet_url}/{groups[1][0][0].sha[:8]}{RESET}'
    TEMPLATE_ENVS['MAIN_URL'] = f'{GREEN}{civet_url}/{groups[0][0][0].sha[:8]}{RESET}'
    TEMPLATE_ENVS['TEST_DATE'] = f'{GREEN}{release_date}{RESET}'
    TEMPLATE_ENVS['PROJECT_URL'] = f'{GREEN}https://{kwargs["uri"]}{RESET}'
    TEMPLATE_ENVS['CIVET_RECIPE_SHA'] = f'{GREEN}{get_recipe_sha(0, statuses)}{RESET}'
    TEMPLATE_ENVS['CIVET_VERSION'] = f'{GREEN}{civet_sha}{RESET}'
    TEMPLATE_ENVS['SUBMODULES'] = f'{GREEN}{modules_str}{RESET}'
    meta_render = meta_template.render(TEMPLATE_ENVS)
    print(f'\n\n{meta_render}')

def print_statuses(statuses: list[tuple[str: 'state',
                                        str: 'context',
                                        str: 'target_url',
                                        str: 'description',
                                        str: 'updated_at']],
                   modules: list[tuple[str: 'name', str: 'path', str: 'sha']],
                   civet_url: str,
                   github_url: str):
    """ print the statuses to stdout """
    labels, groups = get_test_groups(statuses)
    if modules:
        # Print submodules involved at their recorded hashes
        print(f'\n{BOLD}Submodule(s):{RESET}')
        max_length = max(len(module.name) for module in modules) + 3
        for module in modules:
            print(f'\t{module.name.ljust(max_length)}{module.sha[-8:]}')

    # Begin to print statuses
    for label_index, group in enumerate(groups):
        _sha = [x[0] for x in group][0].sha
        recipe_sha = get_recipe_sha(label_index, statuses)

        # CIVET does not record sha events for PRs
        events = (f'\n{BOLD}CIVET Event:{RESET} {civet_url}/{_sha[:8]}\n'
                  f'{BOLD}GitHub Event:{RESET} {github_url}/{_sha[:8]}'
                  if 'PR' not in labels[label_index] else '')

        print(f'\n{BOLD}{labels[label_index]}{RESET} '
              f'Recipe SHA: {BOLD}{recipe_sha}{RESET}{events}')
        # transverse list[(commit, namedtuple())]
        for meta in group:
            (_, tests) = meta
            for test in tests:
                print(f'\t{GREEN if test.state == "success" else RED}{test.state}{RESET}'
                      f' {test.context} {test.target_url}')

def check_args(argv)->object:
    """ checks command line options """
    c_args = parse_args(argv)

    # verify all arguments are supplied
    if not c_args.uri or not c_args.sha or not c_args.token:
        print('ERROR: required arguments missing. Usage:\n')
        parser.print_help()
        sys.exit(1)

    # verify proper URI
    if len(c_args.uri.split('/')) != 3:
        print(f'\nSupplied URI not properly constructed: {c_args.uri}\nThe URI should contain'
              ' three items separated by forward slashes.\n\n\thostname/namespace/repo\n')
        sys.exit(1)

    ### determine how to handle token
    # ...supplied path to token
    if os.path.exists(c_args.token):
        with open(c_args.token, 'r', encoding='utf-8') as t_file:
            c_args.token = str(t_file.read()).strip()
    # ...supplied environment variable with path to token
    elif os.getenv(c_args.token, None) and os.path.exists(os.getenv(c_args.token, None)):
        with open(os.getenv(c_args.token, None), 'r', encoding='utf-8') as t_file:
            c_args.token = str(t_file.read()).strip()
    # ...supplied environment variable with token
    elif os.getenv(c_args.token, None):
        c_args.token = os.getenv(c_args.token)
    elif len(c_args.token) != 40:
        print('WARING: supplied token is not of the correct length, and is therefor'
              ' probably\nwrong. Permission errors mar occur.\n')
    # ...if nothing was true, then assume argument supplied is the token

    return c_args

def parse_args(argv)->object:
    """ parses arguments """
    parser.add_argument('uri', nargs='?', metavar='URI',
                        help='URI to GitHub repo. exp: github.com/idaholab/moose')
    parser.add_argument('sha', nargs='?', metavar='SHA',
                        help='Povided SHA to be considered for release')
    parser.add_argument('-t','--token',
                        help='Your GitHub API Token. Can either be an environment variable'
                        ' containing your token, or a path to a file containing your token, or '
                        ' the token itself. For security purposes, ideally this should be a path'
                        ' to your token. To create a token, see:'
                        ' https://github.com/settings/tokens')
    parser.add_argument('-p','--print-status', action='store_true', default=False,
                        help='Print all statuses relating to provided SHA')
    parser.add_argument('-c','--create-release',
                        help='Output a release for SHA, and tag it with supplied version')
    parser.add_argument('-d','--debug', action='store_true', default=False,
                         help='Print API URL calls')

    return parser.parse_args(argv)

def main(args):
    """ entry point """
    cr = CreateRelease(args)
    github_event = f'{"/".join(cr.commit.html_url.split("/")[:-1])}/{cr.commit.sha[:8]}'
    civet_event = (f'https://civet.inl.gov/sha_events/'
                   f'{"/".join(args.uri.split("/")[1:])}/{cr.commit.sha[:8]}')
    github_event = f'{"/".join(cr.commit.html_url.split("/")[:-1])}'
    civet_event = (f'https://civet.inl.gov/sha_events/'
                   f'{"/".join(args.uri.split("/")[1:])}')
    if args.print_status:
        status = cr.did_pass()
        print(f'\nCI results for {BOLD}{args.sha[:7]}:{RESET}{GREEN if status else RED}'
              f'{"PASS" if status else "FAILED"}{RESET} Obtaining details...')
        modules = cr.get_submodules(cr.repo)
        all_statuses = cr.get_statuses(cr.commit)
        print_statuses(all_statuses, modules, civet_event, github_event)
        print('\n\nIf you are satisfied with these results and would like to create a release '
              'please run the script again with -c|--create-release and follow the '
              'instructions.')
    elif args.create_release:
        print('Gathering submodule information...')
        modules = cr.get_submodules(cr.repo)
        print('Gathering test information for Civet Recipe SHA, Test Date, etc...')
        all_statuses = cr.get_statuses(cr.commit)
        create_release(all_statuses, modules, civet_event, cr, **vars(args))

if __name__ == '__main__':
    m_args = check_args(sys.argv[1:])
    sys.exit(main(m_args))
