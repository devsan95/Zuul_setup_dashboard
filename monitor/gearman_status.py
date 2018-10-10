import re

import citools
import api.telnet_client


class GearmanStatus(object):

    def __init__(self, host, port):
        self.telnet_obj = api.telnet_client.TelnetClient(host, port)
        self.workers = self._get_workers()
        self.status = self.telnet_obj.run_cmd('status', '.')

    def _get_worker_type(self, line):
        # we use a type_dict to find the type of workers
        # for now only support 'exec' type which means jenkins executers
        # type_dict formate is :
        # { <type_name_1> :
        #     [ regex_string_1,
        #         { value_name_1 : matched_number_1,
        #           value_name_2 : matched_number_2
        #         }
        #     ],
        #   <type_name_2> :
        #     [ regex_string_2,
        #         { value_name_1 : matched_number_1,
        #           value_name_2 : matched_number_2
        #         }
        #     ]
        # }
        worker_obj = {}
        type_dict = {
            'exec': [
                '^([0-9]+)\s+([0-9,.]+)\s+(\S+)_exec-[0-9]+ :\s+(build:.*)',
                {
                    'host': 2,
                    'jobs': 4
                }
            ]
        }
        for type_name, type_regex in type_dict.items():
            re_obj = re.compile(r'%s' % type_regex[0])
            m = re_obj.match(line)
            if m:
                worker_obj['type'] = type_name
                for key, m_num in type_regex[1].items():
                    value_obj = self._extra_deal(m.group(m_num))
                    worker_obj[key] = value_obj
        return worker_obj

    def _extra_deal(self, org_str):
        if self == 'jobs':
            return org_str.strip('build:').split()
        else:
            return org_str

    def _get_workers(self):
        workers = []
        workers_content = self.telnet_obj.run_cmd('workers', '.')
        for line in workers_content.splitlines():
            worker_obj = self._get_worker_type(line)
            if worker_obj:
                workers.append(worker_obj)
        return workers

    def get_workers_bytype(self, type_name):
        workers = []
        if self.workers:
            for worker in self.workers:
                if worker['type'] == type_name:
                    workers.append(worker)
            return workers


if __name__ == '__main__':
    citools.print_path()
