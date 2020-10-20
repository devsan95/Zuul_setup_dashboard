mail_object = {'Integration {topic} switch to {mode}': [
    {"General Information": [
        ('Integration Name', '{topic}'),
        ('Baseline package', '{base_package}'),
        ('Release Date', '[function]get_date_time')]},
    {'Rebase Result': '{rebase_result}'},
    {'How to rebase': '[link]https://confluence.ext.net.nokia.com/display/BTSSCMHGH/06+How+to+rebase+gerrit+change'},
    {'5G CB SCM Contact': [('Create Jira ticket here', '[link]https://jiradc.ext.net.nokia.com/secure/CreateIssueDetails!init.jspa?pid=44082&issuetype=3&description=%0A%0A%3CPut%20details%20about%20your%20problem%20here%3E')]}]}

mandatory_params = ['topic', 'base_package']
