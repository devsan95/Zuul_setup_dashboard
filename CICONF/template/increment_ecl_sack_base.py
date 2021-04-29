mail_object = {'Integration {topic}': [
    {"General Information": [
        ('Integration Name', '{topic}'),
        ('Skytrack link', '{topic_link}'),
        ('Incremented Date', '[function]get_date_time')]},
    {'Increment ECL_SACK_BASE Result': '{increment_result}'},
    {'5G CB SCM Contact': [('Create Jira ticket here', '[link]https://jiradc.ext.net.nokia.com/secure/CreateIssueDetails!init.jspa?pid=44082&issuetype=3&description=%0A%0A%3CPut%20details%20about%20your%20problem%20here%3E')]}]}

mandatory_params = ['topic']
