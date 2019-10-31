'''
this is a scripts to create/update manager changes
it is based on a topic name
topic change will attached a change with real modfication
after topic finished, topic change also be merged
topic_change -> pci_change_mgr(repo)
real_chagne -> meta-5g-poc(repo)
functions:
    renew() -> update or create change for <issue_name>
    release() -> merge topoic change for <issue_name>
'''

import sys
from api import config
from api import gitlab_api


CONF = config.ConfigTool()
CONF.load('repo')


class Gitlab_Tools(object):

    def __init__(self, url='', token='', path='', repo='gitlabe1'):
        if not url or not token:
            self.gitlab_client = gitlab_api.init_from_yaml(path, repo)
        else:
            self.gitlab_client = gitlab_api.GitlabClient(url, token)

    @staticmethod
    def chk_mandatory_params(params, mandatory_params):
        for m_param in mandatory_params:
            if m_param not in params:
                print('Error: Mandatory params %s is not set',
                      m_param)
                sys.exit(1)

    def create_mr(self, params, brk_exists=False):
        mandatory_params = ['branch', 'project']
        self.chk_mandatory_params(params, mandatory_params)
        branch = params['branch']
        ref = 'master'
        project = params['project']
        title = 'Create MergeRequest From {}'.format(branch)
        if 'ref' in params:
            ref = params['ref']
        if 'title' in params:
            title = params['title']
        targe_branch = ref
        if 'target_branch' in params:
            targe_branch = params['target_branch']
        self.gitlab_client.set_project(project)
        mr_id = ''
        if 'mr_id' in params:
            mr_id = params['mr_id']
        page = 0
        while True:
            page += 1
            mr_list = self.gitlab_client.get_mr({'title': title}, page=page)
            if mr_list or page == 5:
                break
        if mr_list:
            print('MergeRequest Already Exists: {}'.format(mr_list))
            if brk_exists:
                sys.exit(2)
        else:
            self.gitlab_client.create_branch(branch, ref=ref)
            mr = self.gitlab_client.create_mr(branch, title, targe_branch)
            print('MergeRequest Created: {}'.format(mr))
            mr_id = mr.iid
        return mr_id

    def merge_mr(self, params):
        mandatory_params = ['title', 'project']
        self.chk_mandatory_params(params, mandatory_params)
        project = params['project']
        title = params['title']
        iids = []
        if 'mr_id' in params:
            iids = [params['mr_id']]
        srch_dict = {'title': title}
        print('mr_id is: {}'.format(iids))
        self.gitlab_client.set_project(project)
        try:
            self.gitlab_client.merge_mr(srch_dict, iids=iids)
        except Exception as e:
            if self.gitlab_client.get_mr(srch_dict, iids=iids, state='merged'):
                print('Merge Request {} already merged!'.format(srch_dict))
            else:
                print(e)
                sys.exit(2)

    def update_mr(self, params, params_new):
        mandatory_params = ['title', 'project']
        self.chk_mandatory_params(params, mandatory_params)
        project = params['project']
        title = params['title']
        iids = []
        if 'mr_id' in params:
            iids = [params['mr_id']]
        srch_dict = {'title': title}
        print('mr_id is: {}'.format(iids))
        self.gitlab_client.set_project(project)
        mr_list = self.gitlab_client.get_mr(srch_dict, iids=iids)
        if len(mr_list) != 1:
            print('Error: find MR {} error!'.format(title))
            sys.exit(2)
        mr = mr_list[0]
        for item in params_new:
            print('Info: update MR {} to {}'.format(item, params_new[item]))
            exec("mr.{} = '{}'".format(item, params_new[item]))
        mr.save()
