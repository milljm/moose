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
import argparse

# Current Harbor API version
API_V = 'v2.0'

# Harbor Address
ADDRESS = 'mooseharbor.hpc.inl.gov'

class Harbor:
    """
    Generate API calls necessary to complete requests
    """
    def __init__(self, server=ADDRESS):
        self.server = server
        self.args = self.parse_arguments()

    def _url_api(self):
        return f'https://{self.server}/{API_V}'

    def _url_projects(self):
        return f'{self._url_api()}/projects'

    def _url_users(self):
        return f'{self._url_api()}/users'

    def _url_user_id(self, user_id):
        return f'{self._url_users}/{user_id}'

    def get_url(self):
        """
        Return formated URL
        """
        return getattr(self, f'_url_{self.args.slug}')()

    @staticmethod
    def parse_arguments():
        """
        Parse aguments
        """
        parser = argparse.ArgumentParser(description='Generate API URLs based on provided'
                                         ' arguments')
        return parser.parse_args()

    def main(self):
        """
        Entry point
        """
        print(self.get_url())

if __name__ == '__main__':
    sys.exit(Harbor().main())
